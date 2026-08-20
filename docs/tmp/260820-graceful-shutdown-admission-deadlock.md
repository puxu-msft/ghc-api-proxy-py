# 优雅关闭卡死：准入闸在关停路径上永不重开

日期：2026-08-20。修复分支：主工作树直接改动。相关代码 `src/app/lifecycle/{adapter,listener,standalone}.py`、`src/app/cli.py`。

## 现象

用户在生产运行中按 Ctrl-C 触发优雅关闭。请求排空后进程不退出，客户端连接仍然保持。升级信号后终端打出两条：

```
[FAIL] Exception in ASGI application
  File "src/app/lifecycle/adapter.py", line 320, in gated_app
    await admission_open.wait()
asyncio.exceptions.CancelledError
```

## 根因

结论强度：**已复现、已定位、已用双向变异验证**，足以据此行动。

`stop_accepting()` 在两处适配器里都会清掉准入闸：`adapter.py` 的 `_close_registrations_locked(STOPPED)` 与 `listener.py` 的 `stop_accepting()`。这道闸的设计用途是**滚动重启的 quiesce → resume**：暂停期间到达的请求原地等待，`resume_accepting()` 之后继续。

关停路径复用了同一个 `stop_accepting()`，但关停之后**永远不会 resume**。于是：

1. 客户端（Claude Code 这类连接池客户端）在排空期间，于已经建立的 keep-alive 连接上发来新请求；
2. 该连接早已被 accept，协议对象存活，请求直达 `gated_app`，停在 `await admission_open.wait()`；
3. 这个任务进入 `server_state.tasks`，而 `wait_drained()` 正是轮询等待该集合清空；
4. 排空按设计是**无界**的（`standalone.py` 模块文档：请求自带 deadline，不叠加第二个墙钟上限），于是永久等待。

第二次 SIGINT 升级到 `FINALIZING`，`cancel_requests()` 取消这些驻留任务，`CancelledError` 从 `gated_app` 逃进 uvicorn 的 `run_asgi`——它 `except BaseException` 后按「应用异常」记日志，这就是那两条 traceback。**两个症状是同一个根因。**

复现脚本（一次性，未入库）：长请求在途 + 一条空闲 keep-alive 连接，发 SIGTERM 后在该连接上再发一个请求，`serve()` 6 秒不返回，traceback 与生产完全一致。

## 修复

新增 `ListenerLifecycle.stop_admitting() -> int`，由 `StandaloneServer.serve()` 在 `stop_accepting()` 之后、下降开始之前调用一次。它做两件事，但**两件事的分量不同**（见下方「被证伪的断言」）：

- **拒绝准入**——**修好死锁的就是这一半**。把闸从「等监听器回来」翻成「这个请求不会被服务」，`_admission_refusal` 置位并 `set()` 事件，驻留中的请求立刻被放行到 503。
- **放掉连接**——**让客户端早点知道的那一半**。对每条连接调 `connection.shutdown()`。空闲的 pooled 连接当场关闭；仍在跑请求的那条只被清掉 `keep_alive`，响应结束后才关——**这不是中断档**，在途请求不受影响，已经开始写的响应会完整送达。

`stop_accepting()` 的暂停语义原样保留，滚动重启路径不受影响。

被拒绝的请求得到 `503` + `connection: close` + Anthropic 错误信封 `overloaded_error`。选这个信封是因为到达本代理的流量几乎都在说 Anthropic 协议，客户端会把 `error.message` 渲染给人看；WebSocket 走 `websocket.close` 1012（滚动控制面已在用这个码）。**这一项是我的选择，不是既有裁决**，若不合意可改。

`ShutdownReport` 增加两个字段。`connections_asked_to_close` 进 CLI 收尾行但**不参与 `clean` 判定**——通知连接关闭是健康关停的常态，混进事故列表会让每次正常关闭都显示 `fail`。`refused_requests` 则**进** incidents：被拒绝的请求意味着真有客户端没被服务，那是一次关停实际付出的代价。

## 一个必须记下来的发现：有测试在钉 bug

