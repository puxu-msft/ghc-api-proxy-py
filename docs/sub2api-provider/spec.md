# sub2api model provider 上游 endpoint 配置规格

状态：**DRAFT — 待实现与复评**。上游 provider（`app.model_provider.openai_compatible`）已合入 `main`（`10459e4c` 引入、`42fb2329` 接上 token 计数），但此前只用单一 `api_base_url` 并默认把三个原生协议当作全部直连。本规格把「这个上游直连服务哪些协议、各在哪个地址」拆成三项可独立配置的字段，并把默认改成显式声明。首版记录用户 2026-09-08 的裁决。

**这份是 Spec**，答「应该是什么样」，规范性。**活文档，不冻结。** 新裁决、实测或发现与本文冲突或限定它时当场修订，修订记入 §6。权威永远是当前版本。

## 1. 背景

sub2api 上游原生服务多条协议：Anthropic Messages、OpenAI Responses、OpenAI Chat Completions，另有一条不受本文门控的 OpenAI Embeddings。不同 sub2api 上游实现的能力不同，并非每个都原生实现这三条协议，所以不一定都能走直连路径。单一 `api_base_url` 加硬编码路径、且默认三者全直连的旧模型，无法表达「某个上游只原生服务 Responses、不服务 Anthropic Messages」这类部署。

本文把直连能力与地址拆成三个可独立配置的上游 endpoint 字段。

## 2. 配置字段（用户裁决 2026-09-08）

`model_providers.<name>`（type `sub2api`）新增三个可选字段：

| 字段 | 控制的上游协议 | 备注 |
|---|---|---|
| `openai_chat_completions_endpoint` | OpenAI Chat Completions | — |
| `openai_responses_endpoint` | OpenAI Responses | — |
| `anthropic_messages_endpoint` | Anthropic Messages | **同时控制 `count_tokens`** |

每个字段三态（**用户裁决**）：

- **不设置 / 留空（`""`）→ 该协议禁用**：本上游不直连服务此协议。请求不能直达；provider 目录描述符不把它算进 endpoint 能力，路由转译到上游实际直连的某条协议，或一条都不可达时按既有能力缺失形态失败。Claude 请求在此上游上若没有直连消息腿，则 `count_tokens` 也不走上游，回落到估算（见 §3）。
- **设置 `true` → 该协议启用**，直连地址 = `api_base_url` 拼接该协议的标准路径（Anthropic 的 `/v1/messages` 要做 `/v1` 剥离；`/responses`、`/chat/completions` 除外）。
- **设置字符串 URL → 该协议启用**，直连地址 = 该完整 URL **原样**（不再对 Anthropic 做 `/v1` 剥离）。字符串非空且非 `true`/`false` 时必须是合法绝对 HTTP(S) URL，否则配置校验失败（规则同 `api_base_url`）。

**每个字段本质是三态开关**：未启用是可留空的，启用时要么回退到 base+标准路径（`true`），要么显式写死地址（URL 字符串）。

### 2.1 默认值（用户裁决，破坏性变更）

三个字段**默认全部禁用**。现有 sub2api 配置若不显式声明任一 endpoint，则该上游目录里的模型没有任何可直接通达的 endpoint，路由对该 provider 呈现既有能力缺失形态（`CapabilityMissing` / `UnknownModel`），`count_tokens` 不走上游。「启用」必须显式声明。旧的「默认三者全直连」行为被有意移除，这是本裁决的核心：为的是让「这个上游到底直连服务什么」成为配置里看得见的事实，而不是被硬编码默认悄悄假定。

## 3. 对 endpoint 能力集合与直连地址的作用

provider 目录回退的 endpoint 能力集合：

- 目录提供了 `supported_endpoints` 时：`解析出的 known endpoints ∩ 配置启用的 {三种聊天协议}`，再 ∪ 目录里不受控制的端点（embeddings）。`unknown_endpoints` 原样保留。
- 目录没有提供 `supported_endpoints` 时：回退为「配置启用的协议集合」（替换旧的默认全三）。

交集正是「目录广告 ∩ 配置声明」：目录告诉本代理上游自称提供什么，配置声明本代理信任哪几条、各在哪个地址。两者都不足以单独作为可直接路由的依据。

`count_tokens` 的直连腿只在目标格式为 Anthropic Messages（即该请求是一条可路由的无 `translation_required` 直连消息腿）时走 `provider.count_tokens`，这正是 `anthropic_messages_endpoint`「同时控制 count_tokens」的落点。其 URL = `anthropic_messages_endpoint` 解析出的地址再拼 `/count_tokens`。

`false`（显式布尔假）与留空等价：禁用。

三个字段与 `api_base_url` 一样**不支持热重载（需重启）**：直连地址在上游客户端构建时定下，改动需重启生效。

## 4. 接线

`send`、`fetch_models`、`count_tokens` 三条通路都要用每条协议解析出的上游地址，而不是旧的「base 拼接硬编码路径」：

- `send(endpoint, …)`：按 endpoint 查配置 → `true` 走 `base_url + 标准路径`（Anthropic 做 `/v1` 剥离）；字符串 URL 直接用；留空/`false`/未配置在 descriptor 层已由 `require_endpoint` 拦下（本变更不新增网络往返去探测可用性）。
- `fetch_models`：仍走 `base_url + /models`，不受三个 endpoint 字段影响——模型发现是 base 层的事，即使某条生成协议挂在别处。
- `count_tokens`：直连地址 = anthropic endpoint 解析结果拼 `/count_tokens`；anthropic endpoint 未启用时无该直连腿。

## 5. 验收要点

- 三个字段各自可独立取省略/`""`/`true`/合法绝对 URL；非空非 URL 字符串、`false`、非法 URL 的行为符合 §2/§3。
- 目录广告与配置启用的交集正确：广告了但配置禁用的协议从能力中移除，模型退化为只剩配置启用的那几条；目录没广告时回退为配置启用集合。
- `count_tokens` 只在 anthropic 直连时走上游，URL 正确（`true` 时 `base_url/v1/messages/count_tokens`；字符串时「字符串 + /count_tokens」）。
- 破坏性默认成立：什么都不配的 sub2api provider，其模型无通达能力，`count_tokens` 回落估算。

## 6. 条款修订记录

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-09-08 | 全篇 | 首稿 | 用户 2026-09-08 裁决三分 endpoint 语义与破坏性默认 |