# Raw capture 全面更新复审

日期：2026-09-16

## 评审范围

本轮按 `.dev/docs/raw-capture/spec.md` ACTIVE v28 复核当前 committed HEAD
`541a738b` 的 raw capture 及其直接承重接缝：

- `src/app/observability/raw_capture.py`
- `src/app/observability/capture_observation.py`
- `src/app/observability/request_completion.py`
- `src/app/pipeline/direct_driver/base.py`
- `src/app/server/routes/inference.py`
- `src/app/history/entry.py`
- `src/app/history/writer.py`
- `src/app/history/archive.py`
- `src/app/server/routes/history.py`
- `src/app/replay/process.py`
- 对应 raw capture、History、Replay focused tests 与当前 topic docs

明确不在范围：工作树中与 raw capture 无关的 provider、pipeline、tokenization
和 systemd WIP；History restart/tail hardening、Replay CLI/result persistence 等
`status.md`/`deferred.md` 已明确接受的后续切片。

## 总体 verdict

**NEEDS-FIX。blocker=0，major=1，minor=2。**

核心 CBOR/zstd 写入、规则选择、full-header capture、writer acknowledgement、
per-attempt evidence、History safe projection 与 Replay deadline/result
hardening 已有实质实现，聚焦回归通过；但 replay capability 对非法状态
fail-open，且 full-header 对重复 HTTP header 不保真。topic 状态文档也已落后
于 v28。

## 发现

### Major

#### RCR-20260916-01 — 非法 capture status 可绕过 Replay source gate

- **primary_location:** `src/app/history/entry.py:98-125`
- **related_locations:** `src/app/history/writer.py:953-1021`;
  `src/app/replay/process.py:358-385`
- **判据:** Raw Capture v28 §4.1 将 `capture_status` 定义为封闭集合
  `none | pending | complete | incomplete | corrupt`；Replay v4 §2 要求
  source capability fail closed，只有受 capability 允许的 source 才能执行。
- **证据:** `CaptureCapabilities.replay_rejection_code()` 只特别拒绝
  `"corrupt"` 和 `"none"`，对任意未知字符串继续按 semantic/live 的布尔
  capability 判断。`HistoryWriter._index_entry_from_row()` 只检查
  `capture_status` 是 `str`，随后直接构造 `CaptureCapabilities`，没有验证
  它属于规格闭集。最小实际探针用
  `status="unexpected-status"`、`client_request_available=True`、
  `semantic_replay_eligible=True` 构造 source receipt；直接 gate 返回
  `None`，实际 `ReplayProcess.run()` 进一步读 capture 并执行注入的 semantic
  executor，结果为 `outcome=completed`。另用一条与 SQLite
  `history_entries` 投影形状一致的 row 调用当前 `_index_entry_from_row()`：
  `stored_status` 仍为 `unexpected-status`，semantic gate 仍返回 `None`。
- **影响:** History index 损坏/迁移异常或错误的 source authority projection
  会把未定义状态当成可 replay，而不是稳定拒绝。Replay source gate 的
  “未知即拒绝”安全边界没有成立。
- **建议修复:** 在 `CaptureCapabilities`/History row projection 入口把状态
  解析为严格 enum；未知值统一映射为稳定的
  `source_capability_denied`（或 `source_evidence_unavailable`），并增加
  实际 History-row + Replay path 的回归测试。相同入口应严格验证顶层
  capability 列为 `0/1`，不要对任意整数直接 `bool()`。

### Minor

#### RCR-20260916-02 — full-header capture 折叠重复 header 字段

- **primary_location:** `src/app/observability/raw_capture.py:41-70`
- **related_locations:** `src/app/observability/raw_capture.py:235-245`,
  `:676-707`, `:734-746`
- **判据:** Raw Capture v28 §4 要保存 inbound/client request、每个 upstream
  attempt 和 client response 的完整 headers；full transport evidence 不应
  丢失合法 HTTP 字段。
- **证据:** `_capture_headers()` 将所有 header 对归一化到
  `dict[str, str]`，同名字段后写覆盖前写。实际探针分别传入
  `httpx2.Headers([(b"set-cookie", b"a=1"), (b"set-cookie", b"b=2")])`
  和原始 pair list，落盘结果分别为合并字符串 `"a=1, b=2"` 与只剩最后值
  `"b=2"`。因此 `Set-Cookie` 等不可安全合并的重复字段无法从 capture
  恢复原始字段序列。
