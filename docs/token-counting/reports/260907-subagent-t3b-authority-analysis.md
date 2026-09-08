# Task 3B authority 修正技术分析

## 评审范围与结论

本分析只评估 Task 3B authority 修正，不修改 `spec.md`、`plan.md`、`status.md`、`HANDOVER.md` 或 source。读取范围包括当前 `spec.md`、`plan.md`、`status.md`、Task 3B authority review、design amendment 1～3及其限定复审、Task 3B prerequisite architecture review、Task 4A brief review、当前被标记为 `SUPERSEDED` 的 Task 4A brief，以及 SDD progress 中的 Task 4B-P 投影。

总体结论：**当前 Spec 的主要行为决策已经写入，但 Plan 的 owner 表述、pending evidence carrier、验收 mutation 面和状态投影仍需最小同步；Task 3B source 仍不得启动，直到这组 authority 修正完成并通过 fresh scoped re-review。**

当前五项发现的状态不是原 authority review 报告中的静态快照：`T3B-AUTH-01` 仍为 open；`T3B-AUTH-02` 的 sample order 规则已在 Spec 中存在，但 pending checkpoint evidence carrier 尚未闭合；`T3B-AUTH-03` 的 4B-P 行和旧 brief `SUPERSEDED` 标记已经出现，原 finding 的行为缺口基本关闭，但状态／tracker 仍把它记录为未复核的 handover 变更；`T3B-AUTH-04` 的 normative formula 已在 Spec 中正确写入，但验收控制仍不能判掉两个错误实现；`T3B-AUTH-05` 的行为已在 Spec 中写明，但 current sample 同事务被 prune 的独立 control 仍缺失。

## 权威来源与证据强度

- Behavior authority 是 `.dev/docs/token-counting/spec.md`；其 revision record 明确把 Task 3B 的 per-item conservation、committed order、checkpoint／capacity／outcome 矩阵和 Task 顺序记为本轮 derived decisions，见 `spec.md:698`。
- Implementation sequencing authority 是 `.dev/docs/token-counting/plan.md`；其 Task 3B interface 仍保留 policy 与 observation 的冲突表述，见 `plan.md:134`、`plan.md:143`、`plan.md:387`。
- 当前 Spec 已明确 store 产出 required checkpoint outcome second fact、policy callable entry 边界和 sample prune 不改写真实 outcome，见 `spec.md:372-376`、`spec.md:475-484`。
- 当前 Spec 已明确 pending sample 的 `committed_order` 在 policy 阶段为 `None`、由 store 在 codec 前 stamping，见 `spec.md:265`；但未把 checkpoint evidence 的 pending carrier 写成同等明确的 logical／persistent 分层。
- 当前 Spec 已明确完整 suffix baseline 和 current-zero multiplicative candidate，见 `spec.md:310-312`，但 A40～A45 的 mutation 文字没有把这两个区分写成必然判红的 fixture，见 `spec.md:647-652`。
- 当前 status 已列出 4B-P 并说明旧 Task 4A brief 已 `SUPERSEDED`，见 `status.md:17`、`status.md:119-121`；当前 brief 顶部也有不可错过的 `SUPERSEDED／不得派发` 标记，见 `.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md:1-3`。但 SDD progress 仍把这些 handover 变更标成未复核、归在 AUTH-03 下，见 `.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md:166`。
- Amendment 1 已解决 logical command／store stamping 的大部分设计问题，但其复审明确要求把 pending 与 persistent facts 分开，见 `reports/260907-task3b-design-amendment-1-review-grok.md:70-105`。
- Amendment 2 已决定 checkpoint outcome 是第二事实，并闭合 zero-benefit capacity reject 与 drift precedence，见 `reports/260907-task3b-design-amendment-2.md:1-186` 及其复审 `reports/260907-task3b-design-amendment-2-review-grok.md:29-76`。
- Amendment 3 已闭合 main outcome × checkpoint outcome 矩阵，并将 `NotCommitted` 的 boundary 改为 policy callable entry，见 `reports/260907-task3b-design-amendment-3.md:1-140`、`reports/260907-task3b-design-amendment-3-review-grok.md:29-108`。

