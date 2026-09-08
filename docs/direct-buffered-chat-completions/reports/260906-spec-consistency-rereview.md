# Direct buffered Chat Completions 修订 candidate 规范一致性复评

日期：2026-09-06。

评审对象：初审报告 [`260906-spec-consistency-review.md`](260906-spec-consistency-review.md) 之后的同一书面设计 candidate，以及 [`260906-review-disposition.md`](260906-review-disposition.md) 所列修订。本文是时点复评报告，不替代 living Spec。

## 结论

**当前 candidate 达到 0 blocker，但尚未达到 0 major。** 初审的 2 blocker／6 major／2 minor中，B-2、M-1、M-2、M-4、M-5、M-6、m-1、m-2已实质闭合；B-1与M-3主体修法成立，但各剩一处 major级规范空洞。另发现1项minor级capability类型转写不一致。复评计数为 **0 blocker、2 major、1 minor**，因此**不能形成0 blocker／0 major共识**。

新增用户裁决已被准确记录为 `decisions.md` D-9～D-11：标准multi-choice SSE→JSON聚合；首个合法 `[DONE]` 后冻结semantic state并继续收raw tail；post-`[DONE]` client deadline提交完整body并记录tail截断。修订没有重开Chat block-level incremental delivery、Chat continuation或新的Chat streaming proxy error frame，也没有把内容处理塞回provider。

## 初审finding逐项复核

| 初审finding | 状态 | 复评结论 |
|---|---|---|
| B-1 mode-adapted Chat JSON没有规范性聚合合同 | **OPEN，降为major残余** | §9.3.1已增加multi-choice字段表、`unassemblable`、identity／choice／tool／usage规则，测试不再代替Spec；但“其它已知top-level snapshot字段”仍没有封闭定义，它与unknown字段使用不同冲突规则，见R-1 |
| B-2 post-`[DONE]` ending优先级未闭合 | **CLOSED** | direct-passthrough §5.4按 `done_seen` 两层覆盖EOF、tear、idle、attempt/client deadline、cap、后续semantic frame、本地tail failure与cancellation；error-envelope §8／§10.2与Design §7.2／§9同步，D-10／D-11给出用户来源 |
| M-1 replacement observation切换时点矛盾 | **CLOSED** | direct-passthrough §5.4／§10与Design §10均分开attempt draft、candidate、request projection；replacement建立后才切candidate，final action才promotion，replacement失败时旧fallback snapshot保留 |
| M-2 capability代数不完整 | **CLOSED，带minor转写项** | response modes非空闭集、四种client／endpoint mode组合、unsupported streaming本地400、absent-default与显式值优先均已闭合；Xingchen descriptor已写入capability。Design的 `bool | None`仍宽于Spec的 `true | None`，见n-1，但不再构成major行为分叉 |
| M-3流内error识别／冲突／non-stream carrier不唯一 | **OPEN，major残余** | 三种carrier、code/type一致命中、unknown／malformed不retry、429／502与raw frame offset均已定义；但error-envelope §8漏掉一类已声明支持的parsed object carrier，见R-2 |
| M-4 Chat observation与TUI schema不完整 | **CLOSED** | TUI Spec新增独立 `chat` 槽、choice／tool结构、absent／null／unreadable、issues、unknown保存、无名调用 `?`、multi-choice与tail精确拼法；Design与direct Spec只引用该authority |
| M-5 client-leg README仍把所有Responses写成旧framer | **CLOSED** | README §二按direct／translated分行，§三明确仅描述translated `ResponsesFramer`；direct path改为 `PassthroughFramer`＋默认原生id／显式reshape |
| M-6 retry status的499陈述过期 | **CLOSED** | status开头已按当前人控文档、`RETRYABLE_STATUSES`与可达提交 `39274d7`改为current事实，并区分HTTP 499与本地client cancellation |
| m-1用户亲笔文字与Spec推导混写 | **CLOSED** | decisions §20～27把人控明示与comment／Chat commit frontier推导分开，D-9～D-11另列为用户新增裁决 |
| m-2额外用户复核被写成产品／项目门禁 | **CLOSED** | status把它表述为当前会话brainstorming步骤，并明确“不是新增产品审批门”；当前技术阻塞只剩独立复评共识 |

