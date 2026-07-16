# TODO_CURRENT — 当前开发计划

> **粒度**：模块划分级（第一版，暂不含实现细节）。每阶段展开的接口契约 / TDD 计划 / kickoff prompt 后续落到 `docs/2604-rewrite/plan/`。
> **依据**：[DESIGN.md](docs/2604-rewrite/DESIGN.md)（性能原则 P1–P8、模块树、状态标注）、[ROADMAP.md](docs/2604-rewrite/ROADMAP.md)、[BACKLOG.md](docs/2604-rewrite/BACKLOG.md)。
> **排序原则**：依赖倒序（叶子先行）+ 尽早打通端到端"走通骨架"+ 按里程碑分层价值。

## 依赖主线

```
config / models / errors
    → auth / upstream
        → pipeline 骨架 + anthropic 直连（首个端到端）
            → 横向铺开协议与深度（OpenAI、Anthropic 深度）
                → 纵向加固（韧性、历史可观测、审批）
                    → 多协议扩展（Azure、Gemini）
                        → 可选能力（BACKLOG）
```

**可并行支线**（Phase 4 之后）：Phase 5（韧性）与 Phase 6（历史可观测）依赖面不重叠，可并行；Phase 7 / 8 相互独立。

---

## Phase 0 — 项目骨架与基础设施

> 目标：能启动空壳服务、有配置、有日志、有健康检查。为后续一切提供地基。

- [x] `config/`（settings / loader / paths / compat）—— frozen Pydantic Settings、四层合并、跨平台路径
- [x] `models/`（common / capabilities）—— 叶子数据模型：Usage、ModelInfo、ErrorResponse、能力元数据
- [x] `errors.py` —— 错误分类、wire format 检测、格式化错误响应
- [x] `observability/`（logging 骨架）—— 结构化日志、固定宽度前缀
- [x] `server.py` / `deps.py` / `cli.py`（骨架）—— 应用工厂、分阶段 lifespan 空实现、DI 提供者、Typer
- [x] `routes/health.py` —— `/health`、`/health/liveness`、`/health/readiness`
- [x] `wire_json.py` —— 集中式 orjson wire codec、差异与边界策略测试

**完成记录（2026-07-15）**：Python 3.14.2 下 65 个测试通过，覆盖率 92.87%，Ruff 与 Pyright strict 通过；真实 uvicorn 动态端口启动、配置生成、liveness 和 SIGTERM 关闭均通过；独立 reviewer 为 0 blocker / 0 major，所报配置路径与合并策略问题已修复。

**里程碑**：服务可启动、可配置、可观测。

## Phase 1 — 上游连接与认证

> 目标：能拿到 Copilot token、能向上游发出一个裸请求。

- [x] `auth/`（providers / github / copilot / device_flow）—— Token provider 链、Copilot token 交换与刷新
- [x] `upstream/`（base / client / copilot / generic）—— UpstreamTarget 协议、httpx 客户端封装、请求头伪装
- [x] `upstream/models_api.py` —— 模型列表获取、缓存、定期刷新、O(1) 索引
- [x] `transform/model_resolver.py` —— 模型名解析（别名 / 标准化 / Override / Family）

**完成记录（2026-07-15）**：130 个测试通过；CLI/env/file token provider、显式 Device Flow、Copilot token single-flight 与有限重试、结构化后台刷新、SDK/transport 零重试、raw response passthrough、账户类型推断、模型目录 ETag/保真/O(1) 索引与模型 resolver 已完成。独立 review/verifier 报告的问题均已复核并修复，最终进入 Phase 2。

**里程碑**：认证打通、模型列表可用、模型名可解析。

## Phase 2 — 核心管道最小闭环（Walking Skeleton）

> 目标：**第一个端到端可用请求**——`/v1/messages` 直连 Copilot、SSE 流式直通。全项目最重要的验证点。

- [x] `models/anthropic.py` —— Anthropic 请求 / 响应 / SSE 模型
- [x] `streaming/`（sse / idle_timeout / accumulator 接口）—— SSE 零缓冲直通、流空闲超时
- [x] `anthropic/client.py` + `anthropic/sanitize/`（最小：tool 配对 + 空块）—— Anthropic 客户端 + 基础清洗
- [x] `anthropic/token_counting.py` —— `count_tokens`（上游转发 / 本地估算），支撑本阶段的 count_tokens 路由
- [x] `pipeline/`（context / executor 最小版）—— 请求生命周期、执行循环（限流 / 审批为空实现直通，重试策略留待 Phase 5）
- [x] `routes/anthropic.py` —— `/v1/messages`、`/v1/messages/count_tokens`

