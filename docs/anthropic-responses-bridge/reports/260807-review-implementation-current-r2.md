# Implementation living document current 定向独立复评 R2

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/implementation.md`，内容身份 SHA-256 `16b10e69ec0fc2b38921b96da54828478d9c13889c2fdc6a1e917f9bd4a8122f`。本轮只复核上一份 current 评审取得 0 major 后新增／改写的 living 状态：living 更新规则、current Spec／Acceptance、文档重组 Plan R9、nonstream／stream parser／carrier v2／systemd／route 五条切片及新建 happy integration worktree；不重新评审各候选代码、Spec／Acceptance gate 正文、Architecture 或完整产品符合性。
- **总体 verdict**：**修复 major 后可进入。** Living document 的“持续动态更新、0／0不等于收口或产品 PASS”规则仍正确，但 current 状态汇总已落后于落盘证据和实际 worktree，执行者会重复已完成的 verify／仲裁／review，忽略 systemd 新候选 HEAD，并误判新 happy integration 载体的状态。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **证据基线**：每次计入结论的 shell 调用均在同一调用内验证物理 root 与 cwd 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。Implementation SHA-256 由 `sha256sum` 与 Python `hashlib.sha256` 交叉复核一致。Current Spec 为 `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；current Acceptance 为 `FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。

## 双视角覆盖证据

### 机械核对

- 完整通读 current Implementation、上一份 current 评审、current Spec／Acceptance，并读取 Plan R9、nonstream R2、nonstream／carrier 仲裁、stream parser R2、carrier v2 R2、carrier v2 verify R2、route policy review、systemd R2。
- 用报告原文对账 verdict 与范围：Plan R9 为 0 blocker／0 major／0 minor；nonstream R2 为 0／0且可 squash，仲裁已将 carrier F-1定为组合排序依赖、usage F-2定为后续 required gap；parser R2 为 0／0／0；carrier v2 code R2 为 0／0且独立 verify R2 为 `PASS`；route policy review 为 0／0且明确可 squash；systemd 只有绑定旧 HEAD `1a220e0…` 的 R2，尚无绑定新 HEAD 的 R3 报告。
- 用 Git 逐树复核当前身份：nonstream `7ddf17364d97349638d44352bbd9a9b025723ccc`、parser `73a6aa114647440262691651cd17e9127785c75a`、carrier `8301ee938601ad86c7f72d313abc6c976a74b2a9`、route `84a22c07db3923768db44a1314e5ae6d5aed2e98` 均 clean；systemd 已前进到 clean `49fb1988621bba4356e7a5039a6994c2e6d19604`；foundations worktree仍为 clean `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。
- 对 foundations 三提交逐个执行 main ancestry 检查，`9e5f874…`、`cae83f4…`、`6a00f6f…` 均为 `NOT_ON_MAIN`，Implementation 对这一点仍准确。
- 新 happy integration 已建立为 `/home/xp/src/ghc-api-proxy-py-integrate-happy`、`integrate/260807-bridge-happy-path@6a00f6f7aaa5083cebd7387208eca65b7df3bd79`，当前没有新增 commit，worktree 有 9 个 staged 路径。一次更深的 index-to-carrier blob 比对探针因 Git 128 且未返回可用 stderr，故本报告不声称这 9 个 staged blobs 与 carrier HEAD 完全相等；可确认的结论仅是“载体已建立、组合进行中、尚无可引用 integration commit”。

### 第一人称执行

