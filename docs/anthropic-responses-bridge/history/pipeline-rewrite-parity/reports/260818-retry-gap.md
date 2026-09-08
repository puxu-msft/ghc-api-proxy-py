# 上游出错时的恢复能力差距

## 范围与结论

本报告比较 Python 新处理链 `/home/xp/src/ghc-api-proxy-py` 的 `main`（`662e278b2ec2a43b706ea9eb678b6f687b905fb8`）与 `/home/xp/src/copilot-api-js` 的 `master`（`c0f38b8c367804dd7341485058d209cd5ec0f9e8`）。History 库均通过 SQLite URI `file:...?mode=ro&immutable=1` 打开；未连接、未操作 `127.0.0.1:4141`。

最重要的事实不是“Python 少了一些优化”，而是两层实际断链。

1. 已知真实的 `context_management: Extra inputs are not permitted` 400 没有 Python 自愈路径。上游会将 `context_management` 置 `null`、持久记忆不支持并重发；Python 没有 error-body matcher、请求改写或 negotiation cache。按任务给定的实测，它目前被包装为 502。
2. Python 的 `RetryLedger` 是预算器，不是完整恢复机制。生产 `GhcApiClient` 用 OpenAI／Anthropic SDK 的 `.post()`；SDK 遇 4xx／5xx 会抛 status exception。`DirectDriver` 只把 `PipelineError` 子类判为可重试，故原始 SDK exception 直接终止，`error_status()` 再将其映射为 502。于是名义上已有的 429、5xx、连接异常重试预算，对这条生产发送路径通常不生效。
3. Python 也尚未把流中断后的 `streamReplay`、continuation、`max_tokens_as_retryable` 或 hedge 接到运行路径；上游已具备 buffered replay、续写和 hedge 候选机制。`.dev/human-controlled-docs-candidates/config-schema-gap.md:78-80` 的现状记录与源码搜索一致。

下文“无”均指新链中没有等价的“识别该失败 → 以安全方式改写／等待 → 重发 → 为后续请求学习”的完整行为，不把同名配置字段或单元测试原语误报为等价物。

## 1．`strategies/` 的逐文件盘点

`/home/xp/src/copilot-api-js/src/lib/request/strategies/` 共有下表 16 个 `.ts` 文件。活动 registry 也是 16 项，但集合不完全相同：它包含目录外的 `poisoned-thinking-retry`，不把本目录的通用 factory `reactive-rejection.ts` 当作独立 entry。`/home/xp/src/copilot-api-js/src/lib/request/retry-registry.ts:150-318` 显示前三个 registry entry 覆盖所有 outbound leg，其余 13 个面向 `targetEndpoint === MESSAGES`；`/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:804-878` 先取第一个命中策略，再执行 family／shared budget 门。

