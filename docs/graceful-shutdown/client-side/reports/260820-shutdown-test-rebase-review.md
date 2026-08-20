# 评审：优雅关闭修复中「改掉挡路的既有测试」是否护短

日期：2026-08-20。评审对象：工作树中未提交的改动 `tests/integration/test_standalone_process.py::test_a_half_sent_request_holds_the_drain_until_the_operator_escalates`（夹具重写），及其依赖的 `src/app/lifecycle/{adapter,listener,standalone}.py` 与 `src/app/cli.py`。基线提交 `7af85f6`。
评审性质：只读。除本报告外没有修改仓库中任何文件；全部实验在 `/tmp/shutdown-review/` 下的 `git archive` 副本与工作树副本中进行。

## 结论

**正当，不是护短。置信度：高。**

这不是「断言太严就把断言放松」，而是「夹具从来没有产生过它自称的前提条件，于是断言一直在验一个别的东西」。三项一手证据同时成立：

1. 老夹具发出的 `POST /health/liveness` 在**任何信号之前**就被 Starlette 用 405 答掉了，body 一个字节都没读——所以老测试断言的「进程还活着」不可能来自「在途请求把排空拖住了」。
2. 老测试之所以能绿，是因为 `sendall` 之后立刻发信号，让信号抢在事件循环处理该请求之前落地；请求随后撞上已被 `stop_accepting()` 清空的准入闸，停在 `await admission_open.wait()` 上永不返回。**绿灯的来源就是那个死锁本身**，子进程 stderr 打出的正是生产事故里那份 traceback。
3. 重写后的测试**在修复前和修复后都通过**。这说明它钉的是契约而不是这次修改的实现，也说明保护力没有被「按修复后的行为重写判据」这种方式降低。

同时，**断言本身一个字都没有放松**：`assert child.poll() is None`、3.0 秒等待、两条连接、第二档 `STOPPED INTERRUPTING` 全部原样保留，只是新增了一条发信号前的前提检查。改动是净增强。

### 什么证据会推翻这个结论

按分辨力从高到低列出。任何一条成立，我这个「正当」的判定就要重做：

- 有人证明 `POST` 到只注册 GET 的 FastAPI 路由**在某种配置下会读 body**（例如换用 httptools 协议实现、装了会预读 body 的中间件、或 Starlette 版本变化）。那样老夹具就确实表达了契约，改夹具就变成了绕开一个有效判据。我只在本仓库当前 venv（uvicorn 0.40.0 / starlette 0.52.1 / fastapi 0.129.0，**未安装 httptools，走 h11 实现**）上测过。
- 重写后的测试在**修复前的源码**上变红。那就说明它其实是把修复行为写成了判据。实测（下表 D 组）是绿的。
- 老测试的绿灯在**发信号前先确认 405 已返回**的情况下依然成立。实测相反：一旦先把 405 读出来，修复前的进程 3 秒内就干净退出（`STOPPED DRAINING`），老断言当场失败。
- 有人拿出老测试在**慢机器/负载下也稳定绿**的多次运行记录，且能说明那份绿不来自准入闸死锁。

### 反过来说，哪些指控我认为不成立

- 「改测试是为了让红变绿」——不成立：改完之后老断言全部保留且更严，且新测试对「第一档过度关停」有实测分辨力（变异 M2，见下）。
- 「削弱了契约」——不成立：契约条文（body 在途的请求属于在途请求，第一档必须等，只有升级才能结束）在新夹具下第一次真正被表达出来了。

## 取证方法与实测记录

环境：`/home/xp/src/ghc-api-proxy-py/.venv/bin/python`（CPython 3.14.2），`-p no:randomly`。两棵基准树都用 `git archive HEAD | tar -x` 与工作树 `tar` 复制得到，`PYTHONPATH` 逐次绑定到各自的 `src`，已验证 `app.lifecycle.adapter.__file__` 确实解析到对应树（venv 里存在 `app` 的 editable 安装，这一步不是多余的）。

### 四组对照：老/新测试 × 修复前/修复后源码

| 组 | 源码 | 测试文件 | 结果 |
|---|---|---|---|
| A | HEAD（修复前） | HEAD（老夹具） | 1 passed，3.99s |
| B | 工作树（修复后） | HEAD（老夹具） | FAILED：`the drain gave up on requests that were still arriving`，3.87s |
| C | 工作树（修复后） | 工作树（新夹具） | 1 passed，5.88s |
| D | HEAD（修复前） | 工作树（新夹具） | 1 passed，5.91s |

D 组是本次评审最关键的一格。**新测试在修复前的源码上同样通过**，所以它不是「按修复后的行为重新拟合的判据」，而是一条在两个世界里都成立的契约约束。

### 老夹具到底会不会读 body

裸 uvicorn + FastAPI 探针（`/tmp/shutdown-review/probe1_405.py`，不含任何本项目代码），三条对照：

