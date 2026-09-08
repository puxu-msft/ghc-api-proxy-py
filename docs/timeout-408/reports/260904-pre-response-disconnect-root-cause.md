# 响应前客户端断开未取消上游的根因实验

记录时间：2026-09-04。本文是点时调查报告，不随实现改写；当前结论由 `../spec.md` 和 `../status.md` 接管。

## 现场症状

用户提供的日志同时出现：

- GitHub Copilot `/responses` 在 02:35:10 返回一次 HTTP 200，随后于 02:35:20、02:35:25 和 02:39:28 成批返回 HTTP 408。
- TUI 显示 5 个 client connections，却有 10 条同模型 active requests；最长已存活 2988.3 秒。

HTTP/2 一条连接可同时承载多个 request stream，因此“连接数少于活跃请求数”本身合法；异常在于旧 stream 已被客户端放弃后，代理端请求仍长期存活。

## 代码路径

1. `serve()` 在请求进入时把 request id 加入 active registry。
2. `_dispatch()` 完整读取 request body。
3. 随后 `_dispatch()` 进入解析、路由、限流等待和 `handle_bounded()`；这里没有继续读取 `request.receive`。
4. 只有 `_dispatch()` 返回 `StreamingResponse` 后，Starlette 的 response `__call__` 才并行监听 `http.disconnect`。
5. 因而“body 已读完、上游响应头未到”的窗口没有下游断开观察者。

## 因果实验

实验脚本：`$CLAUDE_JOB_DIR/tmp/reproduce_pre_response_disconnect.py`，运行命令：

```bash
PYTHONPATH=src uv run python "$CLAUDE_JOB_DIR/tmp/reproduce_pre_response_disconnect.py"
```

实验通过真实 `create_pipeline_app()` 和 ASGI scope 驱动 `/v1/responses`，provider 在响应头前永久等待。`receive()` 第一次返回完整 `http.request`，第二次已准备返回 `http.disconnect`。

当前实现的观测：

```text
{'receive_calls': 1, 'app_finished_after_disconnect_available': False, 'live_requests': 1, 'upstream_cancelled': False}
{'live_requests_after_server_cancellation': 0, 'upstream_cancelled_after_server_cancellation': True}
```

第一行证明断开消息无人读取，app 和 provider 都继续运行，active slot 未释放。第二行是正向控制：一旦 server task 真正收到取消，取消能穿过 retry loop 到达 provider，完成协调器也会把 active slot 移除。因此缺陷不在取消传播或 registry cleanup，而在响应前阶段根本没有产生取消信号。

## 根因链

客户端因等待超时或收到可重试状态而取消旧 HTTP/2 stream并发起新请求 → 代理未读取旧 stream 的 `http.disconnect` → 旧 dispatch 继续等待/重试上游 → 新旧请求同时出现在 active registry → 同一批 client connections 下活跃请求数和存活时长持续增长 → 旧请求的重试进一步增加上游负载并提高后续 408 概率。

证据权重：根因机制“响应前断开无人读取”已由可逆因果干预确认，强到足以实施；现场每一条长时 request 是否都由同一机制产生，仍待运行时持久记录逐条对账，不能从一张 TUI 截面全称断言。

## 排除项

- active registry 自身不会在收到完成信号后泄漏：手工取消 server task 后归零。
- retry loop 没有吞掉 `CancelledError`：provider 收到取消，且请求被记录为 `gone`。
- client deadline 并非完全未生效：现有测试覆盖 pre-header 与 streaming body；但默认 3600 秒晚于客户端自行放弃的时点，不能替代断开监听。
- 隐藏或 reap TUI 条目不是修复，因为条目对应仍在执行的真实 task。

## 调查限制

项目指令列出的前身与官方参考目录在本会话文件系统中不存在，无法重新核对客户端对 HTTP 408 的重试实现。当前源代码注释声称 Claude Code 会重试 408，但本文不把该注释提升为独立证据；本次修复不依赖这项外部语义。