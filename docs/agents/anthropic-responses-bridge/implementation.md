# Anthropic Messages ↔ OpenAI Responses bridge 实施状态与动态收敛计划

## 文档状态

- **用途与状态**：本文是 Implementation living document，记录正式规格进入实现后的渐进切片、评审门、待修项、下一最小切片、并行开发线与本地分支收敛策略。开始开发不等于本文收口；一次提交也只是可追溯 checkpoint，不把本文转成只读历史快照。
- **事实快照**：2026-08-07。主仓为 `/home/xp/src/ghc-api-proxy-py`，current `main` HEAD 为 `80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮每次 shell 调用都在同一调用内验证物理 repo root、分支 `main` 与现场 HEAD；未来 `main` 前进后，living document 必须先记录新锚点并重建 gate，不得把本快照冒充未来 HEAD。
- **权威边界**：[规格](spec.md)是唯一行为 oracle；任何 required behavior 与 policy-dependent expected 只能来自 Spec。2026-08-07 carrier 双格式重裁已由 [carrier 双格式定向评审](../../tmp/260807-review-spec-carrier-dual-format.md)给出 blocker 0、major 0、minor 0，Spec 源文档现已恢复 `FINALIZED`，current SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。Implementation 不得自行改写该双格式合同。[独立验收规范](acceptance.md)只把 Spec 合同转成可执行 gate，不得自行补充 expected；空 reasoning 状态与 provenance 同步后的 current SHA-256 为 `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`，状态为 `FINALIZED_ACCEPTANCE_ORACLE`。[Acceptance 空 reasoning 定向独立复评 R2](../../tmp/260807-review-acceptance-empty-reasoning-r2.md)已对该精确内容身份给出 blocker 0、major 0、minor 0并允许 checkpoint；该状态只批准使用 current Acceptance oracle，不构成候选产品或完整 bridge 的 `PASS`，产品继续为 `UNVERIFIED`。[目标架构](architecture.md)仅是非规范实现参考；`D-ARCH`／`D-MIGRATION` 未经用户接受前不产生 behavior 或 expected。[研究](research.md)保留来源、可移植机制与不可照搬项，不是行为或验收 oracle。
- **更新纪律**：本文必须随代码事实、独立评审、main 回放、并行线合并、新发现与计划调整持续更新；每次更新都绑定当时可复验的 commit、worktree、报告或 gate，不把计划中的动作写成已实现事实。状态变化先更新对应切片／开发线与下一步，再同步汇总；过时结论保留其历史绑定或明确降级，不冒充 current verdict。
- **评审语义**：本文某一内容身份取得 blocker 0、major 0，只表示在该轮范围内没有已知阻断项、可以继续实施或形成 checkpoint commit；不表示 Implementation 已定稿、实施已完成、后续不再修改，也不替代新代码、新组合态和新文档 bytes各自所需的复评。后续事实或发现改变本文时，living document 应继续修订，并对新增或改写内容执行相称的定向复评。
- **当前 foundations、happy 与 usage 主树状态**：reasoning carrier baseline `ed77c9d191df81c451c25161420515cca52ce6a4` 之上的 foundations 三片已经按序进入 `main`：`d274f584219f8ae32f59d15d08ac007c45058c8d`（reasoning cardinality）、`798ba3e7653b513c3c9c732019e793f828ae0890`（session liveness）、`1c13fda4f5eac5e42ca0025d503f91eb0563f0e7`（request converter）。Happy 四片随后已作为 `a0d807fe807629b739ab16c5463f99bc27bc7aac`（reasoning carrier v2）、`cdc080e1795ee1ac63d589ee00a10acd581b460e`（non-stream response）、`a815948ef1b8e739e4bd49e31894be4dffc06950`（stream parser）与 `d913a033252693022f0871f1e92c1b996d05eb71`（typed route policy／smoke）进入 `main`，non-stream usage details 也已作为 `80bc8f252b46c511f428af1d97159a5980ee9dc9` 进入 `main`。本轮在 `main@80bc8f2…` 隔离进程组中实跑全仓 pytest 为 434 passed，并以 collect-only node ID 独立交叉核对为 434；全仓 Ruff 与 Pyright 均通过。该组合回归只证明 current 主树，不外推为完整 Acceptance 或产品 `PASS`。
- **当前归档状态**：Foundations reviewed sources 由 `archive/260807-anthropic-responses-reasoning-cardinality@b876e626…`、`archive/260807-anthropic-responses-liveness@f27a8c04…` 与 `archive/260807-anthropic-responses-request@fdd2f75f…` 保留；既有 `archive/260806-anthropic-responses-reasoning@d90c90d7…` 不移动。Happy／usage reviewed sources 由 `archive/260807-reasoning-carrier-v2@8301ee9…`、`archive/260807-responses-anthropic-nonstream@7ddf173…`、`archive/260807-responses-stream-parser@73a6aa1…`、`archive/260807-anthropic-responses-route-policy@84a22c0…` 与 `archive/260807-nonstream-usage-details@aca3ced…` 精确保留。旧 foundations／happy integrations、回放预检与 living-index 阻断仅保留为历史 provenance，不再是 current 下一动作；archive refs 不因主树继续前进而移动。
- **当前 systemd 与部署文档状态**：Systemd prepared squash 已作为 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 `main`，其 reviewed source 由 `archive/260807-systemd-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 精确保留；该提交是 current `main@80bc8f2…` 的祖先。Graceful-timeout 与 rootless installer 已从 current main 重建为排除 `docs/agents/systemd-runtime/plan.md` 的 code-only 线性集成 `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`，提交顺序为 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc → 2ec0cb81832691685bfe8d98ad03071d2d5e5316`；其 merged-state review 为 0 blocker／0 major，独立验收为 `PASS`。旧 `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 及 `91f95f7d30c0b399eef98d997c0f88f57c2d0284 → 0a93e7f…` 只保留历史组合语义、适配与来源 provenance，因携带已被 current living Plan 超越的 Plan patch，不得直接 cherry-pick、回放、续写或作为冲突 postimage。Current main 的 434 tests、Ruff 与 Pyright gate 已通过，但该代码事实不等于 unit 已安装、服务已部署或 `localhost:4141` 已 cutover；Service-cutover plan、systemd-runtime plan 与 readiness 继续保持 living 和 `NO_CUTOVER`。四文档 checkpoint 后只能按 rebuilt code-only 顺序逐片回放；代码提交不得携带 Plan，每片 main-side gate 后从当时 living checkpoint fresh 更新并重新 checkpoint Plan。任何运行态操作仍须独立授权并重新确认唯一 listener owner、supervisor fence、回滚与 `cc-daemon` 边界。
- **当前完整产品边界**：Happy 四片与 usage 已进入 `main`，但 current `main@80bc8f2…` 的 `src/app/routes/anthropic.py` 仍把 Anthropic 请求交给 Messages transport，流式路径仍 raw passthrough；typed route decision、Responses attempt transport、non-stream／stream converter 与完整 block delivery 尚未在主树形成生产接缝。Clean successor integration 已固定为 `/home/xp/src/ghc-api-proxy-py-integrate-successor` 的 `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f`，相对 current main 严格包含三条线性 non-merge commits：semantic `04bdfcbf75bfa7e9709d55869c70106c49146db6` → route `088d66d3f12bd39be7ce7f61877336f490e7dbdb` → block `c43db35a7a5851225b55ce31b8edbec2cf90917f`。其[merged-state 独立代码评审](../../tmp/260807-review-code-bridge-successor.md)为 0 blocker／0 major／0 minor并允许保持三提交边界逐片回放，[独立验收](../../tmp/260807-verify-bridge-successor.md)在真实 ASGI non-stream、typed stream reject、parser→delivery core、single owner／single writer等声明范围内为 `PASS`。该 scoped `PASS`不覆盖真实 Responses stream transport wiring、HTTP SSE、disconnect、retry、quota、backpressure、shutdown或 post-commit partial failure；完整 stream 与 bridge 继续为 `UNVERIFIED`。旧组合 `integrate/260807-bridge-next@a23081c5d5f48143bf3015182d8f00e1f6297755` 只保留失败 provenance，不得回放、续写或 amend。
- **当前 merged-state 修复门**：[current main happy／usage merged-state 独立评审](../../tmp/260807-review-main-happy-usage.md)绑定 `main@80bc8f2…`，原 verdict 为 0 blocker／2 major。其空 summary 且无／空 payload 项已由[空 reasoning 语义仲裁](../../tmp/260807-arbitrate-empty-reasoning.md)撤销：唯一合法行为是每个 empty reasoning item形成一个 `thinking=""` bare carrier block，semantic candidate 在该轴正确，[旧独立复验](../../tmp/260807-verify-semantic-parity.md)的零-block expected与据此产生的 `FAIL` 已被仲裁取代。Acceptance `NS-03` 的 current `6457b896…` 已恢复 `FINALIZED_ACCEPTANCE_ORACLE`，并由[空 reasoning 定向独立复评 R2](../../tmp/260807-review-acceptance-empty-reasoning-r2.md)确认 0 blocker／0 major／0 minor，不得继续沿用旧零-block解释。Authoritative lifecycle 与 unknown summary修复已在 clean `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` 收口；[代码 R2](../../tmp/260807-review-code-semantic-parity-r2.md)为 0 blocker／0 major／0 minor并明确可 squash，[独立 verify R2](../../tmp/260807-verify-semantic-parity-r2.md)为 `PASS`。该 semantic 完整 range 已内容等价进入 successor 的 `04bdfcb…`；route 与 block完整 ranges也分别内容等价进入 `088d66d…` 与 `c43db35…`，三片组合已取得 merged review 0 major与 scoped verification `PASS`。下一门不是创建 integration，而是先完成 Acceptance、Implementation、Readiness与Systemd Plan四文档 current checkpoint，再按 `04bdfcb… → 088d66d… → c43db35…` 逐片回放 `main`，每片完成 main-side gate并归档对应 reviewed source。
- **证据边界**：`docs/tmp` 报告只绑定各自写明的文档内容身份或代码 HEAD，不是长期状态真相源。本文只保留 verdict、仍有效的 gate 与裁决结果，不复制复现细节或长探针输出。后续新建报告使用实际创建日的 `YYMMDD-` 前缀，同一对象复评追加 `-rN` 且不覆盖旧轮次；既有无日期前缀或 `260806-` 报告保持原名。

