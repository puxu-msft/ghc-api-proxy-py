# `3160285` asyncio 控制流与清理语义复评

## 结论

**needs-fix，当前 HEAD `3160285` 不能作为 delivery keep-alive 候选合入。** `97d805e` 的 post-yield 打戳与两条异常／取消测试正确，`3160285` 合并 `client_has_bytes` 门的修复也正确且应保留；但复评忙等状态时找到一个仍在当前实现中的 blocker：deadline 到期后，只要 upstream pull 每轮都立即完成，`:83-85` 的 `task.done()` 分支就永远抢在 deadline 分支之前。此后 `timeout` 可以连续为 0，却一次也不执行 `:86-88`，所以 ping deadline 不前推、`None` 不产出、客户端保活仍可被持续就绪的上游事件无限饿死。

这项 blocker 不是 `3160285` 新引入的，而是 `a374f39` 没有覆盖完的同一缺陷族；但它直接推翻本 feature 的核心判据和本轮要求确认的“没有 timeout 恒为 0 的路径”，不能因属于父提交而降级。`3160285` 的单门修复本身不应回退；修复 B-1 后再复评即可。

证据强度：**高，强到足以阻止当前候选合入**。构造使用生产 `stream_delivery`、合法配置 `sse_ping_interval=1`、真实 `AnthropicAssembler` 与 `BlockBuffer(policy="block")`，没有 fake clock；持续就绪源运行 10.46s，产生 173125 次 `timeout == 0` 且每次 task 已完成，最终 ping 数仍为 0。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`3160285dff1e325427aff018cc815f8629fe8d41`
- 第一轮候选：`a374f3950bdd61552bbbb953d42dbecfb78f32a2`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### B-1：持续就绪的 upstream task 永远抢先于已到期 deadline，保活仍会被饿死

- 严重度：**blocker**
- 把握程度：**高；生产函数、合法配置、可重复计数**
- 位置：`src/app/pipeline/delivery/stream.py:76-88`。

当前顺序是：

```python
await asyncio.wait({task}, timeout=timeout)
if task.done():
    yield task.result()
    break
if ping_deadline is not None and loop.time() >= ping_deadline:
    ping_deadline = loop.time() + interval
yield None
```

当上游有一长串立即可取的事件时，deadline 到期前每轮 task 都先完成；deadline 到期后，`timeout` 被钳为 0，但新建 task 在 `asyncio.wait(..., timeout=0)` 的调度轮中也完成，于是 `task.done()` 仍为真。代码交付事件后 `break`，没有前推已经过期的 ping deadline。下一 pull 重复同一状态，因此 timeout 恒为 0，但不是无限快速 `yield None`，而是无限快速交付 upstream event；客户端在未闭合块期间仍收不到任何字节。

构造 `/tmp/probe_ready_upstream_ping_starvation.py`：先闭合一个块，使客户端已有字节；再开启第二个块并同步产出 200000 个 delta，始终不闭合。每个 delta 是合法 upstream SSE event，assembler 因块未闭合而不向客户端产出内容。探针对 `asyncio.wait` 只做计数，不改变其结果。

```text
$ uv run python /tmp/probe_ready_upstream_ping_starvation.py
{'deltas': 200000, 'elapsed_seconds': 10.456148108991329, 'ping_count': 0, 'chunks_out': 6, 'zero_timeouts': 173125, 'zero_timeouts_with_done_task': 173125}
```

客户端在首块后静默约 10s，而配置 interval 为 1s；173125 次已到期机会全部被 `task.done()` 优先级吃掉。`chunks_out=6` 是首块与流结束后的 terminal frames，不含 ping。

这个构造不是“event loop 被一段不让出控制权的同步函数卡住”：实现每个 event 都创建 task 并 `await asyncio.wait`，event loop 有调度点；失败来自调度点之后显式选择 `task.done()` 优先。真实 `read_events` 也可以从已经缓冲的 chunk 连续同步 yield 多个 frame，因此这个状态在生产解析层可达。

修复判据而非指定实现：deadline 已到期时，代码必须在继续拉取／交付任意数量的立即就绪事件之间安排一次对应的 `None`，同时仍要正确处理已经完成为 `StopAsyncIteration` 或异常的 task，避免在真正 EOF 前凭空发 ping。一个可考虑的结构是在成功交付一个 event、准备创建下一 pull 之前先结算已到期 deadline；具体异常优先级需实现后独立验证。

## 1. 门合并后的忙等穷举

排除 B-1 后，`client_has_bytes` 的 false→true 转换本身没有引入新的 `yield None` busy loop。

### `client_has_bytes` 为 false

