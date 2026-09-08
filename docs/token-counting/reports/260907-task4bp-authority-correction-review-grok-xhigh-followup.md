# Task 4B-P authority-correction follow-up（hash lineage）

## 评审范围

- 被评对象：修订后 `task-4bp-brief.md` SHA-256 `17511ee519ed4ad40641b152c45088e536d6a75ee734d03ea79c69e1f495523c`。
- 上一 finding：T4BP-AC-01（§1 旧 Spec hash 会强制 delta-review stop）。
- 只读：未改 authority／source；未启动 4B-P／4141／shared main。

## 总体 verdict

**READY。** blocker=0，major=0。T4BP-AC-01 **closed**。可以在确认 HANDOVER 仍授权同一 slice 后派 Task 4B-P source。

## 上轮完成度

| ID | 状态 | 证据 |
|---|---|---|
| T4BP-AC-01 | **closed** | §1 Spec pin 现为 `fdf63872…`，与磁盘 spec.md 一致。Plan `bea5e753…`、status `4a03b23c…` 亦与磁盘一致。实施者不会再因 **Spec** hash 被强制做行为 delta review。 |

## Hash 对账（本轮实测 sha256sum）

| 文件 | brief §1 pin | 磁盘 |
|---|---|---|
| spec.md | `fdf63872…` | **一致** |
| plan.md | `bea5e753…` | **一致** |
| status.md | `4a03b23c…` | **一致** |
| HANDOVER.md | `a1ad58d3…` | 磁盘 `eb426ca8…`（**不一致**） |
| task-4bp-brief.md | （自身）`17511ee5…` | HANDOVER 正文已录 `17511ee5…`（**一致**） |

HANDOVER pin 过期是互相钉 hash 的固有环：HANDOVER 写入 brief 的 `17511ee5` 后自身 hash 从 `a1ad58d3` 变成 `eb426ca8`。brief 对 status／HANDOVER 的规则是「变化则确认仍授权同一 slice／base／paths」，**不是** Spec delta review。不重开 AC-01，也不要求再改 brief 去追 HANDOVER（会无限循环）。

## C04 修正

仍成立：正 known delta＋正 visual／prior、actual＝full baseline；禁止 zero-known append；known-only mutation 仍要红。A45 同期表述未回退。current-zero（C06）未改。无需用户裁决。

## Source authorization／stop rule

- Allowed paths 仍仅 `prediction.py`＋`test_prediction.py`；carrier 冲突 stop。
- Spec／Plan hash 已对齐 correction snapshot。
- 启动时 HANDOVER hash 会与 §1 不同：按 brief 只确认 base 仍为 `3badac7f`、两 allowed paths、4B-P 范围，然后继续。不得把这次差异当成新的 C04 矛盾。
- status／HANDOVER 仍写「source 未授权／review 进行中」，与本 follow-up **之前**的状态一致；本报告 READY 后由调度器更新投影。

## Findings

未发现新 blocker／major。

## 未验证边界

- 4B-P source 仍未跑 tests／mutations。
- 未重跑 3B framing＝4 DTO 测试。

## 搜索面

sha256sum 五文件；读 brief §1 stop 条款、C04、A45、HANDOVER 门禁／brief hash。未改文件。

## Verdict

**READY。**
