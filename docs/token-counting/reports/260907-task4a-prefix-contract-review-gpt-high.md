# Task 4A prefix contract 独立审查

> 转录说明：reviewer因自动隔离无法写入active `.dev`路径，主会话按其三段最终回传正文转录；除本说明外，不改写原报告内容。

- `report_id`：`task4a-prefix-contract-review-gpt-high`
- `attempt_id`：`260907-task4a-prefix-contract-review-gpt-high-01`
- `reviewed_at_rev`：Spec SHA-256 `829f11ef3af40ebecd70ed8e67274b6c05df676339c6267fe2c88cca3a036717`；living plan SHA-256 `8752e05f3f116b530af5174f27b959db072b29754a247747a20edd37f23a2d5c`；approved plan SHA-256 `2aee01fd443a06c33af8a141214f41bb4b0502a4d3bed9838e64c213ef97544e`；Task 3 reviewed source commit `9ff21cef4d0f2377d1e60eba962e3b450584902c`。
- `reviewed_source_files`：`types.py` SHA-256 `1136f87e88543010c7eaf7de459a6caeef6a8a5306b1508b5f78a5722a5f31f6`；`learning_store.py` SHA-256 `bc92c9700461564b976a061cbf4cd537ad1bdf1fa621a67d9b2e4d23ca292fef`。

## 评审范围

本轮只审查固定bytes的living Spec §6.2及其2026-09-07最新修订记录，并逐项对照§5、§6.1、§6.2 suffix／demotion／recovery、§7、§8、§12 A19／A20／A36、§13、approved plan、living plan，以及Task 3 reviewed source中`PrefixAnchor`、`AnchorUseIntent`、`TokenPrediction`、`LearningSnapshot`与store projection／`record_anchor_use()`的合同。Task 3其它已review clean的实现、Task 4A尚未产生的source以及broad regression均不在本轮范围内。

## 总体 verdict

**NEEDS FIXES**。单anchor数值修正本身与用户选择、method顺序、fingerprint、suffix、prequential和现有prefix persistence cardinality一致；但Task 4A跨任务返回类型尚未闭合，且planned acceptance不能判红被本次修正明确否决的旧median行为。修复下列Major后才应派发Task 4A。

## Blocker

Blocker数：**0**。未发现Blocker。

## Major

### T4APCR-01：Task 4A没有已定稿的typed返回形态来携带`AnchorUseIntent`

- `finding_id`：`T4APCR-01`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:328-348`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:123-129`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:437-441`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:572`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:481-508`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/types.py:518-527`。
- `evidence`：Living plan把函数签名固定为`predict_exact_or_prefix(features, snapshot) -> TokenPrediction`，并要求exact／prefix result携带`AnchorUseIntent`；Task 4A文件清单却不含`types.py`。固定Task 3 source中的`TokenPrediction`是`frozen=True, slots=True` dataclass，字段中没有intent；`AnchorUseIntent`虽已存在并对PREFIX强制恰好一个source sample，但它没有连接到返回对象。现有合同既没有授权给`TokenPrediction`增加optional field，也没有命名`AnchoredPrediction` subtype、wrapper或`tuple[TokenPrediction, AnchorUseIntent | None]`之类的替代接口。
- `falsifiable_scenario`：只按Task 4A列出的production files实现函数并返回现有`TokenPrediction`，对一个prefix hit构造出的`AnchorUseIntent`无法附着到该slots对象；若实现者仅返回prediction，A36要求的intent丢失；若自行返回wrapper／subtype，函数签名与Task 5消费合同没有权威定义；若修改`types.py`，则越出当前Task 4A文件清单和对应transcription清单。可用`dataclasses.fields(TokenPrediction)`直接证伪“现有DTO已经有intent carrier”这一假设。
- `impact`：这是Task 4 pure policy到Task 5 queue／orchestrator的承重接口。派发时不闭合，两个合理实现会产出不同API，后续Task 5不是无法消费intent，就是被迫反向推导anchor provenance，违反A36。
- `recommendation`：在living Spec／plan中明确选择一种typed形态，并同步Task 4A文件清单与§13。若选择给`TokenPrediction`增加`anchor_use_intent: AnchorUseIntent | None`，应把`types.py`及对应DTO transcription test列入Task 4A；若选择新wrapper／subtype，应把实际函数返回类型、cold-start／profile时intent缺席语义和Task 5消费类型写明。该选择属于R4 delegated scope，不需要伪装成新的用户裁决。
- `evidence_strength`：已确认，足以据此阻止Task 4A派发；它证明合同未选择跨任务接口，不声称Python中不存在任何可表达的自选实现。

### T4APCR-02：现有planned acceptance无法区分“单个最新anchor actual”与已否决的跨anchor median

