# copilot-api-js 的 hosted web search 处理（重点：响应侧）

- 调查日期：2026-08-21
- 参考项目：`/home/xp/src/copilot-api-js`，HEAD `1f7bf8957`（2026-08-20T19:30:45+00:00）
- 调查方式：`rg` 全仓搜 `web_search` / `server_tool_use` / `web_search_tool_result` / `url_citation` / `annotation` / `citation` / `web_search_call` / `tool_usage`，逐条读调用链；未运行该项目的任何代码，未发真实上游请求
- 证据强度声明：文中「代码里是这样」的断言都给了 `文件:行号`，强度足以据此做设计决策；「它没做 X」的断言给了具体的搜索覆盖面，强度同样足以据此决策；标注为「未验证 / 推测」的部分不得用于决策

---

## 0. 一句话结论（先给结果，理由在后面）

**参考项目的响应侧做法和我们现在一样，也是一行纯文本，而且它的文本比我们的还差**（它把上游那个几百字符的加密 `id` 也拼进了文本里）。它没有产出 Anthropic 原生的 `server_tool_use` + `web_search_tool_result` 块对，而且**是明确、成文、带负样本测试守住的拒绝**，不是遗漏。

所以「参考项目里有更好的做法」这个提示，**在已落地的代码里不成立**。真正有价值的东西在别处：它留下了一份被取代但未删的设计（合成 `server_tool_use` + text，不合成 result 块）、一份实测的上游数据清单（哪些字段真的有、哪些真的没有）、以及一条它自己也没实装的续接（continuation）义务。这三样我们可以抄，详见第 6 节。

---

## 1. 响应侧：拿到上游 `web_search_call` 之后产出什么

### 1.1 唯一的渲染函数

`/home/xp/src/copilot-api-js/src/lib/translation/from-ir/anthropic/server-tool.ts:24-27`：

```ts
export function webSearchCallToText(item: Extract<ResponsesOutputItem, { type: "web_search_call" }>): string {
  const query = item.action?.query ?? item.action?.queries?.join(", ") ?? "(unknown query)"
  return `[web_search: "${query}"] (id: ${item.id}, status: ${item.status})`
}
```

同文件 `35-42` 是分发闸门 `degradedServerToolText`：**只有当 item 的来源协议是 `openai-responses` 且 `sourcePayload.type === "web_search_call"` 时才降级为文本**；来源是 Anthropic 的 server tool 走原生 round-trip。判据键在「来源协议」而不是「item 类型」，这一点该文件的注释（`10-11` 行）明确说了理由：两边 kind 相同，只有来源能说明目标协议能不能原生表达它。

单元测试给出的确切字符串（`tests/translation/legacy-direct/responses-to-anthropic.unit.test.ts:145`）：

```
[web_search: "official Bun runtime website"] (id: ws1, status: completed)
```

`id` 在测试 fixture 里是 `ws1`，但**真实上游的 `id` 是一段约 500 字符的加密 blob**——见实测样本 `exp/anthropic-responses-direct/probe-c-websearch.json` 里那个 `web_search_call` item 的 `id`（`tLN4lWdG/P9ALdQBTt4SUZRJyJ40A4n/…`，几百字符）。也就是说这个渲染在生产上会给客户端塞一行几百字符的密文噪声。这是**我们已有做法（`[web_search] <query>`，不带 id）严格优于它**的一点。

### 1.2 非流式路径

活路径（IR 桥）：`src/lib/translation/from-ir/anthropic/response-body.ts:154-173`

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
        content.push({ type: item.kind === "function-call" ? "tool_use" : "server_tool_use", … })
