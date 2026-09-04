# 独立评审：优雅关闭修复的「评审后改动」增量（`1a7353e`）

评审对象：提交 `1a7353e` 中**为回应两轮既有评审而做的那一批改动**（这批本身未被任何人评审过）。逐项范围见下方「逐项裁决」。
评审日期：2026-08-20。评审者：并发与生命周期方向的独立评审 agent。**只读评审，未修改仓库任何源码或测试**；全部探针与变异都在 `/tmp/shutdelta/` 下进行。
权威规范：`docs/.human-controlled/lifecycle.md` 第 18-26 行（关停三档语义）、第 78-82 行（`QUIESCE`／`RESUME`／`TERMINATE`）。只读，未修改。
既有评审：`docs/tmp/260820-shutdown-fix-review-gpt.md`、`docs/tmp/260820-shutdown-test-rebase-review.md`。其中已核实的上游事实（h11 `shutdown()` 的两个分支、`RequestResponseCycle.send` 的 `disconnected` 早返回、`on_tick` 与闸无关等）直接复用，未重复考据。

## ⚠️ 评审期间历史被重写，本报告已重新锚定

评审进行中，并行会话重写了这段历史：`1a7353e` **已不再是 HEAD 的祖先**，其等价提交是 `f37068c`（同一条 subject）。我核对过 `git diff 1a7353e f37068c -- src tests` **为空**——两者在源码与测试上逐字节相同，差异全部是把 `docs/` 的一大批文件移出版本控制（373 个文件、31186 行删除）。**因此本报告的评审对象未变，只是哈希从 `1a7353e` 换成了 `f37068c`。**

此后又有一条提交动过我审的测试：`5968067 test: make the idle-connection guard witness the rung it names`。它出自另一名 agent 的变异复算（`docs/tmp/260820-shutdown-mutation-audit.md`），修的正是我在变异表里量到的 C2 缺口，并改写了两处过度归因的 docstring。**我把关键变异在当前 HEAD 上重跑过**，结论见「对当前 HEAD 的复核」一节：C2 已被修好，**F-1、F-2 及其余全部发现在 HEAD 上原样成立**。

与那份并行审计的分工：它审的是「实现者声称的四条变异是否属实」与测试的分辨力；本报告审的是这批改动本身的并发正确性、`refused_requests` 的语义与可观测性、websocket 拒绝路径、以及测试夹具的稳定性。两份**不重叠**，唯二交叠处（C2 那条测试、真实进程守卫的概率性）它先发现且已落地修复，我在下文逐处注明，避免重复计数。

## 结论

**blocker 0，major 1，minor 6，nit 3。这批改动的机制全部是对的，我逐项做了变异或探针确认；唯一的 major 不是功能缺陷，而是本次新增的那个计数在真实关停路径上量不到它声称要量的东西。以上计数是对当前 HEAD 复核后的数字——评审中途由 `5968067` 修好的那一格已不计入。**

一句话：`open_admission()`／`pause_admission()` 这对方法是正确且必要的收拢，跨两个锁域调用在当前代码里安全（实测无挂起点）；三条新测试的分辨力我逐条用变异打红过，全部成立；`await receive()` 不会挂；marker 文件同步在 14 路满载下仍稳定。问题集中在 `refused_requests`：它的接线是对的，但**实测在真实进程的真实滚动关停里恒为 0**，而客户端真正付出的代价（池化连接被 RST／裸 EOF）被记进了明确排除在事故之外的 `connections_asked_to_close`，于是 `absence-is-not-readable-on-a-log-line` 想堵的那个洞并没有被堵上，且这条计数的 docstring 声称的正好相反。

关于任务书里点名担心的两件事，实测结论都是**否**：

- 「`pause_admission()` 连拒绝态一起清掉，会不会在 `shutdown_lifespan()` → `stop_accepting()` 路径上开新窗口」——plain 模式下窗口宽度为 **0 个事件循环 tick**（实测）；`both` 模式在有待路由连接时确实有 **3 个 tick** 的真实窗口，但落进窗口的请求得到的是 503，不是被服务，也不是挂住。
- 「把 refusal 算作 incident 会不会让例行滚动重启报 fail」——真实进程实测 5 组，`refused=0`、收尾行 `[ OK ]`。**不会例行报 fail，但原因是这条计数根本没被触发**，而不是设计上避开了。

## 方法与证据基线

判断分四种来源，逐条标注：

1. **源码阅读**：`src/app/lifecycle/{adapter,listener,standalone}.py`、`src/app/cli.py` 当前状态（与 `1a7353e`／`f37068c` 一致；`git diff f37068c HEAD` 对 `src/app/lifecycle` 为空，对 `cli.py` 只有一处属于并行会话的 `debug_models` 漂移，与 `report_shutdown` 无关）；uvicorn 0.40.0、wsproto 1.3.2（本环境**未装 websockets、未装 httptools**，故 `http="auto"` → `H11Protocol`、`ws="auto"` → `WSProtocol`）。
2. **树外探针**：`/tmp/shutdelta/probe_window.py`（事件循环 tick 计数器 + 闸状态轨迹）、`probe_woken.py`、`probe_ws.py`、`probe_count.py`、`probe_report.py`、`probe_process.py`（真实子进程 + 真实 SIGTERM）。
3. **树外变异**：两棵副本。`git archive 1a7353e` → `/tmp/shutdelta/tree`（由 `mutate.py` 驱动，评审对象本身）；`git archive HEAD` → `/tmp/shutdelta/head`（由 `mutate_head.py` 驱动，用于历史被重写后的复核）。两者都从各自的 pristine 副本还原后打补丁；`PYTHONPATH` 绑到对应副本的 `src`，已分别验证 `app.lifecycle.adapter.__file__` 解析到该副本（venv 里有 `app` 的 editable 安装，这一步不是多余的）。
4. **基线**：仓库内 `tests/integration/test_standalone_lifecycle.py`、`test_standalone_process.py`、`test_listener_quiesce_resume.py`、`tests/unit/test_lifecycle_cleanup.py`、`test_shutdown_reporting.py` 共 **56 passed / 21.3s**；`1a7353e` 副本树同一组 56 passed 重复 5 次全绿；HEAD 副本树同一组 56 passed。`ruff check` 与 `pyright` 在受审的四个源文件上干净（0 errors）。

