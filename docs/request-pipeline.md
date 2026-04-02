# 请求执行管道

## 概述

请求执行管道（`pipeline/`）是系统的核心，负责编排一个请求从接收到响应的完整生命周期。管道由以下阶段顺序组成：

```
清洗 (Sanitize) → 审批 (Approval) → 限流 (Rate Limit) → 执行 (Execute) → 重试 (Retry)
```

## RequestContext - 请求生命周期追踪

每个请求创建一个 `RequestContext` 实例，追踪其完整生命周期。

### 状态机

```
pending
    │
    ▼
sanitizing ──→ awaiting_approval ──→ executing ──→ streaming ──→ completed
    │               │                    │             │
    └───────────────┴────────────────────┴─────────────┴──→ failed
```

| 状态 | 说明 |
|------|------|
| `pending` | 请求已接收，尚未进入管道 |
| `sanitizing` | 正在执行消息清洗 |
| `awaiting_approval` | 等待手动审批（仅当审批启用时） |
| `executing` | 正在发送到上游 |
| `streaming` | 正在接收上游流式响应 |
| `completed` | 请求成功完成 |
| `failed` | 请求失败（错误、拒绝、超时） |

### 数据结构

```python
@dataclass
class RequestContext:
    id: str                           # 唯一请求 ID（uuid4）
    endpoint: Literal["openai-chat-completions", "openai-responses", "anthropic-messages"]
    state: RequestState
    created_at: float                 # time.time()
    completed_at: float | None

    # 原始请求
    original_model: str               # 用户请求的模型名
    resolved_model: str               # 解析后的模型名
    original_payload: dict            # 原始请求体（用于历史记录）

    # 管道处理详情
    sanitization: SanitizationResult | None
    approval_status: ApprovalStatus | None
    rate_limiter_wait_ms: float       # 限流器等待耗时

    # 执行
    attempts: list[Attempt]           # 所有尝试（含重试）
    current_attempt: int

    # 响应
    response: ResponseData | None
    error: ApiError | None

    def transition(self, new_state: RequestState) -> None: ...
    def add_attempt(self, attempt: Attempt) -> None: ...
    def complete(self, response: ResponseData) -> None: ...
    def fail(self, error: ApiError) -> None: ...
    @property
    def duration_ms(self) -> float: ...

@dataclass
class Attempt:
    number: int
    started_at: float
    completed_at: float | None
    status_code: int | None
    error: ApiError | None
    strategy_applied: str | None      # 应用的重试策略名称
    payload_modifications: list[str]  # 对 payload 的修改描述

@dataclass
class SanitizationResult:
    orphaned_blocks_removed: int
    empty_blocks_removed: int
    system_tags_stripped: int
    tool_names_fixed: int
```

## 管道执行器

`executor.py` 实现核心执行循环。

### 执行流程

```python
async def execute_pipeline(
    ctx: RequestContext,
    payload: dict,
    *,
    upstream: UpstreamTarget,
    sanitizer: MessageSanitizer,
    approval_gate: ApprovalGate,
    rate_limiter: AdaptiveRateLimiter,
    retry_strategies: list[RetryStrategy],
    history_store: HistoryStore,
    max_retries: int = 5,
) -> PipelineResult:
    """
    执行请求管道。

    返回:
        PipelineResult: 包含响应（或流式迭代器）和上下文
    """

    # 1. 清洗
    ctx.transition("sanitizing")
    payload, sanitization = sanitizer.sanitize(payload, ctx.endpoint)
    ctx.sanitization = sanitization

    # 2. 审批
    if approval_gate.enabled:
        ctx.transition("awaiting_approval")
        approval = await approval_gate.wait_for_approval(ctx.id, payload)
        ctx.approval_status = approval.status
        if approval.status == "rejected":
            ctx.fail(ApiError(type="rejected", message=approval.reason))
            raise RequestRejectedError(approval.reason)
        if approval.modified_payload:
            payload = approval.modified_payload

    # 3. 执行（含限流和重试）
    ctx.transition("executing")
    for attempt_num in range(max_retries + 1):
        attempt = Attempt(number=attempt_num, started_at=time.time())
        ctx.add_attempt(attempt)

        try:
            # 限流器等待
            wait_ms = await rate_limiter.acquire()
            ctx.rate_limiter_wait_ms += wait_ms

            # 发送请求
            response = await upstream.send(payload, stream=payload.get("stream", False))
            attempt.status_code = response.status_code
            attempt.completed_at = time.time()

            if response.is_success:
                rate_limiter.report_success()
                # 处理响应...
                return PipelineResult(response=response, context=ctx)

            # 错误分类
            error = classify_error(response.status_code, await response.aread())
            attempt.error = error

            # 限流反馈
            if error.type == "rate_limited":
                retry_after = error.retry_after
                rate_limiter.report_rate_limit(retry_after)

            # 匹配重试策略
            handled = False
            for strategy in retry_strategies:
                if strategy.can_handle(error):
                    action = await strategy.handle(error, payload, ctx)
                    if action.should_retry:
                        payload = action.modified_payload
                        attempt.strategy_applied = strategy.name
                        attempt.payload_modifications = action.modifications
                        handled = True
                        break

            if not handled:
                ctx.fail(error)
                raise UpstreamError(error)

        except httpx.TimeoutException:
            attempt.error = ApiError(type="timeout", message="Upstream timeout")
            attempt.completed_at = time.time()
            ctx.fail(attempt.error)
            raise

    # 重试次数耗尽
    ctx.fail(ApiError(type="max_retries", message="Max retries exceeded"))
    raise MaxRetriesError()
```

