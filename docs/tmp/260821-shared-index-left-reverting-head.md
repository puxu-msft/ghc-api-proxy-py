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

## 备份 ref 已删除

`refs/backup/index-snapshot-260821`（`91f67a1`）已于同日删除。删除依据：修复后索引与 HEAD 差异归零、本次的 6 个提交全部仍是 HEAD 祖先、`loading.py` / `providers.py` / `test_cli.py` 在其后零次被改动，且干净检出的 HEAD 全量通过（`8469cfa`，1660 passed / 3 skipped / 0 failed）。保留它反而有害——它的 tree 是一份与 `2bcf03b` 相差 51 个文件的过期索引快照，任何人 `read-tree` 它都会把工作区拖回一个早已作废的状态。

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

也要注意**只有真拉起进程的测试能抓到它**：本次 1658 条里只有 `tests/systemd/test_systemd_pipeline_unit.py` 那条 `subprocess` 测试变红，其余在进程内构造依赖的测试全绿。

## 两处归因失误，一并记下

- 一开始把这些暂存条目误读成「同伴暂存了一个奇怪的旧版本」并写进了汇报。归因错了一轮，直到用户指出。**看到共享索引里有解释不了的东西，先问「是不是我自己刚才的操作造成的」。**
- 判断某条被刷掉的暂存内容要不要紧时，只扫了最近 25 个提交就把 `composition.py` 判成「索引独有」；扫到 40 个才发现它与 `f025e3c` 逐字节相同，根本不是谁的独有快照。**「在历史里找不到」是搜索深度的函数，不是事实**，用它下结论前先把深度说出来。

同类纪律的完整版在 skill `git-preference:coordinating-a-shared-git-worktree`，以及项目记忆 `git-commit-takes-the-whole-index`（本次已把这一节补进去）。