- `finding_id`：`T4APCR-02`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:532-575`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:275-287`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:577-596`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:328-348`。
- `evidence`：A5只判最长prefix与fingerprint失配；A20只判suffix candidate、demotion和recovery；A36只判intent purity／owner chain／failure semantics。Task 4A test bullet同样只列“最长prefix”，没有一个正确样本把两个同context、同item count、同prefix fingerprint但actual不同的anchors同时放进snapshot，并把选中prediction数值与选中intent source逐字段绑定。§13只笼统写“§4～§6 prediction合同”，没有点明本轮新增的单anchor数值／provenance转录。
- `falsifiable_scenario`：Snapshot含旧anchor A：actual 100、`observed_at_us=1`；新anchor B：actual 120、`observed_at_us=2`；两者对query具有相同context、item count和prefix digest。错误实现返回`median(100, 120)=110`，同时仍可发出只指向B的合法单source `AnchorUseIntent`并选择`history-prefix`。它能通过当前A5、A20和A36各自陈述的断言，却违反§6.2必须返回B actual 120的修正。这正是“错误bytes未改但planned evidence仍全绿”的近邻失败。
- `impact`：本轮修正的唯一行为差异没有可判否oracle；Task 4A即使照旧实现“prefix actual median”，也可能在计划所列测试下被判通过，令数值与provenance再次分裂。
- `recommendation`：把上述双anchor样本加入A5或A20，或新增独立criterion，并在Task 4A test bullet与§13 `test_prediction.py` transcription中逐字登记。正确断言必须同时覆盖selected unscaled prediction的anchor component等于120、intent source恰为B、suffix只加一次；单变量mutation改为对所有matching anchors取median时必须红。再加一个相同timestamp的sample-key tie control，覆盖最终tie分支。
- `evidence_strength`：已确认，足以据此要求合同／planned evidence同步；本轮没有运行尚不存在的Task 4A tests，也不声称现有Task 3 store tests应承担pure predictor oracle。

## Minor

### T4APCR-03：§6.2没有把最终sample-key tie的方向与字段比较规则写成唯一合同

- `finding_id`：`T4APCR-03`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:275-278`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:443-453`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_store.py:4078-4092`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/src/app/tokenization/learning_store.py:5196-5201`。
- `evidence`：§6.2只写“相同长度按newer observation、sample id排序”，没有说明sample key按哪个方向、三字段如何比较。Task 3 store projection当前采用`observed_at_us`降序，再按`process_boot_id` UTF-8 bytes、`request_id` UTF-8 bytes、numeric `attempt_index`升序；§8.5也为prune写出了BINARY text＋numeric integer的canonical字段规则，但§6.2没有引用它，且`LearningSnapshot` DTO本身不验证tuple已经按store顺序排列。
- `falsifiable_scenario`：两个matching anchors拥有相同`item_count`与`observed_at_us`，actual分别为100和120，sample keys只在`attempt_index=2`与`attempt_index=10`上不同。按numeric ascending、numeric descending或序列化JSON lexical order会选择不同actual；这些实现都可声称自己执行了未定向的“sample id排序”。
- `impact`：仅在长度与微秒timestamp同时相等时影响prediction，核心method和常见路径可绕行，因此定为Minor；但它仍会破坏跨进程确定性与数值／provenance一致性，不是风格偏好。
- `recommendation`：§6.2直接规定最终tie复用§8.5 canonical sample-key ascending order，或在§5集中定义一个所有prediction／prune共同引用的sample-key total order；T4APCR-02的tie control同步转录该方向。
- `evidence_strength`：已确认，足以据此补合同精度；未观察到运行时碰撞频率，因此不把它升级为生产高频故障。

## 一致性核对结果

- **§5 fingerprint与identity**：通过。修正没有放宽same LearningIdentity／active epoch／context／rolling-prefix匹配，也没有把unknown top-level、item order或tokenizer等维度从identity移除。
- **§6.1 method order**：通过。`history-exact`仍唯一使用最近5 actual median并始终先于prefix；prefix数值修正没有重排exact → prefix → profile → cold-start。
- **§6.2 suffix／demotion／recovery**：通过。单anchor actual只是prefix base；suffix仍只计append内容，candidate minimum、paired window、strict demotion和recovery规则未缩减。
- **§7 prequential**：通过。单anchor selection发生在当前label进入history之前；current sample仍不得污染自己的anchor、candidate或error。
- **§8 persistence与Task 3 cardinality**：数值合同通过。固定source中`PrefixAnchor`恰有一个`actual_tokens`和`sample_key`，store从同一source sample重建两者，projection按最大coverage／newer／sample key排序，PREFIX intent恰好一个source。跨任务返回carrier另见T4APCR-01。
- **§12 A19**：无语义交集，count error wire未被本修正改变。
- **§12 A20／A36**：规则本身不冲突；A20保留prefix state machine，A36的单source intent与修正一致。其证据组合缺少本轮差异的判别力，见T4APCR-02。
- **§13 transcription map**：没有已存在的Task 4A test transcription需要当场改source test；`test_prediction.py`尚未创建。planned transcription需在派发前明确新增双anchor数值／provenance控制，见T4APCR-02。
- **用户裁决与学习范围**：通过。R3选择的是longest-prefix actual＋suffix，没有裁定跨anchor median；单anchor latest observation没有删除exact、prefix、profile或cold-start，也没有改变它们的eligibility顺序。旧anchors仍保留给prequential challenger、suffix／profile evidence和bounded persistence；本修正没有缩减历史精进或same-attempt learning。
- **Approved plan与living plan**：Approved plan SHA所对应的点时文本仍在line 107写“prefix actual median”，但其line 10明确规定获批后由`.dev/docs/token-counting/plan.md`承接，living plan line 2又明确behavior以current Spec为准；因此本轮把它视为被living plan显式取代的点时输入，不把其旧句另报finding。Living plan没有重复旧median句，但必须补齐T4APCR-01／02所述Task 4A接口与验收转录。

