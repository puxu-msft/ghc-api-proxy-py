# Task 3B design amendment 1

## 文档身份与边界

本文件是对[Task 4A prerequisite design](260907-task4a-prerequisite-design-gpt-high.md)及其[独立architecture review](260907-task4a-prerequisite-design-review-grok.md)的点时设计整改，不是living behavior authority。整改达到独立review 0 Blocker／Major后，结论才写入`../spec.md`、`../plan.md`、`../status.md`和SDD tracker；此前不改source。

绑定输入：原design SHA-256 `97c377956de6ce5352fec7317f47424bb47147e172b823e60cc4c0030a3c9c48`，review SHA-256 `c5f5fa356702f8b8bc71befad9cb018da07c6418a2fedbfa02604e817b0d67b2`，stacked source `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`。

本轮关闭`T4A-AR-01`～`05`。保留原design已获review确认的`committed_order`、完整`suffix_baseline_delta`、current-zero multiplicative、historical single-base、16／8 checkpoint充分统计、all-available candidates、canonical candidate／champion order、sample-count、newest31／diagnostic-absence controls及Task 3B／4A／4B-P／4B／4C顺序，但按下列条款消除transaction、conservation和tracker缺口。

## 1．Capacity rollover：只作用于触发超限的当前identity

### 1.1 选择与理由

Checkpoint transaction开始前，持久状态必须满足per-identity／epoch 4,096 rows与global 32,768 rows上限；一个sample transaction最多为其当前identity新增一个checkpoint row。因此一次合法transaction最多造成一row excess。

Global checkpoint cap超限时，不再选择另一个victim identity。唯一victim就是本次sample／checkpoint command所属的当前identity。原因：

- 超限由该identity的新distinct ProfileKey直接触发，causal owner唯一。
- 当前identity至少有刚新增的active checkpoint；rollover并删除其old-active checkpoint rows至少释放一row，一次动作必然恢复per-identity与global上限。
- 不需要让single-identity policy观察全库、选择identity B、写第二个identity event或同时刷新两个unrelated caches。
- 容量代价由制造新增状态的identity承担，不随机牺牲另一个identity的高价值history。

这仍是显式capacity epoch rollover，不是silent row eviction。它会让当前identity从下一次request开始重新cold／new anchors，代价通过typed transition observation可读。

### 1.2 Current sample的唯一epoch语义

当前sample、`PredictionRecord`、evaluations、anchors及logical checkpoint command均基于transaction-fresh old active epoch E的prequential snapshot，全部以E提交，绝不事后重标为E+1，也不重新predict。

Store先对E形成provisional post-update state。若inactive checkpoint cleanup后仍因本次新增row超过任一cap，store在同一transaction执行current-identity capacity rollover：

1. Current sample facts保持在E。
2. 丢弃或删除E的全部prefix checkpoint rows，包括本次provisional update；E已退出active prediction，无需保留窗口。
3. 把E标为inactive，创建E+1 empty epoch并设为该identity active。
4. Existing E samples／records／anchors／profile facts按既有bounded retention保留供offline；它们不参与E+1 prediction。
5. 下一次`LearningSnapshot`只投影E+1，implicit prefix state为eligible empty。
6. 当前sample的durable learning event仍关联E sample，并携带`CapacityEpochTransition(previous_epoch=E, new_epoch=E+1, reason=prefix-checkpoint-capacity)`。

如果同一sample的future Task 4C policy已经产生statistical drift epoch transition，则该transition优先并同样清空old-active checkpoints；容量planner在transition后的active state重新计数，不再叠加第二个capacity transition。一个sample最多产生一个epoch transition。

### 1.3 独立capacity carrier

Capacity不是statistical drift，不塞进`DriftObservation`。新增closed DTO：

```python
class CapacityEpochTransitionReason(StrEnum):
    PREFIX_CHECKPOINT_CAPACITY = "prefix-checkpoint-capacity"

@dataclass(frozen=True, slots=True)
class PrefixCheckpointCapacityMetadata:
    per_identity_limit: int
    global_limit: int
    prior_identity_rows: int
    prior_global_rows: int

@dataclass(frozen=True, slots=True)
class CapacityEpochTransition:
    identity: LearningIdentity
    previous_epoch: int
    new_epoch: int
    reason_code: CapacityEpochTransitionReason
    metadata: PrefixCheckpointCapacityMetadata
```

`TokenLearningObservation`新增`capacity_transition: CapacityEpochTransition | None`，并与现有`drift`互斥；current sample event可以同时表达sample committed和同identity capacity rollover，不需要第二个cross-identity event。Capacity metadata只含bounded integers／closed enums，不含free text。

