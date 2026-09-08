# Claude Code 客户端对 `web_fetch` 的行为取证（260830）

调查目标：本项目准备把「上游不支持 server tool 时合成一个 200 的失败工具结果块对」这套做法从 `web_search` 扩到 `web_fetch`。扩之前必须先回答一个前置问题——**真实的 Claude Code 客户端到底会不会向服务端声明 `web_fetch` server tool**。如果不会，这条合成路径对它就根本不可达，处置方式的选择完全不同。

一句话结论：**Claude Code 的 `WebFetch` 是纯客户端执行的普通 function tool，它从不在 `tools[]` 里发送任何 `web_fetch*` server tool 声明。**（证据等级：**强，可据此决策**——源码层与真实请求记录两条独立线互证，并跨 2.1.207 / 2.1.226 / 2.1.241 / 2.1.251 四个版本一致。）

---

## 0. 证据分级与来源

| 类别 | 标记 | 说明 |
|---|---|---|
| **客户端源码** | `[SRC]` | `~/.claude/refs/claude-code-<ver>/app.pretty.js`（`unbun` 抽取产物，带行号）。这是最强判据：它说的是「客户端会不会这么做」，而不是「我们有没有观测到它这么做」。 |
| **安装版二进制字面量** | `[BIN]` | `/home/xp/.local/share/claude/versions/2.1.251`（Bun 单文件）。只用于补上「已抽取的最新版 2.1.241」到「当前实际在跑的 2.1.251」这段版本差，且每条否定探针都配了对照探针。 |
| **真实请求记录** | `[REAL]` | 既有 Bun 服务的 `~/.local/share/copilot-api/history-v3-archive.db`，`v3_objects` 里 zstd 压缩的对象。只读打开（`file:...?immutable=1`），未做任何写入。 |
| **官方文档（客户端内自带）** | `[DOC]` | Claude Code 二进制里打包的 `claude-api` 技能 markdown。**它描述的是 Anthropic API 协议，不是 Claude Code 的行为**，见 §1.3 的陷阱说明。 |

版本说明：`~/.claude/refs/` 下有 2.1.207、2.1.226、2.1.241 三份抽取产物；当前安装并在跑的是 **2.1.251**，无抽取产物，故用 `[BIN]` 字面量探针补差。

---

## 1. 问题 1（最关键）：Claude Code 会不会声明 `web_fetch` server tool？

### 1.1 答案：不会。它是客户端自己执行的普通 tool。证据等级：强

`[SRC]` `claude-code-2.1.241/app.pretty.js:429990` 一带，`WebFetch` 工具对象（内部标识 `YN`，名字常量在 `:145227` `var xp = "WebFetch"`）的 input schema 定义在 `:429991`：

```js
hfw = ve(() => pi({ url: O().url().describe("The URL to fetch content from"), prompt: O().describe("The prompt to run on the fetched content") }))
```

它的 `call()`（`:303929`–`:303986`）自己完成整个抓取：调 `L1i(...)` 取内容，分支处理 `provenance_denied` / `http_error` / `redirect` / 二进制落盘，再用一次嵌套模型调用（`lgr`）把 `prompt` 应用到抓下来的正文上。结果通过

```js
mapToolResultToToolResultBlockParam({ result: e }, t4) {
  return { tool_use_id: t4, type: "tool_result", content: e };
}
```

交回主对话——**一个普通的 `tool_result`**。

`L1i` 本身（`:283180`）只有两条出口：CCR 远端会话走 `web-fetch-ccr-proxy`（一次带外的 HTTP 代理调用），否则客户端直接 `fetch`（`http:` 升级成 `https:`，再做 DNS preflight）。**两条都不经过 Messages API 的 `tools[]`。**

旁证同向：`:326608` 的合规门返回的措辞是「arbitrary-URL egress is disabled by your organization's compliance policy」——**出口流量是从客户端出去的**，这只有在客户端自己抓取时才说得通。

### 1.2 决定性的否定证据：请求里根本没有塞 server tool 声明的口子

`[SRC]` 请求体的 `tools` 数组在 `:428906` 拼成：

```js
let de = ..., oe = f.length > 0, ee = [...i.extraToolSchemas ?? []];
if (_) ee.push({ type: "advisor_20260301", name: "advisor", model: _ });
let se = [...M, ...ee], ...
```

两个来源，逐一堵死：

