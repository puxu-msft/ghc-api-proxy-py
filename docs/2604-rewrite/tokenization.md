# Tokenization、校准与 Prompt Limits

## 协议边界

Token count 是协议 wire contract，不是单一通用端点：

- Anthropic：`POST /v1/messages/count_tokens`，上游精确计数优先，本地 calibrated fallback。
- Gemini：`POST /v1beta/models/{model}:countTokens`，使用 Gemini 专用本地 estimator。
- OpenAI/Azure：无独立 count endpoint，只在 completion response 中报告 usage。

共享模块只复用 tokenizer 生命周期、状态与结果机制；Anthropic/Gemini 各自保留协议专用 payload 估算，避免伪造 canonical request。

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
