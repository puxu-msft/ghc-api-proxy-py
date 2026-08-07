# Anthropic Messages ↔ OpenAI Responses bridge 实施状态与动态收敛计划

## 文档状态

- **用途与状态**：本文是 Implementation living document，记录正式规格进入实现后的渐进切片、评审门、待修项、下一最小切片、并行开发线与本地分支收敛策略。开始开发不等于本文收口；一次提交也只是可追溯 checkpoint，不把本文转成只读历史快照。
- **事实快照**：2026-08-07。主仓为 `/home/xp/src/ghc-api-proxy-py`，current `main` HEAD 为 `b91e58a29324b11840002efc53ed6f869b800c39`。本轮每次 shell 调用都在同一调用内验证物理 repo root、分支 `main`、`HEAD == refs/heads/main` 与该完整 SHA；未来 `main` 前进后，living document 必须先记录新锚点并重建 gate，不得把本快照冒充未来 HEAD。
- **权威边界**：[规格](spec.md)是唯一行为 oracle；任何 required behavior 与 policy-dependent expected 只能来自 Spec。2026-08-07 carrier 双格式重裁已由 [carrier 双格式定向评审](../../tmp/260807-review-spec-carrier-dual-format.md)给出 blocker 0、major 0、minor 0，Spec 源文档现已恢复 `FINALIZED`，current SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。Implementation 不得自行改写该双格式合同。[独立验收规范](acceptance.md)只把 Spec 合同转成可执行 gate，不得自行补充 expected；空 reasoning 状态与 provenance 同步后的 current SHA-256 为 `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`，状态为 `FINALIZED_ACCEPTANCE_ORACLE`。[Acceptance 空 reasoning 定向独立复评 R2](../../tmp/260807-review-acceptance-empty-reasoning-r2.md)已对该精确内容身份给出 blocker 0、major 0、minor 0并允许 checkpoint；该状态只批准使用 current Acceptance oracle，不构成候选产品或完整 bridge 的 `PASS`，产品继续为 `UNVERIFIED`。[目标架构](architecture.md)仅是非规范实现参考；`D-ARCH`／`D-MIGRATION` 未经用户接受前不产生 behavior 或 expected。[研究](research.md)保留来源、可移植机制与不可照搬项，不是行为或验收 oracle。
- **更新纪律**：本文必须随代码事实、独立评审、main 回放、并行线合并、新发现与计划调整持续更新；每次更新都绑定当时可复验的 commit、worktree、报告或 gate，不把计划中的动作写成已实现事实。状态变化先更新对应切片／开发线与下一步，再同步汇总；过时结论保留其历史绑定或明确降级，不冒充 current verdict。
- **评审语义**：本文某一内容身份取得 blocker 0、major 0，只表示在该轮范围内没有已知阻断项、可以继续实施或形成 checkpoint commit；不表示 Implementation 已定稿、实施已完成、后续不再修改，也不替代新代码、新组合态和新文档 bytes各自所需的复评。后续事实或发现改变本文时，living document 应继续修订，并对新增或改写内容执行相称的定向复评。
- **当前 foundations、happy、usage 与 bridge 主树状态**：foundations 三片、happy 四片与 non-stream usage details 均已进入 `main`。四文档 current checkpoint 已作为 `9fd6bba9da968819340f103be1971cf8da395f56` 进入主树；随后 semantic parity、route happy 与 block delivery 分别作为 `bfc461f57a507059c5c7b098e0616e7882f7333d`、`86b6cc3e72c0312ea8e93940513ee55e290da245`、`b91e58a29324b11840002efc53ed6f869b800c39` 线性进入 `main`，且三片各自的 main-side gate 与 reviewed-source archive 已完成。Current `main@b91e58a…` 的全仓 gate 记录为 468 tests、Ruff 与 Pyright 全绿；468 是本次主线 gate 的 runner 口径，本轮文档更新未以第二原理重新计数。该组合回归只证明 current 主树，不外推为完整 Acceptance 或产品 `PASS`。
- **当前 main merged-state 评审与并行 non-stream 修复**：[current main successor 独立代码评审](../../tmp/260807-review-main-successor-resume.md)精确绑定 `main@b91e58a29324b11840002efc53ed6f869b800c39`，结论为 `0 blocker／2 major`：production Responses route 尚未把 resolved model 的 reasoning capability facts 传给 request converter，且 non-stream normalized response／usage／conversion facts 尚未进入 History 投影。[同一 main 的 scoped 独立验收](../../tmp/260807-verify-main-successor-resume.md)只对 semantic parity、真实 non-stream happy／error／hooks 与 block-delivery skeleton 给出范围内 `PASS`，完整产品仍为 `UNVERIFIED`；两份结论范围不同，不冲突。两项 major 已分别建立并行修复线：`fix/responses-reasoning-capability` 已形成基于 `b91e58a…` 的 clean candidate `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，[R2 独立代码评审](../../tmp/260807-resume-review-reasoning-capability-r2.md)为 `0 blocker／0 major`并明确可进入 squash，[独立验收](../../tmp/260807-resume-verify-reasoning-capability.md)为 `PASS`；该片尚未进入 current main，须在本轮 Implementation living checkpoint 后执行 main-side squash gate。History 的 `864cfa30e291768cbc7b080fce80d9be4cbf2d83` 在[current 独立终审 R3](../../tmp/260807-resume-review-history-facts-r3.md)仍为 `0 blocker／1 major／0 minor`、不可 squash；其唯一 major 是 success calibration 仍早于可抛错的 retry strategy success callback／最终提交边界，[定向独立验收](../../tmp/260807-resume-verify-history-facts.md)虽为 `PASS`，但只覆盖报告列明的关键路径，不能覆盖 R3 新识别的晚失败窗口。该唯一 major 的修复已进入最终 candidate `fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`；[独立定向终审 R4](../../tmp/260807-resume-review-history-facts-r4.md)为 `0 blocker／0 major／0 minor`并明确可 squash，[独立定向验收 R2](../../tmp/260807-resume-verify-history-facts-r2.md)为 `PASS`，[squash 收口审计 R2](../../tmp/260807-resume-audit-history-squash-r2.md)为 `0 blocker／0 major`并放行 squash。该片尚未进入 current main，仍须 main-side gate 与 merged-state 复核。两线都未进入 current main。
- **当前归档状态**：Foundations reviewed sources 由 `archive/260807-anthropic-responses-reasoning-cardinality@b876e626…`、`archive/260807-anthropic-responses-liveness@f27a8c04…` 与 `archive/260807-anthropic-responses-request@fdd2f75f…` 保留；既有 `archive/260806-anthropic-responses-reasoning@d90c90d7…` 不移动。Happy／usage reviewed sources 由 `archive/260807-reasoning-carrier-v2@8301ee9…`、`archive/260807-responses-anthropic-nonstream@7ddf173…`、`archive/260807-responses-stream-parser@73a6aa1…`、`archive/260807-anthropic-responses-route-policy@84a22c0…` 与 `archive/260807-nonstream-usage-details@aca3ced…` 精确保留。最新三片 reviewed sources 分别由 `archive/260807-responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`、`archive/260807-anthropic-responses-route-happy@dd376d6f1e9dc2997bc2f95d03a352fed4df1412` 与 `archive/260807-anthropic-block-delivery@e506bf87318424e4075b6422772ee0c7e9b8694a` 精确保留。旧 foundations／happy／successor integrations、回放预检与 living-index 阻断仅保留为历史 provenance，不再是 current 下一动作；archive refs 不因主树继续前进而移动。
- **当前 systemd 与部署文档状态**：Systemd prepared squash 已作为 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 `main`，其 reviewed source 由 `archive/260807-systemd-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 精确保留。Graceful-timeout 与 rootless installer 已从 exact `main@b91e58a29324b11840002efc53ed6f869b800c39` 重建为线性 code-only candidate `8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`，位于 `integrate/260807-systemd-rebuild-resume`；前者 parent 为 `b91e58a…`，后者 parent 为 `8cae6c2…`，两提交均排除 `docs/agents/systemd-runtime/plan.md`。[merged-state 独立代码评审](../../tmp/260807-resume-review-systemd-rebuild.md)绑定 exact tip，结论为 `0 blocker／0 major`，明确允许按 `8cae6c2… → d3fabfa…` 顺序逐片 squash 回放，但每片仍须 main-side identity／preimage／tests gate，任一 gate 失败即停；[独立验收](../../tmp/260807-verify-systemd-rebuild-resume.md)给出 `PASS，0 blocker／0 major／3 non-blocking minor`，[第二份独立验收](../../tmp/260807-resume-verify-systemd-rebuild.md)同样给出 `PASS`，并交叉确认474项全仓执行／collect-only、Ruff、Pyright、timeout正控与installer零manager操作。[systemd living Plan current R3 定向复评](../../tmp/260807-resume-review-systemd-plan-current-r3.md)精确绑定 Plan SHA-256 `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f`，结论为 `0 blocker／0 major`、可 checkpoint。该candidate仍未进入main；Plan、代码review与两份PASS均不覆盖真实user manager／cgroup、unit安装、部署或cutover。旧 `862f4cfa… → 2ec0cb8…` 继续只作 old-base 语义 oracle；[current Readiness 独立复评 R2](../../tmp/260807-resume-review-readiness-current-r2.md)精确绑定 SHA-256 `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`，结论为 `0 blocker／0 major`、可继续作为 living checkpoint，整体仍为 `NO_CUTOVER／FOUNDATIONS_ONLY`。
- **当前完整产品边界与 stream candidate**：`86b6cc3e72c0312ea8e93940513ee55e290da245` 已把 Anthropic non-stream 请求的 Responses route 接入生产路径，`bfc461f57a507059c5c7b098e0616e7882f7333d` 与 `b91e58a29324b11840002efc53ed6f869b800c39` 也已把 semantic parser 修复和 typed block-delivery skeleton 放入主树；non-stream Responses happy path与 dual-capability `auto` 保持 Messages leg 的 scoped 回归已成立，但上述两项 non-stream major 尚未进入主树。Stream route 首个 candidate `2087f8f02516136314985f5c48bdee20b2f4b861` 的[首轮独立代码评审](../../tmp/260807-resume-review-code-stream-route.md)为 `0 blocker／8 major`，后继 `bc436af647507df4ea45f3b01ca8942fade4f036` 的[代码复评 R2](../../tmp/260807-resume-review-code-stream-route-r2.md)为 `0 blocker／5 major`，其后 tracked WIP 的[current 定向复评](../../tmp/260807-resume-review-stream-route-current.md)降至 `0 blocker／3 major`；这些均只保留为修复 provenance。Current clean candidate 已前进到 `feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，[独立定向终审 R3](../../tmp/260807-resume-review-stream-route-r3.md)为 `0 blocker／0 major`并明确可 squash，[独立验收 R3](../../tmp/260807-resume-verify-stream-route-r3.md)为限定范围 `PASS`；该片尚未进入 current main，且 retry、quota／resident backpressure、真实 socket partial-write及完整 Acceptance 仍未验证。Current main仍按`responses_stream_not_supported` fail closed，完整stream与完整bridge继续`UNVERIFIED`。
- **备用端口 current layer 与运行态边界**：[备用端口恢复 smoke](../../tmp/260807-backup-port-smoke-resume.md)精确绑定 current `main@b91e58a…`，在隔离 `127.0.0.1:4142` app＋`127.0.0.1:4143` fake Responses upstream 上给出 `PASS_CURRENT_LAYER`：health／readiness／config 脱敏、真实 non-stream Anthropic→Responses→Anthropic、current stream fail-closed与自建进程清理均通过。[备用端口 smoke R2 后续计划](../../tmp/260807-resume-backup-port-smoke-r2.md)及其 `0 blocker／2 major` [独立复评](../../tmp/260807-resume-review-backup-port-smoke-r2.md)只保留历史 provenance。Current [备用端口 smoke R3 计划](../../tmp/260807-resume-backup-port-smoke-r3.md)精确 SHA-256 为 `2bf1dbd5c977728be802d818b752f33a626f98b0382b3c993cd1b0ea1f061821`，[独立复评](../../tmp/260807-resume-review-backup-port-smoke-r3.md)为 `0 blocker／0 major`，已关闭 CLI credential／raw cmdline 旁路并设置施工阶段 A 后同一完整 stream candidate 独立 `0 blocker／0 major` 的 Phase 0 硬门。`f3922a9…` 的 R3 只放行 stream-route 自身进入 squash，不满足该完整 candidate 门；所需 harness 与 safety tests 尚未实现，后续仍须先执行施工阶段 A，再对包含 stream 实现、harness 与 tests 的完整 candidate 复评。计划当前保持 `PLAN_ONLY／NOT_RUN`，本轮未创建 smoke 临时根、未启动 fake／app、未执行 `STREAM-MERGE-00`～`10`。任何后续执行仍须按 R3 Plan 从施工阶段 A 与 Phase 0 重新绑定 exact candidate 及运行前置，不能把 plan review 或 stream 定向 `PASS`冒充完整 candidate 复评或 smoke 已运行。`PASS_CURRENT_LAYER`仍只覆盖current fail-closed层。旧 Bun PID `1623` 在既有 smoke 前后继续持有双栈 `4141`、cgroup 为 `/init.scope`且未被 signal；部署保持 `NO_CUTOVER`。
- **当前 merged-state 结论**：[current main happy／usage merged-state 独立评审](../../tmp/260807-review-main-happy-usage.md)绑定旧 `main@80bc8f2…` 的历史 2 major已由语义仲裁及 semantic parity修复关闭；四文档 checkpoint `9fd6bba…` 后，semantic、route 与 block 三片已按 `bfc461f… → 86b6cc3… → b91e58a…` 进入主树并完成各自 main-side gate／archive。旧 clean successor `04bdfcb… → 088d66d… → c43db35…` 与其 merged review／scoped verification继续证明来源和组合语义，但不再是待回放载荷。Current main 的 468 tests、Ruff 与 Pyright全绿只证明现有组合回归；完整 Responses stream production wiring仍未形成，产品保持 `UNVERIFIED`。
- **证据边界**：`docs/tmp` 报告只绑定各自写明的文档内容身份或代码 HEAD，不是长期状态真相源。本文只保留 verdict、仍有效的 gate 与裁决结果，不复制复现细节或长探针输出。后续新建报告使用实际创建日的 `YYMMDD-` 前缀，同一对象复评追加 `-rN` 且不覆盖旧轮次；既有无日期前缀或 `260806-` 报告保持原名。

### 评审 major 处置

[Implementation current 独立定向复评 R4](../../tmp/260807-resume-review-implementation-current-r4.md)绑定本轮修订前的精确 SHA-256 `5be08662048f4f7f71a0eb104b98a7dec6795989fe290bf002cb004d152d1d8f`，给出 `0 blocker／2 major`；表内“Implementation current R4 M1／M2”两行逐项记录本轮关闭处置。此前的[Implementation current 独立定向复评 R3](../../tmp/260807-resume-review-implementation-current-r3.md)只绑定更早 SHA-256 `7134cd99…`并给出 `0 blocker／4 major`，对应“Implementation current R3 M1～M4”四行；[Implementation current 独立定向复评 R2](../../tmp/260807-resume-review-implementation-current-r2.md)又只绑定更早内容身份并给出 `0 blocker／2 major`。更早报告也均只绑定各自旧内容身份。以下处置均已落入本文，但不把本次自述冒充新的独立复评 verdict；本文新 bytes 仍须定向复评：

| Major | 本次处置 | 复评门 |
|---|---|---|
| Implementation R3 M1：Spec／Acceptance 阶段状态陈旧 | **历史处置，已被 2026-08-07 carrier 重裁再次取代。** 当轮曾同步 Spec `FINALIZED` 与 Acceptance R7；current 状态以本表末行、顶部权威边界和“文档复评剩余项”为准 | 历史行不得作为 current 执行依据；后续每次 Spec bytes 变化都必须传播到 Acceptance 绑定与本文状态 |
| Implementation R3 M2：遗漏完整三片 integration branch | **历史处置，现已完成主树回放。** 当轮把 `integrate/260806-bridge-foundations@6a00f6f…`、三个线性 commits、clean worktree、代码 R2 0／0与 verification R2 PASS 写入状态真相源，并把旧 `8e9aef6…` 降为历史 liveness 载体 | Current foundations 已作为 `d274f58… → 798ba3e… → 1c13fda…` 进入 `main`并归档 reviewed sources；历史 integration verdict不得外推为完整产品 `PASS` |
| Implementation R4 M1：Acceptance R6 旧 Architecture 快照被无条件汇总为 current verdict | **历史处置。** Acceptance 当时绑定 Architecture `6de919…` 并重做七域 manifest，R7 对当时文件终审为 0／0；current Spec 后续已发生 carrier 重裁 | R7 不得外推为 current Acceptance 或产品 `PASS`；Spec／Architecture／Acceptance 内容变化时须重新绑定并复评 |
| Implementation R5 M1：本文未同步 Acceptance R7 已完成状态 | **历史处置。** R7 当时的 0／0已同步；current Spec 后续发生 carrier 双格式重裁，故该 verdict 不再覆盖 current Spec／Acceptance 内容对 | 保留为历史评审链，不得据此跳过 current Acceptance 重绑与复评 |
| Living-plan review M1：Spec carrier 重裁后状态陈旧 | **历史处置，current 状态已再次前进。** Carrier 定向评审曾为0／0／0，Spec恢复`FINALIZED@5e362822…`；Acceptance现已重绑并恢复`FINALIZED_ACCEPTANCE_ORACLE@6457b896…` | 本文新bytes仍须复评；current Acceptance依据是精确绑定`6457b896…`的空reasoning R2 0／0／0，不再沿用旧`224b020d…`终审 |
| Implementation current R2 M1：living 状态落后于 Plan／source／systemd／happy integration | **历史处置，已被 stable checkpoint 复评再次取代。** 当轮同步了 Plan R10、source reviews、systemd R3 与 happy `d78b3cd…` 基础状态 | 历史行不得作为 current 执行依据；current 身份与 gate 以本表末行、顶部状态和“下一步”为准 |
| Implementation stable checkpoint M1：遗漏 happy R1／verification、systemd R4 与后继活动线 | **历史处置，已被 current 状态取代。** 当轮同步 happy R1、systemd R4、usage候选与 Plan R11；随后 happy取得 R2 0／0／0，usage取得 review 0／0与范围内 verify `PASS`，systemd进入 `main`并归档 | 历史 checkpoint verdict只解释当时为何可继续，不覆盖本轮 bytes，不表示 living收口或产品 `PASS` |
| Current main 同步：happy／usage 已落地但 living 仍写待回放 | **历史处置，current 状态已继续前进。** 当轮同步 `a0d807f… → cdc080e… → a815948… → d913a03… → 80bc8f2…` 的主线事实、五个 reviewed-source archive refs与当时434项回归 | Current 主线已推进到`b91e58a…`；本行只保留历史口径，不得作为下一动作 |
| Implementation main／happy M1：四条后继线仍被写成基线 WIP | **已关闭，后继状态继续动态同步。** 原评审所指四个首批 candidate commits 为 route `f3a5a768…`、block `e3fceb1c…`、graceful `865a5b71…` 与 installer `e16c2a70…`；其后 route 已形成并放行 hooks successor `dd376d6…`，block 已到 `e506bf8…`并放行，semantic 已形成并放行 successor `f5bca39…`。Systemd 的旧 `0a93e7f1…` 组合只保留历史 provenance，current rebuilt code-only 集成为 `862f4cfa… → 2ec0cb8…` | 三个 bridge source ranges 已内容等价进入 clean successor `04bdfcb… → 088d66d… → c43db35…`并取得 merged review 0 major 与 scoped verify `PASS`；systemd code-only 也已取得 merged review 0 major 与 verify `PASS`。本文继续 living，不因候选与局部门前进而收口 |
| Implementation R5 M1：route successor 已形成但文档仍要求开发 successor | **已关闭并完成主树收敛。** 完整 route source range已获代码 R3 0／0／0与独立 verify R3 `PASS`，内容等价 successor随后作为`86b6cc3e72c0312ea8e93940513ee55e290da245`进入`main` | Route main-side gate已完成，`archive/260807-anthropic-responses-route-happy@dd376d6…`已建立；下一动作不是重复回放non-stream route，而是stream route happy path |
| Current-main merged-state M1：空reasoning的stream／non-stream归一化漂移 | **按仲裁撤销，Acceptance 最终状态已恢复。** [空 reasoning 语义仲裁](../../tmp/260807-arbitrate-empty-reasoning.md)确认 empty item 必须形成一个 `thinking=""` bare carrier block；`1cde3d58…` 的 stream／non-stream 行为在该轴正确，旧 verify 的零-block expected 与 `FAIL` 被 supersede | Acceptance current `6457b896…` 已恢复`FINALIZED_ACCEPTANCE_ORACLE`并获R2 0／0／0；Semantic R2／verify R2已证明该合同保持；产品仍为`UNVERIFIED` |
| Current-main merged-state M2：parser静默接受冲突authoritative lifecycle值 | **已关闭并进入main。** `1cde3d58…` 与 `f5bca39…` 统一 typed reject并补足 done-only 回归；完整range已作为`bfc461f57a507059c5c7b098e0616e7882f7333d`进入主树 | Semantic main-side gate已完成，`archive/260807-responses-semantic-parity@f5bca39…`已建立；stream route切片必须消费该current parser，不另建normalizer |
| Semantic parity 新 M3：未知 reasoning summary part 两路一收一拒 | **已关闭并进入main。** `f5bca39…` 在 stream 端统一 unknown part typed reject，并补同一 malformed fixture 与 function item-done-only 回归；空语义仲裁轴保持不变 | 精确绑定 source 的R2为0 blocker／0 major／0 minor、verify R2为`PASS`；完整range已作为`bfc461f…`进入main并归档，不得外推为完整bridge `PASS` |
| Route header 与 hooks lifecycle | **Header 与 hooks 两轴均已关闭并进入main。** `44808b7d…` 与 `dd376d6…` 的完整range已作为`86b6cc3e72c0312ea8e93940513ee55e290da245`进入主树并完成route main-side gate | Archive精确指向`dd376d6…`；non-stream与dual-capability Messages回归必须在stream route切片继续保留 |
| Block delivery R1 两major＋一minor | **已关闭并进入main。** `e506bf87…` 的 typed block ordering、source／terminal事实与串行写入合同已作为`b91e58a29324b11840002efc53ed6f869b800c39`进入主树并完成block main-side gate | Archive精确指向`e506bf87…`；下一步把current parser／delivery接到真实ASGI SSE，retry、quota与partial-write仍后补 |
| Graceful timeout＋user installer 组合态 | **旧 M2 证据保留，执行基线已再次前进。** `integrate/260807-systemd-code-only@2ec0cb8…` 的 `862f4cfa… → 2ec0cb8…` 两片保持review／verify与非Plan语义provenance，但其base是旧`80bc8f2…`；更旧`0a93e7f…`继续只作历史组合语义和S3-parent adaptation证据 | New-main rebuilt `8cae6c2… → d3fabfa…`已形成并获review 0 major＋两份verify PASS；当前按序执行逐片main-side gate，每片后fresh更新／checkpoint living Plan。禁止direct replay旧链、cherry-pick、old Plan postimage、restore／stash WIP与运行态动作 |
| Implementation current R7 M1：successor integration 已形成但全文仍要求未来创建 | **已关闭并完成回放。** 四文档checkpoint为`9fd6bba…`；successor三片分别内容等价进入main为`bfc461f… → 86b6cc3… → b91e58a…`，每片main-side gate与reviewed-source archive均已完成 | Successor只保留历史provenance；完整stream继续`UNVERIFIED`，本文继续living，下一最小切片为stream route happy path |
| Implementation current 恢复 R2 M1：History facts仍写未提交WIP | **历史状态漂移已关闭，current 状态再次前进。** 旧 candidate `e5db34bc…` 的独立 review 为 `0 blocker／3 major`；修复线随后形成 clean candidate `2e3a6d2022244a6bca0e2db05e079bc27d94a585`并完成R2 | Current R2为`0 blocker／1 major／1 minor`；该历史行不得再被读成“待R2”，current门见下方R3 M1处置 |
| Implementation current 恢复 R2 M2：systemd遗漏candidate-side code review并重复要求组合review／verify | **已关闭。** `d3fabfa…`已有merged-state code review `0 blocker／0 major`与两份exact-tip verification `PASS` | Candidate-side门已闭合；下一动作是按`8cae6c2… → d3fabfa…`逐片执行main-side identity／preimage／tests gate。仍未main、未安装、未部署，不改变`NO_CUTOVER` |
| Capability WIP 首评与 stream R2 current 状态 | **历史同步已被后继证据取代。** Capability 已形成 clean candidate `8bff1c3…`并取得代码review 0 major＋verify `PASS`；stream 的旧 `bc436af…`／tracked-WIP verdict只保留修复 provenance，current clean candidate 已为`f3922a9…` | Capability可在living checkpoint后执行squash gate；stream `f3922a9…`已取得R3代码review 0 major＋限定验收`PASS`，可按current顺序进入squash gate |
| Backup smoke R2 计划状态 | **历史两项major已由R3计划与其独立复评关闭。** R3 SHA-256 `2bf1dbd…`取得`0 blocker／0 major` | Current stream `f3922a9…`已达到自身独立代码0／0并可squash，但不满足施工阶段A后完整candidate的Phase 0门；R3保持`PLAN_ONLY／NOT_RUN`，harness与safety tests尚未实现，后续仍须先完成施工阶段A，再对包含stream实现、harness与tests的完整candidate复评 |
| Implementation current R3 M1：History仍写“待R2” | **已关闭并由后继证据继续前进。** `2e3a6d2…`的R2已同步为`0 blocker／1 major／1 minor`；后继 clean candidate `864cfa3…`已形成并完成R3 | R3仍为`0 blocker／1 major／0 minor`、定向verify为`PASS`；晚失败窗口修复取得最终0 major前，main History major保持open，不得把scoped PASS冒充放行 |
| Implementation current R3 M2：Capability仍写未提交WIP | **已关闭并由后继证据继续前进。** Clean candidate `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`已形成；精确绑定R2代码review为`0 blocker／0 major`，独立验收为`PASS`，明确可进入squash | 先完成本轮Implementation living checkpoint，再对该片执行main-side identity／preimage／tests squash gate；候选绿灯不等于已进入main |
| Implementation current R3 M3：备用端口状态停在R2 | **已关闭。** R3 SHA-256 `2bf1dbd5c977728be802d818b752f33a626f98b0382b3c993cd1b0ea1f061821`已形成并由独立复评确认为`0 blocker／0 major`，R2两项计划major已关闭 | Stream `f3922a9…`的R3代码review只放行该stream-route candidate进入squash，不满足施工阶段A后包含harness与safety tests的完整candidate Phase 0硬门；R3保持`PLAN_ONLY／NOT_RUN`，后续先施工并形成完整candidate，再取得独立0／0复评 |
| Implementation current R3 M4：living checkpoint被排在事实继续变化之后 | **已关闭。** Current执行顺序已改为先对本文新hash定向复评并立即形成living checkpoint，再继续任何代码squash、修复或systemd回放 | Checkpoint只冻结current状态；后续每次事实变化再次更新living文档，不等待全部开发线结束，且不改变`LIVING／UNVERIFIED／NO_CUTOVER` |
| Implementation current R4 M1：History已形成`864cfa3…`但仍写旧身份施工中 | **已关闭。** 全文同步current clean candidate `864cfa30e291768cbc7b080fce80d9be4cbf2d83`、R3 `0 blocker／1 major／0 minor`与定向verify `PASS` | 当前动作是修复R3识别的retry-success／提交边界晚失败窗口并对后继完整身份取得最终0 major；不得回退到`2e3a6d2…`重复施工，也不得把定向PASS外推为可squash |
| Implementation current R4 M2：stream已形成`f3922a9…`但仍写旧tracked WIP | **已关闭。** 全文同步current clean candidate `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`、R3代码review `0 blocker／0 major`与限定验收`PASS`，明确可squash | Living checkpoint与前序main-side gate完成后，按current默认capability→History→stream顺序执行squash；只有机械证明path／preimage不重叠时才可调整非重叠片顺序，且完整bridge仍`UNVERIFIED` |
| History final candidate 同步 | **已放行。** `fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`的R4独立终审为`0 blocker／0 major／0 minor`，独立验收R2为`PASS`，squash收口审计R2为`0 blocker／0 major` | 该candidate可在living checkpoint与capability main-side gate后进入squash；仍须按当时current main执行identity／preimage／tests gate与merged-state复核，不冒充已进入main |

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
| 7 | Stream parser checkpoint | main `a815948ef1b8e739e4bd49e31894be4dffc06950`；semantic修复main `bfc461f57a507059c5c7b098e0616e7882f7333d`；archives `73a6aa1…`、`f5bca39…` | **parser与semantic parity均已进入main、完成main-side gate并归档** | Stream route只消费current parser facts，不建立第二semantic normalizer或直接从parser写ASGI body |
| 8 | systemd／cgroup runtime checkpoint | main `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`；archive `49fb198…` | **已进入 `main`；current main 468 tests、Ruff、Pyright通过；未部署** | New-main candidate`8cae6c2… → d3fabfa…`已获code review 0 major＋两份独立验收PASS但未main；默认按“living checkpoint → capability → History → stream → systemd S3→S4”执行，只有机械证明path／preimage不重叠时才可调整非重叠片顺序；安装与cutover仍由部署门和显式授权独立约束 |
| 9 | Typed route policy checkpoint | main `d913a033252693022f0871f1e92c1b996d05eb71`；archive `84a22c0…` | **已进入 `main`；reviewed source 已归档** | Route-happy只消费 typed decision，handler／transport不得重新推导 precedence或 fallback |
| 10 | Non-stream usage details | main `80bc8f252b46c511f428af1d97159a5980ee9dc9`；archive `aca3ced…` | **已进入 `main`；reviewed source 已归档；current main组合 gate通过** | 在 stream／non-stream parity与History投影中继续验证 cache／reasoning details，不重复实现 usage算式 |
| 11 | Semantic parity 修复 | main `bfc461f57a507059c5c7b098e0616e7882f7333d`；archive `f5bca39ac582911b61d278fd678ec9298ad0c08e` | **已进入main；semantic main-side gate通过；reviewed source已归档** | 在stream production链继续守authoritative、unknown summary、empty reasoning与done-only回归 |
| 12 | Route happy 接线 | main `86b6cc3e72c0312ea8e93940513ee55e290da245`；archive `dd376d6f1e9dc2997bc2f95d03a352fed4df1412` | **non-stream Responses已生产接线；route／hooks／header main-side gate通过；reviewed source已归档** | 下一切片解除Responses stream happy-path拒绝并保持non-stream与dual-capability Messages回归 |
| 13 | Block delivery | main `b91e58a29324b11840002efc53ed6f869b800c39`；archive `e506bf87318424e4075b6422772ee0c7e9b8694a` | **typed parser→delivery骨架已进入main；block main-side gate通过；reviewed source已归档** | 以真实Responses SSE作为输入、ASGI SSE作为sink完成production happy path；真实retry／quota／partial write继续后补 |
| 14 | Bridge successor integration | 历史 `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f`；主树结果 `bfc461f… → 86b6cc3… → b91e58a…` | **三片已分别进入main并各自完成main-side gate／archive；current主线468 tests、Ruff、Pyright全绿；完整stream仍`UNVERIFIED`** | 不再回放或续写successor；stream后继`f3922a9…`已获R3 0 major＋限定verify PASS，可在living checkpoint与前序gate后squash |
| 15 | Non-stream reasoning capability major | `fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`；base `b91e58a…` | **clean candidate已形成；精确绑定R2代码review为0 blocker／0 major，独立验收为PASS，可进入squash；未main** | 本轮Implementation living checkpoint后执行main-side identity／preimage／tests squash gate；完成后更新本文与merged-state状态 |
| 16 | Non-stream History facts major | `fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`；base `b91e58a…` | **R4独立终审为0 blocker／0 major／0 minor，独立验收R2为PASS，squash收口审计R2为0 blocker／0 major；可squash，未main** | Living checkpoint与capability main-side gate后，按当时current main执行identity／preimage／tests squash gate与merged-state复核 |
| 17 | Stream route current candidate | `feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`；parent `bc436af…`；base `b91e58a…` | **clean candidate；R3代码review为0 blocker／0 major并明确可squash；独立验收R3为限定范围PASS；未main，完整stream仍`UNVERIFIED`** | Living checkpoint与前序main-side gate后执行squash；默认排在History之后，只有机械证明path／preimage不重叠时才调整顺序；不外推未验证的retry、quota／resident backpressure、真实socket partial-write |
| 18 | Graceful timeout new-main rebuild | rebuilt `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`；reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5` | **已从`b91e58a…`形成code-only第一片；组合review 0 major＋两份exact-tip verify PASS；Plan排除；未main** | 前序living／bridge门完成后按精确preimage执行第一片main-side gate，失败即停；不安装unit、不操作真实manager |
| 19 | Rootless user install new-main rebuild | rebuilt `d3fabfadfba57af6c2d63e543e3198444777df54`；parent `8cae6c2…`；reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd` | **组合review 0 major＋两份exact-tip独立验收PASS；其中一份0 blocker／0 major／3 minor；未main** | 仅在前序living／bridge门与第一片main-side gate通过后执行第二片identity／preimage／tests gate；不操作真实manager，不外推为安装态 |
| 20 | Graceful＋installer旧 code-only 集成 | 历史 `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`；`862f4cfa… → 2ec0cb8…` | 旧组合明确排除Plan且review／verify通过，但基线已被`9fd6bba… → b91e58a…`推进 | 只作为冻结patch／result-blob oracle；current执行身份改为`8cae6c2… → d3fabfa…`，禁止回放旧链 |

Foundations、happy四片、usage、systemd runtime、四文档checkpoint以及bridge semantic／route／block三片均已进入current `main@b91e58a…`。Current bridge动作是先为本文新bytes取得定向复评并形成living checkpoint，再依次对已获放行的capability `8bff1c3…`、History `b1df8f9…`与stream `f3922a9…`执行squash gate；只有机械证明path／preimage不重叠时才可调整非重叠片顺序。History最终candidate的R4独立终审为0 blocker／0 major／0 minor、独立验收R2为PASS，squash收口审计R2为0 blocker／0 major，现可squash。Systemd candidate`8cae6c2… → d3fabfa…`已获code review 0 major与两份独立验收PASS，Plan `3c639fcd…`也为0 major；在前述living checkpoint与bridge片gate之后按S3→S4逐片执行main-side squash gate。以上candidate与进展都不能外推为部署或完整产品`PASS`。

### 当前活动与历史开发线

| 开发线 | Worktree／branch | 建树基线 | 当前事实 | 更新与进入条件 |
|---|---|---|---|---|
| Semantic parity（已收敛） | source `fix/responses-semantic-parity@f5bca39…` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | main `bfc461f57a507059c5c7b098e0616e7882f7333d`；main-side gate通过；archive `archive/260807-responses-semantic-parity@f5bca39…` | 保持archive immutable；stream route从current main消费语义，不重复建线 |
| Route happy（已收敛） | source `feat/anthropic-responses-route-happy@dd376d6…` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | main `86b6cc3e72c0312ea8e93940513ee55e290da245`；main-side gate通过；archive `archive/260807-anthropic-responses-route-happy@dd376d6…` | 保持non-stream与dual-capability Messages回归；stream route从current main新建切片 |
| Block delivery（已收敛） | source `feat/anthropic-block-delivery@e506bf8…` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | main `b91e58a29324b11840002efc53ed6f869b800c39`；main-side gate通过；archive `archive/260807-anthropic-block-delivery@e506bf8…` | 保持archive immutable；下一切片接真实Responses SSE与ASGI SSE sink |
| Reasoning capability修复 | `/home/xp/src/ghc-api-proxy-py-reasoning-capability`；`fix/responses-reasoning-capability` | `b91e58a29324b11840002efc53ed6f869b800c39` | clean candidate `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`；R2代码review 0 blocker／0 major；独立验收`PASS`；可进入squash | 本轮Implementation living checkpoint后执行main-side identity／preimage／tests squash gate；候选绿灯不冒充main已修 |
| History facts修复 | `/home/xp/src/ghc-api-proxy-py-history-facts`；`fix/responses-history-facts` | `b91e58a29324b11840002efc53ed6f869b800c39` | 最终candidate `b1df8f910c590033e83d5cafcd5e514f12bab937`的R4独立终审为0 blocker／0 major／0 minor，独立验收R2为PASS，squash收口审计R2为0 blocker／0 major；可squash，未main | Living checkpoint与capability main-side gate后，按当时current main执行identity／preimage／tests squash gate与merged-state复核 |
| Stream route happy path | `/home/xp/src/ghc-api-proxy-py-stream-route`；`feat/anthropic-responses-stream-route` | `b91e58a29324b11840002efc53ed6f869b800c39` | clean HEAD `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`；R3代码review为0 blocker／0 major，独立验收R3为限定范围`PASS`，明确可squash | Living checkpoint与前序gate后执行main-side identity／preimage／tests squash gate；默认排在History之后，只有机械证明非重叠才调整顺序；squash后更新本文并做merged-state复核 |
| Bridge successor integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-successor`；`integrate/260807-bridge-successor` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 历史HEAD `c43db35…`已内容等价收敛为main `bfc461f… → 86b6cc3… → b91e58a…` | 不回放、不续写；只保留review／verification provenance |
| Bridge next integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-next`；`integrate/260807-bridge-next` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 旧HEAD `a23081c5d5f48143bf3015182d8f00e1f6297755`为0 blocker／1 major且verify `FAIL`；只保留失败provenance | 不回放、不续写、不amend，也不把其verdict外推到successor |
| Graceful timeout | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`；`integrate/260807-systemd-rebuild-resume` | `b91e58a29324b11840002efc53ed6f869b800c39` | rebuilt S3 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`已形成，Plan排除；组合review 0 major＋两份verify PASS | 前序living／bridge门完成后按精确preimage执行第一片main-side identity／tests gate；失败即停，不安装unit、不操作真实manager |
| Rootless user install | 同一new-main rebuilt worktree／branch | `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` | rebuilt S4／tip `d3fabfadfba57af6c2d63e543e3198444777df54`获组合review 0 major＋两份verify PASS，未main | 前序living／bridge门与第一片main-side gate通过后才执行第二片；保持exact tip与证据绑定，不写真实user config，不操作manager |
| Systemd code-only integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code`；`integrate/260807-systemd-code-only` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | HEAD `2ec0cb8…`的review／verify保留，但不再是current可直接回放载荷 | 只作old-base oracle；current载荷是`8cae6c2… → d3fabfa…`，禁止direct replay／cherry-pick／old Plan postimage |
| Systemd next integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-next`；`integrate/260807-systemd-next` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 旧 HEAD `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 与 `91f95f7… → 0a93e7f…` 保留 merged review／verify／adaptation provenance；其 Plan patch 已被 current living bytes 超越 | 不回放、不续写、不cherry-pick，不以old Plan postimage解冲突；current动作只从新main重建 |

