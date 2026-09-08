# 2026-09-08 `.dev/docs` 全量并入后最终状态独立审阅

**评审范围**：以 `/home/xp/src/ghc-api-proxy-py` 当前工作树为准，审查 `.dev/docs/` 全量并入后的退役准备状态。判据先取自 `dotdev-repository-repair/README.md`、`reports/260908-inventory-review.md` 与 `subtopics/260908-retirement-reference-map.md`；随后核查 25 个保留主题的 current/living Markdown、全部 2026-09-08 migration reports、`history`／`httpx2-migration`／reasoning carrier／timeout-408／graceful shutdown 与 systemd 的更新，以及本轮 canonical history 迁移。明确不把 repair README、reports、subtopics 或迁移说明中的旧路径表反算为 current consumer；不审查产品改动是否适合合并，不修改被检材料。

**总体 verdict**：**needs-fix，尚未满足整体进入退役阶段的条件。** 本轮已正确迁走绝大多数承重证据，现有 canonical history 未见明显重复或丢失，reasoning carrier、timeout-408、shutdown/systemd 的核心状态结论也成立；但仍有 4 个 major 门未闭合：`history` 漏迁一项仍待确认的 HTTP 查询面、`documentation-restructure` 仍被 living 文档直接消费、顶层 `tmp/` 仍有 77 份未完成逐份处置、`httpx2-migration` 的步骤 4 与运行时 logger 配置仍未闭合。可以先退役 12 个已满足独立目录门槛的候选，但不能按 README 的全局顺序把本轮视为“迁移完成、全面开始删除”。

**blocker 数**：0（major 4、minor 3）。

## Findings

### MSR-01（major）：`history` 仍有一项 living 待确认事项未迁出

**primary_location**：`.dev/docs/history/decisions.md:98`

**related_locations**：

- `.dev/docs/dotdev-repository-repair/README.md`「退役前必须完成的迁移」第 2 项；
- `.dev/docs/upstream/retry-and-continuation/deferred.md:321-339`；
- `.dev/docs/upstream/retry-and-continuation/reports/260908-history-pending-migration.md`。

`decisions.md` 第五节在重定范围后明确写道：原先用户要求的“完整 HTTP 支持”因完整取证库前提消失而需要重新确认；若仍要查询面，查询对象应改成 `requests-*.jsonl` 与 `rejected/*`。这不是 `spec.md` §9 那六项已被后续代行裁决取代的旧文字，而是**重定后的现行节内明确标成“待确认”**的事项。

本轮只迁了 `decisions.md` §6.1、§6.2。两项迁入内容与原文逐字一致，且在 successor 中正确保留为“需用户裁决／暂缓建议，不是永久否决”；但第 98 行这一项仍只存在于准备退役的旧 topic。现在退役 `history` 会丢掉一个尚未闭合的用户可观察查询面问题。

**最小修正**：把这一个待确认项迁入一个 retained living deferred owner，并保留“旧完整取证库前提已消失、查询对象已改变、需重新确认”的射程。按现有归属，优先考虑 `upstream/retry-and-continuation/deferred.md`；若查询 API 的 owner 另定，则必须在退役前给出唯一 current carrier。

### MSR-02（major）：R-13 仍未完成，`documentation-restructure` 仍是 current consumer 的有效链接目标

**primary_location**：`.dev/docs/anthropic-responses-bridge/implementation.md:239`

该 living implementation 表仍以可解析 Markdown link 指向 `../documentation-restructure/README.md`，并继续让旧主题承载“整理 live 入口、提炼有效结论、按主题归档”的当前目标。reference map 的 R-13 已要求改指 `dotdev-repository-repair/README.md` 或删除该表行；全部 2026-09-08 migration reports 中没有一份关闭 R-13。

这不是历史文字或 code span provenance，而是唯一仍指向 14 个普通退役候选之一的 current Markdown dependency。因此 `documentation-restructure` 现在不能退役。

**最小修正**：只改这一行的 owner 指针与状态文案，使 repository repair README 成为唯一 current carrier；复扫后再退役旧主题。

