# 《取证记录能力方案（history 增强）》评审

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/agents/history-forensics/proposal.md`

评审基线：当前工作树，`HEAD eb932156d30294c9c809a70ea5a4649d85304eae`，2026-08-20。相关生产文件中 `src/app/server/pipeline_app.py`、`src/app/pipeline/delivery/sse_source.py`、`src/app/observability/request_log.py` 存在未提交改动，因此本报告裁决的是当前工作树，不是仅裁决 `HEAD`。

结论：**needs-fix，不宜按当前版本交给用户裁决。共 6 个 blocker、5 个 major、1 个 minor。** 第一节的大部分接线事实成立，但“每请求恰好一条”“唯一帧解析”“保 chunk 边界”“3.6MB/千条适用于所提 schema”均有反例；第二节又把现有 `HistoryEntry` 与新记录形状的差距估得过小，并且 L2+L3 不足以无推断地导出定义完整的 cassette。

证据强度：以下代码与命令结果均为当前工作树的一手核对，足以据以修改方案；本机可变数据库计数只支持带时间锚点的快照，不支持永久常量。

## 一、必须断言逐条核对

### 1. 生产 import 闭包

**已确认。** `src/app/cli.py:21-22` 导入 `build_chain` 与 `create_pipeline_app`；`src/app/cli.py:138-149`、`:160-169` 两个 serve 入口都创建新链路。当前工作树实测：

- `reachable_from("app.server.pipeline_app")`：111 个 `app.*` 模块，`app.history*` 为空，`app.routes*` 为空，三类边界违规均为空。
- `reachable_from("app.cli")`：125 个 `app.*` 模块，`app.history*` 为空，`app.routes*` 为空，三类边界违规均为空。

这支持“当前生产入口 import 闭包不含 `app.history` / `app.routes.*`”；不支持“仓库里没有其他 SSE/history 实现”。

### 2. 边界断言与 6/6/9/34

**已确认。** `tests/unit/test_module_boundaries.py:24-30` 的新链路禁区恰为：`app.server.app_factory`、`app.pipeline.executor`、所有 `app.routes.*`，没有禁止 `app.history`。命令 `uv run --project /home/xp/src/ghc-api-proxy-py pytest /home/xp/src/ghc-api-proxy-py/tests/unit/test_module_boundaries.py --quiet` 得到 `3 passed`。

用同一个 `reachable_from` 逻辑重跑得到：

| 模块 | 当前闭包大小 | 三类违规 |
|---|---:|---|
| `app.history.types` | 6 | 0 |
| `app.history.sqlite.writer` | 6 | 0 |
| `app.history.store` | 9 | 0 |
| `app.history.consumer` | 34 | 0 |

表 1.2 的四个数字可复现。

### 3. `ProxyConfig.history` 与 CLI 死开关

**已确认，限 `src/app/config/schema.py` 的新配置类型。** `src/app/config/schema.py:198-200` 定义只有 `enabled` 的 `HistoryConfig`，`:309-310` 挂入 `ProxyConfig`；`src/app/cli.py:102-105` 只把 CLI 值写入加载覆盖。对 `src/**/*.py` 做 AST 搜索，`config.history`、`proxy_config.history`、`chain.config.history` 的运行时读取为 0。因此 `--history/--no-history` 当前不改变新生产链路行为。

不要把它与旧链路 `src/app/config/settings.py` 的另一个 `HistoryConfig` 混为一谈；后者确实由 `src/app/server/app_factory.py:72-82` 等处消费。

### 4. `_log_completion` 是否每请求恰好一次

**已推翻。** 见 blocker B2。它有两个调用点，不是三个调用点；普通返回与已经构造出的 streaming response 有完成记录，但 `_dispatch` 抛出的 `BaseException` 路径只清理 active request 后重新抛出，不记录。用独立临时 pytest 探针令 `Request.body()` 抛错，确认请求异常退出且完成日志为 0，探针 `1 passed`。

### 5. `read_events` 是否唯一帧解析

**已收窄。** 在当前生产新链路 import 闭包里，`src/app/pipeline/delivery/sse_source.py:34-52` / `:55-62` / `:64-86` 是唯一 SSE 切帧解析实现，调用链是 `pipeline_app.py:272-282` → `stream.py:45-77` → `read_events`。但全仓并非唯一，见 blocker B3；旧链路至少还有两个独立解析器。

### 6. `debug info` / `debug usage`

**已确认。** `src/app/cli.py:370-373` 与 `:436-439` 都调用 `_not_implemented`；`debug models` 则在 `:390-433` 有完整实现。

### 7. 六个 `on_*` 钩子

**已确认。** 六个键只定义于 `src/app/config/schema.py:202-214`；全 `src/` 搜索没有 `config.hooks` 或 `.hooks.on_*` 消费/触发。`src/app/server/handler.py:80-83` 只在注释中把一个真实时刻对应到 spec 名称。当前真实注册表使用另一套内部事件：`src/app/pipeline/direct_driver/base.py:28-40` 的 `attempt.*` / `request.*`。

### 8. cassette 结构

**已确认文档的结构摘要。** `tests/integration/recorded/cassettes.py:234-257` 的 `Interaction` 必需构造字段为 method、path、authenticated、extensions、source、request_shape、status、headers、chunks；`:208-227` 的 `request_shape` 只保留 model、stream 与规范化完整 body 的 sha256 digest，不保留 body；`:47-53` 的响应头 allowlist 正好是 `content-type`、`transfer-encoding`、`cache-control` 三项；`:96-117` 按任意深度字段名处理；`:131-174` 先拼 SSE，再按原长度占比重切。

需要补充限定：`_request_shape` 对非 JSON/非对象 body 返回空字典；`from_history.py:228-243` 也刻意构造空 `request_shape`。因此“只存 sha256”只适用于可解析为 JSON object 的 live recording，不是每个 Interaction 的强制不变量。

## 二、发现

### B1 — blocker — “旧链路只有所列两类测试调用”是错误的全称事实

证据：方案 `docs/agents/history-forensics/proposal.md:20` 写“只有 `tests/http/*`、`tests/integration/test_server_startup.py` 在用”。实际还有 `tests/smoke/test_anthropic_responses_route.py:26,314`、`tests/smoke/test_anthropic_responses_stream_route.py:28,268` 和 `tests/unit/test_observability_phase6.py:7,49` 直接导入/调用 `create_app`。生产不调用旧链路这一核心结论仍成立，但“只有”必须改成“测试套件调用，例如……”，否则第一节的枚举事实不可信。

### B2 — blocker — `_log_completion` 不是“每请求恰好一条”汇合点，异常退出是未覆盖的第四类

证据：方案 `docs/agents/history-forensics/proposal.md:55`；`src/app/server/pipeline_app.py:102-130` 是定义，真正调用只有 `:165` 与 `:333`。`src/app/server/pipeline_app.py:155-160` 捕获 `_dispatch` 的任意 `BaseException` 时只从 active registry 删除后 `raise`；`:169-171` 的 `await request.body()`、`:289-298` 的 `response.json()`/翻译等非预期异常都能走该路径而跳过两个调用点。未注册 URL 的 FastAPI 404 则按 `:173-176` 明确在代理请求边界外。

独立运行证据：临时 test-only 探针把 `Request.body` 改为抛 `RuntimeError("body read failed")`，请求确实异常退出，`app.request` INFO 完成记录为 0；`uv run ... pytest /tmp/test_history_completion_probe.py --quiet` 得到 `1 passed`。

替代方案：先把“哪些请求算记录对象”写成明确边界。对进入 `_serve` 的请求，外层必须有一个唯一、幂等的 finalize；正常响应、取消、读取 body 异常、未知内部异常都在那里定终态。不要把当前 docstring 当作已经成立的保证。若持久化必须 await，非流式可由 `_serve` 的 `finally` 异步终结；流式可由 `_AccountedStreamingResponse.__call__` 的异步 `finally` 终结，并用异步幂等状态统一 generator 与 response 两个收尾者。

### B3 — blocker — “唯一帧解析”缺少生产闭包限定，而且在 `SseEvent` 处记录不可能保留 chunk 边界

证据：方案 `docs/agents/history-forensics/proposal.md:72-81,112-113`。全仓至少还有：

- `src/app/streaming/openai_sse.py:5-24`：独立按 SSE 空行聚帧并解析 JSON，由 `src/app/routes/gemini.py:29-33` 和 `src/app/delivery/responses_anthropic_stream.py:208` 调用。
- `src/app/streaming/anthropic_usage.py:5-40`：独立用 `\n\n` 切帧并解析 `data:` JSON。

这些实现都在旧链路，当前生产闭包不含它们，所以正确表述是“当前 `create_pipeline_app` 闭包中的唯一解析点”。

更关键的是，`src/app/pipeline/delivery/sse_source.py:71-83` 把任意输入 chunk 缓冲、按帧分割后只产出 `SseEvent(event: str, data: str)`；输入 chunk 边界、注释帧、原换行形式、data 行布局均已丢失。方案表 2.1 声称在该输出处记录 `SseEvent` 又“保 chunk 边界”，二者不可同时成立。

替代方案：若目标是复现 parser 实际收到的块序列和导出高保真 cassette，在 `src/app/server/pipeline_app.py:355-363` 的 `_counted_upstream` 旁路记录每个原始 chunk，再把原样 chunk 继续交给 `read_events`；若只要与旧 `from_history.py` 同等级的“每帧一个 chunk”语义固件，则可记录 `SseEvent`，但必须明确 source 为 frame-derived，并明确它不证明 wire/parser-input chunking。不要把这两种记录合成一个 L3。

### B4 — blocker — “复用 `app.history` 存储层很便宜”与实际类型、schema 和异步接口不符

证据：方案 `docs/agents/history-forensics/proposal.md:117-136,217-218` 说新 recorder 吃 `_Trace`/`RequestLine`，`entries` 只增 digest/authenticated 两列。现有 `HistoryEntry` 在 `src/app/history/types.py:10-24` 强制要求 session_id、agent_id、epoch started_at、endpoint、字符串 status、ModelRef、`request_payload`，可选 response/usage/error/pinned；而 `RequestLine` 在 `src/app/observability/request_log.py:81-109` 持有 method/path、两侧协议、status_code、duration、上下行 bytes、stop_reason、tools、thinking、dialect、attempts、detail，却没有 id、请求 payload 或起止 epoch。`_Trace.started` 在 `src/app/server/pipeline_app.py:81` 是 `time.monotonic()`，不能当 SQLite 的 wall-clock `started_at`。

现有表 `src/app/history/sqlite/schema.py:1-16` 同样没有大多数 L1 字段；`src/app/history/sqlite/writer.py:133-153` 以无列名的 14 个位置参数写整行，`:218-243` 又按固定下标反序列化。只增两列既不能保存“`_Trace` 全部字段”，也会要求同步改写所有 positional SQL/reader 及已有库迁移。

接线也不是直接承接：`_log_completion` 是同步函数（`pipeline_app.py:102`），`HistoryStore.finalize` 是 async（`src/app/history/store.py:28-30`）；唯一同步提交 `HistoryWriter.submit_nowait` 在 `src/app/history/sqlite/writer.py:71-84` 明令只能 `discardable=True`，与“L1 全量常开、唯一答案来源”冲突。

替代方案：保留旧 `HistoryEntry`/`entries` 合同，新增明确的新 DTO 与表，例如 `ForensicRequest`、`UpstreamExchange(attempt_index, ...)`、`UpstreamChunk`；可以复用 SQLite 单 writer/queue 的实现模式，或在确认收益后抽一个通用 writer runner，但不要声称复用现有 `HistoryEntry`/`HistoryStore` 几乎免费。若坚持同一数据库，也应使用独立表而非把异质字段塞进 `request_payload`/`response`。同时把“durable backpressure”与“best-effort drop”列为用户可裁决的真实分叉。

### B5 — blocker — L2+L3 不足以无推断地导出定义完整的 cassette

证据：方案 `docs/agents/history-forensics/proposal.md:110-113,136,146-154`。cassette 的完整 Interaction 合同见 `tests/integration/recorded/cassettes.py:234-290`。按方案已明确保存的字段，只能得到 request body/digest、authenticated、response headers/error body、status/L1 与 frame events；至少没有明确保存：

1. **上游 request method 与 path**。L1 的 `trace.path` 是客户端入站路径（`src/app/server/pipeline_app.py:141-146`），cassette 要的是上游 request path；真实值在 `response.request.method` / `response.request.url.path`。
2. **`response.extensions`，特别是 `http_version`**。cassette 明确保留它（`cassettes.py:202-205,408-416`）；L1 只有压缩后的显示标签 H1/H2（`pipeline_app.py:255`），不能无损还原 extension 字符串。
3. **真实 chunks**。记录 `SseEvent` 只能重建“每帧一个 chunk”的派生固件，不能重建 `chunks: list[bytes]` 的原边界，见 B3。
4. **attempt 身份**。`RequestContext` 明确允许多次上游交换（`src/app/pipeline/request.py:38-47,71-96`），现 schema 的 `(entry_id, sequence)` 没有 attempt 维度；一次客户端请求的多个上游 request/response 不能表示。

`tests/integration/recorded/from_history.py:228-243` 之所以能产出一个可读 cassette，是因为它人为填入 POST、调用者提供的 path、200、`content-type`、HTTP/1.1；这对旧历史固件是公开的证据降级，不应成为新取证系统凭空补事实的模式。另需说明导出目标：单交互 history fixture 可以直接喂 delivery 测试；完整 `recorded_chain` cassette 往往还含 token exchange/models interaction，例如当前 `anthropic_to_responses_stream.json` 有 3 个 interactions。`export-cassette <id>` 不能同时承诺两种语义而不说明范围。

替代方案：按每个上游 attempt 直接记录 request method/path/auth/body，response status/allowlisted headers/recorded extensions/source/chunks；导出时只做 scrub/encoding，不推断。将 cassette codec/scrubber 从 `tests/integration/recorded/cassettes.py` 提升到可安装的共享模块，再让测试与 CLI 同时依赖它；生产 `debug` 命令不应反向依赖 test-only 模块。

### B6 — blocker — 3.6MB/千条的实测压缩口径与提议的“逐帧 zstd”schema 不一致

证据：方案 `docs/agents/history-forensics/proposal.md:83-90,126-133`。来源报告 `docs/tmp/260820-history-as-fixture-source.md:98-105` 是把一次请求的**完整帧字节串整体**做一次 zstd level 3，得到平均 3,592 bytes/request；提议 schema 却让每个 frame 的 `data_zstd` 独立成为 zstd stream。后者失去跨帧重复压缩并为每帧支付 frame header 开销，所以不能拿 3.6MB 直接估它。

当前 checked-in cassette 的可复现实测对照：

| SSE interaction | 整请求 zstd-3 | 逐帧 zstd-3 | 倍数 |
|---|---:|---:|---:|
| `anthropic_to_responses_stream` 的模型响应 | 17,085 B | 19,764 B | 1.16× |
| `responses_web_search_stream` 的模型响应 | 7,373 B | 10,985 B | 1.49× |
| `history_anthropic_stream`（placeholder 脱敏，故只作结构反例） | 557 B | 3,390 B | 6.09× |
| `history_responses_stream`（placeholder 脱敏，故只作结构反例） | 2,611 B | 22,825 B | 8.74× |

这不证明真实工作负载必为某个固定倍数，但足以推翻“3.6MB 就是该 schema 的体积”这个等号。替代方案：要么按请求/attempt 把原始 chunks 合为一个压缩 blob，并另存 chunk 长度/offset；要么重新按逐帧 schema 对真实未脱敏样本测量，再用分布而非单点决定容量。现有来源报告已经把 3.6MB 标成会随工作负载数倍摆动的点估计，方案不应把它提升为无条件“可承受”。

### M1 — major — “失败全留 + 成功最近 N”没有定义失败何时可知，也漏掉 crash、挂起和 retry

证据：方案 `docs/agents/history-forensics/proposal.md:138-145,176-182`。stream 是否完整直到 `_StreamAccounting.finish` 才知道（`src/app/server/pipeline_app.py:316-333`）；进程在终结前 crash/kill、请求永久挂起、磁盘写失败时，单纯“完成后按结果决定留不留”会恰好丢掉最需要的记录。多 attempt 在 `src/app/pipeline/direct_driver/base.py:123-170,191-213` 中逐次发生，当前 L2 只从最终 `response.request.content` 取，失败过的前序 attempt 及其 error response/body 都没有进入方案数据模型。

替代方案：请求开始先写 provisional L1；每个 upstream attempt 开始时写 request snapshot，chunk 到达时增量追加或持久化 bounded spool，attempt/请求结束后再标终态；reaper 只负责淘汰已知成功记录，失败/未终结按明确策略保留。若允许 best-effort 丢失，必须把该保证降级写清楚，而不是继续称“失败全留”。成功窗口还应按时间/字节预算实现，是否需要按 model/session 分桶可留作后续需求，不必现在臆造复杂策略。

### M2 — major — `upstream_frames` 会被现有 reaper 留成孤儿，容量上限不成立

证据：方案 `docs/agents/history-forensics/proposal.md:123-145` 的表没有 foreign key；现有 reaper `src/app/history/sqlite/writer.py:166-183` 只从 `entries` 删除。即使照来源报告加 `REFERENCES ... ON DELETE CASCADE`，当前 `_open` 在 `writer.py:63-69` 也没有启用 SQLite `PRAGMA foreign_keys=ON`。因此“entries 被删 → frames 一起回收”目前没有机制，L3 会永久累积，条数/字节双限流只是文字。

替代方案：在同一 writer transaction 中显式按 entry/attempt 删除 chunk/blob，再删主记录；或启用并测试 FK cascade。总字节预算必须统计实际压缩 blob 字节，而不是 `data_bytes` 原始字节。

### M3 — major — `app.pipeline.events` 不能作为 `_log_completion` 的等价替代挂点

证据：方案 `docs/agents/history-forensics/proposal.md:204-206` 把内部 events 与 `_log_completion` 并列。`src/app/pipeline/direct_driver/base.py:142-170` 在拿到 response headers 并发布 `attempt.succeeded` / `request.succeeded` 后就返回；stream 此时尚未被 `read_events` 消费，terminal/usage/stop_reason/received bytes 尚不存在。其事件 payload 还是 `RequestContext`（`src/app/pipeline/events.py:13-25`），不含 `_Trace` 的 ASGI method/path/protocol/duration。它适合 per-attempt request snapshot，不适合最终 L1 completion。

替代方案：用内部 attempt events 采集每次上游交换的“开始/headers/失败”事实；用外层 request finalizer 采集最终 L1。分工而非二选一。

### M4 — major — 第三节漏掉两个会改变架构的真实分叉

证据：方案 `docs/agents/history-forensics/proposal.md:164-200` 只有层级、默认档位、死开关、旧链路四类裁决，但 B3/B4/M1 暴露了两个独立且承重的选项：

1. L3 是保留 parser-input raw chunks，还是只保留 frame-derived `SseEvent`。二者证据能力与存储形状不同。
2. L1/L2/L3 是 durable/backpressured，还是 bounded best-effort。现有 writer 的 API 已明确区分：`src/app/history/sqlite/writer.py:71-93`。

建议把这两项加入用户裁决。A1/A2/A3 本身还漏了“L1+L3、不留完整上行 body”，但鉴于上行 body 是盘点最高需求，这只是一个理论组合，不必为形式穷尽强行列出；真正必须补的是上述会改变保证与 schema 的分叉。

### M5 — major — “不做 L4”的结论可保留，但“由 L3 就能推出来”的理由过强

证据：方案 `docs/agents/history-forensics/proposal.md:207`。L3 到下行块还经过 `src/app/pipeline/delivery/stream.py:114-179` 的 buffering、header synthesis、ping、terminal synthesis，并受当时的代码版本与配置影响；客户端提前断开时，实际交付更不能只由上游帧推出。当前取证盘点零次需要 L4，是足以支持暂不做的真实理由；“对照 L3 就能推出来”只能收窄为“可在固定代码/配置下重放预期转换”，不能冒充实际交付证据。

### m1 — minor — 本地 `history.db` 数字是可变快照，方案缺少观测时刻

证据：方案 `docs/agents/history-forensics/proposal.md:26` 写 8,534 行、截止 09:00 左右；来源报告 `docs/tmp/260820-history-wiring-audit.md:126-155` 给出了当时完整快照。当前只读重查已是 8,630 行，max 时间 2026-08-20 09:13:36；endpoint 仍无 `anthropic-messages`，平均 payload 仍为 46.66 B。建议写成“截至 2026-08-20 09:00 的快照为 8,534 行”，不要让可变数据库计数看起来像永久事实。这个漂移不改变“测试写入真实用户目录”和“生产主路径没有记录”的结论。

## 三、设计裁决建议

当前不建议让用户直接在 A1/B1/C1/D1 上拍板，因为 A/B 把两种不同 L3 和两种不同持久化保证混在一起。推荐先按以下模型修订方案，再交裁决：

1. **数据模型按 request → upstream attempt → chunks/exchange 分层。** L1 是 request completion；L2 是每个 attempt 的真实 outbound request 与 response metadata/body；L3 分成 raw parser-input chunks 与可派生的 parsed events，不重复落两份时可只存 raw chunks、查询/导出时解析。
2. **存储与旧 history 共享数据库可以，强行共享 `HistoryEntry` 不值得。** 新表、新 DTO、新 recorder；是否抽通用 SQLite writer 由实现复杂度决定，不把抽象本身当目标。
3. **采集点分工。** attempt events/transport tap 采 L2；`_counted_upstream` 前后不改字节地采 raw chunks；外层幂等 finalizer 采 L1。不要依赖当前并不 exactly-once 的 `_log_completion`，也不要拿 request.succeeded 代替请求完成。
4. **先写后分类。** provisional/attempt/chunk 增量落盘，结束后标成功/失败；成功由按条数+实际压缩字节的 reaper 淘汰，失败和未终结遵循单独保留策略。用户需要裁 durable 还是 best-effort。
5. **cassette codec 提升为共享生产模块。** export 只 scrub/encode 已记录的真实 method/path/auth/body/status/headers/extensions/chunks，不补猜测值；明确导出是单交互 delivery fixture，还是包含 token/catalog 的完整 provider cassette。

修订后，我对原四个方向的偏好仍是：功能层级选修正版 A1；默认触发选“provisional 全采、失败保留、成功滚动淘汰”的 B1 语义；C1 接上 `history.enabled`，但补齐细分档位；D1 不动旧链路。这个偏好建立在上述数据模型和保证已纠正的前提上，不是对当前文本的放行。

## 四、可保留的“不采纳”判断

- 不先实现六个 operator hook：理由成立，当前没有 dispatch surface，见 `src/app/config/schema.py:202-214` 与全仓零消费者。
- 不复制 `copilot-api-js` 内容寻址 manifest/handle：在单请求直接关联、没有跨请求去重目标时成立。
- 不先做 REST/WS：CLI 作为服务停机后仍可读的首个消费面成立；但须使用 production/shared cassette codec，不能让安装后的 CLI import `tests/`。
- 不做 L4：当前需求证据足够支持暂缓，但理由按 M5 收窄。

## 五、运行过的关键核验

```text
uv run --project /home/xp/src/ghc-api-proxy-py pytest /home/xp/src/ghc-api-proxy-py/tests/unit/test_module_boundaries.py --quiet
→ 3 passed

reachable_from(...) 当前实测
→ pipeline_app=111, cli=125, history types/writer/store/consumer=6/6/9/34；禁区违规均为 0

临时 test-only 探针：Request.body() 抛错后检查 app.request completion
→ 1 passed；完成记录确认为 0

只读 SQLite 查询 ~/.local/share/ghc-api-proxy/history.db
→ 8630 rows；无 anthropic-messages；avg request_payload=46.663... B；max=2026-08-20 09:13:36

checked-in cassette zstd-3 对照
→ 逐帧压缩相对整请求压缩为 1.16×、1.49×；脱敏结构样本为 6.09×、8.74×
```
