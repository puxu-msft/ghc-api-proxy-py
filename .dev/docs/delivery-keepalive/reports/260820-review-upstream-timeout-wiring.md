# 独立评审：`upstream_request_timeouts` 接线修复

- 日期：2026-08-20
- 评审者：subagent（只读；未修改 `src/`、`tests/`、`docs/.human-controlled/`，未做任何 git 写操作）
- 被评审快照：`/tmp/rev-tw/snap`（2026-08-20T17:24:33+00:00 从主工作树 `cp -a src tests pyproject.toml uv.lock` 而来）。工作树 HEAD = `16e87a5ea473de25a58c7d329728b2c62eb6bd54`
- 快照关键文件 sha256：

```
15ec267a…  src/app/pipeline/direct_driver/base.py
02553dea…  src/app/streaming/deadline.py
3a0e8647…  src/app/server/pipeline_app.py
f1f90ff1…  src/app/server/handler.py
545859e2…  src/app/pipeline/request.py
013725279… src/app/config/schema.py
e49b8b39…  tests/unit/test_timeout_enforcement.py
```

- 实验产物：`/tmp/rev-tw/probe_nest.py`、`/tmp/rev-tw/probe_delivery.py`、`/tmp/rev-tw/mut/m*.py`、`/tmp/rev-tw/mutate.sh`、`/tmp/rev-tw/probe_keep.py`（探针测试文件的副本，只存在于快照与 `/tmp`，从未写入仓库）

---

## 裁决

**needs-fix。** 机制本身是对的——我逐条实测了嵌套语义、`bound.expired()` 的鉴别力、期限的单一瞬时、以及体阶段击发时的记账与日志，全部与实现声称的一致。问题不在机制，在**这次修复没有被测试锁住的那几处，恰好就是它要修的那一类缺陷**，外加一处未声明的行为回退和一处未上报的语义变更。

- 阻断项（squash 前应处理）：**5**
- 观察项（不阻断，建议记录/上报）：**8**

其中最需要注意的一条：**把 `response_header` 从配置传给 driver 的那一行删掉，1248 条单元 + HTTP 测试里没有一条会红。** 这正是本次修复的立论——「一个从配置读出来、然后没接到任何东西上的守卫，看起来和一个宽松的守卫一模一样」——在上一层原样复现了。

---

## 一、两个 driver 守卫的嵌套（任务点 1）

### 结论：嵌套正确，四种情形都实测过，没有改标

依据 `src/app/pipeline/direct_driver/base.py:239-260`，探针 `/tmp/rev-tw/probe_nest.py` 复刻了 `_send` 的确切形状（把 `provider.send` 换成 `asyncio.sleep`），跑在项目 venv（Python 3.14.2）上。

| 配置 | 实测结果 | 用时 |
|---|---|---|
| header=1, deadline=10 | `UpstreamTimeout: no response headers within 1s` | 1.005s |
| header=10, deadline=1 | `UpstreamTimeout: attempt exceeded 1s` | 1.004s |
| header=30, deadline=2（**矛盾配置**） | `UpstreamTimeout: attempt exceeded 2s` | 2.008s |
| header=0.5, deadline=0.51 / 0.55 / 0.6 | 均为 `no response headers within 0.5s` | 0.50s |
| header=0.51 / 0.55 / 0.6, deadline=0.5 | 均为 `attempt exceeded 0.5s` | 0.50s |
| header=0.5, deadline=0.5（**完全相等**）× 5 次 | 5/5 均为 `attempt exceeded 0.5s` | 0.50s |
| header=0, deadline=1 | `attempt exceeded 1s` | 1.003s |
| header=1, deadline=0 | `no response headers within 1s` | 1.004s |

四条具体回答：

1. **内层抛的 `UpstreamTimeout` 不会被外层 `except TimeoutError` 捕获改标。** 你的依据成立，我核实过：`issubclass(UpstreamTimeout, TimeoutError)` 为 `False`，MRO 是 `UpstreamTimeout → UpstreamError → PipelineError → Exception`（`src/app/pipeline/exceptions.py:43`、`24`、`21`）。实测第 1 行即此路径。
   补充一条你没问但值得知道的：CPython 3.14 的 `asyncio.Timeout.__aexit__` 在自身 EXPIRING 且传播中的异常**不是** `CancelledError` 时，会调用 `_insert_timeout_error(exc_val)` 把一个 `TimeoutError` 插进异常链的 `__context__`，然后 `return None` 让原异常继续传播。所以内外几乎同时到期时，**header 的说法仍然胜出**，只是异常链上多一条 `TimeoutError`。这不影响 `classify()`。
