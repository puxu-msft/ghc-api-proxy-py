# 直连路径原生透传：延后项台账

**这份是活文档**，**只放未闭合项**。查清、决定或做掉的条目从这里移出，并入 [spec.md](spec.md)、[plan.md](plan.md) 或代码注释，移出时带上出处。编号是标识不是序列，移走后不补号。

权威是 [spec.md](spec.md) 的**当前版本**（它也是活文档，不冻结）。本台账不新增规范，只登记它排除或推迟的东西，使其不被静默删掉。**本台账不得成为绕开 Spec 的去处**——Spec 级的事实一律落在 Spec 里，已知错误的条款当场修订，不在这里登记待办。需要用户裁决的产品分叉登记在 Spec §11，不在这里（当前那里有一项：响应头黑名单的定义域）。

建立于 2026-08-31。

## D-1　`format_sse_event` 与 `encode_frame` 是两份等价实现，前者无调用者

**状态**：等用户裁决是否删除。**我不擅自删已实现的功能。**

**事实**：`src/app/streaming/sse.py` 的 `format_sse_event(data, *, event=None)` 与 `src/app/pipeline/delivery/sse_source.py` 的 `encode_frame(event, data)` 逐语句等价——都按 `data.split("\n")` 每行写一条 `data:`，再补空行。签名只差 `event` 是否可选。**`format_sse_event` 在 `src/` 与 `tests/` 里没有任何实际调用者**，只在 `src/app/streaming/__init__.py` 被重新导出并列进 `__all__`。

**出处**：[`reports/260831-review-sse-line-endings.md`](reports/260831-review-sse-line-endings.md) F-01。该缺陷**先于** P3 那一刀存在，不是它引入的。

**为什么现在不动**：删除一个已实现并已导出的符号是对外行为决定，不是清理；`__all__` 里的名字可能被视作公开面。若要处置，两条路都可以：删掉并从 `__all__` 移除，或让它委托给 `encode_frame` 只留一个实现。

**风险**：两份实现各自演化。P3 只改了 `sse_source.py` 那一侧的**解析**方向，编码侧本轮未动，所以当前两份仍然一致——**这个一致是巧合，不是机制**。

## D-2　响应方向的 `function_call_output`：两条路径已知集合不一致，且无任何活文档记录

**状态**：权威归 `anthropic-responses-bridge`，而**那个主题当前没有记录这件事**。本条只是指针，防止它只活在一份报告里。

**事实**（实测，见出处）：Copilot 若在响应 `output` 里给出 `function_call_output` item，缓冲路径 `blocks_from_item` 把它变成 `role="user"` 的 `BlockKind.TOOL_RESULT` 正常返回，流式路径 `ResponsesAssembler` 则以 `code=unknown_output_item` 拒绝。同一个 item，两条路径两个答案。

**为什么它不归本规格**：本腿不翻译，无条件携带该 item，所以透传落地后直连腿这一半自然消失（[spec.md](spec.md) §11 已记这条定义域划分）。剩下的是**翻译腿**的问题。

**为什么仍要在这里留一条**：`anthropic-responses-bridge/spec.md` 只在**请求方向**覆盖 `function_call_output`（user `tool_result` → `function_call_output`，见其 §「双向字段处置矩阵」），**响应方向一个字没有**；该主题也没有 `deferred.md`。于是这条事实目前只存在于一份报告里，而项目规则明令报告不得成为唯一真相来源。

**还缺的证据**：Copilot 究竟会不会在响应 `output` 里发 `function_call_output`。SDK 的 `ResponseOutputItem` union 里有 `ResponseFunctionToolCallOutputItem`，说明**协议允许**；本项目 cassette 与 history 里有没有真实样本**未查**。在拿到答案之前不应单方面选定「拒绝」或「按 tool_result 处理」——前者误伤一个协议允许的形态，后者把 user 角色的块塞进 assistant 回复。

**出处**：[`reports/260830-known-set-divergence.md`](reports/260830-known-set-divergence.md)。当时的处置是「转入设计」，设计尚未落地。

## D-3　本腿启用透传即撤掉稳定 item id，对已具名的一类客户端是回归

**状态**：产品分叉，等裁决。**登记本身不需要用户点头，怎么裁需要。**

