# Dynamic capture v13 最终只读验收

## 评审范围

判据来源是用户本轮给出的 ACTIVE v13 raw-capture 条件、HTTP API + SQLite 规则合同，以及 `.dev/docs/raw-capture/spec.md`。范围覆盖条件选择、未命中不持久化正文、命中后的 CBOR Sequence/zstd 真实 wire evidence、provider/status/partial/cleanup/count/retry attempt completeness、CodeBuddy aggregate 的 raw SSE 与 synthetic response 分离、普通 upstream detail/logger/FailureSummary/InterruptionObservation/ResponseObservation 的安全投影，以及 legacy JSON rejection persistence 的退役状态。

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态。工作树原有大量未提交改动，本轮没有回滚、覆盖或修改实现和测试；只写入本报告，没有读取、输出或持久化 capture 正文、认证信息、token 或 credential，也没有操作 4141。

## 总体 verdict

**未通过：发现 2 个高置信度 major 问题。**

## blocker 数

0。

## Findings

### DYN-CAP-09 —— major —— v13 安全投影已经改动，但旧 raw-text 回归断言仍在最终测试树中

- `finding_id`：`DYN-CAP-09`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`tests/int/test_pipeline_app.py:7924-7932`
- `related_locations`：`tests/int/test_pipeline_app.py:3794-3802`、`3933-3938`、`8106-8142`、`8660-8664`、`8951-8955`；`tests/unit/observability/test_request_completion.py:504-545`；`tests/int/test_pipeline_app.py:8280-8283`、`8499-8521`
- **判据**：ACTIVE v13 要求普通 upstream detail/logger、`FailureSummary`、`InterruptionObservation` 和 `ResponseObservation` 只保留安全的 type/status/code 或固定 presence flag；proxy-owned message 可以保留，但 upstream raw error text 不能回到普通投影。用户条件还明确要求 DYN-CAP-09 的旧 raw-text assertions 已同步。
- **证据**：当前生产路径已经把已归一化和未归一化 upstream failure 投影为固定安全元数据，Responses SSE `error` event 也已经走 `_safe_error_field()`；但最终测试树仍有多处要求 upstream 异常原文、异常 repr 或长度截断后的 raw-text 形状，另有断言仍绑定旧的 proxy-owned detail 形状。最小相关 sweep 仍失败：
  - `test_one_shot_accounting_reports_how_delivery_actually_ended[upstream-tear]`
  - `test_a_client_deadline_is_accounted_as_the_failure_its_frame_reports`
  - `test_a_tear_after_the_stop_reason_is_still_a_tear`
  - `test_delivery_replay_reuses_the_normal_attempt_that_produced_the_stream`
  - `test_a_long_upstream_failure_is_cut_before_it_reaches_the_line`
  - `test_a_long_failure_is_cut_on_the_hand_over_line_too`
  - `test_runtime_upstream_stream_failure_is_reported_without_escaping_the_app`
  - `test_a_tear_after_a_turn_that_ran_out_of_room_is_reported_alongside_the_hand_over`
- **影响**：DYN-CAP-06 的实现方向已经符合安全投影要求，但最终测试合同仍把已废止的 raw-text 行为当成通过条件；交付不能报告为最终通过。测试也没有可靠地把“安全 type/status/code”与“允许保留的 proxy-owned message”分开断言。
- **建议修复方向**：把上述断言统一改为固定 type/status/code、attempt 和 completeness 元数据；保留 proxy-owned deadline、hand-over 等消息的断言时，明确它们不是 upstream 原文。同步覆盖普通 structured record、completion line 和 interruption observation，不要把 upstream raw text 重新加回生产投影。

### DYN-CAP-10 —— major —— 首次 body pull 之前关闭 streaming response 时没有写入不完整 attempt 边界