| 文件／策略 | 识别的上游错误 | 改写与跨请求学习 | 重试次数与等待 |
|---|---|---|---|
| `adaptive-thinking-rejection-retry.ts` | HTTP 400，错误文本含 `adaptive thinking is not supported`。`/home/xp/src/copilot-api-js/src/lib/request/strategies/adaptive-thinking-rejection-retry.ts:49-82` | 将 `thinking.type: adaptive` 变为 enabled／budget 形态，把 `output_config.effort` 折入预算后删除。`…:84-110` | 一次：第二次已非 adaptive 即 abort。`…:85-90` |
| `cache-control-subfield-rejection-retry.ts` | HTTP 400，`.cache_control.<variant>.<field>: Extra inputs are not permitted`。`…/cache-control-subfield-rejection-retry.ts:39-59,68-71` | 收集全部拒绝字段，写 endpoint-wide negotiation cache，并在下一次 prepare 排除这些子字段。`…:73-87` | 单次，closure `attempted`。`…:61-75` |
| `context-management-retry.ts`（现为通用 `body-field-rejection-retry`） | HTTP 400，顶层 `<field>: Extra inputs are not permitted`；涵盖已实测的 `context_management`。嵌套路径被明确排除。`…/context-management-retry.ts:31-55,84-90` | 标记该 model 的 feature unsupported；`context_management` 专门改成 `null`，其他顶层字段设为 `undefined`，并以 `prepareHints.rejectFields` 重 prepare。`…:99-128` | 对 `context_management` 至多一次：已为 `null` 时 abort。`…:103-111`。其他通用顶层字段没有私有计数，受 driver 的 reactive shared cap 约束。 |
| `deferred-tool-retry.ts` | HTTP 400，`Tool reference 'X' not found in available tools`。`…/deferred-tool-retry.ts:41-50,70-76` | 将同 model／tool 写为 sticky non-deferred；本次将 tool 的 `defer_loading` 改 `false`，缺定义时注入 minimal non-deferred stub。`…:87-133,145-161` | 一次有效修复：已 sticky 时 abort。`…:85-89` |
| `effort-learning-retry.ts` | HTTP 400 body 含 `invalid_reasoning_effort`。`…/effort-learning-retry.ts:35-65` | 从错误体学习 model 可用 effort，再由下一轮 prepare clamp `output_config.effort`。`…:67-77` | 单次，`attempted` guard。`…:50-56` |
| `legacy-thinking-retry.ts` | HTTP 400 含 `thinking.type.enabled` 且有 `not supported`／`adaptive` 提示。`…/legacy-thinking-retry.ts:30-40,66-70` | 将 legacy enabled thinking 改为 `{type: "adaptive"}`，保留 display。`…:72-90` | 一次：已经 adaptive 或无 thinking 时 abort。`…:73-77` |
| `network-retry.ts` | 分类为 `network_error`，包括连接重置、超时、socket close、空 499 与特定 408。`…/network-retry.ts:1-6,46-47` | 原 payload 重发，不作语义改写。 | 默认 9 次，operator 可配；1 s 起指数退避，上限 30 s。`…:19-26,39-64` |
| `reactive-rejection.ts` | 不是独立 registry entry，而是 system／web-search／server-tool 等策略共用的“specific 400 → token”工厂。`…/reactive-rejection.ts:1-14,26-55` | 执行调用方给出的 mark 与 remediate。 | 每个 factory instance 一次，`attempted` guard。`…:33-53` |
| `server-error-retry.ts` | 分类为 `server_error` 的 5xx；注释特别排除已归为 upstream-rate-limited 的 503。`…/server-error-retry.ts:1-10,49-51` | 原 payload 重发。 | 默认 9 次；1 s 指数退避，上限 30 s。`…:23-30,42-68` |
| `server-tool-rejection-retry.ts` | HTTP 400，当前已知文本为 `The use of the web search tool is not supported.`。`…/server-tool-rejection-retry.ts:44-75` | 学习 model 不支持的 server-tool type prefix，并经 `excludeServerToolTypes` 使本轮与未来 prepare 都剥离。`…:77-88` | 通过 `reactive-rejection`，单次。 |
| `structured-outputs-rejection-retry.ts` | HTTP 400 Vertex `allowedPartnerModelFeatures` policy，且 feature 有安全 strip target；当前只有 `structured_outputs`。`…/structured-outputs-rejection-retry.ts:87-125` | 学习 feature unsupported，去掉 `output_config.format`，降级为 free-form。`…:127-151` | 单次，`attempted` guard。`…:109-128` |
| `system-reject-retry.ts` | HTTP 400 `Unexpected role "system"`，同时兼容 raw JSON escape。`…/system-reject-retry.ts:33-48,56-63` | 学习 system reject model，然后从 pre-S3 original payload 重跑 sanitize，将 inline system 按已学习策略改写。`…:64-76` | 通过 `reactive-rejection`，单次。 |
| `token-refresh.ts` | 分类 `auth_expired`，即上游 401／403。`…/token-refresh.ts:54-69` | 强制重新 mint Copilot token 后重发；GitHub credential 无效或 runtime 不可用时 abort。`…:71-107` | 默认 3 次；mint transient 以 0.5 s 指数退避，上限 8 s。`…:32-45,94-100` |
| `tool-field-rejection-retry.ts` | HTTP 400 `tools.N.<variant>.<field>: Extra inputs are not permitted`，但已知合法字段不剥以免掩盖 variant-misrouting。`…/tool-field-rejection-retry.ts:71-117` | endpoint-wide 学习并以 `excludeToolFields` 剥全部命中字段。`…:120-149` | 单次，`attempted` guard。`…:120-136` |
| `unsupported-beta-retry.ts` | HTTP 400 `unsupported beta header(s): …` 或 `invalid beta flag`。`…/unsupported-beta-retry.ts:47-74,124-139` | 明示 token：学习并排除；含糊 flag：按子集从小到大 probe，成功后才学习最小非法集。`…:141-198` | 明示列表无私有计数，受 reactive shared cap；含糊路径最多 32 个 probe 子集，且用独立 learning budget。`…:54-56,160-181` |
| `web-search-not-found-retry.ts` | HTTP 400 `Tool '…' not found in provided tools`，与 deferred-tool wording 有意区分。`…/web-search-not-found-retry.ts:33-49,56-63` | 学习 model 要 downgrade server-tool history，并从 pre-S3 original payload 重跑 sanitize。`…:64-76` | 通过 `reactive-rejection`，单次。 |

