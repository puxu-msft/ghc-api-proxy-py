# Token-counting Historical Learning Implementation Plan

状态：approved。本文承接并适配批准计划 `/home/xp/.claude/plans/serialized-moseying-corbato.md`；行为合同以 [spec.md](spec.md) 为准，当前阶段与下一步的唯一 volatile projection 以 [status.md](status.md) 为准。本文的任务勾选只记录各任务的执行与处置，不另立项目级当前状态。

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Production behavior comes before its direct regression tests under this project's workflow; commit boundaries are semantic, not red／green boundaries.

**Goal:** 修复 local token estimator 的结构语义错误，并建立 exact／prefix／profile 混合、可持久化、自评估和可适应漂移的历史学习闭环，使估算随真实 upstream usage持续趋近准确。

**Architecture:** `TokenEstimator`只从最终目标payload抽取可解释features与fingerprints，`TokenPredictor`与`TokenLearningPolicy`只按immutable history snapshot作prediction／evaluation／state transition，`TokenLearningService`和pipeline／lifespan拥有send、terminal、queue、cancel、shutdown与持久化流程。Responses使用actual sent bytes＋raw total input usage学习，历史通过`aiosqlite`写入SQLite／WAL；Responses local success保持`input_tokens`＋`estimated:true`。

**Tech Stack:** Python 3.14、AnyIO／asyncio、`aiosqlite>=0.22.1`＋SQLite WAL、`tiktoken` 0.14.0、FastAPI、现有 `httpx2`／OpenAI raw Responses transport、pytest、Ruff、Pyright。

**Spec:** `.dev/docs/token-counting/spec.md`，由Task 1先创建并经独立评审；`.dev/docs/token-counting/plan.md`在计划获批后承接本文件。

**Review amendment:** 2026-09-07 Task 1 review round 1的7项Important／1项Minor与cross-session review的2项Major均已采纳；本计划同步deterministic cold-start、`ProfileKey`／`FeatureVector`、exact eligibility、prefix state machine、bounded events、count error wire、production learning closure、ordinary special spellings与decision provenance。Behavioral outcomes、全部semantic tasks和external gate保持不变。

**Task 3 review amendment:** Source candidate `8b40d6a`的独立review发现1 Critical／6 Important／2 Minor。Living authority先补齐cancellation-safe ownership、V1 authenticity、concurrent migration、closed durable reasons、exact prune order、independent oracles、single revision order和thread provenance，随后才允许source fix。Review还发现本计划错误要求提交ignored workspace `uv.lock`；该要求已按人控release contract撤销，无需用户重裁。

**Task 3 contract re-review amendment:** 首轮living contract review仍发现2 Blocker／1 Major／2 Minor。本轮分离private persistent validation和public prediction snapshot，补齐Task 4 intent→Task 5 queue→Task 3 store owner chain、A35 revision-before-DELETE oracle、`asyncio.CancelledError` inheritance及canonical timestamp／key ties；此前T3-01／03／04／07／08／09 amendments保持不变。Source fix继续blocked，直到第二轮contract review达到0 Blocker／Major。

**Task 3 source fix round 1 amendment:** Candidate `3df0da3`的source review发现0 Critical／4 Important。Living contract补齐close lock-wait ownership、table-column collation authenticity、retained derived graph closure和complete named test ledger；source fix round 2继续blocked，直到本轮contract review达到0 Blocker／Major。此前所有Task 3 amendments保持不变。

**Task 3 contract round 3 amendment:** Contract review仍发现1 Blocker／1 Major。Living Spec现在分离record＋actual可重建的完整prequential facts与newest-128 bounded diagnostic evaluation rows，并由Spec §8.1.1固定action-ID分母；test literal、production ledger和runtime confirmed trace三方对账，raw-call mapping独立核registered coverage。Source fix继续blocked，直到下一轮contract review达到0 Blocker／Major。

**Task 3A preflight amendment:** Task 4A派发前两路review发现旧DTO／V1 schema不能表达同method variants、point-in-time champions、独立visual output或ephemeral intent carrier。本计划插入Task 3A先修candidate-key persistence、`capability_visual_tokens`与`PredictionDecision`；所有active architecture／lifecycle／Task 3 restatements从本段起按每candidate-key diagnostics、represented-method champions和request-decision-only intent同步解释，旧method-level budget或direct intent-return措辞不再有效。Task 4A等待Task 3A reviewed source，不是scope deletion。

**Task 3A brief review amendment:** Brief review发现0 Blocker／2 Major。Represented exact与cold champions现在是DTO／V1 validator无条件eligible invariants，并有false-corruption controls。Task 3A visual formula明确只作synthetic／unresized A18 mechanics seam；Task 8显式拥有`tokenization/types.py`，须依据已核provider facts扩展closed resize／limit representation后才能接production catalog。Task 3A source review不得冒充真实descriptor formula已闭合。

**Task 3B prerequisite amendment:** Task 4A brief review发现whole-request visual不可分解append suffix、prefix eligibility会随sample prune丢失，以及6 Major／1 Minor相邻合同。经独立design与三轮amendment review，新增Task 3B carrier／store mechanics、收窄Task 4A deterministic core、插入Task 4B-P learned prefix，再由Task 4B profile＋checkpoint policy、Task 4C drift承接。Living Spec现固定per-item conservation、committed order、checkpoint／capacity／outcome矩阵和111／211 action IDs；任何旧3B缺席、4A全包或4B直接跟4A的restatement不再有效。

## Global Constraints

- 不修改`docs/.human-controlled/`；需要补充人控说明时只提交`.dev/human-controlled-docs-candidates/`候选。
- Responses含opaque／media／unknown结构时仍返回best-effort数值与`estimated:true`；cold-start不是终态，eligible upstream usage自动进入历史学习。
- 训练label只用同provider／model／attempt／actual sent payload的raw total input tokens，绝不使用normalized fresh input或output reasoning tokens。
- 不把raw prompt、tool output、opaque carrier或media body持久化进learning store；只保存bounded fingerprints、features、counts、provenance与errors。
- 不用单一跨结构multiplier、现有0.5～3.0 clamp或`river`替代混合学习；operator multiplier只作用于最终prediction且不进入训练。
- 不新增proxy-private client字段；local success继续返回`input_tokens`＋`estimated:true`。Direct Anthropic upstream count按官方标准保留可选`context_management.original_input_tokens`，这是已支持端点的标准字段恢复；其它client-visible字段或错误状态变化仍须暂停并交用户裁定。
- 不把8.66MB reconstructed candidate提交为普通cassette，也不把它与921,248 usage冒充cryptographically identical request。
- 每个语义切片独立评审并及时集成；最终候选只评一次完整合并态，除非相关bytes再次变化。
- `.dev`文档通过项目既有dotdev专用worktree与精确pathspec持久化，不把`.dev/`提交进`main`，不接管其它会话占用的dotdev worktree，不推送。

---

## Context

会话“buffered chat completions”的高置信度同请求重建显示，当前 Responses local estimator 对 upstream 实报 921,248 input tokens 的请求估算为 4,539,201，约高估 4.927230 倍。788 个 `reasoning` items 的完整 contribution 为 3,729,865，其中仅 `encrypted_content` 相对空串的边际就是 3,715,681。主导原因不是 `o200k_base` vocabulary 选择错误，而是 `_responses_item_text()` 把 opaque reasoning JSON 当 ordinary text 编码。

同一代码审计还确认，`handle_count_tokens()` 在 provider chain 前无条件执行 local worker，因此 local tokenizer failure 可以阻断本应优先的 upstream counter。Responses route 没有 upstream count endpoint，正常 inference 的 authoritative usage 又没有进入 calibration，所以“calibrated local estimate”在该协议上实际没有 production learning source。

本计划交付一套完整但分片落地的修复：先建立 living token-counting Spec和结构化cold-start基线，再让local estimation按provider chain懒执行，随后接入exact／prefix／profile三层历史学习、持久化、prequential评估与漂移适应；之后在同一实施计划内补齐Images／PDF、Anthropic thinking、context editing、provider-name routing、dead alternate service与multiplier语义。各项共享新数据模型和学习框架，但按语义边界拆成可独立评审、及时集成的提交，不把12项发现强塞进一个提交。

## Decision provenance

四项decision entry共用transcript`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`；完整source classification、UUID、timestamps与authorized scope以[spec.md §2.2～§2.3](spec.md)为准。

- **R1，`user-selected-from-proposal`**：assistant UUID `8b378b42-2843-433c-8451-9eb94e4e60cc`以tool id `call_vSmGVp2cmJGmJF2mtwXzKOj2`提出单选proposal，user-role result UUID `42764806-9deb-4951-951d-a3584f076f88`选择“返回低置信估算”。被选description授权排除opaque bytes、估可见／结构部分、保留`estimated:true`并接受near-cap undercount。Upstream-no-counter和learning细节是派生内容。
- **R2，direct user-natural-language**：queued-command attachment UUID `78db73d0-10df-4e90-9207-26eb6e1cd2ca`、source UUID `cdcbf829-3e18-432b-9be4-c732a8758715`记录用户原句：“不要逃避问题了，我们的 local tokenzier 一定要努力做到精确，要增加历史学习能力”。Cold-start-only、persistence和reject global multiplier由R1／R3与implementation judgment推导。
- **R3，`user-selected-from-proposal`**：assistant UUID `7b55326f-835a-4d47-b749-4e6eae40fdae`以tool id `call_7qflH1cK3JFKeiHInSyIMvR0`提出proposal，user-role result UUID `04f71c54-bc93-4e2a-a18b-cdd998987ed2`选择“混合学习（推荐）”。授权exact priority、append-only longest-prefix actual＋suffix、no-prefix provider／model／profile learning和staged delivery。Tokenizer key、new-identity cold-start与detailed eligibility／drift／bounds是派生内容。
- **R4，direct user-natural-language**：queued-command attachment UUID `e0d60d1c-2593-4007-b507-af363b3dc812`、source UUID `0310b228-4c7c-4782-81e5-045ed2b4c968`记录用户原句：“具体学习过程不要询问用户，你必须设立完善的精进机制”。八类详细机制与method no-delete／no-reorder是delegated scope加R3 architecture的implementation-derived closure，不是用户逐字文本。

本计划据此保持exact → prefix → profile → cold-start architecture，先建立结构化estimate与same-attempt history，再分slice完成exact／prefix、profile、persistence、prequential evaluation与drift。Proposal choice与direct user text是authority input；本计划的具体算法、constants和orchestration仍是implementation decisions。

## Requirements and invariants

