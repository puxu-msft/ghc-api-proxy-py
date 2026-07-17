# 配置系统

## 概述

配置系统（`config/`）提供四层合并的配置管理：

```
默认值 < YAML 配置文件 < 环境变量 < CLI 参数
```

**本文档是配置的权威清单**：按 section 详列每个配置键（键名、类型、默认值、说明、稳定性标注）。默认值以上游 `copilot-api-js` 的 `CONFIG_MANAGED_DEFAULTS`（`src/lib/state.ts`）与 `config/schema.ts` 为准（`config.example.yaml` 只是示例，不是完整清单）。稳定性标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。

**Python 优化**：上游用全局可变 `state.ts`（`MutableState` + `CONFIG_MANAGED_DEFAULTS` + `resetConfigManagedState()`）承载运行时配置，并背负长串 `CONFIG_MIGRATIONS`（`config/compat.ts`）迁移债。本项目用 frozen Pydantic v2 `AppSettings` + FastAPI 依赖注入，天然不可变、自动校验/序列化；`compat.py` 只保留精简的常见别名迁移，不背上游的历史包袱（见 [BACKLOG.md](BACKLOG.md) 第 6 条）。

## 四层合并机制

### 加载流程

```
1. Pydantic BaseSettings 实例化
   ├─ 加载内置默认值（Settings 类字段默认值，对应上游 CONFIG_MANAGED_DEFAULTS）
   └─ 自动读取环境变量（前缀 GHC_，嵌套分隔符 __）

2. 检查 YAML 配置文件
   ├─ CLI 指定路径（--config）→ 使用指定路径
   ├─ 环境变量 GHC_CONFIG → 使用指定路径
   └─ 默认路径搜索:
   │   ├─ 当前工作目录 ./config.yaml
   │   └─ 用户配置目录 ~/.config/ghc-api-proxy/config.yaml（XDG，见下）
   │
   └─ 文件存在 → 解析 YAML → compat.py 迁移别名键（warn-and-continue）→ 覆盖对应字段

3. CLI 参数覆盖
  └─ Typer 解析的非 None 参数 → 覆盖对应字段

4. 返回最终 frozen AppSettings 实例
```

### loader.py 核心逻辑

```python
def load_settings(
    cli_overrides: Mapping[str, Any] | None = None,
) -> AppSettings:
    """加载并合并四层配置。"""

    # 1. 默认值 + 环境变量（Pydantic 自动处理）
    settings_dict: dict = {}

    # 2. YAML 配置文件
    config_path = _resolve_config_path(cli_args)
    if config_path and config_path.exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f) or {}
        yaml_config = migrate_compat(yaml_config)   # compat.py：警告并迁移弃用键
        settings_dict = _deep_merge(settings_dict, yaml_config)

    # 3. CLI 参数
    if cli_args:
        cli_overrides = _cli_to_dict(cli_args)
        settings_dict = _deep_merge(settings_dict, cli_overrides)

    # 4. 构建 Settings（env vars 由 Pydantic 自动处理）
    return AppSettings(**settings_dict)

def _deep_merge(base: dict, override: dict) -> dict:
    """递归深度合并，override 优先。dict 类型字段（如 model_mappings、effort_overrides）
    per-key 合并；list/scalar 整体替换。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

**per-key vs replace 合并策略**：与上游 `RECORD_MERGE_STRATEGIES`（`config/schema.ts`）对齐——`model_mappings`、`timeouts.stream_idle_overrides`、`timeouts.response_header_overrides` 采用 **per-key 合并**（用户声明的键覆盖内置默认，未声明的内置键保留）；其余 dict 类字段（`anthropic.effort_overrides`、`anthropic.beta_strip_headers` 等）默认 **replace**（用户一旦声明该表即完全接管）。

## AppSettings 顶层结构

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GHC_",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,  # 不可变配置对象，热重载产生新实例
    )

    # ── 服务器（启动期专属，见下）──────────
    host: str = "127.0.0.1"
    port: int = 4141
    debug: bool = False

    # ── 上游目标 ────────────────────────────
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)

    # ── 认证（Copilot 专用，启动期专属）─────
    auth: AuthConfig = Field(default_factory=AuthConfig)

    # ── 请求头伪装（Copilot 专用）───────────
    headers: HeadersConfig = Field(default_factory=HeadersConfig)

    # ── 模型映射 ────────────────────────────
    model_overrides: dict[str, str] = Field(default_factory=lambda: {
        "opus": "claude-opus-4.6",
        "sonnet": "claude-sonnet-4.6",
        "haiku": "claude-haiku-4.5",
    })
    model_mappings: dict[str, str] = Field(default_factory=dict)     # 别名 → 具体模型 ID，per-key 合并
    model_translation: dict[str, list[ModelTranslationRule]] = Field(default_factory=dict)
    disabled_models: list[str] = Field(default_factory=list)
    sanitize_tool_names: bool = False    # 跨协议（Anthropic + Chat Completions + Responses）
    model_refresh_interval: int = 600    # 秒，0=禁用后台刷新

    # ── Anthropic 行为（大 section）─────────
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)

    # ── OpenAI Responses 专用 ───────────────
    openai_responses: ResponsesConfig = Field(default_factory=ResponsesConfig)

    # ── Chat Completions 专用 ───────────────
    chat_completions: ChatCompletionsConfig = Field(default_factory=ChatCompletionsConfig)

    # ── 自适应限流 ──────────────────────────
    rate_limiter: RateLimiterConfig = Field(default_factory=RateLimiterConfig)

    # ── 手动审批（本项目独有）───────────────
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)

    # ── 超时与生命周期 ──────────────────────
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    # ── 关闭 ────────────────────────────────
    shutdown: ShutdownConfig = Field(default_factory=ShutdownConfig)

    # ── 历史记录 ────────────────────────────
    history: HistoryConfig = Field(default_factory=HistoryConfig)

    # ── 可观测性（可选/简化）────────────────
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    # ── 学习式协商 TTL ───────────────────────
    negotiation_learning: NegotiationLearningConfig = Field(default_factory=NegotiationLearningConfig)

    # ── 未知端点日志 ────────────────────────
    unknown_endpoint_logging: UnknownEndpointLoggingConfig = Field(default_factory=UnknownEndpointLoggingConfig)

    # ── 系统提示词 ──────────────────────────
    system_prompt: SystemPromptConfig = Field(default_factory=SystemPromptConfig)
```

---

## 服务器 section（启动期专属，不支持热重载）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | 监听地址；特殊值 `"localhost"`（127.0.0.1 + ::1）、`"any"`（0.0.0.0 + ::） | `[上游稳定][采纳]` |
| `port` | `int` | `4141` | 监听端口（与上游一致，非旧文档的 8313） | `[上游稳定][采纳]` |
| `debug` | `bool` | `False` | 调试模式（更详细日志 + 关闭部分性能优化路径） | `[采纳]` |

