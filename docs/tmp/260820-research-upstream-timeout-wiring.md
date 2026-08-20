# upstream_request_timeouts 接线调查：`await send` 到底等到哪一刻

- 日期：2026-08-20
- 调查者：subagent（只读；未改 `src/`、`tests/`，未做任何 git 写操作）
- 探针脚本：`/tmp/rev-timeouts/probe.py`、`/tmp/rev-timeouts/probe2.py`（真实本地 asyncio HTTP 服务器 + 生产同款 SDK 调用；用 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python` 跑）
- 依赖版本：openai 2.21.0 / anthropic 0.79.0 / httpx 0.28.1（`.venv/bin/python -c "import openai,anthropic,httpx;..."`）

---

## 结论前置

| # | 问题 | 结论 | 证据强度 |
|---|---|---|---|
| 1 | `await provider.send(...)` 等到哪一刻 | **`stream=True` 收到响应头就返回；`stream=False` 等到响应体读完才返回** | 实测，强，可直接据此决策 |
| 2 | `asyncio.timeout(attempt_deadline)` 实际约束哪一段 | **流式下只约束到响应头 —— 它当前的行为就是 `response_header`，而不是「整次尝试存活上限」**；非流式下确实约束整次尝试 | 实测，强 |
| 3 | `response_header` 该接在哪 | **推荐 `asyncio.timeout` 包住 `send`（复用 `base.py:_send` 现有形状）**。httpx `Timeout(read=N)` 是「两次 read 之间的间隔」而非「从发起到收到头的总时长」，语义对不上用户注释 | 实测，强（probe2 反证了 httpx read 的语义） |
| 4 | `upstream_request_deadline` 怎么接才是「整次尝试存活」 | 流式必须在 driver 返回**之后**的交付链上再加一段绝对期限守卫；**它一旦击发无法重试**，这是语义代价，无法用「把守卫写得更好」消除 | 读码推断 + 结构实测，强 |
| 5 | 与 SDK 隐式 600s 的关系 | 隐式 600s **一直在**，而且它是一个**藏在体读取阶段的 `stream_idle=600`**；配 `stream_idle` 不会关掉它，配 `response_header` 时如果用 per-request `timeout` 会把它**整体替换掉**（连体读取阶段一起换） | 实测，强 |
| 6 | 重试语义 | driver 内超时 → `UpstreamTimeout` → `classify=RETRY` → `RetryReason.NETWORK`（`network.max_retries: 9`）→ **会重试**；driver 外的 `stream_idle` / 体阶段超时 → **不可能重试** | 实测（Q3a 走完了 normalize+classify）+ 读码，强 |

一句话：**现在这套接线在流式路径上把三个守卫压成了一个，而那一个的语义是 `response_header`、取的值却是 `upstream_request_deadline`。**

---

## 一、`await provider.send(...)` 等到哪一刻返回

链路：`base.py:226 self._provider.send(...)` → `github_copilot.py:154 send_anthropic_messages` → `client.py:138 _in_pipeline_terms(_post_anthropic(...))` → `client.py:91 self._anthropic.post(..., cast_to=httpx.Response, stream=stream)`。

探针复刻了这一整条调用形状（同样的 `cast_to=httpx.Response`、`options={"headers": ...}`、`max_retries=0`，httpx client 同样不传 `timeout=`，与 `src/app/server/composition.py:79 build_http_client` 一致）。

### 实测输出（`/tmp/rev-timeouts/probe.py`，Q1a / Q1b）

```
=== Q1a stream=True: headers at +1.0s, first body at +3.0s, 3 chunks 0.5s apart ===
[  0.064s] client: about to await send(stream=True)
[  1.084s] server: HEADERS SENT
[  1.086s] client: AWAIT RETURNED status=200 is_closed=False     <-- 头一到就返回
[  3.092s] server: body chunk 0 sent
[  3.093s] client: got body block 1
[  4.099s] server: BODY COMPLETE
[  4.100s] client: body iteration finished

