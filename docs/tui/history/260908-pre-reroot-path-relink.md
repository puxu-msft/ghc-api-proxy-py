---
report_id: pre-reroot-path-relink-260908
status: completed
completed_at: 2026-09-08
---

# PRR-02 TUI/observability path relink 记录

> **Point-in-time repair record**：本记录只描述 2026-09-08 对 PRR-02 TUI/observability 子范围执行的路径改写，不构成 current TUI behavior authority。

## 依据与范围

本次先读取 pre-reroot readiness review、FRR-02 residual ledger 以及 current execution entry。PRR-02 指出 `.dev/docs/tui/spec.md` 的两处 2604 路径和 `src/app/observability/request_log.py` 顶部设计注释仍指向已退役路径；residual ledger 的 EF-2604-TUI 条目指定了 `.dev/docs/tui/history/2604-rewrite/` 为 canonical history destination。

严格按 TUI/observability 子范围处理：只改写 `.dev/docs/tui/spec.md` 与 `src/app/observability/request_log.py`，并新增本记录；没有移动、删除或修改其它文件，没有执行 `git add`、commit 或 push。

## 改写清单

| 文件与原引用 | 新引用 | 处理语义 |
|---|---|---|
| `.dev/docs/tui/spec.md`：`docs/2604-rewrite/telemetry-observability.md` | [`history/2604-rewrite/telemetry-observability.md`](2604-rewrite/telemetry-observability.md) | 改为从 `tui/spec.md` 可解析的相对 Markdown link，并明确该原件是历史设计、不是 current authority。 |
| `.dev/docs/tui/spec.md`：`docs/2604-rewrite/lib-survey/SELECTIONS.md` | [`history/2604-rewrite/lib-survey/SELECTIONS.md`](2604-rewrite/lib-survey/SELECTIONS.md) | 改为从 `tui/spec.md` 可解析的相对 Markdown link，并保留“历史选择/实验，非 current authority”的语义。 |
| `src/app/observability/request_log.py` 顶部注释 | `.dev/docs/tui/history/2604-rewrite/DESIGN.md` | 将 fixed-width frame 的历史 provenance 改到 canonical history 原件；继续说明它不是 standing decision。 |

## 目标与路径复核

- `.dev/docs/tui/history/2604-rewrite/telemetry-observability.md` 存在。
- `.dev/docs/tui/history/2604-rewrite/lib-survey/SELECTIONS.md` 存在。
- `.dev/docs/tui/history/2604-rewrite/DESIGN.md` 存在。
- 两个 spec link 从 `.dev/docs/tui/spec.md` 解析后分别命中上述两个文件；没有保留 `docs/2604-rewrite/` 旧别名。
- `request_log.py` 顶部注释仅保留 `.dev/docs/tui/history/2604-rewrite/DESIGN.md` 新路径；没有保留 `.dev/docs/archived-2604-rewrite/DESIGN.md` 旧路径。
- 本次变更没有处理 PRR-02 中属于其它所有权范围的 bridge、upstream probe、token-counting 或 repair README 项。
