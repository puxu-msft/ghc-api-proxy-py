# Task 3B design amendment 2

## 身份与范围

本文件只整改[design amendment 1 review](260907-task3b-design-amendment-1-review-grok.md)尚未关闭的`T4A-AM1-01`～`03`。它与[amendment 1](260907-task3b-design-amendment-1.md)共同构成下一次architecture re-review对象，仍不是living behavior authority；0 Blocker／Major前不改Spec／plan／source。

绑定输入：amendment 1 SHA-256 `97b9964e6ccb02b1436962cb01756fcc323e042877aa231c913220390ae28670`。本轮保留其current-identity-only原则，但只在rollover能释放pre-existing state时执行；零收益global-cap场景改为typed capacity rejection。

## 1．Capacity planner的完整分支

### 1.1 Store outcome是独立第二事实

Prefix checkpoint logical command与store实际结果分槽。`LearningUpdate.prefix_checkpoint_command`仍是required logical input；store在stamp、capacity planning及commit后产生required typed outcome，放入final `TokenLearningObservation`：

```python
@dataclass(frozen=True, slots=True)
class PrefixCheckpointNoChange:
    pass

@dataclass(frozen=True, slots=True)
class PrefixCheckpointApplied:
    profile_key: ProfileKey
    state_revision: int
    updated_order: int

@dataclass(frozen=True, slots=True)
class PrefixCheckpointDeleted:
    profile_key: ProfileKey
    prior_state_revision: int

@dataclass(frozen=True, slots=True)
class PrefixCheckpointCapacityRejected:
    profile_key: ProfileKey
    per_identity_limit: int
    global_limit: int
    prior_identity_rows: int
    prior_global_rows: int

@dataclass(frozen=True, slots=True)
class PrefixCheckpointCapacityRolledOver:
    transition: CapacityEpochTransition

type PrefixCheckpointStoreOutcome = (
    PrefixCheckpointNoChange
    | PrefixCheckpointApplied
    | PrefixCheckpointDeleted
    | PrefixCheckpointCapacityRejected
    | PrefixCheckpointCapacityRolledOver
)
```

`TokenLearningObservation.prefix_checkpoint_outcome`为required，不与sample committed／duplicate／failure主outcome互相吞掉；一次sample可以同时“committed”且“checkpoint capacity rejected”。Store outcome由最终durable state构造，不由policy预测。Duplicate／rejected sample不调用policy，其outcome使用closed not-applied variant或由其自身observation constructor明确禁止checkpoint fields；具体variant cardinality在living authority中固定，不能用free text。

`CapacityEpochTransition`不进入`DriftObservation`。Capacity rolled-over outcome与`observation.drift`互斥；capacity-rejected也只在logical replace因cap未应用时出现。

### 1.2 计数定义

Store在应用provisional command前记录：

```text
prior_current_identity_checkpoint_rows
prior_global_active_checkpoint_rows
```

Inactive rows先按amendment 1的deterministic order删除，不计入active caps。Provisional command最多造成一个active-row净增量：

- NoChange：0。
- Replace existing：0。
- Replace implicit／missing row：+1。
- Delete：-1。

起始state必须在caps内；否则startup／transaction validation fail-visible，不在正常planner中修补既有corruption。

### 1.3 分支顺序

应用logical command形成provisional active state后，按以下唯一顺序：

1. 未超过任何cap：保留command，store outcome为Applied／Deleted／NoChange。
2. Per-identity cap超限：`prior_current_identity_checkpoint_rows >= per_identity_limit`必然成立；执行current-identity rollover。
3. 仅global cap超限且`prior_current_identity_checkpoint_rows > 0`：执行current-identity rollover，删除其old-active rows会释放至少一条pre-existing global容量。
4. 仅global cap超限且`prior_current_identity_checkpoint_rows == 0`：撤销本次provisional checkpoint row，**不**rollover、**不**改active epoch；sample／record／evaluations／anchors照常提交，store outcome为`PrefixCheckpointCapacityRejected`。Existing global demoted rows不删除，current identity history不重置。

第四分支可能让current identity在global cap持续饱和时无法建立首条checkpoint；这是有界资源下显式、可观察的learning degradation，不冒充成功，也不false-recover任何已存demoted profile。未来inactive cleanup或其它identity正常epoch transition释放global row后，后续sample可再次尝试。

因此拒绝新checkpoint不是正常首选retention，而是严格限定于“rollover只能删除刚插入row、不能释放pre-existing state”的零收益分支。Amendment 1对无条件reject-new的否决改为这一限定版本。

### 1.4 Rollover收益与终止证明

Rollover只在current identity prior rows大于0时执行，删除其old-active epoch全部checkpoint rows至少释放一条pre-existing row；本次provisional row也删除。一次transaction最多新增一row，所以删除后per-identity与global counts都严格不超过起始counts，必在cap内。Planner不循环、不选择identity B。

Current sample、record和capacity logical command均基于old epoch E，且capacity path把sample facts保留在E；E checkpoint rows最终全删，E标inactive，E+1为空且从下一次prediction active。Current event关联E sample，checkpoint outcome为CapacityRolledOver，transition identity的learning epoch、previous epoch及observation sample epoch均为E；new epoch严格E+1，commit后active epoch为E+1。任一不一致使transition／event validation失败。

### 1.5 Statistical drift优先分支

Future Task 4C drift保持现行store合同：

