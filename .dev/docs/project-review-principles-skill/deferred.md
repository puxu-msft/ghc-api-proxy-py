# `project-review-principles` 未闭合项

本文件只列当前仍未闭合的 skill 与产品工作。事实与优先级来源是 [`reports/260903-project-principles-backlog-review-gpt-opus.md`](reports/260903-project-principles-backlog-review-gpt-opus.md)、独立复审及 [`reports/260903-project-principles-backlog-review-disposition.md`](reports/260903-project-principles-backlog-review-disposition.md)；报告是点时证据，本文件是当前状态载体。

## D-1　Skill 的真实复查状态与三组命令已过期

**状态：待修主仓 skill，B 级。** `.claude/skills/project-review-principles/SKILL.md` 的“当前状态”仍写只有 `one-reply-fact-...` 做过一次真实复查、其余四条未被真实复查；2026-09-03 已实际执行五条原则并完成独立复审，这两句已不成立。

同轮还实证三类命令腐坏：原则 1 仍指向已迁移的 `delivery/assembler.py`、`server/handler.py` 与 `pipeline_app.py`；原则 4 把 revision 填进只接受日期的 `git log --since`，且模式漏掉 `async def test_`；原则 3 当前输出包含大量 self-reference 与历史报告噪音。修复应保留原则判据，更新候选生成方法与执行历史；不能为了让命令看起来通过而放宽判据。修改的是模型加载的指令文本，须由未卷入的跨模型 reviewer 复核。

## D-2　Count-tokens 仍绕过共同 usage observation 入口

**状态：已采纳，待实现；当前即时渲染无错误，结构漂移风险成立。** `count_tokens` 成功出口直接写 `trace.usage = {"input_tokens": tokens}`，不经过 `Terminal` 或同形的具名 observation 构造器。下一次统一 reply usage 增加键、来源或换算时，这条出口不会被类型或调用图要求同步。

修法边界：给 count response 建具名、同源的 usage observation，但不把 count 伪装成完整上游 reply；若设计证明 count 的事实所有权本来就不同，则同步修订原则 1 的定义域与 C2。原 finding 是 `PPR-260903-02`。

## D-3　三处 surface 替不拥有结局的层作承诺

**状态：已采纳，待低风险清理。** `DeliveryError` docstring 仍断言 upstream failure “is retryable”，但实际 retry 还受 taxonomy、budget 与 position 决定；server-tools 与 blank-text 的两条 runtime log string 分别断言“upstream would have rejected them”与“which upstream accepts”。这些依据在邻近 rationale 中仍有价值，问题是端点 surface 把当前测量写成自己长期拥有的外部结局。

修法边界：`DeliveryError` 只陈述 delivery-side identity，不替 retry policy 下结论；日志只陈述本模块实际执行的 flatten／empty 动作；保留邻近注释中的测量与理由。原 finding 是 `PPR-260903-03`。

## 已移交，不在本文件重复跟踪

`PPR-260903-01` 的 native reasoning／tool／client-action side facts 已进入 `direct-passthrough` Spec §10 与 plan §11.7；它仍未实现，但当前状态由那两个 living carrier 负责。