# TUI 历史证据索引

本目录只保存 TUI 的 point-in-time 设计、评审与迁移原件。它们不构成 current behavior authority；当前可观察行为以父目录的 [`../spec.md`](../spec.md) 为准。

## 2604 rewrite 历史原件

| 原件 | 性质与阅读边界 |
|---|---|
| [`2604-rewrite/DESIGN.md`](2604-rewrite/DESIGN.md) | 旧 TUI 总设计；保留 fixed-width frame 等历史 provenance，不替代 current Spec。 |
| [`2604-rewrite/telemetry-observability.md`](2604-rewrite/telemetry-observability.md) | 旧日志/TUI 设计；用于解释只读边界沿革，不作为 current 行为合同。 |
| [`2604-rewrite/lib-survey/SELECTIONS.md`](2604-rewrite/lib-survey/SELECTIONS.md) | 旧库选型总表；解释从 `textual` 转向 `rich.Live` 的历史取舍，不作为 current 依赖裁决。 |

## Function-call grouping 评审与收尾

以下原件记录 2026-09-06 的 function-call grouping 设计、计划、实现、评审与收尾；阅读时以各文件顶部的状态和 reviewed revision 为界。

- [`260906-function-call-grouping-closeout.md`](260906-function-call-grouping-closeout.md)
- [`260906-function-call-grouping-closeout-review.md`](260906-function-call-grouping-closeout-review.md)
- [`260906-function-call-grouping-code-review.md`](260906-function-call-grouping-code-review.md)
- [`260906-function-call-grouping-design-review-2.md`](260906-function-call-grouping-design-review-2.md)
- [`260906-function-call-grouping-plan-review.md`](260906-function-call-grouping-plan-review.md)
- [`260906-function-call-grouping-spec-review.md`](260906-function-call-grouping-spec-review.md)
- [`260906-function-call-grouping-structure-review.md`](260906-function-call-grouping-structure-review.md)
- [`260906-function-call-grouping-structure-review-disposition.md`](260906-function-call-grouping-structure-review-disposition.md)
- [`260906-function-call-grouping-closeout-review-checklist.md`](260906-function-call-grouping-closeout-review-checklist.md)
- [`260906-function-call-grouping-code-review-checklist.md`](260906-function-call-grouping-code-review-checklist.md)
- [`260906-function-call-grouping-design-review-checklist.md`](260906-function-call-grouping-design-review-checklist.md)
- [`260906-function-call-grouping-plan-review-checklist.md`](260906-function-call-grouping-plan-review-checklist.md)
- [`260906-function-call-grouping-spec-review-checklist.md`](260906-function-call-grouping-spec-review-checklist.md)
- [`260906-function-call-grouping-structure-review-checklist.md`](260906-function-call-grouping-structure-review-checklist.md)

## 迁移记录

- [`260908-residual-history-migration.md`](260908-residual-history-migration.md) 是本次 2026-09-08 residual ledger 迁移的 point-in-time migration report。
