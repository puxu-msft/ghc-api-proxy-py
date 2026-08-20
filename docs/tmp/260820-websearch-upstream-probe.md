# web search 上游探针实测报告（Copilot 真实上游，2026-08-20）

**执行者**：leaf executor，上游探针任务。用户已授权本次对 GitHub Copilot 上游发真实请求。
**日期**：2026-08-20。**账号**：本机 `~/.local/share/copilot-api/github_token`（individual）。**上游**：`https://api.githubcopilot.com`。
**未触碰** `127.0.0.1:4141` 上的既有 Bun 服务。**未修改** `src/app/` 下任何生产代码。

**探针脚本**：[`exp/260820-websearch-probe/probe.py`](../../exp/260820-websearch-probe/probe.py)（A/B/C 三组）、[`exp/260820-websearch-probe/record.py`](../../exp/260820-websearch-probe/record.py)（录 cassette）。
**原始输出**：`exp/260820-websearch-probe/raw/`，每条探针一份 `-request.json` 与一份 `-response.txt`，流式另有 `-chunks.json` 保留 chunk 边界。落盘前按字段名在任意深度清洗 `token` / `tracking_id` / `enterprise_list` / `organization_list` / `safety_identifier`；传输途中不清洗。

**总请求数**：19 次推理/探针请求 + 4 次 token 交换 + 1 次 `/models`。每条探针只发一次，失败不重试。

---

## 0. 顺带查到的一件事：`refs/available_models.json` 已过期（证据权重：强，一手）

第一轮 A 组用 `claude-sonnet-4.5` 全部得到 `{"error":{"message":"The requested model is not supported.","code":"model_not_supported"}}`。拉一次实时 `/models` 才发现该模型已从目录消失。

实时目录与 `refs/available_models.json` 的差异（2026-08-20）：

| 变化 | 模型 |
|---|---|
| 已消失 | `claude-sonnet-4.5`、`claude-opus-4.5`、`gemini-3-flash-preview`、`gemini-2.5-pro`、`gpt-4o-mini-2024-07-18` 之外的若干旧 GPT 条目（部分仍在） |
| 新出现 | `claude-opus-5`（`/v1/messages` + `/chat/completions`）、`gemini-3.6-flash`、`gemini-3.7-flash`、`grok-4.5`（`/responses`）、`grok-4.6`（`/responses`）、`mai-code-1.1-flash`（`/responses`） |

**对分流判据的影响**：`supported_endpoints` 含 `/responses` 的集合现在多了 `grok-4.5`、`grok-4.6`、`mai-code-1.1-flash`、`mai-code-1-flash-picker`。**这几个都没探针过 web search**，所以「含 `/responses` 是必要非充分条件」这句话现在更弱了——非 GPT 的 `/responses` 模型已经存在。`claude-*` 仍然一个都不广告 `/responses`，根因结论不变。

---

## A 组：count_tokens 腿（模型 `claude-sonnet-5`）

**一句话结论**：**会 400，而且是与 `/v1/messages` 完全相同的那一条**。`count_tokens` 不是 server tool 的豁免通道。

| # | 请求 | HTTP | 完整响应体 |
|---|---|---|---|
| A1 | `tools:[{"type":"web_search_20250305","name":"web_search"}]` | **400** | `{"error":{"message":"The use of the web search tool is not supported.","code":"unsupported_value"}}` |
| A2 | 无 `tools`（对照） | **200** | `{"input_tokens":14}` |
| A3 | 一个普通 function tool（对照） | **200** | `{"input_tokens":427}` |

请求其余部分最小：`{"model":"claude-sonnet-5","messages":[{"role":"user","content":"What is the capital of France?"}]}`，头部只加 `anthropic-version: 2023-06-01`，无 `anthropic-beta`。

**读法**：

1. A1 的 message 与 code 与生产上 `/v1/messages` 那条 400 **逐字相同**（`unsupported_value`）。上游对 server tool 的拒绝发生在读 `tools[]` 声明的那一层，与端点是 messages 还是 count_tokens 无关。
2. A3 证明 `tools` 键本身在 count_tokens 上完全正常，A1 的 400 只由 server tool 类型引起，不是「count_tokens 不吃 tools」。
3. 这直接回答了 `260820-websearch-fix-v2-design.md` §8 记的 m5 缺口——「`/v1/messages/count_tokens` 带 server tool 时行为未测量」现在测量完了：**未接订阅者的 count_tokens 腿确实会 400**。按 `handler.py` 的现有行为，400 后退到本地估算，客户端看不到失败，但校准停止学习。**证据权重：强，一手，单模型单次，但三条对照互证。**

