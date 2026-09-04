# `copilot-api-js` 如何处理空 text 块（`text content blocks must be non-empty`）

调查日期：2026-08-20
被调查仓库：`/home/xp/src/copilot-api-js`（只读，未做任何修改）
被调查仓库 HEAD：`6209cb51004f0cf0f65024e17d64649c7c6cb737`（`docs(tmp): 收尾终端报告`，Thu Aug 20 05:48:44 2026 +0000）
工作树状态：脏（大量 `M` / `??`，主要在 `docs/`、`exp/`、`tests/`；`src/lib/anthropic/sanitize/` 下无未提交改动，本报告引用的源码行即 HEAD 内容）

---

## 0. 结论摘要（先看这个）

| 问题 | 答案 | 权重 |
|---|---|---|
| 有没有针对空 text 块的清洗？ | **有**，且是无条件的终末 pass | 强，源码直读 + 实跑验证 |
| 判据 | `block.text.trim() !== ""`（**trim 后判空**，不是 `=== ""`） | 强，逐字引用 |
| 删除还是占位替换？ | **删除该块**。请求侧从不插入占位文本 | 强 |
| 删空后 `content` 变空数组怎么办？ | **不管**。会原样发出 `content: []`——这是参考实现的一个真实缺口 | 强，已用它自己的函数实跑复现 |
| 会不会破坏 user/assistant 交替？ | 该 pass 不删整条 message，所以**不制造交替破坏**；但它也不修复由此产生的空 message | 强 |
| 作用范围 | `messages` 全部角色（user + assistant）**和** `system` 数组，都做 | 强 |
| 预防式还是反应式？ | **纯预防式**（出站前清洗）。`strategies/` 里**零**针对该 400 的反应式重试 | 强，判据性 grep 见 §5 |
| 知不知道根因？ | 知道。文档明确记录：**Claude Code 会在自己的两个 thinking 块之间发空 text 块**，而且我方**响应侧**也会产出空 text 块 | 强 |
| 响应产出侧有没有防空块守卫？ | **反过来**——它**故意主动插入** `{type:"text",text:""}`。这正是下一轮空块的来源之一 | 强，逐字引用 |

**对我们最有价值的三条**：

1. 判据必须是 `trim()`，不能只判 `=== ""`（`" "` 也会被 Anthropic 拒）。
2. 参考实现有一个**已知未修的洞**：删空后留下 `content: []`。我们不该照抄这个缺陷。
3. **空块很可能是我们自己造的**——参考实现在响应侧无内容时主动补一个空 text 块，客户端下一轮原样回传。查我们自己的响应产出路径。

---

## 1. 清洗代码在哪、逐字是什么

### 1.1 核心函数（消息侧）

`src/lib/anthropic/sanitize/content-blocks.ts:9-27`

```ts
/**
 * Final pass: remove any empty/whitespace-only text content blocks from Anthropic messages.
 * This is a safety net that catches empty blocks regardless of how they were produced.
 */
export function filterEmptyAnthropicTextBlocks(messages: Array<MessageParam>): Array<MessageParam> {
  return messages.map((msg) => {
    if (typeof msg.content === "string") return msg

    const filtered = msg.content.filter((block) => {
      if (block.type === "text" && "text" in block) {
        return block.text.trim() !== ""
      }
      return true
    })

    if (filtered.length === msg.content.length) return msg
    return { ...msg, content: filtered } as MessageParam
  })
}
```

### 1.2 核心函数（system 侧）

`src/lib/anthropic/sanitize/content-blocks.ts:29-35`

```ts
/**
 * Final pass: remove any empty/whitespace-only text blocks from Anthropic system prompt.
 */
export function filterEmptySystemTextBlocks(system: MessagesPayload["system"]): MessagesPayload["system"] {
  if (!system || typeof system === "string") return system
  return system.filter((block) => block.text.trim() !== "")
}
```

### 1.3 调用点（无条件）

`src/lib/anthropic/sanitize/result.ts:53-54`，在 `finalizeAnthropicSanitization` 内，**没有任何配置开关或条件**：

