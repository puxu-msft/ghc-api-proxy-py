# vscode-copilot-chat 对 web search / server tool 的处理：独立代码审计

调查对象：`/home/xp/src/ghc-api-proxy-py/refs/vscode-copilot-chat`
锚定 HEAD：`5863f5a70`（Add archive notice #5120），`git describe` = `v0.43.2026040601-15-g5863f5a70`。仓库已归档，工作树干净，本次全程只读，未修改 `refs/` 下任何文件。
调查日期：2026-08-20。

本文所有 `file:line` 相对该仓库根目录。本文是对 `docs/tmp/260820-websearch-400-vscode-ext.md`（下称「前文」）的独立复核 + 补充，**先按题目重新验证，再在末尾列出与前文的分歧**。前文的主干结论我复核后确认；但它有一处推理缺陷和一处重要遗漏，见 §7。

---

## 0. 一句话结论

1. 出站前对 server tool 的处理**只有「剔除」一种，全仓不存在任何「映射成 Copilot 拼法」的代码**——`web_search_preview`、`web_search_call`、`code_interpreter`、`url_citation` 这四个字面量在整个仓库（排除 `.jsonl` 测试 fixture）**零命中**。
2. 扩展自己**没有任何客户端侧 web search 工具**。它有的是 `fetch_webpage`（按 URL 抓页面，不是搜索），以及 `#web` → GitHub platform 远程 agent 的服务端 `bing-search` skill——后者走的是完全另一个端点，从不进入任何 `tools` 数组。
3. `disallowedTools: ['WebSearch']` 的适用范围**远比前文写的窄**：它只作用于 VS Code 内嵌的 Claude Agent SDK 会话。同一扩展提供的 `/terminal` 路径把真的 `claude` CLI 指向同一个本地 Anthropic 兼容服务器，**完全没有加这个禁用**，而那个服务器对 `tools` 数组一个字节都不过滤。第一方在自己的兼容层上留了这个洞。

---

## 1. Q1：出站前对 `tools` 数组里的 server tool 做了什么

### 1.1 唯一的剔除点，且只在 Codex 兼容层

`src/extension/externalAgents/node/oaiLanguageModelServer.ts:133-143`：

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

语境（同文件 `:57-82`、`:183-191`）：扩展在 `127.0.0.1` 随机端口起 HTTP 服务，接受 `POST /v1/responses`、`/responses`、`//responses`（注释 `:67`：*"It sends //responses if OPENAI_BASE_URL ends in /"*），把请求体几乎原样透传到 Copilot chat endpoint，`user-agent` 前缀写死 `'vscode_codex'`（`:190`）。这是**给外部 Codex CLI 用的兼容层，不是扩展自己的路径**。

引入提交（`git log -L 133,143:...` 实测）：

```
52032e48d35b1879398841ed6b73e388dd082833  2025-11-01  Rob Lourens  Filter out unsupported codex tool type (#1748)
```

diff 显示这 10 行是该提交一次性新增的，此后到归档 HEAD 未再改动。

### 1.2 「剔除是唯一处理吗？」——是。三项证伪检索

**（a）全仓 `tools` 数组过滤点穷举**（`rg "tools = .*\.filter\(|tools\?\.filter\(|\.tools\.filter\(" -g '*.ts' -g '*.tsx' src/`），只有三处：

| 位置 | 是什么 |
|---|---|
| `src/extension/externalAgents/node/oaiLanguageModelServer.ts:135` | 上面这条 web_search 剔除 |
| `src/extension/chatSessions/copilotcli/node/copilotCli.ts:327` | `promptFile.header?.tools?.filter(tool => !!tool)`——滤空值，与类型无关 |
| `src/extension/prompts/node/agent/test/agentPrompt.spec.tsx:171` | 测试代码 |

**（b）builtin 工具字面量零命中**（`rg` 全仓，排除 `.jsonl`）：

```
web_search_preview     0 命中
web_search_call        0 命中
code_interpreter       0 命中
url_citation           0 命中
computer_use           0 命中
```

`file_search` 有 3 处命中，但全部是扩展自己的 VS Code 工具名 `ToolName.FindFiles = 'file_search'`（`src/extension/tools/common/toolNames.ts:26`），与 OpenAI 的 hosted `file_search` 无关。

