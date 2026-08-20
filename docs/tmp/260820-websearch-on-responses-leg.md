# Anthropic 客户端 web search 经 Responses 上游（GPT 模型）真正执行 —— 完整能力合同

调查日期 2026-08-20｜调查员：leaf executor，只读参考仓库，未做任何修改。

**锚点**

| 仓库 | HEAD | 状态 |
|---|---|---|
| `/home/xp/src/copilot-api-js` | `6209cb510` | 工作树有未提交改动，但全部是 `docs/` / `exp/` / 少量 test，未触及本报告引用的 `src/` 文件 |
| `/home/xp/src/ghc-api-proxy-py` | `f5c2e9f` | 本仓 |
| `refs/vscode-copilot-chat` | 只读参考 | — |

**前置事实（任务给定，已核实一致，不重新论证）**：生产 400 `The use of the web search tool is not supported.` 来自 Copilot 的 Anthropic Messages 端点；`/responses` + `{type:"web_search"}` 在 gpt-5.5 上 HTTP 200 且原生执行搜索；用户已裁决按上游能力分流。

**术语**：本报告说「块级交付」不说「流式渲染」。`web_search_call` 是唯一一种 item 与 block 天然重合的类型。

---

## 一、请求侧

### 1.1 工具声明映射：只映射 `type`，所有子字段静默丢弃

权威表 `SERVER_TOOL_MAPPING`，`src/lib/translation/from-ir/openai-responses/parameters.ts:58-65`：

```ts
export const SERVER_TOOL_MAPPING: ReadonlyArray<{ anthropicPrefix: string; responsesType: ResponsesBuiltinToolType }> = [
  { anthropicPrefix: "web_search_", responsesType: "web_search" },
]
```

`translateTools`（同文件 `:92-114`）对非 function 的分支只做一件事：

```ts
if (namedChoice.type !== "function") {
  out.push(namedChoice)   // namedChoice === { type: "web_search" }
  continue
}
```

即 Anthropic 的 `{"type":"web_search_20250305","name":"web_search","max_uses":5,"allowed_domains":[...],"blocked_domains":[...],"user_location":{...},"cache_control":{...}}` 出去时变成**光秃秃的 `{"type":"web_search"}`**。

**这里有一个必须点名的缺陷**：`dropWarn` 只在整个工具无映射时触发（`:97-101`）。子字段的丢弃**没有任何 observation、没有任何 warn**——`max_uses` / `allowed_domains` / `blocked_domains` / `user_location` 全部无声蒸发。按本项目 `never-swallow-errors` 与 `richest-context-flow` 的口径，这条不应照抄。

**上游到底认哪些子字段？** 一手证据来自 probe-c 的 200 响应体里 `tools[]` 的回显（`exp/anthropic-responses-direct/probe-c-websearch.json`，gpt-5.5-2026-04-23，2026-07-14）——发出去的是裸 `{type:"web_search"}`，上游**补默认值后原样回显**：

```json
"tools": [{"type": "web_search", "return_token_budget": "default", "search_content_types": ["text"], "search_context_size": "medium", "user_location": {"type": "approximate", "city": null, "country": "US", "region": null, "timezone": null}}]
```

由此可读出的映射机会与判断：

| Anthropic 字段 | Responses 对应物 | 判断 | 证据权重 |
|---|---|---|---|
| `user_location` `{type:"approximate",city,region,country,timezone}` | `user_location` `{type:"approximate",city,country,region,timezone}` | 形状几乎逐字对应，**极可能 1:1 可写** | 回显字段名与值形状是一手的；**「可写」是推断，未探针** |
| `max_uses` | 无同义物。`return_token_budget` 是 token 预算不是次数 | 映射不了 | — |
| `allowed_domains` / `blocked_domains` | 回显里没有任何域名过滤字段 | 映射不了 | — |
| （无） | `search_context_size: "low"\|"medium"\|"high"?` | 上游独有旋钮，Anthropic 没有对应项 | 只观测到 `"medium"` 一个值 |
| （无） | `search_content_types: ["text"]` | 同上 | 只观测到一个值 |
| `cache_control` | — | Anthropic 侧块级缓存标记，Responses 无 | 桥在块级已剥（`anthropic-to-responses-request-via-ir.ts:85`） |

**映射不了的怎么处理**：目前是静默丢。建议我方改为 observation + 一条 degradation（`allowed_domains`/`blocked_domains` 尤其要报——用户要求限域而我们悄悄放开限制，是行为改变，不是无害降级）。

