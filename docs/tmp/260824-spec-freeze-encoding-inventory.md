# 「Spec 冻结」概念在本项目的全部编码点清单

> 采集时间：2026-08-24 07:30–07:40 UTC。采集者：文档考古 subagent（只读，未修改任何被盘点文件）。
> 采集面：`git -C /home/xp/src/ghc-api-proxy-py ls-files` 与 `git -C /home/xp/src/ghc-api-proxy-py/.dev ls-files` 的并集，加上两仓各自 `status --porcelain --untracked-files=all` 的未追踪项，共 1494 个文件。**`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/` 已按要求显式剔除并复核为零残留。**
> 锚点：`冻结`、`frozen`、`freeze`、`freezing`、`定稿`、`已封`、`封版`、`不可变`、`immutable`，以及定向锚点 `规范判据`、`权威是`、`refined and frozen`、`freeze first`、`frozen spec`、`spec is frozen`、`normative`。

---

## ⚠️ 先读：有同伴正在实时改写同一批文件

盘点过程中发现，**这次改写已经有人在做了，且正在进行中**。以下为实测（`git status` + `stat` mtime，见本文末「采集方法」）：

| 文件 | 状态 | mtime（2026-08-24 UTC） | 已改成什么 |
|---|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md` | 工作树已改，**未提交**（HEAD 仍是旧文本） | 07:35:45 | 第 9 行改成「**The Spec is a living document and is never frozen.**」，并新增一条「deferred ledger 不得存放已知错误的 Spec 条款」 |
| `/home/xp/src/ghc-api-proxy-py/.github/copilot-instructions.md` | 工作树已改，**未提交** | 07:35:50 | 第 8 行改成「it is **never frozen**」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md` | 工作树已改，**未提交** | 07:38:01 | 第 3 行改成「**这是活文档，不冻结。**」，新增 2026-08-24 裁定引述块，表名由「冻结后的修订」改为「条款修订记录」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/deferred.md` | 工作树已改，**未提交** | 07:38:36 | 第 5 行由「权威是冻结的 spec.md」改为「权威是 spec.md 的**当前版本**（它也是活文档，不冻结）」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md` | 工作树已改，**未提交** | 07:39:03 | 第 3 行改掉了「2026-08-23 冻结，含一处冻结后修订」；**但第 31、43、49 行的「冻结 Spec」仍是旧文本，未跟改** |

**这份清单本身有保质期。** `deferred.md` 在我两次读取之间（相隔约 4 分钟）内容就变了一次。下文所有行号与原文摘录是 **07:30–07:40 之间的快照**；动手前请对每个目标文件重新 `rg` 一次，不要直接拿本文的行号去 `Edit`。

同伴当前覆盖的范围看起来只有「两份规则文件 + `error-envelope` 一个主题」，**B/B′ 的其余全部条目尚无人动**。建议先跟主会话确认分工，避免与该同伴撞在同一批文件上。

---

## A. 规则层 —— 把「spec 先定稿再实现 / 冻结后不改」写成项目纪律的地方

共 **4 处**，分布在 2 个规则文件 + 2 个主题文档。其中 2 处（A-1、A-3）同伴已改完。

| 路径:行号 | 原文摘录（截断） | 状态 | 改写建议的措辞方向 |
|---|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:9` | 工作树：「A complete behavioral Spec is required before implementation changes observable behavior. **The Spec is a living document and is never frozen.** …」；HEAD：「… The Spec is refined and frozen first. …」 | **已改（未提交）** | 无需再动。唯一待办是**提交**——目前 HEAD 里还是旧纪律，任何新会话读 `git show HEAD` 或从别的分支拉都会拿到旧规则 |
| `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:42` | 「Specs remain **normative** while their external contract is active. Implementation and readiness documents remain living and are updated at meaningful checkpoints, not after every commit.」 | **未改** | 「normative」本身不等于「frozen」，可以保留；但这句把 Spec 与「living 文档」对立着写（Spec 是 normative，其余是 living），在新裁定下会被读成「Spec 不是 living 的」。建议改成「Spec 既 normative 又 living」的并列表述，明确二者不互斥 |
| `/home/xp/src/ghc-api-proxy-py/.github/copilot-instructions.md:8` | 「The Spec must be complete before implementation changes observable behavior, and it is **never frozen**: amend it the moment a new ruling, measurement, or finding contradicts or qualifies it, and log the amendment in the Spec's own revision record. Never call a Spec "frozen" or cite one as authority by its freeze date …」 | **已改（未提交）** | 无需再动。同样待提交 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/history/proposal.md:430` | 「- **分片 1 起需要 Spec**，把第三节扩写为行为 Spec **并冻结**。分片 1 是第一个新增磁盘写入的，界线划在这里。」 | **未改** | 这是主题级的纪律复述（`history` 主题自己给自己定的「写完就冻结」条款），**属 A 类而非 B′**。建议改为「扩写为行为 Spec 并进入维护」，删掉「冻结」这个动作词 |

另有一处是**对该纪律的推理**，不是纪律本身，但改写时值得一并看，因为它的论证前提会随裁定失效：