### 评审 major 处置

[Implementation current R7](../../tmp/260807-review-implementation-current-r7.md)对上一内容身份给出 blocker 0、major 1、minor 0；唯一 major 是 clean bridge successor 已形成但全文仍会引导执行者重复创建该 integration。本轮保持 `c43db35…` 精确身份、三提交拓扑、merged review 0 major、scoped verify `PASS`、四文档 checkpoint与逐片回放门，并同步 systemd current code-only `862f4cfa… → 2ec0cb8…`、旧链历史 provenance／禁止回放边界及每片 gate 后 fresh Plan checkpoint。更早的 [Implementation current R6](../../tmp/260807-review-implementation-current-r6.md)、[Implementation current R5](../../tmp/260807-review-implementation-current-r5.md)、[Implementation current R4](../../tmp/260807-review-implementation-current-r4.md)、[Implementation current R3](../../tmp/260807-review-implementation-current-r3.md)、[Implementation stable checkpoint 定向复评](../../tmp/260807-review-implementation-checkpoint.md)、[Implementation R2](../../tmp/260807-review-implementation-current-r2.md)及 [living-plan 定向评审](../../tmp/260807-review-implementation-living-plan.md)均只绑定各自旧内容身份。以下处置均已落入本文，但不把本次自述冒充新的独立复评 verdict；本文新 bytes 仍须定向复评：

