# 独立评审：优雅关闭准入闸修复（`begin_draining`）

评审对象：主工作树未提交改动，范围严格限于 `src/app/lifecycle/{adapter,listener,standalone}.py`、`src/app/cli.py`、`tests/integration/test_standalone_lifecycle.py`、`tests/integration/test_standalone_process.py`、`tests/unit/test_lifecycle_cleanup.py`。
评审日期：2026-08-20。评审者：并发与生命周期方向的独立评审 agent。只读评审，未修改任何源码或测试。
权威规范：`docs/.human-controlled/lifecycle.md` 第 18-26 行（关停三档语义）、第 78-82 行（`QUIESCE`／`RESUME`／`TERMINATE` 运行时信号语义）。

## 结论

**blocker 0 条。修复的核心机制是对的，第一档不截断在途请求这一条我用实测证实了，不是靠读文档。** 主要问题集中在两处：`both` 模式下 `resume_accepting()` 清不掉新引入的拒绝态（滚动路径的潜伏缺陷），以及整套测试对「第一档不截断已开始的响应」这一旗舰不变量零分辨力（我做了变异，84 条测试全绿而 SSE 流被截在第 2 块）。

严重度分布：blocker 0，major 2，minor 7，nit 5。

## 方法与证据基线

本报告的判断分三种来源，逐条会标注：

1. **上游源码**：`.venv/lib/python3.14/site-packages/uvicorn/`（uvicorn 0.40.0），h11 0.16.0，wsproto 1.3.2。本环境**未安装 httptools 与 websockets**，所以 `http="auto"` 解析为 `H11Protocol`、`ws="auto"` 解析为 `WSProtocol`（`protocols/http/auto.py`、`protocols/websockets/auto.py`）。
2. **离树探针**：写在 `/tmp` 下，复刻 `tests/integration/test_standalone_lifecycle.py` 的 harness，不触碰仓库任何文件。`/tmp/probe_drain.py`、`/tmp/probe_sse_truncation.py`。
3. **离树变异**：以 pytest 插件形式在 `PYTHONPATH=/tmp` 下猴补 `UvicornListenerAdapter`，同样不改仓库。`/tmp/mut_no_refusal.py`、`/tmp/mut_no_close.py`、`/tmp/mut_hard_close.py`、`/tmp/mut_cut_started.py`。

基线：`tests/integration/test_standalone_lifecycle.py`、`test_standalone_process.py`、`tests/unit/test_lifecycle_cleanup.py`、`tests/integration/test_listener_quiesce_resume.py`、`tests/unit/test_shutdown_reporting.py` 共 53 条，在当前树上全绿（23.5s）。`ruff check` 在五个受审文件上干净。工作树里同时有其他会话的在飞改动，上述文件不在其中。

---

## 问题 1：并发与竞态

### 1.1 死锁／重入 —— 没有问题（置信度：高）

`begin_draining()` 与 `shutdown_lifespan()` 取同一把 `_operation_lock`，但二者在 `serve()` 里是**严格串行**的：`begin_draining` 在 `async with` 块结束时释放锁再返回，`shutdown_lifespan` 稍后由 `_finalize()` 调用。关键在于 `shutdown_lifespan` 自身的结构（`adapter.py:207-226`）——它把最长的等待 `await self.wait_drained(drain_timeout)` 放在**锁外**（第 216 行），锁只覆盖前后两段同步操作。所以即使排空是无界的，也不会有任何人被这把锁挡住。

也不存在重入：`begin_draining` 内部只调用同步方法（`_refuse_admission_locked`、`connection.shutdown()`），没有任何一条路径会再次进入取锁的方法。

### 1.2 与 `_run_ticks` 的交互 —— 没有问题（置信度：高）

我读了 `uvicorn/server.py:233-260` 的 `on_tick`。它只做三件事：每秒刷新 `default_headers`、调 `callback_notify`（本项目未配置）、根据 `should_exit`／`limit_max_requests` 返回是否应退出。**它不碰 `_operation_lock`、不碰 `_admission_open`、不碰 `server_state.connections`**，而且适配器丢弃它的返回值。`limit_max_requests` 在本项目从未配置（`rg limit_max_requests src/` 无命中）。所以 ticker 与准入闸完全解耦。

### 1.3 与 `cancel_requests` 的交互 —— 没有问题（置信度：高，且我自己做了正向对照）

`begin_draining` 不 cancel 任何任务，`_descend` 只在 `INTERRUPTING`／`FINALIZING` 档 cancel。我做了反向变异 `/tmp/mut_hard_close.py`（把 `connection.shutdown()` 换成无条件 `transport.close()`，即让第一档真的去切连接），结果**既有的两条第一档守卫立刻变红**：

```
FAILED test_the_first_signal_stops_accepting_but_lets_a_request_finish - assert b'200 OK' in b''
FAILED test_a_restart_signal_alone_never_interrupts_the_request      - assert b'200 OK' in b''
```

