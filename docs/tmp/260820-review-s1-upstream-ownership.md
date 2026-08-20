# S1 独立核验：`stream_delivery` 上游所有权与关闭语义

评审对象：工作树未提交改动，`src/app/pipeline/delivery/stream.py`、`src/app/pipeline/delivery/sse_source.py`、`tests/unit/test_stream_delivery.py`
评审人：独立评审 subagent（asyncio 并发正确性）
日期：2026-08-20
基线 HEAD：`git show HEAD:` 版本，用于对照实验；实验脚本全部在 `/tmp/rev-s1/`
只读自证：评审结束时 `sha256sum --check /tmp/rev-s1/baseline.sha256` → 四个文件全部 `OK`，未对 `src/`、`tests/` 做任何修改；未执行任何 `git add/commit/stash/checkout/restore`。

---

## 结论

**VERDICT: pass，0 个 blocker。** 六条退出路径逐条实测全部正确关闭上游、零残留 task；异常优先级协议与 `keepalive.py:50-66`、`sse.py:189-203` 去注释后逐 token 一致；正常路径实测确认上游只会自然耗尽，从不收到 `CancelledError`，也不收到 `GeneratorExit`。两条新测试都有分辨力（对照 HEAD 源码实测真红），`asyncio.all_tasks()` 断言在 pytest-asyncio 下稳定。

发现分两类，都**不是本次改动引入的回归**，但都决定这次改动写下的承诺在生产里能兑现到哪一层：

| 编号 | 级别 | 一句话 |
|---|---|---|
| F1 | major（相邻缺陷，非本 patch 缺陷） | `_counted_upstream` 与 `_tracked_delivery` 各自都是裸 `async for`，都不关闭自己的源。生产交给 starlette 的 `body_iterator` 是 `_tracked_delivery`；关它**完全不会**触达上游，本次修好的确定性关闭在生产链路的两端各断了一次。 |
| F2 | minor（本 patch 引入） | 新的 `aclosing` 在 `loop.shutdown_asyncgens()` 时会多产生一条 `RuntimeError: aclose(): asynchronous generator is already running` 日志（基线 3 条 → 现在 4 条）。同一次实测里，改动**换来**的是上游在 `shutdown_asyncgens()` 返回时已经关闭（基线是没关）。净收益为正。 |
| F3 | minor（既有） | `_StreamAccounting.finish()` 读取 `trace.received` 之后，在途 pull 仍可能继续记账。实测漏报 105 B（分片 40 段）到 4209 B（整段一次到达）。与本次改动无关：基线数字逐位相同。 |
| F4 | minor（既有） | 从未被迭代过的 `stream_delivery`，`aclose()` 什么也不关——`response.aiter_bytes()` 连启动都没有。这正是 `_AccountedStreamingResponse` docstring 里描述的「首个 chunk 之前客户端就消失」那一幕，它盖住了记账，没盖住上游释放。 |
| F5 | 提示（既有） | 三处不变量（`task = None`、异常优先级尾巴、`primary=primary`）在本仓库现有测试下变异不红。同形代码在 `keepalive.py` 里被 `test_streaming_resilience.py` 5 条测试钉住，因此不建议为副本补测；仅记录「这份副本本身无独立防回归」。 |
| F6 | 提示（越界观察） | pipeline 链路（`pipeline_app.py:274`）没有接 `with_idle_timeout`，`StreamIdleTimeoutError` 在这条路上无法产生；idle timeout 目前只在 legacy 的 `routes/anthropic.py:221` 上。这与已记忆的「守卫被留在了 legacy 链路上」是同一形态，建议单独裁决，不属本次评审范围。 |

---

## 1. 退出路径穷举

脚本 `/tmp/rev-s1/e2_exit_paths.py`：把上游字节源包成一个记录它到底收到什么的 generator（`received:<异常类型>` / `exhausted` / `closed`），逐条驱动 `stream_delivery`，并在每条之后对比 `asyncio.all_tasks()` 快照。