> 与旧文档更正：默认端口应为 **4141**（对齐上游 `citty` 默认），非此前的 8313。

---

## `upstream` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `type` | `Literal["copilot","generic"]` | `"copilot"` | 上游类型；启动期专属（切换需重启） | `[采纳]` |
| `ghc_api_base_url` | `str` | `""` | 显式指定上游 GHC API base URL（覆盖 `auth.account_type` 派生的 URL）；必须是合法 `http(s)://` URL | `[上游稳定][采纳]` |
| `openai_base_url` | `str` | `""` | Generic 上游：OpenAI 兼容端点 base URL | `[重构]`（本项目 Generic 上游设计） |
| `anthropic_base_url` | `str` | `""` | Generic 上游：Anthropic 兼容端点 base URL | `[重构]` |
| `api_key` | `str` | `""` | Generic 上游：API key | `[重构]` |
| `auth_type` | `Literal["bearer","x-api-key"]` | `"bearer"` | Generic 上游认证头形式 | `[重构]` |
| `max_connections` | `int` | `100` | httpx 连接池最大连接数 | `[重构]`（性能，见 P1/P8 通用取向） |
| `max_keepalive_connections` | `int` | `20` | 连接池 keepalive 连接数上限 | `[重构]` |
| `keepalive_expiry` | `int` | `30` | 秒，keepalive 连接过期 | `[重构]` |
| `connect_timeout` | `float` | `10.0` | 秒，连接超时 | `[重构]` |
| `read_timeout` | `float` | `300.0` | 秒，读超时（与 `timeouts.response_header` 呼应） | `[重构]` |
| `http2` | `bool` | `True` | 启用 HTTP/2（httpx `http2=True`，对应上游 node:http2 传输） | `[采纳]` |
| `proxy` | `str \| None` | `None` | 所有出站请求的代理 URL（`http://`/`https://`/`socks5://`/`socks5h://`），覆盖 env 变量与 config.yaml | `[上游稳定][采纳]` |

Generic 上游手动模型列表（当目标不支持 `/v1/models` 时）：

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `models` | `list[ManualModelConfig]` | `[]` | 手动声明模型（`id` / `name` / `supported_endpoints`） | `[新增]`（Generic 上游便利功能） |

---

## `auth` section（Copilot 专用，`account_type` 启动期专属）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `github_token` | `str` | `""` | GitHub token；也可由 `GITHUB_TOKEN` 环境变量（无 `GHC_` 前缀，兼容常见约定）或 `--github-token` 提供 | `[上游稳定][采纳]` |
| `account_type` | `Literal["individual","business","enterprise"]` | `"individual"` | Copilot 账户类型；省略时可从登录账户的 `copilot_plan` 推断，推断失败回落 `individual`；`upstream.ghc_api_base_url` 设置时此项无效果。启动期专属 | `[上游稳定][采纳]` |
| `token_file` | `str` | `""` | 自定义 token 存储文件路径（空=用默认 `get_token_path()`） | `[采纳]` |
| `show_github_token` | `bool` | `False` | 日志中显示 GitHub token（调试用；Copilot token 刷新日志用 `--verbose`） | `[上游稳定][采纳]` |

---

## `headers` section（Copilot 请求头伪装）

对应上游 `copilotHeaders()` / `githubHeaders()`（`lib/copilot-api.ts`）硬编码值，本项目做成可配置：

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `vscode_version` | `str` | `"1.99.0"` | `editor-version: vscode/{version}` 头 | `[采纳]` |
| `copilot_version` | `str` | `"0.25.2025020601"` | `editor-plugin-version: copilot-chat/{version}`、`user-agent: GitHubCopilotChat/{version}` | `[采纳]` |
| `api_version` | `str` | `"2025-05-01"` | `x-github-api-version` 头（GitHub API 与 Copilot API 共用同一常量） | `[采纳]` |

其余固定头（`copilot-integration-id: vscode-chat`、`X-Interaction-Id`、`X-Interaction-Type`、`x-vscode-user-agent-library-version: electron-fetch` 等）由代码内建，不做配置项（无变化价值）。

---

## `model_overrides` / `model_mappings` / `disabled_models` / `sanitize_tool_names` / `model_refresh_interval` / `model_translation`

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `model_overrides` | `dict[str,str]` | `{opus, sonnet, haiku}`（见上文顶层结构） | 简称别名（顶层，快捷配置） | `[新增]`（Python 侧便利别名层，位于 `model_mappings` 之上） |
| `model_mappings` | `dict[str,str]` | `{}`（内置默认见代码，如 `opus → claude-opus-4.7-1m-internal`） | 通用别名 → 具体模型 ID 映射；**per-key 合并**（用户只需声明要覆盖的键，未声明的内置键保留） | `[上游稳定][采纳]` |
| `disabled_models` | `list[str]` | `[]` | 禁用的模型 ID 列表（从可用模型列表中剔除） | `[上游稳定][采纳]` |
| `sanitize_tool_names` | `bool` | `False` | 跨协议清洗违反目标模型命名约束的 tool 名（非法字符/超长/冲突），响应时还原客户端原名。**跨协议**（Anthropic + Chat Completions + Responses），故置于顶层而非 `anthropic.*` | `[上游稳定][采纳]` |
| `model_refresh_interval` | `int` | `600` | 秒，模型列表后台定期刷新周期；0=禁用 | `[上游稳定][采纳]` |
| `model_translation` | `dict[str, list[ModelTranslationRule]]` | `{}` | 按 ingress 格式（`anthropic-messages`/`openai-cc`/`openai-responses`/`gemini`）的模型级翻译特性规则（如 `strip-thinking-signature`），首个 `match` 命中生效 | `[上游稳定][采纳]`，`[实验]` 范围较窄 |

---

## `anthropic` section（大 section，分组列出）

