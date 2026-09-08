# ghc-api 可靠性 / 容错 / 超时 / 重试 / 上游连接管理 调研报告

- 被调研对象：`sxwxs/ghc-api`，本地只读副本 `/home/xp/.claude/jobs/89874ec2/tmp/ghc-api`，HEAD = `0cb1087`（Flask + waitress + requests，Python）。
- 调研范围：早期失败重试、SSE keepalive 与 pre-header grace、加密内容剥离重试、tool call 恢复、Copilot token 刷新、超时分层、MCP 并发上限。
- 全部结论均来自阅读该 commit 的源码；凡是只有 README/注释/决策文档支持而代码未证实的，均单独标注为「文档主张」。
- 权重档说明：`强到可直接采纳` = 代码事实明确、判据可直接引用；`是个倾向、需更多样本` = 代码形态确定但触发条件或收益未被证据覆盖；`仅存档、不据以决策` = 只是观感或单点样本。

---

## 1. 早期失败重试：判据边界在哪一行

### 1.1 实现点

唯一实现在 `ghc_api/sse/openai_responses.py` 的 `RetryingResponsesResponse`，它是一个**伪装成 `requests.Response` 的包装器**，只实现 `status_code` / `ok` / `text` / `iter_lines()` / `close()`，塞给 `SSEStreamHandler` 当上游用。

判据的三行核心（`ghc_api/sse/openai_responses.py:28-31`）：

```python
    _PRE_OUTPUT_EVENTS = {
        "response.created",
        "response.in_progress",
        "response.queued",
    }
```

主循环（`ghc_api/sse/openai_responses.py:114-130`）：

```python
            for line in lines:
                if self._current_response() is None:
                    return
                if output_started:
                    yield line
                    continue

                buffered.append(line)
                event_type = self._event_type(line)
                if event_type == "response.failed":
                    early_failure = True
                    break
                if event_type is not None and event_type not in self._PRE_OUTPUT_EVENTS:
                    output_started = True
                    yield from buffered
                    buffered.clear()
```

**「已发出真实内容」的定义与记录方式**：不是一个字节计数器，而是一个**布尔闸门 `output_started`**，由「上游 SSE 里出现了一个不在 `_PRE_OUTPUT_EVENTS` 白名单里的事件类型」翻转。翻转之前，所有行只进 `buffered` 列表、**一个字节都不下发**；翻转的那一刻 `yield from buffered` 一次性补发。所以「重试安全窗口」= 从连接建立到第一个非序幕事件为止，这段时间下游确实是零字节。

`_event_type` 的分类规则（`ghc_api/sse/openai_responses.py:82-100`）决定了边界的细节，这里有三个刻意的选择：

- 非 `data: ` 开头的行（`event:` 头、空行分隔）返回 `None`。`None` 既不触发失败也不触发提交，只是被缓冲 —— 即 SSE 信封本身不算「内容」。
- `data: [DONE]` 映射为 `"response.done"`，不在白名单里 → **提交**。
- JSON 解析失败返回 `""`，也不在白名单里 → **提交**。注释写得很直白：`# A malformed data payload is still downstream-visible output and therefore commits the stream`。这是「fail-safe 偏向不重试」的取向。

### 1.2 可重试 vs 不可重试

| 上游情形 | 是否重试 | 证据 |
|---|---|---|
| HTTP 200 + `response.created` … `response.failed`，其间无任何输出事件 | **重试**，上限 `max_connection_retries`（默认 3） | `openai_responses.py:123-125`、`:131-147` |
| 已出现 `response.output_text.delta` / `output_item.added` 等任意非序幕事件后再 `response.failed` | **不重试**，原样透传 | `:126-129` + 测试 `tests/test_sse_base.py:470-481` |
| 标准 `error` 事件（而非 `response.failed`） | **不重试**。这是 ghc-api 自己在 200 提交后合成的错误事件，重放它会让级联的下游代理把一个永远不会成功的请求打 4 次 | `:99`、`routes/openai.py:87-106` 的 docstring、测试 `tests/test_sse_base.py:494-510` |
| 重试请求本身抛 `ReadTimeout` / `ConnectionError` | **放弃重试**，把原来的 `response.failed` 还给下游（认为它比一个空 504 更有信息量） | `:133-137` |
| 重试拿到非 2xx（`retry_response.ok` 为假） | 关掉重试响应，透传原 `response.failed` | `:139-152` |
| 重试预算耗尽 | 透传最后一次的 `buffered`，并把 `response.failed` 之后的残余行也 `yield from lines` 补完 | `:154-159` |

补充两点代码事实：

- 重试是**换一条新连接、重建 headers、先刷 token**：`routes/openai.py:160-169` 的 `retry_streaming_response()` 里先 `ensure_copilot_token()` 再 `get_copilot_headers(enable_vision)`（后者每次生成新的 `X-Request-Id`，见 `api_helpers.py:141`）。Anthropic-over-Responses 路径同理，`routes/anthropic.py:1698-1706`，且其 `build_request_headers()` 的 docstring（`:1689-1693`）明确写了「不复用 headers，否则会重发一个刚被 `ensure_copilot_token()` 换掉的 token，把可恢复的重试变成 401，而且会让多次尝试共用一个 request id」。
- 包装器**不读 `response.text`**：`text` 写成 property（`:56-60`），注释解释在 `stream=True` 的响应上读 `.text` 会走 `Response.content` 从而把整个流吸干。有一条专门的回归测试守这一点（`tests/test_sse_base.py:389-404`）。这是个容易踩的坑，值得记。
- 关闭时序有锁保护：`_replace_response` 用一个 `threading.Lock` 做 compare-and-swap，输的一方负责 `close()`（`:68-80`），`close()` 与重试并发时的孤儿响应也被关（测试 `tests/test_sse_base.py:512-543`）。

