# 域5：可观测性 / 日志 / 指标 / TUI

> 已阅读 `_briefing.md` 全部内容并照办；已读 `telemetry-observability.md`、`project-structure.md` 中 `observability/` 相关段落。

## 版本对齐核心结论（先行说明，贯穿全文）

项目已锁定 `opentelemetry-api==1.39.1`（发布于 2025-12-11）。经查 PyPI 元数据与 `opentelemetry-python-contrib` CHANGELOG：

- core（`opentelemetry-api`/`opentelemetry-sdk`/`opentelemetry-exporter-otlp*`）与 instrumentation 系列（`opentelemetry-instrumentation-*`、`opentelemetry-exporter-prometheus`）**不是同一版本号体系**，instrumentation 系列用 `0.xxb0`/`0.xxb1` 版本号，但两个系列按发布时间**同步打包发布**。
- 核对结果：**`opentelemetry-api/sdk 1.39.1` 精确对应 instrumentation 系列 `0.60b1`**（2025-12-11 同日发布）。`opentelemetry-instrumentation-fastapi==0.60b1` / `opentelemetry-instrumentation-httpx==0.60b1` / `opentelemetry-instrumentation-asgi==0.60b1` / `opentelemetry-exporter-prometheus==0.60b1` 均显式声明 `opentelemetry-sdk~=1.39.1`（`opentelemetry-exporter-prometheus` 的 `pyproject` 依赖甚至精确锁 `~=1.39.1`）。
- 若本项目要引入这些 instrumentation 包，**必须锁定 `0.60b1`**，不能凭直觉挑最新版（最新是 `0.64b0`，对应 core `1.43.0`，与已锁定的 `1.39.1` api 不兼容，会被 pip 依赖解析拒绝或产生运行时不一致）。
- **重要风险提示**：`opentelemetry-python-contrib` 官方 README 明确声明这些 instrumentation 包 "currently in beta, and shouldn't generally be used in production environments"。这是需要主会话/用户知悉并明确接受的风险，不属于本调研可自行拍板豁免的范畴，已列入「遗留疑问」。
- OTLP exporter（`opentelemetry-exporter-otlp-proto-grpc`）在 Python 3.14 上要求 `grpcio>=1.75.1`（版本号里显式区分了 `python_version>=3.14` 的约束），需要额外确认 `grpcio` 对 3.14 的 wheel 可用性（本次未见明确 ABI 问题报告，但建议实现阶段先跑一次 `pip install` 验证）。

推荐锁定版本组合（若采纳 OTel 全套方案）：

```
opentelemetry-api==1.39.1        # 已锁定，不变
opentelemetry-sdk==1.39.1
opentelemetry-instrumentation-fastapi==0.60b1
opentelemetry-instrumentation-httpx==0.60b1
opentelemetry-exporter-otlp==1.39.1          # 可选，仅当 tracing_endpoint 使用 OTLP
opentelemetry-exporter-prometheus==0.60b1    # 可选，仅当需要 /metrics 走 OTel Metrics 数据源
```

## 概览结论表

