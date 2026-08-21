> ⚠️ **本文档已于 2026-08-21 被重定范围取代。**
>
> 对当前生产 import 闭包的全面重测发现：四个取证缺口里两个已被同伴独立解决（`request_log_file.py` 解决完成记录，`rejection_capture.py` 解决上游错误原文），另两个被部分解决。本文档描述的十片计划因此有约六成失去前提。
>
> **现行范围以 [`decisions.md` 第五节](decisions.md) 为准。** 本文件保留作为调查记录与论证过程，其中的事实调查（§1 各节）仍然有效，实施计划（§6）已作废。

---

# 取证记录行为 Spec（history 增强）

- 状态：**规范**。适用范围是新链路（`create_pipeline_app` 及其组合的 `Chain`）上的取证记录、查询、归档与导出，随该外部契约有效而有效。
- 来源：本文是 `proposal.md`（r4）第三节的扩写，按其第四节已裁决的形态展开。**proposal 是「为什么这样裁」的权威，本文是「行为长什么样」的权威**；两者叙述冲突时以本文为准，裁决冲突时以 proposal 第四节为准。
- 冻结范围：§2–§8 为冻结契约，实施切片按它验收。**§9 的六项未裁决，未裁之前不得当作已定**；§10 是实施中发现的缺口，不构成契约。
- **先读 §1.2 与 §1.3**：proposal 的排障盘点里排第二的那个缺口在其定稿之后已被独立解决，L1 的定位与三层的实施优先级都因此变了。
- 指路方式：**一律按符号名，不写行号**。有并行会话正在修改 `src/app/server/pipeline_app.py`、`src/app/observability/*`、`src/app/pipeline/*`。
- 事实基线：本文对现状的每一条陈述都在 2026-08-21（HEAD `be63418`）的工作树上核对过。**proposal 的三处事实基础在其定稿之后发生了变化**：一处新落地的功能改变了 L1 的形状（§10.1），一个被引用的字段已不存在（§10.2），以及 proposal 引证的 `2604-rewrite` 目录已被用户裁定为整体过期的学习笔记、不具权威地位（§10.9）。读 proposal 时请一并读这三条。
- 支撑报告：`.dev/docs/history/reports/`（proposal 里写的 `../tmp/…` 是搬迁前的旧路径）。

---

## 1. 术语与总体不变量

### 1.1 三层的名字

| 层 | 实体 | 一句话 |
|---|---|---|
| L1 | `ForensicRequest` | 一次客户端请求的完成记录，一请求一行 |
| L2 | `UpstreamExchange` | 一次上游 attempt 的实际发出内容与响应元数据，一 attempt 一行 |
| L3 | `UpstreamChunk` | 该 attempt 从上游收到的一个原始传输分片的元数据，字节合并存在 L2 的 blob 里 |

「上游 attempt」的边界与 `RequestContext.begin_attempt` 一致：驱动循环每转一圈开一个 `Attempt`，`Attempt.index` 就是 `attempt_index`。

### 1.2 L1 不是「补上没有的持久化」

**proposal 的一条支撑已经作废。** 它的排障盘点里排第二、被点名三次的缺口是「该次请求的服务端完成记录」，现状写的是「有雏形，只写 stdout」。**这句话在 2026-08-20 16:55 之后不成立**：同伴会话的 `10e4811` 让 `_log_completion` 每条完成记录追加一个 JSON 对象到 `user_data_path()/requests/requests-YYYYMMDD.jsonl`，常开、不可配置、按 UTC 日切文件、按文件名保留最新 14 天。它在生产 import 闭包里（`pipeline_app` 直接 import `write_request_record`），实测目录里已有 `requests-20260820.jsonl`（3,305 行）与 `requests-20260821.jsonl`（1,972 行、仍在增长）。

因此 L1 在本 Spec 里的定位是：

> **给已经存在的完成记录加上可查询性，并作为 L2 / L3 的父行。** 不是补一份从无到有的持久化。

这个重新定位有实际后果，别当成措辞问题：

- **L1 的紧迫性下降。** 「昨天那条 400 发生了什么」现在已经答得出来——`rg` 一下 JSONL 就有。L1 换来的是「按会话/模型/状态过滤着查」和「挂上 L2、L3」。
- **必须回答「同一事实两处推导」这个问题。** 本项目明确反对同一事实在两条路径上各推一遍。L1 与 JSONL 的关系有三种可能的形态，**未裁决**，见 §9.6；在裁决之前，§2.1 的字段表按「两份并存、共享 `RequestLine` 这一个单写源」写，因为那是唯一在三种形态下都不会写错的取法。

### 1.3 三层的紧迫性不是同一档

排障盘点按被点名次数排序的四个缺口，现在的状态是：

| 缺口 | 次数 | 归属 | 现状 |
|---|---|---:|---|
| 实际发往上游的字节级 body | 4 | **L2** | **仍然缺**。数据在手（`response.request.content`），未保存 |
| 该次请求的服务端完成记录 | 3 | L1 | **已由 `requests-*.jsonl` 解决**，见 §1.2。L1 追加的是可查询性 |
| 上游 SSE 帧时序 | 3 | **L3** | **仍然缺**。完全无 |
| 上游错误响应体原文 | 2 | **L2** | **仍然缺**。只在日志 `detail` 留只言片语 |

**三个仍然缺的全部落在 L2 与 L3 上。** 所以：

- 本文的章节顺序是 L1 → L2 → L3，那是**数据模型的父子顺序**，不是实施顺序，不得读成优先级。
- 实施顺序上，**L2 的价值密度最高**：它一个人解决四次点名与两次点名的两个缺口，且它是 `export-cassette` 与 `replay` 两个端点的唯一数据来源。
- L1 仍然要先落，但理由是**结构性的**：L2 / L3 的行需要一个父行来挂，查询面需要一张能过滤的表。**不是因为它更急。**
- 这与 proposal §6.1 的分片表不矛盾（那张表里 L2 就排在 L1 之后一片），但**它给出的理由变了**。若日后需要在 L1 与 L2 之间取舍，按本节判，不按 proposal 的盘点排序判。

### 1.4 取证记录不是请求日志行

两者同源但不同物，不得互相替代：

- **请求日志行**是给人看的一行终端输出，由 `format_completion_line` 渲染，字段「有才打印」。
- **取证记录**是给机器查的结构化行，字段缺席必须与字段为空可区分（见 I4）。

它们共享 `RequestLine` 这一份聚合记录（`app.observability.request_log`），**这是有意的单写源**：同一事实不得在两条交付路径上各推导一遍。现在同一份 `RequestLine` 已经有三个下游——终端行、`requests-*.jsonl`、以及本 Spec 的 L1——所以这条纪律比 proposal 写作时更要紧：**任何新字段都加在 `RequestLine` 上，绝不在 L1 的写入路径里就地从 `_Trace` 再推一次。**

### 1.5 不变量

- **I1 一请求一条 L1。** 每一次进入 `_serve` 的请求恰好产生一条 L1，无论它如何退出。未注册 URL 的 404 由 FastAPI 自己的路由回答、从不进入 `_serve`，因此不产生 L1——这是既有的显式边界，不是漏洞。
- **I2 先写后分类。** L1 在请求开始时就以 provisional 形态落盘，终态是后续的更新，不是首次写入的条件。
- **I3 记录不得改变请求结果。** 取证路径的任何失败（磁盘满、库损坏、队列满、序列化失败）都不得改变响应体、状态码或响应时序，也不得抛到请求路径上。
- **I4 缺席可读。** 「没有观测到」与「观测到了空值」必须在记录上可区分。默认值不得伪装成观测结果：`NULL` 表示未观测，空字符串/空对象表示观测到了空。
- **I5 本地库不裁剪，导出才裁剪。** 见 §2.5。
- **I6 记录点在解析之前。** L3 记的是 `_counted_upstream` 看到的原始字节，位于所有 SSE 解析之前。**不得在 `BlockAssembler` 之后再记第二份**——那样记下来的东西恰好丧失了记录它的理由。
- **I7 查询不得拖慢请求处理。** 见 §6。这是用户点名的唯一危害，是设计约束而不是一般性能考量。
- **I8 不删，归档。** 取证记录到期后转入归档批次，不 `DELETE`。产品面不提供删除端点。

---

## 2. 数据模型

三张表加一张 spool 表，落在独立的数据库文件里（§8.2）。**不复用 `HistoryEntry` / `entries` 合同**：`HistoryEntry` 的字段集与 `_Trace` 交集很小，`writer._insert` 以无列名的 14 个位置参数写整行、按固定下标反序列化，加列要同步改写所有 positional SQL 与 reader。可以共用的是「单 writer + 有界队列 + `asyncio.to_thread` 下沉」这个实现模式。

### 2.1 `ForensicRequest`（L1）

