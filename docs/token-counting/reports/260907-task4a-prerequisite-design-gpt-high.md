# Task 4A learning prerequisite 架构评审与最小设计

## 修订绑定

- `report_id`：`token-counting-task4a-prerequisite-design-gpt-high`
- `attempt_id`：`260907-task4a-prerequisite-design-gpt-high-1`
- Spec SHA-256：`2644ad9a44a9b0b06f072513dfb82834f8512f5b3fc6272a435b45a8a8445834`
- Plan SHA-256：`ab7da5a2f0c5c292824ec14f52fbc5657c91fabf5f264428a493042821e3ab68`
- Task 4A brief SHA-256：`35d5db83aac6283255748dead301b38aa6bca7299a516367b7e61b6e10af883d`
- Task 4A brief review SHA-256：`5e5deba9bc0118a1536e3b2c97ac58e485856b0e297bc55a5e0991a50eff2954`
- Stacked source HEAD：`16a0904496f0af0a7832e4dd4bcb18fdc69919f9`
- 最终复算时间：`2026-09-07T17:12:08+00:00`
- 最终复算结果：上述四份输入及stacked HEAD均未移动；stacked worktree无tracked dirt。

## 评审范围

本报告评审 Task 4A 在固定 stacked source 上的可实施前提，并为已确认的visual suffix信息损失、prefix eligibility随sample prune丢失，以及brief review其余findings提出最小闭合设计。

Behavior authority是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`；implementation authority是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`。被检source是 `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py`、`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/features.py`、`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_schema.py`、`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py`及其相邻tests。

明确不在范围内：修改任何source／Spec／plan／status；实现Task 4A／4B；shared pipeline wiring；真实upstream计费公式；Task 8 production image resize／limit capability；重新验收Task 3／3A的完整SQLite cancellation与并发合同。

## 总体判定

**当前产物 verdict：NEEDS FIX。Blocker：2。**

Task 4A仍不可按现brief派implementer。两个Blocker所缺的信息和状态均不在Task 4A的四个owned files内。

**本 prerequisite 设计：DESIGN READY。**

本报告给出的Task 3B carrier／store、Task 4A deterministic core、Task 4B-P learned prefix及Task 4B profile／eligibility分片已经闭合当前已知分叉，不缺新的用户裁决。必须先把behavior-level选择写入living Spec、同步plan和transcription map，并完成独立authority review，再修改source。

有效findings共3项：2 Blocker、1 Major、0 Minor、0 Nit。

## Findings

### token-counting-task4a-prerequisite-design-gpt-high-01

- `finding_id`：`token-counting-task4a-prerequisite-design-gpt-high-01`
- `severity`：`blocker`
- `primary_location`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py:165-204`；`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/features.py:295-357`
- `related_locations`：Spec §4.1～§4.2、§6.2；Task 4A brief §4～§5.1；brief review `T4A-BR-01`
- `evidence`：`EstimateFeatures`只保存whole-request `capability_visual_tokens`。`_Analysis.capability_visual_tokens()`遇到任一缺公式、非image或缺dimensions的media便返回`None`。实跑确认：旧prefix仅含缺`height`的image，append完整56×84 image后，source和query的visual均为`None`，而prefix lengths为1／2、known为4／8；新item应独立贡献6 visual tokens。
- `impact`：Task 4A若用whole-request差分，会漏算合法append suffix；历史suffix evidence也会学习错误baseline。Task 4A无法恢复feature extraction已经丢弃的信息。
- `recommendation`：Task 3B先新增与prefix chain逐项对齐的immutable per-input-item deterministic contribution，并持久化、pickle和SQLite round-trip；Task 4A按selected anchor的`item_count`直接切片求suffix，不做whole-request相减。
- `conclusion_strength`：`confirmed`。Source、DTO和固定反例一致，足以阻断实施。

### token-counting-task4a-prerequisite-design-gpt-high-02

- `finding_id`：`token-counting-task4a-prerequisite-design-gpt-high-02`
- `severity`：`blocker`
- `primary_location`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py:663-718`、`:833-889`；`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_schema.py:154-229`；`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py:2555-2635`
- `related_locations`：Spec §6.2、§7.3、§8.2～§8.5；brief review `T4A-BR-02`
- `evidence`：点时prefix eligibility只存在于`PredictionRecord.method_champions`；sample被prune时，FK cascade删除record和evaluation。Schema、`LearningSnapshot`和store均没有以`(identity, epoch, ProfileKey)`为键的独立checkpoint。触发demotion的第16条record仍记录label到达前的eligible状态，不能充当事后checkpoint。
- `impact`：16条evidence完成demotion后若其samples被容量淘汰，restart／replay会从implicit eligible重启；这违反“只有latest-8 recovery或new epoch才能恢复”的状态机。
- `recommendation`：Task 3B新增独立于sample FK的bounded `PrefixEligibilityCheckpoint`及store transaction carrier；Task 4B中的pure learning policy在evaluate后产生typed checkpoint update，store与sample同事务应用。
- `conclusion_strength`：`confirmed`。现有关系图无法表达所需持久状态，足以阻断实施。

