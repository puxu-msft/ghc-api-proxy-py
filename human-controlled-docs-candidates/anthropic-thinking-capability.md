# 候选：`thinking.type` 的按模型能力构造与 `output_config.effort`

**性质**：本文是提案素材，**无效力**。规范推导见 `.dev/docs/anthropic-direct-request-shape/spec.md`；那份是我方推导，**在你摘取本文之前，它不是你的裁决**。

**建议摘取到**：

- `docs/.human-controlled/message-format-reshape.md`「向上游输出 Anthropic Messages」一节（今天第 65 行起），作为该节的第三个 `###`。理由：该节下辖的两小节都是「发往 Anthropic 上游的请求体要做哪些整形」，本条同族、同腿、同方向。
- `docs/.human-controlled/config.example.yaml`：一个新的顶层键 `model_thinking_effort`，以及 `hook_fix_anthropic_request.thinking` 下一个新子键 `display`。

---

## 一、现状：这个 400 已经发生过，出站请求体在磁盘上

2026-08-24 10:39:48，`req=530e0e10-c724-45a0-964a-129c3351646a`：

```
[FAIL] H1 400 POST /v1/messages claude-sonnet-4-5 → claude-sonnet-5 760ms
"thinking.type.enabled" is not supported for this model.
Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.
```

**现状**（可复算）：`observability/rejection_capture.py` 把出站请求体存进了 `~/.local/share/ghc-api-proxy/rejected/20260824T103948.240-400-530e0e10-c724-45a0-964a-129c3351646a.json`。它记着 `translation_required: false`、`endpoint: /v1/messages`、`route_reason: inbound_format_supported`，以及：

```json
"max_tokens": 64000,
"thinking": {"budget_tokens": 63999, "type": "enabled", "display": "omitted"}
```

**现状**：`model_mappings` 把 `claude-sonnet-4-5` 映到 `claude-sonnet-5`（`config.example.yaml:145`），而客户端是按它自己以为的 `claude-sonnet-4-5` 构造请求的——它不知道映射发生过。所以这不是客户端的错，也不会因为换个客户端而消失。

## 二、现状：目录里那个能力位，以及为什么只有它能判

**现状**（`refs/available_models.json`，`capabilities.supports`）：

| 模型 | `adaptive_thinking` | `reasoning_effort` | `min/max_thinking_budget` |
|---|---|---|---|
| `claude-sonnet-5` | `true` | `low, medium, high, xhigh, max` | 1024 / 32000 |
| `claude-opus-4.7`、`claude-opus-4.8` | `true` | `low, medium, high, xhigh, max` | 1024 / 32000 |
| `claude-opus-4.6`、`claude-sonnet-4.6` | `true` | `low, medium, high, max` | 1024 / 32000 |
| `claude-sonnet-4.5`、`claude-opus-4.5`、`claude-haiku-4.5` | **缺席** | **缺席** | 1024 / 32000 |

**值得单独注意**：`min_thinking_budget` / `max_thinking_budget` 在两类模型上都发布，所以**它们判别不了任何东西**——`claude-sonnet-5` 一样发布 1024/32000，却拒绝 `budget_tokens`。能判的只有 `adaptive_thinking`。

**现状**：这个能力位此前只被解析进 `src/app/models/capabilities.py`（旧链路），活链路的 `ModelDescriptor` 根本不带它。也就是说这不是实现漂移，是一处从来没人接过的线。

## 三、提案：新增的规范小节

