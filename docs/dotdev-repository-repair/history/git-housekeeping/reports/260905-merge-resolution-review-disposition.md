---
report_id: merge-resolution-review-disposition-260905
status: closed
main_candidate: 96fb3be3d2a0cf7f683c18dc947884cc33e87508
docs_candidate: d46d7d8b34d056b2b2d3ae3ed8130b56d2c97668
updated_at: 2026-09-05
---

# Merge resolution review disposition

本表处置 2026-09-05 四份冲突调查和两份独立候选评审。原报告保持原文；本文件是采用／驳回的唯一处置来源。所有裁定均为 C 级——落入代码或 living document、可逆；没有改变用户亲笔文档、既有用户裁决或 ADR。

| 项 | 来源 | 处置 | 依据与落点 |
|---|---|---|---|
| Runtime M1：terminal 后迟到的新 index 可重新污染 `output_items`，terminal `response` 非 object 会遗留旧 draft | `260905-merge-resolution-review-runtime.md` M1 | **采纳，复评通过** | terminal `output` 是最终集合 authority。`ResponsesObserver` 增加全局封口状态；完整 body 合法数组替换全集，缺失／malformed／非 object 保持不可分类，封口后忽略 item events。测试覆盖 empty／missing／malformed／non-object／late-new-index。 |
| Spec-tests M1：effort plan 仍保存旧 provider 查询签名与 helper-only facts 持久化入口 | `260905-merge-resolution-review-spec-tests.md` M1 | **采纳，复评通过** | living plan 已改为 route-bound `ModelDescriptor`＋compiled profiles；facts 生产入口改记 `RequestCompletionCoordinator.publish()`、freeze／rehydrate，同时保留 legacy helper 的真实定义域。 |
| Spec-tests M2：相反调查建议没有 disposition | `260905-merge-resolution-review-spec-tests.md` M2 | **采纳** | 本表承担处置；以下各行分别记录相反建议的采用与驳回，不改写报告原文。 |
| Unknown `tool_search_call.execution`／`shell_call.environment` 的 delivery projection | translation report 建议部分 unknown 为 False；pipeline-core 与 history-tests 报告建议统一 True | **采用 `UNKNOWN → True`；驳回 False** | `.dev/docs/direct-passthrough/spec.md` §7.1 的现行三态投影是唯一 authority：只有 `NOT_REQUIRED` 为 False。候选 `response_action.py` 统一 classifier；`test_response_observation.py` 与 batch merge 测试钉住 missing／future discriminator。False 建议会扣住未来客户端行动，违反 Spec。 |
| Unknown action 的显示拼写 | observability report 建议 `client_action(type?)`；history-tests 报告建议 `client_action?(type)` | **采用 `client_action?(type)`；驳回 `client_action(type?)`** | `.dev/docs/tui/spec.md`「描述回复的用词」与验收给出精确 oracle；候选 renderer 与 streaming integration 均按该 spelling。远端拼写虽已有测试，但其测试不是比 living Spec 更高的权威。 |
| 相邻同类 client actions 是否 grouping | observability／translation 报告倾向保留远端 grouping；history-tests 报告要求逐项 | **采用逐项输出；驳回 grouping** | TUI Spec 明确“同一类型的每个调用保留重复”，并给出 `function_call(Bash) function_call(Bash) custom_tool_call` 的精确输出。Grouping 保留计数但改变合同形状，不能以“没有去重”替代逐项。Reasoning 连续同 kind 的计数仍保留，因为它不是 client-action 列。 |
| Rich `ResponseObservation` 与 legacy terminal 的优先级 | observability、pipeline-core 报告 | **采用 rich observation 优先，legacy fallback 保留** | observation 覆盖 provider status、failure、usage、reasoning／action 顺序和 attempt freshness；legacy terminal 只在 observation unavailable 时提供 direct-stream compatibility。`format_completion_line` 的分支顺序和正反测试固定该优先级。 |
| Terminal output 与早期 stream drafts 的关系 | history-tests 报告与 runtime review | **采用 terminal 数组替换全集；驳回按 index 补丁式 merge** | terminal `response.output` 是最终集合 authority；显式空数组必须清掉早期项目，缺失／malformed 不得让旧 draft 冒充完整集合，non-object 元素保留为该位置的 unknown。 |
| Responses observer 的覆盖面 | 远端 `6200600` 已覆盖 direct／translated、streaming／non-streaming；旧 direct-passthrough／TUI Spec 仍写 direct streaming only | **采用已实现覆盖面并先修 Spec** | 两份 Spec 自己标明这些是可由评审共识修正的派生事实，不是用户裁决。direct-passthrough v23 与 TUI 2026-09-05 修订已同步生产接线和测试证据，并明确 mock 不冒充真实 upstream。 |
| Request-level effort 与 reasoning bridge／tool choice | translation、history-tests 报告 | **采用正交并集** | `SemanticRequest` 保留 `thinking_effort`＋`tool_choice`，response reasoning 继续由 typed content bridge 承载；旧 `ReasoningIntent`／`request.reasoning` 删除。Anthropic 与 Responses passthrough keys、writer 顺序和 carrier tests 均取两侧并集。 |
| Chat Completions 的 reasoning loss | targeted tests 暴露 | **仅显式 request intent 记录 not-carried loss** | Anthropic 省略 thinking／effort 的 `ANTHROPIC_DEFAULT` 不是客户端显式请求；显式 `thinking` 在 nested residual 留痕，explicit top-level／per-message／Responses intent 有非默认 provenance。修法保留显式 intent 测试，同时恢复普通 Chat 请求的 lossless。 |
| Route target construction | pipeline-core、translation、history-tests 报告 | **采用 route-bound descriptor＋profiles；驳回 provider 二次查询** | routing、translation、prompt admission 必须共享同一 catalog snapshot；send/count 共用 `_translate_with_facts`。living effort plan 所有已发现的旧签名均同步。 |
| Conversion facts 与 legacy terminal fields 的 production persistence | observability 报告 | **采纳** | `RequestCompletionCoordinator` 的 freeze／rehydrate／schema v2 top-level legacy projection均保留 `facts`、`terminal_status`、`client_actions`、classification completeness；测试从 production coordinator 入口验证，不只测 helper。 |
| `.claude/settings.json` 重复 `worktree` key | history-tests 报告 | **采纳** | 两侧值相同，保留一个 `bgIsolation: none`；重复 JSON key 会让解析依赖 last-wins，属于无 marker 的自动合并缺陷。 |
| `test_pipeline_app` catalog 位置假设与 hosted-search loss oracle | full integration failures | **采纳根因修复** | catalog mutation 改按 model id 查找，不再依赖数组位置；hosted-search tests过滤 response direction，只验证自己负责的 response loss，不把合法 request effort loss误判为回归。 |
| Final docs M1／M2：closed 表仍写“待复评”；删除复合 deferred 0 时误删 Chat Completions 半边 | final docs narrow review | **采纳，复评通过** | 两项已通过的整改行改为“采纳，复评通过”；`tui/deferred.md` 恢复只覆盖 direct buffered `/chat/completions` 的第 0 条，TUI Spec 修订记录改为只关闭 Responses 半边、exact usage 与 translated terminal-status。 |

## 验证状态

- targeted merge regression：508 passed。
- pipeline integration：257 passed。
- terminal sealing／display／error-envelope 定向复核：195 passed。
- Ruff：passed。
- Pyright：0 errors，0 warnings。
- 最终 full pytest：2838 passed、2 skipped，coverage 91.75%。
- Runtime 复评：PASS，0 blocker，0 major。
- Spec／tests 复评：PASS，0 blocker，0 major。
- 以上数字是 2026-09-05 的本轮快照，权威复现命令分别为项目 `CLAUDE.md` 的三条验证命令；本文件不把数字当作长期基线。
