# Replay capability fix 独立只读评审

## 评审范围

评审对象限于调用方指定的 replay capability fix：`src/app/replay/process.py`、`src/app/replay/__init__.py`、`src/app/history/entry.py`、History 的直接 read projection、`tests/unit/replay/test_process.py`、`tests/unit/history/test_history_entry.py`，以及直接相关的 Spec 和既有报告。明确未评审 raw-capture writer、archive storage、History routes、retention 或其他并发 WIP。

评审时点：2026-09-15 UTC；代码证据取自共享工作树当前状态。工作树存在大量范围外未提交改动；本报告不把它们归因于本修复。

## 总体 verdict

**needs-fix。** 当前有两个 major：一个 non-finite deadline 可绕过拒绝门并触发 capture reader；另一个 capability 未与 source entry/capture 绑定，不能作为该 source 的强制前置条件。上轮的 per-attempt History capability/provenance 缺口也只完成了 evidence-side 修复，尚未完成 History projection。

## Blocker 数

**0。** 当前新发现：major 2、minor 1；另有上轮 major `OBS-CONTRACT-R1-05` 为 partially-closed。

## 判据与方法

- 直接判据：调用方给出的独立判据；`.dev/docs/raw-capture/spec.md` §4.1；`.dev/docs/history/spec.md` §1、§3–§6；`.dev/docs/replay/spec.md`。
- 对照的上轮问题：`OBS-CONTRACT-R1-05`（capability aggregate-only 与 wire attempt boundary gate 漏检）。
- 作者报告和进度账本仅作为待核验 claim，不作为判据或代码事实。
- 待完成：读取直接实现/完整单测及 replay Spec；对各 mode、corrupt/incomplete/selector/deadline/数据泄漏做 focused tests 和不落盘 probe。

## 上轮已知问题闭合度

### OBS-CONTRACT-R1-05 — partially-closed

上轮 finding 的 wire evidence 漏检部分已闭合：`ReplayProcess._attempt_complete()` 现在要求选定 attempt 有 `upstream.attempt.start`、`upstream.request.start/body`、`upstream.response.start/body/end(complete=true)` 和 `upstream.attempt.end(complete=true)`。现有 focused test 的完整 attempt diagnostic record 集也覆盖了两个 attempt boundary；`complete_attempt=false` 时稳定报 `source_evidence_unavailable`。

但该 finding 要求的 **per-attempt capability/provenance 进入 History attachment/read projection** 仍未闭合。`RawCaptureObservation`、`CaptureCapabilities` 和 `HistoryIndexEntry` 都只有三个 aggregate eligibility boolean；`HistoryIndexEntry` 的 SQLite read projection 也只能恢复这些 aggregate 字段，并没有 `upstream_attempts[]` 或“selector attempt id → complete capability”的关联。因此 History 无法在选择某个 `upstream_attempt(attempt_id)` 前提供该 attempt 的冻结资格。当前 process 改为读取 raw evidence 后临时验证 selector，修复了“错误地放行 incomplete boundary”，却没有完成上轮要求的 capability/provenance projection。

## 当前系统发现

### REPLAY-CAP-01 — 非有限 deadline 绕过同步拒绝门，并在拒绝前触发 capture reader

- **severity:** major
- **primary_location:** `src/app/replay/process.py:132-145,253-255`
- **related_locations:** `tests/unit/replay/test_process.py:356-381`; `.dev/docs/replay/spec.md:45-49`

**判据**

