# 分类批次 04：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：38（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-resume-review-readiness-post-s3.md` | Readiness post-S3 独立定向复评 checkpoint | `service-cutover` | high | 评审对象为 `docs/agents/service-cutover/readiness.md` |
| `260807-resume-review-reasoning-capability-r2.md` | Reasoning capability R2 独立代码评审 | `anthropic-responses-bridge` | high | |
| `260807-resume-review-reasoning-capability-wip.md` | Reasoning capability WIP 评审，1 major | `anthropic-responses-bridge` | high | |
| `260807-resume-review-stream-route-current.md` | Stream route current WIP 复评，3 major | `anthropic-responses-bridge` | high | |
| `260807-resume-review-stream-route-r3.md` | Stream route R3 独立定向终审，0 major | `anthropic-responses-bridge` | high | |
| `260807-resume-review-systemd-plan-current-r2.md` | systemd living Plan R2 复评，1 major | `systemd-runtime` | high | 评审对象为 `docs/agents/systemd-runtime/plan.md` |
| `260807-resume-review-systemd-plan-current-r3.md` | systemd living Plan R3 复评，0 major | `systemd-runtime` | high | |
| `260807-resume-review-systemd-plan-current.md` | systemd living Plan 复评，1 major | `systemd-runtime` | high | |
| `260807-resume-review-systemd-plan-post-s3.md` | systemd living Plan S3 后复评 checkpoint | `systemd-runtime` | high | |
| `260807-resume-review-systemd-rebuild.md` | systemd new-main rebuild merged-state 评审 | `systemd-runtime` | high | |
| `260807-resume-review-systemd-squash-evidence.md` | systemd 逐片 squash 回放证据一致性复核 | `systemd-runtime` | high | |
| `260807-resume-verify-reasoning-capability.md` | Reasoning capability 独立验收 PASS | `anthropic-responses-bridge` | high | |
| `260807-resume-verify-stream-route-r2.md` | Stream route R2 独立验收 PASS | `anthropic-responses-bridge` | high | |
| `260807-resume-verify-stream-route-r3.md` | Stream route R3 独立验收 PASS | `anthropic-responses-bridge` | high | |
| `260807-resume-verify-stream-route.md` | Stream route happy slice 独立验收 PASS | `anthropic-responses-bridge` | high | |
| `260807-resume-verify-systemd-rebuild.md` | systemd S3+S4 rebuild 独立验收 PASS | `systemd-runtime` | high | |
| `260807-review-acceptance-current-resume.md` | Acceptance checkpoint 恢复确认 | `anthropic-responses-bridge` | high | 评审对象为 `docs/agents/anthropic-responses-bridge/acceptance.md` |
| `260807-review-acceptance-dual-carrier.md` | Acceptance 双 carrier 独立终审 | `anthropic-responses-bridge` | high | |
| `260807-review-acceptance-empty-reasoning-r2.md` | Acceptance 空 reasoning 定向复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-acceptance-empty-reasoning.md` | Acceptance 空 reasoning 定向复评 | `anthropic-responses-bridge` | high | |
| `260807-review-architecture-decision-matrix.md` | Architecture 用户裁决矩阵独立终审 | `anthropic-responses-bridge` | high | |
| `260807-review-architecture-final-state.md` | Architecture merged-state M1 定向终审 | `anthropic-responses-bridge` | high | |
| `260807-review-asgi-delivery-uncertainty.md` | ASGI delivery uncertainty 快速复核 | `anthropic-responses-bridge` | high | |
| `260807-review-backup-r3-living-checkpoint.md` | Backup R3 联合复评 checkpoint | `UNCLASSIFIED` | low | 同一报告联合评审 `anthropic-responses-bridge/implementation.md` 与 `service-cutover/readiness.md` 两份不同话题的文档，无法按单一被改对象归类 |
| `260807-review-bridge-acceptance-r7.md` | Bridge Acceptance 独立终审 R7 | `anthropic-responses-bridge` | high | |
| `260807-review-bridge-acceptance-r8.md` | Bridge Acceptance 独立定向终审 R8 | `anthropic-responses-bridge` | high | |
| `260807-review-bridge-implementation-r4.md` | Bridge Implementation 定向复评 R4，1 major | `anthropic-responses-bridge` | high | |
| `260807-review-bridge-implementation-r5.md` | Bridge Implementation 定向复评 R5，1 major | `anthropic-responses-bridge` | high | |
| `260807-review-bridge-implementation-r6.md` | Bridge Implementation 独立终审 R6 | `anthropic-responses-bridge` | high | |
| `260807-review-bridge-readme-r3.md` | Bridge README 独立终审 R3 | `anthropic-responses-bridge` | high | |
| `260807-review-code-block-delivery-r2.md` | Block delivery 骨架定向代码复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-code-block-delivery.md` | Block delivery 骨架独立代码评审，2 major | `anthropic-responses-bridge` | high | |
| `260807-review-code-bridge-next.md` | Bridge-next merged-state 独立代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-bridge-successor.md` | Bridge successor merged-state 独立代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-carrier-v2-r2.md` | Reasoning carrier v2 定向复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-code-carrier-v2.md` | Reasoning carrier v2 独立代码评审，1 major | `anthropic-responses-bridge` | high | |
| `260807-review-code-graceful-timeout.md` | Graceful timeout 独立代码评审 | `systemd-runtime` | high | 评审对象即后续 systemd rebuild S3 片（archive `260807-systemd-graceful-timeout`），是 systemd unit deadline／installer 合同的一部分，不是 anthropic bridge |
| `260807-review-code-happy-path-r2.md` | Anthropic Responses happy-path 定向复评 R2 | `anthropic-responses-bridge` | high | |

## 新提出的 slug

无。

## 读不下去的文件

无。全部 38 个文件均可正常读取标题、评审范围与结论小节。
