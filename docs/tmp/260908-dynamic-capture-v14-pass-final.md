# Dynamic capture v14 最终只读验收

## 评审范围

判据来源是用户本轮给出的 ACTIVE v14 与条件式 raw capture 合同，以及 `.dev/docs/raw-capture/spec.md`。范围覆盖 HTTP API + SQLite 精确规则、未命中不持久化正文、命中后的 CBOR Sequence/zstd wire capture、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate 的 bytes 与 complete 边界、首次 body pull 前 close 的 incomplete boundary、普通 upstream detail/logger/FailureSummary/InterruptionObservation/ResponseObservation 的安全投影、proxy-owned messages，以及 legacy JSON rejection persistence inactive。

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树的相关最终状态。工作树已有其他未提交改动；本次没有修改实现、测试或其他既有文件，没有读取、输出或持久化 capture 正文、认证信息、token 或 credential，也没有操作现有 4141 服务。

## 总体 verdict

**needs-fix：发现 3 个高置信度 major 问题，另有 1 个 minor 测试合同未同步问题，当前不能报告 pass。**

## Blocker 数

0。

## Findings

### DYN-CAP-12 —— major —— CodeBuddy aggregate 的 generic cleanup failure 丢失真实 wire evidence

- `finding_id`: `DYN-CAP-12`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/codebuddy_client/client.py:135`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:176-195`、`src/app/model_provider/codebuddy_client/client.py:147-263`
- **判据**：ACTIVE v14 修订记录与用户条件要求 CodeBuddy aggregate 的 cleanup failure 仍保留实际 upstream request/response bytes 与不完整 attempt 边界；synthetic aggregate response 不能替代真实 wire evidence。
- **证据强度**：高。当前 `aggregate_stream()` 已把真实上游字节放入原 response extension，但 aggregate 成功后 `response.aclose()` 抛出未归一化的 `RuntimeError` 时，`send_chat_completions()` 直接抛出该异常，未把 request、status 或 extension 中的 response bytes 绑定到异常。随后 direct driver 的 `capture_failed_upstream_attempt()` 只接受 `UpstreamError`/`UpstreamRejected`，对该 cleanup failure 记录 0 个 failed-attempt wire events。只读内存 probe 观察到：异常类型为 `builtins.RuntimeError`、`has_sent=false`、原 response extension 仍有 bytes；独立 capture-helper probe 的 captured event count 为 `0`。probe 没有输出正文。
- **影响**：命中规则的 CodeBuddy 非流式请求在 aggregate cleanup failure 接缝上会留下 attempt 失败，却无法回放已经收到的真实 SSE 或核对已发送 request body，违反完整 wire evidence 合同。
- **修复方向**：cleanup-only failure 必须建立带有 request/status/已观察 response bytes 与 `body_complete` 的 upstream error carrier，或者把原 response evidence 直接交给 capture；随后写入正确的 `response.end` 与 `attempt.end(complete=false)`，同时保留安全普通日志投影。

### DYN-CAP-13 —— major —— proxy-owned client deadline 被错误投影为 upstream stream failure

