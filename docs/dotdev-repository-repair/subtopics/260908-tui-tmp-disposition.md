# TUI 关键词 tmp 候选的逐份归属处置

**处置范围**：仅审阅 `.dev/docs/dotdev-repository-repair/README.md` 列出的 26 份 `.dev/docs/tmp/` 候选，并决定其中哪些可由 TUI 安全归档。本报告是 2026-09-08 的点时归属判断；没有修改源码、测试、配置、`.dev/.dev/` 或任何非本报告文档，没有执行 `git add`、commit 或 push。

**总体结果**：没有一份候选同时满足「正文明确以 TUI footer / request-log / terminal UI 为主题」和「可作为 TUI 自身的点时证据」两项条件。因此**已移动 0 份**，26 份均保持在 `.dev/docs/tmp/`。关键词命中在这些文档中是旁及的实现、引用或被审对象，不能替代正文主题和历史归属。

**判据来源**：本报告先阅读了 `dotdev-repository-repair/README.md` 与 `reports/260908-inventory-review.md`。后者特别确认：`260821-plan-g1-upstream-error-events.md`、`260822-h2-streamreset-cancel-diagnosis.md`、`260822-review-session-closeout.md`、`260822-review-never-silent-failure-events.md` 已被 `upstream/retry-and-continuation/` 的活文档引用；stream reset 不应归 TUI；buffered Chat evidence 不应因 TUI/request-log 关键词而归 TUI。

## 已移动

无。

## 保留于 tmp，并给出后续归档建议

下表的「建议归属」是后续负责相应主题迁移者可采用的目标；本次严格所有权下没有移动任何非 TUI 文档，也没有为这些建议创建目录或改写引用。

