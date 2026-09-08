# 每条 HTTP/2 连接的流上限：能不能做、有哪几种做法、代价多大

- **日期**：2026-08-20
- **作者**：PoC 工程师（子智能体）
- **环境**：httpx 0.28.1 / httpcore 1.0.9 / h2 4.3.0 / CPython 3.14.2
- **PoC 目录**：`/home/xp/src/ghc-api-proxy-py/exp/260820-h2-stream-cap/`
- **上游背景**：`docs/agents/upstream-h2-goaway/findings.md`（GOAWAY 致死机制）、`docs/tmp/260820-goaway-frequency-forensics.md`（现网频率取证与姊妹项目 `b5892380f` 的实测对照）

本报告里每条结论都标了证据强度：

- 【实测】——本次 PoC 跑出来的，逐字输出在 `run_poc_output.txt` / `probe_costs_output.txt`，强到可据此改代码。
- 【读源码】——读 httpcore／httpx 源码得到的判断，未在运行时逐条验证。
- 【推理】——基于上面两者的推导，可能有我没想到的前提。

---

## 一句话结论

**这件事完全做得到，代价也不大。如果目标值是 1，它与本项目已有的 `upstream_transport.http2 = false` 在爆炸半径上实测等效，而后者成本低得多——所以我倾向先用后者止血。但这是偏好，不是「HTTP/1.1 严格支配 cap=1」的证明：两者有一处真实差异，见下。**

> **本节曾经写错过，已按独立评审的三条 BLOCKING 更正，并补跑了一个实验。** 原稿声称 (a) HTTP/1.1 带来一条「实打实的正确性收益」、(b) HTTP/1.1 严格支配（dominated）cap=1、(c) 由取证数据可推出「唯一有意义的 cap 是 2」。三条都不成立，更正后的说法见下文对应各节。保留这段记录，是因为 (a) 与 (c) 都是「把源码推断当成实测结论」的典型，值得留痕。

实测等效的部分（`cap1` / `cap1_goaway` / `http11_no_h2` 三个实验）：6 条同时在飞请求都占 6 条 TCP 连接，打掉其中一条都恰好死 1 条请求。

**一处真实差异，方向对 cap=1 有利，已实测**（实验 `early_close_reuse`）：响应**被提前关闭**时（客户端取消、我方主动放弃上游 SSE），httpcore 的 HTTP/1.1 连接会因为双方状态未到 `DONE` 而**整条关掉**（`http11.py:238-249`）；HTTP/2 只是释放那条 stream、连接留在池里继续用（`http2.py:409-419`）。两个顺序请求各读一块就关闭：**h2 cap=1 服务端只 accept 1 次，HTTP/1.1 accept 2 次。** 本项目确实存在提前释放上游流的路径，所以这不是纸面差异——它意味着 HTTP/1.1 每遇到一次提前关闭就要多付一次 TLS 握手（对 `api.githubcopilot.com` 实测 ~155ms）。这条足以否定「严格支配」，但不足以证明 cap=1 值得背上 httpcore 私有 API 的长期维护成本。

所以：

- **想立刻止血、且接受上面那处代价** → 设 `upstream_transport.http2 = false`。零新代码、零私有 API。
- **在意提前关闭时的连接复用，或者想保留 h2 多路复用** → 才需要这个 cap。做法已验证可行，见候选 2。
- **候选 3（客户端发 SETTINGS_MAX_CONCURRENT_STREAMS）方向搞反了，且实测无效**，见下。

还有一条会影响裁决的外部事实：**httpx 1.0.dev4 已于 2026-08-19 发布，并且完全移除了 httpcore 依赖**——本方案赖以工作的三个挂钩点届时会同时消失。详见维护性一节。

---

## 候选方案对比

