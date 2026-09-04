# 评审：deadline 合成物从「空内容块」改为「只发 message_start」

- **评审对象**：工作树未提交改动 `src/app/pipeline/delivery/stream.py`、`tests/unit/test_stream_delivery.py`（第二片）；顺带确认第一片 `src/app/pipeline/anthropic_request_hook.py`、`src/app/server/handler.py`、`tests/unit/test_blank_text_blocks.py` 未被破坏。
- **基线**：`/home/xp/src/ghc-api-proxy-py`，`git HEAD` 之上的未提交改动，2026-08-20 读取。工作树有同伴并行改动（`observability/`、`server/composition.py` 等），与本次评审面无交叉。
- **总体判定**：**pass**。**blocker 0**、应改 2（均非代码缺陷：一项文档冲突需用户裁决，一项缺失用例）、建议 3、不同意但可接受 0。
- **我实际跑过的东西**：`tests/unit/test_stream_delivery.py` + `tests/unit/test_blank_text_blocks.py`（30 passed，7.00s）；两个一次性探针 `/tmp/probe_stream_shape.py`、`/tmp/probe_shield_noise.py`（只读导入 `src/app`，不改仓库）；对 `~/.claude/projects/-home-xp-src-ghc-api-proxy-py/` 下 564 个 transcript 的只读统计；官方流式文档一手抓取。未改动仓库任何源码或测试。

---

## 1. 正确性：deadline 分支没有 `if not started` 守卫，安全吗

**判定：没问题，守卫不需要加；加了反而是死代码，还会遮蔽下面这条不变量。**

顺控制流证实（`src/app/pipeline/delivery/stream.py`）：循环体内 `started` 只可能在两处变为 `True`。

1. `stream.py:117`，即 deadline 分支本身，而该分支第一行 `stream.py:113` 就 `response_started.set()`。
2. `stream.py:131-132`，`_commit` 产出了 chunk 才置位；而要走到这里必须 `blocks` 非空，`stream.py:122-126` 在进入 `for block in blocks` **之前**已经 `response_started.set()`。

（`stream.py:136-139` 的第三处置位在循环之外，与本分支无关。）

于是循环内成立：`started == True ⟹ response_started.is_set()`。取逆否：`not response_started.is_set() ⟹ not started`。而 deadline 分支的条件 `stream.py:108-112` 恰恰包含 `not response_started.is_set()`。因此进入该分支时 `started` **必然**为 `False`，不可能发出第二个 `message_start`；分支自身也因首行置位而只进一次。

顺带核验一个更隐蔽的窗口：`_events_with_ping` 在 `stream.py:52-56` 也读 `response_started`，但消费端 `stream.py:108-112` 会**自行重新校验**开关与时钟；生成器与消费端在同一事件循环里顺序交替，不存在「块已到达但一个陈旧的 `None` 仍触发合成」的竞态。

实测旁证：探针 C（deadline 触发后再来两个真实块）输出块 index 为 `[0, 1]`，事件序列只有一个 `message_start`。

## 2. 协议合法性

**判定：合法。**

一手依据（2026-08-20 抓取 `https://platform.claude.com/docs/en/build-with-claude/streaming`，原 `docs.claude.com` 链接 302 到此）：

- 事件流程原文：「1. `message_start`: contains a `Message` object with empty `content`. 2. A series of content blocks... 3. One or more `message_delta` events... 4. A final `message_stop` event.」另一处措辞是「**Potentially** multiple content blocks」。
- ping：「Event streams may also include any number of `ping` events.」「There may be `ping` events dispersed throughout the response as well.」
- 未知事件：「new event types may be added, and your code should handle unknown event types gracefully.」

文档对 `message_start` 与首个 `content_block_start` 之间的**时间间隔没有任何约束**。我方保活发的是 SSE 注释 `: ping`（`stream.py:18`），比 `ping` 事件更惰性，任何合规 SSE 解析器都会忽略注释行。

与正常路径相比，客户端可观察的差异**只有时序**：`message_start` 提前到第 240 秒；随后是若干注释；真实块仍从 index 0 开始、顺序不变。`message_start` 的 payload 本来就是 `content: []`（`anthropic_sse.py:30-45`），提前发不携带任何内容承诺——这一点与改动的自述一致。

