# 直连路径：原生透传产品规格

日期：2026-08-30
状态：**DRAFT v21 — 待复评**。§3.1 的三处前置缺陷全部已合入 `main`（P1／P2 在 `7e96adc`，P3 在 `109dc44`），骨架亦已合入（`01c33f1`）。**Responses 直连腿已接线并合入 `main`**（`1fb37cd`，源提交存于 `archive/260901-passthrough-wiring`），issue #2／#3 关闭，**issue #4 的根因随同一次接线消除**（§6.2、§6.4；已污染的客户端历史由 §6.5 的 opt-in 修补处置，用户 2026-09-01 裁决）；**§10 的 Responses 流式直连 terminal status 与 typed client-action facts 分槽合同已由 `bb5783f` 实现**；**Anthropic 直连腿的词汇已实现、未接线**（§2.8）。**§11 有一项待用户裁决**（响应头黑名单的定义域）；已污染的客户端历史那一项**用户已于 2026-09-01 裁决**，条款是 §6.5。
定义域：**任何 `route.translation_required is False` 的路由**，不限方言。v10 之前本规格只覆盖 `openai-responses` 两端；用户 2026-08-31 裁决「根因修复所有直连路径」，定义域随之放宽（§2.1）。

> **目录随之从 `direct-responses-passthrough` 改名为 `direct-passthrough`。** v10 第一稿保留了旧名，理由是「改名会让报告里的引文指向不存在的路径」——那条理由用错了地方：路径重写会伪造的是**报告里的原句**，而同一条规则的另一半正是「文件搬了就把活文档的链接指过去」。目录名是活的，一个窄于内容的名字本身就是缺陷。已重指的是活文档与源码注释；**12 份评审报告内文里的旧绝对路径原样保留**，它们记录的是当时的位置，重写才是伪造。

> **本文是活文档，不冻结。** 新裁决、实测或发现与本文冲突时当场修订，每次修订记入 §12。
>
> v2 按 [`reports/260830-review-spec.md`](reports/260830-review-spec.md) 重写（blocker 3、major 5，全部采纳）。v1 的自相矛盾与超范围归属见 §12。

## 1. 为什么需要这份规格

同格式直连请求上，客户端说 Responses，上游说 Responses，中间却走了一次往返翻译：

```
上游 Responses events → Anthropic CompletedBlock → 客户端 Responses events
```

`CompletedBlock` 的定义原文是「one fully materialised **Anthropic** content block」。这条路径上每一次往返都在损耗点上出过故障：

| | 损耗 | 故障 |
|---|---|---|
| GitHub issue #1 | `web_search_call` 无 Anthropic 块对实现，降级成散文 | 实现块对时 framer 不认，撕流 |
| GitHub issue #2 | `custom_tool_call` 连降级都没有，kind 与 payload 矛盾且 payload 为空 | `ValueError`，200 已发出后撕流 |

`ResponseOutputItem` union 共 **28** 个顶层成员；翻译层认识 6 个，**22 个**落进兜底。

**但「翻译是纯损耗」这个说法过头了，v1 写错了。** `CompletedBlock` 的消费者不止 framer：`BlockBuffer` 读整个 payload 的 `size_bytes` 做内存上限、读 `kind` 决定 `until-tool-use` 何时释放；`Terminal.record` 读 `kind`／tool name／thinking，流入完成行与 TUI。所以透传不是「拆掉中间层」，而是**把 wire 与可观测这两件事分开**——wire 走原生，可观测另立旁路事实（§10）。

## 2. 原则与其出处

**三条不同来源的依据，分开记，不要合并成一句。**

### 2.1 用户裁决（逐字锚）

**2026-08-30，原话：「协议允许，凭什么拒绝？」**

支持的命题，仅此一条：**不得以「本代理不认识」为由，拒绝一个协议允许的直连 item。**

它**不**单独支持「不得丢弃」「不得改写任何字段」「id 必须逐字」——那些另有出处，见 §2.2 与 §2.3。v1 把整套保真政策归给这一句，是超范围归属。

**2026-08-31，原话：「根因修复所有直连路径」。**

支持的命题：上面那条**不是 Responses 专有的**，它约束每一条 `translation_required is False` 的腿。这条裁决直接放宽了本规格的定义域，并否掉了「先只治 Responses、其余等将来」这个选项——本规格 v9 的定义域行正是那么写的，v10 依此裁决改写。

> **提出这个问题的是用户，不是本规格。** v9 把范围限制记为本规格的选择，并在回报里把「其余直连对同形缺陷仍在」列为一条自述的局限；用户读到之后直接裁了范围。所以这不是我推导出来的一般化，是用户对一个已知局限的裁决。

### 2.2 用户既有裁决与亲笔文档

- `docs/.human-controlled/message-translation.md`：直连**尽可能原样转发**。
- `.dev/docs/error-envelope/spec.md` 保存的用户 2026-08-23 原话：**「直连路径一定用原生的，即使我们未知，也能传递」**。

这两条共同支撑「本腿走 native」这个方向。

### 2.3 本规格在上述授权范围内的推导

事件级 logical fidelity 的**精确层级**（§3）、逐事件 id 的处置（§6）、全局顺序与 commit frontier（§4）、`requires_client_action` 判据（§7）、可观测旁路（§10）——**这些是本规格的推导，不是用户裁决**，可由评审共识修正。

### 2.4 定义域边界

`anthropic-responses-bridge/spec.md` 的 response 矩阵规定「未知 output item → `REJECT`」。**该矩阵不适用于本腿**：那份规格逐字把定义域钉在 Anthropic `/v1/messages` inbound 选择 Responses upstream，其 downstream 始终是 Anthropic JSON／SSE；它排除 raw Responses passthrough 的理由正是「下游不是 Responses 客户端」，而本腿的下游就是。

`ca777df` 把该矩阵套用到了直连腿，是定义域误用，本规格落地时**必须撤销直连腿的那一半**。翻译腿的 `REJECT` 不变。

跨腿合同（error envelope、keepalive）仍然适用。

### 2.5 一个引擎，每种方言一份词汇

**本规格的绝大部分条款与方言无关**，这是 v10 放宽定义域之后必须先说清的事：§3 的保真层级、§4 的交付单位与全局顺序、§5 的 commit frontier 与 replay、§7 的三种 policy 与收口顺序、§8 的失败与容量、§9／§9.1 的非流式与响应头、§10 的可观测合同——它们描述的是「一条不翻译的腿如何交付」，句子里没有一个 Responses 专有的事实。

**方言专有的只有一份词汇**，每种直连格式各给一份。下表**八行**——v10 只列了六行，漏掉了实现里同样存在的 `read_failure` 与 `name`／`reply_dialect`，而漏掉的那两行不是装饰：`read_failure` 决定上游失败事件怎么被认出来，`reply_dialect` 决定完成行按哪把尺子判读这条回复（两种方言的字节阈值差一个数量级）。

| 词汇项 | 它回答什么 | `openai-responses` | `anthropic-messages` |
|---|---|---|---|
| control 事件集 | 哪些事件属于响应信封而不属于任何 item | `response.created`／`queued`／`in_progress`／`completed`／`incomplete`／`failed`／`cancelled`、`error` | `message_start`、`message_delta`、**`message_stop`**、`ping`、`error` |
| terminal 事件集 | 哪些 control 事件结束响应（§5 提交表「无 item 的 terminal／failure」那一行据此解除持有） | `response.completed`／`incomplete`／`failed`／`cancelled`、`error` | `message_stop`、`error` |
| item 归属键 | 一个事件属于哪个 item | `output_index` | `index` |
| item 闭合事件 | 哪个事件宣告某个 item 完整 | `response.output_item.done` | `content_block_stop` |
| `requires_client_action` | 该 item 是否要求客户端提交 tool output 或 approval（§7.1） | 见 §7.1 的判据 | block `type == "tool_use"` |
| terminal 事实的读法 | §10 要的 status、usage、stop reason 在哪 | `response.completed` 的 `response` 对象 | `message_delta` 的 `delta.stop_reason` 与 `usage` |
| failure 事件的读法 | 哪个事件表示上游说这轮失败了，它的 code／message 在哪 | `response.failed`／`cancelled`／`error`；`error` 有嵌套与扁平两种形状 | `error`，形状是 `{"type":"error","error":{...}}` |
| `reply_dialect` | 完成行与可观测记录按哪种方言判读这条回复 | `RESPONSES` | `ANTHROPIC` |

> **`message_stop` 必须在 control 集里。** 它是 Anthropic 的终局事件，而下一行的 terminal 集是 control 集的子集——v10 的表把它从 control 集漏掉了，照那张表实施会让每一条 Anthropic 直连响应的终局事件被判为「无法归属」并持有到永远，即挂死。实现是对的，v10～v12 期间不一致的那一侧是本规格。

**词汇只描述边界与归属，绝不描述 item 的类型学。**这是 §2.1 的直接后果：一份列举 item 类型的表会重建那道天花板，而边界词汇不会——`response.custom_tool_call_input.delta` 靠 `output_index` 归组，`content_block_delta` 靠 `index` 归组，两者都不需要知道那个 item 是什么。

### 2.6 四条直连腿今天各自的状态

| 直连对 | 状态 | 依据 |
|---|---|---|
| `openai-responses` ↔ `openai-responses` | **本规格的主体工作。**今天走翻译型 assembler，6 个已知 item 类型之外一律拒绝——GitHub issue #2 与 #3 都落在这里 | **已接线并合入 `main`**（`1fb37cd`）；issue #2／#3 关闭 |
| `anthropic-messages` ↔ `anthropic-messages` | **同形缺陷，而且它是主路径不是边角。**`sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` 记着实测：`claude-sonnet-5` 不支持 Responses API（`unsupported_api_for_model`），**Claude 系模型只能走直连**。这条腿今天走 `AnthropicAssembler` ＋ `AnthropicFramer` 的往返，未知 block 类型同样被 framer 拒绝。**落地前须先解决 §2.7 的整形问题** | 词汇已实现并单测（`anthropic_messages_passthrough.py`），**接线待 §2.8 的 hand-over 问题闭合** |
| `openai-chat-completions` ↔ `openai-chat-completions` | **天花板不存在，但那是偶然。**这条腿没有 framer，走 `one_shot_delivery` 把上游字节原样前送，所以没有任何类型表挡在中间。它缺的是**块级交付**——boundaries 在 `choices[].delta` 里面，2026-08-22 已裁决推迟 | 现状即满足 §2.1；块级交付的缺口是既有推迟项，不因本规格重开 |
| `openai-embeddings` ↔ `openai-embeddings` | 非流式，按 §9 处置 | 无 SSE 词汇 |

> `gemini-generate-content` 已在路由表中登记但没有 translator 应答，`InboundRoute.implemented` 挡住请求，因此今天不存在该格式的直连腿。它出现时须先有自己的词汇。

### 2.7 走 native 会拿掉每条腿现有的兼容整形，这不是可以顺手带过的副作用

**放宽定义域之后浮出来的一般事实**：今天每条直连腿的 framer 都在做一点兼容整形，而**纯透传按构造会把它一并去掉**。这不是实现细节，是用户可观察行为，每一条都要单独裁。

已知两例，严重度不同：

| 腿 | 整形 | 今天的状态 | 拿掉的后果 |
|---|---|---|---|
| `openai-responses` | `ResponsesFramer._item_id()` 由 `output_index` 生成，同一 item 的 `added` 与 `done` id 连续 | **默认生效**（framer 一直这么做），配置项 `hook_fix_responses_sse.fix_stream_ids` 是注释掉的候选 | 用户具名的 `@ai-sdk/openai` 一类客户端会被自己的连续性校验拒掉。见 [`deferred.md`](deferred.md) D-3 |
| `anthropic-messages` | `hook_fix_anthropic_sse.thinking.content_block_start_compat`，把嵌在 `content_block_start` 里的 thinking signature 抽成单独的 `signature_delta` | **默认 `"signature_delta"`，即默认开着** | 直接落在 **Claude 系模型唯一的那条腿**上。用户亲笔文档里这条还带着 TODO：「现在我认为（如果客户端真的不支持）这是应该常驻的」——即用户倾向把它变成常驻，而不是拿掉。见 [`deferred.md`](deferred.md) D-4 |

**处置模式 §6.2 已经给过，本节只是把它提升为通则**：兼容变换**必须**另立显式、可选的 reshape 合同，**不得**叫它 native 或逐字。所以正确的形状不是「透传吃掉整形」，也不是「为了保整形而不透传」，而是**透传逐字携带上游事件，声明过的 reshape 合同在其上运行**，且合同的存在与默认值对用户可见。

**因此本规格裁定：接线不得改变任何一条腿今天已生效的整形默认值。** Anthropic 腿的 `signature_delta` 默认开着，接线后仍然开着；Responses 腿今天没有 `fix_stream_ids`，接线后也不会凭空多一个。**要不要改那些默认值是用户的事，不是接线的副作用**（D-3、D-4）。

> 这条通则是 v10 放宽定义域**直接换来的**。只做 Responses 一条腿时，`fix_stream_ids` 看起来像那条腿的特殊情况；两条腿摆在一起才看出它是「native 与既有兼容层的关系」这个一般问题，而 Anthropic 那一例默认开着、又落在主路径上，严重度比先发现的那一例高得多。

### 2.8 §8 的「本腿不咨询 hand-over」是 Responses 腿的事实，不是所有直连腿的

**这条限定是放宽定义域时才暴露出来的，它此前写得比它成立的范围宽。** §8 曾写着代理侧错误「**不得**咨询只适用于 Anthropic 客户端的续写机制」，理由是本腿没有续写通道。那个理由在 Responses 腿上成立——客户端不是 Anthropic 客户端，执行不了那个合成的 `tool_use` 块。**在 Anthropic 直连腿上它不成立**：那条腿的客户端**就是** Anthropic 客户端，`hand_back_block()` 开头那句 `wire_format is not WireFormat.ANTHROPIC_MESSAGES` 按 inbound 格式门控，今天就放行，而 `max_tokens` 的续写是 2026-08-21 用户裁决的「总是 hand over」。

**于是 native 交付与它撞上了，而且是两层，顺序只是浅的那层。**

**其一，顺序，且不限于 `block`。** hand-over 合成一个 `tool_use` 块，它必须落在终局**之前**才是一份合法回复。本规格把上游自己的 `message_stop` 当作终局事件释放（§5 提交表「无 item 的 terminal／failure」那一行），而交付循环冲刷缓冲（含承载终局的那个批次）发生在 hand-over 判定**之前**，对三种 policy 一视同仁。v12 写的「在 `block` 下它早已出门」把范围写窄了——**写窄比写宽更危险**，它给出一条不存在的规避路径，会让 D-5 的候选 1 被做成半个修复。

**其二，类型，这一层更硬。** `_hand_over` 把合成的 `CompletedBlock` 交给 `framer.block()`，而透传腿的 framer 只认 `RawEventBatch`（它调 `batch.encode()`，`CompletedBlock` 没有这个方法）。**所以即使顺序问题解决了，那条路径依然是一次 200 之后的 `AttributeError` 撕流。**

**因此 Anthropic 直连腿的接线在本问题闭合前不进行。** 这不是缩减用户 2026-08-31 裁决的范围：词汇已实现并单测。**但也不是「缺的只是打开开关」**——上面第二层说的类型不匹配是一段还没写的代码，不是一个没翻的开关。挡住它的是 §2.7 自己那条规则——接线不得改变任何一条腿今天已生效的行为，而 `max_tokens` 续写在那条腿上今天就生效，且它正是 Claude 系模型唯一的路。

