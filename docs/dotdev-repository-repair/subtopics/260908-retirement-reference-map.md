# `.dev/docs/` 退役准备：入站引用与证据迁移地图

**评审范围**：以 2026-09-08 当前工作树为快照，扫描分类表中 25 个“保留”主题的 current/living Markdown，对 14 个退役候选、`history` 与 `httpx2-migration` 两个条件退役主题，以及顶层 `.dev/docs/tmp/` 的入站路径引用进行分类。只判断文档依赖与迁移目的地，不复核被引报告的全部事实结论，不把退役候选自身、`reports/`、`history/`、`archive-*` 内的历史互引算成 live dependency。

**总体 verdict**：**needs migration**。退役前仍有承重路径要迁移和改写；顶层 `tmp/` 有 18 个文件名被 living 文档直接点名，其中 16 份仍在 `tmp/`，另 2 份已不在 `tmp/`、实际位于 `delivery-keepalive/reports/`。`history` 的两项待裁决内容已经迁入 `upstream/retry-and-continuation/`，但 living 文档中仍有 4 处旧主题路径/归属叙述待清理。

**blocker 数**：0。这里的“needs migration”不是删除否决票；它表示在下表的迁移与改链完成前，按仓库修复 README 的门槛不能安全删除相应目录或清空 `tmp/`。

## 1. 扫描方法与覆盖范围

1. 判据先读：`.dev/docs/dotdev-repository-repair/README.md` 与 `reports/260908-inventory-review.md`。分类、候选集合、living/history 边界与“先迁证据、再改入站路径”的顺序均取自这两份文件。
2. 源集合：逐目录枚举 25 个保留主题。先对除 `reports/`、`history/` 外的 **133 份 Markdown** 做安全超集扫描，再排除路径中的 `archive-*`、topic-local `tmp/`、文件名为 `*review-disposition*`/`*-reply.md` 的点时材料，得到 **88 份 current/living 或导航文档**。current 集包含 README、Spec、status、decisions、deferred、plan、tracking、design、architecture、acceptance、research、readiness、findings 及仍在用的嵌套主题 README。
3. 形态扫描不是只搜关键词：对每一行同时识别 Markdown inline link target、反引号 code span 中的相对/仓库绝对路径、`.dev/docs/<topic>/...`、`../<topic>/...`、多级 `../../tmp/...`，再人工读取命中行前后文，区分“当前条款依赖”“证据/裁决沿革”“已作废段落”“反例/不得引用警告”“仅同名产品术语”。reference-style link 即使 target 单独成行，也会因目标路径段命中。
4. 目标核验：逐一检查被点名文件是否存在，并读取承重来源的标题、性质、关键节或引用位置。所有退役候选目标均存在；`tmp` 的两个 keepalive 文件名在顶层 `tmp/` 不存在，但同名文件已位于 `delivery-keepalive/reports/`。
5. 排除规则：历史报告内部写着旧路径，只证明报告当时读过什么，不构成 living 入站依赖；例如 `anthropic-responses-bridge/archive-260808/`、`service-cutover/archive-260808/`、`upstream/.../archive-*` 中对 `tmp/` 的链接均不进入执行清单。`archive/260807-copilot-token-identity@...` 是 Git archive ref 名，不是 `.dev/docs/copilot-token-identity/` 路径。`count-tokens` 端点名与 `tui/archive-count-tokens-line/` 也不是退役主题引用。

### 1.1 当前快照相对 inventory review 的变化

`reports/260908-inventory-review.md` 记录 `history/decisions.md` §6.1、§6.2 尚待迁移；当前工作树已经完成这一步：`upstream/retry-and-continuation/deferred.md:321,331` 已把两项保持为待用户裁决，原始上下文已复制到 `upstream/retry-and-continuation/history/decisions-20260821.md`。因此本地图不再把旧 `history/decisions.md` 当承重目标，只把剩余旧路径叙述列为改写项。`.dev` 是并行共享工作树，执行迁移前必须重跑行号与路径扫描。

## 2. 候选总览

下表的“入站”只指上述 88 份 current/living 文档；报告、archive 与退役主题之间的历史互引不计入。

