---
slug: facts
agent_id: afc6e2ab44a22bc36
session_id: 3db40195
base: 5995bbe0ac1885482e4976975c3b74d196cb7b11
branch: worktree-agent-afc6e2ab44a22bc36
worktree: /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-afc6e2ab44a22bc36
plan: /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md
status: superseded-by-facts-round4
---

# Task 2 progress：Raw SSE frame 与 Chat facts

## 当前任务

Task 2 source已完成并提交为 `364e3a490714c3613f7d47f149377fd069433684`。Raw frame decoder、strict Chat facts、per-choice state、标准multi-choice projection与translated assembler facts复用均已落地。

## 基线literal oracle

命令：`uv run --project /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-afc6e2ab44a22bc36 python /home/xp/.claude/jobs/3db40195/tmp/task2_baseline_probe.py`

结果：worktree／branch／HEAD内嵌断言通过；case 1为`[('a', '1'), ('b', '2')]`，case 2为`[('a', 'one'), ('b', 'two')]`，case 3为`[('x', 'first\nsecond')]`；`literal baseline: PASS`。

## Source commit

- `364e3a490714c3613f7d47f149377fd069433684` — `feat: model buffered Chat stream facts`

## 命令结果

- Refactor后literal probe：3组legacy events逐项等于brief literal，raw frames拼接逐字等于输入；LF-only与drop-EOF-tail两个控制均在byte equality处按预期判红。
- Production probe：标准两choice／tool／usage projection、semantic freeze、error-carrier precedence与logical size接口通过。
- Existing translated assembler suite在新增reader-specific tests前：`11 passed`。
- Task 2精确pytest：`96 passed in 2.15s`。
- Task 2精确Ruff：`All checks passed!`。
- Task 2精确Pyright：`0 errors, 0 warnings, 0 informations`。
- 四个critical mutation controls：移除freeze guard、恢复`error and not choices`、从raw删separator、只输出choice 0均由对应目标断言判红；每轮以SHA-256核对恢复。

## 剩余项与验收

1. 已完成：冻结独立literal input→events oracle并记录基线输出。
2. 已完成：实现bounded raw frame decoder并保持既有SSE行为。
3. 已完成：实现strict Chat error／chunk reader与single-read state。
4. 已完成：实现标准multi-choice projection及state／projection size contract。
5. 已完成：translated assembler只复用decoder facts，未采用direct multi-choice state。
6. 已完成：Task 2精确pytest、Ruff、Pyright与source commit。
7. 已完成：最终报告写入`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-implementation.md`。

## 在途意图

无。Source candidate固定在`364e3a490714c3613f7d47f149377fd069433684`，等待主会话独立review与集成。

## 已否决路线

- 用重构后的`read_events()`给新decoder当oracle：同源，无法抓分帧回归。
- 让`ChatCompletionsAssembler`兼任direct state：terminal、multi-choice与loss语义不符。
- 用OpenAI SDK accumulator替代本项目字段表：SDK可作实现辅助／异源正例，不是行为authority。

## Fix round 1／5（WIP）

起点：`364e3a490714c3613f7d47f149377fd069433684`。评审报告`260906-task-2-facts-review.md`的2 blocker／11 major／1 minor全部采纳（C级可逆代码修正）；按更新后的direct-passthrough §9.3.1、TUI Chat schema与plan Task 2执行。

当前顺序：先修production raw decoder／frame ownership，再修event availability与state facts／size／projection；production probe通过后补测试、controls与SDK differential。

本轮不得后移的事项：chunk末CR歧义、single raw bytes、JSON availability、error taxonomy先于freeze、分层unknown／unattributed、usage六态、logprobs三态、error reason／spellings／end offset、unknown key与recursive size、allocation前prospective sizing、stdlib final-writer size。

### Fix round 1 source commit

