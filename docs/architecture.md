# 整体架构概览

## 项目背景

`ghc-api-proxy-py` 是一个 Python 异步 API 代理服务，接收标准的 OpenAI 和 Anthropic 格式请求，经过可配置的转换处理后，转发到可配置的上游目标。默认上游为 GitHub Copilot 后端，同时支持任意 OpenAI/Anthropic 兼容端点。

### 核心目标

- **充分的定制修改能力**：系统提示词注入、消息清洗、格式翻译、模型名称映射
- **审查与历史查看**：所有请求/响应的完整记录、查询、导出
- **手动审批控制**：可选的请求审批门控，支持查看、批准、拒绝、修改后放行
- **高性能**：全链路异步、流式直通、连接池复用

### 使用场景

- 将 GitHub Copilot 作为后端，为 Claude Code、Cursor 等工具提供标准 API 接口
- 在请求链路中注入自定义系统提示词、过滤敏感内容
- 审计所有 AI 请求的内容和响应
- 在关键场景下人工审批 AI 请求

## 技术栈

| 组件 | 技术选型 | 选型理由 |
|------|----------|----------|
| 语言 | Python 3.14 | 类型提示完善、异步生态成熟 |
| Web 框架 | FastAPI | 原生异步、Pydantic 集成、依赖注入、自动 OpenAPI 文档 |
| ASGI 服务器 | uvicorn | 高性能、支持 HTTP/1.1 和 WebSocket |
| HTTP 客户端 | httpx | 异步、连接池、流式响应、HTTP/2 支持 |
| 数据验证 | Pydantic v2 | Rust 核心高速验证、自动序列化、Settings 支持 |
| 可观测性 | OpenTelemetry | 标准化链路追踪、与 FastAPI/httpx 自动集成 |
| 配置 | PyYAML | YAML 配置文件解析 |

## 高层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端 (Claude Code / Cursor / ...)       │
└───────────┬───────────────────┬────────────────────┬────────────┘
            │ OpenAI Chat       │ Anthropic          │ OpenAI Responses
            │ Completions 格式  │ Messages 格式      │ 格式
            ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI 路由层 (routes/)                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────┐ │
│  │ /v1/chat/    │ │ /v1/messages │ │ /v1/responses│ │/v1/    │ │
│  │ completions  │ │              │ │              │ │models  │ │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┘ │
│         │                │                │                     │
│  ┌──────┴────────────────┴────────────────┴──────┐             │
│  │           转换层 (transform/)                   │             │
│  │  模型解析 │ 系统提示词 │ 消息清洗 │ 格式翻译     │             │
│  │  Chat ↔ Anthropic ↔ Responses 三向翻译         │             │
│  └────────────────────┬──────────────────────────┘             │
│                       │                                        │
│  ┌────────────────────┴───────────────────┐                    │
│  │         执行管道 (pipeline/)             │                    │
│  │  清洗 → 审批 → 限流 → 执行 → 重试         │                    │
│  └────────────────────┬───────────────────┘                    │
│                       │                                        │
│  ┌────────────────────┴───────────────────┐                    │
│  │         上游目标 (upstream/)             │                    │
│  │  ┌─────────────┐  ┌────────────────┐   │                    │
│  │  │ Copilot     │  │ Generic        │   │                    │
│  │  │ (默认)      │  │ (可配置)       │   │                    │
│  │  └──────┬──────┘  └───────┬────────┘   │                    │
│  └─────────┼─────────────────┼────────────┘                    │
└────────────┼─────────────────┼─────────────────────────────────┘
             │                 │
             ▼                 ▼
