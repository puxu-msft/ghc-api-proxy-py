# Session liveness primitive 独立验收报告

## 判定

**Verdict：符合本轮冻结的 primitive 行为要求，未发现阻断缺陷。**

验收对象为 `/home/xp/src/ghc-api-proxy-py-liveness` 的 commit `74cff321d3ce993f7def73790b55dee8d44b9d2c`。每个 shell 调用均在同一调用内校验目标 repo、完整 `HEAD` 与工作树洁净度；所有执行测试或产生判定证据的调用还打印并校验了 `PWD` 与 Git top-level。所有有效运行均加载 `/home/xp/src/ghc-api-proxy-py-liveness/src/app/streaming/keepalive.py`。目标工作树在验证结束时仍为洁净状态。

本判定仅覆盖用户指定的 `session_liveness_stream` primitive 可观察行为。Anthropic heartbeat payload 的协议构造、SSE 路由 wiring、真实网络 transport 与配置热重载不在本轮范围内，未据此宣称通过。

## 验收矩阵

| 验收项 | 独立 oracle | 结果 | 证据 |
|---|---|---|---|
| 慢 upstream 时产生多个 heartbeat，且同一时刻仅有一个 `anext` | 可控 async iterator 记录 `__anext__` 调用次数、活动调用峰值与 task identity；连续读取 3 个 heartbeat 前要求 `calls == 1`、`max_active == 1`、task identity 唯一 | 通过 | `/tmp/verify_liveness_74cff321.py:68`；运行输出 `PASS production_slow_upstream` |
| upstream 恢复后顺序不变 | 静默阶段后依次注入 `first`、`second`，要求 heartbeat 后严格收到 `first`、`second` | 通过 | `/tmp/verify_liveness_74cff321.py:68`；运行输出 `PASS production_slow_upstream` |
| upstream 结束后无额外 heartbeat | 第三个 upstream pull 注入终止哨兵，下一次消费必须直接得到 `StopAsyncIteration`，任何额外 frame 都使探针失败 | 通过 | `/tmp/verify_liveness_74cff321.py:68`；运行输出 `PASS production_slow_upstream` |
| upstream idle deadline | upstream 永久阻塞时要求约 55 ms deadline 抛 `StreamIdleTimeoutError`；实测门限允许区间为 40～250 ms，同时要求 deadline 前有 heartbeat、仅一次 upstream pull、pull 被取消并完成清理 | 通过 | `/tmp/verify_liveness_74cff321.py:144`；运行输出 `PASS idle_deadline_and_cleanup` |
| consumer pause 不误触发 idle | 先收到 heartbeat，再让 upstream item 在 consumer pause 期间完成；pause 超过原 idle deadline 后恢复消费，必须优先返回已完成 item，而不是抛 idle timeout | 通过 | `/tmp/verify_liveness_74cff321.py:126`；运行输出 `PASS completed_item_beats_expired_deadline_after_consumer_pause` |
| cancel／close 无 task leak | 分别显式 `aclose()` 与取消正在等待的 consumer；要求 upstream pull task 已完成、活动 pull 为 0、iterator 恰好关闭一次；全部 case 后再检查事件循环中无额外 pending task | 通过 | `/tmp/verify_liveness_74cff321.py:172`、`:188`、`:241`；运行输出 `PASS explicit_close_has_no_pending_pull`、`PASS consumer_cancel_has_no_pending_pull`、`PASS global_no_task_leak` |
| interval 禁用 | 分别传入 `0` 与 `-0.25`；等待 35 ms 后 consumer 必须仍未完成且只有一个 upstream pull，注入 data 后只能收到 data、不能收到 heartbeat | 通过 | `/tmp/verify_liveness_74cff321.py:208`；运行输出 `PASS heartbeat_interval_disabled` |

## 独立正样本控制

探针包含一个故意错误的实现：每次 heartbeat timeout 都取消当前 upstream `anext` 并重新创建。相同的“多个 heartbeat 且单一 `anext`”oracle 必须拒绝该实现，否则生产实现的绿色结果不可采信。

