# Task 4B-P learned prefix variants implementation brief

**状态：草稿，待独立review。** 本brief只定义Task 4B-P source合同；独立brief review达到`READY`且0 Blocker／Major之前不得启动source。Source完成后仍须经过独立source review、merged-state review和一次对应gate，本文不把任何既有Task 4A绿灯外推成Task 4B-P证据。

## 1．Authority、base与启动条件

行为权威是[spec.md](spec.md)，本brief correction snapshot SHA-256为`fdf63872b906dc87ec44eb4627c199552cc904d730add186600cc5095c639df9`；本slice重点实施Spec §5、§6.0～§6.2、§7.3、§12 A20的Task 4B-P子集、A41／A45及§13 transcription map。A20在本slice只承接all-available prefix variants、candidate／champion／`sample_count`、exact selected仍保留strictly-shorter prefix challenger，以及newest31／minimum8／strictly-better／deterministic→additive→multiplicative tie语义；A20中的profile comparison、16-sample demotion与8-sample recovery属于Task 4B，不在Task 4B-P范围。实施顺序权威是[plan.md](plan.md)，本brief correction snapshot SHA-256为`bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`；执行入口是Plan `Task 4B-P：实现learned prefix variants`。进度只以[status.md](status.md)为volatile authority，本brief correction snapshot SHA-256为`4a03b23cefd04ea7a07faf4082f4ad817fcae6b8ae0619f30571bf7786485220`；[HANDOVER.md](HANDOVER.md)只提供交接事实和启动顺序，本brief correction snapshot SHA-256为`a1ad58d3d03eac245103607bbc0bd7ecfb03b2b8b8421fdc95e00ac76ba95fd2`。

Source启动前必须在实际source worktree重新计算并记录`spec.md`、`plan.md`、`status.md`、`HANDOVER.md`四个SHA-256。若Spec或Plan不再等于上述hash，停止并先做brief delta review；若status或HANDOVER变化，停止确认其仍授权同一Task 4B-P slice、exact base和allowed paths。本brief中的点时hash不是永久冻结开关。

Task 4B-P exact base与本brief起草时current main均固定为`3badac7f6b020764cf8e30b2528ff51055dad0c2`，parent为`6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`，subject为`feat: predict tokens from exact history`。已reviewed Task 4A source由`archive/260907-token-prediction-exact-prefix`固定在`7d7e43b32c1d90e1723e6ad469262c5617e670a5`；它同样直接以`6044919a`为parent，经main-side squash而不是祖先关系进入`3badac7f`。Task 4A四个owned files在archive与main squash中byte-identical。Task 3B carrier source由`archive/260907-token-learning-prerequisites → e2461a6ea17c968201bb1e0c2fb33be87be901e8`保留，并已随`6044919a`进入main。

启动前必须读取当前[Task 4A brief](task-4a-brief.md)、[Task 4A source review](reports/260907-task4a-source-review-grok-xhigh.md)和[Task 4A merged-state review](reports/260907-task4a-merged-state-review-grok-xhigh.md)。`.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md`头部已标`SUPERSEDED／不得派发`，只可作为whole-request suffix差分、Task 4A全包learned variants和records重放eligibility等被否路线的历史证据；不得复制、修补或以它替代current Spec／Plan。

实现必须从exact base `3badac7f`的隔离worktree开始。启动记录必须包含physical worktree、repo top-level、branch、initial HEAD、exact base、current main、Task 4A archive和Task 3B archive。不得移动、stash、reset、restore、clean、merge、commit或切换shared main现有WIP，不得push，不得控制4141。若base、authority、Task 3B carriers或已集成Task 4A实现与本brief不一致，立即停止并报告最小反例、涉及路径和authority locator；不得用rebase、cherry-pick、扩大path或改carrier自行“修通”。

## 2．Objective与完成边界

本slice在已完成的Task 4A pure predictor上增加：

