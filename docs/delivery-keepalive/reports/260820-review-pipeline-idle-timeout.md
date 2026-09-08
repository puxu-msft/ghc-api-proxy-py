# 新 pipeline 接入 upstream idle timeout：实现核验

评审日期 2026-08-20。评审者为只读角色：未修改 `/home/xp/src/ghc-api-proxy-py` 下 `src/`、`tests/` 的任何文件，未执行任何 git 写操作。所有变异与对照实验在副本树 `/tmp/rev-idle-impl/`（含 `pyproject.toml`、`refs/`、`contrib/`、`data/`）中进行，用主仓 `.venv` 的解释器 + `PYTHONPATH=/tmp/rev-idle-impl/src` 驱动。

被评审对象是工作树磁盘当前字节（未提交），不是某个 commit 快照。工作树里另有并行会话在改 `src/app/server/`、`src/app/pipeline/delivery/`、`src/app/observability/`，本报告只对上述四个文件的 idle-timeout 相关改动负责。

证据强度沿用 `state-decisiveness`：【足以据此行动】／【仅为倾向，需更多样本】／【仅存档】。

---

## 0. 结论前置

**VERDICT: needs-fix。硬阻断 0 条**（bundled default 为 0，守卫默认关闭，生产行为在运维显式开启前不变），但有 1 条 major 实现缺陷、2 条必须交用户裁决的语义分歧、3 条 minor。

| # | 类别 | 一句话 | 强度 |
|---|---|---|---|
| F1 | **major** | `with_idle_timeout` 新增的「关闭源流」在生产链路上**不可达**：`_counted_upstream`（`pipeline_app.py:403-411`）的裸 `async for` 断掉了所有权链。全仓 **1415 条测试删掉它无一变红**。docstring 写下了一条链路不兑现的承诺 | 【足以据此行动】，变异实测 |
| F2 | **需用户裁决** | 实现计的是**字节间隔**，用户亲笔文档（`config.example.yaml:296-297`）写的是「SSE 事件之间的最大间隔秒数」。两者可观测地不等价（上游用 SSE 注释保活时字节级永不触发）。代码注释里说明了理由，但用户没裁决过 | 【足以据此行动】 |
| F3 | **需用户裁决** | 触发后对外只能是 HTTP 200 + 撕断的 body（实测），无带内 SSE `error` 事件；legacy Responses 腿在首块提交前是 502 JSON。研究报告已登记为待裁决点，本次实现既未解决也未新增登记 | 【足以据此行动】，真 uvicorn 实测 |
| F4 | minor | `stream_idle_overrides` 的**接线**零覆盖：把它换成 `response_header_overrides` 全仓依然全绿。与 `handler.py:114-118` 那个已知错配同形——正是「没有接线测试」让那个错配活到今天 | 【足以据此行动】，变异实测 |
| F5 | minor | `schema.py:103` 的 overrides 值无 `ge=0`：负值通过校验，到 `with_idle_timeout` 被 `<= 0` 静默当成「禁用」。配置写错方向相反地静默生效 | 【足以据此行动】，实测 |
| F6 | minor | 新单测 `test_a_client_leaving_while_the_idle_guard_is_armed_leaves_nothing_behind` 分辨力为 0，且其组合形态（guard 直接挂在 `read_events` 下）**在生产中不存在** | 【足以据此行动】 |

**配置语义（问题 1）、legacy 影响（问题 2）、边界值（问题 4）、接入面（问题 6）四项核验通过。** 详见下文。

**通过项汇总（均为实测）**：Ruff `check` 全过；Pyright strict `0 errors`；全仓 `1415 passed, 3 skipped`。

---

## 1. 配置语义 vs 用户亲笔文档 —— 通过

权威源逐字读的是 `docs/.human-controlled/config.example.yaml:279-314`（我自己打开读的，未采信转述）。

### 1.1 键名与归属节 —— 一致

`src/app/server/handler.py:393-401`：

```python
def stream_idle_seconds(chain: Chain, model: str) -> int:
    timeouts = chain.config.upstream_request_timeouts
    return resolve_timeout(model, timeouts.stream_idle, timeouts.stream_idle_overrides)
```

读的是 `upstream_request_timeouts.stream_idle` / `.stream_idle_overrides`，不是旧 `AppSettings.timeouts.stream_idle`（那个仍由 legacy 的 `routes/anthropic.py:217` 通过 `resolve_stream_idle` 使用）。用的是 `pipeline/timeouts.py:41 resolve_timeout` 而不是匹配规则不合裁决的 `streaming/idle_timeout.py:12 resolve_stream_idle`。**符合裁决。**

### 1.2 覆盖表具体度规则 —— 自己写探针实测，符合