### MSR-03（major）：顶层 `tmp/` 的直接引用已清零，但 77 份材料尚未完成逐份归口／删除判断

**primary_location**：`.dev/docs/tmp/`

**related_locations**：

- `.dev/docs/dotdev-repository-repair/README.md`「TUI 范围内的临时材料」与执行顺序第 2 步；
- `.dev/docs/dotdev-repository-repair/subtopics/260908-tui-tmp-disposition.md`；
- `.dev/docs/tmp/260907-interaction-context-design.md`；
- `.dev/docs/tmp/260908-review-upstream-failure-backoff.md`。

账目闭合：并入后 93 份，已由 migration reports 从顶层迁走 16 份，当前正好剩 77 份。25 个保留主题的 current/living 安全超集扫描已不再发现指向某个顶层 `tmp` 文件的链接或 code-span path；此前 18 个文件名／21 个引用行的承重引用迁移已闭合。

但“没有 current 入站”不等于“可删除”。现有 TUI disposition 只对原 26 份关键词候选给过归属建议，其中 9 份随后迁走、17 份仍留在 `tmp/`；其余 60 份没有一份当前的逐项最终处置表。余项里还明显包含不可直接删除的活性材料，例如：

- `260907-interaction-context-design.md` 是完整的长期 API／数据流设计，不是一次性命令残片；
- `260908-review-upstream-failure-backoff.md` 含 blocker／major 评审、实现方处置和待用户追认的人控 Spec 候选。

因此 README 的执行顺序第 2 步未完成，`tmp` 目录机制仍应保留，且不能把余下 77 份批量视为无长期价值。

**最小修正**：先生成 77 行的最终 disposition ledger。可直接复用已给出建议的 17 行，只需重新核对当前 owner；其余 60 行至少判定 canonical destination／可删除／需新建 retained topic 三选一。优先迁走 2026-09-07、2026-09-08 两份显然仍活跃的材料。

### MSR-04（major）：`httpx2-migration` 的条件退役前置仍真实存在

**primary_location**：`.dev/docs/httpx2-migration/plan.md:186-193`

**related_locations**：

- `.dev/docs/httpx2-migration/reports/260908-residual-audit.md`；
- `pyproject.toml:16`；
- `src/app/observability/logging.py:198-199,216`。

Plan 已诚实标出步骤 4 `deferred，未完成，继续 living`，`pyproject.toml` 仍正确指向该 living Plan。本次复核也确认运行时代码仍只把 `"httpx"`、`"httpcore"` logger 提升到 `WARNING`，而当前库使用 `httpx2`／`httpcore2` logger；这不只是散文旧名。其余 current-stack prose 复核账也尚未关闭。

这不是 migration report 的误报，而是实际未完成项。因此 `httpx2-migration` 必须保留，直到源码 owner 处理三个 deferred、验证 logger 筛噪、复扫并更新或移除 `pyproject.toml` 指针。

### MSR-05（minor）：`archived-2604-rewrite` 已无承重 consumer，但三个 living code span 仍会在删除后变成陈旧路径

**primary_location**：`.dev/docs/graceful-shutdown/client-side/README.md:124`

**related_locations**：

- `.dev/docs/server-layout/README.md:36`；
- `.dev/docs/systemd-runtime/plan.md:211`。

三处都属于已作废、禁止作为依据或负面例子的历史叙述，不消费旧目录内容；R-06～R-12 所需的真实证据原件已经迁到 retained topic history。它们不会要求继续保留旧主题，但目前仍以 code span 写成可定位的旧路径。reference map 已要求把它们改成无 target 的退役历史文字。

**最小修正**：删去三处具体目录 target，保留“旧设计已退役／不能证明现行行为”的语义。完成后 `archived-2604-rewrite` 可退役。

### MSR-06（minor）：两份 migration reports 内共有 5 个自称可解析、实际从报告位置不可解析的链接

**primary_location**：`.dev/docs/graceful-shutdown/reports/260908-pidfile-evidence-migration.md:21-24`