- **`M`** 由 `:428868` 对每个已注册工具调 `aVi()` 生成。`aVi`（`:427734`–`:427758`）的**唯一返回形状**是 `{ name, description, input_schema, ...strict, ...eager_input_streaming, ...defer_loading, ...cache_control }`——**它在任何分支上都不产出 `type` 字段**。所以 `M` 里不可能出现 server tool。
- **`ee`** 只有两个来源：`advisor_20260301`，以及 `extraToolSchemas`。而 `extraToolSchemas` 在整份 bundle 里**只有一个生产者**：

  ```
  rg 'extraToolSchemas' → 2 hits：:331671（唯一写入点）、:428906（唯一读取点）
  ```

  `:331671` 就是 WebSearch 工具的子请求，写入的值是 `{ type: "web_search_20250305", name: "web_search", allowed_domains, blocked_domains, max_uses: 8 }`。

**跨版本一致**：`extraToolSchemas` 在 2.1.207（`:281597`）与 2.1.226（`:333021`）同样是 2 处命中、同样只有 web search 那一个生产者。

结论：**Claude Code 在任何代码路径上都无法把 `web_fetch` server tool 放进请求。** 证据等级：强，可据此决策。

### 1.3 一个必须点破的取证陷阱：`web_fetch_20260209` 确实在二进制里，但它是文档

`[DOC]` `rg 'web_fetch_20'` 在 2.1.241 里有 7 处命中（`:584898`、`:589828`–`:589846`、`:590614`、`:590844` 等）。**逐一核对后，全部落在客户端自带的 `claude-api` 技能 markdown 字符串里**，例如 `:589824` 起：

```
## Server-Side Tools: Web Search and Web Fetch
...
[ { "type": "web_search_20260209", "name": "web_search" },
  { "type": "web_fetch_20260209", "name": "web_fetch" } ]
```

那是**写给使用者看的 Anthropic API 用法文档**，不是 Claude Code 自己发的请求。2.1.207、2.1.226 的 `web_fetch_20` 命中同样**全部**在这段 markdown 里，没有一处在代码里。

> 只做 `rg web_fetch` 数命中数会得到完全相反的结论。判据必须是「这个字符串出现在代码里还是数据里」。

### 1.4 补上 2.1.241 → 2.1.251 的版本差

`[BIN]` 对当前安装并在跑的 `/home/xp/.local/share/claude/versions/2.1.251` 做字面量探针（`rg --count-matches --text`）：

| 探针 | 命中 | 作用 |
|---|---|---|
| `web_fetch_20` | **0** | 目标否定探针 |
| `web_search_20250305` | 3 | **对照**：证明 server tool 声明字面量在这个二进制里可见 |
| `Perform a web search for the query` | 2 | **对照**：证明 web search 子请求那套还在 |
| `The URL to fetch content from` | 2 | **对照**：证明 WebFetch 仍是带 `input_schema` 的普通工具 |
| `Server-Side Tools: Web Search and Web Fetch` | **0** | 证明 §1.3 那段技能 markdown **不在** 2.1.251 里 |

最后一行解释了为什么 `web_fetch_20` 在 2.1.251 是 0：在 2.1.241 里它**只**出现在那段 markdown 中，而 2.1.251 不再打包它。前三行的对照证明这组探针有分辨力，`web_fetch_20 = 0` 不是假零。

结论：**当前在跑的 2.1.251 上，结论同样成立。** 证据等级：强。

### 1.5 真实请求记录的独立佐证

`[REAL]` 扫 `history-v3-archive.db` 的全部 9820 个 `v3_objects`，逐个 zstd 解压后按 JSON 结构分类（脚本 `/tmp/classify_tools.py`，一次性，未入库）：

- **带 `input_schema` 的普通工具声明**：命中 `WebFetch` **2 次**、`WebSearch` **3 次**（含一个 `defer_loading: true` 变体）。`WebFetch` 逐字形态：

  ```json
  {"description":"Fetches a URL, converts the page to markdown, and answers `prompt` against it using a small fast model.\n\n- Fails on authenticated/private URLs — use an authenticated MCP tool or `gh` for those instead.\n- HTTP is upgraded to HTTPS. Cross-host redirects are returned to you rather than followed; call again with the redirect URL.\n- Responses are cached for 15 minutes per URL.","eager_input_streaming":true,"input_schema":{"$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"properties":{"prompt":{"description":"The prompt to run on the fetched content","type":"string"},"url":{"description":"The URL to fetch content from","format":"uri","type":"string"}},"required":["url","prompt"],"type":"object"},"name":"WebFetch"}
  ```

  **注意它没有 `type` 字段**——本项目 `server_tools.py` 的 `_rejected_type()` 遇到 `type` 缺失即返回 `None`，所以这个声明一直原样转发，不受任何剥离逻辑影响。