- Local count remains available for Responses and always returns a numeric best estimate with `estimated:true`，including cold start and requests containing opaque／media／unknown structures。
- Cold-start is deterministic：`known_tokens` equals visible／tokenizable components plus explicit `framing-v1` container／item contributions，then model-capability visual tokens and the versioned released residual prior are added。Missing coefficients are zero with a named low-confidence reason；fixed 1 for all new identities is forbidden。
- Every configured-tokenizer special spelling，including literal `<|endoftext|>`，uses ordinary-text semantics on all Anthropic system／message／tool-schema and Responses instructions／message／tool-schema／function-arguments／function-output surfaces。Implementation uses `encode_ordinary()` or a sequence-equivalent interface；default guard、`allowed_special` and endpoint fallback are forbidden。
- Accuracy improvement is continuous and automatic：every eligible upstream success can improve later predictions without operator action or user-tuned coefficients。
- Learning labels come only from the same actual provider／resolved model／attempt／final sent payload；no cross-attempt、cross-provider、normalized-usage or output-reasoning substitution。
- No raw prompt、tool output、opaque carrier or media payload is copied into learning state；all retained history is bounded fingerprints、`ProfileKey`、`FeatureVector`、counts、provenance and error statistics。
- A model／tokenizer／estimator generation／cold-start prior revision change cannot silently reuse incompatible learned statistics；restart preserves compatible history。
- Learning never changes an already-delivered response，and background learning cannot starve foreground count requests。
- Every prediction exposes its method and evidence strength internally；`estimated:true` remains the stable public provenance marker。
- The system evaluates predictions before learning each label，so observed accuracy cannot be a training-leak false green。
- Active-epoch exact hits are always eligible。Prefix can become temporarily ineligible only through the Spec's 16-sample strict demotion rule；profile requires its 8-paired-sample strict promotion rule。The order of eligible methods remains exact → prefix → profile → cold-start。
- Count errors follow `.dev/docs/error-envelope/spec.md`：the token Spec restates the complete count-specific Anthropic status／type／code／carrier and cause-read-through mapping rather than delegating to an unnamed existing behavior。

## Recommended data model

`estimate_responses_input()`不再只返回一个裸`int`，而返回可序列化的`EstimateFeatures`。`ProfileKey`只放需要exact equality的categorical facts；`FeatureVector`只放带presence state的quantitative values。`known_tokens`显式累加visible／tokenizable components和`framing-v1`：每个opaque、media、unknown item仍贡献framing，但其carrier bytes不进入ordinary-text tokens。所有known text统一走ordinary encoding，literal special spelling不获得control semantics也不改变classification。Model descriptor有visual formula时把其结果加入cold-start；其余feature residual查`cold-start-prior-v1`，缺项按0处理并附low-confidence reason。

`EstimateFeatures`还携带stable estimator generation、按类别分解的components、low-confidence reason codes，以及用于exact／prefix历史匹配的fingerprint chain。被排除的内容不丢结构信息：保留item count、opaque byte length、source kind、可得media dimensions与unknown-shape digest作为quantitative／categorical learning inputs。Unknown type不持久化原文，只保存按bytes排序的前8个SHA-256 digests、总数与`overflow`。

`Attempt`新增immutable `SentRequestSnapshot`与exactly-once learning状态。Snapshot在`DirectDriver._prepare_and_send()`取得response headers之后，从同一`response.request.content`冻结actual sent bytes，并携带`(process_boot_id, request_id, attempt_index)`、endpoint、actual provider、resolved model、catalog tokenizer与descriptor fingerprint。`Attempt.payload`用于count侧结构分析和测试对照；sent bytes是训练样本的发送事实权威。

历史状态分三类，并全部绑定actual provider、resolved model、endpoint／wire format、tokenizer、descriptor fingerprint、estimator generation、profile schema revision与learning epoch：

1. exact anchor：canonical token-relevant full-payload fingerprint → upstream exact input tokens，同时保存raw sent-body SHA作为provenance；
2. prefix anchor：top-level token context fingerprint＋input rolling-prefix fingerprint＋item count → upstream exact input tokens；
3. profile history：exact categorical `ProfileKey`、quantitative `FeatureVector`、raw known-token estimate、actual usage与prequential error，用于无anchor请求的nearest-neighbor residual／ratio prediction。

每个eligible Responses inference attempt只用自己的sent snapshot与自己的`UsageObservation.exact.upstream_input_tokens`配对。失败、无usage、usage不一致、不同retry attempt、不同provider／model的样本不得混入；`response.completed`与携带完整usage的`response.incomplete`可学习，`response.failed`／`cancelled`不可学习。Upstream terminal和raw usage已经成立后，即使后续client translation／delivery失败，该input sample仍可学习，但对应失败事实必须独立保留，不能把“学到了”投影成“请求成功”。

现有单JSON `TokenizationStateStore`无法承载这份history：smooth restart时两个process可并行写，process-local lock加atomic replace仍会last-writer-wins。新增`aiosqlite` backed SQLite／WAL learning store；每个connection由库自己的single shared thread与request queue执行，sample identity提供transactional exactly-once。现有JSON继续承载旧Anthropic calibration与prompt-limit state，直到对应slice迁入新store。

## Count decision order

1. Active-epoch exact anchor命中时始终返回其最近5个actual的median，并仍标`estimated:true`；只有fingerprint miss或已完成epoch transition才停止使用旧anchor，generic error comparison不得绕过它。
2. 否则选择最长可信prefix anchor。无suffix history时使用只计算appended items的deterministic cold-start suffix；additive／multiplicative suffix candidates各需3条eligible samples，最近至多31条中的至少8个paired errors后才选择strictly better candidate，tie保留baseline。
3. Prefix只有在最近16条triply-paired samples上同时比profile和cold-start的median APE高`>5`个百分点才demote；缺样本、缺profile或tie都保留prefix。Demoted prefix继续作challenger，并在8条subsequent paired samples上达到`<=`best alternative时恢复。
4. 没有合格anchor时，从same identity＋exact `ProfileKey` pool选择distance最近31条。Distance是equal-weight L1：定量值先`log1p`，MAD从current sample之前全部eligible同key history计算，MAD 0→1，presence mismatch精确罚4；tie按smaller distance、newer observation、`process_boot_id`／`request_id` UTF-8 BINARY ascending和numeric `attempt_index` ascending。
5. Profile additive／multiplicative candidates各需3条样本，至少8个同批paired errors且median APE严格优于cold-start才promotion；与cold-start相等时保留cold-start。
6. 全新identity或没有合格history method时使用Spec的deterministic cold-start equation，不能固定返回1。
7. Public response保持`input_tokens`＋`estimated:true`；method、`ProfileKey`、history和low-confidence facts只进入typed aggregate与durable records。

## Continuous improvement loop

每个可学习Responses attempt执行prequential流程，避免用学过当前答案的model给自己打分。监督目标必须取upstream raw／exact的总`input_tokens`，包含cached部分，不能取Anthropic-shaped normalized fresh input或`output_tokens_details.reasoning_tokens`：

1. Final sent payload边界只生成immutable `SentRequestSnapshot`；eligible terminal到达后形成`CompletedTokenSample(sent, actual)`并排入body queue，不在client critical path执行tokenization。
2. 只有同一attempt返回完整、非负、internally consistent的raw upstream `input_tokens`时才接收sample；`actual == 0`只参与exact／additive evidence和absolute error，不生成multiplicative ratio、relative／APE、champion或drift evidence。Public Anthropic count response仍要求`type(value) is int and value > 0`。
3. Single consumer先分析sent bytes；store在confirmed `BEGIN IMMEDIATE`后执行duplicate check、读取transaction-fresh snapshot并在background CPU lane运行pure transition。Write order固定为insert／update→compute victims／affected identities→increment every affected identity revision＋global DB revision→cascade prune→event使用post-transition revision→confirmed COMMIT。Busy retry重跑完整ownership flow、duplicate check与transition。
4. Exact anchor保留fingerprint最近5个actual。Prefix anchor保存context／rolling-prefix／item count与actual。Sample另保存exact-conservation fixed／per-item contributions和store-assigned committed order；prefix chain使用compact positional digest JSON。Profile history保存`ProfileKey`、完整compact `FeatureVector`、known estimate、actual与学习前candidate predictions。
5. Request completion只记录当时已知的prediction／offer facts；SQLite可写时，晚到commit／duplicate／rejection／failure、closed reason codes、bounded typed metadata、errors、revision和epoch写入bounded durable `TokenLearningObservation`。DB不可写时只发可含bounded exception text的best-effort structured application warning，不称为durable。
6. Samples／PredictionRecords／actual保留完整可重建prequential facts；persisted evaluations按candidate key各自newest128。Per-ProfileKey prefix checkpoint独立于sample FK保存eligible latest16／demoted latest8；required logical command与store outcome分槽，main outcome矩阵区分NoChange、NotAttempted和NotCommitted。Candidate-key sequence用于variant comparison，checkpoint／record champion sequence用于demotion／recovery／drift。
7. Runtime profile drift的recent32＋preceding reference128从retained PredictionRecord candidates＋sample actual重建，不依赖bounded evaluation rows；因此160 evidence在只留128 diagnostics时仍完整。既有drift thresholds、exact mismatch和epoch isolation不变。
8. Production path必须闭合inference actual sent body＋same-attempt raw total usage→committed sample→reader snapshot→later identical exact／append-only prefix count；不能只在unit test预置anchors。

所有unscaled candidates在唯一`finalize_local_prediction()`边界前保持数值精度；该函数用`Decimal(str(...))`先乘operator multiplier，再`ROUND_CEILING`并minimum-one。其它层不得舍入。Operator multiplier不进入learning label或evaluation。

采用`aiosqlite>=0.22.1`。Queued SQLite actions和lifecycle／reader／writer lock acquisitions都使用confirmed ownership；`close()`同步登记owner ticket，标记CLOSING后按lifecycle→reader→writer等待active operations，再checkpoint／close，最后传播pending cancellation。任何lock-wait exception不得无锁close connection；concurrent close共享一个completion。

不采用通用online-ML dependency `river`。规划时可核稳定版为0.26.1，要求Python 3.11+并引入NumPy与SciPy；它会把当前少量可解释的ratio window、fingerprint和state migration变成更重的runtime dependency。真实样本若证明当前profile不足，再以已保存features／actual评估River，而不是预先替代用户选择的方法。

## Evidence strategy

不把8.66MB reconstructed candidate伪装成普通cassette或cryptographically exact same-request fixture。Production回归分两层：小型deterministic Responses reasoning shape验证ciphertext不再按普通文本增长；历史学习单元／入口测试用独立注入的actual usage验证exact、prefix、profile、prequential error与retry配对。真实921,248 forensic evidence继续留在`.dev`分析及本地可选probe，明确identity是高置信重建而非原body hash证明。

## Strategy／orchestration boundary

