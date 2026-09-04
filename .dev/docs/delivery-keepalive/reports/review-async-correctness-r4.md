# `87b8899` asyncio 控制流与清理语义复评

## 结论

**needs-fix，当前 HEAD `87b8899` 不能作为 delivery keep-alive 候选合入。** M-1 已修：正常 ready event 仍会在交付前结算到期 keep-alive，而 ready EOF／异常在 `task.result()` 处先行离开。B-1 也未复发。

但复评“前面四项修复仍成立”时发现另一个同族 blocker：task 正常完成后的新结算只检查 `_keepalive_due(...)`，不检查已经到期的 `response_headers_deadline`。当客户端尚无字节、upstream event 始终 ready、且 `sse_ping_interval=0` 时，没有任何路径 yield `None`，所以 synthesis deadline 可被正常 event 无限饿死。合法配置 `synthesized_response_headers_after_sec=1` 下，`full` 与 `until-tool-use` 均到 source 在 1.3s 结束时才产生首字节；source 若继续，静默也继续。单门身份仍正确，但 `3160285` 声称的“所有 policy 都受 synthesis deadline 约束”尚未成立。

严重度：**blocker**。这是首字节静默上界的直接违反，不是测试风格问题。它不是 `87b8899` 新引入的，但与 B-1 共用同一个 ready-task 抢占机制，且属于本 feature 的核心契约，不能按既有缺陷放行。

证据强度：**高，强到足以阻止当前候选合入**。M-1 与 B-1 由修复前后对照探针确认；新 blocker 由公共 `stream_delivery`、真实 assembler、真实 buffer policy 与合法整数配置复现。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`87b8899cc21daea7fd707ce9f15b3b18ca889258`
- M-1 对照：`6a55adfd1a382cddaa18276d1edb01add391fce9`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### B-2：ready 正常 event 仍会饿死 synthesis deadline

- 严重度：**blocker**
- 把握程度：**高；公共路径、合法配置、两种 held-back policy 均复现**
- 位置：`src/app/pipeline/delivery/stream.py:83-97`。

`task.done()` 分支现在正确地先读取 result，但随后只结算 keep-alive：

```python
item = task.result()
due = _keepalive_due(ping_deadline, last_write, interval)
if due is not None and loop.time() >= due:
    ping_deadline = loop.time() + interval
    yield None
yield item
```

`response_headers_deadline` 只出现在等待 task 的 `pending_deadlines` 中。只要每次 task 都立即完成，等待超时分支永远不到；若 ping disabled，`_keepalive_due` 永远为 `None`，正常 event 前也不 yield `None`。于是 `_deliver` 没有机会执行 synthesis 分支并置位 `client_has_bytes`。

构造 `/tmp/probe_ready_header_starvation.py`：首块立即闭合但由 `full`／`until-tool-use` 扣住；第二块始终不闭合；随后 1.3s 内不带 await 地持续产出 delta。配置使用生产 schema 允许的整数值：

```python
StreamSettings(
    sse_ping_interval=0,
    synthesized_response_headers_after_sec=1,
)
```

结果：

```text
$ uv run python /tmp/probe_ready_header_starvation.py
{'policy': 'full', 'first_output_seconds': 1.3004800220369361, 'message_start_present': True}
{'policy': 'until-tool-use', 'first_output_seconds': 1.3004134339862503, 'message_start_present': True}
```

`message_start` 不是在 1s deadline 产生，而是 source 结束、`session.finish()` 开始释放 held block 时才出现。把 ready 循环延长会按相同机制延长首字节静默，没有内在上界。

即使 ping enabled，也不能一般地替 synthesis deadline 工作：若 ping interval 晚于 header deadline，synthesis 会被拖到下一次 ping due；只有恰好有某个 keep-alive `None` 或 task 真正 pending，`_deliver` 才有机会发现 header 到期。两个 deadline 是独立配置，不能靠其中一个偶然唤醒另一个。

修复判据：`task.result()` 已确认拿到**正常 event**之后、交付该 event 之前，应结算所有已到期且仍 active 的 deadline，不只是 keep-alive。若 keep-alive due，需要前推 `ping_deadline`；若 synthesis due，只需 yield 一次 `None`，由 `_deliver` 置位 `client_has_bytes`，随后 header deadline 永久退出。EOF／异常仍必须在任何 deadline 结算前从 `task.result()` 离开。

