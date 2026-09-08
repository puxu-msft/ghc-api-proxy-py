受只读约束，未创建 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-2-review-grok.md`。以下为完整报告。

# Task 3B design amendment 2 限定复审

## 评审范围

- 前轮报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-1-review-grok.md`
- 唯一被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-2.md`
- Amendment 2 SHA-256首尾均为`e0da7530d2c121f3922f5ba8096267ea82ab56f5856021c66224a782a119cc0e`。
- Fixed source：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`，末次HEAD仍为`16a0904496f0af0a7832e4dd4bcb18fdc69919f9`，tracked status为空。
- 本轮只复核`T4A-AM1-01`～`03`、新增checkpoint store outcome与现有`TokenLearningObservation`主outcome矩阵。
- 未重审已经关闭的`T4A-AR-02`～`05`及原design已接受部分。

## 总体 verdict

**NEEDS FIXES**

- Blocker：0
- Major：1
- Minor：0
- open_findings_total：1

Amendment 2已经关闭前轮一个Major和两个Minor，但新增的required checkpoint outcome尚未覆盖duplicate／rejected／failed observations，且capacity transition存在两个可能载体。该接口fork必须在authority writeback前唯一确定。

## 前轮finding终态

| Finding | 状态 | 结论 |
|---|---|---|
| `T4A-AM1-01` | **ADDRESSED** | 四个capacity分支、零收益typed reject、收益型current-identity rollover、current sample epoch、drift precedence、termination及rollback／cache语义均已闭合。 |
| `T4A-AM1-02` | **ADDRESSED** | FixedContext framing固定为4的倍数，三位置V1 codec、decoder、manifest及corruption controls已经唯一确定。 |
| `T4A-AM1-03` | **ADDRESSED** | PrefixPairIndex显式按committed order排序、单向排除future bases，复杂度修正为`O(samples log samples + total retained prefix entries)`。 |

## Major

### T4A-AM2-01：required `prefix_checkpoint_outcome`没有覆盖全部主outcome cardinality，capacity transition仍可能存在两个事实槽

- `severity`：Major
- `primary_location`：amendment 2 `§1.1:10-53`
- `related_locations`：amendment 1 `§1.3:40-65`；fixed source `types.py:935-1012`
- `classification`：DTO union、durable observation codec与cross-field validation；属于internal architecture，但现有Spec把durable observation cardinality作为normative contract，因此必须先写清。

#### 问题一：duplicate／rejected仍留有二选一

Amendment 2规定：

> `TokenLearningObservation.prefix_checkpoint_outcome`为required。

但随后又规定duplicate／rejected sample可以：

1. 使用尚未定义的closed not-applied variant；或
2. 由constructor禁止checkpoint fields。

这两个方案不能同时成立。若字段required，constructor便不能简单禁止字段；若非committed observation不带字段，则该字段不是required。设计把选择留给了后续living authority，而本轮目标正是为authority提供唯一可转录设计。

`PrefixCheckpointNoChange`也不能替代not-applied：

- `NoChange`表示policy确实执行并返回`NoPrefixCheckpointChange()`。
- DB duplicate在duplicate check后直接返回，policy根本没有执行。
- Queue-full、sample-ineligible或missing usage等rejected observations同样没有checkpoint command。
- 把两者编码成同一variant，会丢失“policy no-op”与“未尝试checkpoint”的时序事实。

#### 问题二：failed observations也没有合法结果

现有主outcome包含：

- `committed`
- `duplicate`
- `rejected`
- `failed`

Failed又至少分为：

- analysis／validation阶段即失败，checkpoint从未尝试；
- policy运行后transaction rollback或commit明确失败，logical command曾产生，但没有任何checkpoint durable mutation；
- COMMIT成功后caller收到cancellation，此时主outcome实际上应携已提交结果，而不能标failed。

