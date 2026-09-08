# Hooks / Tokenization 独立验收报告

日期：2026-07-17

Oracle：`docs/2604-rewrite/hooks-tokenization-spec.md`

独立 verifier 对冻结规格主动证伪，结论如下：

| 维度 | 结果 |
|---|---|
| Tool pair adjacent/parallel/partial/duplicate/result-first/mixed/idempotence | PASS |
| Anthropic exact count learning 与 calibrated fallback | PASS |
| Protocol/model calibration isolation、bucket/clamp/interpolation | PASS |
| Prompt-limit 两种格式、记录、不覆盖 catalog、不修改 payload | PASS |
| Hook order/name conflict/disabled/frozen context/error isolation | PASS |
| Anthropic SSE usage tap bytes 保真与跨 chunk 解析 | PASS |
| 删除历史截断与原生 server-tool 生产能力 | PASS |
| Tokenization management API 与 protocol/model filters | PASS |

Verifier 初次报告的一个缺口——Anthropic count endpoint 的 token-limit 400 只记录 limit、未训练 calibration——已修复并增加回归断言。独立 reviewer 报告的 disabled poisoned-thinking factory fallback 也已修复并增加集成测试。

最终工程门禁以主测试套件为准：Ruff、Pyright strict、全量 pytest 与覆盖率均通过。