# 独立代码复评：Session liveness R2

## 结论

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-liveness` 分支 `feat/session-liveness`，anchor `47d9ef101c4b81ac70d805b1da157b34d021d33d` 至当前 HEAD `135f5b4bf0946f7c5c9cd032f54f97cc04698210`；直接审阅功能提交 `74cff321d3ce993f7def73790b55dee8d44b9d2c` 与修复提交 `135f5b4bf0946f7c5c9cd032f54f97cc04698210` 的 diff，并复核最终代码。上一轮报告文件缺失，因此按派活提示给出的两项 major 作为上一轮基线。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：2。
- **squash 判断**：当前仍有 major，不能按“只剩 minor”直接 squash 回主分支。

## 双视角覆盖证据

### 机械核对

- 对账 anchor、分支、精确 HEAD、两提交日志、逐提交 diff、最终文件与所有 `keepalive_stream`／`session_liveness_stream` 使用点；每次 shell 调用均在同一调用内校验 root、branch 与 HEAD，目标 worktree 最终保持干净。
- 逐条核对上一轮两项 major：wrapper 现在于 `src/app/streaming/keepalive.py:106-116` 持有 inner 并在 `finally` 中 `await inner.aclose()`；同步取消且 pull 已完成时，`src/app/streaming/keepalive.py:45-65` 会无条件 await／观察 done task，`tests/unit/test_streaming_resilience.py:265-323` 覆盖 item、`StopAsyncIteration` 与普通异常三态。
- 扫描本轮点名的新风险：cleanup 取消优先级、done item 丢失、`StopAsyncIteration`／普通异常、wrapper 资源归零；并检查 Ruff、Pyright 与测试结果。
- 验证结果：最终一次完整收集与执行均为当前 HEAD 全仓 `297` 项，全部通过；Ruff 对两个改动文件通过；Pyright 对生产文件 `src/app/streaming/keepalive.py` 为 0 errors。对测试文件直接运行 Pyright 时，当前 invocation 无法解析 `anyio`／`pytest`，产生级联 missing-import 诊断，因此未把该次运行当作代码通过证据。

### 第一人称执行模拟

- 模拟正常消费：upstream 依次返回 item、结束、抛普通异常；观察到 item 原序交付、`StopAsyncIteration` 正常终止、普通异常传播。
- 模拟 consumer 单次取消与 wrapper 显式关闭：活动 pull 均归零，upstream `aclose()` 被调用一次，wrapper frame 关闭；两项上一轮 major 在这些路径上已修复。
- 模拟 pull 已同步完成后才向 consumer 投递取消，分别让 pull 得到 item、结束、抛异常；三态均观察了 done task，consumer 保持 `CancelledError`，未发现 done item 在仍存活 consumer 路径中丢失。
- 模拟 cleanup 中点再次取消 consumer：upstream 已进入异步 `finally`、但尚未完成；第二次取消后 cleanup 被截断，显式 close 未继续执行。
- 模拟主退出为 consumer cancellation 或 upstream `ValueError`，同时 upstream `aclose()` 抛 `RuntimeError`；两种情况下最终可见异常都变成 close 的 `RuntimeError`。

## 上一轮 major 复核

- **wrapper `aclose()` 非确定**：已修复。`keepalive_stream()` 现在显式持有并关闭 inner；单次显式关闭与单次取消探针均观察到活动 pull 为 0、close 调用为 1、wrapper frame 已关闭。
- **同步 cancel 时 done task 异常未观察**：已修复。`_cancel_and_observe()` 不再跳过 done task；item、`StopAsyncIteration`、普通异常三态的 task 均被 await，且取消仍是 consumer 的最终退出原因。

## 事实性发现

[major] `src/app/streaming/keepalive.py:45-47`、`src/app/streaming/keepalive.py:50-65` — cleanup 不能抵抗第二次取消，可能在资源归零前结束 — 确定性探针让 upstream pull 在其异步 `finally` 中等待事件：第一次 `consumer.cancel()` 进入 `_cancel_and_observe()`，第二次 `consumer.cancel()` 在该函数 `await pending` 时到达；结果 consumer 为 `CancelledError`，但 `cleanup_finished=False`，且顺序执行的 `await _close_iterator(stream)` 被跳过。async generator frame 已关闭不等于 upstream cleanup 已完成；wrapper 继承同一 inner cleanup 缺陷。— 建议把 pull settle 与 iterator close 组成不可被后续取消截断的完整 cleanup 协议：记录外部取消、在独立 cleanup task 中完成 settle＋close、循环 shield／观察直到资源归零，最后再恢复原取消；新增“cleanup 中点二次取消”的确定性回归测试，并断言 upstream `finally` 完成、活动 pull 为 0、close 恰好执行。

[major] `src/app/streaming/keepalive.py:44-47`、`src/app/streaming/keepalive.py:94-97` — `_close_iterator()` 的异常会覆盖正在离开的取消或 upstream 主异常，违反 cleanup 退出原因优先级 — 两个确定性探针分别以 `CancelledError` 和 upstream `ValueError("pull failed")` 触发 generator `finally`，再让 `aclose()` 抛 `RuntimeError("close failed")`；最终调用方两次都只看到 `RuntimeError: close failed`。这会把客户端断连误报为 cleanup 故障，也会丢失 upstream 原始失败。— 建议显式保存 primary exception／cancellation，执行 close 时观察并记录 secondary cleanup failure，但在存在 primary 时保持 primary 为最终退出原因；仅在没有 primary 时传播 close failure。为 cancellation＋close error、pull error＋close error、正常结束＋close error 三个分支补回归测试。

## 点名风险结论

- **cleanup 取消优先级**：发现上述 2 项 major。
- **done item 丢失**：未发现新的 blocker／major；正常完成 item 会在 `pending.done()` 分支优先交付，consumer 已取消时取消优先且 done task 仍被观察。
- **`StopAsyncIteration`／普通异常**：单独发生时语义正确；cleanup 同时失败时被覆盖，已归入第 2 项 major。
- **wrapper 资源归零**：单次显式 close 与单次 cancel 均归零；二次取消继承第 1 项 major，尚不能宣称所有退出路径资源归零。

## 主观建议

未另列主观建议。