- `POST /health/liveness`（只注册了 GET）半发 body（声明 400、实发 11 字节）→ **2 秒内就收到** `HTTP/1.1 405 Method Not Allowed`、`allow: GET`、`content-length: 31`。body 从未被读。
- `POST /swallow`（handler 内 `await request.body()`）同样半发 → 2 秒内无任何字节。
- 完整发送 body 的 `POST /swallow` → `200 OK`、`{"read":16}`（正样本对照，证明探针本身能收到响应）。

结论强度：**已实测，足以据此行动**。老夹具的路由选择使它无法产生「handler 卡在等 body」这个前提。

### 那么修复前撑住排空的是什么

`wait_drained()` 只轮询 `server_state.tasks`（`adapter.py`），连接数不参与，所以「405 已答完」意味着任务已结束、排空应当立即完成。实测（`/tmp/shutdown-review/probe2_whatheld.py`，跑在 HEAD 树上）正是如此：

| 场景（均为 HEAD 源码） | SIGTERM 后 3 秒 | 子进程终态 |
|---|---|---|
| 半发 POST 到 GET-only 路由，**发信号前先 recv 掉 405** | 已退出 | `STOPPED DRAINING`，stderr 空 |
| 已完成的 keep-alive GET，连接留着 | 已退出 | `STOPPED DRAINING` |
| 连上不发任何字节的空闲连接 | 已退出 | `STOPPED DRAINING` |
| 什么都不连 | 已退出 | `STOPPED DRAINING` |
| 半发 POST 到 GET-only 路由，**sendall 后立刻发信号**（＝老测试的写法），跑 3 次 | 3 次全部仍在运行 | `STOPPED INTERRUPTING`，stderr 为 `gated_app` → `await admission_open.wait()` → `CancelledError` |

最后一行同时给出两个判定：

- 老测试的绿灯**确实**来自准入闸死锁，且子进程 stderr 里就是生产事故那份 traceback（老测试没有断言 stderr，所以它一直静默地把事故形状带在身上）。
- 老测试**本身是竞态**：它的成败取决于 SIGTERM 有没有抢在事件循环处理该请求之前落地。在够慢或够忙的机器上，405 先答完，老断言就会假红。也就是说，它在修复前也不是一条稳定的守卫。

同一形状跑在**修复后**的树上：3 秒内退出、`STOPPED DRAINING`、stderr 空。这正是修复要达成的行为。

### 新夹具的前提是不是真的成立

新测试只观测到「没有响应」，这是**否定式**证据。我另外做了肯定式取证（`/tmp/shutdown-review/probe3_entered.py`：handler 入口打印 `ENTERED swallow`）：

- 修复后的树：子进程 stdout 打出 `ENTERED swallow` 两次，SIGTERM 后 3 秒仍在运行，第二次信号后 `STOPPED INTERRUPTING`，stderr 显示请求确实卡在 `message_event.wait()`（即等 body）上被取消。
- 修复前的树：同样两次 `ENTERED swallow`，行为一致（与 D 组一致）。

所以新测试的前提是真的：排空被一个**真正进入了 handler、正在等 body** 的请求撑住。

### 分辨力：变异验证

在 `/tmp` 的副本上做，仓库未被触碰。

- **M1**：`standalone.py::serve()` 中把 `released = await self._adapter.begin_draining()` 换成 `released = 0`（等价于修复不存在）。
  - `tests/integration/test_standalone_lifecycle.py`：2 failed / 11 passed，红的正是新增的 `test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open`（TimeoutError）与 `test_the_drain_lets_go_of_an_idle_pooled_connection`（`assert 0 == 1`）。
  - 重写后的 process 测试：**仍然通过**。
- **M2**：`begin_draining()` 里顺手 `self.cancel_requests()`（一个看似合理的过度修法，等于把第二档提前到第一档）。
  - 重写后的 process 测试：**变红**（`the drain gave up on requests that were still arriving`）。
  - `test_standalone_lifecycle.py`：6 failed / 7 passed，包含既有的第一/二/三档守卫。

这组数据同时确认了两件事：重写后的测试对「第一档过度关停」有分辨力（M2 击中），但**不再守卫死锁复发**（M1 未击中）。见下一节。

### 独立复跑

工作树副本上 `tests/integration` + `tests/unit/test_lifecycle_cleanup.py`：**76 passed，25.59s**。未跑全量（工作树混有其他并行会话的在飞改动，全量结果对本次判定没有增量信息）。

## 逐条回答

### 1. `POST /health/liveness` 打到只注册 GET 路由的 FastAPI，Starlette 会不会读 body

**不会。**Starlette 路由在路径匹配、方法不匹配时走 `Match.PARTIAL` 分支，直接抛 405，永远到不了任何会碰 `receive` 的地方。实测见上（405 在 2 秒内返回，31 字节，`allow: GET`）。你报告里的这条判断成立，且我是独立复现的，不是照抄。

