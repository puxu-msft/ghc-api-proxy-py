# Task 3B living-authority 独立评审

未创建请求的报告文件 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-authority-review-gpt-high.md`：当前 leaf harness 明确禁止写入评审报告文件。以下为完整正文，供上级会话原样转录。

## 评审范围

- Behavior authority：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`，SHA-256 `8405215aa6582728961e9066064cdb59081e519c43bf228267eb6ac21c1086ec`。
- Implementation authority：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`，SHA-256 `030fa1bd1be40dfb12b8bd07ef20acfeb2c752bff809bc12d9fc93ea6311`。
- Topic入口：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/README.md`，SHA-256 `774364f7ea641c385bca1efefb0507554bdef49da670f0b49fe40342e1cb725b`。
- Dotdev commit：`7119473dc3d28a97dd8678e5a070651f418c4508`。
- Fixed source：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`，HEAD `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`。
- Design inputs：用户指定的Task 4A brief review、prerequisite design及review、Task 3B amendments 1～3及各轮review。
- 相邻状态面：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/status.md`、SDD `progress.md`、现存Task 4A brief，以及TaskList `#13／#14／#15／#16／#26／#27`。
- 首尾两次复算均匹配以上三个文件SHA、dotdev commit和fixed source HEAD，评审期间未检测到固定输入移动。

## 总体 verdict

**NEEDS FIXES**

- Blocker：0
- Major：4
- Minor：1
- findings_total：5

存在Major，**不允许启动Task 3B source implementation**。

## Major

### T3B-AUTH-01：Plan仍让pure policy产出最终observation，与store-owned checkpoint outcome互相矛盾

- `severity`：Major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:129-143`，尤其`:134`
- `related_locations`：Plan `:381-395`；Spec `:370-376`、`:473-485`；fixed source `types.py:1016-1063`、`learning_store.py:4470-4522`
- `problem`：Plan上层接口仍规定`TokenLearningPolicy`返回`LearningUpdate`与`TokenLearningObservation`，但同一Plan及Spec又规定store必须在stamping、capacity planning、prune和最终durable state确定后产生required `PrefixCheckpointStoreOutcome`。这两个owner不能同时成立。Fixed source目前也确实把一个预先构造的committed observation放在`LearningUpdate.observation`中，因此这不是无害概述。
- `counterexample`：Policy针对missing-row Replace生成update时，全库可能处于三种状态：未超cap得到`Applied`；global cap满且current prior rows为0得到`CapacityRejected`；prior rows大于0得到`CapacityRolledOver`。Policy只看single-identity snapshot，无法知道最终分支。它若提前填`NoChange`或其它placeholder便违反required actual outcome；store若事后覆盖policy返回的observation，则Plan仍保留两个事实owner，并使pre-store DTO validation没有唯一意义。
- `impact`：Task 3B implementer无法同时遵守Plan的policy接口与Spec的store outcome authority，最可能留下optional placeholder、双重构造或事后静默改写。
- `minimum_fix`：把Plan上层architecture和Task 3B interface改为唯一模型：pure policy的`LearningUpdate`只含pending sample、record／evaluations、required logical checkpoint command及可选drift，不含最终`TokenLearningObservation`或store outcome；store在stamp、capacity、prune和confirmed COMMIT边界构造最终observation。明确删除fixed source现有`LearningUpdate.observation`，或改成名称与类型均不同、不能冒充durable observation的logical draft。增加direct control，证明policy output不能携store-owned outcome／revision。
- `conclusion_strength`：已确认。Spec与Plan直接冲突，fixed source展示了必须迁移的现有接口。

### T3B-AUTH-02：当前sample的checkpoint evidence无法在policy阶段取得`committed_order`

- `severity`：Major
- `primary_location`：Spec `:315-319`、`:370-376`
- `related_locations`：Spec `:264-268`、`:473-478`；Plan `:383-391`、`:447-453`；prerequisite design `:264-276`；amendment 1 `:108-152`、`:226-236`
- `problem`：Persistent `PrefixChampionErrorTriple`以positive `committed_order`排序；Replace logical command却直接携完整`evidence` tuple。Policy运行时pending `StoredSample.committed_order`必须为`None`，而Plan的`advance_prefix_checkpoint(record, actual, checkpoint)`也没有store-assigned order输入。Authority只要求store stamp sample、checkpoint `state_revision`和`updated_order`，没有规定如何stamp当前新增evidence自身的order。
- `counterexample`：Task 4B处理第16条eligible evidence。Policy必须返回包含这条current triple的Replace command，才能判断并持久化demotion；但此时它既不能填写positive global order，也不能合法encode `None`。猜测`next_global_revision`违反store-owned stamp边界；用0或sentinel则使logical／persistent DTO边界和strict ordering未定义。
- `impact`：Task 3B可以用手写历史order做synthetic store test，却会交付一个Task 4B真实policy无法构造的command carrier；问题会被推迟到后续source slice才暴露。
- `minimum_fix`：分离logical和persistent evidence。可采用orderless `PendingPrefixChampionErrorTriple`，或只允许logical evidence tuple最后一项的`committed_order=None`；store以`next_global_revision`stamp该唯一pending tail，再构造全部positive、strictly increasing的persistent checkpoint。必须拒绝多于一个pending entry、非tail pending或提前encode，并在A42／transcription中增加“policy entry时无order，store stamp后current evidence order等于sample committed order”的control。
- `conclusion_strength`：已确认。该值在指定调用顺序中尚不存在，而authority没有合法占位或stamp规则。

### T3B-AUTH-03：状态投影与现存SDD brief没有完整同步新任务顺序

- `severity`：Major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/status.md:108-120`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md:79-138`、`:174-198`；SDD `progress.md:19-24`、`:52-56`；Plan `:366-473`；TaskList `13.json`、`14.json`、`15.json`、`16.json`、`26.json`、`27.json`
- `problem`：Plan、SDD progress和TaskList已经正确表达`3B → 4A → 4B-P → 4B → 4C → 5`，但作为唯一volatile projection的status任务表完全没有Task 4B-P行，并仍写Task 4B“等待Task 4A”。同时现存Task 4A brief没有`SUPERSEDED`标记，仍要求exact miss才构造prefix、whole-request visual subtraction、timestamp availability、Task 4A learned variants及retained-record eligibility replay，逐项重现已被本轮authority否决的旧设计。
- `counterexample`：Task 3B完成后，调度者若按status任务表或现存Task 4A brief继续，会让Task 4B直接跟在4A后，或让Task 4A重新实现已明确移到4B-P／4B的learned variants与eligibility replay。TaskList虽然以`#27`阻塞`#14`，但这不能纠正brief向`#13` implementer发出的错误实现要求。
- `impact`：核心Plan顺序本身正确，但执行入口仍能合法地把旧任务分母交给下一棒；这正是原architecture review `T4A-AR-04`要求关闭的失效面。
- `minimum_fix`：在status任务投影新增Task 4B-P，并把Task 4B依赖改为Task 4B-P。给现存`task-4A-brief.md`顶部加不可错过的`SUPERSEDED`标记，指向current Spec／Plan和新的切片；Task 3B review通过后分别生成Task 3B implementation brief及收窄后的Task 4A brief，Task 4B-P brief在其启动前生成。保持现有TaskList `#13 → #27 → #14 → #15 → #16`边不变。
- `conclusion_strength`：已确认。三个正确调度源与两个陈旧执行入口直接对照即可复现。

