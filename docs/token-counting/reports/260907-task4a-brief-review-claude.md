# Task 4A implementation-brief 独立评审

## 评审范围

- 被评对象：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md`
- Behavior authority：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`
- Implementation authority：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`
- Exact base：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`
- Exact-base source abbreviations：
  - `BASE_TYPES`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py`
  - `BASE_FEATURES`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/features.py`
  - `BASE_SCHEMA`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_schema.py`
  - `BASE_STORE`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py`

首尾复算结果一致：brief SHA-256 为 `35d5db83aac6283255748dead301b38aa6bca7299a516367b7e61b6e10af883d`，Spec SHA-256 为 `2644ad9a44a9b0b06f072513dfb82834f8512f5b3fc6272a435b45a8a8445834`，plan SHA-256 为 `ab7da5a2f0c5c292824ec14f52fbc5657c91fabf5f264428a493042821e3ab68`，exact-base HEAD 为 `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`。评审期间未检测到输入移动。

## 总体判定

**NEEDS FIXES**

- Blocker：2
- Major：6
- Minor：1
- findings_total：9

存在 Blocker／Major，不允许派 implementer。

## Blocker

### T4A-BR-01

- severity：Blocker
- primary_location：brief `:88-97`、`:103-120`
- related_locations：Spec `§4.2`、`§6.2`，尤其 `:198`、`:285-293`；`BASE_TYPES:165-177`；`BASE_FEATURES:294-313`
- 问题：brief 用两个whole-request `capability_visual_tokens`槽相减计算append-only suffix，但该槽是不可分解的all-or-none值。`BASE_FEATURES`在whole payload中只要任一media缺公式或metadata，就把整个槽设为`None`；`EstimateFeatures`没有per-item或prefix-aligned visual contribution。因而现有DTO无法实现Spec要求的“只分析appended items”。
- 反例：source payload已有一张缺dimensions的`input_image`，所以source visual为`None`；query严格append一张56×84且metadata完整的同类图片。Whole query仍因旧图片而为`None`，brief得到`visual_delta=0`；但只分析新append图片应得到`ceil(56/28) * ceil(84/28) = 6`。结果少6。相同信息损失也会污染brief `:109`的historical delta。
- 最小修法：在Task 4A之前插入DTO／feature／persistence前置切片，提供可按input prefix分解的deterministic contribution，例如per-item或prefix-aligned的known／visual presence与sum；并同步`types.py`、`features.py`、V1 codec／schema、Spec revision和transcription map。替代方案是把raw appended items及capability传入predictor重新分析，但这会改变现有接口和feature-core边界，brief必须明确选择。测试必须覆盖`None→None但append部分present`、`0→present`、`present→present`、`present→None`，并证明既不漏算也不double count。
- 结论强度：由固定DTO和feature实现直接确认，足以阻止实施；四个owned files内无法正确修复。

### T4A-BR-02

- severity：Blocker
- primary_location：brief `:128-137`
- related_locations：Spec `§6.2:295-297`、`§8.5:463`；`BASE_TYPES:662-718`、`:832-840`；`BASE_SCHEMA:154-168`；`BASE_STORE:4590-4647`
- 问题：brief要求从“initial state eligible”重放retained records来恢复prefix demotion状态，但现有DTO／V1只把点时eligibility附在可被prune的`PredictionRecord`上，没有能在record prune后存活的per-`ProfileKey`状态checkpoint。Spec又规定demoted状态只能通过8条subsequent evidence恢复或由new epoch清除，不能因旧records被容量淘汰而静默恢复。
- 反例：Profile P的16条triply-paired records完成demotion；随后没有P的recovery sample。容量压力将这16条sample及其records级联prune，但另一个Profile的高`last_used_order`短prefix anchor仍可匹配下一次P请求。brief从空的P记录集重放，回到eligible；Spec要求仍demoted，因为既没有8条subsequent recovery evidence，也没有epoch transition。点时champion不能补救：它与sample一起级联删除，且触发demotion的第16条record本身记录的是label到来前的eligible状态。
- 最小修法：先设计并持久化以`(identity, epoch, ProfileKey)`为键的prefix eligibility checkpoint及恢复窗口所需的bounded state，或建立能在所有合法prune后仍保证可重建的明确retention invariant。前者更直接。需要同步Spec、DTO、schema／store、prune合同和restart／prune测试，不能塞进Task 4A四个owned files。
- 结论强度：由Spec状态机、容量级联合同及固定V1字段共同确认，足以阻止实施。