**待定的是形态，不是方向**（[`deferred.md`](deferred.md) D-5）：要么在 hand-over 可能发生时推迟终局的释放，要么让合成块以该方言的原生事件表达并接在终局之前，要么裁定 native 腿不提供续写并接受那是一次行为回归。**只有第三个选项需要用户裁**——它与 §2.7 冲突，是一次明确的行为回归；前两个是本规格推导，评审共识即可。**候选 1 单独不够**：它只解决顺序那一层，类型那一层原样还在。

> **Responses 直连腿不受此条阻挡**：那条腿上 §8 的原判据仍然成立（客户端执行不了 Anthropic 的合成块），`hand_back_block()` 的 inbound 格式门也本就不放行它。issue #2 与 #3 都在那条腿上。

## 3. 保真层级：合法 UTF-8 SSE 的 logical event 与 data

**承诺**：在**最终被提交的那一次 attempt** 中，凡属于一个**已完成的 item group**、或属于 control 与 terminal／failure 的 SSE 事件，其 `event` 名与**按 SSE 规范的 field parsing 算法得到的 logical `data` 字符串**逐字重放，包括本代理不认识的事件类型与字段。

> **基准是外部规范，不是本项目 parser 的输出**，这个区别是 P3 逼出来的。若以「本项目解析出来的东西」为准，那么 parser 把 payload 截断之后我们仍然「逐字重放了解析结果」，本承诺照样成立——**这句话就检测不出 §3.1 第三条那类缺陷**。钉到规范之后它才有分辨力。相应地，下面那份清单**必须按新基准重读**，它的五项身份并不相同：第 1 项是承诺范围的声明；第 2 项落在本承诺覆盖面之外，是真实取舍（`id:` 不重放会影响客户端的 `Last-Event-ID`）；**第 3、4 项其实与规范一致**——规范规定空 data buffer 不派发事件、规定用 UTF-8 decode 算法（其错误模式就是 replacement），列在这里只是免得读者自己去查；第 5 项描述的正是基准算法自身的规范化。

> **别把「与规范一致」的那两项当成待补的欠缺。** v8 曾把五项统称为「本项目 parser 的现有行为而非规范要求」，一个据此去「让 parser 更贴近规范」的人最可能动的恰恰是它们——例如把 `errors='replace'` 改成 `errors='strict'` 并抛错，那才是真的偏离。

**承诺不覆盖未闭合 item 的尾巴。** 一个 item 收到了 `added` 与若干 delta 却始终没有 `done`，其已缓存的事件在下列时点**丢弃**，且**不计作重排**：上游 tear、terminal 到达、failure 到达、cap 超限、deadline、客户端取消。

**「无法归属」的事件不属于上面这条，它有自己的裁定，见 §7.2 收口第 3 步。** 两者形似而来源不同：未闭合尾巴属于一个确定存在、确定没说完的 item；无法归属的事件则**不知道属于谁，也可能根本不属于任何 item**（§4 列出的四个 audio 事件就不属于任何 item）。把它们并进同一条会让后者继承前者的丢弃理由，而那个理由对它并不成立。

**上面的「承诺」一段同时覆盖按 §7.2 收口第 3 步被提交的无法归属事件**——它们既不属于任何已完成 group，也不是 control 或 terminal，若不在这里点名就会落进一条缝：§7.2 承诺逐字提交，§3 却没把它们纳入保真面。

> 这条限定是被一个反例逼出来的：`response.created → output_item.added(A) → delta(A) → response.failed`，其中 A 永不 `done`。此时「完整交付单位」「逐事件保真」「不重排」三项**不可兼得**——交付 A 就泄漏了不完整 item，让 failure 越过 A 就是重排，丢掉 A 又违反「每一个事件」的全称，不结束则 terminal 已到却仍在等。用户亲笔的块级合同把「`_start` 到 `_end` 之间的全部内容」定义为交付单位，所以放弃的必须是全称，而不是块级完整性。
>
> **terminal 不能证明一个未知 lifecycle 已经完成。** `response.failed` 恰是反例：它只说明 response 结束了，不说明某个没收到 `done` 的 item 变完整了。因此边界不明的 suffix 一律按不完整丢弃，而不是「既然 terminal 来了就当它完了」。

**不改写 `data` 内部的任何字段**——包括 `sequence_number`、`output_index`、任何 `id`，以及任何未知字段。v1 同时承诺「data 逐字」和「重编 sequence_number／output_index」，而**那两个字段就在 data 这个 JSON 文本里**，两者不可能同时成立。v1 给的理由（「时点改变后原序号不再连续」）也是错的：只推迟不重排时，原序号仍保持次序与连续性；三份 **Responses 流** cassette 的 sequence 均为 `0..N-1`。**只有重排才会破坏它，而本规格不重排（§4）。**

**可承诺范围**（实跑核验，见评审 finding 04）：

- 多行 `data:` → SSE 规则 join 为一个含 `\n` 的 logical string，**内容不丢**（丢的是原分行拼法）
- 空 `data:` → 保留为空字符串

**明确不承诺**：

- **不是 byte-level。** 
- 注释行、`id:`、`retry:` 与任何其他／未来 SSE field：`parse_frame` 丢弃，不重放
- 只有 `event:` 而无任何 `data:` 的帧：`parse_frame` 返回 `None`，不重放
- 非法 UTF-8：`errors='replace'` 已替换为 `�`，不可恢复
- field 前后空白与行尾（CRLF／LF）的规范化
- **不含冒号的 `data` 行**：规范要求把整行当字段名、值为空串（于是往 data buffer 追加一个空行），`parse_frame` 的 `if not separator: continue` 直接跳过它。实测 `b"data: a\ndata\ndata: b"` 得到 `a\nb`，规范应为 `a\n\nb`——**这是相对新基准的一处真实偏差**。后果是 payload 里的一个空行可能丢失，机制确定、**触发未测**（上游是否会写裸 `data` 行未知）；本项目自己的 `encode_frame` 总是写 `data:` + 行内容，所以出向不产生这种拼法。权重只够登记，不够列进 §3.1 的前置——它没有 P1／P2／P3 那样的截断后果

### 3.1 三处必须先修的既有缺陷

本承诺**不能**靠 v2 当时的 writer 兑现，实跑给出两个反例；两者都已在主仓 `7e96adc` 修复。条款保留——它们仍是规范性要求，只是已被满足。第三条不是 writer 而是 **reader**（`parse_frame`）的缺陷，它偏离的是上面钉住的那个外部算法。

1. **已实现（`7e96adc`）。** `_report_failure` 把含换行的 payload 写成一行 `data:` 加一行裸文本，客户端再解析只剩第一行。**必须**有一个接受 `(event: str, data: str)` 的 raw-text SSE encoder，对 `data.split("\n")` 的每一段各写一条 `data:`；**不得**复用只接受 dict 并 `orjson.dumps` 的 `SseFrame`。
2. **已实现（`7e96adc`）。** `read_events` 的 frame separator 固定为 `b"\n\n"`，两个合法 CRLF 帧会被合并成一个事件。这是两条腿共用的前置。
3. **已实现（`109dc44`）。** `parse_frame` 曾用 `str.splitlines()` 拆行，而它的断行集是 SSE 的**超集**——SSE 只认 CR、LF、CRLF。于是 data 里一个裸的 U+2028、U+2029 或 U+0085 会让该行**从此处截断**，后半段无论如何都不再构成一个 `data` 字段：没有冒号就被跳过，有冒号则落进一个既非 `event` 也非 `data` 的字段名（真实 payload 多半是后者，例如 `{"delta":"a<CH>b","output_index":0}` 的后半段）。两条路都丢内容，且截断后的 payload 不再是合法 JSON，随后落进 §4 的「无法归属」。**必须**改为只认 CR／LF／CRLF。

   > 机制已实跑证实（U+2028、U+2029、U+0085、VT、FF 五个字符逐一验过，均截断），**触发未证实**：VT 与 FF 在合法 JSON 里必须转义、不可能裸出现，真正有活性的是前三个——它们在 JSON 字符串里裸出现合法，是否真从 Copilot 出来取决于上游的编码器。这个权重足以要求修复，不足以支撑「生产上正在丢数据」。来源：[`reports/260831-review-skeleton.md`](reports/260831-review-skeleton.md) finding 10。

## 4. 交付单位与全局顺序

**交付单位是「安全前缀」，不是「单个 item」。**

维护一个 attempt 内的**全局事件队列**与一个**单调 commit frontier**：只有从 frontier 到某位置之间、所有已打开的 item 都已 `done` 时，才释放这段连续前缀。

- item lifecycle 交错时，**允许**一个已完成的 item 被更早的未完成 item 拖住；
- **不得**为了早发而重排事件——重排正是唯一会让 `sequence_number` 倒退、让 `output_index` 与 SDK snapshot 索引失配的原因。

**「已 `done`」指该 item 的 `done` 事件也落在这段前缀之内，不只是它的状态已经是 done。**一个 item 的事件**不得跨越释放边界**：若前缀末尾之后还留着属于该 item 的事件，就把边界回退到它最早的那个事件之前，反复直到稳定。

> 这一句 v6 之前是空的，两种读法都讲得通，而实现取了代价更大的那一读。反例（实跑）：`created → added(0) → added(1) → delta(1) → done(0)` 会释放 `[created, added(0)]`，把 item 0 的 `added` 与它的 `done` 拆开，中间隔着 item 1 的全部事件。代价有两层，第二层更贵：客户端拿到半个 group；而更要紧的是它**提交了本次 attempt**（§5），于是整轮的透明 replay 窗口被一个没有任何内容价值的字节关掉——item 1 若随后以可重试的失败结束，本可无痕重放的一整轮只能把失败露给客户端。取现在这一读，代价只是多一点 head-of-line blocking，而上面第一条本就已经接受了它。来源：[`reports/260831-review-skeleton.md`](reports/260831-review-skeleton.md) finding 01。

**只含 control 事件的安全前缀可以构成一个交付单位，但不得单独交付给客户端**——它随第一批可交付 item 事件一起落地（§5 提交表）。§4 决定哪一段字节构成交付单位，§5 决定它何时落到客户端。

> **v7 这句话的旧写法给了两种读法，而且已经有读者取了错的那一读。** 旧文写「不构成提交，它何时落到客户端由 §5 规定」，接着又说「§5 讲的是交付它算不算堵死了 replay」——前半句是「扣住不发」，后半句是「发了但不算数」。**§5 只支持前者**：§5 给「已提交」下的定义就是「客户端已经看到本次 attempt 的原生事件」，所以一旦真写出去它**就是**提交，「发了不算数」这种状态在 §5 里不存在。错读的代价不止是窗口关早：真做了 replay，客户端会收到**两个** `response.created`，且两者 `response.id` 不同——那是协议层面的坏帧。来源：[`reports/260831-review-spec-round7.md`](reports/260831-review-spec-round7.md) round7-02。

> 不写这一句就会撞上一个每个请求都发生的矛盾：上游首帧是 `response.created`，此时一个 item 都还没打开，上面的释放条件**空真**，于是 §7 的 `block` 行要求「一就绪即发出」，而 §5 要求它保持 attempt-local。若按前者，`response.created` 一写出去 attempt 即为已提交，§5 随即禁止整次 attempt replay——四轮评审产出的那一整套 replay 合同，在默认 policy 下永远走不到。来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-03。

未知 item-specific 事件**无须被任何类型表认识**，只需停在它原本的全局位置。无法判定某事件属于哪个 item 时，保守持有到 terminal——它与「这是 envelope 事件」是**两个相反的处置**，实现上必须是两个可区分的答案而不是同一个空值。

> 这不是假想形态。`openai==3.3.1` 的 `ResponseStreamEvent` 共 58 个成员，11 个不带 `output_index`，其中 7 个是 envelope，**另外 4 个是 audio 系列**（`response.audio.delta`／`.done`／`.transcript.delta`／`.transcript.done`）——它们承载模型输出，却既无 `output_index` 也无 `item_id`。payload 解不开时也落在这里。持有它的同时**不得**释放它后面的事件，那是重排。

> 三份 **Responses 流** cassette 的 `output_index` run 都是 `[0,1]`，**只说明已观测样本没有交错**，是趋势样本而非协议保证；本规格按可能交错设计。（`tests/int/cassettes/` 下共 5 个文件，带 Responses 事件流的是 3 个。）

## 5. Commit frontier 与 attempt replay

**「已提交」指客户端已经看到本次 attempt 的原生事件。** 它决定 replay 是否还合法，因此必须在本规格裁定，而不是由发送顺序偶然决定。

| 动作 | 是否提交本次 attempt |
|---|---|
| HTTP 200 headers | 否 |
| SSE comment keepalive | 否 |
| `response.created` / `response.in_progress` | **保持 attempt-local**，随第一批可交付 item 事件一起提交 |
| 第一批 item 事件 | 是 |
| 无 item 的 terminal／failure | 在最终决定不 replay 后，与本 attempt 的 control events 一起提交 |

**首个原生事件提交前**：retry taxonomy 判为可重试的 transport tear、无终局 EOF、可重试的 upstream failure，可在统一预算内**透明 replay**；旧 attempt 的 control events、item 队列、terminal、ids、usage 与内存计量**全部丢弃**——**丢弃发生在新流到手之后**（§5.2 的 `OpenedAttempt`），在此之前旧 attempt 的队列**必须保持可提交**，因为重开可能被拒或失败，那时 §7.2 要把这些已完成的 group 发出去。主仓 `stream.py:468-472` 今天就是这个顺序（`reopen` 返回非 `None` 之后才丢），Spec 此前两处复述反而比代码宽。

**首个原生事件提交后**：**禁止**整次 attempt replay，已交付前缀保留。这与用户亲笔的重试合同一致，概括为「尚未交付完整块可无痕重试；已交付块则不得从头重放」。

> **上面那句是概括，不是原文**，别拿引号去回指。人写文档里前半句的对应原句是「如果还没交付过完整块，直接在代理端无痕重试」；后半句**没有**对应句子——那里写的是已交付完整块之后走 MCP 合成续写，而该机制明确「目前只给 anthropic-messages 客户端请求时使用」。在本腿上结论仍然等价：本腿没有续写通道，§8 已裁定走 SSE error。

cap 超限、客户端取消、客户端 deadline 等人写文档列为不可继续的原因，**不得** replay。

**进程处于优雅关闭（draining）时同样不得 replay，这是用户裁决**：`docs/.human-controlled/upstream-retry-and-continuation.md` 在两张清单之后单起一段写着「特别地，优雅关闭时报错不再考虑无痕重试，可以走下文合成续写机制」。它裁的是 replay 的**资格**，因此判定发生在尝试重开**之前**，不是重开之后的一种拒绝。

> v6 之前 §5 全文没有记这条裁决，§5.2 把 draining 建模成「重开之后的拒绝」，时序恰好与裁决相反。主仓 driver 侧那扇门（`direct_driver/base.py:74-82`）已经按裁决实现成判定之前的拒绝，注释里逐字记着两扇门的这个差异——delivery 侧那扇不是，而 §5.2 抄的正是后者。按项目规则，把一条用户已经表过态的事实补记进 Spec 不需要再请裁决；实现偏离裁决时改的是实现。**代价具体**：优雅关闭期间会为一次根本不会发生的 replay 先花掉一次预算，污染完成行与计数器，而那正是 `base.py:75` 的注释在防的东西。来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-02。