## 逐条技术判定与最小改动清单

### T3B-AUTH-01：policy 与 store 同时拥有 final observation

**状态：OPEN，确认是 Plan authority 冲突；Spec 的 store ownership 已基本正确。**

证据闭合如下：Plan 在 `plan.md:134` 仍规定 `TokenLearningPolicy` 返回 `LearningUpdate` 与 `TokenLearningObservation`，而同一 Plan 在 `plan.md:143` 又把 `TokenLearningObservation` 描述为 background learner 完成后另产出的 durable observation。Task 3B interface 在 `plan.md:387` 只说 store 产生 required `PrefixCheckpointStoreOutcome`，没有明确 policy 不能返回 final observation。相反，Spec 已规定 policy entry 后返回 pending sample、logical command 和 optional drift，随后 store 在最终 state 形成 required checkpoint outcome 与 event，见 `spec.md:475-484`。

**最小、精确改动：**

1. 在 `plan.md:134` 将 `TokenLearningPolicy` 返回类型改为只返回 `LearningUpdate`；删除 `TokenLearningObservation`。
2. 在 Task 3B interface 附近补一条 owner invariant：`LearningUpdate` 只能携 pending sample、prequential record／evaluations、required logical checkpoint command 和 optional drift；不得携 final observation、checkpoint store outcome、post-transition revision、capacity transition 或 durable event。
3. 在 `plan.md:143` 保留 observation 由 orchestrator／store 在 confirmed transaction outcome 后构造，但明确它不是 policy return value，也不能由 store “覆盖” policy 已返回的 observation。
4. 在 Spec 的 `§7.3`／`§8.4` 对应 `spec.md:372-376`、`spec.md:475-484` 增加同一 owner 句，避免 Plan 与 Spec 再次分叉。
5. Task 3B 的 direct control 只需验证 policy output 的类型边界不包含 final observation／store outcome；不需要新建 proof framework。

**后续 source 影响：** source slice 启动时必须删除或改名现有 `LearningUpdate.observation`；若保留某个中间 carrier，名称和类型必须明确为 logical draft，不能被解码成 durable observation。这是实现后果，不是本轮要修改的文件。

**不采用方案及原因：**

- 不采用让 policy 先填 `NoChange` 或 placeholder，再由 store 静默覆盖，因为这保留两个事实 owner，并使 pre-store validation 的含义不唯一。
- 不采用让 store 事后修改 policy 返回的 `TokenLearningObservation`，因为 durable outcome 必须以 final state、capacity planning、prune 和 confirmed COMMIT 为依据。
- 不采用删除 `PrefixCheckpointStoreOutcome`，因为 amendment 2/3 已明确它是与 main sample outcome 分离的 required second fact。

### T3B-AUTH-02：current checkpoint evidence 在 policy 阶段没有合法 `committed_order`

**状态：部分关闭；Spec 已解决 sample order authority，但 logical evidence carrier 仍需补写。**

Spec 在 `spec.md:265` 已明确 pending sample 的 `committed_order` 为 `None`、store 在 codec 前以 post-transition global revision stamp，public／persistent state 不允许 `None`。Spec 在 `spec.md:316`、`spec.md:370` 又要求 checkpoint evidence 按 committed order 维护，但没有说明 `ReplacePrefixCheckpoint(..., evidence=...)` 在 policy 阶段如何携带当前 sample 的未 stamping evidence。原 authority review 的反例仍成立：policy 不能伪造未来 order，persistent checkpoint 也不能暂存 `None`。

**最小、精确改动：**