| | 方案 | 能不能做到 | 代价 | 证据 |
|---|---|---|---|---|
| 1 | httpcore 现成开关 | **不能。** `httpx.Limits` 只有 `max_connections` / `max_keepalive_connections` / `keepalive_expiry` 三个字段；`httpcore.AsyncConnectionPool.__init__` 也没有任何 per-connection stream 参数。`AsyncHTTP2Connection` 内部确有 `_max_streams` / `_max_streams_semaphore`，但那是 `min(对端通告值, 硬编码的 100)`，且是**阻塞信号量**——它让请求在这条连接上排队，不会让池去开新连接 | — | 【读源码】`httpx/_config.py:159-198`、`httpcore/_async/connection_pool.py:46-60`、`httpcore/_async/http2.py:118-131,197-212,391-407` |
| 2 | **覆写 `is_available()`** | **能，且干净。** 池分配请求时对每条连接只问一句 `can_handle_request(origin) and is_available()`（`connection_pool.py:308`，全仓唯一调用点）。答 False 就落到「新建连接」分支 | 3 处私有 API（见维护性一节）；`is_available()` 变成 O(在飞请求数)，量级可忽略 | 【实测】`cap2` / `cap1` / `cap2_goaway` / `cap1_goaway` |
| 3 | 客户端发 SETTINGS_MAX_CONCURRENT_STREAMS | **方向是反的，而且即使利用 httpcore 的副作用也没用。** RFC 9113 §6.5.2：这个 setting 限制的是**对端能开多少流**，客户端发它约束的是 server push。httpcore 确实拿自己的 `local_settings.max_concurrent_streams` 去夹 `min()`，所以调小它**会**限制我们的出站流——但那是**在同一条连接上阻塞排队**，连接数不变 | 无收益 | 【实测】`server_advertised_mcs`：服务端通告 2，6 条请求仍然全落在 **1 条** TCP 连接上，只是串行成三波，墙钟 0.4s → 1.22s |
| 4 | 多客户端分片 | **能，最笨但零风险。** N 个 `AsyncClient` 轮转 | N 份连接池 + N 份 TLS context；「哪个请求去哪个客户端」要自己写且无法感知在飞数；无法表达「同一客户端内 cap=2」 | 【实测】`sharded_clients`：3 个客户端 → 3 条连接 |
| 5 | **`upstream_transport.http2 = false`**（项目已有） | **能，且已经落地。** `src/app/config/schema.py:95` | 每条并发请求一次 TLS 握手（对 `api.githubcopilot.com` 实测 ~155ms）；失去 HPACK；**响应被提前关闭时整条连接作废**（h2 只丢那条 stream） | 【实测】`http11_no_h2`：6 条并发 → 6 条连接；杀掉 1 条 → 恰好 1 条失败 |

---

## PoC 代码与输出

| 文件 | 作用 |
|---|---|
| `exp/260820-h2-stream-cap/stream_cap.py` | 候选 2 的实现：`StreamCappedConnection` / `_StreamCapMixin` / `StreamCappedPool` / `StreamCappedHTTPProxy` / `build_capped_client()` |
| `exp/260820-h2-stream-cap/run_poc.py` | 12 个实验的 harness：本地 TLS+ALPN h2 服务端 + HTTP/1.1 服务端，**服务端侧数 accept 次数**并记录每条流落在哪条 TCP 连接上 |
| `exp/260820-h2-stream-cap/run_poc_output.txt` | 上面的逐字输出（本报告正文里的引用是**节选**，见下） |
| `exp/260820-h2-stream-cap/probe_costs.py` | 真实上游 SETTINGS 探针（无凭据、不发任何 HTTP 请求）+ 客户端侧内存／fd 计量 |
| `exp/260820-h2-stream-cap/probe_costs_output.txt` | 上面的逐字输出；网络与 RSS 数字逐次运行会波动，量级稳定 |
| `exp/260820-h2-stream-cap/serve_h2.py` | 独立进程的 h2 服务端，供内存计量隔离两端 |
| `exp/260820-h2-stream-cap/debug_probe.py` | 排障用的最小探针（诊断 harness 自身的挂起，见下） |

复现：

```
cd /home/xp/src/ghc-api-proxy-py/exp/260820-h2-stream-cap
/home/xp/src/ghc-api-proxy-py/.venv/bin/python -u run_poc.py
/home/xp/src/ghc-api-proxy-py/.venv/bin/python -u probe_costs.py
```

证书由 `gen_cert.py` 生成，已 gitignore，有效期到 2026-08-21，过期后重新跑一次 `gen_cert.py` 即可。

### 关键实验的输出（**节选**，不是逐字复制）

下面每段都是从 `run_poc_output.txt` 摘的，为可读性做了两件事：用 `conn#0..conn#5`、`req 1..req 5`、`...` 折叠了重复行；墙钟时间逐次运行会有几十毫秒的自然波动（例如同一条 `cap2_goaway` 在不同次运行里是 0.83s / 0.84s / 0.93s）。**连接数、每条流落在哪条连接上、OK/FAIL 计数这三样是稳定的，多次重跑一致**；要逐字文本请直接看 `run_poc_output.txt`。

**正样本对照——不设 cap，确认观测手段有效**：

```
EXPERIMENT: baseline_no_cap
  TCP connections accepted by server: 1
    conn#0: 6 stream(s) ['/req/0', '/req/1', '/req/2', '/req/3', '/req/4', '/req/5'] max_concurrent=6 goaway_sent=False
  summary: 6/6 OK, 0 FAIL, wall 0.32s
```

**cap=2 → 连接数变成 ceil(6/2)=3**：

```
EXPERIMENT: cap2
  TCP connections accepted by server: 3
    conn#0: 2 stream(s) ['/req/0', '/req/1'] max_concurrent=2 goaway_sent=False
    conn#1: 2 stream(s) ['/req/2', '/req/3'] max_concurrent=2 goaway_sent=False
    conn#2: 2 stream(s) ['/req/4', '/req/5'] max_concurrent=2 goaway_sent=False
  summary: 6/6 OK, 0 FAIL, wall 0.32s
```

**本地复现生产事故——不设 cap + 一帧 GOAWAY**：