1. immutable、revision-bound的`PrefixPairIndex`及pure builder；
2. historical longer→single canonical base配对与full suffix baseline evidence；
3. `history-prefix/additive`和`history-prefix/multiplicative`全部available candidates；
4. 只用point-in-time record＋actual的newest-31共同窗口和prefix method champion选择；
5. all-available prequential candidate preservation、准确`sample_count`与Task 4A request intent兼容。

完成判据是：两个allowed paths内实现本文全部行为；required positive controls和single-variable mutations均有可审计结果；focused prediction tests、完整tokenization、Ruff、Pyright通过；独立source review为0 Critical／Important；随后merged-state review和一次对应gate通过。Task 4B profile／checkpoint、Task 4C drift、Task 5 orchestration和production provider wiring均不属于本slice完成判据。

## 3．Allowed paths与stop rule

Source commit只允许修改：

- `src/app/tokenization/prediction.py`
- `tests/unit/tokenization/test_prediction.py`

不得修改Spec、Plan、status、HANDOVER、Task 4A brief、任何review report或其它authority docs。不得修改Task 3B拥有的`types.py`、`features.py`、`learning_schema.py`、`learning_store.py`、worker及其tests；不得修改`scaling.py`、pipeline／driver、provider／routing、configuration、dependencies、lockfile、human-controlled docs或shared main。

Task 4A的cold-start、exact、deterministic prefix、evaluation、request intent和finalization语义保持原样。若现有`EstimateFeatures` contributions、`StoredSample.committed_order`、`LearningSnapshot`、candidate／champion／record DTO、Task 4A private construction path或其它carrier无法在上述两个文件内表达本合同，或与current Spec存在真实冲突，按stop rule停止并报告；不得修改carrier，不得把learned formula倒塞进“Task 4A修复”。

## 4．Pure interface与revision-bound index

保留现有同步pure接口及行为：

```python
predict_exact_or_prefix(features: EstimateFeatures, snapshot: LearningSnapshot) -> PredictionDecision
build_prediction_record(
    sample_key: SampleKey,
    features: EstimateFeatures,
    snapshot: LearningSnapshot,
) -> PredictionRecord
evaluate(record: PredictionRecord, actual: int) -> tuple[PredictionEvaluation, ...]
```

在`prediction.py`内新增immutable `PrefixPairIndex`和pure builder：

```python
build_prefix_pair_index(snapshot: LearningSnapshot) -> PrefixPairIndex
```

现有两个prediction producer可增加向后兼容的keyword-only `prefix_pair_index: PrefixPairIndex | None = None`参数。未提供时可从snapshot构建；提供时必须验证index的完整`LearningIdentity`、active epoch和snapshot revision全部等于当前snapshot，否则raise `ValueError`。两条producer必须继续共享同一个private candidate／champion path，不允许request decision与prequential record各写一套learned算法。

`PrefixPairIndex`必须绑定完整`LearningIdentity`、active epoch和snapshot revision，且内容不可变、可安全process-local缓存。Task 5以后才能按identity＋revision缓存并传入；revision变化直接丢弃重建。本slice不持久化index、不把它加入Task 3B DTO／SQLite、不创建cache、queue或task。

Builder和prediction保持同步、pure、无I/O；`prediction.py`不得import或调用learning store、SQLite、diagnostic evaluator、pipeline、provider、routing、catalog或config。

## 5．Behavior contract

### 5.1 Pair-index输入与复杂度

Builder必须验证每个retained sample具有positive且unique的`committed_order`；pending或duplicate order是invalid snapshot并raise `ValueError`。不得依赖`snapshot.samples`已有顺序。先按以下ascending total order排序：

1. `committed_order` numeric；
2. `process_boot_id` UTF-8 bytes；
3. `request_id` UTF-8 bytes；
4. `attempt_index` numeric。

随后单向遍历。处理一个historical longer时，lookup中只能存在`committed_order`严格更小的base；处理完成后，才把longer的final rolling-prefix identity加入lookup，供后续sample使用。Builder目标复杂度为：