- `TokenEstimator`是纯策略：输入final target payload，输出immutable `EstimateFeatures`；它只分类、抽取、tokenize与fingerprint，不访问state、不选provider、不调度任务。
- `TokenPredictor`是纯策略：`TokenPrediction`只表示可持久化candidate value；prequential入口构造含candidate keys、represented-method champions／eligibility和selected key的`PredictionRecord`，request-side入口返回ephemeral `PredictionDecision(selected_prediction, anchor_use_intent)`。只有request decision可携typed `AnchorUseIntent(kind, identity, epoch, fingerprint, source_sample_keys)`；predictor不发请求、不调用store、不拥有queue、不持久化intent。
- `TokenLearningPolicy`是纯领域策略：输入attempt-scoped `PredictionRecord`、validated actual usage和transaction-fresh single-identity active `LearningSnapshot`，只返回logical `LearningUpdate`。Final `TokenLearningObservation`、checkpoint store outcome、post-transition revisions、capacity transition和durable event由store在最终state与confirmed COMMIT后唯一构造；policy不得返回或预填这些durable facts。Store先构造／验证private `ValidatedPersistentState`，只把目标active snapshot交给policy，再把update应用到normalized rows；events／inactive epochs不越过policy／predictor boundary。
- `TokenLearningService`是orchestrator：拥有queue、worker lanes、store transaction调用、shutdown与observation发布，不重新推导profile、prediction或drift规则。
- Pipeline driver／learning worker拥有流程：何时捕获final sent payload、何时启动异步feature extraction、如何绑定attempt、何时接收terminal usage、queue backpressure／cancel／shutdown／flush与observation发布。Driver只解释typed outcome，不重新计算profile、误差、drift或method优先级。

跨生命周期字段契约：`SentRequestSnapshot`与`CompletedTokenSample`为per-attempt immutable。Store-private `ValidatedPersistentState`承载一个consistent read transaction验证过的全体retained identities／epochs／events；public `LearningSnapshot`恰好对应一个requested identity的active epoch及samples／anchors／prediction records／evaluations。每个committed mutation先计算affected identities，再递增identity／global DB revisions；cache据此refresh／delete。

观测分成两个时序不同、不可互相冒充的载体：

- Request completion／`RequestLine`只记录冻结前同步已知的prediction facts与`offer()`结果，例如method、profile、history revision、`queued`／`queue-full`／attempt duplicate；发布后不可回写。
- Background learner完成后另产出typed `TokenLearningObservation`，以sample identity关联request／attempt，记录`committed`／DB duplicate／rejected／failed、closed reason codes、bounded typed metadata、所有prequential errors及new revision／epoch。SQLite可写时event进入bounded durable `learning_events`并可同时发结构化日志；DB不可写时只发同identity的best-effort warning，raw exception text不进入DB，也不伪装成request completion字段。

## Learning lifecycle and failure behavior

Historical learning不得延迟或改写已经完成的client response。`_prepare_and_send()`在headers返回时只冻结同一response的actual sent bytes与identity，不做tiktoken；`_absorb_response_observation()`在同一attempt出现eligible final raw usage时，通过attempt-local compare-and-set恰好offer一次immutable sample。它必须接收局部`Attempt`参数，不能把稍后读取`context.current_attempt`的closure排入后台。

CPU-heavy parse／canonical fingerprint chain／components／profile extraction进入lifespan拥有的单消费者、有界learning queue。Foreground `/count_tokens` analyzer与background analyzer使用独立capacity limiters。SQLite读写一律通过`aiosqlite.Connection`代理，底层raw connection不逃逸production owner。Writer与reader使用独立connections；所有queued actions用confirmed-completion helper。Existing DB先read-only authenticity inspection；fresh migration在WAL busy retry和confirmed `BEGIN IMMEDIATE`后lock内重读schema，reader只在migration成功后open。

`PRAGMA data_version`只检测其它connection的commit并触发reader refresh；global DB revision覆盖完全删除identity的cache invalidation。Reader在一个confirmed transaction读取全部active／inactive rows与events，off-event-loop构造store-private `ValidatedPersistentState`；`snapshot_for_prediction(identity)`只投影一个active identity／epoch的public `LearningSnapshot`。失败／取消继续使用上一validated private state和对应active snapshots。

Foreground prediction只读requested identity最后validated active `LearningSnapshot`。Shutdown／close先mark CLOSING，按fixed lifecycle→reader→writer order confirmed-acquire全部locks，等待active operation保持其既定outcome，再checkpoint／close并reverse-release；取消只在resources closed后以typed task cancellation传播。

Queue overflow、feature extraction failure、sample validation failure、SQLite busy／migration failure与commit failure必须产生closed reason code和bounded metadata；raw exception text只进DB外best-effort warning。Task 4 request-side pure prediction通过ephemeral `PredictionDecision`产出可选`AnchorUseIntent`；Task 5／pipeline orchestrator只把request decision intent在critical path外排队并调用store `record_anchor_use(intent)`，prequential challenger不排use。Queue failure记录observation且不改变last-confirmed use；store不拥有queue／task。

Exact／prefix anchor只保存SHA-256 fingerprints、item count、actual tokens、identity key、recency与error metadata，不保存prompt内容。Fingerprint从actual sent JSON解析出的canonical structure产生：full identity忽略唯一已确认与input计数无关的transport字段`stream`；prefix context hash覆盖除`input`／`stream`外的全部top-level字段，rolling hash按canonical input item顺序串联。未知字段也进入hash而不进入ordinary-text count，因此只会保守地产生miss，不会因被忽略而false-hit。Raw sent-body SHA只作provenance。Instructions／tools／model capability变化会使prefix context失配，compaction／重排／删除也不会误命中旧prefix。Smooth restart的双进程通过SQLite WAL、busy retry与unique sample key合并，而不是各自覆盖整个snapshot。Queue同时受item count与pending body bytes双上限约束，避免少量8MB级请求把内存上限放大；饱和时记录`queue-full`拒收而不阻断已完成响应。实现使用`aiosqlite` 0.22.1的per-connection worker thread；`src/.archived/app/history/sqlite/writer.py`只可参考其single-writer／WAL／busy-retry生命周期，不能作为当前运行模块导入或被当成现行行为。

## Critical files

现有文件：

- `src/app/tokenization/estimators.py`：拆出结构化features与protocol-specific cold-start估算；
- `src/app/tokenization/worker.py`：foreground estimate执行与background lane隔离；
- `src/app/tokenization/calibration.py`、`state_store.py`：保留／迁移旧Anthropic状态，并停止把Responses交给跨结构scalar engine；
- `src/app/pipeline/request.py`：`Attempt`拥有sent snapshot与exactly-once learning状态；
- `src/app/pipeline/direct_driver/base.py`：从`response.request.content`冻结真实sent snapshot；
- `src/app/server/routes/inference.py`：stream／buffered共同final observation汇合点向learner offer同attempt sample；
- `src/app/core/chain.py`、`src/app/server/pipeline_app.py`：learning service构造、start、drain、close与shutdown次序；
- `src/app/pipeline/driver.py`、`src/app/pipeline/count_tokens.py`：provider-specific ordered legs、lazy local与prediction结果投影；
- `src/app/pipeline/error_classify.py`与`src/app/pipeline/delivery/formats/errors.py`：消费living error-envelope authority；Task 7验证count-specific mapping，不从当前实现反推新合同；
- `src/app/pipeline/response_observation.py`、`src/app/observability/request_completion.py`：authoritative raw usage与学习／预测observations；
- `src/app/config/paths.py`：SQLite learning-store路径；本计划不新增operator-facing容量配置，因此不改`config/schema.py`。

新增深模块建议：

- `src/app/tokenization/types.py`：跨estimator／store／predictor／pipeline边界的immutable DTO与discriminated outcomes；
- `src/app/tokenization/features.py`：pure canonicalization、component extraction与fingerprint chain；
- `src/app/tokenization/prediction.py`：exact／prefix／profile／cold-start策略与prequential evaluation；
- `src/app/tokenization/learning.py`：attempt sample eligibility、single-consumer queue与lifecycle；
- `src/app/tokenization/learning_store.py`及`learning_schema.py`：`aiosqlite`／WAL事务、查询、unique insert、pruning与migration；queue与调度只属于`learning.py`；
- `pyproject.toml`：声明`aiosqlite>=0.22.1`；Task 3不新增tracked lock artifact；
- `src/app/tokenization/evaluate.py`：只读progressive replay诊断入口。

测试集中在`tests/unit/tokenization/`、`tests/unit/pipeline/`和`tests/int/test_pipeline_app.py`；新建小型synthetic fixtures，不把8.66MB forensic request放进普通cassette。Living文档位于`.dev/docs/token-counting/`，人控候选只在需要时写入`.dev/human-controlled-docs-candidates/`。

## Planned verification

以下跨任务承重判据在同一入口带正确样本与目标缺陷注入；各Task另列本地判据。Mutation变红后还要核失败来自目标不变量，而不是fixture parsing或旁路断言。