## Open major

### R-1　B-1残余：`其它已知top-level snapshot字段`不是封闭集合，仍会让同一输入在success与502之间摇摆

**位置**：`direct-passthrough/spec.md` §9.3.1 第792行与第801行；同节第786行“本表才是行为权威”。

**事实**：字段表把 `service_tier`、`system_fingerprint`、`moderation`“及其它已知top-level snapshot字段”定义为last-explicit-wins；unknown top-level字段则只允许单次或重复相同值，冲突时 `unassemblable`。但是“其它已知”没有枚举、没有引用一个带版本的外部schema，也没有机械判据。对同一路径上两个不同值的字段 `x`，若实现者或SDK把它视为known snapshot，adaptation成功并取后值；若视为unknown，则返回502。§9.3.1同时规定SDK accumulator只可作实现基础、升级不得静默改变输出，所以不能把“known”默认为SDK当前类型集合。

**影响**：这是客户端可见的成功／失败分叉，且会随依赖版本或实现者认知漂移；因此B-1尚未完全闭合，但已不再是“整张聚合合同缺失”的blocker。

**精确修订建议**：在第792行只列出逐字枚举的字段；所有未枚举字段一律落第801行。若确有一组字段共享last-wins语义，则用一个当前Spec内的显式集合定义并在修订记录维护，不能写“其它已知”。同时把unknown delta字段“对应最终object”的落点明确为其原JSON层级投影，避免SDK helper字段被误当known输出。

**是否需要用户裁决**：不需要。用户已经裁定Spec字段表是authority；把集合封闭是兑现该裁决，不改变其方向。

**证据权重**：强到足以保留major。两行给同一未枚举字段的冲突值两种相反结局，文本自身不能选择。

### R-2　M-3残余：`event:error`的parsed flat object若没有`type:"error"`，error-envelope没有定义最终body

**位置**：`direct-passthrough/spec.md` §5.4 第336行；`direct-buffered-chat-completions/design.md` §5.1／§8；`error-envelope/spec.md` §8 第383行与§10.2第427行。

**事实**：Direct Spec与Design都把SSE event名为 `error` 单独认作明确carrier，不要求payload再带顶层 `error`或 `type:"error"`；其parsed object按flat carrier读取顶层code／type。因此 `event:error` + `{"code":"server_error","message":"…"}` 是明确、可重试的合法输入形态。预算耗尽后，error-envelope §8只定义三类non-stream body：含top-level `error`的object原值保留；flat `type:"error"` object包进标准envelope；non-object或不可解析payload进入proxy envelope。上述parsed object既不含top-level `error`、也没有 `type:"error"`，又不是non-object／unparseable，最终JSON无归属。§10.2用“flat error”概括不能补上§8这张精确carrier表的缺格。

**影响**：同一个被reader明确识别并分类的error，在retry预算耗尽时可能被实现为原object、标准 `{"error":…}`、proxy envelope或异常逃逸；M-3要求的non-stream carrier仍非唯一。

**精确修订建议**：在error-envelope §8补一行“由SSE event名确认的error carrier，payload是object但不含top-level `error`”：将整个parsed object作为标准OpenAI envelope的 `error` 值，保留原字段；status仍按已归一化rate-limit为429、其它为502。若payload同时有非carrier普通字段，也一并保留在该raw `error`值，不由writer补写或覆盖type／code。§10.2把“flat error”改成回指这条完整定义。

**是否需要用户裁决**：不需要。这只是把已经明确支持的第三种carrier接到既定“保留原对象、不得覆盖字段”原则上；若团队想选择别的body形状，才需要把产品分叉交用户。

**证据权重**：强到足以保留major。可构造输入逐字满足reader合同，却不命中error-envelope的任一body分支。

## New minor

### n-1　Capability default类型在Design与行为Spec之间仍有一位宽度差

**位置**：`direct-buffered-chat-completions/design.md` §4.1第40行；`direct-passthrough/spec.md` §9.3第782行；`xingchen/spec.md` §4／§5。

Design把两个default字段写成 `bool | None`，行为Spec只允许 `true | None`，因为显式client `false`是payload值而不是descriptor default。当前CodeBuddy／Xingchen／GitHub三份profile只使用true或None，因此没有现行路径行为分叉；但照Design定义实现会让descriptor中的false通过类型检查，而Spec未定义它是“补false”、等同None还是validation error。

