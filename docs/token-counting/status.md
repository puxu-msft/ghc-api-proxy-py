# Token-counting status

**Tasks 1～4B-P completed；reviewed source is archived and Task 4B-P squash integration is in current main at `4fe53d0fe8102e35efeea53ce3024ffadb6823d4`；Tasks 4B～11 remain pending。**

状态快照：2026-09-07，authority snapshot为[spec.md](spec.md) SHA-256 `fdf63872b906dc87ec44eb4627c199552cc904d730add186600cc5095c639df9`与[plan.md](plan.md) SHA-256 `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`；Task 4B-P authority correction、source、merged-state review和main-side gate均通过，reviewed source为`archive/260907-token-prefix-residuals → d10121c9`，main squash为`4fe53d0f`。

## 2026-09-24 止血：learning store读取成本

- **症状**：4,469 samples／233.5 MiB（其中prefix digest arrays 182 MiB——同一会话每轮都把整条前缀链再存一遍）时，一次whole-state read约22 s（decode占90%以上），startup 67.9 s，每个learning transaction读3～4次，count_tokens在每次commit后的reader refresh里等一次full read（2026-09-22 p50 18.8 s）；4141 RSS 1.95 GB。
- **止血**（main `f4b41229`；[spec.md](spec.md) §8.2／§8.3／§8.5与2026-09-24修订记录）：sample caps降为256／512；只超出可剪枝caps的state不再是invalid，由writer在migration／sample／prune transaction中剪回；逐行decode按完整stored values复用；prune planner一次性计算victim keys。同一副本修复后startup 3.3 s、full read 0.35 s。
- **上线须知**：首次以新caps启动的进程要把既有store剪到512个samples，按当前规模约1分钟且期间未ready；之后恢复秒级启动。
- **仍待根治**：每个transaction仍读取全部retained rows（只是不再重复decode），caps因此不能再放宽；根治方向是validated state的增量维护、prefix chain不再逐sample全量持久化、writer自己commit后reader不再重读。

## 当前阶段

Tasks 1～2保持稳定：living authority两路review均为0 blocker／0 major；Task 2 reviewed source `b7603cb6e98425728fc2a70a4e12f243b7e3333b`已归档到`archive/260907-token-features`并以main squash `5d5eb3d817d94cd706f9ac5908ce5dc6589fe599`集成，aggregate patch-id为`a0a14d9b674a244b9429b79c2171b46dfe8bf702`。

Task 3 source implementation／review已完成。最终reviewed source为`9ff21cef4d0f2377d1e60eba962e3b450584902c`，由`archive/260907-token-learning-store`保留；Task 3A reviewed source为`c59cdd66a008f8ae8248b781a0c74fc36e129287`，Task 3B reviewed source为`e2461a6ea17c968201bb1e0c2fb33be87be901e8`并由`archive/260907-token-learning-prerequisites`保留。三者以main-side squash `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`进入current main；merged full gate为Ruff clean、Pyright 0、3,375 passed／2 skipped／1 warning、coverage 90.35%。Current main在integration前已前进到`42fb2329`并保留untracked WIP；本次使用临时main-side worktree处理path overlap，未修改或清理shared untracked。

