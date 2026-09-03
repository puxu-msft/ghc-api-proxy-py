# Effort translation Spec 独立复核清单

- review_id：effort-translation-spec-260903
- attempt_id：effort-translation-spec-gpt-opus-a1
- review_scope：`.dev/docs/anthropic-responses-bridge/spec.md`、`acceptance.md`、`implementation.md` 的 current working tree
- report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-spec.md`
- r2_attempt_id：effort-translation-spec-gpt-opus-a2
- r2_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-spec-r2.md`
- r2_scope：首轮 EFFORT-M01～M06、整改 diff 与相邻合同；首轮报告绑定的 checklist hash 保持其 point-in-time 意义，本文件新增内容只供 R2
- r3_attempt_id：effort-translation-spec-gpt-opus-a3
- r3_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-spec-r3.md`
- r3_scope：R2-M01／R2-M02、用户新增profile裁决、对应整改diff及直接相邻contract；R1／R2报告各自绑定的旧checklist hash继续保持point-in-time意义
- r4_attempt_id：effort-translation-spec-gpt-opus-a4
- r4_report_path：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-spec-r4.md`
- r4_scope：R3-M01／R3-M02、第六条regex正负域、custom modes逐项fallback及直接相邻复述；旧报告绑定的checklist hash均保留point-in-time意义

## 必须逐条核验的断言

- C1：2026-09-03 用户裁决被忠实记录：thinking 只决定启用；effort 档位只由 `output_config.effort` 决定；省略 thinking 为 enabled；Anthropic 省略 effort 为 high；disabled 优先；逐消息 effort 折叠为当前有效档；反向 none→disabled、minimal→low；ultracode 只按实际 wire 的 xhigh 处理。
- C2：Anthropic 官方 effort／thinking／budget／逐消息 model gate事实准确；translated path保留的`auto`、缺budget enabled、正整数低budget及跨source-model逐消息支持均明确标为proxy compatibility extension，且不改写direct path或冒充官方能力。引用与日期足以复核。
- C3：Responses `reasoning.effort` 的合法值与 nullable／model-specific capability 说法匹配项目锁定 OpenAI SDK 3.3.1 类型。
- C4：`ThinkingEffortIntent | None` 能区分 source 无 intent、enabled／disabled、显式／缺省／逐消息档位和 Responses 来源；budget 不作为档位输入。
- C5：Anthropic→Responses 与 Responses→Anthropic 对每个合法值、capability exact／downward／floor／unknown、disabled 无 none、minimal 和 malformed 都有唯一终态；没有 silent fallthrough。
- C6：直连 Anthropic→Anthropic 与 Responses→Responses 原样转发，不被本轮 translator policy 二次改写。
- C7：逐消息 effort 所需 beta header 在路径 header policy 清空前可由 translator reader获得；send 与 count 两个入口均有可实现的数据通路。
- C8：reader 认领 effort 后，兄弟字段同格式可重建；跨格式只记录未携带子字段，不重复把已翻译 effort 计为 loss。
- C9：REQ-05A 每个关键正样本都有同入口、单缺陷注入控制；expected 不调用产品 resolver／writer；证据层声明了不能冒充真实 upstream。
- C10：REQ-05B 不再混入 request-level effort，原 reasoning carrier 合同没有被本轮无意改写。
- C11：字段矩阵、Reasoning 正文、验收行为、冻结决策与 Acceptance 之间没有优先级或状态矛盾；strict unknown 与新增 DEGRADE 项不互相拆台。
- C12：Implementation 只陈述“Spec 已改、代码未改、待复核”，没有把计划写成实现事实或把既有 canary 外推成本轮证据。

## 评审输出要求

本轮只报 blocker 与 major，最多 6 条，每条不超过 6 行；minor／nit 只汇总数量，不展开。每条发现必须有稳定 finding_id、severity、primary_location、related_locations、具体失败场景、证据与建议；没有发现也要逐条回应 C1～C12。

报告最后必须包含：整体判定；“我最没把握的三个判断”；“执行本契约时遇到的摩擦”；`## 交付声明`，其中含 `delivery_complete: true`、`completed_at`、`finding_total`、`blocker_count`、`major_count`、`minor_count`、`nit_count`。报告只绑定评审时的工作树内容，不得修改 Spec／Acceptance／Implementation。
