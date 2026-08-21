# Architecture 用户裁决问题阅读核对报告

- **评审范围**：当前工作树中的 `docs/agents/anthropic-responses-bridge/README.md` 与 `docs/agents/anthropic-responses-bridge/architecture.md`；为判定哪些内容已由行为规格冻结，交叉读取当前 `spec.md`，并扫描同目录五份源文档中的 ADR、待裁决、另行裁决与用户门控措辞。评审基线为 `/home/xp/src/ghc-api-proxy-py` 的 `main@ed77c9d191df81c451c25161420515cca52ce6a4`，评审对象是该 HEAD 上的当前未提交文档工作树内容，而不是 HEAD blob。
- **总体 verdict**：**修复 major 后可进入用户裁决阶段。** 当前不能断言 ADR-BRIDGE-01／02／05 是全部且边界准确的待用户裁决项，也不能让用户仅依现有问题映射作出无歧义裁决。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：1。
- **用户阅读就绪结论**：本轮不满足“0 major”条件，因此暂不能声明“用户可从 README 开始完整阅读后做裁决”。README 仍可作为材料入口，但在下面两项 major 关闭前，只能用于理解背景，不能作为最终裁决问卷。

## 双视角覆盖证据

### 机械核对

- 完整读取当前 `README.md` 与 `architecture.md`，并逐项对账 ADR-BRIDGE-01～06 的分类、标题、建议、理由、未采用方案和已决状态。
- 扫描同目录五份源文档中的 `ADR-BRIDGE-*`、待裁决、待确认、另行裁决、用户裁决、用户门控和最终推荐措辞，用 `spec.md` 的冻结合同核对 Architecture 是否把已决行为重新包装成待决问题。
- 用两种不同方法核验 README Markdown 文件链接：一是解析全部链接并相对 README 所在目录解析目标，二是独立枚举五个唯一目标并逐文件执行存在性检查。两种方法均确认 `spec.md`、`research.md`、`architecture.md`、`acceptance.md`、`implementation.md` 文件目标存在。
- 对账 README 的章节导航文字与 Architecture 当前标题，确认 README 所写“待主会话确认的架构决策草案”并不是当前 Architecture 的真实标题，且 README 所写 ADR-BRIDGE-01～06 与当前章节实际仅列 ADR-BRIDGE-01／02／05 不一致。

### 第一人称执行模拟

- 模拟用户从 README 开始，按推荐顺序完整阅读五份文档，随后尝试回答 README 的“目标架构选择”和“迁移落地边界”两个问题。
- 模拟用户进入 Architecture 的“待用户确认”章节，尝试逐项对 ADR-BRIDGE-01／02／05 作出接受或拒绝，并检查拒绝 ADR-BRIDGE-02 或 ADR-BRIDGE-05 是否会意外推翻 Spec 已冻结行为。
- 模拟用户接受 ADR-BRIDGE-01 后，尝试判断这是否同时表示接受 `PolicyOutcome`、transport cleanup、`AnthropicBlockKey`、delayed response-start、`DeliveryFrontier` 和 History receipt ownership 等全部详细边界；当前两份文档给出的 ADR 归属粒度不足以得到唯一答案。
- 模拟用户选择“分阶段建立 B”或“完整骨架一次建立”，检查该选择应记录在哪个 ADR；当前 Architecture 的 ADR 清单没有可直接承载这一裁决的明确条目。

## 事实性发现

### [major] `architecture.md:532-552`、`README.md:213-226,248-269`、`spec.md:263-269,291,322-335,517,527` — ADR-BRIDGE-02／05 把已冻结行为与可能仍开放的内部结构混成待决项

**问题**：Architecture 声明“仅 ADR-BRIDGE-01／02／05”待用户确认，但 ADR-BRIDGE-02 的完整 block commit、首批 framing 和 terminal batch，以及 ADR-BRIDGE-05 的无安全 continuation 时显式 partial failure、禁止 whole-generation transparent replay，已经由 Spec 冻结。README 也明确把 block-level buffering 与 post-commit partial failure 列为“不应重新投票”的输入约束，并在最小问题之后再次说明不需要重裁 post-commit retry。

