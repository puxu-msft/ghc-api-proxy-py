# 15 个退役候选目录 residual 逐份处置账（FRR-02）

**评审范围**：以 2026-09-08 当前工作树为准，只读枚举并逐份检查 `architecture-audit`、`archived-2604-rewrite`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`documentation-restructure`、`early-verification`、`empty-text-block`、`git-housekeeping`、`history`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure` 下全部 regular files。扫描分母为 **219**，不含此前已从这些目录迁出的 12 份承重原件，也不含顶层 `tmp/`。

**总体 verdict**：**pass（仅指 219/219 已有逐份、可执行且不重复既有 canonical original 的 disposition）**。建议迁移 183、删除 36、needs-user-decision 0；本文件不执行移动、删除、改链、`git add`、commit 或 push。所有迁移仍须按 evidence family 原子实施并在实施后复核 source absent、destination present、hash unchanged、basename/path 唯一。

**blocker 数**：0。

## 判定与扫描方法

1. 判据先读：repository repair README、inventory review、merged-state review、final retirement readiness review、retirement reference map、tmp final disposition、first retirement batch。成功条件取自这些独立控制面：没有 living incoming 只关闭 topic-level gate，不能代替逐份原件处置。
2. 文件枚举：对 15 个目录递归执行 `find <dir> -type f`；目录计数为 `9+38+4+3+25+36+17+7+23+28+4+4+5+13+3=219`。非 Markdown 的 `.py`、`.sh`、`.txt` 也计入并逐份检查。
3. 内容检查：每份读取标题或文件头、状态/verdict、章节地图与结论；对 living owner、潜在删除、跨主题归属和原子 family 补读必要正文。事实强度区分直接探针/源码/Git 取证、独立评审、实施自述、设计/计划和纯清单。
4. consumer/owner 扫描：扫描 retained current/living docs、`src/`、`tests/` 与 `pyproject.toml` 的候选路径和 unique basename。大多数 residual 没有 direct current consumer；明确仍消费原件语义的只有旧 2604 的 4 份材料与 vcrpy PoC，逐行列出并要求移动与改链原子完成。
5. 冲突检查：将 219 个 source basename 与活动 retained `history/` 以及 final readiness review 已确认的 12 份前批迁移原件比较。前批 12 个 exact basename 均不在 residual 集；通用名 `README.md`、`spec.md`、`plan.md`、`decisions.md` 的同名不是同一原件，故所有推荐 destination 都增加 family 子目录或重命名，禁止在 retained history 根制造第二份同路径副本。
6. “立即可动”表示 owner、去向和语义边界已确定，不表示本报告授权执行；标注 family 的项目必须同组移动，涉及 current consumer 的项目必须与引用改写同一变更完成。删除项只在调用方接受本 ledger、且同 family 的保留项已落位后执行。

## 原子 evidence families

| Family | 成员范围 | 原子约束 |
|---|---|---|
| EF-ARCH | `architecture-audit` 9 份 | 同批迁入 `server-layout/history/architecture-audit/`；synthesis 与七轴底稿不得拆散。 |
| EF-2604-TUI | `DESIGN.md`、`telemetry-observability.md`、`lib-survey/SELECTIONS.md` | 与 `tui/spec.md` 两处旧路径及 `src/app/observability/request_log.py` 注释改链原子完成。 |
| EF-2604-TOKEN | `tokenization.md`、`hooks-tokenization-spec.md`、早期 Hooks/Tokenization acceptance | 同批迁入 `token-counting/history/`；`src/app/pipeline/driver.py` 注释改链；acceptance 与 oracle 不拆。 |
| EF-DOCS-TMP | `docs-tmp-migration` 25 份 | 保持 README、brief、10 个 batches、10 个 classification reports、抽样审计与两份复核的相对形状。 |
| EF-DOC-RESTRUCTURE | `documentation-restructure` 36 份 | 作为已终止治理方案及其审计链整体进入 repository-repair history；不得让旧 README/Plan 恢复 current authority。 |
| EF-EARLY-P3 | Phase 3 report + runner | 报告与可复现 runner 同批。 |
| EF-EARLY-FINAL | 260716 final 的 13 份 | README/MANIFEST/REPORT/SUMMARY、`run_all.sh` 与 8 probes 保持目录形状。 |
| EF-EMPTY | `empty-text-block` 7 份 + 已迁 `delivery-keepalive/history/260820-review-synthetic-start-fix.md` | 7 份 residual 同批迁入同一 retained topic；实现时改内部相对链接，不复制已迁 key report。 |
| EF-GIT | `git-housekeeping` 23 份 + 已迁两份 provenance | residual 进入 repository-repair history 子目录；前批两份保持现有 canonical root，不再复制。 |
| EF-HISTORY-BRIDGE | `history/archive-260807-legacy-chain` 13 份 | capability/history/stream integration 的 review、verify、squash 证据保持一组。 |
| EF-HISTORY-FORENSICS | `history/proposal.md` + `history/reports/` 12 份 | 调查、proposal、scope/facts reviews、structured logging 与 gone scenario 同批；不带入已蒸馏的旧 `spec.md`/`decisions.md` 副本。 |
| EF-HOOKS | `hooks-subscription-migration` 4 份 + 已迁 beta-strip implementation | residual 同批迁入 request-shape history；已迁原件不复制。 |
| EF-LIFECYCLE | `lifecycle-reorg` 4 份 | 重组、入口切换、代码评审与 transient pidfile 观测同批。 |
| EF-PARITY | `pipeline-rewrite-parity` 5 份 | 前身项目的 translation/retry/ops/traffic/IR 对照保持完整。 |
| EF-SYNC | `sync-refs` 13 份 + 已迁两份承重报告 | residual 保持研究、交叉核验、处置链；前批 canonical 两份只由新索引跨链。 |
| EF-TEST | `test-infrastructure` 3 份 | 同批迁入 server-layout test history；vcrpy PoC 与 `tests/int/recorded/cassettes.py` 改链原子完成。 |

## 逐份 ledger

### `architecture-audit`（9）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `architecture-audit/reports/260814-audit-dependency-graph.md` | AST import 全图；直接测量，强，固定 `44471c6` | 无 direct；current owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-dependency-graph.md` | 保存 159 模块/358 边、环与层次的可复核基线；不是 current architecture。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-audit-duplication.md` | 重复实现与行为漂移探针；强 | 无 direct；owner `server-layout`/bridge | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-duplication.md` | 含 stream/nonstream 漂移反例与 exact duplicate 路由证据，synthesis 依赖。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-audit-library-alternatives.md` | 第三方替代审计；来源核验，中强、版本限定 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-library-alternatives.md` | 记录 8 类自研点的“不换/部分换”证据，不能只留 synthesis 结论。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-audit-lifecycle-ownership.md` | 生命周期 ownership 矩阵；源码核验，强 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-lifecycle-ownership.md` | 保存 parser→delivery→History ownership 接缝的时点矩阵。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-audit-module-boundaries.md` | 模块职责/巨型文件审计；源码与 import 验证，强 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-module-boundaries.md` | 是 current layout 演进的直接前史，含多轴边界与验证记录。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-audit-test-structure.md` | 808-test 结构审计+mutation；强 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-test-structure.md` | 同源测试变异与五层测试地图有独立方法价值。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-audit-typing-leaks.md` | AST typing 基线与抽象泄漏；强 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-typing-leaks.md` | 保存 `Any`/`cast` 计数和非法状态组合的可复核基线。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-synthesis-gaps.md` | 七轴综合/冲突裁决；中强，依赖底稿 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-synthesis-gaps.md` | 是 EF-ARCH 的跨报告索引与修复层次，不能脱离底稿单留。 | 是，EF-ARCH |
| `architecture-audit/reports/260814-synthesis-vs-proposal.md` | 独立体检与 bridge 提案对账；中强，部分转录 | 无 direct；owner `server-layout` | canonical history | `.dev/docs/server-layout/history/architecture-audit/reports/260814-synthesis-vs-proposal.md` | 保留体检与方案 B 覆盖缺口及主会话复验边界。 | 是，EF-ARCH |