| 判据 | 正确样本 | 缺陷注入控制 | 证据边界 |
|---|---|---|---|
| Deterministic cold-start | Independent stub tokenizer给出instructions 2、message role／text 7；4 items与instructions framing贡献20，immutable capability的per-item formula给独立`capability_visual_tokens=6`，residual 0；断言known29、visual6、unscaled／public35、SQLite round-trip和同面积56×84→6／42×112→8 | 分别固定new identity为1、移除framing、把visual塞known、丢nullable column或从aggregate pixels回推；exact object／value必须红 | Literal arithmetic与capability stub不证明真实descriptor／provider准确率 |
| Ordinary special spelling matrix | 枚举configured tokenizer全部special spellings并显式含`<|endoftext|>`，跨Anthropic system／messages／tool schema与Responses instructions／messages／tool schema／function arguments／output；independent ordinary oracle断言sequence或exact delta | 两次独立mutation分别恢复default guard与启用`allowed_special`；前者exception、后者sequence mismatch都必须红 | 证明local encoding mechanics，不证明provider billing accuracy |
| Ordinary production wiring | Production ASGI direct Anthropic local-only与Anthropic→Responses local都以literal`<|endoftext|>`返回HTTP 200完整对象`{"input_tokens": N, "estimated": true}`且无额外字段，local worker一次、remote provider零次 | 分别恢复Anthropic与Responses default `encode()`；对应路径必须500且success／call-count断言红，endpoint catch不得代偿 | Mock ASGI证明two-path wiring和non-500 behavior，不证明numerical accuracy |
| Opaque bytes不冒充text tokens | 小型deterministic Responses payload增大`encrypted_content`／base64时ordinary-text component不变而opaque features变化；可见summary／message／tool文本仍有delta | 临时恢复unknown item整段`dumps()`进tokenizer，ordinary component断言必须红 | Mechanics test不证明provider实际计费 |
| Provider顺序懒执行 | 真实ASGI count入口中`[ghc,local]` upstream success返回固定独立值且local spy为0次；upstream失败后local恰执行1次；`[local,ghc]`不问upstream | 把local precompute重新放回chain前，upstream-success用例必须因local被调用／抛错而红 | Stub证明我方编排，不证明真实provider可用性 |
| Count error wire | Production Anthropic error入口对`CountTokensRequestError`、`CountTokensUnavailable` cause／no-cause及named ProviderError逐行断言完整status、nested body、type、code和optional fields | 分别统一压成503、停止cause recursion、遗漏named subclass或写成flat envelope；目标完整对象断言必须红 | Local fixtures证明本方mapping；direct upstream passthrough仍由error-envelope Spec裁断 |
| Exact／prefix身份与exact eligibility | 同context exact与append-only分别命中；same-prefix actual100／120选newest120并让decision intent指同source，same-timestamp按BINARY text／numeric attempt ascending；tools／instructions／item次序变化失配，active exact始终优先 | 省略fingerprint维度、对prefix取median110、反转／JSON比较sample key或让generic champion跳过exact；identity／value／intent／method必须红 | Synthetic SHA／anchors不证明forensic candidate与成功body同一，也不证明latest比median现实更准 |
| Profile compatibility与distance | 只有same identity＋exact `ProfileKey`进入pool；quantitative distance按equal-weight L1、log1p、MAD 0→1、presence penalty 4，tie按distance／newer observation／sample id | 把quantities塞入`ProfileKey`、改用L2／非等权、改变penalty、从nearest-31先算MAD或反转tie | Synthetic labels不冒充真实provider计费函数 |
| Prefix suffix／demotion／recovery | Record保存deterministic／additive／multiplicative candidate keys及prefix method champion；minimum3后，最近至多31条所有当前variants共同records至少8条才选strictly better；recent16 method champions同时差于profile／cold-start`>5`百分点才demote，subsequent8达到`<=`恢复 | Collapse by method、非共同batch、one-sample永久demotion、`>=5`、tie选learned、demoted后不评估或7条恢复必须红 | Synthetic errors证明candidate／state machine，不证明现实method优劣 |
| Actual sent-body authority | 最后一个subscriber与provider adapter分别改变payload，sample raw SHA和features等于mock transport实际`response.request.content`，而非`context.payload`重算值 | 改回从`context.payload`或`Attempt.payload`重序列化，body identity／feature断言必须红 | Mock transport证明捕获点，不证明provider计费 |
| Attempt label不串线 | 两次retry使用不同payload与usage，只有eligible attempt进入对应identity；cancel／missing／inconsistent usage拒收 | 用request-level shared record替代attempt record，必须观察到wrong-payload label并红 | Fake usage证明pairing，不冒充upstream behavior |
| Production learning closure | Production ASGI inference actual sent body＋same-attempt raw total usage提交sample与pre-learn error；later identical count走exact，append-only走prefix，并断言provenance／prediction／method | 两次独立mutation：丢offer；保留offer但禁用anchor transition／snapshot refresh | Mock usage证明production wiring，不冒充provider billing |
| Raw-total label | 同一mock response把raw total设120、normalized fresh设20、output reasoning设777；sample actual、error和later exact必须取120 | 两次独立mutation分别用20与777替代120；完整sample／prediction断言必须红 | 人工字段差异证明selection，不证明120是真实计费值 |
| Prequential无训练泄漏 | Cold-only首record只有eligible cold champion；一般record在learn前按candidate key保存全部candidates／evaluations、represented champions／eligibility和selected key，represented exact／cold恒eligible；第二个sample才使用首笔history，actual0只有exact／additive evidence与每key absolute error | 把exact／cold设false、要求absent champion、把learn移到candidate／champion／evaluate前、按method覆盖variant或让0进入ratio／APE；完整record／validation必须红 | 证明cardinality、eligibility、顺序与candidate preservation，不证明prediction已准确 |
| Persistence、bounds与版本隔离 | Compatible restart恢复private validated state和逐identity active snapshots；identity变化不复用；caps、cascade和empty metadata pruning精确断言 | 去掉identity dimension、cascade、event cap或projection boundary；row／type断言必须红 | Local SQLite证明bounded state，不证明filesystem performance |
| Cancellation-safe store ownership | Complete named ledger覆盖queue actions和lifecycle／reader／writer LOCK_WAIT；writer／reader barriers使cancelled close等待operation、取得locks、close后传播typed cancellation；concurrent close只执行一次 | 每个action／lock wait、lock order、CLOSING mark和shared close future各有single mutation | Injected cancel／barrier证明ownership state machine，不代表production close timing |
| V1 authenticity与all-epoch decode | Independent fixed table-DDL digests及complete CHECK／COLLATE／STRICT／PRAGMA manifest；private full-object expected覆盖all rows／events／derived graph，active expected单独验证public snapshot | NOCASE fake、missing／extra child、candidate／prefix／event mismatch和unreferenced metadata各有single validator mutation | Private validation与public prediction snapshot是两种type／oracle |
| Concurrent fresh migration | Barrier保证两个starter都完成complete empty inspection后才竞争ownership；一个create、一个lock内validate，reader migration后open | 移除dual-inspection barrier、lock内reread或reader sequencing，各自必须红 | Local concurrency不证明network filesystem semantics |
| Durable reason boundary | Closed reason variants和typed primitive metadata round-trip；arbitrary prompt／exception text构造或record被拒且row／revision不变 | 恢复free-form detail／reason或generic string metadata；marker进入DB必须红 | 证明durable state无free text；DB外warning是另一surface |
| Exact prune order与anchor use | Task 4 request-side`PredictionDecision.anchor_use_intent`→Task 5 queue→Task 3 `record_anchor_use()`改变目标source order；prequential record不含intent，PRUNED no-op与queue-failure last-confirmed semantics可读；ties用UTC microseconds、BINARY text与numeric integers | 把intent持久化进candidate、让prequential challenger排use、Task 4直接await store、store拥有queue、queue failure预写use或改用string／JSON ties；owner／victim断言必须红 | Fake orchestrator证明carrier／owner chain；cap pressure不证明real traffic value |
| Connect／close thread provenance | Connector factory的`sqlite3.Connection` subclass记录真实connect与override close thread，query／apply另由UDF记录；production不暴露raw connection | 用UDF结果冒充open／close或暴露raw connection；thread／surface断言必须红 | Test connector只证明local aiosqlite provenance |
| Foreground不被background饿死 | Event控制background worker／write lock，在不靠sleep条件下foreground count仍获得专属lane并完成 | 共用single-capacity limiter或把SQLite／CPU work移回event loop，heartbeat／foreground必须红 | Deterministic concurrency不代表production load distribution |
| Public numeric fallback | Production ASGI count入口分别提交opaque reasoning、media与unknown item，完整对象为正整数`input_tokens`＋`estimated:true`且无私有字段 | 改成unavailable／error或加入private field，完整对象断言必须红 | 证明用户裁决在proxy入口成立，不证明numerical accuracy |
| Exactly-once final observation | Retry、stream replay和buffered double-absorb只offer一次并插入一条sample；DB duplicate不transition | 分别移除attempt CAS与DB unique key；offer count或revision断言必须红 | 证明wiring／dedup，不证明background永不故障 |
| Cross-process atomic transition | 两connections用barrier制造same-revision interleave；test-only BEFORE DELETE trigger／transaction trace另证明identity＋global revisions先于cascade，event后于prune并用post-transition revision，full identity deletion仍先推进global revision | 拆开transaction、复用stale update或把revision移到DELETE后；interleave或A35 trace必须红 | Local interleave／trace不代表所有filesystem性能 |
| Multi-table snapshot | Reader读完revision／epoch后放行writer commit，再读anchors／windows；结果只能完整旧或完整新revision | 移除explicit read transaction，mixed state断言必须红 | SQLite snapshot不证明cross-host shared filesystem |
| Profile drift | 保留160 records＋actual但仅128 diagnostic rows，从record candidate重建recent32＋preceding128；结果与literal errors相等 | 错用evaluation table作drift分母、删除reconstruction或混窗；160-evidence断言必须红 | Synthetic labels不冒充真实drift frequency |
| Public standard-field compatibility | Local success保持`input_tokens`＋`estimated:true`；Anthropic upstream success有`context_management`时完整保留、缺席时不合成 | 增加private field或重新丢弃`context_management`，完整对象／absence断言必须红 | Protocol fixture不证明upstream一定发送optional field |
| Unique integer finalization | Exact median100.5、profile fractional candidate、negative additive residual与multiplier 1／非1只在最终边界按multiply→ceil→minimum-one | 在exact／profile／driver提前round，先round再multiply或再次scale；完整值断言必须红 | Numeric test不证明candidate准确 |
| Late learning observation | 冻结worker直到RequestLine发布，再恢复；DB可写时`TokenLearningObservation`持久化，DB不可写时warning明确best-effort且RequestLine不变 | 回写RequestLine、丢late event或把warning标成durable；object／query断言必须红 | 证明truth-time split，不证明external consumer展示 |
| Queue与shutdown | Body queue达到32 items／64 MiB任一上限时foreground完成并记录rejection；accepted samples drain并commit，event caps生效 | 取消drain、漏byte limit、让rejection events无界或吞queue-full；DB／foreground／observation断言必须红 | Deterministic lifecycle不代表production throughput |

Forensic层不把8.66MB reconstructed candidate提交为普通cassette。使用本地冻结capture与921,248 raw usage运行可选offline probe，记录cold-start、注入history后的exact／prefix结果及method；它只能证明当前code与historical evidence的关系，不能冒充CI、live replay或原成功body的cryptographic identity。

完成每个semantic slice后跑相关pytest；最终candidate运行`uv run ruff check src tests`、`uv run pyright src tests`和`uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`。本计划不修改TUI，因此不运行独立`tests/tui`组。

## Implementation tasks

### Task 1：建立 living token-counting authority

**Files**

- Create：`.dev/docs/token-counting/README.md`
- Create：`.dev/docs/token-counting/spec.md`
- Create：`.dev/docs/token-counting/plan.md`
- Create：`.dev/docs/token-counting/status.md`
- Create：`.dev/human-controlled-docs-candidates/token-counting-config.md`

**Produces**：唯一的行为Spec，定义公开count响应、cold-start、三层history prediction、同attempt学习、identity／version、失败与观测语义；`plan.md`承接本计划，`status.md`只投影实施进度。

