---
date: 2026-08-24
topic: Anthropic Messages → OpenAI Responses 翻译腿上的 `defer_loading` 泄漏（第三个 400）
scope: 只调查取证，未修改 `src/`
---

# `tools[].defer_loading` 在翻译腿上泄漏导致 400 —— 调查报告

## 0．范围、快照与证据分级

**本报告只回答派发的 6 个问题，不修改 `src/`。**

快照：

| 对象 | 版本 |
|---|---|
| 本项目 HEAD | `2c4ba5928c5f9ea1937a87b35b47c71d83d5c5d0` |
| 我引用的 `src/` 文件是否脏 | 全部 clean，**唯一例外是 `src/app/pipeline/driver.py`**（同伴在改，见下） |
| `/home/xp/src/copilot-api-js` | `8001c3028` |
| `/home/xp/src/refs/vscode-copilot-chat` | `5863f5a70` |
| `/home/xp/src/refs/CLIProxyAPIPlus` | `0c48ef58` |
| openai Python SDK（本项目 `.venv`） | `3.3.1` |

`driver.py` 的未提交改动是同伴的 gateway beta strip（`strip_gateway_unsupported_betas`），`git diff -U2` 显示它只在 `shape_request` 里加了一段 header 处理，**没有触碰 `handle()` 里第 153-160 行的 `chain.translators.translate(...)` 调用**。所以本报告引用的翻译接线不受它影响。

证据分三类，逐条标注：①**读到的原文**（源码、官方文档、已保存的原始探针输出、生产落盘记录）；②**命令输出**（本轮只读命令 / 只读探针所得）；③**我的推断**（明确标出，不与实测混写）。分量档位用「可据以行动 / 仅为倾向需更多样本 / 仅存档」。

## 1．核心结论表

| ID | 结论 | 分量 |
|---|---|---|
| DL-01 | `defer_loading` 是被 `translation_driver/openai_responses.py:140-153` 的 `_function_tool()` **原样透传**出去的。该函数不是白名单，而是「除 `input_schema` 外全部保留、再补 `type`/`parameters`」的**黑名单式复制**。任何客户端放在 Anthropic tool 上的未知字段都会原封不动出现在 Responses 请求体里。 | 可据以行动 |
| DL-02 | 泄漏没有留下任何 loss 记录。`Conversion` 里既没有 `defer_loading` 也没有 `cache_control` 的条目——它不是「有损转换」，是**无人察觉的直通**。 | 可据以行动 |
| DL-03 | `src/app/protocols/anthropic_responses.py` 的 `_TOOL_FIELDS` 与 `defer_loading` 分支**在今天的生产链上完全不跑**：其唯一入口 `convert_messages_request_to_responses` 全仓库只有测试引用。**同一模块里的 `ToolNameMapper` 仍是活的**，被 `protocols/responses_anthropic.py` 使用，而后者被生产代码引用。所以这是「模块活着、请求转换器死了」。 | 可据以行动 |
| DL-04 | **派发背景里有一处事实错误**：`anthropic_responses.py:541-546` 不是 `_degrade`，是 `self._fail(...)`，而 `_fail` 在 `:663-665` 是 `-> Never` 直接 `raise RequestConversionError`。那条旧路径对 `defer_loading` 的处置是**硬拒整个请求**，不是降级记账。 | 可据以行动 |
| DL-05 | Responses 端 `tool_search` 的合法形状是 `{"type": "tool_search"}`（可选 `execution: "server"|"client"`、`description`、`parameters`）。openai SDK 3.3.1 里有 `ToolSearchToolParam`，且 `FunctionToolParam` 自己就带 `defer_loading: bool`——**字段名与 Anthropic 逐字相同**，这正是它能穿过去并触发语义校验（而不是被当成未知字段忽略）的原因。 | 可据以行动 |
| DL-06 | 前身 `copilot-api-js` 在 Anthropic→Responses 翻译时**用白名单重建 tool 对象**，因此 `defer_loading` 被隐式丢弃，既不报错也不记账。它从未踩过这个 400。`CLIProxyAPIPlus` 则是**显式 `sjson.DeleteBytes(tool, "defer_loading")`**。两个参考实现的行为一致：剥掉。 | 可据以行动 |
| DL-07 | 同一条泄漏路径上还有三个未被处理的 tool-search 相关面：①`type: "tool_search_tool_regex_20251119"` 的服务端工具会**带着 Anthropic 的 type 原样发出**（`_is_anthropic_server_tool` 只认 `web_search_` 家族），必然 400；②`tool_result.content[]` 里的 `{"type":"tool_reference"}` 块会被 `_flattened_output` 压成 **空字符串 `output: ""`**，模型什么也看不到；③Claude Code 每个 tool 上的 `eager_input_streaming` 同样原样穿过。 | 可据以行动 |
| DL-08 | 现有测试**零覆盖**：`tests/` 里 `defer_loading` / `tool_search` / `tool_reference` 命中数为 0。唯一的 tool 翻译测试 `test_anthropic_tools_become_responses_function_tools` 虽然用了精确相等断言，但输入 tool 不带任何额外字段，对「多余字段泄漏」**没有任何鉴别力**。 | 可据以行动 |
| DL-09 | Responses 上游对 tool 上的**未知**字段是宽容的（不 400），今天已有 1013 次 `gpt-5.6-sol` 翻译腿请求 200。所以 `defer_loading` 的 400 不是「多了个字段」，而是「多了个**它认识**的字段，且前置条件不满足」。 | 仅为倾向需更多样本（推理链有一环未直接验证，见 §7.3） |

