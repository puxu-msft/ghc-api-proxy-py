# 上游 GOAWAY 打掉在飞流式请求

**状态**：活文档。诊断已收敛；六处修复已落地；一处接线待做；两处待裁决（见 [`deferred.md`](deferred.md)）。
**本文是入口**：目录导览与证据地图在 [`README.md`](README.md)，过程产物在 `archive-260820/`（九份），只在需要证据时去读。

---

## 发生了什么

2026-08-20 15:01:59，四条流式请求在同一秒集体 `[FAIL]`，异常均为：

```
httpcore.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647>
```

四条请求起始时刻不同（散布约 10 秒），结束秒相同，异常形状相同。**这是一个共同的连接层事件，不是四次独立失败。**

**它有多常见**：现网 `copilot-api-js` 的 history，2026-07-17..08-19、21 个日历日、93125 条请求，传输层打断 594 条 = **0.64%**，繁忙日 178–235 次/天；算上重试恢复的约 1%。取证详见 `archive-260820/260820-goaway-frequency-forensics.md`。

**主导变量是时长，而本次不是**：危险率从 <5 秒的 0.011% 涨到 160–320 秒的 24.9%。本次四条是 5.3–15.9 秒，**落在最低危险区**——独立佐证了它不是那个慢性机制，就是一次连接级事件。请求大小、模型选择、「每天固定的部署窗口」三条假说均被证伪。

## 为什么

上游发的是 RFC 9113 §6.8 推荐的 **graceful-shutdown 首帧**：`NO_ERROR` + `last_stream_id=2^31-1`。RFC 对这类流的措辞是 `might still complete successfully`——可能继续成功，**不保证**。

而 httpcore 1.0.9 收到任意 GOAWAY 后，**任何还需要再次发起网络读取的流**都会在 `_receive_events` 入口被判死（`http2.py:352-355`）。哨兵值 `2^31-1` 是合法 stream id 的最大值，于是 `stream_id > last_stream_id` 恒假，唯一的可重试出口 `ConnectionNotAvailable` 对全体在飞流不可达。

两点必须一起说，否则会误导修复方向：

- **hyper-h2 也参与**：`RECV_GOAWAY` 无条件把连接状态转为 `CLOSED`，closed 态没有 `RECV_DATA` transition。删掉 httpcore 那个提前抛错也不够——这是**集成栈**的问题。
- **存在第三条路，且已实测**：`_receive_stream_event` 在队列非空时不调用 `_receive_events`。DATA+`StreamEnded` 排在 GOAWAY **之前**落进同一次读取时，该流在哨兵值 GOAWAY 之下**正常读完并成功返回**。所以缺口是「**不会为已受理的流发起新的网络读取**」，不是「没有第三种结果」。

## 已经确凿的 / 仍然未决的

| 确凿（源码 + 白盒 + 端到端实测） | 未决（可查，但尚未查） |
|---|---|
| httpcore 使「还需再次网络读取」的流在 GOAWAY 后失败 | 四条请求是否共用同一条 H2 连接（当时日志无 connection id；**结构化日志已落地，下次可答**） |
| 同连接多条并发流一起死（双流实测 3/3） | 「上游响应被提前关闭」的频率——**唯一能区分 h2+cap 与 HTTP/1.1 的量**，现已可测 |
| 已排队完整终止事件的流可正常完成（3/3） | 本项目自身的传输失败频率（此前零生产数据，日志刚上线） |
| `last_stream_id=0` 因 Python 真值判断同样致命 | 裸 `h2.ProtocolError` 在生产中出现的概率 |
| 裸 `h2.ProtocolError` 不被包装、绕开我方全部捕获边界 | |
| 传输层打断约占请求的 0.64%，时长是主导变量 | |

### 不可知项——不要再把它们当成待查

用户裁决（2026-08-20）：**发 GOAWAY 的是什么，我们不可能知道，不能据此分析；只能根据收到的内容决定。**

所以下面这些**从表里移除**，不是因为查清了，而是因为它们**在我们这一侧原理上不可判定**，留在「未决」栏里会持续吸引投入却永远不会关闭：

- 发 GOAWAY 的是源站、边缘节点、还是中间 TLS 终止节点；
- 上游为何在此刻回收连接（连接寿命上限？滚动更新？负载再平衡？）；
- 对端在 GOAWAY 之后本来会不会继续传输——我方栈收到该帧即停止读取，这一半在任何日志里都不会出现。

**设计推论，比上面三条更重要**：既然「谁发的、为什么发」不可知，那么恢复策略**不能**建立在对端意图之上。唯一可依据的是**我们已经收到了什么**——已完成的块、已到的语义位置、已发给客户端的字节。这条直接决定了下面「重试 / 续写 / 完成」那件事的形状：它必须是一个读**已收内容**的裁决，而不是一个读异常类型的裁决。