**完成记录（2026-07-15）**：154 个测试通过，Ruff/Pyright strict 通过；深层未知字段/null 保真、基础 sanitizer、SDK raw stream、SSE 零缓冲与确定性关闭、per-model idle timeout、上游优先 token counting、最小 pipeline 和 Anthropic HTTP 路由均通过独立 review/verifier，最终 0 blocker / 0 major。

**里程碑**：Claude Code 能连上、能对话、能流式。

## Phase 3 — OpenAI 协议族

> 目标：补齐 OpenAI 三端点 + 跨格式翻译。

- [x] `models/openai.py` —— Chat Completions + Responses 模型
- [x] `openai/`（client / responses_client / **responses_conversion** / embeddings / sanitize / accumulators）—— 三个 OpenAI 客户端 + 清洗 + 累积器；`responses_conversion` 承载 `call_` → `fc_` 标准化
- [x] `transform/translator.py` —— 跨协议**非流式**格式翻译
- [x] `transform/system_prompt.py` —— 系统提示词定制（prepend/append/regex，按 model/endpoint 限定作用域）；跨协议共用，被 Phase 4 请求准备调用
- [x] `streaming/translator.py` —— 跨格式**流式**翻译（Chat ↔ Anthropic ↔ Responses ↔ Gemini），与非流式 translator 不同粒度
- [x] `routes/openai.py` / `routes/responses_ws.py` —— chat/completions、models、embeddings、responses（含 httpx-ws）
- [x] `routes/management.py` —— status/config/event_logging 与静默浏览器探针

**完成记录（2026-07-15）**：184 个测试通过，覆盖率 91.55%，Ruff/Pyright strict 通过；OpenAI 深层保真、Chat/Responses/Embeddings、三重前缀、跨协议翻译、sanitizer/accumulators、正式 httpx-ws 上游 transport、bounded queue 和管理端点均通过多轮独立评审，最终 0 blocker / 0 major。

**里程碑**：OpenAI 生态客户端（Cursor 等）可用。

## Phase 4 — Anthropic 深度兼容

> 目标：把 Anthropic 路径做深做正确。价值密度最高、也是上游最复杂的部分。

- [x] `anthropic/sanitize/`（完整 2 阶段）—— 基础清洗、reminder/read tags、tool pair 去重
- [x] `anthropic/thinking/` —— 块级保护 / destack / L2 剥离 / **L3 内存隔离** / signature 兼容
- [x] `anthropic/features.py` + `feature_negotiation.py` —— 特性检测 + beta headers + 11 类学习缓存（内存）
- [x] `anthropic/message_tools.py` + `server_tool_filter.py` —— tool_search/defer_loading 与 server tool 过滤
- [x] `anthropic/header_policy/` —— 请求 / 响应头转发安全
- [x] `anthropic/warmup.py` —— Warmup 策略及路由短路
- [x] `anthropic/request_preparation.py` —— 请求准备编排并接入生产 client

**完成记录（2026-07-15）**：205 个测试通过，Ruff/Pyright strict 通过；Thinking、11 类协商缓存、工具预处理、header floor、warmup、深度 sanitizer 与 preparation 生产接线经两轮独立评审，最终 0 blocker / 0 major。L2/L3 的反应式重试闭环按计划归 Phase 5。

**里程碑**：Anthropic 路径**机制完整**——保护 / destack / 剥离函数 / 隔离数据结构 / 特性协商 / cache / header 转发 / warmup 均单元可测。注意：thinking 拒绝场景的**自动降级重试（L2/L3 行为闭环）**依赖 Phase 5 的 `poisoned_thinking` 策略接入重试循环后才端到端可用——本阶段止于"机制就绪、单元可测"，非"拒绝场景端到端可用"。

## Phase 5 — 韧性与重试

> 目标：容错、限流、优雅关闭。让代理"扛得住"。（可与 Phase 6 并行）