补充一条与「提前发有什么用」直接相关的事实（说明性，非发现）：流式分支返回的 `StreamingResponse` 由 uvicorn 把 `http.response.start` 的头部字节与**第一块 body 一起**写出，所以合成之前客户端一个字节都收不到。这既解释了这个机制真正在解决的是「body 空闲超时」，也解释了 `tests/unit/test_stream_delivery.py:223-228` 那条「注释先到也算开了响应」的既有判断为什么成立。

## 3. 退化场景：deadline 触发后上游始终没有块

**判定：新形态不比现状更差；残余风险一条，低概率，记录不拦截。**

改动前后逐条对比（前两行为探针实测，第三行独立复核了你的依据）：

| 配置与情形 | 客户端收到 |
|---|---|
| deadline 触发（新） | `message_start` → `message_delta{stop_reason:"end_turn", output_tokens:0}` → `message_stop`，即 `content: []` |
| deadline 触发（旧） | 同上，中间多一个 index 0 的完整空 text 块（start＋空 delta＋stop） |
| deadline 关闭（新旧一致） | **零字节**（`stream.py:144` 的 `if started:` 守卫）。我实测 `collect(...)` 返回 `[]`，你的依据成立 |

协议侧：官方文档把内容块段写成「Potentially multiple content blocks」，**零内容块在文档描述的形态之内**，所以 `content: []` 不是非法消息。

回传侧（这是真正的风险问题）：我扫了 `~/.claude/projects/-home-xp-src-ghc-api-proxy-py/` 下全部 564 个 transcript，15795 条 `type=assistant` 记录的内容块数分布为 `{1: 15793, 2: 2}`，`message.content == []` 的记录 **0 条**。事故本身就是最强佐证：第 87、88 行共享同一 `message.id` 却是两条记录，说明 Claude Code 是**按内容块**落盘的——零块自然落零条记录，没有东西可回传。证据强度：**足以据此行动**，但不是证明，因为我们从未直接观测过一次零块响应被该客户端消费。

残余风险（低概率，方向是「换一种被拒方式」而非「新增一类崩溃」）：**若**某客户端仍把零块轮次落成 `content: []` 并回传，主路径（Anthropic in → Responses upstream）会被**我们自己的** converter 拒掉——`src/app/protocols/anthropic_responses.py:382-387` 对空 content list 抛 `invalid_content`，这是 2026-08-06 的既有裁决（`docs/tmp/260806-arbitrate-empty-content-turn.md`）。而旧形态 `[{"type":"text","text":""}]` 在 Responses 腿上是被原样带过去的：第一片的 `drop_blank_text` 只在 `upstream_is_anthropic` 时运行（`anthropic_request_hook.py:115`、`:142`）。也就是说，旧形态在 Anthropic 腿上被上游 400、在 Responses 腿上放行；新形态在两条腿上都不会污染历史，但万一被落盘则在 Responses 腿上被我方 400。综合仍是净改善。

对应的动作在第 6 节（补一个退化用例把这个形态钉住）。

## 4. 删除是否安全

**判定：代码侧安全；文档侧有两处漂移（见 4.3、4.4）。**

### 4.1 符号引用

`rg` 全仓命中 `_frame_now` / `synthesized_headers_block` 的只有三类：

- `.claude/worktrees/tui-request-log-footer/` 下的同伴独立工作树（各自一份 `stream.py` 拷贝，不受本改动影响，也不该由本次改动去动）；
- `docs/tmp/260817-entry-switch-review.md`、`260820-empty-text-block-*.md` 等历史报告（按项目纪律不改写）；
- 已删除的定义本身。

`src/`、`tests/` 主工作树内已无引用。`stream.py` 保留的 import（`CompletedBlock`、`ContentBlockStartCompat`、`block_frames`、`message_start`）都仍在 `_commit` 与终局路径使用。被删的 `synthesized_headers_block(text: str = "")` 那个 `text` 参数从未被任何调用方或配置项使用，确认是死参数。

### 4.2 index 偏移

块 index 由 assembler 给出，`rg 'index \+ 1|replace\(block'` 在 `src/`、`tests/` 内无任何与交付块 index 相关的命中；`stream_delivery` 的其它消费方（`server/pipeline_app.py:273`、`tests/integration/test_history_fixtures.py`、`tests/integration/test_recorded_upstream.py`）都不传 `synthesized_response_headers_after_sec`（`StreamSettings` 默认 0，机制关闭），不存在别处假设 index 0 属于合成块。实测两块流仍为 `[0, 1]`。

