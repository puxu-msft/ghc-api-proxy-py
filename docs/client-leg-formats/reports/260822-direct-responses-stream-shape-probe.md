与结论
本项目现状：客户端直连 POST `/responses`（入站即 OpenAI Responses、模型只广告 `/responses`、路由不翻译）并要求 `stream: true` 时，客户端实际收到的 SSE 事件名是 **Anthropic 形状**（`message_start` / `content_block_start` / `content_block_delta` / `content_block_stop` / `message_delta` / `message_stop`），**不是** Responses 形状（`response.*`）。这一点已用真实录制帧实测确认，权重：**足够作为判断依据（strong enough to act on）**——静态读码 + 真实上游字节回放 + 正样本对照三者一致，且探针已证明命中目标路径与目标模型。

这是与 `/chat/completions` 直连同源的「事件名形状错配」缺陷：无论入站/目标格式是什么，`stream_delivery` 都无条件按 Anthropic SSE 事件名重新成帧。一个只认 `response.*` 事件名的 OpenAI Responses SSE 客户端拿到这个流大概率无法解析。

## 探针搭法

一次性脚本：`/home/xp/.claude/jobs/104f3935/tmp/probe_direct_responses_stream_shape.py`（未写入仓库，未提交）。

- 沿用 `tests/int/test_pipeline_app.py` 的 `make_client`/`make_provider` 写法：`MockTransport` 接管所有出站 HTTP，入口固定生产的 `create_pipeline_app`。
- 目录（catalog）新增 `resp-model`，只广告 `["/responses"]`，使 `decide_route`（`src/app/pipeline/routing.py`）解析出 `inbound_format == target_format == OPENAI_RESPONSES`、`translation_required == False`；`claude-model` 只广告 `["/v1/messages"]` 作正样本对照；`cc-model` 只广告 `["/chat/completions"]` 用于非流式旁证。
- 上游流式字节**不是手写的**，取自 `tests/int/cassettes/anthropic_to_responses_stream.json` 里 `POST /responses` 的那条 interaction（28 个 chunk 拼接，26736 字节），事件名序列为：

  ```
  response.created, response.in_progress,
  response.output_item.added, response.output_item.done,
  response.output_item.added, response.content_part.added,
  response.output_text.delta, response.output_text.delta,
  response.output_text.done, response.content_part.done,
  response.output_item.done, response.completed
  ```

  探针跑前先断言这段原始字节里没有任何 Anthropic 事件名、且确实含 `response.*` 事件名——防止「样本本身就不够格」的假阳性。

## 路径证明

- 直连 `/responses` 流式：`seen[-1].url == "https://copilot.example/responses"`，即 mock 上游确实收到了 `/responses` 请求；日志行打印 `openai-responses/resp-model`，与路由（未翻译）一致。
- 直连 `/chat/completions` 非流式：`seen[-1].url` 命中 `/chat/completions`。
- 直连 `/responses` 非流式：`seen[-1].url` 命中 `/responses`。

三处均先断言命中路径，再读取客户端观测到的内容，避免「探针没跑到目标分支却读到了旧数字」。

## 正样本对照（事件名的分辨力）

同一 harness 跑 `/v1/messages`（Anthropic 客户端，`claude-model`）流式请求，上游给出的是手写但形状真实的 Anthropic SSE（`content_block_start`/`content_block_delta`/`content_block_stop`/`message_delta`/`message_stop`）。客户端收到的事件名序列：

```
message_start, content_block_start, content_block_delta, content_block_stop,
content_block_start, content_block_delta, content_block_stop,
message_delta, message_stop
```

这证明「事件名」这个观测量在本 harness 下是有分辨力的：Anthropic 路由确实收到 Anthropic 事件名，不是探针本身的缺陷让什么请求都长一个样。

## 直连 `/responses` 流式：客户端实际收到的事件名序列

```
message_start, content_block_start, content_block_delta, content_block_delta,
content_block_stop, content_block_start, content_block_delta, content_block_stop,
message_delta, message_stop
```

`content-type: text/event-stream; charset=utf-8`，body 长度 14850 字节。首 800 字节：

```
event: message_start
data: {"type":"message_start","message":{"id":"e3287e2a-b814-4aae-ac36-6a9f2e768aa7","type":"message","role":"assistant","model":"resp-model","content":[],"stop_reason":null,"usage":{"input_tokens":0,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":"","signature":"ghc-api-proxy:synthetic-reasoning:v1:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50IjoiVXRVb2VPZ3ZtZFZ2dGQ3cXI1ZmRjWnljSEE5Z1BVQ2tFMENxVE9FbzZGN1dXN3NTRFY3dTA4czl1ZGJLMy9JcloxQUM1ZHZVdW1NY1BxTmp3QkRmcnVEZ0UxUzV2dVo4djluVlZzaUpaM0RFQnlQQ3F1cDhkRkdTLzVDSkgwNjdsUEJwRXR0UklocXMwckVibEtQYTdPUlVwWnZpMEswc09Manl6U2lpdEhzb25KQnhNTmRLV01JMW9GWXZwWU1IQldiQXlCMnphdnNwL2huNHByOXBHM'...
```

