# Token-counting configuration candidate

> **候选材料，不是人控合同。** 本文只供用户自行摘取到 `docs/.human-controlled/config.example.yaml`；它没有修改、替代或扩张当前人控文档，也不能被实现或评审当成用户已经批准的公开配置说明。行为实现权威暂见 `.dev/docs/token-counting/spec.md`。

## 候选目标

当前人控样例把 `local` 简写为“本地 calibrated tiktoken 估算”。这个描述会掩盖三件已经进入 living Spec 的行为：local 先按结构产生 cold-start prediction；兼容历史存在时按 `history-exact`、`history-prefix`、`profile-calibrated`、`cold-start` 的顺序选择；opaque reasoning、media 和 unknown shape 不作为 ordinary text tokenized bytes，但仍作为 feature 参与低置信预测与后续学习。

下面的 YAML 只提议替换 `inbound.anthropic_count_tokens` 附近的说明。它不增加新的容量配置键，也不改变现有 `providers`、`max_retries` 或 `local_estimate_multiplier` 的数据形状。

```yaml
inbound:
  # POST /v1/messages/count_tokens 的计数器按 providers 顺序懒执行。
  # 非 local 名称选择一个已配置 provider 的计数 transport；每一腿必须针对已经冻结的同一目标 model 和 payload，不能为了计数另行 reroute model。
  # Counters for POST /v1/messages/count_tokens run lazily in providers order.
  # A non-local name selects a configured provider's counting transport for the same frozen target model and payload; counting never reroutes to another model.
  anthropic_count_tokens:
    # local = 本地 best-effort prediction。Responses target 即使含 opaque reasoning、media 或 unknown items，仍返回正整数 input_tokens 和 estimated: true；这些载体的原始 bytes 不按 ordinary text 计数。
    # local = a local best-effort prediction. A Responses target still returns positive input_tokens with estimated: true when opaque reasoning, media, or unknown items are present; their raw bytes are not counted as ordinary text.
    #
    # local 会从同 provider、resolved model、attempt 和实际已发送 payload 的 eligible raw total input usage 自动学习。兼容历史按 history-exact、history-prefix、profile-calibrated、cold-start 的顺序使用；全新或不兼容 identity 回落到 cold-start，而不是把 cold-start 当作终态。
    # local learns automatically from eligible raw total input usage paired with the same provider, resolved model, attempt, and actual sent payload. Compatible history is consulted in history-exact, history-prefix, profile-calibrated, cold-start order; a new or incompatible identity falls back to cold-start rather than treating cold-start as final.
    providers: [ghc, local]
    max_retries: 2

    # 仅对最终 local prediction 施加的 operator bias，默认 1.0；必须是有限且 >= 1.0 的数值。它不缩放 upstream count、不进入 learning label 或 error evaluation，也不替代 exact／prefix／profile 学习。
    # Operator bias applied only to the final local prediction. Default 1.0; it must be finite and >= 1.0. It does not scale upstream counts, enter learning labels or error evaluation, or replace exact/prefix/profile learning.
    # 计算只在一个 finalization boundary 完成：先乘本值，再统一向上取整，最后保证最小值为 1；其它层不得再次舍入。
    # Finalization happens once: multiply by this value, round toward positive infinity, then enforce a minimum of 1. No other layer rounds again.
    local_estimate_multiplier: 1.0
```

## 候选说明的边界

- Public Responses local success 仍只有 `input_tokens` 与 `estimated`，不把 method、confidence reason、history revision 或 learning outcome 增加到 client wire。
- Direct Anthropic upstream count success 不使用 `local_estimate_multiplier`，并按官方 count 协议保留可选 `context_management.original_input_tokens`。
- Learning state 不保存 raw prompt、tool output、opaque carrier 或 media body；它只保存有界 fingerprints、features、counts、provenance 和 errors。
- 这个候选没有承诺误差 SLO，也没有把 recorded forensic evidence、synthetic labels 或 mock upstream 说成 live upstream 准确率证明。
- 用户若不摘取本文，现有 `docs/.human-controlled/config.example.yaml` 继续是配置说明的最终权威；实现文档不得谎称本候选已获人控采纳。
