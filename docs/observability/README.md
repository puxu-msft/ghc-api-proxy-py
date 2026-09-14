# Observability / History / Debug / Replay 文档入口

本组文档描述一次 client request 的事实收集、History durable projection、规则选择的 raw capture 和独立 replay 工具。四个主题各自拥有独立的行为 Spec；本页只负责导航和状态边界，不复制合同。

| 主题 | 行为权威 | 当前状态 |
|---|---|---|
| Observability | [`spec.md`](spec.md) | [`status.md`](status.md) |
| History | [`../history/spec.md`](../history/spec.md) | [`../history/status.md`](../history/status.md) |
| Raw capture | [`../raw-capture/spec.md`](../raw-capture/spec.md) | [`../raw-capture/status.md`](../raw-capture/status.md) |
| Replay | [`../replay/spec.md`](../replay/spec.md) | [`../replay/status.md`](../replay/status.md) |

实施切片索引见 [`implementation-ledger.md`](implementation-ledger.md)。它只记录状态、提交和验证证据，不是第二份行为合同。

本轮 review disposition 见 [`review-disposition.md`](review-disposition.md)。报告原件位于 [`reports/`](reports/)；报告是点时证据，不替代 current Spec 或 status。

## Authority boundary

- 用户控制的产品约束仍由 [`docs/.human-controlled/README.md`](../../../docs/.human-controlled/README.md) 管理；其中缺少的 `observability.md` 已另写候选材料，不能由本页静默代替。
- Observability Spec 只管事实 owner、projection 和 sink isolation。
- History Spec 只管 durable request projection、archive/query/pin/retention。
- Raw-capture Spec 只管 capture selection、binary format、writer safety 和 evidence boundary。
- Replay Spec 只管独立 replay process 的 source、mode、target、deadline/cancel 和 provenance。
- 当前实现限制和长期改进只写入 topic `status.md` / `deferred.md`，不把未实现合同标成 done。
