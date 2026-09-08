# Tool search 翻译：识别判据与两侧往返形状调查

日期：2026-08-25
调查者：investigator subagent（只读；未修改 `src/`）
基线：仓库 HEAD `e7f10d7`；openai SDK 3.3.1；anthropic SDK 1.0.0；Claude Code 参考源 `~/.claude/refs/claude-code-2.1.{207,226,241}`
起因：用户裁定客户端发来的 tool search 要**翻译**到 Responses 侧而非剥掉，需要先查清识别判据与两侧线上形状。

> **本报告不是权威落点。** 其中问题 4 的第 3 条（流式路径把未知 output item 变成空 text 块）是本文新增的事实，spec 尚未记录；按项目规则它必须落到 `spec.md` 而不是停在这份报告里。见文末「交回主会话」。

---

## 摘要（先说结论）

1. **不存在协议级判据能识别「哪个 function tool 是客户端的搜索工具」。** 官方文档明确说自定义实现就是「一个普通的 custom tool」，除了它返回 `tool_reference` 之外没有任何声明侧标记；官方 SDK 没有任何 helper、类型或字段表达这件事。两个真实客户端各自用**自己硬编码的工具名**识别自己的搜索工具，且两者名字不同（Claude Code 用 `ToolSearch`，VS Code Copilot Chat 用 `tool_search`）——这坐实了名字是应用私有约定，不是协议约定。
2. 可用的识别信号只有启发式，且**最强的那条要到下一轮才可观测**（上一轮的 `tool_result` 里出现过 `tool_reference`）。声明侧仅有的信号是「本请求里存在 `defer_loading: true` 的工具」——它只说明「有搜索机制在运作」，不指出是哪个工具。
3. Responses 侧客户端执行的往返是 **`tool_search_call`（output）→ `tool_search_output`（input）**，没有 `tool_search_call_output` 这个类型。关键不对称：Anthropic 回传的是**工具名引用**，Responses 回传的是**完整工具定义数组**。本代理手上有 Anthropic `tools[]` 全量定义，所以这个展开是可做的。
4. 本项目响应侧今天对未知 output item 有**两条不一致的处置**：缓冲路径丢弃 + 记 `ITEM_NOT_CARRIED`；**流式路径发出一个空 text 块**（已实测复现，带控制）。后者是本次新发现。

---

## 问题 1：怎么识别「哪个 function tool 是客户端的搜索工具」

### 1.1 官方文档：明确说没有标记

来源：<https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool>，「Custom tool search implementation」一节（2026-08-25 取回全文）。

原文（逐字）：

> You can implement your own tool search logic (for example, using embeddings or semantic search) by returning `tool_reference` blocks from a custom tool. When Claude calls your custom search tool, return a standard `tool_result` with `tool_reference` blocks in the content array

> Every tool referenced must have a corresponding tool definition in the top-level `tools` parameter, normally with `defer_loading: true`.

> The `tool_search_tool_result` format shown in the Response format section is the server-side format used internally by Anthropic's built-in tool search. For custom client-side implementations, always use the standard `tool_result` format with `tool_reference` content blocks as shown in the preceding example.

**读到的原文里没有任何命名约定、必需的 `input_schema` 形状、或声明侧标记字段。** 全文中唯一被规定的识别面是**输出**：这个工具的 `tool_result.content[]` 里有 `tool_reference` 块。文档也没有提供「把自定义搜索工具告诉 API」的任何机制——API 根本不需要知道是哪个工具，它只是在展开它看到的 `tool_reference`。

**分量：可据以行动。** 这是本条问题的一手权威原文，且是排除性结论（找不到 ≠ 没找全，但文档对这一节是完整成段的，且 SDK 与两个真实客户端三处独立印证了同一结论）。

### 1.2 官方 Python SDK：没有相关 helper