### token-counting-task4a-prerequisite-design-gpt-high-03

- `finding_id`：`token-counting-task4a-prerequisite-design-gpt-high-03`
- `severity`：`major`
- `primary_location`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py:80-83`、`:4541-4587`、`:5039-5056`
- `related_locations`：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py:194-197`；`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_schema.py:119-153`；plan所述788-item motivating request
- `evidence`：当前`prefix_fingerprints_json`把每项编码为含`item_count`和64-byte hex digest的object，并对每个JSON字段施加65,536-byte上限。对788项按当前canonical shape复算得到74,753 bytes；仅保存按位置对齐的digest array为52,797 bytes。
- `impact`：即使per-item算术正确，motivating workload仍会在`_encode_sample()`失败，无法形成history anchor。再增加verbose per-item objects会扩大同一失效面。
- `recommendation`：Task 3B把prefix chain和item contributions改为versioned compact positional JSON，`item_count`由tuple index恢复；保留65,536-byte fail-visible bound，不用简单放大上限掩盖冗余。增加788-item round-trip regression。
- `conclusion_strength`：`confirmed`。长度由固定digest长度、当前JSON shape和当前byte limit决定。

## 1．Per-input-item deterministic contribution

### 1.1 推荐DTO

在`EstimateFeatures`新增：

```python
@dataclass(frozen=True, slots=True)
class InputItemContribution:
    known_tokens: int
    item_framing_tokens: int
    nested_framing_tokens: int
    capability_visual_tokens: int | None
    prior_residual_tokens: float
```

并新增字段：

```python
input_item_contributions: tuple[InputItemContribution, ...]
```

各字段语义如下。

- `known_tokens`包含该top-level input item内的visible／tokenizable text，以及该item的item framing和所有nested-part framing。
- `item_framing_tokens`在`framing-v1`中严格为4。单列它是为了让suffix测试能判别“漏掉整个item framing”。
- `nested_framing_tokens`是该item内structured content／summary／function-output parts的framing和，`framing-v1`下必须是4的非负倍数。
- `known_tokens - item_framing_tokens - nested_framing_tokens`必须非负；它就是该item的visible text contribution，无需再持久化一个冗余字段。
- `capability_visual_tokens=None`表示该item内至少一个适用media缺公式或所需metadata；deterministic suffix对该item取0，但别的appended items仍可贡献自己的known visual值。
- `capability_visual_tokens=0`表示visual贡献已知且为0，包括没有适用visual carrier的ordinary item。它与`None`不同。
- `capability_visual_tokens>0`表示该item的per-item formula结果。
- `prior_residual_tokens`是只由该item局部features和当前released prior revision得到的finite、未量化值。V1为0；未来允许finite signed值，但改变公式或coefficient必须提升estimator generation。

本切片保留现有whole-request `EstimateFeatures.capability_visual_tokens`作为兼容aggregate：只要任一item为`None`，aggregate仍为`None`；否则等于所有item visual值之和。Full cold-start继续按现Spec把whole-request `None`视为0。本设计只修复suffix的prefix alignment，不擅自改变full cold-start的既有all-or-none行为。

### 1.2 对齐不变量

- `len(input_item_contributions) == len(prefix_fingerprints)`。
- 第`i`个contribution对应`prefix_fingerprints[i]`，其`item_count == i + 1`。
- 空input同时产生两个空tuple。
- `sum(item.known_tokens) <= EstimateFeatures.known_tokens`；差值是top-level instructions／tools等固定context的known contribution。
- Whole-request visual aggregate必须由item tuple按上述规则重建；持久化值与重建值不一致属于corruption。
- Tuple顺序就是canonical input order，不另存重复且可能失配的`item_index`。
- DTO不保存raw item、media body、unknown text或capability object。

### 1.3 精确suffix算法

选定prefix anchor后，以其`item_count`直接切片：

```text
appended = query.input_item_contributions[anchor.item_count:]
suffix_baseline_delta =
    Σ(
        item.known_tokens
        + (item.capability_visual_tokens if present else 0)
        + item.prior_residual_tokens
    )
prefix_deterministic =
    anchor.actual_tokens + suffix_baseline_delta
```

这条算法不读取source aggregate contribution，也不执行query-minus-source subtraction。因此：

- `None→None但new item present`仍能从new item取得6。
- `0→present`只加入new item值。
- `present→present`只加入append部分，不double count旧visual。
- `present→None`只让新缺metadata item的visual取0；不会从whole-request差分得到负数或抹掉旧anchor actual。
- Top-level instructions／tools不在slice中，不会重复计入。
- Historical longer sample也从`longer.input_item_contributions[base_item_count:]`重建自己的完整`suffix_baseline_delta`。

