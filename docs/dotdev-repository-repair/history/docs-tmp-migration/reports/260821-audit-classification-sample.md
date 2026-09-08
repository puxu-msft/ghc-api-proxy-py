# 分类质量抽样审计报告

审计时间：2026-08-21　　审计者：独立抽查子智能体（只读）
抽查依据：`.dev/docs/docs-tmp-migration/BRIEF.md`、`.dev/docs/docs-tmp-migration/reports/260821-classify-batch-01..10.md`、`.dev/docs/docs-tmp-migration/README.md`

## 方法

1. 把 10 份批次分类表解析成单一 417 行的 `文件 → 话题` 表，做话题计数校验（与 README 计数基本一致）。
2. 用文件名词根聚类（Python 脚本，剔除通用体裁词如 review/audit/verify/r2 等）扫全部 417 个文件名，找出「同一词根被分到多个话题」的簇，逐簇检查是否为已知合理的跨话题区分，还是分类漂移。
3. 完整打开并逐字读取 31 份报告原文（覆盖要求的全部 13 份 `.dev/docs/tmp/` 未分类文件、6 份 `anthropic-responses-bridge`、5 份 `documentation-restructure`、3 份 `systemd-runtime`，以及 `git-housekeeping`／`hooks-subscription-migration`／`project-review-principles-skill`／`pipeline-rewrite-parity`／`lifecycle-reorg` 各 1 份自选样本），独立判断当前归属是否站得住。

## 结论总览

- 抽查 31 份，**判定「应改归属」的有 9 份**，全部属于同一个具体问题（见「主要发现」）。
- 13 份 `.dev/docs/tmp/` 未分类文件**全部复核通过**，无一份应改判为某个具体话题。
- `anthropic-responses-bridge`（193 份最大话题）抽查的 6 份**均确属主链路**，没有观察到「装不下就扔这儿」的垃圾桶现象。
- 已知的两次跨批次補救（`copilot-token-identity`、`git-housekeeping`）核对无误；另发现一处未在 README 记录的静默重分类（见「次要发现」），内容判断可以接受，但存在文档留痕缺口。

## 主要发现（高把握）：9 份文件应从 `documentation-restructure` 改判

**现象**：存在两组并行的「living 文档当前状态定向复评」系列报告，评审对象分别是 `docs/agents/anthropic-responses-bridge/implementation.md` 和 `docs/agents/service-cutover/readiness.md`。同一目标文档的系列报告，按文件名前缀被分类 agent 拆成了两个不同的话题：

| 文件名模式 | 目标文档 | 判定话题 | 判断 |
|---|---|---|---|
| `260807-review-implementation-current-r2..r8.md`、`-resume.md`、`-checkpoint.md`、`-living-plan.md`、`260807-review-implementation-current.md` | `implementation.md`（bridge） | `anthropic-responses-bridge` | **正确** |
| `260807-resume-review-implementation-current-r2..r7.md`、`260807-resume-review-implementation-post-s3.md` | 同一份 `implementation.md` | `documentation-restructure` | **应改判为 `anthropic-responses-bridge`** |
| `260807-review-readiness-current-r2..r8.md`、`-resume.md`、`260807-review-readiness-current.md` | `readiness.md`（service-cutover） | `service-cutover` | **正确** |
| `260807-resume-review-readiness-current.md`、`260807-resume-review-readiness-current-r2.md` | 同一份 `readiness.md` | `documentation-restructure` | **应改判为 `service-cutover`** |
| `260807-resume-review-readiness-post-s3.md` | 同一份 `readiness.md` | `service-cutover` | 正确（同系列的另一份没被误判） |
| `260807-resume-review-systemd-plan-current.md`／`-r2.md`／`-r3.md`／`260807-resume-review-systemd-plan-post-s3.md` | `systemd-runtime/plan.md` | `systemd-runtime` | 正确（同名模式下第三份目标文档没有被误判） |
| `260807-resume-review-stream-route-current.md` | bridge stream route | `anthropic-responses-bridge` | 正确 |

