# next-root-fix-analysis 独立评审

- report_id：`next-root-fix-analysis-review-general-opus-260903`
- attempt_id：`260903-next-root-fix-review-general-opus-1`
- reviewed_at_rev：`e1b2baa99637349d2f552343c57769a311bfb179`
- 评审对象：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md`
- 评审范围：技术正确性、权威边界、真实生产入口、Spec 先行、类型与顺序、完整语义切片、根因闭合度；不评措辞美感。
- skill 状态：按契约首先尝试加载 `my-agents:as-reviewer`，harness 返回 `Unknown skill: my-agents:as-reviewer`。因此按用户给定核查清单继续独立评审。
- 落点说明：隔离机制拒绝写入主工作树指定路径 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-next-root-fix-analysis-review-general-opus.md`，错误要求只能编辑隔离 worktree 内文件；按契约改写到当前 fallback 路径。
- 状态：评审进行中；尾部出现 `## 交付声明` 才表示完成。

## 整体判定

**needs-fix。** `D-5` 仍是合理的首选，但草稿给出的首选依据与闭合边界需要修正后才能据以排期。当前组合的顺序与类型故障属实，后续用户裁决也足以启动工作；然而建议切片漏掉用户明确要求的非流式 continuation，把 native failure taxonomy 的 `D-6` 放到了可以宣称 `D-5` 完成之后，并把 Anthropic selector 的其余硬前置——现有 `signature_delta` reshape 默认值——漏出实施闭包。草稿还把 Anthropic direct 称为项目“主路径”，与仓库当前产品边界冲突；这会系统性压低 hosted web search 等真正位于 Anthropic inbound → Responses upstream 主路径上的候选。

证据强度：四条 major 足以要求修订分析与实施边界，但不足以推翻 `D-5` 作为首选本身。首选仍由“后续用户已裁范围 + 当前 direct-passthrough 主线的未闭合接线 + 可复现的确定性故障”支撑，而不是由“它是项目主路径”支撑。

## 版本与证据面

主仓 `.git/refs/heads/main` 与本评审隔离 worktree 的 `HEAD` 均为 `e1b2baa99637349d2f552343c57769a311bfb179`。逐文件 `cmp` 证明本次必读的八个生产文件与该 worktree 版本一致：`hand_over.py`、`delivery_policy.py`、`delivery/stream.py`、`delivery/passthrough.py`、`delivery/formats/anthropic_messages.py`、`delivery/formats/openai_responses.py`、补查的 `delivery/formats/anthropic_messages_passthrough.py`、真实入口 `server/routes/inference.py`。因此下述源码结论限定在该 revision；`.dev` 文档按 2026-09-03 读取到的当前文件内容评判，不假称其由主仓 revision 固定。

## Blocker／Major findings

### F-01

