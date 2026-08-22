# E 组独立评审：`66b63c9` / `2769a64` / `4c7129a` / `e81f07f`

**日期**：2026-08-22。**评审对象**：主仓 `66b63c9^..e81f07f`（`src` + `tests`）。
**评审时的树状态**：HEAD = `e81f07f`，`git status -- src tests` 空。所有实测都在这个状态下跑的。
**跑完之后**：同伴把 HEAD 推到了 `630f7f3`（经 `ebb2fec`）。我在 `630f7f3` 上逐条复核了本报告四条主要发现的代码位置——`stream.py:330` 的 `REPLAY` 单挑 + `:338` fall-through、`:358` 的提前 `return`、`:406` 与 `:414`、`pipeline_app.py:541-547` 的 `one_shot_accounting` 不带 `assembler`——**全部一字未变**，所以结论对 `630f7f3` 同样成立（行号已随之偏移 3-4 行，正文用的是 `e81f07f` 行号）。**不在评审范围**：`stream_cap.py`、`composition.py`、`cli.py`、`debug/models.py`、`responses_sse.py`、`framing.py`。

**权威**：`docs/.human-controlled/upstream-retry-and-continuation.md`、`docs/.human-controlled/client-side-block-delivery.md`。裁决台账 `decisions.md`（第三节是推论，第四节未裁决）。

**结论：needs-fix。** 1 blocker、4 major、8 minor。Blocker 与 major 各自都有可执行的窄修法，没有一条需要重做设计。

---

## 一、分级计数

| 级别 | 条数 | 编号 |
|---|---|---|
| blocker | 1 | B1 |
| major | 4 | M1 – M4 |
| minor | 8 | m1 – m8 |

---

## 二、Blocker

### B1 · 上游已发终止事件后撕流，一个**已经完成**的回合被伪造成 `tool_use` 交接回客户端

**位置**：`src/app/pipeline/delivery/stream.py:327-342`（`e81f07f` 行号）。

**为什么错**。`decide_stream_ending()` 有三个结局（`src/app/pipeline/retry.py:99-104`），其中 `terminal_seen=True` **无条件返回 `COMPLETE`**（`retry.py:134-135`）。这次改动只把 `REPLAY` 单独挑出来处理，**`COMPLETE` 与 `ABANDON` 一起 fall through 到 `_hand_over()`**：

```python
if verdict.ending is StreamEnding.REPLAY:
    replacement = await replay.reopen()
    if replacement is not None:
        ...
        continue
handed_over = _hand_over(continuation, session, assembler, ..., error=torn)   # ← COMPLETE 也走到这里
```

于是「上游把整个回合发完了（`message_delta{end_turn}` + `message_stop` 都收到了），随后连接被撕断」会被当成「未完成的回合」交接回去。

**实测证据**（探针，Anthropic 直连腿，上游先发完整 `sse_upstream("first")` 再抛 `RemoteProtocolError`），客户端实收帧序：

```
message_start
content_block_start  index=0  {"type":"text","text":""}
content_block_delta  index=0  text_delta "first"
content_block_stop   index=0
content_block_start  index=1  {"type":"tool_use","id":"toolu_…","name":"mcp__plugin_…__turn_interrupted"}
content_block_delta  index=1  input_json_delta {"num_messages":0,"category":"network","message":"peer closed the connection"}
content_block_stop   index=1
message_delta        {"stop_reason":"tool_use"}
message_stop
```

**上游真实的 `end_turn` 被丢弃，换成了一个代理编出来的工具调用。** 请求行同时报 `[RETY] turn handed back to the client to continue`，所以日志也看不出这是假的。

**这比改动之前更糟，不是等价。** 改动前 `COMPLETE` 走 `raise torn`：客户端拿到半截 SSE + 传输错误——**看得见的坏**。现在拿到的是一份**格式完全合法、内容是错的**回合：客户端会去跑一次没必要的 MCP 工具、把这个假 `tool_use` 写进自己的 transcript、再发一次完整请求。这是「静默错误输出」，客户端没有任何办法察觉。

