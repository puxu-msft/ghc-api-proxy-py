# 评审：`db49581` 排空期间不再开新的上游请求

**日期**：2026-08-22
**评审对象**：主仓提交 `db49581`（`feat: stop opening new upstream requests once the process is draining`）
**评审者**：独立子代理（异源）
**结论**：**needs-fix**（blocker 0 / major 3 / minor 5 / 参考 2）

## 0. 前置说明与方法

**派发要求的 `my-skills:as-reviewer` 技能不存在**（`~/.claude/skills/` 下确认无此项），按派发的备选指示改用 `verifying-authoritative-claims` 与 `trusting-a-green-result` 两份方法论。

### 变异检验的隔离与还原

主工作树是共享的，且**同伴正在改 `src/app/cli.py`**（未提交的 TLS 接线）与 `tests/systemd/test_systemd_pipeline_unit.py`。因此本次**没有在主工作树上做任何变异**：

- 用 `git -C <repo> archive db49581 | tar -x -C /tmp/rev-db49581` 取出被评审提交的**只读快照**（不触碰 `.git`，不建 worktree，不动主树一个字节）。
- 用主树 venv 的解释器 + `PYTHONPATH=/tmp/rev-db49581/src` 运行，并**先验证导入解析到副本**（`app.__file__ == /tmp/rev-db49581/src/app/__init__.py`），再开始读任何数字。
- 每次变异前先冻结 `sha256` 清单，变异后**在测试观测的那一层证明变异确实生效**（`inspect.getsource` 读运行时加载的那份），还原一律用 `git show db49581:<path> >`（按提交对象逐字节重写），随后 `sha256sum --check` 复核。
- **全部 5 次变异的还原均逐字节复核通过**，末次复核输出：`src/app/cli.py: OK` / `src/app/pipeline/direct_driver/base.py: OK` / `src/app/server/pipeline_app.py: OK` / `src/app/server/handler.py: OK` / `src/app/pipeline/delivery/stream.py: OK`。
- 主工作树在整个评审期间未被修改，未 `git add`，未 `git commit`。临时探针脚本 `/tmp/probe_signal_lock.py` 已删除；副本目录 `/tmp/rev-db49581`、`/tmp/rev-pristine` 亦已删除（可用同一条 `git archive` 命令重建）。

### 共享树的并发情况（影响本报告的保质期）

评审期间同伴仍在主树上工作：开始时 `src/app/cli.py` 已有未提交的 TLS 接线，结束时 `handler.py`、`pipeline_app.py`、`config/*` 等又多出若干改动。**本报告的全部判断针对 `db49581` 的树**。已核：结束时刻 `handler.py`（1 行）与 `pipeline_app.py`（2 行）的未提交改动**不含任何 drain 相关 hunk**（`git diff` 里 `draining` / `LedgerBudget` / `_reopen` / `_hand_over` 零命中），所以结论未被这些并发改动作废；但报告里的**行号是 `db49581` 的快照**，落地时请按符号名而非行号定位。

### 基线

- `ruff check src tests`（在副本上）：**All checks passed**。
- 全量 `pytest tests`（在副本上，即 `db49581` 的树）：**1794 passed, 2 skipped, 1 failed**。
  唯一那条失败是 `tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses`，原因是 `db49581` 树里的 `docs/.human-controlled/config.example.yaml` 仍带 `upstream_request_retry.strategies.streamReplay`，而 schema 早已删掉该键。**与本提交无关**，且用户在工作树里已自行删去该键（`git diff` 可见），主树现状不再触发。写在这里是为了防止有人把这条失败误读成本提交的问题。

---

## 1. 核实为正确的部分（先说对的）

以下每条都独立复核过，作者的自述成立。

**V1 · 三处变异检验各自转红且只红对应测试** —— 证据等级：**一手实测**。