| 字段 | 类型 | 可空 | 来源符号 | 说明 |
|---|---|---|---|---|
| `id` | TEXT PK | 否 | `_Trace.request_id`（`_serve` 里的 `uuid4()`） | **不是** `RequestContext.id`：body 解析失败时后者根本不存在 |
| `session_id` | TEXT | **是** | `identify_session(request.headers)[0]` | 必须从 ASGI 原始 `request.headers` 取。**不能用 `RequestContext.client_headers`**——它已被 `forwarded_client_headers` 的 allowlist 裁成 `anthropic-beta` / `anthropic-version` 两项，`SESSION_HEADERS` 一个都不在里面 |
| `agent_id` | TEXT | 否 | `identify_session(request.headers)[1]` | 该函数缺省返回 `"main"`，故非空 |
| `message_id` | TEXT | 是 | `_Trace.message_id`（即 `RequestContext.id`） | 与客户端 transcript 按 `message.id` 归组的连接点，见 §10.5 |
| `started_at` | TEXT ISO-8601 UTC ms | 否 | `_Trace.started_at`（`utc_timestamp()` 于 `_serve`） | **不得用 `_Trace.started`**，那是 `time.monotonic()`，跨进程无意义 |
| `ended_at` | TEXT ISO-8601 UTC ms | 是 | 终结时刻调用 `utc_timestamp()` | provisional 阶段为 `NULL`，这正是 I4 要保住的区分 |
| `duration_s` | REAL | 是 | `time.monotonic() - trace.started`，与 `_log_completion` 同源 | 单调时钟测时长、墙钟记时刻，两者各司其职 |
| `first_upstream_byte_s` | REAL | 是 | `_Trace.first_upstream_byte_s` | 相对 `_Trace.started` 的秒数 |
| `method` | TEXT | 否 | `_Trace.method` | 客户端入站方法 |
| `path` | TEXT | 否 | `_Trace.path` | 客户端入站路径。**不是上游路径**，后者在 L2 |
| `inbound_format` | TEXT | 是 | `_Trace.inbound_format`（`route.wire_format.value`） | 路由未识别时为空 |
| `count_tokens` | INTEGER 0/1 | 否 | `_Trace.count_tokens` | |
| `client_protocol` | TEXT | 是 | `_Trace.client_protocol`（`http_label` 后） | `H1` / `H2` / `WS` |
| `upstream_protocol` | TEXT | 是 | `_Trace.upstream_protocol` | 压缩过的显示标签；未压缩的 `http_version` 在 L2 的 `extensions` |
| `requested_model` | TEXT | 是 | `_Trace.requested_model` | |
| `resolved_model` | TEXT | 是 | `_Trace.model` | 路由从未定下模型时为空 |
| `status_code` | INTEGER | 是 | `_serve` / `_StreamAccounting.status_code` | 流式响应固定在响应头到达的那一刻，此后不变 |
| `status` | TEXT | 是 | `status_for(status_code, override=trace.status_override)` | 取值 `ok` / `fail` / `gone`；provisional 阶段写 `pending`，未终结记录永远停在 `pending` |
| `detail` | TEXT | 是 | `_Trace.detail` | 状态码说不出来的那句话 |
| `bytes_in` | INTEGER | 是 | `_Trace.bytes_in` | 实际发往上游的字节数，取自 `len(response.request.content)` |
| `bytes_out` | INTEGER | 是 | `_Trace.received` | 从上游收到的字节数。**不是发给客户端的字节数**——记录描述的是 proxy↔upstream 那一段 |
| `usage` | TEXT JSON | 是 | `_Trace.usage`（经 `_Trace.absorb`） | |
| `terminal_seen` | INTEGER 0/1 | 是 | `_Trace.terminal_seen` | |
| `stop_reason` | TEXT | 是 | `_Trace.stop_reason` | |
| `blocks` | INTEGER | 是 | `_Trace.blocks` | |
| `tools` | TEXT JSON array | 是 | `_Trace.tools` | |
| `thinking` | TEXT JSON array | 是 | `_Trace.thinking` | |
| `dialect` | TEXT | 是 | `_Trace.dialect.value`（`ReplyDialect`） | 决定 `tools` / `thinking` 该用谁的词 |
| `count_provider` | TEXT | 是 | `_Trace.count_provider` | 仅计数请求有 |
| `count_provider_reason` | TEXT | 是 | `_Trace.count_provider_reason` | |
| `attempts` | INTEGER | 是 | `_Trace.attempts`（`RequestContext.attempt_count`） | 与 L2 行数应当一致；不一致本身是线索，见 §4.2 |
| `upstream_conn` | TEXT JSON | 是 | `_Trace.upstream_conn`（`_snapshot_upstream_connection`） | 四种形态各有含义，**空对象表示从未尝试快照，不得与 `unavailable` 混同** |
| `pinned` | INTEGER 0/1 | 否，默认 0 | 仅由 `POST /history/api/entries/pin` 写 | 语义是「免于归档」，见 §7.5 |
| `archived_batch` | TEXT | 是 | 归档器写 | `NULL` 表示仍在热区 |
| `origin` | TEXT | 否，默认 `"serve"` | 记录器 | `serve` 或 `replay`；见 §5.6 |
| `replay_of` | TEXT | 是 | replay 端点 | 被重放的原记录 id |

> **proposal §3.1 的 `failed` 字段在本 Spec 中不存在。** proposal 写作期间工作树里出现过一个 `_Trace.failed`，当前 HEAD 上已不存在，取而代之的是 `_Trace.status_override: LogStatus | None`——一个值而不是一堆布尔，因为这些结局是互斥的。`failed` 的信息由 `status` 承载：`fail` 是失败，`gone` 是没人接收，两者不能合并（`gone` 在交互式客户端上是家常便饭，涂成红色会把真正的失败淹掉）。

**索引**：`(started_at DESC)`、`(session_id, started_at DESC)`、`(status, started_at DESC)`、`(resolved_model, started_at DESC)`、`(pinned)`、`(archived_batch)`。§6 的「列表只走索引列」指的就是这几列加上表里的定长小字段。

#### 2.1.1 与 `requests-*.jsonl` 的字段对账

按 §1.2，L1 不是从零开始。实测一条 `requests-20260821.jsonl` 记录的键恰为 `at` + `status` + `RequestLine` 的全部 28 个字段（`write_request_record` 的写法是 `{"at": …, "status": status, **asdict(line)}`，所以 `RequestLine` 加一个字段，JSONL 自动就有）。对账结果：

| 类别 | 字段 | 说明 |
|---|---|---|
| **JSONL 已有，L1 直接取同一份 `RequestLine`**（28 项） | `method`、`path`、`request_id`、`message_id`、`inbound_format`、`count_tokens`、`client_protocol`、`upstream_protocol`、`requested_model`、`model`、`status_code`、`started_at`、`duration_s`、`first_upstream_byte_s`、`bytes_in`、`bytes_out`、`usage`、`terminal_seen`、`stop_reason`、`blocks`、`tools`、`thinking`、`count_provider`、`count_provider_reason`、`dialect`、`attempts`、`detail`、`upstream_conn` | L1 的列名有两处改名：`request_id` → `id`、`model` → `resolved_model`。**改的是列名不是来源**，值仍取自同一个 `RequestLine` 字段 |
| **JSONL 已有、不在 `RequestLine` 上**（2 项） | `at`（`datetime.now(UTC)`，写盘时刻）、`status`（`status_for(status_code, override=…)` 的结果） | `status` 已经算好了，L1 不需要再推一次。`at` 是终结时刻的近似——它与 L1 的 `ended_at` 相差一次函数调用，但 **L1 仍取自己的 `utc_timestamp()`**，因为 L1 要在 `pending` 阶段就存在，而那时还没有 `at` |
| **L1 需要、JSONL 没有**（6 项） | `session_id`、`agent_id`、`ended_at`、`pinned`、`archived_batch`、`origin` / `replay_of` | `session_id` / `agent_id` 是查询面的主过滤维度（`sessions/*` 端点与 §7 的归档单位都建立在它上面），其余四项是取证库自己的生命周期状态，JSONL 没有对应物 |
| **结构性缺口，JSONL 天然给不了**（3 类） | provisional 行、attempt 维度、chunk 维度 | 见下 |

三类结构性缺口，是 L1 存在的真正理由：

1. **JSONL 里没有未终结的请求。** `write_request_record` 只从 `_log_completion` 调用，也就是只在终结时写一次。所以进程被 kill、请求永久挂起、终结写入本身失败这三种情况，在 JSONL 上都表现为「什么都没有」——而 I2 的「先写后分类」要的恰恰是这三种情况留下痕迹。**这是 L1 相对 JSONL 唯一的实质性能力差，不是格式差。**
2. **JSONL 只有 `attempts` 这个计数，没有 attempt 的身份。** 哪一次 attempt 慢、发了什么、上游回了什么，一个整数答不了。
3. **JSONL 没有 chunk。**

**反过来，JSONL 相对 L1 也有一样东西：它不依赖任何子系统就绪。** 没有队列、没有线程池、没有 schema 迁移，`mkdir` 加 `open` 就写。取证库出问题的那一刻恰恰是最需要记录的时刻，这个优点不该被消掉——这是 §9.6 里我建议「并存」的主要理由。

### 2.2 `UpstreamExchange`（L2）

主键 `(request_id, attempt_index)`。

