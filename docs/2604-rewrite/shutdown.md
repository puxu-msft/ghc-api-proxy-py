# 优雅关闭与请求生命周期

## 优雅关闭

`shutdown.py` 实现 **4 阶段**优雅关闭（Setup → Graceful Wait → Abort → Force Close），确保进行中的请求有机会完成，同时保证进程不会无限期挂起。`[上游稳定][采纳]`

> 与本项目早期文档的更正：早期版本曾写成 3 阶段（Drain / Graceful Wait / Abort），实际上游把"停止 accept + 停后台服务 + 排空队列"这组立即动作单独称为 Phase 1 Setup，"强制关闭所有连接"是独立的 Phase 4。本篇按 4 阶段定稿。

### Phase 1: Setup（立即）

进程收到 SIGINT/SIGTERM 后立即同步执行的一组动作，不等待任何请求：

- 停止接受新请求（health readiness 探针立即开始返回 503）
- 标记服务器为 draining 状态（`app.state.draining = True`）
- 停止后台服务：token 刷新任务、stale reaper、模型列表定期刷新
- 排空限流队列（拒绝尚未获得配额的排队请求，或让它们尽快失败而不是无限期等待）
- 停止监听新连接（已建立的连接保留，不受影响）

**History DB 保持打开**，不在 Phase 1 关闭——异步 finalize 落盘要贯穿 Phase 2/3 的 drain 过程（settle 期间产生的历史记录仍需正常写入），DB 真正关闭推迟到最终的 finalize 阶段。若在 Phase 1 就同步关闭 DB，会丢失 drain 期间刚完成的请求的历史记录，这是一个真实的正确性陷阱，需要在实现时特别注意。

### Phase 2: Graceful Wait

- 等待活跃请求**自然完成**（不主动干预）
- 超时：`shutdown.graceful_wait` 秒（默认 `60`）
- 期间可周期性检查活跃请求数，用于日志与 `/api/status` 展示进度

### Phase 3: Abort

- 若 Phase 2 超时后仍有活跃请求，向所有仍在进行的请求发送 abort signal
- 等待 handler 处理 abort 信号并完成清理
- 超时：`shutdown.abort_wait` 秒（默认 `120`）

### Phase 4: Force Close

- 强制关闭所有连接（含仍未响应 abort 的请求处理器）
- 关闭所有上游连接，**包括上游 WebSocket 连接**——关闭顺序很重要：应先关闭面向客户端的连接、再关闭上游连接，避免上游连接先断导致客户端侧读到不完整数据引发额外的 `EPIPE` 类错误噪音
- finalize：关闭 History DB、关闭观察者 WebSocket 客户端、fire-and-forget 关闭遥测（不阻塞进程退出）

```python
async def graceful_shutdown(app: FastAPI, reason: str = "shutdown") -> None:
    manager: RequestContextManager = app.state.context_manager
    settings = app.state.settings.shutdown

    # Phase 1: Setup（立即，同步执行）
    app.state.draining = True
    logger.info(f"[Shutdown] Phase 1: Setup — draining, reason={reason}")
    await app.state.background_services.stop_all()   # token 刷新 / reaper / 模型刷新
    await app.state.rate_limiter.drain_queue()
    # 注意：不在此处关闭 history DB —— 见上文说明

    # Phase 2: Graceful Wait
    logger.info(f"[Shutdown] Phase 2: waiting up to {settings.graceful_wait}s for active requests")
    deadline = time.monotonic() + settings.graceful_wait
    while time.monotonic() < deadline and manager.active_count > 0:
        await asyncio.sleep(1)

    # Phase 3: Abort
    if manager.active_count > 0:
        logger.warning(f"[Shutdown] Phase 3: aborting {manager.active_count} request(s)")
        manager.abort_all()
        deadline = time.monotonic() + settings.abort_wait
        while time.monotonic() < deadline and manager.active_count > 0:
            await asyncio.sleep(1)

    # Phase 4: Force Close + finalize
    logger.info("[Shutdown] Phase 4: force close + finalize")
    await app.state.rate_limiter.shutdown()          # 排空限流队列、释放等待者
    await app.state.approval_gate.reject_all_pending("server shutting down")  # 拒绝待审批
    await app.state.upstream.close()               # 含上游 WebSocket，顺序：客户端连接先关
    await app.state.history_store.close()           # finalize：DB 真正关闭
    await app.state.ws_manager.close_all()           # 观察者 WebSocket 客户端
    asyncio.ensure_future(app.state.telemetry.close())  # fire-and-forget，不阻塞退出
    logger.info("[Shutdown] Complete")
```

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `shutdown.graceful_wait` | `60` | Phase 2 等待秒数 |
| `shutdown.abort_wait` | `120` | Phase 3 等待秒数 |

