# 历史与审计系统

## 概述

历史系统（`history/`）持久化记录所有 API 请求的完整对话历史，提供 REST API 查询、WebSocket 实时推送、崩溃回收与容量管理。本文档是**目标设计**（design spec），标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。

### 性能重设计声明

上游参考项目把 History 做成了一套**极重的子系统**：同步 `bun:sqlite` 落在请求路径、三层降温归档（HOT → tier1 → tier2，tier2 用 zstd **L19 + 16MB 窗口**列式封存）、内容寻址去重全文搜索索引、每请求多 stage 增量写盘、client/upstream 双腿 + 逐 attempt 重对象图。这是本项目识别出的最大性能负担之一（见 [DESIGN.md 性能设计原则](DESIGN.md#性能设计原则第一优先级) P1/P2/P3/P4/P7）。

本项目**不原样复刻**，采纳其解决的真问题（双源模型、session 识别、分桶容量管理、崩溃回收、持久化韧性），但用以下精简高性能方案重新实现：

| 维度 | 上游做法 | 本项目设计 |
|------|---------|-----------|
| 落盘位置 | 同步 SQLite 在请求路径上 | 异步单层 SQLite，**所有 I/O off-event-loop**（专用 writer 协程 + 有界队列） `[重构，见 P1]` |
| 归档 | 三层降温（HOT/tier1/tier2）+ zstd L19 | 默认单层 + 简单行数上限 reaper；分层归档 `[缓存/延后，见 BACKLOG#1]` |
| 压缩 | tier2 用 zstd L19 + 16MB 窗口 | zstd **level 3**，线程池执行 `[简化，见 P2]` |
| 搜索 | 内容寻址去重 + 5 源 facet 全文索引 | SQL 列过滤 + `preview_text` 的 `LIKE`；全文搜索 `[缓存/延后，见 BACKLOG#2]` |
| 数据模型 | client/upstream 双腿 + 逐 attempt + `_index.derived` 重算 | 轻量 `dataclass`，终态一次性写入 `[简化，见 P7、BACKLOG#4]` |
| 持久化时机 | 每请求多 stage 增量写盘（eager head → 每转换 → 每 attempt → finalize） | 终态**一次性** fire-and-forget 写入；进行中状态只留内存 in-flight `[简化]` |
| 产品面删除 | 已移除（`archive-now` 替代） | **同样不提供** DELETE 端点，直接沿用该决策 `[采纳]` |

本文档其余部分按此立场展开：先讲存储架构（双源模型 + off-loop 写入），再讲数据模型、生命周期、session 识别、容量管理、崩溃回收、持久化韧性，最后是 REST/WebSocket 接口与配置。

## 存储架构

### 双源模型

历史数据始终有两个来源，REST 查询与 WebSocket 推送都基于此契约：

```
┌─────────────────────┐        ┌──────────────────────┐
│   in-flight 内存映射   │        │      SQLite（HOT）      │
│  dict[str, LiveEntry] │        │   entries 表（终态行）    │
│  进行中请求的权威实时视图 │        │      持久化、跨重启可见     │
└─────────┬────────────┘        └───────────┬──────────┘
          │  entry_added / entry_updated     │  查询走列过滤 + LIKE
          │  经 WebSocket 直接推送             │
          ▼                                  ▼
                    REST 查询合并（in-flight 在前，SQLite 在后，按 started_at DESC）
```

- **in-flight 内存映射**（`history/in_flight.py`）：请求从 `pending` 到终态之前，实时状态只存在于内存 `dict`，是 WebSocket 推送的**权威源**。不涉及磁盘 I/O，天然零延迟。
- **SQLite**（`history/sqlite/`）：只在请求**到达终态**（`completed`/`failed`/`aborted`/`interrupted`）后才落一行，异步、fire-and-forget、不阻塞响应路径。
- **REST 查询**：`GET /history/api/entries` 透明合并两源——in-flight 条目排在前面，SQLite 条目排在后面，整体按 `started_at DESC` 排序、按 id 去重。这一点直接采纳上游的双源合并契约 `[采纳]`，但去掉了上游"增量 stage 写盘"的中间态——本项目的 SQLite 侧只有"尚未出现"或"终态已写"两种状态，没有半写的中间行。

### off-event-loop 写入（P1 核心对策）

历史写入是本项目**性能红线**：绝不允许任何 SQLite 调用直接出现在请求协程的 `await` 链上。设计如下：

```python
import asyncio
import sqlite3
from dataclasses import dataclass

@dataclass
class WriteJob:
    kind: str              # "insert_entry" | "reap" | "pin"
    payload: object
    discardable: bool = False   # 背压时是否可丢弃

class HistoryWriter:
    """专用 writer 协程：唯一持有 SQLite 连接的写路径。"""

    def __init__(self, db_path: str, queue_size: int = 1000):
        self._queue: asyncio.Queue[WriteJob] = asyncio.Queue(maxsize=queue_size)
        self._conn: sqlite3.Connection | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._conn = await asyncio.to_thread(self._open_connection)
        self._task = asyncio.create_task(self._run(), name="history-writer")

    async def submit(self, job: WriteJob) -> None:
        """请求路径调用点：非阻塞提交，永不 await 磁盘 I/O。"""
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            if job.discardable:
                return  # 背压：丢弃可丢弃项（如 reap 心跳），绝不阻塞请求
            # 不可丢弃项（如终态 entry）：短超时等待，仍满则记错误计数并丢弃
            try:
                await asyncio.wait_for(self._queue.put(job), timeout=0.05)
            except asyncio.TimeoutError:
                self._record_drop(job)

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                # 实际 SQLite 调用下沉到线程池，writer 协程本身不阻塞事件循环
                await asyncio.to_thread(self._execute, job)
            except Exception as exc:
                self._classify_and_log(job, exc)  # 见「持久化韧性」
            finally:
                self._queue.task_done()
```

要点：

- **请求路径只做 `submit()`**：把 job 塞进有界 `asyncio.Queue` 后立即返回，是货真价实的 fire-and-forget，请求耗时不含任何历史落盘开销。
- **有界队列 + 背压丢弃**：队列满时，可丢弃项（如 reaper 心跳、pin 状态同步）直接丢弃；不可丢弃项（终态 entry）短超时重试后仍失败则计入错误统计并放弃（宁可丢一条历史，不可拖垮请求路径），呼应 [DESIGN.md](DESIGN.md#性能设计原则第一优先级) 的"背压与有界队列"通用取向。
- **单一 writer + 线程池双重下沉**：writer 协程本身跑在事件循环里，但实际 `sqlite3` 调用经 `asyncio.to_thread` 下沉到线程池；这样即使某次写入较慢（大 payload 压缩/磁盘抖动），也只阻塞线程池 worker，不阻塞事件循环。SQLite 连接只被这一个 writer 持有，天然免锁（`sqlite3` 连接非线程安全，单一持有者规避了跨线程共享连接的问题）。
- **也可用纯 executor 方案替代队列**：更简单的等价实现是每次写入直接 `asyncio.get_running_loop().run_in_executor(pool, fn)` 提交给单线程 `ThreadPoolExecutor(max_workers=1)`，省去手写队列消费循环，代价是背压丢弃需要在 executor 外层自行判断队列深度。两种实现二选一，取决于是否需要精细控制丢弃策略；本设计以显式队列为准，理由是背压语义更透明。

### 压缩

`request_payload`/`response` 等大字段以 zstd **level 3** 压缩后存入 BLOB 列，压缩本身也在线程池执行（不占事件循环 CPU 时间片）。level 3 是吞吐与压缩比的折中点——上游 tier2 用 level 19 是为了长期冷归档的极致压缩比，但本项目默认单层存储、数据本来就会被 reaper 清理，没有为"1% 的存储收益换 10 倍的 CPU 开销"买单的必要（呼应 P2）。

## 数据模型

### HistoryEntry

```python
from dataclasses import dataclass, field
from typing import Literal

EntryStatus = Literal["pending", "executing", "streaming", "completed", "failed", "aborted", "interrupted"]

@dataclass
class ModelRef:
    requested: str              # 客户端原始模型名（pre-alias）
    resolved: str                # 解析后的规范模型名

@dataclass
class HistoryEntry:
    id: str                                  # 请求 ID（uuid4）
    session_id: str | None                   # 见「Session 识别」
    agent_id: str | None                     # x-claude-code-agent-id，缺省 "main"
    started_at: float                        # 必填，Unix 秒，用于排序/过滤/reaper
    ended_at: float | None                   # 终态才有

    endpoint: str                            # "openai-chat-completions" | "openai-responses" | "anthropic-messages" | ...
    status: EntryStatus

    model: ModelRef
    request_payload: dict                    # 完整请求体（压缩存储）
    response: dict | None                    # 累积后的完整响应（压缩存储）
    usage: dict | None                       # {input_tokens, output_tokens, reasoning_tokens, ...}

    duration_ms: float | None
    request_bytes: int
    response_bytes: int
    transport: Literal["http", "websocket"]
    pid: int                                 # 写入进程 pid，供崩溃回收判定归属

    error_message: str | None = None         # 非成功终态的失败原因

    @property
    def is_active(self) -> bool:
        return self.status in ("pending", "executing", "streaming")
```

**Python 优化**：不采纳上游的 client/upstream 双腿 + 逐 attempt 保存整条 wire 报文的模型（见 [BACKLOG#4](BACKLOG.md#4-clientupstream-双腿数据模型--多-stage-持久化-缓存延后)）。`request_payload`/`response` 只存**客户端可见的**入站/出站 payload，重试过程中每个 attempt 的中间上游请求/响应不逐条持久化，只在内存 `RequestContext.attempts`（见 [request-pipeline.md](request-pipeline.md)）中保留、随终态摘要进 entry（`attempt_count`、`retry_strategies_applied` 等标量），不做上游那种可重放的逐 attempt 审计对象图。若未来确需完整逐 attempt 审计，走 BACKLOG 中"可选详细模式"的路径，而非默认行为。

### EntrySummary

列表 / WebSocket 推送用的轻量投影，不含完整 `request_payload`/`response`：

```python
@dataclass
class EntrySummary:
    id: str
    session_id: str | None
    agent_id: str | None
    started_at: float
    ended_at: float | None
    endpoint: str
    status: EntryStatus
    model: ModelRef
    preview_text: str                # request 首段文本摘录，供列表/搜索快筛
    response_preview_text: str | None
    attempt_count: int
    usage: dict | None
    duration_ms: float | None
    pinned: bool
```

`preview_text`/`response_preview_text` 在终态写入时**惰性生成一次**（截断到固定长度，如 200 字符），不做上游那种多 facet 归一化 + 哈希的重投影（呼应 P4/P7）。

### SessionSummary

不作为独立表存储，而是对 `entries` 表按 `session_id` 做一次 `GROUP BY` 聚合得到，查询时现算（数据量级下 SQL 聚合足够快，省掉维护一张冗余聚合表及其一致性问题）：

```python
@dataclass
class SessionSummary:
    session_id: str
    request_count: int
    agent_count: int             # DISTINCT agent_id 数
    total_input_tokens: int
    total_output_tokens: int
    first_started_at: float
    last_started_at: float
    completed_count: int
    failed_count: int
    aborted_count: int
    models: list[str]            # DISTINCT model.resolved
    preview_text: str            # 该 session 最新一条 entry 的 preview

# SQL 示意
"""
SELECT session_id,
       COUNT(*) AS request_count,
       COUNT(DISTINCT agent_id) AS agent_count,
       SUM(input_tokens) AS total_input_tokens,
       SUM(output_tokens) AS total_output_tokens,
       MIN(started_at) AS first_started_at,
       MAX(started_at) AS last_started_at,
       SUM(status = 'completed') AS completed_count,
       SUM(status = 'failed') AS failed_count,
       SUM(status = 'aborted') AS aborted_count
FROM entries
WHERE session_id IS NOT NULL
GROUP BY session_id
ORDER BY last_started_at DESC
LIMIT :limit
"""
```

in-flight 侧的活跃条目也需要参与聚合（否则"进行中"的 session 看起来是空的）：`GET /sessions` 现算时把 in-flight 映射按 `session_id` 分组后与 SQL 聚合结果合并（数量级小，Python 侧合并即可，无需回写 SQLite）。

## 生命周期状态机

```
pending ──→ executing ──→ streaming ──→ completed
   │            │             │
   │            │             └──────────→ aborted（客户端中途断连）
   │            └────────────────────────→ failed（上游/内部错误）
   │
   └── 若进程崩溃、行残留为非终态 ──(崩溃回收)──→ interrupted
```

- `pending`：请求已被路由接受，尚未开始上游调用。
- `executing`：正在执行管道（清洗/审批/限流/发起上游请求），尚无响应流。
- `streaming`：已收到上游响应并开始向客户端转发（SSE 或分块）。**streaming 是 active 态，reaper 免疫**（不计入分桶配额、不被淘汰）。
- 终态四种：
  - `completed` —— 上游返回完整成功响应，转发给客户端亦成功。
  - `failed` —— 上游返回错误，或管道内部异常（清洗/审批/限流/序列化失败等）。
  - `aborted` —— 客户端在请求完成前主动断开连接（区别于 `failed`：责任在客户端而非上游/服务端）。
  - `interrupted` —— 非正常终态：进程崩溃/被杀导致某个 active 行永远等不到自然终态，由崩溃回收机制事后重分类得到（见下文）。

`failed`/`aborted`/`interrupted` 三者统一进入 reaper 的"失败桶"（`failure_limit`），`completed` 进入"成功桶"（`success_limit`）——与上游的分桶口径一致，见「分桶容量管理」。

此状态机与 [request-pipeline.md](request-pipeline.md) 中 `RequestContext` 的管道阶段（`pending → sanitizing → awaiting_approval → executing → streaming → completed/failed`）不是同一个状态机：`RequestContext` 描述的是管道内部的处理阶段，`HistoryEntry.status` 是面向历史/审计消费者的**归并视图**（`sanitizing`/`awaiting_approval` 归并进 `executing`，管道的 `failed` 按客户端是否已断连区分为 `failed` 或 `aborted`）。History 消费者（REST/WebSocket/reaper）只关心归并后的粗粒度状态，无需感知管道内部阶段切换的每一跳，减少了跨模块的状态耦合面。

## Session 识别

Anthropic Messages / OpenAI Chat Completions 等协议本身无状态，客户端不传递会话标识符；本项目从 HTTP header 识别客户端侧关联的会话，按以下优先级取首个存在的 header 值：

| 优先级 | Header | 说明 |
|-------|--------|------|
| 1 | `x-claude-code-session-id` | Claude Code 客户端签发的**稳定 per-conversation UUID**，同一对话全程不变，识别度最高，优先采用 |
| 2 | `x-session-id` | 通用会话标识 |
| 3 | `x-conversation-id` | 通用对话标识 |
| 4 | `x-chat-session-id` | 通用聊天会话标识 |
| 5 | `x-thread-id` | 通用线程标识 |
| 6 | `x-interaction-id` | 通用交互标识 |

均缺失时 `session_id = None`（该 entry 不参与任何 session 聚合，但仍正常落盘/查询）。

**Agent 识别**：读取 `x-claude-code-agent-id`，缺省时归为 `"main"`（Claude Code 的子 agent/主 agent 场景下用于区分同一 session 内不同 agent 发出的请求，供 `SessionSummary.agent_count` 统计）。

**Responses API 的 session 解析**：OpenAI Responses API 用 `previous_response_id` 串联多轮对话而非显式 session header，历史系统维护一张轻量的 `response_id → session_id` 映射表（内存 `dict`，随对应 entry 的 reap 一并过期即可，不需要独立持久化）：收到带 `previous_response_id` 的请求时查表得到 `session_id`，写入新 entry 时把 `response.id → session_id` 登记进映射，供后续轮次查询。

## 分桶容量管理（Reaper）

与上游一致地**按状态分桶**独立维持上限——成功历史与失败诊断历史互不挤占（不希望大量失败重试把有价值的成功样本挤掉，反之亦然），但淘汰机制本身大幅简化（对照 [BACKLOG#1](BACKLOG.md#1-分层降温归档hot--tier1--tier2-缓存延后)：上游是"三层迁移"，本项目是"单层删最旧"）。

- **成功桶**：`status = 'completed'` 的行，上限 `success_limit`（默认 50）。
- **失败桶**：`status IN ('failed', 'aborted', 'interrupted')` 的行，上限 `failure_limit`（默认 200）。
- 任一 limit 为 `0` 表示该桶不设上限（不淘汰）。
- **active 态（`pending`/`executing`/`streaming`）与 pinned 行落在两桶之外**：既不计入配额、也不会被淘汰，由崩溃回收/pin 机制分别处理。
- 每桶按 `started_at ASC` 删除最旧的超额行，保留最新的 `limit` 条。

```python
async def reap_bucket(conn, *, status_clause: str, limit: int) -> int:
    if limit <= 0:
        return 0
    cur = conn.execute(
        f"SELECT COUNT(*) FROM entries WHERE {status_clause} AND pinned = 0"
    )
    count = cur.fetchone()[0]
    if count <= limit:
        return 0
    to_delete = count - limit
    conn.execute(
        f"""
        DELETE FROM entries WHERE id IN (
            SELECT id FROM entries
            WHERE {status_clause} AND pinned = 0
            ORDER BY started_at ASC
            LIMIT ?
        )
        """,
        (to_delete,),
    )
    return to_delete

async def reaper_tick(writer: HistoryWriter) -> None:
    """由后台定时任务调用，job 经队列提交给 writer 协程执行，off-loop。"""
    job = WriteJob(kind="reap", payload=None, discardable=True)
    await writer.submit(job)
    # writer 内部执行：
    #   reap_bucket(status_clause="status = 'completed'", limit=success_limit)
    #   reap_bucket(status_clause="status IN ('failed','aborted','interrupted')", limit=failure_limit)
```

`reaper_interval` 控制定时器周期（默认 600 秒，即 10 分钟），`0` 表示禁用周期性 reap（仍可手动触发）。reaper job 本身标记为 `discardable=True`——若上一次 reap 尚未处理完、队列又满，跳过本次心跳不会造成数据损失，下一周期继续。

### Pin/Unpin（豁免淘汰）

采纳上游的 pin 机制：`entries.pinned`（`INTEGER NOT NULL DEFAULT 0`）标记豁免 reaper 的行。调试/复现问题时常需要保留某条关键样本，pin 之后该行既不计入所在桶的配额、也不会被淘汰。写路径专列独占——只有 `POST /entries/:id/pin|unpin` 触发的显式 `UPDATE` 会改这一列，终态 upsert 不会覆盖它。in-flight 侧若该条目仍在内存（尚未终态化时也支持 pin），pin 状态需要同步一份到内存副本，避免 REST/WS 读到旧值。

## 崩溃回收

进程被 SIGKILL/OOM 杀死时，某些 active 行会永远停在非终态。两条路径把它们回收为 `interrupted`（进入失败桶，可被淘汰）：

- **启动期回收**：`HistoryStore` 初始化 / `openDatabase` 阶段，把所有 `pid` **不等于当前进程 pid** 的 `pending`/`executing`/`streaming` 行批量标为 `interrupted`——这些必然是上一个已死进程遗留的孤儿（本进程刚启动，不可能有自己产生的 active 行）。

```python
async def reclaim_orphaned_active_rows(conn, current_pid: int) -> int:
    cur = conn.execute(
        """
        UPDATE entries
        SET status = 'interrupted', ended_at = :now
        WHERE status IN ('pending', 'executing', 'streaming')
          AND pid != :pid
        """,
        {"now": time.time(), "pid": current_pid},
    )
    return cur.rowcount
```

- **运行期回收**：reaper 周期内，把**本进程**中 `started_at` 超过 `timeouts.stale_request_max_age`（见 [shutdown.md](shutdown.md#stale-request-reaper)）的 active 行也标为 `interrupted`——防止同进程内因某种异常路径未走到 `HistoryConsumer` 的正常终态回调，导致 active 行无限堆积。这与 [shutdown.md](shutdown.md#stale-request-reaper) 描述的 `RequestContextManager` stale reaper 是同一超时配置在不同层面的呼应：`RequestContextManager` 层面强制 `fail()` 该请求上下文（内存态清理），历史系统层面则把对应的 SQLite 行标记为 `interrupted`（持久化状态归位）。两者应由同一个 `on_request_failed` 消费者回调驱动，保证内存状态与持久化状态不脱节。

## 持久化韧性

历史写入**永不静默吞错**（呼应用户核心原则 never-swallow-errors）。每次写入经统一 guard 分类处理：

```python
class HistoryWriteError(Exception):
    def __init__(self, kind: Literal["transient", "permanent"], cause: Exception):
        self.kind = kind
        self.cause = cause

def classify_write_error(exc: Exception) -> Literal["transient", "permanent"]:
    """transient：SQLITE_BUSY/LOCKED/IOERR，稍后重试可能成功；
    permanent：约束冲突/序列化异常/数据本身有问题，重试无意义。"""
    if isinstance(exc, sqlite3.OperationalError) and (
        "busy" in str(exc).lower() or "locked" in str(exc).lower()
    ):
        return "transient"
    return "permanent"

async def _execute_with_guard(self, job: WriteJob) -> None:
    try:
        await asyncio.to_thread(self._execute, job)
    except Exception as exc:
        kind = classify_write_error(exc)
        self._error_counts[(job.kind, kind)] += 1
        logger.error(f"[History] write failed kind={job.kind} class={kind}: {exc}")
        if kind == "transient" and job.retry_count < MAX_RETRIES:
            job.retry_count += 1
            await self._queue.put(job)   # 重新入队重试
        # permanent 或重试耗尽：记录错误、放弃该次写入，绝不无声吞掉
```

关键设计取舍：

- **只终态写、不做增量 stage 写**（呼应 P7/BACKLOG#4），所以不存在上游那种"eager head 行 + 之后再增量补 stage"的复杂持久化状态机，也就不需要"head-first 原子写""FK 安全"之类的应对措施——本项目的写入粒度天然是一次性的整行 `INSERT`。
- **transient 错误重试，permanent 错误放弃并计数**：错误统计（`(job_kind, error_kind) → count`）可经 `/api/status` 或专门端点暴露，供运维发现"历史写入持续失败"这类问题，而不是像上游修复前那样静默降级为一句 `warn` 无人知晓。
- **in-flight 副本是失败前的最后防线**：即使某条 entry 的终态写入最终判定失败（permanent 或重试耗尽），只要该条目仍在内存 in-flight 映射中未被移除，REST/WebSocket 仍能读到它——只是不会跨重启持久化。这与上游"仅确认写成功才 `removeInFlight`"的原则一致 `[采纳]`：只有写入成功后才从 in-flight 移除，避免"写失败 + 立即移除内存副本"导致的彻底数据蒸发。

## REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/history/api/entries` | GET | 分页查询（`limit`/`offset` 或游标）+ 过滤（`model`/`endpoint`/`status`/`since`/`until`/`search`/`session_id`）。`search` 是对 `preview_text` 的 `LIKE` 快筛，非全文搜索 |
| `/history/api/entries/:id` | GET | 单条完整详情（含 `request_payload`/`response`），in-flight 优先、否则查 SQLite |
| `/history/api/entries/:id/export` | GET | 单条导出（JSON），流式返回避免整条大 payload 一次性加载 |
| `/history/api/entries/:id/pin` | POST | 钉住该条目，豁免 reaper |
| `/history/api/entries/:id/unpin` | POST | 取消钉住 |
| `/history/api/sessions` | GET | `SessionSummary` 列表（in-flight + SQLite 聚合合并），支持 `limit` |
| `/history/api/stats` | GET | 全局统计（总请求数、成功/失败数、按 model/endpoint 分布、时延分位数等） |
| `/history/api/export` | GET | 导出全部历史（`format=json\|csv`） |

**未提供**任何 DELETE 端点——沿用上游"产品面移除删除能力"的决策 `[采纳]`：清库/删条目仅作为内部 test-only 原语存在（供测试隔离重置用），不对外暴露 HTTP 接口，避免误触发导致不可逆数据丢失（上游历史上确有此教训）。

## WebSocket 实时推送

`GET /history/ws`，支持主题订阅（`history`/`requests`/`status`），连接后按需订阅感兴趣的频道：

| 主题 | 事件 | 触发时机 |
|------|------|---------|
| `history` | `entry_added` | 新请求进入 `pending`，写入 in-flight 映射 |
| `history` | `entry_updated` | in-flight 条目状态变化（`executing`→`streaming`→终态），或 pin/unpin |
| `history` | `stats_updated` | 聚合统计发生变化（终态写入后触发） |
| `history` | `session_deleted` | 内部测试原语触发清理时广播（生产路径基本不触发，因无 DELETE 端点） |

推送数据一律是 `EntrySummary`（轻量投影），不推送完整 `request_payload`/`response`——避免大 payload 通过 WebSocket 广播给所有订阅连接造成带宽/序列化开销。客户端如需完整详情，收到 `entry_added`/`entry_updated` 后按 id 主动 `GET /history/api/entries/:id`。

```python
@router.websocket("/history/ws")
async def history_ws(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
):
    await ws_manager.connect(websocket, "history")
    try:
        while True:
            # 接收客户端的订阅/取消订阅消息（topic 过滤）
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, "history")
```

## 数据库位置与 PRAGMA

默认路径：`$XDG_DATA_HOME/ghc-api-proxy/history.db`；未设置 `XDG_DATA_HOME` 时回退到 `~/.local/share/ghc-api-proxy/history.db`。可经配置 `history.db_path` 覆盖为任意绝对路径。

打开连接时设置以下 PRAGMA（由 `HistoryWriter._open_connection` 在线程池内执行一次）：

```python
def _open_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")          # 写不阻塞读、提升并发
    conn.execute("PRAGMA synchronous = NORMAL")         # WAL 模式下足够安全，兼顾性能
    conn.execute("PRAGMA busy_timeout = 5000")          # 5 秒忙等，减少 SQLITE_BUSY 报错
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

`WAL` + `synchronous=NORMAL` 是官方推荐的性能/持久性平衡点（进程崩溃仍保证已 commit 的事务不丢，只在整机断电等极端场景有极小概率丢最近事务，可接受）。

## 配置项

完整权威配置见 [config-system.md](config-system.md)，此处列出 `history.*` 全部键：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `history.enabled` | `true` | 历史子系统总开关，**启动期专属**（运行期不支持热切换，需重启生效） |
| `history.success_limit` | `50` | 成功（`completed`）桶行数上限，`0`=不限 |
| `history.failure_limit` | `200` | 失败诊断桶（`failed`/`aborted`/`interrupted`）行数上限，`0`=不限 |
| `history.reaper_interval` | `600` | 周期性 reap 秒数，`0`=禁用周期任务（仍可手动触发） |
| `history.db_path` | `""` | 覆盖默认数据库路径，空则用 XDG 数据目录默认值 |
| `history.websocket` | `true` | 是否启用 `/history/ws` 推送 |

> **与旧文档的更正**：[DESIGN.md「关键更正」](DESIGN.md#关键更正相对本项目旧文档)已指出，旧版曾用 `history.limit` + `history.min_entries`（内存压力驱逐模型）描述容量管理，现更正为 `success_limit`/`failure_limit` 分桶模型——因为**默认单层持久化方案不存在"内存压力"驱逐这一层**（旧文档描述的是纯内存 `OrderedDict` 存储方案，与本文档当前的"异步 SQLite + in-flight 内存映射"双源方案是两代不同设计）。[config-system.md](config-system.md) 已同步为分桶键名（`success_limit`/`failure_limit`），`limit` 仅作向后兼容的 compat 别名保留。

分层归档相关配置（`history.archive.enabled`/`hot_days`/`tier1_size_cap`/`tier2_warn_count`/`tier2_warn_bytes`/`dir` 等）**不在默认配置骨架中**——该能力整体 `[缓存/延后]`，详见 [BACKLOG.md 第 1 条](BACKLOG.md#1-分层降温归档hot--tier1--tier2-缓存延后)。若未来实现该可选能力，会作为独立的 `archive.*` 配置块引入，不影响本文档描述的默认单层行为。全文搜索索引（`search_index` 子系统）同样不在默认配置中，见 [BACKLOG.md 第 2 条](BACKLOG.md#2-内容寻址去重全文搜索-缓存延后)。

## 与管道集成

历史系统作为 [request-pipeline.md](request-pipeline.md) 中 `RequestContextManager` 的一个消费者（`HistoryConsumer`）接入：

```python
class HistoryConsumer:
    """RequestContext 生命周期消费者，见 shutdown.md『消费者注册』。"""

    def __init__(self, history_store: HistoryStore):
        self._store = history_store

    async def on_request_started(self, ctx: RequestContext) -> None:
        # 请求进入时立刻写 in-flight（内存，零 I/O），WS 广播 entry_added
        await self._store.add_in_flight(ctx)

    async def on_state_changed(self, ctx: RequestContext) -> None:
        # executing/streaming 等状态切换：只更新内存 in-flight + WS 广播，不落盘
        await self._store.update_in_flight(ctx)

    async def on_request_completed(self, ctx: RequestContext) -> None:
        entry = build_history_entry(ctx, status="completed")
        await self._store.finalize(entry)   # fire-and-forget 提交给 HistoryWriter

    async def on_request_failed(self, ctx: RequestContext) -> None:
        status = "aborted" if ctx.client_disconnected else "failed"
        entry = build_history_entry(ctx, status=status)
        await self._store.finalize(entry)
```

`finalize()` 内部：先把 entry 从 in-flight 转移出（标记为"待落盘"，此刻 WS 已广播过对应的终态 `entry_updated`），再把整行 `WriteJob` 提交给 `HistoryWriter` 队列；只有 writer 确认写入成功后才真正从 in-flight 映射移除该条目（见「持久化韧性」）。这条链路上，`add_in_flight`/`update_in_flight` 全程零磁盘 I/O，唯一触碰磁盘的 `finalize` 也是非阻塞提交——对请求本身而言，History 子系统在时延上是"不可见"的。

## 相关文档

- [设计文档总纲](DESIGN.md) —— 性能设计原则 P1–P8、借鉴状态标注约定
- [BACKLOG.md](BACKLOG.md) —— 分层降温归档（第 1 条）、内容寻址全文搜索（第 2 条）、client/upstream 双腿模型（第 4 条）的性能取舍与可选实现路径
- [请求执行管道](request-pipeline.md) —— `RequestContext` 状态机、消费者注册机制
- [优雅关闭与请求生命周期](shutdown.md) —— Stale Request Reaper、`RequestContextManager`
- [手动审批系统](approval-system.md) —— 审批事件的 WebSocket 推送（共享同一 `WebSocketManager`）
- [配置系统](config-system.md) —— 完整配置清单（权威来源）
