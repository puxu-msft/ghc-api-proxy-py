# 裸 `h2.exceptions.ProtocolError` 在 body 路径上落 `internal` —— 可达性、影响面与修法

> 调查日期 2026-08-23。代码基线：`main` 的 `d6edd1a`（`refactor: make the auto mode interception the scalar switch its spec defines`，2026-08-23 08:55:40 +0000）。本次调查未修改任何代码或测试；所有实测都通过一次性探针脚本（`/tmp/h2probe/`）与运行期 pytest 插件完成，仓库工作树未被本次调查改动。
>
> 调查期间主工作树里有同伴的未提交改动（`docs/.human-controlled/config.example.yaml`、`src/app/config/schema.py`、`src/app/pipeline/auto_mode_classifier.py`、`src/app/pipeline/driver.py`、`tests/unit/pipeline/test_auto_mode_classifier.py`）。本报告引用的三个文件——`src/app/pipeline/delivery/stream.py`、`src/app/pipeline/hand_over.py`、`src/app/model_provider/ghc_client/errors.py`——**均不在这份脏文件清单里**，所以下文的 `文件:行号` 与 `d6edd1a` 的提交态一致。
>
> 一个必须先说的观测保质期问题：本次全量测试跑了两遍，第一遍 33 failed（其中约 30 条在 `tests/unit/pipeline/test_auto_mode_classifier.py`），第二遍只剩 3 failed。差别不是我的探针，是同伴在两遍之间改了工作树。**因此本报告里任何「测试红/绿」的结论都只对我实测的那几个测试点负责**（见 §4.3），不对全量套件的当时状态负责。

---

## 0. 结论速览

| 问题 | 结论 | 证据等级 |
|---|---|---|
| 1. body 路径上裸 `h2.ProtocolError` 可不可达？ | **有条件可达**，条件有 5 项，默认配置下全部满足（见 §1.4） | 代码直读 + 本次实测（端到端 `stream_delivery` 探针，实际发出 `"category": "internal"`） |
| 2. `internal` 在本仓有没有行为后果？ | **没有任何本仓消费者**。唯一读者是 MCP server 与模型 | 代码直读（穷举 grep，含 `ErrorCategory`、`"category"`、`internal_error`、observability、server） |
| 3. 还有哪些异常同类？ | 见 §3 的表。**错报 2 类**（h2 全族、`httpx2.DecodingError`），**正确 1 类**（framing 层 bug） | 代码直读；h2 与 framing 两条本次实测，`DecodingError` 只有代码直读 |
| 4. 最小改动？ | 三条路径 (a)/(b)/(c)，副作用差别在「要不要连带变成可重放」。**我的倾向是 (a)** | 代码直读 + 本次实测（运行期打补丁跑全量，精确定位到 2 个测试会红） |
| 5. README「结构上不可达」还成不成立？ | **不成立**。垮掉的前提是「`reason is None` 会把它挡在合成之前」，被 `78be0d4`（2026-08-22 18:57:45 +0000）改掉 | 代码直读 + `git log -S` 定位 + `git show` 核对 diff |

---

## 1. body 路径端到端追踪

### 1.1 前置：它真的能以裸类型抵达交付层吗

三段全部是**代码直读**，读的是本仓 `.venv` 里实际装着的版本（`httpcore2 2.12.0`、`httpx2 2.12.0`、`h2 4.4.1`）。

1. **httpcore 让它裸奔。** `httpcore2/_async/http2.py:401-431` 的 `_read_incoming_data`：`try` 只包住 `await self._network_stream.read(...)`，而 `events = self._h2_state.receive_data(data)` 在 `try` **之外**（第 425 行）。这与 `transport.py:31` 注释所述一致。

2. **httpcore 的 h2→`RemoteProtocolError` 转换只覆盖 headers 阶段。** `httpcore2/_async/http2.py:145-167` 的 `except BaseException` 里确实有 `isinstance(exc, h2.exceptions.ProtocolError)` 的转换分支——但那个 `try` 只包住 `_send_request_headers` / `_send_request_body` / `_receive_response`，**body 不在里面**。body 走的是它返回的 `HTTP2ConnectionByteStream`，其 `__aiter__`（`httpcore2/_async/http2.py:537-552`）的 `except BaseException` 只做 `await self.aclose()` 然后 `raise exc` —— **原样重抛，不做任何类型转换**。