### T3B-AUTH-04：A40～A45不能判否known-only learned baseline与current-zero multiplicative gate

- `severity`：Major
- `primary_location`：Spec `:647-652`
- `related_locations`：Spec `:307-313`；Plan `:432-436`；Task 4A brief review `T4A-BR-04`
- `problem`：Normative behavior已正确规定historical `suffix_baseline_delta`包含known＋visual-or-zero＋prior，并规定current baseline为0时历史支持的multiplicative candidate仍存在。但A40只验证deterministic per-item visual suffix，A45验证tuple／sample count／exact challenger／newest31／diagnostic absence；两者都没有让known-only与full baseline产生不同答案，也没有给“删除current-zero candidate”配置单变量缺陷注入。
- `counterexample`：实现正确处理A40的四种deterministic visual transition，却在historical pairing中仍只用known delta；只要A45 fixtures的visual／prior为0，它会全绿。另一个实现增加`if current_baseline <= 0: omit multiplicative`，只要A45使用positive current suffix同样全绿。
- `impact`：Task 4A brief review已确认的核心Major可以绕过Spec自称的可判否acceptance surface。
- `minimum_fix`：扩展A45或新增一条criterion，至少包含两组独立样本与mutation。第一组让historical known delta为0、visual／prior delta为正且actual delta匹配完整baseline，断言residual、ratio、candidate value和sample count；把baseline改成known-only必须红。第二组提供至少3条positive historical ratio evidence但current baseline为0，断言multiplicative candidate仍在record中、`sample_count`正确且full value等于anchor actual；恢复current-value gate必须红。同步§13 transcription map和Plan Task 4B-P mutation清单。
- `conclusion_strength`：已确认。当前acceptance输入空间没有区分这两个错误实现与正确实现的必需变量。

## Minor

### T3B-AUTH-05：Same-transaction current-sample prune没有独立闭环control

