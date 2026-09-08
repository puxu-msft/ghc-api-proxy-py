# 2026-09-08 dotdev root README refresh（PRR-05）

## 范围

本次只重写 `.dev/README.md`，并新增本报告。未修改其他文件，也未移动或删除任何内容；没有执行 `git add`、commit 或 push。

## 判据与输入

已读取 repository repair 的 current execution entry、其 final ledger refresh 与 pre-reroot/final-readiness review。以 repair README 为结构修复的 current owner，并以各 retained topic 的 living docs 保留产品状态的单一权威边界。

## 刷新结果

- README 现为 dotdev re-root 后分支根入口：`docs/`、`exp/`、`human-controlled-docs-candidates/`、`tools/` 和适用的 `verification/` 是同级根内容；主工作树以 `.dev/` worktree 挂载该根树。
- 删除了旧的“远端只有 `.dev/` 前缀”同步模型及其根树推送限制。旧嵌套 `.dev/.dev/` 仅保留为迁移前历史/provenance，不再作为当前操作模型。
- 主题 inventory 仅覆盖 current retained topics 与 `tmp` 机制：已退役的 15 个候选不再列入；新增 `interaction-context`，并指向其 living Spec。
- `httpx2-migration`、`systemd-runtime`、`reasoning-carrier` 和 `timeout-408` 的条目均链接到各自 living docs，且只陈述其当前文档支持的状态边界；没有复活“main 未集成/source unreachable”或“timeout 尚未装位”的历史快照。
- README 明确链接 repository repair README，供目录归档、候选退役、`tmp/` disposition、checkpoint 与 re-root/worktree 结构动作使用。

## 验证

- 本地 Markdown links：README 共 7 个本地链接，逐个解析，`missing=0`。
- README trailing whitespace：`0`。
- 对 README 的 `git diff --check`：通过。

本报告不宣称 re-root/worktree 挂载已经执行；其剩余结构性步骤与验收仍由 repository repair README 定义。
