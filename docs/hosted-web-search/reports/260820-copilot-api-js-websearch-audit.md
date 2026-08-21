# copilot-api-js 的 web search / server tool：实现到哪一层

- 调查日期：2026-08-20
- 被调查仓库：**两份都看了**
  - `/home/xp/src/ghc-api-proxy-py/refs/copilot-api-js`
  - `/home/xp/src/copilot-api-js`
- **两份的 `git HEAD` 完全相同**：`0b818082f docs(tmp): 撤回 durability-overlay 那条待办——peer 已于 09:13 修复`
- **两份的 `git status --porcelain` 逐行相同**，且 `diff -rq --exclude=node_modules --exclude=.git <A>/src <B>/src` **无任何输出**——`src/` 树逐字节一致。
- 因此：**本报告所有行号在两份副本上都成立**。下文一律以 `/home/xp/src/copilot-api-js` 为路径前缀书写，refs 那份同名同行。
- 本次调查**只读**，未修改被调查仓库的任何文件。

> 关于「工作树 dirty」：`git status` 显示大量 `M`/`??`，但改动集中在 `docs/`、`exp/`、`docs/memory/`，与本报告引用的 `src/` 文件无关（`diff -rq` 已证 `src/` 两份一致，且两份都基于同一 HEAD）。行号可信。

---

## 0. 摘要：七个问题的一句话答案

| # | 问题 | 答案 | 锚点 |
|---|---|---|---|
| 1 | 请求侧转成什么 | **裸 `{"type":"web_search"}`，一个键**。`max_uses` / `allowed_domains` / `blocked_domains` / `user_location` **全部静默丢弃**（无警告、无记录） | `from-ir/openai-responses/parameters.ts:58-65,78-82,92-114` |
| 2 | 有没有能力门 | **在 Anthropic→Responses 这条在产腿上：没有任何门**。`translateTools` 连 `model` 参数都不接。`supportsWebSearch` 是**另一条无关链路**（Codex `/models` 目录）的字段，不是悬空但**与本问题无关** | `parameters.ts:92`；`codex-assembly.ts:70` → `codex/catalog.ts:124` |
| 3 | 响应侧怎么办 | **降级成一个 `text` 块**，内容是 `[web_search: "<query>"] (id: <id>, status: <status>)`。**明令禁止**合成 `server_tool_use` / `web_search_tool_result` 对（RFC §7 红线 R-NO-REVIVE） | `from-ir/anthropic/server-tool.ts:24-27`；`from-ir/anthropic/response-body.ts:154-173` |
| 4 | `url_citation` annotations | **完全丢弃**，且是**静默**丢弃（连 degradation observation 都没记）。非流式读 `part.text` 时不看 `annotations`；流式的 `response.output_text.annotation.added` 事件类型定义了但解码器无 case | `to-ir/openai-responses/response-wire.ts:298-307,479-481`；`types/api/openai-responses.ts:390-396` |
| 5 | 流式三事件 | **`response.web_search_call.in_progress/.searching/.completed` 三个事件在全仓完全不存在**——不在类型 union 里，解码器 `default: return []` 静默吞掉。真正成块的时点是 **`response.output_item.done`**。关联用 **`output_index`，不用 `id`** | `types/api/openai-responses.ts:520-552`；`to-ir/openai-responses/response-wire.ts:195,445-455` |
| 6 | History / 续接 | **上一轮的 `server_tool_use` 与 `web_search_tool_result` 块在发往 Responses 时被整块丢弃**（记 observation，不回传）。**`web_search_call` 的 id 不保留、不回传**。声明的 `responses-output-item` / `responses-item-reference` 载体**是纯类型，全仓无任何构造点** | `from-ir/openai-responses/request-write.ts:252-260`；`core/types.ts:126-130` |
| 7 | 未请求的 `web_search_call` | **不做任何处理**，也无从区分：解码器不看请求侧声明了什么，一律降级成同一段文本 | `to-ir/openai-responses/response-wire.ts:88-90` |

**一句话总纲**：copilot-api-js 在 Responses 腿上对 web search 的实现是**「请求侧乐观映射一个裸类型 + 响应侧一律降级成文本」**。它**没有**原生块对、**没有**引用、**没有**能力门、**没有**续接，也**没有** usage 统计。它退役过一套自己造轮子的「双跳」（2026-07-13 ADR），退役后剩下的就是这层薄映射。

---

## 1. 在产链路的确认（先把「读的是不是活代码」钉死）

仓库里同时存在 `src/lib/translation/legacy-direct/` 与 `src/lib/translation/{to-ir,from-ir,bridges}/` 两套。**Anthropic→Responses 的在产路径是后者**：

```
routes/messages/handler-v4.ts
  → driver → CellAssembly(clientFormat="anthropic", targetEndpoint=/responses)
  → OUTBOUND_LEGS[/responses] = responsesLeg            # cell-assembly.ts:115
  → responsesLeg.translateOut → translateRequestVia     # openai-responses-cell.ts:110-126
  → hub-translate.ts:157-163  anthropicToResponsesBridge
  → renderAnthropicRequestAsResponsesViaIr              # bridges/anthropic-to-responses-request-via-ir.ts:70
```

`src/lib/translation/legacy-direct/anthropic-to-responses-request.ts` **无任何 src 内导入者**（只被 `legacy-direct/index.ts:16-17` re-export）：

```
$ rg -n "legacy-direct/anthropic-to-responses-request" src/
（无输出）
```

不过两条路径**共用同一份 tools 映射**——`legacy-direct/anthropic-to-responses-request.ts:109-110` 和 `bridges/anthropic-to-responses-request-via-ir.ts:33-34` 都从 `from-ir/openai-responses/parameters.ts` 导入 `translateTools`/`translateToolChoice`。所以本报告 Q1 的结论对两条路径都成立。

响应侧同理：`legacy-direct/responses-to-anthropic-stream.ts:305-317` 与在产的 `from-ir/anthropic/response-stream.ts:256-267` 都调同一个 `webSearchCallToText`（`from-ir/anthropic/server-tool.ts:24`），**行为一致**。