- finding_id：`NRF-01`
- severity：`major`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:18-34`
- related_locations：`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md:30,60,64`；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:322,524-573`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/reply.py:18-32`
- 证据：用户亲笔文档明确规定“非流式请求也支持无痕重试、合成续写机制”，并已同时给出 Responses 的 `function_call`、`input` 与 `max_output_tokens` 词汇。草稿的 Spec 待补项、生产合同、实施切片和最小判据全部围绕 SSE event、terminal frame、delivery driver 与三种 streaming buffering policy 展开，没有任何 non-stream body 合同。真实入口在 `if context.stream` 之后另走独立路径；direct response 由 `response_payload()` 原样返回，而现有 continuation 只检查 Anthropic body 的顶层 `stop_reason` 与 `content`，然后向 `content` 追加 `tool_use`。Responses body 的判据是 `status == "incomplete"` 与 `incomplete_details.reason == "max_output_tokens"`，载体是 `output`，现代码根本不会命中。
- 影响：按草稿第二刀完成后，Responses streaming 可能可续写，Responses non-stream 仍不可续写，却会被“所有直连腿可用”与最小判据掩盖。这直接缩小了用户已裁范围，并改变完整语义切片的边界。
- 建议：Spec 先行补一份与 streaming 共用 `ContinuationIntent` 的 non-stream finalization 投影，至少定案 Responses body 的触发判据、保留哪些完整 `output` item、如何追加 synthetic `function_call`、最终 `status`／`incomplete_details`／`output`／`usage`／id 的来源以及只出现一个终局对象。实施计划与验收必须从真实 non-stream route 入口各覆盖 Anthropic direct 与 Responses direct，而不是只加 event writer。

### F-02

- finding_id：`NRF-02`
- severity：`major`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:22-34,48`
- related_locations：`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md:4-30`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:231-269,551-598`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/deferred.md:92-106`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py:388-404,458-485`
- 证据：用户合同不是“只有 max-token terminal 才 continuation”，而是先按可继续／不可继续 taxonomy 分类；已交付至少一个完整块且业务可继续时，把报错合成为 continuation call。native failure event 正需要 `D-6` 把 `error.type`／`ResponseError.code` 归一到该 taxonomy。当前 `_deliver()` 在 `assembler.failure` 出现时先交付本事件刚完成的单位，随即 `_report_failure()` 并 `return`，完全绕过 replay 与 `_hand_over()`。草稿的共同不变量只点名“成功／incomplete terminal”，最小判据没有 native failure 正例；随后又把 `D-6` 定义为 `D-5` 之后的独立切片。当前 living Spec 自身也暴露出待修冲突：§5.2 要分类 native failure，§7.2／§8 却把最终可见 failure 一律逐字提交，而没有说明哪些可继续 failure 应被 continuation 替换。
- 影响：这不是单纯把一张表晚做。若 `D-5` 在 `D-6` 之前被宣称闭合，或 selector 在没有该分类与动作次序时打开，已提交完整块后的可继续 native failure 仍不会续写，用户已裁合同没有闭合。反过来，不可继续 failure 又不能被一律合成，故不能靠一个无 taxonomy 的兜底 writer 修补。
- 建议：把“native failure → retry/continuation/final failure”的动作矩阵纳入第一刀 Spec 修订。`D-6` 可以保持独立语义提交，也可以在 `D-5` 基础设施之后落地，但它必须是 `D-5` 对外完成与 Anthropic selector 启用的前置，不是完成后的清理。验收加入至少一个可继续 failure 在已提交完整单位后生成 continuation、一个不可继续 failure 保持原失败、一个未提交时 funded replay 的三向对照。

### F-03

- finding_id：`NRF-03`
- severity：`major`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:20,34`
- related_locations：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:101-116`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/deferred.md:48-64`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery_policy.py:96-112`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/anthropic_messages.py:69-141,222-281`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py:1-7`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:326-356`
- 证据：Spec §2.7 已经定案“接线不得改变任何一条腿今天已生效的整形默认值”，并具体要求 Anthropic `signature_delta` 默认开着。当前这一行为只存在于 parsed `CompletedBlock` 路径：`AnthropicFramer.block()` 经 `block_frames()` 调用 `signature_frame()`。`PassthroughFramer` 虽有通用 `reshape` 槽，但 production `delivery_policy` 只给 Responses direct 构造 reshape；Anthropic 分支直接返回 `AnthropicFramer`，且 production selector 尚不引用 `anthropic_passthrough_assembler()`。草稿在 Spec 待补清单里只说要规定“compatibility reshape 的交互”，实施切片却只列 continuation intent／terminal point／dialect writer／D-7，并说 Anthropic selector 是否能开只取决于 `D-6`。
- 影响：即使 F-01、F-02 与现有类型／顺序问题全部修好，仅按草稿列出的第二、三刀打开 selector，默认的 thinking signature 兼容行为仍会消失，直接违反当前 Spec 与接线前置。`D-4` 的长期“常驻还是可关”仍可待用户裁，但“保持今天默认值”不是待决项。
- 建议：把 Anthropic passthrough reshape 的实现与验收列为 selector 启用前置，并区分两件事：本片只兑现已定案的当前默认值；`D-4` 继续保留长期产品分叉。判据要用带 embedded signature 的真实 route 流，证明默认配置仍产生 `signature_delta`，显式关闭时原样保留 embedded 形态，并证明 continuation synthetic block 不被该 reshape 误处理。

### F-04

