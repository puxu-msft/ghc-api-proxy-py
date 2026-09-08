# copilot-api-js 改写器架构调查

- 调查对象：`/home/xp/src/copilot-api-js`，HEAD = `6209cb510`（`docs(tmp): 收尾终端报告`）。
- 工作树有未提交改动（`git status` 显示 7 个 M + 若干 ??），但均不在 `src/lib/pipeline/`、`src/lib/codec/`、`src/lib/request/` 之下，因此本报告引用的源码行与 HEAD 一致。
- 所有结论均以读源码为准；凡是文档与代码不一致的地方，正文单独标出。
- 证据权重标注：**[强]** = 直接读到接口定义与全部调用点，可据此动手；**[中]** = 读到主要路径，可能有未覆盖的分支；**[弱]** = 只有单点观察或依赖文档陈述。

---

## 1. 机制形态

### 1.1 两级注册表，全部是「静态声明 + 运行期装配」的函数对象

核心接口在 `/home/xp/src/copilot-api-js/src/lib/pipeline/rewrite-registry.ts`。它定义两种改写器，形态是**带元数据的普通对象**（不是类，不是外部声明式配置）：

```ts
// rewrite-registry.ts:34-43
export interface RequestRewrite {
  readonly name: string          // 唯一名，进 history 诊断
  readonly order: number         // 装配排序键
  appliesTo(env: RequestEnvelope): boolean
  apply(env: RequestEnvelope): RewriteResult
}

// rewrite-registry.ts:46-53
export interface RewriteResult {
  env: RequestEnvelope
  changed: boolean               // false → 不记录诊断
  stats?: Record<string, number>
}
```

```ts
// rewrite-registry.ts:123-148
export interface ResponseRewrite {
  readonly name: string
  readonly order: number
  appliesTo(env: RequestEnvelope): boolean
  createState?(env: RequestEnvelope): RewriteState      // 每请求私有可变状态
  transform(frame: SseFrame, state: RewriteState): FrameAction   // 逐帧
  flush?(state: RewriteState): Array<SseFrame>          // 流末尾排空
  transformWhole?(response: unknown, env: RequestEnvelope): unknown  // 非流式对应体
}
```

响应侧的返回值是一个三态动作（`rewrite-registry.ts:80-98`）：

- `emit` —— 替换成 0 个或多个帧（原样透传写作 `[frame]`），并带一个 `provenance: "preserve" | "fresh"` 标记，用于 history 溯源；
- `suppress` —— 丢弃该帧；
- `buffer` —— 扣留该帧，**由改写器自己在 `state` 里累积**，driver 不代为保留。

装配逻辑只有两行（`rewrite-registry.ts:229-239`）：`registry.filter(r => r.appliesTo(env)).sort((a,b) => a.order - b.order)`。`Array.prototype.sort` 稳定，所以同 `order` 保持注册顺序。

### 1.2 能否否决、能否要求重试：都不能

**[强]** 改写器接口里**没有** veto、abort、retry 的表达。`RewriteResult` 只有 `env / changed / stats`；`FrameAction` 只有 `emit / suppress / buffer`。要否决一个请求，只能走 S2 的 `decideRoute` 返回 `{kind:"reject"}`（`driver.ts:504-510`）；要要求重试，只能走另一套 retry strategy（见第 6 节）。这条职责边界画得很干净，值得照抄。

### 1.3 请求侧还嵌了第二级「payload 级」注册表

`/home/xp/src/copilot-api-js/src/lib/anthropic/payload-rewrites.ts` 定义了 `AnthropicPayloadRewrite`（`:68-74`），同样是 `name / order / appliesTo / apply`，但作用在**格式原生的 `MessagesPayload`** 而非 envelope 上。三个成员：`tool-preprocess`(100)、`tool-name-sanitize`(200)、`sanitize-messages`(300)（`:130`），由 `runAnthropicPayloadRewrites` 顺序跑（`:153-170`）。

