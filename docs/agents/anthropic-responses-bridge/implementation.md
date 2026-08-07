# Anthropic Messages ↔ OpenAI Responses bridge 实施状态与动态收敛计划

## 文档状态

- **用途与状态**：本文是 Implementation living document，记录正式规格进入实现后的渐进切片、评审门、待修项、下一最小切片、并行开发线与本地分支收敛策略。开始开发不等于本文收口；一次提交也只是可追溯 checkpoint，不把本文转成只读历史快照。
- **事实快照**：2026-08-07。主仓为 `/home/xp/src/ghc-api-proxy-py`，current `main` HEAD 为 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。本轮每次 shell 调用都在同一调用内验证物理 repo root、分支 `main` 与现场 HEAD；未来 `main` 前进后，living document 必须先记录新锚点并重建 gate，不得把本快照冒充未来 HEAD。
- **权威边界**：[规格](spec.md)是唯一行为 oracle；任何 required behavior 与 policy-dependent expected 只能来自 Spec。2026-08-07 carrier 双格式重裁已由 [carrier 双格式定向评审](../../tmp/260807-review-spec-carrier-dual-format.md)给出 blocker 0、major 0、minor 0，Spec 源文档现已恢复 `FINALIZED`，current SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。Implementation 不得自行改写该双格式合同。[独立验收规范](acceptance.md)只把 Spec 合同转成可执行 gate，不得自行补充 expected；current Acceptance 已绑定 Spec `5e362822…`、重做 route／request／response／buffering／retry／lifecycle／limits 七域 policy 对账，并恢复 `FINALIZED_ACCEPTANCE_ORACLE`，current SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。[Spec／Acceptance current 联合终审](../../tmp/260807-review-spec-acceptance-current.md)与其直接消费的 [Spec current-byte 终审](../../tmp/260807-review-spec-carrier-final.md)、[Acceptance current-byte 终审](../../tmp/260807-review-acceptance-dual-carrier.md)均确认 current 双 carrier 内容为 0 blocker／0 major并可继续实施；Acceptance 对不可恢复 READY 中间快照的 provenance 自述只剩 1 minor，current 放行依据固定为直接绑定最终 bytes 的报告，不再等待缺失的 `787b5c38…` 中间报告。候选产品及完整 bridge 始终为 `UNVERIFIED`。[目标架构](architecture.md)仅是非规范实现参考；`D-ARCH`／`D-MIGRATION` 未经用户接受前不产生 behavior 或 expected。[研究](research.md)保留来源、可移植机制与不可照搬项，不是行为或验收 oracle。
- **更新纪律**：本文必须随代码事实、独立评审、main 回放、并行线合并、新发现与计划调整持续更新；每次更新都绑定当时可复验的 commit、worktree、报告或 gate，不把计划中的动作写成已实现事实。状态变化先更新对应切片／开发线与下一步，再同步汇总；过时结论保留其历史绑定或明确降级，不冒充 current verdict。
- **评审语义**：本文某一内容身份取得 blocker 0、major 0，只表示在该轮范围内没有已知阻断项、可以继续实施或形成 checkpoint commit；不表示 Implementation 已定稿、实施已完成、后续不再修改，也不替代新代码、新组合态和新文档 bytes各自所需的复评。后续事实或发现改变本文时，living document 应继续修订，并对新增或改写内容执行相称的定向复评。
- **当前 foundations 与主树状态**：reasoning carrier baseline `ed77c9d191df81c451c25161420515cca52ce6a4` 之上的 foundations 三片已经按序进入 `main`：`d274f584219f8ae32f59d15d08ac007c45058c8d`（reasoning cardinality）、`798ba3e7653b513c3c9c732019e793f828ae0890`（session liveness）、`1c13fda4f5eac5e42ca0025d503f91eb0563f0e7`（request converter）。Main-side gate 记录为全仓 375 tests passed，Ruff 与 Pyright 通过；该数字口径绑定 `main@cf53334…` 的 `tests` 全量运行，不外推为完整 Acceptance。Reviewed source 已由 immutable refs 保留：`archive/260807-anthropic-responses-reasoning-cardinality@b876e626…`、`archive/260807-anthropic-responses-liveness@f27a8c04…`、`archive/260807-anthropic-responses-request@fdd2f75f…`；既有 `archive/260806-anthropic-responses-reasoning@d90c90d7…` 不移动。旧 integration `6a00f6f…`、回放预检与 living-index 阻断仅保留为历史 provenance，不再是 current 下一动作。
- **当前 happy integration 与 usage 后继线**：Non-stream `7ddf173…`、stream parser `73a6aa1…`、carrier v2 `8301ee9…` 与 route policy `84a22c0…` 的声明范围评审均为 0 blocker／0 major。四片已在线性 clean integration `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 固定为 carrier `1ed13ad` → nonstream `80b3cfa` → stream parser `c950912` → route policy／smoke `7e4b642`。[happy-path 定向代码复评 R2](../../tmp/260807-review-code-happy-path-r2.md)为 0 blocker／0 major／0 minor，明确允许在 foundations 已进入 `main` 的前提下按这四个 commits 顺序回放；该 verdict 只放行 happy checkpoint，不表示完整产品 `PASS`。Non-stream usage 后继 `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857` 的 parent 精确为 `7e4b642…`，[代码评审](../../tmp/260807-review-code-nonstream-usage.md)为 0 blocker／0 major且[独立复验](../../tmp/260807-verify-nonstream-usage.md)在声明范围内 `PASS`；它仍排在 happy 四片之后，不得提前回放。
- **当前 systemd 与部署文档状态**：Systemd prepared squash 已作为 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 `main`，其 reviewed source 由 `archive/260807-systemd-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 精确保留。Main-side 定向、Ruff、Pyright 与全仓 375 tests gate 均已通过。该代码事实不等于 unit 已安装、服务已部署或 `localhost:4141` 已 cutover；Service-cutover plan、systemd-runtime plan 与 readiness 继续保持 living 和 `NO_CUTOVER`，任何运行态操作仍须独立授权并重新确认唯一 listener owner、supervisor fence、回滚与 `cc-daemon` 边界。
- **证据边界**：`docs/tmp` 报告只绑定各自写明的文档内容身份或代码 HEAD，不是长期状态真相源。本文只保留 verdict、仍有效的 gate 与裁决结果，不复制复现细节或长探针输出。后续新建报告使用实际创建日的 `YYMMDD-` 前缀，同一对象复评追加 `-rN` 且不覆盖旧轮次；既有无日期前缀或 `260806-` 报告保持原名。