### 5.1 三个必须闭合的状态转换

| 情形 | 裁定 |
|---|---|
| 上游**原生 failure 事件**（`response.failed` / `response.cancelled` / `error`）在首个原生事件提交前到达 | 是否可 replay **完全复用既有 retry taxonomy**，不为本腿另造闭集。taxonomy 判为不可重试时，该 failure 事件**逐字**交付并结束 |
| **clean EOF 且无终局** 在首个原生事件提交前 | 按既有 taxonomy 视作可重试的截断。用尽预算后仍无终局时，写 proxy error（§8），**不得**合成成功 terminal |
| **重开 attempt 没能给出新流** | 按 §5.2 的三类结果分别处置。**draining 根本到不了这里**——它是 §5 的 replay 资格判定，发生在重开之前；客户端看见 `AttemptFailed` 时才是 replacement 的失败，不是旧 attempt 的。§5 已规定 replay 时丢弃旧 attempt 的 terminal／ids／usage，所以回头重放旧 failure 会交付一份已被本代理判定作废的记录。若 replacement 的失败本身不可成帧，则写 proxy error |

### 5.2 native failure 进入 taxonomy 的 adapter

「复用既有 taxonomy」**不能代替一个可执行的输入**，而 v3 就停在了那里。既有入口是 `replay_reason(error: Exception)`，最终落到 `reason_for(error, status_code=...)`，它只认 exception 与 HTTP status；原生 failure 是一个 `StreamFailure`，两者都不是。所以本规格必须给出归一化，否则「taxonomy 判为可重试」没有可求值的东西。

**归一化结果只能是既有三个 `RetryReason` 之一或 `None`，不新增枚举值。**

| 输入 | 归一化 | 理由 |
|---|---|---|
| `response.cancelled` | `None`（不重试） | 取消是一个**决定**而非故障；再试一次的输入完全相同 |
| `code == "server_error"` | `SERVER_ERROR` | 与用户亲笔 taxonomy 里的 5xx 同类 |
| `code == "rate_limit_exceeded"` | 进**既有 rate-limit 处置**，由它给出 reason 与预算 | 与 429 同类。**不得**当作普通即时重试——限流有它自己的退避通道 |
| `code == "vector_store_timeout"` | `SERVER_ERROR` | 超时就是瞬时失败，与它同处一个 Literal 集不改变这一点 |
| 其余 `code`，含未知 | `None` | **除上表明列的可重试 code 外一律保守不重试。**其中 `invalid_prompt`、`data_residency_mismatch`、`bio_policy` 与各类 image 格式／尺寸／编码／策略错误，由名称即可判定为永久；**`failed_to_download_image` 是否瞬时未核**（下载失败既可能是 404，也可能是一次瞬时网络故障，名字本身不区分），按保守规则同样落 `None`，取得证据后可单独放宽；未知 code 保守不重试 |

> **v4 写的「没有该 code 集的语义表」是错的**，我没有核就写了。`openai==3.3.1` 的 `ResponseError.code` 是一个 20 成员的 `Literal`，头两个正是 `server_error` 与 `rate_limit_exceeded`，语义一目了然。「全部五份 cassette 里零出现」只说明当前样本没命中过 failure event，抹不掉协议类型自带的分辨力。
>
> **v4 判断「replay 窗口本就很窄，所以代价小」也不成立。** 那只对迅速完成首个安全前缀的 `block` 成立。`full` 在上游终局前根本不 commit，未触发的 `until-tool-use` 可以持有整轮，`block` 遇到长 reasoning 或较早的未闭合 item 同样长时间不 commit。所以 `response.failed` 到达时，`full` 下的透明 replay 窗口覆盖的是**整次 attempt**——损失最大的恰恰是它。

**重开一次 attempt 的结果有三类，必须分开**，v4 把它们压成了「一个 exception」，而那不成立：replacement 自己失败与本代理拒绝重开的 **origin 不同**，压成一个 exception 会把前者的上游归因套到后者身上。

> v6／v7 用的论据是「draining 时根本没有调用过 `handle`」，而 v7 已把 draining 移出这张表（见下），论据于是落在一个本表声明不管的例子上。三分法本身不依赖它。

| 结果 | 含义 | 处置 |
|---|---|---|
| `OpenedAttempt` | 新 attempt 已建立 | 继续 |
| `AttemptFailed` | replacement **确实开了**并失败，携带它自己的 error | 该 error 走既有 `replay_reason`；最终不可重试时客户端看见 **replacement 的**失败。**origin 为 upstream**——replacement 是一次真实的上游往返，即使失败发生在 transport 层。现有 `FailureOrigin` 只有 `UPSTREAM_EVENT` 与 `PROXY_REFUSAL` 两个值，哪一个承载它属实现问题，归 [`plan.md`](plan.md) |
| `ReopenRefused` | 本代理**拒绝重开**（本地前置拒绝），origin 是 proxy | **不得**进上游 retry taxonomy，**不得**归因给一个不存在的 replacement；按 §8 写客户端方言的 SSE error |

**draining 不进这张表。**它是 §5 的 replay **资格**判定，发生在重开之前；本表只承载「已判定为可 replay、而重开仍未给出新流」的情形。

`ReopenRefused` 保留为**分类槽位**，但要如实说明它今天是空的：移走 draining 之后，本规格没有点名其余实例，主仓 `_reopen` 也只有 draining 这一条本地前置拒绝（它另一条 `return None` 发生在 `handle` 之后，按定义属 `AttemptFailed`）。保留它是为了**将来新增的本地拒绝有处可去**，不是因为已知还有别的——**不要因为把 draining 提前就把整个 `ReopenRefused` 删掉**，那会让下一种本地拒绝被挤进 `AttemptFailed`、继承一个不属于它的上游归因。

这是**可观察事实的分类**，不是 Python 抛不抛异常的形态；具体用什么类型承载留给 [`plan.md`](plan.md)。

**这四条都是本规格的推导**（§2.3），不是用户裁决。

## 6. 各事件与各字段的处置（`openai-responses` 词汇）

> 本节与 §7.1 是**方言专有**的两节，其余各节与方言无关（§2.5）。`anthropic-messages` 的对应词汇见 §2.5 的表，它的逐字段处置在本腿落地时另立小节，不复制本节。

### 6.1 item 专有事件

**必须**原样重放，包括但不限于 `response.custom_tool_call_input.delta` / `.done`、`response.function_call_arguments.*`、`response.output_text.*`、`response.reasoning_summary_text.*`、`response.web_search_call.*`、`response.content_part.*`、`response.output_text.annotation.added`，以及**任何未来新增的**。**不得**因「本代理不消费该事件」而丢弃。issue #2 的根因正是 `custom_tool_call_input.delta` 无人消费。

### 6.2 id：逐事件原样，包括不一致

每个事件携带的 id（item id、`response.id`、`item_id` 等）**必须**原样重放。**不得**重新 mint。

现有 framer 自铸 id 的依据是实测「上游 id 在事件之间不同」（12/12、16/16、125/125）。**那个观测只证明 id 不能作为内部 draft 关联键**——内部改用 `output_index` 与 attempt-local 序号即可（§4 的队列本就按位置组织）。它不证明发给客户端的 id 应当被改写。

**上游 id 不一致是上游 wire 的事实，在 native 合同下属于应当保留的事实，不是代理该默默修复的缺陷。** 复核：`openai==3.3.1` 的 accumulator 按 `output_index` 累积、不校验 id 相等，所以「SDK 需要稳定 id」在该版本上被排除。

**但已知至少有一类客户端会因 native id 而失败，用户自己写下了它的名字。** `docs/.human-controlled/config.example.yaml` 的 `hook_fix_responses_sse` 段逐字写着：「修复上游流在 `output_item.added` / `output_item.done` 间不一致的 item ID。**`@ai-sdk/openai` 校验 ID 连续性需要。**」v8 之前这里写的是「其他客户端未穷尽，不外推为全生态安全」——那句话本身不假，但它读起来像「我们不知道有没有」，而实际状态是「已知有一个，名字在用户的文件里」。两者给读者的行动指引完全不同。

> **这不是「用户已裁决要修 id」**：那段配置是注释掉的候选项，与它上面的 `hook_fix_responses_request` 同形，是一个 opt-in 开关的形状，不是已启用的裁决。

**回归是具体的。** 今天这条腿由 `ResponsesFramer` 成帧，`_item_id()` 用 `f"{prefix}_{response_id}_{output_index}"` 生成，同一个 item 的 `added` 与 `done` 走同一个 `output_index`，**所以客户端今天拿到的 id 是连续的**。本腿改 native 之后拿到的是上游那份实测全不相同的 id。也就是说：一个用 `@ai-sdk/openai` 的 Responses 客户端今天在这条腿上能跑，透传落地后会被它自己的连续性校验拒掉。**这项回归此前没有任何文档登记。**

若要提供 `fix_stream_ids` 之类的兼容变换，**必须**另立显式、可选的 reshape 合同，**不得**叫它 native 或逐字——方向与用户那段注释一致，因为那本来就是个 opt-in 开关。**但它在本腿不是纯粹的将来事项**：本腿落地即撤掉今天 framer 提供的稳定 id。是否在启用透传的同一刀里提供这个 opt-in，是一个产品分叉，已登记进 [`deferred.md`](deferred.md) D-3。

> 未核的一项：`@ai-sdk/openai` 具体在哪个版本、以何种方式校验连续性，本项目没有它的源码，采纳的是用户的陈述。

**改写 id 的后果不止于客户端兼容，本节此前把它写窄了。** 上面整节把「不得重新 mint」的代价与收益都摆在客户端一侧——谁校验连续性、谁会被拒——读起来像一次可以两边权衡的取舍。**GitHub issue #4 证伪了这个框架：对一个封了 `encrypted_content` 的 reasoning item，改写 id 是硬性正确性缺陷，没有取舍可言。**

实测（2026-09-01，把 issue #4 报的那份 901,008 字节 body 原样重放）：

```
400 invalid_request_body
The encrypted content for item rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0 could not be verified.
Reason: Encrypted content item_id did not match the target item id.
```

被点名的那个 id 是 `rs_` ＋ 一个 `uuid4` ＋ `_0`，即 `_item_id()` 的拼法；这条链路（`request.py` 的 `uuid4` → `inference.py` → `delivery_policy.py` → `openai_responses.py`）足以证明**本代理确实这么拼**，但不足以证明「没有哪个上游会这么拼」——后者本规格早先的措辞是一句没有证据的全称，已删。**密文与它被签发时的 item id 绑定，上游在回传时校验这个绑定**；翻译腿把上游的密文挂到自铸的 id 上，这一对从写出来的那一刻就自相矛盾。逐字段处置见 §6.4。

> **归因的限定**：用户 16:32 收到的原话是 `The resource you requested was not found.`，而 16:50 起同一份 body 重放稳定得到上面那句。两句都是 400 ＋ `invalid_request_body`，且后者点名了本代理自铸的 id。**「这两句出自同一个校验分支」未闭合**——上游可能在这几小时内改了文案，也可能存在两个分支。所以「id 缺陷就是 16:32 那次观测的根因」是**高置信推断，不是直接观测**。它对处置没有影响（缺陷本身是直接观测到的，且修法独立成立），但不得被转述成观测。

**这个缺陷的形状值得单独记：它是延迟的。** 出问题的那一轮响应是干净的 200，item 形状合法，**客户端在回放之前看不出异常**；矛盾要等到一个保存 rollout 历史的客户端（Codex 就是）把这个 item 发回来才暴露。所以「第一轮跑通了」对这条不变量零鉴别力，issue #4 报的也正是一次「本来在用的会话，某一轮起持续 400」。

> 「延迟」是**对客户端而言**，不是原理上不可检测——一个把上游事件与自己交付的事件逐一比对的代理，第一轮就能看见这次改标。今天没有任何东西在做这件比对。本规格早先写的是「本轮任何观测都看不出异常」，那是一句过头的全称。

### 6.3 control 与 terminal 事件

`response.created` / `response.in_progress` / `response.completed` / `response.incomplete` / `response.failed` / `response.cancelled`：**必须**原样重放上游的，**整个 `response` 对象逐字**——含 `status`、`incomplete_details`、`usage`、`tool_usage`、`metadata` 及任何本代理不认识的根级字段。**不得**由本代理合成，**不得**由 `Terminal.stop_reason` 反推（那是面向 Anthropic 的派生摘要，本腿只作可观测用途，见 §10）。

提交时点见 §5。

### 6.4 reasoning

`encrypted_content` **必须**原样交还，**不得**经本项目的 reasoning carrier 编解码。

**下一轮回传不会进入 carrier decoder**，这一条已有确证而非待定：`driver.py` 只在 `route.translation_required` 为真时调用 request translator，而 carrier decoder 只存在于该 translator 内；本规格的定义域恰为 false。**需要一条回归测试钉住这个门。**

**`id` 与 `encrypted_content` 是一对，必须整对原样交还。** `encrypted_content` 与上游签发它时的 item id 绑定，上游在回传时校验该绑定并在不符时以 400 `invalid_request_body` 拒绝整个请求（§6.2 有实测原文）。因此本节的「原样交还」不能只读成「密文别动」——**把密文原样带走而给 item 换一个 id，与篡改密文等效**。

**这条不变量有两半，两半各有一条回归测试**（均在 `tests/int/test_pipeline_app.py`）：

| 半 | 测试 | 它挡住什么 |
|---|---|---|
| 响应（上游 → 客户端） | `test_a_sealed_reasoning_item_keeps_the_id_its_seal_was_cut_against` | 铸新 id；**以及把上游漂移的两个 id 合并成一个** |
| 请求（客户端 → 上游） | `test_a_sealed_reasoning_item_reaches_upstream_the_way_the_client_wrote_it` | 入站 sealed item 的 id 或密文被删改，或被送进 carrier decoder |

**请求那一半此前只有论证没有测试。** 上一段那句「回传不会进入 carrier decoder」是从 `translation_required` 的门推出来的，而**一个论证不是一条回归测试**——本节先前把这件事记为「需要一条回归测试钉住这个门」，现在它存在了。断言落在本代理**发出的字节**上，不在回复上：回复由发出去的东西生成，说不出发出去的是什么。

**响应那一半的夹具必须带 id 漂移，否则它辨别不了第二种破法。** 上游对同一个 item 在 `added` 与 `done` 上拼不同的 id（`tests/int/cassettes/history_responses_stream.json` 的 `output_index` 0：`id_002` → `id_003`，两处都带密文）。一个「稳定化」这两个 id 的兼容层会把 `done` 的密文挂到 `added` 的 id 上——**同一种绑定失配，另一条路径**。旁边那些测试用的 stand-in 两处拼同一个 id，对这种回归恒等，只能看见第一种。

**变异校验（2026-09-01，三次，各自命中对应的那一半）**：(A) 令 `carries_upstream_natively` 返回 `False` → 交付 id 变成 `rs_<uuid4>_0`（与 issue #4 报的同形），响应侧测试红；(B) 在 `PassthroughFramer.block` 注入「把批次内 item id 统一为首见的那个」→ `done` 变成 `(id_002, seal-closed)`，响应侧测试红，而**旧夹具下这个变异是恒等映射、会静默变绿**；(C) 在 `direct_driver/base.py` 注入 §11 O-2 提的那条剥离（无条件删掉入站 sealed item 的 `id`）→ 请求侧测试红、响应侧不受影响。

