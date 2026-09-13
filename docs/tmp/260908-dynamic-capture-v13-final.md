# Dynamic capture v13 最终只读验收

## 评审范围

判据是用户本轮给出的条件式 raw capture 合同与 `.dev/docs/raw-capture/spec.md` ACTIVE v13。范围覆盖 HTTP API 与 SQLite 规则、规则命中时机、未命中不持久化正文、CBOR Sequence/zstd 文件与配额、每个 provider attempt 的真实 upstream request/response wire bytes、status/body-read/aggregate/count/retry/cleanup/partial response 路径、普通日志与请求完成记录的安全投影、`ResponseObservation` 等 structured observation，以及 legacy JSON rejection persistence 的退役状态。

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态，重点读取 `debug_capture.py`、`raw_capture.py`、`rejection_capture.py`、`routes/ops.py`、`routes/inference.py`、`pipeline/driver.py`、direct driver、各 provider client、`request_completion.py`、`response_observation.py` 及相关测试。工作树原有大量未提交改动未被回滚或覆盖。本次没有修改实现、测试或 Spec 文件；只写入本报告，没有读取、输出或持久化真实 capture 正文、认证信息、token 或 credential，也没有操作 4141。

## 总体 verdict

**未通过：发现 3 个高置信度 major 缺陷。**

## blocker 数

0。

## Findings

### DYN-CAP-06 —— major —— 普通 completion/detail/logging 仍可直接渲染 upstream error message

- `finding_id`：`DYN-CAP-06`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`src/app/server/routes/inference.py:1433`
- `related_locations`：`src/app/observability/request_completion.py:765-802`；`src/app/server/routes/inference.py:200、1026、1348`；`src/app/pipeline/delivery/formats/openai_responses.py:117`；`src/app/pipeline/delivery/formats/anthropic_messages.py:420-422`
- **判据**：ACTIVE v13 §4、§6 以及用户条件明确要求普通 detail、`FailureSummary`、`InterruptionObservation`、structured observation 和普通日志不复制 raw error message/body；DYN-CAP-03 的修复目标是未归一化异常也只能产生安全 type/status projection。
- **证据**：流式 `_StreamAccounting._ending()` 对 `self.failure` 直接使用 f-string，写入普通 completion detail；Responses 与 Anthropic 的 mid-stream error logger 直接记录上游 error message；`_safe_exception_message()` 对未被 normalizer 识别的异常回退到 `str()`/`repr()`；`_aborted()`、`replaced_failures` 和 `tore_after_terminal` 也保留异常文本或 repr。只输出布尔值的内存探针确认未归一化异常文本分别进入 FailureSummary fallback、aborted detail；另一个已运行的集成测试在当前状态失败，显示普通流式 completion line 仍包含上游异常文本。报告不重复这些文本。
- **影响**：未命中规则的请求也会把 provider/transport 异常文本写入 always-on 普通日志或请求完成 JSON，绕过 raw capture 的显式条件；异常文本包含上游错误 body 时，同样越过“正文只在命中规则后持久化”的边界。DYN-CAP-03 不能标记为 fully closed。
- **建议修复方向**：统一所有普通 observability projection 的入口，只输出固定 reason、exception type/module、status、attempt 和 completeness 等安全元数据；客户端 hand-over/direct passthrough 可以继续保留上游原文，但不能复用到普通 detail、logger、replaced-failure 或 post-terminal projection。同步改写仍期待原始异常文本的旧测试。

### DYN-CAP-07 —— major —— Responses `error` SSE event 分支把原始 error map 冻结进 structured observation

- `finding_id`：`DYN-CAP-07`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`src/app/pipeline/response_observation.py:302-307`
- `related_locations`：`src/app/pipeline/response_observation.py:447-460`；`src/app/pipeline/response_observation.py:353-380`；`tests/unit/pipeline/test_response_observation.py:469-490`
- **判据**：普通 structured observation 不得复制 raw error message/body；同一文件已有 `_safe_error_field()`，应当把 provider error 投影为 present、type、code 和固定的 message-present 标记。
- **证据**：`ResponsesObserver.observe_event()` 遇到 `event == "error"` 时，嵌套形态调用 `_field(data, "error", ...)`，平面形态直接调用 `_freeze_value(data, ...)`。两条分支都会把原始 `message` 以及同一 error map 的其他字段存入 `ResponseObservation.error`；随后 `FinalizedRequest.to_record_dict()` 会把它写入普通 structured request record。只输出布尔结果的内存探针确认 event error 的 structured value 包含输入 marker。现有安全测试只覆盖 `observe_response()`，没有覆盖这个 SSE event 分支。
- **影响**：流式 Responses provider error 会在不命中 raw capture 规则时进入普通结构化记录，直接违反安全边界。
- **建议修复方向**：对嵌套与平面 event error 都调用 `_safe_error_field(error_value, field_path="error")`，并增加两种 event 形态的回归测试，断言原始 message/body 不在 `ResponseObservation.error` 和最终记录中。

### DYN-CAP-08 —— major —— streaming upstream cleanup failure 在 EOF 后仍被 capture 标记为完整 attempt