**依据**：逐字读了 `260807-review-implementation-current-r2.md`（bridge）与 `260807-resume-review-implementation-current-r2.md`（documentation-restructure）全文——两者标题分别是「bridge implementation living doc 定向复评 R2」与「Implementation current 独立定向复评 R2」，内容都是核对 `implementation.md` 当前所写的候选状态（History facts 是否已提交、systemd 新 HEAD 是否已同步、happy integration worktree 状态等）是否与 Git 现场一致，是同一种「living 文档真相审计」，评审的是同一份文件在不同时间点的快照。又读了 `260807-resume-review-readiness-current-r2.md`，内容 100% 是 `service-cutover/readiness.md` 的 P0-P3 表、stream candidate、systemd rebuild、backup port 状态核对，与同名不带 `resume-` 前缀、被正确分入 `service-cutover` 的系列（如 `260807-review-readiness-current-r2.md`）在体裁与对象上完全一致。

批次分类表原文对这批文件的备注也直接写了「live 文档真相审计」（`260821-classify-batch-03.md`、`260821-classify-batch-04.md`），说明分类 agent 把「体裁是真相审计」当成了分类依据，而没有落实 BRIEF 判据第 2 条「跨话题的，按它评审的那个被改对象属于谁定」——同一批次表里，`resume-review-systemd-plan-current-rX` 与 `resume-review-stream-route-current`（同样的「resume-review-X-current」命名模式）却正确按目标对象分类了。这证明分类不一致不是体裁本身导致的必然结果，而是同一批人为判断在不同目标文档上执行不一致。

**跨批次证据**：这 9 份文件分布在 batch-03 与 batch-04 两份不同的分类表里，是两个独立 agent 的判断，符合任务预期的「同族文件被切进不同批次、各批各判」的风险模式，但这次不是分散成 `UNCLASSIFIED`，而是分散成两个不同的**正式话题**，因此没有被 3 篇门槛的安全网拦住。

**建议**：把这 9 份文件从 `.dev/docs/documentation-restructure/reports/` 移到 `.dev/docs/anthropic-responses-bridge/reports/`（7 份：`260807-resume-review-implementation-current-r2..r7.md`、`260807-resume-review-implementation-post-s3.md`）与 `.dev/docs/service-cutover/reports/`（2 份：`260807-resume-review-readiness-current.md`、`260807-resume-review-readiness-current-r2.md`）。

## 次要发现（中等把握）：一处未记录的静默重分类

`260807-audit-resident-byte-budget-squash.md` 在批次分类表（`260821-classify-batch-02.md:25`）中被判为 `UNCLASSIFIED`，理由是「新话题（delivery 内存/字节预算、reservation/lease），现有 slug 均不覆盖，且本批仅 1 个文件，不足 3 个门槛」，置信度 `high`。但它实际落在 `.dev/docs/anthropic-responses-bridge/reports/` 目录下，而 README 只记录了两次事后合并（`copilot-token-identity`、`git-housekeeping`），未提及这一份。

逐字读了该文件：内容是 `src/app/delivery/reservation.py`、`anthropic_sse.py`、`responses_anthropic_stream.py` 的 resident-byte reservation/lease 功能 squash 审计，与另外 5 份已经分在 `anthropic-responses-bridge` 下的同族文件（`260807-review-resident-byte-budget.md` 等，同样评审这几个 delivery 模块）内容连续、对象一致。**判断：把它归入 `anthropic-responses-bridge` 在内容上站得住**（同族的其余 5 份都在，若单独把这 1 份扔进 `tmp/` 或另立话题反而割裂了同一 squash 决策链）。

但这是一次未留痕的裁决改判——批次表给出的是「high 置信度、新话题」，最终却被合并方悄悄改判进了一个既有话题，而 README 的「合并说明」一节没有覆盖它。按项目规则 `record-what-not-adopted`，这类偏离批次表结论的改判应当留痕说明理由，供后续审计复核，目前这一步是缺失的。

## 全部 13 份 `.dev/docs/tmp/` 未分类文件核实通过

逐字读完全部 13 份（`260807-final-review-current-main.md`、`260807-resume-audit-systemd-bridge-overlap.md`、`260807-review-backup-r3-living-checkpoint.md`、`260807-review-deployment-docs-r3.md`、`260807-review-deployment-plans-r2.md`、`260807-review-identity-living-checkpoint.md`、`260807-review-living-after-main-replay-r2.md`、`260807-review-main-foundations-systemd.md`、`260807-review-reservation-wiring-living.md`、`260807-review-resident-living-checkpoint.md`、`260807-verify-main-foundations-systemd.md`、`260820-review-session-closeout.md`、`260820-system-reminder-wire-shapes.md`）。

