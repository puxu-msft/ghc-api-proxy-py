# 上游 GOAWAY 打掉在飞流式请求：诊断

日期：2026-08-20
触发：生产日志中四条流式请求在同一秒集体 `[FAIL]`，异常为 `httpcore.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647>`

状态：**直接触发机制已定位并经端到端 PoC 实测确认；生产对端在 GOAWAY 之后的实际行为未观测。**

相关文档：
- PoC 实测：`docs/tmp/260820-h2-goaway-poc.md`，代码 `exp/260820-h2-goaway-poc/`
- 主报告评审：`docs/tmp/260820-h2-goaway-review.md`（第一轮 8 条）、`docs/tmp/260820-h2-goaway-review-round2.md`（复评 7 条）
- PoC 评审：`docs/tmp/260820-h2-goaway-poc-review.md`（8 条，含 2 条 major；**推翻了本文原「没有第三条路」的结论**）

> **修订记录**：本报告经三轮独立评审、共 23 条发现，全部采纳。
>
> - 第一轮（8 条）收窄了四处过强表述：「上游行为正确、在飞流明确不受影响」「四条请求共用同一条连接」「请求 3、4 下游零字节」「重试是幂等的」。
> - 第二轮复评（7 条）发现我**在修第一轮问题的过程中又引入了同型错误**（把 `stream_id <= last_stream_id` 写成「服务端明确承诺已受理」），并纠正了行号基线与两处证据虚增。
> - PoC 评审（8 条）**推翻了一条事实结论**：第三条路存在（见第三节的事实更正），并补齐了两组缺失的对照实验。
>
> 这三轮的共同模式值得记下：每一轮都在把未观测的东西说成已确认。详见 `review-round2.md` 末尾。

> **行号基线**：本文的 `file:line` 引用初次核对于 **reviewed-source commit `8870385`**。`8870385` **不在当前 main 的历史上**——二者从 `9110518` 分叉，同主题内容以 squash commit `b822b45` 进入 main，没有任何 ref 包含 `8870385`。初稿曾把这写成「main 从 `8870385` 推进到 `7fa71f3`」，**那是错的**。
>
> 调查期间 main 持续前进（`7fa71f3` → `820f299` → `fd16e5f`），行号随之漂移。为免声称两个不同提交共用同一行号，本文正文优先引用**符号名与关键语句**；确需行号处以 `fd16e5f` 为准并已重新定位。

---

## 一、现象的时间学：四条请求死于一个共同事件，而非各自出错

| 请求 | 耗时 | 推算起始（近似） | ↑ 上行 | ↓ 上游回传 |
|---|---|---|---|---|
| 1 | 5.8s | ≈15:01:53 | 1.7MB | 2.1KB |
| 2 | 12.6s | ≈15:01:46 | 1.3MB | 5.9KB |
| 3 | 5.3s | ≈15:01:54 | 386.0KB | 595B |
| 4 | 15.9s | ≈15:01:43 | 329.5KB | 593B |

四个互不相同的起始时刻散布在约 10 秒窗口里，却收敛到同一个结束秒，且四者拿到的是**形状完全相同**的 `ConnectionTerminated`。这强烈支持一个共同的连接层或上游基础设施事件，不支持四次彼此独立的随机故障。

（日志只有秒级结束时间、耗时只有一位小数，所以起始时刻是近似值。）

**但「共同事件」不等于「同一条 TCP/H2 连接」。** 以下解释与现有证据同等相容，日志里没有 connection id，无从区分：

1. 四条流在同一条 H2 连接上收到同一帧 GOAWAY；
2. 四条流分布在多条 H2 连接上，同一边缘节点／负载均衡器／滚动更新同时向它们发送相同 GOAWAY；
3. 中间 TLS 终止节点而非源站应用发送了 GOAWAY；
4. 我方某个全局动作间接触发了对端关闭（异常类型使纯本地 timeout／cancel 不是首选解释，但仅凭结束秒不能排除）。

