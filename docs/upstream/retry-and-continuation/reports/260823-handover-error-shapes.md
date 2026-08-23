# `hand_back_block(error=...)` 实际会收到哪些异常，它们的 `str()` 与 `__cause__` 链长什么样

- 日期：2026-08-23
- 主树 HEAD：`de5a1ac`
- 任务：纯调查，未改动任何代码
- 探针脚本（临时，未入库）：`/tmp/probe_handover_errors.py`、`/tmp/probe2.py`

## 证据等级约定

| 标记 | 含义 |
|---|---|
| **代码直读** | 从当前 HEAD 的源码读出，附 `文件:行号` |
| **本次实测** | 本次调查跑了探针，附输出 |
| **既有实测** | 引用仓库内已有的一手实测记录（PoC 报告 / 测试） |
| **推断** | 未验证，只是从代码结构推出来的 |

---

## 1. 谁把 `error` 传进 `ContinuationSupport.synthesize`

### 1.1 调用链（代码直读）

```
inference.py:436  stream_delivery(..., continuation=ContinuationSupport(synthesize=_hand_back_streaming, ...))
  └─ stream.py:257 _deliver(...)
       ├─ stream.py:372  _hand_over(continuation, session, assembler, framer, error=torn)     ← 唯一能传非 None error 的点
       └─ stream.py:413  _hand_over(continuation, session, assembler, framer, stop_reason=terminal.stop_reason)  ← error 走默认值 None
            └─ stream.py:472  payload = continuation.synthesize(error, stop_reason)
```

**结论：整个代码库里能让 `error` 非 `None` 的调用点只有一个——`src/app/pipeline/delivery/stream.py:372`。**（代码直读；`_hand_over` 的 `error` 参数默认 `None`，见 `stream.py:458`）

另外两条路径的 `error` 恒为 `None`：

- `stream.py:413`（流式，上游干净收尾但 `stop_reason ∈ hand_over_stop_reasons`）——代码直读。
- `src/app/server/routes/inference.py:480` `_hand_back(None, str(payload.get("stop_reason", "")))`（非流式/缓冲路径）——代码直读，字面量 `None`。

### 1.2 `torn` 是什么，从哪来（代码直读）

`torn` 在 `stream.py:317-319` 被赋值：

```python
except Exception as error:
    torn = error
```

这个 `try` 覆盖 `stream.py:282-316`，也就是整个 `_events_with_ping` 迭代 + `assembler.push` + `_commit`（含 `framer.block(...)`）+ `yield`。

`Exception` 而非 `BaseException`：`CancelledError` 与 `GeneratorExit` 结构上进不来（`stream.py:318` 的注释就是讲这个）。

### 1.3 从 `torn` 到 `synthesize` 之间的四道闸（代码直读）

按代码里的顺序：

| 序 | 位置 | 判据 | 被挡掉的异常 |
|---|---|---|---|
| 1 | `stream.py:322` | `isinstance(torn, ClientDeadlineError)` → 发 error frame 后 `return` | **`ClientDeadlineError` 永远到不了 `synthesize`** |
| 2 | `stream.py:338` | `assembler.terminal.seen` → `break`，走正常收尾 | 上游已经收尾之后才撕裂的一切异常 |
| 3 | `stream.py:348` | `ours = isinstance(torn, DeliveryError) or torn is from_assembly` | `DeliveryError`/`BufferCapExceeded`/`ResponseAlreadyStarted`，以及**从 `assembler.push` 里抛出的任何异常**（按身份比较，不按类型） |
| 4 | `stream.py:469` | `session.committed_count == 0 and stop_reason not in continuation.stop_reasons` → 返回 `None` | error 路径下 `stop_reason=""`，所以此闸等价于「一个完整块都没交付过就不交接」 |

