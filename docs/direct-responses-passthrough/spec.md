# 直连 Responses 路径：保真透传产品规格

日期：2026-08-30
状态：**DRAFT — 待独立评审**。实现未开始。
定义域：**inbound 与 target 同为 `openai-responses`**（即 `route.translation_required is False`）。本规格不覆盖任何其他路由。

> **本文是活文档，不冻结。** 新裁决、实测或发现与本文冲突时当场修订，每次修订记入 §10。

## 1. 为什么需要这份规格

同格式直连请求上，客户端说 Responses，上游说 Responses，中间却走了一次往返翻译：

```
上游 Responses events → Anthropic CompletedBlock → 客户端 Responses events
```

`CompletedBlock` 的定义原文是「one fully materialised **Anthropic** content block」。在这条路径上，把 item 降到 Anthropic 语义再升回来，**唯一的消费者就是那个负责把它升回来的 framer**——纯损耗，且每一次往返都在损耗点上出过故障：

| | 损耗 | 故障 |
|---|---|---|
| GitHub issue #1 | `web_search_call` 无 Anthropic 块对实现，降级成散文 | 实现块对时 framer 不认，撕流 |
| GitHub issue #2 | `custom_tool_call` 连降级都没有，kind 与 payload 矛盾且 payload 为空 | `ValueError`，200 已发出后撕流 |

`ResponseOutputItem` union 共 **28** 个顶层成员（`openai/types/responses/response_output_item.py`，逐字核对）；翻译层认识 6 个。**22 个**落进兜底。issue #2 只是其中第一个被真实客户端触发的。

## 2. 第一原则（用户 2026-08-30 裁决）

> **代理不认识一个 item，不构成在直连腿上拒绝、丢弃或改写它的理由。**

用户原话：「协议允许，凭什么拒绝？」

客户端与上游说同一种语言。**代理的理解力不是客户端能力的上界**——一个代理读不懂的合法 item，客户端很可能读得懂，而且它本来就是冲着那个上游去的。在这条腿上以「我方无法转换」为由毙掉 turn，是把我们的无知强加给一个不需要我们理解任何东西的客户端。

**这条原则划定了本规格与 `anthropic-responses-bridge/spec.md` 的边界。** 那份规格的 response 矩阵规定「未知 output item → `REJECT`」，其定义域是 **Anthropic inbound → Responses upstream** 的转换——直连腿不发生该转换，故该条**不适用于本腿**。2026-08-30 的一次实现曾把该条套用到直连腿上（`main` 的 `ca777df`），那是定义域误用，本规格落地时必须撤销直连腿的那一半。翻译腿的 `REJECT` 不变，那里转换确实做不到。

## 3. 保真层级：事件级，逐字

**承诺**：上游发给我们的每一个属于某 output item 的 SSE 事件，其 `event` 名与 `data` 载荷**逐字**重放给客户端，**包括本代理不认识的事件类型与不认识的字段**。

**可行性依据**：`SseEvent` 保留 `event` 与**未经 re-serialise 的原始 `data` 文本**（`sse_source.py`）。项目已经在用同一机制做直连腿的失败事件重放，`StreamFailure.raw_data` 的注释写明了理由：「a round trip through a JSON encoder keeps the fields and not the bytes」。本规格把该既有做法从失败事件扩展到全部 output item 事件。

**允许改动的，且仅限这些**：

| 可改 | 理由 |
|---|---|
| SSE 帧外壳（重新组帧） | 帧边界是交付侧的事；`stream.py` 既有注释「Only the SSE wrapper is rebuilt, because frame boundaries are this side's to draw」 |
| 投递**时点**（推迟到 item 完成边界） | 本项目是块级交付，见 §4 |
| `sequence_number` **重编** | 时点改变后原序号不再连续；SDK 解析器要求单调 |
| `output_index` **重编** | 同上；且与已投递单元数一致 |

**明确不承诺**（写出来是为了不让读者误读「原样」）：
- **不是字节级**。多行 `data:`、SSE 的 `id:` / `retry:` 字段、注释行在 `SseEvent` 之后已不可恢复。若将来需要字节级，捕获必须发生在 SSE 解析之前，那是另一份规格。
- **不保证事件之间的原始时间间隔**。块级交付按 item 边界成批发出。

## 4. 交付单位

**一个 output item = 一个交付单元。** 该 item 的全部原生事件被缓存，在其 `response.output_item.done` 到达时按**原顺序**一次性发出。

理由：本项目的块级交付契约（缓冲、背压、keepalive、retry position）以「一个完整单元」为粒度，而 output item 是这条腿上天然的完整单元。这样既保住了那套机制，又不需要理解单元的内容——**边界归交付侧，内容归上游**。

`response.created` / `response.in_progress` 与终局事件不属于任何 item，处置见 §5.4、§5.5。

## 5. 各字段与各事件的处置

### 5.1 item 专有事件

