---
report_id: token-task4a-prediction-dto-gap-review-claude
attempt_id: token-task4a-contract-claude-1
status: in-review
reviewed_at_rev: "spec-sha256:829f11ef3af40ebecd70ed8e67274b6c05df676339c6267fe2c88cca3a036717; plan-sha256:8752e05f3f116b530af5174f27b959db072b29754a247747a20edd37f23a2d5c; task3-source:9ff21cef4d0f2377d1e60eba962e3b450584902c"
reviewed_at: 2026-09-07
reviewer_role: Token Task 4A architecture-contract reviewer
---

# Token Task 4A prediction DTO gap review

## 评审范围

本轮以当前 `.dev/docs/token-counting/spec.md` 为行为权威，绑定 SHA-256 `829f11ef3af40ebecd70ed8e67274b6c05df676339c6267fe2c88cca3a036717`；以 `.dev/docs/token-counting/plan.md` Tasks 4A～4C 为任务合同，绑定 SHA-256 `8752e05f3f116b530af5174f27b959db072b29754a247747a20edd37f23a2d5c`；以 worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/` 的 exact HEAD `9ff21cef4d0f2377d1e60eba962e3b450584902c` 为 Task 3 reviewed source。Source 面只审与 Task 4A candidates、prequential record、visual cold-start 和 `AnchorUseIntent` carrier 相交的 `src/app/tokenization/types.py`、`learning_schema.py`、`learning_store.py`、`features.py`、`estimators.py`、`worker.py`及相关 `tests/unit/tokenization/test_features.py`、`test_learning_store.py`。

明确不在范围内：Task 3 已闭合的 cancellation ownership、migration concurrency、thread provenance、prune total order及其它不与本轮三条合同接缝相交的实现；未重审 count error wire 的正确性；未运行 broad tests；未修改 source、tests、Spec、plan 或 status。

## 总体 verdict

**CONTRACT AMENDMENT REQUIRED。Task 4A source 在修正前不可启动。** 当前合同与 Task 3 reviewed DTO／V1 schema 无法表达 Spec 已要求的同 method 多 candidate prequential facts，也无法表达 A18 中与 `known_tokens=29` 分槽的 visual 6 tokens。另有一个 request-side intent carrier 接缝会把 ephemeral orchestration intent 混入 durable candidate DTO。前两项是进入 Task 4A 的 blocker；第三项是必须在同轮澄清的 major internal-interface defect。

**Blocker 数：2。**

## Findings

### token-task4a-prediction-dto-gap-review-claude-01

- `severity`: blocker
- `statement_kind`: fact＋architecture judgment
- `conclusion_strength`: confirmed，足以据此阻止 Task 4A source 启动
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:542-613`
- `related_locations`:
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:275-295`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:329-335`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:401-405`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:453`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:543,550,553,555,571-575`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:677-722`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:848-878`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_schema.py:153-220,492-527`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_store.py:2390-2461,3797-3911,4008-4028,4158-4177,4297-4330,4558-4723`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/tests/unit/tokenization/test_features.py:238-328,359-443`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/tests/unit/tokenization/test_learning_store.py:403-707,863-938,3115-3321`

#### 事实证据

1. Spec §6.2 要求 prefix deterministic baseline、additive 和 multiplicative suffix candidates 在各自存在时以同批 prequential paired errors 比较；§6.3 对 profile additive／multiplicative candidates 作同样要求；§7.3 又要求 learn 前生成 candidates 和 errors。A20 明确要求候选不足、paired window、tie、demotion、recovery 分支可判否；A39 明确要求 sample／`PredictionRecord`／actual 能重建每个 candidate 的 evaluation。
2. `PredictionRecord.__post_init__()` 当前把 `candidate.method` 当唯一键，并在两个 `history-prefix` 或两个 `profile-calibrated` candidates 共存时直接抛出 `ValueError("prediction candidates must have unique methods")`。本轮在 exact source import 路径上构造同为 `history-prefix`、值为 35 和 37 的两个 candidates，实际得到该异常。
3. `PredictionEvaluation` 只有 `method`，没有 candidate identity。`LearningUpdate` 用 `{candidate.method: candidate}`和`{evaluation.method: evaluation}`对账并强制 method 唯一；`LearningSnapshot`也只允许 `(sample_key, method)`唯一。因此即使绕过 `PredictionRecord`，第二个同 method evaluation 仍会覆盖或被拒。
4. SQLite `evaluations` 的 primary key 是 sample owner＋`method`；`ordinal`不是 key，不能避免同 method row collision。`prediction_records`只持久化 `selected_method`，candidate JSON也只有 method，没有 selected candidate key或每个 method 当时的 internal champion。Store reconstruction、event validation、diagnostic windows、bounds和prune keys均继续以 method 为唯一 candidate identity。
5. 因此实现者只有两种错误出口：丢掉 challenger，只保存当前 method champion；或把 additive／multiplicative伪装成新的 public methods。前者使 promotion／demotion／recovery和drift无法复现当时 paired facts，后者违反四个 public methods 不得改名、删除或重排的合同。
6. Spec 自身还有一处必须同步消歧：§8.2／A39要求 newest 128 matching samples 对每个 candidate 各有 evaluation，而§8.5／A23仍写成“128 rows per method／ProfileKey／identity／epoch”。同 method 有多个 candidates 后，这两句话不能同时按“row count”成立。

#### 承重前提及反事实

- 前提：prefix 和 profile 的不同 estimator variants 是同一个 public method 内的 candidates，而不是新的 public methods。
- 它支撑的动作／结论：必须新增 method 之下的 candidate key，并在 source 前修 Spec／V1 schema。
- 若前提为假：若用户改为把每个 variant 暴露为独立 public method，本 finding 的具体 typed model会改变；但这与当前 Spec method集合和用户本轮“不得把四个 public methods 改名、删除或重排”的明确约束冲突，所以当前可按该前提行动。

#### 最小 typed model 修法

保留 `PredictionMethod` 的四个成员及现有顺序不动，在其下新增 closed candidate variant和组合键：

```python
class PredictionCandidateVariant(StrEnum):
    MEDIAN = "median"
    DETERMINISTIC = "deterministic"
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"