`tests/integration/test_standalone_process.py::test_a_half_sent_request_holds_the_drain_until_the_operator_escalates` 在修复后变红。

它的**意图正当**：body 还在路上的请求是真请求，第一档应当等它。但它的**夹具表达不了这个意图**：

- 子进程夹具是一个只注册了 GET `/health/liveness` 的裸 FastAPI；
- 测试发的是 `POST /health/liveness`，Starlette 只看 headers 就回 405，**从不读 body**；
- 直接探测证实：**在任何信号之前**，服务器就把 405 发回来了，没有任何 handler 在等 body。

拆半实验进一步定位：只保留「拒绝准入」而不关连接，该测试同样变红。所以撑住排空的从来不是在途请求，而是**闸口死锁本身**。测试之所以一直绿，是因为它断言的那个「进程还活着」恰好是 bug 的副作用。

处置：**不削弱契约，改夹具让它真能表达契约**。子进程新增 `POST /swallow`，handler 里 `await request.body()`；测试改发这个路由，并在发信号前等 handler 自己写出的就绪信号——原来的写法在 `sendall` 后立刻发信号，没有任何同步，本身就是竞态。改完后该测试通过，且对「第一档过度关停」有分辨力。

**评审补上了这个处置漏掉的一半**：老测试的场景（不同步、发完立刻发信号）虽然期望写错了，却是**唯一一条会因死锁在真实进程里复发而变红**的测试。只改夹具等于把这层守卫一并搬走。所以那个场景被保留下来、换上正确的期望，成为 `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process`。

## 验证

### 真实 CLI 端到端（最有分量的一条）

在真实入口 `uv run ghc-api-proxy start` 上跑，独立端口与独立 pidfile，只对自己启动的子进程发信号（未触碰 4141 的既有服务）。场景按生产形状构造：

- A：`POST /v1/messages`，声明完整 Content-Length 但只发一部分 body —— handler 卡在等 body，**排空窗口因此被合法地撑开**；
- B：一条普通 pooled keep-alive 连接，收到 SIGTERM 之后在这条连接上再发一个请求；
- 然后补齐 A 的 body，让 A 正常完成 —— 此时**没有任何正当理由再等下去**。

结果：

| 构建 | 结果 |
|---|---|
| 变异版（`stop_admitting()` 不调用，等价缺陷在） | **HUNG** —— A 完成 15 秒后仍在运行 |
| 修复版 | A 完成后 **1.8 秒退出**，收尾 `stopped — 2 connections asked to close`，状态 OK，无 traceback |（评审后改动落定再跑一次：2.0 秒退出，同样干净）

两次运行里 A 都拿到了真实上游的 200（日志 `H1/H2 200 anthropic-messages/gpt-5.5 → gpt-5.6-terra`）——**第一档没有截断在途工作**，这是修复必须同时守住的另一半。

**一条关于探针本身的教训**：第一版 e2e 只开一条空闲 pooled 连接、不制造在途请求，结果修复版与变异版**都在 1 秒内正常退出**——因为没有在途请求时整个关停在毫秒级走完，第二个请求根本落不进那个窗口。那一版的绿完全没有分辨力。生产之所以撞上，正是因为当时有响应在跑撑开了窗口。**探针必须先证明它能看见坏行为，它的绿才作数。**

### 单元与集成

- 复现脚本：修复前挂起并打出与生产同形的 traceback；修复后干净退出，在途长请求仍拿到 200。
- 变异验证（做完即还原，`rg MUTATION` 已确认无残留）：
  - 把 `stop_admitting()` 调用改成 `0` → 「pooled 连接中途发请求」测试 `TimeoutError`（与生产同形）、「空闲连接被放掉」断言失败，评审后新增的真实进程测试 `TimeoutExpired`。
  - 让 `stop_admitting()` 顺手 `cancel_requests()`（一个看似合理的过度修法）→ **8 条红**，三档守卫全在内，含既有的 `test_the_first_signal_stops_accepting_but_lets_a_request_finish`。（我原先只点了三条，是低报；红名单规模由独立审计复算得出。）
  - 只切「已开始写、尚未写完」的响应 → **只有**新增的 SSE 测试变红（9 块只到 1 块），其余全绿——这正是评审证明的那个盲区。
  - 让 `open_admission()` 只开闸不清拒绝态 → 新增的 resume 测试变红，复现出 resume 后的永久 503。
