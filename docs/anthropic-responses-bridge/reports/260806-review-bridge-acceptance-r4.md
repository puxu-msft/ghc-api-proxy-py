# Anthropic Responses bridge acceptance 最终复评 R4

- **评审范围**：current `docs/agents/anthropic-responses-bridge/acceptance.md`，仅消费 R3 报告并复核其 `1 major + 2 minor` 的关闭情况，以及与最终状态调整直接相关的 current oracle hash、文档状态和候选实现状态；未重新展开首轮、R2 或候选实现的全量评审。
- **总体 verdict**：**修复 major 后可进入**。R3 的两个 minor 已关闭，但 R3 major 的 `ping` 边界仍允许首个完整 block 提交前出现 body event；此外 current Spec hash 已与 acceptance 绑定值不一致，按文档自身规则不得沿用旧 verdict。因此 oracle 文档当前不能定稿。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **状态结论**：oracle 文档**不可定稿**；候选实现仍为 **`UNVERIFIED`**。本轮未执行任何候选实现 gate，不得把文档修订状态解释为产品符合性证据。
- **证据基线**：每次 shell 调用均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。复评时 current `acceptance.md` SHA-256 为 `13e957eda762257832f804a7fdd41d19955d7c18cee59cacd3ed501803422424`，R3 报告 SHA-256 为 `a32ca0fad8af900e977f272819779752add9b322b38d8059a9a548c045799f50`。

## 双视角覆盖证据

- **机械核对**：逐项对账 R3 的 `R3-M1`、`R3-m1`、`R3-m2` 与 current acceptance 对应行；扫描并核对 `message_delta` 基数、`ping` 状态转移、正向 fixture 插入点、三类负向 fixture 与 oracle mutation；核验 current root／branch／HEAD、相关文件 SHA-256、Git index／worktree 状态及 `git diff --check`；把 acceptance 声明的 Spec／Architecture hash 与 current 文件重新计算值对账；核对 oracle 状态与候选实现 `UNVERIFIED` 状态是否被混写。
- **第一人称执行模拟**：按 current `CAL-04-GRAMMAR-v1` 作为测试作者实际生成 `message_start → ping → content_block_start → … → content_block_stop → message_delta → message_stop`，确认该 feed 会被表格及正向 fixture 文字判为合法，但在首个完整 block 提交前已产生 `ping` body event；另模拟零 content 的 `message_start → ping → message_delta → message_stop`，同样暴露 terminal batch 完成前插入 body event。随后按文档开头的 hash gate 执行最终定稿流程，current Spec hash 不匹配会机械触发“先重做逐项 policy 对账，不能沿用旧 verdict”，因此无法合法升级为定稿状态。

## R3 三项逐条结论

| R3 ID | R4 结论 | 复核依据 |
|---|---|---|
| `R3-M1` | **未关闭，仍为 major** | `acceptance.md:320-331` 已关闭 duplicate `message_delta`、pre-start `ping` 与 open-block `ping`，但 `acceptance.md:321,326,329` 仍明确允许紧随 `message_start` 的 `ping`。这发生在首个完整 block envelope 之前，与 `spec.md:263,505` 的零 body event 及首 batch 绑定合同冲突。 |
| `R3-m1` | **已关闭** | `acceptance.md:6` 声明 current `main` 为 `ed77c9d191df81c451c25161420515cca52ce6a4`；本轮每次 shell gate 的 root、branch、HEAD 均一致。 |
| `R3-m2` | **已关闭** | `acceptance.md:7` 已改为普通 per-request aggregate＋global reservation／backpressure，并明确 16 MiB 不是专门阈值；与 `REL-06` 的两级预算措辞一致。 |

## 事实性发现

### 1. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:321,326,329,397,407` — R3 的首个完整 block 前 `ping` 路径仍未关闭

**问题**：修订把 `ping` 限制为 `message_start` 后且没有 open block，却仍把“`message_start` 之后”列为正向合法插入点。`message_start` 本身不证明首个完整 block 已提交；冻结 Spec 要求首个完整 block 完成前零 `message_start`／零 body event，并要求 `message_start` 与首个完整 block envelope 进入同一串行 sink batch。当前 grammar 因此仍把 R3 指出的错误状态判绿。

