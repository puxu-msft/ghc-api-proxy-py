---
report_id: residual-history-migration-260908
status: completed
completed_at: 2026-09-08
---

# TUI residual history 迁移报告

> **Point-in-time migration report**：本报告只记录 2026-09-08 在工作树 `/home/xp/src/ghc-api-proxy-py` 执行的迁移，不构成 current TUI behavior authority。

## 范围与依据

本次严格执行 `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md` 中 destination 属于 `.dev/docs/tui/history/` 且 disposition 为 `canonical history` 的三条 ledger 行。只移动每条行指定的 exact source 到 exact destination；不处理 `delete` 行，不修改其它主题，不重建 `.dev/docs/tui/reports/`，不执行 `git add`、commit 或 push。

## 执行清单

| exact source | exact destination | source SHA-256 |
|---|---|---|
| `.dev/docs/archived-2604-rewrite/DESIGN.md` | `.dev/docs/tui/history/2604-rewrite/DESIGN.md` | `0f922929886fb04ef0b6d2ac6cd337a51a443a34418233fc0d0b467002c523e3` |
| `.dev/docs/archived-2604-rewrite/telemetry-observability.md` | `.dev/docs/tui/history/2604-rewrite/telemetry-observability.md` | `45a9e3fc9f5cd110e95b89a99810d5ecf1e37e8c4c73804de0777cb12e6e832d` |
| `.dev/docs/archived-2604-rewrite/lib-survey/SELECTIONS.md` | `.dev/docs/tui/history/2604-rewrite/lib-survey/SELECTIONS.md` | `23c2b9c78a37317f005c0215eb2b554b43a4beb9f93f33241d2ede83b9ac4d05` |

## 结果与边界

- 三个 destination 在移动前均不存在，未发生覆盖。
- 三个 source 均已移出原位置；原文未改写。
- `.dev/docs/tui/history/README.md` 已更新，列出三份新 canonical-history 原件及既有 history 原件。
- 本报告位于 `.dev/docs/tui/history/`，是点时迁移记录；没有创建或重建 `.dev/docs/tui/reports/`。
- ledger 要求的 source/destination 改链属于其它路径所有权范围，本次未越权修改；因此本报告不宣称相关 current consumer 链接已更新。