四文档checkpoint `9fd6bba…`、semantic `bfc461f…`、route `86b6cc3…`与block `b91e58a…`均已进入current `main`。真实Responses stream仍未进入main，产品保持`UNVERIFIED`；stream clean candidate `f3922a9…`已获R3代码review 0 major＋限定验收PASS并可squash。History最终candidate `b1df8f9…`已获R4独立终审0 blocker／0 major／0 minor、独立验收R2 PASS与squash收口审计R2 0 blocker／0 major，可squash。Capability `8bff1c3…`已获代码review 0 major＋独立验收PASS，可在本轮living checkpoint后squash。Systemd identity`8cae6c2… → d3fabfa…`已获code review 0 major＋两份独立验收PASS但未main，Plan `3c639fcd…`也为0 major；任何代码收敛都不授权停止现服、安装unit或抢占`4141`。

### 增量开发风格

当前开发节奏明确采用：**先建立结构骨架，完成 happy path 与 smoke，形成单一可评审提交；独立 review 通过后尽快 squash／归档；随后按 Spec／Acceptance 继续补齐边界、失败路径、正反控制与组合态接缝。** 当前先checkpoint本文新bytes；随后capability `8bff1c3…`、History `b1df8f9…`与stream `f3922a9…`按各自已取得的0 major＋PASS依次进入squash gate，默认顺序为capability→History→stream，仅在机械证明path／preimage不重叠时调整非重叠片顺序。产品在完整required gates通过前保持`UNVERIFIED`。

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
| [Service cutover plan](../service-cutover/plan.md)／[systemd runtime plan](../systemd-runtime/plan.md)／[readiness](../service-cutover/readiness.md) | [new-main merged-state review](../../tmp/260807-resume-review-systemd-rebuild.md)；[new-main独立验收](../../tmp/260807-verify-systemd-rebuild-resume.md)；[第二份独立验收](../../tmp/260807-resume-verify-systemd-rebuild.md)；[systemd Plan current R3](../../tmp/260807-resume-review-systemd-plan-current-r3.md)；[Readiness current R2](../../tmp/260807-resume-review-readiness-current-r2.md) | New-main identity`8cae6c2… → d3fabfa…`已获review 0 major＋两份verify PASS，其中一份0 blocker／0 major／3 minor；systemd Plan current `3c639fcd…`与Readiness current `c1e8494e…`均为0 blocker／0 major；candidate未main、未部署，`NO_CUTOVER`不变 | 在Implementation living checkpoint及前序capability／History／stream squash gate后，按S3→S4执行逐片squash main-side identity／preimage／tests gate；只有机械证明非重叠时才可调整前序片顺序，不得使用旧链；任何绿灯都不授权安装、部署或cutover |
| [README](README.md) | [R2](../../tmp/260806-review-bridge-readme-r2.md)；Architecture [裁决矩阵终审](../../tmp/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审确认用户可从 README 开始按阅读顺序进入五份文档；该结论只覆盖 Architecture 用户阅读入口，不是 README 全量新复评或产品状态证据 | 保持 current 导航与 Architecture 待用户裁决边界一致，不传播旧 Acceptance verdict |
| 本文 | [Implementation current 独立定向复评 R4](../../tmp/260807-resume-review-implementation-current-r4.md)绑定修订前SHA-256 `5be08662…`并给出0 blocker／2 major | 本轮仅同步History最终candidate `b1df8f9…`已获R4独立终审0 blocker／0 major／0 minor、独立验收R2 PASS与squash收口审计R2 0 blocker／0 major，可squash。Stream `f3922a9…`与capability `8bff1c3…`均保持review 0 major＋verify PASS可squash；systemd rebuild、backup smoke R3、Readiness与Plan状态不变 | 本轮新bytes须按新hash重新定向复评；达到0 blocker／0 major后立即形成living checkpoint。该checkpoint不表示文档收口、候选进入main、产品`PASS`或部署获授权 |

新报告不得使用无日期前缀的旧式名称，也不得沿用与实际创建日不符的固定日期；同一对象多轮复评递增 `-rN`，不得覆盖上一轮报告。报告正文绑定完整 commit、文档内容 hash 或两者，不能只写分支名。既有历史报告不因本规则批量改名。

## 收敛与分支归档策略

本节约束当前已知分支的回放与归档，不是 Implementation 的封存条件。完成某一 squash、归档或 merged-state review后，本文仍须记录后续开发线、组合事实和新发现；只有事实本身由更新后的证据支持时，才能改变对应状态。

### 逐片收敛

1. 每个新候选 HEAD 只有在独立复评 blocker 0、major 0，且该 HEAD 的声明范围测试、smoke、lint 与类型检查 gate 通过后，才可进入该片的回放／归档。Foundations、happy、usage、systemd runtime以及bridge semantic／route／block均已完成该轮收敛并进入 `main@b91e58a…`；其旧 source／integration verdict只作历史 provenance。任一新切片的声明范围先达到 0／0即可按其剩余 gate收敛，不等待完整 bridge；独立验收缺口与后补边界继续单独登记，不因回放消失。
2. 每次 shell 操作先 gate `/home/xp/src/ghc-api-proxy-py` 的物理 root、分支 `main` 与 `HEAD == refs/heads/main`；记录当时完整 main HEAD。分支或 integration worktree 的绿色结果不能替代最终 main 组合验证。
3. Spec current hash仍为`5e362822…`；Acceptance current hash为`6457b896…`、状态为`FINALIZED_ACCEPTANCE_ORACLE`且R2定向复评为0／0／0。Foundations、happy、usage与systemd回放已经完成；旧living-index阻断、integration audit与候选回放清单只作历史证据，不再是current gate。
4. Bridge successor三片已作为`bfc461f… → 86b6cc3… → b91e58a…`进入main并完成逐片main-side gate／archive；旧`04bdfcb… → 088d66d… → c43db35…`与`a23081c…`均不得再作为current载荷。Stream route successor已从首轮`2087f8f…`、`bc436af…`与tracked WIP前进到clean `f3922a9…`；R3已确认cancel cleanup、空delta authoritative一致性与fixture三项major关闭，代码review为0 blocker／0 major，限定验收为PASS并允许squash。该片仍必须复用current parser／delivery，禁止另建semantic normalizer、stream／finalize owner或header policy旁路；未验证边界继续登记，不得从定向PASS外推完整Acceptance。
5. Graceful-timeout与user-install的old-base `862f4cfa… → 2ec0cb8…`只保留冻结patch、result blob、review与verify provenance。New-main rebuilt identity`8cae6c2… → d3fabfa…`的candidate-side组合review／verify门已由0 major＋两份PASS闭合；当前只按顺序执行每片main-side identity／preimage／tests gate。不得重复组合review／verify，不得使用旧链、restore／stash／覆盖并行WIP，也不执行任何真实manager动作。
6. Current bridge执行面是capability `8bff1c3…`、History `b1df8f9…`与stream `f3922a9…`均已放行待squash；其后继续按Acceptance补disconnect、retry frontier、History、hooks、tokenization、cancel、backpressure、quota、HTTP／WS parity、正反控制、live canary、capture corpus与local fault。任何局部review、阶段`PASS`、smoke、468 tests或归档都不改变产品`UNVERIFIED`或部署`NO_CUTOVER`；只有完整bridge按current Acceptance required gates取得实证，产品verdict才可升级。

### 保留评审证据与归档

- Squash 前不强制改写候选分支。若复评要求继续修复，在活动分支追加提交并对新的完整 HEAD 重新评审；旧报告永远只绑定其原 HEAD。
- 每片回放并完成 main侧验证后，为**最终独立评审通过的 pre-squash HEAD**创建 immutable archive ref。现有 reasoning archive保持指向 `d90c90d…`；foundations refs精确为 `archive/260807-anthropic-responses-reasoning-cardinality@b876e62…`、`archive/260807-anthropic-responses-liveness@f27a8c0…` 与 `archive/260807-anthropic-responses-request@fdd2f75…`；happy／usage refs精确为 `archive/260807-reasoning-carrier-v2@8301ee9…`、`archive/260807-responses-anthropic-nonstream@7ddf173…`、`archive/260807-responses-stream-parser@73a6aa1…`、`archive/260807-anthropic-responses-route-policy@84a22c0…` 与 `archive/260807-nonstream-usage-details@aca3ced…`；最新三片refs精确为`archive/260807-responses-semantic-parity@f5bca39…`、`archive/260807-anthropic-responses-route-happy@dd376d6…`与`archive/260807-anthropic-block-delivery@e506bf8…`；systemd ref精确为 `archive/260807-systemd-runtime@49fb198…`。不得用 integration commit替代 reviewed feature HEAD。对应 feature worktree／branch clean且 archive ref精确后，可随该片逐片清理。
- Archive ref 必须在移除 worktree 与活动 `feat/*` 分支之前创建并机械验证精确指向 reviewed HEAD。Archive ref 是只读追溯证据，不代表可部署主线；创建后不得 force-update。若归档后发现新缺陷，从正确基线建立新活动分支与新评审轮，不移动旧 archive ref。
- 删除 feature worktree 或其活动分支前必须同时确认：该片 archive ref 精确；main 包含该片 squash 语义；该片 main-side gate 通过；feature worktree clean。任一条件不满足都停止清理，且不得用整文件 restore 或强制删除掩盖状态。
- 历史 foundations／happy integration worktree／branch不按单片清理。其组合语义已按序进入current `main`，main-side gate与archive refs均已完成；只有另行机械确认integration HEAD、提交清单和worktree clean后才允许移除历史载体。本轮文档更新不声称该清理已执行。
- Archive refs至少保留到相关merged-state review与长期文档收敛完成；之后是否删除由用户另行决定。本轮文档更新不创建、移动或删除任何ref／worktree／分支。

### 回滚

Current main上的foundations、systemd runtime、happy、usage、semantic、route与block均保持独立语义提交；出现组合回归时先定位到引入缺陷的最低共同层，再按提交依赖逆序形成显式revert，不把“最新提交”自动当作根因，也不整文件恢复相邻切片。原reviewed HEAD仍由archive ref保留；回滚只改变main上的集成提交，不移动archive ref，也不覆盖评审证据。Current bridge锚点为`main@b91e58a…`及semantic `bfc461f…`、route `86b6cc3…`、block `b91e58a…`三片；旧successor、旧bridge-next与旧systemd两组integration只保留provenance。Systemd后续锚点必须是从新main重建出的新提交，不得复用旧integration identity。任一preimage／main-side gate失败时停止后续动作；尤其不得为清洁工作树而restore／stash并行文档WIP。

## 下一步

以下是 current snapshot 的执行顺序，不是把 Implementation 收口的一次性清单。任一步产生新代码、评审结论、回放结果、合并关系或新发现，都先把本文更新到 current 事实，再继续后续步骤；0 blocker／0 major只放行继续实施，不终止该更新循环。

1. **立即形成 living checkpoint**：本轮只修改Implementation。以本文新SHA-256执行定向复评；达到`0 blocker／0 major`后立即形成living checkpoint，再继续任何代码squash、修复或systemd回放。Readiness current `c1e8494e…`为0 major，systemd Plan current `3c639fcd…`为0 major且本轮不改；该checkpoint只冻结current状态，不使Implementation收口，也不改变`LIVING／UNVERIFIED／NO_CUTOVER`。后续每次事实变化再次更新并checkpoint，不等待所有开发线结束。
2. **Squash capability**：living checkpoint完成后，对`fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`执行main-side identity／preimage／tests squash gate。该candidate已获精确绑定代码review `0 blocker／0 major`与独立验收`PASS`；任一main-side gate失败即停。Squash成功后更新本文并做必要的merged-state复核，不把候选证据直接冒充main结果。
3. **Squash History candidate**：capability gate完成并同步living事实后，对`fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`执行main-side identity／preimage／tests squash gate。该candidate的R4独立终审为`0 blocker／0 major／0 minor`，独立验收R2为`PASS`，squash收口审计R2为`0 blocker／0 major`并明确可squash；任一main-side gate失败即停。Squash成功后更新本文并做merged-state复核，不把candidate放行证据冒充main结果。
4. **Squash stream candidate**：History gate完成并同步living事实后，对`feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`执行main-side identity／preimage／tests squash gate。该candidate已获R3代码review `0 blocker／0 major`与独立验收R3限定范围`PASS`；任一main-side gate失败即停。默认顺序为capability→History→stream；只有以current main为基线机械证明path与preimage不重叠时才可调整非重叠片顺序。Squash成功后更新本文并做merged-state复核，不把定向PASS外推为完整stream或产品PASS。
5. **执行systemd逐片squash main-side gate**：`integrate/260807-systemd-rebuild-resume@d3fabfa…`已获merged-state review `0 blocker／0 major`与两份独立验收`PASS`，其中一份为`0 blocker／0 major／3 non-blocking minor`；systemd Plan SHA-256 `3c639fcd…`也已获0 major。在前述living checkpoint与bridge squash gate后，保持Plan排除、报告绑定及S3→S4顺序，逐片执行identity／preimage／tests gate并形成实际squash commit，任一片失败即停；若current main已前进，必须重新机械核对每片preimage与净patch，不得把旧parent链冒充current线性身份。旧`862f4cfa… → 2ec0cb8…`只作oracle；任何仓库绿灯均不授权安装unit、操作真实manager／cgroup、生产`4141`、`cc-daemon`、部署或cutover。
**备用端口阻断边界**：Backup smoke R3 SHA-256 `2bf1dbd…`的独立复评已为`0 blocker／0 major`，但计划保持`PLAN_ONLY／NOT_RUN`。Stream-route candidate `f3922a9…`的R3代码总verdict已达到`0 blocker／0 major`并可squash，但它不含计划要求的harness与safety tests，因而不满足施工阶段A后完整candidate的Phase 0硬门。后续须先执行施工阶段A，形成包含stream实现、harness与tests的完整candidate，再对其全部bytes与接缝取得独立`0 blocker／0 major`；本轮未创建smoke临时根、未启动fake／app、未执行`STREAM-MERGE-00`～`10`。任何后续smoke仍须按R3 Plan重新绑定完整candidate与运行前置。`PASS_CURRENT_LAYER`仍只覆盖`main@b91e58a…`的current fail-closed层，完整产品保持`UNVERIFIED`。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/streaming/keepalive.py` 的 cleanup 路径 | cancellation 与资源清理所有权交叠；secondary failure 可能覆盖 primary failure | `f27a8c0` 已修且 R3 0／0；保留 cancellation-storm、cause chain、资源归零与无 orphan task 为组合回归 gate |
| `src/app/protocols/anthropic_responses.py` 的 tool-name／unknown-field／carrier／thinking 边界 | 多项 fail-closed 合同集中在单一 converter，相邻修复容易互相遮蔽 | `fdd2f75` 已获 R3 0／0；最终组合继续运行 request 行为 gate，不以父提交 PASS 自动覆盖新基线 |
| `src/app/anthropic/thinking/responses_reasoning.py` 的双分支修改 | cardinality 与 request decoder hardening 修改同一文件，错误回放来源会恢复旧聚合 API | 完整 integration 链已按 cardinality → request 顺序完成语义合成并通过 R2；current main 与后续 route／delivery 组合继续联合测试，禁止改用 feature 原提交链或整文件覆盖 |
| request 验收报告与主仓正式 Spec | 两个 oracle 对 server-tool 支持给出相反 expected | 已裁决 reject；外部 F1 撤销，不再作为待实现项 |
| `src/app/routes/anthropic.py`、`src/app/anthropic/client.py` 与 `src/app/pipeline/executor.py` | Non-stream Responses已生产接线，但Responses stream仍被`responses_stream_not_supported`拒绝；route的stream分支只会透传现有Messages上游字节 | Stream route从真实`/v1/messages` ASGI失败测试接线，复用同一`RequestContext`与single pipeline owner；完整stream完成前产品保持`UNVERIFIED` |
| Route-happy与block-delivery的共享生命周期接缝 | 两片虽已进入main，但尚未在production stream路径组合；若route、delivery与ASGI各自finalize会形成第二sink或第二lifecycle owner | Stream route切片只建立一个`DeliverySession`和一个ASGI writer，并让同一`RequestContext`贯穿route→parser→delivery→History／hooks；以真实ASGI E2E与owner identity正控固定接缝 |
| `src/app/anthropic/client.py` 与 response header policy 的Responses adapter边界 | 旧Route candidate代码review通过，但真实ASGI verify证明通用Anthropic header policy在默认非strict模式下会放行Responses-specific header；局部marker blacklist会继续漏掉等价拼写 | `44808b7d…`已在共享Responses header归一化边界关闭该轴，完整route range随后作为`86b6cc3…`进入main；其main-side gate继续守success／error header矩阵，stream route必须复用同一policy |
| `src/app/openai/responses_stream_parser.py` 与 `src/app/delivery/anthropic_sse.py` | Parser与continuous-prefix／single-writer delivery均已在main，但只在独立smoke中组合，尚无production ASGI sink | Stream route只把parser facts交给`DeliverySession`，由delivery拥有排序、render、sink与frontier；parser不得知道commit或直接写body |
| `src/app/anthropic/thinking/responses_reasoning.py` 与 `src/app/openai/responses_stream_parser.py` 的空reasoning判定 | 同一semantic rule双实现曾发生漂移；代码review与旧verify对正确expected冲突 | 仲裁已冻结one-empty-item／one-bare-block并确认`1cde3d58…`该轴正确；撤销零-block门，后续共享normalizer与双路径正反控制不得改变cardinality |
| `src/app/openai/responses_stream_parser.py` 的authoritative lifecycle与summary schema | 历史unknown summary／done-only缺陷已修，但production stream接线可能绕过current parser或在ASGI层降级typed error | `bfc461f…`已进入main并归档；stream route必须调用current parser并把typed protocol／delivery失败映射到同一context终态，不复制弱化解析器 |
| `docs/agents/anthropic-responses-bridge/implementation.md` 的current identity与动作 | Route、semantic、block、integration与Acceptance状态在顶部、处置表、进度表、开发线、收敛、下一步和结尾多点复述，main前进时容易出现弱一致性副本 | 本轮仅把History current身份`b1df8f9…`同步为R4独立终审0 blocker／0 major／0 minor、独立验收R2 PASS与squash收口审计R2 0 blocker／0 major，现可squash；capability`8bff1c3…`与stream`f3922a9…`保持review 0 major＋verify PASS可squash，systemd、Plan、Readiness与backup smoke状态不变；默认顺序为checkpoint→capability→History→stream→systemd逐片。后续优先把顶部current-state入口作为身份真相源 |
| `src/app/pipeline/executor.py` 的pre-attempt failure路径 | 统一failure finalizer已进入main，但stream happy path将把现有typed reject替换为真实attempt，容易分叉出另一套success／failure终结路径 | 保留`86b6cc3…`的single-owner hooks／History合同；stream attempt、parser／delivery错误与ASGI完成都必须在同一`RequestContext`上exactly-once finalize |
| `ResponsesStreamParser` item-level `source_order` 与 block-delivery排序坐标 | R1证明旧候选把item order误作block稠密序号 | Main `b91e58a…`及archive `e506bf87…`已用multi-part、zero-block、较晚item与sparse parts验证typed ordering；production stream gate不得由手工稠密order fixture旁路 |
| Block delivery terminal／open-source与异步writer | R1证明旧session可越过open source成功terminal，且single writer不等于异步串行 | Main `b91e58a…`的typed terminal与operation lock已通过main-side gate；stream happy path增加真实ASGI sink正控，完整Acceptance继续覆盖partial write与retry frontier |
| Reasoning carrier、non-stream response、usage与route已进入main | 局部主线全绿容易掩盖stream route未接、stream History投影与ASGI wire未验收 | Stream route组合gate重放项目主v1、upstream v1、multi-item、encrypted-only、usage parity、client echo与single-context identity；468 tests只作current回归，不作完整Acceptance |
| 历史 source refs与current main commits | Reviewed source identity与main squash identity不同，后续若从旧source重建会制造第二条实现链 | 最新archives保持immutable且只作provenance；stream route从`main@b91e58a…`演进。Systemd旧code-only链同样只作provenance，必须从新main重建 |
| `docs/agents/systemd-runtime/plan.md` 与 systemd 代码提交 | 旧integration把高频living Plan与可复用代码patch绑在同一提交；即使code-only已排除Plan，其base也已落后current main | 旧`862f4cfa… → 2ec0cb8…`只作patch／result oracle；new-main rebuilt identity`8cae6c2… → d3fabfa…`的candidate-side review／verify门已闭合，当前只按序执行逐片main-side gate并在main收敛后fresh checkpoint Plan，禁止direct replay与old Plan postimage |
| `fix/responses-history-facts` 的候选状态与main缺陷状态 | 最终candidate容易被误写成main major已关闭，或把candidate放行冒充main-side gate已通过 | `b1df8f9…`已获R4独立终审0 blocker／0 major／0 minor、独立验收R2 PASS与squash收口审计R2 0 blocker／0 major，可squash；main History major仍保持open，直到main-side gate与merged-state复核通过 |
| `feat/anthropic-responses-stream-route` 的多轮身份与证据范围 | R1、代码R2、tracked-WIP复核与current R3属于不同身份；又容易把R3限定PASS外推到完整Acceptance | R1只绑定`2087f8f…`，代码R2绑定`bc436af…`，tracked-WIP复核绑定旧diff；current `f3922a9…`已由R3代码review确认0 major并获限定verify PASS，可squash，但retry、quota／resident backpressure、真实socket partial-write与完整Acceptance继续未验证 |
| `docs/tmp/260807-resume-backup-port-smoke-r3.md` 的计划与执行边界 | Plan review 0 major容易被误写成smoke已执行，或把stream-route自身的代码放行误写成完整candidate Phase 0已通过 | R3 SHA-256 `2bf1dbd…`已获0 blocker／0 major，但保持`PLAN_ONLY／NOT_RUN`；current stream `f3922a9…`只满足自身可squash门，不满足施工阶段A后完整candidate的Phase 0门。Harness与safety tests尚未实现，后续仍须先施工，再对包含stream实现、harness与tests的完整candidate复评 |
| Systemd source 与 main squash | Source R4绑定 `49fb198…`，main commit为 `cf53334…`；reviewed source与集成提交身份层级不同 | 已以 `archive/260807-systemd-runtime@49fb198…` 保留 source并通过 main gate；仍不得把 main commit外推为安装态或 cutover证据 |
| `contrib/systemd/ghc-api-proxy.service` timeout 与应用shutdown | `TimeoutStopSec`、Uvicorn graceful cap与lifespan cleanup不是同一真相源，unit数值可在代码行为改变后静默漂移 | Graceful-timeout从真实调用链冻结单一公式并用低时长执行测试机械对账；user-install不得复制未冻结常量 |
| System unit与未来rootless user unit | 直接复制模板会让`User=`、paths、targets、slice与timeout各自漂移；install helper又容易越过dry-run边界改变manager状态 | User-install使用共享typed render inputs与明确的system／user渲染合同，默认dry-run；隔离测试证明无真实config或manager副作用，并与graceful-timeout做merged-state复核 |
| `localhost:4141` 的双运行时目标 | 当前 Bun 裸进程与未来 systemd socket 都可能成为 listener owner，直接启动会端口争用或误判新服务已接管 | Cutover 明确设置唯一 socket owner、旧 listener 释放、health 与 rollback gate；代码 review／unit smoke 不外推为运行态切换证据 |

Spec `FINALIZED@5e362822…`继续提供current行为oracle；Acceptance current `6457b896…`保持`FINALIZED_ACCEPTANCE_ORACLE`，本轮未改 Acceptance。四文档checkpoint与bridge三片均已进入main，但 current main merged-state review的reasoning capability与History facts两项major仍未由main关闭：capability clean candidate `8bff1c3…`已获精确绑定代码review `0 blocker／0 major`与独立验收`PASS`，可在本轮living checkpoint后squash；History最终candidate `b1df8f9…`已获R4独立终审`0 blocker／0 major／0 minor`、独立验收R2 `PASS`与squash收口审计R2 `0 blocker／0 major`，可squash。Stream clean candidate `f3922a9…`已获R3代码review `0 blocker／0 major`与独立验收限定范围`PASS`，明确可squash，但完整stream与产品仍`UNVERIFIED`。Systemd new-main identity`8cae6c2… → d3fabfa…`已获merged-state review `0 blocker／0 major`与两份独立验收`PASS`，其中一份为`0 blocker／0 major／3 minor`；systemd Plan current `3c639fcd…`也为`0 blocker／0 major`，但candidate仍未main、未安装或部署。Readiness current `c1e8494e…`为`0 blocker／0 major`；备用端口R3计划`2bf1dbd…`已获`0 blocker／0 major`但保持`PLAN_ONLY／NOT_RUN`，stream R3只放行`f3922a9…`自身进入squash，不满足施工阶段A后完整candidate的Phase 0门；harness与safety tests尚未实现，施工阶段A与完整candidate独立复评仍为后续，本轮未执行smoke。旧Bun继续持有双栈`4141`并位于`/init.scope`。整体保持`NO_CUTOVER`，本文保持`LIVING`、不收口；下一动作固定为先完成本文新hash定向复评并立即形成living checkpoint，再默认按capability→History→stream→systemd S3→S4逐片squash，仅在机械证明非重叠时调整片序。本轮新bytes必须按新hash后续重新定向复评，任何绑定修订前旧hash的并行current复评均不得沿用。