# Replay deadline fix merged-state review

## 评审范围

仅审阅当前 merged state 的 `src/app/replay/process.py` 中 `_read_source` 及其直接调用/辅助路径、`tests/unit/replay/test_process.py` 和 `.dev/docs/replay/spec.md`，以 C1–C6 为核验断言。明确未审阅其他工作树改动、CLI、History/RawCapture 的实现细节，以及未被本范围直接调用的 replay 行为。

## 总体 verdict

pass。RDR-001 已关闭；当前 merged state 满足 C1–C6，且复审未发现 blocker、major、minor 或 nit。

## Blocker 数

0。

## 证据日志

### 2026-09-16 — 判据与初始边界

规格 §4 要求 deadline 在 source read 前建立，offline local read/decode/summary 逐步检查预算，并在超时后停止处理。C1–C6 进一步要求 `_read_source` 返回后的所有随 records/body/attempt 增长的循环共享该 deadline、消除 O(records*attempts) 重扫、停止 CPU 聚合、保留 payload/error 语义，并以可失效的回归测试覆盖大量不同 attempt、deadline 边界及空 source 邻接路径。

## Major

### RDR-001 — 大量不同 attempt 的 deadline 回归测试不能杀死删除了聚合循环 gate 的 mutant

- **状态：**closed（2026-09-16 复审）。
- **Primary location:** `tests/unit/replay/test_process.py:735-794`
- **Related locations:** `src/app/replay/process.py:413-425`
- **证据：**在 `/tmp/ghc-replay-single-gate-mutant` 的隔离副本中，仅删除 `_read_source` 首个按 `records` 聚合 attempt 的循环入口 deadline gate（当前第 414 行），并确认测试实际导入的是隔离副本的 `process.py`。随后运行该测试的单例，结果仍为 `1 passed`（2026-09-16）。因此该测试没有满足 C5 所要求的“故意删除 deadline gate 会变红”。
- **影响：**这是确保 source read 后不会越过 deadline 继续 CPU 聚合的唯一针对“有限但大量不同 attempt”路径的回归保护。该 gate 的删除可随未来重构无声通过，从而让 C1/C3 的 deadline 保证退化而测试仍绿。
- **建议修复方向：**让测试能唯一地观察该聚合循环的检查：例如以独立计数/阶段信号断言在进入第一个 attempt 聚合迭代前 deadline 已过且立即抛出，或针对两个增长循环分别设置无法被后续 gate 掩盖的失效阈值；修复后重跑同一个单-gate mutant，必须失败。

## 核验与搜索面

### C1–C4、C6

- **C1（通过代码核验）：**`_read_source` 在 reader 返回后，`_body` 的 records/chunks 循环、`_end_complete` 的 records 循环、attempt grouping 的 records/attempts 循环均传递同一 `deadline_at` 并逐项调用 `_require_remaining_deadline`（`process.py:403-425,555-593`）；随后 wire summary 的 records 循环也继续使用同一 deadline（`process.py:519-545`）。
- **C2（通过代码核验）：**attempt 收集为一次 records 扫描加一次 distinct-attempt 转换；没有按每个 attempt 回扫全体 records 的嵌套扫描。source read 后复杂度为 O(records + body_chunks + attempts)，不含 O(records × attempts) 路径。
- **C3（通过代码和执行核验）：**所有上述增长循环在处理下一项前 gate；focused test 的 source-read、post-read attempt scan 和 request decode deadline 路径均通过。超时会抛出 `ReplayError("deadline_exceeded", ...)`，不会继续到 diagnostic/executor 聚合。
- **C4（通过执行核验）：**38 个 focused unit tests 通过；另以临时 monkeypatch probe 验证 body 拼接、`request.body.end` 完整性与含 string event 的 attempt 17 仍被保留。既有测试同时覆盖不完整 source、wire body/header evidence 和 safe diagnostic/result projection。
- **C6（通过执行核验）：**手工 probe 确认 `-0.01` 与 `NaN` 在 reader 之前得到 `invalid_deadline`，空 source 得到 `source_evidence_unavailable`；focused tests 覆盖 `NaN`/±infinity 与有限的 0.02/0.05/0.1 秒 deadline 路径。

### 已执行