| 候选 | living 入站结论 | 处置摘要 |
|---|---|---|
| `architecture-audit` | 无 | 可进入候选退役复扫。 |
| `archived-2604-rewrite` | 有；8 个引用行，其中 5 行承载当前约束/证据，3 行只是历史或负面叙述 | 按消费者拆出必要证据到 `anthropic-responses-bridge/history/`、`hosted-web-search/history/`、`delivery-keepalive/history/`；不要整目录继续充当 current authority。 |
| `copilot-token-identity` | 无 | 命中仅为 `archive/260807-copilot-token-identity@...` Git ref，非文档路径。 |
| `count-tokens` | 有；`tui/deferred.md:37` | 把被引报告归入 `token-counting/history/`，TUI 跨主题改链。 |
| `docs-tmp-migration` | 无 | 可进入候选退役复扫。 |
| `documentation-restructure` | 有；`anthropic-responses-bridge/implementation.md:239` | 当前目标已由 repository repair README 承接，改链后旧 README 不再承重。 |
| `early-verification` | 无 | 可进入候选退役复扫。 |
| `empty-text-block` | 有；`delivery-keepalive/spec.md:5,66,80` | 同一评审报告迁入 `delivery-keepalive/history/`；其中 `:5,:66` 承重，`:80` 位于已作废原文。 |
| `git-housekeeping` | 有；`direct-passthrough/spec.md:871` 同行两份报告 | 迁入 `dotdev-repository-repair/history/` 并改两条 link target。 |
| `history` | 有；4 个 living 引用行 | 待裁决内容已迁完；修正 `upstream/h2-goaway/` 两处过时 ownership 叙述，清掉 `retry-and-continuation/deferred.md` 两处迁入前旧路径。 |
| `hooks-subscription-migration` | 有；`hosted-web-search/status.md:83` | beta-strip 实施证据归 `anthropic-direct-request-shape/history/`。 |
| `lifecycle-reorg` | 无 | 可进入候选退役复扫。 |
| `pipeline-rewrite-parity` | 无 | living 文档无入站；命中只在历史报告。 |
| `sync-refs` | 有；5 个 living 引用行、2 个目标文件 | 归 `anthropic-direct-request-shape/history/`，`direct-passthrough` 保留跨主题证据链接。 |
| `test-infrastructure` | 无 | 可进入候选退役复扫。 |
| `httpx2-migration` | 保留主题 living 文档内无入站 | **不是全仓无引用**：repository repair README 已知 `pyproject.toml` 仍指向其 `plan.md`，且步骤 4 尚未闭合；条件退役前另按该前置处理。 |
| 顶层 `tmp/` | 有；21 个引用行、18 个唯一文件名 | 见第 4 节；16 份需迁出，2 份只需纠正已经过时的 `tmp/` 叙述。 |

## 3. 承重引用执行清单（退役候选与条件退役主题）

“需要改写路径”回答的是完成推荐迁移后引用方是否必须动；本节所有 `是` 都应在同一个迁移变更中完成，不能先移动再留断链。推荐文件名是落点建议，不是授权移动。

