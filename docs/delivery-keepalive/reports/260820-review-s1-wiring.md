# S1 接线评审：弃流关闭确定性改动落到真实请求链路上会怎样

- 评审对象：工作树未提交改动 `src/app/pipeline/delivery/stream.py`、`src/app/pipeline/delivery/sse_source.py`、`tests/unit/test_stream_delivery.py`
- 基线 commit：`883b104507bd26e19b14b58fa54b3c93042f9d9e`
- 视角：生产接线与可观测性影响（不做并发理论推演）
- 探针目录：`/tmp/rev-s1-wiring/`（不改仓库，探针与对照快照都在 `/tmp`）
- 日期：2026-08-20

## 结论

**改动在真实请求链路上确实生效：客户端中途断连时，上游 socket 被释放，可观测性的时序与取值一字不变。** 这不是读代码推的，是在「真 uvicorn 上游 + 真 httpx 连接池 + 真 Starlette `StreamingResponse.__call__` 断连分支」上量出来的：改动前连接池里那条连接过了 1.6 秒、两次 `gc.collect()` 仍是 `ACTIVE`，上游服务器自始至终没收到断连，进程里留着一个永不完成的 `async_generator_asend` 任务；改动后 `__call__` 返回的那一刻连接池就空了，上游服务器 10 个 tick 内看到断连，零遗留任务。**建议采纳，不要回退。**

但有两件事必须一并处理，因为它们都是**这次改动之后才成立或才暴露**的：

| # | 级别 | 一句话 |
|---|---|---|
| F1 | major | 「客户端不读了」这一形态下，改动**确定性地**在 operator stderr 上新增一条 `RuntimeError: aclose(): asynchronous generator is already running`（新 5/5，旧 0/5）。这恰恰是 `_events_with_ping` 注释里明说要避免的那类噪声 |
| F2 | major | 同一形态下上游连接的释放**改动前后都依赖循环 GC**，因为 `_AccountedStreamingResponse` 从不关闭自己的 `body_iterator`。修法在本仓库已有现成范本（legacy 链路的 `DelayedStartStreamingResponse.stream_response`），实测能把它变成不依赖 `gc.collect()` |
| F3 | minor | `Response.aclose()` 全程没被调用过，`response.is_closed` 改动前后恒为 `False`；最后两跳（`_counted_upstream` → httpx，httpx 内部）仍是 GC 级联 |
| F4 | minor | 新增的两个单测跳过了 `_counted_upstream` 与 httpx 这两跳，而这两跳正是本次实测中唯一不闭合的部分。它们对本次改动有鉴别力（旧代码上 2/2 变红，已验证），但不能拿来支撑「链路闭合」这个更大的声称 |
| F5 | info | 任务给的链路描述里 `src/app/streaming/sse.py::stream_response` **不在这条链路上** |
| F6 | info | 评审期间工作树被并行会话改动（`pipeline_app.py`、`assembler.py`、`request_log.py`、`stream.py` 又加了一处 `or "end_turn"`），评审范围已漂移 |

Blocker（阻断我完成任务的）：0。F1/F2 是产物缺陷，不是执行阻塞。

---

## 1. 完整链路对账：谁在什么时候关了谁

### 1.1 先纠正一处链路描述（F5）

生产入口是 `create_pipeline_app`（`src/app/cli.py:23,144,169`），流式响应用的是 `_AccountedStreamingResponse`，它继承 **Starlette 原版 `StreamingResponse`**（`src/app/server/pipeline_app.py:337`）。

`src/app/streaming/sse.py` 里的 `DelayedStartStreamingResponse.stream_response`（`sse.py:95-203`）只被 `src/app/routes/anthropic.py:247` 使用，那是 legacy 的 `app_factory` 链路：

```
$ rg -n 'create_delayed_sse_response' --glob '*.py' src/
src/app/routes/anthropic.py:247
```

这一点很关键，因为 `DelayedStartStreamingResponse` 的 `finally` 里**已经**调用了 `finish_stream_cleanup(pending, body_iterator)`（`sse.py:189-203`）——也就是说，「响应对象负责结算 body_iterator」这个做法在本仓库已有实现，只是留在了 legacy 链路上，pipeline 链路没有。这与记忆条目「守卫被留在了 legacy 链路上」是同一个形态，这次是第三次击发。

### 1.2 生产链路各跳与其消费方式

从 uvicorn 到 httpx，按外到内：

| 层 | 位置 | 消费下一层的方式 | 会不会关下一层 |
|---|---|---|---|
| uvicorn h11 | `uvicorn/protocols/http/h11_impl.py:205` 设 `spec_version="2.3"` | — | — |
| Starlette `StreamingResponse.__call__` | `starlette/responses.py:258-275` | `(2,3) < (2,4)` → 走 **anyio task group + `listen_for_disconnect`** 分支 | — |
| Starlette `stream_response` | `starlette/responses.py:242-256` | `async for chunk in self.body_iterator`（裸） | **否** |
| `_AccountedStreamingResponse.__call__` | `pipeline_app.py:349-353` | `finally: self._accounting.finish()` | **否**（不碰 `body_iterator`） |
| `_tracked_delivery` | `pipeline_app.py:367-376` | `async for chunk in chunks`（裸） | **否** |
| `stream_delivery` | `stream.py:125-160` | 改动后 `async with aclosing(...)` | **是**（改动新增） |
| `_events_with_ping` | `stream.py:49-99` | 把 `anext(events)` detach 成 `asyncio.ensure_future` task；改动后 `finally` 走 `finish_stream_cleanup(task, events)` | **是**（改动新增） |
| `read_events` | `sse_source.py:73-87` | `async for chunk in chunks`；改动后 `finally: await chunks.aclose()` | **是**（改动新增） |
| `_counted_upstream` | `pipeline_app.py:356-364` | `async for chunk in chunks`（裸） | **否** |
| httpx `Response.aiter_bytes` | `httpx/_models.py:997` | `async for raw_bytes in self.aiter_raw()`（裸） | **否** |
| httpx `Response.aiter_raw` | `httpx/_models.py:1055-1063` | `async for ... in self.stream`；`await self.aclose()` **在循环之后，不在 `finally` 里** | **否**（提前关闭时 `Response.aclose()` 永不执行） |
| httpcore `PoolByteStream.__aiter__` | — | `except BaseException: await self.aclose()` | 是（收得到 GeneratorExit 才行） |

