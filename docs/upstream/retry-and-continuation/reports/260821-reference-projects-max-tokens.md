# 参考项目如何处理 `max_tokens` / `max_output_tokens` 截断

调查日期：2026-08-21。只读调查，未修改任何被查仓库。

## 0. 调查对象与快照

| 仓库 | 路径 | 语言 | HEAD | 工作树 |
|---|---|---|---|---|
| copilot-api-js | `/home/xp/src/copilot-api-js/` | TS | `1f7bf895718729bc55ef41af947ff57988d44a90` | **脏（124 项）**，但 `git status --porcelain -- src/` 为空，`config.yaml` / `config.example.yaml` / `config.schema.json` 亦干净；本报告只引 `src/` 与这三份配置，行号对应该提交 |
| vscode-copilot-chat | `/home/xp/src/refs/vscode-copilot-chat/` | TS | `5863f5a7088958050792b5dccbe8b46c6e13eccc` | 干净 |
| caozhiyuan/copilot-api | `/home/xp/src/refs/caozhiyuan-copilot-api/` | TS (Bun) | `6b97876927b7209a1e0f498e81927b32cc443e52` | 有一个**未追踪子目录 `copilot-api/`**（内嵌的另一份同名 checkout）。本报告只引仓库根的 `src/`；`copilot-api/src/` 是未追踪副本，不代表该提交 |
| CLIProxyAPIPlus | `/home/xp/src/refs/CLIProxyAPIPlus/` | Go | `0c48ef58e0d37220367401b8f7cf689e2e50a701` | 干净 |
| hooyao/copilot-bridge | `/home/xp/src/refs/hooyao-copilot-bridge/` | C# | `b2d7cc734f8094361245ff4e3fbc15ebc8e770ff` | 干净 |
| sxwxs/ghc-api-py | `/home/xp/src/refs/ghc-api-py/` | Python | `0cb1087c389d9948af580e90019cfde069444ed1` | 干净 |
| agent-maestro | `/home/xp/src/refs/agent-maestro/` | TS | `06d6e493fd163f52ede8ad07801dc3880e23d666` | 干净 |
| awsl-maxx | `/home/xp/src/refs/awsl-maxx/` | Go | `1ec22b11c0e1253a7c444e2fb6e8b2a6cb4c41a3` | 干净 |

所有路径均存在，无缺失仓库。

一条需要先说的事实修正：**awsl-maxx 不是 GitHub Copilot 代理**。`rg -li 'copilot' /home/xp/src/refs/awsl-maxx` 在该 HEAD 下 **0 个文件命中**；`internal/adapter/provider/` 下的 provider 目录是 antigravity / bedrock / claude / cliproxyapi_* / codex / custom / grok / kiro / newapi / ollama / openrouter，没有 copilot。它是 Codex/Claude/Grok 等上游的代理。下文仍按要求列出它的截断处理，但它的做法对本项目的参考权重应按「同类协议翻译器」而非「同类 Copilot 代理」看待。

---

## 1. copilot-api-js（本项目前身）

### 1.1 四问速览

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | 有，且三种 wire 各有专用谓词，集中在 `src/lib/pipeline/max-tokens-truncation-class.ts`。但**只有 Anthropic 那条被接线**：`stopReason === "max_tokens"` |
| 2. 识别之后 | **(a) 原样透传** + 记一条诊断（`recordMaxTokensTruncation`）。P0 明确 observation-only，不改任何客户端可见帧 |
| 3. 截断的 item / block | 不额外处理。截断的 tool_use 半截 JSON 走**与截断无关**的通用 `repairToolInput` 级联修复（`jsonrepair` 能补上缺失的 `]}`），修不好则标 `unrepairable` 并按原样转发的既有策略走 |
| 4. 是否可重试 | **否**。仓里确有一套完整的 continuation 机制，但它挂在**错误截断**（mid-stream throw / 传输中断）路径上，不由 `max_tokens` 触发。`max_tokens_continuation` 配置存在但 `enabled` 默认 false，且没有任何 src 消费者 |

### 1.2 判据（逐字）

`src/lib/pipeline/max-tokens-truncation-class.ts:31-41`：

```ts
export function isAnthropicMaxTokensTerminal(stopReason: string): boolean {
  return stopReason === "max_tokens"
}

export function isCcMaxTokensTerminal(finishReason: string): boolean {
  return finishReason === "length"
}

export function isResponsesMaxTokensTerminal(status: string, incompleteReason: string | undefined): boolean {
  return status === "incomplete" && incompleteReason === "max_output_tokens"
}
```

**接线现状（判据性 grep）**：`rg -n 'isResponsesMaxTokensTerminal|isCcMaxTokensTerminal' src` 只命中这两行定义本身，**src 内零调用点**（调用只在 `tests/pipeline/max-tokens-truncation-class.unit.test.ts`）。也就是说：Responses / Chat Completions 上游的 `max_output_tokens` / `length` 终局在本仓**没有被观测**，只有 Anthropic-direct 腿被观测。

### 1.3 分型器与观测器

`src/lib/pipeline/max-tokens-truncation-class.ts:11-29` 把终局分成四类：

```ts
export type TruncationClass = "text" | "tool_use" | "tool_use_closed" | "thinking"
...
    case "tool_use": {
      return observer.lastBlockClosed ? "tool_use_closed" : "tool_use"
    }
```

分型的数据来自一个独立观测器 `src/lib/pipeline/max-tokens-terminal-observer.ts`，它从**已渲染的 Anthropic 帧**上跟踪「最后一个打开的块是什么类型、有没有闭合」。这个模块的注释解释了为什么不复用 continuation ledger（`max-tokens-terminal-observer.ts:3-9`）：

> This is intentionally independent of the continuation ledger: the ledger preserves only closed, replayable blocks and therefore cannot distinguish partial text, an open tool call, or thinking that followed an earlier committed text block.