### 评审 major 处置

Latest [Implementation stable checkpoint 定向复评](../../tmp/260807-review-implementation-checkpoint.md)给出 blocker 0、major 1，指出上一稳定快照未同步 happy R1／verification、systemd R4 与两个后继 worktree；更早的 [Implementation R2](../../tmp/260807-review-implementation-current-r2.md)及 [living-plan 定向评审](../../tmp/260807-review-implementation-living-plan.md)所指出的前序状态缺口已关闭。以下处置均已落入本文，但不把本次自述冒充新的独立复评 verdict；本文新 bytes 仍须定向复评：

| Major | 本次处置 | 复评门 |
|---|---|---|
| Implementation R3 M1：Spec／Acceptance 阶段状态陈旧 | **历史处置，已被 2026-08-07 carrier 重裁再次取代。** 当轮曾同步 Spec `FINALIZED` 与 Acceptance R7；current 状态以本表末行、顶部权威边界和“文档复评剩余项”为准 | 历史行不得作为 current 执行依据；后续每次 Spec bytes 变化都必须传播到 Acceptance 绑定与本文状态 |
| Implementation R3 M2：遗漏完整三片 integration branch | **历史处置，现已完成主树回放。** 当轮把 `integrate/260806-bridge-foundations@6a00f6f…`、三个线性 commits、clean worktree、代码 R2 0／0与 verification R2 PASS 写入状态真相源，并把旧 `8e9aef6…` 降为历史 liveness 载体 | Current foundations 已作为 `d274f58… → 798ba3e… → 1c13fda…` 进入 `main`并归档 reviewed sources；历史 integration verdict不得外推为完整产品 `PASS` |
| Implementation R4 M1：Acceptance R6 旧 Architecture 快照被无条件汇总为 current verdict | **历史处置。** Acceptance 当时绑定 Architecture `6de919…` 并重做七域 manifest，R7 对当时文件终审为 0／0；current Spec 后续已发生 carrier 重裁 | R7 不得外推为 current Acceptance 或产品 `PASS`；Spec／Architecture／Acceptance 内容变化时须重新绑定并复评 |
| Implementation R5 M1：本文未同步 Acceptance R7 已完成状态 | **历史处置。** R7 当时的 0／0已同步；current Spec 后续发生 carrier 双格式重裁，故该 verdict 不再覆盖 current Spec／Acceptance 内容对 | 保留为历史评审链，不得据此跳过 current Acceptance 重绑与复评 |
| Living-plan review M1：Spec carrier 重裁后状态陈旧 | Carrier 定向评审已为 0／0／0，Spec 已恢复 `FINALIZED@5e362822…`；Acceptance 已重绑并恢复 finalized。随后 current-byte Spec／Acceptance 联合终审与两份直接终审均为 0／0，已取代不可恢复 READY 中间快照的自述 | 本文新 bytes仍须复评；current 实施依据使用直接绑定 Spec `5e362822…`／Acceptance `224b020d…` 的终审，不再等待缺失中间报告 |
| Implementation current R2 M1：living 状态落后于 Plan／source／systemd／happy integration | **历史处置，已被 stable checkpoint 复评再次取代。** 当轮同步了 Plan R10、source reviews、systemd R3 与 happy `d78b3cd…` 基础状态 | 历史行不得作为 current 执行依据；current 身份与 gate 以本表末行、顶部状态和“下一步”为准 |
| Implementation stable checkpoint M1：遗漏 happy R1／verification、systemd R4 与后继活动线 | **历史处置，已被 current 状态取代。** 当轮同步 happy R1、systemd R4、usage候选与 Plan R11；随后 happy取得 R2 0／0／0，usage取得 review 0／0与范围内 verify `PASS`，systemd进入 `main`并归档 | 历史 checkpoint verdict只解释当时为何可继续，不覆盖本轮 bytes，不表示 living收口或产品 `PASS` |

