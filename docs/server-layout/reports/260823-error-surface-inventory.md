# 错误出口清点：一个错误最终以什么字节到达客户端

日期：2026-08-23
提交锚点：`9c4ba6c`（工作树另有未提交改动：`docs/.human-controlled/config.example.yaml` 已修改，`Dockerfile` 等未跟踪文件；均不在本次读的代码路径上）
方法：读源码定位出口，再用一次性探针在真实 ASGI 应用 + 真实 SDK + `httpx2.MockTransport` 上游下实测发出的字节。未改动任何源文件；探针在 `/home/xp/.claude/jobs/08aff420/tmp/probe_err{1,2,3,4,5,6,7,8}.py`。

本报告对每条结论标注 **实测** 或 **读码**。两者不混：凡标"读码"的，我没有跑出对应字节。

---

## 0. 判据：用户的架构裁决

> 1. 直连路径一定用原生的，即使我们未知，也能传递；
> 2. 翻译路径，按需建立 IR 机制，有判断力、需要支持的情况，都要先映射到内部已知概念，再按需转出实际格式。

术语落到代码：**直连**＝`Route.translation_required is False`（`routing.py:119`，`target_format is not inbound_format` 取反）；**翻译**＝该标志为 True。

一个出口可能同时被两条路径走到（`error_body` 就是），此时我按"它在直连路径上会发生什么"来判第 1 条，按"它在翻译路径上会发生什么"判第 2 条。请求尚未到达上游就失败的出口（body 解析、路由拒绝、框架 404/405），既没有上游原生可传，也不涉及格式转换，我判为"与路径无关"，裁决不适用。

---

## 1. 清单表

共清点出 **20 个出口**，其中 **5 个不符合裁决**（E6、E7、E8、E14、E20）。

| # | 出口（文件:行） | 触发条件 | 实际发出的字节形状 | 路径归属 | 是否符合裁决 |
|---|---|---|---|---|---|
| E1 | `server/routes/inference.py:146` | `route_for_path` 返回 None。代码注释自述为防御性、不可达 | `404` + `{"error":{"message":"unknown endpoint"}}` | 无关 | 不适用（**读码**，未实测到可达） |
| E2 | `server/routes/inference.py:154-156` | 路由 `implemented=False`（三条 Gemini 路径） | `501` + `{"error":{"message":"/v1beta/models/gemini-pro:generateContent is not implemented yet"}}` | 无关 | 不适用（**实测**） |
| E3 | `server/routes/inference.py:162` | `request.json()` 抛 `ValueError` | `400` + `{"error":{"message":"body is not valid JSON"}}` | 无关 | 不适用（**实测**） |
| E4 | `server/routes/inference.py:165` | 顶层 JSON 不是对象 | `400` + `{"error":{"message":"body must be an object"}}` | 无关 | 不适用（**实测**） |
| E5 | `server/routes/inference.py:173` | `InboundRequestError`：缺 model、路径段为空、不可流式端点请求 stream | `400` + `{"error":{"type":"InboundRequestError","message":"…"}}` | 无关 | 不适用（**实测**，三种触发条件各测一次） |
| E6 | `server/routes/inference.py:207-211` | count_tokens 端点上任何失败 | `503` + `{"error":{"type":"CountTokensUnavailable","message":"no token counter succeeded: ghc:0:UpstreamRejected"}}` | 直连 | **不符合第 1 条**（**实测**，上游 400 与上游 500 都被压成 503，上游原生 body 一个字节都没到客户端） |
| E7 | `server/routes/inference.py:255-259` | `handle_bounded` 抛出（含重试耗尽后的 `PipelineAbort`） | `error_status`/`error_headers`/`error_body` 三件套，见 §2 | 直连＋翻译 | **不符合第 1、2 条**（**实测**） |
| E8 | `server/routes/inference.py:274-278` | 驱动把失败放在 `outcome.error` 而不是抛出（上游拒绝走的就是这条） | 与 E7 完全同形 | 直连＋翻译 | **不符合第 1、2 条**（**实测**，字节形状与 E7 无法区分） |
| E9 | `pipeline/delivery/stream.py:359` | 响应头已提交后 `client_request_deadline` 到期 | Anthropic 腿：`event: error` + `{"type":"error","error":{"type":"internal_error","message":"client request exceeded its deadline","code":"client_deadline_exceeded"}}` | 直连＋翻译 | 符合（**实测**，本侧时钟事件，无上游原生可传） |
| E10 | `pipeline/delivery/stream.py:417-429` | 上游撕裂 / 本侧交付失败 / `DeliveryError`，且 hand-over 未接管 | 三个 code：`upstream_stream_failed`、`proxy_delivery_failed`、`proxy_delivery_aborted`；帧后仍 `raise torn` | 直连＋翻译 | 符合（**实测** 到前者与 `proxy_delivery_aborted`；`proxy_delivery_failed` 未实测，见 §9 第 3 条） |
| E11 | `pipeline/delivery/stream.py:473-478` | 上游 EOF 且切在块中间，或 `unterminated_stream_stop_reason` 置空 | `event: error` + `code:"incomplete_responses_stream"` | 直连＋翻译 | 符合（**读码**，本次未构造出切在块中的 EOF） |
| E12 | `pipeline/delivery/stream.py:464-467` | 上游在块边界干净 EOF、无终结事件 | `message_delta`（`stop_reason:"incomplete"`）+ `message_stop`，**看起来像正常收尾** | 直连＋翻译 | 符合裁决本身，但它是 E20 的显现处（**实测**） |
| E13 | `pipeline/delivery/stream.py:485-520` + `pipeline/hand_over.py:219` | 可继续的失败/`max_tokens`，且 inbound 是 Anthropic Messages 且配置了工具名 | 合成 `tool_use` 块，`input` 里带 `{"num_messages":…,"category":"network","message":"httpx2.RemoteProtocolError: …"}`，`stop_reason:"tool_use"` | 直连＋翻译（仅 Anthropic 腿） | 符合第 2 条（**实测**，错误被映射成 `RetryReason`/`ErrorCategory` 后再转出为该腿的语言） |
| E14 | `pipeline/delivery/stream.py:194-214`（`one_shot_delivery`），由 `inference.py:309-344` 选中 | inbound 是 Chat Completions（无 framer）且流式，任何守卫触发或上游撕裂 | 已到达的上游字节原样交出，**没有任何错误帧**，`more_body` 停在 `True`（连接裸断，无终止 chunk） | 直连 | **不符合第 1 条的精神**（**实测**，见 §6 的限定） |
| E15 | `pipeline/driver.py:183-208`（`_answered_failed_search`） | `WebSearchNotExecutable` | `200` + Anthropic `web_search_tool_result` 且 `is_error` | 翻译 | 符合第 2 条（**读码**，本次未构造触发） |
| E16 | Starlette 路由（未注册路径） | 任何未注册 URL | `404` + `{"detail":"Not Found"}` — **信封与我们的不同** | 无关 | 不适用（**实测**） |
| E17 | Starlette 路由（方法不匹配） | 对已注册路径用 GET/HEAD | `405` + `{"detail":"Method Not Allowed"}` + `allow: POST` | 无关 | 不适用（**实测**） |
| E18 | `starlette.middleware.errors.ServerErrorMiddleware` | `_dispatch` 里逃出的任何异常（例：上游 200 但 body 不是 JSON，`response.json()` 抛 `JSONDecodeError`） | `500` + `text/plain` + `Internal Server Error` | 无关（但由直连/翻译路径产生） | 不适用（**实测**） |
| E19 | `server/routes/ops.py:44-47` | 目录为空 | `503` + `{"status":"uninitialized","providers":{…}}`，**没有 `error` 键** | 无关 | 不适用（**读码**，本次只测到 `ready` 的 200） |
| E20 | `delivery/formats/anthropic_messages.py:288-301` 与 `formats/openai_responses.py:433-452` | 上游在流中发 `event: error` / `response.failed` / `response.cancelled` | **零字节到达客户端**。只写一条 `logger.warning`，客户端拿到 E12 的正常收尾 | 直连＋翻译 | **不符合第 1 条**（**实测**，两条腿各测一次） |