### `archived-2604-rewrite`（38）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `archived-2604-rewrite/260403-docs-review-01-claude.md` | 旧文档对抗评审回应；agent 判断，中 | 无 | 删除 | — | 只评已整体失效的 2604 文档，两个结论无独立代码/探针证据，且现有 README 已明确退役边界。 | 是 |
| `archived-2604-rewrite/BACKLOG.md` | 旧目标 backlog；设计性、低 | 无 | 删除 | — | 可选能力已由 current topic deferred/plan 重新拥有；本稿不能作为待办且无独立证据。 | 是 |
| `archived-2604-rewrite/DESIGN.md` | 旧总设计；设计性，但有历史 provenance | `src/app/observability/request_log.py:3` | canonical history | `.dev/docs/tui/history/2604-rewrite/DESIGN.md` | current source 明确以其中 fixed-width frame 为历史来由；须保留原件但不得恢复 authority。 | 是，EF-2604-TUI+改链 |
| `archived-2604-rewrite/README.md` | 旧目录退役导航；事实已由 repair README 蒸馏 | 无 current consumer | 删除 | — | 其唯一 current 作用是声明“整体过期”，该结论已进入 repository repair 与 retained history indexes；迁入会制造第二 current retirement owner。 | 是 |
| `archived-2604-rewrite/ROADMAP.md` | 旧里程碑与延期能力；设计性、低 | 无 | 删除 | — | M1–M4 与能力状态均被 current topic plans/status 取代，无独立观测。 | 是 |
| `archived-2604-rewrite/approval-system.md` | 旧 approval 目标设计；设计性、低 | 无；current implementation/source 自持 | 删除 | — | 描述旧路径和目标 API，current code/tests 已明确实现边界；无独立历史观测。 | 是 |
| `archived-2604-rewrite/authentication.md` | 旧 auth/provider 目标设计；设计性、低 | 无；owner `ghe-device-flow` | 删除 | — | current GHC auth/device-flow docs与源码已分离承接；旧方案含未实现目标，不能留作 evidence。 | 是 |
| `archived-2604-rewrite/config-system.md` | 旧配置说明；混合设计/当时实现，中低 | 无；current schema/source 自持 | 删除 | — | 旧键与默认值会误导；current `config/schema.py` 与 retained specs 已明确蒸馏所需合同。 | 是 |
| `archived-2604-rewrite/data-models.md` | 旧全协议模型目标设计；设计性、低 | 无 | 删除 | — | 大量目标 Pydantic shape 与现行 pipeline 不同，且没有独立运行证据。 | 是 |
| `archived-2604-rewrite/feature-negotiation.md` | 旧 TTL store 说明；时点实现说明，中低 | 无；owner request-shape | 删除 | — | current negotiation/subscriber owner 已按现行源码重述；旧 9 类枚举无独立证据价值。 | 是 |
| `archived-2604-rewrite/header-forwarding.md` | 旧双向 header policy 设计；设计性 | 无；owner request-shape | 删除 | — | 当前 header ownership 与 beta stripping 已在 request-shape Spec/history 明确，旧 blacklist/whitelist 设计不应并存。 | 是 |
| `archived-2604-rewrite/hooks-tokenization-spec.md` | 260717 已实施规格快照；历史 oracle，中强 | 早期 acceptance 以它为 oracle；非 current | canonical history | `.dev/docs/token-counting/history/hooks-tokenization-260717/hooks-tokenization-spec.md` | 与 Hooks/Tokenization acceptance 共同解释当时 PASS；保留为 history，不升级为 current Spec。 | 是，EF-2604-TOKEN |
| `archived-2604-rewrite/lib-survey/260715-selections-review-01-claude.md` | 旧 selections 评审；二手判断，中 | 无 | 删除 | — | 采纳/未采纳结果已明确蒸馏进 `SELECTIONS.md`，无额外原始探针。 | 是 |
| `archived-2604-rewrite/lib-survey/HANDOVER.md` | 旧调研交接；综合/导航，中低 | 无 | 删除 | — | 内容由六域底稿和 `SELECTIONS.md` 重复，下一步已完成，保留会延寿旧任务。 | 是 |
| `archived-2604-rewrite/lib-survey/SELECTIONS.md` | 旧库选型总表；综合，中强、版本限定 | `.dev/docs/tui/spec.md:13` | canonical history | `.dev/docs/tui/history/2604-rewrite/lib-survey/SELECTIONS.md` | TUI current Spec 仍以它解释从 `textual` 转向 `rich.Live` 的历史偏离；只留唯一 provenance。 | 是，EF-2604-TUI+改链 |
| `archived-2604-rewrite/lib-survey/_briefing.md` | 调研派活模板；过程性、低 | 无 | 删除 | — | 只规定已完成六域调查的格式/约束，结论全部在 `SELECTIONS.md`。 | 是 |
| `archived-2604-rewrite/lib-survey/domain1-llm-sdk.md` | SDK 候选调查；版本限定，中强 | 无 | 删除 | — | `AsyncOpenAI/Anthropic`、`httpx_ws`、拒绝 LiteLLM 等结论已逐项蒸馏到 `SELECTIONS.md`；旧版本底稿无 current consumer。 | 是 |
| `archived-2604-rewrite/lib-survey/domain2-reliability.md` | retry/cache/control-flow 库调查；版本限定，中强 | 无 | 删除 | — | 结论已蒸馏到 `SELECTIONS.md`，且旧 auto-truncate 前提已明确撤销。 | 是 |
| `archived-2604-rewrite/lib-survey/domain3-streaming-sse-ws.md` | SSE/WS 库调查；版本限定，中强 | 无 | 删除 | — | 采用/拒绝边界已蒸馏；真实 delivery 现由 retained specs 与代码治理，旧底稿不再提供唯一证据。 | 是 |
| `archived-2604-rewrite/lib-survey/domain4-storage-config.md` | storage/config/CLI 库调查；目标设计期，中 | 无 | 删除 | — | 调查基于“模块尚未实现”的旧前提，结论已进 selections，无独立 current 价值。 | 是 |
| `archived-2604-rewrite/lib-survey/domain5-observability.md` | OTel/TUI 库调查；版本限定，中强 | 无 direct；TUI 只消费 selections | 删除 | — | OTel 版本事实会过期，TUI 历史取舍已由 `SELECTIONS.md` 与现行 TUI 证据承接。 | 是 |
| `archived-2604-rewrite/lib-survey/domain6-hot-path-foundations.md` | JSON/token/retry foundations 调查；中强 | 无 | 删除 | — | 结论已进 selections；其中 auto-truncate 段已撤销，保留底稿会混合有效与失效前提。 | 是 |
| `archived-2604-rewrite/model-resolution.md` | 旧 resolver 目标设计；设计性、低 | 无；owner multi-provider-routing | 删除 | — | current routing/model-provider Spec 与源码已重建真实合同，旧链式规则无独立证据。 | 是 |
| `archived-2604-rewrite/multi-protocol.md` | 旧 Azure/Gemini adapter 设计；设计性、低 | 无；owner multi-provider-routing/client-leg-formats | 删除 | — | 薄适配/共享 pipeline 前提已被后续审计证伪并由 current owners 重述。 | 是 |
| `archived-2604-rewrite/plan/260715-implementation-plan-review-01-claude.md` | 已执行计划评审；二手过程，中 | 无 | 删除 | — | findings 已采纳到随后完成的 plan，原计划又整体失效；无独立证据。 | 是 |
| `archived-2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md` | 已执行 TDD 计划；历史过程，低 | 无 | 删除 | — | 当时行为 oracle 已单独保留，逐阶段执行稿明确禁止重放且不增加验收证据。 | 是 |
| `archived-2604-rewrite/plan/HOOKS_TOKENIZATION_KICKOFF.md` | 已完成 kick-off；纯执行提示，低 | 无 | 删除 | — | 仅重述已完成计划和旧路径，明确禁止 current 执行。 | 是 |
| `archived-2604-rewrite/plan/IMPLEMENTATION_HANDOVER.md` | Phase 5–9 已完成交接；过程快照，中低 | 无 | 删除 | — | next actions 已完成或由 current topic 重新拥有，验证事实由 early-verification 原件保留。 | 是 |
| `archived-2604-rewrite/plan/IMPLEMENTATION_PLAN.md` | Phase 0–8 已完成计划；设计/过程，中 | 无 | 删除 | — | 旧阶段计划含已撤销 auto-truncate/server-tool 目标；验收方法另有原件，不能重放。 | 是 |
| `archived-2604-rewrite/plan/PHASE_0_KICKOFF.md` | Phase 0 执行提示；低 | 无 | 删除 | — | 纯失效 kick-off，当前依赖/CLI/架构均已变化，无独立证据。 | 是 |
| `archived-2604-rewrite/project-structure.md` | 旧模块地图；时点说明，中低 | 无；owner `server-layout` | 删除 | — | current server-layout 与源码是唯一 owner，旧路径地图无独立观测。 | 是 |
| `archived-2604-rewrite/request-pipeline.md` | 旧 Anthropic pipeline 说明；混合设计，中低 | 无；owner bridge/direct-passthrough | 删除 | — | current drivers、events 与 retry ownership 已由 retained Specs/src 重述；旧图无唯一证据。 | 是 |
| `archived-2604-rewrite/sanitize-pipeline.md` | 旧 mandatory sanitize 顺序；设计性 | 无；owner request-shape | 删除 | — | current subscriber order 与 negative space 已明确，旧 hooks-system 关系已失效。 | 是 |
| `archived-2604-rewrite/shutdown.md` | 旧四阶段 shutdown 设计；设计性 | 无 current consumer；仅旧负面叙述已清理 | 删除 | — | graceful-shutdown/systemd retained docs 已承接有效行为；reference map 明确不要把旧稿迁成 current evidence。 | 是 |
| `archived-2604-rewrite/streaming.md` | 旧 streaming 总设计；设计性 | 无；owner delivery/client-leg-formats | 删除 | — | “默认零缓冲”等旧合同与 current delivery 不一致，且关键 resilience 原件已另迁。 | 是 |
| `archived-2604-rewrite/telemetry-observability.md` | 旧日志/TUI 设计；历史 provenance，中 | `.dev/docs/tui/spec.md:9` | canonical history | `.dev/docs/tui/history/2604-rewrite/telemetry-observability.md` | TUI current Spec 用其解释只读边界沿革；保留为历史，不称用户裁决。 | 是，EF-2604-TUI+改链 |
| `archived-2604-rewrite/thinking-pipeline.md` | 旧 thinking/reasoning 目标设计；设计性 | 无；owner reasoning-carrier/request-shape | 删除 | — | current v2 carrier 与 thinking subscriber 已有 retained Specs/src；旧 L1–L3 方案无独立证据。 | 是 |
| `archived-2604-rewrite/tokenization.md` | 旧 token wire-contract 说明；历史 provenance，中 | `src/app/pipeline/driver.py:432` | canonical history | `.dev/docs/token-counting/history/2604-rewrite/tokenization.md` | current source 注释仍以“每协议独立 estimator/calibration”为历史理由；须改链到唯一历史原件。 | 是，EF-2604-TOKEN+改链 |

