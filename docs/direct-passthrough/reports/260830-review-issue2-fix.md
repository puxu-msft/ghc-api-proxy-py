# issue #2 显式拒绝修复独立评审

- report_id：`review-issue2-fix`
- attempt_id：`260830-review-issue2-fix-1`
- status：`in-review`
- reviewed_at_rev：`621803c2d2d847cdbc15492b7503ff24b37f6ae2`
- base_rev：`78030df9e822efa554c753f78b15f785f0f9ca4c`
- reviewed_range：`78030df..621803c`，该区间恰好 1 个提交

## 评审范围

本次评审覆盖提交 `621803c` 相对 `main` 基线 `78030df` 的 5 个变更文件：`src/app/pipeline/delivery/assembling.py`、`src/app/pipeline/delivery/formats/openai_responses.py`、`src/app/pipeline/delivery/stream.py`、`src/app/server/routes/inference.py`、`tests/int/test_pipeline_app.py`。同时读取最终态的流式交付、错误 IR、非流式 registry 与两个 Responses→Anthropic converter 接缝，以核对 `StreamFailure.replayable` 全部构造/消费点、完成行归因、22/28 个 item type 的爆炸半径，以及流式/非流式等价性。

判据独立取自 `docs/.human-controlled/README.md`、`api.md`、`client-side-block-delivery.md`、`message-format-reshape.md`、`message-translation.md`、`request-pipeline.md`、`upstream-retry-and-continuation.md`，以及 `.dev/docs/anthropic-responses-bridge/spec.md`、`.dev/docs/error-envelope/spec.md`、`.dev/docs/tmp/260830-custom-tool-call-forensics.md`、`.dev/docs/direct-responses-passthrough/plan.md` 与其 `reports/260830-review-plan.md`。在读取被评提交之前先读取了这些判据；`direct-responses-passthrough/plan.md` 的既有评审锚定 `78030df`，本报告只把它当方案与既有评审材料，不把尚无 Spec 的候选直连合同当成现行产品合同。

明确不在范围内：修改 `src/` 或 `tests/`、真实 Copilot 上游调用、重新审计 openai SDK 3.3.1 的全部 28 个类型定义、为直连原生 passthrough 方案补 Spec 或实施。没有重跑作者所述的源码变异；该变异结果按调用方给定的一手执行记录引用，本报告另外用反例探针独立检查绿灯的负空间。

## 总体 verdict

**needs-fix。当前提交不可合并。** blocker 数：**0**。

正常 `added→done` 的未知顶层 item 已从撕流/空块改成合法客户端方言的 SSE error，且错误后不发成功 terminal，这一核心方向正确；但是拒绝只挂在“先成功打开 draft”的一条生命周期上，同一矩阵明确覆盖的 malformed lifecycle 与 unknown content part 仍会被空 body、空 text block或正常 terminal 掩盖。更直接地，同一个 `custom_tool_call` 在流式 translated 请求中失败、在非流式 translated 请求中仍返回 HTTP 200、`content: []`、`stop_reason: end_turn`；生产 registry 又没有接到已经实现 strict `_fail` 的 converter。三项 major 均是同一规范要求的实现闭合问题，而不是可留给下一刀而不影响本提交结论的旁支。

## 发现

### review-issue2-fix-01

- finding_id：`review-issue2-fix-01`
- severity：`major`
- primary_location：`src/app/pipeline/delivery/formats/openai_responses.py:545-608`
- related_locations：`src/app/pipeline/delivery/formats/openai_responses.py:448-500,516-533,649-658`；`tests/int/test_pipeline_app.py:2528-2583`；`.dev/docs/anthropic-responses-bridge/spec.md:188,223-236,303-316,329-350,370-383,433-440`
- 标题：显式拒绝只覆盖有 draft 的未知顶层 item，矩阵中另外两个同级拒绝面仍静默成功

