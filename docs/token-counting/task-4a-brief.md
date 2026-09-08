# Task 4A deterministic implementation brief

**状态：草稿，待独立review。** 本brief只定义Task 4A source合同；brief独立review达到`READY`之前不得启动source。Source完成后仍须经过独立source review、merged-state review和一次对应gate，本文不以计划或既有绿灯预先授权这些结论。

## 1. Authority、base与启动条件

行为权威是[spec.md](spec.md)，本brief起草时SHA-256为`5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48`；重点是Spec §4.1～§4.2、§5、§6.0～§6.4、§7.3与§13 transcription map，以及§12中A5的single-prefix selection／tie／suffix子集、A8的prequential all-available record／actual-zero子集和A15的唯一finalization。A20只取exact／deterministic-prefix／cold candidate cardinality、champion facts及exact selected仍保留strictly-shorter prefix challenger的Task 4A子集；A36只取request-side `PredictionDecision`／intent和pure predictor边界，不包含Task 5 queue／store owner chain。实施顺序权威是[plan.md](plan.md)，本brief起草时SHA-256为`bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`；执行入口是Plan `Task 4A：实现cold-start、exact／deterministic prefix与prequential record`。进度只以[status.md](status.md)为volatile authority；[HANDOVER.md](HANDOVER.md)只提供交接事实和启动顺序。

Source启动前必须在实际source worktree重新计算并记录`spec.md`、`plan.md`、`status.md`、`HANDOVER.md`四个SHA-256。若Spec或Plan不再等于上述hash，先重新做brief delta review；若status或HANDOVER变化，先确认它仍授权同一Task 4A slice、base和allowed paths。不得把本brief中的点时hash当作永久冻结开关。

旧`.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md`只作为识别已否路线的历史artifact；本文的正向合同全部来自上述current Spec／Plan及已集成Task 3B carriers，不继承、修补或复用旧brief合同。

Task 4A exact base和current main均为`6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`，其parent为`42fb23299bc9487d1751749668277ac4304861f8`，subject为`feat: integrate token learning persistence`。Task 3B reviewed source由`archive/260907-token-learning-prerequisites`保留在`e2461a6ea17c968201bb1e0c2fb33be87be901e8`，其parent为`16a0904496f0af0a7832e4dd4bcb18fdc69919f9`；它通过main-side squash而非祖先关系进入`6044919a`。Task 3B source review locator为[260907-task3b-source-review-grok-xhigh-followup.md](reports/260907-task3b-source-review-grok-xhigh-followup.md)，merged-state review locator为[260907-task3b-merged-state-review-grok-xhigh.md](reports/260907-task3b-merged-state-review-grok-xhigh.md)，main-side gate locator为[260907-task3b-merged-precommit-gate-gpt-s.md](reports/260907-task3b-merged-precommit-gate-gpt-s.md)；三者分别记录source `APPROVED`、merged-state `APPROVED`和gate `PASS`，不替代Task 4A自己的验证。

实现必须从`6044919a`的隔离worktree开始。启动记录必须包含physical worktree、branch、initial HEAD、exact base、current main和上述Task 3B archive ref。不得移动、stash、reset、restore、clean、merge或提交shared main现有WIP，不得push。若exact base、authority或Task 3B carriers与本brief不一致，立即停止并报告，不得用rebase、cherry-pick、扩大path或修改carrier自行“修通”。

## 2. Objective与完成边界

本slice首次实现pure deterministic `TokenPredictor`核心：

1. whole-request deterministic cold-start；
2. active-epoch history-exact；
3. strictly-shorter、single-anchor history-prefix deterministic；
4. request-side `PredictionDecision`与prequential `PredictionRecord`／`PredictionEvaluation`；
5. evaluate-before-learn边界；
6. 唯一public integer finalization及旧scaling wrapper兼容。