### 1.4 Canonicalization、pickle与SQLite JSON

采用frozen／slots dataclass和tuple，标准pickle应严格round-trip。新增worker测试必须通过真正的process pickle boundary，不只在同进程调用`pickle.dumps()`。

SQLite新增`input_item_contributions_json TEXT NOT NULL`。推荐的V1 codec是固定位置数组：

```json
[[29,4,8,6,0.0],[4,4,0,null,0.0]]
```

每项严格五个位置，分别对应`known_tokens`、`item_framing_tokens`、`nested_framing_tokens`、`capability_visual_tokens`、`prior_residual_tokens`。`null`、`0`和正整数保持不同。Decoder拒绝wrong arity、bool、negative integer、non-finite residual和prefix-length mismatch；decode后重新构造DTO并执行全部invariants。

同一Task 3B应把`prefix_fingerprints_json`收紧为按tuple位置排列的digest array，`item_count`由位置恢复。这样788项从74,753 bytes降为52,797 bytes，避免新增字段之前已经存在的64KiB失败。

采用compact positional JSON而不采用normalized child table，是因为本切片只需要一次按sample整体读取的bounded tuple；child table会增加数百至数千个row、FK、action IDs和cascade路径，却不增加查询能力。若将来需要按item SQL查询，再以新schema version迁移。

## 2．完整deterministic learned-suffix baseline

采纳完整`suffix_baseline_delta`，否决literal known-only delta。

历史pair定义：

```text
actual_delta = longer.actual_input_tokens - base.actual_input_tokens
historical_suffix_baseline_delta =
    Σ(longer.input_item_contributions[base_item_count:])
```

其中每个item都使用`known + visual_or_zero + prior_residual`。

- Additive evidence要求`actual_delta > 0`且`historical_suffix_baseline_delta >= 0`，保存`actual_delta - historical_suffix_baseline_delta`。
- Multiplicative evidence要求`actual_delta > 0`且`historical_suffix_baseline_delta > 0`，保存`log(actual_delta / historical_suffix_baseline_delta)`。
- 两种learned candidate仍分别至少需要3条eligible historical pairs。
- 当前query的`suffix_baseline_delta == 0`时，只要已有至少3条合法historical ratio evidence，`history-prefix/multiplicative`仍然存在，其suffix值严格为`0 * factor == 0`。Candidate availability取决于历史支持，不取决于当前query scalar。
- 删除current-value gate。它会丢失一个数学上有定义且应接受prequential evaluation的candidate。
- Current baseline为0时，`sample_count`仍是historical ratio pair数。
- Full candidate分别为：

```text
prefix_additive =
    selected_anchor.actual_tokens
    + current_suffix_baseline_delta
    + median(actual_delta - historical_suffix_baseline_delta)

prefix_multiplicative =
    selected_anchor.actual_tokens
    + current_suffix_baseline_delta
      * exp(median(log(actual_delta / historical_suffix_baseline_delta)))
```

选择完整baseline的理由是deterministic candidate本来就包含known、visual和released prior。Learned residual／ratio必须校准同一个baseline；若只用known delta，visual／prior会被误当成residual学习，随后又在current deterministic suffix中加入，产生口径漂移或double calibration。

这项选择改变合法candidate集合及数值，必须先修改Spec §4.2、§6.2、A20、transcription map和revision record，不能只改brief。

## 3．Historical base availability与single-base order

### 3.1 采用store-assigned global `committed_order`

推荐给`StoredSample`新增：

```python
committed_order: int | None = None
```

语义严格分成两个阶段。

- 进入`TokenLearningStore.apply_sample()`的pending sample必须为`None`；policy不得伪造commit事实。
- Store在成功sample transaction中把`committed_order`写为该transaction的post-transition `global_revision`。
- SQLite列为`committed_order INTEGER NOT NULL CHECK (committed_order >= 1)`。
- Store投影到`LearningSnapshot.samples`时必须为正整数。
- `committed_order`一经写入永不因anchor use、prune preference或event更新而改变。
- 现有mutable `last_used_order`继续只表示anchor use，不得承担availability。
- `observed_at_us`继续表示观测时间和newest preference，不得承担happened-before证明。

没有采用identity-local `committed_revision`，因为现有store已经拥有唯一的post-commit global revision，而global order能覆盖same timestamp、跨process writer竞争及未来drift sample的prediction epoch差异。只要一次sample transaction只插入一个sample，base在longer的prequential snapshot中可用当且仅当：

```text
base.committed_order < longer.committed_order
```

若未来引入multi-sample transaction，必须改为`(global_revision, batch_ordinal)`，不能让多个sample共享无法排序的order。

### 3.2 Historical pair selection

针对current query，先选择historical longer samples：