```text
O(samples log samples + total retained prefix entries)
```

space为`O(total retained prefix entries)`。不得声称未排序输入下严格线性，也不得为每个longer再次扫描所有samples形成quadratic all-pairs实现。

### 5.2 Historical longer与single canonical base

一个historical longer只有在其完整identity／active epoch与index一致时才可进入index；为当前query取evidence时，longer还必须与current `features.profile_key`完全相等。Base的`ProfileKey`不要求相等，因为append item可能首次引入image、function或unknown kind。

对某个longer，base必须同时满足：

1. `base.committed_order < longer.committed_order`；
2. `base`的item count严格小于`longer`；
3. `base.features.context_fingerprint == longer.features.context_fingerprint`；
4. `base`的final rolling prefix fingerprint与`longer`在同item count位置的rolling prefix fingerprint逐字段相等。

每个longer恰选一个canonical base，不能保留或聚合全部matching bases。全序为：

1. 较大coverage／item count优先；
2. 较大`observed_at_us`优先；
3. `process_boot_id`按UTF-8 BINARY ascending；
4. `request_id`按UTF-8 BINARY ascending；
5. `attempt_index`按numeric ascending。

`observed_at_us`只参与canonical preference，不证明availability。Same timestamp但committed order较小的base合法；future或equal committed order不得成为base。Equal committed order同时违反unique-order snapshot invariant，必须fail-visible，不能按timestamp或tuple order任选。

### 5.3 Historical full-baseline evidence

对每个longer及其single canonical base：

```text
actual_delta = longer.actual_input_tokens - base.actual_input_tokens

historical_suffix_baseline_delta = sum(
    item.known_tokens
    + (item.capability_visual_tokens if item.capability_visual_tokens is not None else 0)
    + item.prior_residual_tokens
    for item in longer.features.input_item_contributions[base_item_count:]
)
```

不得用known-only delta，不得用longer whole-request cold减base whole-request cold，不得重复fixed context，也不得从base的whole visual presence推断appended-item visual。每个appended item自己的known、visual-or-zero和prior恰计一次；`None`与真实0保持不同输入状态，但该item在baseline arithmetic中都贡献0 visual。

Additive evidence要求`actual_delta > 0`且historical baseline `>= 0`，保存：

```text
actual_delta - historical_suffix_baseline_delta
```

Multiplicative evidence要求`actual_delta > 0`且historical baseline `> 0`，保存：

```text
log(actual_delta / historical_suffix_baseline_delta)
```

Additive与multiplicative evidence各自至少3条才产生对应candidate；两者的evidence集合和`sample_count`可不同。Actual delta为0或负数不进入任一variant；baseline为0仍可进入additive，但不进入multiplicative。

### 5.4 Current learned candidates

Current query仍先使用Task 4A规则选择一个strictly-shorter deterministic prefix anchor，并从current appended-item contribution slice计算：

```text
current_suffix_baseline_delta = sum(
    item.known_tokens
    + (item.capability_visual_tokens if item.capability_visual_tokens is not None else 0)
    + item.prior_residual_tokens
    for item in current_items[selected_anchor_item_count:]
)
```

没有current deterministic prefix anchor时，不产生learned prefix candidate。存在anchor时：

```text
prefix_additive =
    selected_anchor.actual_tokens
    + current_suffix_baseline_delta
    + median(additive residual evidence)

prefix_multiplicative =
    selected_anchor.actual_tokens
    + current_suffix_baseline_delta
      * exp(median(multiplicative log-ratio evidence))
```

Candidate availability只由对应historical evidence count决定，不得再对current scalar增加`> 0` gate。尤其current baseline为0且已有至少3条positive-ratio history时，multiplicative candidate必须存在，suffix value严格为0，full candidate等于selected anchor actual，`sample_count`仍为实际ratio evidence数。

Learned candidate的`sample_count`只计参与该variant median的actual pair evidence，不加selected anchor的1，不取unique rows总数，也不借用另一个variant的count。Deterministic prefix保持1，exact保持1～5，cold保持0。

