# 真实生产流量中的请求特性处理缺口

## 范围、快照与方法

本报告只分析用户指定的活跃 history 库 `/home/xp/.local/share/copilot-api/history-v3-20260818-044224.db`，每次均以 `file:/home/xp/.local/share/copilot-api/history-v3-20260818-044224.db?immutable=1` 打开。库在分析期间继续增长；因此以用户给出的 429 次操作为冻结集合，即按 `created_at` 升序的前 429 条，截止 `2026-08-18T16:42:30.909Z`。该集合的 SQL 复核输出为 `generation=422`、`count_tokens=7`，与用户给出的 422＋7 口径相符。

`v3_operations.manifest_gz`、`v3_objects.canonical_gz` 和 `v3_tracks.track_gz` 均用 zstd 解压为 JSON。请求体取每个 operation 的 ingress `payload:0`，并按 `payloadSequences`、`v3_sequence_nodes` 重建 `messages`、`system` 与 `tools`，再应用 overlay。所有以下计数都经过两条独立遍历复核：第一条按字段结构遍历，第二条通用递归 JSON walker 遍历；例如 `thinking` 的两条计数均为 65537，且 429 个 payload sequence 的声明长度与重建长度均一致。

以下“新链”只指 `/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py`、`server/pipeline_app.py`、`server/inbound.py`、`pipeline/`、`transform/` 与其实际调用的转换器。不把 `/home/xp/src/ghc-api-proxy-py/src/app/routes/`、`src/app/delivery/` 的 `--fd` 旧链当作新链实现证据。

## 1．Ingress 请求体中实际出现的结构

| 结构 | 出现请求数／结构实例数 | 实际值或形态 | 证据 |
|---|---:|---|---|
| `system[].cache_control` | 421／842 | 每个实例均为 `{"type":"ephemeral"}`；`ttl` 出现 0 次 | 上述重建＋双遍历输出；第二条通用 walker 得到 `system=842` |
| `messages[].content[].cache_control` | 421／421 | 每个实例均为 `{"type":"ephemeral"}`；`ttl` 出现 0 次 | 同上；通用 walker 得到 `messages.content=421` |
| `tools[].cache_control` | 0／0 | 无 | 同上 |
| 所有 `cache_control` | 421／1263 | 唯一值为 `{"type":"ephemeral"}`；没有 `ttl` | `842 + 421 = 1263`，并由通用 walker 的值聚合复核 |
| 非空 `tools` | 421／9467 个 tool definition | 所有 definition 都没有 `type` 字段，也没有 `defer_loading` 字段 | 重建 payload 的 schema-aware 统计；独立的 generic walker 未发现该字段 |
| `tools[].type` | 0／0 | 9467 个 definition 均为字段缺失，而不是 `type: "function"` 或其它值 | 同上 |
| `tools[].defer_loading` | 0／0 | 9467 个 definition 均为字段缺失，而不是显式 `false` | 同上 |
| 顶层 `tool_choice` | 0／0 | 无 | 429 个 rehydrated ingress body 的顶层键统计 |
| message `image` block | 0／0 | 无 | message content block 的双遍历 |
| message `document` block | 0／0 | 无 | message content block 的双遍历 |
| message `thinking` block | 418／65537 | 存在于历史消息内容中 | 两种独立计数均为 65537；sequence 长度 0 mismatch |
| message `redacted_thinking` block | 0／0 | 无 | message content block 的双遍历 |

429 条里有 421 条带正常 generation 形状的 `context_management`，而不是 422 条：剩余一条 generation 是用户已说明的“移除 `context_management` 后返回 200”的控制请求。其余常规字段与用户已经核实的基线一致，即 `thinking={"type":"adaptive"}`、`output_config={"effort":"high"}`、`max_tokens=128000`、`stream=true`。`count_tokens` 的 7 条本来就使用较小的计数请求形状，不能与 generation body 混为同一种顶层 schema。

作为替代目标的对照，history 的 existing proxy `payload:1`／`payload:2` 并非总是简单原样复制 tool：在该冻结集合中，它们出现 4671 个 `defer_loading:true`、345 个显式 `defer_loading:false`、497 个 `type:"function"` 及 345 个 `type:"tool_search_tool_regex_20251119"`。这说明 ingress 中“无 `type`、无 `defer_loading`”不是可以安全忽略的空白，而是现有代理会补充或转换的生产输入形态。