```
EXPERIMENT: no_cap_goaway
  >>> sending GOAWAY(error_code=0, last_stream_id=2**31-1) on conn#0 only
  TCP connections accepted by server: 1
    conn#0: 6 stream(s) [...] max_concurrent=6 goaway_sent=True
    req 0 (served on conn#0): FAIL httpx.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
    ... 六条完全相同 ...
  summary: 0/6 OK, 6 FAIL, wall 0.81s
```

**整件事的目的——设了 cap 后打掉一条连接，其余存活**：

```
EXPERIMENT: cap2_goaway
  >>> sending GOAWAY(error_code=0, last_stream_id=2**31-1) on conn#0 only
  TCP connections accepted by server: 3
    conn#0: 2 stream(s) ['/req/0', '/req/1'] max_concurrent=2 goaway_sent=True
    conn#1: 2 stream(s) ['/req/2', '/req/3'] max_concurrent=2 goaway_sent=False
    conn#2: 2 stream(s) ['/req/4', '/req/5'] max_concurrent=2 goaway_sent=False
    req 0 (served on conn#0): FAIL httpx.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, ...>
    req 1 (served on conn#0): FAIL httpx.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, ...>
    req 2 (served on conn#1): OK   http/HTTP/2 body=b'data: start\n\ndata: bye\n\n'
    req 3 (served on conn#1): OK   http/HTTP/2 body=b'data: start\n\ndata: bye\n\n'
    req 4 (served on conn#2): OK   http/HTTP/2 body=b'data: start\n\ndata: bye\n\n'
    req 5 (served on conn#2): OK   http/HTTP/2 body=b'data: start\n\ndata: bye\n\n'
  summary: 4/6 OK, 2 FAIL, wall 0.84s
```

**cap=1（姊妹项目的取值）**：

```
EXPERIMENT: cap1
  TCP connections accepted by server: 6
    conn#0..conn#5: 各 1 stream(s), max_concurrent=1
  summary: 6/6 OK, 0 FAIL, wall 0.34s

EXPERIMENT: cap1_goaway
  >>> sending GOAWAY(error_code=0, last_stream_id=2**31-1) on conn#0 only
  TCP connections accepted by server: 6
    req 0 (served on conn#0): FAIL httpx.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, ...>
    req 1..req 5: OK
  summary: 5/6 OK, 1 FAIL, wall 0.85s
```

**唯一一处 cap=1 与 HTTP/1.1 不等价的地方（评审指出后补测）**：

```
EXPERIMENT: early_close_reuse
    h2 cap=1  request 0: got b'data: start\n\n', closed early
    h2 cap=1  request 1: got b'data: start\n\n', closed early
  HTTP/2 cap=1: server accepted 1 TCP connection(s); stream ids per conn: [(0, [1, 3])]
    http/1.1  request 0: got b'data: start\n\n', closed early
    http/1.1  request 1: got b'data: start\n\n', closed early
  HTTP/1.1: server accepted 2 TCP connection(s)
```

**HTTP/1.1 对照（`upstream_transport.http2 = false`）**：

```
EXPERIMENT: http11_no_h2
  >>> abruptly dropping conn#0 (/req/0) mid-response
  TCP connections accepted by server: 6
    req 0 (served on conn#0): FAIL httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)
    req 1..req 5: OK   http/HTTP/1.1
  summary: 5/6 OK, 1 FAIL, wall 0.63s
```

**候选 3 的证伪**：

```
EXPERIMENT: server_advertised_mcs   （服务端初始 SETTINGS 通告 MAX_CONCURRENT_STREAMS=2，客户端不设 cap）
  TCP connections accepted by server: 1
    conn#0: 6 stream(s) [全部六条] max_concurrent=2 goaway_sent=False
  summary: 6/6 OK, 0 FAIL, wall 1.22s
  reading: 6 requests x 0.4s hold. 一条连接跑并发 2 就是三波 ~1.2s；一条连接跑并发 6 是 ~0.4s；三条连接跑并发 2 也是 ~0.4s。
```

**我方 cap 与上游通告值的关系**（两个实验）：

```
EXPERIMENT: cap2_plus_advertised_mcs2   （cap=2，上游也通告 2）
  TCP connections accepted by server: 3   ... wall 0.42s     ← 不发生排队

EXPERIMENT: cap4_above_advertised_mcs2  （cap=4，上游只通告 2）
  TCP connections accepted by server: 2
    conn#0: 4 stream(s) [...] max_concurrent=2   ← 分配了 4 条，同时只能跑 2 条
    conn#1: 2 stream(s) [...] max_concurrent=2
  summary: 6/6 OK, 0 FAIL, wall 0.82s          ← 多花一波
```

---

## 正面回答：如果最终要用 cap=1，它相对于直接关掉 HTTP/2 还有什么额外好处？

**在爆炸半径这个目标上：没有额外好处，两者实测数值完全一致。但「没有额外好处」不等于「等价」——在连接复用上 cap=1 确实更好一处，见第 3 条。**