---

## B 组：`/responses` 请求侧能接受什么（模型 `gpt-5.5`，非流式，`max_output_tokens: 64`）

| # | 发出的工具/字段 | HTTP | 判定 | 上游错误码 / 回显 |
|---|---|---|---|---|
| B1 | `tools:[{"type":"web_search"}]` | **200** | **接受**（基线复现成立） | 回显补默认：见下 |
| B2 | `tools:[{"type":"web_search_20250305","name":"web_search"}]` | **400** | **拒绝** | `invalid_request_body`，`Invalid value: 'web_search_20250305'.` + 完整可选值清单 |
| B3 | `web_search` + `user_location`（approximate/city/country/region/timezone） | **200** | **接受，且逐字回显** | 回显 `{"type":"approximate","city":"Seattle","country":"US","region":"Washington","timezone":"America/Los_Angeles"}` |
| B4 | `web_search` + `allowed_domains:["example.com"]` | **400** | **拒绝** | `invalid_request_body`，`Unknown parameter: 'tools[0].allowed_domains'.` |
| B5 | `web_search` + `blocked_domains:["example.com"]` | **400** | **拒绝** | `invalid_request_body`，`Unknown parameter: 'tools[0].blocked_domains'.` |
| B6 | `web_search` + `max_uses:3` | **400** | **拒绝** | `invalid_request_body`，`Unknown parameter: 'tools[0].max_uses'.` |
| B7 | `tool_choice:{"type":"web_search"}` 配 B1 的 tools | **200** | **接受，并真的强制执行了搜索** | 回显 `tool_choice` 被**改写**为 `{"type":"web_search_preview"}`；`tool_usage.web_search.num_requests: 1`；output 含 `web_search_call` |
| B8 | `include:["web_search_call.action.sources"]` | **200** | **接受但静默丢弃** | 响应体 `"include": null`，`output` 里无任何 sources |
| B9 | `tools:[{"type":"web_fetch"}]` | **400** | **拒绝** | `invalid_request_body`，`Invalid value: 'web_fetch'.` + 同一份可选值清单 |

### B1 的回显（补默认后的工具形状）

```json
"tools": [{"type": "web_search", "return_token_budget": "default", "search_content_types": ["text"], "search_context_size": "medium", "user_location": {"type": "approximate", "city": null, "country": "US", "region": null, "timezone": null}}]
```

与 `copilot-api-js` 2026-07-14 在 gpt-5.5 上的回显**逐字一致**。**证据权重：强，跨仓库跨日期独立复现。**

### B2 / B9 泄露出来的可选值清单（最有价值的一条副产品）

两条 400 的 message 里带同一份枚举：

```
'code_interpreter', 'programmatic_tool_calling', 'function', 'namespace', 'tool_search',
'file_search', 'web_search_preview', 'web_search_preview_2025_03_11', 'image_generation',
'mcp', 'custom', 'computer', 'computer_use_preview', 'shell', 'apply_patch'
```

**注意这份清单里没有 `web_search`**，可 B1 发 `{"type":"web_search"}` 是 200。合理解释：`web_search` 是 `web_search_preview` 的别名，被上游在校验之前归一化了——B7 里 `tool_choice:{"type":"web_search"}` 回显成 `{"type":"web_search_preview"}` 正是同一个归一化的可见痕迹。**这一步是推断，不是实测**：我没有单独探针 `{"type":"web_search_preview"}`。但清单本身是一手的，**它是目前唯一一份来自上游自己的、可枚举的 `/responses` builtin 工具名单**，比 `refs/` 里任何东西都权威。

清单里还有几个本项目从未考虑过的名字：`tool_search`、`shell`、`apply_patch`、`programmatic_tool_calling`、`namespace`。**都未探针。**

### 三条对映射设计直接生效的结论