**related_locations**：

- `.dev/docs/hosted-web-search/reports/260908-external-reference-relink.md:6`。

graceful-shutdown 报告表中的 4 个 `history/...` links 是从 `restart-handover/README.md` 复制来的 target；从报告所在的 `graceful-shutdown/reports/` 解析会落到不存在的 `reports/history/`。Hosted web search relink 报告先放了一条适用于 `status.md` 的 `../anthropic-direct-request-shape/...` Markdown link，随后才给出报告自身正确的 `../../...` link；前一条在报告内是断的。

canonical destinations 与真正 living consumers 的链接均有效，所以这是报告可读性／可点击性问题，不是证据丢失。

### MSR-07（minor）：reasoning carrier 与 timeout-408 的 living 状态页把审计时 SHA 写成持续“当前 checkout”

**primary_location**：`.dev/docs/reasoning-carrier/tracking.md:3`

**related_locations**：

- `.dev/docs/timeout-408/status.md:3,28`；
- 两主题的 `reports/260908-status-refresh.md`。

两页写 `HEAD d7e71c19`；本次最终复核时实际 `main` HEAD 为 `d0a4fc8b8fcc2306498f35601e73bb3a61f5983a`，且 `d7e71c19` 是其祖先。核心实现提交 `b9b0a9bf`、`33cf3870` 也都仍是当前 HEAD 的祖先，相应符号仍在，所以“main 已集成”的结论成立。问题只在 living 页把一次审计基线表述成了会持续为真的当前身份。

**最小修正**：将 living 页改成“2026-09-08 审计基线为 d7e71c19；当前 main 仍应现场复核”，或刷新为当前 SHA；日期报告可保留点时 SHA。

## 五组更新结论复核

| 主题 | 结论 | 证据与权威边界 |
|---|---|---|
| `history` | **部分通过，仍不可退役** | §6.1／§6.2 已逐字迁入 `upstream/retry-and-continuation/history/decisions-20260821.md`，living deferred 保持“需用户裁决”“暂缓建议，不是永久否决”；源码事实仍成立。MSR-01 的 §5 HTTP 查询面待确认项漏迁。 |
| `httpx2-migration` | **报告可读且结论成立，不可退役** | `plan.md`、residual audit、当前 logger 配置三者一致；没有把迁移历史数字冒充当前验证。 |
| `reasoning-carrier` | **核心更新通过** | `b9b0a9bf` 为 current HEAD 祖先；`CarrierRecord`、v2 encode/decode 与调用链在位；报告明确 production／真实 upstream 未验证，没有把代码事实写成用户裁决。仅有 MSR-07 的 baseline 表述漂移。 |
| `timeout-408` | **核心更新通过** | `33cf3870` 为 current HEAD 祖先；`_run_dispatch_while_connected`、stream cleanup 符号与阶段 ownership 在位；远端 408 根因、retry/H2 策略仍保持遗留／独立裁决边界，没有由历史报告倒写为已解决。仅有 MSR-07。 |
| graceful shutdown / systemd | **整理结论通过；`systemd-runtime` 不可退役** | S3 `c53849e2`、S4 `e9fb2771` 都是 current HEAD 祖先；S7 摘要已移入 runtime history，并由 `systemd-rolling` Spec/Plan 独占 current owner。S5 仍因缺独立 user manager 与 delegated cgroup v2 而 `BLOCKED`，没有被 static verify/direct-fd 绿灯冒充完成，也没有被写成用户裁决。 |

## 25 个保留主题的路径依赖复扫

本轮对 25 个主题中排除 `reports/`、`history/`、`archive*` 后的 **111 份 Markdown 安全超集**扫描 Markdown links、code spans、`.dev/docs/<topic>/...` 与相对路径；这个集合故意包含 review disposition、topic-local `tmp/` 和迁移说明，范围大于 reference map 的 88 份 current/living 集。

### 当前实际依赖