| 指标 | cap=1（h2） | `http2 = false` | 
|---|---|---|
| 6 条并发请求占用的 TCP 连接数 | 6【实测】 | 6【实测】 |
| 打掉 1 条连接的伤亡 | 1【实测】 | 1【实测】 |
| 每条新连接的 TLS 握手代价 | ~155ms【实测，TCP 与 TLS 分开计时】 | 同一量级（只提供 `http/1.1` 的 ALPN 探针总耗时 151–156ms）【实测，但只有合计值，不足以断言两侧逐项相等】 |
| 每条连接客户端 fd | 1【实测】 | 1（同一 httpcore 池逻辑）【读源码】 |
| 完整读完后的连接复用 | 有 | 有 |
| **提前关闭响应后的连接复用** | **有**（只丢那条 stream）【实测】 | **没有**（整条连接作废）【实测】 |

差异只剩这些，我按方向分开列：

**倾向 `http2 = false` 的**

1. **零私有 API、零新代码。** 一个已经实现并有注释说明的配置键（`schema.py:95`）。cap 方案要引入 3 处私有依赖并长期维护，还要面对 httpx 1.0 的断点。**这是唯一一条站得住的。**
2. ~~消掉一条错误逃逸面。~~ **这条我写错了，已撤回。** 原稿的说法是：裸 `h2.exceptions.ProtocolError` 进不了 `client.py:184` 的 `except`，而 HTTP/1.1 下的 `httpx.RemoteProtocolError` 能进去，所以走 h1 有正确性收益。**类型关系没错**（实测 MRO：`RemoteProtocolError → ProtocolError → TransportError → RequestError → HTTPError`，而 `h2.exceptions.ProtocolError` 只继承 `H2Error`），**但推论错了，两处**：
    - `send_responses_headers` 的 `try` **只包住 `_post_openai(..., stream=True)`**，它在 headers 到达时就返回了。PoC 里 H1 那条故障发生在读 body 阶段（先收到 `data: start`，之后连接才断），**那时 `except` 早已退出**。
    - 即便它真在 `try` 内抛出也没用：`transport.py` 的 `_RESPONSES_PRE_HEADERS_HTTPX_ERRORS` 只有 `ConnectError` / `ConnectTimeout` / `PoolTimeout` 三个，`RemoteProtocolError` 不在其中，`is_responses_headers_pending_transport_error()` 返回 `False`，那条分支只是裸 `raise`。
    还剩下的、真实但很弱的一点：`h2.exceptions.ProtocolError` 是**任何** `except httpx.*` 子句都接不住的类型，去掉 h2 就去掉了这个类型；而 `httpx.RemoteProtocolError` 至少落在 httpx 的异常体系内。但在**我引用的那个边界上，今天两者的结局相同**（都是往上抛）。所以这不能算 http1 的收益，只能算一个潜在的、当前未兑现的差别。【实测（MRO 与 PoC 异常类型）+ 读源码（`client.py:179-186`、`transport.py:4-8,23-34`）；原推论由独立评审推翻】

**倾向 cap=1（h2）的**

3. **提前关闭响应时保住连接。** h11 在响应未读完就关闭时会因为双方状态未到 `DONE` 而**整条连接关掉**（`http11.py:238-249`），h2 只释放那条 stream、连接留在池里（`http2.py:409-419`）。本项目存在提前放弃上游 SSE 的路径，所以这是实际差异：HTTP/1.1 在这条路径上要多付一次 ~155ms 的 TLS 握手。**评审指出后我补了实验 `early_close_reuse`**：两个顺序请求各读一块就关闭，h2 cap=1 服务端只 accept **1** 次（同一连接上 stream id 1 与 3），HTTP/1.1 accept **2** 次（服务端已开 keep-alive，所以不是服务端拒绝复用）。【实测】
4. **HPACK 头部压缩。** 上游请求头不小。但 cap=1 下每条连接同时只有一个请求，动态表只在连接复用时才摊到收益，量级小。【推理】
5. **它是个可调旋钮。** 将来若上游行为改善，把 1 改成 4/8/100 只是改配置；`http2 = false` 是二值的。【推理】

**无法判定的（最该注意的一条）**

6. **上游边缘对 h1 与 h2 是否一视同仁**——限流、空闲超时、缓冲策略、是否有等价的连接回收行为——我们没有数据。只实测到 `api.githubcopilot.com` 在只提供 `http/1.1` 的 ALPN 时**正常协商成功**（`probe_costs.py` PROBE 1b，TLSv1.3，2/2 样本），所以这条路不会被上游直接拒绝；但协商成功不等于行为等价。【实测（仅协商）+ 未测（行为）】

**修正后的结论**：如果目标值是 1，两条路在**爆炸半径**上实测等效，`http2 = false` 成本低得多，**我倾向它**；但第 3 条是 cap=1 一侧真实存在的好处，所以这是**权衡**，不是「这条路可以不做」的证明。裁决点落在一个我没有的数上：**「上游响应被提前关闭」在本服务里有多频繁**。建议在决定前查一下。