| 字段 | 类型 | 可空 | 来源符号 | 说明 |
|---|---|---|---|---|
| `request_id` | TEXT | 否 | L1 的 `id` | 外键语义，但**不依赖 SQLite FK cascade**（§7.4） |
| `attempt_index` | INTEGER | 否 | `Attempt.index` | |
| `provider_name` | TEXT | 是 | `RequestContext.provider_name` | |
| `endpoint` | TEXT | 是 | `Attempt.endpoint.value`（`ModelEndpoint`） | |
| `upstream_method` | TEXT | 是 | 实际发出的 `httpx2.Request.method` | 新观测合同产出，见 §3.4 |
| `upstream_url` | TEXT | 是 | 实际发出的 `httpx2.Request.url` 的完整字符串 | |
| `upstream_path` | TEXT | 是 | 同上的 `.path` | cassette 必需；`ForensicRequest.path` 是入站路径，不能替代 |
| `authenticated` | INTEGER 0/1 | 是 | 实际发出的请求头是否含 `authorization` | 与 `Interaction.authenticated` 同义。**只记事实，值另见 `request_headers`** |
| `request_headers` | TEXT JSON | 是 | 实际发出的 `httpx2.Request.headers`，**完整** | 见 §2.5 |
| `request_body` | BLOB | 是 | `response.request.content` | **实际序列化发出的字节**。不得用 `Attempt.payload`——那是发送前的字典，翻译会重写 payload，被计费和 tokenize 的是发出去的那一份 |
| `request_body_bytes` | INTEGER | 是 | `len(request_body)` | 与 `ForensicRequest.bytes_in` 在最终 attempt 上应当相等 |
| `request_body_digest` | TEXT | 是 | `sha256(request_body).hexdigest()` | 便于跨请求找同一个 body |
| `payload_snapshot` | TEXT JSON | 是 | `Attempt.payload` | **额外保留**，不是 `request_body` 的替代：两者的差就是序列化层做过什么，这个差本身有取证价值 |
| `status` | INTEGER | 是 | `Attempt.status_code` | 连接失败时为 `NULL` |
| `response_headers` | TEXT JSON | 是 | `httpx2.Response.headers`，**完整不裁剪** | 见 §2.5 |
| `extensions` | TEXT JSON | 是 | `response.extensions` 中可序列化的部分 | 必含 `http_version`。**不得序列化 `network_stream`**，它是活的对象；连接身份走 `ForensicRequest.upstream_conn` |
| `error_kind` | TEXT | 是 | 失败异常的类名 | |
| `error_message` | TEXT | 是 | `Attempt.error` | 已被 `normalize_upstream_error` 归一 |
| `error_body` | TEXT | 是 | `UpstreamError.body` / `UpstreamRejected.body` | 上游错误响应体**原文**，由 `_response_parts` 从 `response.text` 取。这是排障盘点里被点名两次的缺口，`Attempt.error` 那个字符串不能替代 |
| `retry_reason` | TEXT | 是 | `reason_for(error)` 的取值 | 为什么重试了（或为什么没重试） |
| `rate_limit_wait_s` | REAL | 是 | `RequestContext.extras["rate_limit_wait_s"]` | 这次 attempt 在限流器上等了多久 |
| `started_at` | TEXT ISO | 是 | attempt 开启时刻 | |
| `ended_at` | TEXT ISO | 是 | attempt 收尾时刻 | 流式 attempt 的收尾是流结束，不是响应头到达 |
| `duration_s` | REAL | 是 | 两者之差（用 monotonic 测） | |
| `chunk_count` | INTEGER | 否，默认 0 | L3 收敛时写 | |
| `chunk_bytes` | INTEGER | 否，默认 0 | 原始字节总数 | |
| `chunks_blob` | BLOB | 是 | 见 §2.3 | |
| `blob_codec` | TEXT | 是 | `zstd-3` 或 `none` | |
| `blob_bytes` | INTEGER | 是 | 压缩后字节数 | **容量统计按这个数，不是 `chunk_bytes`** |
| `spool_open` | INTEGER 0/1 | 否，默认 0 | 见 §3.3 | 为 1 表示这次 attempt 的 chunk 还散落在 spool 表里，未收敛 |
| `truncated` | TEXT | 是 | 见 §4.2 | 记录哪一部分因为 best-effort 被丢了 |

**索引**：`(request_id, attempt_index)` 主键；`(request_body_digest)`；`(spool_open)`。

### 2.3 `UpstreamChunk`（L3）与 chunk blob

主键 `(request_id, attempt_index, sequence)`。

| 字段 | 类型 | 可空 | 来源 | 说明 |
|---|---|---|---|---|
| `request_id` | TEXT | 否 | | |
| `attempt_index` | INTEGER | 否 | | |
| `sequence` | INTEGER | 否 | 该 attempt 内从 0 起单调递增 | |
| `arrived_at` | TEXT ISO-8601 UTC ms | 否 | 该 chunk 在 `_counted_upstream` 被取到的墙钟时刻 | **取证依据，不是可选项**。没有它，「上游沉默 242 秒」这类问题记了也答不了，`sequence` 推不出时刻 |
| `arrived_offset_s` | REAL | 否 | `time.monotonic() - trace.started` | 同一请求内做时序分析用，免受墙钟跳变影响 |
| `byte_length` | INTEGER | 否 | `len(chunk)` | |
| `blob_offset` | INTEGER | 否 | 该 chunk 在解压后字节流中的起始偏移 | 与 `byte_length` 一起还原 chunk 边界 |

**chunk 字节不逐行存。** 一次 attempt 的所有 chunk 按到达顺序首尾相接成一段字节流，整体做一次压缩存进 `UpstreamExchange.chunks_blob`。理由是实测：整请求压一次比逐帧独立压小 1.16×～1.49×，且逐帧压缩会丢掉跨帧的重复。

**压缩器用标准库 `compression.zstd`**（Python ≥ 3.14，`requires-python = ">=3.14"`，已实测可用），默认 level 3。**不引入 `zstandard` 运行时依赖**——它当前只在 `[dependency-groups].dev` 里，注释明写「Nothing the proxy itself runs touches this」，把它提到运行时会推翻那句话。压缩失败时 `blob_codec` 写 `none` 并存原始字节，不丢数据。

**空 attempt**（非流式，或流式但一个 chunk 都没到）：`chunk_count = 0`，`chunks_blob` 为 `NULL`，`blob_codec` 为 `NULL`。这与「压了但是空的」可区分（I4）。

### 2.4 `ChunkSpool`（在途缓冲）

主键 `(request_id, attempt_index, sequence)`，字段同 `UpstreamChunk` 加一列 `payload BLOB NOT NULL`（**未压缩**）。

这张表是 §3.3 的落点，存在的全部理由是：1.8 要的「按 attempt 合并压缩」只有在 attempt 结束时才做得到，而进程被 kill 恰恰发生在结束之前。代价是在途请求占用未压缩体积，收益是进程死的时候那些字节还在。**二者不可兼得，本 Spec 选保住证据。**

收敛完成后该 attempt 的 spool 行被删除，`UpstreamExchange.spool_open` 置 0。启动时若发现 `spool_open = 1` 的行，见 §3.5。

### 2.5 头部与脱敏边界

**取证库本身不脱敏。** 它落在本机用户自己的数据目录，完整记录含临时 token 不构成本项目认定的敏感面。请求头与响应头都**存完整的**。

**不得在取证表上套 cassette 的 headers allowlist。** `KEPT_RESPONSE_HEADERS` 那三项（`content-type` / `transfer-encoding` / `cache-control`）是 cassette 的产物合同，属于 §5.7 的导出阶段。取证表若提前裁剪，会丢掉上游 request id 这类只在响应头里出现的取证事实——而那正是向上游报障时唯一能引用的凭据。

脱敏只发生在**导出**这一步：`export-cassette` 走 `VOLATILE_REQUEST_HEADERS` 的丢弃、`KEPT_RESPONSE_HEADERS` 的 allowlist、`REDACTED_RESPONSE_FIELDS` 的按字段名递归替换、`PINNED_RESPONSE_FIELDS` 的固定值改写，因为 cassette 要进版本库。

> 这条立场是按项目既有立场**推定**的，不是用户裁决过的（proposal §3.5 已如此声明）。列在这里供否决。

---

## 3. 采集点与时机

### 3.1 生命周期

一条记录按下面的顺序推进。**每一步都可以是最后一步**——记录在任意一步之后被读到，都必须是自洽的、能说清自己停在哪里的。

| # | 时机 | 动作 | 落在哪 |
|---|---|---|---|
| 1 | `_serve` 里 `_Trace` 构造完、`chain.active_requests.add` 之后，`_dispatch` 之前 | 写 provisional L1（`status = "pending"`，`ended_at = NULL`） | L1 |
| 2 | 每次 attempt 开启（驱动 `begin_attempt` 之后、真正发出之前） | 写 L2 行的开头部分（`attempt_index`、`endpoint`、`started_at`、`payload_snapshot`） | L2 |
| 3 | 该 attempt 拿到 `httpx2.Response`（或拿到失败异常） | 补齐 L2 的上行快照与响应元数据 | L2 |
| 4 | 每个 chunk 在 `_counted_upstream` 被取到、`yield` **之前** | 写一行 spool（未压缩、带 `arrived_at`） | ChunkSpool |
| 5 | 该 attempt 收尾 | spool 收敛为单个 blob + `UpstreamChunk` 元数据行，删 spool 行，写 `ended_at` | L2 + L3 |
| 6 | 请求终结（幂等终结器） | 更新 L1 为终态 | L1 |
| 7 | 归档器周期运行 | 搬迁已终结、非 pinned、已过热区的记录 | 见 §7 |

第 4 步写在 `yield` 之前而不是之后：`yield` 之后恢复不了的那一次（客户端断连使生成器被关闭）恰恰是最该有记录的一次。代价是记录里可能有一个从未交付下去的 chunk——但 L3 描述的本来就是 proxy↔upstream 那一段，「我们收到了」是真的。

### 3.2 采集点分工

| 采什么 | 在哪采 | 为什么不能换地方 |
|---|---|---|
| L1 provisional | `_serve`，在 `_dispatch` 之前 | 再晚就覆盖不到 `await request.body()` 抛错这条路径 |
| L1 终态 | 外层幂等 finalizer：非流式补洞后的 `_serve`，流式的 `_StreamAccounting.finish` | **不能用 `app.pipeline.events` 的 `request.succeeded` 代替**——它在拿到响应头之后就发布，此时 stream 尚未被消费，`terminal_seen` / `usage` / `stop_reason` / `received` 都还不存在 |
| L2 每 attempt | 驱动的 attempt 边界 | `_dispatch` 那个位置只看得到**最终**那次交换的 `response`，前序 attempt 的 response 已经没了 |
| L3 原始 chunk | `_counted_upstream`，不改字节地旁路 | 位于所有解析之前。`SseEvent` 有损：`parse_frame` 用 `errors="replace"` 解码、丢注释行（**包括保活帧**）、丢不认识的字段名、剥前导空格、用 `"\n"` 重接 data 行，从它无法还原原始字节，更没有输入 chunk 边界 |

