# Implementation living document current 定向独立评审

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/implementation.md`，内容身份 SHA-256 `052bda8eea562ffee40bb9106d999832c4c98149b5508b5bd7090ccf85a748e0`。本轮只消费旧 [living-plan 定向评审](260807-review-implementation-living-plan.md) 的 1 项 major、current [Spec](../agents/anthropic-responses-bridge/spec.md)、current [Acceptance](../agents/anthropic-responses-bridge/acceptance.md)、四个切片首轮代码评审，以及与 systemd 严重级别分歧和现服替代边界直接相关的只读报告；只检查 living document 规则、Spec 是否已恢复 `FINALIZED`、Acceptance current 绑定、四切片是否均已提交但首评各有 1 major且不可 squash、foundations 是否仍未进入 `main`、目标是否是替代当前现服，以及是否避免提前声称完成。未重审四个候选实现、Acceptance gate 内容、Architecture、文档重组 Plan 或完整 bridge 产品符合性。
- **总体 verdict**：**可进入下一阶段。** 本轮为 **0 blocker／0 major**。旧 living-plan major 已关闭；current Implementation 的事实边界和执行顺序足以继续使用。该结论只批准 Implementation 继续随代码、评审、回放、运行态和新发现动态更新，并可形成当前 checkpoint；**不要求也不授权将 Implementation 收口、定稿或转成只读历史文档**。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **证据基线**：每次有效 shell 调用均在同一调用内验证物理 root 与当前目录为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。Implementation、Spec 与 Acceptance 的 current SHA-256 分别为 `052bda8eea562ffee40bb9106d999832c4c98149b5508b5bd7090ccf85a748e0`、`5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` 与 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`；三者均用 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉复核一致。
- **双视角覆盖证据——机械核对**：完整通读 current Implementation、旧 living-plan 评审、current Spec 与 Acceptance；逐项对账 Implementation 的 living 规则、权威边界、评审语义、集成状态、四线状态表、文档复评剩余项、squash／归档策略、下一步与结尾状态摘要。完整读取四份首轮代码评审 `260807-review-code-nonstream-response.md`、`260807-review-code-stream-parser.md`、`260807-review-code-carrier-v2.md`、`260807-review-code-systemd-runtime.md`，并读取 `260807-systemd-socket-feasibility.md` 核对 `KillMode` 分歧。用 Git 注册 worktree 清单与逐 worktree 直接探针两种路径交叉核对四条开发线的 root、branch、HEAD、相对声明基线 ahead 数与 clean 状态；对三个 foundations commit 分别执行 main ancestry 检查；用 `ss` 与 `/proc` 交叉核对 current 4141 listener 的进程、命令、cwd 与 cgroup。扫描 `docs/tmp` 中 Acceptance READY 候选 hash `787b5c386dd6c623d66e47e2c26d2b84bb605db66dc0db97a6ee9dc1a2379afb`，未找到独立报告文件。
- **双视角覆盖证据——第一人称执行**：按“消费 current oracle 状态 → 修复四线首评 major并逐片复评 → 闭合 Acceptance 独立报告落盘门 → 完成 docs checkpoint → 回放 foundations 三片到 `main` → 消费已获 0／0 的新增切片 → 继续边界切片与 merged-state 验收”的顺序模拟执行。分别走过四个关键分支：任一切片先达到 0／0时是否可独立收敛；前三片达到 0／0但 foundations 尚未进入 `main` 时是否会错误抢跑；systemd 代码收敛时是否会误停止现服或争用 4141；Implementation 本轮取得 0／0时是否会被误解成计划收口或产品 `PASS`。各分支均有明确门和停止条件，无需执行者猜测状态。

## 事实性发现

未发现问题。

### 旧 major 关闭核对

旧 [living-plan 定向评审](260807-review-implementation-living-plan.md) 的唯一 major 是 Implementation 把 carrier 重裁前的 Spec `FINALIZED` 当作 current 事实，并在 current Spec 尚处于 `READY_FOR_TARGETED_REREVIEW` 时允许按 frozen Spec 推进。