这一整条链被**一个** envelope 级 `RequestRewrite` 包起来：`createAnthropicSanitizeRewrite`（`/home/xp/src/copilot-api-js/src/lib/codec/anthropic/request-rewrite-adapter.ts:58-69`，name=`anthropic-sanitize`，order=300）。也就是说请求侧实际上是「registry 套 registry」，外层负责 envelope 适配与四路 side-channel 记录（`:72-100`），内层负责真正的 payload 变换。

**判断**：这一层嵌套是历史演进的产物（内层先于 envelope 存在，注释在 `payload-rewrites.ts:22-27` 明说「P2 的 driver 会用一个 trivial adapter 包起来」），不是设计出来的。Python 侧不必复制。

---

## 2. 挂载点全集

### 2.1 driver 的七阶段（S1→S7）与改写点

`driver.ts` 的 `runRequest`（`:475-556`）按顺序执行：

| 位置 | 代码 | 数据形态 |
|---|---|---|
| S1a ingest | `deps.codec.parse(raw)`，`driver.ts:482` | 原始 HTTP → envelope，body 为 client-native |
| **hook `client.inbound`** | `driver.ts:486-487` | client-native body，注入前 |
| 系统提示注入 | `applyInboundSystemPrompt`，`driver.ts:494` | 同格式追加 |
| **hook `client.inboundComposed`** | `driver.ts:497-498` | client-native body，注入后 |
| S1b translate-in | `codec.translateInbound?.()`，`driver.ts:502` | 仅 gemini（Gemini→CC） |
| S2 translate-out / route | `resolveRouteDecision` + `outboundTranslateOut`，`driver.ts:504-527` | body 变为 target-format |
| **S3 rewrite-in** | `runRewriteIn`，`driver.ts:528` / 实现 `driver.ts:606-618` | target-format payload（即已翻译后的 body） |
| **hook `upstream.outbound`** | `driver.ts:532-533` | sanitize 后、exchange 前，**在 retry loop 之外**（注释 `:530-532` 说明原因：每次重放会覆盖 reactive strategy 已写入 env 的修正） |
| S4-pre prepare-wire | `codec.prepareWire(env)`，`types.ts:1094` | 最终 URL + headers + body 字节 |
| **hook `exchange`** | `openPhysicalDispatch`，`driver.ts:1000-1004` | 包裹 `transport.send`，**每次物理调用都触发（L1×L2 次）** |

响应侧在 `/home/xp/src/copilot-api-js/src/lib/pipeline/stream/response-processor.ts` 的 `processFrames`（`:149`）：

| 位置 | 代码 | 数据形态 |
|---|---|---|
| upstream 原始采样 | `captureUpstreamGenerationDispatchFrame`，`:229-232` | 上游原始 SSE 帧，**先于任何改写** |
| **hook `upstream.inbound`** | `:240-273` | 上游协议帧，逐帧，返回 `undefined` 丢弃 |
| **S5 rewrite-out** | `passThrough([effectiveFrame], rewrites, states, …)`，`:276` | 上游协议帧（**还未翻译回 client 协议**） |
| S6 render | `renderFrames` → `codec.renderResponse`，`:277 / :380-397` | 产出 client 协议帧 |
| **hook `client.outbound`** | `candidate-response-session.ts:210-213`（`postRender`） | 已渲染的 client 帧，sink write 前 |

非流式路径另有 `runResponseWhole`（`driver.ts:2183-2189`），用**同一条按 `order` 升序的链**跑 `transformWhole`。

### 2.2 数量与分布

**[强]**

请求侧 `RequestRewrite` 实现共 4 个：

| name | order | 位置 |
|---|---|---|
| `thinking-quarantine-proactive` | 250 | `src/lib/anthropic/thinking-quarantine/proactive-filter.ts:101-104` |
| `anthropic-sanitize` | 300 | `src/lib/codec/anthropic/request-rewrite-adapter.ts:58` |
| `reverse-anthropic-sanitize` | 300 | `src/lib/codec/openai-cc/reverse-anthropic-rewrite.ts:83-86` |
| `responses-tool-name-sanitize` | — | `src/lib/codec/openai-responses/openai-responses-cell.ts:85-87` |

