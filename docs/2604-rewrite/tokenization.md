# Tokenization、校准与 Prompt Limits

## 协议边界

Token count 是协议 wire contract，不是单一通用端点：

- Anthropic：`POST /v1/messages/count_tokens`，上游精确计数优先，本地 calibrated fallback。
- Gemini：`POST /v1beta/models/{model}:countTokens`，使用 Gemini 专用本地 estimator。
- OpenAI/Azure：无独立 count endpoint，只在 completion response 中报告 usage。

共享模块只复用 tokenizer 生命周期、状态与结果机制；Anthropic/Gemini 各自保留协议专用 payload 估算，避免伪造 canonical request。

## 与请求管道共享的部分（2026-08-20）

`/v1/messages/count_tokens` 与 `/v1/messages` 共用 `handler.shape_request()`：**路由**与 **`fix_anthropic_request`**。理由是 count endpoint 量的必须是**真正会发出去的那个 body**——上游已实测会用**逐字相同**的措辞拒绝 counting 请求与被计数的请求（server-tool 声明即为一例）。

`attempt.prepare` 订阅者**不在** `shape_request()` 内：真实路径由驱动逐 attempt 发布，count 路径只有一次 attempt，故在 `handle_count_tokens` 中自行发布一次。这一条早于本次改动就已共享。

**翻译不共享。** 本节开头那条「token count 是协议 wire contract」与「避免伪造 canonical request」同时否掉了「为了计数先翻译一遍」：翻译后的 body 在两侧都没有计数器——上游对 OpenAI 家族不提供，本地 estimator 读的是 Anthropic body。

**分成两问，而不是一问。**

1. **这个请求发得出去吗**——`translation_required` 但没有对应 translator 时（例如只广告 `/embeddings` 的模型），`handle()` 会抛 `TranslatorNotFound` 给出 400；count endpoint 用 `TranslatorRegistry.can_translate()` 问同一个问题并给出同样的 400。量一个注定被拒的请求，答案再准也没有意义。
2. **上游有没有计数器**——`target_format` 不是 Anthropic Messages 时，不向 `count_tokens()` 传 upstream counter，链路按既有语义交棒给 `local`，答案带 `estimated: true`；跳过原因经 `upstream_absent_reason` 进入 attempts trail（形如 `ghc:no-counter-for-openai-responses`），**不写成 `ghc:unconfigured`**——那会让下一个读日志的人去查一个并不存在的配置错误。

> **推翻了一条旧行为。** 此前翻译路径上 count endpoint 返回 **400 `EndpointNotSupported`**，理由写在 `count_tokens.py` 与其测试里：「answering would report a count for a model this request can never reach」。**该前提不成立**——同一个模型、同一个入站协议下 `POST /v1/messages` 会经翻译成功返回 200（`tests/http/test_pipeline_app.py::test_anthropic_request_for_a_responses_model_is_translated`）。模型是够得着的，够不着的是**计数器**。于是旧行为等于告诉客户端「你马上要发的这个请求没法量」。用户 2026-08-20 裁决改为本地估算。

`count_tokens.py` 中「`ProviderError` 一律外抛、不降级」的规则**未改**，但**在这个调用点上现已整体不可达**：只有 `target_format` 为 Anthropic Messages 时才会传入 upstream counter，而那种情况下 `require_endpoint` 必然通过。该规则继续为其他调用者保留。


## Anthropic service

`AnthropicTokenCountingService`：

1. 使用 `estimate_anthropic_input()` 计算与 fallback 相同 caliber 的本地 estimate。
2. 若 `anthropic.use_upstream_count_tokens=true`，调用 upstream count endpoint。
3. 上游返回正整数 `input_tokens` 时原样返回，并用 `(estimate, real)` 训练 calibration。
4. 网络/HTTP/JSON 失败时使用 `calibrate("anthropic", model, estimate)`。
5. Fallback 响应增加 `estimated: true`。

Assistant 历史里的 `thinking` 与 `redacted_thinking` 不计入 input estimate。

## Size-aware calibration

Key 为 `(protocol, normalize_for_matching(model))`。固定 buckets：

```text
[0,15k) [15k,30k) [30k,60k) [60k,120k) [120k,240k) [240k,+∞)
```

每个 bucket 保存 `sum_real`、`sum_estimated`、`sample_count`、`mean_estimated`。Factor 为 `sum_real/sum_estimated`，clamp 到 `[0.5,3.0]`；跨 populated buckets 按 mean estimate 做 log-linear interpolation。单 bucket 权重上限为 2000，达到上限后持续衰减旧 aggregate。

校准只修改本地计数结果，不修改 payload、不触发 retry、不覆盖 model catalog。

## 学习来源

- Anthropic count endpoint 精确响应。
- Anthropic 非流式 response usage。
- Anthropic 流式 `message_start/message_delta` usage，经 byte-preserving SSE tap。
- Prompt-limit 400 报告的真实 current input tokens，用于高尺寸 bucket。

Completion real input 口径为：

```text
input_tokens + cache_read_input_tokens + cache_creation_input_tokens
```

若真实探针显示 count endpoint 与 completion usage 的 caliber 不等价，应立即拆分 calibration key/source，不能混训。

## Prompt-limit observations

支持解析：

- `prompt token count of N exceeds the limit of M`
- `prompt is too long: N tokens > M maximum`
- 裸文本或 `{ "error": { "message": ... } }`

只接受 `current > limit > 0`。Observation 保存 protocol、normalized model、current、limit、source、time 和 count。

Catalog 的 `max_prompt_tokens` 是 advertised fact；错误中的 limit 是 observed fact。二者独立展示，错误观测不会静默覆盖 catalog，也不会让代理删改历史。

## 持久化

`TokenizationStateStore` 由每个 `RuntimeState` 持有：

- Versioned JSON。
- 内存更新只标记 dirty。
- 固定周期 off-thread flush。
- Async lock 串行化 periodic/shutdown flush。
- 写临时文件、`fsync`、atomic replace。
- 写失败保留 dirty，后续重试；读损坏文件告警后从空状态启动。
- Shutdown 在关闭 upstream 与取消 task group 前最终 flush。

默认路径为 XDG user data 下的 `tokenization.json`。

## 管理 API

- `GET /api/tokenization/calibration`
- `GET /api/tokenization/limits`

均支持 `protocol`、`model` query filters。Limits 响应同时给出 advertised、observed 和 difference。

## 相关文档

- [Hooks 机制](hooks-system.md)
- [请求管道](request-pipeline.md)
- [配置系统](config-system.md)