---

## 2. `UpstreamRejected` 携带的原文到底是什么（问题 1）

**结论：客户端 body 里的两处上游原文，来源不同、可靠性不同，而字节级原文在任何地方都不存在。**

### 2.1 `message` 里的 Python dict repr —— 来源

`http_errors.py:72` 把 `str(error)` 直接放进 `message`。这个 `str` 最终来自 `model_provider/ghc_client/errors.py:128` 的 f-string：

```python
return UpstreamRejected(
    f"upstream rejected the request: {error}",
    ...
)
```

其中 `error` 是 SDK 的 `APIStatusError`。SDK 构造它的 message 时先 `json.loads(response.text)`，成功就写 `f"Error code: {status} - {body}"` —— `body` 是一个 **Python dict**，于是 f-string 走 `dict.__str__`，得到单引号的 repr。**实测**（探针 1 用例 1）：

```
"message":"upstream rejected the request: Error code: 400 - {'error': {'type': 'invalid_request_error', 'message': 'bad tool', 'param': 'tools[0]'}}"
```

这串不是 JSON，也不是任何协议的合法错误体，任何客户端都解析不了。它**不总是这个形状**：**实测**上游答 `text/html` 时是 `upstream rejected the request: <html><body>Bad Request</body></html>`（SDK 在 JSON 解析失败时改用 `response.text.strip()`，并且**不加** `Error code:` 前缀）；上游答空 body 时是 `upstream rejected the request: Error code: 400`（无正文段）。所以三种形状轮换，全由 SDK 的分支决定，本项目没有一处代码知道自己在往 `message` 里放什么。

### 2.2 `upstream` 键里的 JSON 字符串 —— 来源

`http_errors.py:85-88`：

```python
upstream = getattr(detail, "body", "")
if isinstance(upstream, str) and upstream:
    body["upstream"] = upstream
```

`detail.body` 来自 `errors.py:118` 的 `_response_parts`，取的是 `response.text`（`errors.py:84-85`）。它是 **`str`，不是 `bytes`** —— httpx 已按 charset 解码过一遍。放进 JSON 响应时又被序列化成一个字符串字面量，于是客户端拿到的是转义过的 `"{\"error\":{...}}"`，要二次解析才能用。

**是否总是存在**：不总是。`if isinstance(upstream, str) and upstream` 决定了空 body 时该键整个消失（**实测**，探针 1 用例 4 的响应里没有 `upstream` 键）。这是本项目已记录过的"缺席读不出来"形状：客户端无法区分"上游没说"与"我们没转"。

### 2.3 原始字节还在某处可取吗

**不在。**（**读码**，三处都查过）

- `errors.py:_response_parts` 只取 `response.text`，解码后的 `str`。SDK 的 response 对象连同 `.content` 在异常被翻译的那一刻就丢了（`normalize_upstream_error` 返回新异常，旧异常与其 response 无人持有）。
- `UpstreamRejected.sent`（`exceptions.py:76`）保留的是**请求**字节，不是响应字节；它只被 `observability/rejection_capture.py:78` 用来落盘。
- `rejection_capture` 落盘的 `upstream` 字段（`rejection_capture.py:62`）也是 `error.body`，同一个已解码的 `str`。该文件明确写着"Headers are not written"。

