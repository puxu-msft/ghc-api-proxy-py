# `aac348e` hand-over message 独立评审

- 评审对象：`aac348e0d04a5f51d0e7f9d6d994cd9b85152a8a`，`feat: say what interrupted the turn instead of handing back an exception's repr`
- 评审文件：`src/app/pipeline/hand_over.py`、`tests/unit/pipeline/test_hand_over_message.py`
- 评审日期：2026-08-23
- 结论：**needs-fix**
- 发现计数：blocker 0，major 1，minor 4，nit 0

## 总结

实现对当前已观测的 GOAWAY、RST_STREAM、空文本连接重置和裸 `h2.ProtocolError` 明显优于原来的 `str(error)`；正常的 `__cause__`／`__context__` 选择、上下文抑制、循环防护、当前 httpcore2→httpx2 事件对象保留路径、耦合失效时的文本回退，以及 h2 4.4.1 内现有 `stream_id` 异常的特判均经探针核过。没有发现 blocker。

必须修正的一项是测试接线缺口：新增 16 条测试只直接调用新 helper，完全不经过真正生成 `tool_use.input.message` 的 `hand_back_block`。我在 `/tmp` 的提交副本中只把该接线恢复为旧的 `str(error)`，新增 16 条单测和已有相关集成测试仍全部通过。因此，当前测试不能证明这次改动真的到达用户看到的字段。

以下经验性判断的权重是：F1 的证据强到足以据此修复；F2、F3 是构造反例，证明代码的一般性断言不成立，但调查报告未观测到这些形状到达生产链路，故只定 minor；F4 是已确认的跨仓描述冲突，但接收端不据 `message` 做行为决策，故只定 minor；F5 是源码和一手记录可直接证伪的证据措辞问题，故只定 minor。

## Findings

### F1 — [major] 新测试没有覆盖 `hand_back_block` 到 `input.message` 的生产接线，整项用户可见改动可被断开而保持全绿

**问题。** `tests/unit/pipeline/test_hand_over_message.py:22` 只导入 `interruption_message`，其 16 条测试全部经 `message()` 直接调用该 helper（`:27-33`），没有一条调用 `hand_back_block`。现有集成测试也只在 `tests/int/test_pipeline_app.py:3127` 断言 `handed["input"]["message"]` 为真。这样能证明 formatter 本身，却不能证明生产块采用了 formatter；这正是“primitive 有测试、orchestrator 接线未测”的 false-green 形状。

**独立变异证据。** 我从 `aac348e` 用 `git archive` 建了 `/tmp/handover-review-wiring-KKZHZ8`，只把 `hand_back_block` 的接线改回旧实现：

```python
detail = stop_reason if error is None else str(error)
```

随后用 `PYTHONPATH=/tmp/handover-review-wiring-KKZHZ8/src` 运行目标测试，结果仍为：

```text
16 passed in 2.35s
```

继续运行原有真实入口测试：

```text
tests/int/test_pipeline_app.py::test_an_interrupted_turn_is_handed_back_to_the_client_as_a_tool_call
1 passed in 2.90s
```

运行时 `inspect.getsource(app.pipeline.hand_over.hand_back_block)` 与 `app.pipeline.hand_over.__file__` 又确认 pytest 装载的是 `/tmp/handover-review-wiring-KKZHZ8/src/app/pipeline/hand_over.py`，且其中确为上述旧接线，不是变异未生效或导入了主树。

**影响。** 将 `src/app/pipeline/hand_over.py:215-220` 整段误删、恢复成旧行为、或把 helper 接到别的字段，当前新增套件和已有相关集成测试都不会发现；用户仍会看到原来的 opaque repr，而 CI 全绿。

**建议。** 在现有单元文件中增加一个最小的 `hand_back_block` 测试，或增强现有那条集成测试，让断言直接落在产出的 `input.message` 上并至少钉住一个旧实现无法满足的区分，例如 GOAWAY 的 `NO_ERROR`、空文本错误的类型名，或 `request_id`／`attempt_count`。这只是补生产接线的一条 targeted test，不需要新建任何证明基础设施。

### F2 — [minor] 链上限与丢弃规则确实能静默丢掉唯一的因果信息

**问题。** `_chain` 在 6 个 link 后无标记停止（`src/app/pipeline/hand_over.py:78-82`），而文件头注释却说 truncation 会明确说明（`:55`）。另外，`describe_error` 会丢弃所有内层空文本 link（`:138-142`）以及文本与先前 link 相同的 link（`:143-145`）；这里把“文本没有新增”当成“该 link 没有新增信息”，但异常类型本身可能就是唯一新增信息。

**构造反例证据。** `/tmp/review_handover_probe.py` 在当前提交上得到：