> **raw chunk 采集点不等于配置里的 `on_upstream_sse_block_ready`。** 后者的语义是「一个完整的块」，raw chunk 是任意边界的传输分片。本次不实现那六个钩子点，但采集点的位置要按它们的语义留好接缝（`on_upstream_request_ready` 对应第 3 步之前，`on_upstream_sse_block_ready` 对应块装配之后），日后接钩子分发不用重开刀。

### 3.3 spool 收敛

「该 attempt 收尾」的定义：

- **非流式**：`_dispatch` 读完 `response.json()` / `response.content` 之后。此时 chunk 数为 0，收敛是一次空操作，只写 `ended_at`。
- **流式**：`_counted_upstream` 所在的生成器链走到终点或被关闭时。三种结局（上游流自然结束、上游撕裂、下游走人）都必须触发收敛，因此收敛动作挂在 `finally` 语义的位置上，与 `_tracked_delivery` 保证 `accounting.finish()` 被调用的方式同构。
- **失败 attempt（连不上、超时、非 2xx 直接抛）**：驱动的失败分支收尾，chunk 数通常为 0。

收敛动作：读该 attempt 的全部 spool 行 → 按 `sequence` 拼接 payload → 压缩 → 一个事务里写 `chunks_blob` / `blob_*` / `chunk_count` / `chunk_bytes`、批量插入 `UpstreamChunk` 元数据行、删除 spool 行、`spool_open` 置 0。**必须是同一个事务**，否则一次崩溃会留下既没有 blob 也没有 spool 的空洞。

### 3.4 L2 需要的观测合同扩展

当前 `DirectDriver._publish` 的处理器签名是 `Handler[RequestContext] = Callable[[RequestContext], Awaitable[None]]`，只递交 `RequestContext`。`DriverOutcome` 持有 `response`，但**不递交给订阅者**。所以订阅 `attempt.succeeded` 拿不到 `httpx2.Response`，也就拿不到 §2.2 里六样 L2 必需字段中的五样。

规范要求：**上游交换的观测合同必须显式携带 `httpx2.Request`、`httpx2.Response` 与失败异常三者中实际存在的那些，不得靠遍历异常链去重建。** 具体地：

- 成功 attempt：`response.request`（方法、URL、请求头、`content`）与 `response`（状态、响应头、`extensions`）。
- 失败 attempt：归一后的 `PipelineError` 携带 `status_code` / `headers` / `body`（`normalize_upstream_error` 已经从 `_response_parts` 里取好了），实际发出的请求对象由合同显式带出。**不得依赖 `raise normalized from error` 留下的 `__cause__` 去摸 `.response.request`**——那是实现细节，一次重构就会静默失效，且失效时记录只是变空，不会有任何测试变红。

这个扩展是 L2 的真实成本，proposal §1.3 已列明。合同的具体形状（新事件、新 tap 对象，还是给 `Handler` 加一个 payload 类型参数）留给实施切片，但上面这条「显式携带」是冻结的。

### 3.5 前置条件（不解决则记录不可信）

- **P1 L1 采集点必须先补成 exactly-once。** 当前 `_log_completion` 只有两个调用点。流式路径是真 exactly-once（`_StreamAccounting.finish` 自带 `done` 幂等标记，生成器的 `finally` 与 `_AccountedStreamingResponse.__call__` 的 `finally` 谁先到谁记录）。**非流式路径有洞**：`_serve` 捕获 `_dispatch` 抛出的 `BaseException` 后只从 active registry 删除再 `raise`，不记录。`await request.body()`（客户端中途断连）、`response.json()`、翻译层的非预期异常都走这条路。`_log_completion` 的 docstring 写的「每一条退出路径都必须产出且仅产出一条」是愿景，不是事实。**补洞后 I1 才成立。**
- **P2 测试不得往用户真实数据目录写库。** 现状是 `~/.local/share/ghc-api-proxy/history.db` 里全是测试流量且仍在增长。取证库另用独立文件名（§8.2）是隔离，测试库改落 `tmp_path` 是缺陷修复，**两者都做**。
- **P3 启动时的 spool 清理。** 进程启动时若发现 `spool_open = 1` 的 `UpstreamExchange`，按当时能拿到的 spool 行做一次收敛，并在该行的 `truncated` 里写 `spool-recovered-at-startup`。**不得静默丢弃**：那些字节正是崩溃现场。

> **未终结记录本身是一条线索，但因果要说准。** `status = "pending"` 只说明「这条请求没有走到终结点」。可能是进程死了，也可能是请求永久挂起，还可能是终结写入本身失败了。三者的排查方向不同，记录不能替读者做这个判断，端点也不得把它渲染成任何一种。

---

## 4. 持久化保证

按裁决 C1：**L1 durable，L2/L3 bounded best-effort**。

### 4.1 L1 durable

- L1 的写入（provisional 与终态）进入 writer 队列时**不允许因队列满而丢弃**：队列满时背压（`await queue.put`），不是丢。
- 但 I3 优先：背压有上界。L1 写入带超时（`history.write_timeout_s`，默认 5 秒）；超时后放弃该次写入、把 `forensic_l1_dropped_total` 加一、记一条 WARNING，**绝不把异常抛回请求路径**。「durable」的含义是「不会因为队列忙就悄悄丢」，不是「宁可挂住请求也要写进去」。
- L1 的写入必须在 `asyncio.to_thread` 之下完成实际的 SQLite 调用，事件循环上不做磁盘 I/O。
- provisional 写入是 fire-and-forget（不等 ack），终态写入等 ack。理由：provisional 丢了还有终态兜底，终态丢了这条记录就永远停在 `pending`，会被误读成崩溃现场。

### 4.2 L2 / L3 bounded best-effort

- 队列满时**立即丢弃并计数**，不背压，不阻塞。
- 丢弃必须在记录上留痕，不能只体现在计数器上：被丢的是 L2 行时，L1 的 `attempts` 与实际 L2 行数会不一致，端点必须把这个不一致原样呈现（`meta.exchanges_missing`）；被丢的是 chunk 时，在 `UpstreamExchange.truncated` 里写 `chunks-dropped:<n>`。**「记录看着完整但其实丢过东西」是本 Spec 最不能接受的形态。**
- spool 行也受同一个界约束。spool 表的总字节数超过 `history.spool_max_bytes` 时，新 chunk 不再落 spool，`truncated` 写 `spool-full`，但**已经落下的不回滚**。

### 4.3 失败的处理

- SQLite 报 `SQLITE_BUSY` / `SQLITE_LOCKED`：按现有 `_insert_with_retry` 的模式在 writer 线程里重试到本次写入的 deadline。
- 致命错误（`SQLITE_IOERR` / `READONLY` / `CORRUPT` / `FULL`，判据同现有 `_is_fatal`）：记录子系统整体转入 `fatal` 态，此后所有写入立即返回失败并计数，查询端点回 503 并在响应体里说明原因。**请求处理不受影响**（I3）。
- **`PRAGMA busy_timeout` 必须设成非 0。** 现有 `writer._open` 设的是 `busy_timeout=0`，意思是一撞上锁就立刻抛 `SQLITE_BUSY`，全部靠 `_insert_with_retry` 在应用层自旋补救；而本 Spec 的形态是「一个 writer 连接加若干只读连接」，checkpoint 之类的短暂互斥完全正常。**新 writer 取 5000 毫秒**，理由是它自己的形态，不是别处写过这个数（见 §10.9）。
- **`PRAGMA foreign_keys` 的现状要说清**：现有 `writer._open` 没有开它，所以 FK cascade 不工作。新表**不依赖 cascade**，跨表的搬迁与清理一律在同一个 writer 事务里显式做（§7.4）。

### 4.4 计数暴露

计数走已有的 Prometheus 面（`ops_routes` 已经 `generate_latest(REGISTRY)`），**不新增计数端点**：

| 指标 | 类型 | 含义 |
|---|---|---|
| `forensic_l1_written_total{phase="provisional"\|"final"}` | Counter | |
| `forensic_l1_dropped_total{reason="timeout"\|"fatal"}` | Counter | |
| `forensic_l2_written_total` / `forensic_l2_dropped_total` | Counter | |
| `forensic_l3_chunks_written_total` / `forensic_l3_chunks_dropped_total` | Counter | |
| `forensic_queue_depth` | Gauge | writer 队列当前深度 |
| `forensic_spool_bytes` | Gauge | spool 表当前未压缩字节数 |
| `forensic_hot_bytes` | Gauge | 热区**压缩后**字节数，见 §7.3 |
| `forensic_archive_runs_total{result="ok"\|"fail"}` | Counter | |
| `forensic_query_seconds` | Histogram，按 `endpoint` 分标签 | §6 的检验读它 |
| `forensic_query_pool_saturation` | Gauge | 查询线程池当前占用比 |

`forensic_l1_dropped_total` 与 `forensic_l3_chunks_dropped_total` 恒为 0 是正常状态；它们不为 0 时读到的记录不完整，这一点必须能从指标上看出来，而不是靠翻记录发现。

---

## 5. HTTP 端点契约

### 5.0 通用约定

**路由模块的归属。** 这些端点当前只存在于旧链路的 `app/routes/history.py`，而 `app.routes.*` 整个包在新链路的边界禁区里（`tests/unit/test_module_boundaries.py` 断言新链路 import 闭包中 `app.routes` 前缀的模块数为 0）。**在新链路下另建路由模块，不叫 `app.routes`**，写法参照 `app.server.ops_routes`（它就是为同一个理由从零写的，其模块 docstring 明写「History and the management API need state this chain does not own yet, and are absent rather than answered with a plausible stub」——本 Spec 落地后那句话要一并更新）。**不调整边界断言**：那是有意为之的产品决策，为了少写一个模块名去动它不划算。

