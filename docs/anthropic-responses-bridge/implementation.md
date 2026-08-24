# Anthropic Messages ↔ OpenAI Responses bridge 实施状态与动态收敛计划

## 文档状态

- **用途与状态**：本文是 Implementation living document，记录正式规格进入实现后的渐进切片、评审门、待修项、下一最小切片、并行开发线与本地分支收敛策略。开始开发不等于本文收口；一次提交也只是可追溯 checkpoint，不把本文转成只读历史快照。
- **事实快照**：2026-08-08。主仓为 `/home/xp/src/ghc-api-proxy-py`，current `main` HEAD 为 `c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`。本轮每次 shell 调用都在同一调用内验证物理 repo root、分支 `main`、`HEAD == refs/heads/main == c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`；未来 `main` 前进后，living document 必须先记录新锚点并重建 gate，不得把本快照冒充未来 HEAD。
- **权威边界**：[规格](spec.md)是唯一行为 oracle；任何 required behavior 与 policy-dependent expected 只能来自 Spec。Current Spec 为 `FINALIZED@4c9beed133b80e1c03d46db50b25bcbb43df505c29174a68fab566fc671e1f8f`。[独立验收规范](acceptance.md)只把 Spec 合同转成可执行 gate，不得自行补充 expected；current Acceptance 为 `FINALIZED_ACCEPTANCE_ORACLE@f99492ad5c573f5d53dc2186082c9ec2a2fd7dad7d7d06cb26051331b3b7c2b3`，并在首屏绑定 current Spec 与 Architecture 内容身份。该状态只批准使用验收 oracle，不构成候选产品或完整 bridge 的 `PASS`，产品继续为 `UNVERIFIED`。[目标架构](architecture.md)仅是非规范实现参考；`D-ARCH`／`D-MIGRATION` 未经用户接受前不产生 behavior 或 expected。[研究](research.md)保留来源、可移植机制与不可照搬项，不是行为或验收 oracle。
- **更新纪律**：本文必须随代码事实、独立评审、main 回放、并行线合并、新发现与计划调整持续更新；每次更新都绑定当时可复验的 commit、worktree、报告或 gate，不把计划中的动作写成已实现事实。状态变化先更新对应切片／开发线与下一步，再同步汇总；过时结论保留其历史绑定或明确降级，不冒充 current verdict。
- **评审语义**：本文某一内容身份取得 blocker 0、major 0，只表示在该轮范围内没有已知阻断项、可以继续实施或形成 checkpoint commit；不表示 Implementation 已定稿、实施已完成、后续不再修改，也不替代新代码、新组合态和新文档 bytes各自所需的复评。后续事实或发现改变本文时，living document 应继续修订，并对新增或改写内容执行相称的定向复评。
- **foundations、happy、usage 与 bridge 主树状态（2026-08-08 快照）**：foundations、happy、usage、semantic、route、delivery、capability、History、stream、retry、resident wiring、Copilot identity，以及真实tool／reasoning两个最小纵向切片均已线性进入 `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`，对应reviewed sources均已归档。此后 `main` 已继续前进，`c1de6bf…` 不再是 current HEAD：其中的 resident wiring 已于 2026-08-19 按用户裁决删除（`src/app/delivery/reservation.py` 随 `546852a` 移除），进程级改由等待式在途请求上限 `proactive_rate_limiter.max_inflight` 承接（`InFlightLimit`，`f5589ec`），`/health`、`/health/liveness`、`/health/readiness` 与 `/metrics` 豁免该上限（`7e9b62d`）。完整产品仍为 `UNVERIFIED`，任何局部测试、评审或 smoke 不外推为完整 Acceptance `PASS`。
- **最近真实主路径证据与 current delta 边界**：Tool reviewed source `archive/260808-real-copilot-tool-roundtrip@8524c00ee6e59dfd2ae7582a9de31a0356d67d3d`已作为`main@e8708fb77a200abe9b2827095fe9a1e921d82090`进入主树；隔离`4142`真实canary取得纯文本non-stream／stream 200、forced ordinary function tool 200与tool-result continuation 200。Reasoning reviewed source `archive/260808-real-copilot-reasoning-roundtrip@b50481800d16f776bb61f87045aa01200fcf6ef2`已作为`main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`进入主树；真实canary取得非空project-v1 payload thinking block并证明完整assistant content原样echo后的第二请求被真实Copilot接受。两片均经main-side全量647项tests、Ruff与Pyright通过；它们只形成ordinary non-stream tool roundtrip与单item reasoning carrier echo的scoped PASS，不覆盖完整REQ-04／REQ-05、完整Acceptance、quota／backpressure、kernel partial-write、manager／cgroup或cutover。
- **当前归档状态**：Foundations reviewed sources 由 `archive/260807-anthropic-responses-reasoning-cardinality@b876e626…`、`archive/260807-anthropic-responses-liveness@f27a8c04…` 与 `archive/260807-anthropic-responses-request@fdd2f75f…` 保留；既有 `archive/260806-anthropic-responses-reasoning@d90c90d7…` 不移动。Happy／usage reviewed sources 由 `archive/260807-reasoning-carrier-v2@8301ee9…`、`archive/260807-responses-anthropic-nonstream@7ddf173…`、`archive/260807-responses-stream-parser@73a6aa1…`、`archive/260807-anthropic-responses-route-policy@84a22c0…` 与 `archive/260807-nonstream-usage-details@aca3ced…` 精确保留。后继 reviewed sources 由 `archive/260807-responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`、`archive/260807-anthropic-responses-route-happy@dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、`archive/260807-anthropic-block-delivery@e506bf87318424e4075b6422772ee0c7e9b8694a`、`archive/260807-responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`、`archive/260807-responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`、`archive/260807-anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`、`archive/260807-stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b`、`archive/260807-responses-network-retry@584e63ba3724a7b6999d2163266d3daf8e731221`、`archive/260807-resident-byte-budget@8fb6a97e97fe7db9034b1b68636bc40beaf7cec6`、`archive/260807-resident-budget-wiring@aa5f1d3ef793c8d9b4098df0883d20468a48dc57`、`archive/260807-copilot-token-identity@8f164d897966fd80f9a5087083f420f2caf79ac9`、`archive/260807-copilot-response-identity@1bc5a8185a6a19101679e13c9a3a0bda3072bab4`与`archive/260807-copilot-item-identity@f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`精确保留。Systemd reviewed sources包括 runtime `archive/260807-systemd-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`、S3 `archive/260807-systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5` 与 S4 `archive/260807-systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`。Archive refs不因主树继续前进而移动。
- **当前 systemd 与部署文档状态**：Systemd runtime `cf53334…`、graceful-timeout S3 `c53849e2b5103c6426a67a8cbab687f2e45c1fa0` 与 rootless installer S4 `e9fb2771d6e040c761bb4074e3fcf2547caece28` 均已进入main；current主树已前进到`c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`，对应reviewed sources分别由`archive/260807-systemd-runtime@49fb198…`、`archive/260807-systemd-graceful-timeout@865a5b7…`与`archive/260807-systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`保留。S5本机隔离诊断已执行：helper、临时apply、动态unit verify与direct inherited-fd关键路径通过，但独立`systemd --user`在创建private control socket前以`rc=1`退出，故真实manager activation、fd inheritance、effective cgroup、restart与manager stop统一为`BLOCKED`，不是`PASS`。真实Copilot canary虽已取得readiness 200及non-stream／stream 200，但该进程不是由真实user manager／cgroup启动，不能关闭S5。真实manager／cgroup仍保留为独立外部环境验证，S7 rolling仍为后续独立切片。整体保持`NO_CUTOVER`。
- **完整产品边界与真实 canary 状态（2026-08-08 快照）**：Non-stream route、semantic parser、typed delivery、reasoning capability、History facts、Responses stream route、network retry、Copilot identity及tool／reasoning最小纵向切片均已进入`main@c1de6bf…`（同期的 resident wiring 已于 2026-08-19 删除，见上）。隔离`4142`真实Copilot canary已覆盖纯文本non-stream／stream、forced ordinary tool roundtrip及单item project-v1 reasoning carrier echo；旧Bun在各成功窗口内身份不变且收到零signal。完整产品仍为`UNVERIFIED`：完整tool／reasoning矩阵、buffer cap 与在途上限下的真实背压行为、kernel-level partial-write、真实manager／cgroup、完整Acceptance、P2与P3继续open。
- **备用端口 happy smoke 与运行态边界**：[备用端口 smoke 执行记录](../service-cutover/reports/260807-resume-backup-port-smoke-execution.md)精确绑定`main@ae84aa9d4330e56b83aefdad977e7d93190ff0d4`，在隔离`127.0.0.1:4142` app＋`127.0.0.1:4143` fake上给出`PASS_HAPPY_BACKUP_PORT_SMOKE`。后继[current-main备用端口关键主路径smoke R2](../service-cutover/reports/260807-final-backup-port-smoke-r2.md)精确绑定`main@e9fb2771d6e040c761bb4074e3fcf2547caece28`，给出`PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`；[独立快速复核](../service-cutover/reports/260807-review-final-backup-port-smoke-r2.md)确认该报告可按`0 blocker／0 major／1 minor`归纳。该缺口已由reviewed source`4fa7a877…`的净语义作为`main@d903d726…`修复并由`archive/260807-stream-request-facts`归档。[备用端口关键主路径smoke R3](../service-cutover/reports/260807-final-backup-port-smoke-r3.md)精确绑定`main@d903d726…`并取得`PASS_KEY_BACKUP_PORT_SMOKE_R3`；[stream facts最终定向复核](reports/260807-final-review-stream-facts-main.md)在限定合并接缝内为`0 blocker／0 major`，真实History API也确认stream final attempt的typed request conversion fact保留，R2定向缺口已关闭。R3继续提供fake与History scoped证据，但最新运行证据已由`main@fb4272b…`真实Copilot canary取代；两者均不得外推为真实manager／cgroup、quota／backpressure或kernel partial-write证据。完整产品继续`UNVERIFIED`，部署保持`NO_CUTOVER`。
- **stream request facts 主线收敛**：`fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b`用于收敛R2唯一stream History request-facts缺口；[Spec窄裁决](reports/260807-arbitrate-stream-request-facts.md)判定completed、post-commit partial failure与delivery-uncertain均保留最终selected attempt的request conversion observations，[独立定向终审R2](reports/260807-review-stream-request-facts-r2.md)给出`0 blocker／0 major／1 minor`。该净语义现已作为`d903d726baf3f15bf46ddf17384564fee154ed6a`进入main，main-side全量590项tests、Ruff与Pyright通过，reviewed source由`archive/260807-stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b`精确保留。R3真实History API已观察到final attempt的typed request conversion fact，定向缺口关闭；该scoped入口`PASS`不得外推为完整Acceptance或完整产品`PASS`。
- **当前 merged-state 结论**：Capability `bd86207…`、History `38bb06f…`、stream `ae84aa9…`、S3 `c53849e…`、S4 `e9fb277…`、stream request facts `d903d72…`、headers-before Responses network retry `fb5c027…`、exhaustion永久回归门 `080105b…`、resident-byte最小primitive `29c0ce3…`、production stream resident wiring `941299f…`、token identity `c188165…`、response identity `0e66cab…`与item identity `fb4272b…`均已依次进入main并归档reviewed source；其中两片 resident 切片的机制已于 2026-08-19 按用户裁决删除（`546852a`），archive ref 仍保留其历史身份。祖先`main@fb4272b…`的纯文本canary与后继tool／reasoning scoped canary共同限定当前运行结论；旧Bun在成功窗口内身份快照不变并收到零signal。buffer cap 与在途上限下的真实背压行为、真实sink kernel partial-write／delivery-uncertain、完整tool／reasoning矩阵与真实manager／cgroup仍未闭合；完整产品继续`UNVERIFIED`，部署继续`NO_CUTOVER`，Implementation继续`LIVING`且不收口。
- **已删除机制的统一说明（2026-08-19 裁决）**：resident-byte／quota／全局内存预算这一整套机制**已按用户裁决整体删除**（`546852a`），由等待式在途请求上限 `proactive_rate_limiter.max_inflight` 取代（`f5589ec`、`7e9b62d`）。本文此后仍会出现「resident wiring」「完整 quota 尚未完成」「quota／backpressure 仍未验证」一类表述，**它们都是各自日期下仍然为真的历史取证范围声明，不是待办**——那部分工作不再存在，不要去找、也不要去补。同理，文中各处 `main@c1de6bf…` 等锚点均为其所属快照当时的 HEAD，均已非 current。本条是这两类表述的唯一权威说明，各处不再逐行重复。
- **证据边界**：`docs/tmp` 报告只绑定各自写明的文档内容身份或代码 HEAD，不是长期状态真相源。本文只保留 verdict、仍有效的 gate 与裁决结果，不复制复现细节或长探针输出。后续新建报告使用实际创建日的 `YYMMDD-` 前缀，同一对象复评追加 `-rN` 且不覆盖旧轮次；既有无日期前缀或 `260806-` 报告保持原名。

### 评审 major 处置

[Implementation post-S3 定向复评](reports/260807-resume-review-implementation-post-s3.md)精确绑定 SHA-256 `0a99620dc352b1cdec788c0a67d1b476df67926ae598970994649a69617e043d` 与 `main@c53849e…`，给出`0 blocker／0 major／0 minor`并允许形成living checkpoint；该精确内容随后作为`3a55c091ef000d867b2f58f3afeacf60b6c1c64d`进入main。此后S4又作为`e9fb277…`进入main并归档，因此本轮新bytes仍须以新hash重新定向复评；R7及更早报告均只绑定各自旧内容身份，以下历史处置不冒充本轮current verdict：

| Major | 本次处置 | 复评门 |
|---|---|---|
| Implementation R3 M1：Spec／Acceptance 阶段状态陈旧 | **历史处置，已被 2026-08-07 carrier 重裁再次取代。** 当轮曾同步 Spec `FINALIZED` 与 Acceptance R7；current 状态以本表末行、顶部权威边界和“文档复评剩余项”为准 | 历史行不得作为 current 执行依据；后续每次 Spec bytes 变化都必须传播到 Acceptance 绑定与本文状态 |
| Implementation R3 M2：遗漏完整三片 integration branch | **历史处置，现已完成主树回放。** 当轮把 `integrate/260806-bridge-foundations@6a00f6f…`、三个线性 commits、clean worktree、代码 R2 0／0与 verification R2 PASS 写入状态真相源，并把旧 `8e9aef6…` 降为历史 liveness 载体 | Current foundations 已作为 `d274f58… → 798ba3e… → 1c13fda…` 进入 `main`并归档 reviewed sources；历史 integration verdict不得外推为完整产品 `PASS` |
| Implementation R4 M1：Acceptance R6 旧 Architecture 快照被无条件汇总为 current verdict | **历史处置。** Acceptance 当时绑定 Architecture `6de919…` 并重做七域 manifest，R7 对当时文件终审为 0／0；current Spec 后续已发生 carrier 重裁 | R7 不得外推为 current Acceptance 或产品 `PASS`；Spec／Architecture／Acceptance 内容变化时须重新绑定并复评 |
| Implementation R5 M1：本文未同步 Acceptance R7 已完成状态 | **历史处置。** R7 当时的 0／0已同步；current Spec 后续发生 carrier 双格式重裁，故该 verdict 不再覆盖 current Spec／Acceptance 内容对 | 保留为历史评审链，不得据此跳过 current Acceptance 重绑与复评 |
| Living-plan review M1：Spec carrier 重裁后状态陈旧 | **历史处置，current 状态已再次前进。** Carrier 定向评审曾为0／0／0，Spec恢复`FINALIZED@5e362822…`；Acceptance现已重绑并恢复`FINALIZED_ACCEPTANCE_ORACLE@6457b896…` | 本文新bytes仍须复评；current Acceptance依据是精确绑定`6457b896…`的空reasoning R2 0／0／0，不再沿用旧`224b020d…`终审 |
| Implementation current R2 M1：living 状态落后于 Plan／source／systemd／happy integration | **历史处置，已被 stable checkpoint 复评再次取代。** 当轮同步了 Plan R10、source reviews、systemd R3 与 happy `d78b3cd…` 基础状态 | 历史行不得作为 current 执行依据；current 身份与 gate 以本表末行、顶部状态和“下一步”为准 |
| Current-main merged-state M1：空reasoning的stream／non-stream归一化漂移 | **按仲裁撤销，Acceptance 最终状态已恢复。** [空 reasoning 语义仲裁](reports/260807-arbitrate-empty-reasoning.md)确认 empty item 必须形成一个 `thinking=""` bare carrier block；`1cde3d58…` 的 stream／non-stream 行为在该轴正确，旧 verify 的零-block expected 与 `FAIL` 被 supersede | Acceptance current `6457b896…` 已恢复`FINALIZED_ACCEPTANCE_ORACLE`并获R2 0／0／0；Semantic R2／verify R2已证明该合同保持；产品仍为`UNVERIFIED` |
| Current-main merged-state M2：parser静默接受冲突authoritative lifecycle值 | **已关闭并进入main。** `1cde3d58…` 与 `f5bca39…` 统一 typed reject并补足 done-only 回归；完整range已作为`bfc461f57a507059c5c7b098e0616e7882f7333d`进入主树 | Semantic main-side gate已完成，`archive/260807-responses-semantic-parity@f5bca39…`已建立；stream route切片必须消费该current parser，不另建normalizer |
| Semantic parity 新 M3：未知 reasoning summary part 两路一收一拒 | **已关闭并进入main。** `f5bca39…` 在 stream 端统一 unknown part typed reject，并补同一 malformed fixture 与 function item-done-only 回归；空语义仲裁轴保持不变 | 精确绑定 source 的R2为0 blocker／0 major／0 minor、verify R2为`PASS`；完整range已作为`bfc461f…`进入main并归档，不得外推为完整bridge `PASS` |
| Route header 与 hooks lifecycle | **Header 与 hooks 两轴均已关闭并进入main。** `44808b7d…` 与 `dd376d6…` 的完整range已作为`86b6cc3e72c0312ea8e93940513ee55e290da245`进入主树并完成route main-side gate | Archive精确指向`dd376d6…`；non-stream与dual-capability Messages回归必须在stream route切片继续保留 |
| Graceful timeout＋user installer 组合态 | **旧 M2 证据保留，执行基线已再次前进。** `integrate/260807-systemd-code-only@2ec0cb8…` 的 `862f4cfa… → 2ec0cb8…` 两片保持review／verify与非Plan语义provenance，但其base是旧`80bc8f2…`；更旧`0a93e7f…`继续只作历史组合语义和S3-parent adaptation证据 | New-main rebuilt `8cae6c2… → d3fabfa…`当时已获review 0 major＋两份verify PASS；其逐片main-side gate现已由S3 `c53849e…`与S4 `e9fb277…`完成并归档。旧链只保留provenance，禁止direct replay、cherry-pick或作为S5载荷 |
| Post-S3 checkpoint后主线收敛 | **已完成并继续前进。** Capability、History、stream、S3、S4与stream request facts分别作为`bd86207…`、`38bb06f…`、`ae84aa9…`、`c53849e…`、`e9fb277…`与`d903d72…`进入main；六片reviewed source均已归档，post-S3 Implementation bytes以`3a55c09…`形成历史living checkpoint | Current不再重复上述squash或S4 gate；`d903d72…` main-side全量590项tests、Ruff与Pyright通过，backup smoke R3取得`PASS_KEY_BACKUP_PORT_SMOKE_R3`并关闭stream History facts定向缺口；S5真实manager／cgroup诊断`BLOCKED`并转到VM／container。完整产品仍`UNVERIFIED`，部署仍`NO_CUTOVER` |
| Backup happy smoke执行 | **R3限定范围通过。** `main@ae84aa9…`取得`PASS_HAPPY_BACKUP_PORT_SMOKE`；后继`main@e9fb277…`取得`PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`并获独立复核`0 blocker／0 major／1 minor`。该facts缺口已由`main@d903d72…`修复并归档；同一祖先上的R3取得`PASS_KEY_BACKUP_PORT_SMOKE_R3`，真实History API确认缺口关闭 | Semantic reorder、完整usage／terminal／History矩阵、retry、quota／backpressure、真实partial-write、真实credential、真实systemd manager、in-flight shutdown、持久化harness／变异控制与完整Acceptance继续未验证；完整产品`UNVERIFIED`，部署`NO_CUTOVER` |
| Headers-before Responses network retry | **窄实现与永久回归门均已进入main。** Reviewed source `584e63ba3724a7b6999d2163266d3daf8e731221`经集成期fail-closed分类收敛后，作为`fb5c027b38cc72910dd4495979a26a57fbbaa99b`进入主树；archive精确指向`archive/260807-responses-network-retry@584e63b…`。`080105b54614e1320a5c193d7206dcaa584c9b41`补回两次allowlisted连接失败后的调用数、attempt facts、零success facts、History与hooks永久断言，关闭current review唯一major | 父提交main-side全量599项tests、Ruff与Pyright通过；`080105b…`上5个定向tests经collect与执行交叉核对均通过。其范围仍不能外推到stream读取、post-commit、quota／backpressure、真实partial-write、真实upstream或完整Acceptance |
| Resident-byte最小primitive main收敛 | **已进入main并归档。** Final reviewed source `8fb6a97e97fe7db9034b1b68636bc40beaf7cec6`的净语义已作为`29c0ce3230181a113363eb398dfa24d8e41a9012`进入主树，archive精确指向`archive/260807-resident-byte-budget@8fb6a97…`；该checkpoint现场全量611项tests、Ruff与Pyright通过 | Production stream wiring后继已作为`941299f…`进入main。该 resident-byte 记账已于 2026-08-19 按用户裁决整体删除（`src/app/delivery/reservation.py` 随 `546852a` 移除），由 `proactive_rate_limiter.max_inflight` 的等待式在途上限取代（`src/app/server/admission.py`，`f5589ec`）；quota 其他 owner、parser drafts、admission 与 metrics／History 映射不再是待办。有限 queue 与真实partial-write仍未验证 |
| Production stream resident wiring main收敛 | **已进入main并归档。** Final reviewed source `aa5f1d3ef793c8d9b4098df0883d20468a48dc57`的净语义已作为`941299fe5a5275c4a5fc327d172a1deeccfb3085`进入主树，archive精确指向`archive/260807-resident-budget-wiring@aa5f1d3…`；该checkpoint现场全量613项tests、Ruff与Pyright通过。配置默认`0／0`保持既有行为，显式同时启用正值时有界 | Token identity后继已进入main。该 wiring 与其两个配置键已于 2026-08-19 按用户裁决随全局内存预算一并删除（`546852a`），进程级改由 `proactive_rate_limiter.max_inflight` 的等待式在途上限承接（`f5589ec`）；quota 其他 owner、parser drafts、admission 与 metrics／History 映射不再是待办。有限 queue 仍未闭合 |
| Copilot token exchange identity main收敛 | **已进入main并归档。** Final reviewed source `8f164d897966fd80f9a5087083f420f2caf79ac9`的净语义已作为`c188165dd413b7683a65472781ca3bef9c1a29b3`进入主树，archive精确指向`archive/260807-copilot-token-identity@8f164d8…`；current main现场全量614项tests、Ruff与Pyright通过 | 真实启动已由403修复为readiness 200并加载32个模型、10个Responses-capable模型；该证据不覆盖完整auth provider、manager／cgroup或cutover |
| Copilot response／item identity canary缺口 | **已关闭并进入main／archive。** Response identity作为`0e66cab…`进入main；item identity作为`fb4272b…`进入main，两条archive refs精确保留reviewed sources | 后继tool／reasoning scoped canary已在各自reviewed source上通过并作为`e8708fb…`／`c1de6bf…`进入main；完整canary verdict仍不得由局部路径拼接外推 |

此前 `docs/tmp` 归纳评审的 5 项 major 处置也随最新 merged-state 结论重新对账：

| Major | 当前处置 | 事实边界 |
|---|---|---|
| M1 Reasoning cardinality 状态缺失 | **已关闭并进入 `main`** | Reviewed source `b876e626…` 已归档为 `archive/260807-anthropic-responses-reasoning-cardinality`；对应 main commit 为 `d274f584…`，main-side gate 已通过 |
| M2 Liveness 状态停在待 R3 | **已关闭并进入 `main`** | Reviewed source `f27a8c04…` 已归档为 `archive/260807-anthropic-responses-liveness`；对应 main commit 为 `798ba3e765…`，main-side gate 已通过 |
| M3 Request 状态停在父提交 | **已关闭并进入 `main`** | Reviewed source `fdd2f75f…` 已归档为 `archive/260807-anthropic-responses-request`；对应 main commit 为 `1c13fda4…`，main-side gate 已通过 |
| M4 文档复评汇总陈旧 | **已关闭。空reasoning合同与最终状态均已同步** | Spec `FINALIZED@5e362822…` 不变；Acceptance current `6457b896…` 已恢复`FINALIZED_ACCEPTANCE_ORACLE`并由R2确认为0 blocker／0 major／0 minor。产品仍为`UNVERIFIED`，本文不把文档0／0或局部smoke外推为产品状态 |
| M5 临时报告跨日期命名合同未形成仓库级载体 | **已由项目规则承载；旧控制面计划已终止并归档** | [项目开发规则](../../../.claude/rules/00-development-workflow.md)要求新报告使用实际 `YYMMDD-` 前缀、不得覆盖旧轮次，并及时把结论归纳到 live docs。旧 generation／certificate／ledger 方案不再执行；已有历史报告不批量改名。 |

## 总体进度

| 顺序 | 切片 | 主树／历史身份 | 当前 gate | 下一动作 |
|---|---|---|---|---|
| 1 | Reasoning carrier baseline | `main` `ed77c9d191df81c451c25161420515cca52ce6a4` | **已 squash；原 reviewed HEAD 已归档** | 保持既有 archive ref，不移动或 force-update |
| 2 | Reasoning cardinality correction | main `d274f584219f8ae32f59d15d08ac007c45058c8d`；archive `b876e626…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | 保持 archive ref immutable；在 happy 与 route wiring 组合 gate 中继续守住一 item 一 block与 encrypted-only no-loss |
| 3 | Session liveness | main `798ba3e7653b513c3c9c732019e793f828ae0890`；archive `f27a8c04…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | 在后续 stream owner接线中继续守住 cancellation cleanup、primary／secondary failure与资源归零 |
| 4 | Request converter | main `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7`；archive `fdd2f75f…` | **已进入 `main`；main-side gate 通过；reviewed source 已归档** | Route wiring只在每 attempt `PRE_SEND` 后消费 converter，不建立第二 lifecycle owner |
| 5 | Reasoning carrier v2 checkpoint | main `a0d807fe807629b739ab16c5463f99bc27bc7aac`；archive `8301ee9…` | **已进入 `main`；reviewed source 已归档** | 在完整 route与 echo gate中继续守住项目主 v1 producer、upstream v1 consumer、direct Messages strip与一 item一 block |
| 6 | Non-stream response checkpoint | main `cdc080e1795ee1ac63d589ee00a10acd581b460e`；archive `7ddf173…` | **已进入 `main`并归档；原空reasoning parity major已按仲裁撤销** | 保持one-empty-item／one-bare-block合同；完整error／terminal／History仍按Acceptance补齐 |
| 7 | Stream parser checkpoint | main `a815948ef1b8e739e4bd49e31894be4dffc06950`；semantic修复main `bfc461f57a507059c5c7b098e0616e7882f7333d`；archives `73a6aa1…`、`f5bca39…` | **parser与semantic parity均已进入main、完成main-side gate并归档** | Stream route只消费current parser facts，不建立第二semantic normalizer或直接从parser写ASGI body |
| 8 | systemd／cgroup runtime checkpoint | runtime main `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`、archive `49fb198…`；S3 main `c53849e2b5103c6426a67a8cbab687f2e45c1fa0`、archive `865a5b7…`；S4 main `e9fb2771d6e040c761bb4074e3fcf2547caece28`、archive `e16c2a7…` | **runtime、S3与S4均已进入main并归档；S5真实manager／effective cgroup诊断`BLOCKED`；未部署** | 在可销毁容器或虚拟机继续S5独立manager／delegated cgroup v2诊断；S7后续。部署与cutover仍由独立运行态门和显式授权约束 |
| 9 | Typed route policy checkpoint | main `d913a033252693022f0871f1e92c1b996d05eb71`；archive `84a22c0…` | **已进入 `main`；reviewed source 已归档** | Route-happy只消费 typed decision，handler／transport不得重新推导 precedence或 fallback |
| 10 | Non-stream usage details | main `80bc8f252b46c511f428af1d97159a5980ee9dc9`；archive `aca3ced…` | **已进入 `main`；reviewed source 已归档；current main组合 gate通过** | 在 stream／non-stream parity与History投影中继续验证 cache／reasoning details，不重复实现 usage算式 |
| 11 | Semantic parity 修复 | main `bfc461f57a507059c5c7b098e0616e7882f7333d`；archive `f5bca39ac582911b61d278fd678ec9298ad0c08e` | **已进入main；semantic main-side gate通过；reviewed source已归档** | 在stream production链继续守authoritative、unknown summary、empty reasoning与done-only回归 |
| 12 | Route happy 接线 | main `86b6cc3e72c0312ea8e93940513ee55e290da245`；archive `dd376d6f1e9dc2997bc2f95d03a352fed4df1412` | **non-stream Responses已生产接线；route／hooks／header main-side gate通过；reviewed source已归档** | Stream production后继已作为`ae84aa9…`进入main；继续保持non-stream与dual-capability Messages回归 |
| 13 | Block delivery | main `b91e58a29324b11840002efc53ed6f869b800c39`；archive `e506bf87318424e4075b6422772ee0c7e9b8694a` | **typed parser→delivery骨架已进入main；block main-side gate通过；reviewed source已归档** | Production stream已组合消费该delivery；真实retry、buffer cap 下的背压与partial write继续按未验证清单补齐 |
| 14 | Bridge successor integration | 历史 `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f`；主树结果 `bfc461f… → 86b6cc3… → b91e58a…` | **三片已分别进入main并各自完成main-side gate／archive；后继capability、History与stream也已进入main** | 不再回放或续写successor；只保留review／verification provenance |
| 15 | Non-stream reasoning capability major | main `bd86207b4fdb55b7c10c795118f61ba693192003`；archive `8bff1c3fbd721060a87f18b0ef9d90d7d998a997` | **已进入main；main-side gate通过；reviewed source已归档** | 保持archive immutable；在每attempt重转换与stream／non-stream组合回归中继续守住resolved-model capability facts |
| 16 | Non-stream History facts major | main `38bb06ff0eefef69fd4fdab830e67ff549563a20`；archive `b1df8f910c590033e83d5cafcd5e514f12bab937` | **已进入main；main-side gate与组合复核通过；reviewed source已归档** | 保持archive immutable；完整Acceptance继续验证committed／partial／uncertain与exactly-once事实投影 |
| 17 | Stream route | main `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`；archive `f3922a9ba9f90e4eea598dac1d899ebbe18985e8` | **已进入main；main stream定向review为0 blocker／0 major；reviewed source已归档；完整stream仍`UNVERIFIED`** | 按backup smoke已列真实缺口补semantic reorder、usage／terminal／History矩阵、retry、buffer cap 下的背压、真实partial-write与完整Acceptance |
| 18 | Graceful timeout S3 | main `c53849e2b5103c6426a67a8cbab687f2e45c1fa0`；archive `865a5b71210e2436b36786b5de67146939d1e0f5` | **已进入main；main-side定向与全仓gate通过；reviewed source已归档；未部署** | 不重复S3回放；由已进入main的S4继续承接S5运行态验证 |
| 19 | Rootless user install S4 | main `e9fb2771d6e040c761bb4074e3fcf2547caece28`；reviewed source／archive `e16c2a700f23f66535e7347ab7357518eb8e56bd`；历史rebuilt candidate `d3fabfadfba57af6c2d63e543e3198444777df54` | **已进入main；main-side定向与全仓gate通过；reviewed source已归档；未安装、未部署** | S5首轮诊断已`BLOCKED`；在受控容器或虚拟机继续真实user-manager／effective cgroup验证，不把仓库绿灯外推为运行态或cutover证据 |
| 20 | Graceful＋installer旧 code-only 集成 | 历史 `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`；`862f4cfa… → 2ec0cb8…` | 旧组合明确排除Plan且review／verify通过，但基线已被后继主树推进 | 只作为冻结patch／result-blob oracle；S3／S4 current身份已分别收敛为`c53849e…`与`e9fb277…`，禁止回放旧链 |
| 21 | Stream request facts major | main `d903d726baf3f15bf46ddf17384564fee154ed6a`；reviewed source／archive `4fa7a87728376f14bd84b4b5853f8212d5bc786b`；source base `e9fb2771d6e040c761bb4074e3fcf2547caece28` | **已进入main；main-side全量590项tests、Ruff与Pyright通过；`archive/260807-stream-request-facts`精确保留reviewed source。Backup smoke R3取得`PASS_KEY_BACKUP_PORT_SMOKE_R3`，真实History API确认定向缺口关闭** | 以实测缺口为准补retry、buffer cap 下的背压与真实partial-write；真实credential、真实systemd manager与cutover仍未验证，不外推为完整产品或完整Acceptance `PASS` |
| 22 | Responses headers-before network retry | main `fb5c027b38cc72910dd4495979a26a57fbbaa99b`；exhaustion test main `080105b54614e1320a5c193d7206dcaa584c9b41`；reviewed source／archive `584e63ba3724a7b6999d2163266d3daf8e731221` | **已进入main；明确连接失败窄分类、唯一retry owner、一次预算、attempt facts隔离与非retry近邻反例已实现；`080105b…`补回exhaustion永久回归门，5个定向tests通过，current review唯一major关闭** | Resident primitive也已进入main；真实partial-write与完整retry其余范围继续独立取证，不能把本切片写成完整retry `PASS` |
| 23 | Resident-byte最小primitive | main `29c0ce3230181a113363eb398dfa24d8e41a9012`；reviewed source／archive `8fb6a97e97fe7db9034b1b68636bc40beaf7cec6`；base `080105b54614e1320a5c193d7206dcaa584c9b41` | **已进入main并归档；primitive覆盖opt-in request／global resident reservation与delivery lease lifecycle** | 该机制已于 2026-08-19 按用户裁决整体删除（`546852a`），由 `proactive_rate_limiter.max_inflight` 的等待式在途上限取代（`f5589ec`）；quota／backpressure 不再是待办，真实partial-write与完整Acceptance继续独立取证 |
| 24 | Production Responses stream resident wiring | main `941299fe5a5275c4a5fc327d172a1deeccfb3085`；reviewed source／archive `aa5f1d3ef793c8d9b4098df0883d20468a48dc57`；base `29c0ce3230181a113363eb398dfa24d8e41a9012` | **已进入main并归档；该checkpoint现场全量613项tests、Ruff与Pyright通过。配置默认`0／0`保持既有行为，显式同时启用正值时有界** | 该 wiring 与两个配置键已于 2026-08-19 随全局内存预算一并删除（`546852a`），进程级改由 `proactive_rate_limiter.max_inflight` 承接（`f5589ec`）；quota 其他 owner、parser drafts、admission、metrics／History 映射不再是待办 |
| 25 | Copilot token exchange identity headers | main `c188165dd413b7683a65472781ca3bef9c1a29b3`；reviewed source／archive `8f164d897966fd80f9a5087083f420f2caf79ac9`；base `6e0112f90f39245f77618a7b4887dfe6b526c60a` | **已进入main并归档；真实启动已由token exchange 403修复为readiness 200，模型目录为32个模型／10个Responses-capable模型** | 保持archive immutable；response／item identity后继也已进入main并归档，不重复token identity施工 |
| 26 | Copilot stream response／item identity | response main `0e66cab…`、archive `1bc5a81…`；item main `fb4272b…`、archive `f171fa0…` | **两项修复均已进入main并归档；真实纯文本non-stream／stream 200绑定祖先`fb4272b…`** | Tool／reasoning最小纵向scoped PASS已由后继切片补齐；quota／backpressure、kernel partial-write与完整Acceptance继续未验证 |

Foundations、happy、usage、semantic、route、block、capability、History、stream、systemd S3／S4、stream request facts、retry、identity fixes及tool／reasoning最小纵向切片均已进入 `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`（同期的 resident wiring 已于 2026-08-19 删除，改由 `proactive_rate_limiter.max_inflight` 承接）。真实纯文本、forced ordinary tool roundtrip与单item reasoning carrier echo均取得scoped PASS；完整tool／reasoning矩阵、buffer cap 与在途上限下的真实背压行为、kernel partial-write与真实manager／cgroup仍未闭合，完整产品保持`UNVERIFIED`、部署保持`NO_CUTOVER`。

### 当前活动与历史开发线

| 开发线 | Worktree／branch | 建树基线 | 当前事实 | 更新与进入条件 |
|---|---|---|---|---|
| Semantic parity（已收敛） | source `fix/responses-semantic-parity@f5bca39…` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | main `bfc461f57a507059c5c7b098e0616e7882f7333d`；main-side gate通过；archive `archive/260807-responses-semantic-parity@f5bca39…` | 保持archive immutable；stream route从current main消费语义，不重复建线 |
| Route happy（已收敛） | source `feat/anthropic-responses-route-happy@dd376d6…` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | main `86b6cc3e72c0312ea8e93940513ee55e290da245`；main-side gate通过；archive `archive/260807-anthropic-responses-route-happy@dd376d6…` | 保持non-stream、stream与dual-capability Messages回归；下一核心入口为kernel partial-write |
| Block delivery（已收敛） | source `feat/anthropic-block-delivery@e506bf8…` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | main `b91e58a29324b11840002efc53ed6f869b800c39`；main-side gate通过；archive `archive/260807-anthropic-block-delivery@e506bf8…` | 保持archive immutable；后继只补 buffer cap 下的背压与kernel partial-write边界 |
| Reasoning capability修复（已收敛） | source `fix/responses-reasoning-capability@8bff1c3…` | `b91e58a29324b11840002efc53ed6f869b800c39` | main `bd86207b4fdb55b7c10c795118f61ba693192003`；main-side gate通过；archive `archive/260807-responses-reasoning-capability@8bff1c3…` | 保持archive immutable；不重复回放source |
| History facts修复（已收敛） | source `fix/responses-history-facts@b1df8f9…` | `b91e58a29324b11840002efc53ed6f869b800c39` | main `38bb06ff0eefef69fd4fdab830e67ff549563a20`；main-side gate与组合复核通过；archive `archive/260807-responses-history-facts@b1df8f9…` | 保持archive immutable；不回退到旧History candidates |
| Stream route happy path（已收敛） | source `feat/anthropic-responses-stream-route@f3922a9…` | `b91e58a29324b11840002efc53ed6f869b800c39` | main `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`；main stream定向review 0 major；archive `archive/260807-anthropic-responses-stream-route@f3922a9…` | 保持archive immutable；按实际未验证矩阵继续建立后继边界切片，不重复回放happy source |
| Bridge successor integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-successor`；`integrate/260807-bridge-successor` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 历史HEAD `c43db35…`已内容等价收敛为main `bfc461f… → 86b6cc3… → b91e58a…` | 不回放、不续写；只保留review／verification provenance |
| Bridge next integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-next`；`integrate/260807-bridge-next` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 旧HEAD `a23081c5d5f48143bf3015182d8f00e1f6297755`为0 blocker／1 major且verify `FAIL`；只保留失败provenance | 不回放、不续写、不amend，也不把其verdict外推到successor |
| Graceful timeout（已收敛） | source `feat/systemd-graceful-timeout@865a5b7…` | 历史 new-main candidate `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` | main `c53849e2b5103c6426a67a8cbab687f2e45c1fa0`；main-side gate通过；archive `archive/260807-systemd-graceful-timeout@865a5b7…` | 保持archive immutable；不重复S3回放 |
| Rootless user install（已收敛） | reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd`；历史 rebuilt candidate `d3fabfadfba57af6c2d63e543e3198444777df54` | 历史 candidate parent `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` | main `e9fb2771d6e040c761bb4074e3fcf2547caece28`；main-side gate通过；archive `archive/260807-systemd-user-install@e16c2a7…` | 保持archive immutable；不重复S4回放。S5本机首轮诊断已`BLOCKED`，下一步在受控VM／container续诊 |
| S5隔离user-manager／effective cgroup验证 | [执行记录](../systemd-runtime/reports/260807-systemd-user-manager-smoke.md)绑定历史 `main@e9fb277…` | current `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62` | **本机`BLOCKED`；独立manager未创建private control socket，真实activation／effective cgroup未执行；未安装、未部署、未cutover。应用路径scoped PASS不改变该结论** | 在可销毁VM／container继续诊断，要求独立login session／user manager与delegated cgroup v2；不得退回宿主user manager |
| Stream request facts major（已收敛） | source `fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b`；archive `archive/260807-stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b` | main `d903d726baf3f15bf46ddf17384564fee154ed6a` | **已进入main；main-side全量590项tests、Ruff与Pyright通过；reviewed source已归档。Backup smoke R3取得`PASS_KEY_BACKUP_PORT_SMOKE_R3`，stream History facts定向缺口已关闭** | 不重复已main的request-facts source；按未验证边界继续补证，不把scoped入口PASS外推为完整产品`PASS` |
| Responses headers-before network retry（已收敛） | source／archive `archive/260807-responses-network-retry@584e63ba3724a7b6999d2163266d3daf8e731221` | source base `910e4bcbe22f9477aa8d36e828f2d6a325498cd4` | **收敛语义已作为`main@fb5c027…`进入主树；`main@080105b…`补回exhaustion永久回归测试，5个定向tests通过，current review唯一major关闭** | 不重复该补测；buffer cap 下的背压矩阵仍保持`UNVERIFIED` |
| Resident-byte最小primitive（已收敛，机制其后被删除） | source／archive `archive/260807-resident-byte-budget@8fb6a97e97fe7db9034b1b68636bc40beaf7cec6` | main `29c0ce3230181a113363eb398dfa24d8e41a9012` | **已进入main并归档；该checkpoint现场全量611项tests、Ruff与Pyright通过。Primitive只覆盖opt-in request／global resident reservation与delivery lease lifecycle** | 该 primitive 已于 2026-08-19 按用户裁决整体删除（`546852a`），由 `proactive_rate_limiter.max_inflight` 的等待式在途上限取代（`f5589ec`）；quota 其他 owner、parser drafts 与 metrics 不再是待办，archive 保持 immutable |
| Production Responses stream resident wiring（已收敛，机制其后被删除） | source／archive `archive/260807-resident-budget-wiring@aa5f1d3ef793c8d9b4098df0883d20468a48dc57` | main checkpoint `941299fe5a5275c4a5fc327d172a1deeccfb3085` | **已进入main并归档；该checkpoint现场全量613项tests、Ruff与Pyright通过。默认配置`0／0`保持既有行为，显式同时启用正值时有界** | 该 wiring 与两个配置键已于 2026-08-19 随全局内存预算一并删除（`546852a`），进程级改由 `proactive_rate_limiter.max_inflight` 承接（`f5589ec`）；quota 其他 owner、parser drafts 与 metrics 不再是待办，archive 保持 immutable |
| Copilot token exchange identity（已收敛） | source／archive `archive/260807-copilot-token-identity@8f164d897966fd80f9a5087083f420f2caf79ac9` | main `c188165dd413b7683a65472781ca3bef9c1a29b3` | **已进入main并归档；真实启动已从403修复为readiness 200，模型目录观测为32／10** | 保持archive immutable；response／item identity后继已收敛，不重复token identity施工 |
| Copilot stream response identity（已收敛） | source／archive `archive/260807-copilot-response-identity@1bc5a8185a6a19101679e13c9a3a0bda3072bab4` | main `0e66cab5ffd636e40a0f378d6017326603a3196a` | **已进入main并归档；Copilot-only response ID drift兼容保持generic strict合同** | 保持archive immutable；后继item identity也已收敛，不重复response identity施工 |
| Copilot stream item identity（已收敛） | source／archive `archive/260807-copilot-item-identity@f171fa05bc0a2afcdd1dab12d3010cf09ce978ab` | main `fb4272b5752bd8439c1ee5a098960f31d4ea70f1` | **已进入main并归档；该祖先上的真实纯文本stream canary为HTTP 200** | Tool／reasoning最小纵向scoped PASS已由后继切片补齐；不重复identity施工 |
| Systemd code-only integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code`；`integrate/260807-systemd-code-only` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | HEAD `2ec0cb8…`的review／verify保留，但不再是current可直接回放载荷 | 只作old-base oracle；S3／S4已在main收敛，禁止direct replay／cherry-pick／old Plan postimage |
| Systemd next integration（历史） | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-next`；`integrate/260807-systemd-next` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 旧 HEAD `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 与 `91f95f7… → 0a93e7f…` 保留 merged review／verify／adaptation provenance；其 Plan patch 已被 current living bytes 超越 | 不回放、不续写、不cherry-pick，不以old Plan postimage解冲突；S5只从current `main@c1de6bf…`执行 |

Capability、History、stream、S3／S4、stream request facts、network retry、Copilot identity及tool／reasoning最小纵向切片均已进入main并归档reviewed source；同期的 resident wiring 已于 2026-08-19 删除，改由 `proactive_rate_limiter.max_inflight` 承接。真实纯文本、forced ordinary tool roundtrip与单item reasoning carrier echo scoped PASS已取得；完整tool／reasoning矩阵、buffer cap 与在途上限下的真实背压行为、kernel partial-write与真实manager／cgroup仍未闭合。任何代码收敛或scoped canary都不授权停止现服、安装生产unit或抢占`4141`。

### 增量开发风格

当前开发节奏明确采用：**先建立结构骨架，完成 happy path 与 smoke，形成单一可评审提交；独立 review 通过后尽快 squash／归档；随后按 Spec／Acceptance 继续补齐边界、失败路径、正反控制与组合态接缝。** Tool／reasoning最小纵向切片已进入main并归档；下一核心序列转向kernel partial-write，同时在外部环境继续manager／cgroup。产品保持`UNVERIFIED`，部署保持`NO_CUTOVER`。

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

[Reasoning R2 复评](reports/260806-review-code-reasoning-r2.md)绑定原候选 HEAD，随后其净改动以 `ed77c9d191df81c451c25161420515cca52ce6a4` squash 到 `main`。后续[reasoning aggregation 裁决](reports/260806-arbitrate-reasoning-aggregation.md)区分了必须保留的 upstream-compatible carrier wire／逐 block reverse primitive与必须修正的 forward 聚合语义；旧 R2 的代码事实保留，但“聚合行为即目标 oracle”的终局判断已被推翻。

Cardinality 修复的 reviewed source为 `b876e626dda821b267535b0bcffc9d81ced12763`。[独立代码评审](reports/260806-review-code-reasoning-cardinality.md)给出 blocker 0、major 0：每个 reasoning item产生自己的有序 thinking block，保留 non-empty encrypted-only payload，并保持 carrier与逐 block reverse。该语义已作为 `d274f584219f8ae32f59d15d08ac007c45058c8d` 进入 `main`，reviewed source由 `archive/260807-anthropic-responses-reasoning-cardinality@b876e626…` 精确保留；既有 reasoning archive不移动。

## 切片 2：Session liveness

### Git 快照

| 字段 | 值 |
|---|---|
| Worktree | `/home/xp/src/ghc-api-proxy-py-liveness` |
| Branch | `feat/session-liveness` |
| Anchor | `47d9ef101c4b81ac70d805b1da157b34d021d33d` |
| HEAD | `f27a8c04cd3470bd50d7194a30371ca5404f727e` |
| Status | clean |
| Review state | [R3](reports/260806-review-code-liveness-r3.md) blocker 0、major 0；reviewed source已归档，语义已进入main |
| 变更路径 | `src/app/streaming/keepalive.py`；`tests/unit/test_streaming_resilience.py` |

当前 reviewed HEAD 在原两提交后追加 `f27a8c04cd3470bd50d7194a30371ca5404f727e`（preserve liveness cleanup failures）。该分支基于 reasoning squash 之前的旧 anchor，不能把原三提交链直接视为组合状态。

### 评审结论与 integration 状态

[Liveness R2 复评](reports/260806-review-code-liveness-r2.md)在旧 HEAD 上给出的两项 major，已经由 R3 在 `f27a8c0…` 上逐条关闭：

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
| Review state | [R3](reports/260806-review-code-request-r3.md) blocker 0、major 0；reviewed source已归档，语义已进入main；R2 行为复验 PASS 绑定父提交 `028f1f2…` |
| 相对 current main 的变更路径 | `src/app/anthropic/thinking/responses_reasoning.py`；`src/app/protocols/anthropic_responses.py`；`tests/unit/test_anthropic_responses_request.py` |

request 切片基于 reasoning squash：`cb286059b656d960225c2afff84f204b9123810d` 为 converter 语义提交，`028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 为首轮四项 major 的 hardening，`fdd2f75fcec11e592b04f2686c4664262052a964` 关闭 R2 新发现的 unknown／explicit-unbounded reasoning limits 混淆。旧候选 `f8a11ad3…` 与父提交 `028f1f2…` 的报告都只绑定各自 HEAD，不能替代 R3 对最新 HEAD 的结论。