所以：上游错误响应的**字节**在 `_response_parts` 那一行就永久丢失，此后全系统只有它的 UTF-8 解码投影。

### 2.4 附带发现：`error.headers` 全系统零消费者

`UpstreamError.headers`（`exceptions.py:38`）与 `UpstreamRejected.headers`（`exceptions.py:80`）都被赋值，但 **`rg '\.headers' src/app --glob '!.archived/**'` 在整个在用源码里，除这两行赋值外没有任何读取点**（**实测**，命令与输出见 §10.9；唯一的第三处命中 `upstream/ghc_settings.py:13` 是另一个对象的同名属性）。也就是说：直连路径要"原样传递上游错误头"所需的原料**已经躺在异常对象上了**，只是没有一个出口去读它。`error_headers` 只从 `UpstreamRateLimit.retry_after` 重新格式化出一个 `retry-after`，而那个值本身是 `retry_after_seconds(headers)` 解析后再 `str(int(...))` 回去的——原头的写法（比如 HTTP-date 形式）也丢了。

---

## 3. 状态码：直连路径上是否原样透传（问题 2）

**结论：只有"不可重试的 4xx"透传，其余全部改写。**（**实测**，逐个状态码跑过）

| 上游状态 | 客户端拿到 | 机制 |
|---|---|---|
| 400 | **400** | `UpstreamRejected` → `error_status` 读 `status_code`（**实测**） |
| 404 | **404** | 同上（**实测**） |
| 418 | **418** | 同上（**实测**） |
| 401 | **502** | 401 在 `RETRYABLE_STATUSES` 里 → `UpstreamError` → 预算耗尽 → `PipelineAbort` → 落到 `error_status` 末尾的 `return 502`（**实测**） |
| 500 | **502** | 同上（**实测**） |
| 503 | **502** | 同上（**实测**，上游给的 `retry-after: 42` 也一并丢失） |
| 429 | **429** | 走 `UpstreamRateLimit` 分支，是重新判定而非透传（**实测**） |
| 408 / 409 / 425 | **502** | 同 401 的机制（**读码**，未逐个实测） |
| 502 | **502** | 巧合相同，机制上仍是改写（**读码**） |

也就是说，`RETRYABLE_STATUSES = {401, 408, 409, 425, 429, 500, 502, 503, 504}`（`errors.py:33`）里除 429 外的每一个，在预算耗尽后都会变成 502。502 的语义是"网关自己坏了"，与上游实际说的（凭证过期、过载、上游超时）都不同。`error_status` 的 docstring 本身写着"a client that gets 429 can back off and a client that gets 400 can fix its body; both learn nothing from a 502"——这条理由对 401/503 同样成立，但代码没覆盖它们。

补充：**成功**响应的状态码是透传的（`inference.py:512` 的 `status_code=response.status_code`，流式则是 `_AccountedStreamingResponse(..., status_code=response.status_code)`）。但这条路径上 SDK 已经对非 2xx 抛过异常了，所以那里实际只会是 2xx。

---

## 4. 响应头：直连路径上上游的其它错误相关头（问题 3）

**结论：除 `retry-after` 外全部不传，包括 `anthropic-ratelimit-*` 与 `x-request-id`；且 `retry-after` 只在 429 上出现。**（**实测**）

探针 1 用例 1 让上游在一个 **400** 上带了 `anthropic-ratelimit-requests-remaining: 17`、`x-request-id: req_abc`、`retry-after: 3`。客户端收到的全部响应头是：

```
content-length: 297
content-type: application/json
```

三个都没了，**包括 `retry-after`** ——因为 `error_headers`（`http_errors.py:67`）只在 `isinstance(error, UpstreamRateLimit)` 时才发它。探针 1 用例 7（上游 429）确实收到了 `retry-after: 7`，但同一响应里的 `anthropic-ratelimit-requests-reset` 依然被丢弃。

`error_headers` 的 docstring 自述是"allowlist rather than forwarding upstream's set, which carries its own framing headers"。这个理由对**框架头**（`content-length`、`transfer-encoding`、`content-encoding`）成立，对 `anthropic-ratelimit-*`、`x-request-id`、`openai-*` 这类**语义头**不成立——它们既不影响 HTTP 分帧，又正是客户端排障要的东西。而直连路径上它们本就是客户端自己协议的一部分。

---

## 5. 非 JSON 的上游错误体（问题 4）

**实测**，探针 1 用例 3 与 4：

- 上游 `400` + `text/html` + `<html><body>Bad Request</body></html>`：客户端拿到 `400` + `{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: <html><body>Bad Request</body></html>","upstream":"<html><body>Bad Request</body></html>"}}`。HTML 原文被完整放进一个 JSON 字符串字段，没有崩，也没有丢；但 `message` 里那一份少了 `Error code: 400` 前缀（SDK 的分支差异），所以**同一个字段在不同 body 类型下语义不一致**。
- 上游 `400` + 空 body：`{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: Error code: 400"}}`。`upstream` 键整个消失。
- 上游 **200** + 非 JSON body（非流式）：`response.json()` 抛 `JSONDecodeError`，逃出 `_dispatch`，客户端拿到 **`500` + `text/plain` + `Internal Server Error`**（**实测**，探针 5 G5）。这是 E18，全系统唯一一个非 JSON 的错误响应。日志里有一行 `request failed before a response: JSONDecodeError(...)`，客户端那边什么信息也没有。