此前 `docs/tmp` 归纳评审的 5 项 major 处置也随最新 merged-state 结论重新对账：

| Major | 当前处置 | 事实边界 |
|---|---|---|
| M1 Reasoning cardinality 状态缺失 | **已关闭并进入 `main`** | Reviewed source `b876e626…` 已归档为 `archive/260807-anthropic-responses-reasoning-cardinality`；对应 main commit 为 `d274f584…`，main-side gate 已通过 |
| M2 Liveness 状态停在待 R3 | **已关闭并进入 `main`** | Reviewed source `f27a8c04…` 已归档为 `archive/260807-anthropic-responses-liveness`；对应 main commit 为 `798ba3e765…`，main-side gate 已通过 |
| M3 Request 状态停在父提交 | **已关闭并进入 `main`** | Reviewed source `fdd2f75f…` 已归档为 `archive/260807-anthropic-responses-request`；对应 main commit 为 `1c13fda4…`，main-side gate 已通过 |
| M4 文档复评汇总陈旧 | **再次动态同步并关闭 current 内容门** | Spec `FINALIZED@5e362822…` 与 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d…` 已由直接绑定 current bytes 的独立终审确认为 0 blocker／0 major，可继续实施。Acceptance 的 READY 中间 provenance只剩 minor；产品仍为 `UNVERIFIED`，本文不把文档 0／0或局部 smoke外推为产品状态 |
| M5 临时报告跨日期命名合同未形成仓库级载体 | **命名合同已承载；Plan R8 历史关闭 R7 阻断，current R11 保持 0 major** | 文档重组 Plan 第 2.5 节已承载实际创建日 `YYMMDD-`、历史报告单一身份与禁止覆盖合同；R11 确认 Plan bytes 自 R10 未变化，generation 0A、post-cut、42 owner 与 living 开放状态未回归。已有 `260806-` 报告及用户明确指定的历史路径不批量改名 |

## 总体进度

| 顺序 | 切片 | 候选／集成 HEAD | 当前 gate | 下一动作 |
|---|---|---|---|---|
| 1 | Reasoning carrier baseline | `main` `ed77c9d191df81c451c25161420515cca52ce6a4` | **已 squash；原 reviewed HEAD 已归档** | 保持既有 archive ref，不移动或 force-update |
| 2 | Reasoning cardinality correction | main `d274f584219f8ae32f59d15d08ac007c45058c8d`；archive `b876e626…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | 保持 archive ref immutable；在 happy 与 route wiring 组合 gate 中继续守住一 item 一 block与 encrypted-only no-loss |
| 3 | Session liveness | main `798ba3e7653b513c3c9c732019e793f828ae0890`；archive `f27a8c04…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | 在后续 stream owner接线中继续守住 cancellation cleanup、primary／secondary failure与资源归零 |
| 4 | Request converter | main `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7`；archive `fdd2f75f…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | Route wiring只在每 attempt `PRE_SEND` 后消费 converter，不建立第二 lifecycle owner |
| 5 | Non-stream response checkpoint | `7ddf17364d97349638d44352bbd9a9b025723ccc` | 代码R2 0／0；仲裁允许checkpoint squash，carrier F-1固定为carrier-first组合依赖，usage detail由后继切片承担 | 作为 happy链第二片，在 carrier v2之后消费；组合 gate不得替代完整 non-stream验收 |
| 6 | Stream parser checkpoint | `73a6aa114647440262691651cd17e9127785c75a` | 代码 R2 为 0 blocker／0 major／0 minor，semantic-facts 骨架可 squash | 尽快 squash／归档；随后补完整 grammar、framing、strict lifecycle、refusal与 production sequencer接线 |
| 7 | Reasoning carrier v2 checkpoint | `8301ee938601ad86c7f72d313abc6c976a74b2a9` | 代码R2 0／0、独立verify R2 `PASS`；可squash | 作为 happy链首片先于 nonstream消费并执行项目主 v1组合 gate；后续 malformed／foreign／echo边界仍继续 |
| 8 | systemd／cgroup runtime checkpoint | main `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`；archive `49fb198…` | **已进入 `main`；main-side 定向、Ruff、Pyright 与全仓 375 tests gate 通过；未部署** | 保持 archive ref immutable；安装与 cutover继续由部署门和显式授权独立约束 |
| 9 | Route policy checkpoint | `84a22c07db3923768db44a1314e5ae6d5aed2e98` | 代码评审0 blocker／0 major、明确可squash | 作为 happy链第四片消费；完整 route handler／transport接线继续后补 |
| 10 | Four-checkpoint happy integration | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | Carrier → nonstream → parser → route／smoke 四个线性 commits；R2 为 0 blocker／0 major／0 minor，允许按序回放 | 下一主动作：按 `1ed13ad → 80b3cfa → c950912 → 7e4b642` 回放 current `main`，逐片执行 main gate并归档对应 reviewed source；不得外推为完整产品 `PASS` |
| 11 | Non-stream usage details | `aca3ced6e38efabf13ffe43d5935697801c74857` | 单提交 clean 后继，parent 为 happy `7e4b642…`；代码 review 0／0且独立复验范围内 `PASS` | Happy 四提交进入 `main` 且逐片 gate通过后回放 usage，执行 main gate并归档 source |
| 12 | Route wiring 与完整 lifecycle 接缝 | current `main` 上尚未形成候选 | Anthropic route仍调用 Messages transport并对 stream raw passthrough；route policy checkpoint不等于 handler／transport已接线 | Happy → usage完成后建立下一切片：把 typed route decision、Responses attempt transport、nonstream／stream converter与单一 pipeline owner接通，并按 current Acceptance执行真实入口 gate |