| 路径:行号 | 原文摘录 | 备注 |
|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/history/decisions.md:56` | 「…依据是两者的验收方式根本不同——取证记录的验收是数据对不对，终端呈现的验收是人看着对不对，把它们**冻结在同一份文档里**会让「冻结」这个词对其中一半失去意义。」 | 裁决结论（拆成两份 Spec）仍成立，但它给出的**理由**建在「冻结」这个机制上。裁定废除后该理由要重述为「同一份文档承载两套验收口径会让修订记录失去可审计性」之类，**结论不要改** |

**「其它规则文件」的核查结论**：`/home/xp/src/ghc-api-proxy-py/.claude/rules/` 下**只有 `00-development-workflow.md` 一个文件**（`ls` 实测）。项目根 `CLAUDE.md` 全文无任何冻结锚点命中。`.dev/` 下没有自成一套的流程纪律文档在复述这条规则——`.dev/README.md`、各主题 `README.md` 均未命中。

---

## B. 自称冻结的 spec 文件

`.dev/docs/` 下的 spec 类文件共 **8 份活文档**（不含 `reports/` 与 `archive-*/` 下的报告原件）。逐份判定如下，**其中 4 份带冻结声明**。

### B-1 `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md` —— 已被同伴改完

| 行号 | 原文摘录 | 备注 |
|---|---|---|
| `:3`（旧） | 「**这份是 Spec**，答「应该是什么样」，规范性。**2026-08-23 冻结**——§10 的两项已由用户裁决，本文的规范条款自此为实施的判据。变更需要新的裁决或新的评审共识。」 | 已被改写 |
| `:3`（现） | 「**这份是 Spec**，答「应该是什么样」，规范性。**这是活文档，不冻结。** 新的用户裁决、实测或发现一旦与本文任何一处冲突或限定它，**当场修订本文**……权威永远是本文的当前版本；某条何时因何而变，读下面的条款修订记录。」 | 同伴的成品，可作为其余 spec 的措辞模板 |
| `:5`（现） | 「> **2026-08-24 用户裁定**：全面废除「spec 冻结」规则……**该声明作废**。下表原名「冻结后的修订」，现名「条款修订记录」；**表内条目原文一字未动**……」 | 这种「保留原表条目、只作废框架」的处理很干净，建议其余 spec 沿用 |
| `:161` | 「`EndpointNotSupported` … **冻结时漏了这一格**，而它已被实测证明可达」 | **正文内的「冻结」残留，同伴尚未处理**。属点时记录，可以保留但需加限定 |

**修订记录表结构（可直接复用）**——这份 spec 有**两张**表：

```
**条款修订记录**：

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-08-23 | §5.1 | …… | 计划评审 [reports/260823-plan-review.md](...) F-04，我方独立复现 |
```

```
## 修订记录

| 版本 | 变化 | 触发 |
|---|---|---|
| v1 | 首稿 | 用户裁决 |
| v2 | 推翻 v1 的两处：…… | 出口清点 [260823-error-surface-inventory.md](...) |
| **v3** | 采纳评审的 4 条 blocker、8 条 major、1 条 minor，**全部** | 评审 [reports/260823-spec-review-gpt.md](...) |
```

两张表分工明确：`## 修订记录` 记**整份文档的版本演进**（触发多为评审轮次），`条款修订记录` 记**单条条款的定点变更**（依据落到具体报告或实测）。建议把这套双表结构推广到其余 spec。

**是否已被违反**：**是，且是最完整的先例。** 声明 2026-08-23 冻结，表内已记 3 条冻结后修订（2026-08-23 两条、2026-08-24 一条），每条都写明了触发原因。其中 2026-08-24 那条的依据栏还明确写了「原登记为延后项 E-9 待裁；2026-08-24 裁定废除冻结后，按新规则『台账不得存放已知错误的 Spec 条款』直接并入正文，E-9 撤销」——这是「冻结制度把已知错误的条款挡在 Spec 之外」的直接证据，改写规则正文时可以引用。

### B-2 `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/spec.md` —— 未改，编码点最密

591 行，`冻结` 出现 29 次。冻结分两个层次，**要分开处理**。

**（a）文档级冻结声明**（必须改）：

| 行号 | 原文摘录（截断） | 改写建议的措辞方向 |
|---|---|---|
| `:5` | 「**状态**：正式开发规格，当前为 **`FINALIZED`**。……结论为 0 blocker／0 major，**可恢复 `FINALIZED` 并按冻结合同继续实施**。」 | 把 `FINALIZED` 这个状态字面量整体退役——它是 `冻结` 的英文别名。改为「现行规格，随裁决与实测持续修订」。**注意 `FINALIZED` 是被外部文档按字符串引用的**，见「连带风险」第 2 条 |
| `:7` | 「**总体 verdict**：`FINALIZED`。Carrier 双格式合同及其余行为**已经冻结**，可继续实施。……**实现进度不得反向改写本规格**。」 | 「实现进度不得反向改写本规格」这半句要**保留**——它防的是「实现跑偏了就改 Spec 来将就」，与新裁定不冲突。要改的只有「已经冻结」四字 |
| `:539` | 「## **已冻结决策与残余分叉**」（章节标题） | 改为「已裁决的决策与残余分叉」。这一节列的是「不得在实施计划中重新开放」的架构轴，语义是「已裁决」而非「文档冻结」 |
| `:541` | 「以下架构轴**已经冻结**，不得在实施计划中重新开放：semantic block 等于 Anthropic content block；……」 | 同上，改「已经冻结」为「已由用户裁决」，并保留「不得在实施计划中重新开放」 |
| `:575` | 「……双格式合同**已经冻结**，本文件为 `FINALIZED`；具体实现进度和缺口只在 implementation.md 维护。」 | 同 `:5` |

