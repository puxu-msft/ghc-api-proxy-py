# Direct buffered `/chat/completions` 当前实现调查

## 1. 范围、快照与方法

本报告只描述当前实现，不修改行为契约，也不提出已获裁决的新行为。

- 源码根：`/home/xp/src/ghc-api-proxy-py`
- 调查用隔离快照：`f97d243f9431d836861ce5e9938605df56b37478`
- 2026-09-05 调查时，本文引用的关键源码与测试已逐文件和主工作树比较，字节一致。
- 已先阅读仓库根 `CLAUDE.md` 与 `.claude/rules/00-development-workflow.md`。
- 仓库根存在 `.codegraph/`，因此先调用了 `codegraph explore --path /home/xp/src/ghc-api-proxy-py ...`；CLI 返回“no `.codegraph/` index exists”，说明目录存在但没有可用索引。依其提示，后续改用 `rg`、`Read` 和只读 Git 查询，没有自行建立索引。
- 没有修改源代码、测试、Spec 或 living docs；没有提交或推送。

这里把几个容易混淆的词分开：

- **direct**：`Route.translation_required is False`，表示 client wire format 与所选 upstream endpoint format 相同。
- **buffered request**：本文主要指 client body 中 `stream` 为 false，server 最终返回普通 JSON response。
- **client-requested streaming**：client body 中 `stream` 为 true。对 direct Chat Completions，它并不形成增量下游交付，而是由 `one_shot_delivery()` 缓冲整个 upstream SSE 后一次写出。
- **driver retry**：response headers／provider send 返回前的失败，由 `DirectDriver.run()` 循环重试。
- **delivery replay**：response headers 已经返回、读取 streaming body 时发生 tear，只有 block delivery 路径构造 `ReplaySupport`；direct Chat Completions 的 one-shot 路径没有。

## 2. 端到端调用链

### 2.1 HTTP 路由与输入边界

1. `src/app/server/routes/table.py:28-46` 在 `ROUTES` 中登记 `InboundRoute("/chat/completions", WireFormat.OPENAI_CHAT_COMPLETIONS, openai_prefixed=True)`，Azure 变体是 `/openai/deployments/{deployment}/chat/completions`。
2. `src/app/server/routes/table.py:25-26,83-104` 通过 `OPENAI_PREFIXES = ("", "/v1", "/openai/v1")` 和 `expanded_paths()` 形成 `/chat/completions`、`/v1/chat/completions`、`/openai/v1/chat/completions` 三个普通入口；`route_for_path()` 把实际路由模板映回 `InboundRoute`。
3. `src/app/server/routes/router.py:13-30` 的 `build_router()` 把所有路径的 `POST` 处理器统一注册为 `serve()`。
4. `src/app/server/routes/inference.py:108-159` 的 `serve()` 建立 trace／completion accounting，然后调用 `_dispatch()`。
5. `src/app/server/routes/inference.py:457-519` 的 `_dispatch()`／`_dispatch_with_body()` 在 client deadline 下完整读入请求体，并在读完 body 后同时监听 client disconnect。
6. `src/app/server/routes/inference.py:522-583` 的 `_dispatch_after_body()` 查路由、解析 JSON object，然后调用 `build_context()`；无效 JSON、非 object body、缺少 model 均在 upstream 前失败。
7. `src/app/server/inbound.py:25-73` 的 `build_context()` 要求普通 Chat Completions body 携带非空字符串 `model`；Azure 变体从 path parameter 取 deployment 并覆盖工作 payload 的 model。`stream = bool(payload.get("stream", False))`，所以这里按 truthiness 而非严格 JSON boolean 读取。工作 payload 和原始 payload 分槽保存；转发 client headers 在这里过滤。

### 2.2 路由判定与 direct 边界