Foundations 的本地收敛与主树回放已经完成，旧 `integrate/260806-bridge-foundations@6a00f6f…` 只保留历史 provenance。Current 执行顺序固定为 happy 四片 → usage → route wiring。Request 与 cardinality同改 `src/app/anthropic/thinking/responses_reasoning.py`，因此 happy 与 route wiring的组合 gate仍须机械确认有序 block-list API、项目主 v1＋upstream v1合法主路径兼容、typed malformed止血及跨片 production-chain回归；不得把旧“全malformed Node byte-exact”范围重新带回 current gate。

### 当前并行开发线

| 开发线 | Worktree／branch | 建树基线 | 当前事实 | 更新与进入条件 |
|---|---|---|---|---|
| Non-stream response | `/home/xp/src/ghc-api-proxy-py-response`；`feat/responses-anthropic-nonstream` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `7ddf173…`；代码R2 0／0、骨架可squash；仲裁允许checkpoint收敛 | 作为 happy链第二片消费，固定依赖 carrier v2先进入组合；usage reasoning detail由后继切片承担，完整产品仍为`UNVERIFIED` |
| Stream parser | `/home/xp/src/ghc-api-proxy-py-stream-parser`；`feat/responses-stream-parser` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `73a6aa1…`；代码 R2 0／0／0，骨架可 squash | 作为 happy链第三片消费并归档；完整 grammar／framing／strict lifecycle与 sequencer接线作为后续切片继续 |
| Reasoning carrier v2 | `/home/xp/src/ghc-api-proxy-py-carrier-v2`；`feat/reasoning-carrier-v2` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `8301ee9…`；代码R2 0／0、verify R2 `PASS`、可squash | 作为 happy链首片消费；nonstream必须依赖本片的项目主v1 producer，后续兼容边界继续 |
| Non-stream usage details | `/home/xp/src/ghc-api-proxy-py-nonstream-usage`；`feat/nonstream-usage-details` | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | `aca3ced…`；单提交、clean；代码 review 0／0且独立复验范围内 `PASS` | 不重复建线；happy 四片 main gates通过后再消费，随后执行 usage main gate并归档 |
| systemd／cgroup runtime | source `feat/systemd-cgroup-runtime`；archive `archive/260807-systemd-runtime` | source 基于 `ed77c9d…` | `cf53334…` 已进入 `main`；reviewed source `49fb198…` 已归档；未部署 | 不再作为 bridge代码回放待办；真实 manager／cgroup、安装与 cutover继续服从独立部署门 |
| Route policy | `/home/xp/src/ghc-api-proxy-py-route-policy`；`feat/anthropic-responses-route-policy` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `84a22c0…`；评审0／0、明确可squash | 作为 happy链第四片消费；route handler／transport／History完整接线继续后补 |
| Happy integration | `/home/xp/src/ghc-api-proxy-py-integrate-happy`；`integrate/260807-bridge-happy-path` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `7e4b642…`；四个线性 commits、clean；R2 0／0／0，可按现有链回放 | 立即按四提交顺序回放 current `main`；不得重建第二条 happy 组合链 |

