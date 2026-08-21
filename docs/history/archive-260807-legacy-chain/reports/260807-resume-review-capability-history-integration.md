# Capability + History integration 只读预审

基线：`main` capability commit `bd86207b4fdb55b7c10c795118f61ba693192003`；History source `b1df8f910c590033e83d5cafcd5e514f12bab937`。Integration 树 `integrate/260807-post-capability` 当前仍以 `bd86207` 为 HEAD，但 History 合并结果已经 staged 且无 unmerged path，因此以下同时是合并清单与快速事实核对。

## 共享 `client.py` 必须同时保留的符号与调用顺序

- Imports 必须同时保留 `ConversionFact`、`ReasoningCapabilityFacts`、`ReasoningEffortBand`、`ConvertedResponse`；当前 integration 位于 `src/app/anthropic/client.py:21-29`。
- 必须保留 `AnthropicAttemptResult`，字段为 `response`、`converted_request_facts`、`converted_response`；当前 integration 位于 `src/app/anthropic/client.py:80-83`。
- 兼容入口 `send_prepared()` 必须委托 `send_prepared_attempt()` 后只返回 `.response`；executor 必须调用 `send_prepared_attempt()`，不能退回只返回 `httpx.Response` 的旧链路。当前 integration 位于 `src/app/anthropic/client.py:175-197` 与 `src/app/pipeline/executor.py:280-284`。
- Responses leg 的顺序必须是：根据 `prepared.resolved_model` 调用 `_reasoning_capabilities()` → 把结果作为 `reasoning_capabilities=` 传给 `convert_messages_request_to_responses()` → 发送 `converted_request.wire` → 非成功响应仍用 `AnthropicAttemptResult` 携带 request conversion facts → 成功响应完成 Responses→Anthropic 转换后，用同一结果同时携带 request facts 与 `ConvertedResponse`。当前 integration 位于 `src/app/anthropic/client.py:238-293`。
- `_reasoning_capabilities()` 必须完整保留 capability commit 的 fail-closed 语义：catalog/model 缺失返回未知，重复或空 effort 失效，预算上下界只有字段显式存在才视为已知，只有 singleton effort 才生成 enabled/adaptive 映射。当前 integration 位于 `src/app/anthropic/client.py:306-345`。

## Executor / History invariants

- 每次 attempt 必须在 `PRE_SEND` 后重建 `PreparedAnthropicRequest`，再调用 `send_prepared_attempt()`；这样 pre-send 修改后的 thinking 会重新用 resolved-model capability facts 转换，同时该 attempt 的 conversion facts 不会丢失。
- 非流式成功顺序必须保持：读取 body → 执行 response hooks → 严格校验最终 client-visible body → 写入 `context.normalized_response`、`context.final_response_payload`、当前 attempt 的 request/response conversion facts 与 exact usage → `coordinator.notify_success()` → `limiter.report_success()` → 发布 `ObserverEvent.RESPONSE` → transition 到 `COMPLETED` → 发布 `FINALIZE` → `history.finalized(context)`。当前 integration 的关键区间为 `src/app/pipeline/executor.py:301-423`。
- body 读取、response hook、最终 wire 校验或 success callback 任一步失败时，不得发布成功 `RESPONSE`，不得校准 limiter，不得持久化 response/usage 成功事实；必须走单一 failure lifecycle。
- retry 后 `context.conversion_facts` 只投影最终成功 attempt，且每条 record 保留 attempt 与 request/response provenance；不得把失败 attempt 的 request facts 混入最终 History summary。
- History 只在 `RequestState.COMPLETED` 时持久化 `final_response_payload` 与 usage summary；失败条目不得带成功 response/usage。完成态 response 必须等于 response hooks 后实际返回给 client 的最终 payload；usage 优先保留 typed exact facts，缺失时才落 estimated summary。当前 integration 位于 `src/app/history/consumer.py:20-112`。

## 最小测试 selector

在 integration cwd 下，用项目现有虚拟环境并令 `PYTHONPATH` 指向 integration 的 `src`，至少运行：

- `tests/smoke/test_anthropic_responses_route.py::test_pre_send_reasoning_modification_is_reconverted_with_capability_facts`
- `tests/smoke/test_anthropic_responses_route.py::test_unknown_reasoning_capabilities_fail_closed_without_model_name_guessing`
- `tests/smoke/test_anthropic_responses_route.py::test_responses_reasoning_budget_uses_exact_catalog_boundaries`
- `tests/component/test_pipeline_executor.py::test_responses_success_persists_hooked_response_and_exact_facts`
- `tests/component/test_pipeline_executor.py::test_failed_final_response_publishes_no_success_callbacks`
- `tests/component/test_pipeline_executor.py::test_success_callbacks_precede_response_commit_once`
- `tests/component/test_pipeline_executor.py::test_history_preserves_request_and_response_conversion_provenance`
- `tests/component/test_pipeline_executor.py::test_history_projects_only_final_success_attempt_conversion_facts`
- `tests/unit/test_anthropic_response_validation.py::test_strict_wire_validator_accepts_sdk_messages`
- `tests/unit/test_anthropic_response_validation.py::test_strict_wire_validator_rejects_invalid_messages`

快速事实核对：上述显式 selector 已在 integration 源码上通过，且测试前后 Git 状态哈希一致。除共享 `client.py` 外的所列 History 文件与 `b1df8f9` 对应 blob 一致，capability smoke 文件与 `bd86207` 对应 blob 一致，staged diff 通过 `git diff --cached --check`。

## 禁止对共享 `client.py` 整文件选边

- 选择 capability／ours 整文件会丢掉 `ConversionFact`、`ConvertedResponse`、`AnthropicAttemptResult`、`send_prepared_attempt()` 及两类 conversion facts 的返回路径；executor 随即失去 History 所需的 attempt result contract。
- 选择 History／theirs 整文件会丢掉 `ReasoningCapabilityFacts`、`ReasoningEffortBand`、`_reasoning_capabilities()` 及 `reasoning_capabilities=` 参数流；这会直接回退 `bd86207` 已修复的 resolved-model capability routing。
- 因此只能语义合并共享文件：保留 capability facts 作为每次 request conversion 的输入，同时保留 `AnthropicAttemptResult` 作为该次 conversion facts 的输出载体。当前 staged integration 已满足这两个方向；不要再用 `checkout --ours/--theirs`、整文件复制或整文件 restore 覆盖它。
