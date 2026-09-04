---
report_id: issue1-gate-scope-review-round2
attempt_id: issue1-gate-scope-review-round2-01
status: in-review
reviewed_at_rev: 5948cb4e809874731f8fdb00011db4555feef78b
reviewed_at: 2026-08-30T17:36:51+00:00
reviewer_role: independent-reviewer
prior_report: /home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/reports/260830-review-issue1-gate-scope-fix.md
prior_reviewed_at_rev: 9d67978ef9e3e9a142855bbe749a34bc8bc484c6
---

# GitHub issue #1 gate scope 修复合并态复评

## 评审范围

被评对象是候选 `5948cb4e809874731f8fdb00011db4555feef78b` 的最终代码与测试状态，重点是提交 `5948cb4` 相对已评 `9d67978` 的第二刀，以及两条提交组合后的接缝。直接改动面为 `src/app/pipeline/driver.py`、`delivery_policy.py`、`reply.py`、`subscribers/hosted_web_search.py` 与两份测试文件；系统状态检查继续沿 `WebSearchNotExecutable` 的全部 producer、`HandledRequest.synthesized` 的全部 writer、错误分类与方言 writer、translator registry、routing、流式 framer 和缓冲 response translation 展开。

按本轮明确范围，不重复计算活 hosted-web-search Spec 尚待更新的 blocker；它仍由调用方另行处理。本轮只评代码与测试。没有修改 `src/` 或 `tests/`，没有调用真实 upstream。

## 总体 verdict

**needs-fix。** `5948cb4` 独立关闭了上一轮 major 指出的 Responses→Anthropic crossing：流式与缓冲请求都在提交 HTTP 200 前得到 Responses 方言的 400 error envelope，且所有 Anthropic inbound 的 web search synthesis 保持不变。合并态仍暴露一条同一 exception/synthesis 接缝上的既有 major：Anthropic `web_fetch` 拒绝也被当作 failed web search 合成。另有两个 minor 注释事实问题，其中一个是上一轮未关闭，另一个由第二刀新引入。

## blocker 数

**0。** major 1、minor 2。

## 判据来源

1. `docs/.human-controlled/api.md:5-10`、`request-pipeline.md:7-13` 与 `message-translation.md:3-5`：client endpoint 决定 inbound dialect，翻译路径的回复必须按 client dialect 写出。
2. `.dev/docs/error-envelope/spec.md` §2、§5.1、§6.1～§6.3、§7：本代理产生的 `TranslationRefused` 是 `CLIENT`／HTTP 400，保留异常自带 `code` 与 `field_path`，并由 inbound wire 的 error writer 写出；OpenAI Responses 的 JSON error 是 `{"error":{"message", "type", "param", "code"}}`。
3. `.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` §1、§8.3、§13：failed search block pair 是 Anthropic web search 路径的回答；`web_fetch` 不属于 hosted web search 本规格，并继续显式拒绝而非借本功能恢复。
4. 本轮任务的直接判据：核验两个 `WebSearchNotExecutable` producer、所有 synthesized reply writer、400／code 的方言正确性、上一轮 minor、测试分辨力与新引入问题；Spec blocker 本轮不计。

## 上一轮发现处置

| 上一轮 finding | 本轮状态 | 独立核验 |
|---|---|---|
| `issue1-gate-scope-review-01` Spec 未先行更新 | 本轮按明确范围不复评、不计数 | 调用方已声明另行完成 Spec；本报告不把该声明改写成已完成 |
| `issue1-gate-scope-review-02` Responses→Anthropic 仍拿到 Anthropic synthesis | **closed** | `driver.py:191` 只对 Anthropic inbound 合成；新参数化测试两例通过；独立探针验证 stream false／true 均为 400 OpenAI error、`upstream calls == 0` |
| `issue1-gate-scope-review-03` provenance／“four bytes” 假叙述 | **not-closed** | `hosted_web_search.py:29,95-99` 与两条首轮测试 docstring 未修改，精确问题仍在 |

## 发现

### issue1-gate-scope-review-round2-01