**建议**：把Design改成 `Literal[True] | None`／等价枚举，或在Spec显式定义false并说明其必要性。不要静默把false当None，因为两者会重新制造“缺席与明确值同形”。

## 修订组合检查

### 已形成一致闭环

1. **`[DONE]`语义与tail**：D-3、D-10、D-11 → direct-passthrough §5.4 → error-envelope §8／§10.2 → TUI `tail_ending` → Design验证矩阵，链路一致。首个 `[DONE]`冻结语义，tail ending不retry；client cancellation／downstream write failure仍无写通道。
2. **Candidate observation**：旧candidate保留到replacement response建立，最终实际carrier决定projection；TUI测试包含fallback candidate被current attempt覆盖的负控。
3. **Retry owner**：collector只读单attempt，pre-success只有DirectDriver消费ledger，post-header只有delivery runner消费；没有双重预算owner。
4. **Capability ownership**：provider只声明immutable per-model endpoint数据并执行最终payload／mode；pipeline解释mode与defaults；Xingchen签名仍覆盖pipeline最终bytes。
5. **Translated边界**：共享纯event reader不暗改translated Chat→Anthropic multi-choice projection；该现有缺口作为D-2留在本主题deferred，未被TUI“最小choice”presentation规则偷裁。
6. **最终carrier**：pre-`[DONE]`不可恢复时仍为final candidate partial+naked-close；没有新增Chat streaming proxy error frame。Mode-adapted non-stream在headers提交前使用JSON carrier，不混入裸断例外。

### 没有发现的新 blocker

Post-`[DONE]` cap与同chunk边界在Design §9已补充：若 `[DONE]` frame本身跨cap，仍按pre-terminal failure且不得越界；只有terminal frame已能完整纳入、后续tail导致越界时才按post-terminal成功截尾。这足以消除初审B-2所担心的cap优先级冲突。

## 否决建议及原因

1. **否决“把第792行的其它已知字段交给OpenAI SDK类型自动决定”。** 同节已裁定Spec字段表才是authority，SDK升级不得静默改输出；动态known集合会直接违反这两句。
2. **否决“把未覆盖的 `event:error` object当malformed”。** Reader合同明确它是parsed flat carrier并能从top-level code/type分类；把它降成malformed会丢掉已读出的rate-limit／server-error事实。
3. **否决“为拿到0 major把R-1／R-2降成minor”。** 两处都改变客户端可见的success／502或最终JSON形状，不是措辞或导航问题。
4. **否决重开Chat block-level incremental delivery、Chat continuation或新的Chat streaming proxy error frame。** 三项仍有明确用户推迟裁决，当前terminal-only replay不依赖它们。
5. **否决顺手修translated Chat→Anthropic multi-choice projection。** 问题成立但需要另行决定单choice选择、拒绝multi-choice或其它投影；当前deferred D-2是正确归属。
6. **否决让provider保留aggregation、按provider名称分支或把所有Chat target强制streaming。** 这些路线仍与D-6／D-8及closed capability matrix冲突。
7. **否决运行真实CodeBuddy P6或Xingchen canary作为本轮文档闭合条件。** D-7明确选择暂不实测；当前两个open major都是Spec内部可闭合的定义问题，不需要外部调用。
8. **否决新增proof gate、schema registry或验证治理层。** 两处修订都是局部闭集／carrier表补全，现有living Spec和针对性测试足够。

除上述八项外，本轮没有其他审查后否决的建议。

## 达成0 blocker／0 major共识所需的最小修订

1. `direct-passthrough/spec.md` §9.3.1删除未封闭的“其它已知top-level snapshot字段”，显式枚举last-wins集合，其余全部走unknown规则。
2. `error-envelope/spec.md` §8补齐event-name识别的parsed flat object carrier，并让§10.2精确回指。
3. 顺手把Design capability default类型收窄为 `Literal[True] | None`；该项不阻挡下一轮0 blocker／0 major复评。

完成前两项并同步修订记录后，无需重开用户产品裁决；对发生变化的两个小节做一次定向独立复评即可。