中间还有一段：`stream.py:350-367`，若 `replay.eligible(torn)` 给出 reason 且 `decide_stream_ending` 判 `REPLAY` 且 `reopen()` 成功，则整条流被换掉、`continue`，这一次的 `torn` 就不会到达交接。**注意 `reason is None`（无法命名的异常）不会被拦——`stream.py:368` 的 `if not ours:` 是无条件的**，这是 2026-08-22 修的那个洞（`stream.py:369` 的注释、`tests/unit/pipeline/delivery/test_stream_delivery.py:1169` 的测试）。

### 1.4 上游字节流的异常来源（代码直读）

生产链（`inference.py:438-455`，外到内）：

```
with_client_deadline_at            → ClientDeadlineError        (deadline.py:77)
  _counted_upstream                → 只转发，自身不抛           (inference.py:599)
    with_deadline_at               → StreamDeadlineError        (deadline.py:66)
      with_idle_timeout            → StreamIdleTimeoutError     (idle_timeout.py:46)
        response.aiter_bytes()     → httpx2 的原始传输异常 / 裸 h2 异常
```

`response` 是 **`httpx2.Response` 原件**，不是 SDK 包装：`GhcApiClient._post_openai` 用 `cast_to=httpx2.Response`（`src/app/model_provider/ghc_client/client.py:83-89`），返回值类型标注也是 `httpx2.Response`（`driver.py:59`）。所以**读 body 时抛的是 httpx2 的异常，不经过 openai SDK，也不经过 `normalize_upstream_error`**。

`read_events`（`sse_source.py:65`）自身不抛：JSON 解析失败在 `SseEvent.json()` 里被吞成 `{}`（`sse_source.py:27-32`），解码用 `errors="replace"`（`sse_source.py:39`）。

---

## 2. 可能到达 `synthesize(error=非 None)` 的异常清单

### 2.1 分类判据的实测结果（本次实测，`/tmp/probe2.py`）

`category` 由 `hand_over.py:89-91` 算出：`replay_reason(error)` → `CATEGORY_FOR_REASON` → 落空则 `internal`。

```
type                                          normalize          replay_reason  category
app.streaming.idle_timeout.StreamIdleTimeoutError None               network        network
app.streaming.deadline.StreamDeadlineError    None               network        network
app.streaming.deadline.ClientDeadlineError    None               None           internal
httpx2.ReadError                              UpstreamError      network        network
httpx2.RemoteProtocolError                    UpstreamError      network        network
httpx2.ReadTimeout                            UpstreamError      network        network
httpx2.ConnectError                           UpstreamError      network        network
httpx2.WriteError                             UpstreamError      network        network
httpx2.ProtocolError                          UpstreamError      network        network
httpx2.LocalProtocolError                     UpstreamError      network        network
h2.exceptions.ProtocolError                   None               None           internal
app.pipeline.delivery.blocks.BufferCapExceeded None               None           internal
builtins.RuntimeError                         None               None           internal
```

（`ClientDeadlineError` 与 `BufferCapExceeded` 两行只是判据本身的取值，它们**结构上到不了交接**，见 1.3 的闸 1 与闸 3。）

### 2.2 逐个异常

#### (a) `app.streaming.idle_timeout.StreamIdleTimeoutError`

- 完整类型名：`app.streaming.idle_timeout.StreamIdleTimeoutError`（继承 `TimeoutError`）
- `str()`：`f"No stream item received for {timeout_seconds:g}s"`，例如 `'No stream item received for 300s'`（**代码直读** `idle_timeout.py:46-48`）
- **能否为空串：不能。**构造时恒带消息。
- `__cause__` 链：**2 层**（**本次实测**）
  ```
  StreamIdleTimeoutError(str='No stream item received for 0.2s')
    -> __cause__ builtins.TimeoutError(str='')
    -> __cause__ asyncio.exceptions.CancelledError(str='')
  ```
  第一层是 `asyncio.timeout` 抛的 `TimeoutError()`（无参，`str()` 为空），第二层是它自己的 `CancelledError`。
