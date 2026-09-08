# 2604 Hosted web search 历史证据：外部改链说明

日期：2026-09-08

本说明只记录需要由外部文档所有者执行的改链，避免本主题迁移工作修改不在其所有权内的 [`../anthropic-responses-bridge/hosted-web-search-spec.md`](../anthropic-responses-bridge/hosted-web-search-spec.md)。该 Spec 仍是 current authority；下列历史文件只提供 provenance/background，不能被改链文案表述成 current authority 或一手用户逐字裁决。

| 外部引用方 | 现有位置 | 旧 target | 应替换为的 canonical path（相对引用方） | 必须保留的限定 |
|---|---|---|---|---|
| `../anthropic-responses-bridge/hosted-web-search-spec.md` | §8.2，当前约第 323 行 | `../archived-2604-rewrite/tool-use.md:23` | `../hosted-web-search/history/2604-tool-use.md:23` | 将它称作“不在 400 后剥离并重试”的历史设计边界/provenance；现行规则的 authority 仍是该 Spec 条款，不能称旧稿为已核实的一手用户裁决。 |
| `../anthropic-responses-bridge/hosted-web-search-spec.md` | §15，当前约第 545 行 | `../archived-2604-rewrite/tool-use.md` | `../hosted-web-search/history/2604-tool-use.md` | link 文案明确“历史 tool-use 边界”，不再列入“当前已实现边界”。 |
| `../anthropic-responses-bridge/hosted-web-search-spec.md` | §15，当前约第 545 行 | `../archived-2604-rewrite/anthropic-compat.md` | `../hosted-web-search/history/2604-anthropic-compat.md` | link 文案明确“历史 Anthropic compatibility 背景”，不称 current compatibility contract。 |
| `../anthropic-responses-bridge/hosted-web-search-spec.md` | §15，当前约第 545 行 | `../archived-2604-rewrite/hooks-system.md` | `../hosted-web-search/history/2604-hooks-system.md` | link 文案明确“历史 hooks 设计背景”；若 Spec 自足，也可移除该证据项，但无论选择何者都不得保留旧 target。 |

本主题自己的活文档 `status.md` 不含上述三个旧 target，因此本次没有可在所有权内改写的 current 自引用。`reports/` 下的既有命中是时点报告原件，按其保真边界保持原样；它们不构成 current dependency。
