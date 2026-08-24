# 错误信封：延后项台账

**这份是活文档**，**只放未闭合项**。查清、决定或做掉的条目从这里移出，并入 [spec.md](spec.md)、[plan.md](plan.md) 或代码注释，移出时带上出处。编号是标识不是序列，移走后不补号。

权威是 [spec.md](spec.md) 的**当前版本**（它也是活文档，不冻结）。本台账不新增规范，只登记它排除或推迟的东西，使其不被静默删掉。**本台账不得成为绕开 Spec 的去处**——Spec 级的事实一律落在 Spec 里，已知错误的条款当场修订，不在这里登记待办。2026-08-24 的 E-9 就是按这条撤销并入 spec.md §6.2/§6.3 的：当时那份 Spec 的文件头自己就写着「推导出的映射表走评审共识而非用户裁决」，授权本来就在，我却把修正登记到了这里。

建立于 2026-08-23，依据 Spec §10.2（「实施时建立」）与 §11（每条登记）。

## E-1　Chat Completions 流式腿没有合法的 error carrier —— 用户裁决推迟

**状态**：用户 2026-08-23 明确裁决推迟，不在本切片内实现。
**事实**：inbound 是 Chat Completions 且流式时那条腿没有 framer，写不出任何错误帧。守卫触发或上游撕裂时，客户端拿到的是**已到达的上游字节 + 连接裸断**（`more_body` 停在 `True`，无终止 chunk），SSE 层面没有任何事件说明发生了什么，`data: [DONE]` 的缺席是唯一线索。实测 69 字节送达。
**后果**：Spec §7「流式与非流式表达同一件事」对这条腿**带例外**。这条台账是该例外的授权记录。
**关联**：它与「给 Chat Completions 找块边界」是同一件工作，那件此前已被推迟过。
**顺带要修的**：`inference.py` 里那句注释说守卫触发时客户端拿到空 body——**与实测不符**，实测拿到的是已到达的上游字节。注释随计划的 J 片或 F 片修正，修完这半从本条移出。

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

## E-6　可观测性面与线路对同一事件给出两种说法

**状态**：Spec §11 排除（不改可观测性面）。
**事实**（清点 §6.1，实测）：客户端截止时间到期那一例，线路上写的是 `client_deadline_exceeded`，而完成日志行写的是「upstream stream ended without a terminal event」。成因是 `stream.py:364` 是 `return` 而非 `raise`，于是 `_tracked_delivery` 把它记成 `drained`。
**为什么值得留着**：一个读日志的人和一个读线路的人会得出不同结论，而这正是本项目花力气拉开的那类区分。

## E-7　`ResponsesAssembler` 不读 `output_item.done` 里的 content

**状态**：与错误面无关，Spec §11 登记。
**事实**（清点 §10.4，顺带实测）：上游 `output_item.done` 里带 `"text":"hello"`，重新成帧后 `output_text.delta` 与 `done` 都是空串——assembler 只从 delta 累积，不读 `done` 里的 content。

## E-8　上游流内失败事件的登记定级需要重评 —— **已闭合**

**闭合于**：2026-08-24，R 片落地（主仓 `f12f76d`）。
**当时登记的是什么**：`.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条把这件事描述为「客户端收到的与撕裂产生的帧不可区分」。自 2026-08-22 干净 EOF 改动落地后那句就不成立了——现状是**与成功不可区分**，代价比登记时重。
**现在是什么**：上游的失败事件不再被吞。直连腿原样重放上游自己的事件名与 payload，翻译腿过 IR 后按客户端方言写出，两条腿都不再以正常终结收尾。
**还剩的一半**：那一份台账的第 4 条本身仍需按新事实改写，它不归本主题。

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

## E-11　完成日志行与线路对同一次失败给出两种说法

**状态**：新登记，2026-08-24，随 K 片。**未闭合**，需要决定改不改可观测性面。

**事实**：`[FAIL] … 400 POST /v1/messages` 那一行的尾巴取自 `str(UpstreamRejected)`，也就是 `model_provider/ghc_client/errors.py` 里 `f"upstream rejected the request: {error}"` —— `{error}` 是 SDK 的 `__str__`，形如 `Error code: 400 - {'error': {...}}`（Python `dict` 的 repr，单引号、不可解析）。而客户端收到的 `message` 自 J 片起就由本项目自己构造，K 片之后在上下文超限这一格更是**完全不同的句子**（`prompt is too long: …`）。

**为什么值得留着**：Spec §4.5 花了力气把 wire 上的 `message` 从 SDK 的 `__str__` 里拆出来，理由是「本项目没有一处代码知道自己在往里放什么」——那个理由对日志行同样成立，而日志行至今还在用它。**这正是用户 2026-08-24 报来的那条记录的形态**：用户看到的是 SDK repr，客户端拿到的是另一句话，两者都为真却读不出对方。

**与 E-6 的关系**：同一类问题的第二例（E-6 是客户端截止那一格）。若要一并处理，判据应当是「完成行的失败说明取自 `ErrorInfo.message`」，而不是逐格打补丁。

## E-12　流内报告的失败不产生 `condition`

**状态**：新登记，2026-08-24，随 K 片与两份评审。**未闭合**，等一份真实样本。

**事实**：`condition` 只由 `_from_upstream` 产生，也就是上游以非 2xx HTTP 响应报告失败的那一格。两个流内 reader（`anthropic_messages` 的 `event: error`、`openai_responses` 的 `response.failed` / `response.cancelled`）各自直接构造 `ErrorInfo`，不经过条件判定；`OpenAIResponsesFramer.error()` 也直接写 `info.code`，不走按方言的条件拼写。

**为什么现在不做**：48 例上下文超限**全部**是建流前 400，没有任何一例以流内事件到达。客户端那一侧倒是够得着——它的 `prompt is too long` 判据没有状态码门，流内错误帧上同样生效（实测，`reports/260824-claude-code-context-limit-detection.md` §2.2）——但「客户端认得」不等于「上游会这么发」，据后者建映射就是替上游发明错误。与 E-10 同一条理由。

**Spec 侧已处理**：§5.5.4 明确把定义域收窄到 HTTP 错误 body，所以这不是 Spec 与实现不一致，而是一处**已登记的范围限制**。两份评审（`reports/260824-context-condition-spec-review.md` CCSR-03、`reports/260824-context-condition-code-review.md` F-12）对它的定级不同（major 对 nit），分歧点正是「Spec 该不该主张全路径覆盖」——收窄 Spec 使两者归一。

**闭合条件**：拿到一份真实的流内上下文超限样本；届时两个 reader 复用同一条件判定，`OpenAIResponsesFramer.error()` 复用同一按方言拼写。