- [ ] 从三份260906调查／勘误／综合分析提炼当前事实和被否路线，并在README链接原件；不改写点时报告。
- [ ] 在Spec中记录四项decision provenance：R1／R3为paired `user-selected-from-proposal`，R2／R4只逐字引用真实user-authored text；proposal之外的cold-start、identity、eligibility／drift／bounds与method no-delete／no-reorder明确归入implementation-derived scope。
- [ ] 写`.dev/human-controlled-docs-candidates/token-counting-config.md`，提出`local`新语义、历史学习和`local_estimate_multiplier`的候选说明；明确它不是人控合同，等待用户自行摘取。
- [ ] 写完整合同：Responses local success不新增私有字段；direct Anthropic upstream success保留官方可选`context_management.original_input_tokens`；provider names只选择同一frozen target的counter transport而不另行reroute model；ordinary-text special spellings、deterministic cold-start与internal prediction methods；raw total usage label；sample eligibility；exact／prefix／profile／cold-start顺序；state／event bounds；drift；operator multiplier；Anthropic thinking／media／context editing；count-specific error wire。规定所有unscaled candidates保持数值精度到唯一finalization边界，先乘operator multiplier，再统一向上取整并minimum-one；其它层不得再次舍入。明确RequestLine只承载同步prediction／offer facts，SQLite可写时晚到commit／error进入bounded durable `TokenLearningObservation`，DB不可写时只发best-effort warning。将标准字段恢复记为实现者依据人控“支持该端点”与官方协议作出的派生决定，不伪称用户逐字裁决。
- [ ] 加revision record，并逐项标出哪些测试文件转录了Spec常量／分类。
- [ ] 派独立Spec reviewer核验权威边界、完整性和可判否验收；处置到0 blocker／0 major后再碰production code。
- [ ] 以`docs: specify adaptive local token prediction`为语义提交主题，仅提交本任务拥有的`.dev`路径；不推送。

### Task 2：建立结构化feature与fingerprint核心

**Files**

- Create：`src/app/tokenization/types.py`
- Create：`src/app/tokenization/features.py`
- Modify：`src/app/tokenization/estimators.py`
- Modify：`src/app/tokenization/worker.py`
- Create：`tests/unit/tokenization/test_features.py`
- Modify：`tests/unit/tokenization/test_responses_estimator.py`
- Modify：`tests/unit/tokenization/test_local_token_worker.py`

**Interfaces**

- `types.py` produces：既有Task 2 DTO，以及Task 3 narrowly added single-active-identity `LearningSnapshot`补全、`AnchorUseIntent`／`AnchorUseOutcome`、closed reason codes与`StoreOperationCancelled`；不得把inactive rows或events加入public snapshot。`ValidatedPersistentState`定义在store implementation内部，不export。
- `features.py` produces：`analyze_responses_input(payload, *, timings=None) -> EstimateFeatures`。
- Compatibility：`estimate_responses_input()`暂保留为返回`known_tokens`的薄wrapper，后续count path改用完整features。

- [ ] 实现canonical top-level／item hashing、rolling prefix chain和component extraction；unknown字段进入hash与quantitative `FeatureVector`，不进入ordinary-text tokens；`ProfileKey`只保留exact categorical compatibility facts。
- [ ] 显式分类Responses message、function call／output、reasoning summary、encrypted reasoning、image／media和unknown items；实现Spec `framing-v1`和`cold-start-prior-v1`。Responses instructions／messages／tool schema／function-call arguments／output的全部configured special spellings走ordinary encoding，不使用default guard或`allowed_special`。
- [ ] 保留现有timing observations，并让worker可返回可pickle的`EstimateFeatures`。`test_real_worker_keeps_encoding_failure_and_stage_metrics`的special-spelling failure改成synthetic estimator exception，继续验证failure timing而不把合法ordinary text钉成失败。
- [ ] 添加mechanics测试与缺陷注入控制，证明ciphertext／base64增长不再放大ordinary component，同时可见文本仍改变known tokens；以独立stub tokenizer和literal arithmetic断言Spec样本`known_tokens=29`、cold-start／public=35，并分别判红fixed-1与missing-framing mutation。
- [ ] 跑`uv run pytest tests/unit/tokenization/test_features.py tests/unit/tokenization/test_responses_estimator.py tests/unit/tokenization/test_local_token_worker.py`。
- [ ] 以`fix: model structured token estimate features`为语义提交主题。

### Task 3：实现versioned SQLite learning store

**Files**

- Create：`src/app/tokenization/learning_schema.py`
- Create：`src/app/tokenization/learning_store.py`
- Modify：`src/app/tokenization/types.py`
- Modify：`src/app/config/paths.py`
- Modify：`pyproject.toml`
- Modify：`tests/unit/tokenization/test_features.py`
- Create：`tests/unit/tokenization/test_learning_store.py`

`uv.lock`不属于Task 3 tracked files。`/uv.lock`被`.gitignore`忽略，`docs/.human-controlled/release-and-deployment.md`定义它为workspace environment而非distribution／uvx dependency contract；Task 3只在`pyproject.toml`声明dependency。本计划此前要求modify／force-add `uv.lock`是reviewer-caught plan-mandated defect，已撤销；若未来要跟踪lockfile，必须另作repository decision并同步人控release合同与`.gitignore`。

**Interfaces**

- Consumes：Task 2 immutable DTOs。Task 3新增store-private `ValidatedPersistentState`用于all-epoch／event validation；public `LearningSnapshot`只补齐一个active identity／epoch的bounded `prediction_records`／`evaluations`，cardinality不变。允许把`StoredSample.observed_at`窄改名为UTC Unix-microsecond integer `observed_at_us`，不改变其它Task 2 feature semantics；另新增`AnchorUseIntent`／`AnchorUseOutcome`、closed reason codes与`StoreOperationCancelled`。
- Produces：`TokenLearningStore.start()`、`snapshot_for_prediction(identity) -> LearningSnapshot`、`apply_sample(analyzed_sample, transition)`、`record_event()`、`record_anchor_use(intent) -> AnchorUseOutcome`、`prune()`、`close()`。
- Queue／predictor boundary：Task 3只实现persistence methods、private validation和active snapshots，不创建sample／anchor-use queue、background lifecycle或prediction algorithm；Task 4的request-side `PredictionDecision`可含intent，prequential record不含intent；Task 5／pipeline orchestrator只拥有request decision intent的queue和调用时机。
- Storage：`tokenization_learning_path()`返回existing config directory下的`tokenization-learning.sqlite3`；使用`aiosqlite>=0.22.1`＋SQLite WAL，不存raw payload或free-form durable text。

**Cancellation-safe ownership**

- [ ] 建立共享confirmed-completion helper，覆盖connection open、所有execute／read、`BEGIN`／`BEGIN IMMEDIATE`、cursor close、`COMMIT`、`ROLLBACK`、checkpoint和connection close。Queue action及completion future在await前登记；outer cancellation后shield到worker返回。
- [ ] Open取消时先确认open结果，有connection则confirmed-close后传播。BEGIN取消时确认是否执行；若成功且COMMIT未enqueue，confirmed-rollback和cursor close后传播。
- [ ] `StoreOperationCancelled`继承`asyncio.CancelledError`并携带closed phase＋`committed_observation|None`，使enclosing task保持cancelled semantics。COMMIT enqueue后shield到确定结果；成功后携带durable observation，pre-commit cancel为None。
- [ ] Lifecycle／reader／writer lock acquisition也用confirmed ownership。`close()`同步登记ticket，标记CLOSING后按lifecycle→reader→writer取得locks；LOCK_WAIT取消先完成close再传播。任何路径不得无锁close connection；concurrent close共用一个completion且physical close恰好一次。

**V1 schema authenticity and migration**

- [ ] `schema_meta`保存version＋manifest digest；每个TableManifest另有independent fixed normalized table-DDL digest，覆盖column COLLATE、全部CHECK和STRICT，并与PRAGMA manifest共同验证。NOCASE fake即使meta／indexes不变也必须MANIFEST_MISMATCH且bytes不变。
- [ ] Startup graph要求每sample one record＋exact anchor；commit-time计算all candidate-key evaluations。Persisted evaluation对每candidate key各自canonical newest128 matching samples mandatory；older absence合法，每个retained row唯一match且no extra。Represented methods各有一个point-in-time champion，absent method没有champion；prefix／event／metadata closure不变。
- [ ] Existing path先read-only inspect。Unsupported、corrupt、fake V1或partial nonempty schema在任何mutating PRAGMA前typed fail且原file bytes不变。
- [ ] Fresh／empty writer设置non-destructive PRAGMAs；WAL acquisition走async busy retry；confirmed `BEGIN IMMEDIATE`后重读schema，仍empty才create，peer已完成则validate／continue。Reader只在migration commit后open；所有busy重跑完整ownership flow。

**Atomic transition, revisions, durable events**

- [ ] `apply_sample()`固定执行duplicate→fresh private state→transition→insert／update→victims／affected→identity＋global revisions→cascade prune→post-transition event→confirmed COMMIT。用test-only BEFORE DELETE trigger／transaction trace证明revision已先推进，full identity deletion仍推进global revision。
- [ ] Application duplicate check和database unique constraint分别保留、分别mutation；duplicate不调用transition、不增加revision。完全删除identity时global DB revision／foreign `data_version`必须使旧cache失效。
- [ ] Durable observations只含closed `LearningReasonCode`／`DriftReasonCode`和per-variant bounded primitive metadata。删除free-form durable`detail`／`reason`；arbitrary prompt／exception text不能构造DTO或进入`record_event()` row。Raw exception text只可去DB外best-effort warning。

**Bounds and exact prune policy**

- [ ] 保持sample／event caps；evaluation rows按candidate key／`ProfileKey`／identity／epoch各自保留newest128 retained samples containing candidate，同method variants预算独立。Older evaluation可删但sample／record／actual保留，drift 160从record冻结的method champion＋actual重建。
- [ ] Anchor source sample的`last_used_order`初始化为evidence creation order。Task 4 request-side `PredictionDecision`返回可选`AnchorUseIntent`；Task 5／pipeline只把request decision intent在critical path外排队调用`record_anchor_use(intent)`，prequential challenger不排use。Source missing返回typed `PRUNED` no-op；queue failure不改变last-confirmed persisted use；store无queue／task。
- [ ] Persist UTC Unix microseconds integer `observed_at_us`。Sample tie按inactive→anchor use→prefix coverage→`observed_at_us`→`process_boot_id` BINARY→`request_id` BINARY→numeric attempt index。Identity tie按fixed LearningIdentity field order，text BINARY、integers numeric。

**Tests and controls**

- [ ] Test-side `EXPECTED_ACTION_IDS`人工转录Spec的108 bases／204 IDs；production ledger、test literal、runtime confirmed trace三方ID set相等。Raw-aiosqlite mapping另断言每call恰有一个ID并覆盖raw expected subset；matrix只从test literal生成。
- [ ] Independent schema oracle列出每个table全部CHECK／column COLLATE／STRICT、fixed normalized DDL digest及PRAGMA facts；NOCASE fake和每项schema mutation均fail-visible且原bytes不变。
- [ ] Barrier明确保证两个fresh starters都完成complete empty read-only inspection后才竞争ownership；再验证one creator／one validator、WAL busy完整retry和reader migration后open。
- [ ] Independent private expected区分newest-128 evaluation missing＝corrupt、older missing＝allowed、extra／mismatch＝always corrupt；另以160 retained records＋actual和128 rows验证drift reconstruction。其它SF1-03 fixtures及active snapshot oracle不变。
- [ ] Durable free-text rejection保持row／revision不变；A35钉revision order；A37 close locks、A38 NOCASE manifest、A39 graph closure各有single target mutation；thread provenance保持true connect／close oracle。
- [ ] Prune tests逐维覆盖epoch activity、confirmed anchor use、prefix coverage、UTC integer `observed_at_us`、BINARY／numeric sample及fixed-field identity ties；每个identity dimension独立mutation。Duplicate application check与unique constraint分开mutation。
- [ ] Run `uv run pytest tests/unit/tokenization/test_learning_store.py` and `uv run pytest tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py`；Ruff／Pyright覆盖所有changed paths。Dependency resolution validation不得改变Task 3 tracked file list。
- [ ] 只参考`src/.archived/app/history/sqlite/writer.py`的lifecycle形态，不导入archived module、不复制business schema。
- [ ] 以`feat: persist token prediction history`为semantic commit主题；exact pathspec只含上述Task 3实际changed tracked files。