所以严格意义上，**aclose 链并没有闭合**：`_tracked_delivery`、`_counted_upstream`、httpx 的两跳都不关下一层。

### 1.3 那为什么实测是有效的

因为**取消（cancellation）会穿透整条 await 栈**，而这条栈上唯一被人为切断的地方，正是 `_events_with_ping` 把 pull detach 成独立 task 的那一处。

客户端在「上游还在思考、我们正卡在 pull 上」时断连（agent 客户端按 Esc 的典型形态）：Starlette 的 `listen_for_disconnect` 返回 → `cancel_scope.cancel()` → `stream_response` task 被取消 → CancelledError 在 `anext(body_iterator)` 内部投递 → 沿 `_tracked_delivery` → `stream_delivery` → `_events_with_ping` 一路展开。改动前 `_events_with_ping` 的 `finally` 只做 `if task.done() and not task.cancelled(): task.exception()`，**从不取消一个仍在飞的 pull**，于是那个 task 挂住 `read_events` 帧、挂住整条上游栈，永远不完成，连回收器都够不着。改动后 `finish_stream_cleanup` 先结算这个 task 再关闭 `events`，栈才接得上。

**实测（`/tmp/rev-s1-wiring/probe_close_chain.py`，对照快照只差本次改动的两个文件）**：

```
=== AT-PULL — old ===
  pool                          : 1:ACTIVE
    +10 ticks        pool=1:ACTIVE     upstream_saw_disconnect=no tasks=3
    +0.3s            pool=1:ACTIVE     upstream_saw_disconnect=no tasks=3
    +gc.collect()    pool=1:ACTIVE     upstream_saw_disconnect=no tasks=3
    +0.3s            pool=1:ACTIVE     upstream_saw_disconnect=no tasks=3
    +gc.collect()    pool=1:ACTIVE     upstream_saw_disconnect=no tasks=3
    +1.0s            pool=1:ACTIVE     upstream_saw_disconnect=no tasks=3
  leftover tasks     : 3
      <Task pending coro=<<async_generator_asend without __name__>()> ...>

=== AT-PULL — new ===
  pool                          : 0:
    +10 ticks        pool=0:           upstream_saw_disconnect=yes tasks=1
    +0.3s            pool=0:           upstream_saw_disconnect=yes tasks=0
    ...
  leftover tasks     : 0
```

`upstream_saw_disconnect` 是上游 ASGI 应用自己 `await receive()` 收到 `http.disconnect` 的记录——这是端到端证据，不是对 httpx 内部状态的推断。

对照快照的构造（保证只差被评审的两个文件）：

```
cp -r src /tmp/rev-s1-wiring/snap-090935-{old,new}
git show HEAD:src/app/pipeline/delivery/stream.py     > .../snap-090935-old/app/pipeline/delivery/stream.py
git show HEAD:src/app/pipeline/delivery/sse_source.py > .../snap-090935-old/app/pipeline/delivery/sse_source.py
# 并把并行会话新加的 `or "end_turn"` 补回 old 侧，见 F6
diff -rq snap-090935-old snap-090935-new   # 仅 stream.py 与 sse_source.py 不同
```

### 1.4 还有第二种断连形态，改动**没有**覆盖（F2）

上面那条链的前提是「取消落在 pull 上」。还有一种：**客户端不再读了**，于是取消落在 Starlette 的 `await send(...)` 里（`starlette/responses.py:256`），此刻整条生成器栈都停在各自的 `yield` 上，CancelledError 根本到不了它们；Starlette 直接丢下 `body_iterator` 走人，而 `_AccountedStreamingResponse.__call__` 的 `finally` 只调 `accounting.finish()`，也不碰它。

实测（`SLOW_SEND=1`，并在测量前 `del asgi_response, body` 以免探针自己钉住引用）：

```
=== SLOW_SEND — old ===        === SLOW_SEND — new ===
  pool : 1:ACTIVE                pool : 1:ACTIVE
    +10 ticks   pool=1:ACTIVE      +10 ticks   pool=1:ACTIVE
    +0.3s       pool=1:ACTIVE      +0.3s       pool=1:ACTIVE
    +gc.collect() pool=1:ACTIVE    +gc.collect() pool=1:ACTIVE   ← 此处 tasks 从 2 跳到 14
    +0.3s       pool=0:            +0.3s       pool=0:
```

结论：这一形态下**新旧完全一样，都要等循环 GC**（注意是 `gc.collect()` 之后才动，说明引用成环、refcount 放不掉）。真实服务里分代 GC 会自己跑，所以它是「软泄漏」而非永久泄漏，但释放时刻不可控。

