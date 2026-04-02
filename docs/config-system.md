# 配置系统

## 概述

配置系统（`config/`）提供三层合并的配置管理，优先级从低到高：

```
默认值 < YAML 配置文件 < 环境变量 < CLI 参数
```

使用 Pydantic v2 `BaseSettings` 作为核心，自动支持环境变量读取和类型验证。

## 三层合并机制

### 加载流程

```
1. Pydantic BaseSettings 实例化
   ├─ 加载内置默认值
   └─ 自动读取环境变量（前缀 GHC_）

2. 检查 YAML 配置文件
   ├─ CLI 指定路径 → 使用指定路径
   ├─ 环境变量 GHC_CONFIG → 使用指定路径
   └─ 默认路径 ~/.config/ghc-api-proxy/config.yaml
   │
   └─ 文件存在 → 解析 YAML → 覆盖对应字段

3. CLI 参数覆盖
   └─ argparse 解析的非 None 参数 → 覆盖对应字段

4. 返回最终 AppSettings 实例
```

### loader.py 核心逻辑

```python
def load_settings(
    cli_args: argparse.Namespace | None = None,
) -> AppSettings:
    """加载并合并三层配置。"""

    # 1. 默认值 + 环境变量（Pydantic 自动处理）
    settings_dict: dict = {}

    # 2. YAML 配置文件
    config_path = _resolve_config_path(cli_args)
    if config_path and config_path.exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f) or {}
        settings_dict = _deep_merge(settings_dict, yaml_config)

    # 3. CLI 参数
    if cli_args:
        cli_overrides = _cli_to_dict(cli_args)
        settings_dict = _deep_merge(settings_dict, cli_overrides)

    # 4. 构建 Settings（env vars 由 Pydantic 自动处理）
    return AppSettings(**settings_dict)

def _deep_merge(base: dict, override: dict) -> dict:
    """递归深度合并，override 优先。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

## AppSettings 完整定义

```python
from pydantic_settings import BaseSettings
from pydantic import Field

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GHC_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # ── 服务器 ──────────────────────────────

    host: str = "127.0.0.1"
    port: int = 8313
    debug: bool = False

    # ── 上游目标 ────────────────────────────

    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)

    # ── 认证（Copilot 专用）─────────────────

    auth: AuthConfig = Field(default_factory=AuthConfig)

    # ── 请求头伪装（Copilot 专用）───────────

    headers: HeadersConfig = Field(default_factory=HeadersConfig)

    # ── 模型映射 ────────────────────────────

    model_mappings: ModelMappingsConfig = Field(default_factory=ModelMappingsConfig)

    # ── 系统提示词 ──────────────────────────

    system_prompt: SystemPromptConfig = Field(default_factory=SystemPromptConfig)

    # ── 功能开关 ────────────────────────────

    features: FeaturesConfig = Field(default_factory=FeaturesConfig)

    # ── 历史记录 ────────────────────────────

    history: HistoryConfig = Field(default_factory=HistoryConfig)

    # ── 限流 ────────────────────────────────

    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # ── 审批 ────────────────────────────────

    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)

    # ── 可观测性 ────────────────────────────

    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
```

### 子配置模型

```python
class UpstreamConfig(BaseModel):
    type: Literal["copilot", "generic"] = "copilot"

    # Generic 上游专用
    openai_base_url: str = ""             # OpenAI-compatible 端点基础 URL
    anthropic_base_url: str = ""          # Anthropic-compatible 端点基础 URL
    api_key: str = ""                     # API key
    auth_type: Literal["bearer", "x-api-key"] = "bearer"

    # 手动指定模型列表（Generic 上游不支持 /v1/models 时）
    models: list[ManualModelConfig] = []

    # 连接配置
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: int = 30            # 秒
    connect_timeout: float = 10.0         # 秒
    read_timeout: float = 300.0           # 秒
    http2: bool = True

class AuthConfig(BaseModel):
    github_token: str = ""                # 直接指定 GitHub token
    account_type: Literal["individual", "business", "enterprise"] = "individual"
    token_file: str = ""                  # token 文件路径（覆盖默认路径）

class HeadersConfig(BaseModel):
    vscode_version: str = "1.99.0"
    copilot_version: str = "0.25.2025020601"
    api_version: str = "2025-05-01"

class ModelMappingsConfig(BaseModel):
    aliases: dict[str, str] = {
        "opus": "claude-opus-4.6",
        "sonnet": "claude-sonnet-4.5",
        "haiku": "claude-haiku-4.5",
    }
    preferences: dict[str, list[str]] = {}

class SystemPromptConfig(BaseModel):
    prepend: str = ""                     # 前置文本
    append: str = ""                      # 追加文本
    overrides: list[OverrideRule] = []    # 替换规则列表

