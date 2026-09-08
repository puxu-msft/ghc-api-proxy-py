---
checklist_id: function-call-grouping-code-review-checklist-260906
status: active
baseline_rev: 5995bbe0ac1885482e4976975c3b74d196cb7b11
owner: coordinator
---

# Responses client-action grouping code review 核查清单

## 评审对象

- `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py`
- `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py`
- Authority: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 验收第 7 条
- Design: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md`“Responses completion display projection”

## 可核验断言

- C1：Rich path 对相邻同 raw type、具名且 `REQUIRED` 的 actions 合并名称并保留重复；different raw type、visible reasoning、`UNKNOWN` 与 anonymous actions 是 barrier；不可见 `NOT_REQUIRED` item 不制造 barrier。
- C2：Legacy fallback 通过同一 `_action_display_segment()`、`_coalesce_response_display_segments()` 与 `_render_response_display_segment()` 实现相同 action grammar，没有复制 requirement→variant 分支。
- C3：Reducer 只读 typed visible segments；raw type 在 encoding 前参与 identity，每个 raw name 分别 inert 后才加 renderer delimiter／color；display grouping 不修改 durable observation。
- C4：Contextual `completed` 继续直接读取完整 `output_items` 与 snapshot completeness，不从 segments 反推；ending precedence 不变。
- C5：Typed variants 使任何未显式列入 merge arm 的当前／未来可见 segment 默认成为 barrier，消除了双 pending accumulator 与 scattered flush 协议。
- C6：Unit tests 分别覆盖 atomic projection、shared legacy projection、reducer、barriers、same-kind reasoning、raw-type collision、renderer encoding、user-reported `TaskCreate,Bash`、legacy grouping 和 durable facts；existing production-entry test 覆盖 `function_call(Bash,Bash)` 与 non-green completed。
- C7：改动未触及 schema、classification、delivery、Chat、Anthropic stop reason、pending tools 或 footer；没有隐藏错误、未处理异常、无效分支或不必要 public API。
- C8：Pre-review evidence 为 targeted 85 passed、Ruff clean、Pyright 0 errors、full suite 2854 passed／2 skipped、coverage 91.77%；这些只证明当前未提交 candidate，review 修改后必须按 plan 刷新。

## 评审要求

1. 先加载 `my-agents:as-reviewer`，再读清单、Spec、design 和实际三文件 diff。
2. 对照 baseline commit 与主工作树当前 bytes；报告同时记录 baseline SHA 和三文件 hash。
3. 逐条回应 C1～C8，重点寻找 correctness、简化／复用、typing、可维护性和测试辨识力问题。
4. 不以当前旧实现或 tests 反推行为；不以成本缩小已确认边界；不扩建 proof framework。
5. 只报 blocker／major，最多 6 条；若只剩 minor，直接 pass。记录未采用建议及理由。
6. 不修改源码、tests、Spec、design 或既有报告；只写自己的新报告。
