# 取证记录行为 Spec 事实与技术可行性评审

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/history/spec.md`。

评审视角：事实与技术可行性。范围取舍由另一路评审，本报告不重复。

评审快照：当前工作树 `HEAD 40d9c76a9ed15093e5aa334acb0f7ac6cb3f7f13`，时间为 2026-08-21。源文件按当前工作树符号核验；工作树中与本报告涉及的生产源码无未提交修改。Spec 自述的事实基线是旧的 `be63418`，并行演进已经造成至少一处实质漂移，即 `RequestLine.losses`。

## 结论

**结论：needs-fix。Spec 目前不能据以直接实施。共 16 条发现，其中 blocker 6、major 7、minor 2、nit 1。**

六条 blocker 都是内部合同彼此不能同时成立或采集点覆盖不到已承诺的对象，不是代码尚未写这种普通 gap：Q2 与 Q3 对 executor 的要求互斥；Q6 与端点过滤器及索引表互斥；count-tokens 的真实上游调用绕过 Spec 唯一指定的 L2 attempt 边界；replay 同时要求原字节与改 `stream`；I3 与 L1 的有界背压／终态 ack 互斥；独立归档库与 WAL 下跨库原子搬迁互斥。

证据权重：源码逐符号核验、Python 3.14.2／SQLite 3.50.4 实验及 `EXPLAIN QUERY PLAN` 输出，均足以据以修订 Spec。微基准只支持当前机器与给定样本下的量级判断，不支持跨机器常数。

## 一、字段来源抽查

本轮实际抽查 29 个字段／字段组，超过任务要求的 15 个。下表中的“成立”表示符号存在、类型相容、在声称的采集点可取得；“需修”表示至少一项不成立。

| 字段／字段组 | 判定 | 一手证据与说明 |
|---|---|---|
| `ForensicRequest.id` | 成立 | `_Trace.request_id` 存在，`_serve` 在任何 body 解析前用 `str(uuid4())` 赋值。`src/app/server/pipeline_app.py:181-203,299-306` |
| `session_id` / `agent_id` | 成立 | `identify_session(headers)` 返回 `tuple[str | None, str]`，缺省 agent 为 `"main"`；`_serve` 此时持有原始 `request.headers`。`src/app/history/sessions.py:3-16`、`src/app/server/pipeline_app.py:291-316` |
| `message_id` | 成立，但仅流式可 join | `_dispatch` 在 `RequestContext` 构造后写 `trace.message_id = context.id`；流式把同一个 `context.id` 传入 `stream_delivery`。`src/app/server/pipeline_app.py:370-384,496-519`。非流式限制见 §10.5，已独立确认 |
| `started_at` | 成立 | `_Trace.started_at` 存在，`_serve` 用 `utc_timestamp()` 写入 ISO UTC 毫秒。`src/app/server/pipeline_app.py:181-204,299-304` |
| `duration_s` | 成立 | `_log_completion` 用 `time.monotonic() - trace.started`。`src/app/server/pipeline_app.py:243-278` |
| `first_upstream_byte_s` | 成立 | `_counted_upstream` 在首个非空 chunk 上写单调时钟差。`src/app/server/pipeline_app.py:629-639` |
| `method` / `path` | 成立 | `_serve` 直接取 ASGI request method 与 `request.url.path`。`src/app/server/pipeline_app.py:299-302` |
| `inbound_format` / `count_tokens` | 成立 | 路由识别后写 `route.wire_format.value` 与 `route.count_tokens`。`src/app/server/pipeline_app.py:349-359` |
| `client_protocol` | 成立 | 取 ASGI scope 的 `http_version`，经 `http_label`。`src/app/server/pipeline_app.py:307-310` |
| `upstream_protocol` | 成立 | 最终 response 用 `response.http_version` 经 `http_label`；计数路径也有独立 extras。`src/app/server/pipeline_app.py:424-434,473-477` |
| `requested_model` / `resolved_model` | 成立 | `RequestContext.requested_model`、路由后的 `context.resolved_model` 均存在。`src/app/pipeline/request.py:53-70`、`src/app/server/pipeline_app.py:382-391,454-458` |
| `status_code` / `status` | 成立 | 非流式取 `Response.status_code`，流式存于 `_StreamAccounting.status_code`；`status_for` 接受 override。`src/app/server/pipeline_app.py:243-288,321-329,542-580` |
| `bytes_in` | 部分成立 | 最终成功 attempt 可由 `len(response.request.content)` 取得。`src/app/server/pipeline_app.py:473-475`。失败 attempt 不能从这个符号取得，见 M3 |
| `bytes_out` | 成立 | 实际来源是 `_Trace.received`，由 `_counted_upstream` 累加 upstream→proxy 字节。`src/app/server/pipeline_app.py:629-639`。Spec 对方向的说明准确 |
| `usage` / `terminal_seen` / `stop_reason` / `blocks` / `tools` / `thinking` / `dialect` | 符号成立，缺席语义不成立 | `_Trace.absorb(Terminal)` 一处聚合，字段均存在。`src/app/server/pipeline_app.py:207-231`。但默认值无法满足 I4，见 M2 |
| `attempts` | 需修 | `_Trace.attempts` 当前是 `int` 且默认 `1`，不是 Spec 表里的可空观测值；body 解析前失败也会落成一次 attempt。`src/app/server/pipeline_app.py:187-218` |
| `upstream_conn` | 成立 | `_snapshot_upstream_connection(response)` 在 response 仍活着时取可序列化快照，空对象明确代表没尝试。`src/app/server/pipeline_app.py:111-142,476-477` |
| L2 `provider_name` / `endpoint` / `payload_snapshot` | 成立 | `RequestContext.provider_name`、`Attempt.endpoint`、`Attempt.payload` 均存在。`src/app/pipeline/request.py:39-91`、`src/app/server/handler.py:76-82` |
| L2 `upstream_method` / `upstream_url` / `upstream_path` | 需要新合同，但技术上可得 | 成功 response 的 `response.request` 可得；当前 subscriber 只收到 `RequestContext`，拿不到 request／response。`src/app/pipeline/direct_driver/base.py:116-176`。§3.4 对“必须扩展合同”的判断成立 |
| L2 `authenticated` / `request_headers` | 需要新合同，但技术上可得 | 实际 GHC headers 在 `GhcApiClient.request_headers` 生成并传给 SDK。`src/app/model_provider/ghc_client/client.py:46-98`。完整性表示法另见 m2 |
| L2 `request_body` | 最终成功成立，失败 attempt 来源写错 | 最终成功 response 可从 `response.request.content` 取得；连接失败／SDK 异常路径没有 response。§3.4 又要求失败合同显式带实际 request，故字段表来源不能只写 `response.request.content`。见 M3 |
| L2 `status` / `response_headers` / `extensions` | 成立，需新合同 | `Attempt.status_code` 存在；成功 `httpx2.Response` 持有 headers 与 extensions。`src/app/pipeline/request.py:39-49`、`src/app/pipeline/direct_driver/base.py:148-169` |
| L2 `error_body` | 成立 | `normalize_upstream_error` 经 `_response_parts` 读取 response text，写入 `UpstreamError.body`／`UpstreamRejected.body`。`src/app/model_provider/ghc_client/errors.py:62-115`、`src/app/pipeline/exceptions.py:24-83` |
| L2 `error_message` | 需修 | `Attempt.error = str(error)` 接受任何 subscriber／driver 异常，不保证都经 `normalize_upstream_error`。`src/app/pipeline/direct_driver/base.py:134-175` |
| L2 `retry_reason` | 需修 | `reason_for(error)` 只分类“若可重试，属于哪类”，不记录 budget 是否批准，也不能说明“为什么没重试”。`src/app/pipeline/retry.py:37-58`、`src/app/pipeline/direct_driver/base.py:197-219` |
| L2 `rate_limit_wait_s` | 成立但必须在 attempt 边界立即快照 | rate limiter 每次 attempt 覆盖 `context.extras["rate_limit_wait_s"]`。`src/app/pipeline/direct_driver/base.py:129-141`。若异步延后读取同一 mutable context，会被后一次 attempt 覆盖 |
| L3 七字段 | 成立 | `_counted_upstream` 每 chunk 持有原始 bytes、请求 trace 和单调时钟，且位于 `read_events` 之前。`src/app/server/pipeline_app.py:629-639`、`src/app/pipeline/delivery/stream.py:60-80` |
| `ChunkSpool.payload` | 技术上可得 | 同上，原始 `chunk: bytes` 在 yield 前可得；但“已持久化”的保证与 best-effort 队列冲突，见 M4 |

## 二、`requests-*.jsonl` 对账

### M1 — major — §2.1.1 的 28／2／6 对账与当前源码及现存文件均不符，L2 列数也写错

当前 `RequestLine` 是 **29 个字段**，不是 28 个。新增且 Spec 漏掉的是 `losses`。源码证据为 `src/app/observability/request_log.py:100-145`，`_log_completion` 已把 `trace.losses` 写进 `RequestLine`，见 `src/app/server/pipeline_app.py:248-278`。按当前 `write_request_record` 的 `{"at", "status", **asdict(line)}`，下一条由当前进程代码写出的 JSONL 应有 31 个顶层键。

机械核对输出：

```text
RequestLine_field_count 29
RequestLine_fields method,path,request_id,message_id,inbound_format,count_tokens,client_protocol,upstream_protocol,requested_model,model,status_code,started_at,duration_s,first_upstream_byte_s,bytes_in,bytes_out,usage,terminal_seen,stop_reason,blocks,tools,thinking,count_provider,count_provider_reason,dialect,attempts,detail,upstream_conn,losses
```

现存生产 JSONL 还显示该文件合同已经发生过多次演进。`requests-20260820.jsonl` 有 6 种 key set，单行总键数分别出现 27、28、29、30；`requests-20260821.jsonl` 在检查时 4,470 行均为 30 键，仍来自尚未加载 `losses` 的运行中进程。故“实测一条键恰为……”只能描述某个进程版本，不能作为当前 schema 的全称事实。

JSONL 独有的 `at`、`status` 两项仍成立。L1 需要而 JSONL 没有的不是“6 项”，而是 **7 个字段**：`session_id`、`agent_id`、`ended_at`、`pinned`、`archived_batch`、`origin`、`replay_of`。原表把 `origin / replay_of` 合写成“一项”，随后又称“其余四项”，两个计数都不成立。

此外，Spec 数据表机械计数为 `ForensicRequest=36`、`UpstreamExchange=31`、`UpstreamChunk=7`。任务背景与 Spec 周边声称 L2 为 30 列，但 §2.2 实际是 31 列，末列为 `truncated`。这会直接影响 DTO、migration 与投影列清单，不能只当标题笔误。

建议修订方向：把 `losses` 纳入 L1，按字段数写 29／2／7，并把 L2 明写 31 列。若 L1 有意不保存 `losses`，则必须撤回 §1.4“任何新字段都进入 L1”的绝对规则并给出理由。

### M2 — major — I4“缺席可读”无法由当前 `RequestLine`／`_Trace` 类型实现

Spec §1.4 要求 L1 直接消费同一个 `RequestLine`，§1.5 I4 又要求 `NULL` 表示未观测、空值表示观测到空。但当前单写源已经把多种状态折叠：

- `_Trace.attempts` 与 `RequestLine.attempts` 均为非空 `int`，默认 `1`。请求在 `await request.body()` 或 JSON 校验时失败也会写成一次 attempt。`src/app/server/pipeline_app.py:187-218`、`src/app/observability/request_log.py:113-145`。
- `terminal_seen=False`、`blocks=0`、`usage={}`、`tools=()`、`thinking=()` 同时表示“没有走到 reply”与“走到了且观测为空”。
- `inbound_format=""`、`requested_model=""`、`model=""`、`stop_reason=""` 折叠未观测与空字符串。

因此将这些字段映射成 L1 的 nullable 列时，writer 无法判断该写 `NULL` 还是空值。并且 provisional L1 在 `_dispatch` 前写入，此时 `RequestLine` 尚未构造；当前 `RequestLine` 是 frozen dataclass，只在 `_log_completion` 终态一次性构造。`src/app/observability/request_log.py:100-145`、`src/app/server/pipeline_app.py:243-284,291-316`。这也使“provisional 与终态都直接取同一个 RequestLine 对象”在当前结构下做不到。

需要先裁清单写源的形态：要么把聚合记录改为能表达 `None` 的生命周期记录并由 JSONL／L1 共读，要么明确 provisional 允许直接取 `_Trace` 的最小身份字段、终态才读 `RequestLine`，并把 §1.4 的绝对措辞收窄。仅在 SQLite writer 里把 falsy 值改成 `NULL` 会把真实的零值一起抹掉，不能采用。

## 三、阻断实施的技术矛盾

### B1 — blocker — Q2 与 Q3 在 Python 中不能同时实现

Q2 指定“每一次查询都在 `asyncio.to_thread` 之下”，Q3 又指定“查询使用独立线程池，不与 `asyncio.to_thread` 默认线程池共用”。`asyncio.to_thread()` 没有 executor 参数，它固定提交到 event loop 的 default executor。复现实验：

```text
to_thread default-pool_0
run_in_executor_custom query-pool_0
```

要满足独立 pool，Q2 必须改成 `loop.run_in_executor(query_executor, ...)`，或将条款写成与具体 API 无关的“在专属 history query executor 中执行”。不能通过 `loop.set_default_executor(query_pool)` 规避，因为那会把 query pool 变成全进程默认池，正好推翻 Q3 的隔离目标。

Q3 的现状理由也需收窄。当前源码中的 `asyncio.to_thread` 只出现在旧 history writer；tokenization 文件 I/O 用 `anyio.to_thread.run_sync`，`request_log_file.py` 则直接同步跑在事件循环线程。证据：`src/app/history/sqlite/writer.py:58-109`、`src/app/tokenization/state_store.py:47-105`、`src/app/observability/request_log_file.py:31-59`。

### B2 — blocker — Q6“按索引列过滤、无全表扫描”与 §5.1 暴露的过滤器及 §2.1 索引表直接冲突

§5.1 提供 `agent_id`、`status_code`、`requested_model`、`inbound_format`、`path`、`min_attempts`、`has_error_body` 等过滤条件；§2.1 没有为前六项建立索引，`has_error_body` 还需要跨 L2 判断。按 Spec 原样建立表与索引后，SQLite 3.50.4 的 `EXPLAIN QUERY PLAN` 输出：

```text
agent_id       SCAN forensic_requests; USE TEMP B-TREE FOR ORDER BY
status_code    SCAN forensic_requests; USE TEMP B-TREE FOR ORDER BY
requested_model SCAN forensic_requests; USE TEMP B-TREE FOR ORDER BY
inbound_format SCAN forensic_requests; USE TEMP B-TREE FOR ORDER BY
path           SCAN forensic_requests; USE TEMP B-TREE FOR ORDER BY
attempts       SCAN forensic_requests; USE TEMP B-TREE FOR ORDER BY
```

即使已有的 `(session_id, started_at DESC)`、`(status, started_at DESC)`、`(resolved_model, started_at DESC)`，统一排序又要求 `started_at DESC, id DESC`，索引没带 `id`，实验仍显示 `USE TEMP B-TREE FOR LAST TERM OF ORDER BY`。单列 `(started_at DESC)` 也不能满足完整 cursor 顺序。

因此不能同时实现 §5.1 的过滤合同和 Q6。需要逐个决定哪些过滤器有复合索引，哪些允许受 limit 驱动的有界扫描，哪些不提供；cursor 关键索引至少要包含 `(started_at DESC, id DESC)`。不能把“SQL 写了 LIMIT”当成“没有扫描”。

### B3 — blocker — Spec 唯一指定的 L2 attempt 边界覆盖不到 count-tokens 的真实上游 exchanges

§1.1 把上游 attempt 定义为 `RequestContext.begin_attempt`，§3.2 指定 L2 在 driver attempt 边界采集。但 count-tokens 生产路径绕过 `DirectDriver.run`：`handle_count_tokens` 只调用一次 `context.begin_attempt()`，随后 `count_tokens()` 在自己的 provider 循环里对 `ghc` 做 `max_retries + 1` 次真实调用，或完全走 local provider而不发上游。证据：

- `src/app/server/handler.py:201-232,248-300`
- `src/app/pipeline/count_tokens.py:41-81`
- `src/app/pipeline/direct_driver/base.py:126-176`

结果是一条 RequestContext attempt 可能对应 0、1 或多次真实上游 exchange，违反“一 attempt 一 L2 行”，而 Spec 没有排除 count-tokens。`ForensicRequest.count_tokens` 明确说明该路径属于 L1。

需在 Spec 中二选一：把 L2 的权威边界下沉到所有 GHC 请求都会经过的 transport／client tap，并定义 direct-driver attempt 与 count-provider attempt 的身份映射；或明确 count-tokens 不进入 L2，并承认相应真实请求体／错误体不可查询。只扩展 `DirectDriver._publish` 不能完成当前合同。

### B4 — blocker — replay 不能同时“发送原字节”与通过 `stream` 参数改变同一个 body 的模式

§5.6 同时规定：发送 `UpstreamExchange.request_body` 原字节；`stream` 可显式从流式改非流式或反之。当前 request body 原样保留入站 `stream` 字段，`build_context` 只读取它但不从 payload 删除；driver 又把 payload 与 `context.stream` 一起传给 provider。证据：`src/app/server/inbound.py:59-89`、`src/app/pipeline/direct_driver/base.py:221-260`。

若 recorded body 内是 `"stream": true`，要改成 false 就必须修改 JSON 字节；若不改 body，传一个 Python 侧 `stream=False` 只改变 SDK 如何消费 response，不保证改变发给上游的 JSON 合同。两条承诺不可同时成立。

需定义：`stream=null` 时严格原字节重放；显式 override 时允许解析并重新序列化，响应明确回报 `body_modified=true` 与新 digest。若坚持任何情况下都原字节，则删除 override。

### B5 — blocker — I3“不得改变响应时序”与 L1 durable 的背压／ack 规则互斥

I3 绝对规定记录失败不得改变响应时序。§4.1 又规定 provisional 在 `_dispatch` 前通过 `await queue.put` 背压最多 5 秒，终态写等 SQLite ack。非流式终态发生在 `_serve` 返回 response 之前。无论磁盘最终成功还是失败，这两个 await 都可能把上游发起或客户端响应延后，最多达到 `history.write_timeout_s`。`src/app/server/pipeline_app.py:291-329` 是当前收尾顺序。

这是 C1 的真实取舍，不可能靠实现技巧同时消掉。需把 I3 收窄为“不改变响应内容／状态，且新增延迟有明确上界”，或放弃请求路径上的 durable ack，改为无等待提交并承认进程崩溃窗口。当前文本不能作为验收合同。

同一矛盾也使 I1 的无条件“恰好产生一条 L1”过强：§4.1、§4.3 已明确 timeout／fatal 时 L1 可以丢失。应区分“生命周期只发出一次终结意图”与“SQLite 中必有一行”。

### B6 — blocker — WAL 下独立归档库不能提供 §7.4 冻结的跨库原子搬迁

§7.4 声称无论归档物理形态怎么选，一次搬迁都在同一个事务中“写目标 → 校验 → 删源 → 提交”，并要求崩溃不丢数据。§9.4 的建议却是独立按日期分片的 SQLite 文件。SQLite 官方明确：使用 WAL 时，跨多个 attached database 的 transaction 只保证每个文件各自原子，不保证这些文件作为一个集合原子；host crash 可能让一边提交、另一边没提交。

因此独立归档文件 + WAL 热库不能满足冻结条款。需按物理选择分合同：同库冷表可单事务；独立文件应采用可恢复的 copy-then-mark 两阶段协议，优先允许重复而不允许丢失，并在启动时按 batch id 幂等对账。另一选择是跨库搬迁时不用 WAL，但这会反过来影响 §6 的读写并发，不能静默切换。

官方依据：SQLite《ATTACH DATABASE》§2 与《Write-Ahead Logging》明确给出该限制，链接见文末。

## 四、其余 major／minor 发现

### M3 — major — L2 三项 provenance 说明强于当前事实

1. `request_body` 不能统一来自 `response.request.content`。成功 attempt 可以，连接失败没有 response；SDK status exception 的 request 只留在被包装的 cause／response 上，而 §3.4 又正确禁止遍历 cause。字段表应改为“显式 observation payload 中的实际 `httpx2.Request.content`”。
2. `error_message = Attempt.error` 不保证“已被 normalize_upstream_error 归一”。subscriber 的 `KeyError`、`PipelineAbort`、rate limiter 事件错误都可直接进入 `Attempt.error = str(error)`。`src/app/pipeline/direct_driver/base.py:134-175`。
3. `retry_reason = reason_for(error)` 只给错误类别，不给实际行动。budget 拒绝时它仍返回一个 retry reason，但这一 attempt 实际没重试；不可重试时 `None` 也说不出 classifier／budget 的裁决。需要至少分 `retry_reason` 与 `retry_disposition`／`retry_allowed`，并在 `_handle_failure` 做决定的时刻快照。`src/app/pipeline/retry.py:37-58`、`src/app/pipeline/direct_driver/base.py:197-219`。

### M4 — major — bounded best-effort 队列无法保证丢失标记与 crash spool 叙述

§4.2 要求 queue full 时 chunk job 立即丢弃，同时必须把 `chunks-dropped:<n>` 持久化到同一个 exchange；但队列已经满，承载这个标记的 update job 也可能被丢。若进程随后崩溃，内存计数还没机会随 attempt-final job 落盘，记录就会“看着完整但其实丢过东西”，正是 Spec 声称最不能接受的形态。

同理，§2.4 说 disk spool 的收益是“进程死的时候那些字节还在”，但第 4 步若只是 `put_nowait` 后立刻 yield，排队中的 payload 尚未进入 SQLite；进程在 writer 消费前退出仍会丢。要逐 chunk 等 ack 才能给这项保证，而那又违反 L3 best-effort 与 I3。

可行的合同应收窄为“已由 writer ack 的 spool 行可在重启后恢复”；丢失标记需有不与 payload job 共用满队列的通道，例如 exchange 内存状态在终结时以 L1 durable lane 提交，并明确 crash 前仍可能无标记。若要绝对保证标记，就必须接受一条 durable metadata 路径及其背压。

### M5 — major — Q7 的 timeout 只终止 HTTP 等待，不能终止正在执行的 SQLite 查询；线程池也不隔离磁盘／CPU 竞争

`asyncio.wait_for`／timeout 取消 `run_in_executor` future 时，已经在线程中运行的 sqlite3 调用不会停止。端点可以在 30 秒回 503，但两个 query worker 仍可能继续执行慢查询；后续请求继续排队，Q7 所谓“而不是无限等”只对调用方成立，不对资源占用成立。若 Q7 要约束执行时间，需要 per-connection `set_progress_handler`／`interrupt()`，并保证 connection 与 worker 生命周期安全。

WAL 的锁语义成立，但不能外推为“查询不会拖慢 writer／请求”。本机实验用一个 WAL writer、四个 `mode=ro` reader：同样 2,000 次 autocommit insert，无 reader 时 53.812 ms；并发 reader 时 1,859.609 ms，reader 18,175 次、0 错误、最大单次 8.505 ms。没有锁阻塞错误，writer 仍因 CPU／存储竞争慢约 34.6×。这支持“读写可并发”，不支持“资源无干扰”。独立线程池与并发上限是必要的限幅，不是物理隔离。

§6 的 p99 检验仍值得保留，但“无可归因抬升”没有数值阈值，无法裁定绝对 I7。至少应明确它是负载相关观测，不把 WAL 句子当成保证。

### M6 — major — 固定 `busy_timeout=5000` 会越过写入自身剩余 deadline

SQLite 的 `busy_timeout` 在一次 sqlite call 内部等待；应用层直到它返回 `SQLITE_BUSY` 后才能检查自己的 deadline。本机第二 writer 持有 `BEGIN IMMEDIATE` 时实测：

```text
busy_timeout=0ms   -> SQLITE_BUSY in 0.4ms
busy_timeout=100ms -> SQLITE_BUSY in 101.3ms
busy_timeout=500ms -> SQLITE_BUSY in 502.3ms
```

若 job 已在队列里等了 4.9 秒，固定 5,000 ms 的 PRAGMA 仍可再阻塞约 5 秒，违反 `history.write_timeout_s=5` 的背压上界；并且 SQLite 内部等待耗尽后，现有 `_insert_with_retry` 的 application deadline 已经过期，不会再“重试到 deadline”。`src/app/history/sqlite/writer.py:123-132` 展示现有模式。

5000 这个数量级本身没有被实验推翻，但必须与每个 job 的剩余 deadline 协调。简单做法是把 connection 的 busy timeout 设为远小于写 deadline的固定小值，让 application loop掌握总上界；或每次 job 按剩余预算临时设置。不要同时声称固定 5 秒 SQLite 等待与总计 5 秒 job deadline都严格成立。

### M7 — major — Q4“列表只含定长小字段”与响应合同不符

§5.1 的列表项除四个 JSON 字段外包含 §2.1 的其余字段，因此包含无长度上界的 `detail TEXT`；新增的 `losses` 若按 §1.4 进入 L1，也同样是可增长结构。Q4 的“不读 BLOB”可以通过显式 SELECT 列实现，但“定长小字段”不成立。需明确列表是否给 `detail_preview`／长度上限，或承认它是变长 TEXT。否则一个携带长异常文本的列表仍能放大查询和响应，即使没碰 BLOB。

### m1 — minor — §10.1 对同步事件循环 I/O 的指控属实，但当前量级很小，`_prune` 是每请求一次

调用链已确认：`_serve` 协程与 `_StreamAccounting.finish` 同步调用 `_log_completion`，后者同步调用 `write_request_record`；该函数执行 `mkdir`、`open`、`json.dumps`、`write`、close，再无条件调用 `_prune`。`_prune` 每条完成记录都 `glob("requests-*.jsonl")`、排序并删除第 14 天以前的文件。证据：`src/app/server/pipeline_app.py:243-329,559-580,610-626,642-663`、`src/app/observability/request_log_file.py:31-59`。

在 `/tmp`、当前 29 字段 `RequestLine`、模拟现状 2 个日文件，5,000 次实测：median 210.402 µs、p95 328.503 µs、p99 464.405 µs、max 1.373 ms。无 `_prune` 的另一次较大记录基准为 median 223.853 µs、p99 582.006 µs；说明在正常最多 14 个文件的稳态下，主要成本是每次 open／serialize／write／close，glob 不是数量级主因。

当前实测约 4,470 请求／天，平均频率约 0.052 次／秒。按该流量，累计 event-loop 占用约 0.94 秒／天，**不足以构成当前事故量级**；每次请求完成仍会引入约 0.2 ms、p99 约 0.46 ms 的同步暂停。若目录在第一次调用前被恢复进 2,000 个匹配文件，单次批量 prune 的实验最大值到 64.3 ms，但正常每次都 prune 后目录稳态不超过 14 个文件，不能把该极端值当日常成本。

结论应写成：指控属实，当前影响为低量级的 event-loop tail pause；新取证 writer 不应复制这个形态。无需把现有 JSONL 当作阻断项。

### m2 — minor — “完整 headers”若用 JSON object 会丢重复头

`httpx2.Headers` 允许同名 header 多次出现；直接 `dict(response.headers)`／JSON object 会合并同名项，不能称“完整”。如果合同真的要求逐项完整，应存 `headers.multi_items()` 的 pair list，或明确合同是 case-insensitive 合并视图。认证判断仍可按 header 名完成，不受此问题影响。

### n1 — nit — `forensic_query_seconds` 的“按 endpoint 分标签”需说明是有限枚举

Prometheus label 若直接取任意 HTTP path／请求字段会造成高基数。这里实际只有本 Spec 固定的查询动作，实施时应以固定 endpoint name 枚举，别把原始 URL 或 id 放入 label。不是新增保护措施，只是把指标表的类型说完整。

## 五、技术断言实测结果

### 5.1 `compression.zstd` 可用，替代 dev-only `zstandard` 在本样本上成立

环境：Python 3.14.2，stdlib 模块路径 `/home/xp/.local/share/uv/python/cpython-3.14.2-linux-x86_64-gnu/lib/python3.14/compression/zstd/__init__.py`，`zstandard 0.25.0`。`pyproject.toml:10,40-52` 确认 Python 下限 3.14，`zstandard` 仅在 dev group。

将 checked-in 5 个 cassette 的 9 个 interaction chunks 解码并拼成 152,028 B corpus，level 3 结果：

```text
stdlib bytes=30498, ratio=4.9849
zstandard bytes=30498, ratio=4.9849
byte_identical=True
stdlib can decode zstandard=True
zstandard can decode stdlib=True

