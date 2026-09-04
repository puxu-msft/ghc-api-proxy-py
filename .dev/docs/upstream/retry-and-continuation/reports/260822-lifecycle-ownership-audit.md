# 生命周期归属审计：`client_request_deadline` / `upstream_request_deadline` / 双侧终止关联

日期：2026-08-22
审计对象 HEAD：`96eb2fa`（`feat: let delivery replace a torn attempt the client never saw`）
审计范围：进程实际服务的链路 `create_pipeline_app`（`src/app/cli.py:151,176`）。**未读、未据以下结论的**：`src/app/delivery/`、`src/app/pipeline/executor.py`、`src/app/hooks/`（未挂载的 legacy 链路）。
性质：只读审计。除本报告外未修改任何仓库文件；探针脚本写在 `/tmp/`，未提交。

## 证据等级约定

- `代码事实` —— 直接读到的源码，带 `文件:行号`。
- `测试佐证` —— 仓库既有测试，指名到测试函数。
- `实测` —— 本次跑的只读探针，附脚本路径与原始输出（见附录）。所有探针用 `MockTransport` 在真实 SDK 之下模拟上游，**没有向任何真实上游发过请求，没有触碰 4141 端口的现网 Bun 服务**。
- `判断` —— 我的推论，可争议。
- `推测` —— 未验证，不得作为结论使用。

探针的隔离措施：每个脚本进入前把 `XDG_DATA_HOME` 指向临时目录（与 `tests/int/conftest.py` 同一手法），因此 history db、tokenization 状态、token 存储都不落到用户真实数据目录。

---

## 一句话结论

用户的判断**前半句成立、后半句不成立**：`client_request_deadline` 确实在响应头到达时就解除（实测），而且它**触发时给客户端的还是错的东西**（502 `CancelledError`，而非设计中的 504）；但这不是「两套生命周期没有一致模型」，而是**一个正确的原语被安在了错误的作用域上，加上同一族的三条未接线的报告缺口**。上游侧的所有权模型是自洽且实测有效的（一个绝对时刻、两处施加、关闭沿生成器链层层级联并真的释放了连接）。**不需要全面重写**；需要的是把客户端侧的时限从 `handle_bounded` 挪到交付生成器层（`with_deadline_at` 已经把这个模式写好了），加一条终止原因的对客户端通道，以及把「谁给总时长兜底」写进文档。详见第 6 节。

---

## 1. `client_request_deadline`（默认 3600）实际覆盖哪一段

### 1.1 它在哪里施加、哪一刻解除

`代码事实`：

- 施加点唯一：`src/app/server/handler.py:328-341` `handle_bounded`，`async with asyncio.timeout(deadline)` 包住 `await handle(...)`（`:338-339`）。
- `handle()`（`:130-171`）里唯一的 await 点是 `outcome = await driver.run(context)`（`:159`）。
- `driver.run` → `_send`（`src/app/pipeline/direct_driver/base.py:141,221-260`）。`_send` 的 docstring 自己写明：「This await ends when the response headers arrive, not when the body has been read — measured 2026-08-20」（`base.py:228`）。
- 调用方 `src/app/server/pipeline_app.py:444` `handled = await handle_bounded(...)`，返回后才在 `:483-529` 构造流式响应；body 的迭代发生在 `handle_bounded` 已经退出之后。

所以：**流式请求下，`client_request_deadline` 覆盖 `handle_bounded` 进入 → 上游响应头到达；body 交付完全在它之外。** 非流式请求下它覆盖到 body 读完（SDK 以 `stream=False` 调用 httpx，body 在 `_send` 的 await 内读完）。

`实测`（`/tmp/probe_lifecycle.py` PROBE 1 与 `/tmp/probe_lifecycle2.py` PROBE 5）：

| 场景 | 配置 | 结果 |
|---|---|---|
| 流式，body 滴流约 3s | `client_request_deadline: 1` | **完整交付**，`elapsed=3.1s`，末尾有 `message_stop` |
| 同一上游，正样本对照 A | `upstream_request_deadline: 1` | `StreamDeadlineError`，`elapsed=1.0s` |
| 流式，响应头延迟 2s，正样本对照 B | `client_request_deadline: 1` | 1.0s 时结束（证明这个键确实接线了，只是作用域错） |
| **非流式**，body 延迟 3s | `client_request_deadline: 1` | 1.0s 时结束 —— 缓冲路径确实被覆盖 |

`实测`（`/tmp/probe_lifecycle7.py` PROBE 12 G'，**主产品路径**：Anthropic Messages 入、Responses 上游）：`client_request_deadline=1` + `upstream_request_deadline=3`，上游发完两个 item 后静默 —— 请求在 **3.0s** 被 `StreamDeadlineError` 结束。1 秒的客户端时限对 body 完全无效，结束它的是上游侧的 3 秒。这是对用户判断最直接的一条测量。

