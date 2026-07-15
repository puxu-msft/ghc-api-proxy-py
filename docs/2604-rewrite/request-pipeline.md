# 请求执行管道

## 概述

`pipeline/executor.py` 中的 `execute_pipeline()` 编排请求从接收到响应的完整生命周期。使用策略模式处理请求失败，根据错误类型选择合适的重试策略。

**Python 优化**：JS 版本的管道由 `executeRequestPipeline()` 函数实现，重试策略以数组形式传入。Python 版本通过 FastAPI 依赖注入获取管道组件，并额外集成了审批门控（JS 版本无此功能）。

## 管道阶段

```
清洗 (Sanitize) → 审批 (Approval) → 限流 (Rate Limit) → 执行 (Execute) → 重试 (Retry)
```

## RequestContext — 请求生命周期追踪

### 状态机

```
pending
    │
    ▼
sanitizing ──→ awaiting_approval ──→ executing ──→ streaming ──→ completed
    │               │                    │             │
    └───────────────┴────────────────────┴─────────────┴──→ failed
```

### 数据结构

```python
@dataclass
class RequestContext:
    id: str                           # uuid4
    endpoint: Literal["openai-chat-completions", "openai-responses", "anthropic-messages"]
    state: RequestState
    created_at: float
    completed_at: float | None

    original_model: str               # 用户请求的模型名
    resolved_model: str               # 解析后的模型名
    original_payload: dict            # 原始请求体

    sanitization: SanitizationResult | None
    approval_status: ApprovalStatus | None
    rate_limiter_wait_ms: float

    attempts: list[Attempt]
    current_attempt: int

    response: ResponseData | None
    error: ApiError | None
```

## 执行流程

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

    # 1. 清洗（Phase 2，Phase 1 已在路由层执行）
    ctx.transition("sanitizing")
    payload, sanitization = sanitizer.sanitize(payload, ctx.endpoint)
    ctx.sanitization = sanitization

    # 2. 审批（可选）
    if approval_gate.enabled:
        ctx.transition("awaiting_approval")
        approval = await approval_gate.wait_for_approval(ctx)
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
                return PipelineResult(response=response, context=ctx)

            # 错误分类
            error = classify_error(response.status_code, await response.aread())
            attempt.error = error

            # 限流反馈
            if error.type == "rate_limited":
                rate_limiter.report_rate_limit(error.retry_after)

            # 匹配重试策略
            for strategy in retry_strategies:
                if strategy.can_handle(error):
                    action = await strategy.handle(error, payload, ctx)
                    if action.should_retry:
                        payload = action.modified_payload
                        attempt.strategy_applied = strategy.name
                        attempt.payload_modifications = action.modifications
                        break
            else:
                # 没有策略能处理
                ctx.fail(error)
                raise UpstreamError(error)

        except httpx.TimeoutException:
            attempt.error = ApiError(type="timeout", message="Upstream timeout")
            ctx.fail(attempt.error)
            raise
```

## 重试策略

### RetryStrategy 协议

```python
class RetryStrategy(Protocol):
    @property
    def name(self) -> str: ...

    def can_handle(self, error: ApiError) -> bool: ...

    async def handle(
        self, error: ApiError, payload: dict, ctx: RequestContext,
    ) -> RetryAction: ...

@dataclass
class RetryAction:
    should_retry: bool
    modified_payload: dict
    modifications: list[str]
```

### 策略列表

| 策略 | 触发条件 | 行为 |
|------|----------|------|
| `NetworkRetryStrategy` | 网络错误（ECONNRESET / ETIMEDOUT / socket 关闭等） | 延迟 1 秒后重试一次，不修改 payload |
| `TokenRefreshStrategy` | 401/403 | 刷新 Copilot token 后重试 |
| `AutoTruncateStrategy` | token 超限错误（413 或 400+token 模式） | 截断 payload 后重试 |
| `OrphanCleanupStrategy` | 400 + tool 配对错误 | 清理孤立 tool 块后重试 |
| `DeferredToolRetryStrategy` | tool 相关错误（deferred tool loading 场景） | 调整 tool 配置（如取消 defer）后重试 |
| `PoisonedThinkingRetryStrategy` `[新增]` | 400 且 body 匹配“thinking ... cannot be modified” | 剥离该请求全部 thinking blocks 后重试一次；若剥离后仍失败或本无 thinking 可剥离则放弃（不做无意义的空 payload 重试）。成功后**学习**：把该 `(session, agent)` 标记为“中毒会话”，写入内存隔离表（L3），后续同会话的新一轮请求在发送前就主动剥离 thinking，而不必再走一次反应式 400 才发现。详见 [thinking-pipeline.md](thinking-pipeline.md) 的 L2/L3 分层 |
| `ServerToolRejectionRetryStrategy` `[新增]` | 400 且 body 匹配特定 server tool 不受支持的错误模式（如 `"the use of the web search tool is not supported"`） | 从错误消息命中的 server tool type 前缀出发：① 剥离该 tool 类型后重试一次；② 若剥离重试仍不能满足调用意图，**降级响应**而非直接向客户端返回失败——即把该 server tool 相关的请求语义降级为“该 tool 不可用”的结构化提示，让对话继续而不是整轮失败。同时把该 `(model, tool_type)` 标记写入 feature negotiation 缓存，后续同模型请求预先剥离该 server tool。详见 [tool-use.md](tool-use.md) 的 Server Tool 处理 |

**表驱动而非硬编码正则**：`ServerToolRejectionRetryStrategy` 的“上游错误消息 → server tool type 前缀”映射维护为一张显式的表（而非分散的正则判断），新增一种可观测到的 server tool 拒绝模式 = 表中新增一行，未建模的拒绝消息不匹配任何行、走正常的失败路径（不做推测性的强行剥离）。

### AutoTruncateStrategy 详情

**触发条件：**
- HTTP 413 状态码
- HTTP 400 且错误消息匹配 token 超限模式

**处理逻辑：**
```
1. 从 messages 数组中识别可截断的消息
   - 保留 system 消息（不可截断）
   - 保留最近 30% 对话
   - 优先截断较旧的 tool_result 内容