```ts
  const finalMessages = filterEmptyAnthropicTextBlocks(messages)
  const finalSystem = filterEmptySystemTextBlocks(system)
```

### 1.4 OpenAI Chat Completions 侧的对应清洗

`src/lib/openai/sanitize.ts:149-158`，同判据（`trim()`），同做法（删块）：

```ts
  const allMessages = [...sanitizedSystemMessages, ...messages].map((msg) => {
    if (!Array.isArray(msg.content)) return msg
    const filtered = msg.content.filter((part) => {
      if (part.type === "text") return part.text.trim() !== ""
      return true
    })
    if (filtered.length === msg.content.length) return msg
    emptyTextPartsRemoved += msg.content.length - filtered.length
    return { ...msg, content: filtered }
  })
```

注意它同样**不检查 `filtered.length === 0`**。

### 1.5 另一个相关但不同的函数

`src/lib/anthropic/sanitize/text-blocks.ts:8-32` 的 `sanitizeTextBlocksInArray` 也会丢弃变空的块，但它的语义是「剥掉 `<system-reminder>` 标签后如果变空就丢弃」，判据是 JS truthiness（`if (sanitized)`，即 `=== ""` 才丢，`" "` 会保留），**不是**空块清洗本身。它由 `removeAnthropicSystemReminders` / `stripReadToolResultTags` 使用，是上游 pass，最终仍由 §1.1 兜底。

---

## 2. 清洗的确切语义（逐条回答）

### 2.1 判据：`text.trim() === ""`，不是 `text === ""`

`content-blocks.ts:19` 逐字：`return block.text.trim() !== ""`。

纯空白（`" "`、`"\n"`）同样被删。这一点被集成测试显式锁定，`tests/anthropic/message-sanitizer.it.test.ts:1243-1267`：

```ts
    test("preserve policy: empty text blocks ARE dropped while the thinking block stays verbatim", () => {
      // Old `immutable` kept the empty text block to preserve array length. Empirically,
      // signatures are self-contained and don't bind to position — so empty text blocks
      // around a thinking block are safely dropped. The thinking block itself is untouched.
      setStateForTests({ thinkingBlockMessagePolicy: "preserve" })

      const thinkingBlock = { type: "thinking" as const, thinking: "reasoning", signature: "sig_2" }
      const inputAssistant = {
        role: "assistant" as const,
        content: [thinkingBlock, { type: "text" as const, text: "   " }, { type: "text" as const, text: "visible" }],
      }
```

并且有一条独立证据说明**为什么 trim 是必需的**——纯空白块即使留着上游也不认。`docs/spec/2026-07-07-thinking-signature-quarantine.md:47`：

> **分隔符须非空非纯空白**：实测空 `""`/空格 `" "` text 块被上游 strip 掉、thinking 又相邻仍 400（`pb_sep_empty/space`），非空标记 `"[thinking continued]"` → 200（`pb_sep_marker`）

这是它实测出来的：**上游自己也会 strip 掉纯空白 text 块**，所以纯空白块既不能当内容也不能当结构分隔符。

### 2.2 删块，不替换占位

请求侧是纯删除，`filter` 出去，无任何占位文本字面量。

唯一会**插入**非空占位文本的地方是一个语义完全不同的 pass——`repairAssistantBlockLayout`（`src/lib/anthropic/sanitize/assistant-block-layout.ts`），它的目的是修「两个 thinking 块相邻」的布局违规，会插入合成分隔符（历史上的字面量形如 `"[thinking continued]"`）。这不是空块清洗，别混淆。

### 2.3 `content` 变成空数组 → **它不管，直接发出去**

这是本次调查最重要的发现。**权重：强**——不是读代码推断，是用它自己的函数实跑复现的。

顺序事实（`src/lib/anthropic/sanitize/index.ts`）：

- `index.ts:140` 先跑 `processToolBlocks(messages, payload.tools)`
- `index.ts:143` 再跑 `finalizeAnthropicSanitization(...)`，后者在 `result.ts:53` 里跑 `filterEmptyAnthropicTextBlocks`

