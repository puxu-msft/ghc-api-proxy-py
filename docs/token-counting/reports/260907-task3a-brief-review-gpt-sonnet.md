# Task 3A implementation brief 评审

> 转录说明：reviewer因自动隔离无法写入active `.dev`路径，主会话按其完整最终回传正文转录；除本说明外，不改写原报告内容。

- `report_id`：`task3a-brief-review-gpt-sonnet`
- `attempt_id`：`260907-task3a-brief-review-gpt-sonnet-01`
- `reviewed_at_rev`：brief SHA-256 `88b5518f9727bb3a76e66c9239c81d59678845e416ca5901d381f919a2c6b856`；Spec SHA-256 `f734f8bfe70c8153fe75e609a291c9f3cf2fdcf73e17b03a438cee6072957cdd`；plan SHA-256 `3dc7d33595d1412d2779fc034ce400d22a80d95b9ee0f868746e5f3a2b74e664`；source base `a2779b644844dcf6cc36454c12b85f4e9f09c2e8`
- 引用报告：prefix rereview SHA-256 `75ffc629683544bd2fb20701bba04602d3e042f41a5bf1c08a8157c33fdcc6b1`；prediction rereview SHA-256 `75970949b9680ea6b91d505643bec6735a87e7f3eae0442706666b58166e2db2`
- 交付方式：自动隔离阻止本leaf在共享main执行Git操作，本轮按允许的fallback完整内联回传，未写 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-brief-review-gpt-sonnet.md`

## 评审范围

唯一被检对象是 `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md`。判据来自 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`、`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`、两份指定终态contract review，以及exact source base中Task 3的DTO、feature producer、worker、V1 schema、codec、graph validation、event和per-method bounds入口。

开始与交付前各复算一次三个完整SHA，两次均与指定值相等，未发生moving snapshot。未修改文件，未运行broad tests。

## 总体 verdict

**NEEDS FIXES**

- Blocker：0
- Major：2
- Minor：0

在修正以下两项前，不应派Task 3A implementer。

## Major

### `task3a-brief-review-gpt-sonnet-01`：DTO允许把represented exact或cold-start错误标为不合格

- `severity`：Major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:44-48`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:87-95`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:267-282`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:558,570,582`
- `evidence`：Brief只要求从represented champions中选择按四method顺序出现的第一个`eligible_for_selection=True` champion，却没有转录Spec中两个无条件eligibility事实：represented `history-exact`表示active-epoch exact hit，必须始终eligible；`cold-start`是最终fallback，始终eligible。当前列出的DTO invariants和required tests都没有拒绝这两个错误状态。
- `counterexample`：构造`history-exact/median`和`cold-start/deterministic`两个candidates，champions分别为exact false、cold true，`selected_key`取cold。它满足brief现有全部规则：candidate keys唯一、每个represented method恰有一个champion、champion指向存在且同method的candidate、selected是首个eligible champion；但它违反Spec §6.1“Active-epoch exact hit始终合格”，并把本应选择的exact降级成cold。另一个同形反例是profile champion true、cold champion false、selected profile；selected结果暂时不变，但record持久化了一条错误的point-in-time cold eligibility事实。
- `false-green`：Brief要求的cold-only正控会自然把cold champion设为true，无法识别“有更高优先级eligible method时把cold错误设false”；“selected非首eligible”也识别不了exact被先改成false的状态。
- `minimal_fix`：在§1明确增加两条`PredictionRecord` invariant：represented exact champion必须`eligible_for_selection=True`；cold-start champion必须`eligible_for_selection=True`。在required tests和persistent corruption tests中分别增加exact false与cold false负控；prefix和profile仍允许true／false，由其点时状态决定。
- `conclusion_strength`：confirmed。足以阻止按当前brief派实现，因为当前source review oracle会接受Spec禁止的record。

### `task3a-brief-review-gpt-sonnet-02`：首版visual DTO与Task 8之间缺少可表达resize／limit的明确接力边界

