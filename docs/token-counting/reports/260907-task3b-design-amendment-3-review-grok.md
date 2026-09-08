受只读约束，未创建 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-3-review-grok.md`。以下为完整报告。

# Task 3B design amendment 3 限定复审

## 评审范围

- 前轮报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-2-review-grok.md`
- 唯一被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3b-design-amendment-3.md`
- Amendment 3 SHA-256首尾均为`d7ae80f2e1573a51c04763275b5f2559fb56d4f2d01633b26257d5ebeedca15d`。
- Fixed source：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`，末次HEAD仍为`16a0904496f0af0a7832e4dd4bcb18fdc69919f9`，tracked status为空。
- 本轮只复核open `T4A-AM2-01`及直接相邻的observation／failure／cancellation lifecycle。
- 已关闭的capacity mechanics、FixedContext、PrefixPairIndex及AR02～05未重审。

## 总体 verdict

**APPROVED DESIGN**

- Blocker：0
- Major：0
- Minor：1
- open_blocker_or_major：0

Amendment 3已经唯一确定required checkpoint outcome在全部主outcome和lifecycle phases上的cardinality，并撤销standalone capacity transition。允许开始living authority writeback；下述Minor应在转录时一并校正，但不阻止写回。

## 原finding终态

| Finding | 状态 | 结论 |
|---|---|---|
| `T4A-AM2-01` | **ADDRESSED** | Required second fact完整覆盖committed／duplicate／rejected／failed-before-policy／failed-after-policy／post-COMMIT cancellation；standalone capacity transition已撤销；DTO／event codec／graph corruption矩阵闭合。 |

## Minor

### T4A-AM3-01：`NotCommitted`定义中的“产生logical command”与policy-entry唯一边界不一致

- `severity`：Minor
- `primary_location`：amendment 3 `:29-33`
- `related_locations`：amendment 3 `:98-108`

`:32`把`NotCommitted`定义为：

> policy已经执行并产生logical command，但transaction没有commit。

而`:105`又把唯一边界定义为：

> 一旦进入policy callable，之后任何pre-commit失败都使用`NotCommitted`。

若policy callable进入后直接抛错，它没有返回logical command，却按`:105`必须是`NotCommitted`。后者是更完整、可执行的生命周期定义，前一句范围过窄。

**最小修法**

写回authority时将定义改为：

> `PrefixCheckpointNotCommitted`表示policy callable已经开始执行，但sample transaction没有commit；policy可能在返回logical command之前失败，也可能已经返回command后由validation／write／revision／event／COMMIT失败触发rollback。该outcome不持久化未提交command的种类或内容。

并增加“进入policy后、返回command前抛错”的direct control，断言主outcome为`failed`、checkpoint outcome为`NotCommitted`、rows／revision不变。

这不会改变union、matrix或store流程，只修正一个限定语。

## `T4A-AM2-01`逐面核验

### Required union及三种时序不混同

设计现在明确区分：

- `PrefixCheckpointNoChange`：policy确实执行并显式返回`NoPrefixCheckpointChange()`。
- `PrefixCheckpointNotAttempted`：policy callable从未进入。
- `PrefixCheckpointNotCommitted`：policy callable已经进入，但transaction未commit。
- 五种committed results：NoChange／Applied／Deleted／CapacityRejected／CapacityRolledOver。

字段在四种main outcomes上均required且不得为`None`。NoChange不再用于duplicate、rejected或rollback；NotAttempted与NotCommitted由policy callable entry这一可观察边界唯一分开。

除上述一处描述过窄的Minor外，时序模型闭合。

### Main outcome矩阵

矩阵已唯一固定：

