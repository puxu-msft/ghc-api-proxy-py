# `6a55adf` asyncio 控制流与清理语义复评

## 结论

**needs-fix，`6a55adf` 当前不能合入。** B-1 的持续就绪事件饥饿已经修掉：同一 200000 delta 探针由修复前 10.46s、0 ping、173125 次 zero-timeout-and-task-done，变为修复后 8.16s、8 ping、只有 2 次瞬时 zero-timeout-and-task-done，后者会在下一轮顶部结算而不再恒定。

但“EOF／其它异常一旦发生就不会先发 ping”的论证不成立。顶部结算发生在**创建下一次 pull task 之前**：若上一 event 处理期间 deadline 到期，而下一 pull 会立即返回 EOF 或抛异常，`6a55adf` 会先 yield `None`，随后才创建 task 并发现终止。客户端已有字节时，这个 `None` 会变成真实 `PING_FRAME`。与 `3160285` 对照，当前实现会在 terminal 前多发一枚 ping，也会在原本应立即传播的 `RuntimeError` 前先发一枚 ping。

严重度定为 **major** 而非 blocker：异常最终仍原样传播、EOF 后 terminal 仍发送，额外帧是无内容的 SSE comment；但它明确改变了本轮要求保持的 EOF／异常优先级，而且 coordinator 的放行论证依赖这个不成立的命题，因此必须修正后再合入。`6a55adf` 的“到期后必须在下一 ready event 之前结算”机制应保留，不应回退到 `3160285`。

证据强度：**高，强到足以阻止当前提交合入**。反例分别在私有调度器与公共 `stream_delivery` 路径复现，并与 `6a55adf^` 动态加载对照；不是从源码顺序单独推断。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`6a55adfd1a382cddaa18276d1edb01add391fce9`
- 对照：`6a55adf^ = 3160285dff1e325427aff018cc815f8629fe8d41`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### M-1：顶部结算抢在下一 pull 之前，EOF／异常优先级不再与 `3160285` 一致

- 严重度：**major**
- 把握程度：**高；修复前后公共路径直接对照**
- 位置：`src/app/pipeline/delivery/stream.py:59-66`。

当前外层循环先做：

```python
while True:
    due = _keepalive_due(ping_deadline, last_write, interval)
    if due is not None and loop.time() >= due:
        ping_deadline = loop.time() + interval
        yield None
    task = asyncio.ensure_future(anext(events))
```

因此 coordinator 的论证只证明了一个较窄命题：**某个已经创建的 task 在 `task.result()` 抛出 `StopAsyncIteration`／其它异常之后，控制流不会再回到顶部。** 它没有证明“顶部结算前，下一 pull 不会立即终止”，因为那时 task 尚未创建。

私有调度构造 `/tmp/compare_pretermination_priority_6a55adf.py`：先交付一个 event，等待 interval 到期，再请求下一项；底层下一 pull 立即 EOF 或抛 `RuntimeError`。

```text
$ uv run python /tmp/compare_pretermination_priority_6a55adf.py
{
  'eof': {
    '6a55adf^': ['SseEvent', 'StopAsyncIteration'],
    '6a55adf':  ['SseEvent', 'None', 'StopAsyncIteration']
  },
  'error': {
    '6a55adf^': ['SseEvent', 'RuntimeError: next pull failed'],
    '6a55adf':  ['SseEvent', 'None', 'RuntimeError: next pull failed']
  }
}
```

公共路径构造 `/tmp/compare_public_pretermination_6a55adf.py` 使用真实 `stream_delivery`、`AnthropicAssembler` 和 block policy：先完整交付首块，使 `client_has_bytes` 为 true；下一 incomplete block-start 的 pull 占用 event loop 超过 1s 后完成；其后的 pull 立即 EOF 或抛异常。结果：

