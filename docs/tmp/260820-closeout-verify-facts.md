# 事实核查：计数请求日志行收尾产物

日期：2026-08-20
核查者：事实核查评审 subagent（只读）
核查对象：

1. `docs/tmp/260820-closeout-count-tokens-log-line.md`（终态报告草稿，主产物）
2. `/home/xp/.claude/jobs/23a78bec/tmp/DISPOSITION.md`
3. `~/.claude/projects/-home-xp-src-ghc-api-proxy-py/memory/git-commit-takes-the-whole-index.md`
4. `docs/tmp/260820-review-count-tokens-log-line.md` 第七节

核查基准：主工作树 `/home/xp/src/ghc-api-proxy-py`，`main` 在核查开始时为 `bbbcb37`（工作区有同伴的在途改动，见 §0）。

严重度口径：blocker = 会让读者据以做出错误动作；major = 事实错或口径不一致，需改；minor = 措辞不精确或易误读；仅记录 = 无需改，只是核查留痕。

---

## 0. 核查环境（影响后面每一条的锚点）

- `main` HEAD 在核查开始时 = `bbbcb37 docs: say what this module has actually been seen doing, which is nothing`（`git log --oneline -1`）。**比报告所写的 `fa1df74`／`bd2fb81` 更新**，中间还夹着同伴的 `42738c9 feat: cap how many concurrent requests share one upstream connection`。
- 工作区有同伴大量未提交改动（`src/app/ghc_client/transport.py`、`src/app/pipeline/retry.py`、`src/app/server/handler.py`、`src/app/config/schema.py` 等 12 个 `M` 文件与大量未跟踪文件）。因此**任何在共享树里跑的测试都不能归因给报告里的提交**；下文凡是需要归因的，都在 `/tmp` 下的一次性 worktree 里跑。

---

## 1. 提交 SHA 核对

命令：`git cat-file -e <sha>^{commit}`、`git merge-base --is-ancestor <sha> main`、`git show --stat`。

| SHA | 存在 | 在 `main` 历史 | 报告描述 | 核查结论 |
|---|---|---|---|---|
| `d3335b6` | 是 | 是 | feat: 计数行说出是谁应答的（`counter` 字段、`format_counter`、上游腿双向字节） | **属实**。`git show d3335b6 -- src/app/observability/request_log.py` 有 `+    counter: str = ""` 与 `+def format_counter(counter: str, *, color: bool = False)`；stat 为 request_log.py / pipeline_app.py / 三个测试文件，137 insertions |
| `9e3d374` | 是 | 是 | fix: `counter_reason`，判定在 `handle_count_tokens` | **属实**。`+    counter_reason: str = ""`、`format_counter(counter, reason="")` 签名扩展；"判定在 handle_count_tokens" 是对代码位置的描述而非对本提交内容的描述（该判定字节在 `064ba63` 里，见 §2），报告自己下一段也这么说，不矛盾 |
| `40681ce` | 是 | 是 | refactor: `count(...)` → `provider(...)`，括号改为按发生顺序的轨迹 | **属实**。diff 有 `-def format_counter` / `+def format_count_provider`、`-    counter: str` / `+    count_provider: str`、`-    named = f"{counter}:{reason}"` / `+    trail = f"{reason},{provider}"`（轨迹顺序＝先试过的、后应答的） |
| `86f4a46` | 是 | 是 | docs: 评审报告与逐条处置 | **属实**。单文件 `docs/tmp/260820-review-count-tokens-log-line.md`，+205 行，与该文件当前 205 行一致 |
| `fa1df74` | 是 | 是 | docs: 改名后残留旧名字的 docstring | **属实**。`request_log.py` 2 处改动，触及 `format_count_provider` 的 docstring |
| `bd2fb81` | 是 | 是 | 同上 | **属实**。`tests/unit/test_request_log.py` 1 行 docstring |
| `4d029eb`（`.dev` 仓） | 是 | 是（`dotdev` 分支 HEAD） | docs，同步 `docs/tui/spec.md` 与 `deferred.md` 第 4 条 | **属实**。`git -C .dev show --stat 4d029eb`：`docs/tui/deferred.md +12`、`docs/tui/spec.md +37/-1`；spec 新增标题确为 `### 一次计数请求怎么读`，着色表新增 `| **计数提供方** | ...`；deferred 新增 `## 4. 计数行说不出上游是怎么失败的` |