## Major

### T4A-BR-03

- severity：Major
- primary_location：brief `:76-80`
- related_locations：Spec `§6.0:268-270`、`§7.3:339-345`、A20 `:570`；`BASE_TYPES:662-718`
- 问题：brief规定“只有exact miss时考虑prefix”，并明确exact-selected record只保留cold challenger。Spec要求prequential record保存所有当时available candidates；即使exact成为global selected，严格更短且可匹配的prefix仍须作为challenger存在。
- 反例：当前full fingerprint命中exact，同时snapshot有当前payload前N-1 items的有效prefix anchor。正确record应含exact、prefix deterministic／可用learned variants和cold，global selected仍是exact；brief会生成exact＋cold，永久丢失该样本的prefix error，后续16-sample demotion／recovery与diagnostics均缺分母。
- 最小修法：把candidate availability与global selection分开。`build_prediction_record()`无条件尝试构造严格更短的prefix candidates，随后按exact→prefix→cold选择；request decision仍返回exact及其intent。增加“exact hit＋shorter prefix available”的完整record测试，以及“exact存在时跳过prefix construction”的mutation。

### T4A-BR-04

- severity：Major
- primary_location：brief `:103-120`
- related_locations：Spec `§4.2:170-179`、`§6.2:291-293`
- 问题：brief把historical `known_delta`重新定义为`cold_value(longer)-cold_value(base)`，即known＋visual；Spec则把`known_tokens`与visual分槽，并以`known_delta`定义additive／multiplicative训练和公式。brief还额外规定current suffix baseline `<=0`时不产生multiplicative candidate，而Spec把candidate存在性系于至少3条历史eligible ratios，没有这项current-value gate。
- 反例：base为known100／visual0／actual100，longer为known100／visual10／actual110。按Spec字面，known delta为0、additive residual为10且该pair不产生multiplicative ratio；按brief，delta为10、additive residual为0且该pair产生`log(10/10)`。三条样本后candidate集合及预测不同。另有3条合法positive-ratio history时，current delta为0仍有定义良好的`0 * exp(median(log ratios))`candidate；brief会直接删除该candidate及其prequential fact。
- 最小修法：先在living Spec唯一确定训练baseline。若确实要以完整deterministic suffix baseline训练，应在Spec中改名为` suffix_baseline_delta`，明确known／visual／prior及`None`规则，并修订formula、candidate eligibility和transcription；否则brief必须按literal known-token delta实现，并删除current-value gate。为known与visual刻意分离的样本、minimum-3边界及current-zero candidate增加精确断言。
- 说明：这里不是简单的重复加visual，而是brief改变了校准baseline；T4A-BR-01中的presence不可分解问题仍须另行修复。

### T4A-BR-05

- severity：Major
- primary_location：brief `:103-110`
- related_locations：Spec `§6.2:291-293`及`§15` revision record
- 问题：brief新增了会改变合法prediction的历史配对规则，但living Spec没有承载它们：base必须`observed_at_us < longer.observed_at_us`、same timestamp一律跳过、每个longer只按coverage／newest／sample-key选择一个base。它们不是invalid-state validation，而是决定哪些样本达到minimum3的行为合同。
- 反例：同一longer有两个合法strict prefixes，base A为coverage1／actual100，base B为coverage2／actual120。选择B得到`actual_delta=30`，保留全部pairs或选A得到50。又如base和longer同timestamp，brief给0 evidence，而按canonical key建立顺序会给1 evidence。三条门槛附近会直接改变candidate是否存在。
- 最小修法：在Spec §6.2先写入point-in-time availability判据、same-timestamp处置及single-base total order，并追加revision／transcription；随后brief逐字引用。该决定属于R4 delegated implementation scope，无需冒充新的用户裁决。