2. **外层先到期时，内层 `asyncio.timeout` 的行为**：内层状态是 ENTERED，`__aexit__` 把它置为 EXITED 并让 `CancelledError` 原样传播；`CancelledError` 不是 `TimeoutError`，所以内层的 `except TimeoutError` 不接，外层照常转成 `attempt exceeded`。实测第 2、3 行。
3. **两者相等时外层（deadline）赢，且是确定性的**：外层的 `deadline_at` 在 `run()` 里 `begin_attempt()` 之后就取好了（`base.py:132`），内层的 `when` 要等到 `_send` 进到 `asyncio.timeout(...)` 才算，绝对时刻必然更晚。5/5 一致。差值小于约 100 µs 时同样归外层——这属于「两个守卫本来就同时到期」，不是错标。
4. **`response_header > attempt_deadline` 的矛盾配置**：外层在 2s 掐断，报 `attempt exceeded 2s`。合理——期限本来就是上限，header 配得再大也越不过去。没有死锁、没有静默、没有把 header 的名字打出来。

两条路径都归到 `classify=retry`、`reason_for=network`（探针同时跑了真的 `classify` 和 `reason_for`）。

---

## 二、「同一个瞬时只算一次」（任务点 2）

### 结论：成立。但**这条不变量在测试里的鉴别力为 0**

**写入方只有一处**：`src/app/pipeline/direct_driver/base.py:130-132`，在 `begin_attempt()` 之后立刻算。
**读取方两处**：`base.py:239-240`（driver 自己）和 `src/app/server/pipeline_app.py:358, 379`（交付链）。
`rg -n 'begin_attempt|current_attempt' src/ tests/` 的全部命中只有这几处，加上 `src/app/server/handler.py:155`（count_tokens 自己开的 attempt，另一条路径，与流式交付无关）。**没有第二处重算。**

「交付链读到 `None` 而 driver 设了值（或反之）」不成立：两侧都走 `context.current_attempt`，唯一的写入者是 driver 的 `run()`，且 `deadline_at` 只在 `self._attempt_deadline > 0` 时写——与交付链 `attempt.deadline_at if attempt is not None else None` 的判定一致。`src/` 里没有任何 subscriber 调 `begin_attempt`，所以 `_send` 里 `current_attempt` 不会指向另一个 attempt。

**端到端实测（`/tmp/rev-tw/probe_keep.py::test_probe_deadline_origin`）**：`upstream_request_deadline=2`，上游先延迟 1.5s 才发响应头、随后无限滴水。

```
P2 header_delay=0.0: ended after 2.01s with StreamDeadlineError
P2 header_delay=1.5: ended after 2.01s with StreamDeadlineError
```

两条都在 2.0s 结束 —— 期限确实是从 attempt 开始那一刻算的，等头花掉的 1.5s 计入其中。**这是对的。**

### 重试时每次 attempt 各自获得新期限——对的

`base.py:129-132` 在 `while True` 里，每次 `begin_attempt()` 之后重算。对照用户注释「**单次**上游尝试的最大存活秒数」（`docs/.human-controlled/config.example.yaml:302`），这就是正确读法。变异 m5（改成只在第一次 attempt 设期限）被 `tests/unit/test_timeout_enforcement.py::test_a_timeout_is_retryable_when_the_budget_allows` 打红，说明这一点是被钉住的。

### 但「只算一次」本身没被钉住 —— 阻断项 B3

变异 **m3**：把 `pipeline_app.py:379` 的 `deadline_at=attempt.deadline_at …` 换成 `anyio.current_time() + config.upstream_request_deadline`（asyncio 后端下 `anyio.current_time()` 就是 `loop.time()`，是精确等价的重算）。

```
MUTATION: m3_recompute
118 passed in 40.85s
```

**全绿。** 也就是说，`Attempt.deadline_at` 这个字段存在的全部理由——注释里写的「a second `now + deadline` here would … quietly grant the attempt a second full lifetime」——目前没有任何测试能证伪它被破坏。

我已经写出了能打红它的测试并验证过分辨力（上面的 `test_probe_deadline_origin`，`header_delay=1.5`）：

```
（m3 变异下）
P2 header_delay=0.0: ended after 2.02s with StreamDeadlineError
P2 header_delay=1.5: ended after 3.52s with StreamDeadlineError   <-- 多出整整一条命
```

