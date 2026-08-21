# 独立代码复评：Session liveness R3

## 结论

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-liveness` 分支 `feat/session-liveness`，anchor `47d9ef101c4b81ac70d805b1da157b34d021d33d` 至 HEAD `f27a8c04cd3470bd50d7194a30371ca5404f727e`。本轮只复核 R2 的两项 major，以及提交 `f27a8c0` 的修复可能引入的新 blocker／major；重点覆盖 cancellation storm、shield cleanup task 泄漏、异常 cause 链和正常 close failure。
- **总体 verdict**：**可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：0。
- **squash 判断**：R2 两项 major 均已关闭，且未发现新 blocker／major，**可以 squash**。

## 双视角覆盖证据

### 机械核对

- 每次 shell 调用都在同一调用内校验目标 root、分支、精确 HEAD 和 anchor 祖先关系；测试与探针均设置 `PYTHONDONTWRITEBYTECODE=1`，pytest 禁用 cache provider，目标 worktree 在每轮后均保持干净。
- 对账 R2 报告、`f27a8c0` 的完整 diff、最终 `src/app/streaming/keepalive.py` 和新增测试。`src/app/streaming/keepalive.py:50-64` 现在显式保存 primary，并按“既有 primary／cleanup 期间取消／cleanup failure”排序；`src/app/streaming/keepalive.py:67-101` 将 settle＋close 放入独立 cleanup task，并循环 `asyncio.shield()` 直至该 task 完成。
- 核对新增确定性测试：`tests/unit/test_streaming_resilience.py:265-299` 覆盖 cleanup 中二次取消；`tests/unit/test_streaming_resilience.py:302-356` 覆盖 cancellation／upstream error 与 close failure 的 cause 链；`tests/unit/test_streaming_resilience.py:359-379` 覆盖无 primary 时传播 close failure。
- 定向回归测试通过；全量 pytest 通过；Ruff 对两个改动文件通过；Pyright 对生产文件 `src/app/streaming/keepalive.py` 为 0 errors、0 warnings、0 informations。

### 第一人称执行模拟

- 模拟 direct stream 与 `keepalive_stream` wrapper 各自遭遇 cancellation storm：第一次取消启动 cleanup，cleanup 阻塞期间继续投递五次取消，再释放 upstream cleanup。两条路径都完成 cleanup，最终仍传播第一次 `CancelledError`，且与执行前 task 集合对账后没有残留 task。
- 对 task 泄漏判据做正控：额外创建一个故意保持活动的 synthetic task，探针能够检测到它，证明“无残留 task”不是失效判据导致的假绿。
- 模拟 upstream `ValueError("pull failed")` 与 `aclose()` 的 `RuntimeError("close failed")` 同时发生。direct stream 与 wrapper 的最终 cause 链均为 `ValueError` primary → `RuntimeError` cause。
- 模拟 upstream 正常耗尽后 `aclose()` 失败，以及先产出 item、调用方再显式 `aclose()` 时 close 失败。两条无 primary 路径都向调用方传播 `RuntimeError("close failed")`。

## R2 major 复核

- **二次取消截断 cleanup**：已修复。独立 cleanup task 不随 consumer 的后续取消被取消；循环 shield 会观察 cancellation storm，但持续等待 settle＋close 完成。新增测试和 direct／wrapper 独立探针均观察到 upstream cleanup 完成，且没有 shield cleanup task 泄漏。
- **close 错误覆盖 primary**：已修复。有 primary 时，primary 保持为最终异常，close failure 作为显式 `__cause__`；无 primary 的正常耗尽或显式关闭路径则传播 close failure。新增测试与独立异常链探针结果一致。

## 事实性发现

未发现 blocker、major，亦未发现 R2 两项修复未闭合的证据。

## 主观建议

无。