`processToolBlocks` **确实**有空 message 清理，`src/lib/anthropic/sanitize/tool-blocks.ts:141` 与 `:168` 各一处：

```ts
      if (newContent.length === 0) continue
```

但它跑在空 text 清洗**之前**。空 text 清洗自己（`content-blocks.ts:24-25`）只做：

```ts
    if (filtered.length === msg.content.length) return msg
    return { ...msg, content: filtered } as MessageParam
```

**没有 `filtered.length === 0` 的分支。**

`index.ts:125-128` 的注释显示作者是有意识地利用这个顺序的，但只针对 thinking 块：

```
  // Drop corrupt (unsigned) thinking blocks BEFORE processToolBlocks so its existing
  // empty-message cleanup (content.length === 0 → drop the whole message) handles any
  // message left empty after corrupt-block removal — no extra drop logic needed, no
  // adjacent same-role risk introduced beyond what processToolBlocks already produces.
```

空 text 清洗没享受到这个安排，因为它被刻意放在了**最后**（为了不让后续 pass 重新造出空块）。

**实跑验证**（在 `/home/xp/src/copilot-api-js` 下，`bun -e`，只读该仓库源码、无写入、无网络）：

```
输入:  [{role:"user", content:[{type:"text", text:""}]}, ...]
输出:  [{"role":"user","content":[]}, ...]
```

即一条只含空 text 块的 user message，清洗后变成 `{"role":"user","content":[]}` 并原样保留在 messages 里。

最后一个 pass `repairAssistantBlockLayout`（`assistant-block-layout.ts:175-196`）也救不了：它 `msg.role !== "assistant"` 直接放行；即便是 assistant，空数组既无相邻 thinking、也无 terminal 违规，`:193` 的三条件全 false 直接 `continue`。

**判定：参考实现在这里有一个未修的洞。** Anthropic 会以 `messages: content blocks must be non-empty`（另一条错误）拒绝空 content 数组——这一点该仓自己在别处是知道的，见 `src/lib/translation/from-ir/anthropic/request-write.ts:182`：

```
      // An empty turn is an Anthropic 400 (`content: []` / `content: ""`), so it is skipped rather than
```

以及 `src/lib/translation/legacy-direct/responses-to-anthropic-request.ts:326`：

```
        // would be an Anthropic 400 (content:[] / content:"") — skip it, never emit a well-formed-looking
```

但这两处是**翻译腿**的保护，没有回流到 sanitize 腿。

> **对我们的建议**：删块后必须加 `if (blocks.length === 0)` 分支。参考实现没做，别照抄。

### 2.4 user/assistant 交替顺序

`filterEmptyAnthropicTextBlocks` **不删除整条 message**（它 `map` 而非 `filter`），所以它自己不制造交替破坏。代价就是 §2.3 的空数组。

真正会删整条 message 的是 `processToolBlocks`（`tool-blocks.ts:141`/`:168`），而 `index.ts:126-128` 的注释显示作者评估过这个风险，结论是「不引入超出 `processToolBlocks` 既有产出的相邻同角色风险」——即**它接受可能产生相邻同角色 message，没有做交替修复**。

单独存在一个入口保护 `src/lib/anthropic/message-tool-utils.ts:24-30`，只管开头：

```ts
export function isLegalLeadingUserMessage(msg: MessageParam): boolean {
  if (msg.role !== "user") return false
  if (typeof msg.content === "string") return true
  if (msg.content.length === 0) return false
  // Legal iff at least one block is NOT a tool_result (regular or server).
  return msg.content.some((block) => !isToolResultBlock(block) && !isServerToolResultBlock(block))
}
```

注意 `:27` **确实**把空数组判为非法——但它只被 `ensureAnthropicStartsWithUser` 用于丢弃**开头**的非法 message，中间位置的空数组不受它保护。

### 2.5 作用范围：全角色 + system

- **角色**：`filterEmptyAnthropicTextBlocks` 对 `messages` 里每一条都跑，不区分 user / assistant。
- **system**：`filterEmptySystemTextBlocks`（`content-blocks.ts:32-35`）同判据同做法，在 `result.ts:54` 同步调用。
- **string content**：`typeof msg.content === "string"` 直接 return，**不清洗**。即 `{role:"user", content:""}` 会原样发出。（这是另一个次要缺口，但 Anthropic 对 `content: ""` 也会 400——见 §2.3 引用的两条注释。）