权重：**强到可直接采纳**。判据、边界、失败分支、并发所有权四项都有代码与测试双重支撑。

### 1.3 一个不在窗口内的空洞

`RetryingResponsesResponse.iter_lines()` **不捕获上游迭代过程中抛出的异常**。序幕阶段如果连接被 RST（`ConnectionError`），异常直接穿过包装器传到 `SSEStreamHandler._generate()` 的 `except (ReadTimeout, ConnectionError)` 分支（`sse/base.py:359-365`），变成 504 + 一个错误事件 —— **不会重试**，尽管此时下游同样是零字节、完全满足重试安全条件。也就是说这个机制只覆盖「上游用 200 + `response.failed` 报错」这一种早期失败，不覆盖「上游早期直接断线」。

权重：**强到可直接采纳**（代码事实确定）。是否值得在我方补上这半边，取决于我方观测到的早期失败形态。

---

## 2. keepalive 的计时器读哪一侧？

### 2.1 代码事实：读的是**上游**活跃度

`ghc_api/sse/keepalive.py:140-199` 的 `iter_lines_with_keepalive` 是唯一的流内 keepalive 来源。上游行由后台 daemon 线程读入一个 `maxsize=128` 的队列，前台消费者：

```python
    try:
        while True:
            try:
                is_exc, item = q.get(timeout=interval)
            except queue.Empty:
                yield KEEPALIVE
                continue
```
（`ghc_api/sse/keepalive.py:183-188`）

`q.get(timeout=interval)` 的超时在**每次上游到达一行时被重置**。KEEPALIVE 只在「上游连续 `interval` 秒没有产出任何一行」时才产生。基类的消费点（`ghc_api/sse/base.py:273-277`）：

```python
            for line in iter_lines_with_keepalive(self.response, state.sse_keepalive_interval):
                if line is KEEPALIVE:
                    counters.incr("ping_sent")
                    yield self.keepalive_event()
                    continue
```

所以：**面向下游的保活守卫，用的是上游活跃度重置** —— 正是我方担心的那个装反方向。

权重：**强到可直接采纳**。

### 2.2 ghc-api 踩没踩这个坑：踩了，但只踩了一半

在纯透传路径（`/v1/responses`、`/v1/messages` direct）上两侧是 1:1 的，上游来一行下游出一行，读哪一侧等价，不构成缺陷。

但在 **Anthropic Messages ← OpenAI Responses 翻译路径**（`ghc_api/sse/anthropic_responses.py`，即我方的同类路径）上，翻译器对不同内容类型采取了不同的缓冲策略（`ghc_api/sse/anthropic_responses.py:446-459`）：

```python
    def _state_ready(self, state: _OutputState) -> bool:
        if state.item_type in ("reasoning", "web_search_call"):
            return True
        if state.item_type == "message":
            return bool(state.text) or state.done
        if state.item_type == "function_call":
            # Buffer the complete argument string so malformed/non-object JSON
            # can never be partially committed to an Anthropic tool block.
            return bool(state.done and state.name and state.call_id)
        if state.item_type == "custom_tool_call":
            # Custom input is not necessarily JSON; wait for the terminal item
            # so it can be wrapped as one valid JSON object.
            return bool(state.done and state.name and state.call_id)
        return False
```

- 文本：增量下发（`bool(state.text)` 一有内容就 ready），两侧仍近似耦合。
- **`function_call` / `custom_tool_call`：必须等 `state.done`（`response.output_item.done` 或终局事件）才开始下发**。
- **`reasoning`：`_drain()` 里同样 `if not state.done: break`**（`:480-482`）。
- 而且 `_drain()` 是**严格按 `output_index` 顺序**推进的（`:463` `while self.next_output_index in self.states:`），后面的 item 即便先完成也会被前面未完成的 item 堵住。

结果：当模型在生成一个大的 tool call 参数时，上游 `response.function_call_arguments.delta` 每几十毫秒来一行，`q.get()` 从不超时 → **KEEPALIVE 永不触发**；同时 `forward_event` 返回空列表 → **下游一个字节都收不到**。这段静默的长度等于该 tool call 的完整生成时长，可以远超客户端读超时。

这就是我方提出的「两侧活跃度脱钩」失效，ghc-api 在这条路径上**装反了守卫**，而且：

- 没有任何测试覆盖这个场景（`tests/test_sse_keepalive.py` 只有 `test_idle_stream_yields_keepalive_before_real_line` / `test_fast_stream_yields_no_keepalive` 这类上游侧断言，见测试名清单）；
- 该项目自己的决策文档 `docs/decisions/RESPONSES_PRE_HEADER_KEEPALIVE.md` 的开放项里也没有提到它（提到的是 pre-header 的三条路径不一致、退避睡眠不发 ping，见 §5 items 3/4），说明**这个坑他们尚未意识到**。

对我方的含义更严重：我方是**全量块级交付**，文本也要攒满一个完整 content block 才发。ghc-api 至少在文本上保留了增量下发因而部分掩盖了问题；我方没有这层掩盖，脱钩是普遍的而不是仅限 tool call。

权重：**强到可直接采纳**（代码路径确定、可复算；「未被测试覆盖」也已用测试清单证否）。

### 2.3 正确的形状应该是什么

从这份代码反推，可用的分离是：

- **面向下游的保活**：计时器应挂在「上一次真正 `yield` 出下游字节」的时刻上，与上游是否在忙无关。实现上就是把 keepalive 判定从 `iter_lines_with_keepalive` 内部移到 `_generate` 的发射点外面（或者让消费者每轮把「本轮是否产出了下游字节」回传给计时器）。
- **面向上游的停滞检测**：`q.get(timeout=...)` 这套按上游活跃度计的逻辑本身是对的，它应当被重新定位为**上游 stall 探测**（用于打日志、计数、触发放弃），而不是下游保活。

ghc-api 现在把这两件事合成了一件。

