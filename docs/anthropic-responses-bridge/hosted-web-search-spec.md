# Responses 腿 hosted web search 产品规格

## 文档状态

- **类型**：独立产品规格。它是 [spec.md](spec.md) 的**增补与定点覆盖**，不是它的替代品。凡本文件未提及的行为，一律回到 `spec.md`。凡本文件与 `spec.md` 冲突的条款，本文件在其明确列出的范围内优先，冲突点在 §11 逐条列名。
- **状态**：`DRAFT — D1／D4／D6 已裁决，其余待裁决`。用户 2026-08-20 第三批裁决已定案三项，见下条；§14 剩余的 D2／D3／D5／D7 未获裁决前，对应条款按本规格给出的保守分支执行。

> ## ⚠️ 2026-08-22：本规格与在产实现已分叉，读之前先读这一节
>
> 独立对账见 [`../hosted-web-search/reports/260822-websearch-doc-reconciliation.md`](../hosted-web-search/reports/260822-websearch-doc-reconciliation.md)；实现的当前状态见 [`../hosted-web-search/status.md`](../hosted-web-search/status.md)。三处差异**已按用户后续裁决更正在下文各节**，一处**尚待用户裁决、下文原文未动**：
>
> 1. **多了一条本规格没有的轴：功能总开关。** 用户 2026-08-21 裁决 hosted web search **默认关闭**，键是 `model_translation.to_openai_responses.hosted_web_search`。本规格 §2／§9 定义的能力门只谈模型与路由，按它写出来的门在默认配置下永远判通过，而实现永远判不通过。§9 已补这一轴。
> 2. **能力门不通过时不是「剥离声明」。** §8.3 起草时写的「必须剥离、不得 REJECT」已被用户 2026-08-20「去除 drop 策略，drop 远不如 mock_result」的裁决推翻：实现合成一个失败的 `web_search_tool_result`。§8.3 已改。
> 3. **配置键名与取值语义已落地。** 不再「待定」，不再是模型 id 列表；用户 2026-08-21 裁决「能力门采用版本清单，清单接受正则表达式」。§9.3 已改。
> 4. **⏳ 部分待裁决：域名限制。** 两件事，**只剩一件开着**：**（已裁，2026-08-24）**第三取值由 `drop_web_search` 改为 `empty_result`——合成 `content: []` 的有效结果，不再剥离声明，详见修订记录与 §3.4。**（仍待裁）默认值**：§3.4 与 §14 D1 写「默认 `error`」，实现是「默认 `drop_fields`」，且实现只有两个取值。**这是实现单方面偏离了用户已下的裁决**，理由（190 个真实子请求 `allowed_domains` 全部非空、且值来自主对话模型而非人，取 `error` 等于对本客户端永久禁用）写在 `src/app/config/schema.py` 的注释里，**至今没有回到用户手上重裁**。
- **2026-08-20 用户第三批裁决（推翻本规格起草时的三处偏好）**：
  1. **D6 response presentation → 尽量还原成原生块。** 起草时的偏好是降级成单个 text block；用户裁决要求还原成 `server_tool_use` + `web_search_tool_result`。§5 已按此重写，并写明「尽量」的实际边界。
  2. **D1 域名限制 → 可配置。** 默认 `error`（大声报错），可选 `drop_unsupported_fields`（剥离降级）与 `drop_web_search`（整条声明剥离）。§3.4 当时按此重写。⚠️ **第三取值已于 2026-08-24 被用户修订为 `empty_result`**（见修订记录与 §3.4）；本行保留的是 2026-08-20 那次裁决的原貌，不是现行规范。
  3. **D4 capability gate → 配置项手动维护。** 用户先要求确认上游 `/models` 是否给出信号；已于 2026-08-20 对实时目录（42 模型、67,656 字节）全量重判，**确认没有任何信号**，故落到配置项。§9 已按此重写。
- **开启的冻结裁决**：[`reports/260806-arbitrate-server-tool-contract.md`](reports/260806-arbitrate-server-tool-contract.md) 要求「若未来用户决定引入 Responses hosted web search，应以独立产品规格一次性冻结 declaration、forced choice、response presentation、stream lifecycle、History／continuation、错误与 capability gate，不能借 request converter 映射表增量恢复」。用户 2026-08-20 的裁决（「anthropic 上游不支持，但 gpt 上游支持 websearch」「该路径要正确支持 server tool web_search」）是那道门的开启，本文件是它要求的那份规格，七个面在 §3～§9 逐面给出规范性行为。
- **一手证据基线**：[`../hosted-web-search/reports/260820-websearch-upstream-probe.md`](../hosted-web-search/reports/260820-websearch-upstream-probe.md)（本项目 19 次上游实测，gpt-5.5，2026-08-20，原始输出在 `exp/260820-websearch-probe/raw/`）；真实响应样本 `tests/cassettes/responses_web_search_nonstream.json` 与 `tests/cassettes/responses_web_search_stream.json`。参考项目的做法记录在 [`../hosted-web-search/reports/260820-websearch-on-responses-leg.md`](../hosted-web-search/reports/260820-websearch-on-responses-leg.md)，其中「`web_search_call` 的 id 在事件间稳定」一条**已被本项目实测推翻**，不得引用。
- **证据权重**：§12 逐条标注每项规范性要求的依据是实测、设计裁决，还是仍需探针。凡标注为「仍需探针」的行为，实现时必须按本规格给出的保守分支执行，不得按推断放开。
- **索引待补**：[README.md](README.md) 的「权威边界」表需要新增本文件一行；本规格作者不代改该索引。
- **剩余修订项（本文件尚未定稿）**：独立评审 [`../hosted-web-search/reports/260820-review-hosted-web-search-spec.md`](../hosted-web-search/reports/260820-review-hosted-web-search-spec.md) 报 blocker 3、major 9、minor 7。**三条 blocker 与 MJ-3、MJ-6、MJ-9 已处置**（见 §6.3 的成块时点重写、§11 覆盖清单、§14 的裁决登记、§3.4 的 `tool_choice` 清理、配置键命名待对齐、error 裸对象）。**尚未处置**：MJ-1／MJ-2（§12 证据权重表与 §13 探针表未随裁决更新，P12 未登记）、MJ-4（§8.3 与 §3.4 的组合情形未定义）、MJ-5（§9.3 默认值「运行期谓词 vs 冻结字面量」两解并存待收敛）、MJ-7（§5.3 三分支条件不互斥，须改为有序判定）、MJ-8（派生 id 跨轮次重复的唯一性范围未声明）、以及全部 minor。**实现前必须先关闭这些项。**

## 修订记录

**本文是活文档，不冻结**（2026-08-24 用户裁定全面废除 spec 冻结）。新裁决、实测或发现与本文冲突时当场修订，每次修订记入下表。

| 日期 | 条款 | 变化 | 触发 |
|---|---|---|---|
| 2026-08-24 | §3.4、§14 D1 | 第三取值由 `drop_web_search`（整条声明剥离）改为 `empty_result`（合成 `content: []` 的有效结果）。原取值在本客户端上做不到它承诺的事——剥离后模型凭记忆作答而客户端标为搜索结果 | 用户裁决 |
| 2026-08-24 | 本表 | 建立修订记录 | 用户裁定 spec 不冻结，修订须可审计 |
| 2026-08-30 | §1 新增末两段、§8.3 新增末条、§9.0 新增末段 | 把「能力门只在 Anthropic→Responses 这条 crossing 上求值」与「§8.3 的合成只在客户端腿是 Anthropic Messages 时成立」写成规范性条款。原文只在 §1 说了覆盖范围是 Anthropic 客户端，没有把它写成对**能力门与合成**的约束：实现遂按 `target_format`（上游腿）判门，对直连 Responses 客户端也击发；合成侧则完全没有腿判据 | GitHub issue #1（两条独立路径，各自撕流与静默错协议，均已实测）＋ 用户 2026-08-30 裁决「直连 Responses 的声明放行到上游」 |


## 1. 范围

本规格覆盖：Anthropic Messages 客户端声明 web search server tool，请求经本项目路由到 **Responses 上游**并由上游 hosted web search 真正执行，其结果回到 Anthropic 客户端的完整往返。

本规格**不**覆盖，且明确划出（§13 展开理由）：`web_fetch`、`code_execution`、上游枚举里其余 builtin 工具、`/v1/messages` 直连 Anthropic 腿的任何行为改变、`/v1/messages/count_tokens` 腿、反应式 400 剥离重试、Responses continuation 载体。

**本规格的所有规范性行为只在一条 crossing 上成立：inbound 是 Anthropic Messages，target 是 Responses 上游。**「Responses 腿」在本文里指的始终是这条 crossing 的上游那一半，从来不是「凡是 target 为 Responses 的请求」。这两者在实现里被混同过一次，代价见 §9.0 末段。