httpcore 通常把同 origin 请求复用到已有 H2 连接，这让解释 1 显得自然；但旧连接进入不可用状态而仍有在飞流时，**新旧连接可以并存**，而这四条请求起始时间横跨约十秒，跨连接 generation 无法排除。

> 初稿曾用「↓593B 说明远未触及流数上限」来支撑单连接归因。**这条论证是错的**：传输字节数与 `MAX_CONCURRENT_STREAMS` 计数毫无关系。已删除。

## 二、`error_code:0, last_stream_id:2147483647` 的准确语义

这个字段组合与 RFC 9113 §6.8 推荐的 graceful-shutdown **首帧**形状一致：

```text
A server that is attempting to gracefully shut down a connection SHOULD
send an initial GOAWAY frame with the last stream identifier set to
2^31-1 and a NO_ERROR code.
```

它的作用是禁止再开新流，并把所有合法 stream id 纳入「发送方可能已经处理、或仍可能处理」的范围。关于在飞流，RFC 的原话是：

```text
Activity on streams numbered lower than or equal to the last stream
identifier might still complete successfully. The sender of a GOAWAY
frame might gracefully shut down a connection by sending a GOAWAY
frame, maintaining the connection in an "open" state until all in-
progress streams complete.
```

是 **`might still complete successfully`**——可能继续成功，**不是保证跑完**；「保持连接直到所有流完成」同样是 `might` 描述的可选行为。

两点精确化：

- `2^31-1` **不是**「大于任何可能的 stream id」，而是**等于**合法 31-bit stream identifier 的最大值（hyper-h2 的 `HIGHEST_ALLOWED_STREAM_ID` 实测为 `2147483647`）。这不影响「`stream_id > last_stream_id` 恒假」的结论，但措辞必须准。
- **不能据此认定「上游无过」。** 我方的栈在看到该帧之后立即停止了后续网络读取，所以现有日志根本无法告诉我们：对端随后本来会继续传输，还是也会关闭连接。这一半事实是**未观测**，不是已排除。

能确凿认定的只有：**当前 httpcore／hyper-h2 栈对该帧的处理，足以单独造成观测到的失败。**

上游为什么在这一刻回收连接——连接寿命上限、边缘节点滚动更新、负载再平衡都是候选，从客户端侧无从判定。**仅存档，不支撑任何针对上游的结论。**

## 三、直接触发机制：栈不会为这类流发起新的网络读取

`httpcore` 1.0.9，`_async/http2.py:348-355`：

```python
async with self._read_lock:
    if self._connection_terminated is not None:
        last_stream_id = self._connection_terminated.last_stream_id
        if stream_id and last_stream_id and stream_id > last_stream_id:
            self._request_count -= 1
            raise ConnectionNotAvailable()
        raise RemoteProtocolError(self._connection_terminated)
```

`error_code` 的值在这段代码里从头到尾没有被读过（全文件仅在 line 351 读 `last_stream_id`），所以 `NO_ERROR` 和真正的协议错误走完全相同的路径。

### 白盒实测：四组组合

PoC 直接调 httpcore 真实的 `_receive_events`，传入不同 `(last_stream_id, stream_id)`：

| `last_stream_id` | `stream_id` | 实际结果 |
|---|---|---|
| `2**31-1`（RFC 哨兵） | 1 | `RemoteProtocolError` |
| `0`（合法的「一条都没受理」） | 1 | `RemoteProtocolError` |
| `1` | 3（更晚发起，落在「对端不会处理」的范围） | `ConnectionNotAvailable` ✅ 可重试 |
| `1` | 1（**落在「对端可能已处理或仍可能处理」的范围**） | `RemoteProtocolError` |

三个结论：

1. **`last_stream_id=0` 也失效，原因还不一样**——`if stream_id and last_stream_id and ...` 用的是 Python 真值判断，`0` 是假值，短路掉了后面的比较。于是一个完全合法、语义明确的「我一条都没受理」（本该是最该重试的情形）被当成了「未设置」。这是独立于哨兵值的第二条失效路径。
2. **可重试分支不是死代码**——第三行证明它在正确条件下确实触发。问题不是「这段代码没用」，是「它覆盖不到该覆盖的情形」。
3. **第四行最关键**：`stream_id <= last_stream_id` 的流——RFC 说这些流对端**可能已经处理、或仍可能处理**，并且**可能继续成功**——后续读取一样被判死。

