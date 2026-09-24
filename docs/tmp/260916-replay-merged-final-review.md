# Replay/history capability merged-state review

日期：2026-09-16  
评审类型：只读、独立最终状态评审  
状态：完成

## 评审范围

检查当前工作树中 replay/history capability 的最终接缝：`src/app/replay/process.py`、`src/app/history/entry.py` 与 `writer.py` 的 direct projection、RawCapture observation direct facts、`tests/unit/replay/`、`tests/unit/history/`，以及其直接相关的 Replay、History、Raw Capture ACTIVE specs。重点核对 source authority、有限/慢 source 的 deadline、`none`/`incomplete`/`corrupt` 语义、per-attempt matrix 的事实来源、wire headers/body/end gate、`ReplayResult.as_dict()` 的安全摘要和 semantic/live output 的 raw-field 隔离。

不把先前报告（包括 RCR-01/02/03/04 与 REPLAY-CAP-FINAL-01）作为事实来源；不审主程序 replay API（规格明确当前不存在）、未列范围的 provider 业务正确性、或旧报告的处置状态。工作树在评审开始时已有未提交改动；本报告针对当时可见的当前状态。

## 判据来源

- `.dev/docs/replay/spec.md`（ACTIVE v3；其修订记录含 2026-09-16 v4 的 matrix 约束）
- `.dev/docs/history/spec.md`（ACTIVE v2；其修订记录含 2026-09-16 v4 的 direct immutable-matrix 约束）
- `.dev/docs/raw-capture/spec.md`（ACTIVE v28）

## 总体 verdict

**needs-fix。** 未发现 blocker；发现 2 个 major，均在 replay process/CLI 的 source deadline 与受控 source composition 接缝。RawCapture writer-confirmed direct facts、History direct projection、状态语义、selected-attempt wire gate 与默认结果的 raw-field isolation 在本次范围内没有发现额外问题。

## Blocker 数

0

## Findings

### `replay-deadline-post-read-matrix-scan` — major

**Severity：** major  
**Primary location：** `src/app/replay/process.py:388-429`  
**Related locations：** `src/app/replay/process.py:431-469`、`src/app/replay/process.py:516-543`、`tests/unit/replay/test_process.py:test_replay_enforces_deadline_during_source_read`

**判据：** Replay spec §4 要求 deadline 在 source read 前建立，offline local read、decode 与 summary 都必须在预算内逐步检查；超时后必须停止继续处理。  
**事实与影响：** `_read_source()` 在 reader 已返回后，会无 deadline check 地遍历全部 records 一次，再对每个不同 attempt 完整重扫 records 构造 `upstream_attempts`。因此有限但 attempt 数很多的 source 能在已经越过 deadline 后仍持续 CPU 处理；wire diagnostic 直到随后开始 summary 才报告 `deadline_exceeded`。无落盘 probe 以 3,500 个 attempt-start records、`deadline_s=0.001` 运行，最终得到 `code=deadline_exceeded`，但总耗时 `0.885s`，约为预算的 885 倍。此路径违背同步 deadline 的停止语义，并可让本地恶意或异常大的 capture 消耗超过调用方授权的 CPU 时间。  
**修复方向：** 在 `_read_source()` 的每个可能随输入规模增长的循环、body aggregation 与 attempt grouping 中传递并检查 `deadline_at`；同时避免每个 attempt 对全 records 重扫（单遍按 attempt 累积），使检查频率与工作量保持有界。加入覆盖“有限但大量不同 attempt 的 reader 结果”的 deadline 回归测试，而不只覆盖 reader 自身 sleep。  
**证据强度：** 已由当前代码路径、focused unit suite 及独立无落盘 probe 复现；现有 `test_replay_enforces_deadline_during_source_read` 只模拟 reader 在返回前 sleep，不能覆盖 reader 返回后这段未计时的组装工作。

### `replay-cli-has-no-history-source-authority` — major

**Severity：** major  
**Primary location：** `src/app/replay/__main__.py:25-47`  
**Related locations：** `src/app/replay/process.py:82,163-169,323-354`、`tests/unit/replay/test_process.py`