1. `src/app/server/routes/inference.py:671-699` 保存原始 inbound payload，然后调用 `handle_bounded()`。
2. `src/app/pipeline/driver.py:489-515` 的 `handle_bounded()` 只负责整个 client request deadline；正常进入 `handle()`。
3. `src/app/pipeline/driver.py:169-219` 的 `handle()` 调用 `shape_request()`，按需翻译 request，最后把 payload 的 model 改为 resolved model并进入 `_drive()`。
4. `src/app/pipeline/driver.py:87-135` 的 `shape_request()` 调用 `decide_route()`、`apply_route()`，并应用路径级 headers policy与Anthropic专属request fixups。
5. `src/app/pipeline/routing.py:295-345` 的 `decide_route()` 先选 provider／model descriptor；若 descriptor 支持 inbound format 对应 endpoint，就选择该 endpoint，并令 `translation_required=False`。因此 inbound `/chat/completions` 加上支持 `ModelEndpoint.OPENAI_CHAT_COMPLETIONS` 的 model，就是 direct Chat Completions。
6. `src/app/pipeline/translation_driver/registry.py:172-207` 明确只把 Chat Completions 注册成 outbound request target 和 response source；没有 `inbound.from-openai-chat-completions`，也没有 Chat response writer。`tests/unit/pipeline/translation_driver/test_openai_chat_completions.py:560-565` 明确断言 Chat inbound translator 不存在。
7. 所以当前 `/chat/completions` 可成功服务的实质路径是 direct。若 inbound Chat request 被 routing 选到 Anthropic／Responses endpoint，`handle()` 在网络前因 `TranslatorNotFound` 失败，最终是 501；这不是可用的 translated `/chat/completions` 路径。

### 2.3 Driver 与 provider 调用链

1. `src/app/pipeline/driver.py:250-280` 的 `_drive()` 从 `DRIVERS[route.endpoint]` 取得 driver，构造共享 `LedgerBudget`，并传入 attempt deadline、response-header timeout、rate limiter、descriptor和token admission。
2. `src/app/pipeline/direct_driver/__init__.py:55-60` 把 `ModelEndpoint.OPENAI_CHAT_COMPLETIONS` 映射到 `OpenAIChatCompletionsDriver`。
3. `src/app/pipeline/direct_driver/openai_chat_completions.py:16-48` 的 `OpenAIChatCompletionsDriver` 只绑定 endpoint，所有执行与 retry 行为都继承 `DirectDriver`，没有 Chat 专属 retry 分支。
4. `src/app/pipeline/direct_driver/base.py:287-325` 的 `_prepare_and_send()` 在每次普通 attempt 上发布 `attempt.prepare`，建立最终 payload 副本，执行 token admission／rate-limiter acquire，然后调用 `_send()`。
5. `src/app/pipeline/direct_driver/base.py:462-489` 的 `_send()` 调用 `provider.send(endpoint, payload, descriptor=..., stream=context.stream, extra_headers=...)`；response-header timeout只包围provider send。
6. `src/app/pipeline/direct_driver/base.py:344-420` 的 `run()` 从 `context.begin_attempt()` 开始循环。provider／subscriber 在 response 交接前抛出的异常进入 `_handle_failure()`；成功 response 经过 rate limiter 和 success subscribers后才交给server delivery。

## 3. Buffered direct `/chat/completions`

### 3.1 共用 server 后半段

当 inbound body 的 `stream` 为 false：

1. driver／provider 返回一个已缓冲 `httpx2.Response`。
2. `src/app/server/routes/inference.py:996-1005` 以 `len(response.content)` 记录 upstream response bytes；只有当前 attempt 存在 response observer时才做provider-side body observation。
3. `src/app/server/routes/inference.py:1008-1025` 才解析 `response.json()` 并要求结果是 object。此处位于 driver retry loop之外；200 body非JSON或不是object会直接变成 `UPSTREAM` 502，不会再开attempt。
4. `src/app/pipeline/reply.py:24-53` 的 `response_payload()` 对 direct route 原样返回 body object，不做 response translation。
5. `src/app/pipeline/reply.py:70-81` 的 `reply_summary()` 对 inbound format不是Anthropic Messages的请求直接返回 `None`。
6. `src/app/server/routes/inference.py:1026-1059` 最终通过 `JSONResponse(payload, status_code=response.status_code)` 返回。因此成功JSON中未知字段会保留，但bytes会经历JSON decode／encode，不是byte-for-byte passthrough。

### 3.2 GitHub Copilot provider