### header 转发（详见 [header-forwarding.md](header-forwarding.md)）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `use_upstream_count_tokens` | `bool` | `True` | 转发 `/v1/messages/count_tokens` 到 GHC 上游取精确计数；`False` 时仅用本地校准估算 | `[上游稳定][采纳]` |
| `strict_response_headers` | `bool` | `False` | `False`=黑名单模式（转发除 `response_header_blacklist` 外的全部响应头）；`True`=白名单模式（只转发匹配 `response_header_whitelist` 的头）。两模式均先过安全底线（`PROXY_CONTROLLED_RESPONSE_HEADERS` 恒删） | `[上游稳定][采纳]` |
| `request_header_blacklist` | `list[str]` | `["x-anthropic-billing-header"]` | 黑名单模式下剥除的客户端请求头 glob 列表 | `[上游稳定][采纳]` |
| `request_header_whitelist` | `list[str]` | `["accept","anthropic-dangerous-direct-browser-access","x-app","x-claude-code-*","x-stainless-*"]` | 白名单模式下唯一转发的客户端请求头 glob 列表（叠加代理重建的核心头） | `[上游稳定][采纳]` |
| `response_header_blacklist` | `list[str]` | `[]` | 黑名单模式下剥除的上游响应头 glob 列表 | `[上游稳定][采纳]` |
| `response_header_whitelist` | `list[str]` | `["request-id","x-request-id","anthropic-ratelimit-*","anthropic-organization-id","retry-after"]` | 白名单模式下唯一转发的上游响应头 glob 列表 | `[上游稳定][采纳]` |
| `strict_request_headers` | `bool` | `False` | 客户端→上游请求头转发模式开关（黑/白名单，语义同 `strict_response_headers`） | `[上游稳定][采纳]` |
| `strip_attribution_header` | `bool` | `True` | 剥离 Claude Code 归属计费行（作为请求体 `system[0]` 携带，HTTP 头黑名单无法触及），补充 `request_header_blacklist` | `[上游稳定][采纳]` |

### streaming / keepalive（详见 [streaming-resilience.md](streaming-resilience.md)，标 `[实验/opt-in]` 者默认关闭）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `stream_keepalive_ping_sec` | `int` | `20` | 秒，客户端侧 SSE keepalive 心跳最小间隔（0=禁用） | `[上游稳定][采纳]` |
| `stream_keepalive_mode` | `Literal["ping","empty_text"]` | `"empty_text"` | 心跳帧类型；`empty_text`（唯一稳定超时安全模式，默认）/`ping`（逃生舱，可能超时）。上游的第三值 `enveloped_ping` 明确预期超时，本项目**不实现**，Pydantic 不接受该值 | `[上游实验][拒绝 enveloped_ping，仅实现 ping/empty_text]` |
| `stream_commit_after_sec` | `int` | `20` | 秒，延迟提交窗口：等待请求在此窗口内落定再开 200 SSE 流；超时则提交 200 + keepalive。0=立即提交，clamp < 60 | `[上游稳定][采纳]` |
| `protect_streaming_generation` | `Literal[False,"on","tool_use_only"]` | `False` | 整响应缓冲重试模式开关（应对上游 mid-stream RST）。默认关，见 P6/BACKLOG | `[上游实验][采纳默认关]` |
| `buffered_retry` | `{max_retries:3, buffer_cap_bytes:16777216, heartbeat_sec:15}` | 见左 | Anthropic 路径缓冲重试 cap 覆盖（覆盖顶层 `buffered_retry.*` 共享 cap） | `[上游实验][采纳默认关]` |
| `protect_streaming_escalate_context` | `bool` | `False` | 每次缓冲重试时强制升级 `context_management` 压缩（更小 keep）以加速下一轮生成 | `[上游实验][缓存/延后]` |

### tools（详见 [tool-use.md](tool-use.md)）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `tool_inject_claude_code` | `bool` | `True` | 历史中引用但请求 `tools` 数组缺失时，注入 Claude Code 官方工具桩（Bash/Read/Write…） | `[上游稳定][采纳]` |
| `tool_search` | `bool` | `True` | 注入 `tool_search_tool_regex` 工具（deferred loading） | `[上游稳定][采纳]` |
| `tool_search_non_deferred` | `list[str]` | `[]` | 不参与 defer_loading 的工具名列表 | `[上游稳定][采纳]` |
| `tool_dedup_calls` | `Literal[False,"input","result"]` | `False` | 重复 tool_use/tool_result 对去重模式 | `[上游稳定][采纳]` |
| `tool_strip_read_result_tags` | `bool` | `False` | 剥离 Read 工具结果中的 system-reminder 标签 | `[上游稳定][采纳]` |
| `tool_strip_fields` / `tool_keep_fields` | `dict[str, list[str]]` | `{}` | model-name pattern → 自定义 tool 顶层字段黑/白名单（strip 叠加内置默认 `eager_input_streaming` + 学习式协商缓存；keep 为可逆开关） | `[上游稳定][采纳]` |
| `server_tool_memory` | `bool` | `False` | Anthropic 原生 memory 工具（`memory_20250818`）支持开关，未验证 CAPI 接受度 | `[上游实验][缓存/延后]` |

### thinking 管道（详见 [thinking-pipeline.md](thinking-pipeline.md)，L3 隔离为本项目内存重设计，见 P5）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `thinking_block_message_policy` | `Literal["preserve","stripped"]` | `"preserve"` | `preserve`：保留 thinking 块原文与相对顺序、永不丢弃，但允许周围内容清理；`stripped`：主动删除旧消息中的 thinking 块 | `[上游稳定][采纳]` |
| `thinking_block_sanitize` | `Literal[False,"all_empty","signature_empty","thinking_empty","any_empty"]` | `"all_empty"` | 发送上游前丢弃损坏的 thinking 块，判定依据签名而非文本 | `[上游稳定][采纳]` |
| `thinking_destack_strategy` | `Literal["passthrough","insert_text","move_blocks"]` | `"move_blocks"` | 去堆叠相邻 thinking 块（上游拒绝相邻 thinking），`move_blocks` 用非 thinking 块交错，幂等 | `[上游稳定][采纳]` |
| `strip_thinking_on_reject` | `bool` | `True` | L2：遇"thinking cannot be modified" 400 时一次性剥离全部 thinking 块并重试 | `[上游稳定][采纳]` |
| `poisoned_thinking_quarantine` | `bool` | `True` | L3 隔离总开关：L2 剥离成功后记住该会话，后续主动预剥离。**本项目用内存 dict + 滑动 TTL 替代上游磁盘 sidecar SQLite**（见 P5） | `[上游稳定][重构，见 P5]` |
| `poisoned_thinking_ttl_hours` | `float` | `72` | 小时，L3 隔离条目滑动 TTL | `[上游稳定][采纳]` |
| `thinking_coerce_adaptive` | `Literal[False,"basic","best_effort"]` | `"basic"` | 将旧版 `thinking.type="enabled"` 强制转换为 `"adaptive"`（仅支持 adaptive 的模型如 opus 4.6/4.7/4.8） | `[上游稳定][采纳]` |
| `thinking_signature_compat` | `Literal[False,"signature_delta","redacted_thinking"]` | `"signature_delta"` | thinking 签名兼容模式 | `[上游稳定][采纳]` |