- 唯一仍指向普通退役候选的 current Markdown link：`anthropic-responses-bridge/implementation.md:239` → `documentation-restructure/README.md`（MSR-02）。
- 指向顶层旧 `history` topic 的 current path：0。
- 指向顶层 `tmp` 某个文件的 current link/code path：0。
- 指向 `sync-refs`、`count-tokens`、`empty-text-block`、`git-housekeeping`、`hooks-subscription-migration` 的旧 current paths：0。
- 所有新 canonical history links 均解析。

### code span path 与纯历史文字

- `graceful-shutdown/client-side/README.md:124`、`server-layout/README.md:36`、`systemd-runtime/plan.md:211` 的 `archived-2604-rewrite` 路径是作废／禁止引用／负面例子，不是 current evidence consumer；见 MSR-05。
- `hosted-web-search/260908-external-reference-migration-note.md:9-12` 的四个旧 target 是迁移控制表；实际 consumer 已改链，不计 current consumer。
- `auto-mode-classifier/spec.md:199` 的 `.dev/docs/tmp/` 只解释历史报告原件为什么保留旧路径，没有点名现存 tmp 文件。
- `anthropic-responses-bridge/review-disposition-tool-whitelist.md:32` 泛指旧 tmp 调查，且本身是 disposition，不构成 living file dependency。
- `archive/260807-copilot-token-identity@...` 是 immutable Git ref 名；`count-tokens` endpoint 与 `tui/archive-count-tokens-line/` 也不是同名退役 topic 路径。

对 111 份文件共解析 698 个本地 Markdown links；脚本报告的两个“断链”均是正文 regex 字面量 `[?:7|8]` 被朴素 parser 误识别，不是真正 Markdown link。未发现其它 current local link 断裂。

## Canonical history 与 src/dst 完整性

- 28 份 migration reports 声明的 canonical moved originals 均满足：destination 存在、live source 不存在、同 basename 在 `.dev/docs/` 唯一。
- 其中 24 份在旧嵌套源 `.dev/.dev/docs/` 仍有 pre-move 原件，逐份 SHA-256 与 destination 相同。
- 4 份 2026-09-06 token-counting 原件（local tokenizer analysis、transcript evidence、erratum、code audit）不在旧嵌套源，因而无法用该源独立复核 pre-move bytes；当前 destination、状态边界、erratum 共址、living links 与 basename 唯一性均成立，未见明显丢失或重复。其“内容未改写”记为 source-hash unavailable，而不是反证。
- `history/decisions.md` §6 迁入副本从“六、实施完成”起与源节 1017 字符逐字一致。
- reasoning carrier 的旧 snapshot 与 systemd S7 handoff history 均存在，current owner links 可解析；S7 摘要覆盖旧 Plan 的状态、目标、设计前置和验收意图，并明确不得作为 current design。
- 全部 12 份名称含 `migration` 的 2026-09-08 文件（其中包括 external migration note）及配套 external relink report 均可读取；共检查 50 个本地 report links，除 MSR-06 的 5 个报告自身相对路径问题外均解析。

## 候选逐项状态

