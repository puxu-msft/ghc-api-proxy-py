# 域1：LLM 上游 SDK（三链路封装）

调研范围：openai==2.21.0、anthropic==0.79.0（均已安装于 `.venv/lib/python3.14/site-packages/`）源码；`docs/2604-rewrite/{DESIGN,anthropic-compat,model-resolution,multi-protocol,streaming}.md`、`project-structure.md` 中 `upstream/`、`openai/`、`anthropic/`、`transform/`、`models/` 相关章节；`exp/upstream-sdk-passthrough/` 既有 PoC。

## 概览结论表

| 自研点(模块/文件) | 候选库 | 匹配度 | 威胁硬约束? | 推荐 | 理由 |
|---|---|---|---|---|---|
| `anthropic/client.py`（打 `/v1/messages`） | `anthropic.AsyncAnthropic` 底层 `client.post(cast_to=httpx.Response, stream=True)` | 高 | 否 | **采纳**：复用 SDK 传输层做原始字节直通 | 与 `AsyncOpenAI` 完全同构的 stainless 生成代码，`cast_to == httpx.Response` 短路点逐行核对一致，见下 §1 |
| `openai/responses_client.py`（打 `/responses`） | `AsyncOpenAI` 底层 `client.post(cast_to=httpx.Response, stream=True)` | 高 | 否 | **采纳**：与 chat/completions 同一套底层 client，同一份 PoC 结论直接适用 | `resources/responses/responses.py` 用的仍是同一 `AsyncAPIClient.post`，路径只是换成 `/responses`，无新短路点需要验证 |
| `/responses` 的 `ws:/responses` 传输 | openai SDK 的 `Realtime`/`beta.realtime` WebSocket 封装 | **不适配** | — | **采用域3选定的 `httpx_ws` 建立上游 WS 连接**，不借用 openai SDK 的 realtime 封装 | openai SDK 的 WS 支持是 `/realtime` 专用协议（事件类型、鉴权握手均为 Realtime API 私有语义），并非通用的"把任意 REST 端点转 WS 调用"的机制，见 §2；通用传输库结论见域3 |
| `transform/translator.py`、`streaming/translator.py`（跨协议转换 anthropic↔openai↔responses↔gemini） | `litellm` | **不适配** | **是**（Python 版本硬冲突 + 强缓冲倾向） | **拒绝** | `litellm` 声明 `requires-python "<3.14,>=3.10"`，与项目 `requires-python = ">=3.14"` 直接冲突；其定位是"调用层"而非"纯转换层"（自己发请求、自己管路由/重试/缓存），见 §3 |
| 同上 | `any-llm-sdk`（mozilla-ai/any-llm） | **不适配** | 未知（需自测），但定位不符 | **拒绝** | 同样是"统一调用层"（`completion()`/`AnyLLM.create()`），不提供独立的、无状态的"仅做协议格式转换、不发请求"的函数/模块；引入它等于让它接管调用而非只借类型，见 §3 |
| `models/openai.py`、`models/anthropic.py` 的自定义 Pydantic 模型 | 直接复用 `openai.types.*` / `anthropic.types.*` | 部分适配 | 部分（见下） | **部分采纳**：入站校验层保留自研 `BaseModel`（`extra` 策略不同、需要宽松未知字段透传）；转换/构造 wire body 时可借用 SDK 的 `TypedDict` Param 类型做类型提示，不必照抄字段定义 | 见 §4：SDK 的 request-param 类型是 `TypedDict`（非 Pydantic），response 类型是 SDK 自带 `BaseModel`（`extra="allow"` 但类结构面向"SDK 自己解析响应"而非"承接任意上游 wire 并保真透传"），直接复用会绑死升级节奏且与本项目"未知字段不丢"的保真度要求不完全对齐 |

## 逐项详述

### 1. `AsyncAnthropic` 打 `/v1/messages` 与 `AsyncOpenAI` 打 `/responses` 能否复用同一套「typed 构造 + cast_to=httpx.Response 直通」