`content_block: {"type": "thinking", ...}` 上还带着本项目自制的 reasoning carrier（`ghc-api-proxy:synthetic-reasoning:v1:...`），说明 upstream 的 `response.*` 事件确实先被 `ResponsesAssembler`（`src/app/server/handler.py:527-534`）正确解析成了 `CompletedBlock`，只是随后被无条件按 Anthropic 词汇重新成帧——`assembler_for`/`dialect_for` 只管「怎么读」，不管「怎么写」。

结论：**直连 `/responses` 流式，客户端拿到的事件名是 Anthropic 的**，不是 Responses 的。

## 缺陷定位（文件:行号）

- `src/app/pipeline/delivery/stream.py:303` `yield message_start(message_id, model).encode()` —— 无条件写 Anthropic 的 `message_start` 帧，`stream_delivery`（174 行起）签名里没有任何「目标/入站格式」或 `ReplyDialect` 参数可供分支。
- `src/app/pipeline/delivery/stream.py:306` `for frame in block_frames(block, signature_compat=settings.signature_compat):` —— 同上，逐块套用 Anthropic 事件名。
- `src/app/pipeline/delivery/stream.py:324` `for frame in terminal_frames(...)` —— 终止帧同样无条件走 Anthropic（`message_delta`/`message_stop`）。
- `src/app/pipeline/delivery/anthropic_sse.py:30` `message_start`、`:85` `block_frames`、`:154` `terminal_frames` —— 这三个函数本身就是 Anthropic 专用的成帧器，硬编码 `event: message_start` / `content_block_start` / `content_block_delta` / `content_block_stop` / `message_delta` / `message_stop`，函数名和模块名（`anthropic_sse.py`）都表明它们从未打算服务于 Responses 出站。
- `src/app/server/pipeline_app.py:569` 调用 `stream_delivery(...)` 处：外层已经拿到了 `assembler = assembler_for(handled)`（500 行）、也拿得到 `handled.route.target_format` / `dialect_for(handled)`，但传给 `stream_delivery` 的只有 `assembler`、`buffer`、`settings`、`message_id`、`model`、`replay`，没有把「入站/目标格式」这个决定成帧词汇的信息传下去。
- 对照：`src/app/server/handler.py:527-534` 的 `assembler_for` 已经按 `dialect_for(handled)` 正确二选一（`ResponsesAssembler` vs `AnthropicAssembler`），说明「解析」这一侧的格式感知是齐的；缺口只在「重新成帧发给客户端」这一侧——`stream.py`/`anthropic_sse.py` 没有对应的 `ResponsesAssembler` 的姊妹「Responses 出站成帧器」。

## 旁证：非流式路径

- `/chat/completions` 非流式：客户端收到的 body 与 mock 上游 body 逐字节相同（`resp.json() == mock_cc_body`），即非流式路径是**原样透传**，未被改写。
- `/responses` 非流式：同样逐字节透传（`resp.json() == mock_resp_body`）。

即缺陷只存在于流式路径；非流式直连不受影响。这也符合代码结构：非流式路径不经过 `stream_delivery`/`anthropic_sse.py`。

## 权重与限制

- 本次探针命中的是「入站 Responses、模型只广告 `/responses`、故不翻译」这一具体路由分支；已用 `seen[-1].url` 与日志行 `openai-responses/resp-model` 双重确认命中，属于「实测确认」而非推断。
- 上游流式字节取自真实录制（`anthropic_to_responses_stream.json`），覆盖了 `output_item.added/done` 配对、`content_part` 包裹、乱序 id 等真实特征，但该录制场景本身是"Anthropic 客户端 → Responses 上游"的翻译场景（cassette 文件名如此），录制时的**入站**是 Anthropic；本探针只借用了它的**上游出站**半段字节，重新接到一个"入站 Responses、不翻译"的路由上——这是探针本身构造的场景，不是该 cassette 原始录制场景的直接复用，这一点在报告中明示，避免误读为「该 cassette 场景本来就是直连 Responses」。
- 未测试工具调用（`tool_calls`）、多 output_item 并发、错误帧（`response.failed`/`response.incomplete`）等更复杂的 Responses 流形态是否也同样被误成帧；但缺陷根因在成帧函数本身无条件选择 Anthropic 词汇，与具体内容形态无关，据此判断该结论可外推到其余 Responses 流形态，权重为「强倾向，未逐一穷举」。

## 未采纳的备选解释

排除了「探针没有真正走到目标分支」的可能：`0. FIXTURE SANITY` 与两处 `seen[-1].url` 断言、以及日志行 `openai-responses/resp-model` 三重独立信号一致确认命中。也排除了「事件名本身在这套 harness 下没有分辨力」的可能：正样本对照（`/v1/messages`）证明同一 harness 下路由不同、事件名确实不同。