```text
SIX_LINK_BOUND_WITH_ONLY_REASON_AT_SEVEN
walked 6 ["builtins.RuntimeError:''", "builtins.RuntimeError:''", "builtins.RuntimeError:''", "builtins.RuntimeError:''", "builtins.RuntimeError:''", "builtins.RuntimeError:''"]
described builtins.RuntimeError

DUPLICATE_TEXT_WITH_INFORMATIVE_INNER_TYPE
builtins.RuntimeError: permission denied
```

第一个对象是 6 个空 `RuntimeError` 最内接一个 `ConnectionResetError(104, "Connection reset by peer")`；唯一原因在第 7 层，被无提示地截掉。第二个对象是 `RuntimeError("permission denied") from PermissionError("permission denied")`；文本重复，但唯一说明错误类别的 `PermissionError` 类型被丢掉。另一个更直接的反例 `RuntimeError() from PermissionError()` 输出也只有：

```text
builtins.RuntimeError
```

这些都由真实的 Python 异常类型组成并遵循合法 cause 语义，但支撑报告没有观测到它们从当前交付链抵达 hand-over，因此该发现足以否定“一般不会丢唯一信息”，尚不足以声称现有已观测故障被误报。

**建议。** 保留有信息的末端或在达到 `_MAX_LINKS` 时附加明确的 omission marker；对于空文本／重复文本 link，可以不重复正文，但不应在它的类型是唯一新判别信息时连类型一并删除。

### F3 — [minor] `_chain` 用 truthiness 选择 `__cause__`，会违背显式 cause 优先规则

**问题。** `src/app/pipeline/hand_over.py:81` 使用 `current.__cause__ or ...`。Python 的 cause 判据是 `__cause__ is not None`，不是 cause 对象为真；异常子类可以定义 `__bool__`。因此一个 falsy 的显式 cause 会被跳过，转而跟随无关的 context，或在 `__suppress_context__` 为真时直接停止。

**构造反例证据。** 探针给 `RuntimeError("outer")` 同时设置 `FalsyCause("the actual cause")` 与 `LookupError("incidental context")`，结果是：

```text
FALSY_EXPLICIT_CAUSE
["builtins.RuntimeError:'outer'", "builtins.LookupError:'incidental context'"]
```

这与 docstring 声称的“`__cause__` 优先”不符。当前报告里的 httpx2、httpcore2、anyio、h2 和 built-in 异常均为 truthy，故不影响已经观测的形状；但交付 try 区间还能接到 framing 抛出的任意 `Exception`，不能把自定义异常排除为结构上不可达。

**建议。** 用显式 `is not None` 选择 cause：有 cause 就跟 cause；只有 cause 为 `None` 时，才依据 `__suppress_context__` 决定是否跟 context。

### F4 — [minor] `message` 改成代理合成诊断是合适的，但当前接收端契约仍错误地承诺 `verbatim`

**判断：有条件赞成。** `request_id` 是 MCP journal 到代理 request trace 的唯一精确 join key；`attempt_count` 让单行记录不用先 join 就能区分首次尝试和重试后的中断。用户亲笔权威只固定 `turn_interrupted(num_messages, category, message)` 的签名，没有规定 `message` 必须是上游原文，所以把这两个值放进现有 `message` 没有违背用户契约，也避免在未裁决时扩展工具参数。

**已确认的契约冲突。** 发送端在 `src/app/pipeline/hand_over.py:167-171` 输出的是代理合成句，包含类型、cause 摘要、HTTP/2 gloss、request id 和 attempt count；接收端 `/home/xp/.claude/my/ghc-api-proxy-helper/src/auto_retry/server.py:53-55` 却仍描述为 “The upstream error message, or the reason the turn ended, verbatim.”。这不再是 verbatim。

**影响边界。** 接收端在 `server.py:65-68` 只用 `category` 与 `num_messages` 驱动 loop/reply；`message` 在 `:69-75` 仅传给 `build_record`，并在 `:103` 写入 JSONL。因此当前冲突不会改变 retry 行为，但会向看 tool schema 的模型或维护者错误描述 journal 字段的 provenance。

**建议。** 同步把接收端描述和跨仓契约改成“proxy-authored interruption diagnostic”一类准确说法，并明确方括号中的 request/attempt 是代理 metadata、不是 upstream verbatim。若接收端必须坚守 verbatim，才应反过来删掉这些合成内容；按本次用户诉求和现有固定签名，我不建议走这个方向。

### F5 — [minor] 新增注释与测试 docstring 有多处把未观测或较窄事实写成已确认的全称

**问题与证据。** 这些不改变运行时，但会让后续维护者误判证据边界：