1. **`user_location` 可写，1:1 对应成立。**（`260820-websearch-on-responses-leg.md` §1.1 把这条标成「推断，未探针」，现在它是实测。）Anthropic 的 `user_location` 可以直接映射过去，不必丢。**证据权重：强，一手。**
2. **`allowed_domains` / `blocked_domains` / `max_uses` 不是「无对应物、静默丢就完了」，而是「写进去会 400」。** 这把设计稿 §5.2 的保守方案从「可选」变成「必须」：带域名限制的声明**必须整条剥离并告警**，绝不能把子字段原样带过去。**证据权重：强，一手，三条独立错误。**
3. **`include` 被接受但不生效。** 200 在这里**无判别力**——上游把它吃掉并回显 `null`。所以「`web_search_call.action.sources` 能不能拿到」的答案是：**拿不到，而且不会报错**。任何指望它的设计都会静默失败。**证据权重：强，一手，单次。**

---

## C 组：真实响应样本

### C1 非流式（`gpt-5.5`，prompt `Search the web for today's date.`，无 `tool_choice`）

HTTP 200，`tool_usage.web_search.num_requests: 1`，`output` = `[web_search_call, message]`。

`web_search_call` item 原文（id 截断）：

```json
{"action": {"queries": ["time: {\"utc_offset\":\"-04:00\"}"], "query": "time: {\"utc_offset\":\"-04:00\"}", "type": "search"},
 "id": "Q604Qgq27FefvuQ5t/qL1iSo2ersozVnNG/py8UXSOeE6HKZZpikSwgwSbCNsSg1…<416 字符>…rMl5d/JxvkA1JMs53ElNwFFWFJujQ==",
 "status": "completed",
 "type": "web_search_call"}
```

- **keys 恰好四个：`action, id, status, type`。确无 `encrypted_content`。** 与 `copilot-api-js` 两次独立捕获一致 —— 现在是**三次独立捕获、三个日期、两个仓库**。
- `query` 与 `queries` **同时存在且内容相同**（复现了旧样本的这一点）。
- id 长度 **416 字符**（旧样本 424）。长度不是常数。
- 后续 message 的 `annotations`：**`[]`**（这次没有引用）。

### 关于 `annotations`：**B7 的样本里有真的 `url_citation`**（对旧结论的实质补充）

B7（prompt 是 trivial 的 `What is the capital of France?`，`tool_choice` 强制搜索）的 message item：

```json
{"annotations": [{"end_index": 168, "start_index": 36,
                  "title": "France – EU country | European Union",
                  "type": "url_citation",
                  "url": "https://european-union.europa.eu/principles-countries-history/eu-countries/france_en?utm_source=openai"}],
 "logprobs": [], "type": "output_text",
 "text": "The capital of France is **Paris**. ([european-union.europa.eu](https://european-union.europa.eu/principles-countries-history/eu-countries/france_en?utm_source=openai))"}
```

`260820-websearch-on-responses-leg.md` 结论 #11 写「一个空样本 + 一个散文样本，不要在 `annotations` 上建东西」。**这条现在要修正一半**：`annotations` 上游**确实会填**，形态是 `{type:"url_citation", url, title, start_index, end_index}`，指向正文的字符区间。同一次响应里**引用同时以两种形式出现**：结构化的 `annotations` 数组，以及正文里内联的 markdown `([host](url))`。

**证据权重：中等偏强。** 一手、单次、单模型；两个样本（B7 有、C1 无）说明它**取决于这一次模型答得如何**，不是恒有恒无。**足以据此说「`annotations` 是真实存在的结构化引用载体」，不足以据此说「每次搜索都会有」。** 消费者必须容忍空数组。

### C2 流式 —— **本次最重要的发现：`web_search_call` 的 id 在事件之间会变**

完整帧序列（20 个 chunk，16 个事件）：

