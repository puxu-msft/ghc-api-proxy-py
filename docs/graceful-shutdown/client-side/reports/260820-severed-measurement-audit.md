# 复算「真的被切断」那一格的测量声称（2026-08-20）

审计对象：`docs/tmp/260820-graceful-shutdown-admission-deadlock.md` 最末一节「用户裁决：把「真的被切断」那一格量出来」里的全部测量声称。
被审提交：`89002eb feat: count the connections the drain actually cut off`。

**总判定：声称成立，其中一条（第 5 条，对第三轮评审的更正）部分成立，需要收窄。另有一条正文之外的附带结论（全量数字 1464 不可复现）判定为不成立——那个数字完全可复现，归因写错了。**

## 结论一览

| # | 声称 | 判定 | 依据强度 |
|---|---|---|---|
| 1 | 单连接扫时序四次全部落空，`severed_connections` 恒为 0 | **成立** | 82 次真实进程运行，severed 全 0。足以据此行动 |
| 2 | 40 条池化连接错峰写入，3 次尝试命中 2 次 | **成立，且是保守说法** | 110 次运行；在合适的写入节奏下命中率 90%–100%，量级与三行样例逐条复现 |
| 3 | 纯拒绝 → `[ OK ]`，出现 severed → `[FAIL]` | **成立** | 真实进程两侧都拿到实测行；另有确定性变异佐证 |
| 4 | 窗口约一次事件循环迭代宽 | **成立，可以说得更死** | tick 计数器实测 5/5 次恰为 1 次迭代；有源码结构佐证 |
| 5 | `refused_requests` 的「恒为 0」只在单客户端下成立，并发下稳定非零 | **部分成立** | 两半都要收窄：单客户端下也不是恒为 0；并发下也不是稳定非零 |
| 6 | 三个变异分别打红对应的测试 | **成立，逐字对得上** | 全量跑三遍，红名单与断言值精确匹配 |
| 附 | `89002eb` 全量 1464 在脏树上量、不可复现 | **不成立（归因错误）** | 干净 checkout 上补一个未跟踪文件即精确复现 1464 / 2 |
| 附 | 新增正样本测试连跑稳定 | **成立，已扩展到负载下** | 60 次连跑全绿（空闲 20 + 负载 20 + 重负载 20） |

## 方法与可复算性

全部实验在 `/tmp/severed-audit`——`git clone /home/xp/src/ghc-api-proxy-py` 后 `checkout 89002eb` 的私有副本，实验前后 `git status` 均为空。主工作树 `/home/xp/src/ghc-api-proxy-py` 除本报告外未被写入。

探针在 `/tmp/severed-probe/`：

- `child.py` —— 真实子进程：最小 FastAPI（`GET|POST /quick`）+ `run_standalone()` + 生产代码的 `report_shutdown(outcome.report)`。收尾行由生产代码产出，不是我重新拼的；另外多打一行 `REPORT {json}`，让审计读原始计数而不是解析散文。
- `probe.py` —— 父进程：`single <gap> [settle]` 与 `pool <n> <stagger> <pre>` 两种形态，真实 socket、真实 `os.kill(SIGTERM)`。
- `child_window.py` / `run_window.py` —— 事件循环 tick 计数器 + 时间戳，量窗口宽度。

**一处限制，先说清楚**：我跑的是自己的最小子进程，不是 `uv run ghc-api-proxy start` 的完整 pipeline（那需要真实上游凭据）。生命周期与收尾行的代码路径逐字相同（`run_standalone` → `StandaloneServer.serve` → `stop_admitting` → `report_shutdown`），但 pipeline app 的中间件与订阅者不在场。对本次要复算的这几条声称，这个差别不影响判据；如果哪天要量 pipeline 自身对时序的影响，这份数据不能直接外推。

