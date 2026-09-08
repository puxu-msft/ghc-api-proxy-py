# 会话收尾产物独立复核（job d123700e）

**复核时间**：2026-08-20 19:35–19:55　**复核者**：独立子智能体，只读
**被核产物**：`/home/xp/.claude/jobs/d123700e/tmp/DISPOSITION.md`、新增项目记忆、`.dev/tools/git-hunks.py`、`260820-review-s1-upstream-ownership.md` 文末更正节、15+2 个提交清单
**独立事件源**：`~/.claude/projects/-home-xp-src-ghc-api-proxy-py/d123700e-e080-4b20-8d5b-8a777d3f0032.jsonl`（3757 条记录）+ 同目录 `subagents/` 下 9 份子智能体转录

## 结论

**needs-fix，0 blocker。** 提交清单双向对账通过（正好 15+2，无遗漏、无夸大）；`DISPOSITION.md` 的 population 计数可复算且精确；第 4 类探针表 6 行中 5 行的载体逐个打开确认属实；新增记忆的三次失败全部在 transcript 里逐字属实；更正节确为纯追加（19 行插入、0 行删除）。

需要处理的有 7 条，按代价排序：

| # | 严重度 | 一句话 |
|---|---|---|
| A | major | **`/tmp/rev-*` 完全不在处置面内**——7 份已提交报告把它当证据载体点名引用，约 36000 个文件，而它不是 harness 拥有的目录，会被系统 tmp 清理静默抹掉 |
| B | major | **更正节的因果解释与它自己的数字自相矛盾**：当前侧 4→4 根本没变，变的是基线 3→4。原报告被推翻的其实是**基线数字**，不是「补 F2 消除了增量」 |
| C | major | **非文件类候选漏了 8 条**（我独立枚举出 14 条，你列了 6 条），其中 4 条在任何持久载体里都找不到 |
| D | minor | 新增记忆写「踩了三次」，transcript 里是**四次**——重测 e8 时脚本缺 `mode` 参数崩掉却被数成 0 条，这一次没写进去 |
| E | minor | 更正节在文末，而被推翻的 F2 条目在**结论表 line 20**，那里没有任何指向更正的标记 |
| F | minor | 第 1 类点名 `260820-review-s1-wiring.md` 承载变异记录，但**该文件零变异记录**（`rg '变异'` 命中 0） |
| G | minor | 探针表 `_trace_driver.py` 那一行的结论**没有载体**——点名的两处都不含它 |

已被你自己修掉、我独立复算确认无误的：三个失效哈希（详见第 1 节）。
判断正确、无需改动的：`docs/agents/delivery-keepalive/` 不代为编辑（详见第 6 节，有比你手上更强的依据）。

---

## 1. 提交清单双向对账

### 枚举方法

不靠 `[main abcd123]` 形态的回执收割——**这次会话一条都没有**（`rg '\[[a-zA-Z0-9/_.-]{1,40} [0-9a-f]{7,10}\]'` 在主 transcript 上 exit 1，因为 15 次提交全部用了 `git commit --quiet`）。改为从 `tool_use` 记录里直接枚举实际发出的命令：

```bash
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use")
       | select(.name=="Bash") | .input.command' "$T" \
 | rg -o 'git (-C [^ ]+ )?(commit-tree|update-ref|commit|tag|push|stash|reset|checkout|revert|cherry-pick|rebase|branch|worktree|gc|prune|filter-branch|apply|am)\b[^\n]{0,50}'
```

这条枚举覆盖了 `commit-tree` + `update-ref` 这条不产生 `git commit` 字样的旁路（记忆 `git-commit-takes-the-whole-index` 里那套私有索引写法正是它），结果是**零命中**——所以不存在「用别的方式落地、清单里看不到」的提交。

### 方向一：你列了而源里没有的（夸大）

**零条。** 实际发出的主仓库 `git commit` 恰好 15 次（5 次 `--file=- && git log -1`、3 次裸 `--file=-`、1 次 `&& git log -3`、1 次 `&& git log -1 && git status`、5 次 `-m`），`.dev` 恰好 2 次。逐条与你列的 15+2 对上，提交信息一一吻合。

### 方向二：源里有而你没列的（遗漏）

**零条提交。** 但有 3 个**非提交的写操作**不在你的清单里，其中两个值得记一笔：

- `git tag -f wip/s1-snapshot`（指向 `git stash create` 出的 `bd09f2b`，09:56）——你在第 6 问里已自陈，见第 6 节。
- **`git checkout -- $FILES` ×2**。这条命令在你自己的记忆 `git-commit-takes-the-whole-index` 里被明确列为禁用写法（「不要用 `git checkout -- <file>` 还原临时改动：它会连同该文件里未提交的修改一起清掉（同日也踩过）」）。它出现在本次会话的 transcript 里。我没有证据说它这两次造成了损失（当时的还原都有 sha256 前后比对），但**这两次执行本身没有出现在任何收尾记录里**，而它是同日已付过代价的高危写法。建议在收尾里点名，或确认它跑的是副本树而非主工作树。

### 三个失效哈希：独立复算

你的更正正确，我用两条独立判据各验一遍：

```
9194fd5 -> 9fc5f25 : SAME-PATCH   (git patch-id --stable)
b4cdccc -> a7ca9ea : SAME-PATCH
cf9e590 -> 31a4b00 : SAME-PATCH
```

三个新哈希 `git merge-base --is-ancestor <h> main` 全部为真；`git show main:src/app/server/pipeline_app.py | rg 'Ruled 2026-08-20'` 命中 line 386。内容在位，结论成立。

**你没查的那一半，我查了**：重写发生在 16:02（`git log --format='%h|%cd'` 显示 40 余个提交共享 `08-20 16:02` 这个 committer date），主分支今日 126 个提交、ahead origin 102。我把 `DISPOSITION.md` 当前引用的全部 13 个哈希逐个查了可达性，除更正表里保留备查的 3 个旧哈希外，其余 10 个全部 ON-MAIN 或 ON-DEV。**没有第二批失效哈希。**

`9194fd5` 现在**任何 ref 都不可达**（`git for-each-ref --contains` 空），只活在 reflog 里，会被 gc 回收；`b4cdccc`/`cf9e590` 还挂在 `refs/heads/a/2026-08-20-split-53fec22` 上。内容既已在 main，这不构成损失。

### 一个你没注意到的事实：`9194fd5` 是那次「裹走同伴 11 个文件」的提交