---

## 6. 流式：响应头提交之后上游才失败（问题 5）

响应头在拉第一个 chunk 之前就发出去了（`StreamingResponse.stream_response` 先 `http.response.start`），且带的是**上游自己的状态码**。所以此后一切失败都只能靠 SSE 帧表达。

> ⚠️ 测量方法上的一个坑，先说：**Starlette 的 `TestClient` 在流式响应异常终止时会把 body 读成空** ——它的 `send` 只在 `more_body=False` 时才 `stream.seek(0)`，异常路径永远走不到那句，于是 `httpx.Response` 从流尾开始读，得到 `b''`。我第一轮探针（`probe_err3.py`）因此把三个用例误读成"客户端拿到空 body"。第二轮改成直接驱动 ASGI 并捕获每一条 `http.response.body` 消息（`probe_err4.py`/`probe_err5.py`），才拿到真实字节。下面的数字都来自第二轮。

### 6.1 有 framer（Anthropic 腿 / Responses 腿）

**实测**：

| 场景 | 客户端实际拿到 |
|---|---|
| 交付过一个块后上游撕裂，inbound 是 Anthropic Messages | 不是错误帧，而是 **hand-over**：合成一个 `tool_use` 块把 `httpx2.RemoteProtocolError: peer closed the connection [request …, attempt 1]` 写进工具参数，然后 `stop_reason:"tool_use"` + `message_stop` 正常收尾。`more_body=False`，连接干净结束 |
| 同上但把 `auto_retry_tool_call_full_name` 置空（关掉 hand-over） | `event: error` + `{"type":"error","error":{"type":"upstream_error","message":"peer closed the connection","code":"upstream_stream_failed"}}`，然后异常继续上抛，`more_body` 停在 `True`（裸断） |
| inbound 是 OpenAI Responses（`/v1/responses`），上游撕裂 | 没有 hand-over（`hand_back_block` 在 `wire_format is not ANTHROPIC_MESSAGES` 时返回 None），拿到 `event: error` + `{"type":"error","sequence_number":8,"code":"upstream_stream_failed","message":"upstream_error: peer closed the connection","param":null}` |
| 客户端截止时间到期 | `event: error` + `code:"client_deadline_exceeded"`，且**正常收尾**（`more_body=False`，异常没有上抛） |
| 上游空闲超时（`stream_idle=1`） | `event: error` + `code:"upstream_stream_failed"` + `message:"No stream item received for 1s"`，裸断 |
| 缓冲上限超出（`buffer_cap_bytes=8`） | `event: error` + `{"type":"error","error":{"type":"internal_error","message":"buffered 30 bytes exceeds the 8 byte cap","code":"proxy_delivery_aborted"}}`，裸断。注意这一条**在 `message_start` 之前就发了**，客户端拿到的第一个也是唯一一个事件就是 error |

另外一处**实测**到的日志/线路不一致：客户端截止时间那一例，线路上写的是 `client_deadline_exceeded`，而完成行写的是 `upstream stream ended without a terminal event`（因为 `stream.py:364` 是 `return` 而非 `raise`，于是 `_tracked_delivery` 把它记成 `drained`）。两个面对同一事件给出两种说法。这不属于本次任务范围，登记在此。

### 6.2 无 framer（one-shot 腿）

**实测**，三个场景全部相同：客户端拿到**上游已到达的那部分原始字节，一个错误帧都没有，`more_body` 停在 `True`**。

- 上游撕裂：`b'data: {"id":"c1","choices":[{"index":0,"delta":{"content":"hel"}}]}\n\n'`，无 `data: [DONE]`
- 客户端截止时间到期：同上
- 上游空闲超时：同上

`inference.py:312` 的注释说"the guard's exception simply ends the response — 200, `text/event-stream`, and whatever had been buffered, which is nothing"。**这句话现在只对了一半**：`one_shot_delivery`（`stream.py:206-212`）在 `except Exception` 里会先 `yield bytes(body)` 再 `raise`，所以已到的字节**是**会交出去的，不是 nothing。我实测到 69 字节送达。注释描述的"空 body"是 2026-08-22 那条分支存在之前的状态，或者是被 `TestClient` 的同一个假象误导的读数。**这一处注释与当前行为不符，建议修正**。

关于 E14 的裁决判定，我给一个限定的说法：它不是"上游给了原生错误而我们没传"——三个场景里上游都没给错误体（是撕裂或本侧守卫）。它违反的是第 1 条的另一半："即使我们未知，也能传递"。这条腿对客户端**零信息**：SSE 层面没有任何事件说明发生了什么，HTTP 层面靠连接裸断表达，而 `data: [DONE]` 的缺席是唯一线索。我判为**不符合**，但请注意这条的证据强度弱于 E6/E7/E8/E20——那四条是有原生内容而没传，这条是没有原生内容也没合成。

---

## 7. 上游中途发来的 `event: error` —— 核实是否被转发（任务点）

**结论：完全没有被转发，一个字节都没有。**（**实测**，两条腿各测一次）

- Anthropic 腿（`anthropic_messages.py:288-301`）：上游发 `event: error` + `{"type":"error","error":{"type":"overloaded_error","message":"upstream is overloaded"}}` 然后 EOF。客户端拿到的是 `message_delta`（`stop_reason:"incomplete"`）+ `message_stop`——一个**看起来完全正常**的收尾。上游的 `overloaded_error` 只出现在进程自己的 `logger.warning` 里。
- Responses 腿（`openai_responses.py:433-452`）：上游发 `event: response.failed` + `{"response":{"error":{"code":"server_error","message":"boom"}}}` 然后 EOF。客户端拿到 `event: response.incomplete`，`status:"incomplete"`，`incomplete_details: null`，`error: null`。同样是正常终结形状。翻译路径（Anthropic 客户端 + Responses 上游）上，上游的 `event: error` 同样只进日志。