### 2.6 触达范围有一道门（重要）

`src/lib/anthropic/payload-rewrites.ts:117-122`，sanitize 注册为恒真：

```ts
const sanitizeMessages: AnthropicPayloadRewrite = {
  name: "sanitize-messages",
  order: 300,
  appliesTo: () => true,
```

但**外层**有一道端点门，`src/lib/codec/anthropic/request-rewrite-adapter.ts:66`：

```ts
    appliesTo: (env) => env.attempt.targetEndpoint === ENDPOINT.MESSAGES,
```

注释（`:61-65`）：

```
    // Two-axis gate (RFC §3.1 / §7.1): the sanitize chain produces the UPSTREAM Anthropic
    // `/v1/messages` wire, so it gates on the OUTBOUND leg (`targetEndpoint`), not the inbound
    // `clientFormat`. Byte-identical to the prior `clientFormat==="anthropic"` gate in Phase 1
    // (anthropic-direct has both axes co-true; no translation leg exists yet).
```

即：**只有出站到 Anthropic `/v1/messages` 的直连腿跑这条清洗**；翻译到 `/responses` 或 `/chat/completions` 的腿不跑（那些腿有自己的空块保护，见 §2.3 引用）。该仓自己的文档把这条记成已知缺口，`docs/buffered-block-delivery/anchor-allocator/HANDOVER.md:229`：

> **事实**：空 text block 清洗 `filterEmptyAnthropicTextBlocks` 经 `sanitize-messages` 跑在 Anthropic 入站路径上，**但外层有门**——`codec/anthropic/request-rewrite-adapter.ts:65` 的 `appliesTo: (env) => env.targetEndpoint === ENDPOINT.MESSAGES`，故 `@cc` / `@responses` 的 forward translate 腿**不跑这条清洗**，而它同样会产出 gap anchor 空块。

**对我们的直接含义**：我们的主路径是「Anthropic Messages 入 → OpenAI Responses 上游」，在参考实现的分类里属于**翻译腿**，恰恰是它不跑这条清洗的那一类。但我们报的 400 来自 Copilot 的 `/v1/messages` 直通路径，属于它跑清洗的那一类。清洗应该挂在**出站是 Anthropic Messages** 这个轴上，与入站格式无关——这是参考实现明确写下的设计判断，值得直接采纳。

---

## 3. 预防式还是反应式？——纯预防式

**预防式**：出站前无条件清洗，见 §1.3。

**反应式：零命中。** 判据性 grep：

```
$ rg -F --line-number 'text content blocks' src/
src/lib/anthropic/sanitize/content-blocks.ts:10: * Final pass: remove any empty/whitespace-only text content blocks from Anthropic messages.
exit=0
```

唯一命中是那句注释，不是错误匹配逻辑。

`src/lib/request/strategies/` 下 16 个策略文件：

```
adaptive-thinking-rejection-retry.ts   cache-control-subfield-rejection-retry.ts
context-management-retry.ts            deferred-tool-retry.ts
effort-learning-retry.ts               legacy-thinking-retry.ts
network-retry.ts                       reactive-rejection.ts
server-error-retry.ts                  server-tool-rejection-retry.ts
structured-outputs-rejection-retry.ts  system-reject-retry.ts
token-refresh.ts                       tool-field-rejection-retry.ts
unsupported-beta-retry.ts              web-search-not-found-retry.ts
```

无一针对空 text 块。

```
$ rg --line-number 'must be non-empty|content blocks|invalid_request_error' src/lib/request/
src/lib/request/recording.ts:16: * Map Anthropic content blocks to history-friendly format.
```

仅一条无关注释。

反应式基元本身存在（`src/lib/request/strategies/reactive-rejection.ts:33` 的 `createReactiveRejectionStrategy`，形态是「检测特定 400 → 解析能力 token → 写协商缓存 → 补救 → 重试一次」），但**没有任何实例注册到这条错误上**。

