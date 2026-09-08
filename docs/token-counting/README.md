# Token counting

本目录是 token counting 的当前入口。它把需求权威、完整行为合同、批准的实施计划、唯一 volatile 状态投影和点时证据分开，避免从既有代码或事故报告反推产品合同。

## 文档地图

- [spec.md](spec.md) 是normative、living的唯一token-counting行为Spec。它完整定义public success／error wire、ordinary-text special spellings、counter选择、deterministic cold-start、`ProfileKey`／`FeatureVector`、history prediction、learning、persistence、failure和observability，并在每次行为修订时追加revision record。
- [plan.md](plan.md) 是批准的实施计划，承接 `/home/xp/.claude/plans/serialized-moseying-corbato.md` 的全部语义任务和 external sequencing gate。它可以记录每项任务的执行证据和评审处置，但不充当项目级当前状态。
- [status.md](status.md) 是本主题唯一的 volatile 状态投影，回答当前阶段、下一步、阻塞和最近验证事实。
- [HANDOVER.md](HANDOVER.md) 是2026-09-07 Task 3B authority review后的活交接入口；当前状态为`草稿·未评审`，完整复述必须回指status／Spec／plan snapshot，冲突时这些named authorities胜出。
- [token-counting-config.md](../../human-controlled-docs-candidates/token-counting-config.md) 是供用户自行摘取的人控配置候选，不是 `docs/.human-controlled/` 合同，也不授权直接修改人控文档。

## 权威顺序

1. `docs/.human-controlled/`是需求层的最终耐久权威；本topic另有R1／R3两次`user-selected-from-proposal`决定和R2／R4两句direct user-natural-language要求。[spec.md §2.2～§2.3](spec.md)以transcript UUID／tool id／source UUID／timestamp记录其一手来源、授权scope和implementation-derived additions。若未来人控文档或新的直接用户裁决与其冲突，必须先取得用户重裁。
2. [spec.md](spec.md)是实施者在上述边界内推导并维护的完整行为合同。Proposal description与user exact text未覆盖的cold-start、identity、eligibility、persistence、prequential error、drift、version migration、state bounds和fallback细节必须明确标为implementation-derived。
3. [plan.md](plan.md) 规定实施顺序与交付切片；[status.md](status.md) 单独投影执行中的当前状态。
4. 现有代码、测试和下列调查报告是证据或转录，不能反向改写用户裁决或 Spec。实现与 Spec 不一致时，应修实现或升级真实的产品分叉，不得把 Spec 改成当前缺陷的说明书。

Count-specific error mapping由 [error-envelope Spec](../error-envelope/spec.md) 拥有category、status、carrier和cause passthrough；本主题Spec完整转录其count子集，避免实现者依赖未命名的“既有mapping”。两份living Spec必须在相关error合同变化时同步，发生冲突时以error-envelope Spec为该横切事实的authority。

## 合同导航

- Deterministic cold-start equation、`framing-v1`、`cold-start-prior-v1`、exact-conservation fixed／per-input-item contributions、presence-aware visual与compact 788-item carrier见[spec.md §4](spec.md)。
- Literal`<|endoftext|>`及全部configured tokenizer special spellings在完整Anthropic／Responses surfaces上的ordinary semantics见[spec.md §4.3](spec.md)，unit／production controls见§12 A24～A25。
- Exact categorical `ProfileKey`、quantitative `FeatureVector`、equal-weight L1、MAD pool、presence penalty 4与neighbor tie-break见[spec.md §5](spec.md)。
- 四个public methods下的candidate keys／champions、all-available selection、single-source per-item suffix、learned variants和per-ProfileKey checkpoint 16／8 state machine见[spec.md §6](spec.md)；committed availability见§5。
- Production inference→same-attempt raw-total sample→later exact／prefix count闭环见[spec.md §7.4](spec.md)。
- Sample／checkpoint bounds、logical command／required outcome矩阵、zero-benefit capacity rejection、current-identity rollover、111／211 confirmed actions与durable event见[spec.md §7～§8](spec.md)。
- Count-specific Anthropic error status／type／code／body见[spec.md §3.3](spec.md)，横切authority仍是[error-envelope Spec](../error-envelope/spec.md)。

## Decision provenance与review材料