## 信号升级

进程在优雅关闭过程中若再次收到终止信号（SIGINT/SIGTERM），行为取决于当前所处阶段——这允许运维人员通过"再按一次 Ctrl+C"来加速关闭，而不是傻等 60+120 秒：

| 当前 Phase | 再次收到信号的效果 |
|-----------|-------------------|
| Phase 1 | **忽略**（Phase 1 本身很快完成，几乎立即进入 Phase 2；忽略也能防止某些进程管理场景下父子进程各发一次信号导致意外双重处理） |
| Phase 2 | 跳过剩余等待，**立即升级到 Phase 3**（发送 abort signal） |
| Phase 3 | 跳过剩余等待，**立即升级到 Phase 4**（强制关闭） |
| Phase 4 | 已在强制关闭中，再收到信号直接 `sys.exit(1)` |
| Finalized（已完成关闭流程） | 忽略（清理已经完成，无需任何处理） |

### Python asyncio 实现思路

```python
import asyncio
import signal
from enum import Enum, auto


class ShutdownPhase(Enum):
    RUNNING = auto()
    SETUP = auto()
    GRACEFUL_WAIT = auto()
    ABORT = auto()
    FORCE_CLOSE = auto()
    FINALIZED = auto()


class ShutdownCoordinator:
    """跟踪当前关闭阶段，并根据阶段决定重复信号的效果（信号升级表）。"""

    def __init__(self) -> None:
        self.phase = ShutdownPhase.RUNNING
        self._escalate_event = asyncio.Event()   # 通知当前等待中的 Phase 提前结束

    def register_signal_handlers(self, loop: asyncio.AbstractEventLoop, app: FastAPI) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: self._on_signal(app))

    def _on_signal(self, app: FastAPI) -> None:
        match self.phase:
            case ShutdownPhase.RUNNING:
                self.phase = ShutdownPhase.SETUP
                asyncio.ensure_future(graceful_shutdown(app))
            case ShutdownPhase.SETUP:
                pass  # 忽略——Setup 很快自然推进到 Graceful Wait
            case ShutdownPhase.GRACEFUL_WAIT | ShutdownPhase.ABORT:
                self._escalate_event.set()  # 唤醒当前阶段的等待循环，提前进入下一阶段
            case ShutdownPhase.FORCE_CLOSE:
                sys.exit(1)
            case ShutdownPhase.FINALIZED:
                pass  # 忽略——清理已完成
```

`graceful_shutdown()` 内部的 Phase 2 / Phase 3 等待循环应同时 `await` 自身超时与 `_escalate_event`，两者任一先触发就结束等待、进入下一阶段：

```python
async def _wait_or_escalate(deadline: float, escalate_event: asyncio.Event, check: Callable[[], bool]) -> None:
    while time.monotonic() < deadline and check():
        try:
            await asyncio.wait_for(escalate_event.wait(), timeout=1.0)
            return  # 收到升级信号，提前结束
        except asyncio.TimeoutError:
            continue  # 正常的每秒轮询
```

## 稳定 Shutdown Signal

### 为什么必须 eager 创建

一个容易被忽视但会造成严重后果的时序陷阱：**如果代表"关闭中"的信号对象是在 Phase 1 才创建的，那么在 Phase 1 之前就已经阻塞在某个停滞上游流上的请求，将永远观察不到后续的 abort**。

具体场景：某个流式请求正阻塞在 `await stream.__anext__()` 上等待上游数据（比如上游进入了长时间静默），而这个 `await` 是在关闭流程开始**之前**就已经在执行的。如果它在发起这次 `await` 时拿到的是"尚不存在信号"（因为信号要等到 Phase 1 才创建），那么无论后续 Phase 3 如何调用 abort，这个已经在等待中的协程都不会收到任何通知——它只能靠自己的空闲超时机制自然结束，或者一路挂到 Phase 4 被强制关闭连接。