**（c）`chat-lib/` 子包零命中**：`rg -ni "web_search|websearch|url_citation|bing" chat-lib/` 无输出。

**结论：不存在任何「把 `web_search_20250305` / `web_search` 映射成 Copilot 拼法」的代码。** 证据权重：**强，可据以动手**（穷举式检索 + 过滤点穷举，两条独立路线互证）。

### 1.3 扩展自己的原生出站路径：构造性白名单，压根产不出 hosted tool

**Responses 路径**——`src/platform/endpoint/node/responsesApi.ts:42-47`：

```ts
tools: options.requestOptions?.tools?.map((tool): OpenAI.Responses.FunctionTool & OpenAiResponsesFunctionTool => ({
    ...tool.function,
    type: 'function',
    strict: false,
    parameters: (tool.function.parameters || {}) as Record<string, unknown>,
})),
```

`type: 'function'` 写死在 map 的输出里，输入只有 VS Code 注册的 function tool。紧随其后的注释 `:48-49` 自陈：*"Only a subset of completion post options are supported, and some are renamed. Handle them manually."*

**Messages 路径**——`src/platform/endpoint/node/messagesApi.ts:114-141`：逐个映射成 `{ name, description, input_schema, defer_loading? }`，**不带 `type` 字段**；唯一会被压入的非 function 工具是 Anthropic 的 tool search（`:134-136`：`finalTools.push({ name: TOOL_SEARCH_TOOL_NAME, type: TOOL_SEARCH_TOOL_TYPE, defer_loading: false })`）。没有 web search。

所以原生路径不需要黑名单，因为白名单在类型和实现两个层面都堵死了。

---

## 2. Q2：扩展自己怎么提供「网页搜索」

### 2.1 没有客户端侧 web search 工具

`src/extension/tools/common/toolNames.ts:22-75` 是扩展全部工具名的枚举（`ToolName`），逐条读完：**没有任何一条是 web search**。与网络相关的只有一条：

```ts
FetchWebPage = 'fetch_webpage',       // toolNames.ts:46
```

对应的 contributed 名 `ContributedToolName.FetchWebPage = 'copilot_fetchWebPage'`（`:102`）。

### 2.2 `fetch_webpage` 是抓 URL，不是搜索

`src/extension/tools/vscode-node/fetchWebPageTool.tsx:20-23`：

```ts
interface IFetchWebPageParams {
	urls: string[];
	query?: string;
}
```

`:28` 说明它只是包装 VS Code 核心的内部工具：`const internalToolName = 'vscode_fetchWebPage_internal';`，`:66-74` 里 `lm.invokeTool(internalToolName, ...)` 转发，`:113-117` 用 `UrlChunkEmbeddingsIndex.findInUrls` 对抓回来的正文做 embedding chunk 排序——`query` 是**用于在已抓回的页面里排序**的，不是搜索引擎查询词。

系统提示里对它的用法也是「用户给了 URL 才用」——`src/extension/prompts/node/agent/defaultAgentInstructions.tsx:305`：

> `If the user provides a URL, you MUST use the {ToolName.FetchWebPage} tool to retrieve the content from the web page. After fetching, review the content returned by {ToolName.FetchWebPage}. If you find any additional URL's or links that are relevant, use the {ToolName.FetchWebPage} tool again to retrieve those links.`

同文件 `:228` 同义。**没有任何提示词教模型「用 fetch_webpage 去搜索」。**

### 2.3 唯一真正的 web 搜索能力：`#web` → GitHub platform 远程 agent 的服务端 skill

`src/extension/conversation/vscode-node/remoteAgents.ts:50-54`：

```ts
const GITHUB_PLATFORM_AGENT_NAME = 'github';
const GITHUB_PLATFORM_AGENT_ID = 'platform';
const GITHUB_PLATFORM_AGENT_SKILLS: { [key: string]: string } = {
	web: 'bing-search',
};
```

注册为聊天变量（`:730`）：

