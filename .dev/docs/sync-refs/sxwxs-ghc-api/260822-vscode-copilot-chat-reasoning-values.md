# vscode-copilot-chat 官方源码考据：`thinking` 与 `reasoning` 的取值与映射

考据对象：`/home/xp/src/refs/vscode-copilot-chat/`（只读，未做任何修改）
考据目的：用第一方客户端的实际请求构造，校正我方 `src/app/pipeline/translation_driver/reasoning.py` 中「自己拍的产品策略」。
设计背景：`.dev/docs/sync-refs/sxwxs-ghc-api/260821-design-thinking-effort-wiring.md`

## 0. 版本信息与一条必须先说的限定

| 项 | 值 |
|---|---|
| `package.json` name / version | `copilot-chat` / `0.44.0` |
| git HEAD | `5863f5a7088958050792b5dccbe8b46c6e13eccc` |
| HEAD 提交信息 / 日期 | `Add archive notice (#5120)` / 2026-05-20 |
| 上一条实质提交 | `9e668cb12 Yemohyle/subagent telem (#4916)` / 2026-04-06 |

**这个仓库已归档。** `README.md:1-7`（分类：文档）：

```
> [!IMPORTANT]
> This project has been moved into the main VS Code repository and this repository is now archived.
>
> Active development continues at:
> https://github.com/microsoft/vscode
```

所以本报告的全部结论都带一条时间限定：**代码停在 2026-04/05，而模型目录是活的**。这条限定不是免责声明，它有可判定的后果——下面第 1 节会看到，官方 UI 的 effort 文案里根本没有 `max` 这一档，而我方 2026-08 实录的目录里已经有 5 个模型发布 `max`。判断某条结论还成不成立，看它依赖的是「代码逻辑」还是「当时的目录内容」：前者仍是权威，后者已经过期。

**权重声明**：本报告对「官方代码怎么写」的结论强到可直接据以行动（有原文与行号）；对「上游到底接受什么」的结论只是**下界**（官方发过的一定被接受，官方没发过的不等于不被接受）。

---

## 1. effort 的合法取值集合

### 结论

官方**不硬编码 effort 集合**。集合来自模型目录字段 `capabilities.supports.reasoning_effort`，类型是 `string[]`——一个开放的字符串数组，不是枚举。

**类型定义（次权威，说明协议允许什么）** `src/platform/endpoint/common/endpointProvider.ts:45-57`：

```ts
	supports: {
		parallel_tool_calls?: boolean;
		tool_calls?: boolean;
		// Whether or not the model supports streaming, if not explicitly true we will try to parse the response as not streamed
		streaming: boolean | undefined;
		vision?: boolean;
		prediction?: boolean;
		thinking?: boolean;
		adaptive_thinking?: boolean;
		max_thinking_budget?: number;
		min_thinking_budget?: number;
		reasoning_effort?: string[];
	};
```

**读取处（权威，请求构造链路的上游）** `src/platform/endpoint/node/chatEndpoint.ts:169-172`：

```ts
		this.supportsAdaptiveThinking = modelMetadata.capabilities.supports.adaptive_thinking;
		this.minThinkingBudget = modelMetadata.capabilities.supports.min_thinking_budget;
		this.maxThinkingBudget = modelMetadata.capabilities.supports.max_thinking_budget;
		this.supportsReasoningEffort = modelMetadata.capabilities.supports.reasoning_effort;
```

### 官方认识到的取值名

唯一一处把 effort 名逐个列出来的地方是模型选择器 UI 的下拉文案。**分类：请求构造的邻接代码（它决定用户能选什么，进而决定实际发什么），权重次于请求构造本身。** `src/extension/conversation/vscode-node/languageModelAccess.ts:73-92`：

```ts
				reasoningEffort: {
					type: 'string',
					title: vscode.l10n.t('Thinking Effort'),
					enum: effortLevels,
					enumItemLabels: effortLevels.map(level => level.charAt(0).toUpperCase() + level.slice(1)),
					enumDescriptions: effortLevels.map(level => {
						switch (level) {
							case 'none': return vscode.l10n.t('No reasoning applied');
							case 'low': return vscode.l10n.t('Faster responses with less reasoning');
							case 'medium': return vscode.l10n.t('Balanced reasoning and speed');
							case 'high': return vscode.l10n.t('Greater reasoning depth but slower');
							case 'xhigh': return vscode.l10n.t('Maximum reasoning depth but slower');
							default: return level;
						}
					}),
					default: defaultEffort,
					group: 'navigation',
				}
```

注意 `enum: effortLevels` —— 下拉项本身**就是目录数组原样**，`switch` 只负责文案，`default: return level` 是显式的兜底。所以官方的设计意图明确：**目录可以发出官方没见过的 effort 名，客户端照样把它展示并原样发出**。

已知被官方文案覆盖的：`none` `low` `medium` `high` `xhigh`（五个，**没有 `max`**）。

`max` 在整个仓库里只出现一次，在 BYOK 的 Anthropic 直连路径上，而且只是一个 TypeScript 断言而非枚举校验 —— `src/extension/byok/vscode-node/anthropicProvider.ts:262-266`（分类：请求构造，但属于 BYOK 旁路而非 Copilot 主路径）：

