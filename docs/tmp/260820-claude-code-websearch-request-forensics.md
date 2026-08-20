# Claude Code 的 web search 请求取证（260820）

调查目标：在裁决「剥离 `web_search_20250305` 声明」与「保留一个返回 `unavailable` 的替身工具」之前，先弄清楚 **Claude Code 真实发出的请求到底长什么样**。

一句话结论：**问题问错了对象**。`web_search_20250305` 从来不和普通工具一起出现在主对话请求里；它出现在 Claude Code 为「执行一次搜索」单独发起的**独立子请求**中，那个请求的 `tools` 数组**有且只有它一个**，`system` 只有两句话，`messages` 只有一条「Perform a web search for the query: X」。剥离它 = 把一个「只为调用这一个工具而存在的请求」变成一个「没有任何工具的请求」，而 Claude Code 会把返回的正文原样贴上 `Web search results for query: "..."` 的抬头交回主对话。

---

## 0. 证据分级与来源分类

本报告严格区分三类材料：

| 类别 | 标记 | 说明 |
|---|---|---|
| **真实客户端请求** | `[REAL]` | 从既有 Bun 服务的 `~/.local/share/copilot-api/history-v3*.db` 中，按 `stage=ingress, track=client` 重建出的客户端原始请求体。这是 Claude Code 实际发到 4141 端口的字节所对应的结构化记录。 |
| **真实客户端转录** | `[TRANSCRIPT]` | `~/.claude/projects/**/*.jsonl` 中的 `tool_use` / `tool_result` 记录。不是 API 请求，但能证明「主对话看到了什么」。 |
| **我们自己造的探针** | `[PROBE]` | `exp/260820-websearch-probe/raw/`、`tests/cassettes/`。手工构造，**不能**作为「Claude Code 会这么发」的证据。 |

**重建方法**（可复现）：history-v3 的 `v3_operations.manifest_gz`（zstd + JSON）里，`record.arena.payloads` 列出每个 payload 的 `origin.stage` / `origin.track`；`objectHashes[handle]` 指向 `v3_objects` 里的 **payload-skeleton**（`messages` / `system` / `tools` 均为 `null`），`payloadSequences[handle]` 给出每个数组字段的 `rootHash`，沿 `v3_sequence_nodes.parent_hash` 回溯即得数组元素（再套用 `overlays` 里的 `cache_control`）。脚本留在 `/tmp/recon.py`（一次性，未入库）。

> 注意：`tests/integration/recorded/from_history.py` 的注释里写着「history records no request body」。**那句话是错的**——history 不存请求的原始字节，但完整存了请求体的结构（skeleton + 序列）。本次取证正是靠这一点做的。这条应当回写到该文件。

**只读纪律**：所有 db 均以 `file:...?immutable=1` 打开，未做任何写入。

---

## 1. 主问题：系统提示提到 WebSearch 吗？

### 1.1 主对话请求：**没有提到**（强证据，可据此决策）

`[REAL]` 扫描 `history-v3-20260816-160151.db` + `history-v3-20260818-044224.db` 共 **2070 个 ingress 请求体**的 `system` 字段，用正则 `web[ _-]?search|WebSearch|web[ _-]?fetch|WebFetch` 匹配，命中三条：

- 1 条是下面第 2 节那个专用搜索子请求；
- 2 条是**用户自己写的 gpt-souls agent 提示词**（中文，「充分利用可用工具：`Read` 精读……`WebSearch`/`WebFetch` 联网查证」），属于用户资产，不是 Claude Code 的内建系统提示。

**Claude Code 自身的系统提示（不论 CLI 版还是 Agent SDK 版）从未提及 WebSearch。** 工具的存在完全由 `tools` 数组承载，`description` 里自带说明（见 1.2）。

推论（**中等强度，逻辑清晰但未做对照实验**）：主对话里不存在「提示说我有、工具列表里没有」的矛盾。就算我们把主对话里的某个 web 工具删掉，模型也不会因为系统提示的暗示而困惑。

### 1.2 主对话里的 WebSearch 是**普通 function tool**，不是 server tool