以及一处容易漏的细节（`:43-46`）：`content_block_stop` 只有在 `frame.index` 等于最后打开块的 index 时才置 `lastBlockClosed`——「A delayed stop for an older block must not make a newer last block appear closed.」

### 1.4 识别之后做什么（实现）

唯一的消费点在 `src/routes/messages/handler-v4.ts:2182-2198`：

```ts
      if (isAnthropicMaxTokensTerminal(acc.stopReason)) {
        const truncationClass = classifyMaxTokensTruncation(terminalObserver)
        if (truncationClass !== undefined) {
          // P0 is observation-only: record the actual upstream terminal before ctx.complete freezes
          // the history entry, without suppressing or rewriting any client-visible frame.
          env.ctx.recordMaxTokensTruncation({
            truncationClass,
            roundsAttempted: 1,
            roundsSucceeded: 0,
            continuedTokens: 0,
            perRoundStopReason: [acc.stopReason],
            clientVisibleStopReason: acc.stopReason,
            suppressedMaxTokens: false,
            visibilityMode: "passthrough",
          })
        }
      }
      env.ctx.complete(buildAnthropicResponseData(acc, model))
```

观测器的喂养在同文件 `:318-330`（`onRenderedFrame` 钩子，解析已渲染帧的 JSON）。诊断出口是 telemetry 维度 `src/lib/observability/telemetry-dimensions.ts:154`：

```ts
  max_tokens_truncation: (entry) => entry.pipelineInfo?.maxTokensContinuation?.truncationClass ?? null,
```

**所以：实现 = 原样透传 + 打一个可观测标签。没有续写、没有改写 stop_reason、没有丢弃内容。**

### 1.5 跨协议的 stop_reason 映射（纯透传保真）

这部分是「翻译」而非「处理截断」，但它决定了截断信号能不能活着到客户端：

- `src/lib/translation/from-ir/anthropic/stop-reason.ts:34-40`：
  ```ts
  const TRUNCATION_REASONS: ReadonlySet<string> = new Set(["max_output_tokens", "max_tokens"])

  export function anthropicStopReason(terminalKind, incompleteReason, sawToolUse): StopReason {
    // Matched explicitly rather than by negating `content_filter`: a future reason nobody has mapped yet
    // must fall to `end_turn`, not silently inherit `max_tokens`.
    if (terminalKind === "incomplete") return incompleteReason !== undefined && TRUNCATION_REASONS.has(incompleteReason) ? "max_tokens" : "end_turn"
    return sawToolUse ? "tool_use" : "end_turn"
  }
  ```
  同文件 `:29-32` 的注释指出为什么两个拼写都收：「a Responses source says `max_output_tokens` and an Anthropic source says `max_tokens` … Recognising only one silently downgrades the other to `end_turn`, which tells the client the model chose to stop when it was actually cut off.」

- 反向 `src/lib/translation/from-ir/openai-responses/status.ts:46-47`：`max_tokens` → `{ status: "incomplete", incompleteReason: "max_output_tokens" }`。
- legacy-direct 三条腿同构：`legacy-direct/anthropic-to-cc.ts:172-173`（`max_tokens`→`length`）、`legacy-direct/cc-to-anthropic-stream.ts:111`（`length`→`max_tokens`）、`legacy-direct/responses-to-anthropic.ts:324`（`status === "incomplete" && incompleteDetails?.reason === "max_output_tokens"` → `max_tokens`）。

### 1.6 截断的 tool call 怎么办

没有「因为 max_tokens 所以特别处理」这一层。半截 JSON 走的是通用修复模块 `src/lib/anthropic/tool-input-repair.ts`，四层级联（`REPAIR_ITEMS = ["tags", "unicode", "jsonrepair", "unicode-lossy"]`，`:256`）。其中 `jsonrepair` 层的文档字符串（`:218-224`）明说它覆盖结构性截断：

> Runs `jsonrepair` (which completes missing brackets/quotes, fixes trailing commas, etc.) over input that survived Layer 1 still malformed — e.g. **a structurally truncated tool arg missing its closing `]}`**.

有两道防止「修出假成功」的闸：`isPlausibleToolInput`（`:290-292`，结果必须是 JSON 对象，拒 `jsonrepair("not json")` → 裸字符串这类捏造）和 `tryJsonRepair` 的 re-parse gate（`:232-240`）。修不好返回 `{ unrepairable: true }`，由调用方决定原样转发还是失败。

需要注意：这个修复是**面向转发轨**的，History 保留上游原始字节（`:1-10` 头注释）。

### 1.7 「文档声称」与「实现」的差距（本节是本项目最该读的部分）

仓里有一份 356 行的完整 spec：`docs/spec/2026-07-22-max-tokens-continuation.md`，状态自述为「草案（两轮异模型对抗审查已消化、Q1/Q2 用户已裁决 2026-07-23、续写底座已 landed master 已对齐——可进 plan 阶段）」。它规定了一整套东西，其中**只有 P0 观测那一小块落进了 `src/`**。

spec 的实证画像（§1.1，来自 4141 History API 近 1200 条中的 5 例 `max_tokens`，占比约 0.4%，全部 `claude-sonnet-5` 流式、干净收尾、`output_tokens` 精确撞客户端自设的 32000 而非模型 cap 64000）把截断分成三型：

| 型 | 截断在 | 终止 wire 形状 | 悬挂开块 | spec 的裁决 |
|---|---|---|---|---|
| A | text | `start@0 stop@0 start@1 stop@1 MΔ STOP` | 否 | 唯一适合 proxy 续写的子集，可默认 opt-in |
| B | tool_use input JSON | `start@0 stop@0 start@1 MΔ STOP` | **是**（`start@1` 无 `stop@1`） | 高危，默认透传，PoC 门后再评估 |
| C | thinking（0 可见答案） | `start@0 stop@0 MΔ STOP` | 否 | 最贵最不可靠；默认透传，或 opt-in「抬预算重发」而非续写 |

