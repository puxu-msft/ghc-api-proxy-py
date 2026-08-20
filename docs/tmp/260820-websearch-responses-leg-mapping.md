# Responses 腿 hosted web search：映射实现

日期：2026-08-20
性质：现行实现说明 + 与官方／参考项目做法的对照 + 待裁决点

**取代** [`260820-websearch-responses-leg-400-fix.md`](260820-websearch-responses-leg-400-fix.md) 的修复方案（那份是剥离，让 400 消失但 web search 一并不可用；用户裁决不符合初衷）。那份文档的根因分析、对 spec 的事实更正与评审处置仍然有效，不重复于此。

## 1. 现在的行为

Anthropic 客户端声明 web search，模型走 Responses 腿：**搜索真的执行**，答案带着搜索结果回到客户端，并且客户端看得见模型搜了什么。

真实上游存证（`tests/cassettes/responses_web_search_nonstream.json`，gpt-5.5）驱动的端到端结果：

```json
"content": [
  {"type": "text", "text": "[web_search] time: {\"utc_offset\":\"-04:00\"}"},
  {"type": "text", "text": "Today's date is **Thursday, August 20, 2026** in U.S. time zones. "}
]
```

流式路径产出等价的两个块，且**不再有空块**（见 §3.3）。

## 2. 请求侧

### 2.1 映射

| 输入（Anthropic） | 发往 `/responses` |
|---|---|
| `{"type":"web_search_20250305","name":"web_search"}` | `{"type":"web_search"}` |
| 带 `user_location` | `{"type":"web_search","user_location":{...}}` |
| `web_search` / `web_search_preview` / `web_search_preview_2025_03_11` | 原样保留（本就是上游合法值） |
| `web_fetch_20250910` | 原样透传，未处理（§5.1） |
| `bash_20250124` 等客户端执行型 | 原样透传，未处理（§5.1） |

判据是 `<family>_<YYYYMMDD>`（8 位 ASCII 数字后缀），不是 `web_search_` 前缀——`web_search_preview` 与 `web_search_preview_2025_03_11` 都以该前缀开头且都是上游合法值，前缀判据会把它们从 Responses→Responses 直通里改写掉。同时它对未来的日期版本仍然有效。

### 2.2 各字段的处置

| 字段 | 处置 | 依据 |
|---|---|---|
| `user_location` | **透传**，但只保留 `type`／`city`／`region`／`country`／`timezone` 五个已实测键 | 实测写入 200 且原样回显。未知子参数实测使整条请求 400，所以剥离一个未知键好过赔上整轮 |
| `max_uses` | 剥离 + 记 `SERVER_TOOL_CONSTRAINT_DROPPED` | 实测 `Unknown parameter`。它是**成本上界**，丢弃导致更多搜索与延迟，但不反转任何断言，且上游回报 `tool_usage.web_search.num_requests` 事后可查 |
| `allowed_domains` / `blocked_domains` | **拒绝整个请求**（400，调用上游前），错误码 `server_tool_constraint_not_representable`，`field_path` 精确到该字段。空数组视同未提供，不拒绝 | 实测 `Unknown parameter`。它们与 `max_uses` **不同类**：这是用户明确要求的**收紧**，丢弃等于把限制变成 no-op，且**事后无法补救**——搜索在上游执行、结果直接进模型，代理从头到尾看不到读了哪些站点。这是 spec §3.4 裁决 D1 的默认分支 |
| 允许集之外的字段 | **拒绝整个请求**，错误码 `unsupported_field` | 今天的未知字段是明天有语义的字段，静默剥离会把它要求的东西变成 no-op——与域名限制同类的失败，只是来得更晚、更没人看着 |
| `name` | 不写入 | builtin 工具对象没有这个键 |
| 多条 web search 声明 | 合并成一条 `{"type":"web_search"}` + 记 loss | spec §3.5。两个相同的 builtin 条目是上游从未被问过的形态，而第二条说不出第一条没说的东西 |
| `cache_control` | 不写入 | 块级缓存标记，该端点自己按前缀缓存 |

### 2.3 `tool_choice`

指向 web search 声明的 named choice 会**跟着改写**成 `{"type":"web_search"}`——但**仅当那个名字不同时属于一个普通 function tool**。

后半句是 spec §4 点名的陷阱：客户端可以把一个普通 function tool 也命名为 `web_search`。两者都声明时，choice 指的是哪一个是**客户端自己的歧义**，替它判成 hosted search 等于代理凭空作答，会把客户端写的一次函数调用变成它从没要求过的搜索。所以那种情况下 choice 原样保留。

