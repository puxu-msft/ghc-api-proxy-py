# 直连 Responses 保真透传产品规格独立评审

- report_id：`direct-responses-passthrough-spec-review`
- attempt_id：`260830-review-spec-1`
- status：`in-review`
- reviewed_at_rev：主仓 `ca777df137db1d12d84baa97a58ab3f5e66c3bdc`；`.dev` 仓 `80b181daae67add1f9d49d5f6834c59d270ab60c`
- target_sha256：`80fe412f1b1f5e23f91e27e811d99b5f8c8df9972a690222e1dfd6e9ace2659f`
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/spec.md`
- 评审性质：尚未实施的新产品规格，只读评审；未修改 `src/` 或 `tests/`

## 评审范围

本次评审覆盖该规格的定义域、事件与 JSON 载荷保真层级、output item 交付边界、`id`／`response.id`／`sequence_number`／`output_index`、root lifecycle events、terminal response object、reasoning 回传、三种 buffering policy、失败／EOF／透明 replay／post-commit ending、memory cap、non-stream 合同、Spec-first 归属和与既有计划／报告的同步。判据先于被评对象读取，独立取自用户亲笔的 `docs/.human-controlled/`，尤其是 `README.md`、`api.md`、`client-side-block-delivery.md`、`config.example.yaml`、`ghc-api.md`、`message-translation.md`、`request-pipeline.md`、`upstream-retry-and-continuation.md`；另取 `.dev/docs/anthropic-responses-bridge/spec.md`、`.dev/docs/error-envelope/spec.md`、`.dev/docs/delivery-keepalive/spec.md`、项目 `CLAUDE.md`、`.claude/rules/00-development-workflow.md`，以及同 topic 的 `plan.md` 与三份指定报告。

实现可行性静态核查覆盖 `sse_source.py`、`sse_frame.py`、`assembling.py`、`blocks.py`、`stream.py`、`formats/openai_responses.py`、`delivery_policy.py`、`reply.py`、`driver.py`、`routes/inference.py`，并读取本仓 `.venv` 内 `openai==3.3.1` 的 Responses stream accumulator 与相关 output item／tool 类型。执行了只读 parser 探针、当前 raw failure replay 探针和三份 cassette 的 id／sequence／output-index 次序测量。

明确不在范围内：修改被评规格、实施生产代码、修改测试、真实 Copilot 上游调用、对 OpenAI Responses 全部事件语义作外部文档审计、决定翻译腿 `function_call_output` 的新映射、重新评审 issue #1 的 Anthropic hosted-web-search 块对、生产 4141 服务的任何操作。

## 总体 verdict

**needs-fix。当前规格不可据此开始实现。** blocker 数：**3**。

核心方向与定义域成立：同格式 Responses→Responses 直连腿不受 Anthropic inbound bridge 的 unknown-item `REJECT` 矩阵约束，且不应再用 Anthropic `CompletedBlock` 往返翻译。但当前文本同时要求 `data` 逐字与改写 `data` 内字段，未定义能够保持全局事件次序的 commit frontier；也没有定义控制事件何时成为客户端可见事实、attempt replay 如何丢弃或保留它们、post-commit failure 如何结束；`until-tool-use` 又把承重判据明确留给实现。三处都要求实现者自行作产品决定，故 Spec-first 前置尚未闭合。

## 发现

### direct-responses-passthrough-spec-review-01

- finding_id：`direct-responses-passthrough-spec-review-01`
- severity：`blocker`
- primary_location：`spec.md:35-58,64-86`
- related_locations：`src/app/pipeline/delivery/sse_source.py:18-52`；`src/app/pipeline/delivery/formats/openai_responses.py:100-189`；`.dev/docs/anthropic-responses-bridge/spec.md:402-411`
- 标题：`data` 逐字与重编其内部字段不可同时成立，且 item batching 缺少保持全局顺序的 commit frontier

**证据。** §3 第 37 行把每个 item event 的 `data` 文本逐字重放定为核心承诺；第 47～48 行同时允许重编 `sequence_number` 与 `output_index`。这两个字段位于同一 JSON `data` 文本内，改任一字段都必须解析并重新序列化或做文本改写，输出已不可能逐字相同。给出的理由“时点改变后原序号不再连续”不成立：只推迟事件而不删除或重排事件时，原 `sequence_number` 仍保持原次序和连续性；三份 cassette 的 sequence 均为 `0..N-1`。只有按 item 重排事件组时它才会倒退，而这正暴露了第二个未定合同：若两个 item lifecycle 交错，§4 要求每个 item 成批交付会改变全局事件次序。现有三份 cassette 的 `output_index` run 都是 `[0,1]`，只说明已观测样本没有交错，证据等级为“趋势样本，不足以充当协议保证”。

**影响。** 实现者无法判断验收 oracle 究竟比较 raw `data` 字符串，还是比较改写后的 JSON value。选择逐字会违反当前允许改写表；选择重编会违反规格标题下最核心的保真承诺。若未来合法流交错，逐 item 一到 `done` 就立刻发还可能把后开的 item 提到先开的 item 前面，造成 sequence 倒退、`output_index` 对 SDK snapshot 的索引失配，或者被迫泄漏尚未完成 item 的事件。

**建议。** 本规格应裁定：上游已有事件的 `event` 与 `SseEvent.data` 一律保持，不重写 `sequence_number`、`output_index`、任何 `id` 或任何未知字段；只有本代理自己生成的 error／keepalive envelope 不属于该逐字承诺。用 attempt-local 全局 event queue 与单调 commit frontier保存原始次序：只有从当前 frontier 到某位置涉及的全部已打开 item 都已 `done` 时才释放连续前缀；item lifecycle 交错时允许完成 item 被更早的未完成 item拖住，而不重排事件。未知 item-specific event 无须被类型表认识，只需停在原全局位置；无法证明其边界时保守持有到 terminal。若产品确实选择重编 JSON 字段，就必须把承诺降为“除明列字段外 JSON value 保真”并放弃“data 逐字”，二者不能并存。

**证据强度。** 自相矛盾由同一规格逐字可证，强到足以阻断；三 cassette 不交错只是一种已观测趋势，报告没有把它外推成协议全称。

**承重前提检查。** 前提是“改变投递时点会自动使原 sequence／output index 失效”；它支撑“可以改写字段而仍称 data 逐字”。若前提为假，改写没有必要且直接破坏核心承诺。只推迟、不重排的反例已推翻前提；若实现打算重排，则规格缺失的正是重排是否合法这一更上游决定。

### direct-responses-passthrough-spec-review-02

- finding_id：`direct-responses-passthrough-spec-review-02`
- severity：`blocker`
- primary_location：`spec.md:54-60,80-109`
- related_locations：`src/app/pipeline/delivery/stream.py:298-577`；`src/app/pipeline/retry.py`；`docs/.human-controlled/upstream-retry-and-continuation.md:2-39`；`.dev/docs/error-envelope/spec.md:51-104,366-368`；`.dev/docs/delivery-keepalive/spec.md:16-57`
- 标题：控制事件的 commit 时点与 attempt replay／post-commit ending 没有合同

**证据。** §5.4 要求原样重放 `response.created`／`response.in_progress`，却没有说何时发；§4 只把它们排除在 item 之外。当前 `stream_delivery` 的透明 replay 判据读取的是客户端是否已经看到 semantic bytes 与 committed block：一旦原生 `response.created` 先发，后续即使尚无 item 完成也不再可能无痕替换 attempt；若把它们留在 attempt-local buffer，首 item 前的 retry仍可丢弃整次 attempt。§7 只列 upstream terminal failure、incomplete item、EOF 和 cap，没有规定 retryable transport tear／clean EOF 在首个 native event 前是否 replay、replacement attempt 是否必须丢弃旧 `response.id` 与全部 control events、已经发送 native item events 后是否严禁 whole-attempt replay，也没有规定 proxy-side delivery／cap／deadline error 与 upstream-native failure event如何分别成帧。人写重试合同已经规定“尚未交付完整块可无痕重试；已交付块则不得从头重放”，error-envelope 又规定直连 upstream event 原生、proxy error 走客户端方言 IR；这些承重事实没有进入本规格。

**影响。** 两种表面合理的实现会产生相反行为：早发 `created` 会关闭所有首 item 前 replay，晚发则允许无痕 replacement；post-commit tear 可以被错误地从头重播，令客户端收到两个 response preamble／重复 item，也可以被现有 Anthropic hand-over policy吞掉。三个 buffering policy 又会因 release 时点不同得到三种 retry window。没有这组合同，EOF 的“具体形态待定”不是一个局部 writer 选择，而是整个状态机未闭合。

**建议。** 在 Spec 中建立 direct-native commit frontier并按位置裁定：HTTP 200 headers 与 SSE comment keepalive 不提交 native attempt；`response.created`／`in_progress` 与其 attempt id 保持 attempt-local，随第一批可交付 item events一起提交；无 item 的 terminal／failure则在最终决定不 replay 后与本 attempt control events一起提交。首个 native event 提交前，retry taxonomy判为可重试的 transport tear／unterminated EOF／可重试 upstream failure可以在统一 budget 内透明 replay，旧 attempt 的 control、item draft、terminal、ids、usage和内存 charge全部丢弃；首个 native event提交后禁止 whole-attempt replay，已交付前缀保留。upstream 自己给出的 `response.failed`／`response.cancelled`／`error` 若最终可见则逐字；proxy cap、client deadline、delivery failure与预算耗尽而没有 upstream terminal时按 `error-envelope/spec.md` 写 Responses `event:error`，不得合成成功 terminal，也不得咨询只适用于 Anthropic client 的 hand-over。cap／client cancel／client deadline等人写文档列为不可继续的原因不得 replay。

**证据强度。** 源码位置判据与现行人写合同均是强到可直接行动的静态证据；具体 upstream failure code中哪些可重试应继续复用现有 retry taxonomy，本报告不另造闭集。

**承重前提检查。** 前提是“原生 event 只换载体、不影响现有 replay 状态机”；它支撑“§7 只列三种特殊 ending就够”。若前提为假，preamble早发本身会改变 replay合法性。当前 replay明确以 downstream-visible state为输入，故前提为假。

### direct-responses-passthrough-spec-review-03

- finding_id：`direct-responses-passthrough-spec-review-03`
- severity：`blocker`
- primary_location：`spec.md:96-102,115-120`
- related_locations：`docs/.human-controlled/config.example.yaml:378-388`；`src/app/pipeline/delivery/blocks.py:87-106`；本仓 `.venv/lib/python3.14/site-packages/openai/types/responses/response_output_item.py:278-310`；本仓 `.venv/lib/python3.14/site-packages/openai/types/responses/tool_search_tool_param.py:10-24`
- 标题：`until-tool-use` 的 release predicate 属于产品语义，不能留给实现

**裁定。** **必须在 Spec 中定，当前未定状态阻断实现。** 正确判据不是 Anthropic `BlockKind.TOOL_USE`，也不是一个看到名字带 `_call` 就命中的封闭列表，而是 `requires_client_action(item, original_request)`：该 output item 是否要求客户端提交与它对应的 tool output／approval，模型回合才能继续。判定需要原始 Responses request 的 tool declaration与 execution mode，不能只看 response item type。

当前协议中明确的正例至少包括 `function_call`、`custom_tool_call`、`computer_call`、`local_shell_call`、`apply_patch_call`、使用 local environment 的 `shell_call`、请求声明 `execution:"client"` 的 `tool_search_call`，以及等待客户端回答的 `mcp_approval_request`。明确反例包括 upstream 已自行执行并在同一 response 内给出结果的 `web_search_call`、`file_search_call`、`code_interpreter_call`、`image_generation_call`、server-executed `tool_search_call`／MCP call；仅仅是 call 名字不意味着客户端需要执行。未来新增类型按同一语义判据进入，不因代理暂时不认识类型而默认 `false`；无法判定时，为避免把客户端所需行动扣到 terminal，保守视为需要释放并记录“predicate unknown”这一 operational fact，而 wire event本身仍逐字。

**影响。** 若只列当前两种 function/custom call，computer、local shell、apply patch或 client tool search 会被 `until-tool-use` 一直扣住，客户端无法执行它们；若所有 `_call` 都触发，hosted web search与 code interpreter会过早释放 buffered prefix，改变用户选择该 policy 的语义。把 unknown 默认 false还会在下次协议扩展时重演“代理认识集合成为客户端能力上界”。

**建议。** 把上述语义 predicate、当前正反例与 unknown fallback写进 §6，并规定触发只发生在该 action item完成且已到达安全 commit frontier时；触发后永久转为 per-item／safe-prefix release，保持今天 `until-tool-use` 的一次性状态变化。实现可以维护由 SDK/version导出的表，但表是 predicate 的当前编码，不是产品判据本身。

**证据强度。** `tool_search` 自带 `execution: server|client` 和 `mcp_approval_request` 的 approval-response合同直接证明“item type叫 call”与“客户端必须行动”不是同一事实；判据强到可直接写入 Spec。具体未来类型的归类必须随协议新增更新，不能由本报告预言。

**承重前提检查。** 前提是“实现者只需看 SDK union就能自行决定哪些 call触发 policy”；它支撑把清单留成未定。若前提为假，同一 `tool_search_call` 已因 `execution` 不同产生相反答案，说明这是 request＋response 的产品语义判断而非局部实现细节。

### direct-responses-passthrough-spec-review-04

- finding_id：`direct-responses-passthrough-spec-review-04`
- severity：`major`
- primary_location：`spec.md:35-52`
- related_locations：`src/app/pipeline/delivery/sse_source.py:15-52,64-86`；`src/app/pipeline/delivery/stream.py:282-295`；`.dev/docs/anthropic-responses-bridge/spec.md:345-350`
- 标题：`SseEvent` 足以承载规范化后的 logical data，但现有 parser／replay并未兑现规格写下的完整范围

**专项核验结果。** `parse_frame` 对多行 `data:` 返回 `data='first\nsecond'`，所以 logical data没有丢，丢的是原分行拼法；对空 `data:` 返回 `SseEvent(event='x', data='')`，所以空 data也没有丢；注释行、`id:`、`retry:` 与任何其他 SSE field 均被删除；只有 `event:` 而没有任何 `data:` 的帧返回 `None`；invalid UTF-8 经 `errors='replace'` 变成 `�`。这说明“未经 JSON re-serialise 的 `SseEvent.data` 文本”成立，但“原始 payload bytes”不成立，且 promise 的精确定义必须是“合法 UTF-8 SSE 经过 SSE field parsing得到的 logical event/data”。

**两个运行反例。** 当前 `_report_failure` 把含换行的 `raw_data='first\nsecond'` 写成一行 `data:` 加一行裸文本，客户端再解析只剩 `data='first'`；所以“项目已经在用同一机制”只能证明单行 payload，不能证明多行。`read_events` 的 frame separator固定为 `b'\n\n'`；给它两个合法 CRLF frames，实测只产出一个 `SseEvent(event='b', data='1\n2')`，把两个事件合并。bridge Spec 已要求 parser正确处理 CRLF，这也是 direct implementation必须复用或修复的共同前置。

**影响。** 若实现者照抄现有 raw failure writer，多行 logical data会静默丢后续行；若认为 `SseEvent` 已经保住全部 SSE field，则未来 valid extension field、`id`／`retry` 与 event-only frame会被错误承诺为可重放。空 data反而可保留，不应被误列为做不到。

**建议。** §3 的“不承诺”清单目前不够精确：保留“不是 byte-level”总限定，并补明 unknown SSE fields、event-only/no-data frames、invalid UTF-8／解码替换与 field whitespace／line-ending normalisation；明确空 `data:` 和 multi-line的 logical newline属于可承诺范围。实现一个接受 `event: str, data: str` 的 raw-text SSE encoder，对 `data.split('\n')` 的每一段各写一条 `data:`，而不是复用只接受 dict并 `orjson.dumps` 的 `SseFrame`，并修复 CRLF frame boundary。加入 multi-line、空 data、comments、id/retry、unknown field与 CRLF 正反例。

**证据强度。** parser和writer输出均为目标 HEAD上的实跑结果，强到可直接行动；invalid UTF-8是否要纳入产品支持范围是规格选择，但未限定时不能称“逐字”。

**承重前提检查。** 前提是“保存 `SseEvent.data` 就自动保证重新成帧后客户端读到同一 data”；它支撑现有可行性说明。若前提为假，multi-line反例会丢字；实跑已证明前提为假，必须补 encoder合同。

### direct-responses-passthrough-spec-review-05

- finding_id：`direct-responses-passthrough-spec-review-05`
- severity：`major`
- primary_location：`spec.md:111-113`
- related_locations：`src/app/server/routes/inference.py:524-573`；`src/app/pipeline/reply.py:18-41`；`.dev/docs/error-envelope/spec.md:64-83`
- 标题：non-stream“body原样返回”的现状陈述不实，成功响应的 fidelity level、status与headers没有合同

**证据。** `response_payload(..., translation_required=False)` 确实返回同一个 Python dict，但到它之前 `inference.py` 已执行 `response.json()`，并拒绝非 object JSON；之后用 `JSONResponse(payload)` 再序列化。因而未知 object fields可以 value-level 保留，raw bytes、空白、key顺序、number lexical form、duplicate keys和原 `Content-Type`都不保留。“今天已是 body原样返回”若按 §3 的“逐字”读是错误事实，若只指 JSON value则没有写出限定。该节还没有规定成功响应的 upstream status与语义 headers；同格式直连是否保留 `request-id`、rate-limit、`retry-after`等是客户端可观察合同，不应由实现偶然决定。

**影响。** 实现可以在不违反当前文字的自我解释下选择 byte-exact raw response或重新序列化 dict，两者面对 duplicate keys、非标准 content type与未来字段有不同结果。标题“保真透传”与 streaming 的逐字层级会让读者自然把 non-stream也读成 byte fidelity，而现有代码做不到。

**建议。** 明确二选一。我的偏好是与“协议允许就不由代理拒绝”一致地规定：合法 Responses JSON object按 JSON value保真，所有未知字段保留，允许 serialization spelling变化；status原样；response headers按一张明确的 direct-leg过滤表保留语义头。若产品要 byte-exact，则必须在 JSON parse之前直接交付 `response.content`与原 content type，并另定 malformed／non-object成功 body行为。无论选哪种，都把“当前 response_payload直接返回”改成准确的 value-level观察，不能称 raw body。

**证据强度。** 当前代码路径是强到可直接行动的静态事实；byte-level还是value-level是产品选择，本报告不把偏好冒充用户裁决。

**承重前提检查。** 前提是“返回同一个 dict就等于 body原样”；它支撑“不改变 non-stream便已满足§2”。若前提为假，重新序列化会改变字节。源码明确存在 parse＋serialize，因此前提为假。

### direct-responses-passthrough-spec-review-06

- finding_id：`direct-responses-passthrough-spec-review-06`
- severity：`major`
- primary_location：`spec.md:104-121`
- related_locations：`docs/.human-controlled/config.example.yaml:390-392`；`src/app/pipeline/delivery/blocks.py:27-37,57-123`；`src/app/pipeline/driver.py:157-172`；`.dev/docs/direct-responses-passthrough/reports/260830-known-set-divergence.md:33-42`
- 标题：§9把已有答案与定义域外问题列为待定，反而漏列真正阻断的 replay／ordering 决策

**裁定。** 当前文件的 §9 实际只有 **5** 项，不是调用任务所说的 9 项；我以读到的 hash为准评审。五项中：第 1 项阻断且见 finding 03；第 2 项阻断且必须与 replay一起按 finding 02闭合；第 3、4项已有足够依据，不应继续待实现确认；第 5项明确不在本规格定义域，不阻断 direct implementation，也不应挂在本规格“实现前必须闭合”标题下。

**第 3 项。** 人写配置已经把 `buffer_cap_bytes` 定义为“max bytes to buffer before abandoning this response”，`BufferCapExceeded`也写明 guard bounds memory；所以 cap限制的是代理当前持有的 buffered bytes，不是累计交付量。对本腿应计入尚未 done的 raw event queue、已完成但 policy扣住的 event groups、root/control events及同时保留的预渲染副本；释放、retry reset、failure、cancel后按实际 ownership退 charge。精确容器 overhead的估算法可以是实现细节，“held而非delivered”不是。

**第 4 项。** `driver.py` 只有 `route.translation_required` 为真才调用 request translator，而 reasoning carrier decoder只在该 translator内；本规格定义域恰为 false。因此 direct下一轮回传的 `encrypted_content`不进入 carrier decoder，只有既有 route shaping会把 model改成 resolved model。这个结论证据强到可以写成 normative条款并要求回归测试，不必继续悬为产品未知。

**第 5 项。** `function_call_output` 是否在 Responses response output里出现、翻译成 Anthropic什么，是 translation leg的能力问题；direct leg按本规格无条件携带。若该发现改变 bridge产品合同，必须修订 `.dev/docs/anthropic-responses-bridge/spec.md`；留在本规格 §9既不能授权那个修改，也不控制本腿。

**影响。** 实现者会在已有权威的问题上重复作决定，却看不到真正缺失的 attempt commit/replay和全局 ordering；定义域外条目又可能让 direct work无故等待 upstream样本。更严重的是，若第 3项被选成“累计交付量”，会把一个 memory guard改成 response-size limit，拒绝可以逐单元释放、resident始终受控的长回答。

**建议。** 关闭第 3、4项，把第 5项从本规格移出并回链其真正 authority；把 findings 01～03要求的 global commit frontier、control-event commit、retry/replay与 `requires_client_action`列入并在正文定案。§9只保留真正未闭合且归本规格所有的事项，待正文修订后清空“实现前必须闭合”而不是把答案留给实现。

**证据强度。** cap与carrier结论分别有用户亲笔配置和生产调用门，强到可直接行动；`function_call_output`真实发生率仍未验证，但它不影响“与 direct定义域无关”这一结论。

**承重前提检查。** 前提是“这些项目尚无答案，所以留在 Spec待实现确认最谨慎”；它支撑继续挂起。若前提为假，挂起会绕开既有 authority或扩大定义域。第 3、4、5项分别由现行合同、调用门和本规格定义域证伪。

### direct-responses-passthrough-spec-review-07

- finding_id：`direct-responses-passthrough-spec-review-07`
- severity：`major`
- primary_location：`spec.md:25-39`
- related_locations：`.dev/docs/error-envelope/spec.md:34-49,64-97`；`docs/.human-controlled/message-translation.md:6-8`
- 标题：§2把“不可因不认识而拒绝”扩写成用户裁决的“不拒绝／不丢弃／不改写”，归属范围超过逐字原话

**权威归属核对。** 本轮给到的一手原话是「协议允许，凭什么拒绝？」；调用任务也把它解释为“代理不认识一个 item不构成在直连腿上拒绝它的理由”。这能直接支持“未知且合法不是 rejection reason”，但不能单独覆盖第 27 行新增的“丢弃或改写”以及 §3的event/data逐字、§5的全部 id不改写。后者方向上有独立依据：用户亲笔 `message-translation.md` 规定直连“尽可能原样转发”，`error-envelope/spec.md` 又保存了 2026-08-23 用户原话“直连路径一定用原生的，即使我们未知，也能传递”。这些来源合起来可以支持 native/direct设计，但不能把所有精确 fidelity policy倒签为 8月30日这一句用户原话的逐字 scope。

**影响。** `sequence_number`／`output_index`能否重编、SSE logical text还是bytes、id instability是否透明暴露都是 agent仍需推导的设计选择。整段标成“用户裁决”会让后续会话把这些选择当作用户不可重开的决定，恰好掩盖 finding 01里现在需要修正的自相矛盾。

**建议。** 把 decision origin拆开：用户 8月30日裁决只写“不得以代理不认识为由拒绝协议允许的 direct item”；用户亲笔的直连尽量原样与 8月23日 native ruling另行引用；事件级 logical data、per-event ids、commit frontier等标为本规格在授权范围内推导的产品合同。若调用方认为用户原话另有更宽上下文，应补逐字锚，不用 rationale代替。

**证据强度。** 归属超宽由原话和目标句直接比较即可，强到可直接修文档；“更宽上下文是否存在”不可由本会话否定，因此报告只要求停止传播超出已举证范围的 attribution，不断言用户从未说过。

**承重前提检查。** 前提是“质问为什么拒绝等于裁定所有字段不得改写”；它支撑把完整 fidelity policy归给用户。若前提为假，后续设计分歧会被错误关闭。两句话的语义范围不相等，故必须拆分 provenance。

### direct-responses-passthrough-spec-review-08

- finding_id：`direct-responses-passthrough-spec-review-08`
- severity：`major`
- primary_location：`spec.md:8-23,84-109`
- related_locations：`src/app/pipeline/delivery/blocks.py:44-123`；`src/app/pipeline/delivery/assembling.py:28-60`；`src/app/pipeline/reply.py:58-69`；`.dev/docs/direct-responses-passthrough/plan.md:70-105`；`.dev/docs/direct-responses-passthrough/reports/260830-review-plan.md:57-99,148-185`
- 标题：既有评审证明的 buffer／observability消费者仍未形成 Spec合同，当前 plan又与新 Spec相反

**证据。** §1 第 16行仍写“唯一的消费者就是 framer”，但计划评审已经用源码反例推翻：`BlockBuffer`读取整个 payload的 size和 `kind`决定 `until-tool-use` release，`Terminal.record`读取 kind／tool name／thinking并流入完成日志与 TUI。目标规格后来提到 policy、cap和 `Terminal.stop_reason`不得反推 wire，却没有定义 direct native items应产生怎样的 truthful operational facts：tool names、reasoning presence、item count、upstream terminal status／usage、failure origin；因此实现可以做到 wire保真而让完成行把有工具的 turn报告成没有工具，或继续用 Anthropic stop_reason词汇。

与此同时，当前 `plan.md` 仍规定只保存 final `done.item`并重新生成 `output_item.added`＋`.done`，继续 mint id、沿用 framer自己的 output index，且把 translation unknown item的成功 stop reason列为待裁；新 Spec已经要求保存全部 item-specific events、不得 mint id、terminal whole object raw，并确认 translation leg维持 `REJECT`。这不是措辞滞后，而是照 plan实施会违反 Spec的直接冲突。

**影响。** 已知的非-wire消费面会在重构时静默退化；维护者也没有一份可执行的单一计划，可能按旧方案再次丢掉专有事件或改写 id。项目不可协商的规则要求 Spec-level事实只能落在 Spec，并要求 living plan与当前 Spec同步；现在两半都未闭合。

**建议。** 在 Spec补最小 operational contract：wire source of truth永远是 raw upstream event／terminal；observability从旁路 typed facts派生，不反向改写 wire；至少记录 native output item count、client-action tool names／types、reasoning presence、authoritative terminal status与usage、failure／truncation／retry origin，无法分类时明确 unknown而不是伪装 absent。`BlockBuffer`不再靠 Anthropic kind同时承担 payload carrier、release predicate和日志分类。待 Spec按本报告修订后，同步重写 `plan.md`的 delivery unit、ids、sequence／output index、unknown translation与状态机，旧报告保持点时原件不改。

**证据强度。** payload消费者和 plan冲突均是强到可直接行动的静态证据；具体 observability record类型与专用 assembler还是显式 mode属于实现选择，不应写死在产品 Spec。

**承重前提检查。** 前提是“只要 raw events能到客户端，现有 buffer和观测层不读其语义，所以 plan无需同步”；它支撑把这些留在实现。源码和既有评审已经给出 size、release、completion-summary三个反例，前提为假。

## 对七项专项问题的集中回答

### 1. §3 的保真承诺能否兑现

**结论：限定为合法 UTF-8 SSE的 logical `event`／`data` 后技术上可兑现，但当前论证和现有 writer不足以兑现；按当前文字与 field rewrite表则不可兑现。** `SseEvent.data`没有经过 JSON re-serialise；multi-line按 SSE规则 join为一个含 LF的 logical string，空 `data:`也保留为空 string。注释、`id:`、`retry:`、unknown SSE fields、event-only frames与invalid UTF-8 bytes不会保留。现有 `_report_failure` 对 multi-line重新成帧会丢第二行，CRLF frame separator也有实测缺陷。四项“不承诺”不够精确，修法见 finding 04；最上游的“逐字却改 sequence/output index”矛盾见 finding 01。

### 2. §2 的定义域边界是否成立

**成立，证据强到可直接采用。** `anthropic-responses-bridge/spec.md` 的标题、问题与意图、目标和范围边界逐字把定义域钉在 Anthropic `/v1/messages` inbound选择 Responses upstream；其 downstream始终是 Anthropic JSON／SSE，semantic block也明定为 Anthropic content block。该文件排除 raw Responses passthrough的理由正是“下游不是 Responses客户端”，不适用于本规格中下游就是 Responses客户端的路径。矩阵“unknown output item→REJECT”、stream/non-stream归一化等均受该文件定义域限制，与本规格 direct Responses腿不冲突。错误与 keepalive等跨腿合同仍适用，但它们不把 Anthropic response matrix扩张到 direct腿。

### 3. 上游 id不稳定时，原样使用是保真还是缺陷

**明确裁定：在本规格选择的 direct native合同下，这是保真；不一致是 upstream wire的事实，不是代理应默默修复的缺陷。§5.2／§5.3不应回退为 mint。** 12／16／125不是“同一 id重复”的证据，而是三个 cassette中每个事件携带的 relevant id都不同；本轮独立复算也得到每个 output index下每个 item/item_id均互异，三个 response lifecycle event的 `response.id`也各异。这个观测只证明 id不能作为内部 draft correlation key；内部可用 `output_index`与 attempt-local ordinal／lifecycle frontier，wire则保留每个事件自己的 id。`openai==3.3.1` accumulator按 `output_index`累积并未校验 id相等，所以“Python SDK snapshot必需稳定 id”在该版本上被排除；其他客户端是否会拒绝仍未穷尽，不能外推为全生态安全。若产品以后要提供 `fix_stream_ids` compatibility transform，应另立显式、可选择的 reshape合同，不能把它叫 native/逐字。

### 4. §7 是否覆盖实际状态机

**不覆盖。** 三条方向分别正确：direct incomplete item必须交付、不套 Anthropic `cut_short`；无 terminal的 EOF不能伪造成功；cap必须按 held bytes。但至少还缺五组承重状态：root/control events何时 commit；首个 native event前 transparent replay与 replacement state reset；首个 native event后禁止 whole-attempt replay并保留已交付前缀；upstream-native failure与proxy-generated error的不同 carrier／retryability；三种 policy下 safe-prefix release、memory charge与keepalive不关闭 replay window。item interleaving下的 global ordering又是第六组。完整裁定见 findings 01、02、06。

### 5. §6 的 `until-tool-use` 是否该在 Spec定

**必须定，且当前未定是 blocker。** 正确判据是“该 item是否要求客户端提交对应 output／approval才能继续”，由 response item与 original request tool execution contract共同决定；不是 Anthropic block kind，也不是名字含 `_call`。当前正反例、future unknown fallback与触发时点见 finding 03。

### 6. Spec-level事实是否留在 plan／report，或实现细节混入 Spec

**仍有。** 既有方案评审已证明的 control-event/replay、observability、typed release predicate、raw resident-byte charge与 translated unknown `REJECT`没有全部形成正文合同；其中前三项甚至决定实现分支。反向地，`CompletedBlock.size_bytes == len(repr(payload))`、`hand_back_block()`当前返回形态、`ResponsesFramer`当前 mint方式、28／6计数与具体源码调用门是 implementation observation，不应代替 normative条款；可以留作有 revision的“当前差距”，但产品合同应只写 held-byte语义、direct不 hand-over、ids保留和route gate行为。`plan.md`目前仍与 Spec的全事件／id／terminal合同冲突，须在 Spec收口后同步更新；历史 reports保持原文，不回填。

### 7. §9 哪些未闭合项阻断实现

目标 hash下 §9实际是五项。第 1项 `until-tool-use` 与第 2项 EOF/replay阻断；第 3项 cap和第 4项 carrier已有答案，应直接闭合而非继续等待；第 5项 `function_call_output`不属于 direct定义域，不阻断且应移出。更关键的是，§9没列出的 fidelity自相矛盾／global ordering与 control-event commit／replay同样阻断。**因此可否据此开始实现：no。**

## 已排除掉的可能性

1. **“bridge response矩阵的 generic措辞覆盖所有 Responses输出，所以 direct也必须 `REJECT`”——排除。** 该文件的 scope明确是 Anthropic inbound与Anthropic downstream；本规格边界成立。
2. **“bridge排除 raw Responses SSE说明本项目普遍禁止 direct passthrough”——排除。** 原条款理由是 downstream不是 Responses客户端，本腿前提相反。
3. **“上游 id每事件变化本身授权代理 mint”——排除。** 它只否定 id作为内部 correlation key；native wire是否 reshape是另一个产品决定。当前 native合同选择不改。
4. **“所有客户端都能接受不一致 id”——未作此全称。** 只核了 Python OpenAI SDK 3.3.1的 accumulator；其他客户端影响未验证，不拿缺证据冒充安全保证。
5. **“空 `data:` 在 `parse_frame` 后消失”——排除。** 实跑返回 `SseEvent(event='x', data='')`。消失的是没有任何 data field的 event-only frame。
6. **“multi-line logical data在 parser处已经丢失”——排除。** parser按规范用 LF join；真正已证实的丢失发生在当前 raw replay重新成帧时。
7. **“SSE `id:`／`retry:`与comments仍藏在 `SseEvent`某处”——排除。** dataclass只有 `event`和`data`，探针也证明其他 fields被删除。
8. **“只改变投递时间就必须重编 sequence”——排除。** 保持全局事件顺序时原 sequence仍单调；需要重编只会来自删除／重排，而那与逐字承诺冲突。
9. **“要保全全局次序只能整轮 full-buffer”——排除。** 单调 safe-prefix frontier可在没有交错未完成 item挡路时按 item释放；交错时才暂时扩大持有范围。
10. **“direct reasoning回传会进入 carrier decoder”——排除。** request translator受 `translation_required=True`门控，本定义域为 false。
11. **“memory cap可以解释成累计交付量”——排除。** 用户亲笔配置明确写“bytes to buffer”，是 resident/held guard。
12. **“翻译腿 `function_call_output`的真实发生率不明会阻塞 direct腿”——排除。** direct不翻译；真实发生率只影响另一 authority的能力矩阵。
13. **“`response.created`不是 item，所以什么时候发只是实现细节”——排除。** 它一旦客户端可见就关闭 transparent replay window，直接改变外部失败行为。
14. **“现有 full suite绿可证明本规格可实现”——排除。** 本次是未实施规格评审，没有用既有回归替代新合同；只运行了有判别力的 parser／cassette探针。

空清单声明：以上 14项是本轮实际考虑并排除或限定的可能性；没有把未取得依据的猜测写成 severity finding。

## 搜索面、探针与证据限制

### 判据来源

- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/README.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/api.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/client-side-block-delivery.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/config.example.yaml`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/ghc-api.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-format-reshape.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-translation.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/request-pipeline.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/spec.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/delivery-keepalive/spec.md`
- `/home/xp/src/ghc-api-proxy-py/CLAUDE.md`
- `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/plan.md`
- 同 topic三份指定报告：`260830-review-plan.md`、`260830-review-issue2-fix.md`、`260830-known-set-divergence.md`

### 代码与协议面

读过 `src/app/pipeline/delivery/{sse_source.py,sse_frame.py,framing.py,assembling.py,blocks.py,stream.py}`、`delivery/formats/openai_responses.py`、`delivery_policy.py`、`reply.py`、`driver.py`、`server/routes/inference.py`，以及本地 OpenAI SDK 3.3.1的 `_responses.py` stream state、`ResponseOutputItem` union、function/custom/computer/shell/apply-patch/tool-search/MCP approval相关类型。`.codegraph/`不存在，按项目规则没有自行建立索引，使用绝对路径 `Read`与 `rg -u`读取 gitignored `.venv`。

### 执行证据

- 独立核验主仓为 `main`、HEAD=`ca777df137db1d12d84baa97a58ab3f5e66c3bdc`；`.dev`仓 HEAD=`80b181daae67add1f9d49d5f6834c59d270ab60c`；目标 SHA-256见文首。
- parser探针得到：multi-line→`'first\nsecond'`；empty data→`''`；comment/id/retry/unknown field被删除；invalid UTF-8→`'�'`；event-only→`None`。
- CRLF探针把两个 frames错误合成一个 `event='b', data='1\n2'`；这是当前 parser缺陷，不是对未来实现的猜测。
- 当前 raw failure replay探针把 `raw_data='first\nsecond'`重新解析成 `'first'`，证明现有 writer不支持 multi-line logical data。
- 三 cassette测量：事件数分别为 12／125／16；sequence均连续；response id在各自三个 root lifecycle events中均为 3个不同值；各 output index内每个 observed item id也都不同；index runs均为 `[0,1]`，未观测交错。
- OpenAI SDK 3.3.1 accumulator以 `output_index`读 snapshot，未找到 item id equality validation；结论只限定该版本与该 parser。

没有运行完整测试套件：被评对象尚未实施，完整旧回归不能回答新合同；本轮只运行直接区分相关命题的只读探针。没有真实 upstream call，故未知 future event scope与真实 item interleaving发生率保持未验证。Bash未被守卫拒绝，代码结论除外部协议语义外均有实跑或目标 HEAD静态依据。

## 尾部整体判定

**needs-fix；blocker 3。** 方向正确、定义域正确、id不 mint的 direct-native选择正确，但规格的 fidelity oracle自相矛盾，delivery/replay状态机与 `until-tool-use`产品判据未闭合。修订 findings 01～08并同步 plan之前，不可开始实现。

## 我最没把握的三个判断

1. **`until-tool-use`对无法分类的 future item默认 release。** 我的偏好是 `true`，因为误作 false可能把客户端必须执行的动作扣死，误作 true只会提前释放完整、安全前缀；这是“强偏好，可据此提出 Spec条款”，不是用户既有裁决。若产品把保密式延迟高于 liveness，应由用户重裁 fallback，但 semantic predicate本身不变。
2. **协议是否允许不同 output item lifecycle实际交错。** 本地 SDK结构不禁止，bridge规格也专门要求处理 interleaved ordering，但三份真实/历史 cassette都未出现；证据等级是“可能性必须有合同，发生率未验证”。finding 01的 blocker不依赖它，因为 data逐字与 field rewrite已独立矛盾。
3. **non-stream应选 byte fidelity还是 JSON value fidelity。** 用户的 native/direct原则支持两者中的更强者，但当前人写文档没有对成功 Responses body逐字定案。我的偏好是 value-exact JSON＋unknown fields preserve＋status/header明确，因为这满足本次 unknown-item目标且不把 malformed JSON bytes扩成新产品；这是产品取舍，不冒充事实。

真实不足三个以外没有编造第四项。上述三项都写明了可支持的决策强度与不能外推的范围。

## 执行本契约时遇到的摩擦

- 目标报告路径的 `Write` 被 shared-checkout isolation guard拒绝；按调用任务预案改写到 `/tmp/260830-review-spec.md`，需要调用方搬到 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260830-review-spec.md`。没有绕过守卫。
- 调用任务称“§9列的九个未闭合项”，目标 hash实际只有五项；本报告明确记录差异并按实际文件评审，没有臆造四项。
- 没有派 agent，遵守调用任务的明确禁令；本报告本身因此没有第二位 reviewer复审，调用方应按既有处置流程核验，不把本次自查冒充共识。
- 没有修改 `src/`、`tests/`或被评规格；所有 probes通过 heredoc在现有解释器中运行，没有新增 test asset。

## 严重度汇总

- blocker：3
- major：5
- minor：0
- nit：0
- finding_total：8

## 交付声明

- delivery_complete：true
- completed_at：2026-08-30
- finding_total：8
- blocker：3
- major：5
- minor：0
- nit：0

