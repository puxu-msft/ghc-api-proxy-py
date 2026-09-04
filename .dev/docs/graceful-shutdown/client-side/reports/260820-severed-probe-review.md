# 独立评审：`severed_connections` 探针与分级（提交 `89002eb`）

评审对象：`89002eb feat: count the connections the drain actually cut off`，即用户自己加的最后一批改动（`_closing_would_sever()`、CLI 分级、三条新测试）。此前三轮评审（`260820-shutdown-fix-review-gpt.md`、`260820-shutdown-test-rebase-review.md`、`260820-shutdown-delta-review.md`）已核实的上游事实直接复用，未重复考据。

评审日期：2026-08-20。方向：并发与系统编程。**只读评审：仓库源码与测试一个字节都没有改动**，全部探针、变异、压力测试都在 `/tmp/severedrev/` 下的 `git archive 89002eb` 副本上进行，收尾已逐文件 `cmp` 确认还原。权威规范 `docs/.human-controlled/lifecycle.md` 只读未改。

环境（实测，不是记忆）：CPython 3.14.2、uvicorn 0.40.0、h11 0.16.0，**未装 uvloop、未装 websockets、未装 httptools**，`selectors.DefaultSelector` 是 `EpollSelector`（水平触发，未使用 `EPOLLET`）。

## 结论

**blocker 0，major 1，minor 4，nit 4。**

机制层面这批改动是对的，我逐条做了实测：fd 借用在当前代码里安全、peek 不干扰事件循环、四条变异的分辨力全部独立复现、正样本的时序论证成立且在 8 路满载下 15/15 稳定。**唯一的 major 不是缺陷，而是这个数字被赋予的含义又一次超过了它能量到的范围**——与上一轮把 `refused_requests` 降级时踩到的是同一个坑，只是挪了一格。实测：一次由在途请求撑开的正常排空里，10 个池化客户端全部发出 POST、全部一无所获，而收尾行读作 `[ OK ]`、`severed=0`。

分级本身（severed 进 incidents，asked/refused 不进）我判**成立**，例行滚动重启不会因此误报 `fail`；风险方向恰好相反——它更容易在该报 `fail` 时读作 `ok`。

---

## 对任务书四个问题的直接回答

### 问题 1：fd 借用安全吗

**安全，但守卫漏了一种异常类型。置信度：高，全部有实测。**

| 子问题 | 实测结论 |
|---|---|
| `socket.socket(fileno=fd)` 内部做什么 | Linux 上用 `getsockopt(SO_DOMAIN/SO_TYPE/SO_PROTOCOL)` 探测 family/type/proto。实测借用一条 `AF_UNIX/SOCK_STREAM` 得到 `family=1 type=1 proto=0`，探测确实发生 |
| fd 已关闭（EBADF） | 抛 `OSError [Errno 9]`，**被 `except OSError` 接住** |
| fd 不是 socket（管道） | 抛 `OSError [Errno 88] ENOTSOCK`，**被接住** |
| **fd 为 `-1`** | 抛 **`ValueError: negative file descriptor`**，**接不住** —— 见发现 S-2 |
| 借用对象被 GC 会不会关掉 fd | **会**。实测不 `detach()` 直接 `del` 之后 `os.fstat(fd)` 报 EBADF。`finally: probe.detach()` 是必须的，且它确实覆盖了正常与异常两条路径（实测 detach 之后原 socket 仍可用） |
| double-free | 不会。`detach()` 置 `_closed` 并交出 fd，dealloc 不再关闭；`finally` 无条件执行 |
| 构造成功与进入 `try` 之间被打断而泄漏 | 理论窗口存在（此时抛 `KeyboardInterrupt` 会让 probe 被 GC 关掉真连接的 fd），但 `serve()` 全程处在 `_signal_handlers()` 里，SIGINT 由 `loop.add_signal_handler` 接管、不再注入 `KeyboardInterrupt`，**该窗口在关停路径上不可达** |
| `recv` 会不会抛非 OSError | 不会。`BlockingIOError`／`InterruptedError` 都是 `OSError` 子类；EINTR 由 PEP 475 在 CPython 内部自动重试。唯一的非 OSError 来自构造函数（上面那格） |
| 会不会因为 timeout 语义而阻塞 | 不会。借用出来的对象 `gettimeout()` 是 `None`（自认阻塞），但实测「阻塞态 fd + `MSG_DONTWAIT`」照样立刻抛 `BlockingIOError`。仓库与依赖里没有任何 `socket.setdefaulttimeout` 调用，因此构造函数也不会顺手改动 fd 的阻塞标志 |

