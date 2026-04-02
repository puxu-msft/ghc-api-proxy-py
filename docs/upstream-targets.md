# 上游目标系统

## 概述

上游目标系统（`upstream/`）负责管理与后端 API 服务的通信。通过 `UpstreamTarget` 协议抽象，系统支持多种上游实现：

- **Copilot 上游**（默认）：连接 GitHub Copilot 后端，使用 GitHub token 认证
- **Generic 上游**：连接任意 OpenAI/Anthropic 兼容服务，使用 API key 认证

## UpstreamTarget 协议

所有上游目标必须实现此协议：

```python
from typing import Protocol, AsyncIterator
import httpx

class UpstreamTarget(Protocol):
    """上游目标统一接口。"""

    @property
    def target_type(self) -> str:
        """目标类型标识，如 "copilot" 或 "generic"。"""
        ...

    async def send_openai(
        self,
        path: str,
        payload: dict,
        *,
        stream: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发送请求到 OpenAI-compatible 端点。"""
        ...

    async def send_anthropic(
        self,
        path: str,
        payload: dict,
        *,
        stream: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发送请求到 Anthropic-compatible 端点。"""
        ...

    async def send_responses(
        self,
        path: str,
        payload: dict,
        *,
        stream: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发送请求到 OpenAI Responses API 端点。"""
        ...

    async def get_models(self) -> list[ModelInfo]:
        """获取上游可用模型列表。"""
        ...

    def supports_anthropic_endpoint(self, model_id: str) -> bool:
        """检查指定模型是否支持直接 Anthropic 端点。"""
        ...

    def supports_responses_endpoint(self, model_id: str) -> bool:
        """检查指定模型是否支持 Responses API 端点。"""
        ...

    async def close(self) -> None:
        """关闭底层连接。"""
        ...
```

## Copilot 上游

### 认证流程

```
用户 GitHub Token
    │
    ▼
GitHub API: GET /user
    │ 验证 token 有效性
    ▼
Copilot Token API: GET /copilot_internal/v2/token
    │ 交换为 Copilot 短期 token
    ▼
Copilot Token（含到期时间）
    │
    ├─ 正常使用：注入到每个请求的 Authorization 头
    └─ 自动刷新：到期前 5 分钟自动重新交换
```

### GitHub Token 获取

`auth/manager.py` 按以下优先级获取 GitHub token：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | CLI `--github-token` | 命令行直接传入 |
| 2 | 环境变量 `GITHUB_TOKEN` | 适合 CI/CD 环境 |
| 3 | 文件存储 | `~/.config/ghc-api-proxy/github_token` |
| 4 | Device Flow | 交互式授权，获取后自动存储到文件 |

### GitHub Device Flow

```
1. POST https://github.com/login/device/code
   scope=user:email
   → 返回 {device_code, user_code, verification_uri}

2. 提示用户：
   "请访问 https://github.com/login/device 并输入代码: XXXX-XXXX"

3. 轮询 POST https://github.com/login/oauth/access_token
   device_code=...
   → 等待用户授权
   → 返回 {access_token}

4. 存储 token 到文件
```

### Copilot Token 交换

```python
# auth/copilot.py 核心逻辑

class CopilotAuth:
    def __init__(self, github_token: str, settings: AppSettings):
        self._github_token = github_token
        self._copilot_token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """获取有效的 Copilot token，必要时自动刷新。"""
        if self._is_token_valid():
            return self._copilot_token
        async with self._lock:
            if self._is_token_valid():  # double-check
                return self._copilot_token
            await self._refresh()
            return self._copilot_token

    async def _refresh(self) -> None:
        """交换 GitHub token 为 Copilot token。"""
        # GET https://api.github.com/copilot_internal/v2/token
        # Authorization: token {github_token}
        # → {"token": "...", "expires_at": 1234567890}
        ...

    def _is_token_valid(self) -> bool:
        """token 是否在有效期内（提前 5 分钟失效）。"""
        return self._copilot_token and time.time() < self._expires_at - 300
```

### 模型发现（通过 GitHub Token）

Copilot 上游通过 GitHub API 获取可用模型列表：

```
GET https://api.github.com/copilot_internal/v2/models
Authorization: token {github_token}
→ 返回模型列表（含 capabilities、supported_endpoints）
```

此 API 返回的模型信息包括：
- `id`：模型标识（如 `claude-sonnet-4-5-20250514`）
- `name`：显示名称
- `version`：版本标识（可能与 id 不同）
- `vendor`：供应商（`"Anthropic"` / `"OpenAI"` / `"Google"`）
- `model_picker_category`：分类（`"powerful"` / `"versatile"` / `"lightweight"`）
- `preview`：是否为预览版
- `capabilities`：支持的能力（tool_calls, vision, thinking, adaptive_thinking, structured_outputs 等）
  - `limits`：token 限制（max_context_window_tokens, max_prompt_tokens, max_output_tokens 等）
  - `supports`：功能标记