- finding_id：`NRF-04`
- severity：`major`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:12,49-52,60`
- related_locations：`/home/xp/src/ghc-api-proxy-py/CLAUDE.md` 的“当前项目优先级与产品边界”；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:90-99`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:8-17,31-41,55-62`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/deferred.md:6-20`
- 证据：仓库当前指令明确把主产品路径定义为“Anthropic Messages input served through an OpenAI Responses upstream”。Anthropic direct 是 Anthropic inbound → Anthropic upstream；`claude-sonnet-5` 不支持 Responses API 只证明这条 served route 对 Claude 模型重要，不把它改写成项目主产品路径。草稿却用“它是主路径”支撑 `D-5`，并以“不是主产品路径”压低 retry §16、TUI 0 等候选。direct Spec §2.6 自己也把 Anthropic direct 写成“主路径”，但它是 `.dev` 推导文档，不能覆盖更近的项目级边界。
- 影响：首选结论未必改变，但候选排序的一个承重前提是错的。尤其 hosted web search D6 位于真正的 Anthropic inbound → Responses upstream 路径；它的优先级只能因默认关闭、当前主线阻塞度、用户裁定时点与完整性成本而降低，不能因路径归类降低。
- 建议：把“主路径”论据删掉或改为“Claude 模型可达性的关键 direct route”。重新陈述排序权重：`D-5` 胜在用户后续明确裁范围、当前 direct-passthrough 接线 blocker 与确定性故障；hosted search D6 胜在真实主产品路径但默认关闭；TUI 0 与 retry §16 依各自 served surface 与流量证据排序。若重排后 `D-5` 仍首选，结论即可保留。

## Minor findings（集中）

### M-01

- finding_id：`NRF-M01`
- severity：`minor`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:29,34`
- related_locations：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/deferred.md:109-120`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/hand_over.py:32-38,238-281`
- 证据：`D-7` 的字段属于 continuation intent，草稿把它纳入同一语义切片是对的；但“同片”不等于必须与整个 finalization 实现在同一 commit。当前 helper 的 `messages`／`input` 读取可作为一个独立、立即有规范价值的前置小片落地，只是不能因此把 `D-5` 标成完成。
- 建议：将“完成边界一致”和“提交边界可拆”分开写，避免为了语义归属强行制造大提交。

### M-02

- finding_id：`NRF-M02`
- severity：`minor`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:46-54`
- related_locations：`/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:43-97`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/auto-mode-classifier/deferred.md:20-46`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/multi-provider-routing/deferred.md:4-15`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/deferred.md:121-161`
- 证据：未选候选的主判断大体成立，但 hosted search 的调查只点了 §4.2 D6，漏了同一 living status 后部 2026-08-24 已裁未实现的 §4.5 `empty_result`；该 status 文首锚定 2026-08-22，正文有后续增量，不能仅凭标题级快照概括整个 backlog。这个遗漏暂不足以把它抬过 `D-5`，因为功能仍默认关闭，但候选面不是完整枚举。
- 建议：在候选表补 §4.5，并给每个结论写明读取的是当前条目而非文首旧锚点。

### M-03

- finding_id：`NRF-M03`
- severity：`minor`
- primary_location：`/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md:26-28`
- related_locations：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/anthropic_messages.py:175-194,222-281`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:129-218,351-417`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:326-364`
- 证据：format-neutral intent、driver-owned ordering 与 dialect-owned encoding 是正确的职责切分；但“per-dialect writer”若被读成新建第三套 writer，会重复现有 `AnthropicFramer`／`ResponsesFramer` 的事件与终局词汇。
- 建议：计划明确优先扩展现有 framer 的 typed continuation projection，或复用其模块级 frame builders；只有现有接口无法表达时才新增对象。草稿否决把 `PassthroughFramer.block` 放宽为 union 是正确的。

## C1-C9 逐项核验

### C1：通过

后续用户裁决足以让 `D-5` 无需再次交用户决定，并覆盖 Responses direct。`direct-passthrough/deferred.md:70` 保存了具名日期与用户原话，Spec 修订记录 v15 在 `spec.md:708` 记录同一来源与射程。人写文档 `upstream-retry-and-continuation.md:40` 的旧限制带有明确时态“目前”与未来触发条件“未来我有需要后再补全”；2026-09-01 裁决正是该触发条件，不构成两个同时有效且互斥的永久裁决。限定：本次没有原始 transcript，用户裁决 provenance 依赖两份独立 living 文档一致记录；证据足以据以行动，但不把 `.dev` 文档本身冒充人写权威。

