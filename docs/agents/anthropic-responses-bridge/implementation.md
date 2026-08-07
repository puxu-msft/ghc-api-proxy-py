# Anthropic Messages ↔ OpenAI Responses bridge 实施状态与动态收敛计划

## 文档状态

- **用途与状态**：本文是 Implementation living document，记录正式规格进入实现后的渐进切片、评审门、待修项、下一最小切片、并行开发线与本地分支收敛策略。开始开发不等于本文收口；一次提交也只是可追溯 checkpoint，不把本文转成只读历史快照。
- **事实快照**：2026-08-07。主仓为 `/home/xp/src/ghc-api-proxy-py`，当前 `main` HEAD 为 `ec5e8f5240c6a587544e022b449aa7b392ba7ca1`。本轮取证的每次 shell 调用均在同一调用开头验证物理 repo root、分支 `main`、`HEAD == refs/heads/main` 与精确 HEAD `ec5e8f5240c6a587544e022b449aa7b392ba7ca1`；未来 `main` 经有意回放前进后，living plan 必须先记录新锚点，再以新锚点建立下一轮 gate，不得把本快照冒充未来 HEAD。
- **权威边界**：[规格](spec.md)是唯一行为 oracle；任何 required behavior 与 policy-dependent expected 只能来自 Spec。2026-08-07 carrier 双格式重裁已由 [carrier 双格式定向评审](../../tmp/260807-review-spec-carrier-dual-format.md)给出 blocker 0、major 0、minor 0，Spec 源文档现已恢复 `FINALIZED`，current SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。Implementation 不得自行改写该双格式合同。[独立验收规范](acceptance.md)只把 Spec 合同转成可执行 gate，不得自行补充 expected；current Acceptance 已绑定 Spec `5e362822…`、重做 route／request／response／buffering／retry／lifecycle／limits 七域 policy 对账，并恢复 `FINALIZED_ACCEPTANCE_ORACLE`，current SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。[Spec／Acceptance current 联合终审](../../tmp/260807-review-spec-acceptance-current.md)与其直接消费的 [Spec current-byte 终审](../../tmp/260807-review-spec-carrier-final.md)、[Acceptance current-byte 终审](../../tmp/260807-review-acceptance-dual-carrier.md)均确认 current 双 carrier 内容为 0 blocker／0 major并可继续实施；Acceptance 对不可恢复 READY 中间快照的 provenance 自述只剩 1 minor，current 放行依据固定为直接绑定最终 bytes 的报告，不再等待缺失的 `787b5c38…` 中间报告。候选产品及完整 bridge 始终为 `UNVERIFIED`。[目标架构](architecture.md)仅是非规范实现参考；`D-ARCH`／`D-MIGRATION` 未经用户接受前不产生 behavior 或 expected。[研究](research.md)保留来源、可移植机制与不可照搬项，不是行为或验收 oracle。
- **更新纪律**：本文必须随代码事实、独立评审、main 回放、并行线合并、新发现与计划调整持续更新；每次更新都绑定当时可复验的 commit、worktree、报告或 gate，不把计划中的动作写成已实现事实。状态变化先更新对应切片／开发线与下一步，再同步汇总；过时结论保留其历史绑定或明确降级，不冒充 current verdict。
- **评审语义**：本文某一内容身份取得 blocker 0、major 0，只表示在该轮范围内没有已知阻断项、可以继续实施或形成 checkpoint commit；不表示 Implementation 已定稿、实施已完成、后续不再修改，也不替代新代码、新组合态和新文档 bytes各自所需的复评。后续事实或发现改变本文时，living document 应继续修订，并对新增或改写内容执行相称的定向复评。
- **当前 foundations 与主树回放状态**：reasoning carrier baseline 仍由 `ed77c9d191df81c451c25161420515cca52ce6a4` 承载，正式 Spec／Acceptance 文档提交 `ec5e8f5240c6a587544e022b449aa7b392ba7ca1` 已在其后进入 `main`；原 reviewed HEAD `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b` 继续由 `archive/260806-anthropic-responses-reasoning` 保留。完整 foundations 组合源仍是 clean worktree `/home/xp/src/ghc-api-proxy-py-integrate-bridge` 的 `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79`，恰有三个线性 squash commits `9e5f874d5b547bd9d733b0ee134e165f818de205`（reasoning cardinality）、`cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`（session liveness）和 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`（request converter）。[merged-state 代码 R2](../../tmp/260806-review-code-bridge-foundations-r2.md)为 blocker 0、major 0，[独立复验 R2](../../tmp/260806-verify-bridge-foundations-r2.md)为范围内 `PASS`，[integration commits 只读回放预检](../../tmp/260807-audit-integration-commits.md)为 blocker 0、major 0。首次回放已被主树 living docs index WIP 的机械门阻止，未进入任何 cherry-pick、merge 或 revert 状态，`CHERRY_PICK_HEAD`／`MERGE_HEAD`／`REVERT_HEAD` 均不存在，也未产生产品提交。必须先形成只含 current `README.md` 与本文的文档 checkpoint、清空该 index 阻断，再从 `9e5f874…` 开始逐片回放；任何 integration 侧 verdict 都不得外推为完整 bridge 产品 `PASS`。
- **当前 source checkpoints、happy integration 与 usage 后继线**：Non-stream `7ddf17364d97349638d44352bbd9a9b025723ccc` 的[代码 R2](../../tmp/260807-review-code-nonstream-response-r2.md)为 0 blocker／0 major、骨架可 squash；[carrier 依赖仲裁](../../tmp/260807-arbitrate-nonstream-carrier-dependency.md)已明确允许该 checkpoint 收敛，并把 carrier F-1 裁定为组合排序依赖而非 converter major，固定顺序为 foundations → carrier v2 → nonstream。Stream parser `73a6aa114647440262691651cd17e9127785c75a` 的[代码 R2](../../tmp/260807-review-code-stream-parser-r2.md)为 0 blocker／0 major／0 minor；Carrier v2 `8301ee938601ad86c7f72d313abc6c976a74b2a9` 的[代码 R2](../../tmp/260807-review-code-carrier-v2-r2.md)为 0 blocker／0 major且[独立 verify R2](../../tmp/260807-verify-carrier-v2-r2.md)为 `PASS`；Route policy `84a22c07db3923768db44a1314e5ae6d5aed2e98` 的[代码评审](../../tmp/260807-review-code-route-policy.md)为 0 blocker／0 major、明确可 squash。四片已在 clean worktree `/home/xp/src/ghc-api-proxy-py-integrate-happy` 形成以 foundations tip 为 base 的 `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443`，当前线性 commits 为 carrier `1ed13ad` → nonstream `80b3cfa` → stream parser `c950912` → amended route／smoke `7e4b642`。[merged-state code review R1](../../tmp/260807-review-code-happy-path.md)绑定 amend 前 `d78b3cd…`，产品行为未发现 blocker／major，但组合 smoke 的 carrier expected 与产品 codec 同源，故给出 1 major；该测试判别力缺口已在 `7e4b642…` 中修复，current worktree clean，尚无 R2 报告，四提交在 R2 达到 0 blocker／0 major 前不得回放 `main`。[独立 verification](../../tmp/260807-verify-happy-path.md)绑定 `d78b3cd…` 并给出本阶段 `PASS`，该阶段结论不替代 amended bytes 的 R2，也不外推为完整产品 `PASS`。Non-stream usage required 后继线已在 clean `/home/xp/src/ghc-api-proxy-py-nonstream-usage` 形成 `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857`，其 parent 精确为 `7e4b642…`，当前待独立 review，不得先于 happy 四提交进入 `main`。
- **当前 systemd 与部署文档状态**：Systemd clean source 候选为 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`。[代码 R4](../../tmp/260807-review-code-systemd-runtime-r4.md)给出 0 blocker／0 major、1 个非阻断 credentials 文档 minor，并明确 source 的 `66551e45… → 1a220e04… → 49fb198…` 三提交可 squash 回并。Clean `/home/xp/src/ghc-api-proxy-py-integrate-systemd` 已形成以 current `main@ec5e8f5…` 为 parent 的单一准备提交 `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef`；它尚未进入 `main`，且代码 R4 与 squash 准备均不表示已安装、已部署或已接管 `4141`。Service-cutover plan、systemd-runtime plan 与 readiness 保持 living 和 `NO_CUTOVER`，后续每次上游身份变化仍须重绑。当前替代目标保持为本项目 Python bridge＋systemd runtime 受控接管 `/home/xp/src/copilot-api-js` Bun 现服承担的前门；cutover 前必须重取 `localhost:4141` owner、fence `--restart` parent／listener child、避免双 owner 并禁止触碰独立 `cc-daemon` 生命周期。任何部署文档或代码评审 0／0只放行继续准备，不授权安装、部署或切换。
- **证据边界**：`docs/tmp` 报告只绑定各自写明的文档内容身份或代码 HEAD，不是长期状态真相源。本文只保留 verdict、仍有效的 gate 与裁决结果，不复制复现细节或长探针输出。后续新建报告使用实际创建日的 `YYMMDD-` 前缀，同一对象复评追加 `-rN` 且不覆盖旧轮次；既有无日期前缀或 `260806-` 报告保持原名。