3. **httpx 的映射表不认它。** `httpx2/_transports/default.py:71-114` 的 `HTTPCORE_EXC_MAP` 只有 httpcore2 的 14 个类型；`map_httpcore_exceptions` 在 `mapped_exc is None` 时执行裸 `raise`（第 111-112 行）。`AsyncResponseStream.__aiter__`（第 264-265 行）就是用这个上下文管理器包 body 迭代的。

4. **本仓这一侧的三道守卫都不吞它。** `with_client_deadline_at` / `with_deadline_at`（`src/app/streaming/deadline.py`）、`with_idle_timeout`（`src/app/streaming/idle_timeout.py`）只 `except StopAsyncIteration` 与 `except TimeoutError`；`_counted_upstream`（`src/app/server/routes/inference.py:609-632`）不含 `except`。

**对照（这是本节结论的鉴别力所在）**：openai SDK 的 `_base_client.py:1730-1747` 对 `_send_request` 的失败做 `except Exception as err: ... raise APIConnectionError(request=request) from err`。所以**headers 阶段**的同一个 h2 异常会被包成 `openai.APIConnectionError`，`normalize_upstream_error` 认得（`_CONNECTION_ERRORS` 含 `OpenAIConnectionError`）。**body 阶段不在 SDK 的 `try` 里**（`stream=True` 时 `_send_request` 在 headers 到达就返回，body 由本仓自己 `response.aiter_bytes()` 拉），所以只有 body 阶段裸奔。头尾两段的差别就是这一条。

> 附带更正一个我一度形成的错误判断：我先怀疑 `transport.py` 的 h2 识别是「守卫被留在 legacy 链路上」，因而现役链路的 headers 阶段也漏。**查证后不成立**——`CopilotUpstream`（`src/app/upstream/copilot.py:69`）在 `src/` 与 `tests/` 里确实没有任何实例化点，`send_responses_headers` 因此没有活的调用者（这一条是真的，见 §4.1），但现役链路的 headers 阶段由 openai SDK 兜住了，**没有行为缺口**。证据等级：代码直读。

### 1.2 逐个闸门

起点：`src/app/server/routes/inference.py:445-479` 构造的那一串生成器包装，交给 `stream_delivery` → `_deliver`。

| # | 闸门 | 位置 | 裸 `h2.ProtocolError` 的判定 |
|---|---|---|---|
| 0 | `except Exception as error: torn = error` | `stream.py:317-319` | **接得住**。MRO 实测：`h2.exceptions.ProtocolError → h2.exceptions.H2Error → builtins.Exception → BaseException → object`。`H2Error` 直接继承 `Exception`，h2 4.4.1 全部 15 个异常类无一例外 |
| 1 | `isinstance(torn, ClientDeadlineError)` | `stream.py:322` | 不匹配，放行 |
| 2 | `assembler.terminal.seen` | `stream.py:338` | **条件闸门**。上游已发完 terminal 才 `break`；未发完则放行。这一格已有回归测试 `tests/unit/pipeline/delivery/test_stream_delivery.py:1328-1374` |
| 3 | `ours = isinstance(torn, DeliveryError) or torn is from_assembly` | `stream.py:348` | `ours = False`。它不是 `DeliveryError`（那是 `RuntimeError` 子类，`blocks.py:24`），也不是 `assembler.push` 抛的 |
| 4 | `reason = ... replay.eligible(torn) ...` → `if replay is not None and reason is not None:` | `stream.py:349-350` | `reason is None`（`replay_reason` → `normalize_upstream_error` → `None`），**整个 replay 分支被跳过**，不消耗预算、不重放 |
| 5 | `if not ours:` | `stream.py:368` | **确认无条件**。原文见下 |
| 6 | `session.committed_count == 0 and stop_reason not in continuation.stop_reasons` | `stream.py:469` | **条件闸门**。`stop_reason` 此处是默认空串，不在 `{"max_tokens"}` 里；所以只有 `committed_count >= 1` 才放行 |

### 1.3 第 5 道闸门的原文（`src/app/pipeline/delivery/stream.py:368-376`）

```python
        if not ours:
            # Asked whether or not the failure could be *named*, which is the half that used to be missing: `reason is None` sent the stream straight out of this function on a bare `raise`, so a failure the caller's taxonomy has no word for — a naked `h2.ProtocolError` is the one on record — skipped the hand-over entirely and took the client's turn with it. Naming a failure decides whether another *attempt* is worth funding; it says nothing about whether the client can carry the turn on, and only the second question belongs here.
            #
            # An unnamed failure is still not replayed. That is the narrower of the two readings and it is deliberate: a replay spends budget on a guess, while a hand-over spends nothing and leaves the decision with the client. Whether unnamed should also mean retryable is a product question, and it stays in `deferred.md` §20 rather than being answered by this edit.
            handed_over = _hand_over(continuation, session, assembler, framer, error=torn)
            if handed_over is not None:
                for chunk in handed_over:
                    yield chunk
                return
```

