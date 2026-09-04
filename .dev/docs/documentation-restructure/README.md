# 文档整理状态

旧的《文档渐进式重组实施计划》已归档至 [archive-260808/plan.md](archive-260808/plan.md)。它记录了早期对 `docs/2604-rewrite/`、文档分层和临时报告归纳的讨论，但其中 generation、closure certificate、ledger checker 和受管 action gate 等证明治理方案已终止，不得再作为当前执行计划。

当前文档纪律由项目规则 [`.claude/rules/00-development-workflow.md`](../../../.claude/rules/00-development-workflow.md) 承载：

- `docs/` 保存 live conclusions；
- `../<topic>/` 保存进行中的 Spec、Plan、Research、Acceptance 与状态文档；
- `../<topic>/archive-<date>/` 保存历史过程和 point-in-time evidence index；
- `../tmp/` 只交换临时报告，新文件使用 `YYMMDD-` 前缀；结论及时归纳进 live docs；
- 先直接解决产品任务，不为普通文档整理建设 manifest、certificate、generation 或验证状态机；
- 不批量重写历史评审报告，必要时只建立归档索引和当前结论载体。

## 尚未完成的正确目标

以下工作仍有效，但按普通增量文档维护完成，不再执行旧控制面计划：

1. 为 live docs 提供清晰入口，减少同一 current state 的重复副本。
2. 将已完成或被取代的开发材料移入对应主题的 `archive-<date>/`。
3. 保留仍定义外部合同的 Spec 和 Acceptance，不因“已实现”而归档。
4. 从旧 `docs/2604-rewrite/` 提炼仍然有效的当前结论，再逐主题归档历史来源。
5. 定期检查相对链接、文档提到的真实代码符号和明显陈旧的“待做／下一步”陈述。

易变产品状态继续由各主题自己的 living 文档维护；本文不建立第二个项目状态源。