### C2：通过

对 `src/` 与 `tests/` 的定向引用检索显示，production 只有 `delivery_policy.carries_upstream_natively()` 一个 native 选择函数。它在当前 revision 只对 `OPENAI_RESPONSES` 返回真（`delivery_policy.py:58-73`），`framer_for()` 与 `assembler_for()` 分别在 `:96-106`、`:121-131` 咨询它；真实入口 `inference.py:326-385,493-515` 只经这两个 factory 构造并交给 `stream_delivery()`。`anthropic_passthrough_assembler()` 的其余引用全部在 unit tests，没有第二套 production selector 或 writer 兜底。`passthrough=not context.translation_required` 只是 failure carrier 标志，不会替换 assembler/framer，因此不是另一道 selector。

### C3：通过

源码顺序与独立探针共同支撑草稿故障结论。`stream.py:388-396` 在每个 `assembler.push()` 后立即 `_commit()`；正常读完后 `:510-524` 先 `assembler.close()` 与 `session.finish()`，`terminal` 与 continuation 判定到 `:526-536` 才发生。`_hand_over()` 在 `:624-626` 构造 `CompletedBlock` 并调用 `framer.block()`，而 `PassthroughFramer.block()` 的签名与实现只接受 `RawEventBatch` 并调用 `encode()`（`passthrough.py:353-356`）。独立探针 `/tmp/next_root_fix_probe.py` 在该 revision 逐一运行 `block`、`full`、`until-tool-use`，三次都先观察到 `message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop`，随后得到 `AttributeError: 'CompletedBlock' object has no attribute 'encode'`，且 synthetic call 未输出。结论限定为“绕过当前 selector、用现有构件接线时确定失败”，不外推为生产当前已触发。

### C4：通过，带 M-01 限定

`num_messages` 是 neutral intent 的业务字段，不是方言 writer 的显示细节。用户文档 `:30` 同句定义 `messages / input`；当前 `hand_over.py:37` 只读 `messages`，而 `:238` 还把 Responses 挡在外。Responses continuation 一旦启用，错误计数与功能同时可达，因此 `D-5` 的完成边界必须包含 `D-7`。它可以作为前置小提交独立落地，不应被误写成只能与全部 D-5 代码原子提交。

### C5：不通过

`D-6` 在代码组织上是独立 failure taxonomy 工作，但不是“`D-5` 完成以后再做也不影响完成声明”的后续项。F-02 说明 native failure 正是 continuation 决策输入；没有 Anthropic `error.type` 映射与通用 adapter，就无法对已提交内容后的错误区分 continuation 与原失败。草稿第三刀“补 D-6 → 打开 selector”的执行顺序比文首“D-5 已使所有直连腿可用、D-6 随后”更准确，两者当前自相矛盾。另按 F-03，selector 还有 signature reshape 前置，不能写成只由 D-6 决定。

### C6：通过，带 M-03 限定

现状的根因确实横跨三个职责：`ContinuationSupport.synthesize` 产出 Anthropic dict，driver 在 terminal 已出门之后才决定 continuation，passthrough framer 只承载 raw batch。format-neutral intent、显式 finalization outcome 与 dialect projection 能分别关闭类别、顺序与方言问题，不是仅为形式抽象。更小但同样闭合的实现可以不新建“writer 类”：保留 typed intent 与 ending outcome，把 projection 加到现有 framers 或模块级 builders。不能采纳只延迟 `message_stop`，也不能把 `PassthroughFramer.block` 改成 `RawEventBatch | CompletedBlock`。

### C7：通过，带 M-02 与 F-04 限定

读取当前条目后，auto-mode D-1 的 synthetic observability 缺陷属实且真实命中仍未验证；hosted search D6 已裁未实现但功能默认关闭；TUI 0 的现象已有 mock 证据但流量权重未知；retry §16 是 served 的反向翻译缺陷且修法明确；multi-provider D-1 是只在错误配置下出现、fail-closed 的静态告警缺口；direct D-9 的客户端机制与代理差异已定位，但真实 upstream duplicate-done 触发仍未取证。它们都不足以按当前证据取代 `D-5`。需要修正的是候选枚举漏项与“主路径”归类，而不是直接换首选。

