# 独立评审：`docs/tmp/260820-h2-goaway-poc.md` + `exp/260820-h2-goaway-poc/`

日期：2026-08-20
评审者：独立 agent（HTTP/2 协议 / httpx-httpcore-h2 栈 / 实验方法学）
被评审产物：报告 `docs/tmp/260820-h2-goaway-poc.md`；代码与原始输出 `exp/260820-h2-goaway-poc/`（`run_poc.py`、`check_retry_branch.py`、`gen_cert.py`、`run_poc_output.txt`）
环境：`/home/xp/src/ghc-api-proxy-py/.venv/bin/python`（CPython 3.14.2 / httpx 0.28.1 / httpcore 1.0.9 / h2 4.3.0 / hyperframe 6.1.0）——与报告自陈完全一致，已实测核对。

## 总体判决

**核心主张成立，报告的四条结论里有一条是事实错误、一条的证据归属写错了。** PoC 的判决方向没有问题：GOAWAY(NO_ERROR, last_stream_id=2**31-1) 确实会让同连接上仍需继续读网络的在飞流立即抛 `RemoteProtocolError`，且我用**三条 PoC 里没有的实验**（缺失的单变量对照、双并发流、DATA-先于-GOAWAY）独立确认了这一点，方向不变。

但两处需要修订：

- **结论 3「httpcore 根本没有第三条路 / 根本没有第三种结果」是错的**，我实测到了第三种结果：GOAWAY 与该流的 `DataReceived`／`StreamEnded` 落进同一次 read 时，流**正常读完并成功返回**，异常根本不抛。
- **主实验从未真正把「1 秒后到达的合法 DATA」放上过线**。`run_poc.py` 的服务端 handler 在那 1 秒 sleep 期间就被 `async with server` 的退出撕毁了，`writer.write(raw_data2)` 一次都没执行过。报告把这条列在「强到可以据此改代码 / 端到端网络实测」里，属于证据归属错误。

复现性极好：`run_poc.py` 与 `check_retry_branch.py` 各跑 3 次／2 次，输出与 `run_poc_output.txt` 逐字节一致，无任何时序抖动。

发现 8 条：major 2、moderate 3、minor 3。

---

## 我实际执行的命令与环境

```bash
cd /home/xp/src/ghc-api-proxy-py/exp/260820-h2-goaway-poc
/home/xp/src/ghc-api-proxy-py/.venv/bin/python -c "import httpx, httpcore, h2, hyperframe, sys; print(sys.version, httpx.__version__, httpcore.__version__, h2.__version__, hyperframe.__version__)"
# 3.14.2 ... httpx 0.28.1 / httpcore 1.0.9 / h2 4.3.0 / hyperframe 6.1.0
```

补测脚本（一次性，均放在 `/tmp`，未写入仓库、未改动 PoC 任何文件）：

- `/tmp/h2_review_probe.py`——缺失的单变量对照 + DATA-先于-GOAWAY 的两种时序 + h2 状态机转录复现
- `/tmp/h2_third_path.py`——不带 END_STREAM 的第三条路边界
- `/tmp/h2_multistream.py`——单连接上两条并发流
- `/tmp/h2_timing.py`——抛错时刻 vs DATA2 写出时刻
- `/tmp/run_poc_instrumented.py`——`run_poc.py` 的 `/tmp` 副本，仅加 print 探针

---

## 可复现性（重点核查项 7）

### `run_poc.py`：3/3 完全稳定

```bash
cd /home/xp/src/ghc-api-proxy-py/exp/260820-h2-goaway-poc
for i in 1 2 3; do /home/xp/src/ghc-api-proxy-py/.venv/bin/python run_poc.py > /tmp/rerun_$i.txt 2>&1; echo "exit=$?"; done
diff <(sed -n '260,335p' run_poc_output.txt) <(sed -n '260,335p' /tmp/rerun_1.txt) && echo "IDENTICAL structured tail"
```

三次 `exit=0`，五组实验的 `chunk received` / `EXCEPTION RAISED` / `is bare h2.exceptions.ProtocolError` / `wire-level confirmation` 全部逐行相同；与归档的 `run_poc_output.txt` 结构化尾段 `diff` 为空（`IDENTICAL structured tail`）。

