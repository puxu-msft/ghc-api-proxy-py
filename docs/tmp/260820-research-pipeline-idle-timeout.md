# 新 pipeline 接入上游 idle timeout：现状调查

调查日期 2026-08-20。调查者为只读角色，未修改 `src/`、`tests/` 下任何文件，未执行任何 git 写操作。工作树 HEAD 为 `1ac5ab2`，工作树有并行会话的未提交改动（`src/app/pipeline/delivery/`、`src/app/server/pipeline_app.py`、`src/app/observability/` 等），本报告读的是**磁盘当前字节**，不是某个 commit 的快照。

证据强度标注沿用 `state-decisiveness`：【足以据此行动】／【仅为倾向，需更多样本】／【仅存档】。

---

## 0. 结论前置

| 问题 | 回答 | 强度 |
|---|---|---|
| 这件事被裁决过吗 | **部分裁决过，且裁决人是用户本人**。`docs/.human-controlled/config.example.yaml` 逐字规定了键名、默认值 0、按模型覆盖的具体度规则、以及「适用于所有流式路径」和「单次尝试上游」的语义边界，还写下了一条**冻结不变量**。但「新链路怎么接、触发后对外发什么」没有任何文档裁决过 | 【足以据此行动】 |
| legacy 触发后客户端看到什么 | **两条腿完全不同**。Anthropic 原生腿：永远 HTTP 200 + 撕断的 body（连首字节前触发也是 200 空 body），History 记 499 `stream interrupted`，**看不出是超时**。Responses 腿：首个 block 提交前触发 → HTTP **502** JSON，code `responses_stream_conversion_error`；提交后触发 → 200 + 带内 Anthropic SSE `error` 事件、无 `message_stop` | 【足以据此行动】，已实测 |
| 新链路等价接入点 | 与 legacy `upstream.aiter_raw()` 等价的那一跳是 `src/app/server/pipeline_app.py:278` 的 `response.aiter_bytes()`。推荐接在 `src/app/pipeline/delivery/stream.py:31 _events_with_ping` 的既有等待循环里（方案 B），次选包在 `aiter_bytes()` 外（方案 A） | 【足以据此行动】 |
| 重叠机制 | `session_liveness_stream` / `keepalive_stream` **零生产调用方**，只有测试在用；新链路完全不经过它们。同一模块里只有 `finish_stream_cleanup` 被生产代码复用 | 【足以据此行动】 |
| 非流式有等价保护吗 | 有，而且是三重的（`client_request_deadline` 3600 → `upstream_request_deadline` 1200 → SDK read 600），`stream_idle` 与它们不冲突 | 【足以据此行动】 |

**本次调查里权重最高的、之前没人记录过的事实**：新链路的 httpx client（`src/app/server/composition.py:75-81`）**没有传 `timeout=`**，于是 openai / anthropic SDK 采用自己的 `DEFAULT_TIMEOUT`，**read = 600 秒**。而 httpx 的 read timeout 在 body 迭代期间是**逐次读的空闲超时**（已实测）。也就是说：**新链路此刻已经有一个 600 秒的上游空闲超时在跑，只是它不可配置、不叫这个名字、报出来的是 `httpx.ReadTimeout`。** 这与用户亲笔写下的「bundled defaults 全部禁用此类终止器」这条冻结不变量直接冲突。详见 §4.3、§6.1。

---

## 1. 这件事是否已被裁决过

### 1.1 用户亲笔文档：`docs/.human-controlled/config.example.yaml`

这是唯一压过一切推导结论的来源。逐字引用（第 279-315 行）：

```yaml
upstream_request_timeouts:
  # 单次尝试上游，从请求发起到开始收到 HTTP 响应头的最大秒数（0 = 不超时）。
  #
  # 用户冻结的不变量是绝不误杀合法长思考：活连接上的静默没有可证明安全的 wall-clock 上界，因此 bundled defaults 全部禁用此类终止器。
  # 运维可显式配置非零值以选择有界等待，但那是对该不变量的主动覆盖。
  #
  # Each upstream attempt: Max seconds from request start to receiving HTTP response headers (0 = no timeout).
  #
  # The frozen invariant is never to false-kill legitimate thinking: silence on a live connection has no provably safe wall-clock bound, so bundled defaults disable these terminators.
  # Operators may explicitly configure nonzero values to choose bounded waiting, which is an intentional override of that invariant.
  #
  response_header: 0

  # 按模型覆盖的 response_header，键规则同 stream_idle_overrides。无内置值。
  # Per-model response_header override, same keying as stream_idle_overrides. No built-in value.
  response_header_overrides: {}

  # 单次尝试上游，SSE 事件之间的最大间隔秒数（0 = 不超时）。适用于所有流式路径。
  # Each upstream attempt: Max seconds between SSE events (0 = no timeout). Applies to all streaming paths.
  stream_idle: 0

  # 按模型覆盖 stream_idle，键为模型名子串（或 glob `*`/`?`）；"*" = 所有模型。
  # Per-model stream_idle override, keyed by model-name substring (or glob `*`/`?`); "*" = all models.
  #
  # 命中项优先于上面的标量 stream_idle；0 = 禁用（无空闲超时）。多键命中时具体度：literal 子串 > glob > "*"（同类再按键长最长胜）。
  # A match wins over the scalar stream_idle above; 0 = disabled (no idle timeout). Key specificity when multiple match: literal substring > glob > "*" (then longest key).
  #
  stream_idle_overrides: {}

  # 单次上游尝试的最大存活秒数（0 = 禁用）。
  # 与另外两个上游守卫互补：response_header 只管首字节前，stream_idle 只管帧间空档，两者都拦不住「一直滴水但永不结束」的尝试。
  #
  # Max seconds ONE upstream attempt can live (0 = disabled).
  # Complements the two phase-scoped guards: response_header covers only the pre-header wait and stream_idle only the gap between frames — neither bounds an attempt that trickles forever.
  #
  upstream_request_deadline: 1200
```

从这段文本**已被裁决**的事项（强度【足以据此行动】）：

1. **键名与归属节**：`upstream_request_timeouts.stream_idle` / `.stream_idle_overrides`。不是旧 `AppSettings` 的 `timeouts.stream_idle`。
2. **默认值 0，即关闭**。理由被明确写成一条**冻结不变量**：「绝不误杀合法长思考；活连接上的静默没有可证明安全的 wall-clock 上界」。
3. **语义边界**：「单次尝试上游」（per attempt，重试后重新计时）、「SSE 事件之间的最大间隔」（帧间空档，不是总时长，也不是首字节前的等待——首字节前是 `response_header` 管的）。
4. **适用范围**：「适用于所有流式路径」。这一句直接回答了「新链路要不要这个超时」的**范围问题**：Anthropic、Chat Completions、Responses 三条流式路径都在内。
5. **覆盖表的匹配与具体度规则**：literal 子串 > glob > `*`，同类取最长键。`src/app/pipeline/timeouts.py:41 resolve_timeout` 已经按这条实现了（`_classify` / `_matches` / 排序键 `(class, len)`）。
6. **三个守卫的分工**：`response_header` 只管首字节前，`stream_idle` 只管帧间空档，`upstream_request_deadline` 管单次尝试总存活。

从这段文本**没有被裁决**的事项（这是接下来实现要面对的真空）：

- **触发后对外发什么**。用户文档只说「超时」，没说客户端应该看到 502、还是带内 SSE `error` 事件、还是撕断连接。
- **接在哪一跳**、以及计时器读的是「字节到达」还是「SSE 事件到达」。用户文本写的是「SSE 事件之间」，这偏向事件级；但没有明文禁止字节级实现。
- **触发后是否重试**。`upstream_request_retry.strategies` 里有 `network` / `streamReplay` 两栏，但没有任何文档说 `StreamIdleTimeoutError` 归哪一类。**这是一个 `no-silently-cut-but-defer` 意义上的待裁决点，建议单独提请用户裁决，不要在实现里默默定一个。**