### 6.5 请求侧：剥离本代理自己铸出来的 reasoning item id（`hook_fix_responses_request.repair_minted_reasoning_ids`）

**出处是用户裁决，不是本规格的推导。** 2026-09-01，用户读过 §11 O-2 的两侧材料后原话裁定：**「加，按窄形态 ＋ 显式 opt-in」**。本节把那条裁决写成规范；形态的两个限定词——「窄」与「显式 opt-in」——都来自用户，不得放宽。

**它修的是什么。** §6.2 记着一段已经结束的历史：翻译腿曾把上游的 `encrypted_content` 挂到 `_item_id()` 自铸的 id 上。`1fb37cd` 之后本代理不再产生这种 item，**但已经写进客户端 rollout 历史的那些不会消失**——客户端每轮把它们原样回发，上游每轮校验绑定失败，会话就此永久 400。本节是给这类历史的一次性修补。

**这是一次兼容整形，不是 native 的一部分**（§2.7）。因此：**默认关闭**，由一个具名配置项显式打开；打开与否对用户可见；本节的任何行为都不得被描述成「原样转发」。

**落地位置**（记在这里是因为 §6.5.3 的「请求离开本代理之前」有好几个点都满足）：配置键 `hook_fix_responses_request.repair_minted_reasoning_ids`（`ProxyConfig`），实现是 `attempt.prepare` 上的 subscriber `builtin:repair-minted-reasoning-ids`（`app/pipeline/subscribers/minted_reasoning_ids.py`）。**这是一处转写**：键名与 subscriber id 同时出现在本规格与代码里，改名要一起改。

#### 6.5.1 判据（三个条件全部满足才动）

一个**入站** item 被修补，当且仅当：

1. `type == "reasoning"`；**且**
2. 它带一个非空的 `encrypted_content`；**且**
3. 它的 `id` 逐字等于 `_item_id()` **在已知生产路径上能产出的文本**，即 `rs_` ＋ 一个 `uuid4()` 的字符串形式 ＋ `_` ＋ 一个非负 `int` 的 `str()`。

   展开成可实施的判据：小写十六进制、`8-4-4-4-12` 分组、**第三组首位固定 `4`**（version）、**第四组首位属于 `89ab`**（RFC variant）、序号为 `0` 或不以 `0` 开头的十进制数。

   > **这五项限定不是装饰，少写一项判据就宽于本代理能铸出的集合。** 独立评审构造并实跑证实：早先只写「`8-4-4-12` 位十六进制」的版本会删掉 `rs_00000000-0000-1000-8000-000000000000_0`（version 1，`uuid4()` 不可能产出）与 `rs_<uuid>_00`（`str(0)` 不是 `00`）。这两个 id 只可能出自别的作者，删它们正是「窄形态」裁决要避免的那种误伤。顺带更正：本节此前把 UUID 分组写成 `8-4-4-12`，漏了一组。

**为什么钉得这么窄，而不是「`rs_` ＋任意＋数字」。** 宽形态在本上游够用（Copilot 签发的 item id 是无前缀 base64），但换一个上游就不成立：OpenAI 本家的 reasoning item id **正是** `rs_` 开头，宽形态会去改一个完全合法的 id，把一个能用的会话弄坏。窄形态钉的是 `_item_id()` **真正会产出**的那个形状——`f"rs_{response_id}_{output_index}"`，其中 `response_id` 是 `RequestContext.id` 的 `uuid4()`——所以它只认本代理自己的笔迹。**用户裁决里的「窄形态」指的就是这一条。**

> 判据里没有「provider 是不是 Copilot」这一项。窄形态已经把误伤面收到本代理自己的拼法上，再加一层 provider 门是把同一件事判两遍；真要限定作用域，用配置项本身（下节），那也是用户可见的那一层。

**这条判据对着真实的坏 body 全量核过**（2026-09-01，issue #4 那份 901,008 字节 body 的 359 个 input item）：

| | 条数 |
|---|---|
| reasoning ＋ 带密文 ＋ **命中**窄形态 | **15**（正是导致 400 的那些） |
| reasoning ＋ 带密文 ＋ **未命中**（会被漏修） | **0** |
| reasoning ＋ 不带密文（判据正确地不动它） | 51 |

**那 51 个里有另一种自铸形状，`rs_resp_<上游响应id>_<序号>`，它不是 uuid4。** 本代理当前不可能产出它——`inference.py` 把 `context.id` 传给 framer，而那是 `uuid4()`——所以它多半来自用户此前在同一端口上跑的 `copilot-api-js`，即**同形缺陷的另一份实现**。它们全部只带明文 `content` 而不带密文，因此上游没有绑定可校验，实测这类 item 原样回传得 200：**判据不动它是对的，不是漏修。**

> **残余限制，如实记下**：如果某天出现一个**既带密文、id 又是 `rs_resp_…_N` 形状**的 item，本节的判据会漏掉它，那条会话仍然修不好。上面这份样本里是 0 条，但一份样本不能证明它不存在。**不据此放宽判据**——用户裁的是窄形态，而放宽的代价（误伤 OpenAI 本家合法的 `rs_` id）落在正常会话上，比漏修一类历史更贵。真遇到了，正确的动作是拿着那份样本回来重裁，而不是现在先把口子开着。

#### 6.5.2 处置：删 `id`，不动别的

命中的 item **删掉 `id` 字段**，其余字段（含 `encrypted_content` 本身）**逐字保留**。

**为什么是删 id 而不是改 id。** 本代理**没有保留**上游的原始 item id，也无法从它还持有的任何字段重建它——reasoning carrier 只存 `encrypted_content`——所以「改成对的」这条路不存在。

> 此处此前写的是「正确的 id 只存在于密文里」。那是一句**位置声称**，证据支撑不到：绑定也可能由 AAD 或上游侧状态实现，密文里未必真的躺着一个可取回的 id。修法不受影响——它由「我们没保留」独立支撑——但地点不能瞎写。

实测（2026-09-01，真实上游）：**三个**不同的不匹配 id 各试一次，全部 400，且报文逐字说明是 item_id 不符；**去掉 `id` 后 200**——见 [`reports/260901-issue4-sealed-reasoning-id.md`](reports/260901-issue4-sealed-reasoning-id.md) §3.3。「任意不匹配的 id 都会失败」是由该报文语义得出的强推断，**不是穷举观测**。

**为什么不是删 `encrypted_content`。** 那会把这一轮的推理上下文丢掉，是有损的；删 id 不丢内容。

**不命中的 item 一律不动**，包括带密文但 id 不匹配窄形态的（那不是本代理的笔迹，动它就是在猜）。

#### 6.5.3 定义域与作用点

只在 `translation_required is False` 且 `inbound_format` 为 `openai-responses` 的腿上运行，作用于**发往上游的请求体**的 `input` 数组顶层元素。不递归进嵌套结构：`_item_id()` 只铸顶层 item id，别处出现的同形字符串不是它铸的。

**必须发生在请求离开本代理之前，且必须能在「本代理实际发出的字节」上被观测到**——这是 §6.4 请求半程那条回归测试的断言面。

#### 6.5.4 可观测

修补过的请求**必须**留下痕迹：至少记下本次修补了几个 item。一次静默的请求体改写，正是本主题反复付过代价的那种缺陷——`1fb37cd` 之前那次改写就没有任何记录，代价是 issue #4 用了一整轮调查才被归因。

#### 6.5.5 这一节的保质期

**它修的是一个不再增长的集合。** 本代理不再产生这种 item；随着旧会话淘汰，命中数会归零。**但「不再增长」不等于「自行清空」**（§11 O-2 存档段记着这条被评审纠正过的论据）：一个保存完整 rollout、失败后既不推进也不裁剪历史的客户端会永远重发同一个坏 item。

因此本节**不设自动过期**，但它是一条到点该复查的兼容层。

**复查条件必须是可判定的，而本节的初稿不是。** 初稿写的是「当 §6.5.4 的计数在生产上长期为零时应当被提出退役」，独立评审指出它没有 oracle：实现只在命中时写日志，所以「没看到那条 INFO」同时兼容四种情形——开着且有流量但零命中、根本没开、没有流量、INFO 没被采集——而「长期」既无时间窗也无请求量门槛，更没有说谁在什么事件上去看。**照它字面执行，永远不会有人得出「可以退役了」。**

**改用一个不需要新机制的判据**：本开关是 per-operator 显式打开的，所以退役的可判定条件是——**打开过它的操作者把它关掉，其受影响的会话不再出现 §6.2 那句绑定失败的 400**。触发时点是操作者自己下次修改配置时；证据是关掉之后那几条会话还能不能跑。这不需要累计计数，也不需要区分日志缺席的四种情形。

若将来确实想按命中数退役，那要先补一个能把上述四种缺席分开的计数来源（至少：启用状态、观察窗口内的请求量、累计命中数），本节在那之前不主张按计数判断。

### 6.6 响应侧：把上游漂移的 id 稳定化（`hook_fix_responses_sse.fix_stream_ids`）

**状态：草案，等用户裁默认值。** 方向不需要再裁——§6.2 已裁定这类变换必须另立显式、可选的 reshape 合同、不得叫它 native，[`deferred.md`](deferred.md) D-3 也说「方向没有分歧，分歧只在时点」。**时点已被生产逼出来了**（下一段），剩下要用户定的只有一件：默认开还是默认关。

> ### ⚠️ 本节的触发理由已被证伪，条款本身仍然成立——两件事分开读
>
> **写这节时的因果假设是：Codex 的「结果重复输出」由 id 漂移引起。那个假设错了**，2026-09-02 由针对用户实际在跑的 Codex `0.144.1` 二进制的定向探针推翻（8/8 正探针命中、2/2 负控制落空，见 [`reports/260902-codex-item-grouping-key.md`](reports/260902-codex-item-grouping-key.md)）：
>
> - Codex **既不按 `item_id` 也不按 `output_index` 归组**，它用一个**单槽 `active_item`**——`output_item.added` 置位、`.done` 取走，中间的 delta 全挂那个槽；
> - 它的 `ResponsesStreamEvent` 结构体**根本不解析 `output_index`**，`output_text.delta` 分支只取 `delta`；
> - `response.completed` 只解析 `{id, usage, end_turn}`，**不读 `output`**。
>
> 所以 §6.6.4（统一 `response.id`）与本节全部 item id 处置，**对 Codex 的行为一概无影响**——重复输出另有成因，仍未查明（[`deferred.md`](deferred.md) **D-9**）。
>
> **本节为什么还留着**：它服务的是 D-3 登记的那个客户端——用户在 `config.example.yaml` 里亲笔点名的 `@ai-sdk/openai`，症状是校验失败抛异常而非重复渲染。那条需求独立成立，与 Codex 无关。**§6.6.6 的默认值随之改判为「关」**：默认开的唯一论据是「Codex 需要它」，论据没了，默认值不能活得比它久。

#### 6.6.1 触发它的观测

**2026-09-02，用户报告：Codex 在 `/responses` 上「结果会重复输出」。** 这是 `1fb37cd` 接线之后出现的，接线之前同一个客户端在同一条腿上正常。

同日实测，同一个 provider、同一个模型，抓完整流逐字段比对：

| | 旧构建（翻译腿，8/29） | 现在（透传，`a436c96`） |
|---|---|---|
| 事件类型序列 | created／in_progress／output_item.added／content_part.added／output_text.delta ×N／output_text.done／content_part.done／output_item.done／completed | **完全相同** |
| `response.id`（created／in_progress／completed 三处） | 三处同一个 | **三处互不相同** |
| `output_item.added` 与 `.done` 的 item id | 同一个 | **不同** |
| 每条 `output_text.delta` 的 `item_id` | 全部相同 | **每条都不同**（5 条 5 个值） |
| `response.completed` 的 `output[0].id` | 同上 | 又是另一个值 |
| `response.completed` 带完整 `output` 数组 | 是 | 是（**不是差异**） |

**事件类型与 `output` 的存在都没变，这次逐字段比对里唯一变的是 id。**

> **当时我据此写下一条单变量因果论证——「Codex 在 id 稳定时能用、在 id 漂移时重复，所以恢复稳定即恢复它工作过的条件」——那条论证不成立，值得记下它错在哪。** 它的形式没问题；**错在把「我这次比对到的唯一差异」当成了「唯一差异」**。那次比对是**两条短流的字段级对照**（单 item、无工具调用、无重试、无保活），而用户的真实流量不是。上游源码随后表明 Codex 连那些 id 都不读，于是「唯一变的是 id」这个前提只能说明**我的样本里**只有 id 变了。
>
> 教训写在这里而不是报告里，因为它会再犯：**一次单变量论证的强度，等于那次比对的覆盖面，而不等于比对结果的整齐程度。**

> **旧构建并不是「对」，它只是恰好盖住了这件事。** `_item_id()` 由 `output_index` 生成，同一 item 的所有事件因此共享一个 id——那是自铸 id 的副产品，不是有意的兼容层。issue #4 正是同一个自铸行为的另一面（§6.2）。所以本节不是「把旧行为改回来」，是**第一次把这件事写成显式合同**。

#### 6.6.2 定义域与作用点

只在 `translation_required is False` 且两端均为 `openai-responses` 的腿上运行，作用于**发往客户端的事件**。与 §6.5 是两个方向、两条独立开关，互不蕴含。

#### 6.6.3 稳定到哪个 id：**必须是闭合事件那个，不能是首见那个**

**这一条是本节唯一的技术难点，写错就会把 issue #4 重新造出来。**

实测（2026-09-02，`reasoning` item，`output_index` 0）：

| 事件 | item id | `encrypted_content` |
|---|---|---|
| `response.output_item.added` | `FGX3hL/eUVRCIoOZ…` | **4,888 字节** |
| `response.output_item.done` | `IN1onZX23hrx5eZ+…` | **5,032 字节** |

**两个 id 不同，两段密文也不同，各自绑各自的那个 id。** §6.2 记着上游会校验这个绑定并在不符时 400。

所以「把一个 item 的所有事件统一成**首见**的 id」会把 `done` 的密文挂到 `added` 的 id 上——**逐字就是 issue #4 那个错配**，而且这次是我们自己造的。本仓已有的变异校验证明这条路径可被测试捕获（`tests/int/test_pipeline_app.py` 的响应侧回归测试，变异 B）。

**因此裁定：每个 `output_index` 的全部事件，统一到该 item 的闭合事件（`response.output_item.done`）所携带的那个 id。** 闭合事件自身完全不动，于是客户端最终留存的那一对（id ＋ 密文）保持原配。

> **这个做法只有靠块级交付才可能。** 一条逐事件前送的流在发出 `added` 时还不知道 `done` 会带什么 id；而本项目按块缓冲，整批事件是一起释放的（§4），闭合事件在批次内、在任何字节发出之前就已经在手。**这是块级交付第一次买到一个纯流式实现做不到的东西**，值得单独记一笔。

**被改写 id 的非闭合事件，若自身携带 `encrypted_content`，必须同时删掉那段密文。** 理由与上一段同构：改了 id 就破坏了那一对，留着一段对不上号的密文，等于把一颗哑弹交给客户端——万一它持久化的是 `added` 而不是 `done`，issue #4 就以另一条路径复现。完整密文本来就在 `done` 上，删掉非闭合事件的那份不丢任何东西。

#### 6.6.4 `response.id`

envelope 事件（`created`／`in_progress`／`completed`／`incomplete`／`failed`／`cancelled`）的 `response.id` 同样漂移，同样统一。**这里没有绑定问题**，所以取哪个都不破坏语义；取 `response.created` 的那个，因为它是客户端最先看到、也是任何关联／日志会记下的那个。