---

## 2. Q1 — 请求侧：Anthropic 声明 → Responses 请求

### 2.1 映射表（逐字）

`src/lib/translation/from-ir/openai-responses/parameters.ts:58-68`：

```ts
export const SERVER_TOOL_MAPPING: ReadonlyArray<{ anthropicPrefix: string; responsesType: ResponsesBuiltinToolType }> = [
  // Anthropic's Responses-facing web_search request is a bare `{type:"web_search"}` (Phase 0 probe (c) —
  // NOT the richer `web_search_preview`/schema-carrying shape some OpenAI docs describe elsewhere; the
  // GHC Responses upstream accepted the bare form and returned real results).
  { anthropicPrefix: "web_search_", responsesType: "web_search" },
  // web_fetch / code_execution have NO probed Responses-upstream request shape yet (Phase 0 only probed
  // web_search) — omitted from the table until probed, rather than guessed. Falls through to strip+warn.
]

/** The Responses builtin-tool `type` values this table may emit (a subset of `ResponsesBuiltinTool["type"]`). */
export type ResponsesBuiltinToolType = "web_search"
```

匹配键是**类型前缀** `web_search_`（`parameters.ts:71-73`），所以 `web_search_20250305`、`web_search_20260101`、任何带日期后缀的都命中。

### 2.2 输出键集：**只有 `type` 一个键**

`parameters.ts:78-82`：

```ts
export function translateNamedToolChoice(tool: AnthropicTool): AnthropicTranslatedNamedToolChoice | undefined {
  if (!isApiDefinedToolType(tool.type)) return { type: "function", name: tool.name }
  const mapped = tool.type ? mapServerToolType(tool.type) : undefined
  return mapped ? { type: mapped } : undefined
}
```

`parameters.ts:92-114`：

```ts
export function translateTools(tools: Array<AnthropicTool>, reqId: string | undefined): Array<ResponsesTool> {
  const out: Array<ResponsesTool> = []
  for (const tool of tools) {
    const namedChoice = translateNamedToolChoice(tool)
    if (!namedChoice) {
      dropWarn(
        `dropping native server tool "${tool.name}" (type: ${tool.type}) — no Responses-builtin mapping (unmapped type or a client-executed builtin)`,
        reqId,
      )
      continue
    }
    if (namedChoice.type !== "function") {
      out.push(namedChoice)          // ← ★ 原样推入 { type: "web_search" }，不带任何其他字段
      continue
    }
    out.push({
      ...namedChoice,
      ...(tool.description !== undefined && { description: tool.description }),
      ...(tool.input_schema !== undefined && { parameters: tool.input_schema }),
    } satisfies ResponsesFunctionTool)
  }
  return out
}
```

注意 `namedChoice.type !== "function"` 那条分支**直接 `out.push(namedChoice)`**，而 `namedChoice` 是 `{ type: "web_search" }`——**一个键**。函数分支才有 `description`/`parameters` 的展开。

**结论（Q1 的三个子问题）**：

| Anthropic 字段 | 处置 | 依据 |
|---|---|---|
| `type: "web_search_20250305"` | → `type: "web_search"` | `parameters.ts:62,71-73` |
| `name: "web_search"` | **丢弃**（未进入 server-tool 分支的输出对象） | `parameters.ts:103-106` |
| `max_uses` | **静默丢弃**（无 `dropWarn`，无 observation） | 同上，对象里没有这个键 |
| `allowed_domains` | **静默丢弃** | 同上 |
| `blocked_domains` | **静默丢弃** | 同上 |
| `user_location` | **静默丢弃** | 同上 |
| `cache_control`（若带） | **静默丢弃** | 同上 |

「静默」这个判断有依据：`dropWarn` 只在 `!namedChoice`（即**没有映射**）时触发（`parameters.ts:97-101`），映射命中的分支**没有任何 warn / observation / degradation 上报**。

**上游会把裸 `{type:"web_search"}` 自行展开成什么**——仓库里有一手实测捕获，`exp/anthropic-responses-direct/probe-c-websearch.json`（响应体的 `tools` 回显）：

```json
"tools": [{"type": "web_search", "return_token_budget": "default", "search_content_types": ["text"],
           "search_context_size": "medium",
           "user_location": {"type": "approximate", "city": null, "country": "US", "region": null, "timezone": null}}]
```

即上游用**自己的默认值**填 `user_location` 等字段；客户端传来的 `user_location` 被 js 丢掉后，上游按账号地理位置自行推断。

### 2.3 `tool_choice` 指向 web search

`parameters.ts:125-156`：

```ts
export function translateToolChoice(
  choice: AnthropicToolChoice,
  sourceTools: Array<AnthropicTool> | undefined,
  translatedTools: Array<ResponsesTool> | undefined,
): ResponsesToolChoice | undefined {
  switch (choice.type) {
    case "auto": { return "auto" }
    case "any": {
      // Anthropic "any" = must call SOME tool → Responses "required".
      return translatedTools && translatedTools.length > 0 ? "required" : undefined
    }
    case "none": { return "none" }
    case "tool": {
      const selectedTool = sourceTools?.find((tool) => tool.name === choice.name)
      if (!selectedTool) return undefined
      const translatedChoice = translateNamedToolChoice(selectedTool)
      if (!translatedChoice) return undefined
      const isAvailable = translatedTools?.some((tool) =>
        translatedChoice.type === "function" ? tool.type === "function" && tool.name === translatedChoice.name : tool.type === translatedChoice.type,
      )
      return isAvailable ? translatedChoice : undefined
    }
    default: { return "auto" }
  }
}
```

即 `{"type":"tool","name":"web_search"}` → 先按 **`name`** 在原始 `tools[]` 里找到那条声明，走同一个 `translateNamedToolChoice` 得到 `{type:"web_search"}`，再确认译后 tools 里确实有 `type === "web_search"`，命中则输出 **`tool_choice: {"type":"web_search"}`**；否则 `undefined`（省略 `tool_choice`，而非发一个悬空的 function choice）。