```ts
			const rawEffort = options.modelConfiguration?.reasoningEffort;
			const supportsEffort = modelCapabilities?.supportsReasoningEffort;
			const effort = supportsEffort && typeof rawEffort === 'string' && supportsEffort.includes(rawEffort)
				? rawEffort as 'low' | 'medium' | 'high' | 'max'
				: undefined;
```

团队内部覆盖设置的类型（分类：配置声明，弱于请求构造）`src/platform/configuration/common/configurationService.ts:852-855`：

```ts
		/** Internal: configure reasoning effort for Responses API. Used by evals. */
		export const ResponsesApiReasoningEffort = defineTeamInternalSetting<'low' | 'medium' | 'high' | 'xhigh' | undefined>('chat.advanced.responsesApiReasoningEffort', ConfigType.Simple, undefined);
		/** Internal: configure reasoning effort for Anthropic thinking. Used by evals. */
		export const AnthropicThinkingEffort = defineTeamInternalSetting<'low' | 'medium' | 'high' | undefined>('chat.advanced.anthropicThinkingEffort', ConfigType.Simple, undefined);
```

Responses 侧的内部覆盖只到 `xhigh`（无 `none`、无 `max`），Anthropic 侧只到 `high`。这两个是 evals 用的调试开关，**不是协议边界**。

### 未在本仓库找到的

- **没有找到任何模型目录的 JSON 固件**。`rg 'reasoning_effort'` 在非 `.ts` 文件中零命中（已检索全仓所有 `*.json`，含 `--no-ignore`）。所以这个仓库回答不了「目录实际发了哪些名字」。
- **未找到 `minimal`**（见下方对照，这是我方目录里真实存在的一个名字）。

### 交叉证据：我方实录目录（第一手，2026-08，强于官方源码的时效性）

`tests/int/cassettes/anthropic_to_responses_stream.json` 里 `GET /models` 的真实响应（我方录制），`reasoning_effort` 全量：

| 模型 | `reasoning_effort` | `adaptive_thinking` | `min/max_thinking_budget` | `supported_endpoints` |
|---|---|---|---|---|
| claude-opus-4.6 | `low, medium, high, max` | `true` | 1024 / 32000 | `/v1/messages`, `/chat/completions` |
| claude-opus-4.7 / 4.8 / claude-opus-5 / claude-sonnet-5 | `low, medium, high, xhigh, max` | `true` | 1024 / 32000 | `/v1/messages`, `/chat/completions` |
| claude-sonnet-4.6 | `low, medium, high, max` | `true` | 1024 / 32000 | `/chat/completions`, `/v1/messages` |
| claude-haiku-4.5 | *（无此字段）* | *(无)* | 1024 / 32000 | `/chat/completions`, `/v1/messages` |
| gemini-3.1-pro-preview | `low, medium, high` | *(无)* | 256 / 32000 | `/chat/completions` |
| **gemini-3.5-flash / 3.6-flash** | **`minimal, low, medium, high`** | *(无)* | 256 / 24000、256 / 32000 | `/chat/completions` |
| gemini-3.7-flash | `low, medium, high` | *(无)* | *(无)* | `/chat/completions` |
| gpt-5.3-codex | `low, medium, high, xhigh` | *(无)* | *(无)* | `/responses`, `ws:/responses` |
| gpt-5.4 / 5.4-mini / 5.5 | `none, low, medium, high, xhigh` | *(无)* | *(无)* | `/responses`(+`/chat/completions` for 5.4) |
| gpt-5.6-luna / sol / terra | `none, low, medium, high, xhigh, max` | *(无)* | *(无)* | `/responses`, `ws:/responses` |
| grok-4.5 | `low, medium, high` | *(无)* | *(无)* | `/responses` |
| grok-4.6 | `low, medium, high, xhigh` | *(无)* | *(无)* | `/responses` |
| mai-code-1.1-flash / mai-code-1-flash-picker / gpt-5-mini | `low, medium, high` | *(无)* | *(无)* | 含 `/responses` |

**两条要点**：

1. 目录里存在一个第七个名字 **`minimal`**，官方 UI 文案不认识它（走 `default: return level`），**我方 `EFFORT_LADDER` 也不认识它**。它目前只出现在 `/chat/completions` 专属的 gemini flash 上，因此在我方的 Responses 产品路径上**当前不会击中**——但这是「今天的目录如此」，不是结构保证。见第 7 节差异表。
2. `/responses` 端点的模型**全部不发布** `min_thinking_budget` / `max_thinking_budget`；发布它们的全是 Claude 与 Gemini。这**证实**了我方 `reasoning.py` 模块 docstring 第 9 行的判断。

---

## 2. budget_tokens → effort 的换算

### 结论：官方**完全没有**这个换算。两侧都没有。

**Responses 侧（权威，请求构造）** `src/platform/endpoint/node/responsesApi.ts:74-88` —— 全文如下，注意里面**没有任何数字**：

```ts
	const summaryConfig = configService.getExperimentBasedConfig(ConfigKey.ResponsesApiReasoningSummary, expService);
	const shouldDisableReasoningSummary = endpoint.family === 'gpt-5.3-codex-spark-preview';
	const effortFromSetting = configService.getConfig(ConfigKey.TeamInternal.ResponsesApiReasoningEffort);
	const effort = endpoint.supportsReasoningEffort?.length
		? (effortFromSetting || options.reasoningEffort || 'medium')
		: undefined;
	const summary = summaryConfig === 'off' || shouldDisableReasoningSummary ? undefined : summaryConfig;
	if (effort || summary) {
		body.reasoning = {
			...(effort ? { effort } : {}),
			...(summary ? { summary } : {})
		};
	}

	body.include = ['reasoning.encrypted_content'];
```