**修法本仓库已有范本**，把 legacy 侧 `DelayedStartStreamingResponse` 的做法搬到 `_AccountedStreamingResponse.__call__` 的 `finally` 即可。我在探针里试了（`CLOSE_BODY=1`，等价于在 `finally` 里 `await self.body_iterator.aclose()`）：

```
=== new tree, SLOW_SEND=1              ===   +gc.collect() 之后才 pool=0
=== new tree, SLOW_SEND=1 CLOSE_BODY=1 ===   +0.3s 即 pool=0，且无 stderr 噪声
```

即：**不再依赖循环 GC**。建议连同本切片一起做，或作为紧随的下一个小切片。

---

## 2. 可观测性：时序与取值一个没动

### 2.1 相关代码位置（全部是我实际读到的行）

| 事项 | 位置 |
|---|---|
| `trace.received += len(chunk)` | `pipeline_app.py:362`，在 `yield chunk` **之前** |
| `chain.active_requests.add_bytes(...)` | `pipeline_app.py:363` |
| footer 移除 `active_requests.remove(...)` | `pipeline_app.py:321`（在 `finish()` 内） |
| 完成日志 `_log_completion(..., bytes_out=trace.received)` | `pipeline_app.py:334` |
| `finish()` 幂等哨兵 | `pipeline_app.py:318-320` |
| `finish()` 的两个调用点 | `pipeline_app.py:376`（`_tracked_delivery` 的 `finally`）与 `pipeline_app.py:353`（`_AccountedStreamingResponse.__call__` 的 `finally`） |
| `trace.bytes_in`（`↑`） | `pipeline_app.py:253`，取自 `response.request.content`，与本改动无关 |

说明两点：
- 没有 `trace.sent` 这个字段。日志里的 `↓`/`<NNNB` 取的是 `trace.received`，即 proxy 从上游收到的字节；这与记忆条目「可观测性描述的是上游那一段」一致。
- **History 在流式路径上根本不 finalize**：`executor.py:455-469` 对 `request.stream` 只 `transition(RequestState.STREAMING)` 就 `return`，`history.finalized(context)` 只在非流式与失败分支被调用（`executor.py:123,468,511`）。所以弃流路径上 History 没有可被本改动影响的落库动作——新旧皆然。

### 2.2 取消发生在累加之前还是之后

累加发生在**收到 chunk 的那一刻**（`pipeline_app.py:362`，先加后 yield）。取消投递在 httpx 的 await 点上，即「要么这个 chunk 已经到了并已计数，要么它根本没到」。**不存在少算或多算一个 chunk 的窗口。**

而在 AT-PULL 形态下，新代码的关闭级联跑在 `_tracked_delivery` 的 `finally` **之前**（取消由内向外展开），所以日志写出时的计数就是终值。

我用一个「客户端走了还继续说」的上游把这件事量了出来（`KEEP_SENDING=1`）：

```
=== KEEP_SENDING=1 — old ===
  日志行                        : 200 POST /v1/messages 32ms <490B: upstream stream ended without a terminal event
  trace.received at log time    : 490
  trace.received 1.6s later     : 1290  (drift=800)

=== KEEP_SENDING=1 — new ===
  日志行                        : 200 POST /v1/messages 32ms <490B: upstream stream ended without a terminal event
  trace.received at log time    : 490
  trace.received 1.6s later     : 490   (drift=0)
```

读法：**两侧日志数字完全相同（490B），没有任何一侧报错**。差别在于旧代码那个孤儿 pull 在日志写完之后又吞了 800 字节进一个再没人读的记录里，同时连接一直开着。`add_bytes` 对已移除的 request id 是静默 no-op（`active_requests.py:96-98`），所以 footer 不会诈尸。

### 2.3 逐项对账

| 观测面 | AT-PULL 旧 | AT-PULL 新 | AT-YIELD 旧 | AT-YIELD 新 |
|---|---|---|---|---|
| `accounting.done` | True | True | True | True |
| footer 中该请求 | 已移除 | 已移除 | 已移除 | 已移除 |
| 完成日志条数 | 1 | 1 | 1 | 1 |
| 日志 `<NNNB>` | 490 | 490 | 490 | 490 |
| `__call__` 墙钟 | 0.034s | 0.034s | 0.034s | 0.033s |
| 日志写出后计数漂移 | +800 | 0 | 0 | 0 |

**可观测性零变化。**（顺带：日志里那句 `upstream stream ended without a terminal event` 和 `status=fail` 来自并行会话新加的 `pipeline_app.py:330-333`，两侧都有，与本改动无关，见 F6。）

---

## 3. 新引入的用户可见行为

### 3.1 正常 / 上游报错 / 上游超时：客户端看到的字节完全一致

`/tmp/rev-s1-wiring/probe_outputs.py` 把六类请求逐帧 dump 出来，在只差本改动的两份源码上跑，`diff` 结果：

```
$ diff outputs-old.txt outputs-new.txt
1c1
< stream.py under test: .../snap-090935-old/...
---
> stream.py under test: .../snap-090935-new/...
64c64
<     upstream_closed   : []                （abandon-at-yield）
---
>     upstream_closed   : ['aband-y']
69,70c69,70
<     upstream_closed   : ['aband-y']       （abandon-at-pull，旧侧这里出现的是上一例被 GC 顺带关掉的痕迹）
<     leftover tasks    : 1
---
>     upstream_closed   : ['aband-p']
>     leftover tasks    : 0
```

