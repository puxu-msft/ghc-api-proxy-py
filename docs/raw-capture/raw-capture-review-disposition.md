# Raw capture 评审处置账

状态：closed（Task 1–6 scoped findings 已 closed；Git integration 仍 pending/keep，不等同于全量系统验收）
日期：2026-09-09
范围：当前共享工作树 `/home/xp/src/ghc-api-proxy-py` 中 Task 1–6 的 raw-capture 实现、测试、实现报告与 scoped review/fix 记录。
权威规格：`.dev/docs/raw-capture/spec.md` ACTIVE v23。规格继续是行为的唯一权威；本轮没有为了迁就实现而削弱或改写任何 v23 条款。

> 本文是 v23 实现切片的 point-in-time disposition。2026-09-13 的 ACTIVE v24 已作为后续设计修订 supersede v23 的 capture header/credential、capability matrix、History attachment 与 replay 关系；本文的 v23 closeout 不外推为 v24 已实现。
报告原件：`.dev/docs/raw-capture/reports/` 下的 raw-capture review reports，以及 `.superpowers/sdd/plan-f8086b646635/` 下的 Task 1–5 implementation/review reports 和 `final-review.md`，均保持 point-in-time 原文不变。

## 处置原则

本账只记录报告 claim 在当前字节上的最终成立度、修复状态和可重跑证据，不替代规格，也不把 scoped 测试外推为全量测试或真实 upstream 验收。重复报告的同一语义缺陷合并处置，但每个原始 finding ID 都保留在下表中。被 refute 的 claim 记录为 refuted，不伪装成“已修复”；真正没有采纳的事项才进入 deferred ledger。本轮没有新增 deferred 条目。

## v23 条款逐项核对