spec 对 B 类不自动续写给出的理由（§3.2），是本项目直接可用的判断：

> **重生成 ≠ 续写**：合成轮里模型从**已 commit 的前缀**（此例是前面的 text 块 + 一个被丢弃的半截工具意图）**从头重规划**这个工具调用——极可能吐出**不同的 tool / 不同的 input**，而非「接着写原来那半个 JSON」。

以及一条已经验证过、容易被误引的区分（§3.2 第 3 点）：PoC 门 G3 已 PASS，证明的是「**完整未截断**的 tool_use 块作 assistant 前缀会被 GHC 接受、不 400」，**不等于** B 类场景成立——B 类的 partial tool_use 是被丢弃的，前缀退化成它之前的已闭合块。

spec 还固化了一条与 thinking 有关的架构约束（§3.3 + ADR D3）：extractor 把 thinking 块排除在 ledger 之外、上游拒 thinking 作前缀，**所以 thinking 续写在现架构下不可实现**，C 类只有 `passthrough` 和 `retry_with_budget` 两个选项，没有 `continue`。

用户在 2026-07-23 对可见性做了裁决（§4）：默认 `transparent`——续到自然终止就**抑制**首轮的 `message_delta{stop_reason:max_tokens}` + `message_stop`，客户端看到一条完整流；续不动了才如实透传。理由是该项目下「下游预算约束当前并不被客户端强制遵守」，用户明确不在乎双重计费。但同时钉死一条：**透明只对客户端，后端 history/telemetry/日志必须忠实完整记录**真实轮数、每轮请求（含合成轮，打 `synthetic:"continuation"` 标记）、每轮 usage。

配置面已经全部铺好但未通电：`config.example.yaml:235-259` 给出完整键位（`enabled` / `max_rounds` / `classes.{text,tool_use,thinking}` / `message` / `visibility` / `thinking_retry_budget`，含 per-vendor 覆盖），`config.yaml:423-424` 的中文注释写着「max_tokens 终局续传独立 opt-in。P0 只观察并记录真实终局；enabled=false 时绝不改变客户端 wire」。`src/lib/config/model-overrides.ts:63-89` 有 `resolveMaxTokensContinuation` / `resolveEffectiveMaxTokensContinuation`（后者还带一条一致性闸：`visibility === "passthrough"` 与任何 `continue` 类目互斥，因为 passthrough 已终止流、无法缝合）。**判据性 grep**：`rg -n 'resolveEffectiveMaxTokensContinuation' src tests` 的 src 侧只有定义那一行，消费者全在 tests。

### 1.8 另一套 continuation：错误截断路径（不要与 max_tokens 混淆）

`src/lib/pipeline/driver.ts` 里确实有一套跑起来的续写，但触发条件是**mid-stream 失败且已有块提交**，不是 `max_tokens`。要点：

- 请求组装形状（`src/lib/anthropic/continuation-builder.ts:48-53`）：`[original body 不变] + {role: assistant, content: [committed blocks]} + {role: user, content: <配置的续写消息>}`，`stream: true`。头注释说明为什么不用 assistant PREFILL：「The upstream rejects assistant PREFILL ("must end with a user message")」，PoC 在 haiku + opus-4.8 上验证过。
- 默认续写提示语：`config.example.yaml` 的 max_tokens 段给的是 `"Please continue where you left off."`（该段仍是注释态）。
- ledger 只收**已闭合、已落 wire** 的块，`thinking` 被排除（ADR D3）。
- 有一道 gate：`hasCompleteInteractiveToolUse`——前缀里已有**完整的、客户端可交互的** tool_use 块时**不续写**，因为那是合法的回合边界（客户端该去跑工具）。
- Responses 腿的 builder（`src/lib/openai/responses-continuation-builder.ts:28-42`）把 canonical block 投影成 `input[]`，tool_use → `function_call` 且 `arguments` 必须**重新字符串化**（ledger 存的是解析后的值，或解析失败时的原始串）。它还有一条与本项目直接相关的经验：`remapResponsesOutputIndex`（`:100-105`）——续写腿的上游会**从 0 重新计 output item**，不偏移会与已交付的 item 撞号；而且**只能改 `output_index`**，`sequence_number` 归 emitter 自己、`content_index` 是 item 内作用域。
- 预算：`driver.ts:2068-2070`，family 预算与 shared upstream 预算取 min，首轮有一个「至少 1」的地板。失败分两种终局：`continuation-exhausted`（续写试过但用尽预算）vs `partial-degrade`（续写从未触发），`driver.ts:2151-2157`。
- builder 注册表按 **wire format** 而非 client format 键控（`responses-continuation-builder.ts:7-13`）：「A Responses client pinned to `@messages` reaches an Anthropic upstream, and that leg must use the ANTHROPIC builder even though the client format is `openai-responses`.」

---

## 2. vscode-copilot-chat（官方实现）

### 2.1 四问速览

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | **分路径**。Chat Completions 路径有：`FinishedCompletionReason.Length`（枚举值 `'length'`）。**Responses 路径没有**：`rg 'response\.incomplete\|incomplete_details' src test` **全仓 0 命中** |
| 2. 识别之后 | 组合：多数消费者把 Length 当**错误**（(c) 改写成错误终局，向用户报「hit the length limit」）；**codeMapper 是唯一做续写的**，把 `truncatedValue` 塞回 prompt 重发 |
| 3. 截断的 tool call | **(d) 丢弃**。工具调用只在 `finish_reason` 为 `tool_calls` 或 `stop` 时才 emit；`length` 不在其中，半截工具调用不会被交付 |
| 4. 是否可重试 | codeMapper 有一个 `while (true)` 续写循环，**不按轮数封顶，按累计长度封顶**；无退避。其余路径不重试 |