### 变异一览（副本树，56 条同一组测试）

| 变异 | 内容 | 结果 |
|---|---|---|
| A_cut_started | 第一档对 `response_started and not response_complete` 的连接直接 `transport.close()` | **1 failed** —— 正是 `test_rung_one_delivers_a_response_that_had_already_started_streaming` |
| B_router_arm_leaves_refusal | 路由器 `_arm_locked` 退回只 `admission.set()`、不清拒绝态 | **1 failed** —— 正是 `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503` |
| C1_no_refusal | `stop_admitting` 只放连接、不置拒绝态 | 1 failed —— `test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting`（该测试属于上一版，非本次增量） |
| C2_no_close | `stop_admitting` 只置拒绝态、不放连接 | **56 passed，全绿**（此格已由 `5968067` 修好，HEAD 上变红，见下节） |
| D_pause_leaves_gate_open | `pause_admission` 只清拒绝态、不 clear 事件 | 1 failed —— barrier 那条 |
| E_no_count | 删掉 `self._refused_requests += 1` | **56 passed，全绿**（HEAD 上依旧全绿） |
| F_no_stop_admitting | `serve()` 不调 `stop_admitting()`（等价于缺陷仍在） | 3 failed，含新增的真实进程测试 |
| G_cli_clean（另跑） | `clean = not incidents` 改回 `clean = not parts` | **22 passed，全绿**（HEAD 上 56 条同组依旧全绿） |

A、B、F 三格是本次增量新测试的正向证据；C2、E、G 三格是覆盖缺口的证据。修复文档 `docs/tmp/260820-graceful-shutdown-admission-deadlock.md` 里声称的三条变异结果（A、B、F 对应的那三条）**我独立复现，全部属实**。

### 对当前 HEAD 的复核

在 `git archive HEAD` 的另一棵副本（`/tmp/shutdelta/head`，`mutate_head.py` 驱动）上重跑同一组 56 条：

| 变异 | 结果 | 含义 |
|---|---|---|
| （无变异） | 56 passed | HEAD 基线绿 |
| C2_no_close | **1 failed** —— `test_the_drain_lets_go_of_an_idle_pooled_connection` | 缺口已由 `5968067` 补上，本报告不再计入 |
| E_no_count | **56 passed，全绿** | **F-2 在 HEAD 上原样成立** |
| G_cli_clean | **56 passed，全绿** | **F-2 在 HEAD 上原样成立** |

`git diff f37068c HEAD -- src/app/lifecycle` 为空，`src/app/cli.py` 的漂移全在 `debug_models`，所以 F-1、F-3 至 F-10 涉及的源码在 HEAD 上一个字节都没变，无需重跑。

---

## 逐项裁决

### 项 1：`begin_draining` → `stop_admitting` 改名

**判定：无问题。置信度：高。**

`rg` 全仓库确认改名彻底：`src/app/lifecycle/{adapter,listener,standalone}.py`、`tests/integration/test_standalone_lifecycle.py`、`tests/unit/test_lifecycle_cleanup.py` 一致，`ListenerLifecycle` 协议同步，pyright 0 error。旧评审 6.5 指出的重名（与 `observability.active_requests.begin_draining` 在 `cli.py:169` 同一行相邻）确实消除了。新名字也更准：它在 `serve()` 里紧跟 `stop_accepting()`，读作「停止 accept 连接，停止 admit 请求」。

### 项 2：新增 `open_admission()` / `pause_admission()`，被两个锁域调用而自身不取锁

**判定：设计正确，无可达缺陷。有两条形状级备案（F-3、F-6、F-7）。置信度：高，有实测。**

先说为什么**不取锁是必须的**：`_arm_locked`、`_register_dormant_locked`、`_close_registrations_locked` 三个调用点都在 `UvicornListenerAdapter._operation_lock` 之内，而 `asyncio.Lock` 不可重入——这对方法若自己取锁，plain 路径当场死锁。所以「自身不取锁 + 由持锁方调用」是唯一可行的形状。

再说**路由器那条路径为什么也安全**：`FirstByteRoutingAdapter._arm_locked` 与 `_register_dormant_locked` 都是**同步方法**，`stop_accepting` 的锁块内也没有任何 `await`（`asyncio.gather` 在锁块之外）。所以路由器对这两个字段的写入相对事件循环是原子的，不可能与内层的任何操作交错到「只写了一半」的状态。两个字段之间也没有 await，`gated_app` 的读者要么看到旧的一对、要么看到新的一对。

**任务书点名的那个问题——`pause_admission()` 现在连拒绝态一起清，会不会在 `shutdown_lifespan()` → `stop_accepting()` 上开新窗口——我用 tick 计数器直接量了。** 探针 `probe_window.py` 起一个 `while True: TICKS += 1; await asyncio.sleep(0)` 的后台任务，给每次闸状态变更打上 tick 戳；tick 差为 0 就说明其间事件循环一次都没让出：

```
event                                      tick  refusal / open
open_admission                                3  None / True
--- pooled connection established ---    132003  None / True
pause_admission                          132004  None / False      ← serve(): 路由器 stop_accepting
refuse(server is shutting down)          132004  'server is shutting down' / True   ← serve(): stop_admitting
pause_admission                          132010  None / False      ← _finalize(): 路由器 stop_accepting 第二次
refuse(server is shutting down)          132010  'server is shutting down' / True   ← 内层 shutdown_lifespan
--- serve returned ---                   132018  'server is shutting down' / True
```

两处 `pause → refuse` 的 tick 差都是 **0**。原因是 `asyncio.Lock` 无竞争时 `acquire()` 直接返回不让出，且第二次 `stop_accepting` 时 `routing_tasks` 已空、`asyncio.gather` 被跳过。**旧评审 2.2 描述的那个窗口，在本次改动后依然是零宽的**，只是内容从「拒绝态在、闸关着」变成「拒绝态和闸都清了」——对**新到达**的请求两者等价（都是先挂在闸上、随后被内层的 `_refuse_admission_locked` 唤醒并答 503）。

