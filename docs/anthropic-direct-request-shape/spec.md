# Anthropic 直连腿：`thinking` 与 `output_config` 的构造

**这份是 Spec**，答「应该是什么样」，规范性。**这是活文档，不冻结。** 新的用户裁决、实测或发现一旦与本文任何一处冲突或限定它，**当场修订本文**——不把已知错误的条款留在原地，也不把修正寄存到延后台账或评审报告里。权威永远是本文的当前版本。

**范围**：**所有出站目标格式为 Anthropic Messages 的请求**，在 translation 之后的最终形状里，`thinking` 与 `output_config` 两个字段。其余字段不在本文范围内。

**为什么范围不是「直连腿」。** 首稿写的是 `translation_required == False`，而实现从第一天起就按 target format 判断——这不是实现越界，是首稿把范围写窄了。判据在于：能不能收 `thinking.type: enabled` 是**回答请求的那个模型**的属性，与这个请求体是客户端原样送来的还是翻译出来的无关。翻译到 Anthropic 的那条路今天真的会写出 `{"type":"enabled","budget_tokens":N}`（`pipeline/translation_driver/anthropic_messages.py` 的 `_restore_thinking`），它到了同一个端点会吃同一个 400。按腿切会让那半边无人认领，而 `attempt.prepare` 与 count 腿本来就都在 translation 之后运行，target format 才是它们共同的边界。

**仍然不在范围内**：Anthropic → Responses 方向的 reasoning 映射，那是 `anthropic-responses-bridge/spec.md` 的管辖。

**条款修订记录**：

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-08-24 | 全文 | 首稿 | 线上 400（§1），用户 2026-08-24 对 effort 来源与 `display` 处置的裁定（§4、§5） |
| 2026-08-24 | §2.1 | 补上正向实测：本文规定要发的那个请求体**被上游接受**。首稿只有「旧形状被拒」这一半，据以推断新形状可用——那是从上游的建议里读出来的，不是量出来的 | 双向探针（§2.1），负控制与正样本各一次真实调用 |
| 2026-08-24 | 范围声明 | 从「直连腿」改为「所有出站目标格式为 Anthropic Messages 的请求」。首稿把范围写窄了，而实现一直按 target format 判断，两者矛盾 | 实施评审 [reports/260824-implementation-review.md](reports/260824-implementation-review.md) ADTR-03 |
| 2026-08-24 | §4.0、§4.2 | 补上「客户端省略 `thinking` 时仍附 effort」，并给规则 4 补上目录只发布本地阶梯无法排序的名字时该怎么办——首稿两处都没说，实现于是各自替它做了决定 | 同上，ADTR-01 与 ADTR-02；`output_config` 单独发出被实测接受（§2.1） |
| 2026-08-24 | §7 A-1 | 原文说「当前实现按透传」，这在生产里不可达：`decide_route` 在 `describe` 返回 `None` 时直接抛 `UnknownModel`，根本不会生成 Route。改写为它实际是什么 | 同上，ADTR-05 |

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

反应式（学习 + 重试）作为增强留在 §7 延后项里。

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

### 4.5 客户端省略 `thinking` 时仍附 effort

`thinking` 与 `output_config` 是两个独立的顶层字段，上游分别读。**实测 2026-08-24**：一个完全不带 `thinking` 的请求体单独带 `output_config` 得 200。

所以「客户端有没有发 `thinking`」不是发不发 effort 的判据。在 adaptive 模型上，省略 `thinking` **不是**「不思考」——目录与文档都写明它会跑 adaptive，所以那里确实有一个 effort 可以控制的东西。只有显式的 `thinking.type == "disabled"` 才退出（§4.4）。

`thinking` **存在但读不懂**（`null`、字符串、数字）时两件事都不做：要判断该不该附 effort 就得知道思考是不是被关掉了，而一个读不懂的字段恰恰不说这件事。

### 4.3 客户端自带的 `output_config` 不被覆盖

客户端若已经发了 `output_config`，原样透传，本条不介入。它在用这个端点自己的词汇说自己的事，替它改口不是能力门该做的。

### 4.4 `disabled` 不附 effort

`thinking.type == "disabled"` 时不写 `output_config`。文档说 effort 也影响整体 token 花销，但没有任何实测说明「关掉思考还要给 effort」是必要的，缺一个具体失败面。见 §7。

## 5. `thinking.display`

**用户 2026-08-24 裁定**：可配置改写或丢弃，**默认透传**。

| `hook_fix_anthropic_request.thinking.display` | 行为 |
|---|---|
| `passthrough`（默认） | 客户端发什么就发什么；客户端没发就不加 |
| `drop` | 删去 `thinking.display` |
| `omitted` / `summarized` | 改写为该值（`thinking` 存在且非 `disabled` 时） |

默认透传的理由是 §2.3：`display` 是 adaptive 形态上的合法字段，客户端发的 `omitted` 又恰好就是 Sonnet 5 一族的默认值，所以透传既不增加风险也不改变客户端说过的话。留下开关是因为它有一个真实的用途——`summarized` 会让上游返回可读的推理摘要，而默认的 `omitted` 会让 thinking 块的文本为空。

## 6. 不做什么

