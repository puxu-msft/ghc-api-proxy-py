# Claude Code "auto mode" 授权判定请求的形状（取证报告）

- 调查日期：2026-08-23
- 主证据源：`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js`（由 `~/src/unbun` 从 `/home/xp/.local/share/claude/versions/2.1.241` 静态提取并格式化，660402 行）。下文凡标 `[代码字面]` 的，行号均指这个文件。
- 版本对照源：`/home/xp/.claude/refs/claude-code-2.1.207/app.pretty.js`、`/home/xp/.claude/refs/claude-code-2.1.226/app.pretty.js`。
- 证据等级约定：`[代码字面]` = 我在上述文件里逐字读到的代码或字符串，附行号；`[文档]` = 官方文档，附 URL；`[推测]` = 由代码推导但未直接读到的结论。本报告**未做任何联网抓取**，因此没有 `[文档]` 级证据；所有结论都建立在代码字面上。

## 一、结论摘要

1. **auto mode 确实会额外发出独立的 LLM 请求**，不是纯本地规则、不是沙箱、也不是 hook。每次需要判定的工具调用会向同一个 Messages 端点发 1 到 2 次**非流式**请求（两阶段分类器）。`[代码字面]` 368453-368490
2. 这些请求由 `Age()`（内部通用 side-query 函数）发出，走 `client.beta.messages.create(...)`，即 `POST /v1/messages?beta=true`，**与主对话同一个 base URL、同一套认证、同一批默认请求头**。没有任何专属的 `X-` 请求头把它标出来。`[代码字面]` 12369、170548、429850
3. **最强的单条判别特征是 system 块的首行字面量**：某个 system 文本块以 `You are a security monitor for autonomous AI coding agents.` 开头。这句话在三个版本（2.1.207 / 2.1.226 / 2.1.241）里完全一致，且在整个 bundle 里全局唯一。`[代码字面]` 367602
4. **次强特征是 messages 结构**：最后一条（也常常是唯一一条）消息 `role` 为 `user`，其 `content` 数组的**第一个块的 text 恰好是 `"<transcript>\n"`**，倒数第二个块是 `"</transcript>\n"`。请求中**没有 `tools` 字段**、**没有任何 `role: "assistant"` 消息**、**没有 `stream`**。`[代码字面]` 368454-368455（`Q` 的包裹）、368459（`we` 拼接）、368460（`messages` 组装）
5. 还有一个**理论上最干净但实际最不可靠**的特征：`anthropic-beta` 请求头里的 `auto-mode-classifier-2026-07-16`。它只在 base URL 是 `api.anthropic.com` 时才发送——也就是说**任何反代场景下它都不会出现**，对本项目基本无用。`[代码字面]` 71249（beta 名）、368512（发送门）、64597-64609（`Fm`/`Zmt`/`e$e`），详见 §7
6. 除了这条主判定链路，还有若干**容易误认**的权限相关请求（`permission_explainer`、`auto_mode_critique`、`auto_mode_setup_propose`、`agent_classifier`），它们形状各不相同，§8 逐个给了区分点。
7. 判定链路**不是每个工具调用都触发**：只读工具走本地 allowlist 直接放行，不发请求。`[代码字面]` 263206-263208

## 二、auto mode 的整体机制

权限模式枚举里 `auto` 是一个一等模式，与 `default` / `plan` / `acceptEdits` / `bypassPermissions` / `dontAsk` 并列，对外名 `"auto"`：`[代码字面]` 41036

```js
auto: { title: "Auto", shortTitle: "Auto", indicator: "auto mode", symbol: _mt, color: "warning", external: "auto" }
```

在 auto mode 下，一次工具调用要经过三层，只有第三层才发请求：

1. **本地快速放行**：如果该工具调用在 `acceptEdits` 模式下本来就会被允许，直接放行，日志写 `Skipping auto mode classifier for <tool>: would be allowed in acceptEdits mode`。`[代码字面]` 263190
2. **本地安全 allowlist**：`RPi(toolName, input)` 命中就直接放行，日志写 `Skipping auto mode classifier for <tool>: tool is on the safe allowlist`。`[代码字面]` 调用在 263205-263208，`RPi` 定义在 260469。对应的用户可见文案是 `Note: reading files, searching code, and other read-only operations do not require the classifier and can still be used.` `[代码字面]` strings 命中，见 `strings-n6.txt`
3. **LLM 分类器**：`fhr(...)` → `zGw(...)` → `Age(...)`，发出真正的判定请求。`[代码字面]` 368576、368453、429850