### 2.2 判据（逐字）

`src/platform/chat/common/commonTypes.ts:101`：

```ts
	Length = 'length',
```

（`FinishedCompletionReason` 枚举；另一份同名枚举在 `src/platform/nesFetch/common/completionsAPI.ts:47`。）

转成对外结果类型在 `src/extension/prompt/node/chatMLFetcher.ts:1765-1772`：

```ts
			case FinishedCompletionReason.Length:
				return {
					type: ChatFetchResponseType.Length,
					reason: 'Response too long.',
					requestId: requestId,
					serverRequestId: result.requestId.headerRequestId,
					truncatedValue: getTextPart(result.message.content)
				};
```

注意 `truncatedValue` —— 被截断的文本**被保留下来**，这是后面能续写的前提。

### 2.3 Responses 路径根本没接这条线

`src/platform/endpoint/node/responsesApi.ts` 的事件 switch（`rg -n "case '" …`）只有这些 case：`error` / `response.output_text.delta` / `response.output_item.added` / `response.function_call_arguments.delta` / `response.output_item.done` / `response.reasoning_summary_text.delta` / `response.reasoning_summary_part.done` / `response.completed`。**没有 `response.incomplete`**。而 `response.completed` 分支硬编码（`:613`）：

```ts
					finishReason: FinishedCompletionReason.Stop,
```

判据性 grep：`rg -n 'response\.incomplete|incomplete_details' src test` → **0 命中**（4282 文件已搜）。`max_output_tokens` 在该仓的 27 个命中全部是**请求侧**（`responsesApi.ts:50` `max_output_tokens: options.postOptions.max_tokens`）或模型能力元数据，没有一处是读取响应侧的截断信号。

结论：官方客户端在 Responses 上游下**不识别** `max_output_tokens` 截断。

### 2.4 识别之后：三种下游行为

1. **报错**（最常见）。`src/extension/prompt/node/defaultIntentRequestHandler.ts:555-561`：Length 与 `Unknown` / `NotFound` 走同一形状——取 outage status、生成 errorDetails、`turn.setResponse(TurnStatus.Error, …)`。用户看到的文案在 `src/platform/chat/common/commonTypes.ts:369-370`：

   ```ts
   		case ChatFetchResponseType.Length:
   			details = { message: l10n.t(`Sorry, the response hit the length limit. Please rephrase your prompt.`) };
   ```

2. **当成「无下一次编辑」**。`src/extension/xtab/node/xtabProvider.ts:1490`：Length 与 OffTopic / Filtered / RateLimited 等一起归入 `NoNextEditReason.Uncategorized`。

3. **续写（唯一一处）**。`src/extension/prompts/node/codeMapper/codeMapper.ts:686` 开一个 `while (true)`，`:706-722`：

   ```ts
   			if (result.type === ChatFetchResponseType.Length) {
   				if (responseLength > maxLength) {
   					… return { result, …, annotations: [{ label: 'codemapper loop', message: `Code mapper might be in a loop: …`, severity: 'error' }] };
   				}

   				const promptRenderer = PromptRenderer.create(
   					this.instantiationService,
   					endpoint,
   					CodeMapperFullRewritePrompt,
   					{ request, shouldTrimCodeBlocks: true, inProgressRewriteContent: result.truncatedValue } satisfies CodeMapperPromptProps
   				);
   				const response = await promptRenderer.render(undefined, token);
   				promptMessages = response.messages;
   			}
   ```

   续写不是「追加一条 user 轮说 continue」，而是**重渲染整个 prompt**，把已产出的部分作为一个具名 prompt 变量 `inProgressRewriteContent` 传进去。上限是 `maxLength = documentLength + request.codeBlock.length + 1000`（`:670`，注释 `// add 1000 to be safe`）——**按累计输出长度而非轮数封顶**，超了就当作「模型进入了循环」并带 severity=error 的 annotation 返回。无退避。

### 2.5 截断的 tool call 被静默丢弃

`src/platform/networking/node/stream.ts:543`：

```ts
					if ((choice.finish_reason === FinishedCompletionReason.ToolCalls || choice.finish_reason === FinishedCompletionReason.Stop) && this.toolCalls.hasToolCalls()) {
```

同样地 `:520` 的 legacy function_call 分支条件是 `FunctionCall || Stop`。两处都**不含 `Length`**。所以 `finish_reason: "length"` 到达时，累积在 `this.toolCalls` 里的半截工具调用**既不会被 emit、也不会被修复或报告**——它就消失了，只留下一个 Length 类型的结果。这是「丢弃截断段」的一个实例，而且是隐式的（没有任何代码注释说明这是有意为之）。

---

## 3. caozhiyuan/copilot-api

> 提醒：仓库根有一个未追踪的 `copilot-api/` 子目录（内嵌副本）。以下全部引用仓库根 `src/`，即该 HEAD 的追踪内容。

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | 有，两套：Responses 侧 `status === "incomplete" && incomplete_details.reason === "max_output_tokens"`；Chat Completions 侧 `finish_reason === "length"` |
| 2. 识别之后 | **(a) 纯透传**，映射成 Anthropic `stop_reason: "max_tokens"` |
| 3. 截断的 tool call | 原样发给客户端。`handleResponseCompleted` 先 `closeAllOpenBlocks` 补上 `content_block_stop`，半截 `partial_json` 早已随 delta 发出，不做修复也不丢弃 |
| 4. 是否可重试 | **否**。`rg -ln 'retry\|Retry' src` 只命中 `src/lib/error.ts` 与 `src/lib/token.ts`（HTTP/鉴权层），与截断无关 |

非流式（`src/routes/messages/responses-translation.ts:699-721`）：

