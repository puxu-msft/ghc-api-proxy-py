# Anthropic Responses bridge 实施状态独立复评 R2

## 评审结论

- **评审范围**：`docs/agents/anthropic-responses-bridge/implementation.md` 最新稳定内容，SHA-256 `ed4a00f9c01a47361bb2d71309a4049271a1220c34b637dfffe017465a8f6479`；Git 状态核验锚定 current `main` `ed77c9d191df81c451c25161420515cca52ce6a4`。重点核对 reasoning cardinality、session liveness、request converter、文档状态、下一步，以及 squash／archive／worktree 清理规则。
- **总体 verdict**：**修复 major 后可进入下一阶段**。核心候选 HEAD、评审 verdict、main 未集成状态、最新文档复评状态和 archive refs 均已对齐，但共享 integration worktree／branch 的逐片清理顺序仍可能在 request 组合提交进入 `main` 前移除其唯一组合载体。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **状态文档提交判断**：**尚不满足“0 major，状态文档可提交”门槛。** 收紧共享 integration 载体的清理条件后，可做同范围快速复评。
- **报告路径说明**：本报告按本轮用户明确指定的唯一路径写入 `docs/tmp/260806-review-bridge-implementation-r2.md`；这是对一般 `YYMMDD-` 命名合同的一次任务级路径裁决，不据此反推正式文档中的前瞻命名规则错误。

## 双视角覆盖证据

### 机械核对

- 每次 load-bearing shell 调用均在同一调用内打印并验证物理根 `/home/xp/src/ghc-api-proxy-py`、`pwd`、分支 `main`、完整 `HEAD`，并要求 `HEAD == refs/heads/main`。最终评审对象在写报告前再次核验为 SHA-256 `ed4a00f9c01a47361bb2d71309a4049271a1220c34b637dfffe017465a8f6479`。
- 直接核验 local refs：`archive/260806-anthropic-responses-reasoning` 精确指向 `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b`；`fix/reasoning-cardinality`、`feat/session-liveness`、`integrate/260806-session-liveness`、`feat/anthropic-responses-request` 分别精确指向文档声明的 `b876e62…`、`f27a8c0…`、`8e9aef6…`、`fdd2f75…`，且四个 HEAD 均未进入 current `main`。
- 分别核验 reasoning-cardinality、liveness、liveness integration 与 request worktree 的 branch／HEAD／clean 状态。Liveness reviewed candidate 相对旧 anchor 的 binary diff SHA-256 与 integration commit 相对 current main 的 binary diff SHA-256 同为 `7d06bdc27f9f45258ea9a739c7d2f2461c9e2a31d440738b0130cbdbd3445587`。
- 对账 `260806-review-code-reasoning-cardinality.md`、`260806-review-code-liveness-r3.md`、`260806-review-code-request-r3.md`：三者均绑定文档所列最新 reviewed HEAD，均为 blocker 0、major 0、明确可 squash。父提交 `028f1f2…` 的 request 行为 PASS 没有被冒充成 `fdd2f75…` 的放行证据。
- 读取两个候选 tree 中的 `responses_reasoning.py`：`b876e62…` 明确返回 `list[AnthropicThinkingBlock] | None` 并 `return blocks`；`fdd2f75…` 新增 `AnthropicThinkingDecode`，但保留旧 forward 形状。文档要求在新基线上语义合成而非整文件覆盖，事实依据成立。
- 对账 Spec R3、Architecture R3、Acceptance R4、Research R3 与文档重组 Plan R3。Spec／Architecture 为 0／0；Acceptance R4 为 blocker 0、major 2、不可定稿且产品仍为 `UNVERIFIED`；Research R3 与 Plan R3 均为 0／0。实施文档转述准确。
- 扫描实施文档全部 Markdown 相对链接，均可解析到现存文件。

### 第一人称执行模拟

- 按“修复 Acceptance R4 → 完成本次 R2 → 形成 docs 提交边界 → cardinality → liveness → request → 回放 main”执行，能够得到唯一组合顺序；不会把“可 squash”误读为“已进入 main”，也不会用 request 分支整文件覆盖 cardinality list API。
- 以 reasoning 集成者身份执行：先保留 fixed carrier／逐 block reverse，再引入 per-item list cardinality与 encrypted-only no-loss；当前文档没有重新采纳已被裁决否定的跨 item 聚合。
- 以 liveness 集成者身份执行：R3 的 cancellation storm、primary／secondary failure 优先级、资源归零和 close 至多一次均被保留为组合 gate；`8e9aef6…` 只被当作已对账净补丁来源，没有被误写成 main 状态。
- 以 request 集成者身份执行：先保留 cardinality blobs，再叠加 Node-compatible decode／malformed classification和 converter调用；server-tool no-revive 裁决继续保持 reject，没有因旧 verifier F1 恢复半支持。
- 以归档执行者身份逐条走“main 侧每片验证通过后 archive 并清理”时，发现共享 integration worktree／branch 的清理 owner 不明确：该树承载三片组合链，而局部 liveness 段和“逐片清理”步骤允许在 request 组合提交进入 main 前移除整棵 integration 载体。该失败路径形成下述 major。

