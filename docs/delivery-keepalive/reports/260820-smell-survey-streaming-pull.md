# 代码怪味普查：`_events_with_ping` 及其近邻的上游拉取／保活／清理这一片

- 时间：2026-08-20
- 范围：`src/app/pipeline/delivery/stream.py`、`src/app/streaming/keepalive.py`、`src/app/streaming/sse.py`、`src/app/streaming/idle_timeout.py`，以及它们在 `src/app/server/pipeline_app.py`、`src/app/routes/anthropic.py` 上的接线
- 基线：`git HEAD = 3193880`（工作树有他人未提交改动，均不在本报告涉及的文件里）
- 前置阅读：`docs/tmp/260820-review-shield-stopasynciteration.md`（shield 缺陷的评审）、`docs/tmp/260820-downstream-keepalive-defect.md`（ping 节拍缺陷，待裁决）
- 证据强度约定：**【实测】**本次亲手复现、脚本可重跑；**【读码】**源码结构，可 grep 复核；**【推断】**有依据但未复现
- 本次**只读**：未修改 `src/`、`tests/` 下任何文件，未执行任何 git 写操作。探针脚本全部留在 `/tmp/smell-probe/`

---

## 结论

**这片代码最要紧的怪味不是并发写法重复，而是「谁负责关上游」这个契约在主产品路径上是空的，而项目却把它的全部测试火力压在了一条没有生产调用方的支路上。**

刚修完的 shield 缺陷、`docs/tmp/260820-downstream-keepalive-defect.md` 里那个 ping 节拍缺陷、以及前一轮评审 §6 记的「弃流时噪声换了个名字」，三件事共用同一个结构根：`_events_with_ping` 把上游拉取的所有权拿在手上，却没有任何退出路径去处置它。

| # | 怪味 | 位置 | 推荐强度 |
|---|---|---|---|
| S1 | 主产品路径没有清理契约，而 docstring 宣称它有 | `stream.py:73-75`、`stream.py:88-91` | **强烈建议改** |
| S2 | 那个 `finally` 在所有可达路径上都是空操作，形状上却像在兜弃流泄漏 | `stream.py:73-75` | **强烈建议改** |
| S3 | 测试密度与生产暴露面倒挂：清理语义的 10 个用例守着 0 个生产调用方 | `tests/unit/test_streaming_resilience.py` vs `tests/unit/test_stream_delivery.py` | 建议改 |
| S4 | 同一个「超时不取消 pull」循环两份实现，deadline 计算重复三处 | `keepalive.py:8-66,139-155` vs `stream.py:43-70` | 建议改 |
| S5 | `yield None` 哨兵 + `response_started` 双向读写：同一判据在调用方与被调用方各写一遍 | `stream.py:48-70` vs `stream.py:108-122` | 建议改 |
| S6 | 三个 `started`，三种含义，一个词 | `stream.py:94,95`、`blocks.py:137` | 记录备查 |
| S7 | `DeliverySession.start_response()` 无条件抛异常，docstring 描述了一条不存在的成功路径 | `blocks.py:158-166` | 记录备查 |
| S8 | 无 loop exception handler；真问题是 foreign ERROR 记录被渲染成 `[....]` 且 level 被丢弃 | `logging.py:24-35,75-91` | 记录备查 |
| S9 | `StreamSettings` 的默认值与 config schema 的默认值互相矛盾（0 vs 240） | `stream.py:21-25` vs `schema.py:193` | 记录备查 |
| S10 | 杂项：类型不一致、`if not started: started = True`、`with_idle_timeout` 是语义相反的第四变体 | 见 §10 | 记录备查 |
| S11 | 委托里说「`sse.py` 的 `stream_response`/`next_chunk` 是同一模式的第三遍实现」 | — | **判定为误报** |
| S12 | 委托里说「asyncio 噪声直接落 stderr，绕开了项目日志层」 | — | **判定为误报** |

计数：强烈建议改 2、建议改 3、记录备查 4（S10 内含 3 个小项）、误报 2。

---

## S1 主产品路径没有清理契约，而 docstring 宣称它有

**位置**：`src/app/pipeline/delivery/stream.py:73-75`（`_events_with_ping` 的 `finally`）与 `stream.py:88-91`（`stream_delivery` 的 docstring）。

`stream_delivery` 的 docstring 写着：

> Typed as a generator rather than a plain iterator so a caller that stops early can close it: abandoning it mid-stream otherwise leaves the upstream response open until the loop is collected.

这句话承诺：**调用方 `aclose()` 了，上游响应就会被关掉**。

**【实测】这个承诺不成立，而且失败得比「不确定」更彻底。** 探针 `/tmp/smell-probe/p4_midpull.py` 走的是客户端中途断连的形状——消费到第一个块的全部 4 帧，起一个 task 驱动第 5 次拉取让上游真正进入在途状态，取消该 task，然后 `await agen.aclose()`：

```
upstream reached the hang? -> True | waiter pending? True
right after aclose():  upstream closed? -> False
after 5 ticks:         upstream closed? -> False
tasks alive after aclose: [('Task-6', 'PENDING')]
after gc.collect():    upstream closed? -> False
tasks alive after gc:  [('Task-6', 'PENDING')]
```