| Major | 本次处置 | 复评门 |
|---|---|---|
| Implementation R3 M1：Spec／Acceptance 阶段状态陈旧 | **历史处置，已被 2026-08-07 carrier 重裁再次取代。** 当轮曾同步 Spec `FINALIZED` 与 Acceptance R7；current 状态以本表末行、顶部权威边界和“文档复评剩余项”为准 | 历史行不得作为 current 执行依据；后续每次 Spec bytes 变化都必须传播到 Acceptance 绑定与本文状态 |
| Implementation R3 M2：遗漏完整三片 integration branch | **历史处置，现已完成主树回放。** 当轮把 `integrate/260806-bridge-foundations@6a00f6f…`、三个线性 commits、clean worktree、代码 R2 0／0与 verification R2 PASS 写入状态真相源，并把旧 `8e9aef6…` 降为历史 liveness 载体 | Current foundations 已作为 `d274f58… → 798ba3e… → 1c13fda…` 进入 `main`并归档 reviewed sources；历史 integration verdict不得外推为完整产品 `PASS` |
| Implementation R4 M1：Acceptance R6 旧 Architecture 快照被无条件汇总为 current verdict | **历史处置。** Acceptance 当时绑定 Architecture `6de919…` 并重做七域 manifest，R7 对当时文件终审为 0／0；current Spec 后续已发生 carrier 重裁 | R7 不得外推为 current Acceptance 或产品 `PASS`；Spec／Architecture／Acceptance 内容变化时须重新绑定并复评 |
| Implementation R5 M1：本文未同步 Acceptance R7 已完成状态 | **历史处置。** R7 当时的 0／0已同步；current Spec 后续发生 carrier 双格式重裁，故该 verdict 不再覆盖 current Spec／Acceptance 内容对 | 保留为历史评审链，不得据此跳过 current Acceptance 重绑与复评 |
| Living-plan review M1：Spec carrier 重裁后状态陈旧 | **历史处置，current 状态已再次前进。** Carrier 定向评审曾为0／0／0，Spec恢复`FINALIZED@5e362822…`；Acceptance现已重绑并恢复`FINALIZED_ACCEPTANCE_ORACLE@6457b896…` | 本文新bytes仍须复评；current Acceptance依据是精确绑定`6457b896…`的空reasoning R2 0／0／0，不再沿用旧`224b020d…`终审 |
| Implementation current R2 M1：living 状态落后于 Plan／source／systemd／happy integration | **历史处置，已被 stable checkpoint 复评再次取代。** 当轮同步了 Plan R10、source reviews、systemd R3 与 happy `d78b3cd…` 基础状态 | 历史行不得作为 current 执行依据；current 身份与 gate 以本表末行、顶部状态和“下一步”为准 |
| Implementation stable checkpoint M1：遗漏 happy R1／verification、systemd R4 与后继活动线 | **历史处置，已被 current 状态取代。** 当轮同步 happy R1、systemd R4、usage候选与 Plan R11；随后 happy取得 R2 0／0／0，usage取得 review 0／0与范围内 verify `PASS`，systemd进入 `main`并归档 | 历史 checkpoint verdict只解释当时为何可继续，不覆盖本轮 bytes，不表示 living收口或产品 `PASS` |
| Current main 同步：happy／usage 已落地但 living 仍写待回放 | **本轮处置。** 已同步 `a0d807f… → cdc080e… → a815948… → d913a03… → 80bc8f2…` 的主线事实、五个 reviewed-source archive refs、current 434 tests／Ruff／Pyright gate，并把执行面切换到四条新并行线 | 本轮新 bytes仍须独立定向复评；主树组合绿只证明 checkpoint，完整 route仍未接、产品保持 `UNVERIFIED`，Implementation继续 living |
| Implementation main／happy M1：四条后继线仍被写成基线 WIP | **已关闭，后继状态继续动态同步。** 原评审所指四个首批 candidate commits 为 route `f3a5a768…`、block `e3fceb1c…`、graceful `865a5b71…` 与 installer `e16c2a70…`；其后 route 已形成并放行 hooks successor `dd376d6…`，block 已到 `e506bf8…`并放行，semantic 已形成并放行 successor `f5bca39…`。Systemd 的旧 `0a93e7f1…` 组合只保留历史 provenance，current rebuilt code-only 集成为 `862f4cfa… → 2ec0cb8…` | 三个 bridge source ranges 已内容等价进入 clean successor `04bdfcb… → 088d66d… → c43db35…`并取得 merged review 0 major 与 scoped verify `PASS`；systemd code-only 也已取得 merged review 0 major 与 verify `PASS`。本文继续 living，不因候选与局部门前进而收口 |
| Implementation R5 M1：route successor 已形成但文档仍要求开发 successor | **已关闭并完成后续门。** 全文 current route identity 已统一为 `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`；完整三提交结果范围已获代码 R3 0／0／0与独立 verify R3 `PASS`，且已内容等价进入bridge successor `088d66d…` | 四文档checkpoint后回放现有successor第二片`088d66d…`；不得沿用旧R2 verdict，也不得只摘source尾提交 |
| Current-main merged-state M1：空reasoning的stream／non-stream归一化漂移 | **按仲裁撤销，Acceptance 最终状态已恢复。** [空 reasoning 语义仲裁](../../tmp/260807-arbitrate-empty-reasoning.md)确认 empty item 必须形成一个 `thinking=""` bare carrier block；`1cde3d58…` 的 stream／non-stream 行为在该轴正确，旧 verify 的零-block expected 与 `FAIL` 被 supersede | Acceptance current `6457b896…` 已恢复`FINALIZED_ACCEPTANCE_ORACLE`并获R2 0／0／0；Semantic R2／verify R2已证明该合同保持；产品仍为`UNVERIFIED` |
| Current-main merged-state M2：parser静默接受冲突authoritative lifecycle值 | **已关闭。** `1cde3d58…` 已为 function arguments 与 reasoning summary 冲突增加 typed protocol error并保留 done-only 正样本；successor `f5bca39…` 进一步统一 unknown summary typed reject并补真正 function item-done-only 回归 | [Semantic 代码 R2](../../tmp/260807-review-code-semantic-parity-r2.md)为 0／0／0且可 squash，[verify R2](../../tmp/260807-verify-semantic-parity-r2.md)为 `PASS`；其完整range已进入bridge successor第一片`04bdfcb…`，四文档checkpoint后回放并完成main-side gate |
| Semantic parity 新 M3：未知 reasoning summary part 两路一收一拒 | **已关闭。** Successor `f5bca39…` 在 stream 端统一 unknown part typed reject，并补同一 malformed fixture 与 function item-done-only 回归；空语义仲裁轴保持不变 | 精确绑定 `f5bca39…` 的 R2 为 0 blocker／0 major／0 minor，verify R2 为 `PASS`，当前可 squash；不得外推为完整 bridge `PASS` |
| Route header 与 hooks lifecycle | **Header 与 hooks 两轴均已关闭。** `44808b7d…` 在共享 header policy 边界关闭 header 缺陷；`dd376d6…` 进一步为 capability／override／stream 等 pre-attempt typed reject建立统一 failure finalizer。[代码 R3](../../tmp/260807-review-code-route-happy-r3.md)对完整三提交结果范围给出0／0／0并允许squash，[独立 verify R3](../../tmp/260807-verify-route-happy-r3.md)为`PASS` | 完整route range已内容等价进入successor第二片`088d66d…`；四文档checkpoint后按既定顺序回放，不得只摘source尾提交；完整stream与bridge继续由Acceptance承担 |
| Block delivery R1 两major＋一minor | **已关闭。** `e506bf87…` 的 typed block ordering、source／terminal事实与串行写入合同已由[代码 R2](../../tmp/260807-review-code-block-delivery-r2.md)复核为 0／0／0并可 squash | 完整block range已内容等价进入successor第三片`c43db35…`并取得scoped verify `PASS`；四文档checkpoint后在route片main-side gate后回放，真实ASGI／socket、retry、quota与完整产品门继续后补 |
| Graceful timeout＋user installer 组合态 | **旧 M2 证据保留，current 执行载荷已重建。** 旧 `0a93e7f…` 的合并态 review 0 blocker／0 major、独立 verify `PASS` 与最终 replay gate 继续证明历史组合语义和 S3-parent adaptation，但[重建审计](../../tmp/260807-audit-systemd-next-rebuild.md)已否决直接回放其含 Plan 的提交。Current `integrate/260807-systemd-code-only@2ec0cb8…` 严格包含 `862f4cfa… → 2ec0cb8…` 两个 non-merge code-only commits，[合并态 review](../../tmp/260807-review-systemd-code-only.md)为 0 blocker／0 major，[独立 verify](../../tmp/260807-verify-systemd-code-only.md)为 `PASS` | 四文档 checkpoint 后重验 main identity、preimage、code-only exact tip 与重叠 paths，按 `862f4cfa… → 2ec0cb8…` 逐片回放。代码提交不得包含 Plan；每片 main-side gate 后 fresh 更新并 checkpoint living Plan。不得回放旧 `91f95f7… → 0a93e7f…`，不得 restore／stash／覆盖并行 WIP，不执行运行态动作 |
| Implementation current R7 M1：successor integration 已形成但全文仍要求未来创建 | **已关闭。** Current successor 固定为 clean `integrate/260807-bridge-successor@c43db35…`，拓扑为 semantic `04bdfcb…` → route `088d66d…` → block `c43db35…`；其 merged-state review 为0 blocker／0 major／0 minor，独立 verification 为 scoped `PASS` | 四文档 current bytes各自取得 checkpoint后，保持三提交边界逐片回放main并执行每片main-side gate／reviewed-source archive；完整stream继续`UNVERIFIED`，本文继续living |

此前 `docs/tmp` 归纳评审的 5 项 major 处置也随最新 merged-state 结论重新对账：

| Major | 当前处置 | 事实边界 |
|---|---|---|
| M1 Reasoning cardinality 状态缺失 | **已关闭并进入 `main`** | Reviewed source `b876e626…` 已归档为 `archive/260807-anthropic-responses-reasoning-cardinality`；对应 main commit 为 `d274f584…`，main-side gate 已通过 |
| M2 Liveness 状态停在待 R3 | **已关闭并进入 `main`** | Reviewed source `f27a8c04…` 已归档为 `archive/260807-anthropic-responses-liveness`；对应 main commit 为 `798ba3e765…`，main-side gate 已通过 |
| M3 Request 状态停在父提交 | **已关闭并进入 `main`** | Reviewed source `fdd2f75f…` 已归档为 `archive/260807-anthropic-responses-request`；对应 main commit 为 `1c13fda4…`，main-side gate 已通过 |
| M4 文档复评汇总陈旧 | **已关闭。空reasoning合同与最终状态均已同步** | Spec `FINALIZED@5e362822…` 不变；Acceptance current `6457b896…` 已恢复`FINALIZED_ACCEPTANCE_ORACLE`并由R2确认为0 blocker／0 major／0 minor。产品仍为`UNVERIFIED`，本文不把文档0／0或局部smoke外推为产品状态 |
| M5 临时报告跨日期命名合同未形成仓库级载体 | **命名合同已承载；Plan R8 历史关闭 R7 阻断，current R11 保持 0 major** | 文档重组 Plan 第 2.5 节已承载实际创建日 `YYMMDD-`、历史报告单一身份与禁止覆盖合同；R11 确认 Plan bytes 自 R10 未变化，generation 0A、post-cut、42 owner 与 living 开放状态未回归。已有 `260806-` 报告及用户明确指定的历史路径不批量改名 |