也就是说 `success` / `upstream-error` / `upstream-timeout` / `truncated` / `ping` / `synth-preamble` 六类的**输出字节逐帧相同，抛出的异常也相同**：

- `success`：9 帧，`message_delta{stop_reason:"end_turn"}` + `message_stop`，两侧一致。
- `upstream-error`：客户端已收 4 帧，随后 `RuntimeError: upstream read failed` 原样向外传播——**没有被 cleanup 异常顶替，也没有被吞掉**。这是新 `finally` 里那段异常优先级代码的关键验收点，实测通过。
- `upstream-timeout`：同上，`StreamIdleTimeoutError: No upstream stream item received for 60s` 原样传播。
- 状态码：流式响应的状态码在 header 发出时就定死了（`pipeline_app.py:284` 用 `response.status_code`），本改动不触及。
- 终止帧：见 `success` / `truncated` 两例，一致。

另外全量回归：`uv run pytest -q -p no:randomly` → **1390 passed, 2 skipped**。`ruff check`（三个文件）全过；`pyright`（三个文件）0 errors。

### 3.2 但 operator 的 stderr 上多了一条（F1）

在「客户端不读了」（AT-YIELD）形态下，改动**确定性地**产生：

```
Task exception was never retrieved
future: <Task finished name='Task-16' coro=<<async_generator_athrow without __name__>()>
        exception=RuntimeError('aclose(): asynchronous generator is already running')>
RuntimeError: aclose(): asynchronous generator is already running
```

重复计数（每次都是全新进程、同一探针）：

```
old: 'already running' 出现在 0/5 次运行（SLOW_SEND，AT-YIELD）
new: 'already running' 出现在 5/5 次运行（SLOW_SEND，AT-YIELD）
old: 同一消息 0/3 次（AT-PULL）
new: 同一消息 0/3 次（AT-PULL）
```

**判据权重：强到可以据此行动**——5/5 vs 0/5，单一变量对照，两侧源码只差本改动的两个文件。

开 `PYTHONASYNCIODEBUG=1` 拿到的 `source_traceback` 指向 `asyncio/events.py:94`，即**异步生成器终结器钩子**调度的那个 `aclose()`；配合我在 `/tmp/rev-s1-wiring/snap-trace` 里加的打点，顺序是：

```
[trace] _events_with_ping finally, task=None, exc=GeneratorExit()
[trace] read_events finally, closing=True
[trace] read_events closed chunks
RuntimeError: aclose(): asynchronous generator is already running    ← 发生在这之后
```

即：显式关闭级联跑完之后，终结器又对同一条链上某个生成器发起了一次 `aclose()`，撞上「已在运行」。

**机制未完全隔离**：我写了两级和三级的最小复现（`/tmp/rev-s1-wiring/probe_aclosing_race.py`），**都没能复现**（0/3、0/3）。所以「`aclosing` 与终结器双重关闭」这个解释目前只是与观测相符的假说，**不足以据此设计修法**。可以据此行动的只有现象本身。想复现直接跑：

```
SLOW_SEND=1 PYTHONPATH=/tmp/rev-s1-wiring/snap-090935-new \
  .venv/bin/python -u /tmp/rev-s1-wiring/probe_close_chain.py
```

为什么这条值得当 major 而不是噪声：`_events_with_ping` 自己的注释（`stream.py:69`）花了整段解释为什么不用 `wait_for(shield(...))`——理由正是「会在 operator 的 stderr 上每个超时的 pull 打一条 `StopAsyncIteration exception in shielded future`」。同一份文件用同样的标准衡量，这条新噪声属于它自己拒绝过的东西。

顺带一提：F2 里那个 `CLOSE_BODY` 实验**同时消掉了这条噪声**（那次运行的输出里没有 `already running`）。这是一条线索，不是结论——我只跑了 1 次，没做重复计数。

---

## 4. 同类断点清点

`src/app/` 全量 `async for`（20 处），按是否在 pipeline 生产链路上分类：

| 位置 | 在本链路上？ | 是否同类泄漏 | 判定 |
|---|---|---|---|
| `server/pipeline_app.py:373`（`_tracked_delivery`） | **是** | 部分 | **是同类断点，但单独修它无用**。前提：只有当有人对 `_tracked_delivery` 调 `aclose()` 时它才起作用，而 Starlette 不会调。它必须与 F2（`_AccountedStreamingResponse` 关 `body_iterator`）**成对**才有意义 |
| `server/pipeline_app.py:361`（`_counted_upstream`） | **是** | 是 | **是同类断点**。它是 `read_events` 关闭级联的终点，再往下（httpx `aiter_bytes`）就断了。前提：修它能把「最后一跳交给 GC」缩短一跳，但因 httpx 内部还有两跳（`aiter_bytes`→`aiter_raw`→stream，见 1.2），单靠它拿不到确定性 |
| `pipeline/delivery/stream.py:133` | 是 | 否 | 本次已改为 `aclosing` |
| `pipeline/delivery/sse_source.py:75` | 是 | 否 | 本次已加 `finally` 关闭 |
| `streaming/sse.py:34`（`passthrough_bytes`） | 否（legacy） | 否 | 自带 `finally` 关闭 |
| `streaming/keepalive.py:177`（`keepalive_stream`） | 否（legacy） | 否 | 自带 `finally: await inner.aclose()` |
| `streaming/idle_timeout.py:24`、`streaming/buffered_retry.py:14`、`streaming/openai_sse.py:9` | 否 | — | 只被 `routes/anthropic.py`、`routes/gemini.py`、`delivery/responses_anthropic_stream.py` 使用，均为 legacy |
| `routes/{anthropic,gemini,protocol_history,responses_ws}.py`、`delivery/responses_anthropic_stream.py`（共 9 处） | 否 | — | legacy 链路，本次不评 |

