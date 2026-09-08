# 上游请求失败时本项目当前的实际行为（只读调查）

- 日期：2026-08-21
- 调查基线：`git -C /home/xp/src/ghc-api-proxy-py rev-parse HEAD` = `2bcf03b`（`docs: a squash from an old branch brings both directories back silently`）
- 范围：Anthropic Messages 入站 → OpenAI Responses 上游，直到写出 SSE / JSON 为止
- 纪律：**只读**，未修改任何生产代码，未运行任何测试。下文每条结论标注 `文件:行号`；凡属推断而非代码事实的，单独标 `【推测】`。

---

## 0. 先决事实：live chain 与 legacy chain 的分叉（决定后面所有答案）

这是本次调查最重要的前置结论，如果搞错，第 1～6 题全都会答反。

**进程真正服务的是 `create_pipeline_app`，不是 `routes/anthropic.py`。**

证据链（代码事实）：

1. `src/app/cli.py:23` `from app.server.pipeline_app import create_pipeline_app`；`src/app/cli.py:151` 与 `src/app/cli.py:176` 是仅有的两个建 app 的调用点，都传 `create_pipeline_app(chain)`。
2. `src/app/server/pipeline_app.py:682-696` `create_pipeline_app` 只挂两个 router：`build_router()`（`pipeline_app.py:666-679`，路径表来自 `src/app/server/inbound.py:33-41`）和 `ops_router`。**没有 include `app.routes.anthropic` 的 `anthropic_router`。**
3. `create_app`（`src/app/server/app_factory.py:157`）在 `src/`下无任何调用点（`rg 'create_app' src/` 只有定义处与注释）。`src/app/server/__init__.py:6-12` 的注释也直说 `app_factory` 是 “the existing implementation”，`pipeline_app.py:3-4` 说 “Mounting both would give one path two owners”。

**因此以下模块在生产路径上是死代码**（仅被 legacy chain 或测试引用）：

| 模块 | 唯一引用者 | 证据 |
|---|---|---|
| `src/app/routes/anthropic.py` | 只有 `app_factory`（未被调用） | `rg 'anthropic_router'` 仅 `routes/__init__.py`、`app_factory.py` |
| `src/app/delivery/anthropic_sse.py`、`src/app/delivery/responses_anthropic_stream.py` | `routes/anthropic.py:12`、测试 | 见 §6 |
| `src/app/pipeline/executor.py`、`src/app/anthropic/client.py` | 互相引用 + `deps.py:7` + `upstream/bootstrap.py:10`，均只服务 legacy | `anthropic/client.py:357` |
| `src/app/hooks/**`、`src/app/pipeline/strategies/**`（含 `RetryCoordinator`、`PoisonedThinkingStrategy`） | `app_factory.py:15-18`、`pipeline/executor.py:31` | `rg 'from app.hooks' src/` 中无一行来自 `server/composition.py` 或 `server/pipeline_app.py` |

下文凡说“现在的行为”，一律指 live chain（`pipeline_app` → `handler` → `direct_driver` → `pipeline/delivery`）。legacy 的做法在 §6 单列，因为它和 live chain 的答案**不一样**，容易被误引。

---

## 1. 现在有没有任何重试？

**有，而且是配置化的、分原因计账的重试——但只发生在“上游响应头到达之前”。响应头一旦到达，之后的任何失败都不再重试。**

### 1.1 重试发生的唯一地点

`src/app/pipeline/direct_driver/base.py:126-176` 的 `DirectDriver.run` 是一个 `while True` 循环：

- `base.py:134-146`：`_publish(attempt.prepare)` → `_send()`。任何 `BaseException` 进 `except`，交给 `_handle_failure`，返回 `True` 就 `continue`（即重试）。
- `base.py:150-165`：响应虽已返回，但被 reactive rate limiter 判定为受限状态（429/502）时，把 `outcome.response` 置回 `None`，构造 `UpstreamError` 再走同一条 `_handle_failure`。
- `base.py:167-175`：`attempt.succeeded` / `request.succeeded` 订阅者抛异常也会触发同一条路径。

`_send`（`base.py:221-260`）的 await **在响应头到达时就返回**（`base.py:228` 的注释明确说明并注明 2026-08-20 实测）。所以循环覆盖不到 body。

### 1.2 判定与计账

