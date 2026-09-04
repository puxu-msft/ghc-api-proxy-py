# 优雅关闭：客户端侧

进程收到关闭信号之后，**面向已连接客户端**的那一半：什么时候停止接受新请求、已建立的连接怎么处理、在途工作保不保、以及运维从收尾行能读出什么。

监听器那一半（socket activation、`SO_REUSEPORT` 平滑重启、代际生命周期）不在这里，见主仓库 `docs/.human-controlled/lifecycle.md`——那是用户亲笔的权威规范，本目录的一切以它为准。

状态：**已落地并进入 main**，2026-08-20。五个提交，见下方「提交」一节。

---

## 起因

生产运行中按 Ctrl-C 触发优雅关闭，出现两个症状：

1. 请求排空后进程不退出，客户端连接仍然保持；
2. 升级信号后打出 `Exception in ASGI application` + `CancelledError`，栈底在 `adapter.py` 的 `await admission_open.wait()`。

## 根因：一道为「暂停」设计的闸被用在了「停止」上

`UvicornListenerAdapter` 在 ASGI 应用外面包了一层准入闸（`gated_app`）。它的设计用途是**滚动重启的 quiesce → resume**：暂停期间到达的请求原地等待，`resume_accepting()` 之后继续。

`stop_accepting()` 会清掉这道闸。关停路径复用了同一个 `stop_accepting()`，但**关停之后永远不会 resume**。于是：

1. 连接池客户端（Claude Code 就是）在排空期间，于已建立的 keep-alive 连接上发来新请求；
2. 该连接早已被 accept、协议对象存活，请求直达 `gated_app`，停在 `await admission_open.wait()`；
3. 这个任务进入 `server_state.tasks`，而 `wait_drained()` 正是轮询等待该集合清空；
4. 排空按设计**无界**（请求自带 deadline，不叠加第二个墙钟上限），于是永久等待。

第二次信号升级到 `FINALIZING`，`cancel_requests()` 取消这些驻留任务，`CancelledError` 从 `gated_app` 逃进 uvicorn 的 `run_asgi`——它 `except BaseException` 后按「应用异常」记日志。**两个症状同一个根因。**

影响面只限**自持监听器的直接运行路径**（`run_standalone` → `StandaloneServer`）。`--fd` 继承监听器的 systemd 路径走 `cli.serve_inherited()`，用 uvicorn 自己的 `Server.serve()`，从不安装这道闸。

## 修法

新增 `ListenerLifecycle.stop_admitting()`，由 `StandaloneServer.serve()` 在 `stop_accepting()` 之后调用一次。名字紧跟 `stop_accepting()` 读作「停止 accept 连接，停止 admit 请求」。它做两件事，**分量不同**：

- **拒绝准入**——修好死锁的就是这一半。把闸从「等监听器回来」翻成「这个请求不会被服务」，驻留中的请求立刻被放行到 503。
- **放掉连接**——让客户端早点知道的那一半。对每条连接调 `connection.shutdown()`。**实测证明这一半不是必需的**：去掉它排空照样结束，因为 `shutdown_lifespan` 稍后本来就会关。它买到的是「池化客户端在长排空期间就知道该另寻出路」。

第一档**不截断任何在途工作**：uvicorn 的 `shutdown()` 对仍在写响应的连接只清 `keep_alive`，响应完整送达（含 chunked 终止块）。`stop_accepting()` 的暂停语义原样保留，滚动路径不受影响。

`open_admission()` / `pause_admission()` 一对公开方法把「闸事件 + 拒绝态」两个字段的写入收拢，`FirstByteRoutingAdapter` 也走它们，不再伸手摸被包装适配器的私有字段。

## 关停收尾行报什么

`ShutdownReport` 有三个与客户端相关的计数，分成两档：

| 计数 | 含义 | 影响 `ok`/`fail`？ |
|---|---|---|
| `connections_asked_to_close` | 被通知关闭的连接数 | 否 |
| `refused_requests` | 被闸当场答成 503 的请求数 | 否 |
| `severed_connections` | 关闭时内核缓冲里还躺着未读请求的连接数 | **是** |

