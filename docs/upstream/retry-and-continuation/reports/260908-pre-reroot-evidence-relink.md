# PRR-02/PRR-01 upstream evidence relink

- 日期：2026-09-08
- 范围：`upstream/retry-and-continuation/` 内的 `max_output_tokens` 证据目录与一个 `deferred.md` 墓碑链接；未修改生产代码、测试、配置或其他主题。

## 已完成的 relink

1. `evidence/probe-reasoning-item-control.py` 的 `EV` 已从已清空的顶层 `tmp/` 位置改为 canonical 的 `evidence/max-tokens-block-completeness/`。它读取的输入仍是该目录已有的 `scan_hits.txt`。
2. `README.md` 现在把 `scan_hits.txt`、`inc_table.txt` 和只读 probe 明确为该 canonical 目录的 current evidence；同一组调查报告和复现命令也已改用该目录。因此本主题内不再有已清空的旧顶层 `tmp/` 证据目录 consumer。
3. `decisions.md` §22 的 `22 之四` 链接已指向 `deferred.md` 的完整墓碑 heading。

## 验证清单

- 静态解析 probe 的 `EV` 赋值并只读取其 `scan_hits.txt` 输入；未导入或执行 probe，因此没有打开 history SQLite 库或发出任何外部操作。
- 确认 canonical evidence 目录、`scan_hits.txt` 与 `inc_table.txt` 均存在。
- 复扫本主题的已退休证据目录 basename，结果为零。
- 按 GitHub slugger 规则验证墓碑。它先删除标点（包括 `.`、`——`、全角圆括号），再把空格替换为 `-`；heading `22 之四. 一条状态断言在写下时就已经过期 —— 已移入教训文档（2026-08-27）` 的 fragment 为 `#22-之四-一条状态断言在写下时就已经过期--已移入教训文档2026-08-27`，与 `decisions.md` 链接一致。
- 对本轮允许范围运行 `git diff --check`。

## 未做事项

- 未运行探针本体、未访问 Copilot history 数据库、未发出网络请求。
- 未执行 `git add`、`commit` 或 `push`，也未修改授权目录之外的文件。