1. 在 Spec 的 logical command 定义附近（当前 `spec.md:370`）增加 `PendingPrefixChampionErrorTriple`，其 evidence 不携 committed order；它只允许作为 policy-return logical command 的 pending carrier。
2. 规定一次 command 至多有一个 pending evidence entry，且该 entry 必须是 evidence tuple 的唯一 tail；历史 entries 必须已经是 persistent positive-order facts。多于一个 pending、pending 非 tail、历史 entry 为 `None` 或 persistent row 含 `None` 均为 corruption。
3. 在 store transaction 顺序（`spec.md:475-484`）明确：store 计算 `next_global_revision` 后，把唯一 pending tail materialize 为 `committed_order == sample.committed_order == next_global_revision`，再执行 checkpoint codec／row preparation；不能提前 encode。
4. 在 `plan.md:387`、Task 3B checklist 的 stamping 条款附近补同一分层：policy 使用 pending logical evidence，store 只在 stamp 后构造 `PrefixChampionErrorTriple`。
5. 在 A42／A44 的现有 control 中增加 pending-tail、multiple-pending、non-tail-pending 和 early-encode mutation；这些是一个小的 DTO／store control，不是新的验证系统。

这里推荐新增 orderless pending carrier，而不是让 persistent `PrefixChampionErrorTriple.committed_order` 在 logical DTO 中 nullable。原因是它直接把“未提交逻辑事实”和“已提交持久事实”分成两个类型边界，避免 `None` 穿透 public／persistent snapshot；它不改变用户可观察的 learned-prefix 行为。

**不采用方案及原因：**

- 不采用 policy 猜测 `next_global_revision`，因为 revision 是 store-owned post-transition fact。
- 不采用 `0`、负数或 sentinel 伪装 pending order，因为 persistent order 的正数与 strict availability 是 normative contract。
- 不采用让 public checkpoint evidence 永久接受 `None`，因为这破坏 `spec.md:265` 和 checkpoint strict ordering。
- 不采用把当前 evidence 从 command 中丢掉、待下一次 sample 重建，因为会丢失当前 transaction 的 point-in-time checkpoint state。

### T3B-AUTH-03：status、tracker 与旧 Task 4A brief 的顺序投影

**状态：原 finding 的主要行为缺口已关闭；当前剩余的是状态 provenance 同步，不是新的 Spec behavior fork。**

原 authority review 认为 status 没有 4B-P、旧 brief 没有 `SUPERSEDED`。当前文件已经分别具备这些内容：`status.md:119-121` 列出 `4B-P` 并将 4B 依赖到 4B-P，`task-4A-brief.md:1-3` 已明确不得派发并指向 `3B → 4A → 4B-P → 4B`，Plan 也在 `plan.md:29`、`plan.md:422-433` 写入新顺序。因此不应重复实施原 review 中已经完成的“新增一行／加标记”。

**最小、精确改动：**

1. 不改 Spec behavior。保留当前 Plan、status、旧 brief 的顺序与 `SUPERSEDED` 标记。
2. fresh scoped re-review 时把 AUTH-03 记录为“已实施但待复核”，并核对 SDD progress 的 `progress.md:166` 是否改为已复核状态；不能继续把已存在的 4B-P 与 `SUPERSEDED` 说成缺失。
3. 在 status 的历史 review 表和 handover action list 中同步 provenance：明确这些 post-review handover edits 的实际状态是“已存在，待 authority re-review”，而不是“尚未执行”。
4. 不修改旧 brief 的正文来适配新设计；Task 3B reviewed source 完成后生成新的收窄 Task 4A brief，保持当前 `SUPERSEDED` 保护。

**不采用方案及原因：**

- 不采用恢复旧的 `Task 3B → Task 4A → Task 4B` 顺序，因为它会让 learned prefix variants 在 demotion／recovery 分母之后才出现。
- 不采用直接编辑旧 Task 4A brief 使其“看起来可用”，因为该 brief 已被 review 证伪，且其 owned-file 边界无法承载 Task 3B prerequisite。
- 不采用删除 4B-P 以减少 tracker 复杂度，因为它会回退已通过三轮 design amendment 的语义切片。

