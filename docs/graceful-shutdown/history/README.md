# graceful-shutdown 历史证据

本目录保存 `lifecycle-reorg` 主题迁入的逐字历史原件。它们是 2026-08-16～24 的 point-in-time evidence，不是当前关闭行为的规范或实现状态；当前语义仍以父目录及其主仓库 human-controlled lifecycle 文档为准。原件正文未编辑，旧路径字符串仅作为 provenance 保留。

| 原件 | 原始路径 | 日期 | 证据边界 | current carrier |
|---|---|---|---|---|
| [260816-lifecycle-code-review.md](lifecycle-reorg/reports/260816-lifecycle-code-review.md) | `.dev/docs/lifecycle-reorg/reports/260816-lifecycle-code-review.md` | 2026-08-16 | lifecycle shutdown/listener 代码评审与 mutation 的时点记录；保存 signal rung、ownership 与后续复评上下文，不外推为当前代码结论。 | [../README.md](../README.md)；[client-side/README.md](../client-side/README.md) |
| [260816-lifecycle-reorg-review.md](lifecycle-reorg/reports/260816-lifecycle-reorg-review.md) | `.dev/docs/lifecycle-reorg/reports/260816-lifecycle-reorg-review.md` | 2026-08-16 | 模块搬迁与 AST 等价评审的原始记录；其 import graph 与测试读数限于当时快照。 | [../README.md](../README.md) |
| [260817-entry-switch-review.md](lifecycle-reorg/reports/260817-entry-switch-review.md) | `.dev/docs/lifecycle-reorg/reports/260817-entry-switch-review.md` | 2026-08-17 | production entry switch、headers timer 与 wheel/CLI/config probes 的时点评审；不替代当前部署状态。 | [../README.md](../README.md) |
| [260824-standalone-process-test-transient-failure.md](lifecycle-reorg/reports/260824-standalone-process-test-transient-failure.md) | `.dev/docs/lifecycle-reorg/reports/260824-standalone-process-test-transient-failure.md` | 2026-08-24 | 一次 standalone pidfile test transient failure 观测；未复现、测试名与下一步均限于该次观测。 | [restart-handover/README.md](../restart-handover/README.md) |

四份原件于 2026-09-08 按 residual ledger 的 canonical-history 行迁入。每份原件的 source、destination、SHA-256 与 basename uniqueness 核对见 [`260908-residual-history-migration.md`](../reports/260908-residual-history-migration.md)。不得复制、改写或把这些历史材料升级为 current authority。
