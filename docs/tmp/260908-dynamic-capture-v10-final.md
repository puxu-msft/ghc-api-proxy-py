# Dynamic capture v10 final read-only acceptance

## 评审范围

本次评审针对当前工作树最终状态，判据为用户给出的条件式 raw capture 合同与 `.dev/docs/raw-capture/spec.md` ACTIVE v10，覆盖 HTTP 管理接口与 SQLite 规则、命中选择、未命中不持久化正文、CBOR Sequence/zstd 存储、配额与 writer acknowledgement、所有 provider attempt 的 request/response wire evidence、429/5xx 与 count retry、普通日志和 structured observation 的错误信息安全边界，以及 legacy JSON rejection persistence 的退役行为。

重点检查了 `src/app/observability/raw_capture.py`、`debug_capture.py`、`rejection_capture.py`，`src/app/server/routes/ops.py` 与 `routes/inference.py`，`src/app/pipeline/direct_driver/base.py`、`pipeline/driver.py`、`observability/request_completion.py`、`observability/request_trace.py`、`pipeline/response_observation.py`，以及 GHC、CodeBuddy、OpenAI-compatible、Xingchen provider error paths。

## 总体 verdict

- verdict: **fail**
- blocker_count: **0**
- major_count: **2**

当前实现不能按 ACTIVE v10 通过最终验收；两个高置信 major defect 都在 CodeBuddy 的非流式聚合路径，分别影响失败归一化与 response wire evidence。

## Findings

### RC-009

- severity: **major**
- status: **open**
- primary_location: `src/app/model_provider/codebuddy_client/client.py:122-135`
- related_locations: `src/app/pipeline/direct_driver/base.py:176-192`
- criterion: v10 修订记录要求 CodeBuddy aggregate/read/cleanup timeout/transport error 归一化并保留 request bytes；失败 attempt 必须进入 raw capture wire evidence。
- evidence: `send_chat_completions()` 对非流式调用在 `aggregate_stream(response)` 外层捕获了 `httpx2.TimeoutException` 和 `httpx2.HTTPError`，但 `finally` 中的 `await response.aclose()` 没有经过 `normalize_upstream_response_error()`。只读内存探针让聚合读取成功、随后 `aclose()` 抛出 `httpx2.ReadTimeout`；实际结果是裸 `ReadTimeout`，不是 `UpstreamTimeout`/`UpstreamError`，且没有 `sent` request bytes。
- impact: provider cleanup timeout/transport failure会绕过 pipeline 的已知错误集合，直接按未知异常结束而不是按 upstream failure 处理；`capture_failed_upstream_attempt()` 只接受 `UpstreamError`/`UpstreamRejected`，因此该 attempt 不写入 upstream request body，违反“每个 attempt 的 wire evidence”与 v10 cleanup 条件。
- recommendation: 将 CodeBuddy 聚合路径的 cleanup 纳入与非 200 response 相同的 primary/cleanup 归一化策略，在 cleanup-only failure 中从 error 或 response attached request 提取 request bytes，并保留既有 primary failure 的优先级与安全 secondary note。

### RC-010

- severity: **major**
- status: **open**
- primary_location: `src/app/model_provider/codebuddy_client/client.py:120-135`
- related_locations: `src/app/model_provider/codebuddy_client/client.py:138-223`；`src/app/server/routes/inference.py:1165-1168`；`.dev/docs/raw-capture/spec.md:50,82-83`
- criterion: 命中 capture 后必须记录每个 provider attempt 的实际 upstream request/response wire body；v10 明确把 CodeBuddy aggregate 纳入该规则。
- evidence: CodeBuddy 无论调用方是否要求流式都把请求改为 `stream=True`。当 `stream=False` 时，`aggregate_stream(response)` 消费真实 upstream SSE，并新建一个内容为聚合后 `chat.completion` JSON 的 synthetic `httpx2.Response` 返回。raw capture 只在 client 返回后由 inference route 记录 `response.content`，而 `aggregate_stream()` 没有 raw capture callback 或原始 chunk 记录路径。
- impact: 匹配规则命中的 CodeBuddy 非流式请求，capture 中的 `upstream.response.body` 是代理生成的聚合 JSON，不是 provider 实际返回的 SSE wire body；聚合读取中途 timeout/transport 时，已经收到的 provider response bytes 也完全没有进入 capture。该实现不能满足 v10 的 response wire evidence 合同。
- recommendation: 在 CodeBuddy provider seam 为聚合路径接入 per-attempt raw capture，按实际读取到的 upstream bytes 记录 response body 与完成状态；synthetic aggregate response 只能继续服务 pipeline 语义，不能替代 raw wire capture。

## 已核验且未发现高置信 defect 的面

- SQLite 规则持久化、唯一约束、规范化精确匹配、可选 agent 匹配、HTTP GET/POST/DELETE 管理接口及 rule API 的选择性行为符合当前测试与代码路径。
- 未命中规则不会创建 request capture 或持久化 request body；命中后会在路由解析后、首次 upstream attempt 前补录已读取的入站 body。
- CBOR map、每 item 独立 zstd frame、`.cborseq.zst` 路径、缺失 agent-id 独立分组、legacy `.jsonl.zst` 配额计入、writer acknowledgement、partial-write poison 与跨 store 校验均有对应实现和测试覆盖。
- CodeBuddy/OpenAI-compatible 非 200 response `aread()` timeout/transport 与 cleanup-only timeout/transport 的 v10 归一化改动在已覆盖路径上成立；新增的 CodeBuddy status-body timeout test 通过，OpenAI-compatible 同等内存探针也得到 `UpstreamTimeout` 且保留 request bytes。
- 429、500、count_tokens retry、account-switch retry 的现有 raw capture 集成测试通过；失败 attempt 的 request/status/body 记录路径对已归一化错误成立。
- ordinary completion log、request completion record 与 Responses structured observation 对 provider error message 使用固定安全标记或 status/type/code 元数据，没有在已检查路径中复制 raw error body/message。
- `rejection_capture` 已成为无持久化副作用的兼容 shim，legacy JSON rejection persistence 不再是 active 行为。

## 执行的最小相关验证

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/openai_compatible/test_provider.py tests/unit/pipeline/test_direct_driver.py -k 'raw_capture or capture or rejection or timeout or wire or provider_error or unconsumed_stream_status_body or cancellation_during_retry_cleanup or deadline_during_retry_cleanup or client_preserves_upstream_rejection'`：35 passed，65 deselected。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'opt_in_raw_capture_records_client_and_upstream_bodies or raw_capture_keeps_both_failed_account_switch_attempts or raw_capture_is_selective_and_rule_api_is_persistent or rule_selected_count_capture_keeps_each_upstream_retry or rule_selected_rejection_capture_keeps_upstream_wire_evidence or response_observation or error_message'`：5 passed，273 deselected。
- `uv run pytest -q tests/unit/pipeline/test_response_observation.py -k 'provider_error_observation_keeps_only_safe_error_metadata or provider_error_summary_bounds_type_and_code_as_well_as_message or buffered_unreadable_body' tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_log.py -k 'provider_error or error or observation'`：81 passed，82 deselected。
- 另执行了只读内存探针验证 RC-009 的 CodeBuddy aggregate cleanup failure；该探针复现裸 `ReadTimeout` 与 request bytes 丢失。探针未写入仓库文件，也未输出任何 request/response 正文或秘密。

## 未覆盖面

本次没有运行全量 regression、Ruff 或 Pyright；用户要求的是最终只读验收与最小相关测试。未对已有 4141 服务执行任何 signal、restart、reconfigure 或 cutover 操作。