**判定**：作者认为这条错误应该在出站前根除，不值得设反应式兜底。理由可推断：这类错误 100% 可在本地判定，反应式重试纯属浪费一个 RTT。**建议我们同样只做预防式。**

---

## 4. 它知不知道空块从哪来？——知道，而且记得很细

### 4.1 原始动机：Anthropic 会拒空 text

`docs/client-keepalive/2026-07-27-keepalive-and-separator/research-separator-options.md:33` 逐字：

> `git blame` 指向 `57b15e61c`，更早引入提交 `461e9557` 的注释明确写着：Anthropic API 会以 `text content blocks must be non-empty` 拒绝空 text，因此它是 original input / sanitization / truncation 后的通用安全网。现有集成测试还明确锁定"preserve thinking 时也删除纯空白 text"：`/home/xp/src/copilot-api-js/tests/anthropic/message-sanitizer.it.test.ts:1243-1267`。

（`461e9557` 与 `57b15e61c` 都是巨型 `update` 提交，commit message 无信息量；`57b15e61c` 是纯 docs 搬迁，真正的 blame 落点在更早的重构里。上面这条文档是该仓自己做的 blame 考古，可信度高于我重跑一遍。）

pickaxe 检索结果（`git log -S'must be non-empty' --oneline`）：`349663ecd`、`18e4aa02e`、`1e3fcd420`——全是大型 `update` / 文档恢复提交，无独立的「修空块」提交。**该清洗从一开始就存在，不是事后补的。**

### 4.2 空块的三个已知来源

**来源 A：Claude Code 在自己的两个 thinking 块之间发空 text 块。**

`881f72abc test(anthropic): guard the empty-text seam that two production 400s came through`（Tue Jul 28 22:38:41 2026）commit message 逐字：

```
The terminal-order file only covered ONE way an earlier pass manufactures adjacent
thinking blocks: processToolBlocks deleting an orphan tool_use. Both production
incidents (req_1785160010003_3754, req_1785276101202_7795) came through the OTHER
one — finalize stripping the empty text block Claude Code puts between its own
thinking blocks — and it makes a different demand on the repair: a real tool_use IS
present, so it must be RESERVED as the terminator (C3) rather than spent as the
separator.
```

事故形状记录在 `docs/client-keepalive/.../research-separator-options.md:25`：

> 项目文档对事故请求 `req_1785160010003_3754` 的客户端形状记录为 `[thinking,text(""),thinking,tool_use]`，sanitizer 后 wire 形状为 `[thinking,tool_use,thinking]`

**注意这条事故的性质**：删空块本身没有引发 `must be non-empty`，反而是**删空块导致两个 thinking 相邻**，触发了另一条 400。所以在该仓的语境里，空块清洗是「必需但有副作用」的。

**来源 B：我方响应侧主动产出空 text 块，客户端下一轮回传。**

见 §5。`research-separator-options.md:11` 逐字：

> 事故导出 entry 中承担 thinking 边界的最终空 text 来自上游响应，经客户端回流后被我方 `filterEmptyAnthropicTextBlocks` 删除，由此制造邻接；它不是 keepalive 自激闭环。

**来源 C（历史，已退役）：empty_text keepalive 载体。**

早期用 `{type:"text",text:""}` 做 keepalive 锚点。已在 `b688ffdf6 feat(keepalive): retire empty-text keepalive as default → bare ping (ADR 2026-07-22 D2)` 退役，并在 `818fee392 feat(anthropic)!: remove the empty_text keepalive carrier` 彻底移除。设计文档 `docs/buffered-block-delivery/keepalive-anchor/spec.md:20` 当时明确把「空 text 块会被我方自己剥掉」当作选它的**理由**：

> 空 text 块收口 known-benign（我方 `filterEmptyAnthropicTextBlocks` 本就剥空 text）→ **无 thinking/tool_use 毒化门控**

**来源 D：上游 SSE 的 `content_block_start` 初值。**

`research-separator-options.md:27` 有一次对生产 4141 的只读抽样：