- `finding_id`：`DYN-CAP-08`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`src/app/server/routes/inference.py:1804-1818`
- `related_locations`：`src/app/server/routes/inference.py:1760-1766`；`src/app/server/routes/inference.py:1584-1608`；`src/app/pipeline/driver.py:566-577`
- **判据**：ACTIVE v13 要求 capture 保留 cleanup failure 以及 partial/incomplete response boundary；DYN-CAP-04 已确立 count cleanup failure 不能提交 `attempt.end(complete=true)`。
- **证据**：`_counted_upstream()` 在正常 EOF 时先写 `upstream.response.end` 默认 `complete=true` 并设置 `upstream_eof=True`。随后 `finish_stream_cleanup()` 即使返回 `cleanup_error`，capture 仍使用 `complete=upstream_eof` 写 `upstream.attempt.end`，没有写 cleanup failure 或 `response.end(complete=false)`。只输出事件布尔值的内存探针让 body 正常 EOF、source `aclose()` 抛出 cleanup exception，结果仍是 `response.end.complete=true` 与 `attempt.end.complete=true`。
- **影响**：命中规则的流式 provider attempt 在 cleanup 失败后看起来像完整成功 exchange，raw capture 无法表达该 cleanup failure，也无法阻止回放者把这次 attempt 当作完整证据。该缺陷独立于已修复的“异常 body-read 后写 `response.end(complete=false)`”路径。
- **建议修复方向**：不要在 cleanup 成功前提交完整 response/attempt boundary；cleanup failure 或 cleanup cancellation 应使 attempt 为 incomplete，并通过稳定的 capture 事件或失败边界保留诊断。应覆盖正常 EOF 后 source close failure 以及外层 `response.aclose()` failure 两个接缝。

## 上轮 DYN-CAP-03/04/05 完成度

- `DYN-CAP-03`：**partially closed**。`_safe_failure_detail()` 与 hand-over 的普通 interruption message 已改为安全 projection，相关 hand-over 测试通过；但本报告 DYN-CAP-06 证明流式 completion detail、异常 fallback 和普通 logger 仍未统一闭合。
- `DYN-CAP-04`：**closed for the reviewed count cleanup ordering**。当前 count path 在 `response.aclose()` 完成后才写 attempt end，并以 cleanup failure 写 `complete=false`；count retry 与基本 wire capture 测试通过。
- `DYN-CAP-05`：**closed for the reviewed partial body paths**。`capture_failed_upstream_attempt()` 使用 `body_complete`，streaming body-read failure 写 `response.end(complete=false)`；相关 provider normalizer 与 raw capture 目标测试通过。DYN-CAP-08 是 EOF 后 cleanup failure 的不同边界。

## 已核验且符合当前 Spec 的面

- SQLite rule store、唯一约束、规范化后的非空精确匹配、可选 agent-id、HTTP `GET/POST/DELETE /api/debug/capture-rules` 以及下一次匹配立即生效的接线存在。
- 未命中规则不会创建 request capture 或 `.cborseq.zst` 文件，也不会把 inbound body 写入普通记录；命中后在首次 upstream attempt 前补录原始 inbound body。
- capture 使用每 item 独立 zstd frame 的 CBOR map stream，路径只含 hash；缺失 agent-id 使用独立 identity；旧 `.jsonl.zst` 只计入总配额，不参与新格式读取或写入。
- writer acknowledgement、配额 reservation、partial-write poison、跨新 store 的 reader 校验、request completion warning 和 legacy rejection persistence inactive 的相关测试通过。
- 429/5xx、status-body-read、CodeBuddy aggregate 的真实 SSE extension、count retry、account-switch retry 的已覆盖路径保留 request/status/body evidence；未观察到高置信度的另外缺陷。

## 最小相关验证

- `uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules or rejection_capture or count_tokens or provider_error_wire or unmatched_refusal' --maxfail=1`：43 passed。
- `uv run pytest tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/pipeline/test_response_observation.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/pipeline/test_direct_driver.py -q --maxfail=1`：176 passed。
- `uv run pytest tests/int/test_pipeline_app.py -k 'hand_back or interruption_evidence or only_the_attempt_that_synthesizes_continuation' --maxfail=1`：4 passed。
- `uv run pytest tests/int/test_pipeline_app.py -k 'runtime_upstream_stream_failure_is_reported_without_escaping_the_app or reported_upstream_failure_does_not_hide_a_distinct_cleanup_failure' -q --maxfail=1`：在第一项 assertion 处失败；该失败与当前实现仍把 raw upstream exception text 写入普通 completion detail 的 DYN-CAP-06 直接相关。
- 另执行两个只输出布尔值或事件 completeness 的内存 probe：确认 DYN-CAP-07 的 SSE error structured value 泄露，以及 DYN-CAP-08 的 EOF 后 cleanup failure 仍产生完整 response/attempt boundary。

## 搜索面与未覆盖面

已读 ACTIVE v13 Spec、项目开发工作流、raw capture store/reader、SQLite rule store、HTTP ops route、composition、inference lifecycle、count path、direct driver、shared upstream normalization、GHC/OpenAI-compatible/CodeBuddy client、request completion、Responses observation、stream delivery 与相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141 服务。未覆盖面不改变上述三个由当前代码路径、定向失败测试和不落盘 metadata probe 直接证明的 major findings。