=== Q1b stream=False: same server timing ===
[  4.108s] client: about to await send(stream=False)
[  5.116s] server: HEADERS SENT
[  8.129s] server: BODY COMPLETE
[  8.131s] client: AWAIT RETURNED status=200 bytes=45             <-- 体读完才返回
```

**结论（实测，强）**：

- `stream=True`：`await send` 在**响应头到达的那一刻**返回（1.084s 发头 → 1.086s 返回，2ms）。响应体还没开始发（+3.09s 才有第一块），`is_closed=False`。
- `stream=False`：`await send` 在**响应体读完之后**返回（8.129s 体完 → 8.131s 返回）。

这条事实决定了后面所有结论。

---

## 二、`asyncio.timeout(self._attempt_deadline)` 实际约束哪一段

代码：`src/app/pipeline/direct_driver/base.py:233-241`。它的 docstring 写着「The deadline bounds the whole attempt rather than a phase of it, which is what catches an upstream that trickles forever without ever finishing」——**这句话在流式路径上是错的**。

### 实测输出（Q2a / Q2b）

```
=== Q2a stream=True, asyncio.timeout(2.0), headers at +0.5s, body trickles past the deadline ===
[  8.145s] client: asyncio.timeout(2.0) around send(stream=True)
[  8.652s] server: HEADERS SENT
[  8.653s] client: AWAIT RETURNED status=200 (deadline did NOT fire)
[  9.155s] client: body block (outside the deadline scope)
[ 10.661s] client: body block (outside the deadline scope)
[ 12.169s] client: body block (outside the deadline scope)
[ 13.677s] client: body block (outside the deadline scope)   <-- 超出 deadline 5.5 秒，守卫全程没响