- [用户裁决来源取证](reports/user-rulings-source-research-2026-09-07-sonnet.md)记录R1／R3 proposal selection与R2／R4 queued-command user text，终态verdict为`found-partial`。
- [Cross-session Spec review](reports/spec-review-2026-09-07-gpt-high.md)记录ordinary special-spelling与decision provenance两项major finding。
- [Review disposition](spec-review-disposition.md)拥有finding采纳范围、source classification和re-review去向；它不是behavior authority。
- [Special-token point-in-time investigation](reports/special-token-counting-research-2026-09-07-claude.md)记录`tiktoken 0.14.0`的default guard、ordinary encoding与两条production ASGI 500；它证明mechanics和failure location，不冒充provider billing accuracy。
- [Task 4A prefix contract review](reports/260907-task4a-prefix-contract-review-gpt-high.md)在Spec `829f11ef…`上发现typed intent carrier、single-source oracle与sample-key tie三项缺口；点时verdict为0 Blocker／2 Major／1 Minor。
- [Task 4A prediction DTO gap review](reports/260907-task4a-prediction-dto-gap-review-claude.md)证明同method多variants、visual 29＋6分槽与ephemeral intent无法由Task 3旧DTO／V1 schema表达；点时verdict为2 Blocker／1 Major。两份报告是本轮Spec／plan修订的触发证据，不替代current authority。
- [Task 3A prefix contract re-review](reports/260907-task3a-prefix-contract-rereview-gpt-high.md)在Spec `c81d9046…`上关闭原3项finding，结论0 Blocker／0 Major／1个plan-summary Minor，明确Task 3A合同可实施。
- [Task 3A prediction contract re-review](reports/260907-task3a-prediction-contract-rereview-claude.md)在同一snapshot关闭visual finding，但以cold-only反例保持candidate／decision两项open并新增1 Blocker／1 Major／1 Minor；current authority随后按represented methods、双error sequences、active restatements与tuple-route disposition继续修订。
- [Task 3A prediction contract second scoped re-review](reports/260907-task3a-prediction-contract-rereview-2-claude.md)在Spec `f734f8bf…`／plan `3dc7d335…`上关闭上一轮全部open findings及prefix plan-summary Minor，终态0 Blocker／Major／Minor／Nit，明确Task 3A contract可实施、Task 4A仍等待reviewed source。
- [Task 3A implementation brief review](reports/260907-task3a-brief-review-gpt-sonnet.md)在brief `88b5518f…`上发现exact／cold unconditional eligibility和synthetic→production visual capability handoff两项Major；current Spec／plan／brief已据此继续修订。
- [Task 3A implementation brief scoped re-review](reports/260907-task3a-brief-rereview-gpt-sonnet.md)在brief `f2db75d3…`上关闭原2项Major，结论0 Blocker／Major／1个mutation-report计数Minor并允许implementer dispatch；该Minor已在最终brief `6f98acb6…`中改为逐项列名六个mutations。
- [Task 3A implementation report](reports/260907-task3a-implementation-claude.md)逐字保存candidate `56ec5e7`的实现、exact commands、533／368 tests、Ruff／Pyright及六项mutation／恢复证据；SHA `c13222bf…`，它是implementer evidence，不冒充review verdict。
- [Task 3A source review](reports/260907-task3a-source-review-gpt-high.md)独立重跑533／368与static／raw-DB probes，结论0 Critical／2 Important：snapshot extra candidate evaluation和event duplicate candidate evaluation仍可被接受；candidate进入fix round 1。
- [Task 3A source fix 1 report](reports/260907-task3a-source-fix-1-claude.md)记录commit `c59cdd66`对两项finding的subset／duplicate-key验证与direct raw-DB regressions；implementer报告store369、tokenization535、Ruff／Pyright通过。
- [Task 3A source re-review](reports/260907-task3a-source-rereview-gpt-high.md)关闭T3A-SR-01／02，结论Spec／quality均APPROVED、0 Critical／Important／Minor；reviewer独立跑535 tests、Ruff／Pyright并核无进程／DB残留。Reviewed source由`archive/260907-token-prediction-persistence`保留，stacked squash `16a09044`通过3,358 tests与90.33% coverage。
- [Task 4A implementation brief review](reports/260907-task4a-brief-review-claude.md)发现2 Blocker／6 Major／1 Minor：whole-request visual槽不能分解append suffix，prefix demotion state会随sample prune丢失；另需闭合all-candidate construction、suffix baseline／pairing、ProfileKey／latest windows、diagnostic controls与canonical durable order。Task 4A未启动source，先执行Task 3B prerequisite。
- [Task 4A prerequisite design](reports/260907-task4a-prerequisite-design-gpt-high.md)提出per-input-item contributions、global committed order、prune-stable per-ProfileKey checkpoint、capacity epoch rollover及Task 3B／4A／4B-P／4B分片；报告结论`DESIGN READY`。
- [Task 3B architecture review](reports/260907-task4a-prerequisite-design-review-grok.md)发现1 Blocker／3 Major／1 Minor：cross-identity capacity transaction未闭合、policy／store stamping混层、contribution非exact conservation、4B-P未进真实tracker、ProfileKey hash identity不完整。
- [Task 3B design amendment 1](reports/260907-task3b-design-amendment-1.md)改为current-identity-only rollover、old-epoch current sample／next-request new epoch、required logical command＋store stamp、fixed-context exact conservation、canonical ProfileKey JSON identity，并把4B-P加入task#27与SDD dependency graph。
- [Task 3B amendment 1 review](reports/260907-task3b-design-amendment-1-review-grok.md)关闭原AR-02～05，但保留1 Major／2 Minor：global cap下current identity原有0 rows时rollover无收益，drift command epoch未定，FixedContext codec与pair-index traversal不完整。
- [Task 3B design amendment 2](reports/260907-task3b-design-amendment-2.md)对零收益global cap采用typed checkpoint rejection而不rollover，drift强制NoChange；补store outcome、FixedContext三位置codec和committed-order sort。
- [Task 3B amendment 2 review](reports/260907-task3b-design-amendment-2-review-grok.md)关闭此前remaining Major／Minors，但发现required checkpoint outcome未覆盖duplicate／rejected／failed，且capacity transition有standalone／nested双权威这一项Major。
- [Task 3B design amendment 3](reports/260907-task3b-design-amendment-3.md)以required second-fact union区分policy NoChange、NotAttempted和NotCommitted，固定四种main outcome矩阵，并删除standalone capacity transition。
- [Task 3B amendment 3 re-review](reports/260907-task3b-design-amendment-3-review-grok.md)结论`APPROVED DESIGN`、0 Blocker／Major／1 wording Minor；该Minor已在current Spec按policy callable entry定义NotCommitted。Spec `8405215a…`／plan `030fa1bd…`完成writeback，等待fresh authority review。