`response.completed` 的 `output[]` 里各 item 的 `id` 一并按 §6.3.3 的结果改写，使之与该 item 的闭合事件一致。

#### 6.6.5 不得越界

**只改 id 字段，别的一律不动。** 不重排事件、不合并、不补齐、不改 `sequence_number`、不动 `output_index`、不动任何 payload 内容——`sequence_number` 是上游自己的计数，改它就等于声称这条流是我们编的。

**必须留下痕迹**：启用时至少记录本次响应改写了几个事件、以及被统一掉的 id 有几个不同值。理由与 §6.5.4 相同——一次静默的流改写正是本主题反复付过代价的形状。

#### 6.6.6 待用户裁决：默认开还是默认关

**这是本节唯一悬空的事，其余都已由 §6.2 与本节裁定。**

- **默认关**（与 §6.5 一致，也与 §2.7「兼容整形必须显式」的字面最贴）：代价是用户的 Codex 在他自己打开之前一直是坏的，而这条腿上**目前已知的两类客户端（Codex、`@ai-sdk/openai`）都需要它**。
- **默认开**：代价是「native 透传」这条对外承诺默认就被一层整形改写了，与 §2.1 的方向相悖；但可辩护之处在于——**它恢复的是这条腿在 `1fb37cd` 之前一直提供、且从未有人依赖过其反面的行为**，而 §2.7 那句「接线不得改变任何一条腿今天已生效的整形默认值」按其**意图**读，本来就指向「不要在接线中悄悄拿掉既有整形」。

> **v11 写 §2.7 时把这条判错了。** 原文是「Responses 腿今天没有 `fix_stream_ids`，接线后也不会凭空多一个」——它只看了配置项存不存在，没看**行为**存不存在。稳定 id 那时是**默认生效的**，只是由自铸 id 顺带提供、没有名字。按 §2.7 自己那句「不得改变已生效的整形默认值」，接线其实**已经违反了它**，而当时无人察觉，因为那层整形没有名字可查。**这是「负空间读不出来」的一个实例**：一份只列出配置项的清单，看不见那些没有配置项的既有行为。

**已定为「默认关」，2026-09-02。** 上面「默认开」那一侧的全部分量都压在「这条腿上已知的客户端都需要它」这句话上，而那句话里的 Codex 被证伪了（见本节开头的警示框），剩下的只有用户点名的 `@ai-sdk/openai` ——那是一个**特定客户端的兼容需求**，正是 §2.7 说必须显式索取的东西。**一个默认值不能活得比支撑它的论据更久。**

> 「稳定 id 曾是无名的既有行为」这条负空间观察**本身没有被证伪**，仍然记在这里：`1fb37cd` 的接线确实悄悄拿掉了一层一直在生效的整形，而 §2.7 那句「接线不得改变已生效的整形默认值」当时看不见它，因为它没有名字。**那说明 §2.7 的检查方式有缺口**（只查配置项、查不到无名行为），但它不足以把这层整形推回默认开——**「它以前在」不等于「它应该在」**，尤其在唯一已知的受益者已经被证明不需要它之后。

## 7. Buffering policy

| policy | 本腿含义 |
|---|---|
| `block` | 每个安全前缀（§4）一就绪即发出，**首批仍受 §5 的 control-event 提交时点约束**。默认。 |
| `full` | 全部可提交事件在**任意最终 ending**（§7.2）时一次发出，不限于上游终局。 |
| `until-tool-use` | 见下。 |

### 7.1 `until-tool-use` 的释放判据（`openai-responses` 词汇）

> **方言专有**（§2.5）。判据本身——「该 item 是否要求客户端提交 tool output 或 approval，模型回合才能继续」——与方言无关；下面枚举的类型与字段只属于 Responses。`anthropic-messages` 的同一判据是 block `type == "tool_use"`，它没有 `execution`／`environment` 这类条件字段，所以那份词汇是一行而不是一节。

**事实判据是 `client_action_requirement(item)`：该 output item 是否要求客户端提交与之对应的 tool output 或 approval，模型回合才能继续。它返回 `required`、`not_required`、`unknown` 三态。** `requires_client_action` 是 buffering policy 使用的布尔投影：仅 `not_required` 投影为 `false`，`required` 与 `unknown` 都投影为 `true`，因为在事实不明时先释放不会限制客户端能力，而扣押可能让模型永久等不到客户端。

**不是** Anthropic `BlockKind.TOOL_USE`（本腿没有 Anthropic kind），**也不是**「类型名以 `_call` 结尾」。

当前 `required`：`function_call`、`custom_tool_call`、`computer_call`、`local_shell_call`、`apply_patch_call`、`item.environment` 明确为 local 的 `shell_call`、`item.execution == "client"` 的 `tool_search_call`、等待客户端回答的 `mcp_approval_request`。

当前 `not_required`（上游自行执行并在同一响应内给出结果）：`web_search_call`、`file_search_call`、`code_interpreter_call`、`image_generation_call`、`item.execution == "server"` 的 `tool_search_call`、明确指向 server container 的 `shell_call` 与 MCP call。

当前 `unknown`：代理不认识的原生 type、type 缺席，以及 `tool_search_call` 与 `shell_call` 这类条件类型缺少或带有无法判定的 discriminator。unknown fact 保留原生 type 与可选 name；原生 type 也缺席时才把其显示名记为 `unknown`。不得把「policy 为避免扣押而选择释放」改写成「已确认模型在等客户端」。

**分类读 item 自身携带的执行语义**，不需要回查原始请求。核对 SDK 类型（2026-08-30）：`ResponseToolSearchCall` 自带 `execution: Literal["server", "client"]`，`ResponseFunctionShellToolCall` 自带 `environment`。同一个 `tool_search_call` 因此会给出相反答案——这正是「按 type 判」不成立、而本规格必须定案的原因。

> v2 曾写「判定需要原始请求的 tool declaration」，那是把上一轮评审的「同一 type 会有相反答案」误读成「要回请求里查」。响应 item 自己就带着答案；回查原始请求既无依据，还可能读到 attempt 之间被改写过的版本。

触发**只发生在**该 item 的布尔投影为 `true`、item 已完成且已到达安全 commit frontier 时；触发后永久转为逐前缀释放，保持今天 `until-tool-use` 的一次性状态变化语义。三态分类同时进入 §10 的可观测旁路，不能从触发结果反推回来。

### 7.2 policy × ending

`block` 之外的两种 policy 会持有**已完成**的 item group，而 proxy ending（cap、deadline、预算耗尽的 EOF、transport tear）可能先于上游 terminal 到达。v3 只裁了未闭合 suffix 的去向，没裁这些**完整**group 的去向，于是同一段文字同时要求「保留它们」「等 terminal 才发」「立刻写 error」——三者互斥。

**入口条件先于顺序，两者不能混为一谈。** 「ending」在 v4 里同时指了两件事——*一个可能被 replay 掉的 attempt 结束*，和*客户端最终看到的结束*。只有后者才触发收口。

**§7.2 只在 §5 的 replay 判定完成之后运行**：

| §5 判出 | §7.2 |
|---|---|
| 首个原生事件**尚未**提交，replay 有预算、该失败可重试，**且重开已经成功**（§5.2 的 `OpenedAttempt`） | **不运行。** 旧 attempt 的 control、queue、ids、usage 全部丢弃且**一个字节都不提交**——包括已完成的 group |
| 首个原生事件尚未提交，但 replay 不可用／被拒／预算耗尽 | 运行；末步的 carrier 由**下表的 final source** 决定，不由 commit 状态决定 |
| 首个原生事件**已**提交 | 运行（§5 此时已禁止 whole-attempt replay） |

> **「且重开已经成功」这半句是 v7 补的，缺了它两格在时间上不互斥。** 第一格原本的三项谓词在**尝试重开之前**就全部可求值，而第二格把「被拒」也算进自己——那是**重开之后**才知道的事实。于是优雅关闭期间收到一个可重试的 `response.failed` 时，第一格先命中并销毁全部已完成 group，随后第二格命中并要求提交它们，同一场景两个相反答案，`full` 下差别是「整轮内容」对「一条 error」。这不是纸面推演：`retry.py:140` 在返回 `REPLAY` 时就已花掉预算，`stream.py:467-468` 之后才重开，`inference.py:410-415` 的 draining 检查还在 `_reopen` 内部——判定与「知道被拒」之间隔着一次完整往返。补上这半句，三格重新成为任一时刻都可判定的 partition。采纳上面 §5 的 draining 前移会消掉这里最尖锐的那个实例，但**替代不了**这半句：`AttemptFailed` 与本地前置拒绝的其余形态仍然落在同一个间隔里。来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-01。

**末步发什么，由 final source 决定——这是一根与 commit 状态正交的轴。** v5 把第二格一律写成 proxy error，而那一格至少装着三种来源，其中两种手里有上游自己的终局：

| final source | 末步 |
|---|---|
| 上游 `response.completed`／`response.incomplete` 到达 | **逐字提交它**（§6.3）。这一格里根本没有 replay 的必要 |
| 上游 `response.cancelled`，或不可重试 code 的 `failed`／`error` | **逐字提交它**（§5.1）。它是真实存在的上游终局 |
| 可重试的 `response.failed` 但预算耗尽 | **逐字提交它**。预算耗尽改变的是「能不能再试」，不改变「上游说了什么」 |
| 上游终局**存在**，但它所属的 attempt 已被 replay 判定作废（§5.2 的 `ReopenRefused`／`AttemptFailed`） | 按 §8 写 error，origin 依 §5.2（`ReopenRefused` 为 proxy，`AttemptFailed` 为 upstream）。**不得**回头逐字重放那份已作废的终局——§5 规定 replay 时丢弃旧 attempt 的 terminal／ids／usage，重放它等于交付一份本代理自己判定作废的记录 |
| 没有任何上游终局（tear、EOF、proxy refusal、cap、deadline） | 写 proxy error（§8） |

**裁定：`full` 的「response 结束」指任意**最终**ending，不限于上游 terminal。** 最终 ending 到达时，一律按同一顺序收口：

1. 丢弃未闭合 item 的 suffix（§3）
2. 按**原序**提交 control 与所有已完成的安全 group
3. **无法归属的事件**（§4）：**收口时刻没有任何已打开而未闭合的 item** 时，与上一步一并按原序逐字提交；**存在**未闭合 item 时，与未闭合尾巴一同丢弃
4. 提交上游 terminal／failure（若有），否则提交 proxy error（§8）

> **这一步存在的理由**：这类事件不是某个未闭合 item 的 suffix（它不属于任何已知 item），也不属于任何已完成 group，v8 之前的三步收口把它整个漏在了外面——而骨架的 docstring 已经替本规格裁定为丢弃。**丢弃恰好是与 §2.1 张力最大的那个答案**：用户裁的是「不得以本代理不认识为由拒绝一个协议允许的直连 item」，而静默丢掉一个协议合法、承载模型输出的事件，理由正是「本代理判不出它属于谁」。
>
> **v8 用的是「ending 来源」这根轴，那是错的，v9 换掉。** v8 的论据句写着「上游给出终局……此时这些事件不再有『属于某个还没说完的 item』之外的解释」——字面上「不再有 X 之外的解释」就是「唯一的解释是 X」，恰好说反；而作者真想说的那个推理也不成立，**否掉它的正是本规格 §3**：「terminal 不能证明一个未知 lifecycle 已经完成」。一个收到 `added` 却没收到 `done` 的 item，在上游终局之后**仍然**是未闭合的，所以「它可能属于某个还没说完的 item」这个解释在终局之后依然可用。
>
> **实跑构造出的坏帧**（骨架 assembler ＋ 主仓 `parse_frame`）：一个 `output_item.done` 的 payload 里含裸 U+2028，被 §3.1 第三条描述的截断切坏 → 不再是合法 JSON → 读不出 `output_index` → 落进「无法归属」；**与此同时它本该关闭的那个 item 因此永远开着**。按 v8 的规则，第 1 步丢掉该 item 的 `added` 与 `delta`，第 3 步却把这个 `done` 逐字发出去——客户端拿到一个没有 `added` 与之配对的孤儿 `done`，`data` 还不是合法 JSON。
>
> **根因是 §4 把两类语义不同的事件并进了同一个桶**：一类**本来就不属于任何 item**（四个 audio 事件，既无 `output_index` 也无 `item_id`），另一类**属于某个 item、只是本代理没读出归属**。对前者，终局时交付完全正确；对后者，它按构造就属于某个 item，而那个 item 可能正是未闭合的那个。ending 的来源这根轴**不区分这两类**。
>
> **新谓词直接瞄准那个后果。** 「收口时刻有没有未闭合 item」正是「孤儿帧会不会产生」的判据：没有未闭合 item 时，一个无法归属的事件不可能是某个开着的 item 缺失的那一半，交付它就是交付上游确实发过的字节；有未闭合 item 时，不能排除它就是那一半，而 §3 已裁定这类碎片一律不交付。**拒绝的理由因此从「判不出它属于谁」换成了「不能排除它属于一个我们已知没说完的 item」**——后者 §3 已经用过一次并被接受，不是 §2.1 否掉的那个。
>
> **本规格没有采纳评审建议里的另一半。** [`reports/260831-review-spec-round8.md`](reports/260831-review-spec-round8.md) round8-01 建议的替代谓词后面还跟着「代理侧 ending 一律丢弃，理由不变」。**不采纳**，因为它与同一次收口的第 2 步不一致：代理侧 ending 下第 2 步照样提交全部已完成 group，那么在同样没有未闭合 item 的前提下单独丢掉这些事件就没有理由，只会重新引入一根多余的轴。留一根轴。
>
> **残余情形，登记而不裁**：若某个 item 连它的 `added` 都因为同样的原因无法归属，该 item 对本代理完全不可见，「没有未闭合 item」为真而它的事件仍会被交付。此时交付的是上游确实发过的字节、顺序也没变，本规格接受这个结果——它与「payload 本身就坏」不可区分，而那不是本代理造成的。P3 落地后这条路径的主要来源关闭。
>
> **触发面分四层，权重不同。** (a) U+2028／U+2029／U+0085 截断——**今天在 `main` 上是活的**，P3 落地后关闭；(b) 上游发出非 JSON object 的 payload——机制确定、触发未测；(c) 四个 audio 事件——机制确定、触发未证实，**这一类交付是对的**；(d) 将来新增的、携带 `item_id` 而不携带 `output_index` 的 item 专有事件——机制确定，而**这一类正是本腿存在的理由**（§6.1「以及任何未来新增的」），它不会随 P3 关闭。支撑本条裁定的是 (d) 加「谓词本身要为真」，不是 (a)。
>
> 这是**本规格的推导**（§2.3），且它触到 §2.1 的边。来源：round7-04（提出）、[`reports/260831-review-spec-round8.md`](reports/260831-review-spec-round8.md) round8-01（推翻 v8 的轴并给出替代）。

| 最终 ending | `block` | `until-tool-use`（未触发） | `full` |
|---|---|---|---|
| **partition 第一格命中**（仍可 funded replay，**且重开已经成功**）的 tear／EOF | **不收口**，整次 attempt 无提交丢弃 | 同左 | 同左 |
| 上游 terminal／failure | 已逐前缀提交 | 按上表收口 | 按上表收口 |
| cap／deadline／预算耗尽 EOF／不可重试 tear | 已提交部分保留，写 error | 按上表收口，末步写 error | 按上表收口，末步写 error |
| 客户端取消／下游写失败 | — | **例外：无可写通道，不收口** | **例外：无可写通道，不收口** |