## 2．客户端 HTTP 请求头：库确实记录了，且包括 `anthropic-beta`

结论不是“库里不记录请求头”。每条 operation 的 `v3_tracks` 都有 `client-ingress` track，并在其 track JSON 中存有 `headers` 的 `[name, value]` 列表。429 条均有该 track；另外 `upstream-request`、`upstream-response`、`upstream-egress` 与 `client-egress` 也各有 429 条 header-bearing track。`manifest.record.dispatches[].diagnostics[].data.headers` 则是上游响应诊断头，不是客户端 ingress 头。

客户端 ingress 的记录头名为：`accept`、`accept-encoding`、`anthropic-beta`、`anthropic-dangerous-direct-browser-access`、`anthropic-version`、`authorization`、`connection`、`content-length`、`content-type`、`host`、`user-agent`、`x-app`、`x-claude-code-session-id`、`x-stainless-*`；其中 `x-claude-code-agent-id` 出现 76 次，`x-stainless-timeout` 出现 422 次，其余上表所列基础头均出现 429 次。`authorization` 的值也被记录，但本报告不把 credential-bearing value 写入仓库文件。

`anthropic-beta` 的实际完整值只有以下三种，计数相加为 429：

| 请求模型／用途 | 次数 | `anthropic-beta` 实际值 |
|---|---:|---|
| `claude-opus-5` generation | 346 | `claude-code-20250219,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,effort-2025-11-24,fallback-credit-2026-06-01` |
| `gpt` generation | 76 | `claude-code-20250219,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,effort-2025-11-24` |
| `claude-opus-5` `count_tokens` | 7 | `claude-code-20250219,interleaved-thinking-2025-05-14,context-management-2025-06-27,token-counting-2024-11-01` |

命令证据：对冻结集合解压 `v3_tracks.track_gz` 并按 `track_name='client-ingress'` 聚合，输出 `anthropic-beta:429`；再按 `(payload:0.model, beta value)` 分组，输出为 `346/76/7` 三组。该分组与 header-value 聚合的三种值及总数 429 交叉一致。

## 3．新链逐项对照与实在缺口

