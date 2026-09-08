# `docs/tmp/260807-*` 正式文档归纳矩阵

## 用途与边界

本矩阵只读归纳 `main@ed77c9d191df81c451c25161420515cca52ce6a4` 工作树中 2026-08-07 的临时报告，以及与本轮下一动作直接相关的既有代码集成审计和后续报告族。它用于修复 `docs/agents/documentation-restructure/plan.md` 第 2.5 节“及时归纳”缺少机械截止点的问题，不重新评审报告结论，不替代报告原文，也不修改任何正式文档。

“正式落点”表示结论最终应由哪个长期或易变状态载体承接；本矩阵本身仍是 `docs/tmp/` 临时证据，不是新的状态真相源。若报告同时改变正文合同和易变状态，两类落点都必须更新，不能以“正文已经改过”替代 verdict、下一动作或 gate 的状态归纳。

## 覆盖状态口径

- **已归纳**：报告中会改变当前合同、实现状态、验收 verdict、下一动作或 gate 的结论，已经进入对应正式 owner；读者无需依赖临时报告即可知道当前真相和下一动作。
- **部分归纳**：正文修订已经进入正式文档，但最新独立 verdict、内容身份绑定、未关闭项、下一动作或 gate 尚未进入正式状态载体。受影响动作仍须阻断。
- **未归纳**：报告的 load-bearing 结论尚未进入正式 owner，或正式 owner 仍明确传播被该报告推翻的旧状态。
- **待产生**：触发条件尚未发生，报告尚不存在。触发后必须先登记并按本矩阵的截止动作归纳，不能用预先写好的流程描述冒充运行结果。

## 及时归纳的统一截止规则

任何新报告只要改变当前合同、实现状态、验收 verdict、下一动作或评审 gate，就必须在以下三个时点中**最早到达者之前**完成归纳：①采用该结论作出决定之前；②开始受该结论影响的下一相关切片或回放之前；③提交受该结论影响的正式文档或代码之前。

“部分覆盖／待覆盖”不是通行证。它必须同时列出未覆盖结论、正式 owner 和明确阻断动作；在状态转为“已覆盖”前，只阻断其影响范围内的动作，不无差别阻断无关工作。报告影响规范输入内容身份、finalized 状态或 Acceptance 绑定时，阶段 gate 还必须校验当前 SHA-256 与绑定关系，不能只验证路径存在。

## 今日报告归纳矩阵