**注意一个真实缺口**：`case "tool"` 用 `tool.name === choice.name` 做匹配。Anthropic 的 web_search 声明 `name` 恒为 `"web_search"`，所以这条能命中。但如果客户端声明的 `name` 与 `choice.name` 不一致，就 `undefined` 掉了——没有按 type 兜底。

### 2.4 请求侧的**入站**方向（历史块）见 §7。

---

## 3. Q2 — 能力门：没有

### 3.1 在产腿上确实没有任何门

`translateTools(tools, reqId)` 的签名（`parameters.ts:92`）**不接 `model`**。调用点 `bridges/anthropic-to-responses-request-via-ir.ts:80`：

```ts
const tools = payload.tools ? translateTools(payload.tools, opts?.reqId) : undefined
```

同文件 `:82` 的 `translateThinkingToReasoning(payload, opts?.model)` **确实**接了 model 并做能力收窄（`parameters.ts:181` `modelSupportsReasoningEffort(model)`）——**对比之下更说明 tools 这条是有意/无意地没有门**，不是「参数没传到」。

`responsesLeg.prepareWire` → `prepareResponsesDirectWire`（`codec/openai-responses/openai-responses-leg.ts:110-119`）也不碰 tools：

```ts
export function prepareResponsesDirectWire(env: RequestEnvelope): PreparedRequest {
  const model = env.request.model as Model | undefined
  const prepared = prepareResponsesRequest(env.attempt.body as ResponsesPayload, { resolvedModel: model })
  return { url: ENDPOINT.RESPONSES, headers: new Headers(prepared.headers), body: prepared.wire, stream: prepared.wire.stream ?? false }
}
```

### 3.2 那套 learned 门**挂在另一条腿上**，Responses 腿够不着

仓库里**确实有**一套 server-tool 剥离机制，但它是 `/v1/messages` 腿专属：

- `stripServerTools`（`lib/anthropic/message-tools.ts:380-400`）唯一消费点是 `buildWirePayload`（`lib/anthropic/request-preparation.ts:579`），只被 `prepareAnthropicRequest` 调用；
- `prepareAnthropicRequest` 只被 `codec/anthropic/anthropic-leg.ts:66,124` 调用，两处 `url` 都是 `ENDPOINT.MESSAGES`（`:103,:137`）；
- 喂它的 retry 策略 `server-tool-rejection-retry` 在注册表里 `appliesTo: appliesToMessages`（`lib/request/retry-registry.ts:274`），而

```ts
// src/lib/request/retry-registry.ts:140-143
/** `appliesTo` gate shared by all 13 anthropic-only (400-class) entries (RFC §3.3 — targetEndpoint, NOT clientFormat). */
function appliesToMessages(ctx: RetryStrategyContext): boolean {
  return ctx.targetEndpoint === ENDPOINT.MESSAGES
}
```

`web-search-not-found-retry` 同样 `appliesTo: appliesToMessages`（`retry-registry.ts:303`）。

所以：**Anthropic 客户端 → Responses 上游这条腿，既没有前置能力门，也没有后置 400 自愈门。** 它是纯乐观发送。这一条与 `docs/tmp/260820-websearch-400-copilot-api-js.md` §0 第 3 条一致，我独立复核确认。

### 3.3 `codex-assembly.ts:70` 的 `supportsWebSearch`：**不是悬空代码，但与 web search 请求路径无关**

`src/lib/codex-assembly.ts:59-72`：

```ts
function toCodexModel(model: Model): CodexModel {
  const supports = model.capabilities?.supports
  const efforts = supports?.reasoning_effort
  return {
    id: model.id,
    displayName: model.name,
    maxContextWindowTokens: model.capabilities?.limits?.max_context_window_tokens,
    maxPromptTokens: model.capabilities?.limits?.max_prompt_tokens,
    reasoningEfforts: Array.isArray(efforts) ? efforts.filter((entry) => typeof entry === "string") : undefined,
    supportsVision: supports?.vision === true,
    supportsParallelToolCalls: supports?.parallel_tool_calls === true,
    supportsWebSearch: supports?.web_search === true,
  }
}
```

它有且只有一个消费者：

```
$ rg -n 'supportsWebSearch' src/
src/lib/codex-assembly.ts:70:    supportsWebSearch: supports?.web_search === true,
src/lib/codex/catalog.ts:124:  if (ghc.supportsWebSearch === false) merged.supports_search_tool = false
src/lib/codex/ports.ts:34:  supportsWebSearch?: boolean
```

`codex/catalog.ts:124` 是**给 Codex CLI 拼 `/models` 目录**用的（`supports_search_tool` 是 Codex 侧的字段名）。它**不参与任何请求构造**。

关于「是否恒为 false」：`ModelSupports` 是开放袋（`packages/foundation/src/ghc-model-types.ts:37-43`，`[key: string]: boolean | number | Array<string> | undefined`），所以 `supports?.web_search === true` 在类型上不恒 false。**但我在仓库里没找到任何 GHC `/models` 抓取样本含 `"web_search"` 这个 supports 键**——搜了全仓 `*.json` 的 `"web_search"` 字面量，命中全是 Anthropic 块类型或 Responses 工具类型，没有一条是 capability flag。

**因此我的判断（标为推测，中等强度）**：`supportsWebSearch` 在真实 GHC 目录上大概率恒为 `undefined`，从而 `=== true` 恒 false、`=== false` 也恒 false（`catalog.ts:124` 的 `if` 恒不进）。这是「**实质悬空**」而非「代码悬空」。但**它本来就不是本问题要找的那道门**——它读的是 Codex 目录字段，不是 web search 请求门。原委托里那条线索的方向需要修正。

---

## 4. Q3 — 响应侧：`web_search_call` → Anthropic 什么块

### 4.1 结论：**一个 `text` 块**，且这是被写进 RFC 的硬红线

`src/lib/translation/from-ir/anthropic/server-tool.ts:1-27`（整个模块的开头就是决策说明）：