因此，代表 shutdown 的信号必须在**进程启动时就 eager 创建**（而非等到收到关闭信号才创建），且是**全进程唯一的单例**，每个在途请求 / 上游调用在**发起时**就把这个信号注册进自己的等待逻辑，而不是等到需要检查时才去"寻找"它。

### Python asyncio 的等价设计

```python
class ShutdownSignal:
    """
    进程启动即创建的单例、不可取消的关闭信号。Phase 3 只调用一次 trigger()。
    每个在途请求 / 上游调用在发起 await 之前，把这个 event 折入自己的等待逻辑
    （例如 asyncio.wait([task, signal.wait()], return_when=FIRST_COMPLETED)），
    从而即使该协程早于 Phase 1 就已经在等待，也能在 Phase 3 abort 时被唤醒。
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def trigger(self) -> None:
        """Phase 3 调用，且只应调用一次（幂等：Event.set() 本身天然幂等）。"""
        self._event.set()

    @property
    def is_triggered(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


# 应用启动时（server.py 的 lifespan 开始处）立即创建，绝不延迟：
SHUTDOWN_SIGNAL = ShutdownSignal()
```

在流式消费者中折入该信号的典型用法：

```python
async def guarded_stream_iteration(stream: AsyncIterator[SseEvent], shutdown: ShutdownSignal) -> AsyncIterator[SseEvent]:
    """把稳定 shutdown 信号 + per-request 客户端断开信号折入流迭代，
    保证即使协程在 Phase 1 之前就已发起 __anext__()，也能在 Phase 3 abort 时被唤醒。"""
    it = stream.__aiter__()
    shutdown_wait_task = asyncio.ensure_future(shutdown.wait())
    try:
        while True:
            next_task = asyncio.ensure_future(it.__anext__())
            done, pending = await asyncio.wait(
                {next_task, shutdown_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shutdown_wait_task in done:
                next_task.cancel()
                raise StreamAbortedByShutdown()
            try:
                yield next_task.result()
            except StopAsyncIteration:
                return
    finally:
        shutdown_wait_task.cancel()  # 显式清理，确保每个流恰好持有一个 waiter，不依赖 GC 回收
```

### 约束

- **该单例从不重建**，也不支持"取消 shutdown"——一旦 Phase 3 触发过一次，`is_triggered` 恒为 `True`，直到进程退出。若未来需要支持"取消正在进行的关闭流程"，需要重新设计这个单例的生命周期，当前设计**明确不支持**。
- **判断"是否在 draining"应使用独立的 `app.state.draining` 布尔标志**（Phase 1 置位），而不是用"信号是否存在"来判断——因为信号本身是 eager 创建、进程启动起就一直存在的，其存在性不携带任何"是否在关闭"的信息，只有 `is_triggered`（对应 Phase 3 之后）或独立的 draining 标志才携带这个语义。
- **显式移除 listener/waiter**：每个流对该共享信号的等待都应在退出路径上显式清理（如上例的 `finally: shutdown_wait_task.cancel()`），确保共享信号上"每个流恰好一个等待者"，回收是确定性的、不依赖垃圾回收时机。

## 请求上下文管理

### RequestContextManager

`pipeline/manager.py` 中的 `RequestContextManager` 跟踪所有活跃请求的生命周期：

```python
class RequestContextManager:
    def __init__(self, *, stale_max_age: int = 600, request_deadline: int = 0):
        self._active: dict[str, RequestContext] = {}
        self._lock = asyncio.Lock()
        self._sinks: list[ContextSink] = []
        self._stale_max_age = stale_max_age
        self._request_deadline = request_deadline
        self._reaper_task: asyncio.Task | None = None

    async def register(self, ctx: RequestContext) -> None:
        async with self._lock:
            self._active[ctx.id] = ctx
        if self._request_deadline > 0:
            ctx.arm_deadline(self._request_deadline, on_expire=lambda: asyncio.ensure_future(self._force_fail(ctx)))

    async def complete(self, ctx: RequestContext) -> None:
        ctx.disarm_deadline()
        async with self._lock:
            self._active.pop(ctx.id, None)
        await self._notify_sinks(ctx, event="completed")

    async def fail(self, ctx: RequestContext) -> None:
        ctx.disarm_deadline()
        async with self._lock:
            self._active.pop(ctx.id, None)
        await self._notify_sinks(ctx, event="failed")

    @property
    def active_count(self) -> int:
        return len(self._active)

    def abort_all(self) -> None:
        """Phase 3 调用：向所有活跃请求发送 abort signal。"""
        for ctx in self._active.values():
            ctx.abort()
```

