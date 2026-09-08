# Task 3 独立 code review

> 本文件由coordinator从reviewer `ab690ff0`的完整末轮转录；reviewer因隔离worktree guard无法写指定路径。以下正文保持原结论与证据边界。

评审对象为固定 package `82afd89..6b27458`，并对照 implementer report、`task-3-brief.md`、current Spec 的双向字段矩阵与 `Request-level ThinkingEffortIntent` 小节，以及 Acceptance `REQ-05A`。按要求未重跑 targeted tests、mutation、Ruff、Pyright 或 production probes；这些结果仅作为绑定到该 package 的既有证据采用。

## Verdict

- **行为实现：PASS。** 静态审查未发现 production source 把合法输入转换成错误 wire、错误 field path、silent loss，或提前实现 Task 4 的缺陷。
- **Package-level Spec acceptance：NEEDS-FIX。** `REQ-05A` 要求的部分可判否 oracle 未落地，尤其 compatibility loss producer 可以被全部删除而保持现有测试全绿。
- **Code quality：NEEDS-FIX。** 问题集中在测试分辨力；未发现 production source 的 blocker 或 major correctness defect。

## Findings

### Major M1：translated compatibility loss 没有能判否其删除的断言

位置：

- `src/app/pipeline/translation_driver/anthropic_messages.py:100-125`
- `tests/unit/pipeline/translation_driver/test_translation_driver.py:288-361`
- `.dev/docs/anthropic-responses-bridge/acceptance.md:90-97`

Source 分别为 `thinking.type=auto`、缺 budget 的 `enabled`、低于官方 minimum 以及 `budget_tokens>=max_tokens` 记录 compatibility approximation；nested residual 还会另行记录实际未携带的 `thinking.budget_tokens`。两者是并存事实，不是重复 loss：前者说明输入依赖 translated-path compatibility extension，后者说明 budget 没有进入 Responses wire。

现有参数化测试只断言 `enabled`、effort 与 top-level source。删除 `anthropic_messages.py:100-125` 的全部 `conversion.record(...)` 后，这组测试仍会通过。`test_explicit_effort_wins_and_budget_never_selects_the_level` 的两个输入没有 `max_tokens`，因此 `64000` 不会进入 over-bound compatibility branch，而且测试只期望普通 `EXTENSIONS_NOT_CARRIED`。Implementer 报告的 7 个 mutation 也没有覆盖这些 loss producer。

因此现有测试无法区分“精确记录 compatibility”与“静默接受 compatibility”，正是 Spec 与 `REQ-05A` 要排除的相邻失败。

建议增加静态 expected，不得由产品 reader／writer 生成：

1. 分别覆盖 `auto`、缺 budget 的 `enabled`、`budget_tokens<1024`、`budget_tokens>=max_tokens`。
2. 每个样本断言完整 `reasoning` wire、按顺序的精确 loss code／detail，以及适用时恰好一次 `thinking.budget_tokens` not-carried。
3. 增加一次只删除 compatibility record 的单侧控制，确认失败落在 loss 断言，而不是 wire 断言。

### Minor m1：Responses same-format merge-order 测试不再含冲突字段

位置：

- `tests/unit/pipeline/translation_driver/test_translation_driver.py:243-260`
- `src/app/pipeline/translation_driver/openai_responses.py:906-908,1007-1010`

Production writer 当前顺序正确：先 merge nested residual，再由 `_apply_reasoning()` 写 owned `effort`。

但测试把原先能裁决 precedence 的冲突 residual `{"effort": "low", "summary": "auto"}` 收窄成只有 `{"summary": "auto"}`。如果未来把 merge 移到 `_apply_reasoning()` 之后，或者 reader 错把 stale effort 留回 residual，这个测试仍可能得到 `high`，没有真正验证测试名所称的 precedence。

建议恢复 conflicting static residual，并继续期望完整对象为 `{"effort": "high", "summary": "auto"}`。这是 writer merge-order oracle，不是要求正常 reader 生产 stale residual。