- `category` = `network`
- 生产可达性：**既有实测**——`tests/int/test_pipeline_app.py:2472` `test_an_upstream_that_goes_quiet_past_the_idle_timeout_is_given_up_on` 断言 `b"turn_interrupted" in delivered`，即这条确实走到了交接。默认 `stream_idle` 为 0（关闭），运维开启后才可能触发。

#### (b) `app.streaming.deadline.StreamDeadlineError`

- 完整类型名：`app.streaming.deadline.StreamDeadlineError`（继承 `TimeoutError`）
- `str()`：恒为 `'attempt exceeded its deadline'`（**代码直读** `deadline.py:66`，唯一构造点，字面量硬编码）
- **能否为空串：不能。但它是一个固定串，不含任何区分信息**——两次不同原因的 attempt 超时在 `input.message` 上完全同形。
- `__cause__` 链：**2 层**（**本次实测**），与 (a) 同形：`-> TimeoutError('') -> CancelledError('')`
- `category` = `network`
- 生产可达性：**既有实测**——`tests/int/test_pipeline_app.py:2524`（`test_the_attempt_deadline_reaches_the_streamed_body`）与 `:2595`（`test_the_deadline_is_one_instant_and_not_a_duration_started_twice`）都断言 `b"turn_interrupted" in delivered`。

#### (c) `app.streaming.deadline.ClientDeadlineError` —— **到不了**

- `str()`：恒为 `'client request exceeded its deadline'`（**代码直读** `deadline.py:77`）
- `__cause__` 链 2 层，同 (a)（**本次实测**）
- **结构上永远到不了 `synthesize`**：`stream.py:322-337` 在任何交接判断之前就 `return`。这是 2026-08-22 的裁决（`stream.py:329` 注释）。
- `hand_over.py:44-45` 的 `replay_reason` 仍然显式点名并拒绝它，`hand_over.py:42-43` 的 docstring 明说这是不依赖 delivery 行为的防御，不是当前可达路径。

#### (d) `httpx2.ReadError`

- 完整类型名：`httpx2.ReadError`（MRO: `TransportError` → `HTTPError` → `Exception`）
- `str()`：**实测为空串**。**本次实测**（真实 localhost socket，服务端发完 headers + 部分 body 后 `SO_LINGER=0` 强制 RST）：
  ```
  httpx2.ReadError(str='')
    -> __cause__ httpcore2.ReadError(str='')
    -> __cause__ anyio.BrokenResourceError(str='')
    -> __cause__ builtins.ConnectionResetError(str='[Errno 104] Connection reset by peer')
  ```
- **能否为空串：会，而且真实连接重置这一最常见形态就是空串。**唯一带信息的是 `__cause__` 链第 3 层。
- `__cause__` 链：**3 层**（httpcore2 → anyio → OSError）
- `category` = `network`
- 机制解释（**代码直读**）：httpx2 的 `map_httpcore_exceptions` 用 `message = str(exc); raise mapped_exc(message) from exc`（`httpx2/_transports/default.py:114-115`），把 httpcore2 的空消息原样搬过来。

#### (e) `httpx2.RemoteProtocolError`

- 完整类型名：`httpx2.RemoteProtocolError`（MRO: `ProtocolError` → `TransportError` → `HTTPError`）
- `str()`：**取决于是 HTTP/1.1 还是 HTTP/2**
  - HTTP/1.1 中途干净 FIN（**本次实测**）：
    ```
    httpx2.RemoteProtocolError(str='peer closed connection without sending complete message body (received 19 bytes, expected 1000)')
      -> __cause__ httpcore2.RemoteProtocolError(同串)
      -> __cause__ h11._util.RemoteProtocolError(同串)
    ```
    链 **3 层**，全部带同一条信息。
  - HTTP/2 收到 GOAWAY（**既有实测**，`.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-poc.md:130,143`）：
    ```
    httpx.RemoteProtocolError: '<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>'
      -> __cause__ httpcore.RemoteProtocolError(同串)
    ```
    链 **2 层**。注意该 PoC 记的是迁移前的 `httpx`/`httpcore` 名字，当前仓库是 `httpx2`/`httpcore2`；异常内容不受影响（**推断**：两者是同一上游库的重打包）。
  - 上游 HTTP/2 连接直接断（httpcore2 的 `raise RemoteProtocolError("Server disconnected")`，`httpcore2/_async/http2.py:411`）：`str()` = `'Server disconnected'`（**代码直读**）