```
$ git show 9194fd5 --stat
docs: say what is known about the guard's placement and what is not
 docs/agents/anthropic-responses-bridge/implementation.md   |  2 +-
 docs/tmp/260820-websearch-responses-leg-mapping.md         | 42 ++++++--
 src/app/pipeline/delivery/assembler.py                     | 13 ++-
 src/app/pipeline/translation_driver/openai_responses.py    | 86 ++++++++++++---
 src/app/pipeline/translation_driver/semantic.py            | 14 ++++
 src/app/server/handler.py                                  | 18 ++++-
 src/app/server/pipeline_app.py                             |  3 +-
 tests/http/test_pipeline_app.py                            | 31 ++++++
 tests/unit/test_sse_assembly.py                            | 41 ++++++
 tests/unit/test_translation_driver.py                      | 92 ++++++++++++---
 10 files changed, 301 insertions(+), 41 deletions(-)
```

`9fc5f25`（main 上的等价体）逐字节相同。这条提交只有 `pipeline_app.py` 的 3 行是你的，其余 9 个文件是同伴的 hosted web search 工作——正是记忆 `git-commit-takes-the-whole-index` 开篇记的那次事故。

**这影响「15 个提交」这个说法的含义**：它是 15 次提交动作，不是 15 份属于本会话的内容。收尾清单如果被后人当作「本会话产出」来读，`9fc5f25` 会把别人的一整片工作算到你头上。建议在清单里给它加一句注。反向的那一半（同伴的 pathspec 提交带走你未提交的改动）已在记忆里记了，此处不重复。

---

## 2. `DISPOSITION.md` 的准确性

### population：可复算，且精确

| 判据 | DISPOSITION 记 | 我实测 | 说明 |
|---|---|---|---|
| `find … \( -type f -o -type l \)` | 18969 | **18970** | 差 1 = `DISPOSITION.md` 自身，写入前的快照 |
| `fd -H -I --type f --type l` | 18969 | **18970** | 同上，两法仍一致 |
| 顶层目录 | 22 | **22** | 一致 |
| 顶层文件 | 23 | **24** | 差 1 = `DISPOSITION.md` 自身 |
| `fd` 不带 `-I` | （少报） | 9225 | 确认 `.gitignore` 会吃掉一半，`-I` 的说明成立 |

我另做了一次**分类闭合校验**：23 个顶层文件按表中五类点名分别是 9（备份）+5（中间产物）+8（探针）+1（工具）= 23，22 个目录全在第 1 类里。**枚举无遗漏、无重复计数**。唯一的瑕疵是 `combined/` 在第 1 类和第 3 类各出现一次，不影响计数（它是目录，计在 22 里）。

### 第 5 类（可复用工具）：属实

`.dev/tools/git-hunks.py` 与 `$CLAUDE_JOB_DIR/tmp/hunks.py` **逐字节相同**（`diff` 无输出）；`README.md` 19 行；`.dev` 提交 `9c6da97` 含这两个文件、47 行插入，ON-DEV 可达。

### 第 2 类（变异前备份）：属实

`sha256sum` 在 transcript 里出现 26 次，成对的 `BEFORE=$(sha256sum …)` / `AFTER=$(sha256sum …)` 形态可见。点名的 6 个提交现在写作 `7a51902 5e2f1d5 f1e76fc 926cabf a7ca9ea 783f023`，全部 ON-MAIN。

### 第 1 类（仓库树副本）：**F —— 点名的一份载体不承载它**

表中说「每次变异的『改了哪一处 → 打红了谁』都写在已提交的评审报告里」，点名 4 份。逐个查：

| 报告 | `rg -c '变异'` | 实际 |
|---|---|---|
| `260820-review-upstream-timeout-wiring.md` | 12 | ✅ line 213 起是一张完整的 10 行变异矩阵（m1–m10，含 3 个「绿（未检出）」和 1 个 hang），你说的「含 10 行变异矩阵」逐字属实 |
| `260820-review-pipeline-idle-timeout.md` | 9 | ✅ M1/M2 有「改了哪一处 → 打红了谁」，line 366、392、452 |
| `260820-review-s1-upstream-ownership.md` | 3 | ✅ §6.1「分辨力：对照 HEAD 源码实测真红」 |
| `260820-review-s1-wiring.md` | **0** | ❌ **零变异记录**。我另查了 `打红/改坏/分辨力/正样本/mutat` 全部零命中。它是一份链路对账 + 复核报告（19 个二级标题全部是对账、时序、逐项核对），不含任何变异实验 |

**这不是说第 1 类的处置结论错了**——另外 3 份报告足以支撑「变异可重建」。错的是**点名**：把一份不含变异记录的报告列为变异记录的载体，读者按图索骥会扑空，而扑空之后无从判断是自己找错了还是记录写错了。改法很小：把 `260820-review-s1-wiring.md` 从第 1 类的载体列表里挪走（它是第 1 类中 `staged-tree`/`mine`/`combined` 那几棵**归因**副本树的载体，不是变异副本树的）。

### 第 4 类探针表：6 行逐个打开，5 行属实、1 行落空

| 探针 | 点名载体 | 复核 |
|---|---|---|
| `repro.py` | `stream.py` 注释 + `7a51902` | ✅ `src/app/pipeline/delivery/stream.py:122` 逐字写了 shield 的 last-resort observer、后续 shield 不置换、`StopAsyncIteration exception in shielded future`。结论完整在位 |
| `probe_log.py` | `5e2f1d5` + `tests/unit/test_logging.py` | ✅ `test_a_logged_exception_carries_its_stack:71`、`test_json_carries_the_stack_as_one_field:94` |
| `probe_level.py` | `f1e76fc` + 同上 | ✅ `test_a_library_record_shows_its_severity:110`、`test_our_own_status_outranks_the_level_it_logged_at:123` |
| `_trace_driver.py` + `_trace_run.py` | 「`5e2f1d5` 的验证」+「`tests/tui/test_footer_screen.py` 的同形 harness」 | ❌ **见下** |
| `probe_cancel.py` | `stream.py` / `deadline.py` 注释 + `926cabf` | ✅ `stream.py:130,136,137` 三条注释分别写了「只取消在途的 pull」「取消投递到上游自己的 await 点」「`anext` 在途时 `aclose()` 抛 `RuntimeError`，先 settle 是前置条件」。三个结论一个不少 |
| `probe_idle.py` `probe_idle_c.py` | research 文档 + `a7ca9ea`/`2c3ba7b` 注释 | ✅ `pipeline_app.py:386` 的「Ruled 2026-08-20」注释在 main 上 |

**G（minor）：`_trace_*` 那一行的结论没有载体。** 它声称的结论是「多行栈在 live footer 之下不被 `rich.Live` 重绘吃掉（pty 抓屏）」。

