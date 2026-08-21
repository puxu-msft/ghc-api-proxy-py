# GitHub Copilot 上游「输入超出上下文窗口」的 400 响应实例

调查日期：2026-08-21
调查范围：**只读**本机已有历史数据，未向上游发送任何请求。
主要数据源：`~/.local/share/copilot-api/history-v3*.db`（现网 `copilot-api-js` 服务的历史库，8 个文件，145,781 个 operation，覆盖 2026-07-17 09:37 ~ 2026-08-19 19:39）。

---

## 0. 结论速览

**找到了，共 48 例，且形态不唯一——有两种完全不同的表达，取决于走哪条上游腿。**

| | Anthropic 腿（`resolved_model=claude-*`） | Responses 腿（`resolved_model=gpt-*`） |
|---|---|---|
| 实例数 | 27 | 21 |
| HTTP 状态码 | **400** | **400** |
| `Content-Type` | `application/json` | **`text/plain; charset=utf-8`** |
| `error.code` | **`model_max_prompt_tokens_exceeded`** | **`invalid_request_body`** |
| `error.type` | **`invalid_request_error`** | **不存在该字段** |
| 顶层 `type` | `"error"` | 不存在 |
| 顶层 `request_id` | 有（`req_011C...`） | 不存在 |
| body 末尾换行 | 无 | **有 `\n`** |
| 消息里带数字 | 有（当前 / 上限） | **无任何数字** |
| 本项目 `limits.py` 能解析吗 | 能（第 2 条正则） | **不能** |

证据等级：**录制/实测**（history 库原文，逐字）。

**最要紧的一条**：Responses 腿的 `error.code` 是 `invalid_request_body`，与「参数写错」「id 前缀不对」「`max_output_tokens` 太小」这些普通 400 **完全同码**。这条腿上 `code` 没有任何区分力，只能匹配 message 文本。

**第二要紧的一条**：归档里存着一次同伴调查的结论——「没有任何一条当前 2 条正则漏掉的真实 token-limit body」。**该结论已被本次调查证伪**（Responses 腿的 21 例正是漏掉的那种）。它当时多半是对的，因为那批语料全部早于 2026-07-18，而 Responses 腿的上下文超限最早出现在 2026-08-06。详见 §7.1。

---

## 1. 实例原文（逐字）

### 1.1 Anthropic 腿（`POST /v1/messages` 上游腿）

**实例 A**：`history-v3-260807.db` / operation `req_1784404326995_700` / 2026-07-18 19:52:06 / 请求模型 `claude-opus-4-8` / 解析后 `claude-opus-4.8`

HTTP 状态码：`400`

响应 body（逐字，含上游自己的 `>` 转义）：

```json
{"error":{"code":"model_max_prompt_tokens_exceeded","message":"prompt is too long: 1001284 tokens > 1000000 maximum","type":"invalid_request_error"},"request_id":"req_011CdA784vkb8RKW4Qdyg2ci","type":"error"}
```

`>` 被转义成 `>` **是线上事实而非 JS 侧序列化产物**：同类实例记录的 `content-length: 213`，而带 `>` 的字符串长度正是 213（写成字面 `>` 只有 208）。

**实例 B**（带完整响应头，2026-08-08，`claude-opus-5`）：`history-v3-260809.db` / `req_1786221961723_387`

```json
{"error":{"code":"model_max_prompt_tokens_exceeded","message":"prompt is too long: 1051542 tokens > 1000000 maximum","type":"invalid_request_error"},"request_id":"req_011CdqwDkJy9YDgyzVF2fixv","type":"error"}
```

响应头（`kind: response.headers` 诊断事件原文）：