- PredictionRecord及candidate identities声明prediction epoch E。
- 触发drift的`StoredSample.identity.learning_epoch == drift.new_epoch == E+1`；该label作为new epoch首个sample／exact anchor。
- `LearningUpdate.drift is not None`时，`prefix_checkpoint_command`必须逐字为`NoPrefixCheckpointChange()`；replace／delete与drift并存是invalid transition，rollback且fail-visible。
- Store清除E active checkpoints，E+1从implicit eligible empty开始；old-E checkpoint evidence绝不搬到E+1。
- Capacity planner在drift transition后的E+1 active checkpoint state计数。由于command为NoChange且new epoch empty，本sample不能新增checkpoint，不产生capacity rejection或rollover。
- Final observation保留drift，`prefix_checkpoint_outcome=PrefixCheckpointNoChange`；不得同时携capacity transition。

如果future policy需要在drift sample上立刻积累new-epoch checkpoint evidence，必须在E+1 snapshot上重新predict／evaluate的新事务中进行，不能把old-E command重标。

### 1.6 必须判否的controls

- Global-at-cap、current prior rows=0、Replace missing：sample仍在同一active epoch提交；checkpoint row未创建；typed capacity rejection存在；anchors／profile history不被reset；next prediction仍使用原epoch。
- 同状态错误rollover mutation：必须因epoch／history变化断言红。
- Global-at-cap、current prior rows>0：rollover current identity，删除至少一条pre-existing row，current sample留E，next snapshot为E+1且counts恢复。
- Per-identity-at-cap：同样rollover且终止。
- Drift＋Replace／Delete command：transition validation fail-visible并rollback，DB bytes／revision不变。
- Drift＋NoChange：sample进E+1，record prediction epoch E，E checkpoints清除，只有drift、没有capacity transition／rejection。

## 2．FixedContext exact framing与V1 codec

`FixedContextContribution.framing_tokens`必须满足：

```text
type is int and not bool
framing_tokens >= 0
framing_tokens % 4 == 0
```

因为`framing-v1`的instructions container、tools container及每tool declaration都只贡献4；任意2、6等非4倍数无法由合法producer产生，即使whole conservation凑得上也属于corruption。

V1新增`fixed_context_contribution_json TEXT NOT NULL`，canonical positional shape严格为：

```json
[visible_tokens,framing_tokens,prior_residual_tokens]
```

Decoder要求恰好3位置、visible／framing nonnegative non-bool int、framing为4倍数、prior finite signed number；构造DTO后再与items／whole known、components及whole prior执行exact conservation。Wrong arity、2-token framing、bool、non-finite residual、missing column／CHECK／DDL digest分别有independent corruption controls。

不拆成三列：该record与input-item positional tuple同属一次sample feature snapshot，只按sample整体读取；compact JSON减少DDL列面，且exact shape／manifest已足以认证。Test expected必须是手写literal，不从production encoder生成。

## 3．`PrefixPairIndex`复杂度与availability

采用review建议的排序路线，不要求`LearningSnapshot.samples`改变全局tuple order。

Pure builder步骤：

1. 验证所有committed samples的`committed_order`为positive且unique；pending／duplicate order是invalid snapshot。
2. 以`(committed_order, process_boot_id UTF-8 bytes, request_id UTF-8 bytes, numeric attempt_index)`ascending排序samples。Committed order在单-sample transaction下应已唯一，sample key仍作为defensive deterministic tie。
3. 单向遍历。处理一个longer之前，lookup只含严格较小committed order的bases；因此availability不需要每个longer重复过滤全体samples。
4. 对longer查询same context及其prefix chain可用的best base，再把longer的final prefix identity加入lookup供后续sample使用。
5. Best-base value按较大coverage、较大observed_at_us、sample-key text／numeric ascending比较。

复杂度固定为：

```text
O(samples log samples + total retained prefix entries)
```

Space为`O(total retained prefix entries)`。不再声称未排序输入下严格线性。Task 4B-P pure `PrefixPairIndex`携完整LearningIdentity＋snapshot revision；Task 5 process-local cache以两者为key，revision变化直接丢弃重建；不持久化。

Tests：将snapshot samples故意反序；same timestamp但committed order不同；base commit order等于／大于longer时不可用；remove-sort mutation必须选择future base或错过available base并红。

## 4．Review findings disposition

| Finding | 本修订处置 |
|---|---|
| `T4A-AM1-01` | 零收益global-cap分支typed reject而不rollover；有pre-existing rows才current-identity rollover；drift sample进E+1且command强制NoChange；capacity outcome与drift分槽；完整epoch／event／termination controls。 |
| `T4A-AM1-02` | FixedContext framing固定4倍数；V1 shape固定三位置compact JSON并列出decoder／manifest controls。 |
| `T4A-AM1-03` | Builder先按committed order排序再单向index，复杂度改为`O(samples log samples + total prefix entries)`；reverse-input／future-base controls。 |

## 5．路线记录

采纳：

- Current-identity rollover只在能释放pre-existing state时执行。
- 零收益global cap显式拒绝checkpoint command，但sample正常commit。
- Drift transition强制NoChange，old evidence不跨epoch。
- FixedContext compact三位置JSON。
- PrefixPairIndex显式排序，不依赖snapshot tuple order。

不采纳：

- Global cap每次都rollover current identity，包括prior rows=0。
- 把capacity rejection冒充sample rejection或静默NoChange。
- Drift与checkpoint replace／delete并存。
- Old-E command迁移到E+1。
- FixedContext framing只检查非负。
- 未排序snapshot上声称linear pair index。

这些是design-level处置；下一步仍是原architecture reviewer限定复核。达到0 Blocker／Major后才写living authority，随后authority自身再做独立review。
