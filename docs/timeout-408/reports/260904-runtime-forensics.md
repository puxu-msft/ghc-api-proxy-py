# 2026-09-04 HTTP 408 与长期活动请求运行时取证

记录日期：2026-09-04。

性质：只读、点时故障取证。本文记录现场证据与当时源码快照，不随实现改写。行为规格与实施状态分别由 `../../spec.md` 和 `../../status.md` 接管。

> [!IMPORTANT]
> 独立复核勘误，2026-09-04：本文正文保留调查当时的原始判断，不就地改写。第一，§5 表中两条 near-simultaneous request 的正确映射是 `1151.0s → 362cc93c-5411-41ca-b0dc-6b700c1c95cd /v1/messages`、`1148.5s → e628c955-db47-4f34-a1dd-2b030e861180 /v1/responses`；依据是 `finalized_s - TUI age` 的 monotonic residual，不是 wall registration 顺序。第二，§8.1 的已确认最小链不得包含“客户端另开 connection 发新 request”：已确认的是 pre-response disconnect 未被读取、detached request 继续 dispatch/retry、active 数超过 live H1 connections且 age 持续增长；client reissue 只是一条未闭合候选。§13 的“request accumulation 根因已闭合”仅指该 persistence 机制与现场至少 5 个 detached H1 tasks，不包括具体 request identity、disconnect 时刻或 client lineage。复核原文与处置分别见 `260904-runtime-forensics-review-general-opus.md` 和 `260904-runtime-forensics-review-disposition.md`；当前口径以 `../status.md` 为准。

## 1．结论先行

1. **已确认，强到足以据此行动：现场并不是“10 个仍有连接的正常慢请求”。** TUI 的 `5 clients` 来自 Uvicorn 当前打开的下游 TCP connection 数，`x10` 来自 active-request registry；与快照对应的 10 条 durable records 全部是下游 `H1`。当前 Uvicorn H11 protocol 在一条 connection 上只运行一个 request/response cycle，因此正常运行时 `10 active requests / 5 open connections` 意味着至少 5 个 request task 已失去原下游 connection，却仍留在 dispatch／上游重试阶段。
2. **已确认，强到足以据此行动：请求体读完后、上游 response headers 返回前没有下游断开监听。** Uvicorn `connection_lost()` 只把 `cycle.disconnected=True` 并唤醒下一次 `receive()`，不会取消 ASGI task；`_dispatch()` 在 `await request.body()` 之后不再调用 `receive()`，直到已经拿到 Response。故该窗口中的客户端断开不会取消 provider send，也不会终止 HTTP 408 retry loop。平行调查的无网络 ASGI 最小复现已做因果干预并得到同样结论；本报告只引用其结果，没有复跑或修改测试。
3. **已确认：用户摘录中的 8 条 `HTTP 408 Request Timeout` 是 GitHub Copilot upstream 返回的 HTTP response status，不是客户端本地 timeout，也不是 proxy 自己生成的 504。** Durable record 最终还记录了一条 upstream `408`，错误 code 为 `user_request_timeout`，message 为 `Timed out reading request body. Try again, or use a smaller request size.`。
4. **已确认：HTTP 408 会被 proxy 当作 `serverError` 无冷却重试，OpenAI SDK 自带重试已明确关闭。** 默认纯 408 序列是 1 次初始调用加 9 次 retry；现场最长的 direct Responses 请求记录为 14 attempts，另一个 Anthropic→Responses 请求在 proxy 的 3600 秒 client deadline 前累计 16 attempts。由于 14 大于纯 408 的默认 10 calls，这些 attempts 不可能在默认配置下全是 408，或者事故配置改写了预算；现有记录没有保留每次 attempt 的失败原因，不能把 8 条 console 408 逐条分配给 request id。
5. **已确认：TUI 的约 2988 秒与 JSONL wall-clock timestamp 看似冲突，根因是现场存在严重的 wall clock／monotonic clock 漂移。** Journal 在 01:00～03:20 记录了 279 次 `systemd-resolved: Clock change detected`；该段 wall time 前进 8377.764 秒时 monotonic time 前进 9064.186 秒，差值累计为 -686.422 秒。最老请求从 record `started_at=01:53:31.485` 到快照附近只有约 2758 秒 wall time，TUI 却显示 2988.3 秒；两者相差约 230.8 秒，和同段 journal 测得的 wall-minus-monotonic 变化 -230.784 秒一致。TUI 没有凭空泄漏条目，它在如实显示 monotonic elapsed；打印时间则在另一时钟域。
6. **证据尚不足以关闭最初 upstream body-read timeout 的物理原因。** “旧 request 在客户端离开后继续重试”已经解释 active 数积累和无用上游负载；“大量并发且可能为 MiB 级的 body 使 upstream 读 body 超时”与错误文本和邻近流量相符，但失败 attempts 没有 request-body bytes、connection id、stream id 或发送进度，不能证明是 payload size、HTTP/2 flow control、链路吞吐、upstream edge overload 中的哪一个。
7. **用户补充的 H2→H1 缓解有强运行时相关性，但还不是单变量因果实验。** 切换前最后 20 分钟有 50 条完成记录，median duration 211.871s、p95 575.645s、11 条多 attempt、1 条 408；切换后首 20 分钟有 452 条，median 18.539s、p95 52.723s、仅 1 条多 attempt、0 条 408。可是协议切换通过 restart 生效，05:10:54 同时取消并清空了旧 backlog，且两窗 workload 数量不同；因此可以确认“切换后显著缓解”，不能只凭这组观察确认 H2 是最初 408 的唯一触发条件。Pre-response disconnect 残留发生在下游 ASGI lifecycle，和 upstream 使用 H2 还是 H1 无关，关闭 H2 不会修复该机制。

