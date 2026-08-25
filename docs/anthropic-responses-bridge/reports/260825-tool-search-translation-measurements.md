# 客户端执行的 tool search 能翻译：两侧形状与完整往返实测

- 日期：2026-08-25
- 探针：`exp/260824-beta-and-cache-control-probe/probe_tool_search_translation.py`（模式矩阵）、`probe_tool_search_roundtrip.py`（完整往返），输出在同目录 `raw/`
- 上游：`https://api.enterprise.githubcopilot.com/responses`，模型 `gpt-5.6-sol`，非流式
- 背景：用户 2026-08-25 裁定——**客户端传来的 tool search 要翻译过去，不是剥掉**，且不靠配置开关决定

## 0. 一句话

Responses 侧原生支持**客户端执行**的 tool search（`execution: "client"`），语义与 Anthropic 侧的自定义 tool search 对应，完整往返已实测跑通；**唯一没有答案的是「哪个 function tool 是客户端的搜索工具」——Anthropic 协议里没有这个标记**。

## 1. `execution` 决定谁来搜，这是整件事的关键

`ToolSearchToolParam`（openai SDK 3.3.1）：

```python
type: Required[Literal["tool_search"]]
description: Optional[str]        # "for a client-executed tool search tool"
execution: Literal["server", "client"]
parameters: Optional[object]      # "for a client-executed tool search tool"
```

实测各模式，同一个请求体（一个 `defer_loading: true` 的 `get_weather`，问「巴黎天气」）：

| 用例 | 上游 | 模型产出的 output items |
|---|---|---|
| S0 正控制：不 defer、无 tool_search | 200 | `function_call:get_weather` |
| S1 `execution: "server"` | 200 | `reasoning` → `tool_search_call` → **`tool_search_output`** → `function_call:get_weather` |
| S2 `execution: "client"` + description + parameters | 200 | `reasoning` → `tool_search_call` **然后停住** |
| S3 `execution: "client"` 不带 description | **400** | `Client-executed tool_search requires a description.` |
| S4 不带 `execution` | 200 | 同 S1，即默认按 server |

**S1 与 S2 的差别是承重的**：server 那格里 `tool_search_output` 由**上游自己**产出，整个搜索对客户端不可见；client 那格没有 output，模型在等**客户端**把结果送回来。这正是 Anthropic 侧自定义 tool search 的语义。

## 2. 完整往返：客户端执行确实能走通

`probe_tool_search_roundtrip.py`，两条真实调用：

| 腿 | 发出 | 回来 |
|---|---|---|
| R1 | `tools: [tool_search(client), get_weather(defer_loading)]` + 用户提问 | `reasoning` → `tool_search_call`，`call_id='call_…'`，`arguments={"pattern": "weather\|forecast\|temperature"}` |
| R2 | R1 的 input ＋ 那个 `tool_search_call` ＋ `tool_search_output{call_id, execution:"client", status:"completed", tools:[get_weather 的完整定义]}` | **`function_call:get_weather`** |

两点值得单独记：

1. **`arguments` 是按我们声明的 `parameters` schema 生成的**（我们声明了 `{pattern: string}`，模型就发 `{"pattern": …}`）。所以翻译时把 Anthropic 侧搜索工具的 `input_schema` 搬过去，模型的调用参数就能直接翻回那个工具的 `tool_use.input`。
2. **回传的是完整工具定义，不是工具名**——`ResponseToolSearchOutputItemParam.tools: List[Tool]`。Anthropic 侧客户端回传的 `tool_reference` **只有 `tool_name`**。两侧不对等，但**能补上**：那些工具的完整定义就在同一个请求的 `tools` 数组里（正是被 `defer_loading` 标记的那些），按名字查得到。

## 3. 三个边界，其中一个决定了「提升」的确切含义

| 用例 | 上游 | 说明 |
|---|---|---|
| E1 同时声明 `execution:"server"` 与 `execution:"client"` 两个 `tool_search` | **400** `Only one tool_search tool is allowed in 'tools' parameter.` | 一个请求只能有一个，托管与自定义两种**必须二选一** |
| E2 客户端 `tool_search` **与原来那个普通 `ToolSearch` 工具并存** | 200，模型产出 **`function_call:ToolSearch`** | 模型走了老路，`tool_search` 形同虚设 |
| E3 `tool_search_output` 一次回传两个工具定义 | 200 → `function_call:get_weather` | Anthropic 的 `tool_result` 可含多个 `tool_reference`，能对上 |