- Commit：`b417bf6508e65eb72195ebb71fbc79550dcf33d3` — `fix: preserve exact buffered Chat facts`。
- Commands：更新后Task 2 pytest为`121 passed`；Ruff clean；Pyright 0 errors；修改前literal oracle、refactor后literal oracle、全量长度0～8 one-byte split oracle及fix-round production probe均通过。
- Controls：ambiguous CR、single raw owner、freeze、error-with-choices、raw separator、all choices、prospective no-deepcopy、unknown-key size、big-int recursive equality、stdlib float size、JSON null availability、layered unknown、error reason、error end offset、invalid-index provenance、logprobs null、usage null均有目标判红并逐次SHA-256恢复。
- 剩余项：原评审者复评当前HEAD；如有新finding，进入下一fix round。
- 在途意图：不再修改source，等待复评。
- 已否决路线：不以Task 3补偿Task 2缺失facts；不以orjson代替最终stdlib writer；不以合并unknown层级简化snapshot；不接入SDK production accumulator。

### Fix round 2／5 source commit

- Commit：`e42fc7660a656bc53a1ee7ea06e920b555d2a1f5` — `fix: reserve Chat materialization memory`。
- Finding处置：`task-2-facts-review-03`已改为direct prospective field-ledger merge；不再clone retained choice/tool metadata，也不调用payload/snapshot materializer。新增`MaterializationReservation`、`projection_reservation()`与`observation_reservation()`。
- Materialization：`to_completion_bytes(reservation)`直接从state按stdlib JSON语义增量写入预分配buffer，不构造payload或joined content string；reservation覆盖working buffer与final bytes，并校验state对应的reservation。
- 2,000,000-byte probe：projection `state=2000088, working=2065703, output=2000167, total=4065870, tracemalloc peak=4007960`；observation `state=2000098, working=0, output=2000214, total=2000214, peak=2696`。两者reservation均覆盖实测peak。
- Commands：Task 2 exact pytest `123 passed`；Ruff clean；Pyright 0 errors。200-case deterministic stdlib projection differential与prospective delta fuzz均通过。
- Controls：19项targeted mutation controls均判红并逐次SHA-256恢复；新增“只reserve output bytes”控制在2,000,000-byte peak断言处失败。
- 剩余项：原评审者仅复评`task-2-facts-review-03`及fix diff，无其他实施项。
- 在途意图：不再修改source，等待fix round 2复评。
- 已否决路线：不继续保留metadata clone；不靠Task 3补偿；不以最终body size冒充materialization peak；不恢复whole-payload／whole-string中间物。

### Fix round 3／5 source commit

- Commit：`0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f` — `fix: account Chat materialization structure`。
- Finding处置：`task-2-facts-review-03` residual A改为`_ProspectiveSizer`直接对current field ledger与incoming FrozenJson逐项、按event顺序演算，不构造fresh/collapsed state，也不复制retained choice／tool metadata；choice finish、tool id/name、unknown的`current=B; incoming=A,B`三组测试均满足`before + delta == after`。
- Finding处置：residual B移除fixed 64KiB与zero-working猜测；projection／observation的`working_copy_bytes`均由递归结构输出量计算并随nested结构与record数量增长。`to_completion_bytes(reservation)`直接增量写入预定尺寸buffer，不构造payload或whole JSON string。
- Evidence：2,000,000-byte content reservation为`working=2000167, output=2000167, total=4000334`；100层nested projection total从shallow `378`增长到deep `778`；5000-choice observation total从small `318`增长到many `218060`。这些是DeliveryUnit式logical encoded bytes，不声称CPython allocator/tracemalloc上界。
- Commands：Task 2 exact pytest `127 passed`；Ruff clean；Pyright 0 errors；500-step prospective delta fuzz与200-case stdlib byte differential均通过。
- Controls：22项targeted mutation controls均判红并逐次SHA-256恢复；新增collapse same-event overlay、fixed 64KiB projection working、zero observation working及only-output reservation controls。
- 剩余项：原评审者仅复评`task-2-facts-review-03` residual A/B及`e42fc76..0a7c9ce` diff。
- 在途意图：不再修改source，等待fix round 3复评。
- 已否决路线：不使用fresh-state collapse计算delta；不以tracemalloc作为cap口径；不使用fixed overhead或zero working guess；不让Task 3反推Task 2 materializer开销。

## 取代链

本文件已由 [`260906-direct-chat-progress-facts-round4.md`](260906-direct-chat-progress-facts-round4.md) 接管写入权；后续不再更新本文件。