但见 F-3：对**已被唤醒、尚未恢复执行**的等待者，两者不等价，且这次是往坏的方向变的。见 F-4：`both` 模式在有待路由连接时，第一次 `stop_accepting` 的 `await asyncio.gather(routing_tasks)` 会让出，窗口不是零宽（实测 3 个 tick）。

### 项 3：新增 `refused_requests` 计数

**判定：接线正确，语义与可观测性有问题。1 条 major（F-1）+ 3 条 minor（F-2、F-4、F-5）+ 1 条 nit（F-9）。**

先给出**成立**的部分（实测，`probe_report.py`）：把请求真正堵在闸上再关停，端到端完全通：

```
parked request got: HTTP/1.1 503 Service Unavailable
report.refused_requests    = 1
adapter.refused_requests() = 1   ← 相等，说明读的时机没漏
[FAIL] stopped — 1 connections asked to close, 1 requests refused
```

- **读的时机没问题。** `_descend` 在 `await self._finalize()` **之后**才构造 `ShutdownReport`（`standalone.py:221-231`），而 `_finalize` → `shutdown_lifespan(drain_timeout=None)` → `wait_drained(None)` 是无界等待，被拒绝的 `gated_app` 本身就是 `server_state.tasks` 里的一个任务，所以读之前所有拒绝都已发生。探针里 `report.refused_requests == adapter.refused_requests()` 直接印证。
- **计数点位置**：`self._refused_requests += 1` 在 `await _refuse_admission(...)` **之前**，所以客户端已断开时**仍会计入**。我认为这是对的：这条数字问的是「有没有人被回绝」，不是「有没有人收到了回绝」；旧评审 5.2 已证实 uvicorn 那两条 `send` 在 `disconnected` 时静默早返回，不抛，所以「计了但没送到」不会伴随异常。docstring 写的是 "turned away at the barrier rather than served"，与实现一致。

问题见 F-1（真实路径上恒为 0）、F-2（整条特性零覆盖）、F-4（`both` 模式反而会触发，从而例行报 fail）、F-5（累计量被当成单次关停代价）。

### 项 4：`gated_app` 改读 `self._admission_open`

**判定：无问题，是净改善。置信度：高。**

旧评审 1.5 的诉求被完整满足：两半闸状态现在同一种读法，「此 Event 不得重绑」不再是跨文件的隐式契约。`gated_app` 本来就闭包持有 `self`（为读 `_admission_error`），改成读 `self._admission_open` 不引入任何新的引用或生命周期问题。行内注释把理由（重绑是写 reset 最自然的写法，症状是静默永久挂起）写清楚了，值得肯定。

### 项 5：`_refuse_admission` 增加 `receive` 参数，websocket 分支先 `await receive()`

**判定：不会挂。置信度：非常高——源码 + 端到端实测。**

源码：`wsproto_impl.py:188` 在 `handle_connect` 里 `self.queue.put_nowait({"type": "websocket.connect"})`，**紧接着**第 189 行才 `self.loop.create_task(self.run_asgi())`。`run_asgi` 全仓库只有这一个调用点，所以应用被调起时队列里必然已经有 `websocket.connect`，`await receive()` 立即返回。`websockets_impl.py:360-362` 的 `asgi_receive` 用 `connect_sent` 标志直接构造返回，同样不等待（本环境未装 `websockets`，这一条是读源码，未实测）。

实测（`probe_ws.py`，挂一条真实 `@app.websocket("/ws")` 到闸后面）：

```
ws protocol class: <class 'uvicorn.protocols.websockets.wsproto_impl.WSProtocol'>
before refusal: HTTP/1.1 101 Switching Protocols
after refusal:  HTTP/1.1 403
refused_requests = 1
```

**握手被立刻答成 403，没有任何挂起**，并且顺带证实了旧评审 5.3 的判断（1012 与 reason 都被 uvicorn 丢弃，上线的是 403），当前注释已改写为这个实情，准确。客户端已消失的情况也不会挂：`websocket.connect` 是在连接建立时入队的，即使随后 `handle_disconnect` 又塞进 `websocket.disconnect`，先取到的仍是 connect。

### 项 6：三条新测试

**判定：三条都有实测分辨力，是这批改动里质量最高的部分。置信度：非常高——逐条变异打红。**

- `test_rung_one_delivers_a_response_that_had_already_started_streaming`：变异 A（只切「已开始写响应」的连接）下，**56 条里只有它一条变红**。这正是旧评审 4.3 判 major 的那个零分辨力缺口，现已封上。断言选得好：9 块 + `[DONE]` + `delivered.endswith(b"0\r\n\r\n")`（chunked 终止块）+ `cancelled_requests == 0` + `stage is DRAINING`，最后那条 chunked 终止块的断言尤其值——「块都到齐了但帧没收尾」是唯一能绕过前两条的形状。
- `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503`：变异 B（路由器 `_arm_locked` 退回只 set 事件）下**只有它一条变红**，且复现出旧评审 3.2 预言的永久 503。`assert b"503" not in resumed` 这一条不是多余的——只断言 `200 OK` 会被「先 503 后 200」之类的形状蒙混，而它同时钉住了 `refused_requests() == 0`。
- `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process`：变异 F（`serve()` 不调 `stop_admitting`）下**6/6 变红**（未加载）+ **4/4 变红**（16 核上开 14 路满载 busy loop），且干净树上 4/4 绿、耗时 0.8-1.0 秒而变异下稳定撞 15 秒 `communicate` 超时。这填的正是 rebase 评审第 2 条指出的「真实进程这一层没了守卫」的空位，**实测确认它填上了**。

  一条限定：这条测试的分辨力**结构上是概率性的**。docstring 自己说「Deliberately unsynchronised」，如果 405 抢在 SIGTERM 之前答完，缺陷版进程也会干净退出、测试变绿。我 10 次（含满载 4 次）都没观察到这一支，所以「今天它守得住」这个判断**强到可以据此行动**；但「它在任何机器上都守得住」我给不出，也没有必要为此加同步——加了就把这条测试变成另一条测试了。方向相反的失败（正确代码下假红）我在满载下跑了 3×10 条全绿，没有观察到。

  **补记（评审期间落地）**：并行审计 `docs/tmp/260820-shutdown-mutation-audit.md` 的「发现 C」独立量到了同一件事，并给出了更细的分档——同样是 10 次一组：干净代码 0/10、整个 `stop_admitting` 移除 10/10、只复活死锁机制 4/10、只移除拒绝那一半 2/10。`5968067` 已把这段实测数字写进该测试的 docstring。**我的 F 变异（整个 `stop_admitting` 移除）10/10 与他们的 10/10 完全一致**；差异只在于我没跑更弱的那两种变异。这一条我不再单列为发现。