| v23 条款 | 当前核对结论 | 实现、测试与证据 | claim/fix 状态 |
|---|---|---|---|
| §1、§2、§3：二进制格式、分组路径、缺失 agent namespace、旧 JSONL 和身份边界 | Task 1–6 未改变这些既有行为；当前实现仍使用 CBOR Sequence、独立 zstd frame、SHA-256 24-character session/agent prefixes、独立 missing-agent namespace 与 `.cborseq.zst`，不把 legacy JSONL 纳入新格式或配额 | `test_capture_is_a_stream_of_native_cbor_maps_not_json`、`test_capture_appends_complete_frames_and_rejects_a_truncated_tail`、`test_capture_path_uses_exact_hash_prefixes_without_raw_identity_values`、`test_missing_agent_id_has_its_own_exact_hashed_capture_group`、`test_legacy_jsonl_files_do_not_participate_in_any_quota`；Task 6 fix report 的 focused raw-capture evidence | 已验证（本轮未发现与 v23 或已验证用户目标冲突） |
| §2.1：规则持久化、实际发送 model-id、精确匹配、匹配时机、补录和 CRUD | 规则选择与入站 body 补录保持成立；配置 store 的 HTTP CRUD 正路径和缺失 id 404 已有真实 pipeline route control。实现 finding 05 中“没有 HTTP CRUD 测试”的 claim 被当前测试 refute，不是待修复项。未配置 store 的错误形状另行采纳并已修复为稳定 503 JSON | `tests/int/test_pipeline_app.py:351-406` 的 `test_raw_capture_is_selective_and_rule_api_is_persistent` 覆盖 POST 201、重复 POST 200、GET、422、DELETE 204 和同 id 再 DELETE 404；`test_capture_rule_management_reports_unconfigured_store` 覆盖 GET/POST/DELETE 的 503 envelope；证据命令 E2、E3 | CRUD claim refuted；absent-store claim adopted and fixed |
| §4：实际 request/response wire evidence、retry/failed attempt、timeout、普通日志安全投影 | Task 1 将 attempt 业务结果与 request-level evidence completeness 分开；Task 2 在实际 transport boundary 观察 request bytes，并区分 observed-empty 与 absent；Task 4/6 让 unknown failure、exception chain 和 note 只投影固定 upstream status 或稳定 exception type/metadata；准备阶段 warning 也只保留安全 metadata，client wire error 不变 | `test_failed_attempt_after_complete_response_does_not_report_request_incomplete`、`test_rule_selected_count_capture_keeps_each_upstream_retry`、`test_header_timeout_keeps_transport_boundary_raw_capture`、`test_error_fallback_distinguishes_observed_empty_body_from_absent_evidence`、`test_provider_error_normalizers_distinguish_observed_empty_request_from_absence`、`test_a_request_that_raised_on_its_way_out_still_writes_its_one_line`、`test_disconnect_cleanup_failure_projects_metadata_without_leaking_the_error_or_note`、`test_local_stream_failure_preserves_the_error_without_recording_its_text`、`test_non_ghc_direct_clients_observe_active_capture_at_transport_boundary`、`test_capture_hook_is_idempotent_and_excludes_token_and_catalog_traffic`；Task 6 fix report 的 focused evidence；source-level durable final re-review | 已验证；Task 1–6 findings closed within scoped evidence and final review chain |
| §5：per-file quota、reservation、bounded queue、writer ack、partial poison、跨 store 验证和 count cleanup | Task 1 保留并验证 committed-event/ack 记账、准备失败和 poison 语义；全局 `max_total_bytes` 已由前序实现移除，兼容路径只丢弃旧键并发出 DeprecationWarning；Task 3 将 buffered count 的 response boundary 推迟到 `aclose()` 之后；Task 6 为 valid-zstd/non-map 与 multi-item-in-one-frame 的跨 store 首次 append 增加判否控制 | `test_legacy_jsonl_files_do_not_participate_in_any_quota`、`test_quota_drop_is_reported_safely_at_request_completion`、`test_writer_error_is_acknowledged_and_releases_reservations`、`test_writer_failure_rollback_preserves_concurrent_successful_cost`、`test_partial_write_poisons_shared_path_for_the_next_request`、`test_partial_write_poison_is_recovered_by_a_new_store`、`test_new_store_first_append_rejects_valid_zstd_with_invalid_cbor_items`、`test_new_store_validates_and_appends_to_a_complete_existing_stream`、`test_rule_selected_count_capture_marks_cleanup_failure_incomplete`；Task 6 fix report 的 focused raw-capture evidence；source-level durable final re-review | 已验证；count cleanup、quota 和 RC-FINAL-03 findings 已关闭 within scoped evidence and final review chain |
| §6：恰好一次安全完成 warning、首个丢失原因、response-body completeness、writer/path 状态和封闭 reason enum | v23 §6 已明确完整 reason 集合。Task 1 的 committed response evidence 谓词修复了首事件 drop 与晚到非 body drop 两个方向；safe warning 不再格式化 path 或异常原文。Task 4/6 的 completion fallback、FailureSummary、InterruptionObservation、secondary cleanup 和 note metadata 只输出固定 safe projection | `test_store_closed_before_request_start_reports_missing_response_body`、`test_committed_response_body_survives_late_store_closed_request_end`、`test_queue_full_preparation_warning_is_safe`、`test_capture_error_preparation_warning_is_safe`、`test_writer_error_is_acknowledged_and_releases_reservations`、`test_partial_write_poisons_shared_path_for_the_next_request`、`test_interruption_evidence_is_ordered_typed_and_orthogonal_to_delivery`、`test_local_stream_failure_preserves_the_error_without_recording_its_text`；Task 6 fix report 的 focused evidence；source-level durable final re-review | 已验证；F-01 duplicate、store-closed、safe warning、safe fallback 和 RC-FINAL-01 findings 已关闭 within scoped evidence and final review chain |
| §7：修订记录 | `spec.md` 已是 ACTIVE v23，§6 的 reason enum 与实现当前使用集合一致。本轮不改 spec，不把报告的旧 v22 header 当作当前权威 | 直接读取 `/home/xp/src/ghc-api-proxy-py/.dev/docs/raw-capture/spec.md` 全文；文档自审命令 E7 | 已核对 |

## 发现逐条处置