### 评审 major 处置

Latest [Implementation stable checkpoint 定向复评](../../tmp/260807-review-implementation-checkpoint.md)给出 blocker 0、major 1，指出上一稳定快照未同步 happy R1／verification、systemd R4 与两个后继 worktree；更早的 [Implementation R2](../../tmp/260807-review-implementation-current-r2.md)及 [living-plan 定向评审](../../tmp/260807-review-implementation-living-plan.md)所指出的前序状态缺口已关闭。以下处置均已落入本文，但不把本次自述冒充新的独立复评 verdict；本文新 bytes 仍须定向复评：

| Major | 本次处置 | 复评门 |
|---|---|---|
| Implementation R3 M1：Spec／Acceptance 阶段状态陈旧 | **历史处置，已被 2026-08-07 carrier 重裁再次取代。** 当轮曾同步 Spec `FINALIZED` 与 Acceptance R7；current 状态以本表末行、顶部权威边界和“文档复评剩余项”为准 | 历史行不得作为 current 执行依据；后续每次 Spec bytes 变化都必须传播到 Acceptance 绑定与本文状态 |
| Implementation R3 M2：遗漏完整三片 integration branch | 把 amend 后的 `integrate/260806-bridge-foundations@6a00f6f…`、三个线性 commits、clean worktree、代码 R2 0／0与 verification R2 PASS 写入状态真相源；把旧 `8e9aef6…` 降为历史 liveness 载体 | 后续只消费现有三提交链，不再重复组合；tip 尚未进入 `main`，archive 仍指 reviewed feature HEAD，共享 integration 整链清理门不放宽 |
| Implementation R4 M1：Acceptance R6 旧 Architecture 快照被无条件汇总为 current verdict | **历史处置。** Acceptance 当时绑定 Architecture `6de919…` 并重做七域 manifest，R7 对当时文件终审为 0／0；current Spec 后续已发生 carrier 重裁 | R7 不得外推为 current Acceptance 或产品 `PASS`；Spec／Architecture／Acceptance 内容变化时须重新绑定并复评 |
| Implementation R5 M1：本文未同步 Acceptance R7 已完成状态 | **历史处置。** R7 当时的 0／0已同步；current Spec 后续发生 carrier 双格式重裁，故该 verdict 不再覆盖 current Spec／Acceptance 内容对 | 保留为历史评审链，不得据此跳过 current Acceptance 重绑与复评 |
| Living-plan review M1：Spec carrier 重裁后状态陈旧 | Carrier 定向评审已为 0／0／0，Spec 已恢复 `FINALIZED@5e362822…`；Acceptance 已重绑并恢复 finalized。随后 current-byte Spec／Acceptance 联合终审与两份直接终审均为 0／0，已取代不可恢复 READY 中间快照的自述 | 本文新 bytes仍须复评；current 实施依据使用直接绑定 Spec `5e362822…`／Acceptance `224b020d…` 的终审，不再等待缺失中间报告 |
| Implementation current R2 M1：living 状态落后于 Plan／source／systemd／happy integration | **历史处置，已被 stable checkpoint 复评再次取代。** 当轮同步了 Plan R10、source reviews、systemd R3 与 happy `d78b3cd…` 基础状态 | 历史行不得作为 current 执行依据；current 身份与 gate 以本表末行、顶部状态和“下一步”为准 |
| Implementation stable checkpoint M1：遗漏 happy R1／verification、systemd R4 与后继活动线 | 已同步 happy current `7e4b642…`、R1 major 已修待 R2、verification 阶段 `PASS`；systemd R4 0 major 与 prepared squash `fe9c203…`；usage `aca3ced…` 基于 `7e4b642…` 待 review；并把 Plan 更新到 R11 0／0／0 | 本文新 bytes 须定向复评；只有取得 0 blocker／0 major 才可形成 README＋Implementation checkpoint。该 verdict 只清 index 并放行后续实施，不表示 living 收口或产品 `PASS` |

此前 `docs/tmp` 归纳评审的 5 项 major 处置也随最新 merged-state 结论重新对账：

