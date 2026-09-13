# Dynamic capture v15 最终只读验收

## 评审范围

判据来源为用户给出的 ACTIVE v15 与条件式 raw capture 合同，以及 `.dev/docs/raw-capture/spec.md`。范围覆盖 HTTP API + SQLite 精确规则、未命中无正文、命中后的 CBOR/zstd 真实 wire evidence、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate attempt bytes 与 completeness、首次 body pull 前边界、普通 upstream projection 的安全 metadata、proxy-owned message、ResponseObservation error events、legacy JSON rejection inactive，以及 COUNT projection 使用 body-attempt metadata。

被检对象为 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态。当前仅进行只读验收；不修改实现、测试或配置，不操作现有 4141 服务，不读取、输出或持久化 capture 正文、认证信息、token 或 credential。本报告是按用户指定路径写入的验收产物。

## 总体 verdict

**needs-fix：发现 1 个高置信度 major 生产缺陷，且 DYN-CAP-09 仍未闭合。DYN-CAP-15 会让 direct one-shot upstream failure 把原始异常 message 带回普通 completion line；最终集成测试另有 3 处 stale raw-text assertions。**

## Blocker 数

0。

## Findings

### DYN-CAP-15 —— major —— direct one-shot upstream failure 绕过安全 provenance projection

- `finding_id`: `DYN-CAP-15`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:1457-1463`
- `related_locations`: `src/app/server/routes/inference.py:917-949`、`src/app/server/routes/inference.py:1909-1920`、`tests/int/test_pipeline_app.py:3736-3802`
- **判据**：普通 upstream completion projection 只能保留安全 type/status/code 等 metadata；proxy-owned deadline/own message 可以保留，但 upstream 原始异常文本不得进入普通日志。
- **证据强度**：高。direct one-shot 路径没有给 `_tracked_delivery` 提供 upstream provenance callback；未知异常因此由 `note_runtime_failure(error, False)` 写入 `failure_provenance=None`。`_StreamAccounting._ending()` 对 `failure_provenance is None` 直接格式化 `self.failure`，导致 `ConnectionError("upstream tore")` 在 completion line 中变成 `stream failed before a terminal event: upstream tore`。最小回归 `test_one_shot_accounting_reports_how_delivery_actually_ended[upstream-tear]` 失败，测试期望的安全结果是固定 `upstream stream failure: builtins.ConnectionError`。
- **影响**：Chat Completions 等 direct one-shot 请求的 upstream transport failure 会把 provider message 泄漏到普通 completion line，并且把 upstream failure 与 proxy-owned failure 归在同一无 provenance 分支；DYN-CAP-13 的 deadline 修复因此在相邻 one-shot seam 引入了安全投影回归。
- **修复方向**：为 one-shot delivery 明确传递 upstream/local provenance，或将 `_ending()` 的 raw-message 分支收窄为显式 proxy-owned failure 类型；不能以“无 callback 就是 proxy-owned”代替 provenance，也不能把 upstream message 重新放回普通日志。

### DYN-CAP-09 —— major —— upstream 安全投影仍有 3 处最终集成断言漂移

- `finding_id`: `DYN-CAP-09`
- `severity`: `major`
- `status`: `not-closed`
- `primary_location`: `tests/int/test_pipeline_app.py:8858-8859`
- `related_locations`: `tests/int/test_pipeline_app.py:8505-8506`、`tests/int/test_pipeline_app.py:8525-8527`；`src/app/server/routes/inference.py:203-230`
- **判据**：ACTIVE v15 与 raw-capture Spec v15 修订记录要求普通 upstream detail、FailureSummary、InterruptionObservation、ResponseObservation 与 hand-over completion 只保留安全 type/status/code/presence 等 metadata；proxy-owned message 可以保留，upstream 原始异常文本不能回到普通 projection。
- **证据强度**：高。当前生产 `_safe_failure_detail()` 对这些 upstream failures 输出固定安全投影 `upstream request failed before a response`，而不是 `RemoteProtocolError` 或 upstream message。最小相关执行中：
  - `test_a_hand_over_says_what_it_swallowed` 失败，因为 completion line 仍被测试要求包含 `RemoteProtocolError` 与 `peer closed the connection`；
  - `test_real_h1_incomplete_chunked_body_records_the_exact_trigger_and_pull_timing[mid-turn]` 失败，因为 `InterruptionObservation.message` 被测试要求为 upstream 原始 `incomplete chunked read` 文本；
  - 同一测试的 `post-terminal` 参数失败，因为 `tore_after_terminal` 被测试要求包含 `RemoteProtocolError` 与原始异常文本。
  当前实现的安全输出与 ACTIVE v15 一致，失败的是最终测试合同仍把已废止的 raw text 当作验收条件。
- **影响**：最终安全投影回归不绿；更严重的是，这些断言会在将来把 upstream 原文重新放回普通日志/结构化投影时继续给出错误的绿灯，直接削弱 raw-capture 的安全边界验收。
- **修复方向**：将这 3 处断言改为固定 upstream type/status/presence metadata 与 completeness/attempt 字段，并明确把允许保留的 proxy-owned message 与 upstream raw text 分开。不要为通过旧断言而回退生产安全投影。

## 已闭合的上轮 findings

- `DYN-CAP-12`：**已闭合**。generic provider cleanup failure 现在归一化为带 request/status/observed response bytes/`body_complete=false` 的 `UpstreamError`，direct-driver failed-attempt capture 能保留 request、status、response bytes 与不完整边界。
- `DYN-CAP-13`：**已闭合**。proxy-owned client deadline 的 completion detail 不再经过 upstream safe fallback；最小 deadline integration test 通过，并保留 proxy-owned deadline message。
- `DYN-CAP-14`：**已闭合**。pre-first-pull cleanup fixture 已实现 `note_unstarted_upstream_body_cleanup()`，相关 cleanup integration test 通过。

## 最小相关验证

- `uv run pytest -q --tb=short --disable-warnings tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_log.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/pipeline/test_direct_driver.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：`246 passed`。
- 动态 capture、规则 API、pre-first-pull cleanup、client deadline 与 ResponseObservation 选择集：`25 passed`。
- count/retry attempt bytes 选择集：`6 passed`。
- unmatched refusal 与 legacy JSON rejection inactive 选择集：`2 passed`。
- safe projection / ResponseObservation 回归选择集：`12 passed, 1 failed`；失败为 DYN-CAP-09 的 `test_a_hand_over_says_what_it_swallowed`。
- 其余 upstream failure / hand-over / incomplete-body projection 选择集：`8 passed, 2 failed`；失败为 DYN-CAP-09 的 `test_real_h1_incomplete_chunked_body_records_the_exact_trigger_and_pull_timing` 两个参数。
- one-shot accounting 选择集：`2 passed, 1 failed`；失败为 DYN-CAP-15 的 `test_one_shot_accounting_reports_how_delivery_actually_ended[upstream-tear]`。
- 只读 generic cleanup carrier probe 通过：仅验证 `UpstreamError` 的 status、request/response byte lengths、`body_complete=false` 与 failed-attempt event 顺序，未输出正文。

## 搜索面与未覆盖面

已读 ACTIVE v15 raw-capture Spec、项目开发工作流、HTTP API 与 SQLite rule store、raw capture writer/reader、inference capture lifecycle、count/retry attempt recording、CodeBuddy 与 OpenAI-compatible cleanup normalization、direct-driver failed-attempt capture、request completion/logger、Responses ResponseObservation、stream cleanup 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141。除上述 findings 外，没有发现新的高置信度 ACTIVE v15 defect。报告不包含 request/response body、认证信息、token、credential 或秘密。