### T4A-BR-06

- severity：Major
- primary_location：brief `:128-135`
- related_locations：Spec `§6.2:295-297`
- 问题：variant selection在brief `:124`明确过滤same `ProfileKey`，但demotion／recovery replay没有重新施加该过滤，文字上会遍历snapshot的全部retained records。Spec把状态机限定在当前`identity／epoch／ProfileKey`。
- 反例：Profile A有16条prefix同时落后profile／cold超过5个百分点；Profile B没有paired evidence。跨profile replay会把B也demote，而Spec要求B保持eligible。
- 最小修法：§5.3入口显式先筛选`record`及其source sample与当前`features.profile_key`相等，并让持久化状态同样以ProfileKey为键。增加A有16条差样本、B为空的隔离测试和移除ProfileKey过滤的mutation。

### T4A-BR-07

- severity：Major
- primary_location：brief `:134`
- related_locations：Spec `§6.2:297`
- 问题：brief说demotion后“只统计后续paired records，至少8条后比较”，但没有把window限制为最近8条。按自然实现会累计全部post-demotion records；Spec明确是“最近8条”。
- 反例：demotion后的前8条中prefix APE=1、cold APE=0，接着8条中prefix APE=0、cold APE=0.1。正确latest-8 window应恢复；累计16条的median仍会使prefix落后而不恢复。
- 最小修法：定义bounded latest-8 deque；触发demotion的第16条label不得计入recovery，之后每个qualifying sample滚动一次，满8条即按`<= best alternative`判断。增加“8 bad随后8 good”的淘汰测试及把window改成unbounded的mutation。

### T4A-BR-08

- severity：Major
- primary_location：brief `:173-197`
- related_locations：brief `:124`；Spec `§6.2:293`、`§7.3:345`、`§8.5:463`；plan Task 4A `:381-387`
- 问题：required tests／mutations不能判红两个brief自己声明的承重不变量。其一，没有超过31条且older与newest结论相反的fixture，遗漏`[:31]`仍可通过minimum8／tie测试。其二，没有明确让relevant `PredictionEvaluation` rows缺席的fixture，错误依赖bounded diagnostics而不是`PredictionRecord candidate＋sample actual`的实现可能全绿。
- 反例：63条共同records中older32条让additive胜、newest31条让deterministic胜；正确结果只看newest31，使用全部63条会反转。另构造8条record＋actual但`LearningSnapshot.evaluations=()`，正确实现仍可选learned champion，错误实现会缺证据或走fallback。
- 最小修法：增加上述两类fixture；对应执行“移除newest-31 slice”和“改从snapshot.evaluations读取APE”两个单变量mutations，并核失败来自champion选择而非fixture construction。

## Minor

### T4A-BR-09

- severity：Minor
- primary_location：brief `:50-56`、`:113-126`、`:141-151`
- related_locations：`BASE_TYPES:609-618`、`:662-718`；`BASE_STORE:4590-4621`
- 问题：brief没有完全固定DTO的持久事实。它没有明确`PredictionRecord.candidates`及`method_champions`的canonical tuple order，也没有规定prefix deterministic candidate的`sample_count`。当前DTO接受多种顺序和值；`evaluate()`按candidate tuple order返回，store又持久化candidate ordinal并把champions重排为method enum order，因此不同实现可得到不同durable／round-trip对象。
- 反例：`(cold, exact, prefix)`与`(exact, prefix, cold)`均可通过DTO且selected仍为exact，但evaluation顺序和persisted ordinal不同；prefix deterministic的`sample_count=0`与`1`也都合法。
- 最小修法：明确candidate按method order，prefix内部按deterministic→additive→multiplicative，champions按`PredictionMethod` order；同时明确每种candidate的`sample_count`含义和值。建议single-source deterministic prefix记1，但如果字段意图只计suffix-training evidence，则需在Spec中明确另一值。增加完整tuple和round-trip断言。