```
normal end                             upstream=['exhausted', 'closed']                                      out=ok                     leaked_tasks=0
upstream raises                        upstream=['raising', 'received:RuntimeError', 'closed']               out=raised RuntimeError    leaked_tasks=0
upstream StreamIdleTimeoutError        upstream=['raising', 'received:StreamIdleTimeoutError', 'closed']     out=raised StreamIdleTimeoutError  leaked_tasks=0
consumer aclose (idle)                 upstream=['received:GeneratorExit', 'closed']                         out=ok                     leaked_tasks=0
consumer aclose (pull in flight)       upstream=['received:CancelledError', 'closed']                        out=ok                     leaked_tasks=0
consumer task cancelled in pull        upstream=['received:CancelledError', 'closed']                        out=ok                     leaked_tasks=0
cancelled during cleanup               upstream=['received:GeneratorExit', 'closing-slowly', 'closed', 'closer-cancelled'] out=ok  leaked_tasks=0
```

七条路径全部：上游 `finally` 执行、零残留 task、原异常按预期继续传播。要点逐条：

**`task = None` 的置位时机正确，没有漏、也没有误取消。** `stream.py:77` 是唯一一处把 `task` 置 None 的地方，且紧接在 `task.result()` 成功返回之后（`stream.py:72-78`）。因此 `task is None` ⟺ 没有在途 pull，是一个真不变量：

- 唯一另一条能带着非 None 的 `task` 进入 `finally` 的正常出口是 `stream.py:74-75` 的 `return`（end-of-stream）。此时 `task` 是**已完成**的那个，`_cancel_and_observe`（`keepalive.py:120`）先判 `pending.done()` 才决定要不要 `cancel()`，所以不会取消它，只 `await` 观测，`StopAsyncIteration` 被吞掉返回 `None`。上表第一行 `upstream=['exhausted','closed']` 就是这条：没有 `received:` 记录，说明上游根本没收到任何异常。
- 从 `task = None`（第 48 行）到第一次 `ensure_future`（第 51 行）之间没有 await 点（`read_events(...).__aiter__()` 与 `get_running_loop()` 都是同步的），所以不存在「已经有 pull 在途但 `task` 还是 None」的窗口。
- 内层 `while` 的 ping 分支（`stream.py:82` 的 `yield None`）是**带着在途 pull** 挂起的——这是唯一一个消费者走开就要取消 pull 的位置，取消是必需的而非可选：`aclose()` 撞上在途 `anext` 会直接 `RuntimeError`（见第 5 节实测复现）。

**「清理进行中再次被取消」单独加测**（`/tmp/rev-s1/e12_double_cancel.py`，上游的 `finally` 里放一个 0.15s 的 shielded 清理）：

```
cancels=1: closer -> CancelledError   upstream=['received:CancelledError', 'closing', 'closed']
cancels=2: closer -> CancelledError   upstream=['received:CancelledError', 'closing', 'closed']
cancels=4: closer -> CancelledError   upstream=['received:CancelledError', 'closing', 'closed']
```

反复取消（1/2/4 次）都没有出现 `close-INTERRUPTED`，清理跑完，取消本身仍作为最终结果保留。`finish_stream_cleanup` 的 `shield` + `cancelling()` 计数（`keepalive.py:97-107`）在这份副本上行为与 `keepalive.py` 一致。

---

## 2. 异常优先级协议：逐字比对 + 语义实测

**文本层面：三份一致。** 去掉注释与缩进后逐 token 比较 `keepalive.py:50-66`、`sse.py:189-203`、`stream.py:83-99`，仅变量名不同（`pending, stream` / `pending, body_iterator` / `task, events`）：

```
keepalive vs sse   : IDENTICAL
keepalive vs stream: IDENTICAL
```

（脚本见本次会话中执行的 `difflib` 比对；三份的 `primary = sys.exception()` / `isinstance(primary, GeneratorExit)` / 三段 raise 分支完全一致。）

**语义层面：你问的那个具体风险不存在，已实测。** `/tmp/rev-s1/e1_semantics.py`（Python 3.14.2）：

```
A sys.exception() on the StopAsyncIteration-return path: [('A', 'None')]
B aclose() raised: ValueError cleanup failure
B2 aclose() raised: ValueError cleanup failure after awaiting
B3 aclose() raised: RuntimeError async generator ignored GeneratorExit
C aclose() raised: RuntimeError RuntimeError('async generator raised StopAsyncIteration')
D sys.exception() in finally: CancelledError()
```

