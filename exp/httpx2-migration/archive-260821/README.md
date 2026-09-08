# 2026-08-21 共享索引 staging 助手（历史原件）

`stage_migration.py` 只服务 httpx→httpx2 迁移当时的一次共享工作树形态：五个 Python 文件同时含机械改名与同伴未提交编辑，脚本从当时 HEAD 重建 rename-only blob，并把结果写入操作者显式提供的 private index。

它不是迁移逻辑、不是当前提交工具，也没有 living consumer。原脚本的 Usage 宣称支持 `--check`，但 argparse 只有 `--write`；默认无参数实际承担当时的检查模式。这处不一致连同硬编码仓库路径、private-index 前提和当时的文件分类原样保留，因为修复它会把历史一次性助手伪装成可复用工具。

不得对当前工作树运行其 `--write` 路径。当前共享工作树提交纪律由用户级 `my-skills:coordinating-a-shared-git-worktree` 承担；脚本的历史存在不授权把 private index 当作一般隔离手段。文件级归类与否决路线见 [`../../../docs/git-housekeeping/reports/260904-dotdev-dirty-inventory.md`](../../../docs/git-housekeeping/reports/260904-dotdev-dirty-inventory.md)。