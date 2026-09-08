# delivery-keepalive 承重历史证据迁移

- **日期**：2026-09-08
- **范围**：`.dev/docs/delivery-keepalive/` 内的历史归口、引用改写与两条已失效 `tmp` 路径修正。
- **执行依据**：`.dev/docs/dotdev-repository-repair/README.md` 的“先迁证据、再改入站路径”顺序，以及 `subtopics/260908-retirement-reference-map.md` 的 R-11、R-12、R-14、R-15 和第 4 节 keepalive 两项。

## 已迁移原件

| 原位置 | 新位置 | 性质与边界 |
|---|---|---|
| `empty-text-block/reports/260820-review-synthetic-start-fix.md` | [`../history/260820-review-synthetic-start-fix.md`](../history/260820-review-synthetic-start-fix.md) | R-14/R-15 所需的缺陷背景、实测和评审 provenance。其涉及的合成机制与待裁窗口已作废；迁移不将其复活为当前待裁决。 |
| `archived-2604-rewrite/streaming-resilience.md` | [`../history/2604-streaming-resilience.md`](../history/2604-streaming-resilience.md) | R-11/R-12 所需的旧配置键设计意图快照。它是过期设计快照，**不是 current config truth**。 |

新增 [`../history/README.md`](../history/README.md) 固化两份材料的 provenance 边界和 current authority 的所在。

## 已改写的承重引用

- `decisions.md` 的 R-11 与 R-12 从绝对 `.dev/docs/archived-2604-rewrite/...` 代码路径改为指向本主题 `history/2604-streaming-resilience.md` 的相对 Markdown links；说明继续明确该快照不描述当前事实。
- `spec.md` 的 R-14、R-15 及作废原文中的同一历史引用均改为相对链接 `history/260820-review-synthetic-start-fix.md`。作废段的“仅作记录”与“已随机制消失”边界未改变；顶部遗留的“§2.2 尚有待裁”也已更正为它不是 current 未决项。
- `spec.md` 顶部两份曾写为 `../tmp/` 的 keepalive 核对报告已改为现存的主题内 `reports/260820-review-keepalive-rulings.md` 与 `reports/260820-review-keepalive-doc-fixes.md`。两份 reports 没有复制或移动。

## 核对

迁移后应满足：

1. 两份原件仅在 `delivery-keepalive/history/` 的新位置存在；
2. `delivery-keepalive/spec.md` 与 `decisions.md` 不再引用旧 `empty-text-block` 或 `archived-2604-rewrite` 路径；
3. `spec.md` 不再把这两份已有 topic-local reports 说成位于 `tmp/`；
4. 历史原文保持原样，且没有新建 current 待裁决项。