| 自研点(模块/文件) | 候选库 | 匹配度 | 威胁硬约束? | 推荐 | 理由 |
|---|---|---|---|---|---|
| 结构化日志 JSON/text 切换 + request_id 关联（`observability/logging.py`） | `structlog` 26.1.0 | 高 | 否 | **替换**（日志管线接管，前缀渲染需自定义 processor） | contextvars 原生支持，async 安全；JSON/text 双 renderer 开箱；固定宽度前缀需少量自定义 processor 承载 |
| 同上，仅 JSON 格式化 | `python-json-logger` 4.1.0 | 中 | 否 | 不采用（劣于 structlog） | 只解决 JSON 序列化，不解决 request_id 跨协程传播这一核心痛点 |
| 同上 | `loguru` 0.7.3 | 低-中 | 否 | 不采用 | 全局单例 logger 设计与 FastAPI/uvicorn 现有 logging 生态整合成本高，contextvars 支持不如 structlog 系统化 |
| OTel 入站 span（FastAPI 自动埋点，`observability/tracing.py`） | `opentelemetry-instrumentation-fastapi==0.60b1` | 高 | 否 | **替换**（零手写 span） | `FastAPIInstrumentor.instrument_app(app)` 一行代码接管，文档设想的手写 span 逻辑可完全省略 |
| OTel 出站 span（httpx 自动埋点） | `opentelemetry-instrumentation-httpx==0.60b1` | 高 | 否（已读源码确认） | **替换**（零手写 span） | `AsyncOpenTelemetryTransport` 只包裹调用、透传 `stream` 对象本体，不消费/不缓冲流，不违反 P6 |
| OTLP/stdout exporter 选择与装配 | `opentelemetry-sdk` + `opentelemetry-exporter-otlp` | 高 | 否 | **替换**（本就是标准 SDK 用法，无需自研） | `BatchSpanProcessor` + 可插拔 exporter 是 OTel SDK 标准模式，文档现有设计已经是"用库"而非"自研"，仅需锁定正确版本 |
| 内存维度计数器 + 手写导出到 OTel（`observability/telemetry.py` 的 `_counters: dict`） | 直接用 OTel Metrics API（`Counter`/`Histogram`） | 高 | 否 | **替换**（消除双写） | 现设计"内存 dict 计数 + 同步再手动 `.add()` 到 OTel instrument"是重复记账；应删除内存 dict，只保留一份 OTel instrument 作为唯一数据源 |
| `/metrics` Prometheus 文本导出（`routes/metrics.py`） | `opentelemetry-exporter-prometheus==0.60b1`（`PrometheusMetricReader`） | 高（但有实现细节要定） | 否 | **替换**（同一份 OTel 数据源） | 已读源码确认 `PrometheusMetricReader` 是 pull 模型，按需从 SDK 拉取数据序列化为 Prometheus 文本，**不需要**额外手写 `prometheus_client.Counter/Histogram`；比文档现设想的"OTel instrument + prometheus_client 双写同步"更简 |
| 同上，若不采用 OTel Metrics 全套，仅想要 Prometheus 文本 | `prometheus_client` 0.25.0 单独使用 | 中 | 否 | 备选（仅当放弃 OTel Metrics 数据源统一时） | 更轻量但会退回到"两套独立计数器"的重复记账问题，不如上一条 |
| TUI 渲染循环、按键处理、终端控制（`observability/tui.py`） | `textual` 8.2.8 | 高 | 否 | **替换**（渲染循环/布局/按键事件） | reactive/message 模型天然契合"纯 reducer + 事件驱动更新"架构；文档已预先做出同样推荐，本次核实版本/维护度后予以确认 |
| 同上，更轻量方案 | `rich.live` | 中 | 否 | 不采用（除非明确要更轻依赖） | 功能弱于 textual 的完整 TUI 框架能力（无内建按键/焦点/布局系统），textual 本身依赖 rich，属于父子关系而非互斥选项 |

## 逐项详述

### 结构化日志（`observability/logging.py`）

**现状**：文档要求两种输出格式（JSON 生产 / text 开发）、固定宽度 ASCII 前缀（`[ OK ]`/`[FAIL]`/`[RETRY]` 等）、按 `request_id` 关联同一请求生命周期全部日志行（`telemetry-observability.md` L31-77）。核心诉求是 `get_request_logger(ctx.id)` 绑定 request_id 后自动携带到所有日志调用。

**候选库核对**：

- **`structlog`**（最新 26.1.0，2026-06-06 发布，`requires-python >= 3.10`，兼容 3.14；类型标注完善；Apache/MIT 双协议宽松许可；GitHub 星标量级为 Python 结构化日志生态事实标准）。
  - `structlog.contextvars` 模块基于标准库 `contextvars.ContextVar`，文档明确称其"safe to be used both in threaded as well as asynchronous code"，可以在 FastAPI 中间件里 `clear_contextvars()` + `bind_contextvars(request_id=...)`，之后跨函数/跨协程调用的所有 `structlog` logger 都会自动带上该字段（通过 `merge_contextvars` processor，需放在 processor 链首位）。
  - JSON/text 双格式：`structlog.processors.JSONRenderer()` 与 `structlog.dev.ConsoleRenderer()`（或自定义 `KeyValueRenderer`）可以按配置切换，这正是文档要求的 `observability.log_format` 开关。
  - **固定宽度前缀不是 structlog 内置能力**：需要自定义一个 processor，在 `event_dict` 里根据请求阶段字段拼出 `[ OK ]`/`[FAIL]` 等前缀字符串，再交给 renderer。这部分仍是少量自研代码，但被纳入 structlog 的标准 processor pipeline，而非独立的字符串拼接逻辑，可维护性显著提升。
  - 与 uvicorn/FastAPI 日志整合：uvicorn 默认用标准库 `logging`，`structlog` 可以通过 `structlog.stdlib.ProcessorFormatter` 把标准库 `logging` 记录也路由进同一套 processor 链，实现二者输出格式统一（这是 structlog 官方文档明确支持的场景，非本次调研杜撰）。
  - 性能：`structlog` 的 processor 链是同步函数调用链，无额外线程/锁开销，社区公认性能足以覆盖高吞吐服务场景。