```ts
/**
 * How an Anthropic emitter renders a server-tool call it did not originate.
 *
 * Anthropic has `server_tool_use` / `web_search_tool_result` blocks, so a server tool that CAME from
 * Anthropic round-trips as itself. A Responses `web_search_call` is a different matter: RFC §7 draws a
 * red line at synthesising a `web_search_tool_result` we never received, because that block asserts
 * results the upstream never handed us. It degrades to readable text instead — the same rendering the
 * direct bridges produce, imported rather than re-written so the two cannot drift.
 * ...
 */
export function webSearchCallToText(item: Extract<ResponsesOutputItem, { type: "web_search_call" }>): string {
  const query = item.action?.query ?? item.action?.queries?.join(", ") ?? "(unknown query)"
  return `[web_search: "${query}"] (id: ${item.id}, status: ${item.status})`
}
```

**产出的块（逐字）**：

```json
{ "type": "text", "text": "[web_search: \"official Bun runtime website\"] (id: tLN4lWdG/P9ALdQ…, status: completed)" }
```

字段取值来源：
- `query` ← `item.action.query`，缺失则 `item.action.queries.join(", ")`，再缺失则字面量 `"(unknown query)"`
- `id` ← `item.id`（**`output_item.done` 那一份的 id**，见 §6 的风险讨论）
- `status` ← `item.status`

### 4.2 非流式发射点

`src/lib/translation/from-ir/anthropic/response-body.ts:154-173`：

```ts
      case "function-call":
      case "server-tool-call": {
        const degraded = item.kind === "server-tool-call" ? degradedServerToolText(item) : undefined
        if (degraded !== undefined) {
          content.push({ type: "text", text: degraded } as unknown as ContentBlock)
          observations.push({
            itemKey: item.key,
            reason: DEGRADATION_REASONS.serverToolNotRepresentable,
            detail: "a responses server-tool call has no anthropic form that does not assert results we never received",
          })
          break
        }
        content.push({
          type: item.kind === "function-call" ? "tool_use" : "server_tool_use",
          id: item.call?.callId ?? "",
          name: item.call?.name ?? "",
          input: parsedInput(item.authoritativeArguments),
        } as unknown as ContentBlock)
        break
      }
```

注意 `degradedServerToolText` 的门（`server-tool.ts:35-42`）：

```ts
export function degradedServerToolText(item: PerOutputItemState): string | undefined {
  if (item.source.identity.protocol !== "openai-responses") return undefined
  const payload = item.call?.sourcePayload
  if (payload === undefined || typeof payload !== "object") return undefined
  const type = (payload as { type?: unknown }).type
  if (type !== "web_search_call") return undefined
  return webSearchCallToText(payload as Extract<ResponsesOutputItem, { type: "web_search_call" }>)
}
```

**这里的分工要看清**：`server_tool_use` 原生块**只在源协议本身就是 Anthropic 时**才会走到（`degradedServerToolText` 返回 `undefined` → 落到 `:166` 的原生分支）。源是 Responses 就一定降级。所以 `server_tool_use` 分支对我们这个形态（Anthropic 入 / Responses 上游）**永远不会命中**。

### 4.3 流式发射点

`src/lib/translation/from-ir/anthropic/response-stream.ts:251-269`：

```ts
          case "finish-item": {
            const item = transition.item
            if (item === undefined) break
            // A server tool arrives whole, with no deltas, and has no Anthropic wire form we are allowed
            // to synthesise. It degrades to a readable text block, emitted complete and closed here.
            if (item.kind === "server-tool-call" || item.kind === "degraded-text") {
              const text = degradedServerToolText(item) ?? item.authoritativeOutput ?? item.parts.values().next().value?.authoritativeText ?? ""
              if (text.length === 0) break
              emitMessageStart(out)
              closeOpenBlock(out)
              const index = blockIndexFor(item.key)
              out.push(
                anthropicSseFrame({ type: "content_block_start", index, content_block: { type: "text", text: "" } }),
                anthropicSseFrame({ type: "content_block_delta", index, delta: { type: "text_delta", text } }),
                anthropicSseFrame({ type: "content_block_stop", index }),
              )
            }
            break
          }
```

**一次性 start + delta + stop 三帧，在 `finish-item` 上原子发出**——不存在半开的 web_search 块。

### 4.4 `usage.server_tool_use.web_search_requests`：**不产出**

```
$ rg -n 'tool_usage|web_search_requests|num_requests' src/ --glob '!*.test.ts'
（无输出）
```

上游 `probe-c-websearch.json` 明明返回了 `"tool_usage": {"web_search": {"num_requests": 1}}`，js **完全不读**。所以走 Responses 腿时，回给客户端的 `usage` 里**没有** `server_tool_use.web_search_requests`。（`exp/delivery-inferred-boundaries/captures/anthropic.sse:47` 里那个 `server_tool_use:{web_fetch_requests:0,web_search_requests:0}` 是 `/v1/messages` 直通腿上游自己给的，不是 js 合成的。）

---

## 5. Q4 — `url_citation` annotations：静默丢弃

### 5.1 类型定义存在

`src/types/api/openai-responses.ts:385-396`：

```ts
/** Emitted when a citation/file/container-file annotation is attached to an output_text content
 *  part while streaming (e.g. gpt-5.5 web_search_preview native citations). Same minefield shape
 *  ...
 *  node_modules/openai/lib/responses/ResponseAccumulator.js, `annotation.added` case ~97-107). */
export interface OutputTextAnnotationAddedEvent {
  type: "response.output_text.annotation.added"
  ...
  annotation_index: number
  annotation: unknown
}
```

且在 union 里：`types/api/openai-responses.ts:536 | OutputTextAnnotationAddedEvent`。

### 5.2 但没有任何解码

全仓对该事件名的引用只有三处，全是**类型定义与缓冲白名单**，无一处解码：