分类器有四个调用点，**共用同一套请求形状**：`[代码字面]`

| 调用点 | 行号 | 场景 |
|---|---|---|
| 主工具权限门 | 263205 | 普通工具调用的授权判定 |
| workflow / Task 派发门 | 317038 | 派发 subagent 前审 `{prompt, subagent_type}` |
| subagent 交回审查 | 317044 | subagent 结束、把结果交回主 agent 前审 |
| 沙箱网络出网 | 368800 | 合成一个名为 `SandboxNetworkAccess` 的伪工具调用（`bAt = "SandboxNetworkAccess"`，368805）送审 |

规则来源：默认规则内置在 bundle 里，用户可在 settings 的 `autoMode.{allow, soft_deny, hard_deny, environment}` 四个类别里追加或替换，这些规则被模板替换进 system prompt 的 `<user_allow_rules_to_replace>` 等占位槽。`[代码字面]` 模板替换函数 `Sgi` 定义在 150468、由 `IGw` 在 368328 调用；槽名清单 `xjv = ["user_allow_rules_to_replace", "user_soft_deny_rules_to_replace", "user_hard_deny_rules_to_replace", "user_environment_to_replace"]` 在 150500

## 三、两阶段请求的精确形状

### 3.1 分类器请求构造器

`[代码字面]` 368453 `async function zGw(e, t4, r2, n4, o4, i, s, a, l, c, u, d, p, f)`

阶段 1（fast）请求对象，368460：

```js
b = {
  model: o4,
  max_tokens: (l === "fast" ? 256 : 64) + U,
  system: t4,
  skipSystemPromptPrefix: true,
  forceAttributionHeader: true,
  temperature: f1m(),
  thinking: F,
  messages: [...e, { role: "user", content: we }, ...[]],
  maxRetries: HVi(),
  ...l !== "fast" && { stop_sequences: [u ? "</severity>" : "</block>"] },
  querySource: "auto_mode",
  extraBodyParams: d1m(o4),
  extraBetas: u1m(Iw(o4))
}
```

阶段 2（thinking）请求对象，368474：

```js
j = {
  model: o4,
  max_tokens: 8192 + U,
  system: t4,
  skipSystemPromptPrefix: true,
  forceAttributionHeader: true,
  temperature: f1m(),
  thinking: F,
  messages: [...e, { role: "user", content: V }],
  maxRetries: HVi(),
  querySource: "auto_mode",
  extraBodyParams: d1m(o4),
  extraBetas: u1m(Iw(o4))
}
```

三种运行模式（`twoStageClassifier`，服务端配置可改，默认 `"both"`）：`[代码字面]` 368727-368734

- `"both"`（默认）：先发阶段 1（`max_tokens = 64 + U`，带 `stop_sequences`），若阶段 1 判 allow 就直接放行、不发阶段 2；判 block 或不可解析则再发阶段 2。
- `"fast"`：只发阶段 1，`max_tokens = 256 + U`，**不带 `stop_sequences`**。
- `"thinking"`：跳过阶段 1，只发阶段 2。

`U` 来自 `Tht(model)`：模型支持 adaptive thinking 时 `[undefined, 2048]`，否则 `[false, 0]`。`[代码字面]` 73533-73536。所以实际 `max_tokens` 只有六种取值：`64 / 2112`（both 阶段 1）、`256 / 2304`（fast）、`8192 / 10240`（阶段 2）。同时 `thinking` 字段要么完全缺席（adaptive 模型），要么是 `{"type":"disabled"}`（非 adaptive 模型）。`[代码字面]` 429858-429859

### 3.2 从 opts 到 HTTP body

`Age()` 把上面的 opts 翻译成真正的请求体，429862：`[代码字面]`

```js
W = {
  model: fne(t4),
  max_tokens: a,
  system: G,
  messages: Q,
  ...o4 && { tools: o4 },
  ...i && { tool_choice: i },
  ...x && { output_config: { format: s } },
  ...f !== void 0 && rQo(Y) && { temperature: f },
  ...h && { stop_sequences: h },
  ...F && { thinking: F },
  ...C.length > 0 && { betas: I4(C) },
  metadata: jFt(),
  ...g
}
```