**一个我自己踩到、原文档没有记录的陷阱**：建池时若在每条连接握手后做「盲读到超时」的排空，40 条连接的建池要花 8 秒，uvicorn 默认 5 秒 keep-alive 超时会在爆发开始前悄悄关掉前十几条——我第一版探针因此量到 `asked=24` 而不是 40，而计数本身看不出异常。改成按 `Content-Length` 精确读完即返回后才是 40。原文档报的是 `40 connections asked to close`，说明它的池是完整的，这条不影响它的结论；但任何人要重跑，这一格必须先对上。

## 1. 单连接扫时序：成立

gap 定义同原文（信号到客户端下一次写的间隔，负数表示先写后发信号）。三批次共 **82 次真实进程运行**：

| 批次 | 握手方式 | gap 集合 | 每格次数 | severed |
|---|---|---|---|---|
| A | 盲读排空（有 keep-alive 干扰） | {-0.05, 0, 0.002, 0.05} | 3 | 全 0 |
| B | 精确读 | {-0.005, -0.001, 0} | 10 | 全 0 |
| C | 精确读 + settle 0.2s | {-0.05, 0, 0.002, 0.05} | 10 | 全 0 |

**`severed_connections` 在 82 次里全部为 0。声称成立，强度足以据此行动。**

**但原文给出的理由有一半不准。** 原文写「gap ≤ 0 时服务端来得及读走并正常回应」。实测在 gap = 0 这一格，请求有时并没有被「正常回应」，而是被闸答成 503：

```
gap=0.0  [ OK ] stopped — 1 connections asked to close, 1 requests refused
```

gap = 0 共 23 次运行（批次 A 3 次、B 10 次、C 10 次），其中 **3 次 `refused=1`**（批次 A 里 2 次、批次 C 里 1 次），其余 20 次 `refused=0`。所以正确的说法是：gap ≤ 0 时请求已经落到服务端手里，**要么被正常回应、要么被答成 503，两种都不算「被切断」**。结论没变，理由要补这半句——而且这半句正是下面第 5 条要用的证据。

## 2. 40 条池化连接：成立，而且 2/3 是保守说法

写入节奏是决定性变量，而原文**没有记录**它用的 stagger 与信号时点。我只能扫参数找到同一现象的所在区域。共 **110 次 40 连接运行**（池完整，`asked = 40`），按配置分组的命中率（命中 = `severed ≥ 1`）：

| stagger (s) | pre (s) | 命中 / 运行 | severed 范围 | refused 范围 |
|---|---|---|---|---|
| 0 (不错峰) | 0.005 | 0 / 3 | 0 | 0 |
| 0.0001 | 0.002 | 6 / 6 | 7–13 | 3–7 |
| 0.0001 | 0.005 | 8 / 8 | 3–13 | 5–11 |
| 0.0002 | 0.005 | 26 / 27 | 0–10 | 0–7 |
| 0.0002 | 0.008 | 6 / 6 | 3–5 | 0–2 |
| 0.0002 | 0.0095 | 8 / 8 | 3–8 | 0–9 |
| 0.0002 | 0.012 | 6 / 14 | 0–8 | 0–9 |
| 0.0003 | 0.006 | 6 / 6 | 2–7 | 0–3 |
| 0.0005 | 0.008 | 4 / 4 | 2–3 | 0–1 |
| 0.0005 | 0.01 | 3 / 3 | 1–4 | 0 |
| 0.001 | 0.015 | 4 / 4 | 1–2 | 0 |
| 0.001 | 0.02 | 14 / 15 | 0–2 | 0 |
| 0.002 | 0.04 | 1 / 3 | 0–1 | 0 |
| 0.005 | 0.1 | 0 / 3 | 0 | 0 |

`0.0002 / 0.005` 那一格的 27 次里有 10 次用的是第 4 节的插桩子进程（多一个 tick 计数任务），会改变调度；这 10 次单独看是 10/10，去掉它们仍是 16/17，方向不受影响。