## 已修复

**HTTP/1.1 上游开关**（裁决 2026-08-20）。新增 `upstream_transport.http2`（默认 `true`），设 `false` 即与上游协商 HTTP/1.1，每个请求独占连接，一帧 GOAWAY 最多打掉一个请求。代价是握手与连接数上升。

顺带修掉一个陷阱：此前决定协议的是 `upstream_transport.http2_ping_interval > 0`——一个以「PING 间隔」命名的键**静默地**决定了走哪个协议，而找 HTTP/1.1 开关的人没有理由去看它。**并且 `http2_ping_interval` 从来没产生过任何 PING**：httpx 0.28.1 与 httpcore 1.0.9 都不提供 HTTP/2 PING 间隔接口，全仓也只有那一处读它。该键予以保留（它是用户亲笔配置里的键，背后有 spec），但已在 schema 中标注为当前传输层未实现，且不再影响协议选择。

**STR-04 的 SSE 信封一半**（`16dd68c`）。与本次故障相邻但独立：一个没有合法终止事件的 EOF，此前被 flush 成 `message_delta{stop_reason:"end_turn"}` + `message_stop`，把截断的 turn 伪装成干净结束存进客户端历史。现在发 Anthropic SSE `error`（`upstream_error` ／ `incomplete_responses_stream`），且不再跟发 `message_stop`。从 legacy 移植而非重新设计。

**未闭合的另一半**：failed History。`context.reply` 仍 gate 在 `terminal.seen`，需与该 gate 的放宽一同裁决——那是 hooks／History 的契约变更。见 `docs/agents/anthropic-responses-bridge/implementation.md` 结构怪味登记。

**结构化请求日志**（`10e4811`）。每条完成的请求写一行 JSON 到 `<user_data>/requests/requests-YYYYMMDD.jsonl`，按天分文件保留 14 天，派生路径不新增配置键。**连接标识零私有 API**：httpcore 把 `network_stream` 放进 `Response.extensions`、H2 另给 `stream_id`，`client_addr` 就是这条 TCP 连接在本机的名字，还能直接和 `ss -tnp` 对上。

一个实测出来的坑已处理：连接关闭后 `get_extra_info("client_addr")` 抛 `OSError: Bad file descriptor`，而完成行是在 response 释放**之后**才写的——所以地址在响应头到手那一刻就被拷成字符串。

记录是既有聚合记录 `RequestLine` 的序列化，**不是同一批事实的第二次抽取**；状态词与控制台前缀共用同一个 `status_for` 调用。调研见 `archive-260820/260820-structured-log-survey.md`。

**三条路的裁决**（`5c1afbe`）。`decide_stream_ending()`：读 `terminal_seen` / `downstream_opened` / `committed_blocks` 与重试预算，返回 COMPLETE / REPLAY / CONTINUE / ABANDON。规则本就写在 `retry.py` 的 docstring 里（「replay 只在客户端一无所见时合法，之后只剩 continuation」），机器也早就有（`continuation_messages`、`RetryReason.CONTINUATION`、配置项）——**缺的一直是裁决本身，那些件此前只被测试引用**。

三个刻意的设计：**异常类型不是输入**（干净 EOF 与连接撕裂把客户端留在同一位置，决定合法性的是位置而非到达方式）；**当场扣预算**而非只查询（否则同一条流问两次被资助两次）；**四条路而非三条**——客户端只见过合成 `message_start` 而零块时，重放会发第二个 `message_start`、续写会造出上游拒收的空 assistant turn，两扇门都关着。

已做变异检验：判据反向 / 删掉空块那一格 / 把 `take` 换成 `consider`，三个变异各自被对应测试抓红。

**headers 之前撕裂的连接现在会重试**（`09ef3cc`）。上传途中撞上 GOAWAY 此前被转成 502 交给客户端。判据自己的 docstring 早就写着这类失败可以安全重试（「还没有产生任何客户端可见的响应字节」），但它的元组把承载连接撕裂的那一整类漏在外面——**它为之而写的那个情形从来没匹配上过**。

凡是到达该判据的按定义都是 headers 之前：它服务的那个 `try` 只包住「返回时上游响应头已到」的那次调用。裸 `h2.exceptions.ProtocolError` 在**捕获边界与判据两处**都单独点名，因为没有任何东西包装它——httpcore 只守住 socket 读取，GOAWAY 与其后帧落进同一次读取时，hyper-h2 直接穿过 `isinstance(..., httpx.TransportError)` 抛出。

**成本不构成理由**（裁决 2026-08-20）：一个已经无法继续使用的上游请求就是已经花掉了，不重试并不能把它退回来。此前把 at-least-once 与重复计费列为该项的主要顾虑，那条顾虑已撤销。

