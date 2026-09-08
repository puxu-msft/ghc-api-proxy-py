---
checklist_id: function-call-grouping-design-review-checklist-260906
status: active
target_rev: f97d243f9431d836861ce5e9938605df56b37478
artifact: ../design.md
owner: coordinator
---

# Responses completion display projection 设计评审核查清单

## 当前状态断言

- C1：`design.md` 把 `spec.md` 指定为唯一行为权威，自身只解释内部机制，没有另立不同的用户可观察合同。
- C2：现有 `OutputItemSummary` 与 legacy `ClientAction` 已分别携带推荐 projection 所需的 requirement、raw type、raw name 和顺序；rich path 还携带 reasoning facts，因此不需要修改 schema。
- C3：Atomic projection 先识别可见 reasoning，再跳过其余 `NOT_REQUIRED` item，能够同时满足“可见 reasoning 是 barrier”和“不可见 non-client item 不制造 barrier”。
- C4：Typed segment union 让 unknown、anonymous、不同 raw type、可见 reasoning和未来新增可见 variant 默认成为 barrier；只有 reducer 显式列出的同 raw type named actions 与同 kind reasoning 能合并。
- C5：Raw type 和 raw names 保留到 renderer 边界，identity 发生在 `inert_token` 之前，每个 name 分别编码后才由 renderer 添加逗号与颜色。
- C6：Contextual `completed` 独立读取完整 observation，不从 display segments 反推，因此显示归约不会改变 action presence 或绿色语义。
- C7：Legacy `format_terminal_status()` 在 rich observation unavailable 时渲染同一 Responses client-action grammar；复用 action segment seam 可以消除 source-availability-dependent 分叉，而无需修改 producer、优先级或 durable schema。
- C8：测试分层能够分别判否 projection、adjacent reduction、rendering、public orchestration 和 production wiring；它没有建立新的 proof framework。
- C9：未采用方案及原因完整记录，特别说明为何不原样恢复双 accumulator、为何不做 callback 型通用 reducer、为何不改 schema。

## 评审要求

1. 逐条回应 C1～C9，给出文档与源码位置或具体反例。
2. 复核 `_NamedAction.raw_type: str | None` 与 `ClientAction.type: str`／`OutputItemSummary.type: str | None` 的 adapter 是否有未定义语义，尤其 missing type 与 literal `"unknown"`。
3. 复核 raw name 的具名判据是否与现有 producer 一致；空白字符串经 `inert_token` 后是否仍可读，是否需要额外合同。
4. 检查 typed segment 是否真正降低 merge-time partial deletion 风险，还是把同样的耦合搬到新的函数之间。
5. 检查 legacy fallback 同批纳入是否属于同一根因边界；若不应纳入，给出具体 contract 或数据路径证据，不得只以范围／成本反对。
6. 检查 design 与现行 `spec.md` 的已知冲突是否被明确标成待同 change 修订，而不是让 design 静默覆盖 spec。
7. 只报告 blocker 与 major；若没有，明确 verdict 为 pass。记录未采用的建议与理由。
