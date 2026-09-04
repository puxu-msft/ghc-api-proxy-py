# 下游保活缺陷：ping 的节拍挂在上游事件上，不挂在下游字节上

- 调查时间：2026-08-20
- 触发事件：客户端 `API Error: The operation timed out.`，界面显示 256.9s
- 证据强度约定：每条结论标注**【实测】**（本次亲手复现，可重跑）、**【取证】**（原始记录可复核）、**【读码】**（源码结构，可 grep 复核）、**【未坐实】**（有线索、没证据）

配套取证报告：

- 客户端侧：`docs/tmp/260820-client-timeout-forensics.md`
- 服务端侧：`docs/tmp/260820-server-timeout-forensics.md`

---

> **修订记录（2026-08-20，经独立证伪评审 `docs/tmp/260820-review-downstream-keepalive-defect.md`）**：初版把「该机制能产生这种现象」写成了「事故中确实如此」。第 3、5 节已按 F1 收窄为相容性陈述；第 1 节措辞按 F2 修正；第 6、7 节按 F4、F5 修正。**中心机制主张经独立复核成立，且在 Responses 形状下同样复现；本次 256.97s 事故的因果归因未成立。**

## 结论

**这是一个独立成立的缺陷：不是与上游的保活没做好，而是上游一活跃，我们发给下游的保活就被压住了。**

**但它是不是本次 256.97s 失败的原因，现有证据不足以断定**——见第 5 节。两件事要分开读。

`src/app/pipeline/delivery/stream.py` 的 `_events_with_ping` 把 ping 的倒计时挂在**上游事件**上：每拉到一个上游 SSE event 就重置一次 deadline。而块级交付意味着「上游有事件」与「下游有字节」是两回事——上游正在往一个尚未闭合的块里灌 delta 时，下游一个字节都没有。于是：

- 上游安静 → ping 照发（这时候其实最不需要）；
- 上游活跃但块没闭合 → **一个字节都不发，也一个 ping 都不发**（这时候最需要）。

---

## 1. 【实测】判据与正样本对照

探针 `stream_delivery` 真实入口，`sse_ping_interval=1`。两组都先交付一个完整块令 `started` 为真，然后进入 3 秒观察窗口；**窗口内两组的新增内容字节都是 0**（整次运行各有 6 个 chunk，全部来自计时开始前那个首块——这一点初版写成了「整次 3 秒下游 0 字节」，不准确）。唯一差别是上游在这 3 秒里说不说话：

| 情形 | 观察窗口内发出的 ping |
|---|---|
| 上游每 0.2s 一个 `content_block_delta`，块不闭合 | **0** |
| 上游开块后完全静默（正样本对照） | **2**（1.0s、2.0s） |

正样本对照击发，证明探针本身有分辨力；chatty 那一组的 0 是真的 0，不是探针看不见。

评审方独立重跑得到同样数字，并另用合法的 **OpenAI Responses 事件形状**（`response.reasoning_summary_text.delta` 持续、不发 `response.output_item.done`）复跑，结果一致：chatty 0 ping、silent 2 ping。**该缺陷与 assembler dialect 无关**——因为 ping 的调度发生在 `assembler.push(event)` 之前。

第一版探针两组都是 0，原因是块从未闭合、`started` 一直为假——`elif started: yield PING_FRAME` 根本没到。修正为「先交付一个完整块」后才得到上表。**这本身也是一条独立事实：首块交付之前，ping 完全不存在。**

## 2. 【读码】机制

`src/app/pipeline/delivery/stream.py:43-45`：

```python
while True:
    task = asyncio.ensure_future(anext(events))
    ping_deadline = loop.time() + interval if interval > 0 else None
```

`ping_deadline` 在**外层**循环顶部重置，也就是每拉一个上游 event 重置一次。内层 `asyncio.wait({task}, timeout=...)` 一旦等到 event，就 `break` 回外层，deadline 归零重来。

`stream.py:120-121`：`elif started: yield PING_FRAME`。`started` 只在第一个完整块被 `_commit` 提交、或 240s 合成 `message_start` 之后才为真。

两条合起来，下游静默的上界不是 `sse_ping_interval`，而是**单个内容块从开始到闭合的全部时长**——对一个长 thinking 块来说，这个时长没有上界。