**落到 strip+warn 的那一类**（`parameters.ts:97-101`）：`isApiDefinedToolType`（`src/lib/anthropic/message-tools.ts:344-356`）认的前缀共 10 个——`web_search_` / `web_fetch_` / `code_execution_` / `text_editor_` / `computer_` / `bash_` / `advisor_` / `agent_toolset_` / `memory_` / `tool_search_`。
除 `web_search_` 外**全部被剥掉 + warn**。

> ⚠️ **这是过度剥离，别照抄。** 后 7 个是 **client-executed** builtin（`text_editor` / `computer` / `bash` / `memory` / `tool_search` 等，产的是普通 `tool_use` + `caller:{type:"direct"}`，由最终客户端执行，永不产 `server_tool_use`——见 `exp/server-tool-web-fetch-poc/README.md` 的分类表与姊妹探针 `exp/server-tool-memory-probe/`）。它们本可以降级成普通 function tool 透传，剥掉是纯损失。Claude Code 实际会发 `memory_20250818` 与 `tool_search_*`。copilot-api-js 自己在注释里也承认这是「被 `isApiDefinedToolType` 误分类」（`parameters.ts:47-48`），但没有修。

### 1.2 `tool_choice`

`translateToolChoice`，`parameters.ts:125-156`：

| Anthropic | Responses | 备注 |
|---|---|---|
| `{type:"auto"}` | `"auto"` | |
| `{type:"any"}` | `"required"` | 仅当译出的 tools 非空，否则 `undefined` |
| `{type:"none"}` | `"none"` | |
| `{type:"tool",name:"web_search"}` | `{type:"web_search"}` | 走 `translateNamedToolChoice`（`:78-82`）：按 name 找回原声明 → `isApiDefinedToolType` → `mapServerToolType` |
| `{type:"tool"}` 但声明已被剥 | `undefined`（整条省略） | 可用性回检 `:146-149`，避免发出悬空引用 |
| `disable_parallel_tool_use` | 未映射 | switch 里没有；`parallel_tool_calls` 在 payload 构造里也根本不设 |

类型上 `ResponsesToolChoice` 允许 builtin 对象形态（`src/types/api/openai-responses.ts:123`）。

> **`{type:"web_search"}` 作为 tool_choice 从未对上游探针过。** 所有 web_search 实测（probe-c、C0.4 五形态）用的都是 `tool_choice:"auto"`（probe-c 响应体里 `"tool_choice":"auto"`）。**要用就先探针**，别当已知。

### 1.3 配套请求字段

桥实际发出的 payload 就这些（`src/lib/translation/bridges/anthropic-to-responses-request-via-ir.ts:88-105`）：
`model, input, instructions?, max_output_tokens, temperature?, top_p?, stream?, reasoning?, tools?, tool_choice?, user?`

| 字段 | 现状 | 结论 |
|---|---|---|
| **`include`** | 类型里有（`openai-responses.ts:151`），**全仓无任何写入点**（`rg 'include' bridges/ from-ir/openai-responses/` 零命中） | **`web_search_call.action.sources` 从未被请求过**。它是否被 GHC 支持、支持后 `action` 里会多出什么，**完全未知**。这是我方若想拿到来源清单的第一个待探针项 |
| **`tool_usage`** | **不是请求字段，是响应字段**。全仓 `rg tool_usage src/` **零命中**——copilot-api-js 从不读它 | 一手可见：probe-c 响应体 `"tool_usage":{"image_gen":{...},"web_search":{"num_requests":1}}`；我方 cassette `tests/cassettes/anthropic_to_responses_stream.json` 的 `response.created` 里也带 `"web_search":{"num_requests":0}`。**这是一个真实存在、上游一直在发、双方都没用的搜索计数信号**，可直接用于 footer/日志 |
| **`store`** | 该桥不设。只有反向腿与自己发出的 Responses 响应体里写 `store:false` | probe-c 响应体没有 `store`，但有 `"prompt_cache_retention":"24h"`。本项目不用 `previous_response_id`（`responses-to-anthropic-request-via-ir.ts:46` 明列为有意丢弃），故 `store` 与 web search 无观测到的相互作用 |
| **`reasoning`** | `translateThinkingToReasoning`（`parameters.ts:169-184`）→ `{effort, summary:"auto"}`，受 `modelSupportsReasoningEffort` 白名单门控 | **与 web_search 共存无碍**：probe-c 的 output 顺序是 `[reasoning, web_search_call, message]`——模型先推理再搜索再作答，同一个 200 里两者都在。未观测到任何互斥或额外约束 |

---

## 二、响应侧（核心）

### 2.1 `web_search_call` item 的真实形状

**两次独立一手捕获，两个模型，两个日期。**