**（b）条款级「冻结」用作规范性标记**（灰区，建议保留但统一措辞）：`:74`「### 冻结的 route precedence」、`:120`「按下方冻结矩阵处置」、`:148`/`:177` 表头「冻结行为」、`:156`/`:159`/`:165`/`:170`/`:189`/`:196`/`:219`/`:322`/`:333`/`:486`，以及 `:583`–`:588` 评审处置表内 6 处。这些说的是「这一条的行为已经定死、不由实现者自选」，**不是「这份文档不再修订」**。新裁定废除的是后者。若一并改写，工作量会翻数倍且可能改错语义；建议**保留，但在文档状态区加一句「本文出现的『冻结』一律指某条行为已裁决不再由实现者自选，不指本文档不可修订」**。

**修订记录表**：**没有。** 本文只有 `## 文档状态`（`:3`）与 `## 评审处置表`（`:577`，表头为 `| 编号 | 发现 | 处置 | 依据 | 说明 |` 一类的评审行）。**这是最需要补一张 B-1 那种双表的地方**。

**是否已被违反**：**是。** `:9` 记录了 2026-08-22 用户重裁，明确「覆盖本文原『首块前零 HTTP success headers』」，并写明「已按此改写『Downstream Anthropic SSE』第 1／2／3 条、retry 边界一节与不变量一节」。也就是说这份 `FINALIZED` 文档在冻结后被整段重写过，但**改动只以散文形式记在文档状态区，没有进任何修订记录表**。`:10` 还挂着一串「尚未跟进、需独立切片」的欠账。

### B-3 `/home/xp/src/ghc-api-proxy-py/.dev/docs/history/spec.md` —— 未改，「部分冻结」形态

| 行号 | 原文摘录 | 改写建议的措辞方向 |
|---|---|---|
| `:13` | 「- **冻结范围**：§2–§8 为冻结契约，实施切片按它验收。**§9 的六项未裁决，未裁之前不得当作已定**；§10 是实施中发现的缺口，不构成契约。」 | 这是「分节冻结」——只冻 §2–§8。改为「规范范围：§2–§8 为规范契约，实施切片按它验收」，其余限定保留原样 |
| `:282` | 「……合同的具体形状留给实施切片，但上面这条『显式携带』**是冻结的**。」 | 条款级用法，改为「是规范的」即可 |
| `:629` | 「无论选哪种，下面几条**是冻结的**：」 | 同上 |
| `:784`、`:743`、`:765` | 引用 proposal「**定稿**」这一事件（「proposal 定稿之后才出现的事实」等，共 3 处） | 这些是**对 proposal 的时间指称**，不是对本 spec 的冻结声明。可保留，但若 proposal 也要去掉「定稿」概念，需一并重述为具体日期或 commit |

**修订记录表**：**没有。** 只有开头的元信息列表（`:11`–`:17`）。

**是否已被违反**：**部分。** §2–§8 声明冻结后未见明确的「冻结后修订」记录；但文档自身用 §10 承载「实施中发现的缺口」（`:761`「**本节不是契约。** 它记录 proposal 没有覆盖、或覆盖得与当前事实不符的地方，**供下一次修订采纳**」）。这正是新裁定要废除的形态——**已知与事实不符的内容被停放在一个「不构成契约」的附录里等下一次修订，而不是当场改进正文**。这条对改写规则正文很有说服力。

### B-4 `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` —— 未改，「冻结被实现单方面违反」的先例

| 行号 | 原文摘录（截断） | 备注 |
|---|---|---|
| `:24` | 「- **剩余修订项（本文件尚未定稿）**：独立评审……报 blocker 3、major 9、minor 7。……**实现前必须先关闭这些项。**」 | 自称「尚未定稿」，即处于「冻结前」状态。改写时把「尚未定稿」改为「尚有未闭合的评审发现」 |
| `:15` | 「> 4. **⏳ 待裁决：域名限制的默认值。** §3.4 与 D1 **冻结**「默认 `error`，三取值」，实现是「默认 `drop_fields`，两取值」。**这是实现单方面偏离了用户已下的裁决**，理由……写在 `src/app/config/schema.py` 的注释里，但**没有回到用户手上重裁**。**下文 §3.4 与 §14 D1 保持原文不动，等用户裁决后再改。**」 | **最有力的反面先例**：冻结制度导致一条已知与实现不符的条款被刻意「保持原文不动」，错误在 Spec 里挂了 4 天 |
| `:20`、`:37`、`:150`（「### 5.3 冻结的呈现形态」）、`:233`、`:237`、`:238`、`:257`（「### 7.2 冻结裁决：不做 continuation」）、`:323`、`:327`（「### 9.3 冻结的保守判定」）、`:388`、`:465`、`:472`、`:474`、`:486` | 条款级「冻结」标记 | 同 B-2（b），建议保留 + 加统一说明 |

**修订记录表**：**没有。** 只有 `## 文档状态`（`:3`）。

**是否已被违反**：**是，且方向与 B-1 相反。** B-1 是「冻结后仍修订了，并记录下来」；这份是「发现冻结条款是错的，却因为它冻结了而拒绝修订」。两个方向的先例都拿到手，改写规则正文时建议各引一条。

### B-5～B-8 无冻结声明的 spec（作为「正确形态」的对照样本）