- same `LearningIdentity`；
- same active epoch；
- `longer.features.profile_key == current.features.profile_key`；
- longer有完整record与actual；
- base严格更短，same context，且base final prefix fingerprint等于longer chain在base item count位置的fingerprint；
- `base.committed_order < longer.committed_order`。

多个available bases按与request-side prefix相同的single-base total order选择一个：

1. 较大`item_count`优先。
2. 较大`observed_at_us`优先。
3. `process_boot_id` UTF-8 BINARY ascending。
4. `request_id` UTF-8 BINARY ascending。
5. Numeric `attempt_index` ascending。

Same timestamp不再跳过；`committed_order`证明availability，sample key完成selection tie。日志邻接、strict timestamp和保留全部bases均被否决。

ProfileKey isolation施加在historical longer sample和current query之间。Base不是neighbor sample，不要求与longer具有相同ProfileKey；否则append首次引入image、function call或unknown kind时会被错误排除。Base由prefix identity和availability约束。

## 4．Prefix eligibility checkpoint

### 4.1 最小状态

逻辑key严格为`(LearningIdentity base, learning_epoch, ProfileKey)`。SQLite row保存canonical `profile_key_json`和其SHA-256 `profile_key_hash`；lookup必须比较decoded object，不得只信hash。

推荐DTO：

```python
class PrefixEligibilityMode(StrEnum):
    ELIGIBLE = "eligible"
    DEMOTED = "demoted"

@dataclass(frozen=True, slots=True)
class ChampionApe:
    candidate_key: PredictionCandidateKey
    absolute_percentage_error: float

@dataclass(frozen=True, slots=True)
class PrefixChampionErrorTriple:
    committed_order: int
    prefix: ChampionApe
    profile: ChampionApe | None
    cold_start: ChampionApe

@dataclass(frozen=True, slots=True)
class PrefixEligibilityCheckpoint:
    profile_key: ProfileKey
    mode: PrefixEligibilityMode
    evidence: tuple[PrefixChampionErrorTriple, ...]
    state_revision: int
    updated_order: int
```

必要invariants如下。

- `ChampionApe.candidate_key`必须分别属于prefix、profile或cold method，并保存当时record冻结的method champion key，不按当前algorithm重选variant。
- APE必须finite、nonnegative，并只来自`actual > 0`。
- `evidence`按`committed_order`严格递增且无重复。
- `ELIGIBLE`模式最多保存latest 16；每项必须有prefix、profile和cold三方。
- `DEMOTED`模式最多保存latest 8；prefix和cold必须存在，profile允许`None`。
- `state_revision`是目标identity的post-transition revision；`updated_order`是最后一次状态变化或evidence追加的global order。
- 缺少row表示implicit `ELIGIBLE`且空window。
- Recovery成功后删除row，回到implicit eligible empty；这次删除是明确state transition，不是capacity eviction。
- Checkpoint不含raw text、actual body、arbitrary reason或sample FK。其evidence在source sample被prune后仍有效。

### 4.2 Prequential transition

`PredictionRecord`始终记录当前label到来前的eligibility。Policy必须在`evaluate(record, actual)`之后更新checkpoint。

Eligible模式：

1. 当前record必须有prefix、profile和cold的point-in-time champions及其APE。
2. 追加当前triple并保留latest 16。
3. 不足16时保持eligible。
4. 满16且prefix median APE分别严格比profile与cold高`>0.05`时，转`DEMOTED`并清空recovery window。
5. 触发demotion的第16条不得同时进入recovery window。

Demoted模式：

1. Prefix challenger和cold alternative必须存在；profile可选。
2. 追加当前triple并保留latest 8。
3. 少于8条保持demoted。
4. 满8条后，cold使用同8条paired errors。Profile只有在同8条全部存在时才成为可比较alternative，避免用更小的非共同batch。
5. `median(prefix) <= min(median(available alternatives))`时恢复，平手恢复；随后删除checkpoint row并从空eligible window重新开始。
6. “8 bad后8 good”必须按latest 8恢复；累计16条是错误实现。

缺prefix、`actual == 0`或不具备当前模式所需paired facts时，不改变mode和window。Profile A的checkpoint绝不能读取或更新Profile B。

### 4.3 Pure policy与store边界

新增closed update union，例如：

```python
type PrefixCheckpointUpdate = (
    KeepPrefixCheckpoint
    | ReplacePrefixCheckpoint
    | DeleteRecoveredPrefixCheckpoint
)
```

`LearningUpdate`携带这个typed update。`TokenLearningPolicy`负责：

- 从当前record冻结的champions和actual形成error triple；
- 执行16／8窗口、strict threshold和recovery判断；
- 产生replace／delete／no-op；
- 必要时产生typed epoch transition intent。

`TokenLearningStore`只负责：