- 分类：`src/app/pipeline/exceptions.py:105-115` `classify()`。`UpstreamError` 与 `PipelineRetry` → `RETRY`；`PipelineAbort` 及**任何闭集之外的异常** → `ABORT`。
- SDK 异常归一化：`src/app/model_provider/ghc_client/errors.py:80-115` `normalize_upstream_error`，在 `src/app/model_provider/ghc_client/client.py:100-114` 的 `_in_pipeline_terms` 里被每个 `send_*` 调用。
- 命名原因：`src/app/pipeline/retry.py:40-61` `reason_for()`。
- 计账：`src/app/pipeline/retry.py:64-105` `RetryLedger`，经 `LedgerBudget`（`base.py:61-72`）接入，实例化在 `src/app/server/handler.py:149`。

### 1.3 各类失败当前分别走哪条路（代码事实）

| 失败形态 | 归一化结果 | reason | 默认次数上限 | 证据 |
|---|---|---|---|---|
| 连接失败（`httpx2.TransportError` / SDK `APIConnectionError`） | `UpstreamError`（无 status） | `NETWORK` | 9 | `errors.py:112-114`、`retry.py:58-60`、`schema.py:169-171` |
| 超时（SDK `APITimeoutError`） | `UpstreamTimeout` | `NETWORK` | 9 | `errors.py:88-89`、`retry.py:46-47` |
| 500/502/503/504 | `UpstreamError(status)` | `SERVER_ERROR` | 9 | `errors.py:106-111`、`retry.py:56-57`、`schema.py:172-174` |
| 429 | `UpstreamRateLimit` | `SERVER_ERROR` | 9 | `errors.py:92-98`、`retry.py:48-49` |
| 401 | `UpstreamError(401)` | `GITHUB_TOKEN_EXPIRED` | **0**（默认不重试） | `errors.py:40`、`retry.py:54-55`、`schema.py:166-168` |
| 其他 4xx（400/403/404/422…） | `UpstreamRejected` | —（`classify` → ABORT） | 不重试 | `errors.py:99-105`、`exceptions.py:60-83` |
| **响应头之后的读流中断** | 不经过 driver | — | **无重试** | 见 §1.5 |

共享总预算 `max_total` 默认 20（`src/app/config/schema.py:184`）。`RetryLedger.consider`（`retry.py:91-98`）先查总预算再查单项。

### 1.4 有没有指数退避？

**没有指数退避，也没有 jitter。**

证伪依据：`rg 'backoff|asyncio.sleep|anyio.sleep|exponential|jitter' src/` 全量输出中，与请求重试路径相关的只有一处 —— `src/app/pipeline/rate_limiting.py:130-138` `RateLimiter.acquire()`。`direct_driver/base.py:146` 的 `continue` 之前没有任何 sleep。

现存的唯一等待是**常量间隔**，且只对 429/502 生效：

- `src/app/pipeline/rate_limiting.py:23` `REACTIVE_STATUSES = frozenset({429, 502})`；503/504 明确排除（`rate_limiting.py:166-168`）。
- `rate_limiting.py:157-175` `observe_failure`：命中后进入 LIMITED，`_next_allowed = now + (Retry-After 或 retry_interval=10s)`。
- `direct_driver/base.py:139-140` 下一次尝试前 `await self._rate_limiter.acquire()` 会等到那个时刻。
- 恢复：`recovery_interval=600s` 后进 RECOVERING，连续 `consecutive_successes=5` 次成功回 NORMAL（`schema.py:250-256`、`rate_limiting.py:140-155`）。

**所以：500/503/504 和网络错误当前是“无间隔连打 9 次”**（NORMAL 模式下 `_spacing()` 返回 `_proactive_interval`，而它只在成功响应带限额头时才非零，见 `rate_limiting.py:125-128`、`rate_limiting.py:147-150`）。这是我认为最值得关注的一条现状。

### 1.5 读流中断：明确“没有重试”

我读完的 except 分支，逐条列出证伪依据：

