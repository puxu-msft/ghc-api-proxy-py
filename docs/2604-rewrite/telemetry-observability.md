# 可观测性：日志、追踪、遥测、TUI

> 本文档是**目标设计**（design spec），标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。

## 概述与性能声明

`observability/` 子包提供本项目全部的可观测性能力：结构化日志、分布式追踪、请求遥测计数、健康/状态端点，以及可选的终端 UI（TUI）。

**核心立场：分层遥测的性能简化，见 [BACKLOG.md 第 3 条](BACKLOG.md#3-分层遥测ddsketch--rawhourlydaily简化)。**

上游参考项目的 `request-telemetry.ts`（约 **90KB** 单文件）实现了一套相当重的分层遥测系统：

- **维度化计数器**：按 model / endpoint / status / client / agent 等多维度交叉累加请求数、token 数、耗时、成本等指标；
- **DDSketch 直方图**：为延迟等连续值分布构建可合并的分位数草图（sketch），支持跨时间窗口聚合分位数；
- **三层 SQLite 存储**：raw（5 分钟粒度，保留 7 天）→ hourly（保留 90 天）→ daily（长期），三层之间靠周期性 **rollup** 任务把细粒度数据聚合并降采样进粗粒度表；
- **cumulative tier**：额外维护一份“从不清零”的累计视图；
- **基数上限**：为了防止维度组合（model × endpoint × client × agent）无界增长拖垮存储，还需要专门的基数上限与淘汰逻辑；
- **一次性 JSON backfill**：历史数据迁移到新 schema 的一次性回填任务。

**这在请求热路径上的开销是：** 每个请求完成时，至少要做一次多维度计数器的原子递增 + 一次 DDSketch 直方图桶更新；同时后台常驻着 rollup 定时任务持续读写三张 SQLite 表并做降采样计算。对于一个以“转发代理”为核心职责的服务而言，这套自建时序数据库的复杂度和 CPU/IO 成本已经超出了“可观测性”本身的合理边界——**指标的存储、聚合、长期趋势分析，本就是成熟时序数据库（TSDB）和监控生态的分内之事，不该由代理进程自己实现一遍**。

**本项目的简化方案**：

- 进程内只维护**轻量内存计数器**（简单的 `dict`/`collections.Counter` 递增，O(1)，无锁竞争热点，无需持久化到本地文件）；
- 通过 **OpenTelemetry**（OTel）标准协议把指标、追踪导出给外部 collector；直方图、长期聚合、多维度下钻查询、告警规则，全部交给成熟的 OTel collector + 后端 TSDB（Prometheus / VictoriaMetrics / Grafana 等）去做；
- `/metrics` 端点额外暴露一份 Prometheus 文本格式，兼容不愿意跑完整 OTel collector 的简单场景（直接被 Prometheus server 抓取）；
- 分层遥测（DDSketch + 三层 SQLite + rollup）整体列入 [BACKLOG](BACKLOG.md#3-分层遥测ddsketch--rawhourlydaily简化) 作为**可选**能力，默认不实现、不启用。

这一取舍与 [DESIGN.md](DESIGN.md#性能设计原则第一优先级) 的 P3（分层归档同理简化）、`battle-tested-over-hand-rolled` 的工程原则一致：能交给成熟外部系统做的事，不在代理进程内手搓一遍。

## 结构化日志（`observability/logging.py`）

### 格式

两种输出格式，由 `observability.log_format` 配置项切换：

- **`json`**（生产推荐）：每行一个 JSON 对象，字段包括 `timestamp` / `level` / `request_id` / `message` / 额外的结构化字段（model、endpoint、status 等）。便于日志聚合系统（Loki/ELK）解析。
- **`text`**（开发默认）：人类可读的单行格式，见下方固定宽度前缀约定。

### 固定宽度 ASCII 前缀

`text` 格式下，每条日志以固定宽度的 ASCII 前缀标注请求生命周期阶段，视觉上对齐、易于扫描：

| 前缀 | 含义 |
|------|------|
| `[....]` | 请求已接收，处理中（占位符，尚无阶段性结果） |
| `[<-->]` | 流式响应进行中 |
| `[ OK ]` | 请求成功完成 |
| `[FAIL]` | 请求失败 |
| `[RETRY]` | 正在执行某个重试策略 |

日志行格式：

```
[PREFIX] HH:MM:SS METHOD /path ...
```

例如：

```
[ OK ] 14:32:07 POST /v1/messages model=claude-sonnet-4.5 tokens=1024/342 duration=2.3s
[RETRY] 14:32:10 POST /v1/messages strategy=token-refresh attempt=2
[FAIL] 14:32:15 POST /chat/completions status=429 rate_limited
```

### 按 request_id 关联

同一请求生命周期内的所有日志行携带同一个 `request_id`（`RequestContext.id`），便于在聚合系统里按请求串联全部日志（清洗 → 审批 → 限流等待 → 执行 → 重试 → 完成）。

```python
logger = get_request_logger(ctx.id)  # 绑定 request_id 的 contextual logger
logger.info("sanitize completed", extra={"modifications": len(sanitization.modifications)})
```

### 只显示相关信息

非模型请求（如 `/health`、`/metrics`、管理 API）不显示模型名/token 等字段——这些字段在这些端点上没有意义，强行显示只会制造噪音。日志字段按端点类型条件性附加，而不是统一的大而全模板。

## OpenTelemetry（`observability/tracing.py`）

### 自动 instrumentation

- **入站 span**：FastAPI 的每个请求自动生成一个 span（用 `opentelemetry-instrumentation-fastapi` 自动埋点），span 名为 `{method} {route}`，属性含 `http.method`/`http.route`/`http.status_code`。
- **出站 span**：httpx 客户端每次向上游发起的请求自动生成子 span（用 `opentelemetry-instrumentation-httpx`），与入站 span 建立父子关系，形成完整的请求-转发调用链。

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

def setup_tracing(app: FastAPI, settings: ObservabilitySettings) -> None:
    if not settings.tracing_enabled:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "ghc-api-proxy"}))
    exporter = build_exporter(settings.tracing_endpoint)  # OTLP / stdout / None
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
```

### 可配置 exporter

| Exporter | 说明 |
|----------|------|
| `otlp` | 标准 OTLP（gRPC/HTTP），发往外部 collector，生产推荐 |
| `stdout` | 打印到标准输出，本地调试用 |
| `none`（默认） | 禁用追踪，零开销 |

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `observability.tracing_enabled` | `false` | 是否启用 OpenTelemetry 追踪 |
| `observability.tracing_endpoint` | `""`（未设置） | OTLP collector 地址，如 `http://localhost:4317` |

