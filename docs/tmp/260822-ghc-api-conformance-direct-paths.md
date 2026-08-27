# GHC API 直连路径核对报告（direct_driver 四模块）

日期：2026-08-22
范围：`docs/.human-controlled/ghc-api.md` 所列四条直连端点（`ws:/responses` 不在范围，暂不支持）。
方法：`rg` + `Read` 逐字读代码，只读不改，未提交、未暂存。

## 结论摘要

- 四个驱动模块**均已实现**，共享同一个 `DirectDriver` 循环（`src/app/pipeline/direct_driver/base.py`），彼此只是绑定不同的 `ModelEndpoint`，不存在行为漂移。
- 四个驱动都**已接线到生产路径**——但生产入口是 `app.cli:main → create_pipeline_app`（`src/app/server/pipeline_app.py`），**不是** `app.server.app_factory.create_app`。`src/app/routes/anthropic.py`、`src/app/routes/openai.py` 属于 `app_factory` 这条“仍在维护但不再挂载”的旧实现，production 完全绕开它们。
- `count_tokens` **不经过** `AnthropicMessagesDriver`/`DirectDriver.run()`：它走一条独立方法 `ModelProvider.count_tokens()`（`send_anthropic_count_tokens`），只有当路由目标是 `WireFormat.ANTHROPIC_MESSAGES` 时才真正直连上游 `/v1/messages/count_tokens`；一旦模型被路由到 Responses（需要翻译），上游没有计数端点，直接退化为 `app/tokenization` 的本地估算——这是设计如此，但与人写文档「驱动模块 = direct_driver.anthropic_messages」的字面表述有出入。
- `openai_embeddings` 已接线且有下游路由 `POST /embeddings`（含 `/v1/embeddings`、`/openai/v1/embeddings` 前缀），非孤儿模块，有直接的生产集成测试断言真实上游 URL。
- 块级交付的 `BlockAssembler` 只认两种上游 SSE 形状（Anthropic、Responses），**没有 OpenAI Chat Completions 形状的分支**；`/chat/completions` 在生产集成测试 `tests/int/test_pipeline_app.py` 中**零覆盖**（流式、非流式都没有）。这是本次核查发现的最大风险点，见下方第 5、6 节。

---

## 逐端点结论表