**动作式而非 RESTful**（用户裁决）：路径形如 `POST /history/api/<resource>/<action>`，标识符走请求体而不是路径段。

| 约定 | 规范 |
|---|---|
| 方法 | 一律 `POST`。唯一例外是 `GET /history/ws` |
| 请求 `Content-Type` | `application/json`。缺失或不匹配 → 415 |
| 请求体 | JSON 对象。空体、`null`、`{}` 三者等价于「全部用默认值」 |
| 未知字段 | **400 拒绝**，`code` 为 `unknown_field`，`field_path` 指出是哪个。理由：本项目的调研主要由 subagent 发起，一个拼错的过滤器名若被静默忽略，返回的是一份看着正常、实则没过滤的结果——那比报错危险得多 |
| 成功响应 | `200`，体为 JSON 对象，恒含 `data`，可含 `meta` |
| 错误响应 | JSON 对象 `{"error": {"type", "message", "code"?, "field_path"?}}`，与 `app.server.handler` 的 `error_body` 同形 |
| 时间 | 请求与响应中的时刻一律 ISO-8601 UTC，与 `utc_timestamp()` 同精度（毫秒） |
| 认证 | 无。这些端点与推理端点同在一个监听面上，本项目不为它们单设认证 |

**状态码的含义**（除各端点另行说明外）：

| 码 | 含义 |
|---|---|
| 200 | 成功。**「查到 0 条」是 200，不是 404** |
| 400 | 请求体不合法：不是对象、未知字段、字段类型错、`limit` 越界 |
| 404 | 按 id 指名的记录不存在 |
| 409 | 记录存在但状态不允许该动作（例：对没有任何 L2 行的记录 replay） |
| 415 | `Content-Type` 不对 |
| 503 | 记录子系统未启用、尚未就绪，或处于 `fatal` 态。响应体的 `message` 必须说明是三者中的哪一种 |

**分页**。列表类端点统一用 `limit` + `cursor`：

- `limit`：整数，默认 50，**上限 500**。超出上限 → 400，不静默截断（静默截断会让调用方以为自己看到了全部）。
- `cursor`：不透明字符串，来自上一页 `meta.next_cursor`。内容是 `(started_at, id)` 的编码，因此排序恒为 `started_at DESC, id DESC`，翻页期间新写入的记录不会造成重复或跳过。
- `meta.next_cursor` 为 `null` 表示没有下一页。

**列表端点绝不返回大字段**（§6 Q4）：不含 `request_body`、`response_headers`、`request_headers`、`payload_snapshot`、`chunks_blob`，也不解压任何 blob。

### 5.1 `POST /history/api/entries/list`

请求体（全部可选）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `limit` / `cursor` | | 见上 |
| `session_id` | string | 精确匹配。传 `null` 显式筛「无会话」的记录 |
| `agent_id` | string | |
| `status` | string \| string[] | `pending` / `ok` / `fail` / `gone` |
| `status_code` | int \| int[] | |
| `resolved_model` / `requested_model` | string | |
| `inbound_format` | string | |
| `path` | string | 入站路径，精确匹配 |
| `since` / `until` | ISO 时刻 | 对 `started_at` 的闭开区间 `[since, until)` |
| `pinned` | bool | |
| `include_archived` | bool | 默认 `false`。为 `true` 时同时查归档面，代价见 §7.4 |
| `min_attempts` | int | 便于直接捞出重试过的请求 |
| `has_error_body` | bool | 便于直接捞出上游有原话的请求 |

响应：

```json
{
  "data": [ { "…ForensicRequest 的索引列与定长字段…" } ],
  "meta": {
    "count": 50,
    "limit": 50,
    "next_cursor": "…",
    "hot_only": true
  }
}
```

`data` 每项含 §2.1 全部字段**除 `usage` / `tools` / `thinking` / `upstream_conn` 之外**的部分，外加 `exchange_count`（该记录的 L2 行数）与 `exchanges_missing`（`attempts - exchange_count`，非 0 表示有 L2 被丢弃）。

### 5.2 `POST /history/api/entries/get`

请求体：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `id` | string | 必填 | |
| `include_exchanges` | bool | `true` | L2 行，含完整头部与 `payload_snapshot` |
| `include_bodies` | bool | `false` | L2 的 `request_body` 与 `error_body` 原文 |
| `include_chunks` | bool | `false` | L3 元数据行（`sequence` / `arrived_at` / `arrived_offset_s` / `byte_length` / `blob_offset`）。**不含字节** |
| `include_chunk_bytes` | bool | `false` | 解压 blob 并返回 chunk 字节。为 `true` 时 `include_chunks` 被强制视为 `true` |
| `attempt_index` | int \| null | `null` | 只取某一次 attempt |

响应：

```json
{
  "data": {
    "request": { "…ForensicRequest 全字段…" },
    "exchanges": [ { "…UpstreamExchange…", "chunks": [ … ] } ]
  },
  "meta": { "exchanges_missing": 0, "truncated": [] }
}
```

chunk 字节的编码沿用 cassette 的做法：能按 UTF-8 解码就给 `{"text": "…"}`，否则给 `{"base64": "…"}`。理由是这份东西的读者是人和 subagent，可读性压过体积。

**`include_chunk_bytes` 是唯一会触发解压的读路径**，`meta` 必须回报 `decompressed_bytes`，让调用方知道自己拿了多大一坨。

### 5.3 `POST /history/api/entries/pin`

请求体 `{"id": "…"}`。响应 `{"data": {"id": "…", "pinned": true}}`。记录不存在 → 404。

**已归档的记录不能 pin**（`archived_batch` 非 `NULL`）→ 409，`message` 说明它已在归档批次里、pin 只影响是否被归档。

### 5.4 `POST /history/api/entries/unpin`

同上，`pinned` 为 `false`。对未 pin 的记录 unpin 是成功的空操作（幂等）。

### 5.5 `POST /history/api/sessions/list` 与 `POST /history/api/sessions/get`

`sessions/list` 请求体：`limit` / `cursor` / `since` / `until` / `agent_id` / `include_archived`。响应 `data` 每项是一个会话聚合（§7.2）。

`sessions/get` 请求体 `{"session_id": string|null, "include_entries": bool = true, "limit": int = 200}`。响应：

```json
{
  "data": {
    "session": { "…SessionSummary…" },
    "entries": [ { "…与 entries/list 同形的摘要…" } ]
  },
  "meta": { "count": 12, "next_cursor": null }
}
```

`session_id` 传 `null` 是合法的，取「没有会话头的那些请求」；它们**不聚成一个巨批**，按 UTC 日切分，`SessionSummary.id` 形如 `anon:2026-08-21`（§7.1）。

### 5.6 `POST /history/api/entries/replay`

用记录下来的**真实 outbound body** 重新打一次上游，替代手写 curl 探针。

请求体：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `id` | string | 必填 | |
| `attempt_index` | int | 最后一次 attempt | |
| `stream` | bool \| null | `null` | `null` 表示沿用记录里的 stream 与否；显式给值可以把同一个 body 换个模式再打一次 |
| `record` | bool | `true` | 是否把这次重放本身记进取证库 |

行为规范：

- 发出的是 `UpstreamExchange.request_body` 的**原字节**，不是从 `payload_snapshot` 重新序列化。凭据、`user-agent` 之类的身份头由当前的 `app.ghc_client.headers` 现造，**不重放记录里的旧凭据**——旧的多半已过期，重放它只会得到一个 401 并掩盖真正想问的问题。
- 记录里没有 `request_body`（该 attempt 的 L2 被丢了、或压根没走到发出）→ 409。
- `record = true` 时，这次重放产生一条新的 L1，`origin = "replay"`，`replay_of = <原 id>`。这是我的**推定**：重放本身就是一次真实的上游交换，不记它等于在取证库里开一个不留痕的旁路。列在 §9.4 供裁决。
- 响应：

```json
{
  "data": {
    "replay_request_id": "…",
    "status": 200,
    "headers": { "…完整…" },
    "duration_s": 3.2,
    "chunk_count": 412,
    "body": "…" ,
    "recorded": { "status": 400, "duration_s": 0.4, "chunk_count": 0 },
    "differs": ["status"]
  }
}
```

`differs` 只做**浅层对照**（status、是否流式、chunk 数量级），不做内容 diff。内容 diff 属于调用方的事，端点提供的是两边的原始事实。

### 5.7 `POST /history/api/entries/export-cassette`

请求体：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `id` | string | 必填 | |
| `attempt_index` | int | 最后一次 | |
| `scope` | `"interaction"` \| `"request"` | `"interaction"` | 见下 |
| `path` | string | 无 | 写到哪。缺省时只在响应里返回 cassette 的 JSON，不落盘 |
| `overwrite` | bool | `false` | |

**`scope` 必须显式，因为两种语义不能由一个动词同时承诺**（proposal §1.9）：

- `interaction`：单次上游交换的 delivery fixture，一个 `Interaction`。
- `request`：该请求的全部 attempt，多个 `Interaction` 按 attempt 顺序排列。

**都不等于完整的 `recorded_chain` cassette**——后者往往还含 token exchange 与 models interaction（当前 `anthropic_to_responses_stream.json` 有 3 个），而那些交换不经过本 Spec 的采集点。响应的 `meta.scope_note` 必须原样说明这一点，导出的 cassette 里 `source` 字段写 `forensic:<request_id>:<attempt_index>`。

**导出只 scrub 与 encode 已记录的真实字段，不补猜测值。** `from_history.py` 之所以能产出可读 cassette，是因为它人为填入 POST、调用者给的 path、200、`content-type`、HTTP/1.1；那是对旧历史固件的公开证据降级，**不得成为新取证系统凭空补事实的模式**。某个 `Interaction` 必需字段在记录里缺失时，端点回 409 并列出缺了哪些，而不是填一个像样的值。

