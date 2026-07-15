# Roadmap（路线图）

> 本文档记录**借鉴自上游参考项目、但本项目有意暂缓或分期**的能力，以及里程碑规划。状态标注见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。
>
> 核心立场：本项目**不原样复刻上游**。上游性能负担重、过度工程多。这里记录的是"其解决的真实问题值得关注，但落地方式需在 Python 中重新设计、或时机未到"。

## 里程碑

### M1 — 核心代理（MVP）

目标：可用的高性能双协议代理。

- OpenAI（Chat Completions / Responses / Embeddings / Models）+ Anthropic（Messages / Count Tokens）端点
- 模型解析（别名 / 标准化 / Override / Family）
- Anthropic 直连 Copilot + 请求准备（wire payload / thinking budget / cache control `passthrough`）
- 2 阶段消息清洗 + tool 配对修复
- 请求管道：清洗 → 限流 → 执行 → 重试（network / token_refresh / auto_truncate / orphan_cleanup）
- SSE 流式直通 + 流空闲超时 + 重复检测
- Token provider 链（CLI / env / file / device-auth）
- 结构化日志 + 健康检查（liveness / readiness）
- 配置系统（四层合并 + 热重载）

### M2 — Anthropic 深度兼容

- Feature negotiation（多类别学习缓存 + TTL）
- Thinking-block 处理管道：块级保护 / destack / L2 剥离 / **L3 内存隔离**（非上游的磁盘 sidecar，见 P5）
- Context Editing（clear-thinking / clear-tooluse / clear-both）
- Cache control 全模式（disabled / passthrough / sanitize / proxied）
- Tool Search 注入 + deferred loading + per-model 覆盖 + CC 官方工具注入
- 请求/响应头转发安全（blacklist / whitelist + security floor + 归属头剥离）
- Warmup 策略（allow / reject / drop / fake）
- Server tool 结果过滤（响应侧常驻 + 块索引重映射）

### M3 — 韧性与运维

- 4 阶段优雅关闭 + 信号升级
- RequestContextManager + stale reaper + hard request deadline
- 错误持久化消费者
- 流式韧性：延迟提交窗口 + keepalive 心跳（empty_text anchor）
- 自适应限流 3 模式
- 请求历史（异步 SQLite off-loop）+ REST + WebSocket 实时推送
- 管理 API（status / config / tokens / negotiation / logs）
- Prometheus `/metrics` + OpenTelemetry

### M4 — 多协议与增强

- Azure OpenAI 适配（deployment 经典格式 + v1）
- Google Gemini 适配（`/v1beta`）
- 手动审批系统（本项目独有）
- 缓冲重试（opt-in，默认关，见 P6）— Anthropic 整响应级
- 分层遥测（可选）

## 借鉴但暂缓/分期的能力

| 能力 | 上游状态 | 本项目决策 | 理由 |
|------|---------|-----------|------|
| **整响应缓冲重试** | `[上游实验]`（默认关，四端点非对称，块级门控在用户 PoC） | `[采纳，默认关]` M4 | 应对上游 mid-stream RST 的真实价值；但内存开销大（见 P6），严格 opt-in |
| **块级缓冲重试** | `[上游实验]`（handler 接线未启用） | `[缓存/延后]` | 上游自身尚未启用，复杂度高，观望其定论 |
| **优雅重启（零停机换代）** | `[上游未落地]`（"设计（未实现）"，含未解 sd_notify PoC 与多个 overlap bug） | `[缓存/延后]` | 上游都没实现且有已知竞态；Python 侧可用进程管理器（systemd / supervisor）+ SO_REUSEPORT 另行设计 |
| **`enveloped_ping` keepalive** | `[上游实验]`（"预期会超时"） | `[拒绝]` | 上游明确其撑不住 300s；只实现 `empty_text`（有效）+ `ping`（逃生舱） |
| **error-shaping AskUserQuestion 交互** | `[上游实验]`（未实测，headless 无用户可问） | `[缓存/延后]` | 语义不清、价值待验证 |
| **memory tool（server_tool_memory）** | `[上游实验]`（默认关，CAPI 接受度未验证） | `[缓存/延后]` | 上游未验证，观望 |
| **upstream hooks 模块** | `[上游稳定]`（dev/test only） | `[缓存/延后]` | 仅开发期用途，非核心 |
| **分层遥测（DDSketch + raw/hourly/daily）** | `[上游稳定]` | `[简化]` M4 可选 | 见 BACKLOG；默认用轻量计数器 + OpenTelemetry |

## 参见

- [BACKLOG.md](BACKLOG.md) — 上游重能力的可选实现细节（分层归档、全文搜索等）
- [DESIGN.md](DESIGN.md) — 性能设计原则、状态标注约定
