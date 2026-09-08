# 空 Anthropic text content block：响应产出侧调查

调查日期：2026-08-20。

代码快照：当前工作树，`HEAD f5c2e9f274bfd576ef58a8755561ac7e359c8bda`；`src/app/cli.py`、`src/app/pipeline/delivery/assembler.py`、`src/app/server/handler.py`、`src/app/server/pipeline_app.py` 当时存在未提交修改，因此以下 `file:line` 和结论以调查时磁盘上的实际内容为准，而不是只描述该 commit。

调查范围：`src/app/delivery/*`、`src/app/streaming/*`、`src/app/pipeline/delivery/*`、`src/app/pipeline/translation_driver/*`、`src/app/openai/responses_stream_parser.py`、`src/app/protocols/responses_anthropic.py`、当前 CLI 接线及 `tests/cassettes/*`。未修改生产代码或测试。

## 结论摘要

1. **[强，代码事实，足以行动] 当前 CLI 主路径确实能主动造出一个空 text block。** 当首个可解析上游 SSE event 在 `synthesized_response_headers_after_sec` 内没有到达时，`src/app/pipeline/delivery/stream.py:109-129` 立即发送 `synthesized_headers_block()`；该占位块默认 `text=""`，见 `src/app/pipeline/delivery/stream.py:210-217`。默认超时是 240 秒，见 `src/app/config/schema.py:187-194`。它不是“半开的块”：`src/app/pipeline/delivery/anthropic_sse.py:85-138` 会完整发送 `content_block_start`、空 `text_delta`、`content_block_stop`。因此客户端有充分理由把它记成 `{"type":"text","text":""}`。
2. **[强，代码事实，足以行动] 没有通用的“空 text block 不发”守卫，也没有纯空白守卫。** 两套交付实现都会给已形成的空 `TextBlock` 发 start/stop；当前 CLI 交付实现还会发一个 `text:""` delta。代码没有在交付边界使用 `text.strip()`。`"   "`、`"\n"` 等纯空白文本会作为非空 delta 发出。
3. **[强，代码事实] 正常重组也存在空块路径。** Anthropic 上游开 text block 后直接 `content_block_stop`，以及当前 CLI 的 Responses assembler 收到 message `output_item.done` 前没有任何 `response.output_text.delta`，都会形成空 text block并交付。
4. **[强，代码事实] 非 SSE 的 Responses→Anthropic 翻译明确把“没有任何可渲染 content”补成一个空 text block。** 当前 translation driver 在 `src/app/pipeline/translation_driver/responses.py:71-90` 这样做；旧 app_factory 路径使用的 converter 在 `src/app/protocols/responses_anthropic.py:121-133` 也这样做。显式 `output_text:""` 也原样变成空 text block。
5. **[强，代码事实] reasoning-only 和 tool-only 本身不会额外补 text block。** reasoning-only 变成一个 `thinking` block，tool-only 变成一个 `tool_use` block。只有“翻译后 content 列表完全为空”才触发非 SSE 的空 text fallback。
6. **[强，一手 cassette，足以排除这三个样本] 三个真实 cassette 中没有累计文本为空或纯空白的最终 text block，也没有 text block start 后在 stop 前完全没有 text delta 的样本。** cassette 中确有协议正常的空初始 start/content-part placeholder，但后续都有非空 delta／authoritative text。该样本集不能证明生产从未出现空块。

## 当前 CLI 主路径

### 接线

**[强，代码事实]** CLI 的 inherited-listener 与 standalone 两种启动方式都构造 `create_pipeline_app(chain)`，见 `src/app/cli.py:132-167`。SSE 响应统一经过 assembler 和 `stream_delivery()`，见 `src/app/server/pipeline_app.py:253-283`；非 SSE 响应先经 `response_payload()`，见 `src/app/server/pipeline_app.py:285-292`。因此 `src/app/pipeline/delivery/*` 是当前 CLI 的实际交付路径。

### 路径 A：超时占位块由本项目主动产生

**触发条件：** 请求是 SSE；`synthesized_response_headers_after_sec > 0`；从计时起到 deadline 仍没有首个可解析 SSE event。这里代码实际探测的是“首个 SSE event 是否到达”，不是 HTTP response headers 是否到达。

