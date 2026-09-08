# Anthropic Responses bridge README current drift 只读审计

- **评审范围**：current `docs/agents/anthropic-responses-bridge/README.md` 相对 current `architecture.md`、`acceptance.md`、`implementation.md` 的标题、阶段状态、唯一用户裁决矩阵、Acceptance provenance 与 foundations integration 状态。为验证这些转述，额外交叉读取 `docs/tmp/260807-review-bridge-acceptance-r7.md`、`docs/tmp/260807-review-docs-merged-r2.md`，并只读核对相关 Git refs、worktree 与三提交拓扑。本轮不做架构、协议、代码或测试技术评审。
- **总体 verdict**：**修复 major 后可进入。** README 的行为／架构／产品状态边界、`D-ARCH`／`D-MIGRATION` 决策矩阵和 `6a00f6f…` integration 状态与 current 来源一致；但 README 仍把只绑定旧 Architecture 快照的 Acceptance R7 写成 current Acceptance 的提交依据，并以已经失效的例子描述 Implementation 状态。另有一处 Architecture 章节标题陈旧。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：1。
- **README 当前内容身份**：SHA-256 仍为 `3f48e6a3cab32545591bad32ae3ee96682a4d9cc870408fbe1da87f664b9b920`。本轮在 `main@ed77c9d191df81c451c25161420515cca52ce6a4` 下分别用 `sha256sum` 与 Python `hashlib.sha256` 交叉复核，两种实现结果一致。
- **双视角覆盖证据——机械核对**：逐项对账 README 的权威角色表、当前快照、Architecture 导航、Acceptance 导航、Implementation 导航、唯一用户裁决段与裁决后记录要求；解析 README 全部本地 Markdown path／fragment，未发现失效链接；分别用两种 SHA-256 实现锁定 README、Architecture、Acceptance 与 Implementation current bytes；只读核对 integration branch、feature refs、archive ref、worktree clean 状态及三提交 parent 链。
- **双视角覆盖证据——第一人称执行**：模拟下一位 planner 从 README 冷启动，依次走“判断哪些文档可提交”“定位 Architecture 待决章节”“只回答用户真正需要裁决的两项”“确认 foundations 是否已进 main”“决定下一步是文档收敛还是产品回放”五条路径。Acceptance provenance 会让执行者把旧 R7 当成 current bytes 的独立放行；Architecture 标题漂移会让执行者找不到 README 点名的真实标题。决策矩阵与 integration 路径则能导向正确动作。

## 事实性发现

### [major] `README.md:32,34` — Acceptance current provenance 与 Implementation 转述已经陈旧

**问题**：README 第 32 行写 `[Acceptance 独立终审 R7]` “确认 current Acceptance 可提交”；第 34 行又以“R7 定稿结论覆盖 `implementation.md` 中较早的‘待本轮独立终审’转述”为 current 示例。这两个说法都不再描述 current 文件组合。

**证据**：

- R7 自身第 9 行明确绑定 Architecture SHA-256 `6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327`，并据此判定当时的 Acceptance 可提交。
- current Architecture SHA-256 已为 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`。
- current Acceptance SHA-256 已为 `19635e04886052fa2c2c98e42aab1c87c23c1fb9c8935753201928eaa8463498`。其第 8～11 行已经自行改绑 current Architecture `c6088a…`，明确把 R7 限定为旧 `6de919…` 组合，并记录后续 merged-state provenance；因此 R7 不能单独证明 current Acceptance bytes 已获独立放行。
- current Implementation SHA-256 为 `e43fd96003a8de3a1b9c5e165a65d711e25e76d1cc6444415088af0a994dda65`。其第 7、18、20 行仍写 Acceptance 绑定 `6de919…`，但已经不再处于 README 所称“待本轮独立终审”的状态；README 第 34 行举例方向与 current drift 相反。
- `docs/tmp/260807-review-docs-merged-r2.md` 绑定 README `3f48…` 并曾将这一 provenance 冲突列为 merged-state major。之后 Acceptance 已修改，README 与 Implementation 尚未同步到新的 current 内容身份。

**失败场景**：planner 从 README 冷启动时，会把“R7 0／0”当成 current Acceptance `19635…` 的独立提交许可，跳过对 current bytes 的内容身份核验；再读第 34 行时，会误以为 Implementation 只是落后在“等待 R7”，而不是仍转述旧 Architecture hash。由此可能在正式 docs 提交门上得到 false-green，或把真正需要同步的 source-of-truth 留给后续会话继续猜。

**修复建议**：

1. 把 README 第 32 行拆成“文档自身状态”与“独立评审 provenance”两层：保留 current Acceptance 自身为 `FINALIZED_ACCEPTANCE_ORACLE`、产品为 `UNVERIFIED`；明确 R7 只绑定 `6de919…` 历史组合，不再写成 current `19635…` 的提交许可。
2. 若 current Acceptance `19635…` 已有后续独立复评，改为引用并绑定那份报告；若尚无，则只写“已同步 current Architecture `c6088a…`，current bytes 待独立内容身份复核”，不得由 README 自行推导“可提交”。
3. 把 README 第 34 行的过时例子替换为 current 事实：Acceptance 已改绑 `c6088a…`，而 Implementation 仍转述 `6de919…`；在 Implementation 同步前，涉及 Acceptance provenance 的下一动作以 Acceptance 自身 current 状态与后续独立报告为准。不要改变任何代码实施状态。

### [minor] `README.md:129` — Architecture 章节导航仍引用不存在的“Verdict”标题

**问题**：README 的 Architecture 章节导航写“开头状态、已决合同与‘Verdict’”，但 current Architecture 的真实一级章节标题是 `## 提案结论与裁决边界`，全文没有 `Verdict` 标题。