### system 消息（inline `role:"system"` 处理）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `system_default_mode` | `Literal[False,"drop_invalid","merge","as_user","as_assistant"]` | `False` | 默认处理模式（未在 `system_reject_models` 中的模型使用）。`False`=透传（部分模型 400，学习式协商标记后自动重试） | `[上游稳定][采纳]` |
| `system_reject_mode` | 同上 | `"as_user"` | `system_reject_models` 命中的模型使用的处理模式 | `[上游稳定][采纳]` |
| `system_reject_models` | `list[str]` | `["claude-sonnet-4.6","claude-haiku-4.5"]` | 已知会拒绝 inline system 消息的模型列表 | `[上游稳定][采纳]` |
| `system_rewrite_reminders` | `bool \| list[RewriteRule]` | `False` | system-reminder 标签重写规则 | `[上游稳定][采纳]` |

### context editing（服务端上下文管理，详见 [anthropic-compat.md](anthropic-compat.md)）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `context_editing` | `Literal["off","clear-thinking","clear-tooluse","clear-both"]` | `"off"` | 服务端上下文裁剪模式 | `[上游稳定][采纳]` |
| `context_editing_trigger` | `int` | `100000` | 触发裁剪的 token 阈值 | `[上游稳定][采纳]` |
| `context_editing_keep_tools` | `int` | `3` | 保留最近 N 个 tool 调用 | `[上游稳定][采纳]` |
| `context_editing_keep_thinking` | `int` | `1` | 保留最近 N 个 thinking 块 | `[上游稳定][采纳]` |

### cache control（详见 [anthropic-compat.md](anthropic-compat.md)）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `cache_control` | `Literal["disabled","passthrough","sanitize","proxied"]` | `"passthrough"` | cache_control 处理模式 | `[上游稳定][采纳]` |
| `extended_cache_ttl.enabled` | `bool` | `False` | 扩展缓存 TTL（`extended-cache-ttl-2025-04-11` beta）总开关 | `[上游稳定][采纳]` |
| `extended_cache_ttl.tools_system_ttl` | `Literal["5m","1h"]` | `"1h"` | tools/system 层 TTL（enabled 时生效） | `[上游稳定][采纳]` |
| `extended_cache_ttl.messages_ttl` | `Literal["5m","1h"]` | `"5m"` | messages 层 TTL，须 ≤ tools_system_ttl | `[上游稳定][采纳]` |
| `cache_control_strip_subfields` | `dict[str, list[str]]` | `{}` | model-name pattern → 需剥离的 cache_control 子字段（叠加内置默认 + 学习式协商缓存） | `[上游稳定][采纳]` |

> **关键更正**：旧文档的 `auto_cache_control`(bool) 已废弃，改为 `cache_control` 四值枚举；旧文档的 `immutable_thinking`(bool) 已废弃，改为 `thinking_block_message_policy`。

### server tools / warmup / effort

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `warmup` | `Literal["allow","reject","drop","fake"]` | `"allow"` | Claude Code Warmup 请求策略 | `[上游稳定][采纳]` |
| `effort_overrides` | `dict[str, list[str]]` | `{}` | model-name pattern → effort 覆盖列表 | `[上游稳定][采纳]` |
| `beta_strip_headers` | `dict[str, list[str]]` | `{}` | model-name pattern → 需剥离的 `anthropic-beta` 值 | `[上游稳定][采纳]` |
| `partner_strip_features` | `dict[str, list[str]]` | `{}` | model-name pattern → 需剥离的 partner-only 特性 | `[上游稳定][采纳]` |
| `retry_reject_body_fields` | `dict[str, list[str]]` | `{}` | 400 拒绝时需剥离的 body 顶层字段（学习式协商配合） | `[上游稳定][采纳]` |

### 模型能力元数据（config 驱动的家族前缀白名单）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `model_capabilities.context_editing` | `list[str]` | `["claude-haiku-4-5","claude-sonnet-4","claude-opus-4","claude-opus-41"]` | 支持 context editing 的模型家族前缀 | `[上游稳定][采纳]` |
| `model_capabilities.interleaved_thinking` | `list[str]` | `["claude-sonnet-4","claude-haiku-4-5","claude-opus-4-5"]` | 支持交错 thinking 的模型家族前缀 | `[上游稳定][采纳]` |
| `model_capabilities.adaptive_thinking` | `list[str]` | `["claude-opus-4-6","claude-opus-4-7","claude-opus-4-8"]` | 支持 adaptive thinking 的模型家族前缀 | `[上游稳定][采纳]` |
| `model_capabilities.extended_cache_ttl` | `list[str]` | 见上游默认（`claude-fable-5`、`claude-opus-4-5..8`、`claude-sonnet-4-5/6`、`claude-haiku-4-5`） | 支持扩展缓存 TTL 的模型家族前缀 | `[上游稳定][采纳]` |
| `model_capabilities.memory` | `list[str]` | 见上游默认 | 支持 memory 工具的模型家族前缀 | `[上游实验][缓存/延后]` |
| `model_capabilities.tool_search_overrides` | `dict[str,bool]` | `{}` | 按模型强制开/关 tool-search（覆盖默认允许判定，检查顺序：声明元数据 → 本表 → 内置 Claude≥4.5 默认允许） | `[上游稳定][采纳]` |

### 响应侧修复与错误整形

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `response_text_fix.invoke_in_text` | `bool` | `True` | 修复上游误发为纯文本的 `<invoke>` 调用，还原为真正的 `tool_use` 块 | `[上游稳定][采纳]` |
| `response_tool_use_fix.malformed_input` | `str`（逗号分隔） | `""` | tool_use input 畸形 JSON 修复项集合（`tags`/`unicode`/`jsonrepair`/`unicode-lossy`），空=关闭 | `[上游稳定][采纳]` |
| `response_tool_use_fix.send_message_to_missing` | `bool` | `True` | 从 `agentId` 别名恢复缺失的 SendMessage `to` 收件人 | `[上游稳定][采纳]` |
| `response_tool_use_fix.ask_user_question_question_missing` | `bool` | `True` | 从 `header` 回填缺失的 AskUserQuestion `question` | `[上游稳定][采纳]` |
| `refusal_sse_rewrite` | `Literal["refusal","end_turn","error"]` | `"error"` | 拒绝响应的 SSE 重写模式 | `[上游稳定][采纳]` |
| `refusal_end_turn_text` | `str` | 内置默认文案 | `end_turn` 模式注入文本，支持 `{model}`/`{request_id}`/`{thinking_tokens}` 占位符 | `[上游稳定][采纳]` |
| `refusal_error_message` / `refusal_error_type` | `str` | 内置默认 | `error` 模式合成错误帧的消息/类型 | `[上游稳定][采纳]` |
| `error_shaping_enabled` | `bool` | `True` | 上游错误→客户端可行动形态整形总开关 | `[上游稳定][采纳]` |
| `error_ask_user_question` | `bool` | `False` | B 类错误合成 AskUserQuestion 轮次而非拍平错误帧（仅交互式部署） | `[上游实验][缓存/延后]` |
| `error_auq_template` | `str` | `""` | AUQ 问题文案模板 | `[上游实验][缓存/延后]` |
| `error_selfheal_delegate` | `dict[str,Literal["proxy","delegate"]]` | `{}` | 按反应式策略名配置代理自修 vs 透传委派客户端自愈 | `[上游稳定][采纳]` |