**与人写文档对不上**。文档第 5-19 行把结局分成「无法继续」与「一般可以继续」两类，都以「业务是否因此无法继续」为前提。终止事件已经到达的回合**两类都不属于**——它已经完成了。文档第 21 行的合成前提是「业务可能可以继续」，这里不成立。

**这不是新发现的问题类别，而是本项目已经诊断过的 P2**：`.dev/docs/tmp/260822-h2-streamreset-cancel-diagnosis.md:123` 已写明「`COMPLETE` 与 `ABANDON` 被折叠成同一条路」，并在 `:177` 列为 P2 待修。E 组在那条折叠之上**又加了一个新出口**，把「丢掉一份攒齐的回复」升级成「用一份编造的回复替换它」。

**证据权重**：机制可达性是**强证据，可据以行动**（探针端到端复现，帧序已抄录）。至于生产上「terminal 之后才撕」发生频率：本上游的 `RST_STREAM(CANCEL)` 是**生产实测**存在的（同上诊断文档），但**「terminal 之后」这一时刻本身尚未在生产日志里见到**——诊断文档自己写着「本次确未见 terminal」。所以频率未知，危害确定。定级 blocker 的理由是危害形态（静默产出错误内容）与修法成本（一行判断）不成比例，不是频率。

**建议怎么改**：

```python
if verdict.ending is StreamEnding.COMPLETE:
    break            # 落到 :344 的正常收尾，把攒齐的块与 terminal_frames 发完
handed_over = _hand_over(...)
```

`COMPLETE` 该怎么收尾与诊断文档 §2.3 提的 `break` 是同一件事，两处应一并裁决、一次改完，别各改各的（那份文档同时提醒 `break` 会让 `accounting.failure` 丢失、`_ending()` 的 detail 退化，需要一并处理）。**配一条判别性回归**：上游发完整回合后抛 reset，断言客户端收到 `stop_reason: end_turn` 且 `turn_interrupted` 不出现。

---

## 三、Major

### M1 · `max_tokens` 一块不剩时不交接，客户端拿到 200 + **零字节**

**位置**：`src/app/pipeline/delivery/stream.py:354-356` 的 `if not client_has_bytes.is_set(): return`，排在 `:367` 的 `_HANDED_OVER_STOP_REASONS` 判断**之前**。

**为什么错**。`decisions.md` §2 第 2 条是明确裁决：「**`max_tokens` 一律走合成，不回落到无痕重试——即使按第 1 条丢弃后一块不剩**」。而上游一个 output item 都没产出、只说了 `max_tokens` 时，`client_has_bytes` 从未置位，`:354` 直接 return，交接判断根本到不了。

**实测证据**：上游只发 `message_delta{stop_reason:"max_tokens"}` + `message_stop`，客户端实收 `b''`（200 + `text/event-stream` + 零字节）。这恰好是 `2769a64` 那条提交花大力气修掉的形态（chat-completions 零字节），在另一个位置原样复现了一份。

**连带**：`stream.py:420-422` 那个 `if session.committed_count == 0: chunks.append(message_start(...))` 分支**因此不可达**，而它的注释写着「Reachable only for a turn upstream cut short for want of room whose one block was itself truncated and dropped」——**断言了一个不存在的可达路径**。这正是评审要点 5 的形状：把推理出来的可达性写成了确认的事实。（顺带，那句描述的状态本身也自相矛盾：裁决 §2 第 1 条规定「只有未完成块时保留它」，所以「唯一的块被丢弃」这个前提在丢弃规则下不成立。）

**建议怎么改**：把 `terminal.stop_reason in _HANDED_OVER_STOP_REASONS` 的交接尝试提到 `if not client_has_bytes.is_set(): return` **之前**；`_hand_over` 里那个 `committed_count == 0` 的 `message_start` 分支届时才真正可达，注释也就变成真的。补一条测试：上游零 item + `max_tokens` → 客户端应收到 `message_start` + `turn_interrupted` + `stop_reason: tool_use`。

### M2 · `_hand_over` 里 `if remaining and not session.started` 是**死分支**，`message_start` 会漏发

**位置**：`src/app/pipeline/delivery/stream.py:414-416`。

**为什么错**。`DeliverySession.finish()` → `_commit(...)` → `if blocks: self.started = True`（`src/app/pipeline/delivery/blocks.py:148-156`）。所以 `remaining` 非空的那一刻 `session.started` **已经是 `True`**，判断永假。

