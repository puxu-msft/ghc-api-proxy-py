# Anthropic Responses Bridge Architecture 用户裁决可读性评审

## 评审摘要

- **评审范围**：只读检查 current `docs/agents/anthropic-responses-bridge/architecture.md` 是否足以让用户完整阅读后作出架构裁决。仅核对目录／摘要、方案 A／B／C、推荐理由、已决／待决状态、与正式 Spec 的权威边界、术语首次定义，以及是否存在需要 README 导读才能跨越的阅读跳跃。`spec.md` 仅用于核对权威边界，`README.md` 仅用于核对阅读入口，`docs/tmp/260806-review-bridge-architecture-r3.md` 仅用于确认既有技术终审已是 blocker 0、major 0；本轮不重做技术正确性评审，也不改变 R3 结论。
- **总体 verdict**：**修复 major 后可供用户裁决。** 方案 A／B／C 的内容、比较表与方案 B 的推荐理由本身可解码，feature README 也已提供完整阅读顺序、权威分工和最小裁决问题；但 architecture 仍把正式 Spec 已冻结的 unknown capability 行为列为待确认项。用户按 architecture 的 ADR 草案逐条裁决时，仍可能重开已决行为。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：完整通读 architecture 与 feature README；扫描 architecture 全部标题层级、A／B／C 段落、比较表、首尾推荐、ADR-BRIDGE-01～06、所有“已决／冻结／待确认／建议”措辞和关键术语首次出现位置；逐项对账 Spec 的文档状态、route precedence 与“已冻结决策与残余分叉”；核对 README 的阅读约定、权威边界、推荐阅读顺序、architecture 导航、已决／待决分栏和最小裁决问题。首次扫描时 README 尚不存在，最终交叉验证发现并发新增的 `docs/agents/anthropic-responses-bridge/README.md` 后，已重读 current 文件并撤销原“缺少导读入口”发现。
- **双视角覆盖证据——第一人称执行**：模拟用户先按 README 顺序完整阅读 Spec、Research、Architecture、Acceptance 与 Implementation，再回到 README 的两个最小裁决问题；模拟用户直接打开 architecture，从状态声明进入 Verdict，依次阅读当前事实、A／B／C、推荐目标架构和末尾 ADR 草案；模拟用户准备逐条批准 ADR-BRIDGE-01～06，并在 ADR-BRIDGE-04 遇到与正式 Spec 已冻结行为相反的“仍待确认”指令；模拟首次阅读置顶 Verdict 的术语解码，再回跳后文章节寻找定义。
- **证据基线**：每次 shell 取证均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。最终评审读取的 architecture SHA-256 为 `ea6a3eca21c653096b17914d56497a5c6bbb6a8d1c237ebf2a055db24e31dc86`，Spec SHA-256 为 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，README SHA-256 为 `b7281a1fe078e2fcbf1d1f0402f00c0bb64f3386188d70cd813db127ef40b804`；三者在最终落盘后分别以 `sha256sum` 与 Python `hashlib.sha256` 交叉验证。

## 范围内通过项

