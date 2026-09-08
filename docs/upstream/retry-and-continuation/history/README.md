# 本主题承接的历史材料

本目录保存已经迁入本主题、但不应被误读为当前实现状态或永久产品裁决的原始上下文。活跃的未闭合事项只在上级 [`../deferred.md`](../deferred.md) 中登记；那里必须链接这里的材料，而不是继续依赖将退役的来源主题。

| 材料 | 原始来源 | 承接内容 | 使用边界 |
|---|---|---|---|
| [`decisions-20260821.md`](decisions-20260821.md) | `.dev/docs/history/decisions.md` §6 | §6.1、§6.2 产生时的实施背景、原文建议与暂缓理由 | 这是 2026-08-21 的历史快照；当前是否扩展或渲染仍是 `deferred.md` 中待裁决事项 |
| [`decisions-20260821-query-surface.md`](decisions-20260821-query-surface.md) | 已计划退役的 history 主题之 `decisions.md` 第五节，2026-08-21 | “完整 HTTP 支持”原先针对完整取证库、重定范围后须重新确认的上下文 | 这是历史范围重定；当前是否建设查询面仍是 `deferred.md` §26 的待确认事项 |
| [`260822-deferred-md-inventory.md`](260822-deferred-md-inventory.md) | 顶层 `tmp/`，2026-08-22 | `deferred.md` 的全条目、编号引用面和撤回旧标题的教训 | 点时只读清点；当前未闭合项仍以 `../deferred.md` 为准 |
| [`260822-review-session-closeout.md`](260822-review-session-closeout.md) | 顶层 `tmp/`，2026-08-22 | 整改复核 N1，为 deferred §20 的负样本与位置事实提供证据 | 点时异源评审；不替代当前产品状态 |
| [`260822-review-never-silent-failure-events.md`](260822-review-never-silent-failure-events.md) | 顶层 `tmp/`，2026-08-22 | 上游失败事件的证伪式评审，为 deferred §21 的未处理静默点提供证据 | 点时异源评审；当前待办以 `../deferred.md` 为准 |
| [`260822-h2-streamreset-cancel-diagnosis.md`](260822-h2-streamreset-cancel-diagnosis.md) | 顶层 `tmp/`，2026-08-22 | Anthropic 上游腿 RST_STREAM(CANCEL) 的一次性诊断及方言判据 | 点时诊断；当前实现状态以 `../status.md` 为准 |
| [`260821-plan-g1-upstream-error-events.md`](260821-plan-g1-upstream-error-events.md) | 顶层 `tmp/`，2026-08-21 | G1 上游错误事件的边界与设计裁决记录，含 G4 的 code/message 核查 | 点时计划；不替代 current Spec 或实现状态 |
| [`260821-probe-history-error-frames.md`](260821-probe-history-error-frames.md) | 顶层 `tmp/`，2026-08-21 | history 数据库中上游 SSE `error`／`response.incomplete` 终局的只读探针 | 直接但时点化观测；不外推到未覆盖时间窗 |
| [`260821-review-g1-candidate.md`](260821-review-g1-candidate.md) | 顶层 `tmp/`，2026-08-21 | G1 上游失败事件候选的独立评审 | 点时评审；当前行为以 `../status.md` 为准 |
| [`260821-truncated-anthropic-stream-diagnosis.md`](260821-truncated-anthropic-stream-diagnosis.md) | 顶层 `tmp/`，2026-08-21 | 一次 Anthropic 腿干净截断生产事件的诊断 | 单次事件证据；不把样本外推为频率结论 |
| [`260822-p2-complete-fix-handover.md`](260822-p2-complete-fix-handover.md) | 顶层 `tmp/`，2026-08-22 | `StreamEnding.COMPLETE` 修复的实施交接与变异记录 | 点时交接；当前结局语义以 living 文档为准 |
| [`260822-pyright-errors-in-stream-cap-slice.md`](260822-pyright-errors-in-stream-cap-slice.md) | 顶层 `tmp/`，2026-08-22 | stream-cap 切片当时的 21 个 pyright error | 固定 main 快照；不是当前 pyright 状态 |
| [`260822-review-complete-fix-gpt.md`](260822-review-complete-fix-gpt.md) | 顶层 `tmp/`，2026-08-22 | `COMPLETE` 修复的独立评审 | 点时评审；与同组 Opus 评审及 handover 共同解释历史修复 |
| [`260822-review-complete-fix-opus.md`](260822-review-complete-fix-opus.md) | 顶层 `tmp/`，2026-08-22 | `COMPLETE` 修复的异源证伪评审，含 deadline/terminal 次序的受控变异 | 点时评审；`deferred.md` §11 以此为历史证据，不把它当 current authority |
| [`260822-review-streamreset-diagnosis-gpt.md`](260822-review-streamreset-diagnosis-gpt.md) | 顶层 `tmp/`，2026-08-22 | H2 RST_STREAM(CANCEL) 诊断的独立评审 | 点时评审；与已归档诊断原件共同保存 |
| [`260822-review-streamreset-diagnosis-opus.md`](260822-review-streamreset-diagnosis-opus.md) | 顶层 `tmp/`，2026-08-22 | H2 RST_STREAM(CANCEL) 诊断的端到端证伪评审 | 点时评审；结论受固定基线与测试条件限制 |
| [`260824-cc-stop-reason-incomplete.md`](260824-cc-stop-reason-incomplete.md) | 顶层 `tmp/`，2026-08-24 | Claude Code 对 `stop_reason: "incomplete"` 的实测兼容性 | 客户端版本限定的时点调查；不外推到其他客户端 |
| [`260827-fix-silent-drop.md`](260827-fix-silent-drop.md) | 顶层 `tmp/`，2026-08-27 | Responses assembler S3 无声丢弃的修复与变异记录 | 点时实施记录；当前静默点台账以 `../deferred.md` 为准 |
| [`260908-review-upstream-failure-backoff.md`](260908-review-upstream-failure-backoff.md) | 顶层 `tmp/`，2026-09-08 | consecutive-failure backoff 的 blocker/major、修复与测试处置、replay 固定 base 边界 | 保留 `.dev/human-controlled-docs-candidates/260908-upstream-retry-backoff.md` 待用户追认的 provenance；当前行为仍以 `../status.md` 与该候选稿为准 |
| [`history-forensics/`](history-forensics/README.md) | 已退役 `.dev/docs/history/` topic，2026-09-08 | History 取证能力调查、proposal、wiring/fixture/gone 情景调查，以及 proposal/Spec 的独立复核 | 一组保真时点证据；当前行为与未闭合工作只由 `../status.md`、`../deferred.md` 承载 |

`decisions-20260821.md` 于 2026-09-08 从计划退役的 history 主题迁入；首批五份及本表新增的十二份原件于同日从顶层 `tmp/` 迁入；`history-forensics/` 的 13 份原件于同日从该退役 topic 按 residual ledger 迁入。本索引记录 canonical 位置，不替代用户亲笔的产品权威文档。