## 2．目录证明与约束

用户要求第一步执行：

```bash
pwd
git -C /home/xp/src/ghc-api-proxy-py rev-parse --show-toplevel
```

Harness 在命令执行前拒绝了第二行，理由是本 agent 被固定在隔离 worktree，不能以 `git -C` 指向 shared checkout；因此该组合没有产生用户要求的 main-tree proof。随后允许执行的等价 worktree 命令输出为：

```text
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-ac9729bf778f9a537
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-ac9729bf778f9a537
```

这证明的是 agent 的隔离 worktree，不是 main checkout。后续所有被调查数据与报告目标均以用户指定的绝对根 `/home/xp/src/ghc-api-proxy-py` 访问；没有运行 main checkout 的 Git 命令，没有修改 source、Git、日志、journal、request records、配置或运行进程。

## 3．时间窗与时钟口径

- 用户重点窗：2026-09-04 02:35:10～02:39:28，Asia/Shanghai，UTC+08:00。
- 为重建请求生命周期而扩展读取：2026-09-04 01:30:00～03:10:00；请求最终状态追到 02:58:49 的批量 cancellation。
- JSONL 使用 UTC `Z` timestamp；本文统一换算为 UTC+08:00。
- TUI elapsed、proxy timeout guards 和 `duration_s` 使用 monotonic clock；console timestamp、JSONL `started_at`／`at` 和 journal human timestamp 使用 wall clock。现场两者显著漂移，不能直接相减后假定是同一时钟。
- TUI 行没有自身 timestamp，只能确定它出现在 02:39:28 console 行之后、02:40:01 第一条对应 request 完成之前。本文不为它伪造更精确的 wall-clock instant。

## 4．数据来源与完整性边界

### 4.1 一手运行记录

1. `/home/xp/.local/share/ghc-api-proxy/requests/requests-20260903.jsonl`。首次完整解析时为 5003 lines，`json.loads` parse errors 为 0；事故对应行主要为 4844～4872。文件名按 UTC day 切分，所以本地 2026-09-04 02:xx 位于 `20260903` 文件。
2. 用户传入的 console／TUI 摘录：

```text
[....] 02:35:10 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 200 OK"
[....] 02:35:20 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:35:20 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:35:20 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:35:25 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:35:25 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:35:25 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:35:25 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[....] 02:39:28 HTTP Request: POST https://api.enterprise.githubcopilot.com/responses "HTTP 408 Request Timeout"
[<-->] 5 clients | gpt-5.6-sol x10 2988.3s, 2778.6s, 2085.1s, 1721.3s, 1151.0s, 1148.5s, 808.7s, 487.7s ↓235.5KiB, 445.9s, 82.1s
```

这份摘录是用户现场 evidence，不是本报告从 journal 再找到的一份独立副本。HTTPX console line 没有 request id、connection id 或 attempt index，因此不能逐行关联。

3. System journal。Proxy 当时不是可匹配的 user systemd service，事故窗 journal 中没有 proxy console lines；journal 可独立提供 clock-change evidence。Sing-box 在 02:34:30～02:40:30 没有 unit records，不能裁决该窗具体 upstream socket 行为。

### 4.2 未找到的数据库

只读搜索 `/home/xp` 与 `/tmp` 未找到 basename 匹配 `history*.db`、`history*.sqlite` 或 `history*.sqlite3` 的文件；`/home/xp/.local/share/copilot-api` 也不存在。当前 Python service 的可用 durable request-level source 是上述 JSONL，不是 SQLite history。无命中只限于本 agent 可见文件系统和这些名字，不证明历史数据库从未存在或未被搬走。

### 4.3 源码与依赖快照

关键 on-disk SHA-256 如下。事故进程已经退出，且用户禁止 Git，因此这些 hash 锚定本轮读取内容，不证明事故进程运行的 commit 与之逐字相同；record schema、字段与当前实现一致。

```text
f91b10b94ecf02efcd5ce364dfb825024a3c48fd291ec5d407a2e2c22ceb72a3  /home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py
e62c7fe4c59ef2e2b1caa3d8c7c263c872e9dd1a2e97bfb832c6e74d654c2873  /home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py
5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a  /home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py
d7ea2f85146084b4a20b73775fd98225b66ecf0050fe9c6c1e2407403edb112c  /home/xp/src/ghc-api-proxy-py/src/app/observability/active_requests.py
621fc7b329bf7a6715cba65803e7e09fcea0c0ec48b630c71bb05599b2e548da  /home/xp/src/ghc-api-proxy-py/src/app/observability/request_completion.py
1313de1da72a7b17b2bdd7d98028ab72ee50fb64452c54867df930851a66749f  /home/xp/src/ghc-api-proxy-py/src/app/observability/footer.py
0c10c4fc79e742da96e746c06f8396ddd28a0e01004d448ebcda9f0c20c11764  /home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/uvicorn/protocols/http/h11_impl.py
```

