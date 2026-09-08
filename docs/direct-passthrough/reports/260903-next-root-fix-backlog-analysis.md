# 下一个无需决策、值得根因修复的 backlog item

## 结论

在当前文档中没有已记录的近期 hosted-web-search rollout／默认启用计划这一前提下，中等置信首选 `direct-passthrough/deferred.md` D-5：建立格式无关的 continuation intent 与按客户端方言投影的统一 finalization contract，使 streaming 与 non-streaming continuation 在每条直连腿上原生可用。D-7 属于它的完成边界，可以先作为独立语义提交落地；D-6、native side facts 与 Anthropic `signature_delta` reshape 的当前默认行为属于 selector 启用和 direct-passthrough 对外完成的前置，不能在接线宣称闭合以后再补。

这不是“打开 Anthropic selector”，也不是“把 `message_stop` 晚发一点”。当前缺失的是 continuation 领域决策、streaming／whole-body 流程终局与方言编码之间的一份显式 typed contract。只修一个症状，会在类型、顺序、non-stream、native failure、side-fact observability 或 compatibility reshape 的另一面继续失败。

证据权重：足以据此采用 D-5 作为当前默认顺位，不足以建立无条件全序。依据包括当前 living Spec 一致记录的 2026-09-01 后续用户裁决、当前 direct-passthrough 主线的未闭合接线、当前源码的类型与顺序事实、一个绕过 selector 的最小执行探针，以及既有用户合同对 non-stream 和两种客户端方言的明确覆盖。它不证明生产今天已经触发组合崩溃，因为 selector 正在刻意阻止该组合；它证明的是按现有构件直接完成已裁接线必然失败。若实际近期目标是启用 hosted web search，位于项目 primary product crossing、已裁但仍给错 carrier 的 hosted-search D6 会成为更直接的下一项；当前文档没有这项运营前提，所以不据一个未观测计划改选。受这项条件约束的只是排序，不是 D-5 或 hosted-search D6 的成立性。

## 为什么是它

1. **无需用户再裁。** `direct-passthrough/spec.md` §2.8 与修订记录 v15、`deferred.md` D-5／D-7 一致记录用户 2026-09-01 的后续裁决：continuation 必须在每条直连腿上以本腿原生方言可用。较早的人写文档第 39 行写的是带时态的阶段限制“目前只给 anthropic-messages”，并明示“未来我有需要后再补全”；后续裁决触发了这个开放条件，不是两个同时有效的永久裁决。当前证据来自两份 living 文档对用户原话的一致转录，不是原始 transcript；强度足以据以行动，不冒充一手原文。
2. **阻塞当前 direct-passthrough 主线。** `plan.md` 文首与 §8 明确：Responses 直连腿已接线，Anthropic 方言词汇已实现但 selector 未打开，continuation 是已经具名的直接 blocker。最近主仓和 `.dev` 的开发主线也集中在 direct passthrough，而不是另一个主题。
3. **它是 Claude 模型可达性的关键 direct route。** Spec §2.6 记录 `claude-sonnet-5` 不支持 Responses API，因此该模型只能走 Anthropic direct。这个事实说明 route 重要，但不把它改写成项目“主产品路径”——项目 `CLAUDE.md` 定义的主产品路径仍是 Anthropic Messages inbound → OpenAI Responses upstream。
4. **它有两个独立、可执行的 streaming 故障，而不是文档推演。** `stream.py` 在检查 `terminal.stop_reason` 之前已经提交 `assembler.close()` 与 `session.finish()` 的所有字节；`_hand_over()` 又把一个 `CompletedBlock` 传给 `PassthroughFramer.block()`，后者只接受并调用 `RawEventBatch.encode()`。绕过 selector 的探针对 `block`、`full`、`until-tool-use` 三种 policy 都得到同一个结果：客户端先收到上游 `message_delta + message_stop`，随后抛 `AttributeError: 'CompletedBlock' object has no attribute 'encode'`。
5. **non-stream 不是顺带项，而是同一用户合同的另一半。** 人写文档明确规定非流式也支持合成续写；真实入口在 `inference.py:524-573` 另走 whole-body 路径。现有实现只检查 Anthropic `stop_reason/content`，Responses direct 的 `status == incomplete`、`incomplete_details.reason == max_output_tokens` 与 `output` 完全不进入 continuation。只修 SSE 会把“所有直连腿”悄悄缩成“部分 streaming 腿”。
6. **它能做成根修。** `ContinuationSupport.synthesize` 现在产出 Anthropic `tool_use` dict，delivery 再把它硬塞成 Anthropic `CompletedBlock`；原生 terminal 同时作为普通 `RawEventBatch` 数据和 `Terminal.seen` side channel 出现，driver 在读 side channel 前已把数据提交；whole-body 路径又自行重判另一套字段。格式无关 intent、显式 finalization outcome 与复用现有方言 framing primitives 能让一个事实只判一次，同时让 streaming 与 non-stream 共享决策而各自执行正确流程。