### 1.2 冻结不变量的一处措辞歧义（需要用户确认）

「bundled defaults 全部禁用此类终止器」这句挂在 `response_header` 的注释块里，但用了「全部」和复数 `these terminators`。同一节里 `upstream_request_deadline` 的默认值是 **1200**，不是 0。所以「此类」应当读作「按阶段划分的静默终止器」（`response_header` 与 `stream_idle` 两项），而不包含总存活上限。

强度【仅为倾向，需更多样本】。这条读法与 `upstream_request_deadline` 注释里「与另外两个上游守卫互补」的分组一致，但归根到底是我在读用户的措辞，**不是用户裁决过的**。如果实现会依赖这条读法（例如「idle 关掉了但 deadline 还在，所以没问题」这种论证），应当先请用户确认。

### 1.3 推导类文档：与用户文档冲突，以用户文档为准

`docs/2604-rewrite/streaming.md:200-260` 有一整节 idle timeout 设计，包含 `with_idle_timeout` 的伪代码、`resolve_stream_idle`、per-model 覆盖示例。它规定：

- `timeouts.stream_idle` 默认 **300**（`streaming.md:235`）
- 覆盖表匹配规则是**朴素的「首个命中的子串」**（`streaming.md:252-257`，与现行 `resolve_timeout` 的具体度排序不同）
- 「适用于所有流式路径（Anthropic、Chat Completions、Responses）」（`streaming.md:238`）
- 「解析结果在**流开始时**读取一次，注入 `with_idle_timeout()`；进行中的流保持其解析值不受热重载影响」（`streaming.md:259`）

**判定**：前两条已被 `docs/.human-controlled/config.example.yaml` 推翻（默认值 300→0，匹配规则朴素→具体度排序），`streaming.md` 是旧 `AppSettings` 键名空间下的推导稿，不再是权威。第三条与用户文档一致。第四条（流起点读一次、热重载不影响进行中的流）**用户文档没有涉及，只在推导稿里存在**，可以当作实现参考，但它不是裁决。强度【足以据此行动】（冲突判定部分），【仅存档】（第四条的效力）。

### 1.4 其他文档中的相关表述

- `docs/2604-rewrite/request-pipeline.md:54`：「Streaming event transform 不属于首版通用 Hook API；idle timeout、keepalive、delayed commit 与 buffered retry 保持 transport 基础设施。」——**裁决了归属层**：idle timeout 属于传输基础设施，不是 hook。这与「接在 delivery 层」并不矛盾（delivery 就是传输层），但它明确排除了「做成一个可订阅的 hook」这条路。强度【足以据此行动】。
- `docs/agents/anthropic-responses-bridge/spec.md:467`：把 `idle time` 列进「必须存在并可观测的限制类别」清单。这是一条**存在性要求**，不含数值和行为。强度【足以据此行动】（存在性），但它不能推出任何具体默认值。
- `docs/agents/anthropic-responses-bridge/architecture.md:50`：只是描述 legacy 现状（「当前流式返回仍是 `with_idle_timeout()` 后的原始 upstream bytes passthrough」），并要求「替换 raw-byte downstream 接线」。没有说替换后 idle timeout 怎么办。
- `docs/tmp/260820-server-timeout-forensics.md:87`：已经查明「本次运行中，上游空闲超时机制没有被接线」。本报告与它一致，并在 §4.3 补上了它没查到的那一层。
- `docs/tmp/260820-downstream-keepalive-defect.md:110`：已记录 `keepalive.py` 两个生成器无生产接线，形态归入项目记忆「守卫被留在了 legacy 链路上」。本报告 §4 复核一致。
- `docs/.human-controlled-candidates/config-schema-gap.md:65`：「上游超时默认值 → `response_header` / `stream_idle` 均为 0，新增 `upstream_request_deadline: 1200`；旧默认仍是 300」。**注意这是 candidates 目录，不是 `.human-controlled/`**，属于待用户签收的稿件，不能当裁决用；但它与用户亲笔文档一致，可作交叉印证。

**Q1 总答**：**是**——范围、键名、默认值、语义边界、覆盖规则已被用户亲笔裁决；**否**——接入点、触发后的对外行为、以及是否重试，一律没有裁决。

---

## 2. legacy 触发后，客户端实际看到什么

### 2.1 抛出点与传播链

`src/app/routes/anthropic.py:216-266`：

```
upstream.aiter_raw()                                    # httpx 原始字节
  └─ with_idle_timeout(..., timeout_seconds=idle)       # anthropic.py:221；idle_timeout.py:28-38 抛 StreamIdleTimeoutError
       └─ [仅 Responses 腿] render_responses_as_anthropic_sse(...)   # anthropic.py:229
            └─ _history_stream(...)                     # anthropic.py:237
                 └─ passthrough_bytes(..., cleanup=upstream.aclose)  # anthropic.py:236
                      └─ create_sse_response(...)  或  create_delayed_sse_response(...)
```

关键的类型事实：`StreamIdleTimeoutError(TimeoutError)`，而 `TimeoutError.__mro__ == (TimeoutError, OSError, Exception, BaseException, object)`（实测输出）。**它既是 `Exception` 也是 `OSError`**，这一点决定了下面两条腿的分岔。

全仓没有任何地方 `except StreamIdleTimeoutError`（`rg` 全仓，只有 `idle_timeout.py` 定义处、`keepalive.py:44` 抛出处、以及 tests）。legacy app 也没有对应的 exception handler（`src/app/server/app_factory.py:165` 只注册了 `ApprovalRejectedError`）。

### 2.2 Anthropic 原生腿（`responses_leg = False`）

没有 `render_responses_as_anthropic_sse` 这一层，所以 `StreamIdleTimeoutError` 一路裸奔到 `create_sse_response` 返回的普通 Starlette `StreamingResponse`。Starlette 的 `StreamingResponse.stream_response` **先发 `http.response.start` 再迭代 body**，因此：

- **流已开始与未开始，客户端看到的没有区别：都是 HTTP 200 + `text/event-stream`**，区别只在 body 里已经落了多少字节。
- body 以「连接被撕断」结束，客户端侧表现为 `httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`。
- 没有任何终止事件（无 `message_delta`、无 `message_stop`、无带内 `error` 事件）。

**实测**（`/tmp/idle-research/probe_legacy_idle_visible.py`，真 uvicorn + 真 httpx 客户端）：

```
=== /plain-before      # 首字节前抛
  status=200 content-type='text/event-stream; charset=utf-8'
  body read raised httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)
  body=b''
=== /plain-after       # 已发一个事件后抛
  status=200 ...
  body read raised httpx.RemoteProtocolError: ...
  body=b'event: message_start\ndata: {}\n\n'
```

**History 与日志**：`_history_stream`（`anthropic.py:35-126`）的 `except ApiError` **抓不到** `StreamIdleTimeoutError`，于是走 `finally`：`completed=False`、`stream_error is None` → 在 `anthropic.py:79-88` **合成**一个 `ApiError("stream interrupted", category=NETWORK, status_code=499, code=None)`，`context.fail(...)`，再 `observe_stream_finalized(completed=False)` 与 `history.finalized(...)`。

**即：在这条腿上，上游空闲超时在 History 与 hook 里记成 499 `stream interrupted`，与「客户端中途走了」「上游 RST」完全同形，读不出是超时。** 强度【足以据此行动】（代码路径确定，且 `stream_error` 为 None 是唯一可能——`responses_state` 在这条腿是 `None`）。

