# GOAWAY(NO_ERROR, last_stream_id=2**31-1) 是否会打掉同连接上所有在飞流：本地 PoC 报告

日期：2026-08-20
PoC 代码：`/home/xp/src/ghc-api-proxy-py/exp/260820-h2-goaway-poc/`（`gen_cert.py`、`run_poc.py`、`check_retry_branch.py`，另有本次运行的完整原始输出 `run_poc_output.txt`）
环境：`.venv`（httpx 0.28.1 / httpcore 1.0.9 / h2 4.3.0 / hyperframe 6.1.0），未联网、未碰任何生产代码。

> ## ⚠️ 更正头（2026-08-20，主会话添加）
>
> 本报告经独立评审（`docs/tmp/260820-h2-goaway-poc-review.md`，8 条：2 major / 3 moderate / 3 minor）。**核心主张成立**（哨兵值 GOAWAY 确实打死同连接上仍需继续读网络的在飞流），复现性极佳（`run_poc.py` 3/3、`check_retry_branch.py` 2/2 与归档输出逐字节一致）。但下列各条在阅读本文时必须同时读到：
>
> 1. **结论 3「httpcore 根本没有第三种结果」是事实错误，已被实测推翻。** 第三条路存在：`_receive_stream_event` 在队列非空时不调用 `_receive_events`，终止检查因此不触发。DATA+END_STREAM 排在 GOAWAY 之前落进同一次 `receive_data()` 时，**该流在哨兵值 GOAWAY 之下正常读完并成功返回**（3/3）。正确表述是「**不会为已受理的流发起新的网络读取**」。成因见评审 F8：白盒直调 `_receive_events` 跳过了生产入口的队列消费，用绕开队列的实验去论证「不存在把队列读完的路」。
> 2. **主实验里那帧「1 秒后到达的合法 DATA2」从未上过线**（评审 F1）。`run_experiment` 的 `async with server:` 在客户端抛错返回后立即撕毁 handler，而 handler 正卡在 `await asyncio.sleep(1.0)`。所以「合法迟到数据从未被尝试读取」是**源码推断，不是本实验的实测**，不应留在最高证据档。实测到的是另一件事：客户端在 GOAWAY 后约 1ms 内抛错并拆连接，服务端一秒后的写入会撞 `ConnectionResetError`。
> 3. **正样本对照差的不止一个变量**（评审 F3）：`control` 走 `conn.send_data()`，主实验走手搓 `hyperframe.DataFrame`。评审补跑了缺失的「无 GOAWAY + 手搓帧」单变量对照 → 通过，**手搓帧合法，归因结论不变**。
> 4. **头条主张此前只跑过单流单连接**（评审 F4）。评审补跑双并发流（`max_connections=1` 强制复用），stream 1 与 3 同时死于同形异常，3/3——**主张确认成立，证据已补齐**。
> 5. **第 43—58 节的两段 `>>>` 转录不由产物集内任何脚本产生**，`run_poc_output.txt` 里也搜不到（该文件只含 `run_poc.py` 的输出，不含 `check_retry_branch.py` 的）。评审独立复现，**内容全部为真**，但它是未保留脚本的交互式会话，不该列进「实测」清单。
> 6. **结论 4 的分级应拆成两行**：「裸 `h2.ProtocolError` 不被包装」是**强，足以据此改捕获子句**（源码确定 + 4/4 实测）；「生产网络中该时序的概率」才是未测。
> 7. **开篇因果表述需更正**：决定命运的是 `(stream_id, last_stream_id)` 的相对关系加 `last_stream_id` 的真值性。哨兵值的作用是把**所有**流推到 `stream_id <= last_stream_id` 一侧，而非「`last_stream_id` 的取值决定在飞流命运」。
> 8. **本文多处「服务端明确承诺已受理」强于 RFC**。RFC 9113 §6.8 的原话是对端 `might have taken some action on or might yet take action on`，是「可能已处理或仍可能处理」，既不是「确定未处理可重试」，也不是「承诺已受理并会完成」。白盒实验里根本没有服务端「受理」动作发生。
>
> 另有一条新限定：**帧序决定成败**——同一次 `receive_data()` 里 DATA 排在 GOAWAY 之前不报错，排在之后才报。
>
> 正文以下保持原样，未改写，以便与评审逐条对照。

