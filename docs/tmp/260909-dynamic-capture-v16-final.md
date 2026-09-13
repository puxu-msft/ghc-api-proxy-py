# Dynamic capture v16 最终只读收尾验收

## 评审范围

评审对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态，判据来源为用户给出的 ACTIVE v16 条件、`.dev/docs/raw-capture/spec.md` ACTIVE v16、项目开发工作流，以及其中引用的 HTTP API、SQLite 精确匹配、普通 observability 安全投影和 attempt completeness 合同。范围覆盖 HTTP API + SQLite 规则、未命中无正文、命中后的 CBOR/zstd 真实 wire evidence、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate attempt bytes 与 completeness、pre-first-pull boundary、ordinary upstream safe metadata、proxy-owned failure/message、ResponseObservation event errors、legacy JSON rejection inactive 和 COUNT body-attempt projection。

本轮只读检查、定向测试和不落盘合成探针；没有修改实现、测试或配置，没有操作现有 4141，没有读取、输出或持久化真实 capture 正文、认证信息、token、credential 或秘密。唯一新增产物是本报告。

## 总体 verdict

**needs-fix：发现 5 个高置信度 major 问题和 1 个 minor 文档漂移，不能报告 pass。**

## Blocker 数

0。

## Findings

### DYN-CAP-09 —— major —— ordinary upstream safe projection 的最终集成断言仍未同步

- `finding_id`: `DYN-CAP-09`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `tests/int/test_pipeline_app.py:8293`
- `related_locations`: `src/app/observability/request_completion.py:779-813`、`.dev/docs/raw-capture/spec.md:52、86-91`
- **判据**：普通 `InterruptionObservation`、completion、FailureSummary 和 logger 只能保留安全 upstream type/status/reason/presence metadata；hand-over 发给客户端的消息是独立边界，可以保留客户端需要的 upstream 诊断。
- **证据强度**：高。当前生产投影把已归一化 upstream failure 映射为固定安全文本，合成生产路径 probe 也确认 upstream 异常原文不会进入普通 completion detail；但最终集成测试仍要求 `interruption["message"]` 包含 upstream 的原始 HTTP/2 事件文本。最小动态选择集为 `57 passed, 1 failed`，唯一失败是 `test_an_interrupted_turn_is_handed_back_to_the_client_as_a_tool_call`。
- **影响**：测试合同仍把已废止的 raw upstream text 当成正确结果，未来重新泄漏原文时反而会给出绿灯；当前候选不能通过最终安全回归。
- **修复方向**：把该断言改为固定安全 upstream metadata，并保留 hand-over 客户端消息的原始诊断断言；不要为通过旧断言而放宽生产投影。

### DYN-CAP-17 —— major —— direct-driver pre-first-pull discard 没有 response incomplete boundary

- `finding_id`: `DYN-CAP-17`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/direct_driver/base.py:198-215`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:513-527`、`.dev/docs/raw-capture/spec.md:50、83-84`
- **判据**：命中 capture 的每个 upstream attempt 都必须保留 response completeness；首次 body pull 前 response 被 retry、subscriber failure、rate-limit discard 或其他 discard 路径关闭时，必须写 `upstream.response.end(complete=false)`，随后写 `upstream.attempt.end(complete=false)`。
- **证据强度**：高。不落盘合成 response probe 调用 `capture_returned_upstream_response()` 后得到的 event 类型只有 `upstream.request.body, upstream.response.start`；生产 finally 随后只追加 `upstream.attempt.end(complete=false)`，没有 response end。
- **影响**：被 discard 的 attempt 无法区分“尚未开始读取 body”和“response completeness 未知”；capture 不能完整重放或诊断该 attempt。
- **修复方向**：在未消费 response 的 returned-response 分支补充幂等 `upstream.response.end(complete=false)`；已经消费的 response 继续保存实际 body 和真实 completeness，不要伪造 body bytes。

### DYN-CAP-18 —— major —— 已写入的 partial boundary 不参与 request completion warning