权重：**是个倾向、需更多样本**（这是我从代码反推的设计建议，非该项目已验证的做法）。

### 2.4 pre-header grace 的机制细节

三个状态项（`ghc_api/state.py:75-85`）：

```python
        self.upstream_read_timeout: int = 1800
        self.sse_keepalive_interval: int = 30
        self.responses_pre_header_grace: float = 0.5
```

机制（以 `/v1/responses` 为例，`ghc_api/routes/openai.py:1733-1785`）：

1. `_start_responses_post()` 把 `requests.post(stream=True)` 丢到后台 daemon 线程（`BackgroundResult`，`sse/keepalive.py:27-70`），路由线程不再被阻塞在 header 等待上。
2. `grace = min(state.responses_pre_header_grace, state.sse_keepalive_interval)`，然后 `pending_response.get(timeout=grace)`。
3. **grace 内拿到响应**（无论状态码）→ 走原来的同步路由分支：2xx 交给 stream handler，非 2xx **保留真实 HTTP 状态码与响应体**，并继续走加密内容剥离重试等既有逻辑（`:1758-1785`）。
4. **grace 内没拿到**（`queue.Empty`）→ `_stream_pending_responses_request()`：**立刻提交 SSE 响应头并发一条 `: keepalive`**（`:238-241`），然后在生成器里继续等上游。此后任何上游错误只能表达成 SSE `error` 事件，HTTP 状态码已经锁死为 200。
5. **grace 内拿到的是异常**（快速失败）→ 特殊处理（`:1748-1756`）：把异常重新包进一个新的 `BackgroundResult` 里，让快失败和慢失败走同一条流式错误路径。这是个小而聪明的归一化。

映射关系一句话：**「有没有拿到 HTTP 响应」而不是「快不快」决定分流**。决策文档 D1（`docs/decisions/RESPONSES_PRE_HEADER_KEEPALIVE.md:38-47`）写明了理由 —— 早期版本对所有非 2xx 都走流式，导致客户端丢掉 429（不再退避，反而重试更凶）、丢掉 401（不再重新鉴权），且面板与客户端看到的状态不一致。`ConnectionError` 意味着「没有响应存在」，所以它归流式路径是自洽的。

参数校验只有一行（`ghc_api/main.py:288-295`）：

```python
            state.responses_pre_header_grace = min(
                max(0.0, float(config['responses_pre_header_grace'])), 5.0)
```

注释解释了为什么这一行就够：负数会让 `queue.Queue.get(timeout=...)` 抛 `ValueError`（每个流式请求变 500），`inf` 抛 `OverflowError`，`nan` 会**静默地**关掉超时退回旧的阻塞行为；而 `max(0.0, nan)` 是 `0.0`、`max(nan, 0.0)` 是 `nan`，所以参数顺序有意义。这条「防御性散文应当变成可执行代码」的处理方式本身值得学（决策文档 §7 明说这一行取代了原先一整张表）。

默认值 0.5 秒的理由（决策文档 D3，`:62-72`）：跨区 RTT 常在 50–200 ms，grace 太小会让「保留真实状态码」这条路**静默地永不生效**；观测到的客户端约 1 秒放弃，所以 grace 必须 < 客户端最短读超时。两侧失效模式不对称 —— 太小是静默失败，太大是可见且有界的失败，所以默认值偏大。

权重：**强到可直接采纳**（机制、校验、默认值理由三者都有代码或同仓决策文档支撑；注意「0.5 是占位值不是实测值」是文档自述，见 `:140`）。

### 2.5 三条流式路径的 pre-header 语义不一致（该项目自己承认的缺陷）

- `/v1/responses`：等 `grace`（0.5 s）。`routes/openai.py:1743`
- `/v1/messages` 走 Responses 兼容路径：等 `grace`。`routes/anthropic.py:1732-1737`
- `/v1/messages` direct passthrough：**等整整一个 `sse_keepalive_interval`（默认 30 s）**。`routes/anthropic.py:2156`

```python
                        response = pending_response.get(timeout=state.sse_keepalive_interval)
```

决策文档开放项 4（`:163-165`）原话：「Three streaming paths, three error semantics … Converge them or document why they differ.」——即这是已知未收口的问题。direct 路径的代价是：客户端在最坏情况下 30 秒收不到任何字节，而这正是 grace 机制存在的理由。

权重：**强到可直接采纳**（代码 + 项目自述双证）。对我方的意义是：**这类「新机制只接到了一条路径上」的漏接是常态**，值得在我方做同类改动时专门反查所有入口。

### 2.6 退避睡眠期间不发 keepalive（已知缺陷）

连接重试的退避在生成器内部直接 `time.sleep(min(2 ** conn_attempt, 8))`（`routes/openai.py:267`、`routes/anthropic.py:613`、`:1782`），最长 8 秒，期间**不产出任何 keepalive**。决策文档开放项 3（`:160-162`）：「Backoff sleeps are silent … breaks the promise of a short configured interval.」

权重：**强到可直接采纳**。我方若有退避，同样要让退避期间继续发保活 —— 这是「守卫读错侧」的近亲：退避是代理自身造成的下游静默，跟上游无关。

### 2.7 后台请求的所有权与可见性

`BackgroundResult.cancel()`（`sse/keepalive.py:92-112`）在一把锁下决定「谁拥有那个最终会返回的响应」：取消方若抢到已入队的结果就负责 `close()`，否则由生产者线程发现 `_cancelled` 后 `close()`。决策文档 D5（`:95-104`）记录了实测：20 个被取消的请求产生了 20 个 `iter_lines` 从未被调用、`close` 从未执行的响应。

调用位置：