@dataclass(frozen=True, slots=True)
class PredictionCandidateKey:
    method: PredictionMethod
    variant: PredictionCandidateVariant

@dataclass(frozen=True, slots=True)
class MethodChampion:
    method: PredictionMethod
    candidate_key: PredictionCandidateKey
    eligible_for_selection: bool
```

V1 只接受七种 method／variant pair：`history-exact/median`、`history-prefix/deterministic`、`history-prefix/additive`、`history-prefix/multiplicative`、`profile-calibrated/additive`、`profile-calibrated/multiplicative`、`cold-start/deterministic`。不得为这些 variants 新增 public method。

- `TokenPrediction`增加`candidate_key`并验证`candidate_key.method is method`。
- `PredictionRecord`以`selected_key`唯一定位 global selected candidate，另保存每个当时存在 method 的`method_champions`；`selected`可保留为从`selected_key`派生的 property，避免重复真值。Candidate uniqueness改为 candidate key，不再是 method。每个 champion key必须存在、method一致且每 method恰有一个；global selected key必须等于一个`eligible_for_selection=True`的 method champion。
- `eligible_for_selection`不能由 global selected反推：exact优先时，global selected不会告诉离线重放者 prefix当时是 eligible还是 demoted；profile candidates存在时也不能据此知道 profile是否已 promotion。Demoted prefix继续以`eligible_for_selection=False`保留 champion和challenger errors。
- `PredictionEvaluation`绑定`candidate_key`；`method`应由 key派生或与 key交叉验证。`LearningUpdate`、`LearningSnapshot`、event evaluation及全部 reconstruction以 candidate key对账。Candidate缺席仍保持缺席，不制造0 error；actual 0的 relative／APE缺席合同不变。

#### 最小 V1 persistence 修法

采用 method＋variant作为 candidate key的 SQL 表达，避免不透明拼接字符串：

1. `prediction_records`保留`selected_method`并新增`selected_variant TEXT NOT NULL`与`method_champions_json TEXT NOT NULL`；`candidates_json`每个 entry新增`variant`。`method_champions_json`使用 canonical closed mapping `method -> {variant, eligible_for_selection}`，decoder要求 exact keys、unique method、合法 pair及全部 target candidate存在。
2. `evaluations`新增`candidate_variant TEXT NOT NULL`，primary key改为 sample owner＋`method`＋`candidate_variant`；保留`ordinal`作为 candidate-list order一致性检查，不把 ordinal当稳定 identity。新增 method／variant合法组合 CHECK；`evaluations_window` index加入 variant。
3. Event `evaluations_json`也增加 variant；selected／champion／candidate／evaluation四处必须逐 key对账。Persistent graph validator、newest mandatory window、extra／mismatch detection、event completeness、snapshot uniqueness、prune plan和reconstruction map全部从 method key改为 candidate key。
4. Diagnostic retention的单位改成“每 candidate key／`ProfileKey`／identity／epoch最近128个 matching samples”，而不是每 method最多128 rows。一个 prefix method若三个 candidates都存在，可有最多`3 × 128`条 diagnostic rows；完整更老 facts仍从 record candidate＋actual重建。
5. 当前 Task 3 尚是本轮指定的 reviewed candidate，最小路径是在集成前修订 V1 DDL、`TableManifest`、fixed table-DDL digests、overall manifest digest和independent test literals；confirmed-action call sites没有增加，§8.1.1 action-ID集合无需变化。若调用方另有必须兼容已经发布的旧 V1 database这一外部事实，则不能原地重定义 V1，必须改走新 schema version＋migration；本轮没有得到该事实。

#### Spec 先修项

这是 Spec-level prerequisite，不是实现者可在 source 内自行补的局部类型选择。至少同步修订§7.3的 candidate／method champion点时事实，§8.2的 candidate-key relational match，§8.5的 retention单位，A8／A20／A23／A39及§13 transcription map；然后同步 plan Tasks 4A～4C和 Task 3 V1 schema ownership。四个 public methods保持原名、原集合、原顺序。

#### 受影响文件与 tests

- Production：`types.py`、`learning_schema.py`、`learning_store.py`、新建的`prediction.py`。
- Existing tests：`test_features.py`当前“unique methods”转录必须改成“允许 same method不同 variant，拒绝 duplicate candidate key”；`test_learning_store.py`的独立列／PK／CHECK／DDL digest／index／raw fixture／A39 graph oracle全部同步。
- Planned tests：`test_prediction.py`需用一个 sample同时保存 prefix三候选、profile两候选和 cold-start，并分别断言 candidate paired errors、method champions、global selected key、demotion／promotion／recovery；至少有一条 corruption fixture交换 champion key、eligibility或 evaluation variant后必须被 persistent validation拒绝。

#### 被否路线

- **只保存每 method最终 champion。** 否决；challenger paired errors和点时 champion selection消失，A20／A39无法重放。
- **用 candidate ordinal作 identity。** 否决；ordinal依赖 list order，后续增加候选会改写含义，且当前 PK仍按 method冲突。Ordinal只适合一致性校验。
- **把 additive／multiplicative加入 `PredictionMethod`。** 否决；改变四个 public methods集合，并把 internal estimator variant冒充 method。
- **只改 JSON，不改 evaluation PK／bounds。** 否决；第二个同 method row仍冲突，或 diagnostic prune仍丢同 method candidates。
- **事后用当前算法重算 method champion／eligibility。** 否决；当时窗口可能已被 bounded prune，且算法／generation变化后不能证明点时选择。

### token-task4a-prediction-dto-gap-review-claude-02

- `severity`: blocker
- `statement_kind`: fact＋architecture judgment
- `conclusion_strength`: confirmed，A18 的 exact 35无法由当前 DTO／producer／store表达
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:43-99,166-201`
- `related_locations`:
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:161-210`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:553`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:244-267,328-348,470-491`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/features.py:27-50,223-322,269-285,765-787`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/estimators.py:99-105`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/worker.py:35-74`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_schema.py:119-151,467-489`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_store.py:2342-2386,3141-3164,3453-3511,4509-4555,5063-5075`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/tests/unit/tokenization/test_features.py:177-206,498-542,702-766,831-837`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/tests/unit/tokenization/test_learning_store.py:800-861,2305-2453`

