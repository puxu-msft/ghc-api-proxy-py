# Capture Matrix 与 History/Replay 接缝合并态最终评审

## 评审范围

本次为只读、基于当前工作树最终状态的独立复评。审查对象限定为 `src/app/observability/raw_capture.py`、`capture_observation.py`、`request_completion.py`/`request_trace.py` 的直接投影，`src/app/history/entry.py`/`writer.py`，`src/app/replay/process.py`，以及用户点名的 Raw Capture、full-header、request-completion、History entry/writer 与 Replay unit tests。判据先于实现读取：Raw Capture ACTIVE v28 §4.1/§5/§6、History ACTIVE v4 §2/§4、Replay ACTIVE v4 §2.2，以及 Observability ACTIVE v2 §4.4/§5。

明确不在范围内：未直接构成上述事实交接的 provider/pipeline 生产路径、History transport authorization、部署与 Replay deferred items，以及工作树中其他在飞改动。`request_trace.py` 当前差量为 reasoning-effort 表示，未改变 capture direct projection，故只在接缝边界确认后排除。

## 总体 verdict

**Pass。** 未发现 blocker、major、minor 或 nit。RCR04-001（invalid header 被伪造成空 mapping 并放行 wire diagnostic）在当前状态确已关闭。

**Blocker 数：0。**

## 已闭合证据：header 与 writer acknowledgement

此前 RCR04-001 的 malformed-header 假阳性以当前代码重新核对为已修复：`_capture_headers()` 对有效空 mapping/pair iterable 返回空 mapping；对 `None`、字符串/bytes、坏 pair 和迭代/转换失败返回 `None`。`upstream_request_start()` 与 `upstream_response_start()` 只在结果非 `None` 时放入 raw event；`_capture_event_evidence()` 以相同验证规则生成非敏感 `headers_available` fact。

RawCapture attempt matrix 仅在 `note_writer_frame_completed(..., drop_reason=None)` 中由 worker acknowledgement 更新；队列接收不是事实源，`finish()` 先加入 `request.end`、等待本 request 所有 pending writer receipts，再冻结 `RawCaptureObservation`。`RequestCompletionCoordinator.publish()` 也在生成 `RequestFacts`/History handoff 之前调用该 `finish()`。因此有效空 header 与 invalid/absent header 的区分，以及“writer ack 而非 enqueue”为矩阵 authority，已有源码与 committed-writer regression 的闭合证据；完整最终结论待执行验证与其余接缝复核后追加。

## 最终交叉核对