- **能否为空串：真实路径下未观测到空串**（三种形态都带消息）。手工构造的 `httpx2.RemoteProtocolError("")` 当然为空（**本次实测**），测试里就是这么造的。
- `category` = `network`
- 生产可达性：**既有实测**，`.dev/docs/upstream/h2-goaway/findings.md:17` 引的是生产 traceback。

#### (f) `httpx2.ReadTimeout` / `httpx2.WriteError` / `httpx2.ConnectError` / `httpx2.LocalProtocolError` / `httpx2.ProtocolError`

- 全部 `isinstance(..., httpx2.TransportError)` → `normalize_upstream_error` 归为 `UpstreamError(f"upstream connection failed: {error}")` → `reason_for` 给 `network`（**本次实测**，见 2.1 表）
- `str()` 与链形态与 (d)/(e) 同族：由 httpcore2 原消息决定，可为空串（**推断**——这几种未在本次真实 socket 实验里复现出来，只测了构造版）
- `ConnectError` 在 body 阶段实际不太可能出现（连接已建立）——**推断**
- 注：httpx 的默认 timeout 配置下 `ReadTimeout` 会不会在 body 阶段抛，取决于 client 的 timeout 设置。**未查到**本项目给上游 client 配了什么 read timeout。

#### (g) `h2.exceptions.ProtocolError`（裸抛，`transport.py:31` 注释说的那个情形）—— **会到达**

- 完整类型名：`h2.exceptions.ProtocolError`（及其子类），继承 `h2.exceptions.H2Error` → `Exception`
- **会不会走到这里：会。**三条证据：
  1. **代码直读**：`httpcore2/_async/http2.py:401-431`，`_read_incoming_data` 的 `try/except` 只包住 `self._network_stream.read(...)`；`events = self._h2_state.receive_data(data)` 在 `try` 之外。
  2. **代码直读**：`httpx2/_transports/default.py:111-112`，`map_httpcore_exceptions` 对映射表里没有的异常执行裸 `raise`，不做包装。
  3. **代码直读**：`stream.py:341` 与 `stream.py:369` 的注释都明确点名「a bare `h2.ProtocolError`」是那个「taxonomy 无法命名、因而以前直接把客户端的回合带走」的异常；`stream.py:368` 的 `if not ours:` 就是为它开的门。
- `str()`：
  - 基类无参构造 → 空串（**本次实测**：`h2.exceptions.ProtocolError()` 的 `str()` 是 `''`）
  - GOAWAY 后再收 DATA 的真实形态（**既有实测**，`260820-h2-goaway-poc.md:74,166`）：`'Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED'`
  - ⚠️ **子类 `StreamClosedError` / `NoSuchStreamError` 的 `str()` 是一个裸数字**（**本次实测**）：
    ```
    StreamClosedError(3)   str='3'   args=(3,)
    NoSuchStreamError(3)   str='3'   args=(3,)
    ProtocolError()        str=''    args=()
    InvalidBodyLengthError(10,5)  str='InvalidBodyLengthError: Expected 10 bytes, received 5'
    ```
    它们的 `__init__` 只赋 `self.stream_id`、不调 `super().__init__`，但 `BaseException.__new__` 已经把构造参数填进 `args`，于是 `str()` 就是那个 stream id。**一个只写着 `3` 的 `input.message` 比空串更有害——它看起来像一条真消息。**
  - `InvalidBodyLengthError` / `StreamIDTooLowError` 自定义了 `__str__`，带信息（**代码直读**）