Source checkpoints 均已关闭当前声明范围的 0 major：carrier v2另有独立 verify `PASS`，nonstream仲裁允许 checkpoint squash并冻结 carrier-first组合依赖，stream parser与route policy均可squash。Happy integration `7e4b642…` 的 R2已为 0／0／0，可按现有四提交链回放。Usage后继 `aca3ced…` 已完成代码 review 0／0与声明范围独立复验，但必须等待 happy main gates。Foundations与systemd已在 current `main`，对应 reviewed source已归档；后补边界不因 checkpoint、组合绿灯或main-side 375 tests全绿而取消。任何代码收敛都不授权停止现服、安装 unit或抢占 `4141`。

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

Cardinality 修复的 reviewed source为 `b876e626dda821b267535b0bcffc9d81ced12763`。[独立代码评审](../../tmp/260806-review-code-reasoning-cardinality.md)给出 blocker 0、major 0：每个 reasoning item产生自己的有序 thinking block，保留 non-empty encrypted-only payload，并保持 carrier与逐 block reverse。该语义已作为 `d274f584219f8ae32f59d15d08ac007c45058c8d` 进入 `main`，reviewed source由 `archive/260807-anthropic-responses-reasoning-cardinality@b876e626…` 精确保留；既有 reasoning archive不移动。

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

旧 `8e9aef69…` 与完整 foundations integration 的 `cae83f467…` 只保留历史组合 provenance。Liveness语义已作为 `798ba3e7653b513c3c9c732019e793f828ae0890` 进入 `main`，reviewed source由 `archive/260807-anthropic-responses-liveness@f27a8c04…` 精确保留；后续不得从历史 integration再建第二套组合链。

**验收判据**：后续 cancellation 不得截断资源清理；primary cancellation／upstream error 保持最终可见；secondary close failure被观察并记录但不覆盖 primary；正常退出时的 close failure仍显式传播；所有退出路径中 active pull、generator frame 与底层 iterator 都归零且 close 至多一次。

**风险与回滚**：shield或 cleanup task若错误吞掉 cancellation，会造成 shutdown延迟或 orphan task；若只保留 primary而不观察 secondary，会重新引入 task warning。Route wiring接入新的 stream owner时必须复跑 cancellation-storm、cause chain、资源归零与 close-at-most-once gate；若失败，在 current main新建修复切片并重新评审，不移动 archive ref。

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

完整 foundations integration曾在 `6a00f6f…` 中把 request converter合到 cardinality＋liveness基线上，没有用 request分支的旧整文件覆盖 `responses_reasoning.py`。[merged-state 代码 R2](../../tmp/260806-review-code-bridge-foundations-r2.md)确认新增 major已关闭，[独立复验 R2](../../tmp/260806-verify-bridge-foundations-r2.md)确认空 content-list typed reject与真实 forward→`MessagesRequest`→public converter 的 $N \rightarrow N$ reasoning接缝范围内 `PASS`。该语义现已作为 `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` 进入 `main`，reviewed source由 `archive/260807-anthropic-responses-request@fdd2f75f…` 精确保留；integration报告继续只作历史 provenance。

## 文档复评剩余项

