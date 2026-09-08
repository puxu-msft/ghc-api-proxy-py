# 分类批次 06：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：40（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-review-implementation-current-r2.md` | bridge implementation living doc 定向复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-r3.md` | bridge implementation living doc 定向复评 R3 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-r4.md` | bridge implementation living doc 定向复评 R4 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-r5.md` | bridge implementation living doc 定向复评 R5 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-r6.md` | bridge implementation living doc 定向复评 R6 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-r7.md` | bridge implementation living doc 定向复评 R7 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-r8.md` | bridge implementation living doc 独立复评 R8 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current-resume.md` | bridge implementation WSL 重启后恢复复评 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-current.md` | bridge implementation living doc 定向评审（首轮） | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-living-plan.md` | bridge implementation living plan 定向评审 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-main-happy.md` | bridge implementation main／happy 定向复评 | `anthropic-responses-bridge` | high | |
| `260807-review-implementation-stream-facts.md` | bridge implementation stream facts 定向复评 | `anthropic-responses-bridge` | high | |
| `260807-review-living-after-main-replay-r2.md` | 联合复评 implementation＋systemd plan＋readiness 三份 living 文档 | `UNCLASSIFIED` | medium | 三份文档权重相当，横跨 `anthropic-responses-bridge`／`systemd-runtime`／`service-cutover`，判不出唯一 owner |
| `260807-review-living-bridge-docs-r2.md` | bridge README＋implementation 联合复评 R2 | `anthropic-responses-bridge` | high | |
| `260807-review-living-bridge-docs-r3.md` | bridge README＋implementation 联合定向复评 R3 | `anthropic-responses-bridge` | high | |
| `260807-review-living-bridge-docs.md` | bridge README＋implementation 联合终审 | `anthropic-responses-bridge` | high | |
| `260807-review-main-foundations-systemd.md` | current main foundations＋systemd merged-state 评审 | `UNCLASSIFIED` | medium | 同时评审 reasoning/converter/liveness（bridge）与 CLI fd/systemd units（systemd-runtime），major 发现横跨 implementation.md／README.md／service-cutover plan.md 三份文档 |
| `260807-review-main-happy-usage.md` | current main happy／usage merged-state 独立评审 | `anthropic-responses-bridge` | high | reasoning carrier、stream parser、route policy、usage facts 均是 bridge 主链路 |
| `260807-review-main-network-retry.md` | current main headers-before network retry 定向复核 | `anthropic-responses-bridge` | high | Responses upstream 重试，属于 bridge 请求管道 |
| `260807-review-main-resident-budget.md` | current main resident byte budget 合并态复核 | `anthropic-responses-bridge` | medium | resident primitive／delivery reservation 是 bridge block delivery 的背压机制，无独立现有 slug 覆盖 |
| `260807-review-main-successor-resume.md` | current main semantic／route／block merged-state 代码评审 | `anthropic-responses-bridge` | high | |
| `260807-review-network-retry-integration.md` | network retry integration 只读预审 | `anthropic-responses-bridge` | high | Responses retry 接入 pipeline/executor，bridge 请求管道 |
| `260807-review-network-retry-wip.md` | Responses network retry WIP 只读预审 | `anthropic-responses-bridge` | high | |
| `260807-review-readiness-current-r2.md` | service-cutover readiness 独立复评 R2 | `service-cutover` | high | |
| `260807-review-readiness-current-r3.md` | service-cutover readiness 独立复评 R3 | `service-cutover` | high | |
| `260807-review-readiness-current-r4.md` | service-cutover readiness 独立复评 R4 | `service-cutover` | high | |
| `260807-review-readiness-current-r5.md` | service-cutover readiness 定向独立复评 R5 | `service-cutover` | high | |
| `260807-review-readiness-current-r6.md` | service-cutover readiness 定向独立复评 R6 | `service-cutover` | high | |
| `260807-review-readiness-current-r8.md` | service-cutover readiness 独立复评 R8 | `service-cutover` | high | |
| `260807-review-readiness-current-resume.md` | service-cutover readiness checkpoint 恢复确认 | `service-cutover` | high | |
| `260807-review-readiness-current.md` | service-cutover readiness 定向复评（首轮） | `service-cutover` | high | |
| `260807-review-readiness-stream-facts.md` | readiness stream facts 定向复评 | `service-cutover` | high | |
| `260807-review-real-copilot-canary.md` | real Copilot canary 独立快速复核 | `anthropic-responses-bridge` | medium | 复核认证根因、response/item identity 修复、stream event sequence，均是 bridge 核心行为的实证 |
| `260807-review-research-external-change.md` | bridge research.md 外部变化只读复核 | `anthropic-responses-bridge` | high | |
| `260807-review-reservation-wiring-living.md` | implementation＋readiness resident wiring 联合定向复评 | `UNCLASSIFIED` | medium | 同时复评 bridge implementation.md 与 service-cutover readiness.md 两份 living 文档，权重相当 |
| `260807-review-reservation-wiring-wip.md` | reservation wiring WIP 只读预审 | `anthropic-responses-bridge` | medium | 改动 settings/server/routes/delivery，属于 bridge delivery 背压接线代码 |
| `260807-review-resident-byte-budget-r2.md` | resident byte budget 定向独立终审 R2 | `anthropic-responses-bridge` | medium | 同上，resident primitive 是 bridge block delivery 的背压原语 |
| `260807-review-resident-byte-budget-r3.md` | resident byte budget 定向独立终审 R3 | `anthropic-responses-bridge` | medium | |
| `260807-review-resident-byte-budget.md` | resident byte budget 定向独立评审（首轮） | `anthropic-responses-bridge` | medium | |
| `260807-review-resident-living-checkpoint.md` | implementation＋readiness resident living 联合定向复评 | `UNCLASSIFIED` | medium | 同时复评 bridge implementation.md 与 service-cutover readiness.md 两份 living 文档，权重相当 |

## 新提出的 slug

无。考虑过为 resident byte budget／背压原语（`260807-review-main-resident-budget.md`、`260807-review-reservation-wiring-wip.md`、`260807-review-resident-byte-budget*.md` 共 5 个文件）单独提出 `resident-byte-budget` slug，但该原语只是 `anthropic-responses-bridge` 的 block delivery 背压机制的一部分（改动集中在 `src/app/delivery/**`、`src/app/routes/anthropic.py`），`.dev/docs/` 与 `docs/agents/` 均无独立话题目录承接它，故仍归入 `anthropic-responses-bridge`，判为 medium 置信度并在备注中说明。

## 读不下去的文件

无。全部 40 个文件均可正常打开阅读（长度 18～77 行不等），标题、评审范围、verdict 与事实性发现段落足以判断话题归属。
