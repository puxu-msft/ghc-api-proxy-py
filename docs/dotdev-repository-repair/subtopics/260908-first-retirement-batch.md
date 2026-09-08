# 第一批主题退役清单（仅准备，不执行删除）

**范围**：本清单只覆盖 `architecture-audit`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`early-verification`、`empty-text-block`、`git-housekeeping`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure` 这 12 个目录；不包含仍有门槛未闭合的 `archived-2604-rewrite`、`documentation-restructure`、`history`、`httpx2-migration`，也不包含必须保留的顶层 `tmp/` 和 `systemd-runtime`。本文件是后续逐项迁移、改链和删除的依据，**不是**移动、删除、`git add`、commit 或 push 授权。

**判据与当前结论**：以 `dotdev-repository-repair/README.md` 的“先迁证据、改入站链接、复扫、再删除”顺序为门槛，以 `reports/260908-merged-state-review.md` 的最终 12/16 可退役结论为交叉复核，并以 `subtopics/260908-tmp-final-disposition.md` 确认本轮顶层 `tmp/` 的逐份最终去向。本次重新枚举了 12 个目录的 regular files，并在排除候选自身、顶层 `tmp/`、repair control-plane、`reports/`、`history/` 与 `archive-*` 后，对 retained topics 的 current/living Markdown 作目录路径扫描；12 个候选均为 **0 个 retained-current candidate-directory path hit**。

**总体 verdict**：12 个目录均已满足“可纳入第一退役批次”的主题级门槛；但它们目前均非空，且 README 要求先完成实际证据归档/处置、`tmp` 迁移及最后复扫。因此“可删除”均为**条件是**，不是当前立刻可删。目录内保留的“用户裁决／deferred／current”等字样若存在于 point-in-time report，只是历史取证，不能被重新当作该目录仍承载的 living authority。

**blocker 数**：0。

## 逐项删除释放表

| 目录 | 文件数 | 剩余内容性质 | live incoming scan 结论 | 是否可删除 | 必须等待的全局前置 |
|---|---:|---|---|---|---|
| `architecture-audit` | 9 | 全部位于 `reports/`；2026-08-14 七轴代码/测试结构审计及综合/对账，均为固定时点评审。 | 0；merged-state review 同样判为“仅 9 份时点 reports；无 living 入站”。 | **条件是**：候选目录中的 9 份原件完成 history 归档或逐份删除处置、目录清空后可删。 | 完成候选原件处置；完成 77 份 `tmp` 的实际迁移/处置；对 retained living 文档重跑路径与 link 复扫。 |
| `copilot-token-identity` | 4 | 全部位于 `reports/`；2026-08-07 token exchange identity 的审计、两轮评审和验收。 | 0；唯一同名命中是 `archive/260807-copilot-token-identity@...` immutable Git ref，不是文档目录。 | **条件是**：4 份时点原件处置并清空目录后可删。 | 同上。 |
| `count-tokens` | 3 | 全部位于 `reports/`；端点评审与异构计数测量。没有根级 living 文档。报告内的建议/历史裁决不构成 current Spec。 | 0；原 `tui/deferred.md` 承重报告已迁到 `token-counting/history/` 并改链。 | **条件是**：3 份 residual reports 处置并清空目录后可删。 | 完成候选原件处置；完成 `tmp` 实际迁移；最后复扫 `token-counting`、`tui` 及 retained living links。 |
| `docs-tmp-migration` | 25 | 根级 `README.md`、`BRIEF.md`、10 份批次表和 13 份分类/迁移评审；均记录 2026-08-21 已完成迁移过程和已废止旧目录规则，不是当前迁移控制面。 | 0；tmp ledger 只记录其 README 对一份 identity checkpoint 的退役候选提名，且该 tmp 原件的最终落点是 `anthropic-responses-bridge/history/`。 | **条件是**：25 份过程记录处置并清空目录后可删。 | 完成实际 `tmp` 迁移；候选原件处置；最后复扫。不得因删除本目录重建旧 `docs/tmp/`/`docs/agents/` 机制。 |
| `early-verification` | 17 | 根级入口 README 加 16 份 `archive-260715/16/17` 验收原件、runner 与 probes；明确是历史快照，不是当前验证入口。 | 0；当前验证权威为根 `CLAUDE.md`、主仓 `tests/` 和各 retained topic living Spec。 | **条件是**：archive bundle 获得明确 history 保留去向或逐份删除处置、目录清空后可删；不得把旧 runner 修成“当前验证”。 | 候选原件处置；完成 `tmp` 实际迁移；最后复扫。 |
| `empty-text-block` | 7 | 全部位于 `reports/`；空 text block 的根因、上游取证、修复/探针与独立评审。报告中的“仍待裁决”仅是 2026-08 时点记录；现行合同由 `anthropic-direct-request-shape` 承接。 | 0；原 `delivery-keepalive/spec.md` 的承重证据已迁至 `delivery-keepalive/history/`，旧 source target 不再存在。 | **条件是**：7 份 residual reports 处置并清空目录后可删。 | 完成候选原件处置；完成 `tmp` 实际迁移；最后复扫 `delivery-keepalive` 与 request-shape 的 links。 |
| `git-housekeeping` | 23 | 全部位于 `reports/`；worktree/archive 清理、dotdev import/merge 与 merge-resolution 的过程审计、方案、复评和 closeout。即使报告讨论 pending worktree 或 deferred，它们不是本目录的 current carrier。 | 0；`direct-passthrough/spec.md` 曾消费的两份 provenance 已迁到 `dotdev-repository-repair/history/` 并改链。 | **条件是**：23 份过程原件处置并清空目录后可删。 | 完成候选原件处置；完成 `tmp` 实际迁移；最后复扫 `direct-passthrough` 与 repository-repair links。 |
| `hooks-subscription-migration` | 4 | 全部位于 `reports/`；sanitize/hook 迁移、外置改写面、参考架构与 beta-strip closeout。历史报告含用户裁决和未决问题，但 current subscription/request-shape owner 已在 retained topics。 | 0；原 `hosted-web-search/status.md` beta-strip 实施证据已迁至 `anthropic-direct-request-shape/history/` 并改链。 | **条件是**：4 份 residual reports 处置并清空目录后可删。 | 完成候选原件处置；完成 `tmp` 实际迁移；最后复扫 `hosted-web-search` 和 request-shape links。 |
| `lifecycle-reorg` | 4 | 全部位于 `reports/`；生命周期模块重组、入口切换及单次 transient test failure 的时点评审。当前实现 owner 是 `src/app/lifecycle/` 对应的 retained documentation。 | 0；没有 retained current consumer。 | **条件是**：4 份 residual reports 处置并清空目录后可删。 | 候选原件处置；完成 `tmp` 实际迁移；最后复扫。 |
| `pipeline-rewrite-parity` | 5 | 全部位于 `reports/`；与前身项目的 cache-control、ops、retry、traffic feature、IR architecture 对照调研，不含活合同。 | 0；其它报告中的命中是 historical references，不是 live dependency。 | **条件是**：5 份调研原件处置并清空目录后可删。 | 候选原件处置；完成 `tmp` 实际迁移；最后复扫。 |
| `sync-refs` | 13 | `sxwxs-ghc-api/` 下 13 份一次性外部实现调研、事实核验与轮次处置；其中的用户待裁决是历史调研结论，不能替代 retained topic 的 current deferred。 | 0；原 5 个 living 引用行所需的 2 个承重原件已迁至 `anthropic-direct-request-shape/history/`，消费者已改为该 canonical history。 | **条件是**：13 份 residual research reports 处置并清空目录后可删。 | 完成候选原件处置；完成 `tmp` 实际迁移；最后复扫 `anthropic-direct-request-shape` 与 `direct-passthrough` links。 |
| `test-infrastructure` | 3 | 全部位于 `reports/`；vcrpy PoC、unit/smoke hang 与 test hygiene 缺陷的点时记录，不能作为当前 test infrastructure 或绿灯的 authority。 | 0；没有 retained current consumer。 | **条件是**：3 份时点原件处置并清空目录后可删。 | 候选原件处置；完成 `tmp` 实际迁移；最后复扫。 |

## 五个已迁承重证据、源目录仍在的专项核对

| 目录 | 已关闭的旧承重引用 | 源目录中是否仍有 living Spec/deferred/用户裁决 | tmp 最终 ledger 对目录的影响 | 释放判断 |
|---|---|---|---|---|
| `count-tokens` | `tui/deferred.md:37` 的共享 pipeline 证据已改到 `token-counting/history/260820-review-count-tokens-shared-pipeline.md`。 | 否。余下仅 3 份 reports；文本中的建议或测量结论不是 current owner。 | ledger 将两份 count_tokens tmp 原件送入 `token-counting/history/`，不送回本目录；其中只把旧 `count-tokens` report 当 historical 提名。 | 不受 tmp 内容归属阻塞；仍等实际 tmp 迁移和最后复扫。 |
| `empty-text-block` | `delivery-keepalive/spec.md:5,66` 的报告已迁至 `delivery-keepalive/history/260820-review-synthetic-start-fix.md`；旧路径入站为 0。 | 否。余下 7 份都是历史取证/修复报告；其中历史“待裁决”不再是目录内 active deferred。 | ledger 未向此目录分配任何顶层 tmp 原件，也未把它作为 retained owner。 | 不受 tmp 分配阻塞；仍等全局实际迁移和最后复扫。 |
| `git-housekeeping` | `direct-passthrough/spec.md:871` 的两份 provenance 已迁至 `dotdev-repository-repair/history/` 并改链。 | 否。余下 23 份是仓库操作过程记录；旧工作树清理计划不能作为当前执行授权。 | ledger 未向本目录分配顶层 tmp 原件；涉及 Git/document governance 的材料改投 `dotdev-repository-repair/history/`。 | 不受 tmp 分配阻塞；仍等全局实际迁移和最后复扫。 |
| `hooks-subscription-migration` | `hosted-web-search/status.md:83` 的 beta-strip 实施证据已迁至 `anthropic-direct-request-shape/history/` 并改链。 | 否。余下 4 份虽逐字记录旧用户裁决/未决问题，但没有根级 Spec/deferred/current status，且 retained owner 已接管。 | ledger 未向本目录分配顶层 tmp 原件；beta-strip 关联 tmp 原件均指定给 `anthropic-direct-request-shape/history/`。 | 不受 tmp 分配阻塞；仍等全局实际迁移和最后复扫。 |
| `sync-refs` | 5 个 living 引用行消费的两个原件已迁到 `anthropic-direct-request-shape/history/`，且 cross-topic consumers 已改链。 | 否。余下 13 份是外部实现的时点 research；其中“待用户裁决”是调研所列问题，current deferred 必须由 retained topic 维护。 | ledger 的 `260821-probe-history-error-frames.md` 曾只被本目录以旧 tmp 路径提名；最终改投 `upstream/retry-and-continuation/history/`，不会把本目录变成 owner。 | tmp 迁移实际执行后会消除该目录自己的历史 tmp 指向；仍须最后复扫。 |

## 执行时的不可省略释放门

1. 对每个表行先逐份处理该候选目录的 residual 原件：迁至唯一 retained topic 的 `history/`，或另有逐项、可追溯的删除处置；不得因“无 live incoming”直接丢弃尚未处置的证据。
2. 实施 `tmp-final-disposition` 的 77/77 项，而非只依赖其 ledger verdict：72 份迁至表列 canonical history、4 份按 ledger 删除、`260907-interaction-context-design.md` 先提炼 retained living contract。涉及 current consumer 的改链必须与移动原子完成。
3. 在同一待删除状态重新扫描 retained current/living Markdown：候选目录路径、候选文件 basename 和新增 canonical history Markdown links 都必须无未解释 consumer，且所有新 links 可解析。特别复查表中五个专项目录的 consumer。
4. 对每个 moved original 核对 source absent、destination present、hash unchanged 与同 basename 唯一性；确认候选目录已真正为空后，才将对应一行从“条件是”提升为实际删除许可。
5. 完成上述 12 行后才可删除空目录；删除与 `.dev` 提交、dotdev re-root、git worktree 挂载均是后续独立操作，不包含在本清单授权中。

## 搜索面与边界

本次读取 repair README、merged-state review、tmp final disposition ledger 和 retirement reference map；枚举了 12 个候选目录的 117 个 regular files，并检查目录形状。对 retained topics 的 current/living 安全超集重跑 candidate-directory textual path scan，12/12 为零；该口径刻意不把候选自身、`tmp`、repair control-plane、`reports/`、`history/`、`archive-*` 内的历史快照引用误判为 incoming consumer。没有移动、删除、编辑候选内容，亦未运行产品测试：本任务只判断文档退役的依赖与释放门。
