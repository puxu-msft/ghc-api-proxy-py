# Anthropic Messages ↔ OpenAI Responses bridge 阅读索引

## 阅读约定

本目录包含行为规格、证据研究、目标架构、验收规范和实施状态五类不同权威层级的文档。它们不能互相替代，也不能把“独立评审没有 blocker／major”自动解释成“用户已经接受”或“实现已经完成”。

**架构裁决前必须完整阅读本索引列出的五份文档，尤其必须从头到尾完整阅读 [architecture.md](architecture.md)。** 本索引只提供阅读顺序、章节定位、权威边界和待裁决问题，不摘要替代原文，也不邀请用户在只看推荐结论或 A／B／C 对比表后直接接受方案。

不要按预计时长取舍文档。本索引不提供阅读时长，因为没有实测依据，而且架构裁决所需的是完整理解，不是按时间预算截断阅读。

## 权威边界

| 文档 | 权威角色 | 可以决定什么 | 不能决定什么 |
|---|---|---|---|
| [spec.md](spec.md) | **唯一行为 oracle** | 用户可观察行为、兼容政策、字段处置、路由、buffering、retry、usage、error、lifecycle 与非功能不变量 | 不能证明实现已经完成，也不自动接受某套内部架构 |
| [acceptance.md](acceptance.md) | **验收 oracle** | 如何把 Spec 转成可执行 gate、正反控制、证据层级和最终 PASS／BLOCKED／UNVERIFIED 判定 | 不能新增 Spec 未定义的 expected，不能用 Architecture 提案补行为政策，也不能把“规范已写”当成“候选实现已通过” |
| [architecture.md](architecture.md) | **非规范架构提案** | 提议内部组件边界、owner、typed facts、transport／converter／assembler／sink／History 协作方式，以及 A／B／C 方案取舍 | 未经用户接受前不是 ADR，不能覆盖 Spec，不能产生新的行为 expected；独立评审通过只说明提案达到可讨论质量，不等于用户裁决 |
| [research.md](research.md) | 可追溯证据与方案来源 | 说明参考实现、固定 commit、可移植机制、反例、不可照搬项和 upstream 同步方法 | 不是行为或验收 oracle，不能把参考项目的默认值或缺陷提升为本项目合同 |
| [implementation.md](implementation.md) | **易变实施状态的真相源** | 当前 `main`、候选／integration HEAD、切片是否进入主线、评审门、组合顺序、清理与归档条件、下一动作 | 不能改写 Spec／Acceptance／Architecture 的权威角色，也不能用候选分支测试替代最终主线或整桥验收 |

发生冲突时按以下方式处理：行为 expected 回到 `spec.md`；验收方式回到 `acceptance.md`；是否接受内部架构由用户在完整阅读 `architecture.md` 后裁决；候选代码、分支和下一动作等易变状态以 `implementation.md` 的最新修订为准；参考实现事实回到 `research.md` 的固定来源。若 `implementation.md` 对其他文档状态的转述与对应文档当前状态头不一致，应先同步 `implementation.md`，不得让转述覆盖源文档。

## 当前快照

本节只是 2026-08-07 的导航快照，不是长期状态源。

