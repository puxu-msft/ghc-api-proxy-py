# Token-counting 历史证据索引

本目录只保存 point-in-time 调查、评审、勘误与已被 current Spec/status 取代的实施证据。它们不构成 current behavior authority：需求层仍以 `docs/.human-controlled/` 为准，行为合同以父目录的 `../spec.md` 为准，执行状态以 `../status.md` 为准。

## Buffered Chat / local tokenizer 证据链

| 原件 | 性质与阅读边界 |
|---|---|
| [260906-buffered-chat-completions-transcript-evidence.md](260906-buffered-chat-completions-transcript-evidence.md) | `in-review` 的 transcript、request-log、rejected payload 与 deployed estimator 取证。保留 hash、样本与“强烈推断，不是 cryptographic identity”的界限。 |
| [260906-buffered-chat-completions-transcript-evidence-erratum.md](260906-buffered-chat-completions-transcript-evidence-erratum.md) | 上一原件的勘误，必须与其配套阅读。它区分 ciphertext-only decrease `3,715,681` 和删除完整 reasoning items 的 decrease `3,729,865`。 |
| [260906-local-tokenizer-code-audit.md](260906-local-tokenizer-code-audit.md) | `in-review` 的 production dataflow 审计，记录当时的 8 major / 4 minor；不以此替代 living Spec。 |
| [260906-buffered-chat-local-tokenizer-analysis.md](260906-buffered-chat-local-tokenizer-analysis.md) | `settled` 的综合分析：记录 4.927230× 高估证据，并明确 local estimate 不是该次 overflow 的已证根因。 |
| [260906-buffered-chat-local-tokenizer-analysis-review.md](260906-buffered-chat-local-tokenizer-analysis-review.md) | `in-review` 的 R1 独立评审，核验 C1–C10 并提出两个 minor。 |
| [260906-buffered-chat-local-tokenizer-analysis-review-r2.md](260906-buffered-chat-local-tokenizer-analysis-review-r2.md) | `in-review` 的 R2 限定复评，关闭 R1 F1，保留 LT-09 汇总遗漏的 minor。 |
| [260906-buffered-chat-local-tokenizer-analysis-review-r3.md](260906-buffered-chat-local-tokenizer-analysis-review-r3.md) | `in-review` 的 R3 限定复评，只关闭 R2 的 LT-09 残余 finding；不得把其 narrow scope 外推为整条证据链的重新验收。 |

## Claude Code auto-compact / context-window 证据链

| 原件 | 性质与阅读边界 |
|---|---|
| [260824-cc-autocompact-trigger-forensics.md](260824-cc-autocompact-trigger-forensics.md) | Claude Code auto-compact 判定路径的静态取证，版本限定为其文中列出的 2.1.207 / 2.1.226 / 2.1.241 比对和 2.1.241 行号。 |
| [260824-why-autocompact-did-not-fire.md](260824-why-autocompact-did-not-fire.md) | 初始诊断及同日更正。正文保留，但其版本/环境主线已被文件顶部更正收窄；只适用于未设置 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 的环境。 |
| [260824-cc-autocompact-same-version-divergence.md](260824-cc-autocompact-same-version-divergence.md) | 同版本、同 settings 的环境/模型名/熔断分歧取证；适用版本和代码位置固定为 Claude Code 2.1.241。 |
| [260824-autocompact-window-is-one-million.md](260824-autocompact-window-is-one-million.md) | 本机 1M context window 与 967k auto-compact threshold 的实测定案；结论受其记录的 env、模型名和 Claude Code 2.1.241 限制。 |

## Count endpoint 的较早证据

| 原件 | 性质与阅读边界 |
|---|---|
| [260820-review-count-tokens-shared-pipeline.md](260820-review-count-tokens-shared-pipeline.md) | 共享 pipeline 计数观察的早期点时评审；TUI 仅通过跨主题链接引用其 F6，不能把它当 TUI authority。 |
| [260824-count-tokens-prior-art-survey.md](260824-count-tokens-prior-art-survey.md) | count_tokens 的既有裁决、Spec、报告与测试清点，基线固定为文中 SHA 和当时工作树。 |
| [260824-count-tokens-heterogeneous-review-gpt.md](260824-count-tokens-heterogeneous-review-gpt.md) | 异构 `POST /v1/messages/count_tokens` 路径独立评审；客户端兼容性结论明确限定 Claude Code 2.1.241，不能外推给未知客户端。 |

## Residual ledger canonical-history 迁移（2026-09-08）

以下六份原件按 `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md` 的逐行 ledger 从其 exact source 移入本目录；路径与内容均保留，不把历史结论提升为 current authority。destination SHA-256、source absent 与 destination present 逐项核对见 [迁移报告](../reports/260908-residual-history-migration.md)。

| 原 exact source | canonical destination | provenance / evidence family |
|---|---|---|
| `.dev/docs/archived-2604-rewrite/hooks-tokenization-spec.md` | `hooks-tokenization-260717/hooks-tokenization-spec.md` | EF-2604-TOKEN；260717 Hooks/Tokenization 历史 oracle，与 acceptance report 共址。 |
| `.dev/docs/archived-2604-rewrite/tokenization.md` | `2604-rewrite/tokenization.md` | EF-2604-TOKEN；旧 token wire-contract provenance，保留 source 注释所依赖的历史依据。 |
| `.dev/docs/count-tokens/reports/260816-count-tokens-review.md` | `count-tokens/reports/260816-count-tokens-review.md` | EF-2604-TOKEN successor family；provider-chain 接线评审与 blocker closure。 |
| `.dev/docs/count-tokens/reports/260820-review-responses-token-counting.md` | `count-tokens/reports/260820-review-responses-token-counting.md` | EF-2604-TOKEN successor family；Responses 估算、reasoning ciphertext 与 mutation 证据。 |
| `.dev/docs/count-tokens/reports/260824-heterogeneous-count-tokens-measurement.md` | `count-tokens/reports/260824-heterogeneous-count-tokens-measurement.md` | EF-2604-TOKEN successor family；314 次真实测量与系统性高估证据。 |
| `.dev/docs/early-verification/archive-260717-hooks-tokenization/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | `hooks-tokenization-260717/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | EF-2604-TOKEN；与 260717 spec 共址，保留当时 matrix 与 PASS 射程。 |

## 迁移记录

- [260908-historical-evidence-migration.md](../reports/260908-historical-evidence-migration.md) 记录 2026-09-08 的首批 5 份历史原件迁移与引用改写。
- [260908-tmp-evidence-migration.md](../reports/260908-tmp-evidence-migration.md) 记录 2026-09-08 的本批 9 份 tmp 原件迁移、SHA-256 对账和分组边界。
- [260908-residual-history-migration.md](../reports/260908-residual-history-migration.md) 记录本次 residual ledger 中 token-counting canonical-history 的 6 份 exact move、逐项 SHA/source/destination 验证与 provenance。
