# 对 H2 StreamReset(CANCEL) 诊断的独立评审

**日期**：2026-08-22

**评审对象**：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-h2-streamreset-cancel-diagnosis.md`

**代码基线**：`8f654b44ad81ca200cff3d8d2b44808a50e336b7`

**方法说明**：我先独立阅读并走通 `src/app/pipeline/delivery/stream.py`、`src/app/streaming/keepalive.py`、`src/app/server/pipeline_app.py`、`src/app/model_provider/ghc_client/errors.py`、`src/app/pipeline/retry.py`，形成判断后才读取评审对象。用户指定的 `my-skills:as-reviewer` 在当前运行时不可用，调用返回 `Unknown skill: my-skills:as-reviewer`；因此本报告按只读独立评审原则直接完成。这个工具缺失不影响代码与 Git 证据的取得。

## 一、独立结论

### 1. 发生了什么

上游响应头已经到达，客户端侧 HTTP 200 已经固定。上游响应体由 `response.aiter_bytes()` 经过 idle/deadline guard、`_counted_upstream()`、SSE parser 和 block assembler 消费。HTTP/2 对端对 stream 3 发来 `RST_STREAM(CANCEL)` 后，底层 `httpcore2.RemoteProtocolError` 在标准 `httpx2.AsyncResponseStream` 边界被映射为 `httpx2.RemoteProtocolError`，正在 `_events_with_ping()` 中等待的 pull task 失败。`finish_stream_cleanup()` 的 `await pending` 只是观察并回收这个已经失败的 task，不是失败原因；原异常随后沿 `_events_with_ping()` → `_deliver()` → `stream_delivery()` → `_tracked_delivery()` → Starlette/Uvicorn 向外传播。

**权重：强到可以据此行动。** 依据是上述五个生产文件的控制流、`httpx2._transports.default.AsyncResponseStream` 的异常映射实现，以及后文实际运行输出。

`think(enc:1)` 只直接证明 assembler 闭合并记录了一个加密 thinking block。若生产沿默认 `client_delivery.buffering_policy = "block"`，该块在闭合的同一轮被 `_commit()` 释放，`client_has_bytes` 被置位，客户端已经收到 `message_start` 和该完整块；若生产改成 `full` 或尚未遇到 tool call 的 `until-tool-use`，该块可能仍被扣在 buffer 中。因此“客户端已经拿到块”必须带生产配置前提，不能仅由 `think(enc:1)` 无条件推出。

**权重：默认配置下强到可以据此行动；脱离生产配置只能作为条件判断。** 依据是 `Terminal.record()`、`BlockBuffer.add()`、`DeliverySession.offer()` 与 `_commit()` 的接线，以及后文分别以 `block`、`full` 运行的结果。

### 2. 该不该修

应该修，但要把三个层次分开。

1. 那台机器应升级到包含 `8f654b4` 的当前候选版本。所有能匹配 traceback 行号的已知提交都早于 replay 接线；升级能修复“客户端尚未收到语义块时，transport tear 仍直接失败”的问题。**权重：强到可以据此行动。**
2. 对本次这种“Anthropic Messages 客户端已经收到至少一个完整块，随后网络中断”的情况，HEAD 的 `ABANDON` 只是内部 retry driver 不再重放的正确裁决，不是完整的客户端交付行为。用户权威文档 `docs/.human-controlled/upstream-retry-and-continuation.md:29-41` 已明确裁决：此时应合成 `turn_interrupted(...)` MCP `tool_use`，由客户端发起下一次请求续写。当前源代码完全没有 `turn_interrupted` 或 `auto_retry_tool_call_full_name` 实现。因此这次事故揭示的是一个已裁决但尚未实现的主路径功能，不应被概括为“代码处置基本正确”。**权重：强到可以据此行动。**
3. 对不适用 MCP-driven continuation 的 route/client，或作为合成失败后的明确 fallback，发送带内 SSE `error` 比 abrupt EOF 更可读；但不应把所有落入 `except Exception` 的错误一律伪装成 `incomplete_responses_stream`。该 catch 同时包含 transport error、assembler/conversion bug、`BufferCapExceeded` 等本地失败，只有已识别且按合同可转成客户端 ending 的分支才应“发帧并 return”；未知异常仍应抛出并保留 traceback。**权重：方向足够明确，但 fallback 的适用集合和 wire code 仍需 Spec 落字；这是倾向，不足以直接实现宽泛 catch-all。**

## 二、指定可证伪论断逐条核验

| 论断 | 核验结论 | 权重与依据 |
|---|---|---|
| 部署版本是 `9aa31f9` | **不成立。** 行号只能把部署树限定到本仓库已知的五个提交之一：`9aa31f9`、`767d0f2`、`fa628e1`、`b64003e`、`a68672c`。这五个提交的相关文件行号完全相同。能确定的是部署早于 `51196e2` 和 `8f654b4`，不能确定恰好是 `9aa31f9`，也不能确定“落后 6 个提交”。 | **强到必须改正报告中的版本断言。** 全 revision 行签名扫描给出五个正匹配，见实际运行证据 A。 |
| `9aa31f9` 上 `ReplaySupport` 未接线，`raise torn` 无条件击发 | **成立，但“无条件”限于进入该 ordinary `Exception` tear 分支后。** `stream_delivery(..., replay=None)` 虽有形参和原语，`pipeline_app.py` 没有传入；`replay is None` 恒真，命中当时第 270 行。 | **强到可以据此行动。** `git show 9aa31f9` 的调用点与行号直接证明；而且五个候选部署提交都早于 `8f654b4` 的接线。 |
| HEAD 上该异常归类为 `RetryReason.NETWORK` | **标准生产链上成立，但原报告漏写了一层重要条件。** literal `httpcore2.RemoteProtocolError` 本身不在 `_CONNECTION_ERRORS`，直接传给 `normalize_upstream_error()` 会得到 `None`；标准 `httpx2.AsyncResponseStream` 会先把它映射成以原异常为 cause 的 `httpx2.RemoteProtocolError`，后者才归一化为 `UpstreamError` 并得到 `NETWORK`。给出的缩略 traceback 只点名 root cause，未展示 outer exception；正常 `httpx2` response iterator 足以支持报告的生产判断，但报告中那条直接构造 `httpx2.RemoteProtocolError` 的 probe 不是对“literal httpcore2”这一说法的证明。 | **在标准 `httpx2` transport 链上强到可以据此行动；若实际 outer exception 真的是未映射的 `httpcore2`，则结论反转。** 实际映射与 direct literal 对照见证据 B。 |
| HEAD 上这次仍会 `abandon`，因为客户端已拿到一个 `think(enc:1)` 块 | **带报告自己写出的配置前提后成立。** 默认 `block` 下，闭合 thinking block 已交付，transport tear 被识别为 `NETWORK` 后进入 `ABANDON`，不调用 `reopen()`；`full` 下相同事件被扣住，HEAD 会 replay 并正常完成。 | **默认配置下强到可以据此行动；未知生产配置下只是条件结论。** 证据 C 直接运行了相同 thinking block + reset 在两种 policy 下的结果。 |
| tear 不发带内 SSE `error`，clean EOF 无 terminal 会发 | **成立。** ordinary tear 在 replay 不可用、不可识别、裁决为 `ABANDON` 或 reopen 失败时 `raise torn`，越过函数末尾的 STR-04 frame；clean EOF 正常退出 event loop 后，若已开始消息且 `terminal.seen == False`，会发送 `incomplete_responses_stream`，且不发 `message_stop`。 | **强到可以据此行动。** 现有四个 targeted tests 全绿，clean EOF 的直接输出见证据 D，tear 的直接输出见证据 C。 |

## 三、与原报告逐条对照

### 同意的部分

1. `[FAIL]` completion line 保留异常原文，符合当前 TUI/logging 规格。它把已经固定为 200 的失败 stream 与成功请求区分开，不能因日志“看起来红”而删除。**权重：强到可以据此行动。**
2. 不追查对端为何发送 `RST_STREAM(CANCEL)`。现有证据只能说明流级 remote reset，不能从 error code 推导对端意图。**权重：强到可以据此行动。**
3. HEAD 的 pre-block transparent replay 有价值，而匹配 traceback 的部署候选都没有生产接线。升级建议本身合理。**权重：强到可以据此行动。**
4. 在没有先提供带内 ending 的情况下，单独吞掉已识别 tear 会把 abrupt failure 变成 clean EOF，可能让截断更难辨认。**权重：强到可以据此行动。**
5. `block` policy 下，本次已有 thinking block 交付，transparent replay 不再合法。**权重：以生产确用默认 policy 为前提，强到可以据此行动。**

### 四处实质分歧

#### 分歧 1：不能把部署提交精确归因为 `9aa31f9`

原报告把两个 `stream.py` 行号称为“不是推测”的精确版本判据。全 revision 扫描找到五个完全相同的提交态，因此最多只能判定一个提交区间。这个错误不推翻“应升级”，但会把“落后 6 个提交”、部署内容归因和后续取证都写错。

**权重：强到必须改正。**

#### 分歧 2：“这次事故本身处置基本正确”不符合用户权威需求

`ABANDON` 的含义只是“代理端不能透明重放”，不是“直接 raise 就是完整处置”。`docs/.human-controlled/upstream-retry-and-continuation.md:29-41` 已为“已交付至少一个完整块”的 Anthropic Messages 请求规定 MCP-driven synthesized continuation。报告只看到了被放弃的 proxy-side continuation 和当前 `retry.py` 的 `ABANDON`，没有把同一权威文档紧接着写出的替代机制纳入结论。

本次 route 正是 `/v1/messages`，网络中断也在文档列出的“一般可以继续”集合中；因此这不是一个需要重新裁决是否继续的空白，而是一个尚未实现的已裁决行为。

**权重：强到可以据此建立实现任务。**

#### 分歧 3：P1 不应把“通用 SSE error 扩面”排在真正的主路径行为之前

对本次 Anthropic Messages 请求，优先实现的不是通用 `incomplete_responses_stream`，而是权威文档规定的 `turn_interrupted(num_messages, category, message)` tool block。SSE `error` 仍可能适合作为不支持该机制的 client/route fallback，但它不是本次主路径的已定答案，而且“所有 tear 共用同一 frame”会把 transport tear、本地 assembler bug 与 buffer guard 混成一个错误类别。

**权重：主路径优先级强到可以据此行动；fallback 设计只是倾向，需要单独冻结适用条件。**

#### 分歧 4：P1 与 P2 不应作为两个可独立落地的产品切片

一旦某个已识别 ending 被裁定要通过 SSE frame 或 synthetic tool block回答，该分支就应在同一个语义 patch 中 `yield` 完整 ending 并 `return`。先“发 error 后仍 raise”会同时给客户端协议 ending 和 transport failure；先吞异常则制造 clean truncation。两者都不是可交付中间态。

同时，不能把“消除 traceback”泛化到所有 `raise torn`：未知 conversion/assembler/internal error 的 traceback 仍是唯一完整诊断。应消除的是被代码明确识别并已经转成协议 ending 的 expected transport failure traceback，而不是异常边界本身。

**权重：强到可以据此调整切片边界。**

## 四、原报告遗漏的一个更简单问题

HEAD 的 `decide_stream_ending()` 明确定义了 `terminal_seen=True -> COMPLETE`，但 `_deliver()` 对任何不是 `REPLAY` 的 verdict 都执行 `raise torn`。所以若完整 upstream terminal event 已经被 assembler 接收，紧接着下一次读取才收到 reset，客户端仍拿不到代理本来已经有充分信息生成的 `message_delta`/`message_stop`，Uvicorn 仍打印 traceback。

证据 E 的运行结果是：`terminal_seen=True stop_reason=end_turn raised=RemoteProtocolError message_stop_delivered=False`。

这条修复比“给所有 tear 扩 error frame”更窄、更简单、语义也更确定：对 `COMPLETE` 应走现有 finish/terminal framing，而不是把一个已完整接收的 reply 当成中断。它不修本次事故，因为本次日志明确未见 terminal；但它应在泛化 error-frame 之前处理，避免把本来可以成功完成的请求降级成 error。

**权重：强到可以据此建立一个独立小修复。** 依据是 `decide_stream_ending()` 的公开返回类型、caller 对 `COMPLETE` 的遗漏以及实际运行输出。具体实现仍应新增一个针对“terminal event 后 reset”的 discriminating regression test，而不是追求覆盖率。

## 五、优先级建议

1. **P0a：升级部署到包含 `8f654b4` 的已验候选。** 这修复 pre-block tear 的 replay 接线。不要在部署记录中声称旧版本精确为 `9aa31f9`；正确表述是“旧部署匹配 `9aa31f9..a68672c` 的相关文件态，且早于 replay wiring”。**权重：强到可以据此行动。**
2. **P0b：实现已裁决的 MCP-driven synthesized continuation。** 对 `/v1/messages` 且至少一个完整块已交付的可继续失败，生成 `turn_interrupted(...)` tool block并正常结束该 turn；这才直接回答本次事故。它与升级可并行设计，但部署基线应先统一。**权重：强到可以据此行动。**
3. **P1a：修复 `StreamEnding.COMPLETE` 被 caller 当作 `ABANDON` 的遗漏。** 这是窄而确定的成功路径修复。**权重：强到可以据此行动。**
4. **P1b：为不适用 MCP continuation 的已识别 transport ending 定义并实现 SSE `error` fallback。** 我倾向复用现有 Anthropic error event envelope，但错误 code/message 应按 ending 分类，不能把任意 local exception 都命名成 upstream incomplete。**权重：只是倾向；适用 route、错误分类和 fallback 顺序需要 Spec。**
5. **与 P0b/P1b 同 patch处理预期异常的 traceback。** 已经转成完整协议 ending 的分支 `return`；未知异常继续 raise。不要另立一个“消除 traceback”的宽泛 P2。**权重：强到可以据此行动。**
6. **不做上游动机归因。** **权重：强到可以据此行动。**

如果只能先做一件运行操作，先升级；如果只能先做一件代码工作，先实现 MCP-driven continuation，因为它是本次 post-block incident 的既定产品行为。把 `buffering_policy` 改为 `full` 虽能让相同位置的 reset 变成 transparent replay，但会延迟所有块、提高内存驻留，只能作为已知权衡下的临时配置选择，不应伪装成修复。

## 六、实际运行证据

### A. traceback 行签名匹配五个提交，不是一个

运行了遍历 `git rev-list --all` 的 Python probe，同时要求以下四个条件全部成立：`stream.py:206` 是 `async for chunk in inner`、`stream.py:240` 是 `async for pull in events`、`stream.py:270` 是 `raise torn`、`keepalive.py:126` 是 `await pending`。输出：

```text
a68672c fix: stop the driver answering a cancellation as though it were a failure
b64003e fix: scope the web-search model list to the provider that owns it
fa628e1 test: commit the catalog capture the web-search model list is argued from
767d0f2 feat: hosted web search is off until the config turns it on
9aa31f9 refactor: a torn body is a network failure, not a kind of its own
matches=5
```

### B. httpcore root cause、httpx outer exception与 retry reason

运行 `uv run python`，在 `httpx2._transports.default.map_httpcore_exceptions()` 内抛出实际 `httpcore2.RemoteProtocolError`，再分别检查 outer exception与 literal root：

```text
root=httpcore2.RemoteProtocolError
outer=httpx2.RemoteProtocolError
cause_is_root=True
normalized=UpstreamError
reason=network
literal_httpcore_normalized=None
```

### C. 同一 thinking block + reset 在 `block` 与 `full` 下的 HEAD 行为

运行 `uv run python`，首尝试发送一个闭合的 signed thinking block 后抛 `httpx2.RemoteProtocolError`，reopen 返回一条完整 replacement stream。输出：

```text
policy=block reopened=0 raised=RemoteProtocolError error_frame=False message_stop=False bytes=677
policy=full reopened=1 raised=none error_frame=False message_stop=True bytes=701
```

这证明 `think(enc:1)` 是否意味着已经交付取决于 buffering policy，也证明默认 `block` 下 HEAD 对这次位置会 `ABANDON`。

### D. clean EOF 的带内 error 与 targeted tests

运行 clean EOF probe，先交付一个完整 text block，再无 terminal 地正常结束：

```text
raised=none error_frame=True incomplete_code=True message_stop=False
```

运行：

```bash
uv run pytest -q \
  tests/unit/pipeline/delivery/test_stream_delivery.py::test_a_truncated_stream_ends_in_an_error_event_and_never_claims_success \
  tests/unit/pipeline/delivery/test_stream_delivery.py::test_an_upstream_tear_is_still_raised_rather_than_framed \
  tests/unit/pipeline/delivery/test_stream_delivery.py::test_a_stream_the_client_already_saw_is_not_replaced \
  tests/int/test_pipeline_app.py::test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end
```

输出：

```text
....                                                                     [100%]
4 passed in 2.24s
```

### E. terminal event 已收齐后 reset 仍被错误抛出

运行 `uv run python`，上游依次发送完整 text block、`message_delta(end_turn)`、`message_stop`，然后抛 `httpx2.RemoteProtocolError`。输出：

```text
terminal_seen=True stop_reason=end_turn raised=RemoteProtocolError message_stop_delivered=False
```

## 七、最终票

**VERDICT：needs-fix。** 原报告的主控制流分析和“upgrade 有价值、不能先吞异常、不追上游动机”判断可靠，但精确版本归因错误；更重要的是，它遗漏了用户已经裁决的 MCP-driven post-block continuation，把本次真正应实现的行为降成了一个待裁决的通用 SSE error 扩面问题，并把协议回答与停止抛异常拆成了不应独立交付的两个优先级。另有一个原报告未覆盖的 caller bug：`StreamEnding.COMPLETE` 仍被抛成 transport failure。