今天没出事，是因为 `_deliver:344-348` 在走到 `_hand_over` 之前已经 flush 过一次（`max_tokens` 路径），或者根本走不到（`full` 策略下 `committed_count == 0` 直接拒绝交接）。**这是被别处遮住的 latent bug，不是无害写法**：M1 一旦按建议修好，「缓冲里有块、从未交付过」的路径就会真正走到这里，客户端会拿到没有 `message_start` 的 `content_block_start`。

**建议怎么改**：在调用 `session.finish()` **之前**取快照，例如 `started_before = session.started`，然后判 `if remaining and not started_before`。同时删掉下面那个 `committed_count == 0` 的重复分支或与之合并——两段做的是同一件事（在需要时补 `message_start`），分成两处写是它们互相遮蔽的原因。

### M3 · 一次性交付路径（`2769a64`）**丢掉了整个结局判定**，撕流的 chat-completions 流会记成 `[ OK ] 200`

**位置**：`src/app/server/pipeline_app.py:545-551`（`one_shot_accounting` 构造时不带 `assembler=`）+ `:772`（`_StreamAccounting.finish()` 里 `if self.assembler is not None:` 把**整段结局判定**——包含 `self.trace.status_override, self.trace.detail = self._ending()`——都包在里面）。

**为什么错**。`assembler is None` ⇒ `_ending()` 永不被调用 ⇒ `status_override` 恒为 `None` ⇒ `status_for(200, override=None) == "ok"`（实测确认三点）。于是 `/chat/completions` 的流式请求无论怎么结束都记成成功：上游撕流记 `ok`、客户端断开记 `ok`（不再有 `gone`）、idle/deadline 守卫击发也记 `ok`。

`request_log.py:338` 的文档自己写着这条判据存在的全部理由：「a streamed reply's code is fixed when upstream's headers arrive, so a stream that tore halfway is a failure wearing a 200」。一次性交付路径正好把这句话作废了。

提交信息说「The one-shot path is wrapped in the same guards in the same order as the block path，so an idle upstream, an expired attempt and an expired client deadline still end it the same way」——**守卫接对了，但守卫击发之后没人把结论写到行上**。这句话在字节层面成立，在观测层面不成立。

**建议怎么改**：把 `finish()` 里的 `if self.assembler is not None:` 收紧到只包住真正需要 assembler 的三行（`absorb` / `context.reply` / `terminal.stop_reason` 的读取），让 `self.handed_over or not (delivered_whole and ...)` 这一支在 `assembler is None` 时也能跑；无 assembler 时 `terminal.stop_reason` 视为空即可，恰好让「drained 且没有 stop_reason」自然落到 `_ending()`。补一条测试：chat-completions 流式上游中途抛错 → 行状态是 `fail` 而非 `ok`。

### M4 · 测试样本全部走 Anthropic 直连腿；主产品路径零覆盖，`num_messages` 无鉴别力

**位置**：`tests/int/test_pipeline_app.py:2249-2253` 的 `_delivered()`（固定 `POST /v1/messages` + `model: "claude-model"`），四条新增交接测试（`:2849`、`:2885`、`:2909`、`:2934`）全部经由它。

**为什么是问题**。主产品路径是 **anthropic-messages 进 → openai-responses 出**（`model: "gpt-model"`）。四条新测试一条都没走。唯一涉及 Responses 的是 `test_a_client_request_in_another_format_is_not_handed_a_tool_call`，而它是 `POST /responses`（Responses 格式的**客户端**请求）——负样本，方向正相反。**这与上一轮 D 组 blocker 是同一个形状。**

好消息先说：我实测了主路径（客户端 `/v1/messages` + `gpt-model`，上游发 Responses SSE 后撕流），**行为是对的**——交接确实发生、`route.wire_format` 读的是客户端侧格式所以门是对的、块 index 连续、`num_messages` 读到了客户端自己的计数。所以这次**不是缺陷被样本绕开**。

坏消息是**判据同样被绕开了**。变异实测：把 `pipeline_app.py:344` 的 `_client_message_count(inbound_payload)` 改成 `_client_message_count(context.payload)`（即误读翻译后的 Responses body），