**代码链：**

- `src/app/config/schema.py:187-194`：默认 `synthesized_response_headers_after_sec=240`。
- `src/app/pipeline/delivery/stream.py:93-101`：从进入交付时计算绝对 deadline。
- `src/app/pipeline/delivery/stream.py:109-129`：deadline 到达且尚未开始响应时，设置 `synthetic_block_sent=True`，调用 `synthesized_headers_block()` 并立即绕过业务块 buffer 发送。
- `src/app/pipeline/delivery/stream.py:210-217`：`synthesized_headers_block(text: str = "")` 构造 `{"type":"text","text":""}`。
- `src/app/pipeline/delivery/anthropic_sse.py:48-60`：text block 的 delta 总是 `str(payload.get("text", ""))`；空串不被过滤。
- `src/app/pipeline/delivery/anthropic_sse.py:103-138`：start 中先写 `text:""`，随后追加上述空 `text_delta`，最后 stop。

**实际 wire 形状：** 一个完整的 Anthropic text block，累计文本仍是 `""`。测试也把这个行为作为预期固定下来：`tests/unit/test_stream_delivery.py:127-146` 的测试名就是 `test_synthesizes_one_empty_block_when_first_real_block_is_late`；`tests/unit/test_stream_delivery.py:268-305` 证明该空块会在上游仍沉默时立刻发出，并包含 start、delta、stop。

**证据权重：强，足以确认“本项目自身能够产生空 text block”。** 但仅凭当前生产报错，不能确认出错会话上一轮一定等了 240 秒或采用了该配置；那一段因果仍需前一轮的时间线／capture 佐证。

### 路径 B：Anthropic SSE text block 在首个 delta 前正常关闭

**触发条件：** 上游发送 `content_block_start(type=text)`，随后发送 `content_block_stop`，期间没有 `text_delta`，或所有 `text_delta.text` 都是空串。纯空白 delta 形成纯空白块。

**代码链：**

- `src/app/pipeline/delivery/assembler.py:131-139`：open 时 draft 的累计 `text` 默认为空串。
- `src/app/pipeline/delivery/assembler.py:141-156`：只有 text delta 才累加，且不做 `strip()`。
- `src/app/pipeline/delivery/assembler.py:158-172`：stop 无条件把 draft 变成 `CompletedBlock`；text payload 使用累计值，即空串也照样完成。
- `src/app/pipeline/delivery/stream.py:138-147`、`src/app/pipeline/delivery/stream.py:187-207`：完成块被 buffer 释放后直接 framing，没有空文本过滤。
- `src/app/pipeline/delivery/anthropic_sse.py:48-60`、`src/app/pipeline/delivery/anthropic_sse.py:103-138`：空 text block 被发送为 start＋空 delta＋stop。

**归因：** 这条路径会让本项目向客户端 emit 空块，但空内容语义来自上游的已关闭块；它不是本项目凭空创造内容。若上游只发 `message_stop` 而没有对应 `content_block_stop`，draft 不会被 close，也就不会由这条路径发出空块。

### 路径 C：Responses SSE message item 没有任何 text delta

**触发条件：** 当前 CLI 的 Responses assembler 收到 `response.output_item.added`，item type 为 `message`；随后收到匹配的 `response.output_item.done`；期间没有任何能匹配 draft 的 `response.output_text.delta`，或 delta 全为空串。`item.content=[]` 是直接触发形状之一。

**代码链：**

- `src/app/pipeline/delivery/assembler.py:240-251`：任何 Responses `message` item 都映射为 kind `text`，draft.text 初值为空；这里不检查 `item.content`。
- `src/app/pipeline/delivery/assembler.py:253-256`：只累加 output text delta，不做空串或纯空白过滤。
- `src/app/pipeline/delivery/assembler.py:263-286`：`output_item.done` 对非 tool/reasoning 一律构造 `{"type":"text","text":draft.text}`，即使为空；closing item 中的 authoritative `content` 没有参与 text 值构造。
- 后续交付与路径 B 相同，最终 start＋空 delta＋stop。

