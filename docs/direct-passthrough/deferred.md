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

## D-4　Anthropic 直连腿的 thinking signature 整形默认开着，走 native 会拿掉它

**状态**：产品分叉，等裁决。**比已由 Spec §6.6 闭合的 Responses id reshape 更严重，因为它默认生效、且落在 Claude 模型的关键可达 route 上。**

**事实**：`hook_fix_anthropic_sse.thinking.content_block_start_compat` 的默认值是 `"signature_delta"`（`src/app/config/schema.py`），`framer_for` 把它交给 `AnthropicFramer`，于是**今天每一条 Anthropic 腿都在做这个整形**——把嵌在 `content_block_start` 里的 thinking signature 抽成单独的 `signature_delta` 事件。纯透传按构造不做任何整形，接线后它就没了。

**为什么射程重要**：`sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` 记着实测，`claude-sonnet-5` 不支持 Responses API（`unsupported_api_for_model`），该模型只能走直连。所以这不是某条边角腿的行为变化；但项目定义的 primary product path 仍是 Anthropic Messages inbound → OpenAI Responses upstream，不把两者混称。

**用户已经表过态，但表的是倾向不是裁决**：`docs/.human-controlled/message-format-reshape.md`「改写上游 Anthropic Messages 输出」一节逐字写着「曾经用 `hook_fix_anthropic_sse.thinking.content_block_start_compat` 配置控制生效，现在我认为（如果客户端真的不支持）这是应该常驻的」，并挂着两个 TODO：确认 Claude 新版是否接受嵌入形式，以及了解 copilot-api-js 原项目怎么处理。**倾向是「常驻」，方向与「拿掉」相反。**

**本规格已裁的部分**（[spec.md](spec.md) §2.7）：接线**不得**改变任何一条腿今天已生效的整形默认值。所以这条不阻塞接线——接线后 `signature_delta` 仍然开着。

**仍待裁的部分**：这个整形长期该以什么形态存在。§6.2 的模式是「另立显式、可选的 reshape 合同，不得叫它 native」；用户的倾向是「常驻」。两者不矛盾（常驻的合同也还是合同），但「默认开、可关」与「常驻、不可关」是两种不同的对外承诺，得由用户定。

**未核**：Claude 新版是否真的不接受嵌入 signature 的形式——这正是用户自己挂的第一个 TODO。整形是否仍然必要取决于它。

**出处**：本轮扩大定义域时发现（[spec.md](spec.md) §2.7）；与已由 Spec §6.6 闭合的 Responses id reshape 是同一形状的两例。


## D-5　让 continuation 在当前两种 block-aware 直连生成方言上原生可用——Anthropic 直连腿的接线等它

**状态**：**已裁，已进入 [`plan.md`](plan.md) §11，待做**。用户 2026-09-01：「该功能理应在直连路径上正确可用，因为块级交付是直连、翻译都必须全面、原生支持的」。这条否掉了下面的候选 3，并把候选 2 定为要做的事。此前这里写的是「需用户裁形态」——现在形态也裁完了，Spec v22 已闭合共同 intent、streaming／whole-body finalization 与 native failure 动作矩阵，剩下的是实施。

**事实**：`max_tokens` 的 hand-over 是 2026-08-21 的用户裁决（「总是 hand over」），`hand_back_block()` 开头那句 `wire_format is not WireFormat.ANTHROPIC_MESSAGES` 按 inbound 格式门控，**Anthropic 直连腿今天就放行**。它合成一个 `tool_use` 块交给客户端继续，而那个块必须落在终局**之前**才是一份合法回复。

**冲突有两层，顺序只是浅的那层。**

**顺序，且不限于 `block`。** 本规格把上游自己的终局事件当作终局释放（[spec.md](spec.md) §5 提交表「无 item 的 terminal／failure」那一行），而交付循环冲刷缓冲发生在 `_hand_over` 判定之前，**对三种 policy 一视同仁**。此前这里写成「`block` 下它早已出门」，把范围写窄了——那会让下面的候选 1 被做成半个修复。

**类型，这一层更硬。** `_hand_over` 把合成的 `CompletedBlock` 交给 `framer.block()`，而透传 framer 只认 `RawEventBatch`（它调 `batch.encode()`）。**即使顺序解决了，那条路径仍是一次 200 之后的 `AttributeError` 撕流。**

**为什么这挡住接线而不是被绕过**：[spec.md](spec.md) §2.7 裁定接线不得改变任何一条腿今天已生效的行为，而这条腿是 `claude-sonnet-5` 的唯一可达 route（它不支持 Responses API）。关掉 continuation 就是该关键 route 的行为回归。

**三个候选，用户 2026-09-01 已裁：走第二个。**候选 3 被明确否掉，因为它与「块级交付两条路都必须原生支持」相反。

