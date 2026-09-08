# Task 3A prefix contract 限定复核

> 转录说明：reviewer因自动隔离无法写入active `.dev`路径，主会话按其完整最终回传正文转录；除本说明外，不改写原报告内容。

- `report_id`：`task3a-prefix-contract-rereview-gpt-high`
- `attempt_id`：`260907-task3a-prefix-contract-rereview-gpt-high-01`
- `reviewed_at_rev`：Spec SHA-256 `c81d9046425fef155a20bfa666e396ba15196fbfb596941abbbe883bebd4f440`；plan SHA-256 `866c8643530d31ebd5f70ca50bcc8d1a2004fd2ad1b9837b36f2ea445f77deb7`；dotdev amendment commit `143e077`。
- `delivery_mode`：本leaf仍受自动worktree隔离，无法写共享main的指定报告路径；按coordinator指令一次回传完整正文，供主会话原样转录到`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-prefix-contract-rereview-gpt-high.md`。

## 评审范围

本轮严格限定为原`T4APCR-01`／`T4APCR-02`／`T4APCR-03`、本次authority整改及直接相邻合同：Spec §5、§6.0～§6.2、§7.3、§8.5、§11、§12 A5／A20／A36、§13、§15最新修订；living plan的strategy summary、Task 3A／4A／5 interfaces、tests与transcriptions；status中的Task 3A sequencing。没有复审Task 3 SQLite ownership、migration、schema authenticity、cancellation、prune或其它已review clean内容，也没有运行broad tests。

完整SHA在开始与交付前各重算一次，两次均严格等于给定值：Spec `c81d9046425fef155a20bfa666e396ba15196fbfb596941abbbe883bebd4f440`，plan `866c8643530d31ebd5f70ca50bcc8d1a2004fd2ad1b9837b36f2ea445f77deb7`。未发生moving snapshot。

## 总体 verdict

**APPROVED**。原三项finding均已按其承重谓词关闭；整改没有改变R3的四method体系、优先顺序、single-source prefix base、suffix或prequential semantics。另发现1项不影响实施的Minor stale restatement；因此Task 3A合同可实施，Task 4A仍按plan正确等待Task 3A reviewed source后再启动。

## 原finding逐条复核

### T4APCR-01：ADDRESSED

- `original_claim`：Task 4A没有已定稿的typed返回形态来携带`AnchorUseIntent`。
- `observed_fix`：Spec `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:447-451`定义request-side ephemeral immutable `PredictionDecision(prediction, anchor_use_intent)`，selected exact／prefix分别必须携EXACT／PREFIX intent，profile／cold-start intent缺席；decision明确不进入`PredictionRecord`、candidate JSON、evaluation或event。A36在`spec.md:586`逐项判定carrier、absence、purity、Task 5 owner chain、prequential challenger不得冒充actual use，并提供intent落入durable codec、prequential排队、Task 4 await store等单变量mutation。
- `plan_closure`：Task 3A在`plan.md:329-359`负责新增`PredictionDecision`及其DTO invariants／transcriptions；Task 4A在`plan.md:361-385`明确`predict_exact_or_prefix(...) -> PredictionDecision`、`build_prediction_record(...) -> PredictionRecord`，并规定decision intent不得进入record；Task 5在`plan.md:424-445`消费`PredictionDecision`，只把request decision的`anchor_use_intent`排入其owned queue。§13在`spec.md:597`、`spec.md:603-604`分别把DTO、request-side predictor和Task 5消费转录到`test_features.py`、`test_prediction.py`和`test_learning_service.py`。
- `falsifiable_scenario`：若实现把intent加回durable `TokenPrediction`／`PredictionRecord`，A36的DDL／JSON absence和Task 3A的intent-in-candidate mutation必须红；若request prefix decision缺intent或cold-start错误带intent，`PredictionDecision` invariant／`test_prediction.py` transcription必须红；若prequential challenger排use，A36 owner／queue call-count必须红。
- `judgment`：原核心接口fork已经消失，故为`ADDRESSED`。Living plan较早strategy summary仍有一处旧措辞，但更具体的Spec与三个Task signatures已经唯一决定接口；该局部漂移单列新Minor，不重开原Major。