---

## cap 取值与「成批失败概率」的关系

> **本节原稿有一张按 K≈3.17 推算的取值表，已整节撤回。** 独立评审指出：取证报告里的 `victims/event=3.17` 是「同 pid、结束时间相距 ≤3 秒的启发式聚簇」中、**条件于已成为 multi-victim 的那些聚簇**的失败条数均值。它没有 connection id，没有直接观测 GOAWAY，只数失败者而不数同一时刻仍健康的在飞流，也无法证明一个聚簇对应一条连接或一次连接事件。**因此它不是事故时刻的在飞并发度 K，甚至不是 K 的无偏下界**，据它推出的「N=2 约一半事件成批」「N≥4 是纯无操作」「N=2 是唯一有意义的中间值」全都没有数据支撑。我原来只把它软化为「条件均值」，那不够——问题不在条件化，在于它压根不是并发度。

去掉那张表之后，**还站得住的只有三条**：

1. **只有 N=1 能从构造上消灭「一次连接事件伤多条请求」。** 这不需要任何并发度估计：连接上只有一条流，事件最多伤一条。任意 **N≥2 仍然允许单连接多受害者**，只是把上限压到 N。【推理，前提只有「一次事件打一条连接」】
2. **cap 设到上游通告值以上没有意义。** 上游通告 `MAX_CONCURRENT_STREAMS = 100`（实测，`api.githubcopilot.com` 三次采样一致，`api.github.com` 同值）。超出部分只会在连接内排队而不是新开连接——`cap4_above_advertised_mcs2` 实测：cap=4 而上游只给 2，那条连接分到 4 个请求却只能同时跑 2 个，多花一波。所以配置校验只需要这一条。【实测】
3. **在实践中，上游那个 100 从来不是约束**：我们的并发度远达不到，**起作用的只有我方的 cap**。【推理】

**要给 N≥2 选一个有依据的值，缺的那个数是「GOAWAY 到达时刻该连接上的在飞流数」，现有取证拿不出它。** 想拿到它有两条路：在本项目的日志里记录 connection id 与该连接的在飞流数（当前日志没有 connection id，这正是 `findings.md` 未决表里的第一条）；或者解出 `copilot-api-js` 的 GOAWAY ledger（取证报告 §「不能直接数 GOAWAY 帧」说明那需要复现它的 manifest 编码，本次没做）。**在拿到之前，N≥2 的具体取值只能是拍脑袋，我不给推荐值。**

**一条仍然成立、且应回传给取证报告作者的观察**：POST 窗口（N=1）残留 5.9% 成批失败、victims/event 仍有 2.19。若 N=1 严格生效，**单条连接事件**的成批失败应当是 0。残留只能来自两种情况——上游一次性回收多条连接（node 级），或者时间窗聚簇把两次独立失败算作一批。无论哪种，结论都一样：**任何 per-connection cap（包括 N=1）都治不了它**，把成批失败压到零做不到。这给「cap 能买到什么」划了一条上界。
## 连接数上升的代价（实测量级）

`probe_costs.py` 输出（节选自 `probe_costs_output.txt`；网络数字逐次运行波动，量级稳定）：

```
--- api.githubcopilot.com ---
  sample 0: alpn='h2' tcp_connect=9.5ms tls_handshake=156.7ms total=166.2ms
  sample 1: alpn='h2' tcp_connect=8.4ms tls_handshake=153.3ms total=161.8ms
  sample 2: alpn='h2' tcp_connect=6.9ms tls_handshake=156.3ms total=163.2ms
    server SETTINGS: {'ENABLE_CONNECT_PROTOCOL': 1, 'INITIAL_WINDOW_SIZE': 67108864,
                      'MAX_CONCURRENT_STREAMS': 100, 'MAX_FRAME_SIZE': 68608}

--- client-side RSS vs live HTTP/2 connections (one client, cap=1, one open stream each) ---
  baseline (client built, 0 connections): rss=44868 KiB, fds=9
  1 connections:   rss=45780 KiB  delta=912 KiB   per-connection=912.0 KiB  fds=10
  10 connections:  rss=46360 KiB  delta=1492 KiB  per-connection=149.2 KiB  fds=19
  50 connections:  rss=49612 KiB  delta=4744 KiB  per-connection=94.9 KiB   fds=59
  100 connections: rss=53560 KiB  delta=8692 KiB  per-connection=86.9 KiB   fds=109
```

