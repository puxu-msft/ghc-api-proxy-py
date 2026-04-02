# 目录结构与模块职责

## 完整目录树

```
ghc-api-proxy-py/
├── pyproject.toml                       # 项目元数据、依赖声明
├── main.py                              # 入口点 → app.cli.main()
├── config.example.yaml                  # YAML 配置示例（带注释）
│
├── src/app/
│   ├── __init__.py                      # 包初始化、版本号
│   ├── cli.py                           # CLI 参数解析（argparse），启动 uvicorn
│   ├── server.py                        # FastAPI 应用工厂、lifespan 生命周期、中间件注册
│   ├── deps.py                          # FastAPI 依赖注入提供者（Depends 工厂函数）
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py                  # Pydantic BaseSettings 模型（所有配置项定义）
│   │   ├── loader.py                    # YAML 加载 + 三层合并逻辑（defaults < yaml < env < cli）
│   │   └── paths.py                     # 跨平台配置/数据目录路径解析
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── openai.py                    # OpenAI API Pydantic 模型（Chat Completions + Responses API）
│   │   ├── anthropic.py                 # Anthropic API Pydantic 模型（请求/响应/SSE事件）
│   │   └── common.py                    # 通用模型（Usage、ModelInfo、ErrorResponse）
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── manager.py                   # GitHub token 获取（多源优先级）
│   │   ├── copilot.py                   # GitHub→Copilot token 交换、自动刷新
│   │   └── device_flow.py              # GitHub OAuth 设备授权流程实现
│   │
│   ├── upstream/
│   │   ├── __init__.py
│   │   ├── base.py                      # UpstreamTarget 协议定义
│   │   ├── copilot.py                   # GitHub Copilot 上游实现
│   │   ├── generic.py                   # 通用 OpenAI/Anthropic 兼容上游实现
│   │   ├── client.py                    # httpx.AsyncClient 封装（连接池、超时）
│   │   └── models_api.py               # 上游模型列表获取与缓存
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── context.py                   # RequestContext 请求生命周期追踪
│   │   ├── executor.py                  # 请求执行管道核心循环
│   │   ├── rate_limiter.py              # 自适应三模式限流器
│   │   ├── approval.py                  # 手动审批门控
│   │   └── strategies/
│   │       ├── __init__.py
│   │       ├── base.py                  # RetryStrategy 协议定义
│   │       ├── auto_truncate.py         # 自动截断策略
│   │       └── orphan_cleanup.py        # 孤立块清理策略
│   │
│   ├── transform/
│   │   ├── __init__.py
│   │   ├── model_resolver.py            # 模型名称标准化与别名映射
│   │   ├── translator.py               # Anthropic ↔ OpenAI 双向格式翻译
│   │   ├── sanitizer.py                # 消息清洗（孤立块、空块、标签）
│   │   └── system_prompt.py            # 系统提示词定制（prepend/append/regex）
│   │
│   ├── streaming/
│   │   ├── __init__.py
│   │   ├── sse.py                       # SSE StreamingResponse 工具函数
│   │   ├── accumulator.py              # 流式块 → 完整响应累积器
│   │   └── translator.py              # OpenAI chunk ↔ Anthropic event 流式翻译
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── openai.py                    # POST /v1/chat/completions, GET /v1/models
│   │   ├── responses.py                # POST /v1/responses
│   │   ├── anthropic.py                # POST /v1/messages
│   │   ├── health.py                    # GET /health
│   │   ├── history.py                  # /api/history/* 历史查看端点
│   │   └── approval.py                # /api/approval/* 手动审批端点
│   │
│   ├── history/
│   │   ├── __init__.py
│   │   ├── store.py                     # 异步安全内存历史存储
│   │   └── ws.py                        # WebSocket 连接管理与广播
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── logging.py                  # 结构化日志配置
│   │   ├── tracing.py                  # OpenTelemetry 链路追踪配置
│   │   └── middleware.py               # 请求日志 / 追踪中间件
│   │
│   └── errors.py                        # 错误分类、格式化错误响应构建
│
└── tests/
    ├── conftest.py                      # 共享 fixture（测试客户端、mock 上游）
    ├── test_translator.py
    ├── test_sanitizer.py
    ├── test_model_resolver.py
    ├── test_pipeline.py
    ├── test_routes.py
    └── test_history.py
```