必须做，因为 builtin 工具对象**没有 `name`**：choice 若仍按名字指向它，就指向了不存在的东西，整轮失败——那等于映射把一个 400 换成另一个 400。上游对 choice 位置的 `{"type":"web_search"}` 实测 200，回显归一化为 `web_search_preview`，`num_requests` 为 1 且 output 里确有 `web_search_call`，**它真的强制执行了搜索**。

**仅在同格式路径（Responses→Responses）可达**。Anthropic 腿的 `tool_choice` 落进 `extensions`，跨格式时整体丢弃——那是一个独立缺口，见 §5.2。

### 2.4 能力门：不在清单就拒绝请求

清单是 `model_providers.<name>.models_support_web_search`（用户 2026-08-20 裁决的键名），与 `disabled_models` 同族的精确 id 匹配，默认为目录里 vendor 为 OpenAI 且广告 `/responses` 的七个模型。

判定落在**订阅者层**而不是 codec：判据是 *resolved* model，而 codec 只拿得到客户端请求的名字。

**不通过时返回 400，不是剥离声明。** 这是 2026-08-20 用户裁决「去除 drop 策略」的结果，理由见 §3.5——在 Claude Code 的两段式架构下，剥离会让模型凭记忆作答然后被贴上搜索结果标签。

**计数腿豁免**：`/v1/messages/count_tokens` 只测量、不产生模型输出，没有伪造风险，拒绝它只会把一个有答案的问题变成错误。标记是 `pipeline/subscribers/counting.py` 的 `COUNTING_ONLY`。

## 3. 响应侧

### 3.1 我们手上有什么

`web_search_call` item **恰好四个键**：`action`、`id`、`status`、`type`。**搜索结果不在里面**——它们直接进了模型上下文，已经体现在随后的答案正文里。`id` 是 416 字符的不透明句柄。

（本项目 cassette 两次实测，与参考项目跨仓库跨日期的记录一致。）

### 3.2 渲染成一行文本

```
[web_search] <query>
```

`query` 缺失时退到 `queries` 以 `", "` 连接；`action` 整个缺失时（`status: incomplete` 观测到过）渲染成裸 `[web_search]`——那是真的：搜索发生了，我们说不出搜的什么。

**这个文本形状与 Anthropic 腿摊平历史后的形状完全一致**，由同一份实现产出（`src/app/pipeline/server_tool_text.py`）。理由是 spec §10 的硬性要求：同一段对话会在两条腿之间迁移（客户端换模型就会），两套措辞会让一份历史里出现同一事实的两种形态，而**不会有任何东西报错**。

**`id` 不进正文**，这是与参考项目的明确分歧，见 §4.2。

### 3.3 流式：空块的来源与修法

`web_search_call` **没有任何 delta 事件**，且 `output_item.added` 上只有 `id`／`status`／`type`——**`action` 只在 `done` 上出现**。

所以常规的「added 开块 → delta 累积 → done 收口」模型在这里失效：draft 里从来没有内容，收口时产出的是**空 text 块**。客户端在每次搜索前都会收到一个空内容块。

修法是在 `_close` 里从**收口事件的权威快照**读 `action`，而不是从 draft 读——与 `_reasoning_signature` 处理 `encrypted_content` 的既有做法同源。

关联键用 `output_index` **不用 `id`**：本项目实测同一个 `web_search_call` 在五个事件里带了五个互不相同的 416 字符 id。现有 assembler 本来就按 `output_index` 关联，天然免疫这一点。

### 3.4 三个专有事件

`response.web_search_call.in_progress` / `.searching` / `.completed` 只带 `item_id`／`output_index`／`sequence_number`，**不带内容增量**，被忽略，不触发任何块的开启或关闭。

### 3.5 无法执行时：合成一个「搜索失败」的结果，而不是剥离、也不是报错

2026-08-20 的客户端取证（[`260820-claude-code-websearch-request-forensics.md`](260820-claude-code-websearch-request-forensics.md)）推翻了原本的处置，用户随后裁决「去除 drop 策略，drop 远不如 mock_result，凭记忆作答不可接受」。

