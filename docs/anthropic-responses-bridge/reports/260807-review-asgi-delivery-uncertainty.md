# ASGI delivery uncertainty 快速复核

- **评审范围**：只读复核 current `main@941299fe5a5275c4a5fc327d172a1deeccfb3085` 已有的 ASGI accepted／uncertain 实现与三个现成测试。唯一写入为本报告；未做新设计或测试矩阵。
- **总体 verdict**：**可关闭重复开发项。** 现有实现已覆盖 ASGI `send(http.response.start)` 与 `send(http.response.body)` 返回异常时的 accepted／uncertain 归类，并把 body delivery uncertainty 投影为失败 History。0 blocker／0 major。
- **blocker 数**：0。
- **major 数**：0。
- **双视角覆盖证据——机械核对**：对账 `src/app/streaming/sse.py:131-171` 的 start／first-body 异常分支、`src/app/routes/anthropic.py:62-116,255-273` 的 hook 接线与 History 收口、`src/app/delivery/responses_anthropic_stream.py:76-89` 和 `src/app/delivery/anthropic_sse.py:849-914` 的 pending acknowledgement。实跑三个既有具名测试，pytest 退出码为 0，现场输出为 `3 passed in 1.80s`；测试前后工作树 status 哈希一致。
- **双视角覆盖证据——第一人称执行**：分别模拟 response start 尚未确认即由 ASGI `send` 抛错，以及首个 body batch 已交给 ASGI `send` 但调用抛错。前者在重抛前调用 start uncertain hook；后者在重抛前以原 batch bytes 调用 body uncertain hook，沿同一 `DeliverySession` 将对应 pending batch 标为 uncertain，随后 route finalize 将请求与 History 收口为失败。

## 复核结论

1. **send start／body 失败是否调用 uncertain hook：是。** `DelayedStartStreamingResponse.stream_response()` 对 start 与每个非空 body 的 `await send(...)` 分别包裹异常分支；start 失败调用 `on_start_uncertain()`，body 失败调用 `await on_body_uncertain(batch_bytes)`，然后保留原异常继续抛出。route 将两者分别接到 `ResponsesAnthropicStreamState.mark_headers_uncertain` 与 `mark_body_uncertain`。
2. **DeliverySession pending→uncertain：是。** buffered sink 首先返回 `pending`，`DeliverySession` 将 batch 留在 `_pending`；body uncertain hook 用同一 bytes 调用 `acknowledge_data_if_pending(..., "uncertain")`，匹配 pending batch 后进入 `frontier.mark_uncertain(...)`。首 body 场景下 headers 已 accepted，而 `message_start` 与 block 变为 uncertain，`committed_blocks` 保持为空。
3. **History failed code `delivery_uncertain`：是。** `_history_stream()` 在未完成且 frontier 为 delivery uncertain 时构造 `ApiError(code="delivery_uncertain")`，调用 `context.fail(...)`，并把同一错误 code 写入 committed response 后交给 `history.finalized(...)`。现有 route 测试断言 History context 为 `RequestState.FAILED`，context error 与 response error code 均为 `delivery_uncertain`。
4. **两个关键测试：通过。** `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_send_failure_marks_envelopes_uncertain_without_commit` 与 `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history` 均通过。第三个现成 start-hook 测试 `tests/unit/test_streaming_sse.py::test_delayed_response_marks_response_start_send_failure_uncertain` 也通过。

## 事实性发现

未发现问题。0 blocker／0 major，因此关闭对应重复开发项，不再为同一 ASGI accepted／uncertain 行为重复实现。

## 范围边界

本 verdict **只覆盖 ASGI `send` 调用级别的 accepted／uncertain**：调用正常返回视为 accepted，调用抛错视为结果 uncertain。它**不覆盖**底层服务器、socket 或内核在一次失败调用中可能已经写出部分 bytes 的精确 partial-write／partial-bytes 事实，也不对此作保证。

## 主观建议

未提出额外建议；按本轮限定不新增设计或矩阵。
