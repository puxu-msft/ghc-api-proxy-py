# Anthropic Responses Bridge Architecture merged-state M1 定向终审

- **评审范围**：稳定快照 `docs/agents/anthropic-responses-bridge/architecture.md`，SHA-256 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`。本轮只复核 merged-state M1 的 Architecture 部分：文档是否继续是尚未获用户接受的非规范提案；260807 裁决矩阵终审 0 blocker／0 major 的 current provenance 是否准确；当前唯一门是否确为用户从 `README.md` 开始完整阅读规定的五份文档，尤其完整阅读 Architecture 后分别裁决 `D-ARCH`／`D-MIGRATION`；状态同步是否改坏技术正文或裁决矩阵。不重做 Architecture 技术 R3，不评审候选代码或产品符合性，也不扩展到 merged-state 其他 major。
- **总体 verdict**：**可进入下一阶段；Architecture 可提交供用户完整阅读。** current 状态同步准确关闭 merged-state M1，未改变既有技术正文、已决 Spec 承载记录、唯一裁决矩阵或最终推荐。文档继续明确是“非规范架构提案，尚未获用户接受”；0／0 终审只证明材料具备用户裁决条件，不替代用户接受。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **提交判断**：**Architecture 在本轮指定范围内可以提交供用户阅读。** 提交不等于用户接受；下一门仍是用户按 `README.md` 的顺序完整阅读 `spec.md` → `research.md` → `architecture.md` → `acceptance.md` → `implementation.md`，尤其完整阅读 Architecture 后分别裁决 `D-ARCH` 与 `D-MIGRATION`。

## 双视角覆盖证据

### 机械核对

- 每次 shell 调用均在同一次调用内验证物理仓库根为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`，并断言 current Architecture SHA-256 为本报告绑定的 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`。
- 直接核验 `docs/tmp/260807-review-architecture-decision-matrix.md`，其 SHA-256 为 `6922a93038b9e80677c8d6482c7236ec729facff3d8b3b69d53397f193d17a93`；报告明确给出 blocker 0、major 0，并明确“独立终审通过不替代用户接受”。current Architecture 顶部准确引用该报告、日期与 0／0 verdict，没有引用旧轮次冒充 current provenance。
- 从 VS Code 本地 History 精确恢复裁决矩阵终审绑定的旧 Architecture 快照 `/home/xp/.vscode-server/data/User/History/75f0d34b/4QlM.md`，其 SHA-256 精确等于旧终审报告绑定的 `6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327`。对该旧快照与 current `c6088…` 快照执行全量字节差异，只有两处变化：顶部状态行从“仍须独立复评”更新为“裁决矩阵已于 260807 独立终审 0／0，当前唯一门为用户完整阅读并裁决”；评审问题处置表新增 merged-state M1 的已采纳记录。
- 对旧／新快照执行章节切片比较：从“提案结论与裁决边界”到“已决 Spec 输入与历史 ADR 承载记录”之前的技术正文逐字相同，SHA-256 均为 `238c34d5efcdc73f8df54448e1e75d2dac76347db2ecfbcea1d1cf69121ef328`；“已决 Spec 输入与历史 ADR 承载记录”至“评审问题处置表”之前逐字相同，SHA-256 均为 `28066a3a9734c8e31671e391e2c7f51ed5e981672ad12dd181212ae95bfa108b`；“唯一用户裁决矩阵”单独切片逐字相同，SHA-256 均为 `819271a8292a7379eaed005b38705cbc957ee16418335b6c9499baf54a39ea85`；“容量政策的当前边界”至文末逐字相同，SHA-256 均为 `b6a9442537a9b871283f2b2195d1be4792d59e35350bd36d2e792bfebd2eb8c3`。移除预期的顶部状态行与新增处置行后，旧／新其余全文完全相等。
- 枚举 current 唯一裁决矩阵的数据行，结果恰为 `D-ARCH`、`D-MIGRATION` 两行；旧 `ADR-BRIDGE-02`～`06` 继续位于“已决 Spec 输入与历史 ADR 承载记录（非待裁决）”，未因状态同步变成隐藏投票项。
- 扫描 current Architecture 的陈旧状态措辞，未发现“仍须独立复评”或 `READY_FOR_FINAL_REVIEW` 残留。文档继续明确“非规范架构提案，尚未获用户接受”，并声明独立终审、推荐、旧评审或实现进度均不能替代用户接受。
- 解析 Architecture 内部目录锚点及 README 指向 Architecture 的 heading fragments，全部可达。README 的五份文档阅读顺序精确为 `spec.md` → `research.md` → `architecture.md` → `acceptance.md` → `implementation.md`，并明确 Architecture 必须从头到尾完整阅读、两项裁决一一对应且接受其中一项不自动接受另一项。
- `git diff --check -- docs/agents/anthropic-responses-bridge/architecture.md` 通过，未发现 whitespace error。

### 第一人称执行模拟

- 以首次参与裁决的用户身份从 `README.md` 进入：先读取五类文档的权威边界，再按规定顺序完整阅读五份文档；到达 Architecture 时，顶部先告知“提案尚未获用户接受”，正文再要求完整阅读而不能只看目录、推荐或矩阵。该路径不会把独立终审误读成 accepted ADR。
- 以完成全文阅读、准备作答的用户身份执行：最终只需分别回答 `D-ARCH` 与 `D-MIGRATION`。选择 `D-ARCH=B` 时能看到 typed facts、single driver、protocol／transport 正交、完整 delivery chain、History projection ownership 五项不可拆分核心；`D-MIGRATION` 只有在目标 B 下才比较 M1／M2，选择或拒绝其中一项不会重开 Spec 已决行为。
- 以用户选择 A、C，或尚未接受 B 的分支执行：M2 推荐不会自动生效，文档要求按所选目标重新制定迁移决策；独立终审、推荐结论和开始实施均不能替用户作出任何一项选择。
- 以提交者身份执行：current 顶部已不再要求重复 Architecture 独立复评，而是准确把下一门指向用户完整阅读与裁决；同时文档身份仍保持非规范提案，因此“可提交供阅读”不会被误执行为“架构已接受”或“产品已通过”。

## 事实性发现

未发现问题。

## 主观建议

无。

## 结构怪味扫描

- **扫描范围**：`architecture.md:1-13` 的身份、provenance 与裁决门；`architecture.md:569-640` 的 `D-ARCH`／`D-MIGRATION` 矩阵、核心、迁移边界、route 前置门与退出条件；`architecture.md:642-658` 的评审处置记录；`architecture.md:660-674` 的容量边界与最终推荐。
- **判据**：重复或冲突的状态源、已决行为与待决提案混列、推荐冒充接受、迁移节奏反向偷渡目标架构、处置表与正文不一致、状态同步改写技术合同。
- **处置**：未发现新的结构怪味；本轮无需修订或登记 backlog。

## 最终结论

稳定快照 `architecture.md@c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d` 在 merged-state M1 Architecture 指定范围内为 **0 blocker、0 major、0 minor**。current provenance 准确，技术正文与唯一裁决矩阵未被状态同步改坏，Architecture **可以提交供用户从 README 开始完整阅读**。该结论不接受 `D-ARCH` 或 `D-MIGRATION`，不把提案升级为 ADR，也不构成候选实现或完整 bridge 的产品符合性证据。