## 2．问题 1：`defer_loading` 是怎么进到 Responses 请求体里的

### 2.1 完整路径

**读到的原文，逐跳：**

1. **入站解析** —— `src/app/pipeline/translation_driver/anthropic_messages.py:133`：

   ```python
   tools=_dict_list(payload.get("tools")),
   ```

   `_dict_list` 在同文件（与 `openai_responses.py:47-51` 同名同构）只做 `dict[str, Any](...)` 浅拷贝，**不筛字段**。所以客户端 tool 对象的全部键原样进入 `SemanticRequest.tools`。

2. **路由与翻译接线** —— `src/app/pipeline/driver.py:153-160`：

   ```python
   if route.translation_required:
       translated, semantic = chain.translators.translate(
           context.payload,
           source=route.inbound_format,
           target=route.target_format,
           target_model=translation_target(provider, route.model_id),
       )
   ```

   `chain.translators` 由 `src/app/server/composition.py:509` 绑定为 `default_registry(config.model_translation)`；`registry.py:139-147` 把 `WireFormat.OPENAI_RESPONSES` 的 outbound 注册为 `to_openai_responses`。**这就是本次 400 走的那条链。**

3. **出站 tools** —— `src/app/pipeline/translation_driver/openai_responses.py:713-718` → `_tools_for_upstream()`（`:282-328`）→ 对非 web-search 声明走 `:319` 的 `_function_tool(tool, request.conversion)`。

4. **泄漏点** —— `openai_responses.py:140-153`：

   ```python
   def _function_tool(tool: dict[str, Any], conversion: Conversion) -> dict[str, Any]:
       tool = _coerced_description(tool, conversion)
       if "input_schema" not in tool:
           return tool
       converted = {key: value for key, value in tool.items() if key != "input_schema"}
       converted["type"] = tool.get("type", "function")
       converted["parameters"] = tool["input_schema"]
       return converted
   ```

**这是黑名单，不是白名单。** 唯一被排除的键是 `input_schema`；其余全部保留。`defer_loading`、`cache_control`、`eager_input_streaming`，以及任何未来的 Anthropic tool 字段，都会照原样出现在 Responses 的 `tools[]` 里。

对照同一文件里 web search 的处理（`:202-260` 的 `_web_search_tool`）：那里是**严格白名单 + 未知字段 `TranslationRefused`**，docstring 逐字写着「A field outside the allowed set refuses too, rather than being stripped」。**两种 tool 走的是两套完全相反的字段纪律，而普通 function tool 走的是宽松的那一套。**

### 2.2 只读探针（命令输出）

我在不改 `src/` 的前提下，用 `/tmp/probe_defer.py` 直接调 `default_registry().translate(...)`，输入一个同时包含 `defer_loading`、`cache_control`、`tool_search_tool_regex_20251119`、`tool_reference` 的 Anthropic body。实际输出的 `tools[]`：

```json
[
  {"name": "ToolSearch", "description": "search", "type": "function", "parameters": {"type": "object"}},
  {"name": "get_weather", "description": "w", "defer_loading": true, "type": "function", "parameters": {"type": "object"}},
  {"name": "tool_search_tool_regex", "type": "tool_search_tool_regex_20251119", "defer_loading": false},
  {"name": "Bash", "cache_control": {"type": "ephemeral"}, "type": "function", "parameters": {"type": "object"}}
]
```

`losses` 只有三条，且**没有一条与 tool 字段有关**：

```
tool-result-content-flattened: non-text tool result content for toolu_1
server-tool-not-carried: server_tool_use into openai-responses: flattened to text
server-tool-not-carried: tool_search_tool_result into openai-responses: flattened to text
```

**结论 DL-01、DL-02。** 读到的事实：`_function_tool` 保留全部未知键；探针复现了 `defer_loading: true` 出现在出站 body 里，且不产生 loss。我的推断：无。分量：可据以行动。

### 2.3 翻译之后没有第二道关

**读到的原文：**`src/app/pipeline/subscribers/__init__.py:50-112` 是唯一注册 builtin subscriber 的地方，六个 subscriber 里：

- `adapt_server_tools`（`server_tools.py:242-243`）第一行就是 `if context.target_format is not WireFormat.ANTHROPIC_MESSAGES: return`；
- `prune_cache_control_fields`（同伴今天新增的 `anthropic_cache_control.py`，未追踪）其 docstring 明确写「on the way to an **Anthropic Messages** upstream」；
- 其余（`hosted_web_search` gate、`anthropic_thinking`、`blank_text`、`trailing_assistant`）都不改 `tools` 数组的字段。

**没有任何一个 subscriber 在 Responses target 上清洗 `tools`。** 翻译输出即发出的字节。

