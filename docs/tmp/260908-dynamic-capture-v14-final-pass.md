# Dynamic capture v14 最终只读验收

## 评审范围

判据来源是用户本轮给出的 ACTIVE v14 条件，以及 `.dev/docs/raw-capture/spec.md`。范围覆盖条件式 HTTP API + SQLite 精确匹配、未命中不持久化正文、命中后的 CBOR Sequence / zstd 真实 wire capture、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate 的 bytes 与 attempt completeness、首次 body pull 前的 incomplete boundary、普通 upstream detail/logger/FailureSummary/InterruptionObservation/ResponseObservation 的安全 metadata 投影、proxy-owned messages，以及 legacy JSON rejection persistence inactive。

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态。工作树已有大量其他未提交改动；本轮没有修改实现、测试或既有文件，没有读取、输出或持久化 capture 正文、认证信息、token 或 credential，也没有操作现有 4141 服务。按用户要求，仅写入本报告文件。

## 总体 verdict

**needs-fix：发现 2 个高置信度 major 缺陷，另有 1 个 focused test fixture 的 minor 合同漂移；当前不能报告 pass。**

## Blocker 数

0。

## Findings

### DYN-CAP-12 —— major —— CodeBuddy aggregate 的 generic cleanup failure 仍丢失真实 wire evidence

- `finding_id`: `DYN-CAP-12`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/codebuddy_client/client.py:133-144`
- `related_locations`: `src/app/model_provider/upstream_errors.py:152-187`、`src/app/pipeline/direct_driver/base.py:176-195`
- **判据**：命中 capture 的 CodeBuddy 非流式 aggregate 在 cleanup failure 接缝上仍必须保留已经实际发送和观察到的 upstream request/response bytes，并用不完整 attempt 边界表示失败；synthetic aggregate response 不能替代真实 SSE wire evidence。ACTIVE v14 的 cleanup 规则要求 provider response body / cleanup failure 路径保留这些证据。
- **证据强度**：高。当前 `CodebuddyClient.send_chat_completions(stream=False)` 在 aggregate 成功后调用原始 response 的 `aclose()`；若该 cleanup 抛出未归一化的 `RuntimeError`，`normalize_upstream_response_error()` 只识别 timeout/transport 类型并返回 `None`，客户端因此重新抛出原始 `RuntimeError`。随后 `capture_failed_upstream_attempt()` 只接受 `UpstreamError` / `UpstreamRejected`，不会写入 request、status 或已观察 response bytes。只读内存 probe 只输出安全 metadata：`raised_type=builtins.RuntimeError`、`captured_event_count=0`；probe 未输出正文或秘密。
- **影响**：命中规则的 CodeBuddy aggregate 请求在 provider cleanup failure 时仍可能只留下失败 attempt 标记而没有真实 SSE response evidence，无法重放或核对该次实际 upstream exchange，违反 cleanup / aggregate attempt completeness。
- **修复方向**：为 provider response cleanup failure 建立带 request/status/已观察 response bytes/`body_complete` 的稳定 error carrier，或把 response evidence 直接交给 capture；随后写出 `response.end(complete=false)` 与 `attempt.end(complete=false)`，并保持普通日志只使用安全 metadata。若只允许归一化 timeout/transport，也必须为其他 cleanup failure 保留真实 response evidence，而不能让 generic exception 绕过 capture。

### DYN-CAP-13 —— major —— proxy-owned client deadline 仍被普通 completion line 归类为 upstream stream failure

- `finding_id`: `DYN-CAP-13`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:1457-1462`
- `related_locations`: `src/app/pipeline/delivery/stream.py:497-516`、`tests/int/test_pipeline_app.py:3854-3858`
- **判据**：普通 upstream 投影必须是安全 metadata；proxy-owned message 可以保留，且不得把 proxy-owned failure 误归因成 upstream failure。
- **证据强度**：高。`stream.py` 的 client deadline 分支以 `on_runtime_failure(torn, False, None)` 明确记录 proxy-owned failure，但 `_StreamAccounting._ending()` 对所有 `self.failure` 统一调用 `_safe_failure_detail()`。`ClientDeadlineError` 不是 normalized upstream error，于是被渲染成 `upstream stream failure: app.streaming.deadline.ClientDeadlineError`。最小相关测试 `test_a_client_deadline_is_accounted_as_the_failure_its_frame_reports` 失败：client error frame 存在，但 completion line 没有 proxy-owned 的 `client request exceeded its deadline`，而是上述 upstream 归因。
- **影响**：运营日志会把代理自己的 deadline 误判成 upstream stream failure，导致排障方向错误，并使 error frame 的 proxy-owned 事实与 completion / structured observability 的 failure ownership 不一致。
- **修复方向**：让 `_ending()` 按 failure provenance 分支处理：upstream failure 使用安全 type/status projection，proxy-owned failure 使用固定安全 proxy message 或 proxy-owned reason；两者不得共用 upstream fallback。