补充：live registry 还有 `poisoned-thinking-retry`，文件在目录外的 `/home/xp/src/copilot-api-js/src/lib/codec/anthropic/poisoned-thinking-retry.ts:64-123`，故不冒充为 `strategies/` 目录成员。它针对非法 thinking-layout 400，strip all thinking 后重发一次，并在成功后 quarantine `(session, agent)`。

## 2．逐策略对 Python 新链的等价性

Python 的实际新链是 `/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py:55-98` 创建 `LedgerBudget(RetryLedger(...))` 并交给 `DirectDriver`，不是旧 `pipeline/executor.py`。`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:124-171` 是唯一的 send/retry loop。

| 上游策略 | Python 等价物 | 结论与证据 |
|---|---|---|
| adaptive thinking rejection | 无 | `fix_anthropic_request()` 只做 empty-thinking 与 assistant layout（`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/anthropic_request_hook.py:36-68`），没有错误 matcher／adaptive-to-enabled rewrite。搜索范围为 `src/app`，关键词 `adaptive thinking`、`thinking.type.enabled`；命中列表未含新链修复器。 |
| cache-control subfield rejection | 无 | 搜索 `src/app` 的 `cache_control` 只命中 model／旧模块，不存在错误 matcher、per-endpoint learned strip 或 retry hint；新链 hook 也未读取 cache-control。搜索命令见“未找到的验证”。 |
| body field／context management rejection | 无 | 已知真实 400 是直接证据。Python `RetryReason` 只有 token/network/server/stream/continuation（`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:24-60`），无 400 body-field reason；`handler.handle()` 无 400 remediation handler（`…/server/handler.py:55-98`）。 |
| deferred tool | 无 | 无 `defer_loading` parser、sticky tool state 或 retry payload rewrite。搜索 `src/app`，关键词 `defer_loading`、`Tool reference`、`available tools`，未找到。 |
| effort learning | 无 | 无 `invalid_reasoning_effort` parser、supported values learner 或 effort clamp-on-retry。搜索 `src/app`，关键词 `invalid_reasoning_effort`、`output_config.effort`，未找到。 |
| legacy thinking rejection | 无 | 预处理有 layout 维修，不等价于收到 `thinking.type.enabled` 400 后改 adaptive。`…/anthropic_request_hook.py:36-68`；搜索 `src/app`，关键词 `thinking.type.enabled`，未找到。 |
| network retry | 预算原语存在，但生产路径不等价 | `UpstreamTimeout` 会被归为 NETWORK（`…/pipeline/retry.py:46-59`），默认预算 9（`…/config/schema.py:107-127`）；但没有退避，且 SDK connection／timeout exception 不会自动变成 `UpstreamTimeout`。`DirectDriver._send()` 只转换它自己 `asyncio.timeout` 的 `TimeoutError`（`…/direct_driver/base.py:216-240`）。 |
| `reactive-rejection.ts` primitive | 无 | Python 没有“匹配 specific 400 → mark → retry action”的策略接口；只有异常分类与计数器（`…/pipeline/exceptions.py:57-70`、`…/pipeline/retry.py:64-104`）。 |
| server 5xx retry | 预算原语存在，但生产路径不等价 | `reason_for()` 可将已包装的 `UpstreamError(status>=500)` 命名 serverError（`…/pipeline/retry.py:51-60`），默认 9（`…/config/schema.py:114-116`）；但普通 SDK 5xx 是未知 exception，详见第 5 节。没有上游同等的 1→30 s backoff。 |
| server-tool rejection | 无 | 无 `web search tool is not supported` matcher、server tool strip 或 learned model state。搜索 `src/app`，关键词该错误文本、`excludeServerToolTypes`、`server_tool`，未找到新链等价实现。 |
| structured outputs rejection | 无 | 无 Vertex policy matcher、`output_config.format` fallback 或 feature negotiation cache。搜索 `src/app`，关键词 `allowedPartnerModelFeatures`、`structured_outputs`，未找到。 |
| system reject | 无 | Python 有 system prompt transform，但无 HTTP 400 `Unexpected role "system"` 的 reactive learning／从 pre-transform base 重跑。搜索 `src/app`，关键词 `Unexpected role`、`systemReject`，未找到。 |
| token refresh | 不等价 | `CopilotTokenManager` 在 token exchange 内重试 408／429／5xx，并可在 exchange 401 后刷新 GitHub token（`/home/xp/src/ghc-api-proxy-py/src/app/ghc_client/tokens.py:116-151`）；这不是 request 收到 Copilot 401／403 后 force-remint-and-replay。新链 `githubTokenExpired.max_retries` 默认是 0（`…/config/schema.py:107-110`），无对应 request-level action。 |
| tool-field rejection | 无 | 无 `tools.N…Extra inputs` parser、合法字段保护、learned strip 或 retry hint。搜索 `src/app`，关键词 `eager_input_streaming`、`Extra inputs are not permitted`，未找到。 |
| unsupported beta | 无 | 无 `unsupported beta header`／`invalid beta flag` parser、preparation hint、subset probe 或 cache。搜索 `src/app`，关键词 `unsupported beta`、`invalid beta flag`，未找到。 |
| web-search-not-found | 无 | 无 `not found in provided tools` matcher、历史 downgrade／re-sanitize。搜索 `src/app`，关键词 `not found in provided tools`、`web_search`，未找到该恢复路径。 |
| poisoned thinking（目录外补充） | 原语有，未接线 | 旧模块有 `strip_all_thinking`／quarantine，但候选文档明确新链未接；新链实际 hook 仅执行 layout/empty 修复。`/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/config-schema-gap.md:82-83`，`…/pipeline/anthropic_request_hook.py:36-68`。 |