- **TLS 握手：约 155ms／条新连接，对 `api.githubcopilot.com`**（TCP connect 只要 7–10ms，握手本身就要 150ms 上下；同机对 `api.github.com` 只要 15–20ms，说明这是 Copilot 那个边缘节点的特性，不是本机 CPU）。**这是最大的一项代价，而且它落在首字节延迟的关键路径上**：不设 cap 时第 2..N 条并发请求复用已建连接、零额外延迟；cap=1 或 HTTP/1.1 下每条都要先付这 165ms。已建连接在 `keepalive_expiry` 内会被复用，所以这笔钱只在并发度上涨、需要新开连接时付。
- **内存：边际约 80–90 KiB／连接**（第一条连接的 912 KiB 里绝大部分是 TLS／h2 模块的一次性开销）。100 条连接才 8.7 MB。**可忽略。**
- **文件描述符：精确 1 个／连接**（实测 fds 从 9 线性涨到 109）。**可忽略。**
- **`is_available()` 的算法代价**：本实现每次调用扫一遍 `pool._requests`，于是 `_assign_requests_to_connections` 变成 O(连接数 × 在飞请求数)。几十条的量级下无所谓；真要在意可以在池上维护一个 `连接 → 计数` 的字典，但那要挂到 `assign_to_connection` / `PoolByteStream.aclose` 两个点上，反而多依赖两处私有 API，不划算。【推理】

---

## 维护性：依赖了哪些私有 API，升级会不会碎

这条按要求老实写。

**公开的（在 `httpcore.__all__` 里，实测确认）**：`AsyncConnectionPool`、`AsyncHTTPProxy`、`AsyncConnectionInterface`、`Origin`、`Request`、`Response`。所以「实现一个自定义连接类」这件事本身是 httpcore 明确导出的能力。

**依赖的私有面共 3 处**：

| # | 依赖 | 用途 | 碎了会怎样 |
|---|---|---|---|
| 1 | `AsyncConnectionPool.create_connection(origin)` | 包装池创建的每条连接 | 名字无下划线前缀，且 httpcore **自己的** `AsyncHTTPProxy`（`http_proxy.py:146`）和 `AsyncSOCKSProxy`（`socks_proxy.py:176`）都覆写它——是事实上的扩展点。改名会**立刻报错**（我们的覆写不再被调用……不，是 super() 找不到），属于**响亮失败** |
| 2 | `pool._requests`（`list[AsyncPoolRequest]`）与 `AsyncPoolRequest.connection` | 数「这条连接现在挂了几个请求」 | **这是最危险的一处，因为它会静默失效**：如果 `_requests` 改名或 `.connection` 语义变化，`assigned_request_count()` 恒返回 0，`is_available()` 恒为真，**cap 就变成一个什么都不做的装饰**，没有任何报错。历史上这两个名字自 2021 年起没变过（详见版本面），但没变过不等于有承诺 |
| 3 | `httpx.AsyncHTTPTransport._pool` | 把自定义池塞进 httpx | 改名会**立刻 AttributeError**，响亮失败 |

**必须配套的一条防线**：针对第 2 处写一个断言型的冒烟测试——起本地 h2 服务端、发 N 条并发请求、断言服务端 accept 数 == ⌈N/cap⌉。本 PoC 的 `run_poc.py` 已经是这个测试的雏形。**不要**只断言「没抛异常」，那正是第 2 处失效时的表现。

**另外三条必须写进实现的注意事项**（都是我在 PoC 里踩到或读源码发现的）：

- **计数必须取自池，不能取自连接。** TLS 握手完成前 `AsyncHTTPConnection.is_available()` 对任何 http2 连接一律返回 `True`（`connection.py:175-185`），因为那时它还不知道自己会不会是 h2。一批同时到达的请求会在第一条连接还在握手时全部压上去。`pool._requests` 在**分配时刻**就已经是对的。【读源码 + 实测（cap 生效即为验证）】
- **`proxy=` 路径要单独接线。** 生产的 `build_http_client` 传了 `proxy=options.proxy`；一旦配了代理，httpx 建的是 `AsyncHTTPProxy` 而不是 `AsyncConnectionPool`。只继承后者的 cap **在配代理那天会静默失效**。`stream_cap.py` 里已经做成 mixin 并给出 `StreamCappedHTTPProxy`，但**代理路径本 PoC 未实际跑过**。【读源码，未实测】
- **HTTP/1.1 回退是安全的。** 我们的 `is_available()` 是在内层结果上再 `and` 一个计数条件，只会更严格，不会放行 h11 连接去接第二个并发请求。【读源码】

**版本面**：一份并行的库考古调研（逐 commit 拉源码核对，非二手转述）给出下面这些，我认为强到可据此定升级策略。

**历史稳定性——比预想的好**