- **`python-json-logger`**（4.1.0，`>=3.10`，MIT 许可）：只是一个标准库 `logging.Formatter` 子类，负责把 LogRecord 序列化成 JSON。**不提供** contextvars 传播机制，仍需自己实现 request_id 绑定（例如用 `logging.Filter` + 手写 contextvars 存取），本质上只解决"格式化"这一个子问题，工作量节省有限。

- **`loguru`**（0.7.3，`<4.0,>=3.5`）：设计上是全局单例 `logger` 对象，不走标准库 `logging` 的 handler/formatter 体系，与 uvicorn（用标准库 logging）整合需要额外桥接层（`InterceptHandler` 之类的样板代码，loguru 官方文档本身给出了这种桥接示例，说明这一整合并非无成本）。contextvars 支持不如 structlog 系统化（loguru 有 `contextualize()` 上下文管理器，但生态成熟度、文档完整度不如 structlog 的 `contextvars` 模块）。

**是否威胁 P1/P6/保真度**：无威胁。日志本身是同步内存操作 + 落盘由标准 `logging` handler（如异步 handler）承担，不涉及热路径新增阻塞 I/O；不涉及流式响应体处理。

**推荐**：**替换**——采用 `structlog` 接管日志格式化 + request_id 传播；固定宽度前缀作为自定义 processor 保留少量自研代码；与 uvicorn 整合走 `ProcessorFormatter` 桥接标准 `logging`。

### OpenTelemetry 追踪（`observability/tracing.py`）

**现状**：文档已经预先设计为"自动 instrumentation"（`telemetry-observability.md` L79-117），即已经倾向用库而非手写 span，本次调研任务是核实这个设计假设是否成立、版本是否兼容。

**候选库核对**：

- **`opentelemetry-instrumentation-fastapi==0.60b1`**（对应 core 1.39.1；`requires-python>=3.10`；依赖 `opentelemetry-instrumentation-asgi==0.60b1` + `opentelemetry-instrumentation==0.60b1`）：`FastAPIInstrumentor.instrument_app(app)` 一行代码即可为每个入站请求自动生成 span，span 命名规则、`http.method`/`http.route`/`http.status_code` 属性均由库自动填充，与文档描述完全一致。**零手写 span 代码**，文档里给出的 `setup_tracing()` 示例函数本身就是标准装配代码而非自定义埋点逻辑，符合"用成熟库"的诉求。
- **`opentelemetry-instrumentation-httpx==0.60b1`**：`HTTPXClientInstrumentor().instrument()` 全局接管所有 httpx client 的出站请求，自动生成子 span 并与入站 span 建立父子关系（通过 OTel Context 传播机制，无需手动传递 trace context）。
  - **已读源码确认不违反 P6**：`opentelemetry/instrumentation/httpx/__init__.py` 中的 `AsyncOpenTelemetryTransport.handle_async_request()` 只是在原始 `handle_async_request` 调用前后加 span 记录（`start_as_current_span` + 耗时统计），响应对象的 `stream`（`httpx.AsyncByteStream`）字段被原样提取并透传给上层（`_extract_response()` 只是解包 `(status_code, headers, stream, extensions, http_version)` 元组，不读取/不消费 stream 内容），**不存在强制缓冲整个响应体的行为**。SSE 流式转发场景可以安全叠加此 instrumentation。
- **`opentelemetry-sdk` + `opentelemetry-exporter-otlp`（`==1.39.1`）**：`TracerProvider` + `BatchSpanProcessor` + 可插拔 exporter（OTLP/stdout/None）是 OTel SDK 官方标准用法，文档现有 `setup_tracing()` 示例本身已经是"标准装配"而非自研，仅需确保版本号精确对齐（见前文版本对齐结论）。OTLP exporter 在 Python 3.14 上依赖 `grpcio>=1.75.1`，需在实现阶段验证 wheel 可用性。

**是否威胁 P1/P6/保真度**：不威胁。span 记录是内存操作 + `BatchSpanProcessor` 后台批量导出（off 请求热路径，本身就是 OTel SDK 设计的一部分）；httpx instrumentation 透传 stream，不缓冲。