新链入口只读取 JSON body：`/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:40-55` 调用 `request.json()` 后把 `body` 交给 `build_context`。`/home/xp/src/ghc-api-proxy-py/src/app/server/inbound.py:58-83` 只保存 model、stream 与 payload；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/request.py:50-69` 的 `RequestContext` 没有 headers 字段。因此下表中“原样穿透”是实际调用路径的结论，不是只凭关键词的猜测。

| 真实特性 | 新链处理证据 | 缺口判定 |
|---|---|---|
| `context_management` | Anthropic translator 仅把其列为未声明 extension：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/anthropic_messages.py:44-48`。Responses writer 在最后 `payload.update(request.extensions)`：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py:81-98`。`handle` 对需要转换的路由调用该 translator：`/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py:71-82`。 | **已由实测证实的阻断缺口。** 对 Responses 路由会把 Anthropic 字段原样送往上游；用户已实测其导致 `context_management: Extra inputs are not permitted` 的上游 400，并被包装为 502。 |
| 顶层 `thinking={"type":"adaptive"}` 与 `output_config={"effort":"high"}` | 都未列入 Anthropic translator 的 `_PASSTHROUGH_KEYS`，所以同样进入 extensions：`anthropic_messages.py:12-14,44-48`；Responses writer 再无条件重放 extensions：`openai_responses.py:97`。 | **实际流量已触发的转换缺口。** 新链没有把 Anthropic adaptive thinking／effort 映射为 Responses 的 reasoning／对应控制字段，而是发送 Anthropic 顶层键。未对这些键另做上游 400 断言，因为本轮只获得了 `context_management` 的实测拒绝。 |
| `system` 与 `messages` 的 `cache_control` | `system_blocks_from_value` 显式把除 `text`／`type` 外的 metadata 留在 block：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/semantic.py:61-85`；Responses writer 又把 metadata 直接置于 `instructions[].content[]`：`openai_responses.py:83-88`。messages 则由 `_dict_list` 原样复制：`anthropic_messages.py:17-21,30`，再作为 `input` 原样送出：`openai_responses.py:81-82`。 | **实际流量已触发的语义转换缺口。** 1263 个 Anthropic `cache_control` 会保留在 Responses-shaped body 中，没有 feature mapping，也没有基于 `ttl` 选择 capability/header 的新链逻辑。`ttl` 当前为 0，故 extended TTL 是未触发的后续面，而不是本样本已发生的输入。 |
| 标准 tools 缺少 `type`／`defer_loading` | 新 translator 原样复制 tools：`anthropic_messages.py:27-32`；Responses writer 原样赋给 `payload["tools"]`：`openai_responses.py:89-90`。发出路径由 `DirectDriver._send` 直接调用 provider：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:216-230`。虽有 `preprocess_tools` 会补 `defer_loading`：`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/message_tools.py:6-30`，但其唯一调用者是旧 `app.anthropic.client` 的 `prepare_anthropic_request`：`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:12,134-151`；新链没有调用它。 | **实际流量已触发的阻断候选。** 9467 个生产 tool definition 无 `type`／`defer_loading`，而新链没有采用现有的预处理，也没有把 Anthropic `input_schema` 转成 Responses function tool schema。history 的 effective/wire payload 已证明现有代理会为同类输入增补这些字段。是否被具体 Responses upstream 拒绝尚未用新链实发验证。 |
| 65537 个历史 `thinking` block | Anthropic message list 被原样复制到 `SemanticRequest.messages`：`anthropic_messages.py:30`，并直接成为 Responses `input`：`openai_responses.py:81-82`。旧代码中确有 `thinking`／`redacted_thinking` helper，例如 `/home/xp/src/ghc-api-proxy-py/src/app/anthropic/thinking/protection.py:4,43-55`，但搜索新链调用路径没有找到从 `server/handler.py`、`pipeline_app.py`、`pipeline/` 或 `transform/` 到这些 helper 的调用。 | **实际流量已触发的转换缺口。** 新链没有把 Anthropic reasoning carrier／thinking block 转为 Responses reasoning input，也没有在转换边界保留协议所需的适配。这里不把旧 helper 的存在误报为新链已处理。 |
| `redacted_thinking` | 当前请求次数／实例数均为 0。代码可以识别该 type：`thinking/protection.py:4,43-55`，但不在上述新调用路径内。 | 当前样本未触发；新链没有可见的专用转换点。 |
| `image`／`document` content block | 当前请求次数／实例数均为 0。搜索范围为 `/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py`、`server/pipeline_app.py`、`server/inbound.py`、`pipeline/`、`transform/`、`anthropic/`，关键词为 `image`、`document`；未找到新请求转换器的 block-type mapping。messages 的原样复制位置如上。 | 当前样本未触发；不能作为已发生故障报告，但新链没有把 Anthropic block shape 转为 Responses input item 的处理点。 |
| `tool_choice` | 当前请求次数为 0。它同样不在 `_PASSTHROUGH_KEYS`，故若出现会进入 extensions：`anthropic_messages.py:12-14,44-48`，并在 `openai_responses.py:97` 原样重放。 | 当前样本未触发；存在未转换的潜在兼容面。 |
| 客户端 `anthropic-beta` 与其它 ingress headers | 新入口完全未读 `request.headers`：`pipeline_app.py:40-55`；context 无 header carrier：`pipeline/request.py:50-69`。`forward_request_headers` 只有定义和导出、没有调用点：`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/header_policy/__init__.py:68-92,123-126`。`build_anthropic_beta_headers` 只被旧 `prepare_anthropic_request` 调用：`anthropic/features.py:50-70` 与 `anthropic/request_preparation.py:17-63`。 | **实际流量已触发的明确缺口。** 429 个客户端 beta header 都在 history 中，但新链既不保存、也不转发、也不据其协商能力；更不会保留 10 个 production beta token 的组合差异。 |

补充：`/home/xp/src/ghc-api-proxy-py/src/app/models/anthropic.py:47-63` 的 `MessagesRequest` 能表达 `tool_choice`、`thinking`、`context_management` 与 tool metadata，但新链的正常 generation 入口不在这里进行 schema validation；该 model 只由 count-token 的 `_countable` 使用，见 `/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py:166-178`。因此“模型类型有字段”不能当作新链 feature handling 已存在的证据。

## 4．无配置时 `claude-opus-5` 与 `gpt` 的解析

已现场核对以下三个位置都不存在：`/home/xp/.local/share/ghc-api-proxy/config.yaml`、`/home/xp/.config/ghc-api-proxy/config.yaml`、`/home/xp/src/ghc-api-proxy-py/config.yaml`。以 `GHC_CONFIG`、`GHC_MODEL_MAPPINGS` 均 unset，且临时 XDG data/config 目录为空的方式运行 `load_proxy_config()`，输出为：

```text
model_mappings= {}
providers= ['ghc'] default= ghc
claude-opus-5 ModelResolution(requested='claude-opus-5', resolved='claude-opus-5', matched_key='', passthrough=True, hops=0)
gpt ModelResolution(requested='gpt', resolved='gpt', matched_key='', passthrough=True, hops=0)
```

这与 `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/config-schema-gap.md:63-68` 的裁决一致：没有内置 alias/default mapping。实现上，schema 的 mapping 默认空字典：`/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:235-245`；解析器在没有 mapping 命中且 catalog 未直接提供同名 model 时返回原请求名并标 `passthrough=True`：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/model_resolution.py:64-105`。