**特别值得说明的是 `goaway_sentinel_same_write`。** 报告把它归为「操作系统级竞态、尽力而为」，但在 loopback + 单次 `write()` + 小帧的条件下它 3/3 都命中 `h2.exceptions.ProtocolError: Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED`，本次评审加上原报告共 4/4。**在这个 harness 里它不是竞态，是确定性行为**——竞态只存在于生产网络（见 F6）。

### `check_retry_branch.py`：2/2 完全稳定

```bash
for i in 1 2; do /home/xp/src/ghc-api-proxy-py/.venv/bin/python check_retry_branch.py; done
```

两次输出与报告第 191—194 行逐字一致，四组组合分别为 `RemoteProtocolError` / `RemoteProtocolError` / `ConnectionNotAvailable` / `RemoteProtocolError`。

---

## 发现

### F1｜major｜主实验里那帧「1 秒后到达的合法 DATA」从未上过线，实验没有测到它声称测到的东西

报告第 20 行把这句写进「**强到可以据此改代码**」一档：

> 1s 之后才到达的合法 DATA+END_STREAM 从未被尝试读取。这是端到端网络实测，不依赖任何 mock。

第 34 行的实验设计也写着「等 1 秒后再发一段合法的 DATA2+END_STREAM」，第 135 行进一步断言「服务端 1 秒后发送的 DATA2 从未出现在 `chunk received` 日志里」。

**实际上服务端从来没有走到那一步。** `run_experiment()` 的结构是：

```python
server, port, srv = await start_server(mode)
async with server:
    await run_client(port)
```

客户端在 GOAWAY 到达后 **~1 毫秒**就抛错返回，`async with server` 随即退出并撕毁连接 handler 任务，而 handler 此刻正卡在 `await asyncio.sleep(1.0)` 上，`writer.write(raw_data2)` 这一行永远不会执行。

我把 `run_poc.py` 原样复制到 `/tmp/run_poc_instrumented.py`（**未改动仓库里的 PoC**），只在 sleep 前后各插一行 print：

```
12:EXPERIMENT: goaway_sentinel_separate_reads
15:  [PROBE] GOAWAY written, now sleeping 1.0s before DATA2
19:  EXCEPTION RAISED: httpx.RemoteProtocolError: RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>')
```

`[PROBE] woke from sleep, about to write DATA2` **一次都没有出现**。

我又用 `/tmp/h2_timing.py` 把服务端生命周期延长到超过 sleep，测出真实时序：

```
  [server t+0.066s] HEADERS+DATA1 written
  [server t+0.066s] GOAWAY written
  [client t+0.067s] chunk b'data: hello\n\n'
  [client t+0.068s] EXCEPTION RemoteProtocolError: RemoteProtocolError('<ConnectionTerminated ...>')
ConnectionResetError: Connection lost      # 服务端在 t+1.07s 写 DATA2 时收到
```

即：客户端在 **t+0.068s** 抛错并拆掉连接；服务端一秒后尝试写 DATA2，撞上 `ConnectionResetError`。

**这条不推翻结论，但推翻了它的证据来源。** 「合法的迟到 DATA 会被丢掉」当前是从源码读出来的推断（`_receive_events` 的终止短路排在 `_read_incoming_data` 之前），不是这个实验测出来的。实验测到的是更窄也更干净的一件事。

**我认为正确的表述**（两句都由我实测支撑）：

> 主实验实测到的是：GOAWAY 到达后约 1 毫秒内，仍在读取该流的客户端抛出 `RemoteProtocolError`，抛出点为 `httpcore/_async/http2.py:355`，此时没有发起任何新的网络读取。**服务端一秒后尝试写出的 DATA2 从未上线**——PoC 的服务端 handler 在实验结束时已被撕毁；延长服务端寿命重测（`/tmp/h2_timing.py`）显示该写入会撞上 `ConnectionResetError`，因为客户端早已拆掉连接。「合法的迟到数据被丢弃」这一点由源码结构决定（终止检查排在读取之前），而非由本实验直接观测。