**「未推送」核查：属实。** `git branch -r --contains <sha>` 对六个提交均为空；`main@{u}` = `origin/main` = `e82e9a5`，远在这批之前。`.dev` 仓的 `dotdev` 分支**根本没有 upstream**（`fatal: no upstream configured`），origin 指向 `puxu-msft/ghc-api-proxy-py.git`，与报告所述一致。

**严重度：无发现**（7/7 属实）。

### 1a. minor：命名在表格里是中途态，读者可能当成终态

`d3335b6` 行写的 `counter` 字段、`format_counter`，在同一切片的 `40681ce` 里已全部改名为 `count_provider` / `format_count_provider`。表格本身没错（它描述的是各提交当时做了什么），但下方「五种渲染形态」全用 `provider(...)`，读者若只扫表格会以为仓库里现在有 `format_counter`。实测当前 `main` 上 `format_counter` 已不存在。**minor**，建议在 `d3335b6` 行加半句「后被 `40681ce` 改名」。

---

## 2. `handler.py` 那部分是否被 `064ba63` 裹走

**属实。** 证据：

```
git show 064ba63 -- src/app/server/handler.py | rg '^[+-].*(count_tokens_bytes_out|count_tokens_reason)'
+            context.extras["count_tokens_bytes_out"] = len(response.content)
+            context.extras["count_tokens_reason"] = "no-counter"
+            context.extras["count_tokens_reason"] = "ghc-failed"
```

`git log -S` 交叉确认引入顺序：

- `count_tokens_bytes_out`：`064ba63`（首次）→ `d3335b6`
- `count_tokens_reason`：`064ba63`（首次）→ `9e3d374`

`064ba63` 的提交时间 08-20 17:51，早于 `d3335b6` 的 18:07，且其 subject 是同伴的 `fix: refuse a search this endpoint cannot run...`（12 个文件，含 hosted_web_search / server_tools）。三项事实互相印证：这两个 key 确实是随同伴的整文件提交先落地的。

**严重度：无发现。**

---

## 3. 五种渲染形态：实际渲染过一遍

**方法**：为避免共享树里同伴的在途改动污染归因，用 `git archive main | tar -x -C /tmp/verify-facts-260820/main` 取出干净副本（`git worktree add` 会写共享 `.git`，故不用）。先确认 `git diff main -- src/app/observability/request_log.py` 为空，即**工作区与 `main` 在该文件上完全一致**，所以这次渲染同时代表两者。

**我验的是 `main` 的哪一个：`8a36fe3`。** 注意报告写的锚点是 `fa1df74`；核查期间 `main` 从 `bbbcb37` 又前进到 `8a36fe3`（同伴在活跃提交）。这中间同伴的 `b97930b` 给 `format_completion_line` 加了必填 keyword-only 参数 `status: LogStatus`，所以复现脚本必须传 `status="ok"`。

渲染脚本 `/tmp/verify-facts-260820/render2.py`，命令 `PYTHONPATH=/tmp/verify-facts-260820/main/src /home/xp/src/ghc-api-proxy-py/.venv/bin/python render2.py`。字段映射先按代码核实：`bytes_in = len(response.request.content)`（发往上游）由 `↑` 渲染，`bytes_out = len(response.content)`（收自上游）由 `↓` 渲染（`request_log.py:345-346`）；`client_protocol` 存的是 `http_label()` 已缩写的 `H1`。

实测输出（`…` 处为 `200 anthropic-messages-count-tokens/claude-opus-5 1.2s`）：

```
H1/H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑2.5KB ↓25B ↑19.7k provider(ghc)
H1/H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑2.5KB ↓25B ↑19.7k provider(ghc-failed,local)
H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑19.7k provider(ghc-failed,local)
H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑19.7k provider(no-counter,local)
H1 200 anthropic-messages-count-tokens/claude-opus-5 1.2s ↑19.7k provider(local)
```

**五条逐字符与报告表格一致。严重度：无发现。**

可达性也已顺代码核对（`src/app/server/handler.py:180-232`）：第 4 档 `no-counter` 由 `f"ghc:{absent_reason}" in trail` 判定，第 5 档裸 `provider(local)` 由「运维把 `ghc` 排除或把 `local` 排在前面」落到 `result.provider != "ghc"` 且两个分支都不命中而产生。报告说第 4 档「由我按同一模式补齐」，代码里它有独立判据、不是猜的，**属实**。

