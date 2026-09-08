# Task 4B-P source implementation follow-up

## Source status

**NEEDS INDEPENDENT SOURCE REVIEW.** The Task 4B-P authority correction follow-up is READY and T4BP-AC-01 is closed. The candidate remains deliberately **uncommitted** in `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction` on `integration/task4bp-prediction`; it was not pushed, source-reviewed, merged, or applied to shared main.

Only the two permitted source paths are modified:

- `src/app/tokenization/prediction.py`
- `tests/unit/tokenization/test_prediction.py`

`git diff --check` passed, and the exact allowed-path guard passed. No carrier, authority, shared-main, pipeline, store, worker, checkpoint, provider, routing, configuration, dependency, lockfile, or 4141 path was changed.

## Authority and startup provenance

- Physical worktree and repository top-level: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction`
- Branch: `integration/task4bp-prediction`
- Initial and final source HEAD / exact base / current main: `3badac7f6b020764cf8e30b2528ff51055dad0c2`
- Base parent: `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`
- Task 4A archive: `7d7e43b32c1d90e1723e6ad469262c5617e670a5`
- Task 3B archive: `e2461a6ea17c968201bb1e0c2fb33be87be901e8`
- Corrected brief: `17511ee519ed4ad40641b152c45088e536d6a75ee734d03ea79c69e1f495523c`
- Spec: `fdf63872b906dc87ec44eb4627c199552cc904d730add186600cc5095c639df9`
- Plan: `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`
- Current status: `2e193ba190e40180fe8cc6f41fb08f426dc063b4bfb27766b93ffa95d02b950f`
- Current HANDOVER: `1ed46124b786ce60f1ccb2e7b74428ef19ec1c4e4b20eb8c8f4b9510c0c7c062`

The supplied prior status hash (`4a03b23c…`) changed before this continuation. Per the corrected brief’s status/HANDOVER rule, I read both current documents instead of treating the old pin as a hard stop: both explicitly retain the same Task 4B-P slice, exact base `3badac7f`, isolated source worktree, and the two allowed paths. HANDOVER also pins the current corrected brief and therefore naturally changed. Spec and Plan match their corrected brief pins.

Runtime evidence: CPython `3.14.2`; imported candidate module `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction/src/app/tokenization/prediction.py`.

## Implemented behavior

- Added immutable, revision/identity/epoch-bound `PrefixPairIndex` and synchronous pure `build_prefix_pair_index()`.
- Validated positive unique `committed_order`, sorted the input by committed order and canonical sample-key total order, and built pairs in one forward traversal with only strictly earlier bases.
- Selected exactly one historical canonical base by coverage, observation time, UTF-8 BINARY sample-key fields, and numeric attempt index. Historical longer evidence is filtered to the current exact `ProfileKey`; a base may use another profile.
- Computed historical and current suffix baselines from per-item `known_tokens + visual-or-zero + prior_residual_tokens`, without whole-request subtraction or fixed-context reuse.
- Added independent additive and multiplicative evidence/counts, thresholded at three, including the current-zero multiplicative case.
- Preserved exact, deterministic prefix, learned additive, learned multiplicative, and cold candidates in canonical order. Exact selection does not suppress prefix challengers; learned-prefix request selection retains the deterministic anchor’s single-source intent.
- Chose the prefix champion exclusively from retained point-in-time records plus linked actuals: all current prefix variants must co-occur, actual must be positive, window is canonical newest 31, minimum is eight, learned variants require strictly lower median APE, and ties are deterministic → additive → multiplicative. No diagnostic evaluation row is read.
- Kept Task 4A cold/exact/deterministic/evaluation/finalization semantics and made no Task 4B checkpoint/profile or Task 4C/Task 5 change.

## Positive controls

The focused test file now contains direct controls for T4BP-C01 through C12:

- committed-order reverse input, future base exclusion, duplicate/equal-order rejection;
- a single canonical base with coverage, observed-time, UTF-8 BINARY, and numeric-attempt discriminators;
- profile isolation, cross-profile base validity, identity/epoch/revision-bound index rejection, and record/sample profile mismatch rejection;
- corrected C04 valid positive known plus positive visual/prior baseline evidence;
- all four historical visual `None`/`0` transitions;
- two/three threshold, unequal additive/multiplicative evidence counts, and current-zero multiplicative preservation;
- exact-selected all-variant preservation, canonical candidates/champions/counts;
- minimum-eight, strict-improvement, and tie semantics;
- 63-record older/newest-31 reversal plus reversed snapshot input;
- empty diagnostics;
- all-current-variant common-record window; and
- existing prequential/current-sample, actual-zero, and NoPrefixCheckpointChange regressions.

## Direct mutation evidence

Each mutation was made only in `prediction.py`, run against its target node, then manually restored before the recorded same-node green check. The table preserves the exact command, nonzero exit result, and target assertion/exception surface; raw terminal stdout/stderr was captured by the session command executions. All target-red commands exited `1`, while each restoration command exited `0`.

| Control | One-variable mutant and target command | Raw red surface | Restore green |
|---|---|---|---|
| C01 | Remove committed-order sort; `uv run pytest -q tests/unit/tokenization/test_prediction.py::test_t4bp_c01_committed_order_is_canonical_and_strict` | `AssertionError: PrefixPairIndex(... pairs=()) != ... pairs=(...)` at `assert reverse == forward` | `1 passed in 0.33s` |
| C02 | Change canonical `min` to `max`; same C02 node | `AssertionError: ('z', 'short', 0) != ('a', 'preferred', 10)` at selected-base assertion | `1 passed in 0.33s`; final expanded C02 is covered by focused green |
| C03 | Remove exact `ProfileKey` filter; C03 node | `AssertionError: (1, 4, 4, 0) ==/!= (1, 3, 3, 0)` | `1 passed in 0.35s` |
| C04 | Replace historical full baseline with known-only; C04 node | `AssertionError: 115 != 110` for additive candidate | `1 passed in 0.35s` |
| C05 | Make appended visual `None` contribute one; C05 parametrized node | Two literal failures: `suffix_baseline_delta=7`, expected `6` | `4 passed in 0.32s` |
| C06 | Restore forbidden `current_suffix_baseline_delta > 0` gate; C06 node | `KeyError` for required multiplicative candidate key | `1 passed in 0.29s` |
| C07 | Raise multiplicative evidence threshold from 3 to 4; C07 node | Canonical candidate tuple lacked `history-prefix/multiplicative` | `1 passed in 0.34s` |
| C08 | Change minimum common window from 8 to 7; C08 node | `AssertionError: history-prefix/additive != history-prefix/deterministic` | `1 passed in 0.32s` |
| C09 | Remove `[:31]` newest slice; C09 node | `AssertionError: history-prefix/additive != history-prefix/deterministic` | `1 passed in 0.31s` |
| C10 | Make empty diagnostics force deterministic; C10 node | `AssertionError: history-prefix/deterministic != history-prefix/additive` | `1 passed in 0.37s` |
| C11 | Exclude current multiplicative key from common-set requirement; C11 node | `AssertionError: history-prefix/additive != history-prefix/deterministic` | `1 passed in 0.32s` |
| C12 | Remove current-sample prequential guard; existing C12/T4A prequential node | `Failed: DID NOT RAISE ValueError` | `1 passed in 0.29s` |

No mutant was committed. The final focused suite and final diff check ran after all restores.

## Verification

| Command | Result |
|---|---|
| `uv run pytest -q tests/unit/tokenization/test_prediction.py` | `36 passed in 0.45s` |
| `uv run pytest -q tests/unit/tokenization/` | `588 passed in 148.43s` |
| `uv run ruff check src/app/tokenization/prediction.py tests/unit/tokenization/test_prediction.py` | `All checks passed!` |
| `uv run pyright src tests` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | passed |
| exact two-path diff guard | passed |

## Unverified boundaries

- Independent source review, merged-state review, and their gate remain unperformed and are required before integration.
- No production pipeline/store orchestration, provider, real upstream, or 4141 behavior was exercised; all are explicit non-goals.
- Task 4B profile candidates/MAD/promotion/16/8 checkpoint policy, Task 4C drift, and Task 5 caching/queue/anchor-use persistence remain unimplemented by design.

## Rejected routes

- Did not revive the prior zero-known append fixture: corrected C04 uses valid positive known plus positive visual/prior terms.
- Did not aggregate all bases, infer availability from timestamps, use whole-request baseline deltas, use known-only learning, gate multiplicative availability on current baseline, reselect historical variants, read diagnostics, retain only champions, or use unbounded/oldest records.
- Did not modify Task 3B DTO validators to make malformed fixtures representable, and did not modify Task 4A semantics to absorb learned behavior.