### C8：不通过

草稿已正确点名 Responses terminal 的 `output`／usage／id／sequence／index 与 compatibility reshape 需要先入 Spec，未擅自定细节；这些面没有漏。真正漏出切片的是三面：F-01 的 non-stream body 路径、F-02 的 upstream native failure 动作矩阵、F-03 的既有 Anthropic signature reshape 默认值。三者都会让“所有直连腿 continuation 可用”在代码完成后仍为假，因此不是可延后的测试细节。

### C9：部分不通过

“当前现有构件一旦绕过 selector 必然先发 terminal 再类型崩溃”已由 C3 限定并复现；“没有第二套 production selector/writer”已由 C2 的全仓引用面支撑；“D-5 无需新用户决策”由 C1 支撑。需要收回的全称有三处：`D-5` 不是 selector 安全启用的“唯一 blocker”（还有 F-02 的 failure taxonomy 与 F-03 的 reshape preservation）；Anthropic direct 不是仓库定义的“主产品路径”（F-04）；“使所有直连腿可用”的完成声称未覆盖 non-stream（F-01）。

## 被否决的替代解释及理由

1. **“人写文档第 40 行仍禁止 Responses continuation，所以必须再问用户。”**否决。该句自带“目前”与“未来有需要”的时态，后续具名裁决正好闭合其开放条件；再次询问会把已有裁决伪装成未决。
2. **“只把 `message_stop` 晚发即可。”**否决。独立探针证明晚发不能改变 `CompletedBlock` 被传给只认 `RawEventBatch` 的类型冲突；Responses 也不是一个 `message_stop` 事件的问题。
3. **“让 `PassthroughFramer.block` 接受 union 最小。”**否决。它把 raw native batch 与 synthetic semantic call 两类交付单位压进同一方法，方言选择与 finalization 顺序仍无 owner，类型系统当前给出的类别错误反而被掩盖。
4. **“`D-7` 完全独立，修完计数就可以从 `D-5` 移出。”**否决为完成边界，部分接受为提交边界。它可先单独提交，但 Responses continuation 交付前必须消费正确的 `input` 数量。
5. **“`D-6` 可以在 selector 打开以后再补，因为 failure 不是 continuation。”**否决。用户合同先问错误是否可继续，而 native failure 的分类恰由 D-6 提供；当前 source 还会在 failure 分支提前 return。
6. **“因为 Anthropic direct 不是主产品路径，`D-5` 应直接失去首选。”**否决。路径标签确实要修，但 `D-5` 仍有后续用户裁决、当前 direct-passthrough 主线 blocker 与确定性接线故障三项独立依据；现有证据只要求重做权重说明，不足以改选。
7. **“存在另一个 production selector 或 writer，会让 C3 组合不可达但仍被兜底。”**否决。引用检索与真实入口顺读没有找到；唯一使组合不可达的是 `carries_upstream_natively()` 当前只放行 Responses。

## 我最没把握的三个判断

1. **后续用户裁决的 provenance 强度。**我对“足以据以行动”置信度高，对“原话记录逐字无误”置信度中等，因为本次可读证据是 Spec 修订记录与 deferred 的一致转录，不是用户原始 transcript。这个不确定性不足以重开决定，但调用方若握有原 transcript，应以它核一次引文。
2. **native failure 最终 carrier 的精确规则。**我对“必须纳入 D-5/D-6 共同闭包”置信度高，对每个 `error.type`／code 最终是 continuation、原失败还是 proxy error 的格子置信度中等；原因正是 living Spec §5.2 与 §7.2／§8 尚未把用户 continuation 合同闭成同一张动作矩阵，不能由 reviewer 越权替它定案。
3. **F-04 对首选排序的实际翻转概率。**我对“Anthropic direct 不是项目定义的主产品路径”置信度高，对纠正后 hosted web search 是否会超过 `D-5` 置信度中等偏低。默认关闭与当前 direct 接线 blocker 仍让 `D-5` 更强，但这需要分析作者重算权重，而不是沿用错误标签。

