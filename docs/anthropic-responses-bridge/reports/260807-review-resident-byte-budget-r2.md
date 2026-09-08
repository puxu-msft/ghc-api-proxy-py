# Resident byte budget 定向独立终审 R2

## 评审范围与 verdict

- **评审范围**：只读复核 `/home/xp/src/ghc-api-proxy-py-reservation` 的 `feat/resident-byte-budget@5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`，base 为 `080105b54614e1320a5c193d7206dcaa584c9b41`。范围严格限定为 R1 的 4 项 major 及其最小新增测试：close 后写、pending ACK／close race、lease 不可篡改、request aggregate／`reserve_many()`／capacity waiter。不扩展 production quota、route 配置、parser charge-before-read、admission、metrics、History 或完整 `REL-06`。
- **总体 verdict**：**修复 major 后可进入；当前不可 squash。**
- **Blocker**：0。
- **Major**：1。

## 双视角覆盖证据

### 机械核对

- 每次有效执行均在同一调用内断言物理 cwd、Git top-level 与完整 HEAD；候选执行前后 `git status --porcelain` 为空。相对 base 的最终改动仍限定在 `reservation.py`、`anthropic_sse.py`、`responses_anthropic_stream.py` 与 `test_anthropic_block_delivery.py`。
- 完整通读 R1 报告、原独立验收、切片说明及 4 个最终改动文件；逐项将 R1 的 4 个 major 对账到 hardening commit `5b744ce…` 的最终代码与新增测试。
- 显式设置候选 `PYTHONPATH`，并断言 `app.delivery.reservation` 与 `app.delivery.anthropic_sse` 均从候选 worktree 的 `src/` 加载。
- 精确执行与原 4 个 major 对应的 8 个 node-id；其中 ACK／close 参数化为 2 个 case，故执行口径为 9 项。结果为 `9 passed in 0.41s`；独立 `--collect-only` 得到 `9 tests collected`。这只说明现有最小新增测试全绿，不替代下面的反例。
- 对 lease 不可篡改测试做等价入口扫描：现有测试只检查 `setattr()`、删除的 `mark_released()` 与删除的实例 `release()`，没有检查公开 `__init__` 对已初始化 lease 的重入。

### 第一人称执行模拟

- **close 后写**：执行 `aclose()` 后分别尝试 `deliver()`、`consume()`、`finish()` 与 `render_error()`；最终代码在 operation lock 内由 `_raise_if_closed()` 拒绝，accepted／pending writer 都不会写入或新建 lease，重复 close 复用同一 cleanup task。
- **ACK／close race**：分别让 ACK 先进入 release 中点与 close 先进入 release 中点；`acknowledge*()` 与 `aclose()` 现在共用 `_operation_lock`，两个调度顺序都只释放一次 rendered lease，首次 close 完成且两级余额归零。取消一个 close waiter也不会取消后台 cleanup，后续 waiter可完成同一 task。
- **request aggregate／`reserve_many()`／waiter**：同一 request 已持有 6 bytes 后再申请 5 bytes，在 request capacity 10 bytes 下立即得到 request-scope typed failure且余额仍为 6；批量 `(6, 5)` 在 capacity 10 下全有或全无、失败后余额为 0；shared budget holder 释放后，等待中的 4-byte reservation继续完成并最终归零。
- **lease 不可篡改反例**：取得 owner=`payload`、amount=`5` 的合法 lease 后，直接调用公开 `lease.__init__("payload", 1)`。该调用成功把公开事实改成 amount=`1`，而 account／global current仍各为 `5`；随后 `account.release(lease)` 只各扣 `1`，终态为 lease `released=True`、request current=`4`、global current=`4`。反例不使用 `object.__setattr__`、私有 registry 或生产 quota 扩展，只调用对象公开存在的方法。

## 原 4 项 major 处置

| R1 major | R2 结论 | 最终证据 |
|---|---|---|
| `aclose()` 后 `render_error()` 可写并泄漏 | **关闭** | `src/app/delivery/anthropic_sse.py:813-835,915-945`；`tests/smoke/test_anthropic_block_delivery.py:958-1034` |
| pending ACK 与 close 竞争 double release | **关闭** | `src/app/delivery/anthropic_sse.py:838-945`；`tests/smoke/test_anthropic_block_delivery.py:1037-1147` |
| `ResidentLease` 可篡改 | **未关闭，仍为 major** | `src/app/delivery/reservation.py:165-205`；独立 `__init__` 重入反例稳定留下 request／global 各 4 bytes |
| request aggregate、原子 `reserve_many()` 与 waiter tests 缺失 | **关闭** | `tests/smoke/test_anthropic_block_delivery.py:836-910`；3 个直接测试均通过并分别区分 typed fail、全有或全无及容量恢复后继续 |

## 事实性发现

[major] `src/app/delivery/reservation.py:165-205`、`tests/smoke/test_anthropic_block_delivery.py:913-944` — `ResidentLease` 的公开 `__init__` 可重入，原“lease 不可篡改”major 仍可用等价入口绕过 — `ResidentLease.__setattr__()` 虽拒绝普通赋值，但 `ResidentLease.__init__()` 自身在 189-191 行无 one-shot guard 地调用 `object.__setattr__()`，可重写 `_owner`、`_amount` 与 `_released`；`RequestResidentAccount.release()` 在 170-175 行又信任被重写后的 `lease.owner`／`lease.amount`。独立候选进程中的确定性反例得到 `BEFORE=('payload', 5, False, 5, 5)`、`AFTER_REINIT=('payload', 1, False, 5, 5)`、`AFTER_RELEASE=('payload', 1, True, 4, 4)`。现有 read-only 测试只覆盖 `setattr()`，因此 9 项全绿仍是假绿，不足以放行 squash — **修复建议**：至少让初始化成为 one-shot，并新增 `lease.__init__(...)`／`ResidentLease.__init__(lease, ...)` 对已初始化实例必须失败且正常 release 后两级余额归零的回归。更稳健的共同基座修复是让 account registry保存构造时冻结的 canonical owner／amount，release 按 account-owned record 扣账而不再信任返回给调用者的 lease 字段；这仍属于当前 primitive 的不可篡改修复，不是 production quota 扩张。

## 已关闭路径的限定结论

- 未发现 close 后任一写入口可越过 `_closed` guard；pending outcome 不会在 close 后重新形成 lease。
- 未发现 ACK／close 当前仍可并发释放同一 rendered lease；公开 ACK、data ACK、conditional data ACK 与 close 均通过同一 operation lock串行。
- 未发现首次 close waiter取消会取消 cleanup task；`asyncio.shield()` 与持久 `_cleanup_task` 允许后续 close waiter继续等待同一清理。
- 未发现 request aggregate、`reserve_many()` 全有或全无或 capacity waiter恢复路径的新增测试缺口；三项测试直接命中对应机制，未借 production quota 接线扩大范围。
- 未发现本轮引入 `16 MiB`、per-block特殊阈值、spill、victim policy、route admission或隐藏 global singleton。

## 主观建议

无。修复只应闭合 lease 不可篡改及其回归，不应借本轮终审扩展 production quota。

## 终审结论

**0 blocker／1 major；当前不可 squash。** close 后写、ACK／close race，以及 request aggregate／`reserve_many()`／waiter 三组问题已经关闭；lease 不可篡改仍被公开 `__init__` 重入绕过。修复该入口并使新增回归对目标机制变红／恢复后变绿后，再做一次只针对该 major 的定向复评；若届时为 `0 major`，方可 squash。本 verdict 不外推为 production quota、完整 resident accounting或完整 `REL-06` 已完成。