- 主仓：`/home/xp/src/ghc-api-proxy-py`。
- 当前分支与 HEAD：`main`，`ec5e8f5240c6a587544e022b449aa7b392ba7ca1`。本快照写入时，`README.md` 已加入 index，`implementation.md` 同时存在已暂存与未暂存修改；其余四份源文档在主树工作区相对 index 无修改。不要把工作区状态或本导航快照冒充长期状态源。
- `spec.md` 当前 SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，自身状态为 `FINALIZED`；这表示行为规格已定稿，不表示 bridge 已实现。
- `research.md` 继续只提供可追溯证据、来源与反例；其权威边界和阅读位置不变。
- `architecture.md` 当前 SHA-256 为 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`，仍是“非规范架构提案，尚未获用户接受”。其裁决矩阵终审为 blocker 0、major 0；当前门是用户按本索引完整阅读五份文档，尤其完整阅读 Architecture 后，分别裁决 `D-ARCH` 与 `D-MIGRATION`。终审通过不等于用户接受。
- `acceptance.md` 当前 SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`，自身状态为 `FINALIZED_ACCEPTANCE_ORACLE`；候选产品及完整 bridge verdict 仍为 `UNVERIFIED`，required gates 尚未对完整 bridge 候选执行。
- `implementation.md` 是 Implementation living 入口，持续记录 current `main`、候选／integration identities、评审门、组合顺序与下一动作；它不会因某个 checkpoint 通过而收口。操作前必须重新 gate 其中的易变事实，其跨文档转述若落后于源文档，应以源文档自身状态为准。
- Foundations integration `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 与 happy-path integration `integrate/260807-bridge-happy-path@d78b3cdc172ecad42873a70f1df31438ecca1663` 均已有独立本地载体，但都尚未进入 `main`。任何 integration 侧 review、verification 或 smoke 只覆盖其声明范围，不能外推为完整 bridge 产品 `PASS`。

## 推荐阅读顺序

以下顺序是为了先确定“必须实现什么”，再理解证据与方案，最后检查验收和真实进度。每一份都要求完整阅读。

1. **完整阅读 [spec.md](spec.md)**：建立唯一行为合同，先分清不可重开的裁决、冻结基础行为和低概率扩展。
2. **完整阅读 [research.md](research.md)**：理解方案来源、参考实现的可移植机制和已知反例，避免把 Architecture 的推荐当成凭空设计或把 upstream 整体照搬。
3. **完整阅读 [architecture.md](architecture.md)**：比较 A／B／C，检查推荐方案 B 的内部 owner、typed facts、delivery frontier、History 与迁移代价。**未读完本文件不得作架构裁决。**
4. **完整阅读 [acceptance.md](acceptance.md)**：确认任何架构方案最终如何被独立、可证伪地验证，以及哪些证据仍缺失。
5. **完整阅读 [implementation.md](implementation.md)**：最后核对当前 `main`、候选分支、组合顺序、尚未进入主线的切片和下一动作，避免把设计状态误认成落地状态。

如果架构文档在阅读期间有修改，应重新阅读所有受影响章节，并回看 Spec 与 Acceptance 的权威边界；不能沿用修改前的接受意见。

## `spec.md`：唯一行为 oracle

### 预计用途

用它回答“bridge 对客户端、上游、生命周期和资源管理必须表现成什么”。实施、架构与验收中任何 policy-dependent expected 都必须能回指本文件。

### 章节导航与关键问题

| 章节 | 阅读重点 | 关键问题 |
|---|---|---|
| “文档状态”“问题与意图”“目标”“范围边界” | 定稿状态、direct bridge 意图、single owner、包含与排除范围 | 目标是否仍由 Anthropic pipeline 拥有完整生命周期？Chat Completions 是否被明确排除为中间表示？ |
| “术语”“总体架构契约” | canonical request、semantic block、block envelope、commit frontier、attempt-local state | 哪些状态可以在 retry 时丢弃，哪些下游事实一旦提交就不可重写？ |
| “Route selection 与 model capability 契约” | resolved model、override precedence、双支持默认 Messages、unknown fail closed、protocol leg 与 physical transport 正交 | 路由是否只在一个接缝决定？显式 override 不可用时是否禁止静默 fall through？ |
| “Request conversion 契约”“双向字段处置矩阵” | system、content、tool、reasoning、metadata、unknown 字段的 `PRESERVE`／`TRANSFORM`／`REJECT`／`DEGRADE` | 每个字段是否有唯一冻结处置？是否存在 silent drop、顺序重排或伪造 id 的空间？ |
| “Reasoning 与 signature 契约” | 固定 upstream v1 carrier、legacy／foreign／malformed 边界、一 reasoning item 一 thinking block、encrypted-only no-loss | Wire compatibility 与目标语义是否被分开？是否错误复制 upstream 的有损聚合？ |
| “Response conversion 契约”“Non-stream contract” | text／refusal／tool／reasoning、terminal、stop reason、non-stream 原子提交 | 完整 body 通过转换、hook 和 limits 前是否保持未提交？unknown item 是否显式失败？ |
| “SSE／WS envelope 契约”“Block-level buffering 与 commit 契约” | 首 block 前零 success headers／body、完整 block batch、HTTP SSE 与 WS 共享语义核心 | 下游最小可见单元是否始终是完整 Anthropic content block？上游增量读取是否被误解成下游 live streaming？ |
| “Retry ownership 与 delivery semantics”“Ordering、no duplication、no loss 契约” | application pipeline 唯一 retry owner、pre-commit retry、post-commit partial failure、ledger | 失败 attempt 是否完全隔离？commit 后是否禁止 whole-generation replay？ |
| “Usage 契约”“Error 契约”“Header 契约” | 冻结算式、错误归一、commit 前后错误差异、允许下发的 headers | reasoning token 是否被重复计数？错误是否可能被伪装成成功 terminal？ |
| “Approval、hooks、History 与 tokenization 契约” | exactly-once approval／finalize、每 attempt `PRE_SEND`、单 History entry、Anthropic count contract | Responses leg 是否可能创建第二个生命周期 owner？hook 是否仍看到 Anthropic 语义？ |
| “Shutdown、cancel、backpressure 与 limits 契约” | memory-only、per-request aggregate、global reservation、有限队列、cancel／shutdown cleanup | 容量压力是否可能触发 spill、partial flush 或 live forwarding？所有 charge／release 是否有 owner？ |
| “Compatibility 契约”“非功能要求” | direct Messages 不回归、strict unknown、correctness、resource safety、observability、maintainability、performance | 内部优化是否会放宽行为合同？非功能要求是否在实施前置而不是事后补做？ |
| “验收行为” | 外部可观察的规格级接受条件 | 每条行为能否映射到 Acceptance gate，而不是只映射到内部 helper 测试？ |
| “已冻结决策与残余分叉” | 不得重开的轴、四个低概率扩展、continuation 扩展边界 | 当前是否真的需要重裁扩展，还是已有明确基础行为足以实施？ |
| “已排除或暂不采纳的方案” | 第二 pipeline、两跳 bridge、raw passthrough、whole-response-only、overflow-to-live 等反例 | Architecture 或实施计划是否重新引入了已排除路径？ |
| “当前基线事实与证据”“结论”“评审处置表” | 当前 main 的已落地 primitive、forward cardinality 缺口、M1～M6／R2／R3 的关闭边界 | 哪些只是实现基础，哪些仍是开放缺口？规格评审通过是否被错误写成实现通过？ |

### 读完后应能回答

- 哪些行为不可由 Architecture 或实现者重新选择？
- 哪些低概率扩展有冻结基础行为，因此不阻断实现？
- 什么事件真正关闭 transparent retry 窗口？
- 为什么 carrier byte compatibility 不允许保留当前有损 forward 聚合？

## `research.md`：证据、来源与反例

### 预计用途

用它回答“为什么选这些机制、参考实现实际做了什么、哪些做法不能照搬”。它为 Spec 与 Architecture 提供 provenance，但不产生新的行为合同。

### 章节导航与关键问题

| 章节 | 阅读重点 | 关键问题 |
|---|---|---|
| “Verdict”“目标项目约束” | 可进入设计但不可整体照搬；四项用户直接裁决 | 哪些结论来自用户裁决，哪些来自参考仓源码？两者是否被混写？ |
| “证据口径” | 已独立核验、仅 agent 报告、未运行验证；固定 repo＋HEAD | 每项结论的证据等级是什么？是否把测试源码存在误写成测试已通过？ |
| “目标仓当前事实与能力缺口” | 当前 Anthropic／Responses raw passthrough、buffering primitive、retry owner、server-tool 边界 | 目标仓已经具备哪些基座，完整 bridge 还缺哪些生产接缝？ |
| “主 upstream 机制” | 路由、direct bridge、request／response translator、reasoning carrier、stream parser、commit ledger、terminal repair、delivery owner | 哪些机制可移植？哪些 upstream 缺陷必须明确反向测试？ |
| “异构参考交叉结论” | TypeScript、Go、.NET 等参考的共同模式和局部缺陷 | 是否有独立来源支持某个架构模式？是否存在只由 agent 报告、尚待核验的说法？ |
| “可移植能力矩阵” | 每项能力的采用方向、依据和迁移约束 | Architecture 是否保留了矩阵中的约束，而不只是采用模块名称？ |
| “后续规格必须冻结的合同” | 当时要求 Spec 覆盖的路由、字段矩阵、frontier、资源、History、兼容性 | 当前 Spec 是否已经逐项关闭这些问题？若已关闭，是否还被误列成待用户决定？ |
| “本轮评审处置” | file:line 修订、carrier／16 MiB 重裁、route scope 修复 | 后续文档是否沿用了被覆盖的旧结论？ |
| “持续同步 upstream 的方法” | 固定 baseline、watch list、四类 delta 判定、差分 oracle、provenance | 将来 upstream 前移时，如何防止工作树污染、只看 commit title 或无差别代码同步？ |
| “验证边界与下一步” | 静态研究已完成，运行与 live-wire 验证未完成 | 哪些事实仍需要 Acceptance 的真实入口和 fault injection 才能成立？ |

### 读完后应能回答

- 为什么 `copilot-api-js` 是主参考但不能成为整体实现 oracle？
- 哪些反例必须在目标实现中做正反控制，例如顺序重排、tool-name mapper 未接线、reasoning 聚合错配？
- 哪些 source claims 尚未独立闭环，不能进入架构定论？

## `architecture.md`：待用户接受的非规范提案

### 预计用途

用它回答“在不改变 Spec 行为的前提下，内部系统如何组织”。这是本轮真正需要用户裁决的主要文档，但**只能在全文阅读后裁决**。

### A／B／C 对比入口

从“候选架构比较”开始查看三个方案，再继续阅读后续全部章节验证比较表是否被详细设计支撑：

- **方案 A：Anthropic canonical pipeline＋Responses adapter。** 接线较小、接近现有 pipeline，适合作为受约束迁移形态；长期保留 wire-shaped mutable state、converter 漂移和隐式耦合风险。
- **方案 B：typed semantic kernel＋单一 driver＋protocol／transport legs。** 文档推荐的长期目标；以 typed facts 分开 policy、orchestration、conversion、transport、assembly、delivery 和 observation，成本是需要认真定义 semantic schema 与 legacy hook compatibility projection。
- **方案 C：Anthropic route 调用现有 OpenAI／Responses route pipeline。** 文档明确不采用；会制造双 approval／History／finalize owner，并破坏 attempt、cancel 和 frontier 的唯一所有权。

不能只阅读此对比入口或“最终推荐”后作决定。方案 B 是否成立，取决于“共享内部事实模型”到“History 与 observer”等详细章节是否完整、可实施且没有越过 Spec。

### 章节导航与关键问题

| 章节 | 阅读重点 | 关键问题 |
|---|---|---|
| 开头状态、已决合同与“Verdict” | 提案身份、推荐 B、已决产品边界 | 推荐是否被误写成 accepted ADR？哪些内容只是复述 Spec、不能重新裁决？ |
| “当前事实与不可破坏边界” | 生产现状、single owner、memory／retry／History 不变量 | 目标架构是否建立在真实代码接缝上？是否引入第二 lifecycle owner？ |
| “候选架构比较” | A／B／C 的可行性、长期代价和推荐 | A 是目标还是迁移形态？B 的新增复杂度是否由长期不变量支撑？C 是否与 Spec 直接冲突？ |
| “推荐目标架构”“单一 driver 的职责”“唯一策略 outcome 契约” | 组件图、driver action owner、`PolicyOutcome` 的 observation／action／effect 分离 | Policy 是否可能自己重试、写下游或 finalize？Driver 是否仍能读取完整领域事实？ |
| “共享内部事实模型” | Request／Route／Attempt／Conversion／Delivery／Terminal／History facts 的 owner 与真值时点 | 每类事实由谁写、何时成立、retry 时如何 reset？是否存在同一事实两份 owner？ |
| “Route policy 与 Responses transport” | protocol leg／physical transport 正交、统一 exchange port、cancellation-resilient cleanup | Transport 是否会静默 fallback 或重发？close failure 与 primary cancellation 如何同时保真？ |
| “Converter 边界” | inbound adapter、request codec、response normalizer、outbound renderer、hook compatibility | 非流与流是否共享语义 constructors？legacy Anthropic hook view 能否无损 round-trip？ |
| “Block assembler、buffer 与 sink” | `AnthropicBlockKey`、reasoning identity、commit sequencer、reservation、delayed response start、single sink | 一个 Responses item 多 content parts 是否被拆成多个目标 blocks？较晚 block 先完成时是否被正确阻塞？ |
| “Retry 与 delivery frontier” | headers／message_start／blocks／terminal 的 accepted／uncertain 状态、failure matrix、continuation 边界 | assembler complete 与 sink committed 是否被区分？write uncertainty 后是否禁止猜测重发？ |
| “History 与 observer” | request-local journal、immutable projection、History writer receipt、reservation ownership | `request.finalized` 与 durable receipt 是否由不同 owner 发布？默认 History 是否仍遵守既有精简裁决？ |
| “非流式路径” | 同一 normalizer／CompletedBlock、body commit frontier、response hook | 非流是否偷偷形成第二套 converter 或更弱的 retry 边界？ |
| “可证伪的架构判据” | 单 owner、每 attempt 转换、block withholding、reasoning、frontier、cleanup、History receipt 的正反控制 | 判据能否同时防 false-green 与 false-red？是否覆盖真实 route／sink 接缝？ |
| “结构怪味与目标处置” | 当前代码的 wire-shaped state、route delivery、HTTP／WS 分裂、History 时点 | 方案 B 是否确实修在共享基座，而不是只新增抽象层？ |
| “[已决 Spec 输入与历史 ADR 承载记录（非待裁决）](architecture.md#已决-spec-输入与历史-adr-承载记录非待裁决)” | ADR-BRIDGE-02～06 如何承载完整 block／SSE、capacity、unknown capability、post-commit failure 及综合 bridge 合同 | 是否把 Spec 已决行为误放回用户投票，或把非分叉实现建议升级为产品选择？ |
| “[唯一用户裁决矩阵](architecture.md#唯一用户裁决矩阵)” | 仅 `D-ARCH` 与 `D-MIGRATION`；B 的不可拆分核心、可局部调整边界、M1／M2 风险与退出条件 | 用户能否分别裁决目标架构和迁移节奏，同时不重开 Spec 或把独立终审当成接受？ |
| “评审问题处置表”“容量政策的当前边界” | 评审修订、用户 U1／U2 重裁、容量最小止血 | 独立评审关闭了哪些提案缺陷？评审通过是否被错误等同于用户接受？ |
| “最终推荐” | B 目标、A 迁移、C 拒绝的完整组合 | 用户是否接受整套 owner／facts／frontier／History 边界，还是需要指定修改？ |

### 阅读时必须保持的边界

- Architecture 中与 Spec 相同的 route、buffering、carrier、unknown capability、post-commit failure 等内容，是对已决行为的实现解释，不是新的投票项。
- `typed semantic kernel`、统一 `PolicyOutcome`、History durability receipt owner、具体 fact records 与迁移组织方式是提案内容；独立评审 0／0 不能替代用户接受。
- Architecture 的全部待决面已经收敛到 [`D-ARCH` 与 `D-MIGRATION` 两行矩阵](architecture.md#唯一用户裁决矩阵)。`ADR-BRIDGE-02`～`06` 位于[已决承载记录](architecture.md#已决-spec-输入与历史-adr-承载记录非待裁决)，不得作为隐藏附加投票项。
- Architecture 不能让 Acceptance 从 proposed internal type 推导新的 required behavior；Acceptance 只能从 Spec 取 expected。

## `acceptance.md`：验收 oracle

### 预计用途

用它回答“如何独立证明实现符合 Spec，以及证据不足时应判 `UNVERIFIED` 还是 `BLOCKED`”。它是执行验收的规范，不是候选实现通过报告。

### 章节导航与关键问题

| 章节 | 阅读重点 | 关键问题 |
|---|---|---|
| “状态与判定”“用户可观察合同” | `FINALIZED_ACCEPTANCE_ORACLE`、current Spec／Architecture hash 边界、产品 verdict | Oracle 定稿是否被误解为 bridge PASS？Architecture 是否只提供观测接缝而不生成 expected？ |
| “POLICY-MANIFEST-v1” | route／request／response／buffering／retry／lifecycle／limits 七域对账 | 每个 gate 是否明确回指 current Spec？Spec hash 改变后是否要求重做内容对账？ |
| “Gate 执行规则” | 正确样本＋单缺陷注入、独立 oracle、证据标签 | 绿测试是否有目标 mutation 证明判别力？expected 与 actual 是否来自独立来源？ |
| “请求与路由 gate” | REQ-01～06：route、wire、content、tools、reasoning、approval／attempt | 是否覆盖真实 pipeline 入口、exact carrier vectors、producer-only／consumer-only 变异和每 attempt 转换？ |
| “非流响应 gate” | NS-01～05：content、tools、reasoning、usage、HTTP error | encrypted-only、多 reasoning、malformed args、unknown item 与 response close 是否可证伪？ |
| “流式转换与 block buffering gate” | STR-01～05：strict SSE、完整 block 可见性、no-dup／loss／order、terminal、usage parity | 是否用真实 downstream 观测点，而不是内部 buffer 长度证明 withholding？ |
| “retry、failure frontier、cancel 与 backpressure gate” | REL-01～06：attempt reset、post-commit、delivery uncertainty、cancel、两级 reservation | partial write／RST 后代理认知与客户端实际 bytes 是否分别记录？是否同时防 global-only 和 single-block threshold 两种错误？ |
| “HTTP 与 WebSocket transport gate” | TR-HTTP／TR-WS／TR-PARITY | WS 是否只是 transport leg？HTTP／WS 是否共享语义和生命周期 owner？ |
| “History、hooks、approval 与 tokenization gate” | LIFE-01～04 | entry、approval、finalize、calibration 是否保持 single request contract？ |
| “真上游、capture corpus 与本地 fault 校准” | `LIVE-CANARY`／`CAPTURE-CORPUS`／`LOCAL-FAULT` 的证据分层 | 不可控真上游异常缺席时是否错误判实现失败？fake 是否由 SDK 前 raw provenance 校准？ |
| “CAL-04 Anthropic strict grammar oracle”“CAL-05 Anthropic 官方 SDK 兼容 oracle” | batch-aware strict grammar 与 SDK compatibility 分离 | SDK 宽松接受是否会覆盖严格 grammar 红灯？首 batch 与零 content terminal 是否禁止插入 `ping`？ |
| “自动化资产规划”“当前实现映射与尚未执行项” | 未来测试职责、路径只是规划、当前未执行范围 | 是否把规划中的 fixture／test 文件误写成已存在或已运行？ |
| “最终放行清单”“评审问题处置表” | PASS／BLOCKED／UNVERIFIED 规则和历轮问题关闭证据 | 最终报告是否逐 gate 给出 candidate commit、正反控制、live／corpus／fault provenance 和未验证项？ |

### 读完后应能回答

- 为什么“测试尚未运行”必须是 `UNVERIFIED`，而不是 PASS 或实现缺陷？
- 哪些 gate 必须走真实 ASGI／socket／WS 接缝，不能只测 converter helper？
- 哪些 required 证据目前仍未产生，因此完整 bridge 不能放行？
- 为什么 R7 的 blocker 0、major 0、minor 0只定稿验收 oracle，而不接受 `D-ARCH`／`D-MIGRATION`，也不把候选产品升级为 `PASS`？

## `implementation.md`：易变实施状态与收敛顺序

### 预计用途

用它回答“当前代码到底在哪里、哪些切片已评审但未进 `main`、组合时按什么顺序、何时可以清理 worktree／branch／archive”。每次准备实施、回并、清理或宣称完成前都应重读本文件并重新 gate 当前仓库。

### 章节导航与关键问题

| 章节 | 阅读重点 | 关键问题 |
|---|---|---|
| “文档状态”“评审 major 处置” | 快照日期、权威边界、主树 WIP、完整 foundations integration 载体、跨文档状态转述 | 哪些状态是 current source-of-truth，哪些只是滞后的跨文档转述？主树 WIP 是否阻止直接产品回放？ |
| “总体进度” | carrier baseline、三个 reviewed feature HEAD、`integrate/260806-bridge-foundations@6a00f6f…` 的三提交线性链、gate 与下一动作 | merged-state review／verification 是否被误写成“已进入 main”或完整产品 PASS？是否错误重建第二套 integration 链？ |
| “切片 1：Reasoning carrier 与 cardinality correction” | main baseline、archive、cardinality 候选、one-item-one-block 缺口 | 当前 main 的 codec／reverse primitive 与尚未进入 main 的 forward 修复是否被分开？ |
| “切片 2：Session liveness” | cancellation-resilient cleanup、primary／secondary failure、integration commit | integration commit 是否只作为组合载体而未冒充主线？cleanup 是否经 cancellation storm 验证？ |
| “切片 3：Request converter” | thinking capability、tool mapper、Node-compatible decode、unknown-field fail closed、与 cardinality 同文件冲突 | 组合时是否禁止整文件覆盖 `responses_reasoning.py`？request 的旧聚合 API 是否可能回归？ |
| “文档复评剩余项” | Spec／Architecture／Acceptance／Research／重组计划／本文的交叉状态 | 这些转述是否已同步到源文档当前状态？若没有，应先修状态源再继续后续动作。 |
| “Squash 与分支归档策略” | cardinality → liveness → request 顺序、main-side gate、immutable archive、feature 与共享 integration 清理条件 | 是否逐片保留 reviewed HEAD？是否在 request 尚未进入 main 时错误清理共享 integration 载体？ |
| “回滚” | 独立 squash commit 的逆序回退与 archive 不变性 | 回滚是否只改变 main，而不移动评审证据 ref？ |
| “下一步” | 文档收敛、三片组合、main 回放、archive／cleanup、merged-state review、Acceptance 执行 | 哪些步骤已经被后续文档修改覆盖？执行前是否重新核对 current main 与最新文档状态？ |
| “结构怪味登记” | cleanup owner、converter 集中边界、同文件双分支修改、oracle 冲突 | 组合评审是否覆盖这些高风险接缝，而不是只复跑各切片孤立测试？ |

### 当前仍未实现或未放行的内容

- 完整 Anthropic Messages → Responses upstream bridge 尚未在 `main` 落地；当前 Anthropic stream 仍不是目标 block-level semantic bridge。
- Reasoning cardinality correction、session liveness、request converter 已在 clean foundations integration `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 中按三个线性 squash commits 完成组合，并取得 merged-state 代码复评 blocker 0、major 0与范围内独立复验 `PASS`；它们当前仍未进入 `main`，integration 证据不能替代回放后的 main-side gate。
- Response normalizer、stream assembler、continuous-prefix sequencer、delayed response start、single sink／delivery frontier、完整 route policy 接线、HTTP／WS parity、History／hook／approval／tokenization 全桥接线与资源预算仍需要后续实现切片。
- Acceptance required gates、mutation controls、live canary、capture corpus 校准和 local fault suite 尚未对完整候选执行；产品 verdict 必须保持 `UNVERIFIED`。
- Architecture 尚未被用户接受为 ADR，因此不能据方案 B 的评审通过状态直接开始把全部内部合同当成既定事实。

