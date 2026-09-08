# 客户端请求头转发面调查

调查时刻的 HEAD：`53dd99c98e40aa892a4ccaa43a3c0d6a5e77e02d`（共享工作树，`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/module-org.md` 处于 modified 状态，同伴正在并行改动；`src/app/server/handler.py` 与 `src/app/pipeline/request_headers.py` 之间已存在签名不一致，见 §7.3）。

任务：为「按 `docs/.human-controlled/message-format-reshape.md`《剥离请求头》一节把直连路径改成黑名单」这一裁决收集事实。本文只报告读到的东西，不提设计方案。

参考项目：`/home/xp/src/copilot-api-js/`（存在，且找到了对应实现）。

---

## 0. 一句话结论

**这个项目已经有一份完整的、和 copilot-api-js 一一对应的 header security floor 实现（`src/app/anthropic/header_policy/__init__.py`），连配置键都齐了（`src/app/config/settings.py::AnthropicSettings`），但 `forward_request_headers` 在生产代码里零调用者，只有测试在用。**用户文档里那份「黑名单」正是这个 floor 的敏感项子集。所以这件事不是「新建机制」，更像是「把已经躺在仓库里的 floor 接上新链路，并在它之上加模式层」。

同时测得一个**当前就成立的合并语义陷阱**：`GhcApiClient.request_headers` 用普通 dict 合并把客户端头放在代理头下面，而代理头里 `Authorization`、`X-Interaction-Id`、`X-Interaction-Type`、`X-Agent-Task-Id` 是大写拼写。在 OpenAI SDK 路径上，dict 合并是**大小写敏感**的，SDK 也不折叠——客户端小写的 `authorization` 会与代理的 `Authorization` **并存**，两条 Authorization 都发到线上。详见 §1。

---

## 1. `extra_headers` 到底怎么合并（Q1）

### 1.1 调用链

| 位置 | 符号 | 做了什么 |
|---|---|---|
| `src/app/pipeline/direct_driver/base.py` | `DirectDriver._send` | `extra_headers=context.client_headers or None` 传给 `provider.send` |
| `src/app/model_provider/github_copilot.py` | `GithubCopilotProvider.send` | 按 endpoint 分派到 `GhcApiClient.send_anthropic_messages` / `send_chat_completions` / `send_responses`；**`send_embeddings` 不接 `extra_headers`** |
| `src/app/model_provider/ghc_client/client.py` | `GhcApiClient.request_headers` | **合并点**：`headers = {**{str(k): str(v) for k, v in extra_headers.items()}, **headers}` |
| 同上 | `_post_openai` / `_post_anthropic` | `options={"headers": <合并结果>}` 交给 SDK |
| SDK | `openai._base_client.BaseClient._build_headers` / `anthropic._base_client.BaseClient._build_headers` | 见 §1.3、§1.4 |

`GhcApiClient.request_headers` 的 docstring 已经写明意图是「caller adds underneath rather than on top」。**意图是对的，实现只在同拼写时成立。**

### 1.2 第一层：`request_headers` 内部的 dict 合并

`{**extra_lowercased, **proxy}`——Python dict 合并，键是**大小写敏感的字符串**。

`build_request_headers`（`src/app/model_provider/ghc_client/headers.py`）产出的键拼写：

- 小写：`editor-version`、`editor-plugin-version`、`user-agent`、`x-vscode-user-agent-library-version`、`content-type`、`copilot-integration-id`、`openai-intent`、`x-github-api-version`、`x-request-id`、`copilot-vision-request`
- **大写开头**：`Authorization`、`X-Interaction-Id`、`X-Interaction-Type`、`X-Agent-Task-Id`

而 `forwarded_client_headers`（`src/app/pipeline/request_headers.py`）**总是把客户端头名 lowercase**。

于是：客户端的 `authorization` 与代理的 `Authorization` 在这个 dict 里是**两个不同的键，同时存在**。`x-interaction-id`、`x-agent-task-id` 同理。

### 1.3 OpenAI SDK 路径（`/responses`、`/chat/completions`、`/embeddings`）——**不折叠，重复发出**

`openai/_base_client.py:474`：