确认：`if not ours:` 上没有任何 `reason` 相关的条件。注释自己点名了 `h2.ProtocolError`。证据等级：代码直读。

### 1.4 裁定：**有条件可达**

条件清单（全部满足才走到 `category: "internal"`）：

1. 上游 **未** 发出 terminal 事件（`stream.py:338`）；
2. 客户端 deadline **未** 先于它到期（`stream.py:322`）；
3. `continuation` 已配置——流式路径上 `inference.py:435-437` 是无条件构造的，所以恒真；
4. 入站是 Anthropic Messages 且 `upstream_request_retry.auto_retry_tool_call_full_name` 非空（`hand_over.py:235-239`；默认值非空，`src/app/config/schema.py:157-159`）；
5. `session.committed_count >= 1`（`stream.py:469`）——即缓冲策略已经放行过至少一个完整块。默认 `client_delivery.buffering_policy: "block"`（`src/app/config/schema.py:230`）每块即放，满足；**但 `full` 与 `until-tool-use` 下块会一直被扣住，`committed_count` 停在 0**，此时 `_hand_over` 返回 `None`，走的是 `stream.py:384-396` 的错误帧 + `raise torn`，缓冲里的完整块被丢弃。这与 `inference.py:371-373` 的 `_reopen` 文档串与 `deferred.md` §5 记的是同一道闸门。

**默认配置下条件 3/4/5 恒成立，实际取决于 1 与 2。**

### 1.5 本次实测

探针：`stream_delivery` 端到端，先喂一个完整的 Anthropic text 块（`content_block_start`/`delta`/`stop`），再从上游迭代器抛出真实的 `h2.exceptions.ProtocolError`；`replay.eligible` 与 `continuation.synthesize` 都接生产代码（`replay_reason`、`hand_back_block`）。把发出的 SSE 里 `input_json_delta` 的 `partial_json` 拼回来解析：

```
h2.exceptions.ProtocolError              -> {'num_messages': 1, 'category': 'internal', 'message': 'h2.exceptions.ProtocolError: Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED [request req_probe, attempt 1]'}
httpx2.DecodingError                     -> {'num_messages': 1, 'category': 'internal', 'message': 'httpx2.DecodingError: Error -3 while decompressing data [request req_probe, attempt 1]'}
framing-bug TypeError                    -> {'num_messages': 1, 'category': 'internal', 'message': 'builtins.TypeError: OutboundFramer.block() bug [request req_probe, attempt 1]'}
httpx2.RemoteProtocolError (control)     -> {'num_messages': 1, 'category': 'network', 'message': 'httpx2.RemoteProtocolError: peer closed [request req_probe, attempt 1]'}
```

最后一行是**阴性对照**：同一条探针、同一个位置换成 `httpx2.RemoteProtocolError`（`TransportError` 子类）就出 `network`。所以前三行的 `internal` 是判据本身给出的，不是探针接错线。

同一探针的 `committed_count == 0` 变体（在第一个块闭合前就抛）实测**不发生交接**，客户端收到：

```
event: error
data: {"type":"error","error":{"type":"upstream_error","message":"Invalid input ConnectionInputs.RECV_DATA in state ConnectionState.CLOSED","code":"upstream_stream_failed"}}
```

然后 `ProtocolError` 从生成器抛出。**注意这里的自相矛盾**：同一个异常，SSE 错误帧把它归给 `upstream_error`（`stream.py:385`，`ours=False` 那一侧），而交接块把它归给 `internal`。两条出口对同一个失败给了两个答案——这正是 `hand_over.py:24` 那条注释想消灭的东西，只是它当时消灭的是「`classify_error` vs 重试路径」那一对。

证据等级：**本次实测**（探针脚本 `/tmp/h2probe/probe.py`、`/tmp/h2probe/probe2.py`，为一次性 fixture，未入库）。

---

## 2. `internal` 这个取值在本仓有没有行为后果

**没有任何本仓消费者。唯一读者是 MCP server 与模型。** 证据等级：代码直读，穷举式。