不只读码。探针 `/tmp/rev-idle-impl/probe_resolve.py`，实际输出：

```
doc: literal beats glob      model='gpt-5.6-terra'  ov={'gpt-*': 90, 'terra': 45} -> 45  OK
doc: glob beats *            model='gpt-5.6-terra'  ov={'*': 30, 'gpt-*': 90}     -> 90  OK
doc: literal beats *         model='gpt-5.6-terra'  ov={'*': 30, 'terra': 45}     -> 45  OK
doc: longest literal         model='claude-opus-5'  ov={'opus': 60, 'claude-opus': 75} -> 75  OK
doc: longest glob            model='gpt-5.6-terra'  ov={'gpt-*': 90, 'gpt-5.6-*': 120}  -> 120 OK
doc: override 0 disables     model='claude-opus-5'  ov={'opus': 0}                -> 0   OK
doc: * override 0 disables   model='anything'       ov={'*': 0}                   -> 0   OK
doc: no match -> scalar      model='claude-opus-5'  ov={'gpt': 60}                -> 300 OK
SHORT literal vs LONG glob   model='gpt-5.6-terra'  ov={'gpt': 60, 'gpt-5.6-terr?': 120} -> 60  OK
```

最后一行是关键：**类别优先于长度**（短 literal 压过长 glob），这正是文档「literal 子串 > glob > `*`（同类再按键长最长胜）」的读法。`resolve_timeout` 的排序键 `(int(_classify(key)), len(key))`（`timeouts.py:56`）与之一致。

两处**既存**的、文档未覆盖的边角（不是本次改动引入，仅登记，强度【仅存档】）：

- 同类同长的两个键都命中时，`rank > best_rank` 为假使得**先出现者胜**，结果依赖 dict 顺序。实测 `{'terra':45,'gpt-5':99}` → 45，反序 → 99。这与 `timeouts.py:6` 自己的 docstring「A request must not get a different timeout depending on dict order」相悖。文档对同类同长没有规则，故不算违反裁决。
- `_classify`（`timeouts.py:28`）把含 `[` 的键也归为 glob，文档只写了 `*`/`?`。实测 `{'gpt-[0-9]': 90}` 对 `gpt-5` 命中 90。同样属文档未覆盖。

### 1.3 「0 = 禁用」—— 符合，且两侧都对

`src/app/streaming/idle_timeout.py:29-32`：`timeout_seconds <= 0` 时走无守卫的透传分支。`resolve_timeout` 的 docstring（`timeouts.py:48-49`）明确「override 的 0 是决定而非缺省」，实测 `{'opus': 0}` 在 scalar=300 时返回 0。**override 命中 0 确实禁用而不是回退到标量。**

变异 M4（把 `<= 0` 改成 `< 0`，即 0 不再禁用）→ `test_the_bundled_default_leaves_a_quiet_upstream_alone` 变红，日志行显示 `No stream item received for 0s`。**这条判据有分辨力。**

### 1.4 「单次尝试上游」—— 符合，且是平凡符合

守卫挂在 `handle()` 返回后的最终响应体上（`pipeline_app.py:281-285`），而新链路里所有重试都发生在 driver 内、body 迭代之前。`rg 'streamReplay|stream_replay|hedge' src/app/pipeline/ src/app/server/` 只命中 `pipeline/retry.py:29,83`（枚举 + 预算查表），**不存在 body 迭代中途重试的代码路径**。因此「只有一次尝试的 body 会被流式交付」，per-attempt 语义自动成立。强度【足以据此行动】。

### 1.5 模型名取哪个 —— 与既有约定一致

`pipeline_app.py:284` 传 `context.resolved_model`；`handler.py:60` 有 `context.resolved_model = route.model_id`，与 `handler.py:114-115` 给 `attempt_deadline` 用的 `route.model_id` 是同一个值。**一致。** 变异 M5（改成 `context.requested_model`）全仓不变红——但测试配置里两者相等，所以这条变异存活不说明缺陷，只说明这项选择没被钉住。文档也没规定该用请求名还是解析名，登记【仅存档】。

---

## 2. `with_idle_timeout` 关闭源流对 legacy 的影响 —— 通过，无回归

### 2.1 结论

**legacy 对外行为不变，无重复关闭，无提前关闭，相关测试全绿。** 强度【足以据此行动】。

### 2.2 依据

legacy 链（`routes/anthropic.py:216-245`）：

```
upstream.aiter_raw()
  └─ with_idle_timeout(...)                       # anthropic.py:221
       └─ [Responses 腿] render_responses_as_anthropic_sse(...)
            └─ _history_stream(...)               # anthropic.py:35, 第 47 行是裸 async for
                 └─ passthrough_bytes(..., cleanup=upstream.aclose)   # sse.py:28-42
```