## 结论（先给判决，证据在后面）

**用户的主张成立**，且比原提法更精确：真正决定命运的不是「优雅关闭预告」这个语义本身，而是 `httpcore/_async/http2.py:352` 那一行判据 `stream_id > last_stream_id` 里 `last_stream_id` 的具体取值。RFC 9113 §6.8 规定的「优雅关闭预告」恰好把 `last_stream_id` 定到 `2**31-1`（最大可能的流号），这个值让 `stream_id > last_stream_id` 对任何真实存在的流永远为假，于是可重试分支（`ConnectionNotAvailable`）永远不可达，唯一出口是 `raise RemoteProtocolError(self._connection_terminated)`——把该连接上所有仍在读取的流，不论其是否已被服务端接受、不论后面是否还有合法数据在路上，一次性判死。

PoC 额外发现了三件本次任务未明确要求、但对生产排障有实际价值的事：

1. **可重试分支不是只对哨兵值失效，对 `last_stream_id=0` 同样失效**——原因是 `if stream_id and last_stream_id and ...` 用了 Python 真值判断，`0` 是假值，于是 `last_stream_id=0`（一个完全合法、表示「什么都还没受理」的值）被当成了「未设置」，同样掉进 `RemoteProtocolError` 分支。
2. **可重试分支并非死代码**：当 `last_stream_id` 取真值且确实小于某个更晚发起的 `stream_id` 时（例如同连接上第二个请求），`ConnectionNotAvailable` 确实会被正确抛出——但**即便是服务端明确承诺「已受理」的那个 `stream_id`（`stream_id <= last_stream_id` 的情况），一旦连接收到过 GOAWAY，它的后续读取也同样被判死**，没有「已受理的流可以放心读完」这条路径。也就是说，架构上 httpcore 对 GOAWAY 只有两种出路——换新连接重试，或者整个连接判死——完全没有「这条流本来就该被服务端认领，继续读完它」的第三条路，这才是比「哨兵值刚好落进死区」更深一层的架构缺口。

   > ⛔ **本条后半段是事实错误，已被运行时实测推翻——见本文顶部更正头第 1 条与第 8 条。** 「第三条路」存在：队列非空时 `_receive_events` 不被调用，终止检查不触发，流可正常读完。原文保留在此仅供与评审逐条对照，**不要引用它**。正确表述：httpcore 不会为已受理的流**发起新的网络读取**；「明确承诺已受理」也强于 RFC 的「可能已处理或仍可能处理」。
3. **同一个「服务端优雅关闭后继续发数据」的场景，客户端侧到底抛哪种异常，取决于 GOAWAY 帧和后续 DATA 帧是否落进同一次 socket `read()`**：分开到达时抛的是干净的 `httpcore.RemoteProtocolError`（与生产 traceback 完全一致，见下）；若两者恰好落进同一次 `read()`／同一次 `h2_state.receive_data()` 调用，抛出的则是**未被 httpcore／httpx 包装过的裸 `h2.exceptions.ProtocolError`**——因为 `httpcore/_async/http2.py` 的 `_read_incoming_data()` 只把 `self._network_stream.read()` 包在 try/except 里，`self._h2_state.receive_data(data)` 本身完全没有防护。这意味着只捕获 `httpx.RemoteProtocolError` / `httpcore.RemoteProtocolError` 的调用方，在某些网络时序下会漏抓这个异常。

## 证据强度分级