- 按 current Implementation 的“先消费文档门与切片 verdict，再完成 docs checkpoint，再回放 foundations，再消费新增 checkpoint”顺序模拟执行。执行者会被文字要求再次执行已经落盘的 carrier verify、nonstream carrier 仲裁和 route 首评，同时仍把 systemd 修复动作指向旧 `1a220e0…`，没有把新 `49fb198…` 送入 R3。
- 模拟组合路径时，现文档完全没有登记 happy integration worktree。执行者可能另建第二个组合载体，或把现有 dirty／staged worktree当成 clean、已提交的组合源；这与文档自身“状态变化先写回、不得把计划动作写成已实现事实、不得重建第二套 integration 链”的纪律冲突。
- 模拟 nonstream 回并路径时，仲裁要求固定组合顺序 `foundations → carrier v2 → nonstream`，但现文档仍写“carrier项待仲裁”；这会让执行者缺少已经裁定的唯一组合顺序。Usage detail 仍是后续 required gap，不能被仲裁或 checkpoint 0／0误写为已关闭。
- 模拟本报告 0 major 分支失败：由于上述 current-state 漂移会直接改变下一动作与组合载体选择，不能仅以“living 规则正确”放行当前 bytes。修订后若定向复评为 0 blocker／0 major，才可继续动态更新；该 0／0仍不表示 Implementation 收口、产品 PASS、foundations 已进 main或 happy integration 已提交。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:11-12,35,45-49,57-63,170-184,206-209,222-227` — Current 状态与下一动作未消费已经落盘的 Plan R9、三份切片后续证据、systemd 新 HEAD及新 happy integration worktree，导致 living truth source 与执行现场分叉 — 证据如下：

1. 文档多处仍写“文档重组 Plan R8”，但 `docs/tmp/260807-review-doc-migration-plan-r9.md` 已绑定 current Plan `054087655a539ad95babb2a15f918bc0467aa0fd6726d6e17569169f31f12aee` 并给出 0 blocker／0 major／0 minor、可继续执行。
2. Carrier v2仍写“待独立 verify”，但 `docs/tmp/260807-verify-carrier-v2-r2.md` 已绑定 `8301ee938601ad86c7f72d313abc6c976a74b2a9` 并给出 `PASS`；其 code R2也为 0／0、可 squash。
3. Nonstream仍写“carrier项待仲裁”，但 `docs/tmp/260807-arbitrate-nonstream-carrier-dependency.md` 已裁定 carrier F-1是组合排序依赖，不是 converter major，并冻结 `foundations → carrier v2 → nonstream`；usage F-2仍是后续 required gap，产品保持 `UNVERIFIED`。
4. Route policy仍写“待独立 review”，但 `docs/tmp/260807-review-code-route-policy.md` 已绑定 `84a22c07db3923768db44a1314e5ae6d5aed2e98`，为 0 blocker／0 major且明确可 squash。
5. Systemd仍把 current 候选写成 `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` 并要求实施 permissions 修复；实际 clean HEAD 已为 `49fb1988621bba4356e7a5039a6994c2e6d19604`，commit subject为 `fix: restrict systemd state permissions`，并已出现 `UMask=0077`与`StateDirectoryMode=0700`。但没有任何 R3 报告绑定 `49fb198…`，所以准确状态应是“修复候选已形成，待 R3”，不得写成 R2 major仍未实施，也不得预写 0／0或可 squash。
6. Happy integration worktree已建立，但 Implementation未登记。现场为 `integrate/260807-bridge-happy-path@6a00f6f…`，没有新增 integration commit，9 个 staged 路径使 worktree非 clean。它只能写成“新载体已建立、组合进行中／待形成可评审提交”，不能写成“happy integration 已完成／已 PASS”，也不能让执行者再建第三套组合链。

— **失败场景**：按现文档执行会重复 carrier verify／route review／nonstream仲裁，继续在旧 systemd HEAD上规划已实施的修复，并可能无视现有 happy worktree重建组合载体或把 staged WIP当成可回放提交；这些都是 current tracking 文档对执行顺序与状态的实质误导。— **修复建议**：在顶部状态、major处置、总体进度、并行开发线、逐片收敛、下一步、结构怪味与结尾摘要中一次性传播同一组 current facts：Plan R9 0／0／0；nonstream R2 0／0＋仲裁后的固定组合依赖＋usage gap；parser R2 0／0／0；carrier v2 review 0／0＋verify PASS；route 0／0；systemd `49fb198…` 修复候选待 R3；happy integration载体已建但仍停在 foundations tip且有 9 个 staged路径、无新增提交。保留 foundations未进main、Spec／Acceptance身份、产品`UNVERIFIED`及0／0只放行继续动态更新的边界。

## 主观建议

无。

## 结论

Current Implementation 的 living规则、Spec／Acceptance绑定、foundations未进main与产品`UNVERIFIED`边界仍正确，但 volatile state已经落后于证据与Git现场。本轮为 **0 blocker／1 major／0 minor**，须先同步上述 current facts，再做 R3定向复评。

修订后的 Implementation 若达到 **0 blocker／0 major**，应明确解释为：**可以继续动态更新和执行下一阶段，不需收口**。该结论不预先覆盖未来bytes，也不表示任何未进入main的切片已回放、systemd已部署、happy integration已提交或完整bridge已通过Acceptance。