```
$ rg -n 'annotation\.added|OutputTextAnnotationAddedEvent' src/
src/types/api/openai-responses.ts:389   （注释）
src/types/api/openai-responses.ts:390   export interface OutputTextAnnotationAddedEvent {
src/types/api/openai-responses.ts:536   | OutputTextAnnotationAddedEvent
src/lib/codec/openai-responses/buffered-merge-reducer.ts:20,27  （merge reducer 的事件名清单）
```

在产解码器 `to-ir/openai-responses/response-wire.ts` 的 `decode()` switch（`:369-482`）**没有这个 case**，落 `default: return []`（`:479-481`）。

### 5.3 非流式同样丢

`decodeResponsesBody`（`response-wire.ts:141-166`）与 `backfillPartsFromFinal`（`:295-316`）都只读 `part.text` / `part.refusal`：

```ts
    for (const [at, part] of content.entries()) {
      // `refusal` is a structured-output refusal, whose text sits in its own field. ...
      const text = str(part.text) || str(part.refusal)
      if (text === "") continue
      ...
    }
```

`ResponsesOutputTextPart.annotations: Array<unknown>`（`types/api/openai-responses.ts:168`）——类型上就是 `unknown`，从未被读。

### 5.4 Anthropic 侧也明说不产 `citations`

`from-ir/anthropic/response-body.ts:118-119`：

```ts
        // No `citations`: the IR never saw one, and the direct bridge this replaces does not emit the
        // field either. Inventing `citations: null` would be a gratuitous wire change dressed as fidelity.
```

**结论**：js **只依赖正文里的内联 markdown 引用**（模型自己在 `output_text` 里写的链接），**没有**任何 `citations` / `web_search_result_location` 结构化产出。且丢弃是**静默的**——没有 `dropWarn`、没有 degradation observation。这是这套代码里少见的、与它自己「never-swallow」纪律不一致的一处。

`src/lib/anthropic/stream-accumulator.ts:368-370` 那套 `copilot_annotations.ip_code_citations` 是**另一回事**——Copilot 在 `/v1/messages` 直通腿上给的 IP 代码引用扩展，与 Responses 的 `url_citation` 无关。

---

## 6. Q5 — 流式路径

### 6.1 三个 `web_search_call.*` 事件：**全仓不存在**

```
$ rg -n 'web_search_call\.(in_progress|searching|completed)|response\.web_search_call' src/ tests/
（无输出，exit 1）
```

`ResponsesStreamEvent` union（`types/api/openai-responses.ts:520-552`）逐项列举了 lifecycle / output-item / content-part / text / function-call / refusal / reasoning / error 八组，**没有 server-tool 组**。

因此这三个事件走解码器 `default: return []`（`to-ir/openai-responses/response-wire.ts:479-481`），**静默吞掉，无记录**。

### 6.2 成块时点：`response.output_item.done`

`to-ir/openai-responses/response-wire.ts:445-455`：

```ts
        case "response.output_item.done": {
          if (settled.has(event.output_index)) return []
          // An item can arrive WHOLE, with no `added` and no deltas — a `web_search_call` does exactly
          // that. Returning early here (which this used to do) dropped the entire item on the floor:
          // it never entered the ledger, so no emitter could render it and nothing recorded the loss.
          const opening = open.get(event.output_index) === undefined ? declareItem(event.output_index, event.item) : []
          const item = open.get(event.output_index)
          if (!item) return opening
          open.delete(event.output_index)
          return [...opening, ...closeItem(event.output_index, item, { kind: "complete" }, event.item)]
        }
```

注意这里的**双保险**：即使 `output_item.added` 从没来过，`.done` 也会补一个 `declareItem` 再立刻 `closeItem`。这是修过的 bug（注释里写着「which this used to do」）。

`closeItem` 里 server-tool 的处理（`:351-353`）：

```ts
    if (item.kind === "server-tool-call") {
      updates.push({ type: "set-final-arguments", key: item.itemKey, arguments: item.argumentDeltas.join("") })
    }
```

即 **arguments 恒为空串**（`web_search_call` 没有 arguments delta 事件）。真正的 query 走的是 `call.sourcePayload`（见下）。

### 6.3 关联方式：**`output_index`，不是 `id`** ★★★

这是对我们最关键的一条。`to-ir/openai-responses/response-wire.ts:195-204`：

```ts
  const itemKeyFor = (index: number): ItemKey => asItemKey(`${deps.segmentId}:item:${index}`)
  const partKeyFor = (index: number, kind: string, at: number): PartKey => asPartKey(`${deps.segmentId}:item:${index}:${kind}:${at}`)

  const sourceFor = (index: number, callId?: string): SourceRef => ({
    identity: deps.identity,
    turn: deps.turn,
    blockOrOutputIndex: index,
    ...(responseId !== undefined && { sourceId: responseId }),
    ...(callId !== undefined && { callId }),
  })
```

**ledger 的 item 主键是 `${segmentId}:item:${output_index}`**。`open` / `settled` 两张表也都以 `output_index` 为键（`:376-377,445-455`）。`id` 只作为 `call.callId` 与 `source.callId` **附带记录**，不参与关联：

`response-wire.ts:236-262`：

```ts
  const declareItem = (index: number, sourceItem: ResponsesOutputItem): Array<LedgerUpdate> => {
    const kind = kindOfItem(sourceItem)
    const raw = sourceItem as unknown as Record<string, unknown>
    const callId = str(raw.call_id) || str(raw.id)
    const isCall = kind === "function-call" || kind === "server-tool-call"
    const updates: Array<LedgerUpdate> = [
      {
        type: "declare-item",
        key: itemKeyFor(index),
        segmentId: deps.segmentId,
        source: sourceFor(index, isCall ? callId : undefined),
        ordinal: index,
        kind,
        ...(isCall && {
          call: {
            callId,
            name: str(raw.name) || (kind === "server-tool-call" ? "web_search" : ""),
            // Kept only for the server tool: it is the one whose Anthropic rendering has to describe
            // what the call DID, and a function call's arguments already travel on their own channel.
            ...(kind === "server-tool-call" && { sourcePayload: sourceItem }),
          },
        }),
      } as Extract<LedgerUpdate, { type: "declare-item" }>,
    ]
    open.set(index, { itemKey: itemKeyFor(index), kind, parts: new Map(), argumentDeltas: [] })
    return updates
  }
```