### 2.3 Responses 腿（`responses_leg = True`）

`render_responses_as_anthropic_sse` 在 `src/app/delivery/responses_anthropic_stream.py:294` 有 `except Exception as error:`，`StreamIdleTimeoutError` 是 `Exception`，**会被抓住**并经 `_normalize_stream_error`（`:381-396`）落到最后一条兜底分支，变成：

```python
_upstream_error(str(error) or "Responses stream conversion failed", code="responses_stream_conversion_error")
# => ApiError(message, category=UPSTREAM, status_code=502, code="responses_stream_conversion_error")
```

`message` 就是 `with_idle_timeout` 写的那句 `No stream item received for {N:g}s`（`idle_timeout.py:35-37`）。然后按**是否已提交 `message_start`** 分岔（`responses_anthropic_stream.py:297-310`）：

**（a）`frontier.message_start_accepted` 为真——已经有字节交付给客户端**：
调用 `session.render_error(...)` 生成一个带内 Anthropic SSE `error` 事件，drain 出去，然后 `return`（**不抛**）。客户端看到 HTTP 200 + 已有内容 + 一个 `event: error`，**没有 `message_stop`**，流正常结束（不是撕断）。

**（b）尚未提交 `message_start`**：`raise api_error`。这个 `ApiError` 冒泡到 `DelayedStartStreamingResponse.stream_response` 的 `except ApiError`（`src/app/streaming/sse.py:120-139`），那里**尚未发过 `http.response.start`**，于是发出：

```
HTTP 502, content-type: application/json
{"type": "error", "error": {"type": <wire_type>, "message": "No stream item received for 300s", "code": "responses_stream_conversion_error"}}
```

**所以「流是否已开始」在 Responses 腿上确实产生不同行为，而且差别很大：502 JSON vs 200 + 带内 error 事件。** 强度【足以据此行动】（三处代码位置确定：`:294`、`:297-310`、`sse.py:120-139`）。

**History**：分支 (a) 下生成器正常返回，`_history_stream` 的 `finally` 里 `responses_state.error is not None` → `completed=False`、`stream_error = responses_state.error`（那个 502 ApiError），`history.finalized` 的 `response["error"]` 带上 `code="responses_stream_conversion_error"`。分支 (b) 下 `except ApiError` 命中，同样记这个 502。**这条腿上超时是可辨认的**（code 字段有值），代价是被归类成 `conversion_error` 而不是 timeout。

### 2.4 一处必须点明的探针局限

我的探针 `/delayed-before` 一栏得到的是 **HTTP 500 `Internal Server Error`**，而不是上面说的 502。原因是探针直接把 `StreamIdleTimeoutError` 丢进 `create_delayed_sse_response`，绕开了真实链路里的 `render_responses_as_anthropic_sse`。裸 `StreamIdleTimeoutError` 不是 `ApiError`，走不进 `sse.py:120` 那个分支；更妙的是它**是 `OSError`**，于是被 `sse.py:77-78` 的 `except OSError: raise ClientDisconnect() from error` 抓住，**改标成了客户端断连**，最终由 uvicorn 兜底成 500。

这条留作**风险登记**（强度【足以据此行动】，有 traceback 实证）：`src/app/streaming/sse.py:77` 那个 `except OSError` 会把任何 `TimeoutError` 家族的异常改写成 `ClientDisconnect`。**新链路若引入 `StreamIdleTimeoutError` 并让它经过任何形如 `except OSError` 的层，同样会被错标成「客户端走了」。** 新链路当前的 `_AccountedStreamingResponse`（`pipeline_app.py:359-388`）没有这种 `except OSError`，但 `_StreamAccounting._ending()`（`pipeline_app.py:343-356`）区分 `fail` / `gone` 的逻辑，恰恰是这一族错误最容易被读反的地方。

---

## 3. 新链路上等价的接入点在哪

### 3.1 逐跳链路（文件:行号）

流式请求，从上游 httpx 响应到客户端：

| # | 位置 | 做什么 | 与超时的关系 |
|---|---|---|---|
| 1 | `src/app/server/pipeline_app.py:231` | `await handle_bounded(chain, context, _routed)` | 进入 |
| 2 | `src/app/server/handler.py:208-215` | `asyncio.timeout(client_request_deadline=3600)` 包住 `handle()` | **只包到拿到响应对象为止**，不约束 body 交付 |
| 3 | `src/app/server/handler.py:99-113` | 算 `attempt_deadline`，构造 driver，`await driver.run(context)` | 见 §5.2 的错配 |
| 4 | `src/app/pipeline/direct_driver/base.py:136 → 216-241` | `asyncio.timeout(self._attempt_deadline)` 包住 `provider.send(...)` | 流式下 `send` 拿到响应头就返回，**所以这 1200s 在流式路径上只是首字节前的守卫**，不是它 docstring 说的「whole attempt」 |
| 5 | `src/app/ghc_client/client.py:67-81` | `AsyncOpenAI.post(..., stream=True)` / `AsyncAnthropic.post(...)` | SDK 的 read timeout 在这里被绑到请求上，**600s**，见 §4.3 |
| 6 | `src/app/server/pipeline_app.py:278` | **`response.aiter_bytes()`** | ← **与 legacy `upstream.aiter_raw()` 等价的那一跳** |
| 7 | `src/app/server/pipeline_app.py:278 → 391-399` | `_counted_upstream(...)`：逐 chunk 计数并原样转发 | 字节级，可作接入点 |
| 8 | `src/app/server/pipeline_app.py:279 → delivery/stream.py:102` | `stream_delivery(chunks, assembler, ...)` | |
| 9 | `src/app/pipeline/delivery/stream.py:125-132` | `aclosing(_events_with_ping(chunks, sse_ping_interval, response_headers_deadline=..., response_started=...))` | |
| 10 | `src/app/pipeline/delivery/stream.py:46` | `read_events(chunks).__aiter__()`（`delivery/sse_source.py:65`） | 字节 → `SseEvent` |
| 11 | `src/app/pipeline/delivery/stream.py:51,70` | `task = ensure_future(anext(events))`；`await asyncio.wait({task}, timeout=...)`，timeout 取 `ping_deadline` 与 `response_headers_deadline` 的最近者 | ← **事件级等待循环，已有 deadline 机制** |
| 12 | `src/app/pipeline/delivery/stream.py:149-160` | `assembler.push(event)` → `_commit(...)` → yield SSE 帧 | |
| 13 | `src/app/server/pipeline_app.py:277 → 402-421` | `_tracked_delivery(...)`：`except Exception → accounting.failure`；`finally → accounting.finish()` | 异常在这里被记账 |
| 14 | `src/app/server/pipeline_app.py:359-388` | `_AccountedStreamingResponse`（Starlette `StreamingResponse` 子类，未覆盖 `stream_response`） | **先发响应头再迭代 body** |

由 #14 直接得到一条对外行为事实（强度【足以据此行动】）：**新链路上不存在 legacy Responses 腿那种「首字节前变成 HTTP 502」的可能。** Starlette 在拉第一个 chunk 之前就把 `http.response.start` 发出去了，所以无论 idle timeout 何时触发，客户端拿到的状态码都是上游那个（正常是 200）。想给客户端一个可辨认的失败，只能走带内 SSE `error` 事件——而那正是 `stream.py:173-177` 已经登记为 KNOWN SPEC VIOLATION、归属 STR-04 切片的那块缺口。**两件事耦合，建议一并考虑。**

### 3.2 候选接入点与取舍

**方案 A：包在 `response.aiter_bytes()` 外（`pipeline_app.py:278`）**

