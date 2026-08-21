# 评审：`_events_with_ping` 去掉 `wait_for(shield(...))` 以消除 `StopAsyncIteration exception in shielded future`

评审对象：当前工作树未提交改动 `src/app/pipeline/delivery/stream.py` + `tests/unit/test_stream_delivery.py`（基线 HEAD `db9aa7d`）。
评审时间：2026-08-20。评审者独立复核，未采信提交者的结论文本，全部判据自行取证。

## 结论

**VERDICT: pass，blocker = 0。** 改动可以按现状提交。

- 根因判定**成立**，而且比提交者陈述的更强：生产日志里的 `coro=<<async_generator_asend without __name__>()>` 是一个**指纹**，全仓只有 `stream.py:44` 的 `asyncio.ensure_future(anext(events))` 能产生这种 repr，其余 shield 调用点包装的都是具名协程或裸 Future，repr 形状不同。所以这条生产日志归因到这一处，不是「合理推断」，是排他性的。
- 语义等价性：6 个情形（含 timeout=None / 0.0 / 已完成 / GeneratorExit / 外部取消 / 普通异常）实测行为一致，**无回归**，无新增忙等。两处可测量差异都对产品无害，见 §2。
- ping 与合成 `message_start` 时序：实测计数一致。唯一边界差异是「超时与 pull 完成撞在同一轮」时新码**少发一个 ping、提前一轮交付事件**；合成帧不会多发也不会丢失，最坏晚一轮，见 §3。
- 回归测试有鉴别力：变异回旧写法后必红，且捕获的正是生产同文；per-test event loop 隔离，无污染；时序上不存在假绿路径，见 §4。
- 同源缺陷：其余 5 个 shield 调用点**都能**以同一机制打印 `<ExcName> exception in shielded future`，但都需要额外前提，且都不会打印生产那条日志的 repr 形状。其中 **`src/app/streaming/sse.py:106` 不在委托清单里，但它是唯一可能打出与生产**完全相同文本**的第二个来源**，见 §5。
- 一个**非回归**的残留：消费者中途关闭生成器（客户端断连）时，新码把噪声从 `StopAsyncIteration exception in shielded future` 换成了 `Task exception was never retrieved`。旧码在同一场景下同样有噪声，数量没变差，所以不是本改动引入的缺陷；但「这条链路不再往 stderr 写东西」这个目标只完成了主路径那一半。见 §6。

术语约定：下文「OLD」指 `yield await asyncio.wait_for(asyncio.shield(task), timeout=timeout)`，「NEW」指当前工作树的 `await asyncio.wait({task}, timeout=timeout)` + `if task.done(): yield task.result(); break`。

---

## 1. 根因判定：成立，机制描述需要补一句时机

### 1.1 CPython 源码事实

本机解释器 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python3` → `3.14.2 (main, Jan 14 2026, 19:38:07) [Clang 21.1.4]`，标准库位于 `/home/xp/.local/share/uv/python/cpython-3.14.2-linux-x86_64-gnu/lib/python3.14/asyncio/tasks.py`。

- `tasks.py:911-928` `_log_on_exception(fut)`：模块级函数。`fut.cancelled()` 直接返回；`fut.exception()` 为 `None` 直接返回；否则组装 `{'message': f'{exc.__class__.__name__} exception in shielded future', ...}` 调 `fut._loop.call_exception_handler(context)`。
- `tasks.py:930-1000` `shield(arg)`：`inner = ensure_future(arg)`；`inner` 已完成则**走捷径直接返回 inner**（不建 outer、不挂任何回调）；否则建 `outer`，并在 `inner` 上挂 `_clear_awaited_by_callback`（每次调用新建的闭包）与 `_inner_done_callback`（同样是每次新建的闭包），在 `outer` 上挂 `_outer_done_callback`。
- `tasks.py:991-996` `_outer_done_callback(outer)`：**只在 outer 完成（本例中是被 `wait_for` 超时取消）时触发**，且带 `if not inner.done():` 前置判断。其中确有一次 `inner.remove_done_callback(_log_on_exception)`（995 行），但紧跟着 996 行又 `add_done_callback(_log_on_exception)`——注释写得很直白：`# Keep only one callback to log on cancel`。

