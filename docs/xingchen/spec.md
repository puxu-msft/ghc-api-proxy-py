# Xingchen model provider 规格

状态：imported living specification；另一 source clone 曾实现并评审，当前 checkout 尚未装位对应 source history。

本规格定义 `ghc-api-proxy` 如何把 Xingchen 云端 LLM 网关接入 `app.model_provider`。它是本 feature 的目标行为权威；外部 TeleAgent 协议材料提供上游事实，用户在本项目中的裁决决定本次产品范围。当前实现状态以 [`status.md`](status.md) 顶部导入注记为准，不得从报告 PASS 或本规格存在反推 current main 已实现。

## 1. 依据与权威边界

上游事实来自 2026-09-04 更新的 `C:\Users\xp\.local\share\TeleAgent\TeleAgent的工作空间\TeleAgent模型调用协议规格书.md`，重点是 §2.2、§2.4、§4.1、§5.1 和 §12。

该材料的完整签名探测形成了足够据以实施的结论：

- `POST https://agent.teleai.com.cn/superCowork/sapi/api/v1/chat/completions` 返回 HTTP 200。
- `/responses`、`/v1/messages` 和 `/messages` 在使用各自 request URI 完整签名后均返回 HTTP 404。
- 56 个真实调用样本全部使用 OpenAI Chat Completions；未观察到 Anthropic Messages 或 OpenAI Responses 请求。
- `/models` 不可用于模型发现。

外部材料 §5.1.3 中仍有一句把 `Authorization` 写成 access token；它被 §4.1 的真实 tap 和 §12 的 HTTP 200 直连实验取代。本实现采用两份不同凭据：`Authorization` 使用 gateway API key，`X-Token` 使用完整 access token。

用户于 2026-09-04 裁定本次只实现 chat-only model provider，不扩展 Anthropic/Responses 与 Chat 之间的翻译。

## 2. Provider 身份与路由

配置中的 provider `type` 是 `xingchen`。

`model_providers` 下的配置键是本地 provider 名，也是 `provider/model` qualifier 的 provider 部分。例如配置键是 `xingchen` 时，`xingchen/chat-pro` 指向该 provider 的 `chat-pro` 模型。

本地 provider 名不进入上游 JSON。上游 `model` 仍是模型 ID，例如 `chat-pro` 或 `chat-lite`。

Xingchen 只发布 `ModelEndpoint.OPENAI_CHAT_COMPLETIONS`。它不发布以下能力：

- Anthropic Messages
- OpenAI Responses
- OpenAI Responses WebSocket
- OpenAI Embeddings
- Anthropic token counting

原生 OpenAI Chat Completions ingress 可以直连 Xingchen。当前项目没有 Anthropic/Responses→Chat translator；非 Chat ingress 必须在翻译或 endpoint 能力选择阶段失败，且不得向 Xingchen 发出请求。

## 3. 配置契约

### 3.1 字段

| 字段 | 必填 | 默认值 | 语义 |
|---|---:|---|---|
| `type` | 是 | 无 | 固定为 `xingchen` |
| `api_base_url` | 否 | `https://agent.teleai.com.cn/superCowork/sapi/api/v1` | 星辰网关基址；发送路径固定追加 `/chat/completions` |
| `models` | 是 | 无 | 静态模型 ID 列表；至少一项，不允许空项、重复项或按项目模型名规则等价的 ID |
| `gateway_api_key` | 是 | 无 | `Authorization: Bearer` 使用的 gateway API key |
| `x_token` | 是 | 无 | `X-Token` 使用并参与签名的完整 access token，保留原始前缀 |
| `device_id` | 是 | 无 | `X-SuperAgent-Device-Id` |
| `install_id` | 是 | 无 | `X-SuperAgent-Install-Id` |
| `app_version` | 否 | `2.4.1` | `X-App-Version` 及第二层签名字段 |
| `route_target` | 否 | `ops-gateway` | `X-Route-Target` |
| `client_type` | 否 | `desktop` | `X-TeleAI-Client-Type` |
| `user_agent` | 否 | `super-agent/1.0` | `User-Agent` |
| `disabled_models` | 否 | `[]` | 本地禁用的静态模型 ID |

所有 credential 和 identity 字段拒绝空串与纯空白。实现不得按 `sk-` 或某个 access-token 前缀作格式拒绝，因为参考材料没有把当前前缀规定为稳定协议。

