# 直连 Responses 透传方案独立评审

- report_id: `direct-responses-passthrough-plan-review`
- attempt_id: `260830-review-plan-1`
- status: `draft`
- reviewed_at_rev: `78030df`（调用方给定；本会话的 Bash 被隔离工作树守卫拒绝，未能独立核验 Git 指针）
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/plan.md`
- 评审性质：尚未实施的架构方案，只读评审；未修改 `src/` 或 `tests/`

## 评审范围

本次评审覆盖方案的两层架构、`CompletedBlock` 消费面、直连与翻译两条腿的分流、块级交付状态机、D2 裁定、reasoning carrier 回路、与 hosted web search 块对工作的交叉面，以及 Spec-first 义务。判据独立取自用户亲笔的 `request-pipeline.md`、`message-translation.md`、`api.md`，当前 `anthropic-responses-bridge/spec.md`、`hosted-web-search-spec.md`、`error-envelope/spec.md`，项目开发规则及两份指定取证原件。

明确不在范围内：实施代码修改、测试资产修改、真实上游调用、GitHub issue 评论本身的内容复核、对 28 个 SDK union 成员重新做外部 SDK 类型审计。

## 总体 verdict

**needs-fix。当前方案不得进入实施。** blocker 数：**1**。

层一识别出的架构病因是对的：同格式直连不应先降到 Anthropic 语义再升回 Responses。但方案把“保留 `output_item.done.item` 的最终快照”称为“原样透传”，遗漏事件级与 terminal-level 的 Responses 语义，并继续让直连 item 经过翻译腿专用的 `cut_short`、buffer policy 与 terminal 推导。层二按“丢弃或降级成文本”处理未知 item 又与当前规范的 `REJECT` 明确冲突。

## 发现

### direct-responses-passthrough-plan-review-01

- severity: `blocker`
- primary_location: `plan.md:74-104`
- related_locations: `.claude/rules/00-development-workflow.md:7-13`；`docs/.human-controlled/message-translation.md:6-8`；`.dev/docs/anthropic-responses-bridge/spec.md:222-235,303-317,433-440`；`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:40-48`；`.dev/docs/error-envelope/spec.md:34-38,64-104`
- 标题：方案把新的用户可观察合同留在 plan 里，尚无可实施的 Spec

**证据。** `plan.md` 新定了至少六项外部行为：直连流式每个 output item 变成一种“保真块”；只重放 `response.output_item.added` 与 `.done`；用 `done` 快照稳定 item id；沿用 framer 的 `output_index`；直连 `encrypted_content` 原样交还；翻译腿未知 item 丢弃或降级成文本并选择某个成功 `stop_reason`。现有权威没有定义这组成功响应合同：`hosted-web-search-spec.md` §1 只把直连 `/responses` 排除在其限制之外并裁定请求声明放行；`error-envelope/spec.md` 只定义直连错误的原生透传；`anthropic-responses-bridge/spec.md` 的定义域是 Anthropic inbound → Responses upstream，而且其当前矩阵反而规定未知 output item `REJECT`。项目规则明确禁止实现先于完整行为 Spec，也禁止 Spec-level 事实停在 plan。

**影响。** 实现者必须自行决定“原样”到底是 final snapshot、事件集合、JSON value、SSE payload 还是字节，新增 item-specific event、terminal 扩展字段、id 与 sequence_number 漂移时没有权威答案；层二还会直接实施一个与现行 Spec 相反的行为。这不是文档完善度问题，而是实施授权与验收 oracle 缺失，因此阻断进入实施。

**建议。** 实施前新增 `.dev/docs/direct-responses-passthrough/spec.md`，至少定义：定义域仅同格式 Responses→Responses；非流式继续 body 原样；流式的保真层级；允许改动的只有哪些传输包装与时点；item-specific events、item id、response id、`sequence_number`、`output_index`、terminal response object、usage/tool_usage/metadata 的处置；三种 buffering policy；不完整 item、failure、EOF、retry 与 memory cap；reasoning 回传。若层二仍要改变未知 item 的 `REJECT`，则必须同时修订 `anthropic-responses-bridge/spec.md` 的 response 矩阵、Response conversion 与 Error 条款；否则按当前 Spec 实施显式失败。`hosted-web-search-spec.md` §1 只需回链新的直连 Spec，不应复制其合同。

**承重前提检查。** 前提是“plan 中这些句子只描述实施方法，不是行为合同”；它支撑“可不先写 Spec 就实施”。若前提为假，实施即违反本项目不可协商的 Spec-first 规则。上述事件集合、id、terminal 字段与未知 item 处置都会改变客户端可观察结果，所以前提为假；本 finding 强到足以阻断。

### direct-responses-passthrough-plan-review-02

- severity: `major`
- primary_location: `plan.md:74-80,102-104`
- related_locations: `src/app/pipeline/delivery/formats/openai_responses.py:99-188,190-355`；`src/app/pipeline/delivery/sse_source.py:18-52`；`docs/.human-controlled/message-translation.md:6`
- 标题：`done.item` + 两个合成事件不是“原样透传”，也不能一次性保住未来 item

**证据。** 方案只把 `response.output_item.done.item` 的最终 dict 放进块，再重发 `response.output_item.added` 与 `.done`。这会删除所有 item-specific 事件，例如 issue #2 已确认存在的 `response.custom_tool_call_input.delta` / `.done`，以及 web search 的状态事件、文本 content-part / annotation 事件；会删除原事件的 `sequence_number`、阶段状态和事件级 id；还会继续由 `ResponsesFramer.preamble()` 与 `terminal()` 合成 `response.created` / `response.in_progress` / `response.completed|incomplete`。当前 `_response_object()` 只造一个字段子集，根级 `tool_usage` 等扩展不会因为 item payload 保真而回来。`SseEvent` 本身也只保留 `event` 与规范化后的 `data`，所以到这里后连原 SSE 字节都已不可恢复。

**影响。** 普通 final-response 聚合器可能仍能得到 output snapshot，但订阅具体流事件的 Responses 客户端会观察到协议事件消失；未来 item 若把有判断力的信息放在专有事件或 terminal 扩展里，方案仍会无声丢弃。由此，收益段的“包括 OpenAI 以后新增的”与“直连腿不再需要认识任何 item type”不成立，且“原样”名不副实。

**建议。** 先在新 Spec 里二选一并说准：若产品只承诺“最终 Response snapshot value-equivalent”，就明确这不是事件原样透传，并完整携带 authoritative terminal response object；若坚持用户的“尽可能原样”，应在 `delivery_policy` 处分出专用的 Responses passthrough assembler / delivery unit，缓存并在 item 完成边界后重放该 item 的完整原生事件组，只对时点、chunking 与必要的序号重编做明确列举。若要求 byte-level，捕获必须发生在 `SseEvent` 解析前。不要把 raw Responses delivery unit 塞进 docstring 明定为 Anthropic content block 的 `CompletedBlock` 而不先重定义该公共类型。

`plan.md:103` 对 id 的口径也必须改准：若以 `done.item` 为 authoritative snapshot，就应把该 snapshot 的原 item id 同时用于重放的 added/done，而不是沿用 framer 的 synthetic id。事件间上游 id 不稳定只说明不能拿 added id 关联 draft，不说明 final item id 可以改写；对于 future item，它可能是客户端下一轮回传的 opaque handle。若确需 synthetic id，必须在 Spec 中承认这是 transform 并证明回传后果。

**更简单方案比较。** 在 `delivery_policy` 对 `translation_required=False && inbound_format==target_format==OPENAI_RESPONSES` 早分流，整段 SSE memory-buffer 后原字节交付，是最小实现且最彻底保真；但它把 block policy 收窄成 full-response、失去 block 完成即交付、现有 `one_shot_delivery` 又无 keepalive、replay 与 buffer cap，因此并非同代价。长期更稳妥的是早分流但保留一个只识别边界、不做 Anthropic 映射的 passthrough assembler。方案应把这两个候选及其代价写进决策，而不是默认“final item snapshot”等于原样。

**承重前提检查。** 前提是“`done.item` 包含直连客户端需要保真的全部 Responses 语义”；它支撑“一种保真块一次消灭当前及未来 22/28 面”。若前提为假，未来专有事件与 terminal 扩展仍丢失。现有 `custom_tool_call_input.*` 和根级 `tool_usage` 已构成反例，故前提被推翻，结论需重写。

### direct-responses-passthrough-plan-review-03

- severity: `major`
- primary_location: `plan.md:76-79,92-104`
- related_locations: `src/app/pipeline/delivery/blocks.py:44-54,57-123`；`src/app/pipeline/delivery/assembling.py:28-60`；`src/app/pipeline/request.py:85-88`；`src/app/observability/request_log.py:102-156,159-203,335-401`
- 标题：消费者清点需修正；buffer policy、容量记账与可观测摘要都会读块语义

**独立清点结果。** 在 Bash 守卫允许的静态读取面内，我确认的直接消费者不是方案所称的“三类且最后一类完全不读 payload”：

1. 两个 framer 读 `kind` 与 `payload`，负责 wire。
2. `Terminal.record()` 读 `kind`，并对 `tool_use` 读 `payload.name`、对 `thinking` 读 `payload.thinking`；`RequestContext.reply` 明确是 console line 与后续消费者的聚合记录，`RequestLine` 又把 `tools`、`thinking`、`blocks`、`stop_reason`、`usage` 渲染出来。因此 footer 的在途视图不读 payload，但完成日志/TUI 所依赖的 reply summary 会受影响。
3. `CompletedBlock.size_bytes` 对**整个** `payload` 做 `repr(...).encode()`；`BlockBuffer.add()` 在 cap 检查与记账各读一次，故“完全不读 payload”按字面为假。
4. `BlockBuffer.add()` 还直接读 `block.kind`：`until-tool-use` 只有 `kind == TOOL_USE` 才释放。把所有 Responses item 统一成一种新“保真 kind”，会让 `function_call` 乃至 `custom_tool_call` 不再触发该 policy，整轮被持有到 terminal。
5. `DeliverySession` 不读 payload，只按实际释放的块维护 `delivered` 与 `committed_count`；`decide_stream_ending` 只读位置事实与计数。`hand_back_block` 也不读已交付块 payload，它合成一个新的末尾块。

受工具限制，这不是全仓机械穷举，History/hook 是否另有直接引用无法做否定性全称断言。但本 finding 不依赖全称：第 3、4 项已足以推翻方案中“BlockBuffer 完全不读 payload，因此只需边界”的承重论据；第 2 项证明现有可观测语义也必须显式迁移。

**影响。** 新 kind 会改变 `until-tool-use` 的交付时点；raw item 可能远大于翻译后的 Anthropic payload，而“added + done”会把同一 item 编码两遍，当前 cap 只按一个 Python `repr` 计，不能证明覆盖预渲染 envelope 的 resident bytes；`Terminal.record` 若不扩展，直连 Responses 的工具名与 reasoning 分类会从完成行消失。`Terminal.blocks` 又参与 `cut_short` 判定，所以这不是纯展示问题。

**建议。** 把“协议载体类型”“是否是客户端待执行的 tool call”“buffer release trigger”“observability classification”拆成 typed facts，不要让一个新字符串 kind 同时承担四件事。为直连 Responses 明确定义哪些 item 触发 `until-tool-use`；对 raw payload 和预编码事件做一致的容量记账；让 Terminal 按 `ReplyDialect.RESPONSES` 从原生 item 分类 function/custom tool call 与 reasoning，而不是假装它们是 Anthropic block。若采用独立 passthrough delivery unit，这些 facts 应由其边界检测器产出。

**层一前提裁定。** **需修正。** “没有 History 等第四类直接读取 payload 语义的消费者”在本次静态面上未发现反例，但方案已经列到的 `Terminal` 与 `BlockBuffer` 并非无关：前者把语义送入完成日志/TUI，后者既读整个 payload 的大小又按 kind 改变交付。因此“直连翻译是纯损耗”的产品方向成立，“可以只换 payload 而不迁移任何派生事实”的工程前提不成立。

**承重前提检查。** 前提是“只要 `BlockBuffer` 不解释 payload 字段，保真块就不会改变交付政策”；它支撑“层一不必设计 policy/observability 适配”。若前提为假，`until-tool-use` 与 cap 会变。源码给出两个直接反例，故必须在方案阶段补齐。

### direct-responses-passthrough-plan-review-04

- severity: `major`
- primary_location: `plan.md:74-80,90-98`
- related_locations: `src/app/pipeline/delivery/formats/openai_responses.py:400-420,536-649`；`src/app/pipeline/delivery/stream.py:343-575,577-612`；`src/app/pipeline/hand_over.py:221-240`
- 标题：直连“保真块”仍会被翻译腿的 `cut_short`/hand-over 政策丢掉

**证据。** `ResponsesAssembler._close()` 在任何 kind 分支之前按 closing item 的 `status == "incomplete"` 与 `Terminal.blocks > 0` 计算 `cut_short`，随后把块停进 `_cut_short`。到 `response.incomplete` 时，若转换后的 `terminal.stop_reason` 落在 `hand_over_stop_reasons`，held block 被直接丢弃。这个设计只在 Anthropic 客户端能接住合成 hand-over block 时成立；`hand_back_block()` 对非 Anthropic inbound 明确返回 `None`。方案层一没有绕开这套政策，只说所有 item 一律产出保真块，因此一个直连 Responses 客户端的最后 incomplete item 仍可能在 terminal 前消失。

`Terminal.stop_reason` 也是 Anthropic 导向的派生：`max_output_tokens` 先改成 `max_tokens`，completed 再由 `_saw_tool_call` 推成 `tool_use`/`end_turn`；Responses framer 又据此反推 `response.completed`/`response.incomplete`。标准 `usage` 尚有 `upstream_usage` 原值可回写，但 authoritative terminal response object 没有被保存，`tool_usage`、未来 terminal 字段及上游原 incomplete details 仍会丢失或经闭集映射。

**影响。** 层一无法兑现“所有 output item 一律保真”；直连腿还会继续受一个只为 Anthropic continuation 合理的丢块政策影响。对 future item，仅从 type 推 `_saw_tool_call` 也会重建一套会过期的 union 分类，正好把方案想消灭的认知面搬到 terminal 上。

**建议。** 直连 mode 必须在进入 `_upstream_cut_this_item_short` 与 hand-over 处置之前分流：closing item 一律形成可交付的原生 delivery unit，`response.incomplete` 按上游 authoritative terminal 发出；不得为一个 Responses 客户端丢块等待 Anthropic hand-over。把原 terminal response object作为 direct path 的一等事实携带，wire status、incomplete details、usage、tool_usage 与扩展字段从它写出；`Terminal.stop_reason` 仅作为内部可观测摘要，不能反过来成为直连 wire 的 source of truth。

**逐项状态机结论。** keepalive 按最后一次客户端写入计时，与 payload 无关，结构上仍成立；背压的“yield 时不继续 pull”仍成立，但容量记账与 release trigger 见 finding 03；`DeliverySession.committed_count` 按实际交付块计，若一 item 一 delivery unit 则无需另改；`decide_stream_ending` 只读 `terminal_seen/downstream_opened/committed_blocks`，无需理解 raw payload；`hand_back_block` 对 Responses 客户端本来就不适用。真正必须切开的就是 assembler 内的 `cut_short` 与 terminal 重建。

**承重前提检查。** 前提是“保真 payload 进入现有 assembler 后只会被缓冲，不会被语义政策改写或抛弃”；它支撑“层一只需加一个 block kind”。若前提为假，直连 item 仍会丢。`_cut_short` 的现行分支直接证伪该前提。

### direct-responses-passthrough-plan-review-05

- severity: `major`
- primary_location: `plan.md:84-98`
- related_locations: `.dev/docs/anthropic-responses-bridge/spec.md:222-235,303-317,433-440,593-603`；`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:40-48,510-524`；`src/app/pipeline/translation_driver/responses.py:155-206`；`src/app/pipeline/delivery/stream.py:391-398,480-501`
- 标题：D2 的三个选项都不是当前合同允许的答案；翻译腿必须显式失败

**裁定。** **三项均不采纳。按当前 Spec，翻译腿遇到未知 output item 必须 `REJECT`，产生明确 conversion error；已经提交 HTTP success headers 后写客户端方言的 SSE error event，且不得再发成功 terminal。** 因此 D2 在翻译腿上没有需要伪造的 `stop_reason`：这一轮不是成功 message，不应在 `end_turn`、`tool_use` 与文本降级之间选一个。

**理由。** 当前 `anthropic-responses-bridge/spec.md` 的 response 矩阵逐字规定“未知 output item、未知 content part、malformed lifecycle → `REJECT`，不得由空 text block或正常 terminal掩盖”；Response conversion 又规定 unknown 不得变成正常 `end_turn`；Error 契约规定 commit 后用明确 error terminal。`hosted-web-search-spec.md` 只对 `web_search_call` 作定点覆盖，并把其余 builtin 明列为继续 `REJECT`。取证报告的“与缓冲侧看齐＝丢弃”描述的是当前代码现状与作者建议，不高于当前 Spec。

三个候选各自的问题：保留 `end_turn` 是已知说谎；`tool_use` 没有对应 Anthropic `tool_use` 块，客户端无从执行；降级成文本是新的产品行为，会把 typed/opaque item 解释成代理撰写的散文，还不能一般性保住自由文本 input、结构字段与 future semantics，且直接违反 strict unknown 合同。若用户以后明确重裁允许某个 item family 做有损文本降级，应像 hosted web search 一样在 Spec 中逐族定点覆盖，不能作为 unknown 默认。

**实施含义。** 层二可以引入 `UNKNOWN`，但它应是“识别到不支持后触发 conversion failure”的显式状态，而非“丢弃”的状态；`DISCARDED` 只留给 Spec 明确认识且允许不投递的 control item。buffered `from_openai_responses_response()` 也必须停止对 `BlockKind.UNKNOWN` 仅记 `ITEM_NOT_CARRIED` 后继续，改为同一 conversion error，才能真正实现 non-stream/stream 等价。直连腿不经过这一状态，原生 item 与原生 terminal 一起交还。

**承重前提检查。** 前提是“缓冲侧当前丢弃未知 item 的实现代表产品合同”；它支撑“层二与缓冲侧看齐即正确”。若前提为假，层二修错方向。当前 Spec 明确给出相反合同，所以该前提被推翻；这项裁定的证据强度为**强到可直接实施**，除非用户另行重裁。

### direct-responses-passthrough-plan-review-06

- severity: `major`
- primary_location: `plan.md:72-88`
- related_locations: `.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:152-217,231-281`；`.dev/docs/hosted-web-search/reports/260830-native-block-pair-gap-reconciliation.md:60-87,138-210`；`src/app/pipeline/delivery_policy.py:50-95`；`src/app/pipeline/delivery/formats/openai_responses.py:393-649`
- 标题：与 issue #1 的产品语义正交，但与其状态机改动不正交

**裁定。** “块对只给 Anthropic 客户端，层一只给直连 Responses 客户端”这一**产品作用域正交性成立**。但方案的“互不重叠”“Anthropic 腿一个字不动”若被读成实施正交则不成立。

**证据。** 两项工作都会改 `ResponsesAssembler` 的构造参数、`push/_open/_close`、block index 分配、`Terminal.record` 时点与 terminal flush。块对工作还要增加 pending attribution queue、在后随 message 的完成边界一次产生两块、处理无后随文本的 flush；层一则要在同一个 item close 路径上提前产出 raw delivery unit，并绕开这整套翻译逻辑。当前 selector 只按 upstream dialect 选一个 `ResponsesAssembler`，因此没有现成的物理隔离。G1b 本身已经证明客户端腿判据必须到 assembler，而那正是本方案也要占用的接缝。

**影响。** 若两边各自按现有 plan 改共享 `_close`，容易出现 direct `web_search_call` 先进入待归因队列、直连 terminal 把队列 flush 成 Anthropic 块对，或 index/`Terminal.blocks` 的时点被后合入者覆盖。两份分支各自测试通过也不能证明合并态成立。

**建议。** 在计划中明确一个共同重构边界：`delivery_policy` 先算出 `DIRECT_RESPONSES_PASSTHROUGH` 与 `RESPONSES_TO_ANTHROPIC` 两种 mode，最好实例化两个不同 assembler，而不是在 `_close` 深处散落 client-leg 条件。前者只做原生边界与 passthrough facts，后者独占 web-search attribution queue、Anthropic block index、`UNKNOWN→REJECT` 与 reasoning carrier。至少补合并态矩阵：direct `web_search_call`、direct `custom_tool_call`、translated web-search block pair、translated unknown item error；每项覆盖 stream/non-stream 及关键 buffer policy。先落共同 seam，再分别实现，最后只评一次合并态。

**承重前提检查。** 前提是“只要两个 feature 的客户端作用域不相交，它们就不会改同一状态机”；它支撑“两层可独立落地且 Anthropic 腿不用复核”。若前提为假，合并态可能跨腿泄漏。上述共享方法与共享状态直接证明前提为假；正确表述应是“语义正交，实施共享承重点”。

### direct-responses-passthrough-plan-review-07

- severity: `minor`
- primary_location: `plan.md:5`
- related_locations: `.dev/docs/hosted-web-search/reports/260830-native-block-pair-gap-reconciliation.md`
- 标题：块对取证链接指向了不存在的相对路径

**证据。** 从 `direct-responses-passthrough/plan.md` 出发，`reports/260830-native-block-pair-gap-reconciliation.md` 解析到本 topic 自己的 `reports/`；原件实际位于 `.dev/docs/hosted-web-search/reports/260830-native-block-pair-gap-reconciliation.md`。正确相对路径应为 `../hosted-web-search/reports/260830-native-block-pair-gap-reconciliation.md`。该原件又锚定 issue #1 隔离工作树 HEAD `b9a7236`，计划若引用其行号或现状，还应保留该 revision 限定。

**影响。** 读者无法沿计划定位 G1b，一条承重依据失去可解析锚；但调用方已给出原件路径，本次评审未因此阻塞。

**建议。** 修正链接并在引用文字中注明报告的锚定 revision 与其“主树行号可能不同”的限定。

## 对专项问题的集中回答

### reasoning carrier 会不会打架

**结论：按正确分流实现时不会；证据强到可据此设计。** `handle()` 只在 `route.translation_required` 为真时调用 request translator；直连 Responses→Responses 为假，客户端下一轮回传的原生 reasoning item 因而不进入项目 reasoning carrier decoder。响应侧也必须在现有 `_reasoning()` 之前走原生 passthrough 分支，直接保留 `encrypted_content`。只有误把 raw reasoning item 再交给 `_reasoning()`、或把 synthetic item id 当“稳定化”改写时，才会重新引入 carrier/continuation 风险。新 Spec 应把“same-format direct path 不编码、不解码项目 carrier”写成明确条款。

### §5 的三个当心点是否足够

**不够。** 除 plan 已列的 reasoning、item id、output index 外，至少还必须加入五项：item-specific event 与 terminal root fidelity；`BlockBuffer` 的 `until-tool-use` release trigger；raw payload 与预渲染事件的容量记账；翻译专用 `cut_short`/hand-over 对直连腿的隔离；`Terminal` 到完成日志/TUI 的原生 item 分类。Spec-first 与 D2 strict unknown 是更上游的两道门，不应只写成“实施时当心”。

### keepalive、背压与终局状态

- keepalive：机制只依赖最后一次客户端写入，和 payload 无关；只要 direct delivery 仍由同一串行 yield 驱动，成立。
- 背压：yield 期间停止 pull 的结构成立；但 raw block 的内存 charge、双份 added/done 编码和 `until-tool-use` 时点未定义，当前方案不足以宣称背压保证完整保持。
- `cut_short`：不成立，finding 04 已给反例；直连必须绕开。
- `hand_back_block`：对 Responses client 明确不适用；正因如此，不能先丢 incomplete item 等待 hand-over。
- `DeliverySession.committed_count`：按实际 delivered list 计，一 delivery unit 一次 offer 时会自然正确，无需从 payload 派生。
- `decide_stream_ending`：只读 terminal/position/count facts，保持可用；mode-specific assembler 必须提供 truthful `terminal.seen`。
- `Terminal.stop_reason`：可作为内部摘要，不能做 direct Responses wire 的权威；翻译 unknown item 时不应产生成功 stop reason。
- `Terminal.usage`：现有 `upstream_usage` 可保住标准 `usage`，但不覆盖 `tool_usage` 与 future root fields，所以“usage 对”只能限定到标准 usage object。

### 更简单的实现路线

**偏好：在 `delivery_policy` 早分流到专用 `ResponsesPassthroughAssembler`/delivery unit，而不是继续扩张一个同时产 Anthropic block 与 raw Responses item 的 `ResponsesAssembler`。** 它仍解析到 item 完成边界以维持 block-level delivery、keepalive、retry position 与 backpressure，但不做 Anthropic IR 映射；翻译 assembler 则继续专注 Anthropic block pair、carrier 与 strict conversion。

“整个 SSE 收齐后原字节一次交付”更短、更保真，也天然支持 future events，但会把默认 block policy 变成 full-response，延迟与内存占用更大；现有 `one_shot_delivery` 还没有 keepalive、replay、cap。因此它适合作为 full buffering policy 的实现候选，不是无代价替换。把 client-leg boolean 塞进现有 assembler 是最小 diff，却让两套互斥语义共享最多状态；从长期边界看不是我的首选。

### 实施前最低限度的可判失败用例

这不是新 gate，只是与本方案变更面直接对应的现有测试补强方向：

1. direct `custom_tool_call` 携带自由文本 input 与专有事件，按新 Spec 的 fidelity 层级断言客户端观察结果；
2. direct `web_search_call` 不产生 Anthropic 块对；translated 同一样本必须产生块对；
3. direct reasoning `encrypted_content` 交付后原样 echo 到下一请求，断言送往上游的值与必要 opaque id 不被 carrier 改写；
4. 已有一个完成 item 后再来 `status: incomplete` item，terminal reason 命中 hand-over 配置时 direct client 仍收到该 item；
5. `block`、`full`、`until-tool-use` 三种 policy 下 direct function/custom call 的 release 时点与 cap；
6. translated unknown item 在首块前与已提交块后分别产生合法错误，不产生 `message_stop`/正常 terminal；non-stream 同样失败而非丢弃；
7. terminal `usage`、`tool_usage` 与一个未知根字段按 Spec 的保真层级断言，防止“items 保真、response 根仍丢”。

## 已排除掉的可能性

1. **“reasoning carrier 必然与直连原生 `encrypted_content` 冲突”——排除。** 前提是正确的 same-format 早分流；请求 translator 根本不运行，响应也不进 carrier writer。若实现复用 `_reasoning()`，则不在本排除范围内。
2. **“active footer 是第四个直接 payload 语义消费者”——排除。** `ActiveRequestRegistry` 只记录 model、elapsed、bytes、attempts；但完成日志/TUI 经 `RequestContext.reply → Terminal → RequestLine` 间接消费 tools/thinking/stop reason，这是真实影响，已列 finding 03。
3. **“keepalive 需要理解 item 内容”——排除。** 它只看客户端最后写入时间；item kind 影响的是何时有真实写入，不影响计时器本身。
4. **“`DeliverySession.committed_count` 或 `decide_stream_ending` 需要读取 raw payload”——排除。** 前者是 `len(delivered)`，后者只读位置布尔值与计数。
5. **“直连 non-stream 也在做同一次往返翻译”——排除。** `response_payload()` 在 `translation_required=False` 时直接返回上游 body；本方案层一的问题定义应明确收窄到 stream delivery。
6. **“放宽 `ResponsesFramer.block` 的 unknown raise 就能彻底修”——排除。** 它只会把响亮失败换回空块/错误形状，且无法恢复专有事件与 terminal root；现有 raise 应保留在翻译 framer。
7. **“层一和 hosted web-search 块对产品作用域冲突”——排除。** client leg 条件可使两者互斥；未排除的是它们在同一类和同一状态机里的实施冲突，见 finding 06。
8. **“文本降级是 unknown item 的通用无损兜底”——排除。** `custom_tool_call.input` 已是自由文本反例，future typed fields 更无法一般化；且当前 Spec 明确 REJECT。

## 搜索面与证据限制

### 读过的判据来源

- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/request-pipeline.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-translation.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/api.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/spec.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md`
- `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md`
- `/home/xp/src/ghc-api-proxy-py/CLAUDE.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260830-custom-tool-call-forensics.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/reports/260830-native-block-pair-gap-reconciliation.md`