## 方案比较与采纳／否决

### 采纳：全序选择最新单anchor

在same identity／epoch／context与query rolling prefix匹配后，先取最大`item_count`，再按newer observation与明确的sample-key total order取一个source；prediction使用该source actual＋suffix。该路线直接满足R3的“longest-prefix actual＋suffix”，使数值和`AnchorUseIntent` provenance一一对应，与Task 3 `PrefixAnchor`／`record_anchor_use()` cardinality一致，并对计费漂移优先采用更新观测。采纳强度：足以实施，但须先关闭本报告两项Major。

### 否决：跨同fingerprint prefix anchors取median并扩宽intent source keys

这条路线在另立合同后可表达，并非数学上错误；但当前`AnchorUseIntent`明确禁止PREFIX多source，store匹配与use-order更新也按单source成立。采用它必须同时决定median窗口上限／奇偶数值、source lineage、intent大小、prune后部分source缺失及`record_anchor_use()`原子匹配规则，重开Task 3 reviewed interface。当前没有prefix prequential evidence证明median优于latest，R3也只要求actual＋suffix而未要求aggregation，因此本轮否决其作为Task 4A合同。若未来same-prefix latest的paired median APE持续劣于bounded median challenger，应以该运行证据重开，而不是现在偷偷扩宽cardinality。

### 否决：用“最接近median的单个source”或derived aggregate anchor维持单source外形

选择最接近median的source会悄悄把“newer observation”改成另一套selection policy；derived aggregate anchor则不再是现有`PrefixAnchor`所表达的某个actual source，必须新增lineage和persistence类型。两者都没有比latest single anchor更强的当前证据，且会模糊“prediction base来自哪次upstream actual”这一承重provenance，故不采纳。

## 搜索面与未执行项

- 已在审查开始与报告写入前两次计算完整Spec SHA；两次均为`829f11ef3af40ebecd70ed8e67274b6c05df676339c6267fe2c88cca3a036717`，没有moving snapshot。
- 已读Spec §1～§2、§5～§15相关完整子句，approved plan、living plan、status中Task 4A projection，以及Task 3固定source的`types.py`、`learning_store.py`关键projection／intent路径和对应Task 3 unit transcriptions。
- 已确认目标worktree loose ref指向`9ff21cef4d0f2377d1e60eba962e3b450584902c`，并记录被读source文件hash；未把共享main工作树或本reviewer自己的隔离worktree冒充Task 3 source。
- 未运行broad tests、live upstream、cassette或Task 3回归。理由是本轮对象是固定合同与已reviewed type cardinality，Task 4A tests尚未创建；本报告不声称任何runtime行为已通过。
- 未复审Task 3 schema、cancellation、migration、prune和其它已review clean内容；只读了prefix selection、snapshot cardinality和anchor-use承重接缝。

## 整体判定

合同结论为**NEEDS FIXES**。零Blocker不等于可派发；两项Major分别使跨Task接口和本轮行为差异的oracle未闭合。关闭T4APCR-01与T4APCR-02并同步T4APCR-03后，再用新Spec完整SHA进行限定复核；不需要重跑Task 3 broad review。

## 我最没把握的三个判断

1. **T4APCR-01定为Major而非Blocker**：我认为存在wrapper／subtype等可表达路线，所以不是技术上无法继续；但合同尚未选择跨Task API，足以阻止派发。若上级能指出既有、已授权且被Task 5明确消费的result type，应该撤销或降级此finding。
2. **Approved plan旧median句不另立finding**：判断依据是approved plan line 10与living plan line 2已经显式完成authority handoff。若项目把`~/.claude/plans/serialized-moseying-corbato.md`仍视为并行living implementation authority而非点时输入，则该旧句应并入T4APCR-02的同步范围。
3. **T4APCR-03定为Minor**：合同分歧只在相同prefix长度和相同微秒timestamp的最终tie出现，且Task 3 store已有可复用顺序。我没有production碰撞频率，因此不把影响扩大；若多进程实际常产生同timestamp anchors，应重定为Major。

## 执行本契约时遇到的摩擦

- Harness拒绝从本reviewer隔离worktree执行指向共享main的Git命令。为避免错树声称，本轮改用共享main的worktree ref文件确认Task 3 commit，并直接读取用户指定Task 3 worktree绝对路径及文件hash；该限制没有阻断合同审查。
- 目标Task 3 worktree没有可用CodeGraph index；已先尝试CodeGraph并收到明确“未索引”结果，随后按规则使用`Read`与定向`rg`。未因此缩减承重范围。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-07T13:30:48+00:00`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 2`
- `minor_count: 1`
- `nit_count: 0`
- `contract_verdict: NEEDS FIXES`