### 1.4 完整store transaction顺序

Store-private planner拥有完整persistent state与capacity决定；`TokenLearningPolicy`不选择capacity victim。一次sample transaction固定为：

1. Confirmed `BEGIN IMMEDIATE`、duplicate check、读取transaction-fresh private state并投影current identity／epoch snapshot。
2. Pure policy在old snapshot上生成sample candidate／evaluations及logical checkpoint command；不得填写store-owned post revisions。
3. Store计算`next_global_revision = current_global_revision + 1`与current identity的`next_identity_revision`；一次transaction只增加一次global revision。
4. Store把pending sample stamp为`committed_order=next_global_revision`，把logical checkpoint replacement stamp为`state_revision=next_identity_revision`、`updated_order=next_global_revision`，再执行codec／row preparation。
5. Apply current sample rows与logical checkpoint command，形成provisional state。
6. 先按确定性inactive order删除不参与active prediction的checkpoint rows：较小epoch、较小updated_order、canonical ProfileKey JSON BINARY ascending。
7. 核per-identity与global cap。若均满足，无capacity transition。若仍超限，只rollover current identity，删除其E checkpoint rows、创建E+1、更新active epoch并生成capacity transition。
8. 计算affected identity；本设计只有current sample identity，identity revision递增一次、global revision递增一次。若future同事务已有drift transition，仍只递增一次。
9. 按既有sample prune执行cascade；old inactive checkpoint已在步骤6／7删除，不绑sample FK。
10. Store以stamped sample、最终checkpoint／epoch state和可选capacity transition形成final `TokenLearningObservation`，写post-transition event。
11. Confirmed COMMIT；rollback同时撤销sample、checkpoint、epoch、revisions和event。Commit后刷新current identity cache到E或E+1最终active snapshot。

起始state within caps＋最多新增一row＋rollover current identity至少释放一row，证明步骤7最多执行一次且终止。不存在global victim order、identity B revision或第二cache的未定义状态。

### 1.5 不采用路线

| 路线 | 结论 | 理由 |
|---|---|---|
| 跨identity retention-value victim | 否决 | 需要global victim total order、B event／revision／cache与multi-identity observation；没有比causal current-identity reset更强的需求。 |
| 把capacity塞进`DriftObservation` | 否决 | Capacity不是exact／profile statistical drift，破坏closed kind与Task 4C owner。 |
| 事后把current sample重标E+1 | 否决 | Record／evaluation基于E snapshot，会伪造prequential provenance；如要E+1必须重新predict整个transition。 |
| 淘汰ELIGIBLE partial window | 否决为正常cap语义 | 不false-recover demoted state，但会静默延迟latest-16 demotion；只能作为明确store failure降级，不是canonical retention。 |
| Cap满拒绝新checkpoint update | 否决为正常cap语义 | 不恢复旧demoted rows，但使该ProfileKey持续无法精进；queue／store failure可显式走这条降级，正常capacity仍用rollover。 |
| 永不删除或filter／digest近似 | 否决 | 分别无界、false positive／negative或把never-seen profile错误demote。 |

## 2．Logical command与store-stamped persistent facts

### 2.1 Pending sample与public sample

`StoredSample.committed_order: int | None`分两个合法阶段：

- 传入pure policy／`LearningUpdate`的pending sample必须为`None`。
- Store在transaction内以`next_global_revision` stamp后才可encode persistent row。
- `LearningSnapshot.samples`与store-private committed state只接受positive int；任何None是corruption。
- Anchor-use、event-only或prune revision gaps不影响sample strict order；一次sample transaction只插入一个sample。Future batch必须改为`(global_revision, batch_ordinal)`。

Store必须在stamp后调用sample codec；不得像旧flow那样先encode pending sample。

### 2.2 Required checkpoint command union

Policy返回logical command，不返回persistent checkpoint DTO：

```python
@dataclass(frozen=True, slots=True)
class NoPrefixCheckpointChange:
    pass

@dataclass(frozen=True, slots=True)
class ReplacePrefixCheckpoint:
    profile_key: ProfileKey
    mode: PrefixEligibilityMode
    evidence: tuple[PrefixChampionErrorTriple, ...]
    expected_prior_state_revision: int | None

@dataclass(frozen=True, slots=True)
class DeleteRecoveredPrefixCheckpoint:
    profile_key: ProfileKey
    expected_prior_state_revision: int

type PrefixCheckpointCommand = (
    NoPrefixCheckpointChange
    | ReplacePrefixCheckpoint
    | DeleteRecoveredPrefixCheckpoint
)
```