三条判据：

1. **`_history_stream`（`anthropic.py:47`）用的是裸 `async for chunk in stream`，它不会关闭上游生成器。** 所以 legacy 上 `with_idle_timeout` 的新 `finally` 只在它自己的生成器体结束时运行（正常耗尽 / 抛超时），不会被外层显式触发。
2. **正常耗尽时无害。** httpx `_models.py:1063` 显示 `aiter_raw()` 在迭代到底时自己会 `await self.aclose()`；此时对一个已耗尽的 asyncgen 再 `aclose()` 是 no-op。
3. **不会重复关闭。** httpx `Response.aclose()`（`_models.py:1065-1076`）被 `if not self.is_closed` 守着，幂等。`passthrough_bytes` 的 `cleanup=upstream.aclose` 因此安全。反过来，关闭 `aiter_raw()` 生成器**不会**把 `Response.is_closed` 置真（第 1063 行在循环之后，GeneratorExit 走不到），所以 legacy 的 `cleanup` 依然是真正释放响应的那一步——它的职责没有被抢走。

### 2.3 实测

副本树上：

```
$ pytest tests -q -k "legacy or anthropic_route or idle or keepalive or resilience or passthrough or sse"
127 passed, 1291 deselected in 6.07s

$ pytest tests -q                      # 全仓
1415 passed, 3 skipped in 60.16s
```

（第一次全仓跑有 11 条 smoke/debug 失败，全部是我副本树缺 `refs/`、`contrib/` 造成的，补齐后 `tests/smoke tests/unit/test_debug_models.py` → `148 passed, 2 skipped`。与被评审改动无关。）

---

## 3. 超时击发时的完整后果 —— 已实测，行为自洽

用真 uvicorn + 真 httpx 客户端跑（`/tmp/rev-idle-impl/probe_firing.py`，复用仓库自己的 `make_client` 造真 chain，只把 TestClient 换成 uvicorn，这样客户端看到的是线上的字节而不是 harness 的行为）。`stream_idle: 1`，上游静默 2 秒。

### 3.1 提交首块**之后**击发

```
[FAIL] 14:29:33 H1/H1 200 anthropic-messages/claude-model 1.0s ↑52B ↓214B: stream failed before a terminal event: No stream item received for 1s
  HTTP status seen by client : 200
  body bytes received        : 555   (message_start + 第一个完整 block)
  body read error            : RemoteProtocolError('peer closed connection without sending complete message body (incomplete chunked read)')
  completion log lines       : [('[FAIL]', 'fail', '...: stream failed before a terminal event: No stream item received for 1s')]
  footer entries left behind : []
```

### 3.2 提交首块**之前**击发

```
[FAIL] 14:29:35 H1/H1 200 anthropic-messages/claude-model 1.0s ↑52B ↓0B: stream failed before a terminal event: No stream item received for 1s
  HTTP status seen by client : 200
  body bytes received        : 0
  body read error            : RemoteProtocolError(...)
  footer entries left behind : []
```

### 3.3 逐条回答

| 问题 | 答案 | 依据 |
|---|---|---|
| 异常从哪抛 | `idle_timeout.py:41-43` 的 `StreamIdleTimeoutError` | — |
| 经过哪些层 | `with_idle_timeout` → `_counted_upstream`（裸 async for，原样上抛）→ `read_events` → `_events_with_ping` → `stream_delivery` → `_tracked_delivery` | `pipeline_app.py:278-297` |
| `_tracked_delivery` 记 failure 吗 | **记**。`pipeline_app.py:429-432` 的 `except Exception` 命中（`StreamIdleTimeoutError` 是 `TimeoutError` 是 `OSError` 是 `Exception`），`accounting.failure = error` 后重抛 | 上方实测日志 `status=fail` |
| 完成日志行 | `[FAIL] ... 200 ... ↑52B ↓214B: stream failed before a terminal event: No stream item received for 1s`，走 `_ending()` 的第一支（`pipeline_app.py:364-365`） | 实测 |
| footer 是否移除 | **是**，`active_requests` 击发后为空 | 实测 |
| 上游 httpx 响应是否释放 | **是**，且是及时的 | 见 §3.4 |
| 首块前 vs 首块后 | **状态码无差别，都是 200**（Starlette `StreamingResponse` 在拉第一个 chunk 之前就发了 `http.response.start`）。只差已交付的字节数与 `↓` 计数 | 实测两栏 |

### 3.4 上游释放：真 socket 实测