| Major | 当前处置 | 事实边界 |
|---|---|---|
| M1 Reasoning cardinality 状态缺失 | **已关闭** | `b876e626dda821b267535b0bcffc9d81ced12763` 已独立评审为 blocker 0、major 0、可 squash；分支／worktree clean，提交尚未进入 `main` |
| M2 Liveness 状态停在待 R3 | **已关闭** | reviewed HEAD `f27a8c04cd3470bd50d7194a30371ca5404f727e` 的 R3 为 0／0、可 squash；current 完整 integration 链使用 `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`，旧 `8e9aef69cc8606c4ca25286da617da8fc74d5c55` 仅为历史净补丁载体，二者均尚未进入 `main` |
| M3 Request 状态停在父提交 | **已关闭** | 最新 reviewed HEAD `fdd2f75fcec11e592b04f2686c4664262052a964` 的 R3 为 0／0、可 squash；父提交 `028f1f2…` 的行为 PASS 不冒充最新 HEAD 的独立放行，最新 HEAD 尚未进入 `main` |
| M4 文档复评汇总陈旧 | **再次动态同步并关闭 current 内容门** | Spec `FINALIZED@5e362822…` 与 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d…` 已由直接绑定 current bytes 的独立终审确认为 0 blocker／0 major，可继续实施。Acceptance 的 READY 中间 provenance只剩 minor；产品仍为 `UNVERIFIED`，本文不把文档 0／0或局部 smoke外推为产品状态 |
| M5 临时报告跨日期命名合同未形成仓库级载体 | **命名合同已承载；Plan R8 历史关闭 R7 阻断，current R11 保持 0 major** | 文档重组 Plan 第 2.5 节已承载实际创建日 `YYMMDD-`、历史报告单一身份与禁止覆盖合同；R11 确认 Plan bytes 自 R10 未变化，generation 0A、post-cut、42 owner 与 living 开放状态未回归。已有 `260806-` 报告及用户明确指定的历史路径不批量改名 |

## 总体进度

| 顺序 | 切片 | 候选／集成 HEAD | 当前 gate | 下一动作 |
|---|---|---|---|---|
| 1 | Reasoning carrier baseline | `main` `ed77c9d191df81c451c25161420515cca52ce6a4` | **已 squash；原 reviewed HEAD 已归档** | 保持既有 archive ref，不移动或 force-update |
| 2 | Reasoning cardinality correction | reviewed `b876e626dda821b267535b0bcffc9d81ced12763`；integration `9e5f874d5b547bd9d733b0ee134e165f818de205` | 完整 foundations 链首提交；merged-state代码R2 0／0、verification R2范围内PASS；回放被living docs index机械阻止，尚未进入`main`且无cherry state | 先提交README＋Implementation checkpoint清index，再回放`9e5f874…`并执行cardinality main-side gate |
| 3 | Session liveness | reviewed `f27a8c04cd3470bd50d7194a30371ca5404f727e`；integration `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` | 完整 integration 链第二提交；merged-state 代码 R2 0／0、verification R2 范围内 PASS；尚未进入 `main` | 只在前片 main gate 通过后回放 `cae83f4…`，执行 liveness main-side gate，再归档 reviewed HEAD |
| 4 | Request converter | reviewed `fdd2f75fcec11e592b04f2686c4664262052a964`；integration `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | 完整 integration 链第三提交／tip；merged-state 代码 R2 0／0、verification R2 范围内 PASS；尚未进入 `main` | 只在前两片 main gate 通过后回放 `6a00f6f…`，执行 request 与跨片 main-side gate，再归档 reviewed HEAD |
| 5 | Non-stream response checkpoint | `7ddf17364d97349638d44352bbd9a9b025723ccc` | 代码R2 0／0；仲裁允许checkpoint squash，carrier F-1固定为carrier-first组合依赖，usage detail仍后补 | Foundations进入main后按carrier v2 → nonstream顺序消费；组合gate不得替代完整non-stream验收 |
| 6 | Stream parser checkpoint | `73a6aa114647440262691651cd17e9127785c75a` | 代码 R2 为 0 blocker／0 major／0 minor，semantic-facts 骨架可 squash | 尽快 squash／归档；随后补完整 grammar、framing、strict lifecycle、refusal与 production sequencer接线 |
| 7 | Reasoning carrier v2 checkpoint | `8301ee938601ad86c7f72d313abc6c976a74b2a9` | 代码R2 0／0、独立verify R2 `PASS`；可squash | Foundations进入main后先于nonstream消费并执行项目主v1组合gate；后续malformed／foreign／echo边界仍继续 |
| 8 | systemd／cgroup runtime checkpoint | source `49fb1988621bba4356e7a5039a6994c2e6d19604`；prepared squash `fe9c20315b0137ca5b2253fdbd86a30d504255ef` | 代码 R4 为 0 blocker／0 major；单一 squash 已基于 `main@ec5e8f5…` 准备且 clean；未进入 `main`、未部署 | 排在 usage 之后回放；执行 current-main identity／定向／全仓／Ruff／Pyright gate，通过后归档 source。安装与 cutover 仍由部署门独立约束 |
| 9 | Route policy checkpoint | `84a22c07db3923768db44a1314e5ae6d5aed2e98` | 代码评审0 blocker／0 major、明确可squash | Foundations进入main后消费；完整route handler／transport接线继续后补 |
| 10 | Four-checkpoint happy integration | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | Carrier → nonstream → parser → amended route／smoke 四个线性 commits；R1 唯一 major 已修，待 R2；verification 阶段 `PASS`；clean | R2 达到 0／0 后才按四提交顺序回放 current `main`，逐片 main gate并归档对应 reviewed source；不得外推为完整产品 `PASS` |
| 11 | Non-stream usage details | `aca3ced6e38efabf13ffe43d5935697801c74857` | 单提交 clean 后继，parent 为 happy `7e4b642…`；required usage details 已形成候选；待 review | Happy 四提交进入 `main` 且逐片 gate 通过后，先完成独立 review，再回放 usage、执行 main gate并归档 source |

本地收敛顺序固定为reasoning cardinality correction → liveness → request converter。串行组合已经在`integrate/260806-bridge-foundations@6a00f6f…`完成并通过代码R2与verification R2，回放预检又以0 blocker／0 major冻结stable patch-id／tree／diff与逐片blob身份。后续重点是先完成README＋Implementation current-byte复核与checkpoint、解除主树living index阻断，再按审计报告绑定身份把现有三个语义提交逐个回放`main`并逐片执行main-side gate；不得重新组合第二条integration链。Request与cardinality同改`src/app/anthropic/thinking/responses_reasoning.py`，因此每次回放后仍须机械确认cardinality的有序block-list API、upstream v1合法主路径兼容、typed malformed止血及跨片production-chain回归均保持；不得把旧“全malformed Node byte-exact”范围重新带回current gate。

### 当前并行开发线

