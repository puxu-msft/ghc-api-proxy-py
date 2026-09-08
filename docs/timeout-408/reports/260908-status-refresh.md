# timeout-408 状态刷新报告

日期：2026-09-08

## 改动

- 更新 `.dev/docs/timeout-408/status.md`，将 living 状态从“当前 checkout 尚无 disconnect listener”纠正为：当前 `main` 已包含 response-preparation disconnect listener 与 cancellation/cleanup 实现。
- 明确区分已在 `main` 的实现、仍遗留/待决的 HTTP 408 远端根因与策略问题，以及证据基线。
- 未改动 `.dev/docs/timeout-408/spec.md` 或用户控制文档；用户已裁决的 HTTP 408 retry、timeout、H2 与 ASGI 范围边界保持原样。历史报告继续保留在 `reports/`，并在状态页标明其点时性质。

## 代码证据

- 当前 checkout：`main`，HEAD `d7e71c19`；`git merge-base --is-ancestor 33cf3870... HEAD` 成功。`33cf3870` 为 `fix: cancel upstream work after client disconnect`。
- `src/app/server/routes/inference.py`：
  - `_dispatch_with_body()` 在 body 完整读取后进入 `_run_dispatch_while_connected()`。
  - `_run_dispatch_while_connected()` 用 task group 并行 dispatch 与 `receive()` listener，收到 `http.disconnect` 后取消 dispatch，并对未 handoff 的 response 做 cleanup。
  - `serve()` 和 `_AccountedStreamingResponse` 保留 `ClientDisconnect`／streaming 阶段的记账与清理边界。
- `src/app/streaming/keepalive.py`：
  - `session_liveness_stream()` 处理 streaming heartbeat/idle timeout。
  - `finish_stream_cleanup()` 与 `finish_async_cleanup()` 处理 pending pull、iterator close 和 cancellation-resistant async cleanup。
- 测试证据：`tests/int/test_pipeline_app.py` 含 `test_count_http_disconnect_cancels_running_process` 及 listener cleanup/cancellation 覆盖；`tests/unit/streaming/test_streaming_resilience.py` 覆盖 keepalive/cleanup。

## 未做事项

- 未重新运行测试；本次是文档状态核实。
- 未修改 HTTP 408 retry policy、retry budget、timeout 默认值、H2 默认值或 upstream 远端根因结论。
- 未修改源码、测试、配置或其他主题文档；未删除、`git add`、commit、push。

## MSR-07 修订（2026-09-08）

- 将 `status.md` 顶部和“证据基线”中的 `HEAD d7e71c19` 改为 2026-09-08 审计的点时 checkout 基线，明确不对未来 HEAD 作持续声明。
- 保留证据：在该审计基线中，`33cf3870afee562351b49141efc8d5901f850c16` 由 `git merge-base --is-ancestor` 确认为 `main` 祖先。
- 同步限定“已在 main”段落为该审计基线语境；未改动源码、测试、配置、用户裁决或其他主题文件。
