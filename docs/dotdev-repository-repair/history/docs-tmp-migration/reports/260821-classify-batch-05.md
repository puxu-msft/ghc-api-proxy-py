# 分类批次 05：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：40（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-review-code-happy-path.md` | happy-path 四切片合并态代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-nonstream-response-r2.md` | nonstream identity 修复定向复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-code-nonstream-response.md` | nonstream happy-path 骨架代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-nonstream-usage.md` | nonstream usage details 代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-route-happy-r2.md` | route happy-path header 泄漏复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-code-route-happy-r3.md` | route happy-path finalizer 复评 R3 | `anthropic-responses-bridge` | high | |
| `260807-review-code-route-happy.md` | Responses route happy-path 代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-route-policy.md` | route policy 独立代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-semantic-parity-r2.md` | semantic parity 独立代码复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-code-semantic-parity.md` | Responses semantic parity 代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-stream-parser-r2.md` | stream parser 骨架定向复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-code-stream-parser.md` | Responses stream parser 代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-code-systemd-next.md` | systemd-next 合并态代码评审 | `systemd-runtime` | high | |
| `260807-review-code-systemd-runtime-r2.md` | systemd cgroup runtime 定向复评 R2 | `systemd-runtime` | high | |
| `260807-review-code-systemd-runtime-r3.md` | systemd cgroup runtime 定向复评 R3 | `systemd-runtime` | high | |
| `260807-review-code-systemd-runtime-r4.md` | systemd cgroup runtime 独立终审 R4 | `systemd-runtime` | high | |
| `260807-review-code-systemd-runtime.md` | systemd cgroup runtime 首轮代码评审 | `systemd-runtime` | high | |
| `260807-review-code-systemd-user-install.md` | rootless systemd user installer 评审 | `systemd-runtime` | high | |
| `260807-review-copilot-item-identity-r2.md` | Copilot item identity 定向终审 R2 | `anthropic-responses-bridge` | high | Responses stream parser 的 item identity 严格性 |
| `260807-review-copilot-item-identity-wip.md` | Copilot item identity WIP 只读预审 | `anthropic-responses-bridge` | high | |
| `260807-review-copilot-response-identity-r2.md` | Copilot response identity 定向终审 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-copilot-response-identity-wip.md` | Copilot response identity WIP 预审 | `anthropic-responses-bridge` | high | |
| `260807-review-cutover-current-r5.md` | cutover Plan／Readiness 联合复评 R5 | `service-cutover` | high | |
| `260807-review-deployment-docs-r3.md` | systemd／cutover living docs 联合复评 R3 | `UNCLASSIFIED` | high | 同一份报告联合评审 `systemd-runtime/plan.md` 与 `service-cutover/{plan,readiness}.md`，判不出单一 owner，横跨 `systemd-runtime`、`service-cutover` |
| `260807-review-deployment-plans-r2.md` | cutover／systemd living plans 联合复评 R2 | `UNCLASSIFIED` | high | 同一份报告联合评审 `service-cutover/plan.md` 与 `systemd-runtime/plan.md` 的一致性，判不出单一 owner，横跨 `systemd-runtime`、`service-cutover` |
| `260807-review-doc-bootstrap-protocol.md` | 文档治理 bootstrap generation 设计预审 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r10.md` | 文档重组 living Plan 定向复评 R10 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r11.md` | 文档重组 living Plan 定向终审 R11 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r4.md` | 文档重组计划独立终审 R4 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r5.md` | 文档重组计划独立定向复评 R5 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r6.md` | 文档重组计划独立终审 R6 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r7.md` | 文档重组计划独立定向终审 R7 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r8.md` | 文档重组计划独立定向复评 R8 | `documentation-restructure` | high | |
| `260807-review-doc-migration-plan-r9.md` | 文档重组 living Plan 独立定向复评 R9 | `documentation-restructure` | high | |
| `260807-review-docs-merged-r2.md` | bridge 正式文档 merged-state 终审 R2 | `anthropic-responses-bridge` | high | 主体是 bridge 7 份正式文档；附带核对 `documentation-restructure/plan.md` 的 bootstrap，但被评对象以 bridge 文档为主 |
| `260807-review-final-backup-port-smoke-r2.md` | 备用端口关键主路径 smoke 快速复核 R2 | `service-cutover` | high | |
| `260807-review-final-backup-port-smoke-r3.md` | 备用端口关键主路径 smoke 快速复核 R3 | `service-cutover` | high | |
| `260807-review-happy-integration-strategy.md` | happy-path 四切片集成策略只读预审 | `anthropic-responses-bridge` | high | |
| `260807-review-identity-living-checkpoint.md` | identity living checkpoint 联合定向复评 | `UNCLASSIFIED` | high | 同一份报告联合评审 `anthropic-responses-bridge/implementation.md` 与 `service-cutover/readiness.md` 的状态一致性，判不出单一 owner，横跨 `anthropic-responses-bridge`、`service-cutover` |
| `260807-review-implementation-checkpoint.md` | Implementation stable checkpoint 定向复评 | `anthropic-responses-bridge` | high | 评审对象为 `docs/agents/anthropic-responses-bridge/implementation.md` |

## 新提出的 slug

无。

## 读不下去的文件

无。
