# `.dev` development records

This directory is the main worktree's active copy of agent-authored development records. It is intentionally ignored on `main`; the dedicated orphan branch `origin/dotdev` is the durable Git source and carries only `.dev/`.

This storage choice was selected by the user on 2026-09-04 in Claude Code session `00409e7f-6b11-4954-9cfc-56d755db19dd`. It replaces the earlier project rule that described `.dev/` as a nested independent repository.

## Roles

- `.dev/docs/` holds living development documents, review originals, disposition ledgers and archived development records according to `.claude/rules/00-development-workflow.md`.
- `.dev/human-controlled-docs-candidates/` holds agent-written candidate material for `docs/.human-controlled/`; it never authorizes an agent to edit that user-controlled directory unless the user gives a current explicit instruction.
- The ignored `.dev/` under the main worktree is the collaborative editing surface. A file existing there is not proof that it is durable.
- `origin/dotdev` is the last published durable snapshot. A local `dotdev` commit that has not been pushed is durable only in the current clone and must not be described as present on `origin/dotdev`.

## Synchronization

Use a dedicated worktree checked out on local branch `dotdev`; never switch the shared main worktree away from `main`. Copy only the exact `.dev` paths owned by the current task from the main working copy into that worktree, compare their content hashes, commit with exact pathspecs, and push only when the user has given a current explicit publication instruction.

Do not bulk-copy `.dev/`: other sessions may be writing unrelated reports or living documents in the same ignored directory. Do not merge or squash `dotdev` into `main`; the orphan branch is storage for development records, not a feature branch.

When the main working copy and `dotdev` differ, first identify which side contains active peer work. A branch snapshot must not overwrite newer ignored files, and an unreviewed ignored file must not silently replace a reviewed durable snapshot. Resolve the owned paths explicitly and leave unrelated differences untouched.

## Recovery

Fetch `origin/dotdev` into a local `dotdev` branch and inspect it in a dedicated worktree. Restore only the required paths into the main worktree's ignored `.dev/` copy; do not checkout the orphan branch in the shared main worktree.
