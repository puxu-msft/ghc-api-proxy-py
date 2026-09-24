# bridge model provider 上游 endpoint 配置规格

状态：**DRAFT — 待实现与复评**。上游 provider（`app.model_provider.openai_compatible`）已合入 `main`（`10459e4c` 引入、`42fb2329` 接上 token 计数），但此前只用单一 `api_base_url` 并默认把三个原生协议当作全部直连。本规格把「这个上游直连服务哪些协议、各在哪个地址」拆成三项可独立配置的字段，并把默认改成显式声明。首版记录用户 2026-09-08 的裁决。

**这份是 Spec**，答「应该是什么样」，规范性。**活文档，不冻结。** 新裁决、实测或发现与本文冲突或限定它时当场修订，修订记入 §6。权威永远是当前版本。

## 1. 背景

bridge 上游原生服务多条协议：Anthropic Messages、OpenAI Responses、OpenAI Chat Completions，另有一条不受本文门控的 OpenAI Embeddings。不同 bridge 上游实现的能力不同，并非每个都原生实现这三条协议，所以不一定都能走直连路径。单一 `api_base_url` 加硬编码路径、且默认三者全直连的旧模型，无法表达「某个上游只原生服务 Responses、不服务 Anthropic Messages」这类部署。

本文把直连能力与地址拆成三个可独立配置的上游 endpoint 字段。

## 2. 配置字段（用户裁决 2026-09-08）

`model_providers.<name>`（type `bridge`）新增三个可选字段：

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

三个字段**默认全部禁用**。现有 bridge 配置若不显式声明任一 endpoint，则该上游目录里的模型没有任何可直接通达的 endpoint，路由对该 provider 呈现既有能力缺失形态（`CapabilityMissing` / `UnknownModel`），`count_tokens` 不走上游。「启用」必须显式声明。旧的「默认三者全直连」行为被有意移除，这是本裁决的核心：为的是让「这个上游到底直连服务什么」成为配置里看得见的事实，而不是被硬编码默认悄悄假定。

### 2.2 上游鉴权头（用户裁决 2026-09-16）

鉴权由**协议**决定，不由 provider 决定：

| 腿 | 默认鉴权头 |
|---|---|
| Anthropic Messages（含 `count_tokens`） | `x-api-key: <api_key>` |
| OpenAI Chat Completions / Responses / Embeddings | `Authorization: Bearer <api_key>` |
| `GET /models` | `Authorization: Bearer <api_key>` |

理由是 Anthropic Messages 腿是一条 Anthropic API，`x-api-key` 是它的规范鉴权头。此前 bridge 对三条协议一律发 `Authorization: Bearer`，对只认 `x-api-key` 的上游必然失败——opencode Zen 实测回 `401 AuthError "Missing API key."`，这正是 2026-09-16 那组 `provider=opencode`、`path=/v1/messages` 的 401。`api_key` 为空时不发任何鉴权头。

两个可选布尔字段在此默认之上**追加**头：

| 字段 | 默认 | 作用 |
|---|---|---|
| `add_header_authorization` | `false` | 在 Anthropic Messages 腿上**额外**发 `Authorization: Bearer <api_key>`。OpenAI 腿本来就发 Bearer，该字段对它们无作用。 |
| `add_header_x_opencode_session` | `false` | **所有腿**额外发 `x-opencode-session: <会话标识>`，供按会话路由或缓存的网关使用。取值优先本次请求的会话 identity（由客户端会话头解析而来），没有时回落到该 client 一个进程内稳定的 id。 |

这两个头与 `api_key` 同由 client 持有，**不支持热重载（需重启）**；调用方也**无法**通过 `extra_headers` 覆盖这三个头中的任何一个。

实测依据（2026-09-16，opencode Zen Go 档）：`/zen/go/v1/messages` + `Authorization: Bearer` → `401 AuthError "Missing API key."`；同路径 + `x-api-key` → 过鉴权；三条协议缺 `x-opencode-session` → `400 MissingSessionID`；三者齐备 → 200。

### 2.3 本地模型信息（`model_info_json`，用户裁决 2026-09-16）

有些 bridge 上游的 `/models` 只报 id：opencode Zen Go 档返回 `{id, object, created, owned_by}`，没有名称、能力、上下文长度或价格。路由不受影响（能力只问配置与目录的 endpoint），但**面向客户端的每一处目录投影都是空的**——`/models` 没有上下文窗口与价格，`?format=pi` 也没有 `contextWindow`、`cost`、`api`。这类事实由运维掌握，所以写进一个本地文件。

| 字段 | 默认 | 作用 |
|---|---|---|
| `model_info_json` | `""` | 本地模型信息文件的路径。留空 → 上游目录原样采信。提供 → 该文件与上游 `/models` 取**交集**。 |

