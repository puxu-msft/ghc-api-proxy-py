# Dynamic capture v14 最终只读验收

## 评审范围

判据来源是 ACTIVE v14 `.dev/docs/raw-capture/spec.md` 与本轮用户给出的条件式 raw capture 合同。范围覆盖 HTTP API + SQLite 精确规则、未命中不持久化正文、命中后的 CBOR Sequence/zstd 真实 wire capture、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate 的 request/response bytes 与 complete boundaries、首次 body pull 前关闭 streaming response 的不完整边界、普通 upstream detail/logger/FailureSummary/InterruptionObservation/ResponseObservation 的安全投影、proxy-owned messages，以及 legacy JSON rejection persistence 的 inactive 状态。

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终实现与相关测试。没有修改实现或测试，没有读取、输出或持久化 capture 正文、认证信息、token 或 credential，也没有操作现有 4141 服务。按用户要求，仅将本报告写入指定路径。

## 总体 verdict

**needs-fix：发现 2 个高置信度 major 问题，当前不能报告 pass。**

## Blocker 数

0。

## Findings

### DYN-CAP-09 —— major —— 安全投影实现已收紧，但最终回归测试仍要求废止的 upstream raw text

- `finding_id`: `DYN-CAP-09`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `tests/int/test_pipeline_app.py:8499-8500`
- `related_locations`: `tests/int/test_pipeline_app.py:8480-8490`、`tests/int/test_pipeline_app.py:8951-8952`、`src/app/server/routes/inference.py:203-230`、`src/app/observability/request_completion.py:780-814`
- **判据**：ACTIVE v14 要求普通 upstream detail/logger、`FailureSummary`、`InterruptionObservation` 和 `ResponseObservation` 只保留安全的 type/status/code 或固定 presence metadata；proxy-owned message 可以保留，但 upstream raw error text/body 不得进入普通投影。
- **证据**：当前实现对未归一化 upstream exception 已返回固定的 `upstream request failed before a response` 或 `upstream exception: <module>.<type>`，Responses error observation 也使用固定安全字段。可是最终测试树仍直接断言 upstream 异常原文或长度截断后的 raw-text 形状。最小安全回归运行结果为 3 passed、4 failed，失败项是 `test_a_long_upstream_failure_is_cut_before_it_reaches_the_line`、`test_a_long_failure_is_cut_on_the_hand_over_line_too`、`test_runtime_upstream_stream_failure_is_reported_without_escaping_the_app` 和 `test_a_tear_after_a_turn_that_ran_out_of_room_is_reported_alongside_the_hand_over`。
- **影响**：生产实现方向符合 v14 安全边界，但最终测试合同与当前 Spec 冲突，且 focused regression 不绿，不能把这份工作树验收为完成。
- **建议修复方向**：把这些断言改为固定 type/status/reason、attempt 和 completeness metadata；保留 hand-over、deadline 等 proxy-owned message 的独立断言，但不要把 upstream 原文重新加入普通 completion、logger 或 structured record。

### DYN-CAP-11 —— major —— CodeBuddy 非流式 aggregate 的 response-discard/cleanup 接缝仍捕获 synthetic response，而不是真实 SSE wire body