| 端点 | 驱动模块 | 实际发出的 URL（逐字符） | 实现 | 接线 | 判定 | 证据 file:line |
|---|---|---|---|---|---|---|
| `POST /v1/messages` | `direct_driver.anthropic_messages` (`AnthropicMessagesDriver`) | `/v1/messages` | 已实现 | **已接线** | 直连，生产路径确认 | `src/app/pipeline/direct_driver/anthropic_messages.py:15`；`src/app/model_provider/ghc_client/client.py:132-146`（字面量 `"/v1/messages"`）；`src/app/pipeline/direct_driver/__init__.py:48`（`DRIVERS[ANTHROPIC_MESSAGES]`）；`src/app/server/handler.py:150`（`driver_type = DRIVERS[route.endpoint]`）；`src/app/server/inbound.py:34`（路由注册）；`src/app/server/pipeline_app.py:685-696`（`build_router` 挂载 `ROUTES`）；`src/app/cli.py:23,151`（生产入口用 `create_pipeline_app`）；测试断言 `tests/int/test_pipeline_app.py:154-165`（`seen[-1].url == f"{BASE_URL}/v1/messages"`） |
| `POST /v1/messages/count_tokens` | 文档写 `direct_driver.anthropic_messages`；**实际是独立方法**，不经过该 Driver 类 | `/v1/messages/count_tokens` | 已实现 | **已接线，但绕开 DirectDriver** | 见第 3 节：仅当目标是 Anthropic 时直连，否则本地估算 | `src/app/model_provider/ghc_client/client.py:148-154`；`src/app/model_provider/github_copilot.py:176-191`（`count_tokens()`，不是 `send()`）；`src/app/server/handler.py:206-310`（`handle_count_tokens`，`upstream_counts = route.target_format is WireFormat.ANTHROPIC_MESSAGES`）；`src/app/server/pipeline_app.py:401`（生产调用点）；`src/app/server/inbound.py:35-40`（路由注册，`count_tokens=True`） |
| `POST /chat/completions` | `direct_driver.openai_chat_completions` (`OpenAIChatCompletionsDriver`) | `/chat/completions` | 已实现 | **已接线（路由/驱动层面），但生产端到端零测试覆盖，流式很可能有缺陷** | 接线成立，行为风险见第 5/6 节 | `src/app/pipeline/direct_driver/openai_chat_completions.py:15`；`src/app/model_provider/ghc_client/client.py:116-130`（字面量 `"/chat/completions"`）；`src/app/pipeline/direct_driver/__init__.py:49`；`src/app/server/inbound.py:38`；`src/app/server/pipeline_app.py:685-696` |
| `POST /responses` | `direct_driver.openai_responses` (`OpenAIResponsesDriver`) | `/responses` | 已实现 | **已接线** | 直连，生产路径确认，含流式测试 | `src/app/pipeline/direct_driver/openai_responses.py:15`；`src/app/model_provider/ghc_client/client.py:156-170`（字面量 `"/responses"`）；`src/app/pipeline/direct_driver/__init__.py:50`；`src/app/server/inbound.py:39`；测试 `tests/int/test_pipeline_app.py:571-577`（`/responses`、`/v1/responses`、`/openai/v1/responses` 均命中同一上游） |
| `POST /embeddings` | `direct_driver.openai_embeddings` (`OpenAIEmbeddingsDriver`) | `/embeddings` | 已实现 | **已接线** | 直连，生产路径确认，非孤儿 | `src/app/pipeline/direct_driver/openai_embeddings.py:15`；`src/app/model_provider/ghc_client/client.py:191-197`（字面量 `"/embeddings"`）；`src/app/pipeline/direct_driver/__init__.py:51`；`src/app/server/inbound.py:41`（`streamable=False`）；测试 `tests/int/test_pipeline_app.py:716-720`（三条前缀路径均断言 `seen[-1].url == f"{BASE_URL}/embeddings"`） |

---

## 1-2. 逐模块实现与接线核查（调用链）

四个驱动文件（`anthropic_messages.py`/`openai_chat_completions.py`/`openai_responses.py`/`openai_embeddings.py`，各 34 行）本身只是各绑定一个 `ModelEndpoint` 常量并继承 `DirectDriver`（`src/app/pipeline/direct_driver/base.py:92-260`），真正的重试/限流/事件发布循环全部在共享基类里，四者不可能行为漂移（模块 docstring 原话）。

`ModelEndpoint` 的值本身就是 URL 路径字符串（`src/app/model_provider/types.py:14-19`）：

```
ANTHROPIC_MESSAGES = "/v1/messages"
OPENAI_CHAT_COMPLETIONS = "/chat/completions"
OPENAI_RESPONSES = "/responses"
OPENAI_RESPONSES_WS = "ws:/responses"
OPENAI_EMBEDDINGS = "/embeddings"
```

生产调用链（从 HTTP 入口读通）：

