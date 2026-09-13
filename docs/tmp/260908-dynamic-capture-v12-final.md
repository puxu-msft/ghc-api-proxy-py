# Dynamic capture v12 final read-only acceptance

## 评审范围

判据是用户本轮给出的条件式 raw capture 合同与 `.dev/docs/raw-capture/spec.md` ACTIVE v12。覆盖 HTTP API + SQLite 条件选择、未命中不持久化正文、CBOR Sequence + zstd、每个 provider attempt 的真实 upstream request/response wire body、status-body read partial failure、cleanup、429/5xx/timeout/transport、count retry、CodeBuddy non-stream aggregate 的真实 SSE body，以及普通 detail、FailureSummary、InterruptionObservation 和 structured observation 的安全投影。legacy JSON rejection persistence 不作为 active 行为。

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树的最终实现与相关测试，重点包括 `debug_capture.py`、`raw_capture.py`、`routes/ops.py`、`routes/inference.py`、`pipeline/driver.py`、direct driver、`upstream_errors.py`、OpenAI-compatible client、CodeBuddy client、request completion、response observation 及相关 unit/component/integration tests。工作树原有的大量未提交改动未被回滚或覆盖。本次未修改实现文件，也未读取、输出或持久化真实 capture 正文、token、header 或 credential。

## 总体 verdict

**needs-fix：发现 3 个高置信 major 问题。**

## Blocker 数

0。

## Findings

### DYN-CAP-03 — major — 未归一化 upstream exception 的 safe projection 会泄露正文并重复渲染异常

- `finding_id`: `DYN-CAP-03`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:203-230`
- `related_locations`: `src/app/server/routes/inference.py:1090-1105`；`tests/int/test_pipeline_app.py` 中的 hand-back render-once 与 unrenderable-trigger 场景。
- **判据**：普通 detail、FailureSummary、InterruptionObservation 和 structured observation 不得复制 raw upstream error message/body；hand-over 失败路径仍必须保持可观察且不能因观测本身破坏用户可观察的 continuation。
- **证据**：`_safe_failure_detail()` 对无法由 `normalize_upstream_error()` 识别的异常直接执行 `return str(error)`。streaming hand-over 先调用 `hand_back_block()`，其中 `_observe_exception()` 已经读取异常文本，随后 `_hand_back_streaming()` 再调用 `_safe_failure_detail(error)`，同一个异常会被再次渲染。现有集成测试 `test_hand_back_renders_the_failure_once_for_payload_and_trigger` 与 `test_hand_back_reports_unrenderable_trigger_without_losing_the_outcome` 在当前最终状态失败：前者触发二次渲染异常，后者没有交付 hand-over。
- **复核探针**：使用只存在于内存中的未归一化 upstream exception，并只检查布尔结果；当前结果显示 synthetic raw marker 同时进入普通 `detail` 与 `InterruptionObservation.message`，且 hand-over 依赖异常可渲染时会失败。探针没有输出 marker、request body 或 response body。
- **影响**：未被共享 normalizer 覆盖的 provider/transport 异常可以把 raw message 进入普通持久化观察；异常文本带有 provider body 时同样会越过 raw-capture 条件边界。另一个独立影响是 hand-over 的用户可观察结果可能被二次渲染错误阻断。
- **建议修复方向**：让 hand-over 复用一次已经完成的异常观察结果，再分别生成客户端 payload 与普通安全投影；对未归一化异常的普通投影使用固定类型/阶段/状态元数据，不回退到 raw `str(error)`。渲染失败只应降级为安全的不可用消息，不能让 continuation 结果消失。

### DYN-CAP-04 — major — count_tokens cleanup failure 被记录成完整成功 attempt

- `finding_id`: `DYN-CAP-04`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/driver.py:545-561`
- `related_locations`: `src/app/pipeline/count_tokens.py:80-102`；`src/app/observability/raw_capture.py:350-427`。
- **判据**：命中规则后，每个实际 provider attempt 必须保留真实 request/response wire evidence，并包含 cleanup failure 与 retry 边界。
- **证据**：`ask_upstream()` 在 `response.aclose()` 之前已经写入 `upstream.response.end` 与 `upstream.attempt.end(complete=True)`。`response.aclose()` 位于 provider response 读取和 capture 记录之后，cleanup exception 不再进入 `capture_failed_upstream_attempt()`；外层 `count_tokens()` 将该 exception 当作普通失败继续 retry，之后还可能返回 local estimate。
- **复核探针**：让 count response 的 `aclose()` 在内存中对每一次调用抛出 synthetic `ReadTimeout`，命中 SQLite 规则后观察 capture 元数据。请求最终 local fallback，发生 3 个 upstream attempts；每个 attempt 都出现 `upstream.response.end(complete=true)` 和 `upstream.attempt.end(complete=true)`，没有 cleanup failure 或 incomplete boundary。探针只输出事件类型、attempt 编号和 complete 布尔值，没有输出正文。
- **影响**：capture 把发生 cleanup failure 的 attempt 伪装成完整成功 exchange，且把 cleanup 失败隐去在 count retry/fallback 之后，无法按合同复现或诊断该 provider attempt。
- **建议修复方向**：把 count response 的 close 纳入与 provider client 相同的 primary/cleanup normalization 和 attempt finalization；cleanup 失败时在 request/response bytes 已保存的同时把 attempt 标为不完整并保留稳定 failure reason，且不能先提交 `complete=true`。