- `anthropic/lib/tools/_beta_functions.py:152,168,195-196` —— `beta_tool(..., defer_loading=...)` 只把布尔写进定义：`defn["defer_loading"] = self._defer_loading`。它是**普通 function tool 的一个字段**，与「谁来搜索」无关。
- `anthropic/lib/tools/mcp.py:359,406,421,466` —— MCP toolset 上的同名参数，同样只是透传。
- 类型侧只有两个与搜索相关的结构，且都属于**托管**路径：`anthropic/types/tool_search_tool_result_block.py:15-20`（`tool_search_tool_result`）与 `anthropic/types/tool_search_tool_search_result_block_param.py:13-15`（`tool_search_tool_search_result`，内含 `tool_references`）。
- 客户端侧唯一的类型是 `anthropic/types/tool_reference_block_param.py:13-21`，其 docstring 逐字为 `"""Tool reference block that can be included in tool_result content."""`，字段只有 `tool_name` / `type` / `cache_control`。
- `anthropic/types/tool_result_block_param.py:18-25` 确认 `ToolReferenceBlockParam` 是 `tool_result.content` 联合的合法成员。

SDK 里**没有** `is_search_tool`、没有 `search_tool=True` 装饰参数、没有 examples 目录里的自定义搜索样例（`anthropic/` 包内无 `examples/`）。

**分量：可据以行动。**

### 1.3 Claude Code 实测：工具名与描述是硬编码常量，跨三个版本稳定

`~/.claude/refs/claude-code-2.1.241/app.pretty.js`：

- **`:121173`** —— `var SH = "ToolSearch", MGr = "DeferredToolPlaceholder", Yui = "Reserved placeholder that keeps deferred tool loading active; never call this tool.";`
- **`:333714,333720`** —— 工具对象 `pio = ss({ ..., name: SH, ... })`，即工具名逐字为 `ToolSearch`；`description` 与 `prompt` 都取 `Fgi()`。
- **`:333713`** —— `inputSchema` 为 `{ query: string, max_results?: number = 5 }`，`query` 的 describe 逐字为 `Query to find deferred tools. Use "select:<tool_name>" for direct selection, or keywords to search.`；`outputSchema` 为 `{ matches: string[], query, total_deferred_tools, pending_mcp_servers?, failed_mcp_servers? }`。
- **`:152381-152393`** —— `Fgi()` 拼出的描述，开头逐字为 `Fetches full schema definitions for deferred tools so they can be called.\n\nDeferred tools appear by name in <system-reminder> messages.`，尾部列出三种 query 形式（`select:Read,Edit,Grep` / 关键词 / `+slack send`）。
- **`:152363-152377`** —— `isDeferredTool(e)`：`if (e.name === SH) return false;`，即 **ToolSearch 自身永不 deferred**。
- **`:333848`** —— 结果映射逐字为 `return { type: "tool_result", tool_use_id: t4, content: e.matches.map((r2) => ({ type: "tool_reference", tool_name: r2 })) };`
- **`:428149`** —— 另有一个占位工具：`{ name: "DeferredToolPlaceholder", description: "Reserved placeholder that keeps deferred tool loading active; never call this tool.", input_schema: { type: "object", properties: {} }, defer_loading: true }`，在 `:428871` 被插进 tools 数组（当数组里还没有同名工具时）。
- **`:427751-427756`** —— 出站 tool 的字段构造：`{ name, description, input_schema, strict?, eager_input_streaming? }`，`if (t4.deferLoading) p.defer_loading = true`。

跨版本稳定性（实测三个版本）：

| 版本 | `= "ToolSearch", ... = "DeferredToolPlaceholder"` 常量行 | 描述首句 |
|---|---|---|
| 2.1.207 | `:69699` | `:148657` |
| 2.1.226 | `:74884` | `:128659` |
| 2.1.241 | `:121173` | `:152381` |

三个版本逐字相同（只有 minify 后的变量名不同）。**分量：可据以行动**（跨三版本样本，且是常量而非配置项——源码里没有任何读配置改这个名字的路径）。

#### Claude Code 什么条件下才发这套东西 —— 对本代理直接相关

`app.pretty.js:118755-118767`，`gj()` 即 ToolSearchTool 的 `isEnabled`：

```
function gj() {
  let e = dGr();
  if (e === "standard") { ...; return false; }
  if (!q.ENABLE_TOOL_SEARCH && !sui() && lo() === "firstParty" && !Fm()) {
    ... `[ToolSearch:optimistic] disabled: ANTHROPIC_BASE_URL=${q.ANTHROPIC_BASE_URL} is not a first-party Anthropic host. Set ENABLE_TOOL_SEARCH=true (or auto / auto:N) if your proxy forwards tool_reference blocks.`
    return false;
  }
  return true;
}
```