两个细节值得记：
1. `name` 缺失时对 server-tool **硬编码兜底为 `"web_search"`**（`:252`）——`web_search_call` item 本来就没有 `name` 字段，所以这个兜底**总是**在起作用。
2. `sourcePayload: sourceItem` **只对 server-tool 保留**，这是后面 `webSearchCallToText` 能拿到 `action.query` 的唯一途径。

`.done` 分支（`:450`）用的是 `event.item`（`.done` 那一份），覆盖 `.added` 那一份——所以最终文本里的 `id` 是 **`.done` 的 id**。

### 6.4 legacy 直译桥的做法（作对照）

`legacy-direct/responses-to-anthropic-stream.ts:296-317` 同样只在 `output_item.done` 上处理，`blockIndexFor(event.output_index)`——**也是按 `output_index` 关联**。两条路径一致。

---

## 7. Q6 — History / 续接

### 7.1 上一轮的 server-tool 块：**丢弃，不回传**

入站读取（`to-ir/anthropic/request-read.ts:42-46`）把 Anthropic 块归类：

```ts
    case "server_tool_use": {
      return "server-tool-use"
    }
    ...
      return type.endsWith("_tool_result") ? "server-tool-result" : undefined
```

出站写 Responses 请求（`from-ir/openai-responses/request-write.ts:252-260`）：

```ts
      case "server-tool-use":
      case "server-tool-result": {
        observations.push({
          reason: DEGRADATION_REASONS.serverToolNotRepresentable,
          detail: `an anthropic ${token.kind} block has no responses request-item form`,
          ordinal: token.ordinal,
        })
        break
      }
```

**没有 `input.push`**——整块丢弃，只记 observation。对比同文件 `:217-250` 的 reasoning 分支：那里有精心设计的 carrier 往返（`encrypted_content` 回灌）。**server tool 没有任何等价机制。**

### 7.2 `web_search_call` 的 id：**不保留、不回传**

上一轮我们发给客户端的是**一个 text 块**（§4），文本里虽然含 `(id: …)`，但下一轮客户端把它当普通文本回传，js 也只当普通文本处理。**没有任何代码从文本里回解析 id。**

### 7.3 声明了续接载体，但**从未构造**

`src/lib/translation/core/types.ts:113-130`：

```ts
/**
 * Responses-side server-tool item types allowed into a continuation carrier. Deliberately a closed
 * set rather than a bare `string`: without it, a `responses-output-item` payload could carry an
 * arbitrary blob — including an Anthropic `web_search_tool_result` in disguise, which RFC §7's red
 * line forbids us to ever synthesise. Add entries as capabilities open; never widen to `string`.
 */
export type ResponsesServerToolItemType = "web_search_call"

/**
 * ...
 * The reference and the whole item are two granularities of one capability, not two features. Measured against the real upstream on 2026-08-11 (`exp/responses-server-tool-continuation/`): the whole item and a bare `{type,id}` are both accepted, `item_reference` is **not** (404 for `web_search_call`) — but a *fabricated* short id is accepted too, so acceptance does not discriminate a real reference from a made-up one and cannot be used to narrow the shape. Hence `responses-output-item` stays the default: it is the only form that preserves the part we cannot inspect.
 */
export type ContinuationRecord =
  | Readonly<{ kind: "claude-signature"; opaque: string }>
  | Readonly<{ kind: "responses-encrypted"; opaque: string }>
  | Readonly<{ kind: "responses-item-reference"; ref: Readonly<{ type: ResponsesServerToolItemType; id: string }> }>
  | Readonly<{ kind: "responses-output-item"; item: Readonly<{ type: ResponsesServerToolItemType }> & Readonly<Record<string, unknown>> }>
```

```
$ rg -n 'responses-output-item|responses-item-reference' src/
src/lib/translation/core/types.ts:115  （注释）
src/lib/translation/core/types.ts:124  （注释）
src/lib/translation/core/types.ts:129  （类型定义）
src/lib/translation/core/types.ts:130  （类型定义）
```

**唯四命中全在类型定义文件内**——**没有任何构造点，没有任何消费点**。这是**真正的悬空代码**（与 §3.3 的 `supportsWebSearch` 不同，后者至少有一个消费者）。

解码器给 server-tool 的 disposition（`to-ir/openai-responses/response-wire.ts:224-230,356-362`）实际写的是什么：

```ts
  const dispositionFor = (opaque: string | undefined, kind: ItemKind): ItemDisposition => {
    const continuation: ContinuationDisposition =
      kind === "drop" ? { kind: "none" }
      : opaque !== undefined ? { kind: "carrier", record: { kind: "responses-encrypted", opaque } }
      : { kind: "none" }
    return { presentation: { kind: "native" }, continuation }
  }
  ...
    const encrypted = item.kind === "reasoning" ? str(raw?.encrypted_content) : ""   // ← 只对 reasoning 取
    updates.push({
      type: "finish-item",
      key: item.itemKey,
      terminal: itemTerminal,
      disposition: dispositionFor(encrypted === "" ? undefined : encrypted, item.kind),
    })
```

`encrypted` 只对 `reasoning` 求值，server-tool 恒为 `""` → `opaque === undefined` → **continuation = `{kind: "none"}`**。即「判定它不携带跨轮状态」。

### 7.4 反向（Responses 出站发射器）：`web_search_call` 会被重建，但字段贫瘠

`from-ir/openai-responses/response-body.ts:220-237`（这是 Responses **客户端**方向，与我们形态相反，但说明了它对这个 item 的完整认知）：