`LearningUpdate.prefix_checkpoint_command`是required field，无永久`None`默认：

- Task 3B synthetic transitions、Task 4A和Task 4B-P必须显式传`NoPrefixCheckpointChange()`。
- Task 4B profile＋eligibility policy才产生replace／delete。
- Missing field应在constructor／typecheck失败，不能让漏接policy静默no-op。

`expected_prior_state_revision=None`只表示implicit eligible／row absent；非None必须严格匹配transaction-fresh old row。Replace／delete mismatch是typed transition rejection并rollback，不覆盖别的process已提交state。`NoPrefixCheckpointChange`单纯表示无logical update，不承担CAS语义。

### 2.3 Store stamping

Persistent `PrefixEligibilityCheckpoint`保存`state_revision`与`updated_order`，但只由store从logical command构造：

- `state_revision=next_identity_revision`。
- `updated_order=next_global_revision`。
- ProfileKey／mode／evidence来自validated command。

Public snapshot拒绝unstamped checkpoint。Store preparation、JSON encode、UPSERT必须发生在stamp后。Task 3B用synthetic commands测试replace／delete／rollback／restart；不提前实现16／8 policy。

## 3．Exact contribution conservation

### 3.1 非重叠DTO

采用两个frozen／slots DTO：

```python
@dataclass(frozen=True, slots=True)
class FixedContextContribution:
    visible_tokens: int
    framing_tokens: int
    prior_residual_tokens: float

    @property
    def known_tokens(self) -> int:
        return self.visible_tokens + self.framing_tokens

@dataclass(frozen=True, slots=True)
class InputItemContribution:
    visible_tokens: int
    item_framing_tokens: int
    nested_framing_tokens: int
    capability_visual_tokens: int | None
    prior_residual_tokens: float

    @property
    def known_tokens(self) -> int:
        return self.visible_tokens + self.item_framing_tokens + self.nested_framing_tokens
```

Invariants：

- Token整数严格`type is int and not bool`且非负。
- `item_framing_tokens == 4`；每个top-level input item恰好一个item framing，包括non-object／opaque／media／unknown。
- `nested_framing_tokens >= 0`且为4的倍数；每个structured content／summary／function-output part恰好一个nested framing。
- Prior residual finite signed；V1为0.0。
- Per-item visual为None／nonnegative int，语义沿用原design。
- Context只含input之外的instructions／tools／tool declarations及其framing，不含任何input item token。
- `len(input_item_contributions) == len(prefix_fingerprints)`，tuple position对应item count。
- `EstimateFeatures.known_tokens == fixed_context_contribution.known_tokens + sum(item.known_tokens for item in input_item_contributions)`，必须exact equality，不用`<=`。
- Existing components仍按kind提供展示／profile facts，但`sum(component.tokens) == known_tokens`；contribution total与component total必须相等，任何一侧漂移是invalid state。
- Whole prior residual若需要full cold，唯一由context prior＋item priors求和，不另存第二份aggregate。
- Whole `capability_visual_tokens`唯一从item tuple重建：任何item visual为None则whole为None，否则sum；persisted aggregate与重建不等即corruption。无input为空sum0。

这让重复nested framing、漏function-output part、把item token算进context或tuple位置错位都无法只靠调整whole total通过。

### 3.2 Feature producer边界

`features.py`按每个top-level input item建立独立item accumulator，再合并到whole components／FeatureVector。每种shape至少逐项区分：raw string，null／number／bool，message scalar／structured content，reasoning summary，function call，function output scalar／list，function-output text＋media，unknown／non-object。Item／nested framing在其owner accumulator只加一次。

Full cold保持current Spec的whole visual all-or-none：任一item None时whole visual项为0并带reason。Prefix suffix获得method-specific information gain：只切appended items，对每项visual independently取value-or-zero；旧prefix item None不抹掉新item已知visual。这不是两份事实，因为whole aggregate必须从item tuple重建。

### 3.3 Compact codec与788-item bound

`prefix_fingerprints_json`改为canonical positional digest array，item count由index＋1恢复；不再保存每项`{"item_count":N,"digest":...}`。`input_item_contributions_json`每项固定五位置：

```json
[visible_tokens,item_framing_tokens,nested_framing_tokens,capability_visual_tokens,prior_residual_tokens]
```

Decoder拒绝wrong arity、bool、negative token、item framing非4、nested framing非4倍数、non-finite prior、invalid visual、tuple length mismatch及whole aggregate不一致。Profile／fingerprint order由tuple position拥有。