## 点时调查与勘误

下列原件保持点时记录，不为适配本 Spec 而改写。综合结论必须连同证据边界阅读；勘误对原取证报告的 mutation 数字具有优先解释力。

- [260908-grok-responses-usage-observation.md](reports/260908-grok-responses-usage-observation.md)：当前 `ghc-api-proxy` 通过 `/v1/responses` 实测 `grok-4.6` 的终态 usage，确认提供 `cached_tokens` 而未提供 `cache_write_tokens`；Anthropic 兼容层的 `cache_creation_input_tokens: 0` 不代表上游写入为零。
- [260906-buffered-chat-local-tokenizer-analysis.md](history/260906-buffered-chat-local-tokenizer-analysis.md)：综合分析。高置信重建体的 local estimate 为 4,539,201，关联 upstream raw total input usage 为 921,248，约高估 4.927230 倍；这足以支持结构性修复，但不是该次 overflow 的已证根因。
- [260906-buffered-chat-completions-transcript-evidence.md](history/260906-buffered-chat-completions-transcript-evidence.md)：transcript、request log、rejected capture 和 deployed estimator 的点时取证。8,662,058-byte candidate 与上一笔成功请求的 outbound byte count 相等，但缺少原成功 body 或 hash，所以只是强烈推断，不能冒充 cryptographic identity。
- [260906-buffered-chat-completions-transcript-evidence-erratum.md](history/260906-buffered-chat-completions-transcript-evidence-erratum.md)：纠正 ciphertext-only mutation。清空 788 个 `encrypted_content` 后 estimate 为 823,520，较 4,539,201 减少 3,715,681；3,729,865 是删除全部 reasoning items 的减少量。
- [260906-local-tokenizer-code-audit.md](history/260906-local-tokenizer-code-audit.md)：production dataflow 审计，记录 8 个 major、4 个 minor，包括 eager local、media、thinking、opaque reasoning、context editing、provider-name、learning source、缺失 living Spec、tool identity、boolean count、dead alternate service 和 multiplier 合同缺口。

人控依据是 `docs/.human-controlled/api.md`、`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/ghc-api.md`、`docs/.human-controlled/message-translation.md` 与 `docs/.human-controlled/request-pipeline.md`。既有计数请求日志合同见 `.dev/docs/tui/spec.md`。

## 已建立的事实边界

- 已有证据足以行动：旧 Responses estimator 把 opaque reasoning ciphertext 当 ordinary text，是 reasoning-heavy 长请求数量级高估的主导机制；同一结构假设还会把 image／PDF base64 当文本，并会漏掉应按 model capability 保留的 Anthropic thinking。
- 已有证据不能支持：local count 导致了被调查会话的 overflow、失败请求的精确 upstream count、重建 candidate 与成功请求逐字相同、所有 Responses 请求都固定高估 4.927230 倍，或 output `reasoning_tokens` 可以充当以后输入的 label。
- `spec.md` 的验收节逐项声明 fake、synthetic、recorded forensic evidence 与 live upstream 各自能证明什么，且每个关键判据同时给出正确样本和单一目标缺陷注入。它们是验收表达，不是 CI gate、投票系统或 proof control plane。

## 被否路线

[spec.md §11“被否路线”](spec.md)是当前权威清单。除既有unavailable／ciphertext／global-multiplier／wrong-label／adjacency／raw-prompt／forensic-identity路线外，它还明确否决default special-token guard、`allowed_special`、endpoint fallback、Responses-only、one-spelling、one-position与旧failure expectation；每条都保留原因。