| ID | 引用方:line | 当前目标与引用形态 | 证据性质 | 推荐目的地/动作 | 需要改写路径 |
|---|---|---|---|---|---|
| R-01 | `anthropic-direct-request-shape/README.md:22` | code span `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62` | 主题成立的直接历史前因：真实探针记下 `claude-sonnet-5` 不支持 Responses API；报告是时点证据，不是 current authority | 完整报告迁入 `anthropic-direct-request-shape/history/260822-round2-disposition.md`；README 改成有效相对 link，并继续由 current Spec 解释射程 | 是 |
| R-02 | `direct-passthrough/deferred.md:41` | code span `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` | D-4 射程证据；同一探针说明 Claude 模型为什么只能走直连 | 指向 R-01 的 `../anthropic-direct-request-shape/history/260822-round2-disposition.md`，避免复制同一报告两份 | 是 |
| R-03 | `direct-passthrough/spec.md:95` | code span，同 R-01 | 当前 route 状态表的可达性证据 | 同 R-02，跨主题指向唯一历史原件 | 是 |
| R-04 | `anthropic-direct-request-shape/spec.md:117` | code span `sync-refs/.../260822-vscode-copilot-chat-reasoning-values.md` | 第一方客户端时点考据；用于限定“形状可采纳、effort 枚举不可照抄” | 迁入 `anthropic-direct-request-shape/history/260822-vscode-copilot-chat-reasoning-values.md`；保留报告的 archived-repo/version 限定 | 是 |
| R-05 | `anthropic-direct-request-shape/spec.md:428` | absolute code path `.dev/docs/sync-refs/.../260822-vscode-copilot-chat-reasoning-values.md` | Spec 证据来源表中的点时报告 | 与 R-04 指向同一新位置，并改成相对 Markdown link | 是 |
| R-06 | `anthropic-responses-bridge/architecture.md:492` | code span `../archived-2604-rewrite/history-system.md` | current Architecture 用它约束默认持久化保持轻量；目标是旧目标设计，不是一手用户裁决 | 把支撑“轻量终态一次写入”的必要原始切片迁入 `anthropic-responses-bridge/history/2604-history-system.md`，或在 Architecture 内完整写明当前约束并把旧件仅作 provenance；不得继续把已判整体过期的主题当 authority | 是 |
| R-07 | `anthropic-responses-bridge/hosted-web-search-spec.md:323` | code span `../archived-2604-rewrite/tool-use.md:23` | current Spec 的“不在 400 后剥离重试”沿革证据；旧文档记录设计边界，但未在本次核到一手用户逐字裁决 | 把 `tool-use.md` 的相关历史快照迁入 `hosted-web-search/history/2604-tool-use.md`；现行规范继续以本 Spec 条款为 authority，避免把旧稿升级成“用户裁决” | 是 |
| R-08 | `anthropic-responses-bridge/hosted-web-search-spec.md:545` | Markdown link `../archived-2604-rewrite/tool-use.md` | “当前已实现边界”来源索引之一 | 与 R-07 合并到 `hosted-web-search/history/2604-tool-use.md` | 是 |
| R-09 | `anthropic-responses-bridge/hosted-web-search-spec.md:545` | Markdown link `../archived-2604-rewrite/anthropic-compat.md` | 旧 Anthropic 兼容矩阵/请求整形快照；只适合做历史背景 | 必要快照迁入 `hosted-web-search/history/2604-anthropic-compat.md`，并在 link 文案明确“历史边界”，不要称 current authority | 是 |
| R-10 | `anthropic-responses-bridge/hosted-web-search-spec.md:545` | Markdown link `../archived-2604-rewrite/hooks-system.md` | 旧 hooks 生命周期/阶段设计快照 | 必要快照迁入 `hosted-web-search/history/2604-hooks-system.md`，或若 current Spec 已自足则删除该证据项；两种做法都要消除旧 target | 是 |
| R-11 | `delivery-keepalive/decisions.md:158` | absolute code path `.dev/docs/archived-2604-rewrite/streaming-resilience.md:284-288` | 删除旧配置键时对“原始设计意图确被取代”的 provenance；current decisions 已自足描述现状 | 将旧文档或至少相关配置表的保真快照迁入 `delivery-keepalive/history/2604-streaming-resilience.md`，注明它从未是 current config truth | 是 |
| R-12 | `delivery-keepalive/decisions.md:167` | absolute code path，同 R-11 | 对旧件为何不回改的历史说明；与 R-11 共用证据 | 同 R-11；同时把“已移到 archived-2604-rewrite”改为新历史位置，避免迁移后叙述失真 | 是 |
| R-13 | `anthropic-responses-bridge/implementation.md:239` | Markdown link `../documentation-restructure/README.md` | current implementation 状态表仍用旧入口承载“live 入口、有效结论提炼、按主题归档”的剩余目标 | 改指 `../dotdev-repository-repair/README.md`，或删除该表行并由 repair README 独占仓库整理状态；旧 README 无需为此整体迁入 history | 是 |
| R-14 | `delivery-keepalive/spec.md:5` | code span `../empty-text-block/reports/260820-review-synthetic-start-fix.md` | 规范前言的缺陷背景/独立评审证据 | 报告迁入 `delivery-keepalive/history/260820-review-synthetic-start-fix.md`，与当前 keepalive Spec 共址 | 是 |
| R-15 | `delivery-keepalive/spec.md:66` | code span，同 R-14 | held-back block 同时熄灭两道 guard 的历史实测与回归来源 | 同 R-14；保留“历史缺陷、现已修复”的时间边界 | 是 |
| R-16 | `direct-passthrough/spec.md:871` | Markdown link `../git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition-recheck.md` | v22 修订的仓库脏文件处置复核 provenance，不是产品合同本身 | 迁入 `dotdev-repository-repair/history/260904-dotdev-dirty-inventory-disposition-recheck.md` | 是 |
| R-17 | `direct-passthrough/spec.md:871` | Markdown link `../git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus.md` | v22 候选合并复核 provenance | 迁入 `dotdev-repository-repair/history/260904-dotdev-merge-review-gpt-opus.md` | 是 |
| R-18 | `tui/deferred.md:37` | code span `../count-tokens/reports/260820-review-count-tokens-shared-pipeline.md:72` | TUI 未闭合项 F6 的更早共享 pipeline 证据 | 迁入 successor `token-counting/history/260820-review-count-tokens-shared-pipeline.md`；TUI 保持跨主题链接 | 是 |
| R-19 | `hosted-web-search/status.md:83` | code span `../hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md` | `strip_anthropic_beta_flags` 已实施与未采纳项的点时实现记录；current owner 已是 Anthropic request-shape | 迁入 `anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md`，并让 hosted-web-search status 跨主题改链 | 是 |
| R-20 | `upstream/h2-goaway/deferred.md:40` | absolute directory path `.dev/docs/history/` | 当前文字用旧 topic 归属来关闭“HistoryConsumer 未接线是否有意”的问题；退役后 ownership 断言会变假 | 不迁旧 `history` 主题；把句子改为指向同主题 `upstream/h2-goaway/findings.md` 中的结构化 request-log 结论或现行实现说明，删除旧 topic ownership | 是（改叙述/本地 link） |
| R-21 | `upstream/h2-goaway/findings.md:82` | absolute directory path `.dev/docs/history/` | 与 R-20 相同的 closure 事实；承重的是“旧链已归档且新记录能力有现行载体”，不是旧目录本身 | 在 `findings.md` 内直接写出现行 structured request log/JSONL owner，必要时链接 `upstream/retry-and-continuation/status.md` 或当前源码说明 | 是（改叙述/本地 link） |

