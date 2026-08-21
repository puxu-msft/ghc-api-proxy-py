# Anthropic Responses bridge living 文档联合终审

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/README.md` 与 `docs/agents/anthropic-responses-bridge/implementation.md`。本轮只做机械核对：五文档阅读顺序与 `D-ARCH`／`D-MIGRATION` 边界、Spec／Acceptance／产品状态、Implementation living 规则、foundations 回放阻断、happy integration 实际身份、source reviews／nonstream 仲裁／systemd／route 状态，以及下一步执行顺序；不评审方案优劣、不运行产品测试、不修改被评审文档。
- **总体 verdict**：**修复 major 后可进入。** 两份工作树文档的权威边界、阅读顺序、frozen oracle 状态、Implementation living 语义与 foundations-first 执行顺序机械一致；但当前 index 中拟提交的两个 blob 都不是本轮连续两次 hash 稳定的工作树 bytes，且 `implementation.md` 对 happy integration 的 clean／review 状态已经落后于现场。因此当前不能给出“0 major、可直接提交当前 index”的结论。关闭下列 2 项 major 并复核后，两文件可作为 living checkpoint 提交；该 checkpoint 不使 Implementation 收口，后续仍须动态更新。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：在主树 `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1` 上逐次 gate 物理 root、cwd、branch 与精确 HEAD；完整读取 README、Implementation、Spec、Research、Architecture、Acceptance；对账阅读顺序、文档权威表、状态标记、hash、Architecture 唯一裁决矩阵、Implementation 进度表／开发线／回放策略／下一步；核验 foundations、happy、nonstream、carrier、parser、route、systemd worktree 的 branch／HEAD／clean 状态；读取相关 review／verify／仲裁 verdict；核验 main index path、index blob、工作树 blob、foundations ancestry 与 `CHERRY_PICK_HEAD`／`MERGE_HEAD`／`REVERT_HEAD`。
- **双视角覆盖证据——第一人称执行模拟**：按 README 指定顺序模拟 `Spec → Research → Architecture → Acceptance → Implementation`，确认执行者最终只需裁决 `D-ARCH` 与 `D-MIGRATION`，不会把 Architecture 推荐或文档评审当成用户接受；再从 Implementation“下一步”依次模拟“提交两份 living 文档清 index → 回放 foundations 三片 → 评审／修复 happy integration → 消费后续 checkpoints → systemd 收敛”，在提交动作处由 index／worktree blob mismatch 复现错误提交对象，在 happy gate 处由 dirty worktree 与已落盘 1-major review 复现陈旧状态。

## Hash 稳定记录

同一主树 gate 调用内对五份阅读文档连续执行两轮 SHA-256；两轮逐文件完全一致，`HASH_STABILITY=PASS`。本表记录的是工作树 current bytes，不是 index bytes：

| 文档 | Round 1 | Round 2 | 稳定 |
|---|---|---|---|
| `README.md` | `2de36b129b7682cfc1637fac2498226d838dbf939195cea8c15ff12603e35840` | `2de36b129b7682cfc1637fac2498226d838dbf939195cea8c15ff12603e35840` | 是 |
| `implementation.md` | `fe051644c793e3fc57e35b2f1b2d20b285af1eb9bbb08825114300b5f9943fee` | `fe051644c793e3fc57e35b2f1b2d20b285af1eb9bbb08825114300b5f9943fee` | 是 |
| `spec.md` | `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` | `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` | 是 |
| `acceptance.md` | `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4` | `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4` | 是 |
| `architecture.md` | `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d` | `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d` | 是 |

## 机械对账通过项

- README 的五文档阅读顺序精确为 `Spec → Research → Architecture → Acceptance → Implementation`；Architecture 的待用户裁决面只保留 `D-ARCH` 与 `D-MIGRATION`。`ADR-BRIDGE-02`～`06` 被标为已决 Spec 输入／历史承载记录，不是隐藏附加投票项。
- Spec 工作树 current SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，状态为 `FINALIZED`。Acceptance 工作树 current SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`，状态为 `FINALIZED_ACCEPTANCE_ORACLE`。README 与 Implementation 均明确候选产品及完整 bridge 为 `UNVERIFIED`，未把文档定稿、局部 review、integration smoke 或局部 verify 外推为产品 `PASS`。
- Implementation 明确自称 living document；checkpoint、0 blocker／0 major、squash、归档或 merged-state review 均不使其收口，后续代码事实、评审、回放与部署状态变化仍须动态更新。
- Foundations worktree 当前为 clean `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。该 tip 不是 current `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1` 的祖先；`CHERRY_PICK_HEAD`、`MERGE_HEAD` 与 `REVERT_HEAD` 均不存在。Main index 只列 `README.md` 与 `implementation.md`，与“首次回放被 living docs index WIP 安全阻止，未进入 cherry／merge／revert 状态”一致。
- Nonstream `7ddf17364d97349638d44352bbd9a9b025723ccc` 的代码 R2 是 0 blocker／0 major且可 squash；独立 full-Spec verify 的 `FAIL` 仍有效，但仲裁已把 carrier F-1 定为组合排序依赖、usage F-2 定为后续 required gap，因此 checkpoint squash 与完整产品 `UNVERIFIED` 可以同时成立。组合顺序保持 foundations → carrier v2 → nonstream。
- Carrier v2 `8301ee938601ad86c7f72d313abc6c976a74b2a9` 为代码 R2 0 blocker／0 major且独立 verify R2 `PASS`；stream parser `73a6aa114647440262691651cd17e9127785c75a` 为代码 R2 0 blocker／0 major／0 minor；route policy `84a22c07db3923768db44a1314e5ae6d5aed2e98` 为 0 blocker／0 major且明确可 squash。四者现场 HEAD 与文档 source checkpoint identities 一致。
- README／Implementation 的 immediate 执行顺序一致：先形成仅含两份 living 文档的 checkpoint并清 index，再重新 gate current main与无 cherry state，随后按 `9e5f874… → cae83f4… → 6a00f6f…` 逐片回放 foundations并执行 main-side gates。该顺序没有被下游 happy／systemd 状态漂移改变。

## 事实性发现

[major] `README.md` 与 `implementation.md` 的 index blob — 当前 index 不是本轮评审的 current 工作树 bytes，直接提交会提交旧内容 — `README.md` 工作树 SHA-256 为 `2de36b12…`，index SHA-256 为 `3f48e6a3…`；`implementation.md` 工作树 SHA-256 为 `fe051644…`，index SHA-256 为 `8eb18f93…`，两者均 `equal=no`。虽然 index path 集合正确地只有这两文件，但 path 正确不等于 blob identity 正确 — 提交前只重新暂存这两份 current 工作树文档，再在同一 main gate 中复核 index SHA-256 分别等于上述稳定工作树 SHA-256、cached path 集合仍只有这两文件、`git diff --cached --check` 通过；不得直接提交当前旧 index，也不得夹带 `docs/tmp/**` 或其他 WIP。

[major] `implementation.md:11,26,51,64,66,190,211,229,232` — happy integration 的 current clean／gate 状态陈旧，不能作为 living truth source 直接执行 — 文档多处写 `integrate/260807-bridge-happy-path@d78b3cdc…` 为 clean、当前待 merged-state review＋独立 verify；现场 HEAD 仍为 `d78b3cdc172ecad42873a70f1df31438ecca1663`，但 worktree 已 dirty，修改 `src/app/anthropic/thinking/reasoning_carrier.py` 与 `tests/smoke/test_anthropic_responses_happy_path.py`。独立 verify 已对该 HEAD 给出本阶段 `PASS`，而 `docs/tmp/260807-review-code-happy-path.md:3-6,25` 已给出 0 blocker／1 major并明确当前不能放行四提交逐个回放；不存在 `260807-review-code-happy-path-r2.md`。文档的“尚待 review”掩盖了“review 已完成并发现 major，修复正在未提交工作树中”的 current gate — 先决定并冻结 happy 修复的提交身份，完成对应 R2 定向复评；随后把 Implementation 更新为实际 HEAD、clean／dirty 状态、review 1-major处置与 verify PASS 的并列范围，再复核 living bytes。不得把 dirty working tree、旧 `d78b3cd…` verify PASS 或 418 绿灯外推为 happy commits 已获回放放行。

[minor] `implementation.md:12,26,66,190,213,232` — systemd 状态仍停在“R3 0 major、下一门 R4”，但 R4 已落盘并绑定同一候选 HEAD — `docs/tmp/260807-review-code-systemd-runtime-r4.md:3-6,15,50` 已对 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 给出 0 blocker／0 major、精确三提交可 squash 回并，并保留 1 项 credentials 文档 minor；现场 systemd worktree clean且 HEAD 未漂移。该陈旧状态会让执行者重复 R4，但不改变本轮 immediate foundations 顺序 — 同步为“R4 0／0、可 squash 回并；未部署，安装／manager／生产 `4141` 仍由部署门独立约束”，并保留 R4 的 1 minor，删除“下一步只做 R4”的旧动作。

## 主观建议

未提出。用户要求本轮只做机械核对。

## 结论与复评门

当前不能诚实给出“0 major、两文件可直接作为 living checkpoint 提交”的 verdict。两份工作树文档的长期边界和 immediate foundations 顺序正确，但提交身份与 happy current gate 尚不一致。关闭两项 major后进行窄复评，至少机械确认：连续两次工作树 hash 仍稳定；index blobs等于被评审工作树 blobs且 cached paths 仅为两份 living 文档；happy HEAD／status／review disposition已同步；systemd R4已同步；Spec／Acceptance／产品 `UNVERIFIED`、Implementation living 不收口、foundations 未入 main及“先 docs checkpoint、再 foundations回放”均未回归。若该复评为 0 blocker／0 major，则可明确提交两文件作为 living checkpoint；该 verdict只放行 checkpoint与后续实施，不表示 Implementation 定稿、happy放行、foundations 已进 main或完整 bridge产品 `PASS`。