**证据。** 新的 `UNKNOWN` 只在 `_open()` 建立 draft 后，由 `_close()` 第 584 行命中。若 `response.output_item.done` 没有对应 `added`，第 548～567 行会在判断 item 是否 `UNKNOWN` 之前直接 warning 后 `return ()`；我用合法 `custom_tool_call` item 构造只有 `done→response.completed` 的序列，经 `/responses` 与 `/v1/messages` 两条腿实跑，二者均为 HTTP 200、body 为空，完成行均为 `ok … end_turn`。这不仅是 malformed lifecycle，也是未知 output item，二重命中矩阵的 `REJECT`，却没有 error frame。

**第二个独立反例。** 对 `message` item 的未知 content part，assembler 只因顶层 `type=message` 选择 `TEXT`，从不检查 closing item 的 `content[]`；我构造 `done.content=[{"type":"future_part","value":"opaque"}]` 且没有 output-text delta 的完整 `added→done→completed` 序列。直连 Responses 腿实跑为一个合成的空 `output_text` item加 `response.completed`，translated Anthropic 腿实跑为 `content_block_start` 空 text、空 `text_delta`、`message_stop`，两条完成行都是 `ok … end_turn`。这正是 Spec 第 235 行逐字禁止的“unknown content part 由空 text block或正常 terminal 掩盖”。

**影响。** 当前测试证明的只是一条正常顶层 item lifecycle，不足以支撑注释所引用的整行矩阵；同一个 fail-closed 入口仍有两个结构性绕路。客户端继续可能把未转换的输出读成空成功，History/重放继续保存错误事实，运维完成行继续写 `ok`。

**建议。** 把 conversion refusal 提炼成 assembler 内唯一入口：没有 draft 的非救援 close 应按 malformed lifecycle 失败，而不是 drop；message closing item 必须按 authoritative `content[]` 校验 part 类型，或让流式路径共享 strict semantic converter。保留 `web_search_call`/有 client tool name 的 `tool_search_call` 这两个经 Spec 明定的 late rescue，不能把所有 done-only item 一概接受。新增 translated 与 direct 两条腿的 malformed、unknown part 反例测试；测试必须断言 error 后无成功 terminal，且无任何 content block/output item。

**证据强度。** 强到可直接行动：两个反例都在目标 commit、目标 worktree 的完整 ASGI 路径实跑复现，且输出逐字命中 Spec 禁止形态。

**承重前提检查。** 前提是“`UNKNOWN` 分支位于 `_close()` 就等于未知 item/content/lifecycle 都会到达它”；它支撑“本提交实现了矩阵的显式拒绝”。若前提为假，提交仍存在静默成功出口。两个实跑反例证明前提为假，因此本项为 major，并阻断当前合并。

### review-issue2-fix-02

- finding_id：`review-issue2-fix-02`
- severity：`major`
- primary_location：`src/app/pipeline/translation_driver/responses.py:156-207`
- related_locations：`src/app/pipeline/delivery/formats/openai_responses.py:392-397,584-608`；`src/app/pipeline/translation_driver/openai_responses.py:448-519,534-540`；`src/app/pipeline/translation_driver/registry.py:157-164`；`.dev/docs/anthropic-responses-bridge/spec.md:303-327,433-440`；`tests/int/test_pipeline_app.py:2528-2583`
- 标题：同一未知 response 在流式侧失败、非流式侧成功，违反明确的等价契约

**证据。** `from_openai_responses_response()` 第 195～200 行仍将 `BlockKind.UNKNOWN` 记为 `ITEM_NOT_CARRIED` 后继续，随后第 202～204 行从剩余 blocks 推出正常 `end_turn`。我把与新测试相同的 `custom_tool_call` 放入完整非流式 Responses body，经生产 registry 的 `/v1/messages` 路径实跑，得到 HTTP 200、`content: []`、`stop_reason: "end_turn"`；同一 item 的流式 translated 路径得到 Anthropic `event: error`，没有 `message_stop`。这是 Spec 第 305、327 行要求等价的 `content`、stop reason、degradation 与 error 中至少三项同时分叉。

**额外一致性证据。** 变更注释 `openai_responses.py:396` 逐字说“which is why `translation_driver/responses.py` changes with it”，但 `78030df..621803c` 的 name-status 与 diff 均显示该文件没有变化。注释描述了正确的原子边界，提交没有实现它。