配置读取形成两个 point-in-time snapshots。03:41:27 mtime 的版本设置 `proxy: socks5h://127.0.0.1:4000`，未写 `upstream_transport`，按 schema defaults 为 `http2=true`、`max_streams_per_connection=0`；05:10:51 mtime 的版本保留同一 proxy 并新增 `upstream_transport.http2: false`，仍未写 `max_streams_per_connection`。当前 process environment 中没有 `GHC_API_PROXY_*` override，command line 也没有 transport override；对 05:11 generation，project-side `max_streams_per_connection` 因而仍是 default 0，但 upstream 已是 H1，该 H2 stream cap 不再有作用。03:41 snapshot 晚于原始 02:35 incident，不能倒推为事故 exact config；不过 durable records 在切换前持续观测 H2、切换后持续观测 H1，足以划定后续对照窗。

## 5．TUI 十请求逐条对账

在 console 快照所在的窄区间内，JSONL 恰有 10 条 record 满足 `started_at <= snapshot-window < at`。它们全部记录 `client_protocol=H1`，resolved model 均为 `gpt-5.6-sol`，按注册先后与 TUI 从最长到最短的 age 一一对应。表内 `attempts` 是最终 durable field，不一定代表快照时 TUI 已显示的值。

| TUI age | Request id | Inbound | Wall `started_at` | 最终 `at` | 最终状态 | Recorded attempts | 关键事实 |
|---|---|---|---|---|---|---:|---|
| 2988.3s | `8a3bf009-f9e5-48d9-ab60-e19070e0f69b` | `/v1/responses`，`openai-responses` | 01:53:31.485 | 02:40:09.637 | `fail/408` | 14 | Upstream body 128 B，error code `user_request_timeout`；request bytes 未记录。 |
| 2778.6s | `f93505c8-f22e-473f-9e97-24f22c45a8cb` | `/v1/messages`，`anthropic-messages` | 01:56:46.432 | 02:52:08.410 | `fail/504` | 16 | Proxy `client_request_deadline=3600s`；downstream error body 108 B 的 ASGI send 返回。 |
| 2085.1s | `02bf8e91-dd43-4aed-8c2e-b9464572ded4` | `/v1/messages` | 02:07:27.159 | 02:58:49.736 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |
| 1721.3s | `69e934ec-d092-460e-beb1-bc9146671b35` | `/v1/messages` | 02:13:02.715 | 02:58:49.589 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |
| 1151.0s | `e628c955-db47-4f34-a1dd-2b030e861180` | `/v1/responses` | 02:21:49.767 | 02:58:49.729 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |
| 1148.5s | `362cc93c-5411-41ca-b0dc-6b700c1c95cd` | `/v1/messages` | 02:21:49.795 | 02:58:49.712 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |
| 808.7s | `e8c7c1fc-fa26-47fa-b1ea-33534e44c303` | `/v1/messages` | 02:27:04.812 | 02:58:49.760 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |
| 487.7s，`↓235.5KiB` | `a5ed41a0-3128-4998-a3a6-2707ad1423b0` | `/v1/messages` | 02:32:01.053 | 02:40:01.321 | `ok/200` | 1 | 唯一已有 upstream body progress 的快照项；最终 request body 248672 B、response body 346140 B。 |
| 445.9s | `5d11b559-a7f5-4194-940c-873ff0df6f8b` | `/v1/messages` | 02:32:40.351 | 02:58:49.744 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |
| 82.1s | `9faf8ca8-0992-497e-991e-fd0ccf30578a` | `/v1/messages` | 02:38:14.312 | 02:58:49.704 | `gone/None` | 1* | Dispatch `CancelledError`，response 未开始。 |

`1*` 不是“确认只发了一次 upstream call”。`RequestTrace.attempts` 默认是 1；当前 route 只在 `handle_bounded()` 正常返回或转换为普通 `Exception` 后把 `context.attempt_count` 写回 trace。02:58:49 的 `CancelledError` 直接越过这段写回逻辑，由 outer completion path 记录，因此这些 cancellation records 的 attempts 是 stale default。快照 TUI 中也没有任何 `(N)` retry suffix，而最老请求最终明确为 14 attempts，证明 response-header 阶段的 live attempt 数没有及时投影到 registry。

这 10 条最终形成：1 条 upstream 408、1 条 proxy 504、1 条正常 200，以及 7 条 02:58:49 batch cancellation。所有 request 都有 durable final record；当前 sink 顺序会在写 JSONL 前调用 `active_requests.complete()`，但没有第二张 TUI snapshot 独立证明每次 UI removal 的具体刷新时刻。