建议：把这个形状收进 `tests/http/test_pipeline_app.py`（异步 MockTransport handler + 一个 `header_delay`，断言总墙钟时间上界）。现有的 `test_the_attempt_carries_the_one_deadline_both_halves_read` 只断言 driver **记下**了一个落在窗口里的瞬时，既不能区分「在 `begin_attempt` 算」和「在 `_send` 算」，也不能证明有人**读**它。

---

## 三、`with_deadline_at` 的正确性（任务点 3）

### 结论：全部实测通过

探针 `/tmp/rev-tw/probe_delivery.py`：

| 场景 | 实测 |
|---|---|
| A. 内层 idle=0.3 先到期，外层 deadline=+30 | `StreamIdleTimeoutError: No stream item received for 0.3s`（0.307s），源流已关闭 |
| B. 外层 deadline=+0.3 先到期，内层 idle=30 | `StreamDeadlineError: attempt exceeded its deadline`（0.302s），源流已关闭 |
| C. 逼近（idle 0.30 vs deadline 0.31）× 5 | 5/5 `StreamIdleTimeoutError` |
| D. `deadline_at` 已是过去时刻，源立即就绪 | 立刻 `StreamDeadlineError`（0.000s），一个 item 都没放行，源流已关闭 |
| D2. 同上但源会 await | 同样立刻击发 |
| E. `deadline_at=None` | 完整交付，源流仍被关闭 |
| F. 消费者每拉一次睡 0.2s，deadline=+0.5 | 第 3 个 item 之后在**下一次拉取**时 `StreamDeadlineError`——消费者占用的时间计入，但不打断消费者 |
| G. 消费者拿一个就 `gen.aclose()` | 源流被关闭 |
| H. 消费者任务在拉取途中被 cancel | `CancelledError` 正常传播，源流被关闭 |
| I. 类型关系 | `StreamDeadlineError` 与 `StreamIdleTimeoutError` 都是 `TimeoutError` 子类，互不为对方子类 |

三条具体回答：

1. **`bound.expired()` 判定确实避免了改标。** A/C 两组是直接证据。机制上也说得通：CPython 3.14 `Timeout.expired()` 返回 `self._state in (EXPIRING, EXPIRED)`；内层先到期时外层状态是 ENTERED→EXITED，`expired()` 为 `False`，`raise` 把原异常原样放走。
   **变异 m1**（删掉 `if not bound.expired(): raise`）打红了两条测试：`tests/unit/test_stream_delivery.py::test_the_deadline_does_not_answer_for_the_idle_guard` 和 `tests/http/test_pipeline_app.py::test_an_upstream_that_goes_quiet_past_the_idle_timeout_is_given_up_on`。这条判定**有分辨力**。
2. **cancel scope 没有跨 `yield` 持有。** 变异 m9（把 `bound` 提到 `while` 外、跨 `yield` 持有）导致 `tests/unit/test_stream_delivery.py -k deadline` **挂死**（两次 150s 超时均未返回）。算是被检出，但形式是 hang 而不是干净的红。
3. **被关闭时会关闭源流**（G、H），**`deadline_at` 已过期时立即击发且不放行任何 item**（D、D2）。

### 但嵌套顺序是承重的，而它没被钉住 —— 阻断项 B4

变异 **m7**（把两个守卫的嵌套顺序对调成 idle 在外、deadline 在内）：`118 passed`，**全绿**。

而这个顺序确实承重。直接实测（源发一个字节后静默 60s，deadline=0.3，idle=30）：

```
shipped order  (deadline outer, deadline 0.3 < idle 30) -> StreamDeadlineError: attempt exceeded its deadline
swapped order  (idle outer,     deadline 0.3 < idle 30) -> StreamIdleTimeoutError: No stream item received for 30s
```

对调之后报出的是**一个根本没走完的 30s**。根因：`src/app/streaming/idle_timeout.py:41-45` 用的是 `anyio.fail_after` + 裸 `except TimeoutError`，**没有 `with_deadline_at` 那样的 `expired()` 鉴别**，因此它会把任何嵌在它里面的 `TimeoutError` 改标成自己的，还附上一个假的秒数。

现在的顺序是安全的，`pipeline_app.py:372` 的注释也说明了理由。但：

- 没有测试锁住这个顺序（m7 全绿）；
- `with_idle_timeout` 本身缺少对称的守卫，任何人以后往它里面再嵌一层会静默中招。

建议二选一或都做：给 `with_idle_timeout` 补上同样的鉴别（anyio 用 `cancel_scope.cancelled_caught`），以及/或者加一条「deadline 在外」的顺序测试。

---

## 四、行为变更的影响面（任务点 4）

### 事实