### T3B-AUTH-04：A40～A45 无法判否 known-only baseline 与 current-zero gate

**状态：OPEN，但属于 acceptance discrimination gap；Spec 的 normative behavior 已正确。**

Spec 的行为定义已经明确完整 `suffix_baseline_delta` 包含 item known、visual-or-zero 和 prior，并明确 current baseline 为 0 时只要有至少三条合法 historical ratio evidence，multiplicative candidate 仍存在，见 `spec.md:310-312`。Plan 也已写入同样的实现要求，见 `plan.md:431-433`。问题在于 A40～A45 当前文字只要求一般 suffix transitions、candidate tuple、newest31 和 diagnostics absence，见 `spec.md:647-652`；错误实现可以在现有 fixtures 下全绿。

**最小、精确改动：**

1. 扩展 `spec.md:652` 的 A45 正向 fixture：历史 pair 的 known delta 为 0、visual／prior delta 为正，actual delta 与完整 baseline 一致；断言 historical baseline、residual、ratio、candidate value 和 sample count。
2. 为同一 fixture 增加单变量 mutation：把 implementation 改成 known-only baseline，必须判红。
3. 在 A45 增加第二个正向 fixture：至少三条 positive historical ratio evidence，current suffix baseline 为 0；断言 multiplicative candidate 仍存在、`sample_count` 等于 evidence 数、suffix value 为 0 且最终 candidate 仍按 anchor actual 定义。
4. 增加第二个单变量 mutation：恢复 `current_baseline <= 0` 时删除 multiplicative candidate 的 gate，必须判红。
5. 在 `plan.md:431-436` 的 Task 4B-P checklist 明确列出上述两个 mutation，而不是只写 `zero baseline`；A40 继续负责 per-item exact conservation 和四种 visual transitions，不把 learned-baseline acceptance 混入 feature producer control。
6. 在 Spec revision record（当前 `spec.md:698`）追加本次“acceptance surface 补强”记录，并同步 `spec.md:665` 的 transcription map，使 `test_prediction.py` 的两个 mutation 成为现行转录要求。

**不采用方案及原因：**

- 不采用把 normative baseline 改回 known-only，因为这直接违反当前 Spec 的 full-baseline 行为和既有 design amendment 的已审结路线。
- 不采用恢复 current-zero gate，因为 Spec 明确 candidate availability 不由 current scalar 决定。
- 不采用只增加更多 positive fixture而不做 targeted mutation，因为两个错误实现仍可能保持绿色，无法满足一个绿的分辨力要求。
- 不采用把问题归为“未来 Task 4B-P 实现细节”而不改 Spec，因为 A45 是 Spec-owned acceptance surface，必须能判否其承重语义。

### T3B-AUTH-05：same-transaction current-sample prune control 缺失

**状态：OPEN，Minor；行为 authority 已明确，control 尚未闭环。**

Spec 已规定 sample 被同一事务 prune 时不改写真实 checkpoint outcome，见 `spec.md:372`、`spec.md:484`；A42 已覆盖 checkpoint 在 sample prune／restart 后存活，A44 已覆盖 main outcome × checkpoint outcome 矩阵，但 `spec.md:649-651` 没有要求“本次刚插入的 current sample 自己成为 victim”这一接缝。

**最小、精确改动：**

1. 在 `spec.md:651` 的 A44 中增加 current sample 因 sample cap 在同一 transaction 被选为 victim 的 fixture。
2. 该 fixture 必须断言：sample row 最终缺席；checkpoint replacement／delete 的 durable state 仍按真实 command outcome 保留；event 保存实际 `Applied`／`Deleted`／其它 committed result；identity/global revision 与 post-transition state 一致。
3. 对同一 fixture 增加两个定向 mutation：pruned 时跳过 checkpoint mutation；pruned 时把 outcome 改写成 `NoChange`。两者必须分别判红。
4. 在 `plan.md:394-397` 的 Task 3B test checklist 中补同一 current-sample-victim control；A42 保持负责跨事务 sample prune／restart survival，不用它替代本 control。
5. 在 Spec revision record `spec.md:698` 追加该 acceptance seam 的同步说明。

