# 收尾报告：计数请求日志行的可读性修复

日期：2026-08-20
会话 transcript：`~/.claude/projects/-home-xp-src-ghc-api-proxy-py/23a78bec-3ecd-45d0-b2eb-5b4a5f43ba48.jsonl`
状态：**草稿，未经独立评审**（评审通过后本行改为终态）

## 起因与结论

用户报告一条读不出来的日志：

```
[ OK ] 17:08:01 H1 200 anthropic-messages/claude-opus-5 1.2s ↑19.7k
```

它是一次 `POST /v1/messages/count_tokens`，200 诚实。`↑19.7k` 是词元（字节必带 `B`/`KB`/`MB`）；没有 `↓`、没有字节、只有一条腿，是因为 count 分支在 delivery 路径之前 return，那些字段只在 delivery 路径上填。缺陷不是这些缺席本身，而是**缺席读不出来**——成功行把 `METHOD /path` 折叠成 `<inbound-format>/<model>`，而计数与真实对话共用同一个 inbound format。

## 交付

主仓 `~/src/ghc-api-proxy-py`，均已提交到 `main`（**未推送**）：

| 提交 | 内容 |
|---|---|
| `d3335b6` | feat: 计数行说出是谁应答的（`counter` 字段、`format_counter`、上游腿双向字节） |
| `9e3d374` | fix: 估算说明为什么（`counter_reason`，判定在 `handle_count_tokens`） |
| `40681ce` | refactor: `count(...)` → `provider(...)`，括号改为按发生顺序的轨迹 |
| `86f4a46` | docs: 评审报告与逐条处置 |
| `fa1df74`、`bd2fb81` | docs: 改名后残留旧名字的两处 docstring |

`.dev` 独立仓：`4d029eb` docs，同步 `docs/tui/spec.md`「一次计数请求怎么读」与着色表、`docs/tui/deferred.md` 第 4 条。**未推送**（该仓 origin 指向公开仓）。

`handler.py` 里属于本切片的部分（`count_tokens_bytes_out`、`count_tokens_reason` 判定）在我提交之前已被同伴的 `064ba63` 整文件裹走，因此不在上表。

渲染结果（五种形态）：

| 行 | 含义 |
|---|---|
| `H1/H1 … ↑2.5KB ↓25B ↑19.7k provider(ghc)` | 问了上游，上游答了 |
| `H1/H1 … ↑2.5KB ↓25B ↑19.7k provider(ghc-failed,local)` | 问了，回了响应但答案不可用 |
| `H1 … ↑19.7k provider(ghc-failed,local)` | 问了，连响应都没给 |
| `H1 … ↑19.7k provider(no-counter,local)` | 这条路由没有上游计数器，从没问过 |
| `H1 … ↑19.7k provider(local)` | 运维配成只估算 |

`provider(no-counter,local)` 是用户未给例子的第四档，由我按同一模式补齐，已在会话中说明可改。

## 验证

**先说明一次证据作废与重做。** 收尾初稿里的基线对比来自两棵临时 worktree，其中一棵是用 `HEAD~2` 建的——而共享树的 HEAD 在那期间被同伴推进了，于是它落在了与另一棵**相同的提交**上，两次「不同点位」实为同一点位测两遍。该证据已作废。下表是 2026-08-20 收尾时用**显式 SHA** 重建四棵 worktree 重跑的结果，并且比的是**失败测试的集合**（`comm` 双向差分）而不只是计数。

| 点位 | 提交 | 结果 | 相对上一行 |
|---|---|---|---|
| 基线 | `6ef4b03`（`d3335b6` 的父） | 44 failed / 1184 passed / 1 skipped | —— |
| 我的两个功能提交 | `9e3d374` | 44 failed / 1190 passed / 1 skipped | **集合双向差分为空**：同一批 44 条，零新增失败 |
| 同伴点位 | `f76f395` | 75 failed / 1180 passed / 1 skipped | 基线 44 条中 43 条仍在、1 条被修，另新增 32 条 |
| 我的改名提交 | `40681ce` | 75 failed / 1180 passed / 1 skipped | **集合双向差分为空**：零新增失败 |
| 当前 main | `fa1df74` | 1257 passed / 0 failed / 1 skipped | 前述失败均已被同伴的提交修掉 |