| 变异 | 结果 |
|---|---|
| `base.py` 的 `if self.draining is not None and self.draining():` → 前置 `False and` | `test_a_draining_process_does_not_open_another_upstream_attempt` 与 `test_the_drain_is_read_at_each_refusal_rather_than_at_construction` 红，另 3 条绿 |
| `pipeline_app.py` 的 `if chain.active_requests.draining:` → 前置 `False and` | 仅 `test_a_draining_process_does_not_replay_a_stream_the_client_never_saw` 红（`calls` 变成 10），另 4 条绿 |
| `cli.py` 的 `handle_exit` 去掉 `self._on_draining()` | 仅 `test_the_systemd_path_says_when_it_stops_accepting` 红（`assert [] == [1]`），同批 55 条绿 |

**V2 · 「每次读取」与「构造时采样」确实可分辨** —— 证据等级：**一手实测**。把 `LedgerBudget` 改成带 `_sampled: bool` 字段 + `__post_init__` 里采样一次、`take_for` 读快照，结果**只有** `test_the_drain_is_read_at_each_refusal_rather_than_at_construction` 转红（`assert True is False`），兄弟测试（构造时 `draining` 就为真）照常绿。该测试对这条判据有真实鉴别力，不是靠命名自证。

**V3 · `LedgerBudget` 没有漏传 `draining` 的活跃路径** —— 证据等级：**代码事实**（`rg` 全仓 + 调用链）。`src/` 内 `LedgerBudget(` 的构造点**只有一处**：`handler.py:180`，且传了 `draining`。而 `handler.handle()` 是所有客户端请求驱动的唯一漏斗——翻译路径（主产品路径 Anthropic Messages → OpenAI Responses）在 `handle()` 内部先翻译再走同一个 `DRIVERS[route.endpoint]`，不另建 driver。`_reopen` 里的第二次入口也是 `await handle(...)`。所以「守卫被留在 legacy 链路上」那种形态在今天不成立。

**V4 · `RetryBudget` 没有生产调用点** —— 证据等级：**代码事实**。`budget=RetryBudget(` 只出现在 `tests/unit/pipeline/subscribers/test_builtin_subscribers.py`、`tests/unit/pipeline/test_direct_driver.py`、`tests/unit/pipeline/test_timeout_enforcement.py`。它没有排空闸不构成缺口。（它仍是 `Budget` 协议的一个公开实现，将来有人拿它接生产会静默失效——但这是 m5 的一部分，不单独记。）

**V5 · 直调 `handle_exit` 与 uvicorn 真实信号路径等价，且这条路上没有别的排空入口** —— 证据等级：**一手实测**（读 venv 内 uvicorn 0.52.4 源码 + 反查本仓接线）。

- `uvicorn/server.py:323-340` 的 `capture_signals()` 用 `original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS}` 注册，`HANDLED_SIGNALS = (SIGINT, SIGTERM)`。注册的是**绑定方法**，所以子类覆盖的 `handle_exit` 就是真正被装上的那个。测试的直调与信号路径同一入口。
- 其余可能路径逐条排除：① lifespan 失败走的是 `startup()` 里的 `sys.exit(STARTUP_FAILURE)`，那不是排空；② 外部直接置 `should_exit = True`——全仓无此写法，`serve_inherited` 内也没有别人持有该 server 引用；③ **SIGUSR2 平滑重启协议触及不到这条路**：`cli.py:255` 明确让 `--fd` 与 `--pidfile-dir` / `--force-write-pidfile` 互斥，`--fd` 进程不写 pidfile，`--restart` 找不到它，而 uvicorn 的 `HANDLED_SIGNALS` 里也没有 SIGUSR2。
- 唯一在理论上绕开 `handle_exit` 的是 `limit_max_requests`（`on_tick` 里达到上限直接让 `main_loop` 返回 True），本项目构造 `uvicorn.Config` 时未设该项，故非活口。见「参考 i2」。

**V6 · 两道闸互不重叠，也没有互相兜底** —— 证据等级：**一手实测**。只去掉 `_reopen` 那道闸时，端到端测试记到 **10 次上游调用**——因为交付层的重放预算由 `decide_stream_ending` 直接 `ledger.take(reason)` 花掉（`retry.py:140`），**从不经过 `LedgerBudget.take_for`**。所以「两扇门」的说法准确：驱动层那道闸拦不住交付层的重放，反之亦然。