## 已裁决、已评审提案与未实现状态

### 用户已经裁决或已由正式 Spec 冻结，不应在架构阅读后重新投票

以下轴应作为 Architecture 的输入约束，而不是待选项：

- Semantic block 与最小提交单元是一个 Anthropic content block；一个 Responses item 可以对应多个 Anthropic blocks。
- Block-level buffering 是基础能力；首个完整 block 前不暴露 success headers、`message_start` 或 body event；不提供 token／event 级 live downstream streaming。
- Buffer 与 carrier 是普通 memory-only 对象，服从 per-request aggregate、global reservation、有限队列、准入和 backpressure；不 spill，不 overflow-to-live，不建立 16 MiB 单 block 专属阈值或状态机。
- Anthropic bridge 无 override 且模型同时支持 Messages／Responses 时默认 Messages；Responses-only 走 Responses；unknown capability fail closed；protocol leg 与 physical transport 分开决定。
- Reasoning carrier 必须与固定 `copilot-api-js` v1 prefix＋unpadded base64url wire byte-compatible，不引入私有 HMAC／schema；同时保持一 reasoning item 一 thinking block和 non-empty encrypted-only no-loss。
- Client-executed function tools 是基础范围；Anthropic 原生 server／typed tools执行 no-revive并显式拒绝。启用 hosted server tools 是新的产品能力，不可由 converter mapping 偷渡。
- Post-commit 无已证明 continuation contract 时明确 partial failure；不得透明重放 whole generation。
- Spec 双向字段矩阵、usage 算式、error／header、approval／hooks／History／tokenization、cancel／shutdown与 strict unknown 行为均已冻结为基础合同。