`[REAL]` 主对话请求（典型 `ntools=52`）里的声明，出现 **2020 次**：

```json
{
  "name": "WebSearch",
  "description": "Search the web. Returns result blocks with titles and URLs. US-only.\n\n- The current month is August 2026 — use this when searching for recent information.\n- `allowed_domains` / `blocked_domains` filter results.\n- After answering from results, end with a \"Sources:\" list of the URLs you used as markdown links.",
  "eager_input_streaming": true,
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "query": {"type": "string", "minLength": 2, "description": "The search query to use"},
      "allowed_domains": {"type": "array", "items": {"type": "string"}, "description": "Only include search results from these domains"},
      "blocked_domains": {"type": "array", "items": {"type": "string"}, "description": "Never include search results from these domains"}
    },
    "required": ["query"]
  }
}
```

同一形状还有一个 `defer_loading: true` 的变体（ToolSearch 延迟加载时），以及配套的 `WebFetch`（同样是普通 function tool）。

**关键点：这个对象没有 `type` 字段。** `server_tools.py` 的 `_rejected_type()` 遇到 `type` 缺失即返回 `None`，所以主对话里的 `WebSearch` / `WebFetch` **完全不受我们的剥离逻辑影响**，一直原样转发。这是对的。

---

## 2. 完整的 `web_search_20250305` 声明形态

`[REAL]` 全量样本：跨 5 个 db（`history-v3-260807`、`-260809`、`-260811`、`history-v3.db`、`-20260816-160151`），按 `summary_json LIKE '%Perform a web search for the query%'` 选出 **190 个操作**，逐个重建 ingress 请求体。

### 2.1 键集合：190/190 完全一致

```json
{
  "type": "web_search_20250305",
  "name": "web_search",
  "max_uses": 8,
  "allowed_domains": ["kernel.org", "man7.org", "git.kernel.org"],
  "blocked_domains": []
}
```

- `type` / `name`：190/190 恒为上述值。
- `max_uses`：**190/190 恒为 8**。
- `allowed_domains`：190/190 **均非空**（1 个域 152 次、2 个 29 次、3 个 8 次、5 个 1 次）。值来自主对话模型传给 `WebSearch` 的入参。
- `blocked_domains`：190/190 **均为空数组**（键存在，值 `[]`）。
- **`user_location`：190/190 从未出现。** `cache_control` 也从未出现在这个工具对象上。

### 2.2 `tools` 数组长度：190/190 都是 **1**

**没有任何一个样本把 `web_search_20250305` 和普通 function tool 混在一起发。** 这是本次取证最重要的一条事实。

### 2.3 同一请求的其他字段

`system`（三种变体，只有第一句随客户端形态变化，第二句恒定）：

| 次数 | `system` |
|---|---|
| 79 | `[{"type":"text","text":"You are a Claude agent, built on Anthropic's Claude Agent SDK."}, {"type":"text","text":"You are an assistant for performing a web search tool use"}]` |
| 62 | `[{"type":"text","text":"You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK."}, {"type":"text","text":"You are an assistant for performing a web search tool use"}]` |
| 49 | `[{"type":"text","text":"You are Claude Code, Anthropic's official CLI for Claude."}, {"type":"text","text":"You are an assistant for performing a web search tool use"}]` |

`messages`：恒为 1 条 user 消息，`[{"type":"text","text":"Perform a web search for the query: <query>"}]`。

`tool_choice` 与其余字段：

| 次数 | 组合 |
|---|---|
| 77 | `tool_choice={"type":"tool","name":"web_search"}`，`max_tokens=64000`，`thinking={"type":"disabled"}` |
| 65 | `tool_choice={"type":"auto"}`，`max_tokens=32000`，无 `thinking` |
| 30 | `tool_choice={"type":"auto"}`，`max_tokens=128000`，无 `thinking` |
| 18 | `tool_choice={"type":"tool","name":"web_search"}`，`max_tokens=128000`，`thinking={"type":"disabled"}` |

全部 `stream=true`、`output_config={"effort":"high"}`。