### 3.1 路径命中但不是 current 承重依赖

这些条目必须与上表分开，避免为了保留一段纯历史叙述而错误延寿整个退役主题。

| 引用方:line | 当前命中 | 为什么不承重 | 退役时建议 |
|---|---|---|---|
| `delivery-keepalive/spec.md:80` | `../empty-text-block/reports/260820-review-synthetic-start-fix.md` | 位于“以下为作废前的原文，仅作记录”，前文已明确合成机制删除、无需再裁 | 因 R-14/R-15 会迁同一报告，顺手改到 `delivery-keepalive/history/`；不得把这行重新解释成当前待裁决。 |
| `graceful-shutdown/client-side/README.md:124` | `.dev/docs/archived-2604-rewrite/` | 删除线中的旧冲突关闭叙述，且正文明确该旧笔记不是设计依据 | 可改成“已退役的 2604 rewrite 学习笔记”而不保留路径；不为它单独迁 `shutdown.md`。 |
| `server-layout/README.md:36` | `.dev/docs/archived-2604-rewrite/` | 导航表中的“整体过期、不得引为依据”警告，不消费目录内容 | 删除目录后改成无路径的退役记录，或移到本 topic history 注记；不构成证据迁移前置。 |
| `systemd-runtime/plan.md:212` | `../archived-2604-rewrite/shutdown.md` | 只用作负面例子：“旧设计不能证明生产已接线” | 删掉具体路径或改成无链接的历史说明；不要把旧 shutdown 设计迁成 current evidence。 |
| `upstream/retry-and-continuation/deferred.md:321` | `.dev/docs/history/decisions.md` | 当前承重 link 已是同句的 `history/decisions-20260821.md`；旧路径只说明迁入前来源 | 改成“原 history 主题的 decisions §6.1”，不保留可解析旧路径。 |
| `upstream/retry-and-continuation/deferred.md:331` | `.dev/docs/history/decisions.md` | 同上，§6.2 已完整迁入并由 current deferred 承接 | 同上。 |

## 4. 顶层 `tmp/` 被保留主题 living 文档直接引用的全部条目

以下按**唯一文件名**列 18 项，并在“引用方”保留全部 21 个命中行。除两份 keepalive 文件外，其余 16 项当前都确实存在于 `.dev/docs/tmp/`。同一文件被多行引用时只迁一份，所有引用方在同一变更中改链。