> **措辞更正**：本节初稿把 `stream_id <= last_stream_id` 写成「服务端明确承诺已受理」，这**强于 RFC**。RFC 9113 §6.8 的原话是 last stream identifier 标出的是对端 `might have taken some action on or might yet take action on` 的最高流号，`All streams up to and including the identified stream might have been processed in some way`。所以它既不能被客户端当作「确定未处理、可无条件重试」，也不是对端「承诺已受理并会完成」。白盒实验里更没有任何服务端「受理」动作发生——它只是直接设置了 `_connection_terminated` 再观察分支。分支实验结果本身不受影响，被更正的是对它的解读。

第 3 条说明的是：**httpcore 不会为这类流发起新的网络读取**——它要么换连接重试，要么在下一次进入 `_receive_events` 时判死。

> **事实更正（PoC 评审实测推翻）**：初稿在此写「httpcore 对 GOAWAY 只有两种出路，**没有第三条路**」。**这是错的，第三条路存在，且已被运行时实测到。**
>
> `_receive_stream_event` 的结构是 `while not self._events.get(stream_id): await self._receive_events(...)`——**队列非空时 `_receive_events` 根本不会被调用**，终止检查也就不触发。而 h2 在同一次 `receive_data()` 里按帧顺序处理，DATA 排在 GOAWAY **之前**时不报错，产出 `['DataReceived', 'StreamEnded', 'ConnectionTerminated']`。
>
> 评审端到端实测（服务端把 DATA2+END_STREAM 写在 GOAWAY 之前，3/3 一致）：**该流在收到哨兵值 GOAWAY 的同一条连接上正常读完并成功返回，一个异常都没抛。** 边界也测了——DATA2 不带 END_STREAM 时，已排队的 chunk 照常交付，然后才在下一次进入 `_receive_events` 时判死。
>
> 所以架构缺口的正确表述是「**不会为已受理的流发起新的网络读取**」，而不是「没有第三种结果」。哨兵值的作用也要重述：它把**所有**流都推到 `stream_id <= last_stream_id` 一侧，从而让唯一的可重试出口对全体在飞流不可达——`last_stream_id` 的取值决定不了在飞流的命运，只决定比它更晚的流能否走到可重试分支。

### 不止 httpcore：hyper-h2 同样把连接状态置 CLOSED

评审与 PoC 从两个方向确认了同一件事——**独立评审读 hyper-h2 状态机源码核对，PoC 运行时实测**：hyper-h2 4.3.0 在 `RECV_GOAWAY` 时把 `CLIENT_OPEN` 转成 `ConnectionState.CLOSED`，而 closed 状态没有 `RECV_DATA`／`RECV_HEADERS`／`RECV_WINDOW_UPDATE` 等 transition。PoC 实测的报错：

```text
h2.exceptions.ProtocolError: Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED
```

所以**即使删掉 httpcore 的提前抛错，后续帧仍会由 hyper-h2 报错**。这是 **httpcore/hyper-h2 集成栈**的问题，不是改一处条件就能修的。

（附带：h2 库在 `close_connection()` 之后同样拒绝 `send_data()`，所以它自身也不支持 RFC 描述的双阶段优雅关闭。PoC 里 GOAWAY 之后的 DATA 帧是用 `hyperframe` 手搓裸字节绕开 h2 库写出去的——这是刻意的、如实记录的实现选择。）

### 一个必要的限定：不是「全部」在飞流

`_receive_stream_event` 先消费 `self._events[stream_id]` 里已排队的事件，只有队列为空才调用 `_receive_events`。同一次 socket read 可以同时产生某流的 `DataReceived`／`StreamEnded` 和 `ConnectionTerminated`。

