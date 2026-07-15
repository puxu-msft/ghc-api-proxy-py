# Backlog（可选能力储备）

> 本文档记录**上游参考项目实现了、但因性能/复杂度成本，本项目默认不实现或列为可选**的重能力。每项说明：上游怎么做、性能问题、本项目的默认方案、以及若将来确需该能力的可选实现路径。
>
> 参见 [DESIGN.md 性能设计原则](DESIGN.md#性能设计原则第一优先级)（P1–P8）。

## 1. 分层降温归档（HOT → tier1 → tier2）`[缓存/延后]`

**上游做法**：三层 SQLite。HOT（`history.db`，近 3 天）→ tier1（`archive.db`，列式压缩，per-session `archive-t1-*.db`）→ tier2（`archive-t2-*.db`，整 session 封存，列式转置 + zstd **L19 + 16MB 窗口**，~9× 压缩）。迁移用"copy→verify→delete"两阶段事务，配合孤儿 GC、增量 vacuum、启动期后台 compact。产品面"永不真删"。

**性能问题**（见 P2/P3）：
- zstd L19 + windowLog=24 CPU 开销巨大
- 列式转置 + per-session 封存 + 迁移 verify + 多表孤儿 GC，后台开销与代码复杂度极高
- 大量边界情况（崩溃恢复、跨文件原子性、WAL checkpoint）

**本项目默认**：单层 SQLite（`history.db`）+ 按 `success_limit`/`failure_limit` 分桶行数上限的简单 reaper（删最旧）。zstd **level 3** 压缩 payload（线程池执行）。满足"最近 N 条可查"的核心需求。

**可选实现路径**（若确需"永不删除 + 冷归档"）：
- 保留单层 + 一个可选的"归档到 Parquet/DuckDB 文件"后台任务（比手搓列式 SQLite 更省心、查询更快）
- 或对接外部存储（S3 / ClickHouse），把冷数据搬出进程
- 关键：归档**永远后台、可关闭、不在请求路径**

## 2. 内容寻址去重全文搜索 `[缓存/延后]`

**上游做法**：`msg_blob(hash, text)` 按内容哈希去重存每条消息（~42× 去重），`req_msg` / `req_aux` 关联表，`history_meta` 账本，后台可恢复 backfill（keyset 续跑），5 个搜索 facet。取代了旧的 trigram FTS5。

**性能问题**（见 P4）：每条消息归一化 + 哈希 + 多表写入 + 后台 backfill，构建成本高；写放大明显。

**本项目默认**：查询走 SQL 列过滤（model / endpoint / status / 时间范围）+ 对 preview_text 的简单 `LIKE`。不建全文索引、不做去重。

**可选实现路径**（若确需全文搜索）：
- 优先用 SQLite 内置 **FTS5**（成熟、C 实现、无需手搓内容寻址），仅对 preview/文本列建虚拟表
- 内容寻址去重仅在"存储成本成为瓶颈"时才考虑，且作为独立后台压缩任务

## 3. 分层遥测（DDSketch + raw/hourly/daily）`[简化]`

**上游做法**：`request-telemetry.ts`（~90KB）维度化计数器 + DDSketch 直方图 + 三层 SQLite 存储（raw 5min/7d、hourly/90d、daily）+ 基数上限 + rollup + cumulative tier + 一次性 JSON backfill。

**性能问题**：热路径维度化累加 + 直方图更新 + 周期 rollup；存储与代码复杂度高。

**本项目默认**：轻量内存计数器（model / endpoint / status / tokens / reasoning_tokens）+ **OpenTelemetry** 导出（把直方图/聚合/存储交给成熟的 OTel collector 后端，而非自建 SQLite 分层）。`/metrics` 暴露 Prometheus 文本。

**可选实现路径**：若需进程内长期留存趋势，用 OpenTelemetry Metrics + 外部 TSDB（Prometheus / VictoriaMetrics），不自建 SQLite 遥测层。

## 4. client/upstream 双腿数据模型 + 多 stage 持久化 `[简化]`

**上游做法**：每 entry 含 `clientRequest` / `clientResponse` / per-attempt `upstreamRequest` / `upstreamResponse` / `sseEvents` / `_index.derived`（重算派生）/ `_index.aux` 等，多 stage 增量写盘（eager head → 每转换 → 每 attempt → finalize），legacy stage 读时适配。

**性能问题**（见 P7）：每请求重对象图、多次投影重算、多次事务写盘。

**本项目默认**：轻量 `dataclass` 记录关键字段（request/response payload、attempts 摘要、usage、timing）。终态**一次性**异步落盘（off-loop），不做增量 multi-stage 写入。进行中状态留在内存 in-flight 映射供 WebSocket。惰性构造摘要，不预算所有派生字段。

**可选实现路径**：若需完整的每-attempt 审计，增加一个可选的"详细模式"，但仍终态一次写入。

## 5. 三重前缀路由注册 `[采纳但简化]`

**上游做法**：每个 OpenAI 端点在 `/`、`/v1`、`/openai/v1` 三处注册。

**本项目**：用 FastAPI 的单一 router + 多 `path` 挂载或 `APIRouter(prefix=...)` 循环注册，避免重复 handler 定义。功能等价，代码不重复。

## 6. 大量配置 compat 迁移层 `[简化]`

**上游做法**：`config/compat.ts` 维护长串的 `CONFIG_MIGRATIONS`（renameLeaf / removeKey / warn-and-continue），承载多轮键改名历史。

**本项目**：本项目是全新实现，**无历史包袱**——直接采用上游"改对了之后"的最终键名，只保留一个精简的 `compat.py` 处理明显的常见别名（如 `history.limit` → success/failure）。不背上游的迁移债。

## 参见

- [ROADMAP.md](ROADMAP.md) — 里程碑与暂缓能力
- [DESIGN.md](DESIGN.md) — 性能设计原则（P1–P8）
- [history-system.md](history-system.md) — 历史存储的默认（精简）设计
- [telemetry-observability.md](telemetry-observability.md) — 可观测性的默认设计