### T4APCR-02：ADDRESSED

- `original_claim`：planned acceptance不能区分“单个最新anchor actual”与跨anchor median。
- `observed_fix`：A5在`spec.md:554`给出两个同context／item-count／prefix-digest anchors，actual 100／120、`observed_at_us` 1／2；明确selected prefix base必须是newer 120、intent source必须是同一120 sample、suffix只加一次。单变量mutation明确把matching prefix actual改取median 110，并要求selected unscaled value／intent source断言红。
- `plan_closure`：Living plan跨任务证据表`plan.md:193`转录same-prefix 100／120→newest120与median110 mutation；Task 4A行为与测试在`plan.md:377`、`plan.md:383`再次转录newest120、同source intent、suffix、median-prefix mutation；§13 `spec.md:603`点名same-prefix 100／120、same-source intent及canonical tie。
- `falsifiable_scenario`：错误实现面对上述snapshot返回110但发出120 source intent，会同时违反A5 exact value和Task 4A完整decision断言；它不再能靠“method正确＋intent单source”假绿。若suffix把top-level或anchor覆盖部分重复加入，A5的suffix exactly-once数值同样红。
- `judgment`：正确样本、相邻错误状态、target mutation和三处planned transcription均齐全，故为`ADDRESSED`。

### T4APCR-03：ADDRESSED

- `original_claim`：§6.2没有固定最终sample-key tie的方向与字段比较规则。
- `observed_fix`：`spec.md:287`明确total order为较大`item_count`优先、较大`observed_at_us`优先，最终按`process_boot_id` UTF-8 BINARY、`request_id` UTF-8 BINARY、numeric `attempt_index`依次升序；并明确predictor必须自行排序，不得依赖`LearningSnapshot.prefix_anchors`现有tuple order。
- `acceptance_closure`：A5 `spec.md:554`加入same-timestamp、逐个BINARY sample-key字段和numeric attempt 2／10 controls，反转或JSON lexical比较必须红；plan `plan.md:193`、`plan.md:377`、`plan.md:383`和§13 `spec.md:603`均转录canonical tie与wrong-tie mutation。
- `falsifiable_scenario`：把snapshot anchors反向排列，同时令matching anchors同coverage／timestamp、attempt分别2和10；正确predictor仍按numeric ascending选择2。若直接取snapshot首项、按JSON lexical取10或反转BINARY方向，A5／Task 4A tie断言必须红。
- `judgment`：predicate、方向、字段类型、order independence及mutation均已固定，故为`ADDRESSED`。

## 新finding

### T3APCRR-01：Living plan strategy summary仍把request-side结果写成`TokenPrediction`

- `finding_id`：`T3APCRR-01`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:127`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:348-350`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:372-373`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:436-438`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:449`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:586`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:603-604`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:632`。
- `evidence`：Plan architecture summary仍写“`TokenPredictor`……输出`TokenPrediction` discriminated union。Exact／prefix selection另在result中携带typed `AnchorUseIntent`”。同一living plan后续已明确request-side输出为`PredictionDecision`，`TokenPrediction`只是decision／record内candidate；Spec还明确否决把intent持久进`TokenPrediction`。因此line 127是本轮未同步的旧restatement。
- `falsifiable_scenario`：后继者只按architecture summary给request API标注`-> TokenPrediction`并尝试让result携intent，会重新遇到旧slots carrier矛盾或把ephemeral command塞进candidate；按Task 3A／4A／5具体signatures则不会。两个阅读入口给出不同接口名。
- `impact`：更具体的Spec、Task 3A／4A／5 interfaces、A36与transcriptions全都一致地选择`PredictionDecision`，所以没有真实实施fork，存在明确绕行，不阻断Task 3A；但architecture summary是高发现率入口，继续陈旧会误导后续维护，故不是nit。
- `recommendation`：把line 127改为同时区分request-side `PredictionDecision`与prequential `PredictionRecord`，明确`TokenPrediction`是candidate value DTO、只有decision可携optional `AnchorUseIntent`。这只是同步既定合同，不需要新裁决。
- `evidence_strength`：已确认；支持局部文档修正，不支持重开Task 3A设计。