#### 事实证据

1. Spec §4.2把`known_tokens`和`capability_visual_tokens`定义为两个相加但不可互相冒充的槽；A18进一步固定独立 arithmetic：known为29、descriptor visual为6、residual为0，cold-start unscaled和multiplier 1后的public结果均为35。
2. 当前`FeatureName`只有`MEDIA_PIXEL_COUNT`等原始量，没有 visual-token output；`EstimateFeatures`也没有`capability_visual_tokens`字段。`_Analysis.record_media()`只累计 decoded bytes、aggregate pixel count和PDF pages，`finish()`不能写出 visual 6。
3. `analyze_responses_input(payload, *, timings=None)`没有 exact resolved descriptor或其它visual formula输入。Legacy estimator和worker随后只取`max(features.known_tokens, 1)`，所以即使 Task 4A新增 cold-start equation，也无处读取 descriptor-derived visual contribution。
4. Store只持久化`known_tokens`、components、profile key和feature vector等现有字段；restart decode会重建同样缺槽的`EstimateFeatures`。因此运行期临时算出6而不扩展持久化同样失败：restart后的prequential record、cold-start replay和A39 graph无法复现原 prediction。
5. 本轮使用与production estimator不同源的stub encoder复现A18 payload。Exact reviewed source返回`known=29`，`MEDIA_PIXEL_COUNT=(present=True, value=4704)`；独立公式`ceil(56/28) × ceil(84/28)=6`；运行时检查确认`EstimateFeatures`字段和`FeatureName`均没有`capability_visual_tokens`。这是当前表示能力的反例，不是对真实provider计费准确率的声称。
6. 现有`test_features.py`覆盖known／framing、media bytes和aggregate pixels的mechanics，却没有A18的29＋6＝35 exact oracle；`test_empty_payload_has_zero_structured_tokens_and_legacy_minimum_one`仍只钉 legacy minimum-one wrapper。Plan把A18列入Task 2／4A，但Task 2 producer signature与Task 8 descriptor producer的时序没有闭合。