### 1.2 它自称的契约

用户亲笔文档（最高权威）`docs/.human-controlled/config.example.yaml:380-382`：

> 一次客户端请求的最大存活秒数（0 = 禁用）。从受理开始计，任何重试都不重置它，所以它是整个请求的外层上限。
> Max seconds one CLIENT request can live (0 = disabled). Measured from admission and never reset by retries, so it bounds the whole client-visible operation.

`docs/.human-controlled/upstream-retry-and-continuation.md:59-61` 同：「后者是代理端对客户端请求的保护」。
`src/app/config/schema.py:249-252` 的代码注释复述了这个契约（"bounds the whole operation"）。

**两处与实现不符**（`代码事实`）：

1. 「整个请求的外层上限」——流式下不含 body（上文）。
2. 「从受理开始计 / Measured from admission」——计时起点其实是 `handle_bounded` 进入，而 `pipeline_app.py:355 await request.body()`、JSON 解析（`:365`）、`build_context`（`:375`）、attribution 剥离（`:382`）、以及 `InFlightLimit` 中间件的排队（`:709-712`，middleware 在外层）**全部在时限之外**。同一份 `_Trace.started` 却是在 `_serve` 里 `:306` 设的，比时限起点更早——所以日志行报的时长和时限量的时长起点不同。`.dev/docs/anthropic-responses-bridge/reports/260820-spec-revision-candidate.md:44` 已经实测过排队时间不计入任何 deadline，与此一致。

### 1.3 触发时客户端拿到什么（这一条比作用域更严重）

`实测`（`/tmp/probe_lifecycle2.py` PROBE 4/5/7）：三种不同 await 点上让 `client_request_deadline` 触发，客户端一律拿到：

```
status=502  body={"error":{"type":"CancelledError","message":""}}
```

而不是 `handler.py:340-341` 写的 `UpstreamTimeout(f"client request exceeded {deadline}s")`（那会经 `error_status` 走 504，`handler.py:376-377`）。

`代码事实` 的机制：`asyncio.timeout` 通过给当前 task 投递 `CancelledError` 来实现；这个 `CancelledError` 落在 `base.py:142 except BaseException as error:` 里被接住，`classify()` 判 ABORT（`exceptions.py:113-123`，`CancelledError` 不在闭集内），`run()` **正常返回** `outcome.error=CancelledError`。于是 `asyncio.timeout.__aexit__` 看到 `exc_type is None`，不抛 `TimeoutError`，`handler.py:340` 的 `except TimeoutError` 永不命中。`pipeline_app.py:466-476` 读到 `response is None`，把 `CancelledError` 当成上游失败渲染成 502，而 `str(CancelledError())` 是空串。

结论：**`handle_bounded` 的 `raise UpstreamTimeout` 在 driver 路径上是死代码。** 客户端时限一旦触发，客户端得到的是一个既没有正确状态码也没有任何说明文字的 502。

`判断`：这不只是文案问题。502 对客户端意味着「代理坏了」，504 意味着「超时了、可以重试」，而 `CancelledError` 这个类名会把读日志的人指向 asyncio 而不是配置。

**已有记录**：这条 2026-08-20 就被一次评审查出并编号 O5（`.dev/docs/delivery-keepalive/reports/260820-review-upstream-timeout-wiring.md:333,342,390`），处置写的是「先前存在，不阻断本次 slice，单开一条」。我在 `.dev/docs/` 全量 grep 后**没有找到它进入任何活文档**（`deferred.md` / `status.md` / `decisions.md` 都没有）——它只活在那份报告里，所以没有被修。同一份报告的 `260820-research-upstream-timeout-wiring.md:86,257` 也已经指出流式下 `client_request_deadline` 只覆盖到响应头。本次审计的价值主要是**第一手复现 + 补上「触发时客户端看到什么」这一半**。

### 1.4 流式请求的客户端侧总时长，由什么兜底（穷举）

按默认配置（`schema.py:150-152`：`response_header=0`、`stream_idle=0`、`upstream_request_deadline=1200`；`schema.py:252`：`client_request_deadline=3600`）：

