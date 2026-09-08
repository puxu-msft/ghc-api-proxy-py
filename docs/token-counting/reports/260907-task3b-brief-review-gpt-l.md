# Task 3B implementation brief 独立评审

## 评审范围

本次只读评审对象是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/task-3b-brief.md`。判据来源为当前 `spec.md`、`plan.md`、`HANDOVER.md`、`status.md`、`reports/260907-subagent-authority-repair-review.md`、原 `reports/260907-task3b-authority-review-gpt-high.md` 及其 authority-repair 分析。评审重点是 Task 3B 是否严格停留在 carrier/store mechanics，allowed paths 是否闭合且不越界，A40～A45 是否能判否原 finding，policy/store owner、pending order、COMMIT 边界、base/ref/hash 和 source review gate 是否可执行。未读取或修改 source；未启动 source、测试、4141、provider 或 pipeline。

## 总体 verdict

**NEEDS FIXES**

- blocker：0
- major：2
- minor：1
- findings_total：3
- 总体 confidence：高

Brief 已正确写清 `LearningUpdate` 的 logical-only 方向、store 对 final observation／checkpoint outcome／revision 的唯一归属、pending tail 的基本 stamping 规则、current-sample same-transaction prune control，以及 `16/8` policy、candidate formulas、pipeline 和 provider routing 的明确 non-goal。因此不是整个 brief 失效；但当前仍有两个会直接阻止 source 派发的可实现性／验收缺口，另有一个会削弱 authority hash 可复核性的非阻断问题。

## Major findings

### T3B-BRIEF-01：A45 的 formula mutations 与 Task 3B non-goal、allowed paths 互相冲突

- severity：major
- confidence：高
- primary_location：`task-3b-brief.md:38,44-51`
- related_locations：`task-3b-brief.md:17-26,57-59`；`plan.md:397`；`plan.md:431-436`；`spec.md:A45`（当前约 `spec.md:665` 附近的 transcription map 与 `spec.md:652` 附近的判据）

Brief 一方面在 `:38` 明确禁止实现 candidate formulas、history-prefix additive／multiplicative selection、`16/8` policy、profile candidates 和 Task 4A predictor，且 allowed paths `:17-26` 没有 `src/app/tokenization/prediction.py` 或 `tests/unit/tokenization/test_prediction.py`；另一方面在 `:44-51` 又把 A45 的两个 predictor-level controls 作为本 slice 必须绑定并在 source gate 中验收的内容：full suffix baseline 对 known-only mutation 判红，以及 current baseline 为零时对恢复 current-zero gate 的 mutation 判红。`plan.md:431-436` 明确这两项属于 Task 4B-P 的 `prediction.py`／`test_prediction.py`；它们不是 `types.py`、`features.py`、`learning_schema.py` 或 `learning_store.py` 的 carrier/store mechanics。

这不是措辞上的重复：`known-only` mutation 必须改变 suffix baseline 的预测计算，`current-zero gate` mutation 必须改变 multiplicative candidate 的 availability。仅修改 Task 3B allowed paths 无法让这两个错误实现变红；若为满足 brief 去改 `prediction.py` 或新增 prediction tests，就越过 brief 自己声明的 non-goal 和后续 Task 4B-P owner。`task-3b-brief.md:51` 所说“Task 3B 只提供 carrier/store control”也没有消除冲突，因为它没有把 formula controls 明确拆成 deferred controls，反而仍要求 `A40～A45` 全部绑定到本 slice。

影响是 implementer 必须二选一：违反 scope 修改 candidate/predictor，或提交一个没有按 brief 完成 A45 的 source slice；source reviewer 也无法同时满足 `:38` 的 no-scope-leakage 和 `:59` 的 A40～A45 gate。该冲突会使 H3 brief review 通过后仍不能可靠派发 H4 source。

最小修正：

1. 将 Task 3B 的 A45 子面明确限定为 carrier/persistence invariants，例如 canonical candidate-key shape、sample-count carrier、record/evaluation persistence 和 independent decoder/graph controls。
2. 把 full-baseline-vs-known-only 与 current-zero multiplicative 两个 formula mutation 从 Task 3B 的 Required controls、source review gate 和 Task 3B allowed-path evidence 中移除，并明确转录到 Task 4B-P 的 `test_prediction.py`／source gate；保留当前 Spec/Plan 的 normative behavior，不回退行为定义。
3. 若坚持在 Task 3B 执行这两个 mutation，则必须显式扩大 allowed paths 和 scope 到 `prediction.py`，这与当前 HANDOVER 的 H3 boundary 不相容，不应作为默认修法。

### T3B-BRIEF-02：pending evidence 的 malformed-carrier rejection 没有落到 Required controls／source gate

- severity：major
- confidence：高
- primary_location：`task-3b-brief.md:30,44-53,57-59`
- related_locations：`spec.md:7.3`（当前约 `spec.md:475-484`）；`plan.md:387,392,395`；`HANDOVER.md:22-25,163`

Brief `:30` 已规定 logical checkpoint 最多一个唯一 tail、store 在 codec 前把 pending tail 与当前 sample 用同一 post-transition revision stamping；这是正确方向。但 brief 没有把 authority 已要求的失败边界完整转成 source controls：multiple pending、non-tail pending、历史 entry 缺 positive order、persistent/public pending，以及 stamp 前 early encode 必须被拒绝。`plan.md:387` 明确列出这五类 rejection，而 brief `:59` 只泛称检查 `persistent pending rejection`，`:44-51` 的 A40～A45 列表也没有 pending-tail mutation 或 malformed-carrier control。`HANDOVER.md:163` 只提醒 NoChange／NotAttempted／NotCommitted 不得合并，也不能替代这些 pending-order boundary controls。

因此一个实现可以完成 brief 明示的 positive path：有一个 orderless tail，store 正确 stamp 后落盘；同时对两个 pending、pending 不在 tail、历史 `None` 或提前 encode 采取静默截断、重排、接受后再修正等错误行为，而现有 brief 的 Required controls／review checklist 仍可能全绿。这样会重新打开原 `T3B-AUTH-02` 的核心风险：logical carrier 与 persistent positive-order evidence 的 boundary 不是“有规则”而是“规则可判否”。

最小修正：

1. 在 brief 的 Required controls 增加 pending carrier 专项控制，明确逐项拒绝 multiple pending、non-tail pending、历史 pending、persistent/public pending 和 early encode，并断言 DB bytes、revision、event 与 checkpoint state 在拒绝前不变。
2. 明确 `policy entry -> next_global_revision -> sample/pending stamp -> persistent DTO/codec` 的唯一顺序，并为每类 malformed input 至少列一个单变量 mutation；source review `:59` 必须逐项核对，而不是只检查“persistent pending rejection”。
3. 保持 `TokenLearningPolicy` 不返回 final observation、store 在 confirmed COMMIT 后拥有 durable facts 的现有 owner 结论；本 finding 只要求把 pending boundary 的 rejection evidence 补到 brief，不改变 API 行为。

## Minor findings

### T3B-BRIEF-03：status／handover snapshot 未在 brief 中以可复核的 status hash 固定，source gate 的 lineage evidence 不完整

- severity：minor
- confidence：高
- primary_location：`task-3b-brief.md:7,9,57-59`
- related_locations：`HANDOVER.md:5,33-37`；`status.md:5`；`reports/260907-subagent-authority-repair-review.md` 的 authority-hash 实测段落

Brief `:7` 只给出 `spec.md` 和 `plan.md` SHA-256，把 volatile status 退回“当前 snapshot 由 HANDOVER 记录”；`:9` 给出 exact implementation base 和 current main，但 `:57-59` 没有要求 source review 报告核对 source tree 的 exact parent/base、changed-path diff、source commit SHA 和 review artifact locator。`HANDOVER.md` 确实有更完整的 H0/H3/H4 gate 和 status hash，因此这不构成行为 owner 或 source authorization 的 Major；但 brief 单独作为 H3 产物时不能自足地证明使用的是同一 volatile projection。当前 `HANDOVER.md:5` 记录的 status hash 也应与实际 `status.md` hash 在派发前重新核对，不能把 handover 的旧 snapshot 当永久冻结开关。

最小修正：在 brief 的 Authority and base 中补当前 `status.md` SHA-256，或明确“source 启动前必须重新计算并记录 status/HANDOVER hash”；在 source review gate 中增加 exact base parent、allowed-path diff、source commit/ref 和 review-report locator 的硬性 evidence。该修正不会授权提前启动 source，只会让已有 H4 gate 可审计。

## 逐项对照原 Task 3B authority findings

- T3B-AUTH-01：基本关闭。Brief `:30`、`:38` 已把 `LearningUpdate` 限定为 logical facts，并明确 `TokenLearningObservation`、checkpoint outcome、post-transition revision、capacity transition 和 durable event 由 store 在 final state／confirmed COMMIT 后唯一构造；与当前 `spec.md:134`、`plan.md:387` 的 repaired owner 一致。
- T3B-AUTH-02：设计方向已写入，但本报告的 T3B-BRIEF-02 说明 malformed pending carrier 的 rejection／mutation surface 仍未落到 brief，不能把 positive stamping 规则误当作完整 source gate。
- T3B-AUTH-03：基本关闭。Brief `:40` 禁止复活旧 Task 4A brief，`:13` 和 `:59` 保持后续 Task 4A／4B-P 的独立 brief 与 source-review 顺序；Handover H3/H4 仍是实际授权 gate。
- T3B-AUTH-04：normative formula 与两个 mutation 已被 brief 转述，但由于 T3B-BRIEF-01 把它们错误地放入 Task 3B required scope，当前 brief 仍不能作为严格 scope-limited dispatch artifact。
- T3B-AUTH-05：已正确转录。Brief `:32`、`:50` 要求 current sample 在同一 transaction 成为 victim 时，checkpoint state 与 event outcome 不被 sample row 缺席改写，并要求 `pruned->skip checkpoint` 与 `pruned->NoChange` mutations 判红。

## 未采用建议与理由

- 未把 A42 的 `latest16／8 state` 单独判作引入 `16/8 policy`：当前 Spec/Plan 明确 Task 3B 负责 checkpoint carrier、mode、bounds、CAS、prune/restart persistence；被禁止的是后续 eligibility/demotion/recovery policy，brief 的 `:38` 已禁止 policy selection。
- 未把 A43 的 `drift NoChange precedence` 单独判作 drift-policy 越界：store 需要执行已定义的 typed command/outcome precedence，brief 没有要求在本 slice 产生 drift detector 或 drift candidate policy。
- 未把 brief 没有写出每个测试函数名判作缺陷：allowed paths、A40～A45 binding、mutation evidence 和 source-review checklist 已足以让 implementer选择测试名称；本报告只对会改变 scope 或使验收不可判否的缺口定级。
- 未把 `TokenLearningObservation` 在 brief 的 non-goal 中完全消失判作问题：当前 owner 需要被明确禁止，brief `:38` 的禁止性表述比只写“later store”更安全。
- 没有要求重跑任何 source/test/provider/prod gate；本次是 implementation brief 的只读 authority/scope review，且用户明确禁止启动 source、测试或 4141。

## 搜索面与限制

已通读当前 `spec.md`、`plan.md`、`HANDOVER.md`、`status.md`、authority-repair review、原 Task 3B authority review、authority-repair analysis 和目标 `task-3b-brief.md`；使用 `nl` 对目标 brief、Spec、Plan、Handover、status 建立了行号锚点，并核对了 Task 3B／4B-P 的 allowed paths、A40～A45、owner、pending carrier、action-ID、base/ref/hash 与 source gate。未读取 source 实现，未执行测试、mutation、Ruff、Pyright、真实 upstream、pipeline 或 4141，因此不对尚未实现的 Task 3B source quality 作结论。

## 结论

在拆出后续 Task 4B-P 的 formula controls、并补齐 pending-carrier malformed rejection controls 之前，Task 3B brief **NEEDS FIXES**，不可进入 H4 source。修正后仍需按 Handover H3/H4 重新核对 authority hashes、exact base、allowed-path diff 和独立 source review gate。
