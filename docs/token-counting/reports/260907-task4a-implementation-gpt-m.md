# Task 4A implementation report

## Source status

`needs-review / uncommitted`。本报告不是 source review，未提交、未 push、未操作 4141，未修改 shared main 上除本报告外的内容。Source worktree 是 `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4a-prediction`，repo top-level 相同，branch 为 `integration/task4a-prediction`，initial/final HEAD、exact base 与 current main 都是 `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`，其 parent 是 `42fb23299bc9487d1751749668277ac4304861f8`。Task 3B reviewed-source archive 为 `archive/260907-token-learning-prerequisites → e2461a6ea17c968201bb1e0c2fb33be87be901e8`，它以 squash 而非祖先关系进入 main。

启动前再次读取 current `task-4a-brief.md`、Spec §4/5/6/7/12/13、Plan Task 4A、status 和 HANDOVER。volatile authority 已确认同一 slice/base/四条 allowed source paths：status 的 H6 为 `in_progress`，HANDOVER 的 H5 brief review 为 `READY`、H6 指向本 worktree。

## Authority hashes

| Artifact | SHA-256 |
|---|---|
| `spec.md` | `5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48` |
| `plan.md` | `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a` |
| `status.md` | `0db7407636431c1e641d462b06ebe46a0c45ae416d9803ec2816f755984eede7` |
| `HANDOVER.md` | `4c114e8b2161d5b035b2734902f871ce46d6e0b063dba6228bf07c86c8e47066` |
| `task-4a-brief.md` | `7fb755930f4427405137f058ca323d7135b2a8682a4fefa8dbe677209c86d76b` |

## Changed paths and implementation

仅有四条 allowed source paths 发生变化：

- `src/app/tokenization/prediction.py`（new）：public immutable carriers 上的 pure synchronous cold-start、exact median、strictly-shorter deterministic single-prefix、decision/intent、prequential record 与 evaluation。
- `src/app/tokenization/scaling.py`：新增唯一 `finalize_local_prediction()`，以 `Decimal(str(value)) * Decimal(str(multiplier)) → ROUND_CEILING → max(1, ...)` 完成量化；legacy wrapper 只 delegate。
- `tests/unit/tokenization/test_prediction.py`（new）：C01–C14 direct controls。
- `tests/unit/tokenization/test_local_estimate_scaling.py`：将 legacy wrapper 的零值期望从 `0` 更新为 `1`。

`prediction.py` 不导入/构造 `ReplacePrefixCheckpoint` 或 `DeleteRecoveredPrefixCheckpoint`，不访问 store/private state/SQLite/event/diagnostic row，不实现 profile、learned prefix pair、newest31、16/8、drift、queue、pipeline 或 persistence。`LearningUpdate` seam 的 direct test 显式构造 `NoPrefixCheckpointChange()`。

## Verification

所有命令在上述 physical cwd、Python `3.14.2` 下运行；imported module 为 `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4a-prediction/src/app/tokenization/prediction.py`。

| Command | Result |
|---|---|
| `uv run pytest tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py` | `38 passed in 1.09s` |
| restored C01–C14 selector nodes | `22 passed in 0.38s` |
| `uv run pytest tests/unit/tokenization/` | `574 passed in 144.29s (0:02:24)` |
| `uv run ruff check src/app/tokenization/prediction.py src/app/tokenization/scaling.py tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py` | `All checks passed!` |
| `uv run pyright src tests` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | exit `0` |

Final worktree status is exactly `M src/app/tokenization/scaling.py`、`M tests/unit/tokenization/test_local_estimate_scaling.py`、`?? src/app/tokenization/prediction.py`、`?? tests/unit/tokenization/test_prediction.py`。因此 tracked/untracked accounting 合起来仍严格等于四条 allowed paths。

## Direct mutation evidence

每项先只改变 `prediction.py` 或 `scaling.py` 的一个 branch/expression，再运行同一 direct node。下面保留当次 pytest stdout/stderr 的完整失败结论、assertion/exception 和 exit status；每项之后以对应正常 source 恢复，并由同一 node selector 的后续 restored-selector run green（22 items，exit 0）确认恢复。