1. `src/app/server/pipeline_app.py:499-519`：流式响应的 body 由 `response.aiter_bytes()` 经 `with_idle_timeout` → `with_deadline_at` → `_counted_upstream` → `stream_delivery` 组成。这条链**不在** `DirectDriver.run` 的作用域内（`handler.py:154` `outcome = await driver.run(context)` 已经返回）。
2. `src/app/server/pipeline_app.py:642-663` `_tracked_delivery`：唯一的 `except Exception` 分支（`:657-661`）只做 `accounting.failure = error` 然后 `raise`。没有重试。
3. `src/app/server/pipeline_app.py:610-626` `_AccountedStreamingResponse.__call__`：`finally` 里只做 `aclose()` 与 `finish()`，异常原样传播（`:618-624`）。
4. `src/app/pipeline/delivery/stream.py:204-294` `_deliver`：没有 `except` 捕获上游异常。`:126-129` 只捕 `StopAsyncIteration`（正常结束）。
5. `src/app/streaming/idle_timeout.py` / `src/app/streaming/deadline.py`：两者的 `except TimeoutError` 只做重贴标签（`StreamIdleTimeoutError` / `StreamDeadlineError`）并 `raise`。

**结论：一旦上游响应头返回，后续读流中断、上游中途 RST、GOAWAY、idle 超时、attempt deadline 到期，全部没有任何重试。** 相关的重试判定代码是写了但没接线的，见 §6。

### 1.6 两个时间边界（不是重试，但决定失败何时发生）

- `upstream_request_deadline` 默认 **1200s**（`schema.py:153`），在两处执行同一个时刻：`direct_driver/base.py:130-132` 设定 `attempt.deadline_at`，`base.py:253-260` 守头，`pipeline_app.py:503-509` `with_deadline_at` 守 body。
- `client_request_deadline` 默认 **3600s**（`schema.py:261`），`handler.py:323-336` `handle_bounded` 包住整个 `handle`，超时抛 `UpstreamTimeout`。注意它只包 `handle`，**不包 body 流式交付**（`handle` 在响应头到达时就返回了）。
- `response_header` 与 `stream_idle` 默认都是 **0（关闭）**（`schema.py:151-152`），理由写在 `handler.py:524-529`：“永不误杀正常 thinking”。

---

## 2. 错误怎么变成给客户端的响应？

### 2.1 时机 (a)：还没向客户端写任何字节

两条出口，都在 `src/app/server/pipeline_app.py::_dispatch`：

- **抛出型**（`pipeline_app.py:441-453`）：`handle_bounded` 抛异常时。
- **返回型**（`pipeline_app.py:462-472`）：driver 把失败放在 `outcome.error` 里而不是抛出，`handled.response is None`。`pipeline_app.py:466` 的注释明确说 “The branch an upstream refusal actually takes”。

两条都产出 `JSONResponse(error_body(error), status_code=error_status(error), headers=error_headers(error))`。

- `error_status`：`src/app/server/handler.py:339-371`。`ProviderError|RoutingError|TranslatorNotFound|CountTokensRequestError|TranslationRefused` → 400；`CountTokensUnavailable` → 503；`UpstreamRateLimit` → 429；`UpstreamTimeout` → 504；`UpstreamRejected` → 上游原状态码；**其余 → 502**。
- `error_body`：`src/app/server/handler.py:385-403`。形状是 `{"error": {"type": <类名>, "message": str(error), ...}}`，可选带 `code` / `field_path` / `upstream`（分别用 `getattr` 读）。
- `error_headers`：`src/app/server/handler.py:374-382`。只放行 `Retry-After`，且**只在 `isinstance(error, UpstreamRateLimit)` 时**。

#### 一个我认为是缺陷的现状：可重试类失败在预算耗尽后被降级为 502

`src/app/pipeline/direct_driver/base.py:210-216`：

```python
if disposition is Disposition.RETRY:
    funded, detail = self._budget.take_for(error)
    if funded:
        return True
    outcome.error = PipelineAbort(f"{detail}: {error}")
```

`PipelineAbort` 不是 `UpstreamRateLimit`、不是 `UpstreamTimeout`、不是 `UpstreamRejected`，所以：

- `error_status(PipelineAbort)` 落到 `handler.py:371` 的 `return 502`；
- `error_headers(PipelineAbort)` 返回 `{}`，**`Retry-After` 丢失**；
- `error_body` 用 `getattr` 找 `code`/`field_path`/`body`，`PipelineAbort`（`exceptions.py:94-99`）三个都没有，**上游 body 作为独立字段丢失**（只有 `str(error)` 里嵌的 SDK 异常字符串可能残留部分内容）。

