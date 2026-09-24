# 当前重构复查：测试与架构边界

- report_id: 260923-current-refactor-review-tests-grok-sonnet
- attempt_id: 260923-tests-grok-sonnet-1
- status: draft
- reviewed_at_rev: 061aff32520dd54dceda8ebce7ef6678dee3e02d（完整 HEAD，调查开始时）
- reviewer: grok-sonnet（叶子执行单元，只读）
- 范围：当前未提交差异涉及的 `tests/architecture/`、`tests/int/`、`tests/unit/`、`tests/component/` 与相关 `src/app`
- 不在范围：改写产品代码、格式化、运行会修改工作树的生成器、人类控制文档、`4141` 服务

## 判据来源（读被检对象之前）

- coordinator 清单：`.dev/docs/tmp/260923-refactor-review-checklist.md` 范围三
- 项目原则 `a-broken-test-needs-its-scenario-and-expectation-rechecked`：既有测试随产品改动变红时，要重核场景与期望，不能只改断言；夹具重写可能把守卫搬走
- 项目原则 `assertions-about-copilot-wire-need-a-recorded-counterpart`：声称 Copilot 实际会发/会接受什么的期望值，必须有 cassette 录制对应；本方合同的手写输入是恰当的
- 审查角色：判据不从被检对象反推；事实问题必须附证据；最多 5 条经证据支撑的发现

## 调查笔记

待补充：未提交差异清单、架构测试覆盖、wire 断言与 cassette 对照。
