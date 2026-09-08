# Task 4B-P authority correction 独立评审

## 评审范围

- 修订快照（已核 sha256sum）：Spec `fdf63872b906dc87ec44eb4627c199552cc904d730add186600cc5095c639df9`；Plan `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`；status `4a03b23cefd04ea7a07faf4082f4ad817fcae6b8ae0619f30571bf7786485220`；HANDOVER `4c4c52d518bfe912548397f250f5e83e68391a889b89fc2a3bb0ad27047f7816`；`task-4bp-brief.md` `df79ffa92c4e1a703b05638e61c1c2f2b97a206fbd18007d8fc530a2f65f1bec`。
- 判据：Task 3B `InputItemContribution.item_framing_tokens == 4`；Spec §6.2 full baseline／current-zero；A45 修订前后；brief C04／C06；Plan Task 4B-P checklist。实现者 preflight 报告只作发现来源，不当行为权威。
- 只读：未改 authority／brief／source；未启动 4B-P source、4141、shared main。

## 总体 verdict

**NEEDS FIXES。** blocker=0，major=1，minor=0。A45／C04 的 fixture 修正本身成立，也**不需要用户裁决**。但 brief §1 仍钉着修正前的 Spec／status／HANDOVER hash，和它自己的「hash 不一致则停止」条款冲突，**source 仍不能授权**。

## Findings

### T4BP-AC-01 — brief §1 未跟上 correction snapshot 的 Spec／status／HANDOVER hash

- **severity:** major
- **confidence:** high
- **阻塞派发:** 是
- **primary_location:** `task-4bp-brief.md` §1
- **related_locations:** 当前 Spec／status／HANDOVER 文件 hash；brief 同节「若 Spec 或 Plan 不再等于上述 hash，停止并先做 brief delta review」

**事实**

| 文件 | brief §1 钉的 hash | 磁盘当前 hash |
|---|---|---|
| spec.md | `5d9477dd…` | `fdf63872…` |
| status.md | `f482da1b…` | `4a03b23c…` |
| HANDOVER.md | `4c8238df…` | `4c4c52d5…` |
| plan.md | `bea5e753…` | `bea5e753…`（未改，一致） |

HANDOVER／status 已经指向新 Spec 与新 brief 字节。实施者按 §1 启动会立刻因 Spec hash 不等而 stop。C04 正文已改、§1 身份未改，correction 包装不完整。

**最小修法：** 把 brief §1 的 Spec／status／HANDOVER 点时 hash 改成上表当前值（并重算 brief 自身 hash 写回 HANDOVER）。不改 C04 行为。

## 修正内容本身

1. **矛盾已关闭，normative 未改。** 合法 strict append 至少带 item framing 4，known delta 不能为 0。新 fixture：正 known delta **且** 正 visual／prior，actual＝完整 baseline（residual／log-ratio 为 0）；known-only mutation 会把 visual／prior 打进 residual，仍可红。C06 current-zero（current baseline 0、≥3 条正 ratio、multiplicative 仍在、suffix 0）未改。Spec §11 否决 known-only／zero-current deletion 未改。
2. **Spec revision record 已写。** §15 明确 agent-derived、不改变 full-baseline／current-zero 行为、无新用户分叉。同意：不需要额外用户裁决。
3. **Plan checklist 本就兼容。** Task 4B-P 只要求 known-only 与 full baseline **分叉**，从未要求 known delta＝0。不必改 Plan。
4. **Allowed paths／stop rule 仍清楚。** 仅 `prediction.py`＋`test_prediction.py`；carrier 冲突 stop、不改 types。source 授权仍要求本 review READY **且** hash 对齐。
5. **HANDOVER 历史 T3B-AUTH-04** 仍录「known delta 为 0」为当时 finding 原文（标明历史保留）。Living A45 已改；不要当现行 fixture。status／HANDOVER 写「等待 fresh scoped review／source 未授权」与本次评审时刻一致。

## 未采用建议

- 改写 HANDOVER 历史 AUTH-04 正文：会抹掉当时发现；保持「原样保留」即可。
- 为 Plan 3B 清单补「正 known delta」字样：该条本属 4B-P，不必借 3B checklist 重写。

## 未验证边界

- 未跑 4B-P source／tests／mutations（source 仍未授权）。
- 未在运行时再证 `InputItemContribution` 拒 framing≠4（既有 3B DTO，本轮未重跑）。

## 搜索面

sha256sum 五文件；读 A45、§15 修订、brief §1／C04／C06、Plan 4B-P checklist、status 任务投影、HANDOVER 门禁与下一步。未改文件。

## Verdict

**NEEDS FIXES。** 先改 T4BP-AC-01（brief §1 hash），再授权 source。0 Blocker。