Task 4A派发前的两路初审触发Task 3A prerequisite。Prefix scoped re-review已关闭原3项finding，结论0 Blocker／0 Major／1 Minor；其plan-summary Minor已同步。Prediction scoped re-review关闭visual finding，但以cold-only record反例保持candidate／decision findings open，并新增1 Blocker／1 Major／1 Minor：champions须按represented methods量化、candidate-key与method-champion error sequences须分槽、plan上层active restatements须同步、tuple carrier否决理由须进入living source。第二轮prediction scoped re-review已关闭全部contract findings，终态0 Blocker／Major／Minor／Nit。随后fresh implementation-brief review发现0 Blocker／2 Major：DTO仍可接受represented exact／cold false；synthetic unresized formula与Task 8真实resize／limit representation之间缺明确ownership接力。Spec／plan／brief已增加unconditional eligibility、false corruption controls，并把Task 3A公式限定为synthetic mechanics、Task 8显式拥有`tokenization/types.py` production extension。Brief scoped re-review已关闭原2项Major，结论0 Blocker／Major／1 Minor并允许派发；唯一Minor已把报告合同从“五个”修成“上述六个mutations逐项列名”。最终brief SHA为`6f98acb6138451fdb4c08031075f274d0d2921244998dc446e81bad2e63dfed2`。Task 3A implementer已在exact base `a2779b644844dcf6cc36454c12b85f4e9f09c2e8`上提交candidate `56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8`，commit恰含10个owned paths且worktree无tracked dirt。Initial implementation report `c13222bf…`记录focused 11、learning-store 368、tokenization 533、Ruff clean、Pyright 0及六个mutations判红／恢复；这些是implementer evidence。Independent source review重跑focused17、store368、tokenization533、Ruff与Pyright并确认无残留process／DB，结论0 Critical／2 Important：`LearningSnapshot`接受record中不存在的extra candidate-key evaluation；duplicate event candidate evaluation经DTO／decoder／set graph折叠后使corrupt DB startup accepted。Fix round 1新增commit `c59cdd66a008f8ae8248b781a0c74fc36e129287`，只改3 paths；source re-review关闭T3A-SR-01／02，Spec／quality均APPROVED，0 Critical／Important／Minor，独立535 tests、Ruff／Pyright通过且无进程／DB残留。Reviewed source archive为`archive/260907-token-prediction-persistence → c59cdd66`。该source已squash到stacked integration commit `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`，parent为`a2779b6`，source／squash patch-id均`6a605b76f192282fe2f29c1fa795323d32930388`且tree exact-equivalent；integration full gate为Ruff clean、Pyright 0、3,358 passed／2 skipped／1 warning、coverage 90.33%。Task 4A initial brief `35d5db83…`的独立review发现2 Blocker／6 Major／1 Minor，source未启动。Blockers：whole-request `capability_visual_tokens` all-or-none，无法在旧prefix visual为None时计出新append item的visual contribution；prefix demotion／recovery只存在于会随sample prune删除的records，无法跨prune／restart保持state。其余findings要求all-available candidates、learned suffix baseline、historical availability／single-base、ProfileKey隔离、latest8／newest31、diagnostic absence controls与canonical candidate order落入authority。Task 3B design report `97c37795…`提出per-item contributions、compact 788-item codec、global `committed_order`、per-ProfileKey checkpoint、capacity epoch rollover和Task 4B-P分片。Fresh architecture review发现1 Blocker／3 Major／1 Minor：cross-identity rollover事务未闭合、logical policy与store stamping混层、contribution没有exact conservation、4B-P未进入真实tracker、ProfileKey hash identity不完整。Design amendment 1 `97b9964e…`关闭AR-02～05，但原reviewer保留1 Major／2 Minor：global cap满且current identity prior rows为0时rollover没有容量收益；drift command epoch未定；FixedContext codec与pair-index traversal不完整。Amendment 2 `e0da7530…`关闭此前remaining Major／Minors，但第二轮review发现1 Major：required checkpoint outcome未覆盖duplicate／rejected／failed，且capacity transition有standalone／nested双权威。Amendment 3 `d7ae80f2…`增加NotAttempted／NotCommitted与完整main-outcome矩阵，删除standalone capacity field；第三轮review结论`APPROVED DESIGN`，0 Blocker／Major／1 wording Minor。该Minor已在current Spec把NotCommitted边界写成“policy callable已进入但transaction未commit”。Living authority已写入per-item／committed-order／checkpoint／capacity／outcome与3B→4A→4B-P→4B→4C顺序，current Spec `5d9477dd…`／plan `bea5e753…`。Prior independent authority review结论`NEEDS FIXES`：0 Blocker／4 Major／1 Minor，Task 3B source authorization denied。Authority repair已写入当前 Spec／Plan，并由`260907-subagent-authority-repair-review.md`复审为`READY`，0 Blocker／Major、1 non-blocking Minor；当前下一步是生成并独立review Task 3B implementation brief，source仍未启动。

## 唯一下一步

生成Task 4B implementation brief并独立review。Task 4B负责profile candidates、promotion和per-ProfileKey 16／8 eligibility checkpoint policy；不得回写已完成的Task 4B-P variants或Task 4A predictor。详见[HANDOVER.md](HANDOVER.md)。

## Task 1终态证据

| 证据 | 终态 |
|---|---|
| Initial authority | `ec292d5`。 |
| Review-gap fixes | `7fb43f4`与`c281b29`。 |
| Reviews | 两路0 blocker／0 major；DISP-01／DISP-02 closed。 |
| Production implementation gate | open。 |

## Task 2终态证据

