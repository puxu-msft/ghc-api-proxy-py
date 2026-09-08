# Task 4B-P implementation-brief 独立评审

## 评审范围

- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/task-4bp-brief.md`（SHA-256 `51d4071c4c20d647cf60ae87c826abd155e46faef9e1d8be9a6f8b609502cf92`）。
- 判据（读 brief 前）：Spec `5d9477dd…` §5／§6.0–6.2／§7.3／A20／A41／A45；Plan `bea5e753…` Task 4B-P；main `3badac7f6b020764cf8e30b2528ff51055dad0c2`（parent `6044919a`，含 Task 4A `prediction.py`）；archive `7d7e43b3`；旧 SUPERSEDED Task 4A brief 及其 2 Blocker／6 Major；Task 4A source／merged reviews。
- 只读：未改 brief／authority／source；未启动 4B-P source、4141、shared main。

## 总体 verdict

**READY。** blocker=0，major=0，minor=2。可以派 Task 4B-P source（隔离 worktree、base `3badac7f`、仅 `prediction.py`＋`test_prediction.py`）。Minor 不阻止 READY。

## Findings

### T4BP-F-01 — §1 把 A20 整表列为「重点实施」，未切开 4B-P 子集

- **severity:** minor
- **confidence:** high
- **阻塞派发:** 否
- **primary_location:** `task-4bp-brief.md` §1
- **related_locations:** Spec A20（含 16／8 demotion、profile variants）；brief §6 non-goals

A20 还要求 prefix 相对 profile／cold 的 16-sample demotion。§6 已排除 16／8 与 profile。§1 写「重点实施…A20／A41／A45」而未像 Task 4A brief 那样切开 cardinality／newest31／full-baseline。实施者若按表全做会越界。C07–C10 实际绑定的是 A20／A45 的 4B-P 子集，合同主体仍闭合。

**最小修法：** §1 写明 A20 只取 all-available prefix variants、champion／sample_count、exact 仍留 shorter prefix、newest31／min8／strict-better／tie；16／8 与 profile 仍属 Task 4B。

### T4BP-F-02 — C01「pending order」与 C07 部分 mutation 在 public DTO 上不可表示

- **severity:** minor
- **confidence:** high
- **阻塞派发:** 否
- **primary_location:** `task-4bp-brief.md` §7 T4BP-C01、T4BP-C07
- **related_locations:** `3badac7f` `LearningSnapshot` 拒绝 `committed_order is None`；`PredictionRecord` 要求 selected＝first eligible、champions 覆盖 represented methods

Public snapshot 不能携带 pending `None` order；C01 可执行的是 duplicate／equal order 与 reverse-tuple／future order。C07「只保留 prefix champion」「global selected 改成 prefix（exact 仍在）」会在 `types.py` 构造期失败，无法给出 tuple／intent diff。可执行 mutation 是 exact-hit early return、candidate 错序、sample_count。正向 C01／C07 断言仍成立。

## 七个承重面

1. **Scope** — §2／§5 限 pair index、single canonical base、additive／multiplicative、newest31、sample_count、all-available preservation。**成立。**
2. **Allowed paths／non-goals** — 仅两文件；排除 types／store／scaling／pipeline／4B profile／16／8／4C／Task 5／4141。A45 formula 明确本 slice 实施、不再 deferred。**成立。**
3. **Carriers vs `3badac7f`** — `StoredSample.committed_order`、per-item contributions、4A `_build_predictions`／deterministic prefix 均在；`prediction.py` 尚无 `PrefixPairIndex`（预期）。keyword-only `prefix_pair_index` 向后兼容。冲突时 stop、不改 carrier。**成立。**
4. **Availability／baseline／current-zero** — order 严格 `<`、same-time 合法、future／equal 非法；full slice baseline；None／0 在算术中 visual 0；current baseline 0 仍保留 multiplicative。C01／C04／C05／C06 对应 A41／A45。**成立。**
5. **Record＋actual／newest31／ties** — 不读 `evaluations`；共同窗口含当前全部 learned keys；min8、strict `<`、tie deterministic→additive→multiplicative。C08–C11。**成立。**
6. **C controls vs 旧错误** — 旧 4A BR-04 known-only／current-zero → C04／C06；BR-05 timestamp／all-bases → C01／C02；BR-08 newest31／diagnostics → C09／C10；whole-visual → C05。**足够。**
7. **Lineage** — Spec／Plan／status／HANDOVER hash 与磁盘一致；`3badac7f` parent `6044919a`；`7d7e43b3` 四 4A 文件与 main squash **byte-identical**；诚实写明 squash 非祖先。§11 未验证边界诚实。**成立。**

## 未采用建议

- 为 quadratic all-pairs 加 mutation：复杂度宜 source review 读结构，不易用单测稳定判红。
- 允许改 `types.py` 以测 pending snapshot：会冲 3B carrier；builder 对 duplicate order 的 `ValueError` 已够。

## 未验证边界

- 4B-P source 未启动；未跑 tests／Ruff／Pyright／mutations。
- Index 的 `O(n log n + prefix entries)` 无生产规模 benchmark（brief 已声明）。
- Task 5 按 identity＋revision 缓存 index 不在本 slice。

## 搜索面

读完 brief 全文；Spec §5／§6.2／A20／A41／A45；Plan Task 4B-P／4B；`3badac7f` prediction API 与 parent；`7d7e43b3` vs main 四文件 diff 空；sha256sum Spec／Plan／status／HANDOVER／brief。未改文件。

## Verdict

**READY。**
