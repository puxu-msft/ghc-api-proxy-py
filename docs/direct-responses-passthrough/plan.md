# 直连 Responses 路径：停止不必要的往返翻译

日期：2026-08-30
状态：**方案待评审**，未实施
触发：GitHub issue #1（`server_tool_use`）与 issue #2（`custom_tool_call`）——两次撕流，同一个架构缺陷
取证：[`../tmp/260830-custom-tool-call-forensics.md`](../tmp/260830-custom-tool-call-forensics.md)、[`reports/260830-native-block-pair-gap-reconciliation.md`](reports/260830-native-block-pair-gap-reconciliation.md) G1b

> 用户 2026-08-30 的判断是本方案的起点：「作为直连路径，这两次的问题都不该出现」。

## 1. 缺陷是什么

直连 `/responses` 请求上，客户端说 Responses，上游说 Responses，中间却走了一次**往返翻译**：

```
上游 Responses events → Anthropic CompletedBlock → 客户端 Responses events
```

中间那一步是纯损耗。`assembler_for` 按**上游方言**选 assembler，`framer_for` 按**客户端腿**选 framer，两者在直连路径上指向同一个协议，而中间的 `CompletedBlock` 是 Anthropic 词汇（`blocks.py` 的定义原文：「one fully materialised *Anthropic* content block」）。

**损耗点正好是两个 issue 的位置**：

| | 往返丢了什么 | 表现 |
|---|---|---|
| issue #1 | `web_search_call` 没有 Anthropic 块对实现，降级成散文 | 实现块对后 framer 不认（G1b 已用测试钉住） |
| issue #2 | `custom_tool_call` 连降级都没有，`kind` 与 payload 互相矛盾且 payload 为空 | `ValueError`，200 已发出后撕流 |

## 2. 爆炸半径：22 / 28

`ResponseOutputItem` union 共 **28** 个顶层成员（`openai/types/responses/response_output_item.py:278-310`，逐字核对）。`ResponsesAssembler._open` 的映射表认识 5 个，加上 `_close` 单独救回的 `web_search_call`，共 **6** 个。

**其余 22 个全部落进 `.get(item_type, item_type)` 兜底**：`custom_tool_call`、`custom_tool_call_output`、`program`、`program_output`、`additional_tools`、`compaction`、`mcp_call`、`mcp_list_tools`、`mcp_approval_request`、`mcp_approval_response`、`code_interpreter_call`、`computer_call`、`computer_call_output`、`file_search_call`、`shell_call`、`shell_call_output`、`apply_patch_call`、`apply_patch_call_output`、`image_generation_call`、`local_shell_call`、`local_shell_call_output`、`function_call_output`。

issue #2 只是其中第一个被真实客户端触发的。**这不是一个 item type 的问题。**

## 3. 三个独立缺陷

取证把它们分开了，三个都要修，修法不同。

### D1 — 兜底产出自相矛盾的块

`_open` 把未知类型映射成**它自己**（`.get(item_type, item_type)`），`_close` 的末尾 `else` 构造 `TEXT` 形状的 payload 却不同步设 `kind`（相邻的 `WEB_SEARCH_CALL` 分支设了）。

实测探针：`kind='custom_tool_call'`，`payload={'type':'text','text':''}`。

- Responses 腿：framer 认不出该 kind → `ValueError` → 撕流。**这就是 issue #2。**
- Anthropic 腿：`block_frames` 三分支全不命中，`_delta_for` 返回 `None`，客户端收到 `content_block_start{"type":"text","text":""}` + `stop`，一个**空 text 块**。不崩、不告警、日志上是一次成功交付。

**payload 为空不是巧合**：`custom_tool_call` 的内容走 `response.custom_tool_call_input.delta` / `.done` 两个专有事件，而 `push` 只消费 `output_text.delta`、`reasoning_summary_text.delta`、`function_call_arguments.delta`。所以 `draft.text` 与 `draft.partial_json` 双双为空。

**由此可知：仅让 `kind` 与 payload 一致，是把响亮的失败换成安静的失败。** 项目已经两次写下这个教训（`web_search_call` 分支的「assembling from the draft is what produced an empty text block on every search」，`DISCARDED` 常量的「the fallback renders an empty text block, and an assistant turn carrying one is refused when the client replays it」），并为两个具体 item type 单独绕开了兜底——但没有修兜底本身。

### D2 — `stop_reason` 说谎

`_close` 只在 `draft.kind == TOOL_USE` 时置 `_saw_tool_call`；兜底走不到，于是 `_read_terminal` 算出 `stop_reason = "end_turn"`。

**客户端被告知模型正常说完了，实际上模型发起了一次工具调用并在等结果。** 客户端不会执行工具、不会回传结果，这一轮静默中断。

**两条腿都有，缓冲侧也有**（缓冲侧的 `has_tool_call` 由 `response.blocks` 算，被丢弃的块不在其中）。这与 D1 独立：修好块的去向，仍会告诉客户端「模型说完了」。

### D3 — 流式与缓冲对同一事实给出不同答案

| | 流式（`ResponsesAssembler`） | 缓冲（`blocks_from_item`） |
|---|---|---|
| 未知 item 的内部表示 | `kind = <item type 字符串>`，与 payload 矛盾 | `BlockKind.UNKNOWN`，**有专属的名字** |
| 交给 Responses 客户端 | **`ValueError`，撕流** | 丢弃，正常交付 |
| 交给 Anthropic 客户端 | 静默空 text 块 | 丢弃，不产生空块 |
| 是否留下记录 | **无** | `LossCode.ITEM_NOT_CARRIED` |