### `copilot-token-identity`（4）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `copilot-token-identity/reports/260807-audit-token-identity-squash.md` | source/main squash 审计；Git/blob 证据强 | 无 direct；auth owner `ghe-device-flow` | canonical history | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-audit-token-identity-squash.md` | 保存 exact archive target、preimage/result 与 squash gate。 | 是 |
| `copilot-token-identity/reports/260807-review-token-exchange-identity-r2.md` | identity fix 定向终审；强 | 无 direct；owner `ghe-device-flow` | canonical history | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-review-token-exchange-identity-r2.md` | 关闭首轮 major 并限定四身份头/刷新范围，是评审链终态。 | 是 |
| `copilot-token-identity/reports/260807-review-token-exchange-identity.md` | 首轮代码评审；强，1 major | 无 direct；owner `ghe-device-flow` | canonical history | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-review-token-exchange-identity.md` | 与 R2 形成 finding→closure 链，不能只留 PASS。 | 是 |
| `copilot-token-identity/reports/260807-verify-token-exchange-identity.md` | scoped 独立验收；PASS，强且边界明确 | 无 direct；owner `ghe-device-flow` | canonical history | `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-verify-token-exchange-identity.md` | 保存 MockTransport、聚焦回归与真实 A/B 的验收边界。 | 是 |

### `count-tokens`（3）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `count-tokens/reports/260816-count-tokens-review.md` | provider-chain 接线评审；强，含 blocker closure | 无 direct；successor `token-counting` | canonical history | `.dev/docs/token-counting/history/count-tokens/reports/260816-count-tokens-review.md` | 记录“测试孤立新 app/生产仍旧路由”失败机制及复评。 | 是，EF-2604-TOKEN 的 successor family |
| `count-tokens/reports/260820-review-responses-token-counting.md` | Responses 估算评审+mutation；强 | 无 direct；successor `token-counting` | canonical history | `.dev/docs/token-counting/history/count-tokens/reports/260820-review-responses-token-counting.md` | reasoning 密文计数、测试分辨力与 calibration 键问题是后续测量前史。 | 是 |
| `count-tokens/reports/260824-heterogeneous-count-tokens-measurement.md` | 314 次真实测量；直接观测，强 | 无 direct；successor `token-counting` | canonical history | `.dev/docs/token-counting/history/count-tokens/reports/260824-heterogeneous-count-tokens-measurement.md` | 定量证明机制通但数值系统性高估；与 prior-art/后续修复证据链相关。 | 是 |

### `docs-tmp-migration`（25）

本节 25 项的 current consumer 均为“无 direct；current 文档仓修复 owner 为 `dotdev-repository-repair`”，且均须按 EF-DOCS-TMP 原子迁移。destination 保留原目录内相对形状，使批次表、分类表、README 与复核之间的链接仍可解析。

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `docs-tmp-migration/BRIEF.md` | 417 份分类派活 brief；过程合同，中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/BRIEF.md` | 保存当时分类判据、允许目标和“不改原件”边界；是十批输出的解释入口。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/README.md` | 482-file 迁移终态索引；Git/计数事实强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/README.md` | 是旧 `docs/tmp`/`docs/agents` 搬迁提交、计数、改判与遗留项的唯一综合账。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-01.txt` | batch-01 原始文件名 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-01.txt` | 是 classify-batch-01 分母底片，单独删除会失去双向集合核对。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-02.txt` | batch-02 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-02.txt` | 保留对应 43 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-03.txt` | batch-03 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-03.txt` | 保留对应 37 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-04.txt` | batch-04 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-04.txt` | 保留对应 38 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-05.txt` | batch-05 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-05.txt` | 保留对应 40 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-06.txt` | batch-06 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-06.txt` | 保留对应 40 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-07.txt` | batch-07 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-07.txt` | 保留对应 40 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-08.txt` | batch-08 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-08.txt` | 保留对应 48 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-09.txt` | batch-09 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-09.txt` | 保留对应 40 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/batches/batch-10.txt` | batch-10 manifest；机械事实 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/batches/batch-10.txt` | 保留对应 48 项分类输入。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-audit-classification-sample.md` | 417 行分类抽样审计；强，31 份全文样本 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-audit-classification-sample.md` | 记录 9 份错误归类与 13 份未分类核验，是 README 改判的独立证据。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-01.md` | batch-01 逐份分类表；point-in-time，中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-01.md` | 与 batch-01 manifest 一一对应，保存逐件归属而非泛化目录结论。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-02.md` | batch-02 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-02.md` | 保存 43 项逐件归属及 cross-topic 限定。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-03.md` | batch-03 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-03.md` | 保存 37 项逐件归属及 Git-housekeeping 例外。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-04.md` | batch-04 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-04.md` | 保存 38 项逐件归属和 service/systemd 边界。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-05.md` | batch-05 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-05.md` | 保存 40 项 bridge code-review 归属。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-06.md` | batch-06 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-06.md` | 保存 40 项 implementation/current-review 归属。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-07.md` | batch-07 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-07.md` | 保存 40 项 service-cutover/retry 归属。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-08.md` | batch-08 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-08.md` | 保存 48 项 verify/systemd/bridge 归属。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-09.md` | batch-09 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-09.md` | 保存 empty-text/hooks 等 40 项逐件归属。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-classify-batch-10.md` | batch-10 逐份分类表；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-classify-batch-10.md` | 保存 token/test/websearch 等 48 项逐件归属及未分类原因。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-review-instruction-surfaces.md` | 搬迁后写回旧目录的证伪评审；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-review-instruction-surfaces.md` | 证明旧 worktree 指令可重建 `docs/tmp` 的 blocker；是规则迁移风险的独立证据。 | 是，EF-DOCS-TMP |
| `docs-tmp-migration/reports/260821-review-migration-integrity.md` | source/destination blob 与 link 完整性评审；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/docs-tmp-migration/reports/260821-review-migration-integrity.md` | 106 tracked+355 untracked 的完整性、可逆性与断链 finding 是搬迁事实底片。 | 是，EF-DOCS-TMP |