- `git log -1 --format=%B 5e2f1d5 | rg -i 'live|footer|pty|多行|redraw'` → **零命中**。提交正文只说「The console gives the traceback its own lines rather than trailing it after `key=value` extras」，那是设计意图，不是 pty 实测结论。
- `tests/tui/test_footer_screen.py` mtime 是 **Aug 19 21:08**，早于本次会话；它有 `test_no_log_line_is_swallowed_or_overwritten`、`test_the_footer_sits_below_every_log_line`，形状确实同类——但它测的是**日志行**不被吞，不是**多行异常栈**不被吞。这正是本次探针要答的那一步差别。
- `src/app/observability/logging.py` 里唯一提到 footer 的是 line 127，讲的是终端能力探测，与此无关。

所以这一行的处置判据（「结论有可定位的持久载体」）**在这一行上不成立**。要么补一句到 `logging.py` 的注释里，要么在 `tests/tui/` 补一条同形用例，要么把这一行改成「结论未持久化，判定可弃，理由是 X」——三者都行，但现在的写法是「有载体」而实际没有。

---

## 3. 非文件类候选：我独立枚举出 14 条，你漏了 8 条

### 我的枚举方法（据此可判断「没有新增」与「没有枚举」之别）

1. `jq` 抽出主 transcript 全部 `assistant` 的 `text` 块 → 921 行；
2. 用 19 个更正／放弃标记扫一遍：`不成立|被证伪|证否|改判|撤回|作废|我错了|那是错的|假绿|放弃|不再成立|纠正|更正|推翻|收回|白做|走错|误判|归属判断`；
3. 命中 20 处，**逐处读全文**（不看摘要），归入你那张表的四个类别；
4. 反向再做一次：对每条候选，去 `docs/tmp/`、`src/`、`tests/`、提交正文、项目记忆里找载体，用 `rg` 确认在或不在。

命中 20 处收敛为 14 条不重复候选（三次假数字按你的写法算作 1 条）。**你列了 6 条，其中 6 条与我的重合，漏了 8 条。**

### 已列、我确认属实的 6 条

`事件级 idle 更贴合文档` / `停机噪声 3→4` / `变异导致 idle-guard 挂起` / `给取消测试加 asyncio.timeout` / `三次假数字` / `三个运行时探针`——载体逐个打开都在（第 5 节对第 2 条另有一处更正）。

### 漏掉的 8 条

**★ 标记的 4 条在任何持久载体里都找不到，是真丢失，不只是没列。**

| # | 类别 | 内容 | 现有载体 |
|---|---|---|---|
| ★1 | 放弃的路线 | 修 shield 噪声时**考虑并否决的两个替代**：手工 `task.remove_done_callback(asyncio.tasks._log_on_exception)`（依赖私有名字、是消音不是纠正用法）；`async with asyncio.timeout(...)`（超时语义仍是取消，不满足需求）。transcript 主文 921 行中的第 114 行 | **无**。`stream.py:122` 只记了被否决的 `wait_for(shield(...))` 形态；`260820-review-shield-stopasynciteration.md` 分析了 `_log_on_exception` 的机制但不含这次取舍。用户规则 `record-what-not-adopted` 要求记未采纳方案及理由 |
| ★2 | 放弃的路线 + 变异对照 | **撤回了一条自己刚加的测试**：评审建议补「正常路径从不取消上游」的回归测试，加完按惯例验分辨力，**四种变异（预读 pull／清理改成投递取消／清理顺序颠倒／去掉 `task = None`）全都打不红它**，判定「那是构造性保证，不是测试保证的」，与同日删掉的 S2 假守卫同一种气味。transcript 第 242、253、366 行 | **无**。`rg '构造性保证|永远不会失败|假守卫' docs/ src/ tests/` 零命中。这是本次会话里**分辨力判据最完整的一次否定结果**，而它只活在 transcript 里 |
| ★3 | 被证伪 + 变异盲区 | 上一个提交自称 `upstream_request_deadline now bounds a whole attempt`，且写了 `Verified by mutation`——实测在流式下不成立（`await send` 在响应头就返回）。**关键的第二层**：那批变异「打的是解析器和 driver 内的守卫，没有一个打在『配置到 driver 那根线』和『守卫覆盖到哪个阶段』上」。transcript 第 844 行 | 第一层由 `783f023` 提交正文承载；**第二层无载体**（`rg 'Verified by mutation|变异.*没有一个|盲区'` 在两份 timeout 文档里零命中）。这一层是可复用教训：**变异全绿只证明了它打到的那一层**，与既有记忆 `guards-stranded-on-the-legacy-chain` 同族 |
| ★4 | 被纠正的解析错误 | **第四次假绿**：重测 e8 三种停机形态时，脚本缺 `mode` 参数直接崩掉，被数成 0 条。transcript 第 331 行「又是一次假绿——脚本需要 `mode` 参数，直接崩了」 | 新增记忆只写了三次，这一次没写进去。见第 4 节 D |
| 5 | 被证伪（同源污染） | 子智能体报「机制上栈本来就是渲染的」——**它的探针跑在 08:13，读的是我 08:11 刚落的 `5e2f1d5` 新增行**（它引的 `logging.py:84,85,90` 正是新增行），判定不成立。transcript 第 123、124、140 行 | 结论被采纳进 `5e2f1d5`，但「这条判定为何被驳回」无载体。这是**同源 oracle** 的一次真实击中，且是子智能体在主会话正在改的同一棵树上跑探针造成的——属于派活纪律 |
| 6 | 被证伪（我给的前提错了） | 派活提示词里两个前提被子智能体推翻并被我照单接受：`sse.py` 的 `next_chunk` **没有超时**（是取消解耦，不是同一模式第三遍实现）；asyncio 噪声**没有**绕开项目日志层（走 `logging.getLogger("asyncio")` 冒泡到 root handler）。transcript 第 126、140 行 | `260820-smell-survey-streaming-pull.md` 承载结论（该文件已提交、412 行），但你的表里没点它，且「前提是我写错的」这一层没进文档 |
| 7 | 被纠正的因果解释 | 改动 3 的注释理由被证否：关闭源流保住关闭级联在 **generator 级成立、真实 socket 级不成立**——httpx 的 `aiter_raw` 把 `await self.aclose()` 写在循环之后而非 `finally` 里，提前关闭时 `Response.aclose()` 永不执行。transcript 第 480、481、533 行 | 有载体：`260820-review-s1-wiring.md:59`、`260820-review-pipeline-idle-timeout.md:107`。**只是没列** |
| 8 | 被纠正的落库错误 | 沙箱里写的是 `try/finally`，落到仓库时写成两条顺序语句 → `aclose()` 抛异常时 `finish()` 被整个跳过（请求永久卡在 footer、零完成日志）；实测还确认清理异常会**顶替**原始异常，按 `sse.py`／`keepalive.py` 既有约定改成原始异常获胜、清理异常 `from` 挂上。transcript 第 364 行 | 有载体（回归测试，撤回修复即变红）。**只是没列**，而它是本次唯一一处「沙箱验过的形状在落库时走样」 |

### 一条方法论上的建议

