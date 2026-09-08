# 文档重组计划独立终审 R6

## 评审摘要

- **评审范围**：稳定快照 `docs/agents/documentation-restructure/plan.md`，SHA-256 `53f7a02c936801e5f68fb67701449521941f2599c1d0092a8cf11eea1a6190ad`，分支 `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`。本轮只复核 R4 的两项 major：bridge 规范输入的内容身份、Acceptance → Spec 关系与 finalized 状态是否机械绑定；`docs/tmp` 归纳 deadline 是否覆盖 `docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup`、`user_ruling`，且 `pending`／`partial` 不能通行、临时材料不能成为永久权威。同时回归确认 42 项 source owner、required-output producer 与 literal pathspec 契约未破坏；未重新评审其他计划内容或 42 份源文档正文。
- **总体 verdict**：**可进入下一阶段；Plan 可提交执行。** R4 的两项 major 均已机械关闭，定向回归未发现 blocker、major 或 minor。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：每次 shell 调用均在同一调用开头验证物理根目录、`main@ed77c9d191df81c451c25161420515cca52ce6a4` 与 Plan SHA-256 精确相等。用 shell `sha256sum` 与 Python `hashlib.sha256` 交叉复核 Plan、Spec、Acceptance；current Spec 为 `FINALIZED@a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，current Acceptance 为 `FINALIZED_ACCEPTANCE_ORACLE@31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091`，Acceptance 内嵌绑定同一 Spec SHA-256，`POLICY-MANIFEST-v1` 的 route／request／response／buffering／retry／lifecycle／limits 七域均为“一致”。逐项扫描 Plan 第 2.3、2.5、5.4、6.5 节、阶段 0、阶段 1、阶段 11、kick-off 与 R4 major 处置表；另以 Python `Path.rglob()`、`git ls-files` 与 Plan 表三种载体对账 42 项集合，三者双向相等。
- **双视角覆盖证据——第一人称执行模拟**：模拟阶段 0 建 manifest 后暂停，再在阶段 1 前分别发生 Spec bytes 漂移、Acceptance bytes 漂移、Acceptance → Spec hash 失配、Spec 状态退回非 finalized、Acceptance 状态退回非 finalized、只刷新 hash 而未重做七域对账，以及 Architecture 内容变化的路径；前六类均被计划要求的 identity gate 阻断，Architecture 变化不产生行为 expected。再模拟一份临时报告影响六类动作中的每一类，分别令其为 `covered`、`pending`、`partial`、漏登记、anchor 失效或正式落点仍位于 `docs/tmp/**`；只有相关结论完整 `covered` 且正式落点有效时可通行，无关 topic 的 pending 不产生 false-red。最后模拟临时示例矩阵被删除，checker 仍只依赖已提交 ledger 与正式落点，不把该临时文件当永久 schema 或 oracle。

## R4 major 复核

### 1. 规范输入内容身份与 Acceptance → Spec 关系

**结论：已关闭。**

- `plan.md:62-69` 精确冻结 Spec／Acceptance 的路径、规范角色、必需状态、内容 SHA-256、Acceptance → Spec 绑定与七域 `POLICY-MANIFEST-v1` 身份，并明确 Architecture 只是非规范参考。
- `plan.md:247,304,311` 要求 manifest 记录规范角色、状态、已接受内容 hash、被绑定输入与 policy reconciliation evidence；阶段 0 与阶段 1 使用同一 identity gate，并为 Spec 漂移、Acceptance 漂移、状态错误、绑定不一致、只刷新 hash 未重做对账和 Architecture 越权分别提供红色 fixture。
- `plan.md:315,361,643` 把该身份门接到阶段 0 验收、阶段 1 消费前和 kick-off；任一内容、状态、绑定或七域对账身份漂移都会 fail closed，恢复必须先做新规范对账、独立复评与独立验证资产提交。
- current 文件的独立现场对账为绿：Spec SHA-256 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`；Acceptance SHA-256 `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091`；状态分别为 `FINALIZED` 与 `FINALIZED_ACCEPTANCE_ORACLE`；Acceptance 绑定同一 Spec hash；七域全部一致。

### 2. `docs/tmp` 归纳 deadline 与非权威边界

**结论：已关闭。**

- `plan.md:79-81` 把每份报告和逐条 load-bearing 结论登记到机器可读 ledger，定义 `covered`／`partial`／`pending`，并把机械截止点绑定到最早相关依赖动作；六类动作 `docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup`、`user_ruling` 全部明确列出。
- `plan.md:81,289,312` 要求任何相关报告为 `partial`／`pending`、漏登记、正式 anchor 失效、覆盖不完整或正式落点仍指向 `docs/tmp/**` 时非零退出；只有完整 `covered` 可通行。无关 topic 的 pending 明确不得造成 false-red。
- `plan.md:35,79,82,305` 明确 `docs/tmp/**` 不进入新的规范引用链，ledger 只是机械索引而不承载结论，正式落点不得仍在 `docs/tmp/**`；`docs/tmp/260807-tmp-distillation-matrix.md` 仅为一次性迁移输入，不是永久 schema、运行时 oracle 或 checker 依赖，阶段 0 必须从实际报告集合和正式 owner 重建 ledger。
- `plan.md:312,315,365,558,643` 把正反 fixtures、阶段 0 验收、阶段 1 提交／推进、合并态六类动作和 kick-off 接到同一 action-scoped gate；因此“只登记 pending／partial 便继续”和“临时报告继续存在才可运行”两条绕行路径均被关闭。

## 42 项契约回归

| 核对项 | 结论 | 独立证据 |
|---|---|---|
| 42 个迁移源集合 | **保持** | `Path.rglob()`、`git ls-files` 与 Plan 第 5.4 节均得到 42 项，集合双向相等。 |
| source owner／destination | **保持** | 42 个 source 与 42 个 canonical destination 分别唯一；每项 source 与映射左端一致，所有 `extract phase ≤ final move phase`。 |
| required-output producer | **保持** | `plan.md:247,304,310,315` 继续要求第 5.1～5.3 节全部产物进入 `required_outputs`，每个输出恰有一个 producer、完整 source inputs，并在 producer 阶段 literal pathspec 中出现；漏产物、重复 producer、晚生产和漏 pathspec 均有红色 fixture。 |
| 三份阶段 1 spec | **保持** | `plan.md:329-337` 的三条 producer／source input／literal pathspec／final owner 四元组精确存在，producer 与 final owner 均为阶段 1，并明确禁止同一路径进入其他阶段 pathspec。 |
| staged path 边界 | **保持** | `plan.md:275-279,304,337,643` 继续要求 staged paths 与阶段 pathspec 精确相等，规范输入不进入阶段 1 staged path，`docs/tmp/**` 与既有脏项被排除。 |

## 事实性发现

**未发现问题。** R4 的两项 major 已关闭，原 42 项 owner／producer／pathspec 契约未退化。

## 主观建议

无。

## 结构怪味复核

- 扫描范围：`plan.md:35,60-82,198-252,284-315,329-367,548-563,643-660`，判据包括路径身份冒充内容身份、规范层级倒置、不可执行的时间词、自报状态门、临时证据升级为永久权威、producer／owner 重复和 pathspec 漂移。
- **未发现新增结构怪味。** R4 的“路径身份冒充内容身份”已改为内容 hash＋状态＋绑定＋policy reconciliation gate；“不可执行的及时归纳”已改为六类动作的 action-scoped fail-closed gate。

## 结论

稳定快照 `53f7a02c936801e5f68fb67701449521941f2599c1d0092a8cf11eea1a6190ad` 的定向终审结果为 **0 blocker、0 major、0 minor**。规范输入身份与 Acceptance → Spec 层级已机械绑定；临时报告归纳 gate 覆盖六类依赖动作，`pending`／`partial` 不能通行，`docs/tmp` 不构成永久权威；42 项 source owner、required-output producer 与 literal pathspec 契约保持。**Plan 可提交执行。**