- `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider tests/unit/replay/test_process.py` → **38 passed**。
- `uv run --no-sync ruff check --no-cache src/app/replay/process.py tests/unit/replay/test_process.py` → **All checks passed**。
- `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pyright src/app/replay/process.py tests/unit/replay/test_process.py` → **0 errors, 0 warnings, 0 informations**。
- 在已删除的 `/tmp/ghc-replay-single-gate-mutant` 隔离副本中，确认 import 指向 mutant `process.py` 后运行 RDR-001 的单例 mutation probe → **1 passed / MUTANT_SURVIVED**。

### 未覆盖面

本次未审阅或执行 CLI、History/RawCapture 的实现、真实 capture 的超大文件性能、跨平台 multiprocessing（当前实现使用 `fork`）以及工作树中其他未提交改动；这些均在用户给定范围之外。未发现其他 blocker、minor 或 nit。

## 2026-09-16 — RDR-001 修复复审

### 范围与既有发现状态

复审范围仍限于 `src/app/replay/process.py` 的 `_read_source` 及直接辅助/调用路径、`tests/unit/replay/test_process.py` 和 `.dev/docs/replay/spec.md`。RDR-001 为 **closed**：修复后的测试以 `CountingAttemptRecord` 的 `attempt_reads` 作为 phase signal，不再仅凭后续循环的 deadline gate 间接变红。

### C1–C6 复核

- **C1 / C3：**当前代码对 reader 返回后的 records、body chunks、attempt grouping/tuple conversion、wire summary 循环均传递同一 `deadline_at`，并在处理下一项前调用 `_require_remaining_deadline`。规格 §4 所要求的 local read/decode/summary budget 和超时立即停止仍成立。
- **C2：**attempt 仍是单次 records 聚合加单次 distinct-attempt 转换，不存在按每个 attempt 重扫全部 records 的 O(records × attempts) 路径。
- **C4：**focused suite 和独立 probe 确认 string-event attempt、body 拼接、`request.body.end` 完整性、source error code 及安全投影语义未被该测试修复改变。
- **C5：**在当前实现中，source authority 的 gate、reader-return gate、`_body` records scan 与 `_end_complete` records scan 共恰好消耗 `2 * len(records) + 2` 次检查；测试 callback 在下一次调用才抛错，故当前第一个 attempt-grouping loop 的入口 gate 必然在读取任何 `record["attempt"]` 前触发。`attempt_reads == 0` 直接确认这个 phase。于已删除的隔离副本中仅删掉该入口 gate 后，测试实际导入 mutant `process.py` 并失败：`attempt_reads == 3500`，随后输出 `MUTANT_KILLED`。这同时证明不会由后一个 attempts loop 的 gate 掩盖此 mutation。
- **C6：**独立 probe 重新确认负数与 NaN deadline 在 reader 前得到 `invalid_deadline`，空 source 得到 `source_evidence_unavailable`；focused suite 继续覆盖有限 deadline 及 infinity 变体。

### 测试设计复核

`CountingAttemptRecord` 仅存在于测试函数内部，`monkeypatch` 自动回滚替换；没有生产代码测试钩子、全局状态或持久化测试污染。`attempt_reads` 观察的是目标 first grouping loop 在 gate 后的第一项工作，恰好对应 C1/C3 的停止边界，而非断言私有容器布局或调用结果。检查次数计算只用于把合成 deadline 安置在该边界：增加早期 gate 只会更早停止且仍满足 `attempt_reads == 0`，删除目标 gate 则由 3,500 次实际 attempt 读取使测试失败。

### 本轮执行与未覆盖面

- `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider tests/unit/replay/test_process.py` → **38 passed**。
- `uv run --no-sync ruff check --no-cache src/app/replay/process.py tests/unit/replay/test_process.py` → **All checks passed**。
- `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pyright src/app/replay/process.py tests/unit/replay/test_process.py` → **0 errors, 0 warnings, 0 informations**。
- isolated single-gate mutation probe → **MUTANT_KILLED**；临时副本已删除。

未覆盖 CLI、History/RawCapture 实现、真实超大 capture 性能、跨平台 multiprocessing 与范围外工作树改动。当前复审未发现活跃 blocker、major、minor 或 nit。
