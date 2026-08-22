# GHC API 模型提供方

位于模块 `app.model_provider.ghc_client`，它是 GHC API 的客户端实现，提供了多种不同格式的模型端点，从抽象接口的不同模型请求格式的入口接入，构造最终上游模型请求。

子模块 `auth` 负责认证逻辑，主要包括：

1. 使用 device code 流程获取 github_token
2. 使用 github_token 换取 copilot_token

GHC API 根据账户类型使用不同的 API Base URL：

| 账户类型 | API Base URL | 说明 |
|----------|-------------|------|
| `individual` | `api.githubcopilot.com` | 个人订阅 |
| `business` | `api.business.githubcopilot.com` | 企业团队版 |
| `enterprise` | `api.enterprise.githubcopilot.com` | 企业高级版 |
| self-hosted | `msft.ghe.com` | 自托管版，必须显式配置 |

如未配置，根据用户订阅自动识别选择。

根据 GHC API 的现状，提供这些直连路径：

| 上游模型端点 | 驱动模块 | 说明 |
|--------------|----------|------|
| `POST /v1/messages` `POST /v1/messages/count_tokens` | `direct_driver.anthropic_messages` | Anthropic 模型都具备该端点 |
| `POST /chat/completions` | `direct_driver.openai_chat_completions` | 部分 OpenAI 模型具备该端点 |
| `POST /responses` | `direct_driver.openai_responses` | 部分 OpenAI 模型具备该端点 |
| `ws:/responses` | 暂不支持 | 支持 `POST /responses` 的 OpenAI 模型具备该端点 |
| `POST /embeddings` | `direct_driver.openai_embeddings` | 部分 embeddings 模型具备该端点 |

2026-08-16：Responses WebSocket 已在项目内存在，现有代码、测试均保留，**不最终接线**，如果存在陈旧可适当注释掉。