### 1.2 「后续 `shield()` 不会摘掉那个 `_log_on_exception`」——对，但要说清时机

精确表述应为三句：

1. `shield()` **本身**从不摘除 `_log_on_exception`。它只做「建 outer + 挂 3 个回调」，其中两个是新建闭包，因此后续每次 shield 只会**新增**观察者，不动已有的。
2. 995 行那次 `remove_done_callback(_log_on_exception)` 发生在 `_outer_done_callback` 内，即**某个 outer 完成的时刻**，作用对象是 inner 上已有的同名回调；因为 `remove_done_callback` 按对象相等移除、而 `_log_on_exception` 是模块级函数（所有 shield 共享同一对象），这次移除会把**之前所有轮次**留下的那份一并摘掉，随即在 996 行原样加回一份。所以它是**去重**，不是清理：净效果永远是「恰好一份，且永不为零」。
3. 因此残留份数与超时次数无关，恒为 1；提交者「每个 task 上只残留一份，与超时次数无关」的观察正确。

实测（`/tmp/rev-shield/e1_residue.py`，直接窥探 `task._callbacks`）：

```
after ensure_future: []
after timeout 0: ['_clear_awaited_by_callback', '_log_on_exception']
after timeout 1: ['_clear_awaited_by_callback', '_clear_awaited_by_callback', '_log_on_exception']
after timeout 2: ['_clear_awaited_by_callback', '_clear_awaited_by_callback', '_clear_awaited_by_callback', '_log_on_exception']
caught StopAsyncIteration from wait_for
handler messages: ['StopAsyncIteration exception in shielded future']
```

三次超时 → `_log_on_exception` 恒为 1 份 → pull 以 `StopAsyncIteration` 收尾时恰好 1 条日志。**顺带暴露一个旧码的次要问题**：`_clear_awaited_by_callback` 是每轮新建的闭包、且 `_outer_done_callback` 不去重它，所以它随 keep-alive 次数**线性累积**在 pull task 上（一次 keep-alive 一个闭包）。NEW 下无任何累积（`/tmp/rev-shield/e8_callbacks.py`：连续 4 次 `asyncio.wait` 后 `task._callbacks` 始终为 `[]`，因为 `_wait` 在 `finally` 里 `remove_done_callback(_on_completion)`，`tasks.py:520-527`）。这是本改动一个未被声明的附带收益。

### 1.3 归因的排他性证据（比提交者给的更强）

生产日志第二行是：

```
future: <Task finished name='Task-2443' coro=<<async_generator_asend without __name__>()> exception=StopAsyncIteration()>
```

`coro=<<async_generator_asend without __name__>()>` 只在把 **async generator 的 `anext(...)` 对象**直接交给 `ensure_future/create_task` 时才会出现；包装具名协程（`create_task(pull_chunk())`）时 repr 是 `coro=<...pull_chunk() done, defined at ...>`。实测对照（`/tmp/rev-shield/e7_sites.py`）：

```
A stream.py shape (anext): ('StopAsyncIteration exception in shielded future', "<Task finished name='Task-2' coro=<<async_generator_asend without __name__>()> exception=StopAsyncIteration()>")
B named-coroutine shape:   ('StopAsyncIteration exception in shielded future', "<Task finished name='Task-4' coro=<named_coro() done, defined at /tmp/rev-shield/e7_sites.py:4> exception=StopAsyncIteration()>")
```

而 `rg -n "create_task\(anext|ensure_future\(anext" src/` 全仓只有一处命中：`src/app/pipeline/delivery/stream.py:44`。所以生产那条日志只能来自这里。

在旧码上跑真实模块，也直接复现了同款输出（`/tmp/rev-shield/e5_pings.py` 在变异窗口内运行）：

```
StopAsyncIteration exception in shielded future
future: <Task finished name='Task-2' coro=<<async_generator_asend without __name__>()> exception=StopAsyncIteration()>
```