### 5.5 All-available candidates与canonical producer

Candidate tuple必须是Spec §6.0七种合法pair的canonical subsequence。本slice最多产生：

1. `history-exact/median`，Task 4A exact match存在时；
2. `history-prefix/deterministic`，Task 4A strictly-shorter prefix存在时；
3. `history-prefix/additive`，当前prefix存在且additive evidence至少3条时；
4. `history-prefix/multiplicative`，当前prefix存在且multiplicative evidence至少3条时；
5. `cold-start/deterministic`，始终存在。

本slice不产生任何`profile-calibrated` candidate。Record必须保存当时全部available candidate keys和精确unscaled values；不得只保存prefix champion或global selected。Exact命中只决定global优先级，不能短路deterministic或learned prefix challenger construction。

每个represented method恰有一个`MethodChampion`，champion tuple按`PredictionMethod` enum order。Exact与cold champion继续恒为eligible；本slice没有16／8 policy，represented prefix champion也保持`eligible_for_selection=True`。Global selected仍按exact→prefix→cold取第一个eligible method champion。若prefix selected，无论其champion是deterministic、additive还是multiplicative，request-side `AnchorUseIntent`都必须继续准确指向Task 4A选中的single prefix anchor和唯一source sample key；challenger不产生intent。

Task 4A的cold／exact values、deterministic prefix value、low-confidence reasons、evaluation arithmetic、minimum-one和finalization不得改变。

### 5.6 Prefix variant champion selection

Variant selection只读取retained `PredictionRecord` candidates和对应`StoredSample.actual_input_tokens`，不得读取`snapshot.evaluations`或其它bounded diagnostic rows。每条eligible historical record必须：

1. 可唯一关联同sample key的retained sample；
2. record与sample的identity／epoch一致；
3. record candidate的`ProfileKey`与linked sample features的`ProfileKey`一致，并与current exact `ProfileKey`相等；
4. sample actual `> 0`；
5. 在其自己的prequential时点同时包含`history-prefix/deterministic`及当前待比较的全部available learned prefix candidate keys。

不得事后用当前算法重选历史candidate，也不得给历史record回填当时尚不存在的variant。对共同records按以下descending total order取newest 31：

1. linked sample `observed_at_us`；
2. `process_boot_id` UTF-8 BINARY；
3. `request_id` UTF-8 BINARY；
4. `attempt_index` numeric。

共同records少于8时，deterministic是prefix champion。达到8后，直接由record中的unscaled candidate和linked actual计算每个candidate的APE；learned variant只有median APE严格低于deterministic才可成为champion。所有数值相等时的固定优先级为deterministic→additive→multiplicative；additive与multiplicative都严格优于deterministic但彼此相等时，additive胜。无论谁成为champion，record仍保存全部available prefix variants。

`LearningSnapshot.evaluations=()`不影响variant selection。Actual为0的record不进入共同window，不伪造0 APE或占满8／31门槛。

### 5.7 Prequential与checkpoint边界

`build_prediction_record()`继续在current sample进入snapshot前冻结全部point-in-time candidates、champions和selected key；current label不得影响pair index、variant evidence、共同record window或champion selection。`evaluate()`继续沿完整candidate tuple产生evaluation，actual0语义不变。

Task 4B-P仍不实现checkpoint policy。未来caller构造`LearningUpdate`时必须显式使用`NoPrefixCheckpointChange()`；`prediction.py`不得import、构造或返回`ReplacePrefixCheckpoint`／`DeleteRecoveredPrefixCheckpoint`。

## 6．Explicit non-goals

