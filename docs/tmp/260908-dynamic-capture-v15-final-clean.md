# Dynamic capture v15 最终只读收尾验收

## 评审范围

判据来源为用户给出的 ACTIVE v15、`.dev/docs/raw-capture/spec.md` 及其所引用的条件式 HTTP API、SQLite、二进制 wire capture、普通 observability 安全投影与 attempt completeness 合同。被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态，覆盖动态 capture 规则与匹配、未命中请求、CBOR/zstd wire evidence、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate、pre-first-pull、普通 upstream metadata、proxy-owned failure、ResponseObservation、legacy JSON rejection 与 COUNT projection。明确不覆盖完整 regression、Ruff、Pyright、真实 upstream 或部署切换。

本轮仅只读检查与测试；没有修改实现、测试或配置，没有操作现有 4141，也没有读取、输出或持久化真实 capture 正文、认证信息、token、credential 或秘密。按用户指定路径写入本验收报告。

## 总体 verdict

**needs-fix：发现 1 个高置信度 major 生产缺陷，且 DYN-CAP-09 的最终集成测试合同仍未同步。**

## Blocker 数

0。

## Findings

### DYN-CAP-15 —— major —— direct one-shot upstream failure 仍可能绕过安全 provenance projection

- `finding_id`: `DYN-CAP-15`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:921-940`
- `related_locations`: `src/app/server/routes/inference.py:1912-1924`、`src/app/server/routes/inference.py:1457-1464`、`tests/int/test_pipeline_app.py:3757-3805`
- **判据**：普通 upstream completion projection 只能保留安全 type/status/code 等 metadata；proxy-owned deadline 或其他 proxy-owned message 可以保留，但 upstream 原始异常文本不得进入普通日志。
- **证据强度**：高。one-shot `/chat/completions` 分支调用 `_counted_upstream(...)` 时没有传入 `on_body_started=...`。`_tracked_delivery` 只有在 `assembler is None and upstream_body_started` 时才把未带 callback 的异常判为 one-shot upstream；实际只读端到端探针让 one-shot upstream 在已经产生 body 后抛出带合成文本的 transport exception，完成日志出现了该 upstream exception 文本，而不是固定的安全 upstream projection。现有 `test_one_shot_accounting_reports_how_delivery_actually_ended` 通过手工预置 `upstream_body_started` 与 provenance，未覆盖这个生产接缝。
- **影响**：direct one-shot upstream transport failure 会把 provider message 带入普通 completion line，并再次把 upstream failure 与 proxy-owned failure 混在同一无 provenance 分支；上一轮所称的 `_tracked_delivery` 修复没有闭合实际 one-shot 入口。
- **修复方向**：one-shot `_counted_upstream` 必须传递实际 upstream body-started provenance，或由 one-shot delivery 建立明确的 upstream/local provenance；只有显式 proxy-owned failure 才可保留原始 proxy message。不得用“没有 callback 就当作 proxy-owned”或重新放回 upstream raw text。

### DYN-CAP-09 —— major —— upstream 安全投影相关最终集成断言仍要求废止的 raw text

- `finding_id`: `DYN-CAP-09`
- `severity`: `major`
- `status`: `not-closed`
- `primary_location`: `tests/int/test_pipeline_app.py:8510-8532`
- `related_locations`: `tests/int/test_pipeline_app.py:8840-8864`、`src/app/server/routes/inference.py:1094-1114`、`src/app/observability/request_completion.py:765-782`
- **判据**：ACTIVE v15 要求普通 upstream detail、FailureSummary、InterruptionObservation、ResponseObservation 与 hand-over completion 只保留安全 upstream metadata；proxy-owned message 可以保留，upstream 原始异常文本不能回到普通 projection。
- **证据强度**：高。最小相关集实际结果为 `26 passed, 3 failed`。失败的三项仍分别要求 `RemoteProtocolError`、`peer closed connection` 或 `incomplete chunked read` 原文；当前生产安全投影已经输出固定的 `upstream request failed before a response`，所以这是最终测试合同漂移，不是应当回退生产安全边界的理由。
- **影响**：最终相关测试不绿；这些旧断言还会把未来重新泄漏 upstream raw text 的回归当成正确结果，削弱 ACTIVE v15 的验收分辨力。
- **修复方向**：把剩余断言改为固定 upstream type/status/presence metadata、attempt/completeness 与 proxy-owned message 的区分，不要为通过旧断言而放宽生产安全投影。

## 最小相关验证

- `uv run pytest -q --tb=short --disable-warnings tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_log.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/pipeline/test_direct_driver.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：`246 passed`。
- 动态 capture、规则 API、count/retry、pre-first-pull、client deadline、unmatched refusal 与 legacy JSON rejection 选择集：`26 passed, 3 failed`；失败全部为上述 DYN-CAP-09 的旧 raw-text assertions。
- 只读 one-shot production-path probe 复现 DYN-CAP-15；探针只检查安全投影与合成异常文本是否出现，没有输出响应正文或秘密。

## 已覆盖搜索面与未覆盖面

已读 ACTIVE v15 raw-capture Spec、项目开发工作流、HTTP API 与 SQLite rule store、raw capture writer/reader、inference capture lifecycle、direct-driver failed-attempt capture、count/retry、CodeBuddy 与 OpenAI-compatible cleanup normalization、request completion/logger、Responses ResponseObservation、stream cleanup、one-shot delivery 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141；未读取任何真实 capture 文件或数据库；未输出 request/response body、认证信息、token、credential 或秘密。