Responses 侧的 effort 来源只有三个，优先级从高到低：团队内部设置 → `options.reasoningEffort`（来自模型选择器下拉，见第 5 节）→ 硬编码字面量 `'medium'`。**没有 budget 这个概念存在于这条路径上**。

**Messages 侧（权威，请求构造）** `src/platform/endpoint/node/messagesApi.ts:144-177`：

```ts
	// Thinking is enabled only when options.enableThinking is true, a non-zero thinking budget
	// is configured for the model, and the model supports thinking. reasoningEffort (if present)
	// is used only to configure the effort level when thinking is enabled, not to gate it.
	const reasoningEffort = options.reasoningEffort;
	let thinkingConfig: { type: 'enabled' | 'adaptive'; budget_tokens?: number } | undefined;
	if (options.enableThinking) {
		const configuredBudget = configurationService.getConfig(ConfigKey.AnthropicThinkingBudget);
		const thinkingExplicitlyDisabled = configuredBudget === 0;
		if (endpoint.supportsAdaptiveThinking && !thinkingExplicitlyDisabled) {
			thinkingConfig = { type: 'adaptive' };
		} else if (!thinkingExplicitlyDisabled && endpoint.maxThinkingBudget && endpoint.minThinkingBudget) {
			const maxTokens = options.postOptions.max_tokens ?? 1024;
			const minBudget = endpoint.minThinkingBudget ?? 1024;
			const normalizedBudget = (configuredBudget && configuredBudget > 0)
				? (configuredBudget < minBudget ? minBudget : configuredBudget)
				: undefined;
			const maxBudget = endpoint.maxThinkingBudget ?? 32000;
			const thinkingBudget = normalizedBudget
				? Math.min(maxBudget, maxTokens - 1, normalizedBudget)
				: undefined;
			if (thinkingBudget) {
				thinkingConfig = { type: 'enabled', budget_tokens: thinkingBudget };
			}
		}
	}

	const thinkingEnabled = !!thinkingConfig;
	let effort: 'low' | 'medium' | 'high' | undefined;
	if (thinkingConfig && endpoint.supportsReasoningEffort?.length) {
		const candidateEffort = configurationService.getConfig(ConfigKey.TeamInternal.AnthropicThinkingEffort) ?? reasoningEffort;
		if (candidateEffort === 'low' || candidateEffort === 'medium' || candidateEffort === 'high') {
			effort = candidateEffort;
		}
	}
```

budget 与 effort 在这里是**两个互不相干的量，并列发出**（`messagesApi.ts:233-234`）：

```ts
		thinking: thinkingConfig,
		...(effort ? { output_config: { effort } } : {}),
```

也就是说，官方在 Anthropic Messages 侧同时发 `thinking.budget_tokens` **和** `output_config.effort`，二者各自独立计算。budget 来自用户设置 `github.copilot.chat.anthropic.thinking.budgetTokens`（默认 16000，范围 0–32000，`package.json:3181-3187`），effort 来自模型选择器。

单元测试固化了这个并列关系（**分类：测试固件，弱证据，仅作为对代码意图的佐证**）`src/platform/endpoint/test/node/messagesApi.spec.ts:809-826`：

```ts
	test('uses budget_tokens thinking when model has maxThinkingBudget but not adaptive', () => {
		const endpoint = createMockEndpoint({
			supportsAdaptiveThinking: false,
			maxThinkingBudget: 32000,
			minThinkingBudget: 1024,
			supportsReasoningEffort: ['low', 'medium', 'high'],
		});
		mockConfig.setConfig(ConfigKey.AnthropicThinkingBudget, 10000);
		...
		expect(body.thinking).toEqual({ type: 'enabled', budget_tokens: 8191 });
		expect(body.output_config).toEqual({ effort: 'low' });
	});
```

### 对我方的意义

**官方给不出阈值，因为官方没有这个问题。** 官方是「用户在两个独立控件里分别选 budget 和 effort」，而我方是「Anthropic 客户端只给 budget，必须折算成 effort」。这是一个真实存在于我方而不存在于官方的翻译缺口。

因此：**我方 `BUDGET_LADDER` 的四个阈值没有、也不可能有官方依据。** `reasoning.py:18` 的注释「Policy, not measurement」是准确的，本次考据没有推翻它，也没有给它找到背书。这条结论强到可以据以行动：**不要再去找官方阈值了，它不存在。**

唯一一个官方数字可以借鉴的地方：`AnthropicThinkingBudget` 的默认值是 **16000**（`configurationService.ts:902`、`package.json:3186`），也就是官方认为「一个不加思考的合理思考预算」是 16k。我方阶梯里 16000 恰好是 `xhigh` 的门槛。这个巧合**不构成证据**，只是一个可以拿来做直觉校验的参照点：如果我方把 16k 判成 `xhigh`，等于说「官方的默认档 = 次高档」，偏高。见第 8 节建议。

---

## 3. `thinking: {"type": "disabled"}` 怎么表达