### 读过的主要实现面

`delivery/assembling.py`、`delivery/blocks.py`、`delivery/formats/openai_responses.py`、`delivery/formats/anthropic_messages.py`、`delivery/stream.py`、`delivery/framing.py`、`delivery/sse_source.py`、`delivery/sse_frame.py`、`delivery_policy.py`、`translation_driver/responses.py`、`translation_driver/openai_responses.py`、`pipeline/reply.py`、`pipeline/request.py`、`pipeline/driver.py`、`pipeline/retry.py`、`pipeline/hand_over.py`、`observability/request_log.py`、`observability/active_requests.py`、`observability/footer.py`、`observability/tui.py`。

### 能力限制与证据权重

本会话绑定在隔离工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue2-custom-tool-call`。对主树执行只读 Bash 时，守卫以“无法证明命令停留在本工作树”为由拒绝；我按任务要求没有绕过，后续全部用绝对路径 `Read`。因此未能执行 `rg` 全仓消费者穷举、Git HEAD/status 核验或测试，也未能用命令证明读到的工作树 bytes 恰好等于 commit `78030df`；`reviewed_at_rev` 采用调用方给定值。

证据分级如下：Spec 冲突、`BlockBuffer`/`Terminal`/`cut_short` 的源码反例和 reasoning request 分流均是**强到可直接行动**的静态证据；“全仓不存在别的 payload consumer”**未验证，不得作否定性全称断言**；专用 passthrough assembler 优于布尔 mode 是**架构判断**，理由充分但不是事实；whole-response passthrough 的成本比较是**强趋势，需用目标 policy 与流量大小决定**。

History、hooks 是否有未通过 `Terminal` 的直接 `CompletedBlock.payload` 消费，因无法全仓检索而保持 `unverified`。这不改变 verdict：已确认的 size/policy/observability 消费者和 Spec 冲突已经独立足够推翻当前承重论据。

## 我最没把握的三个判断

1. **专用 assembler 是否一定优于现有 assembler 的显式 mode。** 这是长期边界判断，不是正确性事实；若 mode 能在入口单分支并让两套状态完全互斥，小 diff 也可能足够。当前偏好专用类型，因为两项并行工作都在改 `_close`。
2. **direct client 对被省略的每一种 item-specific event 的实际后果。** 没有运行真实 OpenAI SDK/客户端；有些客户端只取 final snapshot，可能不受影响。但“事件观察不同”本身已成立，且足以否定“原样/future-proof”，不依赖某个客户端必崩。
3. **whole-response raw passthrough 的实际内存与延迟是否可接受。** 未测流量分布；报告只把它列为最简保真基线并明确代价，没有建议默认采用。

## 执行本评审时遇到的摩擦

- 主树 Bash 被工作树守卫拒绝，无法机械穷举；未绕过。
- 目标报告目录位于主工作树 `.dev/`，`Write` 被同一隔离守卫拒绝；按调用方预案写入 `/tmp/260830-review-passthrough-plan.md`，需调用方搬到目标路径。
- 未运行测试或探针；本次对象是未实施方案，所有代码结论均为指定快照的静态路径分析。
- 本报告本身未再派独立 agent 复审：当前角色是 leaf executor，且任务明确禁止再派 agent；该终态审阅义务交回调用方处置，不以自审冒充独立复审。

## 严重度汇总

- blocker: 1
- major: 5
- minor: 1
- nit: 0
- finding_total: 7

## 交付声明

- delivery_complete: true
- completed_at: 2026-08-30
- finding_total: 7
- blocker: 1
- major: 5
- minor: 1
- nit: 0
