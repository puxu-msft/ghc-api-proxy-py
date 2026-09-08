# 分类批次 07：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：40（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-review-retry-living-checkpoint.md` | 联合复评 retry 实现与 cutover readiness | `anthropic-responses-bridge` | medium | 同时评审 implementation.md（retry 实现）与 service-cutover/readiness.md；按被改对象（retry 实现属 bridge）归类，横跨 service-cutover |
| `260807-review-service-cutover-docs-r2.md` | Plan／Readiness 联合终审 R2 | `service-cutover` | high | |
| `260807-review-service-cutover-docs-r3.md` | Plan／Readiness 联合复评 R3 | `service-cutover` | high | |
| `260807-review-service-cutover-docs.md` | Plan／Readiness 联合评审首轮 | `service-cutover` | high | |
| `260807-review-service-cutover-plan-r2.md` | Plan 独立复评 R2，4 major 关闭 | `service-cutover` | high | |
| `260807-review-service-cutover-plan-r3.md` | Plan 独立定向复评 R3 | `service-cutover` | high | |
| `260807-review-service-cutover-plan-r4.md` | Plan 快速复评 R4 | `service-cutover` | high | |
| `260807-review-service-cutover-plan.md` | Plan 独立评审首轮，4 major | `service-cutover` | high | |
| `260807-review-spec-acceptance-current.md` | Spec／Acceptance 联合终审 | `anthropic-responses-bridge` | high | |
| `260807-review-spec-carrier-dual-format.md` | Spec carrier 双格式定向评审 | `anthropic-responses-bridge` | high | |
| `260807-review-spec-carrier-final.md` | Spec carrier 终审 | `anthropic-responses-bridge` | high | |
| `260807-review-stream-facts-checkpoint.md` | 联合复评 stream facts 与 cutover readiness | `anthropic-responses-bridge` | medium | 同时评审 implementation.md（stream request facts）与 service-cutover/readiness.md；横跨 service-cutover |
| `260807-review-stream-request-facts-r2.md` | Stream request facts 独立终审 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-stream-request-facts.md` | Stream request facts 只读预审，1 major | `anthropic-responses-bridge` | high | |
| `260807-review-systemd-code-only.md` | systemd code-only 合并态评审 | `systemd-runtime` | high | |
| `260807-review-systemd-plan-current-resume.md` | systemd Plan current-resume 评审 | `systemd-runtime` | high | |
| `260807-review-systemd-plan-post-s4.md` | systemd Plan S4 后定向复评 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r2.md` | systemd runtime Plan 复评 R2 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r3.md` | systemd runtime Plan 复评 R3 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r4.md` | systemd runtime Plan 联合终审 R4 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r5.md` | systemd runtime Plan 复评 R5 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r6.md` | systemd runtime Plan 复评 R6 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r7.md` | systemd runtime Plan 复评 R7 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan-r8.md` | systemd runtime Plan 独立复评 R8 | `systemd-runtime` | high | |
| `260807-review-systemd-runtime-plan.md` | systemd runtime Plan 独立评审首轮 | `systemd-runtime` | high | |
| `260807-review-systemd-user-manager-diagnosis.md` | user-manager 隔离诊断快速复核 | `systemd-runtime` | high | |
| `260807-review-token-exchange-identity-r2.md` | Token exchange identity 定向终审 R2 | `UNCLASSIFIED` | high | GitHub Copilot token exchange 身份头修复，无候选 slug 覆盖；本批次仅 2 个同题文件，不足 3 个不新开 slug |
| `260807-review-token-exchange-identity.md` | Token exchange identity 只读评审，1 major | `UNCLASSIFIED` | high | 同上 |
| `260807-review-worktree-cleanup-plan.md` | worktree／branch 清理计划快速复核 | `UNCLASSIFIED` | high | 一次性仓库杂务，无候选 slug 覆盖；本批次仅 2 个同题文件 |
| `260807-review-worktree-cleanup-r2.md` | worktree／branch 清理清单复核 R2 | `UNCLASSIFIED` | high | 同上 |
| `260807-simulate-happy-first-replay.md` | happy 第一提交回放模拟 | `anthropic-responses-bridge` | high | |
| `260807-systemd-installer-rebuild-resume.md` | S4 rootless installer 重建恢复报告 | `systemd-runtime` | high | |
| `260807-systemd-socket-feasibility.md` | socket activation／cgroup v2 可行性复核 | `systemd-runtime` | high | |
| `260807-systemd-user-manager-smoke.md` | user-manager／cgroup 隔离可行性验证 | `systemd-runtime` | high | |
| `260807-tmp-distillation-matrix.md` | `docs/tmp` 正式文档归纳矩阵 | `documentation-restructure` | high | |
| `260807-verify-bridge-next.md` | bridge-next 独立验收，1 blocker | `anthropic-responses-bridge` | high | |
| `260807-verify-bridge-successor.md` | bridge successor 独立验收 PASS | `anthropic-responses-bridge` | high | |
| `260807-verify-carrier-v2-r2.md` | reasoning carrier v2 独立复验 R2 | `anthropic-responses-bridge` | high | |
| `260807-verify-happy-path.md` | bridge happy-path 独立验收 | `anthropic-responses-bridge` | high | |
| `260807-verify-main-foundations-systemd.md` | main foundations／systemd 独立验收 | `UNCLASSIFIED` | medium | 一半验收 bridge foundations（reasoning／request converter／liveness），一半验收 systemd（CLI inherited fd／HTTP／SIGTERM／状态路径），权重相当难以归一 |

## 新提出的 slug

无。token-exchange-identity 与 worktree-cleanup 两组各自只在本批次出现 2 个文件，均不足 3 个覆盖门槛，按判据判 `UNCLASSIFIED`，不新开 slug。

## 读不下去的文件

无。40 个文件均完整读取（大多数在 20-110 行之间，最长 188 行），标题、评审范围、总体 verdict 与事实性发现均清晰可判。