### 评审结论与待修项

[Request converter 代码评审](reports/260806-review-code-request-converter.md)在旧 HEAD 上给出 blocker 0、major 4：

1. **Thinking capability conversion 缺失。** 旧 HEAD 把顶层 `thinking` 一律作为 unsupported field 拒绝；正式 [Spec](spec.md) 要求 enabled／adaptive 经模型 capability 与 budget gate 映射为 Responses `reasoning`，disabled／absent 省略，unsupported capability 产生稳定 capability error。
2. **缺少 request-scoped 双向 tool-name mapper。** 旧 HEAD 没有让声明、assistant 历史 `tool_use`、forced named choice 与未来 response restore 共享同一原子映射，非法 Responses tool name 会原样穿过。
3. **Malformed carrier codec 与当时固定 Node 合同不兼容。** 旧 HEAD 对若干 non-canonical／Unicode payload 产生错误差分，其中非 ASCII 输入会泄漏裸 `ValueError`；该轮当时的合同要求固定 Node codec 语义与稳定 typed outcome。2026-08-07 carrier 重裁已把 Node 范围收窄为 upstream v1 合法主路径 compatibility consumer，不再要求所有 malformed 边界逐字节一致；current expected 以双格式 Spec 的当前版本为准。
4. **Unknown declared field gate fail open。** 旧 HEAD 的 allowlist 动态取自 Pydantic `model_fields` 且只检查 `model_extra`；共享模型未来正式声明新字段后，converter 可能静默丢弃。目标合同要求 converter 自身维护静态 consumed-field 合同，并对 `model_fields_set ∪ model_extra.keys()` fail closed。

