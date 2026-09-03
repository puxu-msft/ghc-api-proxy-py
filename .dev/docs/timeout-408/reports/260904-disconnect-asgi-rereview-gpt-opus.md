# ASGI／并发终局复核报告

## 结论

**0 blocker，0 major；当前候选可合。**

`my-agents:as-reviewer` 不在本次可用 skill 清单中，故未加载。最终检查均直接在目标 worktree 执行。

## 冻结快照

```text
cwd=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect
toplevel=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/timeout-408-disconnect
HEAD=45e7cfb972b6f9df5874a8455d9961d692f2bba2
branch=fix/timeout-408-disconnect
staged=0
unstaged=6
```

最终 diff 涉及：

```text
src/app/pipeline/direct_driver/base.py
src/app/server/routes/inference.py
src/app/streaming/keepalive.py
tests/int/test_pipeline_app.py
tests/unit/pipeline/test_direct_driver.py
tests/unit/streaming/test_streaming_resilience.py
```

## A1～A7 终局裁定

| 命题 | 结论 | 依据 |
|---|---|---|
| A1 | 通过 | Operation、listener 与 task-group outer exit 均捕获终态；未 handoff 的 prepared response 在所有 helper 出口执行 cancellation-resistant disposal；operation/listener cleanup secondary 保持可达。 |
| A2 | 通过 | 多异常 group 不被错误 collapse；selected cancellation 被移除后 residual `BaseExceptionGroup` 保留 message、note、cause 与成员结构。`_clear_exception_backedges()` 现以 `seen` 遍历 cause、context 和 group members，真实两层 wrapper 回归证明异常图无环。 |
| A3 | 当前产品范围通过 | 当前唯一生产栈固定为 Uvicorn HTTP/1.1，且没有 receive middleware；Uvicorn 的持久 `disconnected` flag 使后续 receive 重复返回 disconnect。先前 cancel-after-dequeue 反例经独立仲裁判为当前范围外。重开条件是引入其他 ASGI server、receive middleware，或公开承诺任意 ASGI host。 |
| A4 | 不再构成命题 | Uvicorn 不支持 downstream HTTP/2。最终测试已改成 Uvicorn HTTP/1.1 connection loss，并使用 ASGI 2.3，不再以伪造 scope 声称证明 `RST_STREAM`。 |
| A5 | 通过 | Response ownership 覆盖 subscriber success 区间的取消、普通 failure、retry、status rejection、close failure 与 cleanup 期间的新 cancellation。优先级现为既有 primary，其次 cleanup 新 cancellation；仅当 close 失败时恢复已消费的 subscriber/status discard reason。 |
| A6 | 通过 | Disconnect、operation failure、listener failure、prepared response disposal 与 outer cancellation 均汇入同一 idempotent completion coordinator；回归测试断言 `live == ()` 且 `completed == 1`。 |
| A7 | 通过 | 关键竞态以 `Event` 和显式 cancellation 落点驱动，不依赖固定 sleep；包含 checkpointing close、retry/deadline、close failure、outer cancellation、nested wrapper、group residual 和 completion exactly-once 的判别性断言。 |

## 反例复核结果

- Subscriber `PipelineRetry` 与 response close failure 同时发生：`PipelineRetry("subscriber retry")` 为 primary，`RuntimeError("close failed")` 为 cause。
- AnyIO level cancellation 下的 checkpointing close：`stream_close_started=True` 且 `stream_close_finished=True`。
- Disconnect 期间 close failure：异常链保持 `ClientDisconnect → CancelledError → CloseError`。
- Nested `Outer → Inner → cancellation`：cancellation 成为 primary，outer/inner secondary 仍可达，所有回边已清除，图无环。
- Task-group outer cancellation：prepared response 在 helper 退出前完成 disposal。
- 原 HTTP/2 假设：已从测试和说明中删除，当前测试严格限定 Uvicorn HTTP/1.1 与 ASGI 2.3。

## 独立验证

最终冻结候选的 9 个核心 concurrency regression tests：

```text
9 passed in 2.54s
```

三个原始 PoC 均重新执行并符合预期。`git diff --check` 通过。协调者另报告相关 292 tests、targeted Ruff 和 Pyright 通过；本 reviewer 未重复执行完整 292-test 集合。

未发网络请求，未修改目标 worktree 或 Git。