`models` 的重复判断使用项目模型名匹配规则：先 trim、转小写，再把 `.` 视同 `-`。例如 `m-1.0` 与 `m-1-0` 不能同时出现，否则 unordered catalog index 会让进程 hash seed 决定实际发送哪一个上游 ID。

`gateway_api_key`、`x_token`、`device_id`、`install_id` 不得被自动裁剪；签名和 header 使用配置中的原始值。配置验证错误不得包含输入值，以免缺少另一个字段时把已经提供的 credential 写入 CLI 或启动错误。

GitHub Copilot 专属字段不能出现在 Xingchen variant；Xingchen 专属字段也不能出现在 GitHub Copilot variant。未知字段继续由 Pydantic `extra="forbid"` 拒绝。

### 3.2 环境变量

配置 loader 已支持 `GHC_API_PROXY_` 前缀和双下划线嵌套。Xingchen credential 可通过下列变量覆盖同名 YAML 字段：

```text
GHC_API_PROXY_MODEL_PROVIDERS__XINGCHEN__GATEWAY_API_KEY
GHC_API_PROXY_MODEL_PROVIDERS__XINGCHEN__X_TOKEN
```

YAML 字符串中的 `${VAR}` 不会被通用插值，不能把它当作 environment lookup。

### 3.3 热重载

Provider 实例和其 outbound client 在启动时构造。以下变化只记录为 restart-required，并继续使用启动值：

- provider 新增、删除或 `type` 改变
- `api_base_url`
- `models`
- `disabled_models`
- `gateway_api_key`
- `x_token`
- `device_id`
- `install_id`
- `app_version`
- `route_target`
- `client_type`
- `user_agent`

Provider graph 变化必须原子保留启动时 variant，不能只恢复 discriminator 而留下另一 variant 的字段。发生新增、删除或 type 变化时，`default_model_provider`、`fallback_model_provider` 与显式 `inbound.anthropic_count_tokens.providers` 也恢复为启动值，使 effective config 的所有 provider selector 仍指向实际构造的 graph。`restart_required` 只报告字段路径，不包含 credential 值。

## 4. 静态模型目录

Xingchen 不调用 `/models`。每个 `models` 配置项生成一个 `ModelDescriptor`：

```text
endpoints = {/chat/completions}
unknown_endpoints = ()
request_headers = {}
reasoning_efforts = None
adaptive_thinking = false
```

用于 diagnostics 的 synthetic raw catalog 使用 OpenAI list 形状，并明确 `source=static`。这份 synthetic catalog 是对配置的投影，不得声称来自上游模型目录。

构造 provider 时即完成静态目录装载并记录 `catalog_refreshed_at`。`refresh_catalog()` 不访问网络、不改变 timestamp，并返回 `False`。

`available_ids` 是静态目录减去本地禁用模型。`disabled_ids` 只包含 `models` 与 `disabled_models` 的交集；`disabled_models` 中不存在于静态目录的陈旧名字不计入 disabled 数量。

`describe()` 对 unknown 或 disabled 模型返回 `None`。发送这些模型时抛出 `UnknownModel`，且不得联网。

## 5. Payload 准备与最终字节

Provider 不翻译格式、不解析别名、不选择 fallback，也不覆盖上层已经决定的 `model`。

Client 先复制顶层 payload。仅当调用参数 `stream=True` 时：

- `stream_options` 不存在时补 `{ "include_usage": true }`。
- `stream_options` 是 mapping 时复制该 mapping，并对复制品执行 `setdefault("include_usage", true)`。
- `stream_options` 已存在但不是 mapping 时原样保留，让上游按原请求判断。
- 顶层执行 `setdefault("tool_stream", true)`。

调用方显式设置的 `false` 必须保留。非流式请求不注入上述两个字段。顶层和嵌套对象均不得被变异。

准备完成后只调用一次 `app.wire_json.dumps`，得到最终 `body_bytes`。SHA-256、HMAC 和 HTTP request 的 `content` 必须共用这一份字节，禁止签名后再次格式化或通过 SDK 重新序列化。

`WireJsonEncodeError` 在联网前原样传播。

## 6. Cloud gateway 签名

常量分为两种，不得混淆：