上游生成器的 `finally` 从未运行，拉取 task 永远 PENDING，**连 GC 都收不掉**——因为 pending task 本身是 GC root，它强引用着那个 async generator 的栈帧。docstring 说「否则会开到循环回收为止」，实际是「即使你关了，它也开到循环回收为止，而且循环回收也收不掉」。

对照探针 `/tmp/smell-probe/p3_ownership2.py` 走的是「拉取不在途」的形状（消费完 4 帧就 `aclose`），结论稍轻但同样不满足承诺：`aclose()` 之后连转 5 轮，上游仍未关闭；只有 `gc.collect()` 之后才关。即**最好的情况下也是非确定性关闭，最坏的情况下是不关闭**。

作为正样本对照，同一形状打到 `session_liveness_stream` 上（`/tmp/smell-probe/p5_contrast.py`）：

```
upstream reached the hang? -> True
right after aclose():  upstream closed? -> True
tasks alive: []
```

确定性关闭，拉取 task 被取消并观测，没有残留。证明探针有分辨力，`stream_delivery` 那两组的 False 是真的 False。

**【读码】整条链上没有任何一层承担这件事**：`_AccountedStreamingResponse.__call__`（`pipeline_app.py:340-344`）的 `finally` 只调 `accounting.finish()`；`_tracked_delivery`（`pipeline_app.py:358-367`）的 `finally` 也只调 `accounting.finish()`，没有 `chunks.aclose()`；`_counted_upstream`（`pipeline_app.py:347-355`）是裸 `async for`；`read_events`（`sse_source.py:65-80`）也是裸 `async for`。所以从 Starlette 到 `response.aiter_bytes()` 之间，**没有一层持有关闭责任**。

**它具体会怎么伤人**：

1. 客户端中途断连（agent 类客户端上很常见，用户按 Esc 就是这个）时，httpx 的这个 response 不被关闭、连接不还池。长 thinking turn 里上游可能几十秒不发字节，这段时间该连接一直被占着。这不是猜测性的资源焦虑——p4 的实测里它是**无限期**的，只有上游自己吐字节或断链才解开。
2. **操作者看到的状态是错的**：`accounting.finish()` 照常执行，footer 里这条请求消失、完成日志照写，而上游连接还开着。「日志说结束了」与「连接还在」之间的这条缝，正是排查连接池耗尽时最难看见的一种。
3. 前一轮评审 §6 记的 `Task exception was never retrieved`，就是这条缝在 stderr 上的投影——那不是一条孤立的噪声，是同一个所有权空洞。
4. 下一个读 `stream_delivery` 的人会**相信那句 docstring**。它写得很自信，还解释了「为什么类型标注成 generator 而不是 iterator」，读起来像是深思熟虑过的契约。

补一句避免过度索赔：admission 的并发槽位（`server/admission.py:35` 的 `asyncio.Semaphore`）是 ASGI 中间件层释放的，ASGI 调用一返回就还，**不受此影响**。泄漏面限于 httpx 的 response 与其连接。

**建议的形状**：`finish_stream_cleanup`（`keepalive.py:69-115`）就是为这件事写的，已经被 `keepalive.py:56` 和 `sse.py:193` 两个模块复用，签名是 `(pending: Task[T] | None, stream: AsyncIterator[T], *, primary)`，与 `_events_with_ping` 手里的 `task` 和 `events` 恰好对得上。把 `stream.py:73-75` 换成 `sse.py:189-203` 那段完全相同的 `finally`，代码量大致持平，而且不需要新写任何原语。

**代价与风险**：这是**行为改变，不是重构**，需要用户裁决。

- 弃流时 pull 会被 `cancel()`，`read_events` 与 `_counted_upstream` 会收到 CancelledError 并解栈；`_counted_upstream` 里 `trace.received` 的最后一次累加可能就此丢掉（数值影响：最多一个 chunk）。
- 取消一个正在 `anext()` 的 async generator，会把 CancelledError 抛进它的栈帧。这条链上三层都是裸 `async for`，没有会吞掉它的 `except`，所以按现状是安全的；但这个安全性依赖于中间层不长出 `except Exception`。
- `finish_stream_cleanup` 的异常优先级协议（primary / cleanup_error / cleanup_cancellation 三者的排序）会一并进来。它有 10 个用例守着（见 S3），但那些用例守的是 `session_liveness_stream` 的调用姿态，不是 `stream_delivery` 的。

**推荐强度：强烈建议改。** 判据是实测 + 读码闭合，不是推断。但**具体改法要先裁决**：是采纳 `finish_stream_cleanup`，还是改 docstring 承认现状（后者是有可能的选择——如果确认「让 pull 自然收尾」才是想要的语义，那么该改的是那句话，以及 S2 那个假装在处理它的 `finally`）。这两条路我推荐前者，因为 docstring 已经把「上游还开着」写成了要避免的坏结果。

---

## S2 那个 `finally` 在所有可达路径上都是空操作