默认关闭，符合“重特性默认关”的整体取向（[DESIGN.md](DESIGN.md#性能设计原则第一优先级) 通用性能取向）。

## 请求遥测（`observability/telemetry.py`）

### 轻量维度计数

进程内维护一组内存计数器，按以下维度分组：

- `model`：解析后的模型名
- `endpoint`：`openai-chat-completions` / `openai-responses` / `anthropic-messages` / `gemini-generate-content` 等
- `status`：`success` / `error` / `aborted`
- `client`：调用方标识（如 User-Agent 归一化后的客户端类型）
- `agent`：Agent 类型（如 Claude Code / Codex，从特定 header 识别）

每个维度组合下累计：请求数、input tokens、output tokens、耗时。**不做基数上限**——维度组合数受限于实际接入的客户端/模型种类，工程上认为在合理范围内；若未来出现基数爆炸场景，优先通过采样或维度收窄解决，而不是重新引入自建基数管理。

### Token 计数含 reasoning_tokens

Token 计数细化到 **reasoning tokens**（推理模型的思维链 token，产生成本但不出现在最终输出文本里），从响应的 `usage.output_tokens_details.reasoning_tokens` 字段提取：

```python
def extract_reasoning_tokens(usage: UsageData) -> int:
    """从 usage.output_tokens_details.reasoning_tokens 提取推理 token 数（无则为 0）。"""
    details = usage.output_tokens_details
    return details.reasoning_tokens if details is not None else 0

def record_request_telemetry(ctx: RequestContext, usage: UsageData) -> None:
    reasoning = extract_reasoning_tokens(usage)
    dims = TelemetryDimensions(
        model=ctx.resolved_model,
        endpoint=ctx.endpoint,
        status="success" if ctx.state == "completed" else "error",
        client=ctx.client_label,
        agent=ctx.agent_label,
    )
    _counters[dims].requests += 1
    _counters[dims].input_tokens += usage.input_tokens
    _counters[dims].output_tokens += usage.output_tokens
    _counters[dims].reasoning_tokens += reasoning
    _counters[dims].duration_seconds += ctx.duration()

    # 同步导出到 OpenTelemetry Metrics（Counter/Histogram），
    # 不在进程内做任何聚合/持久化——留给 OTel SDK 的内置批处理 + collector
    _otel_request_counter.add(1, attributes=dims.as_otel_attributes())
    _otel_token_counter.add(usage.input_tokens, attributes={**dims.as_otel_attributes(), "token_type": "input"})
    _otel_token_counter.add(usage.output_tokens, attributes={**dims.as_otel_attributes(), "token_type": "output"})
    _otel_token_counter.add(reasoning, attributes={**dims.as_otel_attributes(), "token_type": "reasoning"})
    _otel_duration_histogram.record(ctx.duration(), attributes=dims.as_otel_attributes())
```

### 用 OpenTelemetry Metrics 导出，不自建存储

直方图（如请求耗时分布）用 OTel Metrics API 的 `Histogram` instrument 记录，桶边界、分位数计算、跨时间窗口聚合全部由 OTel SDK + collector 后端负责，**不在进程内维护 DDSketch 或任何自定义分位数草图**。这是与上游最核心的分歧点：上游把“存储与聚合”内建进应用进程，本项目把它交还给专门的可观测性基础设施。

### `/metrics` 暴露 Prometheus 文本

对于没有部署 OTel collector、只想直接用 Prometheus 抓取的简单场景，额外暴露一个标准 Prometheus 文本格式端点：

```python
@router.get("/metrics")
async def metrics_endpoint() -> Response:
    """Prometheus 文本格式，抓取当前进程内计数器快照。"""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4",
    )
```

`prometheus_client` 库的 `Counter`/`Histogram` 与上文的内存计数器/OTel instrument 保持同一份数据源（避免重复记账），二者是同一套指标的两种导出通道。

## 观察者/sink 模型

请求生命周期中的关键事件（`created` / `sanitized` / `approval_requested` / `approval_resolved` / `attempt_started` / `attempt_failed` / `streaming_started` / `completed` / `failed` / `aborted`）通过一个中心化的**事件总线**分发给多个订阅者（sink）：

| Sink | 职责 |
|------|------|
| `ConsoleSink` | 驱动 TUI（终端交互式展示，见下文，可选） |
| `LogSink` | 写入结构化日志 |
| `HistorySink` | 触发历史记录的 off-loop 持久化（见 [history-system.md](history-system.md)） |
| `TelemetrySink` | 更新内存维度计数器 + 推送 OTel metrics |
| `WsSink` | 通过 WebSocket 推送给前端订阅者 |

```python
class ObservabilityBus:
    """请求生命周期事件的中心分发器。同步 publish，sink 各自的异步处理不阻塞发布方。"""

    def __init__(self) -> None:
        self._sinks: list[ObservabilitySink] = []

    def subscribe(self, sink: ObservabilitySink) -> None:
        self._sinks.append(sink)

    def publish(self, event: ObservabilityEvent) -> None:
        for sink in self._sinks:
            try:
                sink.handle(event)  # 各 sink 内部自行决定同步处理还是 create_task 异步处理
            except Exception:
                logger.exception("sink %s failed to handle event %s", sink, event.kind)
                # 一个 sink 抛错不影响其余 sink 收到事件——never-swallow-errors：
                # 这里記录异常而非静默吞掉，但不重新抛出以免阻断分发链
```

**性能**：sink 的消费逻辑（尤其 HistorySink 的落盘、TelemetrySink 的 OTel 导出）严格 off 请求关键路径——`publish()` 本身只是把事件塞进各 sink 各自的处理逻辑（内存操作或 `asyncio.create_task` 派生后台任务），不阻塞请求返回。这与 [DESIGN.md](DESIGN.md#性能设计原则第一优先级) P1（历史/遥测/隔离等 I/O 一律 off-event-loop）的原则一致。

## TUI（可选，`observability/tui.py`）

**默认可关**，标注为可选特性；启用后在终端提供交互式的实时请求监控界面。

### 分层 pure/impure 设计

参考上游的架构思路——把状态机、按键解析这些**纯函数**部分从“实际渲染到终端”的**副作用**部分中剥离出来，二者独立可测试：

```
纯 reducer（状态机）  ←──  纯 key decoder（按键 → 动作）
        │
        ▼
  impure 渲染 sink（订阅生命周期事件，更新终端显示）
```

- **纯 reducer**：`(state, action) -> new_state`，无 I/O，可用普通单元测试驱动，覆盖状态转换的所有分支。三级状态机：
  - `collapsed footer`（折叠态，只显示一行摘要：活跃请求数/成功/失败计数）
  - `panel 列表`（展开态，列出最近 N 个请求的一行摘要）
  - `detail`（详情态，选中某个请求，展示完整 payload/响应/attempts）
- **纯 key decoder**：把终端原始按键序列（如方向键的转义序列）解析为语义化的动作（`ExpandAction` / `SelectNextAction` / `EnterDetailAction` / `ExitAction`），同样是无副作用的纯函数，便于对各种终端按键序列做穷举测试。
- **impure 渲染 sink**：订阅 `ObservabilityBus` 的生命周期事件，驱动 reducer 更新状态，并把新状态渲染到终端（这一层才真正接触 I/O：终端输出、按键读取）。

```python
@dataclass(frozen=True)
class TuiState:
    view: Literal["collapsed", "panel_list", "detail"]
    requests: tuple[RequestSummary, ...]
    selected_index: int | None

def tui_reduce(state: TuiState, action: TuiAction) -> TuiState:
    """纯函数：(state, action) -> new_state。无 I/O，单元测试驱动。"""
    match action:
        case ExpandAction():
            return replace(state, view="panel_list")
        case EnterDetailAction(index=i):
            return replace(state, view="detail", selected_index=i)
        case ExitAction():
            return replace(state, view="collapsed")
        case RequestAddedAction(summary=s):
            return replace(state, requests=(*state.requests, s))
        case _:
            return state

def decode_key(raw: bytes) -> TuiAction | None:
    """纯函数：终端原始按键字节 → 语义动作。"""
    if raw == b"\x1b[B":  # 方向键 Down
        return SelectNextAction()
    if raw == b"\r":
        return EnterDetailAction(index=...)
    ...
```

### P1 只读

TUI 只**读取**请求生命周期事件并展示，不提供任何“从 TUI 反向控制请求”的交互（如取消、修改）——那是审批系统（[approval-system.md](approval-system.md)）的职责范畴，TUI 与审批 API 是两个独立关注点。

### Python 实现思路

两种候选方案：

1. **[推荐] 用现成库**：[`textual`](https://github.com/Textualize/textual)（或更轻量的 `rich.live`）提供成熟的终端渲染循环、布局、按键事件处理，本项目只需实现 reducer + 事件到 widget 的映射，不必手搓终端控制序列。`textual` 的 reactive/message 模型天然契合“事件驱动更新状态”的设计。
2. **轻量自实现**：仅用标准库 `curses`（或纯 ANSI 转义序列 + `sys.stdout`）手写渲染循环，适合希望零第三方依赖的极简部署场景，但需要自行处理终端 resize、方向键转义序列解析等细节，工作量明显更大。

默认建议方案 1（`battle-tested-over-hand-rolled`），除非有明确的“零依赖”约束。

### 配置

TUI 归属 `observability` 配置 section（完整清单以 [config-system.md](config-system.md#observability-section-python-侧新增日志追踪配置) 为准），新增键 `tui_enabled`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `observability.tui_enabled` | `false` | 是否启用终端 UI（默认关，避免非交互式部署环境如容器/CI 中产生无意义的终端控制序列输出） |

## 健康与状态端点

| 端点 | 说明 |
|------|------|
| `GET /health`、`/health/readiness` | 就绪检查：`200`（健康）/`503`（未就绪），检查项含 Copilot token、GitHub token、模型目录是否已加载 |
| `GET /health/liveness` | 存活检查：恒 `200`，先于 token 中间件与关闭门注册——即使 Copilot token 失效或正处于优雅关闭阶段，liveness 仍应返回 `200`（避免容器编排系统因误判存活状态而强制重启进程；判断“能否接流量”是 readiness 的职责，不是 liveness） |
| `GET /api/status` | 聚合状态：`uptime` / `auth`（token 有效性）/ `quota`（配额使用情况）/ `activeRequests`（当前活跃请求数）/ `rateLimiter`（限流器当前模式）/ `shutdown`（若正在关闭，当前所处阶段）/ `models`（模型目录加载状态）等 |

```python
@router.get("/health/liveness")
async def liveness() -> dict:
    """恒 200，不依赖 token/上游状态。"""
    return {"status": "alive"}

@router.get("/health", tags=["health"])
@router.get("/health/readiness", tags=["health"])
async def readiness(state: AppState = Depends(get_app_state)) -> JSONResponse:
    healthy = bool(state.copilot_token and state.github_token)
    return JSONResponse(
        {
            "status": "healthy" if healthy else "unhealthy",
            "checks": {
                "copilot_token": bool(state.copilot_token),
                "github_token": bool(state.github_token),
                "models": bool(state.models),
            },
        },
        status_code=200 if healthy else 503,
    )

@router.get("/api/status")
async def status(
    state: AppState = Depends(get_app_state),
    ctx_manager: RequestContextManager = Depends(get_context_manager),
    rate_limiter: AdaptiveRateLimiter = Depends(get_rate_limiter),
    shutdown_mgr: ShutdownManager = Depends(get_shutdown_manager),
) -> dict:
    return {
        "uptime_seconds": time.time() - state.started_at,
        "auth": {"github_token": bool(state.github_token), "copilot_token_valid": state.copilot_token_valid()},
        "quota": state.quota_snapshot(),
        "active_requests": ctx_manager.active_count(),
        "rate_limiter": {"mode": rate_limiter.mode},
        "shutdown": {"phase": shutdown_mgr.current_phase},
        "models": {"loaded": bool(state.models), "count": len(state.models.data) if state.models else 0},
    }
```

## 相关文档

- [设计文档总纲](DESIGN.md)
- [BACKLOG.md 第 3 条](BACKLOG.md#3-分层遥测ddsketch--rawhourlydaily简化)（分层遥测的性能简化决策）
- [历史与审计系统](history-system.md)（HistorySink 落盘、WebSocket 推送共享同一 sink 模型）
- [手动审批系统](approval-system.md)（审批事件复用同一 WebSocket 通道）
- [配置系统](config-system.md)（`observability.*` 配置完整清单）
- [优雅关闭](shutdown.md)（关闭阶段在 `/api/status` 中的展示）
