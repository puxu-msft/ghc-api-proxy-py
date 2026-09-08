# Task 3B follow-up implementation report

## Source and authority

- Source worktree: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`
- Source HEAD: `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`
- No source commit was created, as instructed for this continuation.
- Re-read authority hashes: `spec.md` `5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48`; `plan.md` `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`; `status.md` `1a6fe0f2298543e448bc3981b39d5a50e088d58c1179401d4a50fb6d447771b3`; `HANDOVER.md` `5b79a13614a6d069a21445d5cf88a0f833bb9815ef6efef2ee6911124a2a697a`.

## Changed paths

- `src/app/tokenization/types.py`
- `src/app/tokenization/features.py`
- `src/app/tokenization/learning_schema.py`
- `src/app/tokenization/learning_store.py`
- `tests/unit/tokenization/test_features.py`
- `tests/unit/tokenization/test_learning_store.py`

`git diff --name-only` contained only these allowed paths and `git diff --check` passed. No `worker.py`, provider, routing, prediction, pipeline, Task 4A or Task 4B-P formula code was changed.

## Follow-up implementation

- Removed the pre-stamp sample codec call from the logical `apply_sample`/transition validation path. Logical samples may remain pending, whereas `_validate_sample_for_storage` requires a positive `committed_order`; `_stamp_update()` is now the pre-codec boundary.
- Strengthened logical command re-validation so a forged malformed `ReplacePrefixCheckpoint` is rejected by the pure transition before any persistent codec or row write.
- Rejected persistent/public pending evidence: persistent checkpoint and public snapshot carriers accept only positive-order `PrefixChampionErrorTriple`; active public snapshots also reject pending samples.
- Added globally unique committed-order validation for retained samples, permitting only the one post-transition order while an uncommitted transaction is being internally inspected.
- Added active checkpoint limits to `_StoreLimits`, all-state bounds validation, inactive-checkpoint cleanup, per-identity rollover and global zero-benefit rejection. Rollover deletes only the causal identity’s active checkpoint rows, creates the next empty epoch and leaves the current sample in its old epoch.
- Added durable codecs for `CapacityRejected` and `CapacityRolledOver`; committed observations now enforce the committed outcome family, while duplicate/rejected/failed observations enforce the appropriate not-attempted/not-committed families.
- Preserved checkpoint outcomes if the same transaction prunes the current sample. The sample-linked event becomes a pruned event while retaining the actual checkpoint `Applied` result.
- Added focused controls for malformed pending tails, no-early-codec/no-write invariants, zero-benefit global capacity rejection, current-identity rollover, drift plus `NoPrefixCheckpointChange`, same-transaction current-sample pruning and 788-item compact contribution/prefix pickle sizing.

## Verification

| Command | Result |
| --- | --- |
| `uv run pytest -q tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py --maxfail=1` | PASS, `432 passed in 86.68s` |
| `uv run pytest -q tests/unit/tokenization` | PASS, `549 passed in 141.41s` |
| `uv run pytest -q tests/unit/tokenization/test_learning_store.py::test_checkpoint_capacity_rolls_over_current_identity_and_rejects_zero_benefit_global tests/unit/tokenization/test_learning_store.py::test_malformed_pending_checkpoint_commands_reject_before_codec_or_rows` | PASS, `2 passed in 1.61s` |
| `uv run pytest -q tests/unit/tokenization/test_learning_store.py::test_current_sample_prune_keeps_applied_checkpoint_and_event_truth tests/unit/tokenization/test_learning_store.py::test_drift_requires_nochange_and_removes_old_epoch_checkpoints tests/unit/tokenization/test_learning_store.py::test_closed_reason_variants_round_trip_and_free_text_cannot_enter_db` | PASS, `3 passed in 1.89s` |
| `uv run pytest -q tests/unit/tokenization/test_features.py::test_compact_prefix_carriers_cover_788_items_with_pickle_safe_alignment` | PASS, `1 passed in 0.77s` |
| `uv run ruff check <six changed paths>` | PASS, `All checks passed!` |
| `uv run pyright <six changed paths>` | PASS, `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |

## Direct mutation evidence

### Pre-codec committed-order stamp

- Mutation: changed `_stamp_update()` from `replace(update.sample, committed_order=next_global_revision)` to `update.sample`.
- Target invariant: no pending sample may cross the persistent sample row boundary.
- Original failure: `test_store_stamps_pending_checkpoint_evidence_before_durable_codec` failed with `sqlite3.IntegrityError: NOT NULL constraint failed: samples.committed_order`; result `1 failed in 1.11s`.
- Restoration: restored the stamp expression; the selector passed with `1 passed in 1.00s`.

### Zero-benefit global-capacity rejection

- Mutation: changed `if over_global and prior_identity_count == 0:` to `if False and over_global and prior_identity_count == 0:`.
- Target invariant: a new identity with no pre-existing active checkpoint rows must not roll over merely to delete its own provisional row.
- Original failure: `test_checkpoint_capacity_rolls_over_current_identity_and_rejects_zero_benefit_global` failed because the outcome was `PrefixCheckpointCapacityRolledOver(...)`, not the required `PrefixCheckpointCapacityRejected`; result `1 failed in 1.10s`.
- Restoration: restored the condition; the same selector passed with `1 passed in 1.05s`.

## Remaining boundaries

The implemented slice now has direct controls for the requested carrier, pending-boundary, capacity, drift and current-prune behaviors. The following work is still not separately mutation-verified and must not be claimed as such:

- Every individual malformed-pending class has a shared no-codec/no-write control, but not an independently mutated source branch per class.
- The full policy-entry failure and post-COMMIT-cancellation outcome matrix is not exposed by a new dedicated Task 3B test matrix; existing confirmed-cancellation regression coverage remains in the store suite.
- A41 historical single-base availability and A45 formula controls remain outside this slice’s prediction implementation; no `prediction.py` was added. The implemented A41/A45 coverage is limited to committed-order and candidate/carrier persistence boundaries.
- The 788-item control proves compact in-memory JSON and pickle bounds, not a newly dedicated SQLite round-trip fixture for that exact 788-item payload.
