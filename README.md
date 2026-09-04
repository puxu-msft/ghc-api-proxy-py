# `.dev` —— 开发过程状态

本目录存放开发团队（用户 + 各会话 + 各 agent）的**工作产物、工作记录与工作证据**：开发文档、分析报告、归档的实验证据。

与项目自身 `docs/` 的区别：`docs/` 是面向使用者的最终文档；这里是**给做这件事的人看的**。

## 与主仓库及远端分支的关系

`.dev/` 是主工作树里的协作编辑面，在主仓库的 `.gitignore` 中，**不进入 `main`**。用户于 2026-09-04 选择专用 orphan 分支 `origin/dotdev` 作为开发记录的远端持久源；该裁决取代了本文件此前所写的“`.dev/` 以嵌套独立仓库作为最终存储”模型。远端分支的规范树只含 `.dev/`，不得把它 merge 或 squash 进 `main`。

本机当前 `.dev/.git` 仍保存迁移前的本地独立历史。本地历史可以作为合并来源，但**不能把其仓库根直接推到 `origin/dotdev`**：那会把 `docs/` 写到远端根，而不是规范的 `.dev/docs/`。同步时应在专用 worktree／临时 clone 中以远端 tip 为第一父提交，把本地内容映射到 `.dev/` 前缀，并保留本地历史为第二父提交。

> **注意一个已经踩过的坑**：`git mv` 会把目标路径登记进主仓索引，而 `.gitignore` 对**已跟踪**的路径无效。把主仓库里已跟踪的文件搬进 active copy，用 `mv` + `git rm --cached <旧路径>`，不要用 `git mv`；否则文件会被改名后继续留在 `main` 的版本控制里，恰好是搬进来要避免的事。

## 提交、同步与推送

裁决于 2026-08-20，并由 2026-09-04 的远端存储裁决补全：

- **本地记录：总是可以主动持久化，不必先问。** 这里存的是工作记录，它最直接的失败模式是丢失；允许短暂的不一致状态，提交边界只按语义划分。
- **同步：只带当前任务拥有的精确路径。** 不 bulk-copy 整个 `.dev/`，因为其它会话可能正在写不相关报告或 living docs。远端与 active copy 不同时，先判断哪一侧是仍在进行的工作；不得让较旧快照覆盖新 WIP，也不得让未经评审的 active copy 静默替换 reviewed remote snapshot。
- **推送：`[hard]` 除非用户当次明确指示，不推送。** `origin/dotdev` 是最后一次已发布的持久快照；只存在于本机的提交不得描述为已经在远端。本轮用户明确要求合并远端时，仍须先获取并比较远端 tip，禁止 force push 覆盖并行提交。

## 恢复

从 `origin/dotdev` 恢复时，在专用 worktree 中检出该 orphan 分支，再把需要的 `.dev/` 精确路径还原到主工作树的 ignored active copy；不要把共享主工作树从 `main` 切走，也不要把整个远端树无选择地覆盖到正在被同伴编辑的 `.dev/`。

完整的同步边界、首次远端建立与已发生的失败尝试见 [`docs/upstream/retry-and-continuation/status.md`](docs/upstream/retry-and-continuation/status.md) 的 HTTP 499 状态段及其 `http-499-retry.md`、`review-disposition.md`。

## 布局

```
.dev/
├── docs/
│   ├── <topic>/              一个话题一个目录
│   │   ├── README.md         入口：本目录有什么、怎么读
│   │   ├── spec.md           规范。行为契约，活文档
│   │   ├── plan.md           实施计划。活文档，随代码与发现同步
│   │   ├── deferred.md       未决项：想到了但没做的事，及不做的理由
│   │   ├── reports/          本话题的 agent 报告原件，逐字保留
│   │   └── archive-<subtopic>/   历史：已完成工作的知识沉淀
│   │       ├── README.md     重写过的知识文档
│   │       └── reports/      当时的 agent 报告原件，逐字保留
│   └── tmp/                  未分类：判不进任何话题的报告，以及话题尚不明朗时的新报告
└── exp/
    └── <name>/               实验脚本与探针，保留可跑
```