**证据或失败场景**：`message_start → ping → content_block_start(index=0) → content_block_delta → content_block_stop → message_delta → message_stop` 满足 current 表的每次状态转移，也符合 `acceptance.md:329` 明示的正向插入点，但 `ping` 出现在首个完整 block envelope 之前，违反 `spec.md:263,505`。零 content 路径 `message_start → ping → message_delta → message_stop` 也会被 current 表接受，却把 `ping` 插入 Spec 要求一次性提交的完整 terminal batch。新增的 pre-start 与 open-block 负向 fixture 都抓不到这两个状态缝隙；把它们跑绿不能证明 R3 major 已关闭。

**修复建议**：为 `message_start` 后、首个 block 尚未完整关闭的阶段建立单独状态，该状态不得接受 `ping`；正向 `ping` 插入点至少要删除“紧随 `message_start` 后”，并按 sink batch 合同明确零 content terminal batch 内也不得插入。增加 `message_start → ping → first content_block_start` 与零 content `message_start → ping → message_delta` 两条单缺陷负向 fixture，再分别放宽对应转移，确认负向 fixture 因目标分支转绿、外层 mutation gate 因非法 feed 被接受而红。关闭后还应复跑无 `ping` 的五类正样本及首个 block 已完整关闭后的合法 `ping` 变体，防止 false-red。

### 2. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:7-8,11,380,384` — current oracle hash 已漂移，却仍宣称 R3 已关闭并进入最终评审状态

**问题**：`acceptance.md:7` 绑定的 Spec SHA-256 是 `6c36c7fbab001b776787d17845d5deee9a97da6e3de8dac635c33b0e52d0a04a`，current `spec.md` 实测为 `7e4389947998de7b0028d04eb23b6c4c053d4a35afbda9def67b967a76451699`；`acceptance.md:8` 绑定的 Architecture SHA-256 是 `74fef4675ebc61c89dbc31648acce6c21c8554649b8473ed20236c8a4e7e683c`，current 文件实测为 `ea6a3eca21c653096b17914d56497a5c6bbb6a8d1c237ebf2a055db24e31dc86`。Spec、Architecture 与 acceptance 均是 current `main@ed77…` 工作区中的 staged／modified 文档，不是读取了另一提交造成的路径误差。

**证据或失败场景**：`acceptance.md:7` 自己规定“Spec 内容 hash 改变后，本规范必须先重做逐项 policy 对账，不能沿用旧 verdict”。当前 hash 不相等时，执行者若依照该门就必须停止；但 `acceptance.md:11,380,384` 仍声称 R3 已关闭和 `READY_FOR_FINAL_REVIEW`，形成互斥状态。由于本轮按授权只窄复核 R3 三项，没有对 current Spec 全文重做 policy 对账，不能用本报告替代该缺失步骤，也不能宣布 oracle 定稿。

**修复建议**：先以 current Spec 内容重新完成逐项 policy 对账，确认所有 expected 与 current Spec 一致后，再更新 Spec hash；同步更新 Architecture hash并确认它仍只作参考。若尚未完成对账，状态应明确保持未就绪，而不是沿用 `READY_FOR_FINAL_REVIEW` 或“R3 已实证关闭”。hash 与内容对账必须在同一最终快照上取得，避免再次漂移。

## 主观建议

无。本轮结论均由 R3 原发现、冻结 Spec、current 文件内容及文档自带状态门机械裁定。

## 最终结论

R3 的 HEAD 陈旧与容量摘要冲突两个 minor 已关闭；duplicate `message_delta`、pre-start `ping` 与 open-block `ping` 的局部修订也已出现。但 `message_start` 后、首个完整 block 提交前的 `ping` 仍被正向 grammar 接受，故原 R3 major 尚未关闭。与此同时，current Spec hash 漂移触发 acceptance 自身的重新对账门，当前状态声明不能成立。

**本轮为 blocker 0、major 2，oracle 文档不可定稿。候选实现仍为 `UNVERIFIED`，且本轮没有取得任何可以升级该实现 verdict 的证据。**
