# Task 3B source review fix 2 report

## Source status

- Source worktree: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`
- Source HEAD: `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`
- Commit: none, as instructed.
- Final source status: uncommitted Task 3B source candidate; `git diff --check` passed.

## Changed paths

- `src/app/tokenization/features.py`
- `src/app/tokenization/learning_schema.py`
- `src/app/tokenization/learning_store.py`
- `src/app/tokenization/types.py`
- `tests/unit/tokenization/test_features.py`
- `tests/unit/tokenization/test_learning_store.py`

The final `git diff --name-only` contains only these brief-allowed paths. No shared-main path, `worker.py`, prediction/pipeline/provider/routing code, or service port was touched.

## Fixed source-review findings

### T3B-SR-01: mixed media reason preservation

`_Analysis.capability_visual_tokens()` no longer removes `MEDIA_REASON` during a per-item calculation. It only removes that reason while calculating the whole media aggregate and only after the whole aggregate succeeds. A mixed image/PDF payload now preserves:

- image item visual contribution `6`;
- PDF item visual contribution `None`;
- whole visual aggregate `None`;
- `MEDIA_REASON` and `PDF_REASON`.

### T3B-SR-02: failed checkpoint-outcome matrix

`TokenLearningObservation.__post_init__()` now permits failed observations only with:

- `PrefixCheckpointNotCommitted()`, or
- `PrefixCheckpointNotAttempted(FAILURE_BEFORE_POLICY)`.

It rejects failed observations incorrectly paired with duplicate or sample-rejected not-attempted outcomes. A raw event-row corruption test also proves startup decoding cannot bypass this through event JSON.

### T3B-SR-03: typed pre-stamp codec rejection

`_encode_sample()` now raises `ValueError("sample codec requires a positive committed_order")` for a pending sample. Logical validation remains codec-free, while `_stamp_update()` stamps the sample before persistent preparation. The existing positive store-stamping test continues to pass.

## Regression and verification results

| Command | Result |
| --- | --- |
| Finding-specific selectors for mixed media, codec stamp, failed outcomes, and startup corruption | PASS, `4 passed in 1.69s` |
| `uv run pytest -q tests/unit/tokenization` | PASS, `552 passed in 144.01s` |
| `uv run ruff check src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py` | PASS, `All checks passed!` |
| `uv run pyright src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py` | PASS, `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |

## Mutation evidence

### T3B-SR-01

- Mutation: replaced `if media_items is None:` with `if True:` in `capability_visual_tokens()`, recreating the shared-reason mutation from successful per-item image calculation.
- Original failure: mixed-media regression failed at `assert MEDIA_REASON in features.low_confidence_reasons`; actual reasons were only `('zero-prior:pdf-without-capability-formula',)`. Result: `1 failed in 0.87s`.
- Restoration: restored the whole-aggregate guard; the finding-specific selector passed.

### T3B-SR-02

- Mutation: restored the broader failed branch accepting any `PrefixCheckpointNotAttempted`.
- Original failure: `test_failed_observation_rejects_duplicate_and_rejected_checkpoint_non_attempts` failed because the duplicate non-attempt case did not raise `ValueError`. Result: `1 failed in 0.82s`.
- Restoration: restored the exact `NotCommitted` or `FAILURE_BEFORE_POLICY` comparison; the finding-specific selectors passed.

### T3B-SR-03

- Mutation: removed the pending-order guard from `_encode_sample()`.
- Original failure: `test_store_stamps_pending_checkpoint_evidence_before_durable_codec` failed because the direct pending-codec call did not raise `ValueError`. Result: `1 failed in 0.67s`.
- Restoration: restored the codec guard; the positive stamping path and all finding-specific selectors passed.

## Unverified boundaries

No claim is made that the Task 3B-wide source-review gate has been independently re-run. The complete tokenization selector, focused finding controls, Ruff and Pyright are green, but any later review must still assess the complete Task 3B contract and all prior report boundaries rather than treating this fix report as an independent source review.