---

## `openai_responses` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `normalize_call_ids` | `bool` | `True` | `call_` → `fc_` 前缀标准化 | `[上游稳定][采纳]` |
| `upstream_ws` | `bool` | `False` | 上游 WebSocket transport | `[上游稳定][采纳]` |
| `buffered_retry` | `bool \| BufferedRetryOverride` | `False` | opt-in 中途缓冲重试（Codex 自动重试场景） | `[上游实验][采纳默认关]` |
| `fix_stream_ids` | `bool` | `True` | 修复 Responses SSE 流事件 ID | `[上游稳定][采纳]` |
| `client_ws_keep_open` | `bool` | `False` | 客户端 WS 连接保持打开 | `[上游稳定][采纳]` |
| `max_ws_frame_bytes` | `int` | `0` | 入站 WS 帧字节上限（0=无限） | `[上游稳定][采纳]` |
| `max_client_ws_connections` | `int` | `256` | 客户端 WS 并发连接上限（0=无限） | `[上游稳定][采纳]` |
| `max_upstream_ws_connections` | `int` | `32` | 上游 WS 连接池软上限（0=无限） | `[上游稳定][采纳]` |

---

## `chat_completions` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `buffered_retry` | `bool \| BufferedRetryOverride` | `False` | Chat Completions 路径缓冲重试模式开关 | `[上游实验][采纳默认关]` |

---

## `rate_limiter` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `retry_interval` | `int` | `10` | 秒，退避重试间隔 | `[上游稳定][采纳]` |
| `request_interval` | `int` | `10` | 秒，请求最小间隔 | `[上游稳定][采纳]` |
| `recovery_interval` | `int` | `600` | 秒，从限流恢复模式的等待时长（**注意**：单位是秒，非旧文档的分钟） | `[上游稳定][采纳]` |
| `consecutive_successes` | `int` | `5` | 连续成功次数达到后视为恢复 | `[上游稳定][采纳]` |

> **关键更正**：`recovery_interval` 单位是**秒**（600），不是旧文档写的"分钟"（`recovery_timeout_minutes`）。

---

## `approval` section（本项目独有 `[新增]`）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `enabled` | `bool` | `False` | 手动审批门控总开关 | `[新增]` |
| `timeout_seconds` | `float` | `300` | 审批超时秒数 | `[新增]` |

---

## `timeouts` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `stream_idle` | `int` | `300` | 秒，SSE 事件间最大间隔（0=无超时）。旧键名 `stream_idle_timeout` | `[上游稳定][采纳]` |
| `stream_idle_overrides` | `dict[str,int]` | `{"gpt-5.5": 600}`（内置示例默认，per-key 合并） | 按模型名子串（`*`=通配）覆盖 `stream_idle`，仅 App 层守卫，不触碰传输层 dispatcher | `[上游稳定][采纳]` |
| `response_header` | `int` | `300` | 秒，请求发起到收到响应头的超时（0=无超时）。旧键名 `fetch_timeout` | `[上游稳定][采纳]` |
| `response_header_overrides` | `dict[str,int]` | `{}` | 按模型名覆盖 `response_header`，同 `stream_idle_overrides` 合并语义 | `[上游稳定][采纳]` |
| `upstream_keepalive` | `int` | `15` | 秒，上游 TCP keepalive 初始探测延迟（0=用传输层默认） | `[采纳]`（Python httpx 对应实现） |
| `upstream_h2_ping` | `int` | `15` | 秒，上游 HTTP/2 PING keepalive 间隔（0=禁用），应对长时间 thinking 静默被中间设备判定空闲切断 | `[上游稳定][采纳]` |
| `stale_request_max_age` | `int` | `600` | 秒，活跃请求最大存活时长（0=禁用），由 stale reaper 强制失败 | `[上游稳定][采纳]` |
| `request_deadline` | `int` | `0` | 秒，单请求硬性总时长 SLA（0=禁用，退化为仅靠 stale reaper）。`stale_request_max_age` 应大于此值 | `[上游稳定][采纳]` |

---

## `shutdown` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `graceful_wait` | `int` | `60` | 秒，优雅等待阶段时长 | `[上游稳定][采纳]` |
| `abort_wait` | `int` | `120` | 秒，中止等待阶段时长 | `[上游稳定][采纳]` |

本项目为 **4 阶段**关闭（Setup → Graceful Wait → Abort → Force Close）+ 信号升级，详见 [shutdown.md](shutdown.md)。

---

## `history` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `enabled` | `bool` | `True` | 历史子系统总开关；**启动期专属**（非热重载，需重启），`False`=不开历史库、不记录、所有 `/history/api/*` 端点 no-op | `[上游稳定][采纳]` |
| `success_limit` | `int` | `50` | 成功（非失败）条目数上限（0=无限） | `[上游稳定][采纳]` |
| `failure_limit` | `int` | `200` | 失败条目数上限（0=无限） | `[上游稳定][采纳]` |
| `reaper_interval` | `int` | `600` | 秒，超限清理周期 | `[上游稳定][采纳]` |
| `db_path` | `str` | `""` | 自定义 DB 路径（空=默认 `<APP_DIR>/history.db`） | `[上游稳定][采纳]` |
| `websocket` | `bool` | `True` | History WebSocket 实时推送开关 | `[采纳]` |
| `archive.*`（分层归档） | 见下 | 见下 | 三层降温归档（HOT→tier1→tier2） | `[上游稳定][缓存/延后，见 BACKLOG #1]` |

`archive.*` 子键（默认**关闭**/延后，本项目默认单层 + 简单行数清理即可覆盖核心需求）：

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `archive.enabled` | `bool` | `False`（本项目默认关，上游默认 `True`） | 归档总开关 |
| `archive.hot_days` | `int` | `3` | 热库保留天数 |
| `archive.tier1_size_cap` | `str` | `"2GB"` | tier1 大小上限（人类可读串或字节数） |
| `archive.tier2_warn_count` | `int` | `200` | tier2 封存单元数告警阈值 |
| `archive.tier2_warn_bytes` | `str` | `"500MB"` | tier2 总量告警阈值 |
| `archive.dir` | `str` | `""` | 归档落盘目录（空=同 `db_path` 同级） |