| 承重要求 | 结论 | 证据 |
|---|---|---|
| Writer acknowledgement 是 capability matrix 的唯一事实源 | 通过 | 每个 queued frame 携带仅含 event type、attempt、header-presence 与 complete 的 `_CaptureEventEvidence`；worker 成功完成才更新 attempt state，drop/short write/poison 则走稳定 incomplete path。`finish()` 等待所有 receipt，`publish()` 在构建 immutable `RequestFacts` 前调用它。 |
| empty header 与 invalid/absent header 必须不同，且 invalid fail-closed | 通过 | 有效空 mapping/pair iterable 持久化为空 mapping 并在 writer ack 后成为 evidence；malformed/不可迭代输入省略 `headers` 字段，`headers_available=false`。metadata-only probe 输出 request header `true`、invalid response header `false`、wire eligibility `false`，并只看到有效 request start 带 header metadata。 |
| partial、zero-body、cleanup 与 returned/direct-discard 边界不能补造完整 wire | 通过 | 零长度 body 仍作为 committed body event；partial response 以 `response.end(complete=false)` 使该 attempt 失去 wire capability。direct-driver 对未 handoff response 先保留真实 request/response evidence；未消费 response 写不完整 end，再在 finally cleanup。失败 attempt 经 canonical failure carrier 写入真实已观察 body；pre-pull pending scope 在 provider send 前安装，active transport observer 只在实际 send boundary 记录。 |
| History 只承接 safe immutable matrix/reference，不用 timing 或 trace 猜测 | 通过 | `HistoryEntry.from_request_facts()` 直接投影 `RawCaptureObservation`；`CaptureAttemptCapabilities.__post_init__` 重算 wire bit；SQLite writer 仅持久化 scalars、attempt matrix JSON 与 capture reference。普通 capture projection 的精确字段集不包含 raw headers、bodies 或 credentials。 |
| selected-attempt Replay gate 必须先消费 source History receipt，并对 legacy fail-closed | 通过 | `ReplayProcess` 在 reader 前解析受控 receipt；`CaptureCapabilities.replay_rejection_code()` 同时要求 selected `attempt_id`、top-level wire bit 和该 attempt 的完整 matrix。source reread 只确认 selected attempt 存在，不从 event/timing 重新推导 completeness。legacy-schema metadata-only probe 经 migration 得到零 attempt matrix，wire 与 semantic 都是 `source_capability_denied`。 |
| semantic/live 与 wire gate 分离 | 通过 | incomplete capture 的完整 client request 仍可 semantic/live，而 wire 只由完整 selected attempt 决定。metadata-only partial-attempt probe 得到 `status=incomplete`、attempt gates `[true,false]`、semantic/live `true`、request-level wire `true`（仅对 attempt 0）；attempt 1 不可被自动替代或放行。 |
| Default History/Replay result 不泄漏 transport evidence | 通过 | History safe projection test 断言 capture schema 的精确安全字段；Replay diagnostic summary 只保留 event、attempt、status、complete 与 body byte count，result sanitization regression 覆盖 nested direct construction 与 opaque executor fields。 |

## 验证

- `uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_full_header_capture.py tests/unit/observability/test_request_completion.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py tests/unit/replay/test_process.py --no-cov -q`：**144 passed**。另有 Replay source-read multiprocessing 的 13 条 Python 3.14 `fork()` deprecation warning；不属于本 capture matrix/History/Replay gate 的失败。
- `uv run ruff check src tests`：**passed**。
- `uv run pyright src tests`：**0 errors, 0 warnings, 0 informations**。
- metadata-only probes：① valid-empty vs invalid header + zero-byte body；② complete attempt 加 partial attempt；③ pre-capability History SQLite schema 经当前 migration。探针仅输出 boolean、计数、event type 与 rejection code，不输出 body、header value、credential、session/agent identity 或原始 capture 内容。
- 绿灯分辨力：focused tests 与独立 probes 同时使用反例（malformed header、partial boundary、ungranted/unknown attempt、legacy absent matrix）；它们分别断言 false/`source_capability_denied`，而非只覆盖 happy path。

## RCR04-001 disposition

**closed。** 当前 `_capture_headers()` 与 `_capture_event_evidence()` 使用同一“valid container 才有 header evidence”的边界。committed-writer regression 覆盖 request-side 与 response-side malformed inputs；额外 metadata-only probe 复现 valid empty request headers + invalid response headers，结果为 response header absence 和 wire gate denial。未发现从 History serialization、SQLite decoding 或 selected-attempt Replay gate 重新把该 invalid input 解释为完整 header evidence 的路径。

## 搜索面与限制

判据：Raw Capture ACTIVE v28、History ACTIVE v4、Replay ACTIVE v4、Observability ACTIVE v2，以及 RCR04-001 前次报告/修复记录。实现：用户列出的七个 production modules；为验证 direct-discard、failure/cleanup 与 pre-pull seams，还读取 `pipeline/direct_driver/base.py`、`pipeline/driver.py` 和 inference response completion 的直接调用片段。测试：用户点名的全部 unit suites及其 scoped diff。

基线是 `main` 当前工作树（最近提交 `8d5547f1`）加其未提交的 scoped changes，而非一个单独不可变 merge commit；本 review 除本报告外未修改被审源码或测试。未审 provider/pipeline 的更广泛端到端行为、History transport authorization、deployment/RBAC 与 deferred feature；这些排除项不影响已核对的 matrix authority、safe projection、legacy fallback 或 selected-attempt gate。

## Findings

未发现问题。