| 文件 | 状态行原文 | 判定 |
|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/auto-mode-classifier/spec.md:3` | 「> 状态：**现行契约**。实现已落地并经三轮独立评审（两轮特性、一轮收尾），**随实现同步更新**。证据基础是两份取证报告……」 | **零冻结锚点命中。**「现行契约 + 随实现同步更新」正是新裁定要的措辞，**建议直接拿它当模板** |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:3` | 「状态：已实现并与代码对账（分支 `worktree-tui-request-log-footer`）。范围为本次切片……」 | 零冻结锚点命中。无需改动 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/delivery-keepalive/spec.md:3` | 「- 状态：规范。适用范围是 `src/app/pipeline/delivery/stream.py` 的下游交付，随该外部契约有效而有效。」 | 自身**无**冻结声明。文内 `:50`、`:99` 是**引用**别处的冻结，归 B′（见下） |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/systemd-rolling/spec.md` | —— | 4 处 `冻结`/`immutable` 全部指 **tokenization snapshot 的内容不可变**（`:134`「Candidate 只复制**冻结 snapshot** 到 generation-local 路径」、`:137` `immutable checkpoint`），是运行时数据语义，**与文档冻结无关**。见「未采纳/排除的路线」 |

---

## B′. 引用别处冻结声明的文档（措辞不同，需另行改写）

共 **19 处**，分布在 12 个文件。这些改写时不能照搬 B 的措辞——它们是**指称**，改法是把「冻结的 X」改成「X 的当前版本」或「X 已裁决的 Y」。

| 路径:行号 | 原文摘录（截断） | 改写建议的措辞方向 |
|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md:3` | **已改**：「规范判据在 spec.md——**它同样是活文档，不冻结**，随新裁定与新发现当场修订，某条何时因何而变见它的条款修订记录」 | 完成 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md:31` | **未改**：「建 `error-envelope/deferred.md`，收 §10.2 与 §11 的全部条目，各自引**冻结 Spec** 为权威。」 | 同伴漏改。改为「各自引 Spec 当前版本为权威」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md:43` | **未改**：「`app/pipeline/error_classify.py`：`describe`，覆盖 pipeline 侧来源与 `ProviderError` 家族五个子类（**Spec 冻结后修订**）。」 | 同伴漏改。这是**点时记录**，指「该条是 2026-08-23 之后补进 Spec 的」。建议改为「Spec 2026-08-23 条款修订记录第 1 条」，保留可追溯性 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md:49` | **未改**：「**测试侧手工转录冻结 Spec 的每一行**，每 case 一个稳定 id……」 | 同伴漏改。改为「手工转录 Spec 当前版本的每一行」。**注意这条隐含一个真实风险**：Spec 变活之后，「手工转录每一行」的测试需要一条随 Spec 修订同步更新的纪律，否则测试会静默落后于 Spec |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/deferred.md:5` | **已改**：「权威是 spec.md 的**当前版本**（它也是活文档，不冻结）。……**台账不得存放已知错误的 Spec 条款**……2026-08-24 的 E-9 就是按这条撤销并入 spec.md §6.2/§6.3 的。」 | 完成，且措辞可作 deferred 类文档的模板 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/README.md:25` | 「不要只读 Architecture 的推荐结论或 A／B／C 对比表后直接裁决。**Spec 已冻结的产品行为**不是 Architecture 的附加投票项。」 | 改为「Spec 已裁决的产品行为」。这句的功能是防越权重开，**必须保留其力度** |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/architecture.md:309` | 「……必须遵守**正式 Spec 已冻结的** fail-closed 行为：自动路由只依据明确 capability……」 | 「Spec 已裁决的」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/architecture.md:461` | 「『无已证明 resume contract 时显式 partial failure』**已经由 Spec 冻结**，不是本文投票项。」 | 「已由 Spec 规定」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/architecture.md:554` | 「- **已决约束：** **正式 Spec 已冻结** unknown／missing endpoint capability fail closed。……」 | 「正式 Spec 已规定」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/architecture.md:658` | 「| 可读性-M1 ADR-BRIDGE-04 把 **Spec 已冻结的** unknown capability fail-closed 重新列为待决 | **已采纳并修订（C）** | ……」 | **评审处置表内的点时记录**。建议**不改**，见「连带风险」第 4 条 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/acceptance.md:12` | 「**未决政策处理**：Spec『仍需用户选择的低概率扩展』当前**均已有冻结基础行为**：……」 | 「均已有确定基础行为」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/acceptance.md:13` | 「**本规范状态**：**`FINALIZED_ACCEPTANCE_ORACLE`。** 本次仅按 **current FINALIZED Spec** `5e362822…` ……」 | acceptance 自己也带 `FINALIZED_*` 状态字面量。**这份是 acceptance oracle 而非 spec，是否一并去冻结需要主会话裁一次**——见「连带风险」第 2 条 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/acceptance.md:35`、`:36`、`:137`、`:401`、`:442`、`:445` | 6 处「冻结 Spec」「逐项冻结」「新冻结 Spec」「未绑定当前冻结 Spec」「Spec 已冻结的……预算」「服从冻结 Spec 中……」 | 逐条改为「当前 Spec」／「Spec 已规定的」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/acceptance.md:414`、`:430`、`:434` | 评审处置表内 3 处（含「采纳最终 verdict 并**定稿**」「是否充分**冻结**项目主 v1」） | **点时记录，建议不改** |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/service-cutover/plan.md:9` | 「- **权威边界**：Anthropic Responses bridge 的用户可观察行为来自 `../anthropic-responses-bridge/spec.md` 的 **`FINALIZED@4c9beed…`** 与 `../anthropic-responses-bridge/acceptance.md` 的 **`FINALIZED_ACCEPTANCE_ORACLE@f99492a…`**；……」 | **这是按「状态字面量 @ 内容哈希」做的硬引用**，是全清单里改写代价最高的一处。见「连带风险」第 2、3 条 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/service-cutover/plan.md:531` | 「> 继续执行 `plan.md` 的下一未完成准备切片。先完整读取该 living plan、current readiness、Anthropic Responses bridge 的 **current frozen Spec／Acceptance** 与 living Implementation……」 | 这是一段**给后继 agent 的 kick-off 提示词**。改为「current Spec／Acceptance」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/service-cutover/readiness.md:56` | 「| Block-level buffering／delivery frontier／…… | `UNVERIFIED` | **Spec／Acceptance 已冻结**完整 Anthropic content block 为最小下游提交单元；`REL-06` 的具体条款以 `../anthropic-responses-bridge/spec.md` 为准。」 | 「Spec／Acceptance 已规定」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/README.md:144` | 「- [`../../anthropic-responses-bridge/`](../../anthropic-responses-bridge/) —— 桥 spec，**冻结中**。本主题的 wire 不变量指回它。」 | 「桥 spec，现行规范」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:83` | 「| **冻结的目标形态与流式时点** | `../anthropic-responses-bridge/hosted-web-search-spec.md` §5、§6.3 |」 | 「规定的目标形态与流式时点」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:27`、`:49` | 「规格 §5.3 **已冻结**形态……」「规格 §5.3 **冻结了**形态，§6.3 **冻结了**流式成块时点。」 | 「规格 §5.3 规定了形态」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/delivery-keepalive/spec.md:50` | 「……并且**按已冻结的 Spec** 不得再补 `message_stop`。」 | 「按 Spec 当前版本」 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/delivery-keepalive/status.md:69` | 「……**按已冻结的 Spec** 不得再补 `message_stop`。回归 `test_a_due_preamble_goes_out_even_though_the_stream_is_already_over` 钉住了这个线形。」 | 同上。**与上一条是同一句话的两处副本**，必须同改，否则两份文档会开始互相矛盾 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/server-layout/README.md:252` | 「- **9.3 → D-1**：……`spec.md` 已改；`acceptance.md` 的**冻结语法**与 `architecture.md` 的 delayed-start owner 留作独立切片。」 | 「acceptance.md 的固定语法」。**这条同时是一笔未闭合的欠账**，改写时顺手确认它是否已闭 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/server-layout/README.md:275`、`:277` | 「- **冻结的** `spec.md:285`：「首个 content block ……**下游不得看到 HTTP success headers**」」；「……但 `spec.md` 是**被其它工作依赖的冻结行为合同**，`architecture.md:397/442` 也建在它上面。」 | `:275` 描述的是**已被 2026-08-22 重裁推翻的旧条款**，且带**行号引用**（`spec.md:285`）——该行号本身就有失效风险。改写时优先把行号换成小标题 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/server-layout/decisions.md:29` | 「1. `acceptance.md` 的 `CAL-04-GRAMMAR-v1` 需升版：`ping` 转移行、**冻结 fixture 集合**里「不得把 `ping` 放在首批之前」那句……」 | 「固定 fixture 集合」。这里的「冻结」指测试夹具集合固定，条款级用法 |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/implementation.md:9` | 「- **评审语义**：本文某一内容身份取得 blocker 0、major 0，只表示……**不表示 Implementation 已定稿**、实施已完成、后续不再修改……」 | **不用改，且值得抄。** 这句已经在说「blocker 0 不等于定稿」，与新裁定同向 |