**交集是这条裁决的核心**，且两边都无法单独给答案：上游广告了文件没描述的模型，文件也点名了上游不服务的模型。剩下的才是运维**既确认过、又描述过**的集合。

- 交集内条目 = 上游条目 ← 文件条目合并：映射**逐键合并**（文件为准，上游已发布的同级键保留），其余值（标量、列表）由文件整体覆盖。列表是整体替换而非追加——`supported_endpoints` 是一组声明，不是累加计数器。
- 上游广告但文件未描述 → 不服务：不出现在 `/models`，`describe` 返回 `None`。
- 文件描述但上游未广告 → 同样不服务。
- 合并后的条目**写回 raw catalog**：`/models` 的元数据直接读自它，否则交集只会决定哪些 id 可路由，而每一条描述仍和上游一样空。

文件在 provider **构造时读一次**。不可读、JSON 非法、`schema_version` 不符、`models` 为空、模型 id 为空或带首尾空白、条目不是对象——任一都让**构造失败**（`ModelInfoError`），不降级成「裸目录」：默默继续会让运维盯着上游那套空描述，还以为文件生效了。

与 `api_base_url` 一样**不支持热重载（需重启）**。路径与其他路径字段同一套展开：`~`、`$VAR`、`${VAR:-fallback}`，外加包位置变量 `${GHC_PACKAGE_DIR}`（见下）；写在配置文件里的相对路径相对**配置文件所在目录**解析。

**`${GHC_PACKAGE_DIR}` 记的是本包的位置**，即 `importlib.resources.files('app')` 所在的目录。它的存在是因为 uvx 运行没有 checkout：包躺在隔离缓存的 site-packages 里，`contrib/` 对这类用户根本不存在，而包内文件随 wheel 发布、无论可编辑安装还是隔离安装都能解析。它不是环境变量——同名环境变量也不会覆盖它，包位置只有一个事实来源。典型写法：

```yaml
model_info_json: "${GHC_PACKAGE_DIR}/model_provider/opencode-go-20260916.json"
```

文件格式（`schema_version: 1`）：

```json
{
  "schema_version": 1,
  "source": "出处（可选）",
  "retrieved_at": "2026-09-16（可选）",
  "models": {
    "kimi-k3": {
      "name": "Kimi K3",
      "supported_endpoints": ["/chat/completions", "/v1/messages"],
      "capabilities": {
        "supports": { "vision": true, "reasoning_effort": ["high"] },
        "limits": { "max_context_window_tokens": 1048576, "max_output_tokens": 131072 }
      },
      "pricing": { "input": 3.0, "output": 15.0, "cacheRead": 0.3, "cacheWrite": 0.0 }
    }
  }
}
```

条目字段就是**目录条目的形状**（`/models` 读的同一形状），所以合并下游不需要任何转换层：`capabilities.supports`、`capabilities.limits`、`supported_endpoints`、`pricing`（键名 `input`/`output`/`cacheRead`/`cacheWrite`，与 `_pi_cost` 一致）。

**分段定价写进 `pricing.tiers`**，形状与 `copilot_pricing.json` 一致：`tiers[0]` 是 `name: "default"` 的基础档，其后每档带 `input_min_tokens`（阈值，`_pi_cost` 据此算出 pi 的 `inputTokensAbove = min - 1`）。**每档都必须四档费率齐全**——`_pi_cost` 缺一个就丢掉**整个** `cost` 块，不是降级，所以上游没报的缓存费率要写成显式 `0`，留空会让这个模型看起来免费。

**`retrieved_at` 是出处，不是门槛。** 采样日期只用于判断新旧：超过 `MODEL_INFO_MAX_AGE_DAYS`（90 天）时**告警**，并在 `/api/status` 的 `providers.<name>.model_info` 里报 `{path, retrieved_at, age_days, stale}`；**不阻止启动**——目录与价格会漂移，但为了一个日期把能用的部署弄挂是另一回事。日期读不出来（缺失/非法/未来）→ 只告警，`stale` 报 `null` 而不是 `false`：`false` 会被读成「已核实」，而 `age_days: 0` 会被读成「今天采的」，两者都不是未知。

固定采样文件**文件名带日期**（`opencode-go-20260916.json`）：样本是一天一次的测量，带日期让 `ls` 就能看出新旧；代价是重新采样后要改 `model_info_json` 并重启（它不在热重载集合内）。

**只写确有把握的字段。** 尤其 `capabilities.tokenizer` 不能填：它连着 `max_prompt_tokens`，一起构成 `prompt_token_limits`，那是 local Responses 准入的事实。文件里编一个 tokenizer 就是伪造准入依据。

