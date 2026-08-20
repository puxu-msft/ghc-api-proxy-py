# 设计文档

## 项目概述

`ghc-api-proxy-py` 是一个 Python 反向代理，暴露标准 OpenAI、Anthropic、以及（可选）Azure OpenAI / Google Gemini 兼容端点，默认上游为 GitHub Copilot API，同时支持任意兼容服务。

本项目**借鉴** `copilot-api-js`（下称"上游参考项目"）在长期运营中踩坑得到的大量洞见，但**不是它的移植**。上游参考项目在快速迭代中积累了严重的性能负担与过度工程，本项目的核心立场是：**吸收它解决的真实问题与设计思想，用 Python 重新设计出更精简、更高性能、更可维护的方案。**

### 文档约定：稳定性与借鉴状态标注

本设计文档体系描述的是**目标设计**（design spec），不代表当前实现状态（实现状态以代码为准）。每个特性/子系统标注两个维度：

**上游成熟度**（该能力在上游参考项目中的状态）：

- `[上游稳定]` — 上游已稳定、默认启用、有明确契约
- `[上游实验]` — 上游标注为实验性/门控/未验证（如 `enveloped_ping`"预期会超时"、块级缓冲重试"门控在用户 PoC"）
- `[上游未落地]` — 上游仅有设计、未实现（如优雅重启"设计（未实现）"）

**本项目取舍**（我们对该能力的设计决策）：

- `[采纳]` — 直接采纳其思想并在 Python 中实现
- `[重构]` — 采纳其解决的问题，但重新设计实现（通常出于性能/可维护性）
- `[简化]` — 采纳核心、砍掉上游的过度工程分支
- `[缓存/延后]` — 记录价值、暂不实现，列入 [ROADMAP](ROADMAP.md) 或 [BACKLOG](BACKLOG.md)
- `[拒绝]` — 明确不复刻（通常是上游的性能反模式），并说明原因

## 性能设计原则（第一优先级）

**上游参考项目的性能表现很差，本项目绝不原样复刻。** 以下是从上游识别出的**性能反模式**及本项目的对策。这些原则优先于"功能对齐"。

| # | 上游反模式 | 性能问题 | 本项目对策 |
|---|-----------|---------|-----------|
| P1 | **同步 SQLite 落在请求路径** | `bun:sqlite` 同步调用阻塞事件循环，历史写入拖慢每个请求 | 历史/遥测/隔离等所有 SQLite I/O **一律 off-event-loop**：专用 writer 任务 + `asyncio.Queue`，或线程池 executor。请求完成**不阻塞**在落盘上（fire-and-forget） `[重构]` |
| P2 | **热路径高强度压缩** | tier-2 用 zstd **L19 + 16MB 窗口**做列式封存，CPU 开销巨大 | 热路径只用 zstd **level 3**，且在线程池执行；L19 级归档若保留则**仅后台、可关闭、非默认** `[简化]` |
| P3 | **三层降温归档（HOT→tier1→tier2）** | 列式转置 + per-session 封存 + 迁移 verify + 孤儿 GC + 增量 vacuum，大量后台开销与代码复杂度 | 默认单层 SQLite + 简单行数上限清理；分层归档整体列入 [BACKLOG]，仅在明确需要"永不删除"时作为**可选**能力 `[缓存/延后]` |
| P4 | **内容寻址去重搜索索引** | 每条消息内容哈希 + 多表 + 后台 backfill + keyset 续跑，构建成本高 | 默认不建全文索引；查询走 SQL 过滤 + 简单 LIKE。全文/去重搜索列入 [BACKLOG] `[缓存/延后]` |
| P5 | **热路径命中磁盘 sidecar**（thinking L3 quarantine） | 每请求查 SQLite sidecar 判断是否"中毒会话" | 隔离表**常驻内存**（`dict` + 滑动 TTL），可选异步持久化；热路径零磁盘 I/O `[重构]` |
| P6 | **整响应缓冲重试默认开** 的倾向 | 缓冲整个流式响应占用大量内存（大 Write/Edit 可达 16MB/请求） | 缓冲重试**严格 opt-in、默认关**；默认路径为零缓冲直通流 `[采纳]`（默认关） |
| P7 | **每请求重对象图 + 多次投影重算** | client/upstream 双腿模型 + 每 attempt 多 stage + 派生字段重算 | 采用轻量 `dataclass` + 惰性投影；只在需要时构造摘要，不预算所有派生字段 `[简化]` |
| P8 | **全局可变单例 state** | 并发下的隐式共享可变状态 | frozen Pydantic `AppSettings` + FastAPI 依赖注入，不可变语义 `[重构]` |