**额外后果：** 即使 `output_item.done.item.content` 含非空 authoritative `output_text`，只要该实现没有收到／匹配到 delta，它仍会输出空串，而不是采用 authoritative text。这是当前 `ResponsesAssembler` 的代码事实；本调查未发现 cassette 中出现这种不一致样本。

### “stop 在第一个 delta 之前”的边界

**[强，代码事实]** “close event 到了但没有 delta”会产生空块：Anthropic 的 close 是 `content_block_stop`，Responses 当前 assembler 的 close 是 `response.output_item.done`。相反，“终端 event 到了但 block/item 尚未 close”不会把 open draft 强行补成空块：当前 assembler 不在 terminal 时 flush draft。该情况下可能形成无下游 message、错误或不完整交付，但不是由 open draft 产生空 text block。

### 空上游、reasoning-only、tool-only

- **空 Anthropic SSE 输入：** `stream_delivery()` 没有任何完成块且占位 timer 未触发时不发送任何字节，测试见 `tests/unit/test_stream_delivery.py:230-232`。若沉默持续到占位 deadline，则路径 A 先发空 text block。
- **空 Responses SSE output，且没有 message item：** 当前 assembler没有块可交付；占位 timer 未触发时不会凭 terminal 补 text block。若 timer 已触发，则已经由路径 A 发出空 text block。
- **reasoning-only：** `src/app/pipeline/delivery/assembler.py:276-281` 形成 thinking block；没有附加 text block。
- **tool-only：** `src/app/pipeline/delivery/assembler.py:268-275` 形成 tool_use block；terminal stop reason 变成 `tool_use`，见 `src/app/pipeline/delivery/assembler.py:288-305`；没有附加 text block。

## 当前 CLI 的非 SSE 响应

### Responses→Anthropic translation

**[强，代码事实]** `response_payload()` 只在 `translation_required=True` 时翻译，见 `src/app/server/handler.py:257-273`。Responses response reader 在 `src/app/pipeline/translation_driver/responses.py:113-137` 遍历 output item：

- Responses `message.output_text` 经 `src/app/pipeline/translation_driver/openai_responses.py:200-204` 成为 `ContentBlock(TEXT, text=...)`，空串和纯空白原样保留。
- Responses `reasoning` 经 `src/app/pipeline/translation_driver/openai_responses.py:170-183` 成为 REASONING block。
- Responses `function_call` 经 `src/app/pipeline/translation_driver/openai_responses.py:151-160` 成为 TOOL_USE block。

Anthropic writer 的关键行为：

- `src/app/pipeline/translation_driver/anthropic_messages.py:163-165`：TEXT 无条件写成 `{"type":"text","text":block.text}`，没有 empty／blank guard。
- `src/app/pipeline/translation_driver/anthropic_messages.py:190-209`：REASONING 写成 `{"type":"thinking","thinking":...,"signature":...}`。
- `src/app/pipeline/translation_driver/anthropic_messages.py:168-174`：TOOL_USE 写成 tool_use。
- `src/app/pipeline/translation_driver/responses.py:71-90`：所有块渲染后若 `content` 为空，主动补 `[{"type":"text","text":""}]`。

由此得到以下逐场景结果：

| Responses 上游结果 | Anthropic 非 SSE 结果 | text block 是否为空 |
|---|---|---|
| `output=[]` | fallback `[{"type":"text","text":""}]` | 是 |
| message `content=[]` | reader 得不到 block，随后触发同一 fallback | 是 |
| 只有无法携带／被过滤的 UNKNOWN item | 最终 content 为空，触发同一 fallback | 是 |
| 显式 `output_text:""` | `[{"type":"text","text":""}]` | 是 |
| 显式纯空白 `output_text` | text 原样保留 | 是，累计值为纯空白 |
| reasoning-only | 一个 `thinking` block | 否，没有 text block |
| empty reasoning summary，但有 reasoning item | 一个 `thinking:""` block及 carrier signature | 否，没有 text block |
| tool-only | 一个 `tool_use` block | 否，没有 text block |