- 前 11 份全部是同时联合复评 `anthropic-responses-bridge/implementation.md`、`systemd-runtime/plan.md`、`service-cutover/readiness.md` 中两到三份的「living checkpoint」报告，报告本身就是「同时核对两个及以上话题当前状态是否一致」，拆给任何一个话题都会丢掉另一半，`UNCLASSIFIED` 判断正确、依据充分。
- `260820-review-session-closeout.md` 是对另一次会话收尾产物（`DISPOSITION.md`、新记忆条目、`.dev/tools/git-hunks.py`）的独立复核，是流程记录而非产品话题，`UNCLASSIFIED` 正确。
- `260820-system-reminder-wire-shapes.md` 是对 copilot-api-js history 库里真实上行 body 中 `<system-reminder>` 形态的取证普查，与现有任何话题（bridge/systemd/hosted-web-search 等）都不重合，`UNCLASSIFIED` 正确。

未发现应予改判的未分类文件；也未发现这 13 份里藏着另一个够 3 篇门槛却被拆散的同族簇。

## `anthropic-responses-bridge` 垃圾桶检验：未发现异常

抽查的 6 份（`260806-arbitrate-empty-content-turn.md`、`260807-audit-usage-replay.md`、`260807-review-implementation-current-r2.md`、`260807-audit-resident-byte-budget-squash.md`、`260820-copilot-api-js-reasoning-identity.md`、`260807-review-main-network-retry.md`）逐一确认都是围绕 request/response converter、reasoning carrier、resident byte budget、network retry、item identity 等 bridge 主链路具体机制的裁决或代码评审，均可定位到具体源码文件与行号，没有出现「找不到更合适位置就扔进最大话题」的迹象。193 份的体量是该话题本身评审轮次极多（很多文件是同一功能的 R2～R8 迭代复评）造成的,不是误分类堆积。

## 词根聚类扫描:其余跨话题簇均为合理区分

对全部 417 个文件名做了词根聚类（剔除 review/audit/verify/r2 等体裁词后按剩余词分组,取出现次数 ≥3 且跨多个话题的簇,共 46 组）。逐组过了一遍,除上述「implementation/readiness 的 resume-review 系列」外,其余簇均为合理的跨话题区分,例如:

- `systemd`（43 处命中,含 UNCLASSIFIED）:UNCLASSIFIED 的 3 处均为已核实的 bridge+systemd 联合评审,其余全部正确分到 `systemd-runtime`。
- `bridge`（42 处,含 UNCLASSIFIED）:UNCLASSIFIED 的 1 处（`260807-resume-audit-systemd-bridge-overlap.md`）已核实为合理跨话题文件。
- `code`（43 处,跨 bridge/systemd/hosted-web-search/lifecycle-reorg）:抽查确认 `260816-lifecycle-code-review.md` 分到 `lifecycle-reorg`、`260807-audit-systemd-code-replay-resume.md` 分到 `systemd-runtime` 均正确,是同一体裁词「code」出现在不同产品模块的正常现象,不是误判。
- `identity`（13 处,跨 UNCLASSIFIED/bridge）:UNCLASSIFIED 的 4 处正是已经修复的 `copilot-token-identity` 话题（token 交换身份）,与分到 bridge 的「item/response identity」（reasoning item 编号稳定性）是两个不同概念,现有区分正确。
- `squash`／`backup`／`resident`／`budget`／`foundations`／`token` 等簇里出现的 UNCLASSIFIED 单点,全部对应已知的两次跨批次补救（`copilot-token-identity` 4 份、`git-housekeeping` 5 份）覆盖的文件,没有遗漏。

未发现除「主要发现」外的第二个够 3 篇门槛却被拆散到多个话题或多次判成 UNCLASSIFIED 的同族簇。

## 未采纳的怀疑方向

- 曾怀疑 `260807-audit-readme-drift.md`、`260807-doc-state-dependency-dag.md` 是否应类比「implementation-current」问题一并挪去 bridge——读后判断不成立:这两份评审的是 README 跨文档导航链接、7 份正式文档间的同步依赖图,对象是「文档体系结构本身」而非某一份 living 文档的候选状态,与 BRIEF 里 `documentation-restructure` 的定义（文档链接审计、蒸馏矩阵）吻合,维持现状。