```ts
      case "server-tool-call": {
        // Responses models a server tool as a single `web_search_call` item; its result folds into the
        // same item rather than following as a sibling. Any other server tool has no Responses shape.
        if (item.call?.name === "web_search") {
          output.push({
            type: "web_search_call",
            id: item.call.callId,
            status: statusOf(item) === "completed" ? "completed" : "incomplete",
          } as ResponsesOutputItem)
          break
        }
        ...
```

注意它**不重建 `action`**——query 丢了。

### 7.5 `/v1/messages` 直通腿另有一套历史降级（与 Responses 腿无关，但值得知道）

`lib/anthropic/sanitize/index.ts:104-118`：

```ts
  // Downgrade native server-tool blocks left in prior turns by the web_search
  // double-hop (server_tool_use{web_search} + *_tool_result) into plain
  // tool_use + tool_result. MUST run BEFORE processToolBlocks so the tool
  // reference validation sees the already-downgraded (plain) blocks. No-op when
  // disabled. See rewrite-server-tool-blocks.ts for the self-poisoning loop.
  messages = rewriteServerToolBlocks(messages, resolveServerToolMode(payload.model)).messages

  // Fallback (always-on): downgrade any synthesized web_search turn whose result
  // `encrypted_content` is empty/missing — upstream rejects it with "Invalid
  // encrypted_content in search_result block" and there is no valid value we can
  // supply (empirically, even a non-empty placeholder is rejected). ...
  messages = downgradeEmptyEncryptedSearchResults(messages).messages
```

**但这条链在 Anthropic→Responses 上根本不跑**——`codec/anthropic/request-rewrite-adapter.ts:66`：

```ts
    // Two-axis gate (RFC §3.1 / §7.1): the sanitize chain produces the UPSTREAM Anthropic
    // `/v1/messages` wire, so it gates on the OUTBOUND leg (`targetEndpoint`), not the inbound
    // `clientFormat`. ...
    appliesTo: (env) => env.attempt.targetEndpoint === ENDPOINT.MESSAGES,
```

在 Responses 腿上不需要它，因为 §7.1 的丢弃已经把这些块拦掉了。

---

## 8. Q7 — 上游返回未请求的 `web_search_call`

**没有任何处理，也无从检测。**

`kindOfItem`（`to-ir/openai-responses/response-wire.ts:76-95`）只看 item 类型：

```ts
function kindOfItem(item: ResponsesOutputItem): ItemKind {
  switch (item.type) {
    case "message": { return "text" }
    case "reasoning": { return "reasoning" }
    case "function_call":
    case "custom_tool_call": { return "function-call" }
    case "web_search_call": { return "server-tool-call" }
    default: { return "drop" }
  }
}
```

解码器的 deps（`ResponsesWireDecoderDeps`）里**没有请求侧 tools 的任何信息**——它拿不到「本轮声明了什么」。所以「请求了」和「没请求」的 `web_search_call` 走**完全相同**的降级路径，产出同一段文本。

这在 js 的形态下不算 bug：它反正一律降级成文本，客户端看到 `[web_search: "..."]` 也读得懂。但**对我们要做原生块对的目标，这个「无请求侧上下文」的解码器结构直接不够用**（见 §9）。

---

## 9. 如果照搬：哪些能用、哪些不能用

前提约束：**我们已实测 `web_search_call` 的 id 在每个事件里都不同**（Copilot 逐事件重新加密 item.id）。以下按这个约束逐条评估。

### 9.1 能直接用的

| 可用项 | 位置 | 为什么能用 |
|---|---|---|
| **请求侧映射：`web_search_*` 前缀 → 裸 `{type:"web_search"}`** | `parameters.ts:58-73` | 与我们的实测一致（200 且真执行搜索）。前缀匹配而非全等匹配是对的——Anthropic 的日期后缀会变。 |
| **`tool_choice` 的三段逻辑**：`any`→`required`（且需 tools 非空）、命名 choice 必须与声明走同一映射、译不出就整个省略而不是发悬空 choice | `parameters.ts:125-156` | 这三条都是与上游语义对齐的正确判断，与 id 稳定性无关。 |
| **`output_index` 作为 item 主键，`id` 只作附带记录** | `response-wire.ts:195-204,236-262,445-455` | ★ **这条恰恰是我们最该抄的**。它天然免疫 id 逐事件变化。 |
| **`.done` 无 `.added` 也能补声明再立刻结算** | `response-wire.ts:445-455` | `web_search_call` 就是整块到达。这个双保险必须有。 |
| **保留 `sourcePayload` 原件** | `response-wire.ts:255`；`core/types.ts:204-212` | 结构化结果（`action.query`、`action.queries`、未来可能新增的字段）只有留原件才不丢。我们要做原生块对，更需要这个。 |
| **不合成没收到的结果**（R-NO-REVIVE 的动机） | `server-tool.ts:1-12`；`exp/encrypted-content-400/README.md` | 它的教训是一手的：合成的 `web_search_tool_result{encrypted_content:""}` 被客户端存进历史、每轮回传、上游恒 400，把 400 焙进了整个会话。**这个失败模式我们必须避开**——若我们要产原生块对，`encrypted_content` 这个字段怎么填必须先有答案。 |
| **`name` 缺失时兜底 `"web_search"`** | `response-wire.ts:252` | `web_search_call` item 确实没有 `name`。 |

### 9.2 不能用 / 会在我们这里失效的