补充一条对既有 docstring 的核对：`test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open` 的 docstring 原写「What actually saves it here is the connection being closed, not the refusal — measured, by removing each half in turn」。我两个方向都打了：C1（去掉拒绝）绿，C2（去掉关连接）也绿，所以那句排他归因不成立。**这一处并行审计的「发现 B」也独立命中，`5968067` 已改写成「a description of the path taken, not a claim that it is the only path that would save it」，措辞现在准确。** 同一提交还把 `test_the_drain_lets_go_of_an_idle_pooled_connection` 改成用一个在跑的慢请求撑住排空、在 `serve()` 返回**之前**读 EOF，我在 HEAD 副本上验过：C2 变异下它现在**变红**。这两处都已闭合，不计入本报告的发现清单。

### 项 7：`/swallow` marker 文件 + `wait_for_arrivals()`

**判定：无问题，是净改善。置信度：高——有满载实测。**

- **跨测试污染：不存在。** `pidfile` fixture 是 `tmp_path / "standalone.pid"`，`marker = pidfile.parent / "entered"` 即 `tmp_path / "entered"`，而 pytest 的 `tmp_path` 按**测试函数**分目录、按 run 分 basetemp。同一 run 内只有 `test_a_half_sent_request_holds_the_drain_until_the_operator_escalates` 一条传 `entered_marker`，只有一个子进程写它，追加模式无并发。`-p randomly` 的随机顺序不影响 `tmp_path` 唯一性。
- **慢机器/高负载：稳定。** 16 核上开 12-14 路 busy loop，`test_standalone_process.py` 整文件跑 3 轮全绿（18.6s / 17.4s / 17.5s，无负载时 12-14s）。`wait_for_arrivals` 的 10 秒预算相对实测的毫秒级进入延迟非常宽，且它的失败方向是**有意义的红**（`only N of 2 requests reached the handler`），不是静默降级。
- **肯定式取代否定式，判据没被削弱。** 旧写法「1 秒收不到响应」混淆了「handler 在等 body」和「事件循环还没轮到它」，rebase 评审第 3 条点名的正是这个；marker 文件排除了混淆项，同时把固定 2.0 秒的开销降到毫秒级。marker 在 `await request.body()` **之前**写，所以即使信号恰好落在写 marker 与 await 之间，该请求也已经是 `server_state.tasks` 里的在途任务，排空照样等它——判据不受影响。
- 一个不构成问题的观察：handler 里做的是阻塞式文件 I/O（`open`/`write`/`flush`），跑在事件循环线程上。这是测试夹具，写入量是一行，不值得改。

---

## 发现清单

### F-1【major】`refused_requests` 在真实关停路径上恒为 0，而客户端真实付出的代价被记成了良性计数

**严重度：major（可观测性准确性，非功能缺陷）。置信度：高——真实子进程 + 真实 SIGTERM 实测 5 组，在制进程实测 6 组，共 11 次全部同向。**

`refused_requests()` 的 docstring 写：

> The one number in a shutdown report that says a client went without. ... a restart that declined none is a restart nobody noticed.

实测正好相反。`probe_process.py` 起真实子进程、真实 SIGTERM、真实池化 socket，扫描「信号到客户端下一次写」之间的间隔：

```
gap=0.0    client saw: recv failed: ConnectionResetError  refused=0 asked_to_close=1 stage=DRAINING
gap=0.0    client saw: recv failed: ConnectionResetError  refused=0 asked_to_close=1 stage=DRAINING
gap=0.005  client saw: clean EOF, no answer               refused=0 asked_to_close=1 stage=DRAINING
gap=0.05   client saw: clean EOF, no answer               refused=0 asked_to_close=1 stage=DRAINING
gap=0.3    client saw: clean EOF, no answer               refused=0 asked_to_close=1 stage=DRAINING
```

在制进程版（`probe_count.py`，6 组）结论一致，收尾行一律是 `[ OK ] stopped — 1 connections asked to close`。

**机制**：`stop_admitting()` 在**同一个锁块里**先置拒绝态、再逐条 `connection.shutdown()`。对一条空闲的池化连接，uvicorn 的 `cycle is None` 分支直接 `transport.close()`，于是那条 socket 当场消失。客户端随后（哪怕只晚几十微秒）发出的请求根本没有 socket 可落地——早到就是 RST（内核收到未被读取的字节时发 RST 而非 FIN），晚到就是裸 EOF。**两种情况都不经过闸，因此都不计数。**

要让 503 真正发出，必须在 `stop_admitting()` 执行的那一瞬间就已经存在一个**被 h11 解析成活跃 `RequestResponseCycle` 并挂在闸上**的请求。而 `serve()` 里 `stop_accepting()` 与 `stop_admitting()` 之间的窗口宽度实测为 0 个 tick（见项 2），plain 模式下**没有任何时机能产生这个状态**。唯一能产生它的是手工驱动适配器——也就是 `test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` 干的事，以及 `both` 模式的 F-4 窗口。