### F2｜major｜结论 3 是事实错误：第三条路存在，我实测到了

报告第 14 行与第 208 行两处断言：

> 完全没有「这条流本来就该被服务端认领，继续读完它」的第三条路
> httpcore 对 GOAWAY 的处理模型里根本没有第三种结果

`_receive_stream_event` 的实际结构（`httpcore/_async/http2.py:326-339`）是：

```python
while not self._events.get(stream_id):
    await self._receive_events(request, stream_id)
event = self._events[stream_id].pop(0)
```

**队列非空时 `_receive_events` 根本不会被调用**，终止检查也就不会触发。而 h2 在同一次 `receive_data()` 里按帧顺序处理，DATA 排在 GOAWAY 之前时不会报错：

```
client.receive_data(DATA + GOAWAY in one call) -> events: ['DataReceived', 'StreamEnded', 'ConnectionTerminated']
```

网络端到端实测（`/tmp/h2_review_probe.py`，服务端把手搓 DATA2+END_STREAM 写在 GOAWAY **之前**）：

```
PROBE: data_before_goaway_same_write
  status: 200 HTTP/2
  chunk received: b'data: hello\n\n'
  chunk received: b'data: bye\n\n'
  STREAM ENDED NORMALLY. total: b'data: hello\n\ndata: bye\n\n'

PROBE: data_before_goaway_separate_writes   # DATA2、0.5s 间隔、再 GOAWAY
  ... STREAM ENDED NORMALLY. total: b'data: hello\n\ndata: bye\n\n'
```

**该流在收到哨兵值 GOAWAY 的同一条连接上正常读完并成功返回，一个异常都没抛。** 这就是第三种结果。

第三条路的**边界**也测了（`/tmp/h2_third_path.py`，DATA2 不带 END_STREAM，与 GOAWAY 同一次 write，3/3 一致）：

```
  chunk received: b'data: hello\n\n'
  chunk received: b'data: bye\n\n'
  EXCEPTION: httpx.RemoteProtocolError: RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:2147483647, ...>')
```

已排队的 chunk **照常交付**，然后才在下一次进入 `_receive_events` 时判死。

**我认为正确的表述**：

> 收到 GOAWAY 后，任何**还需要再次发起网络读取**的流都会在 `_receive_events` 入口被判死。但 httpcore 会先把 `self._events[stream_id]` 里已排队的事件交付完——同一次 socket read 里排在 GOAWAY 之前的 `DataReceived`／`StreamEnded` 会照常交给调用方，若其中含 `StreamEnded`，该流**在哨兵值 GOAWAY 之下依然正常完成**。所以架构缺口应表述为「不会为已受理的流发起新的网络读取」，而不是「没有第三种结果」。

**对下游的影响**：`docs/tmp/260820-h2-goaway-inflight-wipeout.md` 已经通过前一轮评审的 F6 收窄过（见其「一个必要的限定：不是『全部』在飞流」一节），所以主诊断没有被这条带偏。但那份报告第 106 行仍保留着「**没有『这条流 RFC 允许它继续成功，那就继续读完它』这第三条路**」的加粗句，与十九行之后的限定节存在读起来矛盾的观感；而 **PoC 报告本身完全没有修，且它是被引用的源头**。据我所知，此前无人对第三条路做过运行时实测——F6 是纯源码推断，本次是第一次实测证实。

### F3｜moderate｜正样本对照差的不止一个变量（这条的缺口现已由我补上，结论不变）

报告第 33 行称 `control` 是「正样本对照：验证整套 harness 本身没问题」，第 76 行称「对照通过：harness 本身没问题，后续实验里的失败可以归因到 GOAWAY，而不是 PoC 服务端写错了」。

**但 `control` 与主实验之间差了两个变量**：

| | GOAWAY | DATA2 的产生方式 |
|---|---|---|
| `control`（`run_poc.py:120-127`） | 无 | `conn.send_data(...)`，走 h2 库 |
| `goaway_sentinel_*`（`run_poc.py:135-137`） | 有 | `DataFrame(...).serialize()`，`hyperframe` 手搓裸字节，绕开 h2 |