## 6．请求级时间线

### 6.1 事故前积累

- 01:53:31.485 wall：direct `/v1/responses` request `8a3bf009-…` 注册。TUI 到事故快照显示 2988.3s；它最终累计 14 proxy-level attempts。
- 01:56:46.432 wall：`/v1/messages` request `f93505c8-…` 注册并路由到 Responses model；最终累计 16 attempts。
- 02:07:27～02:38:14 wall：另外 8 条快照 request 陆续注册。快照时只有 `a5ed41a0-…` 已显示 upstream response-body progress。
- 02:19:25 与 02:21:49：在快照前已有两条长请求最终记为 `gone/200`，分别累计 2 与 4 attempts；其中 `16b5654c-…` 的上游 request body 为 3092223 B，ASGI HTTP start 已返回但 downstream body 为 0，随后 delivery cancellation。这证明事故前已经存在“旧长请求最终发现下游不再消费”的实例。

### 6.2 用户重点窗

- 02:35:10：至少一个 `/responses` attempt 收到 upstream 200。由于 HTTPX line 无 request id，不能确认就是后来成功的 `a5ed41a0-…`，虽然时序相容。
- 02:35:20：3 个 `/responses` attempts 收到 upstream 408。
- 02:35:25：4 个 `/responses` attempts 收到 upstream 408。
- 02:39:28：1 个 `/responses` attempt 收到 upstream 408。
- 紧接着的 TUI：5 个 open downstream connections、10 个 active requests。所有 10 条对应 records 均为 H1，所以至少 5 条 active request 已没有 open downstream connection。该结论不要求知道是哪 5 条。

### 6.3 后果与终止

- 02:40:01.321：`a5ed41a0-…` 完成 `ok/200`。这证伪“整个 proxy、event loop 或 GitHub endpoint 在事故窗完全失联”。
- 02:40:09.637：`8a3bf009-…` 在 14 attempts 后形成 final `408` record。其 observed upstream JSON error 是 `user_request_timeout`；ASGI start/body send 均返回，记录为 `delivery.state=accepted`。
- 02:40:09.960：新 direct `/v1/responses` request `562707ba-…` 注册，仅比 final 408 record 晚约 323ms。相同 inbound path、model 与紧邻时序使它成为高可信的 client-level retry candidate，但记录没有 downstream connection id、request body hash 或 logical operation id，因此不能证明它一定是同一逻辑调用的 retry。
- 02:52:08.410：`f93505c8-…` 被 proxy 自己的 3600 monotonic-second client deadline 终止为 HTTP 504，不是 upstream 408。它的 wall timestamps 只跨了约 3321.978 秒；约 278 秒差额由同段 clock drift 解释。
- 02:58:49.589～02:58:49.799：13 条 request 在 210ms 内全部以 `failure.category=cancelled`、`origin=dispatch`、`delivery.state=not_started` 完成。快照中的剩余 7 条都在此批次。如此同步的 cancellation 强烈指向 server generation shutdown／restart 或同等级的 process-wide task cancellation，不像 13 个独立 client 在 210ms 内自行超时；journal 没有保存控制动作，所以触发者仍未知。02:59:04 起出现新 requests，与快速新 generation 相容，但不能仅凭 JSONL 证明启动命令。

## 7．必须分开的五类事件

### 7.1 Upstream HTTP 408 response

HTTPX console 的 `HTTP 408 Request Timeout` 和 record 中的 `status_code=408` 都是 GitHub Copilot 返回 headers/body 后的 HTTP status。错误 code `user_request_timeout` 明确指向 upstream 没能及时读完 request body。它发生在 downstream streaming Response 建立前；已发送 200 的同一个 HTTP response 不可能中途改成 408。

### 7.2 Proxy whole-client timeout

`f93505c8-…` 的 `504` 来自本项目 `client_request_deadline=3600`，跨多次 attempts 共用一个 monotonic deadline。它是 proxy-generated HTTP 504，和 GitHub 408 的来源、预算与错误 body 都不同。

### 7.3 Proxy-level retry

当前代码将 408 规范化为 retryable `UpstreamError(status_code=408)`，reason 为 `serverError`；OpenAI SDK 构造为 `max_retries=0`。默认 `serverError.max_retries=9`、`max_total=20`，408 不触发只覆盖 429／502 的 reactive limiter，funded retry 没有 sleep／jitter，直接进入下一 attempt。Console 的每条 408 因此对应一个真实 upstream response，不是 SDK 在下面偷偷多打一层；但它属于哪个 inbound request，console 没写。

### 7.4 Client-level timeout／retry／disconnect

现场没有客户端自己的 timeout exception log，故不能把 connection loss 的原因定性为自动 timeout、用户 Esc、client process exit 或其他 cancellation。能确认的是：快照至少有 5 条 H1 request 已脱离 open connection，却仍在 proxy 执行；02:40:09.960 的新 `/v1/responses` 是强 retry candidate。客户端断开在 pre-response 窗口不被应用读取，是旧 task 留存的已确认机制。

