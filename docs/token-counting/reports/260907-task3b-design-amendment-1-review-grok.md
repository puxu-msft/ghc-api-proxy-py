受只读约束，未创建请求的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-1-review-grok.md`。以下为完整报告。

# Task 3B design amendment 1 限定复审

## 评审范围

- 原评审：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-prerequisite-design-review-grok.md`
- 唯一被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-1.md`
- Amendment SHA-256首尾均为`97b9964e6ccb02b1436962cb01756fcc323e042877aa231c913220390ae28670`。
- Fixed source：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`，末次HEAD仍为`16a0904496f0af0a7832e4dd4bcb18fdc69919f9`，tracked status为空。
- 直接相邻对象：现行Spec的epoch／drift合同、plan Task 4C、SDD `progress.md`、真实TaskList `#13`／`#14`／`#27`。
- 未重审原design已经接受的suffix baseline、committed order、candidate order、sample count、newest-31等部分。

## 总体 verdict

**NEEDS FIXES**

- Blocker：0
- Major：1
- Minor：2
- open_findings_total：3

原Blocker已经显著收窄，但仍有一个capacity／drift接缝的Major，因此尚不允许authority writeback。

## 原finding处置

| Finding | 当前状态 | 结论 |
|---|---|---|
| `T4A-AR-01` | **OPEN，严重度由Blocker降为Major** | Cross-identity victim、第二identity event／revision／cache及非total-order问题已关闭；但global cap饱和时的零收益反复rollover，以及statistical drift与logical checkpoint command的epoch关系仍未闭合。 |
| `T4A-AR-02` | **ADDRESSED** | Required logical command、explicit NoChange、expected prior revision、store stamping与stamp-after-encode顺序均已唯一确定。 |
| `T4A-AR-03` | **ADDRESSED** | Fixed context与非重叠item contribution建立exact arithmetic conservation，whole visual由items唯一重建，直接shape tests覆盖原反例族。 |
| `T4A-AR-04` | **ADDRESSED** | 真实TaskList、SDD task table及overlap scan已接入4B-P；`PrefixPairIndex`的owner与非持久化边界已明确。仍有一个复杂度表述Minor。 |
| `T4A-AR-05` | **ADDRESSED** | Canonical ProfileKey JSON BINARY成为实际identity，hash仅作普通索引，collision两row共存合同明确。 |

## Major

### T4A-AM1-01：current-identity-only rollover在global cap饱和时可能反复清空history，且drift branch没有唯一checkpoint-command epoch

- `severity`：Major
- `maps_to_original`：`T4A-AR-01`
- `primary_location`：amendment `§1.1～§1.4:14-82`
- `related_locations`：amendment `:91-92`、`:136-152`、`:267-273`；fixed source `learning_store.py:4487-4522`；现行Spec `§9:487-491`
- `classification`：必须补充capacity behavior和Task 4C precedence；不是internal name问题。

#### 反例一：global cap已满且当前identity原有checkpoint为0

初始active checkpoint global count为32,768，identity A在epoch E尚无checkpoint。A第一次产生`ReplacePrefixCheckpoint`：

1. Provisional insert使count成为32,769。
2. Current-identity rollover只删除A刚插入的这一row。
3. Count回到32,768，没有释放任何既有容量。
4. A的current sample仍归E，下一次prediction进入empty E+1，全部A的active exact／prefix／profile history退出使用。
5. A以后每次重新积累到能产生首条checkpoint evidence时，都会再次发生同一rollover。

每个事务会终止，但系统不会为A获得一条active checkpoint；与单纯拒绝本次checkpoint command相比，它取得相同的“无checkpoint进展”，却额外反复丢弃A的全部active anchors和profile history。Amendment `:92`以“拒绝会持续无法精进”为由否决reject-new，但在这个状态下rollover同样无法精进，因此该理由不成立。

#### 反例二：同一sample触发Task 4C drift

现有store合同要求drift时`sample.identity.learning_epoch == drift.new_epoch`，而PredictionRecord仍基于old snapshot。Amendment `:27-36`规定capacity路径的current sample／checkpoint command归E，`:38`又规定drift优先，但没有决定old-E policy产生的logical checkpoint command怎么办：