`Fm()`（`:64597-64604`）在 `ANTHROPIC_BASE_URL` 未设或指向 Anthropic 官方域名时为 true。**所以：指向本代理的 Claude Code，默认不发 ToolSearch，也不发 `defer_loading`，除非用户显式设了 `ENABLE_TOOL_SEARCH`。** 日志文案本身就点名了这个场景（"if your proxy forwards tool_reference blocks"）。

**分量：可据以行动，但有一个盲点必须说清**——这是读源码得出的门控条件，我没有实测「设了 `ENABLE_TOOL_SEARCH=true` 之后本代理收到的请求长什么样」。要把翻译做成可验收的，需要一次真实抓包。

顺带：Claude Code **不发**托管的 `tool_search_tool_regex_20251119`。三个版本里该字符串只出现在 `:482834`（一张 Anthropic 托管 server tool 名字集合，用于识别**入站**块）与 `:583702`（一段 PHP 文档示例）——没有任何构造请求的路径写它。这与 spec.md:151 的记述一致。

### 1.4 VS Code Copilot Chat：也是硬编码名字，且名字不同

`/home/xp/src/refs/vscode-copilot-chat/src/platform/networking/common/anthropic.ts:75-76`：

```ts
/** Name for the custom client-side embeddings-based tool search tool. Must not use copilot_/vscode_ prefix — those are reserved for static package.json declarations and will be rejected by vscode.lm.registerToolDefinition. */
export const CUSTOM_TOOL_SEARCH_NAME = 'tool_search';
```

识别处 `src/platform/endpoint/node/messagesApi.ts:306`：

```ts
const isCustomToolSearch = validToolNames && toolCallIdToName.get(message.toolCallId) === CUSTOM_TOOL_SEARCH_NAME;
```

即：按 `tool_use.id → name` 的映射，拿工具名与自己的常量比对。它随后 `tryParseToolReferences`（`:358-377`）把该工具返回的「一个 text 块，内含 JSON 字符串数组」转成 `tool_reference` 块，并按 `validToolNames` 过滤（`:186-190` 的注释说明这是为了避开未知工具名导致的 400）。

它同时会走托管路径：`:136` 在 `!customToolSearchEnabled` 时 push `{ name: 'tool_search_tool_regex', type: 'tool_search_tool_regex_20251119', defer_loading: false }`。

**这是本调查里最有价值的一条旁证**：两个一线客户端都用「我自己定义的那个名字」识别自己的搜索工具，而这两个名字不一样。它同时证明了两件事——(a) 名字不是协议约定；(b) 在**代理**位置上按名字识别，本质是在猜某个特定客户端。

**分量：可据以行动。**

### 1.5 其他参考实现怎么处理

| 项目 | 处理 | 证据 |
|---|---|---|
| `caozhiyuan-copilot-api` | 把 `tool_reference` 降级成一句文本 `Tool ${name} loaded` | `src/routes/messages/responses-translation.ts:776-779`、`src/routes/messages/non-stream-translation.ts:250-256` |
| `copilot-api-js`（前身） | **反向**：代理自己注入托管 `tool_search_tool_regex` + 自己给工具打 `defer_loading`，并在客户端已带 `defer_loading` 时把该标志剥掉 | `src/lib/anthropic/message-tools.ts:89-90,177-211`；实测收益 `exp/tool-search-cost-benefit/FINDINGS.md`（16,157 tok/轮，62.7%） |
| `CLIProxyAPIPlus` | 请求侧显式删除相关字段（未做映射） | `internal/translator/*/claude/*_request.go`（spec.md:15 已记述） |
| `ghc-api-py` | 有相关字符串但只在 compat profile 层 | `ghc_api/compat_profiles.py`、`ghc_api/anthropic_responses.py` |

**没有任何参考实现做过「识别客户端搜索工具并翻译到 Responses 客户端执行 tool_search」这件事。** 我们要做的是新路。

**分量：可据以行动**（覆盖了 CLAUDE.md 列出的全部参考项目，逐个 grep `tool_reference|defer_loading|tool_search`）。

### 1.6 明确回答：**没有协议级判据。**

下面是全部启发式候选，含各自的误判风险。**没有一条单独可靠。**