| 候选 | 最终当前状态 | 是否可退役 |
|---|---|---|
| `architecture-audit` | 仅 9 份时点 reports；无 living 入站 | **可** |
| `archived-2604-rewrite` | 承重原件已迁；只剩 3 处 living 负面／历史 code-span path | **暂不可**；先做 MSR-05 |
| `copilot-token-identity` | 仅 4 份时点评审／审计／验证；命中均为 Git archive ref | **可** |
| `count-tokens` | 被 TUI 引用的原件已迁至 `token-counting/history/`；无旧入站 | **可** |
| `docs-tmp-migration` | 已完成的过程材料；无 living 入站 | **可** |
| `documentation-restructure` | 仍被 `anthropic-responses-bridge/implementation.md` 直接链接并承担 current 整理目标 | **不可**；MSR-02 |
| `early-verification` | 历史验收快照；无 living 入站 | **可** |
| `empty-text-block` | 承重报告已迁至 `delivery-keepalive/history/`；无旧入站 | **可** |
| `git-housekeeping` | 两份承重 provenance 已迁；其余均为仓库过程记录 | **可** |
| `history` | §6.1／§6.2 已迁，但 §5 的 HTTP 查询面仍待确认且未迁 | **不可**；MSR-01 |
| `hooks-subscription-migration` | 承重 beta-strip 原件已迁；无旧入站 | **可** |
| `lifecycle-reorg` | 仅时点评审／closeout；无 living 入站 | **可** |
| `pipeline-rewrite-parity` | 仅旧项目对照调研；无 living 入站 | **可** |
| `sync-refs` | 两份 current-consumed 原件已迁；余项为一次性调研 | **可** |
| `test-infrastructure` | 仅 PoC／hang／hygiene 时点记录；无 living 入站 | **可** |
| `httpx2-migration` | Plan 仍是 living residual，`pyproject.toml` 有指针，步骤 4 与 logger 行为未闭合 | **不可**；MSR-04 |
| 顶层 `tmp/` | 机制按判据继续保留；77 份材料未完成逐份 disposition，但已无 current 直接文件引用 | **目录不可退役，内容不可批量删除**；MSR-03 |
| `systemd-runtime` | S7 已移交，但 S5 是唯一未闭合运行时门 | **不可**；在具备 user manager／delegated cgroup v2 的隔离环境完成 S5 后重审 |

结算：16 个目录候选（14 普通候选加 `history`、`httpx2-migration`）中，**12 个可退役、4 个仍不可退役**。`tmp` 是保留机制；`systemd-runtime` 是 retained living topic，不进入本批目录删除。

## 最小下一步

1. 迁出 `history/decisions.md:98` 的 HTTP 查询面待确认项。
2. 关闭 R-13：把 `anthropic-responses-bridge/implementation.md:239` 改指 repository repair current owner。
3. 把三个 `archived-2604-rewrite` code-span paths 改成无 target 的历史文字。
4. 建立 77 份 tmp 最终 disposition ledger，并优先迁走 2026-09-07／09-08 的活性材料；不需要等所有候选目录一起删除，已就绪的 12 个可作为第一批。
5. `httpx2-migration` 按现有 Plan 修完三个 deferred、验证 `httpx2`／`httpcore2` logger 筛噪并处理 `pyproject.toml` 指针；`systemd-runtime` 另在合格隔离环境完成 S5。
6. 修正两份 migration reports 的 5 个相对链接，并把 reasoning/timeout living 页的 SHA 改成点时基线表述。
7. 复跑同一 25-topic 安全超集扫描与仓库级 literal path scan；只有结果不再含未解释 current consumer，才进入 README 的删除与 `.dev` re-root 步骤。

## 搜索面与未覆盖面

**读过**：三份判据全文；全部 2026-09-08 migration reports及配套 relink/note；history 迁入源、目标与 current deferred；httpx2 residual report 与 living Plan；reasoning/timeout status refresh 与 living 页；shutdown/systemd consolidation、runtime Plan、S7 history、restart-handover；TUI tmp disposition；两份最新 tmp 活性材料；所有 candidate 文件清单。

**执行过**：25-topic 路径形态扫描；698 个 current/safe-superset 本地 Markdown links 解析；13 份 migration/relink 文档的本地 links 解析；28 对 moved original 的 source/destination、basename 与 hash 核验；history §6 精确文本比较；main HEAD 与四个关键实现提交的 ancestor 检查；reasoning、disconnect cleanup、rejection capture、upstream gap 与 httpx logger 当前源码符号检查；`.dev` 与 nested source 文件计数／status 只读盘点。

**未覆盖**：没有逐份阅读全文判定剩余 77 个 tmp 文件的最终归属——这正是 MSR-03 所指出仍未完成的实施工作；没有重跑源码测试，因为本任务是文档最终状态只读审阅，且核心状态结论已用 current source/git 重新取证；没有把 archive/history 内部故意保留的点时旧链接纳入“必须可点击”的本轮门槛。