```ts
const mapResponsesStopReason = (
  response: ResponsesResult,
): AnthropicResponse["stop_reason"] => {
  const { status, incomplete_details: incompleteDetails } = response
  ...
  if (status === "incomplete") {
    if (incompleteDetails?.reason === "max_output_tokens") {
      return "max_tokens"
    }
    if (incompleteDetails?.reason === "content_filter") {
      return "end_turn"
    }
  }

  return null
}
```

流式（`src/routes/messages/responses-stream-translation.ts:129-132`）把 `response.incomplete` 与 `response.completed` **合并到同一个 handler**：

```ts
    case "response.completed":
    case "response.incomplete": {
      return handleResponseCompleted(rawEvent, state)
    }
```

`handleResponseCompleted`（`:460-482`）先 `closeAllOpenBlocks(state, events)`，再复用非流式的 `translateResponsesResultToAnthropic(response)` 取 stop_reason / usage，最后发 `message_delta` + `message_stop`。

CC 侧映射在 `src/routes/messages/utils.ts:9-15`，一张直白的表：`stop→end_turn, length→max_tokens, tool_calls→tool_use, content_filter→end_turn`。

有一处请求侧的行为值得记：`src/routes/messages/responses-translation.ts:81` 把客户端预算抬高到下限 12800：

```ts
    max_output_tokens: Math.max(payload.max_tokens, 12800),
```

这是「用抬预算预防截断」，不是「截断后处理」，但它是这批项目里唯一一处**主动改写客户端预算**的做法，值得在本项目讨论 `retry_with_budget` 时对照。

---

## 4. CLIProxyAPIPlus

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | **部分**。有 `finish_reason == "length"` ⇄ `max_tokens` 的双向映射；但对 Responses 的 `incomplete_details` **只写不读** |
| 2. 识别之后 | **(a) 纯格式映射透传**；在「输出 Responses 格式」的方向上则是 **(c)+(d)：硬编码成 `completed` / `incomplete_details: null`**，截断信号被抹掉 |
| 3. 截断的 tool call | 未见任何专门处理；判据性 grep 见下 |
| 4. 是否可重试 | **否**。`internal/runtime/executor/github_copilot_executor.go` 里 `rg -n 'max_output_tokens\|incomplete\|length\|retry\|Retry'` 只命中一行无关注释（`:1658` 讲模型 context length）。仓内 "continuation" 的 5 处命中（`:622/626/636/638/670`）指的是**请求侧**「这轮是不是 tool-loop 的延续」的计费分类，与输出截断无关 |

映射（逐字）：

`internal/translator/openai/claude/openai_claude_response.go:460-466`：
```go
func mapOpenAIFinishReasonToAnthropic(openAIReason string) string {
	switch openAIReason {
	case "stop":
		return "end_turn"
	case "length":
		return "max_tokens"
```

`internal/translator/claude/openai/chat-completions/claude_openai_response.go:254-262`：
```go
func mapAnthropicStopReasonToOpenAI(anthropicReason string) string {
	...
	case "max_tokens":
		return "length"
```

信号丢失点——三个「生成 Responses 输出」的 translator 都从一个硬编码模板起手：

- `internal/translator/claude/openai/responses/claude_openai-responses_response.go:459`
- `internal/translator/openai/openai/responses/openai_openai-responses_response.go:627`
- `internal/translator/gemini/openai/responses/gemini_openai-responses_response.go:577`

```go
	out := []byte(`{"id":"","object":"response","created_at":0,"status":"completed","background":false,"error":null,"incomplete_details":null,"output":[],...}`)
```

判据性 grep：`rg -n 'incomplete_details' internal/translator/.../{claude,openai,gemini}_openai-responses_response.go` 在这三份文件里**各只有这一行**——即这些 translator 从不给 `incomplete_details` 赋别的值，也从不读它。所以以 Responses 格式对下游供给时，`max_tokens` 截断被降级成 `completed`。

---

## 5. hooyao/copilot-bridge

这是除 copilot-api-js 外唯一在**截断相邻问题**上有成体系工程的项目。

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | 有：SSE 事件类型 `== "response.incomplete"`，或 `response.status == "incomplete"`。**不读 `incomplete_details.reason`** |
| 2. 识别之后 | **(a) 透传**，映射成 Anthropic `stop_reason: "max_tokens"`；并在关闭未闭合块时**拒绝伪造完成态** |
| 3. 截断的 tool call | 有专门的 `ToolInputValidationDetector`：在 `content_block_stop` 校验累积的 tool 输入 JSON（+ schema 子集校验）。**默认 observe-only：记诊断、原样转发**；opt-in `Abort*` 才注入错误事件并终止流 |
| 4. 是否可重试 | **否（对截断）**。重试只针对 HTTP 传输层瞬时错误（`Hosting/Options/UpstreamRetryOptions.cs` + `Copilot/TransientUpstreamError.cs`）。判据性 grep：`rg -i 'retry' --glob '*.cs' src/CopilotBridge.Cli/Pipeline \| rg -i 'max_tokens\|length\|incomplete\|truncat'` 只命中一行注释（见下） |

判据（`src/CopilotBridge.Cli/Pipeline/Strategies/Codex/ResponsesToAnthropicStream.cs:635-644`）：

```csharp
    private static string StopReasonFor(string? eventType, JsonElement root)
    {
        if (eventType == "response.incomplete") return "max_tokens";
        // response.completed: peek at response.status / output for tool calls.
        if (root.TryGetProperty("response", out var r)
            && r.TryGetProperty("status", out var s)
            && s.GetString() == "incomplete")
            return "max_tokens";
        return "end_turn";
    }
```

**这是一个保真缺口**：`incomplete_details.reason == "content_filter"` 的 incomplete 也会被报成 `max_tokens`。对照 copilot-api-js `stop-reason.ts:37-39` 的显式匹配注释（「a future reason nobody has mapped yet must fall to `end_turn`, not silently inherit `max_tokens`」），hooyao 走的是相反的默认。