**位置**：`src/app/pipeline/delivery/stream.py:73-75`

```python
finally:
    if task.done() and not task.cancelled():
        task.exception()
```

**【实测】** `/tmp/smell-probe/p1_finally.py`：

```
A yielded value; _log_traceback after result(): 1 False
B StopAsyncIteration; _log_traceback after result() raised: False
   finally would then call exception(); already False -> False
```

`Future.result()` 与 `Future.exception()` 都会清掉 `__log_traceback`。而 `stream.py:66` 的 `yield task.result()` 在 `task.done()` 为真的**每一条**路径上都先跑过了——包括 `result()` 抛 `StopAsyncIteration` 那条（异常从 `result()` 里抛出，`__log_traceback` 已在抛出前清掉，随后被 `stream.py:71` 的 `except` 接住）。所以进到 `finally` 时，`task.exception()` 只是把一个已经是 `False` 的标志再置一次 `False`。

而 `task.done()` 为假的那条路径——也就是**弃流泄漏真正发生的那条**——被 `if task.done()` 直接跳过。

**它具体会怎么伤人**：这不是「多余的两行」，是**一个假装在场的守卫**。它的形状（`finally` + 取异常 + 排除 cancelled）精确地长得像「处理未被观测的 pull 异常」，位置也正好在被弃流的那个 task 旁边。下一个拿着 `Task exception was never retrieved` 来查 `stream.py` 的人，会读到这三行、认为已经处理过，然后去别处找——前一轮评审 §6 已经把这条噪声记在案，所以这个「下一个人」是可预期的，不是假想的。

顺带指出：这个 `finally` 挂在**外层** `while True` 的 try 上，所以它每交付一个事件就跑一次，而不是只在生成器退出时跑一次。这会加深「它是在做逐事件的清理」的误读。

**建议的形状**：随 S1 一起处置。如果 S1 采纳 `finish_stream_cleanup`，这三行被自然替换；如果 S1 裁决为「维持现状、改 docstring」，那这三行应该直接删掉，或者改写成真正覆盖 `not task.done()` 的形式。**不要单独保留它**——留着就是留一个会误导人的标志物。

**代价与风险**：极低。它是空操作，删除不改变任何可观察行为（p1 已证）。风险只在于「它是不是在防某个我没想到的路径」——我逐路径走过了 `stream.py:43-75` 的控制流，`task.done()` 为真的入口只有 `stream.py:65-67` 一处，而它必经 `result()`。

**推荐强度：强烈建议改。**

---

## S3 测试密度与生产暴露面倒挂

**【读码】** `rg` 全仓：`session_liveness_stream` 在 `src/` 下只被 `keepalive.py:170` 的 `keepalive_stream` 调用，而 `keepalive_stream` 在 `src/` 下**零调用方**（只有 `tests/` 引用）。也就是说这条链在生产里是空转的。`docs/tmp/verify-liveness.md:56` 早就记过这一点，`docs/tmp/260820-downstream-keepalive-defect.md:100` 也把它归到既有的「守卫被留在了 legacy 链路上」那一类。

而 `tests/unit/test_streaming_resilience.py` 的 20 个用例里，有 10 个专门守清理与取消语义：

```
test_keepalive_close_waits_for_upstream_cleanup
test_session_liveness_close_closes_upstream_iterator
test_session_liveness_cancellation_closes_upstream_iterator
test_session_liveness_second_cancellation_does_not_interrupt_cleanup
test_session_liveness_keeps_consumer_cancellation_primary_when_close_fails
test_session_liveness_chains_pull_unwind_failure_after_cancellation
test_session_liveness_keeps_upstream_error_primary_when_close_fails
test_session_liveness_propagates_close_error_without_primary_error
test_session_liveness_cancellation_observes_synchronously_completed_pull
test_session_liveness_does_not_count_downstream_pause_as_upstream_idle
```

对照 `tests/unit/test_stream_delivery.py` 的 19 个用例（这是主产品路径）：**没有一个**涉及关闭、取消、断连或上游清理。

**它具体会怎么伤人**：`test_session_liveness_close_closes_upstream_iterator` 是绿的，而 S1 的探针证明**同名的不变量在生产路径上是红的**。一份 1300+ 全绿的测试套件因此说了一句不真的话：「关闭时上游会被关掉」这个契约看起来被 10 个用例钉死了，实际上它钉的是没人跑的那一支。这与项目规则里记的那个教训同形——「streaming 在主路径上返回零字节而 1243 个测试全绿」。

**建议的形状**：不是删测试，也不是删 `keepalive.py`（memory 里有明确的「不得擅自删除已实现的功能」，孤儿模块可以留着）。建议是**把不变量搬到有人跑的那一侧**：给 `tests/unit/test_stream_delivery.py` 加一个断连用例，断言「`aclose()` 之后上游迭代器的 `finally` 跑过了」。S1 若被采纳，这个用例就是它的回归证据；S1 若被裁决为维持现状，这个用例应该断言现状（并在注释里写清「上游由谁关」），把当前的空契约变成被写下来的契约，而不是留成一句 docstring 里的空话。

