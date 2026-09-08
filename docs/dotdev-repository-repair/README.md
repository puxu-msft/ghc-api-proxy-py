# `.dev` repository repair：current execution entry

状态：**迁移与候选目录退役已完成；尚不得执行 dotdev re-root/worktree 挂载。** 本文是 `.dev` 文档仓库修复的唯一 current execution entry。产品行为继续由各 retained topic 的 living `spec.md`、`status.md`、`plan.md` 或 `deferred.md` 定义；本 README 只汇总文档归档、目录退役与结构修复状态。

## Current ledger

| 工作项 | 当前状态 | 权威边界 |
|---|---|---|
| FRR-01 reasoning review | **已闭合。** `260908-reasoning-encrypted-include-review.md` 已归入 [`reasoning-carrier/history/`](../reasoning-carrier/history/260908-reasoning-encrypted-include-review.md)，原件仍是点时独立评审。`include-01` 的 current test follow-up 是 [`reasoning-carrier/tracking.md` 的 `RC-TF-01`](../reasoning-carrier/tracking.md)，状态为 open / 待独立复验。 | history 原件、RC-TF-01 与候选人控材料均不是用户裁决；RC-TF-01 是 retained-topic test follow-up，不是目录退役或 re-root 的结构性前置。 |
| Original top-level `tmp` ledger | **77/77 已实施**：72 份 canonical history、4 份 exact deletion、1 份 `interaction-context` extraction。 | 原 ledger 的完成不将任何历史原件升级为 current authority。 |
| `interaction-context` | **新增并保留**：[`spec.md`](../interaction-context/spec.md) 是 current contract；2026-09-07 设计/WIP 原稿已在 [`history/`](../interaction-context/history/260907-interaction-context-design.md) 保真归档。 | 原稿的方案、dirty-worktree 描述和测试矩阵不自动成为 current behavior 或已验证结论。 |
| FRR-02 candidate residual ledger | **219/219 已实施**：183 份 canonical history、36 份 exact deletion、needs-user-decision=0。 | 逐项 destination、hash、source absence 与 evidence family 的记录保留在 point-in-time ledger/reports；不把旧 report 改写成 current state。 |
| 15 candidate directories | **15/15 已退役。** 当前 filesystem 的 candidate directories=0、candidate regular files=0。 | “retired”只表示其 living authority、直接依赖与逐份 residual disposition 已闭合；其 canonical history 仍由 retained topics 保存。 |
| Top-level `tmp/` | **机制保留，临时 payload regular files=0。** | `tmp/README.md` 受版本控制以恢复空目录；`tmp/` 仍是临时交换目录，未来新材料必须重新取得 disposition，不能以本次清空结论批量删除。 |
| Retained living dependencies | 对已退役候选目录及具体 top-level `tmp/<file>` 的 direct Markdown links=0。 | 仅适用于 retained living safe superset；`reports/`、`history/`、`archive-*` provenance 和 repair control-plane 内的旧路径都是历史证据，不反算为 current consumer。 |
| `reasoning-carrier` / `timeout-408` | **status refresh 已完成。** 两者实现已在 2026-09-08 审计基线的 `main`，living 页面把 SHA 限定为点时 baseline。 | 未验证的 production/upstream/runtime 范围仍不得写为完成。 |

## 不在退役集合的 retained topics

- [`httpx2-migration`](../httpx2-migration/plan.md) 仍是 living residual owner：步骤 4 prose audit、当前 `httpx2`/`httpcore2` logger 筛噪行为及验证没有闭合，且 `pyproject.toml` 对其 Plan 的指针仍正确。
- [`systemd-runtime`](../systemd-runtime/plan.md) 仍须保留：S3 graceful timeout、S4 rootless installer 已落地，S7 current owner 已转至 `systemd-rolling`；S5 仍需要具有独立 user manager 和 delegated cgroup v2 的可销毁环境完成真实 runtime smoke。static verify 或 direct-fd green 不能替代。

## 唯一剩余结构性顺序

1. **最终独立复扫**：对完成后的 tree 复查 retired candidate path、candidate basename、具体 top-level `tmp/<file>` consumer 与新增/改写 Markdown links；历史 provenance 不反算为 current dependency。
2. **`.dev` git checkpoint**：建立可审查、可恢复的文档整理 checkpoint，并逐路径核对嵌套 tracked tree 与活动根目标树。
3. **才可 dotdev re-root/worktree 挂载**：保留完整 dotdev ancestor chain，验收顶层直接为 `docs/`、`exp/` 等活跃内容，主工作树 `.dev/` 通过 worktree 挂载且 `git status` 可见 `.dev/docs/` 修改。

除上述三项外，不存在待执行的 tmp migration、residual disposition、candidate directory deletion 或 FRR-01 closure 工作；不得把已完成迁移重新写成待办。

## Point-in-time evidence index

以下 reports/ledgers 是本 README current summary 的证据，不是新的 current execution checklist；它们保留各自当时的 filesystem、SHA、发现、范围和未做项。