**捕获 A** —— `exp/anthropic-responses-direct/probe-c-websearch.json`（2026-07-14，gpt-5.5-2026-04-23，非流式全响应体）。item 原文（id 截断标注）：

```json
{"action": {"queries": ["official Bun runtime website"], "query": "official Bun runtime website", "type": "search"},
 "id": "tLN4lWdG/P9ALdQBTt4SUZRJyJ40A4n/fny2YgSCgXtDHFWZynKswHh2ZwiINxopCA7MQzvEGg8+8/idoS8tuzA5DALyvHv84TasLpgCaEEPXax/A4s29RC/CstAZI/nenB1fQpgVaoifzZKou216ol8gNPbBo77LauohzM2R7G+kl8tpJ90h4bfGQR1pJjF5ByybGJweykH3j/gArJGx7b/cy2D0UoS64+iBQrHiu2XstH3+nL8Wwz7lsnBjAw5JC0O/qag67hJNO2qP0C3X3rE+US8RtkgG/7pvLJyenRAV7mWA550XT57bSeycdxuUztXrM4zpbi07NaMFGZFcJV/nyUg4cuw7hSEQD36FcFfAV2iLFespF1VJD/oLPi+9UEtAD3Or9VCGqtrJWNOLw==",
 "status": "completed",
 "type": "web_search_call"}
```

**keys 恰好四个：`action, id, status, type`。确无 `encrypted_content`。**

**捕获 B** —— `exp/responses-server-tool-continuation/`（2026-08-11，gpt-5.6-sol，真 GHC，隔离服务器 45191）。`results.json` 记录 `searchCallKeys: ["action","id","status","type"]`，与 A 一致。`stream-id.json` 记录流式两事件。

**类型建模**（`src/types/api/openai-responses.ts:226-249`）：

```ts
interface ResponsesWebSearchAction { type: string; query?: string; queries?: Array<string>; [key: string]: unknown }
export interface ResponsesWebSearchCallOutput { type: "web_search_call"; id: string; status: "in_progress" | "searching" | "completed" | "failed"; action: ResponsesWebSearchAction }
export interface ResponsesIncompleteWebSearchCallOutput { type: "web_search_call"; id: string; status: "incomplete"; action?: ResponsesWebSearchAction }
```

- `status` 已知取值：`in_progress`（流式 `added` 上实测）、`completed`（实测）、`searching` / `failed`（**建模而已，未实测**）、`incomplete`（实测一次，见下）。
- `action.type` 实测只见过 `"search"`。**没有 action 子类型的穷举清单**，类型故意开放（`type: string` + 索引签名），FINDINGS.md:55 自己写明「没有穷举未来可能新增的 action 类型」。
- `query`（单串）与 `queries`（数组）在唯一样本里**同时存在且内容相同**。消费方不能假定只有其一。
- **`status:"incomplete"` 可能整个缺 `action`**：2026-08-05 在 gpt-5.6-sol 上实测见过（`FINDINGS.md:43`）；**2026-08-11 两次尝试均无法复现**（`README.md:67-71`，含一次强制 6 次搜索的提示词，全是 `completed` 且都带 `action`）。故这是「消费者必须容忍的输入形状」，**不是**频率结论。
- **搜索结果不在 item 里。** 结果落在后续 message 的文本里。probe-c 的 message 文本是 `"https://bun.com/"`，`annotations: []`；2026-08-11 turn-1 的答案带 markdown 内联引用 `([github.com](https://github.com/oven-sh/bun/releases?utm_source=openai))`。即**引用以文本形式到达**，我们手上唯一的完整响应体里 `annotations` 是空数组。类型里建了 `OutputTextAnnotationAddedEvent`（`openai-responses.ts:389-398`，注释提到「gpt-5.5 web_search_preview native citations」），但**全仓没有任何代码读它**（`rg annotations src/` 只有写 `annotations: []` 的构造点）。

### 2.2 翻回 Anthropic：**永远降级为一段文本**，不是完整还原

唯一渲染函数，`src/lib/translation/from-ir/anthropic/server-tool.ts:24-27`：

```ts
export function webSearchCallToText(item: Extract<ResponsesOutputItem, { type: "web_search_call" }>): string {
  const query = item.action?.query ?? item.action?.queries?.join(", ") ?? "(unknown query)"
  return `[web_search: "${query}"] (id: ${item.id}, status: ${item.status})`
}
```

对上面的真实样本，客户端看到的整块文本就是：

```
[web_search: "official Bun runtime website"] (id: tLN4lWdG/P9ALdQBTt4SUZRJ…<424 字符>…OLw==, status: completed)
```

