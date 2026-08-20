# 上游 GOAWAY 打掉在飞流式请求

**状态**：活文档。诊断已收敛；四处修复已落地；一处接线待排期；两处待裁决。
**本文是入口**：过程产物在 `docs/tmp/260820-*.md`（八份：三轮评审、PoC、取证、调研），只在需要证据时去读。

---

## 发生了什么

2026-08-20 15:01:59，四条流式请求在同一秒集体 `[FAIL]`，异常均为：

```
httpcore.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647>
```

四条请求起始时刻不同（散布约 10 秒），结束秒相同，异常形状相同。**这是一个共同的连接层事件，不是四次独立失败。**

**它有多常见**：现网 `copilot-api-js` 的 history，2026-07-17..08-19、21 个日历日、93125 条请求，传输层打断 594 条 = **0.64%**，繁忙日 178–235 次/天；算上重试恢复的约 1%。取证详见 `docs/tmp/260820-goaway-frequency-forensics.md`。

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

记录是既有聚合记录 `RequestLine` 的序列化，**不是同一批事实的第二次抽取**；状态词与控制台前缀共用同一个 `status_for` 调用。调研见 `docs/tmp/260820-structured-log-survey.md`。

**三条路的裁决**（`5c1afbe`）。`decide_stream_ending()`：读 `terminal_seen` / `downstream_opened` / `committed_blocks` 与重试预算，返回 COMPLETE / REPLAY / CONTINUE / ABANDON。规则本就写在 `retry.py` 的 docstring 里（「replay 只在客户端一无所见时合法，之后只剩 continuation」），机器也早就有（`continuation_messages`、`RetryReason.CONTINUATION`、配置项）——**缺的一直是裁决本身，那些件此前只被测试引用**。

三个刻意的设计：**异常类型不是输入**（干净 EOF 与连接撕裂把客户端留在同一位置，决定合法性的是位置而非到达方式）；**当场扣预算**而非只查询（否则同一条流问两次被资助两次）；**四条路而非三条**——客户端只见过合成 `message_start` 而零块时，重放会发第二个 `message_start`、续写会造出上游拒收的空 assistant turn，两扇门都关着。

已做变异检验：判据反向 / 删掉空块那一格 / 把 `take` 换成 `consider`，三个变异各自被对应测试抓红。

## 在建

| | 要做的事 | 状态 |
|---|---|---|
| 裁决的接线 | 让上游 attempt 那一层在流撕裂时读 `decide_stream_ending`：REPLAY 就重开，CONTINUE 就带 `continuation_messages` 重开，ABANDON 才走已落地的 SSE error | **函数已就绪、无调用者。** 排期等待——要动的 `pipeline_app.py`／`handler.py` 正被并行会话大改（`direct_driver` 重构），共用同一棵工作树时同改一文件是互相覆盖而非合并冲突 |

## 待裁决

| | 动作 | 为什么需要裁决 |
|---|---|---|
| A | 把 GOAWAY 类错误纳入 headers-pending 重试判据 | 「客户端还没看见响应」只让重试**对下游可隐藏**，不代表上游没处理过第一次 POST。要接受 at-least-once 与**重复计费**。且须按 `ConnectionTerminated` 窄匹配，不能整类纳入 |
| E | 向 httpcore／hyper-h2 上报 | 对外动作。上报须同时覆盖两层，只报 httpcore 会让对方以为改一处条件即可 |
| 每连接流数上限 | PoC 证明可做（子类化 `AsyncConnectionPool.create_connection()` + 覆写 `is_available()`，12 个实验全对），但**cap=1 在爆炸半径上与已落地的 `http2: false` 完全等价**（实测 6 连接/1 伤亡，两者一致）。唯一差异：提前关闭响应时 H1 要重握手（实测 ~155ms），h2 只丢那条 stream——**裁决点是那个频率，现已可测**。用户已问过版本风险，答案在下方 | 详见 `docs/tmp/260820-h2-stream-cap-poc.md` |

（原 C「降级 HTTP/1.1」已裁决并落地。原 B「缓冲窗口内重试」已并入「三条路的裁决」。）

### 关于「httpx 1.0 会移除 httpcore」这条风险的实际尺度

`0.28.1` **就是最新稳定版**（2024-12-06，已 20 个月无新稳定版）。httpx 1.0.dev4（2026-08-19）把传输层吸收进 `_pool.py`／`_connection.py`／`_network.py`，全包零 httpcore 引用——但**全包搜 `http2`/`h2`/`alpn` 也是零匹配**：HTTP/2 还没写；`ConnectionPool` 只有 100 行，里面写着 `# TODO: concurrency limiting`；复用判据是 `conn.is_idle()`，即 HTTP/1.1 语义。

所以「挂钩点消失」不是近期风险——我们不可能升级到没有 h2 的 httpx。反过来，等它长出 h2 时，每连接流数上限的自然归宿正是那行 `# TODO`。

### 想动 A 的话，先看这个

裸 `h2.exceptions.ProtocolError` **连捕获边界都进不去**：

```python
# src/app/ghc_client/client.py
except (httpx.TransportError, OpenAIAPIConnectionError) as error:
    if is_responses_headers_pending_transport_error(error):
```

它两个类型都不是。**只改 `transport.py` 的判据元组不会让判据被调用到**，必须先改捕获边界。

### 另一个易踩的坑

`upstream_transport.http2`（本次新增，管活跃 pipeline 链路）与 `UpstreamConfig.http2`（只管 `upstream/client.py` 那条 legacy surface）**是两个不同的键**，名字一样、作用范围不同。改协议时认准前者。

## 一条方法学教训

本次诊断经三轮独立评审、23 条发现，**每一轮都查出「把未观测的说成已确认」**，第二轮那条还是我在修第一轮问题的过程中新引入的，第三轮推翻了一条我写死的结论（「没有第三条路」）——推翻它的是**实测**，三轮纯文本评审都没查出来。

结论：**加评审轮次治不了过度断言，先做 PoC 才治得了。** 同时，五份文档 128KB 对应两页可行动内容，这个产出比本身就是问题；后续同类工作应当短诊断 + PoC + 一轮评审 + 立刻落地已裁决部分。