- 主路径上 `num_messages` 从 `3` **静默变成 `0`**；
- 五条 committed 交接测试**全绿**。

唯一相关断言是 `assert handed["input"]["num_messages"] == 0`，而 fixture 里 `messages: []`——`0` 既可能来自正确读取也可能来自读错对象，**恒真形状**。`num_messages` 是防无进展循环的唯一参数，`status.md` 自己写着「两边不一致这个参数就白加」，它现在没有任何测试守着。

**建议怎么改**：加一条主路径用例——客户端 `POST /v1/messages`、`model: "gpt-model"`、`messages` 给 3 条、上游返 Responses SSE（完整 item + 撕流），断言 `num_messages == 3`、合成块 index == 已交付块数、`stop_reason: tool_use`。这一条同时把「两条上游腿都适用」（`decisions.md` §3.3 的**推论**）从推论变成有守卫的事实。

---

## 四、Minor

### m1 · 交接帧的 `usage` 把「没观测到」渲染成「测得 0」

`stream.py:426`：`usage=assembler.terminal.usage or None`。撕流交接时 `terminal.usage` 恒为 `{}`（上游没来得及发），落到 `anthropic_sse.py:166` 的 `usage or {"output_tokens": 0}`，客户端被告知这个回合产出 **0 token**——而它明明收到了内容。`status.md:135` 写的是「`usage` 报失败 attempt 实报值」，实报值是「没报」，不是 0。属项目记忆里的 absence-is-not-readable。影响面只是客户端侧计费显示，建议记进 `deferred.md` 而不是当作已完成。

### m2 · `handed_over` 可能置位却没真的交接

`pipeline_app.py:336` 在**构造 payload 时**就置 `accounting.handed_over = True`，此时帧一个都还没写出去；`_ending()`（`:801-803`）又把 `handed_over` 排在 `failure` / `drained` / `gone` **之前**。客户端在合成帧写出过程中断开 → 行报 `[RETY] turn handed back to the client to continue`，而客户端什么也没收到。这正是评审要点 4 问的那一半。反向（真交接了却没置位）不可达：`_hand_over` 里 `synthesize()` 成功是产出 chunks 的必要条件。建议要么把置位推迟到 delivery 真正 yield 完，要么在 `_ending()` 里把 `handed_over` 排到「本侧结束」判断之后。

### m3 · `config.example.yaml` 里没有 `auto_retry_tool_call_full_name`，而漏检不会报红

人写文档 `upstream-retry-and-continuation.md:35` 承诺这个配置项，schema 加了（`config/schema.py:272-275`），但作为配置权威、同时是 `tests/unit/config/test_config_schema.py` oracle 的 `docs/.human-controlled/config.example.yaml` 里没有它，`.dev/human-controlled-docs-candidates/` 也没写候选。那个测试只验「example 能被 schema 解析」，不验「schema 的键都在 example 里」，所以这类遗漏**永远不会被测出来**。这是用户的文件，不该我们改；建议把候选段落写进 `.dev/human-controlled-docs-candidates/`，并在 `deferred.md` 记一笔「schema→example 的反向检查缺失」。

### m4 · 「被截断项永远是最后一项」是未加护栏的假设，失效时会给客户端发跳号的 `index`

`assembler.py:295-303`。`_open()` 在 `:266-267` 已经预支了 `self._order`，丢弃发生在 `_close()`，序号不退。所以只要有一个 `status:"incomplete"` 的 item **不是最后一项**，后续块的 index 就会跳号（0, 2, …）。Anthropic 客户端按 index 装配 content 数组，跳号是坏帧。

提交信息的措辞是断言：「the item upstream cut short is always the last one」。15 次实测证明的是「`status` 字段存在且取值可读、其中四次落在 `function_call` 上」；**「永远是最后一项」有没有被单独验证过，提交信息与代码注释都没说**。这是评审要点 5 的形状——把结构推理写成了观测结论。

**建议**（按成本从低到高）：(a) 把注释改成「实测样本内成立；若失效表现为 index 跳号」，并记进 `deferred.md`；(b) 改成成块时才分配序号（`_open` 不预支），跳号从结构上不可能。