| 证据 | 结果 |
|---|---|
| Source baseline | `a703543399851da06868cd0f50f37d534ba1e165`。 |
| Reviewed source／archive | `b7603cb6e98425728fc2a70a4e12f243b7e3333b`；`archive/260907-token-features`指向同一commit。 |
| Main squash | `5d5eb3d817d94cd706f9ac5908ce5dc6589fe599`。 |
| Aggregate patch identity | Source series与squash patch-id均为`a0a14d9b674a244b9429b79c2171b46dfe8bf702`。 |
| Task review | 0 Critical／Important。 |
| Main-side gate | Ruff clean；Pyright 0；2,968 passed、2 skipped、1条pre-existing Starlette warning；coverage 90.42%。 |

## Task 3 review round 1

| Finding | 状态 | Authority amendment |
|---|---|---|
| T3-01 cancellation-safe ownership | contract-authored | 所有`aiosqlite`queue action使用confirmed-completion helper；区分pre-commit rollback和post-COMMIT committed cancellation outcome。 |
| T3-02 V1 authenticity | contract-authored | Version＋manifest digest、完整schema introspection、composite links、all-epoch decode及typed no-write startup failure。 |
| T3-03 concurrent fresh migration | contract-authored | Existing path先read-only inspect；WAL async retry；`BEGIN IMMEDIATE`后重读；reader migration后open。 |
| T3-04 durable free text | contract-authored | Closed `LearningReasonCode`／`DriftReasonCode`及typed metadata；raw／exception text仅进DB外best-effort warning。 |
| T3-05 prune policy | contract-authored | `record_anchor_use()` hook及sample／global identity的exact total order；sample write不冒充actual use。 |
| T3-06 test／oracle gaps | contract-authored | 增加cancellation、manifest、migration、composite link、free-text、prune、independent snapshot、duplicate／identity和thread-provenance controls。 |
| T3-07 tracked `uv.lock` | contract-authored | Task 3只改`pyproject.toml` dependency；撤销tracked lock requirement，保持人控release contract与`.gitignore`。 |
| T3-08 revision／prune order | contract-authored | 固定transition writes→victims／affected→identity＋global revisions→cascade prune→post-transition event→commit。 |
| T3-09 thread provenance | contract-authored | Connector factory＋`sqlite3.Connection` subclass直接记录connect／override close；UDF仅证明query／apply。 |

`contract-authored`只表示living docs已修订，不冒充reviewer已经关闭finding。Candidate source仍保持round-1 reviewed snapshot，等待第二轮authority review。

## Task 3 contract re-review round 1

| Finding | 状态 | Authority amendment |
|---|---|---|
| C-01 snapshot type conflict | contract-authored | Store-private `ValidatedPersistentState`验证all epochs／events；public `LearningSnapshot`只含one active identity／epoch且无events／inactive rows；A32拆为两个independent oracles。 |
| C-02 anchor-use owner gap | contract-authored | Task 4 pure `AnchorUseIntent`→Task 5／pipeline queue→Task 3 `record_anchor_use(intent)`；PRUNED no-op与queue-failure last-confirmed semantics明确。 |
| C-03 revision-order oracle | contract-authored | A35用BEFORE DELETE trigger／transaction trace判定identity＋global revisions先于cascade，event后于prune且使用post-transition revision。 |
| C-04 cancellation task semantics | contract-authored | `StoreOperationCancelled`继承`asyncio.CancelledError`并携带phase／committed observation；A26断言enclosing task cancelled。 |
| C-05 canonical prune ties | contract-authored | Persist UTC Unix microseconds `observed_at_us`；sample／identity ties固定BINARY text与numeric integer field order。 |


## Task 3 source fix round 1 review

| Finding | 状态 | Authority amendment |
|---|---|---|
| SF1-01 close lock ownership | contract-authored | `close()`标记CLOSING；lifecycle／reader／writer LOCK_WAIT confirmed ownership；fixed lock order、blocked-cancel cleanup与concurrent idempotence。 |
| SF1-02 table-column collation | contract-authored | TableManifest增加independent fixed normalized DDL digest，覆盖column COLLATE／CHECK／STRICT；NOCASE fake必须mismatch且bytes unchanged。 |
| SF1-03 retained graph closure | contract-authored | 每sample mandatory record＋exact anchor；candidate↔evaluation、prefix iff、event facts和inactive metadata references全部闭合。 |
| SF1-04 false-green tests | contract-authored | Complete named cancellation ledger、dual-empty migration barrier、independent full private objects及逐项schema／graph mutations；新增A37～A39。 |


## Task 3 contract round 3