```python
headers_dict = _merge_mappings({**self._auth_headers(...), **self.default_headers}, custom_headers)
```

`_merge_mappings`（`:2278`）也是 `{**obj1, **obj2}`——同样大小写敏感。随后 `:478` `httpx2.Headers(headers_dict)`，`:612` `request_headers = list(headers.multi_items())`——**保留全部条目**。

实测（openai 3.3.1 + `httpx2.MockTransport`，模拟 `{**client_lowercased, **proxy}`）线上头：

```
authorization: Bearer PROXY-COPILOT
...
authorization: Bearer CLIENT-KEY          ← 两条 Authorization
user-agent: AsyncOpenAI/Python 3.3.1
...
user-agent: GitHubCopilotChat/0.36        ← 两条 User-Agent
content-type: application/json
...
content-type: application/json            ← 两条 Content-Type
host: evil.example
content-length: 999                       ← 只有这一条，真实长度那条被顶掉了
accept-encoding: gzip, br
x-stainless-lang: python
x-stainless-lang: js                      ← 两条
```

三点要注意：

1. **`authorization` 并存**，上游拿哪一条不确定，多数 HTTP 服务器要么取第一条要么按 400 拒绝。这不是「客户端凭据被忽略」，也不是「干净覆盖」，是**两条都发**。
2. **`user-agent` / `content-type` 的重复现在就已经发生**，与客户端头无关：SDK 的 `default_headers` 用 `"User-Agent"` / `"Content-Type"`（大写），我们的 `build_request_headers` 用小写，两者永不折叠。`create_copilot_sdk_clients`（`src/app/upstream/client.py`）与 `src/app/server/composition.py:452` 构造 `AsyncOpenAI` 时**都没有传 `default_headers`**，所以每个走 OpenAI SDK 的上游请求今天就带着两条 User-Agent。这是一条独立于本次改动的既有事实，未验证上游是否在意。
3. `content-length: 999` **顶掉了**httpx 依据真实 body 计算的那条（输出里没有第二条）。转发客户端 `content-length` 会直接损坏请求分帧。

### 1.4 Anthropic SDK 路径（`/v1/messages`、`/v1/messages/count_tokens`）——**折叠，代理胜出**

`anthropic/_base_client.py:455 _build_headers` 走 `build_headers(...)`（`:2460` 附近），它往一个 `httpx2.Headers` 对象里 `headers[name] = value` 逐层写入。`httpx2.Headers.__setitem__` 是**大小写无关**的替换，所以案例变体会被折叠，最后写入的胜出。

实测（anthropic 1.0.0）：

```
x-api-key: sk-ant-CLIENT        ← 客户端的 x-api-key 替换了 SDK 的 X-Api-Key: proxy-managed
Authorization: Bearer PROXY     ← 代理胜出（在合并 dict 里排在后面）
user-agent: GitHubCopilotChat/0.36   ← 只有一条，代理胜出
host: evil.example              ← 顶掉了 Host: api.githubcopilot.com
content-length: 999             ← 顶掉了真实的 Content-Length: 7
accept-encoding: gzip, br       ← 顶掉了 httpx 的 gzip, deflate, zstd
cookie: s=1
forwarded: for=1.2.3.4
```

所以 anthropic 路径上：

- `Authorization` **安全**（代理胜出），因为在 `request_headers` 的 dict 里代理排在后面，且 SDK 折叠。
- **`x-api-key` 不安全**：SDK 用 `X-Api-Key` 承载自己的 key（`auth_headers == {'X-Api-Key': 'proxy-managed'}`），代理的 `build_request_headers` **根本不产生这个键**，所以客户端的 `x-api-key` 没有任何东西压制它，直接替换并发往上游。这正是用户文档把 `X-Api-Key` 列进黑名单的原因。
- `host` / `content-length` / `accept-encoding` **全部由客户端值胜出**，httpx 不再补自己的。

### 1.5 `host` / `content-length` / `accept-encoding` 的确切语义