### 结论：官方在 Responses 侧**根本没有"关闭"这个概念**，因此这个问题在官方那里无解，我方无法从官方获得校正。

证据是 `responsesApi.ts:77-79` 的三元式本身：

```ts
	const effort = endpoint.supportsReasoningEffort?.length
		? (effortFromSetting || options.reasoningEffort || 'medium')
		: undefined;
```

**`options.enableThinking` 在整个 `createResponsesRequestBody` 里一次都没被读。** 已检索：`rg -n 'enableThinking' src/platform/endpoint/node/responsesApi.ts` 零命中；全仓 `enableThinking` 的读取点只有 `messagesApi.ts:149` 一处（其余全是写入与转发）。

所以官方 Responses 请求的行为是：

- 模型目录发布了任意非空 effort 集 → **必发 `reasoning.effort`**，值为用户选的那个，用户没选就是硬编码 `'medium'`。
- 模型目录没发布 effort（`undefined` 或 `[]`）→ **不发 `effort` 键**（但仍可能因 `summary` 存在而发 `reasoning` 对象，见第 4 节）。

用户唯一能表达「不要推理」的途径是：**目录里恰好有 `none` 这个档，用户在模型选择器里手选它**，于是 `options.reasoningEffort === 'none'` 被原样透传。官方从未把它当作一个特殊值处理——`'none'` 在 Responses 请求构造代码里根本没出现过（已检索：`rg "effort.*'none'|'none'.*effort" --type ts` 零命中；`'none'` 仅出现于 `languageModelAccess.ts:82` 的 UI 文案 switch）。

### 与我方实测的关系

我方实测「省略 `reasoning` 会被上游规范化成 `medium`」。官方代码**间接印证**了这一点，但方向是反的：官方在有 effort 集时**从不省略**，兜底值就写死成 `'medium'`。换句话说，**官方客户端和上游默认值达成了同一个答案 `medium`**——这看起来像是官方知道省略的后果，索性显式写死。

分类说明：这是我基于代码形状的推断，**不是官方注释说的**，权重为「倾向性判断，不足以单独支撑决策」。可以据以行动的只有那条硬事实：官方对 Responses 的 effort 兜底是字面量 `'medium'`。

### 一个反向证据：BYOK 路径确实会整体删掉 `reasoning`

`src/extension/byok/node/openAIEndpoint.ts:238-249`（分类：请求构造，BYOK 旁路）：

```ts
	override createRequestBody(options: ICreateEndpointBodyOptions): IEndpointBody {
		if (this.useResponsesApi) {
			// Handle Responses API: customize the body directly
			options.ignoreStatefulMarker = false;
			const body = super.createRequestBody(options);
			body.store = true;
			body.n = undefined;
			body.stream_options = undefined;
			if (!this.modelMetadata.capabilities.supports.thinking) {
				body.reasoning = undefined;
				body.include = undefined;
			}
```

**注意判据是 `supports.thinking`（模型不会推理），不是「用户想关闭推理」。** 这仍然不是一个「关闭」表达式，而是「这个模型没有推理这回事，别发这个字段」。而且这条只在 BYOK（用户自带 OpenAI key）路径生效，Copilot 主路径的 `ChatEndpoint` 不做这件事。

---

## 4. `reasoning` 对象的完整形状

### 官方实际发出的键：只有 `effort` 和 `summary`，加上一个与之配套的顶层 `include`

**类型定义（次权威）** `src/platform/networking/common/networking.ts:78`：

```ts
	reasoning?: { effort?: string; summary?: string };
```

`src/platform/networking/common/networking.ts:108`：

```ts
	include?: ['reasoning.encrypted_content'];
```

注意 `include` 的类型是一个**长度固定为 1 的元组字面量**，不是 `string[]`。这是官方自己给自己划的边界：这个字段只会是这一个值。

**请求构造（权威）** `responsesApi.ts:81-88`（全文已在第 2 节引出），要点：

- `effort`：见第 1、2、3 节。
- `summary`：来自 `ConfigKey.ResponsesApiReasoningSummary`，取值域**只有两个**：`'off' | 'detailed'`，默认 `'detailed'`。`'off'` 被转成不发键。
  `src/platform/configuration/common/configurationService.ts:889`：
  ```ts
  export const ResponsesApiReasoningSummary = defineSetting<'off' | 'detailed'>('chat.responsesApiReasoningSummary', ConfigType.ExperimentBased, 'detailed');
  ```
  `package.json:3780-3792` 里 `"enum": ["off", "detailed"]`，`"default": "detailed"`。
  **官方从不发 `auto`，也从不发 `concise`。**（已检索：`rg "'auto'" src/platform/endpoint/node/responsesApi.ts` 只命中 `truncation: 'auto'` 与图片 `detail: 'auto'`，与 reasoning 无关。）
- 另有一个机型级别的强制关闭：`responsesApi.ts:75`
  ```ts
  const shouldDisableReasoningSummary = endpoint.family === 'gpt-5.3-codex-spark-preview';
  ```
- `include`：**无条件设置**为 `['reasoning.encrypted_content']`（`responsesApi.ts:88`，在 `if` 之外）。唯一会被撤销的地方是上面第 3 节引的 BYOK `openAIEndpoint.ts:247`。

### 明确「未找到」的键

