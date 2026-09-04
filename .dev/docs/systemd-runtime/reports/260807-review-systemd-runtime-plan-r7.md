# systemd runtime living Plan 定向复评 R7

- **评审范围**：current `docs/agents/systemd-runtime/plan.md`，连续两次读取及 `sha256sum`／Python `hashlib` 交叉验证均为 SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`；固定主树 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮只核对 `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的 merged-state review、独立 verify 与最终 replay gate 均已完成，下一步是否为 Plan checkpoint 后按 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 逐片回放，Plan 是否继续 living 且不收口，以及后续强化是否保持非阻断；未重审候选代码、测试实现、部署状态、真实 manager／cgroup 或后续强化设计。
- **总体 verdict**：**可进入下一阶段。current Plan 明确可 checkpoint 并继续执行。** R6 的唯一 major 已关闭：Plan 已准确消费 `0a93e7f…` 的 merged-state review `0 blocker／0 major`、独立 verify `PASS` 与最终 replay gate `0 blocker／0 major`，并把下一步推进为文档 checkpoint 后按 `91f95f7…` → `0a93e7f…` 逐片回放和逐片执行 main-side gate。Plan 继续 `LIVING` 且不收口；既有 minors、helper hardening、S5 与 S7 均继续保留，但不阻断已经满足的 M2 checkpoint 或逐片回放门。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **checkpoint 判断**：**Plan 当前 bytes 可 checkpoint、可继续执行。** 该 checkpoint 只稳定 current living 状态并解除 Plan WIP 对 replay 的即时阻碍，不表示两片已进入 main、Plan 收口、unit 已安装、真实 user manager／cgroup 已验证、部署／cutover 完成或完整产品 `PASS`。

## 双视角覆盖证据

### 机械核对

- 在同一次 shell 调用内固定物理 root、`main` 分支与 `HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。对 planner 修订后的 current Plan 连续读取两次 hash，均为 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`；Python `hashlib.sha256` 独立实现得到同值。
- 完整通读 current Plan，并扫描页首、固定事实、Living 状态看板、M1 下一动作、S3～S7、disposition、验证边界、结构怪味与 kick-off。`docs/agents/systemd-runtime/plan.md:3,46,98,194,283,334,355,419` 均已把 exact tip 三门写成完成，并一致指向 Plan checkpoint 后的逐片回放。
- 旧阶段残留扫描为空：current Plan 不再包含“仍待 merged-state review 与独立 verify”“当前待该 exact tip”“prepared integration 待复核”或“下一步对 exact tip 做 review／verify”等 R6 陈述。
- 对账 `docs/tmp/260807-review-code-systemd-next.md:3-6`、`docs/tmp/260807-verify-systemd-next.md:3-7,50` 与 `docs/tmp/260807-final-systemd-next-replay-gate.md:3-8,100`：三份证据精确绑定 base `80bc8f2…` 与 tip `0a93e7f…`，结论依次为 `0 blocker／0 major`、`PASS`、`0 blocker／0 major`，且 final gate 明确 M2 living checkpoint 已形成。
- Current Plan 保留 S3 配置测试判别力、S4 installer atomicity、冲突备份／卸载、symlink hardening 与共享 timeout facts 等后补边界，并明确它们不阻断 checkpoint 或逐片回放；S5 真实 user-manager／cgroup 与 S7 rolling 仍在后续切片中。

### 第一人称执行

- 作为 Plan 执行者，从页首、看板、M1 下一动作、S6 与 kick-off 进入时，会跳过已经闭合的 review／verify／final replay gate，不再重复派发已完成工作。
- 当前唯一即时动作是先将本 Plan 稳定为文档 checkpoint；随后重新验证 current main、integration exact tip、parent／preimage 与重叠 paths，再回放 `91f95f7…` 并执行第一片 main-side gate。只有第一片通过，才回放 `0a93e7f…` 并执行第二片 gate；任一失败即停止。
- 两片回放完成后继续 S5 真实 user-manager／cgroup 的 activation、graceful／force timeout 与 declared／effective／runtime 三层对账，之后再进入 S7 rolling。执行者不会把 M2 checkpoint、Plan checkpoint 或逐片回放误读为安装、部署、cutover 或完整产品通过。
- 遇到 S3／S4 minors 与其他 helper hardening 时，Plan 明确将其保留为后补而非 replay 门；信息未丢失，也不会因长期强化范围存在而阻塞当前正确动作。

## 事实性发现

未发现问题。

R6 的唯一 major 已关闭：current Plan 已把完成的三类 gate、M2 living checkpoint、Plan checkpoint 后的两提交回放顺序、逐片 main-side gate、living 不收口与后续强化非阻断边界同步到所有执行入口。

## 主观建议

无。

## 结论

Current Plan 为 **`0 blocker／0 major／0 minor`**。**Plan 明确可 checkpoint、可继续执行，同时保持 `LIVING` 且不收口。** 下一步是在该文档 checkpoint 后重验 replay identity／preimage gate，再按 `91f95f7…` → `0a93e7f…` 逐片回放 current main 并逐片执行 main-side gate。后续强化继续保留但不阻断本 checkpoint；本 verdict 不表示两片已进入 main、unit 已安装、部署／cutover 完成或完整产品 `PASS`。