| `tmp` 文件 | 引用方:line | 当前状态与证据性质 | 推荐目的地 | 需要改写路径 |
|---|---|---|---|---|
| `260822-review-beta-flag-strip.md` | `anthropic-direct-request-shape/spec.md:188`; `anthropic-direct-request-shape/status.md:91` | 存在；实施评审，证明按 `resolved_model` 匹配会让样例配置表空转，是 current key-matching 警告的历史证据 | `anthropic-direct-request-shape/history/260822-review-beta-flag-strip.md` | 是；两处一起改 |
| `260824-cache-control-scope-400-investigation.md` | `anthropic-direct-request-shape/spec.md:413` | 存在；`cache_control` 400 与实现缺口的只读调查，支撑 A-9 | `anthropic-direct-request-shape/history/260824-cache-control-scope-400-investigation.md` | 是 |
| `260827-deferred-survey.md` | `client-leg-formats/deferred.md:30` | 存在；八份 deferred 的点时清点，当前引用只用其核对两条“源码不支持已修声明” | `client-leg-formats/history/260827-deferred-survey.md`；若迁移者认为整份跨主题报告不宜归单一消费者，可保留一份 repository-repair history 索引，但不得继续留在 `tmp/` | 是 |
| `260820-review-keepalive-rulings.md` | `delivery-keepalive/spec.md:6` | **顶层 `tmp/` 不存在**；同名文件已在 `delivery-keepalive/reports/`，属于裁决落实/文档一致性评审 | 先把当前叙述直接改为 `reports/260820-review-keepalive-rulings.md`；该 topic reports 日后统一归档时再迁 `delivery-keepalive/history/` | 是；这是纠错，不是从 `tmp/` 搬文件 |
| `260820-review-keepalive-doc-fixes.md` | `delivery-keepalive/spec.md:6` | **顶层 `tmp/` 不存在**；同名文件已在 `delivery-keepalive/reports/`，属于 keepalive 文档修订复核 | 先改为 `reports/260820-review-keepalive-doc-fixes.md`；后续随同主题 reports 归 history | 是；这是纠错，不是从 `tmp/` 搬文件 |
| `260822-ghc-api-conformance-summary.md` | `ghe-device-flow/deferred.md:32`; `ghe-device-flow/spec.md:155` | 存在；GHC API conformance 汇总中的 D2，证明 `auth_base_url` 尚未进入用户控制的样例文档 | `ghe-device-flow/history/260822-ghc-api-conformance-summary.md` | 是；两处一起改 |
| `260822-pidfile-missing-forensics.md` | `graceful-shutdown/restart-handover/README.md:19,189` | 存在；pidfile 覆盖—删除事故的一手时间线与排除假设，结论自述“足以行动” | `graceful-shutdown/restart-handover/history/260822-pidfile-missing-forensics.md` | 是；两处一起改 |
| `260822-review-pidfile-port-scoping-opus.md` | `graceful-shutdown/restart-handover/README.md:190` | 存在；按端口隔离与 restart warning 实施的点时独立评审 | `graceful-shutdown/restart-handover/history/260822-review-pidfile-port-scoping-opus.md` | 是 |
| `260822-review-pidfile-port-scoping-gpt.md` | `graceful-shutdown/restart-handover/README.md:191` | 存在；同一实施的第二份点时独立评审 | `graceful-shutdown/restart-handover/history/260822-review-pidfile-port-scoping-gpt.md` | 是 |
| `260906-buffered-chat-local-tokenizer-analysis.md` | `token-counting/README.md:64` | 存在；settled 综合分析，给出 local estimate 与 upstream raw usage 的量级差，但明确不是 overflow 根因证明 | `token-counting/history/260906-buffered-chat-local-tokenizer-analysis.md` | 是 |
| `260906-buffered-chat-completions-transcript-evidence.md` | `token-counting/README.md:65` | 存在；transcript/request-log/rejected capture 点时取证，状态 `in-review`，有“强烈推断但非 cryptographic identity”边界 | `token-counting/history/260906-buffered-chat-completions-transcript-evidence.md` | 是；迁移时保留状态与 hash 边界 |
| `260906-buffered-chat-completions-transcript-evidence-erratum.md` | `token-counting/README.md:66` | 存在；纠正上一报告 ciphertext-only mutation 数字的勘误，必须与被纠正报告共址 | `token-counting/history/260906-buffered-chat-completions-transcript-evidence-erratum.md` | 是；与上一项原子迁移 |
| `260906-local-tokenizer-code-audit.md` | `token-counting/README.md:67` | 存在；production dataflow 只读审计，状态 `in-review`，README 用其概括 8 major/4 minor | `token-counting/history/260906-local-tokenizer-code-audit.md` | 是 |
| `260822-deferred-md-inventory.md` | `upstream/retry-and-continuation/deferred.md:11,21` | 存在；deferred 编号/引用面的全量点时清点，并保存一条撤回旧标题的教训 | `upstream/retry-and-continuation/history/260822-deferred-md-inventory.md` | 是；两处一起改 |
| `260822-review-session-closeout.md` | `upstream/retry-and-continuation/deferred.md:191` | 存在；异源收尾复核 N1，支撑 §20 的负样本/位置事实 | `upstream/retry-and-continuation/history/260822-review-session-closeout.md` | 是 |
| `260822-review-never-silent-failure-events.md` | `upstream/retry-and-continuation/deferred.md:224` | 存在；对上游失败事件改动的证伪式评审，支撑仍未处理的 10 个静默点 | `upstream/retry-and-continuation/history/260822-review-never-silent-failure-events.md` | 是 |
| `260822-h2-streamreset-cancel-diagnosis.md` | `upstream/retry-and-continuation/status.md:251` | 存在；Anthropic 上游腿 RST_STREAM(CANCEL) 的一次性诊断与方言判据 | `upstream/retry-and-continuation/history/260822-h2-streamreset-cancel-diagnosis.md` | 是 |
| `260821-plan-g1-upstream-error-events.md` | `upstream/retry-and-continuation/status.md:255` | 存在；G1 上游错误事件的边界/设计裁决记录，当前引用使用其 G4 核查 | `upstream/retry-and-continuation/history/260821-plan-g1-upstream-error-events.md` | 是 |

