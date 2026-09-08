# 分类批次 03：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：37（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-final-systemd-next-replay-gate.md` | systemd-next 最终逐片回放 gate 审计 | `systemd-runtime` | high | |
| `260807-final-worktree-cleanup-plan.md` | 全仓 worktree／branch 清理只读计划 | `UNCLASSIFIED` | high | 横跨 anthropic-responses-bridge、systemd-runtime、network-retry 等全部 feature 线，是通用 Git housekeeping，非单一话题 |
| `260807-next-implementation-delta.md` | Implementation 下一步 delta（happy 四片回放） | `anthropic-responses-bridge` | high | |
| `260807-next-reservation-slice.md` | DeliverySession resident byte budget 设计切片 | `anthropic-responses-bridge` | high | |
| `260807-next-small-slice.md` | headers 前 network retry 最小切片设计 | `anthropic-responses-bridge` | high | |
| `260807-resume-audit-bridge-three-squash.md` | capability／History／stream 三片连续 squash 预检 | `anthropic-responses-bridge` | high | |
| `260807-resume-audit-capability-squash.md` | reasoning capability squash 只读审计 | `anthropic-responses-bridge` | high | |
| `260807-resume-audit-four-doc-checkpoint.md` | 四份 living 文档 checkpoint 只读审计 | `documentation-restructure` | high | live 文档真相审计（Acceptance/Implementation/Readiness/Systemd Plan 是否可提交） |
| `260807-resume-audit-living-checkpoint-r2.md` | living checkpoint R2 只读审计 | `documentation-restructure` | high | 同上 |
| `260807-resume-audit-living-checkpoint-r3.md` | living checkpoint R3 只读审计 | `documentation-restructure` | high | 同上 |
| `260807-resume-audit-living-checkpoint-r4.md` | living checkpoint R4 只读复核 | `documentation-restructure` | high | 同上 |
| `260807-resume-audit-living-checkpoint-r5.md` | living checkpoint R5 只读审计 | `documentation-restructure` | high | 同上 |
| `260807-resume-audit-living-checkpoint-r6.md` | living checkpoint R6 只读审计 | `documentation-restructure` | high | 同上 |
| `260807-resume-audit-stream-route-squash.md` | stream route checkpoint 后 squash 只读审计 | `anthropic-responses-bridge` | high | |
| `260807-resume-audit-systemd-bridge-overlap.md` | systemd 与 bridge 三片路径／hunk 重叠预检 | `UNCLASSIFIED` | high | 同时评审 anthropic-responses-bridge（capability/History/stream）与 systemd-runtime（S3/S4）的集成顺序，无法归单一话题 |
| `260807-resume-audit-systemd-rebuild-replay.md` | systemd new-main rebuild checkpoint 后回放审计 | `systemd-runtime` | high | |
| `260807-resume-audit-systemd-squash-r2.md` | systemd new-main 逐片 squash 回放策略审计 R2 | `systemd-runtime` | high | |
| `260807-resume-backup-port-smoke-execution.md` | 备用端口 smoke 实际执行记录 | `service-cutover` | high | |
| `260807-resume-backup-port-smoke-r2.md` | 备用端口 smoke R2 后续执行计划 | `service-cutover` | high | |
| `260807-resume-backup-port-smoke-r3.md` | 备用端口 smoke R3 后续执行计划 | `service-cutover` | high | |
| `260807-resume-review-backup-port-smoke-r2.md` | 备用端口 smoke R2 独立复评 | `service-cutover` | high | |
| `260807-resume-review-backup-port-smoke-r3.md` | 备用端口 smoke R3 独立复评 | `service-cutover` | high | |
| `260807-resume-review-backup-port-smoke.md` | 备用端口 smoke 恢复计划独立复核 | `service-cutover` | high | |
| `260807-resume-review-capability-evidence.md` | reasoning capability 证据交叉复核 | `anthropic-responses-bridge` | high | |
| `260807-resume-review-capability-squash-evidence-r2.md` | reasoning capability squash evidence 快速复核 | `anthropic-responses-bridge` | high | |
| `260807-resume-review-code-stream-route-r2.md` | Responses stream route 独立代码复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-resume-review-code-stream-route.md` | Responses stream route 独立代码评审 | `anthropic-responses-bridge` | high | |
| `260807-resume-review-implementation-current-r2.md` | Implementation current 独立定向复评 R2 | `documentation-restructure` | high | live 文档真相审计 |
| `260807-resume-review-implementation-current-r3.md` | Implementation current 独立定向复评 R3 | `documentation-restructure` | high | 同上 |
| `260807-resume-review-implementation-current-r4.md` | Implementation current 独立定向复评 R4 | `documentation-restructure` | high | 同上 |
| `260807-resume-review-implementation-current-r5.md` | Implementation current 独立定向复评 R5 | `documentation-restructure` | high | 同上 |
| `260807-resume-review-implementation-current-r6.md` | Implementation current 独立定向复评 R6 | `documentation-restructure` | high | 同上 |
| `260807-resume-review-implementation-current-r7.md` | Implementation current 独立定向复评 R7 | `documentation-restructure` | high | 同上 |
| `260807-resume-review-implementation-post-s3.md` | Implementation post-S3 定向复评 | `documentation-restructure` | high | 同上 |
| `260807-resume-review-main-stream-route.md` | main 上 stream route 合并态定向复核 | `anthropic-responses-bridge` | high | |
| `260807-resume-review-readiness-current-r2.md` | Readiness current 独立定向复评 R2 | `documentation-restructure` | high | live 文档真相审计 |
| `260807-resume-review-readiness-current.md` | Readiness current 独立定向复评 | `documentation-restructure` | high | 同上 |

## 新提出的 slug

无。

## 读不下去的文件

无。全部 37 个文件均可正常打开并读出结论。