| 兜底者 | 覆盖什么 | 默认值 | 证据 |
|---|---|---|---|
| `client_request_deadline` | 仅 `handle_bounded` → 响应头 | 3600 | `代码事实` + `实测` |
| `upstream_request_deadline` 经 `with_deadline_at` | **流式 body 的绝对上限**，从「最后一次 attempt 打开」起算 | 1200 | `代码事实` `pipeline_app.py:507-513` + `测试佐证` `test_the_attempt_deadline_reaches_the_streamed_body` |
| `stream_idle` 经 `with_idle_timeout` | 上游静默 | **0 = 禁用** | `代码事实` `pipeline_app.py:508-511`、`handler.py:543-548` |
| `response_header` | 仅响应头 | 0 = 禁用 | `代码事实` `base.py:242-251` |
| **httpx/SDK 的 read timeout** | 单次 socket 读的静默上限 | **600s**（没人选过这个数） | `实测`，见下 |
| TCP keep-alive | 探测对端已死，不是墙钟 | 15s 间隔 | `代码事实` `schema.py` `tcp_keepalive_interval` |
| `sse_ping_interval` | **不是兜底**，是防止客户端自己放弃 | 15 | `代码事实` `stream.py:100-111` |
| 优雅停机 | 只在关机时 | 见第 5 节 | —— |

关于那条 600s：`代码事实` + `实测`。活链路用的是 `src/app/server/composition.py:135-181 build_http_client`，它**没有传 `timeout=`**，于是 httpx 客户端带的是 httpx 默认 `Timeout(timeout=5.0)`；OpenAI SDK 在检测到「http_client 带的是 httpx 默认值」时改用自己的 `DEFAULT_TIMEOUT`。实测：

```
httpx client default timeout: Timeout(timeout=5.0)
AsyncOpenAI resolved timeout (production construction): Timeout(connect=5.0, read=600, write=600, pool=600)
request extensions seen by the transport: [{'timeout': {'connect': 5.0, 'read': 600, 'write': 600, 'pool': 600}}]
```

即每一个上游请求都带着 `read=600` 到达 transport 层。另一个 builder `src/app/upstream/client.py:21-37 create_http_client` **确实**按 `upstream.read_timeout` 设了超时，但它只被 `app/upstream/bootstrap.py:110` 用，不在活链路上。

`判断`：所以「`stream_idle: 0` = 禁用静默守卫」这句话在事实上是不准确的——真正的静默上限是 600 秒，来自一个没人配置、没人记录的 SDK 默认值。这不是缺陷但是一处**未写下的兜底**，值得进文档。

**没有兜底的情况**（`代码事实` + `实测` PROBE 2）：把 `upstream_request_deadline` 设为 0（schema 允许，`ge=0`），并且 `stream_idle` 保持默认 0，则流式 body 只剩 600s 的 per-read 静默上限——一个**持续滴流但永不结束**的上游没有任何时限能终止它。PROBE 2 在这组配置下确认交付照常完成（该探针的上游会自己结束，所以它证明的是「两道守卫都没开火」，不是「跑了无限久」）。

---

## 2. `upstream_request_deadline`（默认 1200）实际覆盖哪一段；「两处施加、同一绝对时刻」是否属实

**属实。** `代码事实`：

1. 时刻在 attempt 打开时定死一次：`src/app/pipeline/direct_driver/base.py:129-132`
   ```python
   attempt = context.begin_attempt()
   if self._attempt_deadline > 0:
       attempt.deadline_at = asyncio.get_running_loop().time() + self._attempt_deadline
   ```
2. 第一处施加（响应头之前，driver 还持有 attempt）：`base.py:253-260` `async with asyncio.timeout_at(deadline_at)`，超时抛 `UpstreamTimeout(f"attempt exceeded {self._attempt_deadline}s")`。
3. 第二处施加（body，driver 已经出栈）：`src/app/server/pipeline_app.py:490-491` 读 `attempt = context.current_attempt`，`:507-513` `with_deadline_at(..., deadline_at=attempt.deadline_at)`；`src/app/streaming/deadline.py:33-45` 用 `asyncio.timeout_at(deadline_at)` 逐次 pull 施加，超时抛 `StreamDeadlineError`。

两处读的是同一个 `attempt.deadline_at` 字段，**不是两次 `now + deadline`**。`pipeline_app.py:490` 的注释明说了这一点，且有测试锁住：

`测试佐证`：`tests/int/test_pipeline_app.py::test_the_deadline_is_one_instant_and_not_a_duration_started_twice`——响应头先花掉 3 秒中的 2 秒，断言总耗时 `< 4.0s`（若下游重算会落在 5 秒附近）。另一条 `test_the_attempt_deadline_reaches_the_streamed_body` 锁住 body 段确实被覆盖。

`实测` 复核：PROBE 1 对照 A（1s deadline，3s 滴流 body）在 1.0s 结束；PROBE 12 F' 在主产品路径上同样。

两点补充事实：

- 施加的是**最后一次 attempt** 的时刻。重试会重新 `begin_attempt()` 并重新定死（`base.py:129-132`），所以 N 次重试的总时长是 N×1200 的量级，`upstream_request_deadline` 从来不是「这个客户端请求的上游总时长」。`实测` PROBE 6：`upstream_request_deadline=1` + 响应头永远不来 → 重试 9 次、总耗时 10.1s、最终 504 `PipelineAbort: network budget exhausted: attempt exceeded 1s`。设计上本该由 `client_request_deadline` 兜住这个乘积——而它兜不住 body（第 1 节）。
- `deadline_at is None`（即 `upstream_request_deadline=0`）时 `with_deadline_at` 明确表示「nothing bounds it」（`deadline.py:18,27-31`）。