| # | 判据 | 可观测时机 | 假阳性（误伤普通工具） | 假阴性（漏掉真搜索工具） |
|---|---|---|---|---|
| H1 | 工具名 `∈ {"ToolSearch", "tool_search"}` | 首轮，声明侧 | **真实存在**。一个自己就叫 `ToolSearch` 的普通工具会被当成搜索工具，从而被抽出 tools 数组、变成 Responses 的 `{"type":"tool_search"}` builtin——模型再也无法用它原本的语义调用它，而且这个失败是静默的（模型只会拿到一个搜索工具）。MCP 工具名会带 `mcp__` 前缀，所以撞名的只可能是内建或本地工具，概率低但后果重 | 任何第三方客户端用别的名字。已知至少两个不同名字，说明名字空间开放 |
| H2 | 本请求 `tools[]` 中存在 `defer_loading: true` | 首轮，声明侧 | 低——这个字段只在搜索机制下有意义 | 只能判断「有搜索在运作」，**不能指出是哪个工具**；托管路径也满足它。且 Claude Code 会额外塞一个 `DeferredToolPlaceholder`（见 1.3），使得「有 deferred 工具」在没有任何真实 deferred 工具时也成立 |
| H3 | 存在名为 `DeferredToolPlaceholder` 且描述逐字匹配的工具 | 首轮，声明侧 | 极低（这个名字+描述组合是 Claude Code 私有的） | 只对 Claude Code 有效，且它受 feature gate `tengu_deferred_stub_tool` 控制（`:428147`），可被远程关掉。**不能作为主判据** |
| H4 | 历史消息里某个 `tool_result.content[]` 含 `tool_reference` 块 → 反查其 `tool_use_id` 对应的 `tool_use.name` | **第二轮起**，行为侧 | 几乎为零：这是文档规定的自定义搜索工具的**定义性行为** | **首轮完全不可观测**。而首轮恰恰是必须决定 tools 数组怎么发的那一轮 |
| H5 | `input_schema` 形状匹配（单个 `query: string` + 可选整数上限） | 首轮，声明侧 | **高**。`{query: string}` 是最常见的工具 schema 之一（任何搜索/查询工具都长这样）。Claude Code 是 `{query, max_results}`，VS Code 侧未核 | 任一客户端换个参数名（`pattern`、`q`、`terms`）就漏 |
| H6 | 描述文本匹配（如含 `deferred tool`） | 首轮，声明侧 | 低 | 脆——描述是自由文本，Claude Code 自己就有两个变体（`Fgi()` 按 `nep()` 分支拼不同中段，见 `:152382`） |

**我的主观倾向（供主会话裁决，不是结论）：**

若要做，最不容易造成静默错误的组合是 **H2 作为闸门 + H1 作为定位 + H4 作为下一轮的自我校正**：只有当请求里真的有 `defer_loading: true` 的工具时才启动识别（H2 把绝大多数普通请求排除在外），此时再用名字定位（H1），并且在第二轮看到 `tool_reference` 时用 H4 校正或确认。这样 H1 的假阳性被 H2 大幅收窄——一个恰好叫 `ToolSearch` 的普通工具，只有在同一请求里还存在 deferred 工具时才会被误伤，而那个组合几乎只可能是真的搜索场景。

但这仍然是启发式。**它需要用户明确接受「按名字猜」这件事本身**，因为一旦猜错，后果是静默的功能替换而不是报错。这不是我能替用户决定的。

---

## 问题 2：Responses 侧客户端执行 tool search 的完整往返形状

来源全部为本仓 `.venv` 里 openai SDK 3.3.1 的生成类型（OpenAPI spec 生成，是这条 wire 的权威）。**分量：可据以行动**（类型定义是权威；但「上游实际接受」只对任务背景里已实测的三格成立，`tool_search_output` 回传我没有实测）。

### 2.1 工具声明

`openai/types/responses/tool_search_tool_param.py:11-24`：

```python
class ToolSearchToolParam(TypedDict, total=False):
    """Hosted or BYOT tool search configuration for deferred tools."""
    type: Required[Literal["tool_search"]]
    description: Optional[str]      # "Description shown to the model for a client-executed tool search tool."
    execution: Literal["server", "client"]
    parameters: Optional[object]    # "Parameter schema for a client-executed tool search tool."
```