```
stream_delivery(with_idle_timeout(_counted_upstream(response.aiter_bytes(), ...), timeout_seconds=idle), ...)
```

- 优点：与 legacy 位置严格等价，改动最小（一行 + import）；`with_idle_timeout` 和 `resolve_timeout` 都是现成的；不动 `delivery/stream.py`（并行会话正在改那个文件）。
- 缺点一：**计的是字节间隔，不是「SSE 事件之间」**。用户文档写的是「SSE 事件之间的最大间隔秒数」。若上游发 SSE 注释帧（`: ping`）或把一个事件拆成多个 TCP chunk，字节级计时器会被重置而事件级不会 —— 二者不等价，字节级更宽松。
- 缺点二：`with_idle_timeout` 用 `anyio.fail_after`，而这条链上 `anext` 是由 `_events_with_ping` 里 `asyncio.ensure_future` 创建的**每次一个新任务**来驱动的。scope 的进入与退出都发生在同一次 `asend` 内，理论上安全，但这是 anyio cancel scope 在 asyncio backend 上最容易出问题的用法形态，需要一个针对性的测试证明它在「pull 任务被取消」时不会留下悬空 scope。强度【仅为倾向，需更多样本】——我没有实测这一条。
- 缺点三：`resolve_stream_idle`（`idle_timeout.py:12-16`）吃的是旧 `AppSettings.TimeoutConfig`，且用的是朴素首命中匹配，**不满足用户裁决的具体度规则**。新链路必须改用 `src/app/pipeline/timeouts.py:41 resolve_timeout(model, cfg.stream_idle, cfg.stream_idle_overrides)`。这一点两个方案都要做。

**方案 B（推荐）：接进 `_events_with_ping` 既有的等待循环（`delivery/stream.py:31-99`）**

在 `stream.py:52` 旁边多算一个 `upstream_idle_deadline`，加入 `:54-63` 的 `pending_deadlines` 列表，并在 `:80` 那组「哪个 deadline 到点了」的判断里加一支抛 `StreamIdleTimeoutError`；deadline 只在 `task.done()`（即**上游真的给了一个事件**）之后重建。

- 优点一：**语义与用户文档逐字对齐**——计的就是 SSE 事件之间的间隔。
- 优点二：**不新增一层生成器**，复用已经存在、已经处理好取消与清理（`stream.py:83-99` 的 `finish_stream_cleanup`）的循环。
- 优点三：结构上与 `session_liveness_stream`（`keepalive.py:8-49`）完全同形，那份代码的语义正确性已有 15 个单测覆盖（`tests/unit/test_streaming_resilience.py`），可以照搬判据而不是照搬代码。
- 优点四：满足项目记忆「保活计时要读自己那一侧」——这个 deadline 由上游 pull 的完成重置，与同一循环里那个面向下游的 `ping_deadline` 互不干扰。**实现时必须守住这条：发出一个 ping 不得重置 upstream idle deadline。**
- 缺点：`src/app/pipeline/delivery/stream.py` 正在被并行会话修改（`git status` 显示 ` M`）。**这是排期问题不是取舍问题**，按项目规则不构成缩小范围的理由，但需要与那个会话协调落地时机。

**方案 C：改用 `session_liveness_stream` 替换 `_events_with_ping`——不建议。** 两者不等价：`_events_with_ping` 用 `None` 哨兵同时表达「该发 ping」和「该合成响应头」两件事，而 `session_liveness_stream` 只会 yield 一个固定的 heartbeat 项，且没有 `response_headers_deadline`。替换会丢掉 `synthesized_response_headers_after_sec`（默认 240s）这项行为。

**方案 D：在 driver 层（`direct_driver/base.py`）接——不可行。** driver 在响应头到达时就返回了，它根本看不到 body。

### 3.3 无论哪个方案都要一并决定的三件事

1. **用哪个 resolver**：必须是 `pipeline/timeouts.py:resolve_timeout`，不是 `streaming/idle_timeout.py:resolve_stream_idle`（后者匹配规则不合裁决）。
2. **异常落地成什么**：当前 `_tracked_delivery`（`pipeline_app.py:415-419`）会把它记成 `accounting.failure`，日志行得到 `status_override="fail"` + `detail="stream failed before a terminal event: No stream item received for Ns"`（`pipeline_app.py:352-353`）。**这一条现成可用，日志侧不需要额外工作。** 客户端侧则只能是撕断（见 §3.1 末），除非同时补 STR-04 的带内 error 事件。
3. **超时后要不要重试**（`upstream_request_retry.strategies` 的哪一栏）。**未裁决，建议提请用户裁决**，不要默认。当前 `classify()`（`pipeline/exceptions.py`）对闭集外的一切返回 ABORT，而 `StreamIdleTimeoutError` 不在闭集里；何况这个异常发生在 driver 已经返回之后，重试根本不在 driver 的控制范围内——**要重试就是一次架构改动，不是加一个分支。**

---

## 4. 既有的重叠机制

### 4.1 `session_liveness_stream` / `keepalive_stream`：零生产调用方

全仓 `rg 'session_liveness_stream|keepalive_stream|finish_stream_cleanup' src/ tests/` 的结果：

- `session_liveness_stream`：定义在 `keepalive.py:8`，生产代码中唯一的调用者是同文件 `keepalive.py:170`（即 `keepalive_stream`）。其余 15 处全在 `tests/unit/test_streaming_resilience.py`。
- `keepalive_stream`：定义在 `keepalive.py:164`，**生产代码中零调用者**，只有 `test_streaming_resilience.py:20,45` 在用。它给内层传的 `upstream_idle_timeout_seconds=0`（`keepalive.py:174`），即那个 idle 能力在这条（不存在的）路径上本来也是关的。
- `finish_stream_cleanup`：**这一个是活的**，被 `src/app/streaming/sse.py:193`（legacy）和 `src/app/pipeline/delivery/stream.py:89`（新链路）复用。

**结论**：新链路只用到 `keepalive.py` 的清理助手，**没有间接用到那个 idle 能力**。`docs/tmp/260820-downstream-keepalive-defect.md:110` 的记载与此一致。强度【足以据此行动】。

### 4.2 `session_liveness_stream` 与 `with_idle_timeout` 的语义差异

| | `with_idle_timeout`（`idle_timeout.py:19`） | `session_liveness_stream`（`keepalive.py:8`） |
|---|---|---|
| 计时起点 | 每次 `anext` 调用的那一刻 | `pending` 任务被创建的那一刻（`keepalive.py:27-28`），两者实质相同 |
| 是否包含首字节等待 | **包含**。第一次 `anext` 就带 `fail_after` | **包含**。第一个 pending 任务创建时就设 deadline |
| 下游停读时会怎样 | 计时器随 `anext` 的调用节奏走；下游不拉，就不计时 | **计时器独立于下游**：pending 任务一直挂着，deadline 照走 |
| 是否同时发心跳 | 否，纯守卫 | 是，`heartbeat_interval_seconds` + `heartbeat` 项 |
| 实现机制 | `anyio.fail_after` | `asyncio.wait(..., timeout=)` + 手算 deadline |
| 取消/清理 | 无特别处理（依赖外层） | `finally` 里走 `finish_stream_cleanup`，处理 pending 任务与源迭代器 |

第三行是**真正的语义差异**，并且正是项目记忆「保活计时要读自己那一侧」讲的那件事。在块级交付下两侧是脱钩的：`with_idle_timeout` 只有在有人拉它时才计时，所以下游被 Starlette 背压卡住时，上游的静默不会被计入；`session_liveness_stream` 的 deadline 与下游是否消费无关。**方案 B 继承的是后者的形状**（deadline 挂在 pending pull 上），这是对的。强度【足以据此行动】（两处代码可直接对读）。