## 3．问题 2：`protocols/anthropic_responses.py` 的 `_TOOL_FIELDS` 到底跑不跑

### 3.1 先证明有没有生产调用者

**命令输出**（`rg` 全仓库，排除 `.dev`）：

```
convert_messages_request_to_responses
  src/app/protocols/anthropic_responses.py:668   ← 定义
  src/app/protocols/anthropic_responses.py:712   ← __all__
  tests/unit/anthropic/test_anthropic_responses_request.py  ← 37 处调用，全在测试
```

`_TOOL_FIELDS`（`:40-42`）与 `defer_loading` 分支（`:541-546`）都在 `class _RequestConverter`（`:163`）内的 `_convert_tools()`（`:534-556`），而 `_RequestConverter` 的唯一构造点是 `:686` —— 也就是 `convert_messages_request_to_responses` 内部。

**所以：这条链上的生产调用者数为 0。**

### 3.2 但模块不是死的

**读到的原文** —— `src/app/protocols/__init__.py:3` 自己写着：

> The two modules still here, `anthropic_responses` and `responses_anthropic`, are imported by their consumers directly, which is what makes it possible to see who uses them.

反查得到：

- `anthropic_responses.ToolNameMapper`（`:109`）被 `protocols/responses_anthropic.py:14` import；
- `responses_anthropic` 被 `src/app/pipeline/translation_driver/responses.py:25` 与 `src/app/pipeline/delivery/formats/openai_responses.py:38` import —— **这两个都在生产响应链上**。

**结论 DL-03。** 读到的事实：请求转换器（含 `_TOOL_FIELDS`、`defer_loading` 分支、`_convert_tools`）是**死代码**，只有测试在维持它；同模块的 `ToolNameMapper` 是活代码。所以不能说「这个文件是死的」，也不能指望在这里改 `_TOOL_FIELDS` 会影响生产行为。我的推断：无。分量：可据以行动。

> 这正是项目记忆里「守卫被留在了 legacy 链路上」的第四次击发：守卫写得比新链路还严（它连 `defer_loading` 都会拒），但新链路根本不调用它。

### 3.3 对派发背景的一处更正

派发背景写的是「`:541-544` 有 `if tool.defer_loading:` → `_degrade(...)`」。**读到的原文是 `self._fail(...)`：**

```python
if tool.defer_loading:
    self._fail(
        f"{path}.defer_loading",
        "unsupported_field",
        "deferred tools are unsupported",
    )
```

而 `:663-665`：

```python
@staticmethod
def _fail(field_path: str, code: str, message: str) -> Never:
    raise RequestConversionError(message, code=code, field_path=field_path)
```

同一函数 `:539-540` 还有 `if tool.type is not None: self._fail(path, "server_tool_not_supported", ...)`——**任何带 `type` 的 tool 都会被硬拒**。这两条如果今天还生效，用户看到的不会是上游 400，而是本代理自己 400。差别在错误归属和可重试性上是实质性的，所以值得更正。**结论 DL-04，分量：可据以行动。**

## 4．问题 3：Responses 端 `tool_search` 的合法形状

### 4.1 官方文档（读到的原文）

来源：<https://developers.openai.com/api/docs/guides/tools-tool-search>（`platform.openai.com/docs/guides/tools-tool-search` 301 重定向至此）。

启用需要**两步**：

1. 在 `tools` 里放一个 `tool_search` 条目；
2. 给可延迟的 function（或 MCP server 定义）打 `defer_loading: true`。

托管形态的最小对象逐字为：

```json
{ "type": "tool_search" }
```

客户端执行形态额外带 `"execution": "client"`、`description` 和 `parameters`（搜索参数的 JSON schema）。

`defer_loading` 写在 function 定义内部：

```json
{
  "type": "function",
  "name": "list_open_orders",
  "description": "List open orders for a customer ID.",
  "defer_loading": true,
  "parameters": { "...": "..." }
}
```

文档另述：namespace 的 deferral 作用于其内含 function；托管搜索回传 `tool_search_call` / `tool_search_output`（`execution: "server"`、`call_id` 为 null），客户端模式需回传同一个 `call_id`；只有 `gpt-5.4` 及更新的模型支持。

### 4.2 SDK 类型（读到的原文）

`.venv/lib/python3.14/site-packages/openai/types/responses/tool_search_tool_param.py`：

```python
class ToolSearchToolParam(TypedDict, total=False):
    """Hosted or BYOT tool search configuration for deferred tools."""
    type: Required[Literal["tool_search"]]
    description: Optional[str]
    execution: Literal["server", "client"]
    parameters: Optional[object]
```

`function_tool_param.py:31-32`：

```python
defer_loading: bool
"""Whether this function is deferred and loaded via tool search."""
```

`tool_param.py:358-374` 的 `ToolParam` 联合里同时含 `FunctionToolParam`、`NamespaceToolParam`、`ToolSearchToolParam`、`CustomToolParam`、`ApplyPatchToolParam` 等；`defer_loading` 出现在 `function_tool`、`custom_tool`、`namespace_tool` 和 `mcp` 四处。

### 4.3 GHC 上游确实认这个 type（读到的原文）