这证明「第一档不得中断在途请求」这条契约**确实有分辨力**（对未开始写响应的请求而言）。报告里声称的另一个变异（让 `begin_draining` 顺手 `cancel_requests()` → 三条守卫全红）与我这条独立观测方向一致，我采信。

### 1.4 丢事件 —— 现状没有问题，但有一个不可达的隐患（置信度：高）

`asyncio.Event` 的语义决定了一个关键点：`set()` 会 resolve 所有等待中的 future，随后的 `clear()` **不会**把它们撤回。所以一个已经被唤醒但尚未被调度的 `gated_app` 一定会往下走，读到它醒来那一刻之后的 `self._admission_refusal`。

由此推出一个理论上的丢事件路径：拒绝态被置位并唤醒了等待者 → 在等待者恢复执行之前，有人调用了会执行 `_close_registrations_locked(ListenerState.STOPPED)` 的 `stop_accepting()` → `_admission_refusal` 被清成 `None`（`adapter.py:310-312`）→ 该请求于是被**正常服务**，而不是被拒绝。

**这条路径当前不可达**：`serve()` 里 `stop_accepting()` 排在 `begin_draining()` 之前，之后再没有任何调用点会用 `STOPPED` 走 `_close_registrations_locked`；`shutdown_lifespan` 传的是 `STOPPING`（第 213 行），不清拒绝态。这个设计细节是对的，值得肯定。记录在此是因为它是一个**隐式的顺序契约**，代码里没有任何东西阻止后来者把 `stop_accepting()` 挪到 `begin_draining()` 之后。

### 1.5 `gated_app` 闭包的读法不对称 —— 今天无害，明天危险

**严重度：nit。置信度：高（读法本身），中（未来风险的判断）。**

`admission_open` 是按值捕获的局部变量，`self._admission_refusal` 是按 `self` 读的。我 grep 确认 `_admission_open` 在整个 `src/` 里**只在 `adapter.py:69` 被绑定过一次**，此后只有 `.set()`／`.clear()`，从不重绑。所以两种读法当前语义等价，**不是缺陷**。

但它是一个值得说出来的脆弱点，理由不是「风格不一致」，而是有第二个文件依赖同一个隐式契约：`listener.py:216` 和 `listener.py:235` 直接抓 `self._adapter._admission_open` 并对它 `set()`／`clear()`。于是「这个 Event 对象永远不许被重新绑定」成了一条**跨文件、无处声明、无测试的不变量**。一旦有人在 `_register_dormant_locked` 里加一句 `self._admission_open = asyncio.Event()`（这是重置一个闸口时最自然的写法），`gated_app` 会继续等旧对象，`FirstByteRoutingAdapter` 会去 set 新对象，结果是**永久静默挂起**，且症状与本次修复的 bug 完全同形。

建议（非阻塞）：在 `gated_app` 里也写 `await self._admission_open.wait()`，让一个不变量的两半走同一种读法；或者在 `_admission_open` 的定义处写明「此对象不得重绑，`listener.py` 与 `gated_app` 都持有它」。

---

## 问题 2：`stop_accepting()` 清闸、`begin_draining()` 再置位在 `both` 模式下的顺序

### 2.1 顺序本身成立 —— 没有问题（置信度：高，有实测）

`FirstByteRoutingAdapter.begin_draining()` 的注释断言「`stop_accepting` 已经处理了本路由器自己那一半——还在等第一个字节的 socket」，我核对了源码，**这个断言准确**：`listener.py:224-240` 依次移除 accept reader、关闭 accept socket、关闭 `_pending_sockets` 里所有待路由的 socket、cancel 并 gather 所有 `_routing_tasks`。所以到 `begin_draining()` 执行时，不存在「已 accept 但尚未交给被包装适配器」的中间态连接。转发给内层适配器去数 `server_state.connections` 是完备的。

实测（`/tmp` 探针，直接读私有状态）：

```
armed:     refusal=None                      open=True
quiesced:  refusal=None                      open=False
drained(0):refusal='server is shutting down'  open=True
```

`both` 模式下清闸再置位的顺序正确生效。

### 2.2 `FirstByteRoutingAdapter.stop_accepting()` 会在拒绝态已置位时再次清掉事件

**严重度：minor。置信度：高（行为已实测），中（不可达性的判断）。**

`FirstByteRoutingAdapter.shutdown_lifespan()`（`listener.py:268-271`）第一件事就是 `await self.stop_accepting()`。此时路由器状态是 `STOPPED`，**不在**早退集合 `{STOPPING, CLOSED, FAILED}` 里，于是它会一路执行到 `admission.clear()`（第 236 行）——而 `_admission_refusal` 属于内层适配器，路由器碰都不碰，仍然是置位的。实测：

```
router stop_accepting after refusal: refusal='server is shutting down' open=False
```

也就是说，存在一个「拒绝态已置位、但闸门却是关的」的窗口：落进这个窗口的请求既不会被服务也不会被拒绝，只会挂着，直到内层 `shutdown_lifespan` 的 `_refuse_admission_locked` 把事件重新 set。