---

## 3. 客户端消失时，上游请求会不会被释放

**会，在实际可达的路径上都会，且我实测到了连接确实关闭。** 一个结构性的窟窿存在但在本部署下不可达。

### 3.1 走通链路（`代码事实`）

1. ASGI 层：uvicorn h11 在 `connection_lost` 里置 `disconnected=True` 并 `message_event.set()`（`uvicorn/protocols/http/h11_impl.py:107-125`），于是挂起的 `receive()` 立刻返回 `{"type":"http.disconnect"}`（`h11_impl.py:539-540`）。`eof_received` 返回 None（`:132-133`），所以客户端只发 FIN 也会走到 `connection_lost`。
2. starlette 1.6.0 `StreamingResponse.__call__`：uvicorn 的 HTTP scope 声明 `spec_version "2.3"`（`h11_impl.py:207`、`httptools_impl.py:228`、`zttp_impl.py:157`），**小于 2.4**，所以走的是 task group + `listen_for_disconnect` 分支——**断连的发现不依赖于我们是否正在 `send`**。这一点很重要：在 `full` 缓冲策略下长时间不写字节，断连**照样**被及时发现。
3. `_AccountedStreamingResponse.__call__`（`pipeline_app.py:614-630`）：`finally` 里 `await self._content.aclose()`。
4. `_tracked_delivery`（`:659-680`）：`async with aclosing(chunks)` 把关闭传给下一层。
5. `stream_delivery`（`stream.py:194-208`）→ `_deliver`（`:231-239` 的 `aclosing`）→ `_events_with_ping` 的 `finally`（`:140-156`）先用 `finish_stream_cleanup` 结掉在飞的 `anext` 任务，再关 `events`。
6. `_counted_upstream` → `with_deadline_at` 的 `finally: await close()`（`deadline.py:46-48`）→ `with_idle_timeout` 的 `finally: await close()`（`idle_timeout.py:50-52`）→ `response.aiter_bytes()`。
7. httpx2 2.12.0：`aiter_bytes` 用 `contextlib.aclosing(self.aiter_raw())`，而 `aiter_raw` 的 `finally` 里有 `await stream.aclose()` + `await self.aclose()`（`.venv/.../httpx2/_models.py`）。**这是关键的第三方事实**：httpx 0.28.1 把 `aclose()` 放在循环之后而非 `finally`，httpx2 挪进了 `finally`，`idle_timeout.py:26` 的注释记录了这次迁移。所以链路末端真的会释放响应。

### 3.2 实测

`实测`（`/tmp/probe_lifecycle.py` PROBE 3，ASGI 层真断连、非 TestClient）：第一个块送达客户端后投递 `http.disconnect`，结果

```
events: ['upstream-yielded-first-block', 'upstream-body-finally']
upstream httpx response is_closed=[True]
```

上游 body 生成器的 `finally` 跑了，httpx 响应 `is_closed=True`。日志行 `[GONE] ... delivery stopped before upstream finished`。

`实测`（`/tmp/probe_lifecycle5.py` PROBE 10，**第一个 chunk 之前就断开**：客户端在上游等待期间按 Esc，`StreamingResponse.__call__` 一开始就拿到 `http.disconnect`）：同样 `is_closed=True`，`upstream-body-finally` 跑了。原因是 anyio 的 `start_soon` 让 `stream_response` 在父任务的第一个 checkpoint 处先跑了一步。

### 3.3 漏网路径

`实测`（`/tmp/probe_lifecycle4.py` PROBE 9）：**唯一**我能构造出的泄漏是「`send({'type':'http.response.start'})` 自己抛异常」——此时 body 生成器一次都没被迭代过，`aclose()` 一个没启动的 async generator**什么都不跑**，于是：

```
upstream body events=[]
upstream httpx response is_closed=False
```

计费与日志仍然正确（`_AccountedStreamingResponse` 的 docstring 承诺的那一半成立，`pipeline_app.py:601-607`），但**上游连接没有被释放**，只能等 GC。

这条在当前部署下**不可达**：uvicorn 三个 HTTP 实现的 `send` 在 `if self.disconnected: return` 处静默返回，从不抛（`h11_impl.py:463-468`、`httptools_impl.py:463-468`、`zttp_impl.py:408-413`）。`判断`：所以它是一个**潜在**缺口而非现行泄漏；换一个 ASGI 服务器（其 `send` 在断连后抛 `ClientDisconnected`）就会踩到。修法很小：把 `response.aiter_bytes()` 换的那个 httpx 响应对象也交给 `_AccountedStreamingResponse` 持有，在 `finally` 里无条件 `await response.aclose()`（幂等）。

