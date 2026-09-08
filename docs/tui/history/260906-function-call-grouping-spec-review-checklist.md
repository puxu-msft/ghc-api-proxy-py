---
checklist_id: function-call-grouping-spec-review-checklist-260906
status: active
artifact: ../spec.md
owner: coordinator
---

# Responses client-action display Spec 修订评审核查清单

## 当前状态断言

- S1：`spec.md` 已把 2026-09-06 用户确认的相邻 action grouping 写入唯一行为权威，不再让 design 或历史实现代替 Spec。
- S2：条款明确区分 durable observation 的逐项事实与 console display projection 的相邻归约；display 合并不等于事实去重。
- S3：只合并连续、同 raw item type、名称非空且 `REQUIRED` 的 actions，并保留名称顺序与重复；different raw type、visible reasoning、unknown 和 anonymous action 都是 barrier；不可见且 `NOT_REQUIRED` 的 item 不制造 barrier。
- S4：Rich observation 与 legacy fallback 使用相同 action grouping grammar，但 legacy 不伪造自身没有的 reasoning facts。
- S5：Contextual `completed` 仍从完整 output facts 和 snapshot completeness 判定，不从 display segments 反推。
- S6：验收第 7 条的 exact unit／integration oracle、raw-type collision、barrier 和缺陷控制足以判否 `f97d243` 的 grouping 删除，同时没有新增 proof framework。
- S7：2026-09-06 修订记录准确区分用户直接确认的行为边界、coordinator 受委托作出的内部设计判断，以及 commit history 提供的事实证据。
- S8：修订没有改变并行加入的 Chat provider observation 合同，也没有改动其它 TUI 行为。

## 评审要求

1. 先加载 `my-agents:as-reviewer`，再读本清单与 `spec.md`。
2. 逐条回应 S1～S8；只报 blocker／major，确无则 pass。
3. 对照 `design.md`、当前 `request_log.py`、相关 unit／integration tests，以及 `45e7cfb`、`b233751`、`f97d243` 的历史事实；不要把当前错误实现当行为权威。
4. 检查行为是否可实现且无自相矛盾，特别是 transparent item 与 visible reasoning 的相邻性定义、legacy carrier 的归一化 type/name、raw identity 与 encoding 顺序。
5. 检查修订是否留下任何活的旧 oracle。历史修订记录可保留当时措辞，但当前正文和验收不得继续要求逐项 display。
6. 不修改评审对象；报告记录未采用建议及理由。