### 2. 改动后的测试是否仍覆盖原契约

**覆盖，而且是第一次真正覆盖。**契约「body 还在路上的请求属于在途请求，第一档必须等它，只有升级才能结束」在新夹具下逐项对上：请求进了 handler（肯定式取证）、停在等 body（`message_event.wait()`）、第一档等满 3 秒不退、第二档才结束并打出 `STOPPED INTERRUPTING`。断言无一被削弱。

**但有一处保护力被移走了，而且报告没有明说**：老测试（无论出于什么原因）是**唯一一条在真实进程 + 真实信号下会因死锁复发而变红的测试**。M1 变异证明，重写之后这条 process 测试对死锁复发完全不敏感，该保护现在只存在于 `test_standalone_lifecycle.py` 的进程内 harness 里。

这不是护短——进程内那三条测试确有分辨力（M1 实测击中两条）——但它是一次**覆盖面的重新划分**，而重新划分之后真实进程这一层出现了空位：事故本身就发生在真实进程 + 连接池客户端上。我实测过这个空位是可以低成本补上的：修复前的树在「半发请求到 GET-only 路由、不做同步、立刻发信号」下 3/3 挂住并打出生产 traceback；修复后的树同样场景 2/2 在 3 秒内以 `STOPPED DRAINING` 干净退出、stderr 为空。**这就是一条现成的、双向有分辨力的真实进程回归测试**，判据可以取「3 秒内退出且终态为 DRAINING」。

顺带一提：这也正是「保留原测试并另加一条」这个选项**真正可行的形态**——原测试的字面断言不可能保留（它断言的是死锁的副作用），但原测试的**场景**应当以正确的期望被保留下来。

### 3. 发信号前那段同步：加强还是变脆

**加强，且失败方向是安全的；但它是否定式证据，没有把竞态关死，还固定花掉 2.0 秒。**

- 老写法的竞态方向是**静默地为错误的原因变绿**（信号抢先 → 死锁撑住排空 → 断言满足）。新同步把这个方向堵死了：能走到断言处，至少说明 1 秒内服务器没有答复。这是明确的改善。
- 慢机器/CI 不会让它变脆。handler 真卡在等 body 时，recv 无论如何都会超时，机器越慢越容易超时通过。`pytest.raises(TimeoutError)` 也覆盖了 `socket.timeout`（3.10 起是同一个类），且对端若关闭连接 `recv` 返回 `b""` 不抛异常 → `DID NOT RAISE`，这是一次有意义的失败。
- 残余竞态在另一个方向：**「1 秒内没有响应」既可能是「handler 进来了正在等 body」（想要的），也可能是「服务器根本还没轮到处理这个请求」（混淆项）**。后者一旦发生，SIGTERM 落地后该请求会撞上准入拒绝拿到 503，排空结束，测试**假红**。1 秒余量对照实测的进入延迟（毫秒级）非常宽，实际发生概率低；但这个同步在原理上没有排除混淆项。
- 更好的写法是**肯定式就绪信号**：子进程 handler 进入时写一个 marker 文件（或打印一行 stdout），测试轮询它。成本从固定 2.0 秒降到毫秒级，并且直接排除混淆项。我在 probe3 里已经用打印验证过这条信号确实可得。这条建议的权重：**值得做，但不是阻断项**；当前写法可以合入。

### 4. 有没有更好的处置

有三个，按价值排序：

1. **补一条真实进程的死锁回归测试**（见第 2 条末尾，判据与实测数据现成）。这是我唯一认为应当在合入前后尽快补上的一项——它填的是事故本身发生的那一层。
2. **把同步换成肯定式就绪信号**（见第 3 条）。
3. 「保留原测试不动、另加一条」在字面上不可行（原断言依赖 bug），但**保留原场景、改成正确期望**可行，且与第 1 条是同一件事。

我不建议的做法：把老测试标 `xfail` 或 skip 留着（留下一条没人读的死代码，且掩盖它本来就是竞态这一事实）；或者为了保住老测试的绿而在 `begin_draining` 里给「已 accept 连接上的新请求」开后门（那等于把事故留在产品里）。

### 5. 顺带扫描：本次改动里还有没有「为了变绿而调整判据」

在这次修复自己的足迹内（`src/app/lifecycle/*`、`src/app/cli.py::report_shutdown`、`tests/integration/test_standalone_*`、`tests/unit/test_lifecycle_cleanup.py`）：