响应侧 `ResponseRewrite` 共 7 个实例（去重后）：

| name | order | 位置 |
|---|---|---|
| `errorFrameCanonical` | 50 | `src/lib/codec/anthropic/error-frame-canonical-rewrite.ts:47` |
| `recover-tool-call` | 100 | `response-rewrite-adapters.ts:135` |
| `thinking-signature-compat` | 150 | `response-rewrite-adapters.ts:213` |
| `tool-input-decode` | 200 | `response-rewrite-adapters.ts:283` |
| `server-tool-filter` | 300 | `response-rewrite-adapters.ts:336` |
| `recover-refusal` | 400 | `response-rewrite-adapters.ts:367` |
| `responses-fix-stream-ids` | 100 | `src/lib/codec/openai-responses/response-rewrites.ts:60-69` |

`RESPONSE_REWRITE_ORDER`（`rewrite-registry.ts:201-208`）用一段 30 行注释把每个 order 值背后的**硬约束**写死了，例如 `recoverToolCall(100)` 必须先于 `serverToolFilter(300)`，因为前者在**上游 index 空间**上合成 `tool_use` 帧，后者才做 client 名恢复 + index 稠密化，颠倒会导致 index/name 损坏。这些不变量由 `tests/pipeline/response-rewrite-contract.unit.test.ts` 锁定。

**这段注释是整个设计里最有价值的东西**：它把原本藏在闭包嵌套（`streaming-pump.ts:195-228`）里的顺序契约，变成了可检查、可测试的显式声明。

---

## 3. 命名与寻址

**[强]** `rewrite-out:responses-fix-stream-ids` 这个 ID **不是注册表里的名字**，而是 history 溯源里的 **`transformId`**，构成规则是 `${stage}:${name}`。

生成点在 `response-processor.ts:167`：

```ts
const transformId = `rewrite-out:${name}`
```

其中 `name` 是 `ResponseRewrite.name`。同一 codebase 里可观察到的 `stage:transformId` 家族（`rg 'stage: "'` 在 src 下的全部结果）：

| stage | transformId | 产生点 |
|---|---|---|
| `rewrite-out` | `rewrite-out:<rewriteName>` | `response-processor.ts:167` |
| `rewrite-upstream-hook` | `hook:rewrite-upstream-frame` | `response-processor.ts:251,257,264,270` |
| `render` | `render:<clientFormat>` | `response-processor.ts:388-389` |
| `client-transform` | `candidate:on-rendered-frame` | `candidate-response-session.ts:219` |
| `upstream-capture` | （无 transformId，是根节点） | `context/request.ts:699` |
| `transform-root` / `synthetic-root` | （无主的溯源根） | `context/request.ts:635,644` |

**没有 `rewrite-in:` 前缀。** 请求侧 S3 完全不产生 transform 记录——`runRewriteIn`（`driver.ts:606-618`）里只留了一行 `// P3.2 wires request.rewrite_applied{name, changed, stats} here.`，即那个诊断事件**至今未接线**。`RewriteResult.changed` 字段目前无人消费。

---

## 4. 配置与开关

**[强]** **没有**一个统一的「改写器」配置区。逐条回答：

- **启停单个改写器**：只能通过每个改写器 `appliesTo` 里各自读的、语义化命名的业务配置键，例如：
  - `responses-fix-stream-ids` → `state.fixResponsesStreamIds` ← `openai.responses.fix_stream_ids`（`src/lib/config/config.ts:1256`）
  - `recover-tool-call` → `state.recoverToolCallText` ← `…invoke_in_text`（`config.ts:888`）
  - `thinking-signature-compat` → `state.thinkingSignatureCompat` ← `anthropic.thinking_signature_compat`（`config.ts:827`，`config.schema.json:686`）
  - `tool-input-decode` → 四个键的**或**（`response-rewrite-adapters.ts:289-294`）：`decode_top_level_field` / `ask_user_question_question_missing` / `send_message_to_missing` / `malformed_input`
  - `server-tool-filter`、`recover-refusal`、`errorFrameCanonical` → **无开关**，Anthropic 腿恒开
