# 优雅关闭修复：变异声称的独立复算

日期：2026-08-20。被审对象：commit `1a7353e`，以及 `docs/tmp/260820-graceful-shutdown-admission-deadlock.md`「验证」一节里的四条变异声称。

**结论：四条变异声称全部成立**（红名单、失败形态、具体断言值都对得上），但其中第 2 条**显著低报了红名单规模**。此外本次复算发现三项文档与测试自述层面的问题，与变异声称本身无关，另列于第 4 节。

## 1. 方法与环境

所有变异都在 `/tmp/gsa-audit` 的私有 clone 上做，`git clone /home/xp/src/ghc-api-proxy-py` 后 checkout 到 `1a7353e`。主工作树 `/home/xp/src/ghc-api-proxy-py` 全程只被读取，未做任何源码或测试改动；本报告是我在仓库内创建的唯一文件。副本上每次变异后 `git checkout -- <file>` 还原，收尾时 `git status` 为空、`rg "MUTATION-|EXPLORE-" src/ tests/` 无残留、HEAD 仍是 `1a7353e`。

每条变异都跑**全量** `uv run pytest -q --tb=no -rf --color=no`，因为「其余全绿」这半个声称只有全量才能证。八次全量运行（干净 1 次 + 变异 7 次）收集数一致为 1421（1419 + 2 skipped），说明变异只改行为不改收集面。

竞态相关的判断额外做了隔离重复（每组 10 次单测），因为一次全量里的一次红绿在竞态测试上不构成证据。

## 2. 逐条复算

### 声称 1：`asked_to_close = await self._adapter.stop_admitting()` → `asked_to_close = 0`

**一致。** 实测 `3 failed, 1416 passed, 2 skipped`，红名单与声称逐条相同，失败形态也相同：

| 测试 | 实测失败形态 | 声称 |
|---|---|---|
| `test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open` | `TimeoutError` | TimeoutError ✅ |
| `test_the_drain_lets_go_of_an_idle_pooled_connection` | `AssertionError: assert 0 == 1` | 断言失败 ✅ |
| `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process` | `subprocess.TimeoutExpired ... 15 seconds` | TimeoutExpired ✅ |

第三条是竞态测试，隔离重复 10 次：**10 红 0 绿**。干净代码下同样 10 次：**0 红 10 绿**。这条变异下它的检出是确定性的。

### 声称 2：`stop_admitting()` 顺手 `cancel_requests()`

**成立但计数不完整。** 声称写「三条第一档守卫全红，含既有的 `test_the_first_signal_stops_accepting_but_lets_a_request_finish`」。实测 `8 failed, 1411 passed, 2 skipped`：

```
tests/integration/test_standalone_lifecycle.py::test_the_first_signal_stops_accepting_but_lets_a_request_finish
tests/integration/test_standalone_lifecycle.py::test_a_restart_signal_alone_never_interrupts_the_request
tests/integration/test_standalone_lifecycle.py::test_a_second_signal_actually_interrupts_the_running_request
tests/integration/test_standalone_lifecycle.py::test_the_third_signal_abandons_a_request_that_ignores_interruption
tests/integration/test_standalone_lifecycle.py::test_a_pooled_connection_that_sends_mid_drain_does_not_hold_the_shutdown_open
tests/integration/test_standalone_lifecycle.py::test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting
tests/integration/test_standalone_lifecycle.py::test_rung_one_delivers_a_response_that_had_already_started_streaming
tests/integration/test_standalone_process.py::test_a_half_sent_request_holds_the_drain_until_the_operator_escalates
```

声称点名的那条在内，三条第一档守卫（`the_first_signal` / `pooled_connection_that_sends_mid_drain` / `rung_one_delivers_a_response`）确实全红，所以字面为真。但实际红名单是 8 条，多出的 5 条包括第二、三档的守卫和真实进程测试。差异方向对结论无害（分辨力比声称的更强，不是更弱），可它让读者以为这条变异的爆破半径是 3 条。**建议把数字改成 8，或改写为「至少这三条第一档守卫全红」。**

