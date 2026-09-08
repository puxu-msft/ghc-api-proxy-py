# Task 3B design amendment 3

## 身份与范围

本文件只整改[design amendment 2 review](260907-task3b-design-amendment-2-review-grok.md)唯一open Major `T4A-AM2-01`。它与amendments 1～2共同构成下一次限定复核对象，仍不是living authority；0 Blocker／Major前不改Spec／plan／source。

绑定input：amendment 2 SHA-256 `e0da7530d2c121f3922f5ba8096267ea82ab56f5856021c66224a782a119cc0e`。Capacity四分支、drift precedence、FixedContext codec及PrefixPairIndex已经review关闭，本轮不重写。

## 1．Required checkpoint outcome完整union

`TokenLearningObservation.prefix_checkpoint_outcome`在所有四种main outcomes上均为required second fact。它不等于main sample outcome，也不允许`None`。

### 1.1 未尝试与未提交

```python
class PrefixCheckpointNotAttemptedReason(StrEnum):
    DUPLICATE_SAMPLE = "duplicate-sample"
    SAMPLE_REJECTED = "sample-rejected"
    FAILURE_BEFORE_POLICY = "failure-before-policy"

@dataclass(frozen=True, slots=True)
class PrefixCheckpointNotAttempted:
    reason: PrefixCheckpointNotAttemptedReason

@dataclass(frozen=True, slots=True)
class PrefixCheckpointNotCommitted:
    pass
```

语义：

- `NotAttempted`表示checkpoint policy根本没有执行。Reason是closed phase category，不复制main reason metadata。
- `NotCommitted`表示policy已经执行并产生logical command，但sample transaction rollback或COMMIT明确失败，没有任何checkpoint durable mutation。
- `PrefixCheckpointNoChange`只表示policy确实执行并显式返回`NoPrefixCheckpointChange()`；它绝不代表duplicate、queue rejection或rollback。

### 1.2 Committed results

沿用amendment 2：

- `PrefixCheckpointNoChange`
- `PrefixCheckpointApplied`
- `PrefixCheckpointDeleted`
- `PrefixCheckpointCapacityRejected`
- `PrefixCheckpointCapacityRolledOver`

`PrefixCheckpointStoreOutcome`是上述五项加`NotAttempted`／`NotCommitted`的closed union。

## 2．Main outcome × checkpoint outcome唯一矩阵

| Main `TokenLearningObservation.outcome` | 唯一合法checkpoint outcome family |
|---|---|
| `committed`，policy执行且sample durable | `NoChange`、`Applied`、`Deleted`、`CapacityRejected`或`CapacityRolledOver`恰一项 |
| `committed`，sample被同事务existing prune语义移除 | 仍保存该transaction最终实际checkpoint result；sample prune不改写checkpoint事实 |
| `duplicate` | 只允许`NotAttempted(DUPLICATE_SAMPLE)` |
| `rejected` | 只允许`NotAttempted(SAMPLE_REJECTED)` |
| `failed`且analysis／validation／startup／queue阶段在policy前失败 | 只允许`NotAttempted(FAILURE_BEFORE_POLICY)` |
| `failed`且policy已执行、transaction rollback或COMMIT明确失败 | 只允许`NotCommitted` |
| post-COMMIT cancellation | Durable observation的main outcome保持`committed`并携实际五种committed result之一；`StoreOperationCancelled.committed_observation`返回它，不得改成failed／NotCommitted |

Main reason code继续拥有具体duplicate／rejection／failure原因；checkpoint reason只表达policy时序，不扩写free text。

## 3．Cross-field invariants

`TokenLearningObservation.__post_init__`、event codec及all-epoch graph必须统一执行：