| Finding | 状态 | Authority amendment |
|---|---|---|
| SF2-01 evaluation facts／diagnostics | contract-authored | Sample＋record＋actual保留完整可重建prequential facts；diagnostic rows仅newest128 mandatory，older absence allowed；160 drift从record＋actual重建。 |
| SF2-02 independent action-ID oracle | contract-authored | Spec §8.1.1拥有fixed action table；test literal、production ledger和runtime confirmed-action trace三方ID set相等；raw-call mapping另证registered coverage，matrix从test literal生成。 |

## Task 4A preflight reviews

| Review | 点时结论 | 当前处置 |
|---|---|---|
| [Prefix contract review](reports/260907-task4a-prefix-contract-review-gpt-high.md) | Spec `829f11ef…`；0 Blocker／2 Major／1 Minor。 | Single newest anchor保持；增加typed decision、100／120 median mutation和canonical tie。 |
| [Prediction DTO gap review](reports/260907-task4a-prediction-dto-gap-review-claude.md) | Spec `829f11ef…`；2 Blocker／1 Major。 | 新增candidate keys／method champions、persisted visual slot及ephemeral decision；拆出Task 3A。 |
| [Prefix scoped re-review](reports/260907-task3a-prefix-contract-rereview-gpt-high.md) | Spec `c81d9046…`；APPROVED，原3项closed，0 Blocker／0 Major／1 Minor。 | Plan summary Minor已同步；该review stream终态clean。 |
| [Prediction scoped re-review](reports/260907-task3a-prediction-contract-rereview-claude.md) | Spec `c81d9046…`；visual closed，candidate／decision open；1 Blocker／1 Major／1 Minor。 | Cold-only represented-method cardinality、双error sequences、active restatements与tuple disposition触发第二轮修订。 |
| [Prediction second scoped re-review](reports/260907-task3a-prediction-contract-rereview-2-claude.md) | Spec `f734f8bf…`；APPROVED，0 Blocker／Major／Minor／Nit。 | 上一轮3项new、原2项remaining和prefix summary Minor全部closed；Task 3A contract可实施。 |
| [Implementation brief review](reports/260907-task3a-brief-review-gpt-sonnet.md) | Brief `88b5518f…`；NEEDS FIXES，0 Blocker／2 Major。 | Exact／cold eligibility与synthetic formula handoff触发Spec／plan／brief修订。 |
| [Implementation brief scoped re-review](reports/260907-task3a-brief-rereview-gpt-sonnet.md) | Brief `f2db75d3…`；APPROVED，0 Blocker／Major／1 Minor。 | 原2项Major closed；mutation report count Minor已在brief `6f98acb6…`修正，implementer dispatch allowed。 |
| [Source review](reports/260907-task3a-source-review-gpt-high.md) | BASE `a2779b6`→`56ec5e7`；NOT APPROVED，0 Critical／2 Important。 | Snapshot extra candidate与event duplicate candidate findings accepted；触发fix round 1。 |
| [Source fix 1](reports/260907-task3a-source-fix-1-claude.md) | BASE `56ec5e7`→`c59cdd66`；3 paths。 | Subset validation与duplicate event raw corruption regressions implemented。 |
| [Source re-review](reports/260907-task3a-source-rereview-gpt-high.md) | Fix `c59cdd66`；APPROVED，0 Critical／Important／Minor。 | T3A-SR-01／02 addressed；reviewed source archived and squash integration gate passed。 |
| [Task 4A brief review](reports/260907-task4a-brief-review-claude.md) | Brief `35d5db83…`；NEEDS FIXES，2 Blocker／6 Major／1 Minor。 | Task 4A source未启动；新增Task 3B prerequisite。 |
| [Task 3B prerequisite design](reports/260907-task4a-prerequisite-design-gpt-high.md) | Design `97c37795…`；DESIGN READY，2 confirmed blockers＋1 compact-codec major。 | 进入fresh architecture review。 |
| [Task 3B architecture review](reports/260907-task4a-prerequisite-design-review-grok.md) | NEEDS FIXES，1 Blocker／3 Major／1 Minor。 | AR-01～05全部采纳；未写authority／source。 |
| [Task 3B design amendment 1](reports/260907-task3b-design-amendment-1.md) | Amendment `97b9964e…`。 | Current-identity rollover、store stamping、exact conservation、task#27、canonical JSON identity。 |
| [Amendment 1 re-review](reports/260907-task3b-design-amendment-1-review-grok.md) | NEEDS FIXES，0 Blocker／1 Major／2 Minor。 | AR-02～05 closed；zero-benefit capacity／drift branch、FixedContext codec、pair-index sort仍开。 |
| [Task 3B design amendment 2](reports/260907-task3b-design-amendment-2.md) | Amendment `e0da7530…`。 | Typed zero-benefit rejection、drift NoChange、store outcome、context codec、committed-order sort。 |
| [Amendment 2 re-review](reports/260907-task3b-design-amendment-2-review-grok.md) | NEEDS FIXES，0 Blocker／1 Major。 | Capacity mechanics closed；required outcome main-matrix／transition authority仍开。 |
| [Task 3B design amendment 3](reports/260907-task3b-design-amendment-3.md) | Amendment `d7ae80f2…`。 | NotAttempted／NotCommitted完整矩阵，nested capacity transition唯一authority。 |
| [Amendment 3 re-review](reports/260907-task3b-design-amendment-3-review-grok.md) | APPROVED DESIGN，0 Blocker／Major／1 Minor。 | Outcome矩阵closed；NotCommitted wording Minor已在Spec修正。 |
| [Task 3B authority review](reports/260907-task3b-authority-review-gpt-high.md) | NEEDS FIXES，0 Blocker／4 Major／1 Minor。 | Source authorization denied；findings保持open并移交，未修。 |