还要限定 `delivery.state=accepted`：当前 Uvicorn 0.52.4 的 `send()` 在 `self.disconnected` 时直接 `return`，应用 wrapper 会把这个 no-op return 当成 send returned。因此 final 408 record 证明 proxy 形成并尝试发送完整 408 response，**不独立证明客户端 socket 实际收到了 128 B body**。也正因此，紧邻的新 request 可能是“收到 408 后 retry”，也可能是“客户端先 timeout／disconnect 后自己 retry”。

### 7.5 Request completion／removal

正常 200、最终 408、proxy 504、stream delivery cancellation 和 batch cancellation 都会进入 `RequestCompletionCoordinator.publish()`；当前 sink 顺序先 `active_requests.complete(request_id, record)`，再写 durable JSONL 和 console line。`complete()` 在同一 lock 中从 live map pop 并追加 completed deque。TUI 长项不是定时 reaped；它们只有在真实 lifecycle settle／publish 后才被移除。

## 8．根因候选、证伪条件与证据强度

| 候选 | 当前判定 | 支持证据 | 能证伪／关闭它的缺失证据 |
|---|---|---|---|
| A．响应前客户端断开无人读取，旧 request 继续执行和重试 | **已确认，强到足以据此行动；这是 active 积累的最早可控偏差。** | 10 条对应 record 全为 H1，只有 5 open connections；Uvicorn H11 每 connection 一个 active cycle；`connection_lost()` 不 cancel task；`_dispatch()` body 之后无 receive；平行最小复现观测 disconnect 已可读时 app／provider／active slot 均不结束，手工 cancel 后三者立即结束。 | 在同一 on-disk stack 下，给 pre-header request 发送真实 `http.disconnect` 后若 provider 被立即取消且 registry 清空，就能推翻；现有平行 PoC 得到相反结果。 |
| B．408 的无冷却 retry 放大 orphan request 的无用上游负载 | **已确认的放大机制，不是第一条 408 的充分原因。** | 408＝`serverError` retry；SDK retry 0；默认最多 10 calls；408 不触发 limiter；现场 8 条 408 密集到 5 秒内 7 条，且 final records 有 14／16 attempts。 | 若事故配置将 serverError retry 设为 0，或 per-attempt trace 证明这些 408 后没有新 attempt，则该现场归因会失败；事故配置与 per-attempt trace 均未保存。 |
| C．MiB 级 body 与并发 upload 使 upstream body-read deadline 到期 | **高可信候选，但不足以封为根因。** | Upstream 自己返回 `user_request_timeout` 并建议 smaller request；01:30～02:45 的 98 条 records 中 97 条有 request bytes，总计 148660640 B，已知最大单条 3092223 B；事故前存在两条相同 3092223 B 的重叠请求；快照有 10 active。 | 为每个 attempt 持久化 serialized request bytes／Content-Length、upload progress 与 upstream response timestamp。当前 final 408 的 `bytes_in=None` 是未知，不是 0；所以不能比较失败 body 与成功 3.09 MiB body。 |
| D．共享 HTTP/2 connection／flow-control 或网络链路 stalls upload | **切换后缓解已确认；H2 作为唯一触发条件仍未确认。** | 切换前 records 为 H2，project cap 默认为 0；最后 20 分钟 median／p95 duration 为 211.871／575.645s，11 条多 attempt、1 条 408。切换后首 20 分钟 records 为 H1，median／p95 为 18.539／52.723s，1 条多 attempt、0 条 408。 | 该切换和 restart 清 backlog 同时发生，且 workload 分母不同；失败 attempts 也缺 local／peer／stream id、DATA bytes sent、flow-control window 与 socket write latency。需要相同 body／并发条件的 H2/H1 对照或 per-attempt transport telemetry，才能在 H2、链路与 upstream edge 之间裁决。 |
| E．本机 clock anomaly 直接制造 GitHub HTTP 408 | **作为 408 唯一根因已证伪；作为 elapsed／本地 deadline 异常的根因已确认。** | 279 次 clock-change 与 wall／monotonic 差额完整解释 TUI age 和 3600s record；但 408 是 remote 返回且带 remote application error body。 | 若能证明 upstream 实际从本机 clock 得到 request-read deadline 才能恢复该归因；当前协议没有这种 evidence。Clock anomaly 仍可能改变本地 SDK／proxy timeout 到点时刻，但那类失败是 local timeout，不是已观察到的 HTTP 408。 |
| F．GitHub endpoint 全面 outage／认证失败／固定 payload-size 拒绝 | **不支持，部分被反例削弱。** | 同窗有 200，`a5ed41a0-…` 在 02:40:01 成功；无 401／429／5xx；成功 request body 达 3092223 B。Observed error 是读 body 超时而不是固定 size-limit status。 | Upstream incident telemetry 或同 body 在独立连接上的 controlled replay；本轮禁止真实请求，未执行。 |
| G．Active registry 自己漏 remove，只有 UI 假象 | **已推翻。** | 项目已有可逆 PoC：手工取消 server task 后 active slot 归零且 provider 收到取消；durable final records 也与 `complete()` sink 对齐。 | 若出现已 publish final record 但同 request id 仍在同一 registry snapshot，才会重新打开；本轮没有这种 evidence。 |