- 全量：**1419 passed / 2 skipped**，在 `/tmp` 的干净 clone、checkout 到本次提交上测得。Ruff `check` 与 Pyright 在全部改动文件上干净。

  ⚠️ 我先前在正文与对话里报过 1415／1424／1425 三个数，**那些都是在主工作树上量的，而主工作树混有并行会话的在飞测试改动，因此在本提交上不可复现**。一个在脏树上量出来的基线数字，最有害的用法就是被下一个人拿去做对比。以干净 checkout 的 1419 / 2 为准。

注：本次全量之前的一轮里 `tests/http/test_pipeline_app.py` 有两条红，属并行会话正在编辑该文件的在飞改动，与本次无关；重跑已绿。同一批在飞改动也是上面那个数字差额的来源。

## 新增测试

`tests/integration/test_standalone_lifecycle.py`：

- `test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open` —— 本次事故的形状本身（整体回归；实际由「关连接」那一半兜住，见评审 6.3 的处置）。
- `test_the_drain_lets_go_of_an_idle_pooled_connection` —— 用客户端自己的 socket 收到 EOF 作证，而不是只信服务端报的计数。
- `test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` —— 503 那条路径；直接驱动适配器，因为窗口在它两个调用之间，靠信号去卡这个微秒数只是在测调度器。
- `test_rung_one_delivers_a_response_that_had_already_started_streaming` —— 评审后补。已经在写的响应必须完整送达，含 chunked 终止块。

`tests/integration/test_standalone_process.py`（真实进程 + 真实信号）：

- `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process` —— 评审后补。保留老测试的场景，换成正确期望，重新守住事故发生的那一层。
- `test_a_half_sent_request_holds_the_drain_until_the_operator_escalates` —— 夹具重写：真读 body 的路由 + 肯定式就绪信号。

`tests/integration/test_listener_quiesce_resume.py`：

- `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503` —— 评审后补。`both` 模式 resume 之后必须恢复服务，而不是永久 503。

## 影响面

只影响**自持监听器的直接运行路径**（`run_standalone` → `StandaloneServer`），也就是 `uv run ghc-api-proxy start` 与 `--restart` 平滑重启。准入闸只在 `UvicornListenerAdapter.startup_lifespan()` 里安装，因此只有这条路径有这道闸，也只有它会死锁。

`--fd` 继承监听器的 systemd 路径走的是 `cli.serve_inherited()`，直接用 `uvicorn.Server.serve()`，从不安装这道闸，因此**不受此缺陷影响，也不被本次修复改变**。

## 未处理 / 待裁决

- **滚动重启路径的同一道闸未动。** `systemd-rolling/spec.md` 写着「仅 TCP 已 accept 不构成 drain 资格」，按这句话，quiesce 期间在已建连接上到达的请求是否也不该被原地挂住，是同一族问题。本次不扩大范围，留作提醒。
- 503 错误信封的具体形状（Anthropic `overloaded_error`）是我选的默认，未经裁决。


---

# 评审处置（2026-08-20）

派了两名异源评审，各自只读取证、全部实验在树外进行：

- `260820-shutdown-test-rebase-review.md` —— 专审「改掉挡路的既有测试是否护短」。结论：**正当，非护短，置信度高**。四组对照（老/新测试 × 修复前/后源码）中最关键的一格是「新测试在修复前的源码上同样通过」，说明它钉的是契约而非本次实现；断言无一被削弱。
- `260820-shutdown-fix-review-gpt.md` —— 并发与生命周期方向的对抗评审。**blocker 0、major 2、minor 7、nit 5、verified_ok 16**。

## 被证伪的两处断言（我原报告写错了）