除此之外，**无新Blocker或Major finding**。

## 相邻合同回归核对

- **R3四method与顺序**：未回归。Spec §6.0 `spec.md:266-270`明确`PredictionMethod`仍只有`history-exact`、`history-prefix`、`profile-calibrated`、`cold-start`；variant只是closed candidate key，不伪装第五种method。§6.1 `spec.md:274-283`仍按exact → prefix → profile → cold-start选第一个eligible method。Plan Task 3A `plan.md:348`和Task 4B `plan.md:396`同样禁止改四method。
- **Single-source prefix／suffix**：未回归。§6.2 `spec.md:287-293`仍以一个anchor actual为base；prefix deterministic／additive／multiplicative只是suffix variants，intent仍只指被选base source。Suffix只计append items，不重复top-level／anchor覆盖内容。Task 4A `plan.md:377-378`及A5完整值保持该语义。
- **Prequential**：未回归。§7.3 `spec.md:341-345`要求当前sample进入前生成全部candidate keys、point-in-time method champions／eligibility与global selected key，再按candidate key evaluate，最后learn。Request-side `PredictionDecision`不进入record；prequential challenger不产生anchor-use side effect。Task 4A `plan.md:373`、`plan.md:380-381`和A36一致。
- **Task 3 cardinality边界**：本轮只核相邻形态。`LearningSnapshot`仍single active identity／epoch；Task 3A扩的是candidate key／visual slot与ephemeral decision，不把private state或events投影进snapshot。没有重开Task 3其它reviewed机制。

## 被否路线保留核对

**忠实保留。** Spec §11 `spec.md:526-529`新增并明确否决四类相邻路线：按method覆盖／ordinal candidate identity会丢paired challenger事实或改变四method体系；visual-in-known／aggregate-pixel inference会破坏29＋6分槽及per-item ceil语义；把anchor-use intent持久进candidate会混淆request actual use与prequential challenger；median／nearest-median／derived aggregate prefix base会重开window、lineage、partial-prune和multi-source use semantics。最后一项仍以“当前无paired evidence证明median优于latest”为限定，没有把latest冒充普遍准确率真理。原采纳路线——coverage desc、newer observation desc、canonical sample key asc选单个actual并绑定同source intent——保持不变。

其它被否路线：**无**。本轮没有在上述既有记录之外新否决另一条可表达方案。

## 搜索面与证据边界

- 已读fixed Spec的§5、§6.0～§6.2、§7.3、§8.4～§8.5、§11、§12 A5／A8／A20／A23／A27／A32-P／A36／A39、§13及最新revision，避免只读grep命中行。
- 已读fixed plan的strategy summary、Task 3A、Task 4A、Task 4B相邻selection接口、Task 5及跨任务evidence table；已核status中Task 3A先于Task 4A的current sequencing。
- 未读／未复判Task 3 broad store implementation；未运行tests，因为本次被审对象是尚待实施的living contract amendment。Planned mutations的存在证明criterion具有目标方向，不冒充未来实现已通过。
- Dotdev commit因本leaf自动worktree隔离无法通过Git命令直接展示diff；本轮以开始／结束两次完整SHA相等、上一轮固定bytes记录和当前完整相关子句作fixed-state对照。该限制没有阻断原三项finding及相邻contract的复核，但本报告不声称审过commit中与上述范围无关的每个hunk。

## 最终counts与结论

- `original_findings_addressed: 3`
- `original_findings_open: 0`
- `new_finding_total: 1`
- `blocker_count: 0`
- `major_count: 0`
- `minor_count: 1`
- `nit_count: 0`
- `contract_verdict: APPROVED`

只剩T3APCRR-01这一项Minor，且具体Task signatures／Spec authority／acceptance transcriptions已经给出唯一接口，因此**不影响Task 3A实施，可以实施**。Task 4A并非当前可越过Task 3A直接实施；它应继续等Task 3A source完成、独立review并更新exact base，这是既定sequencing，不是本轮finding。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-07T14:09:26+00:00`
- `finding_total: 1`
- `blocker_count: 0`
- `major_count: 0`
- `minor_count: 1`
- `contract_verdict: APPROVED`