### DYN-CAP-14 —— minor —— pre-first-pull 相关 focused test fixture 未同步新增 accounting 接口

- `finding_id`: `DYN-CAP-14`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `tests/int/test_pipeline_app.py:6212`
- `related_locations`: `src/app/server/routes/inference.py:1757-1761`
- **判据**：最终验收的最小相关测试必须能够实际验证首次 body pull 前 cleanup 的 incomplete boundary；测试 fixture 不能在被测边界之前因接口漂移退出。
- **证据强度**：高，但仅针对测试合同。`_AccountedStreamingResponse.__call__()` 的 finally 现在无条件调用 `note_unstarted_upstream_body_cleanup()`；`test_a_body_that_fails_to_close_is_still_accounted_for` 使用的 fake `_Accounting` 没有该方法，因此测试在 `AttributeError` 处失败，尚未到达原本的 cleanup assertions。生产 response-start failure 场景 `test_response_start_failure_closes_the_unstarted_upstream_owner` 通过，所以这条不单独证明生产 incomplete boundary 错误。
- **影响**：该 focused regression 不能作为 pre-first-pull / cleanup 行为的证据，当前最小验收集不全绿。
- **修复方向**：同步 fake accounting 的最小接口，或把 unstarted-body fallback 依赖收窄到明确的 accounting protocol，并重新运行该 cleanup regression。不要因为补 fixture 而删掉生产路径上的幂等 incomplete-boundary 调用。

## 上轮 finding 完成度

- `DYN-CAP-12`：**未闭合**。timeout/transport error 的归一化和 raw extension 路径存在，但 generic aggregate cleanup failure 仍绕过 error carrier 与 failed-attempt capture。
- `DYN-CAP-13`：**未闭合**。client deadline frame 已发送且继续传播，但普通 completion line 仍使用 upstream fallback。
- `DYN-CAP-09`：**在本轮选择集内闭合**。普通 upstream raw-text 安全投影相关的 long-failure、hand-over、tear 和 response observation focused tests 通过；client deadline 的 ownership 归因仍由 DYN-CAP-13 单独阻断。
- `COUNT-CAP-01`：**闭合**。四个 count completion projection tests 通过，failed count 的 `body-attempts` 不再被 suffix assumption 阻断。
- `DYN-CAP-10`：**生产路径有幂等 fallback，证据尚未完全闭合**。response-start failure 集成场景通过，但一个相关 cleanup fixture 因 DYN-CAP-14 在调用新增接口时失败。

## 最小相关验证

- `uv run pytest -q --tb=no --disable-warnings tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_log.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/delivery/test_stream_delivery.py`：`300 passed`。
- 动态 capture、HTTP rule API、未命中 rejection、status/partial/count/retry、response observation、cleanup 和安全 projection 集成选择集：`26 passed, 3 failed, 249 deselected`。失败为 DYN-CAP-13、DYN-CAP-14，以及一个不属于本 ACTIVE v14 capture 判据的既有 replay payload regression。
- `uv run pytest -q --tb=no --disable-warnings tests/int/test_pipeline_app.py -k 'token_count_says_it_was_one or count_upstream_could_not_answer or count_with_no_upstream_counter or count_upstream_answered_uselessly'`：`4 passed`。
- `uv run pytest -q --tb=no --disable-warnings tests/int/test_error_envelope.py -k 'deadline or client'`：`8 passed`。
- CodeBuddy generic cleanup probe 只输出 `raised_type` 和 `captured_event_count`，结果为 `builtins.RuntimeError` 与 `0`；没有输出正文或秘密。

## 未纳入 finding 的验证失败

`test_delivery_replay_reuses_the_normal_attempt_that_produced_the_stream` 失败于第二次 retry payload 没有得到该测试 callback 预期的重写。它属于当前候选工作树的 retry/re-encode 行为回归，但没有证据表明它破坏了 ACTIVE v14 的 raw capture 格式或 attempt evidence contract，因此不把它伪装成动态 capture finding；不过它意味着当前工作树也不能声称相关 retry regression 全部通过。

## 搜索面与未覆盖面

已读 ACTIVE v14 raw-capture Spec、项目开发工作流、debug capture SQLite store、ops HTTP routes、inference capture lifecycle、raw capture writer/reader、count path、direct driver、provider error normalization、OpenAI-compatible 与 CodeBuddy client、request completion、request logger、Responses observation、stream cleanup、rejection shim 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141。除上述 findings 与明确列出的 retry regression 外，没有发现新的高置信度 ACTIVE v14 dynamic-capture defect。
