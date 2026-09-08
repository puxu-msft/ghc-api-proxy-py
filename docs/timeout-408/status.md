# HTTP 408 后长期请求修复状态

状态：living；2026-09-08 审计记录的 checkout 基线为 `main`（HEAD `d7e71c19`），这是点时证据，不是对后续 checkout 的持续声明。此前“当前 checkout 没有 response-preparation disconnect listener、`src/`／`tests/` 没有对应实现”的顶部注记已过时，本文件不再沿用该结论。

## 当前结论

在上述 2026-09-08 审计基线中，`main` 已包含 `33cf3870`（2026-09-04，`fix: cancel upstream work after client disconnect`），且该提交当时是该基线 HEAD 的祖先。响应头尚未产生时的 downstream disconnect lifecycle 修复已在该审计 checkout 装位；这不是把点时报告中的用户裁决倒写成代码事实，而是以当时源码和提交历史重新核实实现状态。

`docs/.human-controlled/upstream-retry-and-continuation.md` 仍是需求层权威；`spec.md` 仍记录本主题在 Uvicorn 0.52.4、downstream HTTP/1.x、无消费 `receive` 的 middleware 范围内的行为规格、非目标和重开条件。本文只同步实现状态，不改变 HTTP 408 的既有可恢复失败语义、retry budget、timeout 默认值或 H2 schema 决定。

## 已在 main

- `src/app/server/routes/inference.py` 的 `_dispatch_with_body()` 在完整读取 body 后调用 `_run_dispatch_while_connected()`（约 533–581 行）。该 helper（约 404–496 行）以 AnyIO task group 并行运行 dispatch 与持续 `receive()` listener；收到 `http.disconnect` 时取消 dispatch，并在 response handoff 前等待 listener 清理。
- 同一 helper 区分 `operation`、`disconnect`、`listener` winner；未 handoff 的 prepared `Response` 通过 `_discard_prepared_response()` 释放。dispatch 取消不会被当成可重试 upstream failure。
- `serve()` 对 `ClientDisconnect` 保持既有 `gone`／completion 记账语义，并返回内部 `_DisconnectedResponse`；响应流阶段的 `_AccountedStreamingResponse` 仍自行观察 `http.disconnect` 并完成 owner cleanup。这表示 response-preparation listener 与后续 StreamingResponse listener 的 receive ownership 是分阶段的，不是两个并行消费者。
- `src/app/streaming/keepalive.py` 的 `session_liveness_stream()` 仍负责 streaming pull、heartbeat、idle timeout 和退出清理；`finish_stream_cleanup()`／`finish_async_cleanup()` 负责取消并观察 pending pull、关闭 iterator，以及在再次 cancellation 时让异步释放运行到终态。它不是缺失的 response-preparation listener 的替代品；两者职责不同。
- 相关回归证据在 `tests/int/test_pipeline_app.py` 的 `test_count_http_disconnect_cancels_running_process` 及 `_run_dispatch_while_connected` 的 disconnect、cleanup failure、outer cancellation 测试；streaming cleanup/keepalive 覆盖在 `tests/unit/streaming/test_streaming_resilience.py`。

## 仍是遗留／待决

- GitHub `408 user_request_timeout`（`Timed out reading request body`）的远端物理原因仍未闭合。并发、MiB 级 body、H2 flow control、SOCKS 链路和 upstream edge 仍是候选；现有记录不足以择一宣称根因。
- 本主题尚未改变 HTTP 408 retry policy、retry budget、timeout 默认值或 H2 schema 默认值。将代码默认切换为 H1 是独立产品契约决定，不由本状态页代决。
- 每次 attempt 的 serialized request bytes、stream/connection id、upload progress，以及 response-header 阶段及时投影到 TUI 的 attempt count 仍是可观测性缺口。
- 当前规格的范围外条件仍待未来证据触发重开：更换 ASGI server、加入消费 `receive` 的 middleware、公开支持任意 ASGI host，或在当前 Uvicorn H11 组合复现 response-preparation listener 取消后 StreamingResponse listener 读不到已发生 disconnect。

## 证据基线

- 点时 checkout 审计基线：`main`，HEAD `d7e71c19`（2026-09-08）；在该审计时，实现提交 `33cf3870afee562351b49141efc8d5901f850c16` 由 `git merge-base --is-ancestor` 确认为 `main` 祖先。本条不对后续 HEAD 作声明。
- 源码基线：`src/app/server/routes/inference.py` 的 `_run_dispatch_while_connected`、`_dispatch_with_body`、`serve`、`_AccountedStreamingResponse`；`src/app/streaming/keepalive.py` 的 `session_liveness_stream`、`finish_stream_cleanup`、`finish_async_cleanup`。
- 测试基线：`tests/int/test_pipeline_app.py` 的 disconnect/cancellation 集成覆盖；`tests/unit/streaming/test_streaming_resilience.py` 的 keepalive/cleanup 覆盖。本次状态刷新未重新运行测试。
- 历史报告 `reports/260904-reference-timeout-semantics.md`、`reports/260904-runtime-forensics.md` 及其评审/处置文件保留为点时证据；其中描述“body 完成至 upstream headers 间没有 listener”的文字是实现修复前的历史观察，不得覆盖本页当前 checkout 状态。