- `src/app/config/bundled-config.yaml` 里**没有** `upstream_request_timeouts` 段（`rg` 零命中），所以生效的是 schema 默认值 `src/app/config/schema.py:147` 的 `1200`，且默认开启。
- 改动前，流式路径上这个值只约束到响应头（前置调查已实测），**从来不会掐断响应体**。改动后它第一次真正掐断。

### 击发时客户端与日志看到什么（实测，`probe_keep.py::test_probe_body_deadline_client_and_log`）

```
P1 upstream requests sent: 1
P1 client exception: StreamDeadlineError attempt exceeded its deadline
P1 log lines: ['H1/H1 200 anthropic-messages/claude-model 1.0s ↑52B ↓366B request_id=…:
               stream failed before a terminal event: attempt exceeded its deadline']
```

控制台上是 `[FAIL] … status=fail`。客户端拿到的是**已经发出的 200 + 一条半截的 SSE 流**，没有 `message_stop`，也没有任何 error 对象——因为响应头早就发走了。不可重试。

### 判断

**这不与用户冻结的不变量冲突，但它的可观测后果没有被记录在任何地方，需要上报。** 理由分开说：

- 用户注释里「bundled defaults 全部禁用此类终止器」那一段挂在 `response_header` 名下（`config.example.yaml:288-294`），而 `upstream_request_deadline` 是用户**单独**写了一段注释、并且**唯一**给了非零默认值的键（`config.example.yaml:302-308`）。所以用户是明确地为这一个键做了例外裁决。以此判断「20 分钟被掐」是用户自己选的，**不是我该替他改的**。
- 但是：20 分钟这个数字是在「它在流式下从来不生效」的世界里定下的。现在它生效了，一次合法的长 thinking turn 只要整次尝试（含 `attempt.prepare` 订阅者、限流等待、发请求、等头、以及**整个响应体的交付**）超过 1200s，就会以「200 之后半截断流」的形式收场。`client_delivery.synthesized_response_headers_after_sec: 240` 说明这套系统预期的 turn 长度是分钟级；1200s 是它的 5 倍，余量算充足，但这是一条**新出现的、默认开启的、不可重试的**失败路径。
- 我的建议（判断，中等强度——机制确定，取舍是用户的）：**不改默认值，把这个键的双重身份写进 `config.example.yaml` 的注释并请用户确认 1200 仍是他要的数**。注释至少要说清：非流式下它是「整次尝试上限 + 可重试」，流式下响应头发出之后它只能「掐断这条流」，客户端已经收到 200、只会看到截断。这一条前置调查报告第四节也提了同样的建议，我独立复核后同意。
- `docs/.human-controlled/` 归用户亲笔，我不动它，也不建议你替他动——把措辞提给他。

---

## 五、重试语义（任务点 5）

### 结论：符合描述，逐条实测

**header 超时在 driver 内 → 可重试。** 探针 `probe_nest.py` 用真的 `classify` 与 `reason_for`：两个守卫抛出的 `UpstreamTimeout` 都得到 `classify=retry`、`reason=network`。

**非流式下期限仍然约束整次尝试且仍可重试**（`probe_keep.py::test_probe_non_streaming_still_bounded`，`upstream_request_deadline=1`，上游体读要 3s）：

```
P4 status: 502 body: {"error":{"type":"PipelineAbort","message":"network budget exhausted: attempt exceeded 1s"}}
P4 upstream requests sent: 10
P4 log lines: ['H1 502 POST /v1/messages claude-model 10.1s request_id=… retries=9: network budget exhausted: attempt exceeded 1s']
```

10 次上游请求 = 1 + `network.max_retries: 9`。这一半的行为没有被改坏。

**体阶段期限在 driver 外 → 不可重试，且记账正确。** P1 实测：`upstream requests sent: 1`，没有第二次尝试。链路核实：

- `StreamDeadlineError` 是 `TimeoutError` → `OSError` → `Exception`，因此被 `src/app/server/pipeline_app.py:536` 的 `except Exception` 接住，`accounting.failure = error`（`:539`），再 `raise`。
- `_StreamAccounting.finish()`（`:428`）→ `delivered_whole = self.drained and self.failure is None` 为 `False` → `_ending()`（`:469`）→ `("fail", f"stream failed before a terminal event: {self.failure}")`。**与实测日志逐字一致。**
- 上游连接释放：`_tracked_delivery` 的 `aclosing(chunks)`（`:531`）关闭整条交付链 → `with_deadline_at` 的 `finally: await close()` → `with_idle_timeout` 的 `finally: await close()` → `response.aiter_bytes()`。另有 `_AccountedStreamingResponse.__call__` 的 `finally: await self._content.aclose()`（`:499`）作为第二道。探针 G/H 直接验证了 `with_deadline_at` 这一层会关源。`idle_timeout.py` 的 docstring 已记录「关 `aiter_bytes()` 不等于关 response，response 靠生成器 finalisation 释放」——那是既有事实，本次改动没有让它变差。