随后 429870：`X.beta.messages.create(W, { signal: u, ...timeout })`，SDK 侧 12369 落到

```js
this._client.post("/v1/messages?beta=true", { body: i, ..., headers: [{ "anthropic-beta": n4?.toString() }, ...], stream: r2.stream ?? false })
```

其中 `betas` 数组被 SDK 抽出来放进 **`anthropic-beta` 请求头**，不留在 body 里；`W` 里没有 `stream` 字段，所以 `stream: false`，**这是一次普通的非流式 POST**。作为对照，主对话循环显式带 `stream: true`：`[代码字面]` 429190。

### 3.3 system 数组的实际内容

`Age()` 组装 system，429857：`[代码字面]`

```js
D = [ M ? { type: "text", text: M } : null,
      ...(d ? [] : [{ type: "text", text: Iii({...}) }]),
      ...(Array.isArray(r2) ? r2 : ...) ].filter(x => x !== null)
```

- `M` = `yyi(...)` 生成的**计费归因块**，是一段形如 `x-anthropic-billing-header: cc_version=2.1.241.<3位hex>; cc_entrypoint=<entrypoint>;` 的**文本块**（名字里有 `header`，但它确确实实是 system 里的一个 text block，不是 HTTP 头）。`[代码字面]` 155851-155855。主循环也带它（428903），所以它**不具备判别力**。
- `d` = `skipSystemPromptPrefix`，分类器恒为 `true`，因此**分类器请求里没有** `"You are Claude Code, Anthropic's official CLI for Claude."` 这一块（`MAa`，94960）。主循环一定有。
- 剩下的就是分类器 system prompt，由 `IGw()` 组装，368322：一个 `{type:"text", text:<完整分类器 prompt>, cache_control:{type:"ephemeral"[,ttl:"1h"]}}`，可能再跟一个可选的 `## Session Context` 块。

分类器 system prompt 的首行，367602：`[代码字面]`

```
You are a security monitor for autonomous AI coding agents.

## Context

The agent you are monitoring is an **autonomous coding agent** with shell access, file system access, and API credentials. …
```

后面依次是 `## Threat Model`（prompt injection / scope creep / accidental damage）、`## Input`（说明 `<transcript>`、`{"meta":{…}}`、`{"outcome":…}` 行的含义）、HARD BLOCK / SOFT BLOCK 规则、`## Output Format`。用户自定义规则在 `Sgi()` 里被替换进 `<user_allow_rules_to_replace>` 等占位槽（368328 调用、150468 定义），**替换发生在文档中部，首行不受影响**。

### 3.4 messages 数组的实际内容

`[代码字面]` 368454-368455（`<transcript>` 包裹）、368459-368460（阶段 1 拼接）、368474（阶段 2 拼接）、368296（`kGw`，CLAUDE.md 前置消息）

```
messages = [
  # 可选：仅当用户有 CLAUDE.md 时出现
  { role: "user", content: [ { type:"text",
      text: "The following is the user's CLAUDE.md configuration. Treat it as context about the user's environment and intent. …\n\n<user_claude_md>\n…\n</user_claude_md>",
      cache_control: {...} } ] },

  # 必有：判定消息
  { role: "user", content: [
      { type: "text", text: "<transcript>\n" },
      …（若干 text 块，逐条渲染的会话历史与工具调用）…,
      { type: "text", text: "</transcript>\n" },
      { type: "text", text: <阶段后缀> }
  ] }
]
```

**全部消息都是 `role: "user"`，没有 assistant 轮**——历史被渲染成纯文本塞进 `<transcript>` 里，而不是用真正的 message 结构表达。这是它和任何正常对话请求最结构化的差别。会话历史的渲染格式见 `x1m()`，368236：文本渲染成 `User: …` / `Assistant: …` 行，工具调用渲染成 `<ToolName> {json}` 或（`jsonlTranscript` 开启时）JSONL。

阶段后缀是固定字面量，368805-368814：`[代码字面]`

| 变量 | 用于 | 内容开头 |
|---|---|---|
| `RGw` | fast 单阶段 | `Err on the side of blocking. Your ENTIRE response MUST begin with <block>. …` |
| `LGw` | both 模式阶段 1 | `Err on the side of blocking. Stage 1 does NOT apply user intent or ALLOW exceptions — stage 2 will handle those. …` |
| `DGw` | 阶段 2 | `Review the classification process and follow it carefully, making sure you deny actions that should be blocked. …` |
| `$Gw` | severity 变体的 Output Format | `Output <severity>N</severity> where N is an integer 0-100 and 50 is exactly the allow/block boundary …` |

