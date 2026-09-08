# Task 3A 独立 source review

## 评审范围与总体 verdict

- 固定对象：`BASE a2779b644844dcf6cc36454c12b85f4e9f09c2e8` → `HEAD 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8`。
- Candidate worktree：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd`，branch `worktree-agent-a2cd3b8776da8ebfd`。
- 评审了完整的2,320行固定diff、全部6个changed source文件的相关最终状态、4个changed test文件的diff与承重oracle，并执行了固定package列出的测试、lint和type-check范围。
- 明确排除：Task 4A predictor算法、Task 8 production visual formula及shared pipeline接线；它们尚未实现不构成缺陷。Candidate未提前接线，未发现scope violation。
- **总体 verdict：NOT APPROVED。**
- **Spec compliance：NEEDS FIX。**
- **Code quality：NEEDS FIX。**
- **计数：Critical=0，Important=2，Minor=0。**

## Critical

未发现Critical问题。

## Important

### T3A-SR-01：`LearningSnapshot`接受record中不存在的candidate-key evaluation

**位置**

- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src/app/tokenization/types.py:867-880`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_features.py:449-499`

**判据**

`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:47-49`要求`LearningSnapshot`按`(sample_key, candidate_key)`对账；固定review package的claim 2进一步要求DTO拒绝extra／wrong key。因diagnostic retention允许older evaluation缺席，这里的正确关系应是evaluation keys为对应record candidate keys的子集，而不是强制全集相等。

**具体场景与错误行为**

构造一个sample，其`PredictionRecord`只有`cold-start/deterministic` candidate；随后为同一sample向`LearningSnapshot.evaluations`放入一个自洽但record中不存在的`history-exact/median` evaluation。当前constructor只检查evaluation pair唯一且sample存在，因此完整接受该snapshot。

独立探针在固定HEAD输出：

```text
snapshot_extra_candidate_evaluation_accepted=PredictionCandidateKey(method=<PredictionMethod.HISTORY_EXACT: 'history-exact'>, variant=<PredictionCandidateVariant.MEDIAN: 'median'>)
```

这使public predictor DTO能够表示“有evaluation但没有产生该candidate”的不可能点时事实。虽然SQLite读取路径的`_validate_derived_graph()`会拒绝相同持久化错误，但DTO自身没有兑现固定claim，未来Task 4A若接收其它构造来源，可能把伪造的candidate history用于variant selection。

**为何现有tests未抓到**

`test_learning_snapshot_carries_bounded_prediction_history_with_identity_invariants`只覆盖matching happy path和sample引用；raw SQLite graph tests验证的是store decode边界，不能代替直接DTO constructor负例。没有测试向snapshot放入同sample下的合法但不属于record的candidate key。

**最小修法**

在`LearningSnapshot.__post_init__()`中建立所有record的`(sample_key, candidate_key)`集合，并拒绝任何不在该集合中的evaluation key；不要要求每个record candidate都有persisted evaluation，因为older diagnostic absence仍是合法合同。增加一个cold-only record＋extra exact evaluation的直接DTO负例。

### T3A-SR-02：重复candidate evaluation可进入event JSON，all-epoch startup把损坏DB判为有效

**位置**

- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src/app/tokenization/types.py:929-1002`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src/app/tokenization/learning_store.py:3965-3980`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src/app/tokenization/learning_store.py:4736-4809`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_learning_store.py:5035-5085`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_learning_store.py:5152-5218`

**判据**

Task 3A brief要求`TokenLearningObservation`按`(sample_key, candidate_key)`唯一对账；Spec的V1 authenticity和all-epoch graph要求event evaluation逐candidate key一致，不能让一个candidate事实重复出现。

**具体场景与错误行为**

先用candidate生成含一个合法`cold-start/deterministic` evaluation的committed event，再直接把该JSON entry复制一遍写回`learning_events.evaluations_json`。重启时：

1. `_decode_event_evaluations()`返回两个相同对象，没有唯一性检查。
2. `TokenLearningObservation.__post_init__()`只核sample key一致，不核candidate key唯一。
3. `_validate_derived_graph()`逐项比较时两个副本都匹配；随后用set比较candidate keys，重复项被折叠，所以corruption未被识别。

独立raw-DB探针在固定HEAD输出：

```text
duplicate_event_startup=accepted evaluations=2
```

直接DTO探针同样证明`TokenLearningObservation`接受两个相同candidate evaluations。结果是V1 startup把损坏的durable event当作有效状态，后续diagnostic／offline consumer可把同一candidate error重复计数。

**为何现有tests未抓到**

`event-evaluation-key` corruption只把variant改成不匹配的key，因此会被现有逐项比较抓到；field-set oracle只检查每个entry有哪些字段。两者都没有注入“两个完全合法且相同的entry”，而set equality恰好把该错误隐藏。

**最小修法**

在`TokenLearningObservation.__post_init__()`集中拒绝重复`(sample_key, candidate_key)`；由于event evaluation已经要求与observation sample key一致，按`candidate_key`判重也等价。这样V1 decoder构造DTO时会自动拒绝raw corruption。另加独立raw-row回归：复制一个合法event evaluation entry后，startup必须返回`INVALID_STATE`且DB bytes不变。

## Minor

未发现Minor问题。

## Claims逐项裁断