**为什么 drop 不可接受。** Claude Code 的 web search 是两段式：主对话里 `WebSearch` 是**普通 function tool**（无 `type`，我们碰不到）；模型调用后，客户端**另起一个子请求**，`tools` 数组只有 `web_search_20250305` 一项，用户消息是 `Perform a web search for the query: X`，190/190 真实样本皆如此。剥掉它唯一的工具，请求**不会失败**——模型凭记忆作答，而客户端**无条件**把回复拼上 `Web search results for query:` 抬头交回主对话。无 `is_error`、无标记。**记忆里的文本被当作搜索到的事实交付。**

**为什么最终不是 400。** 400 有实证（转录里模型正确降级、改用 WebFetch），但同一份转录也显示客户端**重试了 3 次**——HTTP 错误在客户端看来是传输故障，值得重试，而一个跑不了的搜索不会在第三次变得能跑。

**所以合成结果。** Anthropic 为这种情形定义了形态：200 + `server_tool_use` 配对 `web_search_tool_result`，其 `content` 是**单个** `web_search_tool_result_error` 对象（官方文档原文：搜索出错时 API「仍返回 200」，`content` 是一个对象而非列表）。失败的**工具**不会被重试，而且模型是用自己的协议被告知搜索失败的，不必去解读一段 HTTP 错误字符串。

`error_code` 取 `unavailable`（文档定义为「发生了内部错误」）。其余合法值都在描述没发生的事：`too_many_requests`、`max_uses_exceeded`、`query_too_long`、`request_too_large`、`invalid_tool_input`。**spec §5.3 悬着的 P12 探针项就此有答案：`unavailable` 合法。**

**不是这两种**：`content: []` 是「搜索了但没匹配」的文档形态，那是关于**互联网**的断言而不是关于我们的；纯文本说明也不行，因为客户端的抬头会把那段说明当作搜索结果呈现。

实现：合成的是**上游方言**的回复（Anthropic SSE 或 JSON），走与真实回复完全相同的 assembler、buffer 与 delivery 路径——绕过它们会造出系统里唯一一条从未被其他东西检验过的成帧路径。`HandledRequest.synthesized` 告诉交付侧按 Anthropic 读，而 route 仍然记录**本该**由谁作答，供控制台行使用。

**未经真实客户端验证，如实记录**：400 那条有转录实证，这条只有协议文档。若实际效果更差，替代方案的证据在取证报告 §4.2。

**仍然返回 400 的一处**：`web_search_domain_restrictions: error`（D1 的显式配置）。那是「客户端要求无法表达」而不是「搜索不可执行」，且是运维显式选择要它响亮失败。**但它同样会被客户端重试 3 次**，这一点记账于此。

## 4. 与官方／参考项目的对照

### 4.1 官方 VS Code Copilot Chat：不用 hosted web search

- 唯一处理点是**剔除**：`oaiLanguageModelServer.ts:134-143` 过滤 `tool.type.startsWith('web_search')`。提交 `52032e48d`，**2025-11-01**。
- `responsesApi.ts:42-47` 把 `type: 'function'` 写死在 tools 构造里，**结构上产不出 builtin 工具**。
- 响应侧完全不处理 web search（但**处理了** `image_generation_call`，说明是有选择地只接了一个 hosted item，不是不知道）。
- 它自己的「网页搜索」走的是另一条路：`#web` → GitHub platform 远程 agent 的服务端 `bing-search` skill，进的是请求体的 `copilot_skills` 字段，**从不进 `tools` 数组**。

**两条不能照抄的理由**：

1. **那个剔除决策是 2025-11 做的**，而我们 2026-08-20 实测 `{"type":"web_search"}` 返回 200 并真的执行搜索。当时正确，今天不是最优。
2. **`disallowedTools: ['WebSearch']` 的适用范围比看上去窄得多**：它只作用于 VS Code 内嵌的 Claude Agent SDK 实例（`claudeCodeAgent.ts:432-434`）。同一扩展的 terminal 路径把**真的 `claude` CLI** 指向同一个本地服务器，命令行没有任何工具禁用，而那个服务器（`claudeLanguageModelServer.ts`）对 `tools` **零过滤**。**我们的代理与后者同构，而第一方在这个位置根本没解决问题**——所以这里没有可抄的答案。

（完整审计：[`260820-vscode-ext-websearch-audit.md`](260820-vscode-ext-websearch-audit.md)）

### 4.2 参考项目 copilot-api-js：做了映射，深度到此为止

它的实现就是「请求侧一行映射表 + 响应侧一行降级文字」：

