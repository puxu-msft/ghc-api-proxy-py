# 自研实现与成熟第三方库替代审计

> 状态：完成。本文只记录技术选型建议，不改变任何生产代码、测试或依赖。
>
> 查证日期：2026-08-14。

## 结论摘要

- 8 项中，建议**部分换** 1 项：以 `sse-starlette` 条件替换普通 SSE response 包装；必须先跑保真与取消黑盒 PoC。
- 其余 7 项结论为**不换**：它们要么是项目核心领域不变量，要么候选库只覆盖较小的低层原语，套入后仍保留同等复杂度并新增第二 authority。
- 最重要的非依赖改进是收敛 `GenerationRecord` 的非法可构造组合；该问题不能用 FSM 库机械掩盖。
- 所有候选版本均于 2026-08-14 通过 PyPI 或候选官方文档核实，链接位于逐项表格。

## 评估表

下列逐项评估表是本报告的唯一结论明细，保留候选版本、活跃度、语义匹配、迁移代价与风险。

## 与既有 lib-survey 的差异

- **已覆盖且落地一致**：`httpx-sse` 不采用；重试／反馈限流／buffered retry 不采用；SQLite single writer、KMP 精确周期检测均保留自研。这些实现与 `docs/2604-rewrite/lib-survey/SELECTIONS.md:31-46` 一致。
- **已覆盖但落地偏离**：既有结论为条件采用 `sse-starlette` 的普通 response wrapper，但 `pyproject.toml` 与 `uv.lock` 均未列该包，当前仍手写 `StreamingResponse`；既有 error persistence 建议是 `aiofiles`，当前实际用 `anyio.to_thread.run_sync` 加 atomic replace，且源码无 `aiofiles` import。
- **调研之后的新增面**：immutable tokenization snapshots、rolling state／runtime、generation-control UDS、systemd socket activation／notify／systemctl adapter；本报告首次对这些实现作库替代评估。
- **待拍板开放项**：是否授权 `sse-starlette` 的黑盒 PoC 后纳入依赖；是否以受限工厂／discriminated variant 和 transition table 修复 rolling-state 建模债。两者都不是本报告自行决定的架构变更。

## 扫描范围与判据

- 范围为用户指定的 20 个 `src/app` 文件及其调用点；依赖事实读取 `pyproject.toml` 与 `uv.lock`，既有裁决读取 `docs/2604-rewrite/lib-survey/SELECTIONS.md`、`HANDOVER.md` 和相关 domain 报告。
- 规模用 `wc -l`，语法结构用 Python `ast` 统计 class、function、await；表内 `file:line` 指向当前工作树源码。
- 判据是语义而非代码量：保真／提交时机、唯一 retry authority、bounded backpressure、fail-closed schema／deadline、不可变 no-replace 与 CAS、extended SQLite error 分类、并发生命周期与持久化、systemd 协议覆盖和部署依赖。
- 版本与发行／维护资料来自 PyPI JSON 或候选项目官方文档；GitHub 动态页面无法提供日期时，报告明确标注该限制，而不以印象补全。

## 未覆盖面

- 未安装或运行任何候选库，未执行 SSE／FSM PoC、性能 benchmark 或真实 systemd manager 验证；这些需要独立授权和实施时验证。
- 未审计候选库漏洞、许可证兼容性、跨平台行为或现有实现正确性；本报告不是安全／性能审计。
- 未重新评估既有调研已覆盖但不在任务轴线的上游 SDK、WebSocket、OTel、配置、CLI、JSON codec、tokenizer 与 TUI。