**代价与风险**：一个用例的成本。风险是它会在 S1 裁决之前先把现状固化——所以顺序上应该 **S1 先裁决，再写这个用例**，否则会出现「测试固化了一个 docstring 明说是坏结果的行为」。

**推荐强度：建议改**（依赖 S1 的裁决结果，不宜先行）。

---

## S4 同一个「超时不取消 pull」循环两份实现，deadline 计算重复三处

先把委托里的假设精确化。**四个地方并不是同一个模式的四遍**：

| | `session_liveness_stream`<br>`keepalive.py:8-66` | `_events_with_ping`<br>`stream.py:28-75` | `next_chunk`<br>`sse.py:102-113` | `with_idle_timeout`<br>`idle_timeout.py:19-38` |
|---|---|---|---|---|
| 持有 pull | `create_task(next_item())` | `ensure_future(anext(events))` | `create_task(pull_chunk())` | 无，直接 await |
| 超时机制 | `asyncio.wait({pending}, timeout=)` | `asyncio.wait({task}, timeout=)` | **没有超时** | `anyio.fail_after` |
| 超时是否取消 pull | 否 | 否 | 不适用 | **是** |
| deadline 数量 | 2（heartbeat + idle），走 `_deadline`/`_next_timeout` | 2（ping + response-headers），内联 | 0 | 1，每项重置 |
| 超时时做什么 | `yield heartbeat`（一个 T 值） | `yield None`（哨兵） | 不适用 | `raise StreamIdleTimeoutError` |
| 退出清理 | `finish_stream_cleanup` | 空操作（见 S2） | `finish_stream_cleanup` | 无 |

**S11（误报）**：`sse.py` 的 `next_chunk` **没有超时**，它是 `await asyncio.shield(pending)` 加一个 `except CancelledError: raise`。它解决的是另一件事——「外层被取消时，别把这次拉取一起打死，让 `finally` 里的 `finish_stream_cleanup` 有序处置它」。所以它是「取消解耦」那一半，不是「超时切出去」那一半。把它算作第三遍实现会导致收敛设计错误。

**S10-c（记录备查）**：`with_idle_timeout` 的超时**会**取消 pull，且它是致命的（抛异常终止整条流），与保活的「切出去做点别的、回头继续等同一个 pull」语义相反。它不应该被收敛进同一原语。另外它只接在 legacy 链路（`routes/anthropic.py:221`）上，主链路 `pipeline_app.py` 没有任何上游 idle 超时——这一点 `docs/tmp/260820-downstream-keepalive-defect.md:100` 已记录，此处不重复展开。

**真正重复的是两处**：`session_liveness_stream` 与 `_events_with_ping`。而且重复得很近：

- `stream.py:45` 的 `loop.time() + interval if interval > 0 else None` 就是 `keepalive.py:139-145` 的 `_deadline()`。
- `stream.py:48-62` 那段列表推导加 `max(0.0, min(...) - loop.time())` 就是 `keepalive.py:148-155` 的 `_next_timeout()`——后者的签名是 `*deadlines: float | None`，**已经是可变参数**，天生就能接两个 deadline。
- `stream.py:68-69` 的 `ping_deadline = loop.time() + interval` 就是 `keepalive.py:47-48` 的 `heartbeat_deadline = now + heartbeat_interval_seconds`。
- 泛型上也对得上：`session_liveness_stream[T]` yield 的是 `T`，取 `T = SseEvent | None` 且 `heartbeat=None` 时，就是 `_events_with_ping` 的签名。

**语义差异只剩两条，且都不是本质的**：(a) `_events_with_ping` 的第二个 deadline 是**绝对**的（response-headers 那个，跨事件不重置），而 `session_liveness_stream` 的两个都随每次新建 pending 重置；(b) `session_liveness_stream` 的第二个 deadline 到点是 `raise`，`_events_with_ping` 的是 `yield`。

**它具体会怎么伤人**：漂移已经发生过，而且是可指认的。刚修的 shield 缺陷之所以只出现在 `_events_with_ping` 而不在 `session_liveness_stream`，正是因为后者一开始就用了 `asyncio.wait`——同一个 bug 在一份实现里被修好、在另一份里活了下来。修复的注释（`stream.py:63`）末尾自己写着「`session_liveness_stream` already waits this way」，等于承认了这一点。下一次同类漂移的候选也已经在案：`docs/tmp/260820-downstream-keepalive-defect.md` 那个 ping 节拍缺陷只存在于 `_events_with_ping`。

**建议的形状**：让 `session_liveness_stream` 成为唯一的原语，给它加一个可选的第二 deadline，形如 `extra_deadline: Callable[[], float | None]`（调用方返回下一个要醒来的绝对时刻，`None` 表示不需要），到点就 `yield heartbeat`。`_next_timeout` 已经能吃下它。`_events_with_ping` 随之收缩成一个薄壳：构造 `read_events(chunks)`，把 `extra_deadline` 接到调用方的判据上。

**代价与风险**：