- **调整顺序**：**不可能**。`order` 是源码里的 `const` 字面量。
- **`config.schema.json` 里与之相关的字段**：只有 `hooks`（见第 5 节），形状是 `{ upstream_module: string|null, enabled: boolean|null }`，`additionalProperties: false`。

对照之下，**retry strategies 反而有统一的配置面**：`upstream_request_retry.strategies.<configKey>.{enabled, max_retries}`，`propertyNames.enum` 里列出了全部 18 个键（`config.schema.json` 的 `upstream_request_retry` 节）。`RetryStrategyEntry` 显式带 `configKey` 字段（`retry-registry.ts:105`），改写器接口则没有对应物。

**这是这套设计里最明确的不对称，也是最值得 Python 侧改进的地方。**

---

## 5. 是否真的「外置」——明确判定

### 判定：**改写器注册表不是外置的；只有一套独立的、能力受限的 hook 中间件是外置的。两者是两个通道，互不连通。**

**[强]** 证据如下。

#### 5.1 改写器一侧：编译进主程序，且刻意拒绝运行期注册

`rewrite-registry.ts:154-166` 与 `:210-217` 两处 `BUILTIN_*_REWRITES` 都是**空数组**，注释直说「Do NOT look here」，真正的注册表是各 codec 模块里的 `const` 数组（`ANTHROPIC_RESPONSE_REWRITES`、`RESPONSES_RESPONSE_REWRITES`），经 `deps.responseRewrites` 或 `CellAssembly` 按请求传入。作者给出的理由是：

> Static (non-runtime) registration keeps assembly deterministic and avoids a mutable global singleton that would leak across bun's single-process test runs.

`src/lib/codec/response-rewrite-registry.ts:39-53` 是全格式并集表，键是编译期穷举的 `Record<UpstreamEndpoint, …>`。**没有任何路径可以从磁盘、配置或插件目录追加一个 `ResponseRewrite`。**

#### 5.2 hook 一侧：真外置，但只有 6 个固定叶子

`src/lib/pipeline/hooks/` 是一套**独立的**中间件：

- 配置：`hooks.upstream_module`（文件路径）+ `hooks.enabled`（`config.schema.json` `/properties/hooks`）。
- 加载：启动时 `packages/cli/src/start.ts:342-344` 调 `loadUpstreamHookSafe`；此后**只有** `POST /api/hooks/reload` 能热重载（`docs/upstream-hooks.md` 与 `src/routes/hooks/route.ts`）。
- 加载机制：`loader.ts:99-125`，`Bun.Transpiler.transformSync` 转译 TS → 写入 `.hooks-cache/hook-<ts>-<seq>.mjs` → `import()`。用唯一文件名绕开 Bun 按路径缓存 ESM；用真实项目内文件（而非 `data:` URL）保住 tsconfig `paths`，这样 hook 才能 `import { … } from "~/lib/pipeline/hooks"` 拿到工具箱。
- 接口：`hooks/types.ts:28-80`，六个可选叶子 `client.{inbound, inboundComposed, outbound}` / `upstream.{inbound, outbound}` / `exchange`。
- 示例：仓库根 `hooks/strip-todowrite.ts`（唯一一个），一个 `client.inbound` 钩子，剥掉 Claude Code 注入的 TodoWrite 提醒。
- 失败语义：`loadUpstreamHookSafe`（`loader.ts:132-144`）warn-continue，加载失败保留旧 hook 并记 `lastReloadError`，不崩进程。

#### 5.3 两个通道的能力差距

| | 改写器注册表 | hook 中间件 |
|---|---|---|
| 来源 | 编译进二进制 | 磁盘文件，配置声明，热重载 |
| 数量 | 任意多，有 `order` 排序 | 每个挂载点**至多一个**函数 |
| 排序 | 声明式 `order` | 无——没有链，只有单点 |
| 状态 | `createState(env)` 每请求私有 | 模块闭包，作者自理 |
| 缓冲/排空 | `buffer` + `flush` 一等公民 | 无——只能 `frame → frame | undefined` |
| 非流式 | `transformWhole` | 无 |
| 门控 | `appliesTo(env)` | 作者自己在函数里 if |
| 观测 | 自动进 history transform 图 | 只有 `hook:rewrite-upstream-frame` 一个 transformId |