因此本规格**不**覆盖、且**不得**据本规格施加任何限制的还有一项：**inbound 就是 `/responses` 的直连请求自己声明的 `{"type":"web_search"}`**。该对象是客户端用上游自己的词汇写给上游的，本项目没有翻译它，`model_translation.*` 下的开关按其键名管的也不是它。它的去留由该端点自己的上游契约决定，代理**不得**拦截、剥离或合成答复。用户 2026-08-30 裁决：放行到上游。

## 2. 术语

- **hosted web search**：由 Responses 上游自己执行的搜索。代理既不发起搜索，也不持有搜索结果。
- **声明**：Anthropic 请求 `tools[]` 中 `type` 以 `web_search_` 开头的条目，例如 `{"type":"web_search_20250305","name":"web_search"}`。
- **能力门**：判定「当前 attempt 的 resolved model 经 Responses 腿是否真正执行 hosted web search」的算法，定义在 §9。
- **搜索块对**：本规格规定的、由一个 Responses `web_search_call` item 产生的**一对** Anthropic content block（`server_tool_use` 紧接 `web_search_tool_result`），形态在 §5 冻结，成块时点在 §6.3 冻结。

本规格说「块级交付」不说「流式渲染」。`web_search_call` 是 item 与 Anthropic block 天然一一对应的类型。

## 3. 面一：declaration 映射

### 3.1 识别

- 声明的识别判据**必须**是 `type` 以 `web_search_` 开头（含尾部下划线），**不得**逐字匹配 `web_search_20250305`。Anthropic 给 server tool 打日期版本，逐字匹配会在下一个日期版本上静默失效。
- 该判据**必须**只在路由已确定为 Responses 腿、且能力门（§9）通过时才触发映射。其余情形按 §8.3 处置。

### 3.2 映射结果

通过能力门的声明**必须**映射为 Responses 工具对象，其键集**必须**是以下二者之一，不得多也不得少：

| 输入 | 输出 |
|---|---|
| 声明不含 `user_location` | `{"type": "web_search"}` |
| 声明含 `user_location` | `{"type": "web_search", "user_location": <逐字透传>}` |

- `{"type":"web_search"}` 经实测 200，上游补默认值后回显 `{"type":"web_search","return_token_budget":"default","search_content_types":["text"],"search_context_size":"medium","user_location":{"type":"approximate","city":null,"country":"US","region":null,"timezone":null}}`。Anthropic 拼法 `web_search_20250305` 经实测 400 `Invalid value`，因此映射是必须的，不是可选的优化。
- `name` 字段**不得**写入 Responses 工具对象。上游泄漏的 builtin 工具枚举里没有该键，而上游对未知子参数的反应经实测是 400 而不是忽略。**未探针**（§12 P4）：保守分支即「不写」。
- `return_token_budget`、`search_content_types`、`search_context_size` **不得**写入。Anthropic 侧没有对应语义可映射，凭空写入等于代理替用户选参数。

### 3.3 `user_location`

- `user_location` **必须**逐字透传。Anthropic 的 `{type:"approximate", city, region, country, timezone}` 与 Responses 回显的形状实测逐字一致，且实测写入返回 200 并原样回显。
- 透传**必须**限定在已实测的五个键 `type`、`city`、`region`、`country`、`timezone`。出现其他键时，其他键**必须**被剥离并记一条 `DEGRADE` fact（字段路径精确到该键），**不得**整体透传。理由：上游对未知子参数的已知反应是整条请求 400（`allowed_domains` 等三条实测），透传一个未知键会把整轮对话打挂，而剥离只损失一个上游本来就不认识的字段。
- 键存在但值为 `null` 时**必须**照传。上游自己的默认回显里就带 `null`，它是合法值。

### 3.4 `allowed_domains`、`blocked_domains`、`max_uses`

三个字段经实测写入 `/responses` **一律 400**（`Unknown parameter: 'tools[0].<字段>'`），因此**不得**以任何形式写入上游。这一点没有裁决余地。有裁决余地的是「写不进去之后怎么办」，因为它们不是无害的装饰：

- `allowed_domains` / `blocked_domains` 是用户明确要求的**收紧**约束。静默丢弃它们并继续搜索，等于把一条限制变成 no-op，且代理**无法在事后补救**：搜索结果不在我们手里（结果落在模型正文里），`include:["web_search_call.action.sources"]` 经实测被上游 200 静默丢弃，所以我们既拿不到来源清单，也无从校验模型读了哪些站点。
- `max_uses` 是**成本上界**。丢弃它导致更多搜索、更多费用与延迟，但不反转任何语义，且上游会在响应里回报 `tool_usage.web_search.num_requests`，事后可观测。

据此，**规范行为（2026-08-20 用户裁决 D1：做成可配置，默认大声报错）**：

**键名待定，语义已定。** `docs/.human-controlled/config.example.yaml` 是用户亲笔、权威最高，它使用扁平顶层键、没有 `anthropic:` 命名空间；本规格**不得**擅自规定与之冲突的键路径。下表冻结的是**三个取值的语义**，键名须在实现前与该文件的既有词汇对齐后再定。下文以 `<unsupported_constraints>` 指代它。

取值三选一，默认 `error`：

| 取值 | 行为 |
|---|---|
| `error`（默认） | 声明含**非空** `allowed_domains` 或**非空** `blocked_domains` 时，请求**必须**在调用上游前失败，返回稳定 incompatibility error，错误码固定 `server_tool_constraint_not_representable`，字段路径精确到该字段 |
| `drop_unsupported_fields` | 剥离这些字段后继续搜索，并记一条 `DEGRADE` fact（`server_tool_constraint_dropped`），日志级别 INFO。**用户已知情并接受搜索范围比其要求更宽** |
| `empty_result`（2026-08-24 用户裁决，取代原 `drop_web_search`） | **合成一个空的有效结果返回**：`server_tool_use` + `web_search_tool_result`，`content` 为**空列表** `[]`——即协议里「搜索跑了、零结果」的形态，不是错误。不调上游，记 `DEGRADE` fact （`server_tool_constraint_yielded_empty_result`）。**必须**同步删除指向该声明的 `tool_choice`（同 §4 与 §8.3），否则 dangling forced choice 会把整轮打挂 |

**为什么由「整条声明剥离」改成「返回空的有效结构」**：原取值在本客户端上做不到它承诺的事。Claude Code 的 web search 是**独立子请求**，`tools` 里只有搜索；剥掉声明后这一轮**不会失败**——模型凭记忆作答，而客户端把回答无条件挂在 `Web search results for query:` 标题下呈现，无 `is_error`、无任何标记。**记忆被贴上「搜到的事实」的标签送到人眼前。** 返回空的有效结果则留在协议词汇里：客户端拿到形状完整的结果、模型知道自己什么都没拿到，且它是 200 携带一个正常工具结果，**不会触发客户端重试**。

> ⚠️ **一处我认为你应当知道的代价，不阻断实施**：`content: []` 在协议里读作「搜过了，没找到」，而事实是**没搜**。模型可能据此形成「网上没有这个」的错误结论，而既有的 `web_search_tool_result_error` 形态会明确告诉它「搜索没能进行」。两者的区别在能力门那条路径上你已经选了后者（§8.3，2026-08-20「drop 远不如 mock_result」）。若你希望这里也用错误形态而非空结果，说一声即改；**在此之前按你 2026-08-24 的裁决实施空结果**。

**取值改名**：行为已不再是「剥离」，继续叫 `drop_web_search` 会主动误导，故改为 `empty_result`。§3.4 原就写明「键名待定，语义已定」，取值名同理属实现前与 `config.example.yaml` 对齐的范围，**此处的改名是我的推导，不是你的裁决**。

- 该键**只**管 `allowed_domains` / `blocked_domains` 这类**收紧型**约束。`max_uses` 不归它管，见下条。
- 三种取值之下，这些字段**都不得**以任何形式写入上游——上游对它们一律 400，这一点没有裁决余地。
- 默认取 `error` 而非 `drop_unsupported_fields`：静默放宽一条用户明确要求的限制，是代理擅自改变了用户的意图，且**事后无法补救**——搜索结果不在我们手里（落在模型正文里），`include:["web_search_call.action.sources"]` 经实测被上游 200 静默丢弃，所以既拿不到来源清单，也无从校验模型读了哪些站点。报错让人看见并选择，剥离让人看不见。
- 两个字段**值为空数组**时视同未提供：剥离并记 `DEGRADE`，不失败，不受该配置键影响。空清单不表达任何收紧。

`max_uses`（对应待裁决 D2，尚未裁决，按此保守分支执行）：

- 声明含 `max_uses` 时，该字段**必须**被剥离，并记一条 `DEGRADE` fact（`server_tool_max_uses_not_enforceable`），请求继续。日志级别为 INFO。
- 与域名限制分开处置的理由：它是**成本上界**而非语义约束，丢弃导致更多搜索、更多费用与延迟，但不反转任何断言；且上游会在响应里回报 `tool_usage.web_search.num_requests`，事后可观测。