正样本控制位于 `/tmp/verify_liveness_74cff321.py:118`，运行结果为 `PASS positive_control_known_bad_restarts_anext`。这里的 `PASS` 表示已知坏实现如预期触发了断言失败，oracle 成功变红，而不是坏实现通过。

探针 SHA-256 为 `299d9605b7bd8e6554d1fe035d7a244ff26e35428b56025fa2f3fe9e22b3b85d`，口径为本次验证期间 `/tmp/verify_liveness_74cff321.py` 的完整内容。

## 实际运行与结果

所有命令均使用 Python `3.14.2`、目标仓库 `.venv`，并设置 `PYTHONDONTWRITEBYTECODE=1` 与 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-liveness/src`。加载路径探针返回 `/home/xp/src/ghc-api-proxy-py-liveness/src/app/streaming/keepalive.py`。

1. 独立黑盒时序探针单次完整运行：8 项 `PASS`，包括 7 个行为／控制 case 与 1 个全局无 task leak 检查，退出码为 0。
2. 同一独立探针连续运行 10 次：每次均为 8 行 `PASS`，每次输出摘要 SHA-256 均为 `ac396e42990c76c1d649272cfe81ce2ad50de80d57cbcdcfc9834c179d9b8ba8`，退出码均为 0。该数字口径为 commit `74cff321d3ce993f7def73790b55dee8d44b9d2c`、上述固定探针与当前 Linux／Python 3.14.2 环境。
3. `python -m pytest -p no:cacheprovider -q tests/unit/test_streaming_resilience.py`：`13 passed in 0.78s`，退出码为 0。独立 AST 解析同一文件得到 13 个顶层 `test_*` 函数，与 pytest 收集／执行结果一致。
4. 验证结束后的 `git status --porcelain=v1` 为空，输出 `WORKTREE_CLEAN=yes`。

第一次尝试执行临时探针时，Python 尚在导入 Pydantic 配置模型便收到外部 `KeyboardInterrupt`；没有进入任何验收 case，因此该次运行不计入通过或失败。随后在重新执行同调用 gate 后，探针完整通过一次，再连续完整通过 10 次。

## 规格与实现证据

- 冻结规格要求默认路径为零缓冲直通流，并将 keepalive 与 idle timeout 视为不同机制：`docs/2604-rewrite/streaming-resilience.md:5-13`。
- 规格要求上游中途停顿与首项前长静默期间持续保活：`docs/2604-rewrite/streaming-resilience.md:84-93`。
- 规格定义 `stream_keepalive_ping_sec = 0` 为禁用，并要求心跳与 upstream 解耦：`docs/2604-rewrite/streaming-resilience.md:133-140`。
- 生产实现只在 `pending is None` 时创建 upstream pull task：`src/app/streaming/keepalive.py:25-29`。
- 生产实现先检查 `pending.done()`，再判 idle／heartbeat deadline，因此已完成 item 优先：`src/app/streaming/keepalive.py:31-50`。
- upstream 结束直接返回，不再产生 heartbeat：`src/app/streaming/keepalive.py:33-37`。
- cancel／close 的 `finally` 会取消并 await 未完成 pull，再关闭 iterator：`src/app/streaming/keepalive.py:51-56`。
- 非正 interval 返回禁用 deadline：`src/app/streaming/keepalive.py:59-65`。

## 未验证项

- 未验证 heartbeat 的具体 Anthropic `empty_text`／`ping` frame 是否满足客户端协议语义；本轮传入的是不透明 heartbeat sentinel。
- 未验证 HTTP SSE／WebSocket 路由是否已调用该 primitive。只读调用点搜索在 `src/` 下仅发现 `keepalive_stream` 对该 primitive 的包装，未发现路由级直接调用；这不影响 primitive 判定，但不能据此推导端到端 wiring 已完成。
- 未使用真实上游网络连接验证 wall-clock 长静默。本轮使用可控 async iterator 验证调度、顺序、deadline、backpressure 与资源清理语义。

## 缺陷

本轮未观察到违反冻结验收项的行为，因此没有可报告的失败复现，也不需要建议 debugger 或 implementer 修复路由。