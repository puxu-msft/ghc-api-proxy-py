---
report_id: timeout-408-reference-timeout-semantics
attempt_id: 260904-reference-timeout-semantics-agent-a84eca8930b314af5
status: in-review
reviewed_at_rev: "2026-09-04 on-disk snapshot，关键文件 SHA-256 见附录；按用户要求未操作 Git"
reviewed_project: /home/xp/src/ghc-api-proxy-py
requested_references:
  - /home/xp/src/copilot-api-js
  - /home/xp/src/refs/vscode-copilot-chat
network_used: false
---

# OpenAI Responses 上游 HTTP 408 语义调查

## 1．结论范围与证据权重

本报告完整调查了当前 Python 项目在本地可读源码与已安装运行库下的行为。结论锚定于 2026-09-04 的 on-disk snapshot，而不是未读取的提交号；用户要求不操作 Git，因此本次没有查询主工作树的 Git revision。

前身 `/home/xp/src/copilot-api-js` 与官方参考 `/home/xp/src/refs/vscode-copilot-chat` 没有在此 remote-isolated agent 的文件系统视图中挂载。第一步用绝对路径逐项核对时，主项目返回存在，两个参考目录的 `test -d` 均返回 1，`Read` 也返回 `File does not exist`。这只证明“本 agent 看不到”，不证明宿主机上目录不存在。CodeGraph 也无法查询两者，因为对应路径没有可见的 `.codegraph/` index。协调方随后确认这是 isolation 可见性限制，并明确要求继续完成 Python 调查、把两份参考比对列为未执行。故本报告不猜测前身或官方实现，更不把项目注释中对它们的转述当作参考实现事实。

证据分四档：

1. **当前源码事实，足以据此行动。** 直接读取 `/home/xp/src/ghc-api-proxy-py` 的绝对路径源码，并以附录 SHA-256 锚定关键文件内容。
2. **本地测得事实，足以据此行动但仅适用于列明版本。** 在无网络的 `httpx2.MockTransport` 或纯内存 fake 上运行探针；版本为 OpenAI SDK 3.3.1、httpx2 2.12.0、Starlette 1.6.0、Uvicorn 0.52.4、AnyIO 4.14.2。
3. **项目内注释或 Spec 的解释，只作语义背景。** 行为结论仍由当前源码与探针支撑，没有把注释中的历史测量冒充本轮重测。
4. **前身与官方参考，未决。** 没有源文件可读，不能给出分类、次数、退避、时限或取消语义差异。

## 2．当前 Python 行为总览