完成判据是：四个allowed paths内的source和direct tests实现本文全部行为；required positive controls和单变量mutations均有可审计结果；focused、完整tokenization、Ruff、Pyright通过；source review为0 Critical／Important；随后merged-state review和一次gate通过。Production pipeline接线、store调用和真实provider准确性不属于本slice完成判据。

## 3. Allowed paths与stop rule

只允许以下tracked path发生变化：

- Create `src/app/tokenization/prediction.py`
- Modify `src/app/tokenization/scaling.py`
- Create `tests/unit/tokenization/test_prediction.py`
- Modify `tests/unit/tokenization/test_local_estimate_scaling.py`，仅在finalization／wrapper回归需要时

不得修改Task 3B拥有的`types.py`、`features.py`、`learning_schema.py`、`learning_store.py`、worker或其tests，也不得修改Spec、Plan、status、HANDOVER、旧brief、其它`.dev`文档、human-controlled docs、pipeline／driver、provider／routing、configuration、dependency或lockfile。若现有Task 3B DTO、codec、snapshot、contribution或checkpoint carrier无法表达本文合同，或其实现与current authority存在真实冲突，必须停止source并报告最小反例、涉及路径、authority locator和建议owner；在取得新授权前不得修改carrier。

## 4. 消费的Task 3B接口与pure API

`prediction.py`只消费已经集成的public immutable carriers：`EstimateFeatures`及其`FixedContextContribution`／`InputItemContribution`，`LearningIdentity`，single-active `LearningSnapshot`，`StoredSample`，`ExactAnchor`，`PrefixAnchor`，candidate／champion／record／evaluation DTO，以及request-only `PredictionDecision`／`AnchorUseIntent`。不得读取store-private validated state、SQLite rows、events或bounded diagnostic rows来补公式。

必须提供以下同步pure接口：

```python
predict_exact_or_prefix(features: EstimateFeatures, snapshot: LearningSnapshot) -> PredictionDecision
build_prediction_record(sample_key: SampleKey, features: EstimateFeatures, snapshot: LearningSnapshot) -> PredictionRecord
evaluate(record: PredictionRecord, actual: int) -> tuple[PredictionEvaluation, ...]
```

`scaling.py`必须提供唯一量化边界：

```python
finalize_local_prediction(value: int | float, multiplier: float) -> int
```

既有`scale_local_estimate(tokens: int, multiplier: float) -> int`保留名称和signature，只delegate到`finalize_local_prediction()`。Candidate构造、champion构造和global selection必须由request decision与prequential record共享同一private result path，不允许复制两套算法。所有接口无I/O，不import或调用learning store、async queue、task、pipeline、provider、routing、catalog或config。

Caller未来构造`LearningUpdate`时，本slice对应的`prefix_checkpoint_command`必须显式传入`NoPrefixCheckpointChange()`；`None`、隐式default、`ReplacePrefixCheckpoint`和`DeleteRecoveredPrefixCheckpoint`都不合法。Task 4A不读取checkpoint来改变prefix eligibility，不实现16／8 policy。

## 5. Deterministic behavior contract

### 5.1 Compatibility与canonical candidates

先验证`features.estimator_generation == snapshot.identity.estimator_generation`、`features.profile_schema_revision == snapshot.identity.profile_schema_revision`且`snapshot.active_epoch == snapshot.identity.learning_epoch`；不兼容是caller contract violation，raise `ValueError`，不得静默降级到cold-start。

本slice只产生以下closed candidate keys，并按Spec §6.0七种合法pair顺序形成canonical subsequence：

1. `history-exact/median`，存在exact match时；
2. `history-prefix/deterministic`，存在strictly-shorter match时；
3. `cold-start/deterministic`，始终存在。

每个represented method恰有一个`MethodChampion`，champion tuple严格按`PredictionMethod`顺序。Task 4A中represented exact、deterministic prefix和cold champions都为`eligible_for_selection=True`；prefix demotion尚未实现。Global selected key是第一个eligible represented-method champion，因此exact优先于prefix，prefix优先于cold。Candidate、champion和selected prediction共享snapshot identity、active epoch、revision及current `features.profile_key`。`sample_count`分别为exact实际使用的1～5、prefix single anchor的1、cold的0。