**为什么这仍然值得判 major**：这条计数是为回应旧评审 5.5 而加的，5.5 引的是项目记忆 `absence-is-not-readable-on-a-log-line`——「字段有才打印，于是没观测到和不报这项同形」。现在的结果是：**同形没有被消除，只是换了个地方**。运维读到 `[ OK ] stopped — 1 connections asked to close`，而实际发生的是一个池化客户端的 `POST /v1/messages` 被 RST 掉了（对非幂等请求这不可重试）。更糟的是这个数字被 docstring 和修复文档双双背书成「唯一说明有人没被服务的那个数」，会让下一个人拿它当判据。

另外要指出一个**处置组合的漏缝**：修复文档把旧评审 4.4（RST）记为「不采纳」（理由是关任何 keep-alive 连接的固有代价、ROI 不明），同时把 5.5 记为「已采纳」（加计数）。两条分开看都说得通，合起来的效果是：**被判为不修的那个代价，恰好也是新加的计数看不见的那个代价**。这不是任何一份评审自己的问题，是两次处置之间的缝。

**可选处置**（我只列，不建议在本次强行处理，且第 1 条与第 3 条是两种不同的产品取舍，够格上交裁决）：

1. 把「关掉一条连接时它的内核接收缓冲里还有未读字节」这一格单独计出来（`transport.close()` 前先 `sock.recv(1, MSG_PEEK | MSG_DONTWAIT)` 探一下），这才是「有人真的没被服务」。代价是多一次系统调用和对 uvicorn transport 内部的依赖。
2. 最小改法：把 `refused_requests()` 的 docstring 从「唯一说明有人没被服务的那个数」降级为「被闸当场答成 503 的请求数」，并在 `connections_asked_to_close` 旁边写明它同时覆盖了「客户端的下一次请求会撞空」这件事。纯文字，零风险。
3. 反过来考虑：既然池化连接被关掉本身就带着代价，`connections_asked_to_close` 非零是否也该影响收尾行的判定。**我不倾向这条**——它会让每次正常关停都报 fail，正是 `cli.py` docstring 已经论证过要避免的。但「关了一条其实有在途字节的连接」与「关了一条真空闲的连接」是两回事，如果走第 1 条就自然分开了。

### F-2【minor】`refused_requests` 整条特性零测试覆盖，包括那条被 docstring 重点强调的 incident 判定

**严重度：minor（守卫缺口）。置信度：非常高——两个变异全绿，且在评审对象与当前 HEAD 两棵树上分别复现。**

- 变异 **E_no_count**（删掉 `self._refused_requests += 1`）：`1a7353e` 树 **56 passed 全绿**，HEAD 树 **56 passed 全绿**。
- 变异 **G_cli_clean**（`clean = not incidents` 改回 `clean = not parts`，即让「asked to close」也能把行判成 fail）：`1a7353e` 树 22 passed 全绿，HEAD 树同组 56 条 **56 passed 全绿**。

这一条**没有**被并行审计覆盖，也**没有**被 `5968067` 修到——那条提交补的是 `test_the_drain_lets_go_of_an_idle_pooled_connection`，与计数和 incident 判定无关。

`rg` 复核：全仓库没有任何测试构造过 `refused_requests` 非零的 `ShutdownReport`，`tests/unit/test_shutdown_reporting.py` 的 `_lines()` 只取 `event` 字段、**从不断言 `status`**，所以 `ok`/`fail` 这个判定在整个测试套件里没有任何守卫。`test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` 确实产生了一次拒绝，但它 `await asyncio.wait_for(serving, 5)` 之后把 report 丢掉了，没有断言。

`cli.py::report_shutdown` 的 docstring 用整整一段论证「Connections asked to close ... never make the line say `fail`」——这是本次增量里论证最用力的一条产品判断，而它一个字都没被钉住。

**建议**（一条就够，不要建门禁）：在 `test_shutdown_reporting.py` 里加一条，构造 `ShutdownReport(stage=DRAINING, connections_asked_to_close=2, refused_requests=1)`，断言行文与 `status`。同时把 `_lines()` 扩成也能取 `status`（现在取不到）。`probe_report.py` 的输出可直接当作期望值。

### F-3【minor】`pause_admission()` 清拒绝态，使「已唤醒但未恢复」的等待者从被 503 变成被正常服务

**严重度：minor（潜伏，当前不可达）。置信度：高（机制已实测复现），高（不可达性有 tick 实测）。**

`asyncio.Event.set()` 会 resolve 所有等待中的 future，随后的 `clear()` **撤不回**已被唤醒的等待者——旧评审 1.4 已指出这一点。本次把 `pause_admission()` 做成「清拒绝态 + clear 事件」之后，这条路径的后果变了：

| | 唤醒后被 `pause` 抢先，等待者恢复时读到 | 结果 |
|---|---|---|
| 改动前（路由器只 `admission.clear()`） | `refusal = 'server is shutting down'` | 503，正确 |
| 改动后（`pause_admission()`） | `refusal = None` | **落到 `loaded_app`，被正常服务** |

`probe_woken.py` 手工构造这个交错并实测：

```
parked at the barrier, refusal = None open = False
after the burst, refusal = None open = False
the woken request received: HTTP/1.1 200 OK
```

注意最后一行与倒数第二行的组合——**闸是关的，请求却被服务了**。

**当前不可达**，我逐条核对过：`serve()` 里 `stop_accepting`（pause）排在 `stop_admitting`（refuse）**之前**，所以第一次 pause 时根本还没有拒绝态可清；`_finalize()` 里路由器第二次 `stop_accepting` 确实排在 refuse 之后，但此时 `routing_tasks` 已空（accept socket 在第一次就关了，不会再产生新的路由任务），`asyncio.gather` 被跳过，pause 与紧随其后的 refuse 在同一个 tick 内完成（实测 tick 差 0），期间没有任何等待者能被调度。FINALIZING 那一支上这些任务已被 `cancel_requests()` 取消，恢复时抛的是 `CancelledError` 而不是继续往下走。

