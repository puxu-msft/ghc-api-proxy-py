# 异构模型 `POST /v1/messages/count_tokens` 链路独立评审

## 评审基线与结论

评审对象是主工作树 commit `35333867dc5ce9374c3f9ad8ec908072dd6442a3` 的当前文件内容；截至取证时，本报告引用的生产文件和测试文件均没有工作树改动。仓库其他位置存在与本任务无关的已修改或未跟踪内容，本评审没有读取其语义，也没有修改生产代码。请求指定的 `my-skills:as-reviewer` 不在当前可用技能列表中；本次采用独立评审者角色，并加载了 `verifying-authoritative-claims`。

**总判定：needs-fix。** 异构 Responses 路由的正常计数主链路顺序正确，默认订阅者不会破坏估算，`estimated: true` 也不会使当前 Claude Code 2.1.241 解析失败；但存在一项高置信度的协议行为缺陷：同一个 Anthropic `count_tokens` 请求体会因目标模型路由不同而得到不同的合法性判定，`messages` 非列表在同构路由返回 400，在异构 Responses 路由却被静默折成空输入并返回 200、`input_tokens: 1`。此外，Responses 校准在当前生产接线中没有自动学习入口，尽管普通推理完成后的真实 usage 已被读取并持久化。

发现计数：1 项 Major、1 项 Moderate、1 项测试覆盖缺口。其余核查项为已确认的正确行为或有条件风险，不计作缺陷。

## 1．成功响应形状、序列化、HTTP 状态与 Claude Code 兼容性

**结论：当前 Claude Code 2.1.241 不会因额外的 `estimated: true` 字段出问题；它会忽略该字段并把 `input_tokens` 当作普通数字使用。该结论对 Claude Code 2.1.241 足够强，可据此行动；不能无条件外推到实行“键集合必须精确相等”的未知第三方客户端。前提是响应为成功的 JSON，且 `input_tokens` 是 number。**

异构 Responses 路由不会调用上游计数器。`handle_count_tokens` 在本地提供者获胜时返回 `{"input_tokens": result.tokens, "estimated": True}`，见 `src/app/pipeline/driver.py:330-341`。HTTP 边缘不再包一层对象，直接执行 `JSONResponse(counted)`，见 `src/app/server/routes/inference.py:212-239`。因此 wire body 是紧凑 JSON，例如行为探针得到 `{"input_tokens":7,"estimated":true}`。

`JSONResponse` 未显式传 `status_code`，所以成功状态是 200。Starlette 1.6.0 的实现默认 `status_code=200`、`media_type="application/json"`，并以紧凑 UTF-8 JSON 序列化，见 `.venv/lib/python3.14/site-packages/starlette/responses.py:181-201`；基类自动补 `content-length` 和 `content-type`，见同文件 `:55-81`。成功路径没有额外业务头；行为探针实际得到 `content-type: application/json` 与随 body 长度变化的 `content-length`。这条链路没有返回 `anthropic-version` 或 request id 响应头，但当前 Claude Code 的计数调用不读取这些头。

当前安装版本由 `claude --version` 确认为 2.1.241。其内置 Anthropic SDK 的 beta count 方法直接把 `/v1/messages/count_tokens?beta=true` 的 JSON 结果返回，见 `/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:12377-12380`；Claude Code 消费端只检查 `typeof d.input_tokens !== "number"`，随后返回 `d.input_tokens`，见同文件 `:366941-366950`。它没有检查响应对象的键集合，也没有读取 `estimated`。所以额外字段不会触发解析错误、重试或 fallback；代价只是 Claude Code 看不到“不确定性”，会把估算值当作普通计数值。

对于“所有 Anthropic 协议客户端都兼容”的全称判断，现有证据不足。一个自行实现严格 JSON Schema 且禁止未知字段的客户端理论上可能拒绝该扩展，但本次没有发现这样的实际客户端，故这只是一项条件性兼容风险，不足以单独提出修复要求。

## 2．错误路径及异构／同构差异

### 2.1 共同的 HTTP 错误渲染

**结论：未知模型、能力缺失、显式 endpoint 不支持、翻译器缺失和同构 Messages 校验失败都通过同一个错误边缘返回；这些错误均为 400、JSON、无业务错误头。置信度高，前提是异常到达 `handle_count_tokens` 的 `except`，而不是发生在 JSON 解析之前。**

