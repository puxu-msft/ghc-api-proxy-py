# 错误信封：延后项台账

**这份是活文档**，**只放未闭合项**。查清、决定或做掉的条目从这里移出，并入 [status.md](status.md)、[spec.md](spec.md)、[plan.md](plan.md) 或代码注释，移出时带上出处。编号是标识不是序列，移走后不补号。

权威是 [spec.md](spec.md) 的**当前版本**（它也是活文档，不冻结）。本台账不新增规范，只登记它排除或推迟的东西，使其不被静默删掉。**本台账不得成为绕开 Spec 的去处**——Spec 级的事实一律落在 Spec 里，已知错误的条款当场修订，不在这里登记待办。2026-08-24 的 E-9 就是按这条撤销并入 spec.md §6.2/§6.3 的：当时那份 Spec 的文件头自己就写着「推导出的映射表走评审共识而非用户裁决」，授权本来就在，我却把修正登记到了这里。

建立于 2026-08-23，依据 Spec §10.2（「实施时建立」）与 §11（每条登记）。

## E-1　Chat Completions 流式腿没有合法的 proxy error carrier —— 用户裁决继续推迟

**状态**：用户2026-08-23明确推迟Chat streaming proxy error frame；2026-09-05～06又明确裁定terminal-only buffer在semantic commit前必须transparent retry。前者仍未实现，后者已经进入 [spec.md](spec.md) §8／§10.2 与 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §5.4，不能继续停在本台账。
**剩余事实**：inbound是Chat Completions且streaming时仍没有framer，pre-`[DONE]`最终无法恢复时写不出本代理自己的error frame。Replay不适用、被draining拒绝、预算耗尽或replacement未建立后，客户端得到仍保留的最终候选attempt partial bytes + 连接裸断；成功replacement取代的attempt不得泄漏。`[DONE]`缺席是截断线索，但现在先触发retry，不再直接触发fallback。第一个 `[DONE]` 后semantic success已冻结，tail ending按Spec提交成功body，不属于本条error-carrier缺口。
**本条只剩什么**：是否为Chat streaming建立合法proxy error carrier，以及是否改为真正按推断block边界增量交付。Terminal-only whole-attempt replay不依赖这两个能力，已经不属于延后项。
**关闭条件**：用户重开carrier裁决并选定Chat streaming error形状，或明确永久接受partial+naked-close作为最终carrier；若同时要求block delivery，再按direct-passthrough的独立合同处理。
**已闭合旁支**：2026-08-27已修正 `inference.py` 关于空body的错误注释；2026-09-06 living Specs已把fallback与transparent replay的先后关系写准。完整设计见 [`../direct-buffered-chat-completions/design.md`](../direct-buffered-chat-completions/design.md)。

## E-2　框架自身的 404 / 405 用另一种信封

**状态**：Spec §11 排除，不在射程内。
**事实**：未注册路径与方法不匹配由 Starlette 直接答 `{"detail":"Not Found"}` / `{"detail":"Method Not Allowed"}`，与本项目的 `{"error":{...}}` 不同形。同一个 app 里因此有两种信封，客户端要按 `error` / `detail` 两个键试探。
**为什么排除**：改它要接管 Starlette 的异常处理；而且未注册路径没有 route，推不出 `inbound_format`，「按客户端方言渲染」在那里没有定义域。
**重开条件**：若将来要求单一信封，需要先决定无 route 时用哪种方言作 fallback。

## E-3　响应头黑白名单的内容本身

**状态**：Spec §11 排除。
**事实**：名单由用户亲笔的 `docs/.human-controlled/message-format-reshape.md`「客户端返回 Anthropic Messages」一节规定。Spec 引用它、不改写它。
**已澄清的一点**：该节原文**不区分成功与错误响应**。Spec v2 曾自行加上「只为成功响应」这个限定，v3 删除——错误响应沿用同一份直连黑名单。

## E-4　Gemini 成功请求的 wire 翻译

**状态**：Spec §11 排除；Gemini 的**错误**信封在射程内（Spec §9，计划 J 片）。
**事实**：Gemini 三条路径今天答 501。实现要点与旧实现的落点在 `.dev/docs/server-layout/deferred.md` §D-A。

## E-5　`app/errors.py` 里 `ApiError` / `classify_error` 的去留

**状态**：Spec §11 排除，登记为独立的归档判断。
**事实**：两者只被 `models/common.py` 与 `streaming/sse.py` 使用，而那两处在当前链路上没有路由消费。`ErrorCategory` 与 `WIRE_TYPES` 则相反——`stream.py` 与 `hand_over.py` 都在用。
**注意**：计划的 I 片会改 `ErrorCategory` 与那张表，**但不动 `ApiError`**。若 I 片之后 `ApiError.wire_type` 因表结构变化而失效，本条要立刻重评而不是顺手删——「暂不支持不是删代码授权」。