- 不实现Task 4B的profile-calibrated additive／multiplicative candidates、MAD、distance、nearest31、promotion或prefix-vs-profile eligibility。
- 不实现per-`ProfileKey` eligible latest16／demoted latest8 checkpoint policy、demotion、recovery、CAS、capacity outcome或Replace／Delete command。
- 不实现Task 4C drift detection、learning epoch transition或old-epoch cleanup。
- 不实现Task 5 learning service、queue、lifespan、process-local index cache、pipeline／driver接线、anchor-use persistence或store orchestration。
- 不修改provider／routing、configuration、dependencies、public response、4141或真实upstream行为。
- 不修改Task 4A finalization、exact／cold semantics、deterministic prefix formula、evaluation semantics或scaling wrapper；不把learned formula重写成Task 4A范围。
- 不修改Task 3B types／features／schema／store／worker或其tests；carrier冲突按§3 stop rule交回owner。
- 不把formula-level A45再次标为deferred；full-baseline与current-zero controls由本slice正式实现、执行并接受review。

## 7．Required positive controls与single-variable mutations

所有control使用现有pytest和直接fixture／assertion完成，不新增proof infrastructure、通用mutation runner、control plane或production instrumentation。Independent oracle必须由test literal、手工算术、Python `statistics.median`／`math.log`／`math.exp`语义或手工构造DTO提供；不得调用被测builder、matcher、baseline或champion helper生成expected。

每个mutation只修改`src/app/tokenization/prediction.py`中的一个目标branch／comparator／filter／formula，在同一目标test node上运行。报告必须保留未裁剪stdout／stderr、exact command、node id、assertion diff或exception和非零exit status；恢复后同一node必须green。未实现或未运行的control明确标`unverified`，不得由邻近green推断。

| ID | Positive control | Single-variable mutation与required red |
|---|---|---|
| T4BP-C01 committed-order availability | Snapshot tuple故意反序，断言index与pair结果不变；future base不得用于earlier longer；duplicate／equal committed order snapshot必须`ValueError`，因此equal-order base不能被接受。 | 分别只移除builder committed-order sort、只放行future base或只删除duplicate-order guard；reverse-order pair source／count、future rejection或expected `ValueError`判红。 |
| T4BP-C02 single canonical base | 一个longer同时有短旧base、长旧base、同coverage较新base及same-time sample-key tie；手写全序只选一个base，并只产生一个pair。 | 只改成保留／聚合全部matching bases，另逐次只反转coverage、newer、BINARY或numeric tie中的一个；pair count、base key、residual／ratio必须判红。 |
| T4BP-C03 ProfileKey与index binding | Longer Profile A与current A可用；Longer Profile B不进入A evidence，而base可为不同ProfileKey。由另一个valid snapshot构造的index在identity、epoch或revision任一不同时均被producer拒绝；record profile与linked sample profile不一致时fail-visible。 | 分别只删除longer exact-ProfileKey filter、只跳过identity／epoch／revision中的一个binding check、或只接受record／sample ProfileKey mismatch；candidate presence、count或`ValueError`判红。 |
| T4BP-C04 full baseline vs known-only | 至少3个合法pair都让historical known delta为正、visual／prior delta也为正，actual delta恰等于完整baseline；手算additive residual为0、multiplicative log ratio为0，两个candidate value和各自`sample_count`精确匹配。不得构造违反Task 3B item framing invariant的zero-known append。 | 只把historical baseline改成known-only；residual、ratio availability、candidate value和count至少一项判红。 |
| T4BP-C05 historical visual tri-state | Historical pairs分别覆盖`None→None`且append item known、`None→known`、`0→known`、`known→None`；每个appended item的known、visual-or-zero、prior恰计一次，fixed context不进入。 | 只改为whole visual subtraction、传播base `None`、把0当absent或重复fixed context之一；每次对应literal baseline／candidate判红。 |
| T4BP-C06 evidence thresholds与current-zero | 2条evidence时variant缺席，3条时出现；构造additive与multiplicative evidence集合大小不同并断言各自count。Current baseline为0且至少3条positive historical ratio时multiplicative仍存在，suffix value0、full value等于anchor actual。 | 只恢复`current_suffix_baseline_delta > 0` availability gate，另一次只把minimum3改为2或把一个variant count借给另一个；candidate tuple／value／sample_count判红。 |
| T4BP-C07 candidate tuple、champion与exact challenger | 同时提供exact、current prefix及两种learned evidence，record candidate keys严格为exact／prefix deterministic／prefix additive／prefix multiplicative／cold；champions按method order，prefix champion指按本slice规则选中的valid variant，各candidate count准确，global selected仍exact，request intent仍只指exact。 | 分别只在exact hit后early return、只丢弃一个available learned candidate、交换candidate顺序、改一个learned `sample_count`或把prefix valid champion-selection branch改回deterministic；candidate tuple／preservation／count或expected champion判红。 |
| T4BP-C08 minimum8、strict improvement与tie | 共同records为7时deterministic胜；8条时learned只在median APE严格更低时胜。构造deterministic tie、additive／multiplicative tie与三方不同值，分别断言deterministic→additive→multiplicative优先级。 | 分别只把8改成7、把strict `<`改成`<=`、反转additive／multiplicative tie；champion key判红。 |
| T4BP-C09 newest31 reversal | 63条共同records中older32支持additive、newest31支持deterministic；正确champion只由newest31决定。反转snapshot samples／records输入顺序仍同结果，并覆盖same-time descending sample-key tie。 | 只移除newest31 slice、从tuple first取31或反转newest comparator；champion及选中31个sample keys判红。 |
| T4BP-C10 diagnostics absence | 至少8条record＋actual足以让learned variant严格胜，同时`snapshot.evaluations=()`；candidate和champion仍完整产生。 | 只改为从diagnostic evaluations读取APE或要求evaluation row存在；learned candidate／champion判红。 |
| T4BP-C11 all-current-variant common window | Current同时有additive与multiplicative时，只有同时保存deterministic＋additive＋multiplicative的historical records进入共同window；缺任一current variant的record不占8／31。Current只有一种learned variant时只要求deterministic＋该variant。 | 只改成per-variant不同record batches、允许missing-current-variant record或事后回填candidate；evidence keys、window count或champion判红。 |
| T4BP-C12 prequential／NoChange regression | Current sample已在samples或records时继续拒绝；actual0 record不进入variant window但每个available candidate仍只有absolute error。AST与caller seam继续证明`prediction.py`不import／构造Replace／Delete，显式`NoPrefixCheckpointChange()`成立。 | 分别只删除current-sample guard、允许actual0占window或在`prediction.py`引入Replace／Delete；对应exception、window／metrics或AST断言判红。 |