```json
{
  "content-length": "213",
  "content-security-policy": "default-src 'none'; sandbox",
  "content-type": "application/json",
  "copilot-edits-session": "1786221962.89dc933a4112c1ba81b1fa86c48029bd333fb75700fe1137fc8fa5651471ee45",
  "date": "Sat, 08 Aug 2026 20:46:03 GMT",
  "strict-transport-security": "max-age=31536000",
  "x-copilot-api-exp-assignment-context": "e4hcf520:1109203;61623843:1255491;permission_prompt_treatment:1294978;ccr_dau_aa_control:1281152;",
  "x-copilot-service-request-id": "2687202d-0301-4d2b-90ec-ec377cbf839a",
  "x-github-backend": "Kubernetes",
  "x-github-copilot-request-te": "true",
  "x-github-edge-region": "iad",
  "x-github-request-id": "D215:1D81DD:200A44A:29601E4:6A779585",
  "x-request-id": "7f7bb33f-ad52-4b49-8a64-5340a02c0965"
}
```

注意：**没有 `x-ratelimit-*`、没有 `retry-after`**，也没有任何声明模型窗口大小的头。窗口大小只出现在 message 文本里。

### 1.2 Responses 腿（`POST /responses` 上游腿）

**实例 C**：`history-v3-260809.db` / operation `req_1786211212875_94` / 2026-08-08 17:46:52 / 请求模型 `claude-opus-5` / 解析后 `gpt-5.6-sol`

HTTP 状态码：`400`

响应 body（逐字，**末尾有换行**）：

```
{"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again.","code":"invalid_request_body"}}
```

即 Python 字面量：

```python
'{"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again.","code":"invalid_request_body"}}\n'
```

长度 147，与响应头里的 `content-length: 147` 一致——**换行在线上，不是记录时加的**。

响应头（原文）：

```json
{
  "content-length": "147",
  "content-security-policy": "default-src 'none'; sandbox",
  "content-type": "text/plain; charset=utf-8",
  "copilot-edits-session": "1786211213.68d77b8e717191f1a4cb6ce9e0dc4ad0634a7cb532359f7df7799d9ce48ca60b",
  "date": "Sat, 08 Aug 2026 17:46:59 GMT",
  "strict-transport-security": "max-age=31536000",
  "x-content-type-options": "nosniff",
  "x-copilot-api-exp-assignment-context": "5133j383:1109202;61623843:1255491;permission_prompt_treatment:1294978;ccr_dau_aa_control:1281152;",
  "x-copilot-service-request-id": "89bbb700-6570-4b04-81d2-2dfe81a77478",
  "x-github-backend": "Kubernetes",
  "x-github-copilot-request-te": "true",
  "x-github-edge-region": "iad",
  "x-github-request-id": "90F0:A9D3E:FE21EC:15F45B9:6A776B8B",
  "x-request-id": "203861ec-aa44-45ff-9365-f4c62006027b"
}
```

**`content-type: text/plain; charset=utf-8`**——body 是 JSON，但上游不声明它是 JSON。这条腿上对 `Content-Type` 做判断会踩空。

**这条 body 里没有任何数字**：既不告诉你当前多少 token，也不告诉你上限多少。任何依赖「从 message 里抽出 (current, limit)」的机制（本项目的 `PromptLimitRegistry`、`copilot-api-js` 的 auto-truncate）在这条腿上一律拿不到数。

---

## 2. 形态是否唯一

**不唯一，至少两种；再加一种来自旁证的第三种。**

对 48 例做字段形态归并（脚本 `p6_occurrences.py`），只得到 2 个形态，没有第三个变体：

```
27x {"error.code": "model_max_prompt_tokens_exceeded", "error.type": "invalid_request_error",
     "error_keys": ["code","message","type"], "top.type": "error",
     "top_level_keys": ["error","request_id","type"]}
21x {"error.code": "invalid_request_body", "error.type": null,
     "error_keys": ["code","message"], "top.type": null,
     "top_level_keys": ["error"]}
```

### 2.1 跨模型 / 跨时间 / 跨账户

