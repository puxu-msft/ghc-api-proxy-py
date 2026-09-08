# Task 4A implementation-brief 独立评审

## 评审范围

- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/task-4a-brief.md`（SHA-256 `7bb1f48bad6a5c0044eeb34e9bb3b4f0994206db61e5e13d74b5073451aa7261`，235 行）。
- 判据（读 brief **之前**取）：`spec.md` `5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48` §4.1–4.2、§6.0–6.4、§7.3、§11、A5／A8／A15／A20／A36；`plan.md` `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a` Task 4A／4B-P／4B／4C；已集成 main `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5` 的 3B carriers；archive `e2461a6e`；旧 SUPERSEDED brief `.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md` 及其 review `260907-task4a-brief-review-claude.md`（2 Blocker／6 Major）。
- 只读：未改 brief／Spec／Plan／status／HANDOVER／source；未启动 Task 4A source、4141、shared main。
- 本轮评的是 **dispatch 合同是否可执行且范围闭合**，不是 4A 实现验收。

## 总体 verdict

**NEEDS FIXES。** blocker=0，major=1，minor=3。不得在修 C13 之前派 source：该 control 按字面会逼实施者改 Task 3B `types.py`，与 §3 allowed paths／stop rule 冲突，且对 4A producer 没有分辨力。

Scope、non-goals、3B 消费面、旧 Blocker 的 per-item suffix／NoChange 收口、C01–C12／C14 的主路径，以及 hash／base lineage，均成立。

## Findings

### T4A-F-01 — C13 的注入／mutation 不能在 allowed paths 内执行，且测不到 4A

- **severity:** major
- **confidence:** high
- **阻塞派发:** 是
- **primary_location:** `task-4a-brief.md` §7 T4A-C13
- **related_locations:** `task-4a-brief.md` §3 stop rule；main `6044919a` `types.py` `MethodChampion.__post_init__`、`PredictionRecord.__post_init__`

**判据**

§3 禁止修改 `types.py`；发现 carrier 已表达合同或冲突时必须 stop，不得改 carrier。C13 要求用手工 DTO 注入 missing／extra champion、wrong-method、missing candidate、represented exact／cold `eligible_for_selection=false`，并「每次只放松对应 validator／producer invariant」作为单变量 mutation。

**事实**

`6044919a` 上这些对象在 DTO 构造期就已经拒绝：champions 必须恰好覆盖 represented methods；champion 必须指向同 method 的现存 candidate；exact／cold champion 不得 `eligible=false`。因此：

1. 「手工注入」在进入任何 4A 函数前就被 `types.py` 挡住；
2. 「放松 validator」的可红点在 `types.py`，不在 `prediction.py`；
3. `evaluate()` 按 brief 只算 error metrics，并不复检 champion 图。把 C13 当 4A mutation 会得到假绿，或诱导修改 3B carrier。

**最小修法**

把 C13 收成 **producer-output** control：断言 `build_prediction_record()` 产出的 record 满足 canonical keys／champion 覆盖／exact+cold eligible／selected=first eligible。Mutation 只改 `prediction.py`（漏 champion、错序、exact hit 后不建 prefix）。DTO 已拒绝的注入标明「由 Task 3A／3B carrier 拥有，4A 不重复 mutation」。

---

### T4A-F-02 — §1 把 A20／A36 整表列为「重点」，超出 4A 子集

- **severity:** minor
- **confidence:** high
- **阻塞派发:** 否
- **primary_location:** `task-4a-brief.md` §1
- **related_locations:** Spec A20（learned variants、16／8）、A36（Task 5 queue／`record_anchor_use`）；brief §6 non-goals

Non-goals 已明确排除 4B-P／4B／Task 5，但 §1 仍写「重点是…A20／A36」。实施者若按 Spec 表全做，会把 newest31、demotion、store 调用偷进本 slice。应在 §1 列出 4A 实际绑定的 A5／A8／A15 子集，并写明 A20 只取 exact／deterministic／cold cardinality 与「exact selected 仍保留 shorter prefix」；A36 只取 request-side `PredictionDecision`／intent／purity，不含 Task 5 owner chain。

---

### T4A-F-03 — cold-start 公式用 contribution prior，未点名 Spec §4.2 系数表

- **severity:** minor
- **confidence:** high
- **阻塞派发:** 否
- **primary_location:** `task-4a-brief.md` §5.2
- **related_locations:** Spec §4.2 `known + visual_or_zero + Σ(coefficient_v1 × feature)`；Plan Task 4A「whole known＋visual-or-zero＋whole prior」

v1 系数全 0、3B producer 的 `prior_residual_tokens` 也是 0，数值重合。brief 按 Plan 把 cold 写成 contributions 求和，没有写清：v1 不得再加一份 FeatureVector 系数残差，且 `missing-prior:*` 已由 features 携带。否则下一版非零系数会出现双计或漏计。补一句 v1 等价关系即可，不必改公式结果。

---

### T4A-F-04 — C14 绑的是 3B `LearningUpdate` DTO，不是 4A 输出

- **severity:** minor
- **confidence:** high
- **阻塞派发:** 否
- **primary_location:** `task-4a-brief.md` §7 T4A-C14；§4 最后一段
- **related_locations:** `types.py` `LearningUpdate.prefix_checkpoint_command`

4A 接口不返回 `LearningUpdate`。`None`／Replace／Delete 在 3B DTO 构造期就会失败。C14 mutation 改的是 test fixture，不是 `prediction.py`。保留「caller 必须显式 `NoPrefixCheckpointChange()`」作为文字合同即可；若要 mutation，应断言 4A 模块不 import／构造 Replace／Delete，而不是构造一个 store update。

## 六个承重面对照

1. **Scope** — §2／§5／§6 把 slice 收在 cold-start、exact、strictly-shorter single-anchor deterministic prefix、prequential record／evaluate、finalization。未把 learned pair／16／8／drift／pipeline 写成正向行为。**成立。**
2. **Allowed paths／non-goals** — 四路径与 Plan Task 4A 一致；禁止 types／features／store／pipeline／`.dev`／4141。Non-goals 点名 4B-P formulas、pair index、newest31、4B 16／8／profile、4C、Task 5，并点名旧 whole-visual 减法与 records 重放。**成立。** C13 是唯一会冲破 path 的 control。
3. **3B 消费接口 vs `6044919a`** — `EstimateFeatures.input_item_contributions`、`PrefixAnchor.sample_key`／`observed_at_us`、`ExactAnchor.actual_tokens`／`sample_keys`、`PredictionDecision`、`NoPrefixCheckpointChange`、`LearningSnapshot` 均存在；`prediction.py` 仍缺席。Prefix total order 字段能从 `sample_key`＋`observed_at_us` 取出。未发现必须改 carrier 才能做 deterministic 4A 的冲突。**成立（v1 cold 公式见 T4A-F-03）。**
4. **C01–C14 vs 旧 4A Blocker／Major** — 旧 BR-01 whole-visual：C07＋C08。BR-02 eligibility 重放：non-goal＋不读 checkpoint。BR-03 exact 跳 prefix：C04。BR-04／05／08 learned baseline、pair availability、newest31：显式留给 4B-P。BR-06／07 ProfileKey／latest8：留给 4B。BR-09 order／sample_count：C03。Prefix median：C05。**主矩阵足够。** 缺口只在 C13 不可执行。
5. **API／gates** — 三个 pure 函数＋`finalize_local_prediction` 与 Plan 一致；exact＋challenger、actual0、Decimal 终态、wrapper 0→1 均有 control。Source／merged 记录项可执行。`scale_local_estimate` 现为 `multiplier==1` shortcut＋integer-ratio，C11／C12 正确要求改掉。**成立。**
6. **Lineage** — Spec／Plan hash 与磁盘一致；base／parent `6044919a`／`42fb2329` 与 git 一致；诚实写明 3B 经 squash 而非祖先进入 main；旧 brief 仅作被否路线。启动时重算 hash 的条款诚实。**成立。**

## 未采用建议

- 增加「snapshot 含 demoted checkpoint 时 4A 仍选 prefix」mutation：4B 尚未写入 demoted rows，生产路径碰不到；§4 已禁止读 checkpoint。不升 finding。
- 把 A45 full-baseline／current-zero 提前进 4A：与 Plan／3B brief 的 4B-P 边界冲突，且 4A 无 learned variants。明确延后是对的。
- 允许 4A 改 `types.py` 以完成 C13：会重开 3B carrier ownership。应改 C13，而不是放宽 paths。

## 未验证边界

- 未跑 tokenization tests／Ruff／Pyright（brief 评审不执行 4A source）。
- 未把 `scale_local_estimate` 行为变化对 `driver.py` 现网 local count 的数值差做成表；那是 source／merged seam，不是 brief 范围错误。
- HANDOVER 正文仍有一处过期「shared main `42fb2329`」快照句；status 已写 `6044919a`。不记为 brief 缺陷。

## 搜索面

读完新 brief 全文；旧 SUPERSEDED brief 前 5 节＋旧 review 全部 findings；Spec §6.1–6.4 与 A5／A8／A15／A20／A36；Plan Task 4A／4B-P；`6044919a` 的 `types.py` PredictionRecord／Decision／anchors／snapshot／LearningUpdate、`scaling.py`；`git log` parent；sha256sum Spec／Plan／两份 brief。未读 4A source（不存在）。未改任何文件。

## Verdict

**NEEDS FIXES。** 先改 T4A-F-01（C13），minor 可同改或留 source 前 delta。0 Blocker；1 Major 期间 **READY 不成立**。