- **B / B2**：从一个正在被 `aclose()` 关闭的 async generator 的 `finally` 里 `raise` 一个非 `GeneratorExit` 异常 → 该异常原样从 `aclose()` 抛出，**不会**触发 `async generator ignored GeneratorExit`。B2 进一步确认：先 `await`、再 `create_task` + `shield`、最后 raise，行为不变。这正是 `stream.py:94-99` 三条 raise 分支所处的情形，安全。
- **B3**：只有在 `finally` 里 `yield` 才会触发 `RuntimeError: async generator ignored GeneratorExit`。新代码的 `finally` 里没有 yield。
- **A**：`return` 是从 `except StopAsyncIteration:` 块内部发出的（`stream.py:74-75`），进入外层 `finally` 时 `sys.exception()` 已经是 `None`。所以 `primary` 不会是 `StopAsyncIteration`，也就不会走到「把 StopAsyncIteration 从 generator 里 raise 出去」的 C 场景（那会变成 `RuntimeError: async generator raised StopAsyncIteration`）。**这一点是隐性依赖，代码里没有注释说明**——建议在 `stream.py:86` 那行旁补一句「此处 `sys.exception()` 在 end-of-stream 路径上是 None，因为 `return` 出自 except 块」，否则将来有人把 `return` 挪出 except 块就会静默变成 C。
- 另一层保险：`_cancel_and_observe`（`keepalive.py:127-128`）对 `StopAsyncIteration` 显式返回 `None`，所以 `cleanup_error` 也不可能是 `StopAsyncIteration`。

---

## 3. 正常路径是否真的从不取消（用户最关心的点）

`/tmp/rev-s1/e9_normal_path.py`：三个块（`alpha`/`beta`/`gamma`）、真实产生 ping、自然收尾，断言上游既没收到 `CancelledError` 也没收到 `GeneratorExit`，且第一条记录必须是 `exhausted-naturally`。

```
no ping, no gap             : pings=0  frames=12 upstream=['exhausted-naturally', 'finally-ran']
ping interval 0.05, gap 0.12: pings=16 frames=28 upstream=['exhausted-naturally', 'finally-ran']
ping interval 1s, gap 1.2s  : pings=8  frames=20 upstream=['exhausted-naturally', 'finally-ran']
```

三种配置下的非 ping 事件序列逐字相同：`message_start / (content_block_start, delta, stop) × 3 / message_delta / message_stop`。三条断言全过。

结论强度：**足以据此行动**。三次运行覆盖「没有 ping」「大量 ping（16 次）」「生产形状的 1 秒 ping（8 次）」，全部是自然耗尽路径，取消一次都没有发生。机制上的理由与 e2 第一行一致：正常收尾时 `task` 是已完成的那个，`_cancel_and_observe` 的 `if not pending.done(): pending.cancel()` 直接短路。

需要如实说明的边界：`StreamSettings.sse_ping_interval` 声明是 `int`，我在 0.05 那一档传了 float。它只参与 `loop.time() + interval` 与 `min()` 的算术，行为等价，只是缩短等待；第三档用的是生产形状的整数 `1`，结论不依赖 float 那一档。

---

## 4. 双重关闭与调用方冲突

### 4.1 重复 `aclose()` 安全

`/tmp/rev-s1/e3_production_chain.py`：走完一条完整正常流后连调两次 `aclose()`，最内层字节源的 `finally` 计数保持 `closes=1`。async generator 的 `aclose()` 对已关闭对象是幂等 no-op。cancel 路径同理：取消沿帧向内传播时上游已经关了一次，随后 `read_events` 的 `finally` 再调 `chunks.aclose()` 命中的是已关闭对象。**无双重关闭问题。**

### 4.2 但 `chunks` 还有别的「本该关而不关」的调用方——这是 F1

`/tmp/rev-s1/e7_layer_isolation.py` 把三层分别隔离出来，各自 `aclose()` 后立刻检查它的源关了没有：

```
read_events (patched)      immediately after aclose(): ['received:GeneratorExit', 'closed']
_counted_upstream          immediately after aclose(): []
                           after del+gc+sleep:        ['received:GeneratorExit', 'closed']
_tracked_delivery          immediately after aclose(): []
                           after del+gc+sleep:        ['received:GeneratorExit', 'closed']
```