- `finding_id`：`issue1-gate-scope-review-round2-01`
- `severity`：major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate/src/app/pipeline/driver.py:191-203`
- `related_locations`：`src/app/pipeline/subscribers/server_tools.py:32-40,198-248`；`src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py:75-115`；`tests/unit/pipeline/subscribers/test_subscribers_server_tools.py:71-83`
- 判据出处：hosted-web-search Spec §13 将 `web_fetch` 明确排除并要求继续显式拒绝；human-controlled request pipeline 要求回复表达客户端实际请求，而不是替换成另一种工具。
- 发现：failed-search synthesis 的 inbound guard 本身正确，但它仍以 exception class 而不是 server-tool family 判语义。`server_tools._refuse_declarations()` 对 `web_search*` 与 `web_fetch*` 都抛同一个 `WebSearchNotExecutable`；`driver.py:191-203` 对任何 Anthropic inbound 的该异常都调用 `_answered_failed_search()`；该 writer 固定产出 `name="web_search"` 与 `web_search_tool_result`。因此 Anthropic 客户端声明 `web_fetch_20250910` 时，代理不返回 web-fetch refusal，而以 HTTP 200 告诉客户端“一次 web_search 失败”。
- 执行证据：在 clean HEAD `5948cb4` 上 POST `/v1/messages`，模型 `claude-model`，工具 `{"type":"web_fetch_20250910","name":"web_fetch"}`。upstream 调用为 0，返回 HTTP 200；body 的第一块是 `server_tool_use name="web_search"`，第二块是 `web_search_tool_result`，query 甚至来自整条 fetch prompt。现有 unit test 只断言 subscriber 抛 `TranslationRefused`，没有穿过 driver 检查最终 wire。
- 影响：一个被显式拒绝的工具被回答成另一种工具的正常 200 失败结果，改变客户端 transcript 的事实与后续动作。它不是 `5948cb4` 新引入的回归，但位于本轮被要求穷举的第二个 exception producer 与同一 synthesis branch 上，是合并候选当前可达的正确性缺陷。
- 建议：让只有 web search refusal 使用 `WebSearchNotExecutable`／failed-search synthesis。`web_fetch` 在未有独立产品裁决与正确 result shape 前应保留为普通 `TranslationRefused`，由现有 400 error envelope 返回；若未来要为 web_fetch 合成失败，须使用自己的 `server_tool_use name="web_fetch"` 与 `web_fetch_tool_result`，不能复用 search writer。补一条穿过 `/v1/messages`→driver→wire 的 web_fetch 回归，而非只测 subscriber 抛异常。
- 结论强度：**强，足以要求修复。** 前提是 `web_fetch` 进入 `_REJECTED_TYPE_PREFIXES` 且仍抛 `WebSearchNotExecutable`；源码与实跑均确认。若产品另有“把 web_fetch 故意改写成 web_search”裁决，本 finding 会失效，但指定判据与现有文档没有该裁决，且 §13 指向相反方向。

### issue1-gate-scope-review-round2-02

- `finding_id`：`issue1-gate-scope-review-round2-02`
- `severity`：minor
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate/src/app/pipeline/subscribers/hosted_web_search.py:29,94-99`
- `related_locations`：`tests/int/test_pipeline_app.py:2516-2521`；`tests/unit/pipeline/subscribers/test_builtin_subscribers.py:438-445`；提交 `9d67978` 的 message
- 判据出处：本轮要求复核上一轮 minor；hosted-web-search Spec §1 的可靠边界是 Anthropic→Responses crossing，不是 declaration 作者 provenance。
- 发现：上一轮 minor 原样保留。`inbound_format` 不能证明 `{"type":"web_search"}` 是代理写的；Anthropic inbound 自带该 Responses-shaped object 时 translator 会原样保留，gate 仍判断它。文字还反复称 `web_search` 两种来源是“four identical bytes”，而该 ASCII 字符串为 10 bytes，完整 JSON object 更长。
- 影响：当前合法 scope predicate 仍正确，故不升级为行为 major；但根因注释与测试 docstring 在承重位置传播一个未被代码实施的 provenance 不变量和一个错误 byte 数。
- 建议：改写为“gate 只管 Anthropic→Responses crossing；direct Responses inbound 不受该 translation gate 判断”，并把“four identical bytes”改成“the same spelling／the same tool object”。不要据此顺手规定 malformed Anthropic request 的新行为。
- 结论强度：**强，足以修正文档，不支持扩展产品行为。** 精确 provenance 反例已在上一轮执行，第二刀未触及相关字节。

