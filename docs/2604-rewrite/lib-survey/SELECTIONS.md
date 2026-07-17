# 2604 Rewrite 成熟库选型总表

> 状态：**已定稿**。用户于 2026-07-15 完成第 4 节 D1～D6 裁决，可进入实施 planning。依据为 [domain1](domain1-llm-sdk.md)、[domain2](domain2-reliability.md)、[domain3](domain3-streaming-sse-ws.md)、[domain4](domain4-storage-config.md)、[domain5](domain5-observability.md)、[domain6](domain6-hot-path-foundations.md) 与 [SDK passthrough PoC](../../../exp/upstream-sdk-passthrough/CONCLUSION.md)。

## 1. 直接采用

| 模块 | 库 / 原语 | 决策边界 |
|---|---|---|
| 上游 Anthropic、Chat Completions、Responses HTTP | 官方 `anthropic` / `openai` SDK 底层 `post(..., cast_to=httpx.Response, stream=True)` | 只借请求构造、认证与 transport；`max_retries=0`；同协议原始 bytes 直通，跨协议仍进自研 translator；Anthropic SDK 会额外注入 `x-stainless-timeout`，出站 header 审计不得误判为客户端注入 |
| 上游 Responses WebSocket | `httpx_ws` | 复用 `httpx.AsyncClient` 的代理/TLS/transport 配置；实施前完成真实逐消息、背压、取消、代理/TLS 的 Python 3.14 black-box PoC；若出现阻塞性缺陷则退回域3记录的 `websockets` 逃生舱 |
| wire JSON 编解码 | `orjson` | 只进入 HTTP/SSE 热路径，集中在内部 codec；Pydantic 模型不迁移到 msgspec；低频可读 JSON 继续标准库 |
| 本地 token 估算 | `tiktoken` `o200k_base` | startup 预载，离线镜像预热 cache；长文本 CPU offload；只称“估算”，精确值默认走上游 count endpoint |
| XDG 路径 | `platformdirs` | 替换手写 OS 分支 |
| 结构化日志 | `structlog` | contextvars、JSON/text renderer 和 stdlib logging bridge；固定前缀仍为自定义 processor |
| TUI | `textual` | 接管终端渲染、布局和按键；保留纯 reducer 与业务 state |
| CLI | `typer` | 直接从目标实现起采用，不先写 argparse 再迁移，避免重复工作 |
| 配置模型与 source | `pydantic-settings` | 继续作为唯一类型/校验系统；优先使用内置 YAML/CLI source，但 per-key vs replace 合并保持自定义 source |
| YAML | PyYAML `safe_load` | 当前无 round-trip 保注释写回需求 |
| 错误文件 I/O | `aiofiles` | 错误快照低频 off-loop 异步写入 |

## 2. 条件采用

| 模块 | 库 | 条件与退路 |
|---|---|---|
| 自动 HTTP tracing | OTel FastAPI/HTTPX instrumentation | 官方 contrib 仍标 beta。若用户接受，整套 core/contrib 原子升级并锁兼容批次；若不接受，保留 OTel API/SDK 和少量手写业务 span |
| Metrics 与 Prometheus | OTel Metrics + `PrometheusMetricReader` | 若采用 OTel SDK，则作为唯一指标数据源，并在 FastAPI `/metrics` 用 `generate_latest(REGISTRY)`；若不采用 OTel Metrics，才退回纯 `prometheus_client`，不可双写 |
| OTLP exporter | OTel OTLP exporter | 只有配置 OTLP endpoint 才安装/启用；先验证 Python 3.14 的 grpc wheel，或选 HTTP/protobuf exporter 降低 gRPC 依赖面 |
| 并发超时/取消 | AnyIO | 建议作为结构化 task group/cancel scope 层，但不强求把所有 `asyncio.Event`/`Lock` 机械改写；详见待拍板项 |
| 出站 SSE response wrapper | `sse-starlette` | 保真 PoC 通过后采用 `EventSourceResponse` 与断连检测；事件格式化和协议 keepalive 仍由业务 generator 控制。若 PoC 发现非常规帧被隐式规范化，则退回 Starlette `StreamingResponse` |
| 事件循环实现 | `uvloop` | Linux/macOS 部署做真实代理 benchmark 后决定是否默认启用；Python 3.14 wheel 与最小运行已验证。Windows 保持 asyncio，依赖应做 platform marker 或 deployment extra |

## 3. 明确保留自研