“未找到的验证”使用的只读搜索命令为：`rg -n -l -i 'context_management|extra inputs are not permitted|adaptive thinking|thinking\.type\.enabled|invalid_reasoning_effort|defer_loading|unsupported beta|server tool|structured_outputs|role.*system|web_search|eager_input_streaming|cache_control|token.*refresh|rate.?limit' src/app | sort`。命中的是配置、旧实现、model 类型和现有 limiter；没有一个命中在新 `DirectDriver`／`handler` 中实现上述 400 matcher＋payload rewrite＋re-dispatch 链。对 `continuation_messages`、`max_tokens_as_retryable`、hedge 的独立搜索结果如下：

```text
continuation_messages(): src/app/pipeline/retry.py + tests/unit/test_retry_strategies.py，只有测试调用者
max_tokens_as_retryable: src/app/config/schema.py:128，只有字段定义
client_delivery.hedge / .hedge: 没有 src/app 或 tests 的消费者
PipelineRetry: 生产 src/app 只有定义、分类和 ledger；构造点只有 tests
```

## 3．History：哪些恢复真的发生过

### 口径和方法

样本为当前目录下四个连续的 v3 history database，而非 archive copy：`history-v3-20260815-183721.db`、`history-v3-20260816-160151.db`、`history-v3-20260817-050754.db`、`history-v3-20260818-044224.db`。每库的分母是 `v3_operations` 全部 operation；“重试”是 `summary_json.attemptCount > 1`；“失败”是 `summary_json.responseSuccess = false`；交集要求二者同时成立。时间范围按 `min(created_at)` 至 `max(coalesce(ended_at, created_at))` 的 UTC 值。

