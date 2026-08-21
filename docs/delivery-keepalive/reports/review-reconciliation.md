# 保活调和后的 asyncio 控制流与清理语义评审

## 结论

**needs-fix，当前候选不能原样合入 `main`。** 生产代码的调和本身通过：没有发现主线 `926cabf`、`a9c75d4`、`16dd68c`、`a7ca9ea` 的语义在 `src/app/pipeline/delivery/stream.py` 中丢失或削弱；七条客户端保活性质仍成立；没有发现第八种生产路径上的「守卫判据取自替身量」；没有发现持续 `timeout == 0` 的忙等路径。

阻塞来自候选同时携带的 live documents：规范仍把 due preamble 后的 EOF 写成 STR-04 之前的成功终止线形，状态文档仍声称调和尚未完成。规范与当前 wire 行为直接矛盾，按本项目「可观察行为变更前规范完整、实现与 live docs 同步」的规则，必须先修正再合入。

证据权重：**代码结论强到足以据此放行该实现；候选整体结论强到足以据此暂缓合入。** 依据是当前源码与 `main` 的逐段差异、生成器 frame 状态探针、独立时序／关闭／STR-04 探针、全量测试、Ruff 与 Pyright。单次毫秒数只作为结构结论的佐证，不单独承担全称判断。

