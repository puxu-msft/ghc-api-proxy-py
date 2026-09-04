# Anthropic 出站请求体：`thinking`、`output_config`、`messages` 末尾角色与 `cache_control` 子字段的构造

**这份是 Spec**，答「应该是什么样」，规范性。**这是活文档，不冻结。** 新的用户裁决、实测或发现一旦与本文任何一处冲突或限定它，**当场修订本文**——不把已知错误的条款留在原地，也不把修正寄存到延后台账或评审报告里。权威永远是本文的当前版本。

**范围**：**所有出站目标格式为 Anthropic Messages 的请求**，在 translation 之后的最终形状里，这几处：`thinking`、`output_config`、`messages` 的**末尾角色**、每个 `cache_control` 对象里**允许出现的键**、以及 `anthropic-beta` 请求头里**这个部署认识的 flag**。其余字段不在本文范围内。

**为什么一个请求头会进一份「请求体」的 Spec。** `anthropic-beta` 与 body 是同一件事的两面：一个 flag 的作用就是让某个 body 字段合法，而 §7.5 记的正是这两面对不上的那次实测。把它放进别处会让「上游不认这个键」和「上游不认这个 flag」这两条互相解释的条款分居两地。§7 因此是「上游的词汇表」，不是「body 的白名单」。

**`cache_control` 只管键，不管断点——而且只在运维选了对应档位时才管。** 断点放在哪里、放几个、归客户端还是归代理控制，那是 `hook_fix_anthropic_request.cache_control` 四档配置的管辖。本文只回答「一个 `cache_control` 对象里可以有哪些键」，并且**用户 2026-08-24 裁定这件事只在 `sanitize` / `disabled` 两档下发生；同日第二次裁定把默认档从 `passthrough` 改为 `sanitize`，而 `passthrough` 这一档本身仍是字面的原样转发**。四档中 `proxied` 仍未实现（启动即拒），见 §7.3 与 §9 A-9。

**为什么范围不是「直连腿」。** 首稿写的是 `translation_required == False`，而实现从第一天起就按 target format 判断——这不是实现越界，是首稿把范围写窄了。判据在于：能不能收 `thinking.type: enabled` 是**回答请求的那个模型**的属性，与这个请求体是客户端原样送来的还是翻译出来的无关。翻译到 Anthropic 的那条路今天真的会写出 `{"type":"enabled","budget_tokens":N}`（`pipeline/translation_driver/anthropic_messages.py` 的 `_restore_thinking`），它到了同一个端点会吃同一个 400。按腿切会让那半边无人认领，而 `attempt.prepare` 与 count 腿本来就都在 translation 之后运行，target format 才是它们共同的边界。

**仍然不在范围内**：Anthropic → Responses 方向的 reasoning 映射，那是 `anthropic-responses-bridge/spec.md` 的管辖。

**条款修订记录**：

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-08-24 | 全文 | 首稿 | 线上 400（§1），用户 2026-08-24 对 effort 来源与 `display` 处置的裁定（§4、§5） |
| 2026-08-24 | §2.1 | 补上正向实测：本文规定要发的那个请求体**被上游接受**。首稿只有「旧形状被拒」这一半，据以推断新形状可用——那是从上游的建议里读出来的，不是量出来的 | 双向探针（§2.1），负控制与正样本各一次真实调用 |
| 2026-08-24 | 范围声明 | 从「直连腿」改为「所有出站目标格式为 Anthropic Messages 的请求」。首稿把范围写窄了，而实现一直按 target format 判断，两者矛盾 | 实施评审 [reports/260824-implementation-review.md](reports/260824-implementation-review.md) ADTR-03 |
| 2026-08-24 | §4.0、§4.2 | 补上「客户端省略 `thinking` 时仍附 effort」，并给规则 4 补上目录只发布本地阶梯无法排序的名字时该怎么办——首稿两处都没说，实现于是各自替它做了决定 | 同上，ADTR-01 与 ADTR-02；`output_config` 单独发出被实测接受（§2.1） |
| 2026-08-24 | §9 A-1（当时编号 §8） | 原文说「当前实现按透传」，这在生产里不可达：`decide_route` 在 `describe` 返回 `None` 时直接抛 `UnknownModel`，根本不会生成 Route。改写为它实际是什么 | 同上，ADTR-05 |
| 2026-08-24 | 范围、新增 §6、§2.5 | 纳入 `messages` 末尾角色：**上游拒收以 assistant 结尾的对话，而本代理自己的两处修复会把请求改成那样**。同时记下一次**反向**实测——官方文档说 Claude 5 一族移除了 `temperature`/`top_p`/`top_k`，经 Copilot 实测**不成立**，不要为它们建守卫 | 字段探针矩阵（§2.5），以及对本项目 `repair_tool_pairs` / `drop_blank_text_blocks` 的可达性实测 |
| 2026-08-24 | §7.3 改写、§7.1 位置集合补全、§7.6～§7.8 新增 | **用户裁定 `passthrough` 字面成立**：白名单只在 `sanitize` / `disabled` 下运行，默认档一个字节都不动，因此默认配置面对 `scope` 仍会吃上游 400——那是被裁定的行为。首稿让白名单在每一档下都跑，论证是「四档管断点、本条管词汇表」，异源评审判为 blocker（「不要用当前 Spec 自己提出的解释代替裁决」），用户裁向字面一侧。同轮把位置集合从「三处」按官方 schema 补到七处（顶层与三处嵌套原先全漏），并把 `anthropic-beta` 的网关词汇表从待裁决条目升为正文条款 | 用户裁决 2026-08-24；异源评审 [reports/260824-cache-control-and-beta-implementation-review.md](reports/260824-cache-control-and-beta-implementation-review.md) CCBIR-01/02/03；跨模型实测（7 个 Claude 模型对 `scope` 全拒、对 `ttl` 全收，正控制全 200） |
| 2026-08-24 | 标题、范围、新增 §7，原 §7～§9 顺延为 §8～§10 | 纳入 `cache_control` 的**子字段白名单**：客户端发的 `cache_control.scope` 让上游整条请求 400，而**补发对应的 beta 救不回来**（网关收下该 beta，后端 schema 却不认它启用的字段）。同时记下一条防止误读的实测——`defer_loading` 与 `tool_search_tool_regex_*` 上游**不带 beta 也收**，所以剥掉那个 beta flag 不会引发二次 400 | 线上 400（§7）、[reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md](reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md)（正控制 + 反向对照各跑两遍） |

## 0. 一句话

**`thinking.type: enabled` 对 `adaptive_thinking` 模型是死路，改发 `adaptive`；`output_config.effort` 由 `model_thinking_effort` 配置给出，按目录发布的能力对齐。两边都已实测。**