**现状**：`anthropic/client.py`（直连 Copilot 原生 Anthropic 端点）与 `openai/responses_client.py`（Responses API 客户端）都要做到 P6 零缓冲直通（`docs/2604-rewrite/streaming.md` 第 9 行"流式直通，不缓冲完整响应"），且需要注入 Copilot 伪装 header（`anthropic-compat.md` B5 步骤：`anthropic-version`、`anthropic-beta`、`X-Initiator` 等）。`exp/upstream-sdk-passthrough/CONCLUSION.md` 已证实 `AsyncOpenAI` 走 `/chat/completions` 可行，本次任务需验证是否推广到另外两条链路。

**源码级证据**：

- 两个包的 `_base_client.py` 都定义了近乎同构的 `class AsyncAPIClient(BaseClient[...])`，`anthropic/_base_client.py` 比 `openai/_base_client.py` 多出 TCP keepalive socket 选项、代理环境变量探测、`_calculate_nonstreaming_timeout`（针对 Anthropic "非流式长任务需报错，引导用户走流式"的策略），差异集中在连接建立细节，**不影响 `post`/`request`/`cast_to` 短路路径**。
- `cast_to == httpx.Response` 短路分支在两个包中位置/行为完全一致：
  - openai：`_base_client.py:1149`（同步路径）与 `:1748`（异步 `_process_response`）。
  - anthropic：`_base_client.py:1216`（同步路径）与 `:1856`（异步 `_process_response`）。
  两处均是逐字节相同的 `if cast_to == httpx.Response: return cast(ResponseT, response)`。
- `AsyncAnthropic.post`（`anthropic/_base_client.py:1966`）签名与 `AsyncOpenAI.post`（`openai/_base_client.py:1858`，见 PoC 结论文档引用）完全同构：`path`、`cast_to`、`body`、`content`、`files`、`options: RequestOptions`、`stream: bool`、`stream_cls`，内部同样是 `FinalRequestOptions.construct(...)` 后转发给 `self.request(cast_to, opts, stream=stream, stream_cls=stream_cls)`。
- `AsyncAnthropic` 默认 `base_url`（`anthropic/_client.py:340-343`：`ANTHROPIC_BASE_URL` 环境变量或 `https://api.anthropic.com`）可通过构造参数覆盖为 Copilot 的 Anthropic 端点 base，与 `AsyncOpenAI` 覆盖 `base_url` 打 Copilot 的做法完全一致的用法模式。
- `openai/resources/responses/responses.py` 内部对 `/responses` 路径的调用（第 877/1191/2508/2826 行的 `"/responses"` 字面量）走的正是同一个 `AsyncAPIClient.post`/`request`，**没有为 Responses 端点引入任何专属的底层传输机制**——它只是 `.responses.create()` 高层封装传给 `cast_to=Response`（SDK 自己的 pydantic 类型）而非 `httpx.Response`；把最外层的 typed `cast_to` 参数换成 `httpx.Response` 即可复用同一 PoC 结论，无需新验证。

**结论**：两条新链路的推广**成立**，且不需要额外 PoC——两个 SDK 由同一家 Stainless 代码生成器产出，`_base_client.py` 的 `cast_to` 短路机制、`post()` 签名、`options={"headers": ...}` 合并语义在两个包间逐行核对一致。实现时还必须把两个 SDK client 的 `max_retries` 显式设为 `0`：固定版本默认都会在 SDK 内自动重试最多 2 次，覆盖 408、409、429、5xx 和部分连接异常；若不关闭，会绕过本项目的共享重试预算、`RequestContext.attempts`、限流反馈与学习回调，并与外层策略形成乘法放大。网络重试的完整裁决见 [domain6-hot-path-foundations](domain6-hot-path-foundations.md)。其余差异点：

- anthropic 的 `_merge_mappings` 会额外注入 `x-stainless-timeout` 头（`_base_client.py:442-450` 附近），openai 没有这一行为；若严格审计出站 header 差异需知晓这一点，但不影响直通可行性。
- anthropic 默认走 `HTTPTransport`/`AsyncHTTPTransport` 并显式设置 TCP keepalive socket 选项（`_base_client.py:843` 起新增代码），openai 未做此定制；这是连接层面的优化差异，不影响 `cast_to` 短路结论。

### 2. `ws:/responses` WebSocket 传输：openai SDK 是否原生支持