> ⚠️ **注意它把 424 字符的不透明 id 原样塞进面向客户端的文本块**。这是我方要不要照抄的一个明确裁决点：id 是上游可解密的引用（见 §2.4），塞进正文既污染模型上下文、又把一个服务端引用暴露成 prose。建议我方渲染成简短形式，把 id 存在自己的续接载体里而不是正文里。

**分流的判据是「来源协议」，不是 item 种类**（`server-tool.ts:35-42`）：

```ts
export function degradedServerToolText(item: PerOutputItemState): string | undefined {
  if (item.source.identity.protocol !== "openai-responses") return undefined
  ...
}
```

- 来自 **Anthropic 上游**的 `server_tool_use` → **原生还原**成 `server_tool_use` 块（`from-ir/anthropic/response-body.ts:166-172`）；配对的 `*_tool_result` 更是**原块逐字回放**（`:171-177` 用 `item.result.sourcePayload`，to-ir 侧在 `to-ir/anthropic/response-wire.ts:341-350` 把整块存了下来，连原始块类型 `web_search_tool_result` / `code_execution_tool_result` 都保住）。
- 来自 **Responses 上游**的 `web_search_call` → **降级文本 + 一条 `serverToolNotRepresentable` observation**。

四个调用点（同一函数，无副本）：
- 非流式 IR emitter：`src/lib/translation/from-ir/anthropic/response-body.ts:154-165`
- 流式 IR emitter：`src/lib/translation/from-ir/anthropic/response-stream.ts:251-268`
- legacy 直桥非流式：`src/lib/translation/legacy-direct/responses-to-anthropic.ts:203-210`
- legacy 直桥流式：`src/lib/translation/legacy-direct/responses-to-anthropic-stream.ts:301-317`

**为什么不能还原成 `web_search_tool_result`**（R-NO-REVIVE，`responses-to-anthropic.ts:204-207`）：Anthropic 的 `web_search_tool_result` 块里每个 `web_search_result` 项要求**非空 `encrypted_content`**，GHC 的 Anthropic 腿对空密文直接 400——这是退役的 web_search 双跳踩过的墙（`src/lib/anthropic/sanitize/empty-encrypted-search-result.ts:1-40`、`exp/encrypted-content-400/`）。而 Responses 的 `web_search_call` **根本没有 `encrypted_content` 字段**（§2.1 两次实测）。合成 = 撞墙。

> **对我方的意义**：这条禁令的适用范围要说准。它成立的前提是「合成的结果要回喂给 **Anthropic 上游**」。我方的方向是 Anthropic 客户端 ← Responses 上游，下一轮请求也是发给 **Responses** 上游（§2.4），**不经过 Anthropic 的 `/v1/messages` 校验**。所以「客户端渲染成什么」与「回喂上游合法性」在我方是解耦的——理论上我方可以给客户端渲染一个更富的形态（例如带引用列表的文本，或真的 `web_search_tool_result`），只要保证它不会被原样回喂给 Anthropic 上游。**但这需要我方自己裁决，并且要有能力在请求侧识别并剥掉自己合成的块。** copilot-api-js 因为同一份历史可能被路由到任一上游，才选了最保守的一刀切。

### 2.3 流式生命周期：「whole-item」到底是什么意思

**核实 `/home/xp/src/ghc-api-proxy-py/docs/tmp/upstream-stream-blocks.md:39`（条目 4）的那句「只有 block 切换、web-search whole-item 或最终 `flush()` 才产生 `content_block_stop`」——属实，代码与实测都对得上。**

具体语义，三层：

**(1) 上游侧：这个 item 根本没有 delta 事件。** 一手实测 `stream-id.json`：

| 事件 | `output_index` | `status` | id |
|---|---|---|---|
| `response.output_item.added` | 1 | `in_progress` | 424 字符 `lLdnCxf7U788eEubnOkkI9uV…` |
| `response.output_item.done` | 1 | `completed` | **同一个 id**（`distinctIds: 1`） |

中间**没有** `output_text.delta`、没有 `function_call_arguments.delta`、没有任何 reasoning delta。整个 item 在两个事件里各自完整出现一次。

**(2) 解码侧：必须支持「item 整个到达、从未 `added`」。** `src/lib/translation/to-ir/openai-responses/response-wire.ts:447-452`：

```ts
case "response.output_item.done": {
  if (settled.has(event.output_index)) return []
  // An item can arrive WHOLE, with no `added` and no deltas — a `web_search_call` does exactly
  // that. Returning early here (which this used to do) dropped the entire item on the floor:
  // it never entered the ledger, so no emitter could render it and nothing recorded the loss.
  const opening = open.get(event.output_index) === undefined ? declareItem(event.output_index, event.item) : []
```