## 1. 触发它的那次失败

2026-08-24 10:39:48，`req=530e0e10-c724-45a0-964a-129c3351646a`：

```
[FAIL] H1 400 POST /v1/messages claude-sonnet-4-5 → claude-sonnet-5 760ms
upstream: {"type":"error","error":{"type":"invalid_request_error","message":"\"thinking.type.enabled\" is not supported for this model. Use \"thinking.type.adaptive\" and \"output_config.effort\" to control thinking behavior."}}
```

**出站请求体已被 `observability/rejection_capture.py` 完整落盘**，这是第一手证据而不是重建：`~/.local/share/ghc-api-proxy/rejected/20260824T103948.240-400-530e0e10-c724-45a0-964a-129c3351646a.json`。它记着：

| 字段 | 值 |
|---|---|
| `requested_model` | `claude-sonnet-4-5` |
| `resolved_model` | `claude-sonnet-5` |
| `endpoint` | `/v1/messages` |
| `translation_required` | `false` |
| `route_reason` | `inbound_format_supported` |
| `payload.max_tokens` | `64000` |
| `payload.thinking` | `{"budget_tokens": 63999, "type": "enabled", "display": "omitted"}` |

两处值得单独记下，后面的条款都建立在它们上面：

- **`budget_tokens` 恰好等于 `max_tokens - 1`**。它是一个**派生数字**，不是深度偏好——客户端在说「不设上限」，不是在说「按最大深度思考」。把它当成一个花钱的旋钮读，会读出一个原文里没有的信号。这是 §4 不从 budget 推导 effort 的直接理由。
- **`display: "omitted"`**：客户端主动发了这个字段。它是 adaptive 形态上的合法字段（§2.3），不是噪声。

## 2. 上游契约

三个来源互相印证，权重从高到低：

### 2.1 上游自己的话，与双向实测（最强）

上面那条 400 的 `message` 就是上游对本条的直接表述：`claude-sonnet-5` 不接受 `thinking.type: enabled`，要用 `thinking.type: adaptive` 加 `output_config.effort`。

**但那只是「旧形状被拒」这一半。** 上游建议发什么，与它真的会接受什么，是两件事——把建议当成实测，是这类修复最容易走进去的坑：换一个 400 而已。所以 2026-08-24 又打了一对探针，经运行中的代理（当时跑的是**改动前**的代码，对 `thinking` 原样透传，因此它在这里只是个透明载体）打到真实上游，模型名 `claude-sonnet-4-5`，非流式，提示词一句话：

| 探针 | 发出的 `thinking` / `output_config` | 上游 |
|---|---|---|
| 负控制 | `{"type":"enabled","budget_tokens":4095,"display":"omitted"}` / 无 | **400**，`"thinking.type.enabled" is not supported for this model...`，与 §1 一字不差 |
| 正样本 | `{"type":"adaptive","display":"omitted"}` / `{"effort":"xhigh"}` | **200**，`"model":"claude-sonnet-5"`，`stop_reason":"end_turn"`，正常作答 |

**负控制是这对探针里更要紧的那个**：没有它，一个 200 只说明「这次没炸」，说不清是不是因为发对了。两条一起才说明这条判据分得开。

正样本同时顺带证实了两件本来只有文档背书的事：`display: "omitted"` 在 adaptive 形态上被接受，`output_config.effort: "xhigh"` 也被接受——后者恰是第一方客户端那段硬编码 `low|medium|high` 会静默吞掉的取值（§2.4）。

**这对探针没有证明什么**：它只覆盖了 `claude-sonnet-5` 这一个模型、非流式、一次调用。别的 `adaptive_thinking` 模型、流式、以及 `disabled` 形态都没有被这次实测覆盖，那几处仍然只有目录与文档背书。

### 2.2 模型目录（活数据，每次刷新可变）

Copilot 目录在 `capabilities.supports` 下发布两个相关能力位。快照见 `refs/available_models.json`：

| 模型 | `adaptive_thinking` | `reasoning_effort` | `min/max_thinking_budget` |
|---|---|---|---|
| `claude-sonnet-5` | `true` | `low, medium, high, xhigh, max` | 1024 / 32000 |
| `claude-opus-4.6` | `true` | `low, medium, high, max` | 1024 / 32000 |
| `claude-opus-4.7`、`claude-opus-4.8` | `true` | `low, medium, high, xhigh, max` | 1024 / 32000 |
| `claude-sonnet-4.6` | `true` | `low, medium, high, max` | 1024 / 32000 |
| `claude-sonnet-4.5`、`claude-opus-4.5`、`claude-haiku-4.5` | **缺席** | **缺席** | 1024 / 32000 |

**`adaptive_thinking` 是一个正向发布的位**：出现即为真，缺席即为「这个模型不是 adaptive 的」。注意 `min/max_thinking_budget` 在两类模型上都发布，所以**它不能用来判别**——`claude-sonnet-5` 一样发布 1024/32000，却拒绝 `budget_tokens`。判据只有 `adaptive_thinking`。

**目录是活的，本表是快照。** 判据必须每次从目录读，不得把上表写死进代码。

### 2.3 Anthropic 官方文档（`claude-api` skill，缓存于 CLI 版本）

- `budget_tokens` 在 Fable 5 / Opus 5 / 4.8 / 4.7 / Sonnet 5 上**已移除，发即 400**；在 Opus 4.6 / Sonnet 4.6 上是过渡逃生口，不用于新代码。
- `output_config: {effort: "low"|"medium"|"high"|"xhigh"|"max"}`，**GA，无需 beta 头**；**省略等价于 `high`**。
- `thinking.display` 是 adaptive 形态上的合法字段：`{type: "adaptive", display: "summarized"|"omitted"}`。`"omitted"` 是 Sonnet 5 一族的默认值。`display` 只控制可见性，思考照样发生、照样计费。
- `{type: "disabled"}` 在 Sonnet 5 上**被接受**。

### 2.4 第一方客户端（vscode-copilot-chat）——形状可抄，取值不可抄

`refs/vscode-copilot-chat/src/platform/endpoint/node/messagesApi.ts:144-176, 233-234` 与其单测 `test/node/messagesApi.spec.ts:728-825`：

```ts
if (endpoint.supportsAdaptiveThinking && !thinkingExplicitlyDisabled) {
    thinkingConfig = { type: 'adaptive' };            // 不带 budget_tokens
} else if (...endpoint.maxThinkingBudget && endpoint.minThinkingBudget) {
    thinkingConfig = { type: 'enabled', budget_tokens: thinkingBudget };
}
...
thinking: thinkingConfig,
...(effort ? { output_config: { effort } } : {}),   // 与 thinking 并列，互不相干
```