- `rg -n "ErrorCategory" src/` 的全部命中：定义与 `WIRE_TYPES` 表（`src/app/errors.py`）、`hand_over.py` 的 `CATEGORY_FOR_REASON` 与第 259 行、`stream.py` 的三处 `WIRE_TYPES[...]`（333/385/441，那是 **SSE 错误帧的 `type` 字段**，与交接块的 `category` 是两条独立出口）。
- `rg -n '"category"' src/` 只有一处命中：`src/app/pipeline/hand_over.py:273`，即写入交接块 `input` 的那一行。没有任何地方读回来。
- 日志 / 指标 / TUI：`rg -n "category" src/app/observability/ src/app/server/` 只命中 `http_errors.py:79` 的一句散文注释。交接在观测面上留下的痕迹只有 `_StreamAccounting.handed_over: bool`（`inference.py:528-529`）与 `trace.status_override = "retry"`（缓冲路径，`inference.py:505`），**都不带 category**。
- History：**本仓目前没有 history 模块**（`ls src/app/` 无 `history/`），所以不存在持久化读者。
- 测试：`rg -n '"category"' tests/` 只有 4 条断言，全在 `tests/int/test_pipeline_app.py`（1084、3227、3301、3428），取值分别是 `"max_tokens"` ×2、`"network"` ×2。`rg -ni 'internal' tests/ -g '!*.json'` 的命中**全部**是 URL 路径（`/copilot_internal/v2/token`）、主机名（`proxy.internal`）与散文，**没有一条测试断言 `category == "internal"` 或 `internal_error` 线格式**。

推论（证据等级：由上述直读得出，**推断但穷举过**）：改动这个取值在本仓内不会打红任何测试，也不会改变任何日志/指标/TUI 输出；它唯一的行为后果在 MCP server 那一侧——`~/.claude/my/ghc-api-proxy-helper/src/auto_retry/config.py` 的 `DEFAULT_REPLIES_BY_CATEGORY` 决定回什么话。那一侧的现状见 `deferred.md` §23（本次未复核，沿用该条记录）。

---

## 3. 同类异常清单

判据：能到达 `hand_back_block` 且 `normalize_upstream_error` 判 `None`。等价于「能被 `stream.py:317` 接住、`ours == False`、且过了 §1.4 的 5 个条件」。

### 3.1 错报（上游/传输的真实故障，被报成 `internal`）

| 类型 | 来源 | 机制 / 位置 | 证据等级 |
|---|---|---|---|
| `h2.exceptions.H2Error` **全族**（`ProtocolError`、`FrameTooLargeError`、`FlowControlError`、`StreamClosedError`、`NoSuchStreamError`、`DenialOfServiceError`、`RFC1122Error` …，h2 4.4.1 共 15 个类） | hyper-h2 的状态机 | `httpcore2/_async/http2.py:425` 在 `try` 外；`HTTP2ConnectionByteStream.__aiter__` 原样重抛（537-552）；`httpx2/_transports/default.py:111-112` 裸 `raise`。`errors.py:34-36` 的三个元组无一含 `H2Error` | 代码直读 + 本次实测（`ProtocolError` 一例） |
| `httpx2.DecodingError` | 上游把 body 压坏了（gzip/br/zstd/deflate 解压失败） | `httpx2/_decoders.py` 共 8 处 `raise DecodingError`；`Response.aiter_bytes`（`httpx2/_models.py:979-997`）在迭代里调 `decoder.decode(...)`。**`DecodingError` 继承 `RequestError` 而非 `TransportError`**（实测继承树），所以 `_CONNECTION_ERRORS` 里的 `httpx2.TransportError` 抓不到它 | 代码直读 + 本次实测（构造 `DecodingError` 走完交付链得 `internal`）。**未观测到真实发生**——这一条是「机制成立」，不是「见过」 |

`h2` 那一族的严重性在于**它是本项目已经付过代价的那个故障**：GOAWAY 与其后的帧落在同一次 socket 读里，就从 httpcore 的缺口里裸奔上来（`.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-poc.md`）。headers 阶段本仓两处专门认它（`transport.py:32`、`client.py:190`），body 阶段一处也没有。

### 3.2 正确（确实是我们自己的 bug，`internal` 是对的）