`/tmp/rev-idle-impl/probe_release.py`：本地 asyncio socket 服务器发三帧后永久静默，httpx AsyncClient + 生产组合。

```
connections after headers: [<AsyncHTTPConnection [... ACTIVE, Request Count: 1]>]
raised: StreamIdleTimeoutError: No stream item received for 1s
fired after 1.01s
response.is_closed  right after the raise: False
pool connections     right after the raise: []
server saw peer close: True b'' None
```

**连接池当场清空、服务端收到 FIN。** 释放机制是 httpcore 的 `PoolByteStream.__aiter__` 在收到任何 `BaseException`（这里是 anyio 取消投递到上游自己的 await 点）时自行 `aclose()`——**不是** `with_idle_timeout` 新增的那行 close 做的（见 F1）。

`response.is_closed` 停在 `False` 属于 httpx 的簿记标志（`Response.aclose()` 从未被调用），socket 已经断了，无人再读这个响应，**不构成泄漏**。强度【足以据此行动】。

### 3.5 取消 vs 截止时刻的竞态：无误标

研究报告 §2.4 提过「`except OSError` 会把 TimeoutError 家族改标成 ClientDisconnect」的风险。新链路上没有这种层（已核 `pipeline_app.py:359-400` 无 `except OSError`）。

我另外担心一种反向误标：外部取消（客户端离开）刚好落在 `anyio.fail_after` 作用域内时，anyio 会不会把它吞掉当成自己的超时，从而把 `gone` 报成 `fail`。探针 `/tmp/rev-idle-impl/probe_race.py`（守卫 0.30s，取消点从 t+0.0 扫到 t+0.40）：

```
  cancel at t+0.2999 -> CancelledError,outer:CancelledError
  cancel at t+0.3000 -> CancelledError,outer:CancelledError
  cancel at t+0.3001 -> CancelledError,outer:CancelledError
  cancel at t+0.3100 -> StreamIdleTimeoutError,outer:StreamIdleTimeoutError
```

**分界干净，没有吞掉外部取消，没有挂起，没有残留任务。** 这条比新单测 F6 更直接地覆盖了那条单测声称要钉的东西。强度【足以据此行动】。

---

## 4. F1（major）：新增的源流关闭在生产链路上不可达

### 4.1 现象

`src/app/streaming/idle_timeout.py:23-26, 45-47` 新增：

```python
    """...
    Closing this closes the stream under it, including on the timeout — giving up on an upstream and leaving its response open would hold the connection for exactly as long as the wait that made us give up. A bare `async for` closes nothing when GeneratorExit unwinds past it, so the close is explicit.
    """
    ...
    finally:
        if close is not None:
            await close()
```

**变异 M1**：把 `finally` 体换成 `pass`（即完全撤掉这次改动的第 3 项），跑全仓：

```
1415 passed, 3 skipped in 60.16s
```

**全仓一条都不变红。** 强度【足以据此行动】。

### 4.2 为什么

生产链路是（`pipeline_app.py:278-295`）：

```
response.aiter_bytes()
  └─ with_idle_timeout(...)          <- 新增的 close 在这里
       └─ _counted_upstream(...)     <- pipeline_app.py:408 是裸 `async for chunk in chunks`
            └─ read_events(...)      <- sse_source.py:73,86-87 会关闭它的源
                 └─ _events_with_ping(...)
```

`_counted_upstream`（`pipeline_app.py:403-411`）**没有**被 commit `926cabf` 修过——那次修的是 `read_events`、`stream_delivery`、`_events_with_ping` 和 `_AccountedStreamingResponse`，`_counted_upstream` 是漏网的一层。它的裸 `async for` 恰恰是 `with_idle_timeout` 自己 docstring 里点名的那种「closes nothing when GeneratorExit unwinds past it」。

对照实验 `/tmp/rev-idle-impl/probe_close_chain2.py`（源流悬挂在 `yield` 而非 `await` 上，这样只有显式 `aclose()` 能跑到它的 `finally`）：

```
counted=False hold_ref=True: right after aclose() -> ['source closed']      # 新单测的形态
counted=True  hold_ref=True: right after aclose() -> []                     # 生产的形态
counted=True  hold_ref=False: right after aclose() -> ['source closed']     # 靠 asyncgen finalizer 兜底
```

第二行是决定性的：**加上 `_counted_upstream` 之后，关闭交付链不再确定性地关闭 guard 与其下的 `aiter_bytes()`**；只有当最后一个引用也掉了、CPython 的 asyncgen finalizer hook 被 asyncio 调度上去，它才被关——正是 `926cabf` 那条 commit message 想消灭的非确定性路径。

### 4.3 严重程度与影响面