优先级规则（`:342-352`）——已经因 function_call item 打开而锁定的 `tool_use` 只被 `max_tokens` 覆盖：

```csharp
                case "response.completed":
                case "response.incomplete":
                    _sawUpstreamTerminal = true;
                    CaptureUsage(root);
                    // Don't clobber a tool_use stop already latched when a
                    // function_call item opened — only a max_tokens/incomplete
                    // signal overrides it; otherwise keep what we have.
                    var completedStop = StopReasonFor(type, root);
                    if (_stopReason != "tool_use" || completedStop == "max_tokens")
                        _stopReason = completedStop;
                    foreach (var s in Flush()) yield return s;
```

`Flush()`（`:660-`）先补 `content_block_stop` 再发 `message_delta` + `message_stop`。

反方向（Anthropic → Responses）`src/CopilotBridge.Cli/Pipeline/Adapters/Codex/IrToResponsesOutboundAdapter.cs:1036`：

```csharp
    private string MapStatus() => _stopReason == "max_tokens" ? "incomplete" : "completed";
```

同文件 `:860-870` 有一段**直接适用于本项目**的原则性判断，讲的是「截断时关掉一个未闭合的 web_search 块」该怎么办：

> marker ABSENT → the search block was closed WITHOUT a completed item (T3.Flush closing an open block on `response.incomplete`: an interrupted search). Do NOT fabricate `.completed` + an output_item.done that claims status:"completed"/"in_progress" as done — that would tell Codex a search finished that did not. Emit output_item.done with the item in its ACTUAL (in-progress) state and NO `.completed` event. … an honest interrupted item is safe; a fabricated completion is not.

### 截断的 tool call：`ToolInputValidationDetector`

类文档（`src/CopilotBridge.Cli/Pipeline/Response/Detection/ToolInputValidationDetector.cs:16-38`）解释了为什么默认不 abort——这条经验对本项目的价值很高：

> **Observe-by-default.** Claude Code recovers from an invalid tool call natively: it parses the accumulated input with `safeParseJSON` (malformed JSON falls back to `{}`), runs the tool's `zod strictObject.safeParse`, and on failure feeds the model an `is_error` tool_result so it retries with corrected input. Aborting the response was found to cut off exactly that recovery (e.g. a real `AskUserQuestion` emitted without the required `question` field — CC would have re-prompted the model, but a mid-stream abort surfaced "Server error mid-response" instead). So the detector records the diagnosis (`tool_input_invalid=` on the summary) but relays the response unchanged unless a class is explicitly set to an `Abort*` action.

以及 abort 时机的选择理由（`:29-38`）：在 `content_block_stop` 处 abort，因为「a content block is only pushed onto the message list at `content_block_stop`」——这样坏块永远不会进客户端的会话上下文。

校验逻辑本身在 `:325-343`：`JsonDocument.Parse(raw.Length == 0 ? "{}" : raw)` 失败 → `Flag(_opts.MalformedJsonAction, …, "malformed JSON: " + ex.Message)`；成功则再跑 `JsonSchemaSubsetValidator`。自定义 grammar 工具（输入是自由文本而非 JSON）显式跳过（`:319-323`）。

另一条注释（`:265-272`）记录了一个观测陷阱：某个 delta 帧解析失败被跳过累积后，重组出的输入必然「malformed JSON」，所以要 trace，「so a spurious abort can be attributed to a dropped frame, not the model」。

`ResponseInspectionStage.cs:288-294` 记了一条客户端侧的实测行为：

> Claude Code treats the injected `overloaded_error` as retryable, but note: once visible output has already streamed, recent Claude Code versions may preserve the partial response and show an incomplete-response notice instead of retrying the whole turn.

---

## 6. sxwxs/ghc-api-py

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | 有，且最严格：`status == "incomplete"` 或终止事件是 `response.incomplete`，再看 `incomplete_details.reason == "max_output_tokens"`；CC 侧 `finish_reason == "length"` |
| 2. 识别之后 | **(a) 透传**，映射成 `max_tokens`。**未知的 incomplete reason 直接抛异常**（fail-closed，不猜） |
| 3. 截断的 tool call | **(d) 拒绝整个转换**。`function_call.arguments` 必须是严格 JSON 且解码成对象，否则抛 `AnthropicResponsesConversionError`——半截 JSON 让整条响应转换失败，而不是发一个坏 tool_use 给客户端 |
| 4. 是否可重试 | **否**。判据性 grep：`rg -n -i 'retry' ghc_api/*.py \| rg -i 'length\|max_tokens\|incomplete\|truncat'` → 0 命中 |

判据（`ghc_api/anthropic_responses.py:1914-1942`）：

```python
    incomplete_value = response.get("incomplete_details")
    incomplete = incomplete_value if isinstance(incomplete_value, dict) else {}
    is_incomplete = (
        response.get("status") == "incomplete"
        or terminal_event_type == "response.incomplete"
    )
    incomplete_stop_reason: Optional[str] = None
    if is_incomplete:
        incomplete_reason = incomplete.get("reason")
        if incomplete_reason == "max_output_tokens":
            incomplete_stop_reason = "max_tokens"
        elif incomplete_reason in ("content_filter", "safety", "policy"):
            incomplete_stop_reason = "refusal"
        else:
            ...
            raise AnthropicResponsesConversionError(
                "Responses incomplete reason is not safely representable",
                report,
            )
```

优先级（`:1943-1948`）：`stop_sequence` > incomplete 类 > `tool_use` > …。注意它把 `content_filter` 映射成 `refusal`，与 copilot-api-js（映射成 `end_turn` 并另打 `contentFiltered` 旁路标记，见 `stop-reason.ts:16-19`）**裁决不同**。

工具参数 fail-closed（`ghc_api/anthropic_responses.py:1669-1699`）：

