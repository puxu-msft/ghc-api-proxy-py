# copilot-api-js 对 `web search tool is not supported` 400 的完整处置

- 调查日期：2026-08-20
- 被调查仓库：`/home/xp/src/copilot-api-js`，**只读**，未修改任何文件
- 锚定 HEAD：`17bed64a1 docs(todo,memory): 登记 delivery grammar 放弃解释后对 driver 不可见`
- 工作树状态：dirty（`src/lib/pipeline/delivery/*`、`src/routes/*/handler-v4.ts` 等有未提交修改），但**本报告涉及的所有文件均未被修改**，行号对应工作树 = 对应 HEAD
- 委托来源：py 项目生产错误 `400 POST /v1/messages claude-opus-5: upstream rejected: {'error': {'message': 'The use of the web search tool is not supported.', 'code': 'unsupported_value'}}`
- 起点线索（已核实无误）：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260818-retry-gap.md`

---

## 0. 摘要（最重要的三条）

1. **两条不同的 400，两条不同的自愈腿，剥的东西完全不同。** `The use of the web search tool is not supported.` 只剥**请求 `tools[]` 里的声明**，完全不碰历史；`Tool 'X' not found in provided tools` 才剥/降级**历史 `messages` 里的 server-tool 块**。两者共用一个 primitive，但 remediation 是两条独立的臂。
2. **learned state 是 per-(upstream base URL, `anthropic-messages`, 归一化 model) 的类型前缀集合**（`web_search_`），落盘 `~/.local/share/copilot-api/negotiation-states.json`，默认 TTL 30 天。下一次同模型请求在 prepare 阶段直接预剥，首跳即 200。
3. **⚠️ 对 py 项目最关键的一条：copilot-api-js 的这整套自愈只挂在「上游是 `/v1/messages`」的腿上。** 门是 `targetEndpoint === ENDPOINT.MESSAGES`（`retry-registry.ts:140-143`）。而 py 项目的形态是「Anthropic 入 → Responses 上游」，在 js 里对应 `anthropic` client + `targetEndpoint = RESPONSES` 的 direct bridge 腿，那条腿的 retry 栈只有 `network → server-error → token-refresh`（`cc-family-strategies.ts:19-23,47-54`），**没有任何 400 级自愈**。也就是说：**copilot-api-js 在你遇到的这个场景下同样会硬失败，它没有现成答案可抄。** 它在 Responses 腿上的做法是「乐观映射 + 原样透传」（`from-ir/openai-responses/parameters.ts:58-65,92-114`），赌上游接受。

---

## 1. 触发条件

### 1.1 代码里的 matcher

单一数据表，只有一行：

```ts
// src/lib/request/strategies/server-tool-rejection-retry.ts:57-59
export const SERVER_TOOL_REJECTION_TABLE: ReadonlyArray<{ pattern: RegExp; typePrefix: string }> = [
  { pattern: /the use of the web search tool is not supported/i, typePrefix: "web_search_" },
]
```

匹配前置条件（`reactive-rejection.ts:42-46`）：`error.type === "bad_request"` **且** `error.status === 400` **且** 未 attempted。注意 **matcher 不看 `code: "unsupported_value"`**，只看 message 文本；`unsupported_value` 在全仓只作为文档/测试夹具里的伴随字段出现，不参与判定。

取文本的两个载体（`server-tool-rejection-retry.ts:61-68`）：先试 `error.message`（可能是 `HTTP 400: <上游原文>` 的包裹形态），否则回落 `error.raw instanceof HTTPError ? error.raw.responseText` 即原始 JSON body。注释明确说明该措辞不含引号、无 JSON 转义差异，所以两种载体读起来一样。

### 1.2 是 `tools` 声明触发，还是历史 item 触发？

**是 `tools[]` 声明触发。** 三条独立证据：

- **remediation 只动 `tools`**：`prepareHints.excludeServerToolTypes` 唯一消费点是 `buildWirePayload` → `stripServerTools(wire.tools, ...)`（`request-preparation.ts:578-580`），历史 `messages` 一个字节都不改。
- **端到端测试的构造**：`tests/anthropic/server-tool-rejection.http.test.ts:136-140` 发的请求是 `tools: [{name:"web_search", type:"web_search_20250305"}, {name:"Read", ...}]`，`messages` 只有一句纯文本 user；断言首跳 wire 带 `web_search_20250305`、二跳不带、`Read` 存活（`:145-153`）。
- **模块注释**：`server-tool-rejection-retry.ts:4-9` 写「GHC's upstream rejects native server tools (e.g. Claude Code's `web_search_20250305`) **for models that don't support executing them server-side**」。

**历史 item 走的是另外两条完全不同的腿**（都不是本 400）：

| 上游 400 措辞 | 触发物 | 处置腿 | 位置 |
|---|---|---|---|
| `The use of the web search tool is not supported.` | 请求 `tools[]` 里的 `web_search_*` **声明** | `server-tool-rejection-retry` → 剥声明 | `server-tool-rejection-retry.ts` |
| `Tool 'X' not found in provided tools` | 历史里的 `server_tool_use{X}` + `*_tool_result` **块**（STRICT 路径整份 transcript 校验） | `web-search-not-found-retry` → 学习 `serverToolDowngrade` → 从 pre-S3 baseline 重跑 sanitize → 历史块降级 | `web-search-not-found-retry.ts:33-49,56-77` |
| `` `server_tool_use` block references `X`, but `X` is not defined in `tools` as a server tool `` | 历史块与本轮声明不一致 | **无 matcher，全仓不识别，硬失败** | 缺口，`docs/spec/2026-07-26-server-tool-provenance-routing.md:725` 要求补，**未实现**（表至今一行） |

另有一条**常驻无 config 的兜底**（不依赖 400）：`sanitize/empty-encrypted-search-result.ts` 无条件把历史里 `encrypted_content` 为空/缺失的 `web_search_tool_result` 降级掉——因为 `""` 与任何占位串都会被上游 400（`exp/encrypted-content-400` 实测），无法修复只能降级。

### 1.3 有没有 fixture/cassette 固化真实上游行为？

**没有。** 逐项核过：

- `tests/anthropic/server-tool-rejection.http.test.ts` 用的是 `mock-fetch` 手写 body（`:45-47`）——按项目自己的说法，这属于「手写替身编码的是我们相信的上游行为」。
- `tests/pipeline/server-tool-rejection-retry.unit.test.ts` 同样是手工构造 `ApiError`。
- 仓库里**没有 cassette 机制**（那是 py 项目的实践）。
- 唯一为此写的真实探针 `exp/web-search-double-hop-live/reject-probe.ts` 是一个**前置门控**（RFC Commit 1 gate，`:1-12`），用来确认真实 400 措辞是否命中这条 pattern。**全仓找不到它的运行结果记录**（`rg reject-probe` 只命中它自己）；RFC `docs/rfc/2026-07-13-retire-web-search-double-hop.md:53` 把它列为「须实测确认的假设」，也没有回填结论。
- 设计文档只说「只有 web search 有实证样本」（`docs/v4/03-spec/server-tool-rejection-retry.md:25`），但**未给出样本出处**（无日志摘录、无 History 库定位、无 commit 引用）。反倒是 `reject-probe.ts:6-7` 自陈：该措辞「在 History 语料里**无真实实例**（从没客户端发过原生 web_search）」。

**证据权重**：措辞本身现在是**强证据、可据以行动**——但强度**不来自 js 仓库**，来自我方 py 项目今天的生产日志逐字复现了它。js 仓库这一侧只是**中等强度的二手记载**（言之凿凿但无一手留痕，且它自己的探针门从未回填）。

对照组值得一记：同族的 web_fetch 400 是**另一套措辞**，且**有一手实测**——`{"error":{"message":"rejected tool(s): web_fetch","code":"invalid_request_body"}}`（2026-07-12，individual 账户，`api.githubcopilot.com`，`exp/server-tool-web-fetch-poc/README.md:123-132`）。所以「server tool 被拒」在 GHC 上**至少有两种完全不同的 body 形状**，不能按一种写死。

---

## 2. 修复动作

### 2.1 命中后发生什么

```ts
// server-tool-rejection-retry.ts:77-89
createReactiveRejectionStrategy<TPayload>({
  name: "server-tool-rejection-retry",
  match: matchServerToolRejection,                                  // → "web_search_"
  mark: (model, typePrefix) => markAnthropicServerToolUnsupported(model, typePrefix),
  remediate: ({ payload, token }) => ({
    action: "retry",
    payload,                                                        // 原样，不改 payload
    prepareHints: { excludeServerToolTypes: [token] },
    meta: { strippedServerTools: [token] },
  }),
})
```

primitive 侧（`reactive-rejection.ts:48-54`）：置 `attempted = true` → 再 match 一次拿 token（null 则 `abort`）→ `mark` 写账本 → 交给 caller 注入的 `remediate`。

**注意 payload 原样回传、不做任何改写**——真正的剥离发生在**下一次 prepare**，靠 `prepareHints` 传递。这是刻意的（`server-tool-rejection-retry.ts:19-21`）：账本写入是异步 schedule 的持久化，本次重试不能依赖账本已生效，所以用一个**权威 per-attempt hint** 让这一跳确定性剥除。

### 2.2 剥的到底是什么

**只剥 `tools[]` 声明。**

```ts
// message-tools.ts:380-400
export function stripServerTools(tools, model, excludeTypes?) {
  if (!tools) return undefined
  const learned = new Set([...getUnsupportedServerToolTypes(model), ...(excludeTypes ?? [])])
  if (learned.size === 0) return tools                      // 默认原样透传
  const result = []
  for (const tool of tools) {
    const matchesLearned = [...learned].some((prefix) => (tool.type ?? "").startsWith(prefix))
    if (isApiDefinedToolType(tool.type) && matchesLearned) {
      consola.warn(`[DirectAnthropic] Stripping server tool: ${tool.name} (type: ${tool.type})`)
      continue                                              // 整条声明丢弃，不降级
    }
    result.push(tool)
  }
  return result.length > 0 ? result : undefined             // 剥空 → undefined（无 tools 字段）
}
```

- 两源并集：learned 账本 ∪ 本次 hint（`:383`）。全局 config 开关 `anthropic.server_tool_strip` 已随 2026-07-13 退役删除，**现在纯 reactive-learned**。
- 匹配是**双重条件**：既要 `isApiDefinedToolType(tool.type)`（在 `API_DEFINED_TOOL_TYPE_PREFIXES` 白名单里，`message-tools.ts:340-363`），又要命中 learned 前缀。
- 被剥的声明是**直接丢弃**，没有「降级成 function tool」这一说。
- 剥空则返回 `undefined`，wire 上就没有 `tools` 字段了（spec `docs/v4/03-spec/server-tool-rejection-retry.md:163` 明说：纯文本回答，可接受的 degradation）。
- 调用点唯一：`buildWirePayload`（`request-preparation.ts:578-580`），且 `tools` 在 `DEEP_CLONE_FIELDS` 里（`:562`），剥离作用在 wire 副本上，不污染 caller 的 payload——注释明确说这是为了避免重试时损失累积。

### 2.3 ⚠️ 已确认的两个缺口（js 侧没做，py 侧要自己决定）

- **`tool_choice` 不处理。** 全仓 `tool_choice` 相关代码只有 `sanitize/tool-name-sanitize.ts:79-106` 的重命名跟随，**没有任何地方在剥掉 server tool 声明后同步清理指向它的 `tool_choice`**。若客户端发 `tool_choice: {type:"tool", name:"web_search"}` 而声明被剥，会留下悬空的 forced choice。对比：Responses 腿的 `translateToolChoice`（`from-ir/openai-responses/parameters.ts:116-137`）**有**这个处理（「omit the choice too rather than sending a dangling function choice that the upstream rejects」）——说明 js 自己知道这是问题，只是 messages 腿没做。
- **历史 item 不处理。** 这条 400 的 remediation 完全不碰 `messages`。如果同一请求既带 `web_search_*` 声明、历史里又有 `server_tool_use{web_search}` 块，剥掉声明后极可能撞上第三种 400（`server_tool_use block references ... not defined in tools as a server tool`），而那条**全仓无 matcher**（见 §1.2 表第三行）。

### 2.4 另一条腿的降级函数（历史 item 怎么变）

`rewriteServerToolBlocks(messages, "downgrade")`，`sanitize/rewrite-server-tool-blocks.ts:116-196`。**这是回答「历史 item 降级成什么」的权威源码**：

- `server_tool_use` → **plain `tool_use`**，`id`/`name`/`input` 逐字保留（`:183-187`）。不是丢弃，不是转 text。
- `*_tool_result`（`web_search_tool_result` 等）→ **user 侧 plain `tool_result`**，`content` 被**字符串化成人类可读文本**（`:189-196` + `:70-94`）：结果数组渲染成 `Web search results for query: "<q>"` + 编号的 `title - url` 列表；错误形状渲染成 `Web search failed: <error_code>` 并置 `is_error: true`。
- **关键协议约束（`:18-28`）**：`tool_result` 必须在 `user` 消息里。合成的 web_search 轮次把所有块放在**一条 assistant 消息**里，就地降级会造出 assistant 角色的 `tool_result`——用一个 400 换另一个 400。所以「downgrade」会**劈开消息**：`tool_use` + text/thinking 留在 assistant 轮，所有 `*_tool_result` 移到紧随其后**新插入的 user 轮**（`:175-177`）。
- 匹配按**块 type**（`server_tool_use` / `*_tool_result`）而非 tool name，所以 web_search / web_fetch / code_execution 一视同仁（`:27-28`）。
- 永不 mutate 输入；无改动时返回同一个数组引用（`:117,180`）。

**这个「劈消息」的细节是 py 项目最该抄的一条**，因为它是那种不亲自撞过就想不到的协议坑。

---

## 3. learned model state 机制

### 3.1 记住什么、按什么粒度

两个**独立**的账本条目，别混：

| 类别 | 存什么 | 粒度 | 写入者 | 读取者 |
|---|---|---|---|---|
| `serverTools` | `Map<modelKey, Map<类型前缀, meta>>`，值如 `"web_search_"` | per-(endpoint, model) | `markAnthropicServerToolUnsupported` (`feature-negotiation.ts:303-308`) | `getUnsupportedServerToolTypes` (`:311-313`) → `stripServerTools` |
| `serverToolDowngrade` | `Map<modelKey, meta>`，**扁平布尔成员集**（无子维度） | per-(endpoint, model) | `markServerToolDowngrade` (`:383-390`) | `isServerToolDowngradeLearned` (`:393-396`) → `resolveServerToolMode` (`server-tool-rewrite-mode.ts:18-20`) → `sanitize/index.ts:109` |

`modelKey` 的构成（`feature-negotiation.ts:124-126`）：

```ts
`${copilotBaseUrl(state)}|anthropic-messages|${normalizeForMatching(modelId)}`
```

即 **上游 base URL × 固定字面量 `anthropic-messages` × 归一化模型名**。**不含 account**——同一进程内换 account 但 base URL 不变，账本共享。对照组：`toolFields` 类别刻意用 `endpointKey()`（无 model 段，`:137-139`），因为那是上游版本属性；注释明确写了 server-tool 拒绝**是 per-model 的**，所以不这么键（`:130-136`）。

存类型**前缀**（`web_search_`）而非全名（`web_search_20250305`），这样一次学习覆盖所有带日期后缀的变体（`:24-28`）。

### 3.2 存在哪、活多久

- 落盘：`PATHS.NEGOTIATION_STATES` = `<APP_DIR>/negotiation-states.json`（`config/paths.ts:76`），v2 格式，v1 数组自动迁移。写入是 `schedulePersist()` 异步合并写（原子写）。
- 每条记录带 `LearnedEntryMeta`（`negotiation-lifecycle.ts:9-20`）：`firstLearnedAt` / `lastConfirmedAt` / `pinned?` / `manuallyExpired?` / `migrated?`。
- 过期判据单一入口 `isEntryActive`（`:66-72`）：`pinned` → 永远活；`manuallyExpired` → 立即死；否则 `now <= lastConfirmedAt + TTL`。
- TTL：默认 **30 天**（`packages/foundation/src/state-defaults.ts:325`，`30 * 86_400_000`），可用 config `negotiation.default_ttl_days` 覆盖，可 per-category 覆盖（`categoryTtlMs`，`:60-64`），`Infinity` = never。
- **每次再撞同一个 400 会刷新 `lastConfirmedAt`**（`recordEntry` / `touchFlagMeta`），所以活跃使用的条目实际上不会过期。
- 人工管理：`/api/negotiation` 路由可以 expire/delete/pin，UI 侧有 `ui-v4/src/lib/learned.ts`。
- **TTL 到期会复发**，spec 明确接受这个代价并要求写明白：`docs/spec/2026-07-26-server-tool-provenance-routing.md` 「每 TTL 窗口最多一次 400 且能自愈……必须写明，免得后人把它当成新 bug 排查」。

### 3.3 下一次同 model 请求还带不带 web_search？

**不带。** 路径：`buildWirePayload`（`request-preparation.ts:578`）→ `stripServerTools(wire.tools, payload.model, undefined)` → 内部读 `getUnsupportedServerToolTypes(model)`（`message-tools.ts:383`）→ 命中 → 首跳就已剥掉。这是**无条件的 prepare 阶段读取**，不需要任何 hint，也不需要先失败。

数据流总览（spec `docs/v4/03-spec/server-tool-rejection-retry.md:38-42`）：

```
client 带 native web_search → 上游 400 → canHandle ✓
  → mark cache + prepareHints.excludeServerToolTypes=["web_search_"]
  → retry: re-prepare → stripServerTools 剥 web_search_* → 上游 200（degraded 无搜索）