1. **「拒绝准入与放掉连接缺一不可」不成立。** 评审做了双向半拆变异：只留放连接 → 1 条红；**只留拒绝 → 全绿**。因为 `shutdown_lifespan` 本来就会关连接，排空照样结束。正确的说法是**拒绝是必要的那一半，放连接是「更早告知」**，仍值得保留（缩短 pooled 客户端继续投递的窗口，也缩小下述 RST 窗口），但不是同等必要。已改正文与 `stop_admitting` 的 docstring。
2. **「两个症状同一根因」容易被误读成「升级后也不再有 traceback」。** 实际是：第一档那次**不该发生的** traceback 没了；第二档只要真的取消了请求，每取消一个仍会打一份，那是语义正确的。

## 采纳并已落地

| 来源 | 问题 | 处置 |
|---|---|---|
| gpt 3.2（major）+ rebase 评审 | `both` 模式下 `resume_accepting()` 清不掉 `_admission_refusal`，resume 后**所有请求永久 503**、而监听器看着完全健康 | 新增 `open_admission()` / `pause_admission()` 一对公开方法，内层与路由器都走它；`listener.py` 不再伸手摸私有字段（顺带删掉两处 `reportPrivateUsage` 豁免）。补测试 `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503`，变异（退化成只开闸不清拒绝态）实测变红并复现出评审预言的 `503 "server is shutting down"` |
| gpt 4.3（major） | 「第一档不截断已开始写的响应」**零分辨力**：评审的截流变异下 84 条测试全绿而 SSE 停在第 2 块 | 新增 `/stream` 路由与 `test_rung_one_delivers_a_response_that_had_already_started_streaming`（9 块 + `[DONE]` + chunked 终止块 + `cancelled_requests == 0`）。复刻该变异实测：**54 条中只有这一条变红**，抓到 9 块只到 1 块 |
| rebase 评审 M1 | 夹具重写后，**真实进程这一层不再守卫死锁复发**（此前唯一的真实进程守卫恰是那条钉着 bug 的测试） | 新增 `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process`：保留老测试的**场景**（不同步、发完立刻发信号），换成正确期望（单次信号即以 `STOPPED DRAINING` 退出，且 stderr 无 `Exception in ASGI application`）。M1 变异下实测 `TimeoutExpired` 变红 |
| rebase 评审第 3 条 | 发信号前的同步是**否定式**证据（「1 秒收不到响应」既可能是 handler 在等 body，也可能是还没轮到它），且固定花 2 秒 | 换成**肯定式就绪信号**：`/swallow` handler 入口按行追加 marker 文件，`wait_for_arrivals()` 轮询。混淆项消除，耗时降到毫秒级 |
| gpt 5.5 | 被拒绝的请求**不留任何痕迹**——闸在 pipeline app 之上，不进请求日志、不进 TUI、不进报告，于是「没人被拒」与「不报这项」同形（项目记忆 `absence-is-not-readable-on-a-log-line`） | 新增 `refused_requests` 计数，进 `ShutdownReport`，且**进 incidents**：被拒绝的请求是真有人没被服务，与「放掉空闲连接」不是一回事 |
| gpt 6.1 | `released_connections` 名不副实：计的是被通知的连接，实测 1 空闲 + 1 在跑 → 报 2 | 改名 `connections_asked_to_close`，CLI 打「N connections asked to close」，与既有 `interrupt_connections` 的诚实措辞一致 |
| gpt 1.5 | `gated_app` 按值捕获 `admission_open` 而按 `self` 读拒绝态，使「此 Event 不得重绑」成为跨文件、无声明、无测试的不变量 | 改为一律读 `self._admission_open`，并写明理由 |
| gpt 5.3 | `REFUSAL_WEBSOCKET_CODE = 1012` 是**事实上的死常量**：握手前的 `websocket.close` 被 uvicorn 转成 HTTP 403，码与 reason 都被丢弃 | 注释改写为实情（保留常量表达意图，但说明当前没有任何下游看得到这个数字） |
| gpt 5.4 | 拒绝 websocket 前未先 `receive()` `websocket.connect` | 补上，符合 ASGI 惯例 |
| gpt 6.4 | `stop_admitting` 取锁而语义相近的 `interrupt_connections` 不取，读者会推断存在竞态 | docstring 写明取锁是为拒绝态（它与 arm/register 路径共写同一份闸状态），不是为连接 |
| gpt 6.5 + rebase 评审 | `begin_draining` 与 `observability.active_requests.begin_draining` 同名不同义，且在 `cli.py` 同一行相邻出现 | 改名 `stop_admitting`。顺带更准：它在 `serve()` 里紧跟 `stop_accepting`，读作「停止 accept 连接，停止 admit 请求」 |
| gpt 6.3 | 头号新测试的 docstring 声称它验证拒绝机制，实际零分辨力（0.2 秒时连接已关，第二个请求从未到达 handler） | 改写 docstring 说明它实际证的是什么、哪一条覆盖另一半。**不改测试**：它是事故本身的形状，整体回归价值独立成立 |