**影响。** 客户端只切换 `stream` 就从明确 incompatibility error 变成成功空回答；这不是传输 envelope 的允许差异，而是相反的业务事实。空成功还会让调用方停止处理/重试并把不完整 turn 当成模型正常结束。

**建议。** 在本提交合并前让生产 non-stream reader 对未知 output item、unknown content part 与 malformed response 走同一 stable conversion error，且由 HTTP error writer 在 commit 前写客户端方言；为同一 fixture 增加 stream=false/true 的归一化结果对照。不要只删除那句错误注释，因为行为差异仍在。

**证据强度。** 强到可直接行动：生产路由的两种实际响应已并列实跑，且是 Spec 的逐字等价要求。

**承重前提检查。** 前提是“非流式现状可以作为下一刀，当前流式 patch 仍是闭合的语义单元”；它支撑“本次可先合并”。若前提为假，合并会把同一受支持端点的一个合同固化为两种相反答案。实跑已经证明相反答案存在，故第 7(a) 项定级为 major，并阻断本次合并。

### review-issue2-fix-03

- finding_id：`review-issue2-fix-03`
- severity：`major`
- primary_location：`src/app/pipeline/translation_driver/registry.py:157-164`
- related_locations：`src/app/protocols/responses_anthropic.py:65-141,153-204,342-347`；`src/app/pipeline/translation_driver/responses.py:156-207`；`tests/unit/protocols/test_responses_anthropic_nonstream.py:1-290`；`.dev/docs/anthropic-responses-bridge/spec.md:303-327,345-356,560-563`
- 标题：已经实现并测试的 strict response converter 没有生产调用者，registry 注册的是退化实现

**证据。** 全 `src/` 检索 `convert_responses_response_to_anthropic` 只有定义与 `__all__`，所有调用都在 `tests/unit/protocols/test_responses_anthropic_nonstream.py`；生产 `default_registry()` 明确注册 `from_openai_responses_response`。前者对 unknown output item、unknown content part、server-tool item、malformed arguments/usage 均调用 `_fail`；后者对 `BlockKind.UNKNOWN` 继续并记 loss。目标提交又在 streaming assembler 内新增第三份 unknown 判定，没有接到 Spec 第 305、354～355、560 行要求的 shared canonical semantic core。

**影响。** 严格 converter 的这一组绿测试不能证明任何生产 non-stream 请求满足对应行为；每次修复都可能只改三套实现中的一套。本次第 02 项不是偶发漏行，而是 registry 接到了另一套语义所有者的直接结果。

**建议。** 合并前裁定并实施唯一 production owner：优先让 registry reader 复用 `convert_responses_response_to_anthropic` 的 strict semantic core，并在边界适配成 `SemanticResponse`；若暂时不能替换类型，则至少把 strict item/part/usage validation 抽成两条路径共同调用的组件，并删除或降格无生产消费者的重复 converter，避免让测试继续背书死路径。该改动必须同时更新流式 semantic assembler 的对应判定，不应再复制一个类型表。

**证据强度。** 强到可直接行动：调用图由全 `src/` 精确检索闭合，registry 的实际注册对象与实跑的非流式结果相互印证。

**承重前提检查。** 前提是“`convert_responses_response_to_anthropic` 的单测代表生产转换合同”；它支撑“第 7(b) 只是接线清理，可在本提交之后做”。若前提为假，现有绿灯不能约束生产。零生产调用与 registry 源码已证明前提为假；第 7(b) 定级为 major，并与第 7(a) 同属当前合并前必须闭合的接缝。

### review-issue2-fix-04

- finding_id：`review-issue2-fix-04`
- severity：`minor`
- primary_location：`src/app/pipeline/delivery/formats/openai_responses.py:596-607`
- related_locations：`src/app/errors.py:35-56,59-83,145-180`；`src/app/pipeline/error_classify.py:225-239`；`.dev/docs/error-envelope/spec.md:109-144,156-177,310-335,355-365`；`.dev/docs/anthropic-responses-bridge/spec.md:394-400,433-440`
- 标题：代理已知自己缺少转换能力，却把拒绝分类为可归责上游的 `UPSTREAM`