- [x] `pipeline/strategies/` —— single-owner coordinator 与 poisoned-thinking L2/L3 行为闭环
- [x] `pipeline/rate_limiter.py` —— 自适应三模式限流与 retry deadline 自愈
- [x] `auto_truncate/` —— 截断 engine + normalized model 24h token 限制缓存
- [x] `streaming/`（keepalive / delayed_commit / buffered_retry）—— 结构化 keepalive、延迟首帧与 opt-in 有界缓冲
- [x] `pipeline/manager.py` + `context/`（consumers / error_persistence）—— active/stale 管理、观察者、off-loop 原子错误持久化
- [x] `shutdown.py` + `repetition_detector.py` —— 4 阶段异步回调关闭、KMP 重复检测

**完成记录（2026-07-15）**：218 个测试通过，Ruff/Pyright strict 通过；429 limiter feedback、single-owner retry、Thinking L2/L3、KMP、token cache、stream resilience、context consumers 与 shutdown 经两轮独立评审，最终 0 blocker / 0 major。

**里程碑**：长时运行稳定、优雅关闭、限流自愈；thinking L2/L3 端到端可用。

## Phase 6 — 历史与可观测性

> 目标：审计、监控、运维面板。（可与 Phase 5 并行——`history/` 作为 HistorySink 订阅 `context/` 事件，`context/` 不反向依赖 `history/`，依赖面不重叠）

- [ ] `history/`（store / sqlite / in_flight / sessions / ws / types）—— 异步 SQLite（off-loop writer）+ 双源 + 分桶 reaper + WS
- [ ] `observability/`（tracing / telemetry / middleware）—— OpenTelemetry、轻量遥测、`/metrics`
- [ ] `routes/history.py` / `routes/management.py` / `routes/metrics.py` —— History REST/WS、`/api/*` 管理、Prometheus
- [ ] `observability/tui.py` —— Textual 终端 UI

**里程碑**：完整审计 + 可观测。

## Phase 7 — 手动审批（本项目独有）

- [ ] `pipeline/approval.py` + `routes/approval.py` —— AnyIO 取消/超时作用域门控、审批 REST/WS（**复用** Phase 6 的 `history/ws.py` WebSocketManager，不另造广播）

## Phase 8 — 多协议扩展

> 各适配层**复用** Phase 3（openai 客户端 / 清洗）与 Phase 4（anthropic 深度能力）的实现，不重新造轮子。

- [ ] `models/gemini.py` —— Gemini 模型
- [ ] `protocols/azure.py` + `routes/azure.py` —— Azure deployment 经典 + v1
- [ ] `protocols/gemini.py` + `routes/gemini.py` —— Gemini `/v1beta`（流式复用 `streaming/translator.py`）

## Phase 9 — 可选能力（BACKLOG，按需）

- [ ] 分层归档、FTS5 全文搜索、分层遥测、块级缓冲重试等 —— 均 `[缓存/延后]`，仅在明确需求时启动。详见 [BACKLOG.md](docs/2604-rewrite/BACKLOG.md)。

---

## 关键切分决策（评审后已确认）

1. **Phase 2 用「Anthropic 直连」作为首个端到端骨架**（而非 OpenAI）—— 因它是默认主路径、不涉及格式翻译，验证最直接。✓ 成立
2. **韧性（Phase 5）放在协议铺开之后、历史之前** —— 先把两条协议主路径走正确，再纵向加固。✓ 成立；Phase 4 里程碑已修正为"机制完整、单元可测"，thinking L2/L3 的行为闭环归 Phase 5。
3. **Phase 5 与 Phase 6 可并行** —— ✓ 成立。已核实并修正设计文档：`history/` 依赖 `context/`（订阅事件），`context/` 不反向依赖 `history/`，依赖面不重叠。

## 建议（可选）

- **更早的走通验证**：Phase 1 的 `auth/`（含 device flow OAuth）复杂度较高。可在接入真实 Copilot 认证前，先用 `upstream/generic.py` + 本地 mock/echo 上游验证 `pipeline/executor` + `streaming/sse` + `routes/anthropic` 骨架能转发一个假流式响应，缩短"验证 pipeline 本身"的反馈回路。

## 评审记录

- 2026-04：GPT reviewer 对本 plan 做模块划分级评审——0 阻断。已解决：补全遗漏模块（`token_counting`、`streaming/translator`、`transform/system_prompt`、`responses_conversion`、`context/consumers`）、修正 Phase 4 里程碑表述、澄清 Phase 2 executor 空实现、声明 Phase 7/8 复用关系。同步修正设计文档两处：`context/`↔`history/` 依赖方向、`system_prompt.py` 去重（合并到 `transform/system_prompt.py`）。