两个字段各自继续受65,536-byte固定上限。788个64-hex digest array实测52,797 bytes；代表性contribution array约11KiB。增加motivating 788-item exact round-trip和limit-neighbor controls；不放大上限掩盖旧verbose encoding。

## 4．Checkpoint identity、evidence与schema

### 4.1 Canonical ProfileKey identity

Checkpoint logical key为`(identity_id, epoch, canonical_profile_key_json)`；canonical JSON `TEXT COLLATE BINARY`进入PK／UNIQUE。`profile_key_hash`只作ordinary lookup index narrowing，绝不承担identity。

Lookup先按hash缩小，再以BINARY JSON equality取row，decode后重建`ProfileKey`并逐字段相等。Test-only injected hash collision必须允许same hash／different canonical JSON两row共存且各自读取，不覆盖／误报corruption。Hash-only key与silent overwrite均否决。

### 4.2 Persistent checkpoint与最小窗口

沿用原design的`PrefixEligibilityMode`、`ChampionApe`、`PrefixChampionErrorTriple`与`PrefixEligibilityCheckpoint`，但persistent checkpoint只能由store stamp。Evidence按committed order严格递增。

- ELIGIBLE row：latest最多16条，每条prefix／profile／cold三方都有。
- DEMOTED row：latest最多8条，prefix／cold必有，profile可None。
- Missing row：implicit eligible＋empty。
- Recovery delete：显式transition后回implicit eligible，绝非capacity eviction。
- Checkpoint不绑sample FK；sample prune不删除active checkpoint。

Candidate keys必须是record冻结的point-in-time method champions；APE finite／nonnegative且actual>0。Actual0、缺prefix或缺当前mode所需facts由policy返回NoChange。

### 4.3 Bounds

- 4,096 checkpoint rows per identity／active epoch。
- 32,768 active checkpoint rows global。
- ELIGIBLE evidence最多16；DEMOTED最多8。
- Inactive checkpoint rows不参加prediction，按epoch ascending、updated_order ascending、canonical ProfileKey JSON BINARY ascending在每次relevant transaction先删。
- Active rows不逐profile LRU淘汰；cap overflow按§1只rollover当前identity。

## 5．Task分片与真实tracker

### Task 3B：carrier／store mechanics

Owned source：`types.py`、`features.py`、`learning_schema.py`、`learning_store.py`，仅在process pickle不能自动承载新DTO时改`worker.py`。交付：exact contributions、compact prefix／contribution codecs、pending／committed order、checkpoint persistent DTO与required logical command union、schema／manifest／action IDs、store stamping、replace／delete／rollback／restart、bounds及current-identity capacity rollover。只用synthetic commands，不实现16／8 policy或candidate formulas。

### Task 4A：deterministic prediction core

交付cold、exact median、strict shorter single-source deterministic prefix、all-available exact＋prefix＋cold record、evaluation、canonical order／sample count和唯一finalization。不实现learned suffix、profile或checkpoint transition；每个LearningUpdate显式NoChange。

### Task 4B-P：learned prefix variants

新增真实任务与tracker entry。交付historical availability、single-base reconstruction、完整`suffix_baseline_delta`、additive／multiplicative minimum3、current-zero multiplicative、common-batch newest31 champion及diagnostic-absence controls；仍显式NoChange，不demote。

为避免O(n²)，新增pure revision-bound `PrefixPairIndex`：

- Identity＋snapshot revision是cache key。
- 单次遍历samples和prefix chains构造context／prefix lookup，复杂度O(total retained prefix entries＋samples)。
- Task 4B-P API接收index或由pure builder创建；Task 5以后拥有process-local cache并在revision变化时失效。
- Index不持久化，不进入LearningSnapshot或SQLite。

### Task 4B：profile＋prefix eligibility

现有profile task扩展为profile neighbor／variants／promotion、point-in-time profile champion，以及per-ProfileKey 16／8 checkpoint policy、replace／delete commands和capacity transition领域解释。Task 3B store-private planner仍唯一决定capacity rollover mechanics；Task 4B不选择victimidentity。

### Task 4C：statistical drift

继续拥有profile／exact statistical drift。若同一sample已经触发drift epoch transition，capacity planner不再生成第二transition。Capacity observation不是DriftObservation。

### Required dependency graph

真实顺序固定为：

```text
Task 3B → Task 4A → Task 4B-P → Task 4B → Task 4C → Task 5
```

同一authority change必须更新living plan、status、SDD progress table／overlap scan和task tracker。历史records只保存其prequential时点真实available candidates，不事后回填Task 4B-P／4B variants。

## 6．Suffix与candidate behavior decisions