Replay Spec §4 要求所有 mode 有显式或配置的 deadline，且 HTTP 返回或取消后不得后台继续执行。调用方的独立判据进一步要求 corrupt/incomplete/wrong-selector/**deadline** 稳定拒绝，且拒绝路径不能读取或输出正文/凭据。

**证据**

`ReplayProcess.run()` 只以 `>` 检查 `deadline_s > max_deadline_s`；随后 `_validate_request()` 也只检查 `<= 0` 和 `> 86_400`。`float("nan")` 对三种比较都为 false，因此它通过两层 deadline gate，随后进入 `_validate_capabilities()` 和 `_read_source()`。

执行了不落盘 probe：把 `iter_raw_capture_records` 替换为只要被调用就抛出 `AssertionError` 的内存 stub，并以有效 History capability、nonexistent path 和 `deadline_s=float("nan")` 调用 `run()`。probe 对 capability 缺失、`incomplete`、wrong selector、负 deadline 分别得到稳定 not-started error，唯独 NaN 输出 `nan_deadline:READER_INVOKED`。这证明它在拒绝 deadline 前已尝试读取 capture；focused pytest 的 24 个 case 全绿，但没有覆盖 non-finite deadline。

**影响**

NaN 是可构造的 `float` 输入。它既不能得到稳定的 `invalid_deadline`，也不能保证在 I/O 或 executor 前停止；在存在 capture 的场景，reader 会先接触 raw transport evidence。该路径直接违反 deadline 的前置 gate 和“拒绝前不读 source”的独立判据。

**闭合要求**

在任何 capability/source I/O 之前以 `math.isfinite()`（或等价逻辑）拒绝 NaN/±infinity，并增加测试：reader/executor stub 必须未被调用，error 必须是 `invalid_deadline` 且消息不含 source body/header/credential。

### REPLAY-CAP-02 — capability 没有绑定 source entry/capture，可用另一 source 的允许值越过本 source 的拒绝

- **severity:** major
- **primary_location:** `src/app/replay/process.py:49-59,283-305`
- **related_locations:** `src/app/history/entry.py:32-63,101-121,176-189`; `src/app/history/writer.py:73-112,909-1005`; `src/app/observability/capture_observation.py:12-20`; `tests/unit/replay/test_process.py:128-166`

**判据**

Replay Spec §1–2 要求 Replay 从 History/Capture artifact 读取 source，并由主程序记录 replay eligibility；调用方的独立判据要求 HistoryEntry/RawCaptureObservation 的三个 eligibility flag 是 **replay 的强制前置条件**，不是 advisory。

**证据**

`RawCaptureObservation` 有 `capture_ref`，`HistoryEntry` / `HistoryIndexEntry` 也各自携带 entry/capture reference；但是传入 `ReplayProcess` 的 `CaptureCapabilities` 只含 status 和五个 boolean，`ReplayRequest` 又把它与 `source_entry_id`、`capture_path` 分离。`_validate_capabilities()` 只检查该无 provenance 的 object，从不比较它与 `source_entry_id` 或 `capture_path`。类型和 runtime contract 因而无法表示“这些 flag 来自当前 source B”，也无法拒绝把 source A 的 complete/eligible capabilities 连同 source B 的 path/entry id 组合起来。

随后 `_read_source()` 只按 `request.source_entry_id` 从 path 过滤 record；若 B 的 raw evidence 可读且完整，semantic/live 会继续解析和执行，尽管 B 自己的 History projection 可以是 denied/incomplete/corrupt。现有测试只证明“把 B 的 false capability 传进来会拒绝”，没有测试 capability source mismatch，也没有可供实现建立比较的 provenance 字段。

**影响**

这使 capability 成为调用方可替换的 advisory boolean，而不是 **selected source 的**强制前置条件。它可导致对本应由 B 的 History flag 拒绝的 evidence 读取 body，semantic/live 还可进入 executor；同时 process 无法区分正常与错配输入。该问题不依赖 source credentials 被输出，已经违反 source authorization/eligibility 的数据流合同。

**闭合要求**

让 process 接收并验证一个 source-bound History projection（至少同时绑定 `source_entry_id`、`capture_ref`/canonical capture identity 和 capabilities），或把 expected entry/ref 加入 immutable capability grant 并在 source I/O 前严格比对。增加 swapped-capability test，要求 reader/executor 都不被调用。

### REPLAY-CAP-03 — 未 capture 的 History source 返回了与 Replay Spec 不一致的 `incomplete` 错误

- **severity:** minor
- **primary_location:** `src/app/history/entry.py:46-64`
- **related_locations:** `src/app/replay/process.py:283-305`; `.dev/docs/replay/spec.md:26-32`

**判据**

Replay Spec §2.2 为“没有 capture”规定 `source_content_unavailable`；`source_evidence_unavailable` 留给不可读或损坏的 evidence。History Spec §3 明确未命中 capture 的 entry 具有 `capture_ref=none`、`capture_status=none` 且三个 replay flag 均为 false。

**证据**

`CaptureCapabilities(status="none")` 由 `replay_rejection_code()` 落入 `status != "complete"` 分支，返回 `source_capture_incomplete`。不落盘 probe 将 reader 替换为 fail-fast stub，并传入 `status="none"`：结果为 `none_capability:source_capture_incomplete:not_started=True`。因此 gate 的 I/O 顺序正确，但用户可观察错误码不符合 source-missing 的 Spec contract。现有 parameterized History test 覆盖 corrupt、incomplete、denied 和 allowed，未覆盖 `none`。

**影响**

未 capture source 会被错误归类为 capture 不完整，调用方不能依赖 Spec 所列 stable code 区分“从未有 source”与“已有 source 但不完整”。

**闭合要求**

为 `status == "none"` 单列 `source_content_unavailable`，并为 none/no-ref source 添加 no-reader 和稳定错误码测试。

## 已核验的正向行为

- `HistoryEntry.from_request_facts()` 逐字段投影 `RawCaptureObservation` 的 status、client request/response availability 和三个 replay eligibility flag；`HistoryIndexEntry` 的 SQLite write/read projection 持久化并恢复同一组字段。旧 SQLite schema migration 的默认值为 false，因此旧行不会因本修复被放行。
- 对 capability 缺失、`incomplete`、`corrupt`、wire/semantic/live 的 false eligibility、wrong selector、负 deadline 的不落盘 fail-reader probe，均得到稳定 `ReplayError`，且 reader 未被调用。错误信息是固定描述，没有 probe 中的 source body/header。
- selected wire attempt 的内存 evidence probe 保持 response end complete、但将 `upstream.attempt.end.complete` 置为 false，稳定得到 `source_evidence_unavailable`；这直接覆盖了上轮 finding 所指的 boundary 组合。
- `uv run pytest tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py`：**24 passed**（Python 3.14.2，3.91 s）。

## 搜索面、限制与结论

已读：四份直接行为 Spec（raw-capture、History、observability、Replay）、本修复报告/账本、上轮契约评审、指定的 replay/history implementation 与完整两份 unit test，并读取了 History SQLite direct read projection 和 `RawCaptureObservation` 的最小类型定义。检查了指定文件的 working-tree diff；范围外 WIP 只用于确认其不在本评审归因内，未评审 raw-capture writer、archive storage、History routes、retention、providers、config 或其他并发改动。

focused green 的分辨力有限：它们覆盖通常的正/反例，却未覆盖 NaN/non-finite deadline、none status、capability 与 source 的 provenance mismatch，因而未能阻止 REPLAY-CAP-01 至 03。