**不是回归**：改动前 `_counted_upstream` 直接吃 `response.aiter_bytes()`，同样不确定性地释放。真 socket 对照（`/tmp/rev-idle-impl/probe_disconnect.py`，客户端读完一块就走）：

```
guard=off: pool right after aclose(): [<AsyncHTTPConnection [... ACTIVE ...]>]
guard=off: pool after 50 ticks     : []
guard=on : pool right after aclose(): [<AsyncHTTPConnection [... ACTIVE ...]>]
guard=on : pool after 50 ticks     : []
```

**加不加 guard 完全一样**：都不是 `aclose()` 释放的，都得等几个 loop tick。

所以 F1 的问题不是「坏了」，而是**这次改动的第 3 项在新链路上价值为 0，同时写下了一条链路并不兑现的承诺**。docstring 说「Closing this closes the stream under it」——生产里没有人会 close 它。既有一层引用被意外持有（异常 traceback 抓住栈帧、future 持有闭包），释放就会无限期推迟。

### 4.4 建议（两条，任选，都不影响本次功能）

- **改法 A（推荐，一行）**：把 `_counted_upstream`（`pipeline_app.py:408`）的裸 `async for` 换成 `async with aclosing(chunks) as source: async for chunk in source:`，与 `stream_delivery`（`stream.py:125`）、`read_events`（`sse_source.py:73`）一致。这样 `926cabf` 的所有权链才真正闭合到 `aiter_bytes()`，`with_idle_timeout` 的新 close 也才有意义。
- **改法 B**：保留现状，但把 `with_idle_timeout` 的 docstring 改成实话（「谁关它就关下面那层；本仓新链路当前没有人关它」），并在 `_counted_upstream` 上留一条注记说明断链是已知的。

我倾向 A：改动更小，且它顺手把 `_counted_upstream` 这个 `926cabf` 的漏网层补上。**但两条都不是本次功能的前置**，可作为独立小切片。

**注意**：无论选哪条，都必须配一条能杀掉 M1 的测试——否则这块永远处于「改了也没人知道」的状态。可用的最小形状就是 `probe_close_chain2.py` 的第二行场景：源流悬挂在 `yield` 上、链路里有 `_counted_upstream`、断言 `aclose()` 返回时源流已关。

---

## 5. F2（需用户裁决）：字节间隔 vs SSE 事件间隔

用户亲笔（`config.example.yaml:296-297`）：

> 单次尝试上游，SSE **事件之间**的最大间隔秒数（0 = 不超时）。适用于所有流式路径。
> Each upstream attempt: Max seconds **between SSE events** (0 = no timeout).

实现把守卫挂在 `response.aiter_bytes()` 外（`pipeline_app.py:281-285`），计的是**字节到达之间**的间隔。`pipeline_app.py:280` 的注释给了理由：上游用 SSE 注释帧保活，而 `parse_frame`（`sse_source.py:40-41`）丢弃以 `:` 开头的行，事件级计时会在一条**可见仍然活着**的连接上误杀，违反用户冻结的不变量。

**这个理由我认为成立**（`sse_source.py:40-41` 的 `if line.startswith(":"): continue` 是我自己核过的），而且偏差方向是保守的——字节级严格更宽松，不会造成误杀。

但两点必须点明：

1. **这仍然是与一份用户亲笔、被标为冻结的文档的可观测偏差。** 上游每 10 秒发一个 `: ping`、`stream_idle=30` 时：文档语义会在 30 秒触发，实现永不触发。不是等价实现，是不同的守卫。
2. **偏差只记在代码注释里。** `handler.py:394-399` 的 docstring 讲了 0 和不变量，没提这条；`docs/` 下也没有任何记录。研究报告 `docs/tmp/260820-research-pipeline-idle-timeout.md:80` 把「计时器读字节还是读事件」列为**未裁决**项。按 `no-silently-cut-but-defer`，这条应当提请用户裁决并落到文档，而不是由实现单方面定下来。

选型之争由另一位评审对抗性复核，我不重复；**我这一条只登记「用户没裁决过，且偏差未进文档」这个事实**。强度【足以据此行动】。

---

## 6. F3（需用户裁决）：击发后客户端拿到的是撕断，没有可辨认的失败

§3 的实测：无论首块前后，客户端拿到 HTTP 200 + `RemoteProtocolError`，没有带内 `error` 事件、没有 `message_stop`。运维侧的信息是全的（`[FAIL]` 行带原文），客户端侧读不出发生了什么，也无法与「上游 RST」「客户端自己断了」区分。

对照 legacy Responses 腿（研究报告 §2.3，我未复测）：首块提交前是 502 JSON + `responses_stream_conversion_error`。**新链路上没有这个可能**，因为 `_AccountedStreamingResponse` 是 Starlette `StreamingResponse` 子类、未覆盖 `stream_response`，响应头在拉第一个 chunk 之前就发出去了。