### 通用性能取向

- **异步优先**：所有 I/O 用 `async/await`；任何同步阻塞调用（SQLite、压缩、文件）下沉到线程池或专用任务。
- **流式零拷贝直通**：SSE 逐事件转发，默认不缓冲完整响应；累积器只做轻量增量记账。
- **连接池复用**：单个 `httpx.AsyncClient` 复用连接（含 HTTP/2）。
- **背压与有界队列**：历史/遥测写入用有界队列，过载时丢弃可丢弃项而非阻塞请求。
- **Pydantic v2 Rust 核心**：高速验证/序列化；热路径避免不必要的模型重建。
- **惰性与可关闭**：重特性（分层归档、全文索引、遥测、缓冲重试）默认关闭或惰性，按需开启。

## 设计目标（相对上游）

| 维度 | 上游参考（TS/Bun/Hono） | 本项目（Python）设计 |
|------|---------|-------------|
| 状态管理 | 全局可变 `state.ts` | frozen `AppSettings` + FastAPI 依赖注入 `[重构]` |
| 数据验证 | 手动 TS 类型 + 运行时检查 | Pydantic v2 自动验证/序列化 `[重构]` |
| 配置管理 | CLI + config.yaml 手动合并 + 大量 compat 迁移 | Pydantic BaseSettings 四层自动合并 `[重构]` |
| 历史存储 | 同步 SQLite + 三层归档 + 内容寻址搜索 | 异步单层 SQLite（off-loop）+ 简单清理，重能力可选 `[简化/重构]` |
| 请求生命周期 | 手动 context + sink 总线 | FastAPI middleware + 依赖注入 + 观察者 `[重构]` |
| 手动审批 | 无 | 完整审批门控（AnyIO Event + cancel scope） `[新增]` |
| 可观测性 | consola + 分层遥测 SQLite + DDSketch | 结构化日志 + OpenTelemetry；重遥测可选 `[简化]` |

## 核心能力

> 标注见"稳定性与借鉴状态标注"。未标注者默认 `[上游稳定][采纳]`。

- **多协议兼容**：OpenAI（Chat Completions / Responses / Embeddings / Models）+ Anthropic（Messages / Count Tokens）+ Azure OpenAI（deployment 经典格式 + v1）`[采纳]` + Google Gemini（`/v1beta`）`[采纳]`
- **Anthropic 直连**：Claude 模型通过 Copilot 原生 Anthropic 端点直连
- **消息清洗**：2 阶段清洗管道（预处理 + 可重复清洗），修复 tool 配对、清理空块、处理 system-reminder
- **Thinking-block 处理管道**：块级保护（`preserve`/`stripped`）+ 去堆叠（destack）+ L2 拒绝后剥离 + L3 会话隔离（内存实现）`[重构，见 P5]`
- **Tokenization**：Anthropic/Gemini 协议专用计数、本地 size-aware calibration、prompt-limit observations；不改写历史
- **Typed Hooks**：Payload / Retry factory / Response / Observer 四类扩展点，启动期冻结 registry，支持可信用户模块
- **模型解析**：别名、版本标准化、修饰符后缀、Family Override、链式解析
- **Feature Negotiation**：多类别学习缓存（body 字段 / beta headers / effort / tool 字段 / cache_control 子字段等），TTL 裁决
- **Cache Control 模式**：`disabled / passthrough / sanitize / proxied`（默认 **passthrough**）`[采纳]`
- **Context Editing**：服务端上下文管理（clear-thinking / clear-tooluse / clear-both）
- **Tool Search**：注入 Copilot `tool_search_tool_regex`，支持 deferred tool loading + per-model 覆盖
- **请求头/响应头转发安全**：blacklist/whitelist 双模式 + security floor + 归属头剥离 `[采纳]`
- **Warmup 策略**：`allow / reject / drop / fake`（默认 allow）`[采纳]`
- **自适应限流**：3 模式（Normal → Rate-Limited → Recovering）
- **流式处理**：SSE 逐事件直通 + WebSocket Transport（Responses）+ 流空闲超时 + 重复性检测（KMP）
- **流式韧性**：延迟提交窗口 + keepalive 心跳（应对客户端 idle watchdog）`[采纳]`；整响应缓冲重试 `[上游实验][采纳]（默认关，见 P6）`
- **Token Provider 系统**：CLI / env / file / device-auth 四源优先级链
- **手动审批**：可选请求审批门控 `[新增]`
- **请求历史**：异步 SQLite 持久化 + REST + WebSocket 推送；分层归档/全文搜索 `[缓存/延后，见 P3/P4]`
- **可观测性**：结构化日志 + OpenTelemetry + TUI；分层遥测 `[简化，见可选]`
- **优雅关闭**：4 阶段（Setup → Graceful Wait → Abort → Force Close）+ 信号升级 `[采纳]`；优雅重启 `[上游未落地][缓存/延后]`