- 在transaction-fresh `LearningSnapshot`上调用pure policy；
- 验证update的identity、epoch、ProfileKey、revision与旧checkpoint匹配；
- 执行UPSERT／DELETE；
- 执行pure retention plan；
- 在同一sample transaction提交sample、record、evaluations、anchors、checkpoint、revisions和event；
- rollback时sample与checkpoint一起不生效；
- duplicate sample不调用policy，也不更新checkpoint；
- sample cascade prune不删除active checkpoint；
- snapshot只投影requested active identity／epoch的bounded checkpoints。

建议的write order为：

1. Duplicate check与transaction-fresh snapshot。
2. Pure prediction／evaluation／learning transition，得到sample update和checkpoint update。
3. Pure checkpoint retention plan。
4. Insert／update sample、record、evaluations、anchors和checkpoint。
5. 计算sample／checkpoint victims与全部affected identities。
6. 递增identity和global revisions。
7. Cascade sample prune及inactive checkpoint prune。
8. 写post-transition event。
9. Confirmed COMMIT并发布新snapshot。

Checkpoint SQL引入的`state.prefix-checkpoints-read`、`checkpoint.upsert`、`checkpoint.delete`及capacity epoch transition action必须同步Spec §8.1.1的fixed action IDs、production ledger和test-owned literal。不得绕开confirmed-completion helper。

## 5．Checkpoint bounds与capacity语义

### 5.1 推荐边界

建议Spec固定：

- `4_096 prefix checkpoint profiles per identity／epoch`。
- `32_768 prefix checkpoint rows global`。
- Eligible evidence最多16条。
- Demoted evidence最多8条。
- 每个ProfileKey JSON及evidence JSON继续受固定byte cap。
- Inactive-epoch checkpoint优先按`epoch → updated_order → profile_key_hash`确定性prune。

这两个row caps与既有sample caps同量级，避免另造一个没有参照面的低限值。数字仍属于implementation-derived Spec常量，未来可通过Spec revision调整。

### 5.2 Active state不得逐profile淘汰

Active eligible或demoted checkpoint都不能通过LRU逐行删除。删除eligible window会推迟本应发生的demotion；删除demoted row会制造未经latest-8或epoch transition的自动恢复。两者都是behavior change。

### 5.3 Cap overflow采用显式new epoch

当新增checkpoint会突破per-identity cap时，pure retention policy为该identity产生capacity epoch rollover。旧epoch的anchors、profile statistics及prefix eligibility立即退出active prediction；当前或后续sample从new epoch的implicit eligible empty state、cold-start和新anchors重新开始。

Global cap处理顺序：

1. 先删除不参与active prediction的inactive checkpoint rows。
2. 若仍超限，按现有global identity retention价值顺序选择一个checkpoint-bearing victim identity，并对该identity执行显式capacity epoch rollover；tie至少包含active evidence、confirmed anchor use、prefix coverage、oldest sample／checkpoint order及canonical identity key。
3. 一次pending insert最多造成一个row excess；所选victim至少释放一个active row。
4. 受影响identity和global revision必须递增，cache失效，并产生closed `prefix-checkpoint-capacity` epoch-transition observation。
5. 不得悄悄把一个demoted profile改成eligible。

这种方案的代价是容量压力会让一个identity整体回到cold／new anchors，而非只丢一条profile状态。代价明确、可观察且可恢复；有限存储不可能永久、精确地区分无限多个历史demoted ProfileKeys而又让所有never-seen ProfileKeys保持initial eligible，因此必须选择一种显式reset语义。

### 5.4 其它路线处置

| 路线 | 处置 | 理由 |
|---|---|---|
| 永不删除demoted rows | 否决 | 精确保留状态但row count随distinct ProfileKey无限增长，违反bounded store。 |
| Cap overflow触发new epoch | 采纳 | 唯一同时保持确定上限、不制造silent recovery、又不把unknown profile永久fail-closed的精确方案。 |
| Bounded exact digest set | 否决 | Set满后必须淘汰digest或设置overflow latch；前者制造false recovery，后者把never-seen profile也当demoted。 |
| Bloom／Cuckoo filter | 否决 | False positive会无证据demote，deletion／saturation可能产生false negative；不符合exact eligibility合同。 |
| Fail-closed“所有未跟踪profile均demoted” | 否决 | 虽不false-recover，却违反new ProfileKey initial eligible，并可能长期实质禁用prefix method。 |
| Anchor关联淘汰 | 否决 | Current query profile可复用另一个profile产生的shorter prefix anchor；“该profile没有自己的anchor”不表示状态不可达。只有whole-identity epoch reset才安全。 |
| 按sample cascade删除checkpoint | 否决 | 正是已确认Blocker。 |
| 持久化完整records以避免checkpoint | 否决 | 要么记录无界，要么回到同一prune问题；checkpoint是窗口状态的最小充分统计。 |

## 6．Candidate availability、canonical order与`sample_count`

### 6.1 Candidate construction与global selection分开

`build_prediction_record()`先构造所有当时available candidates，再按method priority选global champion。

