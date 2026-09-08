# Anthropic Messages → Responses request converter 独立代码评审

## 结论

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-request` 分支 `feat/anthropic-responses-request`，HEAD `f8a11ad3c3cd8f2330333634f1fe963f9aa2c444`，相对 anchor `47d9ef101c4b81ac70d805b1da157b34d021d33d`；只评审新增的 `src/app/protocols/anthropic_responses.py` 与 `tests/unit/test_anthropic_responses_request.py`。行为 oracle 为主树 `docs/agents/anthropic-responses-bridge/spec.md`、`acceptance.md`、`research.md`，reasoning wire oracle 固定为 `copilot-api-js` commit `8d5c861c2e079b92401dd8ccd49695a363d078fe`。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：4。

## 双视角覆盖证据

### 机械核对

- 对账了 envelope、string／block system、user／assistant text、base64／URL image、tool declaration、`tool_use`、`tool_result`、`tool_choice`、parallel flag、reasoning carrier、unknown 字段、server／typed tool no-revive、顺序和结构化错误码。
- 逐行对账主树正式 spec／acceptance 的 REQ-02～REQ-05，以及固定 upstream 的 `synthetic-reasoning.ts` 和 `anthropic-to-responses-request.ts`；carrier 的 malformed 行为直接用 Node `Buffer.from(payload, "base64url").toString("utf8")` 与当前 Python converter 做 differential probe。
- 检查了共享 `MessagesRequest`／`ContentBlock`／`AnthropicTool` 的 Pydantic `extra="allow"` 模型，并用一个只增加已声明字段的 `MessagesRequest` 子类验证 model evolution 接缝。
- 新增测试文件整套通过，ruff 通过。现有 order、有效 carrier fixed vector、unknown top-level extra 三条测试分别经内存变异后按预期转红，说明这些已覆盖机制不是 false-green；但测试没有覆盖下列 4 条缺陷。`pyright` 本轮 CLI 未解析项目 `.venv` 中的 `pydantic`、`orjson` 和 `pytest`，结果为环境性 missing-import 噪声，未据此评价候选代码。

### 第一人称执行模拟

- 模拟客户端分别发送 `thinking.enabled`、`thinking.adaptive` 与 `thinking.disabled`，观察是否生成或省略 Responses `reasoning`。
- 模拟开启跨协议工具名清洗后，声明工具、assistant 历史 `function_call` 与 forced named choice 同时携带 `mcp.weather/tool`，检查最终 wire 是否共同映射。
- 模拟客户端 echo 正常、单字符、非 alphabet、非 ASCII、带 padding 后垃圾及解码后非 UTF-8 的 synthetic carrier，逐个与固定 Node consumer 比较输出与异常类型。
- 模拟共享 Pydantic 模型未来新增一个正式字段且客户端显式提供该字段，检查 converter 是否 fail closed，而不是因为它已从 `model_extra` 移入 `model_fields_set` 就静默丢失。
- 模拟 `[tool_use, text]`、`[text, tool_result]`、图片、foreign thinking、typed tool、`server_tool_use` 和 `*_tool_result` 路径；现实现的连续 run flush、当前 unknown extra 拒绝和 server-tool no-revive 未发现 blocker／major。

## 事实性发现

[major] `src/app/protocols/anthropic_responses.py:76-92` — 顶层 Anthropic `thinking` 无条件按 `unsupported_field` 拒绝，缺少规格冻结的 Responses `reasoning` 转换 — `_reject_unsupported_request_fields()` 把任何非空 `thinking` 与 `top_k`、`stop_sequences` 并列失败；黑盒探针确认 `enabled{budget_tokens}`、`adaptive`、`disabled` 三种输入全部抛 `RequestConversionError(code="unsupported_field", field_path="thinking")`。正式 spec 的 Reasoning 契约和 acceptance REQ-05 要求 enabled／adaptive 经 capability gate 映射 effort＋summary，disabled／absent 则省略；因此任何启用 thinking 的合法 bridge 请求都在发送前错误失败 — 增加独立的 request-level thinking→reasoning 转换，接收 resolved-model capability／limits 事实；enabled、adaptive、disabled 和 unsupported capability 分别返回确定 wire 或稳定 capability error，并补独立 expected 的参数化测试。

[major] `src/app/protocols/anthropic_responses.py:238-249,300-345` — converter 没有共享 tool-name mapper，非法名称会在声明、历史 call 与 forced choice 中原样进入 Responses wire — 仓库虽有 `settings.py:178` 的 `sanitize_tool_names`，现有 Anthropic sanitizer 只做与声明大小写一致化，没有 Responses 合法字符映射；目标代码也没有 mapper 参数或调用。黑盒样本 `mcp.weather/tool` 同时原样出现在 `tools[].name`、`input[].name` 和 `tool_choice.name`。这违反 spec／acceptance REQ-04 的“声明、forced choice、历史 call、response restore 共享同一双向 mapping”，并会让需要 sanitizer 的请求直到 upstream 才被 schema 拒绝 — 在 converter 边界传入一个 request-scoped 双向 mapper，或在其前建立 canonical mapped request fact；同一次原子变换必须覆盖 tool declaration、assistant `tool_use`、forced named choice，并把逆映射事实交给 response converter。补最终 wire equality 与 round-trip restore 测试，不能只测 helper。

[major] `src/app/protocols/anthropic_responses.py:279-297` — malformed reasoning carrier 未与固定 Node base64url／UTF-8 consumer byte-compatible，且部分输入泄漏裸 `ValueError` — 固定 upstream `synthetic-reasoning.ts:59-67` 对任意非空 prefix payload 执行宽松 `Buffer.from(payload, "base64url").toString("utf8")`。差分探针中：payload `A` 在 Node 得空字符串，Python 记录 malformed 并省略 `encrypted_content`；`YWJjZA=garbage` 在 Node 得 `abcd`，Python 降级省略；`_w` 在 Node 得 replacement character，Python 降级省略；非 ASCII payload 在 Node 得空字符串，Python 从 `urlsafe_b64decode` 泄漏未分类 `ValueError`。现有测试只覆盖有效向量 `RU5DPT0→ENC==`，所以绿灯没有验证冻结的 malformed 合同或稳定 error taxonomy — 把 Node-compatible decode 做成单一、独立测试的 codec，明确复现其 alphabet、padding／trailing-data 与 UTF-8 replacement 语义；至少保证所有输入都返回确定的 reasoning item＋fact 或 `RequestConversionError`，绝不泄漏裸标准库异常。用固定 Node 输出生成的静态 differential vectors覆盖上述边界，expected 不得由 Python codec自身生成。

[major] `src/app/protocols/anthropic_responses.py:26-29,65-66,395-400` — 顶层／message／system／tool 的 unknown-field gate 只检查 `model_extra`，会对 Pydantic 已声明但 converter 尚未处理的新字段 fail open — `_REQUEST_FIELDS` 等集合直接取自当前模型全部 `model_fields`，而 `_reject_extras()` 只比较 `model.model_extra`；字段一旦在共享模型中正式声明，就不再存在于 `model_extra`，且还会被动态“允许集合”自动纳入。黑盒子类增加并显式设置 `future_declared_option` 后，converter 返回成功 wire、无 `ConversionFact`，该值完全消失。当前测试只证明尚未声明的 `future_option` 会被拒绝，无法阻止模型演进后回归；这正违反 spec 的“Responses 新字段／未来 unknown explicit，不能因 Pydantic extra allow 静默丢弃” — 将 converter 已消费字段维护为独立、静态的协议合同集合，并用 `model_fields_set ∪ model_extra.keys()` 对账；不要从共享模型的全部字段反向生成 allowlist。对 message／system／tool 使用同一模式，并增加“模型新增正式字段但 converter 未更新时必须红”的架构测试。

## 主观建议

未另列主观建议。以上均为可复现的规格偏差；server-tool no-revive、现有 block 顺序与已声明 variant 字段拒绝路径未发现阻断性问题。若只处理格式、命名或额外负样本等 minor，可与上述修复一并 squash 回该功能提交；当前 4 条 major 未关闭前不建议回并。