Candidate保留unscaled精度，不提前round或clamp。Candidate value `<= 0`时，在其排序去重后的`low_confidence_reasons`中加入`minimum-one`，仍保留原始value；其它low-confidence reasons来自current features，不从anchor或store拼接free text。

### 5.2 Whole deterministic cold-start

Cold-start必须从Task 3B exact-conservation contributions计算，而不是从whole-request差分或固定常数计算：

```text
whole_known =
    fixed_context.known_tokens
    + sum(item.known_tokens for item in input_item_contributions)

whole_visual =
    0
    if any(item.capability_visual_tokens is None for item in input_item_contributions)
    else sum(item.capability_visual_tokens for item in input_item_contributions)

whole_prior =
    fixed_context.prior_residual_tokens
    + sum(item.prior_residual_tokens for item in input_item_contributions)

cold_start_unscaled = whole_known + whole_visual + whole_prior
```

该计算必须与carrier已经验证的whole `known_tokens`和presence-aware `capability_visual_tokens`一致，并保留`None`与真实0的语义区别。空input按空tuple求和；minimum-one只在candidate reason和最终projection体现。

当前`cold-start-prior-v1` coefficient table全部为0，Task 3B contribution中的`prior_residual_tokens`就是该v1 residual的唯一聚合载体。Task 4A使用已经验证的contribution aggregate并保留`features.low_confidence_reasons`中的`missing-prior:*`／`zero-prior:*`事实，不再从`FeatureVector`额外应用一遍coefficient，也不双计prior；未来启用非零prior必须先修改authority和estimator generation，不由Task 4A猜测。

### 5.3 History-exact

按`features.full_fingerprint`匹配active snapshot exact anchors。零个是miss；同fingerprint多于一个group是snapshot contract violation并raise `ValueError`，不得依tuple顺序任选。

Exact使用该anchor保存的最近1～5个`actual_tokens`的数学median，不量化；例如`100, 101 -> 100.5`。Candidate sample count等于actual数量。Exact request decision携带`AnchorKind.EXACT` intent，fingerprint为full fingerprint，source keys完整保留anchor中的全部1～5个sample keys，不得只保留median附近的一个source。

Exact命中只决定global selection，不能短路candidate construction。仍须尝试构造一个strictly-shorter deterministic prefix challenger并把它及cold candidate放入同一prequential record；request decision只为最终selected exact产生intent，内部challenger不产生anchor-use side effect。

### 5.4 History-prefix deterministic

Prefix match必须同时满足：

1. `anchor.context_fingerprint == features.context_fingerprint`；
2. `anchor.prefix_fingerprint.item_count < len(features.prefix_fingerprints)`，即query至少append一个item；
3. query在该item count位置的rolling prefix fingerprint逐字段等于anchor的prefix fingerprint。

在所有match中由predictor自行按以下total order选择唯一canonical anchor，不依赖snapshot tuple顺序：

1. 较大`item_count`优先；
2. 较大`observed_at_us`优先；
3. `process_boot_id`按UTF-8 BINARY ascending；
4. `request_id`按UTF-8 BINARY ascending；
5. `attempt_index`按numeric ascending。

相同coverage的100／120 anchors必须由newer timestamp选120；相同timestamp的attempt 2／10必须按numeric order选2。Prefix不得取多个matching actual的median。Selected anchor的sample key必须在snapshot中恰有一个对应sample；missing或duplicate是contract violation。Prefix request decision携带`AnchorKind.PREFIX` intent、该prefix digest和唯一source sample key。

Deterministic suffix只切current query在selected anchor item count之后的`input_item_contributions`：

```text
suffix_baseline_delta = sum(
    item.known_tokens
    + (item.capability_visual_tokens if item.capability_visual_tokens is not None else 0)
    + item.prior_residual_tokens
    for item in appended_items
)

history_prefix_deterministic = selected_anchor.actual_tokens + suffix_baseline_delta
```