也就是说 `control` **从未验证过手搓的那帧是否合法**。它排除了「TLS/ALPN/h2 握手/httpx 客户端写错了」，但排除不了「手搓的 DataFrame 本身有问题」。任务里点名不放心的正是这一点，判断是对的。

我补跑了缺失的单变量对照——**不发 GOAWAY，但 DATA2 用手搓帧**（`/tmp/h2_review_probe.py`）：

```
PROBE: control_handcrafted_data
  NO GOAWAY, but DATA2 is the hand-crafted hyperframe frame.
  status: 200 HTTP/2
  chunk received: b'data: hello\n\n'
  chunk received: b'data: bye\n\n'
  STREAM ENDED NORMALLY. total: b'data: hello\n\ndata: bye\n\n'
```

**手搓帧被客户端完整接受、流正常结束。** 缺口补上了，两者现在确实只差 GOAWAY 这一个变量，主实验的归因成立。

另有一条旁证支持手搓帧格式无误：`goaway_sentinel_same_write` 里 h2 对它的拒绝是 `Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED`——这是**连接状态机**拒绝，不是帧解析失败，说明帧本身被正确解出来了。

**我认为正确的表述**：

> `control` 排除了 harness 的传输层（TLS/ALPN/h2 握手/httpx 客户端）问题，但它用 `conn.send_data()` 送第二段数据，而主实验用手搓的 `hyperframe.DataFrame`——两者差两个变量。需要额外一组「无 GOAWAY + 手搓帧」的对照才能把主实验的差异收敛到 GOAWAY 单一变量上。（该对照已由评审补跑并通过。）

### F4｜moderate｜「同连接上所有在飞流一次性判死」这个头条主张，PoC 全程只跑了单流单连接

报告第 9 行：「把该连接上所有仍在读取的流……一次性判死」。生产故障的形态是**四条并发流式请求同一秒集体失败**。但 `run_poc.py` 的服务端在收到第一个 `RequestReceived` 之后就 `return`，五组实验每组都只有一条流；`check_retry_branch.py` 也是每次新建一个 connection 对象、只问一个 `stream_id`。**PoC 从头到尾没有跑过一条连接上两条并发流的场景。**

这个推广从源码看是显然的（`_connection_terminated` 是连接级状态，所有流都读它），但它是被引用报告的头条主张，值得有直接证据。我补跑了（`/tmp/h2_multistream.py`，`max_connections=1` 强制复用同一条连接，3/3 一致）：

```
  [server] both streams open: [1, 3]; sending GOAWAY
  stream a: ('httpx.RemoteProtocolError', "RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>')")
  stream b: ('httpx.RemoteProtocolError', "RemoteProtocolError('<ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>')")
  [server] stream ids served: [1, 3]
```

两条并发流（stream 1 与 stream 3）拿到形状完全相同的异常，同时死亡。**主张确认成立**，证据补齐。

### F5｜moderate｜报告第 43—58 节的两段 `>>>` 转录没有任何脚本产生，也不在原始输出里，却被列进「实测」清单

报告第 214 行把这两段列在「**实测（本次 PoC 亲自跑出来的）**」：

```
>>> server.close_connection(error_code=0, last_stream_id=2**31-1)
>>> server.send_data(sid, b'chunk2', end_stream=True)
server send_data after close_connection raised: <class 'h2.exceptions.ProtocolError'> ...
```

`exp/260820-h2-goaway-poc/` 里没有任何脚本产生它们，`run_poc_output.txt` 里也搜不到（`rg -n 'send_data after close_connection' run_poc_output.txt` 无匹配）。同样地，**`check_retry_branch.py` 的四行输出也不在 `run_poc_output.txt` 里**，而报告第 4 行把该文件称作「本次运行的完整原始输出」——它只含 `run_poc.py` 的输出。

我独立复现了这两段（`/tmp/h2_review_probe.py`），**内容全部为真**：

