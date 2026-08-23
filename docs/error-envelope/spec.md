# 错误信封：直连透传 / 翻译过 IR

**这份是 Spec**，答「应该是什么样」，规范性。**当前为 v3 草稿，未冻结**——§10 有两项待用户裁决。

## 修订记录

| 版本 | 变化 | 触发 |
|---|---|---|
| v1 | 首稿 | 用户裁决 |
| v2 | 推翻 v1 的两处：不新建 `SemanticError`（IR 已存在）、原始字节已丢失 | 出口清点 [260823-error-surface-inventory.md](../server-layout/reports/260823-error-surface-inventory.md) |
| **v3** | 采纳评审的 4 条 blocker、8 条 major、1 条 minor，**全部** | 评审 [reports/260823-spec-review-gpt.md](reports/260823-spec-review-gpt.md) |

**v3 相对 v2 的实质改动**（每条都对应一条评审发现，处置记录见 [reports/260823-spec-review-disposition.md](reports/260823-spec-review-disposition.md)）：

- **删掉了 v2 §5 给裁决第 1 条开的例外**。v2 主张「直连路径上流内失败事件也要过 IR，因为本代理已经在重新成帧」——这是把实现约束反过来改写了用户的行为裁决，且该例外并不必要（错误事件是自足的 SSE 事件，不需要装配即可原样转发）。
- **v2 说「IR 已经存在」，只对了一半**。`ErrorCategory` 是一个分类枚举、一个字段，不是能承载翻译的记录。v3 定义 `ErrorInfo`，并补上 v2 整块缺失的 **source → IR 表**。
- **v2 §6 的「同一个信封的两种包装」不成立**。OpenAI Responses 的 `ResponseErrorEvent` 是扁平的，不是 JSON `ErrorObject` 的嵌套形状。改为「同一语义事实，按各协议各自合法的 carrier 写出」。
- **v2 §7 把待裁决项写成了实施指令**（「在裁决到达之前，实施按第 1 个进行」）。删除。
- **v2 给用户亲笔的响应头黑名单加了「只为成功响应」这个原文没有的限定**。删除。
- **补上 category → status / code / retry 的完整输出行为表**。两个客户端 SDK 都按 HTTP status 选异常类、都默认重试 408/409/429/≥500（实测），所以只定义 `type` 字符串不足以定义客户端动作。
- **收窄 v2 §4.2 的结论**：「不属于官方 SDK 声明的顶层词汇表」成立，「Anthropic 不认识」超出证据。
- **消除四处范围自相矛盾**：路径未注册、框架 404/405、Gemini 501、one-shot 腿。

**用户裁决**（2026-08-23，原文）：

> 1. 直连路径一定用原生的，即使我们未知，也能传递；
> 2. 翻译路径，按需建立 IR 机制，有判断力、需要支持的情况，都要先映射到内部已知概念，再按需转出实际格式。

## 1. 这条裁决的来源与效力

**第 2 条已经是追认状态**，不是新增。`docs/.human-controlled/message-translation.md:9`：

> 对于翻译路径，采用按需理解和处理的原则，不直接建立两种类型之间的映射，而是总是建立消息格式与内部 IR 的映射关系，按需理解和处理。

同文件第 3、5 行给出机制：`translation_driver`，`输入格式 <-> 中间表示 <-> 上游模型格式`；每种格式注册 `inbound.from-*` / `outbound.to-*`；**不要求能力等价**，无唯一翻译路径处提供配置选项。

**第 1 条与既有条款同形。** `message-format-reshape.md:11` 对请求头写明：直连走黑名单、翻译走白名单。「客户端返回 Anthropic Messages」一节（第 51～63 行）对响应头写了同一对名单。**该节原文没有「只为成功响应」这样的限定**，v2 曾自行添加，v3 删除。

该节 TODO（第 63 行）带三层限定：「根据我的认知」、非 Anthropic 上游可能语义相同形式不同、「在认清之前翻译路径的处置先不做」。**当前翻译过 IR 的授权来自 2026-08-23 的新裁决，不是来自那条 TODO。**

## 2. 判据：哪条路、什么来源

一个错误的处置由两个正交的事实决定，**不由它发生在流式还是非流式、响应头之前还是之后决定**。今天恰恰是后者在决定形状（§7），那是实现时序泄漏成了协议。