- **能否为空串：能（基类 `ProtocolError()` 即为空串）；更糟的是 `StreamClosedError` 会给出一个无意义的裸数字。**
- `__cause__` 链：**0 层**（裸抛，httpx2 不包装，h2 自身也不 chain）——**推断**，`260820-h2-goaway-poc.md:166` 的输出只给了类型与消息，没打链。
- `category` = **`internal`**（`normalize_upstream_error` 不认它 → `replay_reason` 返回 `None` → `hand_over.py:91` 落到 `ErrorCategory.INTERNAL`）。**这是一个把上游协议故障报成代理内部错误的已知形态**，`hand_over.py:82` 的注释讲的是另一半（分类一致性），并没有覆盖这一格。

#### (h) framing bug（`framer.block(...)` 抛出的任何异常）—— **会到达，且会被归给上游**

- `stream.py:279` 的注释自己承认：`from_assembly` 只覆盖 `assembler.push`，「A bug in framing would still be attributed to upstream — a known limit」（**代码直读**）
- `_commit` 里的 `framer.preamble()` / `framer.block(block)` 在同一个 `try` 内（`stream.py:301-309`），抛出的异常 `ours=False`，于是走 `stream.py:372` 的交接。
- 典型类型：`orjson` 序列化失败的 `TypeError`、`KeyError` 等。`str()` 形态不定，`KeyError` 的 `str()` 是带引号的键名（例如 `"'index'"`），`RuntimeError()` 可为空串。
- `category` = `internal`（`normalize_upstream_error` 不认）
- 证据等级：**代码直读 + 注释自述**；未实测触发。

#### (i) `finish_stream_cleanup` 抛出的 cleanup 异常

- `_events_with_ping` 的 `finally`（`stream.py:161-177`）在没有 primary 异常时会 `raise cleanup_error`，它来自关闭上游流（`keepalive.py:83-88`）。
- 类型同样落在 httpx2 传输异常族里（**推断**，未实测）。

### 2.3 `openai.APIConnectionError` 会不会走到这里 —— **不会**

三步论证，全部**代码直读**：

1. **body 阶段拿不到 SDK 异常。**交付链读的是 `response.aiter_bytes()`（`inference.py:445`、`:316`、`:388`），`response` 是 `httpx2.Response` 原件（`client.py:83-89` 的 `cast_to=httpx2.Response`；`driver.py:59` 的返回标注）。openai SDK 在这条路径上早已退栈。
2. **header 阶段的 SDK 异常在离开 `GhcApiClient` 之前就被剥掉了。**`_in_pipeline_terms`（`client.py:113-119`）对每个 send 方法做 `normalize_upstream_error`，`APIConnectionError ∈ _CONNECTION_ERRORS`（`errors.py:36`）→ 变成 `UpstreamError(f"upstream connection failed: {error}")`（`errors.py:122-124`）。`send_responses_headers` 另有一条 `ResponsesHeadersPendingTransportError` 包装（`client.py:190-194`）。
3. **header 阶段的失败根本不进交付。**`handle_bounded` 抛出的异常在 `inference.py:236-248` 被接住并直接 `return JSONResponse(...)`；此时交付生成器还没被构造出来。

补充：即便 `APIConnectionError` 假设性地到达，它的 `str()` 恒为 `'Connection error.'`（任务背景里已有实测），细节只在 `__cause__`——`transport.py:36-43` 就是专门走这条链的。

### 2.4 汇总表

