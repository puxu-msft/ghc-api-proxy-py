# systemd-next current-main preimage 最终复核 R2

- **评审范围**：只读复核 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、prepared integration `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的线性两提交 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b`、current main 的 tracked WIP、两片路径交集及 archive targets。已有 merged-state review、独立 verify 与 final replay gate 均为 0 major，本轮不重审代码、不重跑测试、不执行 checkpoint、cherry-pick、ref 更新、worktree 清理、unit 安装、manager 操作、部署或 cutover；主树唯一写入为本报告。
- **总体 verdict**：**可进入下一阶段；0 major。四份 living docs 全部提交形成 checkpoint 后，可按 `91f95f7…` → `0a93e7f…` 逐片回放。** Current main commit tree 仍精确满足第一片 `91f95f7…` 的 parent preimage；现场 worktree 因 `docs/agents/systemd-runtime/plan.md` WIP 与两片都重叠，当前不得开始第一片。四 docs checkpoint 完成并重新通过 identity／preimage／worktree gate 后，第一片可立即回放；第一片 main-side gate 通过后才可进入第二片。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。本轮没有新增产品或回放缺陷；当前 Plan overlap 是已知、可由指定 checkpoint 关闭的执行前置条件。
- **即时状态**：**尚不可回放。** Main tracked WIP 精确为四份 docs，index 无 staged path。必须先由其 owner 把四份 docs 安全提交为 checkpoint；不得 restore、stash、覆盖或把 WIP 吸收到任一 systemd 代码提交。
- **证据边界**：本 verdict 只放行 checkpoint 后的仓库逐片回放与每片 main-side gate，不表示 checkpoint 已完成、两片已进入 main、archive refs 已创建、Plan 收口、unit 已安装、真实 user manager／effective cgroup 已验证、部署／cutover 已完成或完整产品 `PASS`。

## 双视角覆盖证据

### 机械核对

- 固定主树物理 root、`main` 分支与 exact HEAD `80bc8f2…`；固定 integration 物理 root、`integrate/260807-systemd-next`、exact tip `0a93e7f…` 与 clean worktree。提交图仍为 `80bc8f2… → 91f95f7… → 0a93e7f…`，没有额外提交。
- 对第一片全部路径逐项比较 current main commit tree／现场 worktree。除 Plan WIP 外，既有路径 blobs 均与 `91f95f7…` parent 相等；新增 `src/app/graceful_timeout.py` 在双方均为 `ABSENT`。因此 commit-tree preimage 保持正确，但当前 worktree preimage 尚未全绿。
- 用 `git diff --name-only` 与 `git status --porcelain --untracked-files=no` 对账 tracked WIP：精确为 `docs/agents/anthropic-responses-bridge/acceptance.md`、`docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/service-cutover/readiness.md`、`docs/agents/systemd-runtime/plan.md`；四者均为 `HEAD == index != worktree`，staged path 数为零。
- 机械计算四份 WIP 与每片 changed paths 的交集。第一片和第二片的唯一交集都为 `docs/agents/systemd-runtime/plan.md`。因此“先 checkpoint”必须发生在第一片之前，而不是只在第二片之前；其余三份 docs 不与两片路径重叠，但按本次指定边界仍作为同一 living-doc checkpoint 一并提交。
- 重新通读并绑定既有证据：`docs/tmp/260807-review-code-systemd-next.md` 对 exact base／tip 给出 `0 blocker／0 major`；`docs/tmp/260807-verify-systemd-next.md` 对同一对象给出 `PASS`；`docs/tmp/260807-final-systemd-next-replay-gate.md` 给出 `0 blocker／0 major` 并规定执行前重验、逐片回放与每片 main-side gate。本轮现场未发现使这些 verdict 失效的 main commit-tree 漂移。
- 核对 source provenance：S3 reviewed source branch `feat/systemd-graceful-timeout` 仍指向 `865a5b71210e2436b36786b5de67146939d1e0f5`；S4 reviewed source branch `feat/systemd-user-install` 仍指向 `e16c2a700f23f66535e7347ab7357518eb8e56bd`。当前只有既有 M1 `archive/260807-systemd-runtime → 49fb1988621bba4356e7a5039a6994c2e6d19604`；本轮未发现 S3／S4 archive refs。

### 第一人称执行