| # | event | `output_index` | id 前 10 字符 | id 长度 |
|---|---|---|---|---|
| 0 | `response.created` | — | — | — |
| 1 | `response.in_progress` | — | — | — |
| 2 | `response.output_item.added` | 0 | `n40LI6g9pS` | 416 |
| 3 | `response.web_search_call.in_progress` | 0 | `t/N1eG6Isj`（`item_id`） | 416 |
| 4 | `response.web_search_call.searching` | 0 | `/xxIRRwnFA`（`item_id`） | 416 |
| 5 | `response.web_search_call.completed` | 0 | `/vJZ9TXvk9`（`item_id`） | 416 |
| 6 | `response.output_item.done` | 0 | `B6uFl9rD6J` | 416 |
| 7 | `response.output_item.added` | 1 | `JmUPA7sOvI` | 416 |
| 8–13 | `content_part.added` / `output_text.delta` ×3 / `output_text.done` / `content_part.done` | 1 | 每个事件各不相同 | 416 |
| 14 | `response.output_item.done` | 1 | `vjGpASA+Qk` | 416 |
| 15 | `response.completed` | — | — | — |

**两条必须写进解码器设计的事实：**

1. **`web_search_call` 的 id 在 `added` 与 `done` 之间不相同**，而且中间三个专有事件的 `item_id` 也各不相同——**同一个 item 在 5 个事件里带了 5 个不同的 416 字符 id**。这**直接推翻**了 `260820-websearch-on-responses-leg.md` §2.3(4) 引自 `copilot-api-js` 的「`web_search_call` 的 id 在两个事件间不变（`distinctIds:1`）」。

   本项目 `CLAUDE.md` 记的 function_call id 不稳定，**在 `web_search_call` 上同样成立**。**唯一稳定的关联键是 `output_index`。**

   **证据权重：强。** 两次独立运行（C2 与随后的 cassette 录制）在同一模型同一天上**各自复现**，两次都是每事件一个新 id。旧结论与新结论在同一个模型家族上冲突，可能是上游 8 月的行为变化，也可能是旧探针只看了两个事件、没看中间三个。无论哪种，**按 id 配对必错，按 `output_index` 配对才对**。

2. **中间有三个专有事件，不是「零 delta」。** `response.web_search_call.in_progress` / `.searching` / `.completed` 确实存在，都只带 `item_id` + `output_index` + `sequence_number`，**不带 `action`、不带任何内容增量**。`260820-websearch-on-responses-leg.md` §2.3(1) 说的「中间没有任何事件」不成立；但它的**实质结论仍然成立**——这三个事件不携带任何可累积的内容，item 的完整数据依然只在 `added`（无 `action`）与 `done`（有 `action`）两次快照里。

   补充一条旧报告没说的：**`output_item.added` 上的 `web_search_call` 只有 `id`/`status`/`type`，没有 `action`。** query 只有到 `done` 才知道。所以「在 `added` 上开块、`done` 上收口」这种写法即使写了，块里也无内容可填。

3. **块级交付的落点不变**：`web_search_call` 仍然是 item 与 Anthropic block 天然一一对应的类型，仍然应当在 `done` 上一次性成块。

---

## C3：cassette

**成功录进 `tests/cassettes/`**，用的是仓库既定的 `RecordingTransport`（`tests/integration/recorded/cassettes.py`），所以格式、清洗、chunk 边界、`authenticated` 标记、请求 shape 摘要全部按既定规矩来：

| 文件 | interactions | 内容 |
|---|---|---|
| `tests/cassettes/responses_web_search_nonstream.json` | 2 | token 交换（200）+ `POST /responses` 200，1 chunk，含 `web_search_call` + `message`，`num_requests:1` |
| `tests/cassettes/responses_web_search_stream.json` | 2 | token 交换（200）+ `POST /responses` 200，**18 个 chunk**，`text/event-stream`，含上表全部 16 个事件 |

核对过的：响应头只留 `content-type` / `transfer-encoding` / `cache-control`（允许清单）；`safety_identifier` 在 SSE payload 深处也被替换成 `REDACTED`；token 交换体里 `token` 与 `tracking_id` 均已 `REDACTED`；`authenticated: true` 两条都记上了；请求 shape 记了 `model` / `stream` / 全 body 摘要。原始 chunk 边界保留（流式 18 个 chunk 与线上落法一致）。

**它接不进 `record_cassette.py` 的 scenario 机制，原因写清楚**：那个入口是从 `/v1/messages` 走 `handle_bounded` 驱动整条链录下来的，而**今天的 Responses 腿根本不会发出 `web_search` 工具**——`builtin:server-tool-capability` 只做剥离，没有任何代码把 Anthropic 的 `web_search_*` 映射成 `{"type":"web_search"}`。产品代码目前造不出这个请求。所以另写了 [`exp/260820-websearch-probe/record.py`](../../exp/260820-websearch-probe/record.py) 直接 POST Responses body，走同一个 `RecordingTransport`。