1. 进程入口：`pyproject.toml:55` `ghc-api-proxy = "app.cli:main"` → `src/app/cli.py:23,151,176` 使用 `create_pipeline_app`（**不是** `app_factory.create_app`）。
2. `src/app/server/pipeline_app.py:685-696` `build_router()` 遍历 `src/app/server/inbound.py:33-42` 的 `ROUTES`（含 `/v1/messages`、`/v1/messages/count_tokens`、`/chat/completions`、`/responses`、`/embeddings`），逐条注册到 `_serve`（`pipeline_app.py:295`）。
3. `_serve` 解析 body → `build_context` → 非 count_tokens 分支调用 `handle_bounded`（`pipeline_app.py:444` → `src/app/server/handler.py:328`）→ `handle`（`handler.py:130-171`）。
4. `handler.py:150` `driver_type = DRIVERS[route.endpoint]`，`DRIVERS` 定义在 `src/app/pipeline/direct_driver/__init__.py:47-52`，四个端点各映射到对应 Driver 类。
5. `driver.run(context)`（`base.py:126`）最终调用 `self._send`（`base.py:221`）→ `self._provider.send(...)`（`ModelProvider.send`，`src/app/model_provider/github_copilot.py:140-174`）→ 按 endpoint 分派到 `self._client.send_xxx`（`github_copilot.py:156-174`）→ `GhcApiClient` 各方法（`src/app/model_provider/ghc_client/client.py:116-197`），把上面列的字面量路径 `path` 传给 `self._openai.post(path, ...)` / `self._anthropic.post(path, ...)`（OpenAI/Anthropic SDK 的 `AsyncOpenAI`/`AsyncAnthropic` 客户端，`base_url` 另配，测试里固定为 `https://copilot.example`）。

`app.server.app_factory`（`src/app/server/app_factory.py:157-178`）确实 `include_router(anthropic_router)` / `include_router(openai_router, ...)`，即 `routes/anthropic.py`、`routes/openai.py` 里手写的 `client.execute()`/`client.chat()`/`client.responses()`/`client.embeddings()` 路径——但这套 app 从未被 `app.cli` 构造，只在 `tests/int/test_anthropic_routes.py:12,127,183`、`tests/int/test_openai_routes.py:10,49` 里单独测试。`pipeline_app.py:3` 的模块 docstring 自己写明："Separate from `app_factory`, which still serves the existing implementation. Mounting both would give one path two owners."——两套实现互斥挂载，生产只挂 `pipeline_app`。因此 `routes/anthropic.py`、`routes/openai.py` 对生产行为而言是**未接线的旧路径**（不是本次核查的四个 direct_driver 模块本身未接线，而是那两个 routes 文件不是生产入口）。

## 3. count_tokens 特别核查

`docs/.human-controlled/ghc-api.md:25` 把 `POST /v1/messages/count_tokens` 和 `/v1/messages` 并列写在同一行，标注驱动模块是 `direct_driver.anthropic_messages`。实际代码里两者**不是同一条调用链**：

- 生产入口 `pipeline_app.py:395-401` 在 `route.count_tokens` 为真时，调用的是 `handle_count_tokens`（`src/app/server/handler.py:206-310`），**不经过 `DRIVERS`/`DirectDriver.run()`**。
- `handle_count_tokens` 内部：`upstream_counts = route.target_format is WireFormat.ANTHROPIC_MESSAGES`（`handler.py:280`）。只有这一分支为真时才会调用 `provider.count_tokens(payload, model_id=...)`（`handler.py:254`）→ `ModelProvider.count_tokens`（`github_copilot.py:176-191`）→ `self._client.send_anthropic_count_tokens(payload)`（`ghc_client/client.py:148-154`，字面量 `"/v1/messages/count_tokens"`）——这才是真正的上游直连。
- 一旦请求的模型被路由到 `WireFormat.OPENAI_RESPONSES`（需要翻译），`upstream_counts` 为假，上游**没有** count_tokens 端点（`handler.py:275` 注释明确写「OpenAI 系列没有计数端点」），直接退化为本地估算：`app/tokenization/estimators.py` 的 `estimate_anthropic_input`/`estimate_responses_input`，再由 `app/tokenization/calibration.py` 的校准因子修正。`src/app/tokenization/` 的存在意味着：本项目把「本地估算」当作 count_tokens 的**正式兜底路径**，而不是缺失功能的临时补丁——这是设计决策，配置项 `inbound.anthropic_count_tokens.providers` 默认 `["ghc", "local"]`（`src/app/config/schema.py:75`），即默认先尝试直连上游，失败或无计数端点再退化本地估算，两者共存。
- 结论：`count_tokens` **在“模型本身是 Anthropic 端点”的常见情形下确实是直连上游**，但实现上是独立方法而非 `AnthropicMessagesDriver` 实例，且存在文档未强调的「本地估算兜底」分支。文档表述「驱动模块 = direct_driver.anthropic_messages」在字面代码归属上不准确，但在“不翻译、直连上游”的功能意图上基本一致（除翻译路由的兜底分支外）。建议在 `docs/.human-controlled/ghc-api.md` 或 `.dev/docs` 的对应主题里补一句，说明 count_tokens 走独立方法、以及本地估算兜底的存在。