### 4.3 【应改·需用户裁决】人写文档说的是「半块」

`docs/.human-controlled/config.example.yaml:404-408`（用户亲笔，按项目约定压过一切我方推导的 ADR／spec）写的是：

> 客户端发起流式请求时，若很久上游都没有响应头，**合成一个半块**给客户端。
> 一旦合成，就无法再转发真正的上游 HTTP 状态码了，无法使用原生的客户端重试／退避机制。

两点：

1. **你派单里「规格与文档里没有要求它必须是内容块（已 grep 确认）」这一条不成立**——这一处就是内容块口径的表述。补充事实：旧实现发的是**完整**块（start＋空 delta＋stop），与「半块」本来也不符；新实现不再发任何块，偏离更大。
2. 同一段的「一旦合成，就无法再转发真正的上游 HTTP 状态码」与当前实现也对不上（这一点新旧一致，非本次引入）：流式分支在 `handle_bounded` 返回**之后**才启动，`pipeline_app.py:271-286` 用的是 `status_code=response.status_code`，即真实上游状态码；合成不改状态码。

该文件只能由用户改。建议主会话把它作为一条待裁决项交回，而不是由实现方顺手改写或忽略。

### 4.4 【应改】候选文档描述已失效

`.dev/human-controlled-docs-candidates/config-schema-gap.md:72` 仍写「合成块**绕过** `BlockBuffer` 直接写出，否则 `full` 策略会把它扣到上游结束，等于没合成」。绕过这件事仍然成立，但「合成块」已不存在，措辞需要更新为「合成的 `message_start`」。该文件是未追踪的候选件，归属由主会话判断。

## 5. ping 行为

**判定：保活成立，且与改动前一致。**

deadline 触发后 `started` 变 `True`，后续 `None` 事件走 `stream.py:119-120` 的 `elif started: yield PING_FRAME`。改动前同样如此（旧代码在 `_frame_now` 里置位后走同一分支）。探针 D（`initial_delay=2.5`、`interval=1`、`after=1`）实测收到 1 个 `: ping` 注释帧。

附带（未变，仅记录）：`sse_ping_interval=0` 时，合成之后 `_events_with_ping` 的待决 deadline 集合为空，此后全程静默——旧实现亦然。

## 6. 测试

### 6.1 `test_a_late_first_block_gets_a_message_start_and_no_placeholder_content`（`tests/unit/test_stream_delivery.py:128-147`）

**仍有分辨力，但只守一半。** 它用全等断言＋`block_start_indices == [0]` 守住「占位块不得复活」：一旦复活，事件多三条、index 变 `[0, 1]`，必红。但它对「合成机制被整体删除」**已无分辨力**——删掉后整条流的输出与它断言的完全一致，并且与 `test_nonpositive_synthesis_timeout_is_disabled`（`:163-171`）期望的形态重合。这不是缺陷，因为那个维度由 6.2 守；只是需要知道两条测试现在各守一半。

### 6.2 `test_the_synthesized_start_goes_out_while_the_policy_holds_everything_else`（`:270-301`）

**没有变成恒真。** `early` 初值为空列表，`while not any(...)` 首轮必为真，所以必须先 `await anext(stream)`；此场景下上游 sleep 30 秒、`sse_ping_interval` 默认 15 秒（超过 `asyncio.timeout(4)`）、且 `started` 之前不发 ping，因此第一块 chunk 只可能是合成的 `message_start`。若合成分支被删，`anext` 会一直阻塞，4 秒超时抛错、测试红——分辨力保住了。

但要点明它现在守的**不是**「没有占位块」：循环取到第一块 chunk 就退出，`events_of(early) == ["message_start"]` 并不断言其后没有别的东西；旧实现（`_frame_now` 也是先单独 yield 一个 `message_start` chunk）同样会通过。它守的是「buffering 策略不得吞掉合成物」，与 6.1 合起来才完整。

### 6.3 【应改】该补而未补：退化用例

deadline 触发后**上游一个块都没有**这条线，目前没有任何测试，而它恰恰是本次改动第一次对外承诺的新形态、也是第 3 节风险的落点。一条即可，形状与现有 `collect` 完全兼容：