### 3a. 仅记录：还有第六种形态，表格没列

`ask_upstream` 在 `response.raise_for_status()` **之前**写 `count_tokens_bytes_in`，在 `response.json()` **之后**才写 `count_tokens_bytes_out`（`handler.py:185`、`190`）。所以「上游 200 但 body 不是 JSON」会产生只有 `↑` 没有 `↓` 的第六种形态 `H1/H1 … ↑2.5KB ↑19.7k provider(ghc-failed,local)`。代码注释本身就预期了这种单向腿（"a leg reported in one direction only says, by this line's convention, that nothing came back"）。

不算错：非 2xx 由 `send_anthropic_count_tokens` → `_in_pipeline_terms` 先行抛出，`raise_for_status()` 这条是防御性的，所以第六形态在实践中极难触发，且报告没有用「全部」「穷举」这类词。但「五种形态」读起来像穷举。**仅记录**，若要更严谨可加一句「按可达性列举，非穷举」。

---

## 4. 验证表的五个数字

复现方法统一为：`git archive <sha> | tar -x -C /tmp/verify-facts-260820/c-<sha>`，然后 `PYTHONPATH=<dir>/src /home/xp/src/ghc-api-proxy-py/.venv/bin/python -m pytest tests/unit tests/http -q --no-header --color=no -p no:cacheprovider`。全部**不碰共享树**。

| 报告的数字 | 我的复现 | 结论 |
|---|---|---|
| `fa1df74` 隔离 worktree = **1257 passed / 0 failed** | `1257 passed, 1 skipped in 73.73s` | **完全复现** |
| 基线 `6ef4b03` = **44 failed / 1184 passed** | `44 failed, 1184 passed, 1 skipped in 53.90s` | **完全复现** |
| `9e3d374` = **44 failed / 1190 passed** | `44 failed, 1190 passed, 1 skipped in 51.97s` | **完全复现** |
| 「同样的 44 条」 | 两次跑各导出 FAILED 列表排序后 `diff` → 完全相同，44/44，全部落在 `tests/http/test_pipeline_app.py` | **完全复现，且比报告写得更硬**（报告只说数量与「同样的」，我做了集合逐条比对） |
| 共享树全量 = **1272 passed** | **未复现**。共享树是移动靶：核查期间 `main` 从 `bbbcb37` → `8a36fe3` → `7debb39`，同伴仍在提交，工作区未跟踪/未提交改动也在变。我此刻跑同一命令得 `1277 passed`（0 skipped）。量级一致，但 1272 这个具体数字**依据仅为作者自述** | 无法核实，非缺陷 |

**注**：报告写「1257 passed / 0 failed」，实测还有 `1 skipped`。`0 failed` 属实，跳过那 1 条未提及。**仅记录**（不影响任何结论）。另注：隔离副本一律 `1 skipped`，共享树 `0 skipped`，差异来自 `git archive` 不带的未跟踪文件，不影响本报告任何判断。

### 4a. major：「那 44 条已由其 `783f023` 修复」这句话不成立（修的是成因，不是让那些测试变绿）

报告 §验证 与 `DISPOSITION.md` 第 29 行都写：「那 44 条属同伴当时在途的超时改动，**已由其 `783f023` 修复**」。

我实测 `783f023`（其父提交正是 `9e3d374`）：

```
75 failed, 1170 passed, 1 skipped
```

集合比对：44 条里 **43 条在 `783f023` 上仍然失败**，只有 1 条转绿，同时新增 32 条失败。

不过成因归属是对的。9e3d374 上那 44 条的报错是 `AnthropicMessagesDriver.__init__() got an unexpected keyword argument …` 与 `DID NOT RAISE StreamIdleTimeoutError`——确属同伴在途的超时改动（测试已提交、driver 定义未提交）。到 `783f023` 这个成因**消失了**：那 75 条的报错**全部**是同一句 `RequestLine.__init__() got an unexpected keyword argument 'count_tokens'`，即另一条裂缝。

所以准确的说法是：**`783f023` 补齐了超时那条裂缝，但同一批测试立刻被 `count_tokens` 那条裂缝接着按住。** 现在的写法会让读者以为 `783f023` 之后那批测试就绿了，而实际上那正是全程最红的一刻。