- `supported_endpoints`：支持的端点类型（`/chat/completions`, `/v1/messages`, `/responses`）
  - **注意：** 部分模型可能仅支持 `/responses`，部分旧模型无此字段（隐式仅 `/chat/completions`）
- `billing`：计费信息（is_premium, multiplier, restricted_to 订阅等级）
- `policy`：策略信息（state, terms）

这些信息用于：
1. `GET /v1/models` 端点返回
2. `model_resolver` 进行名称映射时验证模型存在
3. 路由决策：选择最优上游端点
4. Thinking 模式选择：adaptive vs enabled
5. 计费和配额管理

### 请求头构建

Copilot 上游模拟 VSCode Copilot Chat 扩展的请求头：

```python
def build_headers(self, request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {copilot_token}",
        "X-Request-Id": request_id,
        "X-GitHub-Api-Version": self.settings.api_version,  # "2025-05-01"
        "editor-version": f"vscode/{self.settings.vscode_version}",
        "editor-plugin-version": f"copilot-chat/{self.settings.copilot_version}",
        "copilot-integration-id": "vscode-chat",
        "openai-intent": "conversation-panel",
        "content-type": "application/json",
        "user-agent": f"GitHubCopilotChat/{self.settings.copilot_version}",
    }
```

### Anthropic Beta 请求头

对 Messages API（`/v1/messages`）请求，Copilot 上游需注入 `anthropic-beta` 请求头以启用特定功能：

```python
def build_anthropic_beta_headers(self, model_info: ModelInfo) -> dict[str, str]:
    """构建 Messages API 特定的 beta 功能头。"""
    betas = []

    # 交错思考（非 adaptive 模式的模型需要此 beta）
    if model_info.capabilities.supports_thinking and not model_info.capabilities.supports_adaptive_thinking:
        betas.append("interleaved-thinking-2025-05-14")

    # 上下文管理
    betas.append("context-management-2025-06-27")

    # 高级工具使用（服务端工具搜索等）
    betas.append("advanced-tool-use-2025-11-20")

    return {"anthropic-beta": ",".join(betas)} if betas else {}
```

### Thinking 双模式

Copilot 上游支持两种 Thinking 模式，根据模型能力自动选择：

| 模式 | 条件 | payload 格式 | 说明 |
|------|------|-------------|------|
| **Adaptive** | `supports_adaptive_thinking=True` | `{"thinking": {"type": "adaptive"}}` | 模型自行决定是否思考，无需 budget |
| **Enabled** | `supports_thinking=True` | `{"thinking": {"type": "enabled", "budget_tokens": N}}` | 显式指定 budget，受 min/max 约束 |

```python
def build_thinking_config(self, model_info: ModelInfo, requested_budget: int | None) -> dict | None:
    """根据模型能力构建 thinking 配置。"""
    caps = model_info.capabilities

    if caps.supports_adaptive_thinking:
        # Adaptive 模式：模型自行决策，不需要 budget
        return {"type": "adaptive"}

    if caps.supports_thinking and requested_budget:
        # Enabled 模式：显式 budget，约束在 min/max 之间
        budget = requested_budget
        if caps.min_thinking_budget:
            budget = max(budget, caps.min_thinking_budget)
        if caps.max_thinking_budget:
            budget = min(budget, caps.max_thinking_budget)
        return {"type": "enabled", "budget_tokens": budget}

    return None
```

Copilot 上游使用两个后端端点：

| 端点 | 路径 | 用途 |
|------|------|------|
| OpenAI Chat Completions | `https://api.individual.githubcopilot.com/chat/completions` | 所有模型 |
| Anthropic Messages | `https://api.individual.githubcopilot.com/v1/messages` | Claude 系列模型 |
| OpenAI Responses | `https://api.individual.githubcopilot.com/responses` | 支持 Responses API 的模型 |

基础 URL 根据 `account_type` 变化：
- `individual` → `api.individual.githubcopilot.com`
- `business` → `api.business.githubcopilot.com`
- `enterprise` → `api.enterprise.githubcopilot.com`

## Generic 上游

通用上游连接任意 OpenAI/Anthropic 兼容服务。

### 配置

```yaml
upstream:
  type: generic
  openai_base_url: "https://api.openai.com"       # OpenAI-compatible 端点
  anthropic_base_url: "https://api.anthropic.com"  # Anthropic-compatible 端点
  api_key: "sk-..."                                # API key
  auth_type: "bearer"                              # bearer | x-api-key
```

### 请求头构建