你那张表的标题是「非文件类候选的载体」，但实际起的是两个作用：登记候选、并声明载体。★1–★4 暴露的是第一个作用没做全，而不是载体判断错。**枚举的入口选窄了**——你回溯的是「我明确说过『这条不成立』的地方」，而 ★1（否决替代方案）和 ★2（撤回自己的测试）在当时的措辞里是正常推进，不带更正标记，所以回溯时看不见。补一个入口：**凡是当时写下「考虑并否决」「我撤掉了」「变体 X 更糟所以不落」的地方，都是候选**。

---

## 4. 新增记忆条目

### 三次失败：全部属实，逐字核对

| 记忆里的说法 | transcript 证据 | 判定 |
|---|---|---|
| 副本树没带 `pyproject.toml` → pytest 缺 `asyncio_mode`，`pytest_asyncio` 自己在 plugin 里断言失败；读成「撤销我的改动后通过」→ 归属判错人 | 主文原句：「副本树里 pytest 配置没带过去，导致 harness 自身报错——**这次归属实证无效，重来**（把 `pyproject.toml` 和 conftest 一并复制）」。此后两次派活提示词都写进了这条告诫 | ✅ 属实，无夸大 |
| 沙箱漏 `aclosing` import → `NameError`，`rg -c "already running"` 数出 0 | 主文原句：「等一下——`aclosing` 根本没导入进那个沙箱文件…那 0/5 很可能是 `NameError` 导致探针根本没跑到，是假绿」，下一条「**假绿证实：`NameError`**」。工具输出里有 `NameError: name 'aclosing' is not defined` 的完整栈 | ✅ 属实 |
| gzip 解 zstd → 回退原始字节，`^:` 巧合命中 **22/9/90** 次 | 工具输出逐字：`v3_timeline_chunks rows=300 sse-looking=0 comment-frames=22` / `v3_tracks … =9` / `v3_operation_arenas … =90`，三个 sample 都以 `(\xb5/\xfd` 开头（zstd magic）。下一条：「那些计数是**假的**」 | ✅ 属实，**22/9/90 三个数字逐字对上** |

**没有夸大，没有记错。** 三个数字、三处措辞、以及「都产出形状正确的假数字」这个共性判断，全部有据。

### D（minor）：漏了第四次

主文第 331 行：「又是一次假绿——脚本需要 `mode` 参数，直接崩了。查参数重跑。」第 344 行你自己在给用户的汇报里也写了：「（这次重测本身也差点变成第三次假绿——脚本缺 `mode` 参数直接崩了却被我数成 0 条）」。

按时间顺序实际是四次：`pyproject.toml` → `NameError` → 缺 `mode` 参数 → gzip/zstd。记忆里选了 1、2、4，把 3 漏掉了。第 3 次恰恰是**参数错误**这一形态——前三条分别是配置缺失、导入缺失、格式误判，加上参数缺失才凑齐「探针没跑起来」的四种入口。**建议补上，或把「三次」改成「至少四次」并说明只详述三种形态。**

### 与既有条目的重复度：不该合并

**`never-echo-the-conclusion-beside-the-command`**：讲的是「结论作为固定文本硬编码在命令旁边，命令挂了它照印」——失效点在**结论的载体被挪到命令之外**。新条目讲的是「命令正常返回、输出确实是它算的，但它算的不是要测的东西」——失效点在**被测对象没被执行**。两者是相邻但不同的机制，新条目已用 `[[never-echo-the-conclusion-beside-the-command]]` 双链指了过去，措辞（「判据的载体从被测命令挪到别处，是同一族的另一种形态」）准确。**不该合并。**

一处可以更好：两份文件都开了「先跑正样本对照」这条 How-to（旧的写「用一个确定存在的模式跑同一条命令」，新的写「跑之前先在副本里跑一条已知通过的测试」）。同一条处方在两处各写一遍，是 `one-authority-allows-contextual-restatement` 说的「重述必须回指权威」的场景——建议新条目那句加一个回指，或明确它是旧条目那条在副本树场景下的具体化。不紧急。

**`git-commit-takes-the-whole-index`**：主题是共享索引与提交边界，与探针可信度毫无交集。**完全无重复。**（顺带：该条目的「反向也成立」一节记的正是第 1 节里 `9194fd5` 事故的镜像，两者互补。）

---

## 5. 更正节的正确性

### 形态：合规

`git show 9e3c4b1 --stat` → `1 file changed, 19 insertions(+)`，**0 行删除**。「只追加、不改原文」逐字成立，原报告 283 行中前 264 行一字未动。

### 原报告的相应发现在哪一节

更正节写「**第 5 节** F2」。精确位置是**两处**：

- **`docs/tmp/260820-review-s1-upstream-ownership.md:20`** —— 结论表里的 F2 条目本身：「F2 | minor（本 patch 引入）| 新的 `aclosing` 在 `loop.shutdown_asyncgens()` 时会多产生一条 … 日志（基线 3 条 → 现在 4 条）」
- **`:174`、`:196`** —— §5「死锁 / 挂起风险」里的测量与读法：「撞出第四条 `already running`」

所以「第 5 节」指的是测量所在处，说法不错；但**被推翻的那句断言登记在 line 20 的结论表里**，那里是任何人读这份报告的第一站，而它现在没有任何指向文末更正的标记。

**E（minor）**：结论表上的 F2 仍然独立地读作一条成立的发现。建议在 line 20 那一格末尾追加一句「（2026-08-20 更正，见文末）」——仍属追加，不改原结论文字。

### ★ B（major）：更正的因果解释与它自己的数字矛盾

更正节写：

> 该测量是在主会话补上 `_AccountedStreamingResponse` 关闭 body（F2 修复，提交 `926cabf`）**之前**做的。补上之后重测……
> ```
>               基线    当前
> abandon        1       1
> explicit       4       4
> closed-loop    0       0
> ```
> **增量为零。**

把这组数字和原报告并排看：

| | 原报告 | 更正后重测 | 变了吗 |
|---|---|---|---|
| 基线（explicit） | **3** | **4** | ← 变了 |
| 当前（explicit） | **4** | **4** | ← **没变** |

**当前侧一条噪声都没少。** 增量归零，是因为**基线数字从 3 涨到了 4**，不是因为补 F2 消除了什么。而更正节给出的唯一解释（「该测量是在补 F2 之前做的」）只能解释当前侧的变化——当前侧恰恰是没变的那一侧。

这不是我的推断，你当时自己就看到了。transcript 主文第 330 行前后的原话：

> `explicit` 模式（即 uvicorn 优雅停机的形状）**仍有 4 处**——F2 只覆盖了经由响应对象的那条路径。核对基线以确认增量。

随后跑的基线用的是 `PYTHONPATH=/tmp/rev-s1/base`，即**评审当时那一份基线快照本身**，三次全部 `already-running x4`。