**严重度：major**（事实陈述与可复现观测不符，两份文档都写了）。**注意：本条不动摇「零新失败」这个结论**——那条结论靠的是 `6ef4b03` 与 `9e3d374` 的 44 条集合完全相同，我已独立复现。

建议改成：「那 44 条属同伴当时在途的超时改动；`783f023` 补齐了这条裂缝（其后该成因不再出现），但同一批测试随即被下一条裂缝按住，直到 `b97930b` 才真正转绿。」

### 4b. Ruff 与 Pyright：未复现，理由是口径

报告写 `uv run ruff check src tests` = All checks passed、`uv run pyright <三个文件>` = 0 errors。这两条在共享树上跑，而共享树此刻已含同伴的大量新改动，**跑出来的结果无论绿红都不能归因给报告里的提交**。要复现只能在 `fa1df74` 的隔离副本上跑，而 `uv run` 会解析当前项目的锁文件与 venv，隔离副本上的等价命令与报告所写的不是同一条。判断复跑代价与收益不成比例（这两项即使红了也不改变任何结论），故**未复现，依据仅为作者自述**。

---

## 5. 「零新失败」的措辞边界

**结论：结论被证据支持，且边界已经写出来了。**

- 「零新失败」的证据是基线对比，我已完全复现，并把它加强到集合逐条相同。
- 报告 §验证 明写「**不含** `tests/tui`（项目约定默认排除）与冒烟测试」。`DISPOSITION.md` 第 33 行也单列「**这些探针不能证明什么**」并点名同样两项。**没有漏说。**
- 用词也没有越界：写的是「相对基线零新失败」而不是「零失败」，而基线上就有 44 条红的，读者不会误读成全绿。

**严重度：无发现。** 这一节的写法（把「不能证明什么」单独成段）是本次几份产物里最扎实的部分。

---

## 6. 「main 曾经红过 75 failed」——完全可验证，且比报告写得还准

报告 §「期间 main 曾经红过」：「观察到 75 failed，原因是 `request_log.py` 的 `count_tokens` 字段与 `format_completion_line(status=)` 参数还在同伴工作区未提交，而引用它们的 `pipeline_app.py` 与测试已被提交。由同伴的 `ea0417c`、`b97930b` 补齐后恢复。」

逐点实测（隔离副本，`tests/unit tests/http`）：

| 提交 | 时间 | 结果 | 唯一报错 |
|---|---|---|---|
| `783f023` | 18:09 | **75 failed**, 1170 passed | 75× `RequestLine.__init__() got an unexpected keyword argument 'count_tokens'` |
| `ea0417c` | 18:22 | **75 failed**, 1180 passed | 75× `format_completion_line() got an unexpected keyword argument 'status'`（在 `pipeline_app.py:208`） |
| `b97930b` | 18:23 | **1257 passed, 0 failed** | —— |

- 数字 **75 完全复现**，而且在两个提交上都是 75。
- 两个缺失符号 `count_tokens` 与 `status=` **正是报告点名的那两个**，且报错把它们分成了先后两拍。
- 「由 `ea0417c`、`b97930b` 补齐后恢复」**精确成立**：只补 `ea0417c` 仍是 75 红，必须两个都到位才转绿。报告并列这两个 SHA 是对的。

**严重度：无发现。** 这是本次核查里最强的一条：一个纯口述的历史观测，在两个提交上分别复现出同一个数字和点名的两个符号。

顺带：这也解释了评审报告 §七写的 **1244 passed**——那是在**共享工作树**里跑的，工作区里同伴的 `request_log.py` 已经有 `count_tokens` 与 `status=`，只是没提交。所以「工作树绿、HEAD 红」同时成立，与报告描述的机制自洽。1244 这个具体数字随工作树漂移，**未复现，依据仅为作者自述**。

---

## 7. 临时目录清点：数字口径错了，而且分类数也错了

### 7a. major：清点数 20 是「写入 DISPOSITION.md 之前」的，但分类表把 DISPOSITION.md 算进了这 20

`DISPOSITION.md` 第 10 行：「`find <root> \( -type f -o -type l \) | wc -l` = **20**；`fd -H -I --type f --type l | wc -l` = **20**（两法一致）。清点与本记录写入之间无新增文件（写入前已重列）。」