```python
    Sending a scalar, array, malformed JSON, or an object with duplicate keys
    as an Anthropic ``tool_use.input`` can make the CLI execute a call with a
    different contract.  This is therefore a fail-closed boundary in both
    compatibility modes, not a best-effort projection.
    """

    try:
        if not isinstance(raw_arguments, str):
            raise StrictJSONError("Function arguments must be a JSON string")
        parsed = parse_strict_json_bytes(raw_arguments.encode("utf-8", errors="strict"))
        if not isinstance(parsed, dict):
            raise StrictJSONError("Function arguments must decode to a JSON object")
    except (StrictJSONError, UnicodeEncodeError) as exc:
        ...
        raise AnthropicResponsesConversionError(
            "Responses function arguments are not a strict JSON object",
            report,
        ) from exc
```

调用点在 `:1852`（非流式 `convert_responses_to_anthropic` 的输出 item 循环）。**范围限定**：`rg -n '_strict_function_arguments' ghc_api/*.py` 只有定义（`:1669`）与这一处调用（`:1852`），SSE 流式路径未走这条闸。仓内另有 `ghc_api/tool_call_recovery.py`（`LeakedToolCallTransformer`），但那是修「文本里漏出 antml 工具标签」的，与截断无关。

CC 侧映射（`ghc_api/translator.py:233-239`）：`{"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use", "content_filter": "refusal"}`。

---

## 7. agent-maestro

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | **无**。该项目未处理 |
| 2. 识别之后 | 不适用；对外一律报 `incomplete_details: null` / `finish_reason: "stop"` |
| 3. 截断的 tool call | 未处理 |
| 4. 是否可重试 | 否 |

判据性 grep 与零命中证据：

- `rg -n 'incomplete_details' src/server/routes/openai/openaiResponsesRoutes.ts` → 三处命中，**全部是硬编码 `incomplete_details: null`**（`:455` / `:488` / `:854`）。
- `rg -n 'finish_reason' src/server/routes/openai/openaiChatRoutes.ts` → 六处命中，取值只有 `null`（流式中途，`:305/:344/:374`）与 `toolCalls.length > 0 ? "tool_calls" : "stop"`（`:268` / `:418`）。**`"length"` 从不出现在赋值位置。**
- schema 里定义了这个字段（`src/server/schemas/openai.ts:622-624`，`reason: z.enum(["max_output_tokens", "content_filter"]).optional()`），但只用于校验，无产出路径。

成因是架构性的：agent-maestro 是把 **VS Code Language Model API** 包成 OpenAI 端点，`max_output_tokens` 在 `openaiResponsesRoutes.ts:198-202` 被改名成 `maxTokens` 交给 VS Code LM；LM API 不回传 finish reason，代理端因此无从识别截断。

---

## 8. awsl-maxx

**先记事实**：该 HEAD 下 `rg -li 'copilot'` 全仓 0 文件命中，它不是 GitHub Copilot 代理（provider 列表：antigravity / bedrock / claude / cliproxyapi_* / codex / custom / grok / kiro / newapi / ollama / openrouter）。以下按要求仍列出其截断处理。

| 问题 | 答案 |
|---|---|
| 1. 识别判据 | 有：`status == "incomplete"` 时读 `incomplete_details.reason`，`"max_output_tokens"` 或 `"max_tokens"` 都收 |
| 2. 识别之后 | **(a) 透传**，映射成 OpenAI `finish_reason: "length"`（同时写 `native_finish_reason`）。反方向（生成 Responses）与 CLIProxyAPIPlus 一样硬编码 `incomplete_details: null` |
| 3. 截断的 tool call | 未见专门处理 |
| 4. 是否可重试 | 未见按截断重试。`rg -i 'finishReason\|finish_reason' internal/executor internal/handler \| rg -i 'retry'` → 0 命中 |

`internal/converter/codex_to_openai.go:475-490`：