以上均为点时review，不再描述current authority；current Spec／plan hashes见status header。Contract与brief review closed；source review待fix re-review。

## 任务投影

| Task | 状态 | 当前约束 |
|---|---|---|
| 1．建立 living token-counting authority | completed | Initial authority、review fixes、两路0／0 review及evidence persistence均完成。 |
| 2．结构化 feature 与 fingerprint 核心 | completed | Reviewed source已归档，semantic patch已squash进main，main-side gate通过。 |
| 3．Versioned SQLite learning store | completed／main integrated | Reviewed source `9ff21ce`已归档；stacked Task 3／3A／3B integration squash `6044919a`已进入main。 |
| 3A．Candidate／visual／decision persistence contract | completed／main integrated | Reviewed source `c59cdd66`已归档；merged full gate 3,375 passed／90.35%。 |
| 3B．Per-item suffix／availability／prefix checkpoint | completed／main integrated | Reviewed source `e2461a6e`已归档到`archive/260907-token-learning-prerequisites`；source与merged-state review APPROVED；main squash `6044919a`。 |
| 4A．Cold-start、exact／deterministic prefix 与 prequential record | completed／main integrated | Reviewed source `7d7e43b3` archived at `archive/260907-token-prediction-exact-prefix`；source／merged-state review APPROVED；main squash `3badac7f`；38 focused、574 tokenization passed。 |
| 4B-P．Learned prefix variants | in_progress | C04 authority correction已由fresh review复审为READY；partial candidate在隔离3badac7f worktree继续，source尚未review或提交。 |
| 4B．Profile candidates 与 prefix eligibility | pending／ready for brief | Task 4B-P已集成main；必须生成新brief，负责profile candidates、promotion和16／8 checkpoint policy。 |
| 4C．Drift detection 与 learning epoch | pending | 等待Task 4B。 |
| 5．Learning service 与 lifespan | pending | 等待Tasks 2～4C。 |
| 8．Anthropic thinking 与 media baseline | pending | 可在Task 1完成后按计划先行；必须早于Task 7。 |
| External sequencing gate | pending | Shared pipeline wiring必须等待direct buffered Chat Tasks 4～7已在main稳定其`ResponseHandoff`、selected-candidate callback和attempt／request finalizer seam，并在进入Task 6前重读其living tracking与最终source。 |
| 6．Actual sent attempt 与 exactly-once learning | pending | 受external sequencing gate约束。 |
| 7．Lazy count provider chain | pending | 受external sequencing gate约束，且依赖Task 8。 |
| 9．Context editing 与响应完整性 | pending | 受external sequencing gate约束。 |
| 10．Observability 与 offline evaluator | pending | 受external sequencing gate约束。 |
| 11．收口 alternate service、配置候选与完整验证 | pending | 等待前序tasks与merged-state review。 |

## 当前合同与实现关系

- [spec.md](spec.md)是本topic的behavior authority；[plan.md](plan.md)拥有实施顺序和per-task evidence，不是第二份当前状态。
- [token-counting-config.md](../../human-controlled-docs-candidates/token-counting-config.md)仍只是候选；`docs/.human-controlled/`尚未由用户据此更新。
- Tasks 3／3A／3B source reviews均闭合；`6044919a`是当前main上的stacked integration squash，source archive refs分别保留各自reviewed source。
- Task 4A只写pure predictor／finalization，不进入pipeline、不访问store、不创建queue／task。Task 5才消费ephemeral decision并拥有anchor-use持久化编排。