第 14-18 行的分类表却是 `15 + 4 + 1（本记录）= 20`——把本记录算进了那个 20。

实测（当前，`/home/xp/.claude/jobs/23a78bec/tmp`）：

```
find . \( -type f -o -type l \) | wc -l                     → 21
fd -H -I --type f --type l | wc -l                          → 21
find . \( -type f -o -type l \) ! -name DISPOSITION.md      → 20
```

所以 **20 是写入前的数，写入后是 21**。「清点与本记录写入之间无新增文件」这句在字面上讲得通（没有别的文件新增），但它正好绕开了唯一真正新增的那个文件——本记录自己。分类表随后又把本记录塞回 20 里，两个口径打架。**严重度：major**（一份账目文档的核心数字自相矛盾）。

正确写法：清点 **20**（不含本记录），写入本记录后为 **21**。

### 7b. major：内容副本是 16 个，不是 15 个

实测分类：

| 类 | 实际个数 | 文件 |
|---|---|---|
| stage A 内容副本（无前缀） | 5 | `request_log.py`、`pipeline_app.py`、`test_request_log.py`、`test_request_log_file.py`、`test_pipeline_app.py` |
| stage B 内容副本（`b-`） | 5 | 同上五个文件的 `b-` 版 |
| stage C 内容副本（`c-`） | **6** | 同上五个 + **`c-handler.py`** |
| 构造索引的脚本 | 4 | `stage_a.py`、`stage_a_tests.py`、`stage_b.py`、`stage_c.py` |
| 本记录 | 1 | `DISPOSITION.md` |

**内容副本合计 16**，不是 15。多出来的正是 `c-handler.py`——`40681ce` 那一步比前两步多改了 `handler.py`。`DISPOSITION.md` 的「文件」列写的是 `…、b-*、c-*` 通配，**枚举是对的，只有数字错了**；但 `16 + 4 = 20` 才是那个 20 的正确拆分，恰好也证明本记录不该算在里面。

收尾报告 §临时状态 有**同一处错误**：「15 个是被提交进 git 的内容副本…4 个是构造索引的一次性脚本」——15+4=19，与它自己写的 20 对不上，第 20 个从未交代。

**严重度：major**（两份文档同错；这正是「清点前/后口径不一致」那一类）。

### 7c. 载体核查：16 个内容副本**全部**可用 `git show <sha>:<path>` 原样取回

不是抽查，是 16/16 逐个 `git hash-object` 比对（bare→`d3335b6`，`b-`→`9e3d374`，`c-`→`40681ce`）：

```
OK  pipeline_app.py           == d3335b6:src/app/server/pipeline_app.py
OK  request_log.py            == d3335b6:src/app/observability/request_log.py
OK  test_pipeline_app.py      == d3335b6:tests/http/test_pipeline_app.py
OK  test_request_log.py       == d3335b6:tests/unit/test_request_log.py
OK  test_request_log_file.py  == d3335b6:tests/unit/test_request_log_file.py
OK  b-{同五个}                == 9e3d374:{对应路径}
OK  c-{同五个} + c-handler.py == 40681ce:{对应路径}
```

**16 个全部 blob hash 完全相同。** 载体主张**成立**，且比记录写的还多覆盖一个。`c-handler.py` 值得单独说：它的内容能从 `40681ce` 取回，尽管 `handler.py` 里那些 extras 的**首次**落地在同伴的 `064ba63`——`40681ce` 又改了它 4 行，所以这份副本有自己的归宿，不落空。**严重度：无发现。**

### 7d. minor：4 个脚本的「做法」载体，指错了段落，且漏了唯一真正非平凡的一条

`DISPOSITION.md` 第 17 行称脚本的载体是「记忆 `git-commit-takes-the-whole-index`（**私有索引写法**）与 `docs/tmp/260820-review-count-tokens-log-line.md` 第七节」。

读完 4 个脚本，它们实际的做法是：

1. `git show HEAD:<path>` 取基文本；
2. `sub()` 做文本替换，**每次替换前断言锚点唯一**：`assert text.count(old) == 1, f"anchor not unique: ..."`；
3. 写 blob 文件到 tmp，`git hash-object -w`；
4. `git update-index --cacheinfo "100644,<sha>,<path>"`——**写的是共享索引**，全程没有 `GIT_INDEX_FILE`。

