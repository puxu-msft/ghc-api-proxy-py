# API 端点

## 模型和模型相关端点

- Anthropic：`POST /v1/messages`、`POST /v1/messages/count_tokens`
- OpenAI：`POST /chat/completions`、`POST /responses`、`POST /embeddings`、`GET /models`
- OpenAI 兼容前缀：同一组端点也注册在 `/v1` 和 `/openai/v1`
- ~~Responses WebSocket：`GET /responses`、`/v1/responses`、`/openai/v1/responses`~~ 暂不支持
- Azure：`POST /openai/deployments/{deployment}/{chat/completions|responses|embeddings}`
- Gemini：`POST /v1beta/models/{model}:{generateContent|streamGenerateContent|countTokens}`

2026-08-16：Responses WebSocket 已在项目内存在，现有代码、测试均保留，**不最终接线**，如果存在陈旧可适当注释掉。

## 运维与调试端点

- 健康检查：`/health/liveness`、`/health/readiness`
- 历史：`/history/api/*`、`/history/ws`
- 指标：`/metrics`
- 状态与配置：`/api/status`、`/api/config`
- 调试取证规则：`GET/POST /api/debug/capture-rules`、`DELETE /api/debug/capture-rules/{id}`；规则按 provider、已解析 model-id、session-id 精确匹配，agent-id 可选
- ~~审批：`/api/approval/*`、`/api/approval/ws`~~ 暂不支持
- ~~Tokenization：`/api/tokenization/calibration`、`/api/tokenization/limits`~~ 暂不支持

### History transport access

- index、普通 detail、`include=semantic` 和 `export=semantic` 是 credential-free History projection，不要求额外 header；
- `GET /history/api/entries/{id}/transport`、`include=transport` 和 `export=full` 可以返回含 credentials 的 transport evidence，默认拒绝；
- operator 必须配置至少 16 字符的 `server.history_export_token`；调用方必须提供匹配的 `X-History-Export-Token`；
- token 未配置、缺失或不匹配时，这些 credential-bearing routes 返回稳定的 `403 access_denied`，不会回显 token、capture 或 credentials；
- listener 是否绑定 loopback 不是授权条件；非 loopback 部署仍须负责 TLS、网络隔离和 secret 轮换。