## 评审锚点与范围

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- 受评候选 HEAD：`45b04e3f16a97e63071673f060c6789648f92208`
- 受评生产提交：`1b3c90d fix: separate the client-facing keep-alive from upstream's pace (squashed for rebase)`
- 评审结束时 `main`：`13857911f99eda844cf44f3fa0d6629eb3f73b0d`
- 当前 merge-base：`4511aa3b362e7107141e55834d4c42766c9840b3`
- 评审期间 `main` 又前进了四个提交，但 `git diff HEAD...main -- src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py src/app/streaming/keepalive.py src/app/pipeline/delivery/sse_source.py` 为空；这四个提交没有改变本报告裁决的异步控制流表面。
- 源码加载确认：`uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"` 输出 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py`。
- 只读纪律：未修改生产代码或测试。评审中一度观察到其他会话留下的 `docs/agents/delivery-keepalive/spec.md` 修改与 `docs/tmp/260820-deferred-d3-d5-d6.md` 未跟踪文件；它们没有触及受评代码，也没有修正下述 STR-04 文档矛盾。最终状态检查时这些并行改动已不在本工作树，除本报告外 `git status --short` 为空。

## 发现

### F1——规范仍承诺 STR-04 之前的成功尾部

- 严重度：**major**
- 把握程度：**高，强到足以阻止当前候选原样合入**
- 位置：`docs/agents/delivery-keepalive/spec.md:44-53`，尤其是第 49 行；同一旧结论又出现在 `docs/agents/delivery-keepalive/status.md:30-34`。

规范写明：客户端尚无字节、合成 deadline 到期、下一 pull EOF 时，结果是 `message_start` → `message_delta` → `message_stop`，并称其为「已正常封口」。当前实现由于完整保留 `16dd68c` 的 STR-04，实际线形是 `message_start` → `error`，错误码为 `incomplete_responses_stream`，且不得再发 `message_stop`。

独立公共路径探针得到：

```text
incremental_truncation: ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'error']
held_truncation: ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'error']
preamble_only_truncation: ['message_start', 'error']
empty_unstarted: []
successful: ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'message_delta', 'message_stop']
```

这不是文案细节：`spec.md` 自称规范，且错误陈述的正是本次调和要求重点保存的可观察 STR-04 行为。修复应把 §2 的接受取舍改写为当前真实线形，并同步调整相邻的「下一 pull 失败」说明，避免把 EOF、异常与成功终止混写。

### F2——实施状态仍停在调和之前

- 严重度：**minor**
- 把握程度：**高，事实可由当前 Git 对象与本轮命令直接裁决**
- 位置：`docs/agents/delivery-keepalive/status.md:2-6`、`docs/agents/delivery-keepalive/status.md:43-56`

状态文档仍把最终候选写成 `7732a75`、基线写成 `5e2f1d5`、闸门写成 `1348 passed`，并说 `926cabf` 的调和「合入前必须先处理」且尚待决定。当前候选是 `45b04e3`，调和代码已在 `1b3c90d`，本轮全量结果是 `1488 passed、3 skipped`。该文件是 live status，不是历史归档；继续保留旧状态会让下一位集成者把已完成工作当成待办，并忽略本轮真正剩余的规范修正。

## 主线四项语义逐条核对

### 1. `task = None` 仍准确区分可清理的在飞 pull

`_events_with_ping` 在每轮先把 `anext(events)` 放进 `task`。如果 task 完成，代码先调用 `task.result()`，EOF 直接返回，普通事件则在 `yield _Pull(event=event, claim=claim)` 之前把 `task = None`。如果 deadline 先到，代码在 task 仍 pending 时 `yield _Pull(event=None, claim=claim)`，此时 `task` 保持非空。把裸事件换成 `_Pull` 没有移动清零点，也没有在 event-bearing yield 后偷偷启动下一次 pull。

frame 探针直接读取 `events.ag_frame.f_locals["task"]`：event-bearing `_Pull` 暂停时为 `None`；event-less timeout `_Pull` 暂停时是未完成的 `asyncio.Task`。关闭后一侧源收到 `GeneratorExit`，另一侧在飞源收到 `CancelledError`，且没有遗留 task。

严格措辞：task 可能已经 done、但生成器尚未来得及执行 `task.result()` 与清零；该瞬间不会出现在向调用方 yield 的稳定点，`finish_stream_cleanup` 对 done task 只观察、不取消。因此主线所需的清理语义保持，不能把注释理解成对每条 Python bytecode 之间瞬间状态的全称承诺。

结论：**保持。证据强到足以据此行动。**

### 2. `finish_stream_cleanup` 的异常与取消优先级未被改写

`git diff --unified=0 main...HEAD -- src/app/pipeline/delivery/stream.py` 在 `_events_with_ping` 的 `finally` 区间没有差异：`sys.exception()`、把 `GeneratorExit` 归一为无 primary、`finish_stream_cleanup(task, events, primary=primary)`、primary／cleanup cancellation／cleanup error 的优先级代码逐行保留。`926cabf` 引入的 in-flight pull 取消与下游 iterator 关闭顺序也未变化。

额外的 `_deliver` 层没有吞取消：全量回归中的 `test_a_cancelled_consumer_gets_its_cancellation_back`、`test_a_pull_in_flight_does_not_outlive_the_delivery` 与 idle guard 组合路径通过；独立探针确认关闭 in-flight pull 后源收到 `CancelledError` 且 task 集合回到基线。

一个需要准确描述、但不是本次回归的既有边界：若 `assembler.push` 抛 `AssemblyBoom`，同时 source 的 `aclose` 抛 `CleanupBoom`，调用方最终收到 `CleanupBoom`，`AssemblyBoom` 位于 `__context__`。原因是 body 异常发生在 `_events_with_ping` 的调用方，`aclosing.__aexit__` 随后以 `GeneratorExit` 关闭内层；内层 helper 看不到调用方 body exception 作为自己的 primary。当前候选与 `main` 在这一形状上相同，所以没有发生优先级削弱。

结论：**与主线一致。证据强到足以据此行动。**

### 3. 两层 `aclosing` 的位置正确

外层 `stream_delivery` 在唯一 client-facing yield 周围持有 `aclosing(_deliver(...))`；内层 `_deliver` 在装配与成帧循环周围持有 `aclosing(_events_with_ping(...))`。这两层分别解决两个不同的悬挂点：客户端离开时先关闭暂停在 byte yield 的 `_deliver`，再由 `_deliver` 的 context manager 关闭持有 upstream pull 的 `_events_with_ping`。

独立装配异常探针让 `assembler.push` 立即抛 `AssemblyBoom`。结果是异常原样到达调用方、`stream_delivery.ag_frame is None`、上游 finally 同步运行且只运行一次。路径为：`assembler.push` → `_deliver` 退出内层 `async with` → `_events_with_ping.aclose()` → `finish_stream_cleanup` → `_deliver` 关闭 → 外层 `stream_delivery` 关闭。没有一层被 `GeneratorExit` 跨过去，也没有重复关闭上游。

结论：**层数与位置正确。证据强到足以据此行动。**

### 4. STR-04 与三个 `started` 判断完整保留

调和只把主线三个 `started` 读取替换成同一个真实事实 `client_has_bytes.is_set()`：传给 `_commit` 的 preamble 判断、`session.finish()` 后 held-back preamble 判断、terminal 前「是否已有可纠正的 message」判断。`error_frame`、`terminal.seen` gate、错误码、无 `message_stop` 的早返回与成功 terminal 路径均保持主线代码。

语义等价性来自调用顺序，而不只是名字：增量路径在第一个 chunk yield 前置位；合成路径在 `message_start` yield 前置位；held-back 路径在首次 preamble yield 恢复后置位，但在暂停期间内层不会继续运行，下一次 pull 前已经置位。这与旧 `started` 的对应写入时刻相同。独立五场景探针输出见 F1，覆盖增量截断、held-back 截断、仅合成 preamble 后截断、从未开始、正常成功五条尾部。

结论：**完整保留。证据强到足以据此行动。**

## 七条保活性质复核

| 性质 | 独立证伪方法与结果 | 裁决 |
|---|---|---|
| 上游持续发 delta 且块未闭合时仍发 ping | 首块闭合后，第二块以 15ms 间隔连续送 12 个 delta，interval 为 50ms；在 EOF 的 STR-04 error 前观察到 3 个精确 `PING_FRAME`。 | 成立。证据强到足以据此行动。 |
| 打戳在交出之后 | 拉出第一个 `message_start` 后把 chunk 在调用方持有约 40ms；`last_write.at` 在持有期间不变，恢复生成器取下一 chunk 后才前进约 49ms。源码唯一写点也位于 `yield chunk` 之后。 | 成立。证据强到足以据此行动。 |
| `full`／`until-tool-use` 下两道守卫不同时熄灭 | 两种 policy 都先组装一块但扣住，synthesis 与 ping 均为 50ms；首 `message_start` 分别约 50.7ms／54.5ms，首 ping 分别约 107.2ms／105.0ms，均早于 140ms 上游结束。 | 成立。时值是单次样本，但与单门代码和现有参数化回归共同构成足以行动的证据。 |
| 上游持续就绪时不饿死保活 | 无 await 的 ready delta 循环持续约 120ms，interval 为 40ms，观察到 2 个精确 `PING_FRAME`。event-bearing `_Pull` 仍在装配后调用 `claim`，没有把 deadline 判断藏在 timeout 分支。 | 成立。证据强到足以据此行动。 |
| 合成 deadline 与保活 deadline 一起结算 | 两个 deadline 同时设为约 30ms；同一个 event-less `_Pull.claim()` 返回 true，并把 frame 中的 `ping_deadline` 前推约 30.5ms；置位 `client_has_bytes` 后 preamble 立即从 pending deadlines 消失，下一次 cue 按新 ping deadline 到达。 | 成立。证据强到足以据此行动。 |
| 装配异常先于提示传播 | event 到达后 `SlowNoBlockAssembler` 跨过 synthesis deadline 再抛 `ValueError`；调用方收到异常且已产出 chunk 列表仍为空。代码顺序是 `assembler.push(pull.event)` 在 `pull.claim()` 之前。 | 成立。证据强到足以据此行动。 |
| deadline 在装配期间到期时不被漏掉 | 每次同步装配 50ms、deadline 40ms；首 cue 约 50.3ms 到达，而不是等第二次装配后约 100ms。`claim` 在装配后读取当前时钟。 | 成立。证据强到足以据此行动。 |

主线新增 STR-04 没有让这些断言失去分辨力：相关测试都要求精确 `PING_FRAME`、首字节到达时机或异常前零 chunk；尾部新增的 `error` 既不等于 ping，也不能把首字节从 deadline 前移。尤其是「装配期间到期」若退回提前采样，首字节仍只能在第二次装配后出现，尾部 error 也在 EOF 后出现，无法误充 `< 2.0s`／本轮缩短探针 `< 90ms` 的首 cue。

## 两份设计交界处

### 旧 `_Pull.claim()` 在生成器关闭后

`claim` 闭包只捕获 event loop、`ping_deadline` cell、`last_write` 与 `client_has_bytes`。关闭 `_events_with_ping` 会清理 pull task 与 upstream iterator，但不会使闭包失效。调用方若故意保留旧 `_Pull`，之后调用 `claim()`，它仍可读 `loop.time()`、判断旧状态并前推已经脱离生产控制流的 `ping_deadline`；它不会创建 task、重新打开生成器、写 wire 或触发二次 cleanup。

探针在生成器关闭后调用两次：第一次到期返回 true 并前推 deadline，第二次返回 false；task 集合无变化。另一个探针把 `_Pull` 带出 `asyncio.run`，确认 event loop 已关闭后调用仍返回 true，没有异常。唯一代价是调用方持有 `_Pull` 多久，闭包对象及其捕获值就存活多久；生产唯一 caller `_deliver` 不把 `_Pull` 暴露出去，frame 关闭时引用随之释放。

结论：**无生命周期缺陷。证据强到足以据此行动。**

### 双层 `GeneratorExit` 传播

客户端在 outer yield 处关闭时，`GeneratorExit` 先进入 `stream_delivery`，外层 `aclosing` 对 `_deliver` 调用 `aclose()`；`GeneratorExit` 再进入 `_deliver`，内层 `aclosing` 对 `_events_with_ping` 调用 `aclose()`；最内层把 `GeneratorExit` 归一为无 primary 后完整执行 cleanup。若 pull 在飞，它先被取消并观察，再关闭 `read_events`；若 event-bearing `_Pull` 已交给装配层，`task` 已是 `None`，直接关闭 iterator。两种探针都同步触发 source finally，且只触发一次。

结论：**传播链闭合。证据强到足以据此行动。**

### `assembler.push` 抛异常

异常发生在任何 `claim` 与任何 cue 之前。Python 离开 `_deliver` 的内层 `async with` 时必调 `_events_with_ping.aclose()`，后者执行 `finish_stream_cleanup`；随后异常继续穿过外层 `stream_delivery`。普通 source close 时，原 `AssemblyBoom` 到达调用方；source close 自身也失败时，优先级形状与主线相同，见上文。

结论：**两层清理都运行。证据强到足以据此行动。**

## 忙等穷举

生产 caller 中能让 `timeout` 算成 0 的原因只有 enabled deadline 已到或在计算／等待之间到期。随后有两类分支：

1. pull task 已完成：先读取 result。EOF／异常直接离开；普通 event 交给 `_deliver`，装配不产字节时恰好调用一次 `claim`，产字节时 outer wrapper 会在下一次调度前更新 `last_write`。
2. pull task 仍 pending：产生 event-less `_Pull`。keep-alive 到期时 `claim` 把 `ping_deadline` 前推；preamble 到期时 `_deliver` 发 `message_start` 并置位 `client_has_bytes`；两者同时到期时两项在同一次 claim 中结算。

因此每条继续循环的生产路径都会让造成 0 的 predicate 在下一轮变成 false。探针补充验证：keep-alive-only 的四次 cue 间隔为约 30.4ms、30.4ms、30.4ms；preamble-only 在首 cue 后置位 `client_has_bytes`，60ms 内没有第二个 turn；联合 deadline 前推后按新 deadline 到达下一 cue。

私有 `_events_with_ping` 的协议要求 consumer 对每个没有真实写出的 `_Pull` 调用 `claim`。一个绕过 `_deliver`、反复丢弃 `_Pull` 又从不调用 `claim` 的非生产 consumer 确实可以让到期 predicate 常真；仓库生产调用点只有 `_deliver`，且其 `if wrote or not pull.claim(): continue` 保证 `wrote=False` 时恰好调用一次。这个人为违约形状不构成当前生产忙等路径。

结论：**没有 `timeout` 恒 0 的生产路径。证据强到足以据此行动。**

## 第八种「替身量」搜索

重新沿所有 guard 的事实来源反查：

- keep-alive 到期读 `_LastWrite.at`，唯一写点是 outer `yield` 恢复后；不读 upstream event 节奏。
- preamble 与「可否发 ping」共读 `client_has_bytes`；该门只在将要交出的真实 byte chunk 路径置位，不读「块已组装」或 `DeliverySession.started`。
- `wrote` 只代表本轮 `_commit` 是否实际产生 downstream chunk；它在所有 chunk yield 完成并恢复后才参与 short-circuit，不把「assembler 返回 block」当作写出。
- due 判断由 `claim` 在装配后读取当前 loop clock；不复用 pull 时刻采样值。
- EOF／upstream exception 来自 `task.result()`；不由 timeout 或空 event 代替。
- STR-04 来自 `assembler.terminal.seen`；不由「已有字节」或默认 stop reason 代替。

`client_has_bytes.set()` 在部分路径位于 inner yield 前，而 `_LastWrite` 在 outer yield 恢复后；前者看似比「客户端已收到」早，但两者之间整个 `_deliver` 都暂停，任何依赖该门的下一次判断都不可能运行。若下游成功请求下一 chunk，前一个 yield 已恢复，事实已经成立；若下游失败并关闭，生成器直接清理，不再消费该门。因此这不是第八种有行为后果的替身。

结论：**在当前生产路径中未发现第八种形态。该否定结论强到足以据此评审当前候选，但不外推到未来新增的 client write 路径；`spec.md:30` 已正确记录新增旁路会破坏唯一打戳点。**

## 验证结果

```text
$ uv run pytest
1488 passed, 3 skipped in 77.78s