**推荐**：**替换**——完全采用自动 instrumentation，文档中若有手写 span 的示意代码应删除或改写为纯"装配代码"（`instrument_app` / `.instrument()` 调用），不需要在业务代码里手写 `tracer.start_as_current_span(...)`。

### 请求遥测 / 指标（`observability/telemetry.py` + `routes/metrics.py`）

**现状**：文档已经采取"轻量内存计数器 + 同步导出到 OTel Metrics"的分层简化方案（`telemetry-observability.md` L119-186），明确放弃 DDSketch/三层 SQLite/rollup（见 `BACKLOG.md` 第 3 条），核心诉求是把直方图分位数计算、长期聚合完全交给 OTel + collector/TSDB。本次调研的关键问题是：现设计中"内存 dict 计数器"与"OTel instrument"两者同时维护（`record_request_telemetry()` 示例代码里 `_counters[dims].requests += 1` 之后又调用 `_otel_request_counter.add(...)`）是否有必要，能否进一步简化为单一数据源。

**候选库核对**：

- **直接使用 OTel Metrics API（`meter.create_counter()` / `meter.create_histogram()`）**：OTel SDK 的 `Counter`/`Histogram` instrument 本身就是"进程内维护计数状态 + 支持多维度 attributes"的实现，与文档手写的 `_counters: dict[TelemetryDimensions, Counters]` 在功能上完全重合。**没有必要再手写一份内存 dict 做重复记账**——`.add(n, attributes=...)` 调用本身就是 O(1) 的原子操作，满足"简单递增、无锁竞争热点"的诉求，且已经是标准库级实现，无需自研。
- **`opentelemetry-exporter-prometheus==0.60b1`（`PrometheusMetricReader`）**：已下载源码核实（`opentelemetry/exporter/prometheus/__init__.py`）。它是一个 `MetricReader` 子类，工作模式是 **pull**：Prometheus/`generate_latest()` 抓取时触发 `_CustomCollector.collect()` 回调，从 OTel SDK 内部状态里拉取最新聚合值实时转换成 Prometheus 文本格式（`CounterMetricFamily`/`HistogramMetricFamily` 等）。**关键结论：不需要额外维护一份 `prometheus_client.Counter/Histogram`**，`prometheus_client` 库在这里只承担两个角色：(a) 提供 `REGISTRY.register()` 机制供 `PrometheusMetricReader` 挂载自己；(b)（可选）`start_http_server()` 独立起一个抓取端口。文档现有表述"`prometheus_client` 库的 `Counter`/`Histogram` 与内存计数器/OTel instrument 保持同一份数据源"这一设计可以进一步简化——**不需要 `prometheus_client.Counter/Histogram` 这两个类型**，只需要 OTel Metrics API 一份数据源，`PrometheusMetricReader` 作为 `MeterProvider` 的第二个 `metric_readers`（第一个可以是 OTLP 相关 reader）即可同时供 OTLP 和 Prometheus 抓取。
- **`prometheus_client` 单独使用**（不接入 OTel）：更轻量，但会退回"两套独立计数体系"的重复记账问题，除非项目决定完全放弃 OTel Metrics（不符合文档已确立的"以 OTel 为标准协议"取向），不推荐作为主方案。

**是否威胁 P1/P6/保真度**：不威胁。指标记录是内存操作；`PrometheusMetricReader` 是 pull 模型，抓取发生在独立的 `/metrics` 请求处理时，不在业务请求热路径上产生额外开销（除非抓取频率极高，但这是可观测性基础设施的常规行为，不受本项目控制也不需要控制）。

**推荐**：**替换/简化**——删除手写 `_counters: dict` 内存计数器，只保留 OTel Metrics API 的 `Counter`/`Histogram` 作为唯一数据源；`/metrics` 端点改用 `PrometheusMetricReader` 从同一数据源拉取，不再需要 `prometheus_client.Counter/Histogram` 这层额外封装。此举比文档现有设计（三份并行记账：内存 dict + OTel instrument + prometheus_client 类型）更简，消除潜在的数据不一致风险（三份记账逻辑分叉后难以保证语义一致）。

### TUI（`observability/tui.py`）

**现状**：文档已经给出两个候选方案并倾向方案 1（`textual`），本次任务是核实版本、维护状态。

**候选库核对**：

