# vscode-copilot-chat 如何回避 `The use of the web search tool is not supported`

调查对象：`/home/xp/src/ghc-api-proxy-py/refs/vscode-copilot-chat`
锚定 HEAD：`5863f5a70`（Add archive notice #5120）。仓库已归档，工作树干净，本次调查只读。
调查日期：2026-08-20。

以下所有 `file:line` 均相对该仓库根目录。

## 0. 一句话结论

第一方扩展**从来不向 Copilot 后端发送任何 hosted web search 工具**。它不是靠 model capability 协商避开的，也不是靠 400 之后降级重试避开的，而是**硬编码地在出站前把 `type` 以 `web_search` 开头的工具从 `tools` 数组里剔除**，并在源码注释里直接写明「CAPI 尚不支持」。证据权重：**强，可据以动手**。

## 1. 扩展是否向 Copilot 发送 hosted web search？——不发，且有显式剔除代码

### 1.1 唯一的显式剔除点（Responses 直通代理）

`src/extension/externalAgents/node/oaiLanguageModelServer.ts:133-142`：

```ts
const requestBody: OpenAI.Responses.ResponseCreateParams = JSON.parse(bodyString);
if (Array.isArray(requestBody.tools)) {
    requestBody.tools = requestBody.tools.filter(tool => {
        if (typeof tool?.type === 'string' && tool.type.startsWith('web_search')) {
            this.warn(`Filtering out unsupported tool type: ${JSON.stringify(tool)}`);
            return false;
        }
        return true;
    });
}
```

这段代码的语境（`oaiLanguageModelServer.ts:37-80`）：扩展在 `127.0.0.1` 上起一个 HTTP 服务，暴露 `/v1/responses`、`/responses`、`//responses`，作为 **OpenAI Responses API 兼容端点**，给外部 agent（Codex CLI，`user-agent` 前缀 `vscode_codex`，见 `:190`）当 `OPENAI_BASE_URL` 用；它把请求**原样透传**到 Copilot 的 chat endpoint。Codex CLI 默认会声明 `web_search` 工具，于是扩展在透传前把它摘掉。

引入该过滤的提交：`52032e48d`，Rob Lourens，2025-11-01，标题 **"Filter out unsupported codex tool type (#1748)"**。提交没有正文，只有标题；标题本身就是这条约定的直接陈述。

**判别要点**：过滤只作用于 `requestBody.tools`。同一提交对 `responsesApi.ts` 的 +50 行改动（`52032e48d` diff）全部落在 `responseApiInputToRawMessagesForLogging` 及其辅助函数上，那是**仅供日志使用**的反解析路径（函数名即如此，调用点在 `oaiLanguageModelServer.ts:196-198`，结果只喂给 `messagesForLogging`），**不参与出站请求体构造，也不构成对 `input` 的过滤**。

### 1.2 Claude Code 会话路径：注释直接点名 CAPI 不支持

`src/extension/chatSessions/claude/node/claudeCodeAgent.ts:432-434`：

```ts
// TODO: CAPI does not yet support the WebSearch tool
// Once it does, we can re-enable it.
disallowedTools: ['WebSearch'],
```

这是把 Claude Agent SDK 跑在 Copilot（CAPI）token 之上时，**在 SDK 层面禁用** WebSearch。第一方对「Copilot 后端不支持 web search」的直白确认，且措辞是 `not yet` —— 属于后端能力缺失，而非客户端策略选择。

### 1.3 扩展的 web 搜索能力实际怎么实现——走另一个服务

不是工具，而是 **GitHub 平台远程 agent 的服务端 skill**：

- `src/extension/conversation/vscode-node/remoteAgents.ts:52-54`：`GITHUB_PLATFORM_AGENT_SKILLS = { web: 'bing-search' }`
- `src/extension/conversation/vscode-node/remoteAgents.ts:730`：`{ name: 'web', insertText: '#web', description: 'Search Bing for real-time context', kind: 'bing-search' }`
- `src/extension/conversation/vscode-node/remoteAgents.ts:413-416`：流式响应里遇到 `case 'bing-search'` 时渲染「Searching Bing for …」

即 `#web` 是发给 GitHub platform agent（`github`/`platform`）的**引用/skill**，由那个服务端 agent 自己去搜，**根本不进入 Copilot chat 请求的 `tools` 数组**。