**E2 决定了「提升」是替换而不是添加。** 若把客户端的搜索工具留在 `tools` 里、另外补一个 `tool_search`，模型会继续调用那个普通工具，`tool_search` 白声明——而更糟的是，此时上游并不知道搜索发生过，被 `defer_loading` 的工具也就无从加载。所以提升必须把那个 function tool **从 `tools` 里移除**，换成 `tool_search`。

**E2 同时给出了误判的代价**：一旦把某个普通工具错认成搜索工具并提升，那个工具就从 `tools` 里消失了，模型再也调用不到它。这不是「少一个优化」，是客户端的一件能力凭空不见。识别判据因此必须可靠——**识别不出时的正确行为是不提升，而不是猜**。

## 4. 由此得到的映射表

请求方向（Anthropic → Responses）：

| Anthropic | Responses |
|---|---|
| 客户端的搜索工具（普通 function tool） | `{type: "tool_search", execution: "client", description: <搬>, parameters: <搬 input_schema>}` |
| `tools[].defer_loading` | 原样保留（前置条件已由上一行满足） |
| 历史里 `tool_use{id, name=搜索工具, input}` | `tool_search_call{call_id: id, arguments: input}` |
| 历史里 `tool_result{tool_use_id, content:[tool_reference{tool_name}…]}` | `tool_search_output{call_id: tool_use_id, execution:"client", tools:[按 tool_name 从本请求 tools 里取出的完整定义]}` |
| 托管声明 `tool_search_tool_regex/bm25_*` | `{type: "tool_search", execution: "server"}` |

响应方向（Responses → Anthropic）：

| Responses | Anthropic |
|---|---|
| `tool_search_call{call_id, arguments}` | `tool_use{id: call_id, name: <搜索工具名>, input: arguments}` |

**这套映射不需要跨请求状态**：每个请求都带完整的 `tools` 声明与完整历史，所以每次翻译都能就地重建「搜索工具叫什么」「被 defer 的工具各自的完整定义是什么」。

## 5. 唯一的缺口：哪个 function tool 是搜索工具

Anthropic 侧，自定义 tool search 的搜索工具**就是一个普通 function tool，协议里没有任何标记**。托管那种有 `type: tool_search_tool_regex_*`，可以精确识别；自定义那种不行。

已经想到的候选判据，连同各自的问题（**误判代价见 §3 的 E2**）：

| 判据 | 可靠性 | 问题 |
|---|---|---|
| **历史反推**：某个 `tool_result.content[]` 里有 `tool_reference` 块 → 它对应的 `tool_use.name` 就是搜索工具 | **协议级，零误判** | **第一轮没有历史**，而第一轮就会 400 |
| 工具名匹配（`ToolSearch`） | 启发式 | 是客户端约定不是协议；一个真的叫这名字的普通工具会被误提升 |
| 「唯一没有 `defer_loading` 的工具」 | 启发式 | 官方要求「至少一个工具 non-deferred」，但 non-deferred 的通常不止一个 |

**第一轮那一格今天没有答案**，正在查官方文档与 Claude Code 源码是否给出约定。若最终没有权威判据，实现上需要一个明确的兜底（识别不出就不提升，并把 `defer_loading` 按既有方式处理），而不是猜。

## 6. 一份真实请求说明的事

本机 `~/.local/share/ghc-api-proxy/rejected/20260824T103948.240-400-530e0e10-…json` 是一份 Claude Code 的真实出站请求（29 个工具）：**零个带 `defer_loading`，没有名字像搜索工具的条目，所有工具都是裸的 Anthropic function tool**（无 `type` 字段）。

所以 tool search 在 Claude Code 里是**条件性启用**的，不是每个请求都有。用户报的 `req=fcc0bebc` 那份带 `defer_loading` 的 body 在用户机器上，本仓没有副本——**搜索工具的确切 name / description / input_schema 因此仍是未观测的**，这限制了 §5 中启发式判据的评估。

## 7. 我排除了什么

- **「Responses 的 tool_search 只能由 host 执行，所以语义不等价」**——这是上一轮（2026-08-24）暂缓映射的主要理由，`execution: "client"` 直接证伪。当时只看了「加上它请求变 200」，没有读类型定义，也没有看模型产出什么。**一个 200 不回答语义问题，读类型定义和看 output items 才回答。**
- **「回传工具名即可」**——`tools: List[Tool]` 要的是完整定义，实测 R2 用完整定义通过；只给名字未测，且类型定义不支持。
- **未做**：没有测流式；没有测「保留客户端搜索工具并回传其 `function_call_output`」那条路的第二轮（E2 只跑了第一轮，因为 E1／E2 已经把设计定成替换）；没有真实 Claude Code 的 tool-search 请求样本，所以搜索工具的确切 name/description/input_schema 仍未观测。
