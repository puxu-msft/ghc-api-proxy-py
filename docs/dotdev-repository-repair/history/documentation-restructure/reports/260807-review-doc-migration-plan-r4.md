# 文档重组计划独立终审 R4

## 评审摘要

- **评审范围**：current `docs/agents/documentation-restructure/plan.md`，SHA-256 `b3235905bb824d6d6acc272dae1eaf61724a5c71b49818ef107f1f6d9ef8ccab`，分支 `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`。本轮消费 R3 的 0 blocker／0 major 结论，定向终审其后加入或强化的 `docs/tmp` 实际日期命名与及时归纳、bridge 冻结合同规范输入、派生产物 producer／pathspec，以及这些改动是否继续保持三层目录裁决、渐进迁移不抢产品主线和 42 源唯一 owner；未重新评审 42 份源文档正文。
- **总体 verdict**：**修复 major 后可进入；当前计划不可提交执行。** 三层目录、渐进停靠、42 源唯一 owner、阶段 1 producer／pathspec 和 bridge 六轴的文字合同均保持，但规范输入版本未冻结、临时报告“及时归纳”没有可阻断的时限／触发点，两条路径都可在形式检查全绿时产生错误执行。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：全文通读 current plan 与 R3 报告；逐项扫描第 2.1、2.2、2.3、2.5、5.4、6、7、9.1、11、12 节；把第 5.4 节映射表与 `Path.rglob('*.md')`、`git ls-files docs/2604-rewrite` 两种枚举交叉对账，结果均为 42 个源、42 个唯一 source、42 个唯一 canonical destination，集合双向相等；逐行核对阶段 1 三份 spec 的 producer phase、source extract input、literal stage pathspec 与 final owner 均为阶段 1；对照 current bridge Spec 与 Acceptance，确认 semantic block、pre-commit／post-commit frontier、memory-only／no spill／无 16 MiB 特例、SSE delayed-start、cancel／cleanup 和 History 时点在计划中仍标为冻结合同。
- **双视角覆盖证据——第一人称执行模拟**：模拟阶段 0 生成 manifest、提交验证资产、暂停后再执行阶段 1，并分别走了产品紧急工作插入、旧源按唯一 final owner 移动、三份派生 spec 进入且只进入 `phase-1-pathspec.txt`、历史输入与规范输入冲突、规范输入在两阶段之间变化、以及新临时报告先登记“待覆盖”后继续下一动作的路径。前四类流程有明确 owner／pathspec／优先级 gate；后两类仍能绕过计划目标，形成以下 major。

## 已保持的不变量

| 核对项 | 结论 | 证据 |
|---|---|---|
| 三层目录裁决 | **保持** | `plan.md:29-35` 继续把 `docs/`、`docs/agents/<topic>/`、`archive-<date>/` 分别限定为活文档、开发文档和归档文档；kick-off 在 `plan.md:618` 再次原样约束。 |
| 渐进迁移不抢主线 | **保持** | `plan.md:23,48,239,562,618` 要求独立可停靠提交、产品工作可插入、阶段 1 后暂停并交回主会话。 |
| 42 源唯一 owner | **保持** | 第 5.4 节机器解析为 42 行、source 与 destination 各自唯一；表集合与文件系统、Git 枚举双向相等；`plan.md:235` 要求 checker 固化相同不变量。 |
| 阶段 1 producer／pathspec | **保持** | `plan.md:312-318,341` 对三份 spec 逐条冻结 producer、输入、literal pathspec 与 final owner，并要求仅进入 `phase-1-pathspec.txt`。 |
| bridge 已决合同不重开 | **文字语义保持，但版本门存在 major** | `plan.md:60,288-294,320-341,585-599,618` 与 current Spec／Acceptance 的六轴一致；问题不是合同内容被改写，而是执行时没有机械证明消费的仍是这组已接受内容版本。 |
| `YYMMDD` 命名 | **保持** | `plan.md:68-69` 明确实际创建日、同日轮次／性质后缀、禁止覆盖及旧报告单一身份。 |