**95/190（50%）使用强制 `tool_choice: {"type":"tool","name":"web_search"}`。** 这些请求经过我们的 `_drop_dangling_choice()` 后，`tools` 变空 → `tool_choice` 被整个删掉。

### 2.4 一份完整样本（逐字）

`[REAL]` `history-v3-20260816-160151.db` / `req_1786906969007_605` / 2026-08-16，`stage=ingress track=client`：

```json
{
  "max_tokens": 128000,
  "messages": [{"role": "user", "content": [{"type": "text", "text": "Perform a web search for the query: Linux /proc/pid directory file descriptor pidfd_send_signal stable process reference PID reuse"}]}],
  "metadata": {"user_id": "{\"device_id\":\"<scrubbed>\",\"account_uuid\":\"\",\"session_id\":\"826d4cda-0dc8-46dd-9cd8-02d2818b822d\"}"},
  "model": "gpt",
  "output_config": {"effort": "high"},
  "stream": true,
  "system": [
    {"type": "text", "text": "You are a Claude agent, built on Anthropic's Claude Agent SDK."},
    {"type": "text", "text": "You are an assistant for performing a web search tool use"}
  ],
  "tool_choice": {"type": "auto"},
  "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8, "allowed_domains": ["kernel.org", "man7.org", "git.kernel.org"], "blocked_domains": []}]
}
```

---

## 3. 同一请求里还有哪些工具？

**没有。190/190 都是 `ntools == 1`。**

Claude Code 的 web search 是**两段式**的：

1. 主对话请求（52 个工具，含普通 function tool `WebSearch`）→ 模型发出 `tool_use{name:"WebSearch", input:{query, allowed_domains, blocked_domains}}`；
2. Claude Code 客户端接住这个调用，**另起一个 Messages API 请求**，只带 `web_search_20250305` 一个工具、两句 system、一条 user 消息，把模型入参里的 `allowed_domains` / `blocked_domains` 原样搬进工具声明；
3. 把第 2 步的回复渲染成文本，作为第 1 步那个 `tool_use` 的 `tool_result` 交回主对话。

`[TRANSCRIPT]` 配对证据（同一 `session_id=826d4cda-…`、同一 `agent_id=a685c93b343cfd6b7`、同一 query、同一 allowed_domains）：

`~/.claude/projects/-home-xp-src-ghc-api-proxy-py/826d4cda-0dc8-46dd-9cd8-02d2818b822d/subagents/agent-a685c93b343cfd6b7.jsonl`

```json
{"type":"tool_use","id":"call_Ym15g3a52OtfY45PJLOtqT3h","name":"WebSearch","input":{"query":"Linux /proc/pid directory file descriptor pidfd_send_signal stable process reference PID reuse","allowed_domains":["kernel.org","man7.org","git.kernel.org"],"blocked_domains":[]}}
```

---

## 4. 「剥离之后模型行为异常」的证据

### 4.1 我们自己的代理：**未找到**（真的没有）

`[REAL]` `~/.local/share/ghc-api-proxy/history.db`（`entries` 表，**8966 条**，截至 2026-08-20 14:17）中，请求体含 `web_search` 或 `performing a web search` 的条目数：**0**。

也就是说 `server_tools.py` 的剥离路径**在生产流量里一次都没有被真实触发过**。目前没有任何一手证据说明剥离后模型会怎么表现。这一条必须如实标注，不能用推理填补。

### 4.2 但有一条**同形态的旁证**：子请求失败时主对话看到什么

`[TRANSCRIPT]` 会话 `7c4be027-4f90-47bd-b213-48e12691be05`（`-home-xp-src-refs-ccb-cc/`），对应 `history-v3-260807.db` 中 2026-08-05 03:45 那批 `state=failed` 的搜索子请求。主对话收到的 `tool_result`：

```json
{"type":"tool_result","tool_use_id":"call_c2su7jmjc412fN6jcQkRK7WD","is_error":true,
 "content":"API Error: 400 {\"error\":{\"message\":\"Tool choice 'function' not found in 'tools' parameter.\",\"code\":\"invalid_request_body\"}}"}
```

