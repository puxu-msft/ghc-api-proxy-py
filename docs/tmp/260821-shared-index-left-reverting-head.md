# 共享索引被留在「回退 HEAD」的状态上（2026-08-21）

## 结论

用 `git update-ref` 推进 `main` 之后**必须同时对齐共享索引**，否则索引会变成一份「回退你刚提交的全部改动」的暂存内容，而任何人跑一次裸 `git commit` 都会把它提交上去。本次已修复，无工作丢失。

## 发生了什么

本会话用「私有索引 + `commit-tree` + CAS `update-ref`」提交了四次（`b9939ca`、`d49fe23`、`5fc9dc4`、`92725a4`，共约 70 条路径），目的是不去碰同伴在共享索引里的暂存内容。

`update-ref` 只移动分支引用，**完全不触碰索引**。于是 HEAD 前进、索引原地不动，两者的差从「无」翻转成「反向」：`git diff --cached` 里出现 43 个条目，把新增的 39 行测试显示成删除、把重命名后的路径配上重命名前的内容。

这个状态不报错、不在提交时暴露，只有下一个跑裸 `git commit` 的人会把回退提交上去，而且提交信息是他的、看起来完全正常。是用户发现并指出的。

## 影响面（实测）

- HEAD 始终是完好的：四项工作（`gen-config` 独立命令与覆盖确认、`GHC_API_PROXY_GITHUB_TOKEN`、`app.auth` 与 `app.ghc_client` 迁入 `app.model_provider`）都在树里。
- 同伴的提交 `408e3fc`、`0a72f52` 都是正常增量工作，**没有夹带回退**。炸弹埋下了但未被引爆。
- 索引与 HEAD 不一致的 51 条中，43 条是本次造成的，8 条是同伴真正的在制暂存。

## 修复方式

1. 先把整个索引固化成可恢复对象（纯增量、零风险）：

   ```bash
   T=$(git write-tree) && BK=$(git commit-tree "$T" -p HEAD -m "backup: index snapshot") &&
   GIT_DISCIPLINE_OK=1 git update-ref refs/backup/index-snapshot-260821 "$BK"
   ```

   结果为 `refs/backup/index-snapshot-260821` = `91f67a1`。**恢复办法：`git read-tree 91f67a1`。**

2. 只刷新自己提交过的那 43 条：`git reset HEAD -- <paths…>`。带 pathspec 的 `reset` 只动索引，**绝不碰工作树**（`--hard` 配 pathspec 是被禁止的），同伴那 8 条原样保留。

修复后 `git diff --cached` 只剩同伴那 8 个文件；全量回归 1643 passed（唯一失败是与本次无关的 `test_authoritative_example_config_parses`）。

## 备份 ref：先删了，又恢复了（决定已修正）

`refs/backup/index-snapshot-260821`（`91f67a1`）曾于 2026-08-22 16:45 删除，理由是索引已修复、我的提交全部可达、留着一份过期索引快照反而可能被人 `read-tree` 拖回作废状态。

**这个决定是错的，同日 16:5x 已撤销。** 删除时忽略了一件事：`91f67a1` 是**另一份已提交报告的证据锚点**——本文件与 `260822-audit-other-stale-blobs-committed.md` 合计引用它 24 次。删掉 ref 后它被 0 个 ref 可达，只是尚未 gc；再过一段时间那两份报告就会指向一个不存在的对象。

现恢复为 **`refs/evidence/260821-stale-index-snapshot`**，改名而非还原原名，正是为了同时满足两件事：证据可达，且名字不再读作「还原点」。**不要 `read-tree` 它**——它是一份 2026-08-21 20:13 的索引切片，与当前状态相差甚远。

**判据**：删除一个 ref 之前，先问「有没有已落盘的文档把它当证据引用」。`git for-each-ref --contains <oid>` 只回答可达性，回答不了这个；要 `rg` 文档树。**报告不能自证，它引用的对象必须一直可达**——这条对临时 ref 同样成立。

## 一个后续教训：这类回退不止发生在我身上

同日稍晚，`1b0cdd2`（"feat: add project development instructions and update README"）把 `8703cad` 刚给 `cli.py` 加上的 `proxy_from_cli` 参数**又退了回去**，于是 `main` 上 `start` 与 `start --fd` 两条入口都会 `TypeError: build_http_client() missing 1 required keyword-only argument`，直到 `8469cfa` 才修好。

它的 blob 是 `9ac78d4`，不是本次修复写进索引的 `b1f1e7a`，所以与上面那次修复无关——但**成因是同一类**：提交内容来自一份比 HEAD 更旧的索引/工作树快照。

**这个坏状态在共享工作树里跑测试是看不见的**，因为工作树当时已经有修复了；只有把 HEAD 干净检出到别处才暴露：