这与 `stream.py:173-177` 登记的 STR-04 缺口是同一件事的两半。研究报告 §6 第 3 条已把它列为待裁决，本次实现既没有解决，也没有在任何文档里新增登记。**建议在合入前把这条写进 `.dev/docs/<topic>/decision-pending.md` 之类的待裁决台账**，不要让它只活在一份 `docs/tmp/` 报告里。强度【足以据此行动】。

同一族的另一条未裁决项（研究报告 §3.3 第 3 条）：**击发后要不要重试、归 `upstream_request_retry.strategies` 哪一栏**。实现默认不重试（异常发生在 driver 返回之后，重试根本不在其控制范围）。这个默认我认为是当前架构下唯一可行的，但同样没有被裁决过，应一并登记。

---

## 7. F4（minor）：overrides 接线零覆盖

**变异 M3**：把 `handler.py:401` 的 `timeouts.stream_idle_overrides` 换成 `timeouts.response_header_overrides`，跑 `tests/unit/test_stream_delivery.py tests/unit/test_streaming_sse.py tests/unit/test_timeout_overrides.py tests/http/test_pipeline_app.py`：

```
133 passed in 15.59s
```

**不变红。**

`tests/unit/test_timeout_overrides.py` 的 11 条测试覆盖的是 `resolve_timeout` 这个**函数**，不是它被接到哪张表上。而「标量取 A 的、覆盖表取 B 的」正是 `handler.py:114-118` 已经犯下的错（研究报告 §5.3 已实证：`attempt_deadline` 的标量取 `upstream_request_deadline`，覆盖表却取 `response_header_overrides`）。那个错配至今没有症状，唯一原因就是**两张表都是空的、且没有任何接线测试**。

新代码目前写对了，但它落在同一片没有守卫的地面上。

**建议**：加一条零耗时的接线断言即可，不必走 HTTP。形状类似我的 `/tmp/rev-idle-impl/probe_boundaries.py`：

```python
chain = <配置了 stream_idle=300, stream_idle_overrides={"opus": 5}>
assert stream_idle_seconds(chain, "claude-opus-5") == 5
assert stream_idle_seconds(chain, "gpt-5.6") == 300
```

这条能杀掉 M3，成本约 0 秒。强度【足以据此行动】。

---

## 8. F5（minor）：负数覆盖静默变成「禁用」

`src/app/config/schema.py:96-104`：

```python
    response_header: int = Field(default=0, ge=0)
    response_header_overrides: dict[str, int] = Field(default_factory=...)      # 值无约束
    stream_idle: int = Field(default=0, ge=0)
    stream_idle_overrides: dict[str, int] = Field(default_factory=...)          # 值无约束
```

实测（`probe_boundaries.py`，走真 `ProxyConfig.model_validate` + 真 `stream_idle_seconds`）：

```
bundled default (nothing set)          -> 0
scalar 0                               -> 0
scalar 1                               -> 1
scalar 300, override 0 on a hit        -> 0
scalar 300, override 0 on '*'          -> 0
scalar 0, override 5 on a hit          -> 5
negative override                      -> -7          <- 通过校验
negative scalar                        -> REJECTED by validation: ValidationError
```

标量被 `ge=0` 拦住，覆盖表的值没有。`-7` 一路走到 `with_idle_timeout`，被 `timeout_seconds <= 0`（`idle_timeout.py:29`）当成禁用。

方向是安全的（不会误杀），但**运维把 `-7` 写成配置时得到的是「静默关闭这个模型的守卫」，而不是一条错误**。这正是项目记忆「日志行上的缺席读不出来」的同族形态。

**建议**：`dict[str, Annotated[int, Field(ge=0)]]`，两张覆盖表一起改。既存问题，一行修复，不阻断本次改动。强度【足以据此行动】。

---

## 9. F6（minor）：第三条新单测的处置 —— 建议**改造，不要删**

`tests/unit/test_stream_delivery.py:551-568`。

### 9.1 分辨力实测

- 撤掉源流关闭（M1）→ **不变红**（§4.1 已证，全仓 1415 条都不红）。
- 实现者自陈打掉 `pending.cancel()` 会挂起而非红字——我未复测这一条，采信【仅为倾向】。

它为什么杀不掉 M1：`_hanging_upstream`（`test_stream_delivery.py:490-498`）在 `reached.set()` 之后悬在 `await asyncio.Event().wait()` 上。关闭时是 `finish_stream_cleanup` **取消那个在途 pull**，取消投递到源流自己的 await 点，`finally` 因此自然跑到——**跟有没有 close 无关**。`assert closed == [True]` 断的是取消路径，不是关闭路径。

