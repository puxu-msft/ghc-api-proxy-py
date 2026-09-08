# Anthropic Responses bridge 正式文档 merged-state 最终评审 R2

- **评审范围**：主树 current 7 份正式文档：`docs/agents/anthropic-responses-bridge/{README,spec,research,architecture,acceptance,implementation}.md` 与 `docs/agents/documentation-restructure/plan.md`。本轮不重复首轮技术审查，只审查最终合并态的权威角色、状态、跨文档合同、导航、易变状态与下一步执行接缝。
- **总体 verdict**：**修复 major 后可进入。** Bridge 的正式行为合同与 integration 状态整体一致，但 3 处 current-state／执行接缝仍会让读者采取错误动作，因此 7 份文档当前还不能作为一个正式 docs 提交。
- **blocker 数**：0。
- **major 数**：3。
- **minor 数**：0。
- **提交判断**：当前不可作为一个正式 docs 提交。修复 3 条 major 后需对受影响的新 bytes 做定向 merged-state 复评；若届时为 0 blocker、0 major，应明确判定 7 份文档可作为一个正式 docs 提交。

## 双视角覆盖证据

### 机械核对视角

- 每次 shell 调用均在同一调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。
- 评审开始时连续两次计算 7 份文档 SHA-256，结果逐项一致；落盘前第三次按冻结清单执行 `sha256sum -c`，7 项全部 `OK`。稳定输入如下：

| 文档 | SHA-256 |
|---|---|
| `docs/agents/anthropic-responses-bridge/README.md` | `3f48e6a3cab32545591bad32ae3ee96682a4d9cc870408fbe1da87f664b9b920` |
| `docs/agents/anthropic-responses-bridge/spec.md` | `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694` |
| `docs/agents/anthropic-responses-bridge/research.md` | `54cf0cde2bc7122516bec9948f62a65f7900c775d5bd1da6200cb224f184856e` |
| `docs/agents/anthropic-responses-bridge/architecture.md` | `6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327` |
| `docs/agents/anthropic-responses-bridge/acceptance.md` | `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091` |
| `docs/agents/anthropic-responses-bridge/implementation.md` | `e43fd96003a8de3a1b9c5e165a65d711e25e76d1cc6444415088af0a994dda65` |
| `docs/agents/documentation-restructure/plan.md` | `53f7a02c936801e5f68fb67701449521941f2599c1d0092a8cf11eea1a6190ad` |

- 对账了 README 权威角色表、Spec `FINALIZED`、Acceptance `FINALIZED_ACCEPTANCE_ORACLE`、Architecture 非规范身份、`D-ARCH`／`D-MIGRATION` 唯一待用户裁决面，以及 `ADR-BRIDGE-02`～`06` 仅承载已决 Spec 的分类。
- 对账了 reasoning carrier／cardinality、encrypted-only no-loss、server-tool no-revive、完整 block buffering、首 block 前 delayed start、route precedence、unknown capability fail closed、post-commit partial failure、普通 per-request aggregate＋global reservation、无 16 MiB 专门分支，以及四项低概率扩展的冻结基础行为。未发现这些合同被另一份正式文档重开或改写。
- 实际 gate `/home/xp/src/ghc-api-proxy-py-integrate-bridge`：`integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79` clean；三提交父链精确为 `9e5f874d5b547bd9d733b0ee134e165f818de205 → cae83f467aa66ebae74c27ad2270a79f5dd9aa8e → 6a00f6f7aaa5083cebd7387208eca65b7df3bd79`；base 为 `ed77c9d…`；tip 尚未进入 `main`。该结果与 README／Implementation 的代码状态一致。
- 仓库内本地 Markdown 文件链接存在性扫描覆盖 7 份文档、66 个本地目标，缺失数为 0。该扫描证明目标文件存在；heading／renderer 完整语义仍应由文档重组计划拟建的正式 link checker 负责。
- `git diff --check` 对 7 份文档通过。

### 第一人称执行视角

