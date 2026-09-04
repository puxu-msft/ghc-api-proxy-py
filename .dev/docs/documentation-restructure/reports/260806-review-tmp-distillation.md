# `docs/tmp` 结论归纳独立评审

## 评审摘要

- **评审范围**：只读对账当前 `docs/tmp/` 报告与正式载体 `docs/agents/anthropic-responses-bridge/`、`docs/agents/documentation-restructure/plan.md`。重点覆盖 2026-08-06 前缀报告、server-tool 裁决、reasoning aggregation 裁决、reasoning／liveness／request 代码评审状态、Spec／Architecture／Acceptance／Research／Implementation 文档评审状态，以及文档重组计划复评。未重新调查代码事实或重跑各报告的底层探针。
- **总体 verdict**：**修复 major 后可进入下一阶段**。两项关键裁决与多数文档内容已经进入正式载体，但唯一实施状态真相源仍漏记三个已完成代码 gate，并继续发布陈旧的文档复评状态；未来临时报告命名规则也尚未形成可跨日期执行的正式合同。
- **blocker 数**：0。
- **major 数**：5。

## 双视角覆盖证据

### 机械核对

- 每次 shell 调用均在同一调用中验证物理根目录 `/home/xp/src/ghc-api-proxy-py`、分支 `main` 与 current HEAD；只读取报告、正式文档、Git 状态、标题、verdict、处置表与内容身份。
- 以 `docs/tmp/260806-*.md` 为本日主集合，另保留无日期前缀旧报告作为历史输入；逐类抽取裁决、最终复评、PASS／可 squash 与剩余 major，再对账正式文档的状态栏、当前进度表、处置表和下一动作。
- 对两项关键裁决分别检查了正式落点：server-tool no-revive 已进入 `spec.md`、`research.md`、`acceptance.md` 与 `implementation.md`；reasoning 的“wire codec 可保留、跨 item 聚合不可保留”已进入 `spec.md`、`architecture.md` 与 `research.md`。
- 对文档复评链按最终工作树而非报告快照复核：Acceptance R3 的 grammar／HEAD／容量摘要发现已写回 `acceptance.md`；Research R2 的 carrier／16 MiB 发现已写回 `research.md`；文档重组 R2 的三个派生 spec owner 发现已写回 `documentation-restructure/plan.md`。这些已关闭项不重复列为发现。

### 第一人称执行模拟

- 模拟接手者只读 `implementation.md` 决定下一步：会被要求重复已经完成的 liveness R3，仍把 request 父提交当 current candidate，并完全看不到 reasoning-cardinality 已获 0／0 放行；因此正式状态会直接导出错误执行顺序。
- 模拟文档收口执行者按“文档复评剩余项”派活：会重复派发已完成的 Spec R3、Architecture R3、Acceptance R3 和 Research R2，且漏掉 Acceptance／Research 修订后仍需 final rereview 的真实 gate。
- 模拟 2026-08-07 及以后新增临时报告：`implementation.md` 的固定 `260806-` 前缀会生成错误日期，而 `documentation-restructure/plan.md` 只排除 `docs/tmp/**` 进入迁移提交，没有给出“从现在起必须使用实际 `YYMMDD-` 前缀、旧无前缀文件可原样保留”的一般规则。

## 临时报告 → 正式文档映射

