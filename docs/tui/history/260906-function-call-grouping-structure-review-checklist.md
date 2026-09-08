---
checklist_id: function-call-grouping-structure-review-checklist-260906
status: active
target_rev: f97d243f9431d836861ce5e9938605df56b37478
owner: coordinator
---

# Responses completion action 聚合结构评审核查清单

## 目标

评审要回答的不是“怎样把旧代码贴回来”，而是：哪一个结构性边界能同时保留 provider output 的逐项事实、可见顺序、相邻同 raw type 聚合、reasoning run 聚合、unknown／无名边界、inert encoding 和 contextual `completed` 着色，并使以后修改其中一种 segment 时不容易静默删除另一种聚合语义。

## 必读证据

- `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/response_observation.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/response_action.py`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/git-housekeeping/reports/260905-merge-conflict-observability.md`
- Git commits `45e7cfb972b6f9df5874a8455d9961d692f2bba2`、`b23375165ae0a72d7a5e6271f6d48c3236e55666` 与 merge `f97d243f9431d836861ce5e9938605df56b37478`

## 必须核查

1. 复核 `f97d243` 是否在 merge resolution 中删除了仍存在于第二父提交的 tool-run accumulator，并同步把测试 oracle 改成不聚合。
2. 区分用户已确认的显示合同与 `ResponseObservation` 的事实合同：逐项事实和重复必须保留，但显示层连续同 raw type 的具名 required actions 合并为一个 segment。
3. 比较至少三种设计：恢复双 accumulator；先投影 typed display segments 再做相邻归约；通用 streaming run reducer／其他更小抽象。明确推荐与不采用理由。
4. 检查推荐设计是否把事实选择、相邻性、合并 identity、文本编码／着色、最终拼接分成可单测的责任，而不是把同样的状态机换个名字。
5. 明确以下边界：可见 reasoning、不同 raw action type、unknown action、无名 action必须断开；NOT_REQUIRED 且无可见 reasoning 的 item 不制造伪边界；reasoning item 没有可见内容时是否应断开，必须与现行可观察合同和历史设计对账。
6. 检查 raw type 必须在 `inert_token` 之前参与 identity；显示 label 不能成为分组键；名称逐项 inert 后再由 renderer 加分隔符。
7. 检查 legacy `format_terminal_status()`／`format_client_actions()` 是否应纳入本切片，避免无依据扩大重构范围；若不纳入，写明为什么不是结构根因。
8. 给出 Spec 修订点、生产代码边界、应改测试及至少一个 integration-level 断言；不得创建新的 proof framework。
9. 列出所有未采用方案及原因，不得只写推荐方案。
10. 对每个事实主张标明证据强度；对设计判断写判据，不把现状伪装成用户裁决。

## Coordinator 返回后验收

- 报告存在且尾部交付声明完整、自洽。
- 报告记录 reviewed_at_rev，并能把结论绑定到上述三个 commit 与当前文件。
- 报告至少给出一个明确可执行的结构设计、两个未采用方案及理由。
- 推荐设计逐项覆盖第 5 至第 8 条，不得把“根因修复”降为恢复旧局部变量。
- 报告没有修改源码、测试或 Spec。
- 若报告依赖“合并前行为就是用户合同”，必须区分历史证据与用户在本会话中的当前确认；若该前提为假，推荐设计的行为合同会改变，因此必须显式标注其来源。
