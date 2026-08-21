# ghc-api-proxy

Python 实现的 GitHub Copilot API 代理，取代 JS 旧版（copilot-api-js）。

## 作为服务器，提供

### 主要模型端点

- Anthropic：`POST /v1/messages`、`POST /v1/messages/count_tokens`
- OpenAI：`POST /chat/completions`、`POST /responses`、`POST /embeddings`、`GET /models`
- OpenAI 兼容前缀：同一组端点也注册在 `/v1` 和 `/openai/v1`
- ~~Responses WebSocket：`GET /responses`、`/v1/responses`、`/openai/v1/responses`~~ 暂不支持
- Azure：`POST /openai/deployments/{deployment}/{chat/completions|responses|embeddings}`
- Gemini：`POST /v1beta/models/{model}:{generateContent|streamGenerateContent|countTokens}`

这些端点可以指定具体的模型，根据 GHC API 的现状，提供直连路径或翻译路径。

### 运维端点

- 健康检查：`/health/liveness`、`/health/readiness`
- 历史：`/history/api/*`、`/history/ws`
- 指标：`/metrics`
- 状态与配置：`/api/status`、`/api/config`
- ~~审批：`/api/approval/*`、`/api/approval/ws`~~ 暂不支持
- ~~Tokenization：`/api/tokenization/calibration`、`/api/tokenization/limits`~~ 暂不支持

`/api/config` 会脱敏 GitHub token 和上游 API key。OpenTelemetry 自动 instrumentation 默认关闭，通过 `observability.tracing_enabled` 显式启用。

## 使用

```bash
# 直接提供 GitHub token，从 GitHub 获取和启用
GHC_API_PROXY_GITHUB_TOKEN=ghu_...
uvx --from git+https://github.com/puxu-msft/ghc-api-proxy-py.git --refresh ghc-api-proxy start --port 4141

# device-code 认证，会写入 ~/.local/share/ghc-api-proxy/github_token
ghc-api-proxy auth

# 生成完整默认配置（文件已存在时需二次确认）
ghc-api-proxy gen-config ~/.local/share/ghc-api-proxy/config.yaml
```