---

## 六、测试质量（任务点 6）

变异全部在 `/tmp/rev-tw/snap` 副本树上做，每次跑完 `rsync` 还原并 `diff -r` 校验（脚本 `/tmp/rev-tw/mutate.sh`，每轮都打印 `RESTORE OK`）。主工作树未被触碰。

### 变异矩阵

| # | 变异 | 结果 | 打红了谁 |
|---|---|---|---|
| m1 | 删掉 `bound.expired()` 鉴别 | **红** | `test_the_deadline_does_not_answer_for_the_idle_guard`、`test_an_upstream_that_goes_quiet_past_the_idle_timeout_is_given_up_on` |
| m2 | 交付链上完全拆掉 `with_deadline_at` | **红** | `test_the_attempt_deadline_reaches_the_streamed_body`（`DID NOT RAISE`，日志显示流跑满并报 `status=ok`） |
| m3 | 在交付链重算期限（等价重算） | **绿（未检出）** | — |
| m4 | 内层 header 守卫改抛裸 `TimeoutError` | **红** | `test_the_header_guard_stops_an_upstream_that_never_answers`、`test_the_two_guards_each_report_themselves` |
| m5 | 期限只在第一次 attempt 设 | **红** | `test_a_timeout_is_retryable_when_the_budget_allows` |
| m6 | handler 里把两个设置对调 | **红** | `test_the_attempt_deadline_reaches_the_streamed_body` |
| m7 | 交付链嵌套顺序对调 | **绿（未检出）** | — |
| m8 | 删掉 `with_deadline_at` 的 `finally: aclose()` | **绿（未检出）** | — |
| m9 | cancel scope 跨 `yield` 持有 | **hang**（150s 未返回，两次） | 检出但不干净 |
| m10 | handler 不再把 `response_header` 传给 driver | **绿（未检出，1247 passed）** | — |

m2 复核了你的实测结论，结果一致。

### 逐条测试的分辨力

**`tests/unit/test_timeout_enforcement.py`**

- `test_the_header_guard_stops_an_upstream_that_never_answers` — 有分辨力（杀 m4）。但它直接构造 driver，**不经过 `handler.py` 的接线**，所以杀不掉 m10。
- `test_the_two_guards_each_report_themselves` — 有分辨力（杀 m4），是两个守卫各自报名字的唯一保障。未覆盖矛盾配置（header > deadline）与相等的情形——我已实测两者行为合理，可以不补，但值得知道它没被钉。
- `test_zero_header_timeout_disables_the_guard` — 弱但正当（`0` 若被当作启用，`asyncio.timeout(0)` 会立刻击发）。
- `test_the_attempt_carries_the_one_deadline_both_halves_read` — **分辨力低于它的命名所暗示的**。断言窗口是 `before + 30 <= deadline_at <= now + 30`；把计算从 `begin_attempt` 挪到 `_send` 里仍然落在这个窗口内，所以「哪一刻算」没被钉；「两侧都读同一个」更是完全没测（读取方是 `pipeline_app.py`，这条测试碰不到它）。名字说了 both halves，实际只测了 driver 那一半。**建议改名或补测**。

**`tests/unit/test_stream_delivery.py`**

- `test_the_deadline_stops_an_upstream_that_trickles_forever` — 有分辨力。
- `test_the_deadline_does_not_answer_for_the_idle_guard` — 高价值，杀 m1。
- `test_no_deadline_leaves_a_slow_stream_alone` — 只钉 `None` 分支，弱但正当。

**`tests/http/test_pipeline_app.py`**

- `test_the_attempt_deadline_reaches_the_streamed_body` — 高价值，杀 m2 与 m6。

### 该钉而没钉的不变量

1. **`response_header` 从配置到 driver 的接线**（m10 全绿，1247 passed）。这是本次修复自己的立论所在。
2. **「同一个瞬时只算一次」**（m3 全绿）。已给出可用形状。
3. **交付链的嵌套顺序**（m7 全绿），且它防的失效是真的（见第三节实测）。
4. **`with_deadline_at` 关源流**（m8 全绿）。docstring 明写「Closing this closes the stream under it, as every other layer on this chain does」，无人执行。
5. **体阶段击发时的记账与日志行**（`status=fail` + `stream failed before a terminal event: attempt exceeded its deadline`）——完全没测。这是操作者唯一能看到的东西。
6. **体阶段击发不重试**（`attempts` 停在 1）——没测。