### 4.3 真正在跑的那个重叠机制：SDK 的 600 秒 read timeout

这是本次调查最重要的发现，之前的取证文档没有记录。

`src/app/server/composition.py:75-81`：

```python
def build_http_client(config: ProxyConfig) -> httpx.AsyncClient:
    options = transport_options(config)
    return httpx.AsyncClient(
        proxy=options.proxy,
        http2=options.http2,
        limits=httpx.Limits(keepalive_expiry=options.keepalive_expiry),
    )
```

**没有 `timeout=`**。于是这个 client 的 `.timeout` 是 httpx 的 `DEFAULT_TIMEOUT_CONFIG`（`Timeout(timeout=5.0)`）。而 openai / anthropic SDK 在 `_base_client.py:1464-1467` 有这么一段：

```python
if http_client and http_client.timeout != HTTPX_DEFAULT_TIMEOUT:
    timeout = http_client.timeout
else:
    timeout = DEFAULT_TIMEOUT
```

因为我们的 client 用的**正是** httpx 默认值，条件为假，SDK 采用它自己的 `DEFAULT_TIMEOUT`。实测（`uv run python`，构造与 `create_copilot_sdk_clients` 同形的三个对象）：

```
httpx client timeout: Timeout(timeout=5.0)
openai effective timeout: Timeout(connect=5.0, read=600, write=600, pool=600)
anthropic effective timeout: Timeout(connect=5.0, read=600, write=600, pool=600)
（openai 2.21.0 / anthropic 0.79.0 / httpx 0.28.1）
```

而 httpx 的 read timeout **在 body 迭代期间是逐次读的空闲超时**，不是整个响应的总时限。实测（`/tmp/idle-research/probe_read_timeout.py`：本地服务器每 0.2s 发一个 chunk 共 5 个然后永久停顿，客户端 read=0.5s）：

```
headers at 0.01s status=200
chunk b'data: 0\n\n' at t=0.21s gap=0.20s
...
chunk b'data: 4\n\n' at t=1.02s gap=0.20s
RAISED httpx.ReadTimeout:
  at t=1.52s, 0.50s after the last chunk
```

总时长 1.52s 远超 0.5s 而没有触发，触发点恰好是**最后一个 chunk 之后 0.5s**——证实是 per-read 空闲语义。

**由此得到的事实链**（强度【足以据此行动】，两条独立证据：SDK 源码分支 + 端到端探针）：

1. 新链路此刻**已经有一个 600 秒的上游空闲超时**，字节级，不可配置，与 `stream_idle=0` 的配置无关。
2. 它触发时抛的是 `httpx.ReadTimeout`。这个异常发生在 body 迭代阶段，**不经过 `_in_pipeline_terms`**（`ghc_client/client.py:99-113` 只包住 `await post`），所以**不会被 `normalize_upstream_error` 归一成 `UpstreamTimeout`**。它会作为普通 `Exception` 被 `_tracked_delivery`（`pipeline_app.py:415`）记成 `accounting.failure`，日志行是 `fail` + `stream failed before a terminal event: ...`。
3. 这与用户亲笔的冻结不变量「bundled defaults 全部禁用此类终止器 / bundled defaults disable these terminators」**直接冲突**：配置说没有空闲超时，实际有 600 秒。
4. legacy 链路没有这个问题的隐蔽性：`src/app/upstream/client.py:31-36` 显式传了 `httpx.Timeout(read=read_timeout)`，默认 300（`settings.py:26`），SDK 因而采用 client 的值。**legacy 上是 `with_idle_timeout(300)` 与 httpx read(300) 两个同量级守卫并存**；新链路上是「配置的 0」与「SDK 的 600」并存。

**这条不是我要求的五个问题里的任何一个，但它决定了「新链路要不要接 idle timeout」这个问题的前提**：不是「从没有到有」，而是「从一个隐式的、不可配的、报错含糊的 600s，改成一个显式的、可配的、语义正确的守卫」。建议把它作为 §6 的第一条提请用户裁决。

### 4.4 那么新链路该复用哪一个

**不复用 `with_idle_timeout`，也不复用 `session_liveness_stream`，而是把后者的判据搬进 `_events_with_ping`**（方案 B）。理由：

- `with_idle_timeout` 的下游耦合计时（§4.2 第三行）在块级交付下是错的方向。
- `session_liveness_stream` 整体替换会丢掉响应头合成（§3.2 方案 C）。
- `_events_with_ping` 已经是一个「多 deadline 竞速 + pending pull」的循环，加第三个 deadline 是**增量最小、语义最贴**的做法。

`streaming/idle_timeout.py` 与 `streaming/keepalive.py` 里的 `session_liveness_stream` / `keepalive_stream` 在新链路接完之后**依然没有生产调用方**。按项目记忆「不得擅自删除已实现的功能」，**不建议在本次任务里删它们**；是否清理是另一件事，交用户裁决。

---

## 5. 非流式请求

### 5.1 新链路非流式路径的保护

`src/app/server/pipeline_app.py:292-301`：`body = cast(dict[str, Any], response.json())`。这里 body 已经被 SDK 在 `provider.send(stream=False)` 里读完了，所以非流式路径上：

| 守卫 | 位置 | 生效值 | 覆盖范围 |
|---|---|---|---|
| `client_delivery.client_request_deadline` | `handler.py:208-215` | 3600 | 整个 `handle()`，含全部重试。非流式下**确实**覆盖到 body 读完 |
| `upstream_request_timeouts.upstream_request_deadline` | `direct_driver/base.py:233-241` | 1200 | 单次尝试。非流式下覆盖到 body 读完 |
| SDK read timeout | `composition.py:75-81` 的空缺 + SDK 默认 | 600（per-read） | 单次 socket 读之间的空档 |

**结论：非流式有等价保护，而且是三重的。** `stream_idle` 在非流式路径上没有对应物，也不需要——它管的是「SSE 事件之间」，非流式没有 SSE 事件。**不会重复，也不会冲突。** 强度【足以据此行动】。

### 5.2 但流式路径上，这两个上层守卫都是失效的

**这一条与 §5.1 是同一份代码的另一面，必须一起读。**

- `handle_bounded` 的 3600s（`handler.py:208-215`）只包住 `handle()`。流式下 `handle()` 在拿到响应头时就返回了，body 迭代发生在它返回之后（`pipeline_app.py:278`）。`docs/tmp/260820-server-timeout-forensics.md:104` 已经记过这一条。
- `DirectDriver._send` 的 `attempt_deadline`（`base.py:233-241`）同理。流式下 `provider.send(..., stream=True)` 拿到响应头即返回（整个新链路都依赖这一点：`pipeline_app.py:278` 之后还能 `aiter_bytes()`）。

**所以 `base.py:221-224` 的 docstring 说错了**：

> The deadline bounds the whole attempt rather than a phase of it, which is what catches an upstream that trickles forever.

在流式路径上它恰恰**只**约束了一个阶段——首字节前的等待，也就是 `response_header` 本该管的那一段。「一直滴水但永不结束」的流式尝试**没有任何东西拦得住**（除了 §4.3 那个 600s per-read）。用户文档 `config.example.yaml` 里 `upstream_request_deadline` 的注释正是为了填这个洞而写的，而实现没有做到。强度【足以据此行动】（静态读码链条完整：`_send` 返回 → `pipeline_app` 才开始迭代 body，这是新链路能工作的前提）。

### 5.3 `upstream_request_timeouts` 各键的实际消费情况