| 类型 | 来源 | 机制 / 位置 | 证据等级 |
|---|---|---|---|
| framing 层抛出的任何 `Exception`（`TypeError`、`KeyError`、`AttributeError` …） | `framer.preamble()` / `framer.block()` / `framer.keepalive()` | `stream.py:279` 的注释自陈：`from_assembly` 只覆盖 `assembler.push`。framer 的三个调用点（301-309、316）都在同一个 `try` 里，抛出后 `ours=False` | 代码直读 + 本次实测（`TypeError` 一例） |
| `MemoryError`、`RecursionError` 等运行期自伤 | 任意位置 | 都是 `Exception` 子类 | 推断，未验证 |

**注意这一类有一处不一致**：framing bug 的交接块 `category` 是 `internal`（对的），但如果 `committed_count == 0` 走错误帧那条路，`stream.py:385` 会因为 `ours=False` 把它标成 `upstream_error`（错的，甩锅上游）。方向与 h2 的错报正相反。

### 3.3 查过但**不**属于这一类的（排除项，防止后来者重复查）

| 候选 | 为什么不是 |
|---|---|
| `assembler.push` 抛的任何异常 | `from_assembly` 命中 → `ours=True` → `if not ours:` 不进 → **根本不走交接**，直接 `framer.error(INTERNAL)` + `raise` |
| `DeliveryError` / `BufferCapExceeded` / `ResponseAlreadyStarted` | 同上，`ours=True` |
| `ClientDeadlineError` | `stream.py:322` 提前拦下并 `return` |
| `StreamDeadlineError` / `StreamIdleTimeoutError` | `replay_reason` 第 50-51 行显式给 `RetryReason.NETWORK` → `category: network` |
| `httpx2.RemoteProtocolError` / `ReadError` / `ConnectTimeout` … | 都是 `TransportError` 子类 → `_CONNECTION_ERRORS` 认得 → `network`。本次实测有对照 |
| SSE 解析失败 | `sse_source.py` 不抛：`decode("utf-8", errors="replace")`（第 39 行）、`except orjson.JSONDecodeError: return {}`（第 28-29 行） |
| `anyio.BrokenResourceError` / `ConnectionResetError` / `ssl.SSLError` | httpcore 的 anyio backend 用 `map_exceptions` 包住 socket 读，出来是 `httpcore2.ReadError` → `httpx2.ReadError` → `TransportError` |
| h11（HTTP/1.1）的协议错误 | httpcore 的 `http11.py` 有映射，出来是 `RemoteProtocolError`。README 第 106 行已记录实测形态 |
| `asyncio.CancelledError` / `GeneratorExit` | 非 `Exception`，`stream.py:317` 的 `except Exception` 按设计放过（第 318 行注释即为此写） |
| `PipelineError` 家族（`normalize_upstream_error` 第 95-96 行对它们也返回 `None`） | body 迭代链上没有生产者：三道守卫只抛 `TimeoutError` 子类，`_counted_upstream` 不抛，httpx/SDK 不产 `PipelineError`。**推断，未验证**——没有找到反例，但也没有做穷举证明 |

---

## 4. 修法与影响面

### 4.0 先厘清一个容易搞错的耦合

`replay_reason` 有两个生产消费者，且**都在流式路径上同时生效**：

- `inference.py:443` `ReplaySupport(eligible=replay_reason, ...)` —— 决定**要不要重放**；
- `hand_over.py:52`（被 `hand_back_block:257` 调用）—— 决定**交接块的 `category`**。

所以「只改分类不改可重试性」这件事，**在 `replay_reason` 这一层做不到**。想解耦必须往更下游走（见方案 c）。

`normalize_upstream_error` 本身的生产调用点只有两个：`client.py:116`（`_in_pipeline_terms`，覆盖 `send_chat_completions` / `send_anthropic_messages` / `send_anthropic_count_tokens` / `send_responses` / `send_embeddings`）与 `hand_over.py:52`。证据等级：代码直读（`rg -n "normalize_upstream_error" src/`）。

### 4.1 方案 (a)：把 h2 异常加进 `_CONNECTION_ERRORS`

改动：`src/app/model_provider/ghc_client/errors.py:36`，加 `h2.exceptions.H2Error`（族级）或 `ProtocolError`（次族级）。一个文件、一行。

**连带行为变化：**