计数分支捕获异常后使用 `error_body`、`error_status`、`error_headers`，见 `src/app/server/routes/inference.py:196-211`。错误状态映射把 `ProviderError`、`RoutingError`、`TranslatorNotFound`、`CountTokensRequestError` 和 `TranslationRefused` 统一映射到 400，见 `src/app/server/http_errors.py:24-56`。错误体固定为 `{"error":{"type": <异常类名>, "message": <异常文本>, ...}}`，见同文件 `:71-89`。这些错误不是 rate limit，因此 `error_headers` 返回空映射，见同文件 `:58-69`；Starlette 仍补 `content-length` 和 `content-type: application/json`。

| 路径 | 实际状态与 body | 文件证据 | 异构特有差异判断 |
|---|---|---|---|
| 模型未知 | 400，`{"error":{"type":"UnknownModel","message":"<provider> does not offer model '<id>'"}}` | `src/app/pipeline/routing.py:85-95`；`src/app/model_provider/types.py:22-30`；`src/app/server/http_errors.py:36-44,71-89` | 无。路由在选择目标格式前失败，同构和异构没有分叉。 |
| 模型没有任何已知／可用 endpoint | 400，`CapabilityMissing`，消息为 `<provider> advertises no endpoints for model '<id>'` | `src/app/pipeline/routing.py:92-97`；`src/app/model_provider/types.py:33-43` | 无。也是目标格式选择前失败。注意 Responses-only 模型不属于此类，它有可用 endpoint，会正常翻译并估算。 |
| 客户显式要求模型不支持的格式，例如 `gpt-model@anthropic-messages` | 400，`EndpointNotSupported` | `src/app/pipeline/routing.py:98-102`；`src/app/model_provider/types.py:46-51` | 这是显式格式约束的预期拒绝，不是异构路径意外差异。 |
| 模型只有 `/chat/completions` | 400，`{"error":{"type":"TranslatorNotFound","message":"no translator registered as outbound.to-openai-chat-completions"}}` | fallback 会选择首个可用 endpoint，见 `src/app/pipeline/routing.py:103-120,125-140`；默认 registry 只注册 Anthropic 与 Responses outbound，见 `src/app/pipeline/translation_driver/registry.py:130-156`；缺失 outbound 抛错见同文件 `:83-107` | 差异有正当原因：该请求没有可执行的翻译链，普通 `/v1/messages` 发送同样会在翻译阶段失败。 |
| body 不是 JSON | 400，`{"error":{"message":"body is not valid JSON"}}` | `src/app/server/routes/inference.py:158-162` | 无。尚未读取模型。 |
| JSON 顶层不是 object | 400，`{"error":{"message":"body must be an object"}}` | `src/app/server/routes/inference.py:163-165` | 无。尚未读取模型。 |
| model 缺失、空白或非 string | 400，`InboundRequestError` 错误体 | `src/app/server/inbound.py:40-50`；`src/app/server/routes/inference.py:168-173` | 无。尚未路由。 |

### 2.2 Major：异构 Responses 路由绕过了 Messages body 合法性校验

**严重度：Major。置信度：高，足够据此修复。成立前提：输入是可解析 object、携带有效 model，模型路由到 Responses，并且 Messages 结构在翻译器的宽松读取中被丢弃或强制转换，而不是触发 `TranslationRefused` 的特定字段。**

同构 Anthropic 路由在估算前调用 `_countable(context.payload)`，见 `src/app/pipeline/driver.py:271-276`。`_countable` 用 `MessagesRequest.model_validate` 校验，并把 `ValidationError` 转成 `CountTokensRequestError`，见同文件 `:343-353`；该模型要求 `messages: list[AnthropicMessage]`，见 `src/app/models/anthropic.py:27-30,47-50`。因此 `messages: "not a list of messages"` 返回 400。

异构 Responses 路由不经过 `_countable`。Anthropic reader 对非 list 的 `messages` 直接采用空列表，对 list 中非 mapping 的条目也直接丢弃，见 `src/app/pipeline/translation_driver/anthropic_messages.py:121-133`；它还把若干字段用 `str(...)` 强制转换，见同文件 `:73-118`。翻译后的空 `input` 被 `estimate_responses_input` 估为最小值 1，见 `src/app/tokenization/estimators.py:120-137`，随后成功路径返回 200 estimated，见 `src/app/pipeline/driver.py:337-341`。