- `src/app/model_provider/github_copilot.py:173-205` 把 Chat endpoint 分派到 `GhcApiClient.send_chat_completions()`。
- `src/app/model_provider/ghc_client/client.py:68-82,100-128` 使用 OpenAI SDK `post(..., stream=stream)`；`stream=False` 时 SDK／httpx 在call返回前读取body，异常位于 `_in_pipeline_terms()` 的归一化边界中。
- `src/app/server/composition.py:450-475` 把 OpenAI／Anthropic SDK 的 `max_retries` 设为 0，说明 retry 的唯一 owner 是本项目 driver，而不是 SDK 内建重试。
- 结论：GitHub Copilot direct buffered Chat 的 connect／timeout／status／non-stream body transport error，只要由 shared normalizer识别，就可进入 driver retry。不能据此推出 200 JSON semantic validation failure也会retry；它发生在server解析阶段，已经越过driver。

### 3.3 Xingchen provider

- `src/app/model_provider/xingchen/client.py:77-140` 在一个 `try` 中执行 `http_client.send(request, stream=stream)`；`stream=False` 时 body read 属于该await，失败经过 `normalize_upstream_error()`。
- 非成功status也在同一try中先读body、`raise_for_status()`、close，再归一化。
- 结论：Xingchen direct buffered Chat 的通常 transport／status failure同样能进入 driver retry；200 body后续JSON semantic validation仍在driver外。

### 3.4 CodeBuddy provider：direct buffered retry 的实际缺口

CodeBuddy 是这个问题最关键的 provider：

1. `src/app/model_provider/codebuddy.py:35-44,166-179` 声明所有 model 只支持 `OPENAI_CHAT_COMPLETIONS`，并把 send 交给 `CodebuddyClient.send_chat_completions()`；因此 inbound `/chat/completions` 指向 CodeBuddy model时天然是direct。
2. `src/app/model_provider/codebuddy_client/client.py:50-70` 无论client是否要求streaming，都把upstream body改成 `stream=true`，并用 `http_client.send(..., stream=True)` 只取得headers。
3. `src/app/model_provider/codebuddy_client/client.py:71-76` 的异常归一化try只包围 `send()`；它能把header前timeout／HTTP transport error变成 `UpstreamTimeout`／`UpstreamError`。
4. `src/app/model_provider/codebuddy_client/client.py:77-81` 对non-200 response执行 `await response.aread()`，但该body read已在上述try之外；如果status body读取本身tear，原始 `httpx2.ReadError` 等直接外逃，而且这条分支没有 `finally` close。
5. `src/app/model_provider/codebuddy_client/client.py:82-87` 在client `stream=False` 时调用 `aggregate_stream(response)`；虽然finally会close response，但aggregation的异常没有经过 `normalize_upstream_error()`。
6. `src/app/model_provider/codebuddy_client/client.py:90-191` 的 `aggregate_stream()` 读取SSE，碰到 `[DONE]` 才break，但没有记录它是否出现；JSON解析失败会被跳过；clean EOF、缺 `[DONE]`、缺明确 `finish_reason` 都会继续构造synthetic 200，并用 `finish_reason or "stop"` 补成成功结束。
7. 原始 `httpx2.ReadError` 到达 `src/app/pipeline/direct_driver/base.py:438-460` 后，`classify()` 不认识它，按closed set返回 `ABORT`；driver不调用 `LedgerBudget.take_for()`，所以即使默认network budget为9，也不会retry。
8. 若body以clean EOF结束，则根本没有异常，provider返回synthetic 200，driver发布success events；retry机制没有可判断的失败。

无网络最小探针直接调用了当前 `aggregate_stream()`：

- source在一个partial SSE chunk后抛 `httpx2.ReadError("body tore")`，实际外逃类型仍是 `httpx2.ReadError`；`classify(error)` 返回 `abort`，`reason_for(error)` 返回 `None`。
- 同一异常若显式经过现有 `normalize_upstream_error()`，会成为 `UpstreamError`，随后 `classify()` 返回 `retry`。这证明缺的是provider body-read边界接入现有normalizer，而不是retry ledger没有能力。
- source在一个partial SSE chunk后clean EOF、无 `[DONE]`，实际聚合结果是HTTP 200、content为 `partial`、`finish_reason` 为 `stop`。这证明该形态不会触发retry，并且当前结果会伪装成正常完成。

**可行动结论，证据权重强**：direct buffered `/chat/completions` 的shared retry loop存在且可用；当前失效点是CodeBuddy把upstream streaming body聚合成buffered response时，body transport exceptions未归一化，terminal completeness又未验证。它不是整个Chat driver没有retry，也不是所有provider的buffered body都在同一处失效。