---

## C. 人类控制的文档 —— 🔴 有命中，但经查**不构成冲突**

`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/` 下命中 **3 处**（该目录是隐藏目录，`rg docs/` 默认跳过，必须显式给完整路径才能扫到——我踩过一次，本文的「无命中」结论均已用显式路径复核）。

| 路径:行号 | 原文摘录 | 判定 |
|---|---|---|
| `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/config.example.yaml:293` | 「# **用户冻结的不变量**是绝不误杀合法长思考：活连接上的静默没有可证明安全的 wall-clock 上界，因此 bundled defaults 全部禁用此类终止器。」 | **不是 spec 文档冻结。** 说的是一条**行为不变量**（timeout 默认值语义）被用户定死。与新裁定**不冲突** |
| `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/config.example.yaml:298` | 「# The **frozen invariant** is never to false-kill legitimate thinking: silence on a live connection has no provably safe wall-clock bound, so bundled defaults disable these terminators.」 | 同上，英文对照段 |
| `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/release-and-deployment.md:7` | 「`uv export **--frozen** --format requirements.txt --no-emit-project --no-hashes --no-dev -o constraints.txt`」 | **是 `uv` 的命令行开关**，与本议题无关 |

**结论：C 类不构成阻塞，无需回去问用户。** 三处命中里两处是同一条行为不变量的中英对照、一处是 CLI 参数，**没有任何一处把「spec 文档冻结」写成用户级纪律**。

**但有两条要提醒主会话：**