- `read_events`（本次修的）：同步关闭自己的源。✅
- `_counted_upstream`（`pipeline_app.py:352-355`，裸 `async for`）：**不关**，交给 GC。
- `_tracked_delivery`（`pipeline_app.py:363-367`，裸 `async for`）：**不关**，交给 GC。

整链验证 `/tmp/rev-s1/e5_outer_layer2.py`（消费者停在一个 ping 帧上，此时有在途 pull）：

```
[close stream_delivery directly]:                        after aclose() returned -> upstream=['received:CancelledError', 'closed']  pending_tasks 1 -> 0
[close _tracked_delivery (production body_iterator)]:    after aclose() returned -> upstream=[]                                     pending_tasks 1 -> 1
    upstream closed only after 1 gc+sleep rounds
```

也就是说：**这次修好的确定性，止步于 `stream_delivery` 自己**。生产交给 starlette 的对象是 `_tracked_delivery`（`pipeline_app.py:271-282`），关它在返回时上游一个字节都没释放、在途 pull 仍然 pending，要等 GC。这与新写进 `sse_source.py:69` 的那句「That is the difference between an upstream HTTP response released at the moment the client goes away and one released a few ticks later」是同一件事，只是发生在上面两层。

**实际严重性评估（重要，不要按最坏读）：** 生产里的客户端断连**不走 `aclose()`**。已核实的链路：uvicorn 声明 `spec_version = "2.3"`（`uvicorn/protocols/http/h11_impl.py:205`、`httptools_impl.py:227`），starlette 0.52.1 因此走 `responses.py:268-277` 的 anyio task-group 分支，断连时 `cancel_scope.cancel()` 取消 `stream_response` 任务；starlette 全程**从不**调用 `body_iterator.aclose()`（`responses.py:245-258` 可读，没有这一步）。取消发生在两种位置：

- (a) 阻塞在 `anext(body_iterator)`（模型在思考、长时间没有块可发——正是本次要修的那一幕）：`CancelledError` 直达 `_events_with_ping` 的 `asyncio.wait`，各层帧依次展开，上游同步关闭。`/tmp/rev-s1/e3_production_chain.py` 实测 `cancel-in-pull, no aclose(): closes=1 ticks_after_cancel=1`。**这条路径本次改动是真正生效的**（基线上这里会把 pull 永久留在 pending）。
- (b) 阻塞在 `send(...)`（下游 socket 写不动）：整条 generator 链停在各自的 yield 上，没有任何人取消或关闭，只能等 GC。这条路径上 F1 才起作用，但它同时也是 `_tracked_delivery` 与 `_counted_upstream` 的问题，不是本 patch 能单独解决的。

所以 F1 的定性是：**不是回归，不阻塞落地**；它说明「aclose() 返回即释放」这个不变量目前只覆盖到中间一层，如果将来有人依赖它（例如把 `_AccountedStreamingResponse` 换成会 `aclose()` 的实现，或换用 `DelayedStartStreamingResponse`——后者在 `sse.py:193` 确实会关 `body_iterator`），就必须同时把 `_counted_upstream` 和 `_tracked_delivery` 改成同样形状（各自加 `try/finally` 关自己的源，或用 `aclosing`）。建议记入 `docs/tmp/` 的后续项，不建议在本 patch 里顺手改——那两个文件属于 `pipeline_app.py`，与并行会话的活跃改动同一批文件。

### 4.3 `trace.received` 在取消路径上到底丢多少：给数字

`/tmp/rev-s1/e10_byte_count.py`，构造「`finish()` 已经读走 `trace.received` 之后，在途 pull 才把剩下的字节吃进来」的窗口：

```
split_into=  1 release_before_close=False tail_bytes= 4209 finish()_saw=[214] final=4423 lost_from_the_log_line=4209
split_into=  1 release_before_close=True  tail_bytes= 4209 finish()_saw=[214] final=4423 lost_from_the_log_line=4209
split_into= 40 release_before_close=True  tail_bytes= 4209 finish()_saw=[214] final= 319 lost_from_the_log_line= 105
```