本次以现有 `make_client` 做了一个局部行为探针，得到以下可复现反例：`gpt-model` 加 `messages: "not a list of messages"` 返回 200、`{"input_tokens":1,"estimated":true}`；相同 body 只把模型换成 `claude-model`，返回 400、`CountTokensRequestError`。这不是“估算器不同”所需的差异，而是同一个 Anthropic endpoint 的请求合法性被目标模型格式决定。现有普通推理翻译路径也使用同一个宽松 reader，见 `src/app/pipeline/driver.py:142-150`，所以计数结果确实描述了当前发送路径会构造的空 Responses 请求；但这不消除对外协议不一致，只说明缺陷由计数链路与普通发送链路共享。

## 3．翻译、payload 修改与估算时序

**结论：默认生产链路中顺序正确，`estimate_responses_input` 读到翻译产物，并且 `context.payload["model"] = route.model_id` 不改变估算结果。置信度高。前提是使用默认三个 built-in subscribers；注入的自定义 subscriber 可以在估算前有意修改 payload。**

实际顺序是：先 `shape_request`，再在 `translation_required` 时调用 translator 并执行 `context.payload = translated`，再写 resolved model，随后设置 `COUNTING_ONLY` 并运行 `EVENT_ATTEMPT_PREPARE`，最后按 `route.target_format` 调用估算器，见 `src/app/pipeline/driver.py:247-276`。因此 Responses 估算器收到的对象就是 translator 产出的 dict 在订阅者处理后的当前版本，而不是原始 Anthropic body。

默认订阅者不会在异构 Responses 计数路径上改写该对象。注册集合和顺序是 server-tool capability、hosted web-search gate、blank-text blocks，见 `src/app/pipeline/subscribers/__init__.py:34-67`。`adapt_server_tools` 对非 Anthropic target 立即返回，见 `src/app/pipeline/subscribers/server_tools.py:235-249`；`gate_hosted_web_search` 对 `COUNTING_ONLY` 立即返回，见 `src/app/pipeline/subscribers/hosted_web_search.py:79-105`；`drop_blank_text_blocks` 对非 Anthropic target 立即返回，见 `src/app/pipeline/subscribers/blank_text.py:69-76`。估算之后仅创建 shallow copy 并从用于 provider chain 的 copy 删除 `stream`，见 `src/app/pipeline/driver.py:313-324`；本地 counter 明确不重算，使用已保存的 `estimate`，见同文件 `:302-304`。

resolved model 写入发生在估算之前，见 `src/app/pipeline/driver.py:251-276`，但 Responses estimator 只读取 `instructions`、`tools` 和 `input`，完全不读取 `model`，见 `src/app/tokenization/estimators.py:113-137`，所以该赋值对当前估算值没有影响。它对实际发送仍有必要，因为翻译器起初携带的是客户端请求的模型名。

现有判别力最强的测试是 `test_a_translated_route_is_counted_from_the_body_it_would_actually_send`：它独立翻译同一 body、写入 model，先证明 Anthropic 与 Responses 两个估算器在该输入上给出不同值，再断言 handler 结果等于 Responses 翻译产物的估算，见 `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:219-265`。这足以排除“测试碰巧因两个估算器同值而绿”的解释。

自定义 subscriber 是有条件例外。`build_chain` 接受外部 registry，并把 built-ins 注册到同一 registry，见 `src/app/server/composition.py:447-507`；自定义 `attempt.prepare` handler 可以修改 payload。普通发送 driver 同样在该 event 之后重新复制 `context.payload` 再发送，见 `src/app/pipeline/direct_driver/base.py:136-151`，所以“估算看到 subscriber 的改写”本身是对齐真实请求的设计，而不是覆盖翻译结果的缺陷。只有自定义 handler 在 counting leg 做与 send leg 不一致的副作用时才会产生新问题；默认集合没有这种行为。

## 4．Responses 校准与已有地面真值

### 4.1 Moderate：当前生产接线不会自动学习 Responses 校准因子

**严重度：Moderate。置信度：高，足够据此安排修复。成立前提：讨论的是当前服务器生产接线中的自动学习，而不是手工预置 snapshot、测试直接调用 `learn()`，或未来新增消费者。**