#### 承重前提及反事实

- 前提：A18 的6是 exact resolved descriptor按每个media item的版本化公式得到的确定性输出，并且必须与known 29分槽。
- 它支撑的动作／结论：Task 4A前必须为该输出增加独立、可持久化的DTO字段和producer capability seam。
- 若前提为假：若visual 6只是测试外临时常量或允许并入known，当前DTO可勉强返回35；但这会直接违反Spec §4.2和A18的slot arithmetic，也会污染profile additive baseline，所以不属于当前可选实现。

#### 四条路线比较

| 路线 | 表示A18分槽 | restart可复现 | 对profile distance的影响 | 结论 |
|---|---|---|---|---|
| `EstimateFeatures.capability_visual_tokens: int | None`＋dedicated schema column | 是 | 是 | 不改变现有`FeatureVector`维度 | **采用，语义最小。** |
| 给`FeatureVector`增加presence-aware `CAPABILITY_VISUAL_TOKENS` | 是 | JSON可持久化 | 会把derived visual tokens与`MEDIA_PIXEL_COUNT`同时作为equal-weight L1维度，改变neighbor几何并要求`PROFILE_SCHEMA_REVISION`变化 | 否决为本轮最小方案；它省一列但扩大了prediction behavior。 |
| 把visual tokens塞进`known_tokens`／components | 否 | 表面可持久化 | 污染known、additive residual、A18 exact 29和opaque／media分槽 | 否决。 |
| 从aggregate `MEDIA_PIXEL_COUNT`回推patch tokens | 否，且不可逆 | 不能忠实重建 | 同面积不同形状或多图边界会给不同ceil结果 | 否决；例如56×84和42×112均为4,704 pixels，前者为6 patches，后者为8 patches，provider resize／limit还会增加非可逆性。 |

#### 最小可持久化修法

1. 在`EstimateFeatures`增加`capability_visual_tokens: int | None`。`None`表示formula缺席或必需metadata不完整；非负integer包含真实0。Cold-start只在该值非`None`时相加，否则加0并保留Spec要求的具名low-confidence reason。`known_tokens`及components保持29，不含这6。
2. V1 `samples`新增nullable `capability_visual_tokens INTEGER CHECK (capability_visual_tokens IS NULL OR capability_visual_tokens >= 0)`；同步`TableManifest`、CREATE DDL、fixed DDL digest、overall manifest digest、insert／select／decode和independent schema oracle。DTO constructor继续拒绝bool、negative和非integer；state cardinality bounds不变。
3. 不把 full provider `ModelDescriptor`硬塞入pure feature core或process worker。新增tokenization-owned、immutable、pickle-safe的`TokenizationCapabilities`／`VisualTokenFormula` DTO，至少携带closed formula kind／revision及公式所需resize／limit参数；request shaping从 exact resolved descriptor生成它。`analyze_responses_input(payload, *, capabilities, timings=None)`按每个media item先应用formula再求和，输出上述字段。
4. Task 8的`analyze_anthropic_input(request, capabilities)`复用同一个capability DTO和同一个`EstimateFeatures`槽；Task 8只负责从model catalog／descriptor生产thinking与visual capability facts，不另造第二个visual representation。若Task 8的catalog producer尚未完成，应把这个最小common capability slice提前到Task 4A前，而不是让Task 4A先写固定公式或临时参数。
5. 修改 visual formula selection／cold-start结果按Spec §4.2增加`ESTIMATOR_GENERATION`／cold-start prior revision；descriptor capability变化也必须改变 descriptor fingerprint。采用top-level字段时`FeatureVector`和`ProfileKey`shape不变，`PROFILE_SCHEMA_REVISION`无需仅因该字段递增。若改选FeatureVector路线，则两种revision都必须递增。