- **带 `type` 而无 `input_schema` 的声明**：只有 `tool_search_tool_regex_20251119` 一条（1 次）。**没有任何 `web_fetch*`。**

- `web_fetch_20` 与 `web_fetch_tool_result` 两个字面量在这个库里各命中 4 次，逐条核对后**全部是消息正文**（会话里被载入的 `claude-api` 参考文档），不是声明也不是响应块。

**这一节的覆盖面必须说清楚（否则会被读成比它更强）**：该库有 145783 条 operation，却只剩 9820 个对象——绝大多数请求体已被内容 GC 清掉。它证明的是「在**留存下来的**样本里，WebFetch 是普通工具，且没有 web_fetch server tool 声明」，不是「历史上从未有过」。证据等级：**中等偏强**，与 §1.1–§1.4 的源码结论同向，作为佐证而非独立判据。

> 这里踩到一个坑，记下来：`v3_objects.canonical_gz` 是 **zstd**（magic `28 b5 2f fd`），不是 gzip。第一版脚本因为环境里没装 `zstandard` 模块，把 9820 个对象**全部**归到 undecodable，于是所有探针都报 0——**一个和「真的没有」逐字符相同的假零**。改用 `uv run --no-project --with zstandard` 后才拿到真实数字。任何后续复现这套扫描的人，请先看 `undecodable` 计数。

---

## 2. 问题 2：如果它发 server tool 声明，是独立子请求还是混在正常请求里？

**不适用——前提不成立。** §1 已证明它根本不发。

但为了让对照关系清楚，把 web search 那一侧的机制写全（`[SRC]`，这是对 `../hosted-web-search/reports/260820-claude-code-websearch-request-forensics.md` 那份从请求侧做的取证的源码侧确认）：

WebSearch 的 `call()`（`:331669`–`:331672`）在客户端接住主对话的 `tool_use{name:"WebSearch"}` 之后，另起一个 Messages 请求：

```js
let c = Cn({ content: "Perform a web search for the query: " + s }),
    u = { type: "web_search_20250305", name: "web_search", allowed_domains: e.allowed_domains, blocked_domains: e.blocked_domains, max_uses: 8 };
let f = XZr({ messages: [c], systemPrompt: Um(["You are an assistant for performing a web search tool use"]),
               thinkingConfig: { type: "disabled", mechanical: true }, tools: [],
               options: { toolChoice: { type: "tool", name: "web_search" }, extraToolSchemas: [u], querySource: "web_search_tool", enablePromptCaching: false, ... } });
```

`tools: []` + `extraToolSchemas: [u]` → 子请求的 `tools` 数组**长度恒为 1**。这与既有报告观测到的 190/190 样本逐字吻合。

**`WebFetch` 没有任何对应物**：它的 `call()` 里没有 `XZr`/子请求，没有 `extraToolSchemas`，`prompt` 的应用走的是 `lgr`（`querySource: "web_fetch_apply"`，`:283235`），那是一次**普通的、零工具的**摘要调用，请求里既没有 web_fetch 声明也没有 web_search 声明。

**这条对本项目有直接后果**：web search 的合成之所以有意义，是因为存在一个「`tools` 只有它一项」的子请求，剥离它会让请求退化成零工具从而静默伪造。`web_fetch` **没有这个结构**，所以那套论证一个字都搬不过来。

---

## 3. 问题 3：客户端怎么解析 `web_fetch_tool_result`？

### 3.1 它不解析。没有消费者，没有渲染器。证据等级：强

`[SRC]` 2.1.241 里 `web_fetch_tool_result` 共 4 处命中，逐一核对：

| 行号 | 位置 | 做了什么 |
|---|---|---|
| `:116847` | `zAv` 已知块类型表 | 只是「这是个已知的块类型」的字典键，供 `f1t()` 判定；`f1t` 的全部 5 个调用点（`:415055`、`:415076`、`:415099`、`:482694`、`:507964`）都是**遥测打标**，不做过滤 |
| `:273715` | 内容块指纹/哈希 switch | 空 `break`，穷尽性分支 |
| `:274117` | token 记账 switch | 计入 `r2.other` 桶 |
| `:417404` | 流式 spinner 状态 switch | `n4?.("tool-input")`，只切个状态 |

