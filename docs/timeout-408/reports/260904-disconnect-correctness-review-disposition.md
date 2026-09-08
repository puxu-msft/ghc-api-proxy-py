# 响应前断开修复评审处置

状态：closed。

评审原文：`260904-disconnect-correctness-review-general-opus.md`、`260904-disconnect-correctness-rereview-general-opus.md`、`260904-disconnect-asgi-rereview-gpt-opus.md`。范围分歧仲裁：`260904-disconnect-relay-arbitration-general-opus.md`。

| 发现 | 级别 | 裁定 | 处置与证据 |
|---|---|---|---|
| Cleanup 替换 cancellation 后误入 retry | C | 采纳 | `find_cancellation()` 与 `_reraise_if_cancelling()` 仅在当前 task 仍 cancelling 且异常图含 `CancelledError` 时恢复 cancellation；retryable wrapper、ExceptionGroup 与两层普通 wrapper 均保持一次 provider call。 |
| Response owner 只在裸 cancellation 分支关闭 | C | 采纳 | `_send()` 返回后由统一 owner-finally 持有 Response，覆盖 429/status rejection、subscriber failure/retry、terminal failure、deadline 与 cancellation。 |
| AnyIO level cancellation 再次中断 `aclose()` | C | 采纳 | 从既有 stream cleanup 提炼 `finish_async_cleanup()`，在独立 task 完成释放；测试用 checkpointing close 断言底层 `close_finished`，不再只看 wrapper `is_closed`。 |
| Task group 吞掉 operation/response cleanup failure | C | 采纳 | Operation 与 listener child 在 task group 抑制 cancellation 前捕获退出对象，group 外建立主次；异常链保持 `ClientDisconnect → CancelledError → cleanup error`。 |
| Listener 停止失败时遗弃已产生 Response | C | 采纳 | Task-group clean exit 是 handoff commit point；listener cleanup failure 先关闭 prepared Response，`_AccountedStreamingResponse` 提供 owner close 入口。 |
| Helper 外层 cancellation 在 task-group `__aexit__` 跳过 result disposal | C | 采纳 | Response owner guard 包住整个 task group 与后置判定，仅最终 return 前 handoff；outer cancellation 下 prepared Response 在 helper 退出前关闭。 |
| Cancellation 作为 ExceptionGroup member 时形成异常图环，且 residual metadata 丢失 | C | 采纳 | `_reaches()` 遍历 group members；`_without_exception()` 使用 PEP 654 `split(identity)` 剥离 selected cancellation并保留 residual message/members/cause/context/notes。 |
| 普通 `Outer → Inner → cancellation` 的深层 backedge 仍形成环 | C | 采纳 | `_clear_exception_backedges()` 带 identity `seen` 遍历 cause、context 与 group members，只清直接 target 边；真实 driver 测试断言 Outer/Inner 可达、1 call且完整异常图无环。 |
| 已被 retry 决策消费的 discard reason 压过 cleanup 期间新 cancellation | C | 采纳 | Discard reason 改为 dormant evidence；cleanup 新 cancellation 优先并保留 `asyncio.timeout` 转换，只有 close failure 时才恢复原 status/subscriber error为 primary。 |
| Subscriber retry 与 response close failure 同时发生时原 retry 丢失 | C | 采纳 | Close failure 阻止新 attempt，原 `PipelineRetry` 为 primary、close error 为 cause；status failure 同理。 |
| 回归测试用伪造 downstream HTTP/2 scope 声称证明 `RST_STREAM` | C | 采纳 | 测试改为事故现场和 Uvicorn 实际支持的 HTTP/1.1，ASGI spec 改为 Uvicorn 0.52.4 发布的 2.3；living Spec 同步纠正。 |
| 任意 ASGI Receive wrapper 的 cancel-after-dequeue 可能跨 listener handoff 丢唯一 disconnect | C | 不采纳为当前缺陷 | 未卷入仲裁以高置信度选择 B：当前唯一生产栈固定 Uvicorn H11、无 receive-consuming middleware，disconnect 是持久 flag且后续 receive 重复返回。保留重开条件：更换 ASGI server、加入该类 middleware、公开支持任意 ASGI host、Uvicorn disconnect 语义改变，或当前 H11 上出现复现。不得把本裁定外推为通用 ASGI 正确性。 |

没有暂定发现。两位独立 reviewer 对最终 frozen blobs 均给出 0 blocker、0 major、可合 verdict；范围分歧已有第三方仲裁。Reviewed source 为 `a565bbb`，mainline squash 为 `33cf387`，六条 owned paths blob 逐一相同。

最终 integration gate：Ruff 全绿；Pyright 0 errors；2206 passed、2 skipped；coverage 91.55%。