- ping disabled、synthesis disabled：没有 deadline，等待 task。
- ping enabled、synthesis disabled：ping 到期时若 task 未完成，`:86-87` 先把 raw ping deadline 前推，再 yield `None`；`_deliver` 因 client 尚无字节而吞掉它。下一 timeout 在未来，不会空转。
- ping disabled、synthesis enabled：header deadline 到期且 task 未完成时，`_deliver:160-169` 在 outward yield `message_start` **之前**执行 `client_has_bytes.set()`。inner 在 outward yield 期间暂停；下次回到 `_events_with_ping` 时，`:70-72` 已将 header deadline 排除。
- ping 与 synthesis 都 enabled：先到的 ping 按上一条前推；synthesis 到期时 event 单调置位。二者同时到期时 raw ping deadline 与门都发生状态转换。

### `client_has_bytes` 为 true

header deadline 永久退出候选集。ping enabled 时只剩有效 ping deadline；disabled 时没有 deadline。该 Event 从不 clear，因此不存在 header deadline 重新进入候选集的路径。

短 interval 实测再次确认正常分支：

```text
direct_ping_only: 约 21.9、42.7、63.5、84.2、104.8ms，各次有间隔
ping_before_synthesis: message_start 约 57.0ms；随后 ping 约 77.7、98.5、119.3ms
synthesis_before_ping: message_start 约 21.2ms；随后 ping 约 72.1、122.9ms
ping_disabled: 只有 synthesis message_start
both_disabled: 无输出
```

因此门合并修掉了 `full`／`until-tool-use` 的双门分叉，而且合成后 header deadline 会正确退出；**被否定的是更强的全称命题“当前实现不存在 timeout 恒0路径”**，反例就是 B-1 的 task-ready 优先级。

门修复的正反对照也有效。以 20ms ping、30ms synthesis、held-back block 运行 `97d805e` 与 `3160285`：

```text
full:
  97d805e  首字节约 116.6ms，0 ping
  3160285  message_start 约 30.9ms；ping 约 51.3、71.6、92.0、112.3ms
until-tool-use:
  97d805e  首字节约 116.2ms，0 ping
  3160285  message_start 约 30.9ms；ping 约 51.3、71.6、91.9、112.4ms
```

证据强度：**高到足以确认 `3160285` 的单门改动修对了它针对的 blocker**；它不抵消 B-1。

## 2. post-yield 打戳与异常／取消

`src/app/pipeline/delivery/stream.py:124-129` 现在是：

```python
async for chunk in inner:
    yield chunk
    last_write.at = loop.time()
```

顺序正确。生产 `StreamingResponse` 在取得 chunk 后 await `send(...)`，正常进入下一轮 pull 时才恢复这个 yield，所以打戳位于上次 send 之后、下一次 inner pull 之前。原第一轮慢下游构造现在得到：

```text
$ uv run python /tmp/probe_stamp_order.py
{'next_is_ping': True, 'anext_elapsed_seconds': 0.05059202195843682}
```

旧实现约 0.0001s 立即返回 ping；当前实现从恢复点再等约 50ms，F-1 已修。

异常／取消路径不执行 post-yield 赋值没有不良后果：

1. 如果调用方在处理当前 chunk 时被取消或 send 抛异常，outer 不会再拉 inner，后续不存在需要该时间戳安排的 ping。
2. 如果调用方捕获取得 chunk 后的外部异常并继续请求下一 chunk，恢复 yield 时仍会先打戳，再拉 inner。
3. 如果 outer 正在 await inner 时被取消，则上一个成功 outward yield 的赋值已经在本次 inner pull 之前执行；当前 pull 没有产出字节，不应打新戳。
4. 如果 inner 抛异常，当前 pull 同样没有产出新字节；异常传播后 generator 关闭，不再有 deadline 消费者。

`client_has_bytes` 在 `_deliver` outward yield 前置位与 post-yield 时间戳不构成竞态：两层生成器在同一个消费 task 中串行运行，outer 未恢复时 inner 也不能继续计算 deadline。若 send 失败，门虽已置位，但流随即关闭，不会据此发后续 ping。

结论：**F-1 已完整修复；异常／取消时不打戳是正确语义。**

## 3. 新增清理测试与第一轮手工构造的强弱

新增测试位于 `tests/unit/test_stream_delivery.py:342-372`。

### 取消传播

`test_a_cancelled_consumer_gets_its_cancellation_back` 先让 upstream 产出不完整 block start，再 sleep 60s。assembler 没有 outward chunk，所以 consumer 正停在 outer await inner 的路径；随后取消整个 consume task，并断言 await task 抛 `CancelledError`。这与第一轮手工构造“outer 正在等待永不完成的 inner 时取消 pull task”等价，且使用完整 `async for` + `aclosing` 消费形态，不比手工构造弱。