- **方案 A／B／C 可区分**：`architecture.md:42-97` 分别说明 A 的迁移接线优势与长期 wire 耦合、B 的 typed facts／单 driver／transport 正交收益及 schema 风险、C 的双 lifecycle owner 缺陷；比较表覆盖 owner、typed facts、HTTP／WS 收敛、converter 单源、delivery 验证和长期演进。
- **推荐理由足以理解**：`architecture.md:13-15,85-97,566-569` 一致推荐 B，保留 A 为受约束迁移兼容形态并明确拒绝 C；推荐不是只给结论，已给出结构风险与长期演进理由。
- **当前事实与目标状态有基本隔离**：`architecture.md:3,17-31` 明示文档不是已落地能力，并将 current implementation 与目标架构分开。问题不在“是否把提案冒充实现”，而在提案内部哪些项目仍可裁决。
- **README 导读已经补齐必要跳跃**：`README.md:3-49` 给出完整阅读约定、五份文档的权威边界与推荐顺序；`README.md:109-150` 为 architecture 提供 A／B／C 入口、章节导航和 Spec 不覆盖边界；`README.md:211-270` 分开已决行为、待用户接受的架构提案、未实现状态，并把用户真正需要回答的问题压缩为目标架构选择与迁移落地边界。因此本主题确实需要 README 级导读，current README 已足以承担该职责；用户不应绕过 README 直接从 architecture 开始裁决。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/architecture.md:3,280,505-545` — 待裁决清单仍把已决产品行为与真正待批架构选择混成同一组“待主会话确认”的 ADR 草案，且 ADR-BRIDGE-04 直接与正式 Spec 的冻结状态冲突 — 文档总状态称其为待确认架构提案，`ADR-BRIDGE-03` 和 `ADR-BRIDGE-06` 却在同一清单内自称“用户重裁后的已决边界／已决 bridge 产品合同”；更关键的是 `architecture.md:280,526-530` 仍要求确认 unknown／missing capability 是否 fail closed，而正式 `spec.md:5,80,513-515` 已声明 Spec 是实现与验收的行为 oracle，并冻结 unknown capability fail closed。`README.md:148,211-235` 已正确说明这些行为不是新投票项，却不能消除 architecture 正文给出的相反执行指令。第一人称按 ADR-BRIDGE-01～06 逐条裁决时，用户无法仅凭 architecture 机械区分“批准架构形态”“确认 Spec 已决约束的承载方式”和“重裁产品行为”，仍可能给出相互矛盾裁决 — 将 ADR 草案按 `待用户裁决／已由 Spec 冻结／未来证据门控` 明确分栏；ADR-BRIDGE-04 不再请求确认 unknown capability 行为，只说明方案 B 如何承载 Spec 已冻结的 fail-closed policy。对 ADR-BRIDGE-03、06 等已决行为同样改为“输入约束／架构承载”，真正待批项只保留内部架构选择与迁移边界，并与 README 的最小问题清单逐项一致。

[minor] `docs/agents/anthropic-responses-bridge/architecture.md:11-15` — 置顶 Verdict 在首次定义前集中使用 `typed semantic kernel`、`protocol leg`、`semantic block assembler`、`downstream sink`、`delayed response-start owner` 与 `delivery frontier` — 这些概念的可解码说明分散在后文，例如方案 B、Protocol leg 与 physical transport、职责分离和 Frontier 模型章节；README 能告诉读者去哪里读，却不能降低 architecture 首屏本身的术语负荷。完整读完后大多可以反向理解，但首次阅读摘要时必须记住多个未定义名词并回跳，削弱摘要作为裁决入口的作用 — 在 Verdict 前增加短术语表，或把 Verdict 改写为用户结果语言并链接到后文定义；首次出现时用一句话说明“它负责什么／它不负责什么”，不要只给英文组件名。

## 主观建议

无。方案 B 是否最终接受属于用户裁决；本报告只指出 current architecture 尚有一处会误导裁决范围的权威冲突，不对既有技术方案重新评分。

## 建议阅读入口

从 `docs/agents/anthropic-responses-bridge/README.md` 开始，并严格按其“推荐阅读顺序”完整阅读五份文档。architecture 不是单独可消费的裁决包：Spec 先冻结行为边界，Research 解释证据来源，Architecture 承载内部方案裁决，Acceptance 说明如何验证，Implementation 最后校准当前落地状态。

## 结论

Current architecture 的 A／B／C 比较和推荐理由已经足够，README 也已补齐目录、跨文档权威边界和裁决入口；但 architecture 自身仍把 Spec 已冻结事项列为待确认，因此**尚不足以直接供用户作最终裁决**。修复该 major 后，术语首次定义属于有限的可读性优化。R3 的技术正确性 verdict 保持不变，本轮没有发现或声称新的技术正确性 blocker／major。