两处的代码注释都自述"Nothing here acts on it yet"，并把行动登记在 `.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条。所以这不是被忽略的缺陷，是已登记的待办。**但它对裁决第 1 条的违反程度比注释描述的更重**：注释说"the client receives the same `incomplete_responses_stream` frame a torn connection produces, and the two remain indistinguishable on the wire"——**这句话现在不成立了**。自 2026-08-22 的干净 EOF 改动（`stream.py:456-468`）落地后，块边界上的 EOF 走的是 `framer.terminal(stop_reason="incomplete")` 而**不是** `incomplete_responses_stream` 错误帧。也就是说上游明确说了"我失败了"，客户端收到的却是一次**语法上成功的收尾**。这比"与撕裂不可区分"更严重：它与**成功**不可区分。

---

## 8. 结构层面的发现：同一个进程里两套错误词汇，只有一套是 IR

这是我认为最值得先处理的一条，它直接对应裁决第 2 条。

- **SSE 出口用的是 IR**：`stream.py:360/418/474` 全部走 `WIRE_TYPES[ErrorCategory.X]`（`app/errors.py:13-20`）。`ErrorCategory` 是内部已知概念，`WIRE_TYPES` 是"转出实际格式"的那张表。Responses 腿甚至因为自己的 schema 没有 `type` 字段而把类别前缀进 `message`（`openai_responses.py:361`）——这正是裁决第 2 条描述的做法。
- **JSON 出口完全不经过它**：`http_errors.py:72` 的 `{"type": type(error).__name__}` 直接把 **Python 类名**放到线路上。客户端看到的是 `UpstreamRejected`、`PipelineAbort`、`InboundRequestError`、`TranslationRefused`、`CountTokensUnavailable`、`UnknownModel`、`CapabilityMissing`（后两个**实测**得到）。这些既不是任何协议的 wire type，也不是内部 IR 概念——它们是实现细节，重命名一个类就会改变对外契约。

顺带：`app/errors.py` 里的 `ApiError` 与 `classify_error` 在当前链路上**没有任何调用者**（`rg` 只查到 `WIRE_TYPES` 与 `ErrorCategory` 被 `stream.py` 用）。IR 的一半已经建好且在用，另一半闲置着。

还有一个**实测**到的一致性事实：**错误体形状与 inbound 格式完全无关**。`/v1/messages`、`/v1/responses`、`/v1/chat/completions`、`/v1/embeddings` 四个端点在上游 400 时返回的 body 字节**完全相同**（除 message 内容）。也就是说，一个 OpenAI SDK 客户端打 `/v1/responses` 拿到的错误体，既不是 OpenAI 的 `{"error":{"message","type","param","code"}}`，也不是 Anthropic 的 `{"type":"error","error":{...}}`。四种客户端都得学一套本项目专有的信封。

再叠一层：**同一个 app 里还有第三种信封**。框架的 404/405 用的是 `{"detail":"..."}`（**实测**），`inference.py` 自己的 404/501/400 用的是没有 `type` 的 `{"error":{"message":...}}`（**实测**），`error_body` 用的是带 `type` 的 `{"error":{"type":...,"message":...}}`（**实测**）。三种形状，客户端要么全解析，要么按 `error`/`detail` 两个键试探。

`error_body` 最丰富的一次输出（**实测**，`TranslationRefused` 路径）是四字段：

```json
{"error":{"type":"TranslationRefused","message":"bogus_key is not a field this endpoint's web search accepts, and removing it would silently discard whatever it asked for","code":"unsupported_field","field_path":"tools.web_search_20250305.bogus_key"}}
```

`code` 与 `field_path` 只有 `TranslationRefused` 带（`semantic.py:61-64`），`UpstreamRejected` 和 `PipelineAbort` 都不带（`getattr(detail,"code","")` 取不到）。这两个字段是本项目自己设计的、语义正确的机器可读通道，只服务于一个异常类。

---

## 9. 我没能实测到的部分（明说，不用推断填补）

1. **E1（`inference.py:146` 的 404）**：代码注释自述不可达，我没有构造出反例，也没有构造出证明它不可达的证据。只标"读码"。
2. **E11（`incomplete_responses_stream` 帧）**：需要 EOF 切在块中间（`cut_mid_block` 为真）。我构造的 EOF 都落在块边界上，走的是 E12。未实测。
3. **`proxy_delivery_failed`（E10 的第二个 code）**：需要"本侧失败但不是 `DeliveryError`"。我尝试用非法 JSON 的 SSE data 让 assembler 抛错——**没抛**：`sse_source.py:24-32` 的 `SseEvent.json()` 吞掉 `JSONDecodeError` 返回 `{}`（**实测**，客户端拿到的是正常的 `incomplete` 收尾）。这条分支读码上可达，实测未触发。
4. **E15（`_answered_failed_search`）**：未构造 `WebSearchNotExecutable`。只读码。
5. **E19（readiness 503）**：只测到目录非空的 200。未构造空目录。
6. **422**：我试了未注册路径、错误方法、空路径参数三种，都没有得到 422（分别是 404、405、400）。**读码**看，`build_router` 注册的 handler 是 `serve(request: Request)`，没有任何被 FastAPI 校验的 body model 或类型化 path param（`{deployment}`、`{model}` 都是 `str`），所以 422 大概率不可产生——但我没有穷举，这条只标到"未实测到可达"。
7. **408/409/425/502 的状态码改写**：只读码，未逐个跑。机制与 401/500/503 完全相同（同一个 `RETRYABLE_STATUSES` 分支），我判断这个外推是安全的，但它仍然是外推。
8. **HTTP/2 与真实 socket**：全部实测都在 `httpx2.MockTransport` + ASGI 直驱上做的，没有经过真实 TCP。"`more_body` 停在 `True` 等于连接裸断"这句是对 ASGI 语义的读码推断，我没有在真实 uvicorn 上抓过包确认客户端看到的是什么（chunked 编码下应当是缺少末尾 `0\r\n\r\n`）。

---

## 10. 实测证据：跑过的探针与原始输出

全部探针在 `/home/xp/.claude/jobs/08aff420/tmp/`，运行方式一律 `cd /home/xp/src/ghc-api-proxy-py && uv run python <path>`（探针内 `sys.path.insert(0, "tests/int")` 依赖 cwd 为仓库根）。上游一律是 `tests/int/test_pipeline_app.py::make_client` 的 `httpx2.MockTransport`，SDK 是真实的 `AsyncOpenAI`/`AsyncAnthropic`。所有探针都把重试预算压到 0（`serverError`/`network`/`githubTokenExpired` 各 `max_retries: 0`，反应式限流三个间隔置 0），否则 429/5xx 会跑满 9 次退避。

### 10.1 `probe_err1.py` —— 非流式错误出口（9 例）

关键原始输出：

```
1 直连 /v1/messages -> /v1/messages，上游 400 JSON
  status = 400
  header content-length: 297
  header content-type: application/json
  raw body = b'{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: Error code: 400 - {\'error\': {\'type\': \'invalid_request_error\', \'message\': \'bad tool\', \'param\': \'tools[0]\'}}","upstream":"{\\"error\\":{\\"type\\":\\"invalid_request_error\\",\\"message\\":\\"bad tool\\",\\"param\\":\\"tools[0]\\"}}"}}'