> **关键更正**：`history.limit=200` + `min_entries` 的旧设计（内存压力管理）已废弃。上游已 `removeKey("history.min_entries", ...)`（绑定的内存 history store 已删除）。本项目采用 **`success_limit=50` / `failure_limit=200`** 分桶计数，无内存压力管理概念；`limit`（旧键）仅作 compat 别名回退到 `success_limit`/`failure_limit`。

---

## `telemetry` section（可选/简化，详见 [telemetry-observability.md](telemetry-observability.md)）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `enabled` | `bool` | `False` | 重遥测（DDSketch + 分层 SQLite）总开关。本项目默认**关闭**，改走 OpenTelemetry（见 [BACKLOG](BACKLOG.md) 第 3 条）；此 section 描述的自建时序库仅作可选能力 | `[上游稳定][简化]` |
| `db_path` | `str` | `""` | 独立 DB 路径（空=默认 `<APP_DIR>/telemetry.db`） | `[简化]` |
| `persist_interval` | `int` | `60` | 秒，落盘/flush 间隔 | `[简化]` |
| `rollup_interval` | `int` | `3600` | 秒，上卷间隔 | `[简化/缓存延后]`（本项目默认走 OpenTelemetry 导出，不自建分层 rollup，见 BACKLOG #3） |
| `cardinality_cap` | `int` | `200` | 维度基数上限 | `[简化]` |
| `sketch_gamma` | `float` | `0.01` | DDSketch 相对误差（本项目默认不启用 DDSketch，见 BACKLOG #3） | `[简化/缓存延后]` |
| `cumulative` | `bool` | `True` | 终身累计层开关 | `[简化]` |
| `tiers.raw.resolution_minutes` / `retention_days` | `int` | `5` / `7` | raw 层分辨率与保留 | `[缓存/延后]` |
| `tiers.hourly.retention_days` | `int` | `90` | hourly 层保留 | `[缓存/延后]` |
| `tiers.daily.retention_days` | `int` | `0`（不限） | daily 层保留 | `[缓存/延后]` |

本项目默认方案：轻量内存计数器 + OpenTelemetry 导出 + `/metrics` Prometheus 文本，不自建 SQLite 分层遥测（见 [BACKLOG.md](BACKLOG.md) 第 3 条）。

---

## `negotiation_learning` section（详见 [feature-negotiation.md](feature-negotiation.md)）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `default_ttl_days` | `int` | `30` | 未覆盖类别的默认 TTL；0/null=永不过期 | `[上游稳定][采纳]` |
| `ttl_days` | `dict[str,int]` | `{"tool_fields": 90}`（`partner_features` 内置 `Infinity`，即永不过期） | 按类别 ID 覆盖 TTL | `[上游稳定][采纳]` |

---

## `unknown_endpoint_logging` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `not_found` | `Literal["silent","debug","info","warn","error"]` | `"warn"` | 404（路径未匹配任何业务路由）日志级别 | `[上游稳定][采纳]` |
| `method_not_allowed` | 同上 | `"warn"` | 405（路径存在但 method 不对）日志级别 | `[上游稳定][采纳]` |

---

## `system_prompt` section

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `overrides` | `list[RewriteRule]` | `[]` | 正则/整行替换规则；`from`/`to`/`method`(line\|regex)/`model`(可选正则过滤)/`endpoint`(可选 `anthropic`\|`openai-cc`\|`openai-responses`\|`gemini`) | `[上游稳定][采纳]` |
| `prepend` | `list[str]` 或字符串 | `[]` | 前置文本（可按 model/endpoint 限定作用范围） | `[上游稳定][采纳]` |
| `append` | 同上 | `[]` | 后置文本 | `[上游稳定][采纳]` |

三种机制均跨全部端点（Anthropic Messages、Chat Completions、Responses API）生效；OpenAI 格式作用于 system/developer 消息。

---

## `observability` section（Python 侧新增，日志/追踪配置）

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `log_level` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | 日志级别 | `[采纳]` |
| `log_format` | `Literal["json","text"]` | `"text"` | 日志格式 | `[采纳]` |
| `tracing_enabled` | `bool` | `False` | OpenTelemetry 追踪总开关 | `[简化]` |
| `tracing_endpoint` | `str` | `""` | OTLP exporter endpoint（空=stdout） | `[简化]` |

---

## 顶层其余键

| 键 | 类型 | 默认值 | 说明 | 稳定性 |
|---|---|---|---|---|
| `hooks.upstream_module` | `str` | `""` | 上游 transport mock/拦截模块路径（仅 dev/test 用途） | `[上游稳定][缓存/延后，见 ROADMAP]` |
| `hooks.enabled` | `bool` | `False` | hooks 加载总开关 | `[缓存/延后]` |
| `retry.max_reactive_retries` | `int` | `5` | 所有反应式重试策略（网络/服务端错误/token 刷新/400 类协商等）共享的每请求重试预算上限 | `[上游稳定][采纳]` |
| `buffered_retry`（顶层共享 cap） | `{max_retries:3, buffer_cap_bytes:16777216, heartbeat_sec:15}` | 见左 | 各 vendor 缓冲重试 cap 的共享默认，各 vendor `*.buffered_retry` 可覆盖 | `[上游实验][采纳默认关]` |

---

## YAML 配置文件完整格式