#### Spec 先修项与 plan 接缝

- Spec §4.1需明确`EstimateFeatures`的presence-aware visual slot；§4.2需明确多media的per-item formula求和与`None -> 0 + reason`；§13将字段、schema column和A18 tests列为transcriptions。A18的29／6／35数值不变。
- Plan Task 4A当前不能只“consume Task 2 DTO”后再自行找到descriptor；需把common capability producer安排在4A前。Task 8仍拥有Anthropic thinking／catalog capability扩展，但其shared DTO seam需前移或拆出。这个排序修正是plan／internal interface；29＋6分槽和可restart复现是Spec事实。

#### 受影响文件与 tests

- Production：`types.py`、`features.py`、`worker.py`、`estimators.py`、`learning_schema.py`、`learning_store.py`、新建`prediction.py`，以及Task 8会修改的`model_provider/types.py`和catalog capability adapter。
- Existing tests：`test_features.py`增加不同源stub的A18 exact object；`test_learning_store.py`增加6和`None`的round-trip、negative／wrong-type corruption、column／CHECK／DDL digest oracle，并让independent raw fixtures填新列。
- Planned tests：`test_prediction.py`断言cold-start读取独立field而不是known／aggregate pixels；用同aggregate pixels不同dimensions的正控证明per-item formula seam；formula缺席与metadata缺失分别断言0 contribution＋具名reason；generation变化不得复用旧history。

#### 被否路线

除上表四条比较外，再否决“Task 4A先硬编码28-patch，Task 8以后补descriptor”：它会让行为在Spec之前落到source，并且已有history无法证明使用了哪个版本formula。

### token-task4a-prediction-dto-gap-review-claude-03

- `severity`: major
- `statement_kind`: architecture judgment grounded in current type／codec facts
- `conclusion_strength`: high confidence；exact wrapper名称属于internal choice，但intent与durable candidate分离是承重合同
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:437-441`
- `related_locations`:
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:572`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:337-345,397-405`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:482-538,542-567`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_store.py:750,2907-2920,4393-4423,4558-4631`
  - `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/tests/unit/tokenization/test_features.py:446-469`

#### 事实证据

1. `AnchorUseIntent`当前已经是独立、immutable、epoch-bound DTO；store有显式`record_anchor_use(intent)`入口。它描述“本次request-side selection应异步登记一次anchor use”，不是candidate数值、prequential error或sample label。
2. Spec §8.5写`TokenPrediction`“可携带”intent，Plan Task 4A又把`predict_exact_or_prefix(...) -> TokenPrediction`与“result携带intent”绑定。与此同时，当前`TokenPrediction`正是`PredictionRecord.candidates`的durable元素；store的`candidates_json`只编码 method、tokens、sample count和reasons，并据此重建`TokenPrediction`。
3. 因此直接给`TokenPrediction`加optional intent会形成两种坏状态：若codec忽略intent，内存对象与restart对象不等且persistent validation无法判明丢失是故意还是corruption；若codec保存intent，则把一次request orchestration command持久化成candidate事实，并迫使每个historical candidate携带与数值无关的anchor source command。
4. Anchor-use request与learning sample生命周期并不一一对应：local count可命中anchor并需要排队use intent，却不会因此形成upstream-labeled sample；prequential learner也可在内部计算exact／prefix challenger，但不应把这次内部evaluation当成request-side actual use。把intent放进candidate或`PredictionRecord`会合并这两个时序。

#### 承重前提及反事实

- 前提：`AnchorUseIntent`只由request-side orchestrator消费，store只通过`record_anchor_use(intent)`看到它；prequential candidate persistence不需要它。
- 它支撑的动作／结论：Task 4 pure strategy应返回一个把prediction和intent绑定但不让intent进入`PredictionRecord`的wrapper。
- 若前提为假：若未来产品决定“每次内部prequential challenger evaluation也算anchor use”，wrapper消费规则要改；但这会改变§8.5的last-confirmed actual use语义，必须先改Spec，当前不得预设。

#### 最小接口修法

```python
@dataclass(frozen=True, slots=True)
class PredictionDecision:
    prediction: TokenPrediction
    anchor_use_intent: AnchorUseIntent | None