class OverrideRule(BaseModel):
    from_pattern: str = Field(alias="from")  # 原文本/正则
    to: str                                  # 替换文本
    method: Literal["line", "regex"] = "line"

class FeaturesConfig(BaseModel):
    auto_truncate: bool = True            # 自动截断重试
    redirect_anthropic: bool = True       # Claude 模型使用 Anthropic 端点
    prefer_responses: bool = True         # 优先使用 /responses 端点（若模型支持）
    orphan_cleanup: bool = True           # 自动清理孤立 tool 块
    thinking_budget_tokens: int | None = None  # 默认 thinking budget（可被请求级覆盖）
    anthropic_beta_features: list[str] = [     # Anthropic beta 功能头
        "interleaved-thinking-2025-05-14",
        "context-management-2025-06-27",
        "advanced-tool-use-2025-11-20",
    ]

class HistoryConfig(BaseModel):
    max_entries: int = 200                # 最大存储条目数
    websocket: bool = True                # 启用 WebSocket 推送

class RateLimitConfig(BaseModel):
    base_retry_seconds: float = 10        # 基础退避时间
    max_retry_seconds: float = 120        # 最大退避时间
    request_interval_seconds: float = 10  # 恢复阶段请求间隔
    recovery_timeout_minutes: float = 10  # 限流状态自动恢复超时
    consecutive_successes: int = 5        # 恢复所需连续成功次数

class ApprovalConfig(BaseModel):
    enabled: bool = False                 # 是否启用手动审批
    timeout_seconds: float = 300          # 审批超时（秒）