## 3. 【取证】事故现象与该机制**相容**，但不等于已归因

客户端 transcript（`agent-a4710f6edaa96e0bb.jsonl:77-81`）：

| 时刻（UTC） | 事件 |
|---|---|
| 07:45:09.558 | 请求发起 |
| 07:45:12.461 / 12.720 | thinking 块、text 块落盘（`started` 已为真） |
| 07:49:26.532 | `API Error: The operation timed out.` |

即 **最后一个已落盘的块之后 253.81s 没有新块**。这与第 1 节的机制相容：首两块闭合得快所以到了客户端，之后若进入一个长块、上游持续发 delta，我们就会持续不发任何字节。

**但「事故中上游确实持续在发 delta」没有证据，这里只能写到「相容」为止。** 限制有三条，都来自两份取证报告自己的声明：

- transcript 只在完整 block 落盘时才写行，253.81s 是**静默的上界**，看不见块内 delta，也看不见字节时序；
- 服务端**对这次请求没有任何记录**（`Chain` 无 `HistoryStore`，无文件日志），无法从我方侧复核；
- `CLAUDE_CODE_MAX_RETRIES=30` 开着而客户端重试不落盘，所以这 256.97s 未必是同一条下游连接的连续静默。

有一条**条件性推断**可以记下来，但它的条件目前没被满足，因此不能当结论用：`started` 为真之后，只要上游连续静默达到 15s，ping 就会发出；而第 4 节实测的那个客户端计时器由字节重置。**如果**击发者就是那个计时器，则上游在事故窗口内不曾有过 15s 的静默——也就是 chatty 分支。但第 5 节说明击发者未被坐实，所以这个「如果」还悬着。

## 4. 【实测】客户端那一侧的天花板

Claude Code 2.1.237 是 Bun 编译产物。判断端点是否 first party 的依据是 `ANTHROPIC_BASE_URL` 的 host 是否为 `api.anthropic.com`（bundle 内 `om()`／`$ut()`／`sDe()`）；指向 `localhost:4141` 时判否，于是 `fetch` 的 `timeout: false` **不会**被设上（只有 first party 才关），它自己的 byte-watchdog 也不安装（`qja()` 要求 first party）。留在原位的是 Bun 内置的 fetch 超时。

用 Bun 1.3.14 直接测这个超时的形态，三路探针：

| 探针 | 服务端行为 | 结果 |
|---|---|---|
| A | 立即发响应头，之后永不发 body 字节 | **300.0s 抛 `TimeoutError: The operation timed out.`** |
| B | 立即发响应头，之后每 15s 发一个 `: ping\n\n` | **跑到 420s 仍存活** |
| C | 连响应头都不发 | **300.0s 抛同样的错** |

三条事实：

1. 用户看到的错误串与 A／C 抛出的**逐字一致**，来源就是这个超时。
2. 它是**空闲**超时，由 body 字节重置——**SSE 注释帧算数**，B 证明了这一点。所以「发 ping 能救」这个前提是成立的，问题只在于我们没发。
3. 它与客户端 `settings.json` 里那三个 1 200 000ms 的开关无关，那三个控的是 Claude Code 自己的计时器，管不到 Bun 的。

## 5. 【未坐实】300s 与 256.97s 之间那 43 秒

实测天花板是 300s 空闲，事故是在最后一个已落盘块之后 253.81s 击发的，比 300s **早了约 43 秒**。这个差额本次没有取到证据，不作推测。两个候选（均未验证）：`CLAUDE_CODE_MAX_RETRIES=30` 开着而客户端重试不落盘，因此真正超时的那次 fetch 未必始于 07:45:09.558；或者链路上还有一个我们没测到的计时器。

**这一节的诚实结论是：本次 256.97s 失败的击发者未被坐实，因而不能说这个缺陷解释了它，也不能说修掉它就一定不再复现。** 尤其第二个候选如果是一个**总时限**而非空闲计时器，那么「不再静默」对它无效——初版写的「任何一个候选都会被不再静默消掉」在逻辑上不成立，已删除。

该缺陷值得独立修复，理由不依赖本次事故：它能造成不受 `sse_ping_interval` 约束、无上界的下游静默，而第 4 节已实测证明这条链路上确实存在一个由字节重置的 300s 空闲杀手。