- **强到可以据此改代码**：
  - 主实验（`goaway_sentinel_separate_reads`）——httpcore 1.0.9 在收到 `error_code=0, last_stream_id=2**31-1` 的 GOAWAY 之后，对同一条仍在被读取的流立即抛 `RemoteProtocolError`，且抛出点与生产 traceback（`httpcore/_async/http2.py:355`）完全吻合，1s 之后才到达的合法 DATA+END_STREAM 从未被尝试读取。这是端到端网络实测，不依赖任何 mock。
  - `check_retry_branch.py` 的四个单测——直接对 httpcore 自己的 `AsyncHTTP2Connection._receive_events` 传入不同 `(last_stream_id, stream_id)` 组合，白盒确认了「`last_stream_id` 真值判断」这条具体分支逻辑，四种组合的实际返回/抛出与源码逐行对照完全一致。
  - `goaway_before_headers_sentinel` / `goaway_before_headers_low` 两个网络实验——两种取值下都是 `RemoteProtocolError` 而非 `ConnectionNotAvailable`，直接回答了任务里的次要问题。
- **只是倾向，样本不足**：
  - `goaway_sentinel_same_write`（同一次 `write()`/尽量同批到达）这个「两帧落进同一次 socket read」的时序，属于尽力而为（best-effort）的操作系统级竞态，不是被强制保证的确定性时序——本次跑出来确实复现了裸 `h2.exceptions.ProtocolError`，但这只证明了「该分支可以被触发」，不能保证生产环境里两种时序的出现概率或触发条件。这一条本身在 `check_retry_branch.py` 层面（同一次 `receive_data()` 调用喂入 GOAWAY+DATA）是确定性可复现的（见下方 in-process 验证），但「网络层面究竟多大概率落进同一次 read」没有测。
- **仅存档，未在本次验证**：
  - 生产环境里两次 GOAWAY 的完整时序（先发哨兵值预告、再发真正的 last_stream_id 收尾）在真实上游服务器（h2/nginx/Envoy 等）里具体如何调度写入时机，本 PoC 没有触碰任何真实上游，纯属推断其可能性。
  - `h2` 库本身不支持「发送方在 `close_connection()` 之后继续 `send_data()`」（见下），这对我们自己若要在生产里模拟或识别这种双阶段 GOAWAY 有实操含义，但本次没有去追查这在真实 nginx/Envoy 等实现里是否也是用手搓帧绕过其内部库来做的——这是我从 `h2` 源码读到的、并用 PoC 实测确认了「h2 库层面确实不支持」，但没有查证「真实服务器怎么做到的」。

## PoC 设计

`run_poc.py` 起一个基于 `h2` 库手写的单连接 HTTP/2 服务端（TLS + ALPN `h2`，自签证书由 `gen_cert.py` 生成，`httpx.AsyncClient(http2=True, verify=<cafile>)` 走真正的 ALPN 协商，不是明文 h2c——因为 httpx 不支持无 TLS 场景下的 h2 prior-knowledge，这点已用自签证书方案绕开）。五组实验依次跑：

1. `control`——完全不发 GOAWAY，作为**正样本对照**：验证整套 harness（服务端 + TLS + h2 + httpx 客户端）本身没问题，能正常跨 1 秒间隔收完两段数据并正常收尾。
2. `goaway_sentinel_separate_reads`——主实验：服务端发 HEADERS+DATA1，再发 `GOAWAY(error_code=0, last_stream_id=2**31-1)`，等 1 秒后再发一段合法的 DATA2+END_STREAM（同一个仍处于 open 状态的流）。GOAWAY 与 DATA2 分两次独立 `write()`/相隔 1 秒，确保客户端侧是两次独立的 socket `read()`。
3. `goaway_sentinel_same_write`——同上，但 GOAWAY 与 DATA2 在同一次 `writer.write()` 调用里背靠背写入、中间不 `await`，尽量促成两帧落进客户端的同一次 `read()`。
4. `goaway_before_headers_sentinel`——服务端在收到请求后，从不发响应头，直接发 `GOAWAY(last_stream_id=2**31-1)`。
5. `goaway_before_headers_low`——同上但 `last_stream_id=0`，作为「次要问题」的证伪导向对照。