## 4. openai_embeddings 特别核查

- 下游路由确实存在：`src/app/server/inbound.py:41` `InboundRoute("/embeddings", WireFormat.OPENAI_EMBEDDINGS, streamable=False)`，`_BY_PATH` 为 OpenAI 系族群自动加上 `/v1`、`/openai/v1` 前缀（`inbound.py:44-49`，`OPENAI_PREFIXES = ("", "/v1", "/openai/v1")`）。
- 生产集成测试直接验证：`tests/int/test_pipeline_app.py:715-720`，对 `/embeddings`、`/v1/embeddings`、`/openai/v1/embeddings` 三条路径分别 POST，断言状态码 200 且实际发出的上游 URL 精确等于 `https://copilot.example/embeddings`。
- 非孤儿模块，`streamable=False` 在 `build_context`（`inbound.py:71-73`）里强制：请求体带 `stream: true` 会在解析阶段被 `InboundRequestError` 拒绝，从未到达驱动层，与「embeddings 不支持流式」的协议现实一致。

## 5. 流式 / 非流式支持，块级交付如何处理

- 四个驱动共享的 `DirectDriver._send`（`base.py:221-260`）本身对 `stream` 参数一视同仁地转发给 `provider.send(..., stream=context.stream, ...)`，驱动层不区分流式非流式，只管发请求、量时限、算重试预算。
- 真正决定“流式怎么交付给客户端”的是 `pipeline_app.py:_serve` 里 `if context.stream:` 分支（`pipeline_app.py:478` 附近）：调用 `stream_delivery(...)`，把 upstream 原始 SSE 字节流经过 `assembler_for(handled)` 选出的 `BlockAssembler` 解析成 `CompletedBlock`，再经 `BlockBuffer`（`delivery_buffer(chain)`）做块级缓冲——这正是项目要求的“下游只做块级交付”的落地点，对四条直连端点统一适用。
- 但 `BlockAssembler` 只有两种实现：`AnthropicAssembler`、`ResponsesAssembler`（`src/app/pipeline/delivery/assembler.py:1-8` docstring 原话："Two upstream shapes are handled, matching the two protocol legs."）。`assembler_for`（`src/app/server/handler.py:517-524`）的判据是 `dialect_for(handled)`（`handler.py:488-500`）：只把 `route.target_format is WireFormat.OPENAI_RESPONSES` 单独分支出 `ResponsesAssembler`，**其余一切（包括 `OPENAI_CHAT_COMPLETIONS`）都落到 `AnthropicAssembler`**。
- `AnthropicAssembler.push`（`assembler.py:126 起`）按 `event.event or data.get("type", "")` 派发（`content_block_start`/`content_block_delta`/`content_block_stop`/`message_delta`…）。OpenAI Chat Completions 的 SSE 帧是 `data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":...}}]}`，既没有 `event:` 行也没有 `"type"` 字段，`kind` 会是空字符串，匹配不上任何分支——**据代码读法推断**，`/chat/completions` 若被路由为未翻译（目标端点即 Chat Completions）且客户端要求 `stream: true`，块级组装很可能一个 block 都攒不出来，客户端收到的 SSE 会是空交付。
  - 权重说明：这是**基于架构证据（docstring + push() 分支穷举）的高置信度推断**，未做运行时复现（未起服务实测），也没有找到任何测试覆盖这一具体场景（见第 6 节），所以标注为「强证据、未运行时验证」，建议列入 `.dev/docs` 的 deferred/status 供人确认是否已知风险。