[Request converter 独立验收](reports/260806-verify-request-converter.md)在旧 HEAD 上给出 `FAIL`。其中 malformed Unicode carrier 泄漏裸 `ValueError` 与第 3 项 major 是同一缺陷族。报告原列的 server-tool F1 已由后续独立裁决撤销，不再是实现缺陷。

### Server-tool 裁决

[Server-tool 合同裁决](reports/260806-arbitrate-server-tool-contract.md)已经定案：**reject 成立**。Anthropic typed／server tool 在本项目继续以稳定 `server_tool_not_supported` 显式拒绝；不得映射为 Responses hosted builtin，也不得把另一个项目的专用 WebSearch 合同当作本项目 oracle。

处置结果固定为：

1. `260806-verify-request-converter.md` 的 F1 记为“已撤销／oracle 不适用”，不据此改代码或测试，也不重写该历史报告。
2. R2 复评与重新验收只处理其余有效发现，并明确以主仓当前 Spec 的 no-revive 合同为 expected。
3. 未来若要支持 Responses hosted server tools，必须先形成独立产品规格与用户裁决，完整覆盖 request、response、stream lifecycle、History／continuation、error 与 capability gate；不得从 converter 映射表增量偷渡。

**2026-08-24 追加，tool search：用户裁定它不是本代理提供的能力。** 触发是线上 400 `req=fcc0bebc`（`gpt-5.6-sol`）：`Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.`。这一格恰好把上面第 3 条的「不得增量偷渡」摆到了眼前——实测表明偷渡在技术上是通的（`{"type":"tool_search"}` 与 `defer_loading: true` 同发返回 200，且上游拒绝 Anthropic 拼法时列出的支持枚举里就有 `tool_search`，见 [reports/260824-responses-leg-tool-field-measurements.md](reports/260824-responses-leg-tool-field-measurements.md)），**而技术上通不是做的理由**。已落地的是相反方向的三件事：