| Claim | Verdict | 结论 |
|---|---|---|
| 1．四methods、七pairs、same-method variants | PASS | 四个`PredictionMethod`成员及顺序保持；七种pair closed；same-method variants可共存；duplicate candidate key被拒。 |
| 2．selected／champions／eligibility与DTO graph | FAIL | `PredictionRecord`本身、V1 decode及persistent record graph符合要求，但`LearningSnapshot`未拒绝record中不存在的extra／wrong evaluation key，见T3A-SR-01。 |
| 3．`PredictionDecision` ephemeral boundary | PASS | exact／prefix kind、identity、epoch组合由DTO及组成类型闭合；profile／cold拒绝intent；未进入record、candidate／event JSON或DDL；未提前接Task 4A／Task 5。 |
| 4．visual capability None／0／pickle | PASS | 独立槽、类型拒绝、no-media 0、missing／unsupported None、56×84→6、42×112→8、generation 2／schema revision 1、worker process pickle及legacy known-only行为均成立；未接production catalog。 |
| 5．V1 selected／champion／variant、SQL与graph | FAIL | Visual column、selected variant、champions JSON、evaluation PK／CHECK／index及fixed manifests均同步；但重复合法event evaluation仍通过all-epoch startup，见T3A-SR-02。 |
| 6．per-key newest128与重建 | PASS | Retention、bounds、prune key及graph windows均使用完整candidate key；same-method variants预算独立；record＋actual重建路径保留。 |
| 7．Task 3既有合同与108／204 IDs | PASS | 完整learning-store测试368项通过，action literal仍为108 semantic bases／204 IDs；source diff未新增raw `aiosqlite` await。 |
| 8．tests oracle | FAIL | 主要oracles有分辨力，但没有snapshot extra candidate或event duplicate candidate的负例，因而两项缺陷在533项tokenization测试中保持全绿。 |
| 9．scope boundary | PASS | Exact diff只有package列出的10 paths；未改`uv.lock`、pipeline或`prediction.py`，未接真实descriptor formula，未改变public count结果。 |

## Mutation 6替代oracle与残留检查

- `test_candidate_encoder_has_exact_durable_field_set_without_intent`直接读取candidate encoder结果并与手写exact key set比较。对brief规定的单变量mutation“把intent加入candidate JSON”，该替代oracle确实会判红，未使用production encoder生成expected，因此这一替代本身可接受。
- 该替代oracle**单独**不覆盖event JSON或DDL；完整suite通过另外两类异源literal补齐：event evaluation exact field set位于`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_learning_store.py:5073-5081`，DDL exact column／PK／index oracle位于同文件`:440-717`及`:2405-2493`。因此intent absence的三面总体有覆盖。T3A-SR-02是不同的cardinality盲区，不否定intent mutation oracle。
- 两次`/proc`扫描均得到`non_ancestor_candidate_processes=0`。
- 在candidate worktree内扫描`*.sqlite*`与`*.db*`无命中。
- 测试后重建candidate index tree得到`a34d8b396be0eb16b476134453f728dfc997de88`，与HEAD commit tree一致；683个tracked entries逐blob比较为0 mismatch。未修改任何source、test、authority或candidate commit。

## 独立验证结果

所有命令均在同一调用内显式进入candidate worktree，并打印、断言physical cwd、toplevel、branch与HEAD；测试进程的`app.tokenization` import路径逐字位于candidate的`src/`。

- Focused Task 3A selectors：17 passed，10.65s。
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_learning_store.py`：368 passed，90.95s。
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/`：533 passed，156.61s。
- Ruff changed paths：All checks passed。
- Pyright `src tests`：0 errors、0 warnings、0 informations。
- 未执行live upstream、完整repository pytest／coverage或六项source-file mutations；前两者不能裁断本slice的DTO／SQLite合同，后者因用户明确禁止reviewer修改candidate。Implementer的mutation报告未被冒充为reviewer重跑证据。

## Identity与搜索面

开始和结束均复算并匹配：

- Diff SHA-256：`0a9d62c93a518ec434491b75d9ff65ac3daf25bb3a9daf9319f607a1182be5e9`。
- Brief SHA-256：`6f98acb6138451fdb4c08031075f274d0d2921244998dc446e81bad2e63dfed2`。
- Spec SHA-256：`2644ad9a44a9b0b06f072513dfb82834f8512f5b3fc6272a435b45a8a8445834`。
- Plan SHA-256：`ab7da5a2f0c5c292824ec14f52fbc5657c91fabf5f264428a493042821e3ab68`。
- HEAD loose commit object自身SHA、唯一parent和tree均独立验证；10个diff path的candidate blobs逐项与固定diff的new blob IDs相等。未观察到moving snapshot。

Harness禁止worktree-isolated reviewer在另一managed worktree执行Git CLI，因此未把被拒绝的`git status`伪装成已执行；改用candidate自身worktree metadata、raw commit object、index tree重建和逐tracked-blob比较完成同一identity／cleanliness核验。

## 排除但未采纳为finding的路线

- 曾怀疑sample-prune与diagnostic window相交时会漏掉重新进入newest window的evaluation；受控小limit、anchor-use优先级探针保留了正确sample／evaluation集合，未复现，因此不作为finding，也不外推为所有容量交错已证明正确。
- Duck-typed fake candidate key可在显式`cast(Any)`后绕过静态类型；该场景违反受支持的typed constructor输入，V1 decoder始终构造真实closed key，故未升级为本轮正确性finding。

## 交付说明

请求的报告文件`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-source-review-gpt-high.md`未创建，因为当前subagent harness的developer约束明确禁止写review报告`.md`；按用户给定fallback，完整正文在此回传。未提交、未修复、未push、未执行任何清理或破坏性操作。调用方需修复T3A-SR-01与T3A-SR-02后重新请求source review。