现有五种`PrefixCheckpointStoreOutcome`都不能准确表达“command曾计算但transaction未commit”。若用`NoChange`，会把rollback伪装成policy no-op；若用`Applied`，会声称不存在的durable mutation。

#### 问题三：capacity transition存在两个潜在authority

Amendment 1给`TokenLearningObservation`新增了独立字段：

```python
capacity_transition: CapacityEpochTransition | None
```

Amendment 2又把transition放进：

```python
PrefixCheckpointCapacityRolledOver(transition)
```

Amendment 2没有明确撤销前一字段。由于两份amendment被声明为共同构成设计，implementer可能保留两个槽；它们可以出现一个缺席、另一个存在，或previous／new epoch不一致。这样同一个capacity transition有两份可漂移的事实来源。

#### 具体反例

1. 已存在sample再次进入`apply_sample()`，DB duplicate check命中。主outcome为`duplicate`，policy未调用。Required checkpoint outcome若缺席则DTO非法；若填`PrefixCheckpointNoChange`则错误声称policy执行了no-op。
2. Policy生成`ReplacePrefixCheckpoint`，sample／checkpoint rows写入后COMMIT明确失败并rollback。主outcome为`failed`；现有union没有“attempted but not committed”variant。
3. Event同时保存standalone `capacity_transition(E→E+1)`和`PrefixCheckpointCapacityRolledOver(transition=E→E+2)`。Amendment没有规定constructor或decoder拒绝该矛盾。

#### 最小修法

固定唯一cardinality matrix，不再给authority writer留二选一。若坚持“第二事实required”，推荐扩展union：

```python
class PrefixCheckpointSkippedReason(StrEnum):
    DUPLICATE_SAMPLE = "duplicate-sample"
    SAMPLE_REJECTED = "sample-rejected"
    FAILURE_BEFORE_POLICY = "failure-before-policy"

@dataclass(frozen=True, slots=True)
class PrefixCheckpointNotAttempted:
    reason: PrefixCheckpointSkippedReason

@dataclass(frozen=True, slots=True)
class PrefixCheckpointNotCommitted:
    pass
```

然后规定：

| Main outcome | 唯一合法checkpoint outcome |
|---|---|
| `committed`／sample仍durable | `NoChange`、`Applied`、`Deleted`、`CapacityRejected`或`CapacityRolledOver`恰一项 |
| `committed`但sample在同事务按既有prune语义移除 | 仍保存该事务最终实际checkpoint outcome，不因sample prune改写 |
| `duplicate` | `NotAttempted(DUPLICATE_SAMPLE)` |
| `rejected` | `NotAttempted(SAMPLE_REJECTED)` |
| `failed`且policy前失败 | `NotAttempted(FAILURE_BEFORE_POLICY)` |
| `failed`且transaction rollback／commit明确失败 | `NotCommitted` |
| post-COMMIT cancellation | 使用已提交主outcome及实际checkpoint outcome，不得降成`failed` |

还需同步以下约束：

1. 明确amendment 1的standalone `TokenLearningObservation.capacity_transition`被删除／取代；`PrefixCheckpointCapacityRolledOver.transition`是唯一capacity transition authority。
2. `CapacityRolledOver`与`drift`互斥；其余checkpoint outcomes不得携capacity transition。
3. `CapacityRejected`只允许主outcome `committed`且logical command是missing-row replace。
4. `Applied`／`Deleted`的ProfileKey必须等于logical command；stamped revisions必须等于final committed revisions。
5. Duplicate／rejected／failed observations不得携Applied／Deleted／CapacityRejected／CapacityRolledOver。
6. Event codec、V1 graph validator和`TokenLearningObservation.__post_init__`按完整矩阵拒绝missing、extra及错variant。
7. 增加每个主outcome的正样本，以及逐项把checkpoint outcome替换成非法variant的negative controls；另加standalone与nested capacity transition不一致的corruption control。

#### 路线处置

