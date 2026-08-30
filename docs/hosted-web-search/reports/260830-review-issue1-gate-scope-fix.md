---
report_id: issue1-gate-scope-review
attempt_id: issue1-gate-scope-review-01
status: in-review
reviewed_at_rev: 9d67978ef9e3e9a142855bbe749a34bc8bc484c6
reviewed_at: 2026-08-30T17:30:32+00:00
reviewer_role: independent-reviewer
---

# GitHub issue #1 gate scope 修复独立评审

## 评审范围

被评对象是提交 `9d67978ef9e3e9a142855bbe749a34bc8bc484c6` 相对其父提交的改动，以及该提交最终树中与改动相接的路由、翻译、合成回复、块交付、缓冲回复与 token counting 路径。提交直接改动的文件是 `src/app/pipeline/subscribers/hosted_web_search.py`、`tests/int/test_pipeline_app.py`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py`；为判断系统状态，评审还沿调用链读取了 `driver.py`、`delivery_policy.py`、`reply.py`、`delivery/stream.py`、`hand_over.py`、`subscribers/server_tools.py`、translator registry、路由表与 HTTP 入口。

明确不在本次范围内：hosted web search 尚未实现的成功响应原生块对、citation、domain restriction 默认值等既有遗留项；真实 Copilot upstream 能否执行某个模型的 web search；修复被评对象。未修改 `src/` 或 `tests/`，只在 `/tmp/issue1-review-9d67978` 提取了提交快照并写了独立探针。

评审时原 worktree 已出现提交后的未提交改动，涉及 `src/app/pipeline/driver.py`、`delivery_policy.py`、`reply.py` 与 `tests/int/test_pipeline_app.py`。为避免把并行改动误算进 `9d67978`，源码定位以 `git archive 9d67978` 提取到 `/tmp/issue1-review-9d67978` 的精确快照为准，所有决定 verdict 的执行探针也以该快照的 `src` 为 `PYTHONPATH`。未评审这些后续未提交字节。

## 总体 verdict

**needs-fix。** `gate_hosted_web_search` 新增的 `inbound_format` 判据对本门当前职责是正确的，直接 Responses→Responses 的流式与缓冲路径均恢复了透传；但提交没有关闭同一失效类的另一条当前可达路径，且行为规格尚未先行更新。

## blocker 数

**1。** 另有 major 1、minor 1。

## 判据来源与权威顺序

1. 当前评审请求中的用户一手裁决：2026-08-30 对原生 Responses 客户端声明 `{"type":"web_search"}` 的处置选择“放行到上游”。该裁决比尚未修订的活规格更新，但其耐久权威落点仍必须回到规格。
2. `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/request-pipeline.md:7-13`：路由必须判断输入格式与目标格式，并在翻译路径把响应翻回客户端格式；`docs/.human-controlled/api.md:5-10`：`/responses` 是 OpenAI Responses 客户端端点；`docs/.human-controlled/message-translation.md:3-5`：翻译由 inbound 与 outbound translator 组成；这些是用户亲笔文档，优先于 agent 推导文档。
3. `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` §1、§8.3、§9.0、§13：当前规格只覆盖 Anthropic Messages 客户端→Responses upstream 的 hosted web search，能力门失败时合成的是 Anthropic block pair，并明确排除 count_tokens 与 Anthropic 直连腿的行为改变。当前评审请求已说明 2026-08-30 的新裁决尚未写入此活文档。
4. `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate/.claude/rules/00-development-workflow.md:9-14`：完整行为规格必须先于可观察实现变化，且 Spec-level fact 不得停在消息、报告、代码注释或测试中；规格修订还必须记录 revision。
5. `/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:9-21`：功能总开关与模型清单只描述 Anthropic 声明翻到 Responses upstream 后的能力门；该文档也承认规格是活文档并曾发生分叉。

## 发现

### issue1-gate-scope-review-01

- `finding_id`：`issue1-gate-scope-review-01`
- `severity`：blocker
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:36-40`
- `related_locations`：`/tmp/issue1-review-9d67978/src/app/pipeline/subscribers/hosted_web_search.py:94-100`；`/tmp/issue1-review-9d67978/tests/int/test_pipeline_app.py:2516-2548`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate/.claude/rules/00-development-workflow.md:9-14`
- 判据出处：项目工作流 `00-development-workflow.md:9-14`；当前用户请求明确确认“这次改动尚未写进去”。
- 发现：提交已经改变原生 Responses 客户端的可观察行为，但当前活规格 §1 仍把完整产品范围限定为 Anthropic Messages client→Responses upstream，且没有记录 direct Responses declaration 绕过 translation capability gate 的新规则。新规则目前只停在提交信息、源码注释、测试 docstring 与本次对话里，正是项目工作流明令禁止的 Spec bypass 形状。
- 证据：`9d67978` 的 `hosted_web_search.py:94-100` 在 direct Responses inbound 上提前返回；新增 integration test 把“即使功能关闭仍透传”写成 acceptance oracle；规格修订记录最后一条仍是 2026-08-24，§1、§8.3、§9.0、§13 均未纳入 direct Responses 行为。当前用户请求不是缺失意图，反而直接确认了“裁决已有、规格待补”的事实。
- 影响：在规格更新前，该提交不能按本仓“Spec 先行、活文档及时修订”的硬约束进入下一阶段。后续读者若只读规范，会把 direct Responses 行为判为不在产品契约内；若只读代码，又会把本门的范围解释当成规范。这不是实现正确性推断，而是权威源已经落后于明确裁决。
- 建议：由拥有该活规格修改权的一方在进入下一阶段前修订 §1、§8.3、§9.0、§13 及 revision record，明确 direct Responses declaration 不受这条 Anthropic translation feature switch／capability list 支配，并说明按 upstream target format 分流时的边界。同步检查规格内所有“能力门一律处理 Responses 腿声明”的转述，避免只改 §1 留下内在冲突。
- 结论强度：**强，足以阻止进入下一阶段。** 前提是项目工作流仍适用于本次提交；它直接写明“不可协商”，且当前用户只声明稍后补规格，没有声明取消该约束。若此前提为假，本 finding 的 blocker 结论失效，但实现正确性 findings 不受影响。

### issue1-gate-scope-review-02

- `finding_id`：`issue1-gate-scope-review-02`
- `severity`：major
- `primary_location`：`/tmp/issue1-review-9d67978/src/app/pipeline/driver.py:190-198`
- `related_locations`：`/tmp/issue1-review-9d67978/src/app/pipeline/subscribers/server_tools.py:32-40,198-248`；`/tmp/issue1-review-9d67978/src/app/pipeline/delivery_policy.py:29-46,49-78`；`/tmp/issue1-review-9d67978/src/app/pipeline/reply.py:19-40`；`/tmp/issue1-review-9d67978/src/app/pipeline/translation_driver/registry.py:139-165`；`/tmp/issue1-review-9d67978/src/app/server/routes/table.py:28-50`；`/tmp/issue1-review-9d67978/tests/int/test_pipeline_app.py:2516-2548`
- 判据出处：`docs/.human-controlled/request-pipeline.md:9-13` 要求翻译路径的回复回到客户端格式；`docs/.human-controlled/api.md:5-10` 把 `/responses` 定义为 OpenAI Responses 客户端端点；当前评审请求特别要求检查是否仍有合成 Anthropic 回复交给非 Anthropic framer 的路径。
- 发现：`9d67978` 只阻止 hosted gate 在 Responses→Responses 路径抛 `WebSearchNotExecutable`，但 `driver.handle()` 对任何来源的 `WebSearchNotExecutable` 都无条件合成 Anthropic reply。当前仍有另一位 producer：当 `/responses` 请求选择只支持 `/v1/messages` 的模型时，routing 建立 Responses→Anthropic 翻译路径，`builtin:server-tool-capability` 在 Anthropic target leg 拒绝裸 `web_search`，随后 `driver.py:191-197` 把该拒绝改成 Anthropic `server_tool_use`／`web_search_tool_result` 回复。流式侧仍把它交给按 client inbound 选择的 `ResponsesFramer`；缓冲侧 `response_payload()` 因 `synthesized` 直接返回 Anthropic body。
- 执行证据：在精确 `9d67978` 快照上向 `/responses` 发送 `model="claude-model"`、`tools=[{"type":"web_search"}]`。流式探针未调用 upstream，`HandledRequest.synthesized=True`，随后复现 `ValueError: no Responses item shape for block kind 'server_tool_use'`，日志显示已经进入 `H1/H1 200` 后 stream failure。相同请求去掉 `stream` 后返回 HTTP 200，body 为 `{"type":"message","content":[{"type":"server_tool_use"},...]}` 而非 Responses object，日志错误记为 `ok`。两条均是当前 route table 与默认 translator registry 可达，不是未来假设。
- 影响：issue #1 的同族故障仍可由合法 `/responses` endpoint 与当前模型路由触发。流式请求再次在 200 后撕流；非流式请求更隐蔽地以成功状态交付错误协议并记成功日志。新增 integration test 只选 `gpt-model`，使 target 与 inbound 都是 Responses，因此覆盖不到这一条 Responses→Anthropic crossing。
- 建议：在合成的所有权处关闭，而不是让 `ResponsesFramer` 学会写 Anthropic blocks。具体应将 `driver.handle()` 的 failed-search synthesis 限定为 `context.inbound_format is WireFormat.ANTHROPIC_MESSAGES`；其他 inbound 保留 `WebSearchNotExecutable`，由现有 error-envelope 路径按客户端协议返回。补充 `/responses` + Anthropic-only target 的流式与缓冲回归用例，分别钉住“不撕流／不返回 Anthropic 200”。同时改正 `delivery_policy.delivers_blocks` 与 `reply.response_payload` 对 `synthesized` 的无条件保证；它们依赖 producer invariant，自身并未实施该保证。
- 结论强度：**强，足以要求修复。** 前提是当前 route table 允许 Responses client fallback／mapping 到 Anthropic Messages target；`server_tools.py:37` 与执行探针都直接证明可达。若此前提为假，两个实跑反例将无法产生，但它们在 `9d67978` 上已产生，故不是待验证假设。

### issue1-gate-scope-review-03

- `finding_id`：`issue1-gate-scope-review-03`
- `severity`：minor
- `primary_location`：`/tmp/issue1-review-9d67978/src/app/pipeline/subscribers/hosted_web_search.py:29,94-99`
- `related_locations`：`/tmp/issue1-review-9d67978/tests/int/test_pipeline_app.py:2517-2521`；`/tmp/issue1-review-9d67978/tests/unit/pipeline/subscribers/test_builtin_subscribers.py:438-445`；提交 `9d67978` 的 commit message
- 判据出处：当前评审请求要求逐句核对新注释与 docstring；`hosted-web-search-spec.md` §1 给出的可靠边界是 Anthropic client→Responses upstream 的 crossing，而不是某个对象的作者 provenance。
- 发现：新增文字把正确的 scope predicate 过度表述成 provenance predicate。`inbound_format is ANTHROPIC_MESSAGES` 不能证明 `{"type":"web_search"}` 是代理写的；它只能证明请求来自 Anthropic endpoint。精确快照探针显示，一个 Anthropic inbound 自己携带 Responses-shaped `{"type":"web_search"}` 时，translator 会原样保留该对象，随后 gate 仍会判断它。因此“Only a declaration this proxy wrote may be judged here”“the inbound format is the only thing that says which those are”不是事实。相同文字还三次声称两个拼法是“four identical bytes”；ASCII `web_search` 本身是 10 bytes，完整 JSON object 更不可能是 4 bytes。
- 影响：运行时判据对本次已裁 scope 仍然正确，所以不升级为行为 major；但注释把“限定一条 crossing”误写成“证明对象作者”，会让以后扩 translator 或处理混合 vocabulary 的读者基于一个代码并未保证的不变量推理。错误 byte 数又削弱了这段根因说明的可信度。
- 建议：把文字统一改为“该 gate 只管 Anthropic→Responses crossing；direct Responses inbound 由其 upstream contract 自己决定”，不要声称识别了 declaration provenance。将“four identical bytes”改为“the same spelling／the same tool object”。不要顺手改变 Anthropic endpoint 对外来 Responses-shaped tool 的行为；该行为不在本次用户裁决与规格范围内，需要另行判定。
- 结论强度：**强，足以修正文档但不支持扩展行为。** 前提是 translator 对外来 typed tool 仍原样保留；精确快照探针已观察到这一结果。若未来 translator 改为拒绝该输入，provenance 反例会关闭，但“four bytes”仍然错误。

## 对特别关注项的逐项结论

### 判据宽窄与 translator registry

当前判据在 `gate_hosted_web_search` 内**不窄也不宽**。默认 registry 不是逐对登记，而是分别登记两种 inbound reader 与两种 outbound writer：`ANTHROPIC_MESSAGES` 和 `OPENAI_RESPONSES`（`registry.py:139-165`），因此当前可翻译 crossing 是 Anthropic↔Responses；same-format route 不翻译。Chat Completions、Embeddings 没有 inbound/outbound translator，Gemini route 还是 `implemented=False`。所以当前没有第三条 inbound leg 会把 hosted search 翻成 `{"type":"web_search"}` 后被新增判据误放行。

门内条件的真实含义是 `inbound_format == ANTHROPIC_MESSAGES` 且紧随其后的 `target_format == OPENAI_RESPONSES`，即 Anthropic→Responses crossing。只看 `target_format` 会再次误抓 direct Responses；只看 payload 无法区分；只写 `translation_required` 在当前 registry 下碰巧等价，但会把未来第三种 source format 默认为本 gate 的职责。显式写 Anthropic source 与 Responses target 更符合现行规格 §1。

### `/v1/messages/count_tokens`

该 endpoint 在 route table 中固定 `inbound_format=ANTHROPIC_MESSAGES`（`server/routes/table.py:29-35`），`build_context` 逐字把 route format 写入 context（`server/inbound.py:60-70`）。若 resolved target 是 Responses，`handle_count_tokens` 先做 Anthropic→Responses translation，再在发布 `attempt.prepare` 前设置 `COUNTING_ONLY`（`driver.py:262-283`）。新增 guard 在这条腿不会提前返回，之后原有 `COUNTING_ONLY` 分支仍返回，因此本次改动不改变计数行为。精确快照 targeted test `test_the_counting_leg_measures_rather_than_refusing_on_the_responses_leg_too` 通过。

### 其他 synthesized Anthropic→非 Anthropic 路径

`_answered_auto_mode` 的入口已在 `driver.py:137-155` 以 Anthropic inbound 门控，当前不可把 Anthropic body 交给其他 client framer。`ContinuationSupport.synthesize` 最终调用 `hand_back_block`，后者在 `hand_over.py:222-242` 对非 Anthropic `wire_format` 返回 `None`，也不可达。完整回复 synthesis 的另一个入口 `_answered_failed_search` 则存在 finding 02 所述当前可达缺口，因此 `delivery_policy.py:43` 的“whatever the route was”不是构造性保证，而是错误陈述。

应显式加固，但加固点是 synthesis producer 的 client-format precondition，而不是 `ResponsesFramer`。让 Responses framer 接受 `server_tool_use` 会把不合法协议包装得更深；让 driver 对非 Anthropic client 不合成，才会在 headers 发出前走现有 error envelope。

### 缓冲路径

对 issue 原始的 Responses→Responses route，本次 guard 与 `stream` 无关，已覆盖缓冲路径。精确快照探针确认 declaration 原样发往 upstream，client 收到 Responses body。可是 `reply.py:25-28` 对任意 `synthesized` 直接 `return body` 的同族缺陷仍由 finding 02 的 Responses→Anthropic route 触发：实跑得到 HTTP 200 + Anthropic Message body。这一侧不是理论风险，而且比流式异常更安静。

### 新增测试的分辨力

两条新增测试总体有分辨力，不是钉名字：unit test 同时验证 direct Responses 不拒绝与 Anthropic control 仍拒绝；integration test 断言 upstream 实收 `tools == [{"type":"web_search"}]`，并断言客户端最终拿到 `response.completed`。按用户提供的已核实背景，把新增 guard 变异为 `if False` 时两条都红；精确 `9d67978` 快照上两条新测试与 count-token control 共 3 tests passed。因此它们足以证明新增 gate predicate。

缺口在 coverage 边界，而非现有断言形状：integration test 固定选择 Responses-capable `gpt-model`，没有覆盖同一 `/responses` declaration 被路由到 Anthropic target 后由另一个 subscriber 抛出同一异常。finding 02 的反例说明应补 crossing control。

### 新注释与 docstring

关于 direct Responses declaration 与 translated Anthropic declaration 在 payload 中同形、payload 不能判 origin、`inbound_format` 应参与 scope、原始 stream 因 Responses framer 不认识 Anthropic block 而撕裂，这些核心叙述成立。关于“只有代理写的 declaration 才会被判断”“inbound format 能识别作者”“four identical bytes”的绝对叙述不成立，见 finding 03。`delivery_policy.delivers_blocks` 的既有 docstring 仍声称 synthesized reply 在任何 route 都可交付，也不成立，且已由 finding 02 实跑反证。

## 考虑过但排除掉的可能性

1. **新增 `inbound_format` guard 会误放行另一条现存 translator source。** 排除。registry 当前只有 Anthropic 与 Responses reader/writer；除 direct Responses 外，没有第三种已实现 source 能到 Responses target。
2. **`/v1/messages/count_tokens` 会因新 guard 提前返回而改变。** 排除。它的 inbound 固定为 Anthropic，仍会到达原有 `COUNTING_ONLY` exemption；targeted test 通过。
3. **`_answered_auto_mode` 仍能回答非 Anthropic client。** 排除。入口明确以 Anthropic inbound 门控。
4. **`ContinuationSupport.synthesize` 仍能把 Anthropic `tool_use` 交给 Responses framer。** 排除。`hand_back_block` 对非 Anthropic wire 返回 `None`。
5. **修复 `ResponsesFramer` 以接受 `server_tool_use` 是合适的同族加固。** 排除。这会让 Responses client 收到不属于其协议的语义对象；正确边界是在 synthesis producer 上拒绝非 Anthropic client。
6. **缓冲 primary route 仍受原 bug 影响。** 排除。新增 guard 与 `stream` 无关，精确提交快照的实跑确认 direct Responses→Responses 非流式请求透传并收到 Responses object。
7. **unit test 只靠函数名或注释变绿。** 排除。断言落在异常／无异常控制对，integration 断言落在 upstream 实收 payload 与 terminal event；已提供的控制变异会打红。
8. **为证明 finding 02 必须调用真实 Copilot upstream。** 排除。该失效发生在 routing、subscriber synthesis 与 client framing，探针断言 upstream 零调用；使用 real upstream 不会增加对该命题的判别力。
9. **Anthropic inbound 自己写 Responses-shaped tool 应在本次顺手改行为。** 排除。它只用来反证注释的 provenance claim；hosted web search 规格与本次用户裁决都没有规定该 malformed／cross-vocabulary 输入的产品行为。
10. **规格尚未更新只是措辞 nit。** 排除。项目工作流把 Spec 先行与 revision record 定为不可协商的行为权威约束，因此记录为 blocker；用户已经明确保留后续补写动作，解除条件清楚。

## 搜索面与执行证据

读取的判据包括：完整 `hosted-web-search-spec.md` 的文档状态、§1、§3、§5～§9、§11～§14；完整 `hosted-web-search/status.md`；human-controlled 的 `README.md`、`api.md`、`request-pipeline.md`、`message-translation.md`、`message-format-reshape.md`、`client-side-block-delivery.md`、`ghc-api.md`、`upstream-retry-and-continuation.md` 及 `config.example.yaml` 相关段；项目 `CLAUDE.md` 与 `00-development-workflow.md`。

读取的实现面包括：提交完整 diff；`request.py`、`routing.py`、`driver.py`、`reply.py`、`delivery_policy.py`、`delivery/stream.py`、`delivery/formats/openai_responses.py`、`hand_over.py`、`subscribers/hosted_web_search.py`、`subscribers/server_tools.py`、`subscribers/counting.py`、`translation_driver/registry.py`、两侧 request translator、server route table、inbound context builder、inference route；并扫描所有 `synthesized=True`、`WebSearchNotExecutable`、`ContinuationSupport`、translator registration 与 count-token call sites。

执行证据均钉在精确 `9d67978` 快照：新增 unit、integration 与 count-token control 共 3 passed；direct Responses→Responses 缓冲探针透传 exact tool 并返回 Responses body；Responses→Anthropic 流式探针复现 200 后 `ValueError`；同 route 缓冲探针复现 HTTP 200 + Anthropic Message body；provenance 探针复现 Anthropic inbound 的 Responses-shaped tool 被原样翻译后仍由 gate 判断。用户提供的全套 `1937 passed / 2 skipped`、Ruff、Pyright 与 `if False` 控制变异作为已核实背景采信，未重复运行全套。

未覆盖面：没有真实 upstream 调用；没有评审原 worktree 中 `9d67978` 之后的未提交修复；没有重新评审 hosted web search 的既有未实现功能；没有检查与本失效类无调用关系的模块。以上均不影响三个 findings 的成立度。

## 整体判定

`9d67978` 对 issue 报告中的 Responses→Responses hosted gate 误判给出了正确、分辨力充足的修复，且没有改变 count-token 腿；但它还不是可进入下一阶段的完整候选。必须先补活规格，并关闭当前可达的 Responses→Anthropic failed-search synthesis 路径。完成这两项后，minor 的注释修正不应被遗漏，但不会单独阻断核心功能。

## 我最没把握的三个判断

1. **把未更新规格定为 blocker 而非 major。** 依据是本仓工作流逐字说“complete behavioral Spec comes first”且“not negotiable”；不确定点只在当前用户“稍后会补”是否意在临时覆盖顺序约束。我的判定是没有明确豁免，所以 blocker。调用方若持有用户对顺序的额外逐字授权，应重定级，但仍须补规格。
2. **finding 02 的正确 fallback 是客户端协议 error envelope。** 确定的是不能发 Anthropic synthesis；“保留 `WebSearchNotExecutable`”利用现有 400 mapping，且精确快照已展示其格式。若用户希望 Responses→Anthropic route 另有业务语义，需要单独裁决；这不会推翻当前 200 撕流／错协议是 major。
3. **finding 03 是 minor 而非 nit。** 它不改变当前合法 scope 的行为，但 provenance 绝对句与 byte 数在源码、两条测试和 commit message 中重复，并正处于本次根因解释的承重位置；因此我认为它超过纯文字润色。若调用方把维护误导视为不影响结论，可降为 nit，不影响其他计数。

## 执行本契约时遇到的摩擦

原 worktree 在评审期间出现未提交并行改动，恰好修改了本次必须检查的 synthesis 路径。直接从 worktree import 会把目标提交与后续修复混在一起，第一次 sibling probe 因此返回了后续版本的 400。发现 `git status` 与 runtime source 不一致后，改用 `git archive 9d67978` 的 `/tmp/issue1-review-9d67978` 快照重跑全部决定性探针；报告只引用该快照与提交态。除此之外无工具、权限或文件阻塞。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-08-30T17:30:32+00:00`
- `finding_total: 3`
- `blocker_count: 1`
- `major_count: 1`
- `minor_count: 1`
- `nit_count: 0`
