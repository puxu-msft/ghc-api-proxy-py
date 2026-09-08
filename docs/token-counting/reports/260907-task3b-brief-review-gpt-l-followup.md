# Task 3B implementation brief follow-up review

## 评审范围

本次是对上一轮 `T3B-BRIEF-01`～`T3B-BRIEF-03` 的 follow-up review。只读对象为当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/task-3b-brief.md`，判据来自当前 `spec.md`、`plan.md`、`HANDOVER.md`、`status.md`、上一轮报告和原 Task 3B authority review。未重新派发 agent，未读取或修改 source，未启动 source、test、4141、provider 或 pipeline。

## 总体 verdict

**READY**

- blocker：0
- major：0
- minor：1
- findings_total：1
- 总体 confidence：高

上一轮两个 Major 已得到实质修正：A45 formula controls 已从 Task 3B source gate 中拆出并归 Task 4B-P，pending carrier 的五类 malformed rejection 已逐项进入 Required controls 和 source review gate。上一轮 Minor 的复核字段也已补齐，但 brief 当前记录的 status SHA-256 已经落后于实际 `status.md`／当前 HANDOVER snapshot；这不阻止 H3 follow-up 通过，因为 brief 明确要求 source 启动前重新计算四份 hash，但必须在 H4 source preflight 前更新或重新记录。

## Previous findings follow-up

### T3B-BRIEF-01：A45 formula controls scope boundary

**状态：closed，confirmed，高置信。**

Brief `:51` 现在明确把 Task 3B 的 A45 限定为 canonical candidate-key／champion／sample-count carrier shape、persistent graph references 和 independent decoder controls，并明确“不得在 Task 3B 实现 candidate formulas”。同一行把 full suffix baseline 与 current-zero multiplicative formula controls 明确归入 Task 4B-P 的 `prediction.py`／`test_prediction.py` source gate。Delivery gate `:61` 又明确只检查 A45 carrier subset，并规定 formula-level A45 controls 留给 Task 4B-P，不能用 Task 3B source green 冒充验证。

这与 `:38` 的 candidate-formula、history-prefix additive／multiplicative selection、16／8 policy、profile candidates 和 Task 4A predictor non-goals一致，也与 `plan.md:431-436` 的 Task 4B-P ownership一致。当前 allowed paths `:17-26` 不含 prediction paths不再构成矛盾；没有发现为满足 A45 formula mutation 而越过 Task 3B scope 的隐含入口。

未采用扩大 Task 3B allowed paths 以提前运行 formula mutation 的建议，因为当前修订已经把该行为正确交给 Task 4B-P；扩大 scope 会重新违反既定 task slicing。

### T3B-BRIEF-02：pending carrier malformed rejection matrix

**状态：closed，confirmed，高置信。**

Brief `:53` 已逐项列出并要求拒绝 multiple pending、non-tail pending、历史 entry 缺 positive order、persistent/public pending 和 stamp 前 early encode。每类都要求至少一个单变量 mutation，并要求拒绝发生在 persistent codec／row write 前，同时断言 DB bytes、revision、event 和 checkpoint state 不变。相同条款还给出唯一正向顺序：`policy entry -> next_global_revision -> sample/pending stamp -> persistent DTO/codec -> confirmed COMMIT`。

Delivery gate `:61` 已把 `pending malformed rejection matrix`列为 source review 必查项；因此它不再只是 positive stamping prose，而是实现、mutation 和 review 三层均有明确落点。该边界与当前 `spec.md`／`plan.md` 的 pending carrier、store stamping 和 persistent positive-order contract一致。没有发现 multiple／non-tail／historical／persistent／early-encode 中任何一项仍只能靠实现者自行推断。

未采用把 pending carrier 改成 public/persistent nullable `committed_order` 的建议，因为修订继续保持 logical orderless carrier 与 store-owned positive-order materialization 的类型边界，符合 authority repair 的原始结论。

### T3B-BRIEF-03：status hash、base lineage 与 source review evidence

**状态：部分关闭；base/review evidence closed，status snapshot stale，保留一个 non-blocking Minor。**

Base 与 source-review evidence 已达到可复核要求。Brief `:7` 固定 Spec、Plan 和 status hash，并要求 source 启动前重新计算 Spec、Plan、status 和 HANDOVER hashes；`:9` 固定 exact implementation base ref、base commit 和 current main commit；`:61` 要求 source review evidence 记录 exact base parent、allowed-path diff、source commit/ref 和 review-report locator。结合 `HANDOVER.md:H3/H4` 的 source commit、independent review 和 gate outputs，这些字段足以让 reviewer 在 source 阶段核对 lineage、scope diff 和 review artifact，而不需要依赖 implementer 自述。

但当前 brief `:7` 记录的 status SHA-256 为 `575ee4fa344f6e0036dc6e9d1ab281f0491fe6f14d655fde4bff7322876eaeff`，本次只读复算当前 `status.md` 得到的是 `81e510377f5bbf56af491641ac463207b5a9cc3691d9a5a18e866e11b9a1370d`；当前 `HANDOVER.md:5` 也记录 `81e510...`。因此“当前 snapshot SHA-256”这一字段在 brief 中已经过时，不能直接作为当前状态的 hash evidence。

- severity：minor
- confidence：高
- primary_location：`task-3b-brief.md:7`
- related_locations：`HANDOVER.md:5`；当前 `status.md` 文件本身
- impact：不会改变 Spec／Plan behavior authority，也不会提前解除 H4，因为 `:3` 和 `HANDOVER.md:36-37` 仍明确 brief review 前及 H3 前 source blocked；但若不刷新，接手者会把旧 volatile projection 当作当前 snapshot。
- minimum_fix：在 H4 source preflight 按 `:7` 重新计算并记录四份 hash；若保留本 brief 的 current snapshot字段，则同步更新 status hash为当前值，或改写为明确的 point-in-time snapshot并同时记录 snapshot date／source。

未把 exact base parent“当前值未直接写在 brief正文”判为额外 finding：` :61` 已把它列为 source review 的强制 evidence，`HANDOVER.md:36-37` 已拥有 H3/H4 dispatch gate，source review 可以从 `16a09044...` 的 parent 直接复核。未把 review-report locator 没有预先指定文件名判为 finding：它已是 source review output 的必填 locator，过早固定未来 report 文件名反而会制造虚假当前事实。

## 当前 scope／owner／gate 总结

- Scope严格限于 per-item feature/state carriers、committed-order stamping、prefix checkpoint logical carrier、SQLite store mechanics、111／211 action ledger和A40～A44及A45 carrier subset。没有把 16／8 eligibility policy、candidate formulas、pipeline、provider routing 或 request-side prediction重新引入 Task 3B。
- `LearningUpdate`仍是 logical-only，final `TokenLearningObservation`、checkpoint outcome、post-transition revision、capacity transition 和 durable event仍由 store 在 final state／confirmed COMMIT后唯一构造。
- Pending order边界同时覆盖正向顺序和五类 malformed rejection，且 source review gate要求逐项检查。
- A45 formula controls已明确 deferred 到 Task 4B-P，Task 3B source green不能冒充其验证。
- Base/ref/hash和source review evidence字段足以执行后续 gate，唯一当前不一致是 brief 内 status hash已过时；它由 source preflight refresh约束为非阻断问题。

## 未采用建议与理由

- 未建议再次修改 Spec／Plan 的 A45 normative behavior，因为当前问题只在 dispatch scope，现行 Spec／Plan 已正确把 formula controls归Task 4B-P。
- 未建议把 A45 formula controls从整体 transcription map 删除，因为它们仍是后续 Task 4B-P 的必要验收面；修复是 deferred ownership，不是 scope deletion。
- 未建议把 pending malformed rejection扩展成新的验证框架；当前逐项 mutation、bytes/revision/event/state不变断言和 source review checklist已经是现有测试／review机制可承载的最小控制。
- 未建议把 status hash差异升级为 Major或阻止H3：brief和H4 gate都明确要求 source 启动前重新计算 hash，且当前 status 只承担 volatile projection，不是 behavior authority。

## 搜索面与限制

已通读修订后的 `task-3b-brief.md`、上一轮报告、当前 `spec.md` 的 lifecycle／pending carrier／A40～A45条款、`plan.md` 的 Task 3B／Task 4B-P 接口与测试清单、`HANDOVER.md` 的 H3/H4 gate 和当前 `status.md` header，并用 `nl` 固定 brief 行号、用 `sha256sum`复算 authority hashes。未读取 source，未执行任何测试、mutation、Ruff、Pyright、provider、pipeline 或 4141 操作。

## 结论

**READY**。T3B-BRIEF-01 和 T3B-BRIEF-02 已关闭；T3B-BRIEF-03 的 base/review evidence 已关闭，仅保留 status hash stale 的 non-blocking Minor。H4 source 仍须在启动前按 brief 要求刷新并记录 Spec、Plan、status、HANDOVER hashes；除此之外，本 brief 已具备进入 Task 3B source review gate 的 scope 和验收条件。