### 1.4 唯一构造 hosted web_search 的地方是 BYOK，不经 Copilot

`src/extension/byok/vscode-node/anthropicProvider.ts:199-224` 会构造 `{ name: 'web_search', type: 'web_search_20250305', max_uses, allowed_domains/blocked_domains, user_location }`，受设置 `chat.anthropic.tools.websearch.enabled`（`src/platform/configuration/common/configurationService.ts:904`，默认 `false`）控制。

但这条路是 **BYOK 直连 Anthropic**：`anthropicProvider.ts:73` 与 `:116` 都是 `new Anthropic({ apiKey })`，用用户自带的 key 和 SDK 默认 baseURL（`api.anthropic.com`），`:127` 明确把 `anthropicClient.baseURL` 当 endpoint。**与 Copilot 上游无关**。

### 1.5 证伪检索

在排除 `node_modules` 与 `.jsonl` fixture 后，全仓 `web_search_call`、`web_search_preview`、`WebSearchTool` 的命中**只有** BYOK Anthropic provider 与 Copilot CLI 的工具名字表（`src/extension/chatSessions/copilotcli/common/copilotCLITools.ts:179`，那是解析 Copilot CLI 自己的事件流，不是构造请求）。`chat-lib/` 下零命中。全仓 `unsupported_value`、`web search tool is not supported` **零命中** —— 扩展代码里没有对这个具体错误码的任何处理。

## 2. tools 数组如何组装与过滤

### 2.1 Responses 路径（`ModelSupportedEndpoint.Responses`）

`src/platform/endpoint/node/responsesApi.ts:42-47`，`createResponsesRequestBody`：

```ts
tools: options.requestOptions?.tools?.map((tool): OpenAI.Responses.FunctionTool & OpenAiResponsesFunctionTool => ({
    ...tool.function,
    type: 'function',
    strict: false,
    parameters: (tool.function.parameters || {}) as Record<string, unknown>,
})),
```

**这是构造性的白名单**：入参只有 VS Code 侧注册的 function tool，输出**无条件写死 `type: 'function'`**。这条路径在类型和实现两个层面都**不可能**产出 hosted tool。没有黑名单，因为不需要黑名单。

### 2.2 Messages 路径（`/v1/messages`，Anthropic 系模型经 CAPI）

`src/platform/endpoint/node/messagesApi.ts:114-142`：`finalTools` 由 `options.requestOptions.tools` 逐个映射为 `{ name, description, input_schema, defer_loading? }`，**不带 `type` 字段**；唯一会被额外压入的非 function 工具是 Anthropic 的 tool search（`messagesApi.ts:134-136`，`TOOL_SEARCH_TOOL_NAME` / `TOOL_SEARCH_TOOL_TYPE`）。同样没有 web search。

### 2.3 model capability 里**没有** web search 能力位

`/models` 端点返回的能力结构定义在 `src/platform/endpoint/common/endpointProvider.ts:34-57`：

```ts
supports: {
    parallel_tool_calls?: boolean;
    tool_calls?: boolean;
    streaming: boolean | undefined;
    vision?: boolean;
    prediction?: boolean;
    thinking?: boolean;
    adaptive_thinking?: boolean;
    max_thinking_budget?: number;
    min_thinking_budget?: number;
    reasoning_effort?: string[];
}
```

外加 `supported_endpoints?: ModelSupportedEndpoint[]`（`endpointProvider.ts:93`，枚举见 `:72-77`：`/chat/completions`、`/responses`、`ws:/responses`、`/v1/messages`）。

**结论：整个 capability 契约里不存在任何与 web search 相关的位。** 扩展**无法**按 model 能力决定发不发 web search —— 它只能、也确实是无条件不发。`supports.tool_calls` 的唯一消费点是 `src/platform/endpoint/node/chatEndpoint.ts:166`（`this.supportsToolCalls = ...`），与工具类型裁剪无关。

证据权重：**强**。这是「按 capability 白名单裁剪工具」这一假设的直接证伪 —— 该机制在第一方客户端里根本不存在。

## 3. 上游 400 如何处理——没有针对 `unsupported_value` 的任何路径

集中处理点：`src/extension/prompt/node/chatMLFetcher.ts:1470-1530`。它先尝试 `JSON.parse(text)` 并取 `jsonData.error ?? jsonData`（`:1471-1473`），然后在 `400 <= status < 500` 区间内逐条匹配：