**现状**：`docs/2604-rewrite/streaming.md` 第 113-191 行描述"Responses API 支持 WebSocket 传输，与 HTTP SSE 并行提供"，代理自己的 `GET /v1/responses`（WebSocket 升级）需要连接**上游** GHC 的 `ws:/responses`（据 `refs/available_models.json`，gpt-5.5 等模型的 `supported_endpoints` 含 `ws:/responses`）。这里只讨论"上游转发腿"是否能借用 openai SDK 的 WS 能力（下游/客户端腿由域3的 FastAPI WebSocket 路由负责，不在本域范围）。

**源码级证据**：

- `openai/resources/realtime/realtime.py` 确实内建 WebSocket 支持（`from websockets.sync.client import ClientConnection`、`from websockets.asyncio.client import ClientConnection as AsyncWebsocketConnection`，第 48-49 行），连接目标固定拼接为 `base_url.copy_with(scheme="wss")` + `/realtime` 路径（`realtime.py:409-413`、`:598-602`），是 **Realtime API 专属**的 WS 端点与事件协议（`RealtimeClientEvent`/`RealtimeServerEvent` 等专用类型），与 Responses API 的 `response.create` / `response.output_item.added` 等事件类型体系并非同一套。
- 搜索 openai 包内所有涉及 websocket 的文件（`grep -rn websocket`），命中的全部落在 `resources/realtime/`、`resources/beta/realtime/`、`types/realtime/`、`types/websocket_connection_options.py` 目录下，**没有** `resources/responses/` 下任何 WS 相关代码；`.responses.create(stream=True)` 与其底层 `post()` 全部走 HTTP（第 877/1191/2508/2826 行 `"/responses"` 是纯 REST 路径）。
- 本项目当前 `pyproject.toml` 未依赖 `websockets` 包（`uv pip list` 未见），意味着即便想反向复用 openai SDK 内部的 `websockets.asyncio.client`，也需要额外显式引入该依赖（openai 把它标为 optional extra，非核心依赖强制安装）。

**结论**：openai==2.21.0 **不原生支持** "把 Responses API 当作 WebSocket 调用"这件事——SDK 里唯一的 WS 能力是 Realtime API 专属封装，协议语义（事件类型、URL 拼接规则）与 Responses 完全不同，**不能**被复用或"稍加改造"套到 `ws:/responses`。因此代理连接上游 `ws:/responses` 这条链路**用不上 openai SDK**，采用域3选定的通用传输库 `httpx_ws`，仅在**构造 JSON 帧内容**时复用本项目自己的 `ResponsesRequest`/`OutputItem` 等 Pydantic 模型或 SDK 的 Responses TypedDict 类型。传输层与 SDK 无关。这与 `docs/2604-rewrite/streaming.md` 第 159 行"WebSocket 处理器复用现有 HTTP pipeline 的全部逻辑"的表述**不矛盾**——那里说的是复用本项目自己的 pipeline（token 刷新、重试、rate limiting），不是复用 openai SDK 的传输机制。

### 3. 跨协议翻译（anthropic↔openai↔responses↔gemini）：有没有现成库值得借用

**现状**：`transform/translator.py`（跨协议格式翻译）与 `streaming/translator.py`（跨格式流式翻译，逐事件、不缓冲，`streaming.md` 第 309-319 行）是当前设计的自研模块，需要保真处理 thinking signature、server_tool 块等未知/特殊字段（§硬约束"保真度"）。

**候选库评估**：

