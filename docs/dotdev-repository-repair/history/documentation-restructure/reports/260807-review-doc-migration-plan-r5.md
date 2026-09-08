# 文档重组计划独立定向复评 R5

## 评审摘要

- **评审范围**：current `docs/agents/documentation-restructure/plan.md`，SHA-256 `b3235905bb824d6d6acc272dae1eaf61724a5c71b49818ef107f1f6d9ef8ccab`，分支 `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`。本轮只复核 R4 的两项 major：规范输入内容身份绑定及 Acceptance→Spec 关系；`docs/tmp` 归纳的机械截止点是否覆盖文档提交、阶段推进、产品回放、archive 清理与用户裁决，且不把临时报告变成永久权威。同时确认原 42 项 source owner、派生产物 producer 与 literal pathspec 契约未被破坏；未重新评审其他计划内容或 42 份源文档正文。
- **总体 verdict**：**修复 major 后可进入；当前计划不可提交执行。** current plan 的内容哈希与 R4 评审绑定的哈希完全相同，R4 两项 major 均未进入当前文件；原 42 项 owner／producer／pathspec 契约保持。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：先后两次独立读取 current plan，SHA-256 均为 `b3235905bb824d6d6acc272dae1eaf61724a5c71b49818ef107f1f6d9ef8ccab`；该值与 R4 明示的评审对象哈希一致。对照 current bridge Spec 与 Acceptance，Spec SHA-256 为 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，Acceptance 当前确实绑定该 Spec hash 且状态为 `FINALIZED_ACCEPTANCE_ORACLE`，但 plan 不记录或校验这组三元关系。扫描 plan 第 2.5、5.4、6.3、阶段 0、阶段 1、kick-off 与处置表；第 2.5 节未定义文档提交、阶段推进、产品回放、archive 清理或用户裁决五类机械截止点。另以 `Path.rglob('*.md')` 和 `git ls-files docs/2604-rewrite` 两种原理交叉枚举，均为 42 个源且集合相等；第 5.4 节解析出 42 个唯一 source、42 个唯一 canonical destination，全部 `extract phase ≤ final move phase`。
- **双视角覆盖证据——第一人称执行模拟**：模拟阶段 0 冻结 manifest 后暂停、bridge Spec 或 Acceptance 在阶段 1 前变化、Acceptance hash 与 Spec hash 失配、Acceptance 状态退回 `UNVERIFIED` 的四条路径；现有计划仍可按相同文件路径继续消费。再模拟临时报告改变 gate 后依次进入文档提交、下一阶段、产品实现／验收回放、archive 清理和采用用户裁决五条路径；执行者只登记“部分覆盖／待覆盖”仍能继续。最后模拟阶段 1 三份派生 spec 的生产、源提炼、移动与提交，三者的 producer、source input、literal pathspec、唯一 final owner 及禁止进入阶段 2～11 pathspec 的约束均闭合。

## R4 major 复核

### 事实性发现

[major] `docs/agents/documentation-restructure/plan.md:235,288-294,319-339,618` — 规范输入仍只绑定路径与优先级，没有绑定内容身份，也没有表达 Acceptance 从属于 Spec 行为 oracle 的机械关系 — current Spec／Acceptance 在本次复核时恰好有效，不等于执行协议能保持有效：Acceptance 自身明确绑定 Spec SHA-256，并规定 Spec 内容变化后相关 gate 回到 `UNVERIFIED`、必须重做七域 policy 对账；plan 却既不要求 manifest 记录 Spec SHA-256、Acceptance SHA-256、Acceptance 内绑定的 Spec SHA-256和 `FINALIZED_ACCEPTANCE_ORACLE` 状态，也不在阶段 0 与阶段 1 消费前检查四者。执行者可在路径不变而内容漂移、绑定失配或 Acceptance 失效时继续生产，owner／producer／pathspec 与历史输入优先级检查仍会全绿。plan 还把 Spec 与 Acceptance 并列称为“规范输入”，未机械约束“行为 expected 来自 Spec，Acceptance 只冻结与该 Spec 内容版本绑定的 required gates；Acceptance 不得成为第二份或反向覆盖 Spec 的行为 oracle” — 在 manifest 为两份输入分别冻结内容 SHA-256，解析并校验 Acceptance 内绑定的 Spec SHA-256及状态；阶段 0 提交前和阶段 1 每次消费／提交前都要求实际 Spec hash、实际 Acceptance hash、Acceptance 绑定 hash 与 finalized 状态精确一致。任一变化都阻断受影响切片，先完成规范对账、独立复评并以独立 verification 资产提交新的冻结身份。双向 fixtures 至少覆盖：完整有效四元组为绿；Spec 漂移、Acceptance 漂移、Acceptance→Spec hash 失配、非 finalized 状态分别为红；仅刷新绑定 hash 而未重做 policy 对账不得自动变绿。