| 维度 | 当前 Python 项目行为 | 证据强度 |
|---|---|---|
| HTTP 408 分类 | OpenAI SDK 的 `APIStatusError(status=408)` 被正规化为保留 `status_code=408` 的 `UpstreamError`，pipeline disposition 为 `RETRY`，预算原因是 `serverError`，不是 `network`，也不是本地 `UpstreamTimeout`。 | 已确认：源码＋本地探针。 |
| SDK 自带重试 | OpenAI SDK 构造时显式 `max_retries=0`；408 重试完全由本项目的 `DirectDriver` 与 `RetryLedger` 驱动。 | 已确认：源码＋实例属性探针。 |
| 默认次数 | `serverError.max_retries=9`，共享 `max_total=20`。纯 408 序列因此是 1 次初始尝试＋9 次 retry，共 10 次上游调用；第 10 个 408 终止。 | 已确认：源码＋纯内存 driver 探针测得 `provider_calls=10`、`ledger_total_spent=9`。 |
| 退避 | 没有 408 专属 sleep、指数退避或 jitter；获准后直接进入下一轮。`Retry-After` 在 408 上不参与调度。 | 已确认：控制流与 rate limiter 状态机。 |
| 可继承等待 | provider-wide rate limiter 只由 429 或 502 进入 limited mode，但一个 408 retry 若碰到该 provider 已有的 limited/proactive pacing 状态，下一轮 `acquire()` 仍可能等待；这不是 408 产生的退避。 | 已确认：源码；条件式结论。 |
| 默认时限 | SDK 单次请求实际 timeout extension 为 connect 5 秒、read/write/pool 各 600 秒；项目 `response_header=0` 与 `stream_idle=0` 默认关闭，`upstream_request_deadline=1200` 秒每次 attempt 重置，`client_request_deadline=3600` 秒跨所有 attempts 共用。 | 已确认：源码＋本地请求构造探针。 |
| 总时限 | 对已读完请求体并进入 model pipeline 的默认请求，所有 408 attempts 合计受同一个 3600 秒 client deadline 限制；没有固定退避要额外相加。请求体读取本身只先计算 deadline instant，却没有在读取期间开启 timeout scope，故一个永不结束的请求体仍可越过该时点；这不改变正常已完成请求体的 408 路径。 | 已确认：源码；限定适用范围。 |
| 流开始前 | 即使请求指定 `stream=true`，OpenAI SDK 在返回 streaming `Response` 之前就对 HTTP 408 抛 `APIStatusError`。项目可完成全部 10 次 attempt，而 downstream 还没有收到 SSE 200；耗尽后返回普通 HTTP error response。 | 已确认：SDK mock 探针＋route 控制流。 |
| 流开始后 | 一条已经以 HTTP 200 开始的 SSE 流不可能随后把同一 HTTP response 的 status 改成 408；此后出现的是 body tear、timeout exception 或 SSE failure event，不应再称为“上游返回 HTTP 408”。在 body tear 场景，尚未交付完整 semantic block 时可透明 replay；已经交付至少一个完整 block 后不再 replay，转为 client hand-over（适用时）或 error frame。 | 已确认：HTTP/ASGI 边界与 delivery 状态机；不是对 408 的外推。 |
| 客户端断开 | 请求体读取时的 `ClientDisconnect` 会传播。请求体完成后至 upstream headers 返回前，没有并发读取 `http.disconnect` 的监听者，Uvicorn 也只入队断开而不取消 ASGI task，因此重试不会因该断开自动停止。进入 production SSE response 后，Uvicorn 声明 ASGI 2.3，Starlette 启动 disconnect listener；断开会取消 delivery，取消不被当作 upstream tear，也不重试，cleanup 会取消 pending pull、关闭 iterator 与 upstream response。 | 已确认：应用源码＋已安装 Starlette/Uvicorn 源码＋现有 integration tests。 |

## 3．逐项发现

### T408-01：408 是可重试的 `serverError`，不是 transport timeout