### 9.2 还有一个更根本的问题：形态不对

它把 guard 直接挂在 `read_events` 下（`_delivery(with_idle_timeout(...))`），而生产里中间隔着 `_counted_upstream`（§4.2）。**这个组合在生产中不存在。** 于是即使它某天真的开始检查关闭，检查的也是另一条链。

### 9.3 它是否白写

不完全是。它声称要钉的是「anyio cancel scope 与每次一个新 pull 任务的组合」。这件事**确实值得钉**，而且我的 `probe_race.py`（§3.5）证明这个组合是健全的——没有吞掉外部取消、没有残留任务、截止点前后干净分界。

### 9.4 建议

**改造，不要删。** 两处改动就能让它有分辨力且贴合生产：

1. 在链路里加上 `_counted_upstream` 那一层（或至少一个同形的裸 `async for` 透传），使被测组合等于生产组合；
2. 把源流从「悬在 `await`」改成「悬在 `yield`」（即上游还有数据没发完、客户端先走），这样取消路径不再顺手替 close 路径完成工作，`assert closed == [True]` 才真的在断关闭。

改造后它会**当场变红**（因为 F1 的断链）——这正是它应该做的事。所以 F1 和 F6 是同一件事的两半，建议合成一个切片处理。

删掉的代价：`_events_with_ping` 的每-pull-一个新任务 × anyio scope 这个组合就再没有任何回归防护，而这恰恰是方案 A 唯一真正新颖的风险点（研究报告 §3.2 缺点二把它标为【仅为倾向，需更多样本】）。

### 9.5 前两条 HTTP 级测试：值得，建议留

- `test_an_upstream_that_goes_quiet_past_the_idle_timeout_is_given_up_on`：1.03s，**杀掉 M2**（撤掉 `pipeline_app.py` 里的 wrapper → `DID NOT RAISE StreamIdleTimeoutError`）。
- `test_the_bundled_default_leaves_a_quiet_upstream_alone`：1.52s，**杀掉 M4**（`<= 0` 改 `< 0`）。

两条合计约 2.6 秒真实等待，换来这条链上**仅有的两条**接线判据。我认为值得。

「更省的等价钉法」我找了，结论是**没有**：`stream_idle` 在 schema 里是 `int`（`schema.py:102`），运维能配的最小非零值就是 1 秒，所以走真配置的击发测试下不到 1 秒以下。要更省只能绕开配置直接给 `with_idle_timeout` 传浮点，那就不再是接线测试了——而接线正是 M3 暴露出的薄弱处。

唯一可省的边角：第二条的 gap 是 1.5 秒，但守卫在那条测试里是**关闭**的，`anyio.fail_after` 根本不会进入，gap 多长都不改变结论。降到 1.1 秒可省约 0.4 秒，同时保住「比最小可配值 1 秒还长」的对称读法。收益很小，**不建议为此改动**。

---

## 10. 接入面核查 —— 通过

用户文档说「适用于所有流式路径」。

**新 pipeline app 上，`pipeline_app.py:283` 是唯一的流式出口。** 依据：

- `build_router()`（`pipeline_app.py:438-451`）把 `ROUTES` 里所有路径（含 `/v1`、`/openai/v1` 前缀变体）**统统注册到同一个 `_serve`**；`_serve` → `_dispatch` → `pipeline_app.py:262` 的 `if context.stream:` → 唯一的 `_AccountedStreamingResponse`。
- `create_pipeline_app`（`pipeline_app.py:454-470`）另外挂了 `ops_router`（健康、模型列表、metrics），`rg 'StreamingResponse|Stream' src/app/server/ops.py` **无命中**，不流式。
- `rg 'StreamingResponse|aiter_bytes|aiter_raw|aiter_lines' src/` 在新链路侧只命中 `pipeline_app.py`。

**`src/app/streaming/sse.py` 的 `DelayedStartStreamingResponse` 是 legacy 专用**，只被 `create_delayed_sse_response`（`sse.py:214-222`）构造，只被 `routes/anthropic.py:247` 调用。而 legacy app 不在生产入口上：`rg 'create_pipeline_app|create_app|app_factory' src/app/cli.py src/app/lifecycle/*.py` 只命中 `cli.py:23,144,169` 的 `create_pipeline_app`；`app_factory` 在 `src/` 里除了自身与两处注释外无引用。

