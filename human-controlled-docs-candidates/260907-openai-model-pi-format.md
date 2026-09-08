# OpenAI models API 与 Pi agent 兼容格式候选

这是对 `docs/.human-controlled/api.md` 的候选补充，等待用户采纳。

OpenAI 模型列表和单模型详情默认使用 OpenAI 格式：

```http
GET /models
GET /v1/models
GET /openai/v1/models
GET /models/{model}
GET /v1/models/{model}
GET /openai/v1/models/{model}
```

通过 `?format=pi` 请求 Pi agent 模型字段格式。列表仍保留 `{"object":"list","data":[...]}` 外层，单模型详情直接返回一个 Pi model object：

```http
GET /v1/models/gpt-5.6-sol?format=pi
```

Pi model object 使用 `id`、`name`、`api`、`reasoning`、`input`、`contextWindow`、`maxTokens`、`cost` 和 `compat` 字段。`contextWindow`、`maxTokens` 和思考能力来自上游 GHC catalog 的 `capabilities`，无法确认的字段不应被推断。

不识别的 `format` 值返回 400，未知模型返回 404。未提供 `format` 时保持 OpenAI 格式，以免破坏现有客户端。