准确的说法不是「`trace.received` 丢字节」，而是**完成日志行少报**：`_StreamAccounting.finish()`（`pipeline_app.py:325`）把 `bytes_out=self.trace.received` 取快照，之后 `trace.received` 还会继续涨。少报量 = 在途 pull 被结算之前还能消费掉的上游字节数：

- 上游把剩余部分**一次读回**（`split_into=1`）：少报 **4209 B**，即整个剩余块。
- 上游分成 ~105 B 的片（`split_into=40`）：少报 **105 B**，恰好一个上游 chunk——pull 恢复消费一片后就被取消掉了。
- 上限不是「一个 chunk」，而是「凑齐下一个完整 SSE frame 所需的全部字节」。httpcore 单次 socket read 上限 64 KiB，所以最坏一次可以是数十 KiB。

**这不是本次改动引入的。** 同一脚本对 HEAD 基线（`/tmp/rev-s1/e10_base.py`，`PYTHONPATH=/tmp/rev-s1/base`）跑出**逐位相同**的三行。

主导的生产路径（4.2 的 (a)，取消从内向外展开）上 `_tracked_delivery` 的 `finally` 最后才跑，实测 `delta=0`（`e3_production_chain.py` 的 `bytes-after-finish` 一行）。

---

## 5. 死锁 / 挂起风险：`create_task` + `await` 发生在 `aclose()` 期间

三个场景实测（`/tmp/rev-s1/e8_loop_shutdown.py`）：

**(1) `asyncio.run()` 收尾时的 `shutdown_asyncgens`（uvicorn 的实际形状）：不挂起，且比基线更好，但多一条日志。**

改动后：
```
an error occurred during closing of asynchronous generator <... read_events ...>      RuntimeError: aclose(): asynchronous generator is already running
an error occurred during closing of asynchronous generator <... raw ...>              RuntimeError: 同上
an error occurred during closing of asynchronous generator <... _counted_upstream ...> RuntimeError: 同上
an error occurred during closing of asynchronous generator <... stream_delivery ...>
  Traceback ... File "src/app/pipeline/delivery/stream.py", line 125, in stream_delivery
      async with aclosing(...)
    File ".../contextlib.py", line 390, in __aexit__
      await self.thing.aclose()
  RuntimeError: aclose(): asynchronous generator is already running
after explicit shutdown_asyncgens(): ['received:CancelledError', 'closed']
```

基线（`/tmp/rev-s1/e8_base.py`）：
```
（前三条同样的 RuntimeError，没有第四条）
after explicit shutdown_asyncgens(): []
```

读法：`shutdown_asyncgens()` 会**并发**对所有存活 asyncgen 调 `aclose()`。`stream_delivery` 的 `aclosing.__aexit__` 去关 `_events_with_ping` 时，后者已经被 `shutdown_asyncgens` 自己关上了，于是撞出第四条 `already running`。代价是一条日志；换来的是上游在 `shutdown_asyncgens()` **返回时**已经关闭（基线要拖到 `asyncio.run()` 之后）。两次运行都 `exit=0`，**没有挂起，没有丢清理**。

净判断：可以接受，**不建议**用 `with suppress(RuntimeError)` 去消音——那会把真正的「在途 pull 上误调 aclose」这类 bug 一起吞掉。但既然本仓库在 `stream.py:69` 明确为了消除同类 stderr 噪音而选择了 `asyncio.wait` 而非 `wait_for(shield(...))`，这条新增噪音应当被显式记录并交由用户裁决（每次带活跃流的优雅停机都会出现一次）。

**(2) `loop.close()` 之后再 `aclose()`：报错，不挂起。** `RuntimeError: Event loop is closed`（来自 `finish_stream_cleanup` 的 `create_task`），随后一条 `Task was destroyed but it is pending!`。这是构造出来的病态场景（`asyncio.run` 保证 `shutdown_asyncgens` 早于 `loop.close()`），且同样的 `create_task` 模式在 `sse.py:193` 与 `keepalive.py:56` 已经在生产里跑着。记录，不作为发现。

**(3) 被抛弃后由 GC finalizer 关闭：正常。** `/tmp/rev-s1/e5_outer_layer2.py` 的第二行——1 轮 `gc.collect()+sleep` 后上游收到 `CancelledError` 并关闭，无残留 task、无异常日志。`src/app/lifecycle/standalone.py` 没有自管事件循环（`rg 'shutdown_asyncgens|asyncio.run|loop.close' src/` 在 `src/` 下零命中），所以生产上的循环收尾就是 uvicorn 的 `asyncio.run`，即场景 (1)。