Responses 路由把 `protocol` 设为 `openai-responses` 并计算本地 estimate，见 `src/app/pipeline/driver.py:270-282`；但 `upstream_counts` 只有 Anthropic target 才为真，见同文件 `:306-323`。因此默认 provider 顺序下 Responses 一定先记 `ghc:no-counter-for-openai-responses`，再由 local 返回。生产 handler 只有在 `result.provider == "ghc"` 时调用 `calibration.learn(...)`，见同文件 `:325-341`，这个条件在 Responses 路由上不可达。没有 snapshot 时，校准 engine 找不到 key 就返回 factor 1.0，见 `src/app/tokenization/calibration.py:78-107`。

“永远学不到”需要收窄：engine 可以从 snapshot 恢复任意 protocol/model key，见 `src/app/tokenization/calibration.py:119-158`，也可由代码直接调用 `learn()`。仓库另有 `AnthropicTokenCountingService` 在上游 Anthropic count 成功或 prompt-limit 错误时学习，见 `src/app/tokenization/service.py:41-88`；但它硬编码 protocol `anthropic`，并且生产 `src/app` 中没有构造或调用该 service 的位置，只有 package export 与单元测试。当前 server 只 load／flush `chain.tokenization`，见 `src/app/server/pipeline_app.py:73-85`。所以准确结论是：**Responses key 在当前生产自动路径上没有学习入口；除非外部预置状态，它会一直使用 1.0。**

### 4.2 已有真实 usage 被读取并持久化，但没有喂给校准

**结论：是。置信度高。成立前提：普通 Responses 请求完成且 upstream usage 存在、可解析。缓存场景下应以 upstream 的总 input，或规范化后的 fresh + cache_read + cache_creation 之和作为与完整 payload estimate 对比的 real 值。**

Responses buffered 转换器会解析 `usage.input_tokens`、cache details、output 和 total，并保留 exact `upstream_input_tokens`，见 `src/app/protocols/responses_anthropic.py:225-291`；转换结果把 exact facts 放在 `usage_facts`，见同文件 `:124-140`。不过 buffered reply 的调用者只读取 translation losses，不消费 `usage_facts`，见 `src/app/pipeline/reply.py:19-38`。它仍把规范化后的 Anthropic usage 放进返回 payload，随后 `reply_summary` 生成 `Terminal`，见 `src/app/pipeline/reply.py:55-66`，HTTP 边缘再把 terminal usage 吸收到 trace，见 `src/app/server/routes/inference.py:481-512`。

Responses streaming assembler 在 terminal event 上直接读取 upstream `response.usage`，既保存规范化 usage，也保存原始 `upstream_usage`，见 `src/app/pipeline/delivery/formats/openai_responses.py:535-543,588-598`。stream 完成时 trace 吸收 terminal，见 `src/app/server/routes/inference.py:535-556`。`RequestTrace.absorb` 把规范化 usage 放进 trace，见 `src/app/observability/request_trace.py:177-188`；`log_completion` 将其交给 `RequestLine` 并调用持久化 writer，见同文件 `:200-245`；writer 把整个 line 作为每日 JSONL 追加，见 `src/app/observability/request_log_file.py:31-49`。

因此项目已经持有足以作为校准地面真值的数据。对于 Responses，raw `usage.input_tokens` 是完整 upstream input；规范化记录会把 cache 部分拆成 `input_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`，转换公式见 `src/app/protocols/responses_anthropic.py:248-283`。但普通请求完成路径没有任何 `calibration.learn` 调用；生产 handler 唯一的调用仍是 count_tokens 的 Anthropic-ghc 分支 `src/app/pipeline/driver.py:337-339`。这是“真值已记录、未用于校准”的直接接线缺口。

## 5．`COUNTING_ONLY` 后的订阅者与资源占用

**结论：默认注册的三个 `EVENT_ATTEMPT_PREPARE` 订阅者在异构 Responses 计数路径上全部无副作用；该路径也不会取得 DirectDriver 的 rate limiter／并发配额。置信度高。前提是生产使用 `register_builtin_subscribers` 的默认集合，没有额外注入自定义 subscriber。**

实际注册集合只有三项，且测试把集合与顺序锁定为 `(server-tool-capability, hosted-web-search-gate, blank-text-blocks)`，见 `src/app/pipeline/subscribers/__init__.py:34-67` 与 `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:33-75`。