**这个窗口当前长度为零**：从 `stop_accepting()` 返回到内层 `_refuse_admission_locked` 之间没有任何真正的挂起点——`routing_tasks` 已空所以 `asyncio.gather` 被跳过，两处 `async with asyncio.Lock()` 都走无竞争快路径而不让出事件循环。所以今天挂不住。

但这条不变量的成立**依赖于 `asyncio.Lock` 无竞争时不让出**这样一个实现细节，而不是依赖任何显式设计。这是一个我会记下来但不会要求现在修的问题。若要修，最小改法是让路由器的 `stop_accepting()` 在内层拒绝态非空时跳过 `admission.clear()`。

---

## 问题 3：滚动重启路径

### 3.1 plain adapter 的 quiesce → resume 正确 —— 没有问题（置信度：高，有实测）

`UvicornListenerAdapter.resume_accepting()` → `_register_dormant_locked()`（第 285 行清拒绝态）→ `_arm_locked()`（第 303 行再清一次、第 304 行 set）。即使中途被 `begin_draining()` 置过位也能清干净。实测：

```
VERDICT plain: refusal=None open=True
```

### 3.2 【major】`both` 模式下 `resume_accepting()` 清不掉 `_admission_refusal`，resume 之后所有请求永久 503

**严重度：major（潜伏，当前生产路径不可达）。置信度：高——直接读状态实测确认，不是推理。**

`FirstByteRoutingAdapter` 有它**自己**的 `_register_dormant_locked()` 和 `_arm_locked()`（`listener.py:175-218`）。它们完全不调用内层适配器的同名方法，而内层的这两个方法正是唯二会清 `_admission_refusal` 的地方。路由器的 `_arm_locked()` 对内层只做一件事：`admission.set()`（第 217 行）。

于是走一遍 quiesce → drain → resume：

```
armed:     refusal=None                      open=True
quiesced:  refusal=None                      open=False
drained(0):refusal='server is shutting down'  open=True
resumed:   refusal='server is shutting down'  open=True     ← 事件开着，拒绝态还在
VERDICT router: REFUSAL STUCK -> permanent 503 after resume
```

`gated_app` 的判定是「事件 set 之后看 `_admission_refusal` 是否非空」，所以 resume 之后**每一个**请求都会拿到 503 `overloaded_error`，而且是永久的——没有任何后续调用会清掉它。监听器在正常 accept，端口在正常回应，进程健康，但服务全挂。这正是最难诊断的一类故障。

**可达性**：今天不可达。`begin_draining()` 的唯一调用点是 `StandaloneServer.serve()`，其后必然走向进程退出；`resume_accepting()` 在 `src/` 里没有任何调用点（只有 `tests/integration/test_listener_quiesce_resume.py` 在用，且只用 plain adapter）。

**为什么仍判 major 而不是 minor**：`lifecycle.md` 第 81 行把 `RESUME` 明确列为运行时信号语义，`adapter.py:196` 的 docstring 也把准入闸的存在理由写成「滚动 quiesce 时挂住请求直到监听器恢复」。也就是说，这个模块的既定发展方向就是把 quiesce/resume 接上控制面，而本次改动恰好在这条路上埋了一个「resume 之后服务全挂」的状态，且这半边**没有任何测试**——`test_listener_quiesce_resume.py` 从头到尾没碰过 `FirstByteRoutingAdapter`。修复报告的「未处理／待裁决」一节提到了滚动路径的闸未动，但提的是另一回事（quiesce 期间挂住请求是否合理），没有提到这条。

**最小修法**（供参考，我没有改）：让 `FirstByteRoutingAdapter._arm_locked()` 在 `admission.set()` 之前先把内层的 `_admission_refusal` 清成 `None`；或者更干净地，在 `UvicornListenerAdapter` 上开一个 `_clear_admission_refusal()` 之类的窄接口，别让 `listener.py` 继续伸手摸两个私有字段。

### 3.3 走一遍完整状态机，其余 resume 路径

除 3.2 外，我没有找到别的会让 resume 之后继续 503 的路径。逐条核对：

- `_register_dormant_locked`（内层）：清拒绝态 + clear 事件。正确。
- `_arm_locked`（内层）：成功时清拒绝态 + set；失败时置拒绝态 `"listener failed to start accepting"` + `_close_registrations_locked(FAILED)`。注意 `FAILED` 分支**不**清拒绝态，这是对的：arm 失败之后闸口就该拒绝。但要留意由此产生的状态——`FAILED` 之后 `resume_accepting()` 会抛 `resume requires stopped state`，`stop_accepting()` 会直接早退（第 132 行），所以拒绝态卡在那儿是终态而非中间态。可接受。
- `_close_registrations_locked(STOPPED)`：清拒绝态。仅 `stop_accepting()` 会传 `STOPPED`。见 1.4。

---

## 问题 4：第一档不得中断在途请求

### 4.1 h11 路径 —— 不会截断，我实测证实（置信度：非常高）