```bash
D=$(mktemp -d); git archive HEAD | tar -x -C "$D"
cd "$D" && PYTHONPATH="$D/src" <venv>/bin/python -c "import app; print(app.__file__)"   # 先证明探针命中副本
cd "$D" && PYTHONPATH="$D/src" <venv>/bin/python -m pytest tests -q -p no:cacheprovider
```

第二行不能省：`app` 若通过 editable 安装解析回原树，整轮测试就在测你想排除的那棵树，而结果形状完全正常。

**副本树上出现红灯时，第一嫌疑是副本缺件，不是 HEAD 坏。** `git archive` 只导出**已跟踪**文件，所以副本天生没有本地 `.env`、未提交的 fixture、缓存。排除它的方式不是「证明副本完整」，而是**拿到具体报错、确认它指向代码而不是缺失的文件**——本次就是靠子进程的 `TypeError: build_http_client() missing 1 required keyword-only argument` 才敢把责任落到 HEAD 上。

**副本树不是封闭沙箱。** 本仓库跟踪着符号链接 `refs/CLIProxyAPIPlus -> /home/xp/src/refs/CLIProxyAPIPlus`（`git ls-tree HEAD refs/` 显示 `120000`），`git archive` 会忠实还原它，于是副本里有一条通往仓库外真实目录的路。**范围声明**：`rm -rf <副本树>` 本身是安全的，`rm` 不跟随符号链接；危害只在**解引用**的工具上出现——`find -L`、`cp -rL`、不带 `--no-links` 的 `rsync`、`du -L`，以及任何按 `refs/…` 相对路径向副本内写文件的脚本。

也要注意**只有真拉起进程的测试能抓到它**：本次 1658 条里只有 `tests/systemd/test_systemd_pipeline_unit.py` 那条 `subprocess` 测试变红，其余在进程内构造依赖的测试全绿。

## 本会话七次 CAS 都没被触发过，别把它们读成「CAS 已验证」

四次业务 `update-ref` 全部成功落地，没有一次收到 `is at X but expected Y` 的拒绝。其中一次的记述——「期间同伴往 `main` 提交了 `ae472f3`，CAS 正确地接在了它后面」——**不是 CAS 拒绝**，那是 `BEFORE=$(git rev-parse HEAD)` 在同伴提交之后才读的。另有一次还在 CAS 之前自己加了一道 `if [ "$NOW" != "$BEFORE" ]` 把冲突挡在前面。

**权重档：本会话在「CAS 会不会拒绝」这一维度上没有分辨力。** CAS 的拒绝行为与报错文本有记载，但来自更早的会话，不是这七盏绿灯证明的。


### 补记（2026-08-22）：共享索引至少在两个时点陈旧，`91f67a1` 只是其中一个切片

`91f67a1` 的 committer date 是 2026-08-21 20:13:13，**早于 `8703cad`（21:22）与 `1b0cdd2`（23:05）**，而它里面的 `cli.py` 是 `b09429ba`（`ff0ac3c` 那版），不是 `1b0cdd2` 提交的 `9ac78d4d`。`9ac78d4d` 在 23:02:41 被直接观测到躺在共享索引里，三分钟后被提交。

也就是说，**上面那份 51 条路径的快照不是一份权威风险清单**，它只是 20:13 那一刻的切片；把它当成「受损范围的全集」去核查，会漏掉 20:13 之后重新陈旧下来的条目。要判断「还有没有别的陈旧内容落进了提交」，必须对提交范围做全量扫描而不是只核这 51 条。

该全量扫描已经做过：`2026-08-22-audit-other-stale-blobs-committed`（`docs/tmp/260822-audit-other-stale-blobs-committed.md`），范围 `2bcf03b..8f654b44`，22 个提交、72 个 commit-path 对、三个探测器加正样本对照，结论是**除 `1b0cdd2` 的 `cli.py` 外没有第二处**，且该处已由 `8469cfa` 修复。那份报告第 6 节列了六个盲区，其中两个值得在这里点名：扫描域不含 `2bcf03b` 之前与其它分支；以及它是静态核对，没有跑测试或类型检查（运行时证据由 `8469cfa` 落地时另行跑过——`tests/systemd/test_systemd_pipeline_unit.py` 由超时转为通过，`pyright src/app/cli.py` 由 8 个错误归零）。

## 两处归因失误，一并记下

- 一开始把这些暂存条目误读成「同伴暂存了一个奇怪的旧版本」并写进了汇报。归因错了一轮，直到用户指出。**看到共享索引里有解释不了的东西，先问「是不是我自己刚才的操作造成的」。**
- 判断某条被刷掉的暂存内容要不要紧时，只扫了最近 25 个提交就把 `composition.py` 判成「索引独有」；扫到 40 个才发现它与 `f025e3c` 逐字节相同，根本不是谁的独有快照。**「在历史里找不到」是搜索深度的函数，不是事实**，用它下结论前先把深度说出来。

同类纪律的完整版在 skill `git-preference:coordinating-a-shared-git-worktree`，以及项目记忆 `git-commit-takes-the-whole-index`（本次已把这一节补进去）。
