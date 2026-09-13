# Dynamic capture v15 最终只读验收

## 评审范围

判据来源是用户给出的 ACTIVE v15、`.dev/docs/raw-capture/spec.md`、条件式 HTTP API 与 SQLite rules 合同，以及普通 observability 安全投影和 attempt completeness 合同。被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树，覆盖规则匹配、未命中请求、CBOR/zstd wire capture、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate attempt evidence、pre-first-pull、普通 upstream metadata、proxy-owned failure、one-shot `_counted_upstream` provenance、COUNT projection 与 legacy JSON inactive。未覆盖完整 regression、Ruff、Pyright、真实 upstream 和部署切换。

本轮只读检查、定向测试和不落盘探针；没有修改实现、测试或配置，没有操作现有 4141，也没有读取、输出或持久化 request/response 正文、认证信息、token、credential 或秘密。报告文件是按用户指定路径写入的验收产物。

## 总体 verdict

**needs-fix：发现 4 个高置信度 major 问题，DYN-CAP-15 已闭合；DYN-CAP-09 仍未闭合。**

## Blocker 数

0。

## Findings

### DYN-CAP-09 —— major —— upstream 安全投影相关最终集成断言仍未同步

- `finding_id`: `DYN-CAP-09`
- `severity`: `major`
- `status`: `not-closed`
- `primary_location`: `tests/int/test_pipeline_app.py:8510-8532`
- `related_locations`: `tests/int/test_pipeline_app.py:8863-8864`、`src/app/server/routes/inference.py:203-230`、`src/app/server/routes/inference.py:1094-1114`
- **判据**：普通 upstream detail、FailureSummary、InterruptionObservation、ResponseObservation 与 hand-over completion 只能保留安全 type/status/code/presence 等 metadata；proxy-owned message 可以保留，但 upstream 原始异常文本不得回到普通 projection。
- **证据强度**：高。最小相关集实际为 `17 passed, 3 failed`。三个失败分别要求 `tore_after_terminal`、`InterruptionObservation.message` 和 hand-over completion line 包含 upstream 原始异常类型或文本；当前生产投影已经输出固定安全 upstream reason，因此失败的是测试合同而不是生产安全边界。
- **影响**：最终相关测试不绿；这些旧断言还会把未来重新泄漏 upstream raw text 的回归判为正确结果，削弱 ACTIVE v15 的分辨力。
- **修复方向**：把断言改为固定 upstream metadata、attempt/completeness 与 proxy-owned message 的区分，不要为通过旧断言而放宽生产投影。

### DYN-CAP-16 —— major —— one-shot client deadline 被错误归因于 upstream

