# 2026-09-08 repair final current-state ledger refresh

## 范围与判据

- **范围**：仅刷新 `.dev/docs/dotdev-repository-repair/README.md` 为 current execution entry，并记录本次对账；不修改任何其它主题、ledger 或历史原件。
- **判据**：当前 filesystem、`260908-candidate-residual-disposition.md`、FRR-01 migration report、9 份 residual canonical-history migration reports，以及既有 inventory / merged-state / final-readiness reviews。
- **不在范围内**：最终独立复扫、`.dev` git checkpoint、dotdev re-root/worktree 挂载、产品测试、任何移动、删除、`git add`、commit 或 push。

## 已核对的 current state

| 事项 | 当前事实 | 证据 |
|---|---|---|
| FRR-01 | 已闭合：`260908-reasoning-encrypted-include-review.md` 已以不改写原文的方式归入 `reasoning-carrier/history/`；`tracking.md` 的 `RC-TF-01` 持有 `include-01` 的 current test follow-up，状态为 open / 待独立复验。 | `reasoning-carrier/reports/260908-encrypted-include-review-migration.md`、`reasoning-carrier/tracking.md`、history index。 |
| 原顶层 `tmp` ledger | 77/77 已实施：72 canonical history、4 exact deletion、1 interaction-context extraction。 | final readiness review 与各 migration reports。 |
| FRR-02 residual ledger | 219/219 已实施：183 canonical history、36 exact deletion、needs-user-decision=0。 | candidate residual disposition ledger 与 9 份 residual migration reports。 |
| candidate directories | 15/15 已退役；current filesystem 中 candidate directories=0、candidate regular files=0。 | 当前 `find` 复核。 |
| `tmp` | 顶层 `tmp/` 保留为机制；regular files=0。 | 当前 `find .dev/docs/tmp -maxdepth 1 -type f`。 |
| retained living direct links | 对已退役候选目录和具体顶层 `tmp/<file>` 的 direct Markdown links=0。 | current retained-living safe-superset link parse。 |
| retained exceptions | `httpx2-migration` 仍为 living residual owner；`systemd-runtime` 仍受 S5 runtime environment gate 阻塞；`interaction-context` 已建立，原稿已归档。 | httpx2 residual audit、shutdown/systemd consolidation、interaction-context extraction。 |

## 尚未做

唯一尚待的**结构性**工作按顺序为：

1. 对完成后的 tree 执行最终独立复扫；
2. 建立可审查、可恢复的 `.dev` git checkpoint；
3. 再执行并验收 dotdev re-root 与 worktree 挂载。

`RC-TF-01` 是 retained `reasoning-carrier` 的 current test follow-up，不是候选目录退役、tmp 清空或 re-root 的结构性前置；不得把它误报为 FRR-01 未闭合，也不得因本报告把它视为独立验收通过。

## 刷新实施与验证

- README 已从迁移/目录删除待办改为 final current-state entry：仅保留最终独立复扫、`.dev` git checkpoint、dotdev re-root/worktree 挂载三个未完成结构步骤；原 77 项、FRR-01、FRR-02 与 15 个目录退役均记录为已实施。
- README 链接至既有 control-plane reviews/ledgers、FRR-01/current-status/retained-exception 证据、original tmp/incoming-reference 迁移报告，以及 9 份 residual canonical-history migration reports。所有材料仍标为 point-in-time evidence，不取代 current authority。
- 对 README 的 59 个 local Markdown links 解析，missing=0；对本报告的 local links，missing=0；两文件 trailing whitespace=0。
- 对 retained living safe superset 解析 direct Markdown links，指向 15 个 retired candidate 或具体 top-level `tmp/<file>` 的结果为 0。current filesystem 复核 candidate directories=0、candidate regular files=0、top-level tmp regular files=0。
- 本次没有移动、删除或修改任何其它路径，也没有执行 `git add`、commit、push、最终独立复扫、`.dev` git checkpoint、dotdev re-root 或 worktree 挂载。