以下键在整个仓库中**零命中**，已检索范围：全仓 `--type ts`，以及 `rg 'current_turn|all_turns'` 全仓：

- **`reasoning.context`** —— 未找到。`current_turn` / `all_turns` 两个字面量在全仓不存在。
- **`reasoning.mode`** —— 未找到。`'standard'` 与 reasoning 无任何关联出现。
- **`reasoning.generate_summary`**（Responses 的旧字段名）—— 未找到。

`customizeResponsesBody` 是给子类加字段的钩子，全仓**没有任何覆盖实现**，基类原样返回（`chatEndpoint.ts:339-341`）：

```ts
	protected customizeResponsesBody(body: IEndpointBody): IEndpointBody {
		return body;
	}
```

已检索：`rg -n 'customizeResponsesBody' --type ts` 只有两处命中（调用点 `chatEndpoint.ts:303` 与定义 `:339`）。所以 `responsesApi.ts` 里那 4 个键就是官方 Copilot 主路径 `reasoning` 相关的**全部**。

### Anthropic 侧的对应形状（供交叉参考）

`src/platform/networking/common/networking.ts:115-124`（次权威，类型定义）：

```ts
	thinking?: {
		type: 'enabled' | 'disabled' | 'adaptive';
		budget_tokens?: number;
	};
	output_config?: {
		effort?: 'low' | 'medium' | 'high';
	};

	/** ChatCompletions API for Anthropic models */
	thinking_budget?: number;
```

三点值得记：

1. **类型里有 `'disabled'`，但生产代码从不构造它**——`messagesApi.ts` 只产出 `'enabled'` 与 `'adaptive'`（局部变量类型 `messagesApi.ts:148` 就写死了这两个），关闭的做法是让 `thinkingConfig` 保持 `undefined`、整个 `thinking` 键不发。所以「协议允许 `disabled`」与「官方发 `disabled`」是两回事，**官方不发**。
2. Anthropic 侧的 effort 挂在 **`output_config.effort`**，不是 `reasoning.effort`，且类型收窄到 `low|medium|high`。
3. `thinking_budget?: number`（`/chat/completions` 的 Anthropic 形状）**在整个仓库中没有任何赋值点**，已检索 `rg -n 'thinking_budget' --type ts`：仅 5 处命中，全是 `min_/max_thinking_budget` 或这条类型声明本身。属于预留/死字段。

---

## 5. 模型能力如何决定发什么

完整链路（全部为权威的请求构造/能力读取代码）：

1. **目录 → endpoint 字段**：`chatEndpoint.ts:169-172`（已引）。
2. **endpoint → UI 下拉**：`languageModelAccess.ts:51-67`
   ```ts
   	const effortLevels = endpoint.supportsReasoningEffort;
   	if (!effortLevels || effortLevels.length === 0) {
   		return {};
   	}

   	// Auto model delegates to different backends, so don't expose effort picker
   	if (endpoint instanceof AutoChatEndpoint) {
   		return {};
   	}

   	// Only enable effort picker for Claude and GPT models
   	const family = endpoint.family.toLowerCase();
   	if (!family.startsWith('claude') && !family.startsWith('gpt-')) {
   		return {};
   	}

   	const preferred = family.startsWith('claude') ? 'high' : 'medium';
   	const defaultEffort = effortLevels.includes(preferred) ? preferred : undefined;
   ```
   **官方的默认档是分家族的：Claude 默认 `high`，GPT 默认 `medium`**，且都用 `includes` 校验后才采用。grok / gemini / mai 家族**根本不给 effort 选择器**（即便目录发布了 effort），于是它们永远走 `responsesApi.ts` 的 `'medium'` 兜底。
3. **UI 选择 → 请求选项**：`src/extension/intents/node/toolCallingLoop.ts:1418-1421`
   ```ts
   		const rawEffort = this.options.request.modelConfiguration?.reasoningEffort;
   		const reasoningEffort = typeof rawEffort === 'string' ? rawEffort : undefined;
   		const shouldDisableThinking = isContinuation && isAnthropicFamily(endpoint) && !ToolCallingLoop.messagesContainThinking(effectiveBuildPromptResult.messages);
   		const enableThinking = !shouldDisableThinking;
   ```
   `enableThinking` 只在一个非常窄的场景被置否：**Anthropic 家族的续写请求且历史里没有 thinking 块**。与「用户想不想思考」无关。
4. **请求构造**：`chatEndpoint.ts:301-308` 按端点分流到 `createResponsesRequestBody` / `createMessagesRequestBody` / `createCapiRequestBody`。

### 关键差异：Responses 侧**不校验** effort 是否在集合内

这是本次考据最值得标注的一处**官方缺陷**（分类：权威代码的事实，判断为缺陷是我的评价）。三条路径的校验强度完全不同：

| 路径 | 校验方式 | 位置 |
|---|---|---|
| **Responses（主产品路径）** | 只检查集合**非空**，值本身**原样透传，不校验** | `responsesApi.ts:77-78` |
| Messages | 硬编码 `=== 'low' \|\| 'medium' \|\| 'high'`，**不看集合内容**（只看非空） | `messagesApi.ts:172-176` |
| BYOK Anthropic | `supportsEffort.includes(rawEffort)`，**真正校验** | `anthropicProvider.ts:264` |