后续同 (endpoint, model) → prepare 直接读 cache 剥离 → 首跳即 200
```

---

## 4. 一次性 guard

`reactive-rejection.ts:33-55`，**双重防御**：

```ts
export function createReactiveRejectionStrategy(cfg) {
  // Per-instance one-shot guard. Strategies are built per-request (see
  // buildAnthropicStrategies), so this is request-scoped and cannot leak across
  // unrelated requests. Defense-in-depth alongside the idempotent cache mark.
  let attempted = false
  return {
    canHandle(error) {
      if (attempted) return false          // ← 闸门在这里
      if (error.type !== "bad_request" || error.status !== 400) return false
      return cfg.match(error) !== null
    },
    handle(error, currentPayload, context) {
      attempted = true                     // ← 先置位，再做任何事
      ...
    },
  }
}
```

1. **`attempted` 闭包 flag**：策略实例是 **per-request 构造**的（`buildAnthropicStrategies` → `assembleRetryStrategies` → 每个 registry entry 的 `create(deps)` 每请求调一次，`retry-registry.ts:344-355` + 注释 `:104-118`），所以这个 flag 是**请求作用域**，既保证同一请求内最多重试一次，又不会跨请求泄漏。
2. **账本 mark 幂等**：即使 flag 失效，`markAnthropicServerToolUnsupported` 幂等，重试后 prepare 阶段已预剥，同样的 400 不会再产生。

剥完仍 400（不应发生）→ 落入通用 retry 预算，耗尽后 `[FAIL]`，诊断经 `setAttemptError` 保留（spec `:165`）。

**顺带记一条对 py 有用的**：这个 primitive 把「detect → parse token → persist → remediate → retry once」抽成了共享骨架，两条 remediation 臂由 caller 注入（`reactive-rejection.ts:10-14`）——**re-sanitize 臂**（system-reject / web-search-not-found：从 `context.originalPayload` 这个 **pre-S3 baseline** 重跑整条 sanitize 链）与 **strip 臂**（partner-feature / server-tool：改 payload 或给 `prepareHints`）。re-sanitize 臂有一条硬约束被标为 CORRECTNESS（`web-search-not-found-retry.ts:14-18,71-73`）：**绝不能喂 `currentPayload`**，那是已经过 S3 的，会把整条重写链**双重施加**。

---

## 5. 「乐观发出去再降级」vs「按 learned state 提前剥」

**两者都做，是一个两阶段机制，不是二选一。**

- **首次遭遇**：乐观发出（默认 `stripServerTools` 在无 learned 时**原样透传全部工具**，`message-tools.ts:385-386` + `:377-378` 注释「When neither applies (default), all tools are forwarded unchanged **per the Anthropic protocol**」）→ 被拒 → 反应式降级 + 学习。
- **此后**：按 learned state **提前剥**，首跳即成。

取舍的书面理由（`docs/v4/03-spec/server-tool-rejection-retry.md:19,26-27`、ADR `docs/decisions/2026-07-13-...md:65-68`）：

- 「反应式自愈——只在真被拒后剥离、自动学习、持久记忆、**对所有模型生效、无需预先配置**」。
- 「无 gate，默认开：与所有自愈策略一致；**反应式只在 400 触发，误剥风险低**」。
- 持久化的动机被直白写出：「**避免每会话首请求先 400**」。
- 2026-07-13 的 ADR 决策 3 明确**删掉了**全局 config 开关（`anthropic.server_tool_strip` / `server_tool_rewrite` / 顶层 `server_tool_web_search`），只保留反应式骨架。理由：这些开关服务 0 真实流量，是「永久 bypass 税」；保留一张「零流量但低成本的安全网」。

换句话说：**它明确拒绝了「预防式全局剥离」**，理由不是技术上不行，而是那需要人工预配置、且会对不该剥的模型误剥。默认协议正确（透传），错了才学。

---

## 6. 反向确认：是不是只对某些模型出现？

### 6.1 结论

**是模型相关的，但 copilot-api-js 里没有任何「哪些 model 支持 web_search」的表或探测逻辑。** 逐项核过：

- GHC `/models` 目录的能力字段（`packages/foundation/src/ghc-model-types.ts:36-51` 的 `ModelSupports`）是任意 key 的 flag bag，但 `src/lib/models/capabilities.ts` 只消费了 `reasoning_effort`（`:47`）。全仓**没有任何代码读取 web_search 相关的 supports 字段**。
- `rg -i web_search src/` 的全部命中里，**没有一处是「按模型判断支不支持」**；只有类型前缀表、翻译映射、hedge policy 前缀列表（`pipeline/generation/hedge-policy.ts:3-5`）、以及退役相关的 compat 弃用声明。
- 唯一的「知识」就是 §3 的 learned 账本，它本身就是 per-model 的——**这就是它按模型粒度键控的原因**（`feature-negotiation.ts:130-136` 注释显式对比：tool-field 拒绝是上游版本属性所以 model-agnostic，而 **server-tool / partner-feature 的拒绝 ARE model-specific**）。

### 6.2 与 py 生产错误对得上的一手数据点

`exp/anthropic-responses-direct/FINDINGS.md`（Phase 0 probe (c)，真实上游）：

| 探针 | 模型 | 结果 |
|---|---|---|
| `/responses` + `tools:[{type:"web_search"}]` | **gpt-5.5** | **HTTP 200**，输出 items = `[reasoning, web_search_call, message]`，上游**原生执行**了搜索（`FINDINGS.md:41-42,47`） |
| `/responses` + `model:"claude-opus-4.8@messages"` | claude-opus-4.8 | HTTP 200，但输出只有 `[message]`（`:67`）——这一条**没测 web_search** |
| `/v1/messages` + native `web_fetch_20250910` | claude-sonnet-4.5→sonnet-5 | **HTTP 400** `{"message":"rejected tool(s): web_fetch","code":"invalid_request_body"}`（2026-07-12 实测） |

把这些拼起来（**判断，中等强度，可据以行动但需你自己的抓包确认**）：GHC 的 `/responses` 上游对 **gpt-5.x** 原生支持 `{type:"web_search"}`，对 **Anthropic 家族模型（如你的 claude-opus-5）不支持**，拒绝时给的正是 `unsupported_value` + `The use of the web search tool is not supported.`。这与 js 侧「按模型学习、不按端点学习」的设计取向一致。

### 6.3 ⚠️ js 在 Responses 腿上的做法（对 py 直接相关）

`src/lib/translation/from-ir/openai-responses/parameters.ts`：

```ts
// :58-65
export const SERVER_TOOL_MAPPING = [
  { anthropicPrefix: "web_search_", responsesType: "web_search" },
  // web_fetch / code_execution 未探针，故意不写，落到 strip+warn
]
```

`translateTools`（`:92-114`）：有映射 → **原样透传为 `{type:"web_search"}`**；无映射 → strip + warn。**这里完全不查 learned 账本**（`getUnsupportedServerToolTypes` 全仓只有 `feature-negotiation.ts` 和 `message-tools.ts` 两处引用）。

而这条腿的 retry 栈（`cc-family-strategies.ts:47-54` → `buildOpenAiResponsesStrategies`）按其模块注释（`:19-23`）只有 **network → server-error → token-refresh**，`appliesToMessages` 门（`retry-registry.ts:140-143`）把全部 13 条 400 级策略挡在外面。

**所以：copilot-api-js 在「Anthropic 入 → Responses 上游 → 模型不支持 web_search」这个精确场景下，会把 400 原样抛给客户端，没有自愈。** 它的注释里写着 probe (c) 证明「请求侧透传可行」，但那是 gpt-5.5 的结论，被当成整张表的依据用了。这是 js 侧一个**真实的、未被记录的缺口**，不是我们要抄的东西。

---

## 7. 给 py 项目的可迁移结论

按可迁移性排序，**不含实施建议**（那需要用户裁决）：

1. **值得抄的形状**：`reactive-rejection` 这个 primitive 的分工——detect / parse token / persist / one-shot 归骨架，remediation 归 caller，两条臂（re-sanitize from pre-transform baseline vs strip via per-attempt hint）。以及那条 CORRECTNESS 硬约束：re-sanitize 必须喂**变换前的 baseline**，喂当前 payload 会双重施加变换链。
2. **值得抄的细节**：`rewriteServerToolBlocks` 的「劈消息」——`tool_result` 必须落在 user 轮，所以降级要把 assistant 轮拆成 assistant + 新插入的 user 轮。这个坑不亲自撞不会知道。
3. **值得抄的判据**：learned 键的粒度选择有明确对照——server-tool 拒绝是 **per-model**，tool-field 拒绝是 **per-endpoint（model-agnostic）**。别一刀切。
4. **不能抄的**：js 在 Responses 腿上没有这条自愈（§6.3）。py 面对的正是这条腿，需要自己设计。
5. **不能抄的**：`tool_choice` 悬空问题在 messages 腿没处理（§2.3）。
6. **要留意的**：GHC 对 server tool 的拒绝**至少两种 body 形状**——`unsupported_value` + `The use of the web search tool is not supported.`（web_search）vs `invalid_request_body` + `rejected tool(s): web_fetch`（web_fetch，2026-07-12 一手实测）。按单一形状写死会漏。
7. **要留意的**：这条 400 的 remediation 只解决**声明**问题。历史里的 server-tool 块是另外的 400、另外的腿；而第三种措辞（`server_tool_use block references X, but X is not defined in tools as a server tool`）**js 至今无 matcher**。

---

## 8. 关键 `file:line` 索引（全部锚定 `17bed64a1`）

**核心实现**

- `src/lib/request/strategies/reactive-rejection.ts:26-56` — primitive：config 接口、`attempted` guard、canHandle/handle
- `src/lib/request/strategies/server-tool-rejection-retry.ts:57-59` — `SERVER_TOOL_REJECTION_TABLE`（唯一一行）
- `src/lib/request/strategies/server-tool-rejection-retry.ts:61-75` — `extractErrorText` 双载体 + `matchServerToolRejection`
- `src/lib/request/strategies/server-tool-rejection-retry.ts:77-89` — 策略工厂（mark + prepareHints）
- `src/lib/request/strategies/web-search-not-found-retry.ts:43` — 另一条 400 的正则（**对工具名通用**，文件名是历史遗留）
- `src/lib/request/strategies/web-search-not-found-retry.ts:56-77` — re-sanitize 臂 + pre-S3 baseline 硬约束

**剥离与降级**

- `src/lib/anthropic/message-tools.ts:380-400` — `stripServerTools`（两源并集、只剥 `tools`、剥空返 `undefined`）
- `src/lib/anthropic/message-tools.ts:340-363` — `API_DEFINED_TOOL_TYPE_PREFIXES` + `isApiDefinedToolType`
- `src/lib/anthropic/request-preparation.ts:538-586` — `buildWirePayload`（唯一调用点、`DEEP_CLONE_FIELDS` 防重试损失累积）
- `src/lib/anthropic/sanitize/rewrite-server-tool-blocks.ts:116-181` — 历史块降级主函数（劈消息）
- `src/lib/anthropic/sanitize/rewrite-server-tool-blocks.ts:183-196` — `toToolUse` / `toToolResult`
- `src/lib/anthropic/sanitize/rewrite-server-tool-blocks.ts:70-94` — 结果内容字符串化
- `src/lib/anthropic/sanitize/rewrite-server-tool-blocks.ts:18-28` — `tool_result` 必须在 user 轮的协议约束
- `src/lib/anthropic/sanitize/empty-encrypted-search-result.ts:1-64` — 常驻无 config 兜底
- `src/lib/anthropic/server-tool-rewrite-mode.ts:18-20` — `resolveServerToolMode`（纯 learned）
- `src/lib/anthropic/sanitize/index.ts:109` — 降级在 sanitize 链里的落点

**learned state**

- `src/lib/anthropic/feature-negotiation.ts:24-28` — `serverTools` 类别文档
- `src/lib/anthropic/feature-negotiation.ts:41-44` — `serverToolDowngrade` 类别文档
- `src/lib/anthropic/feature-negotiation.ts:100-109` — 两张内存表
- `src/lib/anthropic/feature-negotiation.ts:124-126` — `modelKey`（base URL × `anthropic-messages` × 归一化 model）
- `src/lib/anthropic/feature-negotiation.ts:130-139` — `endpointKey` 及「为何 server-tool 不这么键」的对照注释
- `src/lib/anthropic/feature-negotiation.ts:303-313` — mark / get 前缀
- `src/lib/anthropic/feature-negotiation.ts:383-396` — downgrade 的 mark / is
- `src/lib/anthropic/negotiation-lifecycle.ts:9-20` — `LearnedEntryMeta`
- `src/lib/anthropic/negotiation-lifecycle.ts:60-72` — `categoryTtlMs` / `isEntryActive`
- `packages/foundation/src/state-defaults.ts:325` — 默认 TTL 30 天
- `src/lib/config/paths.ts:76` — `negotiation-states.json` 落盘位置

**注册与门**

- `src/lib/request/retry-registry.ts:140-143` — `appliesToMessages`（**关键门**）
- `src/lib/request/retry-registry.ts:162,165` — order（serverToolRejection 480 / webSearchNotFound 510）
- `src/lib/request/retry-registry.ts:272-279` — server-tool-rejection 注册
- `src/lib/request/retry-registry.ts:299-308` — web-search-not-found 注册
- `src/lib/codec/anthropic/strategies.ts:20-30,83-95` — messages 腿装配
- `src/lib/codec/anthropic/anthropic-leg.ts:72,128` — `prepareHints.excludeServerToolTypes` 透传
- `src/lib/request/retry-types.ts:28-42` — `PrepareHints`
- `src/lib/codec/cc-family-strategies.ts:19-23,42-54` — **Responses 腿只有 3 条策略**

**Responses 腿（py 直接相关）**

- `src/lib/translation/from-ir/openai-responses/parameters.ts:39-65` — `SERVER_TOOL_MAPPING` + probe (c) 出处
- `src/lib/translation/from-ir/openai-responses/parameters.ts:92-114` — `translateTools`（不查账本）
- `src/lib/translation/from-ir/openai-responses/parameters.ts:116-137` — `translateToolChoice`（**有**悬空 choice 处理）

**测试（均为手写 mock，非 cassette）**

- `tests/anthropic/server-tool-rejection.http.test.ts:45-47,127-154` — 端到端 fetch-mock
- `tests/pipeline/server-tool-rejection-retry.unit.test.ts:34-107` — canHandle 互斥矩阵（含「表外措辞必须不命中」的反例）
- `tests/pipeline/web-search-not-found-retry.unit.test.ts` — 另一条腿

**文档与探针**

- `docs/decisions/2026-07-13-server-tool-positioning-and-web-search-retirement.md:25-31` — 三类工具模型（真 server / 内置 client / 自定义 client）
- `docs/decisions/2026-07-13-...md:65-68` — 决策 3：删 config 键、留反应式骨架
- `docs/v4/03-spec/server-tool-rejection-retry.md:23-34` — 决策表（含「只有 web search 有实证样本」）
- `docs/spec/2026-07-26-server-tool-provenance-routing.md:725` — 第三种措辞的缺口（要求补，未实现）
- `exp/server-tool-web-fetch-poc/README.md:123-132` — **web_fetch 400 一手实测**（另一套措辞）
- `exp/anthropic-responses-direct/FINDINGS.md:41-42,47,67` — **Responses + web_search 一手实测**（gpt-5.5 200）
- `exp/web-search-double-hop-live/reject-probe.ts:1-12` — 措辞门控探针（**结果未回填**）
- `docs/rfc/2026-07-13-retire-web-search-double-hop.md:53` — 该探针被列为「须实测确认的假设」

---

## 9. 证据权重标注

| 结论 | 权重 | 依据 |
|---|---|---|
| 代码路径、matcher、剥离对象、learned 键与 TTL | **强，可直接据以行动** | 逐行读过源码，非推断 |
| `appliesToMessages` 导致 Responses 腿无 400 自愈 | **强，可直接据以行动** | 门函数 + 两处装配点 + 模块注释三重印证 |
| 该 400 由 `tools[]` 声明触发（非历史 item） | **强** | remediation 只动 tools + 端到端测试构造 + 模块注释，三条独立证据 |
| 该 400 措辞真实存在 | **强，但强度来自 py 生产日志，不来自 js 仓库** | js 侧无一手留痕；探针门未回填；设计文档的「实证样本」无出处 |
| 「Anthropic 家族模型在 GHC `/responses` 上不支持 web_search，gpt-5.x 支持」 | **中，倾向性判断，需你自己抓包确认** | gpt-5.5 的 200 是一手实测；Anthropic 侧是把 py 生产错误与 js 的 per-model 设计取向拼起来的推断，无直接对照实验 |
| `tool_choice` 悬空缺口 | **中高** | 全仓 grep 无处理 + Responses 腿有对照实现，属于「找不到即不存在」类证据 |
