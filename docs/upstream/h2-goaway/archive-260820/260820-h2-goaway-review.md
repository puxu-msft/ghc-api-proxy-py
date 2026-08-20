# 独立评审：H2 GOAWAY 故障诊断报告

日期：2026-08-20
评审对象：`docs/tmp/260820-h2-goaway-inflight-wipeout.md`
评审基线：commit `002c2486c0ab4376f6fe59b2caecadd72c94f65d`
评审者：异源 agent（agent type `gpt-opus`——GPT 系列模型，非 Claude Opus），独立核对，未采信原报告转述
结论：**needs-fix**，major=4、moderate=4，共 8 条

> 落盘说明：评审 agent 的 harness 禁止其创建 Markdown 报告文件，本文件由主会话代为落盘。**下方 findings 是评审者返回文本的压缩转写，不是原文**——保留了全部结论与「正确表述」，但省略了原报告逐项列出的实际命令、源码输出与部分限定文字。末尾「处置」一节由主会话添加。

---

## 发现

### F1｜major｜RFC 语义和「上游无过」结论被显著说强了

原报告把初始 GOAWAY 解释为「已经在飞的流照常跑完」「明确告诉我们在飞请求不受影响」「上游做法礼貌且正确」，并据此把生产根因封口为 httpcore。

RFC 9113 §6.8 原文（评审者实取）：

```text
Activity on streams numbered lower than or equal to the last stream
identifier might still complete successfully. The sender of a GOAWAY
frame might gracefully shut down a connection by sending a GOAWAY
frame, maintaining the connection in an "open" state until all in-
progress streams complete.
```

是 `might still complete successfully`，**不是**保证「照常跑完」；保持连接直到所有流完成同样是 `might` 描述的可选行为。该帧形状与 RFC 推荐的 graceful-shutdown 首帧一致，但单凭这一帧无法证明发送方后来保持了连接、继续传输了各流的数据。

另：`2^31-1` **不是**「大于任何可能的 stream id」，而是**等于**合法 31-bit stream identifier 的最大值。（注：这不影响「`stream_id > last_stream_id` 恒假」的结论，只是措辞不准。）

正确表述：

> 该 GOAWAY 的字段组合与 RFC 9113 推荐的 graceful-shutdown 首帧一致。它禁止再开新流，并把所有合法 stream id 纳入「发送方可能已经处理或仍可能处理」的范围；这些在飞流**可能**继续成功，但 GOAWAY 本身不保证发送方一定保持连接直至它们完成。当前栈在看到该帧后立即停止后续网络读取，因此现有日志无法告诉我们生产对端随后本来会继续传输还是也会关闭连接。可以确凿认定的是：当前 httpcore／hyper-h2 栈对该帧的处理足以立即造成观测到的失败；**不能据此认定「上游无过」**。

文档状态「根因已定位」应收窄为「直接触发机制已定位；生产对端在 GOAWAY 后的实际行为未观测」。

### F2｜major｜同一秒只能证明共同触发高度可疑，不能证明四条请求共用同一条 H2 连接

时间计算本身正确，但日志只有秒级结束时间、耗时只有一位小数，只能得到近似起始时间。更重要的是「各自独立失败概率可忽略」依赖失败事件彼此独立，而这个假设没有根据。以下替代解释同样符合现有形状：

1. 四条流在同一条 H2 连接上收到同一帧 GOAWAY。
2. 四条流分布在多条 H2 连接上，同一边缘节点／负载均衡器／滚动更新同时向这些连接发送相同 GOAWAY。
3. 我方某个全局动作间接触发所有对端连接关闭（异常类型使纯本地 timeout／cancel 不是首选解释，但仅凭结束秒不能排除）。
4. 中间 TLS 终止节点而非源站应用发送 GOAWAY。

原报告的连接池理由有两个问题：

- **`↓593B` 是传输字节数，与 `MAX_CONCURRENT_STREAMS` 计数无关，不能证明「远未触及任何流数上限」。**
- httpcore 通常把同 origin 请求复用到已有 H2 连接，但旧连接进入不可用状态且仍有在飞流时，可以**同时存在旧连接和新连接**。四条请求起始时间横跨约十秒，日志又没有 connection id，不能排除跨连接 generation。

正确表述：

> 四条请求在同一秒收到相同形状的 `ConnectionTerminated`，强烈支持一个共同的连接层或上游基础设施事件，不支持四个彼此独立的随机故障。它们是否位于同一条 TCP/H2 连接**仍未直接观测**；单连接 GOAWAY 和多连接同步 GOAWAY 都与现有证据相容。

### F3｜major｜仅凭 `↓593B/595B` 无法认定请求 3、4 下游零 body 字节

`block` 策略**不是**「响应结束前全缓冲」，而是每形成一个完整 block 就立即释放（`src/app/pipeline/delivery/blocks.py:97-101`，`if self.policy == "block": return self._drain()`）。

593B 是网络层累计字节数，不包含事件类型、chunk boundary 或 assembler 状态。一个很短的 text block／tool block 完全可能在这个体积内完成；反过来也可能连一个事件都没有完整到达。没有 cassette、原始 SSE、assembler trace 或下游计数，无法区分。

