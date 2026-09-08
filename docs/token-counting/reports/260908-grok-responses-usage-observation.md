---
report_id: grok-responses-usage-observation
status: settled
observed_at: 2026-09-08T03:38:00Z
trigger:
  source: current user request
  quoted_text: 不要只根据公开文档，要实际根据现状！
  strength: direct runtime observation
scope:
  service: current ghc-api-proxy on 127.0.0.1:4141
  model: grok-4.6
  endpoint: /v1/responses
---

# 当前 Grok Responses usage 观测

## 结论

在 2026-09-08 的当前 `ghc-api-proxy` 实例上，通过 `/v1/responses` 向 `grok-4.6` 发起一次最小非流式请求，HTTP 状态为 `200`。代理返回的 Responses-shaped `usage` 为：

```json
{
  "input_tokens": 1528,
  "input_tokens_details": {
    "cached_tokens": 1408
  },
  "output_tokens": 163,
  "output_tokens_details": {
    "reasoning_tokens": 162
  },
  "total_tokens": 1691
}
```

这条真实终态中没有 `cache_write_tokens`。因此本次请求可以确认使用了缓存，缓存读取量为 `1408`，未命中输入为 `120`；不能确认有多少 token 被写入缓存，也不能确认这 `120` 个未命中 token 是否成功写入缓存。

该结论是当前实例、当前模型和这一次终态响应的直接观测，不扩张为所有 Grok 版本或所有请求的永久协议合同。后续若要升级为更强的 provider-wide 结论，必须采集多条原始终态并按模型、请求形状和缓存状态分别比较。

## 另一条 Anthropic 兼容请求

随后通过同一实例另发了一条 Anthropic `/v1/messages` 请求，返回的 usage 是：

```json
{
  "input_tokens": 120,
  "cache_read_input_tokens": 1408,
  "cache_creation_input_tokens": 0,
  "output_tokens": 272
}
```

这不是上一节 `/v1/responses` 响应的同一条投影；两次请求的 `output_tokens` 分别是 `163` 和 `272`。这里的 `cache_creation_input_tokens: 0` 是 Anthropic wire contract 所需的兼容投影，不是上游 Grok 对缓存写入为零的观测。原始 Responses usage 中缺失的写入字段必须在 exact observation 中保持缺失，不能把兼容零当作 provider fact。

## 对日志和转换的影响

- `cached_tokens > 0` 可以作为本次请求发生缓存命中的直接证据。
- `cached_tokens == 0` 只能表示本次没有读取缓存，不能证明缓存没有建立或写入量为零。
- 缺少 `cache_write_tokens` 时，normalized fresh input 可以在算术上把缺失的另一 cache 分量按零处理，以保留 `input_tokens - cached_tokens`；exact usage 仍必须保留该字段为未观测。
- 当前日志中的 `+0` 必须结合字段来源解释，不能单独读成“缓存写入为零”。

## 证据边界

工作区已有的真实 Responses captures 来自其他模型，部分同时包含 `cached_tokens` 和 `cache_write_tokens`，不能冒充 Grok 证据。历史库中没有 `grok-4.6` 的可复用原始终态，因此本报告以本次当前实例请求为 ground truth，并明确保留单样本边界。