**取「先提交已完成内容再写 error」而不是「全丢」**，因为那些 group 在语义上已经完整——它们是模型已经生成完的工具调用或文本，丢掉它们并不比交付它们更诚实，而「直到 response 结束才交付」这条承诺仍然成立。

**不得**沿用现有 `stream.py` 各 ending 的现状作为答案：那里的 exception／client-deadline 分支不 flush 缓冲块，clean EOF 分支却先 `session.finish()`，抄任何一条都会让输出取决于失败**以何种形式**到达，而不是取决于 policy。

## 8. 失败、截断与容量

- **上游终局失败事件**（`response.failed` / `response.cancelled` / `error`）：若最终可见则**逐字**重放。
- **代理侧错误**（cap 超限、客户端 deadline、预算耗尽而无上游终局）：按 `error-envelope/spec.md` 写 Responses `event: error`，**不得**合成成功 terminal。**续写按 §2.8 以本腿自己的方言提供**（用户 2026-09-01 裁决：块级交付在直连与翻译两条路上都必须原生支持，续写是它的一部分）；在那项工作落地之前本腿没有续写通道，代理侧错误直接写 error frame。此前这里写的是「不得咨询只适用于 Anthropic 客户端的机制」，那句话把一个**尚未实现**的限制写成了一条规范。**客户端取消与下游写失败除外**——那两种情形没有可写通道，§7.2 已把它们列为不收口的例外，写 error 是写给一个已经不在的读者。
- **`status: "incomplete"` 的 item**：**必须**照常交付，**不得**套用翻译腿的 `cut_short` / hand-over 政策——`hand_back_block()` 对非 Anthropic inbound 返回 `None`，那套政策在本腿上只会让最后一个 item 消失。
- **无终局 EOF**：本腿不得伪造成功终局（§6.3 禁止推导）。按 §5 判断：首个原生事件提交前可 replay；提交后写 `event: error` 并保留已交付前缀。
- **memory cap**：`buffer_cap_bytes` 的用户注释是**双语的**，两半给出的读法不同：英文半句是「max bytes to buffer before abandoning this response」，中文半句是「累计缓冲超此字节即放弃该响应」——后者可以读成随时间累加。**本规格取「当前持有」这一读**（§2.3 推导，不是用户的定义本身；v8 之前只引了支持结论的英文那半句，属转述丢掉了限定成分）。理由：它与 `BufferCapExceeded` 自述的「guard bounds memory」、与「abandoning this response」的语气一致，而且它是两种读法里**唯一能让 `full` policy 有意义**的那个——按累计读法，`full` 与 `block` 的 cap 行为将没有区别。若用户裁定取累计读法，本节与 §7.2 的 `full` 行为都要重估。因此**限制的是本代理当前持有的字节，不是累计交付量**。本腿计入：尚未 `done` 的原始事件队列、已完成但被 policy 扣住的事件组、control events、以及同时保留的预渲染副本。释放、replay reset、failure、cancel 后按实际持有退还计量——**replay reset 的时点是「重开成功」而非「判定可 replay」**（§5），因为旧队列要保留到新流到手。这一项本身不产生错误行为（保留期内新 attempt 还没开始产字节，峰值不会超过旧 attempt 已有的持有量），但两种读法会让计数器差一个窗口，属「缺席读不出来」的同族。

## 9. 非流式（仅成功响应）

**本节只覆盖成功（2xx）非流式响应。** 上游的非流式**错误**响应按 [`error-envelope/spec.md`](../error-envelope/spec.md) §3.1 **原始字节透传**，包括其 `Content-Type`（上游答 `text/html` 也照传）——那是跨腿合同（§2.4），不因本腿走 native 而改变。两条规则各自都对，只是定义域此前没写：一个照本节字面实施的人会把上游的 4xx／5xx JSON body 也 parse 一遍再重新序列化，而那正是 error-envelope 用一整节前置工作在防的事。

**当前行为的准确陈述**：`inference.py` 先 `response.json()`（并拒绝非 object 的 JSON），`response_payload` 在 `translation_required is False` 时返回同一个 dict，随后 `JSONResponse(payload)` 再序列化。因此**未知字段按 JSON value 保留，但 raw bytes、空白、key 顺序、数字字面形式、重复键与原 `Content-Type` 都不保留**。v1 写的「今天已是 body 原样返回」按 §3 的逐字读法是错误陈述。

**本规格裁定**：合法 Responses JSON object 按 **JSON value 保真**，所有未知字段保留，允许序列化拼法变化；HTTP status 原样；response headers 见 §9.1。

若将来要 byte-exact，必须在 JSON parse 之前直接交付 `response.content` 与原 content type，并另定非 object／malformed 成功 body 的行为。

## 9.1 成功响应头（流式与非流式同一合同）

**来源已由用户裁决**（`docs/.human-controlled/client-side-block-delivery.md`「客户端响应头」）：**只在第一次 HTTP 200 尝试时转发响应头**；后续重试若 HTTP 报错只能转成 SSE error，并**已明确接受**「找不到载体转发后续 attempt 的 `Retry-After`」这个限制。replacement attempt **不得**覆盖已提交的响应头。

> **该裁决的定义域是流式块级交付；把同一规则延伸到非流式是本规格的推导**（§2.3），标题里的「同一合同」四个字指的是这个延伸的结果，不是用户裁决的范围。原文所在的文档名、所在节、以及它给出的补救方式（「只能转化为 SSE error」）三重都把定义域钉在流式上——非流式既没有「已经发出去收不回来」这个约束，也没有 SSE 这个补救通道。**当前行为无差异**：`direct_driver/base.py:136-193` 的 `run` 拿到响应头即返回，body 在 driver 循环之外读取且读取失败不会重回该循环，所以非流式上「第一次 200 的头」与「产出 body 的那次 200 的头」恒为同一个 attempt。将来非流式接入 replay 时须重估。来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-08。

**哪些头转发：用户已经写过一份名单，而本规格此前写着「用户未裁决」——这是错标，v8 更正。**

`docs/.human-controlled/message-format-reshape.md` 的「客户端返回 Anthropic Messages」一节逐字写着：

> 直连路径的黑名单有：
> - `Connection` `Keep-Alive` `Proxy-Connection` `Hop-By-Hop`
> - `Date` `Cache-Control` `Set-Cookie`
> - `Content-Length` `Content-Encoding` `Transfer-Encoding`
>
> （TODO：这些条目来自 `copilot-api-js` 项目，需要了解原因）

> 名单第一行的 `Hop-By-Hop` **不是一个头名，是类别标记**（用户在写「以及逐跳的那一族」）。所以 `TE`／`Trailer`／`Upgrade`／`Proxy-Authenticate`／`Proxy-Authorization` 已被用户名单覆盖，下面剥它们不构成偏离。

**定义域待用户裁定，这是本规格当前唯一需要用户裁决的事项**（§11）：该节标题是「客户端返回 Anthropic Messages」，而本腿的客户端收到的是 Responses。但 [`error-envelope/spec.md`](../error-envelope/spec.md) §3.1 已经把这份名单套用到本腿，且它的路径判据键在 `Route.translation_required is False`——**自 v10 放宽定义域之后，那与本规格的定义域完全相同**（v10 之前本规格还要求两端同为 `openai-responses`，那时它是超集；这句限定是放宽时漏改的窄读）；而 §2.4 又声明 error envelope 这类跨腿合同「仍然适用」。所以在裁决到达之前，本腿的响应头上并存着两份当前指令。

**裁决到达之前一律取交集**：下面的语义判据在用户名单**之上**运行，**除用户黑名单已点名者外**才谈转发。

**这在剥离方向保守，在转发方向不是——差异有两侧，不止一侧。** 用户在同一份文件里给请求头下过定义：「仅部分请求头是需要剥离的，即采用**黑名单机制**」，而黑名单的语义是「只剥这些，其余转发」，所以它不只规定剥离集，也蕴含转发集。于是：

- **名单要剥而本规格会转发的**：`Date`、`Cache-Control`、`Set-Cookie`。取并集之后它们被剥掉，这一侧不与名单相反。
- **名单没点名而本规格要剥的**：strong `ETag`、`Content-Digest`／`Digest`、`Repr-Digest`、`Content-Range`、legacy `Content-MD5`——按黑名单读法这些应当转发。**这一侧确实偏离名单**，而且按下面判据自己的说法「这是例子不是穷举」，这一侧的偏离数不完。

这一侧的偏离是有理由的（本代理已经重新成帧或重新序列化，那些字段不再为真），但那个理由是**本规格的推导**，不是名单授权的。v8 曾写「落地后不与任一份权威相反」「差异只在三项」，两句都只算了一侧。

**以下的判据本身是本规格的推导**（§2.3）：

- **必须剥离**：hop-by-hop 头（`Connection`、`Keep-Alive`、`Transfer-Encoding`、`TE`、`Trailer`、`Upgrade`、`Proxy-Authenticate`、`Proxy-Authorization`、以及非标准但既有直连表已列的 `Proxy-Connection`）——HTTP 规范要求，不是产品选择。
- **必须由本代理重建**：`Content-Length`（流式重新成帧后不再成立）、`Content-Encoding`（若本代理已解压）、流式的 `Content-Type`（`text/event-stream`）。
- **必须剥离 `Connection` 逐跳清单里点名的头**。`Connection: X, Y` 把 `X` 与 `Y` 也声明为逐跳，所以固定名单不够——**必须先读 `Connection` 的值，把它列出的每个字段一并剥掉**，再剥 `Connection` 自己。
- **必须剥离因 body 变换而失效的表征元数据**。判据是**语义**而非名单：**任何验证或描述上游确切字节、而本代理未重新计算的字段，一律剥离**。非流式会重新序列化 JSON（§9），流式会重新成帧，两边都不再持有上游那份字节。当前已知的例子有 **strong** `ETag`、`Content-Digest`／`Digest`、`Repr-Digest`、`Content-Range`、以及 legacy 的 `Content-MD5`——**这是例子不是穷举**，写成名单必然漏，round4 就漏了 `Content-MD5`。

  > **v5 的例子里有两个不满足这条判据，是我把名单和判据混着写留下的。** `Last-Modified` 描述的是源资源的修改时间，不验证响应字节；**weak** `ETag` 的用途恰恰是标识语义等价而非逐字节相同。两者都不是 exact-byte 断言，因此**保留**。strong `ETag` 仍须剥离或重算。若将来要连 weak validator 也一并剥，那是「块级交付可能改变表征」的另一条取舍，须单独裁定，不能当成本判据的必然推论。
- **非流式的 `Content-Type` 由本代理按实际输出重建**。§9 已说明成功 body 会被 parse 成 JSON object 再由 `JSONResponse` 重新序列化，所以输出的就是 JSON——转发上游的 `text/html` 或 vendor media type 会告诉客户端一件不再为真的事，且显式 `Content-Type` 还会压过 `JSONResponse` 本该生成的 `application/json`。只有当上游的 media type 与实际输出兼容时才可保留。
- **`Content-Encoding` 是 strip-or-recompute**：生产路径经 `httpx2` 的 content decoder 读取，body 到这里已解压，所以上游那个值不再为真——**删除它**，只有本代理自己重新编码时才设新值。**不得**复用原值。
- **除用户黑名单已点名者外，其余一律转发**，包括本代理不认识的头。理由与 §2.1 同源：客户端本来就是冲着这个上游去的，`request-id`、rate-limit 系列、`retry-after` 等决定它的关联、退避与限流行为，剥掉它们是把代理的无知强加给客户端。

> **以下这段论证的是「要不要加额外防护」，不能用来越过一份已经存在的用户名单。** 即使用户裁定本腿不适用那份名单，它的结论也不变；反过来，它也不构成转发 `Set-Cookie` 的授权。
>
> **这与 cassette 录制用 allowlist 的既有教训不冲突，两者场景相反。** 那条教训（denylist 让三个识别性 header 漏进磁盘）针对的是**把上游响应写进版本库**，防的是账号标识被提交；这里是**转发给发起请求的客户端本人**，它对上游的可见性本就不低于我们。没有具体危害就不加防护，是用户既有的安全立场。

**当前实现均未转发任何上游语义头**（非流式只构造 `JSONResponse(payload, status_code=...)`，流式只构造 `_AccountedStreamingResponse(..., media_type="text/event-stream")`），所以本条是新增行为，需要各自的测试。

## 10. 可观测合同

**wire 的 source of truth 永远是上游原生事件与原生 terminal；可观测事实从旁路派生，不得反向改写 wire。**

本腿**至少**要记录：原生 output item 计数、需要客户端行动的 tool 名称／类型（§7.1）、reasoning 是否出现、权威 terminal status 与 usage、failure／截断／replay 的来源。无法分类时**必须**明确记为 unknown，**不得**伪装成 absent——`Terminal` 的 `stop_reason` 空默认值就是为这个区分而设的。

权威 terminal status 与「后续是否仍需客户端行动」是两个可以同时为真的事实，必须占两个槽，不能把后者折进前者，也不能拿前者覆盖后者。本轮实现范围是原生 Responses **流式**直连路径：它从 `response.output_item.*` 与 `response.completed` 事件建立旁路事实；非流式 direct `/responses` 仍属 [`../tui/deferred.md`](../tui/deferred.md) 第 0 条的 whole-body reader 缺口，本轮不把它写成已覆盖。

- `terminal_status` 逐字记录原生 response 对象的 `status`，缺席时为空。`response.completed` 到达且 response 内的 status 缺席时，可由事件名记录 `completed`；这是该原生 terminal 自己给出的状态，不是推测。它不覆盖 `Terminal.stop_reason`——后者仍是翻译和续写策略使用的语义结局，两者的消费者不同。
- 最终 client-action 摘要的 authority 是终局 response 对象的完整 `output` 数组，不是 `output_item.done` 到达顺序，也不是 buffering policy 的 bool。按数组位置得到 Responses `output_index`，逐项运行 §7.1 的三态分类；`client_actions` 只记录 `required` 或 `unknown` 的 typed facts，`not_required` 不进入列表。每项至少含 `requirement`、原生 `type`、可选 `name` 与 `output_index`，保留重复。`function_call` 与 `custom_tool_call` 均为 `required`；名称为空时仍保留 type。原生 type 未知时保留原文并把 requirement 记为 `unknown`，只有 type 本身缺席时 type 才记为 `unknown`。
- `client_action_classification_complete` 是 terminal snapshot 的集合级事实，不能由 `client_actions` 是否为空反推。它只在终局 response 明确携带一个 `output` 数组且数组里的每一项都得到三态分类时为 true。显式空数组满足条件，代表 terminal snapshot 已确认没有 output items；`output` 缺席或类型错误不满足。数组元素不是 object 或缺少 type 时仍可得到 `unknown` 分类，所以它不会把“结论未知”混成“没有分类”。stream 的未闭合 item、越界 index 与 unattributed events 继续由 §4、§7.2、`cut_mid_block`、请求 verdict 与 detail 报告，不进入这个字段；把交付完整性也塞进 terminal snapshot 分类会在同一请求上建立第二套状态机。
- `completed` 只说明这一份 Responses response 已经收口。只有 `client_action_classification_complete is true` 且 `client_actions` 为空时，terminal snapshot 才足以断言没有客户端行动；含 `required` 时模型仍在等待，含 `unknown` 或 snapshot 分类不完备时本代理无法确认工作已经结束。这三种情形都不足以支撑绿色。展示层必须同时读 status、typed facts 与集合完备标志；其文本和颜色合同由 [`../tui/spec.md`](../tui/spec.md)「着色规则」与「描述回复的用词跟随上游」两节定义。任何只按 `terminal_status` 或空 action 列表把 `completed` 判绿的实现都不满足本条。