所以真正被推翻的是**原报告「基线 3 条」这个数字**——同一份基线快照重测三次都是 4。更正节把它写成了「修复消除了增量」，这在读者那里会变成一条错误的因果：他会以为 `926cabf` 里的 `_AccountedStreamingResponse` 改动降低了停机噪声，而实际上它对 `explicit` 形态一条都没降。

**改法（仍是追加，不改原文）**：把那句因果换成事实描述，例如「原报告『基线 3 条』一项无法复现：用评审自己的基线快照 `/tmp/rev-s1/base` 重测三次均为 4 条，当前侧同样是 4 条，故增量为零。F2 修复覆盖的是经由响应对象的那条路径，对 `explicit` 形态的计数无影响。」

顺带：这一处正好是新增记忆那条教训的又一次实例——**基线也是探针，基线的数字同样需要证明它跑了**。原报告的「3」很可能就是一次没有对照的单跑。

---

## 6. 有没有该收尾而没收的

### ★ A（major）：`/tmp/rev-*` 根本不在处置面内

`DISPOSITION.md` 的 population 只覆盖 `$CLAUDE_JOB_DIR/tmp`（18969 个文件），开篇的处置理由是「目录由 harness 拥有并自行到期回收」。**这个理由对 `/tmp/rev-*` 不成立，而本次会话的证据主要就落在那里。**

实测（19:50）：

```
/tmp/rev-idle          12905 files
/tmp/rev-s1-wiring      3988 files
/tmp/rev-s1             2997 files
/tmp/rev-tw             1113 files
/tmp/rev-idle-impl       852 files
/tmp/rev-idle2           834 files
/tmp/rev-head-yV4e       558 files
/tmp/rev-shield           13 files
/tmp/rev-timeouts          2 files
（合计约 23000 个文件，另有 7 个单文件日志）
```

**7 份已提交的报告把它们当载体点名引用**：

```
$ rg -l '/tmp/rev-' docs/
docs/tmp/260820-review-s1-upstream-ownership.md
docs/tmp/260820-review-s1-wiring.md
docs/tmp/260820-review-pipeline-idle-timeout.md
docs/tmp/260820-review-upstream-timeout-wiring.md
docs/tmp/260820-review-shield-stopasynciteration.md
docs/tmp/260820-research-pipeline-idle-timeout.md
docs/tmp/260820-research-upstream-timeout-wiring.md
```

引用密度不低：`/tmp/rev-s1` 26 次、`/tmp/rev-s1-wiring` 19 次、`/tmp/rev-shield` 16 次、`/tmp/rev-idle-impl` 16 次、`/tmp/rev-tw` 14 次。而 `260820-review-s1-upstream-ownership.md:250` 直接有一节标题叫「**附：实验脚本清单（全部在 `/tmp/rev-s1/`）**」，下面列了 e1–e12 共 12 个脚本，第 5 节的更正也指名要读者去跑 `/tmp/rev-s1/e8_loop_shutdown.py`。

**为什么这是 major**：`/tmp` 不是 harness 拥有的目录，它归 systemd-tmpfiles / 系统重启管。这些目录会在你完全不知情的时候消失，而**消失之后，那 7 份报告里的路径引用不会报错，只会指向不存在的地方**——读者读到「见 `/tmp/rev-s1/e8_loop_shutdown.py`」，去看，没有，无从判断是自己环境的问题还是报告写错了。这与 `DISPOSITION.md` 开篇拒绝清空目录的理由（「被扫空的目录与从没有人清点过的目录无法区分」）是同一条道理，只是作用在另一个目录上。

**我不主张必须留下这 23000 个文件。** 三条路都可接受，但必须选一条并写进记录：

1. **判定可弃，写明理由**——变异矩阵已经记到「改哪一处 → 打红了谁」的粒度，副本树确实可由 `git` + 矩阵重建。那就在 `DISPOSITION.md` 里加一节 population，说清 `/tmp/rev-*` 的规模、被哪 7 份报告引用、以及为什么引用失效不构成损失。
2. **把探针脚本捞出来**——`/tmp/rev-s1/e1..e12`、`/tmp/rev-tw/mutate.sh`、`/tmp/rev-timeouts/probe.py` 这些是**脚本**不是副本树，总量很小，可以进 `.dev/`（那里已经有 `tools/`）。副本树本身弃掉。
3. **至少给报告加一句免责**——「`/tmp/` 下的路径为记录当时的位置，不保证仍然存在」。

我的偏好是 **2 + 1**：脚本进 `.dev/exp/260820-<topic>/`，副本树按 1 判弃。理由是那 12 个 e-脚本正是更正节要读者重跑的东西，而 `.dev/tools/git-hunks.py` 已经开了这个先例。

### wip/s1-snapshot：建议保留，但要留一句话

`wip/s1-snapshot` → `bd09f2b`（09:56:57，`git stash create` 的产物，「my S1 work + peer in-flight」）。它现在是**这个仓库里唯一指向那份混合快照的 ref**。

你自己说过「那个 tag 我留着没删——它同时兜着他们未提交的工作」，这个判断是对的：删掉它，同伴那份 09:56 的未提交快照就只剩悬空对象，而这正是记忆 `git-commit-takes-the-whole-index` 里「这种损失不报错」说的形态。

**但 tag 名 `wip/s1-snapshot` 不携带这个信息。** 三个月后的人看到一个叫 wip 的 tag，最自然的动作就是删。建议要么改成带日期和用途的名字，要么在 `DISPOSITION.md` 里加一行说明它兜着谁的什么、以及在什么条件下可以删（比如「同伴的 `delivery-keepalive` worktree 合入 main 之后」）。**不建议现在就删。**

### 两个不属于你的 worktree：正确地没动

```
/home/xp/.claude/jobs/826d4cda/tmp/review              7839b02 (detached HEAD)
.../.claude/worktrees/delivery-keepalive               beceaf4 [worktree-delivery-keepalive]
```

`826d4cda` 是另一个 job 的目录，`delivery-keepalive` 是并行会话的 worktree，**其 HEAD 在 19:38 还在动**（晚于你最后一个提交 19:33）。两个都不该由你处理，你也确实没碰。✅

### `git checkout -- $FILES`

见第 1 节。这是唯一一处「做了但没进收尾记录」的写操作。

---

## 7. 关于 `docs/agents/delivery-keepalive/` 的判断

**你的判断（只点名交回、不代为编辑）是对的，而且依据比你手上的更强。** 我查到三条你没查的事实：

**(1) 同伴自己已经发现并登记了，就在他们的 worktree 里。** `.claude/worktrees/delivery-keepalive/docs/agents/delivery-keepalive/deferred.md`（mtime **19:38**，比主工作树那份新、7646 vs 6975 字节）第 68–70 行：