`240s` 合成计时只证明 5.3～15.9 秒内不会由 timer 主动发送 synthetic `message_start`，**不能证明真实完整 block 未触发发送**。

Starlette 行为确认 HTTP headers 已先提交（`StreamingResponse.stream_response` 先发 `http.response.start` 再迭代 body），这一点原报告无误。

正确表述：

> 合成 headers timer 在这些时长内不会触发；但仅凭上游累计字节数无法判断 assembler 是否已经形成并交付完整 block。请求 3、4 的 body-commit 状态**未观测**，透明重试窗口需要逐请求的下游发送计数或原始事件证据确认。

相应地，「客户端完全无法察觉」和建议 B 对本次请求的适用性必须改成条件句。

### F4｜major｜建议 A 把「未向客户端输出」误写成「请求幂等且可安全重放」

`httpx.RemoteProtocolError` 自身的 docstring 只是 "The protocol was violated by the server."；原报告引用的「响应头之前可以安全重试」来自本项目自定义类 `ResponsesHeadersPendingTransportError`。

MRO 主干原报告给对了，重试元组确实不含 `RemoteProtocolError`。但——

**「客户端尚未看见响应」只说明从下游协议角度可以隐藏第二次尝试，不说明第一次 POST 未被上游处理。** `RemoteProtocolError` 可在完整请求已经发出、上游已经执行乃至返回畸形响应后发生。重发可能带来第二次生成、重复计费或其它上游副作用，因此**不能称为幂等**。

正确表述：

> 当前 classifier 确实不覆盖 `httpx.RemoteProtocolError`。是否纳入 retry policy，需要接受「上游可能已经处理第一次 POST」的 at-least-once 语义和潜在重复计费；「尚无客户端可见响应」只使重试对下游**可隐藏**，不使请求本身幂等。若只想覆盖 GOAWAY，可按异常 cause 中的 `ConnectionTerminated` 字段做更窄的策略裁决，而不是把所有 `RemoteProtocolError` 一概视为低风险。

### F5｜moderate｜缺陷不止在 httpcore 那个分支，hyper-h2 也会在 GOAWAY 后把连接状态置 CLOSED

hyper-h2 4.3.0 在 `RECV_GOAWAY` 时把 `CLIENT_OPEN` 转成 `ConnectionState.CLOSED`；closed 状态没有 `RECV_DATA`／`RECV_HEADERS`／`RECV_WINDOW_UPDATE` 等 transition。**即使删除 httpcore 的提前抛错，后续帧仍会由 hyper-h2 报 `ProtocolError`。**

正确表述：

> 应把问题描述成 **httpcore/hyper-h2 集成栈**无法维持 graceful GOAWAY 后的既有流，而不是暗示改一处条件即可修复。

建议 E「向 httpcore 上报」仍合理，但上报内容应包含 hyper-h2 状态机事实，不应预设修复只在 httpcore。

### F6｜moderate｜「任意 GOAWAY 判死全部在飞流」是过强全称

`_receive_stream_event` 先消费 `self._events[stream_id]` 中已排队的事件，只有队列为空才调用 `_receive_events`。同一次 socket read 可以同时产生某流的 `DataReceived`／`StreamEnded` 和 `ConnectionTerminated`。若一个流的完整余下事件已在该次 read 中排队，它**可以在不再进入 `_receive_events` 的情况下完成**。

准确结论：

> 收到 GOAWAY 后，任何**还需要再次进行网络读取**的流都会在 `_receive_events` 入口抛错；同一次 read 已把 `StreamEnded` 等完整终止事件排入队列的流可能完成。

另一个限定：连接池只在 `handle_async_request` 尚未返回 Response 时捕获 `ConnectionNotAvailable`（`connection_pool.py:234-245`）。Response 已返回后，body 迭代中的该异常向上抛，**不会**由 pool 重发请求。

### F7｜moderate｜traceback 机制说明正确，但「运行进程版本落后」不是唯一解释

机制描述（帧名／行号来自运行 code object，源码文本由 `linecache` 在格式化时读磁盘）核对无误。但证据能力应写窄：

- 多处 function name 与当前磁盘行范围不相容，强烈证明「执行中的 code object 与格式化时磁盘源码不是同一版」。
- 最常见解释确实是进程启动后文件被替换，但也可能是动态 `compile(..., filename=...)`、非原子部署／bind mount 切换、异常的 `.pyc` 复用。**不能仅凭行号唯一证明「运行进程版本落后」，更不能确定具体 commit。**
- `keepalive.py:126` / `stream.py:133` 当前恰好自洽、文件 clean，只说明**没有观测到矛盾**；不能反向证明运行 code object 与当前文件逐字一致——旧版本可能在这些行恰好相同。

### F8｜moderate｜孤儿模块判断正确，但「已具备做块级透明重试的原语」夸大了现有能力

「当前未接线」在当前 checkout 下确认为真。但两个模块实际只提供 `collect_with_limit(stream, cap_bytes) -> bytes` 与 `delayed_first_item(stream, timeout_seconds) -> (first_item, stream)`。

