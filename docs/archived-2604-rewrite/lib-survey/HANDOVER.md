# 库调研任务交接报告（HANDOVER）

> 日期：2026-07-15 ｜ 面向：接续本任务的下一会话
> 一句话：文档重写后，按用户「各模块不自研、尽量用成熟库」的本意，已完成上游 SDK 选型、六个域的库调研、关键断言独立核验、对抗评审与用户架构裁决；最终定稿见 [SELECTIONS](SELECTIONS.md)。

---

## 1. 用户本意（任务的锚，不要偏离）

用户重写了 `docs/2604-rewrite/` 全套设计文档后，提出核心诉求：

- **各个模块不要全部自研**，系统性寻找成熟、活跃的现成库/工具替代手写实现（`battle-tested-over-hand-rolled`）。
- **发往上游的请求封装采用 SDK**。
- 判断标准是 `long-term-wins` + `against-yagni-on-feature`：**「保留自研」必须有正当理由，不能因为「现在能跑」就搁置正确的长期改动；反过来，也不为「省事/赶时髦」硬塞不匹配的库。** 两个方向都要对用户负责。

这不是「能少写代码就少写」，而是「**该借力的借力、该自研的讲清楚为什么**」。

## 2. 已确立、无需重验的事实基础

- **上游端点由数据驱动路由**：`refs/available_models.json` 每个模型带 `supported_endpoints` 字段。真实取值：Claude 全系 `/v1/messages,/chat/completions`；gpt-5.5/5.6 全系 `/responses,ws:/responses`（**无 `/chat/completions`**——「无脑压成 chat」会直接 400）；gpt-5.4 三者皆有；gemini `/chat/completions`。共 4 种端点值、6 种组合。**「按 `supported_endpoints` 选上游端点」是数据事实，不需要再 PoC 后端格式。**
- **上游是三/四链路，不是单一 chat**：`UpstreamTarget` 定义 `send_openai()`/`send_anthropic()`/`send_responses()`/`fetch_models()`（见 [project-structure.md:444](../project-structure.md#L444)、端点决策见 [model-resolution.md:195-208](../model-resolution.md#L195-L208)）。
- **上游传输可用 SDK 底层直通（已 PoC 证实）**：`AsyncOpenAI` / `AsyncAnthropic` 可用 `client.post(path, cast_to=httpx.Response, stream=True, body=..., options={"headers":...})` 拿原始 SSE 字节零缓冲直通，注入自定义 header + 扩展 body 字段。实验在 [exp/upstream-sdk-passthrough/](../../../exp/upstream-sdk-passthrough/)（实测 `is_stream_consumed==False` + chunk 到达间隔吻合发送间隔）。域1 已从源码层面确认该结论对 `/v1/messages`、`/responses` 两条链路同样成立（两 SDK 同出 Stainless、`cast_to==httpx.Response` 短路点逐行一致）。
- **同协议 vs 跨协议，传输策略不同**：同协议链路（anthropic 入→anthropic 出等）响应侧可字节直通；**跨协议链路（如 Claude Code 从 anthropic 端点进、目标 gpt-5.5 → responses 出）响应侧不能字节直通**，必须逐 SSE 事件解析→翻译→逐帧写出（走 `transform/translator.py` + `streaming/translator.py`）。

## 3. 六域调研结论速览

六份完整报告：[domain1-llm-sdk](domain1-llm-sdk.md) · [domain2-reliability](domain2-reliability.md) · [domain3-streaming-sse-ws](domain3-streaming-sse-ws.md) · [domain4-storage-config](domain4-storage-config.md) · [domain5-observability](domain5-observability.md) · [domain6-hot-path-foundations](domain6-hot-path-foundations.md)。共享背景见 [_briefing.md](_briefing.md)。

**核验状态**：域1 的 SDK raw-stream 路径、SDK 默认隐式重试，域5 的 OTel 版本矩阵、HTTPX stream 透传与 Prometheus pull reader，以及域6候选的 PyPI/Python 3.14 兼容性均已由主会话独立核验。已纠正两项 agent 误报：`httpx-retries` 并未删除；OTel HTTPX instrumentation 自身并未显式锁定 `opentelemetry-sdk~=1.39.1`。

### 推荐「换库 / 借库」（收益明确）

| 模块 | 推荐库 | 动作 | 出处 |
|---|---|---|---|
| `config/paths.py` XDG 路径 | `platformdirs` | 直接替换手写平台分支 | 域4 |
| `observability/logging.py` 结构化日志 | `structlog` | 接管日志管线 + request_id contextvars 传播（固定宽度前缀仍需自定义 processor） | 域5 |
| `observability/tracing.py` OTel 埋点 | `opentelemetry-instrumentation-{fastapi,httpx}` | 零手写 span，自动埋点（httpx transport 已确认不缓冲 stream、不违反 P6） | 域5 |
| `observability/telemetry.py` + `routes/metrics.py` 指标 | OTel Metrics API + `PrometheusMetricReader` | 删掉手写内存计数器双写，单一数据源 | 域5 |
| `observability/tui.py` TUI | `textual` | 渲染循环/布局/按键交给库，保留纯 reducer | 域5 |
| 上游侧 WS 客户端（代理→上游 `ws:/responses`） | `httpx_ws` | 采用（接受同一 `httpx.AsyncClient`，避免双套连接配置） | 域3 |
| `streaming/sse.py` 出站 SSE 构建 | `sse-starlette` | 部分替换（借响应构建+断连检测；keepalive `empty_text` 帧仍自研） | 域3 |
| 上游三链路请求封装 | `openai` / `anthropic` SDK 底层 `client.post` | 采纳（typed 构造 + 原始字节直通） | 域1 + PoC |
| `cli.py` | `typer` | 推荐迁移（长期收益，建议排为独立阶段，非阻塞） | 域4 |
| wire JSON 热路径 | `orjson` | 采用内部 codec 边界，逐帧返回 bytes；低频可读 JSON 仍用标准库 | 域6 |
| 本地 token 估算 | `tiktoken` `o200k_base` | 采用，startup 预载并为离线部署预热 cache；精确 count 默认走上游 | 域6 |

### 推荐「保留自研」（有正当理由，非偷懒）

| 模块 | 为什么不换库 | 出处 |
|---|---|---|
| 重试策略框架（`pipeline/strategies/*`） | 是「读错误→改写 payload→换调用重试」的**自愈语义** + 跨策略共享预算 + 学习回调；tenacity 官方的「改写参数」方案就是手写 `for Retrying(...)`，与现有结构同构，套库不省代码（可借退避公式） | 域2 |
| 自适应限流器（`rate_limiter.py`） | 是「消费上游 429/503 反馈的三态状态机」，通用限流库都是「客户端固定速率」，问题域不同 | 域2 |
| feature_negotiation（多类别学习缓存） | 本质是领域知识库（per-entry 元数据/pin/迁移/类别化 TTL/管理 API），TTL 只是一维，通用缓存覆盖不到 | 域2 |
| L3 thinking quarantine | 需「命中即续期」滑动 TTL，`cachetools.TTLCache` 是固定过期；`cacheout` 已停摆 | 域2 |
| 异步 SQLite writer（`history/sqlite/*`） | 现设计 `asyncio.to_thread` + 有界 `asyncio.Queue` 已满足 P1 且有背压/丢弃；`aiosqlite` 无背压、`sqlalchemy` 连接池与「单 writer 免锁」冲突、schema 极简不值 ORM | 域4 |
| 上游 SSE **解析**（累积器） | `httpx-sse` 只产出解析后事件、无原始字节旁路钩子，会逼成「解析→重编码」破坏保真度（**唯一被判定威胁硬约束的候选**） | 域3 |
| keepalive/delayed_commit/buffered_retry | 深度耦合本项目协议语义与业务编排，无通用库覆盖 | 域3 |
| 跨协议翻译本体（translator） | litellm/any-llm 都是「统一调用层」非「纯转换层」，无法脱离其执行链路只借转换；当前 litellm 1.92.0 还显式要求 Python `<3.14`，且即便未来解除版本限制，其庞大调用框架仍与自建 pipeline 控制流冲突——两个理由任一成立都不采用 | 域1 |

## 4. 已完成的跨域架构裁决

权威决定与未采用方案统一维护在 [SELECTIONS 第 4 节](SELECTIONS.md#4-用户已裁决的架构决策)。用户选择：有限采用 AnyIO；接受默认关闭的 OTel beta instrumentation；OTel context 权威并单向注入 structlog；使用 pydantic-settings 内置 YAML/CLI source + 自定义 merge；token-limit cache 使用 24 小时 TTL 且 key 仅按规范化 model；Prometheus 复用 FastAPI `/metrics`。CLI 已收敛为从目标实现起直接采用 Typer。

## 5. 原覆盖缺口（已由域6补齐）

分域时按模块地图切了 5 个域，以下自研点原本不在任何一域范围内，现已在 [domain6-hot-path-foundations](domain6-hot-path-foundations.md) 完成调研：

| 优先级 | 自研点 | 候选方向 |
|---|---|---|
| 高 | **JSON 序列化**（数据模型 + 流式每帧热路径，直接关联 P6/P7） | `orjson` / `msgspec` |
| 中 | tokenizer / token 计数（`anthropic/token_counting.py`，capabilities 的 `o200k_base`） | `tiktoken` / `tokenizers` |
| 中 | 网络层重试（httpx transport 级，与域2 的「内容自愈型重试」不同层） | `httpx-retries` / httpx 内建 transport retries |
| 低 | KMP 重复检测（`repetition_detector.py`） | 是否有成熟串匹配库替代 |
| 低 | tokenization estimator/calibration（历史截断已删除） | `tiktoken` + 自研 calibration |
| 低 | sanitize 管道 / JSON schema 校验 | — |
| 低 | 优雅关闭（`shutdown.py` 4 阶段 + 信号） | uvicorn 内建 / `anyio` |

（此清单是接手会话对 [project-structure.md](../project-structure.md) 模块地图与最初五域调研范围做差集得出，现已成为域6调研范围。）

## 6. 下一步建议（推荐顺序）

1. ~~抽验关键断言~~：已完成。
2. ~~补齐 §5 覆盖缺口~~：已完成，见域6。
3. ~~发起对抗评审~~：已完成两轮，最终无 blocker/major，记录见 [260715-selections-review-01-claude](260715-selections-review-01-claude.md)。
4. ~~收敛跨域决策~~：用户已完成 D1～D6 裁决。
5. **进入 planning**：交 `planner` 转成分阶段 TDD 实施计划。

## 7. 关键约束（贯穿始终，勿忘）

- **P1 off-event-loop**：所有 SQLite/磁盘 I/O 不落请求热路径。
- **P6 零缓冲直通**：SSE 逐事件转发，不缓冲完整响应；任何强制整体缓冲的库/用法淘汰。
- **保真度**：SSE 未知字段/未知块（thinking signature、server_tool 块）不能被库吞掉或重编码破坏。
- **单一 retry owner**：SDK、HTTP transport、业务 pipeline 不能各自隐式重试；每次实际上游调用必须进入统一预算、attempt 审计、限流反馈和可观测性。
- **别用 YAGNI/ROI 砍功能**：「保留自研」和「换库」都必须给出对用户负责的理由；不确定就交用户裁决，不静默缩范围（`no-silently-cut-but-defer`）。

## 相关产物

- 调研：本目录 `_briefing.md` + `domain1`~`domain5`
- PoC：[exp/upstream-sdk-passthrough/CONCLUSION.md](../../../exp/upstream-sdk-passthrough/CONCLUSION.md)
- 上游端点/协议设计依据：[model-resolution.md](../model-resolution.md) · [anthropic-compat.md](../anthropic-compat.md) · [multi-protocol.md](../multi-protocol.md) · [project-structure.md](../project-structure.md)