两个问题：

- **指错段落。** 脚本走的是记忆里的「**共享索引变体**」那段（当前第 85 行），不是「私有索引写法」（第 30-64 行）。记忆自己第 28 行就写着私有索引写法「是当时就该用的」，即当时**没有**用；`DISPOSITION.md` 第 31 行也承认用的是共享索引。所以第 17 行的括注与同一文档第 31 行互相打架。按第 17 行去重建，会建出一套不同的（且更好的）流程，而不是脚本干过的事。
- **漏了锚点唯一性断言。** `assert text.count(old) == 1` 是这 4 个脚本里唯一非平凡、真正防坑的工程细节（一次文本替换若锚点不唯一，就会静默改到别处）。三份候选载体我都 grep 过：记忆、评审 §七、收尾报告 §提交手法，**都没有**。记忆第 61 行的「索引路径必须每次唯一」讲的是索引**文件路径**，不是替换锚点，别看串。

「有价值的是做法不是脚本」这个处置理由本身我认同；但按 `DISPOSITION.md` 现在写的载体，重建不出脚本的做法。**严重度：minor**（脚本是一次性的，重建需求本就弱；但这是账目文档的自我打架）。

修法：把括注改成「共享索引变体」，并在收尾报告 §提交手法那串流程里补一句「每处替换前断言锚点在全文唯一」。

### 7e. 其余载体逐条打开看过，全部属实

| `DISPOSITION.md` 声称的载体 | 核查 |
|---|---|
| 测试 `test_a_count_upstream_answered_uselessly_keeps_the_leg_it_flew` | **存在**，`tests/http/test_pipeline_app.py:1422`；实跑通过 |
| `handler.py` 判定处注释（`providers` 可裁剪/改序会撒谎） | **存在**，`src/app/server/handler.py:279`，原文即「the operator can also leave `ghc` out of `providers`, or order `local` ahead of it」 |
| `.dev/docs/tui/spec.md` 记了被否决的 `ghc→local` 箭头写法 | **存在**，`spec.md:98`，原文「用户选择把原因写进括号，而不是 `ghc→local` 那种箭头写法」 |
| `.dev/docs/tui/deferred.md` 第 4 条 | **存在**，`## 4. 计数行说不出上游是怎么失败的`，且其引用的 `docs/tmp/260820-review-count-tokens-shared-pipeline.md` 也在（15439 字节） |
| 评审报告第七节 F6 行 | **存在**，`260820-review-count-tokens-log-line.md:190` |
| 记忆已补上裸 `git reset` 的写法 | **存在**，记忆第 26、28 行 |
| 两棵临时 worktree 已移除 | **属实**。`git worktree list` 只剩主树、`826d4cda/tmp/review`、`.claude/worktrees/delivery-keepalive`——与收尾报告 §分支与工作树 所列**完全一致** |

**严重度：无发现。**

---

## 8. 记忆条目 `git-commit-takes-the-whole-index` 里新加的那段

**先说一件核查期间发生的事**：这个文件在我核查过程中被改过。我第一次读时 `modified: 2026-08-20T18:35:03.800Z`，再读时是 `2026-08-20T19:06:36.072Z`，私有索引那段被大幅重写（加了 `mktemp` 独占索引、CAS 写进控制流、末步对齐带条件、mode 从索引读，以及四条实测失效）。下面的判断针对 **19:06 版**。

### 8a. 重复？——不算，且它自己交代了为什么另起一段

第 26 行的「绝不做」清单里已有「**不带 pathspec 的 `git reset`**」，第 28 行整段又展开讲它。这不是冗余复述：第 28 行加了新事实（当天三次、当次未损失是侥幸）并且**自己写明了另起一段的理由**——「写在这里是因为「先清空索引」这个动机看着无害，而正是它把人引回共享索引上」。清单负责「别做」，段落负责「为什么你会想做」。**判定：合理复述，不是重复。严重度：无发现。**

### 8b. minor：第 28 行的「根本不碰共享索引」现在与第 30 行矛盾（由后来的改写造成，非原作者之误）

