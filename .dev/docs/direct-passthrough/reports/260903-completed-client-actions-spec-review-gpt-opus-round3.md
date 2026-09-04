---
report_id: review-completed-client-actions-spec-round3
attempt_id: agent-a40c43530f7a688a4-round3
status: in-review
reviewed_at_rev: "main@4b7d74f56b8b0264b481a2fefe275a233979fbb2; .dev dotdev@15baeb1820d750bd190c78d874a674052b250004 + 2026-09-03T23:11:28+00:00 filesystem snapshot"
---

# `completed` 与 client actions Spec 第三轮复评

## 评审范围

只复核 round2-01 的整改：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §7.1／§10、`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的颜色／文本／验收，以及 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md`「第二轮复评处置」。F01、F02、F04、F05 保持 closed，未重开。

## 总体判定

**VERDICT：needs-fix。blocker 0，major 1。** round2-01 的数据合同已闭合：terminal `response.output` 是最终 authority，三态与集合完备分槽，显式空数组为 complete，unknown 算“已分类但结论未知”，未闭合 item 阻止 complete，unattributed 不被粗暴地一律判 incomplete。当前剩余问题是验收 oracle 没有覆盖该合同的全部承重条件，若据处置表称 round2-01 已关闭仍站不住。

## Findings

### review-completed-client-actions-spec-round3-01
severity: major | primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:188`
related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:670-672`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md:17-25`
证据：四组 route 能分别判否五个已列 mutation，但没有 route 对照覆盖显式 `output=[]`、错误类型的 terminal `output`、stream integer `output_index` 越界、带 unattributed event 但 terminal snapshot 完整；也没有让 `done` item 内容与 terminal `output` 内容故意分歧，因此“从 done 收集后按 index 排序”仍可冒充 terminal authority。
影响：把空数组当缺席、把任何 unattributed 都判 incomplete、忽略越界 stream item、或继续以 done snapshot 为事实来源的实现，均可让当前四组与五类缺陷注入全绿；这些正是 `client_action_classification_complete` 的 true 条件和 authority 边界，不是邻近的次要行为。
建议：新增或参数化 route 对照覆盖上述四个边界，并令至少一组 done snapshot 与 terminal `output` 在 type/name/requirement 上有可观察分歧；加入对应 source-of-truth／empty／unattributed／out-of-range 控制后再关闭 round2-01。

## 已确认部分

- **terminal authority：合同清楚。** `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:670` 明确最终摘要逐项读取 terminal `response.output`，数组位置即 `output_index`；不读 `done` 顺序，也不读 policy bool。
- **complete 的 true 条件：合同清楚。** `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:671` 同时要求 terminal 明确携带数组、每项获得三态分类、stream integer index 无越界、无未闭合 item；显式空数组满足条件，缺席或错误类型不满足。
- **unknown：合同清楚。** `unknown` 是完成分类后的第三种结果，进入 `client_actions` 并阻止绿色，但不声称已确认模型等待客户端；与集合本身未分类完备分开。
- **unattributed：合同清楚。** 它留在 §4／§7.2 的既有事实中，不一律阻止 complete，因为完整 terminal snapshot 仍可能给出全体 authority；当前问题仅是验收没有正控这条边界。
- **文本与颜色：合同一致。** complete＋empty actions 才绿；required／unknown／集合不完备均不绿；集合不完备显示 `client_action?(unclassified)`，unknown native type 显示 `client_action?(<type>)`。

## 四组 route 与五类缺陷注入逐项判读

| 缺陷注入 | 当前哪组会判红 | 结论 |
|---|---|---|
| 着色只看 terminal status | formatter 的 action／unclassified exact expected，及 route b／c／d 的无绿色断言 | **有鉴别力** |
| actions 为空即视为 complete | route c：缺 terminal `output` 且 item 未闭合，必须显示 `unclassified` | **有鉴别力** |
| 所有 item 一律分类为 unknown | route a：完整 `message` 必须是 clean `completed` | **有鉴别力** |
| 丢弃 unknown fact | route b：未知 native type 必须显示 `client_action?(future_tool_call)` | **有鉴别力** |
| 按 `done` 到达顺序输出 | route d：2、1、0 闭合却必须按 terminal position 0、1、2 输出 | **有鉴别力，但只证明排序，不证明 fact 来源** |

因此，处置表对这五个 mutation 的声称成立；不成立的是把这五个控制外推成 round2-01 全合同已被验收覆盖。

## 未采纳／被排除路线

1. **不重开 F01、F02、F04、F05。** 当前整改没有触碰或破坏其闭合依据。
2. **不否定 terminal `output` 作为 authority。** 规范选择本身一致；缺的是能区分该选择与 done-derived 假实现的 oracle。
3. **不要求 unattributed 一律阻止 complete。** 这会误判 terminal snapshot 足以裁决的合法 audio 等事件；需要的是正反对照，不是改成更保守的常量。
4. **不把 empty output 并入“actions 为空”的 formatter 单测。** 后者直接注入 complete=true，证明不了 collector 会从 `output=[]` 得到 true，必须穿过 route／collector。

## 搜索面与证据边界

读取了本轮指定的 direct §7.1／§10、TUI 颜色／文本／验收，以及处置表第二轮段落，并逐条对照四组 route 与五类 mutation 的输入差异。未运行测试，因为此轮评审对象仍是待实现的 acceptance contract；结论是判据的可鉴别范围，不声称当前实现已通过。

## 我最没把握的三个判断

1. **边界对照应新增几组。** 可以用参数化保持“四组”表面数量，也可拆成更多组；本报告只要求每个承重条件有可判否 oracle，不要求固定测试数量。
2. **done 与 terminal snapshot 的分歧样本是否合规。** 它可作为受控缺陷 fixture，只需证明 source-of-truth 选择，不得冒充真实上游实况；如果协议禁止字段分歧，可改用 terminal-only item 与 stream-only item 的差异来达到同一鉴别力。
3. **out-of-range index 的生产概率。** 未测；要求控制的依据是 Spec 自己把“无越界”列入 complete 的必要条件，而不是声称上游现实中常发越界。

## 执行本契约时遇到的摩擦

none

## 整体判定

round2-01 的文字合同已修正，但验收尚不足以给该合同买到 closed；补齐 terminal authority、empty output、错误 output、out-of-range 与 unattributed 边界的 route／缺陷控制后，可再次复评。当前不可定稿。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T23:11:28+00:00
finding_total: 1
blocker_count: 0
major_count: 1
minor_count: 0
nit_count: 0