本项目已保存的探针输出 `exp/260820-websearch-probe/raw/B2-responses-anthropic-spelling-response.txt:5`（针对 `api.enterprise.githubcopilot.com` 的 `/responses`）：

> `"message": "Invalid value: 'web_search_20250305'. Supported values are: 'code_interpreter', 'programmatic_tool_calling', 'function', 'namespace', **'tool_search'**, 'file_search', 'web_search_preview', 'web_search_preview_2025_03_11', 'image_generation', 'mcp', 'custom', 'computer', 'computer_use_preview', 'shell', and 'apply_patch'."`

**`tool_search` 就在上游自己打印的可接受枚举里。** 这条是 2026-08-20 的保存输出，不是本轮实测。

**结论 DL-05。** 读到的事实：合法形状是 `{"type": "tool_search"}`（+ 可选三个字段）；`defer_loading` 在 Responses 侧是**同名同义**的一等字段。**我的推断**：正因为同名，Copilot 网关走的是「认识这个字段 → 检查前置条件 → 报 `Deferred tools require tools.tool_search`」，而不是「不认识 → 忽略或报 Unknown parameter」。分量：可据以行动。

**未做的事**：我**没有**对 `/responses` 实测 `{"type":"tool_search"}` 是否真被接受、是否真执行搜索。上游的枚举打印是它自己的可接受列表，但「列在枚举里」与「这个部署真的会跑」是两件事（`web_fetch` 就是反例：它不在枚举里，直接被拒）。要把「映射成 tool_search」当成修复方案，这一步必须先实测。

## 5．问题 4：前身 `copilot-api-js` 怎么处理

### 5.1 结论：白名单重建，隐式丢弃（读到的原文）

`copilot-api-js/src/lib/translation/from-ir/openai-responses/parameters.ts:92-114`：

```typescript
export function translateTools(tools: Array<AnthropicTool>, reqId: string | undefined): Array<ResponsesTool> {
  const out: Array<ResponsesTool> = []
  for (const tool of tools) {
    const namedChoice = translateNamedToolChoice(tool)
    if (!namedChoice) { dropWarn(...); continue }
    if (namedChoice.type !== "function") { out.push(namedChoice); continue }
    out.push({
      ...namedChoice,
      ...(tool.description !== undefined && { description: tool.description }),
      ...(tool.input_schema !== undefined && { parameters: tool.input_schema }),
    } satisfies ResponsesFunctionTool)
  }
  return out
}
```

`translateNamedToolChoice`（`:79-83`）对普通 tool 只返回 `{ type: "function", name: tool.name }`。所以输出对象**只有四个键**：`type`、`name`、`description?`、`parameters?`。

`defer_loading` 从来没有机会进去。这既不是「剥掉」也不是「映射」，而是**结构上不可能泄漏**——它是用白名单重建，不是复制再删。

调用点：`bridges/anthropic-to-responses-request-via-ir.ts:80` 与 `legacy-direct/anthropic-to-responses-request.ts:208`，两条路径都用同一个 `translateTools`。

**代价也读到了**：这个白名单会把 `cache_control`、`eager_input_streaming`、以及任何未来字段一并丢掉，且**不记账**（只有走到 `dropWarn` 那条分支的 server tool 才有日志）。

### 5.2 旁证：`CLIProxyAPIPlus` 是显式删除

`refs/CLIProxyAPIPlus/internal/translator/codex/claude/codex_claude_request.go:252-269`（Claude → Codex/Responses）：

```go
tool, _ = sjson.SetBytes(tool, "type", "function")
...
tool, _ = sjson.SetRawBytes(tool, "parameters", []byte(normalizeToolParameters(...)))
tool, _ = sjson.DeleteBytes(tool, "input_schema")
tool, _ = sjson.DeleteBytes(tool, "parameters.$schema")
tool, _ = sjson.DeleteBytes(tool, "cache_control")
tool, _ = sjson.DeleteBytes(tool, "defer_loading")
tool, _ = sjson.SetBytes(tool, "strict", false)
```

同一个删除在 `gemini/claude/gemini_claude_request.go:192` 与 `gemini-cli/claude/gemini-cli_claude_request.go:159` 也各有一份。**它跟本项目一样是「复制再删」的黑名单结构，因此必须显式点名 `defer_loading`——而它点了。**

**结论 DL-06。** 读到的事实：两个参考实现都不把 `defer_loading` 发到 Responses；前身靠白名单结构，`CLIProxyAPIPlus` 靠显式删除。两者都没有映射成 `tool_search`。我的推断：前身没踩过这个 400（它的 tool 对象根本长不出这个键）。分量：可据以行动。

## 6．问题 5：同一条泄漏路径上还有哪些面

四个面，全部由 §2.2 的同一次只读探针复现。

### 6.1 `type: "tool_search_tool_regex_20251119"` 的服务端工具 → 必然 400

**读到的原文** —— `openai_responses.py:161`：

```python
_ANTHROPIC_SERVER_TOOL_FAMILIES: tuple[str, ...] = ("web_search_",)
```