- 收敛会顺带把 `finish_stream_cleanup` 带进主路径——那是 S1 想要的结果，但它**同时也是 S1 里那个需要裁决的行为改变**。所以 S4 与 S1 是同一个决定的两面，不应分别裁决。
- `session_liveness_stream` 的 `finally` 里那套异常优先级协议（`keepalive.py:50-66`）是本片代码里最难读的一段，收敛意味着主路径开始依赖它。这段有 10 个用例守着（S3），是资产不是负债，但它是**新的**依赖面。
- 风险最高的一点：`session_liveness_stream` 从未在生产流量上跑过（S3）。把主路径切到一个只有单测走过的实现上，比在原地改一行要重。若采纳，建议按项目的交付风格切成一小刀单独落地，而不是和 S1 的清理契约揉在一起。

**推荐强度：建议改**，但**不建议现在就动**——它的前置是 S1 的裁决，而且 `docs/tmp/260820-downstream-keepalive-defect.md` 第 7 节的三个待裁决点也会改动 `_events_with_ping` 的形状。合理的顺序是：先裁决 ping 节拍与清理契约，再一次性收敛，避免收敛完又拆开改。

---

## S5 `yield None` 哨兵 + `response_started` 双向读写

**位置**：`stream.py:48-70`（被调用方）与 `stream.py:108-122`（调用方）。

现状是：`_events_with_ping` 用同一个通道传两种东西——真事件（`SseEvent`）和「该做点什么了」（`None`）。而「该做的是哪件事」它不说，由调用方自己重算一遍：

```python
# stream.py:52-54，被调用方决定要不要把这个 deadline 算进等待
response_headers_deadline
if response_started is not None and not response_started.is_set()
else None
```

```python
# stream.py:109-113，调用方重算同一个判据来决定这个 None 是什么意思
if (
    response_headers_deadline is not None
    and not response_started.is_set()
    and asyncio.get_running_loop().time() >= response_headers_deadline
):
```

同一个三项合取写了两遍，读的是两次不同的 `loop.time()`，而 `response_started` 这个 `asyncio.Event` 由被调用方读（`:53`）、调用方写（`:114`、`:127`）。

先把两件事排除掉，免得夸大：(a) 这两处判据当前**不会**给出冲突结论，因为时间只会向前走，被调用方判「到点」之后调用方必然也判「到点」；(b) 委托里问「是不是把控制反转搞成了共享可变状态」——是，但它不是竞态：单线程 event loop，两个帧不会同时跑。**所以这不是正确性缺陷，是可读性与可改性的代价。**

**它具体会怎么伤人**（这一条有实证，不是设想）：

1. `asyncio.Event` 在这里**从未被 await**。全仓没有 `response_started.wait()`。一个 `Event` 出现在签名上，读代码的人必须先去搜一遍才能确定「没有谁在等它」，才敢把它当成一个布尔标志来推理。它承诺了一个不存在的同步点。
2. **更实的一条**：`docs/tmp/260820-downstream-keepalive-defect.md` 记的那个缺陷——ping 的倒计时挂在上游事件上、而不是挂在下游字节上——其处置（该文第 104 行）需要「在每次 yield 出真实下游内容时重置 `ping_deadline`」。但 `ping_deadline` 是**被调用方**的局部变量，而「是否 yield 出了真实下游内容」只有**调用方**知道（`stream.py:120-121` 的 `elif started`）。也就是说，这个哨兵通道的方向性正好挡在修复路径上：要修它，要么再加一个反向通道（第二个 `Event`？），要么把 deadline 的所有权搬到调用方。这就是这个形状真实的、已经发生的修改代价。
3. 附带一个当前就成立的浪费：`interval > 0` 而 `started` 为假、且合成 deadline 未到时，被调用方每隔 `interval` 秒醒来 yield 一个 `None`，调用方在 `stream.py:120` 的 `elif started` 处**原地丢掉**。功能上无害（这是「首块之前不发任何东西」的既定语义，`test_silence_before_the_first_block_produces_no_keep_alive` 守着），但读起来是「产生一个信号只为了扔掉」。

**建议的形状**：把 deadline 的所有权全部交给调用方，被调用方只负责「等 pull，最多等到你给的这个时刻」。具体：

- `_events_with_ping` 的参数从 `(interval, response_headers_deadline, response_started)` 变成一个 `next_wakeup: Callable[[], float | None]`，返回调用方希望被唤醒的下一个绝对时刻；
- 被调用方超时就 `yield None`，含义收窄成「你要的时刻到了，或者更早」；
- 调用方在一处、只在一处维护 ping deadline、合成 deadline 与 `started`，`asyncio.Event` 消失，判据只写一遍。

这个形状同时把 S5-2 那个修复代价消掉：ping deadline 移到调用方之后，「按下游字节重置」就是一行赋值。它也与 S4 的 `extra_deadline` 收敛方向一致——两者可以是同一次改动。

**代价与风险**：中等。`_events_with_ping` 的双层 `while` 会塌成单层（外层只是为了每个事件重建 task，`session_liveness_stream` 用 `pending is None` 判断做到了同样的事而只有一层），可读性净收益。风险在于这是主路径上的控制流重写，且 `docs/tmp/260820-downstream-keepalive-defect.md` 第 7 节的三个待裁决点会同时改动这里的语义——同样建议**裁决在前，重写在后**，否则会重写两遍。

