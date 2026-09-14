# 可观测性、History、Debug、Replay 实施账本

日期：2026-09-13

本账本只跟踪本轮七项实施工作的状态与证据；行为合同只以各主题 current `spec.md` 为准。这里不复制合同、字段语义或安全边界。

## 任务列表

| # | 任务 | 状态 | 依赖 | 证据与 current owner |
|---|---|---|---|---|
| 1 | raw capture full-header 与 History attachment | done | 无 | `050f0e3e`, `1c348dfc`; 合同见 [`../raw-capture/spec.md`](../raw-capture/spec.md)，实现边界见 [`../raw-capture/status.md`](../raw-capture/status.md) |
| 2 | History archive lifecycle 与 retention seam | done-with-deferred-hardening | 1 | `4008bb5e`, `55d035dd`; 当前限制与长期候选见 [`../history/status.md`](../history/status.md) 与 [`../history/deferred.md`](../history/deferred.md) |
| 3 | History query/export surface | done-with-deferred-hardening | 2、4 | `76fe7eab`; 合同见 [`../history/spec.md`](../history/spec.md)，当前状态见 [`../history/status.md`](../history/status.md) |
| 4 | captured transport 的 History envelope | done-with-deferred-hardening | 1 | `4008bb5e`; 当前 restart/recovery 限制见 [`../history/status.md`](../history/status.md) |
| 5 | RequestJournal 接线 | partial-accepted | RequestFacts projection | `c1c56309`; 当前 bounded event subset 与 JSONL boundary 见 [`status.md`](status.md)，长期 taxonomy 候选见 [`deferred.md`](deferred.md) |
| 6 | 独立 replay process | partial-accepted | 1、3、4 | `dc9f2e81`; contract 见 [`../replay/spec.md`](../replay/spec.md)，CLI/result 当前边界见 [`../replay/status.md`](../replay/status.md) |
| 7 | 合并态回归与文档/实现对账 | WIP | 1–6 | `30384269`: Ruff/Pyright、模块边界、新增 targeted suites 通过；full pytest `3566 passed / 2 skipped / 4 baseline failures`，见 [`status.md`](status.md) |

## 执行顺序

1. 先以各主题 Spec 作为合同，再以 topic status/deferred 描述当前实现边界。
2. History/raw-capture/replay 的能力矩阵必须共享同一份 disposition，不在 ledger 中复制。
3. 最后统一跑 targeted/full gates；基线失败不改写成“本轮功能失败”，但必须保留在 status 中。

## 范围边界

- 不覆盖主树中同伴正在进行的 provider、CommandCode、translation 和 raw-header 其他 hunk；重叠文件使用 filtered patch。
- 不操作 4141 服务，不 push。
- Replay 仍不接入主程序 request path；当前 CLI 以 wire diagnostic 为主，semantic/live 由调用方注入 executor。
- point-in-time reports/history 保留，不把它们改写成 current truth。