## 根因修复边界

### Spec 先行

当前 Spec 只裁了“以该方言原生事件表达并放在终局之前”，还没有把完整行为闭成一张合同。实现前需要由 Spec §2.3 的推导层补齐并独立评审以下内容；这些是设计工作，不是新的用户产品决策：

- streaming Responses continuation 的事件序列、原上游 terminal 的替换规则、`response.output`、`sequence_number`、`output_index`、response/item id、usage 与 compatibility reshape 的交互；
- streaming Anthropic continuation 对原 `message_delta/message_stop` 的持有／替换规则，以及 embedded thinking signature reshape 在原生 batch 上的作用顺序；
- non-stream Anthropic 与 Responses body 的触发判据、保留哪些完整 `content/output` 单位、如何追加 synthetic `tool_use/function_call`、最终 stop/status/incomplete_details/output/usage/id 的来源；
- native failure → funded replay／continuation／final failure 的动作矩阵。现有 Spec §5.2 要求分类 native failure，而 §7.2／§8 又把最终可见 failure 写成逐字交付；两者必须先消除冲突，不能由实现临场选择；
- 与 translating 路径共享的 semantic continuation contract：eligibility、category、message、`num_messages` 与“已交付／已保留完整单位”的判据只能有一个答案，wire 投影才按方言和 streaming 形态分开。

共同不变量至少是：先交付所有应保留的完整单位；原上游 successful／incomplete terminal 或可继续 failure 不得先出门；随后写一个客户端可执行的 continuation call；最后只写一个与该 call 一致的终局；不可继续 failure 保持其规定 carrier；已有上游 item/content block 语义不被重译；代理合成字段有明确来源且不会冒充上游原生字段。

### 生产合同

1. **策略产出 typed intent。** 把现有 `hand_back_block()` 的领域部分收成格式无关的 `ContinuationIntent`／`ContinuationCall`，包含 tool name、call id、`num_messages`、category、message 与适用性 outcome。策略不产出 Anthropic dict，不进入发送循环，也不决定 sequence/index/terminal。
2. **流程驱动拥有 finalization。** streaming driver 拥有顺序、buffer flush、commit frontier 与 terminal 是否仍可提交；whole-body driver 拥有 body 最终化。两者消费同一个 intent。terminal arrival 必须成为显式 ending outcome，而不是既藏在普通 `RawEventBatch` 里又通过 `Terminal.seen` 旁路通知；driver 在任何 terminal frame/body 离开前解释 outcome。
3. **复用现有方言 writer。** 优先扩展 `AnthropicFramer`／`ResponsesFramer` 的 typed continuation projection，或复用其模块级 frame builders；不要新建第三套重复方言词汇。也不要把 `PassthroughFramer.block` 放宽成 `RawEventBatch | CompletedBlock`：那会抹掉当前类型系统准确报告的类别错误，并把方言分支藏进一个本应只转发 raw batch 的方法。
4. **补齐 native typed side facts。** `PassthroughAssembler` 当前只增加 `Terminal.blocks`，不调用 `Terminal.record()` 也没有等价 native item observation；完成记录因而把没读到的 reasoning/tools 写成缺席。方言层应从原生 item 产出 typed side facts，统一摘要类型拥有唯一分类入口；这些事实只进入 observability，不反向改写 native wire。两份真实 cassette 已实证 reasoning 从 translating 的 `['enc']` 变成 native 的 `[]`；tools 同族缺口由源码控制流证明，不能说成 cassette 已观测。
5. **保持当前 Anthropic reshape 默认值。** selector 打开前，passthrough 必须让 `hook_fix_anthropic_sse.thinking.content_block_start_compat=signature_delta` 继续按当前默认生效，显式关闭时继续保留 embedded 形态。这里只兑现 Spec §2.7 已定的当前默认；D-4 的长期“默认可关还是常驻不可关”仍是另一个待裁产品分叉。
6. **D-7 进入完成边界。** `client_message_count` 同时读取客户端 body 的 `messages` 或 `input`，使用非空 Responses input 做回归，避免 0 对 0 的假绿。它可以先独立提交，但不能因先提交就从 D-5 完成条件中移出。
7. **D-6 进入启用前置。** native failure 分支当前在 `_report_failure()` 后直接 return，完全绕过 replay／continuation。D-6 的方言 taxonomy 与通用 adapter 可以保持独立提交，但没有它就不能区分已提交内容后的可继续与不可继续 failure，因此 Anthropic selector 不能启用，D-5 也不能对外宣称完整。

