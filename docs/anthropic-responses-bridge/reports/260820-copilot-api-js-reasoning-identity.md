# copilot-api-js 的 reasoning carrier：身份与位置的事实调查

调查对象：`/home/xp/src/copilot-api-js`，只读。检出分支 `master`，HEAD `06c1fec33`（工作树有大量未提交改动，但均不在 `src/lib/anthropic/` 与 `src/lib/translation/` 下 —— `git status --short` 列出的 `M` 文件只涉及 `docs/`、`.gitignore`、`bun.lock`、`tests/pipeline/delivery-adapters.unit.test.ts`）。本文只陈述代码事实，不对本项目提任何设计建议。

## 摘要（每题一句）

1. **Q1 载体格式**：v1 是「前缀 + base64url 裸串」（`copilot-api:synthetic-reasoning:v1:` 装 `encrypted_content`，反向另有 `copilot-api:claude-signature:v1:` 装真 Claude signature）；另存在一个 **v2 结构化信封**（`copilot-api:*:v2:` + base64url(canonical JSON)），但**当前生产写入端全是 v1，v2 只有读取端和测试在用**。
2. **Q2 可扩展性**：v2 解码器**没有精确 key 集合比对**，`isEnvelope` 只做「必需字段存在且类型正确」的检查；末尾那道「重新编码后逐字节相等」的 backstop 只对 **key 顺序与值的可序列化性**敏感，因此**按 canonical（字典序）排列的额外字段能原样通过并被保留** —— 这一点是我从代码与 `safe-stable-stringify` 源码推出的推论，未实测（详见 Q2）。
3. **Q3 item 身份**：**没有任何地方保存上游 reasoning item 的 `id`** —— 不在 carrier 里、不在 IR 里、不在任何 side table 或 session cache 里；重建出的 `reasoning` input item **完全不带 `id` 字段**，而且该项目曾因在 request input item 上伪造 `id` 被上游 400（commit `684761e40`）。
4. **Q4 位置**：位置**纯粹由 Anthropic content block 的到达顺序决定**，没有任何位置信息被编码或存储；`RESPONSES_ORDERING_CONSTRAINTS` 是一个**刻意为空**的数组，即「Responses 侧没有任何需要重排的硬约束」，所以每个 token 保持源序。
5. **Q5 近期动向**：这块在 2026-08-14/15 刚刚大动过（v2 信封落地 + IR 重构 + 「replay 自己的 carrier」修复），**全部在 checked-out 的 `master` 上**，但**没有任何 id 保存或位置保存的迹象**；v2 的 `itemId` 字段是声明了却从未被写入的槽位。
6. **Q6 已知缺陷**：代码与文档明确承认——同一 reasoning item 的 `encrypted_content` 与 **`id` 在 `.added` 与 `.done` 之间就不一样**（实测 blob 1600 vs 1684、id `oh9qJ6Dq…` vs `kDP29WIY…`）；另有 KNOWN-LOSS 测试锁定「多个 reasoning item 塌缩成一个 thinking block、只有最后一个 opaque 存活」；还有非流式 message item 共用同一个 `id` 的未修缺陷。

---

## Q1 载体格式

**v1（生产在用的两个）。** 两个方向各一个 primitive，前缀不同、互不调用：

`/home/xp/src/copilot-api-js/src/lib/anthropic/synthetic-reasoning.ts:32,44-47` —— 正向（Responses 上游 → Anthropic 客户端）：

```ts
export const SYNTHETIC_REASONING_SIGNATURE_PREFIX = "copilot-api:synthetic-reasoning:v1:"
export function buildSyntheticReasoningSignature(encryptedContent?: string): string {
  if (!encryptedContent) return SYNTHETIC_REASONING_SIGNATURE_PREFIX
  return SYNTHETIC_REASONING_SIGNATURE_PREFIX + Buffer.from(encryptedContent, "utf8").toString("base64url")
}
```

解码：同文件 `:59-68` 的 `extractEncryptedReasoning`，`Buffer.from(payload, "base64url").toString("utf8")`。**payload 是裸串，不是 JSON**；`Buffer` 的 `base64url` 编码**不带 `=` padding**。空 payload（裸前缀）是合法形态，表示「这是我们的块但没有可回传状态」，`:38` 还保留了一个更老的无分隔符 sentinel `copilot-api:synthetic-reasoning:v1`（无尾冒号）仍被识别。