docstring 里的 **BYOT**（bring your own tools）是上游自己对这条路的称呼。

### 2.2 模型产出：`tool_search_call`

`openai/types/responses/response_tool_search_call.py:11-31`：

| 字段 | 类型 | 说明（SDK 原文） |
|---|---|---|
| `id` | `str`（必填） | The unique ID of the tool search call item. |
| `arguments` | `object`（必填） | Arguments used for the tool search call. |
| `call_id` | `str \| None` | The unique ID of the tool search call generated by the model. |
| `execution` | `Literal["server","client"]`（必填） | Whether tool search was executed by the server or by the client. |
| `status` | `Literal["in_progress","completed","incomplete"]`（必填） | |
| `type` | `Literal["tool_search_call"]`（必填） | |
| `created_by` | `str \| None` | The identifier of the actor that created the item. |

注意 `arguments` 是 **object**，不是 JSON 字符串（与 `function_call.arguments` 相反）。

### 2.3 客户端回传：`tool_search_output`，**不是** `tool_search_call_output`

**`tool_search_call_output` 这个类型不存在。** 在整个 openai 包内 grep `tool_search_call_output` 返回 exit 1（无匹配），同一命令对邻近的 `tool_search_output` 在两个文件里各有命中——这是带控制的否定结论。

客户端回传用的 input item 是 `openai/types/responses/response_tool_search_output_item_param_param.py:13-30`：

```python
class ResponseToolSearchOutputItemParamParam(TypedDict, total=False):
    tools: Required[Iterable[ToolParam]]   # "The loaded tool definitions returned by the tool search output."
    type: Required[Literal["tool_search_output"]]
    id: Optional[str]
    call_id: Optional[str]
    execution: Literal["server", "client"]
    status: Optional[Literal["in_progress", "completed", "incomplete"]]
```

它在 input 联合里：`response_input_item_param.py:725` 把 `ResponseToolSearchOutputItemParamParam` 列进 `ResponseInputItemParam`。同一文件 `:199-216` 还有一个 `ToolSearchCall` TypedDict（把模型产出的调用回放进 input 用的）。

**这是本次调查最关键的形状发现**：Anthropic 侧客户端回传的是**工具名**（`tool_reference.tool_name`），Responses 侧客户端回传的是**完整工具定义数组**（`tools: Iterable[ToolParam]`）。翻译时必须由代理用 Anthropic `tools[]` 里的定义把名字展开成定义——这一步是可做的，因为文档规定「Every tool referenced must have a corresponding tool definition in the top-level `tools` parameter」，所以代理手上一定有。

### 2.4 server 执行时上游自产的 `tool_search_output`

`openai/types/responses/response_tool_search_output_item.py:12-32`，与 2.3 同构，差别只在必填性：`id`、`status`、`execution`、`tools`、`type` 都必填，`call_id` / `created_by` 可选。`tools: List[Tool]` 同样是**完整定义**。

它在 output 联合里：`response_output_item.py:290-291` 同时列了 `ResponseToolSearchCall` 与 `ResponseToolSearchOutputItem`。

### 2.5 一个顺带发现：`additional_tools` input item

`response_input_item_param.py:219-230`：`{ role: "developer", tools: Iterable[ToolParam], type: "additional_tools", id? }`，注释为 `A list of additional tools made available at this item.`

这是 Responses 侧**另一条**中途注入工具定义的路。它可能是比 `tool_search_output` 更简单的落点（不需要配对 `call_id`），但我没有任何实测证据说上游接受它，也不知道它与 `tool_search` builtin 的关系。**分量：仅存档，不得据以设计。** 记在这里是为了不让它被静默丢掉。

---

## 问题 3：Anthropic 侧同一往返的形状

### 3.1 模型调用客户端搜索工具时产出普通 `tool_use`

**是的。** 三处独立证据：

- 文档：`When Claude calls your custom search tool, return a standard tool_result with tool_reference blocks in the content array`——`standard tool_result` 说明配对的就是标准 `tool_use`。文档同时把托管路径的 `server_tool_use` / `srvtoolu_...` 单独拎出来警告「Never return a tool_result for its srvtoolu_... ID」，这个对比本身说明自定义路径不走 `server_tool_use`。
- Claude Code：`ToolSearch` 就在普通 tools 数组里（`app.pretty.js:427751` 的构造只产出 `{name, description, input_schema, ...}`），走的是普通工具调用与执行路径。
- VS Code Copilot Chat：`messagesApi.ts:306` 用 `toolCallIdToName.get(message.toolCallId)` 反查——`toolCallId` 是普通 `tool_use.id`。

