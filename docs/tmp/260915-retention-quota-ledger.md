# Capture/history retention quota 修复进度账本

## 任务列表

| ID | 状态 | 说明 |
| --- | --- | --- |
| scope-and-contract | done（2026-09-15T23:37:33Z） | 已核对：现行 raw contract 明确排除目录总量配额；History 明确不提供 public purge，且要求 controlled purge 留 tombstone。 |
| raw-capture-quota | WIP（2026-09-15T23:42:42Z） | 用户补充授权 `composition.py`、`compat.py` 与 current Spec；实现只追加安全 admission cap，不删除 evidence。 |
| history-retention | deferred（2026-09-15T23:42:42Z） | 用户明确要求不做 automatic purge/tombstone/compaction，也不改 archive/writer（其他 agent 正在占用）。 |
| focused-tests | WIP（2026-09-15T23:42:42Z） | 增加 RawCaptureStore total quota、启动盘点和 queued reservation 定向测试。 |
| verification | pending | 修改后运行 focused tests、Ruff、Pyright。 |
| final-report | done（2026-09-15T23:42:42Z） | 已更新原 report：RawCapture total admission cap 已实现、History automatic retention 明确 deferred、验证结果已记录。 |

## 附录：边界

- 仅触及用户白名单中的 capture/history/config/tests 文件，以及本账本和最终报告。
- 不删除仍由 index 引用的 evidence；pinned/archive 的语义以现有合同为准。
- 不在共享工作树执行破坏性 Git 操作或全树 Git 写操作。