### 声称 3：只切「已开始写、尚未写完」的响应

变异实现：`stop_admitting()` 里对 `cycle.response_started and not cycle.response_complete` 的连接改调 `connection.transport.close()`，其余仍 `connection.shutdown()`。

**完全一致。** 实测 `1 failed, 1418 passed, 2 skipped`，唯一的红就是 `test_rung_one_delivers_a_response_that_had_already_started_streaming`，且失败细节正是声称的「9 块只到 1 块」：

```
assert delivered.count(b"data: block-") == STREAM_BLOCKS
E   AssertionError: assert 1 == 9
```

这是四条里分辨力最锐的一条：一个真实的、看起来合理的过度关停，只被这一条测试抓住，其余 1418 条全绿。

### 声称 4：`open_admission()` 只 `set()` 不清 `_admission_refusal`

**完全一致。** 实测 `1 failed, 1418 passed, 2 skipped`，唯一的红是 `test_a_resume_after_a_refusal_serves_again_rather_than_answering_503`，响应体也与声称逐字相符：

```
b'HTTP/1.1 503 Service Unavailable\r\n...\r\n{"type": "error", "error": {"type": "overloaded_error", "message": "server is shutting down"}}'
```

## 3. 探索性变异：更贴切的变异能不能穿过这些测试

四条声称之外，我自己设计并实测了三个变异，目标是分别打掉修复的两半、以及直接复活死锁机制。

| 编号 | 变异 | 全量结果 |
|---|---|---|
| E1 | `stop_admitting()` 只置拒绝态，**完全不关连接**（连 `connection.shutdown()` 循环一起删，返回值仍是 `len(connections)`） | **1419 passed，全绿** |
| E2 | `stop_admitting()` 只关连接，**不置拒绝态** | 1 failed：`test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` |
| E3 | `_refuse_admission_locked()` 记下拒绝态但**不 `set()` 事件**（死锁机制原样复活，调用仍在） | 3 failed：`test_partial_arm_failure_rolls_back_all_registrations`、`test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting`、`test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process` |

E1 与 E2 复现了文档「被证伪的两处断言」第 1 条引用的评审半拆实验（「只留放连接 → 1 条红；只留拒绝 → 全绿」），结论一致。

### 发现 A：`test_the_drain_lets_go_of_an_idle_pooled_connection` 对它自己声称的机制零分辨力

这条测试的 docstring 写「A client holding an idle connection is told to go」，行内注释写「The client's own socket is the proof; a count the server kept could be true of a connection it never actually closed」。

实测：**E1 下它 10 次全绿**（隔离重复 10/10 pass）。也就是说，第一档一条连接也不关，它照样通过。两条断言各有各的失效原因：

- `report.connections_asked_to_close == 1` —— 这个数是 `len(connections)`，与是否真的调用过 `shutdown()` 无关，E1 里它依然是 1；
- `await pooled_reader.read() == b""` —— 这行跑在 `await asyncio.wait_for(serving, 5)` **之后**，而 `serving` 完成意味着 `_finalize()` 里的 `shutdown_lifespan()` 已经跑完，那里本来就会 `for connection in ...: connection.shutdown()`。EOF 来自收尾，不来自第一档。

所以这条测试能区分的只有「`stop_admitting` 压根没被调用」（靠计数，即声称 1 的那个 `assert 0 == 1`），不能区分「第一档告知连接关闭」与「收尾时才关」。注释里那句「a count the server kept could be true of a connection it never actually closed」说对了风险，但它提出的替代证据没有躲开同一个陷阱。

要让它真有分辨力，最小改法是把 EOF 的读取移到 `serving` 完成**之前**（收到 SIGTERM 后、`serve()` 返回前），那时 `shutdown_lifespan` 还没跑。

### 发现 B：`test_a_pooled_connection_that_sends_mid_drain...` 的 docstring 归因过窄