Mutation ownership边界：public `LearningSnapshot`对`StoredSample.committed_order is None`的拒绝，以及`PredictionRecord`对selected／champion missing、extra、wrong-method或missing-key corruption的拒绝，属于Task 3／3A types owner及其既有validator controls。Task 4B-P不得修改或放松`types.py` validator，也不把这些carrier-corruption mutations列为本slice source mutation；本表只对`prediction.py`能产生valid producer-output差异的branch执行mutation。

## 8．Mutation执行纪律

每项mutation前保存本session专用、可审计的`prediction.py`文件snapshot。前台运行最小目标test并确认非零exit来自目标不变量，而不是syntax、import、fixture setup或无关failure；保留原始未裁剪输出与exit status。随后从该snapshot恢复，并以byte comparison、`git diff --check`及同一node green确认恢复。

不得用`git checkout`／`restore`覆盖shared或其他agent工作，不得并行运行会修改同一文件的mutations，不得让mutant进入source commit。超时进程只按具体PID停止。若某mutation未执行、红因不纯或恢复无法证明，标`unverified`并阻止source delivery，不得补写推断性结论。

## 9．Verification、review与delivery gate

Source只在本brief独立review为`READY`且0 Blocker／Major后启动。实现完成后至少运行：

1. Focused prediction：`uv run pytest tests/unit/tokenization/test_prediction.py`
2. 完整tokenization：`uv run pytest tests/unit/tokenization/`
3. Ruff：`uv run ruff check src/app/tokenization/prediction.py tests/unit/tokenization/test_prediction.py`
4. Pyright：`uv run pyright src tests`
5. §7全部direct mutations，逐项保存target red与恢复green