```

该用例上游带了 `anthropic-ratelimit-requests-remaining: 17`、`x-request-id: req_abc`、`retry-after: 3` 三个头，客户端一个都没收到（响应头只有 `content-length` 与 `content-type`）。

```
2 翻译 /v1/messages -> /responses，上游 400 JSON
  status = 400
  raw body = b'{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: Error code: 400 - {\'error\': {...}}","upstream":"{\\"error\\":{...}}"}}'
```

与用例 1 逐字节同形——直连与翻译在这个出口上不可区分。

```
3 直连，上游 400 text/html
  raw body = b'{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: <html><body>Bad Request</body></html>","upstream":"<html><body>Bad Request</body></html>"}}'

4 直连，上游 400 空 body
  raw body = b'{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: Error code: 400"}}'

5 直连，上游 401
  status = 502
  raw body = b'{"error":{"type":"PipelineAbort","message":"githubTokenExpired budget exhausted: upstream returned 401: Error code: 401 - {\'error\': {\'message\': \'token expired\'}}","upstream":"{\\"error\\":{\\"message\\":\\"token expired\\"}}"}}'

6 直连，上游 503（上游带 retry-after: 42）
  status = 502
  header 只有 content-length / content-type
  raw body = b'{"error":{"type":"PipelineAbort","message":"serverError budget exhausted: upstream returned 503: ...","upstream":"..."}}'

7 直连，上游 429 带 retry-after
  status = 429
  header retry-after: 7
  raw body = b'{"error":{"type":"PipelineAbort","message":"serverError budget exhausted: upstream rate limited: ...","upstream":"..."}}'

8 直连，上游 418  → status = 418，type=UpstreamRejected
9 直连，上游 404  → status = 404，type=UpstreamRejected
```

### 10.2 `probe_err2.py` —— 边缘与框架出口（14 例）

```
A 未注册路径 POST /nope   → 404  b'{"detail":"Not Found"}'
B 未注册路径 GET /nope    → 404  b'{"detail":"Not Found"}'
C GET /v1/messages       → 405  allow: POST   b'{"detail":"Method Not Allowed"}'
D POST /v1beta/models/gemini-pro:generateContent
                         → 501  b'{"error":{"message":"/v1beta/models/gemini-pro:generateContent is not implemented yet"}}'
E body 不是 JSON          → 400  b'{"error":{"message":"body is not valid JSON"}}'
F body 是 JSON 但不是对象  → 400  b'{"error":{"message":"body must be an object"}}'
G body 缺 model           → 400  b'{"error":{"type":"InboundRequestError","message":"request body must carry a non-empty string model"}}'
H /v1/embeddings 请求 stream
                         → 400  b'{"error":{"type":"InboundRequestError","message":"/embeddings does not support streaming"}}'
I /openai/deployments/%20/responses
                         → 400  b'{"error":{"type":"InboundRequestError","message":"/openai/deployments/{deployment}/responses takes the model from the path, and that segment is empty"}}'