命令：`git worktree add --detach <wt> <sha>`，`cd <wt> && PYTHONPATH=<wt>/src .venv/bin/python -m pytest tests/unit tests/http -q --tb=no --color=no`。四棵临时 worktree 已逐条路径 `git worktree remove`。

那 32 条新增失败是 `RequestLine.__init__() got an unexpected keyword argument 'count_tokens'` 一族，由同伴的半提交造成（见下节），不是我的改名——`f76f395` 与 `40681ce` 的失败集合完全相同即为证。

**初稿写的「已由其 `783f023` 修复」是推断，且已被证伪**：`40681ce` 排在 `783f023` 之后，那 44 条里仍有 43 条在失败。事实核查评审进一步实测出完整答案（非我的观测，采信其证据）：`783f023` 修掉的是**成因**（超时 driver 的报错消失），但同一批测试立刻被 `count_tokens` 那条裂缝接住，直到 `b97930b` 才真正转绿。**两拍，`ea0417c` + `b97930b` 缺一不可。**

其余验证：

| 项 | 结果 | 新产出/复用 | 锚点 |
|---|---|---|---|
| Ruff | All checks passed | 新产出 | `uv run ruff check src tests` |
| Pyright | 0 errors | 新产出 | `uv run pyright src/app/observability/request_log.py src/app/server/pipeline_app.py src/app/server/handler.py` |
| 共享树全量 | 1272 passed | 新产出，**但不可复现** | `uv run pytest tests/unit tests/http -q`。共享树是移动靶：核查评审当时跑同一命令得 1277。这一行只说明当时那棵树的状态，**依据仅为作者自述** |
| 活文档旧写法残留 | `src`/`tests`/`.dev/docs` 零命中 | 新产出（**重做过**，见下） | `rg -n --fixed-strings -e 'count(ghc' -e 'count(local' -- src tests .dev/docs docs`，另有正样本对照 `provider(ghc` 命中 5 个文件 |

**不含** `tests/tui`（项目约定默认排除）与冒烟测试，所以「零新增失败」只在这两个目录的范围内成立。未跑 `ruff format`（项目禁止）。

**第二次证据作废与重做**：收尾初稿声称「活文档无残留」时，连续两条扫描命令都是坏的——第一条的反引号触发了 shell 命令替换，第二条 `-F` 不带参数使 pattern 落到路径位而报 `No such file or directory`——而我在同一行硬编码了 `echo "(空=无残留)"`，两次都照印了结论。第三次用 `--fixed-strings -e … --` 并加正样本对照后，结论恰好不变，但**先前那两次没有任何证据力**。

## 分支与工作树

全程在共享主树 `main` 上工作，无特性分支。为验证提交内容另建两棵临时 worktree（`verify-wt`、`verify-base`），确认 `git status` 干净后已 `git worktree remove`，其 HEAD 均可从 `main` 到达。剩余 worktree（`826d4cda/tmp/review`、`.claude/worktrees/delivery-keepalive`）不属本会话。

主树仍有同伴的未提交改动（`.gitignore`、`refs/.gitignore`、`bundled-config.yaml` 等）与大量未跟踪文件，**原样保留，未触碰**。

## 临时状态

`$CLAUDE_JOB_DIR/tmp` 清点时 **20** 个文件（`find` 与 `fd -H -I` 两法一致），写入处置记录后为 **21**。**未删除任何文件**，全部就地处置，处置记录落在 `/home/xp/.claude/jobs/23a78bec/tmp/DISPOSITION.md`，目录留给 harness 过期。16 个是被提交进 git 的内容副本（载体＝提交本身，`git show <sha>:<path>` 可取回），4 个是构造索引的一次性脚本（载体＝记忆条目与评审报告第七节），1 个是处置记录本身。非文件线索的载体见该记录。

## 提交手法（共享树）

主树同时有同伴在改同一批文件，所以 `git add <file>` 会裹走其在途改动，`git commit -- <path>` 取的又是工作区内容——两者都不能用。改为**从 HEAD 构造索引内容**（记忆 `git-commit-takes-the-whole-index` 末尾称之为「共享索引变体」；更严格的做法是同文件里的私有索引方案，本次没用）：

