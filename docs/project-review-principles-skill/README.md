# `project-review-principles` 复查记录

本目录保存项目定期复查 skill 的事实核查、形态评审与真实执行报告。模型实际加载的权威是主仓 `.claude/skills/project-review-principles/SKILL.md`；本目录不复制原则正文，也不以报告覆写 skill。

## 当前状态

2026-09-03 首次对五条原则做了完整真实复查。原报告、独立复审与处置账分别是：

- [`reports/260903-project-principles-backlog-review-gpt-opus.md`](reports/260903-project-principles-backlog-review-gpt-opus.md)
- [`reports/260903-project-principles-backlog-review-general-sonnet.md`](reports/260903-project-principles-backlog-review-general-sonnet.md)
- [`reports/260903-project-principles-backlog-review-disposition.md`](reports/260903-project-principles-backlog-review-disposition.md)

三条产品 finding 全部采纳，但报告通过不表示产品修复完成：native passthrough side facts 已进入 [`../direct-passthrough/plan.md`](../direct-passthrough/plan.md) §11.7 与 Spec §10；count-tokens 的共同 usage observation、三处越权承诺面，以及 skill 自己已经过期的状态／命令留在 [`deferred.md`](deferred.md)。

2026-08-20 的四份报告记录 skill 新条目成形时的事实与评审，其中 `260820-review-principles-entries.md` 原本误放在 graceful-shutdown 主题，2026-09-04 按评审对象归回本目录；报告正文保持点时原文。

## 阅读规则

- `reports/` 是定格执行与评审原件，旧 verdict、路径、行号和后附更正都不改写。
- `deferred.md` 只列当前仍未闭合的改动；某项进入其它主题的 living plan 后只保留链接，不在这里维护第二份状态。
- 修改 skill 会改变以后每次复查的模型指令，属于 B 级处置，必须由未卷入的跨模型 reviewer 复核；本次仅合并 `.dev`，没有顺带修改主仓 skill。