因此，问题 3 的直接答案是：`anthropic_messages.py` 本身不为 reasoning-only 追加 text；它把 reasoning block 写成 thinking。empty-content 的补空行为在相邻的 response writer `responses.py:79-81`，不是在 `anthropic_messages.py` 内部。显式空 TEXT 则由 `anthropic_messages.py:164-165` 原样写出。

### `/v1/messages` 直通且 `translation_required=False`

**[强，代码事实]** 非 SSE 路径的 `response_payload()` 在 `src/app/server/handler.py:263-265` 原样返回 body。因此本项目不会在这里给一个原本无 text block 的上游响应新增 text block；但上游响应若本来含 `{"type":"text","text":""}` 或纯空白 text，本项目也不会过滤，会逐字返回。

## 旧 app_factory／`src/app/delivery/*` 路径

这套路径仍在仓库中，并由 `src/app/routes/anthropic.py` 与 `src/app/anthropic/client.py` 使用，但当前 CLI 接线指向 `create_pipeline_app()`，不是 `app_factory`。以下结论不应无条件外推为当前 CLI 行为。

### SSE

**[强，代码事实]** Responses parser 明确允许空 authoritative output text：

- `src/app/openai/responses_stream_parser.py:331-378`：`content_part.done.text` 允许空，并构造 `TextBlock(authoritative)`。
- `src/app/openai/responses_stream_parser.py:390-411`：`output_text.done.text` 允许空，并构造 `TextBlock(authoritative)`。
- `src/app/openai/responses_stream_parser.py:680-751`：`output_item.done.content[*].text` 允许空，并构造 `TextBlock(authoritative)`。

renderer 在 `src/app/delivery/anthropic_sse.py:486-510` 对任何 `TextBlock` 都发送 `content_block_start(text="")`；只有 `if content.text` 为真才发送 delta；随后 `src/app/delivery/anthropic_sse.py:581-587` 总是发送 stop。因此空串成为 start＋stop、没有 delta的空 text block；纯空白字符串 truthy，会成为 start＋空白 delta＋stop。

这套 parser 对“message item 的 content 数组完全为空”有一个窄守卫：`src/app/openai/responses_stream_parser.py:680-703` 不构造 TextBlock，且 `src/app/openai/responses_stream_parser.py:502-517` 把 completed-with-message-but-zero-completed-blocks 降为 `empty_response_content` error。它覆盖的是“空 message source”，不覆盖显式 `output_text:""`，也不是交付层的通用空 text guard。

reasoning-only 和 tool-only 分别形成 reasoning／function-call block，不附加 text。空 text 是独立 block 时仍照发。

### 非 SSE

**[强，代码事实]** `src/app/anthropic/client.py:275-297` 调用 `convert_responses_response_to_anthropic()`。该 converter：

- `src/app/protocols/responses_anthropic.py:153-174` 对每个 `output_text` 无条件追加 text block，空串／纯空白都保留。
- `src/app/protocols/responses_anthropic.py:121-133` 在最终 content 完全为空时主动追加 `ContentBlock(type="text", text="")`。
- reasoning-only 在 `src/app/protocols/responses_anthropic.py:107-111` 追加 thinking block后 content 已非空，不触发 text fallback。
- tool-only 在 `src/app/protocols/responses_anthropic.py:104-106` 追加 tool_use block后 content 已非空，不触发 text fallback。

## “空块不发”守卫盘点

**结论：[强，已按 producer、assembler、renderer、nonstream writer 和入口接线逐项核对] 没有通用的空 text block suppression。**

存在的相邻守卫不能回答“空 text block 不发”：

1. `src/app/pipeline/delivery/anthropic_sse.py:173-175` 的 `render()` 在整个 block iterable 为空时不发 message preamble；它不检查每个 text block 的文本。
2. `src/app/openai/responses_stream_parser.py:502-517` 拒绝旧路径中的 completed empty-message source；它不拒绝显式空 `output_text`。
3. `src/app/delivery/anthropic_sse.py:499-509` 的 `if content.text` 只抑制空 delta，不抑制 start/stop，反而形成“开了 text block 却无 delta”的 wire 序列。
4. `src/app/pipeline/delivery/stream.py:118-120` 明确让 synthetic empty block 绕过 buffer；buffer 不是空内容过滤器。
5. `src/app/models/anthropic.py:12-24` 的 wire model 对 `text` 只有 `str | None` 类型约束，没有非空或非空白约束。