所以准确说法是：**收到 GOAWAY 后，任何还需要再次进行网络读取的流都会在 `_receive_events` 入口抛错**；同一次 read 已把 `StreamEnded` 等完整终止事件排入队列的流可能正常完成。

同理，`ConnectionNotAvailable` 也不是无条件自动恢复：连接池只在 `handle_async_request` **尚未返回 Response** 时捕获它（`connection_pool.py:234-245`）。Response 已返回后，body 迭代中的该异常会向上抛，不会由 pool 重发请求。

## 四、爆炸半径与那个不好找的开关

HTTP/2 多路复用意味着同一 origin 的并发请求跑在同一条 TCP 连接的不同 stream 上。若解释 1 成立，连接死则全部死。

活跃链路的客户端是 `server/composition.py:74-79` 的 `build_http_client`。标准 CLI 入口 `ghc-api-proxy = app.cli:main` 经 `build_http_client` → `build_chain` → `create_pipeline_app` 走真实 pipeline；生产 traceback 里出现 `server/pipeline_app.py` 与此相符。`app_factory.py`／`upstream/client.py:create_http_client` 属于另一条 legacy surface。（此项经评审独立核对。）

需要单独指出的配置耦合（`composition.py:70`）：

```python
http2=transport.http2_ping_interval > 0,
```

活跃链路上决定「是否启用 HTTP/2」的开关是 `upstream_transport.http2_ping_interval`（默认 15），**不是** `UpstreamConfig.http2`——后者只控制 legacy 路径。一个名为「ping 间隔」的键兼职当「启用 h2」开关，在需要临时降级 HTTP/1.1 时会让人找错地方。这是调查副产品，与根因无关，但决定了处置建议 C 是否可操作。

## 五、四道关口逐一失守

### 1. 上游重试判据不覆盖协议错误

`ghc_client/transport.py:4-8`：

```python
_RESPONSES_PRE_HEADERS_HTTPX_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)
```

`httpx.RemoteProtocolError`（MRO：`RemoteProtocolError → ProtocolError → TransportError → RequestError`）不在其中。

本项目自定义类 `ResponsesHeadersPendingTransportError` 的 docstring 写的是「响应头到达之前的传输失败……可以安全重试，因为还没有产生任何客户端可见的响应字节」。按这个判据，headers 之前的 GOAWAY 符合定义却漏网。这是**相邻的独立缺口**——本次四个请求都已拿到 200 头，走的不是这条路。

（注意 `httpx.RemoteProtocolError` 自身的 docstring 只是 "The protocol was violated by the server."，上面引的是我们自己的类。）

### 2. headers 已提交后不重试——这一层是正确的

`executor.py:300` 的 `retryable_transport` 只覆盖 headers-pending。**不是缺陷。**

### 3. 块级缓冲窗口：可能存在，但本次未观测

`synthesized_response_headers_after_sec` 默认 240s，本次请求 5.3–15.9s 就失败，合成 `message_start` 的 timer **确定未触发**。

但**不能**据此断定下游零字节。`buffering_policy=block` 不是「响应结束前全缓冲」，而是**每形成一个完整 block 就立即释放**（`delivery/blocks.py:97-101`）。593B 是上游累计网络字节，一个很短的 text block 或 tool block 完全可能在这个体积内完成；也可能连一个事件都没完整到达。**没有下游发送计数或原始 SSE，无法区分。**

> 初稿断言请求 3、4「下游一个 body 字节都没发出去」。**这条降级为未决。** 它原本是「块级缓冲给了我们一个 HTTP 层看不见的重试窗口」这一论点的支柱，所以那个论点现在也只能是条件式的：**若**某请求在失败时确实尚未提交任何 body 字节，**则**存在一个对客户端不可见的重试窗口。窗口是否敞开必须逐请求判断，不是常量。

顺带确认：`streaming/buffered_retry.py` 与 `delayed_commit.py` **只被 `tests/unit/test_streaming_resilience.py` 引用，生产链路无人调用**——孤儿模块，不是可用的守卫。