| 结论族 | 临时报告 | 正式目标 | 当前映射结果 |
|---|---|---|---|
| Server-tool no-revive | `260806-arbitrate-server-tool-contract.md`、`260806-verify-request-r2.md` | `spec.md`、`research.md`、`acceptance.md`、`implementation.md` | **已归纳**：reject 成立，旧 verifier F1 已撤销，不新增实现项 |
| Reasoning aggregation／cardinality | `260806-arbitrate-reasoning-aggregation.md`、`260806-review-code-reasoning-cardinality.md` | `spec.md`、`architecture.md`、`research.md`、`implementation.md` | **部分归纳**：合同与迁移方向已归纳；最新修复放行状态未进入 `implementation.md` |
| Session liveness 代码 gate | `260806-review-code-liveness-r2.md`、`260806-review-code-liveness-r3.md` | `implementation.md` | **未完成**：正式状态仍停在待 R3 |
| Request converter 代码／验收 gate | `260806-review-code-request-r2.md`、`260806-review-code-request-r3.md`、`260806-verify-request-r2.md` | `implementation.md` | **未完成**：正式状态仍停在旧 HEAD 与待 R2 |
| Bridge 文档评审 | `260806-review-bridge-{spec,architecture,acceptance,research}*.md`、`260806-review-bridge-implementation.md` | 各被评文档与 `implementation.md` | **部分归纳**：被评正文多已修；`implementation.md` 的汇总状态未同步 |
| 文档重组计划评审 | `review-doc-migration-plan.md`、`260806-review-doc-migration-plan-r2.md` | `documentation-restructure/plan.md` | **已归纳**：R2 剩余 major 已写回，正式状态正确标记为待独立复评 |
| 临时报告命名 | 本日 `260806-*` 报告与旧无前缀报告 | `documentation-restructure/plan.md`，并修正 `implementation.md` | **未完成**：缺跨日期的一般规则，且存在固定日期前缀措辞 |

## 事实性发现

### 1. [major] `docs/agents/anthropic-responses-bridge/implementation.md:15,35-37,154-163` — Reasoning cardinality 的仲裁后修复与 0／0 代码放行未进入正式实施状态

- **问题**：正式文档仍只记录 current main 上有损 forward aggregation 与“后续对账”，没有记录 `fix/reasoning-cardinality` 候选 `b876e626dda821b267535b0bcffc9d81ced12763` 已由 `260806-review-code-reasoning-cardinality.md` 判定 blocker 0、major 0、可 squash。进度表第 15 行还保留不可解析的错误 40 位 main token `ed77c9d191df81ac70d805b1da157b34d021d33d`。
- **失败场景**：接手者会把 reasoning cardinality 继续视为未形成候选，或只在 merged-state review 中“对账”，而不是先将已放行净改动按 current-main gate 集成；按错误 token 做 blob／祖先核验则直接失败。
- **修复建议**：目标文件为 `docs/agents/anthropic-responses-bridge/implementation.md`。将 reasoning 状态拆成“main 仍为旧聚合实现”和“`b876e626…` 已独立 0／0、待 current-main squash／集成验证”，记录报告绑定关系与下一动作，并把 main token统一修正为 `ed77c9d191df81c451c25161420515cca52ce6a4`。不得把候选已放行误写成已进入 main。

### 2. [major] `docs/agents/anthropic-responses-bridge/implementation.md:16,41-72,150-163` — Liveness 已完成 R3 并可 squash，正式文档仍要求重复 R3

- **问题**：`260806-review-code-liveness-r3.md` 已绑定 `f27a8c04cd3470bd50d7194a30371ca5404f727e`，给出 blocker 0、major 0、可 squash；正式进度表、切片状态、下一切片 kick-off 和结构怪味登记仍全部写“待 R3”。
- **失败场景**：执行者会重复派发同一 R3，而不进入 current-main 组合验证、squash／archive gate。正式文档也无法表达“评审已通过但尚未进入 main”这一关键中间态。
- **修复建议**：目标文件为 `docs/agents/anthropic-responses-bridge/implementation.md`。将 R3 标为已通过，明确候选尚未进入 main；下一动作改为在当时 current main 上核对净改动、运行组合 gate、集成后创建精确 archive ref，再清理活动分支／worktree。

### 3. [major] `docs/agents/anthropic-responses-bridge/implementation.md:17,75-114,150-163` — Request converter 的最新 HEAD、R3 放行与验收 PASS 均未进入正式状态