**「3 次尝试命中 2 次」没有被夸大，反而低于我在同一现象区间量到的水平**：在 0.1 ms–1 ms 错峰、信号落在爆发中段的配置里，命中率是 90%–100%（例如 0.0002/0.005 是 26/27，0.001/0.02 是 14/15，0.0001/0.005 是 8/8）。两端各有一个失效区：完全不错峰（40 次写在同一微秒批里，全部赶在信号前被读走）命中 0/3；错峰太宽（5 ms）窗口相对整个爆发太窄，命中 0/3。信号落得太晚（0.0002 / 0.012，爆发已近尾声）也会掉到 6/14。

原文那三行样例我**逐条复现到了同一量级和同一措辞**：

```
[ OK ] stopped — 40 connections asked to close, 5 requests refused
[ OK ] stopped — 40 connections asked to close, 6 requests refused
[FAIL] stopped — 40 connections asked to close, 8 requests refused, 2 connections severed with a request already sent
[FAIL] stopped — 40 connections asked to close, 9 requests refused, 1 connections severed with a request already sent
[FAIL] stopped — 40 connections asked to close, 6 requests refused, 5 connections severed with a request already sent
```

其中包含原文最难对上的两格：**「40 条、只有拒绝、severed 为 0、判 `[ OK ]`」**（上面头两行，对应原文第一行样例），以及 **`refused` 到达 8–11**（0.0001/0.005 配置下实测 `r10s3`、`r11s4`、`r11s7`、`r8s10`）。

**这一条的真正缺陷不是夸大，是不可复算**：写入节奏没写进文档，任何人照原文重跑都会落在某个我上表里的失效区，然后得出「命中率远低于 2/3」的错误结论。建议在原文补一行参数（例如「40 条连接、每条间隔 0.2 ms、信号在爆发开始后 5 ms」）。

## 3. 分级的实际效果：成立

两侧都在真实进程上拿到了实测行，见上一节与第 1 节：`severed = 0` 而 `refused > 0` 一律 `[ OK ]`；只要 `severed ≥ 1` 一律 `[FAIL]`。排序也和 `report_shutdown` 的 docstring 一致（asked → refused → severed）。

确定性佐证在第 6 条的变异 M3：把 `severed_connections` 从 incidents 挪到良性组，`test_a_severed_connection_is_the_one_drain_cost_that_counts_as_a_failure` 报 `assert ['ok'] == ['fail']`——**收尾行的文字一个字都没变，变的只有判定**，这正是第三轮评审 F-2 补上 `_statuses()` 的价值所在。

## 4. 「窗口约一次事件循环迭代宽」：成立，而且可以说得更死

我给 `StandaloneServer.receive_signal` 与 `UvicornListenerAdapter.stop_admitting` 打了时间戳与 tick 戳（tick 由一个 `while True: await asyncio.sleep(0)` 的后台任务累加，每次 `sleep(0)` 恰好让出一次迭代）。

```
{"seconds": 0.00040, "iterations": 1.0, "severed": 1, "refused": 0}
{"seconds": 0.00159, "iterations": 1.0, "severed": 7, "refused": 2}
{"seconds": 0.00034, "iterations": 1.0, "severed": 1, "refused": 1}
{"seconds": 0.00111, "iterations": 1.0, "severed": 4, "refused": 3}
{"seconds": 0.00037, "iterations": 1.0, "severed": 1, "refused": 1}
```

**5/5 次恰为 1.0 次迭代**；关掉 ticker 单量墙钟是 0.29–0.96 ms。

源码结构支持这个数：`_await_advance()` 的 `Event.wait()` 由信号回调 `set()` 唤醒，协程恢复排在下一次迭代；此后到 peek 之间——`stop_accepting()` 里 `_close_registrations_locked` 是同步方法、`stop_admitting()` 的 `for` 循环里没有 `await`、两处 `asyncio.Lock` 在无竞争时不让出——**没有任何会让出的挂起点**。所以「一次迭代」不是一个约数，是结构上的确定值（前提是这两把锁无竞争，`both` 模式下的路由器路径未测）。