- `openai_responses` 的流式路径有专门的 `ResponsesAssembler` 且有生产集成测试覆盖（`test_streaming_is_served_as_block_level_sse` 等，`tests/int/test_pipeline_app.py:648-703`，虽然这些用例的路由目标多为 Responses/Anthropic 直连或互译场景，与 `/chat/completions` 无关）。
- `openai_embeddings` 天然不支持流式（见第 4 节），符合协议现实，不需要块级交付。

## 6. 测试覆盖情况

| 驱动/端点 | 单元测试 | 生产集成测试（`create_pipeline_app`） | cassette 回放 |
|---|---|---|---|
| `anthropic_messages`（`/v1/messages`） | `tests/unit/pipeline/test_direct_driver.py`（共享循环，经 `AnthropicMessagesDriver` 具体实例化） | `tests/int/test_pipeline_app.py`（大量：未翻译直连、翻译到 Responses、流式块级、429/503、count_tokens 各分支等） | 无直接依赖；`tests/int/test_pipeline_app.py` 用可编程的假 `httpx2.Response` transport，不是 cassette 回放 |
| `count_tokens` | `tests/unit/tokenization/test_token_counting.py`、`tests/unit/server/test_tls_and_count_tokens.py` | `tests/int/test_pipeline_app.py:877-1020`（`ghc` 计数、本地估算兜底、模型映射后计数、无 `max_tokens` 请求体、无上游计数器模型等多个用例） | 无 |
| `openai_chat_completions`（`/chat/completions`） | 无（`tests/unit/pipeline/test_direct_driver.py` 只测共享循环本体，未单独实例化该 Driver） | **零**——`rg -in "chat.completion" tests/int/test_pipeline_app.py` 无命中 | 无 |
| `openai_responses`（`/responses`） | 共享循环单测覆盖同上 | `tests/int/test_pipeline_app.py`（含 `/responses` 三前缀挂载测试、流式块级测试、Anthropic→Responses 翻译测试） | `tests/int/cassettes/anthropic_to_responses_stream.json`、`responses_web_search_stream.json` 等，经 `tests/int/recorded/` 回放，用在别的用例里（非 `test_pipeline_app.py` 主体） |
| `openai_embeddings`（`/embeddings`） | `tests/unit/server/test_server_inbound.py`（路由解析层面） | `tests/int/test_pipeline_app.py:715-720`（三前缀 + URL 精确断言） | 无 |
| `routes/anthropic.py`、`routes/openai.py`（`app_factory`，非生产） | — | `tests/int/test_anthropic_routes.py`、`tests/int/test_openai_routes.py`——测的是**未挂载到生产**的旧实现 | 无 |

结论：四个 direct_driver 模块本身实现完整、除 `openai_chat_completions` 外均有生产集成测试直接命中；`openai_chat_completions` 的路由注册和 URL 拼装有间接证据（共享循环单测 + `ghc_client` 组件级路径断言），但**没有任何一条测试真正端到端跑过 `POST /chat/completions`（无论流式还是非流式）**，这也是第 5 节流式风险点缺乏测试兜底的直接原因。

## 未采纳/未展开的方向

- 未对 `/chat/completions` 流式假设做运行时复现（起服务 + 真实 POST），因为任务要求只读、不改代码不提交；如需坐实，建议后续起一个隔离环境用假上游 transport 实测一次，成本很低。
- 未深入核查 `responses_ws.py`（`ws:/responses`），按任务要求排除在范围外。
- 未评估 `app_factory`/`routes/anthropic.py`、`routes/openai.py` 这条旧路径是否该被删除或归档，这是产品/清理决策，非本次核查范围，仅如实报告其未接线状态。