```python
def build_headers(self, request_id: str) -> dict[str, str]:
    headers = {
        "X-Request-Id": request_id,
        "Content-Type": "application/json",
    }
    if self.auth_type == "bearer":
        headers["Authorization"] = f"Bearer {self.api_key}"
    elif self.auth_type == "x-api-key":
        headers["x-api-key"] = self.api_key
    return headers
```

### 模型发现

通用上游通过标准 OpenAI API 获取模型：

```
GET {openai_base_url}/v1/models
Authorization: Bearer {api_key}
```

如果上游不支持模型列表端点，可在配置中手动指定：

```yaml
upstream:
  type: generic
  models:
    - id: "gpt-4o"
      name: "GPT-4o"
      supported_endpoints: ["/chat/completions"]
    - id: "claude-sonnet-4-5-20250514"
      name: "Claude Sonnet 4.5"
      supported_endpoints: ["/chat/completions", "/v1/messages"]
```

## HTTP 客户端

### 连接池配置

```python
# upstream/client.py

class UpstreamClient:
    def __init__(self, settings: AppSettings):
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,  # 秒
            ),
            timeout=httpx.Timeout(
                connect=10.0,
                read=300.0,    # LLM 响应可能很慢
                write=10.0,
                pool=30.0,
            ),
            http2=True,         # 启用 HTTP/2
            follow_redirects=True,
        )
```

### 流式响应

对于 `stream=true` 的请求，httpx 使用 `stream()` 上下文管理器：

```python
async def send_streaming(self, method, url, **kwargs) -> AsyncIterator[bytes]:
    async with self._client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            yield chunk
```

### 优雅关闭

```python
async def close(self) -> None:
    await self._client.aclose()
```

## 智能路由

路由层根据模型的 `supported_endpoints` 和客户端请求格式决定使用哪个上游端点。

### 端点选择优先级

对于每个请求，系统按以下优先级选择上游端点：

```
1. 模型仅支持 /responses → 必须使用 /responses（无回退）
2. 模型支持 /responses → 优先使用 /responses
3. 模型支持 /v1/messages（如 Claude 系列）→ 使用 /v1/messages
4. 默认 → /chat/completions
5. 无 supported_endpoints 字段的旧模型 → 隐式仅支持 /chat/completions
```

**重要：** 部分模型（如 gpt-5.x-codex 系列）**仅**支持 `/responses` 端点，没有 `/chat/completions` 回退。代理必须能原生处理 Responses 格式，不能假设 Chat Completions 是通用回退。

### 各入口的路由决策

```
请求到达 /v1/chat/completions（OpenAI Chat 格式）
    │
    ├─ 模型仅支持 /responses？
    │   └─ 是 → 翻译为 Responses 格式
    │           → 发到上游 /responses 端点
    │           → 响应翻译回 Chat Completions 格式
    │
    ├─ 模型支持 /responses？（优先）
    │   └─ 是 → 翻译为 Responses 格式
    │           → 发到上游 /responses 端点
    │           → 响应翻译回 Chat Completions 格式
    │
    └─ 其他 → 直接转发到上游 /chat/completions 端点

请求到达 /v1/messages（Anthropic 格式）
    │
    ├─ 模型仅支持 /responses？
    │   └─ 是 → 翻译为 Responses 格式 → /responses → 翻译回 Anthropic
    │
    ├─ 模型支持 /v1/messages？
    │   └─ 是（如 Claude 系列）→ 直接转发到上游 Anthropic 端点
    │
    ├─ 模型支持 /responses？
    │   └─ 是 → 翻译为 Responses 格式 → /responses → 翻译回 Anthropic
    │
    └─ 否 → 翻译为 Chat Completions 格式
            → 发到上游 /chat/completions 端点
            → 响应翻译回 Anthropic 格式

请求到达 /v1/responses（OpenAI Responses 格式）
    │
    ├─ 模型支持 /responses？
    │   └─ 是 → 直接转发到上游 /responses 端点
    │
    ├─ 模型支持 /v1/messages？
    │   └─ 是 → 翻译为 Anthropic 格式 → /v1/messages → 翻译回 Responses
    │
    └─ 否 → 翻译为 Chat Completions 格式
            → 发到上游 /chat/completions 端点
            → 响应翻译回 Responses 格式
```

### 非 Chat 模型处理

| 模型类型 | 处理方式 |
|----------|---------|
| `type: "chat"` | 正常路由（如上） |
| `type: "embeddings"` | 仅支持 `/v1/embeddings` 端点，不经过代理路由 |
| `type: "completion"` | 仅支持 `/v1/completions` 端点，不经过代理路由 |

代理仅代理 chat 类型模型的请求。嵌入和补全类型的模型在 `GET /v1/models` 中返回，但不支持通过代理的聊天端点发送请求。

## 相关文档

- [整体架构概览](architecture.md)
- [配置系统](config-system.md)
- [请求执行管道](request-pipeline.md)
- [转换系统](transform-system.md)