- `finding_id`: `DYN-CAP-11`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/direct_driver/base.py:198-211`
- `related_locations`: `src/app/model_provider/codebuddy_client/client.py:120-162`、`src/app/model_provider/codebuddy_client/client.py:258-266`、`src/app/pipeline/direct_driver/base.py:497-518`
- **判据**：命中规则后，所有 provider、aggregate、cleanup 和 response-discard paths 都必须保留实际 upstream request/response wire bytes；CodeBuddy 的 synthetic aggregate response 只能用于 pipeline 语义和交付，不能替代真实 SSE capture。
- **证据**：CodeBuddy 非流式路径在 `aggregate_stream()` 中把真实 SSE 累积到 `response.extensions["upstream_raw_response_body"]`，随后返回一个 synthetic JSON `httpx2.Response`。正常 buffered inference path 会读取该 extension，但 direct driver 在后续 subscriber/attempt-success 步骤失败而进入 `not handed_off` 的 finally 时调用 `capture_returned_upstream_response()`，该 helper 只读取 `response.content`，因此把 synthetic JSON 写入 `upstream.response.body`。不落盘探针只输出事件类型和长度，结果为 capture response length `50`、extension 中实际 wire length `22`，证明两者不相同；探针没有输出正文。
- **影响**：命中 capture 的 CodeBuddy aggregate 请求一旦在 provider 返回后、交付确认前进入 response-discard/cleanup 接缝，capture 不能重放或核对真实 SSE wire response，违反 v14 的全路径真实 bytes 合同。
- **建议修复方向**：让 `capture_returned_upstream_response()` 优先读取明确的 raw upstream body extension，并仅在没有 raw extension 时回退到 `response.content`；保留 synthetic response 作为 pipeline 解析输入，不让它覆盖 capture。

## 上轮 finding 完成度

- `DYN-CAP-09`：**未闭合**。安全投影的生产代码已改为固定 metadata，但相关最终回归断言仍未同步，focused regression 仍失败。
- `DYN-CAP-10`：**实现路径已闭合**。当前 `_StreamAccounting` 用 `upstream_body_started` 做幂等保护，首次 body pull 前的 response cleanup 写入 `response.end(false)` 与 `attempt.end(false)`；不落盘探针只观察到一次 `response.end=false` 和一次 `attempt.end=false`。本轮没有将 DYN-CAP-10 重新列为新 finding。
- `RC-009`、`RC-010`：CodeBuddy 正常 aggregate、partial/cleanup normalization 与正常 buffered path 的 raw SSE/synthetic 分离仍成立；DYN-CAP-11 是此前未覆盖的 response-discard/cleanup 接缝。

## 已核验且符合当前 Spec 的面

- SQLite rule store、唯一约束、provider/resolved model/session/可选 agent 的规范化精确匹配、HTTP `GET/POST/DELETE /api/debug/capture-rules` 和下一次匹配立即生效的接线存在。
- 未命中请求不会创建 capture 或持久化 request/response body；命中后在第一次 upstream attempt 前补录已读取的 inbound body。
- 新 capture 使用每 item 独立 zstd frame 的 CBOR map sequence，路径只使用 identity hash；缺失 agent-id 使用不可与普通 agent 字符串碰撞的独立分组；旧 `.jsonl.zst` 只计入总配额，不参与新格式读写。
- writer acknowledgement、quota reservation、partial-write poison、跨新 store 的 reader 校验、request-incomplete warning、provider/status/partial/count/retry wire evidence，以及 legacy JSON rejection persistence inactive 的 focused paths 均通过。
- 首次 body pull 前关闭 streaming response 的实现探针确认了幂等的不完整 response/attempt boundary。

## 执行的最小相关验证

- `uv run pytest -q --tb=no --disable-warnings tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：34 passed。
- `uv run pytest -q --tb=no --disable-warnings tests/int/test_pipeline_app.py -k 'opt_in_raw_capture_records_client_and_upstream_bodies or raw_capture_keeps_both_failed_account_switch_attempts or raw_capture_is_selective_and_rule_api_is_persistent or rule_selected_count_capture_keeps_each_upstream_retry or rule_selected_rejection_capture_keeps_upstream_wire_evidence or buffered_responses_status_error or response_observation or error_message or count_tokens'`：21 passed，257 deselected。
- `uv run pytest -q --tb=no --disable-warnings tests/unit/pipeline/test_response_observation.py -k 'provider_error_observation_keeps_only_safe_error_metadata or provider_error_summary_bounds_type_and_code_as_well_as_message or stream_error_event_observation_redacts_provider_message or buffered_unreadable_body_has_a_specific_unavailable_issue'`：7 passed，64 deselected。
- 最终安全回归选择集：3 passed，4 failed，271 deselected；失败均落在 DYN-CAP-09 的旧 raw-text assertions。
- 两个不落盘探针只输出 metadata：一个确认 pre-first-pull close 产生一次 `response.end=false` 与一次 `attempt.end=false`；另一个确认 CodeBuddy aggregate response-discard helper 捕获的 response bytes 长度不同于 raw SSE extension，未输出正文或秘密。

## 搜索面与未覆盖面

已读 ACTIVE v14 Spec、项目开发工作流、debug capture SQLite store、ops HTTP routes、inference capture lifecycle、raw capture writer/reader、count path、direct driver、GHC/OpenAI-compatible/CodeBuddy client、request completion、request logger、Responses observation、stream cleanup、rejection shim 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未修改被检对象。除 DYN-CAP-09 与 DYN-CAP-11 外，未发现新的高置信度缺陷。