- `conclusion_strength: confirmed`
- `question:` 当前 Python 如何分类 OpenAI Responses 上游 HTTP 408？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:31-36,140-185`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/exceptions.py:24-54,131-144`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:36-58`。
- `quote/measurement:` `RETRYABLE_STATUSES` 显式包含 408；408 不进入 `UpstreamRejected` 分支，而成为 `UpstreamError(status_code=408)`。`reason_for()` 对已知非 401、非 `>=500`、有 status 的 retryable `UpstreamError` 落到 `SERVER_ERROR`。本地探针输出为 `normalized_type=UpstreamError`、`classification=retry`、`retry_reason=serverError`。
- `confidence:` 高。结论直接由常量、分支与运行输出共同支撑。

这里必须区分两种“timeout”：上游真的回 HTTP 408 时保留 408 并走 `serverError` budget；SDK `APITimeoutError` 或项目 timeout guard 则成为 `UpstreamTimeout`，走 `network` budget，最终是 proxy 生成的 HTTP 504。把二者合并会误判预算、客户端 status 与错误来源。

### T408-02：默认是 10 次总调用，SDK 不额外叠加重试

- `conclusion_strength: confirmed`
- `question:` 重试次数是多少，是否存在双层重试？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:422-448`；`/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:144-162`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:61-96`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:136-159,220-242`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:73-80,174-190`。
- `quote/measurement:` SDK 构造明确写 `max_retries=0`。默认 `serverError.max_retries=9`，`max_total=20`。driver 每次失败只在 budget `take()` 成功后 `continue`，初始 attempt 不计入 `total_spent`。纯内存 408 探针测得 `provider_calls=10`、`context_attempts=10`、`ledger_total_spent=9`、`ledger_per_reason={'serverError': 9}`，终态为携带最后一个 `UpstreamError` cause 的 `PipelineAbort`。
- `confidence:` 高。

`max_total=20` 是整个 client request 跨原因共享的 retry 次数，不是 attempts 总数；同一 `RetryLedger` 保存在 `RequestContext` 上并被 header 阶段 retry 与 body replay 共用。纯 408 先撞上 `serverError=9`，不会用完 `max_total=20`。

### T408-03：408 没有自身退避，且它的 `Retry-After` 不控制重试等待

- `conclusion_strength: confirmed`
- `question:` 重试前如何退避？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:136-159,220-242`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/rate_limiting.py:1-24,98-175`；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:61-72,149-181`。
- `quote/measurement:` funded failure 从 `_handle_failure()` 返回 `True` 后，`run()` 直接 `continue`；该 retry loop 内没有 sleep。Reactive rate limiter 的 `REACTIVE_STATUSES=frozenset({429, 502})`，408 在 `observe_failure()` 第一个 status gate 就返回 `False`。只有 status 429 被正规化为带 parsed `retry_after` 的 `UpstreamRateLimit`。
- `confidence:` 高。

因此，408 response 自己携带的 `Retry-After` 会保存在 headers 中并可在最终失败时转发给 downstream，但本 proxy 不按它等待。条件式例外是 provider 的 rate limiter 可能早已由其他 429/502 置为 limited，或成功 response 的 proactive headers 已设置 pacing；下一 attempt 的通用 `acquire()` 会遵守既有 `_next_allowed`，但不能把这写成“408 退避”。

### T408-04：默认总时限由四层时钟共同决定，但只有 client deadline 跨 attempts

- `conclusion_strength: confirmed`
- `question:` 单次与总请求有何时限？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:135-141,236-255`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:136-153,244-283`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:174-190,392-418`；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:196-210,352-371,421-488,503-569,593-633`；`/home/xp/src/ghc-api-proxy-py/src/app/streaming/deadline.py:1-77`。
- `quote/measurement:` defaults 是 `response_header=0`、`stream_idle=0`、`upstream_request_deadline=1200`、`client_request_deadline=3600`。每个 `begin_attempt()` 都重算 `deadline_at=now+1200`；client deadline 在 route 开始时只算一次并传给所有 replay。OpenAI SDK 3.3.1＋httpx2 2.12.0 的无网络探针观测实际 request extension 为 `{'connect': 5.0, 'read': 600, 'write': 600, 'pool': 600}`，SDK `max_retries=0`。
- `confidence:` 高，但 SDK timeout 数字只对本报告列明的安装版本成立。

默认 408 序列的 wall clock 不是“10×固定退避”，而是各 attempt latency、既有 rate-limit wait 与本地调度之和，最迟由同一 3600 秒 client deadline 截断。`upstream_request_deadline=1200` 每次重置，不构成总时限。SDK 的 read 600 秒通常会比 1200 秒 attempt deadline 更早结束一次无 headers 的等待，但那一类结束是本地 `APITimeoutError`，不是 upstream HTTP 408。

请求体边界有一项需要限定：`_dispatch()` 在读 body 前计算 `client_deadline_at`，但 `await request.body()` 本身不在 timeout context 内；只有随后进入 `handle_bounded()` 才用该 instant。已完成 body 的普通 408 请求仍受 3600 秒总限，永不完成的 body 则不会在 deadline 到点时被主动打断。

### T408-05：流式请求的 HTTP 408 仍发生在 downstream stream 开始之前

