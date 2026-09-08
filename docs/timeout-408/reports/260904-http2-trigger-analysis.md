# 上游 HTTP/2 是否触发或放大 HTTP 408 故障

记录时间：2026-09-04。点时调查报告；运行时前后对账仍在进行。

## 新现场观察

用户在同一运行环境中关闭上游 HTTP/2、改用 HTTP/1.1 后，观察到故障明显缓解。这是单次 A/B 操作得到的强相关证据，足以保留 HTTP/1.1 作为当前运维缓解措施；由于同时段负载、上游状态和请求集合尚未逐项对齐，它还不足以单独证明每个 HTTP 408 都由 HTTP/2 产生。

## 当前代码与依赖的已确认事实

### 1. HTTP/2 graceful GOAWAY 仍会截断合法活动 stream

在当前 worktree 的依赖 `httpx2 2.12.0` / `httpcore2` 上，将仓库既有 `exp/260820-h2-goaway-poc/run_poc.py` 仅改为使用 `httpx2` / `httpcore2`，在本机 127.0.0.1 重跑。完整输出位于本会话 `$CLAUDE_JOB_DIR/tmp/h2-goaway-current/output.txt`。

- 无 GOAWAY 的 H2 控制组：HTTP 200，两段 DATA 均收到，stream 正常结束。
- `GOAWAY(NO_ERROR, last_stream_id=2**31-1)` 与后续合法 DATA 分两次 socket read 到达：第一段收到，随后抛 `httpx2.RemoteProtocolError`，第二段丢失。
- 同一 GOAWAY 与后续 DATA 在一次 socket read 到达：第一段收到，随后抛裸 `h2.exceptions.ProtocolError: Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED`，第二段丢失。
- response headers 前收到 GOAWAY：抛 `httpx2.RemoteProtocolError`。

因此 HTTP/2 路径存在当前可复现的协议处理缺陷；HTTP/1.1 没有 GOAWAY，切换后绕开这条路径不是偶然。

### 2. 每连接 stream cap 有效，但它只缩小故障半径

`upstream_transport.max_streams_per_connection` 通过 `src/app/upstream/stream_cap.py` 包装 httpcore2 pool。当前运行 `uv run pytest tests/unit/upstream/test_stream_cap.py --no-cov -q` 得到 21 passed，包括饱和队列与真实 pool 分配测试，说明 cap 没有因当前 httpcore2 私有结构变化而静默失效。

cap=1 使一条 H2 连接最多承载一个活动请求，因此能阻止单个连接事件同时打掉多条请求；它不能让这唯一一条 stream 在 graceful GOAWAY 后继续，也不能消除 H2 edge 与 H1 edge 的协议差异。故“cap 有效”与“关闭 H2 仍明显改善”并不矛盾。

### 3. HTTP 408 与 GOAWAY 是两种证据

日志 `HTTP Request: ... "HTTP/2 408 Request Timeout"` 表示 SDK 收到了完整 HTTP status 408；GOAWAY PoC 的失败是 transport exception，不会打印成 HTTP 408。当前不能把 408 重新命名为 GOAWAY。

可同时成立的链是：H2 transport/edge 更容易出现连接级终止或其他协议特有失败 → 代理无痕重试和客户端重试增加并发/负载 → 上游部分新请求明确返回 408；与此同时，响应前下游断开无人监听让被客户端放弃的旧请求继续存在。要证明这条链中的具体比例，必须对切换前后结构化 request records 和 transport exception 做时间窗对账。

## 当前处置

- 保持上游 HTTP/1.1 是有实证依据的运维缓解，当前不应为了理论上的 H2 性能重新打开。
- 响应前断开取消是独立的根因修复：无论 H1/H2，客户端离开后旧 dispatch 都必须停止；该修复正在实现。
- 不把“默认改为 HTTP/1.1”静默混入本次 patch。`ProxyConfig` schema 默认仍为 H2，而用户控制的 config example 当前显式写 `http2: false`；是否更改代码默认值是产品契约决定，需要在完成切换前后对账后单独呈交。
- 不尝试在本项目内手写 H2 状态机修补 hyper-h2/httpcore2；当前最小可控选择是使用 H1，或等待/采用上游库能通过该 wire-level PoC 的实现。

## 证据权重

- 当前 `httpx2/httpcore2` 对 graceful GOAWAY 的错误处理：本地正控＋反例重跑确认，足以据此行动。
- stream cap 当前有效：21 个当前依赖下测试确认，足以排除“cap 已完全失效”；不能证明真实请求一定配置了 cap=1。
- HTTP/1.1 改善生产表现：用户现场 A/B 观察，强到足以维持缓解；具体改善比例仍需更多同条件样本。
- 所有 408 均由 H2 引起：不成立于现有证据，禁止据此下结论。