**它的分支判据可以采纳**（按 `adaptive_thinking` 分流），**它的 effort 取值不可以采纳**。同文件 `:172-176` 把 effort 硬编码成 `low|medium|high` 三项比较，而今天的目录已经给 `claude-sonnet-5` 发布了 `xhigh` 与 `max`——照抄会把「配了 `xhigh` 却静默不发 `output_config`」这个缺陷一起抄进来。该仓库已归档、代码停在 2026-04/05，而模型目录是活的；这条时效限定来自 `sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` §0 与 §8，必须与那份证据一并带走。

**本文的取法**：effort 的合法集合**只从目录读**，不硬编码（§4.2）。

### 2.5 字段探针矩阵：**哪些字段其实没问题**

2026-08-24，同一套探针，`claude-sonnet-4-5 → claude-sonnet-5`，非流式，一句话提示词，正控制先跑：

| 发出的东西 | 上游 |
|---|---|
| 什么都不加（正控制） | 200 |
| `temperature: 0.5` | **200** |
| `top_p: 0.9` | **200** |
| `top_k: 10` | **200** |
| 三个采样参数同时发 | **200** |
| `temperature` + `thinking: {type:"adaptive"}` | **200** |
| `temperature: 0` | **200** |
| 尾随 assistant 消息（`content` 为字符串） | **400** `This model does not support assistant message prefill. The conversation must end with a user message.` |
| 尾随 assistant 消息（`content` 为块数组） | **400** 同上 |
| `thinking: {type:"adaptive", budget_tokens: 4000}` | **400** `thinking.adaptive.budget_tokens: Extra inputs are not permitted` |
| `output_config: {effort: "turbo"}` | **400** `output_config.effort "turbo" is not supported by model claude-sonnet-5; supported values: [low medium high xhigh max]` |
| `output_config: {effort: "none"}` | **400** 同上形状 |

三条结论，都要一并带走：

1. **官方文档在这条路上不成立。** `claude-api` skill 的表写着 Fable 5 / Opus 5 / Sonnet 5 上 `temperature` / `top_p` / `top_k`「已移除，发即 400」。**经 Copilot 实测，三个都收。** 不知道上游是真的采纳还是收下即忽略——一个 200 不回答这个——但对「要不要建守卫」这个问题它是决定性的：**没有失败面，就不建守卫**。这条记在这里，是为了让下一个读到那张官方表的人不要去建三个没用的门。
2. **`budget_tokens` 必须删，不是顺手删的。** 只把 `type` 改成 `adaptive` 而留着 budget，照样 400，而且错在另一个字段上。§3.1 那条「并删去 `budget_tokens`」由此从「合理」升级为「实测必要」。
3. **目录就是 effort 的权威。** 上游的拒绝信息**直接列出了它支持的值**，`[low medium high xhigh max]`，与目录 `capabilities.supports.reasoning_effort` 逐字一致。§4.2 那条「目录发布了就原样发」因此有了上游自己的背书，而不只是本项目的推理。

**这套探针不覆盖什么**：只有 `claude-sonnet-5` 一个模型、只有非流式、每格一次调用。别的模型与流式没测。

## 3. `thinking.type`：主动式改写

### 3.1 条款

在 Anthropic 直连腿上，出站请求体 `thinking` 存在且是对象时：

| 客户端发的 `thinking.type` | 目标模型 `adaptive_thinking` | 出站 |
|---|---|---|
| `enabled` | `true` | **改写为 `adaptive`，并删去 `budget_tokens`** |
| `enabled` | 缺席 | 原样透传（该模型正是靠 `budget_tokens` 工作的） |
| `adaptive` | 任意 | 原样透传 |
| `disabled` | 任意 | 原样透传（§2.3：Sonnet 5 接受它） |
| 其他 / 非对象 / 缺席 | 任意 | 不碰 |

删去的 `budget_tokens` 记为一条 `LossCode.REASONING_INTENT_APPROXIMATED`，走既有的 `context.extras["conversion_losses"]` 通道，于是它出现在请求日志行与记录里，而不是无声消失。

### 3.2 为什么是主动式，不是反应式

`docs/.human-controlled/upstream-retry-and-continuation.md:9` 把 400 列进「无法继续」。若做成「收到这个 400 → 改写 → 重试」，字面上撞这一条；用户亲笔的 `config.example.yaml:315`（「部分 400 协商重试」）、`:546`（`strip_all_thinking_blocks_on_reject`）与 `:520-535`（注释态的 `message_role_system`，`proactive` + `reactive` 双开关）之间本就存在一处需要用户澄清的张力，**但那处张力不是本条引入的，也不需要本条去解决**：主动式在发送前就把请求构造对，根本不产生这个 400，于是完全不触碰那一条。第一方客户端也是主动式。

反应式（学习 + 重试）作为增强留在 §9 延后项里。

### 3.3 授权来源

`docs/.human-controlled/message-translation.md:7`：

> 对于直连路径，采用尽可能原样转发的原则。当我们需要理解和处理时，才分析和处理对应部分。

后半句与前半句写在同一句里，是授权而非例外。同族先例两个，都在跑：`message-format-reshape.md:37-49` 的按模型剥离 `anthropic-beta` flag，`:76-78` 的常驻剥离空 thinking 块——后者是用户亲笔把一条直连请求体改写从「可配置」升级为「常驻」。

## 4. `output_config.effort`：来自配置，按目录对齐

**用户 2026-08-24 裁定**：不从 `budget_tokens` 推导 effort；新增 `model_thinking_effort` 配置映射，按模型给值，并根据实际上游支持能力对齐。

**以下由这条裁定推导，不属于它**：没有配置项的模型不发 `output_config`（§4.2 规则 1）、客户端省略 `thinking` 时仍附 effort（§4.5）、以及规则 4 的对齐方向。它们是我方的派生规则，按本项目规则可凭评审共识修订，**不得被引用成用户已经关掉的问题**。

### 4.1 键按 **resolved model** 匹配

`model_thinking_effort` 的键是**上游实际收到的模型 id**（`claude-sonnet-5`），不是客户端说的名字（`claude-sonnet-4-5`），也不是 `model_mappings` 的键。

这一条必须写死在这里，因为它已经坑过一次：`strip_anthropic_beta_flags` 落地时（`.dev/docs/tmp/260822-review-beta-flag-strip.md:6`）发现用户亲笔 `config.example.yaml` 里那张表唯一的键 `claude-sonnet-4.6` 在同一份文件里恰好是 `model_mappings` 的**键**（映射到 `claude-sonnet-5`），两段配置同时生效时整张表空转。本次的请求形状一模一样。**配置样例与注释必须点明这一点**，否则同一个坑会以同样的形状再踩一次。