- `conclusion_strength: confirmed`
- `question:` `stream=true` 时，408 在何时可见，是否能先发 200 再 retry？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/client.py:68-82,100-112,154-168`；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:352-393,421-488`；OpenAI SDK 3.3.1 本地 mock probe。
- `quote/measurement:` mock upstream 对 `stream=True` 返回 408 时，`await sdk.post(..., stream=True)` 输出 `raised_before_return=APIStatusError`、`status_code=408`，没有返回 `httpx2.Response`。route 只有 `handle_bounded()` 成功返回 response 后才构造 `_AccountedStreamingResponse`。
- `confidence:` 高。

因此，连续 408 的 10 次 attempt 都发生在 downstream SSE response 尚未构造时。耗尽后 `handled.response is None`，route 返回普通 `error_response()`，而不是先发 HTTP 200 再塞 SSE error event。

当前 live route 也没有使用 `/home/xp/src/ghc-api-proxy-py/src/app/streaming/sse.py` 中的 `DelayedStartStreamingResponse`；全项目 source call-site 搜索只找到定义与导出，没有 production caller。实际 `_AccountedStreamingResponse` 继承 Starlette `StreamingResponse`，在 body pull 前发送 response start。这个事实只影响 upstream 已返回 200 后的 body tear，不改变 HTTP 408 的 pre-start 位置。

### T408-06：stream 已以 200 开始后，按“semantic delivery frontier”决定 replay，而不是按 HTTP status 408

- `conclusion_strength: confirmed`
- `question:` 流开始后失败如何处理？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:99-158`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py:375-544`；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:503-633`。
- `quote/measurement:` `decide_stream_ending()` 仅在 `downstream_opened=False` 时花 budget 并返回 `REPLAY`；已 opened 时无论 committed blocks 是 0 还是更多都返回 `ABANDON`。live caller 的 `downstream_opened` 来自 `client_has_bytes`，该 event 只在完整 block 的 framed chunk 被 yield 时设置；keep-alive comment 与已经发送的 HTTP 200 不算 semantic opening。
- `confidence:` 高。

这里的“流开始”有两个不同边界，必须分开：

- **HTTP/ASGI 边界：** upstream 200 headers 一到，downstream 200 会在 first body pull 前发送。
- **semantic delivery 边界：** 至少一个完整 content block 已交给 client；只有跨过这条 frontier 才禁止透明 replay。

所以 body tear 可以发生在 downstream 已持有 HTTP 200、甚至收过 SSE keep-alive comment，但尚未收到 semantic event 时；项目仍可透明重开 upstream attempt。若至少一个完整 block 已交付，proxy 不 replay。对于 primary Anthropic client 且 continuation tool 可用，upstream tear 会被合成为 hand-over tool call；不适用时则发送 `upstream_stream_failed` error frame并把原异常继续抛给 request accounting。一个已发送 200 的 HTTP response 不可能在中途改成 408；若 SSE event 内部写了 timeout/error，那是 application event，不是“上游返回 HTTP 408”，其路径也不应从本报告的 408 status 规则推导。

### T408-07：预算耗尽仍把最后一个 408 作为客户端可行动的 cause

- `conclusion_strength: confirmed`
- `question:` 最终客户端拿到什么 status、body 与 headers？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:220-242`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:69-120,199-216`；`/home/xp/src/ghc-api-proxy-py/src/app/server/http_errors.py:59-103`；`/home/xp/src/ghc-api-proxy-py/src/app/errors.py:89-119,145-180`。
- `quote/measurement:` budget exhausted 时 driver 建立 `PipelineAbort(..., cause=last_408)`；`describe()` 首先递归到 cause，所以不会把 408 扁平化成 proxy 502。纯内存 probe 测得 direct output 是原始 status 408、原始 JSON bytes、`Retry-After: 7` 与 `x-upstream: kept`；translated-to-Anthropic output 是 status 408、`error.type=timeout_error`、`error.code=timeout`、message `upstream returned 408: request timed out`，并保留 semantic headers。
- `confidence:` 高。

Direct OpenAI Responses client 与 translated Anthropic client 的 body 形状不同，但 status 都保持 upstream 408。只有本地 timeout exception 才映射为 504。

### T408-08：客户端断开只在不同生命周期阶段产生不同取消效果

- `conclusion_strength: confirmed`
- `question:` client disconnect 是否取消 retry/upstream，请求前后语义是什么？
- `source/version:` `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:95-141,196-210,720-877,1010-1126,1202-1291`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py:398-446`；`/home/xp/src/ghc-api-proxy-py/src/app/streaming/keepalive.py:134-203`；Starlette 1.6.0 `StreamingResponse.__call__`；Uvicorn 0.52.4 `protocols/http/h11_impl.py:107-126,199-265,459-545`；现有 tests `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:2993-3069` 与 `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_completion.py:1028-1077`。
- `quote/measurement:` production Uvicorn scope 固定声明 `spec_version='2.3'`。Starlette 对 `<2.4` 同时运行 `stream_response()` 与 `listen_for_disconnect()`，任一完成就 cancel task group。Uvicorn `connection_lost()` 只设置 `cycle.disconnected=True` 并唤醒 `receive()`，没有 `task.cancel()`。应用在完整读取 request body 后、等待 upstream headers 的 driver 阶段不再调用 `receive()`。delivery 的 `except Exception` 刻意不捕获 `CancelledError`，cleanup 会 cancel pending `anext`、await iterator close 并最终调用 upstream `response.aclose()`。
- `confidence:` 高；ASGI 断开监听分支限定于本项目当前 Uvicorn 0.52.4 发布的 ASGI 2.3 scope。