## E-7　`ResponsesAssembler` 不读 `output_item.done` 里的 content

**状态**：与错误面无关，Spec §11 登记。
**事实**（清点 §10.4，顺带实测）：上游 `output_item.done` 里带 `"text":"hello"`，重新成帧后 `output_text.delta` 与 `done` 都是空串——assembler 只从 delta 累积，不读 `done` 里的 content。

## E-9　上游报告失败时是否也该先给 hand-over

**状态**：新登记，2026-08-24，随 R 片。**未闭合**，需要产品裁决。

**事实**：干净 EOF 且 `unterminated_stream_stop_reason` 为空时，失败会**先交给 hand-over**——客户端拿到一个 `turn_interrupted` 工具调用，可以继续这一轮。而上游**明确报告**失败时（R 片新接的这条路），走的是错误帧／原样重放，不经过 hand-over。

**为什么现在这样**：Spec §3.4 对直连腿的要求是「原样重放上游的事件名与完整 payload」，hand-over 会取而代之，两者不能同时满足。所以这不是漏做，是 Spec 当前条款的直接结果。

**为什么仍值得裁**：两种失败对客户端的价值不同——一个能继续，一个只能重来——而区分它们的是「上游有没有说话」，不是「客户端能不能继续」。翻译腿上没有原样重放的约束，那一侧尤其可以两者兼得。

**闭合条件**：用户裁定上游报告的失败是否也应先经 hand-over；若是，需同时裁定直连腿上它与 §3.4 的优先级。

## E-10　上游条件「input length and max_tokens exceed context limit」未映射

**状态**：新登记，2026-08-24，随 K 片。**未闭合**，等一份真实样本。

**事实**：主产品路径上的客户端对这条措辞另有一套自愈——不是压缩历史，而是**算出可用余量后改小 `max_tokens` 重发**，且要求 HTTP status 恰为 400 并从消息里抠出 `A + B > C` 三个数字（实测 Claude Code 2.1.241 `B9f`，见 [reports/260824-claude-code-context-limit-detection.md](reports/260824-claude-code-context-limit-detection.md) §5.2）。它与 `CONTEXT_WINDOW_EXCEEDED` 是**两件不同的事**：一件是历史太长，一件是「历史 + 你要的输出长度」加起来太长，后者改个参数就能过。

**为什么现在不做**：本机 145,781 个 operation 里这条措辞**零命中**，Copilot 两条腿都没观察到等价条件。凭一份客户端能力去反推一个上游从没发过的条件，等于替上游发明错误——而三个数字里的 `A`（当前输入）本代理拿不到，只能估，`app/errors.py` 的 `prompt_limit_counts` 旁边那条禁令同样适用。

**闭合条件**：拿到一份真实上游 body（Copilot 或其它上游）确实这样报告；届时它是 `UpstreamCondition` 的第二个成员，并需要同时为它补上 §5.5.2 的按方言拼写。

## E-12　流内报告的失败不产生 `condition`

**状态**：新登记，2026-08-24，随 K 片与两份评审。**未闭合**，等一份真实样本。

**事实**：`condition` 只由 `_from_upstream` 产生，也就是上游以非 2xx HTTP 响应报告失败的那一格。两个流内 reader（`anthropic_messages` 的 `event: error`、`openai_responses` 的 `response.failed` / `response.cancelled`）各自直接构造 `ErrorInfo`，不经过条件判定；`OpenAIResponsesFramer.error()` 也直接写 `info.code`，不走按方言的条件拼写。

**为什么现在不做**：48 例上下文超限**全部**是建流前 400，没有任何一例以流内事件到达。客户端那一侧倒是够得着——它的 `prompt is too long` 判据没有状态码门，流内错误帧上同样生效（实测，`reports/260824-claude-code-context-limit-detection.md` §2.2）——但「客户端认得」不等于「上游会这么发」，据后者建映射就是替上游发明错误。与 E-10 同一条理由。

**Spec 侧已处理**：§5.5.4 明确把定义域收窄到 HTTP 错误 body，所以这不是 Spec 与实现不一致，而是一处**已登记的范围限制**。两份评审（`reports/260824-context-condition-spec-review.md` CCSR-03、`reports/260824-context-condition-code-review.md` F-12）对它的定级不同（major 对 nit），分歧点正是「Spec 该不该主张全路径覆盖」——收窄 Spec 使两者归一。

**闭合条件**：拿到一份真实的流内上下文超限样本；届时两个 reader 复用同一条件判定，`OpenAIResponsesFramer.error()` 复用同一按方言拼写。