**权重：足以据此行动。** 判据是源码 + 可复现的一手实验 + 唯一性 grep，不是推断。

---

## 2. 语义等价性：6 情形一致，无回归，无新增忙等

原语级对照实验 `/tmp/rev-shield/e2_matrix.py`（同一脚本内跑 OLD 与 NEW 两个 `step` 实现，任务与时序完全相同）：

| 情形 | OLD | NEW | 判定 |
|---|---|---|---|
| (a) `timeout=None`，task 稍后完成 | `('done','value')` | `('done','value')` | 一致 |
| (b) `timeout=0.0`，task 挂起中 | `('timeout',None)`，task 存活未取消 | 同左 | 一致（关键：**都不取消 task**） |
| (b') 紧接着再等 | `('done','value')` | `('done','value')` | 一致 |
| (c) 进入等待时 task 已完成 | `('done','value')`，期间 0 次 loop tick | `('done','value')`，期间 2 次 loop tick | **有差异，见下** |
| (e) 等待中 task 被外部取消 | 抛 `CancelledError` | 抛 `CancelledError` | 一致 |
| (f) task 抛普通异常 | 抛 `ValueError(boom)` | 抛 `ValueError(boom)` | 一致 |
| (f2) 先超时一次、随后抛 `StopAsyncIteration` | 抛 `StopAsyncIteration`，**并留下 1 条 handler 日志** | 抛 `StopAsyncIteration`，handler 日志为空 | 缺陷消除 |

**(c) 的差异**：`asyncio.wait` 对已完成的 future 也要走 `add_done_callback` → `call_soon` → 唤醒 waiter，因此比 OLD（`shield` 对已完成 inner 走捷径直接返回，`await` 一个已完成 Future 不让出）多花约 2 个事件循环轮次。这是**调度延迟**，不是等待、不是自旋，且只发生在「上一轮 `yield None` 挂起期间 pull 恰好完成」这一种进入姿态。对块级交付无可观察影响。**权重：仅作记录，不构成行动依据。**

**(d) GeneratorExit / 消费者关闭**：`/tmp/rev-shield/e3_generator.py::probe_close_midwait` 用真实 `_events_with_ping` 验证——消费者任务被 cancel 再 `agen.aclose()` 后，上游 feed **没有**收到取消（`feed_cancelled=False`）。即 NEW 保持了与 shield 相同的「不把消费者的取消传导给 pull」语义。机制上也清楚：`_wait` 挂起在自己创建的 `waiter` 上（`tasks.py:490-527`），取消只落在 `waiter`，`finally` 里摘掉 `_on_completion` 后 `fs` 里的 task 毫发无损。

**忙等/自旋检查**：新码的等待时长完全由 `timeout` 决定，而 `timeout` 在 `stream.py:58-62` 有 `max(0.0, min(pending_deadlines) - loop.time())` 钳制，且 `ping_deadline` 每次触发后前推一个 `interval`（`stream.py:68-69`），所以 ping 路径不可能出现 0 超时连转。唯一能让 `timeout` 恒为 0.0 的姿态是「`response_headers_deadline` 已过而 `response_started` 一直未被 set」——实测该姿态下 OLD 约 6.1k 次/秒、NEW 约 79k 次/秒（`/tmp/rev-shield/e5_pings.py` 的 S3；NEW 更快是因为 OLD 的 `wait_for` 在 `timeout<=0` 时走 `_cancel_and_wait` 分支，本身更重）。**但这条路在产品里不可达**：`_events_with_ping` 的唯一调用方是 `stream_delivery`，而它在 `stream.py:108-119` 收到第一个 `None` 且发现 deadline 已过时立即 `response_started.set()`——产生 `None` 的条件与 set 的条件是同一个判断，所以最多空转一轮。两边同样如此，不是回归。**权重：仅作记录**；若将来有第二个调用方且它不 set 这个 Event，NEW 的自旋会比 OLD 更烧 CPU，那时才需要在 `_events_with_ping` 内部兜底。

---

## 3. ping 与合成 `message_start` 的时序：计数一致，边界只会「少一个、晚一轮」

用真实 `_events_with_ping` 在 OLD/NEW 两个版本下跑同一组场景（`/tmp/rev-shield/e5_pings.py`，NEW 在还原后跑、OLD 在变异窗口内跑）：

| 场景 | OLD | NEW |
|---|---|---|
| S1：静默 2.5s 后流结束，interval=1 | `yields=[None, None]` | `yields=[None, None]` |
| S2：1.5s 时一个事件、3.0s 结束，interval=1 | `[None, SseEvent, None]` | `[None, SseEvent, None]` |

`stream_delivery` 端（`/tmp/rev-shield/e3_generator.py::probe_ping_timing`，`interval=1` + `synthesized_response_headers_after_sec=1` + 每 0.45s 一帧）两版本输出同为 `events=['message_start','content_block_start','content_block_delta','content_block_stop','message_delta','message_stop']`，`pings=0`——合成帧恰好一个，不多不少。

**平局（`asyncio.wait` 超时返回但 task 恰在同一轮完成）确实存在可观察差异**，我把它构造成确定性实验（`/tmp/rev-shield/e4_boundary.py`：让 pull 的完成定时器与等待超时同刻到期，分「完成定时器先入堆」与「后入堆」两种顺序，各 5 次）：

```
OLD before [('timeout',None) ×5]      OLD after [('timeout',None) ×5]
NEW before [('done','v')   ×5]      NEW after [('timeout',None) ×5]
```

即定时器先入堆时，OLD 判超时（随后下一轮才取到结果），NEW 直接判 done。落到产品语义上：

- **ping**：平局那一轮 NEW 少发一个 `PING_FRAME`，同时把真实事件早一轮交给消费者。keep-alive 是 SSE 注释、无内容语义，真实事件已经到达时省掉它无害。**不是回归。**
- **合成 `message_start`**：不会多发（`response_started` 是幂等 Event，`stream.py:110` 有 `not response_started.is_set()` 前置），也不会丢失。若平局那一轮把事件交付了而该事件没凑成完整块，`response_started` 仍未 set、deadline 仍已过，于是下一轮 `timeout` 被钳到 0.0、立刻产生 `None`，合成在**下一轮**发生。最坏后果是延后一个事件循环轮次。
- 反方向（NEW 多发一个 ping / 多合成一帧）在机制上不存在：NEW 只在 `task.done()` 为假时才走 `yield None`，而 `_wait` 只有超时与 task 完成两种返回原因，`not task.done()` 严格蕴含「超时」。

**权重：足以据此行动**（源码路径闭合 + 确定性实验）。

---

## 4. 回归测试的鉴别力：真红，不假绿，不污染

**变异实验**（第 4 项授权的临时变异，已还原并自证，见 §7）。把 `stream.py:64-70` 改回 OLD 的 `try/except TimeoutError` 写法后：

```
$ uv run pytest tests/unit/test_stream_delivery.py -q
E       AssertionError: assert ['StopAsyncIt...elded future'] == []
E         Left contains one more item: 'StopAsyncIteration exception in shielded future'
FAILED tests/unit/test_stream_delivery.py::test_a_keep_alive_wait_leaves_no_asyncio_noise
1 failed, 19 passed in 10.42s
```

单跑同样红（`1 failed in 1.45s`），所以不依赖同文件其它用例的执行顺序。捕获到的字符串与生产日志第一行**逐字相同**，不是某个近似信号。还原后同文件 `20 passed in 10.38s`，单测重复 3 次全绿、耗时稳定在 1.39–1.40s。

**假绿风险逐条排除**：

- *时序不足以触发 keep-alive*？不成立。`collect([], interval=1, initial_delay=1.2)`：ping deadline 在 `_events_with_ping` 起点 +1.0s，feed 的 `asyncio.sleep(1.2)` 只会**晚于**而不会早于 1.2s 返回（`asyncio.sleep` 不提前返回），所以「pull 活过一次 keep-alive」是确定性的，机器负载只会拉大余量。
- *handler 装得太晚、日志已经先打出去*？不成立。handler 在 `collect(...)` 之前安装、`finally` 里恢复，而 `_log_on_exception` 是在 pull 完成的那批 `call_soon` 里同步调用 `call_exception_handler` 的，必然落在窗口内——变异实验已经实证它被捕获。末尾那句 `await asyncio.sleep(0)` 是余量，不是必需。
- *恢复 handler 时序不当，污染同 loop 的其它用例*？不成立。`pytest-asyncio 1.4.0`、`asyncio_mode=auto`，未配置 `asyncio_default_test_loop_scope`，实测每个 async 用例拿到不同的 loop 对象（`/tmp/rev-shield/test_loopid.py`：`LOOPID one 133458277178336` vs `LOOPID two 133458052549520`）。而 `Future.__del__` / `_log_on_exception` 调的是 `fut._loop.call_exception_handler`，即**任务自己那个 loop** 的 handler；跨用例的遗留任务属于已关闭的旧 loop，落不进本用例的 `reported`。反向也一样，本用例装的 handler 在 `finally` 里被还原，不会外溢。
- *断言过宽导致将来误红*？`assert reported == []` 会捕获该窗口内**任何** loop 级异常上报，不止本缺陷。这是有意的宽度：它把「这段交付路径不许往 stderr 扔东西」整体钉住。代价是将来若有人在这条路径上引入别的 loop 级噪声，红的会是这个用例——那正是应该红。**不视为缺陷。**

一个观察：`test_silence_before_the_first_block_produces_no_keep_alive`（`tests/unit/test_stream_delivery.py:236`）在旧码下**本来就会**打出这条噪声，只是没人断言它。这解释了为什么 1342 个测试全绿而生产在刷屏——噪声一直在测试输出里，只是没有断言把它变成失败。新用例补上的就是这个断言面。

---

## 5. 同源缺陷：5 处都能击发，前提各不相同；**清单漏了 `sse.py:106`**

判定规则（由 `tasks.py:911-928` + `991-996` 推出，并由 `/tmp/rev-shield/e7_sites.py` 三种形状实证）：**当且仅当** ①某个 `shield(x)` 的 outer 在 `x` 未完成时被取消（awaiter 被取消，或 `wait_for` 超时），**且** ②`x` 最终以**异常**收尾（`x.cancelled()` 为真则 `_log_on_exception` 直接返回，实测对照组 D 无日志），才会打印 `<ExcName> exception in shielded future`。日志一个 task 最多一条。全仓 `rg -n "asyncio\.shield"` 命中 6 处（含已修的 `stream.py`）。

| 位置 | 会否击发 | 前提与依据 |
|---|---|---|
| **`src/app/streaming/sse.py:106`**（**不在委托清单内**） | **会**，且是唯一能打出与生产**同一条文本**的第二来源 | `pending = create_task(pull_chunk())`，`pull_chunk` 就是 `anext(body_iterator)`，正常结束即 `StopAsyncIteration`。前提：awaiter 在 pull 在途时被取消（客户端断连 / task group 取消），此时 outer 被取消 → 装上观察者；随后 `finally` 走 `finish_stream_cleanup` → `_cancel_and_observe` 才 `pending.cancel()`，而那是**另一个 task**（`keepalive.py:92` `create_task(cleanup())`），至少晚一个事件循环轮次。若 pull 在这个窗口内自己以 `StopAsyncIteration` 完成（断连与上游流末尾撞在一起），观察者先于 cancel 击发 → 打印 `StopAsyncIteration exception in shielded future`。repr 会是 `coro=<...pull_chunk() ...>`，与生产日志的 `async_generator_asend` 不同，所以**它不是本次生产噪声的来源**，但它是同一缺陷的活体。概率低（要求断连与流末尾同轮），不影响正确性。 |
| `src/app/streaming/keepalive.py:99` | **会** | `while not cleanup_task.done(): await asyncio.shield(cleanup_task)`，`except asyncio.CancelledError` 后继续循环——即被取消时正好装上观察者。前提：①清理期间外层至少被取消一次；②`cleanup()`（`keepalive.py:77-90`）最终**抛异常**（pull 的错误或 `_close_iterator` 失败）。两者同时成立时打印 `<ExcName> exception in shielded future`。之后的 `cleanup_task.result()`（`keepalive.py:112`）虽然取走了异常，但观察者在完成瞬间已经击发，取走不能撤销。不影响正确性，只是一条多余日志。 |
| `src/app/lifecycle/standalone.py:237` | **会** | `wait_for(shield(cleanup), self._cleanup_timeout or None)`，`except TimeoutError` 后仍 `await cleanup`（`standalone.py:241-244`）。前提：①`_cleanup_timeout` 已配置且被超出；②`shutdown_lifespan` 随后以异常收尾。此时 `cleanup.exception()`（`standalone.py:248`）已经在 `CleanupOutcome.error` 里正常上报，`_log_on_exception` 会再向 stderr 打一条形如 `RuntimeError exception in shielded future` 的重复噪声。若超时未发生，`except Exception: pass` 那条路不建立观察者，不击发。 |
| `src/app/history/sqlite/writer.py:94` | **会** | `await asyncio.shield(acknowledgement)`，ack 是裸 Future，`_complete_ack` 在写入失败时会 `set_exception(error)`（`writer.py:288`）。前提：①`submit()` 的调用方在 ack 未落定时被取消；②该条写入随后失败。实测裸 Future 形状同样击发（e7 的 C 组：`RuntimeError exception in shielded future`）。 |
| `src/app/history/sqlite/writer.py:255` | **会** | `await asyncio.shield(task)`，`task = _close_impl()`，后者在 fatal 状态下 `raise RuntimeError(...)`（`writer.py:274`）。前提：①某个 `close()` 调用方被取消；②`_close_impl` 以异常结束。多个并发 `close()` 共用同一 task，任一被取消即装上观察者。 |
| `src/app/pipeline/delivery/stream.py` | 已修 | 本次改动移除 |

**共同点**：五处都只在「取消 + 异常」双前提下击发，都最多一条，都不改变控制流或返回值，异常本身在各处都另有正规上报路径。因此**都不是 blocker，也都不必随本改动一起修**。若要收口，最小手段是把 `shield` 换成同样的 `asyncio.wait({fut}, ...)` + 显式取结果（keepalive/standalone/writer 三处形状都允许），但那是独立的一次改动，需要各自的回归证据。**本次评审未修改这些文件。**

---

## 6. 一个非回归的残留：放弃生成器时的噪声换了个名字

`/tmp/rev-shield/e6_abandon.py`（真实 `_events_with_ping`：消费者 cancel + `agen.aclose()`，随后等到上游 pull 自己结束）：

| 场景 | OLD | NEW |
|---|---|---|
| 关闭前已发生过 keep-alive | `StopAsyncIteration exception in shielded future` | `Task exception was never retrieved` |
| 关闭前未发生 keep-alive | `StopAsyncIteration exception in shielded future` | `Task exception was never retrieved` |

机制：生成器的 `finally`（`stream.py:73-75`）只在 `task.done()` 时取异常，而放弃发生时 pull 还在途，于是没人取；pull 之后以 `StopAsyncIteration` 结束，GC 时由 `Future.__del__` 报 `Task exception was never retrieved`。旧码之所以不报这一条，恰恰是因为 `_log_on_exception` 顺手 `fut.exception()` 把异常「取走」了——它一边制造噪声一边压掉了另一条噪声。

**判定：不是本改动引入的回归**（每个测得的场景里 NEW 的噪声条数 ≤ OLD），但目标「这条链路不再往 stderr 写东西」只完成了主路径。客户端中途断连在 agent 类客户端上并不罕见，所以这条日后大概率会被再次看到。

**建议（仅建议，本次未实施）**：把 `stream.py:73-75` 的 `finally` 改成对未完成的 pull 挂一个「取结果」回调，或干脆在放弃时 `task.cancel()`（被取消的 task 不会触发任何一种上报）。取消是否安全取决于 `read_events`/上游连接的关闭语义——`stream_delivery` 的 docstring（`stream.py:88-91`）说被放弃时上游响应会保持打开直到循环回收，而现状下那个 pull 确实还活着；这两件事可以一起想清楚。这属于独立议题，请主会话决定是否单开一刀。

---

## 7. 变异窗口的还原自证

第 4 项要求的临时变异只落在 `src/app/pipeline/delivery/stream.py` 一个文件，且已按字节还原：

```
$ sha256sum src/app/pipeline/delivery/stream.py
760e170a0c909dae5f9923d193342f00a0f647a985fa6427b48a32042b858893   # 与变异前记录的哈希一致
$ diff <变异前的 git diff> <还原后的 git diff>
IDENTICAL
```

还原方式是从 `/tmp/rev-shield/stream.py.orig` 直接 `cp` 回去，未使用 `git checkout`、`git stash`、`git add`、`git commit`。其余 `src/`、`tests/`、`docs/`（本报告除外）文件一律未碰。

**需要提醒**：评审期间工作树在被并行会话改动——`git status` 在评审开始与结束时不同（`src/app/pipeline/anthropic_request_hook.py`、`src/app/pipeline/subscribers/__init__.py`、`tests/http/test_pipeline_app.py` 从 modified 列表消失，新增未跟踪的 `src/app/debug/`、`tests/unit/test_debug_models.py`、`tests/cassettes/responses_web_search_*.json`）。本报告的所有结论只针对 `stream.py` + `test_stream_delivery.py` 这两个文件的当前内容（sha256 如上），与并行改动无关。

## 8. 本次复核实际执行的验证

- `uv run pytest tests/unit/test_stream_delivery.py -q` → `20 passed`（还原后）
- 变异态同命令 → `1 failed, 19 passed`，失败者正是新增用例
- `uv run pytest ...::test_a_keep_alive_wait_leaves_no_asyncio_noise -q` ×3 → 全绿，1.39–1.40s
- `uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py` → `All checks passed!`
- `uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py` → `0 errors, 0 warnings, 0 informations`
- 未重跑全量回归：提交者已跑过 `1342 passed, 2 skipped`，且工作树此后被并行会话改动，重跑测的已不是同一棵树，重跑结果无法归因给本改动。

实验脚本全部留在 `/tmp/rev-shield/`（`e1_residue.py` 回调残留、`e2_matrix.py` 语义矩阵、`e3_generator.py` 生成器级探针、`e4_boundary.py` 平局、`e5_pings.py` ping 计数与自旋、`e6_abandon.py` 放弃路径、`e7_sites.py` 各调用点形状、`e8_callbacks.py` 回调累积、`test_loopid.py` loop 隔离），仓库内未留任何临时文件。注意：在 `/tmp` 下直接跑 `uv run` 会选到另一个解释器（实测为 Anaconda 3.13.12），必须在仓库根目录发起并用 `PYTHONPATH=src`。

---

## 补记：修 shield 噪声时考虑并否决的两个替代（2026-08-20 收尾追加）

按 `record-what-not-adopted`，未采纳的方案与理由应当留档。当时口头权衡过、未写进任何文件：

- **保留 `shield`，手工 `task.remove_done_callback(asyncio.tasks._log_on_exception)`。** 否决：依赖 CPython 的**私有名字**，一次实现变更就断；而且它是在**消音**，不是纠正用法——那个观察者之所以被挂上，正是因为我们对 asyncio 声称「这个 task 没人等了」，而实际上下一轮还要等它。
- **`async with asyncio.timeout(...)` 包住 pull。** 否决：超时语义仍然是**取消被等待者**，不满足「超时了也别取消这个 pull」这一硬需求。

采纳的是 `asyncio.wait({task}, timeout=...)`：不建 outer future、超时不取消 task，因而根本不存在兜底观察者，且项目内 `session_liveness_stream` 已是这个形状。