**这是记录在案的真实回归，不是假想**：早先的实现在 `done` 时若该 index 没开过就直接 return，结果整个搜索 item 静默消失，且没有任何 observation。我方若照着「先 `added` 开块、delta 累积、`done` 收口」的常规模型写解码器，会重复这个 bug。

**(3) 发射侧：为什么不能逐 delta 发。** 两条理由，一条是物理的一条是语义的：
- 物理上没有 delta 可发——上游只给了两次完整快照（见 (1)）。
- 语义上 Anthropic 侧的目标形态是一段**已经成句的**文本 `[web_search: "..."] (id: ..., status: ...)`，它是从 `action`/`id`/`status` 三个字段**计算**出来的，只有在三者齐备（即 `.done`）时才存在。切成 delta 需要先决定「先发 `[web_search: "` 再发 query」这种毫无意义的切分。

所以发射器在 `finish-item` 一次性吐三帧（`from-ir/anthropic/response-stream.ts:259-266`）：

```ts
out.push(
  anthropicSseFrame({ type: "content_block_start", index, content_block: { type: "text", text: "" } }),
  anthropicSseFrame({ type: "content_block_delta", index, delta: { type: "text_delta", text } }),
  anthropicSseFrame({ type: "content_block_stop", index }),
)
```
且 `openBlock` 保持 undefined（块已自闭），下一块走自己的生命周期（legacy 版在 `-stream.ts:315-316` 有同样的注释）。

**(4) id 稳定性 —— 对我方直接相关的一条。** 我方 `CLAUDE.md` 把「Copilot 在 `output_item.added` 与 `done` 之间改写 item id」列为生产流式缺陷的根源。`stream-id.json` 实测：**`web_search_call` 的 id 在两个事件间不变**，且抓到的 id 回传上游得 200。

> `[hard]` copilot-api-js 自己在 `README.md:63` 明确画界：既有的「GHC 逐事件重新加密 `item.id`」结论是在 **`function_call`** 上测到的（证据涉及 `function_call_arguments.done` 这个 function 专有事件），**不得**据 `web_search_call` 的稳定性放宽 `function_call` 侧的纪律。两者是不同 item 类型，不矛盾。
> 反过来，本条的证据强度也有限：**两个事件、单次运行、单一模型**；未覆盖同一响应里多个 `web_search_call` 并发时各自的 id 行为。

**(5) 对我方块级交付的结论**：`web_search_call` 是唯一一种 **item 与 Anthropic block 天然一一对应**的类型，它不需要缓冲策略——上游给的就已经是块。风险恰好相反：一个只在 `added`+delta 上开块的解码器会**整块丢失**它，且丢得无声。

### 2.4 历史回放：两个方向，完全不对称

**方向 (a)：Anthropic 客户端历史里的 web search 块 → Responses 请求 —— 直接丢弃，只记 observation。**

`src/lib/translation/from-ir/openai-responses/request-write.ts:250-258`：

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

legacy 直桥同样（`legacy-direct/anthropic-to-responses-request.ts:327-328`）。读取侧确实认得它们（`to-ir/anthropic/request-read.ts:42-47`：`server_tool_use` → `server-tool-use`，`*_tool_result` 后缀 → `server-tool-result`），位置也保住了，但写出侧没有形态可落。

**实际链路是这样闭合的**：turn N 的搜索在我方 Anthropic wire 上变成一个**文本块**（§2.2），turn N+1 客户端把它当普通文本回传，于是它作为普通文本回放。provenance 只以散文形式幸存，**没有任何 call id 回到上游**。

**方向 (b)：Responses 来源的 server-tool 状态 → Responses 请求（真正的续接载体）—— 契约已定义、上游已实测、代码未实现。**

类型在 `src/lib/translation/core/types.ts:119-131`：

```ts
export type ResponsesServerToolItemType = "web_search_call"
export type ContinuationRecord =
  | Readonly<{ kind: "claude-signature"; opaque: string }>
  | Readonly<{ kind: "responses-encrypted"; opaque: string }>
  | Readonly<{ kind: "responses-item-reference"; ref: Readonly<{ type: ResponsesServerToolItemType; id: string }> }>
  | Readonly<{ kind: "responses-output-item"; item: Readonly<{ type: ResponsesServerToolItemType }> & Readonly<Record<string, unknown>> }>
```

`rg 'responses-output-item|responses-item-reference' src/ tests/` 的结果：**只有 `tests/translation/ledger-terminal.unit.test.ts:281,300` 两处**，`src/` 里除类型定义外零生产使用点。即**没有任何 emitter 会铸造这种 record**。这是一个有实测背书、但尚未接线的类型级契约。