`/home/xp/src/copilot-api-js/src/lib/anthropic/claude-signature-carrier.ts:32,40-43` —— 反向（Claude 模型 → Responses 客户端），前缀 `copilot-api:claude-signature:v1:`，同样是 base64url 裸串，装的是真 Anthropic signature，塞进 Responses 的 `encrypted_content`。

**v2（结构化信封，已存在但无生产写入端）。** `/home/xp/src/copilot-api-js/src/lib/anthropic/carrier-v2.ts:47-55`：

```ts
export type CarrierV2Envelope =
  | { v: 2; kind: "claude-signature"; source: CarrierSource; opaque: string }
  | { v: 2; kind: "responses-encrypted"; source: CarrierSource; opaque: string }
  | { v: 2; kind: "ext"; ns: string; source: CarrierSource; opaque: string }
export const CLAUDE_SIGNATURE_V2_PREFIX = "copilot-api:claude-signature:v2:"
export const SYNTHETIC_REASONING_V2_PREFIX = "copilot-api:synthetic-reasoning:v2:"
export const EXT_V2_PREFIX = "copilot-api:ext:v2:"
```

`CarrierSource`（`:28-35`）是 `{ protocol, model, provider?, responseId?, itemId? }`。编码是 `prefix + base64url(safe-stable-stringify(envelope))`（`:163-171`），即 **canonical JSON**（key 字典序）。

**关于「v2 是否在生产中被写出」**：唯一的 `encodeCarrierV2` 调用点在 `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/openai-responses/response-body.ts:166-181`，处在一条三元链的最后一档：

```ts
const carrier =
  deps.stripThinkingSignature === true ? undefined
  : item.opaque === undefined || nativeEncrypted !== undefined ? undefined
  : item.opaque.kind === "claude-signature" ? buildClaudeSignatureCarrier(item.opaque.bytes)
  : encodeCarrierV2({ v: 2, kind: item.opaque.kind, source: { ... }, opaque: item.opaque.bytes })
```

而 `item.opaque` 的类型联合只有两种 kind（`/home/xp/src/copilot-api-js/src/lib/translation/core/types.ts:175`：`{ kind: "claude-signature"; carrierVersion: 2; bytes } | { kind: "responses-encrypted"; carrierVersion: 2; bytes }`），两种都被前面的分支吃掉了 —— `responses-encrypted` 走 `nativeEncrypted` 直出原生字段，`claude-signature` 走 v1。**推论（读类型 + 读分支得出，未运行）：这条 `encodeCarrierV2` 分支在当前类型联合下不可达，v2 事实上没有生产写入端。** 该文件 `:165-168` 的注释自己也说明了同一件事：

> `// v1, not v2, and that is a decision rather than an oversight. v2 adds provenance the decoder could cross-check, but nothing reads it yet, and switching generations changes a client-visible string for a benefit no consumer collects today.`

读取端两代都收：`/home/xp/src/copilot-api-js/src/lib/anthropic/replayable-reasoning.ts:45-54`（`readReplayableReasoning`，先试 v2、检查 `kind !== "responses-encrypted"` 就拒、否则退回 v1）与 `:72-80`（`readReplayableClaudeSignature`，镜像）。

## Q2 可扩展性：v2 解码器是否拒绝未知字段

**没有精确 key 集合比对。** `carrier-v2.ts:116-132` 的 `isEnvelope` 逐条检查必需字段，从不枚举 key 集合：

```ts
function isEnvelope(value: unknown): value is CarrierV2Envelope {
  if (typeof value !== "object" || value === null) return false
  const candidate = value as Record<string, unknown>
  if (candidate.v !== 2) return false
  if (typeof candidate.opaque !== "string") return false
  const kind = candidate.kind
  if (typeof kind !== "string" || !(kind in KIND_BINDING)) return false
  ...
  if (typeof sourceRecord.model !== "string" || sourceRecord.model.length === 0) return false
  return true
}
```

真正把额外字段挡掉的是解码末尾那道 backstop（`:205-208`）：

```ts
  // Round-trip: re-encode and require byte equality with what arrived.
  const reEncoded = encodeCarrierV2(parsed)
  if (reEncoded !== carrier) return undefined
```

**这道检查的判别力边界很关键。** `encodeCarrierV2` 用 `safe-stable-stringify` 序列化 **`parsed` 本身**（含额外字段），而该库默认按字典序排 key（`/home/xp/src/copilot-api-js/node_modules/safe-stable-stringify/index.js:263,462,567` 的 `keys = sort(keys, comparator)`，readme 第 113 行「_Object keys_ are sorted instead of using the insertion order」）。于是：

