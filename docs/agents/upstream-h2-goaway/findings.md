# 上游 GOAWAY 打掉在飞流式请求

**状态**：活文档。诊断已收敛，一处修复已落地，四处待裁决。
**本文是入口**：过程产物在 `docs/tmp/260820-h2-goaway-*.md`（五份，含三轮评审），只在需要证据时去读。

---

## 发生了什么

2026-08-20 15:01:59，四条流式请求在同一秒集体 `[FAIL]`，异常均为：

```
httpcore.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647>
```

四条请求起始时刻不同（散布约 10 秒），结束秒相同，异常形状相同。**这是一个共同的连接层事件，不是四次独立失败。**

## 为什么

上游发的是 RFC 9113 §6.8 推荐的 **graceful-shutdown 首帧**：`NO_ERROR` + `last_stream_id=2^31-1`。RFC 对这类流的措辞是 `might still complete successfully`——可能继续成功，**不保证**。

而 httpcore 1.0.9 收到任意 GOAWAY 后，**任何还需要再次发起网络读取的流**都会在 `_receive_events` 入口被判死（`http2.py:352-355`）。哨兵值 `2^31-1` 是合法 stream id 的最大值，于是 `stream_id > last_stream_id` 恒假，唯一的可重试出口 `ConnectionNotAvailable` 对全体在飞流不可达。

两点必须一起说，否则会误导修复方向：

- **hyper-h2 也参与**：`RECV_GOAWAY` 无条件把连接状态转为 `CLOSED`，closed 态没有 `RECV_DATA` transition。删掉 httpcore 那个提前抛错也不够——这是**集成栈**的问题。
- **存在第三条路，且已实测**：`_receive_stream_event` 在队列非空时不调用 `_receive_events`。DATA+`StreamEnded` 排在 GOAWAY **之前**落进同一次读取时，该流在哨兵值 GOAWAY 之下**正常读完并成功返回**。所以缺口是「**不会为已受理的流发起新的网络读取**」，不是「没有第三种结果」。

## 已经确凿的 / 仍然未决的

| 确凿（源码 + 白盒 + 端到端实测） | 未决（不可用于决策） |
|---|---|
| httpcore 使「还需再次网络读取」的流在 GOAWAY 后失败 | 四条请求是否共用同一条 H2 连接（日志无 connection id） |
| 同连接多条并发流一起死（双流实测 3/3） | 生产对端在 GOAWAY 后实际做了什么（我方停止读取，看不到） |
| 已排队完整终止事件的流可正常完成（3/3） | 发 GOAWAY 的是源站还是边缘／中间 TLS 终止节点 |
| `last_stream_id=0` 因 Python 真值判断同样致命 | 裸 `h2.ProtocolError` 在生产中出现的概率 |
| 裸 `h2.ProtocolError` 不被包装、绕开我方全部捕获边界 | 上游为何在此刻回收连接 |

## 已修复

**STR-04 的 SSE 信封一半**（`16dd68c`）。与本次故障相邻但独立：一个没有合法终止事件的 EOF，此前被 flush 成 `message_delta{stop_reason:"end_turn"}` + `message_stop`，把截断的 turn 伪装成干净结束存进客户端历史。现在改为发 Anthropic SSE `error`（`upstream_error` ／ `incomplete_responses_stream`），且不再跟发 `message_stop`。从 legacy 移植而非重新设计。

**未闭合的另一半**：failed History。`context.reply` 仍 gate 在 `terminal.seen`，需与该 gate 的放宽一同裁决——那是 hooks／History 的契约变更。见 `docs/agents/anthropic-responses-bridge/implementation.md` 结构怪味登记。

## 待裁决（四条，均未实施）

| | 动作 | 为什么需要裁决 |
|---|---|---|
| A | 把 GOAWAY 类错误纳入 headers-pending 重试判据 | 「客户端还没看见响应」只让重试**对下游可隐藏**，不代表上游没处理过第一次 POST。要接受 at-least-once 与**重复计费**。且须按 `ConnectionTerminated` 窄匹配，不能整类纳入 |
| B | 在块级缓冲窗口内重试 | 前提「失败时下游零字节」当前**未观测**；孤儿 helper（`buffered_retry`／`delayed_commit`）只提供局部构件，远不够 |
| C | `upstream_transport.http2_ping_interval: 0` 降级 HTTP/1.1 | 纯配置、可立即实验。但收益取决于回收的是单条连接还是整节点全部连接，**当前证据无法区分** |
| E | 向 httpcore／hyper-h2 上报 | 对外动作。上报须同时覆盖两层，只报 httpcore 会让对方以为改一处条件即可 |

**注意一个易踩的坑**：活跃链路上决定是否启用 HTTP/2 的开关是 `upstream_transport.http2_ping_interval`（`composition.py:70`），**不是** `UpstreamConfig.http2`——后者只控制 legacy 路径。

### 想动 A 的话，先看这个

裸 `h2.exceptions.ProtocolError` **连捕获边界都进不去**：

```python
# src/app/ghc_client/client.py
except (httpx.TransportError, OpenAIAPIConnectionError) as error:
    if is_responses_headers_pending_transport_error(error):
```

它两个类型都不是。**只改 `transport.py` 的判据元组不会让判据被调用到**，必须先改捕获边界。

## 一条方法学教训

本次诊断经三轮独立评审、23 条发现，**每一轮都查出「把未观测的说成已确认」**，第二轮那条还是我在修第一轮问题的过程中新引入的，第三轮推翻了一条我写死的结论（「没有第三条路」）——推翻它的是**实测**，三轮纯文本评审都没查出来。

结论：**加评审轮次治不了过度断言，先做 PoC 才治得了。** 同时，五份文档 128KB 对应两页可行动内容，这个产出比本身就是问题；后续同类工作应当短诊断 + PoC + 一轮评审 + 立刻落地已裁决部分。