| 临时报告 | 关键结论，仅转述原报告 | 正式落点 | 当前归纳状态 | 当前缺口 | 必须在何动作前归纳 |
|---|---|---|---|---|---|
| `docs/tmp/260807-audit-doc-links.md` | 对 6 份 bridge 文档与文档重组 Plan 的 current worktree bytes 审计相对 Markdown 文件链接；55 条引用、29 个唯一目标，断链与错误 fragment 均为 0，blocker 0、major 0，可进入最终 docs 提交。结论绑定报告列出的 7 个 source SHA-256；任一 source 变化后必须重跑。 | `docs/agents/anthropic-responses-bridge/implementation.md` 的 docs 提交 gate、已完成审计与失效条件；若由文档重组计划消费，则 `docs/agents/documentation-restructure/plan.md` 只承接可重跑 gate 规则，不复制本次点时计数。 | **未归纳**。正式状态源尚未登记本报告；Implementation 仍保留旧 docs 同步路径，且 Implementation R4 的 Acceptance 内容身份 major 仍独立阻断 docs 提交。本报告的链接 0／0不能关闭该 major。 | 缺正式状态源对本次链接审计 verdict、绑定 source hashes 和“任一 source 变化即失效”的记录；不得把 target-only 语料的 0 fragment 误写成 current 文档已经实测 fragment coverage。 | **在最终提交本批 bridge docs 之前。** 若任一被审计 source 在提交前变化，须先在新 bytes 上重跑并归纳新结果；在 Plan 中把本次点时结果提升为通用 checker 证据之前也须先区分规则与运行快照。 |
| `docs/tmp/260807-audit-integration-commits.md` | 对 `integrate/260806-bridge-foundations@6a00f6f…` 做只读回放预检：base 后恰有三个线性非 merge commits，source feature refs 未漂移，第三提交包含 amend 修复，worktree clean；blocker 0、major 0，可按 `9e5f874… → cae83f4… → 6a00f6f…` 逐个回放。报告冻结 commit parent／subject／paths、stable patch-id、diff SHA-256、逐片 future-main blob oracle 与 archive targets，但未重做代码 review或运行候选测试。 | `docs/agents/anthropic-responses-bridge/implementation.md` 的 current integration 身份、首次回放前 gate、逐片累计 blob oracle、archive target和 shared integration 清理条件。精确 patch／blob 身份若不适合正文长表，也必须进入该 topic 的正式可复现验证资产，不能只留在 `docs/tmp/`。 | **部分归纳**。Implementation 已承载三提交链、顺序、reviewed feature HEAD、逐片 main-side gate、archive／cleanup边界和产品 `UNVERIFIED`；但尚未登记本日预检 0／0、stable patch／diff 身份、future-main 累计 blob oracle及“相关 path 变化即停止回放”的新操作门。 | 缺最新预检 verdict 与精确身份门的正式承载；不得把“可逐个回放”改写成“已进入 main”，也不得用本报告替代每片 future-main gate。 | **在首次回放 `9e5f874…` 之前；在任一 cherry-pick 后创建 archive ref 或清理 feature 载体之前；在 source integration ref、reviewed feature refs 或相关 paths 发生变化后继续回放之前。** |
| `docs/tmp/260807-review-architecture-decision-matrix.md` | Architecture 独立终审为 blocker 0、major 0，可进入下一阶段；用户可在完整阅读五份文档后分别裁决 `D-ARCH` 与 `D-MIGRATION`；评审通过不替代用户接受。 | `docs/agents/anthropic-responses-bridge/architecture.md` 的状态头与裁决就绪状态；`docs/agents/anthropic-responses-bridge/README.md` 的阅读导航、唯一待决集合与用户裁决入口；`docs/agents/anthropic-responses-bridge/implementation.md` 的文档状态汇总和下一动作。用户裁决完成后另进入正式 ADR 或等价决策记录。 | **部分归纳**。Architecture 正文已经形成唯一 `D-ARCH`／`D-MIGRATION` 矩阵并关闭原两项 major，但状态头仍写“仍须独立复评”；README 仍传播旧 Architecture 状态、旧章节名和旧 Acceptance 状态；Implementation 仍写裁决材料在修订中。 | 缺最新 0／0 verdict、裁决就绪状态、README 导航同步和 Implementation 状态同步；尚无用户接受记录，不能把“终审通过”归纳成 accepted ADR。 | **在邀请或接受用户对 `D-ARCH`／`D-MIGRATION` 作裁决之前；在提交本批 bridge docs 之前；在任何依赖方案 B／M2 的实现规划或执行之前。** |
| `docs/tmp/260807-review-bridge-implementation-r4.md` | R3 的完整 integration 遗漏已关闭，但 current Architecture 已晚于 Acceptance R6 绑定快照发生变化；Implementation 无条件把旧 R6 verdict汇总为 current `FINALIZED_ACCEPTANCE_ORACLE`，故仍有 1 major，当前不可提交。产品继续为 `UNVERIFIED`。 | `docs/agents/anthropic-responses-bridge/acceptance.md` 的 current Architecture 内容身份、七域 policy manifest 重绑和新的独立复评记录；`docs/agents/anthropic-responses-bridge/implementation.md` 的 Acceptance 状态、文档复评表、下一步和提交门；必要时同步 `README.md` 的 Acceptance 导航状态。 | **未归纳**。Implementation 仍把 Acceptance R6 旧快照直接写成 current oracle 已定稿，并把 docs 提交列为下一步；Acceptance 仍绑定旧 Architecture SHA-256 `7bd98a…`，而 current Architecture 为报告核验的 `6de919…`。 | 缺 current Architecture 对 Acceptance 的定向重绑／内容复核、新的独立 0／0 verdict，以及 Implementation 对“R6 只适用于旧快照”的如实状态记录。不得只替换 hash沿用旧 verdict。 | **在提交任何 bridge docs 之前；在把 Acceptance 作为文档重组阶段 0／1 的 normative input 冻结之前；在回放 `9e5f874…` 或任何后续产品提交之前；在宣称 current Acceptance oracle 已定稿之前。** |
| `docs/tmp/260807-review-research-external-change.md` | Research 的 R3 后变化仅为已授权的 Anthropic `/v1/messages` bridge route scope 修复；carrier、reasoning cardinality、容量政策、来源／目标裁决分层及 `file:line` 修复保持成立。Verdict 为 blocker 0、major 0，current Research 可提交，不外推为产品通过。 | `docs/agents/anthropic-responses-bridge/research.md` 承载长期研究结论与 route scope；`docs/agents/anthropic-responses-bridge/implementation.md` 的文档状态汇总承载 latest review verdict；`README.md` 只需保持 Research 的证据角色，不复制长结论。 | **部分归纳**。Route scope 与处置记录已进入 current Research 正文，正文语义已吸收；但 Implementation 仍只记录 2026-08-06 Research R3，没有登记本报告对外部变化的 0／0复核和 current 可提交结论。 | 缺正式状态源对 latest Research verdict、current 内容身份和“仅 Research 可提交、不代表产品 PASS”的归纳。 | **在提交 current `research.md` 之前；在把 Research 当作 current 已复核设计／实施输入之前；最迟与本批 bridge docs 状态同步同一截止点完成。** |
| `docs/tmp/260807-review-doc-migration-plan-r4.md` | Plan R4 为 blocker 0、major 2，当前计划不可提交执行。两项 major 是：`normative_inputs` 只记录路径、未冻结内容 SHA-256／Acceptance 对 Spec 的绑定与 finalized 状态；“及时归纳”没有最迟触发点、阻断动作和可执行 checker。 | `docs/agents/documentation-restructure/plan.md` 第 2.5 节、阶段 0 manifest／checker／fixtures、阶段 1 normative-input gate、实施 kick-off、验收与 major 处置表。 | **未归纳**。Plan 仍声明既有 R3 0／0且“可执行”，规范输入仍只冻结路径与优先级；第 2.5 节仍允许“待覆盖”但没有本矩阵所列最早截止规则和受影响动作阻断门。 | 缺规范输入的内容 SHA-256、finalized 状态、Acceptance→Spec 绑定一致性及阶段 0／1 双重 gate；缺报告登记、部分覆盖剩余项、截止动作与正反 fixtures 的机械规则。 | **在提交或执行文档重组计划之前；在阶段 0 生成或提交 manifest／checker 之前；在阶段 1 消费 bridge Spec／Acceptance 之前。** 本矩阵应作为修订输入，但其内容必须进入 Plan 正式条款与可执行验证资产后才算归纳完成。 |