## 重试策略

### RetryStrategy 协议

```python
class RetryStrategy(Protocol):
    @property
    def name(self) -> str:
        """策略名称，用于日志和历史记录。"""
        ...

    def can_handle(self, error: ApiError) -> bool:
        """判断此策略是否能处理该错误。"""
        ...

    async def handle(
        self,
        error: ApiError,
        payload: dict,
        ctx: RequestContext,
    ) -> RetryAction:
        """
        处理错误，返回重试动作。

        可以修改 payload 并指示管道重试。
        """
        ...

@dataclass
class RetryAction:
    should_retry: bool
    modified_payload: dict          # 修改后的 payload
    modifications: list[str]        # 修改描述列表
```

### 自动截断策略 (auto_truncate)

当上游返回 413（Payload Too Large）或 token 超限错误时，截断较旧的消息。

**触发条件：**
- HTTP 413 状态码
- 错误消息中包含 token 限制相关关键词

**处理逻辑：**

```
1. 从 messages 数组中识别可截断的消息
   - 保留 system 消息（不可截断）
   - 保留最近 N 轮对话（默认保留最近 30%）
   - 优先截断较旧的 tool_result 内容

2. 截断策略：
   - 第一步：压缩旧的 tool_result 内容为摘要
   - 第二步：移除最旧的消息对（user + assistant）
   - 第三步：进一步移除，直到低于估算限制

3. 记录截断详情到 attempt.payload_modifications
```

**学习能力：**
- 记录每个模型的实际 token 限制（从错误响应中提取）
- 后续请求可以进行 proactive 截断（在发送前预判）

### 孤立块清理策略 (orphan_cleanup)

当上游返回 400 且错误指示消息结构异常时，清理孤立的 tool 块。

**触发条件：**
- HTTP 400 状态码
- 错误消息包含 tool_use/tool_result 相关内容

**处理逻辑：**

```
1. 扫描 messages 数组
2. 检查 tool_use 块是否都有匹配的 tool_result
3. 检查 tool_result 块是否都有匹配的 tool_use
4. 移除所有不匹配的孤立块
5. 记录移除的块数量
```

## 自适应限流器

三模式限流系统，根据上游反馈动态调整请求频率。

### 模式

```
Normal（正常）
    │
    ├─ 收到 429 ──→ Rate-Limited（限流中）
    │                    │
    │                    ├─ 等待 retry_after 或指数退避
    │                    ├─ 请求排队等待
    │                    │
    │                    └─ 重试成功 ──→ Recovering（恢复中）
    │                                        │
    │                                        ├─ 逐步缩短间隔
    │                                        ├─ 连续 N 次成功
    │                                        │
    └────────────────────────────────────────┘
```

### 详细状态