## 执行本契约时遇到的摩擦

1. `my-agents:as-reviewer` 不在当前 skill 注册表，首次按要求调用即返回 `Unknown skill`；已记录并改按 coordinator checklist 执行。
2. CodeGraph 工具可调用，但项目根没有 `.codegraph/` 索引，工具明确要求改用内置读取／检索；后续未重复调用。
3. 隔离机制拒绝写主工作树指定 REPORT_FILE，错误明确要求只能写 worktree copy；按用户预设 fallback 改写到 `/home/xp/.claude/jobs/f5849771/tmp/260903-next-root-fix-analysis-review-general-opus.md`。
4. 隔离 guard 先后拒绝包含复杂 shell 结构的只读、探针与尾部核对命令；改为拆分 `cmp`、把探针脚本放入 `/tmp` 后以简单命令运行。最终尾部哨兵与计数由成功的精确 `Edit` 写入，不把被拒命令误报为已执行。`uv run` 在隔离 worktree 创建了 ignored `.venv`，`git status --short` 仍为空；没有修改主仓源码、测试、Spec、deferred/status、评审对象或其他报告。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T08:48:57+00:00
verdict: needs-fix
finding_total: 7
blocker_count: 0
major_count: 4
minor_count: 3

## 复评：七条处置闭合核验

- attempt_id：`260903-next-root-fix-review-general-opus-2`
- rereviewed_at：`2026-09-03T08:52:11+00:00`
- 复评对象：修订后的 `/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis.md` 与 `/home/xp/.claude/jobs/f5849771/tmp/next-root-fix-analysis-review-disposition.md`。
- 范围：严格限于 `NRF-01`～`NRF-04`、`NRF-M01`～`NRF-M03` 的处置 diff 及其已在上一轮核过的相邻合同；没有重做全量 backlog 或源码扫描。
- 最新判定：**pass，可交付。**上一轮七条发现全部 closed，当前没有 open finding，也没有残余 minor。旧 `needs-fix` 与旧尾部计数是第一轮时点记录；本节末尾的新交付声明是修订稿的当前结论。

### 逐条状态

| finding_id | 当前状态 | 复评证据与判断 |
|---|---|---|
| `NRF-01` | **closed** | 修订稿结论已把 streaming 与 non-streaming 一并纳入 D-5 完成边界（`:4-8`）；Spec 先行清单明确列出两种 direct whole-body 的触发、完整单位、synthetic call 与终局字段来源（`:23-31`）；生产合同区分 streaming driver 与 whole-body finalization（`:35-37`）；实施序列与最小判据均要求从 Anthropic／Responses direct non-stream 真实入口验证（`:44-48,57`）。这不再把用户亲笔的 non-stream 合同缩成 SSE 工作。 |
| `NRF-02` | **closed** | 修订稿已把 native failure 的 replay／continuation／final failure 动作矩阵列为实现前 Spec 工作，并点明现行 §5.2 与 §7.2／§8 的冲突（`:28-31`）；D-6 被明确改为 selector 启用及 D-5 对外完成的前置，而非完成后的清理（`:40,44-48`）；最小判据覆盖未提交 funded replay、已提交 continuation、不可继续 failure 保持原 carrier 三向对照（`:59`）。处置账对该变更的归因与实际文本一致。 |
| `NRF-03` | **closed** | 修订稿 Spec 清单明确要求规定 embedded signature reshape 在原生 batch 上的作用顺序（`:25-26`）；生产合同把当前 `signature_delta` 默认行为列为 selector 前置，同时保留 D-4 长期默认形态给用户裁定（`:38`）；实施序列与判据分别要求接好 reshape 后再开 selector，并覆盖默认启用、显式关闭与 synthetic continuation 不被误处理（`:48,62`）。没有把“保持现有默认”与“长期是否常驻”混成同一个待决项。 |
| `NRF-04` | **closed** | 修订稿已把 Anthropic direct 改称“Claude 模型可达性的关键 direct route”，并逐字承认项目主产品路径仍是 Anthropic inbound → OpenAI Responses upstream（`:14`）；候选比较把 hosted search 的真正主路径优势写回，同时仅以默认关闭、当前 direct 主线 blocker 与确定性组合故障维持 D-5 首选（`:67-70`）；承重前提也收窄到模型可达性而非项目主路径（`:78`）。首选依据已重算，不再由错误路径标签承重。 |
| `NRF-M01` | **closed** | 修订稿在结论、生产合同、实施序列与边界说明四处一致区分“D-7 属于 D-5 完成边界”与“可先独立语义提交”（`:4,39,45,50`），没有强迫一个大提交，也没有用先提交冒充 D-5 完成。 |
| `NRF-M02` | **closed** | hosted search 近邻项已同时列入 §4.2 D6 与 §4.5 `empty_result`，并说明两者处在真实主产品路径但因默认关闭暂不超过 D-5（`:67`）。遗漏已补，首选未被无据维持。 |
| `NRF-M03` | **closed** | 生产合同明确优先扩展现有 `AnthropicFramer`／`ResponsesFramer` 的 typed projection 或复用 module-level builders，不新建第三套方言词汇，并继续拒绝把 `PassthroughFramer.block` 放宽为 union（`:35-38`）。这保留 format-neutral intent 与显式 ending outcome，同时避免把“per-dialect writer”误做成平行实现。 |