1. **hand-over 可能发生时推迟终局的释放**——保住顺序，代价是终局多等一个判定，且这份延迟对所有 Anthropic 直连请求都存在，即使绝大多数不 hand over。**它只解决顺序那一层**，类型那一层原样还在，所以单独采纳它做不出可用的实现。
2. **合成块以该方言的原生事件表达并接在终局之前**——`AnthropicFramer` 本来就会写这套事件，透传 framer 的 `error` 与 `keepalive` 正是这么委托的，机制现成；要解决的是「终局已发出」，可能需要把终局的释放与 hand-over 判定合并成一个决策点。**代价最小，且与既有委托模式一致。**
3. ~~**裁定 native 腿不提供续写**~~——**用户已否**。它与 §2.7 冲突，也与「块级交付必须在两条路上全面支持」相反。

**Responses 直连腿已经接线，但 continuation 同样未完成**：`hand_back_block()` 的 inbound 格式门今天不放行 Responses，只说明旧实现仍返回 Anthropic 专用 dict，不能把尚未实现读成永久豁免。用户后续裁决覆盖直连与翻译的块级交付路径；Spec v22 §2.6 将当前 applicability 明确为能识别完整生成单位并能表达 executable synthetic call 的 Anthropic Messages 与 OpenAI Responses，两者共享 semantic decision。Chat Completions 的块级解析仍按 2026-08-22 裁决推迟，Embeddings 不是生成回合；D-5 不冒充它们已经有 continuation。

**完成边界**：D-7 message count、D-6 两方言 failure adapter、streaming／whole-body finalization、native side facts、当前 `signature_delta` reshape 与 Anthropic selector 真实接线全部属于 D-5 对外完成边界；它们可以分成独立 semantic commits，不能因先后落地就把后做的一项降为“接线之后再补”。关闭 D-5 只声明当前两种 applicable 方言完成，不关闭 Chat Completions 的独立块级欠项。

**出处**：[spec.md](spec.md) §2.8、§5.3、§9.2 与 [`plan.md`](plan.md) §11。放宽定义域时才暴露——§8 那句限定此前写得比它成立的范围宽；2026-09-03 根修分析及独立复评把完整依赖闭包补齐。


## D-6　Anthropic 直连腿缺一份 failure → `RetryReason` 的映射表

**状态**：已知缺口，**不需要用户裁决，已进入 [`plan.md`](plan.md) §11.6**——它是本规格的推导层（§2.3），缺的是工作不是决定。

**事实**：[spec.md](spec.md) §5.2 的归一化表是本规格里**唯一**规定「怎么算一次原生失败可不可以 replay」的地方，而它的四个输入全是 `ResponseError.code` 的取值（`response.cancelled`、`server_error`、`rate_limit_exceeded`、`vector_store_timeout`），依据写明是「`openai==3.3.1` 的 `ResponseError.code` 是 20 成员 `Literal`」。

**Anthropic 的错误事件没有 `code` 字段**。它的形状是 `{"type":"error","error":{"type","message"}}`，判别字段是 `error.type`，取值是 `overloaded_error`／`rate_limit_error`／`api_error` 这一族——这一点来自本仓自己的 `anthropic_failure_from` 实现，不是记忆。所以 §5.2 那张表对 Anthropic 直连腿**一行都不适用，也没有任何对应表**。

**为什么此前没人登记**：§2.5 曾断言 §5～§10「句子里没有一个 Responses 专有的事实」，而那句话正是 v10 放宽定义域时用来说明「代价可控」的唯一论据。论据被证伪（v14 已改），这件工作才显出来——它一直存在，只是被一句全称否定挡住了。

**射程与顺序**：它直接影响 Anthropic 直连腿，也决定 Spec v22 §5.3 的 native failure 三向动作矩阵能否执行。D-6 不是 D-5 闭合之后的后续清理，而是 D-5 对外完成与 Anthropic selector 启用的前置；实现仍可形成独立 semantic commit，commit 顺序不等于完成依赖。没有这张表，那条腿上一次可重试的上游失败既不会 replay，也无法在已保留完整单位后正确选择 continuation。

**未核**：Anthropic `error.type` 的取值全集，我没有对着官方文档逐条核。这不影响「需要两张表」这个结论，只影响那张表怎么填。

**出处**：[`reports/260831-review-spec-round9.md`](reports/260831-review-spec-round9.md) round9-02。


## D-7　`client_message_count` 只读 `messages`，Responses 请求会得到 0

**状态**：已知缺陷，**不需要用户裁决，已进入 [`plan.md`](plan.md) §11.2**——用户文档已经指定了正确行为，这是实现只做了一半。

**事实**：`src/app/pipeline/hand_over.py` 的 `client_message_count` 是 `payload.get("messages")`，非 list 就返回 `0`。而用户亲笔文档写的是「`num_messages` 是客户端请求中 **`messages` / `input`** 的长度」——`input` 是 Responses 请求的字段名。所以一个 Responses 请求走到续写时，这个数是 0。

**为什么这不只是数字难看**：同一句话说明了它的用途——「**用于检测和避免无进展的重试循环**」。恒为 0 的计数让客户端侧那个检测器失去输入，两次续写在它看来完全一样。

**射程**：今天不可达（续写按 inbound 格式门控，Responses 请求根本走不到这里），但它会在 D-5 落地的同一刻变成可达——所以它属于那项工作，不是它之后的清理。