=== Q2b stream=False, asyncio.timeout(2.0), same server ===
[ 13.686s] client: asyncio.timeout(2.0) around send(stream=False)
[ 14.192s] server: HEADERS SENT
[ 15.690s] client: DEADLINE FIRED -> TimeoutError:              <-- 恰好 2.004s
```

**结论（实测，强）——支持了任务描述里的那个猜想**：

- **流式**：`attempt_deadline` 只约束「从发起到收到响应头」。它现在的**行为**与用户注释里的 `response_header`（「从请求发起到开始收到 HTTP 响应头的最大秒数」）**逐字一致**，只是取了 `upstream_request_deadline: 1200` 的值。「一直滴水但永不结束」正是它拦不住的那一类——而用户的注释恰恰把这一类指派给了 `upstream_request_deadline`。
- **非流式**：`attempt_deadline` 确实约束整次尝试（含体读取），且击发后能走重试。这一半是对的，不要一起改掉。

顺带一条同形缺陷（读码，强）：`handler.py:232-245 handle_bounded` 用 `asyncio.timeout(client_request_deadline)`（默认 3600）包住 `handle`，而 `handle` 内部就是 driver。所以 `client_request_deadline` 在流式下**同样只覆盖到响应头**。这不在本次任务范围内，但它和 `upstream_request_deadline` 是同一个病因，修一个的时候值得顺手判断另一个要不要一起处理，**不要默默改掉**——它是 `client_delivery` 下的用户亲笔键（`config.example.yaml:380`）。

---

## 三、`response_header` 该接在哪

### 先确认「零命中」

```
$ rg -n '\.response_header\b' src/ tests/
tests/unit/test_config_schema.py:37:    assert config.upstream_request_timeouts.response_header == 0
```

`src/` 下**一次读取都没有**。schema 声明在 `src/app/config/schema.py:136`，legacy settings 声明在 `src/app/config/settings.py:71`，两处都无消费者。**实测（命令输出），强。**

### 关于 `response_header_overrides` 的现状更正

任务描述说 `handler.py:114-119` 仍把 `response_header_overrides` 当 `upstream_request_deadline` 的覆盖表。**这一处在当前工作树里已经被并行会话改掉了**（未提交）：

```
$ git diff -- src/app/server/handler.py
-    attempt_deadline = resolve_timeout(
-        route.model_id,
-        timeouts.upstream_request_deadline,
-        timeouts.response_header_overrides,
-    )
+    attempt_deadline = timeouts.upstream_request_deadline
```

同一份 diff 里 `stream_idle_seconds(chain, model)` 也被收成了 `stream_idle_seconds(chain)`（`handler.py:425`），不再读 `stream_idle_overrides`。所以**新链路对两张 overrides 表现在都是零读取**；`schema.py:137,140` 的两个字段成了只声明不消费。`src/app/config/settings.py:68,72` 与 `src/app/streaming/idle_timeout.py:12 resolve_stream_idle` 仍在用，但那是 legacy 链路（`src/app/routes/anthropic.py:217`）。**这属于并行会话的活动区，我未触碰，也建议本次任务不要顺手删 schema 字段——先与对方对齐。**

### 候选接入点及取舍

先给一条决定性的实测事实，它直接淘汰了一个看起来最自然的候选。

**httpx 的 `read` 超时是「两次 read 之间的间隔」，不是「从发起到收到头的总时长」。**

`/tmp/rev-timeouts/probe2.py`：read 超时 1.0s，服务器把响应头拆成 6 段、每 0.7s 发一段，总共 4.2s 才发完头。

```
[  0.234s] client: send with per-request timeout read=1.0s
[  0.968s] server: wrote b'HTTP/1.1 200 OK\r\n'
[  1.670s] server: wrote b'Content-Type: text/event-stream\r\n'
[  2.372s] server: wrote b'X-Filler-1: a\r\n'
[  3.076s] server: wrote b'X-Filler-2: b\r\n'
[  3.780s] server: wrote b'Transfer-Encoding: chunked\r\n'
[  4.484s] server: wrote b'\r\n'
[  4.486s] client: AWAIT RETURNED status=200 (read timeout never fired)
```

1.0s 的 read 超时放过了 4.49s 的等头时间。**实测，强。**

| 候选 | 覆盖连接建立 | 影响体读取阶段 | 可按请求变化（热重载） | 异常类型 | `classify()` 判定 |
|---|---|---|---|---|---|
| **A. `asyncio.timeout(N)` 包住 `send`（流式）** | 是（整个 await 都在内） | **否**（流式下 await 在收头时就返回，见第一节） | **是**，值每次从 `chain.config` 读，构造 driver 时传入，与现有 `attempt_deadline` 同路 | `TimeoutError` → 现有代码转成 `UpstreamTimeout` | RETRY |
| B. SDK per-request `options={"timeout": httpx.Timeout(N, connect=...)}` | 由 `connect` 单独管，`read` 不管 | **是，且会一起改掉**（见下） | 是，逐请求可变 | `anthropic/openai.APITimeoutError` | RETRY（`normalize_upstream_error` → `UpstreamTimeout`） |
| C. SDK client 级 `AsyncAnthropic(timeout=...)` | 同上 | 是 | **否**，构造期固定，热重载要重建 client | 同 B | 同 B |
| D. httpx client 级 `Timeout(read=N)`（`build_http_client`） | 由 `connect` 管 | 是 | 否 | `httpx.ReadTimeout` | 需经 `normalize_upstream_error` 才是 `UpstreamError`；driver 内会走到，RETRY |

B/C/D 三者都共享同一个语义缺陷：**它们量的是 read 间隔，不是等头总时长**（probe2）。对「上游想了 5 分钟一个字节没发」这种现实场景，两者数值上重合；但对 HTTP/2 连接（`upstream_transport.http2`）它们**不重合**——连接级的帧仍可能重置 read 计时（这一条是**读码推断，弱，仅作风险提示，未实测**）。

B 还有一条实测出来的副作用：per-request `timeout` 会把请求的 timeout 扩展**整体替换**，包括体读取阶段。

```
=== Q3b per-request timeout=1.0s, headers immediate, body gap 2.0s ===
[ 20.756s] client: AWAIT RETURNED status=200
[ 20.857s] client: body block
[ 21.861s] client: BODY RAISED httpx.ReadTimeout:                 <-- 体阶段也被这个值管住了
```

也就是说，用 B 接 `response_header=30`，等于同时把体读取阶段的隐式空闲上限从 600s 压到 30s——**装了一个用户没要的第二个 `stream_idle`，而且它和 `with_idle_timeout` 会打架**（谁先响谁说了算，两个值来自不同的配置键）。这条足以否掉 B/C/D 作为 `response_header` 的载体。

**推荐 A。** 具体形状：`base.py:_send` 现在只有一层 `asyncio.timeout(self._attempt_deadline)`；改成两层——外层仍是 `attempt_deadline`（保留非流式的正确行为），内层是 `response_header`；或者在流式分支上只用 `response_header`。异常都落在同一个 `except TimeoutError` 上，只是消息文本要能区分是哪一个击发的（否则日志上两种失败同形）。

A 的一个已知取舍（读码，中等）：`asyncio.timeout` 量的是 wall clock，包含了 `_publish(EVENT_ATTEMPT_PREPARE)` 之后、`rate_limiter.acquire()` 之外的一切——但 `acquire()` 在 `_send` 之外（`base.py:135`），所以限流等待不会计入，这是对的。

---

## 四、`upstream_request_deadline` 要真正约束「整次尝试存活」怎么接

### 先确认「driver 返回后无法重试」

- `handler.py:128 outcome = await driver.run(context)` → 返回 `HandledRequest`。
- `pipeline_app.py:302 handled = await handle_bounded(...)`，随后 `pipeline_app.py:352-376` 才把 `response.aiter_bytes()` 包进 `with_idle_timeout` → `_counted_upstream` → `stream_delivery` → `_tracked_delivery` → `_AccountedStreamingResponse` 返回给 starlette。
- 体的消费发生在 starlette 迭代这个生成器的时候，**`driver.run` 早已返回，`DirectDriver.run` 的 `while True` 循环栈帧已经销毁**。

**确认：driver 返回后发生的超时无法触发重试。**（读码，强；结构上没有任何一条路径能回到 `run` 的循环。）

对语义的影响，必须写进配置注释或文档，否则这是个会被误解的守卫：

1. `upstream_request_deadline` 在**非流式**下是「整次尝试存活上限 + 可重试」（Q2b 实测已证）。
2. 在**流式**下，一旦响应头已经发出，它就只能是「终止这条流」，不能是「换一次尝试」。而且此时客户端**已经收到 200 和若干 SSE 块**，只能以流中断的方式收场——这与 `stream_idle` 击发时的处境完全相同。
3. 因此同一个键在两种模式下的可观测行为不同。这不是实现偷懒，是「块级交付一旦开始就不可撤回」的结构性后果。

### 可行形状与代价

**形状 1（推荐）：绝对期限包住字节迭代器，与 `with_idle_timeout` 并列。**

- 在 `Attempt` 上加一个开始时刻（`request.py:40 class Attempt` 现在没有任何时间字段），或者在 `RequestContext.extras` 里放一个 `attempt_started_monotonic`。
- 在 `pipeline_app.py:357` 那一层再包一个 `with_absolute_deadline(stream, deadline_at)`，形状照抄 `src/app/streaming/idle_timeout.py`（同样用 `anyio.fail_after`、同样在 `finally` 里 `aclose()`）。
- 代价：`upstream_request_deadline` 变成两处执行（driver 内一处管非流式与等头、交付链一处管体），必须保证两处读的是同一个值、算的是同一个起点。这是「一个事实两条路径各推导一遍」的典型风险，建议起点只在 `Attempt` 上记一次、两处都读它。
- 收益：语义与用户注释完全对上，且**不需要动 driver 的重试语义**。

**形状 2：把交付搬进 driver。** 让 driver 持有到流结束。理论上能在「第一个块交付给客户端之前」的窗口内重试。代价极大（driver 要知道块级交付、`_StreamAccounting`、footer 注册），且窗口很窄（块级交付下第一个块往往就是第一个可交付单元）。**不推荐**，但值得记一笔：它是唯一能让流式重试窗口变大的形状，属于「记下来、别默默砍掉」的候选。

**形状 3：只在 driver 内保留，接受流式下它等价于 `response_header`。** 即现状。代价是用户注释里那句「两者都拦不住一直滴水但永不结束的尝试」在流式下依然无人执行——而流式正是主产品路径。**这条不满足需求，列出仅为对照。**

---

## 五、三个守卫与 SDK 隐式 600s 的关系

### 实测：当前生效值

```
=== Q5 effective default timeout with the production client shape ===
[ 27.902s] httpx client default timeout = Timeout(timeout=5.0)
[ 27.902s] SDK effective timeout        = Timeout(connect=5.0, read=600, write=600, pool=600)
[ 27.902s] anthropic DEFAULT_TIMEOUT    = Timeout(connect=5.0, read=600, write=600, pool=600)
[ 27.902s] openai    DEFAULT_TIMEOUT    = Timeout(connect=5.0, read=600, write=600, pool=600)
[ 27.908s] request extensions timeout   = {'connect': 5.0, 'read': 600, 'write': 600, 'pool': 600}
```

机制（读码，强，与实测一致）：`build_http_client`（`composition.py:79`）不传 `timeout=`，httpx 因此是 `Timeout(5.0)`；SDK 在 `_base_client.py:1464-1467` 判断 `http_client.timeout != HTTPX_DEFAULT_TIMEOUT` 为假，于是采用自己的 `DEFAULT_TIMEOUT`（`openai/_constants.py:9`）。请求发出时 SDK 用 `_base_client.py:572` 把这个 timeout 写进 request extension，**覆盖 httpx client 上的设置**。

### 结论

1. **隐式 600s 现在就在，且它在体读取阶段是活的。** Q3b 证明了体阶段的 read 超时会击发（那次是 1.0s）；Q5 证明默认值是 600。所以**即使 `stream_idle: 0`（用户的 bundled default，语义是「不超时」），实际仍存在一个 600s 的上游空闲上限**，由 httpx 在 `aiter_bytes()` 里执行。这与用户冻结的不变量「绝不误杀合法长思考」有出入——600s 是够长，但它是一个**没被任何配置键命名的终止器**。这一条我判断是**值得单独报给用户裁决的发现**，不是本次接线任务能顺手决定的。
2. **它会不会先于我们的守卫击发？** 取决于数值。`response_header` 若用形状 A（`asyncio.timeout`），两者独立并行：谁的秒数小谁先响。`response_header` 默认 0（禁用）时，600s 的隐式守卫就是唯一的等头上限——**这就是今天的真实行为**：等头阶段没有 `response_header`，但有一个 600s 的 read 间隔守卫。
3. **会不会打架？** 用形状 A 不会——`asyncio.timeout` 抛 `TimeoutError`、httpx 抛 `ReadTimeout`，都在 driver 内、都归一到 `UpstreamTimeout`/`UpstreamError`，都可重试。用 B/C/D 会打架（第三节 Q3b 已说明）。
4. **一个副作用值得注意**：`normalize_upstream_error` 只在 `GhcApiClient._in_pipeline_terms`（`client.py:100-113`）里跑，而它只包住 `await post`。体读取阶段抛出的 `httpx.ReadTimeout` **不经过它**，会以原始 httpx 异常的形态出现在交付链上。Q3b 里那次 `normalize_upstream_error -> UpstreamError` 是我在探针里手动调的，**不是生产行为**。

---

## 六、重试语义

### `response_header` 超时（driver 内）

实测（Q3a，走的是真的 `normalize_upstream_error` + 真的 `classify`）：

```
=== Q3a per-request timeout=1.0s, headers delayed 3.0s ===
[ 18.729s] client: RAISED anthropic.APITimeoutError: Request timed out or interrupted. ...
[ 18.729s]         normalize_upstream_error -> UpstreamTimeout: upstream timed out: ...
[ 18.729s]         classify -> retry
```

这是候选 B 的路径。候选 A（推荐）的路径更短，全是读码但确定性同样高：`asyncio.timeout` → `TimeoutError` → `base.py:238-241` 直接 `raise UpstreamTimeout(...)` → `base.py:204 classify(error)`。

两条路都落到：

- `classify()`（`exceptions.py:105-115`）：`UpstreamTimeout` 是 `UpstreamError` 子类（`exceptions.py:43`），`UpstreamError` 在 `_RETRYABLE` 里 → **`Disposition.RETRY`**。
- `reason_for()`（`retry.py:46-47`）：`UpstreamTimeout` → **`RetryReason.NETWORK`**。
- 预算：`upstream_request_retry.strategies.network.max_retries: 9`（`config.example.yaml:329-330`），总额 `max_total: 20`。

**所以 `response_header` 超时会被重试，最多 9 次（受总额 20 约束）。**（实测 + 读码，强。）

这里有一条值得用户知道的后果：`response_header` 设成一个偏小的值，配合 `network.max_retries: 9`，意味着一次「上游想得久」的请求会变成**最多 10 次发往上游的完整请求**。用户注释里说「运维可显式配置非零值以选择有界等待」——但没说这个有界等待会被重试放大。**这一条建议在接线时同步写进 `config.example.yaml` 的注释，或至少报给用户。**（判断，中等强度：机制是确定的，是否要改注释是用户的决定。）

### `stream_idle` 超时（driver 外）对比

- 抛 `StreamIdleTimeoutError`（`idle_timeout.py:8`，是 `TimeoutError` 子类，**不是** `PipelineError`）。
- 它在 `pipeline_app.py:357` 的交付链里抛出，`classify()` **根本不会被调用**——那条路径上没有 driver。
- 结果：流中断，`_StreamAccounting.failure` 记下它（`pipeline_app.py:406`），客户端拿到一条断掉的 SSE 流。**不重试，也无从重试。**
- 假如它真的被 `classify()` 看到，会判成 `Disposition.ABORT`（不在 `_RETRYABLE` 里，也不是 `PipelineAbort`）。这只是个理论对照，说明即使把它挪进 driver 也需要先归一化成 `UpstreamTimeout`。

**对比总结**：driver 内的超时是「换一次尝试」，driver 外的超时是「掐断这一条流」。`upstream_request_deadline` 按第四节形状 1 接线后，会**同时具备这两种身份**（等头阶段可重试，体阶段不可重试）。这个双重身份必须写进注释，否则它是一个会被误读的键。

---

## 附：本次调查未处理但发现的事项（供主会话裁决，均未擅自处理）

1. `client_request_deadline`（默认 3600，`config.example.yaml:380`）在流式下同样只覆盖到响应头 —— 与本次缺陷同因（第二节末）。
2. SDK 隐式 600s 是一个未被任何配置键命名的上游空闲终止器，与「绝不误杀合法长思考」的冻结不变量存在张力（第五节结论 1）。
3. `schema.py:137,140` 的 `response_header_overrides` / `stream_idle_overrides` 在新链路上已零读取（并行会话刚改的，未提交），但字段仍在，legacy 链路仍在读 `settings.py` 里的同名字段。删不删、何时删，需与并行会话对齐。
4. `response_header` 非零 + `network.max_retries: 9` 会把「有界等待」放大成最多 10 次上游请求，注释未提（第六节）。