| 开发线 | Worktree／branch | 建树基线 | 当前事实 | 更新与进入条件 |
|---|---|---|---|---|
| Non-stream response | `/home/xp/src/ghc-api-proxy-py-response`；`feat/responses-anthropic-nonstream` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `7ddf173…`；代码R2 0／0、骨架可squash；仲裁允许checkpoint收敛 | 固定依赖carrier v2先进入组合；usage reasoning detail后补并重验，完整产品仍为`UNVERIFIED` |
| Stream parser | `/home/xp/src/ghc-api-proxy-py-stream-parser`；`feat/responses-stream-parser` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `73a6aa1…`；代码 R2 0／0／0，骨架可 squash | 尽快 squash／归档；完整 grammar／framing／strict lifecycle与 sequencer接线作为后续切片继续 |
| Reasoning carrier v2 | `/home/xp/src/ghc-api-proxy-py-carrier-v2`；`feat/reasoning-carrier-v2` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `8301ee9…`；代码R2 0／0、verify R2 `PASS`、可squash | Foundations后先消费；nonstream必须依赖本片的项目主v1 producer，后续兼容边界继续 |
| Non-stream usage details | `/home/xp/src/ghc-api-proxy-py-nonstream-usage`；`feat/nonstream-usage-details` | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | `aca3ced…`；单提交、clean；待独立 review | 不重复建线；happy R2 与四片 main gates通过后再消费，随后执行 usage main gate并归档 |
| systemd／cgroup runtime | `/home/xp/src/ghc-api-proxy-py-systemd`；`feat/systemd-cgroup-runtime`；`/home/xp/src/ghc-api-proxy-py-integrate-systemd`；`integrate/260807-systemd-runtime` | source 基于 `ed77c9d…`；squash 基于 `ec5e8f5…` | source `49fb198…` code R4 0／0；prepared squash `fe9c203…` clean；未进入 `main`、未部署 | 排在 usage 后回放 `fe9c203…`；main gate 通过后归档 source。真实 manager／cgroup与运行态安装继续后补 |
| Route policy | `/home/xp/src/ghc-api-proxy-py-route-policy`；`feat/anthropic-responses-route-policy` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `84a22c0…`；评审0／0、明确可squash | Foundations后消费；route handler／transport／History完整接线继续后补 |
| Happy integration | `/home/xp/src/ghc-api-proxy-py-integrate-happy`；`integrate/260807-bridge-happy-path` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `7e4b642…`；四个线性 commits、clean；R1 major已修待R2；verification阶段 `PASS` | R2 0／0 后按现有链回放；不得重建第二条 happy 组合链 |

Source checkpoints 均已关闭当前声明范围的 0 major：carrier v2 另有独立 verify `PASS`，nonstream 仲裁允许 checkpoint squash并冻结 carrier-first 组合依赖，stream parser与route policy均可squash。Happy integration 已 amend 为 clean `7e4b642…`；R1 的同源 carrier oracle major 已在 current bytes 修复，verification 对 amend 前产品状态给出阶段 `PASS`，但 current 四提交仍须 R2 0／0后方可回放。Usage 后继 `aca3ced…` 已基于 `7e4b642…` 形成并待 review。Systemd source `49fb198…` 已获 R4 0 major，single squash `fe9c203…` 已准备。后补边界不因 checkpoint、组合绿灯或 squash 准备取消。Non-stream、stream parser、carrier v2、route policy与usage均建立于尚未进入`main`的 foundations／happy 链，落`main`前仍须按 README＋Implementation checkpoint → foundations → happy → usage 的顺序消费；systemd随后独立回放。任何代码收敛都不授权停止现服、安装unit或抢占`4141`。

### 增量开发风格

当前开发节奏明确采用：**先建立结构骨架，完成 happy path 与 smoke，形成单一可评审提交；独立 review 通过后尽快 squash／归档；随后按 Spec／Acceptance 继续补齐边界、失败路径、正反控制与组合态接缝。** 这一节奏把小而清晰的 checkpoint 与完整产品验收分开，避免五线相互等待，也避免把长期 WIP 堆成一个不可审查的大提交。“后补边界”是后续必做阶段，不是删除或降级已接受需求；任何 checkpoint 的报告与提交说明都必须列明未覆盖边界，产品在完整 required gates 通过前保持 `UNVERIFIED`。Non-stream 的代码 0／0与独立验收 `FAIL` 可以同时成立：前者放行声明范围骨架 squash，后者继续约束 carrier依赖仲裁与 usage detail后补，不能互相覆盖。

## 切片 1：Reasoning carrier 与 cardinality correction

### Git 快照

| 字段 | 值 |
|---|---|
| Main integration commit | `ed77c9d191df81c451c25161420515cca52ce6a4` |
| Archived reviewed HEAD | `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b` |
| Archive ref | `archive/260806-anthropic-responses-reasoning` |
| Anchor | `47d9ef101c4b81ac70d805b1da157b34d021d33d` |
| 变更路径 | `src/app/anthropic/thinking/responses_reasoning.py`；`tests/unit/test_responses_reasoning.py` |

归档 ref 精确指向 R2 复评通过的原候选 HEAD；活动 `feat/anthropic-responses-reasoning` 分支与 reasoning worktree 已退出活动集合。`main` 上不保留原分支的两提交形状，而以一个 squash commit 表达该切片。

### 评审结论与当前动作

[Reasoning R2 复评](../../tmp/260806-review-code-reasoning-r2.md)绑定原候选 HEAD，随后其净改动以 `ed77c9d191df81c451c25161420515cca52ce6a4` squash 到 `main`。后续[reasoning aggregation 裁决](../../tmp/260806-arbitrate-reasoning-aggregation.md)区分了必须保留的 upstream-compatible carrier wire／逐 block reverse primitive与必须修正的 forward 聚合语义；旧 R2 的代码事实保留，但“聚合行为即目标 oracle”的终局判断已被推翻。

Cardinality 修复位于 clean 分支 `fix/reasoning-cardinality` 的 `b876e626dda821b267535b0bcffc9d81ced12763`，其 parent 正是 `ed77c9d…`，只改 `src/app/anthropic/thinking/responses_reasoning.py` 与 `tests/unit/test_responses_reasoning.py`。[独立代码评审](../../tmp/260806-review-code-reasoning-cardinality.md)给出 blocker 0、major 0、明确可 squash：每个 reasoning item 产生自己的有序 thinking block，保留 non-empty encrypted-only payload，并保持固定 carrier bytes与逐 block reverse。该提交尚未进入 `main`；最终回并后应新建 `archive/260806-anthropic-responses-reasoning-cardinality` 精确指向 `b876e62…`，不得移动既有 reasoning archive。

## 切片 2：Session liveness

### Git 快照

| 字段 | 值 |
|---|---|
| Worktree | `/home/xp/src/ghc-api-proxy-py-liveness` |
| Branch | `feat/session-liveness` |
| Anchor | `47d9ef101c4b81ac70d805b1da157b34d021d33d` |
| HEAD | `f27a8c04cd3470bd50d7194a30371ca5404f727e` |
| Status | clean |
| Review state | [R3](../../tmp/260806-review-code-liveness-r3.md) blocker 0、major 0，可 squash |
| 变更路径 | `src/app/streaming/keepalive.py`；`tests/unit/test_streaming_resilience.py` |

当前 reviewed HEAD 在原两提交后追加 `f27a8c04cd3470bd50d7194a30371ca5404f727e`（preserve liveness cleanup failures）。该分支基于 reasoning squash 之前的旧 anchor，不能把原三提交链直接视为组合状态。

### 评审结论与 integration 状态

[Liveness R2 复评](../../tmp/260806-review-code-liveness-r2.md)在旧 HEAD 上给出的两项 major，已经由 R3 在 `f27a8c0…` 上逐条关闭：