1. **交接 `category`：`internal` → `network`。** 这是目标。
2. **变成可重放。** `ReplaySupport.eligible` 返回 `NETWORK` → 走 `decide_stream_ending`。因为 `terminal_seen` 已在上游被 `stream.py:338` 处理掉，实际落 `downstream_opened` 分支（`retry.py:138-143`）：客户端还没见到字节就从 `network` 预算里买一次透明重放；已经见到内容就 `ABANDON`。**这与 `httpx2.RemoteProtocolError`（同一个 GOAWAY 走 headers 阶段的形态）今天的待遇完全一致**，所以我认为这是对齐而不是扩权。
3. **driver 的 headers 阶段：无变化。** 因为 openai SDK 已经把 body-外的 h2 异常包成了 `APIConnectionError`（§1.1 第 5 段），`normalize_upstream_error` 早就认得。加进去只是让「万一没被包」的那条理论路径也认得。
4. **与 `transport.py` 的重复：技术上无冲突，但值得单独记一笔。** `is_responses_headers_pending_transport_error` 唯一被 `client.py:192` 调用，`client.py:177` 的 `send_responses_headers` 唯一被 `src/app/upstream/copilot.py:131` 调用，而 **`CopilotUpstream` 类在 `src/` 与 `tests/` 里没有任何实例化点**（`rg -n "CopilotUpstream" src/ tests/` 只命中类定义那一行）。现役 provider 走 `src/app/model_provider/github_copilot.py:167-172` 的 `send_responses`。所以 `transport.py` 那份 h2 识别**目前挂在一条没有活调用者的链上**，不会与 (a) 打架。证据等级：代码直读。（这不属于本次调查范围，但属于 `no-silently-cut-but-defer` 该记的东西：那份守卫要么随 legacy 链一起处置，要么在现役链上重新接线。**建议登记到 `deferred.md`，不建议本次顺手动它。**）

**族级 vs 次族级**：`transport.py:32` 选的是 `ProtocolError`，理由写在 `tests/unit/model_provider/ghc_client/test_pre_header_retry.py:80`——「`ProtocolError` 就是那一族，族里每一个都是在 headers 之前抵达的」。h2 4.4.1 里只有 `H2Error` 和 `RFC1122Error` 在 `ProtocolError` 之外（实测继承树）。两者差别极小；**我倾向 `H2Error`**，因为 body 路径上不存在「headers 之前」这个限定，没有理由把 `RFC1122Error` 排除在外。

**会红的测试：2 个，本次实测。**

用一个只在运行期打补丁的 pytest 插件（`m._CONNECTION_ERRORS = (*m._CONNECTION_ERRORS, H2Error)`，仓库文件未改）跑全量 `tests`，扣掉同伴 in-flight 改动造成的失败后，归因到本补丁的只有：

```
FAILED tests/unit/pipeline/delivery/test_stream_delivery.py::test_a_finished_turn_survives_a_failure_nothing_recognises[block]
FAILED tests/unit/pipeline/delivery/test_stream_delivery.py::test_a_finished_turn_survives_a_failure_nothing_recognises[full]
```

对照跑（不打补丁，同样两个测试点）：`3 passed in 2.22s`。

失败点是**前提断言**，不是行为断言：

```
>       assert eligible(torn) is None, "the premise: production cannot name this failure"
E       AssertionError: the premise: production cannot name this failure
E       assert <RetryReason.NETWORK: 'network'> is None
tests/unit/pipeline/delivery/test_stream_delivery.py:1346
```

而该测试自己的 docstring（第 1328 行）就写明了这一天：「would keep passing if `normalize_upstream_error` ever learned to name this one — at which point the case being guarded no longer exists」。**所以这两条红不是回归，是那个测试按设计自曝其前提已失效**；它守的那个洞（`terminal.seen` 先于分类被问）仍然需要守，但得换一个「production 叫不出名字」的异常来当载具，或者把断言反过来写。

### 4.2 方案 (b)：只在 `replay_reason` 里特判

改动：`src/app/pipeline/hand_over.py:48-53` 加一个 `if isinstance(error, H2Error): return RetryReason.NETWORK`（`H2Error` 已经 import 在第 13 行）。一个文件、两行。

**影响面并不比 (a) 小，只是分布不同：**

- 交接 `category` 与可重放性，**两个都变**，且变法与 (a) 完全相同（因为 §4.0 的耦合）。
- `client.py:116` 那条路不变——headers 阶段仍由 SDK 兜。
- 会红的测试：**0 个**。`test_a_finished_turn_survives_a_failure_nothing_recognises` 用的是它**自己定义的** `eligible`（第 1341-1343 行，直接建在 `normalize_upstream_error` 上），而不是 `replay_reason`，所以 (b) 打不到它。**这本身是个值得记的缺陷**：那个测试的 stand-in `eligible` 与 `inference.py:443` 的生产接线不是同一个函数，于是 (b) 会在生产里把行为改掉而测试全绿。