分阶段结果如下：

1. **client 在 request body 尚未完整到达时断开：** `request.body()` 可抛 `ClientDisconnect`，应用向上传播并将 request 记为 `gone`。
2. **body 已完整、upstream response headers 尚未返回：** 没有 concurrent disconnect listener；断开只进入 Uvicorn 的 receive queue，不会取消正在进行的 SDK send 或 408 retry loop。该 loop 会继续，直到产生 response、触发 timeout、shutdown cancellation 或其他 failure。这是当前行为，不是对参考实现的推测。
3. **streaming response 已进入 ASGI 生命周期：** Starlette 的 ASGI 2.3 listener 读到 `http.disconnect` 后取消 body task。取消沿 iterator stack 传播，既不归类为 upstream tear，也不会消耗 retry budget、replay 或 hand-over；cleanup 先释放 pending pull 与 upstream response，再完成 accounting，未完整交付的 turn 记为 `gone`。
4. **non-streaming response：** 没有 streaming disconnect listener。当前 Uvicorn 在 `send()` 时若 `disconnected` 已经为真会直接 return，而不是抛错；应用侧 observed-send 因此可能把 no-op 当作 send returned。这里只能确认当前 Uvicorn 0.52.4 的代码路径，不外推到其他 ASGI server。

### T408-09：前身与官方参考比较未执行，不能给出差异结论

- `conclusion_strength: inconclusive`
- `question:` `/home/xp/src/copilot-api-js` 与 `/home/xp/src/refs/vscode-copilot-chat` 对 408 的分类、重试、退避、时限、stream frontier 与 disconnect cancellation 分别是什么？
- `source/version:` 无可读 source；仅有目录可见性失败与 coordinator 的 isolation 说明。
- `quote/measurement:` 两个绝对路径的 `test -d` 在本 agent 返回 1，`Read` 返回 `File does not exist`；CodeGraph 报无可用 index。协调方明确回复“参考目录在 remote isolation 不可见”。
- `confidence:` 对“本次未执行比较”的判断为高；对两个实现自身行为没有证据，结论为空。