连续 3 次同样的错误之后，主对话模型的反应（记录 74）：

> CodeGraph 未建立索引，因此我改用源码级检索；官方搜索接口当前报错，我会直接抓取官方文档页面，不把接口失败误当成"官方没有该功能"。

随后改用 `WebFetch` 抓取 `code.claude.com/docs` 并继续完成任务。

**结论（强证据）：当搜索子请求返回明确错误时，主对话模型的降级是干净的**——它正确把错误归因为「接口问题」而非「事实不存在」，换用 WebFetch，没有道歉循环，没有调用不存在的工具。

### 4.3 **真正的风险不在「模型行为异常」，而在「结果被静默伪造」**

`[TRANSCRIPT]` 同一份转录里，成功那次的 `tool_result` 内容是：

```
Web search results for query: "Linux /proc/pid directory file descriptor pidfd_send_signal stable process reference PID reuse"

[web_search: "(unknown query)"] (id: h+ZT83wjMnKmRvAy1ZuR2Dp6L6TPaqeO/…, status: in_progress)Search results indicate that **yes**: on Linux, an open file descriptor for `/proc/<pid>` …
```

注意两件事：

1. 抬头 `Web search results for query: "<query>"` 是 **Claude Code 客户端无条件拼上去的**，不取决于回复里有没有 `server_tool_use` / `web_search_tool_result` 块；
2. 中间那段 `[web_search: "(unknown query)"] (… status: in_progress)` 是既有 Bun 服务翻译出来的**畸形块**，Claude Code 照样原样渲染并放行；助手正文直接跟在它后面。

推论（**中等强度：由观测到的渲染方式外推，未做零工具对照实验**）：如果我们剥离声明，子请求变成「没有工具 + system 说你是个执行网页搜索的助手 + user 说 Perform a web search for the query: X」。模型极可能**凭记忆直接作答**，Claude Code 会给它套上 `Web search results for query: "X"` 的抬头交回主对话。**主对话拿到的是一份被标注为"搜索结果"的、实际未经检索的内容**，而且没有 `is_error`，没有任何标记能让上层察觉。

这比 4.2 那种明确报错**糟糕得多**：明确报错时模型会正确降级，静默伪造时不会。

### 4.4 既有 Bun 服务的做法：**改路由，不剥离**

`[REAL]` 190 个子请求中 **114 个** `requestModel` 是 Claude 模型（`claude-opus-5` 95、`sonnet` 19），另 76 个是 `gpt`；但 **`responseModel` 190/190 都是 GPT**（`gpt-5.6-sol` / `gpt-5.6-terra`）。即：既有服务发现请求带 `web_search_20250305` 就**改判到能执行搜索的 GPT 模型 + Responses 端点**，并翻译声明。

样本 `history-v3-260807.db` / `req_1786005474269_1087`：

| stage | 内容要点 |
|---|---|
| `ingress` (client) | `model=claude-opus-5`，`tools=[{type:web_search_20250305, name:web_search, max_uses:8, allowed_domains:["docs.anthropic.com"], blocked_domains:[]}]`，`tool_choice={type:tool,name:web_search}` |
| `effective-request` (proxy) | `model=gpt-5.6-sol`，`tools=[{"type":"web_search"}]`，`tool_choice={"type":"web_search"}`，`instructions` 由两段 system 拼接 |

顺带两个可记录的缺陷（**观测到，未验证是否有意为之**）：

- 翻译时 **`allowed_domains` 被丢弃**（Responses 侧的 `web_search` 支持 `filters.allowed_domains`）。在我们观测的 190/190 样本里 `allowed_domains` 都非空，所以这个丢弃是 100% 生效的能力损失。
- 拼 `instructions` 时两段 system 之间**有时无分隔符**（`…Agent SDK.You are an assistant…`），有时是 `\n\n`。