### 3.5 其余字段与多重声明

- 声明上的 `cache_control` 按 `spec.md` 既有矩阵固定 `DEGRADE`：从 wire 省略并记录精确字段路径。
- 声明上出现上述允许集之外的字段时，**必须** `REJECT`（既有 `unsupported_field`），基础 strict 政策不放宽。允许集固定为 `{type, name, max_uses, allowed_domains, blocked_domains, user_location, cache_control}`。
- 同一请求出现**多条** web search 声明时，**必须**只发出一条映射结果，其余条目合并去重并记 `DEGRADE` fact。上游对重复 builtin 声明的反应**未探针**（§12 P2），去重是保守分支。
- 通过能力门的 web search 声明与普通 function tool **必须**共存于同一个 `tools` 数组，顺序按输入顺序，web search 条目占据其原位置。

### 3.6 对现有拒绝点的改动

`src/app/protocols/anthropic_responses.py`：

- `:538` `self._reject_extras(tool, _TOOL_FIELDS, path)` —— 对 web search 族**必须**改用 §3.5 的扩展允许集；其余工具的允许集不变。
- `:539-540` `if tool.type is not None: self._fail(path, "server_tool_not_supported", ...)` —— **必须**改为：web search 族且能力门通过时走 §3.2 映射；web search 族但能力门不通过时走 §8.3 剥离；**其余任何非空 `tool.type` 继续 `server_tool_not_supported`**。no-revive 对其他 typed／server tool 原封不动。

## 4. 面二：forced choice

Anthropic `tool_choice` 映射如下，**必须**按表执行：

| Anthropic | Responses | 依据 |
|---|---|---|
| `{"type":"auto"}` | `"auto"` | 既有合同 |
| `{"type":"none"}` | `"none"` | 既有合同 |
| `{"type":"any"}` | `"required"` | 既有合同。**与 hosted builtin 并存时未探针**（§12 P1） |
| `{"type":"tool","name":<web search 声明的 name>}` | `{"type":"web_search"}` | 实测 200，上游回显归一化为 `{"type":"web_search_preview"}`，`tool_usage.web_search.num_requests` 为 1，`output` 中确有 `web_search_call` —— 它真的强制执行了搜索 |
| `{"type":"tool","name":<普通 function tool>}` | 既有 function 形态 | 既有合同 |

- named choice **必须**按 `name` 回查本请求的 `tools[]`，确认被指向的那条声明是 web search 族之后才映射为 builtin 形态。**不得**按 `name` 字符串直接判断——客户端可以把普通 function tool 命名为 `web_search`。
- 被指向的 web search 声明因能力门未通过而被剥离时（§8.3），该 `tool_choice` **必须**同步删除，不得留下 dangling forced choice。这是 `spec.md` 既有条款，本规格不改。
- 被指向的声明因 §3.4 走 REJECT 时不适用本节：整个请求已失败。
- `disable_parallel_tool_use` 保持现状不映射，本规格不改。

## 5. 面三：response presentation

### 5.1 我们手上到底有什么

`web_search_call` item 的键**恰好四个**：`action`、`id`、`status`、`type`。这一点已跨仓库、跨日期、跨模型独立复现三次以上，其中本项目 2026-08-20 的非流式与流式样本各一次。**确无 `encrypted_content`**。

`action` 在 `completed` 时形如 `{"type":"search","query":"<串>","queries":["<同一串>"]}`，`query` 与 `queries` 同时存在且内容相同。`status:"incomplete"` 时**可能整个缺 `action`**（参考项目 2026-08-05 观测到一次，2026-08-11 两次尝试不可复现——这足以要求消费者容忍该形状，不构成任何频率结论）。

**搜索结果不在 item 里**，它们在后续 message 的正文里。后续 message 的 `annotations` 可能带 `url_citation`（`{type,url,title,start_index,end_index}`），也可能是 `[]`——两个反向样本各一次。

### 5.2 「尽量还原」的实际边界（2026-08-20 用户裁决 D6）

起草时本节的裁决是「不还原、降级成单个 text block」。**用户裁决推翻了它**：还原成 `server_tool_use` + `web_search_tool_result`。本节保留原有的三条约束——它们不是反对意见，而是「尽量」这个词的边界，实现必须在这些边界内工作而不是绕过它们。

1. **`web_search_result` 项我们造不出忠实的。** 该项需要 `url`、`title`、`encrypted_content`，而 `web_search_call` item 通篇只有一个 `query`。唯一带 `url`／`title` 的来源是后续 message 的 `annotations` 里的 `url_citation`——**没有摘要，没有 `encrypted_content`**，而且**可能整个是空数组**（本项目非流式样本即 `[]`，B7 样本则有）。
2. **citation 与 call 之间没有关联字段。** `url_citation` 挂在 message item 上，不挂在 `web_search_call` 上；一个响应里可以有多个 `web_search_call`（并发形态**未探针**，§12 P6）。拿 citation 去填某一个 `web_search_tool_result`，需要代理自己发明一条关联关系。
3. **`encrypted_content` 无论填什么都不真。** 省略、空串、占位串，三者都不是上游给的句柄。

**这三条推不出「不还原」，只推出「还原到哪一层」**，因为本规格的合成块**不会被回喂给 Anthropic 上游**：下一轮同样发往 Responses 腿，由 §5.4 摊平；若同一份历史被路由到 Anthropic 直连腿，由 `builtin:server-tool-capability` 摊平。那套机制 2026-08-20 已经建成并在产，所以「合成块要再造一套识别与剥离机制」这项成本**已经付过了**，不构成反对理由。

据此，「尽量」的落点是：**call 块忠实，result 块尽力且不编造**。

### 5.3 冻结的呈现形态

每个 Responses `web_search_call` item **必须**产生**一对** Anthropic blocks：一个 `server_tool_use`，紧随其后一个同 `tool_use_id` 的 `web_search_tool_result`。两者**必须**在同一条 assistant message 内、相邻。

**`server_tool_use` 块**：

| 字段 | 值 |
|---|---|
| `type` | `server_tool_use` |
| `name` | `web_search` |
| `id` | `srvtoolu_ws_<output_index>` |
| `input` | `{"query": <action.query，缺失时取 action.queries 以 ", " 连接，都没有则省略 input>}` |

- `id` **必须**由 `output_index` 派生，**不得**使用上游那个 416 字符的句柄。理由两条：本规格 §7 裁决不做 continuation，所以上游 id 没有任何消费者；而把 416 字符塞进面向客户端的 wire，既膨胀历史又把服务端引用暴露给客户端。参考项目把它塞进正文，本规格**不照抄**。
- `query` **必须**已 strip 首尾空白。上游拒收结尾带空白的 assistant 轮次，而 query 来自客户端与模型，可能带换行。

**`web_search_tool_result` 块**，`content` 按下表：

| 条件 | `content` |
|---|---|
| 本次响应中 `web_search_call` **恰好一个**，且后续 message 的 `annotations` 含 `url_citation` | 每条 citation 一项 `{"type":"web_search_result","url":<url>,"title":<title>}`，按出现顺序，按 `url` 去重 |
| 本次响应中 `web_search_call` **多于一个** | `{"type":"web_search_tool_result_error","error_code":"unavailable"}`，并记 `DEGRADE`（`web_search_results_unattributable`） |
| 无 `url_citation`，或 `status != "completed"` | `{"type":"web_search_tool_result_error","error_code":"unavailable"}`，并记 `DEGRADE`（`web_search_results_not_representable`） |

- error 形态**必须是裸对象**，`content` 直接就是 `{"type":"web_search_tool_result_error",...}`，**不得**包成单元素数组。依据是在产的摊平实现：`src/app/pipeline/subscribers/server_tools.py` 的 `_failure_of()` 只认 dict，包成数组会让 §5.4 的摊平静默产出 `[web_search results omitted]`，把一个「结果不可得」说成「什么都没有」。
- **`encrypted_content` 必须省略**，不得填空串、不得填占位串。省略是「我们没有这个句柄」，占位串是「这里有一个句柄」——后者是断言，且是假的。这一条使合成块不满足 Anthropic 对该项的完整 schema；这是**有意的**，代价由 §5.4 的摊平吸收，且这些块永不回喂 Anthropic 上游。
- **多于一个 call 时不做归因**：citation 与 call 无关联字段，猜一条关系比不给更糟。这一分支的正确性依赖「一个响应可以有多个 `web_search_call`」这一未探针形态（§12 P6），实现时必须按此保守分支执行。
- **无结果时用 error 形态而不是 `content: []`**：搜索确实执行了、结果确实进了模型上下文并体现在正文里，说「返回了零条结果」是与事实相反的断言；说「结果不可得」对客户端为真——代理确实拿不到那份清单。`error_code` 取 `unavailable`，**该取值是否在 Anthropic 该块的合法枚举内，实现前必须核对**（新增探针项 P12）。
- 搜索块**不得**设置 `stop_reason` 为 `tool_use`。它不是客户端要执行的工具调用，客户端无事可做。`stop_reason` 仍由是否存在真正的 `function_call` 决定。
- 这一对块与相邻的答案文本块**不得**合并，各占独立 block index。
- 每对块**必须**记一条 `DEGRADE` 性质的 `ConversionFact`，编码 `server_tool_partially_representable`，携带 `output_index`、`status`、结果条数与 `encrypted_content` 缺失的事实。**不得**记为已保真。
- `annotations` 中的 `url_citation` 在被用于填充 `content` 之后，**不得**再重复以 Anthropic `citations` / `web_search_result_location` 形式附加到文本块上——那需要伪造 `encrypted_index`。正文里上游本就已内联 markdown 引用（实测同一响应两种形式同时到达）。
- 响应体的 `tool_usage.web_search.num_requests` **必须**进入可观测 facts（日志与 footer），**不得**进入 Anthropic wire content。是否同时写入 Anthropic `usage.server_tool_use.web_search_requests` 见待裁决 D7。