### `documentation-restructure`（36）

本节 36 项的 current consumer 均为“无 direct；`anthropic-responses-bridge/implementation.md` 已改指 `dotdev-repository-repair`”。旧 generation/certificate/action-gate 方案明确终止；迁入只保存历史，不恢复任何 current approval。整棵按 EF-DOC-RESTRUCTURE 保持相对形状。

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `documentation-restructure/README.md` | 旧 topic 终止/剩余目标索引；中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/README.md` | 是 archive plan 与 34 份报告的边界入口；迁后仅作 history index。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/archive-260808/plan.md` | 已终止渐进重组 Plan；历史设计，中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/archive-260808/plan.md` | 记录 42-source 映射与后来废止的 proof governance；必须与 review chain 共存才不会被误当 current。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260806-audit-docs-index-state.md` | docs/agents index/worktree 审计；Git/blob 强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260806-audit-docs-index-state.md` | 保存 6 文件 A/AM、并发漂移与精确 commit 机制的直接证据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260806-docs-freeze-check-pre.md` | 并发收口/内容 identity 检查；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260806-docs-freeze-check-pre.md` | 是正式文档冻结序列的 point-in-time gate 证据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260806-review-doc-migration-plan-r2.md` | 42-source Plan R2；独立评审，强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260806-review-doc-migration-plan-r2.md` | 保存 source/destination 完整集与 producer ownership 缺口。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260806-review-doc-migration-plan-r3.md` | Plan R3；0 major 定向复评，强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260806-review-doc-migration-plan-r3.md` | 关闭 R2 并建立命名/distillation 当时门槛，是迭代链必要节点。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260806-review-tmp-distillation.md` | tmp→正式载体对账；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260806-review-tmp-distillation.md` | 记录 5 个未归纳 major，是后续矩阵与 current-state 同步的来源。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-doc-links.md` | current relative links/fragment 审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-doc-links.md` | 保存当时 7 文档 link gate 的 parser 与 false-positive 边界。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-docs-commit-boundary.md` | 7 文档提交边界审计；Git/index 强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-docs-commit-boundary.md` | 证明 current index/链接证据漂移的两个 major及精确 staging 门。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-docs-latest.md` | 10 正式 docs 状态依赖审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-docs-latest.md` | 是最小 checkpoint 与五项暂缓的 point-in-time dependency map。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-four-doc-checkpoint.md` | 四 living docs checkpoint 审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-four-doc-checkpoint.md` | 记录 Implementation 缺 exact-byte review 的 blocker。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-living-checkpoint.md` | 五文档 checkpoint 审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-living-checkpoint.md` | 保存三文件可先 checkpoint、两文件待复评的集合证据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-plan-input-identities.md` | Plan/Spec/Acceptance hash 审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-plan-input-identities.md` | 证明 Acceptance identity 漂移导致 Plan fail-closed。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-readme-drift.md` | bridge README provenance/drift 审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-readme-drift.md` | 保存旧 Acceptance verdict 被外推及标题漂移的具体证据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-audit-tmp-naming.md` | tmp 命名/重复机械审计；中强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-audit-tmp-naming.md` | 是 260807 报告集合与轮次/备份清点底片。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-doc-state-dependency-dag.md` | 7 文档 hash/DAG 状态表；机械事实强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-doc-state-dependency-dag.md` | checkpoint 审计依赖其 identity 与同步顺序。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-resume-audit-four-doc-checkpoint.md` | b91e58a 四文档复审；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-resume-audit-four-doc-checkpoint.md` | 记录两个 blocker 与 pending 复评的恢复点。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-resume-audit-living-checkpoint-r2.md` | checkpoint R2；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-resume-audit-living-checkpoint-r2.md` | 明确 hash 稳定但两份无 exact review 的 pending 边界。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-resume-audit-living-checkpoint-r3.md` | checkpoint R3；强，4 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-resume-audit-living-checkpoint-r3.md` | 将 Implementation 内容门失败与 Git 边界通过分开。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-resume-audit-living-checkpoint-r4.md` | checkpoint R4；pending | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-resume-audit-living-checkpoint-r4.md` | 记录新 bytes 无报告、不迁移旧 finding 的正确状态。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-resume-audit-living-checkpoint-r5.md` | checkpoint R5；pending | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-resume-audit-living-checkpoint-r5.md` | 延续 exact-hash 终审等待链，不能只留最终一轮。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-resume-audit-living-checkpoint-r6.md` | checkpoint R6；pending | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-resume-audit-living-checkpoint-r6.md` | 记录最后 new bytes 与未开 staging gate 的恢复点。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-bootstrap-protocol.md` | bootstrap generation 预审；设计+反例，中强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-bootstrap-protocol.md` | 8 条终止性不变量解释该方案为何后来复杂化并被废止。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r10.md` | living Plan R10；0 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r10.md` | 保存 current-carrier identity 同步后的最后完整复评。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r11.md` | living Plan R11 stable-hash 终审 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r11.md` | 证明 R10 后 bytes 未变；是旧 Plan 评审链终点。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r4.md` | Plan R4；2 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r4.md` | 首次指出规范 identity 与 distillation deadline 缺口。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r5.md` | Plan R5；2 major 未闭合 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r5.md` | 证明同 hash 未吸收 R4 finding，防止误读迭代状态。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r6.md` | Plan R6；0 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r6.md` | 关闭 identity/distillation 两门并回归 42-owner 集。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r7.md` | Plan R7；2 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r7.md` | 暴露 0A 重入与 post-cut false-green，是废止 proof machinery 的关键风险证据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r8.md` | Plan R8；0 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r8.md` | 记录 R7 两 major 的机械关闭，维持 review chain 完整。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-review-doc-migration-plan-r9.md` | Plan R9；0 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-review-doc-migration-plan-r9.md` | 完整通读后的 current identity/owner 回归，承接到 R10。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260807-tmp-distillation-matrix.md` | 260807 报告→正式 owner 矩阵；机械账，中强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260807-tmp-distillation-matrix.md` | 记录 covered/partial/pending 截止规则，是 Plan review chain 的输入。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/260816-candidate-docs-review.md` | human-controlled candidates 对账；源码/文档证据强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/260816-candidate-docs-review.md` | 九个 major 记录候选稿误把已决/已实现事项当提案的具体证据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/docs-migration-plan.md` | 初版渐进迁移计划；历史设计，中 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/docs-migration-plan.md` | 与 truth audit、首轮 review 构成旧方案起点；只在 history 中解释演进。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/live-doc-truth-audit.md` | 42 旧文档 vs current source 真相审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/live-doc-truth-audit.md` | 2 blocker/9 major 是“不能原样提升旧设计”的独立事实依据。 | 是，EF-DOC-RESTRUCTURE |
| `documentation-restructure/reports/review-doc-migration-plan.md` | 初版 Plan 独立评审；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/documentation-restructure/reports/review-doc-migration-plan.md` | 保存 42-source 集合检查、5 major 与恢复流程反例，不能只保留后来终审。 | 是，EF-DOC-RESTRUCTURE |