| 键 | 生效默认 | 谁在读 | 状态 |
|---|---|---|---|
| `response_header` | 0 | **没有任何人读**（全仓 `rg` 只有 `schema.py:100` 的定义） | 未接线 |
| `response_header_overrides` | `{}` | `handler.py:103` | **被拿去当 `upstream_request_deadline` 的覆盖表用了**，见下 |
| `stream_idle` | 0 | 无（新链路） | 本次任务要接的就是它 |
| `stream_idle_overrides` | `{}` | 无（新链路） | 同上 |
| `upstream_request_deadline` | 1200 | `handler.py:102` | 已接线，但流式下语义不符（§5.2） |

**`handler.py:99-104` 的错配**：

```python
timeouts = chain.config.upstream_request_timeouts
attempt_deadline = resolve_timeout(
    route.model_id,
    timeouts.upstream_request_deadline,     # 标量取 deadline
    timeouts.response_header_overrides,     # 覆盖表却取 response_header 的
)
```

用户文档明写 `response_header_overrides` 是「按模型覆盖的 **response_header**」。按现行代码，运维给某个模型调首字节等待，实际改的是那个模型的**单次尝试总存活上限**；同时 `response_header` 标量本身没有任何消费点。当前两张表都是空的，所以生效值就是标量 1200，**没有可观测症状**。

`docs/tmp/260820-server-timeout-forensics.md:97` 已经把这条记为「倾向性观察，需要再确认设计意图」。我这次拿到了用户亲笔文档的逐字表述，可以把强度提到【足以据此行动】——**它确实是错配**，`response_header_overrides` 的语义由用户文档定义，不存在「设计意图另有其他」的空间。但**修不修、怎么修（补 `upstream_request_deadline_overrides`？还是让 `response_header` 单独接线？）超出本次任务范围，登记待裁决。**

---

## 6. 待用户裁决的点（按重要性）

1. **SDK 的 600 秒隐式 read timeout 要不要显式化。** 它与冻结不变量冲突（§4.3）。三个可能方向：(a) 给 `build_http_client` 传显式 `timeout=httpx.Timeout(connect=..., read=None, ...)` 关掉它，让 `stream_idle` 成为唯一的空闲守卫；(b) 保留它但把它接到 `stream_idle` 上（即用配置值驱动 httpx 的 read timeout）；(c) 明确接受 600s 作为兜底并写进文档。**我的倾向是 (a)**：httpx 的 read timeout 是字节级、异常不归一、无法按模型覆盖，三条都不满足用户裁决的语义；把守卫收敛到一处，语义才说得清。
2. **idle timeout 触发后要不要重试，归 `upstream_request_retry.strategies` 的哪一栏。** 未裁决，且当前架构下 driver 已返回、重试不在其控制范围内（§3.3 第 3 条）。
3. **触发后客户端应看到什么。** 新链路上状态码只能是 200（§3.1 末），可辨认的失败只能是带内 SSE `error` 事件，而那块是 STR-04 已登记的缺口。是否把两件事并成一个切片。
4. **§1.2 的措辞歧义**：「bundled defaults 全部禁用此类终止器」是否包含 `upstream_request_deadline`。
5. **`response_header` / `response_header_overrides` 的错配与未接线**（§5.3）。
6. **流式路径上 `upstream_request_deadline` 语义不符**（§5.2），以及 `base.py:221-224` docstring 与实际行为不一致。

---

## 附录：本次用到的命令与探针

全部只读，产物落在 `/tmp/idle-research/`，未写入仓库。

- `uv run python -c "print(TimeoutError.__mro__)"` → `(TimeoutError, OSError, Exception, BaseException, object)`
- `uv run python -c "..."` 构造与 `create_copilot_sdk_clients` 同形的 `AsyncOpenAI` / `AsyncAnthropic`，打印 `.timeout` → §4.3 的 600s
- `/tmp/idle-research/probe_read_timeout.py`：本地 asyncio 服务器 + httpx，证明 read timeout 是 per-read 空闲语义（需 `python -u`，否则 `timeout` 杀进程时看不到输出）
- `/tmp/idle-research/probe_legacy_idle_visible.py`：真 uvicorn + 真 httpx，四条路由分别覆盖 `create_sse_response` / `create_delayed_sse_response` × 首字节前/后。**注意 §2.4 记的局限：它测的是两个响应类本身，不含 `render_responses_as_anthropic_sse`，所以 `/delayed-before` 那栏的 500 不代表真实 Responses 腿的行为（真实是 502）。**

---

# 实现复核（2026-08-20 追加，应主会话请求）

主会话采纳了本报告大部分结论，但选了我列为次选的**方案 A**，并要求我尽力反驳。本节是反驳的尝试与其结果。**反驳失败，我撤回方案 B 的推荐。**

全部实验在隔离副本树 `/tmp/rev-idle/`、`/tmp/rev-idle2/` 中进行（`src` `tests` `pyproject.toml` `uv.lock` 全量复制，用 `PYTHONPATH=<副本>/src` 压过 editable 安装的 `.pth`——已先验证解析确实落到副本：`app.__file__` 打印为 `/tmp/rev-idle/src/app/__init__.py`）。仓库 `src/`、`tests/` 未被修改，未执行任何 git 写操作。副本树同步时点：worktree HEAD `5b960c8`（并行会话在复核过程中把 HEAD 从 `1ac5ab2` 推到了 `5b960c8`，漂移集中在 count_tokens / server_tools / assembler，与本次守卫无关）。

| 复核项 | 结论 | 强度 |
|---|---|---|
| (a) `read_events` 丢弃注释帧 | **是**。4 个 chunk（3 个注释帧 + 1 个真事件）进，1 个事件出 | 【足以据此行动】，实测 |
| (b) 方案 B 在注释保活下误杀 | **是**。我自建 B 变体独立复现了主会话的 C1／C2 | 【足以据此行动】，实测 |
| (c) 有没有第三条路 | 有形状，**但不解决问题类**：C-1 修好了注释这一例，换个形态照样误杀 | 【足以据此行动】，实测 |
| 是否维持方案 B 推荐 | **不维持。改判为方案 A** | — |
| 改动 3 对 legacy 的影响 | **无重复关闭、无行为改变**，字面上是 inert | 【足以据此行动】，变异验证 |
| 改动 3 在新链路上的效力 | **比它的 rationale 说的弱**：generator 级确实变确定，socket 级没有差别 | 【足以据此行动】，真实 socket 实测 |
| 那条取消交互测试 | **值得留，但两处该改**；且它对改动 3 无分辨力这件事有结构性原因 | 【足以据此行动】 |
| blocker | **0** | — |

---

## R1 我改变判断的依据

### (a) `read_events` 确实丢弃注释帧

代码上有两道：`sse_source.py:40-41` `if line.startswith(":"): continue`（注释行直接跳过），以及 `:51-52` `if not data_lines: return None`（没有 data 行就不成事件）。实测（`/tmp/rev-idle/probe_a_comments.py`）：

```
chunks fed: 4 (3 comment frames + 1 real event)
events yielded: 1 -> [SseEvent(event='message_start', data='{"x":1}')]
```

主会话的前提成立。

### (b) 方案 B 在 C1 形态下确实误杀

我没有读主会话的探针，自己在副本树里把方案 B 实现了一遍（给 `_events_with_ping` 加第三个 deadline，只在 `task.done()` 拿到解析事件时重排），再把 A 与 B 放在同一组上游、同一个 1 秒预算下跑：

```
idle budget = 1.0s, quiet window = 2.4s

  plan A  C1 comment keepalive every 0.6s over 2.4s -> delivered whole
  plan A  C2 真静默 2.4s                             -> FIRED  (No stream item received for 1s)

  plan B  C1 comment keepalive every 0.6s over 2.4s -> FIRED  (No upstream stream item received for 1s)
  plan B  C2 真静默 2.4s                             -> FIRED  (No upstream stream item received for 1s)
```

