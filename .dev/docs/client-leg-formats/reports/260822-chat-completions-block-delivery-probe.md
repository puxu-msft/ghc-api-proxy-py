# `/chat/completions` 流式块级交付——运行时验证

日期：2026-08-22
背景：核对 `.dev/docs/tmp/260822-ghc-api-conformance-direct-paths.md` 第 5、6 节提出的**未经运行时验证的推断**——`AnthropicAssembler` 只认 Anthropic/Responses 两种上游 SSE 形状，`/chat/completions` 流式很可能交付空块。本报告用实测把它坐实。

## 结论摘要（先给结果，权重：**实测证实**）

- **非流式 `/chat/completions` 工作正常**：untranslated 路由下 `response_payload`（`src/app/server/handler.py:428-441`）直接把上游 body 原样透传，与 assembler 无关，实测客户端拿到的 JSON 与上游返回的完全一致。
- **流式 `/chat/completions` 交付的是完全空的响应体**：状态码 200、`content-type: text/event-stream`，但客户端收到 **0 字节**——不是「block 变少」，是连一个字节的 SSE 帧都没有，也没有错误帧。原推断偏保守；实测显示后果比推断更严重。
- 定位到底层原因：这不是 assembler 一个环节的孤立缺陷，而是三处协同导致的静默空交付，见下方"断在哪"。
- 服务端日志能看出异常（`status=fail "upstream stream ended without a terminal event"`），但这条判断**不会**进入返回给客户端的 HTTP 响应体——客户端只看到一个开了又空关的连接，日志与客户端体验完全脱节。

## 探针怎么搭的

沿用 `tests/int/test_pipeline_app.py` 里已有的生产集成测试写法（`make_client`/`make_provider`），复制了这套已被项目自己用来测 `/v1/messages`、`/responses`、`/embeddings` 生产路径的 harness，未改动生产代码：

- 入口固定用 `create_pipeline_app`（`src/app/server/pipeline_app.py`），不是 `app_factory.create_app`。
- 上游是 `httpx2.MockTransport`（同一技术，项目集成测试的既有做法），不发真实网络请求，无需凭据。
- 在原有 `CATALOG` 基础上新增一个模型 `cc-model`，`supported_endpoints: ["/chat/completions"]`——只广告这一个端点。按 `src/app/pipeline/routing.py:66-110` 的 `decide_route`，这样的模型在 `inbound_format == OPENAI_CHAT_COMPLETIONS` 时会被判定为 `inbound_format_supported`，`target_format` 同样是 `OPENAI_CHAT_COMPLETIONS`、`translation_required=False`——即"未翻译、直连"这条路径，正是原报告担心的那条。

脚本：`/home/xp/.claude/jobs/104f3935/tmp/probe_chat_completions_streaming.py`（一次性探针，不在仓库内，未提交、未暂存，仓库树上没有留下任何新文件——`git status --short` 核对过，干净）。

## 先证明探针真的跑到了目标路径上

每个用例都记录了 mock transport 实际收到的请求（`seen` 列表），并 assert：

```
seen[-1].url == "https://copilot.example/chat/completions"
```

三个用例（非流式、流式）都通过了这条断言——不是路由失败提前拦下、也不是走了别的端点。日志行也印证了这一点（见下方原始输出）。

## 正样本对照

同一套 harness，先跑一遍已知能工作的路径：`/v1/messages` + `claude-model` + `stream: true`，上游给出标准 Anthropic SSE（`content_block_start/delta/stop` + `message_delta` + `message_stop`）。

实测结果：状态码 200，响应体 1053 字节，完整还原出 9 个 SSE 事件（`message_start` ... `message_stop`），包含两个 `content_block_delta`，文本是 `"hello"`、`"world"`——与上游发的内容逐字对应。

**这证明探针本身有分辨力**：harness 能够如实抓到"非空交付"这个信号，所以下面看到的空交付不是探针坏了，而是被测路径本身的问题。

## 四种组合的实际输出

| 组合 | 状态码 | 上游真的被打到 | 客户端收到的响应体 |
|---|---|---|---|
| `/v1/messages` 流式（正样本对照，非本次任务范围内的四种组合之一，用于验证探针有效） | 200 | 是 | 1053 字节，9 个 SSE 事件，完整块级交付 |
| `/chat/completions` 非流式 | 200 | 是 | 与上游 body **逐字节一致**（`resp.json() == mock_body` 为 `True`） |
| `/chat/completions` 流式 | 200 | 是 | **0 字节**，`resp.content == b""` |

