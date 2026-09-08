# Hosted web search 外部证据改链报告

日期：2026-09-08
范围：只修正 `hosted-web-search/status.md` 的 R-19 current reference。

`status.md` §4.5 中 `strip_anthropic_beta_flags` 的实施证据原指向已迁走的 `../hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`。`status.md` 自身实际使用的相对路径是 `../anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md`；本报告位于 `reports/`，因此引用同一原件时使用可解析的报告相对 Markdown link：[实施记录](../../anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md)。

已验证 canonical target `../anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md` 存在。本次仅改动上述 owned status link 和本报告；未修改或移动外部主题中的文件。

## MSR-06 检查结论

2026-09-08 复查确认：报告正文不再含从 `reports/` 位置无法解析的 `../anthropic-direct-request-shape/...` Markdown link；本报告的唯一 Markdown target 使用 `../../anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md` 并可解析。`status.md` 的实际相对路径说明与其所在目录一致，仍为 `../anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md`。
