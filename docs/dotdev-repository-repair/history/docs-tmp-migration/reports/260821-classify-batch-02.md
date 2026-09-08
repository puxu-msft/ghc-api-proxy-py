# 分类批次 02：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：43（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-arbitrate-empty-reasoning.md` | 空 reasoning 语义冲突裁决 | `anthropic-responses-bridge` | high | |
| `260807-arbitrate-nonstream-carrier-dependency.md` | nonstream converter 与 carrier 依赖裁决 | `anthropic-responses-bridge` | high | |
| `260807-arbitrate-stream-request-facts.md` | stream 请求转换事实在 History 的保留裁决 | `anthropic-responses-bridge` | medium | 同时深度涉及 History 存储机制，但裁决对象是 bridge Spec 的 DEGRADE 合同 |
| `260807-arbitrate-user-install-atomicity.md` | rootless installer 三文件原子性裁决 | `systemd-runtime` | high | |
| `260807-audit-acceptance-current.md` | current Acceptance 状态只读审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-archives-worktrees.md` | archive refs／worktrees 清理审计 | `UNCLASSIFIED` | high | 横跨 `anthropic-responses-bridge`（reasoning/liveness/request foundations）与 `systemd-runtime`，是 Git housekeeping 而非单一产品话题 |
| `260807-audit-bridge-next-successor.md` | bridge-next successor 回放审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-copilot-item-identity-squash.md` | Copilot item identity squash 审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-copilot-response-identity-squash.md` | Copilot response identity squash 审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-doc-links.md` | 正式文档相对 Markdown 链接审计 | `documentation-restructure` | high | |
| `260807-audit-docs-commit-boundary.md` | 7 份正式文档提交边界审计 | `documentation-restructure` | high | |
| `260807-audit-docs-latest.md` | 10 份正式文档状态依赖审计 | `documentation-restructure` | high | |
| `260807-audit-four-doc-checkpoint.md` | 四份 living docs checkpoint 审计 | `documentation-restructure` | high | |
| `260807-audit-happy-replay.md` | happy integration 回放预检 | `anthropic-responses-bridge` | high | |
| `260807-audit-integration-commits.md` | bridge foundations 集成提交回放预检 | `anthropic-responses-bridge` | high | |
| `260807-audit-living-checkpoint.md` | living 文档 tracked 修改审计 | `documentation-restructure` | high | |
| `260807-audit-plan-input-identities.md` | Plan 规范输入 identity 审计 | `documentation-restructure` | high | |
| `260807-audit-readme-drift.md` | bridge README 内容漂移审计 | `documentation-restructure` | high | |
| `260807-audit-resident-byte-budget-squash.md` | resident byte budget squash 审计 | `UNCLASSIFIED` | high | 新话题（delivery 内存/字节预算、reservation/lease），现有 slug 均不覆盖，且本批仅 1 个文件，不足 3 个门槛 |
| `260807-audit-semantic-replay-resume.md` | semantic parity 回放现场恢复审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-semantic-replay.md` | semantic parity candidate 最终回放审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-successor-current-preimage.md` | bridge successor current-preimage 审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-successor-replay-resume.md` | bridge successor 回放现场恢复审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-systemd-code-replay-resume.md` | systemd code-only 回放现场恢复审计 | `systemd-runtime` | high | |
| `260807-audit-systemd-next-rebuild.md` | systemd-next 新 main 重建审计 | `systemd-runtime` | high | |
| `260807-audit-systemd-plan-checkpoint.md` | systemd Plan checkpoint 审计 | `systemd-runtime` | high | |
| `260807-audit-systemd-squash.md` | systemd runtime squash 回放审计 | `systemd-runtime` | high | |
| `260807-audit-tmp-naming.md` | `docs/tmp` 命名/覆盖/重复审计 | `documentation-restructure` | high | |
| `260807-audit-token-identity-squash.md` | Copilot token identity headers squash 审计 | `UNCLASSIFIED` | high | 新话题（上游 token exchange 身份头，非 Responses 桥语义），现有 slug 均不覆盖，本批仅 1 个文件 |
| `260807-audit-usage-replay.md` | non-stream usage main 回放审计 | `anthropic-responses-bridge` | high | |
| `260807-audit-worktree-cleanup-r2.md` | worktree／branch 清理清单复审 R2 | `UNCLASSIFIED` | high | 横跨 `anthropic-responses-bridge`（foundations/happy/usage）与 `systemd-runtime`，Git housekeeping |
| `260807-backup-port-smoke-resume.md` | 备用端口 smoke 设计与恢复验收 | `service-cutover` | high | |
| `260807-current-service-cutover-inventory.md` | 当前 Claude 入口服务与可回滚 cutover 清单 | `service-cutover` | high | |
| `260807-doc-state-dependency-dag.md` | 7 份正式文档状态依赖 DAG | `documentation-restructure` | high | |
| `260807-final-backup-port-smoke-r2.md` | 备用端口关键主路径 smoke R2 | `service-cutover` | high | |
| `260807-final-backup-port-smoke-r3.md` | 备用端口关键主路径 smoke R3 | `service-cutover` | high | |
| `260807-final-backup-port-smoke.md` | 备用端口 smoke 最终执行记录（INCONCLUSIVE） | `service-cutover` | high | |
| `260807-final-happy-replay-gate.md` | current main → happy 回放最终门禁复核 | `anthropic-responses-bridge` | high | |
| `260807-final-review-current-main.md` | current main 最终定向代码复核 | `UNCLASSIFIED` | high | 同时审 capability/History/stream（bridge）与 S3/S4（systemd-runtime），二者并重，跨话题 |
| `260807-final-review-stream-facts-main.md` | stream facts 最终定向复核 | `anthropic-responses-bridge` | high | |
| `260807-final-semantic-replay-gate.md` | semantic parity integration 最终回放门 | `anthropic-responses-bridge` | high | |
| `260807-final-successor-replay-gate.md` | bridge successor 最终逐片回放门 | `anthropic-responses-bridge` | high | |
| `260807-final-systemd-next-preimage-r2.md` | systemd-next current-main preimage 最终复核 R2 | `systemd-runtime` | high | |

## 新提出的 slug

无。`260807-audit-resident-byte-budget-squash.md`（delivery 内存/字节预算）与 `260807-audit-token-identity-squash.md`（Copilot token 身份头）本批各只出现 1 个文件，覆盖不足 3 个门槛，按判据判 `UNCLASSIFIED`，不新开 slug。

## 读不下去的文件

无。43 个文件均可正常打开阅读，无空文件、乱码或超长读不完的情况。