`_is_anthropic_server_tool`（`:182-199`）只匹配这一个家族。`tool_search_tool_regex_20251119` 不匹配 → 落到 `_function_tool` → 因为它没有 `input_schema`，命中 `:148-149` 的 `if "input_schema" not in tool: return tool` → **整个对象原样返回，Anthropic 的 `type` 一字不改地发出去**。

探针输出逐字为 `{"name": "tool_search_tool_regex", "type": "tool_search_tool_regex_20251119", "defer_loading": false}`。

对照 §4.3 上游的枚举，这必然得到 `Invalid value: 'tool_search_tool_regex_20251119'. Supported values are: ...`——与 2026-08-20 `web_search_20250305` 那次同形。

**触发条件**：Claude Code 2.1.241 按前一份报告 TS-02 走的是「客户端执行的自定义 ToolSearch」，**不会**自行加入这个 server tool；VS Code Copilot Chat 会（`refs/vscode-copilot-chat/src/platform/networking/common/anthropic.ts:73` 定义 `TOOL_SEARCH_TOOL_TYPE = 'tool_search_tool_regex_20251119'`，`messagesApi.ts:136` 推入 `finalTools`）。所以这是**尚未观测到、但客户端一换就命中**的面。分量：可据以行动（代码路径确定），触发概率：仅为倾向。

### 6.2 `tool_result.content[]` 里的 `tool_reference` → 静默变成空字符串

**读到的原文** —— `openai_responses.py:535-561` 的 `_flattened_output`：

```python
for part in cast(list[object], output):
    if isinstance(part, Mapping):
        entry = cast(Mapping[str, Any], part)
        if str(entry.get("type", "")) == "text":
            texts.append(str(entry.get("text", "")))
            continue
    dropped = True
if dropped:
    conversion.record(LossCode.TOOL_RESULT_CONTENT_FLATTENED, f"non-text tool result content for {block.call_id}")
return "".join(texts)
```

一个 `content` 全是 `tool_reference` 块的 `tool_result`，`texts` 为空列表，返回 `""`。探针输出逐字为：

```json
{"type": "function_call_output", "call_id": "toolu_1", "output": ""}
```

**这不会 400**（`output` 仍是合法字符串），但它是本次调查里**最阴的一个**：模型调用了 ToolSearch，代理把搜索结果吃掉了，回给模型一个空串。模型看到「我搜了，什么都没搜到」，然后大概率会再搜一次，得到同样的空串。

有 loss 记录（`tool-result-content-flattened`），所以不是完全无声，但记录的措辞是「non-text tool result content」，读的人不会意识到这一整轮工具发现被清零了。

**这一条决定了「只剥 `defer_loading`」是不是完整修复**：剥掉 `defer_loading` 后请求不再 400，Claude Code 仍会把候选工具交给模型（因为 Anthropic 语义下 `defer_loading` 只是「先不进上下文」，完整定义每次都发），所以**功能上基本可用**；但如果客户端已经进入了「调 ToolSearch → 回传 tool_reference」的循环，第二轮就会撞上这个空串。分量：可据以行动。

### 6.3 `eager_input_streaming` 同样穿过去（生产落盘证据）

**读到的原文** —— 生产落盘 `~/.local/share/ghc-api-proxy/rejected/20260824T103948.240-400-530e0e10-c724-45a0-964a-129c3351646a.json`，一次真实 Claude Code 请求（29 个 tool，179 KB）。逐 tool 的键集合**全部**是：

```
['description', 'eager_input_streaming', 'input_schema', 'name']
```

即：这一版 Claude Code 在**每一个** tool 上挂 `eager_input_streaming`，且这次请求里**没有** `cache_control`、**没有** `defer_loading`（这次 tool search 没开，它 400 在 `thinking.type.enabled`，与本题无关）。

按 §2.1 的路径，`eager_input_streaming` 会原样进入 Responses `tools[]`。前身 `copilot-api-js/src/lib/anthropic/message-tools.ts:415` 有：

```typescript
export const BUILTIN_STRIP_TOOL_FIELDS: ReadonlyArray<string> = ["eager_input_streaming"]
```

其注释说 GHC 的 **Anthropic** upstream 会以 `tools.N.custom.eager_input_streaming: Extra inputs are not permitted` 拒绝它。**注意这是 Anthropic 腿的事实，不能直接搬到 Responses 腿。**

### 6.4 `cache_control` 也穿过去

探针输出里 `{"name": "Bash", "cache_control": {"type": "ephemeral"}, "type": "function", "parameters": {...}}`。同一文件 `:170` 的 `_WEB_SEARCH_IGNORED = frozenset({"type", "name", "cache_control"})` 只对 web search 生效；普通 function tool 上的 `cache_control` 无人处理。

系统提示词那一侧是有处理的（`_instructions_value` `:106-117` 记 `SYSTEM_METADATA_NOT_CARRIED`，文件头 docstring 写明 `Unknown parameter: 'input[0].content[0].cache_control'` 是实测的），**唯独 tool 上的没有**。

§6.3 的生产样本显示这一版 Claude Code 没在 tool 上放 `cache_control`，所以今天不触发；但这是客户端版本决定的，不是我们挡住的。

## 7．问题 6：现有测试覆盖

### 7.1 命中数为 0（命令输出）