**由此产生的限定，必须说清楚**：

- 这两份 cassette 现在**没有任何测试在回放**。请求 shape 摘要算的是我手写的 Responses body，等映射落地后产品发出的 body 不会与它逐字相同，**直接拿去回放会撞 `RequestShapeChanged`**。
- 它们的价值是**真实上游形态的存证**（本项目此前零样本，且 169 万个 history 对象零命中，`from_history.py` 这条路是死的），不是「现成的回归夹具」。
- 映射一旦落地，应当把它挪进 `record_cassette.py` 的 `SCENARIOS`，用产品链重录一次，那时 shape 才对得上。

---

## 证据强度汇总

| # | 结论 | 证据 | 权重 |
|---|---|---|---|
| 1 | count_tokens 带 server tool → 400 `unsupported_value`，与 messages 腿逐字相同 | A1/A2/A3，claude-sonnet-5，2026-08-20，各一次 | **强，三条对照互证，可据此动手** |
| 2 | `user_location` 可写并逐字回显 | B3 一次，gpt-5.5 | **强，回显即证明，可据此动手** |
| 3 | `allowed_domains`/`blocked_domains`/`max_uses` 写进去会 400 | B4/B5/B6 各一次 | **强，三条独立，可据此动手** |
| 4 | Anthropic 拼法 `web_search_20250305` 在 `/responses` 被拒 | B2 一次 | **强，错误明确点名该值** |
| 5 | `web_fetch` 在 `/responses` 被拒（与 Anthropic 腿是不同的错误措辞） | B9 一次 | **强。Anthropic 腿是 `rejected tool(s): web_fetch`，这里是 `Invalid value: 'web_fetch'`——两条腿两套措辞，反应式 matcher 至少要三行** |
| 6 | builtin 对象形态 `tool_choice` 被接受、被归一化为 `web_search_preview`、并真的强制搜索 | B7 一次 | **强，回显 + `num_requests:1` + output 里真有 item** |
| 7 | `include:["web_search_call.action.sources"]` 被接受但静默丢弃 | B8 一次 | **强（200 + 回显 null 是明确的丢弃证据）；但「上游完全不支持任何 include」是推断，只测了这一个值** |
| 8 | `web_search_call` keys 恰为 `action/id/status/type`，无 `encrypted_content` | C1 + B7 + cassette，加上 `copilot-api-js` 两次 | **强，跨仓库跨日期多次独立复现** |
| 9 | **流式下同一 item 的 id 每个事件都不同** | C2 + cassette 两次独立运行，gpt-5.5，2026-08-20 | **强到必须据此设计（按 `output_index` 配对）。与旧的 `distinctIds:1` 结论冲突，冲突本身已用两次运行确认** |
| 10 | 存在 `response.web_search_call.{in_progress,searching,completed}` 三个专有事件，均无内容增量 | C2 + cassette 两次 | **强** |
| 11 | `annotations` 会填 `url_citation`，也可能是 `[]` | B7 有、C1 无，各一次 | **中等偏强：足以证明这个载体真实存在并说明其形态；不足以推出频率或触发条件** |
| 12 | 上游 builtin 工具名可选值清单（15 个） | B2/B9 错误体，两次一致 | **强（一手，来自上游自己）。但「`web_search` 是 `web_search_preview` 的别名」是推断，未单独探针** |
| 13 | `refs/available_models.json` 已过期；`/responses` 集合新增 grok / mai-code | 实时 `/models` 一次 | **强（一手目录）。新增模型是否真能 web search：未测量** |

## 未测量（明确留白）

