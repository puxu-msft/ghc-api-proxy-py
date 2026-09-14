# Observability 当前状态

日期：2026-09-14  
状态：**实现切片已落地；完整回归仍有基线失败**

## Current implementation

| 面 | 当前事实 | 权威/证据 |
|---|---|---|
| Request facts | `RequestFacts` 是冻结 projection；`RequestJournal` 已有 bounded lifecycle subset 和 freeze seam | [`spec.md`](spec.md)、commit `c1c56309` |
| Live/request log/metrics | 继续使用独立 projection；普通 log 不承载 raw transport | [`spec.md`](spec.md) |
| History handoff | History writer 接收 immutable entry，durability 与 sink failure 隔离 | [`../history/status.md`](../history/status.md) |
| Capture attachment | full-header capture、capture reference 和 aggregate capability 已接线 | [`../raw-capture/status.md`](../raw-capture/status.md) |
| Replay | 独立 process/CLI 已存在；CLI 当前以 wire diagnostic 为主，semantic/live 依赖注入 executor | [`../replay/status.md`](../replay/status.md) |

## Verification

- Clean committed HEAD：`30384269`。
- Ruff：通过。
- Pyright：通过。
- 新增 History/Replay/Journal/raw-capture targeted suites：通过。
- Full pytest：`3566 passed / 2 skipped / 4 failures`，覆盖率 `89.65%`；4 个失败在基线 `54bc1b5c` 同样出现，属于既有 pipeline/config/catalog fixture 问题。

## Accepted boundaries

以下不是本轮伪装成完成的能力，而是当前状态中明确保留的边界：

- RequestJournal 当前不是完整的 route/attempt/block/history receipt taxonomy。
- capture capability 当前以 aggregate projection 为主，per-attempt durable matrix 仍是长期改进。
- History archive 的重启恢复、Replay result provenance 完整化和更深的 safe projection 对账仍在 deferred。
- `docs/.human-controlled/observability.md` 缺失；候选材料在 `.dev/human-controlled-docs-candidates/260914-observability.md`，需用户控制流程处理。