| Main outcome／phase | Checkpoint outcome |
|---|---|
| `committed`，policy执行 | 五种committed results恰一项 |
| `committed`，sample被同事务prune | 保留transaction实际checkpoint result，不随sample prune改写 |
| `duplicate` | 仅`NotAttempted(DUPLICATE_SAMPLE)` |
| `rejected` | 仅`NotAttempted(SAMPLE_REJECTED)` |
| `failed`且未进入policy | 仅`NotAttempted(FAILURE_BEFORE_POLICY)` |
| `failed`且已进入policy、未commit | 仅`NotCommitted` |
| post-COMMIT cancellation | Durable observation仍为`committed`并携实际committed result，由`StoreOperationCancelled.committed_observation`返回 |

该矩阵没有未覆盖的main outcome或sample-prune分支。

### Failed phase与cancellation

Policy callable entry被选为唯一boundary，避免依赖“command是否成功构造”这类不可统一观察的内部阶段：

- Duplicate check、eligibility、queue、feature extraction、snapshot validation及startup failure均在policy前，使用NotAttempted。
- Policy内部抛错、update validation、checkpoint CAS、row write、revision、event及pre-commit cancellation均在policy entry后，使用NotCommitted并rollback。
- COMMIT enqueue后等待confirmed outcome：成功使用committed actual result；明确失败并rollback使用NotCommitted。
- Post-COMMIT cancellation不伪装成failed或NotCommitted。

没有发现遗漏的失败／取消phase。

### Capacity reject／rollover cross-fields

- CapacityRejected只允许`committed`、missing-row Replace、零收益global cap分支。
- `prior_identity_rows == 0`、`prior_global_rows == global_limit`、active epoch不变。
- CapacityRolledOver只允许真实current-identity rollover。
- Nested transition必须满足identity epoch／previous epoch／new epoch／count invariants。
- Drift存在时checkpoint outcome必须NoChange；RolledOver与drift互斥。
- Duplicate／rejected／failed不能携Applied／Deleted／CapacityRejected／CapacityRolledOver。
- Applied／Deleted的ProfileKey及stamped revisions必须与logical command和final committed state一致。

Cross-field矩阵完整。

### Capacity transition唯一authority

Amendment 3明确撤销amendment 1提出的：

```python
TokenLearningObservation.capacity_transition
```

唯一载体为：

```python
TokenLearningObservation.prefix_checkpoint_outcome
    == PrefixCheckpointCapacityRolledOver(transition=...)
```

Standalone字段不得进入DTO、candidate／event JSON或SQLite。其它outcome不能携transition。Raw corruption controls覆盖：

- extra standalone字段；
- nested previous／new epoch不一致；
- drift＋rolled-over；
- CapacityRejected携transition。

因此不再存在两个capacity transition事实槽。

### Event codec及graph controls

Required tests覆盖：

- committed × 五种committed results；
- duplicate／rejected；
- failed-before-policy／failed-after-policy；
- post-COMMIT cancellation；
- 所有主outcome错配；
- drift＋non-NoChange；
- extra standalone capacity transition；
- policy前、policy callable内、checkpoint write后、COMMIT enqueue后四个真实phase barriers。

要求使用真实phase injection而非同一helper重复调用，且同时断言outcome family、rows、revision和event。这足以判否漏字段、错variant、rollback伪成功及post-COMMIT误报。

## 当前处置汇总

- `T4A-AM2-01`：ADDRESSED。
- New Blocker：0。
- New Major：0。
- New Minor：1。
- Authority writeback：允许。
- Source implementation：仍须等待living Spec／plan／status／tracker写回并完成独立authority review。

## 搜索面与证据边界

完整读取了amendment 2 review与固定SHA amendment 3，并只对照现有`TokenLearningObservation`四种main outcomes和直接相邻lifecycle。没有重审已关闭的capacity／context／index设计，没有运行broad tests或真实upstream，没有修改source／文档。

Amendment 3首尾SHA一致，fixed source HEAD未移动且无tracked dirt。本结论只批准design进入living authority writeback，不证明authority transcription、V1 codec或source implementation已经完成。

# 最终结论

**APPROVED DESIGN**