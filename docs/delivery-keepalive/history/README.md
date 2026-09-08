# delivery-keepalive 历史证据

本目录保存支撑当前 `delivery-keepalive` 规范与已闭合裁决的原始时点材料。它们是 provenance，不是 current/living config authority；当前行为与未闭合事项仍分别以主题内的 `spec.md`、`decisions.md` 和 `deferred.md` 为准。

- [`260820-review-synthetic-start-fix.md`](260820-review-synthetic-start-fix.md)：2026-08-20 对 deadline 合成物从空内容块改为仅 `message_start` 的独立评审。该机制及相关待裁窗口已于 2026-08-22 作废；报告保留其缺陷发现与当时比较，不恢复任何当前待裁决。
- [`2604-streaming-resilience.md`](2604-streaming-resilience.md)：来自 `archived-2604-rewrite` 的旧流式韧性设计快照。它仅保留被替代旧配置键的原始设计意图；尤其**不是 current config truth**。当前配置事实以 `schema.py` 注释及本主题 current 文档为准。

## `empty-text-block` evidence family

以下七份 residual evidence 于 2026-09-08 从退役候选目录逐份移动至本主题的 canonical history。它们保留当时的调查、综合与评审 provenance，不升级为 current authority；当前 request-shape contract 仍以 `anthropic-direct-request-shape` 的 living 文档为准。

- [`empty-text-block/reports/260820-empty-text-block-copilot-api-js.md`](empty-text-block/reports/260820-empty-text-block-copilot-api-js.md)：参考实现源码与探针调查。
- [`empty-text-block/reports/260820-empty-text-block-inbound-trace.md`](empty-text-block/reports/260820-empty-text-block-inbound-trace.md)：direct leg 入站读写点追踪。
- [`empty-text-block/reports/260820-empty-text-block-response-side.md`](empty-text-block/reports/260820-empty-text-block-response-side.md)：响应产出链调查。
- [`empty-text-block/reports/260820-empty-text-block-synthesis.md`](empty-text-block/reports/260820-empty-text-block-synthesis.md)：根因、修复综合及上游实测索引。
- [`empty-text-block/reports/260820-review-blank-text-subscriber.md`](empty-text-block/reports/260820-review-blank-text-subscriber.md)：blank-text subscriber 独立代码评审。
- [`empty-text-block/reports/260820-review-final-and-probe.md`](empty-text-block/reports/260820-review-final-and-probe.md)：最终修订与真实上游 probe 复评。
- [`empty-text-block/reports/260820-review-unconditional-blank-strip.md`](empty-text-block/reports/260820-review-unconditional-blank-strip.md)：unconditional blank-strip 实现评审。