### 5.4 这些块下一轮回到我们手里时

- 我们发给客户端的是**真正的 Anthropic server-tool 块**，客户端下一轮会原样回传。这条回路**必须**由已在产的摊平机制吸收，不得新建第二套：
  - 下一轮仍走 Responses 腿时，由本节下面那条规则摊平成文本；
  - 同一份历史被路由到 Anthropic 直连腿时，由 `builtin:server-tool-capability`（`src/app/pipeline/subscribers/server_tools.py`，2026-08-20 在产）摊平成文本。
- 摊平后的文本**必须**由**两条腿共用的同一份渲染实现**产出（§10）。同一事实不得在两条交付路径上各推导一遍；否则同一会话在两腿之间迁移时，历史里会出现两种文本形状。
- **不得**给合成块附加隐藏标记、私有字段或复用 reasoning carrier 来标注它的出身。区分「我们合成的」与「别处来的」没有消费者：两者的处置相同（都摊平），而加了标记就必须在请求侧识别并剥离，等于给自己造第二套 carrier。
- 历史里出现的 Anthropic `server_tool_use` / `*_tool_result` 块，无论来源是我们自己上一轮的合成、别的 provider、旧会话，还是同一份历史此前走过 Anthropic 直连腿，Responses 腿**必须**将其摊平成文本后继续转换，**不得** `REJECT` 整个请求。这是对 `src/app/protocols/anthropic_responses.py:409` 现有 `server_tool_not_supported` 的定点改动。
- 摊平**必须**同时作用于 `web_search` 与 `web_fetch` 两族——与 `builtin:server-tool-capability` 的剥离清单一致。其余族（`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_`）在本腿的处置不变。
- **必须注意的一处信息损失**：合成块被摊平后，`web_search_result` 的 `url`／`title` 进入文本，而 `encrypted_content` 本就不存在，所以摊平不丢任何我们曾经持有的东西。但模型在下一轮看到的是文本而不是结构化结果——这是本设计的固有代价，**不得**试图用 continuation 或隐藏标记规避（§7 已实测其收益为零）。

## 6. 面四：stream lifecycle

### 6.1 关联键：`output_index`，不是 `id`

**必须**按 `output_index` 关联同一个 `web_search_call` 的各个事件。**不得**用 `id`、`item_id` 或其任何派生值作为关联键、去重键或幂等键。

反例是本项目自己的实测，不是引用来的：一次流式响应里，**同一个 `web_search_call` 在五个事件中带了五个互不相同的 416 字符 id**——

| 事件 | `output_index` | id 前 10 字符 |
|---|---|---|
| `response.output_item.added` | 0 | `n40LI6g9pS` |
| `response.web_search_call.in_progress` | 0 | `t/N1eG6Isj` |
| `response.web_search_call.searching` | 0 | `/xxIRRwnFA` |
| `response.web_search_call.completed` | 0 | `/vJZ9TXvk9` |
| `response.output_item.done` | 0 | `B6uFl9rD6J` |

两次独立运行（探针 C2 与随后的 cassette 录制）在同一模型、同一天各自复现，两次都是每事件一个新 id。这直接推翻了参考项目记录的「`web_search_call` 的 id 在两事件间稳定（`distinctIds:1`）」，该结论**不得**再被引用。本项目 `CLAUDE.md` 记的 function_call id 不稳定，在 `web_search_call` 上同样成立。

配套要求：

- `src/app/routes/anthropic.py:228` 对 Copilot 上游把 `require_stable_item_id` 设为 `False` 的现有分流**必须**保持。本规格不改它，也不因 web search 而放宽 generic 上游的 strict 判定。
- `BlockIdentity.item_id` 对 `web_search_call` **只作诊断字段**，取值**必须**取自 `output_item.done` 上的权威快照，**不得**参与配对、索引分配或去重。

### 6.2 三个专有事件

`response.web_search_call.in_progress`、`.searching`、`.completed` 确实存在，各自只携带 `item_id`、`output_index`、`sequence_number`，**不带 `action`，不带任何内容增量**。

- 三者**必须**被识别为「已知的非语义 control metadata」，按 `spec.md` 既有矩阵记录 event type 与 provenance，**不得**进入 Anthropic content，**不得**落入 `UnsupportedResponsesEvent` 的默认分支。今天它们会落进去。
- 三者携带的 `item_id` **不得**被用于校验（见 §6.1）。定位所属 item **必须**只用 `output_index`。
- 三者**不得**触发任何 block 的开启、提交或关闭。

### 6.3 成块规则：在**后随文本块的完成边界**上成块

起草稿写的是「在 `web_search_call` 的 `done` 上一次性成块」。**该规则与 §5.3 的 content 判据互斥，已废止**：`url_citation` 只在后续 message 的 `content_part.done` 出现，**晚于** `web_search_call` 的 `done`；若在 `done` 上成块，§5.3 用 citation 填充 `content` 的那一分支永远走不到，且流式与非流式必然不等价。

> **2026-08-21 证据更正。** 本条原写「cassette 实测表明」，那句话过强：本项目两份 web-search cassette 的 `annotations` 都是空数组，**它们说明不了 citation 的时序**——空数组里没有可排序的东西。这条规则当时靠的是协议结构推断。现在它有了直接证据，但来源不是 cassette：既有服务 history 库里的真实上游根帧显示 Copilot 会发 `response.output_text.annotation.added`，且 `content_part.done` 与 `output_item.done` 各带一份完整的 `annotations` 数组，均晚于 `web_search_call` 的 `done`。取证见 [`../hosted-web-search/reports/260821-responses-websearch-citation-evidence.md`](../hosted-web-search/reports/260821-responses-websearch-citation-evidence.md)。**结论不变，依据换了。**

**冻结规则**：

- `response.output_item.added` 上的 `web_search_call` item **只有** `id`、`status`、`type` ——**没有 `action`**。查询内容只在 `done` 上出现（本项目实测，cassette 逐字可查）。
- 因此解码器**不得**按「`added` 开块 → delta 累积 → `done` 收口」的常规模型编写。这不是风格问题：`added` 时块里**无内容可填**，而这个 item 的 delta 事件根本不存在。
- `added` 到达时**必须**登记该 `output_index`（占住语义顺序与 source order，冻结 block index 的分配次序），但**不得**产生任何 `CompletedBlock`，**不得**向下游发出任何字节。
- `output_item.done` 上携带的 `item` 是该 call 的**唯一权威快照**（query、status）。此刻**必须**把它记入一个**待归因队列**，但**不得**成块，**不得**向下游发出任何字节。
- **成块发生在紧随其后的那个 message 文本块完成时**（`content_part.done`）。此刻 citations 已齐备。发射顺序**必须**是：该文本块对应的每个待归因 call 的 `server_tool_use` 与 `web_search_tool_result` 块，**然后**才是该文本块本身。**不得**反转。
- 选这个边界的理由，也是它必须被保留的理由：本项目是**块级交付**，文本块本就在 `content_part.done` 才完成并交付；把搜索对钉在同一个边界上，流式与非流式**必然等价**，且**不需要缓冲整个响应**——只推迟到它后面那个文本块的完成边界为止。
- **归因是局部规则**：只有当待归因队列中**恰好一个** call 时，才用该文本块的 `url_citation` 填充其 `content`；队列中多于一个时，该组**全部**落 §5.3 的 error 形态并各记一条 `DEGRADE`。**不得**依赖 `response.completed` 才知道的全局 call 总数——那会让流式与非流式再次分叉。队列在每次成块后**必须**清空。
- **兜底：一个 call 后面没有文本块时**（响应就此结束、或下一个 item 是 `function_call` 等非文本 item），待归因队列中的全部 call **必须**在其自然边界（`response.completed`，或该非文本 item 开始时）以 error 形态成块发出，**不得**丢失。
- **`done` 到达而该 `output_index` 从未 `added` 时，必须补登记并照常入队，不得失败也不得丢弃。** 依据是参考项目记录在案的真实回归：早先实现在 `done` 时若该 index 没开过就直接 return，结果整个搜索 item 静默消失，且没有产生任何 observation。本项目现有 parser 在这种情形下会以 `unknown_output_item` **显式失败**——比静默丢好，但对 web search 而言仍然是把一次成功的搜索变成整轮失败。容忍的成本为零，失败的代价是整轮。**这是设计裁决，本项目两次实测都带 `added`**（§12 P7）。
- `status` 不是 `completed` 时（`failed`、`incomplete`、`searching`，或未来新值）**必须**照常入队并成块，按 §5.3 反映状态。**不得**因状态非终态而丢弃该 item。
- `action` 缺失**必须**被容忍，按 §5.3 渲染为不带查询的形态。
- 非流式路径与流式路径**必须**对同一语义样本产出等价结果。非流式下同一规则退化为：按 output 顺序扫描，遇 `web_search_call` 入队，遇 message 时按同一局部归因规则出队成块。`spec.md` 的 non-stream／SSE 归一化等价要求在此适用。