- 采纳：checkpoint store outcome作为主sample outcome之外的required second fact。
- 采纳：区分policy no-op、根本未尝试和尝试后未commit。
- 否决：用`PrefixCheckpointNoChange`统包duplicate／rejected／rollback。
- 否决：required字段与“非committed禁止字段”两个方案并存。
- 否决：同时保留standalone `capacity_transition`和nested rolled-over transition。

## 已核对通过的修订

### Capacity四分支与终止

Amendment 2已形成唯一分支：

1. 未超cap：Applied／Deleted／NoChange。
2. Per-identity cap超限：current identity prior rows必为正，执行rollover。
3. 仅global cap超限且current prior rows大于0：执行rollover并释放pre-existing state。
4. 仅global cap超限且current prior rows为0：撤销provisional checkpoint row，typed capacity reject；sample／record／evaluations／anchors照常提交，epoch和history不重置。

起始state在cap内、一次transaction最多净增一row、rollover至少删除一个pre-existing row，因此planner无需循环且结束后两个caps不超过起始值。零收益分支不再反复rollover。

Current-identity rollover中：

- current sample和record属于old E；
- E checkpoints全部删除；
- E samples／records／anchors保留为inactive evidence；
- active epoch变E+1；
- next prediction只看empty E+1；
- identity/global revision各递增一次；
- commit后current identity cache刷新到E+1；
- rollback撤销sample、checkpoint、epoch、revision和event。

除checkpoint outcome全主outcome矩阵尚未闭合外，`T4A-AM1-01`的capacity mechanics已经关闭。

### Drift precedence

Amendment 2明确保持现行store合同：

- PredictionRecord的prediction epoch为E。
- Drift-triggering sample进入E+1并成为new-epoch首个sample／exact anchor。
- Drift存在时logical command必须逐字为`NoPrefixCheckpointChange()`；replace／delete并存直接validation failure并rollback。
- E checkpoints清除，不搬到E+1。
- Capacity planner在E+1计数，本sample不产生capacity rejection或rollover。
- Final observation只有drift，checkpoint store outcome为NoChange。

这关闭了old-E command进入new epoch的反例。

### FixedContext framing与codec

- `framing_tokens`要求strict non-bool int、非负及`% 4 == 0`。
- V1唯一shape为`[visible_tokens,framing_tokens,prior_residual_tokens]`。
- Decoder拒绝arity、bool、negative、非4倍数和non-finite。
- Decode后与items、whole known、components和whole prior执行exact conservation。
- Missing column、CHECK和DDL digest均有独立corruption controls。

`T4A-AM1-02`关闭。

### PrefixPairIndex

- Builder先验证committed order positive且unique。
- Samples按committed order排序，不依赖snapshot tuple order。
- 单向遍历时，处理longer之前lookup只含严格较早的bases。
- Base order等于或大于longer均不可用。
- Best base仍按coverage、observed time、sample key全序选择。
- 复杂度为`O(samples log samples + total retained prefix entries)`，space为`O(total retained prefix entries)`。
- Reverse input、same timestamp、future-base及remove-sort controls已列明。
- Cache以完整identity＋snapshot revision失效，不持久化。

`T4A-AM1-03`关闭。

## 当前处置汇总

- `T4A-AM1-01`：ADDRESSED。
- `T4A-AM1-02`：ADDRESSED。
- `T4A-AM1-03`：ADDRESSED。
- New Blocker：0。
- New Major：1。
- New Minor：0。

## 搜索面与证据边界

完整读取了amendment 1 review及固定SHA amendment 2；只对照了现有`TokenLearningObservation`四种主outcome和直接相邻amendment 1 capacity carrier。没有重审已关闭的AR02～05、原design算法或其它Task，未运行broad tests／真实upstream，未修改source／文档。

Amendment 2首尾SHA一致，fixed source HEAD未移动且无tracked dirt。本报告裁的是architecture cardinality，不声称实现、codec或migration已验证。

# 最终结论

**NEEDS FIXES**