**这不是我的推断，测试里已经把它固定下来了**：`tests/int/test_pipeline_app.py:730-756` `test_upstream_429_is_seen_by_the_rate_limiter`，上游返回 429，`assert response.status_code == 502`。

注意 `tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py:129` 的 `assert error_status(limited) == 429` 是对函数的孤立单测，它不证明 live chain 会走到那个分支——`_handle_failure` 保证了可重试类失败到达 `error_status` 时已经是 `PipelineAbort`。`error_status` 的 429 分支和 `error_headers` 的 `Retry-After` 分支在当前 driver 路径上我没有找到可达路径。

【推测】唯一可能让 `UpstreamTimeout` 原样到达 `error_status` 的是 `handle_bounded`（`handler.py:335-336`）自己抛的那个客户端总超时，它不经过 `_handle_failure`，所以 504 那条是可达的。我没有为此写验证，标为推测。

不可重试类（`UpstreamRejected`）走 `base.py:217` `outcome.error = error`，**不包装**，所以上游状态码、`body` 都保留。这条是对的。

### 2.2 时机 (b)：已经交付过至少一个 Anthropic content block

**分两种结局，客户端看到的东西完全不同。**

先明确“已开流”在代码里的判据：`src/app/pipeline/delivery/stream.py:217` 的 `client_has_bytes: asyncio.Event`，在 `:247`（首个 block 提交）、`:261`（240s 合成 `message_start`）、`:270`（held-back 路径 flush）三处 set。

#### (b-1) 上游流“干净地”结束但没有终结事件 → 发 SSE `error` 事件

`src/app/pipeline/delivery/stream.py:279-288`：

```python
if not terminal.seen:
    yield error_frame(
        error_type=WIRE_TYPES[ErrorCategory.UPSTREAM],
        message="Responses stream ended before a successful terminal event",
        code="incomplete_responses_stream",
    ).encode()
    return
```

帧形状见 `src/app/pipeline/delivery/anthropic_sse.py:141-151`：`event: error` + `{"type":"error","error":{"type":...,"message":...,"code":"incomplete_responses_stream"}}`。

`stream.py:282` 的注释明确：**不再发 `message_stop`**（“不得再发 `message_stop` 冒充成功”）。所以客户端拿到的是 `…content_block_stop` → `error` → 连接结束，**没有 `message_delta`，没有 `message_stop`**。

这条只在 `client_has_bytes` 已 set 时执行；否则 `stream.py:276-278` 直接 `return`，客户端得到一个 **HTTP 200 + 空 body**（注释自己承认这是既有行为且未在该 slice 内解决）。

#### (b-2) 上游撕连接 / idle 超时 / deadline 到期 / 交付层自身抛错 → 什么都不发，连接直接断

异常从 `_deliver` 一路上抛（§1.5 已列 5 个 except 分支），沿途没有任何地方生成 SSE `error` 帧。最终到 Starlette `StreamingResponse`。

- `pipeline_app.py:657-661` 记录 `accounting.failure` 后 `raise`；
- `pipeline_app.py:590-591` `_ending()` 把它写进**服务端日志行**：`("fail", f"stream failed before a terminal event: {failure}")`。

**这是唯一一处保留该错误信息的地方，而它只写给运维，不写给客户端。** `pipeline_app.py:584` 的注释亲口说：“It is the only account of what went wrong that exists anywhere”。

【推测，基于 ASGI 语义而非本仓库代码】HTTP 响应头已经在首个 chunk 时发出（状态码固定为上游的 200，见 `pipeline_app.py:523`），此后不可更改；uvicorn 在 body 生成器抛异常时会中止连接，客户端侧表现为 **chunked body 提前截断 / 连接被重置**，没有 SSE `error` 事件，没有 `message_delta`。我没有做端到端抓包验证，因此标为推测；但“本项目代码不发任何错误帧”这半句是代码事实。

同一分类被 `pipeline_app.py:581-594` `_ending()` 明确记录为三种结局：`failure is not None` → fail、`drained` → fail、其余（客户端离开 / 关机取消）→ gone。

#### (b-3) buffer 超上限

`src/app/pipeline/delivery/blocks.py:120-125` `_enforce_cap` 抛 `BufferCapExceeded`（`blocks.py:23-33`，是 `DeliveryError` → `RuntimeError`），默认 cap 16 MiB（`schema.py:263`）。它从 `_deliver` 的 `_commit` 抛出，走的是 (b-2) 的路径——**连接直接断，客户端没有任何错误说明**。