### 4.2 对齐规则

设 `configured` 为配置给该 resolved model 的 effort 名，`published` 为目录 `capabilities.supports.reasoning_effort` 发布的名字集合。

1. 该模型没有配置项 → **不发 `output_config`**。上游默认即 `high`（§2.3），这是「什么都不做」的正确形态。
2. `published` 缺席或为空 → 不发，并记一条日志说明原因。
3. `configured ∈ published` → **原样发出**。哪怕这个名字不在本项目的 `EFFORT_LADDER` 上——**目录是权威**，这正是不重蹈 §2.4 那个硬编码缺陷的地方。
4. `configured ∉ published` → 在 `EFFORT_LADDER`（`none < minimal < low < medium < high < xhigh < max`）上取**不强于 `configured` 的最强的已发布档**；取不到则取**最弱的已发布档**。两种情况都记为近似并写明两个档名。
5. `published` 里**一个能被 `EFFORT_LADDER` 排序的名字都没有**（例如目录只发布 `("turbo",)`，而 `configured` 不是 `turbo`）→ **不发**，日志写明目录发布了哪些名字。首稿漏了这一格，实现于是掉进规则 2 的分支，既不发 effort、又对着一个明明发布了档位的模型报「这个模型没有发布任何 reasoning effort」——两处都错。**不在这里猜**：一个排不了序的名字可能比 `configured` 便宜得多，也可能贵得多，没有任何东西能分辨，而本腿省略即上游默认，是一个真答案。

规则 4 的阶梯与翻译腿 `pipeline/translation_driver/reasoning.py` 的 `_at_or_below` / `_weakest` **共用同一条**，实现上不另起一套：两条腿对「这个 effort 名这个模型收不收」必须给同一个答案。

**但两条腿的兜底方向不同，这是有意的，不是漂移。** 翻译腿的 `resolve` 在什么都配不上时**向上**取最弱档；本腿的 `align_effort` 答 `None`、不发字段。区别不在于对同一问题有两种意见，而在于两条腿对「沉默」的含义不同：Responses 腿实测省略 `reasoning` 会拿到上游自己的默认，所以「关掉」必须说出口，向上取是它唯一能说出点什么的办法；本腿省略 `output_config` **就是**文档写明的默认（`high`），于是「不选」本身是一个真答案。

### 4.3 客户端自带的 `output_config` 不被覆盖

客户端若已经发了 `output_config`，原样透传，本条不介入。它在用这个端点自己的词汇说自己的事，替它改口不是能力门该做的。

### 4.4 `disabled` 不附 effort

`thinking.type == "disabled"` 时不写 `output_config`。文档说 effort 也影响整体 token 花销，但没有任何实测说明「关掉思考还要给 effort」是必要的，缺一个具体失败面。见 §9。

### 4.5 客户端省略 `thinking` 时仍附 effort

`thinking` 与 `output_config` 是两个独立的顶层字段，上游分别读。**实测 2026-08-24**：一个完全不带 `thinking` 的请求体单独带 `output_config` 得 200。

所以「客户端有没有发 `thinking`」不是发不发 effort 的判据。在 adaptive 模型上，省略 `thinking` **不是**「不思考」——目录与文档都写明它会跑 adaptive，所以那里确实有一个 effort 可以控制的东西。只有显式的 `thinking.type == "disabled"` 才退出（§4.4）。

`thinking` **存在但读不懂**（`null`、字符串、数字）时两件事都不做：要判断该不该附 effort 就得知道思考是不是被关掉了，而一个读不懂的字段恰恰不说这件事。

## 5. `thinking.display`

**用户 2026-08-24 裁定**：可配置改写或丢弃，**默认透传**。

| `hook_fix_anthropic_request.thinking.display` | 行为 |
|---|---|
| `passthrough`（默认） | 客户端发什么就发什么；客户端没发就不加 |
| `drop` | 删去 `thinking.display` |
| `omitted` / `summarized` | 改写为该值（`thinking` 存在且非 `disabled` 时） |

默认透传的理由是 §2.3：`display` 是 adaptive 形态上的合法字段，客户端发的 `omitted` 又恰好就是 Sonnet 5 一族的默认值，所以透传既不增加风险也不改变客户端说过的话。留下开关是因为它有一个真实的用途——`summarized` 会让上游返回可读的推理摘要，而默认的 `omitted` 会让 thinking 块的文本为空。

## 6. `messages` 的末尾角色

### 6.1 条款

出站请求体的 `messages` **不得以「带内容的 assistant 轮」结尾**——除非那正是客户端自己发过来的样子。

| 情形 | 出站 |
|---|---|
| 末尾不是 assistant | 不碰 |
| 末尾是 assistant，但 `content` 是空列表 | **不碰**。上游接受它（§2.2 引的本仓 F4/F6 实测 200），它不是 prefill——没有东西可以被续写 |
| 末尾是带内容的 assistant，且**客户端原始请求体**的末尾也是 assistant | 不碰，让上游去命名它 |
| 末尾是带内容的 assistant，且客户端原始请求体的末尾**读不出来** | **不碰**。见 §6.5 |
| 末尾是带内容的 assistant，而客户端原始请求体的末尾是 user | **追加一条合成 user 消息**，文本为 `Please continue.` |

**首稿把这条写成了「不得以 assistant 结尾」的全称，那是错的**，而且本仓自己 2026-08-20 的一手证据就摆在 `exp/260820-empty-text-probe/` 里：F4 与 F6 对末轮与中间位置的 `assistant content: []` 各得 200。两个实测的 400 让我写下了一条第三个实测早已证否的规则——**两个正例不构成全称**，而这个反例本来就在仓库里。更糟的是那个形状正是邻居 `drop_blank_text_blocks` 亲手造的（它把全空白的 assistant 轮**清空**而不是删掉），于是两道守卫会互相打架，而赢的那个会往一个本来就能成功的请求里塞进一句用户指令。

追加记为一条 `LossCode.SYNTHETIC_TURN_ADDED`，走 `conversion_losses`，于是它出现在请求日志行上。

判据读的是 `context.original_payload`——客户端原样送来的那份——而不是 `messages` 的尾巴。这不是实现细节，是这条规则的全部要害，见 §6.3。

**`content: ""`（空字符串）没有测过**，按带内容处理。已测的两个 400 都是非空内容，已测的 200 是空列表；空字符串落在两者之间，没有证据，所以走保守那一侧。

### 6.2 这个坏形状是本代理自己造的

不是假想的可达性。本管线有两处会删掉整条消息，**两处都能删掉最后一条**：