分级的依据是**代价的轻重**，而不是「有没有发生」：

- 被 503 干净回绝的客户端知道该重试；
- 被关闭时请求正在路上的那个拿到 **RST**（内核收到未读字节时发 RST 而非 FIN），对非幂等 `POST` 不可安全重试，而且这些字节从未到达应用，别处无从记录。

**把前者判 `fail`、后者读作 `ok`，正好把运维要做的判断排反了**——这是本次踩过并纠正的一个真实错误。

### `severed_connections` 是下界，不是总数

`MSG_PEEK` 只看**关闭那一瞬间**内核缓冲里有没有字节。客户端在排空窗口后段（生产里可以几十秒）写进来的一切，得到 RST 或裸 EOF，**这个进程里没有任何东西看得见**。

实测：一条在途请求撑开排空，10 条池化连接各发一个 `POST`，10 个全部一无所获，而该计数为 0、收尾行读作 `[ OK ]`；另一组 7 个客户端没拿到答复，计数报 3。

所以在下界这个方向上：**零 ⇏ 没人。** 收尾行的 `ok` 是「没抓到」，不是证书。

**反方向也不是保证。** 明文 h11 下非零基本可信，但 TLS 下等待的字节可能是重协商记录、session ticket 或 close_notify，探针分辨不了，那是**多报**（`_closing_would_sever` 的 docstring 列了三条限制，方向不一致）。所以完整的表述是：**非零是「很可能有人没被服务」，在涉及 TLS 的部署上会被误触；零不代表没人。** 两侧都不是硬保证——这个数字用来引起注意，不用来结案。

---

## 被否定的方案，及否定的理由

- **不修 RST，只加计数**（第三轮之前的处置组合）。分开看都成立，合起来的效果是——**被判为不修的那个代价，恰好就是新计数看不见的那个代价**。这个「处置组合的漏缝」是整条线里最值得记的一条：单条评审各自把关，缝隙出现在两条处置之间。
- **`connections_asked_to_close` 只统计真正当场关掉的连接**（而不是「被通知的」）。评审量到过 1 空闲 + 1 在跑 → 报 2 的失真。要精确就得读 uvicorn 的 `cycle.response_complete` 内部状态，那会随上游重构**静默**给出错误数字；选了改名（原叫 `released_connections`），让措辞与它算的东西一致。**这条讲的是 `connections_asked_to_close`，与 `severed_connections` 无关**——后者是另一次改动，用 `MSG_PEEK` 新增的。
- **借 fd 而非 `dup()`**（`socket.socket(fileno=raw.fileno())` + `detach()`）。已关闭的 transport 报 `fileno() == -1`，而 `socket(fileno=-1)` 抛的是 **`ValueError` 而非 `OSError`**，会从锁里逃出 `stop_admitting()` → 逃出 `serve()`，于是 `_descend()` 与 `_finalize()` 一次都不跑：没有 lifespan shutdown、没有资源释放。改用 `dup()`：拿到的是自己的 fd，忘了关只是泄漏，而借来的 fd 关错了是关掉别人的活连接。
- **给另外三处关连接的地方也加探测**（第二档 `interrupt_connections`、收尾 `shutdown_lifespan`、`both` 模式路由器的 `_pending_sockets`）。第一处不必补（走到那一档必有 incidents）；后两处是真缺口，其中路由器那处就发生在 `stop_admitting()` 的前一句、是同一时刻同一种伤害，而且最好补（socket 就在手上）。**不补的理由**：这个数字结构上不可能完备，加探测点只是把下界抬高一点、代价是更多耦合点；与其让它看起来更像总数，不如让它明确是下界。若要收紧，是产品取舍。
- **把老测试标 `xfail` 或 skip 留着**（见下节）。留下一条没人读的死代码，且掩盖它本来就是竞态这一事实。

## 踩过的坑