| finding ID | 最终 claim | fix / disposition | 当前证据与状态 |
|---|---|---|---|
| `raw-capture-review-2026-09-09-adversarial-verifier-01`；`raw-capture-impl-audit-20260909-a1-01` | 两份报告指出同一缺陷：失败或被丢弃的 upstream attempt 写入 `complete=false` 时，旧实现把整次后来完整成功的 request 错报为 `upstream_incomplete` | 合并为一次语义修复。Task 1 让 `upstream_attempt_end(complete=false)` 只描述 attempt，不再调用 request-level `_note_incomplete`；Task 3 保持 count cleanup failure 的真实 partial boundary。失败 attempt 的边界仍保存，完整 wire evidence 的成功 retry 不再发 completion warning | **closed，adopted and fixed。** `test_failed_attempt_after_complete_response_does_not_report_request_incomplete`、`test_rule_selected_count_capture_keeps_each_upstream_retry`；E1、E2。两个 duplicate F-01 共同关闭，不新增 deferred |
| `raw-capture-review-2026-09-09-adversarial-verifier-02` | store 在首个 `request.start` 就关闭时，旧谓词把从未 committed 的 response body 报成 complete | Task 1 以 committed response-body event、missing event、incomplete state 和 request completion 计算 `response_body_capture_complete` | **closed，adopted and fixed。** `test_store_closed_before_request_start_reports_missing_response_body`；E1 |
| `raw-capture-review-2026-09-09-adversarial-verifier-03` | rule store 为 `None` 时管理接口让 `RuntimeError` 穿透为框架默认错误页 | Task 4 为 GET/POST/DELETE 统一返回 HTTP 503 与固定 `proxy_internal_error` JSON；已配置 store 的 CRUD contract 不变 | **closed，adopted and fixed。** `test_capture_rule_management_reports_unconfigured_store`；E3 |
| `coordinator-2026-09-09-safe-failure-fallback` | 未知异常的 ordinary completion fallback 曾返回 `str(error)`，可能复制异常消息；已识别 upstream 的固定 status projection 仍应保留 | Task 4 的 `_safe_failure_detail` 只返回 `module.qualname`，不读取 message、repr 或异常链文本；upstream status branches 未改变 | **closed，adopted and fixed。** `test_a_request_that_raised_on_its_way_out_still_writes_its_one_line`、`test_an_upstream_refusal_is_described_by_the_same_error_info_on_the_line_and_wire`；E2 |
| `raw-capture-impl-audit-20260909-a1-02`；`task-2-independent-review-01` | timeout/error fallback 用 `sent=b""` 同时表示 observed-empty 和 absent，可能漏掉真实已发送的空 request body，或错误伪造未知 body | Task 2 在 error carrier 和 normalizer 中加入 `sent_observed` 语义；fallback 只在 evidence 已被观察时写入 body，observed-empty 优先于 later non-empty fallback | **closed，adopted and fixed。** `test_error_fallback_distinguishes_observed_empty_body_from_absent_evidence`、`test_provider_error_normalizers_distinguish_observed_empty_request_from_absence`、`test_response_error_normalizer_keeps_observed_empty_request_before_fallback`、`test_normalized_request_evidence_distinguishes_observed_empty_body_from_absence`；E1、E2 |
| `task-2-independent-review-02` | timeout black-box control 的 ingress bytes 与 final transport bytes 相同，不能排除错误地捕获代理重编码 body | Task 2 将 control 改为 Anthropic ingress 到 Responses target 的字节不同路径，并同时断言 ingress 不等于 transport、capture 等于 transport | **closed，quality finding fixed。** `test_header_timeout_keeps_transport_boundary_raw_capture`；E2 |
| `task-2-independent-review-03` | 三个 non-GHC direct client、GHC hook idempotence 及 token/catalog exclusion 缺少 active-scope regression control | Task 2 增加真实 OpenAI-compatible、Xingchen、CodeBuddy transport controls，以及同一 GHC HTTP client 的重复 hook、token、catalog、inference control | **closed，quality finding fixed。** `test_non_ghc_direct_clients_observe_active_capture_at_transport_boundary`、`test_capture_hook_is_idempotent_and_excludes_token_and_catalog_traffic`；E1 |
| `raw-capture-impl-audit-20260909-a1-03` | buffered count response 在 `aclose()` 失败前就写出 complete response boundary，cleanup failure 被错误地投影为完整 attempt | Task 3 将 response/attempt end 移入 cleanup `finally`，二者使用同一 cleanup result；primary error precedence 保持 | **closed，adopted and fixed。** `test_rule_selected_count_capture_marks_cleanup_failure_incomplete`、`test_rule_selected_count_capture_keeps_each_upstream_retry`；E2 |
| `raw-capture-impl-audit-20260909-a1-04`；merged-state `M-2` / `S-1` | 准备阶段 quota、queue-full、capture-error warning 使用整个 path/exception 对象格式化，安全投影边界弱于 writer warning | Task 1 统一改为 request ID、固定 event、固定 reason、exception type 与 errno；相关 test controls 同时排除 path、identity、body marker 和异常原文 | **closed，adopted and fixed。** `test_queue_full_preparation_warning_is_safe`、`test_capture_error_preparation_warning_is_safe`、`test_quota_drop_is_reported_safely_at_request_completion`；E1 |
| `raw-capture-impl-audit-20260909-a1-05` `[CRUD subclaim]`（原 finding 05 的“没有 HTTP CRUD 测试”部分） | 该 claim 不成立；真实 HTTP CRUD regression 已存在，初始审查者因只读了文件前段而漏看 | 不采纳该 claim，也不把它写入 deferred。当前 test 直接经过 configured-store route，覆盖 create、idempotent create、list、422、delete 204 和 missing-id 404 | **refuted，不是 open finding。** `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:351-406`，`test_raw_capture_is_selective_and_rule_api_is_persistent`；E2 |
| `raw-capture-impl-audit-20260909-a1-05` `[absent-store subclaim]`（原 finding 05 的 absent-store error 部分） | rule store 未装配时需要稳定、可机读的 management error | Task 4 三路 handler 共用 HTTP 503 JSON envelope；不改变配置 store 的 CRUD 状态码 | **closed，adopted and fixed。** `test_capture_rule_management_reports_unconfigured_store`；E3 |
| `task-4-review-v23:T4-REV-01` | configured-store route 的 DELETE missing-id 分支缺少 route-level negative control | Task 4 fix round 在同一真实 route 先断言 204，再对同一 id 再 DELETE，断言 404 和完整 `invalid_request_error` body | **closed，quality finding fixed。** `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:396-406`；E2 |
| `task-4-review-v23:T4-REV-02` | unknown exception 的 exception-chain text 缺少真实 ASGI negative control | Task 4 fix round 让真实 `response_payload` 抛出 `RuntimeError("outer-secret") from ValueError("chain-secret")`，断言 qualified type 存在且两段 message/type 不在 ordinary line | **closed，quality finding fixed。** `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:3480-3513`，`test_a_request_that_raised_on_its_way_out_still_writes_its_one_line`；E2 |
| `task-1-review:T1-Q-01` | Task 1 初轮实现已有正确行为，但 completeness 两个反向分支和 queue-full/capture-error warning 的测试分辨力不足 | Task 1 fix round 只补回归 controls，不改变 production semantics；四个 controls 均直接注入相应 failure/drop | **closed，quality finding fixed。** `test_store_closed_before_request_start_reports_missing_response_body`、`test_committed_response_body_survives_late_store_closed_request_end`、`test_queue_full_preparation_warning_is_safe`、`test_capture_error_preparation_warning_is_safe`；E1 |
| merged-state `M-1` | 旧 v21 report 认为实现 reason 集合宽于规格 | v22 修订已把 `store_closed`、`writer_queue_full`、`capture_error`、`upstream_incomplete` 补进封闭枚举；v23 继续以该集合为唯一 authority。不是当前实现应迁就旧 report 的问题 | **closed by living spec revision。** 当前 authority 为 `spec.md` §6；E1、E2 的 warning controls 只使用该集合 |
| `RC-FINAL-01` | FailureSummary、InterruptionObservation、secondary cleanup、exception note projection 与 local stream ending 会复制 unknown exception message、repr、chain text 或 note | Task 6 提取共享 `safe_exception_detail()`，只保留 fixed upstream status 或 `module.qualname`；note 只保留 stable presence marker；secondary detail 与 emit/freeze fallback 不再格式化 exception text；client wire error 和已识别 upstream status projection 不变 | **closed，adopted and fixed。** 真实 dispatch ASGI outer/chain control、disconnect cleanup message/note control、actual ASGI local stream failure control、interruption structured-record control 与 `test_an_upstream_refusal_is_described_by_the_same_error_info_on_the_line_and_wire`；Task 6 fix report；source-level final re-review：`reports/raw-capture-final-rereview-2026-09-09.md` |
| `RC-FINAL-02` | hashed-path tests 没有判定 SHA-256 24-character prefixes、missing-agent namespace、suffix 或 raw identity 缺席 | Task 6 的 path controls 精确比较 session/agent digest paths、`agent-missing-<sha256("missing-agent-id")[:24]>` 与 `.cborseq.zst`，并否定完整 raw identity | **closed，adopted and fixed。** `test_capture_path_uses_exact_hash_prefixes_without_raw_identity_values`、`test_missing_agent_id_has_its_own_exact_hashed_capture_group`；Task 6 fix report；source-level final re-review：`reports/raw-capture-final-rereview-2026-09-09.md` |
| `RC-FINAL-03` | cross-store first append 没有覆盖 valid zstd frame 中 scalar CBOR item 或 two CBOR maps 的 poison | Task 6 用 production RawCaptureStore first append 构造两类 frame，断言 file bytes/reservation 不变、completion reason=`path_poisoned`，且 ordinary raw-capture diagnostics 不含 fixture payload | **closed，adopted and fixed。** `test_new_store_first_append_rejects_valid_zstd_with_invalid_cbor_items`；Task 6 fix report；source-level final re-review：`reports/raw-capture-final-rereview-2026-09-09.md` |
| `RC-FINAL-04` | Task 6 progress ledger 曾同时宣称 `in-progress` 与 final verification `not started`，且 final package 的 progress hash 是旧 snapshot | Task 6 将 Task 6 收敛为唯一 `in-progress` 状态，并将 post-fix source/test/ledger hashes 写入 fix report；final-review package 明确保留为 pre-fix review input，不伪装成 post-fix package | **closed，adopted and fixed。** `progress.md`、`final-fix-review-package.md`、`task-6-fix-report.md` 与 current binding report `final-rereview-final.md` |  