```yaml
# ghc-api-proxy 配置文件
# 放置于 ./config.yaml 或 ~/.config/ghc-api-proxy/config.yaml

# ── 服务器 ──────────────────────────────
host: "127.0.0.1"
port: 4141
debug: false

# ── 上游目标 ────────────────────────────
upstream:
  type: copilot                    # copilot | generic
  # ghc_api_base_url: "https://api.githubcopilot.com"
  # openai_base_url: "https://api.openai.com"
  # anthropic_base_url: "https://api.anthropic.com"
  # api_key: "sk-..."
  # auth_type: bearer

  max_connections: 100
  max_keepalive_connections: 20
  keepalive_expiry: 30
  connect_timeout: 10.0
  read_timeout: 300.0
  http2: true
  # proxy: "socks5://127.0.0.1:1080"

# ── 认证 ────────────────────────────────
auth:
  github_token: ""
  account_type: individual
  # token_file: ""

# ── 请求头伪装 ──────────────────────────
headers:
  vscode_version: "1.99.0"
  copilot_version: "0.25.2025020601"
  api_version: "2025-05-01"

# ── 模型映射 ────────────────────────────
model_overrides:
  opus: claude-opus-4.6
  sonnet: claude-sonnet-4.6
  haiku: claude-haiku-4.5

model_mappings: {}                 # per-key 合并，仅需声明要覆盖的键
disabled_models: []
sanitize_tool_names: false
model_refresh_interval: 600

# ── Anthropic 行为 ──────────────────────
anthropic:
  # header 转发
  use_upstream_count_tokens: true
  strict_response_headers: false
  strict_request_headers: false
  request_header_blacklist: ["x-anthropic-billing-header"]
  request_header_whitelist: ["accept", "anthropic-dangerous-direct-browser-access", "x-app", "x-claude-code-*", "x-stainless-*"]
  response_header_blacklist: []
  response_header_whitelist: ["request-id", "x-request-id", "anthropic-ratelimit-*", "anthropic-organization-id", "retry-after"]
  strip_attribution_header: true

  # streaming/keepalive
  stream_keepalive_ping_sec: 20
  stream_keepalive_mode: empty_text        # ping | empty_text（enveloped_ping 不支持，见[拒绝]）
  stream_commit_after_sec: 20
  protect_streaming_generation: false      # false | on | tool_use_only（[实验/opt-in]）
  buffered_retry:
    max_retries: 3
    buffer_cap_bytes: 16777216
    heartbeat_sec: 15
  protect_streaming_escalate_context: false

  # tools
  tool_inject_claude_code: true
  tool_search: true
  tool_search_non_deferred: []
  tool_dedup_calls: false                  # false | input | result
  tool_strip_read_result_tags: false
  # tool_strip_fields: {}
  # tool_keep_fields: {}

  # thinking
  thinking_block_message_policy: preserve  # preserve | stripped
  thinking_block_sanitize: all_empty       # false | all_empty | signature_empty | thinking_empty | any_empty
  thinking_destack_strategy: move_blocks   # passthrough | insert_text | move_blocks
  strip_thinking_on_reject: true
  poisoned_thinking_quarantine: true
  poisoned_thinking_ttl_hours: 72
  thinking_coerce_adaptive: basic          # false | basic | best_effort
  thinking_signature_compat: signature_delta

  # system 消息
  system_default_mode: false
  system_reject_mode: as_user
  system_reject_models: ["claude-sonnet-4.6", "claude-haiku-4.5"]
  system_rewrite_reminders: false

  # context editing
  context_editing: "off"                   # off | clear-thinking | clear-tooluse | clear-both
  context_editing_trigger: 100000
  context_editing_keep_tools: 3
  context_editing_keep_thinking: 1

  # cache control
  cache_control: passthrough               # disabled | passthrough | sanitize | proxied
  extended_cache_ttl:
    enabled: false
    tools_system_ttl: "1h"
    messages_ttl: "5m"

  # server tools / warmup / effort
  warmup: allow                            # allow | reject | drop | fake
  server_tool_memory: false                # [实验][缓存/延后]
  # effort_overrides: {}
  # beta_strip_headers: {}
  # partner_strip_features: {}
  # retry_reject_body_fields: {}

  # 响应侧修复与错误整形（简要，多数 [实验] 项默认保守值）
  response_text_fix:
    invoke_in_text: true
  response_tool_use_fix:
    send_message_to_missing: true
    ask_user_question_question_missing: true
  refusal_sse_rewrite: error                # refusal | end_turn | error
  error_shaping_enabled: true

# ── OpenAI Responses ────────────────────
openai_responses:
  normalize_call_ids: true
  upstream_ws: false
  buffered_retry: false
  fix_stream_ids: true
  client_ws_keep_open: false
  max_client_ws_connections: 256
  max_upstream_ws_connections: 32

# ── Chat Completions ────────────────────
chat_completions:
  buffered_retry: false

# ── 限流 ────────────────────────────────
rate_limiter:
  retry_interval: 10
  request_interval: 10
  recovery_interval: 600
  consecutive_successes: 5

# ── 审批（本项目独有）───────────────────
approval:
  enabled: false
  timeout_seconds: 300

# ── 超时与生命周期 ──────────────────────
timeouts:
  stream_idle: 300
  response_header: 300
  upstream_keepalive: 15
  stale_request_max_age: 600
  request_deadline: 0
  # stream_idle_overrides:
  #   "gpt-5.5": 600

# ── 关闭 ────────────────────────────────
shutdown:
  graceful_wait: 60
  abort_wait: 120

# ── 历史记录 ────────────────────────────
history:
  enabled: true
  success_limit: 50
  failure_limit: 200
  reaper_interval: 600
  db_path: ""
  websocket: true
  archive:
    enabled: false               # 本项目默认关（见 BACKLOG #1）

# ── 遥测（可选/简化）────────────────────
telemetry:
  enabled: false                 # 本项目默认关，走 OpenTelemetry（见 BACKLOG #3）
  persist_interval: 60

# ── 学习式协商 TTL ───────────────────────
negotiation_learning:
  default_ttl_days: 30
  ttl_days:
    tool_fields: 90

# ── 未知端点日志 ────────────────────────
unknown_endpoint_logging:
  not_found: warn
  method_not_allowed: warn

# ── 系统提示词 ──────────────────────────
system_prompt:
  prepend: []
  append: []
  overrides: []

# ── 可观测性 ────────────────────────────
observability:
  log_level: INFO
  log_format: text
  tracing_enabled: false
  # tracing_endpoint: ""
```

## 环境变量映射

Pydantic BaseSettings 使用 `GHC_` 前缀和 `__` 嵌套分隔符：

| 环境变量 | 配置字段 |
|----------|----------|
| `GHC_HOST` | `host` |
| `GHC_PORT` | `port` |
| `GHC_DEBUG` | `debug` |
| `GHC_UPSTREAM__TYPE` | `upstream.type` |
| `GHC_UPSTREAM__GHC_API_BASE_URL` | `upstream.ghc_api_base_url` |
| `GHC_UPSTREAM__OPENAI_BASE_URL` | `upstream.openai_base_url` |
| `GHC_UPSTREAM__API_KEY` | `upstream.api_key` |
| `GHC_UPSTREAM__PROXY` | `upstream.proxy` |
| `GHC_AUTH__GITHUB_TOKEN` | `auth.github_token` |
| `GHC_AUTH__ACCOUNT_TYPE` | `auth.account_type` |
| `GHC_ANTHROPIC__CONTEXT_EDITING` | `anthropic.context_editing` |
| `GHC_ANTHROPIC__TOOL_SEARCH` | `anthropic.tool_search` |
| `GHC_ANTHROPIC__CACHE_CONTROL` | `anthropic.cache_control` |
| `GHC_ANTHROPIC__THINKING_BLOCK_MESSAGE_POLICY` | `anthropic.thinking_block_message_policy` |
| `GHC_ANTHROPIC__WARMUP` | `anthropic.warmup` |
| `GHC_HISTORY__ENABLED` | `history.enabled` |
| `GHC_HISTORY__SUCCESS_LIMIT` | `history.success_limit` |
| `GHC_HISTORY__FAILURE_LIMIT` | `history.failure_limit` |
| `GHC_RATE_LIMITER__RETRY_INTERVAL` | `rate_limiter.retry_interval` |
| `GHC_APPROVAL__ENABLED` | `approval.enabled` |
| `GHC_TIMEOUTS__STREAM_IDLE` | `timeouts.stream_idle` |
| `GHC_TIMEOUTS__RESPONSE_HEADER` | `timeouts.response_header` |
| `GHC_SHUTDOWN__GRACEFUL_WAIT` | `shutdown.graceful_wait` |
| `GHC_OBSERVABILITY__LOG_LEVEL` | `observability.log_level` |
| `GHC_MODEL_REFRESH_INTERVAL` | `model_refresh_interval` |
| `GHC_SANITIZE_TOOL_NAMES` | `sanitize_tool_names` |