| 模块 | 保留理由 | 可借原语 |
|---|---|---|
| 跨协议 request/response/SSE translator | 现成库都是调用框架，无法只借纯转换；未知字段、thinking signature 和 server tool 保真是项目核心协议能力 | SDK TypedDict 只用于静态类型提示；`orjson` 只编码单帧 |
| 上游 SSE parser/accumulator | `httpx-sse` 无原始 bytes 旁路，解析再序列化会破坏同协议保真 | 自研有界逐行 parser，raw bytes 原样转发 |
| keepalive、delayed commit、buffered retry | 协议状态与提交时机高度业务化 | `sse-starlette` response、AnyIO/asyncio timeout/shield 原语 |
| RetryStrategy 调度器 | 错误驱动 payload 改写、跨策略预算、attempt 审计、学习回调，不是“重复同一函数” | 标准随机抖动/退避公式 |
| transport 自动重试 | 必须由唯一的可观测 retry owner 控制；SDK 与 transport 自动 retry 全关 | HTTPX exception taxonomy |
| AdaptiveRateLimiter | 上游反馈驱动三态状态机，不是固定速率 limiter | Event、clock、jitter |
| feature negotiation / thinking quarantine / token-limit store | 领域元数据、滑动 TTL、pin/expire/migration 语义超出通用 cache | dict、monotonic clock、原子文件替换 |
| History SQLite writer/schema | 有界队列、丢弃策略、单 writer 连接是核心；aiosqlite 无外层背压，ORM 与架构不符 | `sqlite3` + `asyncio.to_thread`/专用单线程 executor |
| sanitize 两阶段管道 | 是有序、幂等、可审计的协议修复状态机，不是 JSON Schema validation | Pydantic 做固定边界校验 |
| auto-truncate | tool 配对、thinking、system、索引映射和错误学习是领域不变量 | `tiktoken` 做 token primitive |
| repetition detector | 未知周期检测不匹配多-pattern 库；KMP 小、确定、有界 | property-based differential tests |
| 四阶段 shutdown | Uvicorn/AnyIO 不表达阶段升级和资源关闭顺序 | FastAPI lifespan、task group、event、cancel scope |
| request deadline / stale reaper | 单请求 SLA 与泄漏兜底是项目生命周期语义 | AnyIO/asyncio timeout 原语 |

## 4. 用户已裁决的架构决策

### D1. 并发抽象层

**决定：有限采用 AnyIO。** 在应用生命周期、后台服务、并发子任务、取消作用域和超时作用域中使用 AnyIO；底层只针对 asyncio 的 transport/SDK 互操作以及简单 `Event`/`Lock` 可继续使用标准库。不要为了“风格统一”机械迁移所有原语，也不要宣称项目支持 Trio——Uvicorn 和现有 SDK 的实际运行后端仍是 asyncio。在 AnyIO task group/cancel scope 内必须用 `task_group.start_soon()` 创建受管子任务；若调用 `asyncio.create_task()`，必须自行保存、取消并 await，不能假设 AnyIO 会传播取消。

未采用：全项目只用 asyncio 3.14。它语义单一，但 task group、cancel scope 与 FastAPI 生态的 AnyIO 接缝需要重复处理。

### D2. OTel beta instrumentation

**决定：接受 beta 自动 instrumentation，但默认关闭并锁整套兼容批次。** 理由是它显著减少 HTTP/FastAPI 通用埋点手写代码，HTTPX 源码核验确认不消费 SSE stream。约束：业务完整流时长不能依赖 headers 阶段结束的自动 client span；升级必须集成测试；配置默认关闭。

未采用：仅使用稳定 core API/SDK + 手写少量入站、出站业务 span。保留为 instrumentation 出现阻塞性缺陷时的逃生舱。

### D3. 日志与 trace context

**决定：OTel 权威、单向注入。** OTel context 是 trace/span 的权威来源；structlog contextvars 只保存 request_id、client、agent 等业务字段。日志 processor 在渲染时读取当前 OTel span 注入 trace_id/span_id，不把 trace context 复制绑定到另一套 ContextVar，避免过期和双向同步。tracing 未启用或当前 span 无效时，processor 直接省略 trace_id/span_id，不填伪造占位值。

### D4. Config source

**决定：直接使用 `settings_customise_sources` + 内置 YAML/CLI source，并保留一个项目自定义 merge source。** 目标代码尚未实现，现在采用不会产生迁移成本。不要先写完整手工 loader 再重构。

### D5. Token-limit cache 过期

**决定：24 小时可配置 TTL，key 仅使用规范化 `model`，并记录来源与学习时间。** 用户选择把 token limit 视为同名模型的固有属性，使不同账户/端点可以共享学习结果、加快收敛。命中可用于主动截断；模型目录或新一次上游错误给出明确 limit 时立即刷新；TTL 到期后不主动发探针，只回到响应式学习。

接受的权衡：如果未来实测同名模型在不同账户路由或 endpoint 下存在不同 limit，仅按 `model` 可能互相污染。届时应以真实反例为依据迁移到 `(base_url, endpoint, model)`，并提供持久化格式迁移，而不是静默改 key。

### D6. `/metrics` 暴露方式

**决定：复用现有 FastAPI `/metrics`。** `PrometheusMetricReader` 注册全局 registry，route 调用 `generate_latest(REGISTRY)`；避免额外监听端口和部署配置。实现时需有一次集成探针确认 scrape 触发 reader collect 且无重复注册。

## 5. 实施门禁

1. 所有新依赖在 Python 3.14 做安装/import smoke test，并在实施当日重新核验最新兼容版本。
2. SDK passthrough regression 必须断言未消费 stream、chunk 间隔、header/body 扩展字段和 `max_retries=0`。
3. JSON codec 必须先做 differential/property tests，再替换热路径；不得把可读持久化文件一并机械迁移。
4. OTel、sse-starlette、httpx_ws 都需要真实流式/WS black-box PoC，不能只靠类型或 README。
5. 任何底层库不得成为隐式第二 retry owner、第二 metrics store 或第二 context authority。
6. 若采用 AnyIO，必须集成测试 cancel scope 与 asyncio transport/原语混用时的取消传播，证明不会遗留孤儿任务。
7. `uvloop` 只凭通用 benchmark 不足以定案，必须用本项目的 SSE/WS 并发、取消和 shutdown 场景对 asyncio 3.14 做对照测试。