```
$ rg -n "defer_loading|tool_reference|tool_search" tests -g '!*.json'
0 matches / 0 files (116 files searched)
```

### 7.2 唯一的 tool 翻译测试没有鉴别力

`tests/unit/pipeline/translation_driver/test_translation_driver.py:78-101`：

```python
def test_anthropic_tools_become_responses_function_tools() -> None:
    """Passing Anthropic's `input_schema` through earns `One of the tools requested is invalid.`"""
    payload, _ = default_registry().translate(
        {**ANTHROPIC_REQUEST, "tools": [{"name": "get_time", "description": "...", "input_schema": {...}}]},
        source=WireFormat.ANTHROPIC_MESSAGES, target=WireFormat.OPENAI_RESPONSES,
    )
    assert payload["tools"] == [{"type": "function", "name": "get_time", "description": "...", "parameters": {...}}]
```

断言形式是精确相等（`==` 整个列表），本身是有力的形状；但**输入 tool 只带四个已知键**，所以「多余字段会不会泄漏」这个命题在这条测试里根本没被提出。它今天是绿的，明天泄漏一百个字段它还是绿的。

**结论 DL-08。** 读到的事实：零覆盖，且既有测试对本缺陷零鉴别力。我的推断：无。分量：可据以行动。

### 7.3 关于「上游宽容未知 tool 字段」这条，我的把握到哪儿

**命令输出**（今天的生产落盘 `~/.local/share/ghc-api-proxy/requests/requests-20260824.jsonl`，按 `losses` 含 `openai-responses` 筛选）：

```
[(('gpt-5.6-sol', 200), 1013), (('gpt-model', 200), 1)]
had tool_use blocks: {True: 763, False: 251}
```

**1013 次翻译腿请求全部 200，其中 763 次含工具使用。**

**我的推断链**：这些请求来自与 §6.3 那次落盘同一台机器、同一时段、同一个 Claude Code 安装 → 它们的 tools 也带 `eager_input_streaming` → 因此 Responses 上游对**未知** tool 字段不 400 → 因此 `defer_loading` 的 400 是「已知字段 + 前置条件不满足」的语义校验，不是「多了个字段」。

**这条链有一环没有直接验证**：请求记录（`requests-*.jsonl`）**不存 body**（键只有 `at/status/…/tools/losses` 等，`tools` 只是名字列表），所以我无法逐条证明那 1013 次的出站 body 里确有 `eager_input_streaming`。落盘 body 只在 `rejected/` 目录里有，且只有被拒的那些。

**因此 DL-09 标为「仅为倾向需更多样本」**，不标「可据以行动」。它影响的是**修复方案的选择理由**（如果上游其实会拒未知字段，那就应该整体收白名单而不只是删一个键），不影响「`defer_loading` 必须处理」这个结论本身。

要把它升到「可据以行动」，最便宜的办法是：对 `/responses` 发一个带 `eager_input_streaming` 的 function tool 做一次单点实测（正控制 + 变量各一发）。**我没有做，因为那是真实计费调用且超出「只调查取证」的授权范围。**

## 8．我排除了什么（硬性要求）

1. **排除「`_TOOL_FIELDS` 白名单包含 `defer_loading` 是本次泄漏的原因」。** 派发背景把这两件事放在一起，容易读成因果。实际上 `_TOOL_FIELDS` 是**接受**列表（`_reject_extras` 用它判断哪些字段不算「多余」），而下一行的 `_fail` 才是处置；更重要的是整条链在生产上不跑（DL-03）。它既不是原因，也不是能改的地方。

2. **排除「翻译之后有 subscriber 会把它清掉，所以问题在 subscriber 的顺序或条件上」。** 逐个读了注册表里全部六个 subscriber（`subscribers/__init__.py:50-112`）；两个显式 gate 在 `ANTHROPIC_MESSAGES` target 上返回，其余不碰 `tools` 字段。没有可调的顺序。

3. **排除「`src/app/config/settings.py:90` 的 `tool_search: bool = True` 与本次有关」。** 该字段属于已退出生产的旧 `AppSettings`（`config/loader.py` 模块 docstring 自述 "no longer serves any production path"），前一份报告 TS-01 已用三种 reader 搜法确认无读者；我本轮复查 `rg "tool_search" src` 也只命中定义与注释。**它是同名巧合，不是开关。**

4. **排除「把 `anthropic-beta: tool-search-tool-*` 补回去就能解决」。** 那是 Anthropic 腿的问题（前一份报告 TS-03/TS-04）。本次是 Responses 腿，而 `request_headers.py:47-48` 的 `TRANSLATED_PATH_WHITELIST = ()` 意味着**翻译腿一个客户端 header 都不转发**，`anthropic-beta` 从来就没到过 `/responses`。Responses 端也没有 beta 机制。

5. **排除「上游把 `defer_loading` 当未知字段拒了」。** 上游的错误措辞是 `Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.`，而它对真正的未知字段用的是另一套措辞（`Unknown parameter: 'tools[0].max_uses'`，见 `openai_responses.py:172`；`Unknown parameter: 'input[0].content[0].cache_control'`，见文件头 docstring）。**两种措辞不同，说明是两条不同的校验路径。** SDK 类型（§4.2）也证实它是一等字段。