**证据或失败场景**：

- `spec.md:263-269` 已冻结首个完整 block、`message_start`、success headers 与 terminal batch 的可观察提交规则；`spec.md:291` 再次要求完整 block envelope 预构造后按序提交。
- `spec.md:322-335` 已冻结 pre-commit retry 与 post-commit partial failure 边界；`spec.md:517,527` 明确基础行为固定为 partial failure，安全 continuation 需要独立合同与 PoC。
- `README.md:213-226` 把上述行为列入已裁决或由正式 Spec 冻结的输入；`README.md:269` 又明确说当前不需要重裁 post-commit retry。
- 若用户在当前 Architecture 中“拒绝 ADR-BRIDGE-02”，无法判断是在拒绝已冻结的完整 block／SSE 行为，还是只拒绝某个尚未被单独命名的 sink 内部边界。若用户“拒绝 ADR-BRIDGE-05”，同样无法判断是在非法重开 partial-failure 行为，还是只拒绝预留 typed continuation action／ledger interface。该裁决无法被忠实记录或执行。

**修复建议**：把 ADR-BRIDGE-02 和 ADR-BRIDGE-05 中已由 Spec 冻结的部分移入“已决约束的架构承载记录”。如果确有仍需用户选择的内部结构，例如“完整 batch 是否恰好等于一次 sink API 调用”或“首版是否预留 typed continuation port”，应拆成独立、明确不改变 Spec 的问题，并分别给出至少两个可选方案、代价、推荐和不采用理由；若没有真实分叉，就不要把它们保留为用户投票项。

### [major] `README.md:228-269`、`architecture.md:532-552` — ADR-BRIDGE-01／02／05 不是完整且可追踪的待裁决集合

**问题**：README 明确要求用户另行裁决“迁移落地边界”，并把多组详细内部合同列为仍待接受的架构提案；Architecture 的正式待裁决清单却只有三个短条目，既没有独立的迁移 ADR，也没有说明 ADR-BRIDGE-01 是否打包承载所有详细 owner／facts／frontier／History 合同。因而“仅 ADR-BRIDGE-01／02／05”既漏掉 README 明示的迁移选择，也缺少从详细提案到 ADR 的可追踪映射。

**证据或失败场景**：

- `README.md:228-244` 列出统一 `PolicyOutcome`、typed fact records、transport cleanup、`AnthropicBlockKey`、commit sequencer、delayed response-start、single sink、`DeliveryFrontier`、History projection 与 durability receipt 等仍待用户接受的提案。
- `README.md:252-261` 将这些详细边界打包进“目标架构选择”；`README.md:263-267` 又提出“完整骨架一次建立”与“分阶段建立 B、局部 A 形 adapter 过渡”的独立迁移选择。
- `architecture.md:536-540` 的 ADR-BRIDGE-01 只写 canonical model、方案 B 与方案 A 迁移兼容形态，没有声明接受该 ADR 是否等于接受上述所有详细合同，也没有呈现“完整骨架一次建立”这一迁移方案及其权衡。
- 用户若只回答 Architecture 的三个 ADR，无法填写 README 的第二个问题应落在哪个决策记录；反过来，用户若按 README 接受“方案 B 整体边界”，又无法知道是否仍可单独修改 transport cleanup 或 History receipt ownership。这会导致 ADR 记录粒度与用户真实意图不一致。

**修复建议**：建立唯一的裁决矩阵，逐项列出“问题 ID／已决输入／可选方案／权衡／推荐／被推荐方案明确包含的详细合同／可单独修改的边界／最终 ADR 归属”。迁移节奏应成为独立 ADR，或明确成为 ADR-BRIDGE-01 的一个具名子决策；两种情况下都要在 Architecture 正文中比较“一次建立完整骨架”与“分阶段建立 B”的实施风险、兼容代价、退出条件和 route 接线前置门。对于打包进 ADR-BRIDGE-01 的详细合同，应明确哪些不可拆分、哪些可由用户逐项修改。