1. **不要顺手改这个词。** 用户亲笔用了「冻结的不变量」这个说法。新裁定废除的是「spec 文档冻结」，**没有**废除「用某条不变量被冻结」来描述一条不再重开的裁决。若改写时为了措辞统一而想把项目里所有「冻结」都清掉，会与用户亲笔用词直接冲突——`docs/.human-controlled/` 我们不能改，改了别处就会出现「文档说不许叫冻结、而用户自己在叫」的分裂。**建议在新规则正文里明确划界：禁止的是把 Spec 文档称为 frozen，不禁止把某条已裁决的不变量称为冻结的。**
2. `docs/.human-controlled/config.example.yaml` 与 `message-translation.md` **此刻是 dirty 的**（`git status` 实测），说明用户或同伴正在动它们。引用其内容时不要引行号——`delivery-keepalive/spec.md:84` 已经因为这个吃过一次亏，文内自己写了「**不引行号**：该文件正被用户持续修订，行号引用已经失效过一次」。

### C 的外溢：源码注释里也有三处「the spec's frozen invariant」

不在 `docs/` 下，但同源，一并列出（**均指 C-1 那条用户不变量，不是 spec 文档冻结**）：

| 路径:行号 | 原文摘录 |
|---|---|
| `/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:127` | `# The spec's frozen invariant is never to false-kill legitimate thinking.` |
| `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery_policy.py:109` | `The frozen invariant is never to false-kill legitimate thinking — silence on a live connection has no provably safe bound …` |
| `/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_schema.py:34`、`/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:2604` | 同一句话的两处测试侧副本 |

其中 `schema.py:127` 的措辞有个小瑕疵值得顺手修：它说「**the spec's** frozen invariant」，但这条不变量的权威其实是**用户亲笔的 `config.example.yaml`**，不是任何 spec。改成 `the user's frozen invariant` 更准确，也顺带避开新裁定造成的歧义。

---

## D. 技能与用户级规则 —— ⚠️ 非本项目所有，改写需另行裁决

`/home/xp/.claude/rules/` 下 **0 处**冻结锚点命中（实测：`00-user/` 六个文件全扫，无 `冻结`/`frozen`/`freeze`/`定稿`）。`40-dev-and-docs.md:28` 只把 `spec.md` 注释为 "the settled requirements spec"——**"settled" 不等于 "frozen"，未把冻结写成纪律**。

`/home/xp/.claude/skills/` 下复述「冻结 spec」纪律的共 **8 处**，分布 6 个 skill：

| 路径:行号 | 原文摘录（截断） | 归属提醒 |
|---|---|---|
| `/home/xp/.claude/skills/adopting-agent-findings/SKILL.md:29` | 「- 评**代码/实现**：最终代码是事实……，**冻结的 spec 是行为 oracle**。」 | ⚠️ **非本项目所有**。这句把「冻结」当成 spec 可作 oracle 的前提，与新裁定语义直接相关 |
| `/home/xp/.claude/skills/adopting-agent-findings/SKILL.md:97` | 「| **A · 不由你裁** | 拟**改变**用户已裁决/ADR/**冻结 spec**/对外契约，或其适用性确有歧义 | **回用户**。……」 | ⚠️ **非本项目所有**。**这条最需要注意**：新裁定要求「发现 Spec 有错就当场修订」，而这条 skill 要求「改 spec 要回用户」。二者在本项目内会打架 |
| `/home/xp/.claude/skills/verifying-authoritative-claims/SKILL.md:67` | 「\| **用户要什么／是否批准** \| 用户当前明确裁决、**冻结 spec**、ADR \| 现有代码、旧计划、模型偏好 \|」 | ⚠️ 非本项目所有 |
| `/home/xp/.claude/skills/reshaping-a-bypassed-guard/SKILL.md:17` | 「> \| 违规性 \| 它属于守卫**声称**要挡的那一类 \| **引用**用户裁决 / ADR / **冻结 spec** / 明写的项目契约——不是「显然属于」 \|」 | ⚠️ 非本项目所有 |
| `/home/xp/.claude/skills/improving-user-proposals/SKILL.md:3`（description）、`:10`、`:48` | 「not yet settled by a decision/ADR/**frozen spec**」；「已由本轮的明确命令、用户既有裁决、ADR、**冻结的 spec** 或对外契约……」；「至少覆盖一手裁决源（用户原话、ADR、**冻结 spec**、CLAUDE.md）」 | ⚠️ 非本项目所有，3 处 |
| `/home/xp/.claude/skills/writing-handover-docs/SKILL.md:24`、`:111`、`:208` | 「用户裁决回到原话／ADR／**冻结 spec**」；「**与冻结的 spec / 决策记录 / backlog 冲突时必须对账**」；「同时提供：……**冻结 plan／spec**」 | ⚠️ 非本项目所有，3 处 |
| `/home/xp/.claude/skills/closing-a-development-session/SKILL.md:73` 与 `clause-inventory-section2.md:88` | 「five were the **sole producer** of conclusions already written into a **frozen spec**」 | ⚠️ 非本项目所有。这是**实证记录**，不是纪律条款，改写价值低 |

**关于任务点名的两个 skill**：

- **`my-skills:agent-driven-sdd` 不存在。** `/home/xp/.claude/skills/` 下无此目录（`ls` 实测，35 个 skill 全列过），`fd` 全盘 `~/.claude` 也无。它**只在 `/home/xp/.claude/rules/00-user/40-dev-and-docs.md:13` 被作为「Consider using the related skill」引用**——这是一条**悬空引用**。与本次裁定无关，但值得单独报给用户。
- **`organizing-project-docs` 未把 spec 冻结写成纪律。** 它有 4 处 `frozen`/`freeze`（`:93`、`:117`、`:122`、`:242`），但讲的是**「一份文档该不该被就地重写」的通用可重写性轴**，且 `:93` 明确写着「**Neither of those is a rewritability policy — that is Axis 1's call**」，`:117` 写「Whether a doc is rewritten, frozen, or left alone depends on **who still depends on it** — never on what it's called」。**它的立场与新裁定相容，不需要改。**

**改写建议**：D 类**一处都不要在本次任务里改**。它们是 user 级资产、跨项目生效，且 `adopting-agent-findings:97` 那条与新裁定的冲突是**真实的语义冲突**，需要用户单独裁一次「是全局改，还是在本项目规则里写一条 override」。

---

## 改写时的连带风险

1. **`error-envelope` 主题正在被同伴改，且已漏改 3 行。** `plan.md:31`、`:43`、`:49` 仍写「冻结 Spec」，而同一文件的 `:3` 已改成「不冻结」——**该文件此刻自相矛盾**。这是最紧急的一处。要么等同伴收尾后复核，要么先和主会话确认由谁补。

2. **`FINALIZED` / `FINALIZED_ACCEPTANCE_ORACLE` 是被跨文档硬引用的状态字面量，不是散文。** 至少 3 处按字符串消费它：`service-cutover/plan.md:9`（`FINALIZED@4c9beed…`）、`readiness.md:56`、`acceptance.md:13`（`current FINALIZED Spec 5e362822…`）。改 `spec.md` 的状态字面量而不同改这些引用，会让 `service-cutover` 的「权威边界」一节指向一个不存在的状态名。**且这是个 fork**：`acceptance.md` 是验收 oracle 而非 Spec，新裁定字面上只管 Spec——acceptance 要不要一起去冻结，**建议交主会话裁**。

3. **`@<内容哈希>` 形式的引用会因改写而全部失效。** `service-cutover/plan.md:9` 绑的是 `spec.md` 的 SHA-256 `4c9beed…`、`acceptance.md` 的 `f99492a…`；`anthropic-responses-bridge/spec.md:5`、`:579` 与 `acceptance.md:13`、`:31`、`:406`、`:434` 各自绑了另外几个哈希（`0d81c21f…`、`5e362822…`、`746a…`、`1d…`）。**只要动一个字节，这些哈希全部对不上。** 这些哈希的作用是「本轮评审审的是哪份 bytes」，属点时记录——建议**不重算、不更新**，而是在文档状态区加一句说明「以下哈希是各轮评审当时的输入身份，2026-08-24 去冻结改写之后不再等于当前文件」。悄悄重算哈希会把「评审过的是哪份」这个事实抹掉。

4. **评审处置表、`## 修订记录` 与报告原件里的「冻结」是点时记录，改了就是伪造历史。** 具体为：`anthropic-responses-bridge/spec.md:583`–`:588`（评审处置表 M1–M6，6 处）、`architecture.md:658`、`acceptance.md:414`/`:430`/`:434`、`error-envelope/spec.md` 的两张表内条目、以及 `.dev/docs/**/reports/` 下的全部报告原件（未逐一列举，`冻结`/`frozen` 在 reports 目录下命中数以百计）。项目规则 `.claude/rules/00-development-workflow.md` 已明写「**A report original is a point-in-time record … rewriting them to match a later layout falsifies the record**」。同伴在 `error-envelope/spec.md:5` 采取的做法（**保留表内条目原文一字未动，只作废框架**）是正确范式，建议全项目沿用。