### m5 · `web_search_call` 迟到注册与新丢弃规则相冲，可能静默吞掉一次真实搜索

`assembler.py:283-303`。迟到注册那段注释的**全部理由**是「refusing to close it would throw away a search that actually ran, silently」，而紧接其后新加的丢弃规则可以对同一个 item 做的正是这件事。目前没有任何观测说明 `web_search_call` 会不会带 `status:"incomplete"`。建议要么把 `WEB_SEARCH_CALL` 排除在丢弃规则外，要么在注释里点明这个交叉是已知且被接受的。

### m6 · 丢弃规则只在流式装配器里，非流式路径不生效

`ResponsesAssembler._close()` 是唯一读 item `status` 的地方；非流式经 `handler.reply_summary` / `blocks_from_anthropic` 整包读取，被截断的 item 照常交付。裁决 §2 第 1 条是就 `max_tokens` 说的，没有限定流式。两条路径要不要对齐**需要裁决，不该我判**，建议记进 `deferred.md` 报给用户。

### m7 · `_hand_over` 抛异常会留下已置位的 `handed_over`

`block_frames()` 在 `signature_compat == "redacted_thinking"` 时抛 `ValueError`（`anthropic_sse.py:95-102`）。此时 `handed_over` 已置位、chunks 未产出。该配置下任何块都会抛，属既有行为，**不建议为它改代码**，仅记录。

### m8 · 同一个函数里两个 payload 来源不一致，且其中一个只是碰巧成立

`_hand_back` 里 `num_messages` 读 `inbound_payload`（客户端原文，正确，符合裁决 §2 第 6 条），紧挨着的 `tools` 检查却读 `context.payload`（**翻译后**的 body）。我实测了：主路径上翻译后的 Responses `tools[]` 仍是扁平 `name`，所以声明检查在两条腿上都成立——**但这是巧合成立而非设计**，Anthropic→Responses 的工具翻译一旦改形状（比如包一层、或改字段名），告警就会在客户端明明声明了工具时误报，而没有任何测试会红。建议统一读 `inbound_payload`，或至少写一句注释说明为什么这里读的是翻译后的。

---

## 五、查过、没问题的（判据写在这里，不是空清单）

### 5.1 「不该交接」的四类，逐条核过，**都不交接**

| 结局 | 判据 | 结论 |
|---|---|---|
| `refusal` | 走 terminal 路径，`refusal` 不在 `_HANDED_OVER_STOP_REASONS`（`stream.py:385`）里 | **实测**：客户端收到 `stop_reason: "refusal"` 原样透出，无 `turn_interrupted`。符合人写文档第 11 行与裁决 §2 第 9 条 |
| 400 / 401 / 429 / 5xx | HTTP 状态码在响应头阶段就定了，那时 `committed_count == 0`；即使 replay 的 `reopen()` 返回 `None` 而 fall through 到 `_hand_over`，`stream.py:407-409` 的 `committed_count == 0` 也会拒绝 | 读码确认，与 `status.md` 那张「只可能在未交付位置」的结构表一致 |
| 客户端断开 / 优雅关闭 | 到达形态是 `CancelledError` / `GeneratorExit`，都不派生自 `Exception`，`stream.py:300` 的 `except Exception` 接不到 | 读码确认（该行注释本身就是为这件事写的） |
| 代理保护机制（缓冲超限） | **实测** `normalize_upstream_error(BufferCapExceeded(10,5)) is None` → `_replay_reason` 返回 `None` → `raise torn` | 不交接。符合人写文档第 8 行 |
| 客户端时限 | `ClientDeadlineError` 在 `stream.py:305-316` 被**提前**答复（`error_frame` + `return`），排在交接之前 | 符合 `decisions.md` §2-2 第 16 条 |

### 5.2 非流式路径不交接

`continuation` 只传给 `stream_delivery`（`pipeline_app.py:726`）；`one_shot_delivery` 与 JSON 路径都不接。符合裁决 §2 第 4 条「非流式路径只可能无痕重试」。

### 5.3 缓冲策略下的可达性