结论：**hook 是「外置的观测/mock/单点补丁」，不是「外置的改写器」。**想外置一个新的兼容性修复（比如再来一个类似 fix-stream-ids 的、需要跨帧状态和缓冲的修补），今天在 copilot-api-js 里做不到——只能改源码往 `RESPONSES_RESPONSE_REWRITES` 里加一项。

#### 5.4 顺带发现的一个真缺陷（未修，向你方无害，但说明这套外置面缺乏维护）

**[强]** `loader.ts:38` 的 `HOOK_POINTS` 只有五项：

```ts
const HOOK_POINTS = ["client.inbound", "client.outbound", "upstream.inbound", "upstream.outbound", "exchange"] as const
```

但 `types.ts:60` 声明了第六个叶子 `client.inboundComposed`，driver.ts:497 也确实读它。加载器用 `HOOK_POINTS.filter(...)` 算 `exports`，再 `for (const p of exports) setLeaf(...)` 组装 hook 对象（`loader.ts:110-116`）——所以**一个从磁盘加载的 hook 模块导出 `client.inboundComposed` 会被静默丢弃**；若它只导出这一个叶子，加载器还会抛 `exports none of: …`。该叶子今天只有 `setUpstreamHookForTests`（测试专用 DI 缝，`loader.ts:73-75`）能装上。live 文档 `docs/upstream-hooks.md` 也只写「五个挂载点」，同样漏了它。

（另一处文档漂移：`src/routes/debug/dry-run-pipeline.ts:19` 注释说「Anthropic 5」个响应改写，实际是 6 个——`errorFrameCanonical` 后来加入而注释没跟。**[强]**）

---

## 6. 与 retry strategies 的关系

**[强]** **是两套完全独立的机制**，接口形态刻意做成同构，但数据通道不共享。

### 6.1 同构之处

`src/lib/request/retry-registry.ts:98-119` 的 `RetryStrategyEntry` 与改写器几乎一一对应：

```ts
export interface RetryStrategyEntry {
  readonly name: string
  readonly order: number                        // 同样是声明式排序键
  appliesTo(ctx: RetryStrategyContext): boolean // 腿门控（只看 clientFormat + targetEndpoint）
  readonly configKey: string                    // ← 改写器没有的东西
  readonly kind: "env" | "payload"
  create(deps, options): PayloadOrEnvStrategy
}
```

`RETRY_STRATEGY_ORDER`（`:151-168`）共 16 项，`RETRY_STRATEGY_REGISTRY`（`:172+`）声明，`assembleRetryStrategies` 按 `appliesTo ∧ config.enabled` 过滤后按 `order` 排序再实例化。**这是从改写器注册表复制过来的模式**（RFC 2026-07-21 明说是「replaces the per-leg hard-coded buildXxxStrategies arrays」）。

### 6.2 语义之别

| | 改写器 | retry strategy |
|---|---|---|
| 触发 | 每请求/每帧无条件跑（受 `appliesTo`） | 只在**上游返回错误**后由 `canHandle(error)` 触发 |
| 产出 | 变换后的 env / 帧 | `{action:"retry", payload, prepareHints}` 或 `{action:"abort", error}` |
| 能否否决 | 不能 | 能（`abort`） |
| 能否要求重试 | 不能 | 这就是它的全部职责 |
| 学习回写 | 无 | `onResolved(ctx)` —— 成功后固化学到的东西（如 `unsupported-beta` 把探测到的 beta 写进协商缓存） |

### 6.3 `prepareHints` 是什么——**不是**二者之间的接口

**[强]** 这一点值得纠正一个直觉。`PrepareHints`（`src/lib/request/retry-types.ts:29-42`）的字段全是「下一次出线时要排除掉什么」：`excludeBetas` / `rejectFields` / `excludeServerToolTypes` / `excludeToolFields` / `excludeCacheControlSubfields` / `contextEscalation`。