- repair control-plane：[inventory review](reports/260908-inventory-review.md)、[merged-state review](reports/260908-merged-state-review.md)、[final retirement readiness review](reports/260908-final-retirement-readiness-review.md)、[previous current-ledger refresh](reports/260908-current-ledger-refresh.md)、[final ledger refresh](reports/260908-final-ledger-refresh.md)、[retirement reference map](subtopics/260908-retirement-reference-map.md)、[tmp final disposition](subtopics/260908-tmp-final-disposition.md)、[first retirement batch](subtopics/260908-first-retirement-batch.md)、[candidate residual disposition](subtopics/260908-candidate-residual-disposition.md)、[TUI tmp disposition](subtopics/260908-tui-tmp-disposition.md)、[shutdown/systemd consolidation](subtopics/260908-shutdown-systemd-consolidation.md)、[repair provenance migration](reports/260908-passthrough-provenance-migration.md)、[repair tmp-governance migration](reports/260908-tmp-governance-evidence-migration.md)、[repair residual migration](reports/260908-residual-history-migration.md)。
- FRR-01 / current-status / retained exceptions：[reasoning review migration](../reasoning-carrier/reports/260908-encrypted-include-review-migration.md)、[reasoning status refresh](../reasoning-carrier/reports/260908-status-refresh.md)、[timeout status refresh](../timeout-408/reports/260908-status-refresh.md)、[interaction-context extraction](../interaction-context/reports/260908-spec-extraction.md)、[httpx2 residual audit](../httpx2-migration/reports/260908-residual-audit.md)、[systemd retired-path cleanup](../systemd-runtime/reports/260908-retired-path-cleanup.md)。
- original `tmp` / incoming-reference migration evidence：[request-shape historical](../anthropic-direct-request-shape/reports/260908-historical-evidence-migration.md)、[request-shape tmp](../anthropic-direct-request-shape/reports/260908-tmp-evidence-migration.md)、[bridge history](../anthropic-responses-bridge/reports/260908-history-evidence-migration.md)、[bridge tmp](../anthropic-responses-bridge/reports/260908-tmp-evidence-migration.md)、[client-leg deferred survey](../client-leg-formats/reports/260908-deferred-survey-migration.md)、[client-leg tmp](../client-leg-formats/reports/260908-tmp-history-migration.md)、[keepalive](../delivery-keepalive/reports/260908-historical-evidence-migration.md)、[error-envelope](../error-envelope/reports/260908-tmp-history-migration.md)、[GHE conformance](../ghe-device-flow/reports/260908-conformance-evidence-migration.md)、[GHE evidence set](../ghe-device-flow/reports/260908-tmp-evidence-set-migration.md)、[pidfile](../graceful-shutdown/reports/260908-pidfile-evidence-migration.md)、[pidfile supplement](../graceful-shutdown/reports/260908-tmp-pidfile-evidence-migration.md)、[2604 evidence](../hosted-web-search/reports/260908-2604-evidence-migration.md)、[external relink](../hosted-web-search/reports/260908-external-reference-relink.md)、[skill history](../project-review-principles-skill/reports/260908-tmp-history-migration.md)、[server retired-path cleanup](../server-layout/reports/260908-retired-path-cleanup.md)、[server tmp history](../server-layout/reports/260908-tmp-history-migration.md)、[service-cutover](../service-cutover/reports/260908-tmp-history-migration.md)、[token historical](../token-counting/reports/260908-historical-evidence-migration.md)、[token tmp](../token-counting/reports/260908-tmp-evidence-migration.md)、[upstream pending](../upstream/retry-and-continuation/reports/260908-history-pending-migration.md)、[upstream references](../upstream/retry-and-continuation/reports/260908-references-and-tmp-migration.md)、[upstream tmp](../upstream/retry-and-continuation/reports/260908-tmp-evidence-migration.md)。
- residual canonical-history implementation evidence（9 份 topic reports + 1 份 TUI history migration record，合计 183 项）：[request-shape](../anthropic-direct-request-shape/reports/260908-residual-history-migration.md)、[bridge](../anthropic-responses-bridge/reports/260908-residual-history-migration.md)、[keepalive](../delivery-keepalive/reports/260908-residual-history-migration.md)、[GHE](../ghe-device-flow/reports/260908-residual-history-migration.md)、[graceful shutdown](../graceful-shutdown/reports/260908-residual-history-migration.md)、[server layout](../server-layout/reports/260908-residual-history-migration.md)、[token counting](../token-counting/reports/260908-residual-history-migration.md)、[upstream](../upstream/reports/260908-residual-history-migration.md)、[repository repair](reports/260908-residual-history-migration.md)、[TUI history migration](../tui/history/260908-residual-history-migration.md)。

[`260908-grok-responses-usage-observation.md`](../token-counting/reports/260908-grok-responses-usage-observation.md) 是单次运行时 observation；它不是迁移完成或 provider-wide contract 的证据。

本 README 当前包含 60 个 local Markdown link occurrences、59 个 unique local destinations；按当前文件树复核 missing=0。

## 明确不做

- 不回写或删除任何 point-in-time report、ledger、history/archive provenance。
- 不把 `httpx2-migration` 或 `systemd-runtime` 纳入本批 retired directories。
- 不在最终独立复扫和 `.dev` git checkpoint 前执行 dotdev re-root/worktree 挂载。
- 本 README 不授权移动、删除、`git add`、commit 或 push。