## 1. M-1 与 B-1 复评

### ready EOF／异常先行

按要求重跑 `/tmp/compare_pretermination_priority_6a55adf.py`。该脚本动态加载 `6a55adf^ = 3160285` 作为正确优先级对照，当前 import 指向 `87b8899`：

```text
$ uv run python /tmp/compare_pretermination_priority_6a55adf.py
{
  'eof': {
    '6a55adf^': ['SseEvent', 'StopAsyncIteration'],
    '6a55adf':  ['SseEvent', 'StopAsyncIteration']
  },
  'error': {
    '6a55adf^': ['SseEvent', 'RuntimeError: next pull failed'],
    '6a55adf':  ['SseEvent', 'RuntimeError: next pull failed']
  }
}
```

脚本标签仍写 `6a55adf`，但当前模块路径在评审锚点已确认是 worktree HEAD `87b8899`。修复后没有额外 `None`；EOF 与 `RuntimeError` 都在 due keep-alive 前离开。

控制流证明与实测一致：`item = task.result()` 位于 due 计算前；`StopAsyncIteration` 被外层 `except` 转为 return，任何其它异常直接传播，二者都不执行后续 `yield None`。

### ready 正常 event 不再饿死 keep-alive

重跑同一个 200000 delta 探针：

```text
6a55adf^ / 3160285:
{'deltas': 200000, 'elapsed_seconds': 10.456148108991329, 'ping_count': 0, 'chunks_out': 6, 'zero_timeouts': 173125, 'zero_timeouts_with_done_task': 173125}

87b8899:
{'deltas': 200000, 'elapsed_seconds': 6.746905597043224, 'ping_count': 6, 'chunks_out': 12, 'zero_timeouts': 0, 'zero_timeouts_with_done_task': 0}
```

每个 ready 正常 event 经 `task.result()` 后都会检查 due；6.75s 内 6 枚 ping，B-1 已修且 M-1 调整没有重开饥饿窗口。

## 2. busy loop、抢占、异常与取消

### 没有新 keep-alive busy loop

- task pending 且 keep-alive due：原分支先把 `ping_deadline` 前推，再 yield `None`。
- task done 且 normal event：新分支同样先前推，再 yield `None`，然后保留并交付 `item`。
- client 尚无字节、synthesis disabled 时，`None` 会被 `_deliver` 吞掉，但 raw ping deadline 已在 yield 前前推；下一轮不是同一个过期 deadline。
- client 已有字节时，`None` 成为 outward ping；outer 恢复后更新 `last_write.at`，下一 due 至少在该写后一个 interval。

B-2 是 header deadline 从未结算，不是 `yield None` 恒0 busy loop。

### 抢占优先级

当前优先级为：ready EOF／异常 → due keep-alive → normal event。它同时满足 M-1 与 B-1。B-2 修复还需把 active header deadline放在 normal event 前，但不能放到 `task.result()` 前。

### 取消与异常

取消测试仍通过。`task.result()` 的非终止异常仍原样穿过 outer finally；由于 due 检查在它之后，不再有 ping 抢先。若正常 event 后 due ping outward 时消费者取消，当前 event 已被拉取但尚未 yield；流随取消关闭，这与任何“已取数据、下游在下一写上断开”的流式消费语义一致，没有异常替换或 busy loop。

`_events_with_ping` 改标注为 `AsyncGenerator[SseEvent | None]` 与运行事实一致，使 `aclose()` 在静态类型上可见；没有改变 runtime 控制流。

## 3. M-1 的实际影响面

coordinator 对**其第一版公共测试**的诊断成立：如果测试在 outer `stream_delivery` 已 outward yield 一个 chunk 后让消费者空转，下一次 pull 恢复时先执行 post-yield `last_write.at = loop.time()`，due 被推到未来；这样的构造在 `6a55adf` 上本来就没有额外 ping，不能区分 M-1。删除那条 false-green 测试是正确的，直接驱动 `_events_with_ping` 的新测试更稳定地锁住调度不变量。

但“这是唯一能看到差异的层”或“公共路径完全不可观察”是过强结论。消费者空转不是 deadline 在两次 inner pull 之间到期的唯一方式：一个正常 event 已从 `_events_with_ping` 交给 `_deliver` 后，`assembler.push(event)` 是同步处理；若该处理跨过 interval 且不产生下游字节，下一 pull 在 `6a55adf` 会先发 ping，而 `87b8899` 会先创建 task，并让 ready EOF／异常离开。