2. 截断策略（依次尝试）：
   Step 1: 压缩旧的 tool_result 内容为摘要（如果 compress_tool_results_before_truncate 启用）
   Step 2: 移除最旧的消息对（user + assistant）
   Step 3: 进一步移除，直到低于估算限制

3. 记录截断详情到 attempt.payload_modifications
4. 重新执行 Phase 2 清洗（截断可能产生新的孤儿块）
```

**Token 限制学习：**
- 从错误响应中提取模型的实际 token 限制（如 `"token limit: 200000"`）
- 缓存到 `auto_truncate/token_limits.py`
- 后续请求可以在发送前预判是否超限（主动截断）

### TokenRefreshStrategy 详情

**触发条件：** HTTP 401 或 403

**处理逻辑：**
```
收到 401/403
    │
    ▼
调用 copilot_auth.refresh()
    │
    ▼
更新请求头中的 Authorization
    │
    ▼
RetryAction(should_retry=True)
```

## 错误分类

`errors.py` 中的 `classify_error()` 将原始 HTTP 错误分类为结构化的 `ApiError`：

| ApiErrorType | HTTP 状态码 | 说明 |
|-------------|------------|------|
| `rate_limited` | 429 | 速率限制 |
| `payload_too_large` | 413 | 请求体过大 |
| `token_limit` | 400（body 含 token 超限模式） | Token 超限，触发 `AutoTruncateStrategy` |
| `content_filtered` | 422 | Responsible AI 内容过滤（不可重试，直接向客户端透传） |
| `quota_exceeded` | 402 | 使用配额耗尽（不可重试，直接向客户端透传） |
| `auth_expired` | 401/403 | Token 过期，触发 `TokenRefreshStrategy` |
| `network_error` | 0（无 HTTP 响应） | 连接失败，触发 `NetworkRetryStrategy` |
| `server_error` | 5xx（非 503 上游限速） | 服务器错误 |
| `upstream_rate_limited` | 503（body 含 rate limit 关键词模式，如 `"rate limit"` / `"too many requests"`） | 上游 provider（而非 Copilot 网关本身）返回的限速信号，与网关级 `429` 区分对待——同样喂给 `AdaptiveRateLimiter.report_rate_limit()`，但不一定携带标准的 `Retry-After` 头，需要走 body 模式识别 |
| `bad_request` | 400（非 token 超限、非 thinking 拒绝、非 server tool 拒绝等已知模式） | 通用错误，落到兜底分支——若无策略能处理则直接失败 |

`token_limit`、`content_filtered`、`quota_exceeded`、`upstream_rate_limited` 均通过匹配 response body 的已知模式识别（而非仅凭状态码），因为上游/网关对同一状态码在不同错误场景下会复用（如 400 既可能是 token 超限也可能是 thinking 拒绝也可能是 server tool 拒绝），必须结合 body 内容做二次判别才能分派到正确的重试策略或分类。

### Retry-After 解析

从两个来源提取（body 优先）：

1. **Response body**：`retry_after` / `error.retry_after` 字段
2. **Response header**：`Retry-After`（支持秒数和 HTTP-date 两种 RFC 7231 格式）

## 反应式重试预算与 feature negotiation 的关系

反应式重试策略（`PoisonedThinkingRetryStrategy`、`ServerToolRejectionRetryStrategy`、`OrphanCleanupStrategy` 等因请求特征“试错后才发现不支持”而触发的策略）共享一个每请求重试预算：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `retry.max_reactive_retries` | `5` | 所有反应式重试策略（网络/服务端错误/token 刷新/400 类协商等）共享的每请求重试预算上限，见 [config-system.md](config-system.md#顶层其余键) |

这一预算与 [feature-negotiation.md](feature-negotiation.md) 的多类别学习缓存是**互补而非重复**的两层机制：

- **单次请求内**：反应式重试策略在 `max_reactive_retries` 预算内，针对*这一次*请求边试边改（剥离 thinking / 剥离 server tool / 清理孤儿 tool 块等），直到成功或预算耗尽。
- **跨请求学习**：多个反应式策略在重试**成功**后，会把“这次踩到的坑”写入 feature negotiation 的学习缓存（按 `(model, feature)` 或 `(model, tool_type)` 等维度，TTL 裁决）。后续对**同一模型**的新请求，在发送前的请求准备阶段（`anthropic/request_preparation.py`）就直接查询这份缓存并主动跳过已知不支持的功能/tool，不必再走一次“发送 → 400 → 反应式剥离 → 重试”的完整回合。

换言之：反应式重试策略解决的是“这一次怎么把当前请求救回来”，feature negotiation 解决的是“下一次怎么避免重蹈覆辙”。二者共享同一份“踩坑事实”，但作用的时间窗口不同——前者作用于单次请求生命周期内，后者作用于跨请求的 TTL 窗口内。详见 [feature-negotiation.md](feature-negotiation.md)。

## 自适应速率限制器

`pipeline/rate_limiter.py` 中的 `AdaptiveRateLimiter` 在 3 种模式间切换：

### 模式

```
Normal（正常）
    │
    ├─ 收到 429 → Rate-Limited（限流中）
    │                    │
    │                    ├─ 等待 retry_after 或指数退避
    │                    ├─ 请求通过 asyncio.Event 排队等待
    │                    │
    │                    └─ 重试成功 → Recovering（恢复中）
    │                                        │
    │                                        ├─ 按间隔放行请求
    │                                        ├─ 连续 N 次成功
    │                                        │
    └────────────────────────────────────────┘