## 在建

| | 要做的事 | 状态 |
|---|---|---|
| 裁决的接线 | 让上游 attempt 那一层在流撕裂时读 `decide_stream_ending`：REPLAY 就重开，CONTINUE 就带 `continuation_messages` 重开，ABANDON 才走已落地的 SSE error | **函数已就绪、无调用者。** 排期等待——要动的 `pipeline_app.py`／`handler.py` 正被并行会话大改（`direct_driver` 重构），共用同一棵工作树时同改一文件是互相覆盖而非合并冲突 |

## 待裁决

| 动作 | 状态 |
|---|---|
| **每连接流数上限** | PoC 证明可做：子类化 `AsyncConnectionPool.create_connection()` + 覆写 `is_available()`，12 个实验全对——不设 cap 时 6 条流挤 1 条连接，cap=2 → 3 条连接，cap=1 → 6 条连接；打掉一条连接后 cap=2 只死 2 条、cap=1 只死 1 条，其余存活。详见 `archive-260820/260820-h2-stream-cap-poc.md` |

### ⚠️ 一个必须先纠正的错误：cap=1 不等于 `http2: false`

本文此前多处写「cap=1 在爆炸半径上与 `http2: false` 完全等价」，并据此建议「可以先不做 cap」。**那个推理是错的，已撤回。**

PoC 只测了**一个维度**——爆炸半径（两者都是 6 连接 / 1 伤亡）。把那一个数当成整体比较，等于把一个协议级区别压缩成一个指标。**它们跑的是不同协议**：

- cap=1 **仍然是 HTTP/2**：二进制分帧、HPACK 头压缩、流级 RST 不杀连接、以及上游边缘对 h2 与 h1 可能完全不同的路由与处理。
- `http2: false` 是**放弃 HTTP/2**，退回 HTTP/1.1 的连接模型。

已知的一处具体差异（PoC 实测）：响应被提前关闭时，HTTP/1.1 作废整条连接并重新握手（对 `api.githubcopilot.com` 实测 ~155ms），h2 只丢那条 stream。但差异**不止于此，也不应由这一条代表**——上游怎么对待两种协议，我们这一侧看不全。

旁证：姊妹项目 `copilot-api-js` 在 2026-07-22（`b5892380f`）选的正是 **h2 + 每 session 并发流上限 1**，而不是退回 HTTP/1.1。

所以两者是**两个不同的产品选择**，不是同一件事的两种写法。`http2: false` 已落地可用；每连接流数上限仍是独立的、值得单独裁决的能力。

### 关于「httpx 1.0 会移除 httpcore」这条风险的实际尺度

`0.28.1` **就是最新稳定版**（2024-12-06，已 20 个月无新稳定版）。httpx 1.0.dev4（2026-08-19）把传输层吸收进 `_pool.py`／`_connection.py`／`_network.py`，全包零 httpcore 引用——但**全包搜 `http2`/`h2`/`alpn` 也是零匹配**：HTTP/2 还没写；`ConnectionPool` 只有 100 行，里面写着 `# TODO: concurrency limiting`；复用判据是 `conn.is_idle()`，即 HTTP/1.1 语义。

所以「挂钩点消失」不是近期风险——我们不可能升级到没有 h2 的 httpx。反过来，等它长出 h2 时，每连接流数上限的自然归宿正是那行 `# TODO`。

### 已撤销的待办

- ~~向 httpcore／hyper-h2 上报~~ —— **删除**。这是本文档作者自己臆想的条目，用户从未要求，也没有任何文档完整描述过它是什么。**本项目不修改上游仓库。**
- 原 C「降级 HTTP/1.1」已裁决并落地。
- 原 B「缓冲窗口内重试」已并入「三条路的裁决」。
- 原 A「纳入重试判据」已落地，见上。


### 另一个易踩的坑

`upstream_transport.http2`（本次新增，管活跃 pipeline 链路）与 `UpstreamConfig.http2`（只管 `upstream/client.py` 那条 legacy surface）**是两个不同的键**，名字一样、作用范围不同。改协议时认准前者。

## 一条方法学教训

本次诊断经三轮独立评审、23 条发现，**每一轮都查出「把未观测的说成已确认」**，第二轮那条还是我在修第一轮问题的过程中新引入的，第三轮推翻了一条我写死的结论（「没有第三条路」）——推翻它的是**实测**，三轮纯文本评审都没查出来。

结论：**加评审轮次治不了过度断言，先做 PoC 才治得了。** 同时，五份文档 128KB 对应两页可行动内容，这个产出比本身就是问题；后续同类工作应当短诊断 + PoC + 一轮评审 + 立刻落地已裁决部分。