---

## 3. 上游的错误信息保留到什么程度？

### 3.1 保留了什么

- **HTTP 状态码**：保留。`errors.py:62-77` `_response_parts` 从 SDK 异常读 `status_code`，存进 `UpstreamError.status_code` / `UpstreamRejected.status_code`（`exceptions.py:36`、`exceptions.py:81`）。
- **上游响应头**：保留在异常对象上（`exceptions.py:39`、`exceptions.py:82`），但**只有 `Retry-After` 会被转发给客户端**（`handler.py:374-382`），且如 §2.1 所述这条在 driver 路径上不可达。
- **上游 body 原文**：保留。`errors.py:74-76` 读 `response.text` 存入 `.body`；`handler.py:398-402` 以 `upstream` 字段放进错误体。**但只对 `UpstreamRejected` 生效**（可重试类被 `PipelineAbort` 吞掉，见 §2.1）。
- **原始 payload 取证**：`src/app/observability/rejection_capture.py:44` `capture_rejection`，在 `pipeline_app.py:448` 与 `:467` 两处调用，把上游拒绝时的请求体落盘。

### 3.2 没有保留什么

**上游 body 里的 `error.code` / `error.type` 在 live chain 上没有被解析。**

证伪依据：`rg 'error_code|get\("code"\)|error\.get' src/` 的全部命中里，与上游错误体解析相关的只有：

- `src/app/anthropic/client.py:436-444` —— legacy chain；
- `src/app/openai/responses_stream_parser.py:483-528` —— 只被 legacy `delivery/` 使用（`rg 'responses_stream_parser' src/` 无 pipeline/server 命中）；
- `src/app/pipeline/subscribers/server_tools.py:97` —— 读的是 web search 工具结果里的 `error_code`，不是上游 HTTP 错误；
- `src/app/tokenization/limits.py:23` —— 读的是 count_tokens 的限额错误。

`handler.py:385-403` `error_body` 里的 `code` 来自 `getattr(error, "code", "")`，读的是**我们自己异常对象上的属性**，而 `UpstreamError`/`UpstreamRejected`/`PipelineAbort` 都没有定义 `code`（`exceptions.py:24-99` 全文无 `self.code`）。所以这个字段在上游失败时恒为空。`field_path` 同理。

【推测】`code`/`field_path` 这两个字段应当是给 `TranslationRefused` 之类的本地拒绝用的。我没有逐一核对每个本地异常类，标为推测。

### 3.3 有没有“可重试 / 不可重试”的分类函数？

**有，两层，且是当前设计里最清晰的部分。**

1. **按状态码判定确定性**：`src/app/model_provider/ghc_client/errors.py:40`
   `RETRYABLE_STATUSES = frozenset({401, 408, 409, 425, 429, 500, 502, 503, 504})`。
   `errors.py:99-105`：4xx 且不在这个集合里 → `UpstreamRejected`（不可重试）。判据写在 `errors.py:15`：“A 400 naming a field upstream will not accept answers the same way nine times over; a 503 does not.”
2. **按异常类型判定处置**：`src/app/pipeline/exceptions.py:105-115` `classify()` → `Disposition.{CONTINUE,RETRY,ABORT}`，闭集之外一律 ABORT。
3. **按原因命名并计账**：`src/app/pipeline/retry.py:40-61` `reason_for()` → `RetryReason`。

---

## 4. `stop_reason` 的处理

### 4.1 live chain 的完整映射

全部在 `src/app/pipeline/delivery/assembler.py::ResponsesAssembler._read_terminal`（`:323-340`）：

| 上游事件 | 条件 | 产出 `stop_reason` | 行号 |
|---|---|---|---|
| `response.incomplete` | `incomplete_details.reason == "max_output_tokens"` | `max_tokens` | `assembler.py:336-338` |
| `response.incomplete` | **其他任何 reason** | `end_turn` | `assembler.py:336-338`（同一个三元表达式的 else） |
| `response.completed` | 本轮见过 `function_call` | `tool_use` | `assembler.py:340` |
| `response.completed` | 否则 | `end_turn` | `assembler.py:340` |
| 无终结事件 | — | `Terminal.stop_reason` 保持 `""`（`assembler.py:48`），交付层不发 `message_delta`，改发 error 帧 | `stream.py:279-288` |