**分类学分裂的风险：是的，(b) 会造成。** `hand_over.py:20`（应为第 24 行）那条注释要消灭的正是「两个分类法对一个失败给两个答案」。(b) 之后：`replay_reason` 说 h2 是 `network`，`normalize_upstream_error` 说它不是上游失败——两者对同一个异常给出相反判断，而 `replay_reason` 的文档串第 44 行明写「`normalize_upstream_error` is the same mapping the driver's own retries are decided by」，(b) 会让这句话变成假的。

**结论：(b) 的「影响面更小」是错觉。** 它改的行为和 (a) 一样多，只是测试打不到它，并且额外制造了一处文档与代码不符。**不推荐。**

### 4.3 方案 (c)：只改 `hand_back_block` 的分类，不动可重放性

改动：`src/app/pipeline/hand_over.py:253-259` 那个三元表达式，在 `reason is None` 时按异常类型再兜一层（例如 h2 → `NETWORK`）。

- 唯一改变的是交接块的 `category`；重放决策一个字节不变（`ReplaySupport.eligible` 仍看 `replay_reason`）。
- 会红的测试：**0 个**（同 §2 的穷举，没有测试断言过 `internal`）。**推断，未实测**——我没有为 (c) 单独跑补丁验证。
- 代价：`hand_back_block` 里出现第二张分类表，而第 250 行的注释正是在说「所以它读的是同一张表」。等于把 (b) 的分裂搬进了同一个函数里。

**我的倾向：(a)。** 理由有三：其一，它把 body 阶段的 h2 与 headers 阶段的 h2 拉齐，而两者本来就是同一个协议故障在两个时刻的形态；其二，它是唯一一个**不新增分类表**的改法，`hand_over.py:24`/`44` 的两条注释在 (a) 之后仍然是真话；其三，它唯一的红是一条自我声明过会过期的前提断言，改起来是明账。

**(a) 的已知代价**要说清楚：它把「上游协议层故障」变成会花网络重试预算的。这在 `downstream_opened` 之前只买一次透明重放，与今天的 `RemoteProtocolError` 同价，我判断**够强、可据此行动**；但「未命名的失败该不该可重试」这个更大的产品问题仍留在 `deferred.md` §20，(a) 并不回答它，只是把 h2 从「未命名」挪进「已命名」。

---

## 5. 裁定 README 的「结构上不可达」

### 5.1 论证还成不成立：**不成立**

README 第 70 行现文：

> `network` / `upstream` / `auth` **三者之一**，外加结构上今天不可达的 `internal`

原论证的两个前提：
1. `RetryReason` 三个成员全在 `CATEGORY_FOR_REASON` 里 —— **仍然成立**（`retry.py:23-26` 三个成员，`hand_over.py:25-29` 三个键，本次核对无缺项）。
2. 带 error 走到合成之前 `reason` 必非 `None` —— **已垮**。

前提 2 垮在 `stream.py:349-368`：`reason` 现在可以是 `None` 而合成照走。`hand_back_block:257-259` 于是拿到 `reason=None`，落 `ErrorCategory.INTERNAL.value`。§1.5 的实测直接印出了这个值。

### 5.2 是哪个提交改掉的

`git log --all --oneline -S 'if not ours:' -- src/app/pipeline/delivery/stream.py` 给出两个提交：`78be0d4`（在 `main` 上）与 `0f1904f`（在 `wip/260822-clean-eof-refinement` 上，即压缩前的来源）。

```
78be0d4fd389be01688cb3edc906184d312479b3 2026-08-22 18:57:45 +0000
feat: close a clean EOF at a block boundary instead of calling it truncated
```

`git show 78be0d4 -- src/app/pipeline/delivery/stream.py` 的关键 hunk（`-` 是改前，`+` 是改后）：

```
-        reason = replay.eligible(torn) if replay is not None else None
-        if replay is None or reason is None:
-            raise torn
...
+        ours = isinstance(torn, DeliveryError) or torn is from_assembly
+        reason = None if ours else (replay.eligible(torn) if replay is not None else None)
+        if replay is not None and reason is not None:
...
+        if not ours:
```

改前那三行就是前提 2 的全部依据：`reason is None` → 裸 `raise torn`，交接根本不发生。改后 `if not ours:` 与 `reason` 脱钩。

