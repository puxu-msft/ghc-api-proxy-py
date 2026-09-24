# bridge provider 的 Responses reasoning effort 配置候选

> 候选材料，不是用户控制的 Spec。用户确认后再摘取到 `docs/.human-controlled/config.example.yaml`。

当 bridge 上游的 `/models` catalog 没有提供
`capabilities.supports.reasoning_effort` 时，可在对应 provider 下按 **resolved model id**
声明该上游实际接受的 Responses effort 集合：

```yaml
model_providers:
  ttthree:
    type: bridge
    api_base_url: "https://sub2api.example/v1"
    openai_responses_endpoint: true
    reasoning_efforts:
      glm-5.3-flash: [high, xhigh]
```

规则：

- `glm-5.3-flash` 必须是上游实际收到的 resolved id，不是客户端别名或 `provider/model` 限定名。
- catalog 已发布 `reasoning_effort` 时，以 catalog 为准；配置只补 catalog 完全缺失的情况。
- catalog 发布空列表时表示该模型不支持 effort，配置不会覆盖它。
- 没有 catalog 能力、也没有配置 fallback 时，代理继续不发送 effort，并在 structured request record 中保留 `reasoning_effort: null` 与 conversion loss。
- 修改该 map 需要重启，因为 provider 的 resolved descriptors 在 provider 实例中构造。
## Review clarifications

- Reject leading or trailing whitespace in both resolved model keys and effort values.
- Provider-bound effort observation covers Responses `reasoning.effort`, Chat Completions `reasoning_effort`, Command Code `reasoning_effort`, and Anthropic `thinking` / `output_config.effort`; explicit `none` remains distinct from an absent field.
