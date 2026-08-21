# Anthropic Responses Bridge Architecture 独立复评 R3

## 评审摘要

- **评审范围**：主树工作区 current `docs/agents/anthropic-responses-bridge/architecture.md`，SHA-256 `ea6a3eca21c653096b17914d56497a5c6bbb6a8d1c237ebf2a055db24e31dc86`；复评时本地分支为 `main`，HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。目标架构文档仍是工作区新增文件，因此内容身份以本段 hash 为准。本轮严格只复核 R2 报告中独立列出的 R2-M1、R2-M2、R2-M3 三项 major，以及这三项修订直接引入的新冲突，不重做全仓评审。
- **总体 verdict**：**可进入下一阶段；架构可定稿。**
- **计数**：blocker 0，major 0。R2 的三项 major 均已关闭，未发现修订直接引入的新 blocker／major。
- **双视角覆盖证据——机械核对**：逐项对账 `docs/tmp/260806-review-bridge-architecture-r2.md` 的 R2-M1～R2-M3 与 current 架构正文、facts owner 表、事件清单、验收判据、ADR-BRIDGE-06 和评审问题处置表；直接读取并核对架构引用的 session-liveness 候选提交 `f27a8c04cd3470bd50d7194a30371ca5404f727e` 的 cleanup 实现与对应 cancellation／close-failure 测试；核对 current main 的 reasoning helper 及其测试确实仍为跨 item 聚合现状，确认文档将其标成待替换迁移起点而非目标 primitive。每次 shell 取证均在同一调用内校验 root、`main` 与精确 HEAD。
- **双视角覆盖证据——第一人称执行**：模拟 client cancel 后 cleanup 中再次 cancellation、parser primary failure 叠加 close failure、正常退出叠加 close failure；模拟 projection accepted 后 request FINALIZE，writer 随后 durable／failed 并释放 token，以及 projection rejected 不产生 receipt；模拟 reasoning item A 含 summary＋ciphertext、item B 仅含 ciphertext，分别形成有序 thinking blocks、各自进入 ledger／History projection 并逐 block reverse。另串联模拟 cleanup 完成后 FINALIZE、FINALIZE 后 receipt、多个 reasoning blocks 的顺序提交，检查三项修订之间的 owner 与时序接缝。

## 逐项复核结论

| R2 项目 | R3 结论 | 复核摘要 |
|---|---|---|
| R2-M1 exchange cleanup／异常优先级 | **关闭** | `architecture.md:303-305` 冻结唯一 cleanup task、反复 shield 观察至 terminal、后续 cancellation 记忆与恢复，以及 primary／secondary close failure 的机械优先级；`architecture.md:490` 给出 cancellation storm、异常 cause、资源归零、close 至多一次和无 orphan task 的正反判据。所引 `f27a8c0…` 实现及测试实际覆盖同一模式，引用不是仅靠报告自证。 |
| R2-M2 FINALIZE 后 durability receipt owner | **关闭** | `architecture.md:240-249,263` 把 `HistoryProjectionFacts` 与 `HistoryDurabilityReceipt` 分属 request-local driver 和 request-external History writer；`architecture.md:438-461` 明确 request journal 以 `request.finalized` 冻结，writer 只在 finalized barrier 后发布 durable／failed receipt，并在 accepted／rejected 分支分别规定 token 的唯一释放 owner；`architecture.md:491` 对回写冻结 journal、过早 receipt、cleanup 后读 buffer 与 accepted 冒充 durable 均设反例。 |
| R2-M3 reasoning cardinality／迁移裁决 | **关闭** | `architecture.md:31` 明确 current helper 的跨 item 聚合是待修现状；`architecture.md:357,389` 冻结一 reasoning item 一 block、item 内 summary 拼接、item 间隔离及 encrypted-only no-loss；`architecture.md:483,542,556` 同步给出回归变异、保留 codec／reverse consumer、替换 forward API／错误 oracle 的迁移路径。实现者不再需要在复用当前聚合 helper与遵守目标 block identity 之间自行猜测。 |
| 三项修订直接交互 | **无新冲突** | Exchange 必须先退出才进入 FINALIZE；request journal 在 FINALIZE 冻结后，History writer 的 receipt stream 独立继续，不延长 request owner 生命周期；reasoning 的 per-item completed blocks、ledger 与 History projection records 使用相同的一 item 一 block 基数，未在 receipt 或 cleanup 接缝重新聚合。accepted projection 的 reservation 已转为 History ownership，因此 FINALIZE 清理 request-owned reservation 与 writer 稍后释放 projection token 不构成双重释放。 |

## 事实性发现

未发现 blocker、major，也未发现 R2 三项修订直接引入的新冲突。

## 主观建议

无。

## 定稿裁决

**架构可定稿。** R2-M1、R2-M2、R2-M3 均已形成 owner 明确、时序闭合且可由正反样本证伪的合同；三项合并执行时没有出现新的 lifecycle、durability ownership 或 reasoning cardinality 冲突。本结论只覆盖上述定向复评范围，不把未重审的全仓其他方面重新背书。