每条load-bearing命令记录physical cwd、repo top-level、branch、HEAD、Python环境和imported candidate module path。禁止`ruff format`。Source commit只含两个allowed paths；必须用exact pathspec确认，禁止`git add -A`、`.`或`-u`。建议subject为`feat: learn token prefix residuals`；不得amend、push或直接修改／集成shared main。

独立source review必须达到0 Critical／Important，并检查Spec §5／§6.2／§7.3、Plan Task 4B-P、allowed-path diff、pure boundary、index complexity、all-available point-in-time facts、positive controls、mutation raw failure provenance和恢复后的clean source。Review evidence必须记录：

- exact source base `3badac7f6b020764cf8e30b2528ff51055dad0c2`及parent；
- source worktree／branch、source commit SHA和保存它的ref；
- `git diff --name-status <exact-base>..<source-commit>`只含两个allowed paths；
- current authority hashes、brief review locator、source review locator和测试／mutation报告locator；
- focused、完整tokenization、Ruff、Pyright及每项mutation的exact command／result；
- Task 4A archive `7d7e43b3`、Task 4A main squash `3badac7f`和Task 3B carrier archive `e2461a6e`的source lineage；
- 未采用路线和未验证边界。

Source review通过后，才可在隔离integration worktree把reviewed source合入当时current main。Merged-state review必须确认两个allowed source files未因overlap漂移、无scope leakage、无冲突残留且0 Critical／Important；随后只运行一次预先约定的merged-state gate并记录完整命令与结果。不得用source gate替代merged-state review，也不得无理由重复full gate。

最终记录merged commit、source↔merged patch／tree equivalence、merged-state review locator和gate locator。任何source commit、integration candidate或gate均不得push，也不得直接操作shared main。

## 10．Rejected routes

- 不采用旧`SUPERSEDED` Task 4A brief把learned variants、profile和eligibility一次塞回Task 4A；current顺序保持4A→4B-P→4B→4C。
- 不用`observed_at_us`证明happened-before；availability只认strictly smaller `committed_order`，same-time合法，future／equal非法。
- 不为一个longer保留全部bases、取base actual median或累计全部base pairs；只取single canonical base。
- 不用known-only historical baseline；它会把visual／prior重新学成residual。也不用whole-request cold差分；它破坏per-item presence与fixed-context边界。
- 不以current baseline为0删除multiplicative candidate；candidate availability由historical positive-ratio evidence决定。
- 不只保存prefix champion或global selected；point-in-time record保存全部available variants和exact candidate keys。
- 不读bounded diagnostic evaluations选variant；record＋linked actual是完整ground truth。
- 不用全部63条、oldest31、tuple first31或unbounded records代替canonical newest31。
- 不在本slice实现profile candidates、MAD／neighbors／promotion、16／8 checkpoint、demotion／recovery、drift／epoch、cache／queue／pipeline／anchor-use store orchestration。
- 不修改Task 3B carrier、Task 4A finalization或shared main来规避stop rule。

## 11．起草时未验证边界

- Task 4B-P source尚未启动；`PrefixPairIndex`、learned candidates、newest31和A45 formula controls均未实现、未运行、未review。
- 本brief尚未取得独立`READY`；不得据本文状态派发source。
- 起草过程只读取current authority、Task 4A brief／source／merged reports与current source；没有运行focused／tokenization tests、Ruff、Pyright或任何mutation。
- 未验证真实provider billing、live upstream、4141、production pipeline、Task 5 index cache性能或跨process lifecycle。
- 未验证Task 4B profile／promotion／16／8 checkpoint、Task 4C drift／epoch及Task 5 queue／store orchestration；这些不是本slice的缺失实现。
- `O(samples log samples + total retained prefix entries)`是source必须满足并由结构审查／定向controls支撑的算法边界，不冒充production规模benchmark。