如果后续要补全，只应在能同时读取两个目录的非隔离会话中重新调查源码。需要逐项建立与本报告相同的六个边界，而不是只搜 `408`：SDK retry layer、wrapper retry layer、`Retry-After` 消费、per-attempt 与 whole-request deadline、HTTP headers 与 semantic block 两条 stream frontier、pre-header 与 post-header disconnect cancellation。任何结果都应标出 commit/content revision；参考实现只提供 comparative evidence，不自动拥有当前项目的规范权威。

## 4．本地无网络探针结果

### 4.1 OpenAI SDK timeout 与 retry 配置

```text
openai 3.3.1
httpx2 2.12.0
starlette 1.6.0
uvicorn 0.52.4
anyio 4.14.2
same_client= True
sdk_timeout= Timeout(connect=5.0, read=600, write=600, pool=600)
transport_timeout= Timeout(timeout=5.0)
sdk_max_retries= 0
request_timeout_extension= {'connect': 5.0, 'read': 600, 'write': 600, 'pool': 600}
```

`transport_timeout` 是 custom AsyncClient 的实例默认值；真正附到 OpenAI request 上的是 SDK 的 5/600/600/600 extension，所以总时限分析采用后者。

### 4.2 `stream=True` 的 HTTP 408 边界

```text
raised_before_return= APIStatusError
status_code= 408
sdk_calls= 1
```

这说明 SDK 在把 streaming `Response` 交给项目之前就抛 status exception；不支持“先返回 408 response 再由 body reader发现”的说法。

### 4.3 默认 pipeline 408 序列与最终输出

```text
normalized_type= UpstreamError
status_code= 408
classification= retry
retry_reason= serverError
provider_calls= 10
context_attempts= 10
ledger_total_spent= 9
ledger_per_reason= {'serverError': 9}
terminal_error_type= PipelineAbort
terminal_cause_type= UpstreamError
direct_status= 408
direct_headers= {'retry-after': '7', 'x-upstream': 'kept', 'content-type': 'application/json'}
direct_body= {"error":{"message":"request timed out","type":"timeout"}}
translated_status= 408
translated_headers= {'retry-after': '7', 'x-upstream': 'kept', 'content-type': 'application/json'}
translated_body= {'type': 'error', 'error': {'type': 'timeout_error', 'message': 'upstream returned 408: request timed out', 'code': 'timeout'}}
```

该 probe 只替换了 network counterpart 为纯内存 fake；分类、budget、driver loop 与 error rendering 使用生产模块。它证明当前模块组合下的行为，不证明真实 Copilot upstream 何时、为何返回 408。

## 5．比较矩阵

| 问题 | 当前 Python | `copilot-api-js` | `vscode-copilot-chat` |
|---|---|---|---|
| 408 类别 | Retryable `UpstreamError`，budget reason `serverError`。 | 未执行：source 不可见。 | 未执行：source 不可见。 |
| 默认调用次数 | 10 calls＝1 initial＋9 retries；SDK retries disabled。 | 未执行：source 不可见。 | 未执行：source 不可见。 |
| 退避与 jitter | 408 自身无 backoff/jitter，忽略其 `Retry-After` 作为调度信号。 | 未执行：source 不可见。 | 未执行：source 不可见。 |
| 总时限 | 默认 whole-client 3600 秒；per-attempt 1200 秒；SDK request extension connect 5 秒、其他阶段 600 秒。 | 未执行：source 不可见。 | 未执行：source 不可见。 |
| stream 前 | SDK 在返回 streaming response 前抛 408；耗尽后普通 HTTP 408。 | 未执行：source 不可见。 | 未执行：source 不可见。 |
| stream 后 | 已是 200 的 stream 不再有 HTTP 408；body failure 依 semantic frontier replay／hand-over／error。 | 未执行：source 不可见。 | 未执行：source 不可见。 |
| disconnect | pre-header 无 listener，不自动取消 retry；production SSE lifecycle 内取消并 cleanup，不 retry。 | 未执行：source 不可见。 | 未执行：source 不可见。 |