## 事实性发现

### [major] `docs/agents/anthropic-responses-bridge/implementation.md:80,152-154,169` — “逐片清理”没有区分 feature worktree 与共享 integration worktree，可能在 request 回放前删除后续组合提交载体

**问题**：文档要求在同一个干净 integration worktree 中依次形成 cardinality → liveness → request 三提交组合链，随后按同序回放 current `main`。但 liveness 局部段写成其 main 验证后即可清理 feature／integration worktree与活动分支；总规则又要求“每片”验证后移除 worktree／活动分支，下一步 7 同样写“逐片 archive 与清理”。这些文字没有把“每片可清理对应 feature worktree／branch”与“共享 integration worktree／branch 必须保留到三片全部进入 main”分开。

**证据或失败场景**：按第一人称顺序，三片已在 integration branch 上组合并通过 gate；cardinality 与 liveness 依次回放 main 后，各自 archive、main blob、测试和 clean 条件都可以成立。此时若照“逐片清理”移除共享 integration worktree及其活动 branch，尚未进入 main 的 request 组合提交会失去唯一明确 ref；`feat/anthropic-responses-request` 只保留基于旧 cardinality 形状的 reviewed source，不能替代已经语义合成的新基线提交。提交对象短期可能仍可从 reflog 恢复，但这不是允许的数据保全策略，会迫使重新合成并使后续 main 回放失去冻结来源。

**修复建议**：把清理规则拆成两个明确 owner：

1. 每片 main-side gate 通过后，可立即创建该片 reviewed feature HEAD 的 immutable archive ref，并在对应 feature worktree clean 时移除该 feature worktree／branch。
2. 共享 integration worktree／branch 只有在 cardinality、liveness、request 三个组合提交均已按序进入 current `main`，三片 main-side gate 均通过，且 integration HEAD／提交清单已记录后，才允许移除。局部 liveness 段不得提前授权清理共享 integration 载体。

同时将“对应 squash 语义”对 integration branch 明确为“三片完整组合语义”，避免执行者把单片已进入 main 当作整棵 integration branch 可删的充分条件。

## 已核验且未形成 blocker／major 的项目

- **Reasoning cardinality**：候选 `b876e62…`、0／0 代码评审、clean worktree、未进入 main、未来 archive ref 目标均准确。
- **Session liveness**：reviewed `f27a8c0…`、integration `8e9aef6…`、R3 0／0、净补丁相等、未进入 main 均准确；缺陷只在共享 integration 载体的清理时点，不在 liveness 实现状态。
- **Request converter**：latest reviewed HEAD `fdd2f75…`、R3 0／0、父提交行为 PASS 的证据边界、共享 reasoning 文件语义合成要求均准确。
- **文档状态**：Spec／Architecture／Research 可定稿，Plan 可执行；Acceptance R4 为 0 blocker／2 major且不可定稿；bridge 产品保持 `UNVERIFIED`。没有把正文修订冒充产品 PASS。
- **下一步主序**：Acceptance 修复与 docs 提交边界优先，随后 cardinality → liveness → request 组合与 main-side gate，最后 merged-state review／Acceptance 执行，主序正确。
- **Archive refs**：archive 精确指向最终 reviewed pre-squash HEAD、先创建 archive 再移除 feature ref、archive 不代表可部署 main、不得 force-update，这些规则正确。

## 主观建议

无。本轮发现可由文档执行顺序与 Git refs／worktrees直接裁定。

## 最终裁决

当前实施文档已关闭首轮 4 项 major与临时结论归纳评审 5 项 major，并准确归纳 reasoning cardinality、liveness、request 和最新文档复评状态；核心集成顺序与候选证据均可信。但共享 integration worktree／branch 的清理时点仍存在 1 项 major：按现有逐片规则执行可能在 request 组合提交回放 main 前移除其冻结载体。

**最终为 blocker 0、major 1、minor 0；状态文档暂不可按“0 major”门槛提交。** 收紧共享 integration 载体的清理条件后，可做定向快速复评；无需重开三个代码切片的已完成评审。