| 条件 | 位置 | 结果 |
|---|---|---|
| `status === 400 && text.includes('off_topic')` | `chatMLFetcher.ts:1483` | `ChatFailKind.OffTopic` |
| `status === 400 && jsonData?.code === 'previous_response_not_found'` | `chatMLFetcher.ts:1502` | `ChatFailKind.InvalidPreviousResponseId` |
| `status === 401/403` | `chatMLFetcher.ts:1512` | 重置 token |
| `status === 402` | `chatMLFetcher.ts:1524` | 配额 |

**没有 `unsupported_value` 分支，没有「剥掉工具后重发」的降级重试。** 也就是说，第一方客户端把这个 400 当作**不可恢复的编程错误**来对待 —— 它的策略是在**出站前**保证不会触发，而不是在**收到后**补救。

唯一与请求体形状有关的 400 预防性代码是 `messagesApi.ts:199-224` 的 trailing-assistant guard（尾部 assistant 消息会被 Anthropic 当作 prefill 而 400，于是补一条合成 user 消息），性质上同样是**出站前预防**。

## 4. Responses 请求体的固定形状

`src/platform/endpoint/node/responsesApi.ts:37-95`，`createResponsesRequestBody` 产出的字段：

| 字段 | 取值 | 位置 |
|---|---|---|
| `tools` | 全部 `type: 'function'`、`strict: false` | `:42-47` |
| `tool_choice` | 对象形态归一为 `{ type: 'function', name }`，否则原样透传 | `:51-53` |
| `store` | **硬编码 `false`** | `:55` |
| `include` | **无条件 `['reasoning.encrypted_content']`** | `:88` |
| `reasoning` | 仅当 `endpoint.supportsReasoningEffort?.length` 非空时带 `effort`；`summary` 受实验配置控制，`gpt-5.3-codex-spark-preview` 强制关闭 | `:74-86` |
| `stream` | `true` | `:39` |
| `max_output_tokens` | 由 `postOptions.max_tokens` 改名而来 | `:50` |
| `truncation` | `'auto'` 或 `'disabled'`，按配置 | `:70-72` |
| `text` | `verbosity ? { verbosity } : undefined` | `:56` |
| `context_management` | 仅实验开关开启且模型不在 `modelsWithoutResponsesContextManagement` 时 | `:59-69` |
| `prompt_cache_key` | 仅实验开关开启且有 `conversationId` | `:89-92` |

注释 `:48-49` 说得很明白：*"Only a subset of completion post options are supported, and some are renamed. Handle them manually."* —— **这是显式的白名单式构造，不是透传。**

## 5. 关键判别问题：400 是冲着 `tools` 声明报的，还是冲着历史 `input` 里的残留 item 报的？

### 5.1 直接证据指向 `tools` 声明

- 修复动作本身只改 `tools`：`oaiLanguageModelServer.ts:133-142` 过滤 `requestBody.tools`，**对 `requestBody.input` 一个字节都不动**。
- 提交标题 `52032e48d` 是 "Filter out unsupported codex **tool type**"，日志文案是 `Filtering out unsupported **tool type**`。
- 若 400 是由 `input` 里的 `web_search_call` item 触发，仅过滤 `tools` 的修复**不足以**让 Codex 直通跑通（Codex 会话第二轮就会带上历史）。该修复自 2025-11-01 起一直保留到归档 HEAD，未被追加 input 过滤补丁 —— 这是**行为层面的间接印证**。

### 5.2 该扩展的代码无法进一步区分（重要限定）

原生路径上这个问题**根本无从触发**：`rawMessagesToResponseAPI`（`responsesApi.ts:107-176`）是构造性白名单，能产出的 `input` item 类型只有 `message`（assistant/user/system）、`function_call`（`:141`）、`function_call_output`（`:160`）、附带 `input_image` 的 user 消息（`:163`）、`reasoning`（`:216-224`）以及 compaction item（`:240+`）。**没有任何代码路径能生成 `web_search_call` 进入 `input`**。既然 `tools` 里从第一轮起就没有 web_search，模型也就永远不会产出 web search item，历史里自然不会有残留。

因此：**扩展源码不能证明「input 里的残留 item 不会触发 400」——它只是从不制造这种输入。** 这是「没有证据」，不是「有反证」。

### 5.3 唯一的类比性旁证