**不采用方案及原因：**

- 不采用改变行为以保留 current sample，因为 sample cap 的 victim 选择和 checkpoint 不绑 sample FK 已是现行合同；这里要验证 outcome truth，不是改变 retention policy。
- 不采用只测试旧 checkpoint source sample 在后续事务被 prune，因为那不能捕获“当前 transaction 同时写入又删除 sample”时的 state／event 接缝。
- 不采用用 `NoChange` 作为“sample 最终不存在”的替代文字，因为 Spec 明确 NoChange 只表示 policy 执行后选择 no-op。

## Spec authority 同步清单

以下是 authority 文件层面的最小同步，不包含 source 实现：

| 顺序 | 文件 | 最小同步 |
|---|---|---|
| 1 | `spec.md` | 明确 policy 不返回 final observation；新增 pending checkpoint evidence carrier 与 store stamping invariant；扩展 A45 的 full-baseline／current-zero controls；扩展 A44 的 current-sample-prune control；追加 revision record。 |
| 2 | `plan.md` | 删除 policy 返回 `TokenLearningObservation`；明确 `LearningUpdate` 的 logical-only payload 与 pending evidence；把 A45 两个 mutations 和 A44 current-prune control写入 Task 3B／4B-P checklist；保留已正确的 3B→4A→4B-P→4B→4C 顺序。 |
| 3 | `status.md`／SDD progress | 不重新添加已经存在的 4B-P 或 `SUPERSEDED` 标记；更新 handover／review provenance，说明它们已存在但等待 fresh authority re-review。 |
| 4 | 新鲜复审输入 | 以当前 Spec／Plan／status／brief 和上述 amendment 结论为输入重跑 scoped authority review；不要以原 authority review 的旧快照判定 AUTH-03 仍未实施。 |

## 用户 ruling 与 agent-derived correction

**仍需要 user ruling：无。**

本轮没有发现必须交回用户的行为分叉。原因是：policy/store ownership、pending order stamping、4B-P 顺序、full suffix baseline、current-zero candidate 和 sample-prune outcome 均已有当前 Spec 或已通过的 amendment 作为判据；待补的是 authority consistency、DTO carrier boundary 和 acceptance discrimination。它们属于 R4 delegated implementation scope 中的 agent-derived correction，不应被包装成用户新裁决。

唯一需要作出的实现选择是 pending evidence 采用独立的 orderless logical carrier，还是在 logical tuple 中允许一个明确的 pending tail。这里推荐独立 carrier；两者不改变用户可观察行为，且独立 carrier 更能保证 persistent/public DTO 永不接受 `None`，所以不构成需要用户裁决的产品 fork。若后续发现既有 public API 必须保持某个类名或序列化兼容，才另行形成 user ruling；当前 V1 尚未发布，不存在该约束。

## 搜索面与未覆盖面

已读取当前 Spec、Plan、status、Task 3B authority review、design amendment 1～3及各自复审、Task 3B prerequisite architecture review、Task 4A brief review、当前 superseded brief，并通过限定 `rg` 核对 line-number evidence、Task 4B-P tracker 和 Spec revision/transcription entries。

未运行 source tests、mutation tests、Ruff、Pyright、真实 upstream 或 SQLite probe；Task 3B source 尚未授权，且本任务只要求 authority 技术分析。未修改任何现有文件，只创建本报告。

## 最终 verdict

在完成上述最小同步并通过 fresh scoped re-review 前，Task 3B source authorization 仍为 **DENIED**。修正后的最小目标是：`LearningUpdate` 只有 logical pending facts，store 独占 final observation；当前 sample evidence 由 store stamp；4B-P 状态投影以当前文件为准并完成 provenance re-review；A45 能判掉 known-only／current-zero 两个 mutation；A44 能判掉 current-sample same-transaction prune 的两个 mutation。
