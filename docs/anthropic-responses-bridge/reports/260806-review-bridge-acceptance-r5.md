# Anthropic Responses bridge acceptance 最终复评 R5

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/acceptance.md`，只复核 R4 报告的 2 个 major：首个完整 block／`message_start` batch 前零 `ping`／body event（含 zero-content terminal），以及 current Spec 七域逐节 policy 对账、同快照 hash 绑定与 Architecture 参考边界。未重新展开更早评审项，也未评审或执行候选产品实现。
- **总体 verdict**：**修复 major 后可进入**。R4-M1 的规范性 batch 禁止已经写入，但其指定负 fixture 与 oracle 放宽 mutation 不能按目标分支形成有效正样本对照；R4-M2 的 current Spec policy 对账与 Spec hash 已匹配，但 current Architecture hash 再次漂移，且 route manifest 仍引用已被 Architecture 修订掉的“待确认 ADR-BRIDGE-04”边界。Acceptance oracle 文档当前仍不可定稿。
- **blocker 数**：0。
- **major 数**：2。
- **状态结论**：Acceptance oracle 文档**不可定稿**；候选产品仍为 **`UNVERIFIED`**。本轮没有执行任何候选实现 gate，不得把文档复评结果解释为产品符合性证据。
- **证据基线**：每次 shell 调用均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。最终写入前，current `acceptance.md` SHA-256 为 `3acc1273625d13bfb265606cb88ea72ac666193f2ba208d8131fc2b34e03d357`，current Spec 为 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，current Architecture 为 `5f6b8bd2f24247ae762cf5e76c129171772b7857839bb5db4fa455cfc5245752`，R4 报告为 `6df6575996e00f669df515959de1061e37bdf5070ccc28f9dd3aca7f23b0aa6e`。文件哈希同时以 `sha256sum` 与 Python `hashlib.sha256` 两种独立方法交叉验证，结果一致。

## 双视角覆盖证据

- **机械核对**：完整通读 R4、current Acceptance、current Spec 与 current Architecture；逐项扫描 Acceptance 的 `POLICY-MANIFEST-v1` 七域映射、CAL-04 batch grammar、正负 fixture、oracle mutation、状态与处置表；核对 current Spec 各规范章节与双向字段矩阵，确认 route／request／response／buffering／retry／lifecycle／limits 的 expected 未被 Architecture 提案覆盖；两种方法重算四个证据文件 SHA-256；检查 Architecture index／worktree diff，确认 current 文件在 Acceptance 绑定快照后又修改了状态、unknown capability 边界与 ADR-BRIDGE-04 分类。
- **第一人称执行模拟**：以测试作者身份分别执行合法首 content batch、合法 zero-content terminal batch、首 block 接受后的合法 `ping` batch，以及两条指定负 fixture。模拟发现行为表能拒绝首 block 前与 zero-content terminal 内的 `ping`，但指定负 fixture 的第一批 `[message_start]` 会先因“内部瞬态不得结束 batch”失败；只放宽内部状态接受 `ping` 仍无法到达 `ping` 分支并转绿。随后按 Acceptance 的定稿流程读取同快照 hash gate：Spec hash 与七域政策可通过，但 Architecture 实测 hash 不等于绑定值，且 manifest 的 ADR-BRIDGE-04 描述不再对应 current Architecture，因此不能合法宣称 R4-M2 已按 current 同快照关闭。

## R4 两项逐条结论

| R4 ID | R5 结论 | 复核依据 |
|---|---|---|
| `R4-M1` | **未关闭，仍为 major** | `acceptance.md:334-346` 已正确冻结 batch 输入模型、首 content batch、zero-content terminal batch 与合法 `ping` 边界；但 `acceptance.md:351-353` 的两条负 fixture 把 `[message_start]` 单独放成第一批。该批在 mutation 前后都会先因 `message_started_but_no_completed_block`／`zero_content_terminal_batch` 不得结束 batch 而失败，仅放宽“接受 `ping`”不能使 fixture 因目标分支转绿，违反同段“必须因目标分支转绿、不能因 batch 格式或另一规则失败”的自有判据。 |
| `R4-M2` | **未关闭，仍为 major** | `acceptance.md:7,29-39` 绑定的 current Spec hash 与实测一致，七域 policy 映射也与 current Spec 一致；但 `acceptance.md:8` 的 Architecture hash 仍为 `ea6a…`，current 文件实测为 `5f6b…`。同时 `acceptance.md:33` 仍写“不采用 Architecture 中仍待确认的 ADR-BRIDGE-04 措辞”，而 current `architecture.md:507-515` 已把该项移出待确认列表并明确为 Spec 已决约束。故 `acceptance.md:11,29,404,421` 的“同一最终输入快照／R4-M2 已关闭”声明不成立。 |

## 事实性发现

### 1. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:351-353` — R4-M1 的目标 mutation 控制无法证明首批／zero-content `ping` 禁止由目标分支守住