- `severity`：Minor
- `primary_location`：Spec `:372`、`:479-485`
- `related_locations`：Spec A42～A44 `:649-651`；Plan `:394-397`
- `problem`：Behavior已明确sample在同一事务被existing prune移除时，checkpoint真实结果不能被改写；A42笼统写了sample-prune survival，A44列主outcome矩阵，但没有要求current sample本身成为本事务victim时同时断言checkpoint durable state与outcome。
- `counterexample`：测试只让一个较旧的checkpoint source sample在后续事务被prune，可抓sample FK；另测未prune sample的五种committed outcomes。实现若在`sample_will_exist == false`分支保留`Applied`文字却跳过／删除当前checkpoint，或把结果改成NoChange，两组测试都可能通过。
- `impact`：Normative state machine仍可实现，但一个与fixed source现有“pruned observation重写”分支直接相邻的接缝缺少专门控制。
- `minimum_fix`：在A42／A44加入current sample因sample cap在同一事务被选为victim的fixture，断言sample row缺席、checkpoint replacement仍存在、event保存实际Applied／Deleted结果、revision一致；分别注入“pruned时跳过checkpoint”和“pruned时把outcome改NoChange”使其定向变红。
- `conclusion_strength`：高置信acceptance缺口；不表示Spec行为本身含糊，因此定为Minor。

## 分面结论

### Spec completeness verdict

**NEEDS FIXES**

Spec已完整、无明显矛盾地转录以下主体行为：

- Fixed／per-item exact conservation、whole visual all-or-none与appended per-item value-or-zero。
- Raw／non-object／message／reasoning／function-output／media／unknown shape归属。
- Compact digest、FixedContext三位置、item五位置V1与788-item单字段bound。
- Sample pending／store stamp、same-time committed availability、single base与ProfileKey边界。
- All-available candidates、canonical tuple／champion order、`sample_count`、完整suffix baseline、current-zero multiplicative、newest31及diagnostic absence。
- Canonical ProfileKey JSON identity、hash仅作index、16／8 checkpoint、sample-prune survival、CAS与store stamp。
- Capacity四分支、drift precedence、old-E current capacity sample、termination、caps、cache与rollback。
- Required checkpoint outcome完整main matrix、policy-entry `NotCommitted`、nested capacity transition唯一authority和post-COMMIT cancellation。
- Rejected route表与revision record记录了本轮采用的主要行为和关键否决路线。

但`T3B-AUTH-02`留下了current evidence order无法构造的实现缺口，`T3B-AUTH-04／05`留下可绕过的acceptance缺口，因此Spec不能批准。

### Plan sequencing verdict

**NEEDS FIXES**

Plan正文中的核心任务顺序与职责切片本身正确：

`Task 3B carrier／store → Task 4A deterministic → Task 4B-P learned prefix → Task 4B profile＋eligibility → Task 4C drift → Task 5`

四个`PredictionMethod`未删除、改名或重排；Spec和SDD明确禁止历史record回填未来candidate。TaskList依赖边也正确，`#13 → #27 → #14 → #15 → #16`不会绕过4B-P。

但Plan的policy／observation ownership仍自相矛盾，status和现存Task 4A brief又没有同步到该顺序，因此整体Plan sequencing不能批准。

## §8.1.1 action-ID核验

该面通过：

- Fixed source现有分母为108 semantic bases／204 expanded IDs。
- Current Spec只新增一个`EFC`：`state.prefix-checkpoints-read`。
- Current Spec只新增两个`EC`：`prefix-checkpoint.upsert`、`prefix-checkpoint.delete`。
- Base数量为`108 + 3 = 111`。
- Expanded ID数量为`204 + 3 + 2 + 2 = 211`。
- Plan使用同样三个base names并声明111／211。
- A26要求base count、expanded count和完整set equality，A27覆盖schema／DDL／outcome转录，没有发现漏名或额外action。

## 搜索面与证据边界

完整读取了固定Spec、Plan、README、status、九份指定design／review输入、SDD progress、现存Task 4A brief、相关TaskList JSON，以及fixed source的DTO、feature analyzer、schema、confirmed-action ledger、apply transaction、codec、snapshot和prune接缝。CodeGraph MCP判定fixed checkout没有可用index，随后使用绝对路径Read和限定`rg`。

没有运行broad tests、真实upstream、SQLite mutation或provider probe。本评审裁的是固定authority的完整性、内部一致性、可实现性及验收分辨力，不证明尚未编写的Task 3B source质量、真实provider计费准确率或production性能。

本轮没有修改文件、source、authority、TaskList或Git状态，没有创建提交、分支、后台进程或测试资产，也没有执行清理。

## 最终结论

**Spec completeness：NEEDS FIXES。**

**Plan sequencing：NEEDS FIXES。**

**Task 3B source authorization：DENIED，待以上4项Major修正并通过fresh scoped re-review。**