特例：`GITHUB_TOKEN` 环境变量（无 `GHC_` 前缀）也会被 `auth/manager.py`（token provider 链）直接读取，兼容常见约定，详见 [authentication.md](authentication.md)。

## CLI 参数

```
usage: ghc-api-proxy [-h] {start,auth,logout,debug,setup-claude-code,setup-codex,list-claude-code} ...

子命令:
  start                启动 API 代理服务器（默认）
  auth (login)         运行 GitHub 认证流程
  logout               删除已存储的 GitHub token
  debug info           显示诊断信息
  debug models         获取并显示 Copilot API 原始模型数据
  debug usage          查看 Copilot 使用量和配额（注意：非顶层 check-usage，是 debug 的子命令）
  setup-claude-code    生成 Claude Code 配置指引
  setup-codex          生成 Codex CLI 配置指引
  list-claude-code     列出已知 Claude Code 安装

start 选项:
  --config CONFIG            YAML 配置文件路径
  --port, -p PORT            监听端口（默认 4141）
  --host, -H HOST            监听地址（特殊值 localhost/any，默认 127.0.0.1）
  --verbose, -v               详细日志输出
  --account-type, -a TYPE     Copilot 账户类型（individual/business/enterprise，省略时从账户推断）
  --ghc-api-base-url URL      显式上游 GHC API base URL（覆盖 --account-type）
  --rate-limit / --no-rate-limit   自适应限流开关（默认开）
  --history / --no-history    历史记录开关（默认从 config history.enabled 取值；--no-history 强制关闭）
  --github-token, -g TOKEN    直接提供 GitHub token
  --show-github-token         日志显示 GitHub token
  --proxy URL                 代理 URL（覆盖 env 与 config.yaml）
  --http-proxy-from-env / --no-http-proxy-from-env   是否读取环境变量代理设置（默认开）
  --manual                    启用手动审批（映射 approval.enabled=true，本项目独有）
  --generate-config           生成默认配置文件
```

> **关键更正**：CLI 无顶层 `check-usage` 子命令，实际是 **`debug usage`**。

## 配置热重载

通过 `/api/config`、`/api/config/yaml` 端点支持运行时配置热重载：

```
GET  /api/config           查看当前生效配置（脱敏）
GET  /api/config/yaml      查看当前 YAML 表示
PUT  /api/config/yaml      提交新 YAML，触发热重载（字段值为 null 表示删除该键，回落默认/继承值）
```

热重载产生新的 frozen `AppSettings` 实例而非原地修改，保证并发安全（见 DESIGN.md P8）。正在处理中的请求继续使用旧配置引用；流式响应的 keepalive 间隔在流开始时捕获，进行中的流保持原值，新流采用新值。

**启动期专属（不支持热重载，需重启）**：

- `host` / `port` — 服务器绑定地址
- `upstream.type` — 上游类型
- `auth.account_type` — 账户类型（当 `upstream.ghc_api_base_url` 未设置时影响 URL 派生）
- `history.enabled` — 历史子系统主开关（打开/关闭需要重新初始化 DB 连接与后台任务）

## 配置文件路径

### paths.py

```python
import os
import platform
from pathlib import Path

def get_config_dir() -> Path:
    """获取配置目录路径（跨平台，支持 XDG）。"""
    if xdg := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg) / "ghc-api-proxy"
    system = platform.system()
    if system == "Linux":
        return Path.home() / ".config" / "ghc-api-proxy"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ghc-api-proxy"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "ghc-api-proxy"
    return Path.home() / ".ghc-api-proxy"

def get_data_dir() -> Path:
    """获取数据目录路径（history.db、telemetry.db 等），支持 XDG_DATA_HOME。"""
    if xdg := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg) / "ghc-api-proxy"
    return get_config_dir()  # 非 Linux 或未设 XDG 时与配置目录同级

def get_default_config_path() -> Path:
    return get_config_dir() / "config.yaml"

def get_token_path() -> Path:
    return get_config_dir() / "github_token"

def get_error_persistence_dir() -> Path:
    return get_config_dir() / "errors"
```

## 弃用键迁移（compat.py，精简版）

本项目是全新实现，无历史包袱（见 [BACKLOG.md](BACKLOG.md) 第 6 条），只保留少量明显、高频的别名迁移，warn-and-continue（不 fail 配置加载）：

| 弃用键 | 迁移目标 | 说明 |
|---|---|---|
| `history.limit` | `history.success_limit` / `history.failure_limit` | 旧单一上限拆分为按结果分桶 |
| `history.min_entries` | （移除，无替代） | 绑定的内存压力管理已删除，警告后忽略 |
| `anthropic.auto_cache_control`(bool) | `anthropic.cache_control`(枚举) | `true→passthrough`，`false→disabled` |
| `anthropic.immutable_thinking`(bool) | `anthropic.thinking_block_message_policy` | `true→preserve`，`false→stripped` |
| `rate_limit.recovery_timeout_minutes` | `rate_limiter.recovery_interval`（秒） | 单位换算 ×60 |
| `anthropic.api_key` | （不存在，无需迁移） | 历史上从未存在此键；如误传，warn 并忽略 |

不迁移的键：上游 `config/compat.ts` 中大量 `anthropic.*` 细粒度改名（如 `dedup_tool_calls→tool_dedup_calls`、`non_deferred_tools→tool_search_non_deferred`）——本项目直接使用改名后的最终键名作为唯一形态，不提供旧名兼容（这些改名从未在本项目历史中出现过）。

## 相关文档

- [设计文档总纲](DESIGN.md)
- [目录结构](project-structure.md)
- [认证系统](authentication.md)
- [请求/响应头转发安全](header-forwarding.md)
- [Thinking 处理管道](thinking-pipeline.md)
- [Tool Use](tool-use.md)
- [Anthropic 兼容性](anthropic-compat.md)
- [流式韧性](streaming-resilience.md)
- [历史与审计系统](history-system.md)
- [可观测性](telemetry-observability.md)
- [Feature Negotiation](feature-negotiation.md)
- [ROADMAP.md](ROADMAP.md) / [BACKLOG.md](BACKLOG.md)