- `finding_id`：`DYN-CAP-10`
- `severity`：major
- `status`：open
- `primary_location`：`src/app/server/routes/inference.py:1596-1613`
- `related_locations`：`src/app/server/routes/inference.py:1734-1737`、`1800-1832`；`src/app/observability/request_completion.py:646-650`；`src/app/server/routes/inference.py:859-865`
- **判据**：ACTIVE v13 要求每个实际 upstream attempt 保留边界和实际收发证据；partial、client abort 和 cleanup 路径必须以 `complete=false` 反映不能证明完整的 exchange。`request.end` 不能替代 upstream response/attempt boundary。
- **证据**：响应 headers 返回后，初始 attempt 已写入 `upstream.request.body` 与 `upstream.response.start`。如果 `http.response.start` 发送失败，或客户端在第一段 body 被 pull 之前断开，`_StreamingResponseCleanup.aclose()` 只关闭尚未启动的外层 async generator；未启动的 `_counted_upstream()` 不会执行其 `finally`。一个不落盘正文的内存 probe 对同样的嵌套 close 路径得到空事件序列，说明 `upstream.response.end` 和 `upstream.attempt.end` 都没有产生。之后的 `completion.publish()` 只调用 `RawRequestCapture.finish()` 写 `request.end`，不会补回缺失的 attempt boundary。
- **影响**：命中规则的 capture 可能留下 request/response start，却没有 `response.end(complete=false)` 或 `attempt.end(complete=false)`；回放者无法区分“尚未读取 body”“body 被中止”与其他不完整状态，违反 attempt completeness 合同。DYN-CAP-08 的已修复路径只覆盖已经启动并进入 `_counted_upstream()` 的 stream。
- **建议修复方向**：为每个 capture attempt 增加幂等的“body 尚未启动即被关闭”终结路径，由外层 response cleanup 调用，写入 `upstream.response.end(complete=false)` 和 `upstream.attempt.end(complete=false)`；正常启动后的 `_counted_upstream()` finalizer 与该路径必须互斥，避免重复边界。增加 response-start send failure 和 pre-first-pull client disconnect 的回归测试。

## 上轮 finding 完成度

- `DYN-CAP-06`：**生产实现已闭合，最终交付未闭合**。安全投影入口已经统一到固定 upstream 元数据，但 DYN-CAP-09 证明旧测试断言仍未同步。
- `DYN-CAP-07`：**已闭合于当前实现和 focused tests**。嵌套与 flat Responses SSE `error` event 都经过安全 error-field projection；相关 unit tests 通过。
- `DYN-CAP-08`：**已闭合于已启动的 streaming source-cleanup path**。`_counted_upstream()` 现在以 EOF 与 cleanup success 的合取决定 response/attempt completeness；相关 streaming cleanup tests 通过。DYN-CAP-10 是它未覆盖的 pre-first-pull 接缝。
- `DYN-CAP-09`：**未闭合**。最终测试树仍有多处旧 raw-text assertions，并且 focused sweep 仍失败。

## 已核验且符合当前 Spec 的面

- SQLite rule store、唯一约束、provider/resolved model/session/可选 agent 的规范化精确匹配、HTTP `GET/POST/DELETE /api/debug/capture-rules` 和下一次匹配立即生效的接线存在。
- 未命中规则不会创建 request capture 或 `.cborseq.zst` 文件；命中后在第一次 upstream attempt 前补录已读取的 inbound body。
- 新 capture 使用每 item 独立 zstd frame 的 CBOR map sequence，路径只含 identity hash；缺失 agent-id 使用独立缺失值；旧 `.jsonl.zst` 只计入配额，不参与新格式读写。
- writer acknowledgement、quota reservation、partial-write poison、跨新 store 的 reader 验证、count retry、status/partial body evidence、CodeBuddy aggregate raw SSE extension、synthetic downstream response 分离、account-switch retry 和 legacy rejection shim 的 focused paths 保持存在。
- 当前 `src/` 没有 active `rejection_capture` caller；legacy JSON rejection persistence 仍 inactive。

## 最小相关验证

- `uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py -q --tb=no --disable-warnings`：26 passed。
- provider aggregation、normalization 和 CodeBuddy focused selection：62 passed。
- `request_completion`、`ResponseObservation` 和 projection focused selection：128 passed。
- capture selection、HTTP rule API、count、unmatched refusal 和 legacy rejection selection：19 passed。
- streaming failure/cleanup selection：19 passed。
- upstream failure、replay、tear、interruption 和 cleanup sweep：28 passed，8 failed；失败均落在最终安全投影/旧断言接缝。
- 一个只输出事件类型与 `complete` 布尔值的内存 probe 验证了 EOF 后 cleanup failure 会写 `response.end=false` 与 `attempt.end=false`；另一个 pre-first-pull nested-close probe 得到空 boundary，形成 DYN-CAP-10 的直接证据。

## 搜索面与未覆盖面

已读 ACTIVE v13 raw-capture Spec、开发工作流、用户控制的 API/config 相关条目、debug capture SQLite store、ops HTTP routes、inference capture lifecycle、raw capture writer/reader、count path、direct driver、GHC/OpenAI-compatible/CodeBuddy client、request completion、request logger、Responses observation、stream delivery、rejection shim 及相关 unit/component/integration tests。

未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141。除 DYN-CAP-09 与 DYN-CAP-10 外，未发现新的高置信度缺陷。
