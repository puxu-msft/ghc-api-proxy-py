# Anthropic Responses Bridge Architecture 用户裁决可读性定向复评 R2

## 评审摘要

- **评审范围**：只逐条复核上一轮 `docs/tmp/260806-review-architecture-readability.md` 的 `1 major + 1 minor` 在 current `docs/agents/anthropic-responses-bridge/architecture.md` 中是否关闭，并对账正式 `spec.md` 的 unknown capability 已决约束与 `README.md` 的完整阅读／最小裁决路径。本轮不重做 Architecture 技术正确性评审，不扩展其他文档问题，也不判断候选实现是否完成。
- **总体 verdict**：**可进入下一阶段；current Architecture 可供用户从 README 开始完整阅读后裁决。** 上一轮唯一 major 的实质冲突已经关闭，唯一 minor 已关闭；本轮 blocker 0、major 0。仍有一处不阻断裁决的标题／导航残余，列为 minor。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：逐项对照旧报告的 major 与 minor；扫描 current Architecture 的顶部已决合同、Verdict 紧邻术语说明、Route policy、`Spec 已决架构约束`、`待主会话确认的架构决策草案`、处置表及最终推荐；将 `ADR-BRIDGE-04` 与 current Spec 的行为 oracle、route precedence、已冻结决策逐句对账；核对 README 的权威边界、Architecture 导航、已决／待决分栏与两个最小裁决问题；用 `sha256sum` 和 Python `hashlib.sha256` 两种原理交叉验证四份证据文件哈希。
- **双视角覆盖证据——第一人称执行**：模拟用户从 README 进入，先接受“完整阅读五份文档且 Architecture 必须全文阅读”的约束，再进入 Architecture，读取顶部已决合同与紧邻术语说明，依次阅读 A／B／C、详细 owner／facts／frontier／History 设计、Spec 已决约束和待确认草案，最后回到 README 只回答“目标架构选择”和“迁移落地边界”；另模拟用户在 Architecture 末尾按 ADR 小节逐项判断哪些需要投票，确认 `ADR-BRIDGE-04` 已不能触发 unknown capability 重裁，但章节标题仍可能让 ADR-BRIDGE-03／06 看起来属于待确认清单。
- **证据基线**：每次 shell 取证均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。最终落盘前读取的 Architecture SHA-256 为 `5f6b8bd2f24247ae762cf5e76c129171772b7857839bb5db4fa455cfc5245752`，Spec 为 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，README 为 `b7281a1fe078e2fcbf1d1f0402f00c0bb64f3386188d70cd813db127ef40b804`，上一轮报告为 `92b00ba444da4e70dd6d01fb546425a23bd62dc7b277486af6fd8b70de2d6783`；两种哈希方法结果一致。

## 上一轮两项逐条复核

### 1. 旧 major：已决行为与待裁决 Architecture 混列，ADR-BRIDGE-04 重开 unknown capability

**结论：major 已关闭。**

- Architecture 顶部已经把 unknown／missing endpoint capability fail closed 明列为已决路由与兼容合同，并明确本文不重开已决产品合同，见 `architecture.md:7-9`。
- Route policy 正文不再把该行为写成建议或可选项，而是要求遵守正式 Spec，并明确它是目标架构的输入约束、不是本文待用户重裁的架构选项，见 `architecture.md:278-282`。
- `ADR-BRIDGE-04` 已移出“待主会话确认”的列表，独立放入 `Spec 已决架构约束`，其裁决状态明确说明：本项只承载 Spec 约束，改变它必须先重裁 Spec，见 `architecture.md:507-513`。
- Current Spec 自身仍是行为 oracle，并在 route precedence 与冻结轴中规定 unknown capability fail closed，见 `spec.md:5,80,513-515`。Architecture 与 Spec 的权威方向现在一致，不再存在相反执行指令。
- README 明确把 Architecture 中与 Spec 相同的 route、buffering、carrier、unknown capability 和 post-commit failure 定位为实现解释而非新投票项，并把用户问题压缩为目标架构与迁移边界，见 `README.md:146-150,248-269`。

第一人称执行结果是：用户即使按 Architecture 末尾小节逐项阅读，也不会再被要求决定 unknown capability 是否 fail closed；回到 README 后只需裁决方案 B／A／C 组合及迁移落地方式。因此旧 major 的阻断性根因已消失。

### 2. 旧 minor：置顶 Verdict 集中使用未解码术语

**结论：minor 已关闭。**

`architecture.md:13` 已在推荐句之前紧邻解释 `typed semantic kernel`、`protocol leg`／`transport leg`、`semantic block assembler`、`downstream sink`、`delayed response-start owner` 与 `delivery frontier`，并分别说明职责或非职责。按首次阅读顺序，用户无需先跳到后文才能区分内部 typed model、协议／物理传输、完整 block 组装、唯一写入点、延迟响应头和交付记录；该修改直接满足上一轮建议与 Architecture 自身处置表 `architecture.md:562` 的复审要求。

## 事实性发现

[minor] `docs/agents/anthropic-responses-bridge/architecture.md:515-548`、`docs/agents/anthropic-responses-bridge/README.md:142` — “待主会话确认的架构决策草案”仍包含明确标为“用户重裁后的已决边界”的 ADR-BRIDGE-03 和“已决 bridge 产品合同”ADR-BRIDGE-06，README 导航又把该节概括为 `ADR-BRIDGE-01～06`，但 ADR-BRIDGE-04 实际已被移到上一节 — 这不再重开 unknown capability：Architecture 顶部、独立 ADR-BRIDGE-04 和 README 的已决／待决分栏已经给出一致边界，README 的最小问题也只保留目标架构与迁移边界，因此用户仍可完成正确裁决；但按章节标题逐项执行时，读者仍需自行判断 ADR-BRIDGE-03／06 是“待投票”还是“仅记录输入约束”，而 `ADR-BRIDGE-01～06` 也不是 current 章节的精确成员集合 — 将该区域拆成“待用户确认的内部架构决策”和“Spec／既有用户裁决的架构承载记录”，或至少在 ADR-BRIDGE-03／06 标题旁写明“不在本轮待裁决清单”；同步把 README 导航改为精确列举该节实际成员与状态。

未发现阻断性问题，也未发现 major。

## 主观建议

无。方案 B 是否接受、方案 A 的迁移边界如何记录，仍由用户在依照 README 完整阅读后裁决；本轮不替用户作该决定。

## 结论

上一轮 `1 major + 1 minor` 的两项原始缺陷均已关闭：ADR-BRIDGE-04 已成为独立的 Spec 已决架构约束，置顶术语也已在 Verdict 前可解码。Current Architecture 因而达到 **blocker 0、major 0**，可以供用户从 `docs/agents/anthropic-responses-bridge/README.md` 开始，按其推荐顺序完整阅读后作架构裁决。剩余 minor 只涉及末尾章节标题和 README 导航对已决记录／待决草案的分类精度，不阻断阅读或裁决。
