# `b1eb2ee` asyncio 控制流与清理语义复评

## 结论

**needs-fix，`b1eb2ee` 当前不能合入。** B-2 已修，B-1 与 M-1 仍成立，两个 deadline 在 pending 与 ready-normal-event 两条路径上都能结算；没有找到 deadline 自身恒0或每 event 多一个 `None` 的 busy loop。

但按“是否还有第六种形态”继续攻击后，找到一个新的异常优先级耦合：`settle()` 在确认 task result 是正常 `SseEvent` 后、把 event 交给 `_deliver` 之前 yield `None`。对于 preamble-only 配置，这会先向客户端写 `message_start`，随后 `assembler.push(event)` 才发现该 event 非法并抛异常。`b1eb2ee^` 在同一构造中直接传播 `ValueError`、没有任何 body；`b1eb2ee` 则先发 1 个 `message_start` 再传播同一个异常。若这次 downstream write 失败或被取消，assembler 异常会像 M-1 曾讨论的 upstream 异常一样退出消费链的可观察范围。

严重度：**major**。异常最终仍会在 send 成功时传播，所以不是 blocker；但这是 `b1eb2ee` 新扩展到 synthesis path 的可见优先级变化，且正来自“scheduler 只返回 bool，由调用方稍后处理 item”这条新耦合，不能在未裁定／未修正前放行。

证据强度：**高，强到足以阻止当前提交合入**。构造使用公共 `stream_delivery`、真实 `AnthropicAssembler`，通过合法但类型错误的 upstream `content_block_start.index` 触发真实 `ValueError`，并动态加载 `b1eb2ee^` 对照。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`b1eb2ee3e80fe82726053738f93f6e4f836b58f6`
- 对照：`b1eb2ee^ = 87b8899cc21daea7fd707ce9f15b3b18ca889258`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### M-2：due cue 抢在 normal event 的 assembler 异常之前

- 严重度：**major**
- 把握程度：**高；公共路径修复前后对照**
- 位置：`src/app/pipeline/delivery/stream.py:103-110` 与 `:179-193`。

`task.result()` 只证明 pull 成功产生了一个 `SseEvent`；它没有证明 `_deliver` 能处理这个 event。当前顺序是：

```python
item = task.result()
if settle():
    yield None
 yield item
```

`_deliver` 收到 due `None` 后可能立即置位 `client_has_bytes` 并 outward yield `message_start`。只有 caller 再次拉 `_events_with_ping` 时，保存在局部变量里的 `item` 才被 yield，随后 `assembler.push(event)` 执行并可能抛异常。

构造 `/tmp/compare_preamble_before_assembler_error_b1eb2ee.py`：配置 `sse_ping_interval=0`、`synthesized_response_headers_after_sec=1`；pull 在 event loop 中占用 1.05s 后正常返回一个 `content_block_start`，但其 `index="not-an-int"`，真实 `AnthropicAssembler._open()` 的 `int(...)` 会抛 `ValueError`。

```text
$ uv run python /tmp/compare_preamble_before_assembler_error_b1eb2ee.py
{
  'b1eb2ee^': {
    'message_start_count': 0,
    'error': "ValueError: invalid literal for int() with base 10: 'not-an-int'"
  },
  'b1eb2ee': {
    'message_start_count': 1,
    'error': "ValueError: invalid literal for int() with base 10: 'not-an-int'"
  }
}
```

这不是 task-level M-1 复发：`task.result()` 确实正常返回，错误来自下一层同步处理。但用户可观察后果相同——修复前没有 body 就失败，修复后先产生一个合法 Anthropic `message_start` 再截断；若该 body write 失败，原始 assembler 错误不会被观察。

根因正是本轮询问的结构耦合：`settle()` 把两个原因压成 bool，而 scheduler 把 cue 与正常 item 分成两次 yield；caller 必须先处理 cue，尚未有机会验证／装配 item。对正常 event，这足以实现 deadline；对“pull 正常、处理失败”的 event，它重开了 M-1 的下一个层级。