## 7. 面五：History／continuation

### 7.1 实测结论

参考项目在真实上游做过五变体探针（2026-08-11，gpt-5.6-sol）：完整 item 原样回传 **200**；最小 `{type,id}` **200**；`{"type":"item_reference", id}` **404**；完整 item 但 `id` 改一个字符 **400**（超长错误，说明上游确实在解密该 id）；完全省略该 item **200**。

关键在于**答案**：变体 A（完整回传）、B（最小形态）、E（完全省略）三者的答案**完全相同**。回传 `web_search_call` **并没有把搜索结果带回上下文**——这个 item 从来只有 `action` 与 `id`，结果一直在 message 正文里。它的续接价值是 provenance 与顺序，**不是可恢复的结果数据**。

### 7.2 冻结裁决：不做 continuation

- 本规格**不引入**任何 Responses continuation 载体。搜索块以普通文本回到客户端，下一轮以普通文本回到我们手里，按普通文本转换（§5.4）。
- `web_search_call` 的 `id` **必须**在转换出 Anthropic wire 时丢弃，并记一条 `DEGRADE` fact（`server_tool_call_id_not_carried`）。**不得**为保留它而引入旁路载体、隐藏标记或复用 reasoning carrier。

理由，逐条对应可证的成本与收益：

- **收益**：仅 provenance 与顺序。而顺序已经由搜索块在 block 序列中的位置保住，provenance 已经由搜索块的文本 `[web_search] <query>` 保住。id 本身对模型不可读、对客户端不可用。
- **成本**：一套编解码、一套请求侧识别与剥离、一套版本管理；且 id 的**时效未测**（数分钟或数小时后是否仍可解密，无人知道），**跨模型回放只测过一次**，**多 `web_search_call` 并发时的行为未测**。
- **判别力问题**：「上游接受」不构成续接有效的证据——参考项目实测一个明显伪造的短 id 也会静默 200。所以任何以 200 为依据的收窄都站不住。

### 7.3 我方 History 记录

- 本项目自己的 History（`history-v3*.db` 一系）记录的是原始上游帧，`id` 天然在其中，**不需要**额外动作，也**不得**为本规格删改。
- 结构化 `ConversionFact`（§5.3、§7.2）**必须**进入 History、metrics 与 trace，按 `spec.md` 既有的 `DEGRADE` 语义。

## 8. 面六：错误处理

### 8.1 三种已知拒绝措辞

| # | 腿／触发 | HTTP | body |
|---|---|---|---|
| 1 | Anthropic Messages 腿（`/v1/messages` 与 `/v1/messages/count_tokens` **逐字相同**）声明了 server tool | 400 | `{"error":{"message":"The use of the web search tool is not supported.","code":"unsupported_value"}}` |
| 2 | `/responses` 腿收到 Anthropic 拼法 | 400 | `invalid_request_body`，`Invalid value: 'web_search_20250305'.` + 上游可选值清单 |
| 3 | `/responses` 腿收到未知子参数 | 400 | `invalid_request_body`，`Unknown parameter: 'tools[0].allowed_domains'.` |

三条均为本项目一手实测（2026-08-20）。同一条规则上游有两套 body，这正是判据**必须**读「我们自己发出的声明与路由」而不是「上游回来的措辞」的原因。

### 8.2 不引入反应式路径

- 本规格**不**在收到上述任何 400 后剥离并重试。这与 `../archived-2604-rewrite/tool-use.md:23` 的既有裁决一致，本规格不重开。
- 上游若仍返回上述任一 400，**必须**按 `spec.md` 既有 Error 契约归一为 `ApiError` 并映射为 Anthropic error envelope 透传给客户端。**不得**吞掉，**不得**静默降级为「去掉搜索再试一次」。理由：这三条 400 出现即意味着能力门（§9）判错了；静默重试会把判错藏起来，下一次仍然错，而且错得没有痕迹。

### 8.3 能力不可用时的行为

- 路由到 **Anthropic Messages 腿**时：`builtin:server-tool-capability` 继续剥离声明、清理悬空 `tool_choice`、摊平历史块。行为完全不变（§10）。
- 路由到 **Responses 腿但门未通过**时（功能开关关闭，或模型不被任何一条模式认领）：**必须**合成一个失败的搜索结果——`server_tool_use` 配对 `web_search_tool_result`，后者 `content` 为单个 `{"type":"web_search_tool_result_error","error_code":"unavailable"}` 对象——并输出 INFO 级日志，日志**必须**区分「功能未开启」与「模型未被认领」两种原因。**不得** `REJECT` 整个请求，也**不得**剥离声明后照发。

  > **2026-08-22 更正。** 本条起草时写的是「**必须**剥离 web search 声明、同步清理指向它的 `tool_choice`……理由：与 Anthropic 腿保持同一取舍——剥掉一个能力，好过整轮失败」。用户 2026-08-20 裁决「去除 drop 策略，drop 在这里行为远不如 mock_result」推翻了它，理由是 Claude Code 把 web search 发成独立子请求（`tools` 只有搜索一项，190/190 实测），剥掉它唯一的工具后请求**不会失败**——模型凭记忆作答，而客户端无条件把回复拼上 `Web search results for query:` 抬头。剥离在这条腿上产出的不是「少一个能力」，是**把记忆当搜索结果交付**。
- **例外且优先**：§3.4 的 `allowed_domains` / `blocked_domains` 非空时走 `REJECT`，该条优先于本节。它拒绝的原因不是能力缺失，而是语义反转：继续执行会把一条明确的收紧约束变成 no-op。
- **合成的前提是客户端腿读得懂它**（2026-08-30 补入）。本节规定的失败结果是一对 **Anthropic** content block，所以它**必须**只在客户端腿是 Anthropic Messages 时产出。客户端腿是别的协议时**不得**合成，**必须**让该拒绝按既有 Error 契约归一为客户端自己格式的 error envelope。

  > 这不是假想情形。一个 inbound 为 `/responses`、模型却只支持 `/v1/messages` 的请求（`claude-*` 即是）会被路由到 Anthropic 上游，其声明被翻译成 Anthropic 拼法，然后由 `builtin:server-tool-capability` 在那条腿上拒绝——于是本节的合成在一个 Responses 客户端上触发。交付侧按**客户端**腿选 framer，两种结局都是错的：流式在 200 已发出之后抛 `ValueError: no Responses item shape for block kind 'server_tool_use'` 撕流；非流式返回 200、日志记 `ok`、把一份 Anthropic message body 交给 Responses 客户端，全程没有任何一处说出这件事。两者均于 2026-08-30 实测复现。
  >
  > 「答复而非失败」的理由（§8.3 上文、Claude Code 会把 HTTP 错误当传输故障重试三次）本身就是**对某一个客户端**成立的，所以它推不出「对任何客户端都合成」。一个读不懂这份合成的客户端，从合成里得不到任何东西。

### 8.4 上游返回未请求的 `web_search_call`

`spec.md:136`（response 半段）与 `:181` 现规定「若 upstream 在未请求时返回这类 item，response conversion 显式失败」。本规格在 `web_search_call` 这一种 item 上**覆盖**该条：

- 上游返回 `web_search_call` 而本次请求并未声明 web search 时，**必须**按 §5.3 降级成文本块并记 `DEGRADE` fact（额外标注 `unsolicited`），**不得**失败。
- 理由：上游主动执行未请求的工具是上游行为变化，把它变成整轮失败对客户端毫无价值，且这个降级是**无损的**——即使我们请求了它，拿到的也只有一个 query。
- 覆盖范围严格限于 `web_search_call`。其余 server-tool item（任何 `*_call` / `*_result`）**继续** `server_tool_not_supported` 显式失败。对应待裁决 D3。

## 9. 面七：capability gate

