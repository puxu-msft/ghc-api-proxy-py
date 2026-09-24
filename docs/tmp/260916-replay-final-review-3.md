# Replay capability final replay review 3

日期：2026-09-16  
评审方式：最终状态、只读、独立复核  
总体 verdict：pass  
Blocker：0

## 评审范围

审查当前最终状态中的 `src/app/replay/process.py`、`src/app/replay/__init__.py`、`src/app/history/entry.py`、`src/app/history/writer.py` 的直接 History projection、`tests/unit/replay/`、`tests/unit/history/`，以及 Replay、History、Raw Capture ACTIVE specs。

明确不在范围：Replay CLI/public API composition、History archive/durability 的其余行为、RawCapture writer/reader 的独立实现和其 writer-ack 事实生产、provider pipeline，以及无关既有 WIP。本报告不输出 capture 正文、headers、credentials 或其他敏感 evidence。

## 总体结论

未发现 blocker、major、minor 或 nit。RCR-01/02/03/04 和此前 REPLAY-CAP 项在本范围的最终系统状态均可核验为 closed。

## 逐项复核

### RCR-01 — source authority / receipt

**closed（在 `ReplayProcess` 的调用方输入边界内）。** `ReplayRequest` 不再携带 capability/grant；`run()` 在任何 source read 前经 `ReplaySourceAuthority` 解析 receipt，并要求 receipt 的 entry id 与 capture ref 同 request 相等。实际用于读取的是 authority receipt 的 `capture_path`，而不是 `ReplayRequest.capture_path`。没有 authority、缺 receipt、缺 capture path/ref、entry/ref 不匹配以及 capability 拒绝均为 not-started error。

这建立的是 composition-owned authority 的信任边界，而不是对任意本地 Python 代码的密码学隔离：`source_authority` 是显式依赖注入点，必须由调用方的受控 History resolver 提供。ReplayRequest 本身不能自填 capability 或将自身 path 指向被读取 source。

### RCR-02 — offline read/decode deadline 与残留 worker

**closed。** finite positive deadline 在 authority 和 source read 前验证；source read 放到 forked daemon worker。父进程只在剩余预算内等待 Pipe；到期会 terminate 并 join worker，`finally` 也保证存活 worker 被 terminate/join，随后才返回 deadline error。受控 slow-reader probe 在 deadline 内得到 `deadline_exceeded`，并确认没有遗留活跃 child process。semantic/live JSON decode 的前后同样检查剩余 budget；executor 使用 `asyncio.wait_for`。

### RCR-03 — default `ReplayResult` safe projection

**closed。** `ReplayResult.as_dict()` 无条件重新 allowlist-project `client_actions`、`output` 与 `diagnostic_records`。action 只保留 type/name；semantic/live output 只保留合法 outcome；wire record 只保留 event、attempt、status code、completion 和 body byte count。直接构造包含 nested raw-like fields 的 public `ReplayResult` 也经同一 projection，不会把正文、headers、credentials、opaque payload 或 action arguments 放入默认 dictionary。

### RCR-04 — History 的 per-attempt matrix 与 selected-attempt wire gate

**closed（直接 projection 范围）。** `HistoryEntry._capture_capabilities()` 逐字段复制 `RawCaptureObservation.upstream_attempts` 到 immutable `CaptureAttemptCapabilities`；没有从 response timing、`UpstreamBodyAttempt` 或 reread records 推断 request/header/body/boundary facts。`CaptureAttemptCapabilities.__post_init__()` 由完整 attempt-local matrix 重算 eligibility；HistoryWriter encode/decode 仍保留每项事实，并将缺失或类型不正确的 stored value fail-closed 为 false。

wire mode 在 source read 前要求 History receipt 的 top-level 和 selected attempt eligibility；matrix 不足时拒绝且不读 source。source reread 只确认 selected attempt 有可读 records，未以 records 反推 completeness。`none` 和 `corrupt` 分别稳定拒绝；`pending`/`incomplete` 不被错误地作为 semantic/live 的单独否决条件，仍按 client-request 和 mode capability 判定。

### Default History / semantic-live projections

**closed。** `HistoryIndexEntry.as_dict()` 只发布 index metadata、capability matrix 和 references，不加载 semantic payload 或 transport bytes；`HistoryWriter.semantic_payload_for()` 是显式 cold read。`HistoryEntry` 的 archive payload 可携带 semantic fields，但不包含 raw transport。Replay 的 semantic/live execution 使用 decoded client request 与当前 target；其 public result 再次经过上述 safe projection。

## 验证执行

- `uv run pytest -q --no-header tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py`：52 passed。
- `uv run pytest -q --no-header tests/unit/replay tests/unit/history`：64 passed。
- 范围文件 `uv run ruff check ...`：passed。
- 范围文件及全仓 `uv run pyright ...` / `uv run pyright`：0 errors、0 warnings、0 informations。
- `git diff --check --`（本范围）：passed。
- 不落盘、无敏感 payload 输出的 probes：NaN deadline 在 authority/source read 前拒绝；slow source read 在 deadline 内终止 worker 且无 residual child；调用方 request path 不会覆盖 authority receipt path。

## 搜索面与未验证项

已按 ACTIVE specs 对 source eligibility、selector/mode matrix、deadline/no-background、none/incomplete/corrupt、selected attempt headers/body/end facts、wire/default result boundary、History index projection 逐项比对，并阅读了当前目录中全部 `tests/unit/replay/` 与 `tests/unit/history/` Python tests。

未读取或验证 RawCapture writer/reader 的 producer implementation，因此“RawCapture attempt facts 确由 writer-acknowledged frame 产生”的生产侧事实不在本次代码搜索面；本次仅核验其在 History 和 Replay 之间的 direct projection/gate 不会自行推断或放宽。该限制不影响上述 scoped verdict。