**出处**：用户 2026-09-01 裁决续写须在直连腿可用时顺带照出；文档指定与实现的差距见 [spec.md](spec.md) §2.8。

## D-9　Codex 在直连腿上「结果重复输出」，成因未查明

**状态**：**未闭合的缺陷调查**，不需要用户裁决——需要的是把成因找出来。

**编号说明**：跳过 D-8。那个号曾短暂用于「已污染的客户端历史要不要剥离」，随即因归属错误移入 [spec.md](spec.md) §11 O-2 并删号；按本台账开头的规矩，**移走的号不补**。

**症状**：用户 2026-09-02 报告，Codex CLI 经本代理 `/responses` 直连腿与 Copilot 对话时，同一段回答会重复输出。出现在 `1fb37cd`（该腿改为原生透传）之后；此前走翻译腿时正常。

**已排除的解释，每条都有硬证据**：

| 假设 | 结论 | 证据 |
|---|---|---|
| item id／`response.id` 漂移导致客户端拆分 item | **证伪** | Codex `0.144.1` 用单槽 `active_item`（`added` 置位、`done` 取走），其事件结构体不解析 `output_index`，delta 分支只取 `delta`，`response.completed` 只读 `{id, usage, end_turn}`。针对用户实际二进制的定向探针 8/8 命中、2/2 负控制落空 |
| 客户端把 `output_text.delta` 与 `output_item.done` 各渲染一次 | **证伪** | 实测旧构建（翻译腿）同样发这两类事件，事件类型序列两边完全一致 |
| `response.completed` 携带 `output` 数组导致二次渲染 | **证伪** | 新旧两边都带；且 Codex 不读该字段 |

**出处**：[`reports/260902-codex-item-grouping-key.md`](reports/260902-codex-item-grouping-key.md)。

**成因形状已定位，2026-09-02**（[`reports/260902-duplicate-delivery-hunt.md`](reports/260902-duplicate-delivery-hunt.md)）：

**上游对同一个 `output_index` 发出第二个 `response.output_item.done`。** 穷举 207 个上游序列变异，能复现该症状的 21 个**无一例外**都是这一形状；其余路径逐事件计数确认每个上游事件恰好交付一次。

**代理侧不是「发两遍」，是「不再过滤两遍」**——方向与我最初的猜测相反。翻译腿把「关闭一个从未打开的 item」当空操作吞掉（`openai_responses.py`），直连透传逐字转发（`passthrough.py`）。所以行为变化是真的，且确由 `1fb37cd` 引入。

**Codex 侧机制已读源码核实**（非推断）：空槽收到 `done` → `stream_events_utils.rs` 补发 started+completed → `streaming.rs` 的 `finalize_completed_assistant_message` 第二次被调用时 `stream_controller` 已被 `take()`，于是把全文当普通内容再渲染一遍。

**最小复现**：普通 Responses 流，把最后那个 `output_item.done` 帧原样再发一遍。直连腿渲染两次，翻译腿一次。**与缓冲策略无关**。

**证据缺口，不掩饰**：**无法证明上游真的会这么发。** 三份真实录音各只有一次闭合事件；历史库自 2026-08-15 起不再存 frame；代理请求日志不含 body。所以触发条件里「上游重复发 `done`」这一条**未取证**，另两条（直连腿、单槽客户端）已知成立。

**已落地的处置：只观测，不动行为**（`e1d6676`）。`PassthroughAssembler` 本就维护着 `_closed`，「对已关闭的 `output_index` 再收到闭合事件」是一行可判的谓词，此前静默通过；现在记一条 warning。**为什么不直接丢弃那个重复事件**：丢弃会改变 native 腿的对外承诺（§2.1，正是这条腿存在的理由），而支撑它的只是一个未取证的猜测；一条日志零行为改动，且**一次真实会话即可判定**。

**下一步（等一次真实观测）**：用户下次用 Codex 跑一轮，若日志出现 `closed output_index N twice`，则触发条件三条齐备，此时再按 Spec 决定要不要过滤——**那是一次对外承诺的修改，须先改 Spec 并交用户裁定**。若始终不出现，则本条结论被证伪，须重开调查。

**已排除并记下的四条**（省得重走）：`synthesises_terminal` 的腿间分歧、Codex 解析 `ResponseCompleted.usage` 失败、replay 重发已交付事件、`until-tool-use` 双重释放。

**另一条便宜的可证伪实验**：只统一 `output_text.delta` 的 `item_id` 而不动 `added`／`done`，Codex 行为应当**零变化**——若观察到变化，说明对其解析器的理解仍有缺口。`b8fe245` 的 `fix_stream_ids` 合并后可直接做。

**为什么这条不是 §6.6**：§6.6 的 `fix_stream_ids` 服务的是 `@ai-sdk/openai`，与本条无关。**当时把两者接在一起是一次错误归因**，已在 §6.6 开头的警示框里更正。

**未核**：Codex 的 app-server IPC 转发层（`bespoke_event_handling.rs`）未逐行核查；上述结论只覆盖 assistant 文本路径，reasoning 与 tool call 的语义不同；全部来自源码阅读与字面量探针，非运行时观测。