- `full` / `until-tool-use` + 可续失败：`committed_count == 0` → `_hand_over` 返回 `None` → 走 replay 或 `raise`。**这是对的**，人写文档第 21 行的判据是「已交付过完整块」，`full` 下确实没交付过。
- `full` + `max_tokens`：`_deliver:344` 先 flush，`committed_count` 变正，交接得以进行。**实测**帧序 `message_start` ×1 → 块 0 → 块 1 → `tool_use` index 2 → `message_delta{tool_use}` → `message_stop`，index 连续、`message_start` 不重复。

### 5.4 合成块的 wire 正确性（实测帧，不是读码推断）

- `content_block_start` 的 `content_block` = `{"type":"tool_use","id":"toolu_"+24hex,"name":<配置全名>,"input":{}}`；参数走 `input_json_delta` 的 `partial_json`（`anthropic_sse.py:104-107,57-59`），符合 Anthropic 线格式。
- `stop_reason: "tool_use"` 与 `message_stop` 成对（`terminal_frames` 一次产两帧），无 `error` 帧混发。
- **缓冲块先于合成块冲刷**，顺序正确。
- **`session.finish()` 排在 `synthesize()` 之后**（`stream.py:410-414`）——这一点是对的，顺序反过来就会在交接被拒绝时**静默吞掉缓冲块**。
- Responses 腿丢弃一个 `incomplete` item 之后，**实测** index 仍是 0,1（合成块接在已交付块后），`usage` 携带 `response.incomplete` 报的真实值。

### 5.5 `retry` 这一格的观测面接线，四处齐全

| 面 | 落点 | 结论 |
|---|---|---|
| 请求行前缀 | `logging.py:23` `STATUS_PREFIXES["retry"]="[RETY]"`、`:70` `PREFIX_COLOURS["[RETY]"]=YELLOW` | 已存在（C 组落的），四字符宽 |
| 请求行本体 | `request_log.py:67` `LogStatus`、`:72` `STATUS_COLOURS`、`:344` `succeeded = status == "ok"` → `retry` 取路由形态并带 request id | 与 `gone` 一致，合理 |
| JSONL | `_log_completion` → `write_request_record(line, status=status)` | **有测试**（`record["status"] == "retry"`，且 M5 变异能打红） |
| TUI / footer | `tui.py:134` 直接复用 structlog 渲染好的行，不另做状态判断；footer 只显示在途请求、不按状态聚合 | 无需额外接线 |

### 5.6 `category` 取自 `RetryReason` 映射而非二次分类

`_CATEGORY_FOR_REASON`（`pipeline_app.py:278-282`）覆盖 `RetryReason` 全部三个成员，`.get(..., ErrorCategory.INTERNAL)` 兜住 `None`。提交信息说的「二次分类会自相矛盾」核过属实，**实测**撕流交接的 `category == "network"`（而非 `internal`）。`max_tokens` 走 `category = stop_reason` 这条临时路，注释与 `decisions.md` §4-1 都标了 provisional，**这一条没有把未裁决写成已裁决**。

### 5.7 `4c7129a` 那条回退

只删了一行错拿的 import，与提交信息一致。提交信息里那条教训（hunk 不是单一 owner）与项目记忆 `git-commit-takes-the-whole-index` 同源，写得准确。

### 5.8 `2769a64` 的字节直通

`delivers_blocks`（`handler.py:493-504`）按 `inbound_format` 判、`synthesized` 例外，边界正确；`one_shot_delivery` 包了与块路径同样的四层守卫、同样顺序；测试 `assert response.content == CHAT_COMPLETIONS_SSE` 逐字节断言含 `data: [DONE]`，**有鉴别力**。唯一的问题是观测面（见 M3）。

### 5.9 Ruff / Pyright

在评审点 `e81f07f`（`src` / `tests` 干净）跑过一次全量单元 + 集成回归（`tests/unit/pipeline/delivery/test_sse_assembly.py` + `tests/int/test_pipeline_app.py`）：136 passed。Ruff / Pyright 当前有报错，**全部落在同伴未提交的 `handler.py` / `test_stream_cap.py` 上**，不算本次头上。

### 5.10 活文档同步