**上游实测（`exp/responses-server-tool-continuation/`，2026-08-11，gpt-5.6-sol，真 GHC，隔离服务器 45191，4141 未动）**——turn 1 拿真 `web_search_call`，turn 2 **不回放 turn-1 的 message**（否则答案就在正文里，观测量失去判别力）：

| 变体 | HTTP | 答案 |
|---|---|---|
| A 完整 item 原样回传 | **200** | `NO_CONTEXT` |
| B 最小 `{type,id}` | **200** | `NO_CONTEXT` |
| C `{type:"item_reference", id}` | **404** `not_found` | — |
| D 完整 item + id 篡改一个字符（负控） | **400** `Invalid 'input[1].id': string too long. Expected a string with maximum length 64, but got a string with length 424 instead.` | — |
| E 完全省略该 item（基线） | **200** | `NO_CONTEXT` |

**机制**（`mechanism.json`，同日补测）：上游对该 id **做解密**。解密成功 → 当服务端不透明引用，不受 64 字符长度规则约束；解密失败 → 退回普通 item-id 规则，撞 64 上限而 400。所以 D 报的是「超长」而不是「无效引用」——翻一个字符即失败，证明它确实在解密。**但**一个明显短的伪造 id `ws_short_id_1` 走「合法普通 id」那条路，**静默 200**。跨模型回放（gpt-5.6-sol → gpt-5.5）**200**。

**必须逐字保留的东西**：**只有 `id`**，且必须 byte-exact（D 的单字符翻转即 400）。**没有 encrypted content 要保**——这个 item 压根没有那个字段，`id` 本身就是唯一的不透明载荷。

**三个不能忽略的诚实边界**（探针 README §四.3、§六自己写的）：
1. **A / B / E 三者答案完全相同（都是 `NO_CONTEXT`）。** 回传 `web_search_call` **并没有把搜索结果带回上下文**——因为这个 item 从来只有 `action` 与 `id`，结果一直在 message 文本里。**它的续接价值是 provenance / 顺序，不是可恢复的结果数据。**
2. **「上游接受」不构成续接有效的证据**：伪造短 id 也 200，所以 200 无判别力，不能据此收窄形态。故默认保留「完整 item」（唯一保全了我们看不见的那部分的形态）。
3. `responses-item-reference` 对 `web_search_call` **不可用**（404）。该 record kind 留在联合里是为将来别的 server tool。

**未证明的**：id 的时效（数分钟/数小时后是否仍可解密，未测）；多 `web_search_call` 并发时的 id 行为；每变体只跑一次，`NO_CONTEXT` 是单次观测。

**反向补充（我方大概率也会撞到）**：Anthropic 上游产的 `server_tool_use{web_search}` 若要发往 **Responses 客户端**，`from-ir/openai-responses/response-body.ts:220-236` 会把它压成 `{type:"web_search_call", id, status: completed|incomplete}`——注意**丢掉 `action`**，配对的 `*_tool_result` 则只记 observation 不发（`:250-260`，因为 Responses 把结果折进 call item 自身，发兄弟项等于发明一个没有读者的 item）。

---

## 三、证据强度逐条标注

| # | 结论 | 证据 | 权重 |
|---|---|---|---|
| 1 | `/responses` + `{type:"web_search"}` → 200，上游原生执行搜索 | `probe-c-websearch.json`（gpt-5.5，2026-07-14）+ `results.json` turn1（gpt-5.6-sol，2026-08-11） | **一手，双模型双日期 —— 强到可以据此动手** |
| 2 | `web_search_call` keys 恰为 `action/id/status/type`，**无 `encrypted_content`** | 同上两份，独立复现 | **一手，独立重复 —— 强到可以据此动手** |
| 3 | 上游把裸工具展开为 `{return_token_budget, search_content_types, search_context_size, user_location}` | probe-c 响应体 `tools[]` 回显 | **回显形状一手；「这些字段可在请求里写」是推断，动手前必须探针** |
| 4 | `status:"incomplete"` 可能整个缺 `action` | 2026-08-05 单次观测（gpt-5.6-sol）；2026-08-11 两次尝试**明确不可复现** | **足以要求消费者容忍这种输入形状；不构成任何频率或条件结论** |
| 5 | 流式生命周期 = `added` + `done` 两事件、无 delta、id 稳定 | `stream-id.json`，单次运行、单模型、两事件 | **足以据此设计解码器；不足以推广到其他 item 类型、不足以推广到并发多搜索** |
| 6 | 续接五形态 A–E 的接受性与解密机制 | `results.json` + `mechanism.json`，真 GHC | **一手；每变体各跑一次，单模型单账号** |
| 7 | Anthropic→Responses 请求侧丢弃 server-tool 块 | 仅代码（`request-write.ts:250-258`） | **code-as-written。没有任何真实流量走过这条路** |
| 8 | 降级文本渲染 | 代码 + 手写 fixture 单测（`tests/translation/anthropic-to-responses-via-ir.it.test.ts:150-166`） | **code-as-written + 手写 mock。从未在真实 Anthropic 客户端的 wire 上见过** |
| 9 | `tool_choice: {type:"web_search"}` 被上游接受 | **无** | **纯推断（只有类型建模）。依赖前必须探针** |
| 10 | `include: ["web_search_call.action.sources"]` 的行为 | **无** —— 该字段全仓从未被写入 | **完全未知，包括 GHC 是否支持该字段本身** |
| 11 | 引用 / `annotations` 的承载方式 | probe-c 里 `annotations: []`；2026-08-11 答案里有 markdown 内联引用 | **一个空样本 + 一个散文样本。不要在 `annotations` 上建东西** |
| 12 | `tool_usage.web_search.num_requests` 真实存在 | probe-c 响应体（值 1）+ **我方自己的 cassette**（值 0） | **一手，双来源 —— 可以直接用** |