**(4) 顺带记录的既有洞（F4）：** `/tmp/rev-s1/e11_never_iterated.py` —— 对一个**从未被迭代过**的 `stream_delivery` 调 `aclose()`：`upstream started=[] closed=[]`。generator 没有挂起的帧，`aclose()` 什么也不跑，`response.aiter_bytes()` 连启动都没有，上游响应不释放。`_AccountedStreamingResponse` 的 docstring（`pipeline_app.py:331`）已经描述过这一幕并为**记账**兜了底，但没有为**上游释放**兜底。既有问题，与本次改动无关。

---

## 6. 两条新测试的质量

### 6.1 分辨力：对照 HEAD 源码实测真红

不修改仓库，改为把 HEAD 版本的两个文件铺到 `/tmp/rev-s1/`，用 `PYTHONPATH` 前置覆盖：

```
PYTHONPATH=/tmp/rev-s1/base   → 2 failed, 20 passed    （两条新测试都红，其余全绿）
PYTHONPATH=/tmp/rev-s1/varA   → 1 failed, 21 passed    （varA = 新 stream.py + 旧 sse_source.py）
PYTHONPATH=/tmp/rev-s1/varB   → 2 failed, 20 passed    （varB = 旧 stream.py + 新 sse_source.py）
```

读法：

- `test_closing_the_delivery_closes_the_upstream_under_it` 同时钉住两处改动——只要 `read_events` 的 `finally` 不在（varA），它就红。**这是唯一钉住 `sse_source.py` 改动的测试**，不能删。
- `test_a_pull_in_flight_does_not_outlive_the_delivery` 只钉住 `stream.py`（varA 下它是绿的）。合理：在途 pull 被取消时异常沿帧展开，不需要 `read_events` 的 `finally` 参与。
- 没有出现「改动没被任何测试钉住」的情况。

### 6.2 `asyncio.all_tasks()` 那条断言稳定，不会因别的测试残留而偶发

三个理由，都可直接核对：

1. `asyncio.all_tasks()` 只返回**当前运行循环**里**尚未完成**的 task。pytest-asyncio 默认 function-scope event loop，每个测试一个新循环，跨测试的残留 task 不在这个循环里。
2. 测试自己做了差集 `- before`（`test_stream_delivery.py:497`），`before` 在 `pump` 创建之前取快照，同循环里任何 fixture 起的后台 task 都会落进 `before` 被减掉。
3. `pump` 在断言前已经 `cancel()` + `await`（`suppress(CancelledError)`），是 done 状态，不在 `all_tasks()` 里。

我用 `--ignore=tests/tui --deselect tests/unit/test_debug_models.py` 跑整仓，`1347 passed, 2 skipped, 35 deselected in 110.03s`，两条新测试稳定通过。

**关于你报的 1382：** 当前工作树上整仓是 `1 failed, 627 passed`（`-x` 提前停），失败的是 `tests/unit/test_debug_models.py::test_the_recorded_catalog_capture_reads_end_to_end`（`KeyError: 'data'`）。这是并行会话在 `src/app/model_provider/`、`src/app/debug/models.py` 上的在途改动，与 S1 无关（该测试不 import delivery 任何模块）。排除该文件后 1347 + 35 deselected = 1382，与你的数字自洽。`ruff check` 与 `pyright` 对三个改动文件均 clean（复核过）。

### 6.3 更该钉住而没钉的不变量

按重要性排：