- `create_connection(self, origin: Origin) -> AsyncConnectionInterface` 的签名自 2021-11-11（#420）至今**一次未变**。
- `AsyncConnectionInterface` 是全仓最稳的一块：`_async/interfaces.py` 全部历史只有 6 个 commit，除首次引入外全是纯风格改动；方法集自 2021-11-11 起**一字未改**。
- `pool._requests` 这个属性名与元素上的 `.connection` 属性，自 0.14 redesign（2021-11-11）起一直在。2024-02-12 的 PR **#880**（首发于 **1.0.3**）把元素类从 `RequestStatus` 改名为 `AsyncPoolRequest`、把 `_pool_lock` 换成 `_optional_thread_lock`、引入 `_assign_requests_to_connections`——**但没有动我们读的那两个名字**。所以只要实现是「读 `pool._requests`、取每项 `.connection`」而**不 import `AsyncPoolRequest`、不调用 `_assign_requests_to_connections`**，它在 0.14 到 1.0.9 全线成立。
- httpcore 已发布最新版**仍是 1.0.9**（2025-04-24），之后 master 只有 3 个 commit，其中唯一触及 `connection_pool.py` 的是一行 bug 修（`len([...])` → `sum(...)` 数空闲连接），**不碰我们的任何挂钩点**。**wrapper 在今天的 master 上无需改动即可运行。**

**一条必须写进依赖注释的事实**：httpcore 的 CHANGELOG 把 #880 那次 pool 重写只记为一行「Fix async cancellation behaviour」。整份 CHANGELOG **从头到尾没有一个字**提到 pool 重写、`_assign_requests_to_connections`、`PoolRequest`、`create_connection` 或 `is_available`。**私有面的破坏性变更不会在 changelog 里通知你**——升级 httpcore 时必须直接 diff 源码，不能读发布说明。

**是不是官方认可的扩展点——不是，而且这个沉默有信息量**

httpcore master 的全部 13 个 docs 文件里，对 `create_connection` / `subclass` / `ConnectionInterface` / `is_available` 做 grep 是**零命中**。对照之下 `docs/network-backends.md:168` 明文写着「The base interface for network backends is provided as public API」——pool／connection 一侧**没有对应的这句话**。所以：按「未文档化但稳定的实现细节」对待，不要按 API 契约对待。有利的一面是 httpcore 自己就是这么用的（`AsyncHTTPProxy` 与 `AsyncSOCKSProxy` 都是 `AsyncConnectionPool` 的子类且**只**覆盖 `create_connection()`）。

**httpx 侧 `transport._pool` 替换——不是公认 idiom**

httpx 官方文档 `docs/advanced/transports.md`（454 行）通篇只教「自己实现或包装 `AsyncBaseTransport`」，**全文不提 httpcore、不提 `_pool`**。实证的第三方（httpx-socks、hishel 新旧两版，都读了源码）**都是**自己实现 `AsyncBaseTransport` 并持有自己的 pool，**没有一个**去动 httpx 的 `_pool`。所以我们这条路能用，但「大家都这么做」这层**没有证据**。它唯一的优势是保住了 `AsyncHTTPTransport.__init__` 已经算好的 `ssl_context` 等配置；走文档路子这些要自己重新配齐。

**先例与 upstream 意愿——两条都要知道**

- **encode/httpcore#1088「Respect HTTP/2 stream capacity in connection pool」**（2026-06-13 开，20 文件 +937/-62，**零 comment、零 maintainer 回应**）做的正是这件事，而且**数的是同一份私有状态**（遍历 `self._requests` 取 `request.connection` 计数）。这算是对本方案「读 `pool._requests[*].connection`」的独立佐证。
- **但它带来一个静默降级风险，已在本 PoC 里防住**：该 PR 给 `AsyncConnectionInterface` 新增 `max_concurrent_requests() -> int`，pool 侧写成 `try: connection.max_concurrent_requests() except AttributeError: return 1`。一个只覆盖 `is_available()` 的 wrapper 会让这个查找落到自己身上失败，pool 退回 **1**，于是每条连接被静默限成一个在途请求——**不报错**。`stream_cap.py` 已经加了这个方法的转发（不存在时返回我们自己的 cap），三行成本换掉一次未来的静默行为变更。
- **maintainer 立场明确且与我们方向相反。** tomchristie 在 httpcore#85 引 RFC 7540 §9.1（「Clients SHOULD NOT open more than one HTTP/2 connection to a given host and port pair」）并写道 "we shouldn't just open up a new connection when we hit this limit."。upstream 的价值取向是**撑满一条 H2 连接**而不是横向铺连接。#1088 一年无人理会与此自洽。**不要指望这个能力被上游接纳。**

**真正的断点：httpx 1.0，而且已经在动**

PyPI 上 **httpx `1.0.dev4` 于 2026-08-19（昨天）发布**。拆包看：`Requires-Dist` 只剩 `truststore`，**httpcore 依赖被完全移除**；换成自带的 `_pool.py` / `_connection.py` / `_network.py`，`_transports/` 目录不存在，`_pool.py` 里搜不到 `is_available` / `create_connection` / `max_concurrent`。**httpx 1.0 一落地，本方案的三个挂钩点会同时消失**（httpcore 的 pool、`AsyncConnectionInterface`、`transport._pool`）。

**综合版本判断**：短期风险低（形状自 1.0.3 冻结、httpcore 近乎停止开发、`AsyncConnectionInterface` 五年未变）；中期风险明确且可命名（升级 httpx 到 1.0 会一次性打掉全部挂钩点）。如果实施，配套动作是**把 httpx 与 httpcore 版本钉死并在依赖处写明理由**——理由不是「怕出 bug」，而是「我们依赖了 httpcore 1.0.x 的 pool 分配路径，httpx 1.0 不再有它」。