docstring 写：「What actually saves it here is the connection being closed, not the refusal — measured, by removing each half in turn.」

实测：**E1（去掉关连接）10/10 绿，E2（去掉拒绝）10/10 绿，只有两半都没有（声称 1 的变异）才红。** 所以「分别去掉两半」这个测量恰恰**不**支持排他性归因——两半各自都足以让它绿。

它对未变异代码的那句事实描述（写第二个请求时连接已经关了、字节落进关闭的 socket）我认为成立：pooled 连接跑完 `/quick` 后 `cycle.response_complete` 为真，`shutdown()` 会直接 `transport.close()`，0.2 秒足够。所以问题只在于把「未变异时走哪条路」写成了「测量证明只有这条路救得了它」。docstring 后半句「a whole-mechanism regression is what it catches」才是实测支持的说法。

### 发现 C：真实进程守卫的检出率是概率性的，且未被记录

`test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process` 的 docstring 说它「is the only assertion in the suite that would notice this deadlock coming back to a real process」。定性上成立：E3 下它确实是唯一变红的真实进程测试。但它是刻意不同步的竞态，检出率随变异而变，隔离重复各 10 次实测：

| 代码状态 | 红 / 10 |
|---|---|
| 干净 `1a7353e` | **0**（无假红） |
| 声称 1 的变异（`stop_admitting` 整体不调用） | **10** |
| E3（拒绝态记下但闸永不开，死锁机制完整复活） | **4** |
| E2（拒绝态被删，连接照关） | **2** |

补一条同样重要的观察：E3 全量里它是红的，单独跑第一次却是绿的——负载会改变竞态走向。所以「跑一次红了」在这条测试上不足以支撑「它守得住」。

这不是「这条测试没价值」，10/10 干净通过说明它不会制造假红，而且它是唯一在真实进程层面对准这个事故的守卫。但它的 docstring 把一条约 40% 命中的守卫写成了唯一防线，读者会据此高估真实进程层的覆盖强度。**建议在 docstring 里写明这是概率性守卫并给出实测数量级**，与项目一贯的「说清判据的效力等级」一致。

### 发现 D：承重的那一半只有一条测试守着

E2 表明，去掉真正修好死锁的那一半（拒绝准入）之后，全量里**只有** `test_a_request_held_at_the_barrier_is_answered_rather_than_left_waiting` 确定性地变红（真实进程那条 2/10，不算确定性守卫）。这条测试直接驱动 adapter、绕过 `serve()`，所以它守的是 `stop_admitting()` 内部契约，不是关停路径的接线；接线由声称 1 的变异所红的那三条守着。两层各有守卫，没有缺口，但承重半边在整个 1421 条里只有一条确定性守卫，值得知道。

### 发现 E：E3 顺带打红了一条不相关的既有测试

`test_partial_arm_failure_rolls_back_all_registrations` 在 E3 下变红。它走的是 `_arm_locked()` 失败路径里的 `_refuse_admission_locked("listener failed to start accepting")`，同样依赖「置拒绝态时必须开闸」。这说明这条不变量在 arm 失败路径上也有守卫，是个正面信息，只是与本次修复的叙事无关。

## 4. 其余事实性陈述的核查

### 4.1 「全量：1424 passed / 2 skipped」——在 `1a7353e` 上不可复现

在 `/tmp` 干净副本、`1a7353e`、`uv run pytest -q` 实测：**1419 passed, 2 skipped, 66.65s**。八次全量运行收集数恒为 1421，判据强度：足以据此行动。

差额来自并行会话的在飞改动。文档自己也提到当时工作树里 `tests/http/test_pipeline_app.py` 有其他会话的编辑。静态对照现在主工作树与 `1a7353e` 的测试函数数：

| 文件 | 主工作树 | `1a7353e` |
|---|---|---|
| `tests/http/test_pipeline_app.py` | 64 | 58 |
| `tests/unit/test_stream_delivery.py` | 25 | 23 |
| `tests/unit/test_rejection_capture.py` | 4 | 0（未入库） |