### `early-verification`（17）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `early-verification/README.md` | 三组历史资产导航；二次索引，中 | 无；current verification owner 为根规则/tests | 删除 | — | 16 个原件迁入各 retained history 后，本导航只重复来源/时点，目标 topic 的 history index 应接管导航。 | 是，在 EF-EARLY-P3/FINAL/TOKEN 落位后 |
| `early-verification/archive-260715-phase3/PHASE3_ACCEPTANCE_REPORT.md` | Phase 3 黑盒验收；2 blocker/1 major，强 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260715-phase3/PHASE3_ACCEPTANCE_REPORT.md` | 保存协议模型、路由、SSE/WS 的失败矩阵；必须与 runner 共址。 | 是，EF-EARLY-P3 |
| `early-verification/archive-260715-phase3/phase3_acceptance.py` | Phase 3 独立 probe runner；test-only 方法资产 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260715-phase3/phase3_acceptance.py` | 是报告中 15 项结果的可复现方法；不得单留 verdict。 | 是，EF-EARLY-P3 |
| `early-verification/archive-260716-final/MANIFEST.md` | 13-file acceptance manifest；机械事实 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/MANIFEST.md` | 解释 runner/probe 目录与当时结果；EF-EARLY-FINAL 索引。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/README.md` | Phase 0–8 验收矩阵/运行说明；point-in-time | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/README.md` | 保留黑盒边界、动态端口和无凭据方法，不作为 current runbook。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/REPORT.md` | Phase 0–8 完整验收；10/11，强、WS skip | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/REPORT.md` | 是每域实证与 skipped 限定的原件，不能用 SUMMARY 替代。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/SUMMARY.md` | 验收摘要；派生，中 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/SUMMARY.md` | 作为报告/资产快速索引保留，且与完整报告同组避免摘要冒充全证据。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/00_cli_smoke.sh` | CLI/config 黑盒 probe；直接方法资产 | 无 direct；owner bridge history | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/00_cli_smoke.sh` | 对应验收域 1；保留原字节与旧路径。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/01_dynamic_port_startup.py` | startup/health/shutdown probe；方法资产 | 无 direct；owner bridge history | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/01_dynamic_port_startup.py` | 对应动态端口与健康检查实证。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/02_anthropic_protocol.py` | Anthropic nonstream/stream probe；方法资产 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/02_anthropic_protocol.py` | 对应 bridge 主要协议验收。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/03_openai_three_prefixes.py` | OpenAI 三前缀 probe；方法资产 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/03_openai_three_prefixes.py` | 对应 Phase 3 路由验收。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/04_responses_websocket.py` | Responses WS probe；方法资产，实际 skip | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/04_responses_websocket.py` | 解释报告 1 个 skipped 的确切机制；不能删后只留“10/11”。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/05_history_metrics.py` | History/metrics probe；方法资产 | 无 direct；owner bridge history | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/05_history_metrics.py` | 对应当时 Phase 6 验收，保留为历史而非 current history contract。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/06_approval_system.py` | approval probe；方法资产 | 无 direct；owner bridge history | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/06_approval_system.py` | 对应 Phase 7 黑盒方法。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/probes/07_gemini_azure.py` | Gemini/Azure probe；方法资产 | 无 direct；owner bridge history | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/probes/07_gemini_azure.py` | 对应 Phase 8 多协议验收。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260716-final/run_all.sh` | 8-probe orchestrator；方法资产 | 无 direct；owner bridge history | canonical history | `.dev/docs/anthropic-responses-bridge/history/early-verification/archive-260716-final/run_all.sh` | 固化 probe 顺序、PASS/FAIL 统计与当时 root；不得修成 current runner。 | 是，EF-EARLY-FINAL |
| `early-verification/archive-260717-hooks-tokenization/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | Hooks/Tokenization 独立验收；PASS，强 | 无 current；历史 oracle 是 2604 spec | canonical history | `.dev/docs/token-counting/history/hooks-tokenization-260717/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | 与迁入的 `hooks-tokenization-spec.md` 共址，保留当时 matrix 与 PASS 射程。 | 是，EF-2604-TOKEN |

### `empty-text-block`（7）