- 第 28 行：「本条已有的私有索引写法（下面那段）**根本不碰共享索引**」
- 第 30 行（19:06 版）：「用私有索引：从建 blob 到落 commit 全程不读也不锁共享索引，**只有最后一步对齐会写，且带条件**」
- 第 53 行代码确实有一句写共享索引的 `git update-index --cacheinfo`

在 18:35 版里那段写的是「全程不碰共享索引与工作树」，与第 28 行是自洽的；19:06 的改写把那句收窄成了准确的说法，却**没有回头改第 28 行**。于是现在一个绝对句和一个带条件句并存。

这条正是「绝对化措辞缺少边界」的形态，只是责任在后一次编辑。**严重度：minor**，改法：第 28 行的「根本不碰共享索引」改成「除末步的条件性对齐外不碰共享索引」。

指向关系我也核了：第 28 行说的「下面那段」确指第 30-64 行，位置引用**正确**。

### 8c. 仅记录：收尾报告第 73 行对这条记忆的转述没有越界

收尾报告写「记忆里本来就有更好的做法（私有索引 `GIT_INDEX_FILE`），我没有取用」——只说存在且更好，没有复制「根本不碰共享索引」那个绝对句。**无需改。**

---

## 9. 评审报告第七节「处置」

逐条对当前 `main` 核过，采纳项**全部落地**：

| 行 | 核查 |
|---|---|
| F1 注释断言有反例 | **属实**。`handler.py:183` 注释已收窄为「it means upstream *responded*」；测试 `test_a_count_upstream_answered_uselessly_keeps_the_leg_it_flew` 存在（`test_pipeline_app.py:1422`）并通过 |
| F2 字段名 | **属实**。`format_counted`/`format_counter` 均已不存在，现为 `format_count_provider`；残留的 `counted` 全是无关局部变量（`pipeline_app.py:292`、`request_log.py:147`、`handler.py:247`），正是 F2 所说「`counted` 已有别的含义」 |
| F3 live doc | **属实**。`.dev` 的 `4d029eb` 落地，spec 新增「一次计数请求怎么读」+ 着色表「计数提供方」一行 + 不进结束原因阶梯的理由 |
| F4 测试改名 | **属实**。`test_a_count_upstream_could_not_answer_is_reported_as_an_estimate`（`:1378`），docstring 第 1381 行确实点明 `ProviderError` refusal 不会降级 |
| F5 `bytes_out` | **属实**。`handler.py:244` 写入、`pipeline_app.py:325-327` 读出并赋 `trace.received`，且带注释说明为什么用 `received` |
| F6 登记 | **属实**。`.dev/docs/tui/deferred.md` 第 4 条存在，其引用的 `docs/tmp/260820-review-count-tokens-shared-pipeline.md` 也在（15439 字节） |
| F7 由 F5 顺带缓解 | **属实**（渲染实测第 1、2 形态是 `↑B ↓B ↑tok`） |
| F8 三处 `isinstance` | **属实**，且现在是 5 处（`count_provider`、`reason`、`upstream_protocol`、`bytes_in`、`bytes_out`）——F5/9e3d374 又加了两个字段，数量长了不是缺陷 |
| F9 正则 | **属实**。`test_pipeline_app.py:1374`、`:1441` 均为 `r"[↑>][\d.]+(B\|KB\|MB)\b"` |
| §三 if/elif 顺序注释 | **属实**，`request_log.py:354` |
| 提交清单 / `064ba63` / F6 后续 | **属实**，见本报告 §1、§2 |
| 「评审自留 `/tmp/mutant/`、`/tmp/probe_count_line.py` 未清理」 | **属实**，两者当前都还在 |

### 9a. minor：「§一 末尾 docstring 措辞」这一行写的是已被覆盖的中间态

§七写：「`format_counter` 的 docstring 原写「indistinguishable」…**改成**「交付轮次仍带自己的字节字段，真正读不出的是缺席」」。

追踪那句英文原文 `would still carry its own byte fields`：

| 提交 | 是否含该句 |
|---|---|
| `d3335b6` 18:07 | 有 |
| `9e3d374` 18:08 | 有 |
| `40681ce` **18:19:15** | **无**（整段被改名重写时删掉了） |
| 当前 `main` | 无 |

而评审报告本身是 `86f4a46` **18:19:58** 提交的——**比删掉那句的提交晚 43 秒**。所以这一行写下时，它描述的终态已经不存在了。

