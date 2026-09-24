# Replay Capability Fix 进度账本

## 任务列表

| 任务 | 状态 | 更新时间（UTC） | 操作会话 | 说明 |
| --- | --- | --- | --- | --- |
| 识别 capability 事实源与读取路径 | done | 2026-09-15T23:40:00Z | 当前会话 | `HistoryEntry.capture` 为资格事实源；history index 需持久化并读回该 projection。 |
| 在 replay 入口强制 capability | done | 2026-09-15T23:55:00Z | 当前会话 | `ReplayRequest.source_grant` 将 History capability 与 source entry/path/ref 绑定；`CaptureCapabilities.replay_rejection_code()` 是唯一资格判定；wire 同时验证选定 attempt 的完整 evidence。 |
| 覆盖拒绝与允许路径 | done | 2026-09-15T23:55:00Z | 当前会话 | 覆盖三个 mode 的 allow/deny、grant 缺失/错配、corrupt/incomplete/none、client request incomplete、wrong selector/attempt、NaN/inf deadline、executor deadline 与正文/credential 不泄漏断言。 |
| 验证与报告 | done | 2026-09-16T00:53:00Z | 当前会话 | RCR-04 合并后重新读取 process/matrix；RCR-01 改为 process 内受控 authority receipt，RCR-02 改为 deadline-bound fork reader worker。focused 52 tests、scope Ruff 与全仓 Pyright 均通过。 |

## 附录：边界

- 白名单仅限 replay、history entry/read projection 与对应单元测试。
- `HistoryEntry.capture` 是 capability 的单一事实源；`ReplayProcess` 不重新从 capture records 推断资格。
