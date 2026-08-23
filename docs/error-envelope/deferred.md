# 错误信封：延后项台账

**这份是活文档**，**只放未闭合项**。查清、决定或做掉的条目从这里移出，并入 [spec.md](spec.md)、[plan.md](plan.md) 或代码注释，移出时带上出处。编号是标识不是序列，移走后不补号。

权威是冻结的 [spec.md](spec.md)。本台账不新增规范，只登记它排除或推迟的东西，使其不被静默删掉。

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

## E-8　上游流内失败事件的登记定级需要重评

**状态**：已在 Spec §3.5 与计划 R 片内，**本条只登记「另一处台账的定级过时了」**。
**事实**：`.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条登记的是同一件事，但登记时的描述是「客户端收到的与撕裂产生的帧不可区分」。自 2026-08-22 干净 EOF 改动落地后，现状是**与成功不可区分**——代价变了，定级要跟着变。
**闭合条件**：R 片落地后，回去更新那条台账并把本条移出。