## 代码集成审计与后续报告族

| 报告或报告族 | 关键结论／预期职责 | 正式落点 | 当前归纳状态 | 必须在何动作前归纳 |
|---|---|---|---|---|
| `docs/tmp/260806-review-code-bridge-foundations-r2.md` 与 `docs/tmp/260806-verify-bridge-foundations-r2.md` | 绑定 `integrate/260806-bridge-foundations@6a00f6f…`；代码定向复评为 blocker 0、major 0，可按 `9e5f874… → cae83f4… → 6a00f6f…` 回放；独立复验在追加范围内 `PASS`，但 route、transport、response assembler、sink／frontier、retry、History、approval、hooks、tokenization、cancel、shutdown、backpressure 与 quota 仍未验证，不能外推为完整产品 PASS。 | `docs/agents/anthropic-responses-bridge/implementation.md` 的 current integration 状态、三提交链、逐片 main-side gate、清理门和产品 `UNVERIFIED` 边界。 | **已归纳**。Implementation 已记录 amended tip、三个提交、两份报告的范围、逐片回放顺序、main-side gate、feature／shared integration 清理条件和产品状态边界。 | 既有报告的归纳截止已经满足。后续执行前仍须重新 gate current refs／worktrees；若内容身份或集成 tip 漂移，必须产生新报告并按下列报告族重新归纳，不能沿用本行。 |
| 每片回放后的 main-side gate／审计报告族，当前尚未产生严格 `260807-*` 报告 | 分别记录 reasoning cardinality、session liveness、request converter 进入 current `main` 后的实际 commit、定向与交叠测试、全仓回归、Ruff、Pyright、前序 blob 未回退、archive ref 与 worktree 状态。报告必须区分“已回放且 main-side gate 通过”与 integration worktree 的旧 PASS。 | `docs/agents/anthropic-responses-bridge/implementation.md` 的总体进度、各切片 HEAD／gate、下一动作、archive／cleanup 状态和结构怪味登记。 | **待产生**。Implementation 目前只有执行计划，没有任何切片已经进入 `main` 的新事实。 | **每片报告必须在开始下一片回放之前归纳；在创建该片 archive ref、清理该片 feature worktree／branch或宣称该片进入 main之前归纳。** Request 片完成后，还须在清理 shared integration 载体之前完成三片状态合并归纳。 |
| 三片进入 `main` 后的最终 merged-state code review／独立 verification 报告族，当前尚未产生 | 对 current main 组合态重新审计 request decoder×reasoning cardinality／codec、liveness cleanup×未来 stream owner及 Spec／Acceptance 策略接缝；不得把 foundations 范围内 PASS 提升为完整 bridge PASS。若后续执行 Acceptance required gates，报告还须逐项记录 `PASS`／`BLOCKED`／`UNVERIFIED` 及证据边界。 | `docs/agents/anthropic-responses-bridge/implementation.md` 的最终组合状态、剩余未实现边界、下一切片与清理门；若 Acceptance 内容身份或产品 verdict 改变，则同步 `acceptance.md` 的执行记录或其指定正式结果载体，不能改写 oracle expected。 | **待产生**。当前 main 仍是 `ed77c9d…`，三片尚未回放；现有报告只覆盖 integration candidate 的 foundation 范围。 | **在清理 `integrate/260806-bridge-foundations` shared worktree／branch之前；在开始依赖组合态的下一实现切片之前；在执行或汇总完整 Acceptance 之前；尤其在把产品从 `UNVERIFIED` 升级为任何更强 verdict 之前。** |