### 我方是否有真实的 `web_search_call` 响应样本？—— **没有。**

- `tests/cassettes/anthropic_to_responses_stream.json`、`tests/cassettes/history_responses_stream.json`：**`web_search_call` 出现 0 次**。两份里 `web_search` 各出现 3 次，全部是响应信封里的 `"tool_usage":{...,"web_search":{"num_requests":0}}`。
- `tests/unit/` 里的四处 `web_search` 全是手写 stub：`test_responses_anthropic_nonstream.py:270` 是 `{"type":"web_search_call","id":"ws_123"}`（**注意：连 `status` 和 `action` 都没有，与真实形状不符**）；`test_anthropic_response_validation.py:35-45` 是手写的 Anthropic 侧 `server_tool_use`+`web_search_tool_result`。
- **生产 history DB 全扫**（gzip 解压后按字面量 `web_search_call` 搜索）：

| DB | objects | 命中 |
|---|---|---|
| `history-v3-20260815-183721.db` | 8,023 | 0 |
| `history-v3-20260816-160151.db` | 9,458 | 0 |
| `history-v3-20260817-050754.db` | 5,461 | 0 |
| `history-v3-20260818-044224.db` | 9,820 | 0 |
| `history-v3-260811.db` | 1,661,173 | 0 |
| **合计** | **1,694,395** | **0** |

未扫：`history-v3-260807.db`（19 GB）、`history-v3-260809.db`（14 GB）、`history-v3.db`（4.2 GB）——成本原因，且它们都早于相关工作。**这不影响结论方向**：生产上 Anthropic 客户端从未把 web_search 送到 Responses 上游（该桥本身就不在生产主路径），所以自然流量里不会有。

**结论**：**唯一存在的真实 `web_search_call` 样本就是 `copilot-api-js/exp/` 下的那两份 JSON。** 我方若要 cassette，必须**自己录**（带凭据、真实调用），不能从 history 派生（`from_history.py` 在这里无米可炊）。

---

## 四、模型边界

`refs/available_models.json`（40 个模型）里所有 `capabilities.supports` 键的并集恰为：

```
adaptive_thinking, dimensions, max_thinking_budget, min_thinking_budget,
parallel_tool_calls, reasoning_effort, streaming, structured_outputs, tool_calls, vision
```

**没有任何 web search 相关能力位。** 目录**回答不了**「这个模型支不支持 web search」。唯一可用的判据是 `supported_endpoints` 是否含 `/responses`：