**结论：本链路上只剩两个同类断点，`pipeline_app.py:361` 与 `:373`，且都不构成当前的泄漏**——AT-PULL 形态靠取消穿透绕过了它们，AT-YIELD 形态则是被 F2 那个更靠外的缺口盖住了。真正决定 AT-YIELD 能否确定性关闭的是 F2，不是这两处。

### 4.1 一个顺带发现（不在本次范围，供裁决）

pipeline 流式路径上**没有上游 idle timeout**。`with_idle_timeout` 只在 `routes/anthropic.py:221` 被接上，pipeline 侧只有 `_events_with_ping` 的 ping（没有 idle 判据）。后果：上游连上了却永远不说话时，只要客户端还在，这个请求可以无限期挂着。这与本改动无关，改动前后都如此，但它和「谁来关上游」是同一个问题域，**建议记为 deferred 项由用户裁决**，不要我在这里静默塞进任何切片。

---

## 5. 建议的处置顺序

1. **保留本改动**。它解决了主要形态（Esc 弃流）下的永久泄漏，端到端有证据，回归全绿，静态检查全过。
2. **F1 先查清再动手**。现象确定（5/5 vs 0/5），机制未隔离。不要凭我的假说直接改；先用探针复现，确认是哪个生成器被关了两次。在没查清之前，不要用「加个 try/except 吞掉 RuntimeError」的方式盖住它——那正是 `never-swallow-errors` 要防的。
3. **F2 单独成一个小切片**：把 `DelayedStartStreamingResponse.stream_response` 的做法搬到 `_AccountedStreamingResponse.__call__` 的 `finally`。实测有效，且很可能顺带解决 F1（线索，非结论）。
4. **F4 的测试补强，与 F2 一起做**：等 `_AccountedStreamingResponse` 关 `body_iterator` 之后，再补一个走完整生产接线（含 `_counted_upstream` + 真 httpx 响应）的用例才有意义。现在补只会固化一个仍然要等 GC 的行为。
5. **F3 记为已知限制**：只要没人调 `Response.aclose()`，`response.is_closed` 就恒为 `False`。当前没有任何代码读它，所以不构成缺陷；但任何未来想用 `is_closed` 判断上游状态的代码都会被它骗到，值得在 `stream_delivery` 或 `pipeline_app` 的注释里留一句。

---

## 附：探针清单

| 文件 | 回答的问题 |
|---|---|
| `/tmp/rev-s1-wiring/probe_close_chain.py` | 生产接线 + 真 Starlette 断连分支：连接释放了吗、什么时候、可观测性有没有变。支持 `SLOW_SEND`（AT-YIELD 形态）、`KEEP_SENDING`（计数漂移）、`CLOSE_BODY`（F2 的修法验证） |
| `/tmp/rev-s1-wiring/probe_layers.py` | 从顶端 `aclose()` 时，关闭能穿到第几跳 |
| `/tmp/rev-s1-wiring/probe_httpx.py` | 纯 httpx：关掉 `aiter_bytes()` 到底释放了什么（结论：连接会走，但 `Response.aclose()` 不跑） |
| `/tmp/rev-s1-wiring/probe_outputs.py` | 六类请求的逐帧输出与抛出的异常，新旧对拍 |
| `/tmp/rev-s1-wiring/probe_aclosing_race.py` | F1 的最小复现尝试（**未复现**） |
| `/tmp/rev-s1-wiring/snap-090935-{old,new}` | 只差被评审两个文件的对照快照 |
| `/tmp/rev-s1-wiring/snap-trace` | 在 new 快照上加了关闭级联打点 |

环境：Python 3.14.2、starlette 0.52.1、fastapi 0.129.0、httpx 0.28.1、uvicorn 0.40.0。

---

## 附：给主会话的范围提示（F6）

评审进行中，并行会话改动了工作树，`git diff --stat src/` 从 2 个文件变成 6 个：

```
 src/app/config/bundled-config.yaml      |  21 ++++++
 src/app/observability/request_log.py    |  12 ++++
 src/app/pipeline/delivery/assembler.py  |   4 +-
 src/app/pipeline/delivery/sse_source.py |  23 +++---
 src/app/pipeline/delivery/stream.py     | 123 +++++++++++++++++--------
 src/app/server/pipeline_app.py          |  21 ++++--
```

其中两处与我拿到的任务描述不符，需要主会话确认归属：

1. `stream.py` 现在还包含一处 `stop_reason=terminal.stop_reason or "end_turn"`（连同一段自称 KNOWN SPEC VIOLATION 的注释），与 `assembler.py` 把 `Terminal.stop_reason` 默认值从 `"end_turn"` 改成 `""` 是**耦合的一对**。这不属于「弃流关闭确定性」这个切片，我按范围没有评它——但它现在混在同一个未提交 diff 里，squash 时会一起进去。
2. `pipeline_app.py:322-333` 的 `finish()` 改写（`terminal.seen` 为假时置 `trace.failed` 并写 detail）同样不在我的评审范围内。

我第一轮的 old/new 对拍因此被污染过一次（`truncated` 这一类的 `stop_reason` 出现了假差异），已重建快照并把那处 `or "end_turn"` 补回 old 侧后重测，第 3 节引用的所有 diff 都出自重测。