**V7 · 排空拒绝重开后客户端拿到的形态，作者说的是对的** —— 证据等级：**代码事实 + 一手实测**。`_reopen` 返 `None` → `stream.py:342` 的 `if replacement is not None` 不成立 → 落到 `_hand_over(...)` → `committed_count == 0` 命中 `return None`（`stream.py:414-416`）→ `raise torn`。变异 2 的运行日志印证了未拦时的对照面（`H1/H1 200 ... retries=9: stream failed before a terminal event`）。即 **HTTP 200 + 半截 SSE + 连接撕断，不发 error 帧**，正是 `deferred.md` §5 已登记的既有形态（第 2 格）。作者把它「按现状钉住而不是按应然钉住」并在 docstring 里写明，这个处理是对的。

**V8 · 「走到 `_reopen` 时必然没有可交接的内容」这条推理链成立** —— 证据等级：**代码事实**。逐环核对：

1. `_reopen` 只作为 `ReplaySupport.reopen` 传出，全仓唯一调用点是 `stream.py:341`，且在 `if verdict.ending is StreamEnding.REPLAY:` 之内。
2. `decide_stream_ending` 返回 `REPLAY` 只在 `if not downstream_opened:` 分支内（`retry.py:138-142`）。
3. `downstream_opened=client_has_bytes.is_set()`（`stream.py:332`），而 `client_has_bytes.set()` 只出现在 `_commit(...)` 产出 chunk 的那个循环里（`stream.py:289`）。
4. `session.committed_count == len(session.delivered)`，`delivered` 只在 `DeliverySession._commit` 里 `blocks` 非空时扩展（`blocks.py:156-161`），而那正是产出 chunk 的同一个条件。

所以循环内恒有 `committed_count > 0 ⟹ client_has_bytes 已 set`，逆否即「走到这扇门时 `committed_count == 0`」。**没有别的调用点能让 `_reopen` 在已交付内容的情况下被调用。**

**V9 · 端到端测试里 `pytest.raises` 不是恒真断言** —— 证据等级：**一手实测**。这是派发点名要查的。把 `_hand_over` 的 `if session.committed_count == 0 and ...` 前置 `False and`（只动这一处），该测试报 `Failed: DID NOT RAISE RemoteProtocolError`。所以它有两条活断言：`len(calls) == 1` 钉排空闸，`pytest.raises` 钉结局形态。**对该闸不敏感 ≠ 恒真**，docstring 也已声明它钉的是形态。这一条作者写对了。

---

## 2. 发现

### major-1 · `handle_exit` 在真信号处理器里取非重入锁，可自锁死 —— 证据等级：**一手实测**

**机制**：uvicorn 用的是 `signal.signal`（源码里还专门写了注释说明「always use signal.signal, even if loop.add_signal_handler is available」），所以 `_DrainAnnouncingServer.handle_exit` 是**真正的 C 级信号处理器**，在主线程任意字节码边界被插入执行。它第一件事就是调 `chain.active_requests.begin_draining()`，而该方法要拿 `ActiveRequestRegistry._lock`（`threading.Lock`，非重入，`active_requests.py:30/51-53`）。这把锁**同一个主线程可能正持有**——`draining` 属性读、`add`／`release`／`set_attempts` 每个请求都进出它一次。信号落在临界区内，处理器就会在 `acquire()` 上永久阻塞，而锁的持有者正是被它中断的那个线程。

**实测**（副本树，带正样本对照）：

- 对照组（处理器不取锁）：`entering critical section` → `HANDLER RAN` → `still inside critical section` → `COMPLETED`，rc=0。**这一组同时证明了注入生效**——信号处理器确实在主线程持锁期间被执行了。
- 危险组（处理器调 `begin_draining()`）：印出 `entering critical section` 之后**永久静止**。附带效果值得记一笔：外层 `timeout 10` 发的 SIGTERM 也救不了它——处理器本身就是卡住的那个，后续信号只能排队。最终靠 `kill -9` 收尾。

