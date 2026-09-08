# Correctness review 报告

## 结论

`needs-fix`。代码层面无 blocker，共发现 5 条 major。

## 目标锚定与执行限制

目标为 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect`，注册分支为 `refs/heads/fix/timeout-408-disconnect`，HEAD 为 `45e7cfb972b6f9df5874a8455d9961d692f2bba2`。`pwd` 在绝对路径切入后返回目标路径，`git worktree list --porcelain` 也确认该路径与 HEAD。

`my-agents:as-reviewer` 不在可用 skill 列表中。运行时的 `EnterWorktree` schema 同时把 `name` 与 `path` 标为必填，而实现拒绝两者同时出现，因此无法完成字面要求的 `EnterWorktree(path=...)`；我没有伪造成功。作为只读替代，我从上述 HEAD 创建 archive，与目标文件逐字比较，并对全部 4 个变更文件逐个运行 `git diff --no-index --check`，均退出 0。当前 diff 仅包含：

- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/pipeline/direct_driver/base.py`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/server/routes/inference.py`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/tests/int/test_pipeline_app.py`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/tests/unit/pipeline/test_direct_driver.py`

未发现 H2 policy、配置 default 或 lockfile 改动。

## Major findings

### Major 1——被 cleanup 替换的 cancellation 会进入 retry

**位置：** `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/server/routes/inference.py:213-219`，`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/pipeline/direct_driver/base.py:145-160`

**触发输入 → 错误结果：** 客户端断开使 AnyIO cancel scope 取消 provider await；若 provider 或 transport 在取消清理中以一个可重试异常替换顶层 `CancelledError`，例如抛出以该 cancellation 为 cause 的 `PipelineRetry`，`DirectDriver` 的顶层类型检查不再命中，随后 `_handle_failure()` 花费 retry budget 并打开第二次 provider attempt。基于目标文件的受控探针得到 `provider_calls=2`、`attempt_count=2`。

这直接违反 C4。新增 integration test 的 provider 只传播裸 `CancelledError`，因此无法区分这一失败形态。

**修复方向：** 在所有进入 retry classification 的 `BaseException` 路径上，同时检查当前任务是否仍在取消以及异常链中是否含 `CancelledError`；命中时保留 cancellation 为主异常，不花费 budget，也不打开下一 attempt。增加 provider 在取消时抛出 retryable cleanup exception 的测试，并断言调用数仍为 1。

### Major 2——response owner 只在裸 cancellation 分支关闭，其他未移交路径仍泄漏

**位置：** `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/pipeline/direct_driver/base.py:162-207`

**触发输入 → 错误结果：** streaming provider 返回 429 response，rate limiter 判为 failure，代码先把 `outcome.response` 清为 `None`，随后在 budget 耗尽或 retry 时离开当前 attempt，却从未调用 `response.aclose()`。基于目标文件的受控探针得到 `outcome_response=None`、`response_is_closed=False`、`underlying_close_finished=False`。同一缺口也存在于 success subscriber 抛出普通异常的 `except BaseException` 分支。

这违反 C4 中“provider response 已返回但未移交时会关闭”的 owner invariant，而且 429 retry 是正常运行路径，不是仅有理论可能的异常。

**修复方向：** 不要分别在少数 catch 中补 close；应让 driver 在明确完成 handoff 之前持续拥有 response，并通过统一的 `try/finally` 或 owner guard 在所有 retry、terminal failure、subscriber failure 与 cancellation 路径关闭它。关闭必须采用 cancellation-resistant cleanup。为 streaming 429 和 success subscriber failure 分别加入底层 stream 已关闭断言。

### Major 3——实际 AnyIO level cancellation 会再次中断 `response.aclose()`

**位置：** `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/pipeline/direct_driver/base.py:192-201`，测试盲点位于 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/tests/unit/pipeline/test_direct_driver.py:597-622`

**触发输入 → 错误结果：** disconnect 发生在 provider response 已返回、success subscriber 尚未结束时。代码捕获第一次 cancellation 后直接 `await response.aclose()`；但生产路径位于已取消的 AnyIO cancel scope 内，任何 cleanup checkpoint 都会再次收到 cancellation。目标代码探针中的 stream 在 `aclose()` 内执行一个 checkpoint，结果为 `close_started=True`、`close_finished=False`。`httpx2.Response.is_closed` 已提前变为 `True`，但底层 release 并未完成。