### 8.1 最小因果链

目前足以成立的最窄链条是：

> 客户端 connection 在 upstream headers 前消失 → Uvicorn 只标记 disconnect，应用没有再次读 receive → 原 dispatch 未被取消并继续 send／retry → 客户端另开 connection 发新 request → active request 数超过 live H1 connections，旧 requests 的 age 持续增长 → 408 无冷却 retry 继续消耗 upstream calls。

从“更多并发 upload”到“GitHub 因此读 body 超时”的最后一跳高度合理，但缺少 failed-attempt upload telemetry，仍是候选而非闭环。因此本报告不会把“payload 太大”“H2 坏了”或“网络慢”其中任何一个写成已确认 root cause。

## 9．Clock anomaly 专项

关键 journal query 以 `__REALTIME_TIMESTAMP` 和 `__MONOTONIC_TIMESTAMP` 成对计算，而不是从人类可读 timestamp 猜测：

- 01:00～03:20：279 个 `Clock change detected` events。
- 第一条到最后一条：wall delta 8377.763924s，monotonic delta 9064.186112s，`wall - monotonic` 累计变化 -686.422188s。
- 靠近最老 request 到 TUI snapshot 的区间：wall 约 2782.718s，monotonic 约 3013.502s，差 -230.784s。
- 靠近第二条 request 到 504 的区间：wall 约 3318.701s，monotonic 约 3594.249s，差 -275.548s；request record 自身的 `duration_s=3600.006864` 与 wall timestamps 差约 278.029s。
- 02:35:13.824～02:39:41.742：wall 267.918s，monotonic 290.251s，差 -22.333s。

结论强度：**已确认存在并已确认解释两个 observability／deadline 现象；setter 与底层原因未决。** Journal 的 producer 是 `systemd-resolved`，它只报告检测到 clock change，并不证明是它改钟。Systemd-timesyncd 在窗口内无 unit entries；当前 `timedatectl` 显示 `NTPSynchronized=yes`、`Timezone=Asia/Shanghai`。平台是 WSL2，但现有 records 不足以把 setter 指定为 Windows host、WSL clocksource 或某个用户进程。

## 10．用户补充后的 H2→H1 运行时对照

### 10.1 切换边界与 effective cap

- 03:41:27 config snapshot：有同一 SOCKS proxy，无 `upstream_transport` block；当前 schema defaults 为 `http2=true`、`max_streams_per_connection=0`。这里的 0 明确定义为 project-side unlimited，并不覆盖 upstream 自己发布的并发上限。
- 05:09:20：当前可见 replacement process 以 `ghc-api-proxy start --port 4141 --restart` 启动。
- 05:10:51：config mtime 更新，新增 `upstream_transport.http2: false`，未设置 `max_streams_per_connection`。
- 05:10:54：旧 generation 在约 0.1 秒内批量取消 12 条尚未回答的 request，并有 1 条 H2 `gone/200` 收尾。这既是协议切换边界，也是 backlog 清空边界。
- 05:11:00：pidfile mtime 更新；05:11:08.704 出现第一条 final `upstream_protocol=H1` record。之后固定对照窗内不再出现 H2。
- 当前 replacement process 的 `/proc/<pid>/environ` 无 `GHC_API_PROXY_*`，command line 无 transport override。因此 H1 generation 的 effective project config 是 `http2=false`、`max_streams_per_connection=0`；后者在 H1 下无 stream-multiplexing object 可限制，实际效果为不适用。旧 generation 已退出，无法读其 `/proc`；03:41 config snapshot 和 H2 records 支持其使用 default cap 0，但不能排除当时存在未保存的环境覆盖。

### 10.2 等长 20 分钟对照

两个窗口都按 final record 的 wall `at` 选取。由于 clock anomaly，duration 使用 record 的 monotonic `duration_s`，吞吐量只作现场相关性，不作严格 benchmark。

| 指标 | H2 切换前：04:50:54～05:10:54 | H1 切换后：05:11:00～05:31:00 |
|---|---:|---:|
| Final records | 50 | 452 |
| Protocol field | 48 H2，2 unknown／not-applicable | 444 H1，8 unknown／not-applicable |
| `ok/200` | 42 | 451 |
| `gone/200` | 5 | 1 |
| `retry/200` | 1 | 0 |
| `fail/408` | 1 | 0 |
| `fail/502` | 1 | 0 |
| Duration median | 211.871s | 18.539s |
| Duration p90 | 553.209s | 45.600s |
| Duration p95 | 575.645s | 52.723s |
| Duration max | 581.684s | 207.246s |
| Duration `>=300s` | 8 | 0 |
| Attempts mean | 2.120 | 1.004 |
| Attempts max | 12 | 3 |
| Records with attempts `>1` | 11 | 1 |

切换前这 1 条 final 408 是 `b604c3b1-21b9-4f17-b114-db39965c9ecb`，04:54:48.850 完成，duration 224.412s、attempts 1、错误仍为 `Timed out reading request body`。H1 窗没有 final 408。该结果强力支持用户的“缓解很多”观察，而且改善同时出现在 status、duration 与 retry count，不只是吞吐量一个 proxy metric。