1. `builtin:server-tool-capability`／`adapt_server_tools`：异构 target 是 Responses，函数在 `src/app/pipeline/subscribers/server_tools.py:242-243` 立即返回，不读取或改写 payload。
2. `builtin:hosted-web-search-gate`／`gate_hosted_web_search`：target 符合 Responses，但在看到 `COUNTING_ONLY` 后于 `src/app/pipeline/subscribers/hosted_web_search.py:94-98` 返回；不会移除 tools，也不会因 feature off 或 model 未列入而拒绝。
3. `builtin:blank-text-blocks`／`drop_blank_text_blocks`：仅作用于 Anthropic target，在 `src/app/pipeline/subscribers/blank_text.py:69-76` 返回，不改写 translated Responses payload。

计数路径只执行 `context.begin_attempt()` 和订阅者循环，见 `src/app/pipeline/driver.py:263-268`，没有构造或运行 `DirectDriver`。普通请求的 rate limiter acquire 位于 DirectDriver 的 prepare event 之后，见 `src/app/pipeline/direct_driver/base.py:136-151`，所以计数 handler 不会到达它。对于 Responses，`upstream_counts=False`，连 provider 的 count HTTP 调用也不会发生，见 `src/app/pipeline/driver.py:306-324`。因此没有上游请求、rate-limit token 或 driver retry budget 占用；唯一资源是本地翻译、subscriber dispatch 与 tokenizer CPU。

## 6．现有测试对异构 count_tokens 的覆盖

**结论：已有一项判别力很强的 unit test 和三项 HTTP／行为侧测试确实穿过 Responses 的 `translation_required=True` 计数路径；但异构非法 Messages body、chat-completions-only 的具体 HTTP 错误体、以及完整 Responses usage→calibration 接线没有覆盖。置信度高，依据是逐项核对测试所用 catalog endpoint 与断言。**

### 6.1 真正覆盖 `translation_required=True` 且 target 为 Responses

- `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:219-265` 的 `test_a_translated_route_is_counted_from_the_body_it_would_actually_send`：直接调用 `handle_count_tokens`，provider 只支持 Responses；独立构造翻译产物并证明两个估算器值不同，再断言返回值来自 Responses estimator。它是估算时序与产物选择的最强覆盖。
- `tests/int/test_pipeline_app.py:1258-1276` 的 `test_count_tokens_estimates_locally_for_a_model_with_no_upstream_counter`：通过真实 ASGI endpoint，`gpt-model` 的 catalog 只支持 `/responses`，catalog 证据见同文件 `:61-68`；断言 200 estimated 且没有上游 count 调用。它穿过翻译分支，但没有用差异化输入证明估算器读了哪一份 body。
- `tests/int/test_pipeline_app.py:1832-1851` 的 `test_a_count_with_no_upstream_counter_says_that_rather_than_a_failure`：同样是 `gpt-model` Responses 路由，覆盖 observability reason `no-counter`；不检查翻译 payload。
- `tests/int/test_pipeline_app.py:2954-2977` 的 `test_a_count_resolves_reasoning_the_same_way_the_send_does`：`reasoning-model` 只支持 Responses，覆盖 translator 读取 resolved model capabilities 并记录 reasoning approximation；不检查 token 值本身。

`tests/unit/pipeline/subscribers/test_builtin_subscribers.py:495-518` 的 `test_the_counting_leg_measures_rather_than_refusing_on_the_responses_leg_too` 只手工构造 target_format=Responses 并直接调用单个 hosted-search subscriber。它覆盖 `COUNTING_ONLY` exemption，但没有调用 `handle_count_tokens`、没有执行 routing／translation，也不能计作完整异构 count path 覆盖。

### 6.2 同构 Anthropic 或前置拒绝路径