`git branch --contains 78be0d4` 确认它在 `main` 上；`git show HEAD:src/app/pipeline/delivery/stream.py | rg "if not ours:"` 确认当前 HEAD（`d6edd1a`）仍是这个形状（第 348、368 行）。证据等级：代码直读 + `git` 核对。

### 5.3 README 那句话是什么时候写的

`.dev` 仓 `git log -S '结构上今天不可达' -- docs/upstream/retry-and-continuation/README.md` 只命中一个提交：

```
a8862e6911d07fdcbf93e2104188d833d17da8e6 2026-08-23 06:26:41 +0000
docs(retry-and-continuation): record the new `message` contract and two things it uncovered
```

再往前用 `-S 'internal'` 查同一文件，还有 `4642eb4`（`docs(upstream/retry-and-continuation): file the emitted MCP contract, and answer review`）。

**所以这不是「代码后来改了、文档没跟上」的常见形状。** `78be0d4` 是 2026-08-22 18:57 落地的，`a8862e6` 是次日 06:26 写的——**这句「不可达」是在洞被补上之后写下的**，它引的是一份自己已经过期的心智模型。`deferred.md` §22 已经把矛盾登记下来并标注「未实测」；本报告提供的就是那份实测。

### 5.4 建议的改法（**不在本次执行**）

README 第 70 行的 `category` 那一格应改为四值全部可达，并说明 `internal` 的两种来源（上游 h2 协议故障的**错报**、framing bug 的**正确报告**）。改动本身需要用户或主会话裁决要不要连带修代码（§4）——如果采纳 (a)，README 就该写「h2 归 `network`，`internal` 只剩本仓自身 bug」；如果不修代码，README 就该写「`internal` 可达，且今天它同时覆盖上游协议故障与本仓 bug 两种不同的事」。两种写法对 MCP server 那一侧的含义完全不同，**不应由本报告单方面决定**。

---

## 6. 附带发现（不属于被问的四个问题，登记备查）

1. **同一失败的两条出口给两个答案。** `committed_count >= 1` 走交接 → `category: "internal"`；`committed_count == 0` 走错误帧 → `type: "upstream_error"`（`stream.py:385`，`ours=False` 那一侧）。同一个 h2 异常，两种归因，取决于缓冲策略放行了几个块。证据等级：本次实测（§1.5 两个变体）。
2. **framing bug 的归因方向相反且也是错的。** `framer.block(...)` 抛异常时 `ours=False`，错误帧会把它标成 `upstream_error` —— 把本仓的 bug 甩给上游。`stream.py:279` 的注释承认了这个已知限制。证据等级：代码直读 + 本次实测（交接那一侧）。
3. **`transport.py` 的 h2 识别挂在没有活调用者的链上。** 见 §4.1 第 4 点。**没有造成行为缺口**（openai SDK 兜住了 headers 阶段），但它是一份读起来像在保护现役路径、实际不在现役路径上的守卫。建议登记 `deferred.md`。证据等级：代码直读。
4. **`test_a_finished_turn_survives_a_failure_nothing_recognises` 的 `eligible` 是 stand-in，不是生产接线。** 它在测试里现建（第 1341-1343 行），而生产传的是 `replay_reason`（`inference.py:443`）。今天两者对 h2 同答 `None` 所以看不出差别，改动一旦落在 `replay_reason` 上（方案 b/c）这个测试就失去鉴别力。证据等级：代码直读。
5. **`classify_error`（`src/app/errors.py:57-62`）在 `src/` 里已无生产调用者**，只剩 `tests/unit/models/test_models_common.py` 在测它。`hand_over.py:24` 的注释仍在解释「为什么不用它」——注释仍然有效，但读者可能以为它还在某处跑着。证据等级：代码直读（`rg -n "classify_error" src/ tests/`）。

---

## 7. 复现方式

本次所有实测都在一次性 fixture 里完成，未入库、未改仓库文件：

- 端到端交接分类探针：`/tmp/h2probe/probe.py`、`/tmp/h2probe/probe2.py`，跑法 `PYTHONPATH=src uv run python /tmp/h2probe/probe2.py`。
- 方案 (a) 的测试影响面：`/tmp/h2probe/patch_plugin.py`（`pytest_configure` 里给 `_CONNECTION_ERRORS` 追加 `H2Error`），跑法 `PYTHONPATH=/tmp/h2probe uv run pytest tests -q -p patch_plugin`。对照跑去掉 `-p patch_plugin`。
- `/tmp` 不在仓库内，这些文件不需要清理即不会污染仓库；如需重跑请按上面重建。