```go
	if statusResult := response.Get("status"); statusResult.Exists() {
		finishReason := ""
		switch statusResult.String() {
		case "completed":
			finishReason = "stop"
			if strings.Contains(template, `"tool_calls":[`) {
				finishReason = "tool_calls"
			}
		case "incomplete":
			finishReason = codexIncompleteReasonToOpenAI(response.Get("incomplete_details.reason").String())
		}
```

`:654-663`：

```go
func codexIncompleteReasonToOpenAI(reason string) string {
	switch reason {
	case "max_output_tokens", "max_tokens":
		return "length"
	case "content_filter":
		return "content_filter"
	default:
		return "stop"
	}
}
```

注意 `default → "stop"`：未知 incomplete 原因被降级成正常结束（与 copilot-api-js 的 `end_turn` 兜底同族，与 ghc-api-py 的抛异常相反）。

信号丢失点 `internal/converter/openai_to_codex.go:266`：生成 Responses 输出时同样从 `"status":"completed" … "incomplete_details":null` 的硬编码模板起手。

---

## 9. 跨项目对比

| 项目 | 识别判据 | 处理方式 | 截断的 tool call | 是否重试 |
|---|---|---|---|---|
| copilot-api-js | `stopReason === "max_tokens"`（**仅 Anthropic 腿接线**；CC/Responses 谓词已写但零调用点） | (a) 透传 + 记 `truncationClass` 诊断（P0 observation-only） | 无专门处理；走通用 `jsonrepair` 四层级联，修不好标 `unrepairable` | 否（continuation 机制存在但只挂错误截断路径；`max_tokens_continuation` 默认 false 且无 src 消费者） |
| vscode-copilot-chat | CC: `FinishedCompletionReason.Length`；**Responses 路径 0 命中** | 多数消费者 (c) 转成错误「hit the length limit」；codeMapper 做 (b) 续写 | **(d) 静默丢弃**：emit 条件是 `ToolCalls \|\| Stop`，不含 `Length` | codeMapper `while(true)`，按累计长度封顶（`documentLength + codeBlock.length + 1000`），无轮数上限、无退避 |
| caozhiyuan/copilot-api | `status === "incomplete" && incomplete_details.reason === "max_output_tokens"`；CC `finish_reason === "length"` | (a) 纯透传 → `max_tokens` | 原样发；仅补 `content_block_stop` | 否 |
| CLIProxyAPIPlus | 只有 `finish_reason == "length"` ⇄ `max_tokens`；`incomplete_details` 只写不读 | (a) 映射透传；输出 Responses 时 (c)+(d) 硬编码 `completed` / `null`，信号丢失 | 未处理 | 否 |
| hooyao/copilot-bridge | 事件类型 `response.incomplete` 或 `status == "incomplete"`（**不读 reason**，content_filter 会被误报 max_tokens） | (a) 透传 → `max_tokens`；关闭未闭合块时拒绝伪造完成态 | `ToolInputValidationDetector` 在 `content_block_stop` 校验 JSON + schema；**默认 observe-only 原样转发**，opt-in 才 abort | 否（重试仅限 HTTP 瞬时错误） |
| sxwxs/ghc-api-py | `status == "incomplete"` 或 `response.incomplete` + `reason == "max_output_tokens"`；未知 reason **抛异常** | (a) 透传 → `max_tokens`（`content_filter` → `refusal`） | **(d) 整条转换失败**：arguments 必须严格 JSON 对象，否则抛错（仅非流式路径） | 否 |
| agent-maestro | **无**（`incomplete_details` 恒 `null`，`finish_reason` 只有 `stop`/`tool_calls`） | 不适用 | 未处理 | 否 |
| awsl-maxx（非 Copilot 代理） | `incomplete_details.reason ∈ {max_output_tokens, max_tokens}` → `length`，未知 → `stop` | (a) 透传；输出 Responses 时硬编码 `incomplete_details: null` | 未处理 | 否 |

---

## 10. 对本项目最有参考价值的观察

按我认为的价值排序，并标注结论强度。

1. **「透传」是这批项目的绝对共识，八个里七个只做协议映射。**（强度：足以直接据此定默认行为。八个样本、判据明确、零反例。）唯一做自动续写的是 vscode-copilot-chat 的 codeMapper，而它的场景极窄——**全文件重写**，续写目标是确定性的文本产物，且 prompt 里有专门的 `inProgressRewriteContent` 变量位。它不是通用对话续写。这印证了 copilot-api-js spec §3 的判断：续写只在 A 类（text 截断）安全，而 A 类的安全性来自「已发文本已闭合、合法可提交」。

2. **被截断的 tool call 有四种截然不同的处理，且各自都写下了理由——这是本项目最需要先裁决的一格。**（强度：足以据此开出选项表让用户裁决，但不足以替用户选。）
   - 静默丢弃（vscode-copilot-chat，无注释说明，疑似非有意）
   - 尽力修复后转发（copilot-api-js `jsonrepair` + 可信性闸）
   - 校验后默认原样转发、opt-in 才 abort（hooyao，**并给出了实测理由**：Claude Code 自己有 `safeParseJSON` → `{}` → zod 校验 → `is_error` tool_result → 让模型重试这条原生恢复链，代理端 abort 反而把它掐掉了）
   - 整条响应转换失败（ghc-api-py，理由是「坏 input 会让 CLI 用不同的契约执行工具调用」）

   hooyao 那条理由与 ghc-api-py 那条理由**指向相反方向且都成立**，区别在于对下游客户端能力的假设。本项目主路径是 Anthropic Messages 服务 Claude Code，hooyao 的实测样本与我们的下游一致，权重更高。

3. **「续写腿的上游从 0 重新计 index」是一个会静默毁掉交付的坑。**（强度：强，有两份独立实现各自处理过。）copilot-api-js 的 `remapResponsesOutputIndex` 和 `remapAnthropicBlockIndex` 都在做同一件事，而且注释点明了边界：只能改 `output_index`，`sequence_number` 归 emitter、`content_index` 是 item 内作用域。本项目若将来做任何形式的多腿缝合，这是必须先解决的接线问题，与「要不要续写」这个策略问题正交。

4. **未知 `incomplete_details.reason` 的兜底，四个项目有三种裁决**：copilot-api-js → `end_turn`（并写明「不能让新原因静默继承 max_tokens」）、awsl-maxx → `stop`、ghc-api-py → 抛异常、hooyao → 一律 `max_tokens`（我认为这是缺陷，见 §5）。本项目已有 memory「日志行上的缺席读不出来」这条教训，同族问题：**兜底值会伪装成观测结果**。建议至少做到 copilot-api-js 的显式匹配 + 可观测标注，不要走 hooyao 的默认。

5. **copilot-api-js 的 P0 形态本身是可直接复制的中间态**：先只做「识别 + 打标签 + 不改 wire」，把配置面和分型器铺好但不通电。它的代价很低（一个观测器 + 一个分型器 + 一条 telemetry 维度），换来的是**真实终局分布的数据**——前身仓的 5 例样本（约 0.4%，全部撞客户端自设预算而非模型 cap，其中 2 例是 thinking 烧满 32k 换来 0 可见答案）就是这么来的，而这批数据直接决定了后续该不该做续写、对哪一型做。本项目若要动这块，我建议先复刻 P0，不要一步到 continuation。

6. **一处需要提醒的差异**：前身仓的 P0 只接了 Anthropic-direct 腿，而本项目的主路径是 **Anthropic Messages 输入 → OpenAI Responses 上游**——正好是前身仓那条**没接线**的腿（`isResponsesMaxTokensTerminal` 零调用点）。所以前身仓的观测数据覆盖不到本项目的主路径，不能直接搬用它的分布结论。
