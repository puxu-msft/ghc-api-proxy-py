# Resident byte budget 定向独立终审 R3

## 评审范围与 verdict

- **评审范围**：只读复核 `/home/xp/src/ghc-api-proxy-py-reservation` 的 `feat/resident-byte-budget@8fb6a97e97fe7db9034b1b68636bc40beaf7cec6`，base 为 `080105b54614e1320a5c193d7206dcaa584c9b41`。本轮只复核 R2 唯一 major——对已初始化 lease 重复调用 `lease.__init__()` 必须拒绝且 request／global 账本不漂移；另以最小 selector 抽查 R1 原 4 项 major 未回退。不扩展 production quota、route 配置、parser charge-before-read、admission、metrics、History、完整 `REL-06`、整文件或全仓测试矩阵。
- **总体 verdict**：**可进入下一阶段。0 major，明确可 squash。**
- **Blocker 数**：0。
- **Major 数**：0。

## 双视角覆盖证据

### 机械核对

- 每个采信的 shell 结果都在同一次调用中打印并断言物理 cwd、Git top-level 与完整 HEAD。候选现场解析为 `8fb6a97e97fe7db9034b1b68636bc40beaf7cec6`，base 解析为 `080105b54614e1320a5c193d7206dcaa584c9b41`；branch 为 `feat/resident-byte-budget`，测试与正控前后候选工作树均 clean。
- 完整读取 R1、R2、既有限定验收与最终实现。`5b744ce… → 8fb6a97…` 的定向修复只改 `src/app/delivery/reservation.py` 与 `tests/smoke/test_anthropic_block_delivery.py`，净增 one-shot guard及其回归；相对 base 的最终 pathset仍为原四路径。
- 显式设置候选 `PYTHONPATH`，并断言 `app.delivery.reservation` 与 `app.delivery.anthropic_sse` 均从候选 worktree 的 `src/` 加载。
- 最小执行口径共 8 个 pytest case：首批 selector参数化后为 7 个 case并全部通过；为闭合 close 后 pending lease 的另一失败方向，另跑 1 个专用 case并通过。对全部相同 selector做 combined `--collect-only`，独立确认 `8 tests collected`。未运行整文件、全仓、Ruff或Pyright，不把旧轮次的更大矩阵退出码外推到本 exact HEAD。
- 对唯一 major 做进程内正控，不编辑文件：临时恢复 R2 的可重入 `ResidentLease.__init__` 后，目标测试按预期因“未抛 `RuntimeError`”变红；新进程退出后在原始候选代码上复跑为 `1 passed`。该测试确实咬住重复初始化拒绝机制，而不是旁路断言。

### 第一人称执行模拟

- **重复初始化**：先申请 owner=`payload`、amount=`5` 的 lease，再直接调用 `lease.__init__("payload", 1)`。最终实现先在 `src/app/delivery/reservation.py:189-190` 检测既有 `_owner` 并抛 `RuntimeError("resident lease is already initialized")`，未执行后续三次 `object.__setattr__()`。测试随后确认 lease amount仍为 `5`、request current仍为 `5`、global current仍为 `5`，正常 `account.release(lease)` 后 lease标记 released且两级余额均归零。
- **close 后写**：关闭 session 后分别走 accepted writer 的全部四个写入口，以及 pending `render_error()`；所有路径都在 reserve／sink之前拒绝，writer没有新增 bytes，两级账本保持零。
- **pending ACK／close race**：分别让 ACK 与 close先进入 release中点；两种参数化调度都只释放一次 rendered lease，首次 close完成且两级余额归零。
- **request aggregate／`reserve_many()`／capacity waiter**：已持有 `6` 后申请 `5` 在 request capacity `10` 下 typed fail且余额仍为 `6`；批量 `(6, 5)` 失败后双零、没有 partial charge；shared holder释放后等待中的 `4` bytes reservation继续完成并最终双零。
- **lease 普通篡改入口**：既有回归继续确认公开／私有 charge属性的普通 `setattr()` 均拒绝，且实例没有公开 `mark_released()` 或 `release()` 状态转换入口。

## R2 唯一 major 处置

| R2 finding | R3 结论 | 最终证据 |
|---|---|---|
| 已初始化 lease 可通过公开 `__init__` 重写 owner／amount／released，随后 release按伪造 amount扣账并留下 request／global 各 `4` bytes | **关闭** | `src/app/delivery/reservation.py:179-208`；`tests/smoke/test_anthropic_block_delivery.py:913-950`；旧行为正控变红，恢复后同一测试变绿 |

## 原 4 项 major 防回退抽查

| R1 major | R3 抽查结论 | 最终证据 |
|---|---|---|
| `aclose()` 后可写并泄漏 rendered lease | **未回退** | `src/app/delivery/anthropic_sse.py:813-835,915-945`；`tests/smoke/test_anthropic_block_delivery.py:963-1040`；accepted 全入口与 pending 专用 case均通过 |
| pending ACK 与 close竞争 double release | **未回退** | `src/app/delivery/anthropic_sse.py:838-945`；`tests/smoke/test_anthropic_block_delivery.py:1042-1115`；两个参数化调度均通过 |
| `ResidentLease` 可篡改 | **未回退，且 R2 等价入口已关闭** | `src/app/delivery/reservation.py:165-208`；`tests/smoke/test_anthropic_block_delivery.py:913-950` |
| request aggregate、原子 `reserve_many()` 与容量恢复 waiter 缺测试 | **未回退** | `tests/smoke/test_anthropic_block_delivery.py:835-910`；三个定向 case均通过 |

## 事实性发现

未发现问题。R2 唯一 major已由共同构造入口的 one-shot guard关闭；拒绝发生在任何 lease事实重写之前，失败后两级账本保持原值，随后正常 release归零。原 4 项 major的最小抽查未发现回退。

## 主观建议

无。本轮不应借终审扩展 production quota或完整 `REL-06` 范围。

## 结构怪味扫描

- `src/app/delivery/reservation.py:113-176`——**计账真相源分叉检查**——request／global charge与release仍集中在同一 account／condition临界区；本轮无需处置。
- `src/app/delivery/reservation.py:179-208`——**初始化与可变性边界检查**——重复初始化 guard位于所有字段写入之前，普通赋值继续由统一 `__setattr__` 拒绝；本轮无需处置。
- `src/app/delivery/anthropic_sse.py:813-945`——**cleanup／ACK双 owner检查**——写入口、ACK与 close仍由 operation lock及单一 cleanup task协调；本轮无需处置。

## 最终结论

**`feat/resident-byte-budget@8fb6a97e97fe7db9034b1b68636bc40beaf7cec6` 相对 `080105b54614e1320a5c193d7206dcaa584c9b41` 为 `0 blocker／0 major`，明确可 squash。** 该结论只放行本 exact candidate 的 resident-byte primitive切片，不表示 production quota、完整 resident accounting、完整 `REL-06`、部署或 cutover 已完成。本轮未执行 squash、commit、archive、部署或 cutover。

## 报告评审状态

本会话是 leaf reviewer，不能派生另一名 reviewer。本文已完成事实证伪、双视角执行模拟、正控与 exact-tip最小门；按 wrap-up 产物规则，主会话在采用本报告前仍须独立复核本文 current-state断言、数字口径与行号。该义务不改变本轮 `0 blocker／0 major` 的定向终审结论。