覆盖块类型方面：没有任何守卫覆盖“所有 text blocks”。thinking／tool_use 的 delta 规则是各自协议语义，不构成 text guard。

## 真实 cassette 一手证据

检查对象共 3 个：

- `tests/cassettes/anthropic_to_responses_stream.json`
- `tests/cassettes/history_anthropic_stream.json`
- `tests/cassettes/history_responses_stream.json`

方法：先用 `rg` 定位 `text:""`、`content_block_start/delta/stop`、`response.content_part.*`、`response.output_text.*`、`response.output_item.*`；再逐 cassette 拼接真实 chunk、解析 SSE data JSON，并按 block index 或 `(output_index, content_index)` 累计 text。这样可区分协议正常的空 start placeholder 与最终累计空 block。

结果：

1. **`history_anthropic_stream.json`：[强，一手录制]** `tests/cassettes/history_anthropic_stream.json:25` 有协议正常的 `content_block_start`，start payload 是 `text:""`；在 `tests/cassettes/history_anthropic_stream.json:109` stop 前共有 27 个非空 `text_delta`，累计文本非空。没有“start 后无 text delta”或累计空白 block。
2. **`history_responses_stream.json`：[强，一手历史派生 cassette]** `tests/cassettes/history_responses_stream.json:37` 有 `response.content_part.added` 的空 `output_text` placeholder；随后有 115 个非空 output text delta，`tests/cassettes/history_responses_stream.json:385` 的 `response.output_text.done` 也非空，`tests/cassettes/history_responses_stream.json:391` 的 closing item authoritative text 非空。没有最终空 text。
3. **`anthropic_to_responses_stream.json`：[强，一手录制]** `tests/cassettes/anthropic_to_responses_stream.json:238` 的 content-part added 是空 placeholder；随后有 2 个非空 delta，`tests/cassettes/anthropic_to_responses_stream.json:247` 的 done text 是 `PONG`，`tests/cassettes/anthropic_to_responses_stream.json:253` 的 closing item text 也是 `PONG`。没有最终空 text。

**样本边界：** 这三份 cassette 只能证明这三次录制／派生流没有目标序列。它们没有覆盖 240 秒 synthetic timeout、上游显式 empty output、close-before-first-delta、reasoning-only 或 tool-only 的全部组合，因此不能用于宣称生产上不可能出现空块。

## 对待验证假设的裁决

### 已确认部分

**[强，足以行动]** “我们自己的上一轮响应能够向 Claude Code 交付一个空 text content block”成立，至少有一条完全由本项目主动产生的明确路径：默认 240 秒的 synthetic response block。另有多条上游 empty／close-before-delta 被本项目无过滤交付的路径，以及非 SSE Responses empty-content fallback。

### 未确认部分

**[中，仅为可检验推断，不能据此封口]** 当前 400 就是由上一轮 synthetic empty block 导致，尚未由本次代码调查证明。要把可能性升级为该次事故的根因，至少需要上一轮同一 Claude Code session 的响应 capture／history，或时间线证明上一轮在首个 SSE event 前跨过了实际配置的 synthesis deadline，并看到客户端收到 start＋空 delta＋stop。当前三个 cassette 都没有这一序列。

### 优先排查顺序

1. 查看报错请求前一轮同 session 的下游 SSE 或 history，搜索完整的 `content_block_start(type=text)`→无非空 text delta→`content_block_stop` 序列。
2. 对照该进程实际 `client_delivery.synthesized_response_headers_after_sec`，并检查上一轮首 SSE event 延迟是否超过该值。默认值是 240 秒，但运行实例可能覆盖配置。
3. 若上一轮是非 SSE Responses 翻译，检查 upstream `output` 是否为空、message content 是否为空，或所有 item 是否均无法渲染；这些形状会走明确的空 text fallback。
4. 若上一轮是直通 Anthropic SSE，检查上游是否自己关闭了一个无 delta／仅空白 delta 的 text block；当前交付层会完整复现它。