### issue1-gate-scope-review-round2-03

- `finding_id`：`issue1-gate-scope-review-round2-03`
- `severity`：minor
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate/src/app/pipeline/driver.py:196`
- `related_locations`：`tests/int/test_pipeline_app.py:2555-2563`；提交 `5948cb4` 的 message；反证位置 `src/app/pipeline/subscribers/server_tools.py:37`
- 判据出处：本轮要求逐句核对新增注释；`server_tools.py:37` 与 translator 实现明确记录 Responses-shaped `tools` 在 Responses→Anthropic crossing 中是 verbatim carry。
- 发现：第二刀的新注释与 test docstring 声称 direct Responses 的 `{"type":"web_search"}` 被“translated into that protocol's spelling”。实际 `to_anthropic_messages` 对 `request.tools` 逐字赋值，裸 `web_search` 到 Anthropic target 后仍是裸 `web_search`；`server_tools.py:37` 也准确写着“assigns tools across verbatim”。subscriber 能拒绝它，是因为 `_REJECTED_TYPE_PREFIXES` 同时匹配 bare OpenAI spelling 与 dated Anthropic spelling，不是因为 translator 改了拼法。
- 影响：行为与测试断言不受影响，但新根因叙述把“跨格式传递”说成“格式翻译”，会误导以后维护者去 translator 查一个不存在的映射，并与同模块已有精确注释直接冲突。
- 建议：把 driver、test docstring 与 commit message 后续转述统一改成“the declaration is carried verbatim into the Anthropic-target payload”或“the translated request still carries the bare declaration”。归档 commit message 不改写；只修活源码与测试文字。
- 结论强度：**强，足以修正文档。** 依据是 writer 逐字赋值与现有同模块注释，非对输出的猜测。

## 对本轮特别关注项的结论

### 新守卫是否过窄

没有。生产代码中 `WebSearchNotExecutable` 只有两个 producer：hosted gate 与 server-tool subscriber。hosted gate 自 `9d67978` 起先要求 `context.inbound_format is ANTHROPIC_MESSAGES`，因此它能抛出时新 driver guard 必然通过。server-tool subscriber 按 target Anthropic 判断，可由 Anthropic 或 Responses inbound 到达；新 guard 正好把前者保留为 Anthropic synthesis，把后者落回 client error envelope。独立探针覆盖四个 Anthropic web-search control：Anthropic→Anthropic 与 Anthropic→Responses，各自 stream false／true，四条均仍返回 200 + `server_tool_use`／`web_search_tool_result` 且 upstream 零调用。

guard 不该改成 `target_format is ANTHROPIC_MESSAGES`：这正会重新放入 Responses→Anthropic 的错误路径。它判断的是 client 能否读 synthesis，不是 upstream leg 的方言。当前使用 inbound format 与 auto-mode branch 的既有门一致。

### “both writers” 是否属实

属实，限定在 `HandledRequest.synthesized` 这一个 full-reply 标记上。全 `src/app` 扫描只有两个 `synthesized=True` writer：auto-mode 分支 `driver.py:138-155` 与 failed-search 分支 `driver.py:191-204`；两者都由 Anthropic inbound 判据控制，没有后置 `.synthesized = ...` 赋值。`ContinuationSupport.synthesize` 生成的是单个 hand-over block，不设置该标记，且 `hand_back_block` 自身也拒绝非 Anthropic wire。由此，`delivery_policy.delivers_blocks:43-45` 与 `reply.py:25-30` 所依赖的 producer invariant 在当前生产图上成立。

这些 consumer 没有自行 enforce invariant 的事实也写对了。这里不建议再让 `ResponsesFramer` 接收 Anthropic blocks；那只会把协议错误包装起来。producer guard 是正确的所有权边界。

### 400 与 `server_tool_not_executable` 是否合适

合适。`WebSearchNotExecutable` 是 `TranslationRefused` 子类，error-envelope Spec §5.1 明确映射为 `CLIENT`／400，并保留异常自带的 `code` 与 `field_path`；§6.1～§6.3 要求按 inbound Responses 方言写 `invalid_request_error` JSON envelope。独立探针观察到两种 `stream` 值都得到完全相同的四字段 detail：`type="invalid_request_error"`、`param="tools.web_search"`、`code="server_tool_not_executable"` 及原 message，且 upstream 零调用。

`stream=True` 仍返回普通 400 JSON 而不是 `event:error` 也正确：拒绝发生在 response headers 与 SSE stream 建立之前，status 400 本身是 client action carrier。把它改成 200 + SSE error 反而会丢失 §6.2 的 status 语义。

### 新测试质量

新参数化测试有分辨力。它同时钉 HTTP 400、upstream 零调用、specific code 与旧 Anthropic block pair 不出现；参数化两例抵达相同 producer guard，但在移除 guard 的控制变异下分别暴露“缓冲 200 错方言”和“流式 ValueError”两种旧结局。调用方提供的变异结果与结构分析一致；本轮独立运行新参数化测试、Anthropic hosted control、direct Responses control 与 unit control，共 5 passed。

它没有断言 `type` 与 `param`，但这不是缺陷：共享 error writer 已有独立契约测试，本轮独立探针又核了完整四字段 envelope。当前用例把注意力放在此 branch 特有的 status、code、零 upstream 与不合成上，边界合理。

### 是否有新引入问题

第二刀没有引入行为回归；上一轮 major 已关闭。新引入的是 finding 03 的事实性注释错误。finding 01 是此前已存在、在本轮穷举第二个 `WebSearchNotExecutable` producer 时暴露的合并态缺陷，不归因给 `5948cb4`。

## 考虑过但排除掉的可能性

1. **hosted gate 抛出的 refusal 因 driver 新 guard 退化成 400。** 排除。hosted gate 自身先锁 Anthropic inbound；Anthropic→Responses 两种 stream control 均继续 synthesis。
2. **server-tool subscriber 上的 Anthropic web search 因 guard 退化成 400。** 排除。Anthropic→Anthropic 两种 stream control 均继续 synthesis。
3. **还有第三个 `WebSearchNotExecutable` producer。** 排除。对 `src/app` 全量搜索只找到 hosted gate 两条 reason branch 与 server-tools 一处；class 定义不算 producer。
4. **还有第三个 `HandledRequest.synthesized=True` writer。** 排除。全量搜索只找到 auto mode 与 failed search 两处；没有后置赋值。
5. **`ContinuationSupport.synthesize` 违反“both writers”断言。** 排除。它不构造 `HandledRequest.synthesized` full reply，且 `hand_back_block` 对非 Anthropic wire 返回 `None`。
6. **Responses→Anthropic 应继续拿 Anthropic failed-search pair，以避免 HTTP retry。** 排除。该 client 不读 Anthropic pair；错误信封 Spec 把 proxy-side `TranslationRefused` 定为 400，400 对 Responses client 不触发默认 retry，保留 synthesis 没有收益且会破坏协议。
7. **specific code 应退回默认 `invalid_request`。** 排除。Spec §4.4 与 §5.1要求保留 `TranslationRefused.code`／`field_path`；`server_tool_not_executable` 比 category default 更精确且已经是 subscriber 的稳定标识。
8. **stream request 必须返回 SSE error。** 排除。此 refusal 在 headers 前发生；HTTP 400 JSON 是完整、可解析且不重试的 Responses error。SSE carrier适用于 200 stream 已建立后的错误。
9. **应让 `ResponsesFramer` 支持 `server_tool_use` 来形成第二道防线。** 排除。该 block 不属于 Responses protocol；支持它会掩盖 producer invariant 失守。
10. **新测试只钉名字或同源实现细节。** 排除。status、upstream call count、error code 与旧 wire discriminator 都是 client／transport 可观察结构；移除 guard 的控制变异会使两参数各自变红。
11. **web_fetch 反例可因“不是本 issue”静默忽略。** 排除。它与本轮必须枚举的第二个 exception producer、同一 driver catch 和同一 synthetic writer直接相连，并产生当前可达的 200 错语义；报告明确标为 pre-existing，未错误归因给第二刀。
12. **上一轮 Spec blocker应在本轮继续计数。** 排除。调用方明确把 Spec 更新拆为下一轮并要求本轮只评代码与测试；本报告保留其未复评状态，不冒充已关闭，也不重复计数。
13. **必须真实调用 Copilot upstream 才能判断第二刀。** 排除。所有争点发生在 upstream 调用前的 routing、subscriber refusal、driver synthesis 与 error writer；零 upstream 调用本身就是 oracle 的一部分。

## 搜索面与执行证据

读取：`git log 9d67978~1..5948cb4`、`git show 5948cb4`、两提交合并 diff、clean HEAD 最终文件；error-envelope Spec §2、§4～§7；hosted-web-search Spec相关范围与非目标；human-controlled API／pipeline／translation；两个 refusal producer；所有 `synthesized=True` writer；auto mode、ContinuationSupport 与 hand-back guard；OpenAI error writer；新增参数化测试与 server-tools tests。

执行：clean HEAD 上相关 5 tests passed；changed files `ruff check` clean；changed files Pyright 0 errors。独立 round2 probe 验证 Responses→Anthropic 在 stream false／true 下均返回 exact 400 OpenAI error 且 upstream 零调用；Anthropic→Anthropic 与 Anthropic→Responses 四个 web-search control 均保持 200 failed-search pair；同一 probe 复现 web-fetch major。调用方报告的全量 1939 passed／2 skipped、coverage 90.74%、完整 Ruff／Pyright 与移除 guard 的控制变异作为外部已核实背景采信，未重复跑全套。

未覆盖：本轮没有复评并行进行的 Spec 更新；没有真实 upstream；没有评审与 issue #1 调用链无关的模块；没有修改或修复 findings。

## 整体判定

`5948cb4` 对上一轮 major 的修复成立，守卫范围正确，错误 envelope 与 specific code 符合规范，新增测试能区分两个旧失败形态，也没有新行为回归。候选代码仍有一个需要处理的 adjacent major：web-fetch refusal 被 generic catch 错合成为 failed web search。上一轮文字 minor未关闭，第二刀又新增一处“translated spelling”误述。故代码／测试轮 verdict 为 `needs-fix`。

## 我最没把握的三个判断

1. **把 web-fetch 问题纳入本轮并定 major。** 不确定点是它不是 `5948cb4` 引入，且 issue #1 的主诉是 web search；支持纳入的依据是本轮明确要求穷举两个 exception producer，而该路径在同一 catch 上实跑产出 200 错工具语义。若调用方按产品范围决定拆出另一个 issue，应记录为 deferred 并给出权威接收者，不能将事实判为不存在。
2. **stream=True 的前置拒绝使用普通 400 JSON。** error-envelope Spec没有用一句话直接区分“request asked for stream”与“stream headers 已提交”，但 §2、§6.2、§6.3 的 carrier分工与客户端重试机制共同支持当前答案。若项目另有“stream request 的所有错误都必须 SSE”裁决，需要提供其权威锚；当前未找到。
3. **finding 03 定 minor而非 nit。** 它只影响文字，但错误句位于根因解释、test oracle说明与 commit message 三处，并与 `server_tools.py:37` 的精确说明正面冲突；因此按维护误导定 minor。降为 nit不影响行为 verdict。

## 执行本契约时遇到的摩擦

`.dev/` 报告路径位于主工作树，当前 session 受 worktree 写入隔离限制，需先写 `/tmp` 再以不覆盖方式复制到指定路径。除此之外 worktree clean、HEAD 与指定 revision一致，没有并行源码改动污染本轮证据。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-08-30T17:36:51+00:00`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 1`
- `minor_count: 2`
- `nit_count: 0`