- 以首次阅读者从 README 按 `Spec → Research → Architecture → Acceptance → Implementation` 顺序完整阅读，模拟“判断什么是行为 oracle、什么仍待用户裁决、什么已经实现”的路径。
- 以用户裁决执行者走读 Architecture：只允许回答 `D-ARCH` 与条件性的 `D-MIGRATION`，并验证拒绝或接受它们都不会重开 route、reasoning、server-tool、buffering、capacity 或 post-commit 合同。
- 以 docs 收敛执行者从 Implementation 的“文档复评剩余项”与“下一步”开始，模拟完成文档门、形成 docs 提交、然后逐片回放 integration 三提交的路径。
- 以文档重组执行者从阶段 0 空目录开始，模拟创建 verification assets、产出独立评审报告、登记全部 `docs/tmp/*.md`、运行 action-scoped matrix checker并形成第一个 `test(docs)` 提交；该模拟暴露了 bootstrap／自指缺口。
- 以产品回放执行者验证 docs 提交后按 cardinality → liveness → request 逐片回放、逐片 main-side gate、逐片 archive feature HEAD，且共享 integration 载体只在三片全部进入 main 后清理。该顺序本身一致。

## 事实性发现

### [major] `architecture.md:3`、`acceptance.md:11,29,400` — 正式源文档仍把旧评审轮次写成 current 状态依据，与同组文档记录的实际 current 终审矛盾

**问题**：Architecture 顶部仍写“仍须独立复评”，但 README、Acceptance、Implementation 与实际 `docs/tmp/260807-review-architecture-decision-matrix.md` 均记录 current Architecture 裁决矩阵已经独立终审为 blocker 0、major 0。Acceptance 自身则仍反复以 R6 作为 current 定稿依据；Implementation 明确说明 R6 只绑定旧 Architecture 快照，current 文件组合的终审是 R7，且实际 `docs/tmp/260807-review-bridge-acceptance-r7.md` 为 blocker 0、major 0。

**证据或失败场景**：从 README 进入 Architecture 的用户会同时读到“已通过独立终审”和“仍须独立复评”；从 Acceptance 自身判断 provenance 的执行者会把旧 R6 当 current 依据，而从 Implementation 判断时又必须排除 R6、采用 R7。虽然“Architecture 尚未获用户接受”和“产品仍为 `UNVERIFIED`”都正确，但正式源文档不能依赖旁边另一份文档替自己纠正 current review provenance。作为一个 docs 提交合并后，这会留下两个互相冲突的“下一门是什么”。

**修复建议**：Architecture 顶部保留“非规范提案、尚未获用户接受”，但把“仍须独立复评”更新为裁决矩阵终审已 0／0、仅剩用户完整阅读后裁决。Acceptance 将 current 文件组合的独立终审依据更新为 R7，并把 R6 明确降为旧快照历史记录；同步状态段、manifest 状态说明、最终状态和处置表，不能只在一处追加 R7。

### [major] `implementation.md:144,146,156,176,196` — 易变状态源仍把已完成的 Plan major 修订写成“正在修订／先关闭”，导致 docs 收敛下一动作倒退

**问题**：current `plan.md:3` 与 `plan.md:657-658` 已明确写明 R4 的两项 major 都已修订并映射到可验收条款，当前剩余动作是对新 bytes 做定向独立复评。Implementation 却仍写“规范输入内容身份门与临时报告及时归纳阻断规则正在修订”“关闭 Plan R4 的 2 项 major并定向复评”，并在多处把“关闭 major”列为 docs 提交前的下一动作。

**证据或失败场景**：以 Implementation 作为易变状态真相源执行时，下一位实施者会重新修改已经完成修订的两处合同，而不是直接对 current Plan 发起定向复评。这不仅重复工作，还可能改变已经稳定并绑定 SHA `53f7a02…` 的 Plan bytes，重启新一轮评审。README 明确指定 Implementation 为候选／integration／下一动作的真相源，因此不能靠 Plan 自身状态让读者自行纠正。

**修复建议**：把 Plan 状态统一改为“R4 两项 major 已修订，current bytes 待定向独立复评；复评达到 0／0 后可提交执行”。同步 Implementation 的权威边界、major 处置表、文档复评表、主树 WIP 门、Squash 前置门、“下一步”和末尾总结；下一动作应是“复评 Plan current bytes”，不是“继续关闭 R4 major”。

### [major] `plan.md:276-289,293-318,643` — 阶段 0 首次提交缺少可执行 bootstrap 规则，且“登记全部实际 tmp 报告”与本轮评审报告形成自指闭环