最终上线：`src/app/pipeline/delivery/stream.py:290-294`，`stop_reason=terminal.stop_reason or "end_turn"`。

非流式（buffered）路径走 `src/app/pipeline/translation_driver/responses.py:114-127` `_responses_stop_reason`，同样只识别 `max_output_tokens`（`responses.py:125`）。

### 4.2 有没有专门识别 `model_context_window_exceeded`？

**没有。**

证伪依据：`rg 'model_context_window_exceeded|context_window' src/` 的全部命中只有 `src/app/debug/models.py:210` / `:294` / `:51` 和 `src/app/models/capabilities.py:29`，全部是**模型目录里的能力字段**（`max_context_window_tokens`），与上游结束原因无关。

后果（代码事实）：上下文超限如果由上游以 `response.incomplete` + 某个非 `max_output_tokens` 的 reason 表达，当前会被 `assembler.py:336-338` 的 else 分支**翻译成 `end_turn`**——即一个被截断的回答会向客户端报告为正常结束。如果上游改用 HTTP 4xx 表达，则走 §2.1 的 `UpstreamRejected` 路径，状态码和 body 会保留。

【推测】Copilot 的 Responses 上游到底用哪种形式表达上下文超限，我没有查证（需要 cassette 或实测）。**此项未查清**，不要据此下结论。

### 4.3 一处被丢掉的信息

`assembler.py:330-338` 读到了 `incomplete_details.reason` 这个字符串，但除了和 `"max_output_tokens"` 比一次之外**没有存到任何地方**——既不进 `Terminal`，也不进 `context.extras`，也不进日志行。所以“上游说它为什么没写完”这个事实在 live chain 上是丢失的。

对照：legacy chain 反而保留了它（`src/app/openai/responses_stream_parser.py:519-528` 把 `incomplete_details.reason` 存进 `error_code`，`src/app/delivery/responses_anthropic_stream.py:266` 与 `:275` 再读回来）。这是 live chain 相对 legacy 的一处能力回退。

---

## 5. 块级交付：交付单元与“已提交的块”的可查询状态

### 5.1 交付单元

`CompletedBlock`（`src/app/pipeline/delivery/blocks.py:40-50`）：`index` / `kind` / `payload`。一个完整的 Anthropic content block。

- 由 assembler 在**闭合事件**上产出，不在 delta 上：`assembler.py:231-232`（Responses 侧是 `response.output_item.done`）、`assembler.py:137-138`（Anthropic 侧是 `content_block_stop`）。
- 由 `BlockBuffer`（`blocks.py:53-125`）按 `buffering_policy` 决定何时释放：`block`（默认，`schema.py:262`）逐块放行、`full` 全部憋到结束、`until-tool-use` 憋到出现 `tool_use` 再逐块（`blocks.py:98-108`）。
- 由 `block_frames`（`src/app/pipeline/delivery/anthropic_sse.py:85-138`）渲染成 start/delta/stop 三帧一组。

### 5.2 “已提交给客户端的块”有没有可查询状态？

**有一个记录，但它记的不是“已交付”，而是“已装配完成”。这两者在默认配置下重合，在 `full` / `until-tool-use` 下不重合。**

存在两个不同的账本：

**(A) `DeliverySession.delivered`** —— 这个才是真正的“已交付”，但**外部拿不到**。

- `src/app/pipeline/delivery/blocks.py:128-156`：`delivered: list[CompletedBlock]`，只在 `_commit`（`:151-156`）中 buffer 真正放行时 `extend`；另有 `committed_count` property（`:140-142`）。
- 但 `DeliverySession` 是在 `src/app/pipeline/delivery/stream.py:215` **函数内的局部变量**，`_deliver` 是一个 async generator，没有任何出口把它交出去。
- 证伪：`rg 'committed_count' src/` 只有定义处 `blocks.py:141` 一行，**无任何读取者**。`rg '\.delivered' src/` 同理只有 `blocks.py:155` 的写入。

**(B) `Terminal`（assembler 上的聚合记录）** —— 外部拿得到，但语义是“已装配”。