## 未采纳、deferred 与范围边界

本轮没有新的未采纳行为要求。实现 finding 05 的 HTTP CRUD 子 claim 已 refute，不能转写成 deferred；其 absent-store 子 claim 已采纳并关闭。Task 3 scoped review 没有 finding；Task 1、Task 2、Task 4 的初轮质量 finding 均有 fix-round closed verdict。Task 6 的 RC-FINAL-01 至 RC-FINAL-04 已由 durable source-level review、current binding review 和 final current binding artifact 关闭；不新增 deferred。真实 Copilot upstream、部署级 canary、全量 pytest、全量 coverage 不在本账的证据范围内，因此本账不使用“全量通过”或等价表述。 final source-level evidence is `reports/raw-capture-final-rereview-2026-09-09.md`; RC-FINAL-04 current binding is `final-rereview-final.md`.

原有 deferred ledger 中真正仍未采纳的事项保持独立生命周期；本轮不因已关闭 finding 新增条目。准备阶段 warning 的旧 D-1 claim 已由 Task 1 的安全 warning fix 取代，其当前处置以本账为准，不得再把旧 report 的 point-in-time 描述当作当前实现事实。

## 证据索引

### E1：raw-capture 与 provider focused tests

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/pipeline/test_timeout_enforcement.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/ghc_client/test_client.py tests/unit/model_provider/openai_compatible/test_provider.py tests/unit/model_provider/xingchen/test_client.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_codebuddy.py --no-cov -q
```

2026-09-09 fresh output：`139 passed in 10.00s`。

### E2：pipeline raw-capture、retry、timeout、cleanup、safe fallback 与 CRUD tests

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/int/test_pipeline_app.py -k 'raw_capture_is_selective_and_rule_api_is_persistent or rule_selected_count_capture_keeps_each_upstream_retry or rule_selected_count_capture_marks_cleanup_failure_incomplete or rule_selected_rejection_capture_keeps_upstream_wire_evidence or header_timeout_keeps_transport_boundary_raw_capture or an_unmatched_refusal_does_not_write_a_legacy_capture or a_request_that_raised_on_its_way_out_still_writes_its_one_line or an_upstream_refusal_is_described_by_the_same_error_info_on_the_line_and_wire' --no-cov -q --log-cli-level=WARNING
```