**裁定。** `category=UPSTREAM` 不对；这里应是 `NOT_IMPLEMENTED`。`ErrorCategory` 的权威切分不是“数据从哪边来”，而是“客户端能做什么不同动作”：`UPSTREAM` 表示上游失败、HTTP 502、默认允许重试；`NOT_IMPLEMENTED` 表示代理没有建成所请求的 crossing、HTTP 501、明确不重试。该 item 是 openai SDK 声明的合法 output item，代理也已经用 `UNKNOWN` 明确认出“我不能转换”，所以这既不是上游错误，也不是未预料的 `INTERNAL` bug；它与 `TranslatorNotFound→NOT_IMPLEMENTED` 是同一类能力缺口。`source_format=OPENAI_RESPONSES` 也与 `ErrorInfo` 的本代理错误约定不一致：这是代理形成的 refusal，不是读到的上游 error event；应为空，必要的来源上下文可另放 conversion fact。

**`status_code` 的语义。** HTTP 200 已提交后，`ErrorInfo.status_code` 不会也不能改写实际响应状态；当前 Responses/Anthropic SSE writer 都不把它写入帧。它只表示“若同一语义错误在 commit 前发生，HTTP carrier 应用哪个状态”，并保持一个 IR 可同时用于 commit 前后。因此当前 `502` 是潜在语义，不是线上实际状态；改成 `NOT_IMPLEMENTED` 后应为潜在 `501`，线上仍是 HTTP 200加 SSE error。commit 后真正有判断力的是 `code=unknown_output_item`，这一 code 选择合理。

**影响。** 当前两种 SSE writer 对 `UPSTREAM` 与 `NOT_IMPLEMENTED` 都拼成 `api_error`/`server_error`，且 code 已显式覆盖，因此本提交的已观测 wire 没有类别差异；这也是本项定为 minor 而非 major 的理由。但错误 IR 会在非流式等价修复或统一错误处置后把代理能力缺口变成 502/可重试上游失败，届时客户端与运维被送到错误责任方。

**建议。** 改为 `ErrorCategory.NOT_IMPLEMENTED` 与 `STATUS_FOR_CATEGORY[NOT_IMPLEMENTED]`，清空 `source_format`；增加一条在构造层断言 category、hypothetical status、code 与 origin 的测试，wire 测试仍只断言实际 HTTP 200与 SSE error。

**证据强度。** 结论强到可直接行动；依据是 ErrorCategory 自身的 normative docstring、error-envelope 的完整 status/retry 表，以及合法 SDK item 事实。对当前 wire“无差异”的判断已由两条腿的实际输出与 writer 源码交叉确认。

**承重前提检查。** 前提是“上游发来代理不认识的合法 item，就应归 `UPSTREAM`”；它支撑当前 category。若它为假，责任与 retry 语义都错。类别契约按客户端动作切分，而不是按输入来源切分，故前提为假。

### review-issue2-fix-05

- finding_id：`review-issue2-fix-05`
- severity：`minor`
- primary_location：`src/app/pipeline/delivery/assembling.py:63-98`
- related_locations：`src/app/pipeline/delivery/formats/openai_responses.py:471-499,584-608`；`src/app/pipeline/delivery/formats/anthropic_messages.py:318-347`；`src/app/pipeline/delivery/stream.py:282-295,394-401`
- 标题：现有构造点都选对了 origin，但 `replayable=True` 默认值让未来代理 refusal fail-open

**裁定。** 三个现有 `StreamFailure(...)` 构造点已全量核对：Responses upstream failure 与 Anthropic upstream `error` 均应为 `True`，新 unknown refusal 显式为 `False`；`_report_failure()` 唯一调用点也先测 `passthrough and failure.replayable`，没有漏掉当前路径。当前行为安全。

**缺陷。** 默认值本身不安全。这个字段是两种互斥 origin 的承重判据，而省略它会静默选择“上游原话”；下一次增加本代理 failure 的构造点若忘记填写，直连腿会尝试按上游 event 重放空的或代理合成的 raw data。字段名 `replayable` 又与同文件真正负责 attempt retry 的 `ReplaySupport` 词义相撞，增加误读概率。`BlockAssembler.failure` 第 93～97 行仍写成只承载“Upstream's own report”，也与新第二 origin 不一致。