- `src/app/pipeline/delivery/assembler.py:43-70`：`blocks: int`、`tools: list[str]`、`thinking: list[str]`，由 `Terminal.record()`（`:61-70`）填充。
- `record()` 的调用点是 `assembler.py:187`（Anthropic `_close`）和 `assembler.py:320`（Responses `_close`）——**block 完成装配的那一刻，而不是被 buffer 放行的那一刻**。
- 可达性：assembler 在 `src/app/server/pipeline_app.py:485` 创建，同时传给 `stream_delivery`（`:514`）和 `_StreamAccounting`（`:494`）。出错时 `_StreamAccounting.finish()`（`:559-579`）读 `self.assembler.terminal`（`:566`）并 `self.trace.absorb(terminal)`（`:568`）。

### 5.3 直接回答“出错时能不能判断已交付的块里有没有工具调用”

- **有现成的东西可读**：`assembler.terminal.tools`（`assembler.py:57`），非空即表示本轮出现过 `tool_use`；`terminal.blocks` 是计数。出错路径上已经在读了（`pipeline_app.py:566-568`）。
- **但它回答的是“上游产出过哪些工具调用”，不是“客户端已经收到哪些工具调用”。** 在默认 `buffering_policy: "block"` 下两者一致；在 `full` 或 `until-tool-use` 下，assembler 可能已经记录了 3 个 tool_use 而 buffer 一个都没放行，此时 `terminal.tools` 会**高估**客户端已见到的内容。
- 真正的“已交付”账本 `DeliverySession.delivered` 目前**无法从 `_deliver` 之外访问**。如果要在出错时做“已交付的块里有没有工具调用”的判断，需要先把这个状态暴露出去（当前不存在这样的通路）。
- 旁证：`pipeline_app.py:569-571` 自己也承认这类边界没理清——`terminal.seen` 为真才写 `context.reply`，注释说这是“conservatively rather than undecidedly”，并登记在 `implementation.md` 的“结构怪味登记”里待重议。

---

## 6. 已存在但没接线的、与重试相关的代码

按“离接线有多近”排序。

### 6.1 `decide_stream_ending` —— 中途失败后的 replay / continuation 判定（**完全未接线**）

`src/app/pipeline/retry.py:139-178`。这是整份调查里最值得注意的一块：它正是 §1.5 里“开流之后没有任何重试”所缺的那段逻辑，写完了、有详尽 docstring（`:146-157`）、有测试（`tests/unit/pipeline/test_stream_ending.py` 全文），**但 `src/` 下没有任何调用者**。

证伪依据：`rg 'decide_stream_ending' src/ tests/` 的全部命中为 `src/app/pipeline/retry.py:139`（定义）与 `tests/unit/pipeline/test_stream_ending.py:14,29`（测试）。零生产调用点。

连带未接线的还有：

- `StreamEnding`（`retry.py:123-129`，四态：COMPLETE / REPLAY / CONTINUE / ABANDON）；
- `EndingVerdict`（`retry.py:132-136`）；
- `continuation_messages`（`retry.py:108-120`）—— `rg` 全量结果里只有 `tests/unit/pipeline/test_retry_strategies.py:102,110`；
- `RetryReason.STREAM_REPLAY` / `RetryReason.CONTINUATION` 两个枚举值：`RetryLedger.limit_for` 能返回它们的额度（`retry.py:82-86`），但由于 `LedgerBudget.take_for` 只从 `reason_for()` 取原因（`base.py:68`），而 `reason_for` 只在 `isinstance(error, PipelineRetry)` 时返回 `STREAM_REPLAY`（`retry.py:44-45`）、**永不返回 `CONTINUATION`**，所以 `strategies.continuation`（默认 enabled、10 次，`schema.py:158-161`）和 `strategies.streamReplay`（默认 100 次，`schema.py:175-177`）这两项配置在当前 live chain 上**完全无效**。

### 6.2 `RetryBudget` —— 简易共享计数器（生产无调用点）

