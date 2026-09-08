报告未落盘：依照本任务“不得改文件”的只读约束，未创建 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-prerequisite-design-review-grok.md`。以下为完整评审正文。

# Task 3B architecture review

## 评审范围

- 唯一 design 对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-prerequisite-design-gpt-high.md`
- Behavior authority：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`
- Implementation authority：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`
- Brief review：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-brief-review-claude.md`
- Fixed source：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`
- 首尾复算均匹配用户给定的四个 SHA-256；stacked source HEAD 首尾均为 `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`，末次 tracked status 为空。
- 额外读取的当前 SDD tracker 快照：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md`，读取时 SHA-256 为 `64886c47350e9191d309a8a61a1c4c9a7704472c2dea4d7345694c3a73a940ce`；它不是用户固定输入，只支撑下述限定时点的 tracker 观察。

## 总体 verdict

**NEEDS FIXES**

- Blocker：1
- Major：3
- Minor：1
- findings_total：5

存在 Blocker／Major，不允许把本 design 写回 living authority，也不应派 Task 3B implementer。

## Blocker

### T4A-AR-01：capacity epoch rollover 尚未形成可执行的跨 identity transaction state machine

- `severity`：Blocker
- `primary_location`：design `§5.3:378-390`、`§4.3:314-357`
- `related_locations`：design `§8:469-525`；fixed source `types.py:893-924`、`:936-944`、`:1016-1063`；`learning_store.py:1972-2205`、`:2311-2553`、`:4060-4164`
- `classification`：必须修改 Spec behavior、epoch/event carrier及store transaction mechanics；不只是internal naming。

**具体反例**

Global checkpoint cap已有32,768条active rows。当前正在为identity A、epoch 7、ProfileKey P提交一个新checkpoint，插入后超限1条。design允许global planner按“retention value”选择另一个identity B作为victim并将B rollover。

现有合同和design无法完成这个事务：

1. `TokenLearningPolicy`只看A的single-identity `LearningSnapshot`，无法看到全库checkpoint rows，也无法选择B；global victim只能由读取`ValidatedPersistentState`的store-private planner选择。design却同时把“capacity epoch transition的领域policy”交给Task 4B。
2. 当前`LearningUpdate`只有当前sample的一份`TokenLearningObservation`和可选`DriftObservation`；后者只能描述当前sample identity的`exact`／`profile` drift。它不能同时记录A的sample commit和B的capacity rollover。
3. 若victim恰为A，policy生成的sample／record／checkpoint都基于epoch 7。事后把当前sample改放epoch 8，会使record仍引用epoch 7的prequential snapshot；保持sample在epoch 7则意味着rollover只能对随后请求生效。design的“当前或后续sample”没有选择唯一语义。
4. `prefix-checkpoint-capacity`不是现有三个`DriftReasonCode`中的任何一个，也不是统计漂移；把它塞进`DriftObservation`会破坏Task 4C的owner和现有`kind in {"exact","profile"}`约束。
5. Global victim order只写了“tie至少包含……”，不是total order；两个process面对相同state仍可由实现自行选择不同victim。
6. Rollover后哪些old-active checkpoint rows在同一事务删除、如何保证至少释放一条、何时停止、A和B分别如何递增revision、如何刷新或删除两个cache，都没有形成一个完整步骤序列。

**最小修法**

1. 保留capacity rollover路线，但新增独立于`DriftObservation`的closed `CapacityEpochTransition`，或建立通用`EpochTransition` union并让statistical drift与capacity各有独立reason／metadata。不要把capacity伪装成profile drift。
2. `TokenLearningPolicy`只返回当前ProfileKey的checkpoint logical update；store-private pure retention planner基于完整transaction-fresh persistent state选择capacity victim并产生零或一个rollover action。
3. 唯一确定current-sample语义。最小改动方案是：当前sample、record和checkpoint仍按prequential old epoch提交；若当前identity被rollover，旧epoch在同事务末变inactive，新epoch从**下一次**prediction开始。不要事后重标当前sample；若要让当前sample进入new epoch，则必须明确先rollover、重新投影empty snapshot并重跑整个pure transition。
4. 同一事务允许写sample commit event和独立capacity transition event；victim为别的identity时两者不得合并。
5. 写出完整global victim tuple、inactive cleanup tuple和方向；不能使用“至少包含”。
6. 明确起始state已在cap内、一次transaction最多新增一row、rollover victim至少有一条active checkpoint、同事务删除足量old-epoch rows，因此最多执行一次rollover即可恢复上限。
7. `affected_identity_ids`必须包含当前sample identity和victim identity；每个identity revision各递增一次、global revision递增一次，rollback撤销sample、checkpoint、rollover、events和revision，commit后两个cache都按新active epoch刷新或失效。

**路线处置**

- 采纳：显式capacity epoch rollover，但前提是补齐上述状态机。
- 否决：把capacity塞进`DriftObservation`；让single-identity policy选择global victim；post-hoc重标当前sample epoch；以非total-order文字留给实现者。
- design所称“唯一方案”过强。确定性淘汰仍处于`ELIGIBLE`模式的partial windows不会false-recover，只会延迟demotion；cap满时拒收新的checkpoint update也不会恢复已有demoted profile。不过两者分别削弱latest-16合同和持续学习，因此我仍推荐rollover，而不是把这些替代项说成数学上不存在。

## Major

### T4A-AR-02：store-owned post-transition facts与policy update carrier没有闭合

- `severity`：Major
- `primary_location`：design `§3.1:195-219`、`§4.1～§4.3:247-357`
- `related_locations`：fixed source `types.py:773-794`、`:833-889`、`:1016-1063`；`learning_store.py:4470-4523`、`:1972-2205`
- `classification`：internal interface与transaction ownership；由于Spec已规范schema／revision，也需同步相应条款。

**具体反例**

`PrefixEligibilityCheckpoint.state_revision`和`updated_order`被定义为post-transition identity／global order，但policy运行时只看pre-transition `LearningSnapshot`，拿不到post-transition global revision。与此同时，design要求store在执行revision update前验证policy返回的checkpoint revision。

因此implementer会被迫在三种错误路线中任选其一：

- policy伪造一个未来global order；
- 用0／`None`占位后把不合法的checkpoint送入DTO／codec；
- store在policy已经构造完整persistent DTO后偷偷替换字段，导致logical policy state与persistent state没有明确边界。

同一问题也存在于`StoredSample.committed_order`：pending sample必须为`None`，但当前store在`_run_and_prepare_transition()`中立即编码`update.sample`，而post-transition order到后面才确定。

此外，design只列出了`KeepPrefixCheckpoint | ReplacePrefixCheckpoint | DeleteRecoveredPrefixCheckpoint`的名字，没有定义payload、expected-old-state或store stamping责任。Task 3B又明确不实现demotion policy。若简单给`LearningUpdate`增加默认`None`，Task 4B漏接policy时会静默永远no-op；若增加无默认required字段，现有constructor和Task 4A／4B-P各阶段该传什么又没有说明。

**最小修法**

1. 分开logical command与persisted DTO。Policy返回的`ReplacePrefixCheckpoint`只携mode、bounded evidence、ProfileKey和可选`expected_prior_state_revision`；不携store-owned新revision／global order。
2. Store在计算`next_global_revision`及affected identities后统一stamp：
   - `StoredSample.committed_order`
   - 新checkpoint的`state_revision`
   - 新checkpoint的`updated_order`
3. 将encoding移到stamp之后；public `LearningSnapshot`拒绝任何`committed_order is None`或未stamp checkpoint。
4. 增加显式`NoPrefixCheckpointChange` union member，并让`LearningUpdate`字段成为required。Task 3B synthetic store tests、Task 4A和Task 4B-P都必须显式传no-change；Task 4B开始产生replace／delete。不要保留可让遗漏接线静默通过的永久`None`默认。
5. 明确`Keep`究竟表示“无状态变化”还是带optimistic predecessor的CAS；不要同时承担两种意思。
6. Task 3B用synthetic commands验证UPSERT／DELETE／rollback／restart即可，不需要提前实现16／8 policy。

**路线处置**

- 采纳：`committed_order = post-transition global_revision`及typed checkpoint command。
- 否决：policy填写store-owned revision；persistent DTO携placeholder；永久optional default让Task 4B wiring遗漏变成合法no-op。

### T4A-AR-03：`InputItemContribution`没有形成exact conservation，错误item／nested attribution仍可通过所有invariants

- `severity`：Major
- `primary_location`：design `§1.1～§1.4:71-153`
- `related_locations`：fixed source `features.py:382-613`、`:616-641`；`types.py:166-204`；`learning_store.py:4541-4587`
- `classification`：per-item behavior representation、DTO invariant与transcription tests；必须改Spec及codec，不是单纯命名。

**具体反例**

假设whole request的`known_tokens=16`，其中top-level instructions及其framing实际贡献8；唯一message item含一个零文本structured part，正确item贡献为item framing 4＋nested framing 4＝8。

错误producer写成：

- `known_tokens=12`
- `item_framing_tokens=4`
- `nested_framing_tokens=8`

Design的全部不变量仍通过：

- nested framing是4的倍数；
- `known - item - nested = 0`非负；
- `sum(item.known_tokens)=12 <= EstimateFeatures.known_tokens=16`；
- prefix tuple长度正确。

SQLite round-trip也会接受它，但append suffix会多加4。反向漏掉一个function-output part framing同样可把item写成4并通过`sum <= whole`。因此字段当前能关闭“旧item visual为None、append独立image item visual=6”的具体反例，却不能精确关闭item／nested重复或遗漏这一族缺陷。

**最小修法**

1. 把贡献拆为非重叠量，例如`visible_tokens`、`item_framing_tokens`、`nested_framing_tokens`、visual和prior，并让`known_tokens`成为derived property；或者至少强制`item.known_tokens == visible + item_framing + nested_framing`。
2. 新增一个明确的`fixed_context_contribution`，使：
   - `EstimateFeatures.known_tokens == context.known_tokens + Σ item.known_tokens`
   - whole prior residual等于context residual＋item residual总和
   - whole visual继续按design定义的all-or-none规则从item tuple唯一重建
3. 若保留whole-request visual all-or-none，Spec必须明确：full cold-start仍在任一item缺metadata时把whole visual term取0；prefix suffix则只对appended item tuple逐项取known值。这是有意的method-dependent information gain，不是“兼容aggregate”一句话能替代的行为说明。
4. Direct tests必须分别覆盖：
   - raw string item
   - `null`／number等non-object item
   - message structured parts
   - reasoning summary parts
   - scalar及list形式的function output
   - function-output内text＋media
   - item／nested framing恰好一次
   - 四个visual transition cases
5. 对codec逐字段改单变量，证明少／多一个nested framing、把function output算到top-level、改变tuple位置都会判红。

**路线处置**

- 采纳：prefix-aligned per-item representation及按anchor count切片；它确实关闭原始`None→None`独立append反例。
- 否决：whole-request subtraction、向predictor重传raw items、重复feature classifier。
- 有条件保留：whole visual aggregate all-or-none，但必须把full cold与suffix semantics写成明确行为并增加exact conservation；不能让aggregate与item tuple成为两份可独立漂移的事实。

### T4A-AR-04：新增Task 4B-P没有闭合到真实task tracker与依赖图

- `severity`：Major
- `primary_location`：design `§8:465-529`、`Open blockers:630-640`
- `related_locations`：当前 `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md:13-23`、`:51-55`；`status.md`
- `classification`：plan／status／tracker sequencing；不改变public behavior。

**具体反例**

Design要求顺序为：

`Task 3B → Task 4A → Task 4B-P → Task 4B → Task 4C`

但当前SDD progress table仍是：

`Task 3B → Task 4A → Task 4B → Task 4C`

Design的authority handoff只要求同步Spec、plan和transcription map，没有点名`status.md`与SDD `progress.md`。如果authority writer只照这份清单做，controller会在Task 4A后合法地按旧tracker派Task 4B。此时demotion以只有deterministic prefix的method champion开始；随后加入learned prefix variants会改变历史champion语义，正是design自己禁止的顺序。

**最小修法**

1. 同一authority change更新：
   - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`
   - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/status.md`
   - `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md`
2. Task table及overlap scan明确写成`3B → 4A → 4B-P → 4B → 4C → 5`。
3. 明确各阶段“all available”分母：
   - 4A只可能保存exact、prefix deterministic、cold；
   - 4B-P加入prefix additive／multiplicative，即使exact selected也要构造；
   - 4B再加入profile variants及eligibility；
   - 历史record不被事后补写不存在于其prequential时点的candidate。
4. Task 4B-P需要revision-bound的ephemeral prefix-pair index或明确的bounded scan算法，以避免对4,096 samples直接做无说明的`O(n²)` base查找；不必新增durable tracker，但应明确index owner与snapshot revision invalidation。
5. 原Task 4A brief必须标为superseded并分别生成3B／revised-4A／4B-P的实施brief，不能继续让implementer引用旧owned-file和行为分母。

**路线处置**

- 采纳：独立Task 4B-P；它让learned prefix champion在demotion之前稳定，语义切片合理。
- 否决：只改plan、不改status／progress；4B先于4B-P；事后回填旧PredictionRecord。
- 无需新增durable learned-prefix tracker；history pair可从sample／record重建，但应有revision-bound的计算索引或复杂度说明。

## Minor

### T4A-AR-05：ProfileKey的logical equality与SQLite唯一键／hash collision处置未唯一确定

- `severity`：Minor
- `primary_location`：design `§4.1:247-289`
- `related_locations`：fixed source `types.py:103-130`；`learning_store.py:4541-4561`、`:5084-5129`
- `classification`：internal schema与codec；由于V1 manifest规范化，仍须写入schema authority。

Design正确要求lookup decode完整`ProfileKey`并比较对象，不能只信SHA-256。但是它没有说明checkpoint table的PK／unique key究竟只含`profile_key_hash`，还是同时包含canonical JSON。

若只以hash为唯一键，两个不同ProfileKey发生hash collision时不能同时表达；仅在读取后比较对象只会把第二个更新变成冲突或误报corruption，并没有实现“逻辑key严格为完整ProfileKey”。

**最小修法**

- 明确canonical `profile_key_json`的BINARY equality才是identity；hash只用于索引／lookup narrowing。
- 选择并固定以下之一：
  - PK／unique包含canonical JSON，hash为普通索引；
  - hash冲突时typed fail-closed、row和revision不变，并把这一限制写进contract。
- 增加same-hash／different-JSON的test-only injected digest regression；不需要尝试真实SHA-256碰撞。

**路线处置**

- 采纳：canonical JSON decode后对象 equality。
- 否决：hash-only identity或发现hash相同后静默覆盖旧row。

## 已核对且可沿用的设计结论

以下部分未发现Blocker／Major，可作为下一版design的保留基础：

1. `committed_order = sample transaction的post-transition global_revision`在“一次sample transaction只插入一个sample”的前提下足以表达prequential availability。`BEGIN IMMEDIATE`序列化跨process writers；anchor-use／event／prune造成的revision gaps不影响严格小于关系；duplicate不产生sample order；same timestamp不再承担happens-before。Future batch必须扩成`(global_revision, batch_ordinal)`，design已正确限定。
2. Historical base不要求与longer同`ProfileKey`是正确的；否则首次append image／function call／unknown kind会把合法prefix base排除。Current query与historical longer必须同exact `ProfileKey`，base由prefix identity和commit availability约束。
3. 16／8 checkpoint窗口在统计上是充分状态：eligible保留latest 16 triply-paired APE；demoted保留latest 8 recovery evidence；触发demotion的第16条清空后不进入recovery；actual 0、缺prefix或缺当前模式所需facts均no-op；ProfileKey隔离正确。Candidate key不是计算median的最小字段，但保留点时champion provenance有合理价值。
4. 完整`suffix_baseline_delta = known + visual_or_zero + released prior`与deterministic candidate口径一致；literal known-only会把visual／prior重新学成residual。Current baseline为0时，历史ratio支持仍使multiplicative candidate存在，值为0且tie由deterministic保留，设计一致。
5. Exact-selected与candidate availability分离正确。最终系统中exact global selected时仍应保留strictly shorter prefix及profile challengers；request decision仍只携EXACT intent。
6. Candidate canonical order、method champion enum order及`sample_count`定义一致：
   - exact为实际median source数1～5；
   - deterministic prefix为1；
   - learned prefix／profile为实际训练evidence数；
   - cold为0。
7. Newest-31从record＋actual重建、`LearningSnapshot.evaluations=()`负控、63／31反转fixture、latest-8 recovery与ProfileKey交叉污染控制均有判别力。
8. Compact prefix digest array的52,797-byte计算属实。按现有compact JSON separators复算，788个64-hex digests为52,797 bytes；代表性的788条`[4,4,0,0,0.0]` contribution array为11,033 bytes，两列分别低于65,536-byte单字段上限。它证明该代表性V1 shape可行，不证明任意无界整数值都能过cap；design要求实现时跑exact 788-item round-trip是必要的。
9. V1尚未发布时同步改V1、发现任何外部V1事实即停止并改用新version＋migration，这一前提与当前plan／fixed source阶段一致。Action IDs、DDL digest、manifest、private-state oracle必须随3B同改。

## Authority写回所需最小顺序

1. 先修本报告T4A-AR-01～05，尤其先决定capacity rollover的current-sample epoch和multi-identity event模型。
2. 再修改living Spec及revision record；行为项与internal schema项分开标识，但两者都进入现有normative authority。
3. 同步plan、status、SDD progress tracker、transcription map、fixed action IDs与相关acceptance rows。
4. 对新Spec／plan做独立review，达到0 Blocker／0 Major。
5. 再派Task 3B implementer；3B通过独立source review后才启动收窄后的Task 4A。
6. 按`Task 4A → Task 4B-P → Task 4B → Task 4C`推进，不得跳过4B-P。

## 搜索面与证据边界

完整读取了固定SHA的design、Spec、plan及brief review，并读取fixed source中相关DTO、feature analyzer、schema、sample codec、snapshot projection、apply transaction、revision、prune、epoch、event和`LearningUpdate`实现。CodeGraph确认该job checkout没有索引，随后使用限定`rg`和绝对路径Read。执行了两个纯内存compact-JSON长度探针。未运行broad tests、未调用真实upstream、未修改任何文件、未创建commit或控制任何服务。

本结论足以阻止authority写回，并足以指导下一轮design修复；它不证明任何尚未实现的Task 3B source质量或真实provider计费准确率。

本轮已到评审边界并完成收口判断：没有本会话创建的仓库文件、提交、分支、worktree或后台进程需要清理；所有发现均保持open并交上级会话处置。

# 最终结论

**NEEDS FIXES**