## 增量评估（第 1 项：SSE，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| SSE 解析与渲染：`src/app/streaming/sse.py:19-230`（230 行，10 函数／19 `await`）；`openai_sse.py:6-48`（47 行，3 函数）；`delivery/anthropic_sse.py:402-1018`（1,047 行，16 类／71 函数／29 `await`） | [`sse-starlette` 3.4.8](https://pypi.org/project/sse-starlette/3.4.8/)，2026-08-14 核实；[`httpx-sse` 0.4.3](https://pypi.org/project/httpx-sse/0.4.3/)，2026-08-14 核实 | `sse-starlette` 3.4.8 是当前非 yanked 发行版，要求 Python >=3.10；仓库有 436 commits、支持 disconnect 与自定义 ping。`httpx-sse` 0.4.3（2025-10-10）标为 beta，维护面较窄。 | **部分换**：条件采用 `sse-starlette`，不采用 `httpx-sse`。 | `sse-starlette` 只替换普通 `create_sse_response()` 的头部／断连样板（`sse.py:44-62`）；不能替换 `DelayedStartStreamingResponse`（`sse.py:65-230`）的首批次预取、HTTP 错误降级与 accepted／uncertain receipt 语义，也不能替换 Anthropic block 顺序和签名渲染。`httpx-sse` 的唯一消费模型是结构化事件，不能服务原始字节直通；当前同协议路由以 `passthrough_bytes()` 直通，`parse_sse_json()` 只用于跨协议转换，47 行实现已精确处理分块 CR/LF、data 拼接和 `[DONE]`，换库会引入一层事件语义而不消除业务代码。 | 现有 `pyproject.toml`／`uv.lock` 未锁上述两库，且 `sse-starlette` 尚未落地，故与既有选型存在偏离。仅在黑盒 PoC 证明 bytes 不被重编码、headers／断连取消正确且不触及 delayed-start 路径后，添加 `sse-starlette`；保留 `format_sse_event()` 和全部 parser／renderer。风险是库规范化 SSE 帧或同 `StreamingResponse` 的取消时序不同；`httpx-sse` 的风险是未知字段丢失与 beta 依赖。

## 增量评估（第 2 项：重试／退避／限流，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| 反馈式限流：`src/app/pipeline/rate_limiter.py:7-59`（59 行，2 类／5 函数／3 `await`）；有界全响应缓冲：`streaming/buffered_retry.py:6-17`（17 行，1 函数）；SDK transport：`upstream/client.py:20-82`（83 行，1 类／4 函数／2 `await`） | [`tenacity` 9.1.4](https://pypi.org/project/tenacity/9.1.4/)，2026-08-14 核实；[`stamina` 26.1.0](https://pypi.org/project/stamina/26.1.0/)，2026-08-14 核实；[`aiolimiter` 1.2.1](https://pypi.org/project/aiolimiter/1.2.1/)，2026-08-14 核实 | tenacity／stamina 于 2026 年发布、要求 Python >=3.10，活跃；aiolimiter 最新发行是 2024-12-08，仍兼容但发布节奏明显较慢。 | **不换**。 | `AdaptiveRateLimiter` 消费上游 429／503 的 `retry_after`，在 Normal→Rate-limited→Recovering 三态间迁移并以成功数释放 gate（`rate_limiter.py:30-56`）；`aiolimiter` 是预先配置的漏桶速率限制，不能替代反馈状态机。tenacity／stamina 重试同一调用；本项目的 pipeline（既有调研已定）需在错误后改写 payload、共享跨策略预算及审计，套用其 imperative API 仍保留自研循环。`collect_with_limit()` 是仅 17 行的 all-or-nothing、超 cap 立即失败原语，通用 retry 库没有安全地感知“是否已向下游提交”的能力。`upstream/client.py:49-82` 已明确 `max_retries=0`，避免 SDK 成为第二、不可审计 retry owner。 | 引库不会删除核心状态机，反而把 retry authority 分散到 decorator／SDK／pipeline；可能把一次逻辑请求放大为未记录的上游调用，或把流开始后的读取故障错误重放。允许仅借鉴指数退避／抖动公式，不添加这些运行时依赖。既有 `lib-survey` 的“不换”结论与实际落地一致。

## 本轮结构怪味观察

- `src/app/streaming/sse.py:65-230`：职责错位／框架实现复制——`DelayedStartStreamingResponse` 直接重写 Starlette response 生命周期并依赖私有 `starlette._utils.collapse_excgroups`。本轮不修：首包延迟提交和 receipt 语义是产品不变量，先以 `sse-starlette` 黑盒 PoC 判定普通路径能否替换；若采纳，隔离该类为唯一自定义 response。