这张矩阵不能被摘要成“三者差异”；本轮只有 Python 一列有证据，另外两列是明确缺口。

## 6．关键源码 SHA-256

```text
5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a  /home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py
224af7c8efd68599f96858feb25e6a630c8dab0c9f3deea5e87ba0ec3e1619c0  /home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py
e62c7fe4c59ef2e2b1caa3d8c7c263c872e9dd1a2e97bfb832c6e74d654c2873  /home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py
d09f78f660621c5601daa69a0e0d4c20cc5045397d03a2a4a5c19032e0a599b6  /home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py
f91b10b94ecf02efcd5ce364dfb825024a3c48fd291ec5d407a2e2c22ceb72a3  /home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py
db1f722c7266925147c7a11255c116fd22edfd52c2062b27d86b84b70a307c91  /home/xp/src/ghc-api-proxy-py/src/app/server/composition.py
bc21c4ab630173d083daec72fb1232cab680425ceb0e2cdf8826acc606ea9c0b  /home/xp/src/ghc-api-proxy-py/src/app/streaming/keepalive.py
cf320c502763646ff986419053cfbe34ae3b241a09029b67276ccb7a41aa0e57  /home/xp/src/ghc-api-proxy-py/src/app/config/schema.py
```

## 7．整体判定

当前 Python 项目的 408 路径已经可以明确描述：它由 proxy layer 以 `serverError` 原因立即 retry，默认共打 10 次，受 3600 秒 whole-client deadline 限制，最终保留 upstream 408；它不是 SDK 自带重试，也不是本地 timeout 504。流式 408 在 downstream stream 建立前结束，stream 建立后的取消与 body tear 属于另一组语义。

前身与官方参考比较没有完成，原因是文件系统 isolation，而不是时间不足或搜索无命中。因此本报告作为“完整三方参考实现比较”的 verdict 是 `blocked`；作为“当前 Python 项目行为调查”的结论是已确认。后续不得用本报告填补两个空列或推断它们与 Python 相同／不同。

## 8．我最没把握的三个判断

1. **non-streaming disconnect 的最终 observability。** Uvicorn 0.52.4 在 disconnected 后让 `send()` 静默 return，应用 wrapper 会把 return 当成 sent；源码足以说明当前组合，但本轮没有建立真实 socket probe 来观测最终日志，因此“可能记作 delivered”的下游描述只应作为高可信推论，不作为已实测 production fact。
2. **已有 provider rate-limit 状态对 408 retry 的等待。** 状态机明确允许 inherited wait，但本轮没有构造“先 429／502，再 408”的组合 probe；结论是由共享 limiter 实例与 `acquire()` 控制流推导，不能简写成每个 408 都等待。
3. **request body 越过 client deadline 的外部呈现。** 源码明确 body read 不在 timeout scope 内，但具体 ASGI server、TCP 断开与 body stream 如何结束会改变最终 exception；本报告只收窄到“deadline 到点本身不会主动打断 body read”。

真实未决判断只有以上三个；两份参考实现不是“低置信判断”，而是没有证据、不得判断。

## 9．执行本契约时遇到的摩擦

- 本 agent 是 remote-isolated worktree，两个 sibling reference repository 未挂载；协调方确认后要求将比较列为空，不进行猜测。
- CodeGraph 只索引当前 Python 项目，而且其输出混入多个 worktree 路径；本报告所有引用都重新限定到固定主项目绝对路径 `/home/xp/src/ghc-api-proxy-py`。
- 用户要求不操作 Git，所以无法用 main checkout commit SHA 作 revision；用读取日期、依赖版本与关键文件 SHA-256 代替。
- 没有发网络请求。所有运行测量使用 pure fake 或 `httpx2.MockTransport`。

## 交付声明

delivery_complete: true
completed_at: 2026-09-04
finding_total: 9
confirmed: 8
likely: 0
inconclusive: 1
refuted: 0