### DYN-CAP-05 — major — partial response body 的 response end 被错误标为 complete

- `finding_id`: `DYN-CAP-05`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/direct_driver/base.py:176-192`
- `related_locations`: `src/app/model_provider/upstream_errors.py:217-224`；`src/app/server/routes/inference.py:1773-1812`。
- **判据**：status-body read partial failure、timeout、transport failure 和 streaming cleanup 必须保留实际已收到的 wire bytes 及其不完整边界，不能把未完成的 upstream response 记录成完整。
- **证据**：`capture_failed_upstream_attempt()` 看到 `body_observed` 后调用 `upstream_response_end(attempt=attempt)`，省略 `complete`，因此使用默认值 `True`。OpenAI-compatible partial status-body read 的当前修复已经把 status 与 partial bytes 带入 normalized error，但没有把 body-read completeness 带入 capture end。streaming `_counted_upstream()` 在异常/cleanup 路径只写 `upstream_attempt_end(..., complete=upstream_eof)`，不会写对应的 `upstream.response.end(complete=False)`。
- **复核探针**：构造一个带 status 的 response，先产生部分 body 再抛 `ReadTimeout`；normalized error 确实保留 status、已观察 body 和 request bytes，但 failed-attempt capture 的事件序列把 `upstream.response.end.complete` 记录为 `true`。探针只输出长度、status、事件类型和布尔值，没有输出 body。
- **影响**：reader 可以同时看到 partial response bytes 与 `response.end.complete=true`，把不可重放的半个 response 当作已完整读完；streaming timeout/transport 还缺少 response-level incomplete boundary，只剩 attempt-level 标记。
- **建议修复方向**：在 error carrier 或 capture helper 中明确区分 body fully consumed、body partially observed 与 body not observed；partial read 和 cleanup/transport failure 必须写 `upstream.response.end(complete=False)`，正常已消费完的 status response 才能写 `true`。

## 上轮 finding 完成度

- `DYN-CAP-01`：**partially-closed**。已归一化的 count、dispatch、普通 provider failure、hand-over trigger 与 interruption 路径现在使用 status/固定安全投影；本轮发现的未归一化 exception fallback 仍违反同一安全合同，因此不能标记 fully closed。
- `DYN-CAP-02`：**closed for its reported defect**。OpenAI-compatible partial status-body 已能保留 status、partial bytes 与 sent request bytes；本轮 `DYN-CAP-05` 是另外发现的 response-level completeness 缺口，不把已修复的 status/body evidence 缺陷重新打开。
- `RC-009`：**closed for the reviewed CodeBuddy aggregate path**。non-stream aggregate 会在实际 SSE 读取时更新 raw extension；cleanup timeout/transport 会经过 shared normalization。对应 CodeBuddy component tests 通过，另有只检查类型、status、body-observed 和 sent presence 的内存探针通过。
- `RC-010`：**closed for the reviewed CodeBuddy wire/body separation**。inference buffered path 优先读取 `upstream_raw_response_body` extension，synthetic aggregate response 只供 pipeline 解析和交付，不替代 capture 中的真实 SSE body。
- `RC-005`：**closed for the reviewed 429/transport request-body paths**。当前 normalizer 和 provider-specific error constructors 都把 sent request bytes 传入失败 attempt capture；focused provider tests 通过。

## 已核验且符合合同的面

- SQLite rule store、唯一约束、规范化非空精确匹配、可选 agent-id、HTTP `GET/POST/DELETE /api/debug/capture-rules` 和下一次匹配立即生效的接线存在。
- 未命中请求不会启动 `RawRequestCapture`，不会创建 `.cborseq.zst` 文件，也不会持久化 inbound body；命中后在第一次 upstream attempt 前补录原始 inbound body。
- capture 使用 CBOR map + 每 item 独立 zstd frame，路径只含 identity hash；缺失 agent-id 使用不可与普通 agent 字符串碰撞的 tagged path identity；旧 `.jsonl.zst` 仅计入配额，不作为新格式读取或写入。
- writer acknowledgement、quota reservation、partial-write path poison、跨新 store 的生产 reader 校验和安全 completion warning 的相关 focused tests 通过。
- `rejection_capture` 当前只是无持久化副作用的 compatibility shim；active `src/app` 路径没有 legacy JSON rejection persistence。

## 执行的最小相关验证

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：34 passed。
- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/openai_compatible/test_provider.py tests/unit/pipeline/test_direct_driver.py tests/unit/observability/test_response_observation_projection.py tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_request_completion.py -k 'raw_capture or debug_capture or rejection_capture or provider_error or wire or capture or timeout or response_observation or provider_failure or finalized_request or upstream_error or unconsumed_stream_status_body'`：112 passed，115 deselected。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules or count_capture or count_failure or provider_error or buffered_responses_status_error or streamed_responses_completed_with_error or upstream_refusal'`：10 passed，268 deselected。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules or rejection_capture or count_capture or count_failure or provider_error or interruption or hand_back'`：9 passed，3 failed。失败为 `test_only_the_attempt_that_synthesizes_continuation_records_an_interruption`、`test_hand_back_renders_the_failure_once_for_payload_and_trigger`、`test_hand_back_reports_unrenderable_trigger_without_losing_the_outcome`；这些失败与 DYN-CAP-03 的 safe projection/hand-over 接缝直接相关。
- 另执行了只输出 metadata 的内存探针：OpenAI-compatible partial status-body 保留 status/partial bytes/sent presence；CodeBuddy aggregate cleanup 归一化为 `UpstreamTimeout` 并保留 status/body-observed/sent presence；count cleanup failure 的 capture 事件均错误标成 complete；未归一化 upstream exception 的 raw marker 进入普通 detail 与 interruption observation。

## 搜索面与未覆盖面

已读 ACTIVE v12 Spec、项目开发工作流、raw capture store/reader、SQLite rule store、ops HTTP routes、composition、inference capture lifecycle、count path、direct driver、shared upstream normalization、OpenAI-compatible client、CodeBuddy client、request completion、response observation、hand-over 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream、真实 capture 文件或真实数据库；未操作现有 4141 服务。上述未覆盖面不改变 3 个由当前代码路径、失败测试和不落盘 metadata probe 直接证明的 major findings。