它的**写入方**是 retry strategy，经 `payload-strategy-adapter.ts:87` 折回 envelope：

```ts
if (action.prepareHints) next.prepareHints = action.prepareHints
```

它的**读取方**是 **S4-pre 的 `prepareWire`**，不是 S3 的改写器。全部读取点集中在 `src/lib/codec/anthropic/anthropic-leg.ts:70-75` 与 `:126-131`。我 grep 过 S3 侧全部 `RequestRewrite` 实现，**没有任何一个读 `prepareHints`**。

所以真实的耦合链是：

```
retry strategy --(prepareHints, REPLACE 语义)--> env.attempt --(读)--> codec.prepareWire (S4-pre)
S3 rewrite-in  --(改写 env.attempt.body)-------> 同一个 env.attempt
```

两者都写 `AttemptScope`（`envelope.ts:157-167`），但写的是**不同字段**（`body` vs `prepareHints`），没有直接对话。`prepareHints` 是 REPLACE 语义（每次 retry 全量覆盖），注释 `envelope.ts:161-164` 专门解释了为什么请求生命周期稳定的供给（如 truncate baseline）不能放这里——否则第一个带 hint 的 retry 会把它抹掉。

**另外注意一个执行顺序事实**：S3 rewrite-in 跑在 retry loop **之外**（`driver.ts:528`，在 `runGenerationPreflight` 之前），`upstream.outbound` hook 同样在循环外（`driver.ts:530-533` 的注释明确说明理由）。retry 时重跑的是 `prepareWire`，不是改写器链。

---

## 7. 可观测性

### 7.1 history 存的是一张 frame DAG，不是「前后两份」

**[强]** 你方 rules 里的说法——「history 会为每次 client-side transform 重复存一次事件」——**基本准确，但有一个重要限定**。

实现在 `/home/xp/src/copilot-api-js/src/lib/context/request.ts`：

- `captureUpstreamFrameFor`（`:696-712`）把上游原始帧注册为根节点，`origin.stage = "upstream-capture"`，`track = "upstream"`。
- `captureFrameTransformFor`（`:716-744`）与 `captureFrameActionFor`（`:746-790`）为每次改写调 `modelOperationRecorder.deriveFrame({ derivedFrom: parentHandle, transformId, origin: { stage, track: "client" } })`，**再**调 `recordTransform({ transformId, stage, inputs, outputs })` 记一条边。

所以 history 里是一棵以上游原始帧为根、每个改写器一层的派生树，加上显式的 transform 边。**这正是为什么「按 db 取全部帧」会拿到每个事件重复三四次。**

**限定条件（重要，决定你方派生 fixture 时的过滤方式）**：字节未变且未 `forceDerived` 的透传**不会**新建节点，而是把输出对象重新指向父 handle：

```ts
// request.ts:726-729
if (parent && !transform.forceDerived && sameBytes) {
  rememberFrame(outputFrame, parent.handle)
  return
}
```

`captureFrameActionFor` 有对应的单入单出同字节短路（`:757-768`）。所以重复只发生在**真正改了字节的改写器**上；`preserveFrame()`（`rewrite-registry.ts:91-93`，`provenance:"preserve"`）就是为了走到这条短路。你方 rules 说的「保留 transform 图的根，别的都丢」是对的做法。

### 7.2 buffer/flush 的溯源

`response-processor.ts:167-207` 的 `captureRewrite` / `captureFlush` 处理了缓冲语义：`buffer` 动作记一条 `action:"buffer"` 的边并把输入帧攒进 `bufferedInputsByRewrite`；下一次 emit 时把攒下的全部帧一起作为 `inputs`，并在 metadata 里记 `bufferedInputCount`（`request.ts:785-789`）。`flush` 记 `action:"flush"`。

### 7.3 请求侧几乎没有观测