2026-09-09 fresh output：8 passed、272 deselected、1 条既有 Starlette deprecation warning。cleanup failure control 的 warning 是预期的 `reason=upstream_incomplete`，不是测试失败。

### E3：unconfigured management route tests

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/int/test_pipeline_ops_routes.py --no-cov -q
```

2026-09-09 fresh output：45 passed、1 条既有 Starlette deprecation warning。

### E4：Task 1–4 scoped Ruff

```text
cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/observability/raw_capture.py src/app/pipeline/direct_driver/base.py src/app/pipeline/driver.py src/app/pipeline/exceptions.py src/app/model_provider/upstream_errors.py src/app/model_provider/ghc_client/client.py src/app/model_provider/openai_compatible/client.py src/app/model_provider/openai_compatible/errors.py src/app/model_provider/xingchen/client.py src/app/model_provider/codebuddy_client/client.py src/app/model_provider/codebuddy_client/errors.py src/app/server/routes/inference.py src/app/server/routes/ops.py tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/pipeline/test_timeout_enforcement.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/component/model_provider/ghc_client/test_client.py tests/unit/model_provider/openai_compatible/test_provider.py tests/unit/model_provider/xingchen/test_client.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_codebuddy.py tests/int/test_pipeline_app.py tests/int/test_pipeline_ops_routes.py
```

2026-09-09 fresh output：`All checks passed!`。

### E5：Task 1–4 scoped Pyright

完整目标集合命令的唯一诊断是 `tests/unit/observability/test_raw_capture.py:586` 对既有 `store._queue` 的 `reportPrivateUsage`；退出码为 1。排除该既有 test-only diagnostic、保留全部 production files 和其他目标测试后重新运行同一 `uv run pyright` target set，输出为 `0 errors, 0 warnings, 0 informations`。因此本账不写“Pyright 全部通过”，也不把该既有测试访问误记为 Task 1–4 production finding。

### E6：移除全局 quota 的 compat probe 与 config controls

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/config/test_config_schema.py::test_raw_capture_uses_rule_selection_and_has_a_bounded_compression_level tests/unit/config/test_config_loader.py::test_compat_migration_warns_and_preserves_explicit_new_keys --no-cov -q
```