| 类型 | 可达 | `str()` 典型值 | 可空串 | `__cause__` 层数 | `category` | 证据 |
|---|---|---|---|---|---|---|
| `app.streaming.idle_timeout.StreamIdleTimeoutError` | 是 | `No stream item received for 300s` | 否 | 2（`TimeoutError('')` → `CancelledError('')`） | `network` | 本次实测 |
| `app.streaming.deadline.StreamDeadlineError` | 是 | `attempt exceeded its deadline`（固定） | 否 | 2（同上） | `network` | 本次实测 |
| `app.streaming.deadline.ClientDeadlineError` | **否** | `client request exceeded its deadline` | 否 | 2 | — | 代码直读 |
| `httpx2.ReadError` | 是 | **`''`**（真实 RST） | **是** | 3（httpcore2 → anyio → `ConnectionResetError`） | `network` | 本次实测 |
| `httpx2.RemoteProtocolError`（h1 FIN） | 是 | `peer closed connection without sending complete message body (...)` | 否（观测） | 3（httpcore2 → h11） | `network` | 本次实测 |
| `httpx2.RemoteProtocolError`（h2 GOAWAY） | 是 | `<ConnectionTerminated error_code:0, last_stream_id:2147483647, ...>` | 否 | 2（httpcore2） | `network` | 既有实测 |
| `httpx2.RemoteProtocolError`（h2 断开） | 是 | `Server disconnected` | 否 | 2 | `network` | 代码直读 |
| `httpx2.ReadTimeout` / `WriteError` / `ConnectError` / `ProtocolError` / `LocalProtocolError` | 是（部分不太可能） | 由 httpcore2 原消息决定 | 是 | 2–3 | `network` | 推断 |
| `h2.exceptions.ProtocolError`（裸） | 是 | `Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED`；基类为 `''`；`StreamClosedError` 为裸数字 `'3'` | **是** | **0** | **`internal`** | 代码直读 + 既有实测 + 本次实测 |
| framing 层 bug（`TypeError`/`KeyError`/…） | 是 | 不定 | 是 | 不定 | `internal` | 代码直读 |
| `DeliveryError` / `BufferCapExceeded` | **否**（`ours`） | `buffered N bytes exceeds the M byte cap` | 否 | 0 | — | 代码直读 |
| `assembler.push` 抛出的一切 | **否**（`from_assembly`） | — | — | — | — | 代码直读 |

**对「改 `input.message`」最要紧的一条：`detail = str(error)` 在真实的连接重置（`httpx2.ReadError`）和裸 `h2.ProtocolError` 上都会产出空串**，而 `hand_over.py:92` 没有任何兜底。对照 `stream.py:387` 的 error frame 就有兜底：`message=str(torn) or torn.__class__.__name__`。**两处对同一个异常给出不同质量的描述，这是当前代码里可以直接指出的不一致。**

---

## 3. 非错误分支：`stop_reason` 的实际取值集合

### 3.1 配置默认值

- **`src/app/config/schema.py:155`**：`hand_over_stop_reasons: list[str] = Field(default_factory=lambda: ["max_tokens"])`（代码直读）
- 注入点：`src/app/server/routes/inference.py:274` `_hand_over_reasons = frozenset(chain.config.upstream_request_retry.hand_over_stop_reasons)`
- 交付层的独立默认：`stream.py:67` `stop_reasons: frozenset[str] = frozenset({"max_tokens"})`（只在没人注入时生效，生产路径总是被 `inference.py:425` 覆盖）
- ⚠️ **`docs/.human-controlled/config.example.yaml:339` 写的是 `["max_tokens", "max_output_tokens"]`**，其中 `max_output_tokens` **结构上永不匹配**——归一化发生在门之前。这是用户亲笔文档，已端给用户、用户明确保留（`.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md:210`），此处只作提示，不重提。

### 3.2 门的位置（代码直读）

- 流式：`stream.py:409` `terminal.stop_reason in continuation.stop_reasons`，随后 `stream.py:414` 把 `terminal.stop_reason` 原样传进 `synthesize`。
- 非流式：`inference.py:481` `str(payload.get("stop_reason", "")) in _hand_over_reasons`，随后 `inference.py:480` 原样传入。

**所以 `stop_reason` 的取值集合 = 配置集合 ∩ 归一化后真实可能出现的拼法。默认配置下只有一个值：`"max_tokens"`。**