1. `translation_driver/openai_responses.py` 的 `_function_tool` 由黑名单复制改为**按白名单重建**（字段表取自 openai SDK 3.3.1 的 `FunctionToolParam`）。根因不是漏了 `defer_loading` 一格，而是「除了 `input_schema` 都带过去」会把客户端此刻与将来放在 tool 上的任何键都送给一个从未同意过它的 endpoint；`cache_control` 与 `eager_input_streaming` 当时也在漏，只是这条腿恰好接受它们。
2. `defer_loading` 不进 wire：`true` 记 `SERVER_TOOL_CONSTRAINT_DROPPED`，`false` 静默移除。
3. legacy `AppSettings` 里两个从未接线的开关 `tool_search` / `tool_search_non_deferred` 已删除。它们零消费者，且 `AppSettings` 整体已不服务生产路径。

规范条款见 [spec.md](spec.md) 的「Tools 与 tool choice」与请求字段矩阵。

### 历史评审与主树结果

[Request R2 代码复评](reports/260806-review-code-request-r2.md)在 `028f1f2…` 上关闭首轮四项 major，但新增 1 major：unknown budget limits 与明确无界被混同；同 HEAD 的[独立行为复验](reports/260806-verify-request-r2.md)为 PASS。[Request R3](reports/260806-review-code-request-r3.md)已在 `fdd2f75…` 上确认该 major 关闭，结论为 blocker 0、major 0；其reviewed source已归档，净语义已进入main。