> ### D-5 / D-6 上游超时语义 —— 并行会话正在做
> 2026-08-20 查看其未提交改动：`direct_driver/base.py` 已把 `response_header_timeout` 拆成独立参数（D-5 的错配），并把 `attempt.deadline_at` 固定成整次尝试的时刻、由交付链承担 body 那一段（D-6），docstring 也改成了与实测一致的说法。**我不重复做。**

他们不但看见了，还准确读出了你改动的两处内容，并明确写了不重复做。**这条漂移已经自行收敛，不需要任何人动手。**

**(2) 他们的分支已经含有 `783f023`。** `git merge-base --is-ancestor 783f023 beceaf4` → 真。所以他们合入时带的是修好之后的状态，不会把旧的 D-5/D-6 重新带回来。

**(3) 如果你去改主工作树那份，会撞车。** 他们 worktree 里那份 `deferred.md` 与主工作树那份 `DIFFERENT`，且更新。主工作树那份是他们 `cca8c9b`（17:16）提交的旧版；他们合入时会覆盖它。你现在在主工作树上编辑，只会给他们的合入制造一次没必要的冲突。

**关于「该不该由造成漂移的一方去更正」这个一般问题**，我的判断分两种情形，判据是**漂移落在哪种文档上**：

- **落在断言上**（`spec.md` 那类「某处有没有接线」的描述）→ **不该由造成漂移的一方改。** `docs/agents/delivery-keepalive/spec.md:117-120` 自己就写了这条政策：「本文里每一条关于『某处有没有接线』的断言都有保质期，主线在动，读到时请重新核实，不要把它当成当前事实引用」——而且它已经示范过一次，那一节逐字引用了 `a7ca9ea` 来自我更新。作者有机制、有意愿、也确实在做。外人代改反而破坏这个机制。
- **落在待办队列上**（`deferred.md` 的 D-5/D-6、`status.md` 的「排期修（不需要输入）」）→ **有告知义务，但仍不是编辑义务。** 区别在于代价：陈旧的断言只会被误读，陈旧的**队列条目会让人去做已经做完的事**——`status.md` 甚至写了「D-6 与 `handle_bounded` 是同一个病，合成一个 slice」，那是一次已经排上的重复劳动。所以造成漂移的一方**必须主动告知**，但告知的形式是交回、留言、或在自己的收尾记录里点名，不是去改别人的文件。

本例中告知这一步事实上已经被同伴自己完成了，所以**你只需要在收尾记录里注明「已核实同伴自行登记，无残留」**即可，比单纯「点名交回」更完整——因为「点名交回」会让读者以为还有一件事悬着。

---

## 附：本次复核跑过的全部判定性命令

| 用途 | 命令要点 |
|---|---|
| 提交枚举 | `jq` 抽 `tool_use.name=="Bash"` 的 `input.command`，`rg -o` 匹配 16 个 git 写动词（含 `commit-tree`/`update-ref`） |
| 哈希可达性 | `git merge-base --is-ancestor <h> main`；`.dev` 侧用 `git -C .dev` |
| 重写等价性 | `git show <h> \| git patch-id --stable` 两两比对 |
| 孤儿归属 | `git for-each-ref --contains <h>` |
| population | `find … \( -type f -o -type l \)` 与 `fd -H -I --type f --type l` 双算 |
| 工具持久化 | `diff <(cat $JOB/tmp/hunks.py) .dev/tools/git-hunks.py` |
| 载体存在性 | 对每个点名载体 `rg -n` 找结论关键词，命中即打开读上下文 |
| 更正追加性 | `git show 9e3c4b1 --stat`（19 insertions, 0 deletions） |
| 同伴 worktree | `git -C <wt> log -1`、`git -C <wt> status --short`、`git merge-base --is-ancestor 783f023 <wt-HEAD>` |
| `/tmp` 证据面 | `ls -d /tmp/rev-*` + `find <d> -type f \| wc -l`；`rg -l '/tmp/rev-' docs/` |

未执行任何写操作，除本报告文件外未新建、修改、删除任何文件；未执行任何 git 写命令。

---

# 修补复检（2026-08-20 19:55–20:10，限定范围）

只核第 1–7 条发现的修补本身，未重跑全部对账。以上内容一字未改。

## 结论

**7 条发现全部有实际动作落地，0 blocker，4 条未闭合 + 1 个前瞻风险。** 修补的方向都对，落点都在你说的位置；不闭合的部分集中在**摘要层与点名层**——正文改对了、索引钩子没跟上；一个点名错误被换成了另一个点名错误。另有 2 处本轮新引入的不实陈述。

## (a) 逐条落地核对

| # | 声称 | 复核 |
|---|---|---|
| 1 | 第 1 类移走 `review-s1-wiring.md` 并单列归因说明 | ⚠️ 动作已做，**但新点名同样不承载**——见「(d) 第 1 条」 |
| 2 | pty 探针持久化到 `.dev/exp/.../pty-footer/`，`c1dd030` | ✅ `c1dd030` ON-DEV，3 文件 74 行。README 四要素齐全：问题 / 做法 / **结论**（栈完整落屏，第 3–12 行是 traceback、第 13 行是下一条日志）/ **不证明什么**（只测一条日志一屏 100×30；不证明 footer 刷新频率与颜色降级；并点出 `tests/tui/_footer_driver.py` 走 `basicConfig` 不走 structlog 链、两者不可互替）/ **重跑命令**。这一条从「无载体」变成了本次做得最扎实的一条 |
| 3 | 59 个脚本 → `.dev/exp/...`，`89d4394`；约 23000 副本树判弃 | ✅ 数字**逐字复算一致**：`find /tmp/rev-* /tmp/smell-probe /tmp/idle-research` = **23293**；exp 树 60 个 `.py` + 1 个 `.sh`，减去 pty-footer 的 2 个 = **59**。11 个分组名与原根目录一一对应，文件名未改，报告引用可按 `<组名>/<文件名>` 对上。⚠️ 两处小失真见「(e)」 |
| 4 | 更正节因果订正 `6dac07f` + line 20 加标记，纯追加 | ⚠️ 内容对，**「0 删除」不实**——见「(b)」 |
| 5 | ★1 补记进 shield 报告文末，`a0d636f` | ✅ ON-MAIN，11 insertions / **0 deletions**。两个替代方案、否决理由、以及采纳方案为何不同（`asyncio.wait` 不建 outer future 所以根本不存在兜底观察者）都写了，比 transcript 里那句更完整 |
| 6 | 新记忆 `what-a-mutation-result-does-and-does-not-prove` | ✅ 文件在，MEMORY.md 索引在 line 21。★2 与 ★3 各成一节，且**多写了一条我没提的**：「同一个坑我随后自己踩了一遍——单测直接构造 driver 传 `response_header_timeout=1`，把 handler 里传参那一行删掉，1247 条测试全绿」。这条自指的复现使它从教训升级为可复算的判据 |
| 7 | `prove-the-probe-ran` 由三次改四次 | ⚠️ **正文改齐了，两处摘要没改**——见「(c)」 |
| 8 | 5–8 号候选 + 枚举入口教训写进 DISPOSITION | ✅ 新增「独立复核后的补充」节，8 条候选逐条列了载体；枚举入口那段逐字采纳。候选 #5 载体写「本节记录」——自指但诚实，可接受 |
| 9 | `git checkout -- $FILES` 如实记录 | ✅ 记了，且**比我报告里更准**：确认目标是主工作树中同时含同伴未提交改动的文件、每次 checkout 前完整复制到 `mine/` 并以 sha256 比对（22 次 `match=YES`）、判定「未造成损失但属侥幸」、并指出同日另一处同类风险中途改到了副本树而这处没有。这是自陈里少见的不打折 |
| 10 | `delivery-keepalive` 改判 | ✅ 改成「已核实同伴自行收敛，无残留」，引了 `deferred.md:68-70` 与 `783f023` 两条依据 |