```ts
{ name: 'web', insertText: `#web`, description: 'Search Bing for real-time context', kind: 'bing-search', command: undefined },
```

注意 `:729` 的 `.filter((skill) => skills.has(skill.kind))`——这个 skill 只有在 GitHub 服务端 `listEnabledSkills`（`:690-702`，`RequestType.ListSkills`）返回里带 `bing-search` 时才出现，**是否可用由服务端决定**。

请求侧（`:705-717`）：

```ts
private async resolveCopilotSkills(agent: string, request: ChatRequest): Promise<{ copilot_skills: string[] }> {
	if (agent === GITHUB_PLATFORM_AGENT_NAME) {
		const skills = new Set<string>();
		for (const variable of request.references) {
			if (GITHUB_PLATFORM_AGENT_SKILLS[variable.name]) {
				skills.add(GITHUB_PLATFORM_AGENT_SKILLS[variable.name]);
			}
		}
		return { copilot_skills: [...skills] };
	}

	return { copilot_skills: [] };
}
```

**它进的是请求体的 `copilot_skills` 字段，不是 `tools` 数组**，而且端点是 `RemoteAgentChatEndpoint`（`:283`，`RequestType.RemoteAgentChat`），不是 `/responses` 也不是 `/v1/messages`。

响应侧只做 UI 提示（`:410-420`）：

```ts
if (delta._deprecatedCopilotFunctionCalls) {
	for (const call of delta._deprecatedCopilotFunctionCalls) {
		switch (call.name) {
			case 'bing-search': {
				try {
					const data: { query: string } = JSON.parse(call.arguments);
					responseStream.progress(l10n.t('Searching Bing for "{0}"...', data.query), async (progress) => reportProgress(progress, l10n.t('Bing search results for "{0}"', data.query)));
				} catch (ex) { }
				break;
			}
```

字段名 `_deprecatedCopilotFunctionCalls`（定义在 `src/platform/networking/common/fetch.ts:152`，产出点 `src/platform/networking/node/stream.ts:457`）说明这是老式 CAPI function-call 通道。`RemoteAgentContribution` 仍在扩展激活时注册（`src/extension/extension/vscode-node/contributions.ts:23,114`），所以路径还活着，但走的是 legacy 协议。

**结论：扩展的「网页搜索」既不是 hosted server tool，也不是客户端工具，而是 GitHub 平台 agent 的服务端 skill。** 结果怎么回填进对话——由那个远程 agent 直接写进它自己的流式回复正文，扩展只把 `bing-search` 的调用渲染成一行进度提示 + 一条 reference。证据权重：**强**。

### 2.4 旁支：Copilot CLI 会话确实有 `web_search`，但那是 CLI 自己的工具

`src/extension/chatSessions/copilotcli/common/copilotCLITools.ts:179-184`：

```ts
type WebSearchTool = {
	toolName: 'web_search';
	arguments: {
		query: string;
	};
};
```

`:1053`：`'web_search': [l10n.t('Web Search'), emptyInvocation, genericToolInvocationCompleted],`

这是**解析 Copilot CLI 进程事件流的类型定义 + UI 标签表**，扩展只负责渲染。CLI 自己怎么执行搜索、走哪个端点，本仓库无从判断。**未找到**任何证据表明它经过扩展的两个本地代理服务器。

---

## 3. Q3：`disallowedTools: ['WebSearch']` 的适用范围与时效

### 3.1 原文

`src/extension/chatSessions/claude/node/claudeCodeAgent.ts:424-444`（完整语境）：

```ts
const options: Options = {
    cwd,
    additionalDirectories,
    // We allow this because we handle the visibility of
    // the permission mode ourselves in the options
    allowDangerouslySkipPermissions: true,
    abortController: this._abortController,
    executable: process.execPath as 'node', // get it to fork the EH node process
    // TODO: CAPI does not yet support the WebSearch tool
    // Once it does, we can re-enable it.
    disallowedTools: ['WebSearch'],
    ...
```

紧接着 `:445-450` 是它把 SDK 指向哪里：

```ts
ANTHROPIC_BASE_URL: `http://localhost:${this.serverConfig.port}`,
ANTHROPIC_AUTH_TOKEN: `${this.serverConfig.nonce}.${this.sessionId}`,
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
```

### 3.2 范围：只覆盖「VS Code 内嵌的 Claude Agent SDK 会话」这一条路径

`disallowedTools` 是 `@anthropic-ai/claude-agent-sdk` 的 `Options` 字段，只对 **这个进程内 SDK 实例** 生效。它：

- **不是**按模型判断的（同一文件 `:440` 才是模型：`model: this._currentModelId`，与 `disallowedTools` 无关）；
- **不是**按端点判断的（本地服务器 `ClaudeLanguageModelServer` 只接 `/v1/messages`，见 `src/extension/chatSessions/claude/node/claudeLanguageModelServer.ts:104-108`）；
- **只是**在 SDK 层面不让 Claude 声明 `WebSearch`，从而 `web_search_20250305` 永远不会出现在发往本地服务器、进而发往 CAPI 的 `tools` 里。

所以它是「一条路径上的客户端策略」，不是「一条全局能力协商」。

### 3.3 关键漏洞：同一扩展的 terminal 路径完全没有这层保护

`src/extension/chatSessions/claude/vscode-node/slashCommands/terminalCommand.ts:89-105`：

```ts
const terminal = this.terminalService.createTerminal({
	name: 'Claude',
	message: formatMessageForTerminal(vscode.l10n.t('This instance of Claude CLI is configured to use your GitHub Copilot subscription.'), { loudFormatting: true }),
	env: {
		ANTHROPIC_BASE_URL: `http://localhost:${config.port}`,
		ANTHROPIC_AUTH_TOKEN: `${config.nonce}.${sessionId}`,
		// Hide account info banner in CLI since it's redundant with the message above
		CLAUDE_CODE_HIDE_ACCOUNT_INFO: '1',
	}
});
...
terminal.sendText(`${cliCommand} --session-id ${sessionId}`);
```

命令行只有 `--session-id`，**没有 `--disallowedTools WebSearch`，也没有任何等价开关**。这是真的 `claude` CLI 进程（`_getClaudeCliCommand()` 找的是 `claude` 或 `agency claude`），指向的是**同一个** `ClaudeLanguageModelServer`。

而那个服务器不过滤工具。`src/extension/chatSessions/claude/node/claudeLanguageModelServer.ts:47-55` 的请求体类型：

```ts
interface AnthropicMessagesRequest {
	model: string;
	messages: MessageParam[];
	system?: string | Array<{ type: 'text'; text: string }>;
	max_tokens?: number;
	stream?: boolean;
	tools?: unknown[];
	[key: string]: unknown;
}
```

`tools?: unknown[]` 被声明了却**从未被读、从未被过滤**——`rg "tools|web_search|WebSearch|filter"` 在这个 751 行的文件里，命中的全部是 `filterSupportedBetas`（`:409-417`，过滤 `anthropic-beta` 头，白名单是 `interleaved-thinking` / `context-management` / `advanced-tool-use`，见 `:36-40`）。请求体唯一被改写的字段是 `model`（`:175`）。最终出站体在 `:728-746`：

```ts
public createRequestBody(options: ICreateEndpointBodyOptions): IEndpointBody {
	const base = this.base.createRequestBody(options);
	// Claude models don't support both temperature and top_p simultaneously.
	if (this.requestBody.temperature !== undefined || this.requestBody.top_p !== undefined) {
		delete base.temperature;
		delete base.top_p;
	}
	// Merge with original request body to preserve any additional properties
	return {
		...base,
		...this.requestBody
	};
}
```

`...this.requestBody` 在后，**客户端原样的 `tools`（含任何 server tool）覆盖 base 并直达 CAPI**。

**结论：第一方对「Claude Code + CAPI 不能用 WebSearch」的防线只有 SDK 那一层，兼容层本身是裸的。** 这条判据对本项目直接相关：我们的代理处在与 `ClaudeLanguageModelServer` **完全同构**的位置上，而第一方在这个位置**没有**给出任何可抄的处理。证据权重：**强**（两处代码 + 一次全文件检索的零命中）。

### 3.4 时效线索

```
git log -S "CAPI does not yet support the WebSearch" --all
→ 130008b5e538398cc3d961b6c2b4076ed6ba93c1  2026-01-17  Tyler James Leonhardt
  feat: add documentation for Claude Agent SDK and integration details (#2954)
```

- 写入日期：**2026-01-17**，且仅此一次（此后 `-L 430,436` 的历史里，2026-02-10、02-11、03-25 三次改动都动了邻近行但没删这三行）。
- 该文件最后一次改动：`1b49834361f`，2026-03-31。
- 仓库归档 HEAD 版本号 `v0.43.2026040601`，即 2026-04-06 左右。

**所以：这条注释在归档时点仍然有效地表达第一方的认知，且从写下到归档存活约 2.5 个月。但它反映的是 2026-01 到 2026-04 之间的 CAPI 状态，不能推断今天（2026-08）的状态。** 我们实测 `{"type":"web_search"}` 返回 200 且真的执行搜索，这与该注释并不矛盾——`WebSearch` 是 Claude Agent SDK 的工具名，对应 Anthropic 的 `web_search_20250305`，而 CAPI 现在支持的是 OpenAI 系拼法。证据权重：**中**（日期与存活区间是硬事实；「不矛盾」的解读是我的推断）。

---

## 4. Q4：扩展走不走 `/responses`，发过 builtin 工具吗

### 4.1 走，而且是一等公民

`src/platform/endpoint/common/endpointProvider.ts:73-78`：

```ts
export enum ModelSupportedEndpoint {
	ChatCompletions = '/chat/completions',
	Responses = '/responses',
	WebSocketResponses = 'ws:/responses',
	Messages = '/v1/messages'
}
```

请求体构造器是 `createResponsesRequestBody`（`src/platform/endpoint/node/responsesApi.ts:32-96`），产出字段（逐行读完的完整清单）：

| 字段 | 取值 | 行号 |
|---|---|---|
| `stream` | `true` | `:40` |
| `tools` | 全部写死 `type: 'function'`、`strict: false` | `:42-47` |
| `max_output_tokens` | 由 `postOptions.max_tokens` 改名 | `:50` |
| `tool_choice` | 对象形态归一为 `{ type: 'function', name }`，否则透传 | `:51-53` |
| `top_logprobs` | `logprobs ? 3 : undefined` | `:54` |
| `store` | **硬编码 `false`** | `:55` |
| `text` | `verbosity ? { verbosity } : undefined` | `:56` |
| `context_management` | 仅实验开关开 + 模型不在排除表 | `:59-68` |
| `truncation` | `'auto'` / `'disabled'` | `:70-72` |
| `reasoning` | `effort`（仅 `supportsReasoningEffort?.length` 非空）+ `summary`（`gpt-5.3-codex-spark-preview` 强制关） | `:74-86` |
| `include` | **无条件 `['reasoning.encrypted_content']`** | `:88` |
| `prompt_cache_key` | 仅实验开关开 + 有 `conversationId` | `:89-92` |

### 4.2 从没发过 builtin 工具

`tools` 的构造是 map + 写死 `type: 'function'`，类型上就是 `OpenAI.Responses.FunctionTool & OpenAiResponsesFunctionTool`。结合 §1.2 的字面量零命中：**扩展自己发往 `/responses` 的 `tools` 里从来只有 function tool**。

`input` 侧同理——`rawMessagesToResponseAPI`（`responsesApi.ts:107-176` + 辅助函数）能产出的 item 类型穷举为：`message`（user/system/developer/assistant）、`function_call`（`:141`）、`function_call_output`（`:160`）、`reasoning`（`:216-224`）、compaction item（`:240-260`）、以及 user 消息里的 `input_text` / `input_image` / `input_file`（`:194-204`）。**没有任何代码路径能生成 `web_search_call` 进入 `input`**。

---

## 5. Q5：响应侧对 `web_search_call` / `url_citation` 的处理

### 5.1 原生 Responses 处理器：完全不处理

`OpenAIResponsesProcessor.push`（`src/platform/endpoint/node/responsesApi.ts:486-620`）的 `switch (chunk.type)` 分支穷举：

| 事件 | 行号 | 处理 |
|---|---|---|
| `error` | `:493` | 转 `copilotErrors` |
| `response.output_text.delta` | `:495` | 文本 + logprobs |
| `response.output_item.added` | `:508` | **只在 `item.type === 'function_call'` 时处理**，其它一律 `return` |
| `response.function_call_arguments.delta` | `:517` | 累积参数 |
| `response.output_item.done` | `:532` | 只认 compaction / `function_call` / `reasoning` / `message` |
| `response.reasoning_summary_text.delta` | `:574` | thinking |
| `response.reasoning_summary_part.done` | `:583` | thinking |
| `response.completed` | `:591` | 汇总 usage + 最终 message |

**没有 `web_search_call` 分支，没有 `response.output_text.annotation.added` 分支，`url_citation` 全仓零命中。**

唯一被处理的 hosted item 类型出现在 `response.completed` 的最终汇总里（`:615-621`）：

```ts
content: chunk.response.output.map((item): Raw.ChatCompletionContentPart | undefined => {
	if (item.type === 'message') {
		return { type: Raw.ChatCompletionContentPartKind.Text, text: item.content.map(c => c.type === 'output_text' ? c.text : c.refusal).join('') };
	} else if (item.type === 'image_generation_call' && item.result) {
		return { type: Raw.ChatCompletionContentPartKind.Image, imageUrl: { url: item.result } };
	}
}).filter(isDefined),
```

`image_generation_call` 被处理、`web_search_call` 没有——这说明**类型联合里是有这些 hosted item 的（OpenAI SDK 的完整联合），第一方是有选择地只接了一个**。这是「不处理」而非「不知道」的直接证据。证据权重：**强**。

顺带一条对我们有用的：`responsesApi.ts:207-212` 在把历史 assistant 文本回填进 `input` 时，`annotations` 被强制置空：

```ts
function rawContentToResponsesOutputContent(part: Raw.ChatCompletionContentPart): ... {
	switch (part.type) {
		case Raw.ChatCompletionContentPartKind.Text:
			if (part.text.trim()) {
				return { type: 'output_text', text: part.text, annotations: [] };
			}
	}
}
```

即便上游真的回了 `url_citation` annotation，扩展在下一轮也会把它丢掉。

### 5.2 Codex 兼容层：字节透传，不解释

`StreamingPassThroughEndpoint.processResponseFromChatEndpoint`（`oaiLanguageModelServer.ts:445-505`）：

```ts
const processor = this.instantiationService.createInstance(OpenAIResponsesProcessor, telemetryData, requestId, ghRequestId);
const parser = new SSEParser((ev) => { ... processor.push(...) ... });
...
for await (const chunk of body) {
	if (cancellationToken?.isCancellationRequested) { break; }
	this.responseStream.write(chunk);   // ← 原始字节直接写给 Codex
	parser.feed(chunk);                  // ← 只为日志/计费再解析一遍
}
```

注释 `:478` 自陈：*"We parse the stream just to return a correct ChatCompletion for logging the response and token usage details."*

**所以对 Codex 那一侧，任何 `web_search_call` item 都会原样透传，扩展的处理器只是漏掉不认识的事件。** 这是一个对我们有直接参考价值的形态：**兼容层做出站过滤 + 响应侧字节透传**。

### 5.3 有一个「server tool call」出口，但只接了 tool_search

`src/platform/networking/common/fetch.ts:88-93`：

```ts
export interface IServerToolCall {
	/** Indicates this is a server-side tool call (e.g., tool_search, websearch) - not validated/executed by client */
	isServer: true;
	name: string;
	id: string;
	...
```

注释里写了 `websearch`，但全仓 `isServer: true` 的产出点只有两处（`rg "isServer"` 穷举）：`src/platform/endpoint/node/messagesApi.ts:774` 与 `:821`，**都在 `tool_search_tool_result` 的成功/失败分支里**。Responses 处理器一次都没用过这个字段。

### 5.4 唯一完整实现 web search 响应侧的地方：BYOK 直连 Anthropic

`src/extension/byok/vscode-node/anthropicProvider.ts`：

- 请求侧 `:199-233` 构造 `{ name: 'web_search', type: 'web_search_20250305', max_uses, allowed_domains|blocked_domains, user_location }`，由 `ConfigKey.AnthropicWebSearchToolEnabled` 门控（`src/platform/configuration/common/configurationService.ts:904`，`ConfigType.ExperimentBased`，默认 `false`；`package.json:3838-3846` 标 `experimental` + `onExp`）。注释 `:199-201` 自陈：*"We need to do this because there is no local web_search tool definition we can replace."*——**第一方自己承认没有本地 web_search 工具可用**，这是 §2.1 结论的独立佐证。
- 响应侧 `:584-590` 接 `server_tool_use` content block；`:604-635` 接 `web_search_tool_result`，把结果序列化成 JSON 塞进 `LanguageModelToolResultPart`，并留了 TODO：*"instead of just pushing text, create a specialized WebSearchResult part"*。
- 引用侧 `:676-700` 接 `citations_delta` 里的 `web_search_result_location`，渲染成 markdown blockquote：``` `\n> "${citation.cited_text}" — [Source](${citation.url})\n\n` ```，同时把结构化 citation 数据存进一个 id 为 `'citation'` 的 `LanguageModelToolResultPart` 供多轮使用。

这条路是 BYOK 用户自带 key 直连 `api.anthropic.com`，**与 Copilot 上游无关**。但它是本仓库里唯一能抄的 web search 响应渲染样板。

---

## 6. 「扩展自用」vs「对外兼容层」的分野（本次审计的核心区分）

| | 扩展自用路径 | Codex 兼容层 | Claude Code 兼容层 |
|---|---|---|---|
| 入口 | VS Code chat participant | `oaiLanguageModelServer.ts` `POST /responses` | `claudeLanguageModelServer.ts` `POST /v1/messages` |
| 请求体来源 | 自己构造 | 外部 JSON 原样 | 外部 JSON 原样 |
| `tools` 处理 | 白名单写死 `type:'function'`（`responsesApi.ts:42-47`）/ 无 `type`（`messagesApi.ts:114-141`） | **黑名单剔除 `web_search*`**（`oaiLanguageModelServer.ts:134-143`） | **无任何处理**（`claudeLanguageModelServer.ts:728-746` 全量合并） |
| 防线位置 | 构造层 | 代理层 | **推到客户端**：`claudeCodeAgent.ts:434` 的 SDK `disallowedTools`；terminal 路径（`terminalCommand.ts:89-105`）**无防线** |
| 响应侧 | `OpenAIResponsesProcessor` 只认 function_call / reasoning / message / compaction / image_generation_call | 字节透传 + 旁路解析仅供日志 | 同左（`claudeLanguageModelServer.ts` 内的 `ClaudeStreamingPassThroughEndpoint`） |

**对本项目最相关的一栏是最右列，而那一栏第一方给的答案是「没解决」。** 我们的代理位置与 `ClaudeLanguageModelServer` 同构，但我们服务的是外部任意 Claude Code 实例，无法像 `claudeCodeAgent.ts` 那样从客户端侧禁用工具——第一方的做法在我们这里**不可直接照搬**。可照搬的是中间那一列的形态：在代理层按 `type` 剔除。

---

## 7. 与前文 `260820-websearch-400-vscode-ext.md` 的分歧

### 7.1 复核确认的部分（无分歧）

前文 §1.1、§1.4、§2.1、§2.2、§2.3、§3、§4 的引文与行号我逐条核对，**全部准确**，`52032e48d` 的日期、作者、标题也复核无误。§1.3 关于 `#web` / `bing-search` 的三处引用同样准确。

### 7.2 【推理缺陷】前文 §5.1 第三条论据不成立

前文写：

> 若 400 是由 `input` 里的 `web_search_call` item 触发，仅过滤 `tools` 的修复**不足以**让 Codex 直通跑通（Codex 会话第二轮就会带上历史）。该修复自 2025-11-01 起一直保留到归档 HEAD，未被追加 input 过滤补丁 —— 这是**行为层面的间接印证**。

**这条推不出来。** 一旦 `tools` 里没有 web_search，模型就不会产出 web_search 调用，Codex CLI 的会话历史里也就永远不会积累 `web_search_call` item。所以「没有追加 input 过滤补丁」是**必然的**，无论 input 侧会不会触发 400——这个观察对两种假设的似然完全相同，**不构成任何印证**。

前文 §5.2 其实已经把正确的话说出来了（「扩展源码不能证明……它只是从不制造这种输入」），但 §5.1 仍把它当作论据列进「直接证据」，且 §7 汇总表里把「400 由 `tools` 声明触发」标成「倾向性强（三处一致指向）」——**去掉这一条后只剩两处一致指向（修复动作 + 提交标题/日志文案），而这两处本质上是同一件事的两种表述**。我建议把该结论的权重从「倾向性强」下调为「**中等，仅说明第一方认为问题出在 `tools` 上，不构成对 input 侧的任何判断**」。

### 7.3 【重要遗漏】前文把 `disallowedTools` 的适用范围说宽了

前文 §1.2 写：

> 这是把 Claude Agent SDK 跑在 Copilot（CAPI）token 之上时，**在 SDK 层面禁用** WebSearch。

这句本身对，但它没说的是：**同一扩展还有一条 terminal 路径，把真的 `claude` CLI 指向同一个本地服务器却不加这个禁用**（`terminalCommand.ts:89-105`），而**那个本地服务器对 `tools` 零过滤**（§3.3）。前文完全没有提到 `claudeLanguageModelServer.ts` 这个文件的存在。

这个遗漏有实际后果：读前文会得到「第一方在 Claude Code 这条路上是防住了的」的印象，从而推出「照抄第一方即可」。实际上第一方在与我们同构的那个位置上**留了洞**，我们必须自己决定怎么办——这正是本次任务真正需要的输入。

### 7.4 【补强】前文 §1.5 的证伪检索可以做得更硬

前文说「`web_search_call`、`web_search_preview`、`WebSearchTool` 的命中只有 BYOK 与 Copilot CLI 工具名表」。实测更强：**`web_search_call` 和 `web_search_preview` 是零命中**（`WebSearchTool` 那个命中是 `copilotCLITools.ts:179` 的 TS type 名）。再加上 `code_interpreter`、`url_citation`、`computer_use` 三个零命中，以及「全仓 `tools` 数组过滤点只有 3 处、其中 2 处无关」的穷举，「不存在映射代码」这个结论可以从「检索没找到」升级为「**结构性穷举**」。

---

## 8. 对 `ghc-api-proxy-py` 的可操作结论

1. **不要指望在扩展里找到 `web_search_20250305` → Copilot 拼法的映射代码，它不存在。** 我们实测的 `{"type":"web_search"}` 返回 200 并真的执行搜索，这是**扩展代码之外的新事实**，第一方从未探索过这条路（他们的时代 CAPI 还不支持，见 §3.4）。因此「照抄第一方 = 剔除」是**当时正确、今天未必最优**的选择，这是一个需要用户裁决的分叉，而不是可以照抄的既定结论。
2. **剔除的形态可以照抄**：在代理层按 `tool.type` 判断并剔除 + warn（`oaiLanguageModelServer.ts:134-143`），响应侧字节透传（`:496-500`）。这是第一方在与我们同构位置上唯一给出的完整样板。
3. **不要为 `unsupported_value` 写降级重试**：前文 §3 已穷举 `chatMLFetcher.ts:1470-1530` 的全部 400 分支（`off_topic`、`previous_response_not_found`、401/403、402），我复核确认没有 `unsupported_value` 分支。第一方的策略是**出站前预防，不是收到后补救**。
4. **响应侧若要落地 web search，唯一可抄的渲染样板在 `anthropicProvider.ts:604-700`**（`web_search_tool_result` → tool result part；`web_search_result_location` → markdown blockquote + 结构化 citation part）。注意它带着两个未完成的 TODO，第一方自己也认为这是权宜之计。
5. **`/responses` 请求体的其它硬编码约定值得对齐**：`store: false`（`responsesApi.ts:55`）、`include: ['reasoning.encrypted_content']`（`:88`）、`tool_choice` 对象形态归一为 `{ type: 'function', name }`（`:51-53`）。

---

## 9. 本次审计的范围限制

- 只读源码，**没有发起任何真实上游请求**。所有关于「上游如何行为」的判断都是从第一方的规避动作反推的，权重上限就是「第一方当时相信什么」。
- 仓库归档于 `5863f5a70`（约 2026-04-06）。CAPI 此后的变化（例如我们实测到的 `{"type":"web_search"}` 可用）不在此代码基的视野内。
- **未检索 `node_modules/`**。`@vscode/copilot-api` 与 `openai` 包的类型定义可能含更多字段；若需确认 `/models` 响应或 Responses 事件联合的完整形状，应直接查包或实测端点。
- Copilot CLI 会话（`copilotcli/`）的 `web_search` 工具由 CLI 进程自己执行，**本仓库无法判断它走哪个端点、用什么拼法**。若这条线索重要，需要另行调查 Copilot CLI 本体。
- `.jsonl` 测试 fixture 里的 `server_tool_use: { web_search_requests: 0 }` 是 Claude Agent SDK usage 结构的固有字段，与本主题无关，已在检索中排除。