**四处全是对 SDK ContentBlock 联合类型的穷尽性 switch 分支，没有一处读它的 `content`。**

更进一步，**`web_fetch_tool_result_error` 与 `web_search_tool_result_error` 这两个字符串在整份 bundle 里零命中**（`rg` exit 1）。客户端从不按这个 type 名做匹配。

### 3.2 如果我们真把它合成进主对话，会发生什么

`[SRC]` TUI 的块渲染 switch（`:482765` 一带）分支是：`server_tool_use` / `advisor_tool_result` → 渲染 `Aus`；`tool_search_tool_result` → `null`；**`default` → `mfs(wdA, nO, Error("Unable to render message type: ..."))` 然后返回 `null`**。

`web_fetch_tool_result` 落在 `default`。`mfs`（`:482705`）的行为是：按块去重打一次 `unrenderable_block:<type>:<id>` 的 claim，然后 `He(r2)` 上报错误。

> 也就是说：**界面上什么都不显示，内部记一条错误。** 注意 `web_search_tool_result` 同样落在 `default`——两者对称，因为在 Claude Code 的设计里这两种块都不该进主对话。

流式接收侧（`:429340` 的 `content_block_start` switch）`default` 分支把未知块 `an[wi.index] = { ...wi.content_block }` **原样存进 assistant 消息**，不报错、不丢弃。

回传侧有一条本项目该知道的规则（`:418421`）：重建 `messages` 时，**`server_tool_use` 块如果在同一条消息里找不到任何带匹配 `tool_use_id` 的块，就会被删掉**（夹在两个 thinking 块之间时替换成 `[Tool use removed]` 文本，否则整个丢掉；若整条消息被清空则塞入 `[Tool use interrupted]`）。所以一对同消息内的 `server_tool_use` + `*_tool_result` 能通过这道过滤，孤立的 `server_tool_use` 不能。

### 3.3 「无条件抬头」是 WebSearch 独有的，`WebFetch` 没有

`[SRC]` 既有报告 §4.3 观测到的那个「无条件拼 `Web search results for query:` 抬头」，源码位置是 WebSearch 工具的 `mapToolResultToToolResultBlockParam`（`:331712`）：

```js
let { query: r2, results: n4 } = e, o4 = `Web search results for query: "${r2}"\n\n`;
```

它确实无条件执行，且结尾还会追加 `REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.`。

**`WebFetch` 的对应函数（`:303987`）是 `{ tool_use_id, type: "tool_result", content: e }`——零加工、零抬头。**

顺带补一条既有报告没写全的：WebSearch 的结果聚合函数 `tHw`（`:331561`）在遇到 `web_search_tool_result` 且 **`content` 不是数组**时，走的是

```js
let c = `Web search error: ${a.content.error_code}`; E(c, { level: "error" }); n4.push(c);
```

——把它当成一条**字符串结果项**推进结果列表，不抛异常、不重试。所以一个 `web_search_tool_result_error` 最终会以 `Web search results for query: "X"\n\nWeb search error: unavailable\n\n…` 的形态交回主对话。这是本项目现有合成路径的真实落地形态，**证据等级：强（源码直读）**，此前只有推断。

### 3.4 会不会重试？不会

`[SRC]` 全 bundle 中不存在任何按 `*_tool_result_error` 或 `error_code` 触发重试的代码。失败的 tool 只是一个内容，主对话模型可能自己再叫一次工具（那是模型行为，不是客户端机制）。

---

## 4. 问题 4：收到 HTTP 4xx/5xx 时重试几次？

### 4.1 源码给出的重试判据（证据等级：强）

`[SRC]` 重试与否由 `Ftw()`（`:273460`–`:273495`）判定，末段是一张干净的状态码表：

```js
if (!e.status) return false;
if (e.status === 408) return true;
if (e.status === 409) return true;
if (e.status === 401) return mjr(), true;
if (rWe(e))          return true;
if (e.status === 429) return !ds() || bjr() || M9f(e);
if (e.status && e.status >= 500) return true;
return false;
```

**HTTP 400 落到最后的 `return false`——不重试。** 另有 `Ptw = new Set([401, 407, 429, 404, 403, 413])`（`:273586`）用于「不可重试则考虑 fallback 模型」的判定。

重试次数上限 `Xpl()`（`:273508`）：默认 **10**（`btw = 10`）；设了 `CLAUDE_CODE_RETRY_WATCHDOG` 则 **300**（`vtw = 300`）；`CLAUDE_CODE_MAX_RETRIES` 可覆盖，非 watchdog 模式下被钳到 **15**（`qpl = 15`）。