Responses 侧之所以没炸，是因为下拉项本身就是 `enum: effortLevels`，用户选不出集合外的值——**校验被外包给了 UI**。一旦有别的调用方（比如我方这样的代理）绕过那个 UI，这层保护就不存在了。

Messages 侧的硬编码则有可见后果：目录给 `claude-opus-5` 发的是 `low, medium, high, xhigh, max`，但用户选了 `xhigh` 或 `max` 时 `messagesApi.ts:174` 的三项比较不通过，`effort` 变成 `undefined`，**整个 `output_config` 不发**。官方自己的测试把这个行为固化下来了（`messagesApi.spec.ts:793-806`，测试名就叫 `omits effort when reasoningEffort is an invalid value`，输入是 `'xhigh' as any`）——**在归档时点这是正确的，因为当时目录里 Claude 可能还没有 xhigh；在今天的目录下它是一个静默降级的 bug。** 这正是第 0 节那条时间限定的可判定后果之一。

### `min_thinking_budget` / `max_thinking_budget` 的实际使用

**被实际使用，但只在 Anthropic Messages 路径，且只用于夹逼一个用户配置的 budget**，见 `messagesApi.ts:154-163`（已引）。运算是：

```
thinkingBudget = min(maxThinkingBudget, max_tokens - 1, max(configuredBudget, minThinkingBudget))
```

**它们从不参与 effort 的任何计算。** 在 Responses 路径上这两个字段完全没被读（`responsesApi.ts` 全文无 `ThinkingBudget`）。这与第 1 节的目录事实一致：`/responses` 模型压根不发布它们。

---

## 6. 有没有 adaptive / auto 这一档

### Responses 侧：**没有。已检索并确认为负结论。**

已检索：`rg -n 'adaptive|Adaptive' --type ts` 全仓 40 处命中，逐条核对，**没有一处出现在 Responses 请求构造链路上**。命中分布：`messagesApi.ts`（Anthropic）、`anthropicProvider.ts`（BYOK Anthropic）、`chatEndpoint.ts` 的能力字段与 beta header、若干 `*LanguageModelServer.ts` 的属性转发、以及完全无关的 `throttledDebounce.ts` / `userInteractionMonitor.ts` / `embeddingsGrouper.spec.ts`。

`reasoning.effort` 的值也没有 `'auto'` 这一档（第 1 节的 UI switch 没有它，且它不是目录里任何模型发布的值）。

### Anthropic 侧：有，且是官方的首选

`messagesApi.ts:152-153`：

```ts
		if (endpoint.supportsAdaptiveThinking && !thinkingExplicitlyDisabled) {
			thinkingConfig = { type: 'adaptive' };
		} else if (...)
```

判据是目录字段 `capabilities.supports.adaptive_thinking`（`chatEndpoint.ts:169`）。**只要模型支持 adaptive，官方就用 adaptive，用户配的 budget 直接被忽略**（除非配成 0）。今天目录里所有 Claude 模型 `adaptive_thinking: true`，所以官方对 Claude 实际上从不发 `budget_tokens`。

配套的 beta header 也随之切换，`chatEndpoint.ts:193-197`：

```ts
			const betaFeatures: string[] = [];

			if (!this.supportsAdaptiveThinking) {
				betaFeatures.push('interleaved-thinking-2025-05-14');
			}
```

### 对我方 `ADAPTIVE_EFFORT = "high"` 的意义

官方在 Responses 侧**没有可对应物**，所以「adaptive 折算成哪一档」这个问题官方回答不了。但有一条弱的旁证可以借：官方给 **Claude 家族**（也就是 adaptive 家族）的 UI 默认档是 `'high'`（`languageModelAccess.ts:69`），给 GPT 是 `'medium'`。我方把 `adaptive` 映到 `high`，与「官方认为 Claude 用户想要 high」方向一致。

**权重：倾向性一致，不构成背书。** 这两件事的语义不同（一个是「用户没选时给什么」，一个是「模型自己决定该想多久」），不要把它写成「官方规定 adaptive = high」。

---

## 7. 与我方当前实现的差异对照

我方实现：`src/app/pipeline/translation_driver/reasoning.py`（读取于 2026-08-22）。