数字通过两个不同的读取路径交叉核对：Python `json.loads(summary_json)` 逐行统计，与 SQLite `json_extract(summary_json, '$.attemptCount')`／`json_extract(summary_json, '$.responseSuccess')` 聚合。两种方法在同一只读事务中断言相等；数据库仍可由现役服务追加，所以下表是报告写入前的观测快照，不应被当作未来稳定计数。

| 库 | UTC 时间范围 | operation | `attemptCount > 1` | `responseSuccess = false` | 两者交集 |
|---|---|---:|---:|---:|---:|
| `history-v3-20260815-183721.db` | 2026-08-15T18:41:06.581Z ～ 2026-08-16T16:01:48.798Z | 797 | 0（0.00%） | 4（0.50%） | 0（0.00%） |
| `history-v3-20260816-160151.db` | 2026-08-16T16:02:18.968Z ～ 2026-08-16T20:13:19.442Z | 906 | 1（0.11%） | 5（0.55%） | 0（0.00%） |
| `history-v3-20260817-050754.db` | 2026-08-17T05:08:01.925Z ～ 2026-08-17T13:13:41.745Z | 571 | 1（0.18%） | 2（0.35%） | 0（0.00%） |
| `history-v3-20260818-044224.db` | 2026-08-18T04:42:43.651Z ～ 2026-08-18T17:11:45.945Z | 582 | 0（0.00%） | 2（0.34%） | 0（0.00%） |

可观察到的成功恢复只有两次：

- `history-v3-20260816-160151.db` 的 `req_1786897414889_13`：`attemptCount=2`、最终 completed；manifest 的 `record.dispatches` 记 `dispatch:0` 为 `retry:buffered-retry`／discarded，`dispatch:1` 的 strategy 为 `buffered-retry`／committed；transport 记录 `session-goaway`，RST code 0。
- `history-v3-20260817-050754.db` 的 `req_1786964132683_369`：`attemptCount=2`、最终 completed；`dispatch:0` 错误为 `[http2] upstream stream closed before any response (rstCode=0)`，`retry:network-retry` 后 `dispatch:1` committed。

这四库没有记录到已命名 400 negotiation strategy、429、5xx 或 upstream timeout 的实际成功触发，不能据此推论它们不需要；它只说明此样本没有覆盖到它们。相反，任务已给出的真实 `context_management` 400 是该策略的直接触发证据，优先级高于“近期 history 尚未出现”的负样本。

这 13 个 `responseSuccess=false` 中，绝大多数并非可由重试修复的上游 4xx／5xx：12 个是 client disconnect／`AbortError` 或 post-response signal abort；唯一可见 transport failure 是 `req_1786944536288_117` 的 `Stream closed with error code NGHTTP2_CANCEL`。因此不能把本表的失败比例误报为“上游 400 策略能消除的失败率”。错误详情来自每条 operation 的 zstd 解压 `manifest_gz`，用其 `objectHashes` 映射读取 `v3_objects.canonical_gz`，并检查 `record.terminal` 与 `record.dispatches`。