按需增加的文件（用户既有约定里列举过，不必预先建空文件）：`decision.md`（用户同意的设计与技术选型）、`decision-pending.md`（待用户裁决的事项）、`status.md`（当前实现状态与已知问题）。

## 几条约定

- **活文档与历史文档分开放。** `spec.md` / `deferred.md` 在话题根目录，因为它们描述的契约与待办**仍然生效**；`archive-*/` 是已完成工作的记录。一份文档搬进 `archive-` 就等于宣布它不再是当前状态。
- **归档要重写，不要堆。** agent 报告是过程产物（严重度计数、验证日志、逐条核验），直接堆着等于没归档。重写成按「做了什么、为什么这样定、踩了什么坑」组织的知识文档，并**保留原件在 `reports/`**——重写承载不了行号与探针输出，而那些有取证价值。
- **写下被否定的方案和否定的理由。** 这是档案里最难重建的部分，也是下一个人最容易重新踩一遍的地方。
- **归档文档里的路径与行号是快照**，会过时；重写文档里要说明这一点，不要让读者以为它们仍然有效。
- **搬动文档时检查引用。** 代码 docstring、测试注释、别的文档都可能指向它。断链比不搬更糟。

## 已有话题

`docs/` 下每个目录是一个话题。下表只解释不能从目录名读出来的那些；其余顾名思义。

| 目录 | 内容 |
|---|---|
| `docs/anthropic-responses-bridge/` | 主产品链路：Anthropic Messages 入站 → OpenAI Responses 上游。本仓库最大的话题 |
| `docs/documentation-restructure/` | 文档重组与迁移本身的计划、审计与评审 |
| `docs/git-housekeeping/` | archive ref、分支与 worktree 的清理审计 |
| `docs/pipeline-rewrite-parity/` | 新请求管道与 `copilot-api-js` 参考实现之间的能力差距分析 |
| `docs/architecture-audit/` | 2026-08-14 那一轮七轴线独立体检（依赖图、重复实现、模块边界、类型泄漏等）及其综合 |
| `docs/graceful-shutdown/` | 关闭信号到进程退出之间的一切；目前只有 `client-side/`，监听器那一半还散在 `systemd-*` 与 `deployment-systemd` 下 |
| `docs/project-review-principles-skill/` | `project-review-principles` skill 本身的事实核查与形态评审 |
| `docs/reasoning-carrier/` | 从另一 source clone 导入的 reasoning carrier v2 规格与评审；原 source ref／worktree 当前不可达，不能视作 current implementation |
| `docs/timeout-408/` | 从另一 source clone 导入的客户端预响应断连规格、运行态取证和评审；当前 checkout 尚未装位实现 |
| `docs/xingchen/` | 从另一 source clone 导入的 Xingchen provider 规格与评审；当前 checkout 尚未装位实现 |
| `docs/early-verification/` | 2026-07-15～17 的 Phase 0～8、Hooks 与 Tokenization 验收原件；只作历史快照，当前验证权威仍是项目根 `CLAUDE.md` 与主仓 `tests/` |
| `docs/archived-2604-rewrite/` | 早期 peer 写的 `copilot-api-js` 学习笔记，用户 2026-08-20 裁定整体过期，**仅供参考、无权威地位** |
| `docs/tmp/` | 未分类：判不进任何话题的报告，以及话题尚不明朗时的新报告 |
| `docs/docs-tmp-migration/` | 2026-08-21 那次搬迁自身的记录：逐文件分类表、判据与批次报告 |
| `exp/<name>/` | 对应话题的实验脚本与探针，保留可跑 |

## 主仓库 `docs/` 现在剩什么

只剩 `docs/.human-controlled/`——用户亲笔的文档。`docs/tmp/` 与 `docs/agents/` 已于 2026-08-21 整体搬入本目录，**不要再在主仓库重建它们**。这次搬了 417 份报告与 8 个话题目录，逐文件的分类结果与判据在 `docs/docs-tmp-migration/`。
