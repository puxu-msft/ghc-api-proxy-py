# 候选修订：`config.example.yaml` — 加密推理 include 的配置项

**提出日期**：2026-09-08。**状态**：待用户裁决追认。

**触发**：用户指令「添加配置项，可以选择：透传（不添加不剥离）、总是添加、总是剥离」——针对上游 Responses 请求的 `include: ["reasoning.encrypted_content"]`。

## 已实现的配置键

`hook_fix_responses_request` 下新增（默认 `passthrough`，与既有行为逐字一致：翻译腿不发 `include`，原生 `/responses` 腿逐字转发客户端自己的 `include`）：

```yaml
hook_fix_responses_request:
  # ...repair_minted_reasoning_ids 等原有键不变...
  # How `include: ["reasoning.encrypted_content"]` is shaped on every Responses-bound request.
  # Encrypted reasoning is opt-in on the Responses wire: only a request naming the entry in its
  # `include` array gets the opaque seal back; every other spelling returns summary text alone.
  # `passthrough` adds nothing and strips nothing; `always_add` guarantees the entry (what
  # cross-turn reasoning reuse needs on a `store: false` upstream); `always_strip` removes it
  # wherever it appears and drops an `include` key left empty by the removal.
  # 本代理如何为每个发往 Responses 上游的请求塑造 `include: ["reasoning.encrypted_content"]`。
  # 加密推理在该协议上是 opt-in 的：只有 include 数组点名该项的请求才会拿回不透明密封体，
  # 其余拼法只返回明文摘要。`passthrough` 不添加不剥离；`always_add` 保证该项存在
  # （`store: false` 上游跨轮复用推理所必需）；`always_strip` 移除该项，剥离后变空的
  # `include` 键一并移除。
  reasoning_encrypted_include: passthrough  # passthrough | always_add | always_strip
```

## 语义要点（裁决时需要确认的边界）

1. **默认是 `passthrough` 而非 `always_add`**：默认值必须保持现行为不变（翻译腿从不发 `include`；原生腿客户端发了才转发）。要 CLIProxyAPIPlus／sxwxs ghc-api-py 式的「总是请求加密推理」，请显式设 `always_add`。
2. **两条腿都生效**：订阅者挂在 `attempt.prepare`，以路由到的 target format 门控；Anthropic Messages 上游与 Chat Completions 腿无 `include` 概念，天然不作用。
3. **无法识别的 `include` 形状不动**：非 list 的 `include` 原样保留交上游裁决，仅记日志——本代理不替上游发明合同。
4. **`always_strip` 对回传的影响**：上游只返回明文摘要，reasoning-carrier 合同本就接受无 `encrypted_content` 的来源（bare form）；但跨轮推理复用会失效，这是该值的目的本身，不是缺陷。