即使exact命中，也必须继续寻找严格更短且匹配的prefix anchor，并保存prefix deterministic及当时available learned variants。Global selected仍为exact；request-side decision只携EXACT intent。Prequential record则保留exact、prefix、profile及cold challengers。

这关闭brief review `T4A-BR-03`。不得把“exact selected”转写成“prefix unavailable”。

### 6.2 Canonical tuple order

`PredictionRecord.candidates`必须是下列固定序列的subsequence：

1. `history-exact/median`
2. `history-prefix/deterministic`
3. `history-prefix/additive`
4. `history-prefix/multiplicative`
5. `profile-calibrated/additive`
6. `profile-calibrated/multiplicative`
7. `cold-start/deterministic`

`method_champions`严格按`PredictionMethod` enum order，仅包含represented methods。`evaluate()`按candidate tuple order返回。DTO的`__post_init__`必须直接拒绝顺序错误，不能只靠store encoder重排。

### 6.3 `sample_count`唯一语义

`sample_count`表示该candidate自身使用的历史evidence count，不表示整个request涉及的所有unique source rows。

- `history-exact/median`：exact anchor实际参与median的actual数，范围1～5。
- `history-prefix/deterministic`：1，即selected single-source anchor。
- `history-prefix/additive`：实际参与residual median的eligible historical pairs数，至少3，不额外加anchor的1。
- `history-prefix/multiplicative`：实际参与log-ratio median的eligible historical pairs数，至少3。
- `profile-calibrated/additive`／`multiplicative`：实际参与该variant计算的neighbors数，至少3。
- `cold-start/deterministic`：0。

这种定义保留minimum-3的直读性，也让deterministic prefix明确反映它使用了一个history anchor。

## 7．Newest-31、latest-8与diagnostic absence

Prefix variant champion必须从`PredictionRecord.candidates`和对应`StoredSample.actual_input_tokens`重建APE，不得读取`LearningSnapshot.evaluations`作为分母。Diagnostic rows只是bounded projection；record＋actual才是完整prequential fact。

Variant window规则：

- 只取same identity、epoch和current exact `ProfileKey`。
- `actual > 0`。
- 每个record在自己的prequential时点同时包含deterministic及全部当前待比较learned variants。
- 按`observed_at_us` descending，再按sample key UTF-8 BINARY／numeric descending形成canonical newest order。
- 只取newest 31。
- 少于8个共同records时deterministic胜。
- Learned variant必须严格优于deterministic；完全相等时顺序为deterministic、additive、multiplicative。

必要direct controls：

- 63条共同records，其中older 32支持additive，newest 31支持deterministic；删除`[:31]`必须反转结果并判红。
- 8条record＋actual且`LearningSnapshot.evaluations=()`；正确实现仍能选择champion。改为读取diagnostic rows的mutation必须判红。
- Demoted recovery用8 bad随后8 good，只有latest 8决定恢复。
- Profile A有16条demotion evidence、Profile B为空；删除ProfileKey filter必须使B错误demote并判红。

这些是普通针对性tests，不新增gate、manifest、proof control plane或verification state machine。

## 8．Task sequencing

推荐采用比现plan更一致的四段分片。

### Task 3B：carrier与store mechanics

只交付：

- `InputItemContribution`与`EstimateFeatures.input_item_contributions`。
- Compact prefix／contribution codecs。
- `StoredSample.committed_order`及SQLite列／snapshot projection。
- `PrefixEligibilityCheckpoint`、typed checkpoint update、schema／codec／snapshot carrier。
- Checkpoint row／window caps、pure retention plan及capacity epoch transition mechanics。
- Same-transaction apply、restart、prune、rollback、manifest与fixed-action-ID更新。
- 不实现candidate formulas、champion selection或demotion policy。

Owned source应包括：

- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py`
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/features.py`
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_schema.py`
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py`
- 必要时仅为pickle-boundary test调整`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/worker.py`

### Task 4A：deterministic prediction core

只交付：

- Cold-start。
- Exact median。
- Strictly shorter、single-source deterministic prefix。
- All-available candidate construction，即exact selected时仍保留prefix challenger。
- `PredictionRecord`／`evaluate()`。
- Canonical order和`sample_count` invariants。
- 唯一finalization。
- 不实现learned suffix variants、profile或eligibility transition。

### Task 4B-P：learned prefix variants

交付：

- Historical base availability和single-base reconstruction。
- 完整`suffix_baseline_delta`。
- Additive／multiplicative minimum-3。
- Current baseline 0时保留multiplicative candidate。
- Common-batch newest-31 variant champion。
- Record＋actual重建，不依赖diagnostics。
- 仍不demote prefix。

### Task 4B：profile与prefix eligibility

在现有profile task中交付：

- Profile neighbors、candidates和promotion。
- Per-ProfileKey checkpoint update。
- Eligible latest-16 demotion。
- Demoted latest-8 recovery。
- Capacity epoch transition的领域policy。
- Point-in-time champion errors和ProfileKey isolation。