---

# F1/F2 修复复核（2026-08-20，独立验证）

## 复核结论

**F1 已消除，F2 的方向与落法正确，v1 足够、不必上 v3。但这次修复引入了一处新的回归：`await self._content.aclose()` 一旦抛出，`self._accounting.finish()` 就不会执行，请求永久卡在 footer 里且没有完成日志——正是这个类的 docstring 声明自己要防的那个失败。同时它会用 cleanup 异常顶替掉原始异常。** 修法只要把那两行改成 `try/finally` 即可，不动其余任何东西。

Blocker：0。

### 复核基准与树指纹

复核对象是我自己构造的单变量对，只回退你落的那一处：

```
$ diff v2-093838-nofix/app/server/pipeline_app.py v2-093838-fix/app/server/pipeline_app.py
361a362
>         self._content = content
369a371
>             await self._content.aclose()
```

复核完成后工作树又被并行会话动过（`pipeline_app.py` md5 `e7efe784…` → `8878f884…`，`stream.py` `f4e353b6…` → `a3e35489…`）。我逐一对过：

- `diff v2-093838-fix/app/server/pipeline_app.py src/app/server/pipeline_app.py` → **完全相同**，本节结论适用当前树。
- `stream.py` 的变动经 AST 比对为**纯注释改动**（`ast.dump` 相等），不影响本节任何判据。

我全程未改动仓库；`git status --short src/ tests/` 列出的 10 个文件全部是你与并行会话的改动，探针与快照都在 `/tmp/rev-s1-wiring/`。

---

## 1. 噪声是否真的消失

重复 5 次，每次全新进程，**带假绿护栏**（要求每次运行都跑到 `leftover tasks` 那一行，并扫描 `NameError|AttributeError|TypeError|ImportError|SyntaxError`）：

```
nofix (SLOW_SEND / at-yield): noise=5/5  completed_runs=5/5  probe_errors=0
fix   (SLOW_SEND / at-yield): noise=0/5  completed_runs=5/5  probe_errors=0
```

护栏是必要的：我这轮自己也被咬了一次——第一版探针把 `__call__(scope, receive, send)` 的后两个参数写反，两个变体都吐 `TypeError` 且**表面上看起来「两侧一致」**。修正参数顺序后才拿到下面的数据。你说你被 `NameError` 假绿咬过，是同一类。

**F1 确认消除。**

## 2. 收敛时机复核，以及对我原报告 F2 措辞的更正

```
=== SLOW_SEND=1 (at-yield) — nofix ===        === SLOW_SEND=1 (at-yield) — fix ===
  +10 ticks     pool=1:ACTIVE                   +10 ticks     pool=1:ACTIVE
  +0.3s         pool=1:ACTIVE                   +0.3s         pool=0:      ← 未经 gc.collect()
  +gc.collect() pool=1:ACTIVE  ← 噪声在此处      +gc.collect() pool=0:
  +0.3s         pool=0:                         +0.3s         pool=0:

=== AT-PULL — nofix ===                       === AT-PULL — fix ===
  __call__ 返回即 pool=0:                        __call__ 返回即 pool=0:      （两侧相同）
```

你的观察成立，而且它更正了我原报告的一处措辞。我在 F2 里写「实测能把它变成不依赖 `gc.collect()`」是对的，但我用来支撑 F2 的 `probe_layers.py` / `probe_httpx.py` 是**自己调 `aclose()`** 的，而生产里在你这次改动之前没有任何人调——所以「从不关闭 → aclose() 即关」那组数据描述的是一个当时不存在的调用点。

**据此更正 F2 的定级**：它不是「可选的紧随切片」，它是让 S1 在生产的 at-yield 形态下**真正生效、并且不净增噪声**的那一半。S1 单独落地时，at-yield 形态相对基线是「释放时机不变 + 多一条 stderr 噪声」，净负。两者合起来才是净正。

对应地，原报告第 5 节的处置顺序第 3 条（「F2 单独成一个小切片」）应读作「F2 与 S1 必须同批交付」。

## 3. 新发现 R1（major）：`aclose()` 抛异常时记账被跳过，且原始异常被顶替

`/tmp/rev-s1-wiring/probe_response_contract.py` 用真实的 `_AccountedStreamingResponse` + `_StreamAccounting` + `_Trace`，配一个可控 body，走完 `finally` 必须扛住的每一种形状（`_log_completion` 用探针本地 monkeypatch 计数，未改仓库）：

| 场景 | nofix | fix |
|---|---|---|
| `success`（body 自然耗尽） | raised=none, finish_done=True, log=1, footer=[] | **同** |
| `start-send-fails`（body 从未被迭代） | raised=OSError, finish_done=True, log=1, footer=[] | **同**（body cleanup 未运行，正确） |
| `body-raises`（上游报错） | raised=RuntimeError: upstream read failed, finish_done=True, log=1 | **同**（原始异常保住） |
| `call-cancelled`（`__call__` 被取消一次） | raised=CancelledError, finish_done=True, log=1, footer=[] | **同** |
| `call-cancelled-twice`（模拟 anyio 每个检查点重投） | raised=CancelledError, finish_done=True, log=1, footer=[] | **同** |
| `finish-idempotent`（手动再调两次） | 1 → 1 | **同** |
| **`cleanup-raises-on-close`** | raised=none, **finish_done=True, log=1, footer=[]** | raised=ValueError: cleanup blew up, **finish_done=False, log=0, footer=['rid']** |
| **`primary+cleanup-both-raise`** | **raised=OSError: broken pipe**, finish_done=True, log=1 | **raised=ValueError: cleanup blew up**, finish_done=False, log=0, footer=['rid'] |