- **`content-length`**：两条 SDK 路径上客户端值都会成为唯一的 Content-Length（实测）。客户端那个值描述的是**它发给代理的 body**，而代理会重建 body（翻译、beta flag 剥离、`payload["model"]` 改写都改变字节数）。转发它必然损坏上游侧分帧。
- **`accept-encoding`**：客户端值胜出（实测）。httpx 只对自己声明过的编码做自动解压；客户端声明 `br` 而 httpx 不支持时，拿到的是压不开的 body。copilot-api-js 在传输层把它硬钉成 `identity` 并注释说明正是这个原因（`src/lib/transport/http2-client.ts:94`，`H2_ILLEGAL_HEADERS` / `TRANSPORT_OWNED_HEADERS`）。
- **`host`**：客户端值胜出（在 MockTransport 构造的 HTTP/1.1 形态请求对象上实测）。**HTTP/2 上未实测**——本项目走 httpx2 + h2，RFC 9113 §8.3.1 规定 `host` 与 `:authority` 不一致的请求是 malformed，copilot-api-js 把 `host` 放进 `H2_ILLEGAL_HEADERS` 在 h2 请求前无条件剥掉。这条判据的权重：**推理 + 参考实现旁证，未在本仓库实测**，动手前值得补一次真实 h2 探针。

---

## 2. 代理自己设置的请求头（Q2）

`src/app/model_provider/ghc_client/headers.py`：

**`build_identity_headers(config)`——身份**

| 头名 | 值 |
|---|---|
| `editor-version` | `vscode/{config.vscode_version}` |
| `editor-plugin-version` | `copilot-chat/{config.copilot_version}` |
| `user-agent` | `GitHubCopilotChat/{config.copilot_version}` |
| `x-vscode-user-agent-library-version` | `electron-fetch` |

**`build_request_headers(...)`——在上面基础上追加**

| 头名 | 类别 | 值 |
|---|---|---|
| `Authorization` | **凭据** | `Bearer {token}` |
| `content-type` | 内容框架 | `application/json` |
| `copilot-integration-id` | 身份 | `vscode-chat` |
| `openai-intent` | 路由/意图 | `intent`（默认 `conversation-panel`） |
| `x-github-api-version` | 协议 | `config.api_version` |
| `x-request-id` | 关联 | uuid4 或传入值 |
| `X-Interaction-Id` | 关联/会话 | 进程级 `interaction_id` |
| `X-Interaction-Type` | 路由/意图 | 同 `intent` |
| `X-Agent-Task-Id` | 关联 | 同 `x-request-id` |
| `copilot-vision-request` | 能力 | `"true"`，仅 `vision=True` 时出现 |
| `model_request_headers` 里的项 | 目录透传 | 已用 `protected = {name.lower() for name in headers}` 做小写保护，不能覆盖上面任何一项 |

**注意两处不对称：**

1. `copilot-vision-request` 是**条件性核心键**。copilot-api-js 明确把它**无条件**加进 `coreLower` 保留集（`request-preparation.ts:456`，注释："Reserve it unconditionally so a client can't forge it on a non-vision request"）。我们这边没有等价保留。
2. **`x-api-key` 不在代理核心集里**，但 anthropic SDK 用它做鉴权。核心集的「谁会被客户端头冲掉」清单必须把 SDK 自带的头也算进去：anthropic SDK 的 `default_headers` 实测为 `Accept`、`Content-Type`、`User-Agent`、`X-Stainless-*`、`X-Api-Key`、`anthropic-version`；openai SDK 的是 `Accept`、`Content-Type`、`User-Agent`、`X-Stainless-*`（openai 路径 auth 用 `Authorization`）。

`model_request_headers` 目前在新链路上**没有被传进来**——`GhcApiClient.request_headers` 调 `build_request_headers` 时只给 `token / config / interaction_id`，`intent`、`vision`、`model_request_headers` 都是默认值。descriptor 上采集了 `request_headers`（`github_copilot.py::replace_catalog`）却没有送到构造点。这是另一件与本调查相邻的事，记下不展开。

---

## 3. 直连路径与翻译路径怎么区分（Q3）

### 3.1 可靠的字段

`RequestContext.translation_required`（`src/app/pipeline/request.py:72`），由 `apply_route`（`src/app/server/handler.py:88`）从 `Route.translation_required` 写入，而后者在 `src/app/pipeline/routing.py:107` 定义为：