## 已核对且未发现问题的部分

- brief `:80-97`对直接prefix anchor的strict append、coverage→newest→UTF-8 BINARY／numeric total order、same-prefix 100／120 single-source provenance及PREFIX intent描述，与Spec和当前`PrefixAnchor` DTO一致；问题仅在不可分解visual suffix。
- Exact median100／101→100.5、全部source keys进入EXACT intent及exact unconditional eligibility，与当前DTO一致。
- `build_prediction_record()`拒绝已存在sample key、`evaluate()`对actual0只产absolute error、variant／demotion从record＋actual重建而不应依赖older diagnostics，这些文字方向正确。
- `Decimal(str(value)) * Decimal(str(multiplier)) → ROUND_CEILING → minimum-one`、large integer及`scale_local_estimate()`兼容wrapper要求与Spec一致。
- Owned-file、同步pure strategy、无store／queue／Task 4B profile generation／Task 4C drift／Task 5 orchestration的边界本身正确；两个Blocker说明的是这些owned files不足以承载现有合同，不能以越界修改规避。

## Living Spec与被否路线处置

brief重复禁止的prefix median aggregate、aggregate-pixel推导、intent持久化、提前round／再次scale等路线已经分别存在于Spec §11或§6.4，不需要再造第二份authority。

以下内容需要先修living authority：

1. T4A-BR-01所需的可分解suffix representation及V1 persistence边界。
2. T4A-BR-02所需的可跨prune／restart存续的prefix state checkpoint。
3. T4A-BR-04的learned-suffix baseline与current-zero candidate语义。
4. T4A-BR-05的historical base availability、same-timestamp和single-base selection。
5. T4A-BR-09若candidate ordinal和`sample_count`属于durable可重放事实，应一并落入Spec；若明确只作为实现内canonicalization，也至少须在brief中唯一固定。

Generation mismatch、duplicate exact groups、非法snapshot抛`ValueError`、purity检查及worktree／commit步骤属于invalid-state或实施工序细节，不要求新增产品行为条款。

## 搜索面与证据边界

读完了固定SHA的brief、完整Spec、完整plan Task 4A及exact-base的DTO、feature analyzer、schema、store snapshot／codec／ordering实现、scaling与相关已有测试。CodeGraph MCP报告该路径未建立可用索引，随后使用绝对路径`Read`和限定`rg`。未运行broad tests，也未调用真实upstream。外部worktree的Git命令和一次运行探针被isolation guard拒绝，拒绝结果未被当作证据；HEAD通过worktree `.git`指针及branch ref复核。未核验brief自述的3,358-test base gate，因为它不承担上述合同判定。

本次未修改或创建任何文件。受当前leaf harness写入约束，报告未写入请求的`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-brief-review-claude.md`，故完整正文内联交付。

## 最没把握的三个判断

1. Spec作者可能本意是让`known_delta`表示完整deterministic suffix baseline，而不只是`known_tokens` delta；但当前文字和分槽合同不能支持该转义，因此T4A-BR-04要求先改authority，不依赖我猜哪种公式更好。
2. T4A-BR-08定为Major而非Minor，依据是项目明确要求tests／mutations能判红承重窗口语义；若调用方只把brief当非规范性提示，可重定级，但缺失控制仍成立。
3. Prefix deterministic的`sample_count`究竟应为1还是0没有现行authority；T4A-BR-09只确认其未定义，没有把我的建议冒充裁决。

**最终结论：NEEDS FIXES。**
