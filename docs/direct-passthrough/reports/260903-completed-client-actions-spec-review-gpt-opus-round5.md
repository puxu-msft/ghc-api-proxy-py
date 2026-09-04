---
report_id: review-completed-client-actions-spec-round5
attempt_id: agent-a40c43530f7a688a4-round5
status: in-review
reviewed_at_rev: "main@4b7d74f56b8b0264b481a2fefe275a233979fbb2; .dev dotdev@15baeb1820d750bd190c78d874a674052b250004 + 2026-09-03T23:18:39+00:00 filesystem snapshot"
---

# `completed` 与 client actions Spec 第五轮终评

## 评审范围

只复核 round4-01：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:188` 的 route (e) 与缺陷注入，以及 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md:33-41` 的处置。F01、F02、F04、F05 及前轮已经关闭的边界均未重开。

## 总体判定

**VERDICT：needs-fix。blocker 0，major 1。** route (e) 现在足以证明最终 action facts 的 `requirement`、type、name 与顺序服从 terminal output，而不是 done snapshot；round4-01 的“action 列 authority”这一半已关闭。但同一 fixture 仍不能证明 `completed` 的**颜色判定**服从 terminal requirement，因为另外两个 done item 仍是 required，旧 `_saw_client_action`／done-side `any(required)` 也会得到“不绿”，与正确结果同形。

## Findings

### review-completed-client-actions-spec-round5-01
severity: major | primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:188`
related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:670-672`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:162,188-194`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md:33-41`
证据：只有 `output_index=0` 的 done requirement 被反转为 `not_required`；terminal 余下两项是重复 `function_call` 与 `custom_tool_call`，验收只说其 done “使用不同名称”，仍允许它们保持 required。于是颜色若继续读现有 done-side `_saw_client_action`，仍因另外两项为 true 而不绿；action 列 exact assertion 会红掉“从 done 收集 facts”，却看不见“列表读 terminal、颜色读 done bool”的混合来源。
影响：terminal action 列可以完全正确，同时决定用户原始需求的 `completed` 颜色仍由非权威 done 事实驱动；当前 expected 与“从 done 读取 requirement” mutation 没有把这两个消费者拆开，因此不能宣称 terminal authority 的全部承重属性已关闭。
建议：让 route (e) 的**所有** done snapshots 都分类为 `not_required`，或另加一个只有单 item 的反向来源对照；再显式注入“action 列读 terminal、颜色只读 done-side bool”，要求 action 列仍正确但颜色断言单独变红。

## 已确认部分

- terminal 侧 `function_call(Bash)` 对 done 侧 `tool_search_call(execution=server)` 已形成 `required` 对 `not_required` 的承重分歧。
- 最终尾段要求保留三项 terminal actions，足以判红整份 facts 从 done 读取、name 从 done 读取、requirement 从 done 读取及按 done 到达顺序输出。
- terminal snapshot／stream delivery 的职责分离继续成立，本轮没有重开。
- 唯一剩余盲区是颜色与 action 列采用两个来源的混合实现；这不是假想架构，因为当前 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:162,188-194` 正持有独立的 done-side `_saw_client_action` bool，实施新 facts 时必须保留它供 `Terminal.stop_reason` 合成使用。

## 未采纳／被排除路线

1. **不重开 action 列 authority。** 新 requirement 分歧已经覆盖该属性。
2. **不要求删除 `_saw_client_action`。** C4 要求保留 `Terminal.stop_reason` 的翻译／continuation 语义；应通过来源分离测试防止它越权驱动 TUI 颜色，而不是删掉既有消费者。
3. **不重开 F01、F02、F04、F05 或 round3 的职责分离。** 当前整改未破坏其闭合依据。

## 搜索面与证据边界

逐句读取了 TUI route (e)、其缺陷列表、direct §10 authority 合同与处置表第四轮段落，并对 action-list consumer 与 color consumer 分别进行反例推演。未运行测试，因为仍在评审待实现的验收判据；结论只说明当前 oracle 无法区分混合来源错误状态。

## 我最没把握的三个判断

1. **其余两个 done item 的 requirement。** 文本只明确它们“使用不同名称”，没有逐字声明 type/discriminator；若作者本意是三项 done 全部 `not_required`，应把这一事实写进 acceptance，写明后本 finding 即关闭。
2. **混合来源实现的概率。** 尚无实现 diff，不能声称一定发生；但现有 `_saw_client_action` 是已经存在的独立 bool，因此不是凭空发明的数据通路。
3. **定级。** 补法只涉及 fixture／mutation 一小处，但盲区直接控制用户点名的绿色语义，按影响仍为 major。

## 执行本契约时遇到的摩擦

none

## 整体判定

round4-01 的 facts authority 已关闭，color authority 尚未关闭；补一组让 terminal 与 done 的 `any(required)` 结果相反的对照，并单独变异颜色来源后，才可定稿。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T23:18:39+00:00
finding_total: 1
blocker_count: 0
major_count: 1
minor_count: 0
nit_count: 0