## 增量评估（第 3 项：原子写与不可变快照，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| 内容寻址快照与 CAS：`tokenization/snapshot_store.py:49-304`（305 行，5 类／18 函数）；状态 replace：`state_store.py:83-113`（114 行，1 类／9 函数／4 `await`）；失败快照：`error_persistence.py:9-29`（29 行，1 类／3 函数） | [`atomicwrites` 1.4.1](https://pypi.org/project/atomicwrites/1.4.1/)，2026-08-14 核实；[`filelock` 3.32.3](https://pypi.org/project/filelock/3.32.3/)，2026-08-14 核实；[`portalocker` 4.1.0](https://pypi.org/project/portalocker/4.1.0/)，2026-08-14 核实 | `atomicwrites` 最后发布于 2022-07-08、仅 sdist，维护停滞；`filelock` 当前稳定版但只解决锁；`portalocker` 4.1.0 于 2026-08-02 发布、活跃，却同样仅提供跨平台锁。 | **不换。** | `atomicwrites` 的 `overwrite=False` 确实以 POSIX `link+unlink` 实现 race-free no-replace，并 fsync 文件和目录；因此不能把它误判为只能 replace。但快照的关键不是这一步，而是内容哈希命名、schema／identity 验证、live-head 单调 revision、canonical compare-and-swap 与 `flock` 临界区（`snapshot_store.py:64-231`），库不能替代。`state_store.py:97-108` 和低频 error sink（`error_persistence.py:22-27`）只需 atomic replace；引入停滞库仅替换少量 stdlib 调用而不减少领域逻辑。`filelock`／`portalocker` 也不能发布文件或表达不可变 object create。 | 采用 `atomicwrites` 会增加已停滞依赖，并把权限、错误时序和 link+unlink 的双名字窗口交给外部实现；更重要的是不得把其 no-replace API 当作快照完整性的证明。保留当前 POSIX 明确 fsync／chmod／hard-link 实现；若未来需要 Windows 支持，另行评估其文件语义而非无验证移植。

## 增量评估（第 4 项：SQLite 写入与并发，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| 单 writer、背压与错误分类：`history/sqlite/writer.py:26-302`（302 行，3 类／27 函数／17 `await`）；DDL：`history/sqlite/schema.py:1-19`（19 行） | [`aiosqlite` 0.22.1](https://pypi.org/project/aiosqlite/0.22.1/)，2026-08-14 核实；[`sqlite-utils` 4.2.1](https://pypi.org/project/sqlite-utils/4.2.1/)，2026-08-14 核实；[`alembic` 1.19.1](https://pypi.org/project/alembic/1.19.1/)，2026-08-14 核实 | aiosqlite 0.22.1 发布于 2025-12-23，是活跃 asyncio bridge；sqlite-utils 4.2.1 与 Alembic 1.19.1 均为当前非 yanked 版本。前者官方定位同步 SQLite utility，后者是 SQLAlchemy migration tool。 | **不换。** | writer 的有界应用队列、mandatory write acknowledgement、discardable 丢弃、单连接、WAL、shutdown 和致命状态是一个完整 ownership 模型（`writer.py:36-69,86-120,232-302`）。aiosqlite 只把每连接工作串行放进内部 shared queue；官方文档未提供应用可控容量、背压或 SQLite error taxonomy，且不会替代 `_is_busy()`／`_is_fatal()` 通过 extended result code 的 primary-code mask 分类（`writer.py:122-131,277-301`）。sqlite-utils 同步且目标是建库／数据操作，不是 writer runtime。当前 schema 仅 1 表＋2 index，Alembic 需要 SQLAlchemy 迁移栈，不能替代这 19 行 DDL。 | 改用 aiosqlite 仍必须在外层保留有界队列、ack、重试及 fatal 分类，额外引入每连接线程／future bridge；把当前分类交给库会失去 `SQLITE_BUSY/LOCKED` 重试与 `IOERR/READONLY/CORRUPT/FULL` fail-fast 的明确契约。未来若产生多版本、可回滚 schema 迁移或跨 DB 需求，再独立评估 Alembic。