**影响。** 已有路径无运行时错误；风险发生在新增 failure origin 时，且会以合法类型、默认值、绿静态检查的形态进入，因此定为 minor 而不是假设性 blocker。

**建议。** 删除默认值，让三个构造点都显式写 origin；优先把 bool 改成 `FailureOrigin.UPSTREAM_EVENT | PROXY_REFUSAL`，由 `_report_failure` 从 origin 判 raw replay，或至少改名 `raw_event_replayable`。同步修正 `BlockAssembler.failure` 的契约说明。

**证据强度。** 当前三处构造与唯一消费点的否定性全称由全 `src`/`tests` 精确检索闭合；未来漏填属于设计风险判断，不冒充已发生故障。

**承重前提检查。** 前提是“默认 upstream origin 对未来构造点是安全默认”；它支撑保留 `=True`。若前提为假，新代理 refusal 会走错误 wire 分支。新功能本身已经证明第二 origin 会出现，故默认值不满足 fail-closed。

### review-issue2-fix-06

- finding_id：`review-issue2-fix-06`
- severity：`minor`
- primary_location：`src/app/server/routes/inference.py:650-668`
- related_locations：`src/app/pipeline/delivery/formats/openai_responses.py:471-499`；`src/app/pipeline/delivery/formats/anthropic_messages.py:318-347`；`.dev/docs/anthropic-responses-bridge/spec.md:315,345-356,433-440`
- 标题：代理 refusal 的完成行顺序正确，但上游 failure 仍被写成“没有 terminal event”

**顺序裁定。** 新分支排在 `self.failure` 之后、`self.drained` 之前是对的。若 error frame rendering/delivery 自己再抛异常，`self.failure` 是客户端实际没收到 refusal 的更近因，必须优先；正常 refusal 会 clean-return，故 `self.failure is None`、`drained=True`，必须在 drain 文案之前识别。`handed_over` 仍应最先，因为它描述客户端实际得到的终局。没有发现新分支遮蔽其他 ending。

**不同意调用方对 upstream failure 文案的初判。** `response.failed`、`response.cancelled` 与 Anthropic `error` 正是 failure terminal；bridge Spec 第 315、350、356 行也把前两者列为 terminal failure。它们使 delivery clean-return 并置 `drained=True`，当前 `_ending()` 因 `replayable=True` 跳过 refusal 分支，落到“upstream stream ended without a terminal event”。这句话把“收到明确失败终局”说成“什么终局也没收到”，事实错误。虽然 assembler 同时另写 warning，客户端 error frame也正确，因此是 observability minor，不阻断 wire 修复。

**建议。** 在 assembler failure 存在时统一完成行分类，再按 origin 分文案：proxy refusal 写当前文字，upstream event 写 `upstream reported a stream failure: …`；仍保持 propagated `self.failure` 更优先。增加两个完成行测试，分别覆盖 `replayable=False` 与 `True`，并断言 status 均为 `fail` 但责任方不同。

**证据强度。** 静态状态机路径与 Spec 术语足以直接行动；现有 upstream failure warning 使“是否完全无记录”这一更严重可能性被排除。

**承重前提检查。** 前提是“failure event 不是 terminal，所以 drain 文案尚可接受”；它支撑保留旧文案。若前提为假，完成行归因错误。Spec 明确把这些事件列作 terminal failure，故前提为假。

## 专项核对结论

### 1. error-envelope 形态

`code=unknown_output_item` 是稳定、具体且适合 post-commit SSE 的 code；`category=UPSTREAM` 不成立，应为 `NOT_IMPLEMENTED`，理由与当前影响见 finding 04。两条实际腿均保持 HTTP 200并发合法方言 error：Responses 为扁平 `event:error`，Anthropic 为嵌套 `event:error`；均无成功 terminal。`status_code` 只是同一错误若发生在 commit 前时的 HTTP 语义，不是已提交后的线上状态。