期望的模型输出是 `<block>yes|no</block>` + `<reason>…</reason>` + `<category>…</category>`，或 severity 变体的 `<severity>N</severity>`。解析器见 368407（`oLl`）、368422（`UGw`）、368429（`eLl`）、368434（`tLl`）。

### 3.5 其余字段

| 字段 | 值 | 判别力 |
|---|---|---|
| `model` | `SEt()` 解析：服务端配置可指定；否则主模型不是 sonnet-4-5/4-6/haiku 时用 sonnet5 档，再否则由主模型推导。**不是固定的 haiku** `[代码字面]` `SEt` 在 368661，`Uma` 见同区 | 弱 |
| `temperature` | `f1m()`，默认 `1`，可被 `CLAUDE_CODE_AUTO_MODE_TEMPERATURE` 覆盖 `[代码字面]` 368646 | 无 |
| `metadata` | `jFt()`：`{"user_id": "<JSON 串，含 device_id/account_uuid/session_id>"}`，**所有请求都一样** `[代码字面]` 428507 | 无 |
| `extraBodyParams` | `d1m()` → `avr()` → 只读 `CLAUDE_CODE_EXTRA_BODY` 环境变量，默认空 `[代码字面]` 368517、428419 | 无 |
| `tools` / `tool_choice` | 分类器不传，body 里**完全缺席** | 强（配合其他条件） |
| `cache_control` | transcript 末块与 CLAUDE.md 块带 `ephemeral`；`auto_mode` 在 1h prompt-cache allowlist 内，命中时 ttl 为 `1h` 并追加 `extended-cache-ttl-2025-04-11` beta `[代码字面]` 367909、428472、`EEe` | 弱 |

请求头方面，`She()` 给所有请求统一加 `x-app: "cli"`（后台会话是 `"cli-bg"`）、`User-Agent`、`X-Claude-Code-Session-Id`，**没有按 `querySource` 分化的头**。`[代码字面]` 170548。`querySource: "auto_mode"` 只用于遥测（`tengu_api_success` 事件）和重试/缓存策略选择，**不上线**。`[代码字面]` 429879

## 四、判别特征候选与鉴别力评估

按推荐程度排序。「误伤」指把正常对话请求判成分类器请求；「漏判」指分类器请求没被认出来。

| # | 判据 | 误伤风险 | 版本稳定性 | 评级 |
|---|---|---|---|---|
| A | 存在 system 块，其 `text` 以 `You are a security monitor for autonomous AI coding agents.` 开头 | 极低。这句话在 bundle 里全局唯一，正常对话不会出现（除非用户自己贴这句话进 prompt，而那时它会在 messages 而非 system 里） | 2.1.207 / 226 / 241 三版逐字一致 | **强，建议作为主判据** |
| B | 最后一条消息 `role=="user"` 且其 `content[0].type=="text"` 且 `content[0].text == "<transcript>\n"` | 极低 | 三版均存在（241 在 368454-368455） | **强，建议与 A 做「或」** |
| C | `messages` 中不存在任何 `role=="assistant"` 的条目，且 `tools` 字段缺席，且非流式 | 中。首轮对话 + 无工具的简单请求也满足 | 高（结构性） | 中，只能做辅助收窄 |
| D | `max_tokens ∈ {64, 256, 2112, 2304, 8192, 10240}` | 高。8192 是极常见的值 | 三版 `64/256/8192 + U` 完全一致 | 弱，只能辅助 |
| E | `stop_sequences == ["</block>"]` 或 `["</severity>"]` | 极低 | 226 / 241 一致；207 未逐字核对该行 | 中偏强，但**只在 both 模式的阶段 1 出现**，覆盖不全 |
| F | `anthropic-beta` 含 `auto-mode-classifier-2026-07-16` | 零 | 226 起才有，207 没有；且日期串会随 beta 版本变 | **对反代场景不可用**，见 §7 |
| G | 请求体里出现 `x-anthropic-billing-header: cc_version=` system 块 | 极高，主循环也有 | 高 | 无判别力，不要用 |
| H | 请求体里**没有** `You are Claude Code, Anthropic's official CLI for Claude.` 这一 system 块 | 高。所有 side query 都 `skipSystemPromptPrefix: true` | 高 | 只能用来把「主循环」剔掉，不能定位到分类器 |