不得从current whole cold减source whole cold，不得重复fixed context，不得仅算known tokens，不得把None当成跨item传播的all-or-none状态。必须覆盖旧prefix／append suffix的`None -> None`、`None -> known`、`0 -> known`、`known -> None`，并证明每个新item自己的known、visual-or-zero和prior各计一次。这里的full suffix baseline是deterministic per-item slice；historical learned-pair full-baseline formula仍属于Task 4B-P。

### 5.5 Prequential record、evaluation与唯一request intent

`build_prediction_record()`必须先拒绝`sample_key`已存在于`snapshot.samples`或`snapshot.prediction_records`，从而保证current label尚未进入candidate generation。它保存当时全部available candidates、完整candidate keys、每个represented method唯一point-in-time champion／eligibility，以及按method顺序得到的唯一global selected key。Absent exact／prefix不制造candidate、champion或0-valued placeholder。Exact selected时prefix challenger仍存在。

`predict_exact_or_prefix()`与`build_prediction_record()`必须选择同一个candidate。只有request-side selected exact／prefix decision携带intent；selected cold无intent。Intent不得进入`PredictionRecord`、candidate、evaluation、event或SQLite，也不得由prequential challenger触发。

`evaluate()`要求`type(actual) is int and not bool`且`actual >= 0`，并严格沿record candidate tuple顺序逐candidate返回：

```text
absolute_error = abs(predicted - actual)
signed_relative_error = (predicted - actual) / actual if actual > 0 else None
absolute_percentage_error = abs(signed_relative_error) if actual > 0 else None
```

不得round。`actual == 0`只产生absolute error；relative、APE、multiplicative ratio、champion window、checkpoint和drift evidence均缺席。Prequential顺序固定为`build record -> evaluate every candidate -> learn/commit`；本slice不执行learn或commit，但测试必须能判否把current sample先放入snapshot的泄漏。

### 5.6 唯一finalization

`finalize_local_prediction()`拒绝bool、非`int | float`、非finite value，以及bool、非`int | float`、非finite或`< 1.0`的multiplier；允许finite negative／zero candidate进入minimum-one。严格执行：

1. `Decimal(str(value)) * Decimal(str(multiplier))`；
2. 对乘积执行`ROUND_CEILING`；
3. `max(1, integer)`。

必须覆盖`100.5, 1.0 -> 101`、`100.5, 1.1 -> 111`、`100.1, 1.1 -> 111`、negative／zero -> 1及large integer无binary-float product精度损失。不得在candidate、predictor、wrapper或未来driver提前ceil，不得finalize后再次scale或round。兼容wrapper的positive integer行为保持；`scale_local_estimate(0, 1.5)`从旧0改为1。

## 6. Explicit non-goals

本slice不实现Task 4B-P的learned prefix additive／multiplicative formulas、historical pair index、committed-order pair availability、newest31 variant selection或formula-level A45 full-baseline／current-zero controls；不实现Task 4B的profile candidates、promotion、per-ProfileKey checkpoint policy或16／8 demotion／recovery；不实现Task 4C drift／epoch transition。

本slice不实现Task 5 queue、learning service、pipeline、lifespan、anchor-use persistence或`LearningUpdate` orchestration；不修改provider、routing、count provider chain、4141 service或public response wiring。它也不复活旧brief的whole-request visual subtraction、records重放eligibility、Task 4A learned variants、demotion／recovery或prefix actual median路线。

## 7. Required positive controls与single-variable mutations

所有control使用现有pytest和直接fixture／assertion完成，不新增proof framework、control plane、通用mutation runner或production-only instrumentation。Independent oracle必须由test literal、直接算术、Python标准库语义或手工构造DTO提供，不能调用被测private helper生成expected。每个mutation必须只改变一个目标变量或branch，在同一目标test node上运行；报告必须保留未裁剪的原始pytest失败输出，至少含命令、node id、assertion diff或exception、exit status，并记录恢复后同一node green。未执行的boundary必须明确列为`unverified`，不得由邻近green推断。