- `severity`：Major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:56-68`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:167-197`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:349-355`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:510-527`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-prediction-dto-gap-review-claude.md:159-180`
- `evidence`：Brief只让capability DTO携带formula revision和positive patch width／height，并要求analyzer直接对payload dimensions执行patch-grid。Spec §4.2则要求immutable capability snapshot承载并执行descriptor的resize／limit／visual formula。原visual gap review也明确要求DTO至少携带公式所需resize／limit参数。与此同时，plan Task 8要从exact descriptor生产同一个Task 3A `TokenizationCapabilities`，但Task 8的owned files不含`src/app/tokenization/types.py`。因此当前brief既禁止Task 3A表达resize／limit，又没有给Task 8修改该DTO的明确ownership。
- `counterexample`：对一张会触发descriptor resize或pixel limit的图，Task 3A定义的DTO只能计算`ceil(raw_width / patch_width) × ceil(raw_height / patch_height)`。Task 8仅修改catalog adapter和`features.py`时，既不能从该DTO读取任何resize规则，也不能把完整provider descriptor传入pure worker；若硬编码provider resize，便破坏“exact descriptor immutable snapshot”边界，若继续直接patch raw dimensions则违反Spec。
- `impact`：A18的56×84→6、42×112→8仍可正确实现，legacy integer wrapper也能保持不变；问题不在A18算术，而在brief把这份synthetic首版seam写成了可供Task 8直接消费的完整capability contract。后续实现者只能静默扩Task 8 scope、硬编码provider行为，或留下不符合Spec的公式。
- `minimal_fix`：不要在Task 3A猜测尚未核定的resize数值或PDF公式。Brief应明确二选一：其一，把首版`PatchGridVisualFormula`标成尚未接入真实descriptor的synthetic／unresized formula kind，并在plan／Task 8 ownership中显式加入`src/app/tokenization/types.py`，要求Task 8在接生产catalog前以已核provider事实扩展closed resize／limit representation；其二，若当前已有足够authority，则先在Spec固定resize／limit字段及语义，再让Task 3A DTO承载它们。无论选哪条，都应明确Task 3A source review只批准A18分槽、presence、pickle和V1 persistence，不冒充真实descriptor公式已经闭合。
- `conclusion_strength`：confirmed scope hole；确切采用哪一种接力方式属于brief／plan作者的实现编排选择，不需要用户产品裁决。

## 已核无问题的承重面

- `PredictionCandidateKey`七种closed pair、四个`PredictionMethod`及优先顺序完整。
- `MethodChampion`不重复保存自由method字段，避免与`candidate_key.method`冲突。
- `TokenPrediction`和`PredictionEvaluation`保留现有`method`并与新增`candidate_key`交叉验证，是对Task 3现有store的最小兼容演进。
- `PredictionRecord.selected`改为由`selected_key`查得的property，能消除重复真值；exact source中所有相关生产消费者都位于owned `types.py`／`learning_store.py`及owned tests内。
- V1修改面已覆盖samples visual column、prediction selected variant、champions／candidates JSON、evaluation PK／CHECK／index、event evaluation codec、manifest／DDL digest、all-epoch graph、snapshot uniqueness及per-candidate-key newest128的validate与prune入口。
- 这些DDL／codec变更不必增加raw `aiosqlite` call site，因此保持108 semantic bases／204 expanded action IDs可实现。
- Legacy `estimate_responses_input()`和worker public integer路径仍取`known_tokens`，不在Task 3A提前把visual加入public结果；Task 4A继续拥有cold-start消费与finalization。
- Exact base建立、owned tracked paths、禁止shared-main操作、前台mutation＋文件快照恢复、精确pathspec commit和不push边界总体安全。

## Brief新增被否路线是否需要进入living Spec

无。Brief没有在living Spec §11现有记录之外形成一条已经完成裁断的新方案路线。第二项finding要求补的是跨Task ownership和阶段边界，不是新增产品级被否路线。

## 搜索面与证据边界

已完整读取fixed Spec、plan、两份指定终态contract review及原visual DTO gap review。对exact source base静态核查了：

- `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/types.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/features.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/estimators.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/worker.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/learning_schema.py`
- `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/learning_store.py`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/tokenization/test_features.py`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/tokenization/test_learning_store.py`

另以exact commit全仓检索DTO消费者、feature constructors、candidate/evaluation codecs、event JSON、bounds和visual metadata入口。没有运行source tests或mutation；本报告评的是brief能否唯一指导未来实施，不声称实现已经存在或测试已经通过。

## 我最没把握的三个判断

1. 第二项定为Major而非Minor，置信度中高。若coordinator已经在别处明确授权Task 8修改`types.py`，scope-hole部分可降级；但该授权不在本brief或fixed plan中，且Task 3A首版公式不代表最终descriptor公式的边界仍需写明。
2. Exact／cold eligibility应由`PredictionRecord` constructor强制，置信度高。即使未来predictor总能正确赋值，V1 startup graph validation仍需要拒绝raw corruption，不能只信producer。
3. 未发现108／204 action-ID变化需求，置信度高但范围仅限静态调用面。未来实现若为新schema另加introspection或SQL await，必须重新判断，不能引用本报告为永久豁免。

## 执行本契约时遇到的摩擦

自动worktree隔离拒绝在共享main执行Git命令，因此exact source通过隔离worktree共享object database读取，authority文档通过共享main绝对路径读取。三个authority SHA在首尾均一致；该限制不影响两项finding，但本轮未核共享main的dirty WIP归属，也未修改任何文件。

## 交付声明

- `delivery_complete`：true
- `completed_at`：2026-09-07
- `finding_total`：2
- `blocker_count`：0
- `major_count`：2
- `minor_count`：0
- `verdict`：**NEEDS FIXES**
- `implementer_dispatch_allowed`：false