两条后果：

1. **请求永久卡在 footer 里，且完成日志一行都没有。** 这正是 `_AccountedStreamingResponse` 的 docstring 明写自己存在的理由：「the request would sit in the footer for the life of the process with its clock climbing and no log line ever written」。把 `await` 放到 `finish()` 前面，等于把这个保证交还给了被关闭对象的 cleanup。
2. **原始异常被 cleanup 异常顶替。** ASGI 服务器看到的是 `ValueError: cleanup blew up`，而真正发生的 `OSError: broken pipe` 消失了。

**当前是否可达**：现网链路上 `self._content` 是 `_tracked_delivery`，它自己的 `finally: accounting.finish()` 会在 `aclose()` 的展开过程中先跑掉，所以今天 `finish()` 实际上还是会执行。**这是一个潜伏的契约破损，不是当前的活故障**——判据权重：足以据此修正，但不足以称之为线上事故。它会在下面任一情况下变成活的：`_tracked_delivery` 的 `finally` 本身抛出；`stream_delivery` / `_events_with_ping` 的清理异常改为向外传播（`stream.py:99` 的 `raise cleanup_error` 已经是这个形状，只是目前被 `_tracked_delivery` 的裸 `async for` 挡住）；或者以后有人在 `_content` 与 `_tracked_delivery` 之间再插一层。

**建议修法**（保留你的顺序意图，只补一道 `finally`）：

```python
try:
    await self._content.aclose()
finally:
    self._accounting.finish()
```

这不改变正常路径的任何行为（上表其余七行全部不动），只是让「记账一定发生」重新成为无条件的。至于原始异常被顶替，见下一条。

## 4. 与 legacy 范本 `DelayedStartStreamingResponse` 的形状对照

你的形状与范本在四点上一致、一点上不一致：

| 维度 | `DelayedStartStreamingResponse`（`sse.py:189-203`） | 你落的 v1 | 判定 |
|---|---|---|---|
| 关闭发生在 `finally`、在框架之外 | 是 | 是 | 一致 |
| 关闭的对象 | `body_iterator` | `self._content` | 等价（`StreamingResponse.__init__` 对 AsyncIterable 直接令 `body_iterator = content`，异步生成器的 `__aiter__` 返回自身）。存 `self._content` 换来的是类型更干净，同意 |
| 结算在途的 pull task | `finish_stream_cleanup(pending, …)` | 无 | **不适用**：Starlette 原版 `stream_response` 用裸 `async for`，这一层根本没有 detached pull |
| 清理期间被重新投递的取消 | `cleanup_cancellation` 显式延后，保证清理跑完 | 裸 `await`，理论上可被打断 | 实测未复现（`call-cancelled-twice` 两侧一致），**结构上仍是弱于范本的一点，但没有可据此行动的证据** |
| **清理异常 vs 原始异常的优先级** | `raise primary from cleanup_error`，原始异常始终是对外那一个 | 无，cleanup 异常直接顶替 | **这就是范本处理了而 v1 漏掉的情形**，实测见 R1 第 2 条 |

也就是说，R1 的两条后果里，第一条（记账被跳过）是 v1 独有的（范本没有记账职责，不存在这个问题），第二条（异常被顶替）是范本明确处理过而 v1 没有的。如果只想改一处，`try/finally` 解决第一条；要连第二条一起，就照范本用 `sys.exception()` 那套优先级阶梯。**我的偏好是先只做 `try/finally`**：第一条是无条件的正确性问题，第二条在当前链路上还没有已知的触发者，套整套阶梯会把这个类从 4 行变成 14 行，与它承担的职责不成比例。

## 5. 可观测性逐项对账：没有任何字段因「先关后记账」而改变

完成日志行，三种形态、两个变体，逐字相同（只把毫秒数归一化）：

```
AT-PULL        nofix  POST /v1/messages NNms <490B: delivery stopped before upstream finished  status=fail
AT-PULL        fix    POST /v1/messages NNms <490B: delivery stopped before upstream finished  status=fail
SLOW_SEND=1    nofix  POST /v1/messages NNms <490B: delivery stopped before upstream finished  status=fail
SLOW_SEND=1    fix    POST /v1/messages NNms <490B: delivery stopped before upstream finished  status=fail
KEEP_SENDING=1 nofix  POST /v1/messages NNms <490B: delivery stopped before upstream finished  status=fail
KEEP_SENDING=1 fix    POST /v1/messages NNms <490B: delivery stopped before upstream finished  status=fail
```

逐项：

| 观测面 | 结论 | 依据 |
|---|---|---|
| 完成日志行（含 `detail`、`status`） | 不变 | 上表 |
| `trace.received` / `↓` | 不变，`<490B`；日志写出后漂移两侧均为 0 | `KEEP_SENDING=1` 两侧 `drift=0` |
| `trace.sent` | 不存在此字段；`↑` 取 `trace.bytes_in`（`pipeline_app.py:253`），与本次改动无交集 | 读码 |
| footer 移除时机 | 不变 | 上表 `footer=[]`（除 R1 的两个场景） |
| History 落库 | 不变，因为流式路径**根本不 finalize**：`executor.py:455-469` 对 `request.stream` 只 `transition(RequestState.STREAMING)` 就 return | 读码 |
| `finish()` 幂等 | 成立，额外手调两次仍是 1 行日志 | 探针 `finish-idempotent` |