> 最近 200 条中有 159 条 outbound `/v1/messages`：59 个 `synthetic="keepalive"` 帧全部是 `ping`；59 个 text `content_block_start{text:""}` 全部没有 synthetic 标记，index 分布为 0×11、1×48。本轮还重建了这批 SSE 的最终 text 内容：64 个 text 块全部在后续 delta 中获得非空文本，没有最终空 text。

结论是：**流式 block start 初值为空 ≠ 最终块为空**。这条对我们有直接价值——如果我们在块级聚合时把 `content_block_start` 的空初值当成完整块物化，就会凭空造出空块。**去查我们的块聚合逻辑。**

---

## 5. 响应产出侧：它不但没有守卫，反而**故意插入**空 text 块

这是本次调查第二重要的发现。**权重：强**，逐字引用。

`src/lib/translation/legacy-direct/cc-to-anthropic.ts:145-149`：

```ts
  // Real Anthropic responses ALWAYS carry ≥1 content block (output_tokens is non-zero even for an
  // empty string — SDK docs). An empty upstream completion (all choices empty + no tool_calls, e.g. a
  // content_filter that blocked everything) would otherwise yield `content:[]`, which a client
  // assuming ≥1 block may choke on — degrade to a single empty text block to stay wire-faithful.
  if (content.length === 0) content.push({ type: "text", text: "" } satisfies TextBlockParam)
```

`src/lib/translation/legacy-direct/responses-to-anthropic.ts:221-222`：

```ts
  // Real Anthropic responses ALWAYS carry ≥1 content block (mirrors cc-to-anthropic.ts's same guard).
  if (content.length === 0) content.push({ type: "text", text: "" } satisfies TextBlockParam)
```

**它的推理是**：真实 Anthropic 响应永远至少 1 个块，`content: []` 会噎住客户端，所以退化成一个空 text 块以保持 wire 忠实。

**但这就把问题推给了下一轮**：客户端把这条 assistant message 存进 transcript，下一轮原样回传，然后我方的请求侧清洗把它删掉——如果它恰好夹在两个 thinking 之间，就制造相邻违规（§4.2 来源 B 的完整因果链）；如果它是该 message 的唯一块，就变成 `content: []`（§2.3 的洞）。

它还有第三处相关：`src/lib/anthropic/request-preparation.ts:1246-1248` 的注释显示它**拒绝**了另一种插入空白块的做法：

```
 * When no block can carry the breakpoint (e.g. an all-thinking message), this returns
 * false and the slot is reclaimed for an earlier message. GHC instead pushes a
 * `{text:" "}` placeholder block to host its CacheBreakpoint part; we deliberately skip
 * to avoid injecting whitespace noise (such messages are vanishingly rare in proxied).
```

即 GHC（上游 Copilot 官方实现）会推 `{text:" "}` 占位块，`copilot-api-js` 明确选择不这么做。**这条很有意思：Copilot 自家实现会造纯空白块，而 Anthropic 拒纯空白块。** 如果我们的上游链路里有 GHC 的行为，这是又一个空块来源。

---

## 6. 给我们的落地建议（不是命令，是我的判断）

按优先级：

1. **加请求侧清洗，判据用 `.strip() != ""`**（Python），对齐 `trim()`。作用于 `messages`（全角色）+ `system`。**权重：强**——这是参考实现跑了大半年的生产判据，且有实测支撑（纯空白块上游也拒）。

2. **必须处理清洗后的空 `content`**——参考实现在这里有洞（§2.3，已实跑复现）。三个选项：
   - (a) 丢弃整条 message（会破坏交替，需要额外处理）；
   - (b) 保留一个非空占位块；
   - (c) 只在 message 还剩其他块时删，全空时保留原样让上游拒。

   我倾向 **(a)+ 交替修复**或 **(b)**，具体取决于我们是否已有交替保护。**这是一个真实的分叉，建议交你裁决。**

3. **一并处理 `content: ""`（字符串形式）**——参考实现直接 return 不管（§2.5）。