- **Anthropic 腿**：观察到 `claude-opus-4.8`、`claude-sonnet-5`、`claude-opus-5` 三个模型，时间跨 2026-07-18 ~ 2026-08-08（另有一条 2026-07-14 的二手引用实例，见 §7.1，形态一致），**形态完全一致**，`limit` 一律是 `1000000`（1M）。`current` 从 1000292 到 1299744 不等。
- **Responses 腿**：观察到 `gpt-5.6-terra`、`gpt-5.6-sol` 两个模型，时间跨 2026-08-06 ~ 2026-08-08，**形态完全一致**。
- **账户类型**：history 库不记录账户类型/plan，本次**无法区分**。已知本机 `~/.local/share/copilot-api/` 下有两个 token 文件（`github_token`、`github_token_puxu_microsoft`），说明存在两个账户，但历史库没有把它们和 operation 关联起来，**未查清**。

### 2.2 第三种表达（旁证，不是本机录制）

`/home/xp/src/refs/vscode-copilot-chat/test/inline/inlineEditCode.stest.ts:144`（提交 `7e74b6541`，2025-12-05）里存有一段**官方客户端录下来的真实响应**（注释形式，带 `serverRequestId`，是 GitHub 请求 id 的形状）：

```
Request Failed: 400 {"error":{"message":"prompt token count of 13613 exceeds the limit of 12288","code":"model_max_prompt_tokens_exceeded"}}\n
```

这是**第三种**形态：OpenAI 措辞的 message + `code=model_max_prompt_tokens_exceeded`，**无 `error.type`**，**无 `request_id`**，末尾有 `\n`。看限额 12288 应当是老的 `/chat/completions` 腿上的小模型。

证据等级：**旁证（但属于第三方录制的真实响应，不是手写 fixture）**。本机 history 库里对这条措辞（`prompt token count of ... exceeds the limit of ...`）**零命中**——覆盖 145,781 个 operation。

**推测（显式标注为推测，不得作为结论）**：Copilot 的 `/chat/completions` 腿沿用 Anthropic 腿的 `code`（`model_max_prompt_tokens_exceeded`）但用 OpenAI 的 message 措辞；而 `/responses` 腿是新写的一层，换成了 `invalid_request_body` + 无数字的通用措辞。这个推测没有本机录制支持。

---

## 3. 和其他 400 怎么区分

把同一批库里**所有**非成功 operation 的 4xx body 全部抓出来做形态归并（脚本 `p5_all_4xx.py`，共 48 个不同形态、74 次出现），得到对照组：

### 3.1 Responses 腿（`gpt-*`）上出现过的 400

| body | `error.code` |
|---|---|
| `Your input exceeds the context window of this model. Please adjust your input and try again.` | `invalid_request_body` |
| `Invalid 'input[1].id': 'call_jCWUMZ57P3JSaKR5wZBhrO8Z'. Expected an ID that begins with 'fc'.` | `invalid_request_body` |
| `Invalid 'max_output_tokens': integer below minimum value. Expected a value >= 16, but got 8 instead.` | `invalid_request_body` |

**结论：这条腿上 `error.code` 没有区分力，三种毫不相干的 400 用同一个 `code`。只能靠 message 文本。** 证据等级：**录制/实测**。

（同腿的非 400：`408 user_request_timeout`、`422 cyber_policy`——这两个 `code` 是有区分力的，但它们不是 400。）

### 3.2 Anthropic 腿（`claude-*`）上出现过的 400

| body | `error.code` | `error.type` |
|---|---|---|
| `prompt is too long: N tokens > M maximum` | **`model_max_prompt_tokens_exceeded`** | `invalid_request_error` |
| `Tool 'search.web' not found in provided tools` | **无 code 字段** | `invalid_request_error` |
| `This model does not support assistant message prefill. The conversation must end with a user message.` | **无 code 字段** | `invalid_request_error` |
| `messages: at least one message is required` | **无 code 字段** | `invalid_request_error` |
| `Tool 't' cannot have both defer_loading=true and cache_control set. Tools with defer_loading cannot use prompt caching.` | **无 code 字段** | `invalid_request_error` |