| 库 | 版本 | Python 要求 | 定位 | 维护活跃度 | 结论 |
|---|---|---|---|---|---|
| `litellm` | 1.92.0（PyPI 最新稳定，`license_expression: MIT`） | **`requires-python "<3.14,>=3.10"`** | 统一调用层（`completion()`），内部含大量协议映射代码但耦合在"发请求"的执行路径里 | 高（发布节奏密集） | **直接淘汰**：与项目 `requires-python = ">=3.14"` 硬冲突，无法安装；即便未来支持 3.14，它的角色是"调用+路由+重试+缓存"的执行框架而非可独立调用的纯函数库，引入会与本项目自己的 pipeline（`request-pipeline.md`）、feature negotiation、重试策略产生控制流冲突，且它的 streaming 处理是否满足 P6 零缓冲需要单独验证（未验证，因版本冲突已一票淘汰，不必再深入） |
| `any-llm-sdk`（mozilla-ai/any-llm） | 1.20.0（2026-07-14 发布，Apache-2.0） | `>=3.11`（兼容 3.14，理论上可安装，未实测） | 同样是统一调用层（`completion()`/`AnyLLM.create()`），官方定位"leverages official provider SDKs"，星标量级 2.1k、798 commits、72 次 release，维护活跃 | 高 | **不采纳**：调研未发现该库暴露"仅做协议格式转换、不发起实际 HTTP 调用"的独立函数或模块——它内部虽然一定存在 anthropic↔openai 请求/响应格式映射代码，但这些映射被封装在"调用者传入统一格式 → 内部转換 → 用官方 SDK 发真实请求 → 再转换回统一格式"的完整执行链路里，无法只借用中间的转换环节而不让它接管请求发送/流式处理。若要借用，等价于把本项目的上游转发执行权交给 `any-llm`，与本项目"自己控制零缓冲直通、自己控制重试/feature-negotiation/history 记录"的既有 pipeline 架构冲突面过大 |

**关于"转换层" vs "调用层"的评估维度**：`_briefing.md` 要求"客观评估 litellm 之类作为『转换层』而非『调用层』的适配度"。调研结论是：目前主流的跨 LLM 库（litellm、any-llm、以及同类的 `aisuite`、`langchain` 的 model I/O 适配器）**没有一个是纯粹的、可独立调用的"请求/响应体格式转换库"**——它们的核心价值主张都是"帮你发请求"，格式转换只是内部实现细节，未作为公开、稳定、无副作用的 API 暴露。这与本项目的需求形状（需要在**已有的**、自己控制的 httpx/SDK 直通传输之上，只做"事件到事件"的纯翻译）本质不匹配。

**风险补充**（即便忽略 Python 版本问题）：
- **零缓冲/保真度**：这两个库的转换逻辑面向"让上层用户拿到统一形状的完整响应对象"，天然倾向于内部攒够信息再转换（尤其是把 provider 的流式增量转成统一 delta 格式时），是否严格逐事件转发、是否会吞掉 provider-specific 的未知字段（如 Anthropic 的 `thinking` signature、`server_tool_use` 块）**没有官方文档承诺**，需要逐版本源码审计才能信任，维护成本不低于自研。
- **依赖体积**：两者都会引入大量与本项目无关的 provider 适配代码（其支持数十个 provider），与本项目"上游固定为 Copilot + 少数直连协议"的场景不匹配，属于过度依赖。

**结论：跨协议翻译保留自研**。`transform/translator.py`、`streaming/translator.py` 的现有设计（逐事件转换、显式处理已知字段、未知字段透传）应继续手写，不引入 litellm/any-llm 等库。

### 4. `models/{openai,anthropic}.py` 能否直接复用 SDK 的 types

**现状**：`data-models.md` 第 22-230 行定义了 `ChatCompletionRequest`/`MessagesRequest` 等一整套自定义 Pydantic v2 模型，用于入站请求校验与内部规范表示。

**源码级证据**：