但它们的能力也被初稿夸大了。二者实际只提供 `collect_with_limit(stream, cap_bytes) -> bytes` 和 `delayed_first_item(stream, timeout) -> (first_item, stream)`，**没有**重建上游请求、判断上游是否已处理、追踪下游已提交字节、丢弃失败 attempt 的 assembler 状态、重新初始化 converter／accounting 等关键能力。`collect_with_limit` 甚至会收完整个流，与「仅在首个完整 block 前重试」不是同一机制。**它们可能提供局部构件，不足以直接接出块级透明重试。**（不建议删除——参见「不得擅自删除已实现的功能」。）

### 4. 撕裂后没有 SSE `error` 事件，异常裸奔出 ASGI

异常从 `stream_delivery` 的 `async for` 上抛，穿过 `_tracked_delivery`（其 `except Exception` 记下 `accounting.failure` 后 `raise`）和 `StreamingResponse`，最终由 uvicorn 打印 `Exception in ASGI application`。

`_StreamAccounting._ending()` 工作正常——那行 `[FAIL] ... stream failed before a terminal event: ...` 是它写的，信息准确。**但客户端拿到的是一个无终止事件、无 error 事件的截断 SSE 流。**

这是 `pipeline/delivery/stream.py:173-177` 已登记的 STR-04 缺口的另一半：那段注释登记的是「干净 EOF 走了正常 flush，把截断伪装成成功」，这里是「撕裂路径连 flush 都没走到，直接裸奔出框架」。日志里那一大段 traceback 不是新 bug，是这个已知缺口的可见症状。

### 5. 某些时序下异常根本不是 httpx 类型（PoC 附带发现）

PoC 构造了两个本地场景，说明 GOAWAY 帧与后续 DATA 帧**是否落进同一次 `h2_state.receive_data()`** 会改变客户端看到的异常类型：

- GOAWAY 到达后、后续 DATA 尚未发送 → 下一次读取得到干净的 `httpcore.RemoteProtocolError`，抛出点与生产 traceback 一致。
- 二者在同一次 `receive_data()` 中处理 → **未被包装的裸 `h2.exceptions.ProtocolError`**。因为 `_read_incoming_data()` 只把 `self._network_stream.read()` 包在 try/except 里，紧随其后的 `self._h2_state.receive_data(data)` 完全没有防护。

> **不要把它写成生产的 wire 时序。** 生产 traceback 只证明我方栈在收到 GOAWAY 后、于后续一次 `_receive_events` 入口抛了 `RemoteProtocolError`。它**不能**证明对端在 GOAWAY 之后还发送过 DATA，更不能还原 GOAWAY 之后的具体帧时序——这与第二节「对端后续行为未观测」是同一条限制。初稿把分开到达的变体称作「本次生产故障的形态」，与那条限定自相矛盾，已删。上面的二分适用于该 PoC 场景，不是对所有 GOAWAY 场景的无条件断言。

**对我们仍然有直接含义**：本项目的传输错误判据是 httpx 类型的，而裸 `h2.exceptions.ProtocolError` 不是 `httpx.TransportError`，httpx 的 `map_httpcore_exceptions` 也不映射它（未知异常原样穿过）。

而且问题比「判据没覆盖」更靠前一层——**捕获边界就拦不住它**（`ghc_client/client.py`）：

```python
except (httpx.TransportError, OpenAIAPIConnectionError) as error:
    if is_responses_headers_pending_transport_error(error):
        raise ResponsesHeadersPendingTransportError(error) from error
    raise
```

裸 `h2.exceptions.ProtocolError` 两个类型都不是，所以**只改 `transport.py` 的判据元组不会让判据被调用到**。要处理它必须先改捕获边界。

证据强度：机制确凿；该时序是操作系统级竞态，PoC 层面「能被触发」确定性可复现，但**生产中出现概率没有测**。

## 六、读这份 traceback 的一个坑

栈里若干帧的**行号与磁盘源码对不上**：

