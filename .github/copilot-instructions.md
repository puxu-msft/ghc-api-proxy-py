# ghc-api-proxy-py agent instructions

The detailed project workflow is maintained in [`.claude/rules/00-development-workflow.md`](../.claude/rules/00-development-workflow.md). Apply it to all work in this repository.

Critical always-on points:

- Develop new functionality as small incremental slices: runnable skeleton and happy path first, discriminating smoke test, prompt squash integration, then targeted hardening.
- Finish and freeze observable behavior in the Spec before implementation. Implementation plans are living documents and evolve alongside code; starting implementation does not close a plan or require another approval cycle.
- Keep no more than 10 subagents in flight. Parallelize independent work, but reuse existing context and avoid resource contention.
- Test only the critical path, happy path, and failure mechanism actually changed. Add tests for newly observed failures; do not prebuild exhaustive proof matrices or verification governance.
- Solve the user task before building proof infrastructure. Do not introduce manifests, voting/graduation protocols, evidence control planes, or validation state machines unless explicitly requested or they are the deliverable.
- Review a final candidate HEAD once by default. Run targeted tests for small fixes, one full regression plus Ruff/Pyright for a squash candidate, and one merged-state review after related slices land. Avoid repeated reviews and reruns of unchanged bytes.
- Integrate feature work with squash commits, never fast-forward or regular merge. Preserve the reviewed source under an immutable `archive/YYMMDD-<topic>` branch after the main-side gate passes. Never push without a current explicit user request.
- New `docs/tmp` reports use an actual `YYMMDD-` prefix and are temporary evidence, not a truth source. Distil conclusions into live docs and archive point-in-time evidence by topic.
- The primary product path is Anthropic Messages served through an OpenAI Responses upstream. Block-level buffering is required; downstream does not expose token/event-level live streaming.
- Do not signal, stop, restart, reconfigure, or take over the existing Bun service on `4141` without an explicit cutover instruction. Socket activation preserves the listener and queued unaccepted connections, not already accepted connections.