### 4.1 `tmp/` 命中但不属于“直接引用某一 tmp 文件”

- `auto-mode-classifier/spec.md:199` 只说明两份报告原先位于 `.dev/docs/tmp/`，且报告原件内部旧路径有意不改；它没有点名仍在顶层 `tmp/` 的文件，属于迁移沿革，不增加待搬项。
- `anthropic-responses-bridge/review-disposition-tool-whitelist.md:32` 泛指调查事实曾只在 `.dev/docs/tmp/`，但该文件本身是 review disposition，不是 current/living carrier，也未点名文件。
- `anthropic-responses-bridge/archive-260808/`、`service-cutover/archive-260808/`、`upstream/retry-and-continuation/archive-proxy-side-continuation/` 内还有若干 `tmp` links；它们是归档文档对当时路径的历史引用，按本任务判据不算 living 入站，不能拿来阻止 `tmp` 归口。若未来要求 archive 内链接也必须可点击，应另做“历史档案自包含化”，不要混入本轮 live dependency 清单。

## 5. 无入站引用的退役候选

在 88 份 current/living Markdown 的扫描面内，下列 8 个候选没有路径级入站引用：

1. `architecture-audit`
2. `copilot-token-identity`
3. `docs-tmp-migration`
4. `early-verification`
5. `lifecycle-reorg`
6. `pipeline-rewrite-parity`
7. `test-infrastructure`
8. `httpx2-migration`

限定：

- `httpx2-migration` 只能解释为“没有**保留主题 living Markdown** 入站”，不能解释为“全仓无入站”；已知 `pyproject.toml` 仍指向 `httpx2-migration/plan.md`。
- `architecture-audit` 与 `pipeline-rewrite-parity` 在保留主题的 `reports/` 中有历史命中，但报告内部引用不属于 live dependency。
- `copilot-token-identity` 的 current 文档命中均是 immutable Git archive ref 名，不能据此保留同名 docs topic。
- “无入站”只关闭本子话题的引用门槛；目录自身是否还含待裁决、未迁事项或应保留的历史证据，仍按 repository repair README 的其他门槛复核。

## 6. 推荐执行顺序