**为什么仍要记**：不可达性依赖两件实现细节——`asyncio.Lock` 无竞争时不让出、以及第二次 `stop_accepting` 时 `routing_tasks` 恰好为空。这两件事都没有任何东西在守。一旦有人在 `stop_admitting` 与 `_finalize` 之间加进任何挂起点，症状就是「关停期间偶尔还会正常服务一个请求」——比 503 难查得多。最小的加固是让 `pause_admission()` 不碰拒绝态（回到只 clear 事件），把清拒绝态的职责留给 `open_admission()`；那会让 `_close_registrations_locked(STOPPED)` 与 `_register_dormant_locked` 少清一次，需要另外确认那两处是否依赖它。**我不建议在本次改**，只建议在 `pause_admission()` 的 docstring 里写明「清拒绝态这一半的前提是：调用它之前不存在已被唤醒的等待者」。

### F-4【minor】`both` 模式下 `pause → refuse` 之间存在真实窗口，因而 `refused_requests` 可以非零，例行重启可能报 `fail`

**严重度：minor。置信度：高——tick 实测。**

项 2 里量到的零宽窗口有一个前提：路由器 `stop_accepting()` 的 `if routing_tasks: await asyncio.gather(...)` 被跳过。给探针加上一条「已 accept 但一个字节都没发」的连接（这在生产里就是一个刚连上还没发 TLS ClientHello 的客户端），窗口立刻打开：

```
--- 1 routing tasks pending ---          243725  None / True
pause_admission                          243726  None / False
refuse(server is shutting down)          243729  'server is shutting down' / True     ← 差 3 个 tick
```

落进这 3 个 tick 的请求（来自一条已被内层适配器接管的池化连接）会挂在闸上，随后被 `stop_admitting` 答成 503 并计数。**这是 plain 模式之外唯一能让 `refused_requests` 在生产里非零的路径**，也就意味着：跑 `tls_mode=both` 的部署，滚动重启偶尔会打出 `[FAIL] stopped — ... , 1 requests refused`，而那次关停其实完全正常（客户端拿到 503 并该去重试新进程）。

这与 F-1 是同一枚硬币的两面：**该计的没计到，不该报 fail 的偶尔会报**。两条一起看，`refused_requests` 作为 incident 的产品定位值得重新确认一次，这是一个够格上交给用户裁决的分叉，不该由实现者或我单方面定。

### F-5【minor】`refused_requests` 是进程累计量，却被放进「本次关停的代价」里

**严重度：minor（潜伏）。置信度：高——源码阅读。**

`self._refused_requests` 从 `__init__` 起只增不减，`open_admission()`／`pause_admission()`／`resume_accepting()` 都不重置它。而 `ShutdownReport` 的另一个新字段 `connections_asked_to_close` 是 `stop_admitting()` 这**一次调用**的返回值。同一个 dataclass 里两个字段的时间尺度不一样，而 dataclass 的 docstring 说自己描述的是「What the shutdown actually did」。

今天无害（一个进程只关停一次）。但 `lifecycle.md` 第 81 行把 `RESUME` 明确列为运行时信号，而本次新增的 `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503` 正是在为那条路径铺路：一旦控制面接上 quiesce/resume，某次 quiesce 期间产生的拒绝会被算进最终那次关停的报告里。它现在断言的 `refused_requests() == 0` 之所以成立，只是因为那次 quiesce 恰好没有请求落进来。

**建议**：要么在 `open_admission()` 里重置，要么让 `stop_admitting()` 返回一对（asked, refused-so-far）并由 `_descend` 做差。我倾向后者——重置会让一个「本进程一共回绝过多少」的指标失去意义，而做差保住两种读法。不阻塞。

### F-6【minor】`stop_admitting` 的取锁理由已被本次新增的公开无锁写入者部分推翻

**严重度：minor（文档准确性）。置信度：高——源码阅读。**

`stop_admitting` 的 docstring 末段：

> Takes the lock although `interrupt_connections` does not, for the refusal rather than the connections: the refusal is one half of a two-field barrier state that the arm and register paths also write, and **those hold this lock**.

这句话在本次增量之后不再完整成立：`listener.py:216` 与 `listener.py:234` 的两个写入者（路由器的 arm 与 stop_accepting 路径）**不持有这把锁**，它们持有的是路由器自己的那把。按这段理由读下去，读者会推断出一个不存在的互斥关系。

有意思的是，**取锁本身是对的，只是理由写偏了**。真正的理由我核对到了：`UvicornListenerAdapter._arm_locked` 在 `try` 块里 `await registration.start_serving()`，然后才 `self.open_admission()`——这中间有一个真实的挂起点。若 `stop_admitting` 不取锁，它完全可以在那个挂起点插进去置上拒绝态，然后被随后恢复的 `_arm_locked` 里的 `open_admission()` 清掉，结果是「关停已经宣布，闸却重新开着」。锁挡住的是这一格。路由器那边之所以不需要锁，是因为它的 `_arm_locked` 与 `_register_dormant_locked` 都是同步的、锁块内无 `await`，写入相对事件循环原子。

**建议**：把 docstring 改成上面这个理由，并在 `open_admission()`／`pause_admission()` 的 docstring 里写明「调用者负责在自己的锁域内保证不与内层的 arm/register 交错；今天成立是因为路由器这两条路径全同步」。纯文字。

### F-7【minor】`FirstByteRoutingAdapter.stop_admitting()` 与 `refused_requests()` 不取路由器自己的锁，而同族的 `stop_accepting()` 取

**严重度：minor（形状不一致）。置信度：高——源码阅读。**

`listener.py` 里 `register_dormant`／`arm`／`stop_accepting`／`resume_accepting` 都是 `async with self._operation_lock:` 开头，而本次新增的 `stop_admitting()` 直接转发、`shutdown_lifespan()` 也不持锁（它靠内部调用的 `stop_accepting()` 自己取）。今天没有并发缺陷——所有调用都来自 `StandaloneServer.serve()` 这一条串行协程。但这让「路由器的锁保护什么」变成一个要逐个方法读才能回答的问题。