1. **「正常路径从不取消上游」——用户最关心的那条，没有任何测试钉它。** 现有测试全部只断言输出字节；把 `finish_stream_cleanup` 改成无条件取消，输出字节一模一样，全仓仍然绿。我在第 3 节用 `/tmp/rev-s1/e9_normal_path.py` 实测了它，但那是一次性探针。**这是我唯一会主动建议补的一条测试**：驱动一条完整正常流（含 ping），断言上游 generator 只记录到自然耗尽，没有 `received:CancelledError`。断言形状可以直接抄 `_recorded_feed` 的 `closed: list` 手法，改成记录异常类型。
2. **ping 分支上关闭（带在途 pull 的 `yield None`）** 没有测试覆盖。`test_a_pull_in_flight_does_not_outlive_the_delivery` 用的是 `sse_ping_interval=0`，走的是「消费者 task 被取消」而非「消费者在 ping 处 aclose」。两者在 `_events_with_ping` 里是不同的进入点（`asyncio.wait` 处收异常 vs `yield None` 处收 GeneratorExit）。我在 `/tmp/rev-s1/e5_outer_layer2.py` 覆盖了它，结论正常；补不补取决于 ROI，我倾向于不补。
3. **F5：三处变异不红。** `/tmp/rev-s1/D1|D2|D3` 分别删掉 `task = None`（`stream.py:77`）、删掉整段异常优先级尾巴（`stream.py:92-99`）、把 `primary=primary` 改成 `primary=None`，三个变体跑 `test_stream_delivery.py + test_sse_assembly.py` 都是 `43 passed`。
   - 这**不构成缺陷**：同形代码在 `keepalive.py:50-66` 被 `tests/unit/test_streaming_resilience.py` 的 5 条测试钉死（`test_session_liveness_second_cancellation_does_not_interrupt_cleanup`、`..._keeps_consumer_cancellation_primary_when_close_fails`、`..._chains_pull_unwind_failure_after_cancellation`、`..._keeps_upstream_error_primary_when_close_fails`、`..._propagates_close_error_without_primary_error`），协议语义有权威覆盖。按本项目「不预建完整状态空间」的规矩，我**不建议**为副本再抄五条。
   - 顺带一个事实澄清：`task = None`（`stream.py:77`）对正确性**不是必需的**——即使不置 None，`finish_stream_cleanup` 拿到的是已完成 task，`_cancel_and_observe` 也不会取消它。它的价值是让「`task` 非 None ⟺ pull 在途」成为一个可读的不变量，值得保留，但它旁边那句注释把它写得像是防止误取消的必要条件，略微夸大了。

---

## 附：实验脚本清单（全部在 `/tmp/rev-s1/`）

| 文件 | 回答的问题 |
|---|---|
| `e1_semantics.py` | `sys.exception()` / 从 `aclose()` 中的 finally raise / ignored GeneratorExit 的语言语义 |
| `e2_exit_paths.py` | 七条退出路径的上游收到什么、残留 task 多少 |
| `e3_production_chain.py` | 生产接线下的重复关闭、cancel-in-pull、finish() 后的字节漂移 |
| `e4_outer_layer.py` / `e5_outer_layer2.py` | 关外层 generator 能不能触达上游（F1） |
| `e6_idle_close.py` / `e7_layer_isolation.py` | 逐层隔离：谁关自己的源，谁不关 |
| `e8_loop_shutdown.py` / `e8_base.py` | `shutdown_asyncgens` / 循环已关 场景，及与基线对照 |
| `e9_normal_path.py` | 正常路径（含真实 ping）绝不取消上游 |
| `e10_byte_count.py` / `e10_base.py` | `trace.received` 少报的具体字节数，及与基线对照 |
| `e11_never_iterated.py` | 从未迭代的 delivery，aclose() 关不关上游 |
| `e12_double_cancel.py` | 清理进行中反复取消 |
| `base/` `varA/` `varB/` `D1/` `D2/` `D3/` | 对照与变异用的 src 副本（均在 /tmp，仓库未被触碰） |

---

## 更正（2026-08-20 追加，由主会话补测）

**第 5 节 F2「改动新增一条 `shutdown_asyncgens` 噪声（基线 3 条 → 改动后 4 条）」不再成立。**

该测量是在主会话补上 `_AccountedStreamingResponse` 关闭 body（F2 修复，提交 `926cabf`）**之前**做的。补上之后重测 `/tmp/rev-s1/e8_loop_shutdown.py` 的三种模式、各 3 次，并对基线快照做同样测量：

```
              基线    当前
abandon        1       1
explicit       4       4      ← uvicorn 优雅停机的形状
closed-loop    0       0
```

**增量为零。** 该改动不新增停机噪声，原报告据此交回用户的「接受还是消音」裁决点随之作废。

报告其余内容未改动。此处只追加时间点与更正，不修改原结论文字。