**问题**：current grammar 已把输入单位改成串行 sink batch，并规定 `message_started_but_no_completed_block` 与 `zero_content_terminal_batch` 只能是同一 batch 内的瞬态、不得在 batch 边界停留。可是两条指定负 fixture 都把 `[message_start]` 单独作为第一批，再把 `[ping]` 放在第二批。测试在第一批结束时已经因 batch 被拆开而红，尚未执行到 `ping` 转移；仅把相应内部状态改成“接受 `ping`”不会改变第一批非法结束，因此原始负 fixture 仍红。该 mutation 不能按文档要求证明判据对目标 `ping` 缺陷有判别力。

**证据或失败场景**：按 `acceptance.md:334-340` 执行 `[message_start] → [ping] → [first content block …]`：读取第一批 `[message_start]` 后进入仅限 batch 内的 `message_started_but_no_completed_block`，但 batch 已结束，立即非法；zero-content 的 `[message_start] → [ping] → [message_delta → message_stop]` 同理。即便 mutation 放宽这两个状态“接受 `ping`”，第二批也不可达。`acceptance.md:351` 又明确要求 fixture 必须因目标分支转绿，并排除“batch 格式错误或另一规则先失败”，所以当前文本内部自相矛盾，无法作为可执行验收控制。

**修复建议**：把两个目标拆成独立、单缺陷的控制轴。对“batch 内禁止 `ping`”，使用单一完整 batch，例如 `[message_start → ping → first complete block envelope]` 与 `[message_start → ping → message_delta → message_stop]`，只放宽相应内部状态的 `ping` 转移后应转绿；对“不得拆开首批／terminal batch”，另设不含 `ping` 的 split-batch fixture，例如 `[message_start] → [first complete block envelope]` 与 `[message_start] → [message_delta → message_stop]`，并以“允许内部瞬态跨 batch 停留”为独立 mutation。每个 mutation 都必须先验证目标 fixture 转绿，再由外层 mutation gate 因非法 fixture 被接受而红；同时保留合法首 batch、合法 zero-content batch 与首 block 已接受后的合法 `ping` 正样本，防止 false-red。

### 2. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:8,11,29,33,404,421` — R4-M2 的 current Architecture 同快照绑定与参考边界再次失真

**问题**：Acceptance 绑定的 Architecture SHA-256 为 `ea6a3eca21c653096b17914d56497a5c6bbb6a8d1c237ebf2a055db24e31dc86`，current 文件的 SHA-256 为 `5f6b8bd2f24247ae762cf5e76c129171772b7857839bb5db4fa455cfc5245752`。这不是哈希命令误差：`sha256sum` 与 Python `hashlib.sha256` 得到相同 current 值。Git diff 还显示绑定快照后 Architecture 新增了 unknown capability 已决约束，并把 ADR-BRIDGE-04 从“待主会话确认”移到“Spec 已决架构约束”；Acceptance route manifest 仍按旧边界描述它为 Architecture 中“仍待确认”的措辞。

**证据或失败场景**：current Spec hash 与 Acceptance 绑定值相同，且逐节 policy 对账未发现 Architecture 反向覆盖 Spec；因此无需把 Architecture 提升为行为 oracle，也无需重做已匹配的 Spec 七域 expected。但执行 Acceptance 自己的“Spec／Architecture SHA-256 来自同一最终输入快照”门时，Architecture 必然不匹配；继续把状态写为 `READY_FOR_FINAL_REVIEW` 并宣称 R4-M2 已关闭，会让定稿证据引用一个并非 current 的参考文件。Architecture 的 current 改动恰好涉及 route policy 的已决／待决分类，不能只以“非行为 oracle”为由忽略引用漂移。

**修复建议**：在同一最终快照重新读取 current Architecture，确认其新增措辞仍只承载 Spec 已决 unknown-capability fail-closed，不把 typed kernel、History receipt owner 或待确认 ADR 提升为 Acceptance expected；然后更新 Architecture hash，并把 route manifest 的旧句改为“不依赖 Architecture 的内部承载方案；unknown capability expected 直接来自 Spec”，或等价的 current 边界表述。Spec hash 未变且七域政策已对账一致时，不应机械重做无关内容；但更新后必须在同一次最终 gate 中重算 Acceptance／Spec／Architecture hash 并复核状态、manifest 和处置表相互一致。

## 主观建议

无。本轮两项结论都来自 current 文本的可执行状态机、独立哈希结果、current Architecture diff 与 Acceptance 自有定稿门，不依赖实现偏好。

## 最终结论

R4-M1 的行为合同已收紧为首个完整 block 与 `message_start` 同 batch、zero-content 三事件同 terminal batch，并且两种内部瞬态均禁止 `ping`；但当前负 fixture 与 mutation 没有形成能咬住目标分支的正样本对照，验收判据仍可能假绿。R4-M2 的 current Spec hash 与七域 policy 对账已经成立，Architecture 也仍只是参考；但其 current hash 和 ADR-BRIDGE-04 分类均已越过 Acceptance 绑定快照，故“同快照关闭”声明仍不成立。

**本轮为 blocker 0、major 2，Acceptance oracle 文档不可定稿。候选产品仍为 `UNVERIFIED`，且本轮没有取得任何可以升级产品 verdict 的证据。若修复后复评达到 0 major，届时才可明确宣布 Acceptance oracle 文档可定稿，同时仍须保持候选产品 `UNVERIFIED`。**