### 建议实施序列

1. **Spec/plan 切片。** 完成上述 streaming、non-stream、failure matrix 与 reshape 合同，独立评审。这里没有用户决策门；若推导过程中发现与现有用户裁决真正冲突的新产品分叉，才另行提问。
2. **D-7 小片。** 让计数 helper 同时读 `messages/input`，直接提交并验证；它是独立语义提交，也是 D-5 的前置组成。
3. **核心 continuation 合同。** 实现 format-neutral intent、streaming ending decision point、whole-body finalization 与两种客户端方言的 projection，优先复用现有 framers/builders；从真实 Responses direct streaming/non-stream route 入口证明接线，而不是只直接构造 helper。
4. **native failure taxonomy。** 完成 D-6 与 Spec 动作矩阵的 adapter；至少覆盖可继续 failure 在未提交时 replay、已提交时 continuation，以及不可继续 failure 保持原 carrier。
5. **native side facts。** 让 passthrough item 的 reasoning／tool／client-action 等 typed facts 进入统一摘要，并用同一录制输入比较 translating/native 摘要；reasoning 用 cassette 实证，tool 分类用相符的现有录制或本项目 side-fact focused test，不能把源码推断冒充录制观测。
6. **Anthropic reshape 与 selector。** 为 passthrough 接上当前 `signature_delta` 默认行为，再打开 Anthropic direct selector；真实 route 同时覆盖 streaming/non-stream、默认 reshape 与显式关闭。到这一步才能宣称 D-5 与 Anthropic direct 接线完整。

这些是完成依赖，不要求挤进一个大提交。commit 边界按语义拆分；D-5 的完成边界按用户合同闭合。F-01 可以在 D-5 核心前独立落地，因为它已经影响当前 `/responses` direct；把它列入 selector 前置不等于强迫它与 continuation 共用一个提交。

## 最小判据

- 三种 buffering policy 下，原上游 terminal 均不早于 continuation call，且最终只有一个 terminal。
- Anthropic direct streaming：已完成内容保留，synthetic `tool_use` 紧随其后，最终 stop reason 为 `tool_use`；不存在先前的 `message_stop`。
- Responses direct streaming：已完成 output item 保留，synthetic `function_call` 成组出现，最终 response object 与事件序列一致；明确断言 sequence/index/id 与 terminal output 的规则。
- Anthropic 与 Responses direct non-stream：分别从真实 route 入口触发 `max_tokens/max_output_tokens` continuation，保留完整单位、追加正确 call、只产生一个终局 body。
- 非空 `messages` 与非空 `input` 分别得到正确 `num_messages`。
- 可继续 native failure 的三向对照：未提交且有预算时无痕 replay；已提交完整单位时 continuation；不可继续 failure 保持原 failure carrier。
- translating 与 direct 对 continuation intent 字段相等，而不是各自对两份字面量；streaming 与 non-stream 同样共享 intent 判定。
- 无 continuation 配置、未交付／未保留完整单位、proxy protection、客户端取消等负样本保持原结局。
- 同一录制 Responses 回复的 translating/native 摘要对 reasoning 与已观测 item facts 相等；未知事实表达为 unknown 而不是 absent。对 tool 名的判据必须注明 ground truth 是录制还是本方 side-fact contract。
- Anthropic direct 默认配置下 embedded signature 仍产生 `signature_delta`；显式关闭时原样保留 embedded 形态；synthetic continuation block 不被该 reshape 误处理。
- selector 接线测试必须从真实 route 入口证明 Anthropic direct 选到 passthrough assembler/framer；只直接构造词汇对象不算接线证据。

## 未选的近邻