### Task 3A：闭合candidate、visual capability与decision persistence合同

Task 3的SQLite ownership／cancellation／bounds语义已经review完成；Task 4A派发前的独立合同／DTO复核发现，现有DTO和V1 schema仍无法表达同method多candidate的paired facts、A18独立visual tokens及request-side anchor intent carrier。本任务是Task 4A的前置语义切片，不重开Task 3已闭合的无关机制。V1尚未集成main或进入production learning lifecycle，因此本轮在未发布边界内同步修订V1；若实施时发现已有外部V1 database事实，必须停止in-place修订并先改为新schema version＋migration。

**Files**

- Modify：`src/app/tokenization/types.py`
- Modify：`src/app/tokenization/features.py`
- Modify：`src/app/tokenization/estimators.py`
- Modify：`src/app/tokenization/worker.py`
- Modify：`src/app/tokenization/learning_schema.py`
- Modify：`src/app/tokenization/learning_store.py`
- Modify：`tests/unit/tokenization/test_features.py`
- Modify：`tests/unit/tokenization/test_responses_estimator.py`
- Modify：`tests/unit/tokenization/test_local_token_worker.py`
- Modify：`tests/unit/tokenization/test_learning_store.py`

**Interfaces**

- `types.py`新增closed `PredictionCandidateVariant`、`PredictionCandidateKey`、`MethodChampion`、ephemeral `PredictionDecision`和pickle-safe tokenization capability container。Task 3A只为A18 mechanics提供明确标为synthetic／unresized的patch-grid formula variant，不声称真实descriptor resize／limit已闭合；Task 8在接production catalog前拥有`types.py`并以已核provider事实扩展closed formula union。四个`PredictionMethod`成员与优先顺序不变；只接受Spec §6.0七种method／variant pair。
- `EstimateFeatures`新增`capability_visual_tokens: int | None`，与known／components／FeatureVector分槽；`None`与0不同。`analyze_responses_input(payload, *, capabilities=None, timings=None)`按每个media item应用capability snapshot公式后求和；旧caller不传capability时保持typed absence与具名reason。
- `PredictionRecord`保存candidate-key unique candidates、每represented-method point-in-time champion／eligibility和global selected key；absent method没有champion。`PredictionEvaluation`按candidate key对账。`PredictionDecision`只绑定request-side selected prediction与可选`AnchorUseIntent`，不进入record／candidate／event persistence。
- V1 samples专列nullable visual tokens；prediction／evaluation schema、JSON codecs、PK／CHECK／indices、manifest、graph validation和diagnostic retention都改用candidate key。Task 3 confirmed-action semantic bases／expanded IDs保持108／204且不增加raw `aiosqlite` call site。

- [ ] 实现candidate variant／key／champion／selected DTO invariants：同method不同variant合法；每represented method恰有一个champion，absent method无champion；represented exact与cold champions必须eligible，prefix／profile才可false；duplicate key、非法pair、represented-method missing／duplicate champion、absent-method extra champion、wrong／missing key、exact／cold false和selected非首eligible champion全部拒绝。Cold-only record只含eligible cold candidate／champion／selected且合法；actual0 relative semantics不变。
- [ ] 实现最小pickle-safe visual capability seam和明确命名的synthetic／unresized per-item patch-grid formula；A18的known29与visual6分别可读，56×84与同面积42×112分别为6／8，公式或任一required metadata缺席时visual为`None`并保留reason。增加estimator generation。本formula只证明分槽、presence、pickle、per-item arithmetic和V1 persistence，不冒充真实descriptor resize／limit；Task 8以已核provider事实扩展同一closed representation后才接production catalog，不在本任务提前猜provider／PDF规则。
- [ ] 同步V1 dedicated visual column、selected method＋variant、method champions JSON、candidate JSON variant、evaluation method＋variant PK／CHECK／index、event evaluation JSON、fixed DDL／manifest digests与all-epoch validation；每candidate key各保留newest128 diagnostics，older reconstructable facts不变。
- [ ] 保持Task 3 cancellation／migration／revision／prune／thread contracts和108／204 action-ID literal不变；schema修改不得新增或绕过confirmed aiosqlite action。
- [ ] 扩展independent tests：same-method多variants、selected／champion／eligibility corruption、candidate-key evaluation round-trip／bounds、visual`None`／0／6 round-trip、negative／bool／missing-column／wrong CHECK／DDL digests；intent字段必须在candidate／event JSON与DDL中缺席，`record_anchor_use()`独立行为保持。
- [ ] 运行Task 3A focused tests、完整`test_learning_store.py`与tokenization unit group；Ruff／Pyright覆盖changed paths。执行candidate-method collapse、exact／cold eligibility guard删除、evaluation PK少variant、visual塞known、visual column丢失和intent入candidate六个单变量mutations，核失败来自目标不变量并用文件快照恢复。
- [ ] 以`feat: preserve token prediction candidates`为semantic commit主题；独立review到0 Critical／Important后归档reviewed source，再更新Task 4A exact base。

### Task 3B：补齐per-item suffix、availability与prefix checkpoint carrier

Task 3B只交付feature／state carrier和store mechanics，不实现candidate formulas、prefix 16／8领域policy或Task 4A predictor。Exact base为Task 3A stacked integration candidate；V1尚未进入main／production，若发现外部V1事实立即停止原地修订并改新version＋migration。

**Files**

- Modify：`src/app/tokenization/types.py`
- Modify：`src/app/tokenization/features.py`
- Modify：`src/app/tokenization/learning_schema.py`
- Modify：`src/app/tokenization/learning_store.py`
- Modify only if required by real process pickle：`src/app/tokenization/worker.py`
- Modify：`tests/unit/tokenization/test_features.py`
- Modify：`tests/unit/tokenization/test_learning_store.py`
- Modify only if worker changed：`tests/unit/tokenization/test_local_token_worker.py`

**Interfaces**

- `EstimateFeatures`新增exact-conservation `FixedContextContribution`＋`input_item_contributions`，与compact positional prefix digest chain对齐；whole known／prior／visual由这些facts唯一重建。
- `StoredSample.committed_order: int | None`在policy pending阶段为None，store以post-transition global revision stamp；public／persistent sample必须positive。
- `LearningSnapshot`新增active-epoch bounded `PrefixEligibilityCheckpoint` rows；canonical ProfileKey JSON BINARY是identity，hash只作index。
- `LearningUpdate.prefix_checkpoint_command`是required NoChange／Replace／Delete union；logical Replace可携带唯一orderless `PendingPrefixChampionErrorTriple` tail，store在codec前与current sample以同一post-transition global revision stamp，再构造persistent positive-order evidence。Store stamp persistent checkpoint并产生required `PrefixCheckpointStoreOutcome`，完整覆盖committed／duplicate／rejected／failed／post-COMMIT cancellation；multiple pending、non-tail pending、persistent pending或early encode必须拒绝。
- Store capacity只rollover causal current identity且仅在能释放pre-existing rows时；global零收益分支typed reject checkpoint、sample照常commit。Capacity transition只嵌套在RolledOver outcome，不是DriftObservation或standalone field。

- [ ] Feature producer按每个input item独立accumulate visible／item4／nested4n／visual tri-state／prior，再与fixed context、components、whole known exact conservation；覆盖raw、non-object、message parts、reasoning、function output／media和unknown。
- [ ] Prefix fingerprints改compact digest array；fixed context三位置、item五位置compact JSON；788-item motivating shape及limit-neighbor round-trip，wrong arity／type／framing／non-finite／length／aggregate corruption全部拒绝。
- [ ] Store在policy entry后、codec前stamp committed order及checkpoint revisions；logical command required且NoChange无默认None。Replace／Delete expected prior revision提供transaction-fresh CAS，rollback原子。
- [ ] Prefix checkpoint table保存canonical ProfileKey JSON PK、hash index、mode／evidence／revision，独立sample FK；eligible16／demoted8 carrier invariants和ProfileKey collision两row共存。
- [ ] 实现4,096 per identity／epoch、32,768 global active checkpoint caps、inactive deterministic cleanup、zero-benefit typed reject、收益型current-identity rollover、drift＋NoChange precedence、cache／revision／event和termination semantics。
- [ ] Required checkpoint outcome matrix逐主outcome闭合：NoChange／Applied／Deleted／CapacityRejected／CapacityRolledOver／NotAttempted／NotCommitted；policy callable entry是attempted边界，standalone capacity字段禁止。
- [ ] 更新V1 manifest／DDL digests／private validation及Spec-owned action ledger为111 bases／211 IDs；新增`state.prefix-checkpoints-read`、`prefix-checkpoint.upsert`、`prefix-checkpoint.delete`，test literal／production registry／runtime raw mapping三方独立。
- [ ] Tests覆盖A40～A45、full-baseline known-only mutation、current-zero multiplicative mutation、current-sample same-transaction prune及其checkpoint／outcome mutations、sample-prune／restart survival、same transaction failure／cancellation真实phases、capacity current-prior0／positive、drift wrong command、same-hash JSON collision、committed-order same-time availability及existing Task3／3A regressions。
- [ ] 跑focused、完整learning-store、完整tokenization、Ruff、Pyright及direct mutations；以`feat: persist prefix learning prerequisites`为semantic commit，独立source review后squash到stacked integration base。

### Task 4A：实现cold-start、exact／deterministic prefix与prequential record

**Files**

- Create：`src/app/tokenization/prediction.py`
- Modify：`src/app/tokenization/scaling.py`
- Create：`tests/unit/tokenization/test_prediction.py`
- Modify：`tests/unit/tokenization/test_local_estimate_scaling.py`

**Interfaces**

- Consumes：Task 3B exact-conservation contributions、candidate／decision DTOs和single-active `LearningSnapshot`；不接收store-private state或events。
- Produces：request-side pure `predict_exact_or_prefix(features, snapshot) -> PredictionDecision`、prequential `build_prediction_record(sample_key, features, snapshot) -> PredictionRecord`、`evaluate(record, actual) -> tuple[PredictionEvaluation, ...]`及唯一`finalize_local_prediction(value, multiplier) -> int`。Task 4A不调用store／queue；caller构造`LearningUpdate`时显式使用`NoPrefixCheckpointChange()`。