```python
translation_required=target_format is not inbound_format
```

所以 `translation_required` 与 `target_format is not inbound_format` 是**同一个判据**，不是两个。用哪个都行，`translation_required` 语义更直白。

**但它在 `build_context` 之后才被填。** `forwarded_client_headers` 目前在 `src/app/server/inbound.py:85`（`build_context` 内）调用，那时 `endpoint` / `target_format` / `translation_required` 全是默认值。要按路径分模式，过滤点必须移到 `apply_route` 之后——`shape_request`（`handler.py:114` 起）里已经有一个「`inbound_format is ANTHROPIC_MESSAGES` 时做 beta flag 剥离」的块，位置和它一致。

注意 `build_context` 的 docstring 现在写着「Headers are filtered here rather than at the send site so that nothing downstream ever holds the client's credentials」——移动过滤点会推翻这句话陈述的性质，需要一并改。

### 3.2 各入口归属

路由表在 `src/app/server/inbound.py::ROUTES`；OpenAI 组另挂 `""`、`/v1`、`/openai/v1` 三个前缀（`OPENAI_PREFIXES`）。`/v1/messages` 与 `/v1/messages/count_tokens` **只有裸路径**，不挂前缀。

| 入口 | `inbound_format` | 直连还是翻译 |
|---|---|---|
| `/v1/messages` | `anthropic-messages` | **取决于路由**。模型支持 `ANTHROPIC_MESSAGES` → 直连上游 `/v1/messages`；不支持则 `_first_supported` 回退（`_FALLBACK_ORDER` 里 `OPENAI_RESPONSES` 排第二）→ 翻译到 `/responses`。**同一个入口两种归属，且由 catalog 决定，无法靠路径静态判定。** |
| `/v1/messages/count_tokens` | `anthropic-messages` | 同上；但见 §3.3——这条路今天根本不传客户端头 |
| `/chat/completions`（含 `/v1`、`/openai/v1` 前缀） | `openai-chat-completions` | 支持则直连，否则翻译 |
| `/responses`（含前缀，即 `/v1/responses`） | `openai-responses` | 支持则直连，否则翻译 |
| `/embeddings`（含前缀） | `openai-embeddings` | 直连；且 `send_embeddings` 签名里**没有 `extra_headers`**，客户端头永不到达 |
| `model@format` 显式后缀 | 任意 | `explicit_format` 分支，仍按 `target_format is not inbound_format` 判定 |

**一个需要用户裁决的缺口**：用户文档《剥离请求头》一节开头写着「这部分仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效」。那么 `/v1/responses` 直连到上游 `/responses` 时，它既不是 Anthropic 入口（文档不覆盖），又是直连路径。文档没说它该走哪种机制。现状是走 `forwarded_client_headers` 的白名单，只放 `anthropic-beta` / `anthropic-version`——对一个 OpenAI 入口而言这两个头本身就没意义。

### 3.3 count_tokens 今天完全不传客户端头

`GithubCopilotProvider.count_tokens` → `GhcApiClient.send_anthropic_count_tokens(payload)`——签名里**没有 `extra_headers` 参数**。`handle_count_tokens`（`handler.py:227`）也不经过 `DirectDriver`。所以：

- 现在客户端的 `anthropic-beta` **到不了** `/v1/messages/count_tokens`。
- 文档把 count_tokens 与 messages 并列，若要让它遵守同一套机制，需要新增参数并接线，不是改一个名单就完事。

---

## 4. 既有的 header security floor 在哪（Q4）

**在。是一份完整实现，但请求方向零生产调用者。**

`src/app/anthropic/header_policy/__init__.py`：

- `REQUEST_FLOOR`：28 项，与 copilot-api-js 的 `SENSITIVE_DENYLIST` **逐项一致**（凭据、分帧/跳段、拓扑泄漏三类）。
- `RESPONSE_FLOOR`：14 项，与 `PROXY_CONTROLLED_RESPONSE_HEADERS` 一致。
- `forward_request_headers(headers, *, core, strict, blacklist, whitelist)`：floor（`REQUEST_FLOOR` + `core` 键名小写 + `x-github-*` / `openai-*` 前缀）→ 模式层（`strict` 走白名单交集，否则黑名单差集）→ `{**selected, **core}`。**结构与 copilot-api-js 的 `selectPassthroughHeaders` → `keepHeaders`/`pruneHeaders` → `{...selected, ...core}` 完全同构。**
- `forward_response_headers`：同构。
- `normalize_responses_response_headers`：本项目自有，收窄到 `request-id` / `x-request-id` / `retry-after` / `x-ratelimit-*`。