- 签名数据前缀：`superagent-auth-v1`
- `X-SuperAgent-Sign-Version` header 值：`v1`

每次上游 attempt 生成：

```text
timestamp = Unix 秒十进制字符串
nonce = UUIDv4
body_hash = lowercase_hex(SHA256(body_bytes))
request_uri = 最终 URL 的 path + 可选 query
```

第一层 HMAC key：

```text
parts = x_token.split(".")
key1 = parts[2] if len(parts) == 3 else x_token
```

不得 base64 decode 或去掉 access-token 前缀。

第一层数据：

```text
superagent-auth-v1/{x_token}/{install_id}/{timestamp}/{nonce}
```

第一层输出 `sig1` 是小写 SHA-256 HMAC hex。

第二层数据以 LF 连接：

```text
superagent-auth-v1
POST
{request_uri}
{timestamp}
{nonce}
{app_version}
{body_hash}
```

第二层 HMAC key 是 `sig1` 的 64 字符小写 hex ASCII，不是把 hex decode 后得到的 32 bytes。第二层输出是 `X-SuperAgent-Signature`。

## 7. 请求 URL 与 headers

最终 URL 是：

```text
{api_base_url.rstrip("/")}/chat/completions
```

签名使用最终 `httpx2.URL` 的 path 和 query；fragment 不上 wire，也不参与签名。

以下 headers 由 provider 拥有，必须逐项生成：

| Header | 值 |
|---|---|
| `Authorization` | `Bearer {gateway_api_key}` |
| `X-Token` | 完整 `x_token` |
| `X-SuperAgent-Sign-Version` | `v1` |
| `X-SuperAgent-Signature` | 第二层 HMAC hex |
| `X-SuperAgent-Timestamp` | Unix 秒字符串 |
| `X-SuperAgent-Nonce` | 签名 nonce |
| `X-SuperAgent-Device-Id` | `device_id` |
| `X-SuperAgent-Install-Id` | `install_id` |
| `X-App-Version` | `app_version` |
| `X-Route-Target` | `route_target` |
| `X-TeleAI-Client-Type` | `client_type` |
| `X-TeleAI-Upstream-Request-ID` | 与 nonce 独立的 UUIDv4 |
| `Content-Type` | `application/json` |
| `Accept` | 流式为 `text/event-stream`，非流式为 `application/json` |
| `Cache-Control` | `no-cache` |
| `User-Agent` | `user_agent` |

`X-TeleAI-Upstream-Request-ID` 必须独立生成；若极小概率与 nonce 相同，重新生成 request ID。

`extra_headers` 中 provider-owned headers 的任何大小写变体都不能覆盖或形成第二份值。`Host`、`Content-Length`、`Transfer-Encoding` 由 HTTP client 和最终 body 决定，不能从入站透传。其他允许的 tracing headers保留。

## 8. HTTP、流式与错误边界

Client 使用 provider 独占的 `httpx2.AsyncClient`，通过 `Request(content=body_bytes)` 和 `send(..., stream=stream)` 发送。

成功的非流式 response 按 httpx2 默认语义返回。成功的流式 response 不预读，交给现有 Chat SSE delivery path；provider 不解析、聚合或改写 SSE。预期 upstream stream 使用标准 OpenAI Chat chunk 和 `data: [DONE]`。

非 2xx response 必须成为 pipeline error，不能作为成功 response 返回。若错误 response 尚未消费，先读取错误 body，再 `raise_for_status()`，使错误载体保留 status、headers、body bytes 与 sent body bytes。

共享 error normalization seam 处理：

- `httpx2.HTTPStatusError`
- `httpx2.TimeoutException`
- `httpx2.TransportError`
- 现有 OpenAI/Anthropic SDK errors

`Retry-After` 继续按秒读取。仅当有效的标准值不存在时，`Retry-After-Ms` 按毫秒换算为秒。

Provider/client 不内建 retry。上层若资助新的 attempt，会重新执行 payload serialization、timestamp、nonce、upstream request ID 和签名。仅在参考材料中以错误字符串出现的 `request expired, resigning` 不足以在本 slice 新建 provider 内部 retry loop。

未识别的本地异常原样传播，不能伪装成上游错误。

## 9. Count tokens

`count_tokens()` 仍作为 `ModelProvider` 结构契约存在。