### 3.4 另一条与断连无关、但同族的未释放

`代码事实`：`DirectDriver.run` 在两处**丢弃一个已经拿到的 `httpx2.Response` 并继续重试，全程没有 `aclose()`**：

- `base.py:150-165`：限流器判定该状态码算失败 → `outcome.response = None`，continue。
- `base.py:167-175`：`attempt.succeeded` / `request.succeeded` 订阅者抛异常 → `outcome.response = None`，continue。

`base.py` 全文没有任何 `aclose`。对流式请求，被丢弃的那个响应持有一条活连接。

可达性：`grep -rn "ATTEMPT_SUCCEEDED" src/` 显示**今天没有任何订阅者注册 `attempt.succeeded`**；限流那条要求 SDK 返回而非抛出一个受限状态码，而 `_in_pipeline_terms`（`ghc_client/client.py:100-114`）会把 SDK 的状态异常规范化后抛出，所以正常情况下 `outcome.response` 不会带着 429/502 到达那里。`判断`：现阶段是**潜伏**而非活跃泄漏，但它和 3.3 是同一个形状——「谁持有这个响应、谁负责关它」没有一个统一的答案。

### 3.5 既有测试覆盖情况

`测试佐证`：`tests/int/test_pipeline_app.py::test_a_client_that_walked_away_is_not_blamed_on_upstream`（关掉交付生成器 → 日志判 `gone`）、`::test_a_body_that_fails_to_close_is_still_accounted_for`（关闭抛异常仍记账）。
**没有**测试断言「上游 httpx 响应真的被关掉了」。`tests/unit/pipeline/delivery/test_stream_delivery.py:508` 的注释明说「What this does not pin: the release of a real httpx response」，而且那条注释是按 httpx 0.28.1 的行为写的、**在 httpx2 迁移后已经过时**（`idle_timeout.py:26` 记录了迁移，注释没跟上）。本次 PROBE 3/10 是我所知第一次把「响应真的关了」测出来。

---

## 4. 上游失败时，客户端会不会被恰当告知

`实测`（`/tmp/probe_lifecycle3.py` PROBE 8，Anthropic 上游；`/tmp/probe_lifecycle7.py` PROBE 12，Responses 上游 = 主产品路径）。两条路径结论一致，下表取 Responses 路径：

| # | 上游那一侧的结束形态 | 客户端收到 | 收尾 | 日志 |
|---|---|---|---|---|
| 1 | 正常终结事件（`response.completed`） | 完整块 + `message_delta` + `message_stop` | clean EOF | `[ OK ]` |
| 2 | EOF 但无终结事件，且**已交付过至少一个块** | 完整块 + **SSE `error` 帧**（`incomplete_responses_stream`） | clean EOF | `fail: upstream stream ended without a terminal event` |
| 3 | EOF 但无终结事件，且**一个块都没交付过** | **200 + 空 body，没有任何 SSE 帧** | clean EOF | `fail: 同上` |
| 4 | 上游撕裂（`ReadError` / reset / GOAWAY / 转换器抛异常） | 已交付的块，**没有 error 帧**，chunked body 不完整 | **NO-FINAL-CHUNK** | `fail: stream failed before a terminal event: <原因>` |
| 5 | `stream_idle` 触发（`StreamIdleTimeoutError`） | 同 4，**逐字节相同** | NO-FINAL-CHUNK | `fail: ... No stream item received for Ns` |
| 6 | `upstream_request_deadline` 触发（`StreamDeadlineError`） | 同 4，**逐字节相同** | NO-FINAL-CHUNK | `fail: ... attempt exceeded its deadline` |
| 7 | 客户端自己走了 | —— | —— | `gone: delivery stopped before upstream finished` |
| 8 | 响应头之前失败（拒绝 / 限流 / 超时 / 重试耗尽） | JSON 错误体 + 恰当状态码（400/429/504/上游原状态） | —— | `fail` |

`代码事实` 支撑：形态 2 的 error 帧在 `stream.py:298-307`；形态 3 的静默返回在 `stream.py:295-297`（注释里已自认这是既有行为）；形态 4/5/6 走 `stream.py:263-265` 的 `except Exception → torn`，`:266-269` 因为 `replay is None` 直接 `raise torn`，**异常绕过了 `:285-313` 所有写帧的代码**，一路穿出 `_tracked_delivery`（`pipeline_app.py:674-678` 记录后再抛）与 starlette，最终连接被截断。

### 彼此不可区分的组合