## 架构

### 入口点

- `main.py` — CLI 入口（Typer），子命令：`start`、`auth`/`login`、`logout`、`debug`（`info`/`models`/`usage`）、`setup-claude-code`、`setup-codex`、`list-claude-code`
- `server.py` — FastAPI 应用工厂 + lifespan（分阶段启动）
- `deps.py` — FastAPI 依赖注入提供者

### 请求流程

1. 请求进入 FastAPI 路由（`routes/`），按协议前缀分发（OpenAI / Anthropic / Azure / Gemini）
2. 模型解析 + 端点决策
3. Pipeline 处理：payload hooks → mandatory 清洗 → 审批（可选）→ 限流 → per-attempt hooks → 执行 → 重试
4. Anthropic 请求经 mandatory tool-pair repair 与 built-in hooks后完成canonical语义处理；route确定后仅direct Messages leg执行tool defer-loading／tool-search wire preparation，Responses leg转为普通function tools
5. 流式响应逐事件直通（含 keepalive / idle timeout / 重复检测），累积器旁路记账
6. 请求终态异步落历史（off-loop），WebSocket 推送

### 核心模块

> 模块树体现"借鉴思想、Python 重设计"。重特性（分层归档、全文搜索、分层遥测）默认为可选实现，未列入默认骨架。