## (b) 第 4 项不是纯追加

```
$ git show 6dac07f --stat
 docs/tmp/260820-review-s1-upstream-ownership.md | 12 +++++++++++-
 1 file changed, 11 insertions(+), 1 deletion(-)
```

**11 insertions, 1 deletion**，不是你说的 0 删除。删掉的那 1 行就是结论表 line 20，替换成同一句 + 内嵌的「（2026-08-20 更正，见文末）」。

**实质合规**：逐字比对两侧，原句一个字没改，标记插在「（基线 3 条 → 现在 4 条）」正后方——比我建议的「格末尾」更好，因为它紧贴被推翻的那个数字。所以**动作是对的，陈述是错的**。

值得单独说一句：往一行里插入内容，在 Git 里必然表现为 1 删除 + 1 新增，这是 diff 的行粒度决定的，**不存在「行内追加而 `--stat` 显示 0 删除」这种可能**。「纯追加」在这里应当由「原有措辞逐字保留」来判定，而不是由 `--stat` 判定；用 `--stat` 当判据会在下一次同类操作里再次给出错误答案。新增的「再订正」节本身（10 行）确实是纯追加。

内容核对：新节把因果改成了「原报告基线数字 3 无法复现，重测三次均为 4」，并明确写了「读者不应据此认为 `_AccountedStreamingResponse` 的改动降低了停机噪声」，还追加了「基线也是探针」那一句。**B 号发现闭合。**

## (c) 两条新记忆

### `what-a-mutation-result-does-and-does-not-prove`：无该合并的重复

读了正文逐条比对：

- 与 `prove-the-probe-ran-before-reading-its-number`：后者管**数字本身可不可信**（探针没跑起来），前者管**数字可信但结论仍错**（变异打到的层不是缺陷所在的层）。互为前后件，不重叠。新条目已双链指过去。
- 与 `guards-stranded-on-the-legacy-chain`：后者是「守卫存在但新链路没调用」这一具体形态，前者把它归纳成「(2) 配置到机制那根线」并给出三问框架 (1) 机制对不对 /(2) 线接没接 /(3) 覆盖到哪个阶段。**这是恰当的泛化，不是重复**——新条目已把旧条目标为其中一个特例并双链。
- 与 `never-echo-the-conclusion-beside-the-command`：机制完全不同（判据载体错位 vs 变异层次错位），无交集。

**判定：不该合并。** 唯一可挑的是两节标题（「打不红」「打红」）在索引钩子里被压成一句，钩子偏长，但可解码。

### `prove-the-probe-ran`：正文闭合，两处摘要未闭合

| 位置 | 现状 |
|---|---|
| 正文 line 13 | ✅ 「踩了**四次**」 |
| 正文 line 15–18 | ✅ 四条齐全，新增的第 3 条写明「`e8_loop_shutdown.py` 需要一个 `mode` 参数，不带就 `IndexError` 退出；我的循环只数 `rg -c` 的结果，读到 0 条」 |
| 正文 `Why` 段 | ✅ 「这**四种**失败都不报错、不变红」 |
| **frontmatter `description`** | ❌ 仍是「**三次**实测都是这样」 |
| **`MEMORY.md` line 22 索引钩子** | ❌ 仍是「副本树缺 `pyproject.toml`／沙箱漏 import／gzip 解 zstd，**三次**都给出形状正确的假数字」——旧三项，缺参数那项没进去 |

你说「正文与『这四种失败』一并改齐」——属实；但摘要没改。**索引钩子是这套记忆体系的第一入口**，一个只读索引的读者会得到「三次、且是那三种」的完整错误印象，而这正是本条目自己在讲的那类失效（摘要形状正确、内容作废）。`How to apply` 段里的 `rg -q "NameError|ModuleNotFound|IndexError"` 已经含 `IndexError`，说明第 3 条的处方早就在了，只是当时没给它一个条目——补齐摘要即可闭合。

## (d) 还有没有点名了却不承载的载体

### 1. 第 1 类的新点名同样不承载（把一个点名错误换成了另一个）

新写法：「**归因用的副本树**（`staged-tree` `staged2` `mine` `combined` `attr*`）另有载体：`260820-review-s1-wiring.md`（链路对账，不含变异记录）」。

```
$ rg -n -i 'staged-tree|staged2|归因|attr[0-9]|逐 hunk|选择性暂存|认领' docs/tmp/260820-review-s1-wiring.md
（零命中）
```

这份报告是**子智能体**对上游所有权改动的独立链路评审，它自己的实验树是 `/tmp/rev-s1-wiring/`。而 `staged-tree`/`staged2`/`mine`/`combined`/`attr*` 是**主会话**为「哪个 hunk 是谁的」做的归因与选择性暂存副本树，两件事没有交集。原来的点名错误（说它含变异记录）被换成了新的点名错误（说它是归因载体）——**同一格仍然不承载**。

归因那件事的真实载体是现成的，两处都在：

- 项目记忆 `git-commit-takes-the-whole-index`——逐 hunk 认领、私有索引 + CAS `update-ref`、以及「同伴的 pathspec 提交会带走你未提交改动」的反向形态，全在里面；
- `.dev/tools/README.md`——「2026-08-20 用它在 5 个混合文件上切出过一次提交，事后核对同伴的改动原样保留」，正是这批树的产物。

建议把那半句改指这两处。顺带一提：第 3 类（选择性暂存的中间产物）的载体写的是「产物就是提交本身」，那个判据对归因树同样成立，可以直接沿用。

### 2. 非文件类候选表第 3、4 行的路径正在失效（前瞻风险，非现存错误）

