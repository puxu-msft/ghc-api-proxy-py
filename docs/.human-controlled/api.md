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
- ~~审批：`/api/approval/*`、`/api/approval/ws`~~ 暂不支持
- ~~Tokenization：`/api/tokenization/calibration`、`/api/tokenization/limits`~~ 暂不支持