**推荐强度：建议改**，前置同 S4。

---

## S6 三个 `started`，三种含义，一个词

**位置**：

- `stream.py:94` `started: bool` —— 「下游是否已经发出过 `message_start`」
- `stream.py:95` `response_started: asyncio.Event` —— 「合成计时器是否该停」
- `blocks.py:137` `DeliverySession.started` —— 「是否有块被释放过」

三者的翻转时机各不相同，而且**会真的分叉**：`stream.py:118` 在合成 `message_start` 时把局部 `started` 置真，此时一个块都没释放，`session.started` 仍为假。

**【读码】** `rg '\.started' src` 除 `blocks.py` 自身外零命中——`DeliverySession.started` 在整个 `src/` 里**没有任何读者**，只有 `tests/unit/test_block_delivery.py:92,102` 在读。而 `DeliverySession` 的 docstring（`blocks.py:130-133`）自称「The single downstream writer. Tracks whether the response has been opened.」——真正跟踪这件事并据此决定要不要发 `message_start` 的，是 `stream_delivery` 里那个同名局部变量。

**它具体会怎么伤人**：这片代码最近的两次事故都围着「响应算不算已经开始」打转（240 秒空文本块、合成 `message_start`）。三个同名不同义的标志，其中一个还自称是权威而实际无人读，意味着任何一次关于「响应开始」的推理都要先花力气确定在说哪一个。这是纯粹的阅读税，而收税的正好是最容易出事的那个话题。

**建议的形状**：改名，不删。局部 `started` → `preamble_sent`；`response_started` → `synthesis_armed` 或 `synthesis_deadline_cleared`；`DeliverySession.started` 保留（memory：「不得擅自删除已实现的功能」，且它有测试），但 docstring 应改成描述它实际的含义（「是否有块被释放过」），并注明当前唯一读者是测试。

**代价与风险**：低，纯改名 + 改注释。风险是 `DeliverySession.started` 是公开导出面的一部分（`pipeline/delivery/__init__.py`），改名会波及导出；建议只改前两个局部名和 docstring。

**推荐强度：记录备查。** 它不会让程序算错，代价全在读者身上；但如果 S1/S5 动了 `stream_delivery`，顺手改名的边际成本接近零。

---

## S7 `DeliverySession.start_response()` 无条件抛异常

**位置**：`src/app/pipeline/delivery/blocks.py:158-166`

```python
def start_response(self) -> None:
    """Open the downstream response explicitly.

    Refused before a block is ready.
    That is what keeps success headers from going out ahead of usable content.
    """
    if self.started:
        raise ResponseAlreadyStarted("response has already started")
    raise DeliveryError("cannot start the response before a complete block is ready")
```

两条分支都 `raise`，**没有成功路径**。docstring 第一句「Open the downstream response explicitly」描述的是一个不存在的能力；「Refused before a block is ready」暗示块就绪之后就不会被拒，而实际是块就绪之后换一条异常拒。

**【读码】** `src/` 下零调用方；唯一调用点是 `tests/unit/test_block_delivery.py:96`，而它断言的是**被拒**（`pytest.raises(DeliveryError, match="before a complete block")`）。所以这个方法目前的全部作用是给一个测试提供一条异常。

**它具体会怎么伤人**：一个方法名 + docstring 组成的假 API。将来有人要「显式开启响应」时会先找到它，读 docstring 认为路径存在，再读实现发现不存在，然后要判断这是缺失实现还是有意为之——而代码里没有任何一句话回答这个问题。

**建议的形状**：在 docstring 里直接写明它是一个**只会拒绝的守卫**，以及为什么存在（大概率是「显式开启这件事被裁决为不允许，留一个会说话的拒绝点，好过 `AttributeError`」）。如果确实是有意为之，一句话就能把它从「疑似未完成」变成「已裁决」。

**代价与风险**：注释级，无风险。

**推荐强度：记录备查。**

---

## S8 可观测性：先更正两条前提，再说真问题

### S12（误报）「asyncio 噪声直接落到 stderr，绕开了项目自己的日志层」

**【实测】不成立。** `/tmp/smell-probe/p6_logging.py` 在 `setup_logging()` 跑过之后触发一次 loop 级异常上报：

```
[....] 08:13:16 Task exception was never retrieved
future: <Task finished name='Task-2' coro=<boom() ...> exception=RuntimeError('upstream pull blew up')>
Traceback (most recent call last):
  File "/tmp/smell-probe/p6_logging.py", line 7, in boom
    raise RuntimeError("upstream pull blew up")
RuntimeError: upstream pull blew up
```

CPython 的 `default_exception_handler` 走的是 `logging.getLogger("asyncio").error(...)`，不是 `sys.stderr.write`。该 logger 没有自己的 handler、`propagate=True`、effective level 20，因此**会**冒泡到 `setup_logging` 装的那个 root handler，经 structlog 的 `ProcessorFormatter` 渲染出来。JSON 模式同样成立，输出是一条完整的 JSON 记录。