### C01 fixed-one cold mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c01_cold_exact_aggregate_and_visual_presence`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c01_cold_exact_aggregate_and_visual_presence
AssertionError: assert 1 == 23.5
where 1 = TokenPrediction(... unscaled_tokens=1, sample_count=0, history_revision=7, learning_epoch=0, low_confidence_reasons=()).unscaled_tokens
1 failed in 0.51s
EXIT_STATUS=1
```

### C02 early-floor median mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c02_exact_median_and_all_source_intent`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c02_exact_median_and_all_source_intent
AssertionError: assert 100 == 100.5
where 100 = TokenPrediction(... candidate_key=PredictionCandidateKey(method=<PredictionMethod.HISTORY_EXACT: 'history-exact'>, variant=<PredictionCandidateVariant.MEDIAN: 'median'>), unscaled_tokens=100, sample_count=4, history_revision=7, learning_epoch=0, low_confidence_reasons=()).unscaled_tokens
1 failed in 0.38s
EXIT_STATUS=1
```

### C03 reversed candidate tuple mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c03_candidate_order_champions_and_cardinality`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c03_candidate_order_champions_and_cardinality
AssertionError: assert (PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>), ...) == (PredictionCandidateKey(method=<PredictionMethod.HISTORY_EXACT: 'history-exact'>, variant=<PredictionCandidateVariant.MEDIAN: 'median'>), ...)
At index 0 diff: PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>) != PredictionCandidateKey(method=<PredictionMethod.HISTORY_EXACT: 'history-exact'>, variant=<PredictionCandidateVariant.MEDIAN: 'median'>)
1 failed in 0.33s
EXIT_STATUS=1
```

### C04 exact-hit prefix short-circuit mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c04_exact_selection_keeps_prefix_challenger`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c04_exact_selection_keeps_prefix_challenger
AssertionError: assert (PredictionCandidateKey(method=<PredictionMethod.HISTORY_EXACT: 'history-exact'>, variant=<PredictionCandidateVariant.MEDIAN: 'median'>), PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>)) == (EXACT, PREFIX, COLD)
At index 1 diff: PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>) != PredictionCandidateKey(method=<PredictionMethod.HISTORY_PREFIX: 'history-prefix'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>)
Right contains one more item: PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>)
1 failed in 0.37s
EXIT_STATUS=1
```

### C05 tuple-first prefix-anchor mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c05_prefix_anchor_total_order_is_stable_across_snapshot_order`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c05_prefix_anchor_total_order_is_stable_across_snapshot_order
AssertionError: assert 23.0 == 127
where 23.0 = TokenPrediction(... unscaled_tokens=23.0, sample_count=1, history_revision=7, learning_epoch=0, low_confidence_reasons=()).unscaled_tokens
1 failed in 0.33s
EXIT_STATUS=1
```

### C06 non-strict `<=` prefix mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c06_strict_prefix_only_allows_a_real_append`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c06_strict_prefix_only_allows_a_real_append
AssertionError: assert PredictionCandidateKey(method=<PredictionMethod.HISTORY_PREFIX: 'history-prefix'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>) == PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>)
Differing attributes: ['method']
method: <PredictionMethod.HISTORY_PREFIX: 'history-prefix'> != <PredictionMethod.COLD_START: 'cold-start'>
1 failed in 0.37s
EXIT_STATUS=1
```

### C07 whole-request subtraction mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c07_suffix_uses_only_appended_item_slice`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c07_suffix_uses_only_appended_item_slice
AssertionError: assert 176 == 215
where 176 = TokenPrediction(... unscaled_tokens=176, sample_count=1, history_revision=7, learning_epoch=0, low_confidence_reasons=()).unscaled_tokens
1 failed in 0.39s
EXIT_STATUS=1
```

### C08 dropped appended visual mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c08_each_appended_item_visual_transition`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c08_each_appended_item_visual_transition[None-7-13]
AssertionError: assert 106 == (100 + 13)
where 106 = TokenPrediction(... unscaled_tokens=106, sample_count=1, history_revision=7, learning_epoch=0, low_confidence_reasons=()).unscaled_tokens
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c08_each_appended_item_visual_transition[0-7-13]
AssertionError: assert 106 == (100 + 13)
where 106 = TokenPrediction(... unscaled_tokens=106, sample_count=1, history_revision=7, learning_epoch=0, low_confidence_reasons=()).unscaled_tokens
2 failed, 2 passed in 0.35s
EXIT_STATUS=1
```

### C09 removed current-sample guard mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c09_prequential_record_rejects_current_sample_already_in_snapshot`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c09_prequential_record_rejects_current_sample_already_in_snapshot
Failed: DID NOT RAISE ValueError
1 failed in 0.39s
EXIT_STATUS=1
```

### C10 actual-zero relative-division mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c10_actual_zero_produces_absolute_error_only_in_candidate_order`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c10_actual_zero_produces_absolute_error_only_in_candidate_order
ZeroDivisionError: division by zero
src/app/tokenization/prediction.py:84: ZeroDivisionError
1 failed in 0.34s
EXIT_STATUS=1
```

### C11 binary-float product mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c11_finalization_decimal_multiply_then_ceiling`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c11_finalization_decimal_multiply_then_ceiling[1000000000000000000000000000001-1.1]
assert 1100000000000000100000000000000 == 1100000000000000000000000000000
where 1100000000000000100000000000000 = finalize_local_prediction(1000000000000000000000000000001, 1.1)
1 failed, 5 passed in 0.40s
EXIT_STATUS=1
```

### C12 old zero passthrough wrapper mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c12_wrapper_delegates_once_and_zero_is_now_one`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c12_wrapper_delegates_once_and_zero_is_now_one
AssertionError: assert 0 == 17
where 0 = <function scale_local_estimate at 0x71878e6f62a0>(0, 1.5)
where <function scale_local_estimate at 0x71878e6f62a0> = <module 'app.tokenization.scaling' from '/home/xp/.claude/jobs/4f9bdf9a/tmp/task4a-prediction/src/app/tokenization/scaling.py'>.scale_local_estimate
1 failed in 0.35s
EXIT_STATUS=1
```

### C13 reversed producer candidate tuple mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c13_producer_invariants_are_actual_output_facts`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c13_producer_invariants_are_actual_output_facts
AssertionError: assert (PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>), ...) == (EXACT, PREFIX, COLD)
At index 0 diff: PredictionCandidateKey(method=<PredictionMethod.COLD_START: 'cold-start'>, variant=<PredictionCandidateVariant.DETERMINISTIC: 'deterministic'>) != PredictionCandidateKey(method=<PredictionMethod.HISTORY_EXACT: 'history-exact'>, variant=<PredictionCandidateVariant.MEDIAN: 'median'>)
1 failed in 0.38s
EXIT_STATUS=1
```

### C14 forbidden checkpoint-transition import mutation

Command: `uv run pytest tests/unit/tokenization/test_prediction.py::test_t4a_c14_no_checkpoint_transition_or_forbidden_predictor_import`

```text
FAILED tests/unit/tokenization/test_prediction.py::test_t4a_c14_no_checkpoint_transition_or_forbidden_predictor_import
AssertionError: assert False
where False = <built-in method isdisjoint of set object at 0x7fb9b8d5a500>(({'AnchorKind', 'AnchorUseIntent', 'EstimateFeatures', 'ExactAnchor', 'LearningSnapshot', 'MethodChampion', ...} | {'AnchorKind', 'AnchorUseIntent', 'EstimateFeatures', 'ExactAnchor', 'LearningSnapshot', 'MethodChampion', ...}))
where <built-in method isdisjoint of set object at 0x7fb9b8d5a500> = {'DeleteRecoveredPrefixCheckpoint', 'ReplacePrefixCheckpoint'}.isdisjoint
1 failed in 0.32s
EXIT_STATUS=1
```

## Unverified boundaries and non-adopted routes

本 slice 的 pure/synthetic controls 不验证真实 provider billing、Task 8 descriptor resize/limit/media formula、Task 5 queue/store transaction/anchor-use persistence、Task 4B-P full-baseline/current-zero learned formulas、historical pair availability/index/newest31、Task 4B profile/promotion/16/8 checkpoint policy，或 Task 4C drift/epoch transition。没有运行 live upstream、4141、pipeline/driver/provider/routing wiring 或 full repository gate；这些均明确为 non-goal 或后续 gate。

未采用：whole-request `current - source` suffix subtraction、prefix actual median、exact-hit early return、records replay eligibility、learned additive/multiplicative or profile candidates、any early rounding/clamping、legacy wrapper zero passthrough、store/private SQLite reads，以及 Replace/Delete checkpoint command construction。