### 2. `StreamFailure.replayable`

现有三个构造点的值都正确，唯一 `_report_failure` 调用点没有漏路；默认 `True` 不应保留，详见 finding 05。该 bool 表示 raw upstream event 能否重放，不表示 attempt 是否值得 retry；当前名字容易与 `ReplaySupport` 混淆。

### 3. 完成行归因

新 refusal 分支的相对顺序正确，不遮蔽其他 ending；上游 failure 的旧 drain 文案不正确，不能以“不在本次改动”为由称其“尚可接受”，详见 finding 06。

### 4. `web_search_call` 与隐式 fallback 依赖

最终态显式列出 `WEB_SEARCH_CALL: WEB_SEARCH_CALL`，保持了旧 `_close` 专门分支；现有 web-search regression tests 与完整 suite 均通过。`tool_search_call` 早已显式映射为带已知 client tool 名的 `TOOL_USE` 或 `DISCARDED`，`tool_search_output` 早已显式为 `DISCARDED`，二者没有依赖旧 `.get(item_type,item_type)`。全 `_close` 分支扫描未发现第四个以原 item type 字符串 dispatch 的类型。

### 5. 22/28 爆炸半径

未发现本提交把一个此前“正确处理”的 item type 误伤成拒绝。除 `web_search_call` 外，另外 21 个旧 fallback 类型都只能落到最终 TEXT-shaped payload；Responses 客户端随后因未知 kind 抛 `ValueError`，translated 客户端至多得到其专有 delta 从未进入的空/错误 text。`function_call_output` 虽在 buffered request/history reader 有显式分支，但 streaming response assembler 旧 fallback 并未调用它，不能把另一条路径的能力算成旧 streaming fallback 的正确处理。`tool_search_call`/`tool_search_output` 已显式排除在 22 个 fallback 类型之外。结论证据强到足以判“无已知正确处理被回归”，但不外推为“未来 Responses item 永远不可能用 generic output text event”；未来类型仍由 fail-closed Spec 决定，不靠猜测放行。

### 6. 新测试的分辨力

调用方给出的变异结果能复现原 `ValueError`，足以证明测试打到了 `.get` fallback。`not [name for name in names if name.startswith("response.output_item")]` 确实排除了 direct Responses 腿渲染空 block：`ResponsesFramer._message()` 对任何 text block必发 `response.output_item.added` 与 `.done`，所以不能靠空文本绕过；它钉的是事件结构，不是 `custom_tool_call` 名字。`names[-1] == "error"` 与不存在 `response.completed` 又排除了 error 后成功 terminal。其盲区是只测 direct、正常 `added→done`、未知顶层 item；findings 01、02 的 translated、done-only、unknown content part 与 non-stream 反例全部在盲区，故现有测试有分辨力但覆盖命题过窄。

测试 helper 给 `custom_tool_call` 的 done item补了 SDK 类型未声明的 `status="completed"`，但 UNKNOWN 分支在 `cut_short` 之后只读 type/id，且该值不会改变本测试结果；我把“这是造成假绿的原因”明确排除。更贴近实测的 fixture 应去掉该字段并加入真实 `response.custom_tool_call_input.delta/done`，但这属于 fixture 精度改进，不单列 severity。

### 7. 两项未做工作的裁定

第 7(a) 项是 **major，并阻断本次合并**：同一 fixture 已实跑出 stream error与 non-stream success，两者直接违反 Response conversion 等价契约。

第 7(b) 项是 **major，并阻断本次合并**：strict converter 的测试不约束生产，且它正是第 7(a) 分叉持续存在的结构原因。这里的阻断不是要求一次建完 direct passthrough，而是要求这次以 bridge Spec 为依据的 unknown-reject 切片至少接到唯一 production semantic owner；否则下一刀仍可能只修三套实现之一。

## 已排除掉的可能性