其中前几项在文档中有明确用户 D1～D3、最新 carrier 重裁和 U1／U2 记录；其余项由已定稿 Spec 或既有产品合同冻结。Architecture 只能提出如何实现，不能通过新的内部结构重新选择行为。

### 仅通过独立评审、仍待用户接受的架构提案

Architecture 的详细提案不构成一串独立投票。它们只通过[唯一用户裁决矩阵](architecture.md#唯一用户裁决矩阵)归入两个待决项：

- `D-ARCH` 决定长期目标选择 A、B 或 C。若选择 B，接受范围包含 typed facts、single driver、protocol／transport 正交、assembler／sequencer／single sink／frontier 完整交付链，以及 History projection ownership 五项不可拆分核心；具体 record／class 名、局部签名、模块拆分和 sink 内部调用粒度等仍可按 Architecture 列出的边界局部调整。
- `D-MIGRATION` 仅在目标选择 B 时决定 M1 一次建立完整 B 骨架，还是 M2 分阶段建立 B并以受约束 A 形 adapter 过渡。它不改变 `D-ARCH` 的目标，也不授权永久保留 A、建立第二 lifecycle owner或绕过 route 启用门。

上述提案的独立终审为 blocker 0、major 0，只证明材料已达到用户裁决就绪状态。没有用户完整阅读 Architecture 后形成的接受记录前，任何提案内容都不得写成 accepted ADR。`ADR-BRIDGE-02`～`06` 只在[已决承载记录](architecture.md#已决-spec-输入与历史-adr-承载记录非待裁决)中解释如何实现 Spec，不是额外待决项。

### 已有代码基础，但不能代表完整实现

- `main` 已有 upstream-compatible reasoning carrier codec、legacy recognition 与逐 block reverse consumer。
- 当前 `main` 的 forward reasoning cardinality 仍不符合最终 Spec；对应修复只存在于尚未进入主线的 reviewed candidate。
- 应用层已有 single pipeline、SDK retry disabled、hooks／approval／attempt／History 等基础 owner，但尚未完成目标 route、semantic conversion、block assembly 与 delivery contract。
- 当前原生 Responses HTTP／WS 能力可提供 transport primitive，不得直接作为 Anthropic bridge 的第二 pipeline owner。

## 用户读完后真正需要裁决的最小问题

**请在完整阅读五份文档，尤其从头到尾完整阅读 `architecture.md` 之前不要回答以下问题。** 以下两项与 Architecture 的[唯一用户裁决矩阵](architecture.md#唯一用户裁决矩阵)一一对应；接受其中一项不自动接受另一项。Spec 已冻结的产品行为无需重开；当前也不需要用户判断实现是否 PASS，因为完整 Acceptance required gates 尚未执行。

### 1. `D-ARCH`：目标内部架构

请选择长期目标内部架构：

- **A：Anthropic canonical pipeline＋Responses adapter。** 接线较小，但长期保留 wire-shaped canonical state、converter 漂移和隐式 owner 耦合。
- **B：typed semantic kernel＋single driver＋protocol／transport legs。** 接受 B 即接受 Architecture 列出的五项不可拆分核心；可局部调整项仍按 Architecture 的明确边界处理。
- **C：Anthropic route 调用现有 Responses route pipeline。** 表面复用最多，但会制造第二套 approval／attempt／retry／History／finalize owner，与 single-owner 合同冲突。

建议选择：**B。** A 只应作为受 `D-MIGRATION` 约束、可退出的迁移形态，C 应明确拒绝。该建议必须以完整 Architecture 的 owner、typed truth、protocol／transport 分层、完整 block 交付链和 History ownership 设计为依据，不能只依据本索引或 A／B／C 对比表。

### 2. `D-MIGRATION`：迁移节奏

若 `D-ARCH` 选择 B，请选择落地节奏：

- **M1：一次建立完整 B 骨架后才接入切片。** 从第一天统一 owner／ports／facts，但改动面和集成爆炸半径最大，首个可验证闭环更晚。
- **M2：分阶段建立 B，并以受约束 A 形 adapter 过渡。** 可逐接缝验证，但必须支付双表示兼容成本，严防 adapter 永久化，并满足 Architecture 的 route 前置门和退出条件。

建议选择：**M2。** 允许分阶段建立 B，但任何 A 形过渡都必须有命名范围、消费者清单和退出条件，不能形成第二套 lifecycle、第二套 converter 语义或永久 wire-shaped canonical state；正式 route 启用前必须通过 Architecture 列出的 single owner、per-attempt conversion、protocol／transport、delivery、lifecycle／History 与真实入口验收组合门。

除非用户在全文阅读中发现 Architecture 与 Spec 的真实冲突，否则当前不需要重裁 route precedence、16 MiB／capacity、reasoning carrier、server-tool、完整 block／SSE、post-commit partial failure 或 strict field policy。尤其不得把 `ADR-BRIDGE-02`／`05` 的历史编号重新包装成投票；它们与 `ADR-BRIDGE-03`／`04`／`06` 一样，只属于[已决 Spec 输入与历史 ADR 承载记录](architecture.md#已决-spec-输入与历史-adr-承载记录非待裁决)。

## 裁决后的记录要求

用户完成阅读并分别作出 `D-ARCH`／`D-MIGRATION` 裁决后，应把结果写成正式 ADR 或等价决策记录，至少包含：两个决策各自的选择；若选择 B，其五项不可拆分核心的接受或明确修改；A 形迁移边界、route 前置门与退出条件；C 的处置；与 Spec 的不覆盖声明；以及 foundations integration 尚未进入 `main`、完整 bridge 仍待实施和 Acceptance required gates 验证的事实。

在 ADR 形成前，实施者只能继续不依赖未决架构选择的事实核对、候选保全与文档同步；不得把本 README 的推荐措辞当作用户授权。