| ID | Positive control与单变量mutation | 允许的独立oracle | 原始失败输出要求 | 本control不验证的边界 |
|---|---|---|---|---|
| T4A-C01 cold exact aggregate | 手工给出fixed和多个item的known／visual／prior，断言whole cold精确等于逐项和并保留fraction；分别用None、0和known whole visual。Mutation只把实现改成固定1、漏prior或直接信任错误的替代aggregate之一，每次独立运行并判红。 | Test literal逐项加法；不得调用production cold helper。 | 完整显示expected／actual unscaled value及目标fixture id。 | 不证明真实provider计费或Task 8 production visual formula。 |
| T4A-C02 exact median与intent | 1～5 actual覆盖single和even median`100.5`，intent保留全部source keys。Mutation只在median处提前floor，另一次只把intent缩成单source，均判红。 | Python `statistics.median`或手写sorted middle arithmetic；source tuple为fixture literal。 | 显示fractional value或完整source-key tuple差异。 | 不证明anchor由store如何形成或exact drift。 |
| T4A-C03 candidate tuple／order／champion／cardinality | Cold-only、exact+cold、prefix+cold、exact+prefix+cold分别断言canonical candidate-key subsequence、champion method order、每represented method恰一champion、sample counts和selected key。Mutation只交换candidate顺序、交换champion顺序、覆盖same-method candidate或改一个sample count，逐项判红。 | Test中显式写出closed key tuple和expected counts，不从production iterator生成。 | 显示完整candidate key／champion tuple或count diff。 | 不验证4B-P learned variants、profile candidates或store codec round-trip。 |
| T4A-C04 exact selected仍构造prefix | 同时命中exact和strictly-shorter prefix时，selected为exact，而record仍含prefix deterministic challenger和cold；request intent只指exact。Mutation只在exact hit后early-return跳过prefix，判红。 | 显式expected三key tuple和exact intent；不调用selection helper。 | 显示missing prefix key、candidate cardinality及selected／intent facts。 | 不验证challenger的16／8 eligibility使用。 |
| T4A-C05 single-anchor canonical tie与snapshot order | 覆盖longest coverage、100／120 newest、same-time UTF-8 BINARY fields、numeric attempt 2／10，并对正序／逆序snapshot得到相同single source。Mutation分别只改成matching actual median、反转一个tie comparator或直接取tuple first，逐项判红。 | 手写anchor集合和lexicographic bytes／integer expected source key。 | 显示selected unscaled value、source key和两种snapshot order结果。 | 不验证4B-P historical base availability或pair-index complexity。 |
| T4A-C06 strict-prefix matching | Equal-length exact prefix、top-level mismatch、item reorder和rolling digest mismatch都不产生prefix；真正append才产生。Mutation只把`<`改为`<=`或省略一个match字段，判红。 | Fixture直接列明item count、context和digest；不复用production matcher。 | 显示意外candidate／缺席candidate及anchor identity。 | 不证明fingerprint producer本身正确；其coverage由Task 2／3B tests拥有。 |
| T4A-C07 suffix whole-request subtraction | Source whole facts故意与current fixed context不同，但current appended-item tuple固定；正确结果只加appended slice。Mutation只恢复`current_whole - source_whole`，判红。 | Test literal对appended items逐项算known+visual-or-zero+prior。 | 显示正确slice delta、错误whole delta和final prefix value。 | 不验证historical pair的learned residual／ratio公式；后者属于4B-P。 |
| T4A-C08 visual transitions | 分别覆盖`None -> None`、`None -> known`、`0 -> known`、`known -> None`，每个append item的known／visual-or-zero／prior只计一次。Mutation只使用whole all-or-none visual subtraction或传播source None，判红。 | 每个appended item的literal arithmetic，不调用whole cold helper。 | 显示每种transition的suffix delta和prefix full value。 | 不证明真实resize／limit或provider visual billing。 |
| T4A-C09 evaluate-before-learn | Current sample key不在snapshot时构造record并evaluation；相同key已在samples或records时拒绝。Mutation只在build前把current sample插入snapshot或移除duplicate guard，判红。 | 两份显式pre／post snapshot和固定actual；不从store transition生成。 | 显示泄漏后method／value变化或缺失的`ValueError`。 | 不验证Task 5 consumer transaction和store commit ordering。 |
| T4A-C10 actual-zero metrics | 对每个available candidate，actual 0仍产生absolute error，而relative／APE均为None，evaluation tuple保持candidate order。Mutation只执行除零替代、写入0.0 relative／APE或丢掉candidate evaluation之一，逐项判红。 | 直接用`abs(predicted)`和literal `None`；candidate tuple手写。 | 显示完整evaluation tuple、metric字段和candidate key。 | 不验证后续ratio、checkpoint或drift window过滤实现。 |
| T4A-C11 finalization multiply order | 覆盖100.5／100.1、multiplier 1／1.1、negative、0和large integer。Mutation只改成先ceil再乘，另一次只改成binary-float product或二次rounding，逐项判红。 | Test中直接使用`Decimal(str(...))`、`ROUND_CEILING`和literal minimum-one。 | 显示输入、Decimal product、expected integer和mutant actual。 | 不验证future driver是否只调用一次；Task 5／pipeline gate负责接线。 |
| T4A-C12 wrapper旧行为 | Positive integer compatibility保持，0现在返回1；monkeypatch／spy证明wrapper只delegate一次。Mutation只恢复旧`multiplier == 1`／integer-ratio shortcut或旧0 passthrough，判红。 | Stub `finalize_local_prediction` call capture加literal expected；不复制wrapper实现。 | 显示delegate call count／arguments或0 expected 1 vs actual 0。 | 不验证config loading和remote count，因为本slice不改它们。 |
| T4A-C13 producer-output invariants | 只检查`build_prediction_record()`实际产出：candidate keys是exact／deterministic-prefix／cold的canonical available subsequence；champions按method order并恰好覆盖represented methods；represented exact／cold eligibility恒true；selected key等于第一个eligible champion；exact hit时仍保留available strictly-shorter prefix。Mutation只改`prediction.py`，分别制造漏champion、candidate／champion错序、exact／cold false、selected非first eligible或exact-hit early return，逐项判红。Missing／extra／wrong champion DTO注入、missing candidate-key reference及validator-relaxation mutations由Task 3／3A carrier tests拥有，Task 4A不重复且不得修改`types.py`。 | Test中显式写出expected candidate-key／champion tuple和eligibility／selected facts，不从production builder或DTO validator生成expected。 | 每个producer mutation必须显示完整actual tuple／coverage／eligibility／selected diff和独立node；不得用Task 3／3A validator异常冒充producer control。 | 不重复证明carrier malformed-input validator或SQLite codec；发现carrier冲突时按§3 stop rule报告。 |
| T4A-C14 explicit NoPrefixCheckpointChange output boundary | 断言Task 4A caller-facing integration contract要求caller显式提供`NoPrefixCheckpointChange()`，且`prediction.py`既不import也不构造`ReplacePrefixCheckpoint`／`DeleteRecoveredPrefixCheckpoint`，predictor outputs只包含decision／record／evaluations。若使用`LearningUpdate` fixture，它只能是独立caller seam test，用于证明显式NoChange装配，不是Task 4A DTO mutation，也不修改Task 3B DTO。Mutation只在`prediction.py`引入或构造Replace／Delete，或让caller seam省略显式NoChange，目标test判红。 | Test-side literal closed command type，加Python `ast`／source import检查；不调用store、不放松或复制Task 3B validator。 | 显示caller seam的command实际type，或禁止的import／constructor AST节点和对应文件位置。 | 不验证16／8 policy、CAS、capacity、store outcome或`LearningUpdate` carrier validator。 |