```python
chunks = await collect([], initial_delay=1.1, synthesized_response_headers_after_sec=1)
assert events_of(chunks) == ["message_start", "message_delta", "message_stop"]
```

我已用探针确认这就是当前实际输出（含 `content: []`、`stop_reason: "end_turn"`、`output_tokens: 0`）。补它的理由不是覆盖率，而是「这是我们新承诺的线形，且它是本次唯一没有被任何断言钉住的可观察行为」。

## 7. 有没有更好的做法

**我的偏好：维持现方案（只发 `message_start`）。** 逐个比较：

- **保留内容块但填非空文本**：反对。凭空造出模型没说过的话，会被客户端落盘并回传进下一轮上下文——把一个格式污染换成语义污染，而且不同客户端如何渲染这段文字完全不可控。
- **只发一个 SSE 注释（复用 `PING_FRAME`）**：承诺比 `message_start` 更少，也确实能把头部字节冲出去。但客户端拿到的是「200＋一个注释」，若随后连接断掉，它看到的是一个开着的空响应，而不是一条格式完整、可被 SDK 解析的消息；并且项目自己在 `tests/unit/test_stream_delivery.py:223-228` 立过「注释先到也算开了响应」的判断，改用它就得同时推翻那条判断。综合下来 `message_start` 更好。
- **改发 `event: error`**：把「还在等」误报成「失败了」，而上游此刻并没有失败。反对。

两条**不属于本片、建议交回用户裁决**的延伸：

- **【建议】重新审视「解除计时」的条件。** 现在 `stream.py:122-126` 一旦组装出首个完整块就 `response_started.set()`，即便 buffering 策略把它扣住。于是 `full` 策略下，第 5 秒就组装好的块被扣住时，合成计时被解除，客户端可以零字节一直等到上游结束（探针 B 复现：`full` 策略下全部事件都在末尾一次性出现）。旧实现下补这个洞的代价是多发一个空块，所以不补是合理的；**现在合成不再承诺内容，补的代价是零**——把「解除」的判据从「首个块被组装出来」改成「已经有字节发给客户端」（即 `started`）即可。这是行为扩大，不该在本片顺手做。
- **【建议】退化路径的终端帧仍报 `stop_reason: "end_turn"`**（assembler 默认值），对一个从没开口的上游来说是在宣称干净收尾。日志侧已经用 `terminal.seen` 挡了同一个谎（`pipeline_app.py:320-325`），发给客户端的那份没挡。改动前后一致，非本次引入，记为观察。

**【建议·观察】** 退化路径会在 stderr 打出 asyncio 的 `StopAsyncIteration exception in shielded future`，来源是 `_events_with_ping` 里 `asyncio.shield` + `wait_for` 超时后内层任务才抛 `StopAsyncIteration`。我在「合成开启」与「合成关闭＋ping 开启」两种配置下都复现了，与本次改动无关，是既有噪声，记录备查。

## 8. 第一片是否被第二片破坏

**没有。**

- 改动面无交叉：第二片只动 `pipeline/delivery/stream.py` 与其单测；第一片在 `pipeline/anthropic_request_hook.py`、`server/handler.py`、`tests/unit/test_blank_text_blocks.py`。
- 调用点一致：`fix_anthropic_request` 的唯一生产调用点 `handler.py:80-84` 位于 `route` 赋值（`handler.py:65-71`）之后，新增关键字参数齐全；测试侧调用点 `tests/unit/test_client_request_headers.py:95`、`tests/unit/test_blank_text_blocks.py:18-19` 均已更新，无遗留旧签名调用。
- 实跑：`uv run pytest tests/unit/test_stream_delivery.py tests/unit/test_blank_text_blocks.py -q` → **30 passed in 7.00s**。

## 9. 交回主会话的事项

1. `docs/.human-controlled/config.example.yaml:404-408` 与本次实现冲突（「半块」；以及「无法再转发真正的上游状态码」与实现不符）。该文件属用户亲笔，只能由用户裁决与修改。
2. `.dev/human-controlled-docs-candidates/config-schema-gap.md:72` 的「合成块绕过 BlockBuffer」措辞需更新。
3. 6.3 的退化用例建议补上。
4. 第 7 节两条延伸（`full` 策略下计时解除条件、退化路径的 `end_turn`）建议作为 deferred 记录，不在本片处理。
