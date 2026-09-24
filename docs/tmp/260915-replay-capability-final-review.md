# Replay capability 最终只读评审

## 评审范围

评审时点为 2026-09-15 UTC。仅审阅 `src/app/replay/process.py`、`src/app/replay/__init__.py`、`src/app/history/entry.py`、`src/app/history/writer.py` 中的直接 SQLite read projection、`tests/unit/replay/test_process.py`、`tests/unit/history/test_history_entry.py`，以及直接相关的 Replay、History、Raw Capture、Observability Spec 和本轮前序 replay capability 报告。

明确不审 raw-capture writer、History archive storage、routes、retention、providers、config 与其他并发 WIP。共享工作树存在这些范围外未提交改动；本报告不将它们归因于 replay capability 修复。

## 总体 verdict

**needs-fix。** 上轮 `REPLAY-CAP-01`、`REPLAY-CAP-02`、`REPLAY-CAP-03` 均已闭合；但当前 `wire_diagnostic` 将 selected upstream attempt 的原始 record 直接放入普通 `ReplayResult.as_dict()`，可默认输出 raw body 和 headers。此行为与 Replay Spec 的 source-full-transport result boundary 冲突，也是调用方给出的“不得输出正文或凭据”判据的反例。

## Blocker 数

**0。** 当前发现：major 1、minor 0、nit 0。

## 判据

- 调用方独立判据：wire diagnostic 必须有完整 upstream attempt；semantic/live 必须有完整 client request 和对应 capability；corrupt/incomplete/wrong selector/deadline 稳定拒绝；capability 不可与另一 source 交换；不得读取或输出正文或凭据。
- `.dev/docs/replay/spec.md` §2、§4、§6、§7：capture-required gate、同步 deadline、source transport 不默认嵌入 replay result、full transport 的显式敏感 projection。
- `.dev/docs/history/spec.md` §1–§4：History capture capability 是 replay 前提；无 capture 时 status/ref/capability 的默认拒绝形态。
- `.dev/docs/raw-capture/spec.md` §4.1：capture capability 不是单一 `complete` boolean，raw transport 是敏感数据面。

前序修复报告和进度账本仅作为待核验 claim；下文结论以最终代码、测试执行和独立内存 probe 为准。

## 上轮发现闭合度

### REPLAY-CAP-01 — closed

`ReplayProcess.run()` 在任何 target/source reader/executor 操作前先调用 `_validate_request()`；该 gate 以 `math.isfinite()` 加上下限、86,400 秒上限和 process 上限校验 deadline（`src/app/replay/process.py:149-151,257-269`）。`tests/unit/replay/test_process.py` 参数化覆盖 NaN、正无穷和负无穷并把 reader/executor 替换为 fail-fast stub。

独立无文件 probe 以 NaN 调用并确认 `invalid_deadline`、`not_started=True`；reader 没有被调用。为检查这条 green 的分辨力，另在独立 Python 进程作受控内存变异：将 module-local `math.isfinite` 临时替换为恒真后，同一 NaN 输入抵达 fail-fast reader。该变异不修改工作树或任何 capture 文件，证明该 probe 会在 finite gate 消失时转红。

### REPLAY-CAP-02 — closed

`ReplaySourceGrant` 不可变地携带 `entry_id`、resolved `capture_path`、`capture_ref` 和 `CaptureCapabilities`；`_validate_source_grant()` 在 reader 前逐项与 request 的 source binding 比对（`src/app/replay/process.py:59-66,287-330`）。entry、path 或 ref 任一不一致均稳定返回 `source_capability_mismatch`。

focused test 覆盖三种 swapped grant，并确认 reader/executor 均不启动。独立无文件 probe 也以错 entry grant 得到 `source_capability_mismatch` 和 `not_started=True`，未触发 fail-fast reader。

### REPLAY-CAP-03 — closed

`CaptureCapabilities.replay_rejection_code()` 将 `status == "none"` 映射为 `source_content_unavailable`（`src/app/history/entry.py:47-65`），而 source-bound grant gate 在 source I/O 前使用这个结果。History direct read projection 也持久化、查询并重建五个 capability 字段和 `capture_ref`（`src/app/history/writer.py:73-110,442-482,597-636,908-1005`）。

focused unit tests覆盖 capability 的 `none` 语义和无 capture source；独立无文件 probe 得到 `source_content_unavailable`、`not_started=True`，reader 未被调用。

## 当前系统新问题

### REPLAY-CAP-FINAL-01 — wire diagnostic 默认把 raw transport record 输出到 result