### 3.3 归一化之后能出现的拼法（代码直读）

Responses 上游腿：

- `src/app/pipeline/delivery/formats/openai_responses.py:554-555`
  ```python
  self._terminal.stop_reason = (
      "max_tokens" if reason == "max_output_tokens" else reason or "incomplete"
  )
  ```
  即 `max_output_tokens` → `max_tokens`；上游给的其它 `incomplete_details.reason` 原样透出；没给就是 `"incomplete"`。
- `openai_responses.py:558`：正常完成时 `TOOL_USE`（`"tool_use"`）或 `"end_turn"`
- 非流式同一次归一：`src/app/pipeline/translation_driver/responses.py:125-126`

Anthropic-direct 上游腿：

- `src/app/pipeline/delivery/formats/anthropic_messages.py:350-352`：直接取 `message_delta` 的 `stop_reason`，不归一。Anthropic 的枚举是 `end_turn` / `max_tokens` / `stop_sequence` / `tool_use` / `pause_turn` / `refusal`（**推断**——项目源码里没有一处穷举这个枚举；`openai_responses.py:331` 的注释提到了 `stop_sequence` / `pause_turn` / `refusal`）。

### 3.4 已有的一手实测（既有实测）

`.dev/docs/upstream/retry-and-continuation/reports/260822-review-mcp-contract-and-deadline-order.md` 的 F6/F11：

- 把 `hand_over_stop_reasons` 配成 `{"content_filter"}` 时，`category` 实测原样透出 `content_filter`。
- **证伪对照**：配成 `{"max_output_tokens"}`（删掉 `max_tokens`）时，`synthesize` **一次都没被调用**——证明归一化在门之前。

### 3.5 结论

| 场景 | `stop_reason` 取值 |
|---|---|
| 默认配置 | 恒为 `"max_tokens"` |
| 运维把 `content_filter` 加进去 | 可为 `"content_filter"`（既有实测） |
| 运维加 `max_output_tokens` | 永不匹配，等于没加（既有实测证伪对照） |
| 运维加 `incomplete` | **推断**可匹配（`openai_responses.py:555` 的兜底值），未实测 |
| error 路径 | `stop_reason` 恒为 `""`（`stream.py:459` 的默认值），此时 `detail` 走 `str(error)` 而非 `stop_reason` |

---

## 4. 现有测试：哪些会因为改 `input.message` 变红

起手命令跑完的完整清单（代码直读 + 逐条打开确认）。

### 4.1 直接断言 `hand_back_block` 产出的 `input` 的测试

全部在 `tests/int/test_pipeline_app.py`。辅助函数 `_handed_back`（`:3084`）把交接块从 SSE 帧里重组回 `{"name", "id", "input"}`。

| 文件:行号 | 断言字面量 | 改 `message` 会红吗 |
|---|---|---|
| `tests/int/test_pipeline_app.py:987` | `handed["type"] == "tool_use"` | 否 |
| `tests/int/test_pipeline_app.py:988` | `handed["name"] == TOOL_NAME` | 否 |
| `tests/int/test_pipeline_app.py:989` | `handed["input"]["category"] == "max_tokens"` | 否 |
| `tests/int/test_pipeline_app.py:991` | `handed["input"]["num_messages"] == 3` | 否 |
| `tests/int/test_pipeline_app.py:3123` | `handed["name"] == TOOL_NAME` | 否 |
| `tests/int/test_pipeline_app.py:3124` | `handed["id"].startswith("toolu_")` | 否 |
| `tests/int/test_pipeline_app.py:3125` | `handed["input"]["category"] == "network"` | 否 |
| `tests/int/test_pipeline_app.py:3126` | `handed["input"]["num_messages"] == 0` | 否 |
| **`tests/int/test_pipeline_app.py:3127`** | **`assert handed["input"]["message"]`（只断真值）** | **只有在新值可能为空串 / 键被改名 / 键被删时才红** |
| `tests/int/test_pipeline_app.py:3190` | `handed["input"]["category"] == "max_tokens"` | 否 |
| `tests/int/test_pipeline_app.py:3311` | `handed["input"]["num_messages"] == 3` | 否 |
| `tests/int/test_pipeline_app.py:3312` | `handed["input"]["category"] == "network"` | 否 |

