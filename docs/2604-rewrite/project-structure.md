# 目录结构与模块职责

> 目录树与依赖关系与 [DESIGN.md 模块树](DESIGN.md#核心模块) 保持一致；本文档补充每个模块的职责细节、CLI 完整规格、分阶段 lifespan 与测试结构。

## 完整目录树

```
ghc-api-proxy-py/
├── pyproject.toml                       # 项目元数据、依赖声明（hatchling）
├── main.py                              # 入口点 → app.cli.main()
├── config.example.yaml                  # YAML 配置示例（带详尽注释，非完整清单——见 config-system.md）
│
├── src/app/
│   ├── __init__.py                      # 包初始化、版本号
│   ├── cli.py                           # CLI 参数解析（argparse），多子命令，启动 uvicorn
│   ├── server.py                        # FastAPI 应用工厂、分阶段 lifespan、中间件注册
│   ├── deps.py                          # FastAPI 依赖注入提供者（Depends 工厂函数）
│   ├── errors.py                        # 错误分类、格式化错误响应、wire format 检测
│   ├── shutdown.py                      # 4 阶段优雅关闭 + 信号升级
│   ├── repetition_detector.py           # KMP 流式重复性检测
│   ├── system_prompt.py                 # System prompt override 应用（prepend/append/regex）
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py                  # Pydantic BaseSettings（全部配置项定义，frozen）
│   │   ├── loader.py                    # YAML 加载 + 四层合并逻辑（defaults < yaml < env < cli）
│   │   ├── compat.py                    # 弃用键迁移（精简 warn-and-continue，见 config-system.md）
│   │   └── paths.py                     # 跨平台配置/数据目录路径解析（XDG 支持）
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── openai.py                    # OpenAI API Pydantic 模型（Chat Completions + Responses）
│   │   ├── anthropic.py                 # Anthropic API Pydantic 模型（请求/响应/SSE）
│   │   ├── gemini.py                    # Gemini generateContent 请求/响应模型
│   │   ├── common.py                    # 通用模型（Usage、ModelInfo、ErrorResponse）
│   │   └── capabilities.py              # 模型能力元数据（context_editing/interleaved_thinking 等家族表）
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── providers.py                 # Token provider 链（CLI/env/file/device-auth，按优先级查找）
│   │   ├── github.py                    # GitHub token 管理（读取/存储/校验）
│   │   ├── copilot.py                   # GitHub→Copilot token 交换、自动刷新
│   │   └── device_flow.py               # GitHub OAuth 设备授权流程实现
│   │
│   ├── upstream/
│   │   ├── __init__.py
│   │   ├── base.py                      # UpstreamTarget 协议定义
│   │   ├── copilot.py                   # GitHub Copilot 上游（含请求头伪装、intent 头）
│   │   ├── generic.py                   # 通用 OpenAI/Anthropic 兼容上游
│   │   ├── client.py                    # httpx.AsyncClient 封装（连接池、超时、代理、HTTP/2）
│   │   └── models_api.py                # 上游模型列表获取、缓存、定期刷新、两种输出格式
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── context.py                   # RequestContext 状态机（pending→streaming→completed/failed）
│   │   ├── manager.py                   # RequestContextManager（活跃请求跟踪 + stale reaper + deadline）
│   │   ├── executor.py                  # 请求执行管道核心循环
│   │   ├── rate_limiter.py              # 自适应三模式限流器（Normal/Rate-Limited/Recovering）
│   │   ├── approval.py                  # 手动审批门控（asyncio.Event）
│   │   └── strategies/
│   │       ├── __init__.py
│   │       ├── base.py                  # RetryStrategy 协议定义
│   │       ├── auto_truncate.py         # 自动截断策略（含 token 限制学习）
│   │       ├── token_refresh.py         # Token 刷新策略（401/403 触发）
│   │       ├── network_retry.py         # 网络重试策略（ECONNRESET/ETIMEDOUT）
│   │       ├── orphan_cleanup.py        # 孤立块清理策略
│   │       ├── deferred_tool_retry.py   # Deferred tool 重试策略
│   │       ├── poisoned_thinking.py     # L2/L3 thinking 拒绝一次性剥离 + 隔离登记
│   │       └── server_tool_rejection.py # server tool 结果被拒后的降级重试
│   │
│   ├── anthropic/
│   │   ├── __init__.py
│   │   ├── client.py                    # Anthropic API 客户端（直连 Copilot 原生 Anthropic 端点）
│   │   ├── request_preparation.py       # 请求准备编排（wire payload/headers/cache/thinking/negotiation）
│   │   ├── feature_negotiation.py       # 功能协商（多类别学习缓存 + TTL 裁决）
│   │   ├── features.py                  # 模型特性检测 + anthropic-beta headers + context management
│   │   ├── message_tools.py             # Tool 预处理管道（tool_search 注入、defer_loading、CC 官方工具注入）
│   │   ├── server_tool_filter.py        # Server tool 结果过滤（响应侧安全网 + 块索引重映射）
│   │   ├── warmup.py                    # Warmup 请求策略（allow/reject/drop/fake）
│   │   ├── stream_accumulator.py        # Anthropic SSE 事件累积器
│   │   ├── token_counting.py            # count_tokens（上游转发 / 本地校准估算）
│   │   │
│   │   ├── sanitize/                    # 2 阶段清洗管道（见 sanitize-pipeline.md）
│   │   │   ├── __init__.py              # 管道入口，编排预处理 + 可重复清洗阶段
│   │   │   ├── content_blocks.py        # Content block 级别清洗
│   │   │   ├── deduplicate_tool_calls.py # 重复 tool_use/tool_result 对去重
│   │   │   ├── read_tool_result_tags.py # Read 工具结果中的 system-reminder 标签剥离
│   │   │   ├── result.py                # 清洗结果数据类
│   │   │   ├── system_prompt.py         # System prompt 中的标签清洗
│   │   │   ├── system_reminders.py      # 消息中的 system-reminder 标签重写/移除
│   │   │   ├── text_blocks.py           # 空 text block 过滤（安全网）
│   │   │   └── tool_blocks.py           # Tool block 配对检查、孤儿过滤、name 大小写修正
│   │   │
│   │   ├── thinking/                    # Thinking 处理管道（见 thinking-pipeline.md），P5 内存重设计
│   │   │   ├── __init__.py
│   │   │   ├── protection.py            # 块级保护（preserve/stripped）
│   │   │   ├── destack.py               # 去堆叠相邻 thinking（passthrough/insert_text/move_blocks）
│   │   │   ├── strip_all.py             # L2 一次性剥离全部 thinking（reject 触发）
│   │   │   ├── quarantine.py            # L3 会话隔离（内存 dict + 滑动 TTL，替代上游磁盘 sidecar）
│   │   │   └── signature_compat.py      # thinking signature 兼容重写
│   │   │
│   │   └── header_policy/               # 请求/响应头转发（见 header-forwarding.md）
│   │       ├── __init__.py
│   │       ├── request_header_forward.py  # 客户端→上游请求头黑/白名单 + 安全底线
│   │       └── response_header_forward.py # 上游→客户端响应头黑/白名单 + 安全底线
│   │
│   ├── openai/
│   │   ├── __init__.py
│   │   ├── client.py                    # Chat Completions API 客户端
│   │   ├── responses_client.py          # Responses API 客户端
│   │   ├── responses_conversion.py      # Responses API 数据格式转换（input/output ↔ 历史 + call_id 标准化）
│   │   ├── embeddings.py                # Embeddings API 客户端
│   │   ├── sanitize.py                  # OpenAI 消息清洗 + 孤儿 tool call 过滤
│   │   ├── stream_accumulator.py        # Chat Completions SSE 事件累积器
│   │   └── responses_stream_accumulator.py # Responses SSE 事件累积器
│   │
│   ├── protocols/                       # 协议适配层（多协议兼容，见 multi-protocol.md）
│   │   ├── __init__.py
│   │   ├── azure.py                     # Azure OpenAI（deployment 经典格式 + v1）适配
│   │   └── gemini.py                    # Google Gemini `/v1beta` 适配
│   │
│   ├── transform/
│   │   ├── __init__.py
│   │   ├── model_resolver.py            # 模型名称解析（别名、标准化、Override、Family 回退）
│   │   ├── translator.py                # 跨协议格式翻译（Anthropic ↔ OpenAI ↔ Gemini）
│   │   └── system_prompt.py             # 系统提示词定制（prepend/append/regex）
│   │
│   ├── streaming/
│   │   ├── __init__.py
│   │   ├── sse.py                       # SSE StreamingResponse 构建工具
│   │   ├── idle_timeout.py              # StreamIdleTimeoutError + 超时检测
│   │   ├── keepalive.py                 # Keepalive 心跳（empty_text anchor / ping，见 streaming-resilience.md）
│   │   ├── delayed_commit.py            # 延迟提交窗口（stream_commit_after_sec）
│   │   ├── buffered_retry.py            # 整响应缓冲重试（opt-in，默认关，见 P6/BACKLOG）
│   │   └── translator.py                # 跨格式流式翻译（Chat ↔ Anthropic ↔ Responses ↔ Gemini）
│   │
│   ├── auto_truncate/
│   │   ├── __init__.py
│   │   ├── engine.py                    # 响应式 auto-truncate 引擎（截断策略选择）
│   │   └── token_limits.py              # 动态 token 限制学习（从错误响应提取）
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── openai.py                    # POST chat/completions, GET models, embeddings（三重前缀，见 BACKLOG #5）
│   │   ├── responses.py                 # POST/GET responses（HTTP + WebSocket）
│   │   ├── anthropic.py                 # POST v1/messages, v1/messages/count_tokens, GET anthropic/v1/models
│   │   ├── azure.py                     # /openai/deployments/:deployment/* （经典格式）
│   │   ├── gemini.py                    # /v1beta/models/:model:{generateContent,streamGenerateContent,countTokens}
│   │   ├── management.py                # /api/status, /api/config(/yaml), /api/tokens, /api/models, /api/logs, /api/negotiation/*
│   │   ├── health.py                    # /health, /health/liveness, /health/readiness
│   │   ├── metrics.py                   # /metrics（Prometheus 文本）
│   │   ├── history.py                   # /history/api/* 历史查看端点 + /history/ws
│   │   └── approval.py                  # /api/approval/* 手动审批端点
│   │
│   ├── history/
│   │   ├── __init__.py
│   │   ├── store.py                     # 异步历史存储门面（off-loop 写入，见 P1）
│   │   ├── sqlite/                      # 异步 SQLite 后端（writer 任务 + asyncio.Queue，off-event-loop）
│   │   │   ├── __init__.py
│   │   │   ├── schema.py                # 建表 DDL、迁移
│   │   │   ├── writer.py                # 单一 writer 任务，串行消费队列，落盘
│   │   │   ├── reaper.py                # 按 success_limit/failure_limit 定期删最旧
│   │   │   └── sessions_agg.py          # Session 聚合查询（GROUP BY session_id）
│   │   ├── in_flight.py                 # 进行中请求内存映射（WebSocket 实时视图）
│   │   ├── sessions.py                  # Session 识别（HTTP header 优先，`x-claude-code-session-id` 领先 / previous_response_id 兜底）
│   │   ├── ws.py                        # WebSocket 连接管理与广播
│   │   └── types.py                     # HistoryEntry / EntrySummary / SessionSummary 类型定义
│   │
│   ├── context/
│   │   ├── __init__.py
│   │   ├── manager.py                   # RequestContextManager 门面（委托 pipeline/manager.py）
│   │   ├── consumers.py                 # 请求上下文消费者注册机制（完成/失败通知）
│   │   └── error_persistence.py         # 错误持久化消费者（文件系统）
│   │
│   └── observability/
│       ├── __init__.py
│       ├── logging.py                   # 结构化日志配置（JSON/text 格式切换，固定宽度前缀）
│       ├── tracing.py                   # OpenTelemetry 链路追踪配置
│       ├── middleware.py                # 请求日志/追踪中间件
│       ├── telemetry.py                 # 请求遥测（model/tokens/reasoning/duration，轻量计数器，见 BACKLOG #3）
│       └── tui.py                       # 终端 UI（可选，Console 格式化输出）
│
└── tests/
    ├── conftest.py                      # 共享 fixture（TestClient、mock upstream、sample settings）
    ├── unit/
    │   ├── test_model_resolver.py       # 模型解析单元测试
    │   ├── test_sanitizer.py            # 消息清洗单元测试
    │   ├── test_translator.py           # 格式翻译单元测试（含 Gemini）
    │   ├── test_features.py             # Feature 检测单元测试
    │   ├── test_feature_negotiation.py  # Feature negotiation 单元测试
    │   ├── test_auto_truncate.py        # Auto-truncate 单元测试
    │   ├── test_repetition_detector.py  # 重复性检测单元测试
    │   ├── test_rate_limiter.py         # 限流器单元测试
    │   ├── test_approval.py             # 审批门控单元测试
    │   ├── test_error_persistence.py    # 错误持久化单元测试
    │   ├── test_thinking_pipeline.py    # Thinking 保护/destack/quarantine 单元测试
    │   ├── test_header_policy.py        # 请求/响应头黑白名单 + 安全底线单元测试
    │   └── test_history.py              # 历史存储单元测试
    ├── component/
    │   ├── test_pipeline.py             # 管道执行集成测试（含重试、限流）
    │   ├── test_history_store.py        # History 存储完整 CRUD + reaper 测试
    │   ├── test_history_api.py          # History API 测试
    │   ├── test_history_ws.py           # History WebSocket 测试
    │   └── test_streaming_resilience.py # keepalive/延迟提交/缓冲重试集成测试
    └── http/
        ├── test_anthropic_routes.py     # Anthropic 路由端到端测试
        ├── test_openai_routes.py        # OpenAI 路由端到端测试
        ├── test_responses_routes.py     # Responses API 路由端到端测试
        ├── test_azure_routes.py         # Azure OpenAI 适配路由测试
        ├── test_gemini_routes.py        # Gemini 适配路由测试
        └── test_management_routes.py    # 管理路由测试（health、config、token、usage、metrics）
```

## 模块间依赖关系

```
                          cli.py
                            │
                            ▼
                         server.py ────────────────────────┐
                            │                               │
           ┌────────────────┼──────────────┬────────────┐  │
           ▼                ▼              ▼            ▼  ▼
        config/          deps.py        routes/    observability/
           │                │              │
           │          ┌─────┼──────┐      │
           │          ▼     ▼      ▼      │
           │       upstream/ pipeline/ history/
           │          │        │         │
           │          │    ┌───┴────┐    │
           │          │    ▼        ▼    │
           │          │ approval rate_limiter
           │          │    │             │
           │          ▼    │             │
           │        auth/  │             │
           │               │             │
           │        context/ ←───────────┘
           │          │
           └──────┬───┤
                  │   ▼
                  │  anthropic/  openai/  protocols/(azure,gemini)
                  │   │            │            │
                  ▼   ▼            ▼            ▼
              transform/  ←──  streaming/  ──→  models/
                  │                              │
                  ▼                              ▼
              auto_truncate/                 errors.py
```

**依赖规则：**

- `models/` 和 `errors.py` 是叶子模块，不依赖其他业务模块
- `transform/` 仅依赖 `models/`
- `streaming/` 依赖 `models/` 和 `transform/`
- `auto_truncate/` 依赖 `models/`
- `anthropic/` 依赖 `models/`、`transform/`、`streaming/`、`auto_truncate/`
- `openai/` 依赖 `models/`、`streaming/`、`auto_truncate/`
- `protocols/`（azure、gemini）依赖 `models/`、`transform/`、`openai/` 或 `anthropic/`（各自复用对应格式的客户端与清洗）
- `auth/` 仅依赖 `config/`
- `upstream/` 依赖 `auth/`、`config/`、`models/`
- `context/` 依赖 `history/`、`pipeline/`（manager 的门面）
- `pipeline/` 依赖 `upstream/`、`transform/`、`anthropic/`、`openai/`、`history/`、`context/`、`config/`
- `routes/` 依赖 `pipeline/`、`models/`、`deps.py`
- `server.py` 组装所有模块
- `cli.py` 仅调用 `server.py` 和 `config/`

## 各模块详述

### `cli.py` — 命令行入口

职责：
- 使用 `argparse` 解析命令行参数（port、host、config、verbose 等）
- 支持子命令：`start`（默认）、`auth`（别名 `login`）、`logout`、`debug`（子命令 `info`/`models`/`usage`——**注意 `debug usage` 才是使用量查询，无顶层 `check-usage`**）、`setup-claude-code`、`setup-codex`、`list-claude-code`
- 调用 `config.loader` 完成四层配置合并（含 `compat.py` 弃用键迁移）
- 调用 `uvicorn.run()` 启动 ASGI 服务器
- 支持 `--generate-config` 生成默认配置文件

`start` 子命令选项（完整清单，供 [config-system.md](config-system.md#cli-参数) 引用）：

| 选项 | 别名 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| `--port` | `-p` | str | `4141` | 监听端口 |
| `--host` | `-H` | str | 无（回落 config `127.0.0.1`） | 监听地址（`localhost`/`any` 特殊值） |
| `--verbose` | `-v` | bool | `False` | 详细日志 |
| `--account-type` | `-a` | str | 无（回落推断/`individual`） | Copilot 账户类型 |
| `--ghc-api-base-url` | — | str | 无 | 显式上游 base URL |
| `--rate-limit` | — | bool | `True` | 自适应限流（`--no-rate-limit` 关闭） |
| `--history` | — | bool | 无（回落 config） | 历史记录（`--no-history` 强制关闭） |
| `--github-token` | `-g` | str | 无 | GitHub token |
| `--proxy` | — | str | 无 | 出站代理 URL |
| `--config` | — | str | 无 | YAML 配置文件路径 |
| `--manual` | — | flag | `False` | 启用手动审批（映射 `approval.enabled=true`） |
| `--generate-config` | — | flag | — | 生成默认配置文件并退出 |

对外接口：
- `main()` 函数，由 `main.py` 调用

### `server.py` — 应用工厂

职责：
- `create_app(settings) -> FastAPI`：创建并配置 FastAPI 实例
- `lifespan` 异步上下文管理器管理完整应用生命周期（**分阶段启动**，见下）
- 注册所有路由（`routes/` 下各 router，OpenAI 端点按 [BACKLOG #5](BACKLOG.md#5-三重前缀路由注册-采纳但简化) 用循环注册三重前缀，避免重复 handler）
- 注册中间件：CORS、请求日志、OpenTelemetry

#### `lifespan` 分阶段启动

对齐 [DESIGN.md](DESIGN.md#运行时选项) 描述的分阶段启动次序：Phase 0 校验 → 1 日志 → 1.5 可观测性 → 2 版本/身份 → 2.5 加载配置 → 2.6 代理 → 3 后端存储/限流/context manager → 4 网络/token/模型 → 5 启动服务器。各阶段的后台任务（history writer、模型刷新、stale reaper）均 **off-loop**，不阻塞请求路径（见 P1/P5 性能原则）。

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: AppSettings = app.state.settings

    # Phase 0 —— 启动期校验
    # 校验 upstream.type、ghc_api_base_url 格式、YAML 结构合法性等，失败则 fail-fast
    validate_startup_config(settings)

    # Phase 1 —— 日志系统
    configure_logging(settings.observability)

    # Phase 1.5 —— 可观测性（tracing、metrics registry）
    configure_tracing(settings.observability)
    metrics_registry = init_metrics_registry()

    # Phase 2 —— 版本/身份解析
    # 解析 auth.account_type（若未显式设置则从登录账户 copilot_plan 推断）
    account_type = await resolve_account_type(settings)

    # Phase 2.5 —— 加载配置（第二次校验：结合运行时信息，如账户类型派生 base_url）
    resolved_settings = settings.with_account_type(account_type)

    # Phase 2.6 —— 代理配置
    configure_proxy(resolved_settings.upstream.proxy)

    # Phase 3 —— 后端存储 / 限流 / context manager 初始化
    history_store = HistoryStore(resolved_settings.history)  # off-loop：内部起 writer 任务
    ws_manager = WebSocketManager()
    rate_limiter = AdaptiveRateLimiter(resolved_settings.rate_limiter)
    approval_gate = ApprovalGate(
        enabled=resolved_settings.approval.enabled,
        timeout=resolved_settings.approval.timeout_seconds,
    )
    context_manager = RequestContextManager(
        stale_max_age=resolved_settings.timeouts.stale_request_max_age,
        request_deadline=resolved_settings.timeouts.request_deadline,
    )
    error_consumer = ErrorPersistenceConsumer(resolved_settings)
    context_manager.register_consumer(error_consumer)

    # Phase 4 —— 网络 / token / 模型初始化
    if resolved_settings.upstream.type == "copilot":
        github_token = await get_github_token(resolved_settings)   # auth/providers.py 四源链
        copilot_auth = CopilotAuth(github_token, resolved_settings)
        await copilot_auth.refresh_token()
        upstream = CopilotUpstream(copilot_auth, resolved_settings)
    else:
        upstream = GenericUpstream(resolved_settings)

    client = UpstreamClient(resolved_settings)   # httpx.AsyncClient，连接池/HTTP2/代理
    upstream.set_client(client)
    await upstream.fetch_models()
    model_resolver = ModelResolver(resolved_settings.model_mappings, upstream.models)

    # 后台任务（off-loop，不阻塞请求路径）
    background_tasks: list[asyncio.Task] = []
    if resolved_settings.model_refresh_interval > 0:
        background_tasks.append(
            asyncio.create_task(periodic_model_refresh(upstream, resolved_settings.model_refresh_interval))
        )
    if resolved_settings.history.enabled and resolved_settings.history.reaper_interval > 0:
        background_tasks.append(
            asyncio.create_task(history_store.run_reaper(resolved_settings.history.reaper_interval))
        )
    background_tasks.append(
        asyncio.create_task(context_manager.run_stale_reaper())
    )

    # Phase 5 —— 存入 app.state，服务器就绪
    app.state.upstream = upstream
    app.state.model_resolver = model_resolver
    app.state.context_manager = context_manager
    app.state.history_store = history_store
    app.state.ws_manager = ws_manager
    app.state.rate_limiter = rate_limiter
    app.state.approval_gate = approval_gate
    app.state.background_tasks = background_tasks

    yield  # 应用运行中

    # 4 阶段优雅关闭（见 shutdown.md）
    await graceful_shutdown(app)
```

**性能要点**：
- Phase 3/4 的初始化本身是启动期一次性成本，不在请求热路径
- `history_store` 内部持有 writer 任务与有界 `asyncio.Queue`；请求完成后写历史是 fire-and-forget，不阻塞响应返回（P1）
- `periodic_model_refresh` / `run_reaper` / `run_stale_reaper` 全部是独立后台 `asyncio.Task`，与请求处理并发但不共享阻塞资源
- L3 thinking quarantine（`anthropic/thinking/quarantine.py`）常驻内存 dict，不在 lifespan 中做磁盘初始化（P5）

### `deps.py` — 依赖注入

职责：
- 提供 FastAPI `Depends` 工厂函数
- 从 `request.app.state` 获取 lifespan 中初始化的单例对象

**Python 优化**：JS 版本使用全局 `state` 对象，所有模块直接 import。Python 版本通过 FastAPI 依赖注入，每个路由处理器声明需要的依赖，测试时可直接替换（`app.dependency_overrides`）。

```python
def get_settings(request: Request) -> AppSettings: ...
def get_upstream(request: Request) -> UpstreamTarget: ...
def get_history_store(request: Request) -> HistoryStore: ...
def get_rate_limiter(request: Request) -> AdaptiveRateLimiter: ...
def get_approval_gate(request: Request) -> ApprovalGate: ...
def get_model_resolver(request: Request) -> ModelResolver: ...
def get_ws_manager(request: Request) -> WebSocketManager: ...
def get_context_manager(request: Request) -> RequestContextManager: ...
```

### `config/` — 配置系统

详见 [配置系统文档](config-system.md)（完整配置清单权威来源）。

- **`settings.py`** — 全部配置项的 Pydantic 模型定义（frozen）
- **`loader.py`** — 四层合并（defaults < yaml < env < cli）
- **`compat.py`** — 精简弃用键迁移（见 config-system.md 迁移表，无历史包袱，见 [BACKLOG #6](BACKLOG.md#6-大量配置-compat-迁移层-简化)）
- **`paths.py`** — 跨平台配置/数据目录（支持 `XDG_CONFIG_HOME`/`XDG_DATA_HOME`）

### `models/` — 数据模型

详见 [核心数据模型文档](data-models.md)。新增 `gemini.py`（Gemini generateContent 请求/响应）、`capabilities.py`（模型能力元数据，对应 `anthropic.model_capabilities.*` 配置）。

### `auth/` — 认证系统

详见 [认证文档](authentication.md)。

- **`providers.py`** — Token provider 链：CLI（`--github-token`）> env（`GITHUB_TOKEN`）> file（`auth.token_file` 或默认路径）> device-auth（OAuth 设备授权流程），按优先级依次查找
- **`github.py`** — GitHub token 存取
- **`copilot.py`** — Copilot token 交换与自动刷新
- **`device_flow.py`** — GitHub OAuth 设备授权流程

### `upstream/` — 上游目标管理

**`base.py`** — `UpstreamTarget` 协议定义，所有上游必须实现的接口：`send_openai()`、`send_anthropic()`、`send_responses()`、`fetch_models()`。

**`copilot.py`** — GitHub Copilot 上游实现：
- 注入 Copilot token 到请求头
- 构建 VSCode 扩展伪装头（`editor-version`、`editor-plugin-version`、`copilot-integration-id`、`openai-intent`），键值来自 [`headers` 配置 section](config-system.md#headers-section-copilot-请求头伪装)
- 支持 3 个 Copilot 端点：`/chat/completions`、`/v1/messages`、`/responses`
- 通过 GitHub API 获取可用模型列表
- 根据模型 capabilities 构建请求特定头（vision、agent intent）
- `upstream.ghc_api_base_url` 显式设置时覆盖 `auth.account_type` 派生的 URL

**`generic.py`** — 通用上游实现：
- 可配置端点 URL（`upstream.openai_base_url`、`upstream.anthropic_base_url`）
- 可配置认证（`upstream.api_key` + `upstream.auth_type`：bearer / x-api-key）
- 适用于任意 OpenAI/Anthropic 兼容服务；若目标不支持 `/v1/models`，走 `upstream.models`（手动模型声明）

**`client.py`** — httpx 客户端封装：
- 创建和管理单个 `httpx.AsyncClient`（连接复用，见 DESIGN.md 通用性能取向）
- 连接池配置（`max_connections`、`max_keepalive_connections`、`keepalive_expiry`）
- 超时配置（`connect_timeout`/`read_timeout`，对应 `timeouts.response_header`/`stream_idle`）
- HTTP/2 支持（`upstream.http2`）
- HTTP/HTTPS/SOCKS5 代理支持（`upstream.proxy`）

**`models_api.py`** — 模型列表管理：
- 从上游获取可用模型（Copilot：专用 API；Generic：`/v1/models`）
- 构建 O(1) 查找索引（`model_index: dict[str, Model]`、`model_ids: set[str]`）
- 定期后台刷新（`model_refresh_interval` 秒，off-loop `asyncio.Task`）
- 提供两种输出格式：OpenAI 标准格式（`/models`）与内部完整格式（`/api/models`）

### `pipeline/` — 请求执行管道

详见 [请求执行管道文档](request-pipeline.md)。

- **`context.py`** — `RequestContext` 状态机：`pending` → `streaming` → `completed` / `failed`
- **`manager.py`** — `RequestContextManager`：跟踪活跃请求生命周期、stale reaper（定期检查超时请求强制清理）、hard request deadline 计时器
- **`executor.py`** — 管道核心循环：清洗 → 审批（可选）→ 限流 → 执行 → 重试（策略模式）
- **`rate_limiter.py`** — 自适应三模式限流器（Normal → Rate-Limited → Recovering）
- **`approval.py`** — 手动审批门控（`asyncio.Event`，本项目独有 `[新增]`）
- **`strategies/`** — 重试策略集合：`network_retry`、`token_refresh`、`auto_truncate`、`orphan_cleanup`、`deferred_tool_retry`、`poisoned_thinking`（L2/L3）、`server_tool_rejection`；共享 `retry.max_reactive_retries` 预算

### `anthropic/` — Anthropic 协议处理

详见 [Anthropic 兼容性文档](anthropic-compat.md)、[消息清洗管道文档](sanitize-pipeline.md)、[Tool Use 文档](tool-use.md)、[Thinking 处理管道](thinking-pipeline.md)、[请求/响应头转发安全](header-forwarding.md)。

**`client.py`** — Anthropic API 客户端，直连 Copilot 的原生 Anthropic 端点。

**`sanitize/`** — 2 阶段清洗管道（预处理 + 可重复清洗），入口在 `__init__.py`；子模块见目录树。

**`request_preparation.py`** — 请求准备编排：
- 构建 wire payload（剥离 Copilot 不接受的字段如 `inference_geo`）
- 调整 thinking budget（根据模型 min/max budget 和 max_tokens 约束，含 `thinking_coerce_adaptive`）
- 按 `anthropic.cache_control` 模式注入/清洗 `cache_control` breakpoint
- 应用请求头策略（`header_policy/request_header_forward.py`）+ `anthropic-beta` headers + `X-Initiator`
- 触发 `feature_negotiation` 查询已知不支持的特性

**`feature_negotiation.py`** — 功能协商：
- 使用 TTL 缓存（`negotiation_learning.default_ttl_days`，默认 30 天，可按类别覆盖）记录不支持的功能（如 `context_management`、tool 字段、beta headers、effort、partner features、cache_control 子字段等多个类别）
- 当某功能请求被拒时标记为 unsupported，后续请求跳过该功能
- 缓存键：`{base_url}|{endpoint}|{normalized_model}`（feature/beta token 是 value，不进 key）
- 管理 API：`GET/POST /api/negotiation/*` 查看/清除学习记录

**`features.py`** — 模型特性检测与 beta headers：
- `model_supports_interleaved_thinking()` — 按 `anthropic.model_capabilities.interleaved_thinking` 家族前缀表
- `model_supports_context_editing()` — 按 `model_capabilities.context_editing`
- `model_supports_tool_search()` — Claude ≥4.5 默认允许 + `model_capabilities.tool_search_overrides` 强制覆盖
- `build_anthropic_beta_headers()` — 根据模型能力构建 `anthropic-beta` 头
- `build_context_management()` — 构建 `context_management` 请求体（受 `anthropic.context_editing*` 配置驱动）

**`message_tools.py`** — Tool 预处理管道：
- 按 `anthropic.tool_search` 注入 `tool_search_tool_regex` 工具
- 标记不常用工具为 `defer_loading: true`（`tool_search_non_deferred` 排除列表）
- 按 `anthropic.tool_inject_claude_code` 注入 Claude Code 官方工具桩

**`server_tool_filter.py`** — Server tool 结果过滤（响应侧常驻安全网），含块索引重映射，避免破坏客户端消息索引一致性。

**`warmup.py`** — Warmup 策略（`anthropic.warmup`：allow/reject/drop/fake）。

**`thinking/`** — Thinking 处理管道（`[重构，见 P5]`）：
- **`protection.py`** — `thinking_block_message_policy`（preserve/stripped）块级保护
- **`destack.py`** — `thinking_destack_strategy`（passthrough/insert_text/move_blocks）去堆叠
- **`strip_all.py`** — L2：`strip_thinking_on_reject` 触发的一次性剥离 + 重试
- **`quarantine.py`** — L3：`poisoned_thinking_quarantine` 常驻内存 dict + 滑动 TTL（`poisoned_thinking_ttl_hours`），**替代上游磁盘 sidecar SQLite**，热路径零磁盘 I/O
- **`signature_compat.py`** — `thinking_signature_compat` 签名兼容重写

**`header_policy/`** — 请求/响应头转发（黑名单/白名单双模式 + 安全底线）：
- **`request_header_forward.py`** — `strict_request_headers` + `request_header_blacklist`/`whitelist` + `strip_attribution_header`
- **`response_header_forward.py`** — `strict_response_headers` + `response_header_blacklist`/`whitelist`

### `openai/` — OpenAI 协议处理

**`client.py`** — Chat Completions API 客户端。

**`responses_client.py`** — Responses API 客户端。

**`responses_conversion.py`** — Responses API 数据转换：
- `input` 数组 ↔ 对话历史格式转换
- `output` 数组解析
- `call_` → `fc_` 前缀 ID 标准化（`openai_responses.normalize_call_ids` 启用时）

**`embeddings.py`** — Embeddings API 客户端。

**各 accumulator** — SSE 事件累积器，在流式转发的同时累积完整响应用于 History 记录（旁路记账，不阻塞转发）。

### `protocols/` — 多协议适配层 `[新增]`

详见 [多协议兼容文档](multi-protocol.md)。

**`azure.py`** — Azure OpenAI 适配：
- 经典格式 `/openai/deployments/:deployment/{chat/completions,embeddings,responses}`，`model` 从 URL path 注入，`api-version` query 被忽略
- 复用 `openai/` 下的客户端与清洗逻辑，仅做路径/参数映射

**`gemini.py`** — Google Gemini 适配：
- `/v1beta/models/:model:{generateContent,streamGenerateContent,countTokens}`
- 复用 `transform/translator.py` 做格式转换，`models/gemini.py` 定义请求/响应模型

### `transform/` — 转换系统

详见 [转换系统 / 模型解析文档](model-resolution.md)。

- **`model_resolver.py`** — 别名（`model_overrides`/`model_mappings`）、标准化、Override、Family 回退、链式解析
- **`translator.py`** — Anthropic ↔ OpenAI ↔ Gemini 多向格式翻译，按 `model_translation` 规则应用特性剥离
- **`system_prompt.py`** — 系统提示词定制（prepend/append/regex，按 model/endpoint 限定作用域）

### `streaming/` — 流式处理

详见 [流式处理文档](streaming.md)、[流式韧性文档](streaming-resilience.md)。

- **`sse.py`** — SSE `StreamingResponse` 构建工具，逐事件直通（P1/通用性能取向：默认零缓冲）
- **`idle_timeout.py`** — `StreamIdleTimeoutError` + 超时检测（`timeouts.stream_idle` / `stream_idle_overrides`）
- **`keepalive.py`** — 客户端侧心跳（`stream_keepalive_mode`：`empty_text`（默认，稳定）/`ping`（逃生舱）；`enveloped_ping` **`[拒绝]`不实现**，见 ROADMAP）
- **`delayed_commit.py`** — 延迟提交窗口（`stream_commit_after_sec`），窗口内错误保留真实 HTTP 状态，超时后提交 200 + keepalive
- **`buffered_retry.py`** — 整响应缓冲重试（`[上游实验][采纳默认关]`，见 P6），仅在显式 opt-in 时启用，内存开销大
- **`translator.py`** — 跨格式流式翻译（Chat ↔ Anthropic ↔ Responses ↔ Gemini）

**性能要点**：默认路径（`buffered_retry` 关闭时）零缓冲直通，累积器只做轻量增量记账，不重建完整响应对象（呼应 P6/P7）。

### `auto_truncate/` — 自动截断

- **`engine.py`** — 响应式 auto-truncate 引擎：截断策略选择（压缩旧 tool_result → 移除最旧消息对 → 进一步截断），保留 system 消息与最近约 30% 对话
- **`token_limits.py`** — 动态 token 限制学习：从错误响应中提取模型实际 token 限制并缓存，后续请求提前截断

### `routes/` — API 路由

详见 [API 端点规格 / DESIGN.md 路由表](DESIGN.md#路由)。

每个文件定义一个或多个 `APIRouter`，在 `server.py` 中注册。OpenAI 端点（`openai.py`）按 [BACKLOG #5](BACKLOG.md#5-三重前缀路由注册-采纳但简化) 用单一 router + 循环挂载三重前缀（无前缀 / `/v1` / `/openai/v1`），避免重复 handler。路由处理器通过 `Depends` 获取依赖。

新增文件：
- **`azure.py`** — Azure OpenAI deployment 经典格式
- **`gemini.py`** — Google Gemini `/v1beta`
- **`management.py`** — 聚合管理 API（`/api/status`、`/api/config`、`/api/config/yaml`、`/api/tokens`、`/api/models`、`/api/logs`、`/api/negotiation/*`、`/api/event_logging/batch`）
- **`metrics.py`** — `/metrics` Prometheus 文本暴露

### `history/` — 历史存储

详见 [历史与审计文档](history-system.md)。

- **`store.py`** — 门面，对外暴露简单读写接口，内部委托 `sqlite/` 后端；写入路径 fire-and-forget（P1）
- **`sqlite/`** — 异步 SQLite 后端：**单一 writer 任务** + 有界 `asyncio.Queue` 消费落盘，请求完成不阻塞在落盘上；`reaper.py` 按 `success_limit`/`failure_limit` 定期删最旧行（简单方案，替代上游三层归档，见 [BACKLOG #1](BACKLOG.md#1-分层降温归档hot--tier1--tier2-缓存延后)）
- **`in_flight.py`** — 进行中请求的内存映射，供 WebSocket 实时视图（终态才落盘，非上游的多 stage 增量写入，见 [BACKLOG #4](BACKLOG.md#4-clientupstream-双腿数据模型--多-stage-持久化-简化)）
- **`sessions.py`** — Session 识别：优先 `x-claude-code-session-id` HTTP header（Claude Code 实际发送、稳定复用的会话 UUID），兜底 `previous_response_id`（Responses API 场景）
- **`ws.py`** — WebSocket 连接管理与广播
- **`types.py`** — `HistoryEntry`（轻量 dataclass，非上游 client/upstream 双腿重对象图）、`EntrySummary`、`SessionSummary`

### `context/` — 请求上下文管理

详见 [优雅关闭文档](shutdown.md)。

- **`manager.py`** — 门面，委托 `pipeline/manager.py` 的 `RequestContextManager` 实现（跟踪、stale reaper、deadline）
- **`consumers.py`** — 消费者注册机制（请求完成/失败时通知）
- **`error_persistence.py`** — 错误持久化消费者：请求失败时写入文件系统（`get_error_persistence_dir()`）

### `observability/` — 可观测性

详见 [可观测性文档](telemetry-observability.md)。

- **`logging.py`** — Python logging 配置：结构化 JSON（生产）或人类可读 text（开发），按 `request_id` 关联，固定宽度 ASCII 前缀对齐
- **`tracing.py`** — OpenTelemetry 配置：自动 instrument FastAPI（入站 span）+ httpx（出站 span），可配置 exporter（OTLP/stdout/禁用）
- **`middleware.py`** — 请求日志中间件：记录 method、path、status_code、duration_ms、model，分配并传播 request_id
- **`telemetry.py`** — 请求遥测：轻量内存计数器（model/tokens/reasoning_tokens/duration），不自建 DDSketch/SQLite 分层（见 [BACKLOG #3](BACKLOG.md#3-分层遥测ddsketch--rawhourlydaily-简化)），配合 `/metrics` 输出与可选 OpenTelemetry 导出
- **`tui.py`** — 终端 UI（可选）：Console 格式化输出，`streaming...` 长请求指示器

**性能要点**：`telemetry.py` 的计数器更新为纯内存操作、O(1)；`logging.py`/`tracing.py` 的 I/O（写文件/导出）异步化或走独立 exporter 线程，不阻塞请求协程。

### `errors.py` — 错误处理

详见 [请求执行管道文档](request-pipeline.md)。包含错误分类、格式化错误响应构建、wire format 检测（区分 Anthropic/OpenAI/Gemini 错误形态）。

### `shutdown.py` — 优雅关闭

详见 [优雅关闭文档](shutdown.md)。4 阶段（Setup → Graceful Wait → Abort → Force Close）+ 信号升级（SIGTERM/SIGINT 二次触发提前进入下一阶段）。

### `repetition_detector.py` — 重复性检测

使用 KMP 前缀函数检测流式输出中的重复模式。当模型陷入重复输出循环时发出警告。

### `system_prompt.py` — System Prompt Override

应用 `system_prompt.*` 配置中的系统提示词覆盖规则（prepend/append/regex，按 model/endpoint 限定作用域）。

## 测试结构

```
tests/
├── conftest.py                      # 共享 fixture
│   ├── app_client                   # TestClient（带 mock 上游）
│   ├── mock_upstream                # Mock UpstreamTarget
│   ├── sample_settings              # 测试用 AppSettings
│   ├── history_store                # 空 HistoryStore 实例（内存 SQLite）
│   └── mock_context_manager         # Mock RequestContextManager
│
├── unit/                            # 纯函数/类单元测试
│   ├── test_model_resolver.py       # 别名、标准化、Override、Family 回退
│   ├── test_sanitizer.py            # 孤儿过滤、空块移除、标签处理
│   ├── test_translator.py           # Anthropic ↔ OpenAI ↔ Gemini 格式转换
│   ├── test_features.py             # 模型特性检测函数
│   ├── test_feature_negotiation.py  # TTL 缓存、mark/query、多类别
│   ├── test_auto_truncate.py        # 截断策略、token 限制学习
│   ├── test_repetition_detector.py  # KMP 重复检测
│   ├── test_rate_limiter.py         # 三模式切换、指数退避
│   ├── test_approval.py             # 审批门控、超时、拒绝
│   ├── test_error_persistence.py    # 错误写入文件
│   ├── test_thinking_pipeline.py    # protection/destack/strip_all/quarantine 单元测试
│   ├── test_header_policy.py        # 请求/响应头黑白名单 + 安全底线
│   └── test_history.py              # 存储 CRUD、reaper 淘汰、统计
│
├── component/                       # 多模块集成测试
│   ├── test_pipeline.py             # 管道执行（含重试、限流）
│   ├── test_history_store.py        # History 完整 CRUD + reaper
│   ├── test_history_api.py          # History REST API 端到端
│   ├── test_history_ws.py           # History WebSocket 消息验证
│   └── test_streaming_resilience.py # keepalive / delayed_commit / buffered_retry（opt-in）集成
│
└── http/                            # HTTP 路由端到端测试
    ├── test_anthropic_routes.py     # Anthropic 消息路由
    ├── test_openai_routes.py        # OpenAI Chat Completions 路由（三重前缀）
    ├── test_responses_routes.py     # Responses API 路由（HTTP + WS）
    ├── test_azure_routes.py         # Azure OpenAI deployment 路由
    ├── test_gemini_routes.py        # Gemini v1beta 路由
    └── test_management_routes.py    # 管理路由（health、config、token、usage、metrics）
```

## 相关文档

- [设计文档总纲](DESIGN.md)（含完整路由表）
- [配置系统](config-system.md)
- [多协议兼容](multi-protocol.md)
- [Thinking 处理管道](thinking-pipeline.md)
- [请求/响应头转发安全](header-forwarding.md)
- [流式韧性](streaming-resilience.md)
- [历史与审计系统](history-system.md)
- [ROADMAP.md](ROADMAP.md) / [BACKLOG.md](BACKLOG.md)