方向一致（脏树多出十余条），但数目对不上 1424，因为并行会话此后又动过这些文件。可以确定的是：**1424 这个数是在带别人在飞改动的脏树上量的，不是 `1a7353e` 的数**。建议改成 1419 / 2 并注明是在干净 checkout 上量的——一个不可复现的全量数字，下次有人拿它当基线对比会得出错误结论。

### 4.2 「Ruff `check` 与 Pyright 在全部改动文件上干净」——属实

在副本上对本次提交改动的 8 个文件跑 `uv run ruff check` 与 `uv run pyright`：`All checks passed!` / `0 errors, 0 warnings, 0 informations`。

### 4.3 「影响面」一节关于 `--fd` systemd 路径——属实

文档称：`--fd` 继承监听器的 systemd 路径走 `cli.serve_inherited()`，直接用 `uvicorn.Server.serve()`，从不安装这道闸，因此不受此缺陷影响，也不被本次修复改变。三个子命题逐一核过：

- **走的是 `cli.serve_inherited()`**：`src/app/cli.py:296` 在 `fd` 分支里 `run(partial(serve_inherited, proxy_config, fd))` 后直接 `return`，不进 `run_standalone`。
- **用 uvicorn 自己的 `Server.serve()`、不安装准入闸**：`serve_inherited`（`src/app/cli.py:134-152`）自己构造 `uvicorn.Server(uvicorn.Config(...))` 并 `await server.serve()`，全程不碰 `UvicornListenerAdapter`。而准入闸的安装点 `_install_admission_barrier()` 在整个 `src/` 里只有一个调用点——`UvicornListenerAdapter.startup_lifespan()`（`src/app/lifecycle/adapter.py:110`）。既然这条路径构造不出 adapter，闸就装不上，死锁的载体不存在。
- **不被本次修复改变**：`1a7353e` 对 `cli.py` 的改动全部落在 `report_shutdown()` 函数体内，而 `serve_inherited` 不调用 `report_shutdown`（它连 `ShutdownReport` 都拿不到）。其余改动文件 `lifecycle/{adapter,listener,standalone}.py` 这条路径都不导入。

判据强度：静态但穷尽（调用点是 `rg` 全量枚举的），足以据此行动。限定条件：我没有在运行时实际拉起一次 `--fd` 路径验证，所以这是「代码上不可达」而非「实测未触发」。

### 4.4 无法复算的部分

「复现脚本：修复前挂起并打出与生产同形的 traceback」与「真实 CLI 端到端」两节依赖未入库的一次性脚本和真实上游凭据，我无法复算，本报告对它们不作判断。文档已自陈脚本未入库，这一点是诚实的。

## 5. 结论与建议

**变异声称：成立。** 四条逐条实测，红名单、失败异常类型、具体断言值（`assert 1 == 9`、503 报文原文）全部对得上。没有任何一条是「跑过了、变红了」的空口声称。第 2 条的问题是低报而非虚报：实测红 8 条，声称只点了 3 条。

按重要性排序的建议：

1. **改正全量数字**：1424 → 1419 / 2 skipped，并注明测量位置（干净 checkout @ `1a7353e`）。一个在脏树上量的基线数字最有害的用法就是被下一个人拿去做对比。
2. **修 `test_the_drain_lets_go_of_an_idle_pooled_connection`**：把 EOF 的读取挪到 `serve()` 返回之前。当前它对「第一档放掉空闲连接」零分辨力，而这正是它自称在证的东西（发现 A）。
3. **改写两处 docstring 的归因**：`pooled_connection_that_sends_mid_drain` 的「measured, by removing each half in turn」并不支持排他归因（发现 B）；真实进程竞态守卫应写明它是概率性守卫（发现 C）。
4. 第 2 条变异的红名单数字由 3 改为 8，或改成「至少这三条」。

以上第 2、3 条属于我作为验证者提的建议，是否采纳由你裁决；本报告不修改任何被审代码或测试。