该 major 已关闭：

1. `implementation.md:7,25,222` 已改为引用 carrier 双格式定向评审，明确 current Spec 已恢复 `FINALIZED@5e362822…`，且不得由 Implementation 自行改写双格式合同。
2. `spec.md:5` 明确状态为 `FINALIZED`；`docs/tmp/260807-review-spec-carrier-dual-format.md` 绑定本次双格式合同并给出 blocker 0、major 0、minor 0，明确允许恢复 `FINALIZED`。本轮没有沿用旧 Spec R3 verdict。
3. Implementation 同时传播了下游状态：Acceptance 已绑定 current Spec `5e362822…`、重做七域 policy 对账并恢复 `FINALIZED_ACCEPTANCE_ORACLE@224b020d…`；但 Implementation 没有把 Acceptance 自述的 0／0当成独立证据，而是把 READY 候选 hash 对应报告尚未落盘保留为 current 文档门。
4. 因此执行者现在可以按已冻结 Spec 继续实现，同时不会把 Acceptance 自述、旧 R7／R8或局部 integration `PASS`误当成 current 独立复评或产品符合性证据。

### Living document 与非收口语义

`implementation.md:5,8-9,192-209,222` 一致把本文定义为持续更新的 Implementation living document：代码事实、评审、回放、合并关系、运行态和新发现变化后都要先更新本文；单轮 `0 blocker／0 major` 只放行继续实施或形成 checkpoint，不等于 Implementation 已定稿、实施已完成或后续不再修改。下一步也明确写成 current snapshot 的执行顺序，而非一次性封存清单。

结论：本轮 0 major 后，Implementation **可以继续动态更新，不需收口**。后续新增或改写内容仍按其风险执行相称的定向复评；这不是对未来 bytes 的预先放行。

### Acceptance current 绑定

current Acceptance 的源文档状态与 Implementation 摘要一致：

- `acceptance.md:3-11,29,400,429` 绑定 current Spec `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，声明七域 policy manifest 已按双格式 carrier 合同重做，并恢复 `FINALIZED_ACCEPTANCE_ORACLE`。
- Acceptance 明确把候选产品及完整 bridge 保持为 `UNVERIFIED`，没有把 oracle 文档 0／0外推为产品 `PASS`。
- Acceptance 自述独立定向复评绑定 READY 候选 `787b5c386dd6c623d66e47e2c26d2b84bb605db66dc0db97a6ee9dc1a2379afb` 并为 0／0，但本轮在 `docs/tmp` 中没有找到承载该 hash 的独立报告文件。
- `implementation.md:7,12,25,191,204,222` 正确把这一差异表述为“内容重绑与状态写回已完成，但独立证据落盘门未闭合”，要求先让报告落盘并核对身份；它没有错误地把 Acceptance 降回未 finalized，也没有只采信源文档自述。

### 四个切片与 squash 边界

四个候选均已形成一个 clean、ahead 1 的提交，Implementation 中的 branch、HEAD、base 与首评 verdict 均与现场和报告一致：

| 切片 | 现场身份 | 首评结论 | Implementation 处置 |
|---|---|---|---|
| Non-stream response | `feat/responses-anthropic-nonstream@b5b82f87f17ce229e8ec85f29071f7ff6280fecf`，base `6a00f6f…`，ahead 1、clean | `0 blocker／1 major`；public Anthropic identity 与 upstream identity 未分离；明确不可 squash | 修 typed result与共享 public identity helper，新完整 HEAD复评至 0／0后独立收敛 |
| Stream parser | `feat/responses-stream-parser@af5956be47ecf222ecd25c044436a36656206bce`，base `6a00f6f…`，ahead 1、clean | `0 blocker／1 major／2 minor`；跨 block 类型 source-order／open-source API不足；明确不可 squash | 冻结 parser→sequencer typed contract并补有判别力的正反控制，新完整 HEAD复评至 0／0 |
| Reasoning carrier v2 | `feat/reasoning-carrier-v2@f19dc32b83f744f088191cf67c21c10b5aeb329c`，base `6a00f6f…`，ahead 1、clean | `0 blocker／1 major`；direct Messages final wire 未无条件 strip synthetic thinking；明确不可 squash | 在 final-wire 接缝统一 strip并保留真实 Anthropic signature，新完整 HEAD复评至 0／0 |
| systemd／cgroup runtime | `feat/systemd-cgroup-runtime@66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`，base `ed77c9d…`，ahead 1、clean | 代码／部署评审为 `0 blocker／1 major／2 minor`，状态目录 major；socket 可行性复核另为 `0 blocker／1 major／2 minor`，把 `KillMode=mixed` 判为 major；当前不可 squash | 至少关闭确定状态目录 major，并在 squash 前处置 `KillMode` 分歧、`fd 0`、`Type=exec`与运行态 gate，再评审新完整 HEAD |

`implementation.md:11,45-48,52-61,199-209,222` 没有把“已提交”“happy-path smoke”或“首轮 review 已完成”误写为切片实现完成。四线任一片只有在新完整 HEAD达到 0 blocker／0 major后才能分别 squash／归档；不等待其他三片，但也不允许把已确认 major降成“后续边界”。

### Foundations 与 main 边界

对 `9e5f874d5b547bd9d733b0ee134e165f818de205`、`cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`、`6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 分别执行 main ancestry 检查，三者均为 `NOT_ON_MAIN`。这与 `implementation.md:10-12,40-44,61,198-208,222` 一致：完整 integration 链已存在并有其绑定范围内的评审／复验，但仍须按现有三提交链逐片回放 current `main`，并执行 main-side gates。