修复判据而非指定实现：due deadline 不能饿死，但任何已取得 normal event 的同步解析／assembler 异常也应在新增的 downstream cue 前传播。实现可能需要让 cue 状态与 item 一起流到 `_deliver`，由 caller 在成功处理 event 后决定是用刚产生的真实字节解除义务、还是在 held／incomplete 情况下发 preamble／ping；仅在 `_events_with_ping` 内先 yield bool cue，无法看见下一层异常。若产品明确裁决“deadline 优先于 assembler 错误”，也必须把这是新的公共 wire 行为写成契约，而不能继续声称异常优先级未变。

## 1. B-2 复评

### `ping=0 / synthesis=1`

动态加载 `b1eb2ee^` 与当前模块，在 `full` policy、1.3s ready upstream 下对照：

```text
$ uv run python /tmp/compare_ready_deadlines_b1eb2ee.py
{
  'config': {'ping': 0, 'synthesis': 1},
  'b1eb2ee^': {'first_output_seconds': 1.300483963044826, 'first_while_running': False},
  'b1eb2ee': {'first_output_seconds': 1.0000818990520202, 'first_while_running': True}
}
```

修复前首字节与 source 结束同到；修复后约在 1s deadline 到达，且 source 仍在运行。原 `/tmp/probe_ready_header_starvation.py` 也确认两个 held-back policy：

```text
{'policy': 'full', 'first_output_seconds': 1.0000825059833005, 'message_start_present': True}
{'policy': 'until-tool-use', 'first_output_seconds': 1.000093703973107, 'message_start_present': True}
```

### `ping>0 / synthesis>0`

使用合法整数 `ping=2 / synthesis=1`，使 synthesis 明确早于 keep-alive：

```text
{
  'config': {'ping': 2, 'synthesis': 1},
  'b1eb2ee^': {'first_output_seconds': 1.3003916590241715, 'first_while_running': False},
  'b1eb2ee': {'first_output_seconds': 1.0001244969898835, 'first_while_running': True}
}
```

修复后不再等 2s keep-alive 充当 synthesis 的偶然唤醒器；1s preamble deadline 独立生效。

结论：**B-2 真正修掉。** `preamble_due()` 在 client 无字节时参与 pending deadline 与 ready-normal-event settlement；`_deliver` 收到 cue 后置位同一个 Event，下一次 `preamble_due()` 返回 `None`，不会重复结算。

## 2. busy loop 与常数开销

### ready 路径、client 无字节、synthesis disabled

此时 `settle()` 只能因 keep-alive due 返回 true。它在 yield 前执行：

```python
ping_deadline = now + interval
```

`_deliver` 因 client 无字节且没有 synthesis 而吞掉 `None`，随后立即取得被保留的 normal item。下一 ready item 再调用 `settle()` 时，raw deadline 在未来；不会每 event 都返回 true。

直接计数 `/tmp/probe_swallowed_none_cadence.py`：2.3s 内处理 102661 个 ready event，只产生 2 个 `None`，与 1s interval 对齐：

```text
{'none_count': 2, 'event_count': 102661}
```

因此多出来的是每 interval 一次的 O(1) cue，而不是每 event 一次的常数放大。

### preamble due

preamble 本身不会前推 fixed deadline，但生产 caller 在第一次 due `None` 上同步执行 `client_has_bytes.set()`，inner 在 outward yield 期间暂停；恢复后 `preamble_due()` 立即返回 `None`。不存在重复过期 deadline。

### pending wait 路径

`asyncio.wait` 在 task 未完成时只会因计算出的某个 deadline 返回。代码仍无条件 yield `None`，即使 `settle()` 因时钟读数差一点返回 false；这是既有的“不要漏提示”语义。若确实稍早，caller 至多吞掉／提前发送一次 cue，下一轮 timeout=0 后完成真实 settlement；没有状态不变的无限循环。

结论：**没有发现新的 busy loop，也没有每 ready event 一个 `None` 的失控开销。**

## 3. B-1、M-1、取消与 task 异常

### B-1

200000 ready delta 探针：