```text
$ uv run python /tmp/compare_public_pretermination_6a55adf.py
{
  'eof': {
    '6a55adf^': {'ping_count': 0, 'terminal_sent': True, 'error': None},
    '6a55adf':  {'ping_count': 1, 'terminal_sent': True, 'error': None}
  },
  'error': {
    '6a55adf^': {'ping_count': 0, 'terminal_sent': False, 'error': 'RuntimeError: next pull failed'},
    '6a55adf':  {'ping_count': 1, 'terminal_sent': False, 'error': 'RuntimeError: next pull failed'}
  }
}
```

这里异常没有被吞，但传播被一枚 outward ping 抢先；若 downstream send 在这枚 ping 上失败／被取消，原本下一 pull 已可得的 upstream 异常甚至不会在该消费链中被观察。EOF 路径则在 terminal frames 前插入一枚不必要的 ping。

修复判据而非指定实现：持续就绪的**正常 event**不得继续饿死 due keep-alive，但已经 ready 的 EOF／异常必须先于 keep-alive 传播。可以考虑先创建并给下一 pull 一次 `timeout=0` 的结算机会；若 task 已完成，先调用 `task.result()` 区分 event 与终止，只有拿到正常 event 后才在交付它之前结算 due keep-alive。具体结构需避免重引入 B-1，并继续观察 task 异常。

## 1. B-1 与 busy-loop 复评

### 修复前后探针对照

同一个 `/tmp/probe_ready_upstream_ping_starvation.py` 使用合法 `sse_ping_interval=1`、200000 个始终 ready 且属于未闭合第二块的 delta，并记录 `asyncio.wait` 收到的 timeout：

```text
6a55adf^:
{'deltas': 200000, 'elapsed_seconds': 10.456148108991329, 'ping_count': 0, 'chunks_out': 6, 'zero_timeouts': 173125, 'zero_timeouts_with_done_task': 173125}

6a55adf:
{'deltas': 200000, 'elapsed_seconds': 8.163459256000351, 'ping_count': 8, 'chunks_out': 14, 'zero_timeouts': 2, 'zero_timeouts_with_done_task': 2}
```

修复后的 2 次 zero-timeout 不是恒 0：该轮 `task.done()` 交付一个 event 后返回外层顶部，顶部发现 due，先前推 `ping_deadline` 再 yield `None`。8.16s 内 8 枚 ping 与 1s interval 一致，B-1 已修。

### 调用方不写字节的顶部 `None`

当 `client_has_bytes` 为 false 且 synthesis disabled 时，顶部 `None` 被 `_deliver:173` 的 `continue` 吞掉。它不会忙等，因为 `_events_with_ping:63` 在 yield 之前已经执行：

```python
ping_deadline = loop.time() + interval
```

恢复后本轮直接创建 task；若恢复延迟使新 deadline 又已过去，inner wait 至多出现一次 timeout 0 或交付一个 ready event，随后外层顶部再次前推 deadline。生产配置的 enabled interval 是正整数，不能维持“前推后的 deadline 仍等于当前时刻”的状态。

当 client 已有字节时，顶部 `None` 变为 outward ping。outer 在该 yield 的 downstream send 完成后更新 `last_write.at`；inner 恢复后 `_keepalive_due` 取 `max(ping_deadline, last_write.at + interval)`，下一次 due 至少在这次写后一个 interval。

当 synthesis deadline 同时到期时，同一个 `None` 会触发 `client_has_bytes.set()` 与 `message_start`；下次 inner pull 时 header deadline 已退出候选集。单门 false→true 转换仍无回退。

结论：**没有发现新的无限 `yield None` busy loop；B-1 确实修复。M-1 是终止优先级问题，不是 deadline 未前推。**

## 2. EOF、异常与取消

### EOF

一旦某个 pull task 的 `task.result()` 实际抛出 `StopAsyncIteration`，`:93-94` 立即 return，此后不会再执行顶部；所以“已观察到 EOF 之后不发 ping”成立。

更强的“若下一 pull 已经可以立即 EOF，也不先发 ping”不成立，见 M-1。async iterator 在协议上要到下一 pull 才正式观察到 EOF，但本轮明确要求与 `3160285` 保持终止优先级；当前公共 wire 已发生可见变化，不能用“尚未观察到”消解。

### 其它异常