`H11Protocol.shutdown()`（`h11_impl.py:335-344`）只有两个分支：

```python
if self.cycle is None or self.cycle.response_complete:
    self.conn.send(h11.ConnectionClosed())
    self.transport.close()
else:
    self.cycle.keep_alive = False
```

关键在于 `response_complete` 只在 `RequestResponseCycle.send` 收到 `more_body=False` 的那一刻才置 `True`（第 511-512 行）。SSE 流在传输期间 `response_complete` 恒为 `False`，因此 `shutdown()` 只会清 `keep_alive`，**不会碰 transport**。等流真正结束时，第 522-525 行才 `conn.send(ConnectionClosed())` + `transport.close()`，而 asyncio 的 `transport.close()` 会先把缓冲区写完再关。所以完整响应一定先落地。

我不满足于读源码，做了端到端实测（`/tmp/probe_sse_truncation.py`）：一个 8 块 + `[DONE]` 的 `StreamingResponse`，在第 2 块发出后立刻 `SIGTERM`：

```
received 9 data lines of 9 expected
last line: b'data: [DONE]\n\n'
DONE present: True
terminating chunk present: True
report: ShutdownReport(stage=DRAINING, released_connections=1, interrupted_connections=0, cancelled_requests=0, ...)
```

**9/9 块 + chunked 终止块全部到达，`interrupted_connections=0`，档位停在 `DRAINING`。第一档没有截断 SSE。** 这是本次评审最重要的一条正面结论。

我另外用 h11 直接探了几个 `conn.send(ConnectionClosed())` 的状态机边界，确认 `shutdown()` 的守卫条件不多不少正好覆盖了会抛的那一格：

| 场景 | our_state | `send(ConnectionClosed())` |
|---|---|---|
| 全新连接（`cycle is None`） | IDLE | 允许 → CLOSED |
| 响应已完成、client body 未收完 | DONE | 允许 → CLOSED |
| 已 CLOSED，再关一次 | CLOSED | **允许**，不抛 |
| 请求头已到、body 未完、尚未响应 | SEND_RESPONSE | **`LocalProtocolError`** |

最后一行是唯一会抛的情况，而它恰好落在 `shutdown()` 的 `else` 分支（`cycle` 存在且 `response_complete` 为假），走不到 `conn.send`。同时第三行意味着**重复 `shutdown()` 不会抛**——我原本怀疑「两次信号连发时 `begin_draining` 与 `interrupt_connections` 可能在同一个 tick 内对同一条连接调两次 `shutdown()`」会炸，实测证伪，可以排除。

### 4.2 websocket 路径 —— 第一档会直接切断，但当前不可达

**严重度：minor（潜伏）。置信度：高（上游行为），高（不可达性）。**

`WSProtocol.shutdown()`（`wsproto_impl.py:151-158`）与 h11 完全不同：

```python
def shutdown(self):
    if self.handshake_complete:
        self.queue.put_nowait({"type": "websocket.disconnect", "code": 1012})
        output = self.conn.send(wsproto.events.CloseConnection(code=1012))
        self.transport.write(output)
    else:
        self.send_500_response()
    self.transport.close()
```

`self.transport.close()` 在**两个分支之外**，无条件执行。也就是说，一条活跃 websocket 在第一档就会被关掉，握手中的连接会拿到 500。按 `lifecycle.md` 第 20-21 行，切断在途连接是第二档的动作，第一档只该「停止 accept 并等待清空」。`interrupt_connections()` 的 docstring 声称「连接会在当前响应结束后才关闭，请求是被截断而非写到一半被杀」——这句话对 h11 成立，**对 websocket 不成立**（这是既有措辞问题，不是本次引入，但 `begin_draining` 现在把这个行为提前到了第一档）。

**当前不可达**：我枚举了 standalone 实际服务的应用 `create_pipeline_app(chain)` 的全部路由，18 条**全是 `APIRoute`，一条 `WebSocketRoute` 都没有**。仓库里的三个 websocket 路由（`routes/responses_ws.py:22`、`routes/history.py:89`、`routes/approval.py:47`）都没有被挂进这个 app（`app_factory` 里那套是另一条链路，其模块 docstring 自称「still serves the existing implementation」）。所以今天没有 websocket 会走到这里。

一旦哪天把 `/history/ws` 之类挂进 pipeline app，第一档就会开始切活跃 websocket。记在这里，等到那天有据可查。

### 4.3 【major】「第一档不截断已开始的响应」在整套测试里零分辨力

**严重度：major（守卫缺口，非现行缺陷）。置信度：非常高——变异实测。**

我构造了一个精确对准 SSE 截断形状的变异（`/tmp/mut_cut_started.py`）：只对 `response_started and not response_complete` 的连接做 `transport.close()`，其余照旧 `shutdown()`。这正是「一个正在写响应的流被切断」。

结果：

```
tests/integration/ + tests/unit/test_lifecycle_cleanup.py + tests/unit/test_shutdown_reporting.py
84 passed in 23.71s
```

**84 条测试全绿。** 同一个变异下，我的探针立刻抓到：