## 记录但不采纳

- **gpt 4.4（minor）**：第一档关空闲 keep-alive 连接会让恰好在途的字节变成 RST 而非干净 EOF。这是关闭任何 keep-alive 连接的固有代价，uvicorn 自己的 `Server.shutdown` 也一样；消除它要先 `SHUT_WR` 再等对端关闭，需额外状态跟踪。**在有实际投诉之前 ROI 不明确，按评审本人的倾向记录不改。**
- **gpt 4.2（minor）**：`WSProtocol.shutdown()` 无条件 `transport.close()`，所以第一档会直接切活跃 websocket。当前 `create_pipeline_app` 的 18 条路由全是 `APIRoute`，无 `WebSocketRoute`，不可达。哪天挂上 ws 路由需要重新看。
- **gpt 2.2（minor）**：路由器的 `stop_accepting()` 会在拒绝态置位后再清一次闸，形成一个「拒绝态在、闸却关着」的窗口。当前窗口长度为零（其间无真实挂起点）。改法会给一条不可达路径加分支，暂不动。
- **gpt 6.6（nit）**：`startup_lifespan` 二次调用会二次包装 `gated_app`。既有问题，本次未加重也未减轻。
- **gpt 6.1 的首选改法**（只统计真正当场关掉的连接）：需要读 uvicorn 的 `cycle.response_complete` 内部状态，会随上游重构**静默**给出错误数字。改名后这个数说的就是它算的东西，选了后者。

## 待裁决

- 503 错误信封形状（Anthropic `overloaded_error`）与 WebSocket 1012 的意图，是我选的默认，未经裁决。
- 滚动路径「quiesce 期间在已建连接上到达的请求是否该原地挂住」——`systemd-rolling/spec.md` 写着「仅 TCP 已 accept 不构成 drain 资格」，与当前挂住的行为存在张力。本次未动。
- 评审顺带提示：工作树里 `tests/http/test_pipeline_app.py` 删掉了 `test_count_tokens_refuses_a_model_that_advertises_other_endpoints`（原断言 400 + `EndpointNotSupported`，改为 200 + 本地估算）。那属于**其他会话的在飞改动**，不在本次范围；是否已被裁决只有你知道。

---

# 变异审计处置（2026-08-20，提交 `1a7353e` 之后）

报告：`docs/tmp/260820-shutdown-mutation-audit.md`。审计者在 `/tmp` 的干净 clone 上逐条复算了上面「变异验证」的四条声称，每条跑全量、竞态项另做 10 次隔离重复。

**结论：四条声称全部成立**——红名单、失败异常类型、具体断言值（`assert 1 == 9`、503 报文原文）逐一对得上，没有一条是「跑过了、变红了」的空口声称。第 2 条是**低报**（实测 8 红，我只点了 3 条），方向对结论无害但会让读者低估爆破半径。

## 采纳并已修

