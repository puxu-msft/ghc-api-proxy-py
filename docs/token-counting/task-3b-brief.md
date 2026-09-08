# Task 3B implementation brief

**状态：草稿·待独立review。** 本brief只授权在独立brief review通过后进入Task 3B source；它不授权Task 3B source本身，也不改变`HANDOVER.md`的H4 gate。

## Authority and base

Behavior authority是[spec.md](spec.md)，当前SHA-256为`5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48`。Implementation sequencing authority是[plan.md](plan.md)，当前SHA-256为`bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`。Volatile status projection是[status.md](status.md)，当前snapshot SHA-256为`1a6fe0f2298543e448bc3981b39d5a50e088d58c1179401d4a50fb6d447771b3`；source启动前必须重新计算并记录Spec、Plan、status和HANDOVER hashes。

Exact implementation base是`integration/token-learning-store` at `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`，它不是当前main `42fb23299bc9487d1751749668277ac4304861f8`的祖先。实现不得移动、stash、reset、clean或接管shared main；最终integration必须在source review后重新检查current main的path overlap并restack。

## Objective

实现Task 3B的per-item feature/state carriers、committed-order stamping、prefix checkpoint logical command与SQLite store mechanics，使Task 4A、4B-P和Task 4B可以在后续使用稳定的persistent contract。实现必须保持Spec中的single-transition authority、evaluate-before-learn、confirmed transaction ownership和block-level product boundary。

## In scope

允许修改的路径严格为：

- `src/app/tokenization/types.py`
- `src/app/tokenization/features.py`
- `src/app/tokenization/learning_schema.py`
- `src/app/tokenization/learning_store.py`
- `src/app/tokenization/worker.py`，仅当真实process pickle boundary需要
- `tests/unit/tokenization/test_features.py`
- `tests/unit/tokenization/test_learning_store.py`
- `tests/unit/tokenization/test_local_token_worker.py`，仅当worker发生修改

`EstimateFeatures`必须提供exact-conservation的fixed-context与per-input-item contributions，并从这些facts唯一重建whole known、prior和presence-aware visual aggregate；compact positional prefix digest必须与item count对齐，788-item motivating shape必须通过pickle／SQLite边界和size limit controls。

`StoredSample.committed_order`在policy logical boundary可以是pending，但public／persistent state不得保存pending order。`LearningUpdate`只携带logical facts和required checkpoint command；logical checkpoint最多携带一个唯一tail的orderless `PendingPrefixChampionErrorTriple`。Store在codec／row preparation前计算post-transition global revision，同时stamp当前sample与pending tail，再构造persistent positive-order evidence。

Prefix checkpoint必须以canonical ProfileKey JSON作为identity、hash只作lookup index，并与sample FK解耦。Store必须实现required `PrefixCheckpointStoreOutcome`、transaction-fresh expected-revision CAS、sample prune／restart survival、same-transaction current-sample prune truth、capacity reject／current-identity rollover、drift-plus-NoChange precedence和完整main-outcome矩阵。Capacity transition只能嵌套在`CapacityRolledOver`，不能新增standalone observation field。

V1 action ledger和transcription literal必须从Spec拥有的111 bases／211 IDs同步，新增`state.prefix-checkpoints-read`、`prefix-checkpoint.upsert`、`prefix-checkpoint.delete`，并保持三方独立性：test literal、production registry和runtime raw-call mapping不得互相生成expected set。

## Explicit non-goals

本slice不得实现或修改candidate formulas、history-prefix additive／multiplicative selection、16／8 eligibility policy、profile candidates、drift policy、request-side prediction、pipeline integration、provider routing或Task 4A predictor。不得把`TokenLearningObservation`、checkpoint outcome、post-transition revision、capacity transition或durable event作为policy return value或placeholder；这些facts由store在final state与confirmed COMMIT后唯一构造。

不得修改`docs/.human-controlled/`、当前main WIP、Task 3A archive、integration ref、旧Task 4A brief或4141 service。旧Task 4A brief仍是`SUPERSEDED／不得派发` artifact，不能通过编辑正文把它复活。

## Required controls

实现前必须把下列controls绑定到Spec A40～A45与对应transcription，不得只写positive fixture：

- A40覆盖fixed／item exact conservation、visual `None`／0／known transitions、compact codec arity／type／framing／finite／length和aggregate corruption。
- A41覆盖same-timestamp committed-order stamping、strictly earlier base availability、single canonical base和reverse snapshot stability。
- A42覆盖checkpoint独立sample FK、sample prune／restart survival、latest16／8 state、ProfileKey isolation、CAS和rollback。
- A43覆盖per-identity／global caps、zero-benefit typed reject、收益型current-identity rollover、drift NoChange和cache／revision／event semantics。
- A44覆盖每种main outcome与required checkpoint outcome，并让current sample在同一transaction成为sample-cap victim；sample row缺席不能改写checkpoint state或event outcome。`pruned->skip checkpoint`和`pruned->NoChange` mutations必须判红。
- A45在本slice只覆盖canonical candidate-key／champion／sample-count carrier shape、persistent graph references和independent decoder controls；不得在Task 3B实现candidate formulas。full suffix baseline与current-zero multiplicative的formula controls属于Task 4B-P的`prediction.py`／`test_prediction.py` source gate，必须在该brief中逐项保留，不能在本slice提前执行或删掉。

- Pending carrier专项control必须分别拒绝multiple pending、non-tail pending、历史entry缺positive order、persistent/public pending和stamp前early encode。每类至少有一个单变量mutation；拒绝必须发生在persistent codec／row write前，并断言DB bytes、revision、event和checkpoint state保持不变。唯一正向control按`policy entry -> next_global_revision -> sample/pending stamp -> persistent DTO/codec -> confirmed COMMIT`顺序验证同一positive order。

所有mutation必须记录目标不变量、失败原始输出和恢复后的green结果；尚未运行的mutation不得标记为verified。测试不得用production decoder生成independent expected，也不得用历史测试数量冒充当前source evidence。

## Delivery and review gate

实现者只在本brief独立review通过后创建source commit。source slice完成后运行changed-path focused tests、完整learning-store与tokenization selectors、Ruff、Pyright和上述direct mutations；不得把full integration green当作替代source review。

source review必须确认0 Critical／Important，并逐项检查allowed paths、non-goals、A40～A44 controls、A45 carrier subset、pending malformed rejection matrix、action-ID literal、confirmed transaction ownership和no-source-scope leakage。Formula-level A45 controls必须留给Task 4B-P，不得以Task 3B source green冒充已验证。Review evidence必须记录exact base parent、allowed-path diff、source commit/ref和review-report locator；source review通过后才可归档reviewed source、squash到stacked integration并更新status。Task 4A brief必须另行生成，旧brief不得修补复用。

## Rejected routes

不采用让persistent/public triple接受nullable `committed_order`，因为这会让policy pending fact穿透durable boundary；不采用policy预测next revision，因为revision是store-owned post-transition fact；不采用placeholder final observation再由store覆盖，因为这会保留双重事实owner；不采用在本slice实现16／8 policy或candidate formulas，因为它们属于后续Task 4B-P／4B authority和source。