公共路径对照 `/tmp/compare_public_slow_assembler_87b8899.py` 在同一个 `stream_delivery`、block policy 与真实 `AnthropicAssembler` 外包一层 1.05s 同步 event-processing delay：

```text
$ uv run python /tmp/compare_public_slow_assembler_87b8899.py
{
  'eof': {
    '6a55adf': {'ping_count': 1, 'terminal_sent': True, 'error': None},
    '87b8899': {'ping_count': 0, 'terminal_sent': True, 'error': None}
  },
  'error': {
    '6a55adf': {'ping_count': 1, 'terminal_sent': False, 'error': 'RuntimeError: next pull failed'},
    '87b8899': {'ping_count': 0, 'terminal_sent': False, 'error': 'RuntimeError: next pull failed'}
  }
}
```

因此影响面应表述为：**权威不变量位于 `_events_with_ping` 调度层；在通常的快速 assembler 与消费者空转场景中，outer post-yield 打戳会遮蔽差异；但事件解析／assembler 同步处理跨过 interval 时，差异能成为生产 wire 可观察的“terminal／error 前是否多一枚 ping”。** 当前真实 assembler 通常很快，所以这是条件性生产影响，不应写成每次 EOF 都可见；也不应写成永远只在 private helper 可见。

新测试注释中“that is the only level the difference is visible at”以及 commit message 的同义句应在后续文档整理时收窄；它不影响 `87b8899` 修复本身的正确性。spec 当前正文已经描述调度优先级与下游写失败的后果，没有把影响面限定为 private-only，方向正确。

## 4. 前四项修复复核

1. **B-1**：仍成立；200000 ready delta 产生 6 枚 ping、0 次 zero timeout。
2. **post-yield 打戳**：仍成立；慢 downstream 探针返回下一 ping 前等待约 50ms，而非立即返回：

```text
{'next_is_ping': True, 'anext_elapsed_seconds': 0.05038281803717837}
```

3. **取消与普通 mid-stream 异常测试**：仍通过；`CancelledError` 与 `RuntimeError("upstream broke")` 未被 cleanup 替换。
4. **单门 `client_has_bytes`**：门的身份与 false→true 转换仍正确，`full`／`until-tool-use` 的 pending-upstream 测试仍通过；但其更强结论“synthesis deadline 对 ready-upstream 也构成首字节上界”被 B-2 推翻。需要修的是 deadline settlement，不应重新拆门。

## 新回归测试评估

`test_an_end_of_stream_is_not_preceded_by_a_keep_alive` 在 `_events_with_ping` 层构造 due deadline + 下一 pull EOF，确实在 `6a55adf` 多得到一个 `None`，在 `87b8899` 不得到；测试有分辨力。返回标注改为 `AsyncGenerator` 后，测试用 `aclosing` 也有正确静态类型。

测试只固定 EOF，没有固定“due deadline + ready RuntimeError”这一对照；当前实现由同一个 `task.result()` 同时保证二者，手工探针已确认异常路径。该缺口不阻塞本提交，但若继续调整这段优先级，建议把 EOF／RuntimeError 参数化，以免未来特判重新分叉。

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
27 passed in 19.99s

$ uv run pytest tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_keep_alive tests/unit/test_stream_delivery.py::test_an_end_of_stream_is_not_preceded_by_a_keep_alive tests/unit/test_stream_delivery.py::test_a_cancelled_consumer_gets_its_cancellation_back tests/unit/test_stream_delivery.py::test_an_upstream_failure_reaches_the_caller tests/unit/test_stream_delivery.py::test_a_held_back_block_does_not_disarm_both_guards -q
6 passed in 7.82s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

这些绿确认 M-1、B-1、取消、普通异常及 pending-upstream 单门路径；B-2 的 ready-upstream + header-only 配置不在现有 selector 中。

## 最终裁决

- blocker：1
- major：0
- minor：0
- M-1：已修
- B-1：仍已修
- 前四项：3 项完整成立；单门身份成立但 ready-upstream synthesis 上界尚未成立
- verdict：**needs-fix**
- 合入判断：**`87b8899` 的 M-1 修复正确且应保留，但当前 HEAD 不能完成合入；先让 ready 正常 event 同时结算 active synthesis deadline，且继续保持 ready EOF／异常最先传播。**