**为什么「先关后记账」不改变任何取值**：`finish()` 读的是 `assembler.terminal`、`trace.received`、`accounting.drained`。body 被迭代过时，`_tracked_delivery` 自己的 `finally` 会在 `aclose()` 展开途中先调到 `finish()`，此时的状态与 nofix 里外层直接调 `finish()` 时完全相同——关闭级联已经取消了在途 pull，不会再有事件进入 assembler、也不会再有字节进入计数。body 从未被迭代时，`aclose()` 什么都不跑，外层 `finish()` 就是第一次，与 nofix 逐字相同（探针 `start-send-fails` 两侧一致）。

**R2（minor，措辞更正）**：你给出的顺序理由「完成日志写在上游真正释放之后而不是仍开着的时候」在 at-yield 形态下**不成立**。`_tracked_delivery` 的 `finally` 在 `aclose()` 展开途中就把日志写掉了，而上游真正离开连接池要到 `+0.3s`（见第 2 节表格：`__call__` 早已返回，pool 还是 `1:ACTIVE`）。顺序本身无害，但这条理由目前描述的不是实际发生的事，注释值得改一句；而且正是这个顺序造成了 R1 的暴露面。

## 6. v2 / v3 拆分变体复核

我自己构造了四个变体（各 5 次全新进程，SLOW_SEND / at-yield）：

```
nofix: runs_with_noise=5/5  total_noise_lines=10  completed=5/5
fix  : runs_with_noise=0/5  total_noise_lines=0   completed=5/5
v2   : runs_with_noise=5/5  total_noise_lines=20  completed=5/5   ← 每次 4 条，是 nofix 的两倍
v3   : runs_with_noise=0/5  total_noise_lines=0   completed=5/5
```

**你的判断成立**：v2（只在 `_tracked_delivery` 用 `aclosing`）确实更糟，v3 相对 v1 在这条判据上没有增益。**只落 v1 是对的**，不必顺手补 `_tracked_delivery`。

顺带回答我原报告第 4 节留的那个问号：`pipeline_app.py:373` 的裸 `async for` 现在有了实测判据——补上它**有害**（噪声翻倍），所以那一条从「同类断点，待定」改为**明确不修**。

## 7. 还有没有残留的等回收器的形态

有一处，且不可能靠生成器关闭消掉：

- `_counted_upstream`（`pipeline_app.py:361`）→ httpx `Response.aiter_bytes` → `aiter_raw` → `PoolByteStream`，共三跳裸 `async for`，其中 httpx 的 `aiter_raw`（`httpx/_models.py:1055-1063`）把 `await self.aclose()` 写在循环**之后**而不是 `finally` 里，所以提前关闭时 `Response.aclose()` 永不执行。
- 可观测的后果：修复后 at-yield 形态下 `__call__` 返回时 pool 仍是 `1:ACTIVE`，要到 `+0.3s` 才归零；`response.is_closed` 在**所有**变体里恒为 `False`。
- 但性质已经变了：修复前必须等**循环 GC**（`gc.collect()` 之前一直 ACTIVE），修复后只需**引用计数**（未经任何 `gc.collect()` 就在 `+0.3s` 归零）。这是本次修复真正买到的东西。
- 想拿到「返回即释放」，唯一的路是 `await response.aclose()`（`probe_httpx.py` 实测：`is_closed=True, pool=0`，另外两种关法都做不到）。那需要把 httpx 响应对象一路带到交付层，是一个独立的设计决定，**不建议塞进本切片**，建议记为 deferred 交用户裁决。

## 8. 回归与静态检查（当前树，指纹 `8878f884…`）

```
1394 passed, 2 skipped in 106.40s
ruff check src/app/server/pipeline_app.py src/app/pipeline/delivery/{stream,sse_source}.py  → All checks passed!
pyright src/app/server/pipeline_app.py                                                       → 0 errors, 0 warnings
```

（你报的是 1391，我这轮是 1394——期间并行会话又加了测试，不是分歧。）

现有测试**没有**覆盖 R1 那两个场景。如果采纳 `try/finally`，值得配一个直接的用例：body 的 cleanup 抛出时，`finish()` 仍然发生。判据就是上表 `cleanup-raises-on-close` 那一行，探针里已经有现成的 `bad_cleanup_body`。

## 9. 处置建议

1. **保留 v1，与 S1 同批交付**（第 2 节：分开落，S1 那一半在 at-yield 形态下是净负）。
2. **R1 必修**：`_AccountedStreamingResponse.__call__` 的 `finally` 改成 `try: await self._content.aclose() finally: self._accounting.finish()`。四行改动，不影响任何正常路径。
3. **R2 顺手改注释**：删掉或改写「完成日志写在上游真正释放之后」那句理由，它在 at-yield 形态下与实测不符。
4. **`_tracked_delivery` 明确不动**（第 6 节，v2 实测有害）。
5. **deferred 交用户裁决**：`await response.aclose()` 才能拿到确定性释放（第 7 节）；以及原报告 4.1 提的 pipeline 流式路径无上游 idle timeout。

### 复核用探针（新增）

| 文件 | 回答的问题 |
|---|---|
| `/tmp/rev-s1-wiring/probe_response_contract.py` | `_AccountedStreamingResponse.__call__` 的 `finally` 在八种形状下的契约（R1 出自这里） |
| `/tmp/rev-s1-wiring/v2-093838-{nofix,fix,v2,v3}` | 只差被复核那一处的四个单变量快照 |