**codec 必须先提升为共享模块。** 导出端点若直接用 `tests/int/recorded/cassettes.py`，会让生产代码 `import tests.*`。正解是把 `Interaction` / `Cassette` 的编解码与 scrubber 提升为可安装模块，测试与本端点同时依赖它；`VOLATILE_REQUEST_HEADERS`、`KEPT_RESPONSE_HEADERS`、`REDACTED_RESPONSE_FIELDS`、`PINNED_RESPONSE_FIELDS`、`CASSETTE_VERSION` 随之搬家，**测试侧不得留一份副本**。

### 5.8 `POST /history/api/archives/list`

请求体 `limit` / `cursor` / `since` / `until`。响应 `data` 每项：

```json
{
  "batch_id": "2026-08-21T03:00:00Z-000",
  "created_at": "…",
  "location": "…",
  "sessions": 12,
  "requests": 418,
  "bytes": 9_400_000,
  "span": { "from": "…", "to": "…" }
}
```

`location` 的形态取决于 §9.2 的裁决。

### 5.9 `GET /history/ws`

实时推送。协议：

- 建立后服务端发一条 `{"type": "hello", "version": 1, "since": "<ISO>"}`。
- 此后每条消息是 `{"type": "request.started"|"request.finished"|"attempt.finished", "data": { … }}`，`data` 与 `entries/list` 的摘要同形。
- **不推 chunk 级事件**：一次流式请求的 chunk 有数千个，推它们会让这条 WebSocket 变成第二条上游流。
- **推送是 best-effort**：发送失败即断开该连接，与现有 `WebSocketManager.broadcast` 的做法一致。推送队列有界，满时丢弃并计数，**不得反压请求路径**（I3）。
- 客户端可发 `{"type": "subscribe", "filter": {"session_id": "…"}}` 收窄。过滤在服务端做。

---

## 6. 查询隔离

用户点名的硬约束（I7）落成下面七条。它们是规范条款，不是建议。

| # | 条款 | 堵的是哪条失效路径 |
|---|---|---|
| **Q1** | 查询用**独立的只读连接**（`file:…?mode=ro`，URI 模式），与 writer 的独占连接分离。WAL 下读不阻塞写、写不阻塞读 | 查询与写入争同一个连接 |
| **Q2** | 每一次查询的 SQLite 调用都在 `asyncio.to_thread` 之下完成，**事件循环上不执行任何 SQLite 调用**，包括看着很便宜的 `COUNT(*)` | 查询在事件循环上跑，一次慢查询停住整个进程 |
| **Q3** | 查询用**独立的小线程池**（`history.query_workers`，默认 2），不与 `asyncio.to_thread` 的默认线程池共用 | 一次大查询饿死请求路径上的线程。默认线程池同时承载 tokenization、文件写入等请求路径工作 |
| **Q4** | 列表查询只走索引列与定长小字段，**绝不触碰任何 BLOB**。解压只发生在 `entries/get` 且 `include_chunk_bytes = true`、以及 `export-cassette` | 列表查询顺手解压大字段 |
| **Q5** | **读路径一条都不许进 writer 队列。** 写路径的动作（pin / unpin）走 writer 队列，但用单条 ack（`submit` 的 future），**不得 `await queue.join()`** | 现有 `reap()` 就是 `await self._queue.join()`，那是写路径的同步模式；查询用它会把自己挂在别人的写入后面 |
| **Q6** | 强制 `limit`（默认 50、上限 500）、按索引列过滤、无全表扫描。带 `LIKE '%…%'` 的模糊过滤本 Spec 不提供 | 无界查询 |
| **Q7** | 查询侧有并发上限（`history.query_concurrency`，默认 4）。超出的请求在队列里等，超过 `history.query_timeout_s`（默认 30）返回 503 而不是无限等 | 一次调研脚本并发打进来把线程池占满，之后每个查询都在排队且没人知道 |

**可证伪的检验**（proposal §4.1）：在持续请求负载下反复打列表与详情查询，请求侧的 p99 不出现可归因于查询的抬升。**这是一个检验，不是一道门**——它用来发现问题，不用来阻断交付。手段用 mock upstream 即可，判据换个上游依然成立。

**旧服务的成因不在这七条里，但也要记住**：`copilot-api-js` 的问题是同步 `bun:sqlite` 落在请求路径上。本 Spec 的对应约束是 Q2 加上 §4.1 的「L1 写入也在 `to_thread` 之下」——**写路径与读路径都不许在事件循环上碰磁盘**。

---

## 7. 会话聚合与归档

裁决是**全量记录 + 按会话聚合 + 定期归档化**，不是淘汰式 reaper。

### 7.1 会话如何识别

用 `app.history.sessions` 的 `identify_session(headers)`，输入是 `_serve` 拿到的**原始** `request.headers`（理由见 §2.1 的 `session_id` 行）。它按 `SESSION_HEADERS` 的顺序取第一个非空值，取不到返回 `None`；`agent_id` 取 `x-claude-code-agent-id`，缺省 `"main"`。

**无会话的记录不聚成一个巨批。** `session_id` 为 `NULL` 的记录按 `started_at` 的 UTC 日归入合成会话 `anon:<YYYY-MM-DD>`。这个 id 只存在于聚合与归档面，**不写回 `ForensicRequest.session_id`**——那一列必须忠实反映「客户端有没有告诉我们会话」（I4）。

### 7.2 `SessionSummary`

派生视图，不是第四张实体表（会话的事实全在 L1 里，再存一份就有两个真值）。字段：

| 字段 | 来源 |
|---|---|
| `id` | `session_id`，或合成的 `anon:<date>` |
| `agent_ids` | 该会话出现过的 `agent_id` 集合 |
| `first_at` / `last_at` | `MIN/MAX(started_at)` |
| `requests` | 计数 |
| `failed` / `gone` / `pending` | 按 `status` 分桶计数 |
| `models` | 出现过的 `resolved_model` 集合与各自计数 |
| `bytes_in` / `bytes_out` | 求和 |
| `usage` | 各 token 字段求和 |
| `pinned` | 该会话下是否有 pinned 记录 |
| `archived_batches` | 该会话涉及的归档批次 id 集合 |

聚合查询必须能走 `(session_id, started_at DESC)` 索引，且受 Q6 的 `limit` 约束。**只在 `sessions/*` 端点被调用时计算**，不做后台物化——物化表是第二个真值，且会引入一条新的写路径。

### 7.3 归档触发

三个条件，任一满足即触发一次归档运行：

| 条件 | 配置键 | 默认 |
|---|---|---|
| 热区压缩后字节数超限 | `history.hot_max_bytes` | 2 GiB |
| 记录年龄超限 | `history.hot_max_age_days` | 30 |
| 周期到点 | `history.archive_interval_s` | 3600 |

**容量按实际压缩后字节统计**（`blob_bytes` 之和加上其余列的估算），不是原始字节。压缩后字节才是它在磁盘上真正占的位置，也是 §2.3 选「按 attempt 合并压一次」的理由所在——proposal §1.8 的实测对照是整请求压一次 17,085 B 对逐帧独立压 19,764 B（1.16×），另一样本 7,373 B 对 10,985 B（1.49×）。用原始字节做上限口径会让同一个数字在两种压缩方式下代表完全不同的记录数。

**归档的搬迁单位是会话，不是行。** 取证的自然单位是一次会话：翻一个事故时要看的是那段对话的前后文，按行数切会把一次会话劈成两半。一次归档运行选出**已终结**（`status != "pending"`）、**未 pin**、**最后一条记录已早于 `hot_max_age_days`（或热区超限时按 `last_at` 从旧到新取够为止）**的整个会话，连同它的全部 L1 / L2 / L3 行一起搬走。

**永不搬迁**：`status = "pending"` 的记录（它们是崩溃现场，见 §3.5），以及任何 `pinned = 1` 的记录所在的会话。热区上限被这两类撑爆时，**告警而不是强行搬**：`forensic_hot_bytes` 越限且 `forensic_archive_runs_total` 在增长而字节数不降，就是这个状态。

### 7.4 归档的物理形态

**待裁决，见 §9.2。** 倾向独立文件——它让热库始终小、查询始终快，且归档批次可以整体移走或离线分析。

无论选哪种，下面几条是冻结的：

- **一次搬迁是一个事务。** 三张表的行必须在同一个 writer 事务里插入目标、删除源。**不依赖 SQLite 的 FK cascade**：`writer._open` 当前没有 `PRAGMA foreign_keys=ON`，cascade 不工作；新 writer 即使开了它，跨库的搬迁也不可能靠 cascade。
- **搬迁完成前不删源。** 顺序恒为「写目标 → 校验目标行数 → 删源 → 提交」。反过来做，一次崩溃就是永久数据丢失，而这套系统存在的理由就是崩溃时还有证据。
- **归档面是只读的。** 没有任何端点写归档批次，也没有任何端点删归档批次。清理归档由人在文件系统上做——I8 说的是产品面不删。
- **`include_archived = true` 的查询代价必须可见**：`meta.archives_scanned` 报出扫了几个批次。

### 7.5 `pin` 的语义

**`pin` = 免于归档**（不是「免于淘汰」，因为已经没有淘汰了）。钉住一条正在排查的记录，让它留在热区可查。

- 作用范围是**单条 L1 记录**，但归档的单位是会话，所以一条被 pin 的记录会让**它所在的整个会话**留在热区。这一点必须在 `pin` 的响应里说清：`{"data": {"id": …, "pinned": true, "holds_session": "<session_id>"}}`。
- 旧的 `HistoryWriter.set_pinned` 只操作旧 `entries` 表，用不上。新表的 `pinned` 有自己的写入途径，就是 §5.3 的端点。
- pin 没有过期时间。一堆忘了 unpin 的记录会让热区涨不停——这由 §7.3 的告警暴露，**不由自动过期解决**：一条自动到期的 pin 会恰好在人还需要它的时候消失。