- `routes/openai.py:359-363`：`finally:` 里 cancel + close。**正确**。
- `routes/anthropic.py:1542-1544`：`finally:` 里有条件 cancel（`if not cache_finished and response is None and active_pending is not None`）。
- `routes/anthropic.py:539-741` 的 `_stream_pending_direct_anthropic_request.generate()`：**既没有 `finally`，也没有任何 `cancel()` 调用**。GeneratorExit 分支（`:710-712`）只更新缓存状态就 `return`。所有权空洞在这条路径上仍然存在（决策文档 §4 `:148-149` 说 cancel 只应用到了 `openai.py`；此后 anthropic 的 Responses 路径补上了，direct 路径没有）。

同时 D6（`:106-127`）做了一个我很欣赏的决定：**不为一个还没观测到的风险加信号量，而是先把占用量计数出来** —— `bg.<label>.{started,inflight,cancelled,orphan_closed}`（`sse/keepalive.py:46-47`、`:64`、`:104`、`:111`），并**预先写死了触发建设的阈值**（peak inflight < 16 就什么都不做；peak > 64 或 cancelled > 10/min 才加并发上限与专用 pre-header 超时）。这是「先测量再建缓解措施」的干净样板。

权重：**强到可直接采纳**（cancel 的三处调用位置为代码事实；D6 的阈值表是文档主张，其价值在方法而非数字）。

---

## 3. 加密内容剥离重试（显式有损路径）

先纠正任务描述里的一处错配：`ghc_api/tool_call_recovery.py` **不是**加密内容剥离重试。它是另一件事（见 §4）。加密内容剥离在 `ghc_api/utils.py` + 两个路由里，测试是 `tests/test_encrypted_content_retry.py`。

### 3.1 触发条件

`ghc_api/utils.py:360-386`，判据极窄：

```python
def is_encrypted_content_parse_error(status_code: int, response_text: str) -> bool:
    if status_code != 400:
        return False
    try:
        error = json.loads(response_text).get("error", {})
    except (AttributeError, json.JSONDecodeError, TypeError):
        return False
    if not isinstance(error, dict) or error.get("code") != "invalid_request_body":
        return False
    ...
    return (
        (
            normalized.startswith("the encrypted content ")
            and normalized.endswith(
                " could not be verified. reason: encrypted content could not be decrypted or parsed."
            )
        )
        or normalized == "encrypted function output content could not be decrypted or decoded."
    )
```

要求同时满足：HTTP 400 + 响应体是 JSON + `error.code == "invalid_request_body"` + message 匹配两种精确文案之一（大小写归一后前缀/后缀匹配，或整串相等）。窄到近乎脆 —— 上游改一个字就失效 —— 但换来的是「绝不误触发一条有损路径」。测试 `tests/test_encrypted_content_retry.py:71-93` 专门列举了不该匹配的变体。

另外这条路整体是**默认关闭**的：`state.auto_remove_encrypted_content_on_parse_error: bool = False`（`ghc_api/state.py:90`），README 给的理由是「有损 + 多花一次上游请求」。

### 3.2 剥离什么、保留什么

`ghc_api/utils.py:448-498`，`remove_encrypted_content_items()`。核实 README 的说法（README 第 222-232 行附近「Encrypted Content Recovery」）—— **属实，且代码比 README 说得更细**：

- 携带 `encrypted_content` 的**工具输出项**（`function_call_output` / `custom_tool_call_output` / `computer_call_output` / `local_shell_call_output`，见 `:348-353`）→ **保留该项**，只剥掉加密块，并在剥空时塞占位文本（`_ensure_tool_output_present`，`:434-445`，占位串 `"[ghc-api] tool output omitted: encrypted content could not be decrypted upstream"`）。docstring 直接写了理由：「Dropping a whole `function_call_output` would orphan its `function_call` and make the retry fail with "No tool output found for function call"」。
- 其他携带加密内容的项（reasoning、message 等）→ **整项删除**。
- **如果被删的是一个工具调用本身**（`function_call` / `custom_tool_call` / `computer_call` / `local_shell_call`，`:341-346`），则记下它的 `call_id`，第二趟把配对的输出也删掉（`:485-496`）。这是反方向的配对维护，README 也提到了。
- 递归扫描有深度上限 `_MAX_ENCRYPTED_SCAN_DEPTH = 32`（`:339`），防病态嵌套。列表元素里只要**任一层**含 `encrypted_content` 就整块丢（`:423-425`，注释：「A content block that carries encrypted data is meaningless once the payload is gone」）。

四条行为都有对应测试：`test_function_call_output_is_sanitized_not_dropped`、`test_emptied_function_call_output_gets_placeholder`、`test_dropping_a_tool_call_also_drops_its_output`、`test_deeply_nested_payload_does_not_recurse_forever`。

### 3.3 重试与失败后的行为

`ghc_api/routes/openai.py:1808-1828`（同步路径）与 `:304-326`（pre-header 流式路径）各有一份**几乎相同但已经开始漂移**的实现。关键控制流：

- `encrypted_content_retry_attempted` 布尔守卫 → **每请求至多一次**（测试 `test_retry_happens_at_most_once`）。
- 重试用 `continue` 回到 `while conn_attempt <= connection_retries` 而**不递增 `conn_attempt`** → 核实 README「the retry does not consume the connection-retry budget」的说法：**属实**。
- `removed_count > 0` 才重试；一个也没删就不重试，直接把 400 还给客户端。
- 重试后再次失败 → 不再判断，按普通错误返回给客户端（原样透传上游状态码与响应体）。
- 每次触发都计数 `counters.incr("mod.encrypted_content_removal")` 并打日志。
- 重试前 `response.close()` 释放上游连接（`:1826`，注释：「The error body was already consumed; release the upstream connection before issuing the retry」）。

**只覆盖 OpenAI 格式端点**。README 明说 Anthropic Messages 兼容路径不适用，因为那条路上 reasoning 状态是由客户端携带的（我方的 reasoning carrier 同理），代理只做字节等价重试。代码侧印证：`handle_responses_anthropic_request` 的 docstring（`routes/anthropic.py:1569-1573`）写着「never retries a protocol error with fields removed. Only byte-identical connection retries are permitted」。