## 依赖顺序与阻断关系

1. 先归纳 Architecture 终审：把 0／0和“仅 `D-ARCH`／`D-MIGRATION` 待用户裁决”同步到 Architecture 状态头、README 与 Implementation，但不得代替用户接受。
2. 再处理 Implementation R4 的 Acceptance 内容身份 major：对 current Architecture 做 Acceptance 定向重绑／内容复核并取得新的独立 verdict；在此之前 docs 提交与文档重组 normative-input 冻结均阻断。
3. 同批把 Research 外部变化复核归纳到 Implementation 状态汇总；Research 正文无需因本矩阵重复改写结论。
4. 把 docs 链接审计登记为点时提交 gate；只要 7 个 source 任一变化，就在新 bytes 上重跑，不能沿用当前 55／29／0 的快照结论。
5. 修订 Plan R4 两项 major：把规范输入内容身份门和本矩阵的最早截止规则落实到 Plan、manifest schema、checker 与双向 fixtures；完成定向复评前不得执行阶段 0／1。
6. Docs 正式状态收敛并提交后，先把 integration commits 预检的最新 verdict 与精确身份门归纳到 Implementation 或正式验证资产，再按既有 integration 链逐片回放。每片新报告先归纳到 Implementation，再进入下一片或清理该片载体；三片 merged-state 报告先归纳，再清理 shared integration 或推进 Acceptance。

## 清点说明

严格按 `docs/tmp/260807-*.md` 匹配并排除本矩阵自身，最终清点到上表“今日报告归纳矩阵”中的六份报告。初次文件索引与 `fd` 清单只看到四份，最终验收时又发现并行产生的 `260807-audit-doc-links.md` 与 `260807-audit-integration-commits.md`；本矩阵已读取并纳入二者，不能沿用早期四份快照。今日仍无 main-side 代码回放结果或三片进入 `main` 后的最终 merged-state 报告，因此本矩阵没有虚构其 verdict，只把触发条件、正式 owner 和最迟归纳动作登记为“待产生”。既有 foundations 代码审计／复验使用 `260806-` 文件名，因其直接决定今日后续回放与清理门，单独纳入“代码集成审计与后续报告族”。
