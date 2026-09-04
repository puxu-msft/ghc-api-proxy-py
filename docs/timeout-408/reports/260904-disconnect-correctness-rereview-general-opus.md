# 最终 correctness 复核报告

## Verdict

`pass`，可合并。**无 blocker/major。**

## 最后一项复核

`src/app/pipeline/direct_driver/base.py:51-101` 现已满足异常图闭包：

- `_clear_exception_backedges()` 使用 identity `seen` 集防止递归循环。
- 它递归遍历未清除的 `__cause__`、`__context__` 与 `BaseExceptionGroup.exceptions`。
- 只删除直接指向所选 cancellation 的 backedge，其余 Outer/Inner wrapper 和 metadata 保持结构化可达。
- `_without_exception()` 使用 PEP 654 `group.split(identity)`，residual group 的显式 cause、note 与成员均得到保留。

针对冻结目标源码重跑 `/tmp/timeout-review-current-a48e2424/probe_nested_backedge.py`，结果为：

- `raised_type=ClientDisconnect`
- `outer_reachable=True`
- `inner_reachable=True`
- `inner_cause_is_cancellation=False`
- `cycle_via_nested_backedge=False`
- `cancellation_notes=None`

新增测试 `tests/unit/pipeline/test_direct_driver.py` 同时验证 cancellation primary、Outer/Inner 可达、provider 仅调用一次，以及遍历 cause/context/group members 时异常图无环。该测试具有足够分辨力。

## A5 与相邻契约复核

- status retry cleanup 遭直接取消时传播 `CancelledError`，底层 close 完成。
- cleanup 跨过 `asyncio.timeout` 时传播 `TimeoutError`，没有恢复已消费的 `UpstreamError`。
- subscriber retry cleanup 遭直接取消时同样传播 `CancelledError`，底层 close 完成且没有打开第二次 provider attempt。
- close 自身失败时，已被 retry 决策消费的 subscriber/status error 才恢复为 primary，close failure 保留为 secondary。
- helper 在 task-group `__aexit__` 遭外层 cancellation 时仍关闭 prepared Response。

## 验证记录

- 独立运行最新 5 项 targeted regressions，结果为 `5 passed in 3.27s`。
- 接受协调者提供的 `294 tests`、Ruff 与 Pyright 全绿作为当前工作前提。
- 当前 6 个变更文件的逐文件 diff whitespace check 均退出 0。
- 未发现 H2 policy/default 改动。
- 目标 worktree 未被修改。