**接线状态（`rg` 全仓库，`src/` + `tests/`）：**

| 符号 | 生产调用者 | 测试调用者 |
|---|---|---|
| `forward_request_headers` | **无** | `tests/unit/anthropic/test_anthropic_preparation.py:11,29` |
| `forward_response_headers` | `src/app/routes/anthropic.py:156`（legacy 链路） | 同文件 `:36,45` |
| `normalize_responses_response_headers` | `src/app/anthropic/client.py`（legacy 链路） | — |

配置键也已经存在且默认值与 copilot-api-js 一致——`src/app/config/settings.py::AnthropicSettings`：

```python
strict_request_headers: bool = False
strict_response_headers: bool = False
request_header_blacklist = ["x-anthropic-billing-header"]
request_header_whitelist = ["accept", "anthropic-dangerous-direct-browser-access", "x-app", "x-claude-code-*", "x-stainless-*"]
response_header_blacklist = []
response_header_whitelist = ["request-id", "x-request-id", "anthropic-ratelimit-*", "anthropic-organization-id", "retry-after"]
```

这四个 request 侧键在 `src/` 与 `tests/` 里**除定义处外零引用**。

设计依据留存在 `.dev/docs/archived-2604-rewrite/header-forwarding.md`（含 floor 两层结构、空名单镜像语义、`fnmatch` 实现建议）。⚠️ 该目录被用户在 2026-08-20 裁定为「copilot-api-js 学习笔记，整体过期」，接手前需重新判断其是否仍成立；但它对**事实**的记述与我在 copilot-api-js 里直接读到的代码逐条吻合。

冻结 spec 里「header security floor 不可 hook 化」的引文出处：`.dev/docs/hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md:63`、`.dev/docs/archived-2604-rewrite/hooks-system.md:62`、`hooks-tokenization-spec.md:188,224`。

---

## 5. copilot-api-js 的实际做法（Q5）—— 黑名单为什么是那样

代码位置：`/home/xp/src/copilot-api-js/src/lib/anthropic/header-policy/`（`request-header-forward.ts`、`response-header-forward.ts`、`header-glob-strip.ts`、`header-name-match.ts`），装配点 `src/lib/anthropic/request-preparation.ts::buildAnthropicHeaders`（`:385`，客户端头处理在 `:440-462`）。

### 5.1 三层结构，实际行为

```
core = { ...copilotHeaders(state, {vision, modelRequestHeaders, intent}),
         "X-Initiator": ..., "anthropic-version": "2023-06-01" }
       （+ "anthropic-beta" 若有）

coreLower = 小写(core 的全部键) ∪ {"copilot-vision-request"}

safe     = selectPassthroughHeaders(clientHeaders, coreLower)
           = 客户端头 − coreLower − SENSITIVE_DENYLIST − SENSITIVE_PREFIXES
selected = strict ? keepHeaders(safe, whitelist) : pruneHeaders(safe, blacklist)
headers  = { ...selected, ...core }
```

`SENSITIVE_DENYLIST`（`request-header-forward.ts:35-64`，逐字）：

```
cookie, set-cookie, authorization, proxy-authorization, x-api-key, api-key,
host, content-length, content-encoding, accept-encoding, expect,
connection, keep-alive, transfer-encoding, te, trailer, upgrade,
via, forwarded, x-real-ip, x-forwarded-for, x-forwarded-host,
x-forwarded-proto, x-forwarded-port, x-forwarded-server,
true-client-ip, cf-connecting-ip, x-client-ip
```

`SENSITIVE_PREFIXES`：`["x-github-", "openai-"]`。