6. **排除「前身 `copilot-api-js` 里某处显式处理了 `defer_loading` 的翻译」。** `rg "defer_loading" src/lib/translation src/lib/codec` 在前身仓库返回 exit 1（零命中）。前身对 `defer_loading` 的全部代码都在 **Anthropic 腿**：`lib/request/strategies/deferred-tool-retry.ts:105,125,153-155`（把 sticky tool 的 `defer_loading` 改成 false 后重试）、`types/api/anthropic.ts:102`（类型定义）。翻译腿上一个字都没有——**因为白名单让它不需要有。**

7. **查了但不相关的来源：**
   - `refs/vscode-copilot-chat`：它是 **Anthropic Messages** 客户端，`messagesApi.ts:126,136` 构造的是 Anthropic 形态的 `defer_loading` 与 `tool_search_tool_regex_20251119`。它**不构造 Responses 请求**，所以对「Responses 端形状」没有第一手价值。唯一有用的产出是 §6.1 的触发条件（它会发那个 server tool）。
   - `refs/CLIProxyAPIPlus` 的 `openai_responses_websocket_test.go`：命中 `apply_patch` 只是因为它出现在测试 fixture 的 `custom_tool_call` 里，与 tool search 无关。有用的只有 §5.2 的三处 `DeleteBytes`。
   - `refs/agent-maestro`、`refs/awsl-maxx`、`refs/caozhiyuan-copilot-api`、`refs/hooyao-copilot-bridge`、`refs/ghc-api-py`：未查。理由是前四个来源已给出一致且互相独立的答案（官方文档 + SDK 类型 + 两个参考实现 + 上游自己的枚举打印），再加样本的边际价值低于成本。**这是我主动做的取舍，写在这里以便复核。**
   - `WebSearch` 工具本轮**两次调用均返回 `Web search error: unavailable`**。§4.1 的文档内容是用 `WebFetch` 直接取的（先 301，再取重定向后的 URL）。

8. **排除「用生产记录复现出站 body」这条取证路线。** `requests-*.jsonl` 不存 body（§7.3）；`rejected/` 只存被拒请求，且其中没有一条含 `defer_loading`（`rg -l "defer_loading|Deferred tools" rejected/` 零命中）。用户报的 `req=fcc0bebc-…` 在四天的 `requests-*.jsonl` 里也搜不到，**推测**它来自另一个进程实例（例如 4142 canary）或早于当前日志文件。所以本报告的出站 body 证据是**只读探针复现**，不是生产捕获——这两者的分量不同，我按前者标注。

9. **没有排除、但明确未做**：`{"type":"tool_search"}` 对 GHC `/responses` 的真实接受性实测（§4.3 末段）；`eager_input_streaming` 对 `/responses` 的真实接受性实测（§7.3 末段）。两者都需要真实计费调用，超出本次「只调查取证」的授权。

## 9．修复选项对比（不替用户裁决）

前置事实：泄漏点是**一个函数、一处结构选择**（`_function_tool` 用黑名单复制而非白名单重建）。所以下面每个选项的改动量都不大，差别在**语义承诺**和**未来的失效方式**。

### 选项 A：翻译时剥掉 `defer_loading` 并记 loss

**做法**：在 `_function_tool` 里点名删除 `defer_loading`，走 `conversion.record(...)`，新增一个 `LossCode`（现有枚举里没有合适的；注意项目记忆「枚举加成员会给每张以它为键的表造缺项」——需要检查所有以 `LossCode` 为键的表）。

**代价**：客户端要求的延迟加载被关闭。按 Anthropic 语义，`defer_loading: true` 只影响「是否预先进入模型上下文」，完整定义每个请求都在发，所以**功能不丢，丢的是上下文预算优化**。对 29 个工具的 Claude Code 会话，这意味着所有工具 schema 都进上下文——原本就是今天的现状（今天 1013 次成功请求都是这样跑的）。

**风险**：
- 低。这是 `CLIProxyAPIPlus` 的做法，也是前身白名单的等效结果。
- 但它是**黑名单再加一项**。下一个 Anthropic 新增的 tool 字段仍会泄漏，而且下一次仍然会以 400 的形式在生产暴露。项目记忆「守卫被绕过时先想清楚要不要换形状」在这里适用。
- `tool_reference` 空串（§6.2）不受此修复影响，仍然存在。

### 选项 B：整体换成白名单（前身的形状）

**做法**：`_function_tool` 改为只输出 `{type, name, description?, parameters?}`，未在白名单内的键统一记一条 loss。

**代价**：一次性把 `defer_loading`、`cache_control`、`eager_input_streaming` 以及未来字段全部挡住。相比 A 多丢的是 `eager_input_streaming`（按前身注释是纯流式优化，**实测无行为差异**）和 tool 上的 `cache_control`（Responses 端不需要，它自己按前缀缓存——文件头 docstring 有 2026-08-18 实测支撑）。