- **不做反应式的 400 学习与重试**（§3.2）。
- **不改 `min_thinking_budget` / `max_thinking_budget` 相关的任何行为**。本次那个 `budget_tokens: 63999` 也超出目录发布的 32000 上限，但没有任何实测说明上游会因此拒绝——它先撞上了 `thinking.type`。缺一个具体失败面，不预建。
- **不把 `adaptive_thinking` 与 `strip_anthropic_beta_flags` 合并。** 第一方客户端在 `chatEndpoint.ts:193-197` 把「支持 adaptive」与「不发 `interleaved-thinking-2025-05-14`」绑成同一个判据，用户亲笔的 `config.example.yaml:443-444` 恰好也在给 `claude-sonnet-4.6` 剥这个 flag——**这两件事很可能是同一个能力位的两个后果**，但那张表是用户手写的，合并与否是用户的决定，不是这里的。记在此处以便用户裁决。
- **不做 `adaptive` → `enabled` 的反向降级。** 一个不支持 adaptive 的模型收到 `{type: "adaptive"}` 同样会 400，且这条路径今天可达（`translation_driver/anthropic_messages.py:274` 在 intent 为 adaptive 时就写出这个形状）。不做的理由不是它不重要，而是**降级需要一个 budget 数字，而没有任何非虚构的来源提供它**：第一方客户端取自用户配置，我们没有对应的配置，凭空造一个就是发明契约。见 §7。

## 7. 待裁决与延后

| 编号 | 是什么 | 状态 |
|---|---|---|
| A-1 | **目录查不到该模型（`describe` 返回 `None`）时怎么办**——**这一格今天在生产里到不了**，首稿说「当前实现按透传」是错的：`decide_route` 在 `describe` 返回 `None` 时直接抛 `UnknownModel`，请求在路由阶段就被本地拒绝，根本不会生成 Route、不会执行 `apply_route`，订阅者也就永远看不到 `None`。订阅者里那条读作「非 adaptive」的分支是给手工构造的 context 用的防御性读法，不是现行系统行为。真正的开口是**未知模型该本地拒绝还是透传给上游拒绝**，那是路由的产品裁决，不属于本 topic；此处仅记指路。 |
| A-2 | `adaptive` → `enabled` 的反向降级（§6 末条）。需要先有一个非虚构的 budget 来源，或者一条实测证明它可达且确实 400。 |
| A-3 | `thinking.type == "disabled"` 时是否也附 `output_config.effort`（§4.4）。 |
| A-4 | `adaptive_thinking` 能力位与 `strip_anthropic_beta_flags` 表是否为同一决策的两半（§6）。用户的表，用户裁决。 |
| A-5 | 本文的规范条款要落进用户亲笔的 `docs/.human-controlled/message-format-reshape.md`「向上游输出 Anthropic Messages」一节（该节今天只有两条 thinking **块布局**的整形，`thinking.type` 取值零命中）。候选片段见 [`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md`](../../human-controlled-docs-candidates/anthropic-thinking-capability.md)，**用户追认前，本文是我方推导，不是用户裁决**。 |
| A-6 | **两个新配置键在 `build_chain` 时被闭包捕获，因此改了要重启才生效**，而用户亲笔 `config.example.yaml` 的默认承诺是热重载，`NOT_HOT_RELOADABLE` 里也没有它们。这不是本次引入的形状——同一事件上的 `builtin:hosted-web-search-gate` 与它的 `models_support_web_search` 一模一样，而且全仓今天**没有任何生产代码调用 `ConfigProvider.reload()`**，热重载在实现上是一处更宽的既有缺口。**因此没有为这两个新键单独改架构**：单独给它们做请求级快照会造出「同一个 registry 里两种时效语义」，比缺口本身更难读。已在候选片段里向用户点明，等热重载整体接线时一并处理。依据：实施评审 ADTR-06。 |

## 8. 证据来源

| 来源 | 权重 | 限定 |
|---|---|---|
| `~/.local/share/ghc-api-proxy/rejected/20260824T103948.240-400-530e0e10-...json` | 第一手，强到可据以行动 | 单次样本；`budget_tokens == max_tokens - 1` 这一形状 n=1 |
| §2.1 的双向探针（负控制 400 + 正样本 200） | 第一手实测，强到可据以行动 | **只覆盖 `claude-sonnet-5`、非流式、各一次调用**；不覆盖其他模型、流式、`disabled` 形态 |
| 上游 400 的 `message` 原文 | 上游自述，但**是建议不是保证** | 它说该发什么，不等于它会接受什么；§2.1 的正样本才是后者 |
| `refs/available_models.json` | 目录快照 | **活数据的快照**，判据必须运行时读目录 |
| `claude-api` skill `brief/thinking-and-effort.md` | 官方文档的缓存 | 缓存于某个 CLI 版本，非实时 |
| `refs/vscode-copilot-chat/.../messagesApi.ts` | 第一方实现 | **仓库已归档，代码停在 2026-04/05**；`:172-176` 的硬编码 effort 三项在今天是缺陷，不可照抄（§2.4） |
| `.dev/docs/sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` | 时点报告 | 自述射程是翻译腿的 `reasoning.py`；是证据，不是权威 |
