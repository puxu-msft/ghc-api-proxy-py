# systemd runtime living Plan 定向复评 R6

- **评审范围**：current `docs/agents/systemd-runtime/plan.md` 稳定 SHA-256 `72ad650d3ee668c5145ee475fab01b05d4d9eec73378ecf5e7c00cfa339e8689`，固定主树 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮只核对 M1 reviewed source `49fb1988621bba4356e7a5039a6994c2e6d19604`、code R4、prepared squash `fe9c20315b0137ca5b2253fdbd86a30d504255ef` 已以等价提交 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 main，systemd-next integration `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的两提交 merged-state review `0 blocker／0 major`、独立 verify `PASS`、尚待进入 main，以及 Plan 继续 living、不收口和后续强化边界；未重审候选代码、测试实现、部署状态或后续强化设计。
- **总体 verdict**：**修复 major 后可进入。** M1、systemd-next 候选身份、living 边界与后续强化范围均正确，但 current Plan 尚未消费已经落盘的 systemd-next merged-state review 与独立 verify，仍把两门写成待执行。当前 bytes 不能取得 `0 major` checkpoint。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **checkpoint 判断**：**当前不可 checkpoint。** 将 systemd-next 状态从“待 merged-state review／verify”同步为“exact tip 已取得 `0 blocker／0 major` 与 `PASS`，尚待按两提交顺序进入 main并逐片执行 main-side gate”后，应对新稳定 bytes 做同范围快速复评；若达到 `0 blocker／0 major`，须明确写为“Plan 可 checkpoint、可继续执行，但仍保持 living 且不收口”。

## 双视角覆盖证据

### 机械核对

- 在同一次 shell 调用内锁定物理 root、`main` 分支、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`；Plan 前后两次 SHA-256 均为 `72ad650d3ee668c5145ee475fab01b05d4d9eec73378ecf5e7c00cfa339e8689`。
- 完整通读 current Plan，并扫描页首状态、固定事实、living 看板、M1／S3～S7、disposition、验证边界、结构怪味与 kick-off；对账 code R4、systemd-next merged-state review 和独立 verify 的 exact HEAD 与 verdict。
- Git 现场确认 `archive/260807-systemd-runtime` 精确指向 `49fb198…`，`cf53334…` 是 current main 祖先，且 `fe9c203…` 与 `cf53334…` 的 stable patch-id 同为 `eab37d38b63730f895be3e55fd256f0547209630`。
- Git 现场确认 clean `integrate/260807-systemd-next@0a93e7f…` 相对 `main@80bc8f2…` 恰有两个线性 non-merge 提交：`91f95f7…` 的 parent 为 `80bc8f2…`，`0a93e7f…` 的 parent 为 `91f95f7…`；tip 尚未进入 main。
- `docs/tmp/260807-review-code-systemd-next.md` 精确绑定该 tip，结论为 `0 blocker／0 major`、允许按当前顺序回放；`docs/tmp/260807-verify-systemd-next.md` 精确绑定同一 tip 与 base，结论为 `PASS`，并保持真实 user manager／effective cgroup／安装／部署／cutover／rolling 未验证边界。

### 第一人称执行

- 从 M1 provenance 执行时，会得到正确动作：不重放 `fe9c203…`，不重开 code R4，也不把 `cf53334…` 仓库 checkpoint 误读为 unit 已安装或运行态已切换。
- 从 current 页首、living 看板、M1 下一动作、S6 与 kick-off 执行时，Plan 会要求再次完成 `0a93e7f…` 的 merged-state review 与独立 verify；这两门事实上已经闭合，执行者会重复已完成工作并停留在错误阶段。
- 按真实 current 状态执行时，下一步应直接转为 replay 前身份／适用性门，然后按 `91f95f7…` → `0a93e7f…` 逐片进入 current main，每片后执行自己的 main-side gate；不得把 candidate-side review／verify 绿色写成已经进入 main。
- 两片进入 main 后仍须继续 S5 真实 user-manager／cgroup 三层对账与后续 S7 rolling；局部 `0 major／PASS`、Plan checkpoint 或两片回放均不表示 Plan 收口、安装、部署或 cutover 完成。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:3,8,14,46,95-98,194,283,299,334,355,419` — living 状态没有消费已经落盘的 systemd-next merged-state review 与独立 verify，仍把 exact tip 两门写成“待 review／verify” — `docs/tmp/260807-review-code-systemd-next.md:3-7,50-53` 已精确绑定 `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 相对 base `80bc8f252b46c511f428af1d97159a5980ee9dc9`，给出 `0 blocker／0 major` 并明确允许按 `91f95f7…` → `0a93e7f…` 回放；`docs/tmp/260807-verify-systemd-next.md:1-7,42-50` 对同一 tip 给出 `PASS`。照 current Plan 执行会重复两项已完成 gate，而不是进入仍未完成的逐片 main replay／main-side gate — **修复建议**：同步页首状态、M2 摘要、目标与完成定义、固定事实、看板 S3／S4／S6、M1 下一动作、S6 状态／评审、disposition、验证边界与 kick-off；统一写为“merged-state review `0 blocker／0 major`、verify `PASS` 已完成，tip 尚未进入 main，下一步按既定顺序逐片 replay 并逐片执行 main-side gate”。保留 installer atomicity 与配置测试 minor 为后补，不将其升级为 replay 门；保留 S5、S7 与 living 不收口边界。

除上述状态同步 major 外，未发现其他事实性问题。

## 已核实为准确的状态

- M1 reviewed source 为 `49fb198…`，code R4 为 `0 blocker／0 major`、明确三提交可 squash；`fe9c203…` 已以 patch-equivalent `cf53334…` 进入 current main，archive provenance 精确。
- `0a93e7f…` 仍是基于 current main 的两提交 prepared integration，尚未进入 main；source review minor、installer atomicity 裁决和其他 helper hardening 均不阻塞 replay。
- Plan 正确保持 `LIVING`：checkpoint 只批准当前文档状态进入仓库并继续实施，不构成定稿、收口、安装、部署、cutover 或 rolling 完成。
- 后续强化没有被缩减：两片 replay 后继续 S5 真实 user-manager／cgroup activation、graceful／force timeout 与 declared／effective／runtime 对账，最后另行设计和验证 S7 rolling。

## 主观建议

无。

## 结论

Current Plan 的 M1 与长期边界正确，但 systemd-next 的 review／verify 状态滞后一轮。本轮为 **`0 blocker／1 major／0 minor`**，Plan 当前不可 checkpoint。同步 exact tip 已取得 `0 blocker／0 major` 与 `PASS`、且仅剩逐片 main replay／main-side gate 的事实后重新定向复评；新稳定 bytes 若达到 **`0 blocker／0 major`**，应明确判定 **Plan 可 checkpoint、可继续执行，同时保持 living 且不收口**。