- `pipeline/anthropic_request_hook.py` 的 `repair_tool_pairs`——被孤儿清除清空的那一轮会被丢弃。一条只装 `tool_result` 而其调用已不在的末尾 user 消息（客户端侧压缩之后，或本代理自己的 thinking 块剥离之后）正是这个形状。
- `pipeline/subscribers/blank_text.py` 的 `drop_blank_text_blocks`——内容只有一个空白文本块的 user 消息会被丢弃。

2026-08-24 各跑了一次：一条合法的、`user / assistant / user` 三轮、以 user 结尾的请求体，经这两处任一之后都变成 `user / assistant`，**以 assistant 结尾**。

值得单独记下的是：`repair_tool_pairs` **已经问过**「删掉一轮要付什么代价」，并且答了一半——它自己的 docstring 记着实测「两条同角色相邻，上游给 200」。**「删完之后对话以 assistant 结尾」是另一半，而当时没有人问。** 一道守卫问了它想到的那个后果，没问它没想到的那个，于是另一个后果安静地活了三个月。

### 6.3 客户端自己写的 prefill 不修

prefill 是 Anthropic 有文档的特性。客户端**故意**用它，是在要一个这个模型不再提供的东西，而上游的拒绝信息恰恰把这件事说得一清二楚。

在那里追加一条 user 消息，会返回一个完全正常的答案——一个**悄悄忽略了客户端所要求的约束**的答案。客户端没有任何办法得知它的 prefill 没有生效。这与 `subscribers/server_tools.py` 拒绝「悄悄摘掉 web_search 再让模型凭记忆作答」是同一条理由：**修好我们弄坏的，和如实转达客户端要的，是两件不同的事。**

第一方客户端在 `messagesApi.ts` 里对同一个 400 做的是无条件追加（它的上游代码也会掉末尾 user 轮）。合成文本 `Please continue.` 照抄它的——合成提示词是模型真会读到的文本，已经有一个出货客户端选好了词，没必要再造一个——但**判别器是本项目自己加的**，因为它有一个第一方没有的信息：`original_payload`。

### 6.4 顺序是承重的

这道守卫必须跑在 `builtin:blank-text-blocks` **之后**，用 `after=` 显式声明，不靠注册顺序。它断言的是最终消息列表上的一条不变量，而那一趟是本事件上最后一个能删消息的东西。跑在它前面，守卫检查的就不是将要发出去的那个列表——那恰好正是它要防的失效。

### 6.5 读不出客户端原件时不修，这是一个已知缺口

判别器读 `original_payload["messages"]`，而**客户端的原件是用它自己的协议写的**。一个 `/responses` 请求的原件里根本没有 `messages` 键，角色在 `input` 里。首稿把「读不出来」当成「不是客户端写的」而去追加，于是在一条客户端确实自己以 assistant 结尾的路径上，塞进了一句它从没写过的话。

现在的规则是：**只有正面读到「客户端自己的对话没有在这里结束」才追加**，读不出来就不碰。

这留下一个真实的缺口：`drop_blank_text_blocks` 在翻译成 Anthropic 的请求体上也会跑，所以一个翻译过来的对话仍可能丢掉末尾 user 轮、以未修复的状态发出去、吃那个 400。**知情地留着它**，因为另一条路是跨协议边界猜，而两种失败不对等——没修的请求体会得到一个把问题说清楚的 400，猜错则是把客户端从没写过的一句话摆到模型面前并报告成功。

要闭合它，需要的是一个**跨协议的显式来源标记**（在 translation 之前由对应协议的 reader 读出「客户端末尾的语义角色」，随 context 传到出站阶段），而不是在这里给 `input` 再写一个读取器——Responses 的 `input` 里 `function_call`、`reasoning` 等多种 item 都会翻成 assistant，一个只看 `role` 的读取器会带来新的误判。登记为 A-7。

## 7. 上游的词汇表：`cache_control` 子字段与 `anthropic-beta` flag

### 7.1 条款

出站目标格式为 Anthropic Messages 的请求体里，**删掉配置表为这个模型点名的 `cache_control` 子字段，其余键一律不动**。表是 `hook_fix_anthropic_request.cache_control_sanitize`，按 resolved model 正则匹配、首个命中者生效，与 `strip_anthropic_beta_flags` 同构。默认档是 `sanitize`（用户 2026-08-24 第二次裁定，见 §7.3），随包默认表在 `src/app/config/bundled-config.yaml`，今天只有一条：Claude 一族的 `scope`。

**位置集合取自 Anthropic 官方请求 schema，不是从线上那条 400 的路径反推的。** 线上只报了 `system.1`，按它去写会漏掉其余每一处：

| 位置 | 说明 |
|---|---|
| 顶层 `cache_control` | 自动缓存，SDK 原话「applies a cache_control marker to the last cacheable block」。**这一处没有 block 承载，最容易漏** |
| `system[]` 的块 | 上游报错路径 `system.1.cache_control.ephemeral.scope` |
| `messages[].content[]` 的块 | `messages.0.content.0.text.cache_control.ephemeral.scope` |
| `tool_result.content[]` 的块 | `content` 是 `Union[str, Iterable[Content]]`，是列表时每个块都可带 marker |
| `search_result.content[]` 的块 | `content` 是 `Iterable[TextBlockParam]` |
| `document.source.content[]` 的块 | 仅当 source 是 `ContentBlockSourceParam` 那一支 |
| `tools[]` 的工具 | `tools.0.custom.cache_control.ephemeral.scope` |

**`thinking` 与 `redacted_thinking` 不在其列**——官方 schema 不允许它们直接带 `cache_control`，所以它们不是「漏掉的又一处」。

**按 schema 分派，不做盲递归。** 对任意 dict 递归去找 `cache_control` 会走进 `tool_use.input`、工具的 JSON Schema、以及普通工具输出的业务数据——那些地方一个恰好叫 `cache_control` 的键是客户端的数据，删掉它是在改用户的载荷。所以只对上表列出的块类型下钻。

**表里今天只有 `scope`，而它凭什么只列这一个**：实测目录里 7 个 Claude 模型（opus-5 / 4.8 / 4.7 / 4.6、sonnet-5 / 4.6、haiku-4.5）全部拒绝 `scope`、全部接受 `ttl`，每个模型的正控制都是 200。另一条独立来源指向同一处：Anthropic 官方 SDK 的 `CacheControlEphemeralParam` 逐字只有 `{type, ttl}`，**没有 `scope`**——与「`scope` 是更新的 beta 引入的字段」一致。所以「Claude 一族拒 `scope`」是两条独立来源共同支持的，而「除 `scope` 外还有别的字段有问题」今天没有任何证据。

`cache_control` 不是对象、或不存在时不碰。表为某模型点名的字段全部删完后若 `cache_control` 变成 `{}`，整个 marker 一并删掉——一个空断点对象不表达任何东西，而它是不是合法形状我们没测过。