| | 来源：上游 | 来源：本代理 |
|---|---|---|
| **直连路径**（`Route.translation_required` 为 False） | **原生透传**（§3），流内事件同样（§3.4） | 过 IR，按客户端方言写出（§4～§6） |
| **翻译路径** | 读成 IR，按客户端方言写出；读不动的见 §10.1 | 过 IR，按客户端方言写出 |

「本代理产生」的完整清单见 §5.1。

**路径未注册不在本 Spec 覆盖范围内**（v2 曾把它列进来，与 §11 排除框架 404/405 相矛盾）：这类请求根本不进 `serve`，由 Starlette 直接答 `{"detail":"Not Found"}`，且没有 route 就推不出 `inbound_format`，「按客户端方言」没有定义域。见 §11 的登记。

## 3. 直连透传（裁决第 1 条）

客户端与上游说同一种方言，因此我们对这段内容**既不需要判断力，也不应施加判断力**。

### 3.1 非流式：body、状态码、响应头

- **body**：上游的错误 body 原样交给客户端。不解析、不重排、不改写、不包一层。我们不认识的字段必须原样到达。
- **状态码**：上游的状态码原样透传。**今天不是这样**：`RETRYABLE_STATUSES`（401、408、409、425、429、500、502、503、504）里除 429 外的每一个，在重试预算耗尽后都变成 502（清点 §3，401 与 503 已实测）。502 说的是「网关自己坏了」，与上游说的（凭证过期、过载、上游超时）都不同，而客户端**会据此改变动作**——两个 SDK 都按 status 选异常类。
- **响应头**：沿用 `message-format-reshape.md`「客户端返回 Anthropic Messages」一节的**直连黑名单**。该节原文不区分成功与错误，本 Spec 因此不区分。语义头（`anthropic-ratelimit-*`、`x-request-id`、`retry-after` 的原始写法、`x-should-retry`）到达客户端；分帧头（`content-length`、`content-encoding`、`transfer-encoding`、`connection` 一族）不转发。
  - 今天除 429 上重新格式化的 `retry-after` 外全部丢弃（清点 §4，实测）。
  - 原料已在手：`UpstreamError.headers` 与 `UpstreamRejected.headers` 都已被赋值，且**全系统零消费者**（清点 §2.4，实测）。
- **`Content-Type`**：随上游。上游答 `text/html` 或空 body 时同样原样透传。

### 3.2 前置项：原始字节已经不在了

`model_provider/ghc_client/errors.py` 的 `_response_parts` 只取 `response.text`，即已按 charset 解码的 `str`；SDK 的 response 对象在异常被翻译的那一刻就无人持有。评审用非 UTF-8 body 实测确认：上游发 `b"\xffraw-body"`，客户端拿到的是 `�raw-body`——**字节已经不可恢复**。

因此：**在 `_response_parts` 处同时保留原始 `bytes` 与其 `content-type`**。对绝大多数 JSON 上游与解码结果等价，但对非 UTF-8、BOM、上游故意发的畸形字节不等价——而那正是「我们未知」的典型情形。

**这一项是 §3 其余部分的前置**，实施排在最前。

### 3.3 直连路径上仍然由本代理产生的错误

本代理在拿到上游回答**之前**就失败了（路由拒绝、翻译器缺失、请求体不合法、本侧守卫触发等），此时不存在「上游原生」这个东西，走 §4～§6。

### 3.4 流式：上游的失败事件也照样原样转发

**v2 曾为这一格开例外，v3 删除。** 上游在流中发的 `event: error`（Anthropic）、`response.failed` / `response.cancelled`（Responses）是**自足的 SSE 事件**——它不是内容块，不需要装配，原样转发在技术上完全可行。「本代理已经在重新成帧」是实现现状，不构成改写裁决的理由。

要求：

- 直连腿上，上游失败事件的 **event 名与完整 JSON payload（含我们不认识的字段）原样重放**给客户端。若 SSE 序号一类的传输包装必须重编，只允许改传输包装，**不得把 payload 先归入本项目的闭集**。
- 翻译腿上，由上游方言的 error reader 读成 `ErrorInfo`，再由客户端方言的 writer 写出。

