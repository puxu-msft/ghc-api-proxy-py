# 2026-09-08 systemd-runtime 退役路径清理报告

## 范围与结论

- **范围**：仅处理 `.dev/docs/systemd-runtime/plan.md` 中 MSR-05 指出的旧 `archived-2604-rewrite` 路径；不迁移、删除或改写旧主题文件。
- **总体结论**：已完成。旧设计仍作为负面历史例子保留，但不再以具体路径或可解析 target 出现在当前 Plan 中。
- **blocker 数**：0。

## 修改

将 S3「基线差距与已完成处置」中的具体路径引用改为无 target 的历史描述：

> 旧版 shutdown 设计曾描述 `60s` graceful wait、`120s` abort wait 与四阶段设计，但该历史设计文档不能证明生产已接线。

修改保留了 MSR-05 要求的负面例子论点：旧设计的描述不能证明生产已接线；同时去掉了会在旧主题退役后变成陈旧路径的旧 archived topic shutdown target。没有把旧文件迁入 `systemd-runtime`，也没有将其提升为 current evidence。

## 核查

- 复读 `dotdev-repository-repair/README.md`、`subtopics/260908-shutdown-systemd-consolidation.md` 与 `reports/260908-merged-state-review.md`，确认 systemd-runtime 仍是保留主题，S5 仍 blocked，且 MSR-05 只要求清理负面历史 code span。
- 核对 `systemd-runtime/plan.md` 修改位置，确认该段仍保留 `60s`／`120s`／四阶段设计及“不能证明生产已接线”的论点。
- 在 `systemd-runtime/plan.md` 内检索旧 archived topic 的 shutdown target，确认不再存在该具体 target。
- 检查改动范围仅限本报告和 `plan.md`；未修改其它路径，未移动／删除文件，未执行 `git add`、commit 或 push。

本次仅为 Markdown 文档清理，未运行源码测试。
