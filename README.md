# dotdev 开发文档工作区

这里保存开发过程中的 living docs、决策边界、实验、报告和可复核证据。它不是产品面向使用者的说明书：产品行为由各话题自己的 living `spec.md`、`status.md`、`plan.md` 或 `deferred.md` 定义。

本 README 是 dotdev re-root 后分支根目录的入口。在主工作树中，dotdev checkout 通过 Git worktree 挂载在 `.dev/`；因此从主工作树读取本文件时，`docs/`、`exp/` 等相对路径就是 dotdev 的分支根内容。

## 当前结构与结构修复

目标且验收后的 dotdev 根树如下：

```text
README.md
docs/                           话题的 living docs、history 与 reports
exp/                            可运行的实验和探针
human-controlled-docs-candidates/  需要用户控制流程处理的候选材料
tools/                          文档维护工具
verification/                   结构与文档验证资产（如适用）
```

共享主工作树的 `.dev/` 是上述根树的 worktree 挂载点，而不是另一层文档前缀。应在该 checkout 的根目录处理 dotdev 的版本控制和协作边界；按当前任务所有权选择精确路径，并在发布前比较 remote tip，避免覆盖并行 WIP。是否建立 checkpoint、执行 re-root/worktree 挂载及其验收顺序，由 [repository repair README](docs/dotdev-repository-repair/README.md) 作为唯一 current owner。

`docs/` 是当前活文档根；`exp/`、`human-controlled-docs-candidates/`、`tools/` 与它同级。旧的嵌套 `.dev/.dev/` 布局及其提交链仅是迁移前历史/provenance，不能作为新文件的落点、同步模型或当前目录结构的依据。

## 文档生命周期

- **living docs**：主题根目录的 `spec.md`、`status.md`、`plan.md`、`deferred.md`、`decision.md` 或 `decision-pending.md` 按各主题实际需要存在。先读入口和状态页，再以其中指定的文件为准。
- **history / archive**：已完成或点时材料的可追溯记录，不自动构成当前合同。归档时保留能解释“做了什么、为什么、否决了什么”的知识入口和需要复核的原件。
- **reports/**：评审、验收、调查与迁移的点时证据。报告里的路径、SHA、文件计数和结论只覆盖其声明的时间与范围。
- **`docs/tmp/`**：临时交换机制，不是可批量删除的垃圾桶。新材料在进入 history、living owner 或获明确处置前，仍须逐份判断归属。

目录移动或归档前，先检查现行 living docs 的入站引用；迁移前的报告和 history 中故意保留的旧路径属于 provenance，不应反推为 current dependency。

## 主题 inventory

下表只列当前保留的话题和机制；目录名已经足够表达的细节留在对应入口中。已完成退役的历史候选不在此 inventory 内。

| 目录 | 当前入口或职责 |
|---|---|
| `docs/anthropic-direct-request-shape/` | Anthropic direct request shape 的合同与评审处置 |
| `docs/anthropic-responses-bridge/` | Anthropic Messages 入站到 OpenAI Responses 上游的主链路 |
| `docs/auto-mode-classifier/` | 自动模式分类器的规格与状态 |
| `docs/cli-commands/` | CLI command 的设计、实现与评审 |
| `docs/client-leg-formats/` | 客户端侧格式兼容性与 deferred work |
| `docs/delivery-keepalive/` | delivery liveness、heartbeat 与 timeout 行为 |
| `docs/deployment-systemd/` | systemd 部署材料 |
| `docs/direct-buffered-chat-completions/` | direct buffered Chat Completions 的实现材料 |
| `docs/direct-passthrough/` | 直连 passthrough 的当前规格与计划 |
| `docs/dotdev-repository-repair/` | 文档归档、退役与 re-root 的结构修复 current owner |
| `docs/error-envelope/` | 错误 envelope 的合同和待办 |
| `docs/ghe-device-flow/` | GHE device-flow 行为与 deferred work |
| `docs/graceful-shutdown/` | 关闭、restart handover 与相关证据 |
| `docs/hosted-web-search/` | hosted web search 状态与兼容性材料 |
| `docs/httpx2-migration/` | [living Plan](docs/httpx2-migration/plan.md) 的 residual owner；步骤 4 prose audit、`httpx2`/`httpcore2` logger 筛噪及验证尚未闭合 |
| `docs/interaction-context/` | [current interaction contract](docs/interaction-context/spec.md)；原始设计/WIP 仅在 history 中保真保存 |
| `docs/multi-provider-routing/` | 多 provider routing 的规格、处置和 deferred work |
| `docs/project-review-principles-skill/` | project-review-principles skill 的项目内材料 |
| `docs/reasoning-carrier/` | [v2 implementation status](docs/reasoning-carrier/tracking.md) 与规格；main 集成是审计基线已核实的代码事实，`RC-TF-01` 仍待独立 test-discriminability 复验 |
| `docs/server-layout/` | server layout 的现行说明与决策 |
| `docs/service-cutover/` | 服务切换的计划和 readiness |
| `docs/systemd-rolling/` | systemd rolling 的独立 current owner |
| `docs/systemd-runtime/` | [living runtime Plan](docs/systemd-runtime/plan.md)；S3/S4 已进入 main，S5 仍需有独立 user manager 与 delegated cgroup v2 的可销毁环境完成真实 runtime smoke |
| `docs/timeout-408/` | [living status](docs/timeout-408/status.md)；response-preparation disconnect lifecycle 已在审计基线 main 装位，远端 408 根因及独立策略边界仍待证据 |
| `docs/token-counting/` | token accounting、provider observation 与迁移后的证据 |
| `docs/tui/` | TUI 合同、决策和 deferred work |
| `docs/upstream/` | 上游 retry、continuation 与相关失败语义 |
| `docs/xingchen/` | Xingchen provider 规格和状态 |
| `docs/tmp/` | 临时交换机制；当前没有把它当作一个产品主题 |

各主题的状态以自己的 living docs 为准。本表不以历史报告取代它们，也不把代码审计、未重跑的测试、部署状态或用户裁决混为同一种结论。

## 操作入口

1. 从本 README 定位话题后，先读该话题的 `README.md`（如有）和 living status/plan/spec。
2. 涉及目录归档、候选退役、`tmp/` disposition、dotdev checkpoint 或 re-root/worktree 时，先读 [repository repair README](docs/dotdev-repository-repair/README.md)；它区分已闭合的迁移与仅剩的结构性顺序。
3. 需要复核历史断言时，沿主题的 `history/` 和 `reports/` 取其点时范围，不将其自动升级为 current behavior。
4. 修改后验证受影响的本地 Markdown links；结构变更还应按 repair owner 指定的独立复扫范围验收。

## 同步与恢复

dotdev 是独立分支根树。通过其 checkout/worktree 进行提交、同步和恢复，保持分支根的 `docs/`、`exp/`、`human-controlled-docs-candidates/`、`tools/` 等目录结构。主工作树的 `.dev/` 挂载让开发者在不切换主工作树分支的前提下访问该根树。

发布、push、force 操作及可能覆盖其他会话工作树的恢复，必须取得当次明确授权并先比较目标与 remote 的当前状态。恢复时仅还原任务需要的精确路径，不以旧嵌套布局或过期快照覆盖仍在进行的工作。