决策文档 §3（`:137-139`）自己点名了这块的债：「Retry / encrypted-content logic is duplicated between the route loop and the pending generator. Drift has already started: the generator dropped the `Received error response ...` and encrypted-content warning prints.」—— 我核对了，确实：`routes/openai.py:1817-1818` 有两条 warning print，`:312-317` 那份没有。

权重：**强到可直接采纳**（触发条件、配对保全、预算不消耗、单次上限均为代码事实 + 测试）。

---

## 4. `tool_call_recovery.py` 是另一回事：泄漏的 tool call 文本恢复

`ghc_api/tool_call_recovery.py:1-26` 的模块 docstring 描述的问题是：Copilot 的 Claude `/v1/messages` 端点偶发地**服务端 tool-call 解析器中途失败**，把 `<function_calls>` 包裹层部分剥掉、把 `antml:` 命名空间前缀去掉，然后把剩下的 tool call 当作 `text_delta` 流出来，并给 `stop_reason: "end_turn"`。依赖结构化 `tool_use` 块的客户端（Claude Code）就把工具调用当文字渲染，agent loop 卡死。

`LeakedToolCallTransformer` 是个有状态的 SSE 转换器，默认关闭（`state.enable_tool_call_recovery = False`，`state.py:50`），关闭时是**真正的 no-op**（`process()` 第一行就走 `_passthrough`，`:167-168`；基类刻意不 import 这个模块，`sse/base.py:16-17`）。

值得记的一点手艺：`_is_viable_danger_prefix`（`:60-121`）+ `_danger_holdback`（`:444-454`）实现了一个**流式回退保留**——把「还可能长成 `<invoke name="...">` 的最长后缀」扣住不发，其余作为散文下发。这解决的是「构造跨 chunk 边界」这个经典问题，且不需要缓冲整块。散文里提到 `<invoke>` 的误判用「紧邻反引号则视为行内代码」来消歧（`:438-442`）。流末未闭合的 invoke 会被 `_finalize_incomplete_invoke()` 尽力兑现成一个 tool_use（`:319-325`）。

这与我方的关系是间接的：它是**上游协议缺陷的下游修补**，属于「上游行为要靠录制而不是想象」的典型案例，但触发条件依赖 Copilot 的 Claude passthrough 端点，我方主路径（Responses 上游）不经过它。

权重：**是个倾向、需更多样本**（机制清楚，但相关性依赖我方是否也走 Claude passthrough）。

---

## 5. Token 刷新的并发安全与失败传播

### 5.1 并发形态

状态（`ghc_api/state.py:29-33`）：一把 `threading.Lock` + 四个 last-attempt/last-success/last-succeeded/last-error 观测字段。

双检查（`ghc_api/api_helpers.py:220-223` + `:149-152`）：

```python
def ensure_copilot_token() -> None:
    """Ensure we have a valid Copilot token"""
    if not state.copilot_token or time.time() >= state.token_expires_at - 60:
        refresh_copilot_token()
```

```python
def refresh_copilot_token(force: bool = False) -> None:
    with state.token_lock:
        if not force and state.copilot_token and time.time() < state.token_expires_at - 60:
            return
```

- 快路径（`ensure_copilot_token`）**无锁读**两个字段。在 CPython 下这是撕裂不了的单次属性读，两个字段之间的不一致最坏只会导致一次多余的 `refresh_copilot_token()` 调用，而后者在锁内重新判定后直接 return。**多线程同时发现过期 → 只有第一个真正刷新，其余在锁上排队后看到新 token 直接返回。**
- 提前量 60 秒（`token_expires_at - 60`）避免「刚好在有效期边缘发出请求」。
- 过期时间来自上游的 `refresh_in` 而不是 `expires_at`（`:176`，`data.get("refresh_in", 1800)`）。

**代价**：整个 HTTP 请求（`timeout=30`）在锁内进行（`:160-164`）。刷新期间所有需要 token 的线程全部阻塞，最长 30 秒。这是有意的串行化（避免刷新风暴），但它会把「上游 token 端点慢」放大成「全服务停顿」。waitress 默认 16 线程（`state.py:150`），这个停顿会吃掉全部工作线程。

一个已避开的坑：`GitHubDeviceFlowManager._complete()`（`token_manager.py:273-280`）先在 `with state.token_lock:` 块里清空 token，**离开该块之后**才调 `refresh_copilot_token(force=True)`。`threading.Lock` 不可重入，写在块内就会自死锁。

### 5.2 失败传播

`refresh_copilot_token` 的异常处理（`api_helpers.py:181-198`）：记录 `token_refresh_last_succeeded = False` 与错误串 → 写结构化 `error.log`（`utils.py:50-80`，响应体截断到 64 KiB，且**不记录鉴权头**）→ 打印一段面向人的修复指引（`--delete-github-token` / `--github-device-login`）→ **`raise` 原样上抛**，不吞。

调用点的处理各不相同，这是可以借鉴的地方也是要小心的地方：

- 连接重试分支里的 `ensure_copilot_token()`（`routes/openai.py:1835`、`:259`，`routes/anthropic.py:1374`、`:610`、`:2205`）**没有单独 try**，刷新失败会把原始的 `ConnectionError` 换成 `RuntimeError` 继续上抛，最终落到路由的兜底 `except Exception` → 500，或落到生成器的 `except Exception` → 一个 SSE `error` 事件。**原始的连接失败信息在这里被覆盖了**。这是个真实的诊断损失，不算严重但值得我方避免。
- 启动阶段允许 token 刷新失败而不阻止服务起来（有测试 `tests/test_token_management.py:277 test_startup_survives_github_502`）。
- 面板暴露 last-attempt/last-success/last-error 供人排查（`state.py:30-33` 的字段就是为此存在的）。