所以，按状态码分：

| 我们返回 | 客户端传输层重试 |
|---|---|
| 400 | **0 次**（不可重试） |
| 403 / 404 / 413 | 0 次 |
| 408 / 409 | 重试，默认上限 10 |
| 429 | 通常重试（有配额相关的例外，见 `Utw` `:273539` 一带） |
| 5xx | 重试，默认上限 10 |

### 4.2 必须纠正的一条：「Claude Code 会把 HTTP 错误当传输故障重试三次」

这句话现在写在 `../anthropic-responses-bridge/hosted-web-search-spec.md:322`，并在 `../hosted-web-search/reports/260820-client-e2e-group.md:100`、`../hosted-web-search/reports/260820-closeout-loose-ends.md:210` 被复述。**按源码，它的归因是错的，数字也对不上。**

- 它的一手来源是 `260820-claude-code-websearch-request-forensics.md` §4.2 的 transcript 观测：主对话连续拿到 **3 条** `is_error` 的 `tool_result`（内容是 `API Error: 400 …`），之后模型改用 WebFetch。
- 那 3 次是**主对话模型自己又叫了 3 次 `WebSearch` 工具**，每次触发一个新的子请求、每次拿到 400。**不是传输层把同一个请求重试了 3 次**——按 §4.1，400 的传输层重试次数是 **0**。
- 方向也相反：真正会被传输层重试的是 5xx / 408 / 429，而那里的默认上限是 **10**，远大于 3。

**这不推翻「合成 200 优于返回 400」这个取舍**——3 次模型级重试同样是 3 个来回的浪费，且失败的 tool result 确实不触发客户端重试。但**理由的措辞必须改**，否则它会被当成一条关于传输层的事实继续复用，并在有人拿 5xx 做对照时直接失效。

建议改写为：*「返回 HTTP 错误时，Claude Code 的主对话模型会把它当成工具故障并重复调用该工具（实测连续 3 次后才降级），而一个失败的 tool result 不会触发重复调用；此外 5xx/408/429 还会被客户端传输层重试，默认上限 10 次。」*

处置权归属说明：`hosted-web-search-spec.md:322` 那句是本项目自己推导的客户端行为描述，不是用户裁决，按 `.claude/rules/00-development-workflow.md` 的「派生表由评审共识修正」应当直接改 Spec，**不要只记进待办台账**。本报告只做取证，不动 Spec；这条留给主会话执行。

---

## 5. 对「把合成扩到 `web_fetch`」的直接含义

这一节是**判断**，不是观测。

1. **对真实的 Claude Code，这条合成路径不可达。** 它不发 `web_fetch*` 声明（§1），所以我们的能力门永远不会在 web_fetch 上触发。为它写的合成代码在这个客户端上是死代码。
2. **web search 那套论证不能搬过来。** 合成之所以在 web search 上优于剥离，靠的是「子请求的 `tools` 只有一项，剥掉就退化成零工具 + 客户端无条件贴抬头 = 静默伪造」（§2、§3.3）。`web_fetch` 既没有子请求，也没有抬头拼接。**理由整体失效，不是弱化。**
3. **就算合成了，Claude Code 也读不懂。** 没有消费者、没有渲染器，落 `default` 分支后界面空白 + 内部错误上报（§3.1、§3.2）。这与 Spec §8.3 那条 2026-08-30 补入的限制（「合成的前提是客户端腿读得懂它」）是同一条道理的另一个实例，只不过这次读不懂的不是协议腿，而是**同一个协议里客户端从未实现的块类型**。
4. **别的客户端仍可能发。** 本报告只覆盖 Claude Code。任何直接用 Anthropic SDK 的调用方都可以按 `[DOC]` 里的写法发 `{"type":"web_fetch_20260209","name":"web_fetch"}`。所以「要不要支持 web_fetch」是一个**产品范围问题**，而不能再用「Claude Code 需要它」来论证。
5. **倾向（供裁决，非已决）**：对 `web_fetch` 不做合成，让它按既有 Error 契约归一为 error envelope 透传；理由是上面第 2、3 条，而不是「web_fetch 不重要」。若将来要为非 Claude Code 客户端支持它，判据应当是那个客户端的解析器，需要重新取证。

---

## 6. 我排除掉、认为不成立的可能性

逐条写下，含理由：