```
src/app/
├── __init__.py                      # 包初始化、版本号
├── cli.py                           # CLI 入口（Typer），多子命令
├── server.py                        # FastAPI 应用工厂 + 分阶段 lifespan
├── deps.py                          # FastAPI 依赖注入提供者
├── errors.py                        # 错误分类、格式化错误响应、wire format 检测
├── shutdown.py                      # 4 阶段优雅关闭 + 信号升级
├── repetition_detector.py           # KMP 流式重复性检测
│
├── config/
│   ├── settings.py                  # Pydantic BaseSettings（全部配置，frozen）
│   ├── loader.py                    # YAML + env + CLI 四层合并
│   ├── compat.py                    # 弃用键迁移（warn-and-continue）
│   └── paths.py                     # 跨平台配置/数据目录（XDG 支持）
│
├── models/
│   ├── openai.py                    # OpenAI Chat Completions + Responses 模型
│   ├── anthropic.py                 # Anthropic Messages 模型
│   ├── gemini.py                    # Gemini generateContent 模型
│   ├── common.py                    # Usage、ModelInfo、ErrorResponse
│   └── capabilities.py              # 模型能力元数据
│
├── auth/
│   ├── providers.py                 # Token provider 链（CLI/env/file/device-auth，优先级）
│   ├── github.py                    # GitHub token 管理
│   ├── copilot.py                   # Copilot token 交换与自动刷新
│   └── device_flow.py              # GitHub OAuth 设备授权流程
│
├── upstream/
│   ├── base.py                      # UpstreamTarget 协议
│   ├── copilot.py                   # Copilot 上游（动态请求头、intent、model headers）
│   ├── generic.py                   # 通用 OpenAI/Anthropic 上游
│   ├── client.py                    # httpx.AsyncClient 封装（连接池/超时/代理/HTTP2）
│   └── models_api.py               # 模型列表获取、缓存、定期刷新、两种输出格式
│
├── pipeline/
│   ├── context.py                   # RequestContext 生命周期状态机
│   ├── manager.py                   # RequestContextManager（活跃跟踪 + reaper + deadline）
│   ├── executor.py                  # 请求执行管道核心循环
│   ├── rate_limiter.py              # 自适应三模式限流器
│   ├── approval.py                  # 手动审批门控
│   └── strategies/                  # RetryCoordinator + poisoned-thinking strategy
│
├── anthropic/
│   ├── client.py                    # Anthropic 客户端（直连 Copilot）
│   ├── request_preparation.py       # 请求准备编排（wire/headers/cache/thinking/negotiation）
│   ├── sanitize/                    # 2 阶段清洗（见 sanitize-pipeline.md）
│   ├── thinking/                    # Thinking 管道：protection / destack / strip-all /
│   │                                #   quarantine（内存 sidecar）/ signature-compat
│   ├── header_policy/               # 请求/响应头转发（blacklist/whitelist + floor）
│   ├── feature_negotiation.py       # 多类别学习缓存 + TTL 裁决
│   ├── features.py                  # 模型特性检测 + anthropic-beta + context management
│   ├── message_tools.py             # 普通 client tool defer + tool_search 声明注入
│   └── warmup.py                    # Warmup 请求策略
│
├── openai/
│   ├── client.py                    # Chat Completions 客户端
│   ├── responses_client.py          # Responses 客户端
│   ├── responses_conversion.py      # Responses 数据转换 + call_id 标准化
│   ├── embeddings.py                # Embeddings 客户端
│   ├── sanitize.py                  # OpenAI 消息清洗 + orphan filter
│   └── *_stream_accumulator.py      # Chat/Responses SSE 累积器
│
├── protocols/                       # 协议适配层
│   ├── azure.py                     # Azure OpenAI（deployment 经典 + v1）适配
│   └── gemini.py                    # Gemini /v1beta 适配
│
├── transform/
│   ├── model_resolver.py            # 模型解析（别名/标准化/Override/Family）
│   ├── translator.py               # 跨协议格式翻译
│   └── system_prompt.py            # 系统提示词定制
│
├── streaming/
│   ├── sse.py                       # SSE StreamingResponse 工具
│   ├── idle_timeout.py             # 流空闲超时
│   ├── keepalive.py                # keepalive 心跳（empty_text anchor / ping）
│   ├── delayed_commit.py           # 延迟提交窗口
│   ├── buffered_retry.py           # 缓冲重试（opt-in，默认关）
│   └── translator.py              # 跨格式流式翻译
│
├── tokenization/
│   ├── estimators.py                # Anthropic/Gemini 协议专用本地估算
│   ├── calibration.py               # protocol+model size-aware factor model
│   ├── limits.py                    # Prompt-limit 解析与 observation registry
│   ├── state_store.py               # Versioned/off-loop/atomic persistence
│   └── service.py                   # Anthropic upstream-first count service
│
├── hooks/
│   ├── types.py / context.py        # 四类 Protocol + frozen HookContext
│   ├── registry.py / loader.py      # Builder、immutable registry、可信 modules
│   ├── executor.py                  # 顺序、timeout、隔离、telemetry
│   └── builtin/                     # Payload/retry/calibration built-ins
│
├── routes/
│   ├── openai.py                    # chat/completions, models, embeddings（三重前缀）
│   ├── responses.py                # responses（HTTP + WebSocket）
│   ├── anthropic.py                # messages, count_tokens
│   ├── azure.py                     # /openai/deployments/*
│   ├── gemini.py                    # /v1beta/models/*
│   ├── management.py               # /api/status, /api/config, /api/tokens, /api/negotiation ...
│   ├── health.py                    # /health, /health/liveness, /health/readiness
│   ├── metrics.py                  # /metrics（Prometheus）
│   ├── history.py                  # /history/api/*, /history/ws
│   └── approval.py                # /api/approval/*
│
├── history/
│   ├── store.py                     # 异步历史存储门面（off-loop 写入）
│   ├── sqlite/                      # 异步 SQLite 后端（writer 任务 + 队列）
│   ├── in_flight.py                # 进行中请求内存映射（WebSocket 实时视图）
│   ├── sessions.py                 # Session 识别（HTTP header / previous_response_id）
│   ├── ws.py                        # WebSocket 连接管理与广播
│   └── types.py                    # HistoryEntry / EntrySummary / SessionSummary
│
└── observability/
    ├── logging.py                  # 结构化日志（JSON/text）+ 固定宽度前缀
    ├── tracing.py                  # OpenTelemetry
    ├── middleware.py               # 请求日志/追踪中间件
    ├── telemetry.py                # 请求遥测（model/tokens/reasoning/duration）
    └── tui.py                       # 终端 UI（可选）
```

### 路由

> `[采纳]` 全量协议表面。OpenAI 端点三重前缀注册（无前缀 / `/v1` / `/openai/v1`）。

#### OpenAI 兼容