1. **“`UPSTREAM` 因 item 来自上游就正确”——排除。** Category 按客户端动作与责任方切分；合法 item加代理能力缺口对应 `NOT_IMPLEMENTED`，不是 upstream failure。
2. **“post-commit `status_code=502` 会把实际 HTTP 200 改掉”——排除。** SSE writer不读取该字段；实际状态已提交，只能靠 error frame结束。
3. **“`code=unknown_output_item` 应随 category 一起改成默认 code”——排除。** §6.4 要求 post-commit code保留判断力；具体 code 比 `not_implemented` 更能定位，现有值应保留。
4. **“`_report_failure` 忘了 translated 或 direct 某一条腿”——排除。** 唯一调用点总是执行，`passthrough && replayable` 只选 raw replay，其余两种组合都进客户端 framer；两条 ASGI 腿已实跑。
5. **“新完成行分支应移到 `self.failure` 之前”——排除。** error frame本身若抛，propagated failure才是客户端实际终局，先报 refusal会遮蔽更近因。
6. **“新完成行分支应移到 `handed_over` 之前”——排除。** hand-over描述客户端实际获得的替代 terminal，优先级更高；当前 unknown refusal路径也不会同时 hand over。
7. **“上游 failure 的 drain 文案是准确的，因为 `Terminal.seen=False`”——排除。** `Terminal.seen` 只记成功 terminal，不会把 `StreamFailure` 从 terminal failure变成无事件 EOF。
8. **“`tool_search_call` 或 `tool_search_output` 依赖旧 fallback”——排除。** 两者在变更前后都显式列入 `_open` map，只有 `web_search_call` 曾依赖 item type自映射。
9. **“另外 21 个 fallback item里存在一个旧 streaming assembler 已正确翻译的类型”——在已检查实现与 fixtures 面上排除。** 它们没有 `_close` 专门分支，专有 delta也不由 generic accumulators消费；仓内 JSON cassette 对 22 个类型检索为零。未把“上游永远不会新增共享 generic delta 的类型”升级为全称。
10. **“新测试的 `output_item` 排除断言会误命中 error code里的同名片段”——排除。** 它先解析 `event:` 行再判断 event name，不搜索整个 response text。
11. **“helper 多出的 `status` 使 UNKNOWN 分支才会触发”——排除。** kind 在 `_open` 只由 type决定，`status` 只参与 `cut_short`，`completed` 与字段缺失都为 false。
12. **“两项第 7 条只是与 issue #2 无关的旧债”——排除。** 本提交在 shared streaming converter 上主动实施同一 unknown-reject合同，并在源码注释声称 non-stream 文件随之改变；相反行为与死接线正处在它宣称的原子边界内。
13. **“当前提交已经具备 direct Responses 原生 passthrough，因此不应拒绝 22 类”——排除。** 目标 diff没有 raw item delivery unit，现行 direct passthrough plan又被既有评审判定须先补 Spec；本评审不把候选方案假装成已实施合同。
14. **“完整 suite全绿足以否定 findings 01～03”——排除。** suite没有 done-only unknown、unknown content part的 stream反例，也没有通过生产 registry断言 strict converter；三个实跑反例在同一绿 HEAD上成立。

空清单声明：以上 14 项是本次评审中实际考虑并排除的可能性；没有把调查途中未闭合的猜测写成发现。

## 测试与命令证据

- `git … merge-base 78030df 621803c`：输出 `78030df9e822efa554c753f78b15f785f0f9ca4c`；`rev-list --count` 输出 1；worktree status clean。
- 目标与相关流式测试：82 passed，含新增 issue #2 test、`test_openai_responses_format.py`、`test_stream_delivery.py`。
- 非流式 strict converter 与 stop-reason 测试：35 passed。
- 完整 `ruff check src tests`：通过。
- 完整 `pyright src tests`：0 errors、0 warnings、0 informations。
- 完整 `pytest tests --cov=app --cov-report=term --cov-fail-under=80`：1945 passed、2 skipped、coverage 90.75%。
- 自建只读 ASGI 探针均运行在 `uv run --directory <目标 worktree>`：正常 unknown item两条腿均得到 error且无 terminal；done-only unknown两条腿均 HTTP 200空 body并记录 `ok end_turn`；unknown content part直连腿得到空 output item加 `response.completed`，translated腿得到空 text block加 `message_stop`；同一 custom item非流式 translated得到 HTTP 200、`content: []`、`end_turn`。

