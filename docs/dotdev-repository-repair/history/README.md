# `dotdev-repository-repair/history/`

本目录保存仓库治理与 `.dev` 文档仓库修复的 historical provenance。它们记录某一时点的 dirty-inventory 处置和合并候选复核，用于说明后续文档合同为何被修订；它们不是产品行为合同，也不取代各产品主题的 living `spec.md`。

| 原件 | 原始路径 | 证据边界 |
|---|---|---|
| [260904-dotdev-dirty-inventory-disposition-recheck.md](260904-dotdev-dirty-inventory-disposition-recheck.md) | `git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition-recheck.md` | 2026-09-04 对 `.dev` 脏文件处置候选的独立复核。 |
| [260904-dotdev-merge-review-gpt-opus.md](260904-dotdev-merge-review-gpt-opus.md) | `git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus.md` | 2026-09-04 对 `.dev` 合并候选的独立复核。 |

产品主题可链接这些原件作为历史 provenance；当前可观察产品行为仍由其各自 living 文档定义。

## 2026-08-20 至 2026-08-27：仓库文档治理与共享索引过程证据

以下 13 份原件从 `.dev/docs/tmp/` 归档而来，正文没有改写。它们记录仓库文档治理、共享索引和当时 repair 决策的过程证据；它们不是产品的 current authority，不能取代任一产品主题的 living `spec.md`、`README.md` 或用户控制文档。

| 原件 | 原始路径 | 证据边界 |
|---|---|---|
| [260820-review-session-closeout.md](260820-review-session-closeout.md) | `tmp/260820-review-session-closeout.md` | 2026-08-20 的评审会话收尾记录。 |
| [260821-shared-index-left-reverting-head.md](260821-shared-index-left-reverting-head.md) | `tmp/260821-shared-index-left-reverting-head.md` | 共享索引在当时 HEAD 回退状态下的记录。 |
| [260822-audit-other-stale-blobs-committed.md](260822-audit-other-stale-blobs-committed.md) | `tmp/260822-audit-other-stale-blobs-committed.md` | 其它 stale 文档 blob 是否已提交的审计。 |
| [260822-candidate-docs-refresh-log.md](260822-candidate-docs-refresh-log.md) | `tmp/260822-candidate-docs-refresh-log.md` | 候选文档刷新过程的日志。 |
| [260822-candidates-vs-user-updates-reconciliation.md](260822-candidates-vs-user-updates-reconciliation.md) | `tmp/260822-candidates-vs-user-updates-reconciliation.md` | 候选材料与用户更新之间的对账。 |
| [260824-spec-freeze-encoding-inventory.md](260824-spec-freeze-encoding-inventory.md) | `tmp/260824-spec-freeze-encoding-inventory.md` | spec freeze / encoding 的当时清点。 |
| [260827-ledger-cleanup.md](260827-ledger-cleanup.md) | `tmp/260827-ledger-cleanup.md` | ledger 清理过程记录。 |

### `2afa0c4` 拆分证据组

[`260822-split-2afa0c4-hash-map.md`](260822-split-2afa0c4-hash-map.md) 是旧新提交哈希的解码对照；[`260822-review-split-2afa0c4.md`](260822-review-split-2afa0c4.md) 是对该拆分的独立评审；[`260822-split-2afa0c4-review-disposition.md`](260822-split-2afa0c4-review-disposition.md) 逐项记录评审发现的处置。三者必须结合阅读：对照表提供可解析的历史身份，评审说明结论，处置记录解释后续选择。

### 代码文档 citation 证据组

[`260822-review-doc-citations-mapping.md`](260822-review-doc-citations-mapping.md) 逐项核验引用映射；[`260822-review-doc-citations-coverage.md`](260822-review-doc-citations-coverage.md) 审查覆盖面和过度改动；[`260822-doc-citations-review-disposition.md`](260822-doc-citations-review-disposition.md) 汇总并记录两份评审的处置。三者是同一次 citation 治理工作的互补证据，不是对当前产品实现或现行文档权威的重新裁定。

## 2026-09-08：residual canonical-history 迁移

以下目录按原 source topic 与 evidence family 保存 residual ledger 指定的 canonical originals。正文保持原样，目录结构保留 family 内部关系；这些材料仅提供 point-in-time provenance，**不是 current authority**，不得取代 `dotdev-repository-repair` 或其它 retained topic 的 living `README.md`、`spec.md`、status、plan 与用户控制文档。

| source topic | evidence family | 原件数 | 导航与 provenance 边界 |
|---|---|---:|---|
| `docs-tmp-migration` | `EF-DOCS-TMP` | 25 | [`docs-tmp-migration/`](docs-tmp-migration/) 保留旧 `docs/tmp` / `docs/agents` 分类迁移的 brief、十批 manifests、十份逐批分类表、抽样审计、完整性复核与当时终态索引。 |
| `documentation-restructure` | `EF-DOC-RESTRUCTURE` | 36 | [`documentation-restructure/`](documentation-restructure/) 保留已终止的 documentation restructure 方案、archive plan 与完整 review/audit chain；旧 README、Plan 和 approval gate 不因归档恢复效力。 |
| `git-housekeeping` | `EF-GIT` | 23 | [`git-housekeeping/`](git-housekeeping/) 保留 worktree/archive 清理、`.dev` remote import/merge 与 merge-conflict resolution 的逐轮调查、评审和处置证据；此前归档在本目录根的两份 canonical originals 不复制。 |

本批共 84 份原件。精确 source、destination 与 SHA-256 见 [`../reports/260908-residual-history-migration.md`](../reports/260908-residual-history-migration.md)。
