# Task 4B-P commit preflight

## Verdict

**PASS.** All required source gates passed in the isolated source worktree, the committed range contains only the two allowed paths, and the authorized semantic commit was created. No push, squash, shared-main modification, carrier/authority modification, or 4141 operation occurred.

## Provenance and commit

- Physical worktree / repository top-level: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction`
- Branch: `integration/task4bp-prediction`
- Exact source base: `3badac7f6b020764cf8e30b2528ff51055dad0c2`
- Commit: `d10121c902daef7da090c4d6702d4b3eb6d28c80`
- Subject: `feat: learn token prefix residuals`
- Task 4A archive: `7d7e43b32c1d90e1723e6ad469262c5617e670a5`
- Task 3B archive: `e2461a6ea17c968201bb1e0c2fb33be87be901e8`
- Corrected brief: `17511ee519ed4ad40641b152c45088e536d6a75ee734d03ea79c69e1f495523c`
- Spec: `fdf63872b906dc87ec44eb4627c199552cc904d730add186600cc5095c639df9`
- Plan: `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`
- Status: `2e193ba190e40180fe8cc6f41fb08f426dc063b4bfb27766b93ffa95d02b950f`
- HANDOVER: `1ed46124b786ce60f1ccb2e7b74428ef19ec1c4e4b20eb8c8f4b9510c0c7c062`

The source worktree is clean after commit. `git diff --name-status 3badac7f..d10121c` and `git diff-tree -r d10121c` both report exactly:

```text
M  src/app/tokenization/prediction.py
M  tests/unit/tokenization/test_prediction.py
```

The range passes `git diff --check`; no conflict marker was found in either committed path.

## Gates

| Command | Result |
|---|---|
| `uv run pytest -q tests/unit/tokenization/test_prediction.py` | `36 passed in 0.57s` |
| `uv run pytest -q tests/unit/tokenization/` | `588 passed in 147.46s` |
| `uv run ruff check src/app/tokenization/prediction.py tests/unit/tokenization/test_prediction.py` | `All checks passed!` |
| `uv run pyright src tests` | `0 errors, 0 warnings, 0 informations` |
| pre-commit `git diff --name-only` exact two-path guard | passed |
| pre-commit `git diff --check` | passed |
| conflict-marker scan of the two source paths | passed |
| post-commit range exact two-path guard | passed |
| post-commit `git diff --check 3badac7f..HEAD` | passed |

## C01–C12 mutation evidence

The implementation follow-up report (`260907-task4bp-implementation-gpt-m-followup.md`) records direct one-target red/restore-green executions for all twelve brief controls. Before commit, this preflight rechecked that source scope and the final focused suite had not drifted and independently replayed representative high-risk mutations whose raw source-review evidence had not been independently produced:

| Control | Mutant and target | Raw red result | Restore result |
|---|---|---|---|
| C01 | Removed the committed-order sort; `test_t4bp_c01_committed_order_is_canonical_and_strict` | `AssertionError` at `assert reverse == forward`; exit `1` | `1 passed in 0.33s`; exit `0` |
| C02 | Changed canonical `min` to `max`; `test_t4bp_c02_selects_one_canonical_base` | `AssertionError`: selected `('z', 'short', 0)` rather than `('a', 'preferred', 2)`; exit `1` | `1 passed in 0.36s`; exit `0` |

The retained C03–C12 raw red/restore-green evidence remains applicable: after their restoration, no production source change occurred before this commit; only a test-only C02 fixture was strengthened to cover BINARY and numeric tie discriminators. The final 36-test focused gate proves the restored source and strengthened fixture are green. No mutant was staged or committed.

## Delivery state

The source is committed and ready for the prescribed next independent integration/merged-state process. This report does not substitute for that review or its gate.