- `{"type":"web_search_preview"}` 与 `{"type":"web_search_preview_2025_03_11"}` 直发是否 200（别名推断未验证）。
- `search_context_size` / `search_content_types` / `return_token_budget` 是否可写（只见过回显，没试过写）。
- 清单里的 `tool_search` / `shell` / `apply_patch` / `programmatic_tool_calling` / `namespace` / `code_interpreter` 全未探针。
- `include` 的其他取值；上游是否支持 `include` 这个字段本身（只知道这一个值被吃掉）。
- `grok-4.5` / `grok-4.6` / `mai-code-1.1-flash` / `gpt-5.3-codex` / `gpt-5.4*` / `gpt-5.6-*` 上的 web search 行为（本次只测 gpt-5.5）。
- 同一响应内多个 `web_search_call` 并发时的 `output_index` 与 id 行为。
- `status: "searching"` / `"failed"` / `"incomplete"` 未在本次观测到。
- 流式下带 `url_citation` 时是否发 `response.output_text.annotation.added` 事件（C2 这次答案没有引用）。
- Anthropic 腿带 `anthropic-beta` 头时 server tool 是否仍被拒（本次未加 beta 头）。

---

## `/models` 是否给出 hosted web search 信号

**追加探针，2026-08-20，1 次请求。** 完整原始响应存于 [`exp/260820-websearch-probe/raw/models-live.json`](../../exp/260820-websearch-probe/raw/models-live.json)（42 个模型，67,656 字节）。用户裁决「能力判定优先看上游 `/models` 有没有信号，没有信号才由配置项手动维护」，本节回答前半句。

### 结论：**没有。实时目录里不存在任何可用于判定 hosted web search 的信号。**

这不是「基于过期 ref 的旧推论」，而是对**今天的实时目录**重新做的判定。证据权重：**强，一手，全量扫描而非抽样**。

### 1. `capabilities.supports` 的键并集（42 个模型全量）

```
adaptive_thinking, dimensions, max_thinking_budget, min_thinking_budget,
parallel_tool_calls, reasoning_effort, streaming, structured_outputs, tool_calls, vision
```

**与过期 ref 的并集完全相同——10 个键，一个没多，一个没少。** 目录换了模型，能力位的词汇表没变。

### 2. 键名含 `search` / `tool` / `builtin` / `web` 的全部路径（递归任意深度）

```
.capabilities.supports.parallel_tool_calls
.capabilities.supports.tool_calls
```

只有这两个，都是**普通 function calling** 的能力位，与 hosted server tool 无关。

补做了一次**值级**扫描：在整个 67KB 响应的**任意位置**（键、值、字符串片段）正则搜 `search|web_|builtin|hosted`，**零命中**。所以不存在「藏在 `warning_message` 或 `policy` 文案里的信号」这种可能。

其余键并集（供参考）：

| 层 | 键 |
|---|---|
| 模型顶层 | `billing, capabilities, id, is_chat_default, is_chat_fallback, model_picker_category, model_picker_enabled, name, object, policy, preview, supported_endpoints, vendor, version, warning_message` |
| `capabilities` | `family, limits, object, supports, tokenizer, type` |
| `capabilities.limits` | `max_context_window_tokens, max_inputs, max_non_streaming_output_tokens, max_output_tokens, max_prompt_tokens, vision` |

### 3. 已实测成立的模型能否与其余 `/responses` 模型区分开？——**不能**

广告 `/responses` 的模型现在有 **12 个**。逐字段对比已实测 web search 成立的 `gpt-5.5`（本次）与 `gpt-5.6-sol`（`copilot-api-js` 2026-08-11）：

| 字段 | 是否能把「已实测为真」的两个与其余 10 个分开 |
|---|---|
| `capabilities.supports` 的 true 集合 | **不能**。12 个里有 11 个完全相同（`parallel_tool_calls, streaming, structured_outputs, tool_calls, vision`），唯一的例外 `mai-code-1-flash-picker` 只是少了 `vision` |
| `reasoning_effort` 取值表 | **不能**。`gpt-5.5` 是 `[none,low,medium,high,xhigh]`，`gpt-5.6-sol` 是 `[…,max]`——两个已实测为真的模型**彼此就不同**，何况 `gpt-5.4` 与 `gpt-5.5` 逐字相同 |
| `capabilities.type` | **不能**，12 个全是 `chat` |
| `capabilities.limits` 键集 | **不能**，12 个里 11 个相同 |
| `model_picker_category` | **不能**。已实测为真的两个都是 `powerful`，但 `gpt-5.3-codex`、`gpt-5.4` 也是 `powerful`，而 `gpt-5.6-terra` 是 `versatile` |
| `billing.restricted_to` | **不能**。`gpt-5.5` 与 `gpt-5.6-sol` 恰好都是 `[pro_plus, business, enterprise, max]`，但这是**订阅档位**，描述的是「谁能用这个模型」，不是「这个模型能干什么」；换个账号档位就变，拿它当能力 oracle 是把账单当能力 |
| `preview` / `policy` / `warning_message` | **不能**，无区分度 |
| `vendor` | **有区分度，但区分的不是 web search**：12 个里 `OpenAI` 7 个、`xAI` 2 个（grok-4.5/4.6）、`Microsoft` 2 个（mai-code）、`Azure OpenAI` 1 个（gpt-5-mini） |