**判据：** Replay spec §1/§2 要求 capture source 由 controlled History boundary 的 source receipt 授权，而不是由调用方的 path/headers/credentials 决定；`status.md` 将独立 `app.replay` CLI 列为已落地（当前仅暴露 wire diagnostic 参数）。  
**事实与影响：** CLI 只将调用方的 `--capture`、`--entry` 组装为 `ReplayRequest`，然后以未配置的 `ReplayProcess(max_deadline_s=...)` 执行。全仓没有为 `_DEFAULT_SOURCE_AUTHORITY` 设置生产实现，也没有在 CLI 注入 `source_authority`。因此任意 CLI 调用都会在触碰 capture 前得到 `source_authority_unavailable`，wire diagnostic 无法运行。反过来，若为了让该 CLI “工作”而把其 `--capture` 当作 receipt/path 直接信任，将恰好绕过规格要求的不可伪造 source authority。独立 CLI probe 使用不存在的无敏感路径也稳定返回该 error；另一个无落盘 probe 确认注入 authority 时 process 实际读取 authority 提供的 path，而不是 caller path，说明问题是 CLI 没有接上该安全 seam，不是 process 应当退回 caller path。  
**修复方向：** 为 CLI 提供可配置但受控的 History-backed source-authority adapter：它应按 source entry/capture reference 从 History index 解析 capability 与 capture path，并拒绝不匹配、缺失或已下线的 source；或在 capability 尚未对 CLI 交付前移除/明确禁用该表面。不要以 caller `--capture` 代替 authority。为 CLI 层增加一条成功路径和一条 forged path/ref 拒绝路径的集成测试。  
**证据强度：** 静态全仓引用检索、CLI 实际执行和 process-level authority-path probe 均一致；现有 replay unit tests 通过 autouse monkeypatch 安装测试 authority，未覆盖 production CLI composition。

## 已核对且未发现额外问题

- **Process source authority（非 CLI composition）：** `ReplayProcess.run()` 先解析 authority receipt，再读取 receipt 的 path，并在读取前核验 entry ID 与 capture ref；未配置 authority、receipt 不匹配、无 capture 和 capability denial 都保持 not-started。无落盘 probe 验证 caller path 与 authority path 不同的时候，实际 reader 只收到 authority path。
- **`none` / `incomplete` / `corrupt`：** `CaptureCapabilities.replay_rejection_code()` 对 `none` 和 `corrupt` fail closed；`incomplete` 只要完整 client request 与对应 semantic/live flag 均成立，仍允许 semantic/live，wire 继续要求 selected attempt 的完整 matrix。对应 replay/history unit tests 已覆盖。
- **RawCapture → History 的 direct facts：** RawCapture 只在 writer acknowledgement 成功后记录 attempt-local body/header/boundary facts；`HistoryEntry.from_request_facts()` 直接复制 immutable observation；writer round-trip 对 matrix 做 JSON 存取，decoder 对缺失/非 `True` attempt facts fail closed，`CaptureAttemptCapabilities.__post_init__()` 重新从完整矩阵导出 wire eligibility。未发现从 response timing、`UpstreamBodyAttempt` 或零散 response event 补推完整性的代码路径。
- **Wire headers/body/end gate：** selected attempt 必须同时有 global 与 attempt-local eligibility；attempt-local eligibility 需要 attempt/request/response start、headers/body、response end complete、attempt end complete。invalid header containers 的已提交 frame 不被当作 header evidence，测试已覆盖。
- **Safe default result projection：** `ReplayResult.as_dict()` 二次投影 client actions、semantic/live output 与 diagnostic records；default output 只保留 allowed outcome，actions 只保留 type/name，diagnostic 只保留 event/attempt/status/complete/body byte count。现有测试还直接构造带 nested raw-like fields 的 `ReplayResult`，确认它们不会序列化。

## 验证与搜索面

- 运行：`uv run pytest tests/unit/replay tests/unit/history tests/unit/observability/test_raw_capture.py` → **100 passed**。
- 运行：`uv run ruff check`（仅上述 replay/history/raw-capture 实现与 unit-test 范围）→ **All checks passed**。
- 运行：`uv run pyright`（同一范围）→ **0 errors, 0 warnings, 0 informations**。
- 无落盘 probes：authority path control 通过；CLI source-authority gate 稳定拒绝；有限 source 的 post-read matrix scan 超时问题复现。
- 读取并对照：Replay/History/Raw Capture ACTIVE specs、Replay status/deferred、范围内 implementation/test seams，及 `request_completion` 的 observation handoff。未将历史 review 报告作为事实来源。
- 未覆盖：未审未列入范围的 provider-specific live execution、主程序 API（当前 spec 明确没有 replay API）、History archive/route 的完整功能正确性、或对修复后状态的回归复审。