完整 foundations integration曾在 `6a00f6f…` 中把 request converter合到 cardinality＋liveness基线上，没有用 request分支的旧整文件覆盖 `responses_reasoning.py`。[merged-state 代码 R2](reports/260806-review-code-bridge-foundations-r2.md)确认新增 major已关闭，[独立复验 R2](reports/260806-verify-bridge-foundations-r2.md)确认空 content-list typed reject与真实 forward→`MessagesRequest`→public converter 的 $N \rightarrow N$ reasoning接缝范围内 `PASS`。该语义现已作为 `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` 进入 `main`，reviewed source由 `archive/260807-anthropic-responses-request@fdd2f75f…` 精确保留；integration报告继续只作历史 provenance。

## 文档复评剩余项

| 文档 | 最新报告 | 当前剩余项 | 下一报告 |
|---|---|---|---|
| [Spec](spec.md) | 历史carrier评审链及本轮收尾一致性复核 | Current `FINALIZED@4c9beed…`；收尾修订只把旧实现快照改为历史基线，不改变行为合同 | 作为 current 行为 oracle继续实施；文档状态不证明候选实现符合 |
| [Architecture](architecture.md) | 技术 [R3](reports/260806-review-bridge-architecture-r3.md)；[裁决矩阵终审](reports/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审为 blocker 0、major 0，确认 Architecture 已具备用户裁决条件；它仍是非规范提案、不是 ADR，`D-ARCH`／`D-MIGRATION` 尚待用户完整阅读后亲自裁决 | 用户接受前 Architecture 不产生 expected；终审 0／0不替代用户裁决 |
| [Acceptance](acceptance.md) | 历史空reasoning评审链及本轮收尾policy复核 | Current `FINALIZED_ACCEPTANCE_ORACLE@f99492a…`，首屏绑定 current Spec／Architecture；产品继续`UNVERIFIED` | 作为current验收oracle继续实施；不得把文档状态外推为产品`PASS` |
| [Research](research.md) | [外部变化只读复核](reports/260807-review-research-external-change.md) | blocker 0、major 0；current Research 可提交，route 作用域只覆盖 Anthropic `/v1/messages` bridge，不改变 native Responses 公共入口 | 无待修；Research 始终不产生 behavior expected |
| [文档整理状态](../documentation-restructure/README.md) | 旧计划已归档到 `archive-260808/plan.md` | 整理 live 入口、提炼仍有效结论和按主题归档历史材料的目标继续保留；generation／certificate／ledger 等证明治理方案已终止 | 按普通增量文档维护继续，不为文档整理建设新的验证控制面 |
| [Service cutover plan](../service-cutover/plan.md)／[systemd runtime plan](../systemd-runtime/plan.md)／[readiness](../service-cutover/readiness.md) | [new-main merged-state review](../systemd-runtime/reports/260807-resume-review-systemd-rebuild.md)；[new-main独立验收](../systemd-runtime/reports/260807-verify-systemd-rebuild-resume.md)；[第二份独立验收](../systemd-runtime/reports/260807-resume-verify-systemd-rebuild.md)；[systemd Plan current R3](../systemd-runtime/reports/260807-resume-review-systemd-plan-current-r3.md)；[Readiness current R2](../service-cutover/reports/260807-resume-review-readiness-current-r2.md)；[S5执行记录](../systemd-runtime/reports/260807-systemd-user-manager-smoke.md) | S3 `c53849e…`与S4 `e9fb277…`均已进入main并归档reviewed source，current主树为`c1de6bf…`。真实启动readiness及non-stream／stream 200不是manager／cgroup证据；S5独立manager未创建private control socket，故本机真实activation／effective cgroup仍为`BLOCKED`，`NO_CUTOVER`不变 | 在受控VM／container继续S5诊断，S7后续。任何仓库或真实应用canary绿灯都不授权安装生产unit、部署或cutover |
| [README](README.md) | [R2](reports/260806-review-bridge-readme-r2.md)；Architecture [裁决矩阵终审](reports/260807-review-architecture-decision-matrix.md) | 裁决矩阵终审确认用户可从 README 开始按阅读顺序进入五份文档；该结论只覆盖 Architecture 用户阅读入口，不是 README 全量新复评或产品状态证据 | 保持 current 导航与 Architecture 待用户裁决边界一致，不传播旧 Acceptance verdict |
| 本文 | [Implementation post-S3 定向复评](reports/260807-resume-review-implementation-post-s3.md)精确绑定历史内容身份 | Current `c1de6bf…`已包含并归档tool／reasoning最小纵向切片；对应scoped PASS已取得。完整tool／reasoning矩阵、quota／backpressure、kernel partial-write与S5 manager／cgroup仍未验证。完整产品`UNVERIFIED`、部署`NO_CUTOVER`、本文`LIVING` | 下一核心先闭合kernel partial-write；完整tool／reasoning矩阵按Acceptance保持open但不重复已通过主路径，S5在外部环境并行推进 |

新报告不得使用无日期前缀的旧式名称，也不得沿用与实际创建日不符的固定日期；同一对象多轮复评递增 `-rN`，不得覆盖上一轮报告。报告正文绑定完整 commit、文档内容 hash 或两者，不能只写分支名。既有历史报告不因本规则批量改名。

## 收敛与分支归档策略

本节约束当前已知分支的回放与归档，不是 Implementation 的封存条件。完成某一 squash、归档或 merged-state review后，本文仍须记录后续开发线、组合事实和新发现；只有事实本身由更新后的证据支持时，才能改变对应状态。

### 逐片收敛

1. 每个新候选 HEAD 只有在独立复评 blocker 0、major 0，且该 HEAD 的声明范围测试、smoke、lint 与类型检查 gate 通过后，才可进入该片的回放／归档。Foundations、happy、usage、systemd runtime、bridge semantic／route／block／capability／History／stream、systemd S3／S4、stream request facts、network retry、resident primitive／wiring及token／response／item identity fixes均已完成该轮收敛并进入current `main@c1de6bf…`；其旧source／integration verdict只作历史provenance。任一新切片的声明范围先达到0／0即可按其剩余gate收敛，不等待完整bridge；独立验收缺口与后补边界继续单独登记，不因回放消失。
2. 每次 shell 操作先 gate `/home/xp/src/ghc-api-proxy-py` 的物理 root、分支 `main` 与 `HEAD == refs/heads/main`；记录当时完整 main HEAD。分支或 integration worktree 的绿色结果不能替代最终 main 组合验证。
3. Current Spec为`FINALIZED@4c9beed…`；Acceptance为`FINALIZED_ACCEPTANCE_ORACLE@f99492a…`并绑定current Architecture `746adc7…`。Current `c1de6bf…`已包含并归档tool／reasoning最小纵向切片；对应scoped canary已通过。完整tool／reasoning矩阵、quota／backpressure、kernel partial-write与真实manager／cgroup仍未闭合。旧评审与已完成候选回放清单只作历史证据。
4. Bridge successor三片已作为`bfc461f… → 86b6cc3… → b91e58a…`进入main，后继capability、History与stream又作为`bd86207… → 38bb06f… → ae84aa9…`进入main；六片均完成main-side gate／archive。旧source、integration与WIP身份均不得再作为current载荷。Current main定向stream review为0 major，但完整retry、buffer cap 下的背压、真实socket partial-write与完整Acceptance继续登记为未验证，不得从定向PASS外推。
5. Graceful-timeout S3已作为`c53849e…`进入main并归档，user-install S4已作为`e9fb277…`进入main并由`archive/260807-systemd-user-install@e16c2a7…`归档；current main已前进到`c1de6bf…`。不得再次回放`8cae6c2… → d3fabfa…`、old-base链或source S4 patch。S5必须从current main在隔离manager边界执行，不得把真实应用readiness或仓库gate冒充manager／cgroup运行态证据。
6. Current产品执行面按真实未验证边界推进：token／response／item identity fixes均已进入main并归档，真实纯文本、tool／reasoning最小纵向层已通过。下一核心顺序是kernel partial-write与manager／cgroup；完整tool／reasoning矩阵继续按Acceptance保持未验证。任何局部review、测试、canary或归档都不改变产品`UNVERIFIED`或部署`NO_CUTOVER`；只有完整bridge按current Acceptance required gates取得实证，产品verdict才可升级。

### 保留评审证据与归档

- Squash 前不强制改写候选分支。若复评要求继续修复，在活动分支追加提交并对新的完整 HEAD 重新评审；旧报告永远只绑定其原 HEAD。
- 每片回放并完成 main侧验证后，为**最终独立评审通过的 pre-squash HEAD**创建 immutable archive ref。现有 reasoning archive保持指向 `d90c90d…`；foundations refs精确为 `archive/260807-anthropic-responses-reasoning-cardinality@b876e62…`、`archive/260807-anthropic-responses-liveness@f27a8c0…` 与 `archive/260807-anthropic-responses-request@fdd2f75…`；happy／usage refs精确为 `archive/260807-reasoning-carrier-v2@8301ee9…`、`archive/260807-responses-anthropic-nonstream@7ddf173…`、`archive/260807-responses-stream-parser@73a6aa1…`、`archive/260807-anthropic-responses-route-policy@84a22c0…` 与 `archive/260807-nonstream-usage-details@aca3ced…`；后继refs精确为`archive/260807-responses-semantic-parity@f5bca39…`、`archive/260807-anthropic-responses-route-happy@dd376d6…`、`archive/260807-anthropic-block-delivery@e506bf8…`、`archive/260807-responses-reasoning-capability@8bff1c3…`、`archive/260807-responses-history-facts@b1df8f9…`、`archive/260807-anthropic-responses-stream-route@f3922a9…`、`archive/260807-stream-request-facts@4fa7a877…`、`archive/260807-responses-network-retry@584e63b…`、`archive/260807-resident-byte-budget@8fb6a97…`、`archive/260807-resident-budget-wiring@aa5f1d3…`、`archive/260807-copilot-token-identity@8f164d8…`、`archive/260807-copilot-response-identity@1bc5a81…`与`archive/260807-copilot-item-identity@f171fa0…`；systemd refs精确为`archive/260807-systemd-runtime@49fb198…`、`archive/260807-systemd-graceful-timeout@865a5b7…`与`archive/260807-systemd-user-install@e16c2a7…`。不得用integration commit替代reviewed feature HEAD。对应feature worktree／branch clean且archive ref精确后，可随该片逐片清理。
- Archive ref 必须在移除 worktree 与活动 `feat/*` 分支之前创建并机械验证精确指向 reviewed HEAD。Archive ref 是只读追溯证据，不代表可部署主线；创建后不得 force-update。若归档后发现新缺陷，从正确基线建立新活动分支与新评审轮，不移动旧 archive ref。
- 删除 feature worktree 或其活动分支前必须同时确认：该片 archive ref 精确；main 包含该片 squash 语义；该片 main-side gate 通过；feature worktree clean。任一条件不满足都停止清理，且不得用整文件 restore 或强制删除掩盖状态。
- 历史 foundations／happy integration worktree／branch不按单片清理。其组合语义已按序进入current `main`，main-side gate与archive refs均已完成；只有另行机械确认integration HEAD、提交清单和worktree clean后才允许移除历史载体。本轮文档更新不声称该清理已执行。
- Archive refs至少保留到相关merged-state review与长期文档收敛完成；之后是否删除由用户另行决定。本轮文档更新不创建、移动或删除任何ref／worktree／分支。

### 回滚

Main上的foundations、systemd runtime、happy、usage、semantic、route、block、capability、History、stream、S3、S4、stream request facts、network retry、Copilot identity及tool／reasoning最小纵向切片均保持独立语义提交；出现组合回归时先定位到引入缺陷的最低共同层，再按提交依赖逆序形成显式revert，不把“最新提交”自动当作根因，也不整文件恢复相邻切片。原reviewed HEAD仍由archive ref保留；回滚只改变main上的集成提交，不移动archive ref，也不覆盖评审证据。2026-08-08 快照锚点为`main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`，`main` 其后已继续前进，两片 resident 切片的机制已由 `546852a` 删除；旧successor、旧bridge-next与旧systemd integration只保留provenance。后续边界验证若发现代码缺口，必须从current main建立新切片，不复用旧identity、S4、request-facts、network-retry、resident primitive或wiring candidate／integration identity。

## 下一步

以下是 current snapshot 的执行顺序，不是把 Implementation 收口的一次性清单。任一步产生新代码、评审结论、回放结果、合并关系或新发现，都先把本文更新到 current 事实，再继续后续步骤；0 blocker／0 major只放行继续实施，不终止该更新循环。

1. **冻结current主线与真实canary边界**：current主线为`c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`；token、response与item identity提交分别为`c188165…`、`0e66cab…`与`fb4272b…`，tool／reasoning后继分别为`e8708fb…`与`c1de6bf…`，对应reviewed source archives精确保留且不移动。
2. **确认当前实测层**：隔离`127.0.0.1:4142`真实启动取得readiness 200与32／10目录；正式`route_override=responses`下真实`gpt-5.3-codex` non-stream与stream均为HTTP 200，stream产生合法Anthropic SSE终态序列。旧Bun在成功窗口内身份快照不变且零signal，收口后`4142`零listener。
3. **形成current living checkpoint**：以current Implementation与Readiness bytes记录上述事实和未验证边界；该checkpoint不得冒充完整产品`PASS`。
4. **Tool／reasoning当前层已闭合**：Tool切片证明forced ordinary function tool与tool-result continuation；Reasoning切片证明project-v1 payload carrier与client echo被真实上游接受。完整tool choice／name restore／malformed／server-tool拒绝矩阵，以及reasoning multi-item／encrypted-only／malformed／双格式consumer矩阵继续按Acceptance保持`UNVERIFIED`。
5. **下一核心边界继续分片闭合**：用真实loopback sink闭合kernel partial-write的body短写／RST及accepted／partial／uncertain分类。原列的完整quota／backpressure（resident owner、admission、metrics／History映射）已随 2026-08-19 的用户裁决删除，不再是下一步。Manager／cgroup仍需在具备独立user manager与delegated cgroup v2的可销毁环境继续S5。P2与P3保持open；任何局部通过都不改变产品`UNVERIFIED`或部署`NO_CUTOVER`。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/pipeline/delivery/stream.py` 的 terminal frames 与 legacy `src/app/delivery/responses_anthropic_stream.py` 的 `not frontier.terminal_accepted` 分支 | 同一条冻结规则在两条链路上一实现一缺失。legacy 对无合法 terminal event 的 EOF 抛 `incomplete_responses_stream` 并 render SSE error；新 pipeline 链路仍 flush `message_delta{stop_reason:"end_turn"}`＋`message_stop`，把被截断的 turn 伪装成干净结束并存进客户端历史。这是**回归**，不是未开工功能，STR-04 的验收判据早已冻结 | **SSE 信封一半已闭合（`16dd68c`，2026-08-20）**：`stream_delivery` 在 `started and not terminal.seen` 时发 Anthropic SSE `error`（`upstream_error` ／ `incomplete_responses_stream`）并**不再**跟发 `message_delta`＋`message_stop`；`error_frame` 的线上形状与 legacy `render_error` 逐字节相同，`not started` 时不发的门也照搬 legacy 的 `message_start_accepted`，均为移植而非重新设计。钉住旧行为的测试已按其 docstring 的自陈反转为 `test_a_truncated_stream_ends_in_an_error_event_and_never_claims_success`，另有 `test_a_synthesized_start_that_never_gets_a_block_ends_in_an_error` 覆盖合成 start 后无终止事件的退化线（**该测试已于 2026-08-22 随 `0b57645` 删除**：用户裁决不再合成 HTTP 响应头、因而也不再合成 `message_start`，它覆盖的那条退化线已不可达。此处保留原文以说明当时闭合了什么）。**failed History 一半仍未闭合**，见下一行：`context.reply` 仍 gate 在 `terminal.seen`，被截断的回复不进 `reply`，该半需与 `context.reply` 放宽同时裁决。操作者一侧的止血（请求行报 `[FAIL]` 与成因）不变，见 `.dev/docs/tui/archive-truncated-stream/` |
| `_StreamAccounting.finish()` 中 `trace.absorb` 与 `context.reply` 的两套门 | 日志行无条件吃下已观测事实，`context.reply` 仍 gate 在 `terminal.seen` 上。两者会分叉出两种形态：被截断的回复不进 `reply`；以及 Anthropic 腿在 `message_delta` 后干净收尾时，日志行完全干净（`ok`、有真实 reason 与 usage）却仍不写 `reply`。今天 `context.reply` 无读者所以无可观测影响 | 有意保持不一致并就地注释。理由**不是**「无读者故推迟决定」——`Terminal.seen` 就在记录上，无条件写入才是保留选择权的那一侧，不写是销毁信息。真正的理由是保守：`reply is not None ⇒ 回复已完成` 是 hooks 与 History 现有契约，放宽它是契约变更；而 STR-04 已点名需要 failed History，第一个读者不是假想的。故与 STR-04 同一切片一并裁决 |
| `src/app/streaming/keepalive.py` 的 cleanup 路径 | cancellation 与资源清理所有权交叠；secondary failure 可能覆盖 primary failure | `f27a8c0` 已修且 R3 0／0；保留 cancellation-storm、cause chain、资源归零与无 orphan task 为组合回归 gate |
| `src/app/protocols/anthropic_responses.py` 的 tool-name／unknown-field／carrier／thinking 边界 | 多项 fail-closed 合同集中在单一 converter，相邻修复容易互相遮蔽 | `fdd2f75` 已获 R3 0／0；最终组合继续运行 request 行为 gate，不以父提交 PASS 自动覆盖新基线 |
| `src/app/anthropic/thinking/responses_reasoning.py` 的双分支修改 | cardinality 与 request decoder hardening 修改同一文件，错误回放来源会恢复旧聚合 API | 完整 integration 链已按 cardinality → request 顺序完成语义合成并通过 R2；current main 与后续 route／delivery 组合继续联合测试，禁止改用 feature 原提交链或整文件覆盖 |
| request 验收报告与主仓正式 Spec | 两个 oracle 对 server-tool 支持给出相反 expected | 已裁决 reject；外部 F1 撤销，不再作为待实现项 |
| `src/app/routes/anthropic.py`、`src/app/anthropic/client.py` 与 `src/app/pipeline/executor.py` | Non-stream与Responses stream均已生产接线，但局部happy路径容易被误写成完整stream已验收 | Current main定向review与backup happy smoke守住同一`RequestContext`、single pipeline owner与关键error／cancel；未覆盖矩阵继续按执行记录逐项补齐，产品保持`UNVERIFIED` |
| Route-happy与block-delivery的共享生命周期接缝 | 两片已在production stream路径组合；若后继边界修复让route、delivery与ASGI各自finalize，仍可能重新形成第二sink或第二lifecycle owner | Main stream只建立一个`DeliverySession`和一个ASGI writer，并让同一`RequestContext`贯穿route→parser→delivery→History／hooks；后继边界切片继续以真实ASGI E2E与owner identity正控固定接缝 |
| `src/app/anthropic/client.py` 与 response header policy 的Responses adapter边界 | 旧Route candidate代码review通过，但真实ASGI verify证明通用Anthropic header policy在默认非strict模式下会放行Responses-specific header；局部marker blacklist会继续漏掉等价拼写 | `44808b7d…`已在共享Responses header归一化边界关闭该轴，完整route range随后作为`86b6cc3…`进入main；其main-side gate继续守success／error header矩阵，stream route必须复用同一policy |
| `src/app/openai/responses_stream_parser.py` 与 `src/app/delivery/anthropic_sse.py` | Parser、continuous-prefix／single-writer delivery与production ASGI sink已组合，后继边界修复仍可能绕过delivery frontier | Main stream只把parser facts交给`DeliverySession`，由delivery拥有排序、render、sink与frontier；parser不得知道commit或直接写body |
| `src/app/anthropic/thinking/responses_reasoning.py` 与 `src/app/openai/responses_stream_parser.py` 的空reasoning判定 | 同一semantic rule双实现曾发生漂移；代码review与旧verify对正确expected冲突 | 仲裁已冻结one-empty-item／one-bare-block并确认`1cde3d58…`该轴正确；撤销零-block门，后续共享normalizer与双路径正反控制不得改变cardinality |
| `src/app/openai/responses_stream_parser.py` 的authoritative lifecycle与summary schema | 历史unknown summary／done-only缺陷已修，但production stream接线可能绕过current parser或在ASGI层降级typed error | `bfc461f…`已进入main并归档；stream route必须调用current parser并把typed protocol／delivery失败映射到同一context终态，不复制弱化解析器 |
| `implementation.md` 的current identity与动作 | Route、semantic、block、capability、History、stream、systemd与Acceptance状态在顶部、处置表、进度表、开发线、收敛、下一步和结尾多点复述，main前进时容易出现弱一致性副本 | 本轮同步current `main@c1de6bf…`、tool／reasoning archives与scoped PASS；下一核心序列统一为kernel partial-write，manager／cgroup并行开放 |
| `src/app/pipeline/executor.py` 的pre-attempt failure路径 | 统一failure finalizer与stream attempt均已进入main，后继retry／delivery边界修复容易分叉出另一套success／failure终结路径 | 保留`86b6cc3…`与`ae84aa9…`的single-owner hooks／History合同；stream attempt、parser／delivery错误与ASGI完成都必须在同一`RequestContext`上exactly-once finalize |
| `ResponsesStreamParser` item-level `source_order` 与 block-delivery排序坐标 | R1证明旧候选把item order误作block稠密序号 | Main `b91e58a…`及archive `e506bf87…`已用multi-part、zero-block、较晚item与sparse parts验证typed ordering；production stream gate不得由手工稠密order fixture旁路 |
| Block delivery terminal／open-source与异步writer | R1证明旧session可越过open source成功terminal，且single writer不等于异步串行 | Main `b91e58a…`的typed terminal与operation lock已通过main-side gate；stream happy path增加真实ASGI sink正控，完整Acceptance继续覆盖partial write与retry frontier |
| Reasoning carrier、non-stream response、usage与route已进入main | 局部主线与happy smoke全绿容易掩盖完整stream矩阵仍未验收 | Current main定向review与backup happy smoke只作已覆盖范围证据；semantic reorder、usage／terminal／History矩阵、retry、quota／backpressure、真实partial-write与完整Acceptance逐项保持未验证 |
| 历史 source refs与current main commits | Reviewed source identity与main squash identity不同，后续若从旧source重建会制造第二条实现链 | 最新archives保持immutable且只作provenance；current主线锚点为`c1de6bf…`。已收敛切片不再从冻结candidate、reviewed source或历史integration重建；后继缺口只从current main建立新切片 |
| `../systemd-runtime/plan.md` 与 systemd 代码提交 | 旧integration把高频living Plan与可复用代码patch绑在同一提交；Plan若落后main事实，会使运行态执行者使用陈旧parent | S3 `c53849e…`与S4 `e9fb277…`均已进入main并归档；S5只从current main按隔离manager／cgroup gate执行，不回放old Plan postimage或历史code-only链 |
| `fix/responses-history-facts` 的source与main身份 | Reviewed source、integration与main squash身份不同，容易把历史候选状态重新写成current缺陷 | Current main`38bb06f…`已关闭旧History major并归档`b1df8f9…`；后续只在真实新缺陷下建立新切片，不回退旧candidate |
| `feat/anthropic-responses-stream-route` 的多轮身份与证据范围 | R1、R2、tracked-WIP、R3、main squash与backup smoke属于不同身份与范围；容易把局部PASS外推到完整Acceptance | Main`ae84aa9…`与archive`f3922a9…`已收敛happy切片；main定向review为0 major，backup smoke只为`PASS_HAPPY_BACKUP_PORT_SMOKE`。未验证矩阵继续逐项登记，不重复回放旧source |
| `../service-cutover/reports/260807-resume-backup-port-smoke-execution.md` 的happy PASS与完整入口边界 | Happy运行证据真实存在，但R3持久化harness／safety tests与全量STREAM-MERGE矩阵仍缺失，容易被一句“smoke PASS”洗平 | 固定verdict为`PASS_HAPPY_BACKUP_PORT_SMOKE`；以执行记录的未验证清单作为后继切片输入，已通过项不重复施工，未通过项不冒充PASS |
| Systemd source 与 main squash | Source R4绑定 `49fb198…`，main commit为 `cf53334…`；reviewed source与集成提交身份层级不同 | 已以 `archive/260807-systemd-runtime@49fb198…` 保留 source并通过 main gate；仍不得把 main commit外推为安装态或 cutover证据 |
| `contrib/systemd/ghc-api-proxy.service` timeout 与应用shutdown | `TimeoutStopSec`、Uvicorn graceful cap与lifespan cleanup不是同一真相源，unit数值可在代码行为改变后静默漂移 | Graceful-timeout从真实调用链冻结单一公式并用低时长执行测试机械对账；user-install不得复制未冻结常量 |
| System unit与未来rootless user unit | 直接复制模板会让`User=`、paths、targets、slice与timeout各自漂移；install helper又容易越过dry-run边界改变manager状态 | User-install使用共享typed render inputs与明确的system／user渲染合同，默认dry-run；隔离测试证明无真实config或manager副作用，并与graceful-timeout做merged-state复核 |
| `localhost:4141` 的双运行时目标 | 当前 Bun 裸进程与未来 systemd socket 都可能成为 listener owner，直接启动会端口争用或误判新服务已接管 | Cutover 明确设置唯一 socket owner、旧 listener 释放、health 与 rollback gate；代码 review／unit smoke 不外推为运行态切换证据 |

Spec `FINALIZED@4c9beed…`继续提供current行为oracle；Acceptance `FINALIZED_ACCEPTANCE_ORACLE@f99492a…`绑定current Spec与Architecture。Current `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`已包含并归档tool与reasoning最小纵向切片；真实forced ordinary tool roundtrip与单item project-v1 reasoning carrier echo均为scoped PASS。完整tool／reasoning矩阵、quota／backpressure、kernel partial-write与真实manager／cgroup仍未闭合。整体保持`NO_CUTOVER`与产品`UNVERIFIED`，本文保持`LIVING`、不收口。