| 发现 | 问题 | 处置 |
|---|---|---|
| 4.1 | 全量数字 **1424 不可复现**：那是在混有并行会话在飞改动的脏树上量的，干净 checkout 上是 1419 / 2 | 正文已改为 1419 / 2 并注明测量位置，同时标出先前三个数字都不该被当基线 |
| 发现 A（major） | `test_the_drain_lets_go_of_an_idle_pooled_connection` **对它自称在证的东西零分辨力**：E1（第一档一条连接都不关）下 10/10 全绿。两条断言各自失效——计数是 `len(connections)`，与是否真调过 `shutdown()` 无关；而 EOF 读在 `serving` 完成**之后**，那时 `shutdown_lifespan` 早已把连接关了，EOF 来自收尾而非第一档 | 加一个在途 `/slow` 请求把排空窗口撑开，把 EOF 的读取挪到 `serve()` 返回**之前**，并断言 `serving.done() is False`——此时收尾还没跑，EOF 只有一个可能来源。实测：E1 下 **5/5 变红**（改前同一变异 10/10 全绿），干净码 5/5 通过 |
| 发现 B（minor） | `test_a_pooled_connection_that_sends_mid_drain...` 的 docstring 写「measured, by removing each half in turn」来支撑**排他归因**（「救它的是关连接不是拒绝」）。实测两半各自去掉它都绿，只有两半都没有才红——那个测量恰恰**不**支持排他归因 | docstring 改为：它抓的是整体机制回归；「未变异时走关连接那条路」是对路径的描述，不是「只有这条路救得了它」的主张 |
| 发现 C（minor） | 真实进程竞态守卫的 docstring 称自己是「唯一会注意到死锁复发的断言」，读起来像一道确定性防线。实测检出率是概率性的：干净码 0/10（无假红）、整体移除 10/10、死锁机制复活 4/10、只删拒绝 2/10 | docstring 写明它是**概率性守卫**并附实测数量级：一次绿不等于守住了，一次红一定是真的 |
| 第 2 条声称 | 红名单低报（3 → 8） | 正文已改，并注明原数是低报 |

## 记录但不改

- **发现 D**：真正承重的那一半（拒绝准入）在全量 1421 条里只有 `test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` 一条**确定性**守卫（真实进程那条只有 2/10）。它直接驱动 adapter，守的是 `stop_admitting()` 的内部契约；关停路径的接线另有三条守着。两层各有守卫、无缺口，但承重半边的确定性守卫只有一条——记录下来，不为此再加测试。
- **发现 E**：E3 变异顺带打红 `test_partial_arm_failure_rolls_back_all_registrations`，说明「置拒绝态时必须开闸」这条不变量在 arm 失败路径上也有守卫。正面信息，无需处置。
- **4.3**：`--fd` systemd 路径不受影响的陈述**属实**，审计者穷尽枚举了 `_install_admission_barrier()` 的调用点。限定条件：静态可达性分析，未在运行时实际拉起 `--fd` 路径验证。
- **4.4**：复现脚本与真实 CLI 端到端两节依赖未入库的一次性脚本与真实上游凭据，审计者无法复算，对其不作判断。

---

# 增量评审处置（2026-08-20，第三轮）

报告：`docs/tmp/260820-shutdown-delta-review.md`。审的是「回应第一轮评审后又改的那批东西」——那批改动此前没有被任何人看过。**blocker 0、major 1、minor 6、nit 3**，机制部分逐项做了变异或探针确认：`open_admission()`/`pause_admission()` 跨两个锁域调用安全（plain 模式下 pause→refuse 窗口实测 0 个 event-loop tick）、websocket 的 `await receive()` 不会挂（实测 403 立即返回）、三条新测试各自被变异打红且只打红对应那条、marker 同步在 16 核 14 路满载下稳定无污染。

## 唯一的 major：我加的那个计数没做到它声称的事

`refused_requests` 是我在第一轮评审后自己加的，用来回应「被拒绝的请求不留痕迹」。**实测它在真实关停路径上恒为 0**——真实子进程 + 真实 SIGTERM 共 11 组，全部 `refused=0`、收尾行 `[ OK ]`。