| 不可用项 | 位置 | 失效原因 |
|---|---|---|
| **`webSearchCallToText` 把 `id` 写进给客户端的文本** | `server-tool.ts:26` | 我们实测 id 每个事件都不同，写进文本的那个 id **对客户端毫无意义、对上游也不可回传**。而且它把一个不稳定值固化进了会被客户端存历史的正文——正是 §9.1 最后一行那个失败模式的同族。**要抄这个降级渲染的话，必须把 `id` 从文本里拿掉。** |
| **整个「降级成 text」的产品决策** | `server-tool.ts`、`response-body.ts:154-173`、`response-stream.ts:256-267` | 这是 js 的**终点**，不是我们的。我们的目标是 `server_tool_use` + `web_search_tool_result` 原生块对。js 在这条路上**没有可抄的实现**，只有一条「不要合成」的警告。 |
| **`ContinuationRecord` 的 `responses-item-reference` / `responses-output-item`** | `core/types.ts:129-130` | **纯类型，零构造点**。它的 docstring 记的 2026-08-11 实测（`item_reference` 对 `web_search_call` 返 404；整 item 与 `{type,id}` 都接受；**伪造的短 id 也接受**）本身是有价值的情报——但它同时说明「上游接受」不能证明「引用有效」。叠加我们的 id 不稳定实测，**回传任何 id 都不可靠**：上游给 200 也不代表它认得那个 id。**结论：不要按 id 做续接。** |
| **`supportsWebSearch` 那条能力门线索** | `codex-assembly.ts:70` → `codex/catalog.ts:124` | 方向错了。它是 Codex `/models` 目录字段，不参与请求构造；且 GHC 目录里大概率没有 `supports.web_search` 键（推测，中等强度：仓库无一手样本）。**照抄它不会得到任何能力门。** |
| **`stripServerTools` + `server-tool-rejection-retry` 那套 learned 自愈** | `message-tools.ts:380-400`；`retry-registry.ts:140-143,272-279,299-310` | 它**只挂在 `targetEndpoint === /v1/messages` 上**。我们的形态是 Responses 上游，照搬门的写法会得到一道**恒不触发**的门。要用必须重挂 gate。（这一条与 `docs/tmp/260820-websearch-400-copilot-api-js.md` §0-3 的结论一致，我独立复核确认。） |
| **依赖 `response.web_search_call.*` 三事件** | 不存在 | js 从来没实现过，也就没有可抄的时序设计。我们若要做「搜索进行中」的可见反馈，得自己设计——但注意我们是块级交付，进行中状态本来也交付不出去。 |
| **annotations 静默丢弃** | `response-wire.ts:298-307,479-481` | 我们要做 `url_citation` → Anthropic citations，**js 这里是空白**，不是参考。它连 observation 都没记，这个「静默」本身还是它自己纪律的一处破口，不要一起抄过来。 |
| **`usage` 不读 `tool_usage`** | 全仓无 | 我们若要产 `usage.server_tool_use.web_search_requests`，得自己从上游 `tool_usage.web_search.num_requests` 映射。js 无参考。 |

### 9.3 三条要带走的结论

1. **关联用 `output_index`，永远不要用 `id`。** js 在这一点上做对了，而且它做对的理由与我们的 id 实测无关（它是为 ledger 的 per-(item, kind) 唯一性设计的），所以它的正确性是稳的。
2. **`id` 不要出现在任何会被客户端存进历史的产物里。** js 违反了这一条（`server-tool.ts:26`）。它的 `encrypted-content-400` 事故是同一失败模式的另一个实例：**把一个只在本次响应内有意义的值写进会被回传的正文**。
3. **js 对 web search 的整体实现深度是「请求侧一行映射表 + 响应侧一行降级文本」。** 原生块对、citations、续接、usage、能力门、流式子事件——**六项全无**。这既意味着没什么可抄，也意味着我们做出来的东西没有对照实现可校验，得靠自己的上游实测。

---

## 10. 明确「未找到」的部分

以下问题我搜过但**确实没有答案**，不用推理填补：

| 未找到的东西 | 搜过的关键词 / 路径 |
|---|---|
| 任何按模型能力决定「能否用 hosted web search」的请求侧门 | `rg 'supportsWebSearch\|supports_web_search\|web_search' src/lib/models/ src/lib/codex*`；`translateTools` 全部调用点；`prepareResponsesDirectWire`；`responsesLeg.requestRewrites` |
| GHC `/models` 目录里 `supports.web_search` 的真实样本 | `rg '"web_search"' --glob '*.json' .`（全仓 JSON，含 `exp/`）——命中全是 Anthropic 块类型或 Responses 工具类型，无 capability flag |
| `response.web_search_call.in_progress` / `.searching` / `.completed` 的任何引用 | `rg 'web_search_call\.(in_progress\|searching\|completed)\|response\.web_search_call' src/ tests/` → exit 1，零命中 |
| `url_citation` 字面量 | `rg -i 'url_citation' src/ tests/` → 零命中（`annotation` 的命中都是别的语境） |
| `responses-output-item` / `responses-item-reference` 的构造点 | `rg 'responses-output-item\|responses-item-reference' src/` → 只有 `core/types.ts` 内的注释与类型定义 |
| `tool_usage` / `web_search_requests` 的消费点 | `rg 'tool_usage\|web_search_requests\|num_requests' src/ --glob '!*.test.ts'` → 零命中 |
| 从降级文本里回解析 `web_search` id 的代码 | `rg 'web_search:' src/`；`webSearchCallToText` 的全部引用 |

---

## 11. 附：本次调查用到的一手证据文件（被调查仓库内）

- `exp/anthropic-responses-direct/probe-c-websearch.json` —— **真实上游响应捕获**。含 `web_search_call` item 的完整形状（`action`/`id`/`status`/`type` 四键，与我们的实测一致）、上游对裸 `{type:"web_search"}` 的字段展开回显、`tool_usage.web_search.num_requests: 1`。**这份是仓库里最有价值的一手材料。**
- `exp/encrypted-content-400/README.md` —— 合成 `web_search_tool_result{encrypted_content:""}` 导致会话级 400 的事故复盘（含 empty / null / placeholder / error-shaped 四种形态的上游响应对照表）。
- `exp/web-search-double-hop-live/README.md` —— 已退役的双跳方案的唯一一次真实端到端跑通记录（用 gpt-5.5 作搜索后端）。**注意它是退役方案的证据，不是当前实现的证据。**
- `exp/web-search-double-hop-live/reject-probe.ts` —— 原生 `web_search_20250305` 打 `/responses` 的 400 措辞门控探针。**全仓找不到它的运行结果记录**，RFC 里也未回填结论。
- `tests/fixtures/anthropic-messages/server-tool/{request,response}.json` —— 手写夹具（非录制）。