---

## 8. 配置

### 8.1 与既有 `HistoryConfig` 的关系

现状（已核实，2026-08-21）：

- **新链路**的 `ProxyConfig.history` 是 `app/config/schema.py` 的 `HistoryConfig`，**只有 `enabled: bool = True` 一个键，且没有任何运行时消费者**。`--history/--no-history` 经 `cli.py` 写进 `cli_overrides["history"]["enabled"]`，配置对象里确实有这个值，但**没有任何代码读它**，所以它是死开关。
- **旧链路**的 `app/config/settings.py` 里另有一个同名 `HistoryConfig`，有 `enabled` / `success_limit=50` / `failure_limit=200` / `reaper_interval=600` / `db_path` / `websocket=True` 六个键，被 `app_factory` 真正消费。**两者不是一回事，别混淆。**
- `docs/.human-controlled/config.example.yaml` 里 `history: enabled: true`，只有这一个键。

**`success_limit` / `failure_limit` 的语义必须重定。** 用户裁的是归档不是淘汰，「成功保留 50 条、失败保留 200 条」这个口径在归档模型下没有位置：归档按会话成批、按字节与年龄触发，不按结果分桶计数。本 Spec 不复用这两个键名，用 §7.3 的三个新键代替。

### 8.2 键表

放在 `history.*` 之下还是另立一段，**待裁决（§9.2）**。下表按放在 `history.*` 之下写；若另立一段，键名不变、前缀改。

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `history.enabled` | bool | `true` | **总开关。见 §9.1——接不接上是待裁项。** 为 `false` 时不采集、不建库，查询端点全部回 503 |
| `history.db_path` | string | 空 | 空则用 `user_data_path() / "forensics.db"`。**独立文件名，不与旧链路的 `history.db` 共用**——测试噪音会把真实取证记录挤掉（§3.5 P2） |
| `history.levels` | string[] | `["l1","l2","l3"]` | 分层开关。让 L3 可以单独关掉而不影响 L1，因为 L3 是体积的主要来源 |
| `history.queue_size` | int | 2000 | writer 有界队列容量 |
| `history.write_timeout_s` | float | 5.0 | L1 背压上界（§4.1） |
| `history.spool_max_bytes` | int | 256 MiB | 在途 chunk 未压缩体积上界（§4.2） |
| `history.blob_level` | int | 3 | `compression.zstd` 压缩等级 |
| `history.hot_max_bytes` | int | 2 GiB | §7.3 |
| `history.hot_max_age_days` | int | 30 | §7.3 |
| `history.archive_interval_s` | int | 3600 | §7.3 |
| `history.archive_path` | string | 空 | 空则用 `user_data_path() / "forensics-archive"`。形态待 §9.2 裁决 |
| `history.query_workers` | int | 2 | §6 Q3 |
| `history.query_concurrency` | int | 4 | §6 Q7 |
| `history.query_timeout_s` | float | 30.0 | §6 Q7 |
| `history.limit_default` | int | 50 | §5.0 |
| `history.limit_max` | int | 500 | §5.0 |
| `history.websocket` | bool | `true` | `/history/ws` 是否挂载 |

**`archive_interval_s` 与 `hot_max_*` 之外不再引入 `reaper_interval`**：没有 reaper 了。

**路径类键走 `expand_user_path`**，与 `config.example.yaml` 里 `$XDG_DATA_HOME/...` 的写法一致。

### 8.3 与人写配置文件的关系

`config.example.yaml` 当前只写了 `history: enabled: true`。上表的其余键**都是新增的**，`ProxyConfig` 的 `model_config` 是 `extra="forbid"`，所以新增键必须同时进 `schema.py` 与人写的示例文件。**人写文档是最终权威**：示例文件的措辞与默认值以用户亲笔为准，本表是提交给用户采纳的候选，不是可以直接覆盖过去的结论。

---

## 9. 待裁决

**以下六项未裁决，未裁之前不得当作已定。** 前三项是 proposal §4.6 明确交回的；后三项是本 Spec 写作期间浮现的，一并交回而不是自行拍板。每项都给了我的建议与理由，建议不构成决定。

### 9.1 【需用户裁决】`ProxyConfig.history` 那个死开关

**现状**：`--history/--no-history` 与配置文件里的 `history.enabled` 都能改到配置对象，但没有任何运行时消费者，所以它是死开关。

三个选项：

| 选项 | 后果 |
|---|---|
| **接上** | `history.enabled` 真正控制记录子系统。因为 `config.example.yaml` 里默认 `true`，这意味着**升级后默认就开始记录**并占磁盘 |
| 保持现状但启动时明说无效 | 启动横幅里打一行「`history.enabled` 当前无消费者」。诚实，但留着一个永远要解释的开关 |
| 删除 | 需要同时改人写的 `config.example.yaml`，而那是用户亲笔文档 |

**我的建议：接上。** 鉴于已裁决全量记录，一个真的能关掉记录的开关比一个装饰性开关有用。但「默认开启新的磁盘写入」这件事本身应当由你点头，而不是从「默认值恰好是 `true`」里推导出来。

### 9.2 【需用户裁决】归档与会话聚合的配置键放哪

`history.*` 之下，还是另立一段（例如 `forensics.*`）？

- **放 `history.*`**：与人写示例文件里已有的 `history:` 一节连续，配置面只有一个词。代价是这一节从 1 个键长到 18 个键，而旧链路的同名 `HistoryConfig` 是另一套六个键，两份文档并置时容易读串。
- **另立一段**：新旧界限清楚，`history.enabled` 可以保持它原来的含义。代价是人写示例文件里多一节，且「history 与 forensics 有什么区别」需要一句解释。

**注意 `success_limit` / `failure_limit` 不能照搬**：你裁的是归档不是淘汰，「成功留 50 条、失败留 200 条」在归档模型下没有对应物，本 Spec §7.3 用「热区字节 / 年龄 / 周期」三个键代替。这是语义重定，不是改名。

**我的建议：另立一段 `forensics.*`，`history.enabled` 保留原名并按 §9.1 接上作为总开关。** 理由是这两套东西的读者不同：`history.enabled` 是运维开关，其余是取证系统的调参面。

### 9.3 【需用户裁决】旧链路 history 的去留

`app/routes/history.py`、`app/history/consumer.py`、`app/routes/protocol_history.py`（`/v1/messages` 走 `HistoryConsumer`，而 `openai.py` / `azure.py` / `gemini.py` / `responses_ws.py` 绕开它手写等价逻辑操作同一个 store）这一整套，本次动不动？

**我的建议：完全不动。** `protocol_history.py` 的重复实现是在一条不服务生产的链路上做整洁性重构，ROI 低；判定它无用并移除则触及「不得擅自删除已实现的功能」，不是我该判的。

### 9.4 【需用户裁决】归档的物理形态

同库的冷表、独立的按日期分片库文件、还是压缩包？

**这一项 proposal §3.4 说「列入 4.6 待你示下」，但 §4.6 实际只列了三项，它掉了。** 所以它至今没有出现在任何一份交给你的裁决清单上。

**我的建议：独立的按日期分片库文件。** 它让热库始终小、查询始终快，且归档批次可以整体移走或离线分析。代价是 `include_archived = true` 的查询要 attach 多个库，这由 §7.4 的 `meta.archives_scanned` 显式暴露。

### 9.5 【需用户裁决】replay 产生的上游交换记不记

**我的推定是记**（`origin = "replay"`，`replay_of = <原 id>`，§5.6）。理由：重放本身就是一次真实的上游交换，不记它等于在取证库里开一个不留痕的旁路，而「我刚才重放的那次上游回了什么」正是下一步要查的东西。

反对理由也成立：重放会污染统计口径（一次事故被重放二十次，`entries/list` 里就多出二十条），且它不是客户端发起的请求。若你倾向不记，那么 `record` 参数的默认值改为 `false`，端点仍保留把它打开的能力。

### 9.6 【需用户裁决】L1 与已经存在的 `requests-*.jsonl` 是什么关系

**这是 proposal 定稿之后才出现的事实**，背景见 §1.2，字段对账见 §2.1.1，对 proposal 论证的影响见 §10.1。一句话：完成记录已经在落盘了，L1 加的是可查询性与父行身份，所以「两份完成记录并存」这个形态需要你点头，否则就是本项目明确反对的「同一事实两处推导」。

三个选项：

| 选项 | 后果 |
|---|---|
| **并存，各司其职** | JSONL 是「进程能写的最简耐久记录」，取证库是「可查询的结构化面」。两条写路径，但**共享 `RequestLine` 这一个单写源**，所以不是两处推导，是一处推导两处落盘。代价是同一事实两个落点，读的人要知道该问哪个 |
| 取证库取代 JSONL | 一个落点。代价是失去「库出问题时的兜底」，而这套系统的价值恰在出问题的时候；且要删掉一个同伴会话刚为一次真实事故建起来的东西 |
| JSONL 降级为取证库的溢出兜底 | 只在取证写入被丢弃（§4.1 / §4.2）时才写 JSONL。一个落点加一条兜底，代价是实现更绕，且兜底路径平时不跑、真要用时才第一次被执行 |

**我的建议：并存，但 JSONL 不再扩字段。** 它已经在解决一个真实问题（`.dev/docs/upstream/h2-goaway/findings.md` 那次事故；`10e4811` 的提交信息里写的旧路径 `../upstream-h2-goaway/findings.md` 已随文档搬迁失效），它的耐久性来自「不依赖任何子系统就绪」这一点，把它接进取证库会把这个优点消掉。取证库单独记它自己那一份，两者靠 `request_id` 对得上。

