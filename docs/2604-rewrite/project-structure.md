# 项目结构

本文只描述当前实现，不列尚未存在的目标文件。

```text
src/app/
├── cli.py / server.py / deps.py / runtime.py
├── config/                 # frozen Pydantic settings、四层加载、paths、compat
├── models/                 # Anthropic/OpenAI/Gemini/common/capabilities wire models
├── auth/                   # token providers、device flow、Copilot token refresh
├── upstream/               # transports、SDK clients、model catalog、bootstrap
├── pipeline/               # RequestContext、executor、approval、rate limiter、strategies
├── anthropic/              # client、mandatory sanitizer、thinking、headers、tools、warmup
├── openai/                 # Chat/Responses/Embeddings clients 与转换/累积
├── protocols/              # Azure 与 Gemini adapters
├── streaming/              # SSE、WS、idle、keepalive、usage tap、resilience helpers
├── tokenization/           # 协议估算、校准、prompt-limit observations、state store/service
├── hooks/                  # typed contracts、builder/registry、loader、executor、built-ins
├── history/                # off-loop SQLite、in-flight、session、WebSocket
├── observability/          # logging、metrics、tracing、TUI reducer
├── routes/                 # protocol、management、history、approval、health、metrics routes
└── transform/              # model resolver、system prompt、cross-protocol translator
```

## 关键模块

### `tokenization/`

- `estimators.py`：共享 tokenizer 生命周期；提供 Anthropic 与 Gemini 协议专用估算入口。
- `calibration.py`：按 `(protocol, normalized_model)` 分桶学习本地 estimate → real token factor。
- `limits.py`：解析 prompt-limit 错误，独立记录 advertised 与 observed facts。
- `state_store.py`：应用生命周期状态实例，periodic/final flush，off-loop serialized atomic replace。
- `service.py`：Anthropic `/count_tokens` 上游优先、本地 calibrated fallback。

### `hooks/`

- `types.py`：Payload、Retry factory、Response、Observer 四类 Protocol。
- `context.py`：frozen request snapshot。
- `registry.py`：启动期可变 builder 与请求期不可变 registry。
- `loader.py`：显式可信 Python module 加载。
- `executor.py`：顺序、timeout、错误隔离与 telemetry。
- `builtin/`：Read 标签、thinking destack、tool preprocessing、可选内容去重、poisoned-thinking retry、token calibration observers。

### `anthropic/sanitize/`

Mandatory protocol sanitizer 使用局部相邻算法修复 client `tool_use`/`tool_result`，不属于可禁用 hook。详情见 [sanitize-pipeline.md](sanitize-pipeline.md)。

## 生命周期装配

`server._lifespan()` 的顺序：

1. 日志、tokenization state load 与 periodic flush task。
2. History/WebSocket、approval。
3. 可用时初始化 upstream services 与 protocol clients。
4. 注册 built-in hooks，加载用户 modules，冻结 registry，注入 Anthropic client。
5. 启动 token/model/history 后台任务。
6. Shutdown 时拒绝审批、最终 flush tokenization、关闭 history/upstream，再取消 task group。

## 依赖约束

- `models/` 与基础 errors 是叶子。
- `tokenization/` 可依赖 wire models、wire JSON、model normalization，但不依赖 routes。
- `hooks/types` 不依赖具体 built-in；built-ins 可以复用 Anthropic/tokenization 服务。
- Mandatory sanitizer 不依赖 Hook registry。
- `RuntimeState` 是每个 FastAPI app 的唯一运行时容器，不使用跨 app 的进程全局可变单例。
- History lifecycle 保持 guaranteed-delivery 一等公民，不降级为可失败 observer。

## 测试结构

- `tests/unit/`：纯算法、配置、registry/loader/executor、built-ins、tokenization。
- `tests/component/`：pipeline 与存储组件。
- `tests/integration/`：bootstrap、server 和 Hooks pipeline。
- `tests/http/`：各协议与管理 API。
- `verification/`：独立黑盒验收脚本和报告。

## 相关文档

- [设计总览](DESIGN.md)
- [Hooks 机制](hooks-system.md)
- [Tokenization](tokenization.md)
- [请求管道](request-pipeline.md)