**`Authorization` 绝不转发给上游。** 它同时被 `coreLower`（代理自己设 `Authorization`）和 `SENSITIVE_DENYLIST` 挡掉。源码注释明说 denylist 里那条是 defense-in-depth，防的是「未来某次重构把 core key 变成条件性的」。

### 5.2 用户文档那份黑名单的来源

用户文档的直连黑名单是：`Forwarded` chain；`Cookie` `X-Api-Key`；`Host`；`Content-Length` `Content-Encoding` `Accept-Encoding`。

对照可见：**这是 `SENSITIVE_DENYLIST` 的分类摘要**——「`Forwarded` chain」= via/forwarded/x-real-ip/x-forwarded-*/true-client-ip/cf-connecting-ip/x-client-ip 这一整组，「Cookie / X-Api-Key」= 凭据组，「Host / Content-Length / Content-Encoding / Accept-Encoding」= 分帧组。

**它漏掉的**（相对 copilot-api-js 的实际行为）：

- 凭据组的 `authorization`、`proxy-authorization`、`api-key`、`set-cookie`；
- 跳段组的 `expect`、`connection`、`keep-alive`、`transfer-encoding`、`te`、`trailer`、`upgrade`；
- 前缀组 `x-github-*`、`openai-*`；
- 「代理核心键动态排除」这一整层——它不是名单，是从 `core` 的键名算出来的。

**我的判断（可据以行动）**：文档那份不是完整黑名单，是 floor 的**可记忆摘要**，`authorization` 之所以缺席，最可能是因为它在参考实现里由 core key 层挡住、写名单的人认为它已被覆盖。但在**我们这边**，core key 层不存在（`forward_request_headers` 没接线），且 §1.3 已实测 OpenAI SDK 路径上大小写变体不折叠——所以**照文档字面实现 = `Authorization` 会被转发**。这一条我认为必须回到用户面前确认，不能自行补齐也不能照字面实现。

### 5.3 参考实现的默认模式

`packages/foundation/src/state-defaults.ts:118-120`：

```
strictRequestHeaders: false                              → 黑名单模式是默认
requestHeaderBlacklist: ["x-anthropic-billing-header"]
requestHeaderWhitelist: ["accept", "anthropic-dangerous-direct-browser-access", "x-app", "x-claude-code-*", "x-stainless-*"]
```

即：**默认放行 floor 之外的一切客户端头**（含 `x-stainless-*`、`x-claude-code-*`、`user-agent`?——不，`user-agent` 是 core key 被挡掉），只额外剥 `x-anthropic-billing-header`。

### 5.4 翻译路径：copilot-api-js 根本不转发

`buildAnthropicHeaders` 是**唯一**读 `opts.clientRequestHeaders` 的地方（`rg -n "clientRequestHeaders" src/` 全量确认）。OpenAI 侧：

- `src/lib/openai/request-preparation.ts::prepareChatCompletionsRequest`（`:95`）
- 同文件 `prepareResponsesRequest`（`:116`）
- `src/lib/openai/embeddings.ts:59`

三处都是 `headers = { ...copilotHeaders(state, {...}), "X-Initiator": ... }`——**没有任何客户端头透传**。

**这就是用户文档「翻译路径的白名单有：（暂无）」的确切出处**：不是「还没想好」，是参考实现在非 Anthropic-direct 路径上一个客户端头也不转发。

### 5.5 参考实现同时在传输层再挡一次

- `src/lib/transport/http1-client.ts::serializeRequest`（`:135` 附近）：`H1_TRANSPORT_OWNED_HEADERS` 跳过；并对每个头名/值跑 `HEADER_NAME_RE` / `HEADER_VALUE_RE`，**CR/LF 直接抛异常**。注释明说：「The values reaching here include client-supplied headers under `strict_request_headers`, so this is the layer that has to refuse them.」——header injection 防线。
- `src/lib/transport/http2-client.ts`：`H2_ILLEGAL_HEADERS = {host, connection, transfer-encoding, keep-alive, upgrade, proxy-connection}` 在 `session.request` 前剥掉；`TRANSPORT_OWNED_HEADERS = {accept-encoding}` 强制 `identity`，注释写「defense-in-depth: the passthrough denylist already drops accept-encoding, but the transport enforces its own framing invariant」。