**缓冲侧的设计是对的，流式侧是错的。** 流式侧有 `DISCARDED`（「认识但故意不投递」）却没有一个表示「不认识」的值；那条常量的注释亲口划出了这个区分，并把兜底那一半留空了。

## 4. 方案

分两层，两层都必要，且互不重叠。

### 层一 —— 直连腿以原始 item 为块的载体（消灭 22/28 的整个面）

`ResponsesAssembler` 接收一个「客户端腿」参数（G1b 已论证过要加的那个），当客户端腿是 Responses 时：**所有** output item 一律产出一种保真块，payload 是上游 item 原文，不做任何类型映射；`ResponsesFramer` 认这种块，原样重发 `output_item.added` + `.done`。

**依据**：`CompletedBlock.payload` 的消费者只有三类——两个 framer（渲染）、`Terminal.record`（只取 `payload["name"]` 与 `payload["thinking"]` 两个派生字段）、`BlockBuffer`（排序与缓冲，**完全不读 payload**）。最后一条是关键：块级交付只需要**块边界**，不需要理解块内容。而在直连路径上，翻译成 Anthropic 词汇的唯一消费者，就是那个负责把它翻回去的 framer。

**收益**：22 个未知类型一次性保真，**包括 OpenAI 以后新增的**；issue #1 与 issue #2 在直连腿上同时消失，且是同一个原因消失的；直连腿不再需要认识任何 item type。

**Anthropic 腿一个字不动**，块对工作（§5.3／§6.3）照旧。

### 层二 —— 翻译腿引入 `UNKNOWN`，与缓冲侧对齐（消灭 D1 的另一半与 D3）

`_open` 的 `.get(item_type, item_type)` 改为 `.get(item_type, UNKNOWN)`，`UNKNOWN` 与 `DISCARDED` 并列。`_close` 对它的处置与缓冲侧看齐。

**不要动 `ResponsesFramer.block` 第 187 行的 raise。** 那是最后一道能喊出「新增了 block kind 却忘了更新 framer」的门，且它是**有意**从静默失败改过来的。层一给 framer 增加的是一个它**认识**的新形状，不是放宽这道门。

### D2 的处置 —— 待评审裁定

层一让直连腿不再丢任何东西，`_saw_tool_call` 从 item type 派生即可。

翻译腿上，未知 item 被丢弃之后 `stop_reason` 报什么，**我没有确信的答案，列为评审要裁的点**：

- 报 `end_turn`：客户端把残缺当完整（今天的行为）
- 报 `tool_use`：客户端会去找 `tool_use` 块，找不到
- 第三条路：**不丢弃，降级成文本**——像 `web_search_call` 那样说出「模型调用了工具 X，本代理无法转达」。这样重放不会 400（非空文本），客户端与模型都知道发生了什么，`end_turn` 也不算说谎。这与项目已有的 `server_tool_text.py`「说出模型做了什么」是同一个模式，但与取证报告建议的「与缓冲侧看齐＝丢弃」相冲突。

## 5. 实施时要当心的三点

- **reasoning carrier**：直连腿原样透传意味着 `encrypted_content` 原样回给客户端。对直连客户端这是对的（它本来就是上游的客户端），但要确认没有别处依赖 carrier 编码。
- **item id**：framer 今天自己 mint id，依据是实测「上游 id 在 `added` 与 `done` 之间会变」。保真块只在 `done` 成块后重发两个事件，两个事件用同一份快照，**id 反而比上游更稳**。要把这条写进注释，否则读者会以为透传把不稳定带回来了。
- **`output_index`**：framer 已有自己的计数器，保真块沿用即可。
- **`CompletedBlock.size_bytes`（自查补入，2026-08-30）**：`BlockBuffer._enforce_cap` 用它做内存上限，取的是 `len(repr(payload))`。保真块装的是**整个 item**，而翻译块装的是从中提取出的文本，所以同一份上游内容在直连腿上的计量会更大、缓冲上限会更早触发。它读的是长度不是语义，**因此不推翻层一的前提**，但需要确认 cap 的语义是「限制我们持有的字节」还是「限制交付给客户端的内容量」——若是后者，直连腿的计量口径要重新定。

## 5.1 一条已经存在的原则，本方案只是把它贯彻完整

`delivery/stream.py:287` 早已写下：

> On a direct leg the client speaks upstream's dialect, so upstream's event name and payload go back out **as they arrived** — including the fields nothing here recognises, which is the whole of "even if we do not know it, it can still be passed on". Only the SSE wrapper is rebuilt, because frame boundaries are this side's to draw.

这条今天**只应用在失败事件的转发上**（`StreamFailure.raw_data`），没有应用到 output item 上。层一不是引入一条新架构原则，而是把项目自己已经写下并给出理由的这一条，应用到它本来就该覆盖的对象上。「Only the SSE wrapper is rebuilt, because frame boundaries are this side's to draw」也正好是层一保留块级交付的理由——边界是我们的，内容不是。

顺带一个反衬：缓冲侧 `reply.py:55` 构造块时是 `kind=str(payload.get("type", ""))`，**kind 与 payload 天然一致**。流式兜底产出二者矛盾的块，在同一个仓库里连内部一致性都没有对齐。

## 6. 尚未闭合

- 取证第 6 条（cassette 与 history db 里有无真实 `custom_tool_call` 样本）因工具受限未完成，报告 §6 列了待补的两条命令。
- 「未知 item 的内容若经 `output_text.delta` 累积会出现在 `content_block_start` 却没有 delta」——取证标为 [INFER，置信度中]，机制清楚但没有构造出真实会这样累积的 item type。层一对直连腿消除该路径；翻译腿是否需要单独处置，随 D2 一并裁。