独立复现，结论一致：**B 在一条字节仍在流动的连接上击发**。这正是用户亲笔冻结不变量禁止的那种误杀。

### (c) 第三条路：存在，但不解决问题类

我把主会话提的那条路（「在 `read_events` 里把注释也当作『上游还活着』的信号往上传」）实现了出来，记作 **C-1**：`read_events` 对无 data 的完整帧 yield 一个 `Liveness()` 标记；`_events_with_ping` 收到它就重排 deadline 并继续拉，不往上层转发。形状与代价：

- **形状**：`read_events` 的产出类型从 `SseEvent` 变成 `SseEvent | Liveness`，消费者必须判别。当前消费者只有 `stream.py:46` 一处，改动面很小。
- **代价一**：它把一个纯解析模块的契约改成了「解析结果 + 活性信号」的混合通道。`sse_source.py` 的 docstring 现在讲的是 SSE 解析，加进活性语义之后它同时服务两个目的。
- **代价二，也是决定性的那条**：它只是把误杀边界从「字节」挪到「帧」，**没有把误杀面清空**。

第三个场景 C3 证明了这一点——上游发一个合法的大 block，分片 trickle 2.4 秒（字节在流动，但 2.4 秒内没有任何一帧闭合）：

```
（C-1 变体在位）
  plan A  C1 comment keepalive every 0.6s over 2.4s -> delivered whole
  plan A  C2 真静默 2.4s                             -> FIRED
  plan A  C3 一个大 frame 分片 trickle 2.4s           -> delivered whole

  plan B  C1 comment keepalive every 0.6s over 2.4s -> delivered whole   ← C-1 修好了注释这一例
  plan B  C2 真静默 2.4s                             -> FIRED
  plan B  C3 一个大 frame 分片 trickle 2.4s           -> FIRED            ← 但换个形态照样误杀
```

**关于 C3 的现实性，我必须说清楚**：Anthropic 与 Responses 两种 SSE 里，大块工具入参是拆成许多个 `content_block_delta` 帧发的，每个都是完整帧，所以「单个巨帧慢速 trickle」是否真会从 Copilot 上游出现，我没有证据。C3 的强度分两层——**机制层【足以据此行动】**（它证明 C-1 的误杀面非空，且证明「事件级／帧级」这一族做法都要逐个形态去堵）；**现实风险层【仅为倾向，需更多样本】**（我没测过真实上游的帧尺寸分布）。

但这不影响结论，因为判据不是「哪个误杀概率低」，而是用户写下的是绝对措辞：「**绝不**误杀合法长思考」。**方案 A 的误杀面是空的（任何字节都重排计时器），C-1 的误杀面只是比 B 小。** 在一条绝对表述的不变量面前，「更小」不等于「满足」。

### 我原来错在哪

我在 §3.2 把「用户措辞是事件级」排成了第一判据，据此判 B 优于 A。这是**判据排序错误**，不是事实错误：同一份 `docs/.human-controlled/config.example.yaml` 里，`stream_idle` 那行注释是**接口描述**，而「绝不误杀合法长思考」被明写为**冻结不变量**；两者在「上游用注释保活」这一情形下互相冲突时，不变量优先。我在 §1.1 已经把这条不变量抄下来了，却没有把它当成一条会与措辞相冲突的约束去检验，只把它读成了「所以默认值是 0」。

一并修正 §3.2 里那句「方案 A 的缺点一：计的是字节间隔，不是 SSE 事件之间，二者不等价，字节级更宽松」——**「更宽松」在这里是优点而不是缺点**，且我当时没有算出「更宽松」具体宽在哪（就是注释保活这一格）。

同时，§3.2 我给方案 B 记的优点四「满足『保活计时要读自己那一侧』」也需要收窄：那条记忆讲的是「面向 A 侧的守卫别用 B 侧活跃度重置」。B 满足它，**A 同样满足**——A 的计时器由上游字节重排，与下游是否在读无关。这一条不构成 B 对 A 的优势。

**结论：撤回方案 B 推荐，采纳方案 A。**（§0、§3.2、§4.4 里的推荐以本节为准；上文原文保留不改，以便看到判断是怎么变的。）

---

## R2 方案 A 落地之后仍然敞着的那个洞

这不是反对 A，是记账。方案 A 的守卫由任何字节重排，所以**一个永远发注释、永远不出内容的上游，A 拦不住**。而按本报告 §5.2，`upstream_request_deadline`（1200s）在流式路径上只约束到响应头为止，也拦不住；§4.3 那个 SDK 隐式 600s read timeout 是字节级的，同样拦不住。

**即：这次改动落地后，「一直滴水但永不结束」的流式尝试没有任何东西约束——而这恰恰是用户在 `config.example.yaml` 里给 `upstream_request_deadline` 写注释时点名要堵的那一类。** 这不是新问题，是 §5.2 与 §6.6 已登记的待裁决项；本节把它的优先级提上来，因为方案 A 的正确选择使它成为该类失效的唯一剩余出口。

---

## R3 改动 3 对 legacy：无重复关闭，无行为改变

在副本树里用**真实 httpx 客户端 + 真实本地 HTTP 服务器**，按 legacy 的组合形状跑（`passthrough_bytes(with_idle_timeout(upstream.aiter_raw()), cleanup=upstream.aclose)`），三个场景，并对「有／无改动 3」各跑一遍（`/tmp/rev-idle2/probe_legacy_close.py`）：

```
（有改动 3）
[stall, idle=0.5] guard fired: No stream item received for 0.5s | response.is_closed=True | a further aclose() is a no-op
    server observed: ['server: connection open', 'server: peer closed the connection']
[finish, idle=30] stream drained normally | response.is_closed=True | a further aclose() is a no-op
    server observed: ['server: connection open']
[stall, idle=0]   guard never fired within 3s | response.is_closed=True | a further aclose() is a no-op
    server observed: ['server: connection open', 'server: peer closed the connection']

（撤掉改动 3，逐字节同上）
```

**两次输出完全一致。** 结论：

- **不会重复关闭。** `with_idle_timeout` 关的是 `upstream.aiter_raw()` 这个 async generator，`passthrough_bytes` 的 `cleanup` 关的是 `upstream`（`httpx.Response`）——两个不同对象；且 `httpx.Response.aclose` 有 `if not self.is_closed` 守卫，async generator 的 `aclose()` 本身幂等。探针里额外再调一次 `aclose()`，回的是 no-op。
- **不改变 legacy 行为。** legacy 早就有 `cleanup=upstream.aclose`，那才是真正释放连接的那一步；改动 3 在 legacy 上是 inert。
- legacy 相关测试在副本树全绿：`tests/http/test_anthropic_routes.py`、`tests/smoke/test_anthropic_responses_{stream_route,route,happy_path}.py`、`tests/unit/test_streaming_{sse,resilience}.py` 合计 **110 passed**。（注意这只证明常规流程无回归；这些用例并不触发 idle 击发，击发路径由上面的探针覆盖。）

---

## R4 改动 3 在新链路上的真实效力，比它的 rationale 说的弱

改动 3 的理由写的是「不加这个会在刚落地的关闭级联（commit 926cabf）上重新打洞」。我分两层测了这句话。

**第一层，generator 级：这句话成立。** 用手写源流跑生产组合 `stream_delivery(_counted_upstream(with_idle_timeout(source)))`，在「无人拉取、直接 aclose」这一格上（`/tmp/rev-idle/probe_cascade.py`）：

```
                                     有改动 3                              撤掉改动 3
PRODUCTION (含 _counted_upstream)  close-only    立即释放                  immediate=NOT RELEASED / after_gc=released
PRODUCTION (含 _counted_upstream)  cancel+close  立即释放                  立即释放（取消直接落在上游栈帧里）
PINNED TEST 形状 (无 _counted_upstream) close-only 立即释放                 立即释放
```