```
received 2 data lines of 9 expected
last line: b'data: block-01\n\n'
DONE present: False
terminating chunk present: False
```

原因很直接：`test_standalone_lifecycle.py` 的 `/slow` 路由返回的是一个普通 dict，响应在信号落地时**尚未开始写**，所以它守的是 `response_started == False` 那一格；`response_started and not response_complete` 这一格全项目没有任何测试覆盖。4.1 里我用变异 `mut_hard_close`（无条件关）证明了前一格确实有守卫，两相对照，缺口的位置非常清楚。

**为什么这条值得判 major**：本项目的产品边界写着「块级缓冲是必须的，一个完整的 Anthropic content block 是交付单位」，被截断的 SSE 响应是严重缺陷。而本次改动是**第一档历史上第一次去动连接对象**——在此之前第一档只关监听器。也就是说这次改动新开了一个失效面，而这个失效面恰好是零分辨力的。现在的代码是对的（4.1 已实测），但下一个改到这个循环的人不会收到任何信号。

**建议的处置**（我只提建议，不建门、不动测试）：在 `test_standalone_lifecycle.py` 里加**一条**测试就够——一个 `StreamingResponse` 路由，第一块发出后 `SIGTERM`，断言收到全部块与终止块、`cancelled_requests == 0`、`stage is DRAINING`。我的 `/tmp/probe_sse_truncation.py` 已经是这条测试的可用骨架。不建议为此建任何验证框架或门禁。

### 4.4 关闭空闲 keep-alive 连接会让在途字节变成 RST 而非干净 EOF

**严重度：minor。置信度：高（实测复现）。**

`/tmp/probe_drain.py` 在 `sleep=0.0` 参数下（客户端在 `begin_draining` 执行的同一瞬间往池化连接写请求）复现出：

```
ConnectionResetError: [Errno 104] Connection reset by peer
```

机制是经典的 keep-alive 竞态：服务端 `transport.close()` 时内核接收缓冲里还有客户端刚发来的、协议层从未读取的字节，于是内核发 RST 而不是 FIN。客户端拿到的是连接重置，而不是干净的 EOF，也不是 503。

这不是本次修复引入的新机制——uvicorn 自己的 `Server.shutdown` 做的是同一件事，而且这是「关闭任何 keep-alive 连接」的固有代价。但值得知道：**第一档现在会触发它**（此前第一档不碰连接）。对幂等 GET 无所谓，对 `POST /v1/messages` 则意味着客户端可能报连接错误而非可重试的信号。若哪天要消除它，方向是先 `shutdown(SHUT_WR)` 发 FIN、待对端关闭后再 close，而不是直接 close；但那要额外的状态跟踪，在没有实际投诉之前 ROI 不明显。我倾向于记录而不改。

---

## 问题 5：503 拒绝路径

### 5.1 HTTP scope 的 ASGI 消息合法 —— 没有问题（置信度：高，有 h11 探针）

`_refuse_admission` 发 `http.response.start`（含 `content-length`）+ 单条 `http.response.body(more_body=False)`，是最标准的两消息响应，`RequestResponseCycle.send` 的状态机（`h11_impl.py:463-520`）逐条接受。

一个我特意验证过的边界：**被拒绝的请求往往 body 还没收完**（客户端声明了 `Content-Length` 却还在发）。这时提前发响应，h11 会把 `our_state` 推到 `MUST_CLOSE`：

```
after refusal our= MUST_CLOSE their= SEND_BODY   MUST_CLOSE? True
```

而 uvicorn 第 522-525 行正好处理了这一格：`if self.conn.our_state is h11.MUST_CLOSE or not self.keep_alive: conn.send(ConnectionClosed()); transport.close()`。所以不会残留半开连接，也不会有 `LocalProtocolError`。显式带的 `connection: close` 头是多余但正确的——h11 无论如何都会进 `MUST_CLOSE`，这个头的价值在于让客户端**看得见**，值得保留。

### 5.2 客户端已断开时的二次发送 —— 不会抛（置信度：高）

`RequestResponseCycle.send` 第 460-461 行：`if self.disconnected: return`。`disconnected` 由 `connection_lost` 在 `cycle and not cycle.response_complete` 时置位（第 112-113 行）。所以一个在闸口挂着时客户端就跑掉的请求，两条 `send` 都静默早返回，不抛。

`run_asgi` 的收尾（第 420-432 行）也覆盖了这一格：`not self.response_started and not self.disconnected` 与 `not self.response_complete and not self.disconnected` 两个分支都带 `and not self.disconnected`，所以不会误发 500、不会打「ASGI callable returned without starting response」的错误日志。干净。

另一个边界：`send` 开头的 `if self.flow.write_paused ... await self.flow.drain()` 理论上能挂住，但拒绝响应体只有几十字节，触不到高水位。

### 5.3 websocket scope 的 1012 在可达路径上永远不生效

**严重度：minor。置信度：高（读源码 + 状态推理）。**