| 路由 | 说明 |
|------|------|
| `/chat/completions`、`/v1/…`、`/openai/v1/…` | Chat Completions |
| `/responses`、`/v1/…`、`/openai/v1/…` | Responses API（HTTP POST + WebSocket GET） |
| `/embeddings`、`/v1/…`、`/openai/v1/…` | Embeddings |
| `/models`、`/v1/…`、`/openai/v1/…` | 模型列表（OpenAI 标准格式：id/object/created/owned_by） |
| `/models/:model`、`/v1/…` | 单个模型 |

#### Azure OpenAI 兼容 `[采纳]`

| 路由 | 说明 |
|------|------|
| `/openai/deployments/:deployment/chat/completions` | 经典格式，model 从 URL path 注入，`api-version` query 被忽略 |
| `/openai/deployments/:deployment/embeddings` | 同上 |
| `/openai/deployments/:deployment/responses` | 同上 |

#### Anthropic 兼容

| 路由 | 说明 |
|------|------|
| `/v1/messages`、`/anthropic/v1/messages` | Messages API |
| `/v1/messages/count_tokens`、`/anthropic/…` | Token 计数 |
| `/anthropic/v1/models` | Anthropic 格式模型列表 |

#### Google Gemini 兼容 `[采纳]`

| 路由 | 说明 |
|------|------|
| `/v1beta/models/:model:generateContent` | 非流式 |
| `/v1beta/models/:model:streamGenerateContent` | 流式 |
| `/v1beta/models/:model:countTokens` | Token 计数 |

#### 管理 API

| 路由 | 说明 |
|------|------|
| `GET /api/status` | 聚合状态（uptime、auth、quota、activeRequests、rateLimiter、shutdown phase、models …） |
| `GET /api/config`、`GET/PUT /api/config/yaml` | 配置查看与热重载编辑 |
| `GET /api/tokens` | Token 信息 |
| `GET /api/models`、`/:model` | 内部格式模型（完整 Copilot 数据） |
| `GET /api/logs` | 请求历史摘要 |
| `GET/POST /api/negotiation/*` | Feature negotiation 学习记录管理 |
| `POST /api/event_logging/batch` | Anthropic 事件日志（静默消费） |
| `/api/approval/*` | 手动审批 API `[新增]` |

#### 基础设施

| 路由 | 说明 |
|------|------|
| `GET /health`、`/health/readiness` | 就绪检查（200/503，token+models） |
| `GET /health/liveness` | 存活检查（恒 200，先于 token 中间件与关闭门） |
| `GET /metrics` | Prometheus 文本 `[采纳]` |
| `GET /`、`/openapi.json`、`/docs` | OpenAPI + Scalar UI |
| `/history/api/*`、`/history/ws` | History REST + WebSocket |

## 运行时选项

所有运行时状态通过 frozen Pydantic `AppSettings` 管理，四层合并（默认值 < YAML < 环境变量 < CLI）。**完整配置清单见 [config-system.md](config-system.md)**（这是配置的唯一权威来源，按 section 详列每个键、默认值、说明、稳定性标注）。此处仅给分类概览。

**Python 优化**：上游用全局可变 `state.ts` + 大量 compat 迁移；本项目用 frozen `AppSettings` + 依赖注入，热重载产生新实例，不可变语义避免并发问题（见 P8）。

| 配置 section | 覆盖内容 |
|-------------|---------|
| 服务器 | host / port / debug |
| `upstream` | 类型、base_url、连接池、超时、HTTP2、代理 |
| `auth` / `headers` | GitHub token、账户类型、VSCode 伪装头 |
| `model_overrides` / `model_mappings` | 模型名映射与别名 |
| `anthropic` | count-token 上游开关、thinking、header 转发、warmup、普通 client tool preprocessing |
| `openai_responses` | call_id 标准化、上游 WS、WS 连接上限 |
| `hooks` | 用户 modules、disabled names、timeout、可选 tool-call 内容去重 |
| `tokenization` | 状态文件路径、周期 flush 间隔 |
| `rate_limiter` | 退避、恢复、连续成功 |
| `approval` | 手动审批开关、超时 `[新增]` |
| `timeouts` | stream idle/response header/upstream/stale request/deadline |
| `history` | enabled、success/failure 上限、reaper、db_path、WebSocket |
| `observability` | 日志级别/格式、OpenTelemetry、TUI |

### 关键更正（相对本项目旧文档）

以下几处旧文档写错或已随上游演进，config-system.md 采用更正后的定义：

