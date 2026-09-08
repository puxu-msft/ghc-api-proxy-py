# 候选修订：`upstream-retry-and-continuation.md` — 上游连续失败的退让

**提出日期**：2026-09-08。**状态**：待用户裁决追认。

**触发**：用户指令「上游连续失败时需要简单的退让机制，避免短时间内加剧问题」。

## 与现文冲突的句子

`docs/.human-controlled/upstream-retry-and-continuation.md` 当前写有：

> 如果还没交付过完整块，直接在代理端无痕重试。**无痕重试不设冷却间隔。**

本修订把加粗句限定为：单次失败后的重试仍尽力即时，但**连续**失败时按共享退避拉开间隔。

## 建议替换文（可直接采用）

> 如果还没交付过完整块，直接在代理端无痕重试。无痕重试本身不设冷却间隔；但**上游连续失败时**，由共享的每提供方速率限制器按连续失败次数对下一次尝试做指数退让（`failure_backoff_base_sec` 起，逐次翻倍，至 `failure_backoff_max_sec` 封顶，一次成功即清零），驱动层重试与交付层无痕重放都经它拉开，避免上游挣扎时短时间内加剧其负载。429/502 仍走反应式限流器，`retry-after` 与 `retry_interval` 仍是受限模式等待的权威，退让只会追加、不会缩短它们的等待。
>
> 边界：驱动层 pre-header 重试的等待逐次翻倍；交付层无痕重放的每次重开都会先经一次「响应头成功」，把连续失败清零，因此重放之间的等待恒为 `failure_backoff_base_sec`，不逐次翻倍。若要求撕流重放也指数化，需要单独裁决「成功」的定义（响应头到达不等于回合完整）。

## 配置示例（供 `config.example.yaml` 追认）

```yaml
reactive_rate_limiter:
  # ...原有四项不变...
  # 上游失败后重试的起始等待秒数，逐次连续失败翻倍；0 关闭退让
  # Seconds to wait before the first retry after an upstream failure, doubling per further
  # consecutive failure; 0 disables the backoff
  failure_backoff_base_sec: 0.5
  # 退让等待的封顶秒数
  # Ceiling for the failure backoff wait
  failure_backoff_max_sec: 30.0
```

## 语义要点（裁决时需要确认的边界）

1. **共享与跨请求**：退让计数放在每提供方共享的 `RateLimiter` 上。上游持续失败时，并发/后续请求的第一跳仍立即发出（不在失败前惩罚请求），但彼此的退让窗口互相生效，避免聚合轰炸。
2. **触发范围**：只计入会被重试的上游失败（`classify` 为 RETRY 的 `UpstreamError` 等）；400 之类确定性拒绝、订阅者自己的 `PipelineRetry` 不计入。
3. **与 429/502 的关系**：受限模式等待不变；连续受限足够多次后退让可能超过 `retry_interval`/`request_interval`，这是有意行为（持续限流时进一步降速）。
4. **第一个重试也会等待 base**：现文的「不设冷却间隔」从第一次重试起就被本修订替代。若希望第一次重试保持完全即时、从第二次失败才开始退让，请裁决，实现改为 `base · 2^(failures-2)`（failures ≥ 2）即可。