- 额外字段若以**非 canonical 顺序**到达 → 重编码后 key 顺序变了 → 字节不等 → 拒绝。这正是测试覆盖的那一例（`/home/xp/src/copilot-api-js/tests/anthropic/carrier-v2.unit.test.ts:149-154`，用 `repack()` 走的是 `JSON.stringify`，即插入顺序 `v,kind,source,opaque,unexpected`，非字典序）。
- 额外字段若以 **canonical（字典序）顺序**到达 → 重编码逐字节相同 → **通过**，且 `decodeCarrierV2` 返回的就是那个带额外字段的 `parsed` 对象。

**标注：以上第二条是推论**，由 `isEnvelope` 无 key 集合检查 + `encodeCarrierV2` 序列化 `parsed` 全量 + `safe-stable-stringify` 排序语义三处代码共同推出，**我没有执行任何代码验证**（任务约束禁止在任何位置落任何其他文件，故未做 PoC）。判别力等级：**足以据此判断「v2 不是精确 key 集合模型」，但不足以作为「任意扩展字段一定能通过」的行为承诺** —— 生产者必须自己保证输出 canonical 排序，否则同一个字段有时通过有时被拒。

该测试文件 `:104-109` 自己记录了一次变异测量：把 prefix⟺kind 和 kind⟺protocol 两道检查改坏，整份测试仍全绿；只有把 backstop 改坏才有一例变红。也就是说，**backstop 是这条解码路径上唯一有判别力的检查**。

另外 `ext` kind 的 `opaque` 内容被明确声明为不校验（`carrier-v2.ts:43-45`，测试 `:161-167` 把这一点钉死为「不许后人来『修』成校验」）。

## Q3 item 身份：`id` 有没有被保存

**没有。** 三个层面各查了一遍：

1. **重建出的 item 不带 `id`。** IR 路径 `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/openai-responses/request-write.ts:228-236`：

```ts
        const replayable = readReplayableReasoning((raw as { signature?: unknown }).signature)
        if (replayable !== undefined) {
          input.push({
            type: "reasoning",
            summary: typeof raw.thinking === "string" && raw.thinking.length > 0 ? [{ type: "summary_text", text: raw.thinking }] : [],
            ...(replayable.encryptedContent !== undefined && { encrypted_content: replayable.encryptedContent }),
          } as unknown as ResponsesInputItem)
```

   legacy-direct 路径同形（`/home/xp/src/copilot-api-js/src/lib/translation/legacy-direct/anthropic-to-responses-request.ts:351-359` 的 `reconstructReasoningInputItem`）：只有 `type` / `summary` / 可选 `encrypted_content` 三个键。

2. **IR 根本没收上游 item 的 `id`。** `/home/xp/src/copilot-api-js/src/lib/translation/to-ir/openai-responses/response-wire.ts:195` 的 item key 是 `${deps.segmentId}:item:${index}` —— 由 `output_index` 合成；`:198-204` 的 `SourceRef` 只带 `blockOrOutputIndex`（位置）与 `sourceId`（**response id，不是 item id**）。全文件对 `.id` 的读取只有三处（`:106` response.id、`:239` `str(raw.call_id) || str(raw.id)` 取 call id、`:372` response.id），**没有一处读 reasoning item 的 `id`**。

3. **没有 side table / session cache。** 反证式搜索：`rg -n "reasoningId|reasoning_id|reasoningItemId|lastReasoningId" src` 无命中；`rg -n "encrypted_content" src -l` 列出的 28 个文件逐个看过没有以任何键缓存 item id 的结构；`src/lib/anthropic/` 下的 `new Map|cache` 命中全是工具调用解码与 cache_control，无关。

**输出侧的 id 全是自己合成的**：`from-ir/openai-responses/response-body.ts:197` 与 `response-stream.ts:105` 都是 `${deps.itemId}_reasoning_${n}`，legacy 路径 `anthropic-to-responses-stream.ts:305,379,459` 同样。上游那个 `rs_…` 从进 IR 的第一刻起就不存在了。

**一条强相关的负面经验**：commit `684761e40`（2026-07-21，`fix(responses): omit fabricated function_call item id on request input (upstream 400)`）记录了在 request input item 上伪造 `id` 的后果：

> `400 Invalid 'input[1].id': 'call_...'. Expected an ID that begins with 'fc'.`
> `the item id is never read for matching, round-trip, History, or wire sampling.`

