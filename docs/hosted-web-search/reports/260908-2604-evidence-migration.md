# 2604 历史证据迁移报告

日期：2026-09-08
范围：R-07 至 R-10；只处理 `archived-2604-rewrite` 中获授权的三份文件，以及 `hosted-web-search/` 内的迁移说明。

## 完成的迁移

下列旧设计快照已逐字移动到 Hosted web search 的唯一 canonical history destination。迁移前后的 SHA-256 相同，证明移动没有改写原件。

| R | 原位置 | 新 canonical path | SHA-256 | 分类 |
|---|---|---|---|---|
| R-07、R-08 | `../archived-2604-rewrite/tool-use.md` | [`../history/2604-tool-use.md`](../history/2604-tool-use.md) | `e453417f17effdd25747f95a3888845a6c8f8c9ba0d256db9b2ed5f6c82b08ba` | 旧 tool-use 设计边界与 provenance，不是 current authority。 |
| R-09 | `../archived-2604-rewrite/anthropic-compat.md` | [`../history/2604-anthropic-compat.md`](../history/2604-anthropic-compat.md) | `f29967393270880c948d0fe66440e2cd9aab4db83771d929e4d7d831c316557a` | 旧 Anthropic 兼容矩阵/请求整形背景，不是 current authority。 |
| R-10 | `../archived-2604-rewrite/hooks-system.md` | [`../history/2604-hooks-system.md`](../history/2604-hooks-system.md) | `6cac11b0391dc6707ab8089a7cdfc5e3f83e60c714dc651d21b8fe89c8422ba8` | 旧 hooks 生命周期/阶段设计背景，不是 current authority。 |

[`../history/README.md`](../history/README.md) 为三份原件逐项声明了来源、适用边界、current carrier 和“不得升级为用户裁决”的限制。原件正文及其中的旧布局相对链接未改写，防止把时点快照伪造成当前文档。

## 引用处置

R-07 至 R-10 已知的 current consumer 是外部主题 `../anthropic-responses-bridge/hosted-web-search-spec.md`：§8.2 的一个 code span，以及 §15 的三条 Markdown link。该文件不在本次所有权内，故未修改。精确的旧 target、新 canonical path、引用位置和所需 authority 文案限制已记录在 [`../260908-external-reference-migration-note.md`](../260908-external-reference-migration-note.md)，供专门的改链任务原子处理。

扫描 `hosted-web-search/` 的活文档后，`status.md` 不含三个旧 target，因而没有本主题可改写的 current reference。既有 `reports/` 命中属于报告原件中的历史叙述，按报告保真规则未改；它们不构成 current dependency，也不应因本次迁移被回写。

## 校验结果

- 三个授权源路径均已不存在，三个 history destination 均存在。
- 三份 destination 的 SHA-256 与移动前记录逐项一致。
- 未修改 `anthropic-responses-bridge/hosted-web-search-spec.md`，也未触及任何不在本次授权内的 archived 文件。
- 本次迁移没有删除文件；旧路径由逐字移动替换为 Hosted web search 的 canonical history path。