随后Task 4C继续做statistical drift和普通learning epoch。

不建议把learned prefix、profile、promotion、demotion、recovery一次塞入一个Task 4B；这会把三个独立failure surfaces重新绑成一轮大改。也不建议profile先于learned prefix启动demotion，因为后续加入prefix variants会改变method champion语义。上述顺序让prefix champion先稳定，再开始持久eligibility state。

四个`PredictionMethod`及exact → prefix → profile → cold顺序全部保留；没有删除、降级或改名任何用户选择的method／learning mechanism。

## 9．Brief review逐项处置

| Finding | 处置 | 落地 |
|---|---|---|
| `T4A-BR-01` | 采纳 | Task 3B新增per-item contribution；Task 4A按item slice求suffix。 |
| `T4A-BR-02` | 采纳 | Task 3B新增持久checkpoint carrier／store；Task 4B实现policy update。 |
| `T4A-BR-03` | 采纳 | Candidate availability与global selection分开；exact hit仍构造strictly shorter prefix challenger。 |
| `T4A-BR-04` | 采纳并裁定完整baseline | Spec把`known_delta`改为`suffix_baseline_delta`；包含known、visual-or-zero和prior；删除current baseline gate。 |
| `T4A-BR-05` | 采纳并替换timestamp假设 | 新增immutable global `committed_order`；same timestamp可配对；每个longer按canonical total order只选一个available base。 |
| `T4A-BR-06` | 采纳 | Historical longer、variant window及checkpoint都按current exact ProfileKey隔离。 |
| `T4A-BR-07` | 采纳 | Demoted recovery严格使用sliding latest 8，不累计全部post-demotion records。 |
| `T4A-BR-08` | 采纳 | 增加63／31反转fixture及`evaluations=()`负控，直接验证算法数据源。 |
| `T4A-BR-09` | 采纳并固定 | Candidates及champions canonical order；prefix deterministic `sample_count=1`；其余variant count按实际evidence定义。 |

## 10．Behavior authority与internal interface分界

### 必须先修living Spec的behavior authority

- Per-item contribution的语义、prefix alignment及visual `None`／0／present规则。
- `suffix_baseline_delta`包含known、visual和prior。
- Multiplicative candidate在current baseline 0时仍存在。
- Historical base的availability、same-timestamp及single-base total order。
- Historical longer／variant／checkpoint的ProfileKey isolation。
- All-available candidates与exact selection分离。
- Canonical candidate／champion order及每种`sample_count`语义。
- Eligible latest-16、demoted latest-8和evaluate-after-predict checkpoint timing。
- Checkpoint caps、active-row不可单独淘汰及capacity new-epoch语义。
- Sample／checkpoint／revision／event同事务关系。

受影响条款至少包括Spec §1、§4.1～§4.2、§5、§6.0～§6.2、§7.3、§8.1.1、§8.2、§8.4～§8.5、§9、A5、A8、A20、A23、A27、A31、A32-P、A39、§13和§15。

### Internal interface，但仍须同步normative schema／transcription

- DTO具体类名。
- `committed_order`选择optional field还是snapshot wrapper。
- Compact positional JSON的数组位置。
- SQLite table／column／index名称。
- Action-ID spelling和manifest digest。
- Checkpoint evidence采用单JSON row而不是child table。
- Task 4B-P的任务编号。

这些不改变public count wire，但Spec当前已把schema authenticity和fixed action IDs列为内部normative contract，因此仍需同一authority change同步，不能只留在source或报告。

Public wire完全不变：local success继续只有`input_tokens`和`estimated:true`。

## 11．Source与tests影响清单

### Task 3B source

- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py`：新增item contribution、committed order、checkpoint／evidence／update DTO、canonical candidate order与sample-count invariants。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/features.py`：每个top-level input item使用独立accumulator；分别记录item／nested framing、visual tri-state和prior residual。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_schema.py`：sample `committed_order`和`input_item_contributions_json`；prefix checkpoint table、CHECK、FK、index及DDL／manifest digest。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py`：compact codec、checkpoint decode／validation／projection／UPSERT、capacity retention plan、transaction ordering、bounds和action IDs。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/worker.py`：仅在现有worker carrier不能自动pickle新DTO时修改。

### Task 3B tests

- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/tests/unit/tokenization/test_features.py`：四个visual transition cases、tuple alignment、item／nested framing、prior residual、pickle、wrong-length／bool／negative／non-finite rejection。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/tests/unit/tokenization/test_learning_store.py`：compact 788-item round-trip、`committed_order` immutability、checkpoint restart／sample-prune survival、same-transaction rollback、ProfileKey JSON／hash、window caps、row caps、capacity epoch、schema oracle、DDL digest和action-ID literal。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/tests/unit/tokenization/test_local_token_worker.py`：真实process pickle boundary。

