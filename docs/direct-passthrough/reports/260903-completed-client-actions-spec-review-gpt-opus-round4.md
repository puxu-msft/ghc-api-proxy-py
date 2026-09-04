---
report_id: review-completed-client-actions-spec-round4
attempt_id: agent-a40c43530f7a688a4-round4
status: in-review
reviewed_at_rev: "main@4b7d74f56b8b0264b481a2fefe275a233979fbb2; .dev dotdev@15baeb1820d750bd190c78d874a674052b250004 + 2026-09-03T23:15:32+00:00 filesystem snapshot"
---

# `completed` 与 client actions Spec 第四轮复评

## 评审范围

只复核 round3-01 的处置：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §10、`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` §验收与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md` 第三轮段落。F01、F02、F04、F05 保持 closed，未重开。

## 总体判定

**VERDICT：needs-fix。blocker 0，major 1。** 我同意把 `client_action_classification_complete` 收窄为 terminal snapshot 分类完备：它回答“最终 `response.output` 是否足以判读 client actions”，不重复回答“stream 是否完整交付”。stream 越界 index、未闭合 item 与 unattributed 的 wire／delivery 处置继续归 §4、§7.2、`cut_mid_block`、verdict／detail，职责分离成立。round3-01 的 boundary oracle 已基本补齐；唯一未闭合的是 terminal authority 的控制只让 `name` 分歧，没有让决定 client-action 分类和绿色的 `type`／discriminator 分歧。

## Findings

### review-completed-client-actions-spec-round4-01
severity: major | primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:188`
related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:670-672`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md:25-33`
证据：route (e) 只规定 `done` snapshot 使用“不同名称”，因此能证明 `name` 与排序来自 terminal output，却不能证明 `requirement` 来自它；一个实现仍可从 `done` 的 type/discriminator 算 required/not-required、只从 terminal 补 name，再按 terminal position 排序，五组对照和全部已列 mutation 仍绿。
影响：`requirement` 正是决定 action 是否进入列表及 `completed` 是否绿色的承重字段；terminal 与 done 在该字段分歧时，上述混合来源实现会重现本轮要消除的 false-green／false-non-green，而现 oracle 看不见。
建议：把 route (e) 的至少一个 `done` snapshot 改成与 terminal output 在 type 或条件 discriminator 上给出相反三态，并明确加入“requirement 从 done 读取”的缺陷注入；断言最终 action 列与颜色均服从 terminal output。名称分歧可同时保留。

## 对职责分离的明确表态

**成立，未发现与既有合同的 blocker／major 冲突。** `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:670-672` 已把两个谓词拆清：terminal snapshot 的 `output` 是否存在为数组且逐项得到三态，决定 action 语义的可知性；stream 生命周期与 wire 提交是否完整不进入该字段。`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:145` 同步明确生命周期由 request verdict／detail 表达，因此不是把异常静默删掉，而是由已有消费者持有。显式空 terminal output 表示该 authoritative snapshot 确认没有 output items，即使 stream 另有 unattributed event，也不应让 action 分类字段替 delivery 状态机再裁一次。

该分离的限定也已写对：unattributed 不会**一律**阻止 snapshot complete，但仍由 §4／§7.2 处理；terminal output 缺席或类型错误仍使 snapshot incomplete；数组元素缺 type 得到 `unknown`，不是 absent。故我撤回 round3 对“越界／未闭合必须进入 `client_action_classification_complete`”的建议，接受处置表 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md:31-33` 的未采纳理由。

## 剩余 oracle 核验

| 合同／假修复 | 当前对照 | 结论 |
|---|---|---|
| 显式 `output=[]` 为 complete | route (a) | 已覆盖 |
| 任意 unattributed 都阻止 complete | route (a) 同时携带 unattributed event | 已覆盖，正控方向正确 |
| complete not-required item | route (b) 的 `message` | 已覆盖 |
| `output` 缺席／错误类型 | route (c) 参数化两例 | 已覆盖 |
| unknown native type | route (d) | 已覆盖 |
| terminal position 而非 `done` 到达顺序 | route (e) 的 2、1、0 反序 | 已覆盖 |
| facts 的 `name` 来自 terminal output | route (e) 的名称分歧 | 已覆盖 |
| facts 的 `requirement` 来自 terminal output | 无 type／discriminator 分歧 | **未覆盖，见 round4-01** |
| status-only 变绿／所有 completed 一律不绿 | formatter exact expected 与 route 的颜色断言 | 已覆盖 |

## 未采纳／被排除路线

1. **不再要求 stream 越界 index／未闭合 item 进入 `client_action_classification_complete`。** 这会把 terminal action 摘要与 delivery 状态绑成第二套状态机；第三轮处置的职责分离理由成立。
2. **不要求 unattributed 一律阻止 complete。** terminal output 是最终 action authority，unattributed 的 wire 去向已有独立合同。
3. **不重开 F01、F02、F04、F05。** 当前整改未触碰其闭合依据。
4. **不把 route (e) 的名称分歧当成整个 terminal authority 已证。** 它只能证明被变异的属性；`name` 绿不绿无关，`requirement` 才是本轮承重属性。

## 搜索面与证据边界

逐句读取了 direct §10、TUI 颜色／文本／验收与处置表第三轮段落，并对五组 route 输入和九类列明缺陷注入逐项判断鉴别属性。未运行测试，因为仍在评审待实现的 acceptance contract；结论只评价判据能否判否，不声称实现已通过。

## 我最没把握的三个判断

1. **round4-01 的定级。** 修法只需改变一处 fixture 字段，但遗漏的是决定核心颜色语义的 source-of-truth，而不是装饰性 name，故按实际影响定 major。
2. **构造哪种分歧最合适。** `tool_search_call.execution=server/client` 能直接反转三态且不依赖名字；`message` 对 `function_call` 也可。fixture 已明确不冒充真实上游合法分歧，所以两者都可作为受控 control。
3. **现实现者是否会混合来源。** 尚无实现 diff，不能声称一定如此；本发现只主张当前 oracle 无法区分该错误状态与正确状态。

## 执行本契约时遇到的摩擦

none

## 整体判定

职责分离成立，round3-01 的四类边界补充有效；补上 terminal-vs-done 的 requirement 分歧与对应缺陷注入后，剩余 blocker／major 可归零。当前仍不可定稿。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T23:15:32+00:00
finding_total: 1
blocker_count: 0
major_count: 1
minor_count: 0
nit_count: 0