用户于 2026-09-03 明确指定 `completed + function_call/custom_tool_call` 不绿，并选择把 terminal status 与 client-action facts 分槽。三态分类、集合完备标志、terminal `output` authority、`output_index` 顺序、重复、无名与 unknown 的记录与呈现是本规格依据既有 §4、§7.1 与「unknown 不得伪装 absent」合同作出的推导，不标作用户原话。

`BlockBuffer` 今天靠 Anthropic `kind` 同时承担 payload 载体、释放判据与日志分类三件事；本腿**不得**沿用该耦合。

## 11. 未闭合项（归本规格所有）

**当前一项待裁**（O-1）。**O-2 已于 2026-09-01 由用户裁决**，条款移入 §6.5；本节按 §11 自己的惯例保留一行存根指向定案处，不删除编号。

| # | 未闭合项 | 现状 | 谁能裁 |
|---|---|---|---|
| O-1 | `message-format-reshape.md`「客户端返回 Anthropic Messages」一节的**直连响应头黑名单**是否覆盖 **Responses 客户端**的直连腿。**只问这一条腿**：四条直连腿里，Anthropic 直连的客户端收到的就是 Anthropic Messages，那一节的标题直接覆盖它，没有定义域疑问；Chat Completions 直连今天字节直传、不进本节；Embeddings 非流式 | §9.1 在裁决前**剥离集取并集**（黑名单 ∪ 语义判据）。**差异有两侧**：名单要剥而本规格会转发的是 `Date`／`Cache-Control`／`Set-Cookie`（取并集后被剥，这一侧不与名单相反）；名单没点名而本规格要剥的是 strong `ETag`／`Content-Digest`／`Content-Range`／`Content-MD5` 一族（这一侧偏离名单，且按语义判据自己的说法数不完） | **用户**。节标题的定义域只有作者能裁。**一条对裁决有用的文本事实**：同一份文件的**请求头**那一节写着「这部分仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效」，**响应头**那一节没有任何同类限定句，只有节标题——这个不对称可以朝两个方向读（「需要限定时用户会明确写出来」或「开头一节的限定统辖全文」），本规格不主张任何一读。另：用户自己在该节旁挂了 TODO「这些条目来自 `copilot-api-js` 项目，需要了解原因」，而本项目指令明令不得把 copilot-api-js 的默认值当作项目契约——所以这可能不是一条已定型的裁决，而是一份待用户自己复核的继承清单 |

| ~~O-2~~ | **已裁决，2026-09-01。** 用户原话：「加，按窄形态 ＋ 显式 opt-in」。条款移入正文定案，见 §6.5 | **已定案**，不再是未闭合项 | 用户已裁 |

> **v8 关闭过一项又在 v9 重裁：**「无法归属」的事件在 ending 处的处置。v8 按 ending 来源二分，v9 改为按「收口时刻有没有未闭合 item」判——重开条件（「出现坏帧」）在 v8 落笔当轮就已被满足，且构造即可、不需要上游样本。详见 §7.2 收口第 3 步下的说明。它属本规格推导且触到 §2.1 的边。

v4 把更早挂在这里的产品分叉全部移入正文定案：header 合同 → §9.1；`requires_client_action` 的数据来源 → §7.1（item 自带，无需请求侧通路）；policy × ending → §7.2；native failure 的 taxonomy 输入 → §5.2。

实施状态不属于本节，见 [`plan.md`](plan.md)。**不需要用户裁决的延后项**（清理、跨主题指针）归 [`deferred.md`](deferred.md)，本节只放需要用户裁决的产品分叉。

### O-2 的两侧，以及裁决（已闭合，存档）

> **裁决结果：用户 2026-09-01 裁定「加，按窄形态 ＋ 显式 opt-in」。** 规范条款是 §6.5。以下两侧论据保留为裁决当时摆在用户面前的材料，不再是待决内容。

**支持加**：能救活用户手上已经死掉的会话，代价是一次窄改。**受影响的会话不会自愈**——`1fb37cd` 阻止的是产生新的坏 item，它修不了已经写进客户端 rollout 历史的那些。

**反对加**：这是一次兼容整形，按 §2.7 **必须**另立显式、可选的合同，不得混进 native。判据只能靠 id 形态启发式，而形态识别的紧度依赖 provider：Copilot 签发的 item id 是无前缀的 base64，所以在本上游够紧；换成 OpenAI 本家就不再成立，`rs_` 正是其合法前缀。**更窄的做法存在**：不认「`rs_` ＋任意＋数字」，只认 `rs_` ＋ 一个规范 `uuid4` ＋ `_` ＋ 序号（即 `_item_id()` 真正会产出的形状），并按 provider 或显式 opt-in 限定作用域。

> **先前草稿的主论据是「这个缺陷自清」，那句话站不住，两处都错。** 其一，它当时写作「本代理再也不会产生这种 item」——而 4141 上运行的仍是早于 `1fb37cd` 的构建，**在明确 cutover 之前它还在制造新的污染**，所以那句话当下为假。其二，「不再新增」只等于集合**不再增长**，不等于**自行清空**：一个保存完整 rollout、失败后既不推进也不裁剪历史的客户端，会把同一个坏 item 永远重发下去——而 issue #4 描述的正是这样一条会话。这条论据被独立评审（`reports/260901-review-issue4-artifacts.md` review-03）判为系统性高估死代码、低估可持续污染，此处采纳。

**我当时的建议（低置信）**：先不加。**用户裁决与之相反**——采纳了「加」，并同时指定了形态（窄识别 ＋ 显式 opt-in），即上一段里更窄的那个方案。这正是低置信的那个量落地的地方：决定天平的是「手上有没有一条不愿放弃的长会话」，而那个量只有用户有。

> 以下**不在**本规格定义域，已从待办移出：`function_call_output` 在响应 output 中的出现与翻译，归 `anthropic-responses-bridge/spec.md`（见 [`reports/260830-known-set-divergence.md`](reports/260830-known-set-divergence.md)）；本腿无条件携带它。

## 12. 修订记录

