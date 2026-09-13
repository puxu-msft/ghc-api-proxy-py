# Dynamic capture v13 最终只读复审

## 评审范围

判据来源是用户本轮给出的 ACTIVE v13 条件式 raw capture 合同与 `.dev/docs/raw-capture/spec.md`。范围覆盖 HTTP API + SQLite 条件选择、未命中不持久化正文、命中后的 CBOR Sequence/zstd 真实 wire capture、partial/status/cleanup/count/provider attempt completeness、普通 completion/detail/logger/FailureSummary/InterruptionObservation/ResponseObservation 的安全投影、CodeBuddy aggregate synthetic 与 raw SSE 分离，以及 legacy JSON rejection persistence 退役状态。被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态；本轮只读，没有修改实现或测试，没有读取、输出或持久化 capture 正文、认证信息、token 或 credential，也没有操作 4141。

## 总体 verdict

**needs-fix：发现 1 个高置信度 major 问题。生产实现对应 DYN-CAP-06/07/08 的三处修复已落地，但相关回归测试仍有旧合同断言，当前最终工作树不能报告 pass。**

## blocker 数

0。

## Findings

### DYN-CAP-09 —— major —— v13 安全投影已改为固定元数据，但相关回归测试仍要求 raw upstream error text

- `finding_id`：`DYN-CAP-09`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`tests/int/test_pipeline_app.py:7883-7934`
- `related_locations`：`tests/int/test_pipeline_app.py:7937-7980`；`tests/unit/observability/test_request_completion.py:1734-1774`
- **判据**：ACTIVE v13 与用户条件要求普通 completion/detail/logger、`FailureSummary`、`InterruptionObservation` 和 `ResponseObservation` 不复制 raw upstream error text/body；hand-over 的客户端消息不属于这些普通投影。
- **证据**：当前实现已经在 `src/app/server/routes/inference.py:203`、`1026`、`1348` 和 `src/app/observability/request_completion.py:765` 统一使用固定的 upstream type/status/reason projection；Responses SSE `error` event 在 `src/app/pipeline/response_observation.py:295-303` 使用 `_safe_error_field`。但最小相关测试仍要求 replay 的 `replaced_failures`、completion line、post-terminal `tore_after_terminal` 和 upstream event ending 包含原始异常类型或文本，导致测试失败：
  - `test_reported_stream_failure_outranks_an_earlier_send_disconnect[upstream_event]`：1 failed；
  - `test_a_replay_is_reported_on_the_request_line`：1 failed；
  - `test_a_tear_after_the_turn_finished_is_recorded_without_being_called_a_failure`：1 failed。
- **影响**：生产投影已经符合 v13 安全边界，但最终测试树仍把已废止的 raw-text 行为当作通过条件，相关 focused regression 不绿，DYN-CAP-06 的最终交付闭合不成立。
- **建议修复方向**：把上述断言改为检查固定 type/status/reason projection，并保留 hand-over 客户端消息的独立断言；不要把 raw upstream text 重新加回普通 completion、logger 或 structured record。

## 上轮 finding 完成度

- `DYN-CAP-06`：**实现已闭合，交付未闭合**。`_ending`、replaced failure、post-terminal tear、普通 logger 和 completion safe projection 已改为固定安全元数据，但旧回归断言仍失败，见 DYN-CAP-09。
- `DYN-CAP-07`：**实现已闭合**。嵌套和平面 Responses SSE `error` event 都走 `_safe_error_field`；相关 provider error observation focused tests 通过。
- `DYN-CAP-08`：**实现已闭合于 reviewed streaming source-cleanup path**。`_counted_upstream` 在 cleanup 完成后才写 `upstream.response.end` 与 `upstream.attempt.end`，并以 EOF 与 cleanup success 的合取决定 `complete`；相关 stream failure/cleanup focused tests 通过。

## 已核验且符合当前 Spec 的面

- SQLite rule store、规范化后的 provider/model/session/可选 agent 精确匹配、HTTP `GET/POST/DELETE /api/debug/capture-rules` 和下一次匹配立即生效的接线存在。
- 未命中规则不会创建 capture 或保存 request/response body；命中后在第一次 upstream attempt 前补录原始 inbound body。
- 新 capture 使用 CBOR map sequence 与每 item 独立 zstd frame，路径只使用 identity hash；legacy `.jsonl.zst` 仅计入旧文件配额，不参与新格式读写。
- partial status-body、429/5xx、provider transport、count retry、CodeBuddy aggregate 的 request/response wire evidence 与 attempt 边界接线保持存在；CodeBuddy synthetic JSON 与真实 SSE raw body 走分离字段。
- `rejection_capture` 只保留无持久化副作用的兼容 shim，当前 `src/` 没有 active caller，legacy JSON rejection persistence inactive。

## 最小相关验证

- `tests/unit/observability/test_raw_capture.py`、`test_debug_capture.py`、`test_rejection_capture.py`、`test_provider_error_wire_capture.py`：26 passed。
- provider wire、CodeBuddy aggregate、upstream normalization 相关选择集：41 passed，26 deselected。
- capture rule、raw capture、count、rejection、Responses status/error 相关集成选择集：33 passed，109 deselected。
- direct driver、request logger、request log file 相关选择集：7 passed，271 deselected。
- 关键 streaming failure/cleanup 选择集：4 passed，67 deselected。
- `test_request_completion.py` 与 Responses observation 相关选择集：127 passed，1 failed；失败即 DYN-CAP-09。

## 搜索面与未覆盖面

已读 ACTIVE v13 Spec、项目开发工作流、debug capture SQLite store、ops HTTP routes、inference capture lifecycle、raw capture writer/reader、count path、direct driver、provider error normalization、CodeBuddy/OpenAI-compatible client、request completion、request logger、Responses observation、rejection shim 及相关 unit/component/integration tests。未运行完整 regression、Ruff、Pyright、真实 upstream 或部署验收；未操作现有 4141。除 DYN-CAP-09 外，未发现新的高置信度生产行为 defect。