补充一条对注释的核实：`TransportSocket` **确实**没有 `recv`（3.14 实测 `AttributeError`），所以借 fd 不是绕远路，是唯一走得通的路。但它**有 `dup()`**——见发现 S-2 的建议。

### 问题 2：peek 会不会干扰事件循环随后的读取

**不会，而且在当前接线下这个问题是空的。置信度：非常高。**

- 前提确认：`selectors.EpollSelector`，注册时不带 `EPOLLET`，**水平触发**。asyncio 的 `add_reader` 不使用边缘触发。
- 直接实测：给一条 socket 注册 reader，在回调运行前从外部 `MSG_PEEK` 一个字节，回调随后仍然触发并读到**完整**的 `b"hello"`。
- 仓库内已有同样的先例：`listener.py::_peek_first_byte` 就是 `recv(1, MSG_PEEK)` 之后把 socket 原样交给 `connect_accepted_socket`，那一个字节被下游重新读到。这条路径每天都在跑。
- **更强的一条**：`_closing_would_sever` 只在 `cycle is None or response_complete` 时才走到 peek，而 uvicorn 的 `H11Protocol.shutdown()` 对这两种情况**一律 `transport.close()`**。也就是说凡是被 peek 过的连接，下一条语句就把它关了，事件循环根本没有「随后的读取」。我用变异证实了这一点：把 `MSG_PEEK` 去掉（让探针真的**消费**掉那个字节）——**51 条测试全绿**（见 S-5）。

### 问题 3：`cycle` 前置判断对 WebSocket 与 TLS 的行为

- **WSProtocol 没有 `cycle` 属性**（`rg` 确认整个 `wsproto_impl.py` 里没有 `self.cycle`），于是 `getattr(..., None)` 返回 None，**直接进入 peek**。活跃 websocket 上任何一个尚未读走的帧（数据帧、ping、甚至客户端的 close 帧）都会被计成「a request already sent」，而 `WSProtocol.shutdown()` 其实先发了一个规规矩矩的 `CloseConnection(1012)` 才关——这是**多报**。当前不可达：`rg` 确认 `src/` 下没有任何 `WebSocketRoute`／`@app.websocket`（与旧评审 4.2 的结论一致，我独立复算过）。
- **TLS 下 `cycle` 判断不变**（协议对象仍是 SSL transport 之上的 `H11Protocol`），但 `get_extra_info("socket")` 拿到的是**底层 TCP 的** `TransportSocket`，于是 peek 读到的是**密文记录**。实测（`probe_tls3.py`）：一条只在内核缓冲里留着 close_notify 的 TLS 连接，`_closing_would_sever` 返回 **True**——密文里是请求还是告警，peek 分不出来。方向是**多报**，见 S-3。
- 正常情况下 TLS 是**少报**：asyncio 的 SSL transport 会积极把内核缓冲吸进 SSL 对象。我第一版探针不强制 `pause_reading` 时，close_notify 已被读走，探针返回 False——这正好实测印证了 docstring 里写的那条 TLS 限制。

### 问题 4：docstring 声称「方向都是少报而非多报」——证伪

**部分证伪。少报的方向成立且是主导，但「不会多报」这个更强的说法不成立。**

多报的四种形状（按可达性排序）：

1. **TLS 下的非请求记录**（已实测 True）：close_notify、post-handshake 控制记录。Go 的 `crypto/tls` 与 Node 关闭连接时都会发 close_notify。窗口宽度与真阳性相同。
2. **客户端发完请求就走人**：实测「对端写完即 close」时 peek 返回 `b"X"` → 计为 severed。请求确实被丢了，但没有人在等答案。
3. **不是请求的字节**：peek 只证明「有 ≥1 字节」，不证明「有一个请求」。RFC 9112 允许客户端在请求行前发空行，任何一个杂散 CRLF 都会让这条连接被计成「a request already sent」。
4. **WebSocket 帧**（当前不可达，见上）。

不会多报的几种（逐条确认）：

- **TCP keepalive**：内核级、无载荷，`recv` 看不见。不多报。
- **对端已关闭（FIN、无数据）**：实测 `recv` 返回 `b""`，`bool(b"")` 为 False → **不计**。这一格是对的，而且重要——关停时客户端正好撤走是常见形状。
- **pipelined 的下一个请求**：确实会丢，属**真阳性**，不是多报。
- **已被 h11 缓冲、尚未被 cycle 消费的字节**：只会**少报**。完整请求会立刻生成新 cycle 走早返回；半个请求头则让 peek 看到空缓冲。两条都不会多报。

