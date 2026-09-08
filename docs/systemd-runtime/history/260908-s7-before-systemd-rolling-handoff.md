# S7 在移交 `systemd-rolling` 前的摘要

2026-09-08。此页从 `../plan.md` 的 S7 章节移出，保留当时“尚未设计”的简要范围。它不是当前计划、状态源或行为规范；rolling 的唯一现行 owner 是 [`../../systemd-rolling/spec.md`](../../systemd-rolling/spec.md) 与 [`../../systemd-rolling/plan.md`](../../systemd-rolling/plan.md)。

## 当时状态

S3～S6 后的独立切片；明确保留，未实施，也不应被冒充为 M1 或真实 user-manager smoke 的自然副作用。

## 当时目标与验收意图

在不迁移 accepted connections 的前提下，让新旧应用实例短时间重叠，先把新连接切到 ready 的新实例，再 drain 旧实例，并支持失败回切。其设计前置为冻结拓扑、readiness／切流 owner、共享状态隔离、migration／资源预算和旧 SSE／WebSocket 的有界 drain。验收意图是：candidate readiness 失败时旧实例保持服务；切流后新连接只进新实例；旧 accepted connections 在 deadline 内完成；回滚不重放已提交响应；并发不损坏 History／tokenization；listener、切流与 drain 分别可观察。

这些前置与验收已被更完整的 rolling Spec／Plan 取代；不得从本摘要反推当前 rolling 行为。