## 4. Client-requested streaming `/chat/completions`

### 4.1 为什么仍是 buffered one-shot

1. driver仍先取得response headers；`src/app/server/routes/inference.py:745-764` 只有 `context.stream` 为true才进入streaming delivery选择。
2. `src/app/pipeline/delivery_policy.py:51-64` 的 `delivers_blocks()` 对任何inbound Chat Completions返回false，因为没有Chat client framer。
3. `src/app/pipeline/delivery_policy.py:84-105` 的 `framer_for()` 因direct route不需要translation而返回 `None`。
4. `src/app/server/routes/inference.py:765-806` 因此构造 `one_shot_delivery()`，把idle timeout、attempt deadline、byte counting和client deadline包在upstream iterator外，但没有assembler、framer、`ReplaySupport` 或 `ContinuationSupport`。
5. `src/app/pipeline/delivery/stream.py:295-320` 的 `one_shot_delivery()` 缓冲所有upstream bytes，正常结束时一次yield；发生Exception时若已有bytes，先yield partial bytes，再重新抛异常。
6. 源码docstring `src/app/pipeline/delivery/stream.py:304-306` 明确写明这条路径没有replay、没有keep-alive，也没有dialect error frame。

因此 `stream=true` 只保留upstream的SSE wire shape，不保留下游增量时序。完整upstream stream会byte-for-byte一次写给client；body tear在response headers已经发出后无法改HTTP status，且不会开第二个attempt。已有partial bytes会先写出，随后连接以异常结束；零bytes tear则没有body。

### 4.2 为什么 block-stream replay 不能覆盖它

- `src/app/server/routes/inference.py:807-994` 只有 `framer is not None` 才构造 `UpstreamSource`、assembler、`_reopen()`、`ContinuationSupport` 与 `ReplaySupport`。
- `src/app/pipeline/delivery/stream.py:371-420,423-596` 的 `stream_delivery()`／`_deliver()` 依据是否已提交block决定transparent replay或hand-over。这些位置事实在one-shot路径不存在。
- `src/app/pipeline/retry.py:114-158` 的 `decide_stream_ending()` 也只对block delivery的 `downstream_opened`／`committed_blocks` 有意义。
- 与之对照，Anthropic／Responses inbound被翻译到Chat upstream时，client leg有自己的framer，`assembler_for()` 会选 `ChatCompletionsAssembler`（`src/app/pipeline/delivery_policy.py:128-155`），所以那条“Chat upstream”路径可block-deliver／replay；它不是inbound `/chat/completions` direct路径。

**可行动结论，证据权重强**：direct streaming `/chat/completions` 的post-header body tear无replay是当前显式实现，不是偶然漏接一个callback。若要改变，需要定义Chat client leg的block／framing语义，或为whole-stream one-shot单独定义replay合法性；不能直接声称现有 `ReplaySupport` 已覆盖。

## 5. Retry 与异常分类

### 5.1 Driver retry

- `src/app/pipeline/exceptions.py:18-24,26-166` 定义闭集。`UpstreamError` 和 `PipelineRetry` 为retryable；`UpstreamRejected`、`PipelineAbort`、token admission failure以及未知异常均abort。
- `src/app/model_provider/upstream_errors.py:31-58,144-189` 负责把provider client异常归一化：timeout → `UpstreamTimeout`；429 → `UpstreamRateLimit`；非retryable 4xx → `UpstreamRejected`；其余status error → `UpstreamError`；SDK／httpx transport和bare `H2Error` → statusless `UpstreamError`；未知异常返回 `None`。
- retryable status allowlist是 `{401, 408, 409, 425, 429, 499, 500, 502, 503, 504}`（`src/app/model_provider/upstream_errors.py:31-35`）。
- `src/app/pipeline/retry.py:36-58` 把timeout／statusless failure归为 `network`，401归为 `githubTokenExpired`，429和其余retryable status归为 `serverError`。
- `src/app/config/schema.py:237-261` 默认 `max_total=20`、`network.max_retries=9`、`serverError.max_retries=9`、`githubTokenExpired.max_retries=0`。
- `src/app/pipeline/direct_driver/base.py:163-187,438-460` 的 `LedgerBudget` 先拒绝drain中的新attempt，再按reason消费shared／per-reason budget；budget耗尽后返回 `PipelineAbort(cause=original_error)`。没有独立backoff；rate limiter的 `acquire()` 是另一个等待机制。

