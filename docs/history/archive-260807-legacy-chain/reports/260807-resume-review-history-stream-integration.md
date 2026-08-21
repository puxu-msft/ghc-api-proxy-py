# History + stream integration 只读预审

## 范围与判定

- **main**：`/home/xp/src/ghc-api-proxy-py@38bb06ff0eefef69fd4fdab830e67ff549563a20`。
- **stream source**：`/home/xp/src/ghc-api-proxy-py-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。
- **integration**：`/home/xp/src/ghc-api-proxy-py-integrate-stream`，分支 `integrate/260807-post-history-stream`，预审时 `HEAD` 仍为 main，source delta 已进入 index，且无 unmerged path 或冲突标记。
- **verdict**：**修复 1 个 major 后可继续；当前不可提交集成结果。** `client.py` 的 capability、History facts 与 stream 三方语义合并已基本正确，但真实 `HistoryConsumer` 与 stream route 的调用契约不兼容。未扩大测试矩阵，也未运行全仓测试。

## 共享 `client.py` 必须同时保留

- **Capability 输入**：保留 `ReasoningCapabilityFacts`、`ReasoningEffortBand` 与 `_reasoning_capabilities()`；每个 Responses attempt 都必须按 `prepared.resolved_model` 取得 catalog facts，并通过 `reasoning_capabilities=` 传入 `convert_messages_request_to_responses()`。catalog／model 缺失、重复或空 effort、预算字段未显式出现等情形继续 fail closed，不能退回 model-name 猜测。
- **History facts 输出**：保留 `ConversionFact`、`ConvertedResponse` 与 `AnthropicAttemptResult(response, converted_request_facts, converted_response)`；`send_prepared()` 只作兼容包装，executor 必须调用 `send_prepared_attempt()`。非成功 Responses HTTP 响应也必须保留 request conversion facts。
- **Stream 路径**：`_send_responses(..., stream: bool)` 必须把同一 `stream` 值传给 `send_responses()`；流式成功返回 `AnthropicAttemptResult(upstream, converted_request_facts=...)`，不得读取或关闭仍由 route 消费的 upstream body；非流式才执行完整 body conversion 并在 `finally` 关闭 upstream。
- **当前快速核对**：integration 的最终 `client.py` 已同时满足以上三项。禁止再对该文件使用 ours／theirs、整文件复制、整文件 restore 或其他整文件选边。

## 共享 `executor.py` 必须同时保留

- 每个 attempt 在 `PRE_SEND` 后重建 `PreparedAnthropicRequest`，调用 `send_prepared_attempt()`；stream 与 non-stream 共用 attempt、retry、failure finalizer，不另建第二条隐式 lifecycle。
- 非流式成功顺序保持：读取 body → response hooks → 对最终 client-visible body 做 strict Anthropic validation → 写入 `normalized_response`、`final_response_payload`、最终成功 attempt 的 request／response conversion facts 与 typed usage → success strategy／limiter → `RESPONSE` → `COMPLETED` → `FINALIZE` → History。
- 读取、hook、strict validation 或 success callback 任一步失败，都不得发布成功 `RESPONSE`、不得写成功 response／usage facts，并且只走一次 `ERROR`／`FINALIZE`／History failure。
- 流式成功只进入 `STREAMING` 并把 upstream 交给 route；不得在 executor 提前发布 `RESPONSE`／`FINALIZE` 或 History completed。integration 的最终 `executor.py` 当前保留了这些边界。

## 共享 `route.py` 必须同时保留

- Responses stream 必须经过 delayed-start ASGI sink、`render_responses_as_anthropic_sse()` 与同一个 `ResponsesAnthropicStreamState`；authoritative block 完成前不发布 success headers／body。
- 保留 prefetch disconnect 与再次 cancellation 下的 shielded cleanup：upstream close、observer `FINALIZE`、History finalize 均完成且恰好一次；不得增加 retry。
- 保留真实 delivery frontier：headers、message start、block、terminal 的 accepted／uncertain 状态只能由 ASGI send outcome 推进。postcommit protocol error 输出单一 Anthropic `error` SSE 且无 `message_stop`；`max_output_tokens` incomplete 为合法 `max_tokens`，其他 incomplete reason 显式失败；terminal identity 与 EOF seal 不得回退。
- History 必须从 delivery ledger 投影：成功保存完整 committed Anthropic response 与 normalized usage；postcommit failure 保存 committed prefix 与 error；delivery uncertain 保存 possibly-visible／frontier facts，不能伪装 committed 或丢成 `None`。

## 事实性发现

[major] `src/app/routes/anthropic.py:116` 与 `src/app/history/consumer.py:25` — stream route 调用 `history.finalized(context, response=response)`，但 integration 中 main 版 `HistoryConsumer.finalized()` 只接受 `context`。真实启用 History 的 stream 在 cleanup／finalize 阶段会抛 `TypeError`；source smoke 的 `RecordingHistory` 恰好接受 `response=`，因此会假绿。**修复方式**：语义合并 `HistoryConsumer.finalized()`，接受可选的 stream projection，同时保留 main 的 completed-only `final_response_payload`、typed usage 与 conversion facts 逻辑。优先级必须是：显式 stream projection 用于 stream 的 success／partial／uncertain 记录；未提供 projection 时使用 main 的 non-stream context facts；失败 non-stream 不得获得成功 response／usage。补一个使用真实 `HistoryConsumer` 的定向 stream 回归，不能继续只靠签名更宽的 fake。

## 最小测试 selector

修复上述契约后，只运行以下具名节点；不扩张到 retry、quota、resident backpressure 或真实 socket partial-write 矩阵：

- `tests/smoke/test_anthropic_responses_route.py::test_pre_send_reasoning_modification_is_reconverted_with_capability_facts`
- `tests/component/test_pipeline_executor.py::test_responses_success_persists_hooked_response_and_exact_facts`
- `tests/component/test_pipeline_executor.py::test_failed_final_response_publishes_no_success_callbacks`
- `tests/component/test_pipeline_executor.py::test_success_callbacks_precede_response_commit_once`
- `tests/unit/test_anthropic_response_validation.py::test_strict_wire_validator_accepts_sdk_messages`
- `tests/unit/test_anthropic_response_validation.py::test_strict_wire_validator_rejects_invalid_messages`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_max_output_tokens_without_usage_uses_estimated_zero_usage`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_success_terminal_is_validated_before_message_stop`
- 新增一个只使用真实 `HistoryConsumer` 的 stream projection 节点，覆盖 success 与 failed／uncertain 至少各一路；该节点是当前 fake 无法替代的集成接缝，不要求扩展其他 stream 状态矩阵。

## 继续条件

只有在 `HistoryConsumer.finalized()` 的双来源语义合并完成、上述最小 selector 通过、`git diff --check` 通过且快速 diff 未发现新的 major 时，才可继续提交 integration。任何共享 `client.py`、`executor.py`、`route.py` 或 `history/consumer.py` 都必须逐 hunk 语义合并，禁止整文件选边。