**我们这边没有等价层**：httpx2/h2 会做什么、CRLF 会不会被 httpx 拒绝，本次未测。

### 5.6 `PROTECTED_HEADERS`（黑名单原语自带的兜底）

`header-glob-strip.ts:31`：`{authorization, content-type, content-length, copilot-integration-id}`——即使运维的 glob 命中也不剥。注释诚实地写明「在当前调用链中这四个键在 `pruneHeaders` 执行前就已经被 floor 剔除，从未真正触发」，保留是为了这个导出原语的独立契约。

---

## 6. `anthropic-version` 的去向（Q6）

**上游 `/v1/messages` 不需要我们操心这个头——anthropic SDK 无条件带它。**

实测（`AsyncAnthropic(api_key="proxy-managed", ...)`，不传任何客户端头）：

```python
c.default_headers == {'Accept': ..., 'Content-Type': ..., 'User-Agent': ...,
                      'X-Stainless-*': ..., 'X-Api-Key': 'proxy-managed',
                      'anthropic-version': '2023-06-01'}
```

线上确实出现 `anthropic-version: 2023-06-01`。SDK 用的是**小写**拼写，与 `forwarded_client_headers` 产出的拼写一致，所以客户端值会**替换**它（而不是并存）。

代码里设 `anthropic-version` 的其他位置，全仓库 `rg` 结果只有两处：

1. `src/app/pipeline/request_headers.py:23` —— 当前白名单里的那一项。
2. `src/app/anthropic/request_preparation.py:56` —— `headers = {"anthropic-version": "2023-06-01"}`。这条属于 **legacy 链路**：`prepare_anthropic_request` 只被 `src/app/anthropic/client.py:12` 引用，而 `AnthropicClient` 被 `runtime.py` / `deps.py` / `pipeline/executor.py` / `upstream/bootstrap.py` 使用，与 `server/handler.py` 的新 pipeline 是两套。它产出的 headers 走 `client.py:200` 的 `extra_headers=prepared.headers`。

**据此对本次改动的意义**：直连路径改黑名单后，`anthropic-version` 不在黑名单里 → 继续转发（与今天效果相同，客户端值替换 SDK 默认值）。翻译路径白名单为空 → 不转发，但翻译路径的目标是 `/responses`（OpenAI SDK），那里本来就没人读 `anthropic-version`，**无损**。这一条我判断**没有风险**。

参考实现的做法可作旁证：copilot-api-js 把 `"anthropic-version": "2023-06-01"` 放进 **core**（`request-preparation.ts:436`），即代理权威、客户端不可覆盖——与我们「让客户端值覆盖」相反。这是一个**尚未被裁决的分歧点**，值得提给用户。

---

## 7. 我认为最要紧的风险点

按我的优先级排列。前三条我认为足以支撑行动，第四条只是记录。

### 7.1 【最高】直接照文档字面实现黑名单，`Authorization` 会被转发，且在 OpenAI SDK 路径上是「两条并存」

- 文档黑名单里没有 `Authorization`（§5.2 分析了为什么——参考实现靠 core key 层挡，文档只摘了 denylist）。
- 我们这边 core key 层（`forward_request_headers`）**没接线**（§4）。
- OpenAI SDK 路径上大小写变体**不折叠**（§1.3 实测）：代理的 `Authorization` 和客户端的 `authorization` 一起发出去。上游会拿哪条、会不会 400，未测。
- Anthropic SDK 路径上 `Authorization` 侥幸安全（折叠 + 代理排后），但这个安全**依赖于 dict 插入顺序 + SDK 内部实现**，不是任何一处代码声明的不变式。参考实现的注释专门点名了这一点：「The guard is NOT the spread order」。

### 7.2 【高】`x-api-key`、`host`、`content-length`、`accept-encoding` 四项在两条 SDK 路径上都是客户端值胜出

`x-api-key` 尤其隐蔽：代理核心集里根本没有这个键，anthropic SDK 却用它鉴权，所以没有任何「代理头压制客户端头」的机制会碰到它（§1.4 实测 `x-api-key: sk-ant-CLIENT` 替换了 `X-Api-Key: proxy-managed`）。这三项分帧头会静默损坏请求，而不是报错。

