# Tokenization、校准与 Prompt Limits

## 协议边界

Token count 是协议 wire contract，不是单一通用端点：

- Anthropic：`POST /v1/messages/count_tokens`，上游精确计数优先，本地 calibrated fallback。
- Gemini：`POST /v1beta/models/{model}:countTokens`，使用 Gemini 专用本地 estimator。
- OpenAI/Azure：无独立 count endpoint，只在 completion response 中报告 usage。

共享模块只复用 tokenizer 生命周期、状态与结果机制；Anthropic/Gemini 各自保留协议专用 payload 估算，避免伪造 canonical request。

## 与请求管道共享的部分（2026-08-20）

`/v1/messages/count_tokens` 与 `/v1/messages` **走同一条塑形路径**：`handler.shape_request()`（路由 + `fix_anthropic_request`），随后**同样翻译**，再发布 `attempt.prepare` 订阅者。顺序与真实请求逐步对齐——真实路径由驱动在翻译之后发布 `attempt.prepare`，count 路径只有一次 attempt，故自行发布一次，但位置相同。

理由是 count endpoint 量的必须是**真正会发出去的那个 body**：

- 上游已实测会用**逐字相同**的措辞拒绝 counting 请求与被计数的请求（server-tool 声明即为一例），所以修复必须共享；
- 翻译腿上真正发出的是 Responses body——不同的 item 集合、不同的工具形状、每个 role 的拼法都不同——**上游的 tokenizer 数的是到达的东西，不是被问的东西**。量 Anthropic body 等于在描述一个不会发生的请求。

### 计数器按目标协议选

| 目标格式 | 计数器 | calibration 协议键 |
|---|---|---|
| Anthropic Messages | 上游 `POST /v1/messages/count_tokens` 优先，失败退本地 `estimate_anthropic_input` | `anthropic` |
| OpenAI Responses | 本地 `estimate_responses_input`（上游无预检端点） | `openai-responses` |

- **上游有没有计数器由 route 判定，不靠调用去发现**：`target_format` 不是 Anthropic Messages 时不传 upstream counter，链路按既有语义交棒给 `local`，跳过原因经 `upstream_absent_reason` 进入 attempts trail（形如 `ghc:no-counter-for-openai-responses`），**不写成 `ghc:unconfigured`**——那会让下一个读日志的人去查一个并不存在的配置错误。
- **calibration 键跟随目标协议**，与本文开头「各协议保留专用 payload 估算」同一条理由：两族的因子混训会让彼此用对方的误差去校正自己。
- **发不出去的请求仍然 400**：`translate()` 找不到 translator 时抛 `TranslatorNotFound`，与 `/v1/messages` 上一模一样。这一类不是「没有计数器」，是**根本发不出去**，量它没有意义。今天落在这一类的有：只广告 `/embeddings` 的模型，以及只广告 `/chat/completions` 的三个（`gemini-3.1-pro-preview`、`gemini-3.5-flash`、`trajectory-compaction`）——注册表尚未登记 chat-completions 的 outbound translator。
- **没有估算器的目标格式显式报错**：目前只有 Anthropic 与 Responses 两个估算器。若将来补上 chat-completions 的 translator 而不补估算器，`handle_count_tokens` 会抛错而不是拿 Responses 估算器去读一个没有 `input` 的 body 并返回 1。

> **两次推翻的记录。** 此前翻译路径上 count endpoint 返回 **400 `EndpointNotSupported`**，理由是「answering would report a count for a model this request can never reach」。**该前提不成立**——同一个模型、同一个入站协议下 `POST /v1/messages` 会经翻译成功返回 200（`tests/http/test_pipeline_app.py::test_anthropic_request_for_a_responses_model_is_translated`）。模型是够得着的，够不着的是计数器。随后的第一版改法**只**退回到 Anthropic body 的本地估算，用户 2026-08-20 判定**不够**：翻译路径要**正确支持**，即量翻译后的 body。现行行为即此。

`estimate_responses_input` 的规矩只有一条：**每个 item 都计入，没有例外**。未列出的种类按整段 JSON 计入，`reasoning` 也一样。

> **这条规矩是改出来的。** 初版跳过 `reasoning`，镜像 Anthropic 侧不计 `thinking`，并声称差额由 calibration 吸收。两处都错：本协议的 calibration **当前无人训练**（全仓没有 `learn("openai-responses", ...)` 的调用点，`calibrate` 是恒等），所以没有任何东西在吸收；而 reasoning item 并不小——实测一次往返携带 7286 字符的 `encrypted_content`，它所属的 7.6 KB body 被报成 30 tokens，生产 history 中 157 个 `encrypted_content` 的中位数为 7164 字符。上游是否对该 payload 计费仍然无从测量（OpenAI 家族不发布计数端点），但 0 对这个数的用途而言是**可测量地错**，且错在「说了装得下、发出去被拒」的方向。

估算器本身由 `tests/unit/test_responses_estimator.py` 以增量断言钉住：每条测试对应一种能击穿它的变异。**不用绝对值断言**——那要复述公式，而复述公式的测试对该公式的每个版本都通过，初版正是这样漏掉了三种变异。

`count_tokens.py` 中「`ProviderError` 一律外抛、不降级」的规则**未改**，但**在这个调用点上现已整体不可达**：只有 `target_format` 为 Anthropic Messages 时才会传入 upstream counter，而那种情况下 `require_endpoint` 必然通过。该规则继续为其他调用者保留。

**尚未做**：OpenAI 家族的 calibration 没有学习来源——上游只在响应完成时报 usage，而 count 发生在之前。把 Responses 响应的 usage 回喂给 `learn("openai-responses", ...)` 是自然的下一步，本次未做。

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