| 面 | 它的做法 | 我们 |
|---|---|---|
| 请求侧映射 | `web_search_` → 裸 `{"type":"web_search"}`，**只有一个键** | 同，但**保留 `user_location`** |
| `max_uses`／域名限制／`user_location` | **全部静默丢弃**，无 warn 无 observation | `user_location` 透传；`max_uses` 记 loss；**域名限制拒绝整个请求** |
| `tool_choice` | 按 name 找回原声明走同一映射，译不出就整个省略 | 同，但**同名 function tool 存在时不改写**（spec §4 的陷阱） |
| 能力门 | 在产腿上**完全没有** | 同（§2.4） |
| 响应侧 | 降级成一个 text 块，逐字 `[web_search: "<q>"] (id: <id>, status: <status>)` | `[web_search] <query>`，**不含 id** |
| 关联键 | `output_index`，不用 `id` | 同 |
| `url_citation` | **完全且静默丢弃** | 同（§5.4） |
| 原生块对／citations／续接／usage／流式子事件 | **六项全无** | 同 |
| 多重声明去重 | 未做 | 合并成一条 |
| `done` 无 `added` | 有双保险 | 有（本轮评审后补） |

**唯一明确不照抄的一条**：`webSearchCallToText` 把 416 字符的 `id` 写进面向客户端的正文（`server-tool.ts:26`）。它会被客户端存进历史、随每一轮重发，对模型不可读，还把服务端句柄暴露给客户端；而在我们这里 id 每个事件都不同，该值连稳定引用都算不上。参考项目自己的 `exp/encrypted-content-400/` 事故正是同族失败模式。

（完整审计：[`260820-copilot-api-js-websearch-audit.md`](260820-copilot-api-js-websearch-audit.md)）

## 5. 已知缺口

### 5.1 其他 Anthropic typed tool 仍原样透传

`web_fetch_20250910`、`bash_20250124`、`text_editor_*`、`computer_*`、`memory_*`、`tool_search_*` 都没有 `input_schema`，都会被 `_function_tool` 原样透传给 `/responses`，且**上游那条 400 的枚举里一个都没有**。

它们与 web search 不同类，不能用同一种处置：`web_fetch` 在该端点下**没有任何可映射的拼法**（spec §13 要求本地明确拒绝）；`bash_`／`text_editor_` 是**客户端执行型**工具，静默剥掉会改变对话能做什么。两者都需要一条本地拒绝路径，那是独立的一片。

**在那一片落地前，声明这些工具的客户端仍会整轮 400。**

### 5.2 `tool_choice` 跨协议时被整体丢弃

`SemanticRequest` 没有 `tool_choice` 字段；Anthropic 的 `tool_choice` 落进 `extensions`，`extensions_for()` 在跨格式时返回空并记 `EXTENSIONS_NOT_CARRIED`。

所以 **Anthropic 客户端的 forced tool choice 从未到达上游**。与 spec §4 要求的映射表直接冲突。§2.3 的改写只在同格式路径生效。

### 5.3 能力门未实现（spec D4 已裁决要配置项）

见 §2.4 的取舍。用户已裁决它应落到配置项，**本片未做**。

### 5.4 `url_citation` 未使用

上游后续 message 的 `annotations` 可能带 `url_citation`（`{type,url,title,start_index,end_index}`），也可能是空数组（两个反向样本各一次）。目前**丢弃**。

spec §5.3（裁决 D6）要求用它填充 `web_search_tool_result.content`。见 §6。

### 5.5 `tool_usage.web_search.num_requests` 未采集

上游一直在响应体里回报搜索次数，双方项目都没读。它可以直接进日志／footer 的可观测 facts。

## 6. 待裁决：是否升级到 D6 的原生块对

用户 2026-08-20 裁决 D6 要求响应侧「尽量还原成原生块」——`server_tool_use` + `web_search_tool_result` 块对，而不是本片交付的文本行。

**本片没有做**，因为它不是一行代码：需要 citation 归因（spec §5.3 的三分支）、成块时点从 `output_item.done` 推迟到后随文本块的 `content_part.done`（spec §6.3，否则 citation 还没到）、以及请求侧识别并摊平自己合成的块（spec §5.4）。

**本片的文本行不阻碍它**：升级时替换的是同一个渲染点，且文本形状的共享实现（`server_tool_text.py`）正是两条腿一致性的落点。

需要裁决：现在就上 D6，还是先让搜索跑一段时间再说。

## 7. 验证