对应地，今天的 `toolUseToFunctionCall`（`/home/xp/src/copilot-api-js/src/lib/translation/from-ir/openai-responses/blocks.ts:31-33`）只发 `call_id`，不发 `id`。**这条证据是关于 `function_call` 的，不是 `reasoning`**；我搜过 `rg -n "rs_" src docs exp tests`，命中全是测试 fixture 的假 id，**没有任何探针测过「给 Responses request 的 reasoning input item 带上 `id` 会怎样」** —— 这个问题在该仓库里是未被回答的。

## Q4 位置：重建的 reasoning item 放在哪

**位置来自 Anthropic content block 的源序，没有任何位置信息被编码或存储。**

读取端 `/home/xp/src/copilot-api-js/src/lib/translation/to-ir/anthropic/request-read.ts:57-93` 给每个 block 一个**全局递增** `ordinal` 和 `messageIndex`（`:7-11` 解释了为什么不用 per-message 编号），连未知 block 也占位（`:79-86`），理由是「丢掉它会静默重排后面所有 token」。

写入端 `/home/xp/src/copilot-api-js/src/lib/translation/from-ir/openai-responses/request-write.ts:63-68`：

```ts
/**
 * Responses' hard ordering constraints on a request. Empty — deliberately, and checked rather than
 * assumed: Responses accepts reasoning, text, function calls and their outputs in source order, so
 * there is nothing here to justify moving a token.
 */
export const RESPONSES_ORDERING_CONSTRAINTS: ReadonlyArray<OrderingConstraint> = []
```

`normalizeTurns(tokens, RESPONSES_ORDERING_CONSTRAINTS)`（`:100`）因此是恒等变换，`reorderings` 恒为空。具体到 reasoning：`case "reasoning"` 先 `flushText()` 再 `input.push(...)`（`:227-236`），也就是**在源序的原位插入**，把它前面积累的 text 先落成一个 message item。`tool-use`、`tool-result` 同样先 `flushText()` 再 push（`:205-217`），所以 `[text, tool_use, text]` 出三个 item。

legacy 路径的文档把「为什么不需要位置信息」讲得更直白（`/home/xp/src/copilot-api-js/src/lib/translation/legacy-direct/anthropic-to-responses-request.ts:279`）：

> `Emitting reasoning in place rather than at the front is safe because Anthropic's own layout rules already require thinking blocks to lead an assistant turn — preserving source order therefore produces the reasoning-first shape Responses expects, without a reordering step that would lie about any other block.`

同一文件 `:274-277` 还记录了一个已被修掉的旧缺陷：早先版本把 text 与 reasoning `unshift` 到最前，导致 `tool_use` 之后的 text 被提到它前面，而 docstring 却宣称「保持顺序」。

## Q5 近 60 天的动向

`git log --since=2026-06-20` 命中的 carrier 相关提交（**全部是 `master` 的祖先，逐个用 `git merge-base --is-ancestor` 验证过**；另查了 `worktree-carrier-json`、`encrypted-content-recovery`、`thinking-drop-summary`、`thinking-translation-audit`、`integrate-thinking-translation-rfc`、`ir-gate` 六个分支相对 master 在 `src/lib/anthropic` 与 `src/lib/translation` 下的独有提交，**全部为空**）：

| commit | 日期 | 内容 |
|---|---|---|
| `9bfd54df9` | 2026-08-14 | `feat(carrier): structured opaque envelope v2 with an ext slot for hooks` —— v2 信封落地。提交信息坦承 backstop 吞掉了前两道检查的判别力 |
| `73917a567` / `196ab6aae` | 2026-08-15 | inbound → IR → outbound 重构：翻译层围绕 IR 重组，六个 legacy anthropic↔responses bridge **全部变成零生产调用方，仅作 oracle** |
| `a48230500` | 2026-08-15 | `fix(ir): replay our own reasoning carriers instead of reporting them unreplayable` —— IR request writer 之前把**每一个** thinking block 都记成 `thinking-signature-not-portable`；这次才接上 `readReplayableReasoning` |
| `986e7a77b` | 2026-08-15 | 反向非流式响应（anthropic body → responses body） |

**「inbound → IR → outbound 重构触及 reasoning」这一项：有，而且是这 60 天的主线。** 但**没有任何 v2 载体的生产写入、没有 id 保存、没有位置保存**：v2 的 `itemId`/`responseId` 两个槽位自 `9bfd54df9` 引入起，`rg -n "itemId" src` 显示除类型声明（`carrier-v2.ts:34`）与测试 fixture（`tests/anthropic/carrier-v2.unit.test.ts:29`）外**无任何写入点**，`response-body.ts:171-179` 构造 `source` 时只填 `protocol/model/provider?/responseId?`，**`itemId` 连在这条不可达分支里都没填**。