1. `tests/unit/pipeline/test_hand_over_message.py:3` 说该字段 “had no test at all until now”，但 `tests/int/test_pipeline_app.py:3127` 已有 `assert handed["input"]["message"]`；一手调查报告 `260823-handover-error-shapes.md:321-328` 也明确把它列为已有真值测试。准确说法应是“没有对内容有鉴别力的测试”。
2. 同一行说 “Every case here is a shape that was measured rather than imagined”，却与本文件 `:139-143` 自己标注 `openai.APIConnectionError` 为 “A defensive case, not an observed one” 直接冲突；`remote_reset=False` + `CANCEL`（`:88-94`）也是手工构造，报告没有记录这种组合。报告 §2.3 还明确证明 `openai.APIConnectionError` 当前结构上到不了 hand-over。
3. `tests/unit/pipeline/test_hand_over_message.py:63` 说 ``error_code:0` is the whole of what the old field said`，但实际 journal 原文是完整的 `<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>`；`:72-75` 又说 journal 中两个 repr “differ only by a number”，实际上它们还分别叫 `ConnectionTerminated`／`StreamReset`，字段集合也不同。准确主张是：决定 NO_ERROR 与 CANCEL 语义的 enum name 被压成了数字，而不是整个字符串只有一个差别。
4. `tests/unit/pipeline/test_hand_over_message.py:117` 把连接重置称为 “the most common tear there is”，但报告只记录了一次 localhost socket 实测，没有频率样本；它足以证明该形状存在，不足以证明最常见。
5. `src/app/pipeline/hand_over.py:97` 把 `remote_reset` 解释为“upstream decision 与 our own”的分界，证据只支持 frame 由哪一侧发出。h2 4.4.1 的 `events.py:455-479` 明说 `StreamReset` 也会在 remote party 造成单流 protocol error、由 h2 自动终止时产生；`h2/stream.py:1146-1167` 具体构造 `remote_reset=False` 的 `FLOW_CONTROL_ERROR`，原因仍是收到对端的 WINDOW_UPDATE 后本地流控溢出。因此输出 “sent by this proxy” 作为 frame 方向是准确的，但注释不能进一步推成“这是代理自己的决定”。

**建议。** 把这些句子收窄到各自证据实际支持的范围；尤其保留 APIConnectionError 测试自身 `:139-143` 的正确限定，不要让模块级全称覆盖掉它。

## 逐项覆盖结果

### 1. `_chain` 与 `describe_error`

- **`__cause__` 优先、正常 `__context__`、`__suppress_context__`：查过。** 普通 truthy cause 时顺序正确；cause 缺席且未 suppress 时跟 context；suppress 时停止。探针输出分别是 `RuntimeError -> ValueError(cause)`、只保留 `RuntimeError`、`RuntimeError -> LookupError(context)`。falsy cause 的漏洞见 F3。
- **循环引用：查过，没发现问题。** `RuntimeError -> ValueError -> RuntimeError` 只返回前两个对象；对象在遍历期间均存活，按 `id` 去重没有重用窗口。
- **上限：查过，有 F2。** 恰好 6 层正常保留；第 7 层被静默截断，唯一信息可丢。
- **重复文本、内层空文本、最外层保留：查过，有 F2。** 当前四层真实 reset 形状不丢末层有文本的 `ConnectionResetError`，但一般规则会丢内层唯一类型。
- **全链空文本仍不返回空串：查过，没发现问题。** 最外层类型名确保结果非空；问题只是内层类型会被省略，不是最终字符串为空。

### 2. `_h2_gloss` 耦合与降级

**查过，没发现运行时问题；该耦合可接受。** 当前环境是 h2 4.4.1、httpcore2 2.12.0、httpx2 2.12.0。`httpcore2/_async/http2.py:313-314` 对 `StreamReset` 执行 `raise RemoteProtocolError(event)`，`:323-328` 对已保存的 `ConnectionTerminated` 也执行 `raise RemoteProtocolError(self._connection_terminated)`；`httpx2/_transports/default.py:114-115` 执行 `message = str(exc); raise mapped_exc(message) from exc`。实际通过该 contextmanager 构造的链为 outer `httpx2.RemoteProtocolError(str)`、inner `httpcore2.RemoteProtocolError(event)`，当前实现成功补出 `NO_ERROR`。

我又把 event 在进入 httpcore2 exception 前先转成字符串，模拟未来依赖不再把对象放进 `args`。输出为：

```text
httpx2.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
```

`GOAWAY`／`NO_ERROR` gloss 消失，但原始 repr 完整保留；只有 outer、完全无 cause 的 text-only 版本结果相同。这个失效路径确实是静默降级，不会把原文一并丢掉。当前测试未固定降级承诺，但代码和独立探针都很直接，我不据此另列 finding。

### 3. `_link_text` 的 h2 特判

**查过，没发现现有 h2 4.4.1 类型误伤。** `h2/exceptions.py:64-78`、`:91-118` 显示现有带 `stream_id` 的异常只有 `StreamIDTooLowError`、`NoSuchStreamError`、`StreamClosedError`。实测结果：