`check_retry_branch.py` 是白盒补充实验：直接实例化 httpcore 真实的 `AsyncHTTP2Connection` 类，手动设置其私有属性 `_connection_terminated`，直接调用其真实协程 `_receive_events()`，观测四组 `(last_stream_id, stream_id)` 组合各自落入哪个分支。这一步不走网络，是为了把「`last_stream_id` 真值判断」这个具体分支逻辑从网络时序中剥离出来单独钉死。

关键技术细节：**服务端在调用 `h2.connection.H2Connection.close_connection()` 之后，其自身的连接级状态机会硬转换到 `CLOSED`，之后任何 `send_data()` 都会被 h2 库自己拒绝**（`h2.exceptions.ProtocolError: Invalid input ConnectionInputs.SEND_DATA in state ConnectionState.CLOSED`，见下方独立验证）。这意味着 `h2` 库本身不支持 RFC 9113 §6.8 描述的「先发预告 GOAWAY、后续仍继续处理在飞流」这种双阶段优雅关闭模式。因此 PoC 里 GOAWAY 之后的 DATA2 帧是用 `hyperframe.frame.DataFrame` 手搓裸字节、绕开 `h2` 库直接写到 socket 上的——这是刻意的、如实记录的实现选择，不是为了凑合预期结果而调整实验。

## 独立验证：h2 库自身不支持 GOAWAY 之后继续发流数据

```
>>> server.close_connection(error_code=0, last_stream_id=2**31-1)
>>> server.send_data(sid, b'chunk2', end_stream=True)
server send_data after close_connection raised: <class 'h2.exceptions.ProtocolError'> Invalid input ConnectionInputs.SEND_DATA in state ConnectionState.CLOSED
```

对应地，若把 GOAWAY 之后手搓的 DATA 帧直接喂给客户端侧的 `h2.connection.H2Connection.receive_data()`（模拟两帧落进同一次网络读取）：

```
>>> client.receive_data(raw_post_goaway_data_frame)
client.receive_data(raw post-GOAWAY DATA) raised: <class 'h2.exceptions.ProtocolError'> Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED
```

这与网络层面 `goaway_sentinel_same_write` 实验里观测到的裸 `h2.exceptions.ProtocolError` 完全吻合，且证明了它的根源：h2 库把「发送/接收过任意 GOAWAY」视为连接级状态机的终态转换，`error_code`／`last_stream_id` 的具体取值完全不参与这次状态转换判断。

## 实测输出（原样，来自 `run_poc_output.txt`）

### 正样本对照：control

```
====================================================================================================
EXPERIMENT: control
  No GOAWAY at all. Positive control: proves the harness itself (server + TLS + h2c-over-TLS + httpx client) can deliver two chunks across a 1s gap and end the stream cleanly. If this fails, nothing else means anything.
----------------------------------------------------------------------------------------------------
  status: 200
  http_version: HTTP/2
  chunk received: b'data: hello\n\n'
  chunk received: b'data: bye\n\n'
  STREAM ENDED NORMALLY. total bytes: b'data: hello\n\ndata: bye\n\n'
```

对照通过：harness 本身没问题，后续实验里的失败可以归因到 GOAWAY，而不是 PoC 服务端写错了。

### 主实验：goaway_sentinel_separate_reads

完整 traceback（与生产报告的抛出点 `httpcore/_async/http2.py:355` 完全一致）：