因此两者的行为相同，而不是 `claude-opus-5` 有特殊默认、`gpt` 有通配解析：都以原字符串进入 provider catalog。若刷新后的 catalog 没有完全相同的 id，`decide_route` 的 `provider.describe(...) is None` 分支抛 `UnknownModel`：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/routing.py:74-84`；`error_status` 将该 `ProviderError` 变成 HTTP 400：`/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py:197-212`。若 catalog 恰好有同名 id，则可直接解析，不需要 mapping。

本环境无法把最后一个“catalog 是否含该 exact id”的条件伪装成已证实：用同一无配置环境实际执行 startup 会调用 `refresh_catalogs()`，其启动期调用见 `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:122-143` 与 `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:215-225`。只读 catalog probe 的实际输出是 `RuntimeError: No GitHub token provider produced a usable token`，发生在 `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/github_copilot.py:93-109` 刷新凭据阶段；没有向 `127.0.0.1:4141` 发起连接、请求或信号。因此目前可确定的是“二者都 passthrough，随后严格依赖 exact catalog id”，不能诚实声称其中任何一个在此无凭据环境已经路由成功或被 UnknownModel 拒绝。

## 5．缺口清单

1. 已实测会失败：Responses 路由把 `context_management` 原样传上游，造成 400 后对客户端成为 502。
2. 已由生产样本触发、尚未逐项上游重放：`thinking`／`output_config`、1263 个 `cache_control`、9467 个无 type 的 tool definition，以及 65537 个 history thinking block 都在新链中缺少 Anthropic→Responses 的特性转换。
3. 已由生产样本触发：429 个 ingress `anthropic-beta` 及其它客户端 headers 被 history 记录，但新链入口丢弃它们；现有 header/helper 实现在旧 `app.anthropic.client` 调用路径，不在新链。
4. 仅潜在、当前样本为 0：`tool_choice`、image、document、`redacted_thinking`。它们不应被误报为当前生产故障，但也没有发现新链专用 mapping。
5. 无配置的模型名问题不是“自动映射失败”而是“原样 passthrough 后 catalog gate”。当前环境缺 GitHub token，catalog refresh 在监听请求前失败；若要判定两个 exact id 的最终 400／成功，必须在有可用 token 的隔离运行环境中刷新 catalog 后再测。

## 本轮结构怪味与反思

- `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/anthropic_messages.py:44-48` 与 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py:97`：怪味是将跨协议的未建模 Anthropic 请求字段统一标成“extension”并无条件注入 Responses wire body。处置：本轮不修改代码，作为本报告的核心缺口，因为用户要求只写报告。
- `/home/xp/src/ghc-api-proxy-py/src/app/anthropic/message_tools.py:6-30` 与新链 `DirectDriver._send` 的 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:216-230`：怪味是已有 tool preprocessing 与实际新链 dispatch 脱节。处置：本轮不修改代码，记录为生产输入已触发的缺口。
- 内部替代方案：已有旧链 `prepare_anthropic_request`／thinking helpers 不能直接证明新链可用，且直接复用也不能替代正确的 Anthropic→Responses transformer；本轮仅取证，不提出未经验证的实现方案。
- 判据判别力：body 重建用了两种遍历并检查 sequence length；headers 则从 `client-ingress` track 按值聚合，而非从上游 diagnostics 推断。已知局限是无凭据环境不能判定 catalog exact-id 是否存在，报告已明确降级。
- 第三方方案：本轮是事实与缺口审计，不新增手写机制或引入依赖；未评估第三方库，因为该问题的缺口首先在现有请求转换接线，而非缺少可替代的独立算法库。