权重：**强到可直接采纳**（并发形态、双检查、锁内网络调用、不可重入陷阱、异常不吞，均为代码事实）。「锁内做网络 IO 会放大成全服务停顿」是我的推断，代码形态确定但未见该项目的实测 —— 标 **是个倾向、需更多样本**。

---

## 6. 超时分层

### 6.1 实际存在的层

| 层 | 是否存在 | 值 / 位置 |
|---|---|---|
| 连接超时（connect） | **与读超时共用一个值** | `timeout=state.upstream_read_timeout` 单值传给 requests，`state.py:73-75` 的注释明说「passed to requests as a single value so it applies to both the connect and read phases」。默认 **1800 秒** |
| 首字节 / 响应头超时 | **没有专用超时**，只有 `responses_pre_header_grace`（0.5 s）作为**分流阈值**而非超时 —— 超过 grace 不是失败，只是改走流式路径，后台 POST 仍可继续跑满 1800 秒 | `routes/openai.py:1743-1747`；决策文档 D6 `:106-113` 明确承认「A cancelled client now frees the WSGI thread while the background POST keeps running for up to `upstream_read_timeout` (default 1800 s)」 |
| 读超时（帧间） | 有，`upstream_read_timeout` = 1800 s。requests 的读超时语义是**两次读之间**，不是总时长 | `state.py:75` |
| 整体请求超时（总时长） | **完全没有**。任何路径都没有 deadline | 全仓 `rg` 未见 |
| 下游保活间隔 | `sse_keepalive_interval` = 30 s，0 关闭 | `state.py:79` |
| WSGI 通道超时 | `channel_timeout = max(300, upstream_read_timeout)`，即默认 1800 s | `main.py:499-516` |
| 辅助请求（token / models / device flow） | 固定 `timeout=30` 硬编码，不可配 | `api_helpers.py:163`、`:207`；`token_manager.py:85`、`:126` |
| Web IQ REST | `webiq_timeout=30`，browse `120`，classic `60` | `state.py:115-119`，`webiq.py:236-244` |
| Web IQ MCP | **唯一使用 `(connect, read)` 元组的地方**：GET（长连事件通道）故意 `(connect_timeout, None)` 即读无上限；其余方法 `(connect, webiq_mcp_timeout=120)` | `webiq.py:354-365` |

### 6.2 「上游慢」与「上游挂了」有没有区分？

**基本没有，只有一处例外。**

- 主 LLM 路径上，`ReadTimeout` 与 `ConnectionError` 被**放在同一个 except 元组里**，处理完全相同 —— 重试、退避、最终 504。全仓一致：`routes/openai.py:1831`、`:250`；`routes/anthropic.py:606`、`:1361-1364`、`:1437`、`:2202`；`sse/base.py:359`。既然读超时是 1800 秒，「慢」实际上要慢到半小时才会被当成「挂了」。
- 唯一的例外在 Web IQ：`webiq.py:298-301` 把 `Timeout`/`ConnectionError` 归为 504，而其余 `RequestException` 归为默认状态；`webiq.py:381-389` 把上游 401/403 单独翻译成 503 + 说明「是本服务器的 key 被拒，不是你的请求有问题」。这个「错在谁那边」的分类是有价值的。
- 另一个方向的区分做得不错：**pre-header grace 的分流本质上就是在区分「还没有响应」与「已有响应」**（决策文档 D1），这比区分快慢更有用。

对我方的直接含义：如果要做「上游慢 vs 上游挂了」，`upstream_read_timeout=1800` 这种量级的单一读超时是无法承担该职责的，需要单独的首字节超时 + 帧间停滞阈值，而 ghc-api 没有提供可抄的现成实现。

权重：**强到可直接采纳**（各层的有无与取值均可逐行核对）。

---

## 7. MCP 并发上限 → 503 + `Retry-After`

`ghc_api/routes/webiq.py:62-86` 是一个**非阻塞**的进程内计数器（不是 `threading.Semaphore`，因为要的是 try-acquire 语义而非排队）：

```python
class _MCPStreamLimiter:
    """Non-blocking process-local cap for thread-occupying MCP streams."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0

    def try_acquire(self, limit: int) -> bool:
        with self._lock:
            if self._active >= max(1, int(limit)):
                return False
            self._active += 1
            return True
```

拒绝路径（`:428-448`）：

```python
    if not _mcp_stream_limiter.try_acquire(
        state.webiq_mcp_max_concurrent_streams
    ):
        counters.incr("webiq.mcp_error")
        message = (
            "Web IQ MCP concurrency limit reached; retry after an active "
            "stream closes."
        )
        response, status = _error_response(message, 503, "mcp")
        response.headers["Retry-After"] = "1"
```

设计意图很清楚（`state.py:120-124` 注释）：MCP 的 Streamable HTTP **GET 故意没有读超时**（长连事件通道），所以必须有一个别的机制阻止它们吃光 waitress 线程池；上限默认 4，线程池默认 16。**「一个不设超时的长连，必须由并发上限而非超时来兜底」——这个配对关系是这份代码里最值得抄走的一条设计原则。**

同样值得注意的是它选择了**立即 503 + `Retry-After: 1`（快速失败）而不是排队**。README（第 540 行附近）的措辞是「and `Retry-After` instead of queueing behind streams」。对客户端而言，一个立刻到达的 503 比一个悬着的连接更有用。

### 7.1 一个我认为存在的缺陷：槽位可能永久泄漏

`try_acquire` 在路由函数体里执行（`:428`），而 `release()` 只出现在三个同步异常分支（`:458`、`:473`）和**生成器的 `finally:`**（`:526`）里。若 Flask/waitress **从未开始迭代**那个生成器（客户端在 WSGI 开始迭代前就断开、或框架内部在迭代前抛异常），生成器的 `finally` 不会执行 —— 我在本机验证过这条 Python 语义：