`REFUSAL_WEBSOCKET_CODE = 1012` 的注释说「1012 是 service restart，滚动控制面已经在用同一个码」。实际上这个码**永远不会上线**。

`gated_app` 在调用下游 app **之前**就拒绝，所以此刻 `handshake_complete` 必然是 `False`（它只在 `WSProtocol.send` 里被置位）。而 wsproto 对握手前的 `websocket.close` 的处理是（`wsproto_impl.py:278-290`）：

```python
elif message_type == "websocket.close":
    self.queue.put_nowait({"type": "websocket.disconnect", "code": 1006})
    self.logger.info('%s - "WebSocket %s" 403', ...)
    event = events.RejectConnection(status_code=403, headers=[])
```

**`code` 与 `reason` 都被丢弃，实际上线的是 HTTP 403，不带任何原因。** 客户端看到的既不是 1012 也不是那句 `server is shutting down`。安装了 `websockets` 库时走 `websockets_impl` 也是同样的 403 语义。

所以 `REFUSAL_WEBSOCKET_CODE` 在当前代码里是**事实上的死常量**，注释描述了一个不会发生的行为。结合 4.2（当前无 ws 路由），整个 websocket 拒绝分支都是潜伏的。要让 1012 真正生效必须发 `websocket.accept` 之后再 `websocket.close(1012)`，那是另一种设计取舍，不建议为此改动——建议只把注释改成实情，或者把常量删掉。

### 5.4 拒绝路径未先 `receive()` `websocket.connect`

**严重度：nit。置信度：高。**

ASGI 惯例是应用先收到 `websocket.connect` 再发 `accept`／`close`。`gated_app` 直接发 `websocket.close`。uvicorn 的 wsproto 实现不校验消息顺序（队列里那条 connect 就被丢掉了），所以不会抛。但若哪天在 `gated_app` 与 uvicorn 之间插入任何严格校验的中间件，这里会炸。一行 `await receive()` 就能规避，成本极低。

### 5.5 被拒绝的请求没有留下任何可读的痕迹

**严重度：minor。置信度：高。**

`gated_app` 装在 pipeline app **之上**（`_install_admission_barrier` 包的是 `config.loaded_app`），所以被拒绝的请求不进请求日志、不进 TUI、不进 `ShutdownReport`。运维读完关停行也无从知道「这次关停有几个客户端吃了 503」——而这恰恰是判断一次重启是否影响了用户的关键数字。

这正落在项目记忆 `absence-is-not-readable-on-a-log-line` 说的那一类：字段「有才打印」，于是「没发生」和「不报这项」同形。建议（非阻塞）：`begin_draining` 之后累计一个 `refused_requests` 计数，进 `ShutdownReport`，并且**要进 incidents**——被拒绝的请求和被放掉的空闲连接不是一回事，前者是有人真的没被服务。

---

## 其余发现

### 6.1 `released_connections` 名不副实：计的是「被通知的」，不是「被放掉的」

**严重度：minor。置信度：高（两次实测均复现）。**

`begin_draining` 返回 `len(connections)`——**全部**打开的连接数，而不是实际被关掉的数量。`connection.shutdown()` 对有在途请求的连接只清 `keep_alive`，那条连接完全没有被「放掉」。

实测两例：

- SSE 探针：`released_connections=1`，而那唯一一条连接把 9 个块全部写完之后才关。它没有被放掉，它是正常跑完的。
- `/tmp/probe_drain.py`：`released_connections=2`，实际只有 1 条空闲连接被关，另一条载着 `/slow` 跑到结束。

于是运维看到的行是 `stopped — 2 connections released`，而其中一条其实是正常服务完的。docstring「reporting how many were released」和 `cli.py:182` 的「Letting go of the idle pooled connections is what the first rung is for」都比事实说得多。对比之下 `interrupt_connections` 的 docstring 是诚实的（"report how many were **asked**"）。

新测试 `test_the_drain_lets_go_of_an_idle_pooled_connection` 只有一条连接，`asked` 与 `released` 恰好相等，所以这个差异**没有任何测试能发现**。

建议：要么只计实际关掉的（即 `cycle is None or cycle.response_complete` 的那些），要么把措辞统一改成「asked to close」。我倾向前者——这条数字的读者是运维，他要的是「有几个客户端被踢了」。

### 6.2 修复文档「两件事，缺一不可」不成立

**严重度：minor（文档准确性）。置信度：高——双向变异实测。**

`docs/tmp/260820-graceful-shutdown-admission-deadlock.md` 第 35 行称拒绝准入与放掉连接「缺一不可」，`adapter.py:194` 的 docstring 写「neither closes it alone」。我做了两个方向的半拆变异：

| 变异 | 结果 |
|---|---|
| 只留放连接、去掉拒绝（`mut_no_refusal`） | 1 failed：`test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` TimeoutError |
| 只留拒绝、去掉放连接（`mut_no_close`） | **13 passed，全绿** |