- `finding_id`: `DYN-CAP-18`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/observability/raw_capture.py:449-484`
- `related_locations`: `src/app/server/routes/inference.py:1442-1455`、`src/app/server/routes/inference.py:1875-1892`、`.dev/docs/raw-capture/spec.md:67-72`
- **判据**：只要 capture 中的 upstream/client response 或 attempt 以 `complete=false` 结束，request completion warning 必须恰好发出一次，并包含固定原因、首个不完整边界、`response_body_capture_complete=false` 和 `forensic_replay_complete=false`。
- **证据强度**：高。不落盘 fake store probe 先写入 `upstream.response.body`、`upstream.response.end(complete=false)` 和 `upstream.attempt.end(complete=false)`，再调用 `finish(complete=true)`；当前 warning 数量为 0。`finish()` 只检查被跳过的 body event type，没有检查已写入 end event 的 `complete` 字段。
- **影响**：mid-stream tear、pre-first-pull close 和其他已记录 partial path 可能被报告为 forensic replay complete，普通诊断也缺少应有的 incomplete warning。
- **修复方向**：request-local capture 状态记录首个 incomplete response/attempt boundary，让 `finish()` 按该状态参与 reason、response-body completeness 和 forensic completeness 投影。

### DYN-CAP-19 —— major —— provider partial/cleanup failure 在 response body 未观测时没有 response end boundary

- `finding_id`: `DYN-CAP-19`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/direct_driver/base.py:176-195`
- `related_locations`: `src/app/model_provider/upstream_errors.py:148-194、200-236`、`.dev/docs/raw-capture/spec.md:50、86-90`
- **判据**：provider status-body read、transport、timeout 和 cleanup failure 只要已经有 response status，就必须保留 request bytes、status 和 response completeness；即使 body 为零字节或尚未观测，也不能省略 `response.end(complete=false)`。
- **证据强度**：高。不落盘合成 `UpstreamError(status_code=500, body_observed=false, body_complete=false)` probe 经过 `capture_failed_upstream_attempt()` 后只有 `upstream.request.body, upstream.response.start`，没有 `upstream.response.end(complete=false)`。当前 helper 把 response end 放在 `if upstream_error.body_observed` 内，导致“已知 response、未观测 body”的 partial/cleanup failure 丢失边界。
- **影响**：OpenAI-compatible partial status-body、CodeBuddy aggregate cleanup 或其他 response cleanup failure 在零字节/未消费窗口无法表达 response incomplete，违反 provider/partial/cleanup attempt completeness 合同。
- **修复方向**：当 normalized error 有 status/response boundary 时无条件写 response end，`complete` 使用 `body_complete`；无 response 的 connect-before-send failure 仍只写 request/attempt evidence。

### DYN-CAP-20 —— major —— COUNT request 没有同步 ordinary body-attempt projection