## 模块间依赖关系

```
                    cli.py
                      │
                      ▼
                   server.py ──────────────────────┐
                      │                            │
          ┌───────────┼───────────┐                │
          ▼           ▼           ▼                ▼
       config/     deps.py     routes/        observability/
          │           │           │
          │     ┌─────┼─────┐    │
          │     ▼     ▼     ▼    │
          │  upstream/ pipeline/ history/
          │     │       │
          │     │    ┌──┴───┐
          │     │    ▼      ▼
          │     │ approval rate_limiter
          │     │    │
          │     ▼    │
          │   auth/  │
          │          │
          └──────────┤
                     ▼
              transform/  ←── streaming/
                  │
                  ▼
              models/    errors.py
```

**依赖规则：**
- `models/` 和 `errors.py` 是叶子模块，不依赖其他业务模块
- `transform/` 仅依赖 `models/`
- `streaming/` 依赖 `models/` 和 `transform/`
- `auth/` 仅依赖 `config/`
- `upstream/` 依赖 `auth/`、`config/`、`models/`
- `pipeline/` 依赖 `upstream/`、`transform/`、`history/`、`config/`
- `routes/` 依赖 `pipeline/`、`models/`、`deps.py`
- `server.py` 组装所有模块
- `cli.py` 仅调用 `server.py` 和 `config/`

## 各模块详述

### `cli.py` - 命令行入口

职责：
- 使用 `argparse` 解析命令行参数（port, host, config, verbose 等）
- 调用 `config.loader` 完成三层配置合并
- 调用 `uvicorn.run()` 启动 ASGI 服务器
- 支持 `--generate-config` 生成默认配置文件

对外接口：
- `main()` 函数，由 `main.py` 调用

### `server.py` - 应用工厂

职责：
- `create_app(settings) -> FastAPI`：创建并配置 FastAPI 实例
- `lifespan` 异步上下文管理器：
  - **启动时**：初始化认证、创建上游客户端、获取模型列表、创建历史存储/限流器/审批管理器
  - **关闭时**：关闭 httpx 客户端、排空限流队列、拒绝待审批请求
- 注册所有路由（`routes/` 下各 router）
- 注册中间件：CORS、请求日志、OpenTelemetry

对外接口：
- `create_app(settings: AppSettings) -> FastAPI`

### `deps.py` - 依赖注入

职责：
- 提供 FastAPI `Depends` 工厂函数
- 从 `request.app.state` 获取 lifespan 中初始化的单例对象

提供的依赖：

```python
def get_settings(request: Request) -> AppSettings: ...
def get_upstream(request: Request) -> UpstreamTarget: ...
def get_history_store(request: Request) -> HistoryStore: ...
def get_rate_limiter(request: Request) -> AdaptiveRateLimiter: ...
def get_approval_gate(request: Request) -> ApprovalGate: ...
def get_model_resolver(request: Request) -> ModelResolver: ...
def get_ws_manager(request: Request) -> WebSocketManager: ...
```

### `config/` - 配置系统

详见 [配置系统文档](config-system.md)。

**`settings.py`** - 核心配置模型，Pydantic `BaseSettings` 子类，定义所有可配置参数及默认值。

**`loader.py`** - 配置加载逻辑：
1. 实例化 `AppSettings()`（加载 env vars + defaults）
2. 如果存在 YAML 配置文件，解析并覆盖对应字段
3. 如果有 CLI 参数，覆盖对应字段
4. 返回最终的 `AppSettings` 实例

**`paths.py`** - 配置目录解析：
- Linux: `~/.config/ghc-api-proxy/`
- macOS: `~/Library/Application Support/ghc-api-proxy/`
- Windows: `%APPDATA%/ghc-api-proxy/`

### `models/` - 数据模型

