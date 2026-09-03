# HTTP 408 后长期请求修复状态

状态：implemented，等待 development-record closeout。

行为权威见 `spec.md`；用户控制的需求来源见 `../../../docs/.human-controlled/upstream-retry-and-continuation.md`。

## 当前结论

已确认的 request-accumulation 根因是：Uvicorn H1 connection 在 upstream response headers 返回前消失时，Uvicorn 只持久标记 disconnect 并唤醒下一次 `receive()`，不会取消 ASGI task；旧 `_dispatch()` 在请求体读完后不再读取 `receive`，所以 detached request 继续等待或重试上游。

事故截面的 10 条 active requests 全部是 downstream H1，而仅有 5 条打开连接，至少 5 条 request task 已失去原 connection。具体是哪五条、何时断开及客户端是否随后 reissue 均未闭合；这些未知不影响本地 persistence 机制与修复入口。

HTTP 408 是另一层：GitHub Copilot 返回 `408 user_request_timeout`，message 为 `Timed out reading request body. Try again, or use a smaller request size.`；proxy 将其归入 `serverError` 无冷却重试，SDK retry 已关闭。事故中一条 request 最终累计 14 attempts 后结束于上游 408，另一条累计 16 attempts 后由本地 3600 秒 client deadline 终止。无冷却 retry 是已确认的 orphan-work 放大机制，不是第一条 408 的充分原因。

上游 H2→H1 后的等长 20 分钟窗口中，p95 duration 从 575.645 秒降到 52.723 秒，多-attempt records 从 11 降到 1，final 408 从 1 降到 0；restart 同时清空了 backlog且 workload 不同，因此 H1 是已确认有效的现场 mitigation，H2 仍不是所有 408 的唯一已证根因。当前 `httpx2 2.12.0/httpcore2` 的本地 wire-level PoC 另行确认 graceful GOAWAY 仍会截断活动 H2 stream；保持 `upstream_transport.http2: false` 有机制依据。

现场另有严重 wall/monotonic clock drift。它完整解释 TUI 的 2988 秒与 wall timestamp、3600 秒 deadline record之间的差额，但不能解释 GitHub 自己返回的 HTTP 408。

## 已实现

`main` commit `33cf387` 在请求体完整读取后并行运行 dispatch 与 Uvicorn disconnect listener；disconnect 会取消整个 dispatch，且 retry loop 不再把被 cleanup wrapper 替换的 cancellation 当成可重试失败。

DirectDriver 在 handoff 前持续持有 provider Response；429/status rejection、subscriber failure/retry、AnyIO level cancellation、deadline、listener failure、helper outer cancellation和 close failure均通过统一 owner cleanup。`finish_async_cleanup()` 在独立 task 中完成释放；异常优先级、residual ExceptionGroup metadata 与完整异常图无环均有回归测试。

当前产品范围明确为 Uvicorn 0.52.4＋H11＋无 receive-consuming middleware。通用 ASGI receive wrapper 的 cancel-after-dequeue 反例经独立仲裁判为范围外；重开条件以 `spec.md` §1 为权威，包括切换 ASGI server、加入该类 middleware、公开支持任意 ASGI host、Uvicorn disconnect 不再由持久 flag 重复报告，或在当前 Uvicorn H11 组合上复现跨 listener handoff 后读不到已经发生的 disconnect。

## 验证

Reviewed source：`archive/260904-timeout-408-disconnect` 指向 `a565bbb`；mainline squash：`33cf387`。两者六个 owned paths 的 blob 逐一相同。

Integration worktree 基于包含后续 HTTP 499 提交的 `main`，执行：

```bash
uv run --frozen ruff check src tests
uv run --frozen pyright src tests
uv run --frozen pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

结果：Ruff 全绿；Pyright 0 errors；2206 passed、2 skipped；coverage 91.55%。两位独立代码 reviewer 最终均为 0 blocker、0 major、可合；ASGI relay 分歧另经未卷入仲裁判定不阻断当前产品范围。

## 保留的未决项

- GitHub `Timed out reading request body` 的远端物理原因尚未闭合。并发、MiB 级 body、H2 flow control、SOCKS 链路与 upstream edge 均有可能；现有 records 缺每次 attempt 的 serialized request bytes、stream/connection id与 upload progress，不能择一写成根因。
- 本次不修改 HTTP 408 的 retry policy、retry budget、timeout 默认值或 H2 schema 默认值。若要把代码默认改为 H1，属于独立产品契约决定；当前部署已显式使用 H1。
- Response-header 阶段的 live attempt count 没有及时投影到 TUI，cancellation record 的 attempts 可能停在默认 1。这是可观测性缺口，不影响本次 lifecycle 修复，未静默并入代码 patch。

## 未采纳方向

- 仅缩短 `client_request_deadline`：只会更早回收症状，仍不能在客户端实际离开时取消，故不是根因修复。
- 将 HTTP 408 直接改为不可重试：会改变用户控制文档明确规定的行为，且无法解释 detached task persistence。
- 只改 TUI，把长时条目隐藏或定时 reap：会丢掉仍在运行的真实请求，并继续消耗上游资源。
- 新增通用 retry backoff：可能缓和请求风暴，但不关闭无人消费的旧 task，且属于独立策略变更。
- 为任意 ASGI receive wrapper 新建跨阶段 relay：当前固定 Uvicorn H1 拓扑没有该触发条件；已记录明确重开条件，不以未来假设扩大本次实现。