```
  server state before close_connection: <ConnectionState.SERVER_OPEN: 2>
  server state after  close_connection: <ConnectionState.CLOSED: 3>
  server send_data after close_connection raised: <class 'h2.exceptions.ProtocolError'> Invalid input ConnectionInputs.SEND_DATA in state ConnectionState.CLOSED
  client state before receiving GOAWAY: <ConnectionState.CLIENT_OPEN: 1>
  client state after  receiving GOAWAY: <ConnectionState.CLOSED: 3>
  client.receive_data(raw post-GOAWAY DATA) raised: <class 'h2.exceptions.ProtocolError'> Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED
```

并从源码核对了状态机表（`h2/connection.py:147-245`）：`SEND_GOAWAY` 与 `RECV_GOAWAY` 在 IDLE / CLIENT_OPEN / SERVER_OPEN 三态下**一律**转 `CLOSED`，转换表里不带 `error_code`／`last_stream_id` 参数。报告第 58 行的解释正确。

这是产物完整性问题而非事实错误：ad-hoc 交互式转录被写进「实测」清单，但产物集里复现不出来。**建议**（不是 blocker）：把那段 in-process 验证落成 `exp/260820-h2-goaway-poc/` 下的一个几十行脚本，或在报告里标注它是交互式会话、未保留脚本。

顺带一条本次新测出、原报告没有的限定：**帧序决定成败**。同一次 `receive_data()` 里 DATA 排在 GOAWAY **之前**不会报错（见 F2 的 `['DataReceived', 'StreamEnded', 'ConnectionTerminated']`），排在之后才报。报告第 58 行「h2 库把接收过任意 GOAWAY 视为连接级终态转换」正确，但读者容易误以为同一次读取里的所有帧都完了。

### F6｜minor｜结论 4 的证据分级偏低：把确定性机制和生产概率混进了同一个弱档

报告把整条结论 4 归入「只是倾向，样本不足」。这一条实际含两个可分离的断言：

| 断言 | 我的定级 | 依据 |
|---|---|---|
| GOAWAY 与后续 DATA 落进同一次 `receive_data()` 时，抛出的是未经 httpcore／httpx 包装的裸 `h2.exceptions.ProtocolError` | **强，足以据此改捕获子句** | 源码确定：`_read_incoming_data` 的 try/except 只包住 `self._network_stream.read()`，`self._h2_state.receive_data(data)` 在 try 之外（`httpcore/_async/http2.py:440-457`）。实测 4/4 复现（原报告 1 次 + 本次 3 次），loopback 上无抖动 |
| 生产网络里两帧落进同一次 read 的概率／触发条件 | **未测，不可用于决策** | 原报告的定级正确 |

把两者压进同一个弱档，会让「给捕获子句多加一个异常类型」这个明确可行动的部分看起来像悬而未决。（下游 `260820-h2-goaway-inflight-wipeout.md` 第 195 行实际上做对了处置——「足以支撑在判据里多加一个类型」——但那是靠读者自己补的，不是 PoC 报告的分级给的。）

**我认为正确的表述**：把这一条拆成两行，机制归「强」，生产概率归「未测」。

### F7｜minor｜开篇的因果表述与它自己的结论 3 互相矛盾

报告第 9 行：

> 真正决定命运的不是「优雅关闭预告」这个语义本身，而是 …… `stream_id > last_stream_id` 里 `last_stream_id` 的具体取值。

但同一份报告的结论 3 与白盒第四行证明：对 `stream_id <= last_stream_id` 的流，`last_stream_id` **取什么值都一样死**。`last_stream_id` 的取值只决定「比它更晚的流」能不能走到可重试分支，决定不了在飞流的命运。

**我认为正确的表述**：

> 决定命运的是 `(stream_id, last_stream_id)` 的相对关系，外加 `last_stream_id` 的 Python 真值性。哨兵值 `2**31-1` 的作用是把**所有**流都推到 `stream_id <= last_stream_id` 一侧，从而让唯一的可重试出口对全体在飞流不可达。

### F8｜minor（信息性，非缺陷）｜白盒构造合法，但比它支撑的结论窄一层——这正是 F2 的成因

任务点名要核查 `check_retry_branch.py` 手设私有属性 `_connection_terminated` 再直调 `_receive_events` 是否等价于「网络上收到 GOAWAY 之后」。**结论：对它要隔离的那条分支，构造合法。**

