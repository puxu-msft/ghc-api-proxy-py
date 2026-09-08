# 顶层 `tmp/` 最终逐份 disposition ledger

**评审范围**：以 2026-09-08 当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/` 的 `find .dev/docs/tmp -maxdepth 1 -type f` 结果为全集，共 77 份。本 ledger 逐份读取标题、状态、正文主旨与必要上下文，并对照 repository repair README、merged-state review、TUI disposition、retirement reference map、retained living 文档及当前源码；不修改、移动或删除任何 `tmp` 文件。

**总体 verdict**：**pass（仅指 77/77 份材料均已有可执行最终处置）**。其中 72 份已有 retained topic 下的 canonical history destination，4 份可删除，1 份必须先提炼成 retained topic 的 living contract，0 份需要用户裁决。这个 verdict 不是移动、删除、`git add`、commit 或 push 授权。

**blocker 数**：0。

## 判定口径

- `current consumer` 只计算 retained topic 的 current/living 文档；repair control-plane、`reports/`、`history/`、`archive-*`、顶层 `tmp/` 内互引及退役候选自身不算 current consumer。对后一类仍在「理由」中保留迁移约束。
- merged-state review 所述「retained living 文档不再直接指向顶层 `tmp/<file>`」仍成立；本轮另发现一个**按 basename 承重但写错目录**的 current consumer：`upstream/retry-and-continuation/deferred.md:157` 指向不存在的 `reports/260822-review-complete-fix-opus.md`，实际原件仍在顶层 `tmp/`。该项移动时必须同步改为 canonical history 路径。
- `可立即移动=是` 表示 owner、目标和边界已经确定，不需要用户裁决；若行内注明「原子迁移」，则同组文件、引用改写或 `history/` 建目录必须在同一变更完成，不能只搬源文件。
- `point-in-time` 材料进入 `history/` 后仍只是时点证据，不升级为 current authority；living 行为继续由对应 retained topic 的 Spec/status/deferred 承载。

## 逐份 ledger

| 文件 | 性质 / 证据等级 | current consumer | 最终 disposition | 目标路径 | 理由 | 可立即移动 |
|---|---|---|---|---|---|---|
| `260807-final-review-current-main.md` | merged-state 独立评审；point-in-time，强但受固定 SHA/范围限制 | 无；仅 bridge archive 与已退役迁移账本提名 | canonical history | `anthropic-responses-bridge/history/260807-final-review-current-main.md` | 主轴是 Responses bridge capability、History 与 stream 接缝；S3/S4 只是同一合并态的旁轴，不能把报告留作 living 状态。 | 是 |
| `260807-resume-audit-systemd-bridge-overlap.md` | 跨切片只读预检；point-in-time，路径/hunk 证据强 | 无 | canonical history | `anthropic-responses-bridge/history/260807-resume-audit-systemd-bridge-overlap.md` | 正文以 bridge 三片的重建顺序为主，systemd 是随后集成顺序；适合作为 bridge 合并史而非独立 living plan。 | 是 |
| `260807-review-backup-r3-living-checkpoint.md` | living checkpoint 独立复评；point-in-time，强 | 无 | canonical history | `anthropic-responses-bridge/history/260807-review-backup-r3-living-checkpoint.md` | 核心是 backup R3 canary 与 bridge History facts 的阶段门，当前状态已由 bridge/service-cutover living 文档取代。 | 是 |
| `260807-review-deployment-docs-r3.md` | 三份部署 living 文档联合复评；point-in-time，强 | 无 | canonical history | `service-cutover/history/260807-review-deployment-docs-r3.md` | 主要裁定 deployment/systemd/service-cutover 的 checkpoint 与 `NO_CUTOVER` 边界；由仍保留的 service-cutover 主题归档最完整。 | 是；先建 topic-local `history/` |
| `260807-review-deployment-plans-r2.md` | 部署计划联合复评；point-in-time，强 | 无 | canonical history | `service-cutover/history/260807-review-deployment-plans-r2.md` | 7 个 major 与进入下一实施门的条件属于 service cutover 计划沿革，不是当前计划。 | 是；与同主题 checkpoint 报告同批 |
| `260807-review-identity-living-checkpoint.md` | bridge identity checkpoint 复评；point-in-time，强 | 无；仅退役候选 `docs-tmp-migration/README.md` 提名 | canonical history | `anthropic-responses-bridge/history/260807-review-identity-living-checkpoint.md` | 正文主轴是 response identity candidate、bridge canary 与下一 checkpoint；服务切换只是授权边界。 | 是 |
| `260807-review-living-after-main-replay-r2.md` | main replay 后 living 状态复评；point-in-time，强 | 无；bridge 的历史 report 提名 | canonical history | `anthropic-responses-bridge/history/260807-review-living-after-main-replay-r2.md` | 直接复核 bridge implementation、systemd plan 与 readiness 的同一 checkpoint，bridge 是承重 owner。 | 是 |
| `260807-review-main-foundations-systemd.md` | foundations+systemd merged-state 评审；point-in-time，强 | 无；仅 bridge archive/退役材料提名 | canonical history | `anthropic-responses-bridge/history/260807-review-main-foundations-systemd.md` | 代码结论是 bridge foundations 已进 main，major 是 living 状态链滞后；归入 bridge 合并历史。 | 是 |
| `260807-review-reservation-wiring-living.md` | resident quota/wiring living 复评；point-in-time，强 | 无；bridge 历史 report 提名 | canonical history | `anthropic-responses-bridge/history/260807-review-reservation-wiring-living.md` | 评审对象和后续动作均围绕 bridge resident-byte 与 production wiring。 | 是 |
| `260807-review-resident-living-checkpoint.md` | resident primitive checkpoint 复评；point-in-time，强 | 无；bridge 历史 report 提名 | canonical history | `anthropic-responses-bridge/history/260807-review-resident-living-checkpoint.md` | 阶段结论已由 bridge implementation/readiness 吸收，原件保留为阶段证据。 | 是 |
| `260807-verify-main-foundations-systemd.md` | 独立验收；scoped PASS，强且边界明确 | 无 | canonical history | `anthropic-responses-bridge/history/260807-verify-main-foundations-systemd.md` | PASS 同时覆盖 bridge foundations 与 systemd，但冻结 oracle 和大多数矩阵来自 bridge；不能把 scoped PASS 当当前整体验收。 | 是 |
| `260820-review-session-closeout.md` | 会话 closeout/证据载体独立复核；point-in-time，过程证据中强 | 无；仅退役候选迁移账本提名 | canonical history | `dotdev-repository-repair/history/260820-review-session-closeout.md` | 不是 TUI 证据；原建议 `documentation-restructure/history/` 的 owner 将退役，repository repair 是文档归口与过程记录的 retained successor。 | 是 |
| `260820-system-reminder-wire-shapes.md` | 真实上行 body 普查；直接数据取证，强且版本/样本受限 | 无；仅退役迁移账本提名 | canonical history | `anthropic-direct-request-shape/history/260820-system-reminder-wire-shapes.md` | 正文回答 `<system-reminder>` 在请求 body 中的结构、剥除影响与混淆源，属于 Anthropic 请求形状历史证据。 | 是 |
| `260821-probe-history-error-frames.md` | 只读 history 数据库探针；直接观测，强但为时点样本 | 无 retained consumer；退役候选 `sync-refs` 仍以旧 tmp 路径引用 | canonical history | `upstream/retry-and-continuation/history/260821-probe-history-error-frames.md` | 主问题是上游 SSE `error`/incomplete 终局与历史记录语义；迁移后退役 `sync-refs` 无需继续承担证据 owner。 | 是 |
| `260821-review-g1-candidate.md` | G1 上游失败事件实现评审；point-in-time，强 | 无 | canonical history | `upstream/retry-and-continuation/history/260821-review-g1-candidate.md` | 评的是明确失败不得伪装成功、错误事件与完成结果，TUI/request log 仅为观察面；复核此前 TUI 建议后维持 upstream owner。 | 是 |
| `260821-shared-index-left-reverting-head.md` | shared-index 事故与修复记录；直接 Git 证据，强 | 无；upstream history 仅作过程引用 | canonical history | `dotdev-repository-repair/history/260821-shared-index-left-reverting-head.md` | 承重结论是共享索引/CAS 的仓库操作风险，不是 upstream 产品行为；由 repository repair 保存。 | 是 |
| `260821-truncated-anthropic-stream-diagnosis.md` | 单次生产事件诊断；直接观测，强但只覆盖一个请求 | 无 current path consumer；upstream reports/history 多处历史提名 | canonical history | `upstream/retry-and-continuation/history/260821-truncated-anthropic-stream-diagnosis.md` | 正文明确挂接 upstream stream termination 欠账，并区分 GOAWAY；应与后续 G1/stream reset 证据链共址。 | 是 |
| `260822-audit-other-stale-blobs-committed.md` | stale-index 提交态独立核查；Git 取证强 | 无 | canonical history | `dotdev-repository-repair/history/260822-audit-other-stale-blobs-committed.md` | 是共享索引事故的全仓复扫与判据分辨力记录，属于仓库修复史。 | 是 |
| `260822-candidate-docs-refresh-log.md` | human-controlled candidates 刷新日志；实施自述+逐项证据，中强 | 无 | canonical history | `dotdev-repository-repair/history/260822-candidate-docs-refresh-log.md` | 不是 TUI；原建议 `documentation-restructure/history/` 将失去 owner，最终归 repository repair 的文档治理沿革。 | 是 |
| `260822-candidates-vs-user-updates-reconciliation.md` | 候选稿与人写文档对账；point-in-time 调查，强 | 无；仅 upstream 历史 report 引用 | canonical history | `dotdev-repository-repair/history/260822-candidates-vs-user-updates-reconciliation.md` | 跨多个主题判定候选是否仍需采纳，属于文档治理/迁移证据而非任一产品 Spec。 | 是 |
| `260822-cli-and-module-move-closeout.md` | CLI/module move 会话 closeout；point-in-time，过程证据强 | 无 | canonical history | `server-layout/history/260822-cli-and-module-move-closeout.md` | 主体是 CLI 切分、模块迁移、import/索引教训；server-layout 是保留的结构 owner，过程教训与事实复核应同址。 | 是；先建 topic-local `history/` |
| `260822-doc-citations-review-disposition.md` | 代码文档引用审计处置；point-in-time，强 | 无；server-layout 历史 report 提名 | canonical history | `dotdev-repository-repair/history/260822-doc-citations-review-disposition.md` | 不是 TUI；两份引用评审的处置属于文档仓库治理，原 `documentation-restructure` 建议改到 retained successor。 | 是；与两份 citation review 原子迁移 |
| `260822-ghc-api-conformance-auth.md` | GHC auth 调用链核实；只读源码证据，强且时点化 | 无；canonical conformance summary 在 `ghe-device-flow/history/` 提名 | canonical history | `ghe-device-flow/history/260822-ghc-api-conformance-auth.md` | 是已迁 conformance summary 的组成证据，且 auth/device flow 正由 retained `ghe-device-flow` 管理。 | 是；与整套 conformance 原件原子迁移 |
| `260822-ghc-api-conformance-baseurl.md` | GHC base URL 需求对照；源码+探针，强 | 无；canonical conformance summary 提名 | canonical history | `ghe-device-flow/history/260822-ghc-api-conformance-baseurl.md` | 与 auth、account type 和 device flow 同属 canonical conformance evidence set。 | 是；同组 |
| `260822-ghc-api-conformance-crosscheck.md` | 四份 conformance 报告独立交叉复核；强 | 无；canonical conformance summary 提名 | canonical history | `ghe-device-flow/history/260822-ghc-api-conformance-crosscheck.md` | 推翻原报告三条主张，是 summary 修订不可丢的异源证据；必须与被复核原件共址。 | 是；同组 |
| `260822-ghc-api-conformance-direct-paths.md` | GHC direct driver 端点核查；源码证据强、运行时部分未验证 | 无；canonical conformance summary 与历史 probe 提名 | canonical history | `ghe-device-flow/history/260822-ghc-api-conformance-direct-paths.md` | 虽跨 direct formats，正文是 `ghc-api.md` 全套 conformance 的一部分；已迁 summary 是唯一索引，故不另拆副本。 | 是；同组 |
| `260822-ghc-api-conformance-responses-ws.md` | Responses WebSocket 现状核查；源码/路由证据强 | 无；canonical conformance summary 提名 | canonical history | `ghe-device-flow/history/260822-ghc-api-conformance-responses-ws.md` | 不是 TUI；它回答 `ghc-api.md` 的 WS conformance，已迁 summary 正逐名索引此原件。 | 是；同组 |
| `260822-ghc-api-conformance-summary-review.md` | canonical conformance summary 独立评审；point-in-time，强 | 无；canonical summary 提名且记录已采纳修订 | canonical history | `ghe-device-flow/history/260822-ghc-api-conformance-summary-review.md` | 8 个 major 是 summary 当前文字的修订来源；与 summary 及五份底稿共址后 basename 引用可解析。 | 是；同组 |
| `260822-header-forwarding-surface.md` | 客户端 header 转发面调查；源码+参考实现测量，强但时点化 | 无；request-shape canonical history 与退役报告提名 | canonical history | `anthropic-direct-request-shape/history/260822-header-forwarding-surface.md` | 直接测量 owned headers、大小写重复和 header policy 未接线，是 beta strip/request-shape 证据链的一部分。 | 是；与 beta-strip 评审链原子迁移 |
| `260822-p2-complete-fix-handover.md` | `StreamEnding.COMPLETE` 修复交接；实施自述+变异，中强 | 无；upstream history 多处提名 | canonical history | `upstream/retry-and-continuation/history/260822-p2-complete-fix-handover.md` | 修复 torn stream 在已见 terminal 后被丢弃的问题，属于 retry/continuation 决策与实施沿革。 | 是 |
| `260822-pyright-errors-in-stream-cap-slice.md` | current-main pyright 缺陷条；直接工具输出，强但已时点化 | 无 | canonical history | `upstream/retry-and-continuation/history/260822-pyright-errors-in-stream-cap-slice.md` | 21 个 error 全在 httpcore2 stream-cap 切片，最接近 retained upstream/connection owner；不能作为当前 pyright 状态。 | 是 |
| `260822-review-closeout-claims.md` | beta-strip closeout claim 独立核查；强 | 无；retired hooks report 与 request-shape history 提名 | canonical history | `anthropic-direct-request-shape/history/260822-review-closeout-claims.md` | 评的是 beta strip 实施报告与 header 测试归因，当前 owner 已从 hooks migration 转到 request-shape。 | 是；与 beta-strip 评审链同组 |
| `260822-review-closeout-facts.md` | CLI/module move 两份 closeout 的事实核查；强 | 无 | canonical history | `server-layout/history/260822-review-closeout-facts.md` | 与 `260822-cli-and-module-move-closeout.md` 是原件—评审关系，放同一 server-layout history 可保住相对引用。 | 是；与 closeout/omissions 原子迁移 |
| `260822-review-closeout-omissions.md` | 同一会话遗漏评审；transcript 双向对账，强但过程性 | 无 | canonical history | `server-layout/history/260822-review-closeout-omissions.md` | 主体是 module move 会话未沉淀的范围/import/索引知识；与 closeout 和 facts 共址，不另复制到 skill topic。 | 是；同组 |
| `260822-review-complete-fix-gpt.md` | `COMPLETE` 修复独立评审；强 | 无；upstream history 提名 | canonical history | `upstream/retry-and-continuation/history/260822-review-complete-fix-gpt.md` | 针对 terminal-seen、deadline 次序与测试分辨力，是 retry/continuation 的历史 review。 | 是；与 Opus 复评及 handover 同组 |
| `260822-review-complete-fix-opus.md` | 同一修复异源证伪评审；强 | **有**：`upstream/retry-and-continuation/deferred.md:157` 按 basename 承重，但误写为不存在的 `reports/...` | canonical history | `upstream/retry-and-continuation/history/260822-review-complete-fix-opus.md` | 当前 deferred 用其证明 deadline/terminal 次序；不得删除，移动时必须把 code-span target 从 `reports/` 改为 `history/`。 | 是；必须与 `deferred.md` 改链原子完成 |
| `260822-review-disposition-manifest.md` | beta-strip job 临时清单独立评审；过程证据中强 | 无；retired hooks closeout report 提名 | canonical history | `anthropic-direct-request-shape/history/260822-review-disposition-manifest.md` | 虽评的是 job manifest，但其发现用于 beta-strip closeout 的证据闭合；request-shape 是最终 retained owner。 | 是；与 beta-strip 评审链同组 |
| `260822-review-doc-citations-coverage.md` | 文档引用修复覆盖面评审；强 | 无；server-layout 历史 report 提名 | canonical history | `dotdev-repository-repair/history/260822-review-doc-citations-coverage.md` | 不是 TUI；主旨是仓库级引用扫描的盲区与过改，归 repository repair successor。 | 是；与 disposition/mapping 原子迁移 |
| `260822-review-doc-citations-mapping.md` | 21 条引用映射逐项评审；强 | 无 | canonical history | `dotdev-repository-repair/history/260822-review-doc-citations-mapping.md` | 与 coverage 是互补评审，且 disposition 逐名链接二者；三件必须共址。 | 是；同组 |
| `260822-review-gate2-ownership.md` | project-review-principles gate/归属评审；强 | 无 | canonical history | `project-review-principles-skill/history/260822-review-gate2-ownership.md` | 直接评 retained skill 的 ownership 判据、用户归属和门槛 2；作为 skill 演化证据保留，不当 living rule。 | 是；先建 topic-local `history/` |
| `260822-review-pidfile-dir-refusal-gpt.md` | pidfile_dir/拒绝覆盖/`--fd` 独立评审；强 | 无 | canonical history | `graceful-shutdown/restart-handover/history/260822-review-pidfile-dir-refusal-gpt.md` | 正文处理 pidfile 生存记录与 restart 行为，owner 明确为 graceful-shutdown/restart-handover。 | 是；与 Opus 评审原子迁移 |
| `260822-review-pidfile-dir-refusal-opus.md` | 同一切片异源评审；强 | 无 | canonical history | `graceful-shutdown/restart-handover/history/260822-review-pidfile-dir-refusal-opus.md` | 与 GPT 报告给出互补 findings，属于同一 pidfile evidence family。 | 是；同组 |
| `260822-review-skill-carrier-tradeoff.md` | shared-worktree skill carrier 独立评审；fixture 实测，强 | 无 | canonical history | `project-review-principles-skill/history/260822-review-skill-carrier-tradeoff.md` | 评的是 skill 召回面、CAS/index realign 与 carrier 可执行性，属于 retained skill 的演化证据。 | 是 |
| `260822-review-split-2afa0c4.md` | 主仓历史拆分独立评审；Git/tree 证据强 | 无 | canonical history | `dotdev-repository-repair/history/260822-review-split-2afa0c4.md` | 核查文档与 refactor 拆分、hash 重写和引用处置，属于仓库历史修复而非产品主题。 | 是；与 hash-map/disposition 原子迁移 |
| `260822-review-streamreset-diagnosis-gpt.md` | H2 `StreamReset(CANCEL)` 诊断独立评审；强 | 无；canonical upstream diagnosis/history 提名 | canonical history | `upstream/retry-and-continuation/history/260822-review-streamreset-diagnosis-gpt.md` | 不是 TUI；它复核 upstream RST_STREAM、replay 和 terminal policy，必须与已迁诊断原件共址。 | 是；与 Opus 评审同组 |
| `260822-review-streamreset-diagnosis-opus.md` | 同一诊断端到端证伪评审；强 | 无；canonical upstream diagnosis/history 提名 | canonical history | `upstream/retry-and-continuation/history/260822-review-streamreset-diagnosis-opus.md` | 逐条重跑并收窄证据链，是 upstream diagnosis 的异源配套原件。 | 是；同组 |
| `260822-split-2afa0c4-hash-map.md` | 历史重写新旧 SHA 映射；Git 事实强 | 无 | canonical history | `dotdev-repository-repair/history/260822-split-2afa0c4-hash-map.md` | 拆分后的旧报告只能靠该映射解析；必须与拆分评审/处置共址，不可删除。 | 是；同组 |
| `260822-split-2afa0c4-review-disposition.md` | 拆分评审处置；point-in-time，强 | 无 | canonical history | `dotdev-repository-repair/history/260822-split-2afa0c4-review-disposition.md` | 记录评审 findings 的采纳与重新改写，完成同一 Git history evidence set。 | 是；同组 |
| `260822-verify-beta-flag-strip-docs.md` | beta strip 文档事实核查；强 | 无；request-shape history 多处提名 | canonical history | `anthropic-direct-request-shape/history/260822-verify-beta-flag-strip-docs.md` | 核实字段改名、header policy 与历史状态，是已迁 beta-strip implementation/review 的配套证据。 | 是；与 beta-strip 评审链同组 |
| `260823-nonfile-candidates-review-A.md` | 非文件知识候选独立枚举/对账；transcript 证据强 | 无 | canonical history | `project-review-principles-skill/history/260823-nonfile-candidates-review-A.md` | 不是 TUI；内容直接服务评审方法、范围判据与记忆 carrier，复核此前建议后维持 retained skill owner。 | 是；与 B/C/final closeout 原子迁移 |
| `260823-nonfile-candidates-review-B.md` | 第二轮非文件候选对账；强但有已声明日志盲区 | 无 | canonical history | `project-review-principles-skill/history/260823-nonfile-candidates-review-B.md` | 与 A 互补并明确其覆盖缺口，不能拆散或把结论升级为 current rule。 | 是；同组 |
| `260823-nonfile-candidates-review-C-subagents.md` | 第三轮只查 subagent logs；强 | 无 | canonical history | `project-review-principles-skill/history/260823-nonfile-candidates-review-C-subagents.md` | 补足 A/B 最大盲区，形成完整的 skill-evidence chain。 | 是；同组 |
| `260823-review-temp-manifest.md` | job 临时状态 manifest 评审；过程性、只对已过期 job root 有效 | 无 | 可删除 | — | 被评对象是 `/home/xp/.claude/jobs/be410f2e/tmp` 的瞬时清单，产品/文档结论由 nonfile final closeout 与 A/B/C 评审承接；保留此稿只会延寿不可复现的临时状态。 | 不适用；可立即删除 |
| `260823-session-closeout-nonfile-candidates.md` | 非文件知识最终 closeout；三轮评审后的综合载体，中强 | 无 | canonical history | `project-review-principles-skill/history/260823-session-closeout-nonfile-candidates.md` | 是 A/B/C 评审后的耐久综合载体，记录哪些教训已落到 skill/文档、哪些未闭合；应与三份原评审共址。 | 是；与 A/B/C 原子迁移 |
| `260823-session-closeout-temp-manifest.md` | job tmp 文件处置清单；瞬时过程记录、低长期证据价值 | 无 | 可删除 | — | 清单明示处置已关闭、文件留给 harness 过期；其中耐久教训已进入 nonfile closeout/A/B/C，剩余是已消失 job root 的逐文件状态。 | 不适用；可立即删除 |
| `260824-acceptance-cut-and-new-skill-review.md` | service acceptance 与新 skill 联合评审；强 | 无 | canonical history | `service-cutover/history/260824-acceptance-cut-and-new-skill-review.md` | 承重 findings 位于 service-cutover acceptance 的 current authority、gate 映射和状态词；skill 只是同一改动的另一轴，最终由 service-cutover 留史。 | 是；先建 topic-local `history/` |
| `260824-autocompact-window-is-one-million.md` | Claude Code context-window/auto-compact 实测定案；直接观测强、版本限定 | 无 | canonical history | `token-counting/history/260824-autocompact-window-is-one-million.md` | 核心是 1M context window、967k 阈值与 token 判定，不是 request header/body 形状；应与完整 autocompact 证据链归 token-counting。 | 是；与另外三份 autocompact 报告原子迁移 |
| `260824-cc-autocompact-same-version-divergence.md` | 同版本 auto-compact 分歧深度取证；代码+环境对照强、版本限定 | 无 | canonical history | `token-counting/history/260824-cc-autocompact-same-version-divergence.md` | **修正此前 TUI 建议**：正文没有 `cache_control`/request-shape 结论，主轴是 context window、环境变量与 token threshold，因此 final owner 是 token-counting。 | 是；同组 |
| `260824-cc-autocompact-trigger-forensics.md` | Claude Code auto-compact 判定路径取证；静态证据强、版本限定 | 无 | canonical history | `token-counting/history/260824-cc-autocompact-trigger-forensics.md` | 与窗口定案、同版本分歧和更正稿构成同一 token/context-window evidence family。 | 是；同组 |
| `260824-cc-stop-reason-incomplete.md` | Claude Code 对 `stop_reason=incomplete` 的静态+动态兼容性取证；强、版本限定 | 无 current consumer；upstream reports 历史提名 | canonical history | `upstream/retry-and-continuation/history/260824-cc-stop-reason-incomplete.md` | 直接支撑 silent EOF/unterminated stream 的客户端交付语义，属于 upstream termination history。 | 是 |
| `260824-count-tokens-heterogeneous-review-gpt.md` | heterogeneous `count_tokens` 独立评审；强 | 无 current consumer；退役 `count-tokens` report 提名 | canonical history | `token-counting/history/260824-count-tokens-heterogeneous-review-gpt.md` | 评审路由、校准、合法性差异与客户端响应形状；复核此前建议后维持 successor `token-counting`。 | 是 |
| `260824-count-tokens-prior-art-survey.md` | count_tokens 裁决/spec/report/test 全量清点；强 | 无 current consumer；退役 `count-tokens` report 提名 | canonical history | `token-counting/history/260824-count-tokens-prior-art-survey.md` | 跨旧 `count-tokens` 材料建立权威边界，是 retained token-counting 的历史 prior art。 | 是 |
| `260824-defer-loading-responses-leg-investigation.md` | `defer_loading` 翻译腿 400 调查；源码+探针，强，状态为调查稿 | 无；bridge tool-whitelist 历史 report 提名 | canonical history | `anthropic-responses-bridge/history/260824-defer-loading-responses-leg-investigation.md` | 主轴是 Anthropic Messages→OpenAI Responses 工具形状泄漏与第二道过滤，属于 responses bridge 历史。 | 是；与 tool-search 调查同组 |
| `260824-spec-freeze-encoding-inventory.md` | 全仓 Spec freeze 编码点考古；point-in-time 全量扫描，强 | 无 | canonical history | `dotdev-repository-repair/history/260824-spec-freeze-encoding-inventory.md` | 不是 TUI；原 `documentation-restructure/history/` owner 将退役，全文是跨主题文档治理/authority 迁移证据，由 repository repair 承接。 | 是 |
| `260824-tool-search-beta-400-investigation.md` | tool-search beta 400 调查；源码/参考客户端证据强，`in-review` | 无；bridge tool-whitelist 历史 report 提名 | canonical history | `anthropic-responses-bridge/history/260824-tool-search-beta-400-investigation.md` | 回答 Responses 翻译腿的 tool beta/body vocabulary 与 400，和 `defer_loading` 是同一 tool-whitelist 事实链。 | 是；同组 |
| `260824-why-autocompact-did-not-fire.md` | auto-compact 初始诊断及同日更正；原主线部分被推翻，保真价值中等 | 无 | canonical history | `token-counting/history/260824-why-autocompact-did-not-fire.md` | 不能单独作为结论，但它明确记录被后续报告推翻的版本/环境假设；与后三份共址才能防止旧主线被误用。 | 是；同组 |
| `260827-fix-inference-accounting.md` | inference/stream 记账修复报告；实施自述+变异，中强 | 无 | canonical history | `error-envelope/history/260827-fix-inference-accounting.md` | 四项中三项直接关闭 error-envelope 的 fail/detail/deadline 事实，retry §9 是交叉项；最终 owner 取 error-envelope。 | 是；先建 topic-local `history/` |
| `260827-fix-responses-stop-reason.md` | Anthropic→Responses stop_reason 修复报告；实施自述+边界清单，中强 | 无 | canonical history | `client-leg-formats/history/260827-fix-responses-stop-reason.md` | 核心是客户端腿终态格式映射表、`status` 与 `incomplete_details` 合法形状，由 retained client-leg-formats 留史。 | 是 |
| `260827-fix-silent-drop.md` | Responses assembler silent-drop 修复报告；实施自述+变异，中强 | 无 | canonical history | `upstream/retry-and-continuation/history/260827-fix-silent-drop.md` | 修复上游 item close 无 draft 时无声丢弃，直接对应 retry/continuation 的失败可见性欠账。 | 是 |
| `260827-ledger-cleanup.md` | 八份 deferred 台账整理/迁出报告；源码复核+实施账，中强 | 无 | canonical history | `dotdev-repository-repair/history/260827-ledger-cleanup.md` | 不是 TUI；原 `documentation-restructure/history/` owner 将退役，跨主题 ledger 治理由 repository repair successor 承接。 | 是 |
| `260906-buffered-chat-local-tokenizer-analysis-review-r2.md` | local-tokenizer 分析限定复评 R2；强，`in-review` 元数据未刷新 | 无 | canonical history | `token-counting/history/260906-buffered-chat-local-tokenizer-analysis-review-r2.md` | 复核分析稿 F1/F2 与 LT-09 残余，必须与分析、R1、R3 同址；状态字段保留为时点元数据。 | 是；与 tokenizer 分析全链原子迁移 |
| `260906-buffered-chat-local-tokenizer-analysis-review-r3.md` | 限定复评 R3；强但只覆盖 LT-09 closure | 无 | canonical history | `token-counting/history/260906-buffered-chat-local-tokenizer-analysis-review-r3.md` | 是 R2 残余 finding 的 closure 证据，单独删除会断评审链。 | 是；同组 |
| `260906-buffered-chat-local-tokenizer-analysis-review.md` | local-tokenizer 独立评审 R1；强 | 无 | canonical history | `token-counting/history/260906-buffered-chat-local-tokenizer-analysis-review.md` | C1–C10 核验与后续两轮构成 token-counting evidence chain；复核此前 TUI 建议后维持该 owner。 | 是；同组 |
| `260906-session-report.html` | 自动生成的 Claude usage dashboard；派生统计并内嵌 session-derived JSON，非产品证据 | 无 | 可删除 | — | 约 494 KB 的单机使用量快照，无 retained topic consumer、无规范/诊断结论，且原始聚合数据不应靠顶层 tmp 长期保存。 | 不适用；可立即删除 |
| `260907-interaction-context-design.md` | 跨 inbound/context/provider/GHC/retry 的长期设计；当前源码已实现主干，设计证据强 | 无现成 living owner | **需新建 living topic**；先提炼 current contract，再归档原稿 | living：`interaction-context/spec.md`；原稿：`interaction-context/history/260907-interaction-context-design.md` | 不能删除：正文有候选优先级、类型/API、匿名 fallback、retry 稳定性、negative space 与测试矩阵；同时 §0/§10 是 2026-09-07 dirty-WIP 快照，不能原样冒充 living。其射程跨 Anthropic/Responses 与所有 provider，硬塞进 `anthropic-direct-request-shape` 会越过该 Spec 的 Anthropic-only 范围，故需独立 retained owner。 | 否；须先提炼 living contract 并核对 current source，再归档原稿 |
| `260908-review-upstream-failure-backoff.md` | consecutive-failure backoff 独立评审+实现方逐项处置；强 | living owner 为 `upstream/retry-and-continuation/status.md`，但未按文件名链接 | canonical history | `upstream/retry-and-continuation/history/260908-review-upstream-failure-backoff.md` | 不能删除：保留 overflow blocker、并发 `_next_allowed` major、replay 固定 base 边界、修复/测试处置及人控候选待追认 provenance；current 行为继续由 status 与候选稿承载。 | 是 |
| `refs-go-bridges.md~` | 编辑器备份/带终端控制序列的原始 shell line evidence；低、未成文 | 无；退役迁移账本只说明其存在 | 可删除 | — | 正式蒸馏稿已存在于 `anthropic-responses-bridge/reports/refs-go-bridges.md`，含 HEAD、接线、状态机、测试与边界；备份是 382 行原始命令输出，既不等字节也不提供独立规范结论。 | 不适用；可立即删除 |

## 结算

| 最终类别 | 数量 | 执行动作 |
|---|---:|---|
| 可立即迁移到 canonical history | 72 | 按表中 owner 移动；标为「同组/原子迁移」的同批处理，并同步唯一的 living 改链 `upstream/retry-and-continuation/deferred.md:157`。 |
| 可删除 | 4 | `260823-review-temp-manifest.md`、`260823-session-closeout-temp-manifest.md`、`260906-session-report.html`、`refs-go-bridges.md~`。 |
| 需活主题 | 1 | `260907-interaction-context-design.md`：新建 retained `interaction-context/`，先提炼 living Spec，再把原稿放入 topic-local history。 |
| 需用户裁决 | 0 | 本轮未遇到无法从正文主题、现有 retained owner、current source 或 canonical evidence chain 判定的归属。 |
| **总计** | **77** | 与当前 `find .dev/docs/tmp -maxdepth 1 -type f` 一一对应。 |

## TUI 既有 17 项建议的最终复核

原 26 个关键词候选中 9 份已在本轮之前迁走；当前仍存的 17 份均已在上表闭合。最终复核结果：

- **维持 upstream owner（3）**：`260821-review-g1-candidate.md`、`260822-review-streamreset-diagnosis-gpt.md`、`260822-review-streamreset-diagnosis-opus.md`；均不是 TUI 主题。
- **维持 token-counting owner（4）**：`260824-count-tokens-heterogeneous-review-gpt.md`、`260824-count-tokens-prior-art-survey.md`、`260906-buffered-chat-local-tokenizer-analysis-review.md`、`260906-buffered-chat-local-tokenizer-analysis-review-r2.md`。
- **维持 project-review-principles owner（1）**：`260823-nonfile-candidates-review-A.md`。
- **原建议 `documentation-restructure/history/` 改为 retained successor `dotdev-repository-repair/history/`（7）**：`260820-review-session-closeout.md`、`260822-candidate-docs-refresh-log.md`、`260822-doc-citations-review-disposition.md`、`260822-review-doc-citations-coverage.md`、`260822-review-doc-citations-mapping.md`、`260824-spec-freeze-encoding-inventory.md`、`260827-ledger-cleanup.md`。理由不是内容归属改变，而是旧 owner 已是退役候选，不能在最终处置中继续向它新增历史。
- **原 request-shape 建议修正为 token-counting（1）**：`260824-cc-autocompact-same-version-divergence.md`。全文主轴是 Claude Code 的 context window、token threshold、环境变量和 auto-compact gate，未承载 `cache_control` 或出站 request-shape 结论。
- **维持 GHC conformance evidence set（1）**：`260822-ghc-api-conformance-responses-ws.md` 最终进入 `ghe-device-flow/history/`，与已迁 summary 及其逐名索引共址。

上述分组有交叉口径时以上表 17 个具体文件行为准；其共同结论仍是 **TUI 自身接收 0 份**，不得重建 `tui/reports/`。

## 两份重点材料

### `260907-interaction-context-design.md`

该稿不是可直接删除的点时报告，也不能原样升级成 living authority。正文的长期承重内容包括：

- 客户端逻辑会话、代理 request id、GHC provider-instance fallback 三种 identity 的生命周期分离；
- 六个候选 header 的有序、大小写不敏感、空白跳过规则；
- `RequestContext`、`ModelProvider.send`、driver、GHC client 的显式 API seam；
- 直连/翻译/retry/count_tokens/匿名请求的行为边界；
- negative space 与分层测试矩阵。

当前源码已经存在 `session_identity.py`、`RequestContext.interaction_id`/`provider_interaction_id`、provider 协议参数和 GHC 显式 binding，说明它不是纯设想；但原稿 §0/§10 固定的是 2026-09-07 HEAD/dirty WIP，且当前实现已出现 `interaction_id_for_provider()` 等后续形状。最终动作必须是：以 current source 重新核对后，将稳定合同提炼到 `interaction-context/spec.md`，把点时 WIP/设计比较保真归入 `interaction-context/history/260907-interaction-context-design.md`。

### `260908-review-upstream-failure-backoff.md`

该稿也不能删除。它同时承载：

- `_failures` 指数溢出的 blocker 与修复；
- sleeping `acquire` 覆盖并发 `note_failure` 的 major 与修复；
- delivery replay 每次 response-header success 清 streak、因此恒定 base 而非 widening 的边界；
- 104 项目标测试、ruff、pyright 与全量回归 1 个 pre-existing failure 的处置记录；
- `.dev/human-controlled-docs-candidates/260908-upstream-retry-backoff.md` 待用户追认的 provenance。

current 行为已由 `upstream/retry-and-continuation/status.md` 承接，故最终位置是该主题 history，而不是新 living Spec；原报告的 blocker/major 与处置链使其具有长期审计价值，不能因 current direct link 为零而删除。

## 搜索面与执行门槛

- 已逐份读取 77 个顶层 regular files 的标题、状态/判定、正文开头、章节地图与必要结论；对两份重点材料阅读全文，对跨主题或可能删除项补读相关正文/canonical carrier。
- 已扫描 retained current/living Markdown 对 77 个 basename 的引用；唯一承重 basename consumer 是 `upstream/retry-and-continuation/deferred.md:157` 的错误 `reports/` 位置。退役候选、reports/history/archive 的历史提名不提升为 current consumer，但在表中用于决定原子迁移组。
- 已核对现有 topic 与 `history/` 目录；需新建的仅是表中明确写出的 topic-local `history/`，以及唯一的新 retained topic `interaction-context/`。
- 已核对 `refs-go-bridges.md~` 与正式蒸馏稿：两者不同字节，前者是 raw terminal evidence，后者已经保留其可行动结论；这支持删除备份而不是误判为重复副本。
- 实际执行迁移后必须复跑：顶层 inventory 计数、retained living path/basename scan、同 basename 唯一性、所有新增/改写 Markdown links 解析，以及每个 moved original 的 source absent/destination present/hash unchanged。删除 4 份材料前仍应把本 ledger 作为逐项授权清单核对一次；本报告本身不执行删除。