| 含 `/responses` | 不含 |
|---|---|
| `gpt-5.3-codex`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.5`, `gpt-5.6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5-mini` | 全部 `claude-*`（只有 `/v1/messages` + `/chat/completions`）、全部 `gpt-4*` / `gpt-3.5*`（`supported_endpoints` 字段缺失） |

Claude 系不广告 `/responses` —— 这正是生产 400 的根因，与前置事实一致。

**边界的诚实说法**：`/responses` 是**必要条件，未证明充分**。实测过的只有 `gpt-5.5` 与 `gpt-5.6-sol` 两个。`gpt-5.3-codex`（codex 专用）与 `gpt-5-mini` 尤其可疑，未测。

> ⚠️ **一个别照抄的陷阱**：`src/lib/codex-assembly.ts:70` 写着 `supportsWebSearch: supports?.web_search === true`。我们手上的任何目录都没有 `web_search` 这个键，所以**这个标志恒为 false**。它不是能力 oracle，是一段悬空代码。

---

## 五、其他 server tool 在 Responses 上游的情况

| 工具 | Responses 上游状态 | 证据 |
|---|---|---|
| `web_search` | **原生支持**，映射为 `{type:"web_search"}` | 一手实测，见 §一/§二 |
| `web_fetch` | **Anthropic 腿实测 400**：`{"error":{"message":"rejected tool(s): web_fetch","code":"invalid_request_body"}}`（2026-07-12，individual 账号，`api.githubcopilot.com`，claude-sonnet-4.5→sonnet-5）。**`/responses` 腿从未探针过。** 映射表**有意留空**并注明「no probed Responses-upstream request shape yet — omitted until probed, rather than guessed」（`parameters.ts:63-64`），落 strip+warn | `exp/server-tool-web-fetch-poc/README.md:126`、`docs/todo/deferred-backlog.md:393` |
| `code_execution` | **任何腿都从未探针过**，落 strip+warn | — |
| `file_search` / `code_interpreter` | 在我们的 Responses builtin 类型联合里（`openai-responses.ts:100`），但**不在 `SERVER_TOOL_MAPPING` 里**，也不在 `ResponsesServerToolItemType` 里（只有 `web_search_call`）。无任何证据 | — |

**两条 GHC 拒绝措辞不同，且自愈网只认其一**：

- Anthropic 腿 web_search：`The use of the web search tool is not supported.` / `unsupported_value`
- web_fetch：`rejected tool(s): web_fetch` / `invalid_request_body`

`SERVER_TOOL_REJECTION_TABLE`（`src/lib/request/strategies/server-tool-rejection-retry.ts:58-60`）**只有一行**，只匹配前者：

```ts
export const SERVER_TOOL_REJECTION_TABLE: ReadonlyArray<{ pattern: RegExp; typePrefix: string }> = [
  { pattern: /the use of the web search tool is not supported/i, typePrefix: "web_search_" },
]
```

所以 `web_fetch` / `code_execution` 被 400 时**不会被反应式预剥、直接硬失败**（`docs/todo/deferred-backlog.md:394` 已核实）。我方若做反应式自愈，措辞表至少要两行。

**参考：VS Code 官方扩展怎么做的**（`refs/vscode-copilot-chat`）——两条腿两种做法，都不是我们要的：
- **对 Copilot 的 `/responses`**：`src/extension/externalAgents/node/oaiLanguageModelServer.ts:134-141` —— 无条件过滤掉**任何** `type` 以 `web_search` 开头的工具，只打一条 warn。粗暴一刀切，不分模型。
- **对 Anthropic BYOK（直连 Anthropic，非 Copilot）**：`src/extension/byok/vscode-node/anthropicProvider.ts:199-230` 主动注入 `{name:"web_search", type:"web_search_20250305"}`；`:585-690` 完整重建 `web_search_tool_result` + `web_search_result` + `web_search_result_location` 引用。**即 Anthropic 原生的完整处理它是有的，只是从不对 Copilot 的 Responses 端点用。**

---

## 六、给我方的落点（判断，非既定裁决）

1. **请求侧可以直接开工**：按 `supported_endpoints` 含 `/responses` 分流，把 `web_search_*` 映射成 `{type:"web_search"}`。证据 #1/#2 足够强。
2. **子字段不要静默丢**。`allowed_domains`/`blocked_domains` 被丢弃会**放宽**用户明确要求的限制，这是行为改变，必须报 degradation。`user_location` 形状对得上，值得单独探针一次（成本很低）。
3. **响应侧的降级形态是我方自己的裁决点，不要照抄。** R-NO-REVIVE 的约束根子在「合成块会被回喂给 Anthropic 上游」，而我方下一轮同样发往 Responses，这个约束在我方**不自动成立**。但要走更富的形态，得先想清楚请求侧怎么识别并剥掉自己合成的块。
4. **424 字符的 id 不该进正文**。存进我方续接载体，正文只留可读摘要。
5. **解码器必须支持「item 在 `done` 上整个到达、从未 `added`」**，否则整块静默丢失（copilot-api-js 真踩过）。
6. **`tool_usage.web_search.num_requests` 是白捡的**：真实存在、双来源一手、双方都没用。适合直接进 footer / 日志。
7. **三件事动手前必须探针**：`tool_choice` 的 builtin 对象形态；`include` 是否被 GHC 支持及支持后 `action` 多出什么；`web_fetch` 在 `/responses` 腿的行为（现有 400 是 Anthropic 腿的，不能挪用）。
8. **cassette 只能自己录**。history 派生这条路在 web search 上是死的（169 万对象零命中）。
