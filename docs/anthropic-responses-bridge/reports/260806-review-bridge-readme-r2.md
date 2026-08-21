# Anthropic Responses bridge README 定向复评 R2

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/README.md`，内容 SHA-256 为 `b7281a1fe078e2fcbf1d1f0402f00c0bb64f3386188d70cd813db127ef40b804`。仅复核阅读顺序与链接、真正待用户裁决是否仅为 ADR-BRIDGE-01／02／05 或等价表述、ADR-BRIDGE-03／04／06 是否保持已决且不要求重裁、`implementation.md` 是否仍能充当易变实施入口，以及 Spec／Acceptance／Architecture 的权威边界；不重做 bridge 技术设计、代码评审或 Acceptance gate。
- **总体 verdict**：**修复 major 后可进入。** README 的阅读顺序、链接和三类权威边界仍然成立，但 current Architecture 已明确把待裁决清单限定为 ADR-BRIDGE-01／02／05，而 README 末尾的“两项最小问题”并不与之等价；同时 README 指向的易变实施入口仍描述旧组合阶段，已落后于 current integration 代码状态。当前不能继续沿用上一轮“0 major、可作为用户入口”的 verdict。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **评审基线**：每次 shell 调用均在同一次调用内确认物理 root 为 `/home/xp/src/ghc-api-proxy-py`、当前分支为 `main`，且 `HEAD == ed77c9d191df81c451c25161420515cca52ce6a4`。current Architecture SHA-256 为 `7bd98a384ccb313f2e72a598dc876766a1044a9bfcef4685ba09412895ea7679`；current Spec SHA-256 为 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`。代码状态额外只读核对了 clean worktree `/home/xp/src/ghc-api-proxy-py-integrate-bridge` 的分支 `integrate/260806-bridge-foundations` 与 HEAD `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`；这不改变主树 gate，也不把 integration commit 冒充已进入 `main`。

## 双视角覆盖证据

### 机械核对

- 扫描 README 全部 Markdown 相对链接并解析到文件系统；`spec.md`、`research.md`、`architecture.md`、`acceptance.md`、`implementation.md` 的全部引用均存在。
- 逐项对账 README 的权威表述与源文档状态：Spec 自身为 `FINALIZED` 且是唯一行为 oracle；Acceptance 为 `READY_FOR_FINAL_REVIEW`、只把 Spec 转成 gate，产品 verdict 仍为 `UNVERIFIED`；Architecture 是待用户接受的非规范提案，不产生行为 expected。README 对这三者的边界没有倒置。
- 对账 Architecture current 分组：`architecture.md:507-530` 明确将 ADR-BRIDGE-03／04／06 归入“已决约束的架构承载记录”；`architecture.md:532-552` 明确把唯一待确认清单限定为 ADR-BRIDGE-01／02／05。再逐项比对 README 的“已裁决”“仍待接受”“最小问题”和“裁决后的记录要求”。
- 对账易变实施入口与代码状态：README 与 `implementation.md` 仍把主要下一动作写成组合 reasoning cardinality、liveness、request 三片；但 clean integration 分支 current HEAD `6a00f6f…` 已按序包含 `9e5f874…`、`cae83f4…`、`6a00f6f…` 三个组合提交。三片仍未进入 `main`，但“尚待建立组合链”已不是 current 状态。

### 第一人称执行模拟

- 模拟首次裁决用户按 README 的 Spec → Research → Architecture → Acceptance → Implementation 顺序完整阅读：顺序本身能够先建立行为合同，再理解证据、架构、验收和落地状态；链接均可到达，且不会把 Architecture 评审通过误认成用户已接受。
- 模拟用户只回答 README 最后两项问题并据 `README.md:271-273` 形成 ADR：用户会裁决方案 B／A／C 与迁移分阶段方式，却没有被要求逐项确认 ADR-BRIDGE-02 的 downstream framing／batch commit 内部选择和 ADR-BRIDGE-05 的 typed continuation action／ledger 接口保留边界；反而 `README.md:223,269` 会让用户把 post-commit 相关内容整体理解为无需再裁决。
- 模拟实施者在裁决后按 README 最后读取 `implementation.md` 并执行“下一动作”：文档仍指示先构建三片 integration 组合链，实际该 clean 组合链已经存在，执行者可能重复重放、另建载体或基于错误阶段安排评审与回并。README 只提醒 `implementation.md` 的跨文档状态转述滞后，没有提示其代码组合状态也已落后。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/README.md:248-273` — “真正需要裁决的最小问题”不再与 current Architecture 的唯一待决 ADR-BRIDGE-01／02／05 等价 — `architecture.md:532-552` 逐项保留 01“内部 canonical model”、02“下游 framing 与 commit 单元”、05“post-commit failure 的内部 continuation／ledger 边界”；README 却把裁决压成“目标架构组合”和“迁移落地边界”。其中 `README.md:223,269` 又把 post-commit 行为整体放入无需重裁区，导致用户可以按 README 完成裁决和 ADR 记录，却未明确接受或修改 ADR-02 与 ADR-05 的内部选择。行为层“无已证明 continuation 时 partial failure”确实已由 Spec 冻结，但这不能替代 Architecture 对 typed continuation action、ledger 接口和 framing／batch owner 的内部架构裁决 — 将末尾清单直接改为 ADR-BRIDGE-01／02／05 三项，或逐项给出严格等价标题与接受内容；把“是否分阶段迁移”降为 ADR-01 的实施约束或另列非裁决执行说明，并明确 03／04／06 仅作已决输入、不重新投票。

[major] `docs/agents/anthropic-responses-bridge/README.md:19,28-33,177-209` — README 宣称 `implementation.md` 是易变实施状态真相源并要求最后据此执行，但该入口已落后于 current integration 代码阶段 — `implementation.md:7-9` 仍描述只准备了旧 liveness integration 载体，并把三片组合列为后续动作；实际 clean `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 已按序包含 reasoning cardinality、session liveness、request converter 三个组合提交，变更覆盖对应三个实现文件和三组单测。虽然 `main` 仍为 `ed77c9d…`、三片仍未进入主线、完整 bridge 仍是 `UNVERIFIED`，但执行阶段已从“建立组合链”推进到“组合态证据／评审与后续 main 收敛”。按 README 当前入口执行会重复已经完成的组合工作，并误排下一 gate — 先同步 `implementation.md` 到 current integration HEAD、三提交顺序、已完成 gate 与真实下一动作；README 随后只保留稳定事实和“操作前重新 gate `implementation.md` current 内容”的链接，删除或缩减容易随代码推进失效的候选／组合细节。若状态源尚未同步，README 必须明确标出其代码状态也已知陈旧，不能继续称其 latest revision 为当前执行依据。

## 主观建议

未发现需要与上述事实性 major 分开记录的主观建议。