失败率：`history-v3-260807.db` 里的 59 个 `claude-opus-5` 子请求中有 **42 个 `failed`**（其余 db 的 claude 子请求全部 `completed`），错误统一是 `Failed to create responses`（伴随 HTTP 408，见 `-home-xp-src-copilot-api-js--worktree-fix-ghc-request-body-408/` 的转录），属于当时的稳定性问题，**不是** web search 的 400。

---

## 5. 参照物（非真实客户端请求，不作判据）

`[PROBE]` `exp/260820-websearch-probe/raw/A1-count-tokens-web-search-request.json` 是我们手工构造的最小探针：

```json
{"model":"claude-sonnet-5","messages":[{"role":"user","content":"What is the capital of France?"}],
 "tools":[{"type":"web_search_20250305","name":"web_search"}]}
```

回 `HTTP 400 {"error":{"message":"The use of the web search tool is not supported.","code":"unsupported_value"}}`。这证明了**上游会拒**，但它的形状（无 `max_uses` / 无 `allowed_domains`）与 Claude Code 真实发出的不同，**不能**用来推断 Claude Code 的行为。

`tests/cassettes/responses_web_search_*.json` 同理，是我们录的 Responses 侧样本。

---

## 6. 对当前设计问题的直接含义

按证据重排一下选项（**这一节是判断，不是观测**）：

1. **剥离声明**（现状）——在这个特定请求形状下，等价于「把一个只有一个工具的请求变成零工具请求，再让客户端把模型的记忆当搜索结果贴回主对话」。风险是**静默伪造**，没有任何一侧能察觉。这是三个选项里最差的。
2. **保留返回 `unavailable` 的替身工具**——需要注意：替身工具得是 Anthropic 端点**能接受**的形状（普通 function tool，因为任何 `web_search*` 型都被拒），且 50% 的样本带 `tool_choice:{type:tool,name:"web_search"}`，替身必须叫 `web_search` 才能让 `tool_choice` 继续成立。它把「静默伪造」换成 4.2 里那种**明确失败**，而 4.2 已经证明主对话模型对明确失败的降级是干净的。
3. **改判路由到 Responses + GPT**（既有 Bun 服务的做法）——已在生产验证可行，190 个样本里成功的那些都返回了带真实引用的结果。代价是模型被换掉，且需要把 `allowed_domains` 正确映射到 `filters.allowed_domains`（既有实现没做）。

三者不互斥：路由改判是「让它真的能用」，替身工具是「路由不可用时的兜底」。**但这是我的倾向，不是已决事项，请用户裁决。**

顺带一条**不能静默砍掉的发现**：`server_tools.py` 的模块 docstring 说「A session that used web search before this ran carries `server_tool_use` calls and `*_tool_result` answers in its transcript」。按本次取证，**主对话的历史里根本不会有 `server_tool_use` 块**——那些块只存在于一次性的搜索子请求里，从不进入主对话的 `messages`。主对话历史里只有普通的 `tool_use{name:"WebSearch"}` / `tool_result`。历史扁平化那段逻辑针对的场景，在 Claude Code 这个客户端上可能从不发生（对其他客户端仍可能成立）。这条应当去核实并回写文档。

---

## 附：搜过但没找到的

- 我们的代理 `~/.local/share/ghc-api-proxy/history.db` 8966 条，`web_search` 命中 0。
- 4 个近期 db（`20260815` / `20260816` / `20260817` / `20260818`，共 32762 个 `v3_objects`）中，`web_fetch_2025*` 只出现在 29KB / 48KB 量级的 sequence-item（即消息正文，是我们自己讨论 web search 的研究文本），**没有任何小对象是 `web_fetch` 工具声明**。结论（**中等强度，窗口限于这 4 个 db**）：Claude Code 的 `WebFetch` 不发送 Anthropic 原生 server tool 声明，它是纯客户端实现。
- `~/.claude/projects/**` 中 `web_search_20250305` 命中 601 个文件——**绝大多数是我们自己关于 web search 的研究与讨论文本**，逐一核对代价过高且价值低，本报告不采信任何一条作为「真实请求」证据。真实请求证据全部来自 history db 的 ingress 重建。
- `user_location`：190 个真实声明中 0 次出现。