理由是这条分支的输入面极窄——`_receive_events` 进入 `async with self._read_lock` 后的第一件事就是这段，它只读两个输入：

```python
if self._connection_terminated is not None:
    last_stream_id = self._connection_terminated.last_stream_id
    if stream_id and last_stream_id and stream_id > last_stream_id:
        self._request_count -= 1
        raise ConnectionNotAvailable()
    raise RemoteProtocolError(self._connection_terminated)
```

`self._connection_terminated.last_stream_id` 与形参 `stream_id`，此外不碰任何连接状态；`_read_lock` 在 `__init__` 里就建好了；`FakeStream` 不会被调用（分支在 `_read_incoming_data` 之前就 raise 了）。而网络路径设置 `_connection_terminated` 的唯一位置（`http2.py:381-382`）也确实只是把 h2 的 `ConnectionTerminated` 事件对象整个存进去，没有附带别的状态变更。**所以人造状态与网络到达后的状态，对这条分支而言是等价的，四组结果可信。**

真正的问题不在构造，在**推论范围**：白盒直调 `_receive_events` **跳过了生产入口 `_receive_stream_event` 的队列消费**。生产上没有任何调用者会绕开那个 `while not self._events.get(stream_id)` 直接进 `_receive_events`。报告用一个绕开了队列消费的实验，去论证「不存在把队列读完的第三条路」——这是 F2 的直接成因。

**建议**在 `check_retry_branch.py` 的模块 docstring 里补一句范围限定：本检查回答的是「`_receive_events` 走哪条分支」，不回答「一条流在生产入口下会怎样」，后者取决于 `_receive_stream_event` 的队列状态。

---

## 核对后确认无误的断言

以下每一条我都独立核过源码或实际跑过，确认可以照用：

1. **抛出点行号精确**。报告称条件在 `httpcore/_async/http2.py:352`、raise 在 `:355`。实测 `sed -n '340,360p'` 逐行数：条件正是 352 行，`raise RemoteProtocolError(self._connection_terminated)` 正是 355 行。与生产 traceback 一致。
2. **`error_code` 全程未被读取**。`_receive_events` 的终止分支只读 `last_stream_id`，`NO_ERROR` 与真协议错误走同一条路。源码核对无误。
3. **`last_stream_id=0` 因 Python 真值判断掉进致命分支**。`if stream_id and last_stream_id and stream_id > last_stream_id` 中 `0` 为假，短路掉比较。白盒实测复现（2/2），网络实验 `goaway_before_headers_low` 也复现（3/3）。诊断正确。
4. **可重试分支不是死代码**。`last_stream_id=1, stream_id=3` → `ConnectionNotAvailable`，2/2 复现。
5. **`stream_id <= last_stream_id` 的流一样被判死**（就 `_receive_events` 这一层而言）。`last_stream_id=1, stream_id=1` → `RemoteProtocolError`，2/2 复现。注意这一层的结论正确，从它推出的「没有第三条路」不正确（F2）。
6. **`stream_id > last_stream_id` 在哨兵值下对任何合法流恒假**。`2**31-1` 是 31-bit stream identifier 的最大合法值，`>` 不可达（等于时也为假）。表述准确。
7. **h2 库在 `close_connection()` 之后拒绝 `send_data()`**，报错 `Invalid input ConnectionInputs.SEND_DATA in state ConnectionState.CLOSED`。独立复现，逐字一致。
8. **h2 客户端在收到 GOAWAY 之后拒绝后续 DATA**，报错 `Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED`；状态机表证实 `RECV_GOAWAY` 从 `CLIENT_OPEN` 无条件转 `CLOSED`，`error_code`／`last_stream_id` 不参与。独立复现 + 源码核对。
9. **裸 `h2.exceptions.ProtocolError` 确实不被 httpcore 包装**。`_read_incoming_data` 的 `try/except` 只覆盖 `await self._network_stream.read(...)`；`self._h2_state.receive_data(data)` 在 try 块之外（`http2.py:457`）。源码核对无误，机制描述正确。
10. **httpx 把 httpcore 异常重包成非子类的 `httpx.RemoteProtocolError`，`__cause__` 链保留原始异常**。报告第 133 行对 `isinstance` 三行为 False/False/True 的解释正确。
11. **手搓 `DataFrame` 绕开 h2 库这一实现选择被如实记录了**（报告第 41 行、代码第 48 行与 134 行注释）。这一点我认为值得肯定：它是最容易被藏起来的实验细节，报告主动写了出来，才使 F3 得以被发现和补齐。
12. **报告对 `goaway_before_headers_low` 打破自身预测这件事做了如实记录**（第 186 行），没有事后把预测改成结果。
13. **报告正确地把「`ConnectionNotAvailable` 之后 pool 是否真能重试成功」列为未实测的推断**（第 220 行）。补充一条支持：`connection_pool.py` 只在 `handle_async_request` 尚未返回 Response 时捕获它，body 迭代阶段的该异常不会被 pool 重发——所以这一条**必须**留在未验证档，报告的处理是对的。
14. **报告正确地把「真实上游如何调度双阶段 GOAWAY」列为纯推断、未触碰任何真实上游**（第 219 行）。