1. **「WebFetch 在某个 feature flag / 配置下会切换成 server tool」** —— 排除。堵口的不是某个分支，而是**形状**：`aVi()`（`:427734`）在所有分支上都不产出 `type` 字段，而 `extraToolSchemas` 全 bundle 只有一个生产者且写死了 web search（§1.2）。要出现 web_fetch server tool，必须新增代码，不是翻个开关。
2. **「远端/CCR 会话下 WebFetch 变成服务端工具」** —— 排除。`L1i`（`:283180`）的 CCR 分支走的是 `xKf(...)` 这个带外 HTTP 代理调用（错误标签 `web-fetch-ccr-proxy`），与 Messages API 的 `tools[]` 无关。
3. **「`mcp__workspace__web_fetch` 说明它是 server tool」** —— 排除。`:41488` 与 `:643689`（`{ Bash: "mcp__workspace__bash", WebFetch: "mcp__workspace__web_fetch" }`）是 cowork/workspace 场景把 WebFetch 映射到一个 **MCP 工具**。MCP 工具在 wire 上仍是带 `input_schema` 的普通工具，不是 Anthropic server tool。
4. **「bundle 里有 `web_fetch_20260209` 就说明它会发」** —— 排除，且这是本次最主要的误判陷阱。全部命中都在打包的 `claude-api` 技能 markdown 里（§1.3），2.1.251 更是连那段 markdown 都不再打包。
5. **「`AdA` 集合里有 `web_fetch` 说明客户端支持它」** —— 排除。`AdA`（`:482834`）的唯一用途是 `prg()`（`:482689`）给遥测打 allowlist 标签，命中就上报名字、不命中就上报 `"non-allowlisted"`。纯观测代码。
6. **「`JEw = new Set(["web_fetch","web_search"])` 是声明表」** —— 排除。`:330162` 紧邻 `/^claude[-_](?:for|in)[-_]chrome$/i` 与 `Claude_Preview`/`Claude_Browser`，属于浏览器扩展/权限分类的名字集合，不参与请求构造。
7. **「`zAv` 表里有 `web_fetch_tool_result` 说明有处理逻辑」** —— 排除。`zAv`（`:116847`）只喂 `f1t()`，5 个调用点全是遥测打标（§3.1），不过滤、不路由、不渲染。
8. **「既有 Bun 服务的历史库里没有 web_fetch 声明，所以从来没有过」** —— **不排除，但收窄**。该库 145783 条 operation 只剩 9820 个对象，覆盖率低（§1.5）。这条只作为同向佐证，独立结论以源码为准。
9. **「客户端收到 `web_fetch_tool_result_error` 会重试」** —— 排除。这两个 `*_tool_result_error` 字面量全 bundle 零命中，不存在按它触发的任何逻辑（§3.1、§3.4）。

**空清单声明**：以上 9 条即全部。没有「纯靠推理排除但没写下来」的候选。

---

## 7. 没查到 / 查不了的

如实列出，不用推理填补：

- **2.1.251 的完整源码**：`~/.claude/refs/` 只到 2.1.241。2.1.251 只做了字面量探针（§1.4，带对照）。如果要在 2.1.251 上做行号级确认，需要先跑一次 `unbun` 抽取——本次未做（会产生约 100MB 落盘产物，属于需要授权的动作）。
- **`web_fetch` 在真实请求里的「历史上从未出现」**：做不到。既有服务的对象库已大量 GC（§1.5），且 2026-08-15 之后不再存 frame。能证明的上限是「留存样本里没有」。
- **本项目自己的 `~/.local/share/ghc-api-proxy/history.db`**：本次未扫。既有报告 §4.1 记载该库 8966 条里 `web_search` 命中 0；`web_fetch` 未单独查过。若要补，方法与 §1.5 相同。
- **Anthropic 官方线上文档**：本次未联网核对，`[DOC]` 一律取自客户端自带的技能 markdown。对本报告的四个问题而言官方文档没有增量——它描述协议能力，回答不了「Claude Code 发不发」。

---

## 附：本次用到的一次性脚本

均在 `/tmp`，未入库，只读：

- `/tmp/scan_webfetch.py` —— 字面量扫描（第一版，因缺 `zstandard` 产生假零，保留作为教训样本）
- `/tmp/classify_tools.py` —— 按 JSON 结构区分「普通工具声明」与「server tool 声明」的分类扫描，产出 §1.5 的表

运行方式：`cd /tmp && uv run --no-project --with zstandard python /tmp/classify_tools.py <db>`。所有 db 均以 `file:...?immutable=1` 打开。
