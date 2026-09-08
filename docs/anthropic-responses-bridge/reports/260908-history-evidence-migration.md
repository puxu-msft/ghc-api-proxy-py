# R-06 历史证据迁移

日期：2026-09-08
范围：`anthropic-responses-bridge` 的 R-06，及获明确授权移动的单一历史原件。

## 已完成的更改

1. 将 `.dev/docs/archived-2604-rewrite/history-system.md` 移至 [`../history/2604-history-system.md`](../history/2604-history-system.md)，保留原件内容作为可追溯的设计 provenance。
2. 新增 [`../history/README.md`](../history/README.md)，明确该原件是已过期目标设计，不能作为用户裁决或 current authority；同时列明 current architecture 与行为 authority 的位置。
3. 更新 [`../architecture.md`](../architecture.md) 的 History 投影段：默认持久化约束现在由该段 current architecture 本身明示为权威，并将旧路径改为新的相对 Markdown link。该链接只说明原件的 provenance。

## 判断依据

- repository repair README 要求先迁移承重证据、再改写入站路径，并禁止把 point-in-time 或旧设计改写成 current 状态。
- retirement reference map 的 R-06 判定旧 `history-system.md` 是支撑“轻量终态一次写入”的旧目标设计，而不是一手用户裁决；它要求消除对 `archived-2604-rewrite` 的 current authority 依赖。
- Architecture 已完整列出默认持久化的字段与排除项，因此它能够独立承载当前架构约束；历史原件只补充设计沿革。

## 未做事项

- 未修改历史 reports 中的旧路径文字：它们是 point-in-time 记录，不是 R-06 的 current 入站链接，迁移不应倒改其历史语境。
- 未迁移或改写其他 retirement-map 条目，也未删除任何目录或文件。
- 未修改代码、测试、仓库配置或其它主题文档；未执行 `git add`、commit 或 push。

## R-07 至 R-10：hosted-web-search 外部改链

在 `hosted-web-search/260908-external-reference-migration-note.md` 确认的三个 canonical targets 落盘后，已更新 [`../hosted-web-search-spec.md`](../hosted-web-search-spec.md)：

1. §8.2 的“不在 400 后剥离并重试”沿革改链至[历史 tool-use 边界](../../hosted-web-search/history/2604-tool-use.md)，并明确该背景不是 current authority 或一手用户逐字裁决。
2. §15 的三个旧 `archived-2604-rewrite` targets 分别改为[历史 tool-use 边界](../../hosted-web-search/history/2604-tool-use.md)、[历史 Anthropic compatibility 背景](../../hosted-web-search/history/2604-anthropic-compat.md)与[历史 hooks 设计背景](../../hosted-web-search/history/2604-hooks-system.md)。
3. §15 的标签由“当前已实现边界”改为“历史设计背景（不作为 current authority）”，故现行规则仍由本 Spec 承载。

已逐一检查上述三个 target 存在，并验证本段与 `hosted-web-search-spec.md` 的四个新 Markdown links 均可解析。

## MSR-02 / R-13：文档整理状态 owner 改链

[`../implementation.md`](../implementation.md) 的“文档整理状态”行现链接到 [`../../dotdev-repository-repair/README.md`](../../dotdev-repository-repair/README.md)，不再依赖已退役候选 `documentation-restructure` 的 README。文案明确该 repair README 只拥有文档整理状态、迁移顺序与历史材料归档的协调职责；产品行为 authority 仍以各主题的 current Spec 为准。已检查该相对 Markdown target 存在且可解析。
