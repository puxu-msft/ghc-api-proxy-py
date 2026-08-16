---
---

# Project development workflow

## Delivery style

- This is a new project. New functionality does not default to TDD. Implement a runnable skeleton and happy path first, add a discriminating smoke test, squash it into `main` promptly, then add error handling and regression coverage in subsequent small slices.
- A complete behavioral Spec is required before implementation changes observable behavior. The Spec is refined and frozen first. Implementation plans are living documents: drafting a plan starts implementation rather than pausing it, and a plan that reaches independent review consensus needs no additional approval before execution. Keep plans synchronized as code and findings change; starting implementation never means the plan is closed.
- Complete and integrate each self-contained small patch immediately. Do not wait for a large feature or design batch when a smaller slice is already reviewable and useful.

## Parallel work

- Parallelism is a core practice, but the development machine is resource-constrained. Keep no more than 10 subagents in flight at once.
- Dispatch narrow tasks immediately when they are independent. Reuse existing reports, verified facts, exact commits, and concrete paths in dispatch prompts instead of making each agent rediscover the project.
- Do not let a new idea silently redirect or narrow the primary task. Run independent work in parallel where possible.

## Tests and review

- Tests cover the critical path, happy path, and failure mechanism actually changed in the current slice. Add targeted tests when a real new failure surface is found; do not prebuild a complete state space, exhaustive proof matrix, or verification governance layer.
- Test groups with different goals get different entries. Setup that only one group needs must live with that group, never in a shared `conftest.py` or a root-level environment tweak — a shared entry imposes one group's environment on every other group and silently removes the next group's ability to choose its own. TUI tests live in `tests/tui/`, are excluded from the default sweep, and run when `src/app/observability/tui.py` changes or by hand via `uv run pytest tests/tui`.
- Reuse existing tests and simple probes. For a small fix, run targeted tests. For a squash candidate, run one final full regression, Ruff, and Pyright. After several related slices land, perform one merged-state review rather than repeating full reviews after every micro-commit.
- Review the final candidate HEAD once by default. Re-review only when the candidate changes in a way that can invalidate the verdict. Do not repeatedly review unchanged bytes or rerun identical evidence without a concrete reason.
- Solve the requested task before building proof infrastructure. Ordinary implementation, refactoring, documentation, migration, Git cleanup, and result checks must not be expanded into manifests, voting systems, graduation protocols, proof control planes, or validation state machines unless the user explicitly requests that infrastructure or it is the deliverable.

## Git and worktrees

- Work incrementally in isolated worktrees when useful. Integrate with a squash commit only; do not use fast-forward or regular merges for feature worktree integration.
- After a reviewed source is squashed and the main-side gate passes, preserve its reviewed source commit under an immutable `archive/YYMMDD-<topic>` branch. Do not point the archive at the squash commit.
- Keep active or dirty worktrees. Remove a clean historical worktree only after its exact HEAD is reachable from a durable archive ref and its semantics are present in `main`.
- Never push or otherwise publish unless the user gives a current explicit instruction for that publication.

## Documentation and agent reports

- `docs/` holds live conclusions, `docs/agents/<topic>/` holds in-flight development documents, and `docs/agents/<topic>/archive-<date>/` holds historical development records.
- Subagent investigations, reviews, and PoCs exchange full reports through repository files. New temporary reports use a `YYMMDD-` prefix under `docs/tmp/` and are never overwritten. Distil current conclusions into live docs promptly; do not let `docs/tmp/` become the only source of truth.
- Specs remain normative while their external contract is active. Implementation and readiness documents remain living and are updated at meaningful checkpoints, not after every commit.

## Current project priorities and product boundaries

- The primary product path is Anthropic Messages input served through an OpenAI Responses upstream. Continue tracking relevant changes in `~/src/copilot-api-js` and its references, but do not copy its defaults or defects as project contracts.
- Block-level buffering is required. Downstream does not provide token- or event-level live streaming; a complete Anthropic content block is the delivery unit.
- The project uses its own versioned reasoning carrier as the default producer and accepts the current `copilot-api-js` v1 format on its legal compatibility path. Compatibility does not require matching every malformed decoder edge or copying lossy aggregation.
- The deployment goal is a systemd/cgroup-managed service with listener continuity and graceful shutdown. Socket activation preserves the listener and queued, unaccepted connections; it does not migrate connections already accepted by the old process and must not be described as full zero-downtime migration.
- Production replacement of the existing `copilot-api-js` requires a separate explicit cutover instruction. Until then, do not signal, stop, restart, or take over the existing `4141` Bun service.