`.dev` 侧 `6bc3912 docs: record what E landed` 已把 E 段写进 `status.md`，出处标注清楚（哪条来自人写文档、哪条来自 `decisions.md` 第二节、哪条是推论）。这一点做得好。**但**：`status.md:135` 的「`usage` 报失败 attempt 实报值」与 m1 不符；「`max_tokens` 一律交接」这句在 M1 的缺口下不成立——两处都该在修完之后回填，或先标注例外。

---

## 六、变异实测记录（5 处，全部 sha256 核对还原）

基线（`e81f07f`，`src`/`tests` 干净时录）：

```
9539bc1fd3f6e4cbda707bcf5ef7c5d3c8d79f15ec091e80edd9ee45f7a1b0f3  src/app/pipeline/delivery/assembler.py
fd53f42633d572db3c6b3a5cf11db10ef3737357ef2a522c87c85c86d1b4c6d6  src/app/pipeline/delivery/stream.py
c06cd5db83ccc6c5ed7ff26a55eff4a2dd9118cb4db04c224a11b27468c80287  src/app/server/pipeline_app.py
```

| # | 变异 | 期望 | 实测 |
|---|---|---|---|
| M1 | `assembler.py`：`self._terminal.blocks > 0` → `>= 0`（永远丢弃） | 红 | ✅ 红 —— `test_an_item_upstream_cut_short_is_kept_when_it_is_all_there_is` FAILED（`assert 0 == 1`）。**只有单元测试打到，集成层零覆盖** |
| M2 | `stream.py`：`_HANDED_OVER_STOP_REASONS` → `frozenset()` | 红 | ✅ 红 —— `test_a_turn_that_ran_out_of_room_is_handed_back_the_same_way` FAILED（`StopIteration`，没有 `tool_use` 帧） |
| M3 | `pipeline_app.py`：`_client_message_count(inbound_payload)` → `(context.payload)` | 红 | ❌ **全绿**（5 passed）。同一变异下我的主路径探针实测 `num_messages` 从 3 变 0 → 见 M4 |
| M4 | `pipeline_app.py`：删掉 `if route.wire_format is not WireFormat.ANTHROPIC_MESSAGES: return None` | 红 | ✅ 红 —— `test_a_client_request_in_another_format_is_not_handed_a_tool_call` FAILED（`DID NOT RAISE`） |
| M5 | `pipeline_app.py`：删掉 `accounting.handed_over = True` | 红 | ✅ 红 —— `test_a_handed_back_turn_is_neither_a_success_nor_a_failure_on_the_line` FAILED（`'fail' == 'retry'`） |

**还原核对**：`sha256sum -c` 三个文件全 `OK`（在 M5 之后一次性核的）。评审期间临时创建的探针文件 `tests/int/test_zzz_review_probe_deleteme.py` 已删除。**注意**：交出探针之后同伴又推进了两个提交并改动了 `stream.py` / `pipeline_app.py`，所以现在再跑 `sha256sum -c` 会对不上——那是同伴的改动。我另做了一次残留反查（三条变异串在 `src` 下**零命中**，三条原串**全部在位**），确认没有把变异留在树里。

**探针（一次性，已删）覆盖的六个问题与答案**：主路径交接✅、terminal 后撕流❌（B1）、`max_tokens` 零块❌（M1）、`full` 策略帧序与 index✅、Responses 腿丢弃后 index✅、工具已声明不误报✅、`refusal` 不交接✅、主路径 `num_messages == 3`✅。

---

## 七、给主会话的建议顺序

1. **B1** —— 一行判断，且与 `.dev/docs/tmp/260822-h2-streamreset-cancel-diagnosis.md` 的 P2 是同一处代码，**两件事一次改完，别分两轮**。
2. **M1 + M2** —— 同一段函数，M1 修完 M2 才真正可达，**必须一起改**。
3. **M3** —— 独立于交接机制，属 `2769a64` 的收尾。
4. **M4** —— 补一条主路径测试，同时给 `num_messages` 一个真正的守卫。
5. m1 / m4 / m5 / m6 / m3 → 记 `deferred.md`；m6 与 m3 需要用户裁决，别自己定。
6. 修完之后回填 `status.md:135` 与那句「`max_tokens` 一律交接」。