Formula-level A45的两项controls明确延后到Task 4B-P：一是historical known delta为0而visual／prior delta为正的full-baseline vs known-only mutation；二是至少3条positive historical ratio而current baseline为0时multiplicative candidate仍存在的current-zero mutation。Task 4A不得提前实现、运行后声称覆盖或从本slice green推断这两项。

## 8. Mutation执行纪律

每项mutation前保存本session专用、可审计的文件snapshot；前台运行最小目标test并确认非零exit来自目标不变量，而不是syntax、import、fixture setup或无关failure；记录未裁剪stdout／stderr与exit status；随后从snapshot恢复，并以byte comparison、`git diff --check`及同一test green确认恢复。不得用`git checkout`／`restore`覆盖他人工作，不得并行运行会修改同一文件的mutations，不得让mutant进入source commit。超时进程必须按具体PID停止后再恢复。

## 9. Verification、review与delivery gate

Source只在本brief独立review为`READY`且0 Blocker／Major后启动。实现完成后至少运行：

1. Focused prediction／scaling：`uv run pytest tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py`
2. 完整tokenization：`uv run pytest tests/unit/tokenization/`
3. Ruff：`uv run ruff check src/app/tokenization/prediction.py src/app/tokenization/scaling.py tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py`
4. Pyright：`uv run pyright src tests`
5. §7列出的direct mutations，逐项保存target red与恢复green