机制：`stop_admitting()` 在同一个锁块里先置拒绝态、再关连接。空闲池化连接走 uvicorn 的 `cycle is None` 分支直接 `transport.close()`，于是客户端随后的请求根本没有 socket 可落地——早到是 RST，晚到是裸 EOF，**两者都不经过闸，都不计数**。要真发出 503，必须在那一瞬间就已经有请求挂在闸上；plain 模式下 `stop_accepting` 与 `stop_admitting` 之间实测 0 tick，没有任何时机产生这个状态。

评审同时指出一个**处置组合的漏缝**，这条最值得记：我把 RST（旧评审 4.4）记为「不采纳，ROI 不明」，又把「加计数」（旧评审 5.5）记为「已采纳」。分开看都成立，合起来的效果是——**被判为不修的那个代价，恰好就是新计数看不见的那个代价**。项目记忆 `absence-is-not-readable-on-a-log-line` 说的同形没有被消除，只是换了个地方。

**处置：不删计数，但纠正它的定位，并把它从事故降级。**

- docstring 从「唯一说明有人没被服务的那个数」改为「被闸当场答成 503 的请求数」，并写明在关停路径上应当为 0、以及为什么 0 不等于「没人受影响」。
- **从 incidents 移出**。真正的倒置在于：被 503 干净回绝的客户端知道该重试，而连接被关掉时请求正在路上的那个拿到 RST（非幂等 POST 不可安全重试）——把前者判 `fail`、后者读作 `ok`，正好把运维要做的判断排反了。这同时消掉 F-4 那个「`both` 模式例行重启可能报 fail」的隐患。
- 未采纳评审列的第 1 个选项（`transport.close()` 前用 `MSG_PEEK` 探未读字节，把「真的被打断的那一格」单独计出来）。那要多一次系统调用并依赖 uvicorn transport 内部，属于新的产品取舍，**留给用户裁决**。

## 其余采纳

| 发现 | 问题 | 处置 |
|---|---|---|
| F-2（minor） | `refused_requests` **整条特性零测试覆盖**，包括 `report_shutdown` 里论证最用力的那条 `ok`/`fail` 判定——全套测试从不断言 `status`，删掉 `+= 1` 或把判定改回去都是全绿 | `_lines()` 旁边加 `_statuses()`，新增两条断言行文与 `status` 的测试；在 barrier 测试里断言计数确实递增。三个变异逐一复现：删递增 → 红、让良性计数参与判定 → 红、报累计值而非本次差值 → 红 |
| F-5（minor） | 计数是**进程累计量**，却放在自称「本次关停做了什么」的报告里 | `serve()` 在 `stop_admitting()` 前取基线，`_descend` 报差值。barrier 测试同时钉住两层：适配器累计为 1，而报告为 0——因为那次拒绝发生在这次关停开始之前 |
| F-9（nit） | 收尾行把良性计数排在事故前面，与 docstring 自述的排序理由相左 | docstring 改为陈述实际顺序及其理由 |

## 记录但不改（评审本人亦不建议现在动）

- **F-3**：`pause_admission()` 清拒绝态，使「已唤醒但未恢复」的等待者可能从被 503 变成被正常服务。当前不可达（tick 实测），但不可达性依赖「`asyncio.Lock` 无竞争不让出」和「第二次 `stop_accepting` 时 `routing_tasks` 恰好为空」两个实现细节，没有任何东西在守。
- **F-6 / F-7**：取锁理由的措辞、路由器两个方法不取自己的锁——形状级不一致，无可达缺陷。
- **F-4**：`both` 模式 pause→refuse 之间有 3 tick 真实窗口，因而计数可以非零。降级出 incidents 之后，它不再会让例行重启报 `fail`。
- **O-1**（范围外）：`both` 模式每次关停会打一条 `accepted connection routing crashed` 的 ERROR。**既有缺陷**，评审与父提交逐行比对确认本次未引入也未加重。值得单独看一眼。

## 一次自己造成的返工，记下来