### 9.1 目录回答不了这个问题

- `refs/available_models.json` 中所有模型 `capabilities.supports` 键的并集里**没有任何 web search 相关能力位**。目录里**不存在**可读的答案。
- **不得**读一个不存在的键。参考项目 `src/lib/codex-assembly.ts:70` 写着 `supportsWebSearch: supports?.web_search === true`，该标志恒为 `false`，是悬空代码，**不得**复制。
- `refs/available_models.json` 本身**已被实测证明过期**（`claude-sonnet-4.5` 已从上游目录消失，新增 `claude-opus-5`）。任何以它为依据的静态判定都必须假定它会漂。

### 9.2 `supported_endpoints` 是必要非充分

- `supported_endpoints` 含 `/responses` 或 `ws:/responses` 是**必要**条件。所有 `claude-*` 都不广告 `/responses`，这正是生产 400 的根因。
- 它**不充分**，而且比过去更不充分：实时目录里 `/responses` 集合现已包含**非 GPT 模型** `grok-4.5`、`grok-4.6`、`mai-code-1.1-flash`、`mai-code-1-flash-picker`，**全部未探针**。`web_search` 是 OpenAI Responses 的原生 builtin，非 OpenAI 血统的模型经 Copilot 的 `/responses` 兼容层转发时是否也真的执行它，没有任何证据。

### 9.0 功能总开关（2026-08-22 补入）

在本节其余所有条件**之前**还有一道：`model_translation.to_openai_responses.hosted_web_search`，**默认 `false`**（用户 2026-08-21 裁决）。关闭时这条腿不提供 hosted web search，声明一律按 §8.3 合成失败结果，§9.1～§9.3 的模型判定根本不会被求值。

关闭的理由是支持**不完整**，且缺的部分对客户端不可见：交给 Anthropic 客户端的是一行文本而非 §5.3 冻结的原生块对；上游确实返回的 `url_citation` 零处读取；`max_uses` 与域名清单都发不出去。把半成品设成每个请求的默认，是这条裁决要避免的事。

日志与 error code **必须**把「功能未开启」（`server_tool_disabled`）与「模型未被认领」（`server_tool_capability_unavailable`）分开——默认是关的，所以前者是两者中更可能的那个，运维必须分得清自己看的是哪一种。

**能力门只在 §1 那条 crossing 上求值**（2026-08-30 补入）。判据**必须**包含 inbound 格式，**不得**只读 target format：只读 target 的门会把直连 `/responses` 请求也判进来，而那类请求不在本规格范围内（§1 末段）。

> 这一条是被 GitHub issue #1 逼出来的，值得写下它是怎么错的。实现只判了 `target_format is OPENAI_RESPONSES`，旁边的注释却声称「直连 Responses 客户端会被放过」——作者以为翻译器发出的拼法和客户端自己写的拼法能分开，而两者是**同一个 tool object，逐字相同**，payload 里没有任何东西能回答「这是谁写的」。于是门在直连请求上击发，拒绝被答以 §8.3 的 Anthropic 块对，Responses framer 没有对应的 item 形状，流被撕断。
>
> 由此也界定了这条判据**证明得了什么**：它限定的是「哪一条 crossing 归这道门管」，**不是**「这个声明是不是本项目写的」。后者 payload 答不了，inbound 格式也答不了——一个 Anthropic inbound 完全可以自己带一个 Responses 形状的 `{"type":"web_search"}` 进来，翻译器原样保留，门照样判它。那种输入在 Anthropic 端点上的处置**不在**本规格范围内，未经裁决**不得**顺手改动。

### 9.3 冻结的保守判定（2026-08-20 用户裁决 D4：配置项手动维护）

用户要求先确认上游 `/models` 是否给得出信号。**已确认：给不出。** 2026-08-20 对实时目录做了全量重判（42 个模型、67,656 字节，原始件 `exp/260820-websearch-probe/raw/models-live.json`）：

- `capabilities.supports` 的键并集共 10 个，与过期的 `refs/available_models.json` **逐字相同**，一个没多：`adaptive_thinking`、`dimensions`、`max_thinking_budget`、`min_thinking_budget`、`parallel_tool_calls`、`reasoning_effort`、`streaming`、`structured_outputs`、`tool_calls`、`vision`。
- 递归任意深度、名字含 `search|tool|builtin|web` 的路径只有 `.capabilities.supports.parallel_tool_calls` 与 `.capabilities.supports.tool_calls`，都是普通 function calling。
- 对整个 67KB 做**值级**正则扫描 `search|web_|builtin|hosted`，**零命中**——所以也不存在藏在 `warning_message`／`policy` 文案里的信号。
- 已实测为真的 `gpt-5.5` 与 `gpt-5.6-sol`，在 `supports`、`type`、`limits`、`model_picker_category`、`preview`、`policy` 上**都无法**与其余广告 `/responses` 的模型分开；`reasoning_effort` 取值表连这两个真模型**彼此都不同**。`gpt-5.5` 与 `gpt-5.4`、`gpt-5.6-terra` 在目录里**逐字段无法区分**。

因此能力门**必须**同时满足以下全部条件才判定为通过：

1. 当前 attempt 的路由已确定为 Responses 腿；且
2. resolved model 的 `supported_endpoints` 含 `/responses` 或 `ws:/responses`；且
3. resolved model id 在**配置维护的允许清单**内。