**证据或失败场景**：README 的 Markdown 链接均能解析，因此这不是 broken link；但第一位按表逐标题阅读的 planner 无法在 Architecture 中找到被点名的“Verdict”，只能靠语义猜到第 34 行的“提案结论与裁决边界”。这会削弱 README 作为精确阅读索引的作用。

**修复建议**：把 README 第 129 行的章节名改为“开头状态、已决合同与‘提案结论与裁决边界’”。其阅读重点和关键问题无需改写。

## 精确对账矩阵

| 对账面 | README current 表述 | current 来源 | 结论 | 最小动作 |
|---|---|---|---|---|
| Architecture 状态 | 非规范提案，尚未获用户接受；终审 0／0不等于用户接受 | `architecture.md:3` | 一致 | 不改状态语义 |
| Architecture 标题 | “Verdict” | `architecture.md:34` 为“提案结论与裁决边界” | 陈旧 | 只改标题文字 |
| 唯一决策矩阵 | 仅 `D-ARCH` 与条件性的 `D-MIGRATION`；推荐 B／M2；B 有五项不可拆分核心 | `architecture.md:569` 起的唯一用户裁决矩阵 | 一致 | 不改选项、推荐、五项核心或裁决边界 |
| 已决与待决边界 | `ADR-BRIDGE-02`～`06` 不是隐藏投票项 | Architecture 已决承载章节与矩阵 | 一致 | 不改 |
| Acceptance 文档状态 | `FINALIZED_ACCEPTANCE_ORACLE`；产品 `UNVERIFIED` | `acceptance.md:11` | 一致 | 保留状态与产品边界 |
| Acceptance provenance | R7 证明 current Acceptance 可提交 | R7 绑定 Architecture `6de919…`；current Acceptance 已是 `19635…` 并绑定 `c6088a…` | 陈旧，major | 改为历史 R7＋current bytes 的真实复评状态 |
| Integration identity | clean `integrate/260806-bridge-foundations@6a00f6f…`，三提交线性链，尚未进 main | Implementation 第 8 行；本轮 Git 实探 | 一致 | 不改 identity 或顺序 |
| Integration verdict 边界 | merged-state 代码 0／0、范围内 verification `PASS`，不等于完整产品 PASS | Implementation 第 8 行及产品 `UNVERIFIED` 边界 | 一致 | 不改 |
| Integration topology | cardinality `9e5f874…` → liveness `cae83f4…` → request `6a00f6f…` | clean integration worktree 的 parent 链实探 | 一致 | 不重建第二条 integration 链，不改 README 摘要 |
| Main 落地状态 | 三提交仍未进入 `main` | `main@ed77c9d…` 与 integration ref 实探 | 一致 | 不改 |
| Implementation 作为易变真相源 | 操作前重新 gate；跨文档转述落后时回到源文档 | `implementation.md` 仍转述 Acceptance `6de919…` | 原则正确，示例陈旧 | 只替换第 34 行 current 示例；Implementation 另行同步 |

## 最小修订清单

1. **必须先修** README 第 32 行：保留 Acceptance／产品状态，撤销“R7 证明 current bytes 可提交”的断言，换成精确 provenance。
2. **同一处同步** README 第 34 行：删除 Implementation 仍“待 R7”的过时例子，改写为 current Acceptance `c6088a…` 与 Implementation `6de919…` 的真实漂移方向。
3. **机械修正** README 第 129 行：`Verdict` → `提案结论与裁决边界`。
4. **明确不改** `D-ARCH`／`D-MIGRATION`、A／B／C、M1／M2、B 的五项不可拆分核心、`ADR-BRIDGE-02`～`06` 的非待决分类。
5. **明确不改** foundations integration 的 tip、三提交顺序、尚未进入 main、局部 verification 不等于产品 PASS，以及共享 integration 载体的保留边界。
6. README 修订后，以最终 README SHA-256 和当时 current Architecture／Acceptance／Implementation SHA-256 绑定一次定向复评；冷启动 planner 只需从 README 得到“读什么、当前什么状态、哪两项待裁决、下一状态源在哪里”，不要再让 README 复制 Implementation 的完整易变计划。

## 主观建议

未提出。上述均为 current 内容身份、标题或状态链的可复现对账结果；决策矩阵与 integration 摘要已足够，不建议借本轮扩大 README 内容。

## 结论

README 当前 hash **仍是** `3f48e6a3cab32545591bad32ae3ee96682a4d9cc870408fbe1da87f664b9b920`。本轮发现 **0 blocker、1 major、1 minor**。修正 Acceptance provenance、替换失效的 Implementation 示例并更新一个 Architecture 标题后，README 才适合作为下一位 planner 的冷启动入口；决策矩阵与 integration 状态无需重写。