**[强]** 前面已提：S3 完全不产生 transform 记录（`driver.ts:616` 只有一行 TODO 注释）。请求侧的可观测性走的是完全不同的一条路——改写器自己往 `ctx` 写 side-channel：`ctx.setInitialSanitizationInfo(...)`、`ctx.setPipelineInfo({ preprocessing, sanitization, messageMapping })`（`request-rewrite-adapter.ts:79-97`）。**这是手写的、每个改写器各自负责的、跟框架无关的记录**，与响应侧那套自动 DAG 完全不对称。

### 7.4 还有一个 dry-run 检查器

`POST /api/debug/dry-run-pipeline`（`src/routes/debug/dry-run-pipeline.ts`）能把一个合成或从 history 回放的请求/响应喂进**真实的** driver，在 `stopAfter ∈ {parse, translate, rewrite-in, prepare-wire, rewrite-out, render}` 处停下并吐出中间态，返回体里有 `stages["rewrite-out"].perRewrite[].name`。它诚实地在 `fidelity.caveats` 里列出了自己覆盖不到的 handler-side 工作（heartbeat 注入、post-render tool-name restore 等）。**这个东西的 ROI 很高**，是把「等症状复现」变成「确定性重放」的关键工具。

---

## 8. 评价：值得借鉴 / 该丢弃

### 8.1 值得借鉴（按优先级）

1. **`order` 作为可检查契约，并把顺序背后的理由写在 order 表旁边。** `RESPONSE_REWRITE_ORDER`（`rewrite-registry.ts:170-208`）那段注释逐条说明「为什么 100 必须早于 300」，并指明由哪个测试文件锁定。这把闭包嵌套里的隐式知识变成了显式的、能被评审的东西。**这是整套设计里最值钱的部分。**
2. **`FrameAction` 三态 + `buffer` 由改写器自持状态。** driver 不代管缓冲，改写器用 `createState` 拿到私有状态自己攒。这让「一个改写器要跨帧看窗口」这件事不需要污染框架。对你方的块级交付模型尤其贴合——你方本来就是攒满一个 Anthropic content block 再发。
3. **`preserve` vs `fresh` 的 provenance 标记。** 它直接决定了溯源图会不会长出一个新节点，从而决定了「history 里一个事件出现几次」。你方在做 cassette 派生时被这个问题咬过，说明这个标记的存在是有实际价值的。
4. **改写器不能否决、不能要求重试。** 职责边界清晰：变换归改写器，控制流归 route decision 与 retry strategy。
5. **`appliesTo` 门控在**出线腿**（`targetEndpoint`）而非**入线格式**（`clientFormat`）上。** `response-rewrite-adapters.ts:112-122` 与 `retry-registry.ts:15-21` 都长篇解释了这一点：一个改写器处理的是**某个上游线协议的字节**，所以门控必须挂在那条腿上；挂在 clientFormat 上，等格式翻译腿一上线就会静默漏掉。**这条对你方直接适用**——你方主路径就是 Anthropic 入、Responses 出，两轴天然不同。
6. **dry-run 检查器**（第 7.4 节）。
7. **retry strategy 的 `configKey` + 统一配置面**（`upstream_request_retry.strategies.<key>.{enabled,max_retries}`，schema 里 `propertyNames.enum` 穷举）。**把这个模式反向应用到改写器上，正是 copilot-api-js 没做而你方应该做的事。**

### 8.2 该丢弃 / 别复制