---

## 未测 / 存疑（不可用于决策）

1. **代理路径**（`AsyncHTTPProxy` / SOCKS）未实际运行验证。
2. **上游边缘对 HTTP/1.1 与 HTTP/2 的行为是否等价**（限流、空闲超时、缓冲、是否有等价的批量连接回收）。只实测了 ALPN 协商成功。
2b. ~~「响应被提前关闭」这个场景本 PoC 没有覆盖。~~ **已补测**，见实验 `early_close_reuse`（第 12 个）。仍未测的是**这个场景在本服务里的真实频率**——那是决定用 `http2 = false` 还是用 cap 的关键数字，我拿不到。
3. **cap 与 `max_connections` 的相互作用**。生产 `build_http_client` 传 `httpx.Limits(keepalive_expiry=...)`，`max_connections` 为 `None` → httpcore 转成 `sys.maxsize`，即**当前无连接数上限**。若将来设了它，cap 会把请求推向「池满 → 排队」，行为未测。
4. **「有没有第三方库已经这么做了」这一项没有查全。** 实际读过源码的 httpx-socks 与 hishel（新旧两版）都没有覆盖 `create_connection` 或按流数限连接；但跨仓库代码搜索没做成（grep.app API 返回非 JSON，GitHub code search 需要 token）。所以这一项只能报告为「样本内没有，全网范围未验证」。
5. **一个 harness 教训，与结论无关但值得记下**：`async with asyncio.Server` 的 `__aexit__` 会 `await wait_closed()`，自 Python 3.12.1 起它会等所有连接处理协程结束——而那些协程正阻塞在 `reader.read()` 上，于是整个 PoC 静默挂死、连一行报错都没有。第二个同类陷阱：`await resp.aiter_bytes().__anext__()` 之后丢弃那个异步生成器，事件循环的终结器会把 `GeneratorExit` 送进 `PoolByteStream.__aiter__`，它的 `except BaseException: await self.aclose()` 会**把请求从 `pool._requests` 里摘掉**——内存探针因此一度报告「100 条连接」而服务端只 accept 了 2 条。两处都已修正并在代码里留了注释。

---

## 我的推荐

**已按独立评审更正过一次，下面是修正后的版本。**

1. **先用 `upstream_transport.http2 = false` 止血。** 它与 cap=1 在爆炸半径上实测等效，零新代码、零私有 API。**但要知道它的代价**：响应被提前关闭时（客户端取消上游 SSE）会丢掉整条连接并重新握手，而 h2 不会。**决定前建议查一个数：本服务里「上游响应被提前关闭」有多频繁。** 频率低 → 直接用这个开关；频率高 → 第 2 条的性价比上升。
2. **「能配置每连接流数」这个能力本身完全可实现**（用户已裁决要它，我不替用户砍需求）。按候选 2 实现，配套三件事：
    - 配置校验只需一条：**不超过上游通告的 `MAX_CONCURRENT_STREAMS`（当前实测为 100）**。超出部分只会在连接内排队。
    - 用「服务端 accept 计数 == ⌈N/cap⌉」的冒烟测试兜住第 2 处私有依赖的**静默失效**，**不要**只断言「没抛异常」——那正是它失效时的表现。
    - wrapper 转发 `max_concurrent_requests()`（已在 `stream_cap.py` 里做了），抵消 httpcore #1088 若合并带来的静默降级；并把 httpx／httpcore 版本钉死写明理由（**httpx 1.0.dev4 已于 2026-08-19 发布且完全移除 httpcore**，三个挂钩点届时同时消失）。
3. **默认值我不给推荐数。** N=1 有构造上的保证（一次连接事件最多伤一条），但那样就该先问第 1 条为什么不直接关 h2；N≥2 的具体取值缺一个我们现在拿不到的数——GOAWAY 到达时该连接上的在飞流数。**原稿写的「默认取 2」是拍脑袋，已撤回**，理由见「cap 取值」一节。想要有依据的取值，先补 connection id 到日志里（`findings.md` 未决表第一条）。
4. **不要**做候选 3（方向错误，实测无效），**不要**做候选 4（能力更弱、代码更多）。
5. **一条应当影响裁决的外部事实**：httpcore maintainer 在 #85 明确表态不应在撞到流上限时新开连接（引 RFC 7540 §9.1），做同一件事的 PR #1088 开了两个月零回应。**这个能力不会被上游接纳，我们要长期自己背着它。**
6. **回传给取证报告作者**：POST 窗口残留的 5.9% 与 victims/event=2.19，在 N=1 下不可能来自单条连接事件；只能是上游 node 级多连接回收，或时间窗聚簇把独立失败算作一批。无论哪种，**任何 per-connection cap 都治不了它**——这是「cap 能买到什么」的上界。