- `finding_id`: `DYN-CAP-20`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/driver.py:526-583`
- `related_locations`: `src/app/server/routes/inference.py:750-830`、`src/app/observability/request_trace.py:225-325`、`src/app/observability/request_completion.py:632-645`
- **判据**：COUNT 的 ordinary completion/structured observation 必须和实际 upstream attempt 保持一致，不能只投影汇总 request/response byte 数而丢掉每次 attempt 的 body bytes/completeness。
- **证据强度**：高。COUNT 路径记录的是 `context.extras["count_tokens_upstream_*_bytes"]`，但没有调用 `RequestTrace.begin_upstream_body_timing()`、`note_upstream_pull_started()` 或 `note_upstream_end()`；最终 `FinalizedRequest` 只序列化 `trace.upstream_body_attempts`。因此 COUNT record 的 `observation.upstream_body_attempts` 保持空列表，即使 raw capture 已记录多次 count retry attempt。
- **影响**：COUNT 的普通日志和 structured record 只能看到汇总 bytes 与 provider reason，无法看到每个 count attempt 的 status/body/completeness；raw capture 与 ordinary projection 对同一请求的 attempt 事实不一致。
- **修复方向**：为 COUNT 的每个实际 upstream response/error/cleanup attempt 建立同一 `UpstreamBodyAttempt` 投影，或建立明确等价且由同一事实源生成的 COUNT body-attempt projection，并补充 retry、failure 和 local fallback 断言。

### DYN-CAP-21 —— minor —— active module doc 仍声称 retired rejection capture 曾持久化正文

- `finding_id`: `DYN-CAP-21`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `src/app/pipeline/subscribers/anthropic_thinking.py:5`
- `related_locations`: `src/app/observability/rejection_capture.py:19-27`、`.dev/docs/raw-capture/spec.md:23、50、91`
- **判据**：legacy JSON rejection persistence 必须 inactive；当前 conditional CBOR capture 之外不得让读者误以为普通 400 会另建正文文件。
- **证据强度**：高。当前 `rejection_capture` 是无持久化副作用的 compatibility shim，`src/app` 没有 active caller，相关 unmatched integration test 通过；但 active subscriber module doc 仍写着 rejection capture 把 outbound body 留在磁盘，和当前实现及 ACTIVE v16 相反。
- **影响**：后续维护者可能按错误文档恢复或依赖已退役的正文落盘路径；不改变当前运行时行为，因此定为 minor。
- **修复方向**：删除或改写该历史段落，并把历史取证依据放回对应 point-in-time report，不在 active module doc 中保留当前不成立的事实。

## 上轮 finding 完成度

- `DYN-CAP-09`：**未闭合**。生产 safe projection 已存在，但最终集成测试仍有一处 raw-text assertion。
- `DYN-CAP-12`：**部分闭合**。observed partial body 的 generic cleanup carrier 和 request/response bytes 已存在，但 body 未观测的 provider cleanup path 仍缺 response incomplete boundary，见 `DYN-CAP-19`。
- `DYN-CAP-13`：**已闭合于当前 probe**。one-shot proxy-owned client deadline 的 `DeliveryObservation.failure.origin` 为 proxy-owned/wrapped，proxy-owned detail 保留；未归入 upstream。
- `DYN-CAP-14`：**已闭合于 outer response-start cleanup path**。`note_unstarted_upstream_body_cleanup()` 能为未启动的 streaming owner 写入 response/attempt incomplete boundary；这不覆盖 direct-driver returned-response discard，见 `DYN-CAP-17`。
- `DYN-CAP-15`：**已闭合于 one-shot upstream tear path**。合成 upstream 异常原文未进入普通 completion detail，failure origin 为 upstream，body attempt completeness 仍被记录。
- `DYN-CAP-16`：**已闭合于 one-shot proxy deadline probe**。proxy-owned deadline 保留自身 message，未被错误投影为 upstream failure。
- `DYN-CAP-17`：**未闭合**，见同名 finding。
- `DYN-CAP-18`：**未闭合**，见同名 finding。

## 最小相关验证

- `uv run pytest -q --disable-warnings --tb=no tests/unit/observability/test_debug_capture.py tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_log.py tests/unit/observability/test_request_log_file.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/test_response_observation.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：`334 passed`。
- 动态 capture、rule API、count/retry、unmatched refusal、legacy rejection、pre-first-pull、one-shot 和 safe projection 选择集：`57 passed, 1 failed, 469 deselected`；失败为 DYN-CAP-09 的 `test_an_interrupted_turn_is_handed_back_to_the_client_as_a_tool_call`。
- safe projection integration 选择集：`5 passed, 1 failed, 272 deselected`；唯一失败仍为 DYN-CAP-09。
- 不落盘合成 probe：pre-first-pull returned response 缺 `upstream.response.end`；已写入 `complete=false` 的 partial capture 不发 completion warning；body 未观测的 provider response error 缺 `upstream.response.end`。
- 不落盘 one-shot probe：proxy-owned deadline 的 failure origin 与 detail 保持 proxy-owned；upstream tear 的异常原文不进入普通 completion detail。

## 搜索面与未覆盖面

已读 ACTIVE v16 raw-capture Spec、项目开发工作流、debug capture SQLite store、ops HTTP routes、raw capture writer/reader、inference capture lifecycle、direct driver 与 COUNT driver、provider error normalization、CodeBuddy/OpenAI-compatible client、request completion/log/trace、Responses observation、rejection shim 及相关 unit/component/integration tests。未运行完整 regression、Ruff、Pyright、真实 upstream、真实磁盘故障、多进程 append 压力或部署验收；未操作现有 4141。除上述 findings 外，没有把未执行的环境类场景推断为已验证。