结论是不对称的：**拒绝准入是必要的那一半，放掉连接不是。** 去掉放连接之后闸口仍然会把落进来的请求答成 503，排空照样结束；空闲连接则由稍后的 `shutdown_lifespan` 关掉（它本来就会关），客户端等到的 EOF 只是晚了几十毫秒。

放连接**仍然值得保留**——它让池化客户端更早知道该另寻出路，也缩小了 4.4 那个 RST 窗口的暴露时间。但它的定位是「更早告知」，不是「缺一不可」。文档把两件事说成同等必要，会让后来者在权衡时高估其中一半的地位。

### 6.3 头号新测试对它自己声称的机制零分辨力

**严重度：minor（测试质量）。置信度：非常高——变异 + 探针双重证实。**

`test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open` 的 docstring 写的是准入闸挂住请求这件事本身（「the admission barrier then held that request for a listener resume that a shutdown is never going to perform」）。但在 `mut_no_refusal` 变异下**它是绿的**——唯一变红的是那条直接驱动适配器的 barrier 测试。

原因我用探针查清了。测试的时序是 `receive_signal(SIGTERM)` → `sleep(0.2)` → 在池化连接上写第二个请求。而 `stop_accepting` + `begin_draining` 在信号后的下一个事件循环迭代就跑完了，那条空闲连接**早在 0.2 秒之前就已经被关掉**。探针输出：

```
after 0.2s: connection_count=1        ← 只剩载着 /slow 的那条，池化连接已消失
second request written OK             ← 写进了已关闭的 socket，本地成功而已
pooled read: b''                      ← 直接 EOF
served handlers: ['quick']            ← 服务端从头到尾只跑了一个 handler，第二个请求根本不存在
```

所以这条测试实际测的是「关停时存在一条空闲池化连接不会拖住排空」，和它旁边那条 `test_the_drain_lets_go_of_an_idle_pooled_connection` 测的是同一件事，而它名字与 docstring 承诺的那件事由第三条测试独立覆盖。

修复报告里的变异证据（把 `begin_draining()` 换成 `released = 0` → 这条测试 TimeoutError）本身是真的，但那是**同时**拿掉了两半；它证明的是「begin_draining 整体是必要的」，不是这条测试对拒绝半边有分辨力。这是一个典型的、值得记下来的推理跳步：整体变异变红，不等于每一条断言各自都有指向性。

建议：把这条测试的 docstring 改成它实际验证的东西，或者把 sleep 换成「在 `stop_accepting()` 之后、`begin_draining()` 之前」这个真窗口——但后者要卡微秒，第三条测试已经用「直接驱动适配器」这个更诚实的办法解决了。我倾向只改措辞。

### 6.4 `begin_draining` 取锁而语义等价的 `interrupt_connections` 不取

**严重度：nit。置信度：高。**

两者对连接做的事完全相同（遍历 `server_state.connections` 逐个 `shutdown()`），但一个是 `async` 且取 `_operation_lock`，另一个是同步且无锁。单线程事件循环里两种写法都安全，不是缺陷。但读者会自然推断「取锁那个是因为有竞态」，从而对不存在的危险建立错误心智模型。值得在其中一处写一句为什么。

### 6.5 `begin_draining` 这个名字在项目里有两个不同含义

**严重度：nit。置信度：高。**

`app.observability.active_requests.ActiveRequests.begin_draining()`（`active_requests.py:51`）是给显示层用的、无返回值的通知；`ListenerLifecycle.begin_draining()` 是本次新增的、返回连接数的关停动作。二者在 `cli.py:169` 那一行里**相邻出现**：

```python
create_pipeline_app(chain), options, chain.active_requests.begin_draining, publish_connections
```

那个位置传的是 `on_draining` 钩子，恰好是另一个 `begin_draining`。不是缺陷，但同名不同义会在 grep 和阅读时制造摩擦，值得知道。

### 6.6 `startup_lifespan` 若被二次调用会二次包装 `gated_app`

**严重度：nit（既有问题，非本次引入）。置信度：中。**

`_install_admission_barrier` 读 `config.loaded_app` 再写回 `gated_app`。若 `startup_lifespan` 被调用第二次（`shutdown_lifespan` 会把 `_lifespan_started` 置回 `False`），就会再包一层，形成嵌套的两道闸。实际上 `shutdown_lifespan` 成功时把状态置为 `CLOSED`，而 `startup_lifespan` 对 `CLOSED` 直接抛错，所以正常路径不可达；只有在 `shutdown_lifespan` 中途失败（状态停在 `FAILED`）之后重新启动才碰得到。本次改动没有加重也没有减轻它。

---

## 我认为没有问题的项（附判断依据）

按要求逐条列出，不只列问题。