### RequestContext 状态机

> `RequestContext` 的完整数据结构（含清洗结果、审批状态、限流等待、response/error 等全字段）以 [request-pipeline.md](request-pipeline.md) 为权威定义。本节只展开与关闭生命周期相关的子集（abort 通路、deadline 计时器）。

```
pending ──▶ executing ──▶ streaming ──▶ completed
   │            │             │
   └────────────┴─────────────┴──▶ failed / aborted
```

```python
class RequestContext:
    def __init__(self, *, endpoint: str, request_id: str):
        self.id = request_id
        self.endpoint = endpoint
        self.state: RequestState = "pending"
        self.created_at = time.monotonic()
        self.attempts: list[Attempt] = []          # 每次 attempt 独立记录
        self._abort_event = asyncio.Event()
        self._deadline_handle: asyncio.TimerHandle | None = None

    def transition(self, new_state: RequestState) -> None:
        self.state = new_state

    def abort(self) -> None:
        self._abort_event.set()

    @property
    def is_aborted(self) -> bool:
        return self._abort_event.is_set()

    @property
    def abort_signal(self) -> asyncio.Event:
        """供流式处理检查是否应中止。"""
        return self._abort_event

    def arm_deadline(self, seconds: float, *, on_expire: Callable[[], None]) -> None:
        loop = asyncio.get_running_loop()
        self._deadline_handle = loop.call_later(seconds, on_expire)

    def disarm_deadline(self) -> None:
        if self._deadline_handle is not None:
            self._deadline_handle.cancel()
            self._deadline_handle = None
```

每次重试都会在 `attempts` 中追加一条独立记录（模型、上游状态码、耗时、错误类型），供 History 与错误持久化消费。

### Sink（观察者）消费模型

请求终态发生时，`RequestContextManager` 通知已注册的 sink，取代"消费者"式的紧耦合注册模式，采用发布订阅：

| Sink | 职责 |
|------|------|
| `HistorySink` | 异步落盘请求终态（off-loop，见 [history-system.md](history-system.md)） |
| `WsSink` | 通过 History WebSocket 向前端实时推送 |
| `TelemetrySink` | 记录请求遥测（model/tokens/duration），fire-and-forget |
| `ConsoleSink` | 结构化日志输出 |

各 sink 之间互不阻塞——一个 sink 的异常不应影响其他 sink 或请求本身的响应（遵循 never-swallow-errors：sink 内部异常需要被捕获并记日志，但不能向上抛出打断请求主流程）。

## Stale Request Reaper

定期扫描是否有请求超过最大存活时间，超时的请求被强制清理，作为**安全网机制**：

```python
async def _reap_stale_requests(manager: RequestContextManager) -> None:
    """周期性检查活跃请求是否超龄，超龄则强制失败清理。"""
    while True:
        await asyncio.sleep(60)  # 扫描周期
        if manager._stale_max_age <= 0:
            continue

        now = time.monotonic()
        stale = [
            ctx for ctx in manager._active.values()
            if now - ctx.created_at > manager._stale_max_age
        ]
        for ctx in stale:
            logger.warning(f"[StaleReaper] {ctx.id} exceeded max age ({manager._stale_max_age}s), forcing cleanup")
            ctx.fail_with(ApiError(type="stale_request", message="Request exceeded max age"))
            await manager.fail(ctx)
```

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `timeouts.stale_request_max_age` | `600` | 活跃请求最大存活秒数（0=禁用） |

Reaper 是**周期扫描**，天然存在扫描粒度带来的迟到可能——正常情况下请求应通过流式完成或自身的 idle 超时自然终结，reaper 只是兜底异常情况（请求卡住、且没有被其他超时机制清理）。