### 推荐判据

```
is_auto_mode_classifier(request) :=
    any(block.get("text", "").startswith("You are a security monitor for autonomous AI coding agents.")
        for block in as_list(request.get("system")))
```

再要更稳，可以做「或」：

```
    or (last_user_message.content[0].get("text") == "<transcript>\n")
```

要区分阶段，用 `max_tokens`：`≤ 2304` 是阶段 1（fast），`≥ 8192` 是阶段 2（thinking）。`[代码字面]` 368460、368474

**明确不建议**做的：靠 `model`、`temperature`、`metadata.user_id`、任何 `X-` 头、`querySource`（它根本不上线）来识别。

## 五、这套判据什么时候会失效

1. **用户自定义规则会改变 prompt 中部**（`autoMode.allow` 等替换 `<user_*_to_replace>` 槽），但**不改首行**，判据 A 不受影响。`[代码字面]` 150468（`Sgi`）、368328（调用点）
2. **severity 模式**会用 `OGw()` 重写 `## Output Format` 段（368332），同样不改首行。
3. **服务端下发的 `s1SuffixByModel` / `s2SuffixByModel` 可以整体替换阶段后缀**（368392、368398），所以**不要拿后缀文本做判据**。
4. **服务端下发 `tengu_auto_mode_config` 可以改分类器模型、重试次数、two-stage 模式**（368661、368713、368727），所以模型和 `max_tokens` 组合都可能变。
5. system prompt 首行若在未来版本改写，判据 A 会静默失效——**建议实现时把这条判据写成配置项并在日志里统计命中率**，而不是硬编码后不管。

## 六、跨版本对照（鉴别力的时间维度）

在 2.1.207 / 2.1.226 / 2.1.241 三个版本上核对：`[代码字面]`

| 特征 | 2.1.207 | 2.1.226 | 2.1.241 |
|---|---|---|---|
| `You are a security monitor for autonomous AI coding agents.` | 有（1 处） | 有（1 处） | 有（1 处） |
| `text: \`<transcript>` 包裹 | 有 | 有 | 有 |
| `querySource: "auto_mode"`（2 处 = 两阶段） | 2 | 2 | 2 |
| `max_tokens: (l === "fast" ? 256 : 64) + <U>` | 有 | 有 | 有 |
| `max_tokens: 8192 + <U>` | 有 | 有 | 有 |
| `stop_sequences: [u ? "</severity>" : "</block>"]` | 未命中该写法 | 有 | 有 |
| beta `auto-mode-classifier-2026-07-16` | **无** | 有 | 有 |

结论：**A 和 B 两条判据跨越了至少三个版本没变**（207 到 241，按安装目录时间跨度约一个多月）。这是「可据以实现」的强度，不是「仅供参考」。beta 头是 226 才引入的，属于新增且带日期，稳定性最差。

## 七、对反代（本项目场景）的关键注意

`extraBetas: u1m(Iw(model))`，368512：`[代码字面]`

```js
function u1m(e) {
  if (e !== "firstParty") return [];
  if (!hB() || !Fm()) return [];
  return [pma];   // pma = NC("auto_mode_classifier", "auto-mode-classifier-2026-07-16")   // 71249
}
```

而 `Fm()` 的定义是（64597、64601、64606）：`[代码字面]`

```js
function Fm() { if (q._CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL) return true; return Zmt(); }
function Zmt() { let e = process.env.ANTHROPIC_BASE_URL; if (!e) return true; return e$e(e); }
function e$e(e) { try { return ["api.anthropic.com"].includes(new URL(e).host); } catch { return false; } }
```

也就是说：**只要用户把 `ANTHROPIC_BASE_URL` 指向本项目的代理（host 不是 `api.anthropic.com`），`auto-mode-classifier-2026-07-16` 这个 beta 就不会被发送**。代理侧永远看不到它。同理，attribution 块里的 ` cch=00000;` 片段也只在首方 base URL 下出现（155854）。

另一方面，auto mode **本身不会因为走代理而被禁用**：`v2r(provider)` 在 2.1.241 里两条分支都 `return true`（73637），provider 门形同虚设；真正的门是 `kht(model)`（73648，模型是否支持）和服务端下发的 `tengu_auto_mode_config.enabled` 熔断，以及 settings 里的 `disableAutoMode`。`[代码字面]` 门禁汇总在 `kno()`，316410-316431