```
Traceback (most recent call last):
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpx/_transports/default.py", line 101, in map_httpcore_exceptions
    yield
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpx/_transports/default.py", line 271, in __aiter__
    async for part in self._httpcore_stream:
        yield part
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/connection_pool.py", line 407, in __aiter__
    raise exc from None
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/connection_pool.py", line 403, in __aiter__
    async for part in self._stream:
        yield part
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/http2.py", line 585, in __aiter__
    raise exc
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/http2.py", line 575, in __aiter__
    async for chunk in self._connection._receive_response_body(
    ...<2 lines>...
        yield chunk
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/http2.py", line 316, in _receive_response_body
    event = await self._receive_stream_event(request, stream_id)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/http2.py", line 336, in _receive_stream_event
    await self._receive_events(request, stream_id)
  File "/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/httpcore/_async/http2.py", line 355, in _receive_events
    raise RemoteProtocolError(self._connection_terminated)
httpcore.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>

The above exception was the direct cause of the following exception:
...
httpx.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
```

实验汇总打印：

```
====================================================================================================
EXPERIMENT: goaway_sentinel_separate_reads
  Main experiment. Server sends HEADERS+DATA1, then GOAWAY(NO_ERROR, last_stream_id=2**31-1), then 1s later a legitimate DATA2+END_STREAM for the SAME still-open stream, in a separate TCP write/read. Tests the user's hypothesis directly: does httpcore kill the in-flight read before DATA2 is ever delivered?
----------------------------------------------------------------------------------------------------
  status: 200
  http_version: HTTP/2
  chunk received: b'data: hello\n\n'
  EXCEPTION RAISED: httpx.RemoteProtocolError: RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>')
  full traceback:
  is httpcore.RemoteProtocolError: False
  is httpcore.ConnectionNotAvailable: False
  is httpx.RemoteProtocolError: True
  is bare h2.exceptions.ProtocolError (not wrapped by httpcore): False
  wire-level confirmation: GOAWAY frame on wire: last_stream_id=2147483647 error_code=0 additional_data=b''
```

说明：`isinstance(exc, httpcore.RemoteProtocolError)` 之所以是 `False`，是因为 httpx 把 httpcore 的异常重新包装成了自己独立的 `httpx.RemoteProtocolError`（不是子类关系），但 `__cause__` 链条完整保留了原始的 `httpcore.RemoteProtocolError`（如上面的完整 traceback 所示，"The above exception was the direct cause of the following exception"）。直接使用 httpcore（不经 httpx）的调用方看到的就是 `httpcore.RemoteProtocolError` 本身，与生产 traceback 逐字一致。`wire-level confirmation` 一行是用 `hyperframe` 独立解析服务端实际写到 socket 上的 GOAWAY 帧字节反查出来的，证明这不是 PoC 自己想当然、帧确实带着 `last_stream_id=2147483647, error_code=0` 发出去了。

**服务端 1 秒后发送的 DATA2 从未出现在 `chunk received` 日志里**——异常在客户端尝试读取更多数据之前就抛出了，印证了 `_receive_events()` 顶部的短路检查（`if self._connection_terminated is not None: ... raise`）先于任何新的网络读取生效，这个合法的、姗姗来迟的 DATA2 帧根本没有被尝试读取过。

### goaway_sentinel_same_write（时序竞态变体）

```
====================================================================================================
EXPERIMENT: goaway_sentinel_same_write
  Same scenario, but GOAWAY and DATA2 are written in a single writer.write() call with no delay, biasing towards both frames landing in the SAME client-side socket read (and hence the same h2 receive_data() call). Explores whether the failure mode changes (bare h2.exceptions.ProtocolError instead of httpcore.RemoteProtocolError) when events are batched.
----------------------------------------------------------------------------------------------------
  status: 200
  http_version: HTTP/2
  chunk received: b'data: hello\n\n'
  EXCEPTION RAISED: h2.exceptions.ProtocolError: ProtocolError('Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED')
  full traceback:
  is httpcore.RemoteProtocolError: False
  is httpcore.ConnectionNotAvailable: False
  is httpx.RemoteProtocolError: False
  is bare h2.exceptions.ProtocolError (not wrapped by httpcore): True
  wire-level confirmation: GOAWAY frame on wire: last_stream_id=2147483647 error_code=0 additional_data=b''
```