```

即：Responses 来源 → 一个 `text` 块 + 一条 degradation observation（进 History/诊断，不上 wire）。落到 `else` 分支去发 `server_tool_use` 的，只有**来源是 Anthropic**的 server tool。

被取代但仍在仓里的直接桥：`src/lib/translation/legacy-direct/responses-to-anthropic.ts:203-211`，同一行为，注释直接点名 R-NO-REVIVE。

### 1.3 流式（SSE）路径

活路径：`src/lib/translation/from-ir/anthropic/response-stream.ts:251-269`。触发点是 IR 的 `finish-item` 转换（不是 `content_block_delta` 累积）：

```ts
          case "finish-item": {
            …
            if (item.kind === "server-tool-call" || item.kind === "degraded-text") {
              const text = degradedServerToolText(item) ?? item.authoritativeOutput ?? …
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
```

**三帧一次性发完并自闭合**：`content_block_start`（空 text）→ 一个 `text_delta` 装全文 → `content_block_stop`。发之前先 `closeOpenBlock` 关掉当前打开的块，发完不把它记为 `openBlock`，下一个块自己重新开。原因写在 `254-255` 行注释：server tool 是整块到达的（上游没有中间 delta），所以没有增量可发。

被取代的直接桥同形：`src/lib/translation/legacy-direct/responses-to-anthropic-stream.ts:296-319`，挂在 `response.output_item.done` 上。

### 1.4 负样本测试（说明这是刻意的，不是漏掉）

- `tests/translation/legacy-direct/responses-to-anthropic-stream.unit.test.ts:242-247`：断言整条 SSE wire 里**不出现** `web_search_tool_result` 字符串，也不出现 `encrypted_content`。
- 同文件 `249-259`：对抗样本——即使把一个假的 `encrypted_content` 塞进 `web_search_call.action` 里，输出也不得携带它（注释写「不发明 → 不搬运」）。
- `tests/translation/legacy-direct/responses-to-anthropic.unit.test.ts:150-174`：非流式的同两条。
- `…:176-193`：`status:"incomplete"` 且**没有 `action`** 的变体渲染成 `(unknown query)` 而不抛异常；只有 `action.queries` 数组形态的用 `", "` join。

---

## 2. 为什么不产原生块对（它的成文理由，以及对我们是否成立）

### 2.1 它的理由链

1. **物理约束**：真实上游的 `web_search_call` item 只有 `action / id / status / type` 四个键，**没有 `encrypted_content`**。实测记录在 `exp/anthropic-responses-direct/FINDINGS.md:42`；类型定义处也写死了这条（`src/types/api/openai-responses.ts:218-249` 的 docstring：「There is NO `encrypted_content` field … this is the physical constraint that forces R-NO-REVIVE's response-side degradation」）。
2. **Anthropic 侧 400 墙**：Anthropic `web_search_tool_result` 的每个结果项要求真实非空的 `encrypted_content`。四种伪造形态全部实测被拒（`exp/encrypted-content-400/README.md`）：`""` 400、`"redacted"` 占位 400、`null` 400、字段缺失 400；只有 error-shaped（`web_search_tool_result_error`）返 200。
3. 因此合成结果块 = 必然填假密文 = 撞墙。RFC 把这条立为红线：`docs/format-translation/2026-08-08-anthropic-responses-semantic-bridge.md:704`「红线：永不合成 Anthropic `web_search_tool_result`；该 block 需要代理无法伪造的上游签名内容」。
4. 历史包袱佐证：这个墙正是它上一代「web_search 双跳」死掉的原因之一——双跳合成的块里硬编码 `encrypted_content: ""`，客户端存进历史、下一轮回传、上游 400，整个会话被 baked 死（`exp/encrypted-content-400/README.md` 的「根因」段）。

### 2.2 这条理由对我们**不完全成立**（重要）

`exp/encrypted-content-400` 的 400 是 **GHC 的 Anthropic 端点 `/v1/messages`** 在校验请求里回传的历史块时报的。copilot-api-js 有一条「Anthropic 客户端 → Anthropic 上游」的腿，所以它必须怕这堵墙。

**我们没有那条腿**：ghc-api-proxy-py 的上游只有 OpenAI Responses。客户端回传的 `web_search_tool_result` 会在我们的请求侧被翻译或丢弃，永远不会以 Anthropic 块的形态送到任何 Anthropic 端点去挨校验。

所以对我们而言，「合成 `web_search_tool_result` 会 400」这个具体机制**不适用**。但另外两个风险仍在，而且**我在本次调查中没有验证过它们**（标注为未验证，不得据此下结论）：

- Claude Code 客户端自己对 `web_search_tool_result` 块的解析与回传行为（它是否要求 `encrypted_content`、是否会把块原样存进 transcript）。
- 我们自己的请求侧在下一轮读到这些块时的行为。

这两点要落地「产原生块对」之前必须先测。

---

## 3. 上游到底给了什么可用数据

实测样本：`exp/anthropic-responses-direct/probe-c-websearch.json`（真实 GHC `/responses`，gpt-5.5-2026-04-23，`tools:[{type:"web_search"}]`）。逐字段清点：

| 字段 | 实测值 | 参考项目有没有读 |
|---|---|---|
| `output[].type == "web_search_call"` 的 `action.query` | `"official Bun runtime website"` | **读了**，进渲染文本 |
| 同上 `action.queries` | `["official Bun runtime website"]` | **读了**，`", "` join 作 fallback |
| 同上 `id` | 约 500 字符加密 blob | **读了**，直接拼进文本（见 1.1 的批评） |
| 同上 `status` | `"completed"` | **读了**，拼进文本 |
| 同上 `encrypted_content` | **字段不存在** | — |
| 搜索结果的标题 / URL / 摘要 | **上游根本没给**——`web_search_call` item 里没有任何结果载荷 | — |
| `output[].content[].annotations`（message item 上） | 实测样本里是 **`[]` 空数组** | **没读**（见下） |
| `tool_usage.web_search.num_requests` | `1` | **没读**（见下） |

### 3.1 「没读 annotations」——确认方式

`rg -ni "annotation" src/` 的全部命中已逐条核过，分四类，没有第五类：

1. 写入侧常量 `annotations: []`：`from-ir/openai-responses/response-stream.ts:136,282,290`、`from-ir/openai-responses/response-body.ts:148`、`legacy-direct/anthropic-to-responses.ts:147`、`legacy-direct/anthropic-to-responses-stream.ts:333,475,483`、`legacy-direct/responses-to-cc-request.ts:178,314,405,414`。全部是 **Anthropic/CC → Responses 方向**造一个空数组，不是读。
2. 类型定义：`src/types/api/openai-responses.ts:168`（`annotations: Array<unknown>`，注意是 `unknown`，没有结构）、`:385-396`（`OutputTextAnnotationAddedEvent`，`annotation: unknown`）。
3. `copilot_annotations` / `ip_code_citations`：`src/types/api/anthropic.ts:174-181`、`src/lib/anthropic/stream-accumulator.ts:369-370` 等。这是 **Anthropic 上游的 IP 代码引用**特性，和 web search 引用无关，别混淆。
4. Responses → Responses 透传 codec：`src/lib/codec/openai-responses/buffered-merge-reducer.ts:20,27` 把 `response.output_text.annotation.added` 列入「item-summary 模式下要丢弃的中间子帧」——**是丢弃，不是消费**。丢弃理由是 SDK accumulator 的坑（annotation.added 不能和 content_part.added 分家，否则 SDK 抛异常）。

**结论：Responses → Anthropic 方向零处读取 `annotations`。** 这是「它没做」，不是「我没找到」。

### 3.2 `url_citation` 的四处命中全是手写 fixture

`rg -l url_citation` 只有四个文件，其中两个是文档，两个是测试：

- `tests/responses/fixtures/buffered-merge-blocks.ts:165`
- `tests/e2e-client/responses-nodelta.probe.it.test.ts:317`

两处都是同一行手写常量 `{ type: "url_citation", start_index: 0, end_index: 5, url: "https://example.com", title: "Example" }`，用途是构造「annotation.added 缺了 content_part.added 会让 SDK 抛异常」的对抗样本，**和 web search 引用没有关系**。

按我们项目 `.claude/rules/00-development-workflow.md` 的「上游行为是录下来的，不是想出来的」原则：**这个 `url_citation` 形状是一份 belief，不是 GHC 的实测记录**。参考项目里**没有任何一份 GHC 真实返回的、annotations 非空的样本**。

### 3.3 `tool_usage` 完全没读

`rg -n "tool_usage" src/` **零命中**（唯一的非 exp 命中在 `docs/codex-support/spec.md`）。`num_requests` 从未进入任何 usage 映射、诊断或渲染。

### 3.4 一句要紧的话

> **2026-08-21 更正：本节原来的全称否定是错的，已被一手样本推翻。** 原文写「上游没有把搜索结果的标题、URL、摘要放在任何字段里」「真的没东西可读」。实际是：上游**会**给 `url_citation`，挂在 `output[].content[].annotations[]` 上，字段为 `{type, url, title, start_index, end_index}`。本仓库 `exp/260820-websearch-probe/raw/B7-*.txt` 就是一份带真实 citation 的非流式一手样本（2026-08-20 真实调用）。流式路径同样会发 `response.output_text.annotation.added`，且 `content_part.done` 与 `output_item.done` 各带一份完整数组。取证过程见 [`260821-responses-websearch-citation-evidence.md`](260821-responses-websearch-citation-evidence.md)。
>
> 错因值得记：本节的证据是**一份 `annotations` 为空的样本**，而那次查询是「今天几号」这类模型搜了却不引用的问题。**空数组被当成了「该字段不承载内容」，而它只说明这一次没有内容。** 本节自己在 §6.3 第 8 条里写下了这个边界，却仍在标题句用了全称否定——边界写在别处，救不了正文里那句话。

仍然成立的部分：**搜索结果不在 `web_search_call` item 里**（该 item 恒为 `action`／`id`／`status`／`type` 四个键），也没有摘要、没有 `page_age`、没有 `encrypted_content`。所以 `web_search_tool_result` 仍然造不出完整忠实的一份，spec §5.3「省略而非伪造 + 记 `DEGRADE`」的裁决不变——只是原料比本节原先认定的充足得多。

---

## 4. 请求侧完整映射表

活路径：`src/lib/pipeline/hub-translate.ts:157-162` 的 `anthropicToResponsesBridge` → `src/lib/translation/bridges/anthropic-to-responses-request-via-ir.ts:80-81` → `src/lib/translation/from-ir/openai-responses/parameters.ts`。

### 4.1 tools 映射

`parameters.ts:58-65` 的映射表：

```ts
export const SERVER_TOOL_MAPPING: ReadonlyArray<{ anthropicPrefix: string; responsesType: ResponsesBuiltinToolType }> = [
  { anthropicPrefix: "web_search_", responsesType: "web_search" },
  // web_fetch / code_execution have NO probed Responses-upstream request shape yet … Falls through to strip+warn.
]
```

`parameters.ts:92-114` 的 `translateTools`：

| 客户端声明 | 产出 | 说明 |
|---|---|---|
| 自定义 tool（无 `type`） | `{type:"function", name, description, parameters: input_schema}` | 透传 |
| `web_search_20250305`（前缀匹配 `web_search_`） | **`{type:"web_search"}` 裸形态** | 注意：不是 `web_search_preview`，也不带 schema。`parameters.ts:59-61` 注释说明这是实测选的形态 |
| `web_fetch_*` / `code_execution_*` | **丢弃 + warn** | 表里没有条目，未探针过 |
| `memory_*` / `computer_*` / `text_editor_*` / `bash_*` | **丢弃 + warn** | 这些其实是 client-executed 内置工具，被 `isApiDefinedToolType` 误分类进来，落到同一降级路径 |

丢弃时的日志：`parameters.ts:97-100`，`dropping native server tool "<name>" (type: <type>) — no Responses-builtin mapping`。

**从 Anthropic 侧被丢掉的字段**：`max_uses`、`allowed_domains`、`blocked_domains`、`user_location`、`cache_control` 等 `web_search_20250305` 的全部配置项——因为映射产出的是硬编码的 `{type:"web_search"}`，源工具对象的其他键一个都没进去。这一点参考项目的注释没提，是我读代码得出的（`parameters.ts:103-106`：`if (namedChoice.type !== "function") { out.push(namedChoice); continue }`，`namedChoice` 就是 `{type:"web_search"}`）。

### 4.2 tool_choice 映射

`parameters.ts:125-156`：

| Anthropic | Responses |
|---|---|
| `auto` | `"auto"` |
| `any` | `"required"`；若翻译后 tools 为空则**省略整个 tool_choice** |
| `none` | `"none"` |
| `tool` + name | 查原始 tools 找到该工具 → 走 `translateNamedToolChoice`：自定义工具 → `{type:"function", name}`；映射过的 server tool → `{type:"web_search"}`。若该声明已被 strip 掉（`translatedTools` 里找不到），**省略 tool_choice** 而不是发一个悬空的 named choice |
| 未知变体 | fallback `"auto"` |

### 4.3 能力门

**没有模型能力门**。`rg -n "web_search|server_tool" src/lib/models/capabilities.ts src/lib/models/capabilities-mapper.ts` 零命中。不管上游模型支不支持，`{type:"web_search"}` 都会照发。

失败是**反应式**兜底的（见 4.4），不是前置门控的。

### 4.4 反应式自愈网（历史遗留，与 Responses 上游腿无关）

`src/lib/request/strategies/web-search-not-found-retry.ts`：匹配上游 400 `Tool '<x>' not found in provided tools` → 把模型记进 `serverToolDowngrade` 学习账本（持久化）→ 用 `context.originalPayload`（**必须是 pre-sanitize 基线，否则整条重写链会被二次应用**）重跑 sanitize 链 → 重试。

但这条链挂在 **Anthropic 上游 codec** 上（`src/lib/codec/anthropic/*` 调 `runAnthropicPayloadRewrites`），不在 Anthropic→Responses 那条腿上。对我们的拓扑参考价值有限，但那个「学习账本 + 从原始 payload 重跑」的重试形态本身值得记住。

---

## 5. 历史回放（客户端把上一轮的块传回来）

### 5.1 我们关心的方向：Anthropic 客户端 → Responses 上游

`src/lib/translation/to-ir/anthropic/request-read.ts:42-48` 认块：

```ts
    case "server_tool_use": { return "server-tool-use" }
    default: { return type.endsWith("_tool_result") ? "server-tool-result" : undefined }
```

然后 `src/lib/translation/from-ir/openai-responses/request-write.ts:252-260`：

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

**整块丢弃**，只留一条 observation。既不还原成 Responses 的 `web_search_call`，也不降级成文本。

这在它自己的体系里是自洽的：因为响应侧发给客户端的本来就是纯 `text` 块，客户端回传的也是 `text`，走正常文本路径，压根不会产生 `server_tool_use` token。这条分支只有在**客户端自己发原生 Anthropic server tool**（实测 0 流量）时才会走到。

### 5.2 它设计了、但**没有实装**的续接义务

RFC v2 §7（`docs/format-translation/2026-08-08-anthropic-responses-semantic-bridge.md:706-719`）加了一条硬约束：展示面降级**不授权**丢弃续接状态。原文 `:717`：

> 把 `web_search_call` 渲染成带 correlation ID 的可读 text 是**展示面的合法降级**，但它**不得同时删除** Responses 侧的 opaque id 或权威 source item——否则下一轮回到 Responses 上游时，该 server-tool 的续接状态已不可恢复。

配套类型已经写好了（`src/lib/translation/core/types.ts:114-130`）：

```ts
export type ResponsesServerToolItemType = "web_search_call"

export type ContinuationRecord =
  | Readonly<{ kind: "claude-signature"; opaque: string }>
  | Readonly<{ kind: "responses-encrypted"; opaque: string }>
  | Readonly<{ kind: "responses-item-reference"; ref: … }>
  | Readonly<{ kind: "responses-output-item"; item: … }>
```

而且探针跑过（`:124` 的注释，2026-08-11，`exp/responses-server-tool-continuation/`）：完整 item 与裸 `{type,id}` 回送 Responses 上游都接受，`{type:"item_reference",id}` 对 `web_search_call` **404**；但**伪造的短 id 也被接受**，所以接受性不能用来区分真引用和编造的，因此保留完整 item 作默认。

**然而 `ContinuationRecord` 的后两个臂在 `src/` 里零构造点。** 我搜 `rg -n '"carrier"' src/`，只有两处，都是 reasoning：

- `to-ir/anthropic/response-wire.ts:246` → `{ kind: "claude-signature", opaque }`
- `to-ir/openai-responses/response-wire.ts:227` → `{ kind: "responses-encrypted", opaque }`

而 Responses 解码器给 server-tool-call 判的 continuation 是（`to-ir/openai-responses/response-wire.ts:224-229`）：

```ts
  const dispositionFor = (opaque: string | undefined, kind: ItemKind): ItemDisposition => {
    const continuation: ContinuationDisposition =
      kind === "drop" ? { kind: "none" }
      : opaque !== undefined ? { kind: "carrier", record: { kind: "responses-encrypted", opaque } }
      : { kind: "none" }
```

`web_search_call` 没有 `encrypted_content`，`opaque` 恒为 `undefined`，所以判 **`{kind:"none"}`**——而 RFC `:478` 明确写了「对源为 Responses 的 server-tool item，其取值只能是 `carrier` 或带具名 reason 的 `rejected`」。**代码违反了自己的 RFC**，且是静默违反（`none` 对别的 item 合法，没有守卫能抓）。

好消息是原始 item **在 IR 内部是保住了的**：`to-ir/openai-responses/response-wire.ts:255` 对 server-tool-call 存了 `sourcePayload: sourceItem`（完整 item）。丢的只是「把它送出去、下一轮再收回来」这一段。

**净效果**：Responses 上游执行了一次 web search，Anthropic 客户端只看到一行文本；下一轮回来，那次搜索在 Responses 侧的 opaque id 已经不存在了，上游无法把它当成同一次会话的一部分继续。这是参考项目**已知、已成文、但未修复**的缺口。

### 5.3 另一条腿（Anthropic 上游）的历史回放处理——技法可借鉴

`src/lib/anthropic/sanitize/rewrite-server-tool-blocks.ts`。当上游是 GHC 的 Anthropic 端点时，历史里的 `server_tool_use` + `web_search_tool_result` 对会被「downgrade」：

- `server_tool_use` → 普通 `tool_use`（id 保留）
- 配对的 `*_tool_result` → 普通 `tool_result`，并且**必须搬到一条新插入的 `user` 消息里**（`:18-25` 注释：`tool_result` 只能在 user 消息，原地降级会造出 assistant-role 的 `tool_result`，把一个 400 换成另一个 400）
- result 的结构化 content 被 stringify 成文本（`:70-94`）：

```ts
    const header = query ? `Web search results for query: "${query}"` : "Web search results"
    return { text: lines.length > 0 ? [header, "", ...lines].join("\n") : header, isError: false }
```

每行形如 `1. <title> - <url>`。error-shaped 的走 `Web search failed: <error_code>` 且 `isError: true`。

这是全仓**唯一一处把搜索结果渲染成人可读文本**的实现，虽然它服务的是另一条腿，但格式本身可以直接抄。

---

## 6. 结论：要做得比「一行文本」更好，能抄什么、什么它也没解决

### 6.1 可以直接抄的（有实测支撑）

1. **请求侧的裸 `{type:"web_search"}` 与前缀映射表**（`parameters.ts:58-73`）。表驱动、按 `web_search_` 前缀匹配、未映射的 strip+warn。我们如果还没有这张表，照抄形状即可，成本极低。
2. **`tool_choice` 的联动规则**（`parameters.ts:125-156`）：声明被 strip 时同步省略 named choice；`any` + 零工具时省略整个 `tool_choice`。这两条是能直接换来 400 的细节。
3. **`action` 缺失的诚实降级**：`status:"incomplete"` 的 `web_search_call` 可能完全没有 `action`（实测，gpt-5.6-sol，`FINDINGS.md:43`）。必须写成 `(unknown query)`，不能无条件解引用 `action`。
4. **搜索结果 → 文本的渲染格式**（`rewrite-server-tool-blocks.ts:70-94`）：`Web search results for query: "<q>"` + 空行 + `N. <title> - <url>`。
5. **别把上游的 `id` 拼进给客户端看的文本**——这是**反向**教训，参考项目在这里做错了（真实 id 是 500 字符密文）。我们现在的 `[web_search] <query>` 已经比它好，**不要为了对齐它而退化**。

### 6.2 值得抄的「设计」，但它自己没实装

6. **续接（continuation）与展示（presentation）分成两个独立平面**（RFC §4.1 / §7，类型见 `core/types.ts:114-157`）。核心判断：「展示降级」不等于「续接状态可以丢」。落到我们身上就是：即使给 Claude Code 的是一行文本，我们也应该把上游那个 `web_search_call` 的完整 item（或至少 `{type,id}`）**保存下来并在下一轮回送给 Responses 上游**，让上游知道那次搜索是这轮对话的一部分。

    实测支撑（`core/types.ts:124`，2026-08-11）：完整 item 与裸 `{type,id}` 回送都被接受；`{type:"item_reference", id}` 对 `web_search_call` 返 404，不可用。

    参考项目**只写了类型没写实现**（第 5.2 节的证据）。我们要做就得自己实现，抄的是判断不是代码。

    载体问题需要单独裁决：我们没有 Responses `previous_response_id` 式的服务端状态，要把这个 item 带过一轮 Anthropic wire，得有个隐藏载体（它对 reasoning 用的是塞进 `thinking.signature` 的哨兵封装，`from-ir/anthropic/response-body.ts:141-146`）。这条路对 server-tool item 可不可行，**参考项目没验过，我也没验**。

7. **被取代的 plan-4 里的中间方案**（`docs/format-translation/2026-08-06-responses-anthropic-semantic-bridge/plan-4-web-search.md:39,102-105`，状态标记为「已被取代，不执行」）：产出 **synthetic `server_tool_use` + 文本 commentary**，但**不产** `web_search_tool_result`。它的 E2E 验收条款写得很具体（`:103`）：断言 Claude Code 内部的 `searchCount > 0`、query-update 事件正确，而 `data.results` 只含 commentary 字符串、不含 `{tool_use_id, content:[{title,url}]}` 结构化条目。

    **这是「比一行文本更好」的唯一具体候选**：`server_tool_use` 块能让客户端知道「这轮模型确实搜了、搜了什么」，可能触发客户端的搜索计数与 UI，而不必伪造带签名的结果块。参考项目从未实施它（Task 4.2/4.6 全是未勾选的 checkbox，文档头部标注 `[hard] 已被取代`），所以**它的可行性没有任何实证**——尤其是「Claude Code 收到孤立的 `server_tool_use` 而没有配对的 `web_search_tool_result` 会怎样」这一条，是纯未验证。要采纳必须先做 PoC。

### 6.3 它自己也没解决的

8. ~~**搜索结果内容根本拿不到**~~ — **已推翻，见 §3.4 的更正。** 上游会在 `output[].content[].annotations[]` 给 `url_citation`（`url` + `title` + 起止偏移），一手样本在 `exp/260820-websearch-probe/raw/B7-*.txt`。参考项目零处读取它，这一条从「它做不到」变成了**「它没做，而我们能做」**——这是「比一行文本更好」目前最有原料的方向。
    - 仍缺的是摘要、`page_age` 与 `encrypted_content`，所以块对里的结果项只能是 `{type, url, title}`，且必须记 `DEGRADE`。
    - 两个实现陷阱（取证报告 §5 记录）：`title` 可能是空串；同一 item 的 `item_id` 逐事件全变，`annotation.added` 用的还是明文 `msg_…` id，**关联只能靠 `output_index`**——与 assembler 已经在用的键一致。
9. **`tool_usage.web_search.num_requests` 完全被忽略**（`rg -n "tool_usage" src/` 零命中）。这是一个上游白给的、可靠的搜索次数计数，参考项目没用。我们可以用它做可观测性（日志/footer 里报「本轮上游搜了 N 次」），成本极低。
10. **续接义务未实装**，第 5.2 节已述。

### 6.4 我的主观倾向（供裁决，不是结论）

按 ROI 排序，我建议的顺序是：**9（读 `num_requests` 做可观测性，几行代码）→ 8 的探针（测 annotations 到底空不空）→ 6（续接状态保存）→ 7（synthetic `server_tool_use`，需 PoC）**。

理由：7 是最像「原生」的方案，但它的收益完全取决于 Claude Code 对孤立 `server_tool_use` 的反应，而那是未验证的；8 的探针成本低、且它的结果直接决定 7 值不值得做（如果 annotations 非空，7 就能变成真正的块对而不只是半个）。先做便宜且能改变后续决策的那两项。

---

## 附：本次调查覆盖到的关键文件（绝对路径）

响应侧：
- `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/anthropic/server-tool.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/anthropic/response-body.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/anthropic/response-stream.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/legacy-direct/responses-to-anthropic.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/legacy-direct/responses-to-anthropic-stream.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/to-ir/openai-responses/response-wire.ts`

请求侧与回放：
- `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/openai-responses/parameters.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/bridges/anthropic-to-responses-request-via-ir.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/to-ir/anthropic/request-read.ts`
- `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/openai-responses/request-write.ts`
- `/home/xp/src/copilot-api-js/src/lib/anthropic/sanitize/rewrite-server-tool-blocks.ts`
- `/home/xp/src/copilot-api-js/src/lib/request/strategies/web-search-not-found-retry.ts`

契约与类型：
- `/home/xp/src/copilot-api-js/src/lib/translation/core/types.ts`
- `/home/xp/src/copilot-api-js/src/types/api/openai-responses.ts`
- `/home/xp/src/copilot-api-js/src/lib/pipeline/hub-translate.ts`

文档与实测证据：
- `/home/xp/src/copilot-api-js/docs/decisions/2026-07-13-server-tool-positioning-and-web-search-retirement.md`
- `/home/xp/src/copilot-api-js/docs/format-translation/2026-08-08-anthropic-responses-semantic-bridge.md`（§6.1 / §7）
- `/home/xp/src/copilot-api-js/docs/format-translation/2026-08-06-responses-anthropic-semantic-bridge/plan-4-web-search.md`（已被取代）
- `/home/xp/src/copilot-api-js/docs/format-translation/effective-decisions-by-path.md`（R-NO-REVIVE 表，`:94`）
- `/home/xp/src/copilot-api-js/docs/tool-use.md`
- `/home/xp/src/copilot-api-js/exp/anthropic-responses-direct/FINDINGS.md`
- `/home/xp/src/copilot-api-js/exp/anthropic-responses-direct/probe-c-websearch.json`（真实上游响应）
- `/home/xp/src/copilot-api-js/exp/encrypted-content-400/README.md`
- `/home/xp/src/copilot-api-js/exp/web-search-double-hop-live/README.md`

测试（作为行为断言的证据）：
- `/home/xp/src/copilot-api-js/tests/translation/legacy-direct/responses-to-anthropic.unit.test.ts`
- `/home/xp/src/copilot-api-js/tests/translation/legacy-direct/responses-to-anthropic-stream.unit.test.ts`
