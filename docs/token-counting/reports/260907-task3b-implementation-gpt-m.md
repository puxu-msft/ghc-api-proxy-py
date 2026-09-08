# Task 3B implementation report

## Source status

- Source worktree: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration`
- Source base HEAD: `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`
- Authority hashes re-read before implementation: `spec.md` `5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48`, `plan.md` `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`, `status.md` `1a6fe0f2298543e448bc3981b39d5a50e088d58c1179401d4a50fb6d447771b3`, `HANDOVER.md` `5b79a13614a6d069a21445d5cf88a0f833bb9815ef6efef2ee6911124a2a697a`.
- Source commit: none. The worktree remains uncommitted because the complete Task 3B authority is not implemented; creating the requested semantic source commit would falsely assert completion.
- Source status: `needs-fix`; only the six allowed paths are modified, and `git diff --check` passed.

## Changed paths

- `src/app/tokenization/types.py`
- `src/app/tokenization/features.py`
- `src/app/tokenization/learning_schema.py`
- `src/app/tokenization/learning_store.py`
- `tests/unit/tokenization/test_features.py`
- `tests/unit/tokenization/test_learning_store.py`

No `worker.py` or worker test was changed: the new frozen dataclass carriers cross the existing pickle boundary without worker-side adaptation.

## Implemented portion

- Added exact fixed-context and per-input-item contribution carriers with framing, visual-presence, prior-residual and exact aggregate validation.
- Kept `PrefixFingerprint` public item alignment while changing its durable codec to compact digest arrays.
- Added `StoredSample.committed_order`; transitions keep it pending, and the store stamps it with the post-transition global revision before durable sample encoding.
- Added logical checkpoint commands, pending tail evidence carrier, persistent checkpoint evidence, public checkpoint snapshots, checkpoint rows keyed by canonical `ProfileKey` JSON, hash lookup index, stamped checkpoint persistence, CAS checks and committed `Applied`/`Deleted`/`NoChange` outcomes.
- Added the three required confirmed actions (`state.prefix-checkpoints-read`, `prefix-checkpoint.upsert`, `prefix-checkpoint.delete`) and updated the independent 111-base/211-ID test literal.
- Added focused conservation and pending-stamping controls.

## Commands and results

| Command | Result |
| --- | --- |
| `uv run pytest -q tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py` | PASS, `427 passed in 91.18s` |
| `uv run pytest -q tests/unit/tokenization/test_features.py::test_item_contributions_exactly_reconstruct_known_and_visual_aggregates tests/unit/tokenization/test_learning_store.py::test_store_stamps_pending_checkpoint_evidence_before_durable_codec` | PASS, `2 passed in 1.85s` |
| `uv run ruff check src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py` | PASS, `All checks passed!` |
| `uv run pyright src/app/tokenization/types.py src/app/tokenization/features.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py` | PASS, `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |

## Mutation evidence

One controlled source mutation was run in the isolated worktree: `_stamp_update()` was changed from `replace(update.sample, committed_order=next_global_revision)` to `update.sample`.

- Target invariant: a pending logical sample must receive its positive committed order before the persistent sample codec/row boundary.
- Original failed output: `sqlite3.IntegrityError: NOT NULL constraint failed: samples.committed_order`, raised by `test_store_stamps_pending_checkpoint_evidence_before_durable_codec` at the sample insert. The test result was `1 failed in 1.11s`.
- Restoration: the original stamp expression was restored with `apply_patch`; the same selector passed: `1 passed in 1.00s`.

No other direct source mutations were run. In particular, no unrun mutation is marked verified.

## Unverified and incomplete authority

This is not a complete Task 3B source implementation. The following required authority remains absent and blocks a semantic commit or source review:

- Full `PrefixCheckpointStoreOutcome` matrix: `CapacityRejected`, `CapacityRolledOver`, `NotAttempted`, and `NotCommitted` are declared but not durably encoded, constructed or validated across every main outcome.
- Per-identity/global active checkpoint caps, inactive deterministic cleanup, zero-benefit rejection, current-identity rollover and drift precedence cleanup.
- Full checkpoint event-to-command/final-state relational validation and current-sample-pruned checkpoint truth.
- Required malformed pending matrix controls proving codec/row-write non-entry plus unchanged DB bytes, revision, event and checkpoint state for multiple pending, non-tail pending, historical missing order and persistent/public pending.
- A40 788-item pickle/SQLite byte-limit evidence, A41 same-time committed-order availability, the complete A42–A44 matrices and the independent A45 carrier graph controls.
- Formula-level A45 controls were deliberately not attempted because they belong to Task 4B-P `prediction.py`/`test_prediction.py`.

## Not adopted

- No prediction implementation, candidate formulas, eligibility 16/8 policy, history-prefix formula selection, drift policy, request prediction/routing, provider changes or Task 4A scope was added.
- No placeholder observation was returned by `LearningUpdate`; observations are store-built for successful sample transactions in the implemented path.
- No worker change was made merely to add proof infrastructure.
