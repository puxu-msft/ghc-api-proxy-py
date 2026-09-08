# `docs/agents/**` index 与 worktree 状态只读审计

## 范围与总判定

- 审计对象：主树 `/home/xp/src/ghc-api-proxy-py`，分支 `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`；最终连续快照冻结于 `2026-08-07T01:14:02+00:00`。本报告只审计 Git 状态、blob 完整性、来源可归属性与安全提交机制，不评审文档内容。
- 文件集合：文件系统遍历与 `git ls-files -- docs/agents` 两种独立方法均得到同一组 6 个正式文档。`docs/agents/**` 下没有 `??`、ignored、unmerged、额外物理文件或符号链接。
- 相对 `HEAD`：6 个路径在 `HEAD` 均不存在，当前全部是 index 新增文件。最终状态为 **1 个 `A`、5 个 `AM`、0 个 `??`**。
- 来源与并发：除 `architecture.md` 外，其余 5 个文档均在本次审计期间出现 worktree blob 漂移；本审计未修改这些文件。可机械确认存在并发写入，但 Git 的 index、blob 和 mtime 不记录 actor，**无法把任何一次写入可靠归属为用户或某个 agent**。`architecture.md` 未漂移也只表示观察窗口内稳定，不构成作者身份证据。
- 提交机制：**无需 `reset` 或 `stash`。若使用 6 个文件的精确 pathspec，Git 2.43.0 允许直接以 `git commit --only -- <exact paths>` 提交命令执行时的 worktree 内容，不要求先 `git add`。** 但当前存在活跃并发写入，故“机制可行”不等于“现在已确认最终版本”；提交前必须先让写者收口并重新冻结 blob。
- index 不变性：`git commit --dry-run --only -- <6 个精确路径>` 前后 `.git/index` SHA-256 均为 `2b56de0de74cb7d47de7f20dda9f1739d44acbba492c0990605c116053cdf90c`；最终读取前后仍为该值。本审计未执行 `git add`、`reset`、`stash` 或 commit。

## 正式文档冻结表

| 正式文档 | index 状态 | index blob | worktree blob | index=worktree | 审计窗口内漂移 | worktree 大小与 UTC mtime | 来源判定 |
|---|---:|---|---|---:|---:|---|---|
| `docs/agents/anthropic-responses-bridge/acceptance.md` | `AM` | `f87e7509af8d51914e87f71d89651bd2b22e3b09` | `d83c15c586a4c28e8dfa9fc02eb1f76997923aa4` | 否 | 是 | 70535 bytes；`2026-08-07T01:13:36.298785+00:00` | 审计窗口内已观测到 worktree blob 变化；Git 无 actor 字段，无法归属用户或 agent |
| `docs/agents/anthropic-responses-bridge/architecture.md` | `A` | `24685e1d63ca239937c5085ab960c898bfd26030` | `24685e1d63ca239937c5085ab960c898bfd26030` | 是 | 否 | 62763 bytes；`2026-08-07T00:37:40.400775+00:00` | 审计窗口内未观测到变化；这只能证明两次快照相同，不能证明最初写入者身份 |
| `docs/agents/anthropic-responses-bridge/implementation.md` | `AM` | `b0146833a1215d75fbee92efc74cc7b8e7d9b9ac` | `29416829302c3214862405f75f200d44ff5db54c` | 否 | 是 | 30805 bytes；`2026-08-07T01:13:01.018369+00:00` | 审计窗口内已观测到 worktree blob 变化；Git 无 actor 字段，无法归属用户或 agent |
| `docs/agents/anthropic-responses-bridge/research.md` | `AM` | `aefdd33c8f8065dfd10b4f5f4314e1af69c642d2` | `65bfbe1054e51dbe0e24a1fc6655cebab40d1841` | 否 | 是 | 42090 bytes；`2026-08-07T01:11:39.121095+00:00` | 审计窗口内已观测到 worktree blob 变化；Git 无 actor 字段，无法归属用户或 agent |
| `docs/agents/anthropic-responses-bridge/spec.md` | `AM` | `32dbb8644a1504f20e9ef8eff219951521bdff41` | `717a3107bda7f0599b4a45a50313a3c3ad090144` | 否 | 是 | 65958 bytes；`2026-08-07T01:10:35.156603+00:00` | 审计窗口内已观测到 worktree blob 变化；Git 无 actor 字段，无法归属用户或 agent |
| `docs/agents/documentation-restructure/plan.md` | `AM` | `c451c74f646976c76fb156d0a3e3ba30ca260f25` | `30391c940a065d6afc5806f7233de7ece706685b` | 否 | 是 | 86877 bytes；`2026-08-07T01:12:10.853761+00:00` | 审计窗口内已观测到 worktree blob 变化；Git 无 actor 字段，无法归属用户或 agent |