**后果**：正是本提交要防的那件事——关机永远排不完，只能等 systemd 的 `TimeoutStopSec` 到点 SIGKILL，届时在途请求全丢。

**权重与分级**：**机制已一手证实，可据此行动**；但**生产触发概率未测且应当很低**——临界区只有几条字节码，而本服务的实测流量是每天 429 个请求。所以定 **major** 而非 blocker：不是系统性失效，是一个窄窗口内的挂死。之所以仍按 major 报，是因为修法只有一行、ROI 极高，且失效面恰好是关机路径本身。

**注意这是本提交新引入的**：独立模式那侧安全，因为 `standalone.py:336` 用的是 `loop.add_signal_handler(sig, self.receive_signal, sig)`，回调作为普通事件循环任务运行，不在信号上下文里。systemd 这条路是第一次让 `begin_draining` 跑在真信号处理器里。

**候选修法（不代评审做裁决）**：① `handle_exit` 里不直接置位，改为 `loop.call_soon_threadsafe(...)`——但信号处理器里取 loop 引用也要小心；② 更简单：`_draining` 是**单向单调的写一次布尔**，读写在 GIL 下本就是原子的，`begin_draining` 与 `draining` 根本不需要那把锁（`snapshot` 等仍需要）；③ 换成 `threading.Event`，其 `set()` 内部也用锁，同样不安全，不推荐。

### major-2 · 「交接需要已交付的内容」这条理由是错的，据它把一个未裁决的问题记成了已裁决 —— 证据等级：**一手实测 + 人写文档原文**

提交信息、`base.py`／`pipeline_app.py` 两处 docstring 与 `status.md` 的更正段，都把这件事记成已经想清楚了，理由是：「a hand-over needs delivered content to hand over」。

**这句关于机制的陈述是假的。** 实测：只把 `_hand_over` 的 `if session.committed_count == 0 and stop_reason not in continuation.stop_reasons:` 短路掉，排空拒绝重开的那条流立刻产出一次干净的交接——日志 `upstream_replay_refused_while_draining` → `auto_retry_tool_not_declared` → `H1/H1 200 ... : turn handed back to the client to continue`，`status=retry`。交接机制**不需要**已交付内容：`_hand_over` 在 `if not started:` 时会自己补 `framer.preamble()`（`stream.py:424-425`）。真正让排空落到裸抛的，是**一道可配置的闸**，不是机制的固有属性。

**而人写文档那句话恰恰长在这一格里。** `docs/.human-controlled/upstream-retry-and-continuation.md:21-22`：

> 如果业务可能可以继续，区分是否已经向客户端交付过完整块。如果还没交付过完整块，直接在代理端无痕重试。无痕重试不设冷却间隔。
> 特别地，优雅关闭时报错不再考虑无痕重试，可以走下文合成续写机制。

「特别地」承接的就是**还没交付过完整块**那一句。所以这句话说的正是这扇门：本来该无痕重试的，关机时改成**可以**走合成续写。

**两个版本要分开说，这一点必须写清楚**：

- 用户工作树里的**当前**措辞是「**可以**走」，且新增的「输出超长」一节给出了平行句式「要么在能续写的情况下……走下文合成续写机制；要么在不能续写的情况下，直接返回给客户端」。按这个读法，**拒绝交接是被允许的**，作者的结论站得住。
- 但 `HEAD` 里**已提交**的版本是「特殊地，优雅关闭时不应无痕重试，**走**下文『MCP-driven 合成续写』机制」——那是命令式，没有留余地。提交信息开头「it must hand the turn back instead」用的正是这个旧措辞，说明作者是对着旧版本工作的，然后凭代码现状把它推翻了。**文档与代码冲突时以代码为准，方向是反的**；这类方向问题按项目规矩要交用户裁。

**综合判断**：作者的**结论**（今天的代码不会把关机变成交接）为真，且在当前人写措辞下**也是被允许的**；但**给出的理由是假的**，而那个假理由正是让这个问题看起来「已经关掉」的东西。请求处置：把理由改成真实的那个（「`_hand_over` 的 `committed_count == 0` 闸不放行，而这一格是否要为排空开口是产品裁决」），并在 `deferred.md` §5 登记，而不是在提交信息与 docstring 里记为已决。