**这条裁决影响实施顺序**：若裁「取代」，L1 就必须先把 JSONL 的全部能力接过来才能拆掉它，L1 的分量变重；若裁「并存」，L1 可以只做查询面需要的那部分，先落 L2 反而更划算（§1.3）。

---

## 10. 实施中发现的缺口

**本节不是契约。** 它记录 proposal 没有覆盖、或覆盖得与当前事实不符的地方，供下一次修订采纳。

### 10.1 proposal 之后落地的「完成记录已落盘」

`10e4811 feat: keep a durable record of every completed request`（2026-08-20 16:55 UTC）在 proposal r4 定稿（同日 13:39）之后合入，proposal 全文未提及。它做的事：

- `_log_completion` 除了写日志行，还调用 `write_request_record(line, status=status)`，把 `RequestLine` 整个 `asdict` 成一个 JSON 对象追加进 `<data>/requests/requests-YYYYMMDD.jsonl`，按 UTC 日切文件、按文件名保留最新 14 天。
- 它同时给 `RequestLine` 加了 `request_id`、`started_at`（墙钟 ISO 字符串，由 `utc_timestamp()` 产出）与 `upstream_conn`。
- **实测**（2026-08-21 13:37）：`~/.local/share/ghc-api-proxy/requests/` 下 `requests-20260820.jsonl` 3,305 行、3.0 MB，`requests-20260821.jsonl` 1,972 行、1.8 MB 且仍在增长。它在生产 import 闭包里——`pipeline_app` 直接 `from app.observability.request_log_file import utc_timestamp, write_request_record`。

对本 Spec 的四处影响：

1. **排障盘点里排第二的缺口已经被独立解决。** proposal §1.7 把「该次请求的服务端完成记录」列为被点名 3 次、现状「有雏形，只写 stdout」；§1.3 的采集点表也写「只写 stdout」。**这两句现在都不成立。** 由此展开的分片 1 论证（「昨天那条 400 的完整上下文——终端滚掉也还在」）已经是既成事实，不是待交付的能力。L1 的定位与三层优先级按本 Spec §1.2、§1.3 重写。
2. **`started_at` 的来源问题已经解决。** proposal §1.5 说「`_Trace.started` 是 `time.monotonic()`，不能当 SQLite 的墙钟 `started_at`」，这依然对；但现在 `_Trace.started_at` 已经存在且就是墙钟 ISO 串，L1 直接取它即可，不需要另造。
3. **分片 1「文件落点」的一半已经在了**，而且形态与 proposal 设想的不同——它不是 structlog 的一个 handler，是一条独立的直写路径。所以 proposal §4.4 里说的「TUI 抢占 root handler 导致文件 sink 在交互终端下为空」这个问题**对它不成立**，它根本不走 logging（`FooterTui.activate` 确实仍然做 `root.handlers = [handler]`，这一点没变，只是它管不到 `write_request_record`）。分片 1 的范围需要按这个事实重估。
4. **它是同步的，跑在事件循环线程上**：`write_request_record` 里有 `mkdir` + `open` + `json.dumps` + `write`，`_prune` 里还有一次 `glob`，全部在 `_log_completion` 这个同步函数里，而 `_log_completion` 由 `_serve`（协程）与 `_StreamAccounting.finish` 调用。**这与 §6 结尾那句「写路径与读路径都不许在事件循环上碰磁盘」直接冲突。** 它当前是否构成可观测的问题没有实测，不在本 Spec 的范围内，但取证库的写路径不得沿用这个形态。

### 10.2 `_Trace.failed` 已不存在

proposal 的并行会话警告框里说「`_Trace.failed` 字段就是在这期间出现的」，§3.1 的 L1 列表也列了 `failed`。当前 HEAD 上没有这个字段，取而代之的是 `_Trace.status_override: LogStatus | None`，配合 `status_for(status_code, override=...)` 产出 `ok` / `fail` / `gone` 三值。本 Spec §2.1 按当前事实写 `status`，并说明了为什么不能退回布尔。

### 10.3 分片 1 没有 Spec 可依

proposal §6.3 划的界线是「分片 1 起需要 Spec，把第三节扩写为行为 Spec 并冻结」。但**第三节完全不涉及结构化日志**——那是 §4.4 的内容，而分片 1 与分片 2 恰恰就是它。所以按 §6.3 的字面执行，扩写出来的 Spec（也就是本文）覆盖的是分片 3 及以后，分片 1、2 没有 Spec。

本文按任务范围没有覆盖结构化日志改造，**不是判它不需要 Spec，而是它需要一份自己的**：它的行为面是「结构化记录是权威，终端呈现与文件落盘都是它的下游」，与取证记录的数据模型没有共享的契约。加上 §10.1 揭示的形态变化，那份 Spec 的起点也和 proposal 设想的不一样了。

### 10.4 归档物理形态在文档内部掉了

proposal §3.4 写「这一项列入 4.6 待你示下」，§4.6 只列了三项，没有它。已作为 §9.4 交回。

### 10.5 `message.id` 关联的可得性已核实，但只对一半路径成立

proposal §5 说「这一条成本极低（L1 加一列），但需要确认该 id 在我方是否稳定可得，本次未核实」。已核实：

- `RequestContext.id` 是一个 `uuid4()` 字符串，`_dispatch` 把它抄进 `_Trace.message_id`，**流式路径**把同一个值作为 `message_id` 传给 `stream_delivery`，最终出现在发给客户端的 `message_start` 里。所以对流式回答，`ForensicRequest.message_id` 与客户端 transcript 里那条 assistant 消息的 `message.id` 是同一个值，可以直接 join。
- **非流式路径不成立。** `response_payload` 返回的是上游 body（或翻译后的 body），其中的 `id` 来自上游，不是 `context.id`。所以对非流式回答，L1 的 `message_id` 是我方内部 id，与客户端看到的对不上。

结论：这一列值得加（§2.1 已加），但**它的语义是「我方为这次请求生成的 id」**，只在流式路径上恰好等于客户端可见的 message id。端点文档与任何依赖它做 join 的调研脚本都必须知道这个限定，否则会在非流式流量上静默匹配不到并把它读成「没有这条记录」。

### 10.6 压缩依赖的归属，proposal 没提

proposal §1.8 全程用 zstd-3 做体积论证，但没说这个能力从哪来。实际情况：`zstandard` 当前只在 `[dependency-groups].dev` 里，注释明写它只服务 `tests/int/recorded/from_history.py`、「Nothing the proxy itself runs touches this」。

已解决且已写进 §2.3：`requires-python = ">=3.14"`，标准库自带 `compression.zstd`（已实测 `compress`/`decompress` 可用，默认等级 3），**不需要新增运行时依赖，也不需要动 `zstandard` 的分组**。

### 10.7 proposal 未给端点的副作用边界

`replay` 会真的打上游，`export-cassette` 会真的写文件。proposal 的端点表只给了路径，没说这两件事的边界。本 Spec §5.6 / §5.7 给了一个形态（replay 用当前凭据、不重放旧凭据；export 缺字段就 409 而不是补值；`path` 缺省时只返回不落盘），但**这几条是我拟的，不是裁决过的**，评审时应当重点看。

另外两条本 Spec 未定、也不打算自行定的：`replay` 是否需要并发限制（一个循环打二十次重放就是二十次真实上游调用与二十份配额消耗），以及 `export-cassette` 的 `path` 是否需要限定在某个目录下。前者建议复用 §6 Q7 的并发闸，后者按项目的安全立场（本机用户自己的数据目录）默认不限。

### 10.8 六个钩子点仍是「待办，非本次」

`config.example.yaml` 里的 `on_client_request_parsed` 等六个键只定义于 `config/schema.py` 的 `HooksConfig`，全仓零消费者；当前真实注册表用的是 `direct_driver/base.py` 的 `attempt.*` / `request.*` 内部事件。本 Spec 不实现钩子分发，但 §3.2 要求采集点按它们的语义留好位置。

### 10.9 proposal 对 `2604-rewrite` 的三处引证，前提已被裁决推翻

**用户 2026-08-20 裁定 `2604-rewrite` 整体过期**：它是早期 peer 会话写的 `copilot-api-js` 学习笔记，不是本项目的设计规范，也不是对已实现行为的描述。裁决与清点见 `.dev/docs/archived-2604-rewrite/README.md`，该文件**逐字点名**了 proposal 里的一处引证。受影响的有三处：

| proposal 的话 | 现在应当怎么读 |
|---|---|
| §3.4「`writer._open` 设的是 `busy_timeout=0`，而 `history-system.md` 的设计明写 `busy_timeout = 5000`。实现与设计文档对不上」 | 「对不上」这个判断不成立——**对不上的可能恰恰是笔记**。`busy_timeout=0` 是不是缺陷，要按新 writer 自己的形态判，本 Spec §4.3 就是这么判的 |
| §3.4「`SessionSummary` 在 `history-system.md` 已有设计」 | 那是笔记里的设想，不是既有设计。本 Spec §7.2 的字段是重新拟的，未沿用 |
| §3.4「`history-system.md` 曾把分层归档整体列入 BACKLOG，此裁决把它提回主线」 | 笔记的 BACKLOG 不构成本项目的取舍记录。用户的归档裁决本身成立，与笔记里写过什么无关 |

同理，§8.1 里「旧链路那六个键」的事实来源是 `src/app/config/settings.py` 里真实存在的代码，**不是**笔记，那一条不受影响。

### 10.10 TUI 历史回看面板

proposal §5 记为「看到了但本次不做」。本 Spec 的端点面（尤其 `sessions/*`）正是那个面板将来的数据源，但界面工作的验收方式不同（人眼看着对不对，测试替代不了），仍建议单独立项。