```

### 配置 `[更正]`

以 [config-system.md](config-system.md#rate_limiter-section) 为权威来源，键名与单位如下（**注意**：本节以前的旧版本键名/单位有误，已按下表更正）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `rate_limiter.retry_interval` | `10`（秒） | 退避重试间隔 |
| `rate_limiter.request_interval` | `10`（秒） | 恢复阶段的请求最小间隔 |
| `rate_limiter.recovery_interval` | `600`（秒） | 从限流恢复模式的等待时长——**单位是秒**，不是旧文档写的“分钟”（`recovery_timeout_minutes`） |
| `rate_limiter.consecutive_successes` | `5` | 恢复所需连续成功次数 |

### 实现

```python
class AdaptiveRateLimiter:
    async def acquire(self) -> float:
        """等待限流器放行。返回等待毫秒数。"""
        if self._mode == "normal":
            return 0
        start = time.time()
        await self._gate.wait()
        return (time.time() - start) * 1000

    def report_success(self) -> None:
        if self._mode == "rate_limited":
            self._mode = "recovering"
            self._consecutive_successes = 1
        elif self._mode == "recovering":
            self._consecutive_successes += 1
            if self._consecutive_successes >= self._needed:
                self._mode = "normal"
                self._gate.set()

    def report_rate_limit(self, retry_after: float | None) -> None:
        self._mode = "rate_limited"
        self._gate.clear()
        backoff = retry_after or min(
            self._current_backoff * 2 or self._base,
            self._max,
        )
        asyncio.create_task(self._schedule_retry(backoff))
```

### 超时恢复

长时间（默认 10 分钟）处于 Rate-Limited 状态且没有成功请求时自动尝试恢复。

## 管道结果

```python
@dataclass
class PipelineResult:
    context: RequestContext
    response: httpx.Response | None
    stream: AsyncIterator[bytes] | None
    is_streaming: bool
```

## 相关文档

- [设计文档总纲](DESIGN.md)
- [消息清洗管道](sanitize-pipeline.md)
- [手动审批系统](approval-system.md)
- [流式处理](streaming.md)
- [认证系统](authentication.md)（TokenRefreshStrategy）
- [Thinking 管道](thinking-pipeline.md)（PoisonedThinkingRetryStrategy 的 L2/L3 分层）
- [Tool Use](tool-use.md)（ServerToolRejectionRetryStrategy 的降级响应机制）
- [Feature Negotiation](feature-negotiation.md)（反应式重试与跨请求学习缓存的关系）
- [配置系统](config-system.md)（`rate_limiter`/`retry`/`approval` 等 section 权威定义）