```
$ python3 -c "..."   # 未启动的生成器 close()
not started -> []
started -> ['finally']
```

未启动的生成器 `close()` 时函数体从未进入，`finally` 不运行。槽位于是永久 -1，累计 4 次之后**所有 MCP 请求永远 503**。

要说清楚的是：**代码形态是确定的，可达性未被证明**（waitress 在正常路径下几乎总会至少 `next()` 一次）。若我方采用同类模式，把 acquire 也移进生成器体内、或者用带最终一致性回收的方式，是更稳的形状。

权重：**是个倾向、需更多样本**（语义已验证，触发路径未验证）。

---

## 8. 明显做错或笨重、不该照抄的地方

### 8.1 非 2xx 响应在 direct Anthropic 路径上被静默重放 4 次

`handle_direct_anthropic_request`（`ghc_api/routes/anthropic.py:2110-2312`）。`for attempt in range(max_retries + 1)`（`:2137`，`max_retries = 3`）的非 2xx 分支里，只有 web-search-unsupported（`:2276-2282`）和 orphaned-tool-result（`:2284-2307`）两种情况会 `continue`；**其它任何错误（含普通 400、429、401）走到循环体末尾没有 `break`，直接进入下一轮 attempt**，把**同一个请求体**再发一遍，共 4 次。

更糟的是 `headers` 在循环外只算了一次（`:2130-2131`），所以四次尝试共用同一个 `X-Request-Id` —— 这与 Responses 路径刻意每次重建 headers 的做法（`:1689-1696`）正好相反。

决策文档开放项 5（`:166-170`）已把它记为「One-line fix, unrelated to this PR」，但在 HEAD 上仍未修。**不要照抄这条路径的重试循环结构。**

权重：**强到可直接采纳**（代码 + 项目自述双证）。

### 8.2 重试/加密剥离逻辑在同步路由与流式生成器之间复制了两份且已开始漂移

见 §3.3。这是 pre-header 机制被塞进既有路由后的结构性后果：一个「等 header」的分叉把整段错误处理逻辑劈成了两条必须手工保持同步的路径。决策文档 §3、§4 都承认了，并明说「No shared helper for the duplicated retry logic — a separate refactor」。

**我方若要做 pre-header grace，应当先把「发请求 + 处理错误 + 重试」抽成一个可以在两种驱动方式（同步返回 / 生成器 yield）下复用的形状，再加分叉**，而不是像这里一样先分叉再欠债。

权重：**强到可直接采纳**。

### 8.3 keepalive 守卫读上游侧

见 §2.2。这是本次调研里对我方最有价值的一条负面样本。

### 8.4 退避睡眠期间静默

见 §2.6。

### 8.5 三条流式路径三种 pre-header 语义

见 §2.5。

### 8.6 direct Anthropic 的 pending 生成器缺少 `finally` / `cancel()`

见 §2.7。同一个所有权修复只落到了三条路径中的两条。

### 8.7 一些小的粗糙处（仅存档）

- `except:` 裸捕获：`routes/openai.py:1882`、`routes/anthropic.py:2252`（`try: result = response.json() except: ...`）。
- 错误日志 `log_error_request`（`utils.py:31-47`）**没有 try 保护**、**不截断响应体**、每次请求都同步 `open(...,"a")` 写盘；相邻的 `log_upstream_error` 反而做了截断和异常保护。两个函数标准不一致。
- `_danger_holdback`（`tool_call_recovery.py:444-454`）对缓冲区是 O(n²)（每轮 `buf[i:]` 切片）。实际缓冲区很小所以无害，但形状本身不好。
- `BackgroundResult._close_result` 里 `except Exception: pass`（`sse/keepalive.py:81-84`），带注释说明是最佳努力清理不应掩盖原始错误 —— 这条**有注释，属于可接受的吞异常**，列在这里只是为了对照 8.7 的其余几条。
- 优雅停机只覆盖 token usage reporter 的落盘（`token_usage_reporter.py:137-175` 注册 SIGINT/SIGTERM/SIGBREAK + atexit，且保留并链式调用前一个 handler）。**没有任何针对在途流式请求的排空逻辑，没有 socket activation 相关的东西。** 我方的 systemd 部署目标在这份代码里找不到可借鉴的实现。

权重：**仅存档、不据以决策**（8.7 各条；其中「无优雅停机可借鉴」是有用的否定结论，标 **强到可直接采纳**）。

---

## 9. 结论表