### 10.3 GOAWAY／ProtocolError／WriteError

对当前 JSONL 全文件的 `detail`、`tore_after_terminal` 和 `replaced_failures` 搜索，在原始 02:35 incident、03:42～05:10 H2 generation 和 H1 对照窗都没有 retained `GOAWAY` 或 `ProtocolError`。全文件只有 1 条 `RemoteProtocolError('<StreamReset stream_id:49, error_code:8, remote_reset:True>')`，发生在 2026-09-03 16:22:44，既不在本次事故也不在切换窗；它是 stream reset，不是 retained GOAWAY。H2 期间 retained `WriteError('')` 有 3 条，分别在 02:24:51、02:32:00 和 05:05:58；H1 首 20 分钟为 0。

这个“0 GOAWAY／0 ProtocolError”只适用于 durable request fields。Header-stage retries 的每次 `attempt.error` 没有逐次写入 JSONL，console 原始 stderr 又未持久化，所以它不能升级为“运行时绝不曾发生 GOAWAY”。能确认的是：现有 evidence 没有把本次 408 关联到 GOAWAY；408 本身是完整 HTTP status＋application error body，不是 H2 protocol exception。

### 10.4 因果限定

- **H2-specific 候选仍然成立但未闭合。** H2 multiplexing、connection／stream flow-control 或 shared connection failure 都能使多个大 body upload 互相影响；H1 为每个 request 使用独立 connection，确实改变该触发面。切换后 duration、retry 与 408 同时显著下降，是强相关证据。
- **restart 是不可忽略的混淆变量。** H1 生效前旧 generation 同时取消 backlog；前 20 分钟 H1 从 clean state 开始，H2 前 20 分钟则包含已经积累的 orphan work。不能把 backlog 清空带来的收益全部归给 protocol。
- **workload 不是受控分母。** H1 窗完成 452 条，H2 窗完成 50 条；这本身说明系统状态大幅不同，也说明不是相同 body／并发序列的 A/B。请求 mix、client state 与 payload size 没有被固定。
- **pre-response disconnect root cause 与 upstream protocol 正交。** 下游 records 是 H1，缺陷发生在 ASGI receive lifecycle；把 upstream 从 H2 改为 H1 不会让 `_dispatch()` 开始读取 `http.disconnect`。H1 可以降低上游共享连接的故障半径或改善 upload，但客户端离开后旧 task 仍会残留，直至 response、deadline、shutdown 或实现修复。

结论强度：**“H1 切换后显著缓解”已确认，足以把它称为现场 mitigation；“H2 单独导致 408”只是一条强倾向，尚不足以据此关闭 root-cause investigation。** 要确认 H2 触发条件，需要在不带旧 backlog 的 clean generations 上固定 request bodies、并发和 proxy route，比较 per-attempt upload progress 与 response；本轮按用户禁令没有发真实 upstream request。

## 11．未知项与后续可证伪观测

1. 8 条摘录 408 分别属于哪些 request ids、哪些 attempt indexes。需要在 HTTPX request hook／driver attempt log 上同时记录 proxy request id 与 attempt index；当前 console line 没有关联键。
2. Final 408 attempt 的 serialized request size、Content-Length、实际送达 bytes 与 upload stall 位置。`bytes_in=None` 是 instrumentation absence。
3. 哪 5 条快照 request 已失去 connection，以及每条下游 disconnect 的时刻与原因。需要 durable downstream connection id／peer、disconnect timestamp 和 reason；仅 connection cardinality 无法逐条配对。
4. `562707ba-…` 是否为 `8a3bf009-…` 的同逻辑 retry。需要 client operation id 或 body hash；323ms 邻接只能给高可信候选。
5. 02:58:49 batch cancellation 的控制来源。需要保存 shutdown／signal line、PID generation 或 supervisor journal。现有同步性支持 generation switch，但不裁决是 Ctrl-C、signal、restart command 还是其他全局 cancellation。
6. 事故进程的 exact config／commit。当前 config mtime 晚于事故，事故进程已退出，用户禁止 Git；不得用当前 SOCKS setting 或当前 HEAD 反写历史。
7. Clock changes 的 setter 和物理时钟真值。需要 host／guest 双侧 clock telemetry；`systemd-resolved` detection 不是 setter provenance。
8. 下游实际是否收到 final 408／504 body。ASGI send return 在当前 Uvicorn disconnect 分支可为 no-op；需要 socket-level delivery acknowledgement 或 client log。
9. H2 mitigation 的独立效应。当前 before／after 同时改变 protocol、process generation、backlog 和 workload；需要 clean-generation fixed-workload 对照。旧 generation 的 effective `max_streams_per_connection=0` 由 config snapshot＋schema default 支持，但其 process environment 已不可读，不能声称已排除所有 override。

## 12．执行命令记录

以下为关键只读命令；Python snippets 均只逐行 `json.loads`、筛选和打印，没有打开写模式。

