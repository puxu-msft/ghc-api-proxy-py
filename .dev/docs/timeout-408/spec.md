# HTTP 408 后的下游断开与请求终止规格

状态：living，已实现。

## 1. 权威边界

需求层权威是 `docs/.human-controlled/upstream-retry-and-continuation.md`：客户端断开时必须取消上游请求；请求超时、HTTP 408 所属的可恢复失败仍可在尚未交付完整块时无痕重试，且既有无痕重试不设置冷却间隔。本规格只定义这两条要求在当前 Uvicorn 请求生命周期中的交界，不改变 HTTP 408 的可重试性、重试预算或既有 timeout 默认值。

当前受支持的生产拓扑是 Uvicorn 0.52.4、downstream HTTP/1.x，且没有消费 `receive` 的 middleware。Uvicorn H11 以持久 `disconnected` flag 表示连接丢失，此后每次 `receive()` 都会再次返回 `http.disconnect`。如果将来引入其他 ASGI server、消费后延迟转交消息的 receive middleware、公开承诺任意 ASGI host，或在当前 Uvicorn H11 组合上复现“响应前 listener 被 operation-win 取消后，后续 StreamingResponse listener 读不到已经发生的 disconnect”，必须重新评估跨 dispatch/response 阶段的持久 receive relay；当前规格不作这项更宽承诺。

## 2. 问题状态

代理此前只在读取请求体时或 Response 进入 ASGI 发送阶段后观察下游断开。请求体已读完、Response 尚未产生时，`_dispatch()` 可能长时间等待上游响应头、反应式限流器或代理内重试；这段期间没有协程读取 ASGI `receive`，所以 Uvicorn 已标记丢失的 HTTP/1.1 connection 不会终止旧 request task。

现场 10 条 active requests 全部是 downstream H1，而 Uvicorn 仅有 5 条打开连接；因此至少 5 条 request task 已失去原 connection 却仍在 dispatch。这个差额不要求客户端另发请求；具体 detached request ids、disconnect 时刻与 client reissue lineage 均未闭合。

## 3. 规定行为

### 3.1 请求体阶段

请求体仍由 dispatcher 在开始业务处理前完整读取。客户端在请求体尚未读完时断开，沿既有 `ClientDisconnect` 路径终止；不得建立上游尝试。

### 3.2 响应前阶段

请求体完整读取后，代理必须并行运行以下两个操作，直到其中一个先形成终态：

1. 既有 dispatch，包括解析、路由、限流等待、上游尝试和代理内重试。
2. ASGI 下游断开监听，持续读取 `receive`，直到收到 `http.disconnect`。

若 dispatch 先完成，代理停止本阶段的断开监听；只有 listener 干净结束后，prepared Response 才完成 owner handoff。StreamingResponse 自己的断开监听随后负责响应发送阶段，不得与本阶段监听并行消费同一 `receive`。

若先观察到 `http.disconnect`，代理必须取消整个 dispatch task，并等待取消传播和资源清理完成后再结束请求。取消必须到达当前 provider send、限流等待或 subscriber await；不得被 retry loop 解释为可重试失败，也不得再开启上游尝试。

### 3.3 Response ownership 与 cleanup

Provider 返回的 `httpx.Response` 在 success subscribers 全部完成且 route 接手前始终归 DirectDriver 所有。任何 retry、status rejection、subscriber failure、cancellation 或 deadline 在 handoff 前结束当前 attempt 时，driver 必须关闭 Response；prepared StreamingResponse 在 listener 停止失败或 helper 外层 cancellation 时也必须在退出前关闭。

所有异步 close 都必须在独立 cleanup task 中运行到终态。等待 cleanup 时再次收到 cancellation，只延后 cancellation 的交付，不得打断底层释放。

退出优先级为：正在传播的既有 primary；cleanup 期间新到达的 cancellation；cleanup failure。已被 retry 决策消费的 status/subscriber error 只是 dormant discard reason：close 成功时不得压过新 cancellation；只有 close 自身也失败时才恢复为 primary，使原 failure 与 close failure 同时可达。

若 cleanup wrapper 把 cancellation 改写成普通异常或 `BaseExceptionGroup`，当前 task 仍处于 cancelling 状态时必须恢复 cancellation 为主退出且不得重试。选中的 cancellation 从 secondary graph 中移除，其余 group message、members、cause、context、notes 与普通 wrapper 结构保留；cause/context/group 的完整异常图不得形成环。

### 3.4 记账

响应前断开沿既有 `ClientDisconnect` 语义记为 `gone`，写且只写一条请求完成记录，并从 active-request registry 移除。正常取消清理不得伪装成 HTTP 408、502 或 504；独立 cleanup failure 必须作为次级事实保留。

### 3.5 同时完成

如果 dispatch 已经形成结果，再观察到的断开由响应发送边界处理；如果断开监听先形成终态，则不得为了抢救一个尚未交付的结果继续 dispatch。判据是哪个 task 的完成先被协调器观察到，而不是 wall-clock 推断。任何尚未 handoff 的 Response 都由响应前 helper 持有，直到 task-group exit 与 owner cleanup 均闭合。

## 4. 非目标

本修复不把上游 HTTP 408 改成不可重试，不修改 `serverError.max_retries=9`、`max_total=20`、`upstream_request_deadline=1200` 或 `client_request_deadline=3600`，也不新增退避算法。若后续运行证据证明存活客户端的 HTTP 408 本身仍造成重试风暴，应作为独立策略变更回到需求层裁决，不得混入本次生命周期修复。

上游 H2→H1 切换是已确认有效的现场 mitigation；它与本规格的 downstream disconnect lifecycle 正交。当前不把 H2 改成新的代码默认值，也不在本项目内手写 hyper-h2/httpcore2 状态机修补。

本修复未修改、重启、停止或 signal 生产端口 4141 上的服务，也未发真实上游请求。

## 5. 可证伪验收

- 给真实 pipeline ASGI app 一个完整 H1 请求体，令 provider 在响应头前永久等待，并让 Uvicorn 语义的下一条 ASGI 消息为 `http.disconnect`：断开消息必须被读取，provider task 必须被取消，app 必须在短时间内返回，active registry 必须为空。
- Provider 在 cancellation cleanup 中抛出 retryable wrapper、含 cancellation member 的 `BaseExceptionGroup` 或两层普通 wrapper 时，provider 调用数仍为 1；cancellation 保持 primary，residual metadata 保留且异常图无环。
- Provider Response 在 429 retry、subscriber retry/failure、AnyIO level cancellation、deadline、response close failure、listener cleanup failure及 helper 外层 cancellation下均完成 owner cleanup。
- Cleanup 期间直接 cancellation 最终传播 `CancelledError`，`asyncio.timeout` 仍转换为 `TimeoutError`；close failure 与原 discard reason 同时可达。
- 没有断开的正常 buffered 与 streaming 请求保持既有响应和完成记账；请求体中途断开与响应发送阶段断开的既有测试继续通过。

## 6. 修订记录

- 2026-09-04，v1：根据现场日志中“5 connections、10 条长时 active requests”和真实 ASGI 最小复现，补全响应前阶段的断开取消语义；触发者为本次故障调查。
- 2026-09-04，v2：根据运行时取证和三轮独立代码评审，把现场协议纠正为 Uvicorn H1，移除未证实的 client reissue；补全 Response ownership、cancellation-resistant cleanup、异常优先级、exception-group metadata、防环及当前 ASGI host 边界。