本组 current contract 由 `anthropic-direct-request-shape` 承接，但关键 synthetic-start review 已先迁入 `delivery-keepalive/history/`。为避免复制该原件并保持根因链共址，7 份 residual 统一进入 `delivery-keepalive/history/empty-text-block/reports/`，current request-shape 只跨主题链接。

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `empty-text-block/reports/260820-empty-text-block-copilot-api-js.md` | 参考实现源码+探针调查；强、固定 SHA | 无 direct；owners request-shape/keepalive | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-copilot-api-js.md` | 保存 `trim()==empty`、删块与路径门的对照证据。 | 是，EF-EMPTY |
| `empty-text-block/reports/260820-empty-text-block-inbound-trace.md` | direct leg 全读写点追踪；强 | 无 direct；owners request-shape/keepalive | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-inbound-trace.md` | 证明入站不制造空块、legacy sanitizer 未接线，是根因排除链。 | 是，EF-EMPTY |
| `empty-text-block/reports/260820-empty-text-block-response-side.md` | 响应产出链调查；源码事实强 | 无 direct；owners request-shape/keepalive | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-response-side.md` | 定位 synthesized headers 与正常空块产出，是修复选择的一手代码证据。 | 是，EF-EMPTY |
| `empty-text-block/reports/260820-empty-text-block-synthesis.md` | 根因+两片修复综合；一手 transcript/探针，强 | 无 direct；owners request-shape/keepalive | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-synthesis.md` | 是三调查、报告所载裁决、上游实测与三轮评审的唯一综合索引；迁移不升级裁决归属。 | 是，EF-EMPTY；同步改内部 key-review 链接 |
| `empty-text-block/reports/260820-review-blank-text-subscriber.md` | `4f2d786` 独立代码评审；强 | 无 direct；owner request-shape | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-review-blank-text-subscriber.md` | 保存顺序理由错误、lookahead 边界与测试分辨力。 | 是，EF-EMPTY |
| `empty-text-block/reports/260820-review-final-and-probe.md` | `3193880`+真实上游 probe 复评；强 | 无 direct；owners request-shape/keepalive | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-review-final-and-probe.md` | 记录修订/探针方法论的应改项与阳性对照，不由 synthesis 完全替代。 | 是，EF-EMPTY |
| `empty-text-block/reports/260820-review-unconditional-blank-strip.md` | 无条件剥离实现评审；强，2 should-fix | 无 direct；owner request-shape | canonical history | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-review-unconditional-blank-strip.md` | 保存“测试未走 Responses leg”和全空日志矛盾的反例。 | 是，EF-EMPTY |

### `git-housekeeping`（23）

本组均无 retained current direct consumer；仓库操作与 dotdev 合并的 current owner 是 `dotdev-repository-repair`。前批已迁 `260904-dotdev-dirty-inventory-disposition-recheck.md` 与 `260904-dotdev-merge-review-gpt-opus.md` 保持现有 canonical path，以下 23 份不得再复制它们。

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `git-housekeeping/reports/260807-audit-archives-worktrees.md` | refs/worktrees 清理审计；Git 证据强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260807-audit-archives-worktrees.md` | 保存 archive target、main patch-id 等价与保留/清理集合。 | 是，EF-GIT |
| `git-housekeeping/reports/260807-audit-worktree-cleanup-r2.md` | 18-worktree R2 审计；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260807-audit-worktree-cleanup-r2.md` | 是 13 组可清理与新 worktree 强制保留的事实底片。 | 是，EF-GIT |
| `git-housekeeping/reports/260807-final-worktree-cleanup-plan.md` | exact-ref 机械清理合同；point-in-time，中强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260807-final-worktree-cleanup-plan.md` | 明确非删除授权并保存分类/gate，解释随后 reviews。 | 是，EF-GIT |
| `git-housekeeping/reports/260807-review-worktree-cleanup-plan.md` | cleanup plan 首轮复评；强，1 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260807-review-worktree-cleanup-plan.md` | 记录漏列 stream-facts/network-retry worktrees 的失败机制。 | 是，EF-GIT |
| `git-housekeeping/reports/260807-review-worktree-cleanup-r2.md` | current 集合独立复核；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260807-review-worktree-cleanup-r2.md` | 修正 19 worktrees/29 heads 与 route blob oracle，完成同一清理证据链。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition-recheck-r2.md` | 脏文件处置第二轮窄复评；pass，强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition-recheck-r2.md` | 与已迁首轮 recheck 不同 basename/bytes；关闭其两项 major，不能误当重复。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition.md` | 29-file 最终处置账；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition.md` | 是 inventory→living carrier→最终评审的唯一处置链。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-dirty-inventory.md` | `.dev` 29-file 语义盘点；直接枚举，强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-dirty-inventory.md` | 保存 A/B/C/D 分母、逐文件归组与不执行边界。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus-r2.md` | merge candidate R2；1 major open | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus-r2.md` | 与已迁首轮报告及 R3 形成 F-04 closure 链。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus-r3.md` | merge candidate R3；pass | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus-r3.md` | 是 F-04 closed 的终态证据。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-peer-report-merge-review-gpt-opus.md` | peer-report exact-path merge 评审；Git object 强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-peer-report-merge-review-gpt-opus.md` | 保存 f491f52/c3601f6/0e64240 三树 C1–C6 核验。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-remote-import-review-disposition.md` | remote import findings 处置；closed | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-remote-import-review-disposition.md` | 是首轮 1 blocker/2 major 的唯一采纳账。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-remote-import-review-gpt-opus-r2.md` | remote import 窄复评；pass，强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-remote-import-review-gpt-opus-r2.md` | 逐条关闭 F-01～F-03 并核原件不变。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-remote-import-review-gpt-opus.md` | origin/dotdev 导入评审；1 blocker/2 major | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-remote-import-review-gpt-opus.md` | 保存旧 living state 冲突与 source-unreachable 的直接发现。 | 是，EF-GIT |
| `git-housekeeping/reports/260904-dotdev-remote-merge-review-gpt-opus.md` | actual merge commit 评审；Git object 强，pass | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260904-dotdev-remote-merge-review-gpt-opus.md` | 保存 parent/tree/blob/worktree C1–C7 的合并完整性证据。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-conflict-history-tests.md` | merge 历史/测试冲突调查；confirmed，in-review | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-conflict-history-tests.md` | 记录 13-path/28-hunk 分母、分叉历史与测试组合判据。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-conflict-observability.md` | request log/trace 冲突逐 hunk 调查；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-conflict-observability.md` | 保存 observability 双方意图和逐文件合并建议。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-conflict-pipeline-core.md` | pipeline/passthrough 冲突调查；强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-conflict-pipeline-core.md` | 记录 completion/status、observation 与 request translation 三轴组合。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-conflict-translation.md` | translation driver 逐 hunk 调查；Git/blob 强 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-conflict-translation.md` | 保存四文件 base/ours/theirs 与 semantic merge 约束。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-resolution-closeout.md` | merge resolution 终态 closeout；settled/pass | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-resolution-closeout.md` | 是四调查、验证与 preserved WIP 的终态索引。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-resolution-review-disposition.md` | 六份 review/investigation 处置账；closed | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-resolution-review-disposition.md` | 保存采纳/驳回与 main/docs candidate identities。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-resolution-review-runtime.md` | runtime 独立评审；needs-fix→复评 | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-resolution-review-runtime.md` | 保存 terminal snapshot 被后续 event 改写的 major及 closure。 | 是，EF-GIT |
| `git-housekeeping/reports/260905-merge-resolution-review-spec-tests.md` | Spec/tests 独立评审；needs-fix | 无 direct；owner repair | canonical history | `.dev/docs/dotdev-repository-repair/history/git-housekeeping/reports/260905-merge-resolution-review-spec-tests.md` | 与 runtime review 互补，处置账不能替代原始 findings。 | 是，EF-GIT |

### `history`（28）

旧 topic 的 living residual 已迁入 `upstream/retry-and-continuation/deferred.md` §24～§26；`decisions.md` §5 查询面和 §6.1/§6.2 已分别有 canonical extracts `decisions-20260821-query-surface.md` 与 `decisions-20260821.md`。因此不再迁整份 `decisions.md`，避免把相同决定复制第二份。其余两条 evidence chain 分开归档。

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `history/archive-260807-legacy-chain/reports/260807-resume-audit-history-squash-prep.md` | History source squash 预审；Git/hash 强，1 major | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-audit-history-squash-prep.md` | 保存未提交 WIP、latest review 与最终 squash 条件。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-audit-history-squash-r2.md` | final candidate squash 审计；强，pass | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-audit-history-squash-r2.md` | 记录四提交 range、9 路径 preimage/result 与 archive target。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-capability-history-integration.md` | capability+History staged integration 预审；强 | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-capability-history-integration.md` | 保存共享 client/executor 的合并不变量和禁用整文件选边。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts-r2.md` | History facts R2 code review；1 major/1 minor | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts-r2.md` | 与 R1/R3/R4 形成逐轮 finding closure。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts-r3.md` | History facts R3；1 major | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts-r3.md` | 保存 post-calibration late-failure 未闭合门。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts-r4.md` | History facts R4；0 major，可 squash | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts-r4.md` | 是 exact source tip 的最终内容放行。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-facts.md` | History facts 首轮 code review；3 major | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-facts.md` | 原始 findings 不能由 R4 PASS 取代。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-squash-evidence.md` | review/PASS/squash 绑定复核；强 | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-squash-evidence.md` | 绑定 final review、verification、squash audit 与 exact archive target。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-stream-integration-r2.md` | History+stream integration R2；0 major | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-stream-integration-r2.md` | 关闭共享 client/consumer contract major并记录测试。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-review-history-stream-integration.md` | History+stream integration 首轮；1 major | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-review-history-stream-integration.md` | 保存真实 `HistoryConsumer` 与 stream route 不兼容的失败机制。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-verify-history-facts-r2.md` | History facts 定向验收 R2；PASS | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-verify-history-facts-r2.md` | 对 final tip 的 key-path matrix，与 review 结论射程不同。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-verify-history-facts.md` | History facts 初次验收；scoped PASS | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-verify-history-facts.md` | 保留早期 PASS 后仍被 code review 找到 major 的反例。 | 是，EF-HISTORY-BRIDGE |
| `history/archive-260807-legacy-chain/reports/260807-resume-verify-history-stream-integration.md` | History+stream 独立验收；PASS | 无 direct；bridge owner | canonical history | `.dev/docs/anthropic-responses-bridge/history/history-legacy-chain/reports/260807-resume-verify-history-stream-integration.md` | 保存定向 tests、真实 consumer spy 与明确未覆盖矩阵。 | 是，EF-HISTORY-BRIDGE |
| `history/decisions.md` | 代行裁决记录；混合 authority，部分已迁 | 无旧-path consumer；successor upstream | 删除 | — | §5 查询面与 §6 两项已逐字迁到两个 canonical extracts并由 living deferred 承接；§1～§4 被 §5 重定取代。迁整份会重复同一决定并重新带入已失效裁决。 | 是，在核对两个 extracts 后 |
| `history/proposal.md` | 取证能力事实调查+已作废十片方案；强事实/失效计划混合 | 无 direct；successor upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/proposal.md` | §1 调查仍是后续重定依据；banner 已清楚标明 §6 作废，保真归档不升级。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-forensic-demand-audit.md` | 线上事故取证需求全量盘点；直接报告对账，强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-forensic-demand-audit.md` | 是 proposal 四缺口频次与取舍的原始证据。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-history-as-fixture-source.md` | history→cassette 能力差距调查；源码/DB 只读，强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-history-as-fixture-source.md` | 保存 cassette 完整结构、最小记录缺口与体积估算边界。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-history-wiring-audit.md` | legacy/new import closure 接线审计；强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-history-wiring-audit.md` | 证明 History 子系统未进 production chain，不是简单配置关闭。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-review-history-forensics-proposal-r2.md` | proposal r2 事实复评；强，新增 5 major | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-proposal-r2.md` | 保存 headers、容量、Spec 顺序和 sink 合同的反例。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-review-history-forensics-proposal.md` | proposal 首轮事实评审；强，6 blocker/5 major | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-proposal.md` | 原始 blocker 是后续大幅重写的依据，不能只留 r2。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-review-history-forensics-r3-spotcheck.md` | proposal r3 定点抽查；源码核验强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-r3-spotcheck.md` | 保存五处精确核验与额外硬矛盾。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-review-history-forensics-scope-r2.md` | intent/scope R2；强，1 blocker/2 major | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-scope-r2.md` | 记录 debug replay、session 聚合与分叉选择的范围缺口。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260820-review-history-forensics-scope.md` | intent/scope 首轮；20 findings | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260820-review-history-forensics-scope.md` | 是 r2 逐条处置的输入，保留原始意图缺口。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260821-gone-scenario-persistence.md` | `gone` 结局持久化调查/设计；源码事实强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-gone-scenario-persistence.md` | 保存 client disconnect/gone 与记录生命周期的边界证据。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260821-review-spec-facts.md` | history Spec 事实评审；强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-review-spec-facts.md` | 记录 Spec current-source 全称断言和持久化事实问题。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260821-review-spec-scope.md` | history Spec scope 评审；强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-review-spec-scope.md` | 保存查询/归档/export/replay 范围是否越界的独立判断。 | 是，EF-HISTORY-FORENSICS |
| `history/reports/260821-structured-logging-design.md` | structlog 统一事件设计；设计+源码核验，中强 | 无 direct；owner upstream | canonical history | `.dev/docs/upstream/retry-and-continuation/history/history-forensics/reports/260821-structured-logging-design.md` | decisions §5 将其明确移入 deferred；保留原设计以解释未采纳架构改进。 | 是，EF-HISTORY-FORENSICS |
| `history/spec.md` | 已被 §1 banner 重定的旧 forensic Spec；失效规范 | 无 old-path consumer；successor deferred | 删除 | — | 全套 L1/L2/L3、HTTP、archive/export 合同约六成失去前提；仍有效的字节保真、gap 与查询面已进入 current upstream status/deferred及 canonical decision extracts。原稿没有独立观测，迁入会与 current successor 形成第二规范。 | 是 |

### `hooks-subscription-migration`（4）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `hooks-subscription-migration/reports/260820-external-rewrite-surface.md` | 新/旧链全部改写接缝盘点；源码强 | 无 direct；current owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/hooks-subscription-migration/reports/260820-external-rewrite-surface.md` | 证明 legacy hooks 与 `SubscriberRegistry` 两套机制及响应侧缺口。 | 是，EF-HOOKS |
| `hooks-subscription-migration/reports/260820-js-rewriter-architecture.md` | 参考项目 rewriter/hook 调查；源码强、版本限定 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/hooks-subscription-migration/reports/260820-js-rewriter-architecture.md` | 保存两级 registry、挂载点与“并非真正外置”的对照证据。 | 是，EF-HOOKS |
| `hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md` | sanitize 迁移代码考古；强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md` | 证明确是迁移残留而非有意让路，并列逐函数去向。 | 是，EF-HOOKS |
| `hooks-subscription-migration/reports/260822-session-closeout.md` | beta-strip/header policy 会话终态；实施+变异，中强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/hooks-subscription-migration/reports/260822-session-closeout.md` | 与已迁 `260822-beta-flag-strip-implementation.md` 及其 reviews 构成完整处置链；不复制已迁原件。 | 是，EF-HOOKS |

### `lifecycle-reorg`（4）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `lifecycle-reorg/reports/260816-lifecycle-code-review.md` | lifecycle shutdown/listener 代码评审+mutation；强 | 无 direct；owner graceful-shutdown | canonical history | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260816-lifecycle-code-review.md` | 保存 signal rung、ownership 与多轮复评证据。 | 是，EF-LIFECYCLE |
| `lifecycle-reorg/reports/260816-lifecycle-reorg-review.md` | 模块搬迁/AST 等价评审；强 | 无 direct；owner graceful-shutdown | canonical history | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260816-lifecycle-reorg-review.md` | 记录 7 个 definition 等价、import graph 与 1208-test 回归。 | 是，EF-LIFECYCLE |
| `lifecycle-reorg/reports/260817-entry-switch-review.md` | production entry switch/headers timer 评审；强 | 无 direct；owner graceful-shutdown | canonical history | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260817-entry-switch-review.md` | 保存 wheel/CLI/config probes、两轮 major 与最终合并态。 | 是，EF-LIFECYCLE |
| `lifecycle-reorg/reports/260824-standalone-process-test-transient-failure.md` | pidfile standalone test 单次失败观测；open、弱到中 | 无 direct；owner graceful-shutdown | canonical history | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260824-standalone-process-test-transient-failure.md` | 虽未复现，但明确限定一次观测、测试名与下一步；不是可丢 scratch。 | 是，EF-LIFECYCLE |

### `pipeline-rewrite-parity`（5）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `pipeline-rewrite-parity/reports/260818-cache-control-translation.md` | cache-control 跨协议调查+真实 GHC probes；强 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-cache-control-translation.md` | 保存 block breakpoint 丢失、Responses 显式 breakpoint 与可行策略的实证。 | 是，EF-PARITY |
| `pipeline-rewrite-parity/reports/260818-ops-gap.md` | 两项目运维端点/部署面盘点；源码强 | 无 direct；owner bridge/server-layout | canonical history | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-ops-gap.md` | 是旧链/新链非推理接口缺口的时点矩阵。 | 是，EF-PARITY |
| `pipeline-rewrite-parity/reports/260818-retry-gap.md` | upstream 400/5xx/retry 恢复差距调查；代码+DB 强 | 无 direct；owner bridge/upstream | canonical history | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-retry-gap.md` | 证明 SDK exception 与 `PipelineError` 断链及 context-management 失败路径。 | 是，EF-PARITY |
| `pipeline-rewrite-parity/reports/260818-traffic-feature-gap.md` | 两项目流量/能力特性对照；源码调查，中强 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260818-traffic-feature-gap.md` | 与其它 parity 报告共同界定哪些差异可采纳或不适用。 | 是，EF-PARITY |
| `pipeline-rewrite-parity/reports/260819-copilot-api-js-ir-architecture.md` | 参考项目 IR/translation architecture 调查；源码强 | 无 direct；owner bridge | canonical history | `.dev/docs/anthropic-responses-bridge/history/pipeline-rewrite-parity/reports/260819-copilot-api-js-ir-architecture.md` | 保存 semantic IR、loss tracking 与 converter 边界的参考事实。 | 是，EF-PARITY |

### `sync-refs`（13）

本组保留为一次性外部项目研究 history；两份已迁 `260822-round2-disposition.md` 与 `260822-vscode-copilot-chat-reasoning-values.md` 不在 residual 分母，也不复制到本子目录。

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `sync-refs/sxwxs-ghc-api/260821-answer-loss-persistence.md` | translation loss storage 设计处置；源码事实中强 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-answer-loss-persistence.md` | 记录明细归 JSONL、聚合归 metrics 而非新 SQLite 的落地理由。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-design-thinking-effort-wiring.md` | thinking→reasoning.effort 方案；源码/cassette 强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-design-thinking-effort-wiring.md` | 保存 `ReasoningIntent`、capability input 与仍需裁决的阈值边界。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-ghc-api-lessons-for-us.md` | 五调查+两核查综合裁断；强，版本限定 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-ghc-api-lessons-for-us.md` | 是 EF-SYNC 总索引与采纳/不适用结论，必须与底稿共址。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-inventory-our-capabilities.md` | 当前生产入口全能力面盘点；源码强 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-inventory-our-capabilities.md` | 提供两链路、协议、translation、reasoning 的我方对照基线。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-probe-upstream-sanitize-rules.md` | 54 次真实上游 probe；直接观测强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-probe-upstream-sanitize-rules.md` | 保存 empty tool description、attribution 与 count_tokens 接受度实证。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-review-losses-attribution.md` | losses/attribution 实现评审+mutation；强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-review-losses-attribution.md` | 保存 regex 误伤、scope、immutability、count-token 漏记与 partial loss findings。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-round-disposition.md` | 六任务实施/评审/待裁决处置；中强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-round-disposition.md` | 连接提交、真实 probe、评审采纳与未决项，是本轮终态账。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-core-translation.md` | 外部 core translation/SSE 全量调查；源码+probe 强 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-core-translation.md` | 保存字段、SSE、ID codec、loss report 等细粒度底稿。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-observability.md` | 外部 history/stats/cache 调查；源码强 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-observability.md` | 记录 JSONL sidecar、RequestCache 与 token reporter 的适用限制。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-periphery.md` | 外部 auth/profile/ACP/deploy 调查；源码强 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-periphery.md` | 补齐综合报告的外围能力底稿。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-reliability.md` | 外部 retry/keepalive/timeout/token 调查；源码强 | 无 direct；owner request-shape/upstream | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-reliability.md` | 补齐恢复与超时对照，和 core/observability/periphery 不可拆。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-verify-ghc-api-claims.md` | 外部转述 49 条交叉核验；强 | 无 direct；owner request-shape | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-verify-ghc-api-claims.md` | 39 忠实/7 过概括/3 失真的校正是综合报告可信度基础。 | 是，EF-SYNC |
| `sync-refs/sxwxs-ghc-api/260821-verify-our-side-claims.md` | 我方能力主张交叉核验；强 | 无 direct；owner request-shape/bridge | canonical history | `.dev/docs/anthropic-direct-request-shape/history/sync-refs/sxwxs-ghc-api/260821-verify-our-side-claims.md` | 修正我方盘点的过时/错误主张，与另一核查构成异源双证。 | 是，EF-SYNC |