**事实**：今天直连 Responses 腿由 `ResponsesFramer` 成帧，`_item_id()` 用 `f"{prefix}_{response_id}_{output_index}"` 生成 id，同一个 item 的 `added` 与 `done` 走同一个 `output_index`，**所以客户端今天拿到的 id 是连续的**。本腿改 native 之后，客户端拿到的是上游那份实测 12/12、16/16、125/125 全不相同的 id（[spec.md](spec.md) §6.2）。

**为什么这是回归而不只是「行为变化」**：用户在 `docs/.human-controlled/config.example.yaml` 的 `hook_fix_responses_sse` 段具名写着「`@ai-sdk/openai` 校验 ID 连续性需要」。所以已知**至少有一类客户端**今天在这条腿上能跑、透传落地后会被它自己的校验拒掉。

**分叉**：是否在启用透传的**同一刀**里提供 opt-in 的 `fix_stream_ids`（默认关），还是先落 native、把兼容开关留作后续。[spec.md](spec.md) §6.2 已裁定这类变换必须另立显式、可选的 reshape 合同、不得叫它 native——**方向没有分歧，分歧只在时点**。

**未核**：`@ai-sdk/openai` 具体在哪个版本、以何种方式校验连续性。本项目没有它的源码，采纳的是用户的陈述。

**出处**：[`reports/260831-review-spec-round8.md`](reports/260831-review-spec-round8.md) round8-02。

## D-4　Anthropic 直连腿的 thinking signature 整形默认开着，走 native 会拿掉它

**状态**：产品分叉，等裁决。**比 D-3 严重，因为它默认生效、且落在主路径上。**

**事实**：`hook_fix_anthropic_sse.thinking.content_block_start_compat` 的默认值是 `"signature_delta"`（`src/app/config/schema.py`），`framer_for` 把它交给 `AnthropicFramer`，于是**今天每一条 Anthropic 腿都在做这个整形**——把嵌在 `content_block_start` 里的 thinking signature 抽成单独的 `signature_delta` 事件。纯透传按构造不做任何整形，接线后它就没了。

**为什么落在主路径上**：`sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` 记着实测，`claude-sonnet-5` 不支持 Responses API（`unsupported_api_for_model`），**Claude 系模型只能走直连**。所以这不是某条边角腿的行为变化。

**用户已经表过态，但表的是倾向不是裁决**：`docs/.human-controlled/message-format-reshape.md`「改写上游 Anthropic Messages 输出」一节逐字写着「曾经用 `hook_fix_anthropic_sse.thinking.content_block_start_compat` 配置控制生效，现在我认为（如果客户端真的不支持）这是应该常驻的」，并挂着两个 TODO：确认 Claude 新版是否接受嵌入形式，以及了解 copilot-api-js 原项目怎么处理。**倾向是「常驻」，方向与「拿掉」相反。**

**本规格已裁的部分**（[spec.md](spec.md) §2.7）：接线**不得**改变任何一条腿今天已生效的整形默认值。所以这条不阻塞接线——接线后 `signature_delta` 仍然开着。

**仍待裁的部分**：这个整形长期该以什么形态存在。§6.2 的模式是「另立显式、可选的 reshape 合同，不得叫它 native」；用户的倾向是「常驻」。两者不矛盾（常驻的合同也还是合同），但「默认开、可关」与「常驻、不可关」是两种不同的对外承诺，得由用户定。

**未核**：Claude 新版是否真的不接受嵌入 signature 的形式——这正是用户自己挂的第一个 TODO。整形是否仍然必要取决于它。

**出处**：本轮扩大定义域时发现（[spec.md](spec.md) §2.7）；与 D-3 是同一形状的两例。


## D-5　native 腿上的 hand-over 长什么样——Anthropic 直连腿的接线卡在这里

**状态**：需用户裁形态。**方向不待定，待定的是怎么做。**

**事实**：`max_tokens` 的 hand-over 是 2026-08-21 的用户裁决（「总是 hand over」），`hand_back_block()` 开头那句 `wire_format is not WireFormat.ANTHROPIC_MESSAGES` 按 inbound 格式门控，**Anthropic 直连腿今天就放行**。它合成一个 `tool_use` 块交给客户端继续，而那个块必须落在终局**之前**才是一份合法回复。