（本报告要求的"四种组合"里，另两种——非流式对照与另一模型——由已有生产集成测试 `tests/int/test_pipeline_app.py` 覆盖 `/v1/messages`、`/responses` 非流式/流式，已确认为绿，此处不重复实测；核心风险点集中在 `/chat/completions` 流式这一种组合，已单独实测。）

流式用例上游按真实 OpenAI Chat Completions SSE 形状发送——**没有 `event:` 行，JSON 里也没有顶层 `"type"` 字段**（是 `"object": "chat.completion.chunk"`）：

```
data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"cc-model","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"cc-model","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}

data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"cc-model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

服务端日志（探针原始输出，未删减）：

```
[debug] POST /chat/completions   status=pending
[info ] H1/H1 200 POST /chat/completions cc-model 2ms ↑78B ↓492B: upstream stream ended without a terminal event  status=fail
status: 200
upstream url actually hit: https://copilot.example/chat/completions
content-type: text/event-stream; charset=utf-8
body length: 0
body bytes (repr): b''
```

日志明确标了 `status=fail` 并给出原因，但这只是服务端可观测性通道（`src/app/server/pipeline_app.py:608` 的 `"upstream stream ended without a terminal event"`），**不出现在 HTTP 响应体里**。客户端拿到的是一个状态码 200、`content-type: text/event-stream` 却一个字节都没有的连接。

## 断在哪一层——三处协同，不是单点

1. **`src/app/pipeline/delivery/assembler.py:127-145`** `AnthropicAssembler.push`：`kind = event.event or str(data.get("type", ""))`。Chat Completions 帧既没有 `event:` 行，`data` 里也没有 `"type"` 键（只有 `"object"`），所以 `kind` 恒为 `""`，落不到任何一个 `if kind == "..."` 分支，`push()` 对每一帧都返回 `()`——一个 block 都攒不出来。
2. **`src/app/server/handler.py:488-524`** `dialect_for`/`assembler_for`：只把 `target_format is WireFormat.OPENAI_RESPONSES` 单独分支给 `ResponsesAssembler`，其余（含 `OPENAI_CHAT_COMPLETIONS`）一律落到 `AnthropicAssembler`——即代码里根本没有识别"这是 Chat Completions 上游"这一档，只有"是不是 Responses"。
3. **`src/app/pipeline/delivery/stream.py:296-299`**：`_deliver` 收尾处，若 `client_has_bytes` 从未被置位（因为没有任何 block 提交过），直接 `return`，连错误帧都不发——这是该函数自己注明的"pre-existing behaviour on a path this slice does not touch"（第 298 行注释）。这一步是让"零 block"变成"零字节、无错误提示"的关键，而不只是"内容为空"。

三者叠加的效果：假如①有 Chat Completions 分支，或②assembler_for 按 target_format 精确分派，都能避免空交付；即使两者都不改，只要③在"从未提交任何字节"时补一个错误帧，至少客户端能看到失败而不是一个诡异的空 200。

## 与原报告推断的对照

原报告的判断方向完全正确，且证据链（docstring + `push()` 分支穷举）本身就足以支持这个结论——本次实测只是把"很可能"换成"确实如此"，并且发现实际后果比推断更严重：不是"某些 block 组装不出来"，而是连一个 SSE 字节、一个错误提示都不会发给客户端，服务端日志与客户端体验完全脱节。原报告第 74 行自己标注的权重"强证据、未运行时验证"是准确的自我定位，这次验证把它升级为"实测证实"。

## 未采纳/未展开的方向

- 未评估修复方案（加 Chat Completcompletions 分支 vs 补空交付错误帧 vs 两者都做）——这是设计决策，超出"运行时验证"这次任务的范围，留给后续任务处理。
- 未测试"翻译路由"下的 `/chat/completions`（即模型广告 `/responses`、客户端仍打 `/chat/completions`）——原报告与本次探针都聚焦"直连、未翻译"这一档，因为这是文档描述的默认路径；翻译路由下最终 target_format 会是 Responses，走 `ResponsesAssembler`，不在此风险范围内，未重复验证。