### 被删掉的测试

`test_a_per_model_override_decides_the_idle_timeout` 被删除、由 `test_the_attempt_deadline_reaches_the_streamed_body` 取代。它是**唯一**锁住 `stream_idle_overrides` 生效的测试。见下一节。

---

## 七、遗漏的接入面（任务点 7）

### 7.1 `stream_idle_overrides` 静默失效 —— 阻断项 B1

任务描述说「schema 删掉两个 `_overrides`」。**当前工作树里这件事没有发生**：

```
$ git diff HEAD -- src/app/config/schema.py
（空）
```

`src/app/config/schema.py:141` 的 `response_header_overrides` 与 `:144` 的 `stream_idle_overrides` 都还在（我第一次 `git status` 时 schema.py 是 modified，几分钟后再看已回到 HEAD——并行会话在动它）。而 `Section` 是 `extra="forbid"`（`schema.py:53`），所以这两个键**仍然能通过配置校验**。

与此同时 `stream_idle_seconds(chain)`（`src/app/server/handler.py:430-435`）已经不再解析 overrides，锁住它的测试也被删了。实测（`probe_keep.py::test_probe_stream_idle_overrides_still_honoured`，配置 `stream_idle: 0` + `stream_idle_overrides: {claude-model: 1}`，上游静默 1.5s）：

```
P3 config accepted the overrides key; outcome: delivered in full
```

**一个操作者现有配置里的 `stream_idle_overrides` 会照常通过校验、然后什么都不做，没有任何提示。** 这是「不得擅自删除已实现的功能」那一类：用户从他亲笔的 example 里删掉这两个键，是对**对外契约**的裁决；代码里的 schema 字段与 legacy 链路（`src/app/streaming/idle_timeout.py:12 resolve_stream_idle`，被 `src/app/routes/anthropic.py:217` 使用）还在，两边现在互相矛盾。

需要一个明确决定并落到代码里，三选一：（a）schema 也删掉，让旧配置**报错**而不是静默失效；（b）保留字段并在加载时 warn「已忽略」；（c）恢复解析。我倾向 (a) 或 (b)——静默是唯一不可接受的那个。这不是我能替你裁的，请交给用户。

### 7.2 count_tokens 路径不受任何守卫约束

实测（`probe_keep.py::test_probe_count_tokens_is_unbounded`，`response_header: 1` 且 `upstream_request_deadline: 1`，上游 sleep 2s）：

```
P5 count_tokens answered 200 {'input_tokens': 7} after 2.43s with both guards set to 1s
```

`handle_count_tokens`（`src/app/server/handler.py:133`）自己 `begin_attempt()` 并直接 `await provider.count_tokens(...)`，既不经过 driver（因此没有两个上游守卫），也不经过 `handle_bounded`（因此没有 `client_request_deadline`）。这是既有状态、本次改动没让它变差，但既然 `response_header` 现在第一次成为一个真守卫，操作者会合理地期待它也管这条腿。**建议记为 deferred，不要在本次 slice 里顺手加。**

### 7.3 非流式路径 / legacy 路径 / `sse.py`

- **非流式**：不需要额外守卫。`_send` 的外层 `asyncio.timeout_at` 在非流式下本来就覆盖整次尝试（P4 实测，10 次重试后 502）。
- **legacy**：`src/app/routes/anthropic.py` 只被 `src/app/routes/__init__.py` 导入，`src/app/cli.py:23,144,169` 只挂 `create_pipeline_app`。**legacy 链路不对外服务**，不需要同样的守卫。
- **`src/app/streaming/sse.py`**：其中的 `DelayedStartStreamingResponse` / `create_delayed_sse_response` 只服务 legacy 路径，本次改动没有触及，不受影响。

---

## 八、其余发现

### 8.1 限流等待与 `attempt.prepare` 订阅者现在都计入期限 —— 阻断项 B5（需裁决）

`base.py:130-132` 把期限固定在 `begin_attempt()` 之后，注释明说这是有意的（「preparing, waiting on the rate limiter, sending, and then streaming a body」）。但**前置调查报告第三节末尾给出的判断正好相反**：「`acquire()` 在 `_send` 之外，所以限流等待不会计入，这是对的」。这是一处未被提出、也未被记录的推翻。

实测（driver 单元级，`attempt_deadline=1`，限流器 `acquire()` 睡 1.5s，上游只要 0.1s）：