| 日期 | 条款 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-04 | §7.1、§10 | **v21。** `bb5783f` 实现 v20 合同：三态 classifier 与 policy bool 投影分开；Responses passthrough 只在 `response.completed` 从 terminal `response.output` 采集 status、ordered typed actions 与 snapshot completeness；三项事实经 RequestTrace 与 RequestLine 持久化并由独立 renderer 组合判读。`response.incomplete`、translated 与 nonstream 均保持 legacy 行为。实现评审修复 present-empty `{}` 被 batch truthiness 跳过的边界，终评 0 blocker、0 major；最终 Ruff clean、Pyright 0、full regression 2213 passed、2 skipped、coverage 91.29% | `bb5783f`；[`reports/260904-completed-client-actions-implementation-review-disposition.md`](reports/260904-completed-client-actions-implementation-review-disposition.md) |
| 2026-09-03 | §7.1、§10 | **v20。** Responses 流式直连的权威 `terminal_status` 与 typed `client_actions` 分槽；action requirement 从 policy bool 拆为 `required`、`not_required`、`unknown` 三态，policy 只读其布尔投影；最终摘要以 terminal `output` 为 authority，并以 `client_action_classification_complete` 区分空 actions 与尚未分类完备。`completed` 仅在集合分类完备且无客户端行动时可绿；action 按 terminal output position 排序并保留重复、无名与 unknown。非流式 reader 仍留在 TUI deferred 第 0 条 | 用户主动指出 `completed + function_call/custom_tool_call` 不代表工作结束，并选择 terminal status 与 client-action facts 分槽；三态、terminal `output` authority、集合完备、顺序、重复、无名、unknown 与 streaming 定义域的精确化为本规格推导，来源是 §4、§7.1、§10 及 2026-09-03 独立评审 |
| 2026-09-01 | §6.5.1、§6.5.2、§6.5.3、§6.5.5 | **v19。** §6.5 落地后的独立评审，3 major／5 minor，**全部采纳，无驳回**。(a) **§6.5.3 的定义域此前只写在纸上**：实现只查了 `target_format`，并用「翻译后的 body 没有 Responses `input` 数组」当省略另两道门的理由——该理由被 `to_openai_responses()` 源码与执行探针共同证伪（它无条件建 `input`，`_reasoning_item()` 还能往里放 sealed item）；**今天没出事只是因为当前 translator 不往那个 item 上写 id**，即定义域是被一个巧合实现的。三道门现已逐字落地并各有反例测试；(b) **§6.5.1 的判据宽于本代理能铸出的集合**：只写「小写十六进制 `8-4-4-12`」会放行 version-1 UUID 与前导零序号（评审实际构造并观察到被误删），而放宽正是「窄形态」裁决要防的那一侧；现补齐 version／variant／无前导零，并更正原文漏写的一组（应为 `8-4-4-4-12`）；(c) §6.5.5 的「计数长期为零即提出退役」**没有 oracle**——日志缺席同时兼容四种情形，且无时间窗、无触发者；改为一个不需要新机制的可判定条件（操作者关掉它、受影响会话不再出现绑定失败的 400）；(d) §6.5.2 的「正确 id 只存在于密文里」是无据的位置声称，改为「本代理没保留、也无法重建」；「任意不匹配 id 一律 400」改为「三个各试一次全部 400，全称是强推断非穷举」 | [`reports/260901-review-issue4-repair-impl.md`](reports/260901-review-issue4-repair-impl.md) |
| 2026-09-01 | §6.5（新）、§11 | **v18。用户裁决 O-2：「加，按窄形态 ＋ 显式 opt-in」。** 已被自铸 id 污染的客户端历史不会自愈，本代理为其提供一次性修补：入站 reasoning item 若带密文且 id 逐字匹配 `_item_id()` 真正会产出的形状（`rs_` ＋ 规范 uuid4 ＋ `_` ＋ 序号），删掉其 `id`，其余逐字保留。**两个限定词都出自用户**：窄形态（不是「`rs_` ＋任意＋数字」——宽形态会误伤 OpenAI 本家合法的 `rs_` id）、显式 opt-in（默认关闭，按 §2.7 它是兼容整形不是 native）。O-2 随之从未闭合项移入正文定案，§11 留存根 | 用户 2026-09-01 裁决 |
| 2026-09-01 | §6.2、§6.4、§11 | **v17。** 独立评审 5 major／2 minor，全部采纳。(a) **O-2 此前被停在 `deferred.md` D-8**，而那份台账开头逐字写着「需要用户裁决的产品分叉登记在 Spec §11，不在这里」——这是本项目「Spec 级事实不得停在待办账本」规则的直接违背，条目已移入 §11 并删去 D-8；(b) O-2 原来的主论据「缺陷自清」两处错（旧构建仍在跑、仍在制造污染；不再新增≠自行清空），已改写并降低建议置信；(c) §6.4 的回归测试此前只覆盖响应半程，请求半程（正是 400 被抛出的方向）只有论证没有测试，现已补齐并登记；(d) 响应侧夹具此前两处拼同一个 id，对「把上游漂移的两个 id 合并成一个」这第二种破法恒等、会静默变绿，已改用 cassette 的真实漂移；(e) 归因的措辞限定（两句 400 是否同一分支未闭合）补进 §6.2、文首与测试 docstring；(f) 两处全称过头（「本轮任何观测都看不出」「没有哪个上游会这么拼」）改为有证据支持的限定 | [`reports/260901-review-issue4-artifacts.md`](reports/260901-review-issue4-artifacts.md) |
| 2026-09-01 | §6.2、§6.4 | **v16。** GitHub issue #4：一条本来在用的 Responses 会话下一轮起持续 400 `invalid_request_body`。§6.2 此前把「不得重新 mint id」的代价全部记在客户端一侧（谁校验连续性），读起来是一次可权衡的取舍；实测证明对封了 `encrypted_content` 的 reasoning item 它是硬性正确性缺陷——**密文与签发时的 item id 绑定，上游回传时校验该绑定**，而 `_item_id()` 自铸的 id 必然对不上。§6.4 的「原样交还」随之补全为「`id` 与 `encrypted_content` 整对原样」，并登记已落地的回归测试与其变异校验。**该缺陷已由 `1fb37cd` 的 native 接线消除（它不铸 id），但已污染的客户端历史不会自愈**，作为产品分叉登记为 §11 的 O-2。归因带一条限定：原始那次 400 的措辞与重放时不同，「两句出自同一校验分支」未闭合（§6.2） | GitHub issue #4；[`reports/260901-issue4-passthrough-400-trace.md`](reports/260901-issue4-passthrough-400-trace.md)；[`reports/260901-review-issue4-artifacts.md`](reports/260901-review-issue4-artifacts.md) |
| 2026-08-30 | 全文 | 初稿 | GitHub issue #1／#2；用户裁决；方案评审的 blocker-01 |
| 2026-09-01 | §2.1、§2.8、§8 | **v15。** 用户两条裁决。**其一，命名**：这个功能叫 `continuation` 不叫 `hand-over`——后者是本规格与实现自造的词，而用户亲笔文档从头到尾叫「续写」，代码里的 `ContinuationSupport` 也早就是这个名字；改名要绕开 `lifecycle` 里同名但无关的 systemd 监听器交接。**其二，射程**：续写必须在每条直连腿上原生可用，因为块级交付在直连与翻译两条路上都必须全面支持——这推翻了 v12 把「native 腿不提供续写」列为候选的处置。**关键背景是这不是改主意**：用户文档的续写一节从一开始就写了 `tool_use` / `function_call` 两种形状、`messages` / `input` 两个字段，末尾那句「暂不」明写「未来我有需要后再补全」，所以待建的是一份已被指定、只实现了一半的合同。顺带照出 `client_message_count` 只读 `messages`、Responses 请求会得 0，而那个数正是循环检测器的输入（D-7） | 用户 2026-09-01 裁决 |
| 2026-09-01 | §2.5、§2.6、§2.8 | **v14。** (a) §2.5 那句「§5～§10 里句子里没有一个 Responses 专有的事实」是**全称否定，被六个反例证伪**，最重的一处是 §5.2 的归一化表——它的四个输入全是 `ResponseError.code` 的取值，而 Anthropic 的错误事件根本没有 `code` 字段；那是本规格里唯一规定了「怎么算 replay 是否合法」的地方，而那个算法只对一种方言存在。改为分开陈述「机制与方言无关／取值只写了一种方言」，缺失的 Anthropic 映射表登记为 [`deferred.md`](deferred.md) D-6。**这句被证伪的断言正是 v10 放宽定义域时唯一用来说明代价可控的论据**，论据不成立即代价没有被算过；(b) §2.6 的 Chat Completions 行只回答了 §2.1，而定义域放宽后 §5／§8／§10 按字面也落在那条腿上，`one_shot_delivery` 的 docstring 逐字否掉其中三条——写下「哪些条款在那条腿上今天不成立」而不是留白；(c) §2.8 的理由两处不准：顺序问题**不限于 `block`**，且更硬的阻断是类型而非顺序（`_hand_over` 把 `CompletedBlock` 交给只认 `RawEventBatch` 的 `block()`），因此 D-5 的候选 1 单独不解决问题，「缺的只是打开开关」也不成立 | [`reports/260831-review-spec-round9.md`](reports/260831-review-spec-round9.md) round9-02／07／12 |
| 2026-08-31 | 文首、§2.5、§2.6、§9.1、§12 | **v13。** (a) §2.5 的词汇表只列了六行，而 `Dialect` 实现有八个字段——漏掉的 `read_failure` 与 `reply_dialect` 都不是装饰，后者决定完成行按哪把尺子判读（两方言的字节阈值差一个数量级，实现里漏传这个参数就让 Responses 回复按 Anthropic 的尺子染色）；(b) **该表的 Anthropic control 集漏了 `message_stop`**，而同表下一行说 terminal 集是 control 集的子集——照表实施，每条 Anthropic 直连响应的终局事件都会被判为「无法归属」并永久持有，即挂死；实现是对的，不一致的那一侧是本规格；(c) §9.1 仍写着「本规格还要求两端同为 `openai-responses`」并据此称 error-envelope 的定义域是超集——那是 v10 放宽定义域时漏改的窄读，两者现在完全相同；(d) §2.7 与 §2.8 的物理顺序与编号相反；(e) §12 缺 v11／v12／v13 三行，文首停在 v10 | [`reports/260831-review-spec-round9.md`](reports/260831-review-spec-round9.md)：blocker 1、major 5、minor 6、nit 4；round8 十三条全部 closed |
| 2026-08-31 | §2.8、§2.6 | **v12。** §8 的「本腿不咨询 hand-over」原来只对 Responses 腿成立——那条腿的客户端执行不了 Anthropic 的合成块。**Anthropic 直连腿上 hand-over 今天就放行**（按 inbound 格式门控），而 native 交付已经把上游终局随批次发出，合成块的插入位置已经过去。因此该腿暂不接线，形态待裁（`deferred.md` D-5） | 接线时实撞 |
| 2026-08-31 | §2.7、§2.6 | **v11。** 走 native 会拿掉每条腿现有的兼容整形，而 Anthropic 的 `content_block_start_compat` **默认开着**且落在 Claude 系模型唯一的那条腿上，用户亲笔文档里还写着倾向让它常驻。裁定：接线不得改变任何一条腿今天已生效的整形默认值（`deferred.md` D-3、D-4） | 放宽定义域后两条腿并置才看出这是通则 |
| 2026-08-31 | 文首、§2.1、§2.5、§2.6、§6、§7.1 | **v10。** **用户裁决「根因修复所有直连路径」**，定义域从「两端同为 `openai-responses`」放宽为「任何 `translation_required is False` 的路由」。触发点是 v9 的一份自述局限：我在回报里说本规格只治 Responses 一对、其余直连对的同形缺陷仍在，用户读到后直接裁了范围——所以这是**用户对已知局限的裁决**，不是本规格推导出的一般化。随之新增 §2.5（一个引擎、每种方言一份词汇，并把「词汇只描述边界与归属、绝不描述 item 类型学」写成 §2.1 的直接后果）与 §2.6（四条直连腿今天各自的状态：Responses 是主体工作；**Anthropic 直连是同形缺陷且今天可达**，集成测试里已有 `anthropic-messages` 上游；Chat Completions 的天花板不存在但那是偶然——它没有 framer 所以字节直传，缺的是块级交付，属既有推迟项；Embeddings 非流式）。§6 与 §7.1 标注为方言专有，其余各节确认与方言无关 | 用户 2026-08-31 裁决 |
| 2026-08-31 | §3、§3.1、§6.2、§7.2、§8、§9.1、§11 | **v9。** (a) **v8 新加的 §7.2 收口第 3 步是错的**：它按 ending 来源二分，论据句字面说反了（「不再有 X 之外的解释」＝「唯一解释是 X」），而作者真想说的推理被本规格 §3「terminal 不能证明未知 lifecycle 已完成」逐字否掉；评审用骨架 assembler 实跑构造出坏帧（截断的 `done` 让 item 永远开着，该 item 事件被丢而这个 `done` 被逐字发出，客户端拿到孤儿帧且 payload 非法）。改为单一谓词「收口时刻有没有未闭合 item」；**未采纳评审建议里「代理侧 ending 一律丢弃」那半条**，理由写在正文（与同次收口第 2 步不一致）；(b) §6.2 说「其他客户端未穷尽」，而用户在 `config.example.yaml` 具名写下 `@ai-sdk/openai` 校验 ID 连续性——本腿改 native 即撤掉今天 framer 提供的稳定 id，对该类客户端是回归，此前无任何登记；产品分叉入 `deferred.md` D-3；(c) §8 的 cap 口径此前只引了用户双语注释的英文半句，中文半句「累计缓冲」可读成相反的意思，改为如实陈述这是本规格在两读之间的选择；(d) §9.1 的「不与任一权威相反」「差异只在三项」两句都只算了一侧——黑名单蕴含「未点名者转发」，语义判据会剥掉名单没点名的 validator／digest 一族；§11 O-1 同步为两侧，并补上「请求头那节有定义域限定句、响应头那节没有」这个对裁决有用的不对称；(e) §9.1 的「定义域完全相同」改为「超集」，并点破用户名单里的 `Hop-By-Hop` 是类别标记不是头名；(f) §3 的「明确不承诺」按新基准重述——其中两项其实与规范一致，v8 把五项统称为「非规范要求」会诱导读者去改动正确的行为；新登记一处真实偏差（不含冒号的 `data` 行）；(g) §3 的承诺面补上第 3 步提交的无法归属事件、排除句的步号改对；§3.1 第三条的 P3 状态与文首、plan 同口径 | [`reports/260831-review-spec-round8.md`](reports/260831-review-spec-round8.md)：blocker 1、major 3、minor 5、nit 4；round7 十四条全部 closed |
| 2026-08-31 | §3、§3.1、§4、§5、§5.2、§7.2、§9、§9.1、§11 | **v8。** (a) §9.1 写着「哪些头转发，用户未裁决」，而 `message-format-reshape.md` 有一份**用户亲笔的直连响应头黑名单**，`error-envelope/spec.md` §3.1 已按 `translation_required` 把它套用到本腿——一句「用户未裁决」永久关闭了一个用户已表过态的问题，且推导出的「其余一律转发」与名单在 `Date`／`Cache-Control`／`Set-Cookie` 上相反；改为事实陈述 + 裁决前取交集，定义域登记进 §11 待用户裁；(b) v7 为修 round6-03 补的那句给出两种读法（「扣住不发」与「发了不算数」），§5 只支持前者，且骨架测试注释已按错的那读复述 §5；改写为一句正面规则；(c) v7 只收紧了 partition 第一格，同节 ending 表第一行与 §5 的丢弃句仍是收紧前的谓词、无时点——修复没传播到全部复述处，而漏掉的正是 step 6 视角最先读到的那张表；(d) **「无法归属」的事件被持有到 terminal 之后没有归宿**，收口三步两类都不含它，骨架 docstring 已代本规格裁定为丢弃——而丢弃的理由恰是「判不出归属」，正是 §2.1 否过的那个理由；新增收口第 3 步按 ending 来源二分；(e) §5.2 的三分法论据、`AttemptFailed` 的 origin 取值、`ReopenRefused` 今天为空的如实陈述；(f) §9 补定义域（只覆盖成功响应，错误 body 归 error-envelope 原始字节透传）；(g) §3 的保真基准从「本项目 parser 的输出」改钉到 SSE 规范的 field parsing 算法——否则该承诺对 P3 那类 parser 缺陷天然没有分辨力；(h) §3.1 第三条的机制陈述、cassette 计数的限定词 | [`reports/260831-review-spec-round7.md`](reports/260831-review-spec-round7.md)：blocker 1、major 3、minor 6、nit 4；round6 十条与 skeleton 十一条全部 closed |
| 2026-08-31 | §3.1、§4、§5、§5.2、§7、§7.2、§9.1 | **v7。** (a) §7.2 的 partition 第一格与第二格**在时间上不互斥**——第一格谓词在尝试重开之前就可求值并要求「全部丢弃」，第二格却把只有重开之后才知道的「被拒」算进自己并要求提交那批已被销毁的 group；第一格补「且重开已经成功」，final source 表补「上游终局存在但其 attempt 已作废」一行；(b) 用户亲笔的「优雅关闭时报错不再考虑无痕重试」**§5 从头到尾没记**，而 §5.2 把 draining 建成重开后的拒绝、时序与裁决相反——补记进 §5 的资格清单并移出 §5.2 的结果表；(c) §4／§7 的「安全前缀一就绪即发出」与 §5 的「control events 保持 attempt-local」对每个请求的首帧给两个答案，按前者实施会让直连腿的透明 replay 在默认 policy 下**永不成立**——§4 补「control-only 前缀不构成提交」，§7 的 `block` 行补提交时点限定；(d) §4 定案「已 `done`」指该 item 的 `done` 也在同一前缀内，一个 item 的事件不得跨越释放边界（否则半个 group 出门，且用一个无内容价值的字节关掉整轮 replay 窗口）；(e) §4 明确「无法归属」与「envelope」是两个相反处置、必须是两个可区分的答案，附 SDK 3.3.1 的 4 个 audio 反例；(f) §5.2 的「余下 17 个是明确的非瞬时失败」仍是未逐项核验的全称，`failed_to_download_image` 改为「未核、保守落 `None`」；(g) §3.1 的两条改为已实现并新增第三条（`splitlines()` 是 SSE 断行集的超集，会截断 data）；(h) §5 的「用户亲笔的重试合同」引号是转述而非原文，改为「概括为」并写明后半句在人写文档里没有对应句子；(i) §9.1 的用户裁决定义域只覆盖流式，向非流式的延伸标为本规格推导 | [`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md)：blocker 1、major 2、minor 6、nit 1；[`reports/260831-review-skeleton.md`](reports/260831-review-skeleton.md)：major 4、minor 6、nit 1 |
| 2026-08-31 | §5.1、§5.2、§7.2、§9.1 | **v6。** (a) §7.2 第二格把「有上游终局」的情形也写成 proxy error——它至少装着三种来源，其中三种手里有上游自己的终局；新增 final source 表，明确 **carrier 由 final source 决定、与 commit 状态正交**；(b) `vector_store_timeout` 归入瞬时，v5 的「其余 18 个全非瞬时」把它一起压掉了；(c) §5.1 仍把 draining 枚举成「replacement 失败」，与 §5.2 的 `ReopenRefused` 相反——改为引用；(d) §9.1 的例子里 `Last-Modified` 与 weak `ETag` **不满足**同句的判据（它们不验证响应字节），已移出并明确保留，`ETag` 拆强弱；非流式 `Content-Type` 此前落进「其余一律转发」，会告诉客户端一个与实际输出不符的 media type | [`reports/260831-review-spec-round5.md`](reports/260831-review-spec-round5.md)：blocker 1、major 3 |
| 2026-08-30 | §5.2、§7、§7.2、§8、§9.1、文首 | **v5。** (a) §7.2 的「任何 ending 一律收口」与 §5 的透明 replay **互斥**——先提交已完成 group 就等于提交了首个原生事件，而 §5 随即禁止 whole-attempt replay；根因是「ending」一词同时指了「可能被 replay 掉的 attempt 结束」与「客户端最终看到的结束」。现在 §7.2 只在 replay 判定之后运行，表里加了 funded replay 一行，§7 主表与 §8 的两处同类表述一并同步；(b) §5.2 放宽——v4 写的「没有 code 语义表」是**未核就写的错误**，`ResponseError.code` 是 20 成员 `Literal`，`server_error` 与 `rate_limit_exceeded` 语义明确；v4「replay 窗口很窄」的判断也只对 `block` 成立，`full` 下窗口覆盖整次 attempt；(c) §5.2 把重开结果分成 `OpenedAttempt`／`AttemptFailed`／`ReopenRefused` 三类可观察事实——v4 的「它是一个 exception」不成立，draining 时根本没调用过 `handle`；(d) §9.1 补 `Proxy-Connection`，表征元数据改为**语义判据**而非名单（名单必漏，round4 漏了 `Content-MD5`），`Content-Encoding` 明确为 strip-or-recompute | [`reports/260830-review-spec-round4.md`](reports/260830-review-spec-round4.md)：blocker 1、major 2、minor 2 |
| 2026-08-30 | §5.2、§7.1、§7.2、§9、§9.1、§11、文首 | **v4。** (a) §7.2 新增 policy × ending 表——v3 只裁了未闭合 suffix，没裁 `full`／未触发 `until-tool-use` 持有的**已完成** group 遇 proxy ending 时的去向，那里三条规范互斥；裁定为「丢 suffix → 按原序提交已完成 group → 提交 terminal 或 error」，客户端取消与下游写失败显式例外；(b) §5.2 新增 native failure → taxonomy 的归一化表——v3 的「复用既有 taxonomy」不是复用而是留空，因为 `replay_reason` 只认 exception 与 HTTP status，而原生 failure 两者都不是；当前保守判为一律不重试并写明放宽条件；(c) §9.1 补 `Connection` 逐跳清单点名的字段与因 body 变换失效的 validator／digest；(d) 同步 v3 只改了解释段而漏掉的 signature、正例、§9 旧句、§11 与文首状态 | [`reports/260830-review-spec-round3.md`](reports/260830-review-spec-round3.md)：blocker 2、major 2 |
| 2026-08-30 | §3、§5.1、§7.1、§9.1、§11 | **v3。** (a) §3 的「每一个事件」是不可兑现的全称——未闭合 item 遇 terminal／failure 时，完整单位／逐事件保真／不重排三者不可兼得；改为限定在「可提交的完整 item group + control + terminal」，并写明未闭合尾巴的丢弃时点与「terminal 不证明未知 lifecycle 已完成」；(b) §5.1 补三个此前无定义的状态转换（原生 failure、无终局 EOF、replacement 自身失败）；(c) §7.1 更正判据来源——响应 item 自带 `execution`／`environment`，v2 写的「需回查原始请求」是对上一轮评审的误读；(d) §9.1 把 header 合同写进正文并覆盖流式，来源部分援引用户亲笔裁决、选择部分标为本规格推导 | [`reports/260830-review-spec-round2.md`](reports/260830-review-spec-round2.md)：blocker 3、major 1 |
| 2026-08-30 | §2、§3、§4、§5、§6、§7、§8、§9、§10、§11 | **v2 全面重写。** (a) §3 的「data 逐字」与「重编 sequence_number／output_index」自相矛盾——那两个字段就在 data 里；改为一律不改写，并新增 §4 的 commit frontier 保持全局顺序而非重排；(b) §2 拆开 provenance，用户 8/30 原话只覆盖「不得以不认识为由拒绝」，其余归本规格推导；(c) §5 新增 control event commit 时点与 attempt replay 合同（v1 完全缺失）；(d) §7.1 定案 `requires_client_action`，v1 留给实现是错的——同一 `tool_search_call` 会因请求的 `execution` 而相反；(e) §3 的可行性论证有两个实跑反例（多行 payload 重放丢行、CRLF 帧被合并），改为先修再依赖；(f) §9 更正「今天已是 body 原样」的不实陈述；(g) §10 新增可观测合同，v1 §1 的「唯一消费者是 framer」被源码反例推翻；(h) §11 关闭原第 3、4 项（cap 口径与 carrier 门已有确证），移出定义域外项 | [`reports/260830-review-spec.md`](reports/260830-review-spec.md)：blocker 3、major 5，全部采纳 |