- **project-review F-01：native passthrough side facts。** 当前 `/responses` direct 已可达，客户端 wire 正确，但 operator-facing completion record 把 reasoning/tools 的“没有 reader”写成缺席。两份真实 cassette 已复现 reasoning parity 反例；tools 是源码控制流确定的同族缺口。它无需用户裁决、根因与回归边界都清楚，并且会在启用 Anthropic selector 时扩面，所以列为第二顺位，也列入 selector 前置。它暂不超过 D-5，是因为影响限于可观测记录，而 D-5 承接更新的明确用户裁决并阻塞当前 direct 功能闭合；若要先拿一个更小、已影响 live route 的独立提交，F-01 是合适的第一小片，但这不把 D-5 从项目级首选移走。
- **hosted web search §4.2 D6 与 §4.5 `empty_result`。** 两项都已裁未实现，并且位于项目真正的 Anthropic inbound → Responses upstream 主产品路径；这是它们最强的优先权。当前仍低于 D-5 的理由是该能力默认关闭，而 D-5 是当前 direct-passthrough 主线的接线 blocker，且已有确定性组合故障。若近期要启用 hosted web search，D6 应改排第一；当前文档没有这项计划。不能用“不是主路径”压低它们。
- **auto-mode D-1。** synthetic reply 被记成真实上游交换是成立的根因型可观测性缺陷，应一次修两条 synthetic 路径；但当前环境的 auto mode 分类器没有真实命中，hosted web search 合成路径也受能力门与默认关闭限制，且它不解锁当前 direct-passthrough 主线。
- **TUI deferred 0。** `/responses` 与 `/chat/completions` 的回复汇总缺失已有 mock 证据，是 served surface 的功能缺口；台账自己把 ROI 绑定在未测流量占比上。它低于已有后续用户裁决、当前主线 blocker 与确定性组合故障的 D-5，而不是因为项目主产品路径标签。
- **retry-and-continuation §16。** served 的 `/responses` client + Anthropic upstream 路径会把 refusal 报 completed、丢 incomplete reason，修法明确且无岔路；它不是项目主产品路径，但这只是一个权重，低于 D-5 的主因仍是它不阻塞当前 direct 工作且射程更窄。
- **project-review F-02 与 F-03。** F-02 是 count-tokens 直接写 `trace.usage`、绕过共同 observation 构造入口的结构漂移风险，当前渲染尚无错误；F-03 是三处越权承诺面，修法是撤 surface 结局断言并保留邻近 rationale。两者都无需裁决，但失败后果与解锁价值低于 D-5/F-01。
- **multi-provider D-1 与 GHE D-2。** 前者只在配置写成永不可命中的键时 fail-closed，后者是潜伏的构造点漂移；都是合理小补丁，但当前失败后果与解锁价值较低。
- **direct-passthrough D-9。** 当前只完成了“可能是重复 close”的最小观测，真实上游触发条件仍未取证；下一步等真实会话，不是现在可直接实施的根因修复。

## 承重前提

前提：本次可见的活文档没有记录近期启用／默认开启 hosted web search 的计划。它支撑 D-5 暂列第一，而不是 hosted-search D6。若实际已有未写入文档的近期 rollout，D6 位于 primary product crossing、启用即给错 carrier，应改排第一；这不会改变两项各自是否成立。当前只能给中等强度的默认排序，不能据文档缺席声称运营计划不存在。

前提：F-01 的当前后果限于 operator-facing record，不改变 client wire。它支撑 F-01 排在 D-5 后。若实际运营主要依赖 `/responses` direct 的 completion record，或该错误正在驱动错误操作，优先级可反转；当前没有这种具名事故。两份 cassette 实证 reasoning parity，tools 缺口只由源码控制流支撑，证据角色已分开。

前提：2026-09-01 的后续用户裁决确实触发并取代了人写文档第 39 行的阶段限制。它支撑“D-5 无需再决策、且覆盖 Responses direct”的结论。若该前提为假，D-5 仍然是 Anthropic direct selector 的 blocker，但把 Responses direct continuation 纳入同一完成边界会越权，必须回用户裁范围。当前 living Spec §2.8、§8、v15 修订记录与 deferred D-5/D-7 四处一致记录该裁决，且旧句自带“目前／未来补全”的开放时态，因此证据足以据以行动。

前提：`claude-sonnet-5` 不能走 Responses upstream 的测量仍适用于当前 provider/model catalog。它只支撑“Anthropic direct 是 Claude 模型可达性的关键 route”，不再支撑“项目主产品路径”。若为假，D-5 仍阻塞用户已裁的所有直连根修，但这一项优先权会减弱；实施前可用现有 catalog 或 real canary 复核，不必用它决定是否修。

前提：现有 selector 是唯一让 streaming 组合不可达的生产门。它支撑“直接接线必现探针故障”的结论。若为假，可能还有更早的门或另一条 writer 已经兜底，修复边界会变化。当前 `carries_upstream_natively()` 对 Anthropic 明确返回 false，`framer_for()`／`assembler_for()` 都以它为单一选择点，真实入口只经这两个 factory 构造，定向全仓引用检索没有第二套 production selector；足以据以设计，实施时仍应由真实 route 集成测试确认。