┌────────────────────┐ ┌─────────────────────┐
│ GitHub Copilot API │ │ 任意 OpenAI/Anthropic│
│                    │ │ 兼容服务             │
└────────────────────┘ └─────────────────────┘

         ┌──────────────────────────────────┐
         │        辅助系统                    │
         │  ┌────────┐ ┌────────┐ ┌───────┐ │
         │  │ 历史   │ │ 审批   │ │ 可观  │ │
         │  │ 存储   │ │ 门控   │ │ 测性  │ │
         │  └────────┘ └────────┘ └───────┘ │
         │                                  │
         │  管理 API: /api/history/*        │
         │            /api/approval/*       │
         │            /health               │
         └──────────────────────────────────┘
```

## 模块划分

| 模块 | 包路径 | 职责 |
|------|--------|------|
| **配置** | `app.config` | 三层配置合并（yaml/env/cli）、Pydantic Settings |
| **数据模型** | `app.models` | OpenAI/Anthropic/通用 Pydantic 模型 |
| **认证** | `app.auth` | GitHub token 管理、Copilot token 交换与刷新 |
| **上游** | `app.upstream` | 上游目标协议、Copilot/通用实现、httpx 客户端 |
| **管道** | `app.pipeline` | 请求生命周期、执行循环、限流、审批、重试策略 |
| **转换** | `app.transform` | 模型解析、格式翻译、消息清洗、提示词定制 |
| **流式** | `app.streaming` | SSE 响应、流式累积、跨格式翻译 |
| **路由** | `app.routes` | FastAPI 路由处理器 |
| **历史** | `app.history` | 内存存储、查询、WebSocket 推送 |
| **可观测性** | `app.observability` | 结构化日志、OpenTelemetry 链路追踪 |

## 关键数据流

### 请求处理全路径

```
客户端发送请求（Chat Completions / Messages / Responses 格式）
    │
    ▼
[FastAPI 中间件] 日志、链路追踪、请求ID 分配
    │
    ▼
[路由层] Pydantic 模型验证、解析请求体
    │
    ▼
[模型解析] 名称标准化（"opus" → "claude-opus-4.6"）
    │
    ▼
[系统提示词] 应用 prepend/append/override 规则
    │           ├─ Chat Completions: 修改 messages 中的 system 消息
    │           ├─ Anthropic: 修改 system 字段
    │           └─ Responses: 修改 instructions 字段
    ▼
[路由决策] 根据模型和端点支持情况选择：
    │   ├─ 直接转发（格式匹配）
    │   ├─ Chat ↔ Anthropic 翻译
    │   ├─ Chat ↔ Responses 翻译
    │   └─ Responses ↔ Anthropic 翻译
    ▼
[消息清洗] 移除孤立块、空块、system-reminder 标签
    │
    ▼
[手动审批] 若启用：挂起请求，等待 API 审批（asyncio.Event）
    │
    ▼
[自适应限流] 检查限流状态，必要时排队等待
    │
    ▼
[发送到上游] httpx.AsyncClient 发送请求
    │   ├─ /chat/completions（Chat Completions 端点）
    │   ├─ /v1/messages（Anthropic 端点）
    │   └─ /responses（Responses 端点）
    │
    ├─ 成功 ──────────────────────┐
    │                             │
    ├─ 429 → 进入限流模式，退避重试 │
    ├─ 413 → auto_truncate 截断重试│
    ├─ 400 → orphan_cleanup 重试   │
    └─ 5xx → 分类记录错误          │
                                  │
                                  ▼
                         [响应处理]
                         ├─ 流式：逐块 yield SSE
                         │   ├─ 三种 SSE 格式对应三种端点
                         │   ├─ 跨格式翻译（如需要）
                         │   └─ tee 到累积器用于历史记录
                         └─ 非流式：返回 JSON（格式翻译如需要）
                                  │
                                  ▼
                         [历史记录] 异步写入 HistoryStore
                                  │
                                  ▼
                         [WebSocket 广播] 通知连接的客户端
```

## 设计原则

### 1. Async-First（异步优先）

所有 I/O 操作使用 `async/await`。HTTP 请求用 `httpx.AsyncClient`，共享状态保护用 `asyncio.Lock`，等待审批用 `asyncio.Event`。不引入线程同步原语。

### 2. 模块化

每个子系统是独立的 Python 包，通过明确定义的接口（Protocol）交互。上游目标通过 `UpstreamTarget` 协议抽象，重试通过 `RetryStrategy` 协议抽象。新增上游类型或重试策略不需要修改核心管道代码。

### 3. 类型安全

所有外部数据（请求、响应、配置）通过 Pydantic 模型验证。内部数据结构使用 dataclass 或 TypedDict。函数签名使用完整的类型注解。

### 4. 可测试

通过 FastAPI 依赖注入，所有外部依赖（上游客户端、历史存储、限流器）可在测试中替换为 mock。核心转换逻辑（翻译、清洗、模型解析）是纯函数，可直接单元测试。

### 5. 高性能

- 流式响应立即 yield，不缓冲完整响应
- 单个 httpx 客户端复用连接池
- 审批和限流使用 `asyncio.Event`，零 CPU 开销等待
- Pydantic v2 的 Rust 核心提供高速序列化/验证

## 相关文档

- [目录结构与模块职责](project-structure.md)
- [API 端点规格](api-endpoints.md)
- [上游目标系统](upstream-targets.md)
- [请求执行管道](request-pipeline.md)
- [转换系统](transform-system.md)
- [流式处理](streaming.md)
- [手动审批系统](approval-system.md)
- [历史与审计](history-system.md)
- [配置系统](config-system.md)
- [核心数据模型](data-models.md)