**结论：这条腿上 `error.code == "model_max_prompt_tokens_exceeded"` 是可靠的判据。** 其余 400 连 `code` 字段都不带（顶层字段顺序也不同：限额错误是 `{"error":…,"request_id":…,"type":"error"}`，其余是 `{"type":"error","error":…,"request_id":…}`，但字段顺序不该当判据）。证据等级：**录制/实测**。

补充两条本次未直接观察、来自归档里同伴调查记录的 Anthropic 腿 400 措辞（证据等级：**二手引用**，见 §7.1）：`thinking blocks cannot be modified`、`Unexpected role "system"`。它们同样不是 token-limit，也不影响上面的判据。

### 3.3 用户提到的那两个 400

`messages: text content blocks must be non-empty` 和 `The use of the web search tool is not supported.` **在本次扫描的 history 库里零命中**——它们是本项目 Python 代理踩到的，而本项目的 `rejection_capture` 落盘目录 `~/.local/share/ghc-api-proxy/rejected/` **不存在**（从未触发过写盘，或产物已被清理）。本项目自己的 `~/.local/share/ghc-api-proxy/history.db` 有 8966 条记录（558 条 `failed`），但 `error_message` 列**全为 NULL**，不存任何上游 body。

据 3.2 的样本推断，`The use of the web search tool is not supported.` 属于 Anthropic 腿「无 code 字段」那一类（同族的 `Tool 'search.web' not found in provided tools` 就是无 code 的）——**这是推测，本次未拿到该 body 原文**。

### 3.4 建议的判据（本节是建议，不是既定事实）

按可靠性排序：

1. **Anthropic 腿**：`error.code == "model_max_prompt_tokens_exceeded"`（强判据，实测支持）。
2. **Responses 腿**：`error.code` 无用；必须匹配 message。当前观测到的唯一措辞是 `Your input exceeds the context window of this model.`——建议匹配 `exceeds the context window`（不区分大小写），不要匹配整句，因为末句 `Please adjust your input and try again.` 是通用尾巴。
3. 兜底：`model_max_prompt_tokens_exceeded` 这个 `code` 在 vscode-copilot-chat 的录制里也出现在 OpenAI 措辞的 body 上，所以 **`code` 匹配应当先于 message 匹配**，且不应假定 `code` 出现就一定有 `error.type`。

---

## 4. 本项目 `limits.py` 的现状差距

`src/app/tokenization/limits.py:10-13` 两条正则：

```python
re.compile(r"prompt token count of\s+(\d+)\s+exceeds the limit of\s+(\d+)", re.I),
re.compile(r"prompt is too long:\s*(\d+)\s+tokens\s*>\s*(\d+)\s+maximum", re.I),
```

对照实测：

- 第 2 条：**命中** Anthropic 腿的 27 例。注意 body 里是 `>`，但 `json.loads` 解出来就是字面 `>`，而 `_error_message()` 正是先 `json.loads` 再取 `error.message`，所以能匹配。**（代码事实 + 录制实测）**
- 第 1 条：本机 145,781 个 operation **零命中**。它对应的是 vscode-copilot-chat 里那条 2025-12 的旧录制（`/chat/completions` 腿）。留着无害，但它不是当前两条腿的形态。
- **两条都不命中 Responses 腿的 21 例**。而且即使加一条正则也抽不出数字——那条 body 里根本没有数字。`PromptLimitRegistry.record()` 要求 `current > limit > 0`，Responses 腿的上下文超限**在结构上就无法进入这个 registry**。这是一个设计层面的缺口，不是正则缺一条的问题。

**实测验证**（直接把三条真实 body 喂给生产模块 `app.tokenization.limits.parse_prompt_limit_error`，只读调用，未修改任何代码）：

```
anthropic-leg (recorded)                   -> (1051542, 1000000)
responses-leg (recorded)                   -> None
chat-completions-leg (vscode fixture)      -> (13613, 12288)
```

即：现役的两条正则，各自只覆盖两条腿中的一条，而当前主产品路径（Responses 腿）恰好是没覆盖的那条。

