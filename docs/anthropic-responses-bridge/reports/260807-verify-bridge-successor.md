# Anthropic Responses bridge successor 独立验收

## 验收身份

- **候选**：`/home/xp/src/ghc-api-proxy-py-integrate-successor`，分支 `integrate/260807-bridge-successor`，`HEAD=c43db35a7a5851225b55ce31b8edbec2cf90917f`。
- **base**：`80bc8f252b46c511f428af1d97159a5980ee9dc9`；已实跑 `git merge-base --is-ancestor` 并通过。
- **冻结 oracle**：`docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。该值由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉复核一致。
- **只读边界**：候选工作树在验收前后均为 clean，HEAD 未变化；候选树未写入测试、fixture、cache 或生产文件。本报告是本轮唯一写入。

## 总体判定

- **本轮 scoped verdict**：**PASS**。
- **完整 stream 产品状态**：**`UNVERIFIED`**。
- **缺陷**：未发现违反本轮验收矩阵的实证偏差。
- **边界**：真实 ASGI non-stream 路径与 typed stream pre-attempt reject 已验；parser→delivery typed core 已验。当前真实 `/v1/messages` stream 路径仍未把 Responses parser／delivery core 接入下游 ASGI SSE transport，故本报告不把 typed core 的 PASS 外推为完整 streaming bridge PASS，也不覆盖 HTTP SSE chunk parser、真实 downstream disconnect、retry、quota、backpressure、shutdown 或 post-commit partial-failure 的端到端行为。

## 从 Spec 独立推导的验收矩阵

| ID | Spec 可观察合同 | 独立 oracle | 结果 |
|---|---|---|---|
| A1 | Non-stream 必须走真实 Anthropic ASGI owner；Responses body 先转换为 Anthropic body，再进入 response hook，hook 后结果才提交 | 真实 `TestClient` 请求 `/v1/messages`；独立 target 只允许 `send_responses(stream=False)`；hook 断言输入已是 Anthropic `message`，再把 text 改为 `hooked text`；客户端最终只看到 hook 后 body | **PASS** |
| A2 | Responses-only 的 `stream=true` 在未实现 typed stream transport 时必须 typed reject；零 upstream 调用；失败 lifecycle 只 finalize 一次 | 真实 ASGI 请求返回 HTTP 400、code `responses_stream_not_supported`；Responses／Messages transport 调用均为零；context 为 `FAILED`、attempts 为空；trace 为 `request_received → error → finalize` | **PASS** |
| A3 | Unknown Responses event 不得 silent drop 或变成成功 terminal | Parser 产生 `UnsupportedResponsesEvent`；delivery 抛出 `ResponsesDeliveryError(kind="unsupported", code="unsupported_responses_event")`；sink 零 bytes、success terminal 未接受 | **PASS** |
| A4 | Upstream terminal `error` 不得变成 `end_turn`／`message_stop` | Parser 保留 `error／overloaded` typed terminal；delivery 拒绝；sink 零 bytes、success terminal 未接受 | **PASS** |
| A5 | Delivery 只能提交已闭合的连续 source prefix；完整 blocks 在 terminal 前且 terminal 唯一 | 先完成 later item 时 sink 仍为空；first 闭合后按 `first → later` 提交；批次顺序为首 block 含 `message_start`、第二 block、最后唯一 `message_delta → message_stop`；block index 为 `0,1` | **PASS** |
| A6 | Terminal 不得越过仍 open 的 source | `response.completed` 到达时保留 open block snapshot；parser 将其定性为 `incomplete_lifecycle`；delivery 拒绝，sink 零 bytes且 terminal frontier 未前进 | **PASS** |
| A7 | Empty reasoning item 仍须一 item 一 thinking block，并发出 bare project marker | 一个 `summary=[]`、`encrypted_content=""` 的 reasoning item 产生且只产生一个 committed block；envelope 为 `message_start → content_block_start(thinking) → signature_delta(bare marker) → content_block_stop`；signature 精确为 `ghc-api-proxy:synthetic-reasoning:v1` | **PASS** |
| A8 | Responses-specific、auth、cookie、内部 headers 不得下发；只保留明确归一项并由 Anthropic 层生成 content headers | 真实 ASGI response 保留 `request-id`、`retry-after`、`x-ratelimit-*`；过滤 `authorization`、`set-cookie`、`openai-processing-ms`、`x-internal-trace`；upstream 假 `content-length=99999` 未泄漏，最终 `content-type` 为 Anthropic JSON response | **PASS** |

## 实跑证据

### 独立 harness

在同一次 gated shell 中先打印并断言物理 cwd、Git top-level、分支、完整 HEAD、base ancestor 与 clean worktree，再以 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-integrate-successor/src` 执行不落盘 Python harness。进程内真实 import 与请求路径均来自候选树。