- 作为 checkpoint 提交者，先把四份 living docs 作为独立文档 checkpoint 提交，不夹带 `docs/tmp/`、verification artifacts 或 systemd 代码。提交后重新读取实际 main HEAD，而不是继续假设它仍为 `80bc8f2…`。
- 作为第一片回放者，提交 checkpoint 后重新确认 integration tip 未变、main 无与第一片重叠的未提交 WIP、第一片 parent／current main 三方适用性成立，然后回放 `91f95f7…`。由于 Plan 同时属于第一片路径，不能在 checkpoint 前先摘第一片。
- 第一片完成后执行其 main-side gate；只有 gate 通过才回放 parent 为第一片的 `0a93e7f…`。第二片完成后再执行第二片 main-side gate。任一 identity、preimage、apply 或 gate 失败都立即停止，不沿用本报告强推。
- 作为 archive 执行者，只在对应片回放且 main-side gate 通过后归档 reviewed source identity：S3 target 固定为 `865a5b7…`，S4 target 固定为 `e16c2a7…`。Archive 保存 source provenance，不改指 integration commit；当前 Plan 未冻结 S3／S4 archive ref 名，本报告不擅自命名或创建 ref。
- 作为后续执行者，两片进入 main 后继续 living Plan 的真实 user-manager／cgroup 等后续切片；不能把仓库回放写成 unit 已安装、运行态已切换、部署／cutover 完成或完整产品通过。

## Current main preimage 与 WIP 结论

### Commit-tree preimage

`main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 仍是 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` 的精确 parent。第一片所有已有路径的 main blobs 与 parent blobs 相等，新增路径在两侧均不存在。因此 prepared integration 的第一片 commit-tree preimage 未漂移。

### Worktree 可执行性

Current main 的 tracked WIP 精确为以下四份文档：

1. `docs/agents/anthropic-responses-bridge/acceptance.md`
2. `docs/agents/anthropic-responses-bridge/implementation.md`
3. `docs/agents/service-cutover/readiness.md`
4. `docs/agents/systemd-runtime/plan.md`

四者均未 staged。只有 `docs/agents/systemd-runtime/plan.md` 与 systemd-next 路径相交，但它同时命中 `91f95f7…` 与 `0a93e7f…`。所以 current main commit tree 满足 preimage，不等于当前 dirty worktree 可以立即回放。必须先提交四 docs checkpoint，再重验现场状态。

## Archive targets

| Slice | Reviewed source target | Integration commit | 当前 archive 状态 | 回放后要求 |
|---|---|---|---|---|
| S3 graceful timeout | `865a5b71210e2436b36786b5de67146939d1e0f5` | `91f95f7d30c0b399eef98d997c0f88f57c2d0284` | 未发现对应 archive ref | 第一片 main-side gate 通过后，archive target 指向 reviewed source `865a5b7…` |
| S4 user installer | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` | 未发现对应 archive ref | 第二片 main-side gate 通过后，archive target 指向 reviewed source `e16c2a7…` |

既有 M1 archive `archive/260807-systemd-runtime` 继续精确指向 `49fb1988621bba4356e7a5039a6994c2e6d19604`，不应改指 S3、S4 或 integration tip。S3／S4 archive ref 名仍未冻结；名称由回放执行阶段依据 current Plan 决定，target commit 不得漂移。

## 事实性发现

未发现问题。

现场唯一 replay overlap 是已知 Plan WIP，四-doc checkpoint 能机械关闭该门；current main commit-tree preimage、integration identity、上游 0-major／`PASS` 证据与 source archive targets 均保持一致。本轮不把预期的 checkpoint 前置条件误报为产品 major，也不把 commit-tree 预像正确误写成 dirty worktree 已可执行。

## 主观建议

无。

## 结论

**0 blocker／0 major／0 minor。四份 living docs 提交后可回放。** Checkpoint 后重新验证实际 main HEAD、integration exact tip、第一片 preimage 与重叠 worktree 状态；通过后按 `91f95f7…` → `0a93e7f…` 逐片执行，每片 main-side gate 通过后才进入下一片。两片分别通过后，archive targets 保存 reviewed source `865a5b7…` 与 `e16c2a7…`。该放行不授权任何 unit 安装、manager 操作、部署、cutover、ref 发布或远程发布。
