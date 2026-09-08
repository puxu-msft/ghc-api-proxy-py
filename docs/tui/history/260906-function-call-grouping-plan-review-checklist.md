---
checklist_id: function-call-grouping-plan-review-checklist-260906
status: active
artifact: ../function-call-grouping-plan.md
owner: coordinator
---

# Responses client-action grouping 实施计划评审核查清单

## 当前状态断言

- P1：计划逐项覆盖 `spec.md` 验收第 7 条和 `design.md` 的 typed projection、adjacent reduction、rendering、status independence、legacy reuse，不增加 schema 或其它 TUI 范围。
- P2：计划遵从项目 implementation-first 节奏；修复前已有 direct failing reproduction，production behavior 先实现，随后同步 tests，不擅自采用 TDD。
- P3：计划中 segment types、helper signatures、调用顺序与当前 Python 3.14 代码及现有 `OutputItemSummary`／`ClientAction` 数据形状一致。
- P4：Shared `_action_display_segment()` 使 rich／legacy 的 requirement→variant 规则只有一个 owner；rich projector只额外处理 reasoning。
- P5：Reducer 对 visible segment tuple 做 total pairwise fold，只有 named action 和 reasoning 两个显式 merge case；其它 variant 默认 barrier。
- P6：Renderer 在 raw identity 归约后才执行 `inert_token`，并逐个编码 raw name 后调用 `_painted_tools()`；计划中的 expected strings 与实际 grammar 相符。
- P7：Unit 与 integration test 修改覆盖 user-reported `TaskCreate,Bash`、重复不去重、transparent item、visible barrier、unknown／anonymous、raw-type truncation collision、legacy fallback、contextual completed 和 production wiring；durable identity assertions保留。
- P8：一次性缺陷检查只禁用 named-action merge arm，使用 `$CLAUDE_JOB_DIR/tmp` snapshot、前台执行并以 `cmp` 确认恢复，不使用 Git restore／checkout，不构建 proof framework。
- P9：验证命令符合项目约定，不运行 `ruff format`；提交使用精确 pathspec、`-F` message file且先检查共享目标状态。
- P10：计划没有 placeholder、错误路径、未定义符号、互相矛盾的步骤，且每个任务产生可验证的语义结果。

## 评审要求

1. 先加载 `my-agents:as-reviewer`，再读本清单与计划全文。
2. 逐条回应 P1～P10，结合当前代码、tests、Spec 和 design 给出证据。
3. 重点模拟计划中的 Python 类型检查和字符串 expected；发现代码片段不合法、helper 顺序不可用、测试无法构造或 mutation 无法安全恢复时按实际影响定级。
4. 检查计划是否误写了当前代码中的 test name／line、是否漏掉会继续携带旧 oracle 的测试。
5. 只报 blocker／major，最多 6 条；若只剩 minor，直接 pass。记录未采用建议及理由。
6. 不修改被评对象或源码；报告落盘并带尾部交付声明。