| # | 发现 | 我方是否值得借鉴 | 理由 |
|---|---|---|---|
| 1 | 早期失败重试的判据 = 白名单式布尔闸门 `output_started`，非序幕事件一出现即永久关闭重试 | **值得** | 判据简单、可测、不需要字节计数；「malformed JSON 也算内容因而提交」的 fail-safe 取向直接可抄。我方是否已实现 **需主会话核对** |
| 2 | 重试时重建 headers + 先 `ensure_copilot_token()`，每次尝试新的 `X-Request-Id` | **值得** | 复用 headers 会重发刚被换掉的 token 并让多次尝试共用 request id，两个后果都实测过 |
| 3 | 包装器绝不读 `stream=True` 响应的 `.text`（property + 专门的回归测试） | **值得** | 这是个会把整条流变成缓冲请求的静默陷阱，成本极低的一条守卫 |
| 4 | 早期失败重试**不覆盖**序幕阶段的 `ConnectionError` | **存疑** | 该处空洞是真的，但补上是否有收益取决于我方观测到的早期失败形态；无数据前不建议动 |
| 5 | keepalive 计时器读上游活跃度 | **不适用（反面样本）** | 我方是全量块级交付，两侧脱钩是普遍情形而非边角；照抄必然装反守卫。应改为「下游最后一次实际写出字节」驱动，另设独立的上游停滞探测 |
| 6 | pre-header grace：按「有没有拿到 HTTP 响应」而非「快不快」分流 | **值得** | 保住 429/401 的真实状态码是硬收益；分流判据本身也比超时判据更稳。我方是否已实现 **需主会话核对** |
| 7 | grace 的一行钳制 `min(max(0.0, x), 5.0)` 及其参数顺序 | **值得** | `nan` 会静默关掉超时、负数与 `inf` 会让每个流式请求 500；一行代码替掉一张说明表 |
| 8 | grace 默认 0.5 s 及「太小静默失败、太大可见失败」的不对称论证 | **值得（论证），存疑（数值）** | 论证方式可直接复用；0.5 是该项目自述的占位值而非实测值，我方数值要自己定 |
| 9 | 退避睡眠期间不发 keepalive | **不适用（反面样本）** | 退避是代理自身造成的下游静默，与上游无关，属于 #5 同一族错误 |
| 10 | 三条流式路径三种 pre-header 语义（新机制只接到部分入口） | **不适用（反面样本）** | 给我方的操作性提示：同类改动后专门反查所有流式入口，别信「已实现」 |
| 11 | `BackgroundResult` + `cancel()` 的单锁所有权移交 | **值得** | 客户端提前断开时后台响应无人认领是实测过的泄漏（20/20）。前提是我方也把上游请求移出请求线程 —— **需主会话核对** 我方是否已是 async 模型（若是 asyncio，这套线程 + queue 的形状不适用，语义仍适用） |
| 12 | 「先加计数器观测，达阈值再建并发上限」并预先写死决策阈值 | **值得** | 与我方「拒绝为任务额外搭建证明基础设施」一致：把缓解措施推迟到观测之后，且推迟是有条件、可被推翻的 |
| 13 | 加密内容剥离：工具输出**保留并占位**、工具调用被删则连带删其输出 | **值得** | 直接对应我方 Responses 上游的同类 400。README 的说法经代码与测试核实属实 |
| 14 | 该有损路径默认关闭、判据窄到近乎脆、每请求至多一次、不消耗连接重试预算 | **值得** | 四条约束合起来才让一条有损路径可接受，缺一条都不行 |
| 15 | 加密剥离逻辑在同步路由与流式生成器里复制两份并已漂移 | **不适用（反面样本）** | 我方若做 pre-header 分叉，先抽共用形状再分叉 |
| 16 | Copilot token 双检查 + 60 s 提前量 + 锁内刷新 + 异常上抛不吞 | **值得** | 并发形态正确且简单；`GitHubDeviceFlowManager` 那个「不可重入锁必须在块外调用刷新」的陷阱尤其值得记 |
| 17 | 刷新时整个 HTTP 调用在锁内（最长 30 s 全服务停顿） | **存疑** | 串行化本身是对的，但阻塞全部工作线程的代价在我方线程/协程模型下未必相同；若我方是 asyncio，同样的语义可以用一个共享 future 实现而不阻塞 |
| 18 | 连接重试分支里 `ensure_copilot_token()` 无 try，会用刷新异常覆盖原始连接异常 | **不适用（反面样本）** | 诊断信息损失，我方避免即可 |
| 19 | 超时只有单一 `upstream_read_timeout=1800` 同时充当 connect + read；无整体 deadline；`ReadTimeout` 与 `ConnectionError` 处理完全相同 | **不适用（反面样本）** | 这个量级的单一读超时无法承担「上游慢 vs 上游挂了」的区分。我方若需要该区分，得自己设首字节超时 + 帧间停滞阈值 |
| 20 | 「不设读超时的长连，必须由并发上限而非超时兜底」（MCP GET `(connect, None)` + `webiq_mcp_max_concurrent_streams=4` vs 线程池 16） | **值得** | 配对关系本身是可迁移的设计原则，与具体协议无关 |
| 21 | 超限立即 503 + `Retry-After: 1`（快速失败）而非排队 | **值得** | 立刻到达的 503 对客户端比悬着的连接更有用；`Retry-After` 让退避可计算 |
| 22 | MCP 限流槽位在生成器 `finally` 里释放，未启动的生成器 `finally` 不执行 → 可能永久泄漏 | **不适用（反面样本）** | Python 语义已本机验证；可达性未证。我方若用同类模式，acquire 也放进生成器体内 |
| 23 | direct Anthropic 路径对任意非 2xx 静默重放 4 次、四次共用一个 `X-Request-Id` | **不适用（反面样本）** | 项目自己记为「一行就能修」但 HEAD 仍未修。绝不照抄该重试循环结构 |
| 24 | `docs/decisions/RESPONSES_PRE_HEADER_KEEPALIVE.md` 的写法：决策 + 明确记录「刻意没做什么」+ 开放项 + 过程教训（含一次被撤回的测量） | **值得** | 尤其 §7「当测量说『没有差异』时，先验证测量装置能不能观测到那个差异」以及「变异测试每一条新回归测试，还能通过的测试什么都没守住」两条 |
| 25 | 优雅停机只覆盖 usage reporter 落盘；无在途流排空、无 socket activation | **不适用** | 我方的 systemd/socket activation 目标在这份代码里没有可借鉴实现，需另找样本 |

---

## 10. 若只带走三条

1. **keepalive 守卫必须由「我方最后一次真正写出下游字节」驱动**。ghc-api 在块级/半块级翻译路径上装反了这个守卫，而且没有测试、也没意识到。我方是全量块级交付，这个坑更大更普遍。
2. **pre-header 的分流判据是「有没有拿到 HTTP 响应」，不是「快不快」**。这一条决定了 429/401 能不能保住真实状态码，也决定了 `ConnectionError` 该归哪边。
3. **有损恢复路径要同时满足四条约束才算可接受**：默认关闭、判据窄到不会误触发、每请求至多一次、不消耗其它重试预算 —— 而且配对结构（工具调用 ↔ 工具输出）要双向维护。