## 增量评估（第 5 项：文本重复检测，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| 流式输出末尾未知周期检测：`repetition_detector.py:3-41`（41 行，2 类／2 函数） | [`difflib`（Python 3.14 标准库）](https://docs.python.org/3/library/difflib.html)，2026-08-14 核实；[`RapidFuzz` 3.14.5](https://pypi.org/project/RapidFuzz/3.14.5/)，2026-08-14 核实 | difflib 随 CPython 3.14 维护；RapidFuzz 3.14.5 是当前非 yanked 版、要求 Python >=3.10、C++ 加速且有 Python fallback，但本轮无法从其 GitHub 页面获得可核验的最近 commit 日期。 | **不换。** | 被测对象不是“两个文本是否相似”：每个 `feed()` 把流式输出截为最后 10,000 字符，KMP 前缀函数仅判定**整个当前后缀**能否被未知的最短周期整除，且周期长度及重复次数必须达阈值（`repetition_detector.py:22-40`）。difflib 的 `SequenceMatcher` 面向两序列 diff／相似片段，最坏二次复杂度且 autojunk 会改变语义；RapidFuzz 面向两序列 fuzzy distance／ratio。二者都不直接回答未知周期、会需要另写周期枚举或阈值逻辑。 | 引入库不能删除 KMP，反而会把精确重复检测变为阈值相似度，造成重复漏报／误报及不稳定时延。当前实现小、确定、窗口有界；后续只应在真实性能信号出现时评估“累计增量触发”优化，不能用 fuzzy matching 偷换检测对象。

- `src/app/tokenization/snapshot_store.py:167-210` 与 `src/app/tokenization/state_store.py:97-108`：局部重复——两处都有 temp＋fsync＋replace，但前者还承担 no-replace／directory fsync，后者是可替换状态。处置：本轮不合并；先抽取时必须保留两种发布语义，不能以通用 atomic-replace 消掉不可变 create。

## 增量评估（第 6 项：UDS RPC、framing 与 schema，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| generation control server：`generation_control.py:22-170`（171 行，2 类／8 函数／10 `await`）；client：`generation_control_client.py:17-249`（249 行，4 类／5 函数／8 `await`） | [`grpcio` 1.83.0](https://pypi.org/project/grpcio/1.83.0/)＋[`protobuf` 7.35.1](https://pypi.org/project/protobuf/7.35.1/)，2026-08-14 核实；[`msgspec` 0.21.1](https://pypi.org/project/msgspec/0.21.1/)，2026-08-14 核实；[`jsonrpcserver` 5.0.9](https://pypi.org/project/jsonrpcserver/5.0.9/)／[`jsonrpcclient` 4.0.3](https://pypi.org/project/jsonrpcclient/4.0.3/)，2026-08-14 核实；现有 [`pydantic` 2.13.4](https://pypi.org/project/pydantic/2.13.4/) | grpcio／protobuf 有 2026 年版本并支持 Python 3.14；msgspec 当前非 yanked，但本次 PyPI 响应无法给出其最新发布日期；两 JSON-RPC 库最后稳定发布分别是 2022-09、2023-02，维护停滞。Pydantic 是现有依赖。 | **不换。** | 控制面只有 `status`、长轮询 `wait`、`flush_tokenization` 三个命令（`generation_control.py:119-154`），每连接只允许一条 newline JSON 请求与一条响应。自研已设版本、严格类型／范围／phase 一致性检查、2 秒或调用方 deadline、64 KiB response cap、路径 escape／hash 校验和 socket file lock（`generation_control_client.py:134-248`）。grpc 能提供 UDS、deadline 与 schema，却强制引入 proto、codegen、HTTP/2 framing 与 stub 生命周期，无法替代 receipt identity 校验；msgspec／Pydantic 只解决 JSON decode＋model validation，不提供网络 framing；JSON-RPC 会添加通用 method/id/error 协议，仍需自定义 fail-closed schema。 | 框架化会把个位数固定方法扩成公开 RPC surface，并造成 deadline／错误映射的双重 authority；JSON-RPC 的停滞维护是额外风险。保持 asyncio UDS＋显式 JSON line；只有控制面演化为跨语言、多流 RPC 或方法数量显著增长时，才以独立 ADR 重新评估 grpc。