### 3.5 今天这里是全清点里唯一「把失败伪装成成功」的出口

上游明确说「我失败了」时，**该失败事件零字节到达客户端**（先前已交付的完整块仍然到达，代理随后合成的正常终结也到达——所以不是「整个响应为空」）。客户端收到 `message_delta(stop_reason:"incomplete")` + `message_stop`，或 `response.incomplete` 且 `error: null`：**语法上完全正常的收尾**（清点 §7 与评审各自实测；评审测得 752 / 2903 / 749 字节）。

两处代码注释都说「与撕裂产生的 `incomplete_responses_stream` 帧不可区分」。**这句话已经不成立**：自 2026-08-22 干净 EOF 改动落地后，块边界上的 EOF 走 `framer.terminal(stop_reason="incomplete")` 而不是错误帧。现在是**与成功不可区分**，比注释描述的严重。注释必须一并修正。

该请求**不得**以一个表示正常结束的终结事件收尾。

这条与 `.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条是同一件事，但**代价已经变了**，登记时的定级需要重评。

## 4. IR：`ErrorInfo`

### 4.1 为什么需要一个记录，而不只是那个枚举

`app/errors.py` 的 `ErrorCategory`（6 个成员）确实已经存在，且 `stream.py` 的三个 SSE 错误出口与 `hand_over.py` 都在用它。**但它是一个分类枚举，是 IR 的一个字段，不是 IR。** 它不装 `message`、`status_code`、`headers`、`code`、`param`、上游原始 payload、未知扩展、来源方言或转换损失——而 §6 的写出要求这些全都参与。

v2 把「枚举已存在」当成「IR 已存在」，是从 v1「在错误的地方新建记录」过度矫正到了「不需要记录」。

### 4.2 形状

沿用 `SemanticRequest` / `SemanticResponse` 的房屋风格（`dataclass(slots=True)`，带 `Conversion`）：

| 字段 | 含义 |
|---|---|
| `category` | `ErrorCategory`，见 §4.3。**保留现有 6 个成员的拼写不变**，只新增——`hand_over.py` 与 MCP 侧已在读这些值（契约见 `.dev/docs/upstream/retry-and-continuation/decisions.md` 4.1） |
| `message` | 给人读的一句话。**不得包含 SDK 的实现细节**，见 §4.5 |
| `status_code` | 告诉客户端的 HTTP 状态。由 §5 的表决定，不是从异常类名猜 |
| `code` | 稳定标识符。本项目自己的扩展，见 §6.4 |
| `param` | 出问题的字段路径（`TranslationRefused.field_path` 是现成来源） |
| `headers` | 要转发给客户端的上游语义头，已按 §3.1 的黑名单过滤 |
| `source_format` | 这份错误读自哪种方言；本代理产生的为空 |
| `source_bytes` / `source_content_type` | 上游原文与其类型，未解析。用于直连透传（§3）与 §10.1 |
| `conversion` | 与请求/响应翻译同样的 `Conversion`，记录读不动或写不出的部分 |

### 4.3 `ErrorCategory` 的取值

现有 6 个在「客户端能做出不同动作」这个尺度上不够分——`CLIENT` 一个成员要同时表达「你的 body 错了」「没这个模型」「你没权限」。补齐为：

`CLIENT`、`AUTH`、`RATE_LIMIT`、`NETWORK`、`UPSTREAM`、`INTERNAL`（以上现有，拼写不变）、`PERMISSION`、`BILLING`、`NOT_FOUND`、`OVERLOADED`、`TIMEOUT`、`NOT_IMPLEMENTED`（以上新增）。

**`BILLING` 必须现在就进表**，不能留给「未来的未知错误」：Anthropic 官方词汇表里有 `billing_error`，它与 `permission_error` 可能同落 403，而客户端靠 `.type` 区分「去处理账单」与「去申请权限」——两个完全不同的动作。

### 4.4 补全 IR 的另一半：`code` 与 `param` 必须一并接上

今天只有 `TranslationRefused` 带 `code` 与 `field_path`（实测拿到过四字段的错误体），`UpstreamRejected` 与 `PipelineAbort` 都不带。这两个字段是本项目自己设计、语义正确的机器可读通道，只服务于一个异常类是浪费。

### 4.5 `message` 的来源

今天它是 `str(APIStatusError)`，形状随上游 content-type 三变：JSON 时是 Python `dict` 的 repr（单引号、不可解析）；HTML 时是原文且**没有** `Error code:` 前缀；空 body 时只有 `Error code: 400`——全由 SDK 的分支决定，本项目没有一处代码知道自己在往里放什么（清点 §2.1，三种形状均实测）。

要求：`message` 由本项目自己构造，上游原文走 `source_bytes` 与 §6.4 的通道，不再依赖 SDK 的 `__str__`。

## 5. source → IR：每一种失败进哪一格

这是 v2 整块缺失的部分。没有它，实现者只能自己发明公共行为。

### 5.1 本代理产生的错误

| 来源 | `category` | `status_code` | 备注 |
|---|---|---|---|
| 请求体不是合法 JSON / 不是对象 | `CLIENT` | 400 | |
| `InboundRequestError`（缺 model、路径段为空、不可流式端点请求 stream） | `CLIENT` | 400 | |
| `UnknownModel` | `NOT_FOUND` | **404** | **行为变更**：今天是 400。理由是本代理自己的语义——请求指名的模型在目录里不存在，这是「没找到」而不是「你的 body 写错了」；`CapabilityMissing` 与它的区别正在于此。两个 SDK 对 400 与 404 都不重试，客户端的重试动作不变，改变的是它拿到的异常类。**不以「Anthropic 真实 API 也这样答」为据**——仓库里没有那个观测，我未验证 |
| `CapabilityMissing` | `CLIENT` | 400 | 模型存在但不能做这件事，是请求与模型不匹配 |
| `RoutingError` | `CLIENT` | 400 | |
| `TranslatorNotFound` | `NOT_IMPLEMENTED` | **501** | **行为变更**：今天是 400，那是把「代理没建这个能力」说成「客户端 body 有错」。与 `route.implemented=False` 同格 |
| `TranslationRefused` | `CLIENT` | 400 | 带 `code` 与 `param` |
| `route.implemented` 为 False（Gemini 三条） | `NOT_IMPLEMENTED` | 501 | |
| `CountTokensRequestError` | `CLIENT` | 400 | |
| `CountTokensUnavailable` | **读穿到它的成因** | 同 | **行为变更**：今天一律 503，上游 400 与 500 两件不同的事被压成同一个答案，上游 body 一字节不到（清点 E6，实测）。直连路径上这违反裁决第 1 条 |
| 客户端截止时间到期（`ClientDeadlineError`） | `TIMEOUT` | 504 | 本侧时钟，无上游原生可传 |
| 上游空闲超时（`StreamIdleTimeoutError`） | `TIMEOUT` | 504 | |
| 缓冲上限超出（`BufferCapExceeded`） | `INTERNAL` | 500 | |
| 上游答 200 但 body 不是 JSON | `UPSTREAM` | 502 | **行为变更**：今天异常逃出 `_dispatch`，客户端拿到 `500` + `text/plain` + `Internal Server Error` 五个字（清点 E18，实测） |

### 5.2 上游状态码 → `category`（仅翻译路径需要；直连路径原样透传）

| 上游 status | `category` |
|---|---|
| 400 | `CLIENT` |
| 401 | `AUTH` |
| 403 | `PERMISSION`；上游 body 的 `error.type` 是 `billing_error` 时为 `BILLING` |
| 404 | `NOT_FOUND` |
| 408 | `TIMEOUT` |
| 413 / 422 | `CLIENT` |
| 429 | `RATE_LIMIT` |
| 500 / 502 | `UPSTREAM` |
| 503 / 529 | `OVERLOADED` |
| 504 | `TIMEOUT` |
| 其它 4xx | `CLIENT` |
| 其它 5xx | `UPSTREAM` |

### 5.3 上游流内事件 → `category`（仅翻译路径；直连路径按 §3.4 原样转发）

| 事件 | `category` |
|---|---|
| Anthropic `event: error`，payload 的 `error.type` 在官方词汇表内 | 按该 type 反查 §6.1 的表 |
| Anthropic `event: error`，payload 的 `error.type` 不在词汇表内 | 见 §10.1 |
| Responses `response.failed` / `response.cancelled` | 由 `response.error.code` 判定；判不出时见 §10.1 |
| 传输撕裂、连接被对端关闭 | `NETWORK` |

### 5.4 `PipelineAbort`

读穿到 `cause`，按上表判定。今天 `error_status` 已经这样做了一半——它对 `cause` 递归，但递归的终点仍然是那张会把 401/503 打成 502 的表。

## 6. IR → 各方言：完整的输出行为

### 6.1 类别 → 各方言的类型拼写

| `ErrorCategory` | Anthropic `error.type` | 本代理约定的 OpenAI `error.type` | Gemini `error.status` |
|---|---|---|---|
| `CLIENT` | `invalid_request_error` | `invalid_request_error` | `INVALID_ARGUMENT` |
| `AUTH` | `authentication_error` | `authentication_error` | `UNAUTHENTICATED` |
| `PERMISSION` | `permission_error` | `permission_error` | `PERMISSION_DENIED` |
| `BILLING` | `billing_error` | `insufficient_quota` | `PERMISSION_DENIED` |
| `NOT_FOUND` | `not_found_error` | `not_found_error` | `NOT_FOUND` |
| `RATE_LIMIT` | `rate_limit_error` | `rate_limit_error` | `RESOURCE_EXHAUSTED` |
| `OVERLOADED` | `overloaded_error` | `server_error` | `UNAVAILABLE` |
| `TIMEOUT` | `timeout_error` | `server_error` | `DEADLINE_EXCEEDED` |
| `NETWORK` | `api_error` | `server_error` | `UNAVAILABLE` |
| `UPSTREAM` | `api_error` | `server_error` | `INTERNAL` |
| `INTERNAL` | `api_error` | `server_error` | `INTERNAL` |
| `NOT_IMPLEMENTED` | `api_error` | `server_error` | `UNIMPLEMENTED` |

**关于 Anthropic 那一列**：取自 `anthropic.types.shared.error_object.ErrorObject` 这个以 `type` 为 discriminator 的九成员 union，与 `anthropic.types.shared.error_type.ErrorType` 交叉核对一致（评审独立验证，方法比清点的目录正则强）。

**今天这一列是错的**：`WIRE_TYPES` 的 `network_error`、`upstream_error`、`internal_error` 都不在这九个之内（我方实测），所以 Anthropic 腿的 SSE 错误帧一直在发**不属于官方 SDK 声明词汇表**的 `error.type`。

**结论只到这里，不再往前**：SDK 的 `APIStatusError.__init__` 对 `error.type` 只做 `cast`、没有 runtime validation，真实 API 也可能先于 SDK 发布新值。所以成立的是「不能声称它是合同内的 Anthropic 类型」，**不是**「Anthropic 不认识」——v2 那句超出了证据，v3 收窄。按官方词汇重映射仍然是对的目标。

**关于 OpenAI 那一列**：`ErrorObject.type` 是裸 `str`（实测 `openai==3.3.1`），没有 Literal 也没有 enum，官方错误指南也没有为这些字符串背书。所以这一列的表头写的是「**本代理约定的**」——它不模拟 OpenAI 的封闭词汇，因为那个词汇不存在。

**正因为它是裸 `str`，就没有理由把 `AUTH`、`PERMISSION`、`NOT_FOUND` 压成 `invalid_request_error`**（v2 那样做了，是为了填表）。v3 保留区分。

### 6.2 类别 → status / 默认 code / retry 指令

**只定义 `type` 字符串不足以定义客户端动作。** 两个 SDK 都按 HTTP status 选异常类，且都默认重试 **408 / 409 / 429 / ≥500**，都识别 `x-should-retry`（实测四条，`_base_client.py` 逐条核对）。

| `ErrorCategory` | status | 默认 `code` | `x-should-retry` |
|---|---|---|---|
| `CLIENT` | 400 | `invalid_request` | —（400 本就不重试） |
| `AUTH` | 401 | `authentication_failed` | — |
| `PERMISSION` | 403 | `permission_denied` | — |
| `BILLING` | 403 | `billing_issue` | — |
| `NOT_FOUND` | 404 | `not_found` | — |
| `RATE_LIMIT` | 429 | `rate_limited` | 不设，保留 SDK 默认重试 |
| `OVERLOADED` | 503 | `overloaded` | 不设，保留 SDK 默认重试 |
| `TIMEOUT` | 504 | `timeout` | 不设，保留 SDK 默认重试 |
| `NETWORK` | 502 | `upstream_network_failure` | 不设 |
| `UPSTREAM` | 502 | `upstream_failure` | 不设 |
| `INTERNAL` | 500 | `proxy_internal_error` | **`false`** —— 代理自己的 bug，重试同一请求不会好 |
| `NOT_IMPLEMENTED` | 501 | `not_implemented` | **`false`** —— 否则两个 SDK 都会把它当 ≥500 自动重试，而这个类别存在的理由正是「重试没用」 |

**直连路径上，status 来自上游而不是这张表**（§3.1）。这张表管的是本代理产生的错误，以及翻译路径上重新渲染的错误。

### 6.3 各方言的 carrier：JSON 与流式分别列

**v2 说「SSE 的 error 帧与 JSON body 是同一个信封的两种包装」，对 OpenAI Responses 不成立**——它的 `ResponseErrorEvent` 是**扁平**的 `{"type":"error","code","message","param","sequence_number"}`，事件 `type` 固定为字面量 `"error"`，没有嵌套 `error` 对象，也没有独立的 category 字段。现有 `ResponsesFramer.error()` 正是因此把 category 放进 `message` 而不是复用 JSON 信封。

规范改为：**同一语义事实，按各协议各自合法的 error carrier 写出**。

| 方言 | 非流式 JSON | 流式 |
|---|---|---|
| `anthropic-messages` | `{"type":"error","error":{"type":<vocab>,"message":…,"code":…}}` | `event: error` + 同一对象 |
| `openai-chat-completions` / `openai-embeddings` | `{"error":{"message":…,"type":<vocab>,"param":…,"code":…}}` | 该腿今天没有 framer，见 §8 |
| `openai-responses` | 同上 | `event: error` + **扁平** `{"type":"error","code":…,"message":…,"param":…,"sequence_number":…}`；category 走 `code` |
| `gemini-generate-content` | `{"error":{"code":<int>,"message":…,"status":<VOCAB>}}` | 未实现（§11） |

### 6.4 `code` 是本项目的扩展，不是方言天然提供的通道

Anthropic 的九个 `ErrorObject` 成员都只声明 `message` 与 `type`；`error_frame()` 现在加的 `code` 是**本项目的扩展**。Python SDK 会把 raw body 的 dict 留在 `APIStatusError.body` 里，但只把 `.type` 提升为 typed 属性，**没有一等 `.code`**。

所以：

- `code` 标为**版本化的本项目扩展**，在 §6.2 里定义默认值。
- **不得用它来论证 §6.1 的分辨率损失已被补回**（v2 那样做了）。`NETWORK` / `UPSTREAM` / `INTERNAL` / `NOT_IMPLEMENTED` 在 Anthropic 侧都塌成 `api_error`，客户端要区分它们只能读这个扩展字段，而**目前没有已知消费者在读**。真正保住客户端动作差异的是 §6.2 的 status 与 `x-should-retry`，不是 `code`。
- 若将来有已知客户端解析它，在此列出该解析器与解析失败的后果。

## 7. 流式与非流式必须表达同一件事

同一个端点上，一个错误发生在响应头提交之前还是之后，客户端得到的**语义事实必须一致**；**形状按 §6.3 各自合法的 carrier**，不要求逐字节同形。今天分界线是实现时序而非协议，本 Spec 取消它。

## 8. `framer is None` 那条腿：本 Spec 不解决，但要说准

inbound 是 Chat Completions 且流式时，那条腿没有 framer，写不出任何错误帧。§7 的不变量对它**带例外**，此处显式写明而不是靠 §11 的排除暗示。

「给 Chat Completions 找块边界」已被裁决推迟，本 Spec 不展开。要求：

- 修正 `inference.py` 里那句与实测不符的注释——它说守卫触发时客户端拿到空 body，实测拿到的是**已到达的上游字节**（清点实测 69 字节），只是没有任何错误帧。
- 把「这条腿缺少合法的 streaming error carrier」登记为**待裁决**（§10.2），而不是当作已满足。

## 9. Gemini 的 501 纳入本切片

`route.implemented=False` 是本代理产生的错误，Gemini 三条路径今天恰好答 501，而**错误 writer 就是 Gemini 端点当前唯一的 wire 输出**。v2 一边在 §2 要求所有本代理错误按客户端方言写出，一边在范围外排除 Gemini，两者不能同时成立。

v3 纳入：**Gemini 的 501 用 Gemini 的错误信封**。这不要求实现成功请求的翻译，只要求已有端点用它自己声明的错误格式。

## 10. 待用户裁决

### 10.1 翻译路径上读不动的上游错误

裁决第 1 条的前提是直连，不适用；第 2 条的前提是「有判断力、需要支持」，也不适用；`message-translation.md` 的「**按需**理解和处理」把这一格留空。生产上会真的发生（上游改版、新错误码、供应商特有的失败）。

三个候选，以 Anthropic 客户端 + 未知 Responses 错误为例，给出完整 wire：

**候选 A —— 渲染 `UPSTREAM`，原文进一个命名扩展字段**

```json
{"type":"error","error":{"type":"api_error","message":"upstream failed and this proxy could not interpret its error","code":"upstream_failure","upstream_error":{"type":"vendor_specific_thing","detail":"…"}}}
```

客户端 SDK 一定能解析（`type`/`message` 齐备，多余字段留在 `.body` 里）。代价：`upstream_error` 是本项目扩展，Anthropic 的 `ErrorObject` 没声明它，**typed 属性拿不到**，客户端要读 raw body。

**候选 B —— 原样透传上游的错误体**

```json
{"error":{"code":"vendor_specific_thing","message":"…"}}
```

零信息损失、零维护。代价：Anthropic 客户端拿到一个没有顶层 `type` 的形状，SDK 的 `.type` 会是 `None` 或解析失败；与「翻译路径理应翻译」相抵触。

**候选 C —— 渲染 `UPSTREAM`，原文只进 `message`**

```json
{"type":"error","error":{"type":"api_error","message":"upstream failed and this proxy could not interpret its error: {\"code\":\"vendor_specific_thing\",\"message\":\"…\"}","code":"upstream_failure"}}
```

完全在方言的声明字段内，任何客户端都能读到全部信息。代价：原文变成一段人读的字符串，机器要二次解析；`message` 长度不可控。

**倾向 A**，理由是与既有的「翻译路径采用白名单」一致，且原文保持结构化。但三者的客户端可见后果不同，**请用户裁**。

**在裁决到达之前，不实施依赖这一格的任何公共行为。** 不依赖它的结构性部分（`ErrorInfo`、source → IR 表、各方言 writer、直连透传）可以先做。

### 10.2 Chat Completions 流式腿缺少合法的 error carrier

见 §8。它不是本 Spec 造成的，但 §7 的不变量因它而带例外。是否在本切片内为该腿实现错误表达，请用户裁。

## 11. 不在本 Spec 范围内（每条都登记，不静默排除）

- **成功响应的信封**。本 Spec 只管错误。
- **框架自身的 404 / 405**（`{"detail":…}`）。改它要接管 Starlette 的异常处理，属另一件事。**登记**：同一个 app 里因此有两种信封，客户端要按 `error` / `detail` 两个键试探。
- **响应头黑白名单的内容本身**。`message-format-reshape.md` 已规定，本 Spec 引用不改写。
- **Gemini 成功请求的 wire 翻译**。Gemini 的**错误**信封在范围内（§9）。
- **`app/errors.py` 里 `ApiError` / `classify_error` 的去留**。它们只被 `models/common.py` 与 `streaming/sse.py` 用，而那两处在当前链路上无路由消费。**登记**为独立的归档判断。
- **可观测性面与线路说法不一致**：客户端截止那一例，线路上写 `client_deadline_exceeded`，完成行写「upstream stream ended without a terminal event」（清点 §6.1，实测）。同一事件两种说法。**登记**。
- **`ResponsesAssembler` 不读 `output_item.done` 里的 content**，导致重成帧后 `output_text` 为空（清点 §10.4 顺带实测）。与错误面无关，**登记**。