### 对处置账的核验

处置账七行均标为 `adopted`，且每行所称修改都能在修订稿找到对应合同、实施序列或判据；“被否决的建议：无”与本轮实际一致。我没有发现处置账把“写进分析”夸成“代码已实现”，也没有发现它用成本理由缩小用户已裁范围。`NRF-02` 与 `NRF-03` 的前置关系现在都落在“D-5 对外完成／selector 启用”而非强制同一 commit，边界正确。

### 相邻合同复核

1. **权威边界未越界。**修订稿把 non-stream、两种客户端方言与后续射程归到用户既有合同／后续裁决；具体 event/body 形状、动作矩阵与字段来源归到 Spec §2.3 推导层，并坚持先改 Spec、再实现。D-4 的长期默认仍明确留给用户。
2. **真实入口没有再次被抽象掩盖。**修订稿同时要求 Responses direct streaming／non-stream 与 Anthropic selector 的真实 route 测试，仍明确 helper-only 不算接线证据。
3. **类型与顺序合同闭合到建议层。**typed intent、driver-owned finalization、方言 projection 与 raw passthrough batch 保持不同类型；terminal／continuable failure 在 continuation 决策前不得出门。具体 wire 值仍留给 Spec，而不是由分析越权定案。
4. **切片完整而提交可拆。**D-7、核心 finalization、D-6、Anthropic reshape／selector 按语义拆成五步，但只有全部前置闭合后才允许宣称 D-5 完整；这符合“小片集成”而不缩小完成定义。

### 复评结论

七条原 finding 的处置均站得住，无需反驳或 reopen。当前修订稿可以作为“下一项首选与根因修复边界”的分析交付；它不是实现完成声明，后续仍须按其自身顺序先修 living Spec 并独立评审。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T08:52:11+00:00
verdict: pass
finding_total: 7
closed_count: 7
open_count: 0
blocker_count: 0
major_count: 0
minor_count: 0

## 复评：条件排序、native side facts 与近邻比较

- attempt_id：`260903-next-root-fix-review-general-opus-3`
- rereviewed_at：`2026-09-03T09:06:50+00:00`
- 范围：只复核上次 pass 后新增的三类内容及上一轮已核相邻合同，不重做全量 backlog、源码或 cassette 审计。
- 最新判定：**pass，仍可交付。**本轮新增 finding 为 0；上一轮七条 finding 继续保持 closed。

### 1. D-5 的条件性首选：站得住

修订稿不再给无条件全序，而是在“当前可见文档没有记录近期 hosted-web-search rollout／默认启用计划”的显式前提下，以中等置信暂列 D-5 第一（`:4-8,81`）。这个前提只控制排序，不控制 D-5 与 hosted D6 各自是否成立；稿件还明确禁止从文档缺席推出运营计划不存在，并给出反转条件：若 coordinator 掌握近期 rollout 事实，primary product crossing 上启用即错 carrier 的 hosted D6 应重新比较并可能升到第一。