- **有一条既有测试在钉 bug。** `test_a_half_sent_request_holds_the_drain_until_the_operator_escalates` 修复后变红。实测证明：它发的 `POST /health/liveness` 打在只注册了 GET 的裸 FastAPI 上，Starlette 只看 headers 就回 405、**从不读 body**——从来没有「还在到达的请求」，撑住排空的就是闸口死锁本身。它的契约正当但夹具表达不了。处置是改夹具（加一个真读 body 的路由 + 肯定式就绪信号），并**把老测试的场景保留下来、换上正确期望**——因为那是唯一一条会因死锁在真实进程里复发而变红的测试，只改夹具等于把这层守卫一并搬走。
- **探针的绿必须先证明它能看见坏行为。** 第一版真实 CLI e2e 修复版与变异版**都正常退出**——没有在途请求时整个关停在毫秒级走完，第二个请求落不进窗口。那一版的绿毫无分辨力。
- **我三次把一个数字的含义说大了**，每次都被独立评审用实测推翻：`refused_requests` 被说成「唯一说明有人没被服务的那个数」→ 证伪；`severed_connections` 被说成「这个数就是那个数」→ 证伪；「拒绝与关连接缺一不可」→ 双向半拆变异证伪。
- **`git checkout -- <file>` 会连同该文件里尚未提交的修改一起清掉。** 复现评审变异时踩过一次。正确做法是按原样反向替换那一处，并前后比对 `git status` 指纹确认工作树逐字节还原。
- **`git commit` 提交的是整个索引，不只是你 `git add` 的路径。** 在多会话共用主仓库时，一次提交把同伴已暂存的改动整个裹走。拆法：`git reset --soft HEAD^` 之后用 `git commit -- <路径>`（带 pathspec 会绕过索引其余部分），且两步必须在**同一次调用**里完成——中间的窗口正是同伴的提交会反过来裹走你的文件的地方。
- **全量测试通过数依赖一个不在版本控制里的输入。** `test_authoritative_example_config_parses` 有 `skipif(not SPEC_PATH.is_file())`，而 `docs/.human-controlled/` 在主工作树里是未跟踪目录。干净 checkout = 1463/3；补上 `config.example.yaml` = 1464/2。我一度把这个差额错误归因为「并行会话污染」。

## 测量口径

供下一个人对账，**路径与行号是 2026-08-20 的快照**：

- 干净 checkout（`89002eb`）= **1463 passed / 3 skipped**；补上未跟踪的 `docs/.human-controlled/config.example.yaml` = **1464 / 2**。
- 切断窗口宽度：tick 计数器实测 **5/5 次恰为一次事件循环迭代**。
- 命中率：40 条池化连接跨信号错峰写入，我报 3 次命中 2 次；独立审计在合适节奏下量到 **90%–100%**，即我的说法偏保守。
- `refused` 与 `severed` **此消彼长**：同一批字节，被事件循环读走的进前者，没被读走的进后者。两者都是概率性的——单客户端下 `refused` 约 13% 非零（只在 gap≈0 那一格），并发下也可以稳定为 0 而 `severed` 非零。
- 真实进程实测的三行收尾（`reports/` 与 `.dev/exp/graceful-shutdown-client-side/` 可复跑）：

```
[ OK ] stopped — 40 connections asked to close, 11 requests refused
[FAIL] stopped — 40 connections asked to close, 8 requests refused, 8 connections severed with a request already sent
[FAIL] stopped — 40 connections asked to close, 9 requests refused, 10 connections severed with a request already sent
```

## 提交

主仓库 `main`，未推送。按时间顺序：

| 提交 | 内容 |
|---|---|
| `9b8114a` | 死锁本身：`stop_admitting()`，503 拒绝 + 主动放掉连接 |
| `8d8026b` | 空闲连接守卫改为见证它自己命名的那一档（原版对该机制零分辨力） |
| `a279de3` | 把 503 从事故降级；补上完全缺失的 `ok`/`fail` 判定测试 |
| `89002eb` | `MSG_PEEK` 探测，区分「真空闲」与「有在途请求」 |
| `693dd0d` | 把 severed 定位成下界；`dup()` 取代借 fd |