| 文档 | 最新报告 | 当前剩余项 | 下一报告 |
|---|---|---|---|
| [Spec](spec.md) | [current-byte 终审](../../tmp/260807-review-spec-carrier-final.md)；[Spec／Acceptance 联合终审](../../tmp/260807-review-spec-acceptance-current.md) | Current `FINALIZED@5e362822…` 为 blocker 0、major 0，可继续实施 | 作为 current 行为 oracle继续实施；该 0／0不证明候选实现符合 |
| [Architecture](architecture.md) | 技术 [R3](../../tmp/260806-review-bridge-architecture-r3.md)；[裁决矩阵终审](../../tmp/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审为 blocker 0、major 0，确认 Architecture 已具备用户裁决条件；它仍是非规范提案、不是 ADR，`D-ARCH`／`D-MIGRATION` 尚待用户完整阅读后亲自裁决 | 用户接受前 Architecture 不产生 expected；终审 0／0不替代用户裁决 |
| [Acceptance](acceptance.md) | [current-byte 终审](../../tmp/260807-review-acceptance-dual-carrier.md)；[Spec／Acceptance 联合终审](../../tmp/260807-review-spec-acceptance-current.md) | Current `FINALIZED_ACCEPTANCE_ORACLE@224b020d…` 为 blocker 0、major 0；不可恢复 READY 中间 provenance只剩 1 minor，最终 bytes已有直接独立证据；产品继续 `UNVERIFIED` | 按 current required gates实施；后续清理中间 provenance时不得把文档 0／0外推为产品 `PASS` |
| [Research](research.md) | [外部变化只读复核](../../tmp/260807-review-research-external-change.md) | blocker 0、major 0；current Research 可提交，route 作用域只覆盖 Anthropic `/v1/messages` bridge，不改变 native Responses 公共入口 | 无待修；Research 始终不产生 behavior expected |
| [文档重组计划](../documentation-restructure/plan.md) | current [独立定向终审 R11](../../tmp/260807-review-doc-migration-plan-r11.md) | R11 为 blocker 0、major 0、minor 0；确认 Plan bytes 自 R10 未变化，generation 0A、post-cut、42 owner与living开放状态均未回归 | 可继续执行并保持 living；不表示文档迁移收口，后续 identity／generation／certificate／action 漂移仍按 Plan 自身 gate 重判 |
| [Service cutover plan](../service-cutover/plan.md)／[systemd runtime plan](../systemd-runtime/plan.md)／[readiness](../service-cutover/readiness.md) | 各自 current living 修订；历史报告继续按绑定 bytes保留 | Systemd代码已作为 `cf53334…` 进入 `main`，reviewed source `49fb198…` 已归档；部署文档仍保持 `NO_CUTOVER`，后续上游 identity变化必须重绑 | 继续定向复评与无副作用准备；任何 main commit、计划／readiness／code review绿灯都不授权安装、部署或 cutover |
| [README](README.md) | [R2](../../tmp/260806-review-bridge-readme-r2.md)；Architecture [裁决矩阵终审](../../tmp/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审确认用户可从 README 开始按阅读顺序进入五份文档；该结论只覆盖 Architecture 用户阅读入口，不是 README 全量新复评或产品状态证据 | 保持 current 导航与 Architecture 待用户裁决边界一致，不传播旧 Acceptance verdict |
| 本文 | latest committed living checkpoint [联合复评 R2](../../tmp/260807-review-living-bridge-docs-r2.md)；本轮继续动态修订 | Foundations 与 systemd 已进入 `main`，happy R2 与 usage review／verify 已前进，故旧 verdict 不覆盖本轮新 bytes | 本轮新 bytes 需后续独立定向复评；任何 0 blocker／0 major 只放行继续实施，不表示 living 收口或产品 `PASS` |

新报告不得使用无日期前缀的旧式名称，也不得沿用与实际创建日不符的固定日期；同一对象多轮复评递增 `-rN`，不得覆盖上一轮报告。报告正文绑定完整 commit、文档内容 hash 或两者，不能只写分支名。既有历史报告不因本规则批量改名。

## Squash 与分支归档策略

本节约束当前已知分支的回放与归档，不是 Implementation 的封存条件。完成某一 squash、归档或 merged-state review后，本文仍须记录后续开发线、组合事实和新发现；只有事实本身由更新后的证据支持时，才能改变对应状态。

### 逐片收敛

1. 每个候选 HEAD 只有在独立复评 blocker 0、major 0，且该 HEAD 的声明范围测试、smoke、lint 与类型检查 gate 通过后，才可进入该片的回放／归档。Foundations 与 systemd 已满足该门并进入 `main`；happy `7e4b642…` 的 R2 为 0／0／0，usage `aca3ced…` 的代码 review为 0／0且独立复验范围内 `PASS`。任一声明范围骨架先达到 0／0即可按其剩余 gate收敛，不等待完整 bridge；独立验收缺口与后补边界继续单独登记，不因回放消失。
2. 每次 shell 操作先 gate `/home/xp/src/ghc-api-proxy-py` 的物理 root、分支 `main` 与 `HEAD == refs/heads/main`；记录当时完整 main HEAD。分支或 integration worktree 的绿色结果不能替代最终 main 组合验证。
3. Spec／Acceptance current hashes 仍为 `5e362822…`／`224b020d…`，两份工作树 bytes 与 `HEAD` blobs相同。Foundations 与 systemd回放已经完成；旧 living-index阻断与 integration audit只作历史证据，不再是 current gate。
4. Happy integration固定消费 `1ed13ad… → 80b3cfa… → c950912… → 7e4b642…`，不得从 reviewed source refs重建第二条组合链。每片回放前后核对 parent、subject、paths与累计 blobs，运行该片定向测试、交叠接缝测试、全仓回归、Ruff 与 Pyright；通过后才进入下一片并归档对应 reviewed source。
5. Happy 四片全部进入 `main` 且逐片 gate通过后，消费单提交 usage后继 `aca3ced…`，执行 usage定向、交叠、全仓、Ruff 与 Pyright main gate并归档 source。
6. Happy 与 usage完成后进入 route wiring：在当前单一 Anthropic pipeline owner内消费 typed route decision；Responses leg每 attempt在 `PRE_SEND` 后转换 request，使用 Responses transport，并把 nonstream／stream结果送入共享 semantic conversion与 Anthropic renderer。任何局部 review、阶段 `PASS`、smoke、375 tests或归档都不改变产品 `UNVERIFIED`；只有完整 bridge按 current Acceptance required gates取得实证，产品 verdict才可升级。

### 保留评审证据与归档

- Squash 前不强制改写候选分支。若复评要求继续修复，在活动分支追加提交并对新的完整 HEAD 重新评审；旧报告永远只绑定其原 HEAD。
- 每片回放并完成 main侧验证后，为**最终独立评审通过的 pre-squash HEAD**创建 immutable archive ref。现有 reasoning archive保持指向 `d90c90d…`；已建 refs精确为 `archive/260807-anthropic-responses-reasoning-cardinality@b876e62…`、`archive/260807-anthropic-responses-liveness@f27a8c0…`、`archive/260807-anthropic-responses-request@fdd2f75…` 与 `archive/260807-systemd-runtime@49fb198…`。不得用 integration commit替代 reviewed feature HEAD。对应 feature worktree／branch clean且 archive ref精确后，可随该片逐片清理。
- Archive ref 必须在移除 worktree 与活动 `feat/*` 分支之前创建并机械验证精确指向 reviewed HEAD。Archive ref 是只读追溯证据，不代表可部署主线；创建后不得 force-update。若归档后发现新缺陷，从正确基线建立新活动分支与新评审轮，不移动旧 archive ref。
- 删除 feature worktree 或其活动分支前必须同时确认：该片 archive ref 精确；main 包含该片 squash 语义；该片 main-side gate 通过；feature worktree clean。任一条件不满足都停止清理，且不得用整文件 restore 或强制删除掩盖状态。
- Foundations共享 integration worktree／branch不按单片清理。其三个组合提交现已按序进入 current `main`，三片 main-side gate与 archive refs均已完成；只有另行机械确认 integration HEAD、三提交清单和 worktree clean后才允许移除该历史载体。本轮文档更新不声称该清理已执行。
- Archive refs 至少保留到三片 merged-state review 与长期文档收敛完成；之后是否删除由用户另行决定。本轮文档更新不创建、移动或删除任何 ref／worktree／分支。

### 回滚

每个新增切片在 main 上保持一个独立 squash commit，因此出现组合回归时可按逆序回退 request → liveness → reasoning cardinality correction；既有 reasoning carrier baseline 只有在确认缺陷属于其 codec／reverse primitive时才单独回退。原 reviewed HEAD 仍由 archive ref 保留；回滚只改变 main 上的集成提交，不移动 archive ref，也不覆盖评审证据。

## 下一步

以下是 current snapshot 的执行顺序，不是把 Implementation 收口的一次性清单。任一步产生新代码、评审结论、回放结果、合并关系或新发现，都先把本文更新到 current 事实，再继续后续步骤；0 blocker／0 major只放行继续实施，不终止该更新循环。

1. **回放 happy 四片**：在每次 shell 调用中重新 gate `/home/xp/src/ghc-api-proxy-py` 的物理 root、`main` 与现场 HEAD。消费已获 R2 0／0／0的 `integrate/260807-bridge-happy-path@7e4b642…`，按 `1ed13ad → 80b3cfa → c950912 → 7e4b642` 逐片回放；每片执行 main-side smoke、交叠、全仓、Ruff 与 Pyright gate，并在通过后建立精确 reviewed-source archive。不得从 source refs重建第二条 happy链，也不得把 R2或 integration green外推为完整产品 `PASS`。
2. **消费 non-stream usage**：Happy 四片全部进入 `main` 且逐片 gate／归档完成后，回放已获代码 review 0／0与独立复验范围内 `PASS` 的 `aca3ced…`，执行 usage定向、交叠、全仓、Ruff 与 Pyright main gate并归档 source。它只补齐 non-stream usage details，不证明 stream parity、History持久化或整桥验收。
3. **实施 route wiring**：以 current `src/app/routes/anthropic.py`、`src/app/anthropic/client.py` 与 `src/app/pipeline/executor.py` 为真实接缝，在不创建第二 approval／retry／History／finalize owner的前提下，把 typed route policy接入 Anthropic pipeline；在每 attempt `PRE_SEND` 后生成 Responses wire，接入 Responses HTTP／WS transport，并让 nonstream／stream共享 semantic conversion core。先写真实 route级失败测试，再实现并运行 REQ-01、REQ-06、NS、STR、REL、TR 与 LIFE相关 gate；route handler不得重新推导 route precedence。
4. **继续完整替代验收**：补齐 response terminal／error、stream delivery owner、continuous-prefix sequencer、retry frontier、History、approval、hooks、tokenization、cancel、shutdown、backpressure、quota、HTTP／WS parity、正反控制、live canary、capture corpus与 local fault证据。完整产品在 current Acceptance全部 required gates通过前保持 `UNVERIFIED`。
5. **部署状态保持独立 living**：Systemd代码虽已进入 `main` 并归档，仍保持 `NO_CUTOVER`。Service-cutover plan、systemd-runtime plan与readiness继续随上游 identity变化重绑；没有显式运行态授权时不安装 unit、不改变 manager状态、不操作生产 `4141`，也不触碰独立 `cc-daemon` 生命周期。

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
| 主树 living index与产品回放 | Foundations首次回放曾被 README／Implementation index机械门阻止；该状态现已结束 | 保留为历史教训：文档与产品提交继续分离；current happy回放前仍检查 index、无 cherry state与精确 path集合，禁止 stash／restore绕门 |
| Happy integration 与四个 source refs | R1 缺陷位于组合 smoke判别力；current `7e4b642…` 已由 R2确认为 0／0／0，carrier producer仍是 nonstream的语义依赖 | 固定消费 clean `7e4b642…` 四提交链，按 carrier → nonstream → parser → route进入 main；从 source重建仍会制造第二条组合链 |
| Non-stream usage 后继与 happy amend | `aca3ced…` 直接基于尚未进入 `main` 的 `7e4b642…`；若提前摘取或在旧 nonstream source重做，会丢失 happy组合上下文或制造重复实现 | 保留单一 clean usage branch；代码 review与范围内 verify已通过，仍须先完成 happy回放／main gates，再消费 usage并归档 source |
| Systemd source 与 main squash | Source R4绑定 `49fb198…`，main commit为 `cf53334…`；reviewed source与集成提交身份层级不同 | 已以 `archive/260807-systemd-runtime@49fb198…` 保留 source并通过 main gate；仍不得把 main commit外推为安装态或 cutover证据 |
| `localhost:4141` 的双运行时目标 | 当前 Bun 裸进程与未来 systemd socket 都可能成为 listener owner，直接启动会端口争用或误判新服务已接管 | Cutover 明确设置唯一 socket owner、旧 listener 释放、health 与 rollback gate；代码 review／unit smoke 不外推为运行态切换证据 |

Spec `FINALIZED@5e362822…` 与 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d…` 的 current bytes均与 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 中的 blobs一致；完整产品仍为 `UNVERIFIED`。Foundations 三片已作为 `d274f58… → 798ba3e… → 1c13fda…` 进入 `main`，reviewed sources已由三个 `archive/260807-anthropic-responses-*` refs保留；systemd已作为 `cf53334…` 进入 `main`并由 `archive/260807-systemd-runtime@49fb198…` 保留 reviewed source。Main-side记录为全仓375 tests、Ruff与Pyright全绿，但该结果只证明 current主树回归，不等于完整 Acceptance。Happy integration `7e4b642…` 已获 R2 0／0／0，可按四提交回放；usage `aca3ced…` 已获代码 review 0／0与声明范围独立复验 `PASS`，排在 happy之后；再下一实施切片是 route wiring。Deployment plans与readiness持续动态修订，任何代码或计划绿灯都不授权安装、部署或cutover。本文保持 living并随每次回放、评审、接线与部署事实继续更新；任何局部 verdict、阶段 `PASS`、375 tests或 archive都只放行其绑定范围，不等于计划收口、已完成cutover或完整bridge产品 `PASS`。