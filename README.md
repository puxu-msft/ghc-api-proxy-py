# ghc-api-proxy

Python 3.14 实现的高性能、多协议 GitHub Copilot API 代理。支持 Anthropic Messages、OpenAI Chat Completions / Responses / Embeddings、Azure OpenAI deployment 路径和 Gemini `/v1beta`，并提供认证、审批、历史审计、Prometheus 指标与可选 TUI。

Anthropic 请求支持 typed Hooks 扩展、局部相邻的 client tool-pair 修复，以及上游优先的 token counting。本地 fallback 使用按协议/模型/请求规模学习的校准因子；prompt-limit 错误仅用于观测，不会删除、压缩或摘要历史。代理不实现 Anthropic 原生 server-tool 执行、过滤或降级。

## 安装

```bash
uv sync
```

## 认证与启动

```bash
uv run python -m app auth
uv run python -m app start
```

也可以通过环境变量提供 GitHub token：`COPILOT_API_GITHUB_TOKEN`、`GH_TOKEN` 或 `GITHUB_TOKEN`。配置优先级为：defaults < YAML < environment < CLI。

生成完整默认配置：

```bash
uv run python -m app start --config ./config.yaml --generate-config
```

## 主要端点

- Anthropic：`POST /v1/messages`、`POST /v1/messages/count_tokens`
- OpenAI：`POST /chat/completions`、`POST /responses`、`POST /embeddings`、`GET /models`
- OpenAI 兼容前缀：同一组端点也注册在 `/v1` 和 `/openai/v1`
- Responses WebSocket：`GET /responses`、`/v1/responses`、`/openai/v1/responses`
- Azure：`POST /openai/deployments/{deployment}/{chat/completions|responses|embeddings}`
- Gemini：`POST /v1beta/models/{model}:{generateContent|streamGenerateContent|countTokens}`

## 运维端点

- 健康检查：`/health/liveness`、`/health/readiness`
- 历史：`/history/api/*`、`/history/ws`
- 审批：`/api/approval/*`、`/api/approval/ws`
- 指标：`/metrics`
- 状态与配置：`/api/status`、`/api/config`
- Tokenization：`/api/tokenization/calibration`、`/api/tokenization/limits`

`/api/config` 会脱敏 GitHub token 和上游 API key。OpenTelemetry 自动 instrumentation 默认关闭，通过 `observability.tracing_enabled` 显式启用。

## 开发验证

```bash
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

详细架构、专题设计和实施记录位于 [docs/2604-rewrite](docs/2604-rewrite)。
Hooks 用法见 [docs/2604-rewrite/hooks-system.md](docs/2604-rewrite/hooks-system.md)，计数与校准见 [docs/2604-rewrite/tokenization.md](docs/2604-rewrite/tokenization.md)。