复现评审的变异时我用 `git checkout -- <file>` 还原，把同一文件里**尚未提交的修改**一起清掉了。改法是按原样反向替换那一处、而不是 checkout 整个文件，并在前后比对 `git status` 指纹确认工作树逐字节还原。

---

# 用户裁决：把「真的被切断」那一格量出来（2026-08-20）

用户裁定采纳增量评审列的第 1 个选项：「在 `transport.close()` 前用 `MSG_PEEK` 探一下内核缓冲里有没有未读字节」，并明确「多一次系统调用在这时候不是问题，项目依赖 uvicorn 也是既定事实」——即此前我列为「待裁决」的两点顾虑都被排除。

## 实现

`_closing_would_sever(connection)` 在每次 `connection.shutdown()` **之前**问一句：关掉它会不会丢掉客户端已经发出、而这里从未读过的字节。

- 响应还在写的连接直接返回 False——它根本不会在这一档被关闭，所以什么都没丢。
- `get_extra_info("socket")` 拿到的是 asyncio 的 `TransportSocket`，它**故意禁掉 I/O 方法**以防有人从事件循环底下把字节读走。peek 恰恰是那个例外（它不消费），所以借 fd 包一层临时 socket，用完 `detach()` 还回去、不关闭。
- `MSG_PEEK` 不消费数据，事件循环该读到的照样读得到。

计数进 `ShutdownReport.severed_connections`，并且**进 incidents**——它就是那个「有人真的没被服务」的数字，而 `connections_asked_to_close` 与 `refused_requests` 都不是。

两条限制都写在 `_closing_would_sever` 的 docstring 里，方向都是**少报而非多报**（对一个印在「severed」旁边的数字，少报是安全的那一侧）：响应进行中的连接不计；TLS 下字节可能已被吸进 SSL 对象而不在内核缓冲里，peek 就看不到。

## 真实进程实测

窗口只有大约**一次事件循环迭代**宽：服务端被信号唤醒之后、`stop_admitting()` 关闭连接之前。客户端从外部瞄不准它——单连接扫时序（gap ∈ {-0.05, 0, 0.002, 0.05}）四次全部落空：gap ≤ 0 时服务端来得及读走并正常回应，gap ≥ 0.002 时连接已关、写入根本没到达。

改用 40 条池化连接、由一个线程跨越信号持续错峰写入，3 次尝试命中 2 次：

```
[ OK ] stopped — 40 connections asked to close, 11 requests refused
[FAIL] stopped — 40 connections asked to close, 8 requests refused, 8 connections severed with a request already sent
[FAIL] stopped — 40 connections asked to close, 9 requests refused, 10 connections severed with a request already sent
```

这三行正好演示了分级的意义：**纯拒绝是 `[ OK ]`**（客户端被告知稍后再来），**一旦有连接被切断就是 `[FAIL]`**（有人真的丢了请求）。

## 顺带更正增量评审的一处结论

评审判定 `refused_requests` 在真实关停路径上**恒为 0**（11 组实测同向）。上面的实测表明那是**单客户端条件下**的结论：并发负载下它稳定非零（11 / 8 / 9）。机制不变——池化连接被关掉之后到达的字节确实不经过闸——但同时存在若干请求赶在关闭前进到了闸上并被答成 503。

所以评审的机制分析成立，「恒为 0」这个量化结论的适用范围要收窄到「单条空闲池化连接」。这不改变把它移出 incidents 的处置：503 仍然是温和的那一端。

## 分辨力

- 探针恒返回 True（丢掉空闲/切断的区分）→ 正样本 `assert 2 == 1` 与负样本 `assert 1 == 0` 双双变红。
- 探针恒返回 False（等价于特性不存在）→ 正样本 `assert 0 == 1` 变红。
- `severed_connections` 不进 incidents → `test_a_severed_connection_is_the_one_drain_cost_that_counts_as_a_failure` 变红（这一格第一次跑变异时**没有**被守住，是补出来的）。
- 进程内那条正样本连跑 10 次全绿，时序确定：asyncio transport 在缓冲为空时当场同步 send，而唤醒 `serve()` 的回调排在 socket 可读回调之前入队。
