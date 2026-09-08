# Task 4B-P source implementation report

## Verdict

**BLOCKED — source delivery is not authorized.** The current Task 4B-P brief requires T4BP-C04 to construct at least three valid historical pairs whose strict appended suffix has a known-token delta of zero and positive visual/prior delta. The Task 3B carrier makes that fixture impossible without changing or invalidly bypassing the carrier, which this slice is forbidden to do.

## Startup provenance

- Physical worktree: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction`
- Repository top-level: `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-prediction`
- Branch: `integration/task4bp-prediction`
- Initial HEAD / exact base / current main: `3badac7f6b020764cf8e30b2528ff51055dad0c2`
- Task 4A archive: `7d7e43b32c1d90e1723e6ad469262c5617e670a5`
- Task 3B archive: `e2461a6ea17c968201bb1e0c2fb33be87be901e8`
- `task-4bp-brief.md`: `1177435d16d5b67f8e57eefff80d0293f834277bab8e08afdedf821fd7d71c73`
- `spec.md`: `5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48`
- `plan.md`: `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`
- `status.md`: `f482da1b200f19ade61d408139b964640f9b617a354c9000489ffab9856a473b`
- `HANDOVER.md`: `4c8238df86b9fa08b2b544a589d89389efbc809b093983a888f5e78cc35cdf50`

The authority hashes equal the Task 4B-P brief’s launch hashes. Task 4A main source is byte-identical to its archive for both prediction-owned files, and the Task 3B archive is present. No authority, carrier, shared-main, provider, 4141, or forbidden path was changed.

## Blocking contradiction

The current requirements are mutually incompatible:

1. Task 4B-P brief §7, **T4BP-C04**, requires: “至少3个pair都让historical known delta为0、visual／prior delta为正”.
2. Spec §6.2 defines the suffix baseline as the sum of every appended item’s `item.known_tokens + visual_or_zero + prior`.
3. The immutable Task 3B carrier `InputItemContribution` defines `known_tokens` as `visible_tokens + item_framing_tokens + nested_framing_tokens`.
4. Its constructor requires `item_framing_tokens == 4`, and both visible and nested values are nonnegative (`src/app/tokenization/types.py`, `InputItemContribution.__post_init__`).

Consequently every appended item has `known_tokens >= 4`. A strict longer sample has at least one appended item, so its historical known-token delta is at least four; it cannot be zero. Constructing the requested fixture would require an invalid DTO or a change to the Task 3B carrier/authority, both prohibited by this slice’s stop rule.

This is not the intended full-baseline-versus-known-only distinction: that distinction remains expressible with nonzero known contribution plus positive visual/prior contribution. The literal C04 requirement, however, cannot be satisfied as written by a valid carrier fixture. The minimal resolution is an authority/brief correction replacing “known delta为0” with a valid discriminating condition, for example an explicitly hand-computed nonzero known baseline plus positive visual/prior terms whose omission changes residual, ratio, candidate values, and counts.

## Source status and changed paths

Before finding the contradiction, a partial, uncommitted implementation was begun only in the two permitted source paths:

- `src/app/tokenization/prediction.py`
- `tests/unit/tokenization/test_prediction.py`

The partial code adds an immutable `PrefixPairIndex`, committed-order validation/sort, canonical base lookup, full suffix arithmetic, learned prefix candidates, and record-based champion selection. It is **not a deliverable**, was not source-reviewed, and must not be integrated or treated as satisfying Task 4B-P. No other source path changed. This report is the explicitly requested main-worktree reporting artifact.

## Tests, lint, type checking, and mutations

- Focused command run in the physical worktree: `uv run pytest -q tests/unit/tokenization/test_prediction.py`
  - Initial partial implementation result: `5 failed, 17 passed`; each failure was existing Task 4A test fixture reuse of `committed_order=1`, correctly rejected by the new duplicate-order invariant.
  - After making the local test helper issue deterministic unique committed orders: `22 passed in 0.42s`.
- Full `tests/unit/tokenization/`: **unverified** (blocked before source completion).
- Ruff allowed paths: **unverified**.
- `uv run pyright src tests`: **unverified**.
- `git diff --check` and allowed-path diff: **unverified** as a delivery gate.
- T4BP-C01 through T4BP-C12 positive controls: **unverified**.
- All required direct mutations: **unverified**; none were run because C04 cannot be validly implemented and mutation evidence must not be produced against an incomplete source candidate.

The focused green result is only a partial regression check and is not evidence for the required controls, mutations, or source gate.

## Not adopted

- Did not modify `types.py` to permit a zero-known appended item.
- Did not use an invalid hand-built object, monkeypatch the carrier validator, or relax it.
- Did not reinterpret the required C04 literal silently as a different fixture.
- Did not modify Task 4A semantics, Task 3B carriers, Spec, Plan, status, HANDOVER, shared main, store, pipeline, checkpoint policy, configuration, dependencies, provider routing, or 4141.
- Did not commit, push, stash, reset, restore, clean, merge, or alter shared main.

## Handoff

The authority owner must resolve the C04/carrier contradiction before source work can continue. After an amended brief/Spec is independently reviewed and declared READY, a source implementer should reassess the partial uncommitted candidate in the isolated worktree rather than assuming it is correct; it has not undergone the complete required controls, direct mutations, lint, type checking, or source review.