```
R1: succeeded=False error=PipelineAbort('retry budget exhausted: attempt exceeded 1s') elapsed=1.51s upstream_calls=1
```

注意 **elapsed 是 1.51s 而不是 1.0s**：限流等待被**计入但没有被打断**——请求老老实实等满限流，然后一进 `_send` 就因为期限已过而立刻死掉。重试会把这个循环重复一遍，整条重试预算被烧光而上游一次都没真正答复。

同形的第二例（`attempt.prepare` 订阅者睡 1.5s）：

```
R2: succeeded=False error=PipelineAbort('retry budget exhausted: attempt exceeded 1s') elapsed=1.51s calls=1
```

默认 1200s 下实际影响很小，但语义上这是一个**变更**：`upstream_request_deadline` 从「上游花了多久」变成了「这次尝试在我们这边加上游一共花了多久」，包括我们自己的限流。请用户裁决要哪一个；无论哪一个，`config.example.yaml` 的措辞都该跟着走。

### 8.2 `resolve_timeout` 成为死代码

`rg` 显示 `src/app/pipeline/timeouts.py:41 resolve_timeout` 在 `src/` 下已零调用方，只剩 `tests/unit/test_timeout_overrides.py` 的 12 条测试在跑它。与 7.1 的裁决绑在一起处理，不要单独删。

### 8.3 先前存在的缺陷：`run()` 吞掉 `CancelledError`

`base.py:142 except BaseException as error:` 会接住 `CancelledError`，`classify()` 判 ABORT，然后 `run()` **正常返回** `outcome.error=CancelledError`。后果是 `handle_bounded`（`handler.py:247`）的 `asyncio.timeout` 在 `__aexit__` 时看到 `exc_type is None`，因此**不会抛 `TimeoutError`**，`client_request_deadline` 就此静默失效，客户端拿到的是 502 + `{"type":"CancelledError","message":""}`。

实测两组对照，确认**与本次改动无关**（无守卫时行为相同）：

```
R3 (attempt_deadline=100, response_header=100): run() RETURNED NORMALLY (cancellation swallowed): error=CancelledError()
R4 (无任何守卫，HEAD 形状):                      run() RETURNED NORMALLY (cancellation swallowed): error=CancelledError()
```

**先前存在，不阻断本次 slice**，但值得单开一条：它同时影响 `client_request_deadline` 和优雅停机。

### 8.4 `_send` 重新读 `current_attempt` 而不用调用方手上的 `attempt`

`base.py:141` 调 `self._send(context, attempt.payload)` 时 `attempt` 就在手上，`base.py:239` 却又从 `context.current_attempt` 取一次。今天两者必然相同（无人在中途 `begin_attempt`），但这是同一个事实的第二条推导路径。小事，建议顺手改成参数传入。

### 8.5 本次 diff 里搭车的无关改动

`src/app/server/handler.py:175-178` 与 `src/app/server/pipeline_app.py:148, 194, 303-311` 是 count_tokens 的可观测性改动，`tests/http/test_pipeline_app.py` 里新增的两条 `count(...)` 日志测试同样与超时无关。不是缺陷，但被评审的这份 diff 并不只有超时接线——如果要 squash 成一条语义提交，这部分该分开。

### 8.6 静态检查与整体回归

快照上 `ruff check` 对五个改动文件全过；`pyright --pythonpath <venv>` 对同一组文件 `0 errors, 0 warnings`。

快照上未变异的整体跑：

```
tests/unit tests/http tests/component tests/smoke → 10 failed, 1395 passed, 2 skipped in 84.01s
```

10 条失败**全部**在 `tests/smoke/`，全部是 `FileNotFoundError: /tmp/rev-tw/snap/contrib/...` 与 `can't open …/scripts/...`——我建快照时只复制了 `src tests pyproject.toml uv.lock`，没带 `contrib/`、`scripts/`。与本次改动无关。`tests/unit`、`tests/http`、`tests/component` 全绿。

### 8.7 与当前工作树的对账（评审收尾时重新核对）

快照取于 17:24:33；收尾时（约 18:0x）并行会话已经又动过 `src/app/server/handler.py`、`src/app/server/pipeline_app.py`、`src/app/config/schema.py`、`tests/http/test_pipeline_app.py`。我逐段核对过，**改动全部落在 count_tokens 可观测性与 web-search 能力门上，没有一处触及超时接线**：