### 5.2 失败如何到达 client

- `src/app/server/routes/inference.py:675-691,701-714` 处理 `handle_bounded()` 抛出的失败和driver outcome中的terminal error。
- `src/app/pipeline/error_classify.py:84-135,222-269` 用原始upstream status分类client-visible error；`PipelineAbort.cause` 被解包，因此budget耗尽不会把upstream 503改写成502。
- `src/app/server/http_errors.py:76-103` 对direct upstream failure，在有 `source_bytes` 时转发upstream自身bytes、status与可转发headers；没有upstream bytes或属于translated／proxy failure时，按inbound dialect写代理envelope。
- `src/app/errors.py:145-160` 的proxy category status包括：NETWORK／UPSTREAM → 502，TIMEOUT → 504，INTERNAL → 500，NOT_IMPLEMENTED → 501。
- CodeBuddy aggregation期raw `ReadError` 因未归一化最终成为INTERNAL 500的OpenAI-style error envelope，不是NETWORK 502，也不会retry。clean EOF则成为synthetic 200。

### 5.3 Driver 外、当前不 retry 的失败

1. 任一provider返回的200 buffered body在 `inference.py:1008-1025` 解析为非JSON／非object：driver已结束，返回502，不retry。
2. direct Chat client-requested streaming的post-header body tear：one-shot delivery无replay。
3. CodeBuddy non-stream aggregation body tear：虽然发生在 `provider.send()` 尚未返回时，但原始异常未映射进closed set，所以driver abort。
4. CodeBuddy clean EOF／malformed SSE line／无明确finish reason：聚合器当前可把它们吸收为synthetic success，retry没有失败信号。

## 6. “direct buffered reply” 的另一处独立缺口

题目写的是“retry”，但当前living deferred中存在一个措辞极相近且确实未完成的 **reply** 缺口，必须分开记录，不能把二者混作同一个问题：

- `src/app/pipeline/request.py:113-128` 的 `begin_attempt()` 只在 `target_format is OPENAI_RESPONSES` 时创建 `ResponsesObserver`。
- `src/app/server/routes/inference.py:996-1005` 只在observer存在时观察buffered provider body。
- `src/app/pipeline/reply.py:70-81` 的通用 `reply_summary()` 对Chat inbound返回 `None`。
- 所以direct buffered `/chat/completions` 即使成功，reasoning、tool calls、native `finish_reason` 与usage也不会进入统一provider response observation／完成行。
- `.dev/docs/tui/deferred.md:7-15` 已把这件事登记为“Direct buffered `/chat/completions` 入站的回复汇总仍为空”，并给出“静态调用链足以确认”的证据等级。

这与transport retry正交：补whole-body observation不会自动修复CodeBuddy body tear；修复body error normalization也不会自动产生Chat reply summary。

## 7. 测试覆盖矩阵