## Hard Request Deadline `[采纳]`

### 解决的问题

Stale Reaper 是周期扫描，存在结构性的"迟到"风险：扫描周期本身有粒度、配置热重载可能改变阈值但扫描节奏未必同步跟上、更极端的情况下（如进程或所在容器被挂起后恢复）所有基于扫描节奏的机制都会一起延后触发。这些都会导致"某个请求早就该被判定超时，但 reaper 还没轮到它"。

Hard Request Deadline 用**每请求独立的精确定时器**解决这个问题——不依赖扫描节奏，到点即触发，从根本上绕开 reaper 迟到的可能性。

### 机制

```python
def register(self, ctx: RequestContext) -> None:
    ...
    if self._request_deadline > 0:
        ctx.arm_deadline(
            self._request_deadline,
            on_expire=lambda: asyncio.ensure_future(self._force_fail_on_deadline(ctx)),
        )

async def _force_fail_on_deadline(self, ctx: RequestContext) -> None:
    """精确到点触发：取消在飞上游调用（若有），记为失败终态。"""
    ctx.abort()  # 复用与 Phase 3 相同的 abort 通路取消上游调用
    ctx.fail_with(ApiError(type="request_deadline_exceeded", message=f"Request exceeded deadline of {self._request_deadline}s"))
    await self.fail(ctx)
```

`asyncio.get_running_loop().call_later()` 提供的定时器由事件循环调度，精度不依赖任何周期扫描节奏，故不受"扫描迟到"问题影响（但仍受事件循环本身被阻塞或进程被挂起的影响，这与 reaper 面临的底层限制相同，只是消除了"扫描粒度"这一层额外的迟到来源）。

### 两个旋钮的关系

| 配置项 | 默认值 | 性质 |
|--------|--------|------|
| `timeouts.request_deadline` | `0`（禁用；上游 bundled 默认 `900`） | 精确、per-request 计时器，是用户可依赖的单请求 SLA 上限 |
| `timeouts.stale_request_max_age` | `600` | 周期扫描，兜底 deadline 未覆盖到的异常泄漏场景 |

**`request_deadline` 应小于 `stale_request_max_age`**——deadline 是精确的主上限，reaper 只兜底"越过 deadline 后仍未被正常清理"的异常情况（例如 deadline 触发的 abort 因为某种原因没有被正确处理）。若两者数值颠倒（deadline 大于 stale_max_age），reaper 会先于 deadline 触发，使 deadline 形同虚设。

## 错误持久化消费者

请求失败时，作为一个独立的 sink，把错误信息 fire-and-forget 写入文件系统，便于事后诊断：

```python
class ErrorPersistenceSink:
    def __init__(self, settings: AppSettings):
        self._error_dir = get_error_persistence_dir()  # ~/.config/ghc-api-proxy/errors/
        self._error_dir.mkdir(parents=True, exist_ok=True)

    async def on_request_failed(self, ctx: RequestContext) -> None:
        if ctx.error is None:
            return
        error_file = self._error_dir / f"{ctx.id}.json"
        error_data = {
            "request_id": ctx.id,
            "timestamp": ctx.created_at,
            "model": ctx.resolved_model,
            "endpoint": ctx.endpoint,
            "error": {
                "type": ctx.error.type,
                "message": ctx.error.message,
                "status_code": ctx.error.status_code,
            },
            "attempts": len(ctx.attempts),
        }
        try:
            async with aiofiles.open(error_file, "w") as f:
                await f.write(json.dumps(error_data, indent=2, ensure_ascii=False))
        except OSError as exc:
            # never-throw：写盘失败不应影响请求已经完成的失败流程，仅记日志
            logger.warning(f"[ErrorPersistence] failed to write {error_file}: {exc}")
```

### 性能考量

写入是 **off-loop、never-throw** 的：`aiofiles` 异步写入不阻塞事件循环；写入异常被捕获并降级为警告日志，绝不向上抛出影响请求本身的响应路径（此时响应早已完成，抛出异常也无意义，只会污染日志或造成未处理异常告警噪音）。错误文件保存在 `~/.config/ghc-api-proxy/errors/` 目录下。