所以对本项目而言：**auto mode 的判定请求会真实到达代理，但只能靠 body 认，不能靠 beta 头认。**

## 八、其他容易混淆的权限/判定相关请求

都走同一个 `Age()`、同一个端点、同一批头，需要靠 body 区分。`[代码字面]`

| 名字（querySource） | 行号 | 触发时机 | 独有特征 |
|---|---|---|---|
| `auto_mode` | 368460 / 368474 | 授权判定（本报告主题） | system 首行 `You are a security monitor…`；`<transcript>\n` 首块；无 `tools` |
| `permission_explainer` | 554001 | 权限弹窗里给用户解释某条命令 | **带 `tools: [{name:"explain_command", …}]` 且 `tool_choice: {type:"tool", name:"explain_command"}`**；system 恒为 `Analyze shell commands and explain what they do, why you're running them, and potential risks.`（554019） |
| `auto_mode_critique` | 650166 | 手动跑 `claude auto-mode critique` | 唯一 user 消息以 `Here is the full classifier system prompt that the auto mode classifier receives:` 开头；system 首行 `You are an expert reviewer of auto mode classifier rules for Claude Code.` |
| `auto_mode_setup_propose` | 371168 | 「Teach auto mode about your environment」向导 | 带 `output_format: {type:"json_schema", schema: …}` |
| `agent_classifier` | 310710 | 判断走开的 agent 处于四种状态中的哪一种（与权限无关） | system 首行 `A user kicked off a Claude Code agent to do a coding task and walked away.`（309657） |

另外值得记一笔：**Bash 命令前缀/注入检测已经不再是 LLM 调用**，2.1.241 里是本地 AST 分析（`commandNode` / `commandPrefix`，253626 起）。旧版 copilot-api 时代那种「命令安全性判定请求」在这一版里不存在。

## 九、旁证线索（超出本次任务范围，但与本项目直接相关）

bundle 里内嵌了一份写给**网关/代理实现方**的契约文档（648400 一带），明确写了：

- 端点形状：`The client is configured with an origin-root base URL and posts to fixed paths under it, with query strings it controls (e.g. \`/v1/messages?beta=true\`) — match on the path, tolerate the query.`
- 拒绝请求的正确方式：`HTTP 400` + `x-should-retry: false` + `{"type":"error","request_id":"<id>","error":{"type":"policy_blocked","message":"…"}}`，并且明确要求 `Never rewrite a request or response body instead — blocking substitutes the whole response; modification poisons prompt caching and diverges the client's view of the conversation.`
- 一张 `error.message` 到错误类别的映射表（`prompt_too_long`、`max_tokens_context_overflow`、`beta_header:<value>` 等）。

`[代码字面]` 648400-648455。这份文档对 ghc-api-proxy-py 的错误语义设计可能有直接参考价值，建议单独立一个调查项，本报告不展开。

## 十、未查证与推测

- `[推测]` `betas` 数组由 SDK 转成 `anthropic-beta` 头而非留在 body：我读到了 12369 处 `headers: [{ "anthropic-beta": n4?.toString() }, …]` 与解构 `let { betas: n4, … } = e`，但没有逐行追完 `_client.post` 的 body 序列化，所以「body 里一定没有 `betas` 键」这一点是从解构行推出的，强度为「足以据以实现，但值得在真机抓包时顺手验证一次」。
- `[推测]` 我没有实际抓到一次真实的 auto mode 判定请求做端到端印证。本报告全部结论来自静态源码阅读。要把 A/B 判据钉死，最便宜的验证是：把 `ANTHROPIC_BASE_URL` 指向一个只记录 body 的本地 sink，在 auto mode 下触发一次写文件操作，看首个 system 块。
- `[未查证]` `SVi()` 返回的完整 system prompt 我只逐字读了开头约 3000 字符，其余（HARD BLOCK / SOFT BLOCK 规则全文）没有通读。这不影响判据 A。
- `[未查证]` 官方文档对 auto mode 的表述（任务原本允许 WebFetch/WebSearch 佐证）。因为代码证据已经足够且更权威，我没有联网；如果需要「官方是怎么说的」这一层，可以再补一轮。