相邻合同支持这组权重：`hosted-web-search/status.md:11,24-42` 记载功能默认关闭、启用后仍把应为原生块对的结果降成 text；`:56-62` 记载 D6 已裁未实现；`:84-98` 记载 `empty_result` 已裁但尚不可配置，同时默认值仍待用户裁。修订稿因此既没有把默认关闭误写成“不参与排序”，也没有把未观测 rollout 写成不存在。D-5 仍有更新的明确裁决、当前 direct 主线 blocker 与确定性组合故障支撑；“中等置信默认顺位”与现有证据强度相符。

### 2. project-review F-01 的顺位、前置关系与证据分层：站得住

`PassthroughAssembler.push()` 在 item done 上只增加 `Terminal.blocks` 并维护 `_saw_client_action`（`delivery/passthrough.py:173-189`），没有调用 `Terminal.record()` 或等价 native item observation；而 `Terminal.record()` 才是 tools／thinking 的统一分类入口（`delivery/assembling.py:40-60`），`RequestTrace.absorb()` 会把 `Terminal` 的空默认值原样复制到完成记录（`observability/request_trace.py:183-194`）。这与 direct Spec §10 的规范相反：native wire 保持上游原生，旁路仍至少要记录 tool 名称／类型与 reasoning，并把 unknown 与 absent 分开（`direct-passthrough/spec.md:661-667`）。所以 F-01 是 typed side-fact 缺口，不是“补一条日志”。

修订稿正确拆分了经验与静态证据：两份既有 cassette 只被用来支撑同一 recorded Responses reply 的 reasoning 摘要从 translating `['enc']` 变成 native `[]`；tool item 未出现在这两份录制中，稿件只以当前 producer/consumer 控制流证明分类入口缺失，并明确禁止冒充 cassette 观测（`:38,49,64,70,83`）。本轮没有重跑 cassette；这里复用的是已由 project-review 原报告与独立复审共同核过、且后者已收窄 item 集合的证据，不把它升级成新观测。

把 F-01 排第二并列为 Anthropic selector 前置也不混淆切片：当前 `/responses` direct 已受影响，所以它可作为 D-5 核心之前的独立小片；它与 continuation 根因不同，不被塞进同一 commit。另一方面，Anthropic translating 路径当前会通过 `Terminal.record()` 得到 side facts，若 native selector 在旁路分类补齐前启用，operator-facing record 会从已读事实退成缺席；因此它是 selector／direct-passthrough 对外完成前置。修订稿明确保留这条传递依赖，同时不把 F-01 误称为已实现或已 closed（`:38,49-52,70,83`）。

### 3. hosted D6／`empty_result` 与 project-review F-02／F-03 的比较：站得住

修订稿将 hosted D6 与 `empty_result` 放回候选面并分别说明可达性：D6 在功能显式启用时已是 served path 且 carrier 错误，`empty_result` 则因 schema 未提供该取值而当前不可选；默认关闭与不可配置只降低权重，不抹掉已裁未做状态（`:71,81`）。这与 hosted status 的当前记录一致，也保留“若近期 rollout 则重排”的回路。

F-02 被准确限定为 count-tokens 直接写 `trace.usage`、当前渲染尚正确但共同 observation 构造入口存在漂移风险；F-03 被准确限定为三处 surface 越权结局断言，处置是撤结局承诺并保留邻近 rationale。修订稿只用它们比较失败后果与解锁价值，没有声称代码已修，也没有因工作量小而前移（`:75`）。project-review 处置账仍把 PPR-260903-01～03 标为 adopted 但实现层 open；分析稿的措辞与该状态一致。

### 本轮反驳与残余项

没有一项新增处置需要反驳。三个容易误读的边界均已写清：条件性首选不是运营事实声明；F-01 的 cassette 权重只覆盖 reasoning；“selector 前置”是完成依赖而不是强制 commit 合并。未发现 blocker、major 或 minor。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T09:06:50+00:00
verdict: pass
finding_total: 7
closed_count: 7
open_count: 0
rereview_finding_total: 0
blocker_count: 0
major_count: 0
minor_count: 0
