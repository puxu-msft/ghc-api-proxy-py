# systemd Plan checkpoint 只读审计

- **评审范围**：current `docs/agents/systemd-runtime/plan.md`，稳定 SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`；R7 `docs/tmp/260807-review-systemd-runtime-plan-r7.md`；以及与“只提交该 Plan 后能否回放 systemd-next”直接相关的 prepared integration `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b`、merged-state review、独立 verify、最终 replay gate、current dirty paths 与 Git index。未修改 Plan、implementation、readiness、其他 tmp、index、候选代码、branch 或 ref；未执行 commit、cherry-pick、测试、unit 安装、manager 操作、部署或 cutover。
- **总体 verdict**：**可进入下一阶段。** Current Plan bytes 为 **`0 blocker／0 major／0 minor`**，可形成独立文档 checkpoint。使用精确 pathspec `docs/agents/systemd-runtime/plan.md` 提交时，prospective commit 只包含该 Plan，不夹带 implementation、readiness、`docs/tmp/` 或其他并行 WIP。该 Plan 提交完成并重新通过执行时 identity／preimage gate 后，可按 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 开始 systemd-next 逐片回放；每片 main-side gate 通过后才进入下一片，失败即停。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **index 结论**：审计开始、各项只读模拟与本报告落盘前后的 index entries 指纹均为 `23cd5bcc48fcb0a179b86271ff25b65b92825c63272ea20cf7415c93b0bed2d2`，staged patch SHA-256 均为空 patch 的 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，staged path 数为 0。本轮不得把报告或 Plan 加入 index。
- **边界结论**：这里的“可回放”表示 Plan checkpoint 后可进入 Plan 已规定的重验与逐片回放流程，不表示两片已进入 main，也不表示无需重验、Plan 收口、unit 已安装、真实 user manager／cgroup 已验证、部署／cutover 完成或完整产品 `PASS`。

## 双视角覆盖证据

### 机械核对

- 在同一次 shell 调用内固定物理 root `/home/xp/src/ghc-api-proxy-py`、`main` 分支与 `HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。Plan 连续两次 `sha256sum` 与 Python `hashlib.sha256` 三次读取均得到用户指定的稳定 SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`。
- 完整通读 current Plan 与 R7。R7 明确给出 `0 blocker／0 major／0 minor`，判定 current bytes 可 checkpoint；Plan 的页首、固定事实、状态看板、M1 下一动作、S6、disposition、验证边界与 kick-off 均一致写明三类 systemd-next gate 已完成、Plan checkpoint 后按既定顺序逐片回放、Plan 保持 `LIVING` 且不收口。旧的“待 merged-state review／verify”类措辞扫描无命中。
- 独立对账上游证据：`docs/tmp/260807-review-code-systemd-next.md` 精确绑定 base `80bc8f2…` 与 tip `0a93e7f…`，为 `0 blocker／0 major`、允许按当前顺序回放；`docs/tmp/260807-verify-systemd-next.md` 对同一对象判定 `PASS`；`docs/tmp/260807-final-systemd-next-replay-gate.md` 为 `0 blocker／0 major`，并确认 M2 living checkpoint 已形成。
- 独立核验 integration 图为 `80bc8f2… → 91f95f7… → 0a93e7f…`，范围内恰有两个 non-merge commits、零 merge commit，integration worktree clean。对两片 union paths 的 main commit tree 与第一片 parent 逐路径对账，既有 blob 均相等，新增 path 两侧均为 `ABSENT`。
- `git commit --dry-run -- docs/agents/systemd-runtime/plan.md` 的 prospective “Changes to be committed” 仅列出 `docs/agents/systemd-runtime/plan.md`。同一次输出把 `docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/service-cutover/readiness.md` 与其他并行修改列在未提交区域，把 `docs/tmp/` 列为 untracked；dry-run 前后 index entries、staged patch 与 staged path 数完全不变。
- Current dirty paths 与 systemd-next 的 12 个 replay paths 取交集时，唯一命中是 current Plan。故精确提交该 Plan 后，implementation、readiness、`docs/tmp/` 及随后出现的 acceptance／verification WIP 均不会夹入该提交，也不会作为 replay path 重叠项残留。
- 第一片补丁的裸 `git apply --check` 只因 current Plan 已比 integration parent 演进而返回非零，其他第一片 paths 均可应用；对 Plan 以 current bytes、base blob、第一片 postimage 做无落盘三方合并，返回 0、无冲突。该结果支持 Git 三方回放路径，但不取消实际提交后重新检查 main HEAD、integration tip、paths 与工作树状态的门。

### 第一人称执行

- 作为 checkpoint 提交者，只向 commit 命令提供 Plan 的精确 pathspec。Git dry-run 显示 prospective commit 只有 Plan；implementation、readiness、acceptance、`docs/tmp/`、verification 与其他 WIP 保持在提交之外。提交动作仍由主会话执行，本审计没有修改 index 或创建 commit。
- 作为 replay 执行者，在 Plan checkpoint 提交后重新读取 current main 与 integration exact tip，确认两片 parent 链、union paths、无重叠未提交 WIP 及适用性。当前唯一 replay overlap 是 Plan 自身，精确提交后消失；其他并行 dirty paths 不在 systemd-next replay path 集合中。
- 第一片 `91f95f7…` 先回放。虽然其 Plan patch 不能作为脱离历史的裸 patch直接套到 current bytes，但 Git 所需的 base／current／postimage 三方模拟无冲突；因此可进入正常 replay，而不是覆盖 current Plan。第一片 main-side gate 未通过时立即停止，不得继续第二片。
- 第一片通过后才回放 `0a93e7f…` 并执行第二片 main-side gate。两片完成后 Plan 继续 `LIVING`，再进入 S5 真实 user-manager／cgroup 与后续 S7 rolling；不得把文档 checkpoint 或仓库回放外推为安装、运行态替换或完整产品验收。

## 事实性发现

未发现问题。

R7 的 `0 blocker／0 major／0 minor` verdict 与 current Plan bytes、三份上游证据、integration 拓扑及 current-main preimage 一致。精确 Plan pathspec 的 commit dry-run 证明该 checkpoint 可独立提交；Plan 提交后不再有 systemd-next replay path 与其他 current WIP 重叠，三方模拟也未发现 Plan 合并冲突。

## 主观建议

无。

## 结论

Current `docs/agents/systemd-runtime/plan.md` 稳定 SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13` 为 **`0 blocker／0 major／0 minor`**，可单独形成文档 checkpoint。精确提交该 Plan 不会夹带 implementation、readiness、`docs/tmp/` 或其他 WIP；本审计全程保持 index 未修改。提交后重新通过执行时 identity／preimage／worktree gate，即可按 `91f95f7…` → `0a93e7f…` 逐片回放 systemd-next，并在每片后执行 main-side gate。该结论不授权安装、manager 操作、部署、cutover 或发布。