- **4、5、6 三者对客户端完全不可区分**：PROBE 12 的 E' 与 F' 输出逐字节相同（同样 8 个事件、1353 字节、NO-FINAL-CHUNK），区别只存在于代理自己的日志行。也就是说，「上游断了」「上游哑了」「我们主动掐了」三件事，客户端只能看到同一个截断的 SSE 流；Anthropic 客户端会把它读成网络错误并可能整轮重试。
- **3 与「成功但零内容块」不可区分**：PROBE 8 的 C（EOF、什么都没有，日志 `fail`）与 D（收到了合法终结事件但零内容块，日志 `ok`）给客户端的都是 `status=200 events=[] bytes=0 clean-eof`。日志能分辨，客户端不能。
- 2 是唯一一种「上游侧异常结束、且客户端被明确告知」的形态。

`判断`：这里的不对称是本次审计里对客户端伤害最实在的一条。项目**已经有** `error_frame`（`pipeline/delivery/anthropic_sse.py:141`）并且在形态 2 用了它，但形态 4/5/6 —— 也就是所有「主动或被动的终止」——都没有走这条通道。这不是缺少机制，是**机制没有接到终止路径上**。

### 一条相关的已实现但未接线的能力

`代码事实`：`ReplaySupport` / `replay=` 参数（`stream.py:38-49,181,203,220,268-283`）在 HEAD `96eb2fa` 刚落地，但 `grep -rn "replay=" src/` 显示**没有任何调用点传它**——`pipeline_app.py:502-523` 调 `stream_delivery` 时没有 `replay`。所以「替换一个客户端没看见过的撕裂 attempt」目前对服务中的链路是关的。`判断`：这看起来像是分片落地的中间态而非缺陷，但它确实意味着形态 4 当前**没有任何补救**，只有截断。

---

## 5. 优雅关闭（SIGTERM）时两侧各自怎么终止

**有两条不同的关机路径，取决于怎么启动。** 这一点本身值得记下来，因为它们的行为不同。

### 5.1 systemd 部署路径（`--fd 3`，即项目的部署目标）

`代码事实`：`src/app/cli.py:283-304` → `serve_inherited`（`cli.py:141-159`），用的是**裸 uvicorn**，`timeout_graceful_shutdown=config.graceful_cleanup_timeout`。单元文件 `contrib/systemd/ghc-api-proxy.service:23,28` 与 `contrib/systemd/install-user.py:20-21,78,83`：`--graceful-timeout 300`、`TimeoutStopSec=330s`。

uvicorn 的行为（`.venv/.../uvicorn/server.py:272-317`）：SIGTERM → 关监听 → 对所有连接 `connection.shutdown()` → 等待在飞任务，上限 `timeout_graceful_shutdown`（300s）→ 超时则 `t.cancel()` 逐个取消请求任务 → lifespan shutdown。

于是：**客户端侧**在 300 秒内不受打扰地继续收块；到点后任务被取消。**上游侧**由这个取消沿第 3 节的链路级联释放（PROBE 10 实测取消路径确实释放）。`ShutdownLadder` 在这条路径上**完全不参与**。

`判断`：所以在部署目标上，「关机 ↔ 在飞流」之间**有**一个明确的关联，但它是 uvicorn 的通用机制（cancel 一个 task）而不是本项目写的协调；本项目在这条路径上没有任何「告诉客户端我们要走了」的动作——被取消的流对客户端就是第 4 节的形态 4/5/6，一个截断。

### 5.2 独立运行路径（`app start` 不带 `--fd`）

`代码事实`：`cli.py:306-338` → `_serve_pipeline` → `run_standalone` → `StandaloneServer`（`src/app/lifecycle/standalone.py`）。三级阶梯：

- `DRAINING`（第 1 个信号）：`stop_accepting` + `stop_admitting`（拒绝新请求、`connection.shutdown()`），然后 `wait_drained()`——`adapter.py:153-161` 是一个**无上限**的轮询等待。
- `INTERRUPTING`（第 2 个信号）：`interrupt_connections()` + `cancel_requests()`（`adapter.py:194-218`，后者是真正 `task.cancel()`）。
- `FINALIZING`（第 3 个信号）：再 cancel 一次，不再等。
- `graceful_cleanup_timeout` 只包住 `_finalize`（`standalone.py:245-288`），不包 drain。

**drain 是故意无上限的**，理由写在 `standalone.py:10-14`：「A request already carries its own deadline.」

`判断`：这个前提**只在默认值下成立，且成立得比它以为的弱**。对一个流式请求，「自己的时限」是 `upstream_request_deadline`（1200s，可被设成 0 关掉）加上 600s 的 SDK read timeout；**不是** `client_request_deadline`（3600s，流式下管不到 body）。所以：把 `upstream_request_deadline` 设为 0 的操作者会同时、静默地把 drain 变成可能无限等待。这是「两个设置之间存在没写下来的耦合」的一个具体实例。

### 5.3 一处文档不一致

