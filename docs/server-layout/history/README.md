# 本主题承接的历史材料

本目录保存迁入 `server-layout` 的时点实施与评审材料。它们保留当时的观察、命令、提交和审查结论，**不是**当前实现状态、现行设计决策或永久产品裁决的权威来源；判断当前状态时应回到本主题的现行文档与代码。

| 材料 | 原始位置 | 承接内容 | 与同组材料的关系 |
|---|---|---|---|
| [`260822-cli-and-module-move-closeout.md`](260822-cli-and-module-move-closeout.md) | `.dev/docs/tmp/260822-cli-and-module-move-closeout.md` | 2026-08-21 至 08-22 的 CLI 切分与模块迁移会话 closeout | 被下列两份独立评审核查 |
| [`260822-review-closeout-facts.md`](260822-review-closeout-facts.md) | `.dev/docs/tmp/260822-review-closeout-facts.md` | 对 closeout 中可验证断言的独立事实核查 | 对应同组 closeout 的 facts review |
| [`260822-review-closeout-omissions.md`](260822-review-closeout-omissions.md) | `.dev/docs/tmp/260822-review-closeout-omissions.md` | 对同一 closeout 的遗漏与反向证据评审 | 对应同组 closeout 的 omissions review |
| [`architecture-audit/reports/`](architecture-audit/reports/) 下 9 份材料 | `.dev/docs/architecture-audit/reports/` | 2026-08-14 的模块边界、依赖图、重复实现、生命周期、测试结构、typing 与综合审计 | 同属 EF-ARCH；保留审计底稿与综合结论的完整时点证据链 |
| [`test-infrastructure/reports/`](test-infrastructure/reports/) 下 3 份材料 | `.dev/docs/test-infrastructure/reports/` | 2026-08-18 至 08-20 的 vcrpy PoC、测试卫生缺陷与 unit+smoke 合跑 hang 调查 | 同属 EF-TEST；保留当时实验和诊断，不将其提升为现行测试合同 |

三份材料于 2026-09-08 原子迁入，以保留 closeout、facts 与 omissions 的原件—评审关联。其正文内保留的旧 `.dev/docs/tmp/` 路径仅说明当时位置，不构成现行链接或权威声明。

上述 `architecture-audit` 与 `test-infrastructure` 材料于 2026-09-08 依 candidate residual disposition ledger 迁入；其旧主题路径仅是原始来源，正文内的旧路径和时点结论不构成 current authority。它们记录的 2026-08 观察、探针、测试规模、提交状态与评审结论均受当时工作树边界限制；判断当前实现、现行设计决策或测试合同，仍须以 `server-layout` 的现行文档、当前代码和现行测试为准。