**登记一条既存缺口**（不属本次改动，强度【足以据此行动】）：legacy 的 `routes/openai.py:37`、`routes/azure.py:33`、`routes/gemini.py:33` 三条流式路径**从来没有 idle timeout**——只有 `routes/anthropic.py:221` 有。用户文档的「适用于所有流式路径」在 legacy app 上从未成立。由于 legacy app 不被服务，这不影响产品行为；但如果哪天 legacy 被重新挂上，这三条就是裸的。

---

## 11. 复现清单

全部只读，产物在 `/tmp/rev-idle-impl/`，未写入仓库。副本树建法：

```bash
rm -rf /tmp/rev-idle-impl && mkdir -p /tmp/rev-idle-impl
cd /home/xp/src/ghc-api-proxy-py
cp -a src tests pyproject.toml uv.lock refs contrib data README.md /tmp/rev-idle-impl/
```

跑法（不建新 venv，借主仓解释器，`PYTHONPATH` 优先级高于已安装包，已核 `app.__file__` 指向副本）：

```bash
cd /tmp/rev-idle-impl
PYTHONPATH=/tmp/rev-idle-impl/src /home/xp/src/ghc-api-proxy-py/.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

| 探针 | 回答的问题 |
|---|---|
| `probe_resolve.py` | 覆盖表具体度规则是否真的按文档实现（§1.2） |
| `probe_boundaries.py` | 0 / 1 / 负数 / override 命中 0，走真 `ProxyConfig` + 真 `stream_idle_seconds`（§1.3、F5） |
| `probe_close_chain.py` | 取消路径下源流是否被释放（结论：是，但靠取消而非 close，探针本身分辨不出 close 的作用） |
| `probe_close_chain2.py` | **纯 close 路径**：源流悬在 `yield` 上，隔离出 `_counted_upstream` 的断链（§4.2，F1 的决定性证据） |
| `probe_release.py` | 真 socket：击发后连接池与服务端 FIN（§3.4） |
| `probe_disconnect.py` | 真 socket：客户端离开时的释放，guard on/off 对照（§4.3） |
| `probe_firing.py` | 真 uvicorn：击发的完整对外后果，首块前/后两栏（§3.1、§3.2） |
| `probe_race.py` | 外部取消 vs 截止时刻的竞态是否误标（§3.5） |

变异（每条做完立即从 `.orig_*.py` 恢复，已核恢复后与主仓字节相同）：

| 变异 | 内容 | 结果 |
|---|---|---|
| M1 | `with_idle_timeout` 的 `finally` 体改成 `pass` | 全仓 **1415 passed** —— 存活 |
| M2 | 撤掉 `pipeline_app.py` 里的 `with_idle_timeout(...)` 包裹 | `test_an_upstream_that_goes_quiet_...` 变红 —— 被杀 |
| M3 | `stream_idle_overrides` → `response_header_overrides` | 133 passed —— 存活 |
| M4 | `timeout_seconds <= 0` → `< 0` | `test_the_bundled_default_...` 变红 —— 被杀 |
| M5 | `context.resolved_model` → `context.requested_model` | 133 passed —— 存活（测试配置下两值相等，不构成缺陷证据） |

静态检查（副本树，Pyright 用 `/tmp/rev-idle-impl/pyrightconfig.json` 把主仓 `.venv` 接进来）：

```
ruff check <四个改动文件>            -> All checks passed!
pyright (strict, include src+tests) -> 0 errors, 0 warnings, 0 informations
```

---

## 12. 处置建议汇总

| # | 建议 | 是否阻断本次合入 |
|---|---|---|
| F1 | 把 `_counted_upstream`（`pipeline_app.py:408`）改成 `aclosing`，闭合 `926cabf` 的所有权链；或改 docstring 说实话。配一条能杀 M1 的测试 | 否，建议作独立小切片 |
| F2 | 把「字节级 vs 事件级」的偏差提请用户裁决并落到文档 | 否，但**合入前应登记** |
| F3 | 把「击发后客户端看到什么」「要不要重试」两条待裁决项从 `docs/tmp/` 的研究报告搬进待裁决台账 | 否，但**合入前应登记** |
| F4 | 加一条 `stream_idle_seconds` 的接线断言（约 0 秒），杀掉 M3 | 否，强烈建议一并做 |
| F5 | 两张 overrides 表的值加 `ge=0` | 否 |
| F6 | 改造第三条单测（加 `_counted_upstream` 层 + 源流悬在 `yield`），与 F1 合成一个切片；**不要删** | 否 |

被评审的四项改动本身——配置解析、接入点、边界行为、日志与 footer 终态——我核下来是**对的**，且有实测支撑。needs-fix 的理由集中在「一项改动没有兑现它写下的承诺且无人能发现」（F1）与「两项语义分歧被实现单方面定下且没进文档」（F2、F3）。