- openai/anthropic 两个 SDK 的**入参**类型（"Param"后缀，如 `ChatCompletionUserMessageParam`、`MessageParam`）全部是 `TypedDict`（`total=False`），**不是** Pydantic 模型（`openai/types/chat/chat_completion_user_message_param.py:13`、`anthropic/types/message_param.py:23`）。TypedDict 只提供静态类型检查提示，**没有运行时校验能力**——不能替代本项目"外部数据必须经 Pydantic 校验"的既定架构原则（`data-models.md` 第 7 行）。
- SDK 的**响应**类型（如 `ChatCompletion`、`Message`）确实是 Pydantic 模型，且都继承自 SDK 自己定制的 `BaseModel`（`openai/_models.py:101`、`anthropic/_models.py:97`），二者的 `model_config` 都设了 `extra="allow"`（分别在 `openai/_models.py:118-119`、`anthropic/_models.py:109-110`），与本项目 `models/capabilities.py` 里 `ModelSupports` 手动设置 `extra="allow"` 的意图（未知字段不丢失）**目标一致**，理论上可以复用响应侧模型来减少重复定义。
- 但存在三个实质性障碍，导致"直接复用"不成立：
  1. **本项目的模型不是"给 SDK 自己解析响应用"，而是"承接任意上游/客户端 wire 并在多协议间转换"**——例如 `MessagesResponse`/`ContentBlock` 需要参与 `transform/translator.py` 的跨协议转换、`streaming/translator.py` 的逐事件流式翻译，需要按本项目自己的字段访问模式（如 `ContentBlock.type` 判别式）组织，而 SDK 的响应模型是为"SDK 用户拿到强类型对象做业务逻辑"设计的判别式联合类型（如 anthropic 的 `ContentBlock = Union[TextBlock, ToolUseBlock, ...]`），字段结构更细粒度、更贴合各自官方 API 而非本项目的内部规范形状。直接复用会让 `transform/`、`streaming/` 层被迫按 SDK 的类型联合分支写转换代码，耦合度不降反升。
  2. **升级节奏绑定**：直接把 `models/anthropic.py`/`models/openai.py` 定义为 SDK types 的别名，意味着每次 `pip install -U openai/anthropic` 都可能因 SDK 侧字段增删（stainless 生成器随官方 OpenAPI spec 变动）而破坏本项目的内部契约，而本项目的 pydantic 模型是"目标设计"文档中承诺的稳定内部规范（`data-models.md` 第 3 行"通过 Pydantic v2 模型验证"），两者变更节奏应该解耦。
  3. **入站请求侧完全没有 Pydantic 版本可用**（如上，Param 类型是 TypedDict），如果要复用就只能复用响应类型，入参仍需自己定义，导致"部分复用"反而增加认知负担（一半用 SDK 类型一半自定义，边界不清晰）。

**结论：不直接复用，保留自研 Pydantic 模型**；但可以在实现层面**部分借用**：
- 构造发往上游的 wire body（`dict`）时，可以用 SDK 的 `TypedDict` Param 类型作为**类型提示**（`body: ChatCompletionCreateParamsStreaming = {...}`），在开发期获得 IDE/mypy 校验收益，运行时仍是普通 dict 传给 `client.post(body=..., cast_to=httpx.Response)`（PoC 已证实 `body` 走 `json_data`，必须是 JSON 可序列化的 dict/list/标量，不能是 Pydantic 实例——见 `exp/upstream-sdk-passthrough/CONCLUSION.md` 第 125 行，这一点对 TypedDict 同样成立，无冲突）。
- 若某些内部辅助函数只需要"读一读 SDK 官方响应形状做单元测试 fixture 或字段名对照"，可以在测试代码里 `import openai.types`/`import anthropic.types` 做交叉验证，但不作为生产代码路径的依赖。

## 遗留疑问 / 需主会话或用户裁决的点

1. **`any-llm-sdk` 的 Python 3.14 兼容性未实测**（只确认 `requires-python ">=3.11"` 声明范围覆盖，未实际 `uv pip install` 验证是否有 C 扩展/间接依赖在 3.14 上失败）。但因其"调用层"定位已经不适配本项目架构，实测优先级不高，除非主会话认为仍有必要留作候补。
2. **上游 WS 依赖由域3收敛为 `httpx_ws`**——不单独引入 `websockets`；实现前仍需在 Python 3.14 环境运行最小 mock WS PoC，验证安装、代理/TLS 参数透传和逐消息背压。
3. anthropic SDK 的 `_merge_mappings` 会额外注入 `x-stainless-timeout` 请求头（openai 没有此行为）——若代理需要对出站 header 做白名单式精确控制（`header-forwarding.md` 涉及的双模式转发），实现时需注意这一 SDK 侧差异不要被误判为"客户端注入的可疑 header"。
4. 本报告未覆盖 `openai/embeddings.py`（`/embeddings` 端点）是否也适用同一套 `cast_to=httpx.Response` 直通模式——虽然结构上应该同样成立（同一 `AsyncAPIClient.post`），但 embeddings 响应通常非流式，直通的收益（零缓冲）不如三条主链路显著，建议由域2或实现阶段按需确认，不在本域展开验证。