详见 [核心数据模型文档](data-models.md)。

**`openai.py`** - OpenAI API 兼容的 Pydantic 模型：
- Chat Completions：`ChatCompletionRequest`, `ChatCompletionResponse`, `ChatCompletionChunk`
- Responses API：`ResponsesRequest`, `ResponsesResponse`, `InputItem`, `OutputItem`
- 共享：`ChatMessage`, `ToolCall`, `Function`, `Tool`

**`anthropic.py`** - Anthropic API 兼容的 Pydantic 模型：
- `MessagesRequest` / `MessagesResponse`
- `ContentBlock`（text / tool_use / tool_result / thinking）
- `MessageStreamEvent`（message_start / content_block_delta / message_stop 等）

**`common.py`** - 跨格式通用模型：
- `Usage`（input_tokens / output_tokens / cache 相关）
- `ModelInfo`（id / name / capabilities / supported_endpoints）
- `ErrorResponse`

### `auth/` - 认证系统

详见 [上游目标系统文档](upstream-targets.md) 中的认证部分。

**`manager.py`** - GitHub token 获取，按优先级尝试：
1. CLI `--github-token` 参数
2. `GITHUB_TOKEN` 环境变量
3. 文件存储（`~/.config/ghc-api-proxy/github_token`）
4. 交互式 device flow

**`copilot.py`** - Copilot token 管理：
- `CopilotAuth` 类：持有 GitHub token，管理 Copilot token 生命周期
- `refresh_token()`：交换 GitHub token → Copilot token
- 自动在到期前刷新（`asyncio.Lock` 保护并发安全）

**`device_flow.py`** - GitHub OAuth 设备授权：
- 请求 device code
- 提示用户在浏览器中输入 user code
- 轮询等待授权完成
- 返回 GitHub access token

### `upstream/` - 上游目标管理

详见 [上游目标系统文档](upstream-targets.md)。

**`base.py`** - `UpstreamTarget` 协议定义，所有上游目标必须实现的接口。

**`copilot.py`** - GitHub Copilot 上游实现：
- 注入 Copilot token 到请求头
- 构建 VSCode 扩展伪装头
- 支持 `/chat/completions`、`/v1/messages` 和 `/responses` 三个 Copilot 端点
- 通过 GitHub API 获取可用模型列表

**`generic.py`** - 通用上游实现：
- 可配置端点 URL（base_url）
- 可配置认证（API key / Bearer token）
- 适用于任意 OpenAI/Anthropic 兼容服务

**`client.py`** - httpx 客户端封装：
- 创建和管理 `httpx.AsyncClient`
- 连接池配置（max_connections, max_keepalive_connections）
- 超时配置（connect / read / write / pool）
- 流式响应支持

**`models_api.py`** - 模型列表管理：
- 从上游获取可用模型（Copilot: 专用 API；Generic: /v1/models）
- 缓存模型列表
- 提供按 ID 查找模型的方法

### `pipeline/` - 请求执行管道

详见 [请求执行管道文档](request-pipeline.md)。

**`context.py`** - `RequestContext`：
- 追踪请求生命周期状态（状态机）
- 记录每次尝试的详情
- 持有原始请求和最终响应引用

**`executor.py`** - 核心执行循环：
- `execute_pipeline()` 函数：编排清洗→审批→限流→执行→重试
- 接收 `FormatAdapter` 和 `RetryStrategy` 列表

**`approval.py`** - 审批门控，详见 [手动审批系统文档](approval-system.md)。

**`rate_limiter.py`** - 自适应限流器，详见 [请求执行管道文档](request-pipeline.md)。

**`strategies/`** - 重试策略，详见 [请求执行管道文档](request-pipeline.md)。

### `transform/` - 转换系统

详见 [转换系统文档](transform-system.md)。

**`model_resolver.py`** - 模型名称标准化与别名映射。
**`translator.py`** - Anthropic ↔ OpenAI 双向格式翻译。
**`sanitizer.py`** - 消息清洗。
**`system_prompt.py`** - 系统提示词定制。

### `streaming/` - 流式处理