1. `committed`禁止`NotAttempted`／`NotCommitted`。
2. `duplicate`只接受duplicate NotAttempted。
3. `rejected`只接受sample-rejected NotAttempted。
4. `failed`接受failure-before-policy NotAttempted或NotCommitted；caller／store根据是否已进入policy选择，不能任意互换。
5. Applied／Deleted的ProfileKey逐字段等于logical command；stamped state／order等于final committed revisions。
6. CapacityRejected只允许committed＋missing-row Replace因零收益global cap未应用；它的prior identity rows必须0，prior global rows必须等于global limit，active epoch不变。
7. CapacityRolledOver只允许committed且current identity rollover真实发生；nested transition必须满足amendment 1～2的identity／epoch／count invariants。
8. `observation.drift is not None`时checkpoint outcome必须`NoChange`；CapacityRolledOver与drift互斥。
9. Duplicate／rejected／failed不得携Applied／Deleted／CapacityRejected／CapacityRolledOver。
10. Missing、extra、unknown outcome variant、wrong main pairing、wrong skipped reason或revision mismatch全部invalid state。

## 4．Capacity transition唯一authority

撤销amendment 1提出的standalone：

```python
TokenLearningObservation.capacity_transition
```

该字段不得进入DTO、candidate／event JSON或SQLite schema。唯一capacity transition authority是：

```python
TokenLearningObservation.prefix_checkpoint_outcome
    == PrefixCheckpointCapacityRolledOver(transition=...)
```

其它checkpoint outcomes不能携transition。Event codec只编码一个`prefix_checkpoint_outcome` discriminated object；不另存standalone capacity columns／JSON。V1 raw corruption tests必须覆盖：

- Nested rolled-over transition previous／new epoch不一致。
- Event额外加入standalone capacity transition字段。
- Drift与rolled-over同时存在。
- CapacityRejected却携transition。

## 5．Lifecycle phase mapping

Caller／store在以下确定点选择outcome：

- Duplicate application check命中：policy未调用，duplicate NotAttempted。
- Sample eligibility／missing usage／queue-full在offer或transaction前拒绝：rejected NotAttempted。
- Feature extraction／snapshot validation／startup failure在policy前：failed NotAttempted before-policy。
- Pure policy抛错前是否算attempted，以进入policy callable作为唯一边界：未进入为NotAttempted，进入后任何pre-commit失败为NotCommitted。
- Policy成功返回后，任一insert／checkpoint CAS／revision／event／COMMIT明确失败并rollback：failed NotCommitted。
- COMMIT enqueue后按既有confirmed outcome处理：成功即committed＋actual result，失败且rollback即failed NotCommitted。
- Cancellation遵循相同边界；post-COMMIT cancellation携committed observation。

`NotCommitted`不声称logical command是哪一种，避免把未durable policy internals写入failed event；application warning可按既有边界带bounded exception text，但SQLite durable outcome不含free text。

## 6．Required tests

对每种main outcome至少一个正样本，并为矩阵每类错配提供direct DTO或raw-row negative：

- Committed × five committed results。
- Duplicate × duplicate NotAttempted。
- Rejected × sample-rejected NotAttempted。
- Failed-before-policy × failure-before-policy NotAttempted。
- Failed-after-policy／rollback × NotCommitted。
- Post-COMMIT cancellation × committed actual result。
- Duplicate／rejected／failed误用NoChange／Applied／capacity results。
- Committed误用NotAttempted／NotCommitted。
- Drift＋non-NoChange。
- Extra standalone capacity transition field。

Store orchestration tests用barrier分别在进入policy前、policy callable内、checkpoint write后、COMMIT enqueue后触发failure／cancellation，断言outcome family、rows、revision和event完全一致。不要用同一个helper重复调用冒充不同phase；复用现有confirmed-action injection。

## 7．Finding disposition

`T4A-AM2-01`在设计上addressed：

- Required second fact保持。
- Policy no-op、never attempted、attempted but not committed三种时序不再混同。
- 四种main outcomes有唯一合法matrix。
- Standalone capacity transition明确删除，nested rolled-over outcome为唯一authority。
- Event codec／graph／DTO tests覆盖missing、extra、错variant与drift冲突。

本文件没有新增其它behavior分叉。下一步由原architecture reviewer限定复核本amendment及T4A-AM2-01；0 Blocker／Major后才开始living authority writeback。