4. **清洗挂在「出站目标是 Anthropic Messages」这个轴上，不是「入站格式是 Anthropic」**——参考实现明确写下了这个设计判断（§2.6），理由充分：清洗产出的是上游 wire。

5. **不做反应式重试**——参考实现零反应式策略，理由充分（§3）。

6. **查我们自己的响应产出侧**（§5）。两个具体怀疑点：
   - 无内容时是否补了空 text 块？参考实现补了，并且这被它自己的文档认定为下一轮空块的来源之一。
   - 块级聚合时，是否把 `content_block_start` 的空初值当成完整块物化了？参考实现的抽样证明 59 个空 start 全部在后续 delta 中被填满（§4.2 来源 D）。

7. **警惕删空块的副作用**：删掉夹在两个 thinking 之间的空块会制造 thinking 相邻，触发另一条 400。参考实现为此专门写了终末布局修复 pass（`assistant-block-layout.ts`），且它必须跑在空块清洗**之后**（`index.ts:154-162` 有长注释解释为什么）。**如果我们支持 thinking 块透传，这个坑迟早会踩。** 建议现在只记下，不预建。

---

## 7. 我跑过的判据性检索（可复现）

```
$ git -C /home/xp/src/copilot-api-js rev-parse HEAD
6209cb51004f0cf0f65024e17d64649c7c6cb737

$ rg -F --line-number 'text content blocks must be non-empty'    # 全仓
docs/client-keepalive/2026-07-27-keepalive-and-separator/research-separator-options.md:33
exit=0    # 唯一命中在文档，源码零命中

$ rg -F --line-number 'text content blocks' src/
src/lib/anthropic/sanitize/content-blocks.ts:10   # 仅一条注释
exit=0

$ rg --line-number 'must be non-empty|content blocks|invalid_request_error' src/lib/request/
src/lib/request/recording.ts:16                   # 仅一条无关注释
                                                  # → 反应式策略零命中

$ rg --line-number 'filterEmptyAnthropicTextBlocks' -g '!exp/**'
src/lib/anthropic/sanitize/content-blocks.ts:13   # 定义
src/lib/anthropic/sanitize/result.ts:14, :53      # 唯一生产调用点
                                                  # 其余全是 docs/ 引用

$ git log -S'must be non-empty' --oneline
349663ecd 18e4aa02e 1e3fcd420                     # 全是巨型 update/docs 提交

$ rg --line-number 'content\.length === 0|content:\s*\[\]|newContent\.length === 0|filtered\.length === 0' src/
# 21 处命中，其中 tool-blocks.ts:141/:168 是唯一的空 message 丢弃逻辑，
# 且跑在空 text 清洗之前；content-blocks.ts 无任何空数组分支
```

实跑验证（在被调查仓库根目录执行，只读该仓源码，无写入、无网络）：

```
$ bun -e 'const m = await import(".../sanitize/content-blocks.ts"); ...'
输入 [{role:"user", content:[{type:"text",text:""}]}]
输出 [{"role":"user","content":[]}]
```

---

## 8. 本报告的边界

- 我读的是 HEAD `6209cb51` 的源码。该仓工作树是脏的，但 `src/lib/anthropic/sanitize/` 与 `src/lib/translation/legacy-direct/` 下无未提交改动。
- §2.3 的「洞」是我对参考实现的判断，不是它自己的记录。它自己的文档没提这一条。我的证据是源码 + 实跑，我认为**足以据以行动**（即：不要照抄，我们要加空数组分支）。
- 我没有验证 Copilot 的 `/v1/messages` 上游对 `content: []` 的实际拒绝行为——那需要真实调用。参考实现有两条注释断言它会 400（`request-write.ts:182`、`responses-to-anthropic-request.ts:326`），我采信但标为**二手**。
- §4.2 的事故因果链来自该仓自己的 commit message 与文档，我未独立复核那两个 `req_*` 事故记录（它们在生产 history 库里，不在本仓）。**权重：可作为设计参考，不作为断言**。
- 我未调查 `docs/.human-controlled/`（该目录未追踪，且按项目约定属用户亲笔权威）。如果里面有关于空块的裁决，本报告可能与之冲突——建议你自行核对。