`代码事实`：`src/app/config/schema.py:250` 声称 `client_request_deadline` 「Also the base for the systemd stop timeout」。但安装器里的 `TimeoutStopSec=330` 是从 `DEFAULT_GRACEFUL_TIMEOUT_SECONDS=300` 推出来的（`install-user.py:20-21`），与 3600 无关，全仓 grep 也找不到任何从 `client_request_deadline` 推导停机超时的代码。`判断`：这句注释要么过时要么从未成立，应当改掉——它会让读者以为把 3600 调大就会自动放宽 systemd 的停机窗口。

---

## 6. 综合裁断

### 裁断

**是「一处具体缺口 + 三条同族的未接线报告通道」，不是「系统性混乱」。不需要全面重写。**

我先把支持用户判断的证据完整列出来，不做削弱：

1. 客户端时限的作用域是错的（第 1.1 节，实测）。
2. 它触发时给出的状态码、异常类型、错误文案全是错的，因为 driver 吞掉了 `asyncio.timeout` 投递的取消（第 1.3 节，实测）。这确实是一处**跨层所有权错误**：`base.py:142` 的 `except BaseException` 声称对一个它并不拥有其取消语义的作用域负责。
3. 「谁给客户端请求的总时长兜底」这个问题，今天的答案是一个没人选过的 SDK 默认值 600（第 1.4 节，实测）。
4. 上游侧的三种终止形态对客户端不可区分，而项目明明有 error 帧通道却没接上去（第 4 节，实测）。
5. 一个请求的生命有四个不同的所有者：`_serve`/`_Trace` 管观测、`handle_bounded` 管前半段时限、`_StreamAccounting` 管结局判定、`_AccountedStreamingResponse` 管释放。时限被安在了**最早结束**的那个所有者身上——这正是缺口 1 的成因。
6. 关机与在飞流之间没有本项目写的协调，靠的是 task cancel 这一通用机制；独立路径的无上限 drain 建立在一个只在默认值下成立的前提上（第 5 节）。

再列反对「需要全面重写」的证据：

1. **上游侧的模型是自洽的，而且经得起实测。** 一个绝对时刻在 attempt 打开时定死、两处施加、有一条专门锁「不是两次计时」的回归测试（第 2 节）。这不是混乱的样子。
2. **释放链路是刻意设计的、统一的、并且真的工作。** `with_deadline_at`、`with_idle_timeout`、`_events_with_ping`、`stream_delivery`、`_tracked_delivery`、`_AccountedStreamingResponse` 六层各自都写了「关我就关我下面那层」，末端 httpx2 的 `finally` 收口；PROBE 3/10 实测 `is_closed=True`。一个「没有一致模型」的系统不会有六层一致的关闭契约。
3. **缺口 1 的修法是加法，不是重写。** `with_deadline_at` 已经把「把一个绝对时刻施加到交付生成器上」这件事写成了通用件；客户端时限要做的是同一件事，只是时刻在准入时算、并且要跨越重试。改动量在几十行量级，且已有的测试形状（`test_the_deadline_is_one_instant_and_not_a_duration_started_twice`）可以照抄。
4. **这些缺口大多在 2026-08-20 就被发现并写清楚了**（O5、以及流式作用域那条），只是**没有从报告进入活文档**，因此没人去修（第 1.3 节末，grep 证据）。`判断`：这是流程问题的证据，不是模型混乱的证据。一个混乱的设计不会有人能在两天前就把病因写得这么准。

### 那条具体缺口怎么补，补完还剩什么

**必须先请用户裁决的一件事**（`no-silently-cut-but-defer`）：`client_request_deadline` 在流式 body 段触发时，该给客户端什么？响应头（200）早就发出去了，状态码改不了。候选：(a) 发一个 SSE `error` 帧再干净收尾（和形态 2 一致）；(b) 直接截断（和形态 4/5/6 一致）；(c) 先 flush 已完成的块再发 error 帧。我倾向 (a)，理由是它复用已有通道且客户端能分辨。**这条不该由我替用户定。**

补法（三步，彼此独立，可分片落地）：

1. **把取消变回超时。** 在 `handle_bounded` 里改用「自己拥有的信号」而不是依赖 task 取消能穿过 driver——最小改动是在 `base.py:142` 与 `:170` 的 `except BaseException` 前先 `if isinstance(error, asyncio.CancelledError): raise`（取消不是上游失败，driver 无权把它转成 outcome）。这一条**单独就值得做**，它同时修好 1.3 的 502/504 和第 5 节里「关机 cancel 落进 driver」的同形问题。
2. **把客户端时限挪到交付层。** 在准入处（`_serve` 里 `trace.started` 附近，这样「从受理开始计」才名副实）算一个 `client_deadline_at`，像 `attempt.deadline_at` 一样挂在 context 上，然后在 `pipeline_app.py:507` 的 guard 栈**外面**再包一层 `with_deadline_at(..., deadline_at=client_deadline_at)`，并让它抛一个自己的异常类型（不要复用 `StreamDeadlineError`，否则第 4 节的不可区分再添一员）。缓冲路径已经被覆盖，不用动。
3. **给三种终止形态接上 error 帧。** 在 `_deliver` 的 `raise torn` 之前，若 `client_has_bytes` 已置位，就按裁决 (a) 写一个带具体 `code` 的 error 帧再抛。这一条会同时改善形态 4/5/6 和新的客户端时限。