详见 [流式处理文档](streaming.md)。

**`sse.py`** - SSE 响应辅助。
**`accumulator.py`** - 流式累积器。
**`translator.py`** - 跨格式流式翻译。

### `routes/` - API 路由

详见 [API 端点规格文档](api-endpoints.md)。

每个文件定义一个 `APIRouter`，在 `server.py` 中注册。

### `history/` - 历史存储

详见 [历史与审计文档](history-system.md)。

**`store.py`** - 内存存储，FIFO 淘汰，异步安全。
**`ws.py`** - WebSocket 管理，实时广播更新。

### `observability/` - 可观测性

**`logging.py`** - 配置 Python logging：
- 结构化 JSON 格式（生产环境）或人类可读格式（开发环境）
- 按 request_id 关联日志

**`tracing.py`** - 配置 OpenTelemetry：
- 自动 instrument FastAPI（入站请求 span）
- 自动 instrument httpx（出站请求 span）
- 可配置 exporter（OTLP / stdout / 禁用）

**`middleware.py`** - 请求日志中间件：
- 记录 method, path, status_code, duration_ms, model（如适用）
- 分配并传播 request_id

### `errors.py` - 错误处理

职责：
- `ApiError` 数据类：统一错误表示
- `classify_error(status_code, body)` → `ApiError`：从 HTTP 响应推断错误类型
- `to_openai_error(error)` → dict：构建 OpenAI 格式错误响应
- `to_anthropic_error(error)` → dict：构建 Anthropic 格式错误响应
- 错误类型枚举：`rate_limited`, `payload_too_large`, `invalid_request`, `auth_error`, `server_error`, `rejected`（审批拒绝）

## 应用生命周期

```python
# server.py 中的 lifespan 伪代码

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings

    # 1. 初始化认证（仅 Copilot 上游需要）
    if settings.upstream_type == "copilot":
        github_token = await get_github_token(settings)
        copilot_auth = CopilotAuth(github_token, settings)
        await copilot_auth.refresh_token()
        upstream = CopilotUpstream(copilot_auth, settings)
    else:
        upstream = GenericUpstream(settings)

    # 2. 创建 HTTP 客户端
    client = UpstreamClient(settings)
    upstream.set_client(client)

    # 3. 获取模型列表
    await upstream.fetch_models()

    # 4. 初始化模型解析器
    model_resolver = ModelResolver(settings.model_mappings, upstream.models)

    # 5. 初始化历史存储
    history_store = HistoryStore(max_entries=settings.history_max_entries)
    ws_manager = WebSocketManager()

    # 6. 初始化限流器
    rate_limiter = AdaptiveRateLimiter(settings)

    # 7. 初始化审批门控
    approval_gate = ApprovalGate(
        enabled=settings.manual_approval,
        timeout=settings.approval_timeout,
    )

    # 存入 app.state
    app.state.upstream = upstream
    app.state.model_resolver = model_resolver
    app.state.history_store = history_store
    app.state.ws_manager = ws_manager
    app.state.rate_limiter = rate_limiter
    app.state.approval_gate = approval_gate

    yield  # 应用运行中

    # 关闭
    await client.close()
    await rate_limiter.shutdown()
    await approval_gate.reject_all_pending("server shutting down")
```

## 测试结构

```
tests/
├── conftest.py              # 共享 fixture
│   ├── app_client           # TestClient（带 mock 上游）
│   ├── mock_upstream        # Mock UpstreamTarget
│   ├── sample_settings      # 测试用 AppSettings
│   └── history_store        # 空 HistoryStore 实例
│
├── test_translator.py       # 格式翻译单元测试
├── test_sanitizer.py        # 消息清洗单元测试
├── test_model_resolver.py   # 模型解析单元测试
├── test_pipeline.py         # 管道执行集成测试
├── test_routes.py           # 路由处理器端到端测试
└── test_history.py          # 历史存储单元测试
```

## 相关文档

- [整体架构概览](architecture.md)
- [API 端点规格](api-endpoints.md)
- [配置系统](config-system.md)