`src/platform/endpoint/node/messagesApi.ts:186-192`：

```ts
// TODO: Ideally the custom tool_search tool should filter results itself, but it doesn't
// have access to the enabled tools for the request. For now, filter tool_reference blocks
// here against the actual tools sent to Anthropic to avoid 400 errors from unknown tool names.
const validToolNames = finalTools.length > 0 ? new Set(finalTools.map(t => t.name)) : undefined;
```

这说明在 **Messages** family 上，第一方确实观测到「历史消息里引用了不在本次 `tools` 数组中的工具名 → 400」，并因此加了**按已声明工具名过滤历史 block** 的逻辑。它是**另一个 API family、另一种错误（unknown tool name）**，不能直接搬到 Responses 的 `unsupported_value` 上；但它表明「上游会拿历史 item 和本次 tools 声明做交叉校验」这一模式在 Copilot 后端是**真实存在过的**。

**判别结论**：
- 「400 由请求 `tools` 声明触发」——**倾向性强，接近可据以动手**（修复动作、提交标题、日志文案三者一致指向 `tools`；且仅改 `tools` 的修复长期有效）。
- 「历史 `input` 残留 item 是否**也**会触发」——**证据不足，扩展代码无法回答**。建议在自己的项目里用一次真实请求做二分实验：同一 `input`（含 web_search 相关 item）分别配 带/不带 web_search 的 `tools`，观察 400 是否消失。

## 6. 对 `ghc-api-proxy-py` 的可操作建议

按第一方约定，最省事且与第一方对齐的做法是**出站前白名单**，而不是收到 400 再降级：

1. 构造发往 Copilot 的 Responses `tools` 时，**只允许 `type: 'function'`**，其余一律剔除并 warn（对齐 `responsesApi.ts:42-47` + `oaiLanguageModelServer.ts:133-142`）。Anthropic Messages 入站侧的 `server_tool_use` 类工具（`web_search_20250305` 等）必须在转换层被丢弃。
2. **不要指望 model capability 协商**：`/models` 的 `capabilities.supports` 里没有 web search 位（`endpointProvider.ts:45-56`），无从查询，只能无条件不发。
3. **不要为 `unsupported_value` 写重试/降级**：第一方没有这条路径（`chatMLFetcher.ts:1470-1530` 全部分支已列举）。它只对 `off_topic` 和 `previous_response_not_found` 做了特化。
4. 若确认历史 `input` 侧也会触发，参照 `messagesApi.ts:186-192` 的模式，按「本次实际发送的 tools」反过滤历史 item —— 但**先做实验确认，别照抄**。
5. 顺带一条与本次 400 无关但同源的经验：`store: false`（`:55`）与 `include: ['reasoning.encrypted_content']`（`:88`）在第一方是硬编码的，`tool_choice` 对象形态要归一成 `{ type: 'function', name }`（`:51-53`）。

## 7. 证据权重汇总

| 结论 | 权重 |
|---|---|
| 扩展从不向 Copilot 发 hosted web search，且有显式剔除代码 | **强，可据以动手** |
| Copilot/CAPI 后端确实不支持 web search 工具 | **强**（`claudeCodeAgent.ts:432` 注释 + 剔除提交，两处独立第一方陈述） |
| model capability 契约里无 web search 能力位，无法协商 | **强**（类型定义穷举） |
| 扩展对 `unsupported_value` 无任何处理/降级 | **强**（全仓零命中 + 400 分支已穷举） |
| Responses 请求体是白名单构造而非透传 | **强**（源码注释自陈） |
| 400 由 `tools` 声明触发 | **倾向性强**（三处一致指向，但无上游直接回执） |
| 历史 `input` 残留 item 是否触发 400 | **无证据**，需自行实验 |
| `#web` 走 GitHub platform remote agent 的 bing-search skill | **强** |

## 8. 本次调查的范围限制

- 只读了源码，**没有**发起任何真实上游请求，因此「上游实际如何行为」全部是从第一方客户端的**规避动作**反推的。
- 仓库已归档于 `5863f5a70`，反映的是该时点的后端约定；Copilot 后端此后可能已变化。
- 未检索 `node_modules`（`@vscode/copilot-api` 的类型定义可能含更多字段）。若需确认 `/models` 响应的完整字段，应直接查 `@vscode/copilot-api` 包或实际调用该端点。