- `auto_cache_control`(bool) → **`cache_control`** 四值模式（默认 `passthrough`）
- `immutable_thinking`(bool) → **`thinking_block_message_policy`**（`preserve`/`stripped`，默认 `preserve`）
- `anthropicApiKey`（**从不存在**）→ **`use_upstream_count_tokens`**（转发 GHC 上游计数）
- History `limit=200` + `min_entries` → **`success_limit=50` / `failure_limit=200`**（分桶），无内存压力管理
- 3 阶段关闭 → **4 阶段** + 信号升级
- 单会话 → **按 HTTP header 识别**（`x-claude-code-session-id` 领先）
- CLI `check-usage` → **`debug usage`**

## 模块文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [project-structure.md](project-structure.md) | 目录结构、模块依赖、分阶段生命周期、测试结构 | 更新 |
| [authentication.md](authentication.md) | Token provider 链、账户类型、Copilot token 管理 | 更新 |
| [config-system.md](config-system.md) | **完整配置清单**（权威）、四层合并、热重载、弃用迁移 | 更新 |
| [data-models.md](data-models.md) | Pydantic 模型（各协议 + 内部 client/upstream 双腿） | 更新 |
| [model-resolution.md](model-resolution.md) | 模型解析、别名、Override、两种输出格式 | 更新 |
| [multi-protocol.md](multi-protocol.md) | Azure / Gemini 适配、三重前缀、模型格式 | **新增** |
| [sanitize-pipeline.md](sanitize-pipeline.md) | 2 阶段消息清洗、Tool blocks 处理 | 更新 |
| [thinking-pipeline.md](thinking-pipeline.md) | Thinking 块保护 / destack / L2 剥离 / L3 内存隔离 | **新增** |
| [tool-use.md](tool-use.md) | Client Tool Use、pair repair、tool_search 边界 | 更新 |
| [hooks-system.md](hooks-system.md) | Typed Hooks 契约、注册、错误语义与 built-ins | **新增** |
| [tokenization.md](tokenization.md) | 协议计数、校准、prompt limits 与持久化 | **新增** |
| [anthropic-compat.md](anthropic-compat.md) | 兼容性、feature 检测、cache 模式、context editing、warmup | 更新 |
| [header-forwarding.md](header-forwarding.md) | 请求/响应头转发安全（blacklist/whitelist + floor） | **新增** |
| [feature-negotiation.md](feature-negotiation.md) | 多类别学习缓存、TTL 裁决、管理 API | **新增** |
| [request-pipeline.md](request-pipeline.md) | 重试管道、错误分类、限流、审批集成 | 更新 |
| [streaming.md](streaming.md) | SSE 直通、WebSocket Transport、idle timeout、重复检测 | 更新 |
| [streaming-resilience.md](streaming-resilience.md) | 延迟提交、keepalive 心跳、缓冲重试（性能取舍） | **新增** |
| [history-system.md](history-system.md) | 异步 SQLite 存储（off-loop）、session、REST、WS（含性能重设计） | 更新 |
| [telemetry-observability.md](telemetry-observability.md) | 日志、OpenTelemetry、请求遥测、TUI（可选） | **新增** |
| [approval-system.md](approval-system.md) | 手动审批门控、AnyIO Event/cancel scope、WebSocket 通知 | `[新增]` |
| [shutdown.md](shutdown.md) | 4 阶段关闭、请求上下文、reaper、deadline、错误持久化 | 更新 |
| [ROADMAP.md](ROADMAP.md) | 借鉴但暂缓的能力、里程碑 | **新增** |
| [BACKLOG.md](BACKLOG.md) | 上游重能力的可选实现（分层归档、全文搜索、分层遥测等） | **新增** |

## UI 设计原则

### Console 日志

- **固定宽度 ASCII 前缀**对齐（`[....]`、`[<-->]`、`[DRIN]`、`[ OK ]`、`[FAIL]`、`[RETRY]`）
    - `[DRIN]` 由用户裁决于 2026-08-20 加入：监听器停止接受新请求、但已有请求仍在处理时，live footer 用它替代 `[<-->]`。这是一个与「运行中」和「已停止」都不同的状态，且是操作者最需要被告知的一个——进程仍然忙碌，但队列只会缩短。两者同为六列，切换时行不会横向跳动。
    - 注：`[RETRY]` 是七列，早于本次即如此，「固定宽度」在它身上不成立。
- **格式**：`[PREFIX] HH:MM:SS METHOD /path ...`
- **只显示相关信息**：非模型请求不显示模型名/token
- **流式指示器**：长时间请求显示 `streaming...`

### 通用原则

- **减少噪音**、**一致格式**、**信息丰富的日志**（含模块标签、模型名、具体值）