- `tests/integration/test_standalone_lifecycle.py` 只有新增，没有任何既有断言被改动或删除。
- `tests/unit/test_lifecycle_cleanup.py` 的 stub 新增 `begin_draining` 返回 0，注释交代了为什么这里的计数无意义。诚实。
- `src/app/cli.py` 把 `clean` 的判据从「parts 为空」改成「incidents 为空」，把 `released_connections` 排除在 `clean` 之外。**这是一次判据调整，但我认为它是正确的**：放掉空闲连接是健康关停的常态，不排除的话每次正常关闭都会打 `fail`。不是为了让某条测试变绿。
- 全仓库检索确认：**从来没有任何测试钉过旧的 `_reject_pending_admission_locked` 抛异常路径**，所以「把抛异常改成返回 503」没有伴随任何测试删除。

工作树里另外几个测试文件（`tests/http/test_pipeline_app.py`、`tests/unit/test_request_log.py`、`test_stream_delivery.py`、`test_sse_assembly.py`、`test_builtin_subscribers.py`、`test_blank_text_blocks.py`）属于**其他议题的在飞改动**（`docs/tmp/260820-truncated-stream-reporting.md` 等），不在本次评审范围，我没有审。仅作归属提示，供你判断是否需要单独看一眼：其中 `test_pipeline_app.py` 删掉了 `test_count_tokens_refuses_a_model_that_advertises_other_endpoints`（原本断言 400 + `EndpointNotSupported`），换成断言 200 + 本地估算。那是一次对外行为裁决，不是判据放松，但它**是不是已经被裁决过**只有你知道。

## 附带发现（与测试处置无关，权重各自标注）

1. **第二档仍然会打出 `Exception in ASGI application` + traceback。**实测：修复后的树在第二次 SIGTERM 后，stderr 首行就是 `Exception in ASGI application`，栈底是 `message_event.wait()` 的 `CancelledError`。这在语义上没错（第二档就是要取消请求），但你报告第 29 行写「**两个症状是同一个根因**」，读者容易读成「升级之后也不再有 traceback」。实际是：第一档那次不该发生的 traceback 没了；只要真的有请求被取消，第二档每取消一个仍会打一份。**权重：文档准确性，建议在报告里补一句限定。**
2. **`released_connections` 会多算。**`begin_draining()` 返回 `len(connections)`（全部连接），但对仍在跑请求的那条，uvicorn 只是清掉 `keep_alive`，连接要等响应结束才关——docstring 自己也这么写。实测（`/tmp/shutdown-review/probe4`，1 条空闲 pooled + 1 条正在跑 `/slow`）：`released_connections=2`，而真正当场放掉的只有 1 条。CLI 会打成 `2 connections released`。现有测试 `test_the_drain_lets_go_of_an_idle_pooled_connection` 只有 1 条空闲连接，捕捉不到。**权重：真实但轻微的可观测性失真，已一手复现。**改法要么改名（像 `interrupt_connections` 那样说成「asked」），要么只统计 `cycle is None or cycle.response_complete` 的那些。
3. **`TlsRouter._arm_locked` 直接 `admission.set()`，但不清 `_admission_refusal`。**被包裹的 `UvicornListenerAdapter._arm_locked` 会显式 `self._admission_refusal = None`，router 那条路径没有对应动作。当前流程里 `begin_draining()` 只在关停路径上调用一次、之后不会 resume，所以**没有找到可达触发点**；但这是一个不对称的形状，将来若有人在 quiesce 之后复用它就会得到「闸开着、每个请求还是 503」。**权重：形状级观察，当前不可达，仅备案。**
4. **`begin_draining` 这个名字撞了。**`app/observability/active_requests.py` 早已有 `def begin_draining(self)`（显示层的「排空开始了」钩子），本次在 listener 侧新增了同名方法（拒绝准入 + 放连接）。两者在 `standalone.py` 里紧邻出现（`self._on_draining` 与 `self._adapter.begin_draining`）。**权重：命名可读性，随手可改，也可以不改。**

## 范围与未做的事

- 未跑全量测试套件（工作树混有并行会话在飞改动）；跑的是 `tests/integration` + `tests/unit/test_lifecycle_cleanup.py`，76 passed。
- 未审 systemd/rolling 路径的行为正确性，只确认了两条路径共用 `StandaloneServer.serve()`，因此都经过 `begin_draining()`；以及 socket activation 下关掉的是连接不是监听器。
- 未审 503 错误信封形状（你已标为未裁决）与 `docs/.human-controlled/lifecycle.md` 的一致性判断之外的产品取舍。按第 20-22 行的三档语义，「拒绝新到达的请求」属于第一档「停止 accept 新请求」，「不打断在途请求」由 M2 变异与 `cancelled_requests == 0` 断言双向确认，**修复与规范一致**。
- 未修改仓库任何文件（本报告除外）。实验产物留在 `/tmp/shutdown-review/`（`probe1_405.py`、`probe2_whatheld.py`、`probe3_entered.py`、`probe4/`、四棵对照树），如需复核可直接复用；`/tmp` 内容随时可删。