| traceback 声称 | 磁盘现状 |
|---|---|
| `adapter.py:323 in gated_app` | `gated_app` 在 369 行 |
| `pipeline_app.py:370 in __call__` | `__call__` 在 391 行 |
| `pipeline_app.py:404 in _tracked_delivery` | `_tracked_delivery` 在 421 行 |

机制（已核对 CPython 3.14 的 `traceback.StackSummary` / `linecache`）：帧名与行号来自**运行中的 code object**，而打印出来的源码文本是**格式化 traceback 时才由 `linecache` 去磁盘读的**。

实践含义：**帧名可信，打印出来的代码文本不可信**——那是拿旧行号去新文件里取的，属于错位。别照着读。

关于成因要说窄一点。多处 function name 与当前磁盘行范围不相容，**确凿**证明「执行中的 code object 与格式化时的磁盘源码不是同一版」。「长驻进程启动后工作树推进」是结合本项目开发方式的**强解释，但不是唯一解释**——动态 `compile(..., filename=...)`、非原子部署／bind mount 切换、异常的 `.pyc` 复用都能产生同样现象，且行号本身无法确定具体 commit。

`keepalive.py:126` 与 `stream.py:133` 三者自洽、文件 clean，所以最吃重的两帧可继续作为分析依据——但这只说明**没有观测到矛盾**，不能反向证明运行 code object 与当前文件逐字一致（旧版本可能在这些行恰好相同）。

另外：`keepalive.py:126 _cancel_and_observe → await pending` 出现在栈底，**不代表 keepalive 是故障源**。它是清理路径：上游拉取任务带着 `RemoteProtocolError` 结束，`_cancel_and_observe` 在此观测到，由 `finish_stream_cleanup` 按既定优先级重抛。这段代码行为正确，只是异常被观测到的地方。

## 七、可选处置

**均未实施，需用户裁决。**

### A. 把 GOAWAY 类错误纳入 headers-pending 重试判据

现状：`transport.py:4-8` 的元组不含 `RemoteProtocolError`。

**但不要简单地把整个 `RemoteProtocolError` 加进去。** 「客户端尚未看见响应」只说明重试对下游**可隐藏**，**不说明第一次 POST 未被上游处理**——`RemoteProtocolError` 可以在请求已完整发出、上游已经执行甚至已开始生成之后发生。重发意味着接受 at-least-once 语义与**重复计费**的可能。

更窄的做法：按异常 cause 里的 `ConnectionTerminated` 字段做裁决，而不是把所有协议错误一概视为低风险。

至于裸 `h2.exceptions.ProtocolError`（见五.5），**不要简单地把这个类型也加进判据元组**，两个理由：

1. 它连捕获边界都进不去（`client.py` 捕的是 `httpx.TransportError` 与 `OpenAIAPIConnectionError`），只改元组不会让判据被调用；要处理必须先在合适的 transport boundary 归一化。
2. `h2.exceptions.ProtocolError` 是**宽类型**，它同样表示其它协议状态机错误。整类纳入可重试集合会重演上面 F4 的错误——异常类型本身既不证明第一次 POST 未被上游处理，也不证明适合重试。真要做就按具体 GOAWAY 状态／异常内容加请求阶段做窄匹配。

代价：1.7MB 上行会重发。**这不修复本次故障**（本次在 headers 之后），修的是相邻缺口。

### B. 在块级缓冲窗口内做一次上游重试

收益最大也最贵，且**前提未验证**（见五.3——「失败时下游零字节」当前是未决）。要落地需要先有「下游是否已提交过 body 字节」的可靠判据。孤儿模块提供的构件远不够（见五.3）。

会引入真实新失败面：重试期间的下游超时、重复计费、上行重发的内存与带宽。**不建议在没有明确需求裁决的情况下自行展开。**

### C. 降级 HTTP/1.1，缩小爆炸半径

设 `upstream_transport.http2_ping_interval: 0`（见第四节；配置路径经评审核对无误）。纯配置动作，可先做实验观察，不需改代码。

代价：连接数上升、TLS 握手增多。收益取决于回收的是「单条连接」还是「边缘节点的全部连接」——**前者 H1 能有效隔离，后者不能**，而当前证据不足以区分（见第一节的四种解释）。所以这条建议带着一个未验证的前提。