`src/app/pipeline/direct_driver/base.py:44-58`，从 `direct_driver/__init__.py:22,71` 导出。`src/` 下唯一的 Budget 实例化是 `handler.py:149` 的 `LedgerBudget`。`RetryBudget` 只出现在三个测试文件里（`tests/unit/pipeline/test_timeout_enforcement.py`、`test_direct_driver.py`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py`）。docstring 自称 “kept for callers that have no named strategies configured”，但没有这样的 caller。

### 6.3 `src/app/streaming/buffered_retry.py` —— 完全孤儿

18 行，`collect_with_limit` + `BufferLimitExceeded`。`rg` 全量：只有 `tests/unit/streaming/test_streaming_resilience.py:8,502,507,508`。名字直指“为重试而缓冲整个流”，但没有任何生产引用。

### 6.4 `src/app/streaming/delayed_commit.py` —— 完全孤儿

13 行，`delayed_first_item`。`rg` 全量：只有 `tests/unit/streaming/test_streaming_resilience.py:9,491`。

### 6.5 配置项写了但没人读

- `upstream_request_retry.max_tokens_as_retryable`（`src/app/config/schema.py:186`，默认 `True`）。`rg 'max_tokens_as_retryable' src/ tests/` 只有这一行。**无任何读取者。**
- `client_delivery.hedge`（`HedgeConfig`，`schema.py:213-215`，挂在 `schema.py:266`）。`rg 'hedge' src/ tests/` 只有这两行。**无任何读取者。** 对冲请求这个能力完全不存在。

### 6.6 整条 legacy 重试链（存在、可运行、但进程不走）

- `src/app/pipeline/strategies/__init__.py:29-63` `RetryCoordinator` + `:84` `PoisonedThinkingStrategy`；
- `src/app/hooks/builtin/retry.py:12-23` `PoisonedThinkingRetryFactory`；
- `src/app/pipeline/executor.py:244-252` 是它们唯一的生产调用点，而 executor 只被 `anthropic/client.py:357` 调用，后者只服务 `routes/anthropic.py`（§0）。

**这一块和 §6.1 的区别要分清**：§6.1 是“新链路缺的功能，代码写好了没接”；§6.6 是“旧链路有的功能，随旧链路一起停用了”。**thinking 中毒后剥离重试这个能力，在当前 live chain 上是不存在的。**

---

## 附：live chain 上一次请求失败的完整路径速查

```
POST /v1/messages
  → pipeline_app._serve            (:291)   注册 in-flight
  → pipeline_app._dispatch         (:349)   解析 body / build_context
  → handler.handle_bounded         (:323)   client_request_deadline 3600s
  → handler.handle                 (:125)   路由 + 翻译
  → DirectDriver.run               (base.py:126)  ←← 唯一的重试循环在这里
       _send                       (base.py:221)  await 到「响应头到达」为止
       _handle_failure             (base.py:197)  classify → budget → continue / PipelineAbort
  ── 响应头到达，driver 退出，此后无重试 ──────────────
  → pipeline_app._dispatch :479-525  组装 body 守卫链
       with_idle_timeout  (默认关闭) → with_deadline_at (1200s) → _counted_upstream
  → stream_delivery                (stream.py:168)
       _deliver                    (stream.py:204)
          assembler.push → BlockBuffer → block_frames → yield
          结尾：terminal.seen ? terminal_frames : error_frame   (stream.py:279-294)
  → _tracked_delivery              (pipeline_app.py:642)  记 failure，原样上抛
  → _AccountedStreamingResponse    (pipeline_app.py:597)  finally 里 aclose + finish
```

---

## 已查清 / 未查清清单

**已查清（代码事实，可直接引用）**

- live chain 与 legacy chain 的分叉及其证据（§0）
- 响应头之前有分原因计账的重试；无指数退避；429/502 有常量间隔（§1）
- 响应头之后无任何重试，5 个 except 分支已逐条核对（§1.5）
- 可重试类失败预算耗尽后降级为 502 并丢 `Retry-After`（§2.1，有 int 测试佐证）
- 开流后两种结局：clean EOF 发 SSE `error`；撕流则静默截断（§2.2）
- 上游 `error.code`/`error.type` 在 live chain 上未被解析（§3.2）
- `stop_reason` 只识别 `max_output_tokens`，无 `model_context_window_exceeded`（§4）
- `DeliverySession.delivered` 无外部读取通路；`Terminal.tools` 记的是「已装配」（§5）
- 6 组未接线代码及配置（§6）

**未查清（不要据此下结论）**

- Copilot 的 Responses 上游用什么形式表达上下文超限（HTTP 4xx？`response.incomplete` + 哪个 reason？）。需要 cassette 或实测。
- 客户端在 (b-2) 静默截断时的实际观感（chunked 提前结束 vs RST）。我只证明了本项目不发错误帧，未做端到端抓包。
- `error_body` 的 `code` / `field_path` 字段原本为哪些本地异常设计。未逐一核对本地异常类。