**分量：可据以行动。**

### 3.2 `tool_reference` 块的语义与多值

块本身（`anthropic/types/tool_reference_block_param.py:13-21`）：`{ type: "tool_reference", tool_name: str, cache_control? }`。

**语义**：不是「搜索命中了这些」的信息性描述，而是**指令性的**——文档说 `the API expands the returned tool_reference blocks the same way`（同托管路径），而托管路径那段写的是 `The API automatically expands these references into full tool definitions`。也就是说，回传一个 `tool_reference` 等于**要求 API 把该工具的完整定义装进模型上下文**。这与 Responses 侧 `tool_search_output.tools` 携带完整定义是同一件事的两种表达。

**一次可以回传多个**：可以。

- 类型上 `tool_result.content` 是 `Iterable[Content]`，`ToolReferenceBlockParam` 是其成员（`tool_result_block_param.py:18-36`）。
- 文档托管侧写 `up to 5 by default; Claude can set a limit`，上限 1–10,000。
- Claude Code 实证：`app.pretty.js:333848` 是 `e.matches.map(...)`——一个数组，`max_results` 默认 5。
- VS Code 实证：`messagesApi.ts:374-376` 同样是 `parsed.filter(...).map(...)`。

**注意一个失配面**：Claude Code 的 `select:A,B,C` query 形式语义是「按名字精确加载这几个」，不是搜索。翻译到 Responses 客户端执行侧时，代理执行的「搜索」实际上多数时候是一次按名查表；这对我们是好事（不需要实现 BM25/regex 搜索），但**不能把 `arguments` 原样透传给上游当成语义等价**——Responses 侧 `tool_search` 的 `parameters` 是我们自己声明的 schema，query 语义由我们定义。

**分量：可据以行动**（类型 + 文档 + 两个客户端实现四处一致）。

### 3.3 空结果

文档：`A search that matches nothing returns a tool_search_tool_search_result with an empty tool_references array, not an error.` 这是托管侧的话；自定义侧对应的就是 `content: []` 或一个空数组。Responses 侧对应 `tool_search_output.tools: []`（`tools` 是 Required 但可为空列表）。**分量：托管侧可据以行动；自定义侧是我的类比推断，仅为倾向。**

---

## 问题 4：本项目响应侧（Responses → Anthropic）现状

### 4.1 代码位置与结构

| 层 | 文件 | 入口 |
|---|---|---|
| 缓冲（非流式）翻译 | `src/app/pipeline/translation_driver/responses.py:135-181` | `from_openai_responses_response()` |
| item → blocks 的**共享**读取器 | `src/app/pipeline/translation_driver/openai_responses.py:374-423` | `blocks_from_item()`（请求侧 `input` 与响应侧 `output` 共用） |
| 流式装配 | `src/app/pipeline/delivery/formats/openai_responses.py:390-600` | `ResponsesAssembler._open()` / `_close()` |
| 成帧 | `src/app/pipeline/delivery/formats/anthropic_messages.py:90-130` | `block_frames()` |

`blocks_from_item()` 今天认识四种 item：`message`、`function_call`、`function_call_output`、`reasoning`，外加一个特例 `web_search_call`（`:418-422`，压成文本）。**其余一律落到 `:423` 的兜底：`return "user", (ContentBlock(BlockKind.UNKNOWN, raw=item),)`。**

`ResponsesAssembler._open()`（`delivery/formats/openai_responses.py:494-505`）的映射表只有 `message`/`function_call`/`reasoning` 三项，`.get(item_type, item_type)` 让未知类型**以自己的类型名做 kind** 建了草稿；`_close()`（`:517-564`）的 `else` 分支（`:556-557`）把它渲染成 `payload = {"type": "text", "text": draft.text}`。

### 4.2 实测：两条路径处置不一致

探针（只读，写在 `/tmp/`，未进仓库）喂进一个 `tool_search_call` item：