- `finding_id`: `DYN-CAP-13`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:1440-1463`
- `related_locations`: `src/app/pipeline/delivery/stream.py:497-513`、`tests/int/test_pipeline_app.py:3810-3853`
- **判据**：普通 upstream 投影必须安全；proxy-owned message 可以保留，且不能把 proxy-owned failure 误归因成 upstream failure。
- **证据强度**：高。`stream.py` 的 client deadline 分支明确以 `upstream=False` 调用 `note_runtime_failure()`，但 `_StreamAccounting._ending()` 对所有 `self.failure` 统一调用 `_safe_failure_detail()`，于是 completion line 将 `ClientDeadlineError` 渲染成固定的 `upstream stream failure: app.streaming.deadline.ClientDeadlineError`，而不是保留或准确投影 proxy-owned deadline reason。最小相关测试 `test_a_client_deadline_is_accounted_as_the_failure_its_frame_reports` 失败；同一响应发送的 client error frame 仍存在，因此问题是普通 observability 的归属与 detail，不是该 frame 本身。
- **影响**：操作员会把代理自己的 client deadline 误判为 upstream stream failure，定位方向错误；这也使现有 failure ownership 信号与 completion line 不一致。
- **修复方向**：`_StreamAccounting._ending()` 按 failure provenance 分支处理：upstream failure 使用安全 type/status 投影，proxy-owned failure 使用其固定安全消息或 proxy-owned type/reason；两者不得共用 upstream fallback。

### DYN-CAP-09 —— major —— 仍有未同步的 upstream raw-text completion assertions

- `finding_id`: `DYN-CAP-09`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `tests/int/test_pipeline_app.py:3744`
- `related_locations`: `tests/int/test_pipeline_app.py:3802`、`tests/int/test_pipeline_app.py:3935`、`tests/int/test_pipeline_app.py:3986`、`src/app/server/routes/inference.py:203-230`
- **判据**：用户要求 DYN-CAP-09 stale raw-text assertions 已同步；ACTIVE v14 要求普通 upstream detail/logger/FailureSummary/InterruptionObservation/ResponseObservation 只保留安全 metadata，不能要求 upstream 原始异常文本。
- **证据强度**：高。上一轮明确列出的四个 DYN-CAP-09 回归现在通过，但当前测试树另外仍有 one-shot、mid-stream tear 和 stop-reason tear 三处 completion-line assertions 要求 upstream exception 的原始 message。安全投影实现当前返回固定的 upstream type/status/reason 形状，因此这些测试会失败或继续把废止行为当成通过条件。Focused sweep 中相关 raw-text tests 失败，已同步的四个回归单独运行结果为 `4 passed`。
- **影响**：最终安全投影合同仍没有在全部相关回归中闭合；绿色结果无法证明普通 completion logger 已拒绝 upstream raw text。
- **修复方向**：把剩余断言改为固定 type/status/reason、attempt 和 completeness metadata；保留 proxy-owned message 的断言时，必须明确它不是 upstream exception text。

### COUNT-CAP-01 —— minor —— count fallback 的 completion-line assertions 未同步新的 bytes/attempt projection

- `finding_id`: `COUNT-CAP-01`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `tests/int/test_pipeline_app.py:3044`
- `related_locations`: `tests/int/test_pipeline_app.py:3087`、`src/app/observability/request_log.py:754-781`
- **判据**：用户条件要求 count/retry 路径正确记录 bytes 与 complete；新的 `body-attempts` projection 是该证据的普通安全摘要，测试不能继续假定 provider segment 必须是整行尾部。
- **证据强度**：高。当前 production formatter 在多 attempt 或 error 时先追加 `body-attempts=...`，再追加 `provider(...)`；两个 count tests 仍使用 `endswith("provider(ghc-failed,local)")`，因此 focused sweep 中这两项失败。规则选中的 count raw capture test 仍通过，并验证了 attempt start/status sequence；失败是测试合同没有同步，不是把 bytes 写入普通日志的问题。
- **影响**：最小相关测试集不绿，无法把 count/retry bytes 与 completion-line projection 一起验收。
- **修复方向**：断言 provider segment 的存在与位置关系，而不是整行 suffix；同时保留对 `body-attempts` 中固定 attempt/status/bytes/outcome metadata 的断言，不读取或输出正文。

## 已核验且符合当前 ACTIVE v14 的面

- SQLite rule store、唯一约束、规范化后的 provider/model/session/可选 agent 精确匹配、HTTP `GET/POST/DELETE /api/debug/capture-rules`、空白条件的 422 处理以及下一次匹配立即生效均有通过的 unit/integration coverage。
- 未命中请求不创建 `.cborseq.zst` capture，也不持久化 inbound body；命中后在第一次 upstream attempt 前补录已读取的 inbound body。
- 新 capture 使用每 item 独立 zstd frame 的 CBOR map sequence，body 是 native bytes，路径只含 identity hash；缺失 agent-id 使用 tagged 独立分组；legacy `.jsonl.zst` 只计入旧文件总配额，不参与新格式读写。
- writer acknowledgement、quota reservation、partial-write path poison、跨 store 的生产 reader 验证、request-incomplete warning 与安全 warning metadata 相关 focused tests 通过。
- provider/status/partial response、429/5xx、request-attached transport failure、count retry、account-switch retry 的已覆盖 capture paths 保留 request/status/response bytes 与对应 complete boundary。
- CodeBuddy 正常 aggregate 与 direct-driver discarded-response path 已优先使用 raw upstream extension；`test_discarded_response_capture_prefers_the_real_upstream_body` 与 CodeBuddy raw-extension component test 通过。DYN-CAP-11 的已报告 defect 在该路径上已闭合；本报告 DYN-CAP-12 是另一个 cleanup-only 接缝。
- Responses `error` observation、provider error summary、普通 upstream exception 的安全 type/status projection 相关 focused tests 通过；已同步的四个 DYN-CAP-09 raw-text regressions 通过。
- `rejection_capture` 当前只是无持久化副作用的 compatibility shim；active `src/app` 路径没有 legacy JSON rejection persistence。
- 首次 body pull 前的 response-start failure 走 `_AccountedStreamingResponse` 外层 cleanup，并有幂等的 `response.end(false)`/`attempt.end(false)` 生产路径；相关 response-start cleanup integration test 通过。未将 DYN-CAP-10 重新列为新 finding。

## 最小相关验证

- `uv run pytest -q --tb=no --disable-warnings tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：`35 passed`。
- `uv run pytest -q --tb=no --disable-warnings tests/int/test_pipeline_app.py -k 'opt_in_raw_capture_records_client_and_upstream_bodies or raw_capture_keeps_both_failed_account_switch_attempts or raw_capture_is_selective_and_rule_api_is_persistent or rule_selected_count_capture_keeps_each_upstream_retry or rule_selected_rejection_capture_keeps_upstream_wire_evidence or buffered_responses_status_error or response_observation or error_message or count_tokens'`：`21 passed, 257 deselected`。
- DYN-CAP-09 已同步子集：`4 passed, 274 deselected`。
- 安全投影、cleanup 与 count 的扩大选择集：`110 passed, 5 failed, 287 deselected`；失败对应本报告 DYN-CAP-09 的两类剩余 upstream raw-text assertions、DYN-CAP-13 的 client deadline assertion，以及 COUNT-CAP-01 的两个 count suffix assertions。
- 只读 CodeBuddy aggregate cleanup probe：异常类型 `builtins.RuntimeError`、`has_sent=false`、原 response extension bytes 存在；只读 failed-attempt helper probe：captured event count `0`。两项 probe 没有写文件、读取或输出正文/秘密。

## 搜索面与未覆盖面

已读 ACTIVE v14 raw-capture Spec、项目开发工作流、SQLite rule store、ops HTTP routes、composition、inference capture lifecycle、raw capture writer/reader、count path、direct driver、shared upstream normalization、OpenAI-compatible 与 CodeBuddy client、request completion、request logger、Responses observation、stream cleanup、rejection shim 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141。报告只记录安全 metadata 与测试结果，不包含任何 request/response body、认证信息、token 或 credential。