### D. 撕裂时补发 Anthropic SSE `error` 事件（STR-04）

让客户端拿到确定错误而非静默截断，同时止住 ASGI 异常刷屏。属已登记 slice，不是新工作项。

### E. 向上游库上报

`error_code == 0` 的优雅关闭预告不应判死「RFC 允许其继续成功」的在飞流。**上报内容须同时覆盖 httpcore 的提前抛错与 hyper-h2 的 `RECV_GOAWAY → CLOSED` 状态转换**——只报 httpcore 会让对方以为改一处条件即可（见第三节）。不阻塞本项目任何处置。

---

## 附：证据强度

| 判断 | 强度 |
|---|---|
| 四条请求受同一个连接层／上游基础设施事件影响 | 较强；同秒 + 同异常形状支持相关性 |
| 四条请求共用同一条 H2 连接 | **未决**；日志无 connection id，多连接同步 GOAWAY 无法排除 |
| httpcore 使「还需再次网络读取」的流在 GOAWAY 后失败 | **确凿**，源码 + 白盒 + 端到端网络实测三重 |
| 同一条连接上的多条并发流会一起死 | **确凿**；评审补跑双并发流（`max_connections=1` 强制复用），stream 1 与 3 拿到同形异常同时死亡，3/3 |
| 同一次 read 已排队完整终止事件的流可能完成 | **确凿，实测**；DATA+END_STREAM 排在 GOAWAY 之前 → 流正常读完并成功返回，3/3。**这是第三条路，初稿曾否认其存在** |
| `stream_id > 2**31-1` 对合法 H2 stream id 不可达 | 确凿 |
| `last_stream_id=0` 因真值判断同样掉进致命分支 | 确凿，白盒实测 |
| 落在「可能已处理」范围的流（`stream_id <= last_stream_id`）也被判死 | 确凿，白盒实测 |
| hyper-h2 在 RECV_GOAWAY 后拒绝后续帧 | 确凿；独立评审读状态机源码核对 + PoC 运行时实测 |
| RFC 推荐该字段组合作为 graceful-shutdown 首帧 | 确凿 |
| 该组合**保证**所有在飞流跑完 | **已推翻**；RFC 只说 might |
| 生产对端在 GOAWAY 后本来会保持连接并完成各流 | **未决**；我方停止读取，看不到后续 |
| 重试判据不覆盖 `RemoteProtocolError` | 确凿 |
| 所有 pre-header `RemoteProtocolError` 可低风险幂等重试 | **已推翻** |
| 请求 3、4 失败时下游 body 零字节 | **未决** |
| 裸 `h2.ProtocolError` 不被 httpcore 包装、会绕开我方捕获边界 | **强，足以据此改捕获子句**；`receive_data()` 在 try 块之外，实测 4/4 无抖动 |
| 该时序在生产网络中出现的概率／触发条件 | **未测，不可用于决策** |
| `buffered_retry`／`delayed_commit` 未接线 | 当前 checkout 下确凿 |
| 该二模块已基本具备块级透明重试能力 | **证据不足** |
| 运行 code object 与格式化时磁盘源码不一致 | 确凿 |
| 成因必然是运行进程落后于工作树 | 较强解释，非唯一 |
| 活跃 pipeline 客户端的 h2 开关是 `http2_ping_interval` | 确凿，经评审独立核对 |
| GOAWAY 由当前 HTTP/2 peer 发来 | **确凿**（前提：该 traceback 来自真实生产 transport 而非人工注入事件）；`_connection_terminated` 只在 `_read_incoming_data()` 遇到 hyper-h2 解析入站 GOAWAY 产生的事件时设置 |
| 该 peer 是源站而非边缘／中间 TLS 终止节点 | **未决** |
| GOAWAY 之后的具体 wire 时序（对端是否续发 DATA） | **未决**；PoC 的两个变体是本地构造，不是生产时序 |
| 上游为何在此刻回收连接 | 仅存档 |