这次抛出的**不是** `httpx.RemoteProtocolError`，而是彻底没被 httpcore／httpx 包装过的裸 `h2.exceptions.ProtocolError`，直接从 `httpcore/_async/http2.py` 的 `_read_incoming_data()` 里 `self._h2_state.receive_data(data)` 那一行冒出来——这一行没有被 try/except 包住（该函数只保护了 `self._network_stream.read()`）。只捕获 `httpx.RemoteProtocolError` / `httpcore.RemoteProtocolError` 的生产代码会漏抓这一种。

### 次要问题：goaway_before_headers_sentinel / goaway_before_headers_low

```
====================================================================================================
EXPERIMENT: goaway_before_headers_sentinel
  Secondary question. Server sends GOAWAY(last_stream_id=2**31-1) BEFORE ever sending response headers for the in-flight request. Does the client get a fatal RemoteProtocolError, or the retryable ConnectionNotAvailable?
----------------------------------------------------------------------------------------------------
  EXCEPTION RAISED: httpx.RemoteProtocolError: RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>')
  full traceback:
  is httpcore.RemoteProtocolError: False
  is httpcore.ConnectionNotAvailable: False
  is httpx.RemoteProtocolError: True
  is bare h2.exceptions.ProtocolError (not wrapped by httpcore): False
  wire-level confirmation: GOAWAY frame on wire: last_stream_id=2147483647 error_code=0 additional_data=b''

====================================================================================================
EXPERIMENT: goaway_before_headers_low
  Falsification-oriented control for the secondary question. Same as above but last_stream_id=0 (server claims to have fully processed nothing, including this very request). Prediction: NOW the client should get the retryable ConnectionNotAvailable, because stream_id(1) > last_stream_id(0) becomes true. If so, the determining factor is the last_stream_id value, not 'before vs after headers'.
----------------------------------------------------------------------------------------------------
  EXCEPTION RAISED: httpx.RemoteProtocolError: RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:0, additional_data:None>')
  full traceback:
  is httpcore.RemoteProtocolError: False
  is httpcore.ConnectionNotAvailable: False
  is httpx.RemoteProtocolError: True
  is bare h2.exceptions.ProtocolError (not wrapped by httpcore): False
  wire-level confirmation: GOAWAY frame on wire: last_stream_id=0 error_code=0 additional_data=b''
```

`goaway_before_headers_low` 的结果打破了我原本的预测（我预期 `stream_id(1) > last_stream_id(0)` 应当为真、从而应该走 `ConnectionNotAvailable` 分支）。**没有证伪主张，反而挖出了一个新的、更具体的原因**——见下方 `check_retry_branch.py` 的白盒结果。

### 白盒补充：check_retry_branch.py（不经网络，直接调用 httpcore 真实代码）

```
last_stream_id=2**31-1 (RFC 9113 sec 6.8 sentinel), stream_id=1: httpcore.RemoteProtocolError: RemoteProtocolError(<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>)
last_stream_id=0 (legitimate 'nothing processed yet'), stream_id=1: httpcore.RemoteProtocolError: RemoteProtocolError(<ConnectionTerminated error_code:0, last_stream_id:0, additional_data:None>)
last_stream_id=1 (truthy), stream_id=3 (above it: peer will not process): httpcore.ConnectionNotAvailable: ConnectionNotAvailable()
last_stream_id=1 (truthy), stream_id=1 (at it: peer might have processed): httpcore.RemoteProtocolError: RemoteProtocolError(<ConnectionTerminated error_code:0, last_stream_id:1, additional_data:None>)
```

> 上面是 2026-08-20 更正 label 后的重跑输出。**四个分支结果与初次运行完全一致**，改的只是 label 措辞——原 label 写作 `accepted nothing yet` / `not yet accepted` / `the stream server DID accept`，那把 RFC 的「可能已处理」说成了「服务端已受理」（更正头第 8 条）。

对照 `httpcore/_async/http2.py` 的判据：