$ uv run ruff check src tests
All checks passed!

$ uv run pyright src tests
0 errors, 0 warnings, 0 informations
```

独立探针均从已确认的 worktree 模块导入生产代码，文件放在 `/tmp`，未修改仓库：

```text
$ uv run python /tmp/reconciliation_asyncio_probe.py
event pull: task=None; stale claim after close is inert and callable
timeout pull: task is pending; close cancels pull and closes source
assembly exception propagates; both delivery frames close; source gets GeneratorExit
simultaneous assembly/close failure: CleanupBoom is raised, AssemblyBoom is context

$ uv run python /tmp/reconciliation_timing_probe.py
stamp-after-handoff: unchanged while held, advanced by 0.0494s on resume
talkative-and-ready: pings=3/2
held-full: start=0.0507s ping=0.1072s
held-until-tool-use: start=0.0545s ping=0.1050s
assembly-order: failure-before-bytes; first due cue=0.0503s

$ uv run python /tmp/reconciliation_deadline_probe.py
keepalive-only cue gaps: [0.030406621983274817, 0.030412521038670093, 0.030381220974959433]
preamble-only: no second zero-timeout turn after client_has_bytes
joint deadlines: ping advanced by 0.0305s and preamble disarmed

$ uv run python /tmp/reconciliation_stale_claim_closed_loop.py
{'loop_closed': True, 'claim_after_loop_close': True}

$ uv run python /tmp/reconciliation_str04_probe.py
incremental_truncation: ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'error']
held_truncation: ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'error']
preamble_only_truncation: ['message_start', 'error']
empty_unstarted: []
successful: ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'message_delta', 'message_stop']
```

这些 timing probes 使用缩短到 10ms～50ms 的运行时参数，目的只是让同一控制流在有限时间内显形；数值本身不是生产延迟承诺。全称裁决同时依赖源码分支穷举与仓库现有秒级回归。

## 最终裁决

- blocker：0
- major：1
- minor：1
- 生产代码调和：**pass**
- 主线资源清理语义：**保持**
- STR-04：**保持**
- 七条保活性质：**保持**
- 忙等：**未发现生产路径**
- 第八种替身量：**未发现**
- 候选整体 verdict：**needs-fix**
- 合入判断：**当前不能原样合入 `main`；修正 `spec.md` 的 STR-04 线形并刷新 `status.md` 后，生产代码无需再改即可进入合入流程。**