前三个新增代码片以 foundations tip `6a00f6f…` 为 base，所以它们即使先修到 0／0，也只能先完成候选收敛；进入 `main` 前仍须等待 foundations 按序回放。Systemd 片基于 `ed77c9d…`，没有该 parent 依赖，但代码收敛不等于已部署或已获 cutover 授权。

### 现服替代目标与不提前声称

本轮动态探针仍观察到 `127.0.0.1:4141` 与 `[::1]:4141` 由同一 Bun PID `1271974` 监听；命令为 `/home/xp/.local/volta/tools/image/packages/bun/bin/bun run ./packages/cli/src/main.ts start --restart`，cwd 为 `/home/xp/src/copilot-api-js`，cgroup 为 `/init.scope`。该 PID 只是本轮瞬时快照，实际 cutover 前必须重取。

`implementation.md:12,205,220,222` 正确把未来目标写成由本项目 Python systemd runtime **受控替代**当前 `copilot-api-js` Bun 裸进程，而不是并行争用 4141；同时要求唯一 socket owner、旁路验收、SQLite 一致性备份、兼容矩阵、health、机械 rollback与实际 cutover前动态重取证据，并明确不得把 `cc-daemon` 纳入切换范围。

Implementation 没有提前声称以下任一状态：foundations 已进入 `main`；四个新增切片可 squash；systemd 已部署；4141 已切换；零停机或原子切换已成立；rollback 已验证；完整 bridge 已通过 Acceptance。`implementation.md:9-12,61,192-209,222` 对局部 review、integration `PASS`、Acceptance 自述与产品 `PASS` 的边界保持清晰。

## 主观建议

无。

## 最终结论

current `implementation.md@052bda8eea562ffee40bb9106d999832c4c98149b5508b5bd7090ccf85a748e0` 在本轮定向范围内为 **0 blocker、0 major、0 minor**。旧 living-plan major 已由 current carrier Spec 0／0定向评审和 `FINALIZED@5e362822…` 状态关闭；Acceptance current 绑定与独立报告未落盘的证据缺口被准确区分；四个切片均已提交但首评各有 1 major且不可 squash；foundations 三片仍未进入 `main`；未来 systemd runtime 的目标是受控替代当前 Bun 现服；文档没有提前声称代码、回放、部署、cutover或产品验收完成。

**Implementation 可继续动态更新并进入下一实施阶段，不需收口。** 后续事实或 bytes 变化仍须写回 living document并接受相称复评；本报告不预先覆盖未来内容身份。