- [ ] Cold-start按whole known＋whole visual-or-zero＋whole prior，保留reasons和未量化0；exact取1～5 actual median并携全部source intent。
- [ ] 无论exact是否selected，都尝试构造strictly shorter available deterministic prefix challenger；按coverage／newest／canonical sample-key选single anchor，suffix只sum anchor count后的item contributions。Same-prefix100／120、reversed tuple和four visual transitions精确断言。
- [ ] Record candidate tuple只含当时available exact／prefix deterministic／cold，按seven-pair canonical subsequence；champions按method order，sample count exact1～5、prefix1、cold0。Exact global selected不删除prefix challenger。
- [ ] `build_prediction_record()`拒绝current sample已在snapshot；`evaluate()`沿candidate order，actual0只absolute。Request decision只为selected exact／prefix带intent，prequential challenger不产use side effect。
- [ ] `finalize_local_prediction()`严格Decimal multiply→ROUND_CEILING→minimum-one；compat wrapper只delegate。Exact100.5、multiply order、negative／0、large integer与invalid input有完整断言。
- [ ] Mutations至少覆盖exact early floor、prefix matching median、tie／snapshot-order、exact-selected skip prefix、whole suffix subtraction、learn-before-evaluate、finalization先ceil和wrapper旧0；目标tests定向红并snapshot恢复。
- [ ] 跑prediction／scaling、完整tokenization、Ruff、Pyright；以`feat: predict tokens from exact history`为semantic commit并独立review。

### Task 4B-P：实现learned prefix variants

**Files**

- Modify：`src/app/tokenization/prediction.py`
- Modify：`tests/unit/tokenization/test_prediction.py`

**Interfaces**

- Produces pure revision-bound `PrefixPairIndex`／builder和prefix additive／multiplicative candidates／champion；Task 5以后按LearningIdentity＋snapshot revision缓存index，不持久化。

- [ ] Builder按committed order排序后单向建立context／prefix best-base lookup，复杂度`O(samples log samples + total prefix entries)`；future／equal-order base不可用，每longer只选single canonical base。
- [ ] Historical longer与current exact ProfileKey相同；完整`suffix_baseline_delta`包含item known＋visual-or-zero＋prior。Additive／multiplicative各minimum3；current baseline0仍保留历史支持的multiplicative candidate。Fixture必须让known-only baseline与full baseline分叉，并让current-zero gate mutation判红。
- [ ] 即使exact selected也保留available learned prefix variants；all variants共同paired records取canonical newest31，minimum8、strictly better、tie deterministic→additive→multiplicative。只读record＋actual，不依赖diagnostics。
- [ ] Tests覆盖same-time committed availability、single base、zero baseline、63 older／newest31反转、`evaluations=()`、reverse input、future base与canonical counts；NoPrefixCheckpointChange保持。
- [ ] 以`feat: learn token prefix residuals`为semantic commit，独立review后进入Task 4B。

### Task 4B：实现feature-aware profile candidates与prefix eligibility

**Files**

- Modify：`src/app/tokenization/prediction.py`
- Modify：`tests/unit/tokenization/test_prediction.py`

**Interfaces**

- Produces：profile additive／multiplicative candidates／champion，以及`advance_prefix_checkpoint(record, actual, checkpoint) -> PrefixCheckpointCommand` pure policy。Consumes Task 4B-P stable prefix champion；不改四个methods，不选择capacity victim。

- [ ] 实现same identity＋exact ProfileKey neighbor distance：equal-weight L1、log1p、pre-current MAD、MAD0→1、presence mismatch4、canonical tie；nearest31产生profile additive／multiplicative minimum3。
- [ ] 保存全部profile variants；至少8个全variant＋cold共同records后strictly better才eligible，variant tie additive；exact／prefix selected仍保留profile challenger。
- [ ] 用point-in-time method champions和actual>0更新current ProfileKey checkpoint。Eligible sliding latest16三方齐备、strict双>0.05才demote；trigger label不进recovery。Demoted sliding latest8，profile仅同8条全有才alternative，prefix<=best时删除恢复；actual0／missing facts NoChange。
- [ ] LearningUpdate携required Replace／Delete／NoChange command和expected prior revision；drift存在时Task 4C必须NoChange。Store capacity mechanics只解释command outcome，policy不选identity或stamp revision。
- [ ] Tests覆盖feature distance、candidate promotion、Profile A／B隔离、16边界／0.05 tie、8 bad后8 good、sample prune／restart checkpoint continuity、CAS与NoChange；对应feature／window／ProfileKey mutations定向红。
- [ ] 跑prediction＋learning-store相关selectors和完整tokenization；以`feat: calibrate token profiles and prefix eligibility`为semantic commit并独立review。

### Task 4C：实现drift detection与learning epoch

**Files**

- Modify：`src/app/tokenization/prediction.py`
- Modify：`src/app/tokenization/learning_store.py`
- Modify：`tests/unit/tokenization/test_prediction.py`
- Modify：`tests/unit/tokenization/test_learning_store.py`

**Interfaces**

- Produces：`DriftObservation`与epoch transition；profile drift使用点时profile method champion的128条reference／32条recent窗口，exact drift使用连续3个超阈值mismatch。Drift sample进入E+1而record prediction epoch为E；checkpoint command／outcome必须NoChange，old-E checkpoints清除且不叠加capacity transition。

- [ ] Profile drift从retained PredictionRecord的candidate-key method champion＋sample actual重建paired errors，不能以bounded evaluation rows或事后variant reselection作分母；在160 records／每candidate-key128 diagnostics下仍形成recent32＋reference128。既有thresholds和exact mismatch规则不变。
- [ ] 定义恢复：新epoch只用cold-start和新anchors，达到普通profile champion样本条件后自动恢复learned prediction；旧epoch保留到prune供offline复查。
- [ ] 添加recent／reference互斥边界、样本不足不触发、单一outlier不触发、持续bias触发、禁用／反转trigger后断言变红、epoch隔离与恢复测试。
- [ ] 跑`uv run pytest tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_learning_store.py -k 'drift or epoch'`。
- [ ] 以`feat: adapt token prediction to drift`为语义提交主题。

### Task 5：建立learning service与lifespan

**Files**

- Create：`src/app/tokenization/learning.py`
- Modify：`src/app/core/chain.py`
- Modify：`src/app/server/pipeline_app.py`
- Create：`tests/unit/tokenization/test_learning_service.py`
- Modify：`tests/systemd/test_systemd_units.py`

**Interfaces**

- Consumes：Task 2 samples、Tasks 3～3B store／checkpoint outcome、`AnchorUseOutcome`和Tasks 4A／4B-P／4B／4C pure strategies／`PredictionDecision`。Task 5按完整LearningIdentity＋snapshot revision缓存pure `PrefixPairIndex`，revision变化重建，不持久化index。
- Produces：sample offer和anchor-use offer两个typed outcomes、`predict(identity, payload) -> PredictionDecision`、`start()`、`close()`；在request critical path外只消费request decision的`anchor_use_intent`并调用Task 3 `record_anchor_use(intent)`。
- Ownership：Task 5／pipeline orchestrator拥有sample／anchor-use queues、background lanes和request lifecycle；Task 4只产ephemeral decision，prequential record丢弃intent，Task 3只执行persistence。Queue-full／closed记录typed observation，不能预写或声称persisted use。

- [ ] 实现32-item／64-MiB body queue和bounded anchor-use queue；后者在critical path外调用`record_anchor_use(intent)`，处理`RECORDED`／`PRUNED`。Queue failure记录observation并保持last-confirmed use不变。
- [ ] 在Chain构造service，并把lifespan调整为startup加载、shutdown停止接收、drain、commit／checkpoint、close，最后再取消其它background tasks。
- [ ] 测试sample／anchor-use queue saturation、PRUNED no-op、queue failure不冒充persisted use、analyzer／DB failure、foreground responsiveness、shutdown drain和smooth restart。
- [ ] 冻结background worker直到request completion已经发布，再恢复worker并断言晚到commit／error进入独立learning event；任何试图修改已冻结RequestLine的变异必须判红。
- [ ] 跑`uv run pytest tests/unit/tokenization/test_learning_service.py tests/systemd/test_systemd_units.py`。
- [ ] 以`feat: run token learning lifecycle`为语义提交主题。

## External sequencing gate before shared pipeline wiring

Direct buffered Chat的living tracking显示Task 4～7仍将重写`RequestContext／Attempt`、`DirectDriver._prepare_and_send()`、`ResponseHandoff`、candidate finalization、`_absorb_response_observation()`与`RequestCompletion`。因此Token Tasks 6、7、9、10不得与它并行修改这些shared seams。

执行顺序在这里显式重排为Tasks 1～5 → Task 8 → external gate → Tasks 6、7、9～11。Tasks 1～5和Task 8只产出tokenization-local类型／策略／service，可先完成；若Task 8完成后外部gate仍未闭合，则暂停，不启动Tasks 6、7、9、10、11的shared-pipeline改动。进入Task 6前必须重新读取`.dev/docs/direct-buffered-chat-completions/tracking.md`和最终已集成源码，并满足二选一：

1. Direct buffered Chat Tasks 4～7已集成到main，则把Token sent snapshot／learning offer接到最终`ResponseHandoff`、selected-candidate callback与attempt／request finalizer上，更新本计划Task 6的具体符号并重新做一次限定plan review；
2. 尚未集成，则暂停所有shared pipeline wiring，保留已完成tokenization slices，不抢占该计划的owner，也不并行写同一接口。

这是一条外部依赖，不是缩减local tokenizer范围。最终学习语义不变；只允许按落地后的共同seam调整接线符号。

### Task 6：捕获actual sent attempt并恰好学习一次

**Files**

- Modify：`src/app/pipeline/request.py`
- Modify：`src/app/pipeline/direct_driver/base.py`
- Modify：`src/app/server/routes/inference.py`
- Modify：`src/app/pipeline/response_observation.py`
- Modify：`tests/unit/pipeline/test_prompt_admission_driver.py`
- Modify：`tests/int/test_pipeline_app.py`

**Interfaces**

- `Attempt.sent_request: SentRequestSnapshot | None`；`Attempt.learning_offer_state`为typed exactly-once状态。
- `_absorb_response_observation()`接收具体`Attempt`与learning service，构造`CompletedTokenSample`后offer；不能在后台closure中重读`context.current_attempt`。

- [ ] 在`_prepare_and_send()`的同一response上读取`response.request.content`并冻结sent snapshot；未取得headers的attempt没有snapshot。
- [ ] 在stream／buffered共同final observation汇合点验证endpoint、source protocol、terminal kind、exact raw total usage与inconsistent flag，然后compare-and-set offer；production ASGI inference必须形成committed sample、pre-learn prediction／error和可被later count读取的snapshot。
- [ ] 保持raw total `upstream_input_tokens`为唯一label；translation／delivery后续失败不撤销已成立sample，也不把sample接受投影成请求成功。
- [ ] 添加subscriber最后改写、ordinary retry、stream replay、buffered double-absorb、completed／incomplete／failed／cancelled、cache target与Chat负控；另加完整production inference→learn→later identical exact／append-only prefix闭环，并分别注入lost offer／anchor transition与normalized fresh／output reasoning错误label。
- [ ] 跑相关`tests/unit/pipeline/`选择器和`uv run pytest tests/int/test_pipeline_app.py`。
- [ ] 以`feat: learn from exact upstream attempts`为语义提交主题。