- **问题**：正式文档仍把 `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 写成 current candidate 并称待 R2。实际 R2 行为复验已在该 HEAD PASS，R2 代码评审留下的唯一 major 已由子提交修复，`260806-review-code-request-r3.md` 又在 `fdd2f75fcec11e592b04f2686c4664262052a964` 上给出 blocker 0、major 0、可 squash。
- **失败场景**：执行者会继续等待已经完成的 R2，或把父提交 PASS 与最新修复混为一谈；同时漏掉新 HEAD 已完成的独立 post-fix review，无法正确进入 current-main squash gate。
- **修复建议**：目标文件为 `docs/agents/anthropic-responses-bridge/implementation.md`。记录 `028f1f2…` 的“行为复验 PASS、代码 R2 留 1 major”、`fdd2f75…` 的修复与 R3 0／0 放行，并把下一动作改为按当时 current main 重放最终净改动、执行所需组合验证后 squash／archive。Server-tool 旧 F1 继续保持撤销，不重新列入待实现项。

### 4. [major] `docs/agents/anthropic-responses-bridge/implementation.md:116-126` — 文档评审汇总停留在 R2／首轮，已无法作为正式收敛状态入口

- **问题**：汇总表仍称 Spec 等待 R3、Architecture 等待 R3、Acceptance 等待 R3、Research 等待 R2；事实上 Spec R3 与 Architecture R3 均为 0 blocker／0 major、可定稿，Acceptance R3 的发现已经写回且正文现为 `READY_FOR_FINAL_REVIEW`，Research R2 的发现也已经写回但仍需修订后 final rereview。`260806-review-bridge-implementation.md` 自身的 4 条 major也尚未形成正式处置状态。
- **失败场景**：接手者会重复旧评审、遗漏真正需要的修订后 final review，并继续信任同一份已被证明陈旧的实施状态文档。内容修复与评审放行是两件事；正文已修不能自动升级为“已定稿”。
- **修复建议**：目标文件为 `docs/agents/anthropic-responses-bridge/implementation.md`。逐行更新最新报告、verdict、正文修订状态与下一 gate：Spec／Architecture 记 R3 0／0；Acceptance／Research 记“发现已写回、待修订后 final rereview”；本文先处置 `260806-review-bridge-implementation.md` 的 4 条 major，再做新的、带实际日期前缀的复评。不要把“可定稿”误写为架构 ADR 已被用户接受，也不要把 `READY_FOR_FINAL_REVIEW` 写成实现 PASS。

### 5. [major] `docs/agents/anthropic-responses-bridge/implementation.md:9,126`；`docs/agents/documentation-restructure/plan.md:35,74,260` — “从现在执行”的临时报告日期命名规则没有正式、跨日期落地

- **问题**：`implementation.md` 一处要求后续报告一律使用固定 `260806-` 前缀，另一处只笼统要求“日期前缀”；`documentation-restructure/plan.md` 仅规定 `docs/tmp/**` 不进入迁移提交，没有一般命名合同。旧无前缀报告可保留、未来报告必须按实际创建日命名这一裁决因此没有稳定正式载体。
- **失败场景**：2026-08-07 及以后照第一处执行会继续创建 `260806-*`，照第二处执行又需要自行猜日期格式；新的 topic 也不会自然继承 bridge 专属文档里的规则。
- **修复建议**：主要目标文件为 `docs/agents/documentation-restructure/plan.md`，增加仓库级前瞻规则：既有无前缀报告不强制重命名；从本裁决起新建 `docs/tmp/*.md` 必须使用实际创建日 `YYMMDD-` 前缀，同一对象复评追加 `-rN` 且不得覆盖旧轮次。同步把 `implementation.md:9` 的固定 `260806-` 改为该一般规则的引用或 `YYMMDD-` 表述。规则只约束未来文件，不要求批量改名历史报告。

## 主观建议

无。本轮只报告会导致正式状态、执行顺序或未来命名合同错误的 blocker／major；已归纳结论与纯风格问题均未列入。

## 最终结论

未发现 blocker。server-tool no-revive、reasoning wire／aggregation 边界、Acceptance R3 修订、Research R2 修订和文档重组 R2 修订已经进入对应正式正文。剩余 5 条 major 全部集中在“正式状态入口没有跟上已完成报告”与“未来日期命名规则没有形成一般合同”：`implementation.md` 需要同步 reasoning、liveness、request 和文档复评的最新状态，`documentation-restructure/plan.md` 需要承载从现在起执行的 `YYMMDD-` 命名规则。修订后应对两份正式文件做独立复评；在此之前，不应把 `implementation.md` 当作可信的下一步真相源。