```text
NoSuchStreamError '3' -> 'stream 3'
StreamClosedError '3' -> 'stream 3'
StreamIDTooLowError 'StreamIDTooLowError: 3 is lower than 9' -> unchanged
```

前两类正是没有调用 `super().__init__` 而遗留裸参数文本的类型；第三类有自己的合法消息，不满足 `text == str(stream_id)`。未来自定义／新增 H2Error 理论上可以同时拥有 `stream_id=3` 和有意消息 `"3"`，但当前库没有这样的类，结构谓词也足够窄，不值得仅为假设扩展类型白名单。

### 4. 测试鉴别力与真实 reset 链

- **基线：通过。** `cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/pipeline/test_hand_over_message.py -q` 得到 `16 passed in 2.14s`。
- **静态检查：通过。** 对两个目标文件运行 targeted `ruff check` 得到 `All checks passed!`；targeted Pyright 得到 `0 errors, 0 warnings, 0 informations`。
- **生产接线：有 F1。** 将接线恢复成旧实现后 16 条新增单测和已有相关集成测试仍绿。
- **重复文本测试：查过，不是恒真断言。** 用户给出的“整个实现退回 `str(error)` 时它不红”只说明旧实现也满足“不重复”这一外部性质；我在独立提交副本中只删除 `describe_error` 的 duplicate skip，`test_the_same_text_is_not_repeated_down_the_chain` 按预期以 `assert 2 == 1` 变红。它能识别自己声称的机制，不必强迫每一条测试单独识别整个旧实现。
- **恒真／冗余：查过，没有会掩盖错误的恒真断言。** `test_an_error_with_no_text_still_says_what_it_was` 的 `assert text.strip()` 在前一个类型名断言已成立后是冗余的，`test_an_error_that_says_nothing_at_all_is_still_named` 同理；但前置类型名断言本身会在旧实现上变红，所以只是低价值重复，不值得单列 nit。
- **文案耦合：查过，没发现钉整句的问题。** 测试只钉 `NO_ERROR`、`GOAWAY`、`RST_STREAM`、方向、stream id、类型名、request id、attempt 等语义区分，不断言整句；这些 token 就是功能本身，合理的措辞改良仍有空间。
- **四层 reset fixture：查过，忠实于报告 §2.2(d)。** `tests/unit/pipeline/test_hand_over_message.py:119-131` 依次以显式 cause 组成 `httpx2.ReadError('') -> httpcore2.ReadError('') -> anyio.BrokenResourceError('') -> ConnectionResetError(104, 'Connection reset by peer')`；类型、文本和 cause 方向都与报告实测一致。它没有把被测 formatter 用来计算 expected，也没有靠 fixture helper 预先消掉中间层。

### 5. 已观测与未观测的边界

**查过，有 F5，但 APIConnectionError 的局部说明本身正确。** `tests/unit/pipeline/test_hand_over_message.py:139-143` 明确说 `openai.APIConnectionError` 是 defensive、not observed，并准确引用 body 直接读 `httpx2.Response.aiter_bytes()`、header-stage SDK error 在进入 delivery 前已归一化的结构事实；没有在该测试或生产 docstring 中把它写成当前 live shape。问题是模块级 “Every case” 全称与该正确限定冲突。

Journal 事实也已直接核过：`/home/xp/.claude/plugins/data/ghc-api-proxy-helper-my-marketplace/auto-retry.jsonl` 当前确有 4 行，3 个 `ConnectionTerminated`、1 个 `StreamReset`，所以 `src/app/pipeline/hand_over.py:88` 关于“迄今所有 journal 记录均是两类 repr”的句子在本次快照下成立。这个结论只对 2026-08-23 读取到的该文件快照有效，不外推到未来记录或别的 journal 路径。

### 6. `request_id`、`attempt_count` 与 `message`

**结论是有条件赞成，条件见 F4。** 两项 metadata 直接提高 journal 的可关联性和单行可读性；接收端只记录而不据以决策，所以不会改变 retry loop。代价是字段从 upstream verbatim 变成 proxy-authored diagnostic，这个语义变化必须在接收端 schema description 和跨仓文档中如实命名。

## 权威与范围核对

- 用户亲笔 `docs/.human-controlled/upstream-retry-and-continuation.md:27-39` 只规定工具签名和续写机制，没有规定 `message` 内容；本改动不违背它。
- 当前接收端实际代码已读到 `/home/xp/.claude/my/ghc-api-proxy-helper/src/auto_retry/server.py`，不是仅依赖旧 README 推断；行为边界见 F4。
- 评审时主工作树的两个目标文件与 `aac348e` 完全一致；`git diff --exit-code aac348e -- <两个目标文件>` 无输出。工作树另有与本提交无关的并行改动，本评审没有修改任何源码或测试。
- 没有评审用户明确排除的 `category` 归类问题。