## 优雅重启（零停机换代）`[上游未落地][缓存/延后]`

上游参考项目对"优雅重启"（新进程接管旧进程、换代期间零停机）有完整的设计文档，但**其自身状态明确标注为"设计（未实现）"**——包含未解决的 `sd_notify` 传输方式 PoC（Node/Bun 环境下 AF_UNIX datagram 支持存在已知障碍）、以及多个已识别但未修复的 overlap 期竞态问题（history reclaim 误杀在途请求、遥测 rollup 并发重复上卷、状态文件覆盖竞争等）。

本项目的决策：**不复刻上游这套未落地的方案**。理由：

1. 上游自己都没有跑通，直接照搬等于把别人未验证的设计负担和已知竞态一起继承过来。
2. 上游方案高度绑定 Bun/Node 的 `SO_REUSEPORT` 与进程模型细节，Python/uvicorn 的等价实现需要重新调研（uvicorn 对多进程接管、`SO_REUSEPORT` 的支持路径与 Bun 不同）。
3. 更成熟的路径是依赖**进程管理器**（如 systemd 的 blue-green 双实例模板单元、或其他 supervisor）配合 `SO_REUSEPORT`，把"谁来接管、何时切换"的编排权交给运维层，而不是在应用代码里自己实现一套接管协议。

具体设计留待需要时另行评估，参见 [ROADMAP.md](ROADMAP.md) 借鉴但暂缓能力表。当前版本的优雅关闭（4 阶段 + 信号升级）本身足以配合外部进程管理器实现"先起新实例、再优雅关闭旧实例"的最基本形式的滚动更新，只是不追求上游文档描述的"重叠窗口零丢包"级别保证。

## 健康检查交互

`routes/health.py` 在 draining 状态下改变 readiness 探针的返回，但 liveness 探针保持恒定：

```python
@router.get("/health/readiness")
async def readiness(request: Request):
    if getattr(request.app.state, "draining", False):
        return JSONResponse(status_code=503, content={"status": "draining"})
    # 正常情况下还应检查 token 有效性、模型列表是否已加载等
    return {"status": "ready"}


@router.get("/health/liveness")
async def liveness(request: Request):
    # 恒返回 200 —— liveness 只回答"进程是否还活着"，不掺杂业务态判断，
    # 且必须先于 token 中间件与关闭门执行，避免进程尚未完成鉴权初始化时
    # 被编排系统误判为"活着但不健康"而重启
    return {"status": "alive"}
```

- `/health/readiness`：draining 期间返回 503，通知负载均衡器停止向本实例转发新请求，这是 Phase 1 立即生效的信号。
- `/health/liveness`：恒返回 200，只要进程本身没有崩溃就应该是健康的——这条探针的意义是让容器编排系统区分"进程卡死需要重启"与"进程正常但暂时不接受新流量（draining）"，混淆两者会导致编排系统在优雅关闭期间粗暴杀死正在完成 drain 的进程。

## 与其他模块的交互

### 关闭时的清理顺序

```python
# server.py lifespan 关闭阶段
async with graceful_shutdown_context(app):
    # Phase 1-3：处理活跃请求（见上文）
    # Phase 4 finalize：
    await app.state.upstream.close()                 # 1. 关闭上游 HTTP 客户端（含上游 WebSocket）
    await app.state.rate_limiter.shutdown()           # 2. 关闭限流器
    await app.state.approval_gate.reject_all_pending("server shutting down")  # 3. 拒绝所有待审批请求
    await app.state.history_store.close()             # 4. 关闭 History DB（finalize）
    await app.state.ws_manager.close_all()             # 5. 关闭观察者 WebSocket 客户端
    asyncio.ensure_future(app.state.telemetry.close()) # 6. fire-and-forget 关闭遥测
```

## 相关文档

- [设计文档总纲](DESIGN.md)
- [流式韧性](streaming-resilience.md)（keepalive 心跳与本篇的 shutdown signal 折入方式互相印证）
- [请求执行管道](request-pipeline.md)
- [历史与审计](history-system.md)
- [配置系统](config-system.md)
- [ROADMAP.md](ROADMAP.md)（优雅重启的暂缓决策）