J 未知模型                 → 400  b'{"error":{"type":"UnknownModel","message":"ghc does not offer model \'no-such-model\'"}}'
K mute-model（无 endpoint）→ 400  b'{"error":{"type":"CapabilityMissing","message":"ghc advertises no endpoints for model \'mute-model\'"}}'
L GET /health/readiness   → 200  b'{"status":"ready","providers":{"ghc":{"models":6}}}'
M GET /metrics            → 200  text/plain
N HEAD /v1/messages       → 405
```

### 10.3 `probe_err3.py` —— 流式（**这一轮的读数不可用**）

保留在磁盘上作为记录。它用 `TestClient` 读流式响应，三个用例（S3 `/v1/responses` 撕裂、S4 Chat Completions 撕裂、S5 Chat Completions 正常）报出 `raw body = b''`。S5 正常结束的那一例后来在 `probe_err4` 里得到 69 字节，证明 `b''` 是 `TestClient` 的假象而非事实。**教训**：`TestClient` 的 `send` 只在 `more_body=False` 时 `stream.seek(0)`，任何异常终止的流式响应都会被读成空。要看流式的真实字节必须直驱 ASGI。

### 10.4 `probe_err4.py` —— 直驱 ASGI，捕获每一条 `http.response.body`

```
R1 直连 Responses /v1/responses（ResponsesFramer），撕裂
  status = 200
  body 消息数 = 9
  最后一条 more_body = True
  实际发给客户端的字节 = …（前 8 条是重新成帧的 response.created / in_progress / output_item.added / content_part.added /
     output_text.delta / output_text.done / content_part.done / output_item.done）…
     b'event: error\ndata: {"type":"error","sequence_number":8,"code":"upstream_stream_failed","message":"upstream_error: peer closed the connection","param":null}\n\n'
  逃出 app 的异常 = RemoteProtocolError('peer closed the connection')

R2 Chat Completions 无 framer one-shot，撕裂
  body 消息数 = 1
  最后一条 more_body = True
  实际字节 = b'data: {"id":"c1","choices":[{"index":0,"delta":{"content":"hel"}}]}\n\n'
  逃出 app 的异常 = RemoteProtocolError('peer closed the connection')

R3 直连 Anthropic 流，撕裂
  body 消息数 = 10
  最后一条 more_body = False
  实际字节 = message_start / content_block_start / content_block_delta("hello") / content_block_stop
     / content_block_start(tool_use, mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted)
     / content_block_delta(input_json_delta: {"num_messages":0,"category":"network",
       "message":"httpx2.RemoteProtocolError: peer closed the connection [request …, attempt 1]"})
     / content_block_stop / message_delta(stop_reason:"tool_use") / message_stop
  逃出 app 的异常 = None

R4 同 R3 但 auto_retry_tool_call_full_name 置空
  body 消息数 = 5
  最后一条 more_body = True
  实际字节 = message_start / content_block_start / content_block_delta / content_block_stop
     / b'event: error\ndata: {"type":"error","error":{"type":"upstream_error","message":"peer closed the connection","code":"upstream_stream_failed"}}\n\n'
  逃出 app 的异常 = RemoteProtocolError('peer closed the connection')
```

R1 顺带暴露一处与错误面无关的内容问题：上游 `output_item.done` 里带 `"text":"hello"`，重新成帧后 `output_text.delta` 与 `done` 都是空串（`ResponsesAssembler` 只从 delta 累积，不读 `done` 里的 content）。**实测**，但不在本次任务范围，登记于此。

### 10.5 `probe_err5.py` —— 守卫触发（8 例）

```
G1 有 framer：client_request_deadline=1
  最后一条 more_body = False
  末帧 = event: error / {"type":"error","error":{"type":"internal_error","message":"client request exceeded its deadline","code":"client_deadline_exceeded"}}
  逃出 app 的异常 = None
  ⚠️ 同一请求的完成行写的是 "upstream stream ended without a terminal event"，与线路说法不一致

G2 无 framer：client_request_deadline=1
  实际字节 = b'data: {"id":"c1",...}\n\n'   （无错误帧，more_body=True）
  逃出 app 的异常 = ClientDeadlineError('client request exceeded its deadline')

G3 无 framer：stream_idle=1
  实际字节 = b'data: {"id":"c1",...}\n\n'   （无错误帧，more_body=True）
  逃出 app 的异常 = StreamIdleTimeoutError('No stream item received for 1s')

G4 有 framer：stream_idle=1
  末帧 = event: error / {"type":"error","error":{"type":"upstream_error","message":"No stream item received for 1s","code":"upstream_stream_failed"}}

G5 非流式：上游 200 但 body 是 <html>not json</html>
  status = 500
  header content-type: text/plain; charset=utf-8
  实际字节 = b'Internal Server Error'
  逃出 app 的异常 = JSONDecodeError('Expecting value: line 1 column 1 (char 0)')

G6 count_tokens：上游 500（providers=["ghc"]）
  status = 503
  实际字节 = b'{"error":{"type":"CountTokensUnavailable","message":"no token counter succeeded: ghc:0:UpstreamError"}}'

G7 count_tokens：上游 400
  status = 503
  实际字节 = b'{"error":{"type":"CountTokensUnavailable","message":"no token counter succeeded: ghc:0:UpstreamRejected"}}'

G8 buffering_policy=full, buffer_cap_bytes=8
  实际字节 = b'event: error\ndata: {"type":"error","error":{"type":"internal_error","message":"buffered 30 bytes exceeds the 8 byte cap","code":"proxy_delivery_aborted"}}\n\n'
  逃出 app 的异常 = BufferCapExceeded('buffered 30 bytes exceeds the 8 byte cap')
