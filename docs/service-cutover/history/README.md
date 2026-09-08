# Service cutover history

本目录保存 service-cutover 的点时 checkpoint 与评审证据。原件按归档时的文件名保留，正文中的当时路径、结论、环境与 verdict 都是历史记录，不因后续状态变化而改写。

这些文档**不能**作为 current plan、readiness、执行规则或生产授权的依据。当前 cutover 合同与状态分别以 [`../plan.md`](../plan.md) 和 [`../readiness.md`](../readiness.md) 为准；它们覆盖旧报告中任何已过期的计划、观察或结论。

## 本次迁入

- [`260807-review-deployment-docs-r3.md`](260807-review-deployment-docs-r3.md)：deployment living docs 的联合复评 checkpoint。
- [`260807-review-deployment-plans-r2.md`](260807-review-deployment-plans-r2.md)：deployment living plans 的定向复评 checkpoint。
- [`260824-acceptance-cut-and-new-skill-review.md`](260824-acceptance-cut-and-new-skill-review.md)：acceptance 文档切除与新 skill 的评审证据；其涉及 cutover 文档的部分仅保留为点时证据。

迁移范围与 SHA-256 完整性记录见 [`../reports/260908-tmp-history-migration.md`](../reports/260908-tmp-history-migration.md)。