1. **「注册表刻意留空 + 靠 `deps` 每请求注入」这套间接层。** `BUILTIN_REQUEST_REWRITES` / `BUILTIN_RESPONSE_REWRITES` 恒为空，注册表实际散落在 `codec/*/…-rewrites.ts` 里，再经 `deps.responseRewrites` → `CellAssembly.responseRewrites(env)` → `migratedCell(env)?.… ?? deps.… ?? BUILTIN_…` 三级兜底（`driver.ts:770, 1066, 2185`）。作者自己在注释里承认「这个常量存在只是为了让 grep 落在这段解释上」。**这是给出的理由（测试隔离）与付出的代价（查找性、三级兜底）严重不匹配的典型。** 用一个显式的、可注入的 registry 对象即可，不必空常量 + 层层 `??`。
2. **请求侧的两级嵌套注册表**（`RequestRewrite` 包 `AnthropicPayloadRewrite`，第 1.3 节）。历史包袱，一级足够。
3. **改写器开关散落在业务配置键里。** 七个改写器七种开关形状，其中 `tool-input-decode` 的 `appliesTo` 是四个配置键的**或**（`response-rewrite-adapters.ts:289-294`），三个改写器根本没有开关。要判断「现在哪些改写器是活的」，得读七处源码。
4. **请求侧观测缺席。** `RewriteResult.changed` / `stats` 定义了却无人消费，`request.rewrite_applied` 事件从 P3.2 计划至今未接线。**接口里留一个没人喂的字段，比不留更糟**——它会让读者以为有这个能力。
5. **`apply` 不是纯函数，且这一点是 2026-08-11 主动放弃的。** `rewrite-registry.ts:29-33` 明说：scopes 变成可变的，`writeAttempt` 返回**同一个** env 对象，所以改写器只能比较 **body** 而不能比较 envelope 身份来判断 `changed`。同时 driver 对 hook 的防御性 clone 也被移除了（`driver.ts:488-489`：「the core trusts hooks」）。这是为性能牺牲可推理性的决定，**你方在 Python 侧没有同样的压力，不必跟进**。
6. **hook 只是单点补丁，不是外置改写器**（第 5.3 节）。若你方想要「外置」，照抄 hook 的加载机制（配置声明 + 热重载 + warn-continue）是对的，但**接口应该是「注册一组改写器」而不是「填五个固定叶子」**。
7. **`exchange` 的 L1×L2 调用语义**（`src/lib/pipeline/hooks/README.md` 的两条警告之一）。挂载点被塞进 retry loop 内部，导致有状态的 hook 作者必须自己数调用次数。这是挂载点位置选错后用文档打补丁。

### 8.3 对 Python 侧的具体建议

如果目标是「把兼容性修复外置成可插拔、可声明、可独立演进的机制」，我的判断是：**照抄它的接口形态（`name / order / appliesTo / transform+flush / transformWhole`）与 order 契约文化，但把它没做的三件事补上**：

1. **给改写器一个统一的配置面**——照搬 retry strategy 的 `configKey` + `<section>.<name>.{enabled}` 形状，并在 schema 里穷举合法键。顺序是否要开放给配置需要你裁决：copilot-api-js 的 order 注释证明顺序是**硬正确性约束**而非偏好，我倾向于**不开放顺序配置**，只开放启停，并让启停组合被测试覆盖。
2. **请求侧与响应侧的观测对称**——要么两边都进 transform 图，要么两边都不进，别留一半。
3. **外置面的粒度是「注册一组改写器」**，而不是固定叶子。加载机制（配置声明路径 + 显式 reload 端点 + 失败不崩、保留旧版本、记 `lastReloadError`）可以直接照抄 `loader.ts:99-144`。

一个需要你裁决而我不该替你决定的点：**是否真的需要运行期外置加载**。copilot-api-js 给出的「静态注册保证装配确定性」的理由是成立的；如果你方的实际需求是「兼容性修复可以独立演进、独立测试、独立开关」，那么「编译期注册 + 声明式配置开关 + 独立文件 + 独立测试」已经满足，动态加载带来的确定性损失可能不划算。这条我记在这里，不自行下结论。

---

## 附：本报告未覆盖的部分

- WS 腿（`src/routes/responses/ws.ts`）的 hook 覆盖情况只从 `docs/todo/deferred-backlog.md:842` 读到「未接入」，未读代码核实。**[弱]**
- `CellAssembly` 的迁移状态（`MIGRATED_LEGS`）只读了文件头注释，未逐腿核实哪些已迁移。这影响的是「改写器由 cell 供给还是由 deps 供给」，不影响接口结论。**[中]**
- `docs/rfc/2026-07-14-symmetric-four-point-hooks.md` 与 `docs/spec/2026-07-12-upstream-hook-middleware.md` 只用 grep 扫过，未通读。本报告的挂载点清单以代码为准。