| tmp 文件 | 建议归属 | 归属理由 |
|---|---|---|
| `260820-review-session-closeout.md` | `documentation-restructure/history/` | 是 job `d123700e` 的全会话收尾和证据载体复核；虽检查过 footer/PTY 探针，但正文不以 TUI 为对象。 |
| `260821-plan-g1-upstream-error-events.md` | `upstream/retry-and-continuation/history/` | G1 定义上游 `error` / `response.failed` 的终止、重试与交付语义；request log 只是该上游失败事实的一个观察面。 |
| `260821-review-g1-candidate.md` | `upstream/retry-and-continuation/history/` | 评审 G1 的上游错误事件实现，核心是不能将明确失败伪装成成功；并非 TUI 设计或终端 UI 证据。 |
| `260822-candidate-docs-refresh-log.md` | `documentation-restructure/history/` | 是人控候选文档刷新日志；`observability/tui.py` 仅是无消费者清单中的一项。 |
| `260822-doc-citations-review-disposition.md` | `documentation-restructure/history/` | 是代码文档引用修复的处置记录；`request_log.py` 只是被改写引用之一。 |
| `260822-ghc-api-conformance-responses-ws.md` | `anthropic-responses-bridge/history/` | 核查 Responses WebSocket 的上游/下游接线及其与 Responses HTTP 路径的关系；不是 TUI。 |
| `260822-h2-streamreset-cancel-diagnosis.md` | `upstream/retry-and-continuation/history/` | 文本明定上游流级 `RST_STREAM(CANCEL)` 的诊断与后续裁决；review report 已确认此文件被该主题活文档直接引用。 |
| `260822-review-doc-citations-coverage.md` | `documentation-restructure/history/` | 评审文档引用修复的覆盖面和过度改动；TUI/footer/request-log 都是搜索面里的引用对象，不是报告主题。 |
| `260822-review-doc-citations-mapping.md` | `documentation-restructure/history/` | 逐条验证代码注释到现行文档的映射；同样只是跨主题引用审计。 |
| `260822-review-never-silent-failure-events.md` | `upstream/retry-and-continuation/history/` | 核心是上游失败事件、SSE 终止与重试/完成结果；review report 已确认它被该主题活文档引用。 |
| `260822-review-session-closeout.md` | `documentation-restructure/history/` | 是一次全会话终态声明和提交/文档收尾审计；提及 upstream、TUI 和 request log 不构成单主题 TUI 证据。 |
| `260822-review-streamreset-diagnosis-gpt.md` | `upstream/retry-and-continuation/history/` | 明确评审 `RST_STREAM(CANCEL)` 诊断，属同一 upstream 事实链。 |
| `260822-review-streamreset-diagnosis-opus.md` | `upstream/retry-and-continuation/history/` | 对同一 stream reset 诊断进行端到端证伪，归属 upstream。 |
| `260823-nonfile-candidates-review-A.md` | `project-review-principles-skill/history/` | 是跨会话的非文件知识候选枚举与证据对账，主要服务评审/记忆方法，非 TUI。 |
| `260824-cache-control-scope-400-investigation.md` | `anthropic-direct-request-shape/history/` | 调查 `cache_control.ephemeral.scope` 及 direct path 改写链，正文直接以该请求整形主题为中心。 |
| `260824-cc-autocompact-same-version-divergence.md` | `anthropic-direct-request-shape/history/` | 调查 Claude Code 的 cache-control/autocompact 差异及模型名条件；不讨论 TUI 呈现或 request-log 合同。 |
| `260824-count-tokens-heterogeneous-review-gpt.md` | `token-counting/history/` | 评审 `/v1/messages/count_tokens` 的异构路由和校准，request-log 是观测数据而非 TUI 内容。 |
| `260824-count-tokens-prior-art-survey.md` | `token-counting/history/` | 全文清点 count_tokens 的裁决、规格、报告和测试；TUI 仅为交叉引用。 |
| `260824-spec-freeze-encoding-inventory.md` | `documentation-restructure/history/` | 是全仓 Spec freeze 编码点考古；TUI 是被盘点主题之一。 |
| `260827-deferred-survey.md` | `documentation-restructure/history/` | 覆盖八份跨主题台账的优先级调查；其中 TUI §0.5 是一项，不足以拆作 TUI 专属历史证据。 |
| `260827-ledger-cleanup.md` | `documentation-restructure/history/` | 是跨主题 deferred 台账整理及迁出记录，非 TUI 专题。 |
| `260906-buffered-chat-completions-transcript-evidence.md` | `direct-buffered-chat-completions/history/` | 是唯一目标为 `direct buffered /chat/completions` 的会话取证，记录原始 session、request-log 和完成失败；README 点名的 buffered Chat evidence 正应归此主题，而不是 TUI。 |
| `260906-buffered-chat-local-tokenizer-analysis.md` | `token-counting/history/` | 结论是 Responses local estimator 的数量级高估及其与本次 overflow 的因果分离；不是 buffered Chat UI 合同。 |
| `260906-buffered-chat-local-tokenizer-analysis-review.md` | `token-counting/history/` | 独立复核上述 local tokenizer 分析的数字、证据等级和处置边界。 |
| `260906-buffered-chat-local-tokenizer-analysis-review-r2.md` | `token-counting/history/` | 限定复评 local tokenizer 分析的两个 minor，仍是 token-counting 证据链。 |
| `260906-local-tokenizer-code-audit.md` | `token-counting/history/` | 直接审计 local tokenizer、校准、fallback 和 count endpoint；direct buffered Chat 仅在实现地图中说明当前未接线状态。 |

## 未确定

无。上述每份材料均有足以排除 TUI 所有权的正文主题，并给出一个明确的后续归档建议。

## 安全检查与后续门槛

- 已检查 `.dev/docs/tui/history/`：现有 14 个文件均为 `260906-function-call-grouping-*`，与 26 个候选文件名无冲突；本轮没有覆盖任何历史文件。
- 没有凭关键词移动：例如 `260821-plan-g1-upstream-error-events.md` 的 `request_log` 是失败观测字段，`260827-deferred-survey.md` 的 TUI §0.5 是八主题调查中的单项，二者都不满足 TUI 专题判据。
- 建议归档前，接手主题仍须按 repair README 的总规则清点入站引用并改写路径。尤其四份已被 `upstream/retry-and-continuation/` 直接引用的 tmp 文件不能在引用改写前移动。