| # | 项 | 我方当前 | 官方 vscode-copilot-chat | 判定 |
|---|---|---|---|---|
| 1 | effort 集合来源 | 目录 `capabilities.supports.reasoning_effort`，逐请求传入 `capabilities` | 同源，`chatEndpoint.ts:172` | **一致** |
| 2 | 集合校验 | `resolve()` 尾部 `assert effort in capabilities`（`reasoning.py:171-174`） | Responses 侧**不校验**，原样透传（`responsesApi.ts:78`） | **我方更严，保持** |
| 3 | 已知 effort 名 | `EFFORT_LADDER = (none, low, medium, high, xhigh, max)` | UI 文案认识 `none/low/medium/high/xhigh`；`max` 仅见于 BYOK Anthropic 的类型断言 | **我方更全**（官方已归档、早于 `max` 上线） |
| 4 | **`minimal` 这一档** | **不在 `EFFORT_LADDER` 中** | 官方也不认识，但设计上允许（`default: return level`） | ⚠️ **我方有缺口，见下** |
| 5 | budget→effort 阈值 `>=30000→max / >=16000→xhigh / >=8000→high / >=3000→medium / else low` | 我方策略 | **官方无此换算，两侧都没有** | **无权威可校正；结论是"别再找了"** |
| 6 | `adaptive` → `high` | 我方策略 | Responses 侧无对应物；Claude 家族 UI 默认档是 `high`（弱旁证，方向一致） | **无权威背书，方向不矛盾，保持** |
| 7 | `disabled` → `none`（不支持时降到最低档） | 我方策略 | 官方无「关闭」概念；`none` 仅作为目录发布的一个普通档由用户手选，原样透传 | **无权威可校正；我方的语义映射是自洽的新增** |
| 8 | 不支持时**向下取** | `_at_or_below`，向下；无下位则 `_weakest` 上浮并标 approximated | Messages 侧硬编码三项，命中不了就**整个字段不发**（静默降级为上游默认）；Responses 侧无此场景 | **我方更好**（官方那个是 bug，见第 5 节） |
| 9 | 目录未发布 effort → 不发 `reasoning` | `capabilities is None` 或空 → `effort=None` | 一致：`endpoint.supportsReasoningEffort?.length` 为假 → `effort = undefined` | **一致** |
| 10 | 不发 `reasoning` 的后果 | 我方 docstring 明确记录「上游会规范化成 medium」 | 官方兜底硬编码 `'medium'`，效果同值 | **一致（殊途同归）** |
| 11 | `reasoning.summary` | 我方目前**不发**（`reasoning.py` 只产出 effort） | 官方**默认发 `summary: 'detailed'`** | ⚠️ **实质差异，见下** |
| 12 | `include: ['reasoning.encrypted_content']` | 需另行核对我方是否发送（本报告未查我方该处） | 官方**无条件发** | ⚠️ **待核对** |
| 13 | `reasoning.context` / `.mode` | 我方不发 | 官方也不发，全仓零命中 | **一致** |
| 14 | `min/max_thinking_budget` | 我方 docstring 说 Responses 侧不发布、不借用 | 证实：`/responses` 模型目录里确实没有这两个字段；官方只在 Anthropic 路径夹逼 budget 用 | **一致，判断被证实** |

### ⚠️ 差异 4：`minimal` 不在我方阶梯里

我方 `EFFORT_LADDER` 缺 `minimal`。后果可推演：若某模型发布 `["minimal", "low", "medium", "high"]`，一个 `thinking: {"type":"disabled"}` 请求走到 `_desired` 得到 `"none"` → `_at_or_below("none", ...)` 返回 `None`（`none` 不在集合里，且它下面没有别的档）→ 落到 `_weakest`，而 `_weakest` 遍历的是 `EFFORT_LADDER`，**看不见 `minimal`**，于是返回 `"low"`。本该是 `minimal` 的答案变成了 `low`——比请求要求的多花钱，且 `reason` 文案会说「弱于本模型提供的任何档位」，**这句是假的**。

**当前不会击中**：`minimal` 只出现在 gemini-3.5/3.6-flash，二者 `supported_endpoints` 只有 `/chat/completions`，不在我方 Responses 产品路径上。**但**这依赖今天的目录内容，不是结构保证；而且 `resolve()` 的断言拦不住它（`low` 确实在集合里，断言通过）。这是一个**静默的错误答案**，不是一个会报错的 bug。

建议：`EFFORT_LADDER` 改为 `("none", "minimal", "low", "medium", "high", "xhigh", "max")`。理由是 `minimal` 是**目录里实际存在的字符串**（第一手证据，我方 2026-08 实录），而 `EFFORT_LADDER` 的职责按 `reasoning.py:15` 的注释就是「本项目自己声明的强弱序」——把一个已知存在的名字漏在序外，等于把它降级成"未知档"。同时 `reasoning.py:3` 的 docstring 举例列了四个模型的档位数，**没有提 `minimal`**，也该一并补上。

### ⚠️ 差异 11：`summary` 我方不发

官方主路径**默认发 `reasoning.summary = "detailed"`**，且这是一个用户可见设置（`github.copilot.chat.responsesApiReasoningSummary`，默认 `detailed`，可选 `off`）。我方目前 `reasoning.py` 只产出 `effort`。

这不是一个「谁对谁错」的差异，而是一个**我方未被决策的开口**：Anthropic 的 `thinking` 请求语义上是要拿回思考内容的，而 Responses 侧拿回思考摘要的开关就是 `summary`。若我方不发，上游给不给摘要取决于上游默认，而**上游默认我方未测**。

按 `no-silently-cut-but-defer`，我把它作为一个待裁决项交回，不自行决定。需要用户/主会话裁决的问题：我方是否应当在 `reasoning` 对象里发 `summary`？如果发，取 `"detailed"`（跟官方）还是 `"auto"`（Responses 协议允许但官方不发）？

### ⚠️ 差异 12：`include` 待核对

官方无条件发 `include: ['reasoning.encrypted_content']`。我方是否发送，本报告**未核查**（超出被派任务的检索范围，且需读我方 request builder 而非 `reasoning.py`）。如果我方不发而上游又不默认返回加密推理内容，跨轮次的推理上下文就传不回去。**标注为未验证的待办，不作结论。**

---

## 8. 建议采纳的权威取值

只列有官方依据的。没有依据的明确写成「无依据，维持我方策略」。