**一处必须区分的细节，原文合在一起讲了**：一次迭代宽的是**被切断**的窗口（字节到了内核缓冲但选择器回调还没读走）。**被拒绝**的窗口不是同一件事——它装的是「字节已被读走、请求任务已创建，但任务还没跑到 `gated_app`」的那些。这就是为什么表格里 `refused` 与 `severed` 此消彼长：同一批字节，被读走的进前者，没被读走的进后者。

## 5. 对第三轮评审 F-1 的更正：部分成立，两半都要收窄

原文写：评审判定的「恒为 0」是**单客户端条件下**的结论，并发负载下**稳定非零**。

### 前半：「单客户端下恒为 0」——被我证伪

第 1 节已给出：单条池化连接、gap = 0，23 次运行里 **3 次 `refused = 1`**。所以在单客户端条件下它也不是恒为 0，只是概率低（约 13%，且只出现在 gap ≈ 0 这一格）。

这不推翻 F-1 的机制分析（连接被关掉之后到达的字节确实不经过闸），也不推翻 F-1 的实测（5 组真实进程 + 6 组在制进程全为 0）——评审扫的 gap 集合是 {0.0, 0.0, 0.005, 0.05, 0.3}，只有两格在 gap = 0，13% 的概率下两格全落空完全正常。**F-1 的结论应写成「单客户端下极少非零」，而不是「恒为 0」；原文的更正把「恒为 0」保留给了单客户端，等于把一个概率性事件写成了确定性事实。**

### 后半：「并发负载下稳定非零」——不支持

看第 2 节的表：stagger = 0.001 / pre = 0.02 这一组 **15 次运行 `refused` 全部为 0**，而同一组 `severed` 有 14 次非零；stagger = 0.0005 / pre = 0.01 三次也全 0；0.002 / 0.04 与 0.005 / 0.1 同样全 0。也就是说，在「有并发、也确实切断了连接」的条件下，`refused` 照样可以稳定为 0。

`refused` 非零需要的是**足够密集**的爆发（0.1–0.3 ms 级错峰），让一批请求任务在 `stop_admitting()` 置拒绝态的那一刻正好排在 `gated_app` 之前。这不是「并发负载」这个条件能概括的。

**正确的收窄措辞**：「`refused_requests` 在关停路径上是概率性非零的：单条空闲池化连接下约 13%（且只在信号与写入几乎同时的那一格），密集并发写入下经常达到个位数到十几；它为 0 不等于没有客户端受影响。」

**这一半的错法值得单独记一笔**：原文纠正评审「把概率当成恒定」时，自己在另一个方向上犯了同一个错——用三次采样里的 11 / 8 / 9 支撑「稳定非零」。三次同向的采样支撑不了「稳定」，正如评审的 11 组同向支撑不了「恒为」。**这条处置不改变把它移出 incidents 的裁决**（503 仍然是温和的那一端），只改变文档里能对它说什么。

## 6. 变异分辨力：成立，逐字对得上

三个变异逐个打在私有副本上，**每次跑全量**，跑完 `git checkout -- <file>` 还原并 `rg MUTATION` 确认无残留（末尾 `git status` 为空）。

| 变异 | 打法 | 实测红名单 | 与声称 |
|---|---|---|---|
| M1 探针恒 True | `_closing_would_sever` 开头 `return True` | `test_a_connection_closed_over_an_unread_request_is_counted_as_severed` → `AssertionError: assert 2 == 1`；`test_an_ordinary_idle_connection_is_not_counted_as_severed` → `assert 1 == 0`。**2 failed / 1461 passed / 3 skipped** | 逐字一致 |
| M2 探针恒 False | 开头 `return False` | `test_a_connection_closed_over_an_unread_request_is_counted_as_severed` → `assert 0 == 1`。**1 failed / 1462 passed / 3 skipped** | 逐字一致 |
| M3 severed 不进 incidents | `cli.report_shutdown` 里改 `incidents.append` 为 `reported.append` | `test_a_severed_connection_is_the_one_drain_cost_that_counts_as_a_failure` → `assert ['ok'] == ['fail']`。**1 failed / 1462 passed / 3 skipped** | 逐字一致 |

