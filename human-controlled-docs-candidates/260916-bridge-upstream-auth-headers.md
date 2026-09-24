# bridge provider 上游鉴权头配置候选

> 候选材料，不是用户控制的 Spec。用户确认后再摘取到 `docs/.human-controlled/config.example.yaml`。

bridge 上游的鉴权头由**协议**决定，不由 provider 决定：

| 腿 | 默认鉴权头 |
|---|---|
| Anthropic Messages（含 `count_tokens`） | `x-api-key: <api_key>` |
| OpenAI Chat Completions / Responses / Embeddings | `Authorization: Bearer <api_key>` |
| `GET /models` | `Authorization: Bearer <api_key>` |

此前 Anthropic Messages 腿也发 `Authorization: Bearer`，对只认 `x-api-key` 的上游必然失败（opencode Zen 实测回 `401 AuthError "Missing API key."`）。自 2026-09-16 起该腿改为 `x-api-key`。

两个可选布尔字段在默认之上**追加**头：

```yaml
model_providers:
  opencode:
    type: bridge
    api_base_url: "https://opencode.ai/zen/go/v1"
    api_key: "your-opencode-go-api-key"

    openai_responses_endpoint: true
    anthropic_messages_endpoint: true

    # 在 Anthropic Messages 腿上「额外」发 Authorization: Bearer。
    # OpenAI 腿本来就发 Bearer，此字段对它们无作用。
    # add_header_authorization: true

    # 所有腿「额外」发 x-opencode-session: <会话标识>。
    # 供按会话路由或 prompt cache 的网关使用，例如 opencode Zen 的 Go 档。
    # add_header_x_opencode_session: true
```

规则：

- 两个字段默认 `false`；置 `true` 是追加，不是替换，Anthropic Messages 腿的 `x-api-key` 不会因为 `add_header_authorization: true` 而消失。
- `x-opencode-session` 的取值优先本次请求的会话 identity（客户端会话头，如 `x-claude-code-session-id` / `x-session-id` 解析而来）；没有会话 identity 时回落到该 client 一个进程内稳定的 id，因此该头在开启后总是存在。客户端没有上送会话 id 时，同一客户端的所有会话会共用一个 id。
- 这两个字段与 `api_base_url`、`api_key`、三个 endpoint 字段一样，**不支持热重载（需重启）**。
- 调用方请求头**无法**覆盖 `x-api-key`、`Authorization`、`x-opencode-session` 三个头中的任何一个。
- `api_key` 为空时不发任何鉴权头。
- opencode Zen 的 Go 档（`/zen/go/v1`）要求 `x-opencode-session`，缺它返回 `400 MissingSessionID`；其模型分散在三种协议上（`/responses`、`/chat/completions`、`/messages`），只声明其中一部分会让其余模型在 `GET /models` 里可见但不可达；此时需按实际要用的模型把三个 endpoint 字段都声明上。