class ObservabilityConfig(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "text"  # json 用于生产环境
    tracing_enabled: bool = False
    tracing_endpoint: str = ""            # OTLP exporter endpoint

class ManualModelConfig(BaseModel):
    id: str
    name: str = ""
    supported_endpoints: list[str] = ["/chat/completions"]
```

## YAML 配置文件完整格式

```yaml
# ghc-api-proxy 配置文件
# 放置于 ~/.config/ghc-api-proxy/config.yaml

# ── 服务器 ──────────────────────────────
host: "127.0.0.1"
port: 8313
debug: false

# ── 上游目标 ────────────────────────────
upstream:
  type: copilot                    # copilot | generic

  # --- Generic 上游专用 ---
  # openai_base_url: "https://api.openai.com"
  # anthropic_base_url: "https://api.anthropic.com"
  # api_key: "sk-..."
  # auth_type: bearer              # bearer | x-api-key
  # models:                        # 手动指定模型（可选）
  #   - id: "gpt-4o"
  #     name: "GPT-4o"
  #     supported_endpoints: ["/chat/completions"]

  # --- 连接配置 ---
  max_connections: 100
  max_keepalive_connections: 20
  keepalive_expiry: 30
  connect_timeout: 10.0
  read_timeout: 300.0
  http2: true

# ── 认证（Copilot 专用）─────────────────
auth:
  github_token: ""                 # 留空则使用文件存储或 device flow
  account_type: individual         # individual | business | enterprise
  # token_file: ""                 # 覆盖默认 token 文件路径

# ── 请求头伪装（Copilot 专用）───────────
headers:
  vscode_version: "1.99.0"
  copilot_version: "0.25.2025020601"
  api_version: "2025-05-01"

# ── 模型映射 ────────────────────────────
model_mappings:
  aliases:
    opus: claude-opus-4.6
    sonnet: claude-sonnet-4.5
    haiku: claude-haiku-4.5

  preferences:
    opus:
      - claude-opus-4.6
      - claude-opus-4.5
    sonnet:
      - claude-sonnet-4.5
      - claude-sonnet-4

# ── 系统提示词 ──────────────────────────
system_prompt:
  prepend: ""                      # 在系统提示词前插入
  append: ""                       # 在系统提示词后追加

  overrides:                       # 替换规则
    # - from: "原始文本"
    #   to: "替换文本"
    #   method: line               # line | regex
    # - from: "pattern\\s+(\\w+)"
    #   to: "replacement \\1"
    #   method: regex

# ── 功能开关 ────────────────────────────
features:
  auto_truncate: true              # 413 时自动截断重试
  redirect_anthropic: true         # Claude 模型走 Anthropic 端点
  prefer_responses: true           # 优先使用 /responses 端点（若模型支持）
  orphan_cleanup: true             # 自动清理孤立 tool 块
  thinking_budget_tokens: null     # 默认 thinking budget（null=不设置）
  anthropic_beta_features:         # Anthropic beta 功能头
    - "interleaved-thinking-2025-05-14"
    - "context-management-2025-06-27"
    - "advanced-tool-use-2025-11-20"

# ── 历史记录 ────────────────────────────
history:
  max_entries: 200                 # 最大存储条目数
  websocket: true                  # 启用 WebSocket 推送

# ── 限流 ────────────────────────────────
rate_limit:
  base_retry_seconds: 10
  max_retry_seconds: 120
  request_interval_seconds: 10
  recovery_timeout_minutes: 10
  consecutive_successes: 5

# ── 审批 ────────────────────────────────
approval:
  enabled: false                   # 启用手动审批
  timeout_seconds: 300             # 审批超时（秒）

# ── 可观测性 ────────────────────────────
observability:
  log_level: INFO                  # DEBUG | INFO | WARNING | ERROR
  log_format: text                 # text | json
  tracing_enabled: false
  # tracing_endpoint: ""           # OTLP exporter endpoint
```

## 环境变量映射

Pydantic BaseSettings 使用 `GHC_` 前缀和 `__` 嵌套分隔符：

| 环境变量 | 配置字段 |
|----------|----------|
| `GHC_HOST` | `host` |
| `GHC_PORT` | `port` |
| `GHC_DEBUG` | `debug` |
| `GHC_UPSTREAM__TYPE` | `upstream.type` |
| `GHC_UPSTREAM__OPENAI_BASE_URL` | `upstream.openai_base_url` |
| `GHC_UPSTREAM__API_KEY` | `upstream.api_key` |
| `GHC_AUTH__GITHUB_TOKEN` | `auth.github_token` |
| `GHC_AUTH__ACCOUNT_TYPE` | `auth.account_type` |
| `GHC_FEATURES__AUTO_TRUNCATE` | `features.auto_truncate` |
| `GHC_FEATURES__PREFER_RESPONSES` | `features.prefer_responses` |
| `GHC_FEATURES__THINKING_BUDGET_TOKENS` | `features.thinking_budget_tokens` |
| `GHC_HISTORY__MAX_ENTRIES` | `history.max_entries` |
| `GHC_APPROVAL__ENABLED` | `approval.enabled` |
| `GHC_OBSERVABILITY__LOG_LEVEL` | `observability.log_level` |

特例：`GITHUB_TOKEN` 环境变量也会被 `auth/manager.py` 直接读取（兼容常见约定）。

## CLI 参数

```
usage: ghc-api-proxy [-h] [--config CONFIG] [--host HOST] [--port PORT]
                     [--debug] [--github-token TOKEN]
                     [--account-type {individual,business,enterprise}]
                     [--manual] [--approval-timeout SECONDS]
                     [--verbose] [--generate-config]

可选参数:
  -h, --help            显示帮助信息
  --config CONFIG       YAML 配置文件路径
  --host HOST           监听地址（默认 127.0.0.1）
  --port PORT           监听端口（默认 8313）
  --debug               启用调试模式
  --github-token TOKEN  GitHub token
  --account-type TYPE   Copilot 账户类型
  --manual              启用手动审批
  --approval-timeout S  审批超时秒数
  --verbose, -v         详细日志输出（等同 --log-level DEBUG）
  --generate-config     生成默认配置文件到 ~/.config/ghc-api-proxy/config.yaml
```

### CLI → Settings 映射

```python
def _cli_to_dict(args: argparse.Namespace) -> dict:
    """将 CLI 参数转换为 Settings 字典（仅包含用户显式传入的参数）。"""
    result = {}
    if args.host is not None:
        result["host"] = args.host
    if args.port is not None:
        result["port"] = args.port
    if args.debug:
        result["debug"] = True
    if args.github_token:
        result.setdefault("auth", {})["github_token"] = args.github_token
    if args.account_type:
        result.setdefault("auth", {})["account_type"] = args.account_type
    if args.manual:
        result.setdefault("approval", {})["enabled"] = True
    if args.approval_timeout:
        result.setdefault("approval", {})["timeout_seconds"] = args.approval_timeout
    if args.verbose:
        result.setdefault("observability", {})["log_level"] = "DEBUG"
    return result
```

## 配置文件路径

### paths.py

```python
import platform
from pathlib import Path

def get_config_dir() -> Path:
    """获取配置目录路径。"""
    system = platform.system()
    if system == "Linux":
        return Path.home() / ".config" / "ghc-api-proxy"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ghc-api-proxy"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "ghc-api-proxy"
    return Path.home() / ".ghc-api-proxy"

def get_default_config_path() -> Path:
    return get_config_dir() / "config.yaml"

def get_token_path() -> Path:
    return get_config_dir() / "github_token"
```

## 相关文档

- [整体架构概览](architecture.md)
- [目录结构与模块职责](project-structure.md)
- [上游目标系统](upstream-targets.md)（上游配置详情）
- [转换系统](transform-system.md)（模型映射和提示词配置）