---

## 发现清单

### S-1【major】这个数字被赋予的含义再次超过它能量到的范围，而它现在决定 `ok`／`fail`

**置信度：高——实测，10/10 同向，一次运行即决定性。**

`severed_connections()` 的 docstring 写「This is the count that says a client genuinely went without」，`cli.py` 写「the one count here that names a client who genuinely went without」，提交说明写「Those bytes never reached the application, so nothing else in this process could report them」。

实测（`probe_longdrain.py`，生产形状：一条在途请求把排空撑开）：

```
client outcomes: {'sent, then clean EOF': 10}
report: asked_to_close=11 refused=0 severed=0
closing line would read: [ OK ]
```

10 条池化连接，在 SIGTERM 之后 0.3 秒（进程还活着、排空还开着）各发一个 `POST`，**10 个全部没有拿到任何答复**，而收尾行读作 `[ OK ]`。原因是机制性的：第一档在 t=0 就把这些空闲连接关了，`severed` 只能看见**关闭前那约一次事件循环迭代**里已经躺在内核缓冲中的字节；此后整整一个排空窗口（生产里可以是几十秒）内客户端写进来的所有请求，得到的是 RST 或裸 EOF，**这个进程里没有任何东西看得见**。

第二组实测（`probe_undercount.py`，20 条连接跨信号错峰写入）给出同一方向的量化：

```
client outcomes: {'answered': 8, 'other': 5, 'sent, then ConnectionResetError': 3, 'sent, then clean EOF': 4}
report: asked_to_close=20 refused=0 severed=3
```

**7 个客户端发了请求没拿到答复，计数报 3。**

这与增量评审给 `refused_requests` 判 major 的结构完全一样，也正是项目记忆 `absence-is-not-readable-on-a-log-line` 说的那件事：**同形没有被消除，只是又挪了一格**。修复文档里那三行实测其实已经把证据摆出来了——第一行 `[ OK ] stopped — 40 connections asked to close, 11 requests refused` 是 40 个跨信号写入的客户端里 0 个落进窗口，而不是 40 个都没事。

**处置建议（纯文字，零风险，我认为应当在本轮内做）**：把这个数字定位成**一次采样的下界**而不是「有人没被服务的那个数」。具体三句话：

- 它只覆盖「关闭那一瞬间内核缓冲里已有字节」的连接，窗口约一次事件循环迭代；
- 排空窗口内**此后**到达的请求同样被丢弃，同样拿到 RST，**同样不计**；
- 因此 `severed > 0` 是「确实有人被切断」的**充分**证据，`severed == 0` 与收尾行的 `[ OK ]` **都不是**「没有人被切断」的证据。

我**不**建议为此改行为。要真正量到「关闭之后还写进来的客户端」，唯一可靠的观测点在内核之外（RST 计数、或客户端侧），不该由这个进程假装能看见。

### S-2【minor，但优先级排在其余 minor 之前】`except OSError` 接不住关闭态 socket 抛出的 `ValueError`，而后果是整个关停中止

**置信度：机制高（实测复现）；可达性——两条候选路径我都实测证伪，判定为潜伏。**

`_closing_would_sever` 的注释自己写着「a probe that cannot answer must not take down the shutdown it was measuring」。但**一条已关闭的 asyncio socket 报 `fileno() == -1`，而 `socket.socket(fileno=-1)` 抛的是 `ValueError`，不是 `OSError`**（实测）。爆破半径实测（`probe_badfd.py`）：

```
direct call raised ValueError: negative file descriptor
stop_admitting raised ValueError: negative file descriptor
dead.shutdown() called: False
```

异常从锁块里逃出 `stop_admitting()` → 逃出 `serve()`，于是 `_descend()` 与 `_finalize()` **一次都不会跑**：没有 lifespan shutdown、没有资源释放、没有收尾报告，剩下的连接也不会被通知。这与 `lifecycle.md` 第 22 行「执行状态持久化、资源清理等，然后退出」直接冲突。

**可达性**：我找了两条候选路径，都实测证伪，所以判潜伏而非 major。

