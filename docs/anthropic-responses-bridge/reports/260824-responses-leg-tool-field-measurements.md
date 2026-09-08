# Responses 腿的 tool 字段：`defer_loading` 400 的实测定形

- 日期：2026-08-24
- 探针：`exp/260824-beta-and-cache-control-probe/probe_responses_tools.py`
- 上游：`https://api.enterprise.githubcopilot.com/responses`，模型 `gpt-5.6-sol`（用户报错里的那个）
- 形态：非流式，一句话提示词，`max_output_tokens` 16，每格一次调用，正控制先跑

## 0. 一句话

`_function_tool` 把 Anthropic tool 上除 `input_schema` 外的**所有**字段原样搬到 Responses 请求体，`defer_loading: true` 因此漏了过去并被拒；同一条腿上**存在**一个上游自己承认的映射形状（`{"type": "tool_search"}`），所以这里的选择不是「剥还是死」，而是「剥还是映射」——两者语义不同，需要裁决。

## 1. 触发它的那次失败

```
[....] 02:34:46 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP/2 400 Bad Request"
[FAIL] 02:34:46 H1 400 POST /v1/messages gpt-5.6-sol 1.2s: upstream rejected the request:
Error code: 400 - {'error': {'message': "Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.", 'code': 'invalid_request_body'}}
```

入站是 Anthropic Messages（Claude Code），模型 `gpt-5.6-sol` 经 `model_mappings` 落到 Responses 上游，于是走翻译腿。

## 2. 字段矩阵

| 发出的东西 | 上游 | 分量 |
|---|---|---|
| P0 两个普通 function tool（正控制） | **200** | 这一轮可读的前提 |
| P1 一个 tool 带 `defer_loading: true`，另一个不带 | **400** `Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.` | 逐字复现用户报错 |
| P2 一个 tool 带 `defer_loading: false` | **200** | 被拒的是「延迟」这件事，不是这个键 |
| P3 一个 tool 带 `cache_control: {type: ephemeral}` | **200** | |
| P4 一个 tool 带 `cache_control: {type: ephemeral, scope: …}` | **200** | |
| P5 Anthropic 的 `{"type": "tool_search_tool_regex_20251119"}` | **400**，并列出它支持的枚举（见下） | |
| P6 `{"type": "tool_search"}` + 一个 `defer_loading: true` 的 tool | **200** | 存在合法形状 |
| P7 顶层 `tool_search: true` + `defer_loading: true` | **400** 与 P1 同 | 「tools.tool_search」不是顶层字段 |

P5 的完整枚举，这是上游自己说的，比任何推断都强：

> Supported values are: `code_interpreter`, `programmatic_tool_calling`, `function`, `namespace`, **`tool_search`**, `file_search`, `web_search_preview`, `web_search_preview_2025_03_11`, `image_generation`, `mcp`, `custom`, `computer`, `computer_use_preview`, `shell`, `apply_patch`.

四条结论：

1. **只有 `true` 是问题（P1 vs P2）。** 一个剥离实现如果连显式 `false` 一起删，删掉的是一个上游接受的字段；保留它也不会有人受损。
2. **tool 上的 `cache_control` 在这条腿上不是问题（P3/P4）。** 这一条是**反向**结果，值得单独记：我原本预期它和 `input[].content[].cache_control` 一样被拒（`openai_responses.py:7` 记着后者被拒的原文 `Unknown parameter: 'input[0].content[0].cache_control'`），于是以为同一行透传埋了第二个 400。实测不成立。**不要为它建守卫。**
3. **`tool_search_` 家族有 hosted 对应物，这证伪了一条既有注释。** `openai_responses.py:163` 写着 `memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_` 这几族「executed by the client, not by the model's host, so there is no hosted equivalent to name — they travel unchanged today」。P5 的枚举里 `tool_search` 与 `computer`/`computer_use_preview`/`shell` 都在，所以至少 `tool_search_` 与 `computer_` 两族的「没有 hosted 对应物」是错的。这条注释需要修订——但注意，**「端点认识这个 type」不等于「语义等价」**，见下。
4. **P6 的 200 只说明请求被接受，不说明行为正确。** Anthropic 侧 Claude Code 用的是**客户端自己执行**的 tool search（它声明一个普通 `ToolSearch` function tool，自己搜索，下一轮回传 `tool_reference` 块）；Responses 的 `{"type": "tool_search"}` 是 **host 侧**的内建工具。两者谁来执行搜索是不同的。把前者映射成后者，模型可能不再调用客户端那个 `ToolSearch`，而客户端仍在等它——这不是一个 200 能回答的问题。

## 3. 修复选项（不替用户裁决）

| 选项 | 做什么 | 代价 | 风险 |
|---|---|---|---|
| **A 剥离** | 翻译时删掉 `defer_loading: true`（保留 `false`），记一条 loss | 全部工具定义进上下文，客户端想省的 token 省不掉；功能仍正确 | 低。不引入任何未验证的语义 |
| **B 映射** | 见到 `defer_loading: true` 就补一个 `{"type": "tool_search"}`；并把 `tool_search_*` 服务端工具映射成它 | 需要验证「谁执行搜索」的语义等价，以及第二轮 `tool_reference` 块翻到 Responses 会变成什么 | 高。§2 结论 4，一个 200 不回答这个 |
| C 本地拒绝 | 像 `web_fetch` 那样在本地拒掉带 `defer_loading` 的请求 | 客户端直接不可用 | 与「让请求能工作」的目标相反 |

**倾向 A**，理由是它有确定的失败面被闭合、没有引入未验证语义，且与本项目「缺一个具体失败面就不预建」的既有判据一致；B 作为增强留待裁决，它需要的那组实测（多轮生命周期、谁执行搜索）本文没有做。

## 4. 我排除了什么

- **「`cache_control` 在 tool 上也会 400」**——P3/P4 证伪。这是我进场时的预期，写下来是因为它很自然：同一行透传、另一层的同名字段确实被拒。
- **「`tools.tool_search` 是顶层字段」**——P7 证伪，错误与 P1 一字不差。上游那句 `tools.tool_search` 读起来像路径，其实指的是 tools 数组里的一个元素。
- **「剥掉 `defer_loading` 要连 `false` 一起剥」**——P2 证伪，`false` 是被接受的。
- **未做，因此不在结论里**：没有测第二轮——即客户端 `ToolSearch` 的 `tool_result.content[]` 里 `{"type":"tool_reference"}` 块翻译到 Responses 之后是什么形状、会不会 400。这是选项 B 必须补的一格，也可能影响选项 A（剥掉 defer_loading 后模型仍可能调用客户端的 ToolSearch）。没有测流式，没有测别的 Responses 模型。