完整绿跑的证据权重是“证明目标 HEAD没有触发既有回归”，不足以否定未被 suite构造的反例；反例的实际 ASGI 输出对对应 findings 强到可直接行动。

## 搜索面与未覆盖面

读过全部 5 个变更文件的 diff与最终相关实现；全 `src`/`tests` 检索了 `StreamFailure(`、`replayable`、`assembler.failure`、`_report_failure`、`web_search_call`、`tool_search_call`、`tool_search_output`、22 个 fallback item type、`blocks_from_item`、`from_openai_responses_response`、`convert_responses_response_to_anthropic` 与 registry registration。读取了 openai SDK 3.3.1 中 output item union与代表性专有 delta event定义，但没有逐文件重审 28 个 item的全部字段，也没有真实 upstream sample；因此“无误伤”的结论限定为现有实现、现有 fixtures 与现行 Spec，不声称穷尽未来协议。

没有审计 TUI、History数据库落盘字节或外部 SDK在收到本次 error frame后的全部重试行为；category裁定不依赖这些面，因为权威 ErrorCategory 已按客户端动作定义，当前 post-commit wire差异又由 writer源码可判。没有修改任何 `src/` 或 `tests/`。

## 我最没把握的三个判断

1. **第 7(b) 是否应独立阻断，而不是只作为第 7(a) 的结构原因。** 我的判断是独立 major：死 strict converter的测试背书会持续制造假完成，而且目标 patch已新增第三套规则；即使调用方选择合并两个 finding处置，计数仍应保留两个稳定 ID。证据强，但“是否一个修复提交一起处理”是调用方的实施划分。
2. **`NOT_IMPLEMENTED` 与 `INTERNAL` 的边界。** 我偏向并裁定 `NOT_IMPLEMENTED`，因为代码已将 UNKNOWN作为预期能力缺口处理，且 `TranslatorNotFound` 是明确类比；若产品把“声明支持该 crossing却漏类型”定义为代理 bug，`INTERNAL` 也比 `UPSTREAM` 更接近。无论二者选谁，`UPSTREAM` 都不成立；这一共同部分证据更强。
3. **malformed done-only 是否会在真实 Copilot上出现。** 没有样本，频率未验证；但 finding 01 的级别不依赖频率，Spec已明确把 malformed lifecycle列为 REJECT，且 unknown content part的第二反例独立成立。该探针只证明实现行为，不主张上游发生率。

## 执行本契约时遇到的摩擦

- 目标报告目录位于主工作树 `.dev/`，Write守卫拒绝从隔离 worktree写共享路径；按调用方预案改写到 `/tmp/260830-review-issue2-fix.md`，需调用方搬运。
- 一次 Bash heredoc探针被 worktree守卫拒绝；没有绕过，改为先把 test-only probe写入 `/tmp/review_issue2_probe.py`，再用单条 `uv run --directory <worktree> python /tmp/review_issue2_probe.py` 执行。
- worktree自身没有 `.venv`，SDK定义从主项目共享 `/home/xp/src/ghc-api-proxy-py/.venv/` 读取；运行期由 `uv run --directory` 解析目标项目，测试 rootdir逐字确认是目标 worktree。
- `/tmp/review_issue2_probe.py` 是本轮 test-only 输入脚本，最终版本保留了 unknown content part 探针；本轮没有取得独立 manifest 评审，也没有删除授权，因此未执行删除，由调用方或 harness后续处置。前两轮 done-only与 non-stream probe的构造和输出已写入本报告，但脚本被逐轮覆盖，不能把最终文件冒充三轮原件。
- 本报告没有再派 agent复审：当前角色是 leaf executor，且任务明确禁止再派 agent；调用方需按既有流程处置本报告，不把本次自查冒充第二位独立 reviewer。

## 严重度汇总

- blocker：0
- major：3
- minor：3
- nit：0
- finding_total：6

## 交付声明

- delivery_complete：true
- completed_at：2026-08-30
- finding_total：6
- blocker：0
- major：3
- minor：3
- nit：0