## 总体进度

| 顺序 | 切片 | 候选／集成 HEAD | 当前 gate | 下一动作 |
|---|---|---|---|---|
| 1 | Reasoning carrier baseline | `main` `ed77c9d191df81c451c25161420515cca52ce6a4` | **已 squash；原 reviewed HEAD 已归档** | 保持既有 archive ref，不移动或 force-update |
| 2 | Reasoning cardinality correction | main `d274f584219f8ae32f59d15d08ac007c45058c8d`；archive `b876e626…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | 保持 archive ref immutable；在 happy 与 route wiring 组合 gate 中继续守住一 item 一 block与 encrypted-only no-loss |
| 3 | Session liveness | main `798ba3e7653b513c3c9c732019e793f828ae0890`；archive `f27a8c04…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | 在后续 stream owner接线中继续守住 cancellation cleanup、primary／secondary failure与资源归零 |
| 4 | Request converter | main `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7`；archive `fdd2f75f…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | Route wiring只在每 attempt `PRE_SEND` 后消费 converter，不建立第二 lifecycle owner |
| 5 | Reasoning carrier v2 checkpoint | main `a0d807fe807629b739ab16c5463f99bc27bc7aac`；archive `8301ee9…` | **已进入 `main`；reviewed source 已归档** | 在完整 route与 echo gate中继续守住项目主 v1 producer、upstream v1 consumer、direct Messages strip与一 item一 block |
| 6 | Non-stream response checkpoint | main `cdc080e1795ee1ac63d589ee00a10acd581b460e`；archive `7ddf173…` | **已进入 `main`并归档；原空reasoning parity major已按仲裁撤销** | 保持one-empty-item／one-bare-block合同；完整error／terminal／History仍按Acceptance补齐 |
| 7 | Stream parser checkpoint | main `a815948ef1b8e739e4bd49e31894be4dffc06950`；archive `73a6aa1…` | **已进入 `main`并归档；authoritative与unknown summary修复已由semantic successor放行** | 四文档checkpoint后回放successor semantic片`04bdfcb…`；后续route／block片消费修复后的parser facts，parser不得自行提交下游 |
| 8 | systemd／cgroup runtime checkpoint | main `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`；archive `49fb198…` | **已进入 `main`；current main 434 tests、Ruff、Pyright通过；未部署** | Graceful-timeout与user-install分别继续强化；安装与 cutover仍由部署门和显式授权独立约束 |
| 9 | Typed route policy checkpoint | main `d913a033252693022f0871f1e92c1b996d05eb71`；archive `84a22c0…` | **已进入 `main`；reviewed source 已归档** | Route-happy只消费 typed decision，handler／transport不得重新推导 precedence或 fallback |
| 10 | Non-stream usage details | main `80bc8f252b46c511f428af1d97159a5980ee9dc9`；archive `aca3ced…` | **已进入 `main`；reviewed source 已归档；current main组合 gate通过** | 在 stream／non-stream parity与History投影中继续验证 cache／reasoning details，不重复实现 usage算式 |
| 11 | Semantic parity 修复 | source `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`；successor slice `04bdfcbf75bfa7e9709d55869c70106c49146db6` | Source 代码R2为0／0／0、verify R2 `PASS`；successor review确认完整range stable patch-id与结果blobs等价 | 四文档checkpoint后作为successor第一片回放main，完成semantic main-side gate并归档reviewed source |
| 12 | Route happy 接线 | source `feat/anthropic-responses-route-happy@dd376d6f1e9dc2997bc2f95d03a352fed4df1412`；successor slice `088d66d3f12bd39be7ce7f61877336f490e7dbdb` | Source完整三提交结果范围代码R3为0／0／0、verify R3 `PASS`；successor review确认完整range stable patch-id与十个结果blobs等价 | 在`04bdfcb…`main-side gate后作为第二片回放main，完成route／hooks／header main-side gate并归档reviewed source；完整stream仍`UNVERIFIED` |
| 13 | Block delivery | source `feat/anthropic-block-delivery@e506bf87318424e4075b6422772ee0c7e9b8694a`；successor slice `c43db35a7a5851225b55ce31b8edbec2cf90917f` | Source R2为0／0／0；successor merged review为0 major，独立verification对parser→delivery／single-writer等范围为`PASS` | 在`088d66d…`main-side gate后作为第三片回放main，完成parser→delivery／single-writer main-side gate并归档reviewed source；保留真实transport、retry与quota后补门 |
| 14 | Bridge successor integration | `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f`；`04bdfcb… → 088d66d… → c43db35…` | Worktree clean；merged-state review 0／0／0；independent verification scoped `PASS`；完整stream `UNVERIFIED` | 四文档checkpoint后保持三提交边界逐片回放，不压成单一不可归因提交；每片重验preimage、执行main-side gate并建立对应archive |
| 15 | Graceful timeout | source `865a5b71210e2436b36786b5de67146939d1e0f5`；current code-only integration commit `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` | Source review 0 blocker／0 major／1 minor；rebuilt merged-state review 0 major且verify `PASS`。旧 `91f95f7…` 仅保留 patch-equivalence 与历史 provenance，不是回放载荷 | 四文档 checkpoint 后作为 code-only 第一片回放 current main；完成 main-side gate 后 fresh 更新并 checkpoint Plan。保留配置优先级判别力 minor，不安装 unit、不操作真实 manager |
| 16 | Rootless user install | source `e16c2a700f23f66535e7347ab7357518eb8e56bd`；current code-only integration commit `2ec0cb81832691685bfe8d98ad03071d2d5e5316` | Source review 0 blocker／0 major／1 minor；rebuilt 第二片保留 S3-parent timeout parity adaptation，merged-state review 0 major且verify `PASS`。旧 `0a93e7f…` 仅保留历史组合与适配 provenance，不是回放载荷 | 在 `862f4cfa…` main-side gate 与 Plan fresh checkpoint 后作为 code-only 第二片回放；完成 gate 后再次 fresh 更新并 checkpoint Plan。保留逐文件原子替换 minor，不操作真实 manager |
| 17 | Graceful＋installer current code-only 集成 | `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`；`862f4cfa… → 2ec0cb8…` | 两提交线性 code-only 组合明确排除 `docs/agents/systemd-runtime/plan.md`；merged-state review 为 0 blocker／0 major，独立 verify 为 `PASS`。旧 `systemd-next@0a93e7f…` 只保留历史 provenance且不得回放 | 四文档 checkpoint 后重验 preimage、exact tip 与路径状态，按 `862f4cfa… → 2ec0cb8…` 逐片回放；每片 gate 后 fresh 更新／checkpoint Plan。不得覆盖 WIP，代码通过不授权安装、部署或 cutover |

Foundations、happy四片、usage与systemd runtime的主树回放均已完成；旧 foundations／happy integrations只保留历史 provenance。Bridge successor 已在 clean `integrate/260807-bridge-successor@c43db35…` 形成 semantic `04bdfcb…` → route `088d66d…` → block `c43db35…` 三片线性组合，merged-state review为0／0／0，独立 verification为scoped `PASS`；完整stream继续`UNVERIFIED`。旧`integrate/260807-bridge-next@a23081c…`绑定失败route范围且不可回放、续写或amend。Current 动作是先让Acceptance、Implementation、Readiness与Systemd Plan四文档各自形成current checkpoint，再保持successor三提交边界逐片回放main、执行每片main-side gate并归档reviewed sources；systemd 只回放 rebuilt code-only `862f4cfa… → 2ec0cb8…`，每片 main-side gate 后 fresh 更新并 checkpoint Plan。旧 `91f95f7… → 0a93e7f…` 明确只作历史 provenance，不得回放。以上进展都不能外推为部署或完整产品`PASS`。Request、cardinality与carrier共同触及reasoning语义，bridge successor回放后的main组合gate仍须机械确认有序block-list API、项目主v1＋upstream v1合法主路径兼容、typed malformed止血及跨片production-chain回归；不得把旧“全malformed Node byte-exact”范围重新带回current gate。

### 当前并行开发线

| 开发线 | Worktree／branch | 建树基线 | 当前事实 | 更新与进入条件 |
|---|---|---|---|---|
| Semantic parity | `/home/xp/src/ghc-api-proxy-py-semantic-parity`；`fix/responses-semantic-parity` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | HEAD `f5bca39ac582911b61d278fd678ec9298ad0c08e`，worktree clean；代码R2 0／0／0、verify R2 `PASS`；完整range已内容等价进入successor `04bdfcb…` | 四文档checkpoint后回放successor第一片`04bdfcb…`，完成semantic main-side gate并建立reviewed-source archive，不外推完整产品`PASS` |
| Route happy | `/home/xp/src/ghc-api-proxy-py-route-happy`；`feat/anthropic-responses-route-happy` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | Clean HEAD `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`；完整三提交结果范围代码R3 0／0／0、verify R3 `PASS`；完整range已内容等价进入successor `088d66d…` | 在`04bdfcb…`main-side gate后回放successor第二片`088d66d…`，完成route／hooks／header gate并建立reviewed-source archive |
| Block delivery | `/home/xp/src/ghc-api-proxy-py-block-delivery`；`feat/anthropic-block-delivery` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | HEAD `e506bf87318424e4075b6422772ee0c7e9b8694a`，worktree clean；R2 0／0／0；完整range已内容等价进入successor `c43db35…` | 在`088d66d…`main-side gate后回放successor第三片`c43db35…`，完成parser→delivery／single-writer gate并建立reviewed-source archive |
| Bridge successor integration | `/home/xp/src/ghc-api-proxy-py-integrate-successor`；`integrate/260807-bridge-successor` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | Clean HEAD `c43db35a7a5851225b55ce31b8edbec2cf90917f`；三片拓扑`04bdfcb… → 088d66d… → c43db35…`；merged review 0／0／0，scoped verify `PASS`；完整stream `UNVERIFIED` | 四文档checkpoint后保持三提交边界逐片回放main；每片重验preimage、完成main-side gate并归档reviewed source，最终重跑main merged-state regression |
| Bridge next integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-next`；`integrate/260807-bridge-next` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 旧HEAD `a23081c5d5f48143bf3015182d8f00e1f6297755`为0 blocker／1 major且verify `FAIL`；只保留失败provenance | 不回放、不续写、不amend，也不把其verdict外推到successor |
| Graceful timeout | `/home/xp/src/ghc-api-proxy-py-graceful-timeout`；`feat/systemd-graceful-timeout` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | Source HEAD `865a5b71210e2436b36786b5de67146939d1e0f5`；current code-only 第一片为 `862f4cfa…`，rebuilt 组合 review 0 major且verify `PASS`。旧 `91f95f7…` 仅作历史 provenance | 四文档 checkpoint 后回放 `862f4cfa…`；main-side gate 后 fresh 更新并 checkpoint Plan。不安装 unit、不操作真实 manager |
| Rootless user install | `/home/xp/src/ghc-api-proxy-py-systemd-install`；`feat/systemd-user-install` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | Source HEAD `e16c2a700f23f66535e7347ab7357518eb8e56bd`；current code-only 第二片为 `2ec0cb8…`，保留 S3-parent adaptation并获 rebuilt 组合 review 0 major、verify `PASS`。旧 `0a93e7f…` 仅作历史 provenance | 在 `862f4cfa…` gate 与 Plan fresh checkpoint 后回放 `2ec0cb8…`；随后再次 fresh 更新／checkpoint Plan。不写真实 user config，不 reload／enable／start manager |
| Systemd code-only integration | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code`；`integrate/260807-systemd-code-only` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | HEAD `2ec0cb81832691685bfe8d98ad03071d2d5e5316`；严格线性 `862f4cfa… → 2ec0cb8…`，明确不含 Plan；review 0 blocker／0 major，verify `PASS` | 四文档 checkpoint 后重验 main identity、preimage、exact tip 与路径状态并逐片回放；每片后 fresh 更新／checkpoint Plan，不 restore／stash WIP，不执行运行态动作 |
| Systemd next integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-next`；`integrate/260807-systemd-next` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 旧 HEAD `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 与 `91f95f7… → 0a93e7f…` 保留 merged review／verify／adaptation provenance；其 Plan patch 已被 current living bytes 超越 | 不回放、不续写、不 cherry-pick，不以 old Plan postimage解冲突；current 动作只使用 code-only integration |

Foundations、happy、usage与systemd runtime checkpoints均已进入current `main`，对应reviewed sources已归档；current 434 tests、Ruff与Pyright全绿。Bridge successor `c43db35…`已clean形成，三提交merged review为0／0／0、scoped verify为`PASS`，因此不再创建另一条integration；四文档checkpoint后直接按`04bdfcb… → 088d66d… → c43db35…`逐片回放并执行main-side gates／archives。旧bridge-next `a23081c…`不可回放。Systemd current 载荷为 code-only `862f4cfa… → 2ec0cb8…`，review 0 major、verify `PASS`；旧 `91f95f7… → 0a93e7f…`只保留历史 provenance且不可回放。不得把candidate存在、scoped `PASS`或临时overlay写成已进入main、完整实现或产品通过。后补边界不因checkpoint、组合绿灯或main-side回归全绿而取消；真实stream仍未生产接线，产品保持`UNVERIFIED`，任何systemd代码收敛也不授权停止现服、安装unit或抢占`4141`。

### 增量开发风格

当前开发节奏明确采用：**先建立结构骨架，完成 happy path 与 smoke，形成单一可评审提交；独立 review 通过后尽快 squash／归档；随后按 Spec／Acceptance 继续补齐边界、失败路径、正反控制与组合态接缝。** 这一节奏把小而清晰的 checkpoint 与完整产品验收分开，避免独立开发线相互等待，也避免把长期 WIP 堆成一个不可审查的大提交。“后补边界”是后续必做阶段，不是删除或降级已接受需求；任何 checkpoint 的报告与提交说明都必须列明未覆盖边界，产品在完整 required gates 通过前保持 `UNVERIFIED`。Bridge successor已形成并取得merged review 0 major与scoped verify `PASS`；执行顺序现为四文档checkpoint后按semantic `04bdfcb…` → route `088d66d…` → block `c43db35…`逐片回放main，不被旧bridge-next `FAIL`阻塞，也不再创建重复integration。

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
| [Acceptance](acceptance.md) | [空 reasoning 定向独立复评 R2](../../tmp/260807-review-acceptance-empty-reasoning-r2.md)；更早的[current-byte终审](../../tmp/260807-review-acceptance-dual-carrier.md)与[Spec／Acceptance联合终审](../../tmp/260807-review-spec-acceptance-current.md)只绑定旧bytes | Current `6457b896…`已把`NS-03`固定为one-empty-item／one-bare-block，状态为`FINALIZED_ACCEPTANCE_ORACLE`，并取得blocker 0、major 0、minor 0；产品继续`UNVERIFIED` | 作为current验收oracle继续实施；不得把文档0／0外推为产品`PASS` |
| [Research](research.md) | [外部变化只读复核](../../tmp/260807-review-research-external-change.md) | blocker 0、major 0；current Research 可提交，route 作用域只覆盖 Anthropic `/v1/messages` bridge，不改变 native Responses 公共入口 | 无待修；Research 始终不产生 behavior expected |
| [文档重组计划](../documentation-restructure/plan.md) | current [独立定向终审 R11](../../tmp/260807-review-doc-migration-plan-r11.md) | R11 为 blocker 0、major 0、minor 0；确认 Plan bytes 自 R10 未变化，generation 0A、post-cut、42 owner与living开放状态均未回归 | 可继续执行并保持 living；不表示文档迁移收口，后续 identity／generation／certificate／action 漂移仍按 Plan 自身 gate 重判 |
| [Service cutover plan](../service-cutover/plan.md)／[systemd runtime plan](../systemd-runtime/plan.md)／[readiness](../service-cutover/readiness.md) | [Systemd 重建审计](../../tmp/260807-audit-systemd-next-rebuild.md)；[code-only review](../../tmp/260807-review-systemd-code-only.md)；[code-only verify](../../tmp/260807-verify-systemd-code-only.md)；current [Readiness](../service-cutover/readiness.md)；其他历史报告继续按绑定 bytes 保留 | Current rebuilt code-only `862f4cfa… → 2ec0cb8…` 为 0 blocker／0 major、verify `PASS`，Plan 不在代码提交内；旧 `91f95f7… → 0a93e7f…` 只保留历史 provenance且不得回放。部署仍保持 `NO_CUTOVER` | 四文档 current checkpoint 后按 code-only 两片回放并执行 main-side gate；每片后 fresh 更新／checkpoint living Plan。任何文档／代码绿灯都不授权安装、部署或 cutover |
| [README](README.md) | [R2](../../tmp/260806-review-bridge-readme-r2.md)；Architecture [裁决矩阵终审](../../tmp/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审确认用户可从 README 开始按阅读顺序进入五份文档；该结论只覆盖 Architecture 用户阅读入口，不是 README 全量新复评或产品状态证据 | 保持 current 导航与 Architecture 待用户裁决边界一致，不传播旧 Acceptance verdict |
| 本文 | [Implementation current R7](../../tmp/260807-review-implementation-current-r7.md)绑定上一内容身份并给出0 blocker／1 major／0 minor | R7唯一major已关闭：clean successor `c43db35…`及`04bdfcb… → 088d66d… → c43db35…`拓扑已同步；merged review为0／0／0，scoped verify为`PASS`，完整stream仍`UNVERIFIED` | 本轮新bytes需后续独立定向复评并纳入四文档checkpoint；任何0 blocker／0 major只放行逐片回放与继续living实施，不表示文档收口或产品`PASS` |

新报告不得使用无日期前缀的旧式名称，也不得沿用与实际创建日不符的固定日期；同一对象多轮复评递增 `-rN`，不得覆盖上一轮报告。报告正文绑定完整 commit、文档内容 hash 或两者，不能只写分支名。既有历史报告不因本规则批量改名。

## 收敛与分支归档策略

本节约束当前已知分支的回放与归档，不是 Implementation 的封存条件。完成某一 squash、归档或 merged-state review后，本文仍须记录后续开发线、组合事实和新发现；只有事实本身由更新后的证据支持时，才能改变对应状态。

### 逐片收敛

1. 每个新候选 HEAD 只有在独立复评 blocker 0、major 0，且该 HEAD 的声明范围测试、smoke、lint 与类型检查 gate 通过后，才可进入该片的回放／归档。Foundations、happy、usage与systemd均已完成该轮收敛并进入 `main@80bc8f2…`；其旧 source／integration verdict只作历史 provenance。任一新切片的声明范围先达到 0／0即可按其剩余 gate收敛，不等待完整 bridge；独立验收缺口与后补边界继续单独登记，不因回放消失。
2. 每次 shell 操作先 gate `/home/xp/src/ghc-api-proxy-py` 的物理 root、分支 `main` 与 `HEAD == refs/heads/main`；记录当时完整 main HEAD。分支或 integration worktree 的绿色结果不能替代最终 main 组合验证。
3. Spec current hash仍为`5e362822…`；Acceptance current hash为`6457b896…`、状态为`FINALIZED_ACCEPTANCE_ORACLE`且R2定向复评为0／0／0。Foundations、happy、usage与systemd回放已经完成；旧living-index阻断、integration audit与候选回放清单只作历史证据，不再是current gate。
4. Bridge successor已固定为clean `c43db35…`，三提交拓扑为semantic `04bdfcb…` → route `088d66d…` → block `c43db35…`，merged review为0／0／0，scoped verify为`PASS`。Acceptance、Implementation、Readiness与Systemd Plan四文档各自形成current checkpoint后，保持三提交边界逐片回放main；每片先重验preimage，再执行对应main-side gate并建立reviewed-source archive，最终重跑main merged-state regression。旧`a23081c…`不得复用、续写或amend。任何一线需要越过职责边界时，先记录公共合同并机械对账，禁止各建一个semantic normalizer、stream／finalize owner或header policy旁路。
5. Graceful-timeout与user-install已从current main重建为不含Plan的`integrate/260807-systemd-code-only@2ec0cb8…`，提交顺序为`862f4cfa… → 2ec0cb8…`，merged-state review为0 blocker／0 major且verify为`PASS`。四文档current checkpoint后，重验main identity、preimage、integration exact tip与重叠paths，按该顺序逐片回放并执行main-side gate；第一片gate后fresh更新／checkpoint Plan，第二片只能从该新main继续，gate后再次fresh更新／checkpoint Plan。旧`91f95f7… → 0a93e7f…`只保留历史组合语义与适配provenance，因携带过时Plan patch而不得回放、续写或作为冲突postimage。不得restore／stash／覆盖并行WIP，也不执行任何真实manager动作。
6. 当前先完成Acceptance、Implementation、Readiness与Systemd Plan四文档current checkpoint，再按两组收敛推进：bridge线回放已存在successor的`04bdfcb… → 088d66d… → c43db35…`；systemd线只回放code-only`862f4cfa… → 2ec0cb8…`并在每片gate后fresh更新／checkpoint Plan。两组都逐片重验preimage、执行main-side gate并归档reviewed source。任何局部review、阶段`PASS`、smoke、434 tests或归档都不改变产品`UNVERIFIED`或部署`NO_CUTOVER`；只有完整bridge按current Acceptance required gates取得实证，产品verdict才可升级。

### 保留评审证据与归档

- Squash 前不强制改写候选分支。若复评要求继续修复，在活动分支追加提交并对新的完整 HEAD 重新评审；旧报告永远只绑定其原 HEAD。
- 每片回放并完成 main侧验证后，为**最终独立评审通过的 pre-squash HEAD**创建 immutable archive ref。现有 reasoning archive保持指向 `d90c90d…`；foundations refs精确为 `archive/260807-anthropic-responses-reasoning-cardinality@b876e62…`、`archive/260807-anthropic-responses-liveness@f27a8c0…` 与 `archive/260807-anthropic-responses-request@fdd2f75…`；happy／usage refs精确为 `archive/260807-reasoning-carrier-v2@8301ee9…`、`archive/260807-responses-anthropic-nonstream@7ddf173…`、`archive/260807-responses-stream-parser@73a6aa1…`、`archive/260807-anthropic-responses-route-policy@84a22c0…` 与 `archive/260807-nonstream-usage-details@aca3ced…`；systemd ref精确为 `archive/260807-systemd-runtime@49fb198…`。不得用 integration commit替代 reviewed feature HEAD。对应 feature worktree／branch clean且 archive ref精确后，可随该片逐片清理。
- Archive ref 必须在移除 worktree 与活动 `feat/*` 分支之前创建并机械验证精确指向 reviewed HEAD。Archive ref 是只读追溯证据，不代表可部署主线；创建后不得 force-update。若归档后发现新缺陷，从正确基线建立新活动分支与新评审轮，不移动旧 archive ref。
- 删除 feature worktree 或其活动分支前必须同时确认：该片 archive ref 精确；main 包含该片 squash 语义；该片 main-side gate 通过；feature worktree clean。任一条件不满足都停止清理，且不得用整文件 restore 或强制删除掩盖状态。
- 历史 foundations／happy integration worktree／branch不按单片清理。其组合语义已按序进入current `main`，main-side gate与archive refs均已完成；只有另行机械确认integration HEAD、提交清单和worktree clean后才允许移除历史载体。本轮文档更新不声称该清理已执行。
- Archive refs至少保留到相关merged-state review与长期文档收敛完成；之后是否删除由用户另行决定。本轮文档更新不创建、移动或删除任何ref／worktree／分支。

### 回滚

Current main上的foundations、systemd runtime、happy与usage均保持独立语义提交；出现组合回归时先定位到引入缺陷的最低共同层，再按提交依赖逆序形成显式revert，不把“最新提交”自动当作根因，也不整文件恢复相邻切片。原reviewed HEAD仍由archive ref保留；回滚只改变main上的集成提交，不移动archive ref，也不覆盖评审证据。活动bridge锚点为clean successor `c43db35…`及其semantic `04bdfcb…`、route `088d66d…`、block `c43db35…`三片；current systemd锚点为code-only `2ec0cb8…`及其第一片`862f4cfa…`，reviewed source archive targets仍为`865a5b7…`与`e16c2a7…`。旧bridge失败组合`a23081c…`与旧systemd组合`91f95f7… → 0a93e7f…`只保留provenance，不得复用、续写、amend或回放。四文档checkpoint与每片preimage／main-side gate任一失败时停止后续回放；尤其不得为清洁工作树而restore／stash并行文档WIP。

## 下一步

以下是 current snapshot 的执行顺序，不是把 Implementation 收口的一次性清单。任一步产生新代码、评审结论、回放结果、合并关系或新发现，都先把本文更新到 current 事实，再继续后续步骤；0 blocker／0 major只放行继续实施，不终止该更新循环。

1. **形成四文档current checkpoint**：分别固定并复核`docs/agents/anthropic-responses-bridge/acceptance.md`、本文、`docs/agents/service-cutover/readiness.md`与`docs/agents/systemd-runtime/plan.md`的current bytes、独立复评结论和living边界；只有四者均达到各自0 blocker／0 major checkpoint后才进入代码回放。Checkpoint只放行继续执行，不表示文档收口、产品`PASS`、部署完成或cutover授权。
2. **按successor三片逐片回放main**：固定clean `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f`及`04bdfcb… → 088d66d… → c43db35…`拓扑，不创建另一条integration，也不使用旧`a23081c…`。先回放semantic `04bdfcb…`并执行semantic定向、交叠、全仓pytest、Ruff、Pyright与独立oracle；再回放route `088d66d…`并执行真实ASGI hooks／header gate；最后回放block `c43db35…`并执行parser→delivery／single-writer gate。每片回放前重验preimage，回放后建立对应reviewed-source archive；三片完成后重跑main merged-state smoke、全仓pytest、Ruff与Pyright。
3. **按systemd code-only两片逐片回放main**：四文档checkpoint完成后，固定`integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`，重验main identity、各片preimage、重叠paths的HEAD／index／worktree状态与integration exact tip。门通过后按`862f4cfa55b124ef9ad21ff2ded2b944ee3307bc → 2ec0cb81832691685bfe8d98ad03071d2d5e5316`逐片回放，每片执行main-side tests、Ruff、Pyright及timeout／dry-run parity gate；第一片通过后fresh更新并checkpoint living Plan，第二片从该新main继续，通过后再次fresh更新并checkpoint Plan。代码提交不得包含Plan；两片成功后archive targets固定为reviewed sources`865a5b71210e2436b36786b5de67146939d1e0f5`与`e16c2a700f23f66535e7347ab7357518eb8e56bd`。旧`91f95f7… → 0a93e7f…`不得回放；不得restore／stash WIP，也不得执行运行态动作。
4. **按current Acceptance完成完整替代验收**：Acceptance current `6457b896…`已恢复`FINALIZED_ACCEPTANCE_ORACLE`并获R2 0／0／0。Bridge三片进入main后验证single owner、每attempt转换、stream／non-stream共享语义、header边界、完整block delivery、retry frontier、History、approval、hooks、tokenization、cancel、backpressure、quota、HTTP／WS parity、正反控制、live canary、capture corpus与local fault。Systemd code-only两片回放后重新验证rendered unit与runtime timeout同源、default dry-run无副作用。完整产品在current Acceptance全部required gates通过前保持`UNVERIFIED`；部署状态继续保持`NO_CUTOVER`，没有显式运行态授权时不安装unit、不改变manager状态、不操作生产`4141`，也不触碰独立`cc-daemon`生命周期。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/streaming/keepalive.py` 的 cleanup 路径 | cancellation 与资源清理所有权交叠；secondary failure 可能覆盖 primary failure | `f27a8c0` 已修且 R3 0／0；保留 cancellation-storm、cause chain、资源归零与无 orphan task 为组合回归 gate |
| `src/app/protocols/anthropic_responses.py` 的 tool-name／unknown-field／carrier／thinking 边界 | 多项 fail-closed 合同集中在单一 converter，相邻修复容易互相遮蔽 | `fdd2f75` 已获 R3 0／0；最终组合继续运行 request 行为 gate，不以父提交 PASS 自动覆盖新基线 |
| `src/app/anthropic/thinking/responses_reasoning.py` 的双分支修改 | cardinality 与 request decoder hardening 修改同一文件，错误回放来源会恢复旧聚合 API | 完整 integration 链已按 cardinality → request 顺序完成语义合成并通过 R2；current main 与后续 route／delivery 组合继续联合测试，禁止改用 feature 原提交链或整文件覆盖 |
| request 验收报告与主仓正式 Spec | 两个 oracle 对 server-tool 支持给出相反 expected | 已裁决 reject；外部 F1 撤销，不再作为待实现项 |
| `src/app/routes/anthropic.py`、`src/app/anthropic/client.py` 与 `src/app/pipeline/executor.py` | Typed route policy、request／response converters已在main，但生产route仍固定Messages transport，stream仍raw passthrough；“primitives存在”容易被误写成“完整route已接” | Route-happy必须从真实`/v1/messages`失败测试接线，只消费typed decision并保持single pipeline owner；完整route完成前产品保持`UNVERIFIED` |
| Route-happy与block-delivery的共享生命周期接缝 | 两线都可能触及stream response、cleanup、History与finalize，若各自就地接通会形成第二sink或第二finalize owner | 预先冻结职责：route-happy拥有route／attempt／exchange／nonstream happy，block-delivery拥有sequencer／delayed start／renderer／sink／frontier；successor merged review已扫描body writer与finalize入口并确认为0 major，scoped verify为`PASS`。四文档checkpoint后按`04bdfcb… → 088d66d… → c43db35…`逐片回放，不续写`a23081c…`；真实stream接线后仍需新E2E与正控 |
| `src/app/anthropic/client.py` 与 response header policy 的Responses adapter边界 | 旧Route candidate代码review通过，但真实ASGI verify证明通用Anthropic header policy在默认非strict模式下会放行Responses-specific header；局部marker blacklist会继续漏掉等价拼写 | `44808b7d…`已在共享Responses header归一化边界关闭该轴，R2 0 major且verify R2 `PASS`；successor `088d66d…`保持该合同，merged review／scoped verify与回放后的main-side gate继续守success／error header矩阵 |
| `src/app/openai/responses_stream_parser.py` 与未来delivery链 | Parser已产生semantic facts，但尚无production sequencer；若按完成顺序直接yield，会重排block或泄漏未完成delta | Block-delivery只把parser facts作为输入，使用continuous-prefix sequencer和真实下游观测gate；parser不得知道commit或直接写body |
| `src/app/anthropic/thinking/responses_reasoning.py` 与 `src/app/openai/responses_stream_parser.py` 的空reasoning判定 | 同一semantic rule双实现曾发生漂移；代码review与旧verify对正确expected冲突 | 仲裁已冻结one-empty-item／one-bare-block并确认`1cde3d58…`该轴正确；撤销零-block门，后续共享normalizer与双路径正反控制不得改变cardinality |
| `src/app/openai/responses_stream_parser.py` 的authoritative lifecycle与summary schema | `1cde3d58…`已拒绝delta／done冲突，但未知summary part仍被stream接受，且function真正item-done-only回归不足 | `f5bca39…`已形成unknown part typed reject与item-done-only回归；代码R2为0／0／0、verify R2为`PASS`，其完整range已进入successor `04bdfcb…`，四文档checkpoint后回放并完成main-side gate |
| `docs/agents/anthropic-responses-bridge/implementation.md` 的current identity与动作 | Route、semantic、block、integration与Acceptance状态在顶部、处置表、进度表、并行线、收敛、下一步和结尾多点复述，successor前进时容易出现弱一致性副本 | 本轮全文同步clean successor`c43db35…`、三提交拓扑、merged review 0 major、scoped verify `PASS`、四文档checkpoint与逐片回放／main-side gates／archives，并以陈旧动作扫描＋全文通读复核；后续优先把顶部current-state入口作为身份真相源 |
| `src/app/pipeline/executor.py` 的pre-attempt failure路径 | `_fail_internal()`旧实现只终结context／History，capability、override与stream等attempt前typed reject未统一发出hooks `ERROR`／`FINALIZE`；局部source测试全绿仍可漏掉single lifecycle合同 | Successor `088d66d…`已建立single-owner统一failure finalizer，merged review与scoped verify精确断言`REQUEST_RECEIVED → ERROR → FINALIZE`及exactly-once History；回放后的main-side gate继续守住该合同，不外推为完整Acceptance |
| `ResponsesStreamParser` item-level `source_order` 与 block-delivery排序坐标 | R1证明旧候选把item order误作block稠密序号 | Source `e506bf87…`与successor `c43db35…`已由review／scoped verify用multi-part、zero-block、较晚item与sparse parts验证typed ordering；main-side gate不得由手工稠密order fixture旁路生产合同 |
| Block delivery terminal／open-source与异步writer | R1证明旧session可越过open source成功terminal，且single writer不等于异步串行 | Successor `c43db35…`的typed terminal与完整operation lock已由merged review／scoped verify复核为0 major／`PASS`；main-side与完整Acceptance继续覆盖真实sink、partial write与retry frontier |
| Reasoning carrier、non-stream response与usage已进入main | 三者局部主线全绿容易掩盖route未接、stream parity与History投影未验收 | Route／delivery组合gate重放项目主v1、upstream v1、multi-item、encrypted-only、usage parity与client echo；434 tests只作current回归，不作完整Acceptance |
| 历史 happy／usage source refs与current main commits | Reviewed source identity与main squash identity不同，后续若从旧source重建会制造第二条实现链 | Archive refs保持immutable且只作provenance；semantic／route／block从`main@80bc8f2…`演进。Systemd current载体是排除Plan的code-only`862f4cfa… → 2ec0cb8…`；旧`91f95f7… → 0a93e7f…`仅保留历史provenance且不得回放 |
| `docs/agents/systemd-runtime/plan.md` 与 systemd 代码提交 | 旧integration把高频living Plan与可复用代码patch绑在同一提交，current Plan超越old postimage后直接cherry-pick会产生冲突并可能回退状态 | Current code-only `862f4cfa… → 2ec0cb8…`明确排除Plan；四文档checkpoint后逐片回放，每片main-side gate后只从当时checkpoint bytes fresh更新并重新checkpoint Plan。旧Plan patch不得回放或用于冲突解法 |
| Systemd source 与 main squash | Source R4绑定 `49fb198…`，main commit为 `cf53334…`；reviewed source与集成提交身份层级不同 | 已以 `archive/260807-systemd-runtime@49fb198…` 保留 source并通过 main gate；仍不得把 main commit外推为安装态或 cutover证据 |
| `contrib/systemd/ghc-api-proxy.service` timeout 与应用shutdown | `TimeoutStopSec`、Uvicorn graceful cap与lifespan cleanup不是同一真相源，unit数值可在代码行为改变后静默漂移 | Graceful-timeout从真实调用链冻结单一公式并用低时长执行测试机械对账；user-install不得复制未冻结常量 |
| System unit与未来rootless user unit | 直接复制模板会让`User=`、paths、targets、slice与timeout各自漂移；install helper又容易越过dry-run边界改变manager状态 | User-install使用共享typed render inputs与明确的system／user渲染合同，默认dry-run；隔离测试证明无真实config或manager副作用，并与graceful-timeout做merged-state复核 |
| `localhost:4141` 的双运行时目标 | 当前 Bun 裸进程与未来 systemd socket 都可能成为 listener owner，直接启动会端口争用或误判新服务已接管 | Cutover 明确设置唯一 socket owner、旧 listener 释放、health 与 rollback gate；代码 review／unit smoke 不外推为运行态切换证据 |

Spec `FINALIZED@5e362822…`继续提供current行为oracle；Acceptance current `6457b896…`已恢复`FINALIZED_ACCEPTANCE_ORACLE`并获R2 0 blocker／0 major／0 minor。完整产品仍为`UNVERIFIED`。Foundations三片、happy四片、non-stream usage与systemd runtime均已进入`main@80bc8f252b46c511f428af1d97159a5980ee9dc9`，各reviewed source已由对应`archive/*` refs保留。本轮在该HEAD实跑全仓434 tests，并以collect-only交叉核对同为434；Ruff与Pyright全绿，但这些结果只证明current主树回归，不等于完整Acceptance。Current bridge successor保持clean `integrate/260807-bridge-successor@c43db35…`，拓扑固定为semantic `04bdfcb…` → route `088d66d…` → block `c43db35…`，merged review为0 blocker／0 major／0 minor，独立verification为scoped `PASS`；真实Responses stream仍未生产接线，完整stream继续`UNVERIFIED`。Current systemd执行载荷为排除Plan的`integrate/260807-systemd-code-only@2ec0cb8…`及`862f4cfa… → 2ec0cb8…`，merged review为0 blocker／0 major、独立verify为`PASS`；旧`91f95f7… → 0a93e7f…`只保留历史provenance且不得回放。下一动作是Acceptance、Implementation、Readiness与Systemd Plan四文档current checkpoint后，分别逐片回放bridge successor与systemd code-only链，执行每片main-side gates并归档reviewed sources；systemd每片后fresh更新并checkpoint Plan，不再创建integration。任何candidate、局部review、verify范围结论或临时overlay都不表示已进入main或完整产品通过。Deployment plans与readiness持续动态修订，任何代码或计划绿灯都不授权安装、部署或cutover。本文保持living、不收口，并随每次实现、评审、组合与部署事实继续更新；任何局部verdict、阶段`PASS`、434 tests或archive都只放行其绑定范围，不等于计划收口、已完成cutover或完整bridge产品`PASS`。