### Task 4A及后续tests

- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/tests/unit/tokenization/test_prediction.py`：exact＋shorter prefix同record、deterministic item slicing、canonical order、`sample_count`、same-timestamp base availability、current-zero multiplicative、63／31窗口、diagnostics absence、ProfileKey isolation、latest-16／latest-8。
- `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/tests/unit/tokenization/test_local_estimate_scaling.py`：保持唯一finalization合同，不因Task 3B扩张。

## 12．额外被否路线

| 路线 | 处置理由 |
|---|---|
| 把raw appended items和capability重新传给predictor分析 | 复制feature classifier和formula owner，破坏`TokenEstimator → EstimateFeatures → TokenPredictor`边界；同一payload会有两套analysis。 |
| Whole-request cold difference | `None→None`不可逆，且会重复或漏掉top-level／visual／prior。 |
| Literal known-only learned baseline | 与deterministic candidate口径不同，会把visual／prior学习成residual。 |
| Current baseline 0时删除multiplicative candidate | 历史ratio支持仍存在，`0 * factor`定义良好；删除会改变prequential candidate set。 |
| `observed_at_us < longer.observed_at_us`作为availability | Timestamp不是commit happens-before；same timestamp会误删合法pair。 |
| 保留每个longer的全部prefix bases | 同一longer会被重复计权，并使actual delta取决于base枚举数。 |
| 从`LearningSnapshot.evaluations`读取variant／demotion windows | Diagnostic rows可缺，不是完整事实权威；record＋actual才可重建。 |
| 每次从implicit eligible重放retained records | Sample prune会截断状态历史，已由Blocker反例证伪。 |
| 把checkpoint绑到sample FK | Sample cascade再次删除状态。 |
| Task 4A越界修改types／store | 掩盖prerequisite缺失并破坏semantic slice ownership。 |
| 把全部learned prefix、profile和eligibility合进Task 4A | 扩大Task 4A并重开已审owned-file边界，不是修复。 |

## 搜索面与证据边界

已完整读取固定SHA的Spec、plan、Task 4A brief及brief review；读取stacked source中的DTO、feature analyzer、V1 schema、store state／snapshot／apply／prune／codec，以及相关feature／store tests。CodeGraph未能为该job checkout提供索引，随后使用绝对路径`Read`和限定`rg`。

执行了两个窄探针：

1. Visual反例实跑得到`prefix_visual=None`、`query_visual=None`、prefix lengths 1／2、known 4／8，确认append 56×84 image的6无法由whole-request槽恢复。
2. Current canonical prefix JSON的788-item size复算为74,753 bytes，digest-only positional array为52,797 bytes，当前limit为65,536 bytes。

没有运行broad tests，也没有调用真实upstream；这些证据不证明真实provider计费准确率。Stacked source在探针后仍无tracked dirt。

## 我最没把握的三个判断

1. `4_096 per identity／epoch`和`32_768 global`是与既有sample caps对齐的高置信实现建议，但没有production ProfileKey cardinality测量。它们足以据此实施，因为overflow语义已经闭合；未来测量只能通过living Spec revision调整数值，不能改成silent eviction。
2. 本设计把visual all-or-none边界从whole request缩到top-level input item，没有进一步拆成per-media leaf。它精确关闭当前prefix反例并保留现有full cold语义；若将来要在同一item内同时保留complete image和missing image的partial known subtotal，那是另一个Spec修订，不应暗中混入Task 3B。
3. Global checkpoint cap触发canonical victim identity epoch rollover会牺牲一个可能仍有价值的identity历史；这是有限精确状态下的明确代价。相比false recovery、永久fail-closed或无界rows，它仍是长期正确的默认选择。

## Open blockers与交接

没有缺失的产品事实或用户裁决，因此不是`NEEDS MORE FACTS`。

进入source实施前仍有以下明确门控项：

1. 修改living Spec并追加revision record。
2. 同步plan，插入Task 3B和Task 4B-P，收窄Task 4A。
3. 同步transcription map、fixed action IDs和受影响acceptance rows。
4. 对修改后的Spec／plan做独立review，达到0 Blocker／0 Major。
5. 随后实施并独立review Task 3B。
6. 本报告自身因leaf约束无法派第三方复评；上级会话应安排一轮独立architecture review后再采用。
7. 若实施时发现V1 SQLite已进入任何外部或production lifecycle，不得原地改V1，必须改为新schema version和migration。

## 交付声明

- `delivery_complete`：`true`
- `completed_at`：`2026-09-07T17:12:08+00:00`
- `finding_total`：3
- `blocker`：2
- `major`：1
- `minor`：0
- `nit`：0
- 报告落盘：失败，原因是harness拒绝isolated agent写入shared checkout路径。
- Source／Spec／plan／status修改：0。

# 最终设计结论

**DESIGN READY**