**旁证交叉验证**：`copilot-api-js` 自己也踩了同一个坑。它对 Anthropic 腿那条错误分类成 `type: "token_limit"` 并抽出 `tokenLimit: 1000000, tokenCurrent: 1051542`；对 Responses 腿那条分类成 **`type: "bad_request"`**，没有任何 token 数——这是 history 库里 `kind: upstream_error` 诊断事件的原文，等于它的解析器**自己承认没认出来**。它的 `docs/todo/deferred-backlog.md:471` 也记着这个已知缺口。

**已知读反陷阱已核实**：`copilot-api-js` 里的 `context_length_exceeded`（`src/lib/error/forward.ts:161`）确实是**它合成给下游的**（`formatTokenLimitErrorOpenAI`），不是上游读到的。本机 history 库里 `context_length_exceeded` 作为上游 body 字段**零命中**。

---

## 5. 两条腿是否一致

**不一致，差别是结构性的，不是措辞差别。** 见 §0 表格。三个最容易踩的差异：

1. `error.type` 在 Responses 腿**不存在**。写 `body["error"]["type"] == "invalid_request_error"` 会 KeyError 或恒假。
2. `Content-Type` 在 Responses 腿是 `text/plain; charset=utf-8`，body 却是 JSON。按 content-type 决定要不要 parse 会漏掉。
3. Responses 腿的 body **末尾有 `\n`**，Anthropic 腿没有。做整串相等比较会失手。

补一句非对称观察：本机 47 例里 `request_id` 只在 Anthropic 腿出现；两条腿都有 `x-github-request-id` 和 `x-copilot-service-request-id` 响应头，那才是跨腿通用的取证 id。

---

## 6. 零命中的判据性证据

以下都是**查过之后的零**，不是没查：

| 检索面 | 范围 | 检索字面量 | 结果 |
|---|---|---|---|
| `v3_operation_summaries`（`summary_json` + `response_preview_text`） | 8 个 v3 库全部 145,781 行 | 全部 9 条字面量 | 5 命中，**全部是对话正文里在讨论这个话题**，无一是上游 body（脚本 `p1_summaries.py`；5 例已用 `p2_dump_op.py` 逐条打开确认：4 例是模型回答里在说「某个 subagent 撞到 `Prompt is too long`」，1 例是 `count_tokens` 请求正文在引用本项目的正则；5 例全部 `state=completed success=1`） |
| `v3_journal.error` | 8 个 v3 库 | 同上 | 0 |
| 非成功 operation 的全部 timeline 非 frame 事件 | 8 个 v3 库 | 见 `p4`/`p5`/`p6` | 48 命中（本报告主体） |
| **成功** operation 的 chunk-0 timeline | 8 个 v3 库 93,983 个成功 operation | 7 条限额字面量 | **0**（脚本 `p8_success_path.py`） |
| 本项目 `~/.local/share/ghc-api-proxy/history.db` | 8,966 条 | 6 条字面量 | 0；且 `error_message` 列全为 NULL，该库不存上游 body |
| 本项目 `~/.local/share/ghc-api-proxy/requests/*.jsonl` | 2 个文件，7.2 MB | 4 条字面量 | 0 |
| 本项目 `~/.local/share/ghc-api-proxy/rejected/` | — | — | **目录不存在**（`rejection_capture` 从未落过盘，或已被清理） |
| `~/.local/share/copilot-api/request-telemetry.json` | 15 MB | 5 条字面量 | 0 |
| `~/.local/share/copilot-api/` 下 178 个非 v3 `.db`（`archive/`、`archive-new/`、`archive-merged-2026-07-18/`、`archive-v2-2026-07-18/`、`telemetry.db`、`thinking-quarantine.db` 等） | 全表全列，TEXT 直搜 + BLOB 试 zstd/gzip/zlib，共 178 库扫完 | 7 条字面量 | 336 命中，**无一是该库自己记录的上游响应**——这批库存的是对话内容（`object_block` 表），命中全部是我和同伴过去在会话里讨论这个话题的正文。详见 §7 |
| `prompt token count of ... exceeds the limit of ...` | 8 个 v3 库全部 operation | 该字面量 | **0** |
| `context_length_exceeded` 作为上游 body 字段 | 8 个 v3 库 | 该字面量 | **0**（只在 `copilot-api-js` 源码里作为**合成给下游**的值出现） |