**关键点**：`gpt-5.5` 与 `gpt-5.4`、`gpt-5.6-terra` 在目录里**逐字段无法区分**（除了 `id`/`family`/`version` 这三个同义的名字字段和 `billing`）。目录里没有任何东西知道 web search 这件事。

### 4. 建议的手工判定依据

**推荐**：配置项维护一份**模型 id 允许清单**，默认值取

> `vendor == "OpenAI"` **且** `supported_endpoints` 含 `/responses`

即 7 个：`gpt-5.3-codex`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.5`、`gpt-5.6-luna`、`gpt-5.6-sol`、`gpt-5.6-terra`。

选它而不选「模型名前缀 `gpt-`」的理由：前缀会把 `gpt-5-mini` 卷进来（它的 `vendor` 是 `Azure OpenAI`，是另一条供给链），也会漏掉将来 OpenAI 换掉 `gpt-` 命名的情况；`vendor` 字段是目录里唯一一个**语义上与「这个 hosted tool 由谁实现」相关**的字段。

**它会误判哪些模型，逐条说明**（全部未测量，这是清单必须可配置的原因）：

| 模型 | 默认判定 | 风险 |
|---|---|---|
| `gpt-5.3-codex` | 判为支持 | **最可疑的假阳性**。codex 专用模型，工具面与聊天模型不同，很可能不吃 `web_search` |
| `gpt-5.4-mini`、`gpt-5.6-luna` | 判为支持 | lightweight 档，hosted tool 常是首个被裁掉的东西 |
| `gpt-5.4`、`gpt-5.6-terra` | 判为支持 | 与 gpt-5.5 目录上无法区分，假阳性概率低但仍是推断 |
| `grok-4.5`、`grok-4.6` | 判为**不支持** | **可能的假阴性**。xAI 自带搜索能力，Copilot 的 `/responses` 腿是否透出来完全未知 |
| `mai-code-1.1-flash`、`mai-code-1-flash-picker` | 判为不支持 | 同上，未知 |
| `gpt-5-mini` | 判为不支持 | 假阴性风险中等：它是 OpenAI 家族但挂在 `Azure OpenAI` vendor 下 |

**失败方向**：判错的代价不对称。假阳性 = 用户的 WebSearch 请求撞 400（可见的硬失败）；假阴性 = 声明被剥离，用户以为在搜其实没搜（静默降级）。所以默认清单**宁可窄**，把不确定的留给配置打开。若要更保守，把默认清单收到已实测的 `gpt-5.5` + `gpt-5.6-sol` 两个也是合理的——代价是每上一个新模型都要人工加一次。

### 5. 一个目录之外的、真正的运行期信号（本次副产品，值得单独裁决）

B2/B9 证明：向 `/responses` 发一个不认识的 builtin 工具类型，上游 400 的 message 里会**列出该端点当前接受的全部 builtin 工具名**（本次是 15 个，含 `web_search_preview`）。这意味着存在一条**不依赖目录、也不依赖手工清单**的能力探测路径：对某个模型发一次带哨兵工具类型的最小请求，从错误体里读回它的 builtin 工具清单。

**没有验证的前提**（不要当已知）：这份清单是**按模型**给的还是整个 `/responses` 端点共用一份——本次只在 `gpt-5.5` 上见过两次，两次内容一致，**无法区分这两种解释**。若它是端点级的，这条路答不出「哪个模型支持」，只能答「端点接受哪些名字」。要用它就得先在第二个模型上验证一次。

记在这里，不主张现在就实现：它与「配置项手工维护」是两条路，选哪条应当由用户裁决。