[major] `docs/agents/documentation-restructure/plan.md:68-70,630` — `docs/tmp` 归纳仍没有覆盖五类动作的机械截止点，“部分覆盖／待覆盖”仍可成为无限期通行证 — 当前条款只要求“及时”归纳并登记覆盖状态，未规定何时必须达到“已覆盖”，也未要求 checker 阻断依赖该结论的动作。第一人称执行时，执行者可把改变合同、实现状态、验收 verdict、下一动作、gate 或用户裁决的报告登记为“待覆盖”，随后提交依赖它的文档、推进阶段、回放产品实现／验收、清理或归档临时证据、采用用户裁决；形式上仍满足第 2.5 节，临时报告便成为这些动作唯一可依赖的实际权威 — 把归纳截止点冻结为可检查规则：任何受临时结论影响的文档提交前、下一相关阶段开始前、产品实现／验收／回放采用该结论前、对应报告被 archive／清理／删除前，以及用户裁决被后续动作采用前，正式状态文档必须已经承载完整结论和来源，受影响项必须为“已覆盖”。“部分覆盖／待覆盖”只能作为短暂登记，必须逐项列出未覆盖内容、正式 owner、受影响范围与阻断截止点，并让 checker 对该范围内动作返回非零。正式文档应保存结论、裁决与可追溯 provenance；`docs/tmp` 只保留临时证据身份，不进入长期引用链，也不能作为 checker 允许推进的权威来源。双向 fixtures 至少覆盖五类截止点各一条正确样本与“只登记待覆盖便继续”的错误样本，并验证历史旧报告不会被错误追溯阻断。

## 原 42 项契约回归核对

| 核对项 | 结论 | 证据 |
|---|---|---|
| 42 个迁移源集合 | **保持** | `Path.rglob('*.md')` 与 `git ls-files docs/2604-rewrite` 均得到 42 个源，集合双向相等；第 5.4 节表亦为 42 行。 |
| source owner／destination | **保持** | 42 个 source 与 42 个 canonical destination 分别唯一；每项只有一个整数 `final move phase`，且所有 `extract phase ≤ final move phase`。 |
| required output producer gate | **保持** | `plan.md:235,288,293,296` 继续要求第 5.1～5.3 节全部派生产物具备唯一 producer、完整 source inputs 与 producer-stage pathspec，并保留漏项、重复、晚生产和漏 pathspec 的反 fixtures。 |
| 三份阶段 1 spec | **保持** | `plan.md:312-318,341` 的三条 producer／source input／literal pathspec／final owner 四元组与 R4 一致，均固定为阶段 1，并明确不得进入阶段 2～11 pathspec。 |
| 阶段 staged path | **保持** | `plan.md:263-269,296,618` 继续要求 staged paths 与已提交 phase pathspec 精确相等，排除 `docs/tmp/**`、既有脏项和非本阶段文件。 |

## 主观建议

无。

## 结构怪味复核

- `plan.md:235,288-294` — **路径身份冒充内容身份，且行为 oracle 与验收 oracle 层级未编码** — 本轮仍须修复。
- `plan.md:68-70,630` — **不可执行的时间词与可无限延期的自报状态** — 本轮仍须修复。
- 本轮定向扫描未发现原 42 项 owner／producer／pathspec 契约的新结构退化。

## 结论

当前为 **0 blocker、2 major、0 minor**。由于 R4 两项 major 仍存在，不能宣告“计划可提交执行”。planner 需先把规范输入内容身份与 Acceptance→Spec 绑定关系接入阶段 0／1 gate，并为 `docs/tmp` 归纳建立覆盖文档提交、阶段推进、产品回放、archive 清理和用户裁决的机械截止点；定向复评达到 **0 blocker、0 major** 后，应明确将总体 verdict 更新为“可进入下一阶段；计划可提交执行”。
