# Xingchen provider 配置候选

本文件是供用户摘入 `docs/.human-controlled/config.example.yaml` 的候选材料，不是当前用户控制的配置 authority。

## 候选 YAML 片段

```yaml
model_providers:
  xingchen:
    type: xingchen
    api_base_url: "https://agent.teleai.com.cn/superCowork/sapi/api/v1"

    # 网关没有可用的 /models；必须显式列出允许路由的模型。
    # 大小写不敏感，`.` 与 `-` 等价，因此 `m-1.0` 与 `m-1-0` 不能同时列出。
    models:
      - chat-pro
      - chat-lite

    # 示例文件需要非空占位符才能通过 schema，但不要把真实 credential 提交到仓库。
    # 运行时建议用下面列出的环境变量覆盖这两个值。
    gateway_api_key: "<set-via-environment>"
    x_token: "<set-via-environment>"

    # 来自 TeleAgent device metadata；签名和网关 identity headers 使用原值。
    device_id: "<teleagent-device-id>"
    install_id: "<teleagent-install-id>"

    app_version: "2.4.1"
    route_target: ops-gateway
    client_type: desktop
    user_agent: super-agent/1.0

    disabled_models: []

# 使用多个 provider 时必须明确请求未写 qualifier 时走哪一个。
default_model_provider: ghc
```

## 推荐的 credential 环境变量

```bash
export GHC_API_PROXY_MODEL_PROVIDERS__XINGCHEN__GATEWAY_API_KEY='<gateway-api-key>'
export GHC_API_PROXY_MODEL_PROVIDERS__XINGCHEN__X_TOKEN='<complete-x-token>'
```

YAML 字符串里的 `${VAR}` 不会被通用配置 loader 插值，因此不要写成 `gateway_api_key: ${XINGCHEN_GATEWAY_API_KEY}` 并期待自动展开。

## 能力边界候选说明

- Xingchen 只提供 OpenAI Chat Completions 上游 endpoint。
- 原生客户端入口是 `POST /chat/completions`。
- 当前没有 Anthropic Messages 或 OpenAI Responses 到 Chat 的 translation driver；这些入站格式不能借此 provider 使用 Xingchen。
- `auth`、`login` 与 `logout` 不管理 Xingchen credential；修改 credential 后重启服务。
- Xingchen 使用静态 `models`，不会访问上游 `/models`。
