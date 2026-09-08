# Implementation living plan 定向独立评审

- **评审范围**：current `docs/agents/anthropic-responses-bridge/implementation.md` 对 living plan 工作方式的修订，仅检查六项：Spec 是否先完整冻结；Implementation 是否随写随做并动态更新；`0 blocker／0 major` 是否只批准继续而不等于收口；四个并行 worktree 状态是否准确；foundations 是否仍待进入 `main`；是否避免提前声称实现。未重审各功能切片代码、Acceptance 内容、Architecture 决策或文档重组计划。
- **证据身份**：主仓物理 root `/home/xp/src/ghc-api-proxy-py`，分支 `main`，HEAD `ed77c9d191df81c451c25161420515cca52ce6a4`；current `implementation.md` SHA-256 `c0fd286f003a0a0f451f4d4230996a56884375269b2d36215d4316101daa7bbe`；current `spec.md` SHA-256 `0d81c21fb6efcc71e217b162418a89cf53cc7f392669e5b0b280651de512691e`。每次 shell 调用均在同一调用开头验证上述 root、branch 与 HEAD。
- **总体 verdict**：**修复 major 后可进入**。Living plan 的持续更新、checkpoint 与非收口语义本身清晰且可执行；但 current Spec 已因 2026-08-07 新 bytes 回到 `READY_FOR_TARGETED_REREVIEW`，Implementation 却仍把旧 R3 的 `FINALIZED` 当作 current 事实，并计划按“frozen Spec”推进四条开发线。该执行前置门未满足，当前不能给出 `0 major`。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据——机械核对**：完整通读 `implementation.md`；逐项对账 `implementation.md:5-12`、`:154-160`、`:192-204` 与 current `spec.md:5-8`、`:571`、`:575`、`:586-587`；用 `git worktree list --porcelain` 清点注册 worktree，并逐个直接核对四条开发线的物理 top-level、branch、HEAD、相对声明基线的 ahead commit 数与 short status；对 foundations 三个 commit 分别执行 main ancestry 检查；扫描 Implementation 中 `FINALIZED`、`frozen Spec`、`UNVERIFIED`、`0／0` 与实现完成措辞。
- **双视角覆盖证据——第一人称执行**：按“关闭文档门 → docs checkpoint → foundations 三片逐片回放与 main-side gate → 四线并行开发 → merged-state review／Acceptance”的顺序模拟执行；分别走了“Implementation 本轮复评为 0／0”“四线尚无候选提交”“前三线基于尚未进入 main 的 foundations tip”“完整 bridge 尚无 merged-state Acceptance 实证”四个分支。模拟在进入四线 TDD 前撞到 Spec 尚未恢复 `FINALIZED` 的前置门，证明不是单纯状态措辞问题。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:7,154,203` — Implementation 把 Spec 误记为已完整冻结，并遗漏 current Spec 定向复评门 — current `spec.md:5-7,571,575,586-587` 明确写明 2026-08-07 carrier 重裁产生的新内容仍为 `READY_FOR_TARGETED_REREVIEW`，旧 R3 的 `0 blocker／0 major` 只绑定旧快照，必须经过独立定向复评后才能恢复 `FINALIZED`。但 Implementation 第 7 行和第 154 行仍断言 current Spec 已通过 R3 且为 `FINALIZED`，第 194 行的“剩余 current 文档评审门”没有列入 Spec，第 203 行又允许四线按“frozen Spec”推进。执行者照计划走会在规范身份未获 current 独立放行时开始实现，违反“Spec 先完整冻结”的阶段门，并可能把尚未终审的 carrier 合同固化进四条并行实现 — 先完成 current Spec 新 bytes 的独立定向复评并恢复 `FINALIZED`；在此之前把 Implementation 中 current Spec 状态改为 `READY_FOR_TARGETED_REREVIEW`，将该复评置于 docs checkpoint 与四线 TDD 之前，并同步 Acceptance 的 Spec 内容身份／policy 对账门。不得沿用旧 R3 verdict。

其余五项检查通过：

- `implementation.md:5,8-9,160,166,192-194,204` 明确把本文定义为 living document，要求代码、评审、回放、合并和新发现先写回计划；`0／0` 只放行继续或形成 checkpoint，不表示收口，也不要求把计划“定稿”。
- 四条并行线的事实准确：non-stream response、stream parser、reasoning carrier v2 均位于声明的 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 基线，systemd／cgroup runtime 位于声明的 `ed77c9d191df81c451c25161420515cca52ce6a4` 基线；四者相对各自基线 ahead commit 数均为 0，且取证时 worktree 均 clean。该结论由注册 worktree 清单与逐 worktree 直接探针两种路径交叉核对。
- Foundations 的 `9e5f874d5b547bd9d733b0ee134e165f818de205`、`cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`、`6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 均不是 current `main` 的祖先；“仍待逐片回放 main”准确。
- `implementation.md:11,203-204` 把“worktree 已建立”“ahead=0”“integration PASS”与“实现完成／完整 bridge PASS”明确分开，未提前声称四线或完整产品已经实现。
- 一旦上述 Spec 身份 major 关闭，且修订后的 Implementation 独立复评达到 `0 blocker／0 major`，这套工作方式即可继续执行：该 `0／0` 只批准下一阶段与 checkpoint，不要求 Implementation “定稿”，计划应继续随实际代码、证据、评审、回并和新发现动态更新。

## 主观建议

未提出范围外建议。