- `tests/int/test_pipeline_app.py:1197-1255` 的 upstream count、fallback、model mapping、无 `max_tokens` 四项均使用 `claude-model`，target 是 Anthropic，同构。
- `tests/int/test_pipeline_app.py:1279-1287` 的非法 body 测试也只使用 `claude-model`；它只证明 `_countable` 同构分支会 400，正因如此没有发现异构分支返回 200 的缺陷。
- `tests/int/test_pipeline_app.py:1305-1336` 的 calibration restart 使用 `claude-model`，只覆盖 Anthropic key。
- `tests/int/test_pipeline_app.py:1787-1829,1854-1874,2205-2219,2855-2869` 的计数 observability／attribution 测试均为 `claude-model` 或 alias→`claude-model`，是同构。
- `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:268-299` 的 repaired-body count 默认 provider target 是 Anthropic，同构。
- `tests/unit/tokenization/test_token_counting.py:61-137` 测的是没有生产 caller 的 `AnthropicTokenCountingService`，且 protocol 明确为 Anthropic，不覆盖当前 handler 的异构路径。
- `tests/int/test_pipeline_app.py:1290-1302` 的 `test_count_tokens_refuses_a_model_without_the_messages_capability` 使用 endpoint 空集合的 `mute-model`，在目标格式决定前抛 `CapabilityMissing`。它既不是同构发送，也不是异构 translation；测试名容易让人误以为覆盖了“只支持其他 endpoint 的模型”，实际没有。
- `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:301-327` 覆盖 translation_required=True 但 target 是 embeddings，断言缺失 translator；它能证明 `TranslatorNotFound` 类别传播，却没有覆盖 chat-completions-only 的具体 outbound 名称与 HTTP body。

### 6.3 明确缺口

1. 没有以 Responses-only model 发送非法 `messages` 结构并断言 400 的测试；这是本次 Major 反例得以存在的直接覆盖缺口。
2. 没有 chat-completions-only model 经 `/v1/messages/count_tokens` 的 HTTP 级测试；目前只有 embeddings 缺 translator 的 unit 类比。
3. 没有测试把普通 Responses 请求完成时的真实 `usage.input_tokens` 与同一 translated payload 的 estimate 一起喂给 calibration，再从后续 count_tokens 观察 factor 生效。
4. 没有项目内测试针对 Claude Code 对额外 `estimated` 字段的读取行为；本次结论来自当前安装的 Claude Code 2.1.241 一手源码，而不是仓库测试。

## 已否决的可能性及理由

- **否决“`estimated: true` 会让当前 Claude Code 解析失败”**：Claude Code 2.1.241 只读取并类型检查 `input_tokens`，额外键不参与判断，证据为 `/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:366941-366950`。
- **否决“Responses 模型因没有 Anthropic count endpoint 就应返回能力错误”**：路由到 `/responses` 的请求本身可发送；代码有意不调用 gated provider counter，而是 local estimate，见 `src/app/pipeline/driver.py:306-324`。把“无 counter”当“模型不可达”会错误拒绝可服务请求。
- **否决“估算发生在翻译前”**：赋值 `context.payload = translated` 明确先于 estimator，见 `src/app/pipeline/driver.py:251-276`，且差异化 unit test 锁定了 Responses estimator。
- **否决“resolved model 写入改变估算值”**：当前 estimator 不读取 `model`，见 `src/app/tokenization/estimators.py:120-137`。
- **否决“默认 attempt.prepare subscriber 会在异构计数时改写 payload 或占配额”**：三个 subscriber 均在对应 guard 返回，且 count handler 不进入 DirectDriver rate limiter，证据见第 5 节。
- **否决“所有非法 Messages body 都会返回 400”**：宽松 Anthropic translator 会把非 list messages 折成空列表；行为探针得到异构 200、同构 400，证据见第 2.2 节。
- **否决“项目没有 Responses 的真实 token ground truth”**：buffered 与 streaming 两条路径都读取 upstream usage，并把规范化 usage 写入 request record，证据见第 4.2 节。
- **否决“`AnthropicTokenCountingService` 已经给 Responses 校准学习”**：该 service 硬编码 `anthropic`，且生产 `src/app` 没有 caller；它不能闭合 Responses 自动学习链路。
- **没有其他纯推理排除项。**

## 验证说明

本次没有运行完整 pytest、Ruff 或 Pyright，因为任务是只读链路评审，且结论不依赖全仓回归。执行了一个使用现有 `tests/int/test_pipeline_app.py::make_client` 的局部 TestClient 行为探针，以核实成功头和七种错误／分叉的 wire 结果。该 app 的生产 request recorder 是 always-on，因此探针向 `/home/xp/.local/share/ghc-api-proxy/requests/` 追加了 7 条请求记录；未删除或改写这些记录，以避免未经授权的数据清理。探针没有修改仓库文件。