## 事实性发现

[major] `docs/agents/documentation-restructure/plan.md:235,288-294,320-341` — `normative_inputs` 只记录路径和优先级，没有冻结内容 SHA-256、Acceptance 对 Spec 的绑定关系或 `FINALIZED_ACCEPTANCE_ORACLE` 状态 — 第一人称执行时，阶段 0 可以为两个 current bridge 文件登记路径并提交 manifest；暂停期间任一文件发生内容变化，阶段 1 仍可按同一路径“只读消费”，而现有 checker 要求只证明输出服从当前路径内容。此时历史素材没有覆盖规范输入，producer／pathspec 也全绿，但消费的可能已不是独立评审接受的合同对。current Acceptance 自身在 `acceptance.md:5,29,61` 明确要求 Spec hash 变化后相关 gate 回到 `UNVERIFIED`，计划却没有把这一失效条件接入阶段 0／1 gate — 在 manifest 为每个规范输入记录内容 SHA-256、规范状态及 Acceptance 内绑定的 Spec SHA-256；阶段 0 和阶段 1 开始前都要求三者一致且 Acceptance 为 finalized。若任一内容变化，应阻断本切片，先完成规范对账／复评并用独立验证资产提交更新 manifest。增加正确绑定为绿、Spec 改变但 Acceptance 未更新为红、Acceptance 仅刷新 hash 未重做对账仍为红的双向 fixtures。

[major] `docs/agents/documentation-restructure/plan.md:68-70,630` — “及时归纳”允许正式状态记录为“待覆盖”，却没有定义最迟触发点、阻断动作或可执行 checker，因此验收可在结论尚未归纳时形式通过 — 执行者可新建一份改变合同、验收 gate 或下一动作的报告，只在正式状态文档登记“报告 → 落点 → 待覆盖”，随后继续使用旧合同执行下一阶段；这满足当前列出的最低记录字段，也没有违反任何 staged path gate，却让 `docs/tmp/` 实际成为临时权威且“待覆盖”可无限存续。`plan.md:630` 的验收也只要求能找到覆盖状态，没有要求受影响动作在“已覆盖”前停止 — 把“及时”冻结为机械触发规则：任何改变合同、实现状态、验收 verdict、下一动作或 gate 的新报告，必须在受影响决策被采用、下一相关切片开始或提交之前归纳；“部分覆盖／待覆盖”必须列出未覆盖项、正式 owner 与阻断触发点，并阻断其影响范围内的下一动作。阶段 0 应提供基于规则生效日期／登记表的正反 fixtures，确保历史旧报告不 false-red，同时让“只登记待覆盖便继续”“报告影响 gate 但未登记”“部分覆盖遗漏剩余项”分别变红。

## 主观建议

无。

## 结构怪味复核

- `plan.md:235,288-294` — **路径身份冒充内容身份** — 本轮应修；规范输入是跨暂停边界的行为 oracle，仅记录路径无法证明还是同一已接受版本。
- `plan.md:68-70,630` — **不可执行的时间词／自报状态门** — 本轮应修；“及时”和“待覆盖”若没有外部触发点，checker 无法区分正常短暂过渡与无限拖延。
- 扫描范围：current plan 的新增治理条款、阶段 0／1 执行协议、owner／pathspec 表、bridge 规范输入链及 R3 关闭项；未重新扫描 42 份源文档正文。本轮未发现除此两处外的新结构怪味。

## 结论

当前为 **0 blocker、2 major、0 minor**，不能按用户要求宣告“计划可提交执行”。修复两条 major 后需定向复评：一条验证规范输入内容版本和 finalized 绑定在阶段 0／1 均不可漂移，另一条验证临时报告在影响后续动作前必须归纳且“待覆盖”不能成为永久通行证。其余六项定向不变量已保持，无需重做 42 份源文档内容评审。