### 6.1 本次调查的方法学限制

- **`p8_success_path.py` 只读每个 operation 的 chunk-0。** 一个在流传输很晚才发生的 4xx 会被漏掉。该探针在 93,983 个成功 operation 里抓到了 12 个 4xx（`{'499': 3, '408': 6, '400': 1, '429': 2}`），证明「chunk-0 里确实装得下诊断事件」这条机制是通的（探针有分辨力，不是恒零），但它的覆盖面**不等于全量**。权重：**足以支持「上下文超限 400 在本机历史里从不发生在成功的 operation 上」这个倾向性判断，不足以支持「绝对没有」**。
- **同伴已知陷阱**（`from_history.py` 的「取变换图的根」判据在 2026-07-17 19:41 之前的 366 个 operation 上恒真失效）**不影响本次调查**：本次读的是 `diagnostic` / `terminal` 事件里的 `responseText`，那是 HTTP 层记录，不经过 transform 图；且最早的实例在 2026-07-18 19:52，已在该时间点之后。
- **账户类型维度未覆盖**：history 库不记录 plan/账户，无法回答「不同账户类型形状是否一样」。
- **未覆盖 2026-07-17 之前**：v3 库最早 2026-07-17 09:37。更早的数据在 `archive*/` 里（见 §7）。

---

## 7. 非 v3 归档库的扫描结果

脚本：`p7_other_stores.py`（178 个库，全表全列，TEXT 直搜 + BLOB 试 zstd/gzip/zlib 解压后搜）。**已跑完 178/178**，输出在 `260821-context-limit-400-evidence/p7_output.txt`（逐库汇总行 `== <path>: tables=… rows=… hits=…`，覆盖面可直接核对）。

共 336 命中，分布在 58 个库（`archive/`、`archive-merged-2026-07-18/`、`archive-new/`、`archive-v2-2026-07-18/` 四份目录高度重叠，是同一批会话的多次归档）。**无一是该库自己记录的上游响应。** 这批归档库的 schema（9 表，主表 `object_block`）存的是**对话内容**，没有存放上游 HTTP 错误 body 的位置。命中全部是正文：一篇讲 Anthropic API 错误码的文档、我和同伴过去讨论 `parseTokenLimitError` 的会话、以及若干工具输出。

证据等级：**录制/实测（覆盖面完整）**。

### 7.1 但归档里捞到两条有价值的二手记录

**(a) 一条比 v3 库更早的实例（2026-07-14）**——某次会话把上游 body 打印进了工具输出，被完整存了下来：

```
===== req_1784029268152_342 =====
upstream.rawBody: "{\"error\":{\"code\":\"model_max_prompt_tokens_exceeded\",\"message\":\"prompt is too long: 1000604 tokens \\u003e 1000000 maximum\",\"type\":\"invalid_request_error\"},\"request_id\":\"req_011Cd1tSzteXuJbsuSF1R5MY\",\"type\":\"error\"}"
upstream.body: null
upstream.usage: {"input_tokens": 0, "output_tokens": 0}
upstream.model: claude-opus-4.8
```

`req_1784029268152` → 2026-07-14 06:21。**形态与 §1.1 完全一致，limit 同为 1000000。** 把 Anthropic 腿这一形态的观察窗口从 2026-07-18 往前推到 2026-07-14。证据等级：**二手引用**（是会话里对当时 history 库的引用，不是本次直接读到的存储记录），但内容与 27 例一手记录逐字同形，可信。

**(b) 一条已被本次调查证伪的旧结论**——同一批归档里存着某次同伴调查的结论原文：