2026-09-09 fresh output：2 passed。

```text
cd /home/xp/src/ghc-api-proxy-py && uv run python -c 'from app.config.compat import migrate_compat; raw={"observability":{"raw_capture":{"directory":"./captures","rules_database":"./rules.sqlite3","max_total_bytes":123}}}; section=migrate_compat(raw)["observability"]["raw_capture"]; assert "max_total_bytes" not in section; print("compat raw-capture max_total_bytes dropped:", section)'
```

2026-09-09 fresh output：发出 `DeprecationWarning`，并打印不含 `max_total_bytes` 的 raw-capture section。

### E7：文档自审

已对 live raw-capture 文档、raw-capture plan 和本轮工作报告执行关键词搜索，并逐个阅读命中上下文。live 文档没有未决占位、旧版权威状态或无可重跑命令支撑的全量通过声明；现存的 `complete=false` 文字都属于 v23 的 attempt boundary、partial boundary、cleanup-failure 或测试断言。报告 originals 中保留的旧 v22 header 是 point-in-time 记录，不是当前 authority，也没有被改写。

## 结论

Task 1–6 的实现与 scoped review 发现已按 ACTIVE v23 逐项对账；Task 6 的 RC-FINAL-01 至 RC-FINAL-04 已由 durable source-level re-review、current binding review 和 final current binding artifact 关闭。duplicate F-01 只关闭一次并由 inference 与 count 两条路径共同复核。没有发现 v23 与已验证用户目标冲突的条款，因此不修改 `spec.md`。本账的“closed”只表示 scoped disposition 已收口，不表示全量测试、真实 upstream 或部署级验收已经完成；Git integration 仍按收尾报告保持 pending/keep。