以下沿用原design并作为authority writeback输入：

1. `suffix_baseline_delta = Σ(appended item known + item visual_or_zero + item prior)`；不用literal known-only或whole request差分。
2. Historical actual delta与同一完整baseline配对。Additive要求actual>0、baseline>=0；multiplicative历史evidence要求actual>0、baseline>0。
3. Current suffix baseline为0时，只要已有至少3条合法ratio evidence，multiplicative candidate仍存在，值为anchor actual＋0；availability不取决于current scalar。
4. Base availability唯一由`base.committed_order < longer.committed_order`证明；observed timestamp只参与newer preference。Same timestamp合法。
5. 每个longer只选一个available base：较大coverage、较大observed_at_us、process／request UTF-8 BINARY ascending、numeric attempt ascending。Base不要求same ProfileKey；historical longer必须与current query exact ProfileKey一致。
6. Candidate construction先于global selection。Exact命中时仍构造strictly shorter available prefix challenger；Task 4B以后同理构造profile challenger。Request decision仍只携selected method intent。
7. Candidate tuple是七pair固定序列的subsequence；method champions按PredictionMethod enum order。`evaluate()`沿candidate tuple order。
8. Sample count：exact=参与median的1～5；prefix deterministic=1；learned prefix／profile=该variant实际evidence数；cold=0。
9. Variant window只读records＋actual，same ProfileKey，actual>0，全部当前variants共同出现；canonical newest31。63 records的older32／newest31反转fixture必须抓移除slice。
10. `LearningSnapshot.evaluations=()`时variant selection仍成立；改读diagnostics的mutation必须红。
11. Eligible demotion只读current ProfileKey latest16 triply-paired method champions，strict双`>0.05`；触发label不进recovery。
12. Demoted recovery只读subsequent sliding latest8；8 bad后8 good按后8恢复，tie恢复；Profile必须在同8条全有才作为alternative。

## 7．Action IDs、events与acceptance

Task 3B新增checkpoint table read／insert-or-update／delete、compact codec读取和capacity epoch state actions；所有raw `aiosqlite` awaits继续走confirmed helper。Spec §8.1.1必须先增fixed semantic bases／expanded IDs，test literal、production ledger和runtime trace三方独立对账；具体ID spelling由authority amendment固定后source照抄。

Acceptance至少覆盖：

- Four visual suffix transitions：None→None＋new present、0→present、present→present、present→None，无漏算／double count。
- Exact contribution conservation across raw／non-object／message parts／reasoning／function outputs／media。
- Compact 788-item fingerprint＋contribution V1 round-trip。
- Pending sample／logical command不能携store-owned future revisions；stamp后public snapshot全为positive order。
- Same-timestamp samples以committed order证明availability。
- Checkpoint survives sample prune／restart；replace／delete CAS、rollback atomically preserve old state。
- Capacity start-at-cap＋one insert只rollover current identity；current sample stays old epoch，next prediction seesE+1；checkpoint rows回到cap内，single capacity observation，revision／cache正确。
- Existing drift transition suppresses second capacity transition。
- Same hash／different ProfileKey JSON rows coexist。
- Tracker顺序3B→4A→4B-P→4B→4C→5。

## 8．Review findings disposition

| Finding | 状态 | 本修订 |
|---|---|---|
| `T4A-AR-01` | addressed in design | 取消cross-identity victim；current identity only，old-epoch current sample，独立capacity carrier，完整single-identity transaction／termination／event／cache语义。 |
| `T4A-AR-02` | addressed in design | Required logical command union与store stamping分离；NoChange显式，pending None不编码，persistent checkpoint only after stamp。 |
| `T4A-AR-03` | addressed in design | Non-overlapping visible／framing fields、FixedContextContribution和exact whole conservation；whole visual由items重建。 |
| `T4A-AR-04` | addressed in design | 明确更新plan／status／SDD／task tracker；新增4B-P与revision-bound PrefixPairIndex。 |
| `T4A-AR-05` | addressed in design | Canonical ProfileKey JSON BINARY是PK identity，hash只作index；injected collision两row共存。 |

## 9．证据边界与下一步

本设计仍未修改Spec／plan／source，也不声称Task 3B实现或真实provider计费已验证。它解决的是已知数据丢失、持久状态和任务顺序合同。

下一步：原architecture reviewer限定复核本文件与原5 findings。只有0 Blocker／Major后，才把本设计写入living Spec／plan／status／tracker并再做authority review。随后Task 3B source从当前stacked integration base开始；如发现V1已外部部署，停止原地V1修订并改用新schema version＋migration。