```python
text = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], ...).stdout   # 起点是 HEAD，不是工作树
for old, new in edits:
    assert text.count(old) == 1, f"anchor not unique: {old[:70]!r} -> {text.count(old)}"   # ← 关键
    text = text.replace(old, new)
sha = subprocess.run(["git", "-C", REPO, "hash-object", "-w", blob_path], ...).stdout.strip()
subprocess.run(["git", "-C", REPO, "update-index", "--cacheinfo", f"100644,{sha},{path}"])
```

**那句 `assert text.count(old) == 1` 是整段里唯一非平凡的东西**：锚点在 HEAD 版本里必须恰好出现一次。出现 0 次说明该锚点其实是同伴改出来的（我在照抄工作树而不是 HEAD），出现 2 次说明替换会波及我没看过的位置。没有它，脚本会静默产出一个「差不多对」的 blob，而它随后被当成提交内容。提交前另核对 `git diff --cached --name-only` 与同伴标志性改动的 grep。

**这一步动的是共享索引**，所以它比记忆里的私有索引方案弱：中间窗口里同伴的暂存会被卷入。当时该用私有索引。

**这里有一个我自己的过程错误**：为清空索引跑了三次裸 `git reset`，会连同伴已暂存的条目一起抹掉。当次未造成损失（同伴恰好随后提交），但那是侥幸。记忆 `git-commit-takes-the-whole-index` 里本来就有更好的做法（私有索引 `GIT_INDEX_FILE`），我没有取用；已把这个写法补进那条记忆的「绝不做」清单。

## 期间 main 曾经红过

观察到 75 failed，原因是 `request_log.py` 的 `count_tokens` 字段与 `format_completion_line(status=)` 参数还在同伴工作区未提交，而引用它们的 `pipeline_app.py` 与测试已被提交。由同伴的 `ea0417c`、`b97930b` 补齐后恢复。**我的提交让这个分裂更容易发生**——我三次把该文件的已提交内容更新为「HEAD + 只有我的」，看起来像该文件已经跟上了。

## 两条查错手法（从 job 目录搬进来的，那里会过期）

**差分定位时，看错误信息不要只看计数。** 在隔离 worktree 里补上疑似缺失的字段后重跑，失败计数纹丝不动（75 → 75），但错误信息位移了：`RequestLine.__init__() got an unexpected keyword argument 'count_tokens'` 变成 `format_completion_line() got an unexpected keyword argument 'status'`。只盯计数会读成「没修对」，位移才说明「修对了一个，后面还排着第二个」。同一批测试被两条裂缝先后接住时，计数是没有分辨力的。

**判断同伴此刻是否在树里**：`ls -l --time-style=+%H:%M:%S <文件>` 与 `date` 对表。本次实测某测试文件 15 秒前刚被改过，据此决定不用 `git add <file>`。**它不能证明同伴不在**——文件静止只说明这一刻没有写盘。

## 可复用资产建议

**已实施**（都是更新既有条目，没有新建同义资产）：

| 资产 | 类型 | 触发 | 补的是什么缺口 |
|---|---|---|---|
| `absence-is-not-readable-on-a-log-line`（记忆，更新） | project | 往请求行加字段时 | 补一条：**修好一层往往在上一层重演**。补上「谁给的数」之后，`local` 一个词又同时代表正常配置与事故——失败没有缺席，它穿着正常情形的衣服。比原来那三条更难发现，因为它有输出 |
| `never-echo-the-conclusion-beside-the-command`（记忆，**新建**） | feedback | 写「我核对过、没问题」这类断言时 | 命令旁硬编码结论，命令坏了照印。本次连续两次拿到「无残留」而两次命令都是坏的。与既有的 rg 用法条目不重叠——那些讲选项误用，这条讲**判据的载体被挪出了被测命令** |
| `git-commit-takes-the-whole-index`（记忆，更新） | project | 共享主树上提交时 | 头号建议「提交一律带 pathspec」加了适用条件（文件里混着同伴改动时它会失效）；「绝不做」清单补上**不带 pathspec 的 `git reset`** |

**建议但未实施**：无。本次没有发现需要新建 skill / rule / agent 的缺口——共享树提交纪律已有 `git-preference:coordinating-a-shared-git-worktree`，收尾流程已有 `closing-a-development-session`，两者都覆盖到了，再造一个只会是同义词。

## 待裁决/未做

- `provider(ghc-failed,local)` 说不出是超时还是 500，细粒度原因仍只在 `count_tokens_attempts` 里且无读者。见 `.dev/docs/tui/deferred.md` 第 4 条。
