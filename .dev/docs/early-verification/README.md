# 早期验收资产（历史快照）

本目录保存 `ghc-api-proxy-py` 在 2026-07-15～17 的 Phase 0～8、Hooks 与 Tokenization 验收原件。它们是当时一次执行的报告与方法，不是当前验收入口，也不定义当前产品行为。

当前验证命令的权威来源是项目根 `CLAUDE.md` 的“开发验证”一节，当前行为由主仓 `tests/` 与各主题 living Spec 决定。本目录里的 PASS／BLOCKER、模块路径、依赖、端口与运行命令只在各自报告写明的日期和实现快照下成立。

## 目录

| 路径 | 原始位置 | 内容与时点 |
|---|---|---|
| `archive-260715-phase3/` | 主仓根 `verification/` | Phase 3 独立验收报告及其单文件 runner；报告当时判 2 blocker、1 major |
| `archive-260716-final/` | 主仓根 `verification/final_acceptance/` | Phase 0～8 的 README、manifest、summary、完整报告、总 runner 与 8 个黑盒 probe；报告当时判 0 blocker、0 major，其中 WebSocket 一项跳过 |
| `archive-260717-hooks-tokenization/` | 主仓根 `verification/` | Hooks／Tokenization 独立验收报告；其 oracle 现位于 [`../archived-2604-rewrite/hooks-tokenization-spec.md`](../archived-2604-rewrite/hooks-tokenization-spec.md)，而该主题已由用户裁定整体过期、仅供参考 |

原件在 2026-09-04 从未跟踪的 `verification/` 工作树内容逐字移动到这里，没有把旧路径、旧依赖、旧 verdict 或命令改写成当前形态。报告与 runner 必须一起读：只留 PASS 而删掉当时的探针会失去方法，只把旧脚本修到当前可跑又会伪造那次执行。

## 为什么不再是当前工具

- `phase3_acceptance.py` 仍导入旧 `app.models.openai`、`app.openai.*`、`app.routes.*` 与 `app.server.create_app`；当前生产入口和 pipeline 布局已经迁移。
- Final acceptance probes 仍依赖旧 `httpx`／`httpx_ws` 与当时的 Responses WebSocket 路由；当前项目使用 `httpx2`，且生产入口不再挂载那条旧 WebSocket 路由。
- `archive-260716-final/run_all.sh` 把原始 `verification/final_acceptance/probes` 路径写死；归档后刻意不修复，因此从现路径运行不是有效复现，也不得把失败解读成当前产品回归。

这些事实的文件级盘点、交叉证据与未采纳路线见 [`../git-housekeeping/reports/260904-dotdev-dirty-inventory.md`](../git-housekeeping/reports/260904-dotdev-dirty-inventory.md) 及其同目录处置账。