# Raw capture ACTIVE v8 最终只读验收报告

## 评审范围

评审基准是 `/home/xp/src/ghc-api-proxy-py` 当前工作树，判据是用户本轮合同与 `.dev/docs/raw-capture/spec.md` 的 `ACTIVE v8` 正文及修订记录。范围包括 SQLite 条件规则与 HTTP CRUD、路由后的 provider/resolved model-id/session-id/optional exact agent-id 匹配、CBOR Sequence + zstd writer/reader、配额与 poison/ack、失败 attempt wire evidence、count_tokens retry、普通 completion/response observation 安全投影，以及直接相关 tests。

明确不评价同一工作树中与 raw capture 合同无关的协议迁移、Responses 形状、Docker、实验目录及其他脏改动。没有编辑生产实现或现有 tests；本报告是用户明确要求写入的唯一新文件。

## 总体 verdict

**needs-fix**

## Blocker 数

0

## Findings

### RC-006 — major — provider-specific upstream normalizer 仍丢失已发送 request bytes

- `finding_id`: `RC-006`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/codebuddy_client/client.py:70-76`
- `related_locations`: `src/app/model_provider/codebuddy_client/errors.py:23-64`、`src/app/model_provider/openai_compatible/errors.py:14-43`、`src/app/pipeline/direct_driver/base.py:176-192`、`.dev/docs/raw-capture/spec.md:50、82`
- **判据**：ACTIVE v8 要求命中规则后，429 与 request-attached transport failure 也必须把实际已发送的 upstream request body 传入失败 attempt capture；§4 和 §6.5 同样要求每个失败 attempt 保留实际 wire evidence。
- **证据**：共享 `model_provider/upstream_errors.py` 的 SDK/httpx normalizer 已在 429、timeout 和 response-less connection 分支调用 `_sent_body(error)`，但 CodeBuddy 自己的 timeout/HTTP transport 分支直接构造没有 `sent` 的 `UpstreamTimeout`/`UpstreamError`。CodeBuddy 与 OpenAI-compatible 的 response-status normalizer 在 429 和默认 retryable status 分支也没有把 `response.request.content` 传入 `sent`；只有 deterministic 4xx rejection 分支保留了该字段。`capture_failed_upstream_attempt()` 只在 `upstream_error.sent` 为真时写入 `upstream.request.body`，也不追溯 CodeBuddy 包装异常的 `__cause__`。
- **合成验证**：对 CodeBuddy 和 OpenAI-compatible 的 429、500 normalizer 分别提供带非空 request content 的 synthetic `httpx2.Response`，四个结果的 `sent` 长度均为 `0`；送入生产 `capture_failed_upstream_attempt()` 后事件只有 `upstream.response.start`、`upstream.response.body`、`upstream.response.end`，没有 `upstream.request.body`。探针只输出事件类型和长度，没有输出 body。
- **影响**：命中规则的 CodeBuddy/OpenAI-compatible 429、5xx 以及 CodeBuddy response-less timeout/transport failure 无法从 capture 重放实际发送的 request bytes；count_tokens 经过 OpenAI-compatible provider 时也走同一缺口。这是 v8 失败 attempt 合同仍未闭合的生产路径，不能以共享 normalizer 已修复 RC-005 代替系统级闭合。
- **修复方向**：让所有 provider-specific normalizer 统一复用带 request-byte 提取的共享边界，或在构造 `UpstreamError`/`UpstreamRateLimit` 时显式传入 response/request content；对 CodeBuddy response-less wrapper 还必须在丢失原始异常前传递 request-attached bytes，并补充 capture-level regression tests。

### RC-007 — major — active integration tests 仍断言已被 v8 废止的 legacy rejection capture

- `finding_id`: `RC-007`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `tests/int/test_pipeline_app.py:2507-2565`
- `related_locations`: `src/app/observability/rejection_capture.py:13-27`、`.dev/docs/raw-capture/spec.md:19、50、83`
- **判据**：v7/v8 明确规定未命中规则不得持久化正文，legacy JSON rejection capture 已退役；当前 shim 的职责正是无持久化副作用。
- **证据**：两个仍在 active `tests/int` 下的测试通过 monkeypatch `rejection_capture.user_data_path`，并断言 4xx 会生成 `rejected/*.json`、保存 upstream body、payload 和 sent bytes。当前 `rejection_capture.py` 已没有 `user_data_path`，也明确不写文件，因此这两项测试不是“发现实现回归”，而是在要求一项当前 Spec 明确禁止的行为。
- **执行结果**：直接运行这两个 test node 得到 `2 failed`，失败点均为 `rejection_capture` 不再拥有 `user_data_path`。因此相关 integration file 在不筛掉这两个旧测试时不能通过，且测试本身会把后续实现重新引向 v8 禁止的 JSON rejection persistence。
- **影响**：最终验收的 active regression surface 仍是红的，tests 与 ACTIVE v8 的安全/选择合同相互矛盾；仅运行带 `-k raw_capture or capture_rules` 的子集会把这两个测试排除，不能作为完整相关测试绿灯。
- **修复方向**：删除或改写这两个 legacy tests，改为验证无命中 4xx 不创建 rejection 文件；保留已有 rule-selected rejection test，验证命中后只写 `.cborseq.zst` 的条件 capture。

## 上轮 finding 完成度

- RC-005 的共享 SDK/httpx normalizer 修复已核实：`UpstreamRateLimit` 和 shared response-less connection/timeout 分支能够携带 request-attached `sent` bytes，现有 normalization tests 通过；但 provider-specific residual path 仍由 RC-006 打开，因此 v8 系统合同不能标记为 closed。
- partial-write shared-path poisoning 与跨 store 首次 reader validation 已在当前 `RawCaptureStore` 和直接 tests 中接线；本轮没有发现新的高置信 poison/accounting 缺陷。
- 未命中规则不再走 legacy persistence 的生产实现已与 v7/v8 一致；RC-007 说明 active integration tests 尚未同步，而不是重新打开生产 shim。
- SQLite 规则 CRUD、路由后精确匹配、缺失 agent-id 独立分组、旧 `enabled: true` 拒绝、CBOR/zstd 格式、配额 ack 和 `request_incomplete` 直接相关路径本轮未发现新的高置信 defect。

## 验证结果

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/openai_compatible/test_provider.py tests/unit/observability/test_response_observation_projection.py tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules or rejection_capture or upstream_error or timeout or provider_error or provider_failure or response_observation or codebuddy or sent_body or capture'`：`75 passed, 289 deselected`，有一个第三方 deprecation warning。
- 直接运行 `tests/int/test_pipeline_app.py::test_a_refused_body_is_kept_where_someone_can_read_it` 与 `tests/int/test_pipeline_app.py::test_a_refused_body_is_kept_as_the_bytes_that_actually_crossed`：`2 failed`，对应 RC-007。
- provider-specific normalizer synthetic probe：四个 429/500 组合均报告 `sent` 长度为 `0`，失败 attempt capture 均缺少 `upstream.request.body`；没有输出任何 body、header、token 或数据库内容。
- 另以 synthetic malformed zstd/CBOR frame probe 检查生产 reader 的截断、空 frame 和非 map rejection；结果均按错误路径拒绝。
- 未运行全仓回归、Ruff、Pyright、真实 upstream、真实端口、真实磁盘故障、多进程 SQLite 压力或真实数据库访问；这些不是本轮最小相关测试范围。

## 搜索面与安全边界

已阅读 ACTIVE v8 Spec 及 v1-v8 修订记录、`RawCaptureStore`/`RawRequestCapture`、SQLite rule store、HTTP ops routes、composition/Chain/config、inference routing、direct/count driver、shared 与 provider-specific upstream error normalizer、request completion/response observation/log projection，以及相关 unit/component/integration tests。

本轮没有读取、输出或依赖真实 capture 正文、真实 token、真实 header 或真实数据库内容；测试与 probe 只使用 synthetic 输入，并只观察事件类型、长度、错误类型、布尔结果和测试状态。