- 若应用到E+1，它把old-epoch champion evidence带入new epoch，破坏epoch isolation。
- 若应用到E，再由drift清除，它是无意义写入，但语义可闭合。
- 若policy必须在drift时返回`NoPrefixCheckpointChange`，则最简单，但amendment没有该不变量。
- `TokenLearningObservation.capacity_transition`与`drift`互斥只解决了event carrier，没解决sample和command各自属于哪个epoch。

#### 最小修法

1. Capacity planner在provisional insert前记录`prior_current_identity_checkpoint_rows`。
2. Global cap超限且该值为0时，不执行无收益rollover：拒绝本次checkpoint command、保持sample和current epoch正常提交，并以closed typed capacity outcome记录“checkpoint未应用”。它不删除任何demoted row，也不false-recover。
3. Per-identity cap超限，或global cap超限且current identity确有至少一条pre-existing checkpoint时，才执行current-identity rollover；这样删除old-active rows会释放至少一条**既有**容量，而非只撤掉provisional row。
4. 明确Task 4C优先分支：
   - drift sample按现行合同存入E+1；
   - PredictionRecord仍声明prediction epoch E；
   - `LearningUpdate.drift is not None`时，`prefix_checkpoint_command`必须为`NoPrefixCheckpointChange()`，否则transition validation失败并rollback；
   - 清除E checkpoints，capacity planner对E+1重新计数，不产生第二transition；
   - event只携drift，`capacity_transition=None`。
5. Capacity carrier补齐跨字段invariants：`capacity_transition.identity.learning_epoch == previous_epoch`、`new_epoch == previous_epoch + 1`、observation的sample／learning epoch为E、commit后active epoch为E+1。
6. Acceptance增加两个直接controls：
   - global-at-cap＋current-prior-rows-0：sample保留在active epoch、checkpoint command明确未应用、无epoch rollover；
   - drift＋non-NoChange command：必须fail-visible并rollback，正确NoChange路径只产生一个drift transition。

#### 路线处置

- 保留：current-identity-only rollover，适用于它确实会释放pre-existing current-identity state的情况。
- 采纳为必要降级：零收益场景拒绝checkpoint command而不rollover。
- 否决：在global cap满时仅删除刚插入的row后仍重置整个identity；把old-E checkpoint evidence带入drift-created E+1。
- Amendment已经不再宣称rollover是数学上的唯一方案；对ELIGIBLE eviction和reject-new的限制说明本身不过度。问题只在于reject-new尚未被路由到它明显支配rollover的零收益状态。

## Minor

### T4A-AM1-02：FixedContext framing仍可接受非`framing-v1`整数，persistent codec位置未固定

- `severity`：Minor
- `primary_location`：amendment `§3.1:158-198`
- `related_locations`：amendment `§3.3:206-216`

Item framing和nested framing都固定为4及4的倍数，但`FixedContextContribution.framing_tokens`只受“非负integer”约束。`FixedContextContribution(visible_tokens=6, framing_tokens=2, prior_residual_tokens=0.0)`可与whole known total保持exact equality，却不可能由instructions／tools的`framing-v1`产生。

此外，amendment固定了item contribution的五位置JSON，却没有固定`FixedContextContribution`如何进入V1 row／codec。V1 manifest authenticity要求该事实只有一个canonical representation。

**最小修法**

- 增加`fixed_context.framing_tokens % 4 == 0`。
- 固定一个compact persistent shape，例如`[visible_tokens,framing_tokens,prior_residual_tokens]`，或三个具名sample columns；选择其一并同步manifest、decoder和corruption controls。
- 保留per-shape producer tests。Exact conservation能证明算术闭合，不能单独证明payload owner attribution；amendment已有独立accumulator与直接shape tests，因此不需要恢复raw payload persistence。

### T4A-AM1-03：`PrefixPairIndex`的线性复杂度需要committed-order traversal前提

- `severity`：Minor
- `primary_location`：amendment `§5:260-265`
- `related_locations`：fixed source当前`LearningSnapshot.samples`投影按observation newest order，而不是committed order。

要在每个longer的prequential边界只使用`base.committed_order < longer.committed_order`，单次遍历必须按`committed_order`递增处理samples，并在处理longer前只让已提交bases进入lookup。当前snapshot tuple没有这个顺序保证。若先按当前tuple构建全部bucket，再为每个longer过滤available base，线性复杂度并不自动成立；通常需要排序、二分或重复扫描。