**风险**：
- 中低。白名单会挡住一个**将来有意义**的字段，而且是**静默**挡住（只留 loss 记录）。这与 `_web_search_tool` 现有的纪律相反：那里对未知字段是 `TranslationRefused`（拒绝而非静默丢弃），docstring 逐字论证过「silently removing one turns whatever it asked for into a no-op」。
- **两种 tool 采用相反的未知字段纪律，本身就是一个需要用户裁决的设计分歧**，不是我能替他定的。
- 与 A 相比，它把「下一个字段」的失效方式从「生产 400」换成「静默降级」。哪个更可接受取决于用户对这两类失效的偏好。

### 选项 C：映射成 Responses 的 `tool_search`

**做法**：当 `tools[]` 里存在任何 `defer_loading: true` 时，向出站 `tools[]` 追加 `{"type": "tool_search"}`（若客户端自己声明了 ToolSearch 这类客户端执行的工具，可能应为 `{"type":"tool_search","execution":"client",...}`），保留 `defer_loading` 原样。

**代价**：改动最大，且**需要先做实测**（§4.3、§8.9）：`{"type":"tool_search"}` 对 GHC `/responses` 是否真被接受、是否真按 server 模式执行。上游打印的枚举只证明它认识这个名字。

**风险**：
- 高，且是**语义风险**而非机械风险。托管 tool search 意味着**上游代替客户端执行工具发现**，而客户端（Claude Code）已经声明了自己的客户端执行 ToolSearch 工具。两个搜索器同时存在，谁来回答 `tool_search_call`、`call_id` 怎么对上，都是本项目没有测过的形状。
- 官方文档明确「搜索工具自身不得 deferred」「至少一个 tool 必须 non-deferred」。Anthropic 侧我们已实测到 `At least one tool must have defer_loading=false. All tools cannot be deferred.`（`exp/260824-beta-and-cache-control-probe/raw/run-main.txt:12`）。Responses 侧同类约束是否一致、错误措辞如何，未知。
- 还要处理 §6.2 的 `tool_reference` 回传：Responses 期待的是 `tool_search_call` / `tool_search_output` 项，而不是 Anthropic 的 `tool_reference` 块。**选 C 就必须一并解决 §6.2，否则第二轮必然坏。**
- 唯一的好处是：它是**不损失客户端意图**的方案。上下文预算优化真的被保住了。

### 选项 D：在翻译腿上拒绝（`TranslationRefused`）

**做法**：像 `_web_search_tool` 对未知字段那样，遇到 `defer_loading` 就抛 `TranslationRefused`，让代理自己给出结构化错误，而不是把 400 让上游报。

**代价**：客户端拿不到答案，但拿到的是**我们写的、说清了原因的**错误，而不是上游的 `invalid_request_body`。

**风险**：
- 对**用户体验**是纯负面（今天至少还有 400 可以看，改成拒绝后依然不能用）。除非配合 A/B/C 之一作为「未知字段」的兜底纪律，单用没有意义。
- 值得单独考虑的是把 D 用在 §6.1 的 `tool_search_tool_regex_*`：那个必然 400，提前拒绝至少能给出准确的字段路径。

### 独立于上面四选一的两项

- **§6.2 的 `tool_reference` 空串**：无论选 A/B/C/D，这一条都还在。最小修复是让 `_flattened_output` 对 `tool_reference` 块渲染成文本（例如 `[tool_reference] get_weather`），与 `server_tool_text.py` 现有的扁平化措辞保持一致——项目已有「一份历史、一种形状」的先例（`server_tools.py` docstring `:17`）。
- **§6.1 的 `tool_search_tool_regex_*`**：`_ANTHROPIC_SERVER_TOOL_FAMILIES` 只有 `web_search_` 一项，这个家族的处置是空白。今天不触发（Claude Code 不发），换客户端就触发。

### 回归测试的最小形状

无论选哪个，`test_anthropic_tools_become_responses_function_tools` 都应补一个**带多余字段**的输入（§7.2）。项目记忆「先证明这个绿有分辨力」在这里直接适用：先把断言写好、确认它对今天的代码是**红**的，再动实现。

## 10．承重检查

- 前提「`_function_tool` 是黑名单复制」支撑结论 DL-01/DL-07 全部四个泄漏面。若该前提为假，全部反转——因此我既读了源码，也用只读探针跑了真实注册表复现，两路互证。
- 前提「`convert_messages_request_to_responses` 无生产调用者」支撑 DL-03「不要去改 `_TOOL_FIELDS`」。若为假，修复位置就错了——因此我查了三层：函数名全仓库引用、`_RequestConverter` 的唯一构造点、以及模块内另一个符号（`ToolNameMapper`）的活跃引用链，避免把「模块被 import」误读成「这条链在跑」。
- 前提「上游宽容未知 tool 字段」支撑的是**选项 A 够不够**这个判断，而**不是**「必须处理 `defer_loading`」。我把它单独标成较低分量（§7.3），正是为了让它塌了也不牵连主结论。

## 11．整体判定

- 问题 1-6 全部回答，均有 `文件:行号` 一手证据。
- 未执行任何写操作到 `src/`；本轮唯一写入是本文件与 `/tmp/probe_defer.py`（一次性只读探针）。
- 两处需要真实上游实测才能收口的点已在 §8.9 点名，未擅自执行。
- 派发背景中的一处事实错误已更正（DL-04）。