它们**没有**：重建上游请求、区分上游是否已处理、追踪下游实际提交字节、丢弃失败 attempt 的 assembler 状态、重新初始化 converter／accounting、在第二次 attempt 后恢复块级交付。`collect_with_limit` 甚至会收完整个流，与「仅在首个完整 block 前重试」不是同一机制。

正确表述：

> 两个模块是当前生产路径未引用的旧 helper，其中一个有限额收集整个 iterator，另一个延迟取得首项。它们**可能提供局部构件，但并未实现、也不足以直接接出**本报告建议的块级透明重试。

---

## 评审者核对后确认无误的断言（节选）

1. `uv.lock` 锁定 `httpcore==1.0.9`、`httpx==0.28.1`，运行环境 hyper-h2 4.3.0。
2. 原报告对 `httpcore/_async/http2.py:348-355` 的代码引用准确。
3. `last_stream_id == 2**31-1` 时 `stream_id > last_stream_id` 对合法 H2 stream identifier 不可达；hyper-h2 的 `HIGHEST_ALLOWED_STREAM_ID` 实测为 `2147483647`。
4. GOAWAY 后处理不检查 `error_code`，相关分支只读 `last_stream_id`。
5. RFC 9113 确实推荐 graceful shutdown 先发 `last_stream_id=2^31-1`、`NO_ERROR` 的 GOAWAY。
6. `_RESPONSES_PRE_HEADERS_HTTPX_ERRORS` 只含三种，不覆盖 `httpx.RemoteProtocolError`。
7. **标准 CLI 入口 `ghc-api-proxy = app.cli:main` 经 `build_http_client` → `build_chain` → `create_pipeline_app` 走真实 pipeline；`app_factory.py`／`upstream/client.py:create_http_client` 属于另一条 legacy surface。生产 traceback 出现 `server/pipeline_app.py` 与此相符。**
8. **活跃 pipeline 客户端确由 `composition.transport_options()` 设 `http2=transport.http2_ping_interval > 0`，默认 15；设为 0 会使该客户端只协商 HTTP/1.1。建议 C 的配置路径没有找错。**
9. `UpstreamConfig.http2` 只供 legacy 路径使用，不控制标准 CLI 的 pipeline 客户端。
10. `buffered_retry.py` / `delayed_commit.py` 在 production source 中无调用者。
11. `buffering_policy` 默认 `block`，`synthesized_response_headers_after_sec` 默认 240。
12. headers-after-body retry classifier 只作用于 headers pending。
13. `_tracked_delivery` 记录 `accounting.failure` 后重抛；当前代码不会在该路径合成 Anthropic SSE `error` event。
14. Starlette 在迭代 body 前发 `http.response.start`，故 HTTP 200 headers 已提交。
15. `_StreamAccounting._ending()` 记为 `fail` 并保留原异常文本。
16. `keepalive.py:126` 是清理位置而非故障源，cleanup priority 会保留原始异常。
17. 降级 HTTP/1.1 确实取消多路复用；原报告也正确保留了「若边缘节点同时回收所有连接，H1 不能隔离」的前提。
18. 从客户端侧证据无法判断对端为何发 GOAWAY。

---

## 处置（主会话）

**8 条全部采纳。** 主报告已按各条的「正确表述」修订，证据强度表整体重写。

| 发现 | 处置 | 说明 |
|---|---|---|
| F1 RFC 语义说强 | 采纳 | 「照常跑完」改「可能继续成功」；删除「上游无过」定性；`2^31-1` 由「大于」改「等于最大值」 |
| F2 单连接归因 | 采纳 | 降为「共同连接层事件」；**删除 `↓593B` 推流数上限那条论证——它本身是错的** |
| F3 下游零字节 | 采纳 | 降为「未决」；建议 B 的前提改条件句 |
| F4 幂等 | 采纳 | 删除「重试是幂等的」；改为 at-least-once + 重复计费风险；采纳「按 `ConnectionTerminated` 做更窄裁决」的建议 |
| F5 hyper-h2 状态机 | 采纳 | 与 PoC 独立测到的 `Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED` 互相印证 |
| F6 过强全称 | 采纳 | 限定为「还需再次网络读取的流」；补上连接池只在 Response 返回前捕获 `ConnectionNotAvailable` |
| F7 traceback 归因 | 采纳 | 降为「强解释而非唯一解释」；两个自洽帧降为「未发现错位」 |
| F8 孤儿模块能力 | 采纳 | 改为「可能提供局部构件，不足以直接接出」 |

关于 F4 的一处**已撤回的辩解**：初版处置曾写「原文『该类的 docstring』指的是 `ResponsesHeadersPendingTransportError`，指代正确，评审者误读」。复评指出这不是误读——原句是「`httpx.RemoteProtocolError`（MRO：…）不在其中。该类的 docstring 写的是……」，**就近语法先行词就是 `httpx.RemoteProtocolError`**，句子确实读作错误归属。该辩解已撤回：这是原文的事实性歧义，不是评审者的阅读问题。修订版写全类名是正确处置，但处置记录不该反过来撤销一条已采纳的 finding。

未采纳：无。