补完之后**还剩**（按我的优先级排序，都不阻断上面三步）：

- 形态 3 与「成功但零块」不可区分（第 4 节）——需要决定空回复要不要也发 `message_start`+`message_stop`。
- 600s 的 SDK read timeout 没人选过、没写进任何文档（第 1.4 节）——建议在 `build_http_client` 显式传一个 timeout，值由用户定。
- `base.py` 丢弃响应不 `aclose`（第 3.4 节）与 `http.response.start` 抛异常时的泄漏（第 3.3 节）——两条潜伏项，各几行。
- `schema.py:250` 那句「systemd stop timeout 的基准」是错的（第 5.3 节）。
- 独立路径的 drain 无上限，其前提依赖 `upstream_request_deadline > 0`（第 5.2 节）——至少要在 `standalone.py:10-14` 的注释里写明这个依赖。
- `ReplaySupport` 未接线（第 4 节末）——确认是分片中间态还是遗漏。

### 关于「全面重写」

`判断`（可争议，我给出依据而非结论）：如果真要重写，值得重写的**只有一个东西**——「一个客户端请求的生命由谁持有」这个对象。今天它散在四个所有者里，谁都没有完整视图。可以设想一个在准入处创建、贯穿到 `_AccountedStreamingResponse` 的 `RequestLifetime`，同时持有：客户端截止时刻、当前 attempt 的截止时刻、终止原因、以及释放清单。这会让第 1、3.3、3.4、4、5 节的问题都变成同一个对象上的字段。但**这不是当前该做的事**：上面三步补丁能在不动结构的前提下解决全部已实测的对客户端可见的问题，而重写会把一个正在服务的链路整个掀开。建议把 `RequestLifetime` 记进 `deferred.md` 作为一个候选重构，等下一次有大改动路过时再评估。

---

## 附录 A：探针脚本与复现方式

| 脚本 | 内容 |
|---|---|
| `/tmp/probe_lifecycle.py` | PROBE 1（客户端时限不覆盖 body + 两个正样本对照）、PROBE 2（两道守卫都关掉）、PROBE 3（断连释放上游） |
| `/tmp/probe_lifecycle2.py` | PROBE 4/5/6/7（触发时客户端收到什么；缓冲路径被覆盖；上游时限的对照；重试次数） |
| `/tmp/probe_lifecycle3.py` | PROBE 8（Anthropic 上游六种结束形态的客户端可见结果） |
| `/tmp/probe_lifecycle4.py` | PROBE 9（`http.response.start` 抛异常 → 上游未释放） |
| `/tmp/probe_lifecycle5.py` | PROBE 10（第一个 chunk 之前断连 → 上游已释放） |
| `/tmp/probe_lifecycle6.py` | 已废弃：本地静默 server 在沙箱里起不来；其中有效的部分改用一行 `uv run python -c` 复现（第 1.4 节的三行输出） |
| `/tmp/probe_lifecycle7.py` | PROBE 12（主产品路径 Responses 上游的同一组形态 + G' 客户端时限对 body 无效） |

跑法：`timeout 180 uv run --project /home/xp/src/ghc-api-proxy-py python -u /tmp/probe_lifecycle3.py`。
所有脚本通过 `importlib` 加载 `tests/int/test_pipeline_app.py` 复用 `make_client` / `sse_upstream` / `responses_sse_upstream`，因此上游行为与既有集成测试同源；它们**不是**测试，没有进仓库。

## 附录 B：本报告未验证的事项

- 真实 Copilot 上游的行为一律未验证（本次没有发出任何真实上游请求）。第 4 节的形态表描述的是**代理自己**面对各种上游结束方式的反应，不是对 Copilot 会怎么结束的断言。
- 600 秒 read timeout 的**触发效果**是由两条实测事实合成的（SDK 解析出的值 + 该值确实随每个请求到达 transport），我没有真的等 600 秒看它开火。合成结论的强度：足以据此行动，不足以据此写「已实测触发」。
- 第 5.1 节 uvicorn 关机路径读的是 uvicorn 0.52.4 源码，没有真的向进程发过 SIGTERM。
- `tests/systemd/`、`tests/e2e/` 未运行、未阅读。
- 未运行完整回归（本次是只读审计，没有改动生产代码，不需要门）。