仓库随带一份 opencode Go 的现成文档，它**住在包里**：`src/app/model_provider/opencode-go-20260916.json`（2026-09-16 探测生成，含 30 个模型，随 wheel 发布）。它**不随包自动加载**，也不存在任何隐式默认——与 §2.1 同一条理由：用哪个文件必须是配置里看得见的事实。配置用包位置变量直接引用它，无需复制：

```yaml
model_info_json: "${GHC_PACKAGE_DIR}/model_provider/opencode-go-20260916.json"
```

**滚动别名要在文件里说清。** opencode Go 的 `/models` 广告 `deepseek-flash`，而 models.dev 的 `opencode-go` registry 里没有这个 id——但它不是「未知模型」：models.dev 的 `deepseek/deepseek-flash` 条目名字就叫 **DeepSeek V4.1 Flash**，limit 与费率与 `deepseek-v4.1-flash` 逐项相同，即上游的 `deepseek-flash` 是「最新 Flash」的滚动指向。所以文件里这一条镜像同上游 `deepseek-v4.1-flash` 的 `name`/`description`/`capabilities`/`pricing`，`supported_endpoints` 则保留该 id **自己**探测出来的结果，并在 `description` 里写明这是滚动别名。这比 pin 到具体版本更贴合上游语义：请求仍发 `deepseek-flash`，上游换指时跟着走；代价是文件里的元数据会**漂移**——这正是采样日期与 90 天告警存在的理由。若要反过来 pin 到具体版本，用既有的 `model_mappings`（`deepseek-flash: deepseek-v4.1-flash`）：映射名会继承目标模型的元数据（`tests/int/test_pipeline_ops_routes.py::test_an_model_alias_preserves_metadata_from_its_upstream_target` 断言了这点），代价是上游换指后仍钉在旧版本。

文档内容另有两处已知缺口，一并记在此处以免被当成完整事实：17/30 有 `reasoning_effort` 阶梯，其余上游只报 `toggle`（无从补全，`?format=pi` 的 `reasoning` 也因此为 `false`）；4 个模型（`qwen3.6-plus`、`qwen3.7-max`、`qwen3.7-plus`、`qwen3.8-max`）上游报的是 `budget_tokens` 上限，落在 `capabilities.supports.max_thinking_budget`。**该字段是描述性的**：按 `model_provider/types.py`，预算上限不是「接受 `budget_tokens`」的证据，那只有 `adaptive_thinking` 能回答，本项目也没有从它推断 `reasoning`。

## 3. 对 endpoint 能力集合与直连地址的作用

provider 目录回退的 endpoint 能力集合：

- 目录提供了 `supported_endpoints` 时：`解析出的 known endpoints ∩ 配置启用的 {三种聊天协议}`，再 ∪ 目录里不受控制的端点（embeddings）。`unknown_endpoints` 原样保留。
- 目录没有提供 `supported_endpoints` 时：回退为「配置启用的协议集合」（替换旧的默认全三）。

交集正是「目录广告 ∩ 配置声明」：目录告诉本代理上游自称提供什么，配置声明本代理信任哪几条、各在哪个地址。两者都不足以单独作为可直接路由的依据。

§2.3 的合并**先于**本节：配置了 `model_info_json` 时，上面说的「目录」指的是**合并后**的条目，所以 `supported_endpoints` 可能来自本地文件而不是上游。上游不广告 endpoint 的模型（opencode Zen 的全部模型）因此第一次有了逐模型的协议声明。配置门控的交集规则一字未改——文件说某模型服务 Anthropic Messages、而运维没启用 `anthropic_messages_endpoint`，该腿依然不可达。

`count_tokens` 的直连腿只在目标格式为 Anthropic Messages（即该请求是一条可路由的无 `translation_required` 直连消息腿）时走 `provider.count_tokens`，这正是 `anthropic_messages_endpoint`「同时控制 count_tokens」的落点。其 URL = `anthropic_messages_endpoint` 解析出的地址再拼 `/count_tokens`。

`false`（显式布尔假）与留空等价：禁用。

三个字段与 `api_base_url` 一样**不支持热重载（需重启）**：直连地址在上游客户端构建时定下，改动需重启生效。

## 4. 接线

`send`、`fetch_models`、`count_tokens` 三条通路都要用每条协议解析出的上游地址，而不是旧的「base 拼接硬编码路径」：

- `send(endpoint, …)`：按 endpoint 查配置 → `true` 走 `base_url + 标准路径`（Anthropic 做 `/v1` 剥离）；字符串 URL 直接用；留空/`false`/未配置在 descriptor 层已由 `require_endpoint` 拦下（本变更不新增网络往返去探测可用性）。
- `fetch_models`：仍走 `base_url + /models`，不受三个 endpoint 字段影响——模型发现是 base 层的事，即使某条生成协议挂在别处。
- `refresh_catalog`：拿到目录后按 §2.3 合并（交集 + 条目合并），再由合并后的条目建描述符并写回 raw catalog。刷新「有无变化」比较的是**合并后**的目录：拿上游原始负载与合并结果相比，等于配了文件之后每次定时刷新都报「变了」。
- `count_tokens`：直连地址 = anthropic endpoint 解析结果拼 `/count_tokens`；anthropic endpoint 未启用时无该直连腿。
- 鉴权头按 §2.2 由**协议**决定，与地址解析相互独立：`send` 与 `count_tokens` 在 Anthropic Messages 腿上发 `x-api-key`，OpenAI 腿与 `fetch_models` 发 Bearer。