```
STREAMING emitted blocks:
  kind='tool_search_call' payload={'type': 'text', 'text': ''}
  count = 1
BUFFERED blocks: []
BUFFERED losses: Conversion(losses=[Loss(code=LossCode.ITEM_NOT_CARRIED, detail="output item 'tool_search_call'")])
```

即：

- **缓冲路径**：丢弃 + 记 `ITEM_NOT_CARRIED`（`responses.py:169-173`）。行为正确、可观测。
- **流式路径**：**发出一个空 text 块**，不记任何 loss。

成帧一侧的实测（带控制）：

```
event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

--- control: a real text block ---
（同样的 start，但中间多一条 content_block_delta 带 "hi"）
```

控制组证明探针有分辨力：真 text 块会多出 delta，未知 kind 的块没有。**客户端收到的是一个内容为空的 text 块。**

**为什么这值得记下来**：`responses.py:88` 的注释已经写明，上游拒绝携带空 text 块的 assistant 轮（400 `messages: text content blocks must be non-empty`），而这正是本代理刻意避免产生空 text 块的原因。流式路径这条兜底违反了同一个约束——客户端存下这一轮再回放，就可能拿到 400。

**分量：可据以行动**（两个探针都跑通，第二个带控制；均为静态复现，不依赖上游）。**限定条件**：这条要真的发生，前提是上游真的发来一个未知类型的 output item。今天不会——因为请求侧根本没送出能触发 `tool_search_call` 的东西（`defer_loading` 被剥掉，`{"type":"tool_search"}` 不注入）。所以这是**一个在做 tool search 翻译的那一刻会立刻变成活缺陷的潜伏面**，不是今天的线上故障。

### 4.3 请求侧现状（为翻译工作定位，非本题）

- `openai_responses.py:143-152,176-196` —— function tool 白名单，`defer_loading` 被显式排除并在 `true` 时记 `SERVER_TOOL_CONSTRAINT_DROPPED`、`false` 时静默移除。
- `openai_responses.py:166-168` —— 带 `type` 且无 `input_schema` 的工具**原样透传**。托管的 `{"type":"tool_search_tool_regex_20251119"}` 走这条，会被上游拒。`subscribers/server_tools.py:40` 的拦截前缀只有 `("web_search", "web_fetch")`。这两点 spec.md:151 已记录。
- `openai_responses.py:578-604` —— `_flattened_output()`：`tool_result.content[]` 里非 text 的 part 全部丢弃并记 `TOOL_RESULT_CONTENT_FLATTENED`。**`tool_reference` 块今天就是在这里被吃掉的**，`output` 变成 `""`。spec.md:150 已记录（且已实测）。

---

## 我排除了什么（硬性清单）

**判据类——考虑过并否决：**

1. **「按 `type` 字段识别客户端搜索工具」** —— 否决。自定义搜索工具在 Anthropic 侧就是普通 function tool，按定义**没有** `type`；有 `type` 的那些是托管工具，属于另一条路。
2. **「Anthropic 的 `anthropic-beta: tool-search-tool-2025-10-19` header 可作闸门」** —— 否决。`src/app/pipeline/request_headers.py:29` 已实测记录：`defer_loading`、`tool_search_tool_regex_20251119` server tool、以及第二轮的 `tool_reference` 块，**在完全不带该 beta 时都返回 200**。所以这个 header 既非必要也非充分，做闸门会同时漏和误。
3. **「用 `input_schema` 形状精确匹配」（H5）** —— 列为候选但不推荐单用，理由见 1.6 表格：`{query: string}` 是最泛的工具 schema 之一。
4. **「等第二轮看到 `tool_reference` 再决定」（H4）单用** —— 否决作为唯一判据。首轮就必须决定 tools 数组怎么发，而 H4 首轮不可观测。它只能做校正，不能做主判据。
5. **「按 `DeferredToolPlaceholder` 识别」（H3）单用** —— 否决作为主判据。它受 Claude Code 的远程 feature gate `tengu_deferred_stub_tool` 控制（`app.pretty.js:428147`），可被上游关掉，且只覆盖一个客户端。
6. **「照抄 caozhiyuan 的 `Tool X loaded` 文本降级」** —— 否决。那不是翻译，是把指令性的 `tool_reference`（= 请把这些工具的定义装进上下文）改写成一句模型读不出效果的散文。模型会以为搜到了，却拿不到 schema。
7. **「照抄 copilot-api-js 的做法」** —— 不适用（不是否决它的正确性）。它做的是**代理主动注入** tool search 以省 token，方向与本任务相反（本任务是把**客户端已有的**搜索翻译过去），且它面对的是 Anthropic Messages 上游而非 Responses。它的 `defer_loading` 剥离逻辑（`message-tools.ts:209-211`）与我们今天的做法同源，可作参考。