**每一处删除记一条 loss，并带上它的路径**，走 §3.1 同一个 `context.extras["conversion_losses"]` 通道，于是它出现在请求日志行与记录里，而不是无声消失。逐处而不是一次 pass 聚合成一条：读者要判断的是「哪几个断点被动过」，一条写着「3 处」的记录回答不了这个问题。**这一条是承重的**：`scope` 表达的是缓存的作用域，剥掉它会改变缓存的实际行为（很可能是让缓存不再跨会话共享），这是一次真实的语义损失，不是清理噪声。

### 7.2 点名拦截，不是白名单——以及这个取舍买到了什么、赔掉了什么

**用户 2026-08-24 裁定：只拦已知模型上的已知字段，规则放进随包配置而不是代码常量。**

首版做的是相反的事：白名单 `{type, ttl}`，任何不在其中的键一律删。论证是上游 schema 是 strict 的（原话 `Extra inputs are not permitted`），所以**任何**它不认识的键都会让整个请求死；黑名单要求我们每次 Anthropic 加新字段都抢在客户端前面更新一次，错过一次的代价是那个客户端完全不可用，而白名单错的方向只是少送一个上游其实已支持的优化。**这个不对称是真的，裁决没有推翻它。**

裁决换来的是另外三样：

1. **不误删上游其实支持的东西。** 白名单会连同一切它没列的字段一起剥掉，包括上游今天就接受、或明天开始接受的那些——`scope` 本身就可能有一天被这个部署支持，那时白名单仍会剥它，而点名表只要删掉一行。
2. **新情况改配置，不改代码。** 运维遇到一个新字段被拒，写一行配置就能解决，不必等一次发布。
3. **拦截范围可以按模型收窄。** 今天 7 个 Claude 模型对 `scope` 的行为一致，所以表里是一条覆盖 `claude-` 的规则；但这个一致是**实测出来的，不是结构保证的**，将来某个模型开始支持时，表能表达这件事而一个全局白名单不能。

**赔掉的那样要写清楚，不能只写好处**：下一个被上游拒绝的新字段**不会**被这张表挡住，它会一路发到上游并让整条请求 400，直到有人把它加进表里。这不是实现缺陷，是这次取舍的定价——用「不误伤」换「不预防」。真出现时的止血是一行配置，而不是一次发布，这也是把表放进配置而不是代码的直接理由。

`ttl` 不在表里同样是实测结果而不是省略：`{type: ephemeral, ttl: "1h"}` 上游收（带不带 `extended-cache-ttl-2025-04-11` 都收），而同一个对象里的 `scope` 单独被点名拒绝。

### 7.3 四档的语义，与默认档的两次裁定

**用户 2026-08-24 两次裁定，方向不同，两次都要读到。**

第一次定的是 `passthrough` 的含义：它就是 `config.example.yaml` 写的那个意思——原样转发客户端的 marker，**包括这个上游会拒绝的键**。这一条至今有效，选了这一档就是这个行为。

第二次定的是**默认值**：从 `passthrough` 改为 `sanitize`。两次并不矛盾——第一次回答「`passthrough` 这一档做什么」，第二次回答「不写配置时用哪一档」。合起来的效果是：**开箱即用，而想要字面原样转发的人显式写 `passthrough` 仍然得到它**。

改默认的前提是 §7.2 那次改造：拦截范围从「白名单，剥掉一切没列的键」收窄成「只剥表为这个模型点名的字段」。默认档去做一件范围明确、有实测支撑、且能被一行配置关掉的事，与默认档去做一件无差别改写，不是同一个决定。

四档与本条的关系：

| 档 | 本条做什么 |
|---|---|
| `passthrough` | 什么都不做，一个字节都不动 |
| `sanitize`（**默认**） | 按 §7.1 的配置表，删掉表为这个模型点名的字段 |
| `disabled` | 每个 marker 整个删除 |
| `proxied` | **启动时拒绝**，注入那一半没有实现 |

`proxied` 的处理是本文的推导而非用户裁决：它在 `config.example.yaml` 里有定义，而这里只实现了「剥」没有实现「注」。静默当成 `passthrough` 的后果是——运维配置了「代理接管 prompt caching」，没有收到任何错误，然后按「没人接管」被计费。配置值无法兑现时停止启动，与一条编译不过的正则同类。

**这里原先写的是相反的东西，记下来是因为那个错法很自然。** 首稿让白名单在**每一档**下都跑，论证是：四档管的是断点（放哪、放几个、归谁），本条管的是词汇表（一个 marker 里能有哪些键），两者正交，所以 `passthrough` 承诺的「不插手客户端精调过的断点」并没有被违反——位置、数量、归属一个都没动，动的只是一个上游根本不认识的键。

这个区分本身没有被否定。被否定的是**据此单方面改掉一个用户定义的默认档**。异源评审 2026-08-24 判为 blocker，措辞是「不要用当前 Spec 自己提出的解释代替裁决」，而那句话说中了：首稿引用的授权是 `message-translation.md:7`「当我们需要理解和处理时，才分析和处理对应部分」，以及用户亲笔把空 thinking 块的剥离从可配置升级为常驻的先例。**两条都成立，但都不覆盖本格**——空 thinking 块**没有**用户定义的配置档，而 `cache_control` 有，用户还亲笔把「strip non-standard fields like scope」写进了 `sanitize` 那一档。当一个字段已经有了用户写下的语义分档，那句通用授权就不再是在空白处授权，而是要去覆盖一处已经有人做过的划分。

前身 `copilot-api-js` 在 `passthrough` 下同样剥 `scope`（`request-preparation.ts:1019-1025`，内置地雷清单 `:298-299` 就是 `["scope"]`）。这条旁证在裁决前就写在这里，裁决后仍然只是旁证——CLAUDE.md 明令不得把它的默认值当本项目契约。


### 7.4 为什么是主动式，不是反应式

与 §3.2 同一个论证，原样成立：`upstream-retry-and-continuation.md:9` 把 400 列进「无法继续」，而发送前就把请求构造对根本不产生这个 400。前身项目另有一条反应式重试（`cache-control-subfield-rejection-retry.ts`，其正则逐字匹配本次这条 400），它作为增强留在延后项里，不作为本条的实现方式。

### 7.5 加上那个 beta 也救不回来

这一条单独写出来，是因为它排掉的是一个方向完全相反、而且非常自然的第一猜想：既然 `scope` 由 `prompt-caching-scope-2026-01-05` 引入，那是不是补发这个 beta 就行？**实测：不行。** 带上该 beta 重发同一个 body，错误一字不差。而单独发这个 beta、body 不用它，上游返回 200——**网关收下了这个 beta，后端 schema 却不认它启用的字段**，上游自身两层不一致。所以「补 header」这条路是死的，只能剥字段。证据见 [reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md](reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md) §2 的 C3。