### 「有没有栈」

**【实测】有。** 上面文本模式里的 `Traceback ...` 三行是渲染出来的；JSON 模式里它落在 `"exception"` 字段。`ProcessorFormatter` 会把 `record.exc_info` 转成 `exception` 键，`_render_text`（`logging.py:85,90`）把它摘出来另起几行——这正是 `logging.py:84` 那条注释描述的行为，注释与代码一致。

> 注：这不与前一轮评审矛盾。评审引的是**生产日志原文**（两行、无栈），那是 `_log_on_exception` 构造的 context **不含** `'exception'` 之外的 traceback、且 `StopAsyncIteration` 的 `__traceback__` 极短所致；机制上栈是渲染的，只是那个特定异常几乎没有栈。

### 【读码】无 loop exception handler

`rg 'set_exception_handler' src` 零命中，只有 `tests/unit/test_stream_delivery.py:251` 在测试里装。因此 loop 级上报走的是 CPython 默认实现。**这不构成缺陷**（默认实现的输出是可用的），但它意味着这些行拿不到 request-id 之类的上下文——`merge_contextvars` 只能捞到 `call_soon` 那一刻复制的 context，而 `Future.__del__` 触发的那次是在 GC 的 context 里跑的，与请求无关。**代价**：这类噪声无法与某一条请求关联，排查时只能靠时间戳对齐。

### 真问题：foreign ERROR 记录被渲染成 `[....]`，且 level 被丢弃

**【实测】** 上面那条 `logger.error` 出来的行，前缀是 `[....]`，行内既没有 `level=error` 也没有 `logger=asyncio`。

**【读码】机制**：`_add_status_prefix`（`logging.py:24-35`）只认 `event_dict["status"]`，任何没有 `status` 字段的记录一律得到 `"[....]"`（`STATUS_PREFIXES` 里 `pending` 的那个）。而 `_render_text`（`logging.py:81`）显式 `event_dict.pop("level", None)`，注释（`logging.py:67`）解释道：「No level column: the fixed-width prefix already says whether this went well」。

这个推理对**本项目自己的**日志成立——它们都带 `status`。但对 **foreign 记录**（asyncio、httpx、httpcore、uvicorn、sqlite，任何用 stdlib logging 的库）不成立：它们没有 `status`，于是拿到 `[....]`，同时被摘掉了唯一还能表达严重性的 `level`。

**它具体会怎么伤人**：一条 `ERROR` 级的库异常，在文本模式下与「一条请求刚开始」的行长得一模一样（同一个 `[....]`，同一个 DIM 配色路径）。操作者扫日志时看不出它是错误；想 grep 也 grep 不到——文本模式里 `error` 这个词根本没被打印。第三方库的 WARNING 与 ERROR 在这里是不可区分的，而 `setup_logging` 刻意把 `httpx`/`httpcore`/`uvicorn` 抬到 WARNING（`logging.py:146-147`），正是为了「不是例行事情时还能透出来」——透出来了，但透成了 `[....]`。JSON 模式不受影响（`level` 字段仍在）。

**建议的形状**：`_add_status_prefix` 在没有 `status` 时回退到按 `level` 取前缀（`error`/`critical` → `[FAIL]`，`warning` → 一个新的 `[WARN]`，其余 → `[....]`）。这不与那条「不要 level 列」的注释冲突——它恰恰是在履行那条注释的承诺（前缀应当说明这件事顺不顺利），只是补上了 foreign 记录这一半。

**代价与风险**：低，改一个函数。风险是会改变现有日志的视觉形状，可能影响别处对输出的断言；需要跑一遍相关测试。

**推荐强度：记录备查。** 委托明确说明主会话正在同时排查这一点，本节只作只读观察，**未修改任何日志相关代码**。这条建议交给主会话决定是否与它正在做的事合并。

---

## S9 `StreamSettings` 的默认值与 config schema 互相矛盾

**位置**：`stream.py:21-25` vs `src/app/config/schema.py:192-194`

```python
# stream.py
class StreamSettings:
    sse_ping_interval: int = 15
    synthesized_response_headers_after_sec: int = 0     # 0 == 关闭
```

```python
# schema.py
buffer_cap_bytes: int = Field(default=16_777_216, ge=0)
synthesized_response_headers_after_sec: int = Field(default=240, ge=0)
sse_ping_interval: int = Field(default=15, ge=0)
```

同一个配置项有两个默认值：产品默认 **240 秒**，dataclass 默认 **0（关闭）**。`sse_ping_interval` 则两边都是 15——所以这不是「dataclass 一律不给默认值」的风格，而是一个项对上了、一个项没对上。

**它具体会怎么伤人**：`StreamSettings` 的默认值是**第二个**关于「合成延迟默认多久」的答案，而且答的是「不合成」。任何写 `StreamSettings()` 的代码（今天只有测试，明天可能是别的调用方）会拿到一个与产品行为相反的配置，且不会有任何报错。240 这个数字本身刚在 `docs/tmp/260820-empty-text-block-synthesis.md` 那条线上被反复讨论过，让它有两个来源是在给下一次讨论埋歧义。

