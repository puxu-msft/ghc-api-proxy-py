# Dynamic capture v11 final review

## 评审范围

判据是 `.dev/docs/raw-capture/spec.md` ACTIVE v11，覆盖 SQLite/HTTP 条件匹配、未命中不持久化正文、CBOR/zstd capture、每个 provider attempt 的真实 upstream request/response wire body、429/5xx/ReadTimeout/transport/status-body-read/cleanup/count retry、CodeBuddy 非流式真实 SSE capture，以及普通日志和 structured observation 的安全边界。

被检对象是当前工作树的最终实现、相关测试和上述 Spec；重点检查 `raw_capture.py`、`debug_capture.py`、`inference.py`、`request_completion.py`、`request_trace.py`、`upstream_errors.py`、direct driver、OpenAI-compatible/CodeBuddy clients 及其相关测试。未进行 live upstream 或 4141 服务操作，也未修改实现文件。

## 总体 verdict

**未通过：发现 2 个高置信 major 问题。**

## blocker 数

0。

## Findings

### DYN-CAP-01 — 普通完成记录和 upstream interruption observation 仍可携带原始错误文本

- **严重度：** major。
- **证据强度：** strong enough to act on；这是代码路径直接保证的行为，不是推测。
- **主位置：** `src/app/server/routes/inference.py:747-764`。
- **相关位置：** `src/app/server/routes/inference.py:808-817`；`src/app/pipeline/hand_over.py:247-258,352-358`；`src/app/observability/request_completion.py:445-465`。
- **问题：** count-token 异常和普通 dispatch 异常直接执行 `trace.detail = str(error)`。另一条 upstream hand-over 路径由 `_observe_exception()` 取异常外层文本，并把它作为 `HandBackTrigger.message`；`RequestCompletionCoordinator.note_upstream_stream_failure()` 又不经安全归一化，直接把该文本写入 `InterruptionObservation.message`。只要 provider 异常文本包含 upstream error message 或其回显内容，普通 completion record 和 structured observation 就会保存它。
- **复核证据：** 用只存在于内存中的带 sentinel 的 `UpstreamError` 探针调用 hand-over observation，返回文本原样进入 observation-like message；未打印 sentinel 内容，也未写入仓库。当前安装的 OpenAI SDK `_make_status_error_from_response()` 还会把已读取的 response text/JSON body 拼入 `APIStatusError` 的错误文本，因此这不是只对人为构造异常成立的抽象路径。
- **绿灯分辨力：** 现有 upstream normalization fixture 手工传入不含 body 的 SDK 异常消息，所以相关测试会绿，但不能检测生产 SDK 生成的带 body 错误文本。
- **与 Spec 的冲突：** v11 §4 明确禁止普通日志和请求完成记录复制 raw error body/message；v7 修订记录明确要求普通 completion/response observation 只保留安全错误元数据。现有 `_safe_failure_detail()` 和 `_safe_exception_message()` 并未覆盖上述直接赋值和 hand-over message 注入点。
- **影响：** 条件 raw capture 之外的普通持久化记录可能泄露 provider 错误正文或错误消息，违反“只有显式命中规则才保存正文”的安全边界。
- **建议修复方向：** 所有普通 `detail`、`FailureSummary.message`、`InterruptionObservation.message` 统一投影为固定枚举、状态码、异常类型和 completeness 等安全元数据；面向客户端的 hand-over 文本与普通 structured observation 分离，不能复用原始异常文本。

### DYN-CAP-02 — OpenAI-compatible status-body-read 在已经收到部分 response bytes 后丢失真实 response body

- **严重度：** major。
- **证据强度：** strong enough to act on；已用当前依赖和当前实现复现。
- **主位置：** `src/app/model_provider/upstream_errors.py:157-188`。
- **相关位置：** `src/app/model_provider/openai_compatible/client.py:133-141`；`src/app/pipeline/direct_driver/base.py:176-192`。
- **问题：** `normalize_upstream_response_error()` 只从 `response.extensions["codebuddy_raw_upstream_body"]` 读取 body evidence，也不把已有 response status 带进 normalized error。OpenAI-compatible client 在 `response.aread()` 期间没有通用的 partial-body accumulator；因此 5xx response 已产生部分 body 后由 `ReadTimeout`/transport error 终止时，normalized error 得到 `status_code=None`、`body_observed=False`、空 `body_bytes`。随后 `capture_failed_upstream_attempt()` 只能记录 sent request bytes，不会写 `upstream.response.start` 或真实已收到的 response body。
- **复核证据：** 只读 Python 探针让 OpenAI-compatible 风格的 500 streaming response 先产生部分 bytes 再抛 `ReadTimeout`；当前结果确认 request bytes 保留，但 normalized error 的 response status/body evidence 均为空。探针没有输出或持久化 body 内容。
- **与 Spec 的冲突：** v11 §4 要求命中后保存每个 provider attempt 的实际 upstream request/response body；v10/v11 修订记录把 provider response `aread()` 和 body-read failure 纳入同一证据合同。当前 CodeBuddy 专用 extension 只覆盖 CodeBuddy，不能满足 OpenAI-compatible provider。
- **影响：** 命中规则的 status-body-read attempt 无法重放或确认已经收到的部分 upstream response，正是动态捕获合同要求保留的 failure evidence。
- **建议修复方向：** 在所有 streaming response body read 路径使用通用的逐块 byte accumulator，并把 status、已观察的 bytes、body completeness 一起带入 normalized error；capture failed attempt 时写入实际 partial response evidence，且保持不完整边界，不把 synthetic response 当作 wire body。

## 已验证测试

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：29 passed。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'capture or rejection or unmatched_refusal'`：6 passed，1 个现有依赖弃用 warning。
- `uv run pytest -q tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py`：86 passed。

这些绿灯覆盖了 CBOR/zstd、规则匹配、命中与未命中、count retry、429/5xx 基本 wire evidence、CodeBuddy 非流式 SSE extension 和普通 Responses error projection，但没有覆盖 DYN-CAP-01 的异常文本注入路径，也没有覆盖 DYN-CAP-02 的 OpenAI-compatible partial status-body read。

## 搜索面与未覆盖面

已读 ACTIVE v11 Spec、raw capture store/reader、SQLite rule store、HTTP ops route、inference capture lifecycle、completion/trace serialization、direct-driver attempt failure/cleanup、shared upstream error normalization、OpenAI-compatible client、CodeBuddy client/aggregation及相关 unit/component/integration tests。

未运行完整回归、Ruff、Pyright、真实 upstream 或部署验收；这些不改变上述两条由当前代码路径和定向探针直接证明的发现。