## 5. 验收要点

- 三个字段各自可独立取省略/`""`/`true`/合法绝对 URL；非空非 URL 字符串、`false`、非法 URL 的行为符合 §2/§3。
- 目录广告与配置启用的交集正确：广告了但配置禁用的协议从能力中移除，模型退化为只剩配置启用的那几条；目录没广告时回退为配置启用集合。
- `count_tokens` 只在 anthropic 直连时走上游，URL 正确（`true` 时 `base_url/v1/messages/count_tokens`；字符串时「字符串 + /count_tokens」）。
- 破坏性默认成立：什么都不配的 bridge provider，其模型无通达能力，`count_tokens` 回落估算。
- Anthropic Messages 腿默认发 `x-api-key` 且**不发** `Authorization`；`add_header_authorization: true` 时两者都发；OpenAI 腿始终发 Bearer 且不发 `x-api-key`。
- `add_header_x_opencode_session: true` 时所有腿都带 `x-opencode-session`，取值为本次请求的会话 identity；未开启时该头不出现。
- 调用方 `extra_headers` 覆盖不了 `x-api-key`、`Authorization`、`x-opencode-session` 三个头。
- 交集成立：上游广告而文件未描述的模型不出现在 `/models`，`describe` 为 `None`；文件描述而上游未广告的同样不出现。
- 合并成立：文件没提到的上游键（`object`、`created`）保留；文件声明的标量覆盖；嵌套映射逐键合并；列表整体替换。
- `/models` 与 `?format=pi` 都反映合并后的 `name`、`capabilities.limits`、`pricing`、`supported_endpoints`（`?format=pi` 出 `contextWindow`、`maxTokens`、`cost`、`api`）。
- `models` allowlist 与交集**同时**生效时，`/models` 不列出被 allowlist 挡掉的模型（过滤发生在记入「已服务」之前）。
- 文件不可读、JSON 非法、`schema_version` 不符或 `models` 为空 → provider 构造失败，不降级为裸目录。
- 目录内容未变的定时刷新报告「无变化」。
- `retrieved_at` 超过 90 天 → 告警且正常加载；`/api/status` 的 `providers.<name>.model_info` 报 `{path, retrieved_at, age_days, stale}`；日期缺失/非法/未来 → 告警且 `stale` 为 `null`（不是 `false`）。
- 未配置 `model_info_json` 的 provider 不在 `/api/status` 里出现 `model_info` 键。
- 分段定价进 `pricing.tiers`，每档四档费率齐全（含显式 `0`），`?format=pi` 出 `cost.tiers[].inputTokensAbove`。

## 6. 条款修订记录

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-09-08 | 全篇 | 首稿 | 用户 2026-09-08 裁决三分 endpoint 语义与破坏性默认 |
| 2026-09-13 | 全篇 | 公共 provider type 从 `sub2api` 更名为 `bridge`；实现仍复用 OpenAI-compatible provider。 | 用户 2026-09-13 裁决「使用公共 type: bridge」 |
| 2026-09-16 | §2.2、§4、§5 | Anthropic Messages 腿默认鉴权头由 `Authorization: Bearer` 改为 `x-api-key`；新增 `add_header_authorization`、`add_header_x_opencode_session` 两个追加开关。 | 用户 2026-09-16 裁决「先止血」+ opencode Zen Go 档实测 |
| 2026-09-16 | §2.3、§3、§4、§5 | 新增 `model_info_json`：以本地文件与上游 `/models` 的**交集**为准，并把文件条目合并进目录，补全上游不提供的名称、能力、上下文长度、价格与逐模型协议；合并结果写回 raw catalog。 | 用户 2026-09-16 裁决「上游不提供模型信息，我们自己内置并补全，以它和 `/models` 的交集为准」+ opencode Zen 目录实测 |
| 2026-09-16 | §2.3、§5 | 快照进包（`src/app/model_provider/opencode-go-20260916.json`，随 wheel 发布）并新增 `${GHC_PACKAGE_DIR}` 包位置变量：uvx 运行没有 checkout，`contrib/` 对它不存在，配置用该变量直接引用包内快照，无需复制。 | 用户「应该使用某种变量，记为本包的位置，从而支持 uvx 运行」 |