**建议的形状**：要么让 dataclass 的默认值与 schema 对齐，要么去掉这两个字段的默认值让它们成为必填（构造点只有 `handler.py:361-369` 一处，加不了多少负担），要么在 dataclass 上写一句注释说明「这里的默认值是`关闭`，产品默认见 `schema.py`」。我倾向第二种：单一权威，且编译期就能发现漏传。

**代价与风险**：低。第二种会让所有 `StreamSettings(...)` 的构造点必须补全参数，测试里 `collect()` 已经全部显式传值，影响面很小。

**推荐强度：记录备查。**

---

## S10 杂项

**S10-a 类型不一致【记录备查】**：`_events_with_ping(interval: int)`（`stream.py:30`）与 `session_liveness_stream(heartbeat_interval_seconds: float)`（`keepalive.py:11`）是同一个量的两种类型。schema 那边是 `int`，所以 `int` 不算错；但如果按 S4 收敛，`int` 会被 `float` 吃掉，届时以 `float` 为准。代价：目前为零，只是收敛时的一个小摩擦点。

**S10-b `if not started: started = True`【记录备查】**：`stream.py:132-133`，在 `for chunk in _commit(...)` 的循环体里。等价于循环外一句 `started = True`（`_commit` 返回非空即意味着已开始）。写成条件赋值会让读者去找「这个条件在防什么」，而它不防什么。代价：几秒钟的阅读困惑，非常轻，仅在改动这一段时顺手处理。

**S10-c `with_idle_timeout` 是语义相反的第四变体【记录备查】**：见 S4 的表格。它的超时**会**取消 pull，是致命 deadline；且它对被包裹的 stream 没有关闭责任（靠外层 `passthrough_bytes` 的 `finally` 和 `cleanup=upstream.aclose` 兜）。**不应收敛进保活原语。** 另外它只接在 legacy 链路上、主链路无上游 idle 超时这件事，`docs/tmp/260820-downstream-keepalive-defect.md:100` 已记录并归入「守卫被留在了 legacy 链路上」，此处不重复提出。

**关于 magic number**：这一片没有找到值得报的裸魔数。`PING_FRAME`（`stream.py:18`）是命名常量；`interval`、`response_headers_deadline` 全部来自配置；`stream.py:59` 的 `max(0.0, ...)` 里的 `0.0` 是钳位下界，不是魔数。委托里列的这一项**判定为无发现**。

**关于「被同一份逻辑覆盖两遍的测试」**：逐条比对了 `test_stream_delivery.py`（19 个）与 `test_streaming_resilience.py`（20 个）的用例名与目标，**没有发现重复覆盖**——两组打的是两个不同的实现，这恰恰是 S3 说的问题（不是重复，是错位）。委托里的这一项也**判定为无发现**。

---

## 附：探针脚本与复现方式

全部在 `/tmp/smell-probe/`，仓库内未留任何临时文件。一律在仓库根目录发起并带 `PYTHONPATH=src`（在 `/tmp` 下直接 `uv run` 会选到另一个解释器，前一轮评审已记过这个坑）：

```
cd /home/xp/src/ghc-api-proxy-py && PYTHONPATH=src uv run python /tmp/smell-probe/<name>.py
```

| 脚本 | 验证的命题 | 结果 |
|---|---|---|
| `p1_finally.py` | `stream.py:73-75` 的 `finally` 是否有效 | 全路径空操作 |
| `p2_ownership.py` | `aclose()` 是否关上游（第一版，拉取不在途） | 需要 GC 才关 |
| `p3_ownership2.py` | 同上，分离「ticks 关的」与「GC 关的」 | 只有 GC 关 |
| `p4_midpull.py` | 拉取在途时 `aclose()`（断连形状） | **不关，task 永久 PENDING，GC 也收不掉** |
| `p5_contrast.py` | 同一形状打到 `session_liveness_stream` | 确定性关闭，无残留（正样本对照） |
| `p6_logging.py` | asyncio 噪声落在哪、有没有栈、前缀是什么 | 走项目日志层、有栈、前缀 `[....]`、level 被丢 |

`p5_contrast.py` 是本报告的正样本对照：它证明 p3/p4 观察到的 `False` 是真的，不是探针看不见。

---

## 交给主会话的裁决点

1. **S1 的方向**：采纳 `finish_stream_cleanup` 让主路径确定性关上游（会取消在途 pull），还是维持现状并改写 `stream.py:88-91` 那句 docstring？后者也是合法选择，但那样 S2 的三行必须删掉，且 S3 的新用例应固化现状。
2. **S4/S5 的时机**：收敛到单一原语这件事，与 `docs/tmp/260820-downstream-keepalive-defect.md` 第 7 节的三个待裁决点改的是同一片代码。建议先裁决 ping 节拍，再一次性收敛，否则会重写两遍。
3. **S8 的归属**：日志前缀那条建议与主会话正在排查的方向可能重叠，是否合并由主会话决定；本次未动任何日志代码。