- 全量：`uv run pytest -q` → **1424 passed, 2 skipped, 0 failed**。
- 端到端两条路径均由**真实上游存证**驱动（`tests/cassettes/responses_web_search_*.json`），非手写 stand-in。选 cassette 是因为「`added` 上没有 `action`」这种不对称正是手写 fake 会写错的地方——它会按「事件应该携带什么」来写。
- 变异验证（四项，均已还原）：
  - 屏蔽映射谓词 → 6 个测试红
  - `user_location` 不剥未知子键 → 对应测试红
  - 不改写 `tool_choice` → 对应测试红
  - 流式搜索退回空块 → 端到端测试红，失败输出逐字显示 `['', 'Today's date is ...']`
- Ruff `check`、Pyright 于全部改动文件干净。

## 8. 评审处置（第三轮，异源评审）

评审报 2 blocker、3 major。处置如下：

| 发现 | 定级 | 处置 |
|---|---|---|
| 域名限制被无条件放宽，违反已裁决 D1 | blocker | **采纳**。改为调用上游前拒绝，错误码与 `field_path` 按 spec §3.4。D1 的三取值配置仍缺，本片实现的是它的默认分支 |
| 响应侧是 text 行而非 D6 的原生块对 | blocker | **降级为待裁决（§6）**，理由见下 |
| `_repoint_tool_choice` 会误改同名 function choice | major | **采纳**，是真 bug。改为「名字同时属于普通 function tool 时不改写」 |
| 没有实现已裁决的 capability gate | major | **采纳方向，本片未做**，理由见下 |
| 多重声明不去重；未知字段应 REJECT 而非静默剥离 | major | **两条都采纳** |
| （评审附带）`done` 无 `added` 时搜索静默丢失 | — | **采纳必修**。已实测复现（返回空元组），spec §6.3 专门要求补登记 |
| （评审附带）并发 call 的 `done` 逆序到达会逆序交付 | — | **记账不修**，见 §5.6 |

**为什么 D6 不当作 blocker**：它不是安全或正确性问题——文本行与原生块对都让搜索可用，客户端都拿得到答案。它需要 citation 归因（spec §5.3 三分支）与成块时点从 `output_item.done` 推迟到后随文本块的 `content_part.done`（spec §6.3），是独立的一片。本片没有悄悄跳过它，而是列为 §6 的裁决点。评审另一条批评成立并已采纳：新增测试确实固化了一个临时形态，测试注释已写明这一点。

**为什么 capability gate 本片未做**：它的正确落点是**订阅者层**而不是 codec。`to_openai_responses` 只拿得到 `SemanticRequest`，其 `model` 是**客户端请求的名字而非 resolved model**；`RequestContext`（订阅者可见）才有 `resolved_model`，但它不持有模型目录，拿不到 `vendor` 与 `supported_endpoints`。更要紧的是 spec §3.4 与 §9.3 **两处都写着「键名待定」**，且要求与用户亲笔的 `docs/.human-controlled/config.example.yaml` 的扁平键词汇对齐——那是用户的裁决，不由实现者发明。

### 5.6 并发 `web_search_call` 的 `done` 逆序会逆序交付

实测：两个 call 分别 `output_index` 0 与 1，若 `done` 以 1、0 的顺序到达，块以 index 1、index 0 的顺序交付（`index` 值本身正确，按 `added` 顺序分配）。

**不是本片引入**：`_close` 对所有 item 类型都是即到即发，`function_call` 同样如此。上游是否真会乱序发 `done` **未探针**。修它要在交付层引入按 index 排序的缓冲，超出本片范围。**记账。**

## 9. 相关文档

- 前一版（剥离方案，含根因分析与两轮评审）：[`260820-websearch-responses-leg-400-fix.md`](260820-websearch-responses-leg-400-fix.md)
- 产品规格：[`../agents/anthropic-responses-bridge/hosted-web-search-spec.md`](../agents/anthropic-responses-bridge/hosted-web-search-spec.md)
- 上游实测一手报告：[`260820-websearch-upstream-probe.md`](260820-websearch-upstream-probe.md)
- Responses 腿全面调研：[`260820-websearch-on-responses-leg.md`](260820-websearch-on-responses-leg.md)
- 官方扩展审计：[`260820-vscode-ext-websearch-audit.md`](260820-vscode-ext-websearch-audit.md)
- 参考项目审计：[`260820-copilot-api-js-websearch-audit.md`](260820-copilot-api-js-websearch-audit.md)