1. `H11Protocol.connection_lost` / `WSProtocol.connection_lost` **先**把自己从 `server_state.connections` 里摘掉，asyncio 的 `_call_connection_lost` **之后**才 `self._sock.close()`。所以「还在集合里、fd 已是 -1」这个状态在正常收敛路径上不存在。
2. `both` 模式的竞态：`_route_connection` 在 `await connect_accepted_socket(...)` 上挂起时，协议对象**已经**进了 `server_state.connections`（`connection_made` 先于 waiter 被 resolve），而 socket **仍然**在 `_pending_sockets` 里，此时 `stop_accepting()` 会把它 `close()`——正好排在 `stop_admitting()` 前一句。我实测确认这个窗口**真实存在**（`probe_race2.py`：tick 5 时 `pending=1 conns=1`），并在该 tick 上精确触发关停 6/6（`probe_race4.py`），结果是 `asked=0 severed=0`、无异常：`stop_accepting()` 取消路由任务后，asyncio 自己在 `_create_connection_transport` 的 except 里 `transport.close()`，`connection_lost` 把协议摘走，而这一切发生在 `gather()` 恢复之前。**窗口被上游的取消清理关上了。**

**建议**：一个词的改法——`except (OSError, ValueError)`。或者更彻底：`TransportSocket` **有 `dup()`**，`probe = raw_socket.dup()` + `finally: probe.close()` 语义上更安全（拿到的是自己的 fd，忘了关只是泄漏一个 fd，而不是关掉别人的连接），且 fd 为 -1 时 `dup` 抛的是 `OSError`。代价是一次 `dup` + 一次 `close` 系统调用，换掉现在的三次 `getsockopt` 探测，量级相当。**这是我唯一建议改代码的地方，且不阻塞。**

### S-3【minor】「两条限制方向都是少报」这句话不成立，且限制不止两条

**置信度：高——TLS 多报已实测；少报的第三条来自源码阅读。**

见「问题 4」的清单。除了多报，被列举的限制也漏了一条**少报**：h11 已经把半个请求头吃进自己的缓冲区时，`cycle` 还是上一个已完成的 cycle，peek 看到的是空缓冲，于是这条**确实会丢掉一个半发出的请求**的连接被记作「genuinely idle」。

建议：docstring 改成「peek 只回答内核缓冲里有没有字节」，然后分别说明它看不见什么（h11 已缓冲的、SSL 已吸走的）与它分不清什么（密文里的告警与请求、非请求字节）。

### S-4【minor】不对称：另外三处关连接的地方同样在丢字节，其中一处能翻转 `ok`／`fail`

**置信度：高——源码阅读 + `both` 模式实测。**

逐处判断：

- `interrupt_connections()`（第二档）：**不必补**。走到这一档一定已经有 `interrupted_connections` 进 incidents，收尾行的判定不会因此改变，补 peek 只增加细节。
- `shutdown_lifespan()`（收尾）：**是真缺口**。第一档特意放过的那类连接（响应还在写）最后是在这里被关的，此时客户端 pipeline 进来的字节照样被丢，且**这一格能让本该 `fail` 的关停读作 `ok`**——因为它可能是全场唯一一次切断。
- **`both` 模式路由器的 `_pending_sockets`**：`stop_accepting()` 对每条待路由 socket 直接 `close()`，而路由器**故意不消费**第一个字节，所以那条 socket 的内核缓冲里很可能躺着一整个请求。它就发生在 `stop_admitting()` 的**前一句**，是同一时刻、同一种伤害，一样不计。讽刺的是这里最好补：socket 就在手上，`_peek_first_byte` 已经证明这套写法在这个文件里能跑。
- **重复计数**：不存在。`stop_admitting()` 全流程只调一次；被关掉的连接随即离开 `connections`；早返回的那类根本走不到 peek。

建议：记录即可，或者只补路由器那一处（十行以内）。不建议为收尾那一处加探针——那正好是 S-1 说的「假装能看见」的方向。

### S-5【minor】让 fd 借用安全的那两条性质，没有任何东西在守

**置信度：非常高——两条变异各跑一次全套，全绿。**

在 51 条相关测试（`test_standalone_lifecycle.py` + `test_shutdown_reporting.py` + `test_lifecycle_cleanup.py` + `test_listener_quiesce_resume.py`）上：

| 变异 | 内容 | 结果 |
|---|---|---|
| `peek_consumes` | 去掉 `MSG_PEEK`，探针真的**消费**掉那个字节 | **51 passed，全绿** |
| `no_detach` | `finally: probe.detach()` 改成 `pass`，借来的 fd 交给 GC | **51 passed，全绿** |