1. **cleanup 会被第二次 cancellation 截断。** 第一次取消已经进入 pull settle／iterator close 流程后，第二次取消可在资源归零前终止 cleanup，导致 upstream `finally` 未完成并跳过后续显式 close。
2. **cleanup 异常覆盖 primary 退出原因。** `aclose()` 的 secondary `RuntimeError` 会覆盖正在传播的 client cancellation 或 upstream `ValueError`，从而丢失真实终止原因；只有不存在 primary failure 时，close failure 才应成为最终异常。

旧 clean worktree `/home/xp/src/ghc-api-proxy-py-integrate-liveness` 的分支 `integrate/260806-session-liveness` 保留单一 commit `8e9aef69cc8606c4ca25286da617da8fc74d5c55`；它曾证明 liveness 净补丁与 reviewed candidate 对账，但现在只作为历史载体。Current 组合源是 `/home/xp/src/ghc-api-proxy-py-integrate-bridge` 上完整线性链的第二提交 `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`，其 parent 为 `9e5f874…`，后继为 `6a00f6f…`。后续不得从 `8e9aef6…` 再建第二套组合链；应直接在 docs 提交后把 `cae83f4…` 作为第二片回放到已含 `9e5f874…` 的 current `main`，并重新执行 main-side liveness 与前序 cardinality gate。

**验收判据**：后续 cancellation 不得截断资源清理；primary cancellation／upstream error 保持最终可见；secondary close failure被观察并记录但不覆盖 primary；正常退出时的 close failure仍显式传播；所有退出路径中 active pull、generator frame 与底层 iterator 都归零且 close 至多一次。

**风险与回滚**：shield 或 cleanup task 若错误吞掉 cancellation，会造成 shutdown 延迟或 orphan task；若只保留 primary 而不观察 secondary，会重新引入 task warning。组合 gate 失败时不得改写 R3 报告绑定的 reviewed HEAD；在新 integration 基线上修复并重新评审。Liveness 进入 `main` 且 main-side gate 通过后，先创建 `archive/260806-anthropic-responses-liveness` 精确指向 `f27a8c0…`，再清理其 clean feature worktree／branch。共享 integration worktree／branch 此时仍须保留；只有 cardinality、liveness、request 三个组合提交全部进入 `main` 且三片 main-side gate 全绿后才可清理。

## 切片 3：Request converter

### Git 快照

| 字段 | 值 |
|---|---|
| Worktree | `/home/xp/src/ghc-api-proxy-py-request` |
| Branch | `feat/anthropic-responses-request` |
| Integrated base | `ed77c9d191df81c451c25161420515cca52ce6a4` |
| HEAD | `fdd2f75fcec11e592b04f2686c4664262052a964` |
| Status | clean |
| Review state | [R3](../../tmp/260806-review-code-request-r3.md) blocker 0、major 0，可 squash；R2 行为复验 PASS 绑定父提交 `028f1f2…` |
| 相对 current main 的变更路径 | `src/app/anthropic/thinking/responses_reasoning.py`；`src/app/protocols/anthropic_responses.py`；`tests/unit/test_anthropic_responses_request.py` |

