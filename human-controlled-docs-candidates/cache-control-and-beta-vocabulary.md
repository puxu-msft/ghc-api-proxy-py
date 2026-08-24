# 候选：`cache_control` 词汇表、网关 beta 清单，与 tool search 的边界

**性质**：本文是提案素材，**无效力**。规范推导见 `.dev/docs/anthropic-direct-request-shape/spec.md` §7 与 `.dev/docs/anthropic-responses-bridge/spec.md`「Tools 与 tool choice」。**其中两条已经是你 2026-08-24 在会话里作出的裁决，但它们还没有落进你亲笔的任何文件**——这份候选存在的唯一目的就是把它们交给你追认，在此之前，那两条在文档层面仍然只是「我方记录的会话裁决」。

**建议摘取到**：

- `docs/.human-controlled/config.example.yaml`：`hook_fix_anthropic_request.cache_control` 那段注释（今天 474-483 行）补一句 `proxied` 未实现；无需改四档语义。
- `docs/.human-controlled/message-format-reshape.md`「按需剥离 `anthropic-beta` 请求头的部分 flag」一节（今天第 37 行起），补一个并列的第二层。

---

## 一、你已经裁决、但还没写进你文件的两条

### 1. `passthrough` 是字面的（2026-08-24 会话裁决）

背景：新版 Claude Code 会发 `cache_control: {"type":"ephemeral","scope":…}`，这个上游整条请求拒绝。

我最初把「剥掉上游不认的键」做成了**常驻**行为，在四档之下都跑，理由是「四档管断点位置，这条管键的词汇表，两者正交」。**你裁定这个做法不成立**：`passthrough` 就按你写的那句 `forward client cache_control as-is` 理解，白名单只在 `sanitize` / `disabled` 下运行，默认值仍是 `passthrough`。

**这条裁决的直接后果，写出来供你确认它确实是你要的**：默认配置下，一个会发 `scope` 的客户端，它的**每一个**请求都会拿到上游的 400。要让它工作，那台机器的 `config.yaml` 需要有：

```yaml
hook_fix_anthropic_request:
  cache_control: sanitize
```

### 2. tool search 不是本代理提供的能力（2026-08-24 会话裁决）

背景：Anthropic 侧的 tool search（客户端给工具打 `defer_loading`）翻译到 Responses 腿后被上游拒绝，而上游**存在**一个可用的对应物 `{"type":"tool_search"}`，实测把它加进去请求就通过。

你裁定不做这个映射。已落地：`defer_loading` 不进 wire（`true` 记一条 degradation，`false` 静默移除），并删除了 legacy `AppSettings` 里两个从未接线的开关 `tool_search` / `tool_search_non_deferred`。

**一处需要你确认边界的地方**：`translation_driver/openai_responses.py` 有一条既有注释，说 `memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_` 五族「没有 hosted 对应物」。实测证伪了其中至少两族（`tool_search` 与 `computer` 都在上游的支持枚举里）。我一度把你这句裁决写成了五族都不映射的依据，**这是越界，已收窄**——目前只有 `tool_search_` 一族是你裁的，其余四族仍按 `anthropic-responses-bridge/spec.md` 的 Server-tool no-revive 处理。若你的意思本来就覆盖五族，请明示。

## 二、需要你新裁的一条：网关 beta 清单该不该有第二张表

你亲笔的 `message-format-reshape.md` 现在只有一层 beta 剥离，配置键是 `strip_anthropic_beta_flags`，按**模型**正则匹配，语义是「这个模型没有这个能力」（上游报 `400 invalid beta flag`）。

实测发现还有**另一种**拒绝，与模型无关：

```
{"error":{"message":"unsupported beta header(s): tool-search-tool-2025-10-19","code":"invalid_request_body"}}
```

信封是 Copilot 网关自己的，措辞是「不认识这个名字」，在任何模型看到请求之前就发生。同一轮实测里，只差一位数字的 `tool-search-tool-2025-11-19` **是被接受的**，所以这是一张词汇表而不是能力判定。

我的处置是**新建一张并列的内置表**（`GATEWAY_UNSUPPORTED_BETAS`，目前两项：`tool-search-tool-2025-10-19`、`output-128k-2025-02-19`），而不是往你那张表里塞默认值——因为你那张表的内容是你的决定，把我方推导塞进去会混淆两个命题。

**请你裁的是**：这个并列结构你认不认。若认，是否要把它也变成一个配置键（今天是内置常量，改它需要改代码）。

顺带一提，你那张表今天有一处失效：唯一的键 `claude-sonnet-4.6` 在同一份 `config.example.yaml` 里被 `model_mappings` 映走了，两段配置同时生效时整张表匹配不到任何东西。你已在工作树里给它加了一条说明该现象的注释。新增的网关剥离不查那张表，因此不受影响。

## 三、需要你知道、但不需要你裁的两条

1. **`proxied` 档启动即拒。** 它在你的 `config.example.yaml` 里有完整定义，但注入那一半从未实现，只有「剥」存在。我没有让它静默降级成 `passthrough`——那样运维会以为代理接管了 prompt caching，收不到任何错误，然后按「没人接管」被计费。配置到它时服务拒绝启动并说明原因。若你希望它降级而不是拒绝，这需要你的一句话。

2. **`claude-sonnet-4.6` 的错误信封与其它模型不同。** 它返回顶层裸 `{"message": …}`，没有 `error` 包装，而 `pipeline/error_classify.py` 要求 `body["error"]` 存在，否则判为「读不懂上游的错误」。也就是说**该模型的所有 400 我们都解释不了**——识别不出上下文超限之类的条件，记录里 message 为空。这不在本次三个症状之内，属于 `error-envelope` 那个主题，尚未处理。
