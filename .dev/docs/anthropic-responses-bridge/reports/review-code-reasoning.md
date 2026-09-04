# 独立代码评审：Anthropic Responses reasoning carrier

## 结论

- **评审范围**：commit `b040eb3ce44a6e18a41cd89228fba4173c1c05d1`，相对 anchor `47d9ef101c4b81ac70d805b1da157b34d021d33d`；仅评审新增的 `src/app/anthropic/thinking/responses_reasoning.py`、`tests/unit/test_responses_reasoning.py`，并以 `copilot-api-js` commit `2e7e998bc2ba150723f2fbe48fefd9eb5b6dbe03` 的 `synthetic-reasoning.ts`、`responses-to-anthropic.ts`、`anthropic-to-responses-request.ts` 为固定 oracle。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：2。

## 双视角覆盖证据

### 机械核对

- 对账了签名前缀、legacy bare sentinel、UTF-8 到 unpadded base64url 的编码、Node `Buffer.from(payload, "base64url").toString("utf8")` 的宽松异常语义、foreign/redacted block 拒绝、summary part 拼接、TypedDict 返回字段和包导出面。
- 固定 upstream HEAD 为 `2e7e998bc2ba150723f2fbe48fefd9eb5b6dbe03`，并验证三个 oracle 文件的 worktree blob 与该 HEAD 完全相等。
- 新增测试无法通过系统 Python 的 `pytest` 入口运行，因为该解释器没有安装 `pytest`；为避免 `uv run` 在严格只读 worktree 创建 `.venv`，改为禁用 bytecode 后直接加载测试模块并调用其中所有 `test_*` 函数，全部断言通过，目标 worktree 状态仍为空。这个绿灯只证明现有断言自洽，不证明与 upstream translator 兼容。
- 安全与脱敏方向未发现 blocker/major：实现没有记录、暴露或额外脱敏 `encrypted_content`，也没有引入新的持久化或安全机制。

### 第一人称执行模拟

- 模拟了一个 Responses 输出中出现两个 `reasoning` item、随后跟随普通 message 的 forward 流程，逐步比较 Python 单 item API 与 upstream 的整响应聚合结果。
- 模拟了只有 `encrypted_content`、summary 为空的 reasoning item，比较两边是否创建 Anthropic thinking block。
- 模拟了正常 payload、bare-prefix、legacy bare sentinel、畸形 payload、foreign signature 与 `redacted_thinking` 的 echo-back 路径。

## 事实性发现

[major] `src/app/anthropic/thinking/responses_reasoning.py:55-92` — forward API 把每个 reasoning item 独立转换为一个 thinking block，无法复现 upstream 的跨 item 聚合语义 — 固定 upstream `src/lib/openai/translate/responses-to-anthropic.ts:154-214` 在遍历完整 `response.output` 时把所有 reasoning summary 按顺序拼入一个 `reasoningText`，只保留最后一个非空 `encrypted_content`，最终至多生成一个 leading thinking block。调用方若自然地对多个 item 逐个调用当前函数，会生成多个 thinking block，并让每个 block 各自携带 payload，wire 形状和 round-trip 载荷均与当前 oracle 不同。现有测试只覆盖单 item，无法使该偏差变红 — 将 forward 公共入口提升为接收完整 reasoning item 序列并一次聚合，或新增一个明确的 collection-level 聚合函数供生产调用；用两个 reasoning item、不同 payload、后接 message 的独立 oracle 用例固定“summary 全拼接、最后非空 payload、只生成一个 leading block”。

[major] `src/app/anthropic/thinking/responses_reasoning.py:85-92` — encrypted-only reasoning 会生成空 `thinking` block，但固定 upstream 明确不生成任何 thinking block — 当前条件 `if not thinking and not encrypted` 允许 summary 为空但 `encrypted_content` 非空的 item 通过；`tests/unit/test_responses_reasoning.py:23-32` 还把这一行为固化为绿灯。固定 upstream `src/lib/openai/translate/responses-to-anthropic.ts:207-214` 只在 `reasoningText.length > 0` 时生成 thinking block，其 `tests/openai/responses-to-anthropic.unit.test.ts:223-226` 也明确断言 empty reasoning summary 不产生 thinking block。该偏差会让 Python 发出 upstream 当前不会发出的空 Anthropic content block，违反本切片的字节兼容目标 — 把 forward 发射门改为必须存在非空聚合 summary；`encrypted_content` 仅在该 thinking block 已因 summary 创建时进入 carrier。将现有 encrypted-only 测试反转为 `None`，并保留 mixed summary+payload 的正样本。