新增 unit test 使用一次性的 `Task.cancel()`，且 `UnreadStream` 的关闭没有可辨别 checkpoint，因此会在生产 cleanup 尚未完成时假绿。

**修复方向：** 在独立 cleanup task 中关闭 response，并以项目现有 `finish_stream_cleanup` 同类机制等待其完成，使第二次 cancellation 只能延后交付而不能终止释放。测试应通过 `_run_dispatch_while_connected` 的 AnyIO cancel scope 驱动断开，并由底层 stream 的 `close_finished` 事件证明释放真正完成，而不是只检查 `Response.is_closed`。

### Major 4——disconnect 下的 response close failure 被 AnyIO task group 完全吞掉

**位置：** `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/pipeline/direct_driver/base.py:197-200`，`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/server/routes/inference.py:221-230`

**触发输入 → 错误结果：** disconnect 取消 operation，随后 `response.aclose()` 抛出 cleanup failure。`raise_with_cleanup_under()` 把 cleanup failure 挂在 `CancelledError` 下，但 AnyIO task group 会把来自自身 cancel scope 的整条 child cancellation 当成预期取消并抑制。helper 随后新建一个无 cause/context 的 `ClientDisconnect`。对目标 helper 的受控探针最终只能遍历到 `ClientDisconnect`，原 cancellation 与 `response close failed` 均不可达。

这违反 C5：cleanup failure 被吞掉，completion/accounting 也只能将请求记录为普通 disconnect。

**修复方向：** `run_operation` 必须在 task group 抑制 cancellation 之前捕获 operation 的退出对象及其 secondary failures；退出 task group 后再以 `ClientDisconnect` 为主异常挂接或记录 cleanup failure。加入遍历 `__cause__`、`__context__`、`BaseExceptionGroup.exceptions` 的断言，并验证 completion 仍以 disconnect 为主分类、cleanup 作为次级事实保留。

### Major 5——dispatch 先完成但 listener 停止失败时，已产生的 Response 被遗弃

**位置：** `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/src/app/server/routes/inference.py:205-231`

**触发输入 → 错误结果：** operation 已返回一个拥有 provider stream 的 Response，`run_operation` 将它放入 `result` 后取消 listener；若正在执行的 `Receive` 在 cancellation cleanup 中抛出异常，task group 传播 listener error，helper 不会抵达 `return result[0]`，也没有关闭该 result。受控探针得到 `raised_type=ReceiveCleanupError`、`owner_closed=False`。

这同时违反 C3 与 C5：Response owner 既未移交给 ASGI response，又未由 helper 释放，listener cleanup failure 成为唯一可见结果。

**修复方向：** 把“task group 已干净退出”作为 handoff commit point。在此之前由 helper 持有可释放的 result；listener 停止失败时调用显式 disposer／owner guard 关闭 Response，再按既定主次关系传播 listener failure。增加一个 cancellation 时抛错的 `Receive` 和一个带底层 close marker 的 streaming Response 测试。

## 验证结果

- 当前目标实现：新增 disconnect test、response-start failure test、response ownership unit test共 3 项通过，`3 passed in 4.01s`。
- 当前目标实现：完整 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect/tests/unit/pipeline/test_direct_driver.py` 通过，`29 passed in 1.58s`。
- 新 integration test 对旧 HEAD 实现会失败，并且失败为 `TimeoutError`，没有被 `pytest.raises(ClientDisconnect)` 或外层 timeout 假绿。
- 新 response ownership unit test 对旧 HEAD 实现会失败于 `response.is_closed is False`。
- 现有 response-start failure 路径在目标实现上通过；除上述 findings 外，未发现 C1、C2、C6 的 blocker/major 退化。
- C8 已确认：diff 没有混入 H2 policy/default 改动。

受控探针保存在 `/tmp/timeout-review-current-a48e2424/`。目标 worktree 未被修改；本轮是只读评审边界，没有需要归档到 repository 的产物，因此不执行 repository closeout。