配置键是 `model_providers.<name>.models_support_web_search`（用户 2026-08-20 裁决的键名）。取值为**正则表达式列表**，用 `fullmatch` 匹配上游 `model.id`（用户 2026-08-21 裁决「能力门采用版本清单，清单接受正则表达式」）。模式在启动时统一编译，不合法的模式带着条目原文与键名抛 `ValueError`。**默认值是一条** `gpt-[5-9]\.\d+.*`，覆盖 2026-08-20 实时目录里 `vendor == "OpenAI"` 且 `supported_endpoints` 含 `/responses` 的那七个（`gpt-5.3-codex`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.5`、`gpt-5.6-luna`、`gpt-5.6-sol`、`gpt-5.6-terra`），并自动纳入后继版本。

> **2026-08-22 更正。** 本节起草时写的是「配置键**名待定**……取值为模型 id 列表……**默认值**由目录派生：`vendor == "OpenAI"` 且……七个」，并说「取 `vendor` 而**不**取 `gpt-` 名字前缀」。三处都已被落地实现取代：键名不待定，取值是正则不是 id 列表，默认是一条模式不是七个字面量。**判据也反了**——实现取的正是名字，靠**点分小版本**排除 `gpt-5-mini`（它没有点分小版本，vendor 为 `Azure OpenAI`），而不是靠 `vendor` 字段。
>
> **一个必须写下来的后果**：条目是正则，所以写成裸模型 id 的条目**不等价于字面匹配**——`.` 是通配符，`gpt-5.5` 也会认领 `gpt-5x5`。要精确钉住一个 id 必须转义：`gpt-5\.5`。

- 每个 provider 的清单**只对它自己生效**，不得跨 provider 合并：键在 `model_providers.<name>` 之下，答案就是那个 provider 的。合并会让一个自身清单为空的 provider 继承别人的许可。
- **已知误判，必须记录而不是掩盖**：假阳性最可疑的是 `gpt-5.3-codex`（codex 专用，工具面不同），其次 `gpt-5.4-mini`／`gpt-5.6-luna`（lightweight 档）；假阴性是 `grok-4.5`／`grok-4.6`（xAI 自带搜索，是否透出未知）、`mai-code-*`、`gpt-5-mini`。
- **两类误判的代价不对称**，这决定了清单宁窄勿宽：假阳性是一次可见的 400，人能看到并改配置；假阴性是「用户以为搜了、其实没搜」的**静默降级**，没有任何人会发现。
- 判定失败时的行为见 §8.3，**不得**失败整个请求。
- 判定结果、判定依据（哪一条不满足）**必须**进入可观测 metadata。`spec.md:106` 已要求路由与拒绝原因进 metadata，本规格沿用同一通道。
- **不得**用模型名做清单之外的任何启发式推断，**不得**用 route override 伪造 capability。
- **不得**把 `billing.restricted_to` 当能力 oracle。已实测的两个真模型在该字段上恰好相同，但那是订阅档位，不是能力。

**另有一条目录之外的运行期信号，本规格不采用但记录在案**：向 `/responses` 发一个不认识的 builtin 工具类型时，400 的 message 会列出该端点当前接受的全部 builtin 工具名（B2／B9 各一次）。但**这份清单是按模型给的还是端点共用一份，本次无法区分**（只在 `gpt-5.5` 上见过）。要把它当判据，必须先在第二个模型上验证一次；在此之前它与手工配置是两条互斥的路，不得混用。


## 10. 与 `builtin:server-tool-capability` 的关系

`src/app/pipeline/subscribers/server_tools.py` 的订阅者今天在 `attempt.prepare` 上按 `context.target_format is WireFormat.ANTHROPIC_MESSAGES` 门控，只作用于 Anthropic 腿；其 docstring 已明确写下「Responses 腿需要自己的答案，而不是这一个」。

**裁决：订阅者不改。** 它的门控判据已经把 Responses 腿排除在外，本规格就是它 docstring 里说的那个「自己的答案」。具体分工：

| | Anthropic Messages 腿 | Responses 腿 |
|---|---|---|
| 声明 | 订阅者剥离 + 清理悬空 choice + INFO 日志（不变） | 本规格 §3 映射为 `{"type":"web_search"}`；能力门不通过时 §8.3 剥离 |
| 历史 server-tool blocks | 订阅者摊平成文本（不变） | **converter 摊平成文本**（§5.4；今天是 `REJECT`） |
| 上游返回的 server-tool item | 不适用（上游不会产） | 本规格 §5.3 降级成文本 |
| `web_fetch` | 订阅者剥离 + 摊平（不变） | 声明 `REJECT`（§13）；历史块摊平 |

三条硬性要求：

- **必须**把「rejected／degraded server-tool block → 文本」的渲染提取为**一份共享实现**，订阅者与 Responses converter 引用同一份。今天该逻辑（`_family`、`_call_subject`、`_describe_one`、`_failure_of`、`_render_results`）私有在订阅者模块内。分成两份的代价是同一会话在两条腿之间迁移时，历史里出现两种文本形状，而这种漂移不会有任何东西报错。
- **不得**因为 Responses 腿支持了 web search 就把 `web_search` 从订阅者的 `_REJECTED_TYPE_PREFIXES` 里删掉。那份清单描述的是 **Anthropic 腿上游的拒绝**，与 Responses 腿的能力无关。
- 订阅者与本规格的执行顺序不重叠（前者只在 target 为 Anthropic Messages 时运行，后者只在 Responses 腿），因此**不需要**新增 order 约束。`builtin:blank-text-blocks` 排在订阅者之后的既有顺序不受影响。

**已知缺口，本规格不覆盖但必须记账**：`/v1/messages/count_tokens` 腿带 server tool 时经实测同样 400（措辞与 messages 腿逐字相同），而该腿今天未接订阅者，400 后退到本地估算——客户端看不到失败，但 tokenization 校准停止学习。这是 count_tokens 的独立缺口（`260820-websearch-fix-v2-design.md` §8 的 m5），**不得**因为本规格落地而被当作已解决。

## 11. 对 `spec.md` 的定点覆盖清单

本规格只在以下四处覆盖 `spec.md`（行号按当前 `spec.md`，共 587 行），其余全部条款继续生效：

| `spec.md` 位置 | 原文要求 | 本规格 |
|---|---|---|
| `:136`（Server-tool no-revive 的 request 半段）、`:159`（请求矩阵「Anthropic 原生 server／typed tool → `REJECT`」） | web search 在 request capability gate 显式拒绝 | 仅 `web_search_*` 族、仅 Responses 腿、仅能力门通过时改为映射（§3）。其余 typed／server tool 的 `REJECT` 不变 |
| `:136`（response 半段「若 upstream 在未请求时返回这类 item，response conversion 显式失败」）、`:181`（响应矩阵「server-tool call／result → `REJECT`」）、`:261`（「任意 server-tool call／result 执行 no-revive 并显式失败」）、`:326`（「server-tool call／result 不构成可提交 block」） | no-revive；上游返回即显式失败，且不构成可提交 block | 仅 `web_search_call` 改为**合成一对 Anthropic 原生 server-tool block**（`server_tool_use` + `web_search_tool_result`）并按块级交付提交（§5、§6.3、§8.4） |
| `:8`（「不得恢复 Anthropic 原生 server-tool 编排」）、`:537`（「server-tool no-revive 已冻结」） | no-revive 已冻结 | **本规格在响应侧定点覆盖它**：2026-08-20 用户裁决 D6 要求「尽量还原成原生块」，故代理会合成 `server_tool_use` + `web_search_tool_result`。仍然不变的是：代理**不执行**搜索（执行者是上游）、**不合成服务端签名结果**（`encrypted_content` 一律省略而非伪造）、**不在 Anthropic 直连腿恢复该编排** |
| 请求侧历史 server-tool block 的 `REJECT`（`src/app/protocols/anthropic_responses.py:409` 实现，`spec.md` 未单列条款） | 历史 `server_tool_use` / `*_tool_result` 一律拒绝 | Responses 腿改为摊平成文本（§5.4） |

`spec.md:582` 的 M4 处置写着「任何白名单必须另行取得用户裁决」——本规格就是那份裁决所要求的载体。用户 2026-08-20 的三批裁决已定案 D1／D4／D6，其余裁决点集中在 §14。


## 12. 证据权重逐条标注

### 有实测支撑，可直接据此实现

| 条款 | 依据 | 权重 |
|---|---|---|
| §3.2 `{"type":"web_search"}` 被接受 | B1 + C1 + cassette，gpt-5.5 | 强，跨仓库跨日期复现 |
| §3.1 Anthropic 拼法被拒 | B2，错误明确点名该值 | 强 |
| §3.3 `user_location` 可写并逐字回显 | B3 | 强，回显即证明 |
| §3.4 三个字段写入即 400 | B4／B5／B6，三条独立 | 强 |
| §4 `tool_choice:{"type":"web_search"}` 被接受并真的强制搜索 | B7，回显归一化 + `num_requests:1` + output 里确有 item | 强 |
| §5.1 item 键恰为四个、无 `encrypted_content` | 本项目 C1 + B7 + cassette，加参考项目两次 | 强，多仓库多日期独立复现 |
| §5.2 `include` 被静默丢弃（拿不到 sources） | B8，200 + 回显 `null` | 强（就这一个取值而言） |
| §6.1 同一 item 每事件一个新 id | C2 + cassette 两次独立运行 | 强到必须据此设计 |
| §6.2 三个专有事件存在且无内容增量 | C2 + cassette 两次 | 强 |
| §6.3 `added` 上无 `action`、query 只在 `done` 出现 | C2 + cassette 逐字 | 强 |
| §7.1 五变体续接结果与「回传不恢复上下文」 | 参考项目真 GHC 探针，每变体一次 | 一手，单模型单账号，足以支撑不做 continuation |
| §8.1 三种拒绝措辞 | A1／B2／B4，本项目一手 | 强 |
| §9.1 目录无 web search 能力位、目录已过期 | 实时 `/models` 一次 + 键并集 | 强 |
| §9.2 `/responses` 集合已含非 GPT 模型 | 实时 `/models` 一次 | 强（新增模型能否搜索：未测） |
| §5.3 `annotations` 会真的填 `url_citation` | B7 有、C1 无，各一次 | 中等偏强：足以证明载体存在并说明形态；不足以推出频率。消费者必须容忍空数组 |

### 属设计裁决，实测只提供约束不提供答案

| 条款 | 裁决内容 | 论证落点 |
|---|---|---|
| §3.3 | `user_location` 只透传五个已知键 | 上游对未知子参数是 400 不是忽略，透传未知键会打挂整轮 |
| §3.4 | 域名限制 → `REJECT`；`max_uses` → `DEGRADE` | 语义反转与成本上界的区别；见 D1／D2 |
| §3.5 | 多重声明去重 | 上游行为未探针，去重是保守分支 |
| §5.2 | 不还原为 `server_tool_use` + `web_search_tool_result` | 三条理由，均不依赖上游校验 |
| §5.3 | 降级文本形态与共享渲染 | 两条腿文本形状必须一致 |
| §5.3 | `id` 不进正文 | 明确不照抄参考项目 |
| §6.3 | `done` 无 `added` 时补登记而非失败 | 参考项目记录在案的静默丢失回归；容忍成本为零 |
| §7.2 | 不做 continuation | 收益仅 provenance，且已由文本保住；成本与未知项列在 §7.2 |
| §8.2 | 不引入反应式路径 | 沿用既有裁决；静默重试会藏起能力门的判错 |
| §8.4 | 未请求的 `web_search_call` 降级而非失败 | 降级无损；见 D3 |
| §9.3 | `gpt-5.` 前缀清单 | 唯一两个实测模型都在其下；见 D4 |

### 仍需探针（实现前或实现后按标注处置）

| # | 探针项 | 影响 | 时机 |
|---|---|---|---|
| P1 | `tool_choice: "required"`（Anthropic `any`）与 hosted builtin 并存 | §4 该行 | 实现前，成本低 |
| P2 | 同一请求两条 `{"type":"web_search"}` | §3.5 去重是否必要 | 实现前，成本低 |
| P3 | `user_location` 部分子键缺失 / 带未知子键 | §3.3 透传边界 | 实现前，成本低 |
| P4 | 工具对象里写 `name` 是否 400 | §3.2 「不写」是否保守过头 | 实现前，成本低 |
| P5 | `gpt-5.3-codex`、`gpt-5-mini`、`gpt-5.4*`、`gpt-5.6-*`、`grok-4.5`、`grok-4.6`、`mai-code-1.1-flash` 的 web search 行为 | §9.3 清单的松紧 | 可后补；未探针前按 §9.3 默认值执行 |
| P6 | 同一响应内多个 `web_search_call` 的 `output_index` 与 id 行为 | §5.2 关联论证、§6.1 | 可后补 |
| P7 | 是否真的存在「`done` 无 `added`」形态 | §6.3 的防御性分支 | 可后补；容忍成本为零，不阻塞 |
| P8 | `status: searching / failed / incomplete` 的真实形态 | §5.3 状态文本 | 可后补 |
| P9 | ~~流式带 `url_citation` 时是否发 `response.output_text.annotation.added`~~ | §6.2 事件清单是否完整 | **已结案 2026-08-21：发。** 且 `content_part.done` 与 `output_item.done` 各另带一份完整 `annotations` 数组，所以消费者有三个可选取点。证据来自 history 库里的真实上游根帧，非本项目 cassette（本项目两份 cassette 的 `annotations` 皆空）。见 [`../hosted-web-search/reports/260821-responses-websearch-citation-evidence.md`](../hosted-web-search/reports/260821-responses-websearch-citation-evidence.md) |
| P10 | 引用是否**恒**同时以内联 markdown 与结构化 `annotations` 两种形式出现 | 决定 D5 | 实现前。**「恒」仍未证**；已知 `exp/260820-websearch-probe/raw/B7-*.txt` 一份样本里两种形式确实同时到达，这只证明可以共存，不证明必然 |
| P11 | `{"type":"web_search_preview"}` 直发是否 200（别名推断未验证） | 无直接影响，用于确认上游归一化 | **优先级已升高 2026-08-21**：上游自己的 400 枚举把 `web_search_preview` / `web_search_preview_2025_03_11` 列为支持值而**未列**裸 `web_search`，且三份第三方实现都发前者。本项目仍在发裸 `web_search`（实测 gpt-5.5／gpt-5.6-sol 返 200）。改用广告值需重录两份 cassette（digest 覆盖整个请求体），**重录即探针** |

### cassette 的现状与限定

`tests/cassettes/responses_web_search_nonstream.json` 与 `responses_web_search_stream.json` 是真实上游存证，走仓库既定 `RecordingTransport` 录制（允许清单响应头、按字段名深度清洗、chunk 边界保留、`authenticated: true`）。**它们目前没有任何测试在回放**，且请求 shape 摘要算的是手写的 Responses body——产品链今天造不出这个请求。本规格落地后，**必须**把该场景挪进 `tests/integration/recorded/record_cassette.py` 的 `SCENARIOS`，用产品链重录，届时 shape 才对得上。直接拿现有两份去回放会撞 `RequestShapeChanged`。

## 13. 不做什么

以下均**不在**本规格范围，且**不得**借本规格的实现顺带引入：

- **`web_fetch`**：`/responses` 腿实测 400（`Invalid value: 'web_fetch'`），与 Anthropic 腿的 `rejected tool(s): web_fetch` 是**第三种措辞**。声明继续 `REJECT`，历史块按 §5.4 摊平。
- **`code_execution`**：任何腿都从未探针。声明继续 `REJECT`。
- **上游枚举里其余 builtin**：`tool_search`、`shell`、`apply_patch`、`programmatic_tool_calling`、`namespace`、`code_interpreter`、`file_search`、`image_generation`、`mcp`、`custom`、`computer`、`computer_use_preview`。全部未探针，全部继续 `REJECT`。
- **`include` 相关一切**：实测被 200 静默丢弃，任何指望它的设计都会静默失败。
- **`search_context_size` / `search_content_types` / `return_token_budget`**：只见过回显，未试过写；Anthropic 侧无对应语义。
- **反应式 400 剥离重试**。
- **Responses continuation 载体**（§7.2）。
- **`/v1/messages/count_tokens` 腿的 server tool 支持**（§10 已记为已知缺口）。
- **`/v1/messages` 直连 Anthropic 腿的任何行为改变**：`builtin:server-tool-capability` 原封不动。
- **Anthropic 客户端 → Anthropic 上游的原生 server-tool 编排**：`spec.md:8` 与 `:537` 的冻结不变，代理仍不执行搜索、不合成签名结果、不合成 Anthropic 原生 server block。
- **客户端执行型 typed tool**（`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_`）在 Responses 腿的处置：本规格不动，维持现状。参考项目把这十个前缀一并剥掉是过度剥离，**不得**照抄。

## 14. 待用户裁决

| # | 裁决点 | 选项 | 我的偏好与理由 |
|---|---|---|---|
| D1 | ~~声明带非空 `allowed_domains` / `blocked_domains` 时~~ | — | **已裁决（2026-08-20，用户）：做成可配置。** 默认 `error` 大声报错，可选 `drop_unsupported_fields` 与 `drop_web_search`。规范文本见 §3.4。**2026-08-24 用户修订第三取值**：`drop_web_search`（整条剥离）→ `empty_result`（返回空的有效结构），理由见 §3.4。**默认值仍待裁决**——实现是 `drop_fields`，本表与 §3.4 是 `error`，见文档状态第 4 条 |
| D2 | 声明带 `max_uses` 时 | (a) 同 D1 `REJECT`；(b) 剥离 + `DEGRADE` | **(b)**。它是成本上界不是语义约束，放开的代价是费用与延迟，且上游回报 `num_requests` 事后可观测。为一个成本上界拒绝整轮对话，代价明显大于收益 |
| D3 | 上游返回**未请求**的 `web_search_call` | (a) 按 §5.3 降级成文本；(b) 保持 `spec.md:136`／`:181`／`:261` 的显式失败 | **(a)**。降级是无损的（即使请求了也只拿到 query），把上游的行为变化变成整轮失败对客户端没有价值。但它确实覆盖了一条冻结条款，需要用户点头 |
| D4 | ~~能力门清单的形态~~ | — | **已裁决（2026-08-20，用户）：配置项手动维护。** 用户要求先确认上游 `/models` 是否给得出信号；已对实时目录全量重判，**确认没有**，故落到配置项。规范文本见 §9.3。键名仍待与人写 `config.example.yaml` 的词汇对齐 |
| D5 | ~~后续 message 的 `url_citation` annotations 是否丢弃~~ | — | **已被 D6 推翻。** 新 §5.3 把 citations 用作 `web_search_tool_result.content` 的**唯一**数据来源，因而不再存在「丢弃与否」的选项。仍然成立的是：**不得**再以 Anthropic `citations` / `web_search_result_location` 形式重复附加到文本块（需伪造 `encrypted_index`）。原挂钩的探针 P10 目标随之改变，见 §13 |
| D6 | ~~response presentation 的整体形态~~ | — | **已裁决（2026-08-20，用户）：尽量还原成原生块。** 起草稿偏好 (a) 降级成单个 text block，用户裁决取 (b) 合成 `server_tool_use` + `web_search_tool_result`。§5.2 保留原三条论证，但改述为「尽量」的边界而非反对理由；「合成块要再造识别与剥离机制」这条成本因 `builtin:server-tool-capability` 已在产而不再成立 |
| D7 | `tool_usage.web_search.num_requests` 是否写入 Anthropic `usage.server_tool_use.web_search_requests` | (a) 只进可观测 facts；(b) 同时写入 wire usage | 倾向 **(b)**：Anthropic 该字段与上游计数是 1:1 语义对应，客户端的用量展示能直接受益。但它需要对 `spec.md` 的 Usage 契约做一处增补，属独立小裁决，不阻塞本规格其余部分 |

## 15. 相关文档

- 行为 oracle 母体：[spec.md](spec.md)（本规格的定点覆盖见 §11）
- 上游实测一手报告：[`../hosted-web-search/reports/260820-websearch-upstream-probe.md`](../hosted-web-search/reports/260820-websearch-upstream-probe.md)
- 合成与七面现状：[`../hosted-web-search/reports/260820-websearch-fix-v2-design.md`](../hosted-web-search/reports/260820-websearch-fix-v2-design.md) §10、§11
- 参考项目做法与不可照搬项：[`../hosted-web-search/reports/260820-websearch-on-responses-leg.md`](../hosted-web-search/reports/260820-websearch-on-responses-leg.md)
- 开启本规格的冻结裁决：[`reports/260806-arbitrate-server-tool-contract.md`](reports/260806-arbitrate-server-tool-contract.md)
- 当前已实现边界：[`../archived-2604-rewrite/tool-use.md`](../archived-2604-rewrite/tool-use.md)、[`../archived-2604-rewrite/anthropic-compat.md`](../archived-2604-rewrite/anthropic-compat.md)、[`../archived-2604-rewrite/hooks-system.md`](../archived-2604-rewrite/hooks-system.md)