```

G6/G7 是 E6 的证据：上游说的是 500 与 400 两件完全不同的事，客户端两次都拿到 503，且上游的 body 一个字节都没出现。`inference.py:206` 的注释已经承认了这一点（"a counting request refused over its body answers 503 rather than upstream's own verdict, which is a separate gap"）。

### 10.6 `probe_err6.py` —— 上游 SSE 错误事件（3 例）

```
P1 有 framer：SSE data 是非法 JSON
  实际字节 = message_start / content_block_start / content_block_delta(text:"") / content_block_stop
     / message_delta(stop_reason:"incomplete") / message_stop
  逃出 app 的异常 = None
  → assembler 没有抛错（SseEvent.json() 吞掉 JSONDecodeError），proxy_delivery_failed 未触发

P2 翻译路径：上游 Responses 发 event: error 后 EOF
  进程日志：upstream sent 'error' mid-stream; it is not acted on yet: code='upstream_boom' message='upstream fell over'
  实际字节 = message_start / … / message_delta(stop_reason:"incomplete") / message_stop
  → 上游的 upstream_boom / "upstream fell over" 零字节送达

P3 直连 Responses：上游发 response.failed 后 EOF
  进程日志：upstream sent 'response.failed' mid-stream; it is not acted on yet: code='server_error' message='boom'
  末帧 = event: response.incomplete / {"status":"incomplete","error":null,"incomplete_details":null,...}
  → 上游的 server_error / "boom" 零字节送达，且客户端拿到的是一个 error 字段为 null 的正常终结
```

### 10.7 `probe_err7.py` —— 四种 inbound 格式的非流式错误体（4 例）

```
N1 /v1/responses      上游 400 → 400 b'{"error":{"type":"UpstreamRejected","message":"upstream rejected the request: Error code: 400 - {\'error\': ...}","upstream":"..."}}'
N2 /v1/chat/completions 上游 400 → 400 （与 N1 逐字节同形）
N3 /v1/embeddings      上游 400 → 400 （与 N1 逐字节同形）
N4 /v1/messages        上游 500 → 502 b'{"error":{"type":"PipelineAbort","message":"serverError budget exhausted: upstream returned 500: ...","upstream":"..."}}'
```

### 10.8 `probe_err8.py` —— `TranslationRefused` 的四字段错误体

```
T1 status = 400
   raw body = b'{"error":{"type":"TranslationRefused","message":"bogus_key is not a field this endpoint\'s web search accepts, and removing it would silently discard whatever it asked for","code":"unsupported_field","field_path":"tools.web_search_20250305.bogus_key"}}'
```

### 10.9 静态核查命令与结果

```
$ rg -n "\.headers" src/app --glob '!.archived/**' | grep -vi "request.headers|client_headers|response.headers|resp.headers"
src/app/pipeline/exceptions.py:38:        self.headers: Mapping[str, str] = dict(headers or {})
src/app/pipeline/exceptions.py:80:        self.headers: Mapping[str, str] = dict(headers or {})
src/app/upstream/ghc_settings.py:13:    versions = settings.headers
```

前两条都是赋值，没有读取点；第三条是 `GhcSettings` 对象的同名属性，与异常无关。→ `UpstreamError.headers` 与 `UpstreamRejected.headers` 在整个在用源码里零消费者（`.archived/` 未纳入搜索范围，那是遗留链路）。

```
$ rg -n "JSONResponse\(|PlainTextResponse\(|raise HTTPException" src/app --glob '!.archived/**'
```

用来穷举响应产生点，结果已并入 §1 的清单表。`src/app/streaming/sse.py` 里的 `create_sse_response` / `DelayedStartStreamingResponse` / `render_error` 只被 `app/streaming/__init__.py` 再导出，当前链路上没有路由消费它们（`rg -l` 确认），属于遗留链路，未计入清单。

---

## 11. 建议（不构成裁决，供主会话与用户判断）

按我的优先级排序，理由都在上文：

1. **E20 最先处理**。上游明确说了"我失败了"，客户端却拿到语法上成功的收尾——这是**唯一一个把失败伪装成成功**的出口，其余出口至少还让客户端知道出事了。它的代价与 `.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条登记时相比已经变了（当时是"与撕裂不可区分"，现在是"与成功不可区分"），建议重新定级。同时修正 `anthropic_messages.py:289` 与 `openai_responses.py:434` 的注释——它们还在说会产生 `incomplete_responses_stream`。
2. **把 `error_body` 接到已有的 IR 上**。`ErrorCategory` + `WIRE_TYPES` 已经在 SSE 出口跑着，JSON 出口却在发 Python 类名。这是裁决第 2 条在同一个进程里被执行了一半。补齐它同时也是给"每条腿转出自己的错误信封"打地基。
3. **直连路径的原生传递，从最便宜的一项开始：响应头**。原料已经在 `UpstreamRejected.headers`/`UpstreamError.headers` 上，零消费者，只差一个读取点与一份"哪些头是分帧头"的判据。
4. **状态码改写的口子（E7/E8）**。`RETRYABLE_STATUSES` 里除 429 外全部落到 502，而 `error_status` 自己的 docstring 已经论证过为什么不该这样。这条改动面小、语义收益大。
5. **`message` 里的 Python dict repr**。它是 SDK 的实现细节泄漏，形状随上游 content-type 三变。至少不应该是客户端唯一能读到的那份上游原文。
6. **E14（one-shot 腿）与 `inference.py:312` 的注释**。注释描述的"空 body"与实测不符，先修注释；这条腿要不要有错误表达是产品问题，与"给 Chat Completions 找块边界"是同一件工作，已被裁决推迟，我不建议在本轮内展开。
7. **E18（500 text/plain）**。上游 200 但 body 不是 JSON 时客户端拿到 `Internal Server Error` 五个字。加一个 `response.json()` 的显式捕获就能变成一条带信息的错误，成本极低。