顺带一条同族的：`FirstByteRoutingAdapter.stop_admitting()` 的注释断言「`stop_accepting` has already dealt with this router's own half」。这个断言我核对属实（`stop_accepting` 会关掉 `_pending_sockets` 并 cancel 掉 `_routing_tasks`），而且 `serve()` 确实是这个顺序。但它是一条**隐式前置条件**：`ListenerLifecycle` 协议允许任何调用者单独调 `stop_admitting()`，那样 `_pending_sockets` 里的连接会被留下。注释写了，没有任何东西强制。记录，不建议加断言。

### F-8【nit】`_descend(self, asked_to_close: int = 0)` 的默认值

唯一的调用点总是传值。默认值在这里的作用只是让「忘了传」变成静默的 0，而这个 0 会原样进 `ShutdownReport`。去掉默认值成本为零，pyright 会替你抓住下一个调用者。

### F-9【nit】收尾行把良性计数排在事故前面，与 docstring 自述的排序理由相左

`report_shutdown` 的 docstring 说「Ordered by what an operator is deciding — whether anything was cut off」，而实现是 `parts = [asked_to_close] ; parts += incidents`，于是运维看到的是 `stopped — 1 connections asked to close, 1 requests refused`——先良性、后事故。实测输出见 F-1 与项 3。改成事故在前更符合它自己写下的排序理由。纯文字量级。

### F-10【nit】`cli.py:198` 的三元表达式挤在一行

```python
parts = [f"{report.connections_asked_to_close} connections asked to close"] if report.connections_asked_to_close else []
```

ruff 放过了（在配置的 line-length 之内），周围每个条件都是一个独立的 `if ... : incidents.append(...)`，只有这一条换了形状。属可读性，不属缺陷。

---

## 我认为没有问题的项（逐条附依据）

| 项 | 判断 | 依据 |
|---|---|---|
| `open_admission`／`pause_admission` 自身不取锁 | **正确且必须** | 三个内层调用点都在 `_operation_lock` 之内，`asyncio.Lock` 不可重入，自取锁会当场死锁 |
| 两个锁域并发写同一对字段 | 无可达竞态 | 路由器的 `_arm_locked`／`_register_dormant_locked` 全同步，`stop_accepting` 锁块内无 `await`；两个字段之间无 `await`，读者不会看到半态 |
| `pause_admission` 清拒绝态在 `shutdown_lifespan` 路径上开新窗口 | plain 模式窗口宽度 **0 tick** | `probe_window.py` tick 实测；`asyncio.Lock` 无竞争不让出，第二次 `stop_accepting` 时 `routing_tasks` 已空 |
| 新到达的请求在该窗口里会不会被服务 | 不会 | `pause_admission` 同时 clear 事件，请求挂在闸上等待，随后被 `_refuse_admission_locked` 唤醒并答 503（F-3 只涉及**已唤醒**的等待者） |
| `_descend` 读 `refused_requests()` 的时机 | 不会漏 | 读在 `await self._finalize()` **之后**，而 `_finalize` → `shutdown_lifespan(None)` → `wait_drained(None)` 是无界等待，被拒绝的 `gated_app` 本身是 `server_state.tasks` 里的任务；`probe_report.py` 实测 `report == adapter` |
| 客户端已断开时仍计入拒绝 | 正确 | 这条数字问的是「有没有人被回绝」；旧评审 5.2 已证实两条 `send` 在 `disconnected` 时静默早返回、不抛、不打 500 日志 |
| 把 refusal 算作 incident 会让例行滚动重启报 fail | **不会**（plain 模式实测 5+6 组 `refused=0`） | `probe_process.py` / `probe_count.py`。但 `both` 模式见 F-4，而「不会」的原因本身是 F-1 |
| websocket 分支 `await receive()` 挂住 | 不会 | `wsproto_impl.py:188` 在 `create_task(run_asgi())` **之前** `put_nowait(websocket.connect)`，`run_asgi` 全仓库仅此一处调用点；`probe_ws.py` 实测 403 立即返回 |
| websocket 拒绝路径的 1012 注释 | 已改成实情 | `probe_ws.py` 实测上线的是 HTTP 403，与新注释一致 |
| `gated_app` 改读 `self._admission_open` | 净改善 | 消除了旧评审 1.5 的跨文件隐式契约；闭包本就持有 `self`，无新增引用 |
| `test_rung_one_delivers_a_response_that_had_already_started_streaming` 的分辨力 | 有，且精确 | 变异 A：56 条里只此一条红 |
| `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503` 的分辨力 | 有，且精确 | 变异 B：56 条里只此一条红 |
| `test_a_pooled_client_that_races_the_signal...` 的分辨力 | 有，实测确定性 | 变异 F：6/6 红（空载）+ 4/4 红（14 路满载）；干净树 4/4 绿、0.8-1.0s |
| marker 文件跨测试污染 | 不存在 | `marker = tmp_path / "entered"`，pytest `tmp_path` 按测试函数分目录；同一 run 内仅一条测试传 `entered_marker` |
| `wait_for_arrivals` 在慢机器/高负载下的稳定性 | 稳定 | 16 核 12-14 路满载，`test_standalone_process.py` 整文件 3 轮全绿（17-19s，空载 12-14s） |
| 改名的彻底性 | 彻底 | `rg` 全仓库；`ListenerLifecycle` 协议与两个测试 stub 同步；pyright 0 error |
| `ListenerLifecycle` 协议新增两个方法后 stub 的诚实度 | 诚实 | `test_lifecycle_cleanup.py` 的 stub 返回 0 并注释了「这里的数字只会是测试发明的」 |
| 静态检查 | 干净 | `ruff check` 四个源文件 + 四个测试文件全过；`pyright src/app/lifecycle src/app/cli.py` 0 errors 0 warnings |
| 测试基线 | 全绿 | 仓库内 56 passed / 21.3s；`1a7353e` 副本树 56 passed 重复 5 次全绿；HEAD 副本树 56 passed |
| 修复文档对本次增量的记录 | 完整且诚实 | `docs/tmp/260820-graceful-shutdown-admission-deadlock.md` 的「评审处置」表逐条列了采纳／不采纳与理由，其中三条变异声称我独立复现属实 |
| `5968067` 对 C2 缺口的修复 | 有效 | HEAD 副本树上 C2 变异使 `test_the_drain_lets_go_of_an_idle_pooled_connection` 变红，该测试现在真的见证了它命名的那一档 |

