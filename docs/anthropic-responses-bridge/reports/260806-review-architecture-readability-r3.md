# Anthropic Responses Bridge Architecture 用户裁决可读性最终定向复评 R3

## 评审摘要

- **评审范围**：只复核 R2 报告 `docs/tmp/260806-review-architecture-readability-r2.md` 遗留的唯一 minor：current `docs/agents/anthropic-responses-bridge/architecture.md` 是否已把 ADR-BRIDGE-03／04／06 的已决承载记录与 ADR-BRIDGE-01／02／05 的待用户确认决策清晰分组，以及 current `docs/agents/anthropic-responses-bridge/README.md` 的导航是否仍准确到不会误导用户裁决。本轮不重做 Architecture 技术正确性评审，不扩展其他文档问题，也不判断候选实现状态。
- **总体 verdict**：**可进入下一阶段；current Architecture 可供用户依照 README 完整阅读后裁决。** R2 遗留 minor 在 Architecture 正文中已经关闭；README 仍有一处合并列出的旧导航措辞，但其权威边界、完整阅读要求、已决／待决说明和两项最小裁决问题均保持正确，不会把用户引向重裁已决合同。该残余列为 minor，不阻断阅读或裁决。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：逐句读取 R2 唯一遗留 minor；扫描 Architecture 的两个 ADR 分组标题、分组说明、六个 ADR 的实际成员及评审处置表；核对 README 的文档权威表、Architecture 章节导航、已决／待决分栏、完整阅读要求和用户最小裁决问题；全文检索旧节名、当前节名与 ADR-BRIDGE-01～06 引用，确认 Architecture 已无混列而 README 仍保留两处旧导航表述。
- **双视角覆盖证据——第一人称执行**：模拟用户从 README 进入，先遵守“完整阅读五份文档且 Architecture 必须从头到尾阅读”，再在 Architecture 末尾按分组逐项判断：先把 ADR-BRIDGE-03／04／06 当作不可重新投票的输入约束，再只对 ADR-BRIDGE-01／02／05 作内部架构裁决；随后回到 README，仅回答“目标架构选择”和“迁移落地边界”。该流程不会要求用户重裁 route、capacity、reasoning carrier 或 post-commit 基础行为，但 README 的旧节名和 `ADR-BRIDGE-01～06` 概括会造成一次可避免的回查。
- **证据基线**：每次 shell 取证与落盘均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。落盘前 current Architecture SHA-256 为 `7bd98a384ccb313f2e72a598dc876766a1044a9bfcef4685ba09412895ea7679`，README 为 `b7281a1fe078e2fcbf1d1f0402f00c0bb64f3386188d70cd813db127ef40b804`，R2 报告为 `577b18d7ae1b1e3fcf643e2d404efe1af870fedee45aa26adbf3a53cce445c21`。

## R2 遗留 minor 复核

### Architecture 分组

**结论：R2 遗留 minor 在 Architecture 正文中已关闭。**

- `architecture.md:507-509` 使用“已决约束的架构承载记录（ADR-BRIDGE-03／04／06；非待裁决）”作为独立标题，并明确该节不改变既有技术内容或裁决状态，也不属于待用户确认的内部架构决策。
- `architecture.md:511-530` 只收录 ADR-BRIDGE-03、ADR-BRIDGE-04 与 ADR-BRIDGE-06；各项分别重申 capacity、unknown endpoint capability 与 bridge 产品合同的已决状态或承载方式。
- `architecture.md:532-534` 使用“待用户确认的内部架构决策（仅 ADR-BRIDGE-01／02／05）”作为相邻独立标题，并再次明确 ADR-BRIDGE-03／04／06 只作为上一节的已决输入约束，不随提案重新投票。
- `architecture.md:536-552` 只收录 ADR-BRIDGE-01、ADR-BRIDGE-02 与 ADR-BRIDGE-05。读者不需要根据各 ADR 正文自行猜测状态，标题、成员集合与执行指令三者一致。

第一人称执行结果是：读者沿文档顺序到达该区域时，会先看到明确标为“非待裁决”的三项已决承载记录，再看到明确标为“仅 01／02／05”的待确认清单；不存在把 ADR-BRIDGE-03／04／06 一并提交用户投票的合理阅读路径。

### README 导航

**结论：核心导航仍准确到不误导，但局部导航未同步 current Architecture 标题，保留一个 non-blocking minor。**

- `README.md:5-7,36-46` 要求完整阅读五份文档，尤其禁止未全文阅读 Architecture 就作裁决；这会让用户接触 current Architecture 的明确分组，而不是只凭索引旧措辞作决定。
- `README.md:13-21` 正确区分 Spec、Acceptance、Architecture、Research 与 Implementation 的权威角色，并明确 Architecture 未经用户接受前不是 ADR、不能覆盖 Spec。
- `README.md:146-150,210-239` 明确把 route、buffering、carrier、unknown capability、post-commit failure 等定位为已决行为的实现解释，并另列仍待用户接受的内部架构提案。
- `README.md:248-269` 把实际用户裁决压缩为“目标架构选择”和“迁移落地边界”，并明确无需重裁 route precedence、capacity、reasoning carrier、server-tool、post-commit retry 或 strict field policy。因此即使用户注意到旧导航行，也不会得到错误的待裁决集合。

## 事实性发现

[minor] `docs/agents/anthropic-responses-bridge/README.md:31,142` — Architecture 导航仍使用旧状态／旧节名：快照写“待主会话确认的架构提案”，章节表写“待主会话确认的架构决策草案”并概括为 `ADR-BRIDGE-01～06`；current Architecture 则已改为待用户完整阅读后接受，并拆成“已决约束的架构承载记录（03／04／06；非待裁决）”与“待用户确认的内部架构决策（仅 01／02／05）” — README 其余权威边界、已决／待决分栏及最小问题清单足以纠正该局部旧措辞，所以不会误导最终裁决，也不构成 major；但用户按章节导航定位时会找不到同名标题，并需自行把 `01～06` 重新映射到两组 — 将 `README.md:31` 改为与 Architecture 状态头一致的“待用户完整阅读后接受的非规范架构提案”；将 `README.md:142` 拆成两行，分别精确指向 current 两个章节及其成员集合。

未发现阻断性问题，也未发现 major。

## 主观建议

无。R2 遗留项只要求判断分组与导航可读性；方案 B、方案 A 的迁移边界及详细 owner／facts／frontier／History 合同仍应由用户完整阅读后裁决。

## 结论

Architecture 已清晰、相邻且无重叠地把 ADR-BRIDGE-03／04／06 归为非待裁决的已决承载记录，把 ADR-BRIDGE-01／02／05 归为真正待用户确认的内部架构决策。README 的核心阅读路径和裁决边界仍准确，不会引导用户重裁已决合同；仅有旧状态／章节导航措辞尚待同步。最终结果为 **blocker 0、major 0、minor 1**，该 minor 不阻断：current Architecture 可以供用户依照 README 完整阅读后作最终裁决。