| 项 | 建议 | 依据强度 |
|---|---|---|
| effort 集合来源 | 继续**只从目录读**，绝不硬编码集合 | **强**：`endpointProvider.ts:56` 类型即 `string[]`，`languageModelAccess.ts:74` 直接把目录数组当 enum，`default: return level` 是官方显式承认未知名字 |
| `EFFORT_LADDER` | 补入 `minimal`，置于 `none` 与 `low` 之间 | **强**：`minimal` 是我方 2026-08 实录目录里的真实字符串（gemini-3.5/3.6-flash） |
| effort 校验 | 保持我方 `assert`，**不要**向官方看齐 | **强**：官方 Responses 侧把校验外包给 UI（`responsesApi.ts:77-78` 只判非空），代理场景下那层保护不存在 |
| 不支持时的降级方向 | 保持「向下取 + 无下位时上浮并标记」，**不要**学官方的「不发字段」 | **强**：官方 `messagesApi.ts:174` 的硬编码三项在今天的目录下会把 `xhigh`/`max` 静默吞掉（`messagesApi.spec.ts:793` 把这个行为当正确固化了），那是缺陷不是范式 |
| 目录未发布 effort → 不发 `reasoning` | 保持 | **强**：与 `responsesApi.ts:77` 的 `?.length` 判据完全同构 |
| `reasoning` 的键集 | 只考虑 `effort` 与 `summary`；**不要**加 `context` / `mode` | **强（负面）**：全仓零命中，`IEndpointBody.reasoning` 类型就只有这两个键（`networking.ts:78`） |
| `summary` | **待裁决**（第 7 节差异 11）。若决定发，取 `"detailed"` | 官方默认值为 `detailed`（`configurationService.ts:889` + `package.json:3782`），`auto`/`concise` 官方从不发 |
| `include` | 核对我方是否发 `['reasoning.encrypted_content']` | **强**：官方 `responsesApi.ts:88` 无条件发，且类型被写成单元素元组 |
| **budget→effort 阈值** | **无依据，维持我方策略。停止寻找官方阈值。** | **强（负面）**：官方两条路径都不做这个换算，Anthropic 侧把 budget 与 effort 并列发出（`messagesApi.ts:233-234`）。唯一可拿来做直觉校验的参照点：官方 budget 默认值 16000（`configurationService.ts:902`）——若我方把 16000 判成 `xhigh`，等于把官方的「无脑默认」放在次高档，**建议主会话重新审视这一档**，但这只是直觉校验，不是官方规则 |
| `adaptive` → `high` | 维持 | 无背书；官方给 Claude（adaptive 家族）的 UI 默认档是 `high`（`languageModelAccess.ts:69`），方向一致但语义不同 |
| `disabled` → `none` | 维持 | 无背书；官方无「关闭」概念，`none` 只是一个可被手选透传的普通档。我方的映射是自洽的新增语义 |
| Responses 侧不要引入 `min/max_thinking_budget` | 保持 | **强**：目录事实（`/responses` 模型全部不发布）+ 官方只在 Anthropic 路径使用（`messagesApi.ts:154-163`） |
| Responses 侧不要引入 adaptive | 保持 | **强（负面）**：全仓检索确认无对应物 |

---

## 附：本次检索的完整范围（用于判断「未找到」的可信度）

在 `/home/xp/src/refs/vscode-copilot-chat/` 执行，全部只读：

- `rg -l -i 'reasoning_effort|reasoningEffort' --type ts --type js` → 19 个文件，全部逐一定位
- `rg -n "\beffort\b" --type ts -g '!**/test/**' -g '!**/*.spec.ts'` → 逐条核对
- `rg -n 'adaptive|Adaptive' --type ts` → 40 处，逐条核对
- `rg -n 'min_thinking_budget|max_thinking_budget|minThinkingBudget|maxThinkingBudget|thinking_budget' --type ts`
- `rg -n 'enableThinking' --type ts`
- `rg -n 'output_config' --type ts`
- `rg -n 'current_turn|all_turns' --type ts` → **零命中**
- `rg -n "effort.*'none'|'none'.*effort" --type ts` → **零命中**
- `rg -n --no-ignore -g '*.json' -g '!node_modules' 'reasoning_effort'` → **零命中**（无目录固件）
- `rg -n 'customizeResponsesBody' --type ts` → 2 处（调用 + 基类定义，无覆盖）
- 完整阅读：`src/platform/endpoint/node/responsesApi.ts:1-180`、`src/platform/endpoint/node/messagesApi.ts:100-237`、`src/platform/endpoint/node/chatEndpoint.ts:115-345`、`src/platform/endpoint/common/endpointProvider.ts:20-120`、`src/platform/networking/common/networking.ts:60-245`、`src/extension/conversation/vscode-node/languageModelAccess.ts:40-95`、`src/extension/byok/vscode-node/anthropicProvider.ts:230-300`、`src/extension/byok/node/openAIEndpoint.ts:215-265`、`src/extension/intents/node/toolCallingLoop.ts:1400-1480`、`src/platform/endpoint/test/node/messagesApi.spec.ts:720-830`

目录事实取自我方 `tests/int/cassettes/anthropic_to_responses_stream.json` 的 interaction #1（`GET /models` 的真实响应），解析脚本为一次性 Python，未落盘、未修改任何文件。