- **`textual`**（最新 8.2.8，2026-06-30 发布，`requires-python <4.0,>=3.9`，兼容 3.14；MIT 许可；由 Textualize 团队积极维护，Python 终端 UI 框架事实标准之一，依赖 `rich>=14.2.0`）：其 reactive 属性 + message 系统天然契合文档描述的"纯 reducer + impure 渲染 sink"架构——业务方只需要把 `TuiState` 映射到 `textual` 的 Widget 更新（如 `reactive` 属性赋值触发重渲染），终端控制序列、resize 处理、按键事件循环全部由 `textual` 内部承担，不需要手写 `decode_key()` 这类底层按键解析（`textual` 有自己的 `Key` 事件系统）。
- **`rich.live`**：`rich` 本身（最新 15.0.0）提供更底层的"实时刷新一块区域"能力，但没有 `textual` 的按键路由、焦点管理、布局系统，适合"只读展示、无交互"的更简单场景。鉴于文档明确要求方向键导航、详情态选中等交互，`textual` 更贴合需求；`rich` 实际上是 `textual` 的底层依赖，二者不是互斥选项而是包含关系。

**是否威胁 P1/P6/保真度**：文档已明确 TUI 是"P1 只读"（只订阅事件、不反向控制请求），`textual` 的渲染循环运行在独立的终端 I/O 循环里，不侵入请求处理热路径。

**推荐**：**替换（沿用文档已有推荐）**——用 `textual` 承接渲染循环/布局/按键分发，业务方只需保留 `tui_reduce()` 纯 reducer 与 `decode_key()`（若不使用 textual 内置按键系统，可省略自研 `decode_key`，直接用 textual 的 `on_key` 事件）。`state`→`reducer`→`textual widget` 的纯/副作用分层设计本身值得保留，是本项目自己的架构决策，不属于"自研 vs 用库"的替换范畴。

## 遗留疑问 / 需主会话或用户裁决的点

1. **instrumentation 系列长期处于 beta（0.x）状态**：`opentelemetry-python-contrib` 官方声明这些包 "shouldn't generally be used in production environments"。是否接受在生产依赖中引入 beta 状态的第三方包？若不接受，退路是保留手写 span（放弃"零代码自动埋点"收益，仅用 `opentelemetry-api`/`opentelemetry-sdk` 手写 span 记录逻辑）。**这是本调研认为最重要、需要用户明确表态的一点**，因为它直接决定"OTel 追踪"这一条能否按推荐方案落地。
2. **固定宽度 ASCII 前缀不是 structlog 内置能力**，需要额外编写一个自定义 processor（拼接 `[ OK ]`/`[FAIL]` 等前缀），这部分仍是少量自研代码，只是被纳入 structlog 标准 pipeline，不算"完全被库解决"。需要在实施计划里明确列出这个小型自定义 processor 作为交付项，不要误以为引入 structlog 后这部分工作量为零。
3. **`/metrics` 路由挂载方式待定**：若采用 `PrometheusMetricReader`，其官方示例默认用 `start_http_server()` 在**独立端口**（默认 9464）暴露抓取端点，与文档设想的"复用现有 FastAPI app 的 `/metrics` 路由"存在差异。需要主会话/实现者在实现阶段选定：(a) 接受独立端口，放弃在同一 FastAPI app 挂载；或 (b) 不使用 `start_http_server()`，改为自定义 FastAPI route 内手动调用 `prometheus_client.generate_latest(REGISTRY)`（`PrometheusMetricReader` 内部把自己注册进了全局 `prometheus_client.REGISTRY`，因此这个手动调用方式在技术上可行，但未在官方文档中作为"标准用法"给出，需要实现阶段验证）。
4. **OTLP exporter 在 Python 3.14 上的 `grpcio` 依赖**：`opentelemetry-exporter-otlp-proto-grpc` 显式区分了 `python_version>=3.14` 时要求 `grpcio>=1.75.1`，本次调研未做实际安装验证（仅核对了 PyPI 元数据），建议实现阶段第一步先做一次 `uv pip install` 验证该版本 wheel 在 3.14 环境下确实可安装且可导入，避免规划阶段假设成立、实现阶段才发现依赖冲突。
5. **是否需要同时保留 stdout exporter 用于本地调试**：文档已设计三种 exporter（`otlp`/`stdout`/`none`），本调研未发现需要变更此设计的理由，维持文档现状即可，仅在此处提示：`stdout` exporter 属于 `opentelemetry-sdk` 内置（`ConsoleSpanExporter`），不需要额外第三方包。
