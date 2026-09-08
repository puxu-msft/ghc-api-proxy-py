---
report_id: tui-evidence-index-fix-260908
status: completed
completed_at: 2026-09-08
---

# TUI residual evidence index 修复报告

## 变更

按 PRR-03 仅更新 `.dev/docs/dotdev-repository-repair/README.md`：

- 在 residual canonical-history implementation evidence 中加入 [`TUI history migration`](../../tui/history/260908-residual-history-migration.md)；
- 将计数明确为 **9 份 topic reports + 1 份 TUI history migration record，合计 183 项**；
- 更新 README local link 计数为 **60 个 occurrences、59 个 unique destinations**，并记录当前 `missing=0`。

README 仍是 current execution entry；既有 history records 未改写。

## 验证

- TUI migration record 存在：`.dev/docs/tui/history/260908-residual-history-migration.md`。
- README 新增目标以 README 所在目录解析后存在，且为本次遗漏的 TUI migration record。
- 9 份 topic residual reports 加上 TUI history migration record 覆盖 ledger 的 183 项 canonical-history migrations；TUI record 明列 3 个 canonical history 原件。
- README Markdown local link occurrences=60，unique destinations=59，missing=0。
- 本次未修改其它文件；未执行 `git add`、commit 或 push。