两条都全绿的原因是同一个（见问题 2）：被 peek 的连接下一句就被关掉，所以「不消费」和「不关掉借来的 fd」在**今天的接线下都不承重**。这不是缺陷，是一条给下一个人的提醒：这两条性质是这套技术里最危险的两条，而它们现在改坏了不会变红。`no_detach` 尤其阴险——refcount 当场关掉那个 fd，而 fd 号一旦被复用，被误关的就是别人的连接。

建议（**一条就够，不要建门禁**）：给 `_closing_would_sever` 加一条直接的单元测试，用 `socketpair` 覆盖三格——空闲（`BlockingIOError` → False）、有数据（True）、对端已关（`b""` → False）。第三格顺带钉住「客户端撤走不算 severed」这个最可能的假阳性形状，而且它是纯函数测试，十行。

### S-6【nit】`except (BlockingIOError, InterruptedError)` 里的第二项名不副实

`InterruptedError`（EINTR）不是「nothing waiting」，把它当空闲处理是一次静默少报。实际不可达：PEP 475 之后 CPython 在 `sock_call_ex` 内部自动重试 EINTR。两者都是 `OSError` 子类，下面那条 `except OSError` 本来就接得住，所以这一格纯属注释与代码不符。

### S-7【nit】`_descend` 的第三个默认参数延续了旧评审 F-8 的形状

`severed_before: int = 0` 与旁边两个一样，唯一调用点总是传值。默认值在这里只把「忘了传」变成静默的 0，而这个 0 会原样进 `ShutdownReport`。旧评审 F-8 已提过同一件事，未采纳；这里只记录它又长了一个。

### S-8【nit】收尾行的措辞比证据强一点点

`N connections severed with a request already sent`——peek 只证明有 ≥1 字节，不证明有一个完整请求。半个请求头、杂散 CRLF 都会读成「a request already sent」。名词保持复数符合项目既有裁决，这里说的只是「a request」那半句。

### S-9【nit】正样本 docstring 里的因果被写反了一次

> the wakeup that resumes `serve()` was queued before the socket became readable

物理顺序恰好相反：`loud_writer.write(...)` 在 `receive_signal(...)` **之前**，socket 早就可读了。真正成立的是**队列顺序**：唤醒回调在上一轮迭代就进了 ready 队列，而 socket 可读回调要等下一次 `select()` 之后才被 `_process_events` 追加到队尾，`_run_once` 按 FIFO 弹出，所以唤醒先跑。我直接实测了这一点（`probe_order.py`，先写 socket 再 `Event.set()`）：

```
order: ['woken-coroutine', 'reader']   × 5/5
```

一个照着现在这句话去核对的人会发现「socket 明明先可读」，从而怀疑整条论证。建议改成队列顺序的说法。

---

## 我认为没有问题的项（逐条附依据）