```

- Wrapper验证：`history-exact`必须带`AnchorKind.EXACT` intent，`history-prefix`必须带`AnchorKind.PREFIX` intent，profile／cold-start必须没有intent；intent identity／epoch必须与prediction相同。Fingerprint和source keys继续由anchor selection构造，不复制进`TokenPrediction`。
- Task 4A outer API改为`predict_exact_or_prefix(features, snapshot) -> PredictionDecision`；Task 4B的candidate generation／champion helpers仍返回durable `TokenPrediction`／candidate records，不需要intent。
- Task 5的request orchestration拿到decision后，在critical path外只把`decision.anchor_use_intent`排入其owned queue；对public projection和同步observation使用`decision.prediction`。Queue outcome不回写prediction。
- Prequential learning policy从相同pure selection取得candidate／champion facts，绑定`PredictionRecord.sample_key`，但明确丢弃request-side intent；store的candidate JSON／DDL完全不新增intent字段。唯一持久化intent的动作仍是独立`record_anchor_use(intent)`更新last-use state，而不是保存command本身。

#### 三条路线比较

| 路线 | 优点 | 承重缺陷 | 结论 |
|---|---|---|---|
| 扩展`TokenPrediction` | 调用点表面最少 | durable candidate与ephemeral command同型；codec要么丢字段，要么错误持久化 | 否决。 |
| 返回`tuple[TokenPrediction, AnchorUseIntent | None]` | 不改candidate DTO | position和跨字段不变量无owner，后续扩展offer facts时继续堆位置槽 | 可工作但不是最小可靠接口，否决。 |
| 新增immutable `PredictionDecision` wrapper | 绑定同一决策的数值与command，同时隔离persistence | 多一个浅wrapper | **采用。** |

#### Spec／plan 分类与受影响 tests

- 必须先修的Spec事实：§8.5和A36把carrier改成typed decision wrapper，并明确intent不属于`PredictionRecord`、candidate JSON或learning event；Task 5只有request-side decision才排队，prequential evaluation不冒充anchor use。
- Plan／internal interface：wrapper exact名称可由实现者决定；Plan Task 4A produces和Task 5 consumes signatures必须同步。`types.py`新增wrapper，`prediction.py`返回它，`learning.py`消费它；`learning_store.py`不新增intent persistence。
- Tests：`test_features.py`或新`test_prediction.py`验证wrapper的method／kind／identity／epoch不变量；`test_learning_service.py`验证Task 5只排request decision intent；`test_learning_store.py`以candidate JSON exact keys和DDL absence断言store没有intent字段，同时保留`record_anchor_use()`的独立round-trip behavior。

#### 被否路线

不采用“先把optional intent塞入`TokenPrediction`，以后再拆”：Task 4一旦写出，Task 3 codec和A39 fixtures就会转录错误结构，后续拆分不是无害重构，而是再次改持久化合同。

## 指定判据处置总览

| Spec criterion | 本轮结论 | 所需动作 |
|---|---|---|
| A8 | 当前zero semantics本身无新异议；candidate identity仍不足 | 增加candidate key和每candidate evaluation；actual 0缺席规则保持不变。 |
| A15 | 未发现本轮相关合同缺口 | Finalization顺序不改；仅同步新candidate constructors／keys。 |
| A18 | blocker，已由运行probe证实当前只能保留29和aggregate pixels，不能保留6 | 增加独立persisted visual slot和capability producer seam。 |
| A19 | 已读但与本轮接缝无关 | 不改、不重审count error合同。 |
| A20 | blocker，same-method candidates及method champions无法持久化 | 修typed model、V1 key／bounds／validator和state-machine tests。 |
| A36 | major，intent carrier边界错误 | 用ephemeral decision wrapper连接Task 4与Task 5，store candidate不持久化intent。 |
| A39 | blocker的一部分，当前graph只能重建每method一个candidate | 把完整graph和newest-128 unit改为candidate key。 |

## Spec事实与internal interface的修正顺序

1. **先改 living Spec。** 明确 candidate key、point-in-time method champion＋eligibility、selected key、candidate-level 128-sample retention；增加presence-aware visual slot；把intent carrier改为ephemeral decision wrapper。同步revision record与§13 transcription map。以上均决定可观察learning行为或restart语义，不能只停在本报告。
2. **再改 plan。** Task 3 V1 schema／DTO amendment必须先于Task 4A；把common visual capability producer安排到Task 4A前；更新Tasks 4A～4C和Task 5的signatures及tests。Exact wrapper class名、SQL列拆分方式和capability DTO名是internal interface，可在满足上述Spec facts的前提下由实现者定。
3. **再修 Task 3 reviewed source与tests。** 修candidate／evaluation keys、selected／champion persistence、visual column、codecs、authenticity／bounds oracles，重新独立review到可消费状态。
4. **最后才启动 Task 4A source。** 此时实现cold-start、exact／prefix、prequential evaluation和finalization，不在source内偷偷补一份与Spec不同的contract。

## 搜索面与执行证据

- Authority：完整读取Spec §4～§8，另外读取§9～§10相邻状态语义、§12的A8／A15／A18／A19／A20／A36／A39及§13；读取plan Tasks 4A～4C、Task 5和Task 8的接口／排序。
- Source revision：通过目标worktree的gitdir HEAD ref读取并确认exact commit为`9ff21cef4d0f2377d1e60eba962e3b450584902c`。
- Source／tests：按symbol map读取四个指定Task 3 source中与DTO、DDL、JSON codec、persistent validation、bounds、features有关的定义和相关tests；补读`estimators.py`、`worker.py`与`model_provider/types.py`的producer seam。没有把5,457行store和4,873行store tests中与本轮无关的cancellation／migration分支伪称为已重审。
- Probe 1：从目标source import两个同为`history-prefix`的`TokenPrediction`，构造一个`PredictionRecord`；实际以`ValueError: prediction candidates must have unique methods`失败。这个probe证明current DTO拒绝目标状态，不证明修法已经正确。
- Probe 2：以独立stub encoder运行A18 payload；实际得到known 29、aggregate pixels 4,704、independent visual 6、DTO无visual slot。这个probe证明表示／接线缺口，不证明真实provider billing。
- 未运行broad tests，未修改任何被评对象。

## 总体判定

**CONTRACT AMENDMENT REQUIRED。** Findings 01和02使Task 4A的输入／输出模型不完备，source在修正前不得启动。Finding 03应在同一合同修订中关闭，避免Task 4A把intent混入durable candidates。评审本身已完整执行，不是权限或工具阻塞；verdict为`needs-fix`。

## 我最没把握的三个判断

1. **Finding 03定为major而不是blocker。** 依据是wrapper选择存在明确局部解，且Findings 01／02已独立阻断source；若调用方认为任何未定Task 4A return type都必须单独阻断，可把严重级别上调，但不改变修正内容。
2. **采用top-level visual field并保持`PROFILE_SCHEMA_REVISION`不变。** 这是为避免改变equal-weight feature distance作出的高置信架构判断；若项目把“profile schema revision”定义为整个`EstimateFeatures` persistence shape而不只`ProfileKey`／`FeatureVector`，则也应递增。当前Spec用语更支持只递增estimator generation。
3. **在集成前原地修订V1而不是发布V2。** 任务明确要求V1 schema变化，且被检对象是指定Task 3 reviewed candidate；本轮没有核验是否已有外部必须兼容的V1 database。若该外部事实存在，必须改成versioned migration，不能依赖本报告的V1-in-place建议。

## 执行本契约时遇到的摩擦

- CodeGraph对目标Task 3 worktree报告没有可用index，因此按项目规则降级到absolute `Read`和`rg`，没有自行建index。
- Harness禁止isolated agent通过`Write`直接写shared checkout；当前agent worktree的`.dev`是指向主树`.dev`的项目既有symlink，但`Write`仍拒绝resolved target。报告改用每条命令先显式`cd /home/xp/src/ghc-api-proxy-py`后，以exclusive create＋append方式只写用户授权的唯一报告路径；没有写其它文件。

## 交付声明

- `delivery_complete`: true
- `completed_at`: 2026-09-07
- `finding_total`: 3
- `blocker`: 2
- `major`: 1
- `minor`: 0
- `nit`: 0