> ……**没有任何一条当前 2 条正则漏掉的真实 token-limit body**。语料里全部 token-limit 上游拒绝都是 Anthropic `prompt is too long: N tokens > N maximum`（code `model_max_prompt_tokens_exceeded`，如 `1002738 tokens > 1000000 maximum` / `1002484 tokens > 1000000 maximum`），**已被现有 Anthropic 正则命中**。其余 400 body 全非 token-limit（`thinking blocks cannot be modified`、`Unexpected role "system"`、`inv……`

**这条结论现在不成立**：Responses 腿的 21 例（`invalid_request_body` / `Your input exceeds the context window of this model.`）正是「当前 2 条正则漏掉的真实 token-limit body」。

它当时**很可能是对的**——那批归档全部早于 2026-07-18，而 Responses 腿的上下文超限最早出现在 **2026-08-06**。问题不在结论错，在于它**没有写下自己的观察窗口**：一句「语料里全部……」在语料换了之后仍然被当作全称命题读。这正好是本报告 §6.1 要求逐条标注限制的理由。

顺带，它还提供了两个本次未直接观察到的 Anthropic 腿 400 措辞，可补进 §3.2 的对照组（证据等级：**二手引用**）：`thinking blocks cannot be modified`、`Unexpected role "system"`。

---

## 8. 还没查清的、以及还能从哪找

1. **账户类型维度**——history 库无此字段。可能的来源：`~/.local/share/copilot-api/logs/`（未扫）、`negotiation-states.json`。
2. **`/chat/completions` 腿的真实 body**——本机 history 库里现网服务不走这条腿。唯一线索是 vscode-copilot-chat 那条 2025-12 录制。若要确证只能实测（用户已禁止）。
3. **`messages: text content blocks must be non-empty` / `The use of the web search tool is not supported.` 的完整 body**——本项目不落盘上游 body。可查的地方：Claude Code 客户端 transcript（`~/.claude/projects/*/`，含 `subagents/`），按 `message.id` 归组；这是项目记忆里记的「最后的取证手段」。
4. **窗口大小是否随模型变化**——Anthropic 腿实测只见过 `1000000` 一个值，跨三个 claude 模型；Responses 腿的 body 不含数字，**完全查不到 gpt 系列的窗口大小**。若需要，`~/.local/share/copilot-api/` 下的模型目录响应（`/models`）可能带 `capabilities.limits.max_prompt_tokens`，未在本次范围内。
5. **本项目自己的取证能力是缺的**——`rejection_capture.py` 只写「被拒的请求 body」，**不写上游的响应 body**（`error.body` 写进了 `record["upstream"]`，这点是写的；但 `rejected/` 目录不存在，说明这条路径在本机从未跑通过或产物已清）。这是一个可以独立提出的改进点，不属于本次调查结论。

---

## 附：探针脚本

全部在 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-context-limit-400-evidence/`，一律以 `?immutable=1` 或 `?mode=ro` 只读打开：

| 脚本 | 作用 |
|---|---|
| `p1_summaries.py` | 扫 `v3_operation_summaries` + `v3_journal.error`（最便宜的第一遍，结果是 5 个假阳性） |
| `p2_dump_op.py <db> <op>` | 单个 operation 的完整转储（summary / manifest / 全部 timeline 事件 / 全部对象 / frames） |
| `p3_failures.py` | 非成功 operation 按 terminal 错误归并的清单 |
| `p4_full_limit_errors.py` | 命中限额字面量的 operation，未截断全文；输出 `p4_output.txt` |
| `p5_all_4xx.py` | **所有** 4xx body 按形态归并（§3 的对照组来源）；输出 `p5_output.txt` |
| `p6_occurrences.py` | 48 例逐条列出 + 字段形态归并；输出 `p6_output.txt` |
| `p7_other_stores.py` | 178 个非 v3 库全表全列扫描；输出 `p7_output.txt` |
| `p8_success_path.py` | 成功 operation 的 chunk-0 扫描，闭合「回退后成功」的盲区；输出 `p8_output.txt` |