### [minor] `README.md:142`、`architecture.md:507,532` — 文件链接有效，但 Architecture 章节导航不是精确链接且文字已漂移

**问题**：README 的五个 Markdown 文件目标均可解析，但 Architecture 导航行仍写“待主会话确认的架构决策草案”与“ADR-BRIDGE-01～06”。当前真实标题是“待用户确认的内部架构决策（仅 ADR-BRIDGE-01／02／05）”，ADR-BRIDGE-03／04／06 位于前一个“已决约束的架构承载记录”章节。README 也只链接到文件，没有把这两个相邻且语义相反的章节精确链接出来。

**证据或失败场景**：用户按 README 的章节名在 Architecture 中检索会得到零个精确标题命中；按“ADR-BRIDGE-01～06”理解则会把已决承载记录与待裁决问题重新混为一组。由于 README 同时强制全文阅读，这一问题不至于单独阻断理解，但会放大前述分类歧义。

**修复建议**：把导航文字更新为当前真实标题和范围，并分别增加指向“已决约束的架构承载记录”与“待用户确认的内部架构决策”的稳定章节链接。若标题会继续调整，优先使用显式稳定 anchor，避免依赖自动生成的中文 heading slug。

## 每项裁决材料充足度

| 当前条目 | 方案 | 权衡 | 推荐 | 核对结论 |
|---|---|---|---|---|
| ADR-BRIDGE-01 | Architecture 的 A／B／C 比较提供了真实替代方案 | A／B／C 的可行性、长期代价、single-owner 与演进影响较完整 | 明确推荐 B，A 作为迁移形态，C 拒绝 | **主体材料足够，但接受范围不清。** 必须补齐详细合同与 ADR-BRIDGE-01 的归属映射，以及迁移节奏是否属于本 ADR |
| ADR-BRIDGE-02 | 待裁决小节只给一个建议，没有独立替代方案 | 只给兼容性理由和“不声称”边界，没有比较其他内部 framing／sink 组织方案 | 有推荐 | **不具备独立裁决条件。** 更根本的问题是核心行为已由 Spec 冻结；应先重分类，再判断是否还存在内部架构分叉 |
| ADR-BRIDGE-05 | 待裁决小节只给基础 partial-failure 建议和未来扩展点 | 解释了 full retry 与 prompt continuation 的风险，但没有比较“首版预留 typed port”与“待独立 continuation ADR 后再引入”等内部方案 | 有推荐 | **不具备独立裁决条件。** 基础行为已冻结；若真正待决的是扩展点形态，应拆题并补方案与代价 |
| README 的迁移落地边界 | README 提出“一次完整骨架”与“分阶段建立 B”两条路径 | Architecture 的 A／B 材料可提供部分背景，但没有围绕迁移节奏做直接对比 | README 推荐分阶段建立 B 并设退出条件 | **尚未形成 Architecture 内可追踪的裁决条目。** 需要独立 ADR 或 ADR-BRIDGE-01 子决策及直接权衡 |

## 主观建议

未提出独立主观建议。上述问题均直接影响用户能否知道自己在裁决什么、裁决结果如何落入 ADR，属于事实性可执行缺陷。

## 结论

当前 Architecture 对方案 B 的主体论证足以支持继续讨论，README 的五个文件链接也全部可达；但待裁决集合的分类、完整性和 ADR 归属仍不满足最终用户裁决条件。应先关闭两项 major：第一，剥离 ADR-BRIDGE-02／05 中已经冻结的行为；第二，把迁移节奏和详细内部合同映射到唯一、完整的裁决矩阵。完成后再复核 README 的精确章节链接。只有复评达到 `0 major`，才可明确通知用户从 README 开始完整阅读五份文档并作最终裁决。