- **severity:** major
- **primary_location:** `src/app/replay/process.py:102-120,155-175`
- **related_locations:** `src/app/replay/process.py:348-421`; `tests/unit/replay/test_process.py:271-289`; `.dev/docs/replay/spec.md` §6–§7; `.dev/docs/raw-capture/spec.md` §4.1

**证据**

1. `ReplayResult` 的公开 `diagnostic_records` 字段保存 `Mapping` 原 record，`as_dict()` 无过滤地把它转成 list（`process.py:102-120`）。
2. wire 成功路径将 `_selected_attempt_records()` 的完整 record tuple 赋给该字段（`process.py:155-175`）。该 helper 仅按 attempt 选择，不执行 safe projection 或字段裁剪。
3. raw-capture Spec 将 headers 和 request/response body 定义为 raw transport 的敏感面；Replay Spec §6 又明确 replay result 不默认内嵌 source full transport，完整 transport 只能由显式 evidence projection 读取并标记 `contains_credentials=true`。
4. 本次无文件、非内容 probe 只注入测试 marker record，不打印任何 marker 值；wire result 的结构检查得到 `wire_result_exposes_body_field=True` 和 `wire_result_exposes_headers_field=True`。这证实该 result path 暴露的是 record 原字段，而非仅事件摘要。
5. 现有 wire unit test 仅断言 event names（`test_process.py:281-289`），没有断言 result/as_dict 不含 raw body 或 headers，因此 32 个 focused tests 全绿仍无法发现此泄漏。

**影响**

一次 capability-allowed 的 wire diagnostic 可以通过它的普通 result serialization 把 selected upstream attempt 的 raw transport 回给调用方；这包含正文和 headers 的数据通路。它既违背 Replay result 的默认安全边界，也违背本评审的非输出判据。该 finding 不依赖 routes 或 raw writer 的实现；`ReplayResult` 本身已经是可被 CLI/调用方消费的公开对象。

从 scoped diff 看，`diagnostic_records` 的无过滤 serialization 在本轮 capability 修复前已存在，故它是最终系统状态中的遗留问题，不归因于本轮对 finite deadline/grant/none 的修复；但不能因其非本轮引入而降低影响级别。

**闭合要求**

默认 `ReplayResult`/`as_dict()` 只能返回 safe diagnostic summary（例如 event type、attempt id、completeness/计数），不得返回 raw body 或 headers。若产品确实需要完整 evidence，必须通过 Replay Spec 所述显式 sensitive evidence projection，带清晰的 `contains_credentials=true` 边界，而不是复用普通 replay result。增加结构性回归测试，使用非敏感 marker 并只断言序列化结果中不存在 `body`、`headers` 或等价 raw transport payload 字段。

## 已核验的其余承重要求

- wire gate 要求 selected attempt 同时含 `upstream.attempt.start`、upstream request start/body、upstream response start/body/end（end 为 complete）和 `upstream.attempt.end(complete=true)`；缺失/不完整 attempt 与未知 attempt 都返回 `source_evidence_unavailable`，不执行 executor（`src/app/replay/process.py:382-424`）。
- semantic/live 在 grant capability 允许后仍要求可用且 complete 的 client request body，并在 JSON object 解析、target 和 executor 检查完成前不执行 replay（`src/app/replay/process.py:178-207`）。这满足“capability 不是 advisory、完整 client request 仍是独立条件”。
- selector 与 deadline 均在 source reader 前拒绝；corrupt/incomplete capability 也经 `_validate_source_grant()` 返回固定 rejection code。相关拒绝消息均为固定文案，独立拒绝 probes 没有输出 body/header 内容。
- `src/app/replay/__init__.py` 导出新的 `ReplaySourceGrant`，没有形成另一条绕开 grant 的公开 process API。

## 执行、搜索面与限制

执行：

```text
uv run pytest -q tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 32 passed

uv run python -c '<in-memory NaN / swapped-grant / none / wire-result-shape probe>'
# nan: invalid_deadline, not_started=True
# swapped: source_capability_mismatch, not_started=True
# none: source_content_unavailable, not_started=True
# wire result has raw body/header fields

uv run python -c '<controlled in-memory finite-gate mutation probe>'
# NaN reaches fail-fast reader when the finite predicate is removed

git diff --check -- <six scoped implementation/test files>
# passed
```

阅读面：完整读取了 scoped replay process、public exports、History entry projection、History SQLite schema/persist/list/get/row-read projection，以及两份指定 unit test；核对了 scoped diff、相关 Spec、上一轮 capability review 和本轮 fix report。没有读取、运行或判断 raw/archive/routes/retention 的实现或测试，也没有打印 source capture body、header 或 credential。

未运行全仓测试、集成测试、Ruff 或 Pyright；它们不替代此处的行为判据，且不影响本报告的 scoped execution evidence。