## 6. 顺带查实的另外三件事

- **【读码】上游那两个「保活」旋钮名不副实**（`src/app/server/composition.py:60-81`）。`tcp_keepalive_interval` 被传成 `httpx.Limits(keepalive_expiry=15.0)`——那是**空闲连接池里连接的存活期**，socket 上从未设过 `SO_KEEPALIVE`；`http2_ping_interval` 只被用作 `http2 = interval > 0` 的布尔开关，**没有任何地方按这个间隔发 HTTP/2 ping**。与本次事故无关，但两个配置项的名字都在承诺它们没做的事。
- **【读码】`client_delivery.hedge` 只有配置项没有实现**。`rg 'hedge' src/ -g '*.py'` 只命中 `config/schema.py` 的定义与引用，没有任何消费方。人写配置文档里说它是用来兜「Claude Code 的 no-real-content watchdog 尾部」的，但这条兜底目前不存在。
- **【读码】`streaming/keepalive.py` 里的两个 liveness 生成器完全没有生产接线**。`session_liveness_stream` 与 `keepalive_stream` 在 `src/app/` 内没有任何模块外调用者；旧链路的 `app/streaming/sse.py` 只从该文件 import 了通用清理函数 `finish_stream_cleanup`。另外 `timeouts.stream_idle` 的生产调用点只有旧链路的 `src/app/routes/anthropic.py:217`，新链路 `server/pipeline_app.py` 不调用它。这与既有的「守卫被留在了 legacy 链路上」是同一形态。
- **【读码】既有单测没有覆盖这个形状，且有一条断言在存在性上无分辨力**。`tests/unit/test_stream_delivery.py:227-231` 只证明「完整块之后上游静默 1.2s 会发 ping」，`:236-240` 证明「首块前静默不发 ping」，没有任何测试让上游以小于 interval 的间隔持续发 delta 并保持块未闭合。`:197-199` 的 `test_a_keep_alive_carries_no_content` 断言 `all(chunk != PING_FRAME or chunk.startswith(b":"))` 对常量 `PING_FRAME = b": ping\n\n"` 恒真，零 ping 时也为真——它检查不了 ping 是否存在。20 条测试全绿，但这个绿灯对本缺陷没有分辨力。

## 7. 建议的处置方向（未实施，待裁决）

核心一条：**保活的计时基准必须从「上次上游事件」改成「上次向下游写出字节」**。

**这不是一行位置的改动**（初版的工程判断被评审否掉，正确）。`_events_with_ping` 的输入是上游 bytes、输出是 `SseEvent | None`，它既看不见 assembler 有没有闭合块，也看不见 `stream_delivery` 实际向下游 yield 了什么。把 `ping_deadline` 挪到外层循环之外，只能得到一个**不再被上游事件重置的周期计时器**，那不是按下游字节计时。两条路：

- **周期 ping**：改动最小，语义是「下游静默不超过 interval」。若合同只要求这个，它就够。
- **按下游写出计时**：需要把计时器放到能观察 `stream_delivery` yield 的层级，或由 `stream_delivery` 向下回传一个「刚写出过」的反馈。改动更大，但语义与「保活」的字面承诺一致。

另需一条针对性回归测试补上第 6 节说的缺口：上游以小于 interval 的间隔持续发 delta、块不闭合，断言 ping **存在**（不要复用那条恒真断言的形状）。

需要用户裁决的四点：

1. **上面两条路选哪条。**
2. **首块之前要不要也发 ping。** 目前 `started` 为假时连 ping 都不发，只有 240s 的合成 `message_start` 一次性把头冲出去。若把 ping 提前到首块之前，等于承诺「200 + 一个注释」这种形态，`docs/tmp/260820-review-synthetic-start-fix.md` 第 7 节此前比较过并选择了 `message_start`，改动需要一并重新裁决。
3. **`synthesized_response_headers_after_sec` 的 240s 起算点。** 现在是从上游响应头到达之后起算，请求受理到上游首字节这一段完全没覆盖。
4. **`hedge` 要不要实现**，还是从配置里撤掉——现在它是一条写在人写文档里、实际不存在的兜底。