**冲突有两层，顺序只是浅的那层。**

**顺序，且不限于 `block`。** 本规格把上游自己的终局事件当作终局释放（[spec.md](spec.md) §5 提交表「无 item 的 terminal／failure」那一行），而交付循环冲刷缓冲发生在 `_hand_over` 判定之前，**对三种 policy 一视同仁**。此前这里写成「`block` 下它早已出门」，把范围写窄了——那会让下面的候选 1 被做成半个修复。

**类型，这一层更硬。** `_hand_over` 把合成的 `CompletedBlock` 交给 `framer.block()`，而透传 framer 只认 `RawEventBatch`（它调 `batch.encode()`）。**即使顺序解决了，那条路径仍是一次 200 之后的 `AttributeError` 撕流。**

**为什么这挡住接线而不是被绕过**：[spec.md](spec.md) §2.7 裁定接线不得改变任何一条腿今天已生效的行为，而这条腿是 Claude 系模型唯一的路（`claude-sonnet-5` 不支持 Responses API）。关掉 hand-over 就是回归主路径。

**三个候选，我倾向第二个**：

1. **hand-over 可能发生时推迟终局的释放**——保住顺序，代价是终局多等一个判定，且这份延迟对所有 Anthropic 直连请求都存在，即使绝大多数不 hand over。**它只解决顺序那一层**，类型那一层原样还在，所以单独采纳它做不出可用的实现。
2. **合成块以该方言的原生事件表达并接在终局之前**——`AnthropicFramer` 本来就会写这套事件，透传 framer 的 `error` 与 `keepalive` 正是这么委托的，机制现成；要解决的是「终局已发出」，可能需要把终局的释放与 hand-over 判定合并成一个决策点。**代价最小，且与既有委托模式一致。**
3. **裁定 native 腿不提供续写**——与 §2.7 冲突，是一次明确的行为回归，须用户裁。

**Responses 直连腿不受此条阻挡**：§8 的原判据在那条腿上成立（客户端执行不了 Anthropic 的合成块），`hand_back_block()` 的 inbound 格式门也不放行它。issue #2 与 #3 都在那条腿上，接线照常。

**出处**：[spec.md](spec.md) §2.8（本主题的 Spec，不是 plan——plan 只有 §1～§9）。放宽定义域时才暴露——§8 那句限定此前写得比它成立的范围宽。


## D-6　Anthropic 直连腿缺一份 failure → `RetryReason` 的映射表

**状态**：已知缺口，**不需要用户裁决**——它是本规格的推导层（§2.3），缺的是工作不是决定。

**事实**：[spec.md](spec.md) §5.2 的归一化表是本规格里**唯一**规定「怎么算一次原生失败可不可以 replay」的地方，而它的四个输入全是 `ResponseError.code` 的取值（`response.cancelled`、`server_error`、`rate_limit_exceeded`、`vector_store_timeout`），依据写明是「`openai==3.3.1` 的 `ResponseError.code` 是 20 成员 `Literal`」。

**Anthropic 的错误事件没有 `code` 字段**。它的形状是 `{"type":"error","error":{"type","message"}}`，判别字段是 `error.type`，取值是 `overloaded_error`／`rate_limit_error`／`api_error` 这一族——这一点来自本仓自己的 `anthropic_failure_from` 实现，不是记忆。所以 §5.2 那张表对 Anthropic 直连腿**一行都不适用，也没有任何对应表**。

**为什么此前没人登记**：§2.5 曾断言 §5～§10「句子里没有一个 Responses 专有的事实」，而那句话正是 v10 放宽定义域时用来说明「代价可控」的唯一论据。论据被证伪（v14 已改），这件工作才显出来——它一直存在，只是被一句全称否定挡住了。

**射程**：只影响 Anthropic 直连腿，而那条腿本来就挡在 D-5 上未接线，所以不阻塞当前工作。但它是 D-5 闭合之后**紧接着**要做的事，不是可选项——没有这张表，那条腿上一次可重试的上游失败不会被重试。

**未核**：Anthropic `error.type` 的取值全集，我没有对着官方文档逐条核。这不影响「需要两张表」这个结论，只影响那张表怎么填。

**出处**：[`reports/260831-review-spec-round9.md`](reports/260831-review-spec-round9.md) round9-02。
