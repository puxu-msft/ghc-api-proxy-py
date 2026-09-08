# systemd runtime living Plan 独立复评 R8

- **评审范围**：current `docs/agents/systemd-runtime/plan.md`，稳定 SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`；主树固定为 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮独立核对 `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的 merged-state review、独立 verify、最终 replay gate、两提交顺序、Plan checkpoint、living 不收口及后续 hardening 边界；不重新评审候选代码，不执行 commit、回放、测试、unit 安装、manager 操作、部署或 cutover。
- **总体 verdict**：**可进入下一阶段。Current Plan 可形成文档 checkpoint。** 文档对 systemd-next current 状态、下一动作、living 边界和非阻断强化的表述与精确证据一致。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **checkpoint 结论**：**0 major 明确允许 checkpoint。** 仅将 current Plan 形成稳定文档 checkpoint 后，重新通过执行时 identity／preimage／worktree gate，即可按 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 逐片回放 current main；每片 main-side gate 通过后才进入下一片，失败即停。
- **边界结论**：checkpoint 与两片后续回放均不使 Plan 收口。Plan 保持 `LIVING`，S5 真实 user-manager／cgroup、S7 rolling 及已登记 hardening 继续作为后续切片；它们不阻断当前已达到 `0 major` 的 checkpoint 或逐片回放门。本 verdict 不表示两片已进入 main、unit 已安装、运行态已切换、部署／cutover 已完成或完整产品 `PASS`。

## 双视角覆盖证据

### 机械核对

- 每次 shell 均在同一次调用内固定物理 root `/home/xp/src/ghc-api-proxy-py`、`main` 分支、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。评审开始时连续两次 `sha256sum` 均得到 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`，`HASH_STABILITY=PASS`；既有独立 checkpoint 审计另以 Python `hashlib.sha256` 交叉得到同一内容身份。
- 完整通读 current Plan。页首状态、固定事实、状态看板、M1 下一动作、S3／S4、S6、disposition、验证边界、结构怪味和 kick-off 均一致写明：Plan 为 `LIVING` 且不收口；systemd-next exact tip 的 review／verify／replay gate 已完成；文档 checkpoint 后按既定顺序逐片回放；后续强化不阻断。
- 独立核验 Git 图严格为 `80bc8f2… → 91f95f7… → 0a93e7f…`，范围内恰有两个 non-merge commits、零 merge commit；第一片 parent 是 current main，第二片 parent 是第一片。
- 完整读取 `docs/tmp/260807-review-code-systemd-next.md`：报告精确绑定 base `80bc8f2…` 与 tip `0a93e7f…`，verdict 为 `0 blocker／0 major`，允许按 `91f95f7… → 0a93e7f…` 回放；继承的 installer atomicity minor 明确不阻断。
- 完整读取 `docs/tmp/260807-verify-systemd-next.md`：同一 tip／base 的独立验收为 `PASS`，并明确未外推真实 user manager、effective cgroup、unit 安装、部署或 cutover。
- 完整读取 `docs/tmp/260807-final-systemd-next-replay-gate.md`：最终 gate 为 `0 blocker／0 major`，M2 living checkpoint 已形成；S3 配置测试判别力、S4 逐文件 atomicity 和其他 helper hardening 均保留后补但不阻断。报告识别的唯一即时执行重叠是 current Plan WIP，正由本次文档 checkpoint 路径处置。
- 完整读取 `docs/tmp/260807-audit-systemd-plan-checkpoint.md`：该审计对同一 Plan 稳定 bytes 给出 `0 blocker／0 major／0 minor`，并以精确 pathspec dry-run 与三方模拟确认 Plan 可独立 checkpoint，checkpoint 后可进入两片正常回放流程。

### 第一人称执行

- 作为文档 checkpoint 执行者，只提交 `docs/agents/systemd-runtime/plan.md` 的精确 pathspec，不夹带 implementation、readiness、`docs/tmp/` 或其他并行 WIP；提交后重新 gate 当时的 main HEAD、integration exact tip、两片 parent、重叠 paths 与工作树状态。
- 作为代码回放执行者，先回放 `91f95f7…` 并执行第一片 main-side gate；只有该 gate 通过，才回放其直接后继 `0a93e7f…` 并执行第二片 main-side gate。任一身份、preimage、路径或运行门漂移即停止，不把本报告强行沿用到变化后的现场。
- 作为后续 Plan 执行者，两片回放完成后继续 S5 真实 user-manager／cgroup，再进入独立的 S7 rolling；不会把 M2 checkpoint 或仓库回放误读为真实安装、服务替换、部署或 cutover。
- 作为维护者，继续保留 S3 配置测试判别力、S4 逐文件 atomicity、冲突备份／卸载 manifest、symlink hardening 与共享 timeout facts 等后续强化；但不会把这些已裁决为 non-blocking 的事项临时升级为当前 checkpoint／replay gate。

## 事实性发现

未发现问题。

Current Plan 对 `0a93e7f…` 的三层证据陈述准确：merged-state review 为 `0 blocker／0 major`，独立 verify 为 `PASS`，最终 replay gate 为 `0 blocker／0 major`。下一动作在所有执行入口均保持为 Plan checkpoint 后按 `91f95f7… → 0a93e7f…` 逐片回放，Plan 全程 living 不收口，后续强化明确保留且不阻断。

## 主观建议

无。

## 结构怪味与方案反思

- **结构怪味扫描**：扫描 `docs/agents/systemd-runtime/plan.md:3-25,41-46,92-98,190-200,230-249,281-301,319-355,389-425`，判据为重复状态是否降级、review／verify／replay gate 是否混写、checkpoint 是否被外推为运行态结论、后补事项是否被静默删除或升级为阻断门。未发现新的重复实现、职责错位、抽象泄漏或强弱不一致；本轮无需修改，后续状态变化继续回写 living Plan。
- **内部替代方案**：当前以独立 code review、verify、replay gate 与 main-side gate 分层，比仅凭 Plan 自述或一次组合测试放行更可靠；未发现更好的项目内替代路径。
- **判据判别力**：三份上游报告分别约束代码合并态、用户可观察行为与回放适用性，Plan checkpoint 审计另约束文档 WIP／精确 pathspec，能够区分“候选已验证”“文档可 checkpoint”“代码已进入 main”三种状态，未发现假绿或假红接缝。
- **成熟第三方方案**：本轮是 living 文档状态复评，不涉及应由第三方库替代的实现机制；候选内 unit 语义已交由官方 `systemd-analyze` 验证。

## 结论

Current `docs/agents/systemd-runtime/plan.md` 稳定 SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13` 为 **`0 blocker／0 major／0 minor`**，**明确可形成文档 checkpoint**。Checkpoint 后重新通过现场 gate，即按 `91f95f7…` → `0a93e7f…` 逐片回放并逐片执行 main-side gate；后续 hardening 不阻断。Plan 保持 `LIVING` 且不收口。