**必须**原样重放，包括但不限于 `response.custom_tool_call_input.delta` / `.done`、`response.function_call_arguments.delta` / `.done`、`response.output_text.delta` / `.done`、`response.reasoning_summary_text.delta`、`response.web_search_call.*`、`response.content_part.added` / `.done`、`response.output_text.annotation.added`，以及**任何未来新增的**。

**不得**因「本代理不消费该事件」而丢弃它。issue #2 的根因正是 `custom_tool_call_input.delta` 无人消费。

### 5.2 item id

**必须**使用上游在该 item 事件中给出的 id，逐字。**不得**重新 mint。

`ResponsesFramer` 今天自铸 id，依据是实测「上游 id 在 `added` 与 `done` 之间会变」。那条实测只支持一个结论——**不能用 `added` 的 id 去关联 draft**——不支持改写发给客户端的 id。该 id 可能是客户端下一轮回传的 opaque handle，改写它的后果未测。

### 5.3 `response.id`

**必须**使用上游的，逐字，不重新 mint。同 §5.2 的理由。

### 5.4 `response.created` / `response.in_progress`

**必须**原样重放上游的，**不得**由本代理合成。今天 `ResponsesFramer.preamble()` 合成的 `response` 对象只包含字段子集。

### 5.5 终局事件与 terminal response object

**必须**原样重放上游的 `response.completed` / `response.incomplete` / `response.failed` / `response.cancelled`，**整个 `response` 对象逐字**——含 `status`、`incomplete_details`、`usage`、`tool_usage`、`metadata` 以及本代理不认识的任何根级字段。

**不得**由 `Terminal.stop_reason` 反推。那是一个面向 Anthropic 的派生摘要（`max_output_tokens` 改写成 `max_tokens`、由 `_saw_tool_call` 推 `tool_use` / `end_turn`），在本腿上**只作内部可观测用途，不得成为 wire 的 source of truth**。

### 5.6 reasoning

`encrypted_content` **必须**原样交还，**不得**经本项目的 reasoning carrier 编解码。carrier 的存在理由是「Responses 的 `encrypted_content` 没有 Anthropic 拼法，所以装进我们签名的载体里」——本腿没有这个跨协议问题。

**待确认**：同一会话下一轮客户端把它原样发回时，请求侧是否会把它当作 carrier 去解码。实现前必须验证。

## 6. 三种 buffering policy 在本腿的含义

| policy | 含义 |
|---|---|
| `block` | 每个 item 的事件组在其 `done` 后立即发出。默认。 |
| `until-tool-use` | **判据必须由 item type 给出，不得由 Anthropic block kind 给出。** 今天 `BlockBuffer.add()` 读 `kind == TOOL_USE`；本腿没有 Anthropic kind，需要一个「这是客户端待执行的工具调用吗」的直连侧判据。**哪些 item type 算，本规格未定，实现前必须补。** |
| `full` | 全部事件在上游终局后一次发出。 |

## 7. 失败、截断与容量

- **上游终局失败事件**（`response.failed` / `response.cancelled` / `error`）：原样重放，见 §5.5。既有 `_report_failure` 的 passthrough 分支已是此行为。
- **`status: "incomplete"` 的 item**：**必须**照常交付，**不得**套用翻译腿的 `cut_short` / hand-over 政策。那套政策的前提是「客户端能接住合成的 hand-over 块」，而 `hand_back_block()` 对非 Anthropic inbound 明确返回 `None`——在本腿上它只会让最后一个 item 消失。
- **上游 EOF 无终局事件**：本腿无法合成一个可信的终局（§5.5 禁止推导），故**必须**按流被截断处理并让客户端可见，具体形态**待定**。
- **memory cap**：`CompletedBlock.size_bytes` 取 `len(repr(payload))`。本腿持有的是原始事件文本，计量口径**必须**改为实际持有的字节数。**cap 的语义是「限制我方持有」还是「限制交付量」，实现前必须确认**。

## 8. 非流式

非流式直连今天已是 body 原样返回（`reply.py::response_payload` 在 `translation_required is False` 时直接返回）。**本规格不改变它**，并确认它与 §2 一致。

## 9. 尚未确定，实现前必须闭合

1. §6 的 `until-tool-use` 判据（哪些 item type 算工具调用）。
2. §7 的 EOF 无终局形态。
3. §7 的 memory cap 口径。
4. §5.6 的 carrier 回传验证。
5. Copilot 是否会在响应 `output` 里发 `function_call_output`——影响的是**翻译腿**的已知集合分歧（见 [`reports/260830-known-set-divergence.md`](reports/260830-known-set-divergence.md)），本腿因不做翻译而不受影响。

## 10. 修订记录

| 日期 | 条款 | 变化 | 触发 |
|---|---|---|---|
| 2026-08-30 | 全文 | 初稿 | GitHub issue #1／#2；用户裁决「协议允许，凭什么拒绝」；方案评审 [`reports/260830-review-plan.md`](reports/260830-review-plan.md) 的 blocker-01 要求实现前必须有本规格 |