- unknown 或 disabled 模型抛 `UnknownModel`。
- 已知 Xingchen 模型通过 Anthropic Messages capability gate 后抛 `EndpointNotSupported`。
- 所有路径都不得联网。

项目的本地 token estimator 仍是独立的 `local` leg；它不成为 Xingchen 的远端计数能力。

## 10. Composition 与生命周期

`build_chain()` 按判别配置 variant 分派 builder：

- GitHub Copilot 分支继续构造 GitHub token source、Copilot token manager、OpenAI SDK 与 Anthropic SDK clients。
- Xingchen 分支只构造 raw `XingchenClient` 与 `XingchenProvider`。

每个 provider 使用独立 outbound `httpx2.AsyncClient`，全部记录在 `Chain.provider_clients`，由 `Chain.aclose()` 关闭。

GitHub subscription/base-URL probe 只处理 GitHub Copilot variant。Xingchen 永远不触发 GitHub token、account 或 device-flow 请求。`debug models --provider xingchen` 也不得顺带探测其他 GitHub provider。

Hosted web-search patterns 只从 GitHub Copilot variant 收集；Xingchen 不发布该字段或能力。

## 11. CLI、diagnostics 与配置展示

`auth`、`login` 和 `logout` 对 Xingchen 确定性拒绝，并说明 credential 来自 provider 配置。类型门必须在 GitHub host 推导、device flow、token-file 读写之前执行。

`debug models` 通过通用 `CatalogProvider` diagnostics seam 读取 GHC upstream catalog 或 Xingchen static catalog。文本输出标明 source；JSON 输出保留 provider 提供的 raw catalog。

`GET /api/config` 精确将每个 Xingchen provider 的 `gateway_api_key` 和 `x_token` 替换为固定 sentinel。它保留 provider 名、base URL、models、device/install ID 和其他诊断字段。遮盖只在展示层发生，不改变运行中 config。

## 12. 明确非目标

本 slice 不实现：

- Anthropic Messages、OpenAI Responses、Embeddings、Responses WebSocket、`/models` 或远端 token counting
- Anthropic/Responses→Chat 或 Chat→其他格式的 request/response/stream translation
- OAuth、refresh token、自动 credential 续期
- TeleAgent LevelDB、Windows 进程环境或文件中的 credential 自动抽取
- local-v1、本地完整 agent serve 或 AKSK
- provider 内部 retry orchestration
- 真实网关 canary

真实 canary 会使用有效 credential 并消耗额度，只能在用户另行明确授权后执行。

## 13. 验收条件

- 合法 Xingchen 配置可与 GHC 配置共同加载；跨 variant 字段、缺 credential、空模型、字节重复或 canonical-equivalent 模型会失败，且 validation error 不包含输入值。
- Signer 有独立固定向量与 hex-ASCII key 负控。
- MockTransport 观察到被 hash 的 body bytes 与实际上网 bytes 完全相同。
- 所有 provider-owned headers 逐项正确，且大小写变体伪造值不能覆盖或形成重复值。
- 原生 OpenAI Chat 非流式与 SSE 请求命中唯一 `/chat/completions` URL。
- 非 Chat endpoint、unknown/disabled model 和 count tokens 均在网络前拒绝。
- Xingchen static catalog 可被 status/debug 使用，refresh 不联网。
- Xingchen 不触发任何 GitHub auth/account probe。
- CLI credential 命令对 Xingchen 零副作用拒绝。
- `/api/config` 不返回 gateway API key 或 x_token，且保留非 credential 诊断字段。
- 现有 GHC provider、retry、delivery、CLI、debug 和全量测试不回归。

## 14. 修订记录

- 2026-09-04：初版。触发依据是用户要求新增 Xingchen model provider、外部 TeleAgent 协议完成 chat-only 探测，以及用户裁定本次只做 Chat provider、不扩展 translation driver。
- 2026-09-04：按冻结候选 `14a5fbec1f7abd349c45058b89f2c651ec2555d1` 的独立代码评审补充三项已复现契约：provider graph selector 原子恢复、validation input 隐藏、canonical-equivalent 静态模型拒绝。
- 2026-09-04：三项评审修复在 `2ed92c5ee15aa28726673343a2df290537da494f` 复评通过，随后以 squash commit `0cd1641aae90b4758a6ec4fc0fa053d24bf5906c` 集成到 `main`；行为契约不变。