---

## 「实测 vs 推断」分界是否诚实（重点核查项 6）

**总体诚实，两处越界。** 报告主动划了这条界，而且把好几条对自己不利的东西放进了推断侧（真实上游行为、pool 重试是否成功、手搓帧的实现选择），这不是走过场。

两处越界：

- **F1**：「1 秒后到达的合法 DATA 从未被读取」被列进实测，实际那帧从未产生。这是把**源码推断**写进了**实测**清单，而且是全篇最关键的一句。
- **F5**：两段 `>>>` in-process 转录被列进实测，但产物集里没有能复现它们的脚本。内容为真，可复现性不在产物里。

除此之外，「哪些没测」写得比多数同类报告细，`goaway_sentinel_same_write` 的竞态性质、生产概率未测、h2 库限制的适用边界，都主动标了出来。

---

## 修订建议（按优先级）

1. **改掉结论 3 的绝对表述**（F2）。用「不会为已受理的流发起新的网络读取」替换「没有第三种结果」，并补上第三条路的实测与边界。这一条也应回传给 `docs/tmp/260820-h2-goaway-inflight-wipeout.md`，把它第 106 行那句加粗与其后的限定节对齐（那份报告的限定节内容已经对了，只是前面那句读起来仍像全称否定）。
2. **修正主实验的证据归属**（F1）。把「合法迟到 DATA 被丢弃」从实测移到源码推断，或按我给的表述改写成实测到的那件更强的事（客户端 68ms 内拆连接，服务端一秒后写入撞 `ConnectionResetError`）。若要真正实测「迟到数据」这一支，`run_experiment` 需要在客户端返回后再等服务端 handler 跑完，而不是立刻退出 `async with server`。
3. **把 F3 与 F4 的两组补充实验并进 PoC**（各二十来行），使对照收敛到单变量、并让头条主张有多流直接证据。我的 `/tmp` 脚本可直接搬。
4. **结论 4 的证据分级拆成两行**（F6）。
5. **修正开篇因果表述**（F7），并给 `check_retry_branch.py` 的 docstring 补一句范围限定（F8）。
6. **把两段 in-process 转录落成脚本**（F5），或标注为未保留的交互式会话。

---

## 评审边界（本报告不覆盖什么）

- 只评审 PoC 报告与 `exp/260820-h2-goaway-poc/`。`docs/tmp/260820-h2-goaway-inflight-wipeout.md` 只在追踪结论传播时读了相关小节，未做整体评审。
- 全部实验都在 **loopback + 自签 TLS + 单进程 asyncio 服务端**下跑，与生产网络的时序分布无关。`goaway_sentinel_same_write` 在这个 harness 里的确定性，**不能**推广为生产里的确定性。
- 生产对端（Copilot 后端／其边缘）实际发送 GOAWAY 的时机与是否随后继续发数据，本次同样未观测——与原报告的限定一致。
- 未修改仓库内任何文件，未运行任何生产代码，未接触 `4141` 上的现有服务。全部补测脚本写在 `/tmp`。