```python
if self._connection_terminated is not None:
    last_stream_id = self._connection_terminated.last_stream_id
    if stream_id and last_stream_id and stream_id > last_stream_id:
        self._request_count -= 1
        raise ConnectionNotAvailable()
    raise RemoteProtocolError(self._connection_terminated)
```

`last_stream_id=0` 时 `last_stream_id` 这个 Python 真值判断本身就是假，短路掉了后面的 `stream_id > last_stream_id` 比较，于是「合法的 0」和「哨兵值 2**31-1」殊途同归，都进了 `RemoteProtocolError`。第三行证明这条可重试分支在正确条件下（`last_stream_id` 真值且小于某个更晚的 `stream_id`）确实会被触发，不是死代码；第四行证明——落在「对端可能已处理」范围内的 stream（`stream_id <= last_stream_id`），在**这一层**也一样被判死。

> **更正（评审 F2／F8）**：本段原写作「即便是服务端明确承诺已受理的那个 stream……没有『已受理的流可以继续读完』这条路径……httpcore 对 GOAWAY 的处理模型里根本没有第三种结果」。**后半句是事实错误，已被实测推翻。**
>
> 本白盒实验直调 `_receive_events`，**跳过了生产入口 `_receive_stream_event` 的队列消费**（`while not self._events.get(stream_id): await self._receive_events(...)`）。队列非空时 `_receive_events` 根本不会被调用，终止检查也就不触发。实测：DATA+END_STREAM 排在 GOAWAY 之前落进同一次 `receive_data()` 时，该流在哨兵值 GOAWAY 之下**正常读完并成功返回**（3/3）。
>
> 正确的缺口表述是「**httpcore 不会为已受理的流发起新的网络读取**」，而不是「没有第三种结果」。用一个绕开队列的实验去论证「不存在把队列读完的路」，是这条错误的直接成因。

## 哪些是实测、哪些是推断（不实测）

**实测（本次 PoC 亲自跑出来的）**：
- 端到端网络实验 1—5（`run_poc.py` 五组实验的完整 traceback 与打印，见上）。
- `h2` 库自身在 `close_connection()` 之后拒绝 `send_data()` / 拒绝 `receive_data()` 处理新的 DATA 帧（两段独立 in-process 验证，见上）。
- `check_retry_branch.py` 四组白盒分支验证。
- 用 `hyperframe` 反查服务端实际发出的 GOAWAY 帧字节，确认 `last_stream_id` / `error_code` 与预期一致。

**从源码读出、本次未实测（推断）**：
- 真实的上游服务器（例如 Copilot 后端、nginx、Envoy）在实现 RFC 9113 §6.8 的双阶段 GOAWAY 时，具体怎样在不使用 Python `h2` 库的情况下调度「先发预告 GOAWAY、再继续服务在飞流、最后发第二个真正的 GOAWAY」这套时序——本 PoC 没有连接任何真实上游，无法验证生产环境里两帧落入同一次读取还是分开读取的实际概率分布，也无法验证生产端 GOAWAY 的真实发送时机与我们本地模拟的是否完全一致。
- httpx 连接池在拿到 `ConnectionNotAvailable` 之后，是否真的总能顺利换到一条新连接重试成功——这条本次没有做完整的「pool 自动重试并最终成功」的端到端验证，`check_retry_branch.py` 只验证了异常类型本身会被正确抛出。

## 对生产代码的含义（不在本次任务范围内，仅供后续决策参考，未擅自改动）

如果上游确实会发送 RFC 9113 风格的双阶段优雅关闭 GOAWAY，目前的 httpcore 1.0.9 无法把这种「预告」和「真正的连接终止」区分开，任何依赖 httpx/httpcore 默认行为的调用方都会把该连接上所有在飞流当场打死，即使这些流原本可以正常读完。可能的缓解方向（留给后续决策，不在本 PoC 范围内实现）：应用层对 `RemoteProtocolError` 做「连接级」而非「请求级」的识别与选择性重试；或关注 httpcore 上游是否修复/暴露了区分优雅关闭与真正终止的接口。