| 层级 | 已覆盖 | 准确位置 | 未覆盖／不能证明 |
|---|---|---|---|
| 路由与输入 | Chat route format、三个OpenAI prefix、stream flag、model validation、Azure deployment model | `tests/unit/server/test_server_inbound.py:16-29,44-80,108-125` | 不覆盖provider send／retry |
| direct Chat buffered happy path | 三个普通路径均路由到 `/chat/completions` 并返回JSON | `tests/int/test_pipeline_app.py:1435-1446` | fixture是GitHub provider；不检查retry、reply summary或durable response observation |
| direct Chat stream happy path | upstream Chat SSE whole且byte-for-byte返回 | `tests/int/test_pipeline_app.py:1425-1471` | 不覆盖body tear后retry；实际上断言的是one-shot现状 |
| one-shot单元 | 单次完整写、空body、guard触发时partial bytes先交付 | `tests/unit/pipeline/delivery/test_one_shot_delivery.py:34-107` | 没有replay；这些测试确认no-replay路径的输出，不证明retry |
| shared direct driver retry | `UpstreamError(502)` 后成功第二次、budget exhaustion、unknown exception abort、drain refusal | `tests/unit/pipeline/test_direct_driver.py:434-472,531-647` | helper实例化的是 `AnthropicMessagesDriver`，依靠共享基类结构间接覆盖Chat driver；没有 `OpenAIChatCompletionsDriver`／CodeBuddy direct route专属retry test |
| retry reason与默认预算 | reason mapping、per-reason／shared total | `tests/unit/pipeline/test_retry_strategies.py:22-88` | 不证明provider raw exception已进入closed set |
| GitHub client边界 | endpoint path／auth、stream response未消费 | `tests/component/model_provider/ghc_client/test_client.py:66-113` | 没有direct Chat buffered body tear end-to-end retry test |
| upstream error normalizer | 4xx／5xx／429／401／timeout／transport／H2，及direct error bytes保真 | `tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py:48-150,166-347` | 直接测试normalizer，不证明每个provider的每个body read都调用它 |
| CodeBuddy client | 强制upstream `stream=true`、stream passthrough、成功content／tool／usage聚合、400、connect timeout | `tests/component/model_provider/codebuddy_client/test_codebuddy_client.py:60-174` | 无aggregation期 `ReadError`、non-200 body read tear、missing `[DONE]`、malformed event、完整app retry测试 |
| CodeBuddy provider | 所有model只支持Chat、endpoint gate、send table | `tests/unit/model_provider/test_codebuddy.py:70-132` | 无inference route integration；`tests/int/` 搜索不到CodeBuddy |
| Chat translator registry | Chat可作为outbound target／response source，且没有inbound translator | `tests/unit/pipeline/translation_driver/test_openai_chat_completions.py:531-565` | 证明translated inbound Chat不可用，不是retry test |
| block-stream replay | client尚未见block时body tear会transparent replay | `tests/int/test_pipeline_app.py:6813-6861` 及后续replay cases | 使用Anthropic／Responses client framer，不能外推到direct Chat one-shot |
| direct buffered Responses observation | provider body在client translation前被观察，provider-level failure进入记录 | `tests/int/test_pipeline_app.py:5429-5508` | 没有Chat等价测试；正好印证response observer只覆盖Responses |
| error dialect | Chat／Responses／Anthropic的proxy-generated envelope，translated Chat unsupported 501 | `tests/int/test_error_envelope.py:167-197,251-261` | direct Chat upstream error与CodeBuddy retry并未端到端覆盖 |

本次运行的针对性测试为18项，全部通过，1个无关deprecation warning：

- `tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`
- `tests/unit/pipeline/delivery/test_one_shot_delivery.py`
- `tests/unit/pipeline/test_direct_driver.py::test_retryable_upstream_error_is_attempted_again`
- `tests/int/test_pipeline_app.py::test_chat_completions_endpoint_is_served`（参数化三路径）
- `tests/int/test_pipeline_app.py::test_chat_completions_streams_are_delivered_whole_and_verbatim`
- `tests/unit/pipeline/translation_driver/test_openai_chat_completions.py::test_no_chat_inbound_translator_is_registered`

这些绿灯证明现有行为未被误读；它们不证明CodeBuddy aggregation interruption可retry，因为测试没有构造该failure surface。

## 8. 结论与证据权重

### 8.1 强到足以据此行动

1. **`/chat/completions` 的共享pre-response retry并未缺失。** Chat driver是共享 `DirectDriver` 的薄绑定；归一化后的 `UpstreamError` 会按同一ledger retry。依据是完整静态调用链、shared driver unit tests、normalizer tests和SDK retry被显式关闭的composition。
2. **CodeBuddy direct buffered Chat的body interruption retry确实失效。** aggregation期body exception越过normalizer，raw `httpx2.ReadError` 被closed classifier判为abort；clean EOF／缺 `[DONE]` 还会被合成正常200。依据是源码控制流加无网络运行探针，两者一致。
3. **direct client-streaming Chat的body tear没有delivery replay。** `framer_for()` 返回 `None` 后走 `one_shot_delivery()`；`ReplaySupport` 只在另一分支构造。依据是静态分支唯一性、one-shot unit tests和direct Chat integration happy path。
4. **direct buffered Chat的reply／response observation仍为空。** `ResponsesObserver` 的构造gate和 `reply_summary()` 的inbound gate都排除Chat。依据是静态调用链、Responses对照integration tests及现有deferred记录。

### 8.2 有支持，但不能单独决定行为