- **影响:** 规则命中请求的 capture 仍能保存大多数普通 headers，但不再是
  重复 header 场景下的 full-header/wire evidence；wire diagnostic 读取到的
  transport 与实际传输不等价。
- **建议修复:** 采用保序的 pair-list header representation（或明确的
  `name -> tuple[value, ...]` schema），让 Mapping/原始 pair 两条入口都
  保留重复值，并为 schema/version 与 Replay/History safe projection 增加
  回归覆盖。

#### RCR-20260916-03 — raw-capture topic 状态与 ACTIVE v28 不同步

- **primary_location:** `.dev/docs/raw-capture/status.md:3-20`
- **related_locations:** `.dev/docs/raw-capture/deferred.md:3,15,23`;
  `.dev/docs/raw-capture/review-disposition.md:3-6,28`
- **判据:** Spec 是当前权威；状态页和处置表必须让接手者得到与当前实现/
  Spec 一致的能力边界，不能把已落地能力继续写成 deferred。
- **证据:** `spec.md` 已是 ACTIVE v28，并在 v28 修订中关闭
  writer-ack per-attempt matrix 的 timing/attempt 推断偏差；RCR-04 final
  review 也记录该项 pass。可是 `status.md` 仍是“v25 ... per-attempt
  durable capability deferred”，`deferred.md` 页首仍以 v27 为依据并把
  full-header/capability/replay 作为 v27 背景，`review-disposition.md`
  仍把 per-attempt capability 标为 accepted-deferred、当前 Spec 写成
  v25。
- **影响:** 接手者可能按过期文档重复实现已经完成的 matrix，或错误地把 v28
  的 writer-ack/fail-closed 合同当作未完成能力；这是文档 authority pointer
  漂移，不是运行时 raw body 泄漏。
- **建议修复:** 更新 status/deferred/review-disposition 的 current pointer
  到 v28，关闭已完成的 per-attempt matrix 条目；保留真正仍 deferred 的
  cleanup boundary、HTTP oracle、warning hardening 等条目。

## 已核对且未发现偏差的承重面

- SQLite rule-selected capture 与路由后、首次 upstream attempt 前的 body
  补录；
- CBOR Sequence + 独立 zstd frame、session/agent hash 路径、legacy 文件
  隔离、per-file/total admission reservation；
- queue/full-write/short-write/poison/跨 store 校验与 writer acknowledgement；
- full-header capture 的 credentials-sensitive boundary 与 History token gate；
- RawCapture observation 只从 committed frame 投影 attempt matrix；
- History entry/index 不默认暴露 transport body/header/credential；
- Replay source authority、显式 selector、隔离 source read deadline、默认
  result safe projection；
- `none`/`corrupt` 拒绝、`incomplete` 的 semantic/live 与 wire capability
  分离，以及 selected attempt 的 matrix gate。

## 验证

- `uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/history/test_archive.py tests/unit/history/test_history_entry.py tests/unit/history/test_history_routes.py tests/unit/history/test_writer.py tests/unit/replay/test_process.py tests/unit/replay/test_cli.py --no-cov -q`
  —— **157 passed, 13 warnings**。警告是 Python 3.14 `fork()` deprecation，
  无失败。
- 相关 production/test 文件 `uv run ruff check` —— **All checks passed**。
- 相关 production 文件 `uv run pyright` —— **0 errors, 0 warnings,
  0 informations**。
- 实际探针：
  - 非法 `capture_status` 通过 gate 并执行 semantic executor；
  - 重复 `set-cookie` header 在落盘 capture 中被合并/覆盖；
  - 4 MiB、8 MiB、16 MiB History zstd frame 读取完成，未将该已知
    restart/tail deferred 面升级为本轮 finding。

## 搜索面与限制

已读取 Raw Capture v28、History v4、Replay v4、Observability 相关契约，
当前 raw/history/replay 实现、直接调用接缝、focused tests，以及历史复审
处置。未执行全仓回归；工作树另有大量与本主题无关的未提交 WIP，当前结论
以本主题 targeted suite 和静态检查为证据。