5. **`server-layout/README.md:275` 引的是已被推翻的旧条款 + 一个行号。** 它引 `spec.md:285`「下游不得看到 HTTP success headers」，而这条已被 2026-08-22 用户重裁覆盖（见 `anthropic-responses-bridge/spec.md:9`）。行号 `:285` 现在指向的是**改写后**的内容（当前 `:287` 才是相关条款）。改写这一段时若照抄行号会把错误固化。**同一风险波及所有形如 `spec.md:NNN` 的引用**：`hosted-web-search-spec.md:388`（引 `spec.md:8`、`:537`）、`:465`（引 `:8`、`:537`）、`README.md:277`（引 `architecture.md:397/442`）。

6. **「同一句话的两处副本」会因单边改写而开始互相矛盾。** 已定位一对：`delivery-keepalive/spec.md:50` 与 `delivery-keepalive/status.md:69` 是同一句「按已冻结的 Spec 不得再补 `message_stop`」。必须同改。

7. **`plan.md:49` 那条「手工转录冻结 Spec 的每一行」隐含一条会被裁定打断的纪律。** 它成立的前提正是 Spec 不再变：Spec 冻结 → 手工转录一次即可。Spec 变活之后，这条测试纪律需要补上「Spec 每次条款修订后同步更新转录」的配套要求，否则测试会静默落后于 Spec，而且落后时**测试仍然全绿**（它断的是自己转录的那份 expected）。**这不是措辞问题，是新裁定引入的一个真实缺口**，建议单独记一条待办。

8. **`.dev` 是独立仓库，两仓要分别提交。** A 类的两个文件（`.claude/rules/`、`.github/`）在主仓，B/B′ 全在 `.dev` 仓。同伴当前的 5 个改动**全部未提交**，跨两个仓库。

---

## 未采纳／排除的路线

以下锚点搜过并命中，但判定**不属于本次改写范围**，理由逐条列出。