`A` 表示新增内容已在 index，且当前 worktree 与 index 相同。`AM` 表示新增文件已有 index 快照，但 worktree 随后又修改；上表 5 个 `AM` 的 index blob 均落后于 worktree blob。index blob 由 `git rev-parse :<path>` 取得；worktree blob 由不带 `-w` 的 `git hash-object -- <path>` 计算，未写 object database。

## 提交语义与选择范围

本机 `git version 2.43.0` 的 `git commit` 手册对 `-o, --only` 的定义是：从命令行指定路径取得“updated working tree contents”，忽略其他路径已 staged 的内容。实际运行 `git commit --dry-run --only -- <6 个精确路径>` 返回 0，拟提交集合只包含这 6 个 `new file`；`docs/tmp/**`、`verification/**` 和其他 untracked 文件只列在 “Untracked files”，不在拟提交集合中。

因此有两个机械路线：

1. **推荐路线：直接精确 `commit --only`。** 无需先 `git add`，并且不会消费其他路径的 staged 内容。前提是提交前重新确认 6 个 worktree blob 已获批准且不再漂移。
2. **备选路线：精确 `git add` 后普通 commit。** 只有调用方明确想让真实 index 先与最终 worktree 同步时才需要。必须逐个列出完全相同的 6 个路径，然后验证每个 `index blob == 已批准 worktree blob`。该路线会修改共享 index；当前 index 已保留较早快照，且存在并发写者，因此不能在未协调时机械执行。

禁止直接执行不带 pathspec 的普通 `git commit` 来声称提交最终 worktree：它会提交现有 index，而 5 个 `AM` 的 index 不是当前 worktree。也不要使用目录级 pathspec `docs/agents`，因为 gate 后新出现的路径可能被意外纳入。

## 提交前后机械门

1. 在**同一次 shell 调用**内验证物理 root、`main` 和预期 `HEAD`。
2. 明确让所有正在写 `docs/agents/**` 的用户／agent 收口；本次审计已经证明仅靠连续读取不能保证稍后仍稳定。
3. 逐个精确路径重新计算 `status + index blob + worktree blob`，把 worktree blob 与主会话或用户批准值对账。任一漂移即停止，不能用 mtime 猜作者或意图。
4. 用同一组精确路径再次运行 `git commit --dry-run --only -- ...`，确认拟提交集合恰为 6 个正式文档。
5. 执行精确 `git commit --only -- ...`。若改走备选路线，先逐个精确 `git add`，再验证 index blob，最后普通 commit；两条路线二选一，不需要 `reset` 或 `stash`。
6. commit 后验证新提交中的 6 个 blob等于提交前批准的 worktree blob，并确认提交路径集合没有 `docs/tmp/**`、`verification/**` 或其他文件。

精确路径集合：

- `docs/agents/anthropic-responses-bridge/acceptance.md`
- `docs/agents/anthropic-responses-bridge/architecture.md`
- `docs/agents/anthropic-responses-bridge/implementation.md`
- `docs/agents/anthropic-responses-bridge/research.md`
- `docs/agents/anthropic-responses-bridge/spec.md`
- `docs/agents/documentation-restructure/plan.md`

## 边界

- “无法归属”是证据边界，不是内容错误结论。安全提交仍需由主会话或用户确认最终 worktree blob 是否代表预期版本。
- `--dry-run` 证明 pathspec 选择范围；本机 Git 手册证明 `--only` 的内容来源语义。二者结合支持“不先 `git add` 也能提交精确路径的 worktree 内容”。
- 本报告是唯一由本次审计写入的文件，路径为 `docs/tmp/260806-audit-docs-index-state.md`；它未加入 index，也不属于正式文档集合。