- `finding_id`: `DYN-CAP-16`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:1914-1924`
- `related_locations`: `src/app/server/routes/inference.py:919-940`、`src/app/pipeline/delivery/stream.py:295-330`
- **判据**：one-shot `_counted_upstream` 必须传递 upstream body-started provenance；该 provenance 不能把外层 proxy-owned deadline 或其他本侧失败伪装成 upstream failure。普通 projection 必须区分 upstream failure 与 proxy-owned failure；proxy-owned message 可以保留。
- **证据强度**：高。不落盘生产路径探针让 `/v1/chat/completions` 的 one-shot body 在已开始后触发 `ClientDeadlineError`。当前 `_tracked_delivery` 因 `assembler is None and upstream_body_started` 建立恒真的 upstream provenance，最终 completion detail 变成类型化的 upstream failure，`DeliveryObservation.failure.origin` 也会被记为 upstream；同一错误没有走 one-shot 专用的 `on_runtime_failure(..., False, ...)` 路径。该探针没有输出 response body 或秘密。
- **影响**：所有启用 client deadline 的 one-shot 请求在 deadline 落到 body pull 阶段时都会错误归因，破坏普通 observability 的失败所有权和 proxy-owned deadline 投影。
- **修复方向**：为 one-shot delivery 接入与 block path 相同的 runtime failure provenance，或只允许显式确认的 upstream body failure 使用 one-shot upstream marker；不能用“body 已开始”作为所有后续异常的恒真 upstream 证明。

### DYN-CAP-17 —— major —— direct-driver pre-first-pull discard 缺少 `upstream.response.end(complete=false)`

- `finding_id`: `DYN-CAP-17`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/direct_driver/base.py:198-215`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:513-527`、`.dev/docs/raw-capture/spec.md:83-84`
- **判据**：命中 capture 的每个实际 attempt 都必须保留 response completeness；首次 body pull 前 response 被 retry、subscriber failure、rate-limit discard 或其他 hand-off failure 关闭时，必须显式写 `response.end(complete=false)`，并随后写 `attempt.end(complete=false)`。
- **证据强度**：高。对 `capture_returned_upstream_response()` 的不落盘 synthetic probe 显示，未消费的 response 只产生 `upstream.request.body`、`upstream.response.start` 和 `upstream.attempt.end(complete=false)`，没有 `upstream.response.end(complete=false)`。生产 finally 在所有未 hand-off 的 returned response 上调用该 helper，因此这是实际 direct-driver 接缝而不是测试替身差异。
- **影响**：命中规则的 discarded attempt 无法区分“尚未开始读取 body”和“response evidence 丢失”；pre-first-pull incomplete boundary 不完整，wire capture 不能按 spec 重放或诊断该 attempt。
- **修复方向**：在未消费 response 的 returned-response cleanup 分支补充幂等 `upstream.response.end(complete=false)`；保持已经消费的 response 继续记录实际 body 和完整性，不要伪造 body bytes。

### DYN-CAP-18 —— major —— 已记录的 partial response 不会进入完成诊断

- `finding_id`: `DYN-CAP-18`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/observability/raw_capture.py:449-472`
- `related_locations`: `src/app/server/routes/inference.py:1420-1425`、`src/app/server/routes/inference.py:1845-1861`
- **判据**：只要 capture 中的 upstream/client response body 或 attempt 以 incomplete 结束，request completion warning 必须恰好发出一次，并包含固定原因、首个缺失事件、`response_body_capture_complete=false` 和 `forensic_replay_complete=false`。记录了 `response.end(complete=false)` 不能被当作完整 capture。
- **证据强度**：高。不落盘 fake store probe 先写入 `upstream.response.body`、`upstream.response.end(complete=false)` 和 `upstream.attempt.end(complete=false)`，再以 `finish(complete=true)` 结束；当前 `RawRequestCapture.finish()` 没有 warning，并把 `response_body_complete` 计算为 true。实现只检查被跳过的 body event type，不检查已写入 end event 的 `complete` 字段。
- **影响**：上游 mid-stream tear、首次 body pull 前关闭和其他 partial path 可能把 capture 文件中的明确不完整边界报告成 forensic replay complete，普通日志也不会给出应有的 incomplete 诊断。
- **修复方向**：在 request-local capture 状态中记录 response/attempt completeness，`finish()` 按首个 incomplete boundary 参与 reason、response-body completeness 和 forensic completeness 投影；不要只依赖 writer drop 状态。

## 已闭合与已验证的承重要求

- **DYN-CAP-15 已闭合**：生产 one-shot call 已把 `on_body_started=one_shot_accounting.note_upstream_body_started` 传入 `_counted_upstream`。不落盘 upstream tear probe 得到固定安全 upstream reason，没有把 upstream exception message 带入普通 completion line。
- 条件式 HTTP API、SQLite unique/idempotent rule store、精确 provider/model/session/可选 agent 匹配、缺失 agent 的独立分组、未命中不创建 capture、命中后补录 inbound body、CBOR Sequence + per-item zstd frame、legacy `.jsonl.zst` inactive，以及 count retry attempt index 均通过相关测试。
- CodeBuddy non-stream aggregate 的真实 upstream SSE body 与 synthetic response 分离并保留，provider status/partial body/cleanup normalization 的 focused tests 通过。

## 最小相关验证

- `uv run pytest -q --tb=short --disable-warnings tests/unit/observability/test_debug_capture.py tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_log.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/pipeline/test_direct_driver.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：`249 passed`。
- 动态 capture、count/retry、unmatched refusal、legacy JSON inactive、pre-first-pull、one-shot accounting、cleanup 和安全 projection 选择集：`17 passed, 3 failed, 258 deselected`；失败全部对应 DYN-CAP-09 的 stale raw-text assertions。
- 额外不落盘探针确认 DYN-CAP-16、DYN-CAP-17、DYN-CAP-18；探针只检查安全 metadata、事件类型、complete 标志和 warning 数量，没有输出正文或秘密。

## 搜索面与未覆盖面

已读 ACTIVE v15 raw-capture Spec、项目开发工作流、debug capture HTTP/SQLite store、raw capture writer/reader、inference capture lifecycle、direct driver 与 count retry、CodeBuddy/OpenAI-compatible/upstream error normalization、request completion/projection、one-shot/block delivery、pre-first-pull cleanup 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream、真实 capture reader 数据和部署验收；未操作现有 4141。除上述四项外，没有发现新的高置信度 ACTIVE v15 defect。