## 4．今日活跃库的两次 `responseSuccess=false`

`history-v3-20260818-044224.db` 的两项均不是 HTTP 400／429／5xx，也不是 upstream timeout：

| operation | 终端错误 | transport 证据 | 判定 |
|---|---|---|---|
| `req_1787057152136_131` | `StreamClientAbortError: Client disconnected` | `kind=local-cancel`、`localCancelSource=post-response-signal-abort`、`rstCode=8`、`h2SessionId=h2-20` | 本地取消／客户端断连；summary attribution 的 `category=upstream` 不足以推翻更具体的 `transportFailure.localCancelSource`。 |
| `req_1787058443727_205` | `StreamClientAbortError: Client disconnected` | `kind=local-cancel`、`localCancelSource=post-response-signal-abort`、`rstCode=8`、`h2SessionId=h2-25` | 同上。 |

两项均为一次尝试，分别持续 59,596 ms 与 29,091 ms，且 `usage.input_tokens=0`、`usage.output_tokens=0`。所以它们不能作为“上游恢复策略没有发挥作用”的证据，也不能由透明重放安全修复。

## 5．429、5xx 与超时的行为差异

### copilot-api-js

- **429／rate-limited envelope**：`/home/xp/src/copilot-api-js/src/lib/pipeline/generation/dispatch-scheduler.ts:294-318` 在物理 open 失败后识别 status 429、`rate_limited` 与 `upstream_rate_limited`，把 retry-after 交给 admission controller 并创建 `rate-limit-retry`，而不是交给普通 reactive strategy。`/home/xp/src/copilot-api-js/src/lib/transport/admission-controller.ts:43-65` 接入 `AdaptiveRateLimiter`；其 admission 路径优先 server `Retry-After`，否则 10 s 指数退避至 120 s，并队列化／渐进恢复。证据为 `/home/xp/src/copilot-api-js/src/lib/adaptive-rate-limiter.ts:246-276,355-372,547-639`。如果最终仍要向客户端交付错误，`/home/xp/src/copilot-api-js/src/lib/error/forward.ts:431-454` 保留 429 语义，亦将“503 且 upstream rate limited”作为 rate-limit envelope 处理并带 `retry_after`。
- **5xx**：`server-error-retry` 默认最多 9 次、1→30 s 指数退避（`…/strategies/server-error-retry.ts:23-68`）；它与 network 策略共同受 shared reactive cap 20 限制（`/home/xp/src/copilot-api-js/packages/foundation/src/state-defaults.ts:191-201`），不会无限重发。
- **连接失败／headers 前 timeout／408**：`network-retry` 默认 9 次、同为 1→30 s 退避（`…/strategies/network-retry.ts:19-64`）。已在 history 中观察到一次 headers 前 HTTP/2 close 由它修复。流在无 client-visible content 前的 recovery，以及 buffer 内完整响应 replay，是独立于该策略的 generation 流程；当前样本也观察到一次 `buffered-retry` 成功。

### Python 新链