compression median, 1315 loops × 9 rounds
stdlib      291.686 us
zstandard   283.495 us

decompression median
stdlib      108.223 us
zstandard    95.721 us
```

在该样本与运行时上，压缩结果和比例完全相同；stdlib 压缩约慢 2.9%，解压约慢 13.1%，绝对量级均小于 0.3 ms／152 KB。**足以支持采用 stdlib、避免新增 runtime dependency**；不支持外推所有 CPU／payload 都是相同比例。Spec 这条断言通过。

### 5.2 WAL + 单 writer + `mode=ro` reader 的锁语义成立

临时库实测：writer 设置 WAL／NORMAL／busy_timeout，reader 用 `file:…?mode=ro`。reader 持有 read transaction 时，writer 成功提交 2,000 行；reader 在事务内始终看到旧 snapshot 1 行，commit 后看到 2,001 行。`PRAGMA wal_checkpoint(PASSIVE)` 在 reader 存活时返回 `(0, 2016, 3)`，reader 结束后 `TRUNCATE` 返回 `(0, 0, 0)`。四个并发 reader 与 writer 共同运行，18,175 次 read 为 0 errors。

`mode=ro` 的 `PRAGMA query_only` 值仍显示 0，但写入实测报 `SQLITE_READONLY`，说明只读性来自 URI open flag，而不是 PRAGMA。这个形态可用。

结论：Q1 的 SQLite 锁级陈述成立，长读事务会阻止 checkpoint 完成并让 WAL 增长，这一点应保留在实施注意事项；它不等于资源层完全无干扰，见 M5。

当前 Python 绑定的 SQLite 是 3.50.4。SQLite 官方说明 3.7.0～3.51.2 范围可能受 WAL-reset bug 影响，触发条件要求多个连接在不同线程／进程中同时 writing／checkpointing。Spec 严格维持一个 writer、只读连接不做 checkpoint 时不满足触发条件；实施不得让 query connection 承担 checkpoint。该运行时事实不单独阻断本设计。

### 5.3 Q1～Q7 逐条判定

| 条款 | 判定 |
|---|---|
| Q1 独立 mode=ro + WAL | **成立**。锁级并发实测通过；注意 checkpoint starvation 与共享资源竞争 |
| Q2 所有 SQLite 调用离开事件循环 | **可行，但不能写死 `asyncio.to_thread`**，否则与 Q3 矛盾 |
| Q3 独立小线程池 | **可行，但须用 custom executor API**。当前理由中“tokenization／文件写入都在 default executor”不准确 |
| Q4 列表不碰 BLOB | **可行**，需 explicit projection；“只含定长小字段”被 `detail` 证伪 |
| Q5 读不进 writer queue，pin 单 ack | **可行**。当前旧 writer 的 `reap()` 确实 `queue.join()`，新查询不应复用 |
| Q6 强制 limit、索引过滤、无扫描 | **按当前 Spec 不成立**。过滤器／排序与索引缺口由 `EXPLAIN` 直接证伪 |
| Q7 并发上限与超时 | **部分可行**。Semaphore + queue timeout 能限制接纳和 HTTP 等待；不能自动停止已在线程运行的 SQLite，需要 progress handler／interrupt 才能限制资源占用 |

## 六、`message.id` join 与新链路 HTTP 边界

### 6.1 `message.id` 只在流式路径成立

已确认 Spec §10.5 准确。

- `RequestContext.id` 是 `uuid4()`，`_dispatch` 写入 `_Trace.message_id`，流式传给 `stream_delivery`，`message_start` 将它写进客户端 SSE。`src/app/pipeline/request.py:53-59`、`src/app/server/pipeline_app.py:382-384,496-519`、`src/app/pipeline/delivery/anthropic_sse.py:30-40`。
- 非流式 `response_payload` 返回上游 body 或翻译 body，客户端可见 id 来自该 body；没有把 `context.id` 覆盖进去。`src/app/server/pipeline_app.py:527-538`、`src/app/server/handler.py:406` 起。

该列可以保留，但查询响应和调研脚本必须带 `message_id_joinable = stream` 这一等价限定，不能在非流式无命中时推断“服务端没有记录”。

### 6.2 新链路增加 HTTP 端点在模块边界上可行

`tests/unit/test_module_boundaries.py:38-44` 只禁止新链路 import `app.server.app_factory`、`app.pipeline.executor` 与任何 `app.routes.*`。它不禁止 `app.history` 或新的 `app.server.history_routes`。现有 `app.server.ops_routes` 已展示独立 APIRouter 由 `pipeline_app.create_pipeline_app` 挂载的形态，见 `src/app/server/ops_routes.py:1-76`、`src/app/server/pipeline_app.py:666-696`。

因此 Spec §5.0 的方案“新建不叫 `app.routes` 的新链路路由模块，不调整边界断言”技术上成立。需要给 `Chain` 新增 recorder／query service 字段并在 lifespan 启停；`Chain` 是 slots dataclass，不能运行时随意 setattr，但修改字段定义即可，见 `src/app/server/composition.py:292-315`。这不是结构阻塞。

真正的结构阻塞是 B3 的 count-tokens 采集边界，不是 HTTP 路由边界。

## 七、建议的最小修订顺序

1. 先修六条 blocker，使合同可同时成立：executor API、filter/index 表、count-tokens L2 边界、replay override、I3 与 durable 的取舍、跨库归档协议。
2. 再重做 §2.1.1 与 DTO 列数，纳入 `losses`，明确 `RequestLine`／provisional 的单写源形态与 I4 的 nullable 类型。
3. 把 L2 observation payload 写成一个显式、不可变的 per-attempt 快照，包含实际 request／response／error／retry verdict；不要继续从 mutable `RequestContext` 或异常 cause 事后拼。
4. 将 Q7 的 timeout 分成“HTTP 等待上界”与“SQLite 执行上界”，前者用 semaphore／future timeout，后者用 progress handler／interrupt。两者不要用一个 30 秒数字假装同一件事。
5. 保留已经通过的方向：stdlib zstd、WAL 单 writer + ro readers、raw chunk 记录点、流式-only message join、`app.server` 新路由模块。

## Sources

- [SQLite ATTACH DATABASE](https://sqlite.org/lang_attach.html)
- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html)
- [SQLite 3.51.3 release notes](https://sqlite.org/releaselog/3_51_3.html)
