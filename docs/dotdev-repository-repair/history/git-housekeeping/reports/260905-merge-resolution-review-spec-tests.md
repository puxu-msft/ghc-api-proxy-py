---
report_id: merge-resolution-review-spec-tests-260905
status: settled
reviewed_main_tree: 96fb3be3d2a0cf7f683c18dc947884cc33e87508
reviewed_docs_tree: d46d7d8b34d056b2b2d3ae3ed8130b56d2c97668
reviewed_at: 2026-09-05
transcription: 主会话从隔离 reviewer 的 SendMessage 转录；reviewer 无法写入主工作树。
---

# Merge resolution specification and tests review

- Verdict：**NEEDS-FIX**。
- Counts：blocker 0，major 2。

## Major

### M1：effort plan 仍有两处旧实现描述

`.dev/docs/anthropic-responses-bridge/plan-effort-translation.md:164` 已写 `translation_target(descriptor, thinking_profiles)`，但 `:881-888` 仍把 helper 参数写成 `provider: ModelProvider` 并调用 `translation_target(provider, route.model_id, chain.thinking_profiles)`；当前实现是 `src/app/pipeline/routing.py:403-415` 与 `src/app/pipeline/driver.py:146-160` 的 route-bound descriptor。

同一 plan `:906-908` 仍称 facts 经 `write_request_record()`／`asdict()` 自动持久化，而生产 sink 是 `src/app/observability/request_completion.py` 的 `RequestCompletionCoordinator.publish()` 加 `_freeze_line()`／`FinalizedRequest.request_line()`。应修正这两处 living plan，不让同一计划同时保存新旧签名和已被替换的生产入口。

### M2：四份冲突调查报告的相反建议缺少显式 disposition

四份 `260905-merge-conflict-*.md` 均已进入 docs candidate，但建议互相冲突：`merge-conflict-translation.md` 主张 unknown `tool_search_call` 的 `delivery_required=False`，而 pipeline-core／history-tests 报告及 living Spec 要求 `UNKNOWN→True`；`merge-conflict-observability.md` 主张 `client_action(type?)`，而 history-tests 报告与 TUI Spec 要求 `client_action?(type)`。候选代码已经按 living Spec 正确选择：`response_action.py` 将 unknown 投影为 True，`request_log.py` 逐项输出 `client_action?(type)`。仍需新增显式 disposition，逐条记录采用／拒绝及依据，且不得改写报告原文。

## 其余核验

C1、C2、C4、C5、C6、C7 静态对账通过；C3、C8 因上述 major 未通过。reviewer 未执行 tests；mock 只证明本代理接线，不证明真实 upstream 本轮行为。`my-agents:as-reviewer` 在 reviewer 环境不可用。

## 复评结果

固定 main tree `c0e5d2b6cad5662173aa3c6cb8ec990efbac22ef`、docs tree `4c92d5900a9b72ee61be932cb077e980ebc79ed0`：**PASS，0 blocker，0 major**。M1 已关闭：plan 全文不再残留 provider-based `translation_target(...)`，production facts persistence 正确指向 coordinator freeze／rehydrate 链。M2 已关闭：disposition 显式采用 `UNKNOWN → True`、`client_action?(type)` 与逐项 action，并按 living Spec 驳回相反建议。未发现相邻 major；复评没有重跑测试。

## 最终文档增量复评

固定 docs tree `562300088b6e7cc324fb0a57d95a6f8c7cc0d1ae` 的首轮结论为 0 blocker、2 major：closed disposition 两行仍标“待复评”；删除复合 deferred 第 0 条时把仍未实现的 direct buffered Chat Completions 半边一起删掉。修复后的最终窄复评为 **PASS，0 blocker，0 major**：处置表状态一致；`tui/deferred.md` 只恢复 Chat Completions 缺口；`tui/spec.md` 只声明 Responses 半边、exact usage 与 translated terminal-status 已闭合。该轮同样未执行测试，只审文档增量。