### `test-infrastructure`（3）

| source | 性质 / 事实强度 | current consumer | disposition | 精确 destination | 理由 | 是否立即可动 |
|---|---|---|---|---|---|---|
| `test-infrastructure/reports/260818-vcrpy-poc.md` | AsyncOpenAI SSE record/replay PoC；直接实验强 | `tests/int/recorded/cassettes.py:3` | canonical history | `.dev/docs/server-layout/history/test-infrastructure/reports/260818-vcrpy-poc.md` | current cassette 实现明确依赖“vcrpy 合并 chunks”的否定证据；须与代码注释改链原子完成。 | 是，EF-TEST+改链 |
| `test-infrastructure/reports/260820-test-hygiene-two-defects.md` | 测试模块污染/断言过宽诊断；源码+probe 强 | 无 direct；test owner `server-layout` | canonical history | `.dev/docs/server-layout/history/test-infrastructure/reports/260820-test-hygiene-two-defects.md` | 保存两类测试卫生失败机制，非当前绿灯 authority。 | 是，EF-TEST |
| `test-infrastructure/reports/260820-unit-smoke-combined-hang.md` | unit+smoke 合跑 hang 调查；直接执行强 | 无 direct；test owner `server-layout` | canonical history | `.dev/docs/server-layout/history/test-infrastructure/reports/260820-unit-smoke-combined-hang.md` | 记录组合顺序/资源状态导致 hang 的证据，和 hygiene 报告互补。 | 是，EF-TEST |