**问题**：计划要求每次 docs 提交前调用“阶段 0 已提交”的 report-distillation checker，并要求 checker 将实际 `docs/tmp/*.md` 与 ledger 双向精确对账；阶段 0 的唯一提交本身却正是第一次创建并提交 checker、ledger 与 pathspec。计划没有说明在 checker 尚未提交时，阶段 0 的首次 `test(docs)` 提交如何合法通过这条通用前置门。更严重的是，阶段 0 verification assets 按计划必须先独立评审；该评审会产生新的 `docs/tmp/*.md` 报告，继而要求修改 ledger。修改 ledger 会改变刚被评审的阶段 0 artifact；若再评审新 ledger，又会产生新的 tmp 报告并再次要求登记，形成无限自指。

**证据或失败场景**：第一人称执行阶段 0：先创建 checker／ledger → 为满足“独立评审”产出报告 A → A 是新的实际 tmp 文件，旧 ledger 立即失效 → 把 A 加入 ledger 后，评审对象 bytes 改变 → 对新 bytes复评产出报告 B → B 又必须加入 ledger。即使不评审 ledger，阶段 0 commit 仍无法调用“阶段 0 已提交”的 checker，因为该提交尚不存在。现有“阶段 0 独占 verification 路径”只解决 staged path 范围，没有解决 gate 的时间边界与自指。

**修复建议**：显式冻结 bootstrap 协议，而不是让执行者临场豁免。例如将阶段 0 拆成两个无环提交：先提交最小 checker/schema/fixtures，并用 repo 外冻结 fixture 做正反控制；再生成 current manifest／ledger并用已提交 checker验证。为 tmp ledger 定义可复现的报告 cut-off／generation 或排除“评审 ledger 自身”的报告并将其结论落到下一 generation，且说明哪一代 checker验证哪一代 ledger。任何例外都必须机械可判，不能使用“本次是 bootstrap，所以跳过”的自评条件。补正向 bootstrap fixture与“新报告导致下一代 ledger 失效”的负向 fixture，并确保阶段 0、后续 docs_commit与 phase_advance 三条路径都可终止。

## 主观建议

未提出额外主观建议。本轮只保留会改变正式提交判断或下一步执行的事实性 major；没有把可选措辞、代码风格或首轮技术设计重新包装成发现。

## 已确认无阻断的合并态结论

- Spec 是唯一行为 oracle，状态 `FINALIZED`；Acceptance 是验收 oracle，状态 `FINALIZED_ACCEPTANCE_ORACLE`；Architecture 仍是非规范提案且尚未获用户接受；Research 只承载证据；Implementation 只承载易变实施状态。权威角色本身没有互相覆盖。
- Architecture 的待用户裁决面只包含 `D-ARCH` 与条件性的 `D-MIGRATION`。`ADR-BRIDGE-02`～`06` 均被归类为已决 Spec 输入／历史承载记录，没有隐藏附加投票项。
- reasoning carrier wire compatibility 与一 item 一 thinking block／encrypted-only no-loss 已分离；server-tool no-revive、四项低概率扩展的冻结基础行为、block-level buffering、route precedence、unknown fail closed、post-commit partial failure及普通两级内存预算均一致。
- Foundations integration `6a00f6f…` 的状态准确：clean、三提交线性组合、范围内 review／verification 已通过、尚未进入 main、不得外推为完整 bridge `PASS`。
- 产品 verdict 继续为 `UNVERIFIED`。本轮没有执行完整 Acceptance required gates，也没有把文档评审或 foundations verification 冒充产品符合性证据。
- Docs 提交完成后的产品回放顺序清晰：逐片回放现有 integration 三提交并逐片执行 main-side gate；归档对应 reviewed feature HEAD；三片全部进入 main且全绿后才清理共享 integration 载体，并再做 merged-state code review。该主路径不应被文档重组阶段 0／1提前展开或重开 bridge 合同。

## 最终结论

当前为 **0 blocker、3 major、0 minor**。7 份文档的核心产品合同与 integration 事实已经对齐，但 current review provenance、Implementation 的 Plan 下一动作和文档重组阶段 0 bootstrap仍不自洽，因此暂不能作为一个正式 docs 提交。关闭上述 3 条 major并对新 bytes定向复评至 0 blocker／0 major后，应明确判定 7 份文档可以作为一个正式 docs 提交；随后才按 Implementation 记录的顺序逐片回放 foundations integration。