三次全量都确认**红名单之外没有任何附带红**，即这三条测试的分辨力是各自独立、互不掩护的。声称成立。

## 附一：`89002eb` 在干净 checkout 上的全量数字

**干净 checkout：`1463 passed / 3 skipped`，共收集 1466 条。**

原文「1464 是在脏树上量的、因此不可复现」这个归因**不成立**。差额来自一条 skipif：

```python
SPEC_PATH = Path(__file__).resolve().parents[2] / "docs/.human-controlled/config.example.yaml"

@pytest.mark.skipif(not SPEC_PATH.is_file(), reason="authoritative config spec not present")
def test_authoritative_example_config_parses() -> None:
```

`docs/.human-controlled/` 在主工作树里是**未跟踪**目录（用户亲笔文档），所以 clone 里没有它，那条测试就 skip 掉。把主工作树的 `config.example.yaml` 单独复制进副本再跑，得到 **`1464 passed / 2 skipped`——与原文报的数字精确相同**（随后已删掉该文件，副本恢复为纯 checkout）。

也就是说：1464 **完全可复现**，它不是被并行会话的在飞改动污染的产物；它只是依赖一个不在版本控制里的输入。原文那段警告的意图是对的（脏树基线害人），但**用错了对象**，而且代价不小：它会让下一个人以为这个数字不可信、从而放弃对账，而真正该记录的是「这个套件的通过数依赖 `docs/.human-controlled/config.example.yaml` 是否在场」。

建议原文改成：**干净 checkout = 1463 / 3；补上未跟踪的 `docs/.human-controlled/config.example.yaml` = 1464 / 2。**

## 附二：正样本测试的连跑稳定性（含负载）

跑的是 `tests/integration/test_standalone_lifecycle.py -k severed`（正负样本各一条），每次独立起 pytest 进程。机器 16 核。

| 条件 | 结果 | 期间 load average |
|---|---|---|
| 空闲 | **20 / 20 全绿** | ~4 |
| 16 个 CPU 占满进程 | **20 / 20 全绿** | 12 → 19 |
| 32 个 CPU 占满进程 + 并发跑一遍全量 | **20 / 20 全绿** | 22 → 40 |

**合计 60 / 60。** 原文「连跑 10 次全绿」的声称成立，且我把它扩展到了负载条件——在 load average 40（16 核）下依然确定性通过。原文给的时序理由（asyncio transport 缓冲为空时当场同步 send；唤醒 `serve()` 的回调排在 socket 可读回调之前入队）与第 4 节量到的「窗口恰为 1 次迭代」互相印证：这条测试不靠抢时间赢，它靠的是回调入队顺序，所以 CPU 竞争压不垮它。

实验结束后已用 `pkill --full 'x = \(x \* 31 \+ 7\)'` 精确终止我自己启动的 32 个占用进程（模式来自我自己写的那行源码，唯一匹配），确认 0 残留。

## 需要原文修订的三处（按我的优先级）

1. **附一的全量数字归因**：把「1464 不可复现」改成「1464 依赖未跟踪的 `docs/.human-controlled/config.example.yaml`；干净 checkout 是 1463 / 3」。这条最要紧——错误的「不可复现」标签会让下一个人放弃对账。
2. **第 5 条的两半措辞**：`refused_requests` 在两种条件下都是概率性的，「单客户端恒为 0」与「并发下稳定非零」都要换成带数量级的概率表述。裁决（移出 incidents）不变。
3. **第 2 条补参数**：把 40 连接实验的 stagger 与信号时点写进文档，否则整节不可复算。顺带记一句 uvicorn 5 秒 keep-alive 会在慢建池时悄悄缩小连接池。

第 1、3、4、6 条无需修订。第 1 条可选地补半句：gap ≤ 0 时请求「被正常回应**或被答成 503**」。