## 增量评估（第 7 项：状态机与生命周期，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| 持久 rolling state：`rolling_state.py:15-260`（261 行，4 类／8 函数）；runtime orchestration：`rolling_runtime.py:42-416`（417 行，4 类／26 函数／47 `await`）；并发生命周期：`generation.py:30-329`（329 行，7 类／26 函数／21 `await`） | [`transitions` 0.9.3](https://pypi.org/project/transitions/0.9.3/)，2026-08-14 核实；[`python-statemachine` 3.2.1](https://pypi.org/project/python-statemachine/3.2.1/)，2026-08-14 核实 | transitions 是 MIT 的轻量 FSM，但 PyPI latest 0.9.3 且本次无法从 PyPI 响应取得发布日期；python-statemachine 3.2.1 于 2026-08-01 发布、要求 Python >=3.10，活跃，支持 guards 与 async callbacks。 | **不换，但保留必须偿还的状态建模债。** | 手写的成本真实存在：`GenerationRecord` 的自由字段可在构造期组合出非法 role／phase／ready／accepting／pid，现靠 `RollingStateStore._validate_generation_record()` 事后拒绝（`rolling_state.py:176-214`）；迁移规则也分散于 lifecycle、runtime 和持久校验。两候选可把单对象有限状态与 guard 写成声明图，却不能替代本项目的并发 lock／condition、cancel-safe shield、外部 `systemctl`／socket side effect、失败补偿，或持久 revision/checksum/CAS。尤其 rolling 的 role 与 phase 是复合持久状态，不是一个当前 state 字段；库持久化仍须自定义序列化和恢复后验证。 | 强套库会产生“库 FSM + 既有持久 validator + runtime choreography”三处 transition authority，且 async callback 的取消／部分副作用失败很难由库 transaction 化。推荐的后续改进不是立即加依赖，而是将合法 `GenerationRecord` 构造收敛到受限工厂／discriminated variant，并抽出可审计 transition table；若随后确认纯状态规则能同运行时编排分离，再以 PoC 比较 python-statemachine。

## 增量评估（第 8 项：systemd 集成，2026-08-14）

| 自研面（file:line，行数） | 候选库（名称＋版本＋核实日期＋URL） | 维护活跃度 | 结论（换／不换／部分换） | 理由 | 迁移代价与风险 |
| --- | --- | --- | --- | --- | --- |
| notify：`systemd_notify.py:11-45`（46 行，1 类／3 函数）；socket activation：`socket_activation.py:31-157`（157 行，4 类／7 函数）；unit CLI adapter：`systemctl_adapter.py:12-82`（82 行，3 类／7 函数／6 `await`） | [`cysystemd` 2.0.5](https://pypi.org/project/cysystemd/2.0.5/)，[`sdnotify` 0.3.2](https://pypi.org/project/sdnotify/0.3.2/)，[`pystemd` 0.15.3](https://pypi.org/project/pystemd/0.15.3/)，均于 2026-08-14 核实 | cysystemd 2.0.5 于 2026-03-04 发布但为 Cython／libsystemd wrapper；pystemd 0.15.3 于 2026-01-15 发布、仅 source archive；sdnotify 最后发布于 2017-08-02，停滞。pystemd 宣称同时提供 notify 和 `listen_fds`；cysystemd 的可核验资料只覆盖 daemon notify。 | **不换。** | 这不是一个“少发两条消息”的封装：当前 notify 严格实现 `NOTIFY_SOCKET` 的 filesystem 与 `@` abstract Unix datagram 两种路径（`systemd_notify.py:11-37`）；activation 严格核对 `LISTEN_PID/FDS/FDNAMES`、fd=3 起点、名称、地址、family、listener 状态，并消费环境变量（`socket_activation.py:62-125`）；adapter 则以受限参数调用 `systemctl` 并读取运行时 UnitStatus（`systemctl_adapter.py:27-82`）。对应 systemd 协议本身极小而稳定，Python stdlib `socket` 已完整覆盖。 | cysystemd／pystemd 添加 native build／libsystemd ABI 与部署依赖，却仍无法替代本项目 listener identity 安全校验、generation 命名和受限 systemctl action；sdnotify 停滞且其公开资料不足以确认对本项目 filesystem＋abstract 两路径及 socket activation 的完整覆盖。保留纯 Python 实现与现有两路径测试。若未来需要 journal reader／watchdog／D-Bus manager，才为该新增需求分别评估 bindings。

- `src/app/rolling_state.py:16-29`：非法状态可构造——扁平 `GenerationRecord` 字段允许 role、phase、ready、accepting、pid 的不合法组合。处置：记入待决架构改进，不在本轮以 FSM 依赖替换；应由主会话决定受限工厂／discriminated variant 与 transition table 的持久化格式影响。