### Task 7：把count provider chain改为lazy prediction

**Files**

- Modify：`src/app/pipeline/count_tokens.py`
- Modify：`src/app/pipeline/driver.py`
- Modify：`src/app/model_provider/registry.py`
- Modify：`tests/unit/tokenization/test_token_counting.py`
- Modify：`tests/int/test_pipeline_app.py`
- Modify：`tests/unit/pipeline/test_error_classify.py`

**Interfaces**

- Consumes：Task 8 `analyze_anthropic_input()`；因此实际执行顺序必须先完成Task 8，再进入本Task。
- `LocalCounter`改为async callable并只在chain轮到`local`时调用。
- `shape_request()`先冻结本次实际inference target的resolved model／wire payload。每个非local counter name选择自己的provider transport，但只有在它能为**同一target model与Anthropic count contract**计数时才执行；不为计数另行reroute成另一个模型。Local始终估算冻结的actual target payload，不继承上一条remote leg的状态。
- Local result携带`TokenPrediction`，driver只投影public body与observation。

- [ ] 重构chain使provider order真实控制调用顺序、retry和fallback；Responses `no-counter`继续进入local predictor。
- [ ] 移除`handle_count_tokens()`的eager estimate。按本计划执行顺序，Task 8已产生`analyze_anthropic_input()`；因此Task 7同时把Responses local腿接到新predictor，并把direct Anthropic upstream count success的同payload raw estimate／actual迁入新history store。两条路径都先返回答案且不受learning failure影响；legacy `CalibrationEngine`只读兼容旧state，不再接收新样本。
- [ ] Public Anthropic counter用`type(value) is int and value > 0`拒绝boolean、0与其它malformed count，并按provider failure继续下一腿；Responses learning的raw usage validator独立允许0，但只进入exact／additive evidence。按Spec §3.3锁定`CountTokensRequestError`、`CountTokensUnavailable` cause／no-cause、named ProviderError及upstream status／body的完整Anthropic envelope。
- [ ] Driver把未量化prediction与`local_estimate_multiplier`交给Task 4A唯一`finalize_local_prediction()`；只在这里得到public整数并记录`operator-scaled`，unscaled prediction进入evaluation，driver不得自行round。
- [ ] 添加真实ASGI入口测试和provider spies，覆盖`[ghc,local]`、`[local,ghc]`、两个不同provider、local failure与Responses no-counter；另以literal`<|endoftext|>`覆盖direct Anthropic local和Anthropic→Responses local的完整success object／non-500／local-worker与provider-call counts，并执行eager-local、default-guard缺陷注入。
- [ ] 跑`uv run pytest tests/unit/tokenization/test_token_counting.py tests/int/test_pipeline_app.py -k count_tokens`。
- [ ] 以`fix: honor token counter provider order`为语义提交主题。

### Task 8：补齐Anthropic thinking与media baseline

**Files**

- Modify：`src/app/tokenization/types.py`
- Modify：`src/app/tokenization/features.py`
- Modify：`src/app/tokenization/estimators.py`
- Modify：`src/app/model_provider/types.py`及catalog capability映射文件
- Create：`tests/unit/tokenization/test_anthropic_features.py`
- Modify：相关model descriptor tests

**Interfaces**

- Task 8拥有`tokenization/types.py`的capability extension：先以已核provider事实把Task 3A仅用于synthetic mechanics的unresized patch-grid union扩成能表达descriptor resize／limit／visual formula的closed production representation并增加estimator generation，再由exact model descriptor／catalog adapter产生`TokenizationCapabilities`；feature core不直接依赖完整provider descriptor。
- `analyze_anthropic_input(request, capabilities) -> EstimateFeatures`；thinking retention从capability读取，不再从role单独猜；Anthropic和Responses共用同一presence-aware `capability_visual_tokens`槽，不另造representation。
- Media贡献保留dimensions／source kind／byte features；base64本体不进入text component。Task 8只生产Anthropic features与catalog capability adapter，不修改shared driver；Task 7在external gate后为frozen exact target消费该producer并迁移direct Anthropic learning。

- [ ] 按current turn、keep-all、last-turn-only分类thinking／redacted thinking；descriptor未知时返回低置信baseline和明确reason。Anthropic top-level system、messages与tool schema的全部configured special spellings使用ordinary encoding，且不改变thinking／opaque classification。
- [ ] 显式计入LT-09的`tool_use.id／name`与`tool_result.tool_use_id／is_error`，并以官方count delta作为独立oracle；unknown block保留完整hash／feature和低置信reason。
- [ ] 解析可得的image dimensions／PDF page metadata；以官方／recorded provider事实固定并测试resize／limit参数、边界与公式后扩展closed capability DTO，production catalog只生成该已核variant。不可得时保留feature并依赖history prior，不把Task 3A synthetic unresized formula、base64／URL长度或aggregate pixels冒充production visual count。
- [ ] 用官方count semantics和已有保存样本添加model差异、thinking长文本、tool identifier delta、同尺寸不同压缩图、tool_result media与unknown block测试；fake只验证本方逻辑，官方／recorded evidence才裁协议。
- [ ] 跑相关tokenization、count endpoint与model catalog tests。
- [ ] 以`fix: model anthropic structured token inputs`为语义提交主题。

### Task 9：闭合context editing与响应完整性

**Files**

- Modify：`src/app/pipeline/driver.py`
- Modify：`src/app/pipeline/anthropic_request_hook.py`
- Modify：token feature／prediction types
- Modify：`tests/int/test_pipeline_app.py`
- Modify：`.dev/docs/token-counting/spec.md`对应revision record

**Interfaces**

- Count与send共用同一effective-request transform；prediction record区分original／effective features。
- Upstream count success保留完整response object，包括`context_management.original_input_tokens`。

- [ ] 接通proxy-owned context-editing配置并保证client-supplied edits同路径生效；count针对effective payload。
- [ ] Local结果按Spec表达post-edit估算与original provenance；upstream response不再压成裸int后重建。
- [ ] 添加完整对象相等、字段缺席、edit触发／未触发和pre-edit冒充post-edit缺陷注入控制。
- [ ] 跑count endpoint、request hook与context editing相关测试。
- [ ] 以`fix: preserve edited token count semantics`为语义提交主题。

### Task 10：统一observability并提供offline evaluator

**Files**

- Modify：`src/app/observability/request_completion.py`及其聚合record owner
- Create：`src/app/tokenization/evaluate.py`
- Modify：`tests/unit/observability/test_request_completion.py`
- Create：`tests/unit/tokenization/test_evaluate.py`

**Interfaces**

- Request completion facts只含同步可知的prediction method、identity／`ProfileKey`、history revision、low-confidence reasons、operator scaling与offer outcome。
- `TokenLearningObservation`以sample identity关联request／attempt，记录最终committed／duplicate／rejected／failed、closed reason codes、bounded typed metadata、prequential errors和new revision／epoch；SQLite可写时它进入bounded durable `learning_events`和结构化日志，DB不可写时降级为明确标注best-effort且可携带bounded exception text的application warning，不回写冻结RequestLine。
- `python -m app.tokenization.evaluate --database <path>`只读SQLite并输出按method／provider／model／profile聚合的count、bias、median APE、p90 APE、coverage与drift摘要。

- [ ] 在learning／prediction owner处产生两类typed facts，RequestLine和late learning event各自只投影自己的真值时点；本计划不改TUI显示合同。
- [ ] 实现offline progressive replay，确保每条sample先predict／evaluate再learn；不把准确率阈值接成CI gate。
- [ ] 添加RequestLine完整对象、late-event关联、worker延后完成、DB failure warning、缺席语义、unknown reason和learn-before-evaluate缺陷注入控制。
- [ ] 跑`uv run pytest tests/unit/observability/test_request_completion.py tests/unit/tokenization/test_evaluate.py`。
- [ ] 以`feat: expose token learning accuracy`为语义提交主题。

### Task 11：收口alternate service、配置候选和完整验证

**Files**

- Modify：`tests/unit/tokenization/test_token_counting.py`及真实production-entry tests
- Modify：`.dev/docs/token-counting/{README.md,spec.md,plan.md,status.md}`
- Modify：`.dev/human-controlled-docs-candidates/token-counting-config.md`
- Preserve：`src/app/tokenization/service.py`，除非用户另行明确授权删除已实现功能

**Produces**：完整实施状态、未采纳路线、仍未解决项与可重跑的accuracy诊断；alternate service不再充当production行为证据。

- [ ] 把字段保留、provider chain和fallback断言迁到ASGI／production driver入口；保留alternate service但标清其非production地位。
- [ ] 为`local_estimate_multiplier`写候选配置说明：它是prediction后operator bias，不参与learning；不直接修改人控样例。
- [ ] 运行本地forensic probe：报告cold-start、注入历史后的exact／prefix方法与921,248 evidence对照，同时重申reconstructed identity边界。
- [ ] 逐项执行本计划的双向控制；任何mutation恢复都使用文件快照而非`git checkout`，恢复后核`git diff`。
- [ ] 运行`uv run ruff check src tests`、`uv run pyright src tests`、`uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`；确认`git diff -- src/app/observability/tui.py tests/tui .dev/docs/tui/spec.md`为空，因此独立TUI测试组不在本计划范围内。
- [ ] 派独立合并态reviewer覆盖Spec、production dataflow、SQLite并发、history prediction、observability、测试oracle和全部LT处置；修到0 blocker／0 major。
- [ ] 更新living status与Spec revision record，按项目约定处置原始报告和计划；以`docs: close token prediction learning work`为最后语义提交主题。不推送。

在整个计划完成前，living status逐项保留未完成任务；任何中间提交只声称其已交付的语义范围，不提前宣称整个local tokenizer已经精确。

## Resolved planning state

没有剩余阻断性产品问题。调用接缝已核到`Attempt.payload`、`response.request.content`、per-attempt `ResponsesObserver`、`UsageObservation.exact.upstream_input_tokens`和`_absorb_response_observation()`。Responses local-success shape不变；direct Anthropic upstream success恢复官方可选`context_management`字段。实施若发现还必须新增其它客户端字段或改变公开错误状态，立即暂停该切片并把新分叉交给用户；学习算法、状态与调度细节不再反复询问用户。

仍有一个显式执行依赖而非设计未决：direct buffered Chat Tasks 4～7必须先稳定shared response handoff／finalization seam；Token Tasks 1～5和8可先行，pipeline wiring按前述external gate串行。