已创建 task 的异常仍由 `task.result()` 原样传播，outer `finally` 没有吞掉它。可是 due 顶部 `None` 可以抢在**尚未创建但会立即失败的下一 pull**之前；所以异常最终类型／消息不变，优先级不与 `3160285` 一致。

### 取消

`test_a_cancelled_consumer_gets_its_cancellation_back` 仍通过；手工取消路径也未出现异常替换。顶部 yield 与既有 outward chunk 使用相同 async-generator 取消语义，且在 client 尚无字节时 `_deliver` 不 outward yield。没有发现取消传播回归。

## 3. 新 ready-upstream 回归测试的分辨力

`test_an_always_ready_upstream_does_not_starve_the_keep_alive` 的 1.3s 墙钟构造**不比固定 200000 delta 探针弱于机器速度变化，反而更稳**：固定数量可能在更快机器上不到 1s，从而根本没跨过 deadline；墙钟循环保证 source 持续 ready 至少约 1.3s。

修复前后实测同一测试形状：

```text
$ uv run python /tmp/compare_ready_test_6a55adf.py
{'6a55adf^': (0, 1.300523417943623), '6a55adf': (1, 1.3007673469837755)}
```

第一项为 ping 数，第二项为耗时。该测试确实咬住 B-1。

保留一个限定：它依赖 event loop 在 interval 内至少调度一次已经 ready 的 pull task。若 CI 整个 event loop 单次停顿超过 1s，旧实现可能因真正 wait timeout 而发 ping，形成环境性 false green；这不是“机器算 delta 慢”的通常情况，而是严重 scheduler stall。固定 200000 构造也不能消除调度变量，并另有“快机器不跨 deadline”的缺点。当前测试作为回归足够；若未来出现该 flaky 形态，再把 deadline／wait 交错下沉成受控单元构造，不必现在新增证明系统。

测试还有一个范围边界：它证明 ready 正常 event 不再饿死 ping，不证明 EOF／异常优先级；M-1 正是这条未覆盖的相邻分支。

## 4. 上一轮三项修复复核

### post-yield 打戳

顺序仍为 `yield chunk` 后更新 `last_write.at`。慢 downstream 探针仍约等一个完整 interval，而不是立即 ping：

```text
{'next_is_ping': True, 'anext_elapsed_seconds': 0.05059202195843682}
```

结论：**仍成立。**

### 两条清理／传播测试

取消测试与 mid-stream upstream failure 测试均通过；后者仍证明已交付内容后出现的 upstream `RuntimeError` 原样到达调用方。M-1 是“due ping 是否抢在下一 pull 前”的新优先级，不是否定这两条测试在各自未到期构造中的断言。

结论：**仍成立，但异常测试没有覆盖 due deadline 与立即失败的下一 pull 同时可行动的路径。**

### 单门 `client_has_bytes`

`full` 与 `until-tool-use` 两个参数化 case 均通过；synthesis 触发前 held-back block 不再解除 header deadline，message_start 后门置位，header deadline 退出，随后 ping 正常。

结论：**仍成立。**

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
26 passed in 18.80s

$ uv run pytest tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_keep_alive tests/unit/test_stream_delivery.py::test_a_cancelled_consumer_gets_its_cancellation_back tests/unit/test_stream_delivery.py::test_an_upstream_failure_reaches_the_caller tests/unit/test_stream_delivery.py::test_a_held_back_block_does_not_disarm_both_guards -q
5 passed in 6.65s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

这些绿确认 B-1 happy path、取消、普通异常与单门 held-back 路径；不覆盖 M-1 的 due deadline 与下一 pull termination 竞争。

## 最终裁决

- blocker：0
- major：1
- minor：0
- 已确认修复：4（B-1、post-yield 打戳、两条清理／传播测试、单门修复；两条测试合并计为一个复核项）
- verdict：**needs-fix**
- 合入判断：**`6a55adf` 不能按当前形态合入。保留其 B-1 deadline 结算目标，修复 M-1，使 ready 正常 event 让位于 due keep-alive，而 ready EOF／异常先于 keep-alive 传播。**