独立 harness 输出的逐项标记如下，全部为 PASS：

- `real_asgi_nonstream_hook_trace`
- `responses_header_filtering`
- `typed_stream_reject_hook_trace`
- `parser_unknown_typed_delivery_reject`
- `parser_error_terminal_reject`
- `delivery_complete_prefix_order_and_terminal`
- `empty_reasoning_one_bare_block`
- `terminal_cannot_cross_open_source`
- `positive_control_bypass_finalizer_bites`

基线执行退出码为 0；post-gate 再次确认 `HEAD=c43db35a7a5851225b55ce31b8edbec2cf90917f` 且候选工作树 clean。

### 正控

独立 harness 在进程内临时把生产 `_finalize_failure` monkeypatch 为 no-op，不改磁盘文件；随后重放同一真实 ASGI typed stream reject。原 oracle 必须同时观察唯一 History finalize、`FAILED` state 与 `request_received → error → finalize` trace。旁路后该 oracle 如预期转红，输出：

`POSITIVE_CONTROL_RED bypass_finalizer detected_by=typed_stream_reject_hook_trace`

恢复原函数后进程正常结束，候选工作树仍 clean。该正控证明 typed reject 的绿灯实际依赖生产 failure finalizer，不是只检查 HTTP 400 的旁路假绿。

另有独立 terminal-over-open 反例：在 source 仍 open 时注入 `response.completed`，parser／delivery 将其拒绝为 `incomplete_lifecycle`，没有产生任何 downstream bytes或成功 terminal。

### 候选相关回归

另一次 gated 调用通过进程内 import oracle确认 `app.__file__=/home/xp/src/ghc-api-proxy-py-integrate-successor/src/app/__init__.py`，随后运行：

- `tests/smoke/test_anthropic_responses_route.py`
- `tests/smoke/test_anthropic_block_delivery.py`
- `tests/unit/test_responses_stream_parser.py`

pytest 退出码为 0，runner 摘要为 `44 passed in 3.50s`。该数量是 runner 单次摘要，未以第二种测试收集方法交叉计数，因此仅作运行记录，不作为 PASS 的独立数字判据。post-gate 再次确认候选 HEAD 未变化且工作树 clean。

## Hook trace 与 wire 观察

### Non-stream 成功

`request_received → response observer → response hook receives normalized Anthropic message → response hook mutation → finalize`

客户端最终 body 中：

- empty reasoning 为一个 bare thinking block；
- text 为 hook 修改后的 `hooked text`，而非 upstream 原始 `upstream text`；
- History started／finalized 指向同一 context，终态为 `COMPLETED`；
- 仅发生一次 Responses exchange。

### Typed stream reject

`request_received → error → finalize`

客户端获得 Anthropic-compatible HTTP 400 error，code 为 `responses_stream_not_supported`；upstream exchange 数为零；context 终态为 `FAILED`，attempts 为空。

## 未验证项

以下均明确为**未验证**，不得从本报告的 scoped PASS 推导为已通过：

- Responses HTTP SSE raw chunk／CRLF／multi-line `data:`／`[DONE]` 到 typed parser 的真实 transport wiring；
- typed parser／delivery 到真实 ASGI streaming response 的 headers commit、socket write、client visibility 与 cleanup；
- 完整 stream 的 response hooks、History usage、cancel、shutdown、retry、quota、backpressure、memory budget、partial failure 与资源关闭；
- upstream WebSocket 与 HTTP SSE 的端到端语义等价；
- 完整 Spec 的 route、request conversion、non-stream 全字段矩阵、usage 数值空间、approval modification、tokenization 和 system lifecycle。

## 结论

`integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f` 在本轮明确范围内为 **PASS**：真实 ASGI non-stream hook 顺序与最终 body成立；typed stream reject具备零 upstream调用和唯一 failure finalizer trace；parser unknown／error保持 typed并被 delivery拒绝；delivery维持完整连续 block顺序且 terminal不能越过 open source；empty reasoning产生一个 bare thinking block；Responses headers在真实 ASGI response中被过滤与归一化。正控旁路 failure finalizer后同一 reject oracle按目标原因转红。

由于 typed parser／delivery 尚未接入真实 ASGI Responses streaming transport，**完整 stream 继续为 `UNVERIFIED`**。本报告不授权把局部 core PASS 外推为完整 bridge 产品 PASS。