后果不严重：`40681ce` 重写后的 docstring 干脆不再做那个同形论证，F 项要修的毛病确实没了。但任何人拿 §七 去对当前代码「§一 采纳了吗」，会既找不到旧措辞、也找不到承诺的新措辞。**严重度：minor**，改法：加一句「该措辞随后被 `40681ce` 的整段重写取代，重写后的 docstring 不再作同形论证」。

---

## 10. 其他

### 10a. minor：收尾报告 §可复用资产建议 是个悬空指针

第 79-81 行：

```
## 可复用资产建议

见下节（评审后补齐）。
```

「下节」是 §待裁决/未做，与可复用资产无关。这是个指向不存在内容的占位符。既然报告状态仍是「草稿」，属预期内，但定稿前必须填或删。**严重度：minor。**

### 10b. 仅记录：报告的锚点 `fa1df74` 已经不是 `main` 的头

核查期间 `main` 从 `bbbcb37` → `8a36fe3` → `7debb39`，`.dev` 从 `4d029eb` → `0e398f3`。报告里凡是说「当前 main」的地方（§验证 第 49 行的 `fa1df74`）都应读作「快照锚点」而非「现状」。报告本身已经写了 SHA，所以没有失真，**无需改**；提醒读者不要把 1257 当成今天的 `main` 的数字。

---

## 结论

| 严重度 | 条数 | 编号 |
|---|---|---|
| blocker | 0 | —— |
| major | 3 | 4a（`783f023` 修复归属不成立）、7a（清点 20 是写入前口径，分类表却含本记录）、7b（内容副本是 16 不是 15，两份文档同错） |
| minor | 5 | 1a、7d（脚本载体指错段落 + 漏锚点断言）、8b、9a、10a |
| 仅记录 | 3 | 3a、4（1 skipped）、10b |

**核查覆盖**：7 个提交 SHA 全部逐个 `git show` 核过；`064ba63` 裹走的说法用 `git log -S` 交叉验证；五种渲染形态实际构造 `RequestLine` 渲染并逐字符比对；1257 / 1184+44 / 1190+44 三个数字在隔离副本上完全复现，且把「同样的 44 条」加强为集合逐条相同；75 failed 在两个提交上复现并定位到报告点名的两个符号；16 个内容副本逐个 blob hash 比对；非文件载体逐个打开看过。

**未复现的**：共享树 1272、评审 §七 1244（共享树是移动靶，当前同一命令得 1277，量级一致，**依据仅为作者自述**）；Ruff / Pyright（口径不可分离，**依据仅为作者自述**，见 4b）。

**最值得说的一句**：报告里最强的一条恰恰是最容易被当成「口述回忆」而被跳过的那条——§「期间 main 曾经红过」的 75 failed，我在 `783f023` 与 `ea0417c` 上分别复现出同一个 75，报错也正是它点名的 `count_tokens` 与 `status=` 两个符号，先后两拍。它写对了。而紧挨着的 `783f023` 修复归属，是同一段叙事里唯一站不住的一句。

---

## 附：核查足迹（只读证明）

- **没有建 worktree。** 全部隔离检出用 `git archive <sha> | tar -x -C /tmp/verify-facts-260820/c-<sha>`，因为 `git worktree add` 会往共享 `.git/worktrees` 写条目。核查结束时 `git worktree list` 仍是三项，与核查开始时相同。
- **共享索引未被触碰**：`git diff --cached --name-only` 为空。
- **共享工作树新增文件只有本报告一个**：`git status --porcelain | rg verify-facts` → `?? docs/tmp/260820-closeout-verify-facts.md`。
- 唯一在共享树里跑过的命令是 `uv run --no-sync pytest … -p no:cacheprovider`（1277 passed）与若干 `git show` / `rg`，均不写仓库。
- 保留的证据文件（`/tmp`，可随时删）：`failed-6ef4b03.txt`、`failed-9e3d374.txt`、`failed-783f023.txt`（FAILED 列表，用于集合比对）、`render2.py`（五种形态渲染脚本）。隔离检出目录已删。
- 核查期间 `main` 移动了四次（`bbbcb37` → `8a36fe3` → `7debb39` → `414d03c`），`.dev` 移动一次；记忆条目 `git-commit-takes-the-whole-index` 被改写一次（18:35 → 19:06）。这些都不是我做的。