### major-3 · 排空闸让一条既有的丢失式结局变得常态可达；`full` / `until-tool-use` 下会丢掉一份已经组装完的回答 —— 证据等级：**代码事实（推理链每环已核）**

场景（`client_delivery.buffering_policy: until-tool-use` 或 `full`，两者都是已发布的配置值，`schema.py:15/286`，默认是 `block`）：

1. 一个长回合正在进行，上游已产出若干**完整块**，但缓冲策略把它们全压在 `BlockBuffer` 里没有释放——`stream.py:295` 自己的注释就写着「under `full` and `until-tool-use` [the pre-first-block window] is the entire turn」。
2. 于是 `session.committed_count` 仍是 0，`client_has_bytes` 未 set。
3. SIGTERM 到达，排空开始；上游 body 此时撕裂。
4. `decide_stream_ending` 因 `not downstream_opened` 返回 `REPLAY`（并已花掉一次预算）。
5. 排空闸让 `_reopen` 返 `None`。
6. `_hand_over` 因 `committed_count == 0` 返 `None`。
7. `raise torn`——**缓冲区里那几个完整块被整批丢弃**，客户端拿到 HTTP 200 + 撕断连接。

**本提交之前**，第 5 步会重放并大概率成功（排空本来就在等这个请求）。之后，同样的场景变成「什么都没有」。

这与 major-2 是同一处闸的两个面：`_hand_over` 一旦被允许在 `committed_count == 0` 时动作，它做的第一件事就是 `session.finish()` 把缓冲块冲出去再附上 `tool_use`（`stream.py:423-429`），恰好把这一格补上。**修 major-2 就同时修掉这条。**

分级为 major 而非 blocker：默认策略 `block` 不受影响（第一个块一释放 `downstream_opened` 即为真，重放本就不合法）；触发需要非默认配置 + 关机 + 撕流三者同时。但这三者都不罕见，而丢失的是一整份已经算完的回答。

### minor-1 · 同一个提交里两处 docstring 对同一件事给出相反的说法

- `base.py:69`：「`upstream-retry-and-continuation.md` rules it out and **points the ending at the hand-over instead**.」
- `pipeline_app.py:662`：「**What the client gets instead is the truncated-stream ending, not a hand-over**」

提交信息说这次专门更正了前一种读法，结果只改了一处。而且在**驱动层那扇门**上，`base.py` 的说法错得更彻底：那道闸在响应头都还没拿到时就拒绝，客户端收到的是一个 HTTP 错误响应（状态码由 `error_status` 读穿 `PipelineAbort.cause` 得到上游真实状态，`handler.py:408`），根本不在 SSE 交付路径上，交接在那里连讨论的余地都没有。

### minor-2 · `base.py:74` 给「在花预算之前拒绝」的理由不成立，而另一扇门的行为正相反 —— 证据等级：**代码事实**

注释说：「the same request may still be handed back to the client, and **that path reads the same ledger**」。核对下来，交接路径 `_hand_over` → `ContinuationSupport.synthesize` = `_hand_back_streaming` → `_hand_back`（`pipeline_app.py:545-...`）读的是 `route.wire_format`、配置里的工具名、`context.payload["tools"]`、`_replay_reason`——**没有任何一处碰 `RetryLedger`**。全仓 `rg` 也确认 `RetryLedger` 的字段只被它自己的 `consider`／`take` 读。

更值得记的是两扇门在这一点上**行为相反**：交付层那侧，`decide_stream_ending` 在返回 `REPLAY` 之前就已 `ledger.take(reason)` 花掉一次（`retry.py:140`），`_reopen` 的排空拒绝发生在**之后**。所以「排空拒绝不花预算」只在驱动层成立，交付层照花。今天无害（此后没有读者，随即 `raise`），但注释给出的理由既不真、也不适用于它自己的兄弟门。

### minor-3 · `decisions.md` 的索引没跟着更新