### 7.3 【高】过滤点必须从 `build_context` 移到 `apply_route` 之后，而那个位置正在被同伴改

`translation_required` 在 `build_context` 时还没填（§3.1）。落点应该在 `shape_request`（`handler.py:114` 附近）——**而那一段现在就处于不一致状态**：`handler.py:117` 调 `strip_denied_beta_flags(context.client_headers, model=..., denials=...)`，`request_headers.py:42` 的签名却是 `(headers, *, models: Sequence[str], denied_by_model: Mapping[...])`。同伴正在改这个函数。动手前需要先和主会话对齐，避免撞车。

### 7.4 【中，独立于本次改动】OpenAI SDK 路径今天就在发两条 `User-Agent` 和两条 `Content-Type`

`build_request_headers` 用小写 `user-agent` / `content-type`，openai SDK 的 `default_headers` 用 `"User-Agent"` / `"Content-Type"`，而 `AsyncOpenAI(...)` 构造时没传 `default_headers`（`src/app/upstream/client.py`、`src/app/server/composition.py:452`）。实测确认两条都发。上游是否在意、以及 Copilot 是否因此把我们的身份识别成 `AsyncOpenAI/Python 3.3.1`——**未测**，但 `request_headers` 的 docstring 恰恰把「a caller forwarding a client's headers would otherwise replace `user-agent`」当成不可接受的后果，而同一个后果已经由 SDK 自己造成了。

### 7.5 【中】三处已有实现/配置在等着被接上，重复造一份的成本是让它们更难被发现

`forward_request_headers` + `AnthropicSettings` 的四个 request 侧键（§4）已经是这套机制的完整形态，包括空名单的镜像语义。若本次新写一份而不动它们，仓库里会有两份同名机制，其中一份永远不执行。

### 7.6 缺口，需用户裁决（不自行决定）

1. 直连黑名单是否补齐 `authorization` / `proxy-authorization` / `api-key` / `set-cookie` / 跳段组 / `x-github-*` / `openai-*`，还是照文档字面只列六类？
2. `anthropic-version` 归代理权威（参考实现做法）还是允许客户端覆盖（现状）？
3. `/v1/responses`、`/chat/completions`、`/embeddings` 这些 OpenAI 入口的直连路径，是否也适用直连黑名单？文档只写了 Anthropic 入口。
4. `/v1/messages/count_tokens` 今天完全不传客户端头（§3.3），要遵守同一机制需要新增 `extra_headers` 参数并接线——做还是不做？
5. `copilot-vision-request` 是否也要像参考实现那样无条件保留，防客户端伪造？

---

## 附：本报告的证据等级

| 结论 | 依据 | 权重 |
|---|---|---|
| §1.3 OpenAI SDK 不折叠大小写、重复发出 | `httpx2.MockTransport` 实测 + `_base_client.py:474,478,612` `_merge_mappings:2286` 源码 | **强，可直接据以行动** |
| §1.4 Anthropic SDK 折叠、客户端 `x-api-key` 胜出 | 同上 + `anthropic/_base_client.py:455,2460+` 源码 | **强，可直接据以行动** |
| §1.5 `host` 在 h2 上的行为 | RFC 9113 §8.3.1 + copilot-api-js `H2_ILLEGAL_HEADERS` 旁证，**本仓库未实测** | 中，动手前建议补探针 |
| §2 代理头集合 | 直读 `headers.py` 全文 | 强 |
| §3 路径区分 | 直读 `routing.py:107`、`inbound.py::ROUTES`、`handler.py:88` | 强 |
| §4 floor 存在但零调用者 | `rg` 全仓库 `src/` + `tests/`，逐符号 | 强 |
| §5 copilot-api-js 实际行为 | 直读源码（非注释），含 `state-defaults.ts` 默认值 | 强 |
| §6 anthropic SDK 无条件带 `anthropic-version` | 实测 `c.default_headers` | 强 |
| §7.4 今天就在发两条 User-Agent | 实测 + 构造点无 `default_headers` 参数（源码确认） | **强（现象）/ 未测（上游是否在意）** |