历史注记：这条线的第一个提交被并行会话**重写过两次**，`1a7353e` → `f37068c` → `9b8114a`；前两个哈希如今都不可达（对象暂时还在，会被 gc 回收）。判据是 **blob 同一性而非补丁文本**——8 个 `src/` 与 `tests/` 路径在 `1a7353e` 与 `9b8114a` 下逐一同 blob（2026-08-20 核过）；补丁文本会因父提交不同而出现上下文差异，用它比对会得出错误结论。

**当时几条提交的 `Docs:` 尾注逐字写的是 `docs/tmp/260820-*.md`，那些文件现已搬到本目录 `reports/`**，对照关系见下——历史没有重写，尾注保持原样，`git log` 里仍按 `docs/tmp/` 搜得到。

## 遗留张力，交给用户裁决

- ~~`docs/2604-rewrite/shutdown.md` 第 17 行与第一档行为冲突~~ —— **已消解**。用户于 2026-08-20 裁定 `docs/2604-rewrite/` 整体过期（早期对 `copilot-api-js` 的学习笔记，非本项目设计），已移入 `.dev/docs/archived-2604-rewrite/`。那一行是笔记而非待实现的设计，不构成冲突。我先前判断它「不是活载体」（三个符号在 `src/` 中不存在）与这条裁决同向，但当时把它当成了「计划中的设计」，那一步高估了它。
- **另外三处关连接的地方不做切断探测**，见上文「被否定的方案」。其中 `both` 模式路由器的 `_pending_sockets` 那处十行以内可补，若日后觉得下界抬得不够高，那是第一个该动的地方。
- **503 错误信封用了 Anthropic 的 `overloaded_error`**，WebSocket 用 1012（实际被 uvicorn 转成 HTTP 403，码与 reason 都被丢弃）。这是我选的默认，未经裁决。
- **`both` 模式每次关停都会打一条 `accepted connection routing crashed` 的 ERROR**（第三轮评审 O-1）。**既有缺陷**，与父提交逐行比对确认本次未引入也未加重，但没人修过它。
- **`pause_admission()` 会连拒绝态一起清**（第三轮 F-3），使「已唤醒但未恢复」的等待者可能从被 503 变成被正常服务。当前不可达，但不可达性依赖「`asyncio.Lock` 无竞争不让出」和「第二次 `stop_accepting` 时 `routing_tasks` 恰好为空」两个实现细节，没有任何东西在守。
- **让 fd 用法安全的两条性质没有守卫**（第四轮 S-5）：去掉 `MSG_PEEK`（探针真的消费字节）测试全绿。改用 `dup()` 之后最阴险的一条（误关别人的 fd）已不复存在，但「不消费」这条**结构上无法守**——每条被探测的连接随即被关，观察不到「字节仍被交付」。

## 本目录

| 文件 | 内容 |
|---|---|
| `reports/260820-graceful-shutdown-admission-deadlock.md` | 我的工作记录原件：完整根因、四轮评审的逐条处置表、被证伪的断言 |
| `reports/260820-shutdown-fix-review-gpt.md` | 第一轮对抗评审（并发与生命周期） |
| `reports/260820-shutdown-test-rebase-review.md` | 第一轮专项：「改掉挡路的既有测试是否护短」 |
| `reports/260820-shutdown-mutation-audit.md` | 第二轮：复算我自称的变异结果 |
| `reports/260820-shutdown-delta-review.md` | 第三轮：审「回应评审后又改、却没人看过」的那批 |
| `reports/260820-severed-probe-review.md` | 第四轮对抗评审：探针本身 |
| `reports/260820-severed-measurement-audit.md` | 第四轮：复算探针的测量声称 |
| `reports/260820-closeout-review.md` | 第五轮：审这套归档文档本身（0 blocker / 4 major，四条都已按它改） |

可跑的探针在 `.dev/exp/graceful-shutdown-client-side/`。