> ### 按模型能力构造 `thinking.type`（400 `"thinking.type.enabled" is not supported for this model`）
>
> 上游同一个 `/v1/messages` 端点上跑着两代 Claude，它们对同一件事的说法互斥：目录发布 `capabilities.supports.adaptive_thinking` 的模型**拒绝** `thinking: {"type": "enabled", "budget_tokens": N}`，没发布的模型**要求**这个形状。不存在同时满足两者的请求体，所以请求体必须按目标模型的目录能力来构造。
>
> 判据是**这个请求要发给哪个模型**，不是它从哪儿来：客户端原样送来的、以及从别的协议翻译成 Anthropic Messages 的，都适用同一条。能不能收 `enabled` 是回答请求的那个模型的属性。
>
> **主动式，不是反应式。** 在发送前构造对，不依赖「先吃一个 400 再学习重试」。后者会撞上 `upstream-retry-and-continuation.md` 里「400 无法继续」那一条，而主动式根本不产生这个 400。第一方客户端也是主动式。
>
> 出站请求体 `thinking` 存在且是对象时：
>
> | 客户端发的 `thinking.type` | 目标模型 `adaptive_thinking` | 出站 |
> |---|---|---|
> | `enabled` | `true` | 改写为 `adaptive`，并删去 `budget_tokens` |
> | `enabled` | 缺席 | 原样透传 |
> | `adaptive` | 任意 | 原样透传 |
> | `disabled` | 任意 | 原样透传（该模型接受它） |
> | 其他 / 非对象 / 缺席 | 任意 | 不碰 |
>
> 被删去的 `budget_tokens` 记为一条转换损失，出现在请求日志行上，不无声消失。
>
> ### `output_config.effort`
>
> `output_config: {effort: ...}` 与 `thinking` 并列、互不相干；省略它等价于上游默认的 `high`。**实测：一个完全不带 `thinking` 的请求体单独带 `output_config` 也被接受**，所以客户端有没有发 `thinking` 不是发不发 effort 的判据——在 adaptive 模型上省略 `thinking` 会跑 adaptive，那里确实有东西可以被 effort 控制。
>
> effort 的取值来自新的顶层配置 `model_thinking_effort`，**没有内置默认值**：没配的模型一律不发 `output_config`。
>
> 配置里的值会与目录 `capabilities.supports.reasoning_effort` 对齐后再发出：目录发布了这个名字就原样发；没发布就在 `none < minimal < low < medium < high < xhigh < max` 上取不强于它的最强已发布档；取不到则取最弱的已发布档；若目录发布的名字**一个都排不上这条阶梯**（比如只有 `("turbo",)`），则不发——排不了序的名字可能比配置值便宜得多也可能贵得多，没有东西能分辨，而省略本身就是上游默认。
>
> 客户端自己发了 `output_config` 时不覆盖它。`thinking.type` 为 `disabled` 时不附 effort。`thinking` 存在但读不懂（`null`、字符串、数字）时两件事都不做。
>
> ### `messages` 不得以「带内容的 assistant 轮」结尾（400 `does not support assistant message prefill`）
>
> 上游拒收以**带内容的** assistant 消息结尾的对话。**而本代理自己会把请求改成那样**：`repair_tool_pairs` 会丢弃被孤儿清除清空的那一轮，`drop_blank_text_blocks` 会丢弃只剩空白文本块的 user 轮——两处都能删掉最后一条。实测：一条合法的、以 user 结尾的三轮对话，经这两处任一之后都变成以 assistant 结尾。
>
> 出站前检查末尾：若是**带内容的** assistant 轮，**而客户端原始请求体的末尾是 user**，追加一条合成 user 消息（文本 `Please continue.`），并记为一条转换损失。
>
> 三种情况不动它：
>
> - **末尾 assistant 的 `content` 是空列表**——上游接受它（本仓 `exp/260820-empty-text-probe/` 的 F4、F6 实测 200），它不是 prefill，没有东西可以被续写。而这恰恰是 `drop_blank_text_blocks` 亲手造出来的形状。
> - **客户端原始请求体的末尾本来就是 assistant**——那是客户端自己写的 prefill，是 Anthropic 有文档的特性，上游的拒绝信息把这件事说得很清楚。替它补一条 user 消息会返回一个正常答案，而那个答案悄悄忽略了客户端要求的约束，客户端无从得知。
> - **读不出客户端原件的末尾角色**——比如一个 `/responses` 请求，它的原件里没有 `messages` 键。只有正面读到「客户端自己的对话没有在这里结束」才追加。这留下一个已知缺口（翻译过来的请求体仍可能未修复地吃 400），知情地留着：没修的请求会得到一个把问题说清楚的 400，猜错则是把客户端从没写过的一句话摆到模型面前并报告成功。

## 四点五、实测澄清：**有三个字段其实不用管**

官方 Anthropic 文档说 Claude 5 一族移除了 `temperature` / `top_p` / `top_k`，发即 400。**经 Copilot 这条路实测，三个都收 200**——单独发、三个一起发、配 adaptive thinking 发、发 `temperature: 0` 都收。

**这次实测覆盖到哪里为止**：只有 `claude-sonnet-5` 这一个 resolved model、只有非流式、每格一次调用。**它不是对 Copilot 上全部 Claude 5 系模型或流式形态的结论。** 另一层限定：一个 200 只说明**上游收下了这个字段**，不说明它照做了——参数有没有生效是另一个问题，这次没测。

所以这段的用途是**防止有人照着那张官方表去建三个没用的守卫**，射程仅限已测路径。将来若另一个 resolved model 或流式路径真的对这些字段返回 400，按那个模型的能力另行处理，不要拿本段当全局否决。

同一批探针另外确认了两件已落地设计的必要性：`{type:"adaptive", budget_tokens:N}` 会 400（`Extra inputs are not permitted`，所以删 budget 是必须的），未发布的 effort 名会 400，**且上游的拒绝信息直接列出它支持的值**，与目录 `reasoning_effort` 逐字一致。
>
> ### `thinking.display`
>
> `display` 是 adaptive 形态上的合法字段（`{type: "adaptive", display: "summarized"|"omitted"}`），不是需要修的东西。用 `hook_fix_anthropic_request.thinking.display` 控制：`passthrough`（默认，客户端说什么就发什么）、`drop`、`omitted`、`summarized`。改写值只在 `thinking` 非 `disabled` 时生效。