1. **先建目的地索引，不先删源。** 为 `anthropic-direct-request-shape`、`anthropic-responses-bridge`、`hosted-web-search`、`delivery-keepalive`、`dotdev-repository-repair`、`token-counting`、`graceful-shutdown/restart-handover`、`ghe-device-flow`、`client-leg-formats`、`upstream/retry-and-continuation` 建立或补齐 `history/README.md`，写明每份点时材料的来源、日期、适用边界与 current carrier。
2. **同一原件只保留一个 canonical destination。** `260822-round2-disposition.md` 同时被 request-shape 与 direct-passthrough 引用，但推荐只归 `anthropic-direct-request-shape/history/`；另一个 topic 跨主题链接。`260820-review-synthetic-start-fix.md` 三次引用也只迁一份。
3. **证据迁移与入站改链原子完成。** 逐项执行第 3、4 节；对 Markdown link 改 target，对 code span 路径改成可解析相对 link。不要移动报告后再等下一轮补链接。
4. **先纠正两个伪 `tmp` 位置。** `delivery-keepalive/spec.md:6` 的两份文件已经在 `delivery-keepalive/reports/`，直接纠正文案；不要尝试从 `tmp/` 找或复制不存在的源。
5. **清理不承重旧路径。** 处理第 3.1 节与 `history` 的 4 个 living 命中，使“无 current 依赖”不仅内容成立，路径扫描也能给出可解释结果。
6. **复扫 living 集，再复扫安全超集。** living 集应不再指向待删除候选或顶层 `tmp/` 文件；133 份安全超集的剩余命中应全部能解释为 archive/review disposition 的时点路径。任何新出现的 current consumer 都回填本地图后再退役。
7. **最后才跑目录删除门槛。** 本地图只处理入站与证据去向，不代替 `history/httpx2-migration` 的事项迁移、候选目录内容价值判断或删除授权。

## 7. 不确定项与实施注意

- **权威归属未被本地图升级。** `archived-2604-rewrite` 的旧 design docs 与若干实施/评审报告能证明“当时写了什么、测了什么”，但不自动证明“用户亲自裁决”。特别是 R-06、R-07：current 文档用了“既有裁决”字样，而本次读取到的旧目标首先是 agent-authored design snapshot；迁移时应保留 provenance，不能把它改写成一手用户裁决。若要继续写“用户裁决”，需另补可逐字回指的一手来源。
- **完整文件还是必要切片**：R-06～R-12 的旧 2604 文档很大且内部链接多。整份移动可保留上下文，但会带入更多旧相对链接；只摘切片更轻，但必须保留原文件名、原节、迁移日期和“不代表 current state”说明。推荐由目标 topic 的 `history/README.md` 记录取舍，不在本地图替执行者伪造新历史。
- **跨主题调查的归属**：`260827-deferred-survey.md` 覆盖 8 个台账，不天然只属于 `client-leg-formats`。当前 living 入站只有一处，故给出消费者归属；如果后续复扫发现第二个 current consumer，应改放 `dotdev-repository-repair/history/` 并由双方链接，而不是复制多个会漂移的副本。
- **行号会漂移**：本次扫描时 `.dev` 存在并行写入；`history` 迁移已在 inventory review 后发生。表中行号是本快照的执行锚，不是长期 ID，实际迁移时必须按文件名/target 再定位。
- **非 Markdown/全仓引用不在主扫描面**：源码注释、配置、`pyproject.toml`、Git commit message 与外部 worktree 未做全量入站扫描；已知 `httpx2-migration` 的 `pyproject.toml` 例外已显式列出。目录最终删除前仍应做一次仓库级 literal path scan。
- **本报告自身不是产品依赖。** 本文件为了执行迁移必然逐字列出所有退役路径与 `tmp` 目标；这些是 repair control-plane 清单，不能在复扫时反向计为“保留主题依赖退役目录”。迁移完成后应更新本表状态或随 repair topic 归档，而不是用本表的历史字符串阻止退役。

## 8. 完成判据

- 第 3 节 R-01～R-21 均有 canonical destination 或明确的“无需保留、改写叙述”处置，且每个引用方已改到最终位置。
- 第 4 节 18 个文件名中，16 份不再留在顶层 `tmp/`，2 份 keepalive 伪路径已指回现有 retained-topic 文件；21 个引用行全部复核。
- 88 份 current/living 文档对 16 个候选主题与顶层 `tmp/` 的路径扫描为零，或只剩本表已经明确判为“无 target 的历史叙述”且不会被 Markdown 解析为 link 的文字。
- `httpx2-migration` 的非 Markdown 指针和未闭合步骤另行关闭；不能拿本表的“living Markdown 无入站”跳过条件退役前置。
- 删除前的最后复扫排除 `dotdev-repository-repair/reports/`、本 `subtopics/` 清单和各 topic `history/` 的 provenance 后，不再出现未解释的 current consumer。