**来源类——查了发现无关：**

8. `anthropic` SDK 的 `examples/` —— 包内不存在该目录。
9. `app.pretty.js:150686-150705`（`hMp`）—— 一开始以为是通用的 tool_search 能力降级路径，读完确认是 **Microsoft Foundry 专属**（`if (lo() !== "foundry") return e;`）。它揭示的唯一可复用事实是：能力不足时 Claude Code 的做法是剥 `defer_loading` **并且**整个丢掉 `DeferredToolPlaceholder` 工具——与我们今天的剥离方向一致。不能当成对本代理生效的路径。
10. `app.pretty.js:482834`（`AdA` / `drg` 集合含 `tool_search_tool_regex`）—— 查了，是**入站**块识别用的 Anthropic 托管 server tool 名字集合，不是构造请求的路径。它不改变「Claude Code 不发托管 tool search」这个结论。
11. `agent-maestro`、`hooyao-copilot-bridge`、`ghc-api-py` —— grep 命中的都是无关上下文（web search patch、Codex 协议研究文档、compat profile 字符串），没有 tool search 识别或翻译逻辑。
12. `~/.claude/refs/*/strings-n6.txt` —— 未使用。`app.pretty.js` 有行号且是结构化源码，按项目记忆 `unbun-extracts-claude-code-source` 的做法直接读源码，不啃 strings。

**方法类——过程中的一次自纠：**

13. 我第一次用 `rg -rn 'tool_search|...' src/` 查本仓，`-r` 是 `--replace` 而非 recursive，导致每个匹配都被替换成字面量 `n` 打印出来，exit 0 无告警。这正是 `20-tool-use-preference.md` 记载的那个静默误用。已用 `rg -n --no-ignore` 重跑，本报告引用的全部是重跑结果。记在这里是因为**那一版被污染的输出如果被当成事实读，会得出「本仓根本没有 tool_search 相关代码」的相反结论**。

---

## 交回主会话

1. **Spec 修订义务（阻断性，不归我做）。** `spec.md:14-16,146-148,175` 与 `openai_responses.py:149-151` 都把「用户 2026-08-24 裁定 tool search 不是本代理提供的能力」记为现行裁决，并据此关闭了「映射到 Responses hosted `{"type":"tool_search"}`」这条路。本次任务的前提是用户裁定要**翻译**——这是同一位用户对同一件事的新裁决，直接推翻旧裁决。按项目规则，实现不得先于 Spec 改变可观察行为，且 Spec 级事实不得停在报告里。**请在动实现之前先改 `spec.md`（含修订记录），并同步 `openai_responses.py:149-151` 那段注释与 `.dev/docs/anthropic-responses-bridge/review-disposition-tool-whitelist.md` 里相关的处置结论。** 我没有做任何修改。
2. **需要用户裁决的一个分叉**：识别只能靠启发式（问题 1.6）。「按工具名猜」猜错的后果是静默的功能替换而非报错。请用户在「按名字识别（我的倾向：H2 闸门 + H1 定位 + H4 校正）」与「只在观测到 `tool_reference` 之后才启用（即第一轮必然降级）」之间裁决。
3. **建议补一次实测**（我没做，超出只读范围里可安全做的部分）：设 `ENABLE_TOOL_SEARCH=true` 让 Claude Code 指向本代理，抓一份真实请求。1.3 的门控条件是读源码得出的，实际 tools 数组长什么样（尤其 `DeferredToolPlaceholder` 在不在、有多少工具带 `defer_loading`）值得一手确认。
4. **建议顺手修的既有缺陷**（与 tool search 无关也成立）：`delivery/formats/openai_responses.py:556-557` 让任意未知 output item 变成空 text 块。两条交付路径对同一件事给出不同答案，且流式那条产出的是上游会拒绝回放的形状。这在做 tool search 翻译时会立刻从潜伏变成活缺陷。