| 项 | 判断 | 依据 |
|---|---|---|
| fd 借用本身 | **安全** | `finally: detach()` 无条件执行；实测 detach 后原 socket 可用、无 double-free；构造失败的两种 OSError 都被接住（唯一例外见 S-2） |
| 借用对象被 GC 关掉真 fd 的风险 | 已由 `detach()` 消除 | 实测：不 detach 时 fd 当场被关（EBADF）；detach 后不会 |
| 构造与 `try` 之间被信号打断 | 关停路径上不可达 | `serve()` 全程在 `_signal_handlers()` 内，SIGINT 由 `add_signal_handler` 接管，不注入 `KeyboardInterrupt` |
| 借来的 socket 会不会阻塞 | 不会 | `MSG_DONTWAIT` 有效；实测阻塞态 fd 上也立刻 `BlockingIOError`；无 `setdefaulttimeout` 干扰 |
| peek 干扰事件循环 | 不会，且当前接线下无关 | `EpollSelector` 水平触发；实测回调仍收到完整数据；仓库内 `_peek_first_byte` 是同一写法的既有先例；被 peek 的连接下一句即关 |
| `cycle` 早返回的判据 | 与 uvicorn 一致 | `H11Protocol.shutdown()` 的分支就是 `cycle is None or cycle.response_complete`，探针取的是同一个谓词，因此「被计的一定是被关的」 |
| 与 `refused_requests` 重复计数 | 不会 | 已挂在闸上的请求 `response_complete` 为 False → 早返回；两个数覆盖不相交的两种形状 |
| 同一次关停内重复计数 | 不会 | `stop_admitting()` 每次关停只调一次，且快照与循环之间没有 await |
| `severed_before` 基线与差值 | 正确 | 唯一调用点在 `stop_admitting()` 之前取基线；只有 `stop_admitting()` 会递增，因此差值就是本次关停的量 |
| RST 这个前提本身 | **属实** | 实测：关闭时缓冲里有未读字节 → 客户端 `ConnectionResetError`；先读干净再关 → 客户端 clean EOF |
| 分级（severed 进 incidents，asked／refused 不进） | **成立**，例行重启不会误报 fail | 空闲连接实测不计（负样本 + 20 客户端实测的第一组：`refused=14 severed=0` → `[ OK ]`）；窗口只有约一次迭代宽；假阳性形状（TLS 告警、ws 帧、客户端撤走）都罕见。风险方向是反的，见 S-1 |
| 正样本的时序论证 | **成立，且不受负载影响** | 三条链路逐条核实：① ready 队列 FIFO，唤醒在上一轮入队、reader 在本轮 `_process_events` 追加到队尾（实测 5/5）；② 唤醒到 peek 之间**没有任何让出点**——`_await_advance` 循环直接退出，`stop_accepting`／`stop_admitting` 取的是无竞争 `asyncio.Lock`（快路径不 await）；③ transport 缓冲为空时 `write` 直接 `sock.send`，36 字节走 loopback 必然当场落地 |
| 正样本在负载下 | **稳定** | 干净副本树上 30/30 空载全绿；8 路 busy loop 满载 15/15 全绿。且万一顺序真的翻转，失败方向是**红**（`severed 0 != 1`），不是假绿 |
| 负样本（空闲连接不计） | 有分辨力 | `always_true` 变异下它与正样本**双双变红**（`assert 1 == 0`），与用户记录一致 |
| 三条新测试的分辨力 | **四条变异全部独立复现** | `always_true` → 2 红（`assert 2 == 1`、`assert 1 == 0`）；`always_false` → 1 红（`assert 0 == 1`）；`no_count` → 1 红；`severed_benign`（挪出 incidents）→ `test_a_severed_connection_is_the_one_drain_cost_that_counts_as_a_failure` 红（`['ok'] != ['fail']`）。与修复文档「分辨力」一节逐格对得上 |
| `TransportSocket` 确实不能直接 peek | 属实 | 3.14 实测 `AttributeError: 'TransportSocket' object has no attribute 'recv'`，注释成立 |
| WebSocket 路径的可达性 | 当前不可达 | `rg` 确认 `src/` 无任何 `WebSocketRoute`／`@app.websocket`（独立复算旧评审 4.2） |
| 线程安全 | 无问题 | 探针在事件循环线程内、锁块内运行；`_severed_connections` 的读写都在同一个循环里 |
| 静态检查 | 干净 | 干净 checkout 上 `ruff check` 四个源文件全过；`pyright` 0 errors 0 warnings |
| 基线 | 全绿 | 相关四个测试文件 51 passed / 10.4s（`git archive 89002eb` 副本，`PYTHONPATH` 已验证解析到副本树） |

---

## 复现指引

全部产物在 `/tmp/severedrev/`（`/tmp` 可随时删除，仓库内除本报告外未留任何文件）：

- 副本树 `tree/`（`git archive 89002eb`）与 `pristine/`；变异用 `python3 /tmp/severedrev/mutate.py <name>`，`restore` 还原。名字：`always_true`、`always_false`、`no_count`、`severed_benign`、`peek_consumes`、`no_detach`。跑测试时 `PYTHONPATH=/tmp/severedrev/tree/src`。**离开时已 restore 并 `cmp` 确认两个源文件与 pristine 逐字节一致。**
- 探针（`uv run --project /home/xp/src/ghc-api-proxy-py python <file>`）：`probe_fileno.py`（fd 借用的八种情形）、`probe_loop.py`（水平触发 + TLS 第一版）、`probe_tls3.py`（强制未读窗口下的 TLS 多报）、`probe_badfd.py`（ValueError 的爆破半径）、`probe_race2.py`／`probe_race4.py`（`both` 模式窗口的可达性）、`probe_undercount.py`（20 客户端跨信号）、`probe_longdrain.py`（长排空盲区，S-1 的决定性证据）、`probe_order.py`（ready 队列顺序）、`probe_rst.py`（RST 前提）。

## 范围之外

工作树里 `src/app/pipeline/`、`src/app/server/`、`tests/http/` 等属于并行会话的在飞改动，按指令未评审、未改动。`docs/.human-controlled/lifecycle.md` 只读引用，未修改。