request 切片基于 reasoning squash：`cb286059b656d960225c2afff84f204b9123810d` 为 converter 语义提交，`028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 为首轮四项 major 的 hardening，`fdd2f75fcec11e592b04f2686c4664262052a964` 关闭 R2 新发现的 unknown／explicit-unbounded reasoning limits 混淆。旧候选 `f8a11ad3…` 与父提交 `028f1f2…` 的报告都只绑定各自 HEAD，不能替代 R3 对最新 HEAD 的结论。

### 评审结论与待修项

[Request converter 代码评审](../../tmp/260806-review-code-request-converter.md)在旧 HEAD 上给出 blocker 0、major 4：

1. **Thinking capability conversion 缺失。** 旧 HEAD 把顶层 `thinking` 一律作为 unsupported field 拒绝；正式 [Spec](spec.md) 要求 enabled／adaptive 经模型 capability 与 budget gate 映射为 Responses `reasoning`，disabled／absent 省略，unsupported capability 产生稳定 capability error。
2. **缺少 request-scoped 双向 tool-name mapper。** 旧 HEAD 没有让声明、assistant 历史 `tool_use`、forced named choice 与未来 response restore 共享同一原子映射，非法 Responses tool name 会原样穿过。
3. **Malformed carrier codec 与当时固定 Node 合同不兼容。** 旧 HEAD 对若干 non-canonical／Unicode payload 产生错误差分，其中非 ASCII 输入会泄漏裸 `ValueError`；该轮当时的合同要求固定 Node codec 语义与稳定 typed outcome。2026-08-07 carrier 重裁已把 Node 范围收窄为 upstream v1 合法主路径 compatibility consumer，不再要求所有 malformed 边界逐字节一致；current expected 以恢复 `FINALIZED` 的双格式 Spec 为准。
4. **Unknown declared field gate fail open。** 旧 HEAD 的 allowlist 动态取自 Pydantic `model_fields` 且只检查 `model_extra`；共享模型未来正式声明新字段后，converter 可能静默丢弃。目标合同要求 converter 自身维护静态 consumed-field 合同，并对 `model_fields_set ∪ model_extra.keys()` fail closed。

[Request converter 独立验收](../../tmp/260806-verify-request-converter.md)在旧 HEAD 上给出 `FAIL`。其中 malformed Unicode carrier 泄漏裸 `ValueError` 与第 3 项 major 是同一缺陷族。报告原列的 server-tool F1 已由后续独立裁决撤销，不再是实现缺陷。

### Server-tool 裁决

[Server-tool 合同裁决](../../tmp/260806-arbitrate-server-tool-contract.md)已经定案：**reject 成立**。Anthropic typed／server tool 在本项目继续以稳定 `server_tool_not_supported` 显式拒绝；不得映射为 Responses hosted builtin，也不得把另一个项目的专用 WebSearch 合同当作本项目 oracle。

处置结果固定为：

1. `260806-verify-request-converter.md` 的 F1 记为“已撤销／oracle 不适用”，不据此改代码或测试，也不重写该历史报告。
2. R2 复评与重新验收只处理其余有效发现，并明确以主仓当前 Spec 的 no-revive 合同为 expected。
3. 未来若要支持 Responses hosted server tools，必须先形成独立产品规格与用户裁决，完整覆盖 request、response、stream lifecycle、History／continuation、error 与 capability gate；不得从 converter 映射表增量偷渡。

### 当前 squash gate

[Request R2 代码复评](../../tmp/260806-review-code-request-r2.md)在 `028f1f2…` 上关闭首轮四项 major，但新增 1 major：unknown budget limits 与明确无界被混同；同 HEAD 的[独立行为复验](../../tmp/260806-verify-request-r2.md)为 PASS。[Request R3](../../tmp/260806-review-code-request-r3.md)已在 `fdd2f75…` 上确认该 major 关闭，结论为 blocker 0、major 0、可 squash。

完整 integration 链已经在第三提交 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 中把 request converter 合到 cardinality＋liveness 基线上，没有用 request 分支的旧整文件覆盖 `responses_reasoning.py`。[merged-state 代码 R2](../../tmp/260806-review-code-bridge-foundations-r2.md)确认两个新增 major 已关闭、可按三个现有 squash commits 回放；[独立复验 R2](../../tmp/260806-verify-bridge-foundations-r2.md)确认空 content-list typed reject与真实 forward→`MessagesRequest`→public converter 的 $N \rightarrow N$ reasoning 接缝范围内 `PASS`。这些证据绑定 integration `6a00f6f…`，不替代回放后的 current main gate；第三片 main-side gate 通过后创建 `archive/260806-anthropic-responses-request` 精确指向 reviewed `fdd2f75…`，再清理活动 feature 分支／worktree。

## 文档复评剩余项

| 文档 | 最新报告 | 当前剩余项 | 下一报告 |
|---|---|---|---|
| [Spec](spec.md) | [current-byte 终审](../../tmp/260807-review-spec-carrier-final.md)；[Spec／Acceptance 联合终审](../../tmp/260807-review-spec-acceptance-current.md) | Current `FINALIZED@5e362822…` 为 blocker 0、major 0，可继续实施 | 作为 current 行为 oracle继续实施；该 0／0不证明候选实现符合 |
| [Architecture](architecture.md) | 技术 [R3](../../tmp/260806-review-bridge-architecture-r3.md)；[裁决矩阵终审](../../tmp/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审为 blocker 0、major 0，确认 Architecture 已具备用户裁决条件；它仍是非规范提案、不是 ADR，`D-ARCH`／`D-MIGRATION` 尚待用户完整阅读后亲自裁决 | 用户接受前 Architecture 不产生 expected；终审 0／0不替代用户裁决 |
| [Acceptance](acceptance.md) | [current-byte 终审](../../tmp/260807-review-acceptance-dual-carrier.md)；[Spec／Acceptance 联合终审](../../tmp/260807-review-spec-acceptance-current.md) | Current `FINALIZED_ACCEPTANCE_ORACLE@224b020d…` 为 blocker 0、major 0；不可恢复 READY 中间 provenance只剩 1 minor，最终 bytes已有直接独立证据；产品继续 `UNVERIFIED` | 按 current required gates实施；后续清理中间 provenance时不得把文档 0／0外推为产品 `PASS` |
| [Research](research.md) | [外部变化只读复核](../../tmp/260807-review-research-external-change.md) | blocker 0、major 0；current Research 可提交，route 作用域只覆盖 Anthropic `/v1/messages` bridge，不改变 native Responses 公共入口 | 无待修；Research 始终不产生 behavior expected |
| [文档重组计划](../documentation-restructure/plan.md) | current [独立定向终审 R11](../../tmp/260807-review-doc-migration-plan-r11.md) | R11 为 blocker 0、major 0、minor 0；确认 Plan bytes 自 R10 未变化，generation 0A、post-cut、42 owner与living开放状态均未回归 | 可继续执行并保持 living；不表示文档迁移收口，后续 identity／generation／certificate／action 漂移仍按 Plan 自身 gate 重判 |
| [Service cutover plan](../service-cutover/plan.md)／[systemd runtime plan](../systemd-runtime/plan.md)／[readiness](../service-cutover/readiness.md) | 各自 current living 修订；历史报告继续按绑定 bytes 保留 | Implementation 已前进到 systemd code R4 0 major与prepared squash `fe9c203…`；部署文档仍保持 `NO_CUTOVER`，后续上游 identity 变化必须重绑 | 继续定向复评与无副作用准备；任何计划／readiness／code review 绿灯都不授权安装、部署或 cutover |
| [README](README.md) | [R2](../../tmp/260806-review-bridge-readme-r2.md)；Architecture [裁决矩阵终审](../../tmp/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审确认用户可从 README 开始按阅读顺序进入五份文档；该结论只覆盖 Architecture 用户阅读入口，不是 README 全量新复评或产品状态证据 | 保持 current 导航与 Architecture 待用户裁决边界一致，不传播旧 Acceptance verdict |
| 本文 | latest [stable checkpoint 定向复评](../../tmp/260807-review-implementation-checkpoint.md)；历史 [current R2](../../tmp/260807-review-implementation-current-r2.md) | Latest review 的唯一 major 是未同步 happy R1／verification、systemd R4 与 usage／systemd 后继载体；本轮已按 current refs／reports 修订，但新 bytes 尚未独立复评 | 形成 README＋Implementation checkpoint 前对本轮新 bytes 定向复评；0 blocker／0 major 只表示可清 index并继续实施，不表示本文收口 |

新报告不得使用无日期前缀的旧式名称，也不得沿用与实际创建日不符的固定日期；同一对象多轮复评递增 `-rN`，不得覆盖上一轮报告。报告正文绑定完整 commit、文档内容 hash 或两者，不能只写分支名。既有历史报告不因本规则批量改名。

## Squash 与分支归档策略

本节约束当前已知分支的回放与归档，不是 Implementation 的封存条件。完成某一 squash、归档或 merged-state review后，本文仍须记录后续开发线、组合事实和新发现；只有事实本身由更新后的证据支持时，才能改变对应状态。

### 逐片收敛

1. 每个候选 HEAD 只有在独立复评 blocker 0、major 0，且该 HEAD 的声明范围测试、smoke、lint 与类型检查 gate 通过后，才可进入该片的 squash／归档。Foundations 的 `b876e62…`、`f27a8c0…` 与 `fdd2f75…` 已取得代码评审 0／0；non-stream `7ddf173…`、stream parser `73a6aa1…`、carrier v2 `8301ee9…` 与 route policy `84a22c0…` 也均为代码 0／0，其中 carrier 另有 verify `PASS`，nonstream 仲裁允许 checkpoint squash。Happy current `7e4b642…` 已修 R1 major但仍待 R2；usage `aca3ced…` 待首轮 review；systemd `49fb198…` 已获代码 R4 0／0并形成 prepared squash `fe9c203…`。任一声明范围骨架先达到 0／0即可按其剩余 gate 收敛，不等待完整 bridge；独立验收缺口、待复评与后补边界继续单独登记，不因 squash 消失。
2. 每次 shell 操作先 gate `/home/xp/src/ghc-api-proxy-py` 的物理 root、分支 `main` 与 `HEAD == refs/heads/main`；记录当时完整 main HEAD。分支或 integration worktree 的绿色结果不能替代最终 main 组合验证。
3. 主树 living docs WIP 未提交前，不在该工作树回放产品提交。Spec／Acceptance 双 carrier 已由 `ec5e8f5…` 正式提交，current hashes 仍为 `5e362822…`／`224b020d…`；文档重组 Plan R11 为 0／0／0且保持 living。Foundations 首次回放已被 index 门机械阻止，并确认未产生 cherry／merge／revert state。当前只须对 README 与本文 current bytes 完成相称复核并形成独立、可追溯的 docs checkpoint；不得 stash、restore、覆盖或夹带 WIP 来腾挪产品回并窗口。
4. 完整 integration 链已冻结为 `9e5f874… → cae83f4… → 6a00f6f…`，不再从 reviewed feature branches或旧 `8e9aef6…` 重建。首次回放前必须先读取并核对 [integration commits 只读回放预检](../../tmp/260807-audit-integration-commits.md)绑定的 base、tip、ref、clean worktree、三提交 parent／subject／path、stable patch-id／tree／binary diff identity及 reviewed source refs；任一身份漂移都停止回放并重新审计。随后每片回放前后按该报告的精确 paths与累计 blob oracle核对，不要求 future-main commit OID或整体 tree OID等于 source integration 对象。
5. Docs 提交完成后，将三个现有语义提交按 cardinality → liveness → request 顺序逐个回放到操作当时的 current `main`。每回放一片都先确认提交路径与前序 blobs未回退，再运行该片定向测试、交叠接缝测试、全仓回归、Ruff 与 Pyright；通过后才进入下一片。Integration branch 的绿色结果不能替代这些 main-side gates。
6. 三片 foundations 全部进入 main 且 main-side gate 全绿后执行其 merged-state code review，重点检查 request decoder 与 reasoning cardinality／codec、liveness cleanup 与未来 bridge stream owner、正式 Spec／Acceptance 与实际策略。随后只消费已形成的 happy integration `7e4b642…`：先取得 amended bytes 的 R2 0／0，再按 carrier v2 → nonstream → stream parser → route policy 顺序落入 current main并逐片执行 main gate／归档；不得从 source refs 重建第二条 happy 组合链。Happy 四片通过后，review并消费其单提交 usage 后继 `aca3ced…`，完成 usage main gate／归档；最后消费已准备的 systemd squash `fe9c203…`，完成 systemd main gate／归档。任何局部 review、stage `PASS`、smoke 或归档都不改变产品 `UNVERIFIED`；只有后续完整 bridge 按 current Acceptance required gates取得实证，产品 verdict 才可升级。

### 保留评审证据与归档

- Squash 前不强制改写候选分支。若复评要求继续修复，在活动分支追加提交并对新的完整 HEAD 重新评审；旧报告永远只绑定其原 HEAD。
- 每片 squash 并完成 main 侧验证后，为**最终独立评审通过的 pre-squash HEAD**创建 immutable archive ref。现有 reasoning archive 保持指向 `d90c90d…`；cardinality correction 新建 `archive/260806-anthropic-responses-reasoning-cardinality` 指向 `b876e62…`，后续分别使用 `archive/260806-anthropic-responses-liveness` 指向 `f27a8c0…` 与 `archive/260806-anthropic-responses-request` 指向 `fdd2f75…`。不得用 integration commit 替代 reviewed feature HEAD。对应 feature worktree／branch clean 且 archive ref 精确后，可随该片逐片清理。
- Archive ref 必须在移除 worktree 与活动 `feat/*` 分支之前创建并机械验证精确指向 reviewed HEAD。Archive ref 是只读追溯证据，不代表可部署主线；创建后不得 force-update。若归档后发现新缺陷，从正确基线建立新活动分支与新评审轮，不移动旧 archive ref。
- 删除 feature worktree 或其活动分支前必须同时确认：该片 archive ref 精确；main 包含该片 squash 语义；该片 main-side gate 通过；feature worktree clean。任一条件不满足都停止清理，且不得用整文件 restore 或强制删除掩盖状态。
- 共享 integration worktree／branch 不按单片清理。只有 cardinality、liveness、request 三个组合提交均已按序进入 current `main`，三片 main-side gate 均通过，integration HEAD 与三提交清单已记录，且 integration worktree clean 时，才允许移除共享 integration worktree／branch。Cardinality 或 liveness 单片已进入 `main` 不是充分条件；request 尚未进入 `main` 时，共享 integration ref 与 worktree必须继续保留其冻结组合提交。
- Archive refs 至少保留到三片 merged-state review 与长期文档收敛完成；之后是否删除由用户另行决定。本轮文档更新不创建、移动或删除任何 ref／worktree／分支。

### 回滚

每个新增切片在 main 上保持一个独立 squash commit，因此出现组合回归时可按逆序回退 request → liveness → reasoning cardinality correction；既有 reasoning carrier baseline 只有在确认缺陷属于其 codec／reverse primitive时才单独回退。原 reviewed HEAD 仍由 archive ref 保留；回滚只改变 main 上的集成提交，不移动 archive ref，也不覆盖评审证据。

## 下一步

以下是 current snapshot 的执行顺序，不是把 Implementation 收口的一次性清单。任一步产生新代码、评审结论、回放结果、合并关系或新发现，都先把本文更新到 current 事实，再继续消费后续步骤；0 blocker／0 major只放行继续实施，不终止该更新循环。

1. **先形成 README＋Implementation checkpoint 并清 index**：Spec／Acceptance 双 carrier 已由 `ec5e8f5…` 正式提交，文档重组 Plan R11 为 0／0／0且保持 living；当前先完成 README 与本文的 current-byte 复核并形成独立、可追溯的 checkpoint。该提交只为清除 foundations 回放的 living index 机械阻断，不把本文定稿，也不得夹带 `docs/tmp/**`、部署 plans／readiness 或其他 WIP。
2. **立即回放foundations三片到`main`**：checkpoint完成后重新gate current main与无cherry state，核对`260807-audit-integration-commits.md`绑定的base、tip、ref、worktree、三提交topology／subject／paths、stable patch-id／tree／binary diff与reviewed source refs仍成立；随后按`9e5f874… → cae83f4… → 6a00f6f…`逐片回放，每片核对累计blob oracle并运行定向、交叠、全仓、Ruff与Pyright main-side gate。每片通过后按既有条件归档对应reviewed source；三片全绿前保留共享foundations integration载体。
3. **R2 放行后回放 happy 四提交**：clean `integrate/260807-bridge-happy-path@7e4b642…` 已修复 R1 的同源 carrier oracle major；独立 verification 对 amend 前产品状态给出阶段 `PASS`，但 current bytes 仍待 R2。只有 R2 达到 0 blocker／0 major 后，才按 `1ed13ad → 80b3cfa → c950912 → 7e4b642` 回放 current `main`，每片执行 main-side smoke／交叠／全仓／Ruff／Pyright gate并归档对应 reviewed source；不得从 source refs 重建第二条组合链。完整 stream grammar／framing／sequencer、carrier malformed／foreign／echo 和 route handler／transport 仍作为后续 required 工作保留。
4. **Review并消费 non-stream usage**：clean `feat/nonstream-usage-details@aca3ced…` 是 `7e4b642…` 的单提交后继，当前待独立 review。Happy 四片全部进入 `main` 且逐片 gate／归档完成后，review到 0 blocker／0 major，再回放 usage，执行其定向／交叠／全仓／Ruff／Pyright main gate并归档 source；不得把候选存在写成 usage 已放行。
5. **最后回放 prepared systemd squash**：source `49fb198…` 已获 code R4 0 blocker／0 major，clean `integrate/260807-systemd-runtime@fe9c203…` 已把精确三提交压成以 `ec5e8f5…` 为 parent 的单一准备提交。Usage 收敛后重新 gate current main与 squash identity，再回放 `fe9c203…`，执行 systemd 定向／全仓／Ruff／Pyright main gate并归档 source。运行态 manager／cgroup、安装、备用端口与 cutover继续由部署门独立约束。
6. **持续动态修订deployment plans／readiness**：service-cutover plan、systemd-runtime plan与readiness已同步latest身份，后续Implementation、systemd候选或评审变化时继续重绑。计划或readiness 0／0只放行无副作用inventory、仓库实现、备用端口与rootless probe；保持`NO_CUTOVER`，不安装unit、不改变manager状态、不操作生产`4141`。
7. **继续完整替代验收与运行态准备**：完成response terminal／error、stream delivery owner、route handler、transport、retry、History、approval、hooks、tokenization、cancel、shutdown、backpressure与quota接缝，并按deployment plans准备现服`--restart` supervisor fence、双栈listener、隔离数据、备份／恢复、readiness与rollback。`localhost:4141`始终由current Bun现服继续服务，直到完整current Acceptance required gates、正反控制、live canary、fault evidence与受控cutover门全部成立。本文持续更新，不写“收口”。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/streaming/keepalive.py` 的 cleanup 路径 | cancellation 与资源清理所有权交叠；secondary failure 可能覆盖 primary failure | `f27a8c0` 已修且 R3 0／0；保留 cancellation-storm、cause chain、资源归零与无 orphan task 为组合回归 gate |
| `src/app/protocols/anthropic_responses.py` 的 tool-name／unknown-field／carrier／thinking 边界 | 多项 fail-closed 合同集中在单一 converter，相邻修复容易互相遮蔽 | `fdd2f75` 已获 R3 0／0；最终组合继续运行 request 行为 gate，不以父提交 PASS 自动覆盖新基线 |
| `src/app/anthropic/thinking/responses_reasoning.py` 的双分支修改 | cardinality 与 request decoder hardening 修改同一文件，错误回放来源会恢复旧聚合 API | 完整 integration 链已按 cardinality → request 顺序完成语义合成并通过 R2；main 逐片回放后继续联合测试，禁止改用 feature 原提交链或整文件覆盖 |
| request 验收报告与主仓正式 Spec | 两个 oracle 对 server-tool 支持给出相反 expected | 已裁决 reject；外部 F1 撤销，不再作为待实现项 |
| 五条新增开发线的 checkpoint 命名 | “骨架＋happy path＋smoke 已完成”容易被误读为该功能全部实现；non-stream代码 0／0与独立验收 `FAIL` 并存尤其容易被压成单一状态 | 每片报告必须列明 review范围、独立 verify与未覆盖边界；squash／归档和后续边界切片分开登记，完整产品始终以 current Acceptance为判据 |
| Non-stream producer与 carrier v2并行归属 | `7ddf173…` 的独立验收要求项目主 v1 producer，而对应 codec／direct-leg边界正在 `8301ee9…` 独立线收敛；重复修复会制造双实现或回放冲突 | Carrier项先做依赖／归属仲裁并以单一共享基座落地；usage reasoning detail作为 non-stream后续边界单独补，不把二者混成骨架 squash blocker |
| Route policy候选与未来 route handler | Typed decision若在 handler／transport中再次推导，会形成第二套 precedence或 fallback | `84a22c0…` review重点扫描所有决策入口；后续接线只消费 typed route fact，unknown／override／transport failure不得在下游重判 |
| 主树 living index与产品回放 | README／Implementation checkpoint未形成时直接回放foundations，会混淆文档与产品提交边界；本轮机械门已阻止该路径 | 先只提交README＋Implementation并确认index清洁、无cherry state，再开始`9e5f874…`；禁止stash／restore绕门 |
| Happy integration 与四个 source refs | R1 缺陷位于组合 smoke 判别力；current `7e4b642…` 已改测试但尚无 R2，且 carrier producer 是 nonstream 的语义依赖；从 source 重建会制造第二条组合链或改变待复评 identity | 固定消费 clean `7e4b642…` 四提交链；先 R2 到 0／0，再按 carrier → nonstream → parser → route进入 main。Verification 阶段 `PASS` 不替代 code R2 |
| Non-stream usage 后继与 happy amend | `aca3ced…` 直接基于尚未进入 `main` 的 `7e4b642…`；若提前摘取或在旧 nonstream source 重做，会丢失 happy 组合上下文或制造重复实现 | 保留单一 clean usage branch，先完成 happy R2／回放／main gates，再 review并消费 usage，最后归档 source |
| Systemd source 三提交与 prepared squash | Source R4 绑定 `49fb198…` 三提交范围，而实际待回放对象是基于旧 current main 的单一 `fe9c203…`；二者身份层级不同 | 回放前同时核对 source range、squash patch与操作时 current main；只在 main gate通过后归档 source。不得把 prepared commit外推为安装态证据 |
| `localhost:4141` 的双运行时目标 | 当前 Bun 裸进程与未来 systemd socket 都可能成为 listener owner，直接启动会端口争用或误判新服务已接管 | Cutover 明确设置唯一 socket owner、旧 listener 释放、health 与 rollback gate；代码 review／unit smoke 不外推为运行态切换证据 |

Spec `FINALIZED@5e362822…` 与 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d…` 已由 `ec5e8f5…` 正式提交，文档重组 Plan R11 为 0 blocker／0 major／0 minor 且保持 living；产品仍为 `UNVERIFIED`。Foundations `9e5f874… → cae83f4… → 6a00f6f…` 三片仍未进入 `main`：首次回放被 living index WIP 机械阻止，未产生 cherry／merge／revert state，下一动作是先提交 README＋Implementation checkpoint 清 index，再立即逐片回放并执行 main gate／归档。Carrier v2、nonstream、stream parser 与 route policy 的 source reviews 均为 0 major；happy integration 已 amend 为 clean `7e4b642…`，R1 major 已修、待 R2，verification 为阶段 `PASS`；R2 0／0后才回放其四提交并逐片 gate／归档。Usage `aca3ced…` 是 `7e4b642…` 的 clean 单提交后继，待 review并排在 happy之后。Systemd source `49fb198…` code R4 为 0 major，prepared squash `fe9c203…` 已 clean就绪并排在 usage之后。Deployment plans 与 readiness 持续动态修订，任何计划绿灯都不授权部署。当前替代目标仍是本项目 Python bridge＋systemd runtime 受控接管 `copilot-api-js` Bun现服；现阶段不声称零停机、原子切换或已验证回滚，也不触碰 `cc-daemon`。本文保持 living 并随每次回放、评审、合并与部署事实继续更新；任何 Implementation 0／0、局部 review、阶段 `PASS`、文档 verdict 或 prepared integration 都只放行其绑定范围内的下一步，不等于计划收口、已进入 main、已完成 cutover 或完整 bridge 产品 `PASS`。