- Git历史显示CodeBuddy client和相关组件测试由同一个提交 `fcb6982` 一次引入，此后该文件无后续commit；这支持“初始切片未覆盖interruption”而非“后续回归”的倾向判断。历史本身不说明产品希望如何处理clean EOF，因此不能作为修复契约。
- `aggregate_stream()` 注释称其镜像reference converter；即使reference也如此，也只能解释来源，不能把“吞掉terminal缺失”自动提升为本项目已裁定行为。

### 8.3 仍不确定

1. 没有真实CodeBuddy upstream cassette或本次live call，无法判断body tear、clean EOF、缺 `[DONE]`、malformed event在真实流量中的发生频率，也不能据此排优先级。
2. 对clean EOF／malformed SSE，产品应“retry”“返回upstream failure”还是接受partial synthetic body，需要进入Spec／用户裁决；当前代码没有可援引的明确裁定。
3. 对direct `stream=true` Chat，现有no-replay是明确实现与既有测试，但若要改变，必须先定义在没有block framer时何时允许whole-stream replay，以及partial bytes是否已经构成不可回滚交付。
4. 对任意provider的buffered 200 malformed JSON／非object response，当前是502且不retry；是否纳入retry taxonomy没有现成裁决。
5. deferred中的direct buffered Chat response observation只给出候选方向，尚未进入行为Spec；本报告只确认现状，不把候选当裁决。

## 9. 排除但未采用的解释／路线

1. **“Chat Completions没有retry loop。”** 排除。`OpenAIChatCompletionsDriver` 明确复用 `DirectDriver.run()`；缺的是部分provider body-read failure没有进入retryable closed set，以及direct one-shot body阶段没有replay。
2. **“所有direct buffered Chat都因同一原因不能retry。”** 排除。GitHub SDK `stream=False` 和Xingchen `httpx.send(stream=False)` 的body read均位于现有归一化边界；CodeBuddy因强制upstream streaming再聚合而不同。
3. **“OpenAI SDK会自行retry，所以driver wiring不重要。”** 排除。production composition显式设置 `max_retries=0`，本项目driver是retry owner。
4. **“现有block delivery replay会接住direct Chat stream tear。”** 排除。Chat client leg无framer，分支在构造 `ReplaySupport` 之前已经返回one-shot response。
5. **“给Chat注册inbound translator即可修复direct retry。”** 不采用。当前成功路径本来就是direct，CodeBuddy聚合失败发生在provider内部；新增translator解决的是另一条目前不支持的translated inbound路线。
6. **“Responses observer已统一覆盖所有OpenAI协议，因此Chat reply summary也有了。”** 排除。observer construction只看 `target_format is OPENAI_RESPONSES`，Chat buffered成功没有observer；`reply_summary()` 也明确拒绝非Anthropic inbound。
7. **“已有generic driver retry test足以证明CodeBuddy buffered retry。”** 排除。该test直接喂给fake provider一个已经归一化的 `UpstreamError`；它绕过了真正有问题的 `aggregate_stream()` raw exception边界。
8. **“缺 `[DONE]` 只是无害clean EOF。”** 不采用。当前聚合器会把未证实完整的partial content补成 `finish_reason="stop"`，这是可观察的成功声明；是否允许不能由实现现状替代产品裁决。
9. **“题目中的retry就是deferred所说的reply。”** 不采用。两处缺口都真实存在且机制不同；本报告分别还原，避免靠猜测改写问题。

## 10. 设计前置摘要

若后续设计目标确实是修复 **CodeBuddy direct buffered `/chat/completions` retry**，最小事实边界是：失败发生在provider为non-stream caller聚合upstream SSE期间；它仍处于 `provider.send()` 尚未返回、client尚未收到response的阶段，位置上允许整个attempt透明重试；现成normalizer、driver loop和shared ledger已经具备能力，当前缺的是body read exception normalization与“完整SSE”的可判定失败信号。

若目标是修复 **direct buffered `/chat/completions` reply summary**，则是另一条工作：需要Chat provider-side whole-body observer或把现有Chat response reader接入统一observation owner，并保持console与durable schema从同一记录投影。它不能替代retry修复。

若目标是修复 **direct `stream=true` `/chat/completions` body tear**，则又是第三条工作：现有downstream one-shot交付没有block frontier、没有framer、没有replay，必须先在Spec中定义whole-stream replay与partial delivery的语义，不能把buffered provider聚合修复直接外推到这里。