| 项 | 判断 | 依据 |
|---|---|---|
| `begin_draining` 与 `shutdown_lifespan` 争同一把锁造成死锁 | 无 | `adapter.py:207-226`：`wait_drained` 在锁外；两者在 `serve()` 里严格串行 |
| `begin_draining` 重入 | 无 | 锁内只调同步方法，无二次取锁路径 |
| 与 `_run_ticks` 的交互 | 无 | `uvicorn/server.py:233-260` 的 `on_tick` 不碰锁／闸／连接；返回值被忽略；`limit_max_requests` 未配置 |
| 与 `cancel_requests` 的档位混淆 | 无 | `begin_draining` 不 cancel；`mut_hard_close` 变异证明两条既有第一档守卫有分辨力 |
| `admission_open` 按值捕获 | 语义上无害 | `rg '_admission_open\s*='` 全 `src/` 仅 `adapter.py:69` 一处绑定；此后只 set／clear。脆弱性另记为 nit（1.5） |
| `both` 模式下 `stop_accepting` → `begin_draining` 的顺序 | 成立 | 实测状态转移；`listener.py:224-240` 已处理 pending socket 与 routing task，转发给内层数连接是完备的 |
| plain adapter 的 quiesce → resume 清闸 | 正确 | 实测 `refusal=None open=True` |
| `_close_registrations_locked(STOPPED)` 会清掉拒绝态 | 在关停路径不可达 | `shutdown_lifespan` 传的是 `STOPPING`（`adapter.py:213`）；`serve()` 中 `stop_accepting` 排在前面 |
| 第一档截断 SSE | **不会**，实测 | `/tmp/probe_sse_truncation.py`：9/9 块 + 终止块；`h11_impl.py:335-344` 的守卫条件与 h11 状态机边界精确对齐 |
| 重复 `connection.shutdown()` 抛 `LocalProtocolError` | 不会 | h11 探针：CLOSED 状态再收 `ConnectionClosed` 不抛；唯一会抛的 SEND_RESPONSE 格落在 `shutdown()` 的 else 分支 |
| 503 的 ASGI 消息（http） | 合法 | 标准两消息响应；body 未收完时 h11 进 `MUST_CLOSE`，uvicorn 第 522-525 行正确收尾 |
| 客户端已断开时二次 send 抛异常 | 不会 | `h11_impl.py:460-461` 早返回；`run_asgi` 收尾分支均带 `and not self.disconnected` |
| `cli.py` 的 `clean` 判定改动 | 正确 | `clean = not incidents and cleanup_completed`，released 只进 detail 不进判定，与「放掉空闲连接是健康关停常态」一致 |
| `test_a_half_sent_request_holds_the_drain` 的夹具与同步修正 | 正确 | 新增 `/swallow` 确实 `await request.body()`；发信号前先确认收不到响应，消除了原来 `sendall` 之后立刻发信号的竞态。`socket.timeout` 在 3.10+ 即 `TimeoutError`，`pytest.raises(TimeoutError)` 写法正确 |
| `ListenerLifecycle` 协议与 `test_lifecycle_cleanup.py` 的 stub 同步 | 正确 | stub 补了 `begin_draining` 返回 0，且注释说明了为什么这里的数字不该由测试发明 |
| 受审范围内的静态检查 | 干净 | `ruff check` 五个文件全过 |
| 相关测试基线 | 全绿 | 53 条（含 quiesce/resume 与 shutdown reporting），23.5s |

---

## 处置建议（按我的优先级，均不构成门禁）

1. **修 3.2**（`FirstByteRoutingAdapter._arm_locked` 清 `_admission_refusal`）。这是唯一一条会导致「服务活着但全挂」的缺陷，虽然当前不可达，但修复成本是一行，且滚动路径已经写进权威规范。顺带建议给内层适配器开一个窄接口，别让 `listener.py` 继续摸第二个私有字段。
2. **补 4.3 的那一条 SSE 测试**。一条就够，`/tmp/probe_sse_truncation.py` 可直接改写。不要为此建任何验证框架。
3. **改 6.1 的计数或措辞**，二选一。
4. 改 6.2、6.3 的文档与 docstring 措辞，让它们描述实际成立的事。这一条纯文字，但影响的是下一个人怎么理解这套机制的必要性结构。
5. 5.3 的 `REFUSAL_WEBSOCKET_CODE`：改注释或删常量。
6. 其余 minor／nit 记录即可，不建议在本次改动里处理。

## 未评审 / 明确的范围边界

- 工作树中 `src/app/pipeline/`、`src/app/server/handler.py`、`src/app/streaming/`、`tests/http/` 等并行会话的在飞改动，按指令未评审、未改动。`src/app/server/admission.py`（`InFlightLimit`）当前是干净的已提交状态，我只把它当作上下文读了一遍以确认它不与准入闸冲突（它在 pipeline app 内部，位于 `gated_app` 之下，被拒绝的请求根本到不了它；被它的信号量挂住的请求已经计入 `server_state.tasks`，第一档等它们是符合规范的），未对其做评审。
- `docs/.human-controlled/lifecycle.md` 只读，未修改。
- systemd 路径（`serve_inherited` 走 uvicorn 自己的 `Server.serve()`）不在本次改动范围内，未评审。
- 所有探针与变异均写在 `/tmp`，未在仓库内留下任何文件，未安装任何 pytest 插件到项目配置中。
