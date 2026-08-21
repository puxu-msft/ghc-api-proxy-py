# Anthropic Messages → OpenAI Responses request converter 独立复验 R2

## 判定

**PASS。** 在目标提交 `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 上，本轮只重跑上一轮仍有效的四组失败族，均通过独立黑盒探针：Unicode／malformed reasoning carrier 不再泄漏裸异常，并与固定 Node base64url consumer 的结果一致；`thinking.enabled`／`adaptive`／`disabled` 由显式模型 capability facts 决定；client function tool 的 declaration／历史 call／forced choice 使用同一个 request-scoped 双向名称映射且可恢复；共享 Pydantic 模型新增正式字段时 converter 默认 fail closed。

本结论只覆盖 request converter 的上述有效失败，不代表完整 Anthropic Responses bridge、route、transport、response conversion 或 History 生命周期已经验收通过。

## 冻结基线与 oracle

- 待验收仓库：`/home/xp/src/ghc-api-proxy-py-request`。
- 待验收完整 HEAD：`028f1f2ba7f7ac8ff30e609acb4b0661aff6124f`，分支 `feat/anthropic-responses-request`。
- 行为 oracle：`/home/xp/src/ghc-api-proxy-py/docs/agents/anthropic-responses-bridge/spec.md`，本轮读取的 SHA-256 为 `6c36c7fbab001b776787d17845d5deee9a97da6e3de8dac635c33b0e52d0a04a`。
- Reasoning codec oracle：`/home/xp/src/copilot-api-js` commit `8d5c861c2e079b92401dd8ccd49695a363d078fe` 的 `src/lib/anthropic/synthetic-reasoning.ts`，固定 blob 为 `166aca112474341717c68378910ab44ea5be08b4`。
- 已消费上一轮报告：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260806-verify-request-converter.md`。
- 已消费 server-tool 裁决：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260806-arbitrate-server-tool-contract.md:5-8`。该裁决明确上一轮 server-tool F1 无效；本项目的 `web_search_20250305` typed reject 是正确的 no-revive 行为。
- 每次 shell 调用都在同一调用内校验 `PWD`、repository top-level 与完整 HEAD；执行探针前后均要求 request worktree 的 `git status --short` 为空。

## 从冻结 Spec 独立推导的验收矩阵

| 验收面 | Spec oracle | 独立判据 | 结果 |
|---|---|---|---|
| Unicode／malformed carrier | `spec.md:161-164,213-220` | 向真实 converter 输入多种 malformed prefix payload；不得泄漏 `ValueError`／`UnicodeDecodeError` 等裸异常；输出必须逐项等于独立 Node `Buffer.from(payload, "base64url").toString("utf8")`，并记录 `malformed_reasoning_carrier` degradation fact | PASS |
| Thinking 显式 facts | `spec.md:202` | `enabled` 的 budget 只能由显式 capability limits 与 bands 映射 effort；`adaptive` 只能使用显式 `adaptive_effort`；`disabled` 省略 Responses `reasoning`；缺失支持或越界必须稳定 typed fail closed | PASS |
| Tool mapper 原子且可逆 | `spec.md:133-136,155-160` | 同一个非法 Responses 工具名同时出现在 declaration、历史 `tool_use` 与 forced named choice；三处必须映射为同一个 wire name，`call_id` 与 arguments 保持；发布的映射事实必须能由独立反向表无歧义恢复原名 | PASS |
| 模型新增正式字段 fail closed | `spec.md:129,142,154,513` | 分别给 request、message、system、tool 与 content block 的 Pydantic 子类增加正式字段并显式赋值；字段不能因从 `model_extra` 移入 `model_fields_set` 而静默消失，必须返回稳定 `unsupported_field` 与精确路径 | PASS |
| Server-tool no-revive 边界 | `spec.md:136,159,513`；server-tool 裁决 `:5-8` | 不把 `web_search_*` reject 判错；不得借本轮修复将 typed／server tool 映射成 Responses hosted builtin | PASS，沿用已裁决边界，本轮不重跑已撤销 F1 |

## 实际执行证据

### Carrier 独立差分

探针先用当前系统 Node 直接计算 expected，再把同一 payload 送入 Python 生产入口 `convert_messages_request_to_responses(...)`。覆盖：单字符 `A`、非 alphabet `!!!`、padding 后垃圾 `YWJjZA=garbage`、URL-safe 与标准 alphabet 的非 UTF-8 bytes `_w`／`/w`／`+w`、单独 `=`、Unicode `你好` 与 emoji `😀`。

所有样本均满足：

- Python 没有泄漏裸异常。
- `encrypted_content` 与独立 Node consumer 完全相等：空字符串、`abcd` 或 UTF-8 replacement character `�`。
- 每个样本都生成唯一结构化 fact：`field_path="messages[0].content[0]"`、`disposition="degrade"`、`reason="malformed_reasoning_carrier"`。

对应生产实现位于 `src/app/anthropic/thinking/responses_reasoning.py:46-72,116-123` 与 `src/app/protocols/anthropic_responses.py:504-511`。固定 Spec 明确要求 malformed payload 不得抛未分类异常，并与 Node codec 对齐，见 `spec.md:213-220`。

### Thinking enabled／adaptive／disabled

探针提供显式 `ReasoningCapabilityFacts`：支持 `low`／`medium`／`high`，有明确 budget 下限、上限、分段阈值和 `adaptive_effort`。实际结果：

- `enabled` 且 budget 位于 medium band → `reasoning={"effort":"medium","summary":"auto"}`。
- `adaptive` → 使用显式 `adaptive_effort="high"`，得到 `reasoning={"effort":"high","summary":"auto"}`。
- `disabled` → wire 中省略 `reasoning`。
- `enabled` 但 capability facts 不支持任何 effort → `RequestConversionError(code="reasoning_not_supported", field_path="thinking")`。
- `enabled` budget 超出显式上限 → `RequestConversionError(code="reasoning_budget_not_supported", field_path="thinking.budget_tokens")`。

生产合同位于 `src/app/protocols/anthropic_responses.py:61-102,231-320`。探针没有按模型名称猜测能力，也没有自行用 budget heuristic 伪造模型支持。

### Tool mapper 原子映射与恢复

独立样本使用原名 `mcp.weather/lookup`、wire 名 `mcp_weather_lookup`，并让原名同时出现在 function declaration、assistant 历史 `tool_use` 和 forced named `tool_choice`。实际 wire 三处名称精确相等，`call_id="call-byte-exact-α"` 保持不变，Unicode arguments 解码后仍为原 JSON 值。

converter 发布单一映射事实 `original_name="mcp.weather/lookup"`、`wire_name="mcp_weather_lookup"`。探针不调用产品 restore 来生成 expected，而是从发布事实独立构造 `wire_name → original_name` 反向表，成功恢复原名；随后另行确认产品 `mapper.restore(...)` 给出相同结果。

生产实现位于 `src/app/protocols/anthropic_responses.py:103-149,213-230,477-486,513-570`。

### 正控

正样本先通过完整三位置 equality oracle。随后只在内存观测副本中把 declaration name 改为 `MUTATED_DECLARATION_ONLY`，保留历史 call 与 forced choice 不变；同一个 oracle 按目标原因转红，失败值明确显示三处名称不再一致。恢复未变异的真实 wire 后，oracle 重新转绿。

该正控证明本轮 tool mapper 的绿色判定确实能抓住“只改声明、未原子改 call／choice”这一目标缺陷，不是仅证明 converter 被调用。正控不写生产文件，也没有用整文件恢复。

### 正式字段 fail-closed

探针分别构造带新正式字段的 `MessagesRequest`、`AnthropicMessage`、`SystemBlock`、`AnthropicTool` 与 `ContentBlock` 子类。五个嵌套面均返回 `RequestConversionError(code="unsupported_field")`，field path 分别精确落到 request、`messages[0]`、`system[0]`、`tools[0]` 与 `messages[0].content[0]` 下的新字段。

该探针额外覆盖了候选 request 测试未单列的 content-block 正式字段演进面。生产 gate 位于 `src/app/protocols/anthropic_responses.py:17-52,625-643`；它以 converter 自己维护的静态 consumed-field 集合对账 `model_fields_set ∪ model_extra`，不再从共享模型的全部正式字段动态生成 allowlist。

## Server-tool 裁决处置

上一轮报告把 `web_search_YYYYMMDD` reject 记为 F1，是把另一个项目的专用 WebSearch 产品能力当成本项目 oracle。现行本项目 Spec 与专门裁决给出相反且更近的合同：所有 Anthropic typed／server tools 在 request capability gate 显式 `REJECT`，不得转成 Responses hosted builtin。

因此本轮：

- 不把 `web_search_20250305` 的 `server_tool_not_supported` 判为失败。
- 不要求 declaration／choice 映射为 `{type:"web_search"}`。
- 不把 server-tool 白名单混入 client function tool mapper 的原子性验收。
- 旧 F1 仅作为已撤销历史结论，不影响本轮 PASS。

## 运行与写入审计

- 独立 harness 最终输出 `verdict="PASS"`；carrier、thinking、tool mapper、正式字段与正控各组均为 PASS。
- 目标 request worktree 在探针前后均保持干净，HEAD 未变化。
- 探针设置 `PYTHONDONTWRITEBYTECODE=1`，未创建 `__pycache__`／`.pyc`，未运行会写 pytest cache 的命令。
- 未修改目标生产代码、候选测试、主仓 Spec、外部 upstream 仓库或其他报告。
- 本轮唯一持久化写入是本报告：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260806-verify-request-r2.md`。

## 未验证范围

- 未验证完整 `/v1/messages` route 接线、真实 Responses upstream、HTTP／WebSocket transport、response converter、block buffering、retry、History、hooks 或 tokenization；它们不属于用户指定的本轮有效失败复验范围。
- 未把候选自带 pytest 作为独立验收 oracle，也未用其绿色结果支撑本报告。
- 未做生产文件变异；正控在独立观测副本上注入 declaration-only 缺陷，验证的是本轮原子性判据的判别力。

## 最终结论

目标提交 `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 已关闭用户指定的四组有效 request-converter 失败，且独立差分与正控均通过。**本轮限定范围 verdict：PASS。**