两行都点名 `tests/unit/test_stream_delivery.py`。它在 `main` HEAD 上还在，但**并行会话已经在工作树里把它改了名**，且改动已暂存：

```
tests/unit/test_stream_delivery.py  →  tests/unit/pipeline/delivery/test_stream_delivery.py
tests/http/test_pipeline_app.py     →  tests/int/test_pipeline_app.py
（同批还有 tests/ghc_client/ → tests/component/、tests/client_e2e/ → tests/e2e/claude/ 等一整轮重组）
```

他们一提交，这两行的路径就断。内容我确认在新位置且完好：`tests/unit/pipeline/delivery/test_stream_delivery.py:552` 是 `test_a_pull_in_flight_does_not_outlive_the_delivery`，`:561-562` 两条注释分别承载「这条测试是靠**不结束**来失败的」（即第 3 行那条「挂的是另一条测试」的结论）与「有意不加上界，实测加了也没用——`finish_stream_cleanup` 会推迟收到的取消并继续等自己那份清理，外层 `asyncio.timeout` 抢不走」（即第 4 行那条放弃的路线）。**两个结论都在，只是门牌号要换。**

这与哈希那件事是同一个病的下一层：**在有并行会话的仓库里，路径和哈希都不是稳定标识**。`DISPOSITION.md` 的「教训」段已经为哈希写了这条，建议把路径一并纳入——或者干脆按你自己那条教训的做法，把点名改成「符号名 + 内容特征」（`test_a_pull_in_flight_does_not_outlive_the_delivery` 的注释），那是重命名杀不掉的。

### 3. 其余点名：本轮复查过的都承载

`.dev/tools/git-hunks.py`（逐字节相同）、`.dev/exp/.../pty-footer/`（README 四要素齐全）、`a0d636f` 的补记、`89d4394` 的 11 个分组、`260820-smell-survey-streaming-pull.md`（候选 #6）、`260820-review-s1-wiring.md:59` 与 `260820-review-pipeline-idle-timeout.md:107`（候选 #7）——逐个打开确认在位。

## (e) 本轮新引入的不实陈述

### 1. 「9 份已提交报告」实为 8 份，且第 9 份未被追踪

这句出现在两处：`DISPOSITION.md:74`，以及**已经提交进 `89d4394` 的** `.dev/exp/260820-streaming-and-timeouts/README.md:3`。

```
$ for f in $(rg -l '/tmp/rev-|/tmp/smell-probe|/tmp/idle-research' docs/); do git ls-files --error-unmatch "$f" ... ; done
TRACKED    260820-research-pipeline-idle-timeout.md
TRACKED    260820-research-upstream-timeout-wiring.md
TRACKED    260820-review-pipeline-idle-timeout.md
TRACKED    260820-review-s1-upstream-ownership.md
TRACKED    260820-review-s1-wiring.md
TRACKED    260820-review-shield-stopasynciteration.md
TRACKED    260820-review-upstream-timeout-wiring.md
TRACKED    260820-smell-survey-streaming-pull.md
** UNTRACKED **  260820-review-session-closeout.md   ← 我这份复核报告，尚未提交
```

第 9 份是**我这份报告**——它引用那些路径是为了**报告这个缺口**，不是把它们当自己的证据；而且它此刻还没进版本控制。所以「9 份已提交报告点名引用它们作为证据」两个限定词都不成立：数是 8，且这 8 份才是「已提交」。

`rg -l` 是在你写完这句之后、我这份报告落盘之后跑的，所以这是一次**观测被自己的观测行为污染**——形态上正是你这轮刚记进记忆的那一类。改法：写 8，或写「8 份已提交报告 + 本次复核报告」。

### 2. `c1dd030` 被并列进 `/tmp` 缺口那一节，但它不属于那个 population

DISPOSITION「处置面缺口」节写「**59 个脚本全部持久化**……`.dev` 提交 `89d4394`、`c1dd030`」。59 这个数是 `89d4394` 一家的（60 个 `.py` − pty-footer 的 2 个 + 1 个 `.sh` = 59，复算一致）；`c1dd030` 里的 `_trace_driver.py` / `_trace_run.py` 来自 `$CLAUDE_JOB_DIR/tmp` 顶层，属于第 4 类探针，**从来不在 `/tmp` 那 23293 个文件里**。把两个提交并列在同一句话下，会让读者以为 59 覆盖了两者。拆开写即可。

### 3. 其余数字复算全部一致

`23293`（逐字）、`59`（可复算）、`11` 个分组、`a0d636f` 的 0 删除、四条新载体的可达性（`6dac07f` `a0d636f` ON-MAIN，`c1dd030` `89d4394` ON-DEV）——**没有其他失真**。

## 仍未闭合的清单

| # | 条目 | 一句话改法 |
|---|---|---|
| U1 | 「9 份已提交报告」在 `DISPOSITION.md:74` 与已提交的 `.dev/exp/.../README.md:3` | 改成 8，或「8 份已提交 + 本次复核报告」。`.dev` 那份需要一次新提交 |
| U2 | `6dac07f` 「0 删除」的陈述 | 记录里改成「原措辞逐字保留，行内插入标记，`--stat` 必然显示 1 删除」 |
| U3 | `prove-the-probe-ran` 的 frontmatter `description` 与 `MEMORY.md:22` 索引钩子仍是「三次」且列旧三项 | 两处摘要补齐第 3 项（脚本缺必需参数） |
| U4 | 第 1 类把 `260820-review-s1-wiring.md` 点名为归因副本树的载体——零命中 | 改指项目记忆 `git-commit-takes-the-whole-index` 与 `.dev/tools/README.md` |
| R1（前瞻） | 非文件类候选表第 3、4 行的 `tests/unit/test_stream_delivery.py` 将随同伴已暂存的重组改名而失效 | 改成新路径 `tests/unit/pipeline/delivery/test_stream_delivery.py`，或改用「测试函数名 + 注释特征」这种重命名杀不掉的点名方式 |

U1–U4 都是措辞级、各一两分钟；R1 只在同伴提交后才生效，可与他们的合入同步处理。**没有一条动摇这一轮修补的方向。**

### 本次复检跑过的判定性命令

`git show <h> --stat` + `rg -c '^-[^-]'`（追加性）、`git merge-base --is-ancestor`（四个新提交可达性）、`find /tmp/rev-* /tmp/smell-probe /tmp/idle-research \( -type f -o -type l \) | wc -l`（23293）、`find .dev/exp/... -name '*.py'|wc -l` 三段式复算（59）、`git ls-files --error-unmatch`（9 份报告的追踪状态）、`rg -n` 逐个打开新点名载体、`fd -HI` + `git status --short tests/`（定位同伴的改名）。仍未执行任何写操作（除本报告）、未执行任何 git 写命令。