它没有证明 upstream 被及时关闭，但该性质正是 D-1，测试名与断言没有冒充覆盖它。

### inner 异常传播

`test_an_upstream_failure_reaches_the_caller` 先闭合并实际交付一个块，再由 upstream 抛 `RuntimeError("upstream broke")`。第一轮手工构造是在任何 outward chunk 前立即抛 `Boom("sentinel")`；新增测试覆盖“已经跨过多个 outward yield 和 post-yield 打戳后再抛”的更强 mid-stream 路径，并以精确类型／消息断言异常没有被正常结束或 cleanup 替代。

结论：**F-2 已修；两条测试分别覆盖原手工构造，异常测试更强。** 它们不覆盖 asyncio loop handler 噪音，但原有 `test_a_keep_alive_wait_leaves_no_asyncio_noise` 仍覆盖正常 timeout→EOF；本轮 `PYTHONASYNCIODEBUG=1` 手工探针在取消与异常路径仍报告 `noise=[]`。

## 4. D-1 既有缺陷判断

### 已确认

1. **缺陷不是本轮引入。** 第一轮已对 `a374f39^` 与 `a374f39` 运行同一 early-close 构造，二者的 upstream `finally` 均未立即执行；当前 `3160285` 仍相同。
2. **裸 `async for` 不替调用方关闭被迭代 async iterator。** outer／`_deliver` 的 `GeneratorExit` 不会自动向 `_events_with_ping`、`read_events`、原始 `chunks` 逐层调用 `aclose()`。
3. **存在 pending `anext` 时，先直接关闭同一个 async generator 会失败。** 实测先 `create_task(anext(source))`，再 `await source.aclose()`：

```text
RuntimeError: aclose(): asynchronous generator is already running
```

取消并观察 pending task 后，upstream `finally` 才执行。

4. **`finish_stream_cleanup` 的“先 cancel 并 observe pending，再 close iterator，同时延迟外部 cancellation”正是所需的顺序。** 对同一 running source 调用 `finish_stream_cleanup(pending, source)` 得到 `cleanup_error=None`、`cleanup_cancellation=None`、`upstream_closed=True`。

### 需要保留的实现层级限定

“直接加 `aclosing(_events_with_ping(...))` 不够”是对的，但原因应读得精确：关闭 wrapper 本身不会自动关闭其内部 `events`／`chunks`。本轮实测在 wrapper 正 yield `None`、内部 pull 仍 pending 时调用 wrapper `aclose()`，调用本身没有抛 RuntimeError，却满足：

```text
upstream_closed_immediately = false
```

之后让 upstream 自然结束，遗留 pull 报出：

```text
Task exception was never retrieved
StopAsyncIteration
```

也就是说，裸 `aclosing` 不仅不释放上游，还会在这种拼法下重新制造 observer 噪音。只有当修复进一步尝试在 pending `anext(events)` 尚未 settle 时关闭那个**底层同一生成器**，才直接撞 `aclose(): asynchronous generator is already running`。

因此 D-1 的结论与 deferred 决策准确，但未来实施时不能把“接入 `finish_stream_cleanup`”理解成只在 `_deliver` 外面包一层调用：pending task 的所有者是 `_events_with_ping`，取消／观察必须在能访问该 task 的层执行；随后还要保证关闭从 `events=read_events(chunks)` 继续传到原始 `chunks`，因为裸嵌套 `async for` 不会自动级联。具体接线必须用 early close after content 与 early close after ping 两种悬停位置分别验收。

证据强度：**高，强到足以确认 D-1 是真实既存缺陷并支持独立 slice；当前证据不支持任何“只加 aclosing 即完成”的修法。**

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
25 passed in 17.61s

$ uv run pytest tests/unit/test_stream_delivery.py::test_a_cancelled_consumer_gets_its_cancellation_back tests/unit/test_stream_delivery.py::test_an_upstream_failure_reaches_the_caller tests/unit/test_stream_delivery.py::test_a_held_back_block_does_not_disarm_both_guards -q
4 passed in 5.31s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

这些绿支持被 selector 枚举到的路径；B-1 的反例说明现有测试没有覆盖“deadline 到期时 task 同时已完成”的优先级。

## 最终裁决

- blocker：1
- major：0
- minor：0
- 已确认修复：3（post-yield 打戳、取消传播测试、inner 异常传播测试）
- 已确认 deferred：1（D-1，含实施层级限定）
- verdict：**needs-fix**
- 合入判断：**`3160285` 的单门修复本身正确且必须保留，但当前 HEAD 不能作为完成的 delivery keep-alive 候选合入；先修 B-1。**