- `src/app/pipeline/direct_driver/base.py`、`src/app/streaming/deadline.py`、`src/app/pipeline/request.py`、`tests/unit/test_timeout_enforcement.py`、`tests/unit/test_stream_delivery.py`：与快照**逐字节相同**。
- `handler.py` 的 `timeouts = …` 到 `outcome = await driver.run(context)` 一段、`pipeline_app.py` 的 `with_deadline_at(...)` 一段、`handler.py` 的 `stream_idle_seconds` 全文：**只有行号位移**（`handler.py` +1，`pipeline_app.py` +16，`stream_idle_seconds` +18），正文一字未改。
- `schema.py:141` 的 `response_header_overrides` 与 `:144` 的 `stream_idle_overrides` **仍在**（B1 成立）。
- `test_a_per_model_override_decides_the_idle_timeout` 仍不存在于 `tests/http/test_pipeline_app.py`（B1 的另一半成立）。

**本报告的全部结论在当前工作树上依然成立**，只是本文引用的 `handler.py` / `pipeline_app.py` 行号要按上面的位移读。

---

## 九、给主会话的处置建议

| # | 事项 | 类别 | 建议 |
|---|---|---|---|
| B1 | `stream_idle_overrides` 仍能通过校验但已失效，锁它的测试被删 | 阻断 | 交用户裁决：schema 也删（旧配置报错）／保留但加载时 warn／恢复解析。静默不可接受 |
| B2 | `response_header` 的配置→driver 接线零测试（m10 全绿） | 阻断 | 补一条经 `handler.py` 接线的 HTTP 级测试 |
| B3 | 「同一个瞬时只算一次」零分辨力（m3 全绿） | 阻断 | 采用本报告第二节给出的 `header_delay` 形状，已验证能打红 m3 |
| B4 | 嵌套顺序承重却零分辨力（m7 全绿）；`with_idle_timeout` 缺对称鉴别 | 阻断 | 给 `with_idle_timeout` 补 `cancelled_caught` 鉴别，并加顺序测试 |
| B5 | 限流等待/prepare 订阅者计入期限，与前置调查结论相反且未上报 | 阻断（需裁决） | 交用户裁决语义，随后同步 `config.example.yaml` 措辞 |
| O1 | 默认 1200 首次真正掐断流式体，后果未记录 | 上报 | 请用户确认 1200，并把双重身份写进他的注释（我不改他的文件） |
| O2 | count_tokens 腿不受任何守卫约束 | deferred | 记入 deferred，不在本 slice 处理 |
| O3 | `with_deadline_at` 关源流、体阶段日志行、体阶段不重试——三项无测试 | 建议 | 各补一条，成本很低 |
| O4 | `resolve_timeout` 成为死代码 | 随 B1 | 与 B1 一并裁决 |
| O5 | `run()` 吞 `CancelledError` 使 `client_request_deadline` 静默失效 | 先前存在 | 单开一条，不阻断本 slice |
| O6 | `_send` 重读 `current_attempt` | 小 | 顺手改成参数传入 |
| O7 | diff 里搭车的 count_tokens 可观测性改动 | 提示 | squash 时分开 |
| O8 | 评审期间并行会话在改 `src/app/config/schema.py` 等文件 | 提示 | 本报告的结论绑定在 17:24:33 的快照上，收尾时已重新对账（第 8.7 节）：超时接线一字未改，结论全部成立，只需按位移读行号 |

---

## 附：我做过什么、没做过什么

- **做过**：只读地读了工作树；把 `src/ tests/ pyproject.toml uv.lock` 复制到 `/tmp/rev-tw/snap`；在副本树上跑 pytest、10 个变异、若干独立探针；在副本树的 `tests/http/` 下新建了一个只属于评审的探针文件（`test_zz_review_probe.py`，副本另存为 `/tmp/rev-tw/probe_keep.py`）。
- **没做过**：没有修改 `src/`、`tests/`、`docs/.human-controlled/` 下任何文件；没有 `git add/commit/stash/checkout/restore`；没有碰并行会话的活动区。每轮变异后都 `diff -r` 校验副本树已还原（有一次因整体超时被中断，随后立即 `rsync` 还原并复验通过）。
- **一处坑，记下来省得下次再踩**：`cp -a` 把主工作树的 `__pycache__` 一起带进了 `/tmp` 副本，`.pyc` 里的 `co_filename` 指向原路径，于是 pytest 的失败回溯打印的是主工作树的文件路径——看起来像跑错了树。执行的代码其实是副本（`.pyc` 与副本 `.py` 内容一致），但取证时极易误判。**给 `/tmp` 副本树跑测试前先清 `.pyc`，并带 `PYTHONDONTWRITEBYTECODE=1`。**