### 7.6 `anthropic-beta`：两层剥离，两个不同的问题

出站前，客户端的 `anthropic-beta` 依次经过两道剥离，**两者并列，互不包含**：

| 层 | 问的是什么 | 拒绝方 | 错误信封 | 清单归谁 |
|---|---|---|---|---|
| 网关词汇表 | 「这个部署认不认识这个名字」 | Copilot 网关，在任何模型看到请求之前 | `{"error":{"message":"unsupported beta header(s): …","code":"invalid_request_body"}}` | **本文，内置** |
| per-model 能力 | 「回答的那个模型有没有这个能力」 | Anthropic | `400 invalid beta flag` | **用户**，`strip_anthropic_beta_flags`，见 §8 与 §9 A-4 |

**内置清单（2026-08-24 实测）**：`tool-search-tool-2025-10-19`、`output-128k-2025-02-19`。同一轮里被接受的 12 个见证据报告 §3，其中 `tool-search-tool-2025-11-19` 与被拒的那个只差一位数字——所以判据必须是**精确逐字匹配**，前缀或子串匹配会把能用的那个一起拿掉。

**为什么不塞进用户那张表。** 那张表按 `resolved_model` 正则匹配，语义是模型能力；网关的拒绝与模型无关。用 `.*` 键机械上可行，但会把两个不同的命题混进同一张表，而且 §8 与 §9 A-4 已把那张表的**内容**判给用户裁决——往里放我方推导就是把我们的判断塞进用户的决定。并列的另一个实际收益：那张表今天有一处已知缺陷（唯一的键 `claude-sonnet-4.6` 被同一份配置的 `model_mappings` 映走，整张表匹配不到东西），而网关剥离不查那张表，因此不受它影响。

### 7.7 剥掉一个 flag 之后，body 必须仍然合法

这是本条最容易出错的地方，也是 §7.5 那条实测的反面。`request_headers.py` 的模块说明写着：剥 header 不会优雅降级，flag 启用的 body 字段会变成未识别字段而再吃一次 400。**所以每往内置清单加一个 flag，都要先测「不带这个 flag、但带它启用的 body」是否仍被接受**，而且要覆盖该特性的完整生命周期，不是只测第一轮。

`tool-search-tool-2025-10-19` 这一格已经这样测过（证据报告 §4）：`tools[].defer_loading` 混合 true/false、`tool_search_tool_regex_20251119` 服务端工具、以及第二轮 `tool_result.content[]` 里的 `{"type":"tool_reference"}` 块，**各自在完全不带 beta 时都返回 200**。第三项是承重的——Claude Code 用的是客户端自定义 tool search，`tool_reference` 只在第二轮出现，只测第一轮会漏掉「第一轮成功、第二轮 400」这个失败形状。

### 7.8 这份清单的适用范围与过期行为

**限定**：清单实测于 `api.enterprise.githubcopilot.com`、`claude-opus-5`、非流式。本项目的 API base url 由账号探测或 `api_base_url` 覆写决定，**其它 host 是否同样拒绝这两个 flag 没有测过**。实现今天对所有 Anthropic 直连请求无条件生效，这是一处**明知的过宽**，接受它的理由是代价不对称：按 §7.7，剥掉后 body 仍然合法，所以在一个其实接受该 flag 的 host 上多剥一个，损失是一次没人在用的能力协商；而少剥一个，损失是那个客户端的每一个请求。

**过期时怎么办**：若将来该网关学会了这两个 flag，清单不会自动失效，也不需要紧急处理——按上一段，继续剥的代价仍然只是一次协商。发现后从清单里删掉即可。**反过来，若发现某个 host 因为被剥而行为变差，那才是要立刻收窄的信号**，收窄的方式是把清单挂到 provider 上，而不是放宽判据。

**谁能改这张清单**：这是我方从实测推导的表，按本文头部的规则，clause 级修订走评审共识即可，不需要用户裁决——它与用户那张表的区别正在于此。

## 8. 不做什么

- **不做反应式的 400 学习与重试**（§3.2）。
- **不改 `min_thinking_budget` / `max_thinking_budget` 相关的任何行为**。本次那个 `budget_tokens: 63999` 也超出目录发布的 32000 上限，但没有任何实测说明上游会因此拒绝——它先撞上了 `thinking.type`。缺一个具体失败面，不预建。
- **不把 `adaptive_thinking` 与 `strip_anthropic_beta_flags` 合并。** 第一方客户端在 `chatEndpoint.ts:193-197` 把「支持 adaptive」与「不发 `interleaved-thinking-2025-05-14`」绑成同一个判据，用户亲笔的 `config.example.yaml:443-444` 恰好也在给 `claude-sonnet-4.6` 剥这个 flag——**这两件事很可能是同一个能力位的两个后果**，但那张表是用户手写的，合并与否是用户的决定，不是这里的。记在此处以便用户裁决。
- **不做 `adaptive` → `enabled` 的反向降级。** 一个不支持 adaptive 的模型收到 `{type: "adaptive"}` 同样会 400，且这条路径今天可达（`translation_driver/anthropic_messages.py:274` 在 intent 为 adaptive 时就写出这个形状）。不做的理由不是它不重要，而是**降级需要一个 budget 数字，而没有任何非虚构的来源提供它**：第一方客户端取自用户配置，我们没有对应的配置，凭空造一个就是发明契约。见 §9。

## 9. 待裁决与延后