| 排除项 | 位置举例 | 排除理由 |
|---|---|---|
| Python `frozen=True` / `frozenset` / `FrozenModel` / `SubscriberRegistry.freeze()` | `src/app/config/settings.py:11`–`:149`（14 个 `FrozenModel` 子类）、`src/app/pipeline/events.py:5`–`:102`、`tests/unit/pipeline/test_pipeline_events.py`（26 处） | 语言/框架的不可变对象语义，与文档冻结无任何关系。**为此把全部 `.py`/`.pyi`/`.json`/`.lock` 从主扫描里剔除，命中数由 2083 降到 1552** |
| tokenization snapshot 的 `immutable` / 「冻结 snapshot」 | `.dev/docs/systemd-rolling/spec.md:134`、`:137`；`.dev/docs/archived-2604-rewrite/hooks-tokenization-spec.md:65`（「防止历史数据永久**冻结**模型」）、`:180`（`frozen snapshot`） | 指运行时数据内容不可变 / 学习权重被锁死，属产品行为，不是文档纪律 |
| Git 归档与历史改写语境的「冻结」 | `.dev/docs/anthropic-responses-bridge/implementation.md:79`、`:257`、`:284`、`:290`；`.dev/docs/upstream/h2-goaway/README.md:22`（「`archive-260820/` …内容已冻结，只作证据」）；`.dev/docs/git-housekeeping/reports/`、`.dev/docs/service-cutover/reports/` 下大量命中 | 指「归档分支/证据目录内容不再变动」，是 Git 归档纪律。项目规则里 `immutable archive/YYMMDD-<topic>` 是独立的一条，**新裁定没有触及它** |
| `uv --frozen` CLI 开关 | `docs/.human-controlled/release-and-deployment.md:7`、`.dev/docs/httpx2-migration/plan.md:241` | 命令行参数 |
| 「证据已封存」 | `.dev/docs/service-cutover/reports/260807-resume-backup-port-smoke-r2.md:145`、`-r3.md:191`/`:317` | 指一次性状态根的清理时序，与「已封（版）」同形但语义无关。这是我用 `已封` 这个锚点搜到的**唯一一族命中**，全部为误配 |
| `.dev/docs/**/reports/` 与 `archive-*/` 下的全部命中 | 未逐条列举；`documentation-restructure/archive-260808/plan.md` 单文件即 64 处、`upstream/retry-and-continuation/archive-proxy-side-continuation/reports/260821-review-g2-spec-draft.md` 35 处等 | **报告原件与归档件是点时记录**，按项目规则不得回改（见「连带风险」第 4 条）。这是**范围裁剪，不是「没找到」**——若主会话认为需要，我可以另出一份 reports 全量清单 |
| `.dev/docs/archived-2604-rewrite/` 全目录 | `DESIGN.md:*`、`thinking-pipeline.md:*`、`lib-survey/*`、`plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md:*` 等约 40 处 | 用户 2026-08-20 已裁定该目录**整体过期**（早期 peer 会话的 `copilot-api-js` 学习笔记，见 `.dev/docs/history/spec.md:819`）。改写它没有收益 |
| `normative` / `规范` 的绝大多数命中 | `.dev/docs/history/spec.md:277`、`:347`、`:483`、`:562` 等 | 「规范/规范性」描述的是**文档的效力**，与「是否可修订」正交。新裁定要的正是「既规范又可修订」。**只有 `.claude/rules/00-development-workflow.md:42` 那一处因为把 normative 与 living 对立着写，才进了 A 类** |
| `.claude/worktrees/` 下的一切 | —— | 任务硬约束，已显式剔除并复核零残留 |
| **纯推理排除、未实际执行的路线** | —— | **无。** 本次没有靠推理排除任何锚点：所有排除项都有上表列出的实际命中位置作为依据 |

### 一处方法学告警（避免下一个人踩）

`rg` 默认跳过隐藏目录，因此 **`rg <pattern> /home/xp/src/ghc-api-proxy-py/docs/` 对 `docs/.human-controlled/` 返回零命中**——而该目录里确实有 3 处命中。我第一次跑就撞上了这个假阴性。任何对 C 类的「未找到」结论，都必须用 `rg <pattern> /home/xp/src/ghc-api-proxy-py/docs/.human-controlled/`（显式到隐藏目录本身）或 `rg --hidden` 重跑才算数。本文的 C 类结论已用显式路径复核。

---

## 采集方法（供复现）

```bash
M=/home/xp/src/ghc-api-proxy-py
D=$M/.dev
{ git -C "$M" ls-files
  git -C "$M" status --porcelain=v1 --untracked-files=all | sed -n 's/^?? //p'
} | sort -u | sed "s|^|$M/|" > /tmp/abs-main.txt
{ git -C "$D" ls-files
  git -C "$D" status --porcelain=v1 --untracked-files=all | sed -n 's/^?? //p'
} | sort -u | sed "s|^|$D/|" > /tmp/abs-dev.txt
# 硬剔除同伴隔离工作树
rg -Fv '/.claude/worktrees/' /tmp/abs-main.txt /tmp/abs-dev.txt --no-filename > /tmp/abs-all.txt
rg -F '/.claude/worktrees/' /tmp/abs-all.txt || echo "worktrees 剔除已复核"

xargs -a /tmp/abs-all.txt -d '\n' rg --line-number --no-heading --color=never -i \
  -e '冻结' -e 'frozen' -e 'freeze' -e 'freezing' -e '定稿' -e '已封' -e '封版' -e '不可变' -e 'immutable'
```

文件总数 1494（主仓 544 + `.dev` 954，均含未追踪、不含 ignored）。核心锚点原始命中 2083 行，剔除 `.py`/`.pyi`/`.json`/`.lock` 后 1552 行，再按上表逐类归并与排除。