**第二层，socket 级：这句话不成立。** 换成真实 httpx 响应 + 真实服务器观察对端（`/tmp/rev-idle2/probe_new_release.py`），生产组合、拉一个块后 aclose：

```
=== 有改动 3 ===
  right after aclose(): server=['nothing'], response.is_closed=False
  after 0.3s of loop:   server=['peer closed'], response.is_closed=False
=== 撤掉改动 3 ===
  right after aclose(): server=['nothing'], response.is_closed=False
  after 0.3s of loop:   server=['peer closed'], response.is_closed=False
```

逐字节相同，且「有改动 3」连跑 3 次结果稳定。原因在 httpx 自己：`Response.aiter_raw` 里那句 `await self.aclose()` 写在循环**之后**、不在 `finally` 里，`aiter_bytes` 同样只是 `async for ... in self.aiter_raw()` 的裸循环。所以 `aclose()` 掉 `aiter_bytes()` 这个 generator **不会**触发 `Response.aclose()`；连接的释放仍然要等 async generator 终结器在后续 loop 轮次里跑，两个版本都一样。

**该怎么读这个结果（我的判断，强度【足以据此行动】）**：

1. **改动 3 不该撤。** 它让 `with_idle_timeout` 遵守这条链上其他每一层都遵守的规则——`read_events`（`sse_source.py:85-87`）、`stream_delivery`（`stream.py:125`）、`_tracked_delivery`（`pipeline_app.py:410`）都结算自己消费的东西。一层守卫不结算，是等着下一次组合变化时踩的坑。
2. **它的 rationale 需要改一句**，否则下一个人拿 socket 去验它会得到「级联是通的」这个错误印象。准确的说法是：它保证 `with_idle_timeout` 这一层的级联是确定的；**httpx 的响应对象不参与级联，其释放仍然靠 generator 终结**。
3. **这条链上唯一不结算自己所消费者的，是 `_counted_upstream`**（`pipeline_app.py:403-411`，裸 `async for`，无 `finally`、无 `aclosing`）。它不是这次改动引入的，改动前后都在，而且因为 httpx 那一层本来就不级联，它当前也测不出症状。**登记为遗留结构缺口，不是本次的 blocker。**
4. 926cabf 提交信息里那句「the cancellation arrives at the upstream's own await point, so every `finally` down that stack runs」是对的，但它描述的是**取消**路径。上表第二行印证了这一点：cancel+close 那一格，有没有改动 3 都立即释放。真正只能靠级联的是**没有在途拉取时被关闭**这一格，而那一格止步于 httpx。

---

## R5 那条取消交互测试：留，但两处该改

`tests/unit/test_stream_delivery.py::test_a_client_leaving_while_the_idle_guard_is_armed_leaves_nothing_behind`。

**留。** 它钉的那个担心是真的：`with_idle_timeout` 把一个 anyio cancel scope 撑在它计时的那次 `anext` 上，而那次 `anext` 跑在 `_events_with_ping` 每轮新建的任务里；scope 在一个任务里进、在另一个任务里退，是会留下悬空 scope 的形状。这条组合值得钉住而不是靠推理。而且它的 `assert asyncio.all_tasks() - before - {current} == set()` 正是 926cabf 那条性质的守卫。

**两处该改：**

1. **失败形态从「挂起」改成「红字」。** 主会话已如实记录：打掉清理里的 `pending.cancel()` 时这条测试**挂起**而不是变红。挂起会把整个 pytest 进程拖住，比失败更糟。把 `pump.cancel()` 到 `await delivery.aclose()` 这一段包进 `async with asyncio.timeout(...)` 就能把它变成红字——这一条我**没有实测**，是从「无界 await 加上界即得失败」推的，强度【仅为倾向】，但代价低到可以直接做。
2. **组合改成生产实际用的那个**，即在 `with_idle_timeout` 外面套 `_counted_upstream`。当前测试少了这一层，而这一层恰好是 R4 第一层实验里唯一能看出差别的地方：`PINNED TEST 形状` 那一行两个版本都立即释放，`PRODUCTION` 那一行才分得开。**「测试组合与生产组合在被质疑的那一环上不一致」本身就值得修，与它能不能测出改动 3 无关。**

**关于「`closed == [True]` 对改动 3 没有分辨力」，有结构性原因，不是运气。** 主会话给的解释（「取消直接落在上游栈帧里」）经我实测确认（R4 上表第二行）。补充一条：即便换成 close-only 形态，在**缺少 `_counted_upstream`** 的组合里两个版本也都立即释放。所以这条断言在当前组合下对改动 3 天然无分辨力，**不该被当成改动 3 的证据读**。

**一个对改动 3 真正有分辨力的钉法**（如果确实想钉它）：生产组合 + close-only + **在 `aclose()` 之后立刻取快照，不给任何 `sleep`**，断言源流已被释放。我实测过它的两态：撤掉改动 3 → `NOT RELEASED`（红），装回 → 释放（绿）。**但必须给这条测试写清它钉的是什么**：它钉的是「这一层遵守级联规则」，用的是一个会级联的手写源流；它**不**钉、也钉不出真实 httpx 响应的释放时机（R4 第二层）。不写清楚，它就会变成一条让人误以为 socket 级已被覆盖的绿灯。

---

## R6 blocker 结算与本节实验清单

**blocker：0。** 已落的四项改动我都核过，没有一项需要在合入前修正：

| 改动 | 核验结果 |
|---|---|
| 1. `stream_idle_seconds` 用 `resolve_timeout` | 与用户裁决的具体度规则一致 |
| 2. 守卫包在 `response.aiter_bytes()` 外 | 方案 A，我已改判支持；计时器由上游字节重排、与下游是否在读脱钩，符合「保活计时要读自己那一侧」；`stream_idle_seconds` 在构造响应时算一次，符合「流起点读一次」 |
| 3. `with_idle_timeout` 关闭源流 | legacy 无重复关闭、无行为改变（变异验证）；新链路 generator 级有效、socket 级无差别——**建议只改注释措辞，不改代码** |
| 4. 三条测试 | HTTP 两条到位；取消交互那条见 R5 的两点改法 |

**非阻塞、建议登记的三条**（都不是这次引入的）：

- R2：方案 A 落地后，「上游一直滴水但永不结束」在流式路径上无界。归入既有的 §5.2／§6.6 待裁决。
- R4-3：`_counted_upstream` 是这条链上唯一不结算自己所消费者的一层。
- R4-2：改动 3 的 rationale 措辞。

**实验清单**（全部只读，产物在 `/tmp/rev-idle/`、`/tmp/rev-idle2/`，仓库未被写入）：

| 探针 | 回答的问题 |
|---|---|
| `/tmp/rev-idle/probe_a_comments.py` | (a) `read_events` 是否丢弃注释帧 |
| `/tmp/rev-idle/probe_b_falsekill.py` | (b)(c) A／B／C-1 在 C1、C2、C3 三个上游形态下的击发行为 |
| `/tmp/rev-idle/probe_cascade.py` | 改动 3 在 generator 级的分辨力（生产组合 vs 钉住的测试组合 × close-only vs cancel+close） |
| `/tmp/rev-idle2/probe_legacy_close.py` | R3：legacy 组合、真实 socket、有／无改动 3 |
| `/tmp/rev-idle2/probe_new_release.py` | R4：新链路生产组合、真实 socket、有／无改动 3 |

副本树内的两次源码变异（方案 B 变体、C-1 变体、以及两次撤掉改动 3）均已还原，还原后与工作树逐字节相同（`diff` 无输出）。