## 按 retained target topic 汇总

| target topic | 迁移数 | families / 内容 |
|---|---:|---|
| `server-layout` | 12 | EF-ARCH 9 + EF-TEST 3。 |
| `tui` | 3 | EF-2604-TUI：旧总设计、telemetry/TUI 设计、library selections。 |
| `token-counting` | 6 | 旧 tokenization 与 hooks-tokenization oracle 2、旧 count-tokens 3、早期 Hooks acceptance 1。 |
| `ghe-device-flow` | 4 | Copilot token identity review/audit/verification family。 |
| `dotdev-repository-repair` | 84 | EF-DOCS-TMP 25 + EF-DOC-RESTRUCTURE 36 + EF-GIT 23。 |
| `anthropic-responses-bridge` | 33 | early Phase 3/Phase 0–8 15 + legacy History bridge 13 + EF-PARITY 5。 |
| `delivery-keepalive` | 7 | EF-EMPTY residual 7；已迁 synthetic-start key report不计本分母。 |
| `upstream/retry-and-continuation` | 13 | EF-HISTORY-FORENSICS：proposal 1 + reports 12。 |
| `anthropic-direct-request-shape` | 17 | EF-HOOKS 4 + EF-SYNC 13。 |
| `graceful-shutdown` | 4 | EF-LIFECYCLE。 |
| **迁移合计** | **183** | 与逐行 canonical-history disposition 一致。 |

## 可删除清单（36）

### `archived-2604-rewrite`（33）

`260403-docs-review-01-claude.md`、`BACKLOG.md`、`README.md`、`ROADMAP.md`、`approval-system.md`、`authentication.md`、`config-system.md`、`data-models.md`、`feature-negotiation.md`、`header-forwarding.md`、`lib-survey/260715-selections-review-01-claude.md`、`lib-survey/HANDOVER.md`、`lib-survey/_briefing.md`、`lib-survey/domain1-llm-sdk.md`、`lib-survey/domain2-reliability.md`、`lib-survey/domain3-streaming-sse-ws.md`、`lib-survey/domain4-storage-config.md`、`lib-survey/domain5-observability.md`、`lib-survey/domain6-hot-path-foundations.md`、`model-resolution.md`、`multi-protocol.md`、`plan/260715-implementation-plan-review-01-claude.md`、`plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md`、`plan/HOOKS_TOKENIZATION_KICKOFF.md`、`plan/IMPLEMENTATION_HANDOVER.md`、`plan/IMPLEMENTATION_PLAN.md`、`plan/PHASE_0_KICKOFF.md`、`project-structure.md`、`request-pipeline.md`、`sanitize-pipeline.md`、`shutdown.md`、`streaming.md`、`thinking-pipeline.md`。

逐项理由见 ledger：它们分别是已被 current retained Spec/source 明确蒸馏的旧目标设计、已完成且禁止重放的 Plan/Kick-off、结论已进唯一 `SELECTIONS.md` 的调研底稿，或已被后续实现/owner 取代且无独立观测的说明；不是因“时点报告”这一泛称而删除。

### 其它（3）

- `early-verification/README.md`：三组原件迁入各自 retained history 后，导航内容由目标 history index 接管，无独立证据。
- `history/decisions.md`：§5/§6 已有两个 canonical extracts，§1～§4 被 §5 重定；迁移整份会复制同一裁决。
- `history/spec.md`：约六成合同失去前提，剩余有效项已进入 upstream current status/deferred 与 canonical extracts；保留会形成第二规范。

## 最终结算、未确定项与执行门

| disposition | 数量 |
|---|---:|
| canonical history | 183 |
| 删除 | 36 |
| needs-user-decision | 0 |
| **总计** | **219** |

**未确定项**：0。没有遇到真正的归属/语义分叉需要用户裁决；跨主题材料均以唯一 current consumer、现有 successor 或完整 evidence chain 选择一个 canonical owner，其他主题只链接，不复制。

**实施顺序**：

1. 先创建各 destination family 子目录/history index；不先删 source。
2. EF-2604-TUI、EF-2604-TOKEN、EF-TEST 与所有原件内部相对链接，在同一变更中移动和改链；前批 12 份 canonical original 只链接、不复制。
3. 每个 family 核 source hash→destination hash、source absent、destination present；再做候选 basename/path scan。通用 basename 以完整 family path 判唯一，不能用全仓 basename 唯一误杀合法的 `README.md`/`spec.md`。
4. 36 个删除项逐项按本 ledger 复核；先确认其蒸馏/唯一 evidence destination 已在位，再删除。
5. 15 个候选目录均实际清空后才删除空目录；随后重跑 retained current/living Markdown、`src/`、`tests/`、`pyproject.toml` 的候选路径/unique basename 与所有新增 Markdown links 解析。

## 搜索面与边界

- 全文/必要上下文已覆盖 219 个 regular files；对 15 个目录逐项枚举，没有按 extension 漏掉 2 个 `.sh`、8 个 `.py` 与 10 个 `.txt` 批次表（其余 199 个为 `.md`）。
- current consumer 扫描覆盖 retained current/living Markdown 安全超集、`src/**/*.py`、`tests/**/*.py`、`pyproject.toml`、根 README/CLAUDE；repair control-plane、reports/history/archive 内的旧路径不反算为 current consumer。
- 已检查 final readiness review 所列 12 个前批 moved originals；它们的 exact basenames 不在 219 residual source set。`README.md` 等通用同名仅表示不同文档，推荐 family destination 不与现有 path 冲突。
- 未执行移动、删除、改链、测试、`git add`、commit、push 或 re-root；本任务是最终处置账，不是实施授权。