### Minor m2：逐消息 provenance 与 future-only original retention 缺少状态断言

位置：

- `src/app/pipeline/translation_driver/anthropic_messages.py:243-271`
- `tests/int/test_pipeline_app.py:3908-3972`
- `src/app/server/inbound.py:55-68`
- `.dev/docs/anthropic-responses-bridge/spec.md:300-307`

Current code正确地在 control 实际到达 user turn 时无条件写 `EffortSource.ANTHROPIC_PER_MESSAGE`，所以 top-level 与 per-message 都为 `high` 时仍保留真实 source。Future-only control 也只从 filtered target messages 移除，没有原地修改 inbound payload；server inbound 另存了 original payload。

但现有正向测试只使用 `medium→xhigh`。把 source 更新错误地改成“只有 value 改变才更新”仍会通过。Future-only HTTP 测试断言 Responses input 中没有 control，却没有从 History original request 证明完整 control 仍在。

建议增加：

- top-level `high`＋per-message `high`，断言 semantic source 为 `ANTHROPIC_PER_MESSAGE`。
- Future-only HTTP 样本读取持久化记录，断言 original request 仍含完整 control。

这不推翻 current source，只说明两条显式状态合同尚无回归保护。

## Behavioral compliance walkthrough

静态审查确认：

- `thinking` 只产生 enablement；五档 effort 只来自 `output_config.effort`，两者省略时为 enabled＋`high`。
- 显式 effort 与实际作用于 user turn 的最后一个 per-message control按冻结优先级折叠；disabled 在 writer 处优先。
- Candidate 在普通 message parser 之前仅以 mapping 含 `output_config` 判定；错误 role 不会漏入普通消息。
- Message sibling、role、content、output sibling、effort 与缺 beta 均返回稳定 code 和精确 field path；beta header按 comma切分并 trim。
- Future-only control 从 Responses input 移除，但不改变 active／source；输入对象未被原地修改。
- Enabled alignment先排除 `none`；known-only-`none`拒绝。Exact、downward、floor、missing、empty 与 unrankable 均符合 Spec。
- Disabled 只有 target明确发布 `none`时才写 `reasoning.effort=none`；否则 upstream前拒绝。
- Top-level `thinking`／`output_config` sibling进入 nested residual；跨格式逐子字段记录 loss，已转换 effort不会再次成为 generic extension loss。
- Compatibility approximation 与 budget not-carried 同时出现时是两个不同事实，不构成 nested residual double loss。
- Responses writer当前确实先 merge residual，再覆盖 owned effort。
- `handle()` 与 `handle_count_tokens()` 都在 path header policy清空前复制 source headers，并将相同 resolved-model capability交给同一个 translator。Count不调用 Responses upstream。
- Driver仅在 `route.translation_required` 时调用 registry；direct Anthropic leg结构性 bypass。新增 literal `ultracode` direct样本能判别 translator是否误介入。
- Translated reader在 `output_config.effort`精确拒绝 literal `ultracode`。
- Responses→Anthropic profile rendering仍未实现，没有提前侵入 Task 4。
- Review package只修改 brief列出的 7 个文件。
- 当前 `src/` 与 `tests/` 未发现已删除的 `ReasoningIntent`、budget ladder、`intent_from_thinking`或旧 reasoning `resolve()` consumer；剩余同名 `resolve`属于无关 lifecycle／model-resolution helper。

## Evidence boundary

Implementer report 声称 112 targeted passed、Ruff passed、Pyright 0 errors、legacy-symbol scan零命中、production probes passed、7／7 mutation命中且恢复后 control nodes 15 passed。本轮未重跑，因此这些只能作为该 report 所述环境和 package 的既有证据；它们不能补上 M1、m1、m2 中未构造的错误状态。

SPEC: NEEDS-FIX
QUALITY: NEEDS-FIX
COUNTS: blocker=0 major=1 minor=2 nit=0