| 编号 | 是什么 | 状态 |
|---|---|---|
| A-1 | **目录查不到该模型（`describe` 返回 `None`）时怎么办**——**这一格今天在生产里到不了**，首稿说「当前实现按透传」是错的：`decide_route` 在 `describe` 返回 `None` 时直接抛 `UnknownModel`，请求在路由阶段就被本地拒绝，根本不会生成 Route、不会执行 `apply_route`，订阅者也就永远看不到 `None`。订阅者里那条读作「非 adaptive」的分支是给手工构造的 context 用的防御性读法，不是现行系统行为。真正的开口是**未知模型该本地拒绝还是透传给上游拒绝**，那是路由的产品裁决，不属于本 topic；此处仅记指路。 |
| A-2 | `adaptive` → `enabled` 的反向降级（§8 末条）。需要先有一个非虚构的 budget 来源，或者一条实测证明它可达且确实 400。**2026-08-24 实测降低了它的紧迫性**：活目录当天只剩 `claude-haiku-4.5`、`claude-opus-4.6/4.7/4.8`、`claude-opus-5`、`claude-sonnet-4.6`、`claude-sonnet-5` 七个 Claude 模型，`claude-sonnet-4.5` 与 `claude-opus-4.5` **已从目录消失**（`refs/available_models.json` 那份快照过期了）；余下唯一非 adaptive 的 `claude-haiku-4.5` 在用户配置里被映到 `gpt-5.6-luna`。也就是说**今天经这份配置到不了任何非 adaptive 的 Claude 模型**。这是配置与目录的当下状态，不是代码性质——目录随时会变，判据仍必须运行时读。 |
| A-3 | `thinking.type == "disabled"` 时是否也附 `output_config.effort`（§4.4）。 |
| A-4 | `adaptive_thinking` 能力位与 `strip_anthropic_beta_flags` 表是否为同一决策的两半（§8）。用户的表，用户裁决。 |
| A-5 | 本文的规范条款要落进用户亲笔的 `docs/.human-controlled/message-format-reshape.md`「向上游输出 Anthropic Messages」一节（该节今天只有两条 thinking **块布局**的整形，`thinking.type` 取值零命中）。候选片段见 [`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md`](../../human-controlled-docs-candidates/anthropic-thinking-capability.md)，**用户追认前，本文是我方推导，不是用户裁决**。 |
| A-6 | **两个新配置键在 `build_chain` 时被闭包捕获，因此改了要重启才生效**，而用户亲笔 `config.example.yaml` 的默认承诺是热重载，`NOT_HOT_RELOADABLE` 里也没有它们。这不是本次引入的形状——同一事件上的 `builtin:hosted-web-search-gate` 与它的 `models_support_web_search` 一模一样，而且全仓今天**没有任何生产代码调用 `ConfigProvider.reload()`**，热重载在实现上是一处更宽的既有缺口。**因此没有为这两个新键单独改架构**：单独给它们做请求级快照会造出「同一个 registry 里两种时效语义」，比缺口本身更难读。已在候选片段里向用户点明，等热重载整体接线时一并处理。依据：实施评审 ADTR-06。 |
| A-7 | **跨协议的「客户端末尾语义角色」没有显式来源标记**，于是 §6.5 那个缺口存在：翻译成 Anthropic 的请求体若被 `drop_blank_text_blocks` 削掉末尾 user 轮，会以未修复状态发出并吃 400。闭合它要在 translation 之前由对应协议的 reader 读出该事实并随 context 传下去，而不是在出站端再写一个 `input` 读取器——Responses 的 `input` 里 `function_call`、`reasoning` 等多种 item 都会翻成 assistant，只看 `role` 会引入新的误判。没有实测样本，优先级低。依据：实施评审 ATRA-01。 |
| A-8 | ~~`passthrough` 档下也剥未知键，需要用户追认~~ **已裁决，2026-08-24：`passthrough` 字面成立**，白名单只在 `sanitize` / `disabled` 两档下运行，默认档一个字节都不动。条款见 §7.3。当时的问法与被否决的论证一并留在 §7.3 末尾，不删——那个错法（用本文自己新写的解释去覆盖用户定义的默认档）比结论更值得下一个人看见。 |
| A-9 | **`proxied` 档与 `extended_cache_ttl` 仍未实现。** 2026-08-24 已实现四档中的三档（`passthrough` 什么都不做、`sanitize` 走白名单、`disabled` 全删）；`proxied` 要求代理剥掉客户端断点后注入自己的，只有「剥」这一半存在，因此配置到它时**启动即拒**而不是静默当作 `passthrough`。原条目：**`hook_fix_anthropic_request.cache_control` 四档与 `extended_cache_ttl` 至今零实现**，配置项存在、注释齐全、消费者一个都没有（`src/app/config/schema.py:16,344`，实测四种取值走完 `fix_anthropic_request` 请求体逐字节不变）。本次只实现了与之正交的子字段白名单，**四档本身仍然没做**，这不是本次静默削减，而是一处此前从未进过任何台账的既有缺口，在此登记。`extended_cache_ttl` 另有一个前置问题：它注释里引用的门控 `model_capabilities.extended_cache_ttl` 在配置样例里从来不是一个真实的键，只存在于那两行注释本身。依据：[reports/../tmp/260824-cache-control-scope-400-investigation.md](../tmp/260824-cache-control-scope-400-investigation.md) F-1、F-2。 |
| A-10 | ~~网关 beta 词汇表与用户 per-model 表未分开~~ **已闭合，2026-08-24**：两者已分为并列的两层，规范条款见 §7.6～§7.8，实现是 `request_headers.py` 的 `GATEWAY_UNSUPPORTED_BETAS` 与 `strip_gateway_unsupported_betas`。**留在表里而不是删除，是因为编号是标识不是序号**；仍开着的那一半——清单只在 enterprise host 实测过而实现对所有 host 生效——已作为限定写进 §7.8，不作为待裁决项。 |

## 10. 证据来源

| 来源 | 权重 | 限定 |
|---|---|---|
| `~/.local/share/ghc-api-proxy/rejected/20260824T103948.240-400-530e0e10-...json` | 第一手，强到可据以行动 | 单次样本；`budget_tokens == max_tokens - 1` 这一形状 n=1 |
| §2.1 的双向探针（负控制 400 + 正样本 200） | 第一手实测，强到可据以行动 | **只覆盖 `claude-sonnet-5`、非流式、各一次调用**；不覆盖其他模型、流式、`disabled` 形态 |
| §2.5 的字段探针矩阵 | 第一手实测，强到可据以行动 | 同上的模型与流式限定。一个 200 只说明**上游收下了**，不说明它照做了——对「要不要建守卫」是决定性的，对「这个参数有没有效」不是 |
| §6.2 的可达性实测（本项目自己的两处修复） | 第一手，强到可据以行动 | 直接跑本仓代码，不依赖上游；证明的是**我们会造出那个形状**，那个形状会被拒是 §2.5 另行测的 |
| 上游 400 的 `message` 原文 | 上游自述，但**是建议不是保证** | 它说该发什么，不等于它会接受什么；§2.1 的正样本才是后者 |
| `refs/available_models.json` | 目录快照 | **活数据的快照**，判据必须运行时读目录 |
| `claude-api` skill `brief/thinking-and-effort.md` | 官方文档的缓存 | 缓存于某个 CLI 版本，非实时 |
| `refs/vscode-copilot-chat/.../messagesApi.ts` | 第一方实现 | **仓库已归档，代码停在 2026-04/05**；`:172-176` 的硬编码 effort 三项在今天是缺陷，不可照抄（§2.4） |
| `.dev/docs/sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` | 时点报告 | 自述射程是翻译腿的 `reasoning.py`；是证据，不是权威 |