每条load-bearing命令必须记录physical cwd、repo top-level、branch、HEAD、Python环境和imported candidate module path。禁止`ruff format`。Source commit只含allowed paths，建议subject为`feat: predict tokens from exact history`；不得`git add -A`、`.`或`-u`，不得amend、push或直接集成shared main。

独立source review必须达到0 Critical／Important，检查behavior、Spec／Plan对应关系、allowed-path diff、non-goals、pure import boundary、所有positive controls与mutations、raw failure provenance和恢复后clean tree。Review evidence必须记录：

- exact source base `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`及parent；
- source worktree／branch、source commit SHA和保存它的ref；
- `git diff --name-status <exact-base>..<source-commit>`及仅allowed paths结论；
- brief review、source review和测试报告的stable locators；
- focused、完整tokenization、Ruff、Pyright与每项mutation的exact command／result；
- 未执行层级和未验证边界；
- Task 3B archive `e2461a6e`与current-main squash `6044919a`的lineage说明。

Source review通过后，才可在隔离integration worktree把reviewed source合入当时current main。Merged-state review必须确认allowed source bytes未因overlap漂移、无scope leakage且0 Critical／Important；随后只跑一次约定gate。最终记录merged commit、source↔merged patch／tree equivalence证据、merged-state review locator和gate locator。不得用source gate替代merged-state review，也不得重复无理由的full gate。

## 10. Rejected routes

- 不采用旧brief的whole-request `current - source` suffix subtraction；它在旧prefix visual为None而新append item visual已知时丢失贡献，current authority要求per-item slice。
- 不采用records重放prefix eligibility；sample prune会抹掉长期状态，16／8状态已由Task 3B checkpoint carrier保存并由Task 4B policy拥有。
- 不在Task 4A实现learned additive／multiplicative variants、historical pair index或newest31 champion；这些属于Task 4B-P。
- 不在Task 4A实现demotion／recovery、profile candidates或16／8 checkpoint transition；这些属于Task 4B。
- 不以exact命中为candidate-construction early return；exact只赢global selection，strictly-shorter prefix仍是point-in-time challenger。
- 不对prefix matching anchors取median；single-source canonical anchor才可由一个prefix `AnchorUseIntent`准确表达。
- 不把minimum-one塞进cold或prefix formula，不先ceil再乘，也不保留旧wrapper对0的旁路。
- 不修改Task 3B carrier来绕过测试；发现真实authority／implementation冲突时按§3停止并交回owner。