---

## 范围之外的观察（不属本次增量，仅备案）

### O-1 `both` 模式每次关停都会打一条 `accepted connection routing crashed` 的 ERROR

**既有缺陷，本次增量未引入也未加重。置信度：高——实测复现 + 与父提交（`1475ec7`，即 `f37068c^`）逐行比对确认 `_peek_first_byte` 与 `stop_accepting` 的关闭-取消顺序均未变。**

`FirstByteRoutingAdapter.stop_accepting()` 先 `pending_socket.close()` 再 `task.cancel()`，于是被取消的路由任务在 `_peek_first_byte` 的 `finally: loop.remove_reader(client_socket.fileno())` 上撞到 `fileno() == -1`：

```
accepted connection routing crashed
  ...
  loop.remove_reader(client_socket.fileno())
ValueError: Invalid file descriptor: -1
```

`ValueError` 既不是 `CancelledError` 也不是 `OSError`，`_route_connection` 的两个 except 都接不住，任务于是以异常而非取消结束，`_finish_routing_task` 的 `if task.cancelled(): return` 落空，走到 `LOGGER.error("accepted connection routing crashed")`。也就是说**每一次 `both` 模式的关停，只要当时有一条连接还在等第一个字节，日志里就多一条「崩溃」ERROR**，而它描述的是一次完全正常的关停。

之所以在这里提：本次增量的主题正是让关停的收尾报告说实话，而这条噪声与它同处一条路径、同一时刻，会让 `[ OK ] stopped` 旁边紧挨着一条 ERROR。**最小改法**是在 `_peek_first_byte` 的 `finally` 里判 `if client_socket.fileno() != -1:`，或把 `except OSError` 放宽到也接 `ValueError`。建议单开一条小改动处理，不要混进本次。

### O-2 一次未能复现的 flake

在一轮把 5 个文件一起跑、且机器上还有前几轮残留负载的批次里，`test_sigterm_reaches_the_ladder_in_a_real_process`（**属既有测试，非本次增量**）红过一次。此后单文件 8 次、5 文件组合 5 次、14 路满载 3 次，共约 14 次运行未再复现，我也没能保留当时的失败输出。**权重：仅记录，不足以据此行动。**若日后再见到，方向是 `communicate(timeout=20)` 与真实子进程启动时间的关系。

### O-3 未评审的并行会话在飞改动，以及评审期间的历史重写

工作树里 `src/app/pipeline/`、`src/app/server/handler.py`、`src/app/streaming/`、`tests/http/`、`src/app/tokenization/` 等属于其他会话，按指令未评审、未改动。

评审期间这段历史被并行会话重写：`1a7353e` 不再是 HEAD 的祖先，等价提交为 `f37068c`（`git diff 1a7353e f37068c -- src tests` 为空），随后又有 `5968067`（改我审的两个测试文件）与若干与本次无关的提交。HEAD 从 `219d261` 一路走到 `7fa71f3`。`src/app/cli.py` 相对评审对象出现了 6 增 2 删的漂移——我核对过，全部在 `debug_models` 里，与 `report_shutdown` 无关。**所有结论已按「⚠️ 评审期间历史被重写」一节重新锚定并在 HEAD 上复核，不影响本报告任何发现。**

**给主会话的一条提醒**：`docs/tmp/` 与 `docs/.human-controlled/` 在 `f37068c` 里被移出了版本控制（373 个文件），所以本报告落盘后是未追踪状态。这是并行会话的决定，我只是记录，不作判断。

---

## 处置建议（按我的优先级，均不构成门禁）

1. **F-1 的第 2 条最小改法**（改 `refused_requests()` 与修复文档的措辞，让它们描述实际成立的事）。这是唯一一条我认为应当在本轮内处理的——留着一个说反了的 docstring，比没有这条计数更糟。至于要不要真去量「关掉时缓冲里还有字节」那一格（第 1 条），以及 `refused_requests` 该不该继续算 incident（F-4），这两个都是产品取舍，**建议连同 F-1 的实测数据一起上交用户裁决**。
2. **F-2 补一条测试**。一条就够，在 `test_shutdown_reporting.py` 里；同时把 `_lines()` 扩成能取 `status`。不要为此建任何验证框架。
3. **F-6 改 `stop_admitting` 的取锁理由**，换成真正成立的那个（`_arm_locked` 的 `await start_serving()`）。纯文字，但它决定下一个人对这把锁的心智模型。
4. **F-3 在 `pause_admission()` 写明前提**（调用前不得存在已被唤醒的等待者）。纯文字。
5. F-5、F-7、F-8、F-9、F-10 记录即可，不建议在本次改动里处理。
6. O-1 单开一条小改动。

## 复现指引

全部产物在 `/tmp/shutdelta/`，可直接复用（`/tmp` 内容随时可删，仓库内未留任何文件）：

- 探针：`probe_window.py`（tick 轨迹）、`probe_woken.py`（F-3 的交错）、`probe_ws.py`（websocket 拒绝）、`probe_count.py`（在制进程扫描）、`probe_report.py`（拒绝→报告→收尾行）、`probe_process.py`（真实子进程 + 真实 SIGTERM）。用 `uv run python /tmp/shutdelta/<name>.py` 跑，在仓库根目录下执行。
- 变异（评审对象）：`python3 /tmp/shutdelta/mutate.py <名字>` 打补丁到 `/tmp/shutdelta/tree`（`git archive 1a7353e`），`restore` 还原；跑测试时 `PYTHONPATH=/tmp/shutdelta/tree/src uv run pytest /tmp/shutdelta/tree/tests/... -p no:randomly`。
- 变异（当前 HEAD 复核）：`python3 /tmp/shutdelta/mutate_head.py <名字>` 打补丁到 `/tmp/shutdelta/head`（`git archive HEAD`），用法同上，另含 `G_cli_clean`。
- 名字见上方变异一览表。两棵树在我离开时都已 `restore`，与各自的 pristine 副本逐文件 `diff -q` 一致。