```bash
pwd
git -C /home/xp/src/ghc-api-proxy-py rev-parse --show-toplevel
```

结果：被 harness 拒绝，未执行 main-tree Git。随后只在隔离 worktree 执行 `pwd && git rev-parse --show-toplevel` 取得第 2 节结果。

```bash
fd --hidden --no-ignore --max-depth 3 --absolute-path . /home/xp/.local/share/ghc-api-proxy --exec-batch stat --printf='%F\t%s\t%y\t%n\n'
fd --hidden --no-ignore --type f --absolute-path '^history.*\.(db|sqlite|sqlite3)(-(wal|shm))?$' /home/xp /tmp
```

```bash
python - <<'PY'
# 逐行解析 /home/xp/.local/share/ghc-api-proxy/requests/requests-20260903.jsonl；验证 5003 行、0 parse errors；以 at／started_at 筛选 2026-09-03T17:30:00Z～19:00:00Z；输出 request_id、status、status_code、attempts、duration、bytes、delivery observation。
PY
```

```bash
journalctl --user --since '2026-09-04 01:45:00' --until '2026-09-04 03:05:00' --no-pager --output=short-iso-precise
journalctl --since '2026-09-04 01:45:00' --until '2026-09-04 03:10:00' --no-pager --output=short-iso-precise
journalctl -u sing-box --since '2026-09-04 02:34:30' --until '2026-09-04 02:40:30' --no-pager --output=short-iso-precise
```

```bash
journalctl --since '2026-09-04 01:00:00' --until '2026-09-04 03:20:00' --no-pager --output=json | python -c '... compare __REALTIME_TIMESTAMP with __MONOTONIC_TIMESTAMP for MESSAGE containing Clock change detected ...'
```

```bash
ss --tcp --listening --processes --numeric | rg ':(4141|4142)\b'
ps -o pid=,ppid=,lstart=,etime=,stat=,args= -p 273832,273835
```

该 process／listener 查询发生在 03:42 后，只用于确认调查时已经是 03:41:43 启动的新 generation；没有拿它冒充事故进程。

```bash
rg -n --hidden --glob '!src/.archived/**' -e '408|user_request_timeout|RetryLedger|attempts|connection_count' /home/xp/src/ghc-api-proxy-py/src/app
sha256sum /home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py /home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py /home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py /home/xp/src/ghc-api-proxy-py/src/app/observability/active_requests.py /home/xp/src/ghc-api-proxy-py/src/app/observability/request_completion.py /home/xp/src/ghc-api-proxy-py/src/app/observability/footer.py /home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/uvicorn/protocols/http/h11_impl.py
```

用户补充 H2→H1 后新增的只读命令：

```bash
stat --printf='%y\t%s\t%n\n' /home/xp/.local/share/ghc-api-proxy/config.yaml /home/xp/.local/share/ghc-api-proxy/standalone-4141.pid
ps -o pid=,ppid=,lstart=,etime=,stat=,args= -C ghc-api-proxy
tr '\0' '\n' < /proc/303153/environ | rg '^GHC_API_PROXY_'
```

```bash
python - <<'PY'
# 按 final at 选择 H2 04:50:54～05:10:54 与 H1 05:11:00～05:31:00 两个等长窗口；统计 protocol、status、duration median/p90/p95/max、>=300s、attempts mean/max/>1，并搜索 GOAWAY／ProtocolError／RemoteProtocolError／WriteError。
PY
```

## 13．总体判定

事故可拆成两个已经闭合的本地机制和一个尚未闭合的远端物理原因：

- **本地 request accumulation 根因已闭合：** pre-response disconnect 不被读取，离开的 H1 client 留下继续执行／retry 的 dispatch task。
- **本地 amplification 已闭合：** upstream 408 被无冷却透明 retry，且 live attempt count 在该阶段没有及时显示；这使 orphan work 更昂贵、更难从 TUI 辨认。
- **远端 `Timed out reading request body` 的底层原因未闭合：** concurrency／large body 很可疑，但缺少 per-attempt upload telemetry，不能在 payload、H2 flow control、网络或 upstream edge 之间裁决。
- **H2→H1 mitigation 的现场效果已确认：** 等长首尾窗口中 final 408 从 1 降为 0，p95 duration 从 575.645s 降为 52.723s，多-attempt records 从 11 降为 1；但 restart 同时清掉 backlog，且无 retained GOAWAY／ProtocolError，所以不能把 H2 写成唯一 root cause。Pre-response disconnect 残留是协议无关的另一条机制，仍必须单独关闭。

Clock anomaly 是独立且确定的运行时问题：它完整解释 TUI age 与 wall timestamp／504 到点差异，但不能替 GitHub 自己返回的 HTTP 408 充当根因。

本轮没有重启、停止或 signal 任何进程，没有发真实 upstream request，没有修改 source、Git、配置或任何被调查数据；唯一 project-tree 写入是用户指定的本报告文件。由于 isolation 阻止 `Write` 直接指向 main-tree `.dev`，先生成了 `/tmp/260904-runtime-forensics.md` staging copy，再复制到报告目标。