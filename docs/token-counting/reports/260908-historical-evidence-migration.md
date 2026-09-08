# Token-counting / TUI 历史证据迁移

**日期**：2026-09-08。**依据**：`dotdev-repository-repair/subtopics/260908-retirement-reference-map.md` 的 R-18 与第 4 节。**范围**：只迁移本文件列出的 5 份原件，并在同一变更中改写两个允许的 current/living 引用方；未删除内容、未改写历史原件的事实、结论、frontmatter 或证据等级。

## 已移动的 canonical 原件

| 原位置 | canonical 位置 | 保留的边界 |
|---|---|---|
| `../count-tokens/reports/260820-review-count-tokens-shared-pipeline.md` | `../token-counting/history/260820-review-count-tokens-shared-pipeline.md` | R-18 所指的更早共享 pipeline 点时证据；不成为 TUI authority。 |
| `../tmp/260906-buffered-chat-local-tokenizer-analysis.md` | `history/260906-buffered-chat-local-tokenizer-analysis.md` | settled 综合分析；4.927230× 是重建前提下的结论，且不把 local estimate 写成 overflow 的已证根因。 |
| `../tmp/260906-buffered-chat-completions-transcript-evidence.md` | `history/260906-buffered-chat-completions-transcript-evidence.md` | 保留 `in-review` 状态、transcript/request-log hash 与“强烈推断但非 cryptographic identity”边界。 |
| `../tmp/260906-buffered-chat-completions-transcript-evidence-erratum.md` | `history/260906-buffered-chat-completions-transcript-evidence-erratum.md` | 与被勘误原件作为一组迁移；保留 ciphertext-only 与完整 reasoning-item contribution 的数字区分。 |
| `../tmp/260906-local-tokenizer-code-audit.md` | `history/260906-local-tokenizer-code-audit.md` | 保留 `in-review` 状态及 8 major / 4 minor 的点时审计结论；不升级为 living Spec。 |

## 已改写的链接

| 引用方 | 原子旧 target | 新 canonical target |
|---|---|---|
| `../tui/deferred.md` §4 来源（R-18） | `../count-tokens/reports/260820-review-count-tokens-shared-pipeline.md:72` | `../token-counting/history/260820-review-count-tokens-shared-pipeline.md:72` |
| `README.md`「点时调查与勘误」 | `../tmp/260906-buffered-chat-local-tokenizer-analysis.md` | `history/260906-buffered-chat-local-tokenizer-analysis.md` |
| `README.md`「点时调查与勘误」 | `../tmp/260906-buffered-chat-completions-transcript-evidence.md` | `history/260906-buffered-chat-completions-transcript-evidence.md` |
| `README.md`「点时调查与勘误」 | `../tmp/260906-buffered-chat-completions-transcript-evidence-erratum.md` | `history/260906-buffered-chat-completions-transcript-evidence-erratum.md` |
| `README.md`「点时调查与勘误」 | `../tmp/260906-local-tokenizer-code-audit.md` | `history/260906-local-tokenizer-code-audit.md` |

## 完成条件

- 5 个 canonical 原件均位于 `token-counting/history/`，原位置不存在。
- transcript evidence 与其 erratum 同时位于新位置；两份原件的状态与事实边界未改。
- R-18 的 TUI 跨主题引用与 README 的 4 个 Markdown links 均解析至 canonical 位置。