- **共享根因——状态错误未归一化**：`GhcApiClient` 的普通发送均直接调用 SDK `.post()`（`/home/xp/src/ghc-api-proxy-py/src/app/ghc_client/client.py:59-89,91-125`）。当前 venv 的 SDK source 在 `/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/anthropic/_base_client.py:1757-1777` 和 `…/openai/_base_client.py:1649-1669` 对 4xx／5xx `raise_for_status()` 后 re-raise provider status error；composition 又显式将 SDK 自身 `max_retries=0`（`/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:144-159`）。但 `classify()` 仅将 `UpstreamError` 与 `PipelineRetry` 归为 RETRY（`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/exceptions.py:57-70`），原始 SDK status／connection exception 会直接终止；`pipeline_app` 捕获后调用 `error_status()`，后者除少数本地错误外一律返回 502（`/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:67-75`、`…/server/handler.py:196-215`）。
- **429**：若错误已经被包装为 `UpstreamRateLimit`，ledger 会把它花在 `serverError` budget（`…/pipeline/retry.py:47-49`）；但普通生产 429 不是该异常。`RateLimiter.observe_failure()` 虽能记录 429／502、采用 response 的 `Retry-After` 或配置间隔（`…/pipeline/rate_limiting.py:157-175`），它本身不重发，且 raw SDK 429 已被 classify abort。因此客户端通常得到 502，丢失 429／`Retry-After` 语义。即使测试 fake 直接返回 429 response，`DirectDriver` 才会构造 `UpstreamError` 并继续（`…/direct_driver/base.py:143-160`）；这不是实际 SDK 4xx 行为。
- **5xx**：同样会在 SDK 层抛出未知 exception，名义的 `serverError=9` 预算没有机会消费。即使将来归一化，也没有 `server-error-retry` 的退避；`DirectDriver` 的 funded failure 立即 `continue`（`…/direct_driver/base.py:124-141,192-214`）。
- **超时／连接中断**：唯一已接到 network budget 的超时是 driver 自己的 attempt deadline，`asyncio.timeout` → `UpstreamTimeout`（`…/direct_driver/base.py:216-240`）；SDK `APITimeoutError`、connection error 与 stream-body 中断未被包装。流响应在 headers 后从 `pipeline_app` 直接交给 `stream_delivery(response.aiter_bytes(), …)`（`…/server/pipeline_app.py:77-91`），此时 driver 已成功返回，后续 mid-stream error 不会回到 `DirectDriver.run()`。`PipelineRetry` 的生产构造点不存在，只有定义与 tests，搜索证据见第 2 节。
- **continuation／max_tokens／hedge**：`RetryLedger` 虽列出 `STREAM_REPLAY` 与 `CONTINUATION` 并给预算（`…/pipeline/retry.py:24-29,75-85`），`continuation_messages()` 只在单元测试调用；`max_tokens_as_retryable` 与 hedge 只有 schema，均无消费者。因而不能把配置的默认值（stream replay 100、continuation 10、hedge threshold 300 s）称为当前服务的恢复能力。

## 处置优先级

1. **P0：先把上游 SDK 的 status／transport exception 规范化为带 status、headers、body、retry-after 的 pipeline error，并让 driver 对它们执行明确的 retry action。** 这是 context-management 400、429、5xx 与 transport error 共同的接线点；只加一条 context-management 分支而不修共同 transport 边界，会让 network／5xx／429 预算继续成为未生效原语。
2. **P0：实现 body-field rejection negotiation，首项即 `context_management` 的 `null` rewrite＋per-model learned suppress。** 它有任务给定的真实触发证据；其余 safe `Extra inputs` 类可沿同一“解析 → 可证明安全的 rewrite → retry → learning”的策略接口扩展，不能将未知 400 一概重试。
3. **P1：接通正确的 backoff／rate-limit 重试与 client status preservation。** 429 要按 `Retry-After`／队列节流处理，而非作为无等待的 server-error retry；5xx 与 network 要有 bounded exponential backoff；最终无法恢复时保留可行动的 429／503／504，而不是统一 502。
4. **P1：把 stream-body failure 接回恢复拓扑，并落实已有 continuation、max_tokens continuation 与 hedge 规格。** continuation 不能透明 replay 已提交内容；必须使用现有 `continuation_messages()` 的 assistant-prefix＋synthetic user turn 语义。hedge 必须在任何 client-visible semantic content 前竞速，并禁止可能重复执行 server tool 的请求。

结构怪味审计：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:64-119` 的“具名策略”只保存 budget／message builder，却没有策略决策或 driver action；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:192-214` 才决定是否重发，导致同一恢复功能分裂为“配置看似完整、运行无 payload remediation／backoff”的抽象泄漏。本轮不修改代码，故记录为本报告的 P0／P1 实施项，而不是声称已修复。