```text
{'deltas': 200000, 'elapsed_seconds': 7.256822401017416, 'ping_count': 7, 'chunks_out': 13, 'zero_timeouts': 2, 'zero_timeouts_with_done_task': 2}
```

7.26s 内 7 枚 ping；2 次瞬时 zero timeout 在 ready event 后由 `settle()` 结算，没有恒0饥饿。B-1 仍成立。

### M-1

私有优先级探针仍得到：

```text
'eof':   ['SseEvent', 'StopAsyncIteration']
'error': ['SseEvent', 'RuntimeError: next pull failed']
```

没有额外 `None`。task-level EOF／异常仍在 `item = task.result()` 处先于 settle 离开，M-1 仍成立。

### 取消与异常传播

现有取消与 upstream mid-stream `RuntimeError` 测试均通过；settle 是同步闭包，不捕获异常／取消。新问题 M-2 不是异常被吞，而是 assembler 错误前新增一个 outward cue；send 成功时原异常仍传播。

`_events_with_ping` pending task 的提前关闭缺陷 D-1 未改变，也不是本提交引入。

## 4. 两 deadline 共用 `settle()` 的结构评估

就 deadline 状态机本身而言，共用函数减少了之前“ready path 只结算其中一个”的漏点：

- active set 由 `_keepalive_due(...)` 与 `preamble_due()` 各自决定。
- keep-alive 是可续期 deadline，到期时在 settle 内前推。
- preamble 是 one-shot fixed deadline，由 caller 写字节后通过共享 Event 退出 active set。
- 两者同时到期只需一个 `None`：caller 优先发 preamble；这次真实写同时解除 keep-alive 义务，outer post-yield timestamp 会把有效 due 推后。

bool union 没有丢失当前两种正常动作所需的信息，因为 caller 可用同一 Event 与固定 deadline重新判定“合成还是 ping”。但它丢失了**normal item 尚未成功处理**这一事实，导致 M-2。问题不是两个 deadline 合并，而是 cue 与 item 被拆成先后两次 yield、且处理顺序固定为 cue first。

本轮找到的“第六种形态”因此是：**pull-level normal 不等于 delivery-level normal；用前者替后者作为“现在可以先写 cue”的 guard，会在 assembler failure 上失真。**

## 新回归测试评估

`test_an_always_ready_upstream_does_not_starve_the_preamble` 使用 ping disabled、synthesis enabled、首块始终不闭合，并记录首 chunk 是否在 source finished 前到达。它在父提交得到 `arrived_while_running=None`，当前得到 true；构造有分辨力。

与 ready keep-alive 测试相同，它依赖 event loop 不发生超过整个 interval 的单次 scheduler stall；正常慢机器由 1.6s 墙钟循环自适应，不会因 delta 数不足失去分辨力。当前 ROI 足够。

该测试不覆盖 M-2，因为其所有 event 都能被 assembler 正常处理；这正是新增 finding 的相邻分支。

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
28 passed in 21.62s

$ uv run pytest tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_preamble tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_keep_alive tests/unit/test_stream_delivery.py::test_an_end_of_stream_is_not_preceded_by_a_keep_alive tests/unit/test_stream_delivery.py::test_a_cancelled_consumer_gets_its_cancellation_back tests/unit/test_stream_delivery.py::test_an_upstream_failure_reaches_the_caller tests/unit/test_stream_delivery.py::test_a_held_back_block_does_not_disarm_both_guards -q
7 passed in 9.42s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

这些绿确认 B-2、B-1、M-1、取消与普通 upstream 异常；不覆盖 normal SseEvent 在 `_deliver` 处理时抛异常的 M-2。

## 最终裁决

- blocker：0
- major：1
- minor：0
- B-2：已修
- B-1：仍已修
- M-1：仍已修
- 第六种形态：M-2，pull normal 先写 cue、delivery processing 后失败
- verdict：**needs-fix**
- 合入判断：**`b1eb2ee` 不能按当前形态合入。保留统一 settlement 与 B-2 修复，但须裁定／修复 normal event 的 assembler 异常是否必须先于新增 cue 传播。**