## Q6 已知缺陷（原文引用）

**(a) 同一 reasoning item 的 id 与 blob 在 `.added` 与 `.done` 之间就不一样** —— `/home/xp/src/copilot-api-js/exp/anthropic-responses-direct/FINDINGS.md:18`（2026-07-14 真上游实测）：

> \| `added` vs `done` reasoning `encrypted_content` \| **不同 blob + 不同 id**（added enc_len **1600** id `oh9qJ6Dq…`；done/completed enc_len **1684** id `kDP29WIY…`）→ **GPT MAJOR 属实** \|

同文件还实测了回喂宽容度：回喂 `done` 版、回喂 `added` 版、**回喂空 `encrypted_content`** 三种全是 HTTP 200 —— 结论写作「Responses reasoning 端点对 `encrypted_content` **宽松**……根本**不是** 400 gate」。

**(b) 旧 CC 中转路径至今捕的是中间态** —— `/home/xp/src/copilot-api-js/docs/todo/deferred-backlog.md:1164-1167`：`responses-to-cc-stream.ts` 仍在 `output_item.added` 捕 `encrypted_content`，而 anthropic↔responses 直连桥已改捕 `.done`；被判为「出 RFC 范围」暂缓。

**(c) 多个 reasoning item 塌缩成一个，最后一个 opaque 胜出** —— `/home/xp/src/copilot-api-js/tests/translation/client-wire/known-defects.unit.test.ts:204-210`：

> `test("KNOWN-LOSS：multiple reasoning items collapse into one thinking block and the last encrypted payload wins；C8.2 should keep item boundaries and opaque values independent", ...)`

紧邻的 `:213-214` 还锁了另一条：`KNOWN-LOSS：non-stream encrypted-only reasoning is dropped and replaced by an empty text block`。这两条针对的是 legacy-direct 路径（现为 oracle-only）；IR 路径的 `from-ir/anthropic/response-body.ts:142-149` 是逐 item push 的，**推论：IR 路径不再有塌缩，但我没有找到直接断言这一点的测试**。

**(d) 无 summary 时整轮 encrypted reasoning 无处可挂** —— `deferred-backlog.md:1108-1111`：low effort 下上游可能返回空 summary，此时不产 thinking 块，`encrypted_content` 非空却**无处承载**，该轮跨轮 round-trip 直接丢失。评级 LOW、暂缓。

**(e) server-tool 侧的续接状态完全没有 carrier** —— `deferred-backlog.md:160-161`：`CarrierV2Envelope` 的 `kind` 只覆盖 reasoning 侧，`web_search_call` 等的 opaque id 与权威 item 「没有任何 carrier record 承载它」，往返时**静默丢失**。

**(f) 非流式 message item 共用同一个 `id`（未修）** —— `deferred-backlog.md:19-25`：`response-body.ts` 的 `text`/`degraded-text` 分支给每个 message item 都写 `id: deps.itemId`，上游发 `text, tool_use, text` 时两个 message item 同 id，会让按 item id 建索引的下游（`@ai-sdk/openai` 的 `activeOutputItemIds`）串槽；流式那侧已于 2026-08-20 改成 `${deps.itemId}_msg_${outputIndex}`，非流式因会动三条 byte golden 而暂缓。

**未找到的东西（诚实记录）**：`rg -n "TODO|FIXME|XXX|HACK" src/lib/anthropic src/lib/translation | rg -i "reason|thinking|carrier|signature"` **零命中** —— 这个仓库的已知缺陷不写在 TODO 里，而是写在 `docs/todo/deferred-backlog.md` 与 `tests/**/known-defects.unit.test.ts` 里。关于「reasoning item 的 `id` 被丢弃是否造成过任何可观测问题」，我**没有找到任何记录**：不在 backlog、不在 exp 探针、不在 known-defects 测试里。这个问题在 copilot-api-js 里似乎从未被当作问题提出过。

## 关于生产进程的说明

任务背景提到 pid 926144 正从该代码库提供 4141 服务。我**没有**核实该进程运行的是哪个 commit（不触碰它是硬约束，`git log` 也无法回答）。本文所有「当前行为」的陈述都是**对 `master` HEAD `06c1fec33` 源码的陈述**，不等同于对运行中进程行为的陈述。