## 四、提案：配置片段

```yaml
# 向 Anthropic Messages 上游请求 `output_config.effort` 的取值，按模型。
# Which `output_config.effort` to ask an Anthropic Messages upstream for, per model.
#
# 键是**上游实际收到的模型 id**，不是客户端说的名字，也不是 model_mappings 的键。
# effort 是「回答这个请求的那个模型」的能力，所以别名要被看穿。
# The key is the *resolved* model id — not the name the client asked for, and not a `model_mappings` key.
#
# ⚠️ 同一个坑已经有过一次：`hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`
# 那张表唯一的键 `claude-sonnet-4.6` 在本文件里恰好是 `model_mappings` 的**键**（映到 claude-sonnet-5），
# 两段配置同时生效时整张表匹配不到任何东西，且没有任何报错。
#
# 没配的模型不发 `output_config`，上游按自己的默认（high）处理。这里**故意没有兜底值**——
# 一个兜底值等于把每个请求都放上一个没人拨过的花钱旋钮。
#
# 取值会与目录发布的 `capabilities.supports.reasoning_effort` 对齐；写了目录没发布的名字会被向下取。
#
# model_thinking_effort:
#   claude-sonnet-5: xhigh
#   claude-opus-5: xhigh
```

```yaml
hook_fix_anthropic_request:
  thinking:
    # thinking.display 的处置。默认透传。
    # What to do with `thinking.display`. Default: pass it through.
    #
    # passthrough: 客户端发什么就发什么，客户端没发就不加。（默认）
    # drop:        删去该字段。
    # omitted:     改写为 "omitted"——上游流出的 thinking 块文本为空。（Claude 5 一族的上游默认）
    # summarized:  改写为 "summarized"——上游返回可读的推理摘要。
    #
    # 改写值只在 thinking 非 disabled 时生效。
    display: passthrough
```

## 五、留给你裁决的开口

按 `.dev/docs/anthropic-direct-request-shape/spec.md` §8 编号：

| 编号 | 问题 | 当前实现取了哪一侧 |
|---|---|---|
| A-1 | 目录里**查不到该模型**时怎么办？——**这一格今天到不了**：`decide_route` 在这种情况下直接抛 `UnknownModel`，请求在路由阶段就被本地拒绝。 | 无需处置。真正的开口是「未知模型该本地拒绝、还是透传给上游去拒绝」，那是路由的产品裁决，不在这条里。 |
| A-2 | `adaptive` → `enabled` 的**反向**降级要不要做？一个不支持 adaptive 的模型收到 `{type:"adaptive"}` 同样会 400，而这条路径今天可达。 | **不做**。不是因为不重要，而是降级需要一个 budget 数字，**没有任何非虚构的来源提供它**——第一方客户端取自它自己的用户配置，我们没有对应的配置，凭空造一个就是发明契约。若你愿意给一个来源（比如再加一个配置键），它就能做。 |
| A-3 | `thinking.type` 为 `disabled` 时要不要也附 `output_config.effort`？文档说 effort 也影响整体 token 花销。 | **不附**。没有任何实测说明它必要。 |
| A-4 | `adaptive_thinking` 这个能力位，与你亲笔的 `strip_anthropic_beta_flags` 表，**是不是同一个决策的两半**？第一方客户端在 `chatEndpoint.ts:193-197` 把「支持 adaptive」与「不发 `interleaved-thinking-2025-05-14`」绑成同一个判据，而你那张表恰好也在给 `claude-sonnet-4.6` 剥这个 flag。 | **没动**。那张表是你手写的，合并与否是你的决定。这里只负责把这个观察摆出来。 |
| A-6 | **这两个新键改了要重启才生效**，而本文件开头承诺「除非另有说明，所有设置均支持热重载」。 | **没有为它们单独改架构**。同一事件上的 `models_support_web_search` 是一模一样的形状，而且全仓今天**没有任何生产代码调用 `ConfigProvider.reload()`**——热重载在实现上整体还没接线。只给这两个新键换一种时效语义，会造出「同一个 registry 里两种规则」。摆在这里让你知道，等热重载整体接线时一并处理；若你希望现在就把它们标成需要重启，那要写进你的文档，我不擅自加。 |

## 六、一处顺带的观察，与本条独立

**现状**：`hook_strip_anthropic_request_headers.strip_anthropic_beta_flags` 那张表按 `resolved_model` 匹配，而表里唯一的键 `claude-sonnet-4.6` 在同一份 `config.example.yaml` 里被 `model_mappings` 映到 `claude-sonnet-5`。两段配置同时生效时，那张表匹配不到任何模型。这是 2026-08-22 该功能落地时评审就记下的（`.dev/docs/tmp/260822-review-beta-flag-strip.md:6`），至今未处理。**这是你的文件，我没有改它**——只是这次撞上的请求形状与它一模一样，顺手指出来。