```python
class AdaptiveRateLimiter:
    def __init__(self, settings: AppSettings):
        self._mode: RateLimiterMode = "normal"
        self._base_retry_seconds = settings.rate_limit_base_retry_seconds      # 10
        self._max_retry_seconds = settings.rate_limit_max_retry_seconds        # 120
        self._request_interval = settings.rate_limit_request_interval_seconds  # 10
        self._recovery_timeout = settings.rate_limit_recovery_timeout_minutes  # 10
        self._consecutive_successes_needed = settings.rate_limit_consecutive_successes  # 5

        self._current_backoff: float = 0
        self._consecutive_successes: int = 0
        self._queue: asyncio.Queue = asyncio.Queue()
        self._gate: asyncio.Event = asyncio.Event()

    async def acquire(self) -> float:
        """
        等待限流器放行。
        返回等待的毫秒数。
        """
        if self._mode == "normal":
            return 0

        start = time.time()
        await self._gate.wait()  # 阻塞直到被放行
        return (time.time() - start) * 1000

    def report_success(self) -> None:
        """报告一次成功请求。"""
        if self._mode == "rate_limited":
            self._mode = "recovering"
            self._consecutive_successes = 1
            self._start_recovery()
        elif self._mode == "recovering":
            self._consecutive_successes += 1
            if self._consecutive_successes >= self._consecutive_successes_needed:
                self._mode = "normal"
                self._gate.set()  # 放行所有等待请求

    def report_rate_limit(self, retry_after: float | None) -> None:
        """报告一次 429 限流。"""
        self._mode = "rate_limited"
        self._gate.clear()  # 阻止新请求

        if retry_after:
            self._current_backoff = retry_after
        else:
            # 指数退避
            self._current_backoff = min(
                self._current_backoff * 2 or self._base_retry_seconds,
                self._max_retry_seconds,
            )

        # 启动定时恢复
        asyncio.create_task(self._schedule_retry())

    async def _schedule_retry(self) -> None:
        """等待退避时间后放行一个请求。"""
        await asyncio.sleep(self._current_backoff)
        self._gate.set()  # 放行一个请求

    async def shutdown(self) -> None:
        """关闭限流器，拒绝所有排队请求。"""
        self._gate.set()  # 释放所有等待
```

### 恢复阶段间隔

```
Rate-Limited → Recovering:
    间隔序列: [5s, 3s, 2s, 1s, 0s]
    每次成功请求后缩短间隔
    连续 5 次成功 → 回到 Normal
```

### 超时恢复

如果长时间（默认 10 分钟）处于 Rate-Limited 状态且没有成功请求，自动尝试恢复：

```
Rate-Limited 持续 10 分钟
    → 自动放行一个请求测试
    → 成功 → 进入 Recovering
    → 失败 → 继续 Rate-Limited，重置超时
```

## 错误分类

`errors.py` 将 HTTP 响应分类为标准错误类型：

```python
@dataclass
class ApiError:
    type: str           # 错误类型
    message: str        # 错误描述
    status_code: int    # HTTP 状态码
    retry_after: float | None = None  # 429 时的重试间隔

# 错误类型枚举
ERROR_TYPES = {
    "rate_limited",       # 429
    "payload_too_large",  # 413
    "invalid_request",    # 400
    "auth_error",         # 401, 403
    "server_error",       # 500, 502, 503
    "timeout",            # 请求超时
    "rejected",           # 审批拒绝
    "max_retries",        # 重试耗尽
}

def classify_error(status_code: int, body: bytes) -> ApiError:
    """从 HTTP 响应推断错误类型。"""
    if status_code == 429:
        retry_after = extract_retry_after(body)
        return ApiError("rate_limited", "Rate limited", 429, retry_after)
    elif status_code == 413:
        return ApiError("payload_too_large", "Payload too large", 413)
    elif status_code == 400:
        message = extract_error_message(body)
        return ApiError("invalid_request", message, 400)
    elif status_code in (401, 403):
        return ApiError("auth_error", "Authentication failed", status_code)
    elif status_code >= 500:
        return ApiError("server_error", "Server error", status_code)
    else:
        return ApiError("unknown", f"HTTP {status_code}", status_code)
```

## 管道结果

```python
@dataclass
class PipelineResult:
    """管道执行结果。"""
    context: RequestContext
    response: httpx.Response | None     # 非流式响应
    stream: AsyncIterator[bytes] | None # 流式响应迭代器
    is_streaming: bool

    @property
    def is_success(self) -> bool:
        return self.context.state == "completed"
```

## 相关文档

- [整体架构概览](architecture.md)
- [转换系统](transform-system.md)（清洗阶段详情）
- [手动审批系统](approval-system.md)（审批阶段详情）
- [流式处理](streaming.md)（流式响应处理）