**最小修法**

选择并写死一种：

1. Builder先按`committed_order`排序，再单向构建prefix-best lookup，复杂度写成`O(samples log samples + total retained prefix entries)`；或
2. Task 3B保证供builder使用的输入序列按`committed_order`严格递增，从而维持amendment所称线性复杂度。

Cache owner与边界已经闭合：Task 4B-P拥有pure builder／index类型，Task 5以后拥有process-local cache，以完整LearningIdentity＋snapshot revision失效，不进入SQLite或LearningSnapshot。

## 已核对通过的相邻接缝

### AR02 logical command／store stamping

- `LearningUpdate.prefix_checkpoint_command`为required，无`None`默认。
- `NoPrefixCheckpointChange`不承担CAS。
- Replace的`None`明确表示old row absent；非None严格匹配old `state_revision`。
- Delete要求existing revision。
- Sample及checkpoint由store填post-transition order，policy不伪造。
- Codec／row preparation发生在stamp之后。
- Public snapshot拒绝pending `None`。
- Task 3B可用synthetic commands验store mechanics，Task 4A／4B-P显式NoChange，Task 4B才实现16／8 policy。

这一部分足以实施，`T4A-AR-02`关闭。

### AR03 exact contributions

- Fixed context和item使用非重叠visible／framing字段。
- `known_tokens`由字段派生。
- Whole known采用context＋items exact equality。
- Components总和与同一known total对账。
- Whole prior只派生一次。
- Whole visual只从item tuple重建，None／0不混同。
- Raw string、non-object、message、reasoning、function call／output及media均列入producer tests。
- 788-item prefix digest仍为52,797 bytes，代表性item contribution约11KiB，两个字段各自低于65,536-byte上限，并要求exact round-trip与limit-neighbor controls。

除上述FixedContext framing Minor外，`T4A-AR-03`关闭。

### AR04真实TaskList与SDD tracker

直接读取了：

- `/home/xp/.claude/tasks/4f9bdf9a-5741-47f2-af2c-79b754532c73/13.json`
- `/home/xp/.claude/tasks/4f9bdf9a-5741-47f2-af2c-79b754532c73/14.json`
- `/home/xp/.claude/tasks/4f9bdf9a-5741-47f2-af2c-79b754532c73/27.json`

实际关系为：

- `#27.blockedBy == ["13"]`
- `#27.blocks == ["14"]`
- `#14.blockedBy`同时含`13`和`27`
- `#13.blocks`同时含`14`和`27`

`#13 → #14`是冗余直接边，但不会绕过`#27`，因为`#14`仍被`#27`阻塞。

SDD `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md`已经明确列出：

`Task 3B → Task 4A → Task 4B-P → Task 4B → Task 4C → Task 5`

Overlap scan也写明3B先扩展carrier／store、4A deterministic、4B-P learned prefix、4B profile＋eligibility、4C drift，且历史records不回填。

`T4A-AR-04`关闭。

### AR05 ProfileKey identity

- Logical key使用canonical ProfileKey JSON。
- Column明确`TEXT COLLATE BINARY`并进入PK／UNIQUE。
- Hash仅作普通index narrowing。
- Lookup还要做BINARY JSON equality及decoded object equality。
- Injected same-hash／different-JSON必须允许两row共存。

这精确关闭hash-only identity问题，`T4A-AR-05`关闭。

## 当前处置汇总

- `T4A-AR-01`：OPEN，剩余1 Major。
- `T4A-AR-02`：ADDRESSED。
- `T4A-AR-03`：ADDRESSED。
- `T4A-AR-04`：ADDRESSED。
- `T4A-AR-05`：ADDRESSED。
- New Blocker：0。
- New Major：1。
- New Minor：2。

## 搜索面与证据边界

完整读取了原评审和固定SHA amendment；只读取直接相邻的Spec epoch条款、plan Task 4C、fixed store transition validation、SDD dependency rows及真实TaskList JSON。没有重审原design已接受部分，没有运行broad tests或真实upstream，没有修改source／文档／TaskList。

Amendment首尾SHA一致，fixed source HEAD未移动且无tracked dirt。SDD与TaskList结论是本轮读取时点的当前状态，不冒充未来authority writeback已经完成。

# 最终结论

**NEEDS FIXES**