**结论：全仓没有任何测试断言 `input.message` 的具体字面量。唯一相关的是 `:3127` 的真值断言。**

该测试（`test_an_interrupted_turn_is_handed_back_to_the_client_as_a_tool_call`，`:3101`）用的上游是 `raise httpx2.RemoteProtocolError("peer closed the connection")`（`:3110`），即**手工构造、带消息**的版本——所以它今天是绿的。⚠️ 若把上游 fixture 换成真实的连接重置（`httpx2.ReadError('')`），这条断言**现在就会红**。这正是 `.claude/rules/00-development-workflow.md` 里那条「a hand-written stand-in encodes what we believe upstream does」的形状。

### 4.2 只断言交接发生、不看内容的测试

| 文件:行号 | 断言 | 触发的异常类型 |
|---|---|---|
| `tests/int/test_pipeline_app.py:2486` | `b"turn_interrupted" in delivered` | `StreamIdleTimeoutError` |
| `tests/int/test_pipeline_app.py:2538` | `b"turn_interrupted" in delivered` | `StreamDeadlineError` |
| `tests/int/test_pipeline_app.py:2609` | `b"turn_interrupted" in delivered` | `StreamDeadlineError` |
| `tests/int/test_pipeline_app.py:3263` | `b"turn_interrupted" not in delivered` | 上游已收尾后撕裂（负样本） |
| `tests/int/test_pipeline_app.py:3340` | `b"turn_interrupted" not in delivered` | 同上，翻译腿（负样本） |

全部不受 `message` 改动影响。

### 4.3 交付层单测（不经过 `hand_back_block`）

`tests/unit/pipeline/delivery/test_stream_delivery.py:1169` `test_a_failure_nobody_can_name_still_reaches_the_hand_over` —— 自己塞了一个假的 `synthesize`（`:1178`），断言它被调用过一次以及 `"carry_on" in body`。不受影响。

### 4.4 `hand_back_block` / `replay_reason` / `client_message_count` 的直接单测

**未查到——`tests/` 下没有任何文件引用这三个符号**（`rg -n "hand_back_block|replay_reason|client_message_count" tests` 无输出）。`src/app/pipeline/hand_over.py` 整个模块只有集成测试覆盖，没有单元测试。

### 4.5 与 `input.message` 相关的其它消费者

`.dev/docs` 里多处提到 MCP server 读 `category` 作为回复的键（`hand_over.py:82` 注释、`.dev/docs/upstream/retry-and-continuation/decisions.md` 4.1）。**未查到**任何仓库内代码或测试消费 `input.message` —— 它当前只是给人读的诊断串。跨仓（MCP server 在另一个仓库）的消费情况**未查到**。

---

## 5. 可直接据此行动的三条

1. **`hand_over.py:92` 的 `str(error)` 缺兜底，`stream.py:387` 有。**同一个 `httpx2.ReadError` 在 error frame 里会显示 `ReadError`，在 `input.message` 里是空串。（代码直读 + 本次实测）
2. **裸 `h2.ProtocolError` 的 `category` 是 `internal`，把上游协议故障报成了代理内部错误。**它同时也是最可能给出无用 `str()` 的一类——基类为空串，`StreamClosedError` 给出一个裸数字。（代码直读 + 既有实测 + 本次实测）
3. **`__cause__` 链是真正带信息的地方**：`httpx2.ReadError` 的第 3 层才是 `ConnectionResetError('[Errno 104] Connection reset by peer')`；两个 deadline 类的链反而全是空串，信息只在自己的 `str()` 里。项目里已有走链的先例——`transport.py:36-43`。（本次实测）