`.dev/docs/upstream/retry-and-continuation/decisions.md:26` 仍写：

> | 优雅关闭不无痕重试，**改走** MCP-driven 合成续写 | 第 25 行 |

两处过期：措辞「改走」对应的是 `HEAD` 里的旧句，用户当前文本是「可以走」；行号「第 25 行」也已变成第 22 行。本提交更正了 `status.md` 对同一件事的表述，却没动它的兄弟索引——同一语义变更的两处复述只更新了一处。（该文件自己声明「凡两者不一致，以人写文档为准，并来改本文件」，所以这是它自己定的义务。）

### minor-4 · `deferred.md` §5 第 2 格的触发条件清单少了一项

原文：「没交付走无痕重试；但**重试预算耗尽或 `reopen()` 自己也失败时**，既无内容也无续写。」本提交新增了第三个触发条件——**排空主动拒绝重开**——且它比另外两个常见得多（每次带在途流式请求的优雅重启都可能撞上）。未登记。

### minor-5 · 提交标题与两处 docstring 的范围陈述强于实现

标题是 `stop opening new upstream requests once the process is draining`，docstring 是「a process that has stopped accepting has promised not to take work on」。实际实现拦的是**重试与重放**，不是「新的上游请求」这个全称。至少两条路径在排空期间仍会开出**第一次**上游请求：

- **被 `InFlightLimit` 排队的客户端请求**（`admission.py`，`max_inflight` 默认 50）。排空开始时，队列里等槽位的请求已经被 accept、任务已存在，槽位一空就照常往下走 `handle()` → `driver.run()` → 首次 `send`。首次发送不经过 `take_for`，两道闸都管不着。
- **`/v1/messages/count_tokens`**：`pipeline_app.py:443` 走 `handle_count_tokens`，完全不经过 `handle()`／`LedgerBudget`，内部还会在 provider 间回落。

两者大概率都是**正确行为**（排空的定义就是让已接下的活干完），所以这不是要求改行为，而是**措辞收窄**：说「排空期间不再开新的上游**尝试**（重试与重放）」才与实现相符。项目吃过「全称量词在自己的报告里失守」的亏，这条按同一标准报。

---

## 3. 参考（非本提交引入，仅备查）

**i1** · `serve_inherited` 的 `finally: await http_client.aclose()` 在 systemd 路径上**不会执行**。uvicorn 的 `capture_signals` 退出时先恢复原处理器再 `signal.raise_signal(captured_signal)`（`server.py:336-340`），SIGTERM 的默认动作直接终止进程，而这发生在 `await server.serve()` 返回**之前**。属 uvicorn 0.52.4 的既有行为，与本提交无关，且进程即将退出，实害有限。

**i2** · `uvicorn.Config(limit_max_requests=...)` 若将来被设上，`on_tick` 达到上限会让 `main_loop` 直接返回 True 走 `shutdown()`，**完全不经过 `handle_exit`**，排空标志静默保持假——即本提交之前的行为原样回来。今天没设，故非活口；记一行是因为它是唯一一条能悄悄退回旧行为的路。

---

## 4. 处置建议（供主会话裁决，评审不代做）

| 编号 | 建议 | 是否需用户裁决 |
|---|---|---|
| major-1 | 让 `begin_draining` 不在信号上下文里取非重入锁（推荐：该布尔单向单调，去掉它自己那把锁即可） | 否，实现选择 |
| major-2 | 把 docstring／提交后续文档里的假理由换成真理由；把「排空这一格是否为交接开口」登记进 `deferred.md` §5 | **是**——「分类器／位置判据默认可否继续」是产品裁决 |
| major-3 | 随 major-2 一并；若暂不开口，至少在 `deferred.md` 记明 `full` / `until-tool-use` 下的丢失场景 | 同上 |
| minor-1/2 | 改正两处 docstring 的事实陈述 | 否 |
| minor-3/4 | 同步 `decisions.md:26` 与 `deferred.md` §5 | 否 |
| minor-5 | 收窄标题／docstring 的范围措辞（历史提交信息不改，改的是活文档与代码注释） | 否 |
