# Responses 出站块级成帧：契约勘察与设计建议

日期：2026-08-22。作者：设计勘察员（只读勘察：除本报告外未写入、未暂存、未提交任何文件；`src/` 与 `tests/` 一字未动）。
上游任务：用户 2026-08-22 裁定新增 `responses_sse.py`，为直连 `POST /responses` 且 `stream: true` 的客户端腿写块级成帧。前置实测见 `.dev/docs/tmp/260822-direct-responses-stream-shape-probe.md`。

## 0. 读了什么，以及本文的权重标注

代码一律读**提交态** `git show HEAD:<path>`，HEAD = `2769a64`（`feat: hand a chat-completions stream to the client whole rather than not at all`）。例外已逐处标注。

工作树上同伴有未提交改动：`src/app/pipeline/delivery/stream.py`、`src/app/server/pipeline_app.py`、`src/app/config/schema.py`。凡引用这两个文件的工作树内容，本文写作「工作树态」并单独标注。

⚠️ 附带发现（与本任务无关，但值得主会话知道）：**HEAD 目前是不可导入的**。`git show HEAD:src/app/server/pipeline_app.py:42` 从 `app.pipeline.delivery.stream` 导入 `ContinuationSupport`，而 `git show HEAD:src/app/pipeline/delivery/stream.py`（共 367 行）里没有这个名字——它只存在于同伴未提交的工作树版本（`stream.py:57`）。按项目规则「commit 边界只由语义决定、不承诺每个提交可跑」，这是允许的状态，不是缺陷指控，只是提醒任何想在 HEAD 上跑测试的人。

权重约定，三档分开写：

- **[录制]**：从 `tests/int/cassettes/` 真实录制字节里读出来的。可直接采信。
- **[码读]**：从代码静态读出来的，附 `文件:行号`。可直接采信。
- **[建议]**：我的设计判断。需要主会话或用户裁决，尤其是第 6 节里我**不同意任务书写法**的那一条。

一次性脚本在 `/home/xp/.claude/jobs/104f3935/tmp/`（`struct.txt` / `events.txt` / `payloads.txt` 为其输出），未写入仓库。

---

## 1. 上游真实的 Responses 流式事件序列 [录制]

三份 cassette 里有 Responses 流：

| cassette | 来源 | 事件数 | 形态 |
|---|---|---|---|
| `anthropic_to_responses_stream.json` interaction 2 | `live-recording` | 12 | reasoning + 一条 message（文本 `PONG`） |
| `responses_web_search_stream.json` interaction 1 | `live-recording` | 16 | web_search_call + 一条 message |
| `history_responses_stream.json` interaction 0 | `history:history-v3-260809.db` | 125 | reasoning + 一条 message（115 个文本 delta） |

三份都**没有** `function_call`，所以工具调用那条腿的上游真实序列**本仓库当前无录制可依**。见第 7 节。

### 1.1 完整事件名序列

**`anthropic_to_responses_stream`（12 事件，`sequence_number` 0..11 连续）：**

```
0  response.created                 seq=0
1  response.in_progress             seq=1
2  response.output_item.added       seq=2  output_index=0  item.type=reasoning
3  response.output_item.done        seq=3  output_index=0  item.type=reasoning
4  response.output_item.added       seq=4  output_index=1  item.type=message  item.status=in_progress
5  response.content_part.added      seq=5  output_index=1  content_index=0
6  response.output_text.delta       seq=6  output_index=1  content_index=0  delta="P"
7  response.output_text.delta       seq=7  output_index=1  content_index=0  delta="ONG"
8  response.output_text.done        seq=8  output_index=1  content_index=0  text="PONG"
9  response.content_part.done       seq=9  output_index=1  content_index=0
10 response.output_item.done        seq=10 output_index=1  item.type=message  item.status=completed
11 response.completed               seq=11
```

`history_responses_stream` 是同一形状，只是文本 delta 有 115 个（seq 6..120）。

**`responses_web_search_stream`（16 事件，seq 0..15）：**

```
0  response.created
1  response.in_progress
2  response.output_item.added            output_index=0  item={id,status:"in_progress",type:"web_search_call"}
3  response.web_search_call.in_progress  output_index=0  （只有 item_id + output_index）
4  response.web_search_call.searching    output_index=0
5  response.web_search_call.completed    output_index=0
6  response.output_item.done             output_index=0  item={action,id,status:"completed",type:"web_search_call"}
7  response.output_item.added            output_index=1  item.type=message
8  response.content_part.added           output_index=1  content_index=0
9  response.output_text.delta            output_index=1  content_index=0
10 response.output_text.delta
11 response.output_text.delta
12 response.output_text.done             text=<全文>
13 response.content_part.done            part.text=<全文>
14 response.output_item.done             output_index=1  item.status=completed
15 response.completed
```

**读出来的次序规律（3/3 一致）：**

- `response.created` 恰好一次，永远是第 0 个；`response.in_progress` 恰好一次，永远是第 1 个。
- `sequence_number` 从 0 起严格递增、无跳号。
- `output_index` 从 0 起，按 item 出现顺序递增，**每个 item 的 added 与 done 用同一个 output_index**。
- `reasoning` item：只有 `added` 和 `done`，**中间没有任何 delta 事件**（seq 2 与 3 相邻）。
- `message` item：`added` → `content_part.added` → N×`output_text.delta` → `output_text.done` → `content_part.done` → `done`，`content_index` 恒为 0（单 part）。
- `web_search_call` item：`added` → 三个 `response.web_search_call.*` 生命周期事件 → `done`，无 delta；**`action`（即查询词）只在 `done` 上出现**，`added` 上只有 `{id,status,type}`。
- 终止事件 `response.completed` 恰好一次，最后一个，其 `response.output[]` 携带**全部 item 的完整副本**与 `usage`。

### 1.2 各类事件的 payload 骨架 [录制]

以下字段名与嵌套结构全部来自实际录制。`REDACTED`/`placeholder` 是 cassette 脱敏留下的痕迹，不是上游值。

**`response.created` / `response.in_progress` / `response.completed`**

```jsonc
{
  "type": "response.created",
  "sequence_number": 0,
  "response": {
    "id": "<416 字符的 base64 串>",
    "object": "response",
    "created_at": 1787203127,
    "completed_at": null,              // completed 上是时间戳
    "status": "in_progress",           // completed 上是 "completed"
    "model": "gpt-5.5-2026-04-23",
    "output": [],                      // completed 上是完整 item 数组
    "usage": null,                     // completed 上是 usage 对象
    "error": null,
    "incomplete_details": null,
    "instructions": null,
    "max_output_tokens": 64,
    "max_tool_calls": null,
    "metadata": {},
    "moderation": null,
    "parallel_tool_calls": true,
    "previous_response_id": null,
    "prompt_cache_retention": "24h",
    "reasoning": {"context": "current_turn", "effort": "medium", "mode": "standard", "summary": null},
    "safety_identifier": "REDACTED",
    "service_tier": "default",
    "store": false,
    "temperature": 1,
    "text": {"format": {"type": "text"}, "verbosity": "medium"},
    "tool_choice": "auto",
    "tools": [],
    "top_logprobs": 0,
    "top_p": 0.98,
    "truncation": "disabled",
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "background": false,
    "user": null,
    "tool_usage": {"image_gen": {...}, "web_search": {"num_requests": 0}}   // Copilot 私有扩展
  }
}
```

`response.completed` 顶层还多一个 Copilot 私有字段 `copilot_usage`（`{"token_details":[{batch_size,cost_per_batch,token_count,token_type}],"total_nano_aiu":…}`）。**[建议]** 我们出站不复制它：那是上游计费口径，我们既没有对应数字也没有承诺过。

`usage` 的实际形状：

```json
{"input_tokens": 12,
 "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
 "output_tokens": 19,
 "output_tokens_details": {"reasoning_tokens": 11},
 "total_tokens": 31}
```

（`history_responses_stream` 那份的 `input_tokens_details` 只有 `cached_tokens`，没有 `cache_write_tokens`——同一字段族在不同日期的上游不完全一致。）

**`response.output_item.added` / `.done`**

```jsonc
{"type": "response.output_item.added", "sequence_number": 2, "output_index": 0, "item": { … }}
```

`item` 三种实测形状：

```jsonc
// reasoning：added 与 done 的 key 集合完全相同，无 status 字段
{"type":"reasoning","id":"<416ch>","summary":[],"content":[],"encrypted_content":"<4892ch>"}
// message
{"type":"message","id":"<416ch>","role":"assistant","phase":"final_answer","status":"in_progress","content":[]}
// message（done 上）
{"type":"message","id":"<416ch>","role":"assistant","phase":"final_answer","status":"completed",
 "content":[{"type":"output_text","text":"PONG","annotations":[],"logprobs":[]}]}
// web_search_call（added 上只有三个键）
{"type":"web_search_call","id":"<416ch>","status":"in_progress"}
// web_search_call（done 上多出 action）
{"type":"web_search_call","id":"<416ch>","status":"completed",
 "action":{"type":"search","query":"…","queries":["…"]}}
```

注意 `phase: "final_answer"` 是 Copilot 私有扩展，OpenAI 官方 `ResponseOutputMessage` 里没有这个字段。

**`response.content_part.added` / `.done`**

```jsonc
{"type":"response.content_part.added","sequence_number":5,
 "output_index":1,"content_index":0,"item_id":"<416ch>",
 "part":{"type":"output_text","text":"","annotations":[],"logprobs":[]}}
```

`.done` 的 `part.text` 是全文。

**`response.output_text.delta`**

```jsonc
{"type":"response.output_text.delta","sequence_number":6,
 "output_index":1,"content_index":0,"item_id":"<416ch>",
 "delta":"P","logprobs":[],"obfuscation":"EMAj0lQX4xbGUTt"}
```

`obfuscation` 是 OpenAI 的随机填充字段（抗长度侧信道），**[建议]** 出站不发。

**`response.output_text.done`**

```jsonc
{"type":"response.output_text.done","sequence_number":8,
 "output_index":1,"content_index":0,"item_id":"<416ch>",
 "text":"PONG","logprobs":[]}
```

**`response.web_search_call.in_progress` / `.searching` / `.completed`**

```jsonc
{"type":"response.web_search_call.searching","sequence_number":4,
 "output_index":0,"item_id":"<416ch>"}
```

**本仓库无录制的事件**：`response.function_call_arguments.delta` / `.done`、`response.reasoning_summary_*`、`response.incomplete`、`response.failed`、`error`。它们的存在与字段只能从 SDK 类型定义读（下一节），不是从上游录制读的。

---

## 2. 块级交付下能发哪些、发不了哪些

### 2.1 判据来源：OpenAI Python SDK 的流式解析器 [码读]

本机 `.venv` 里 `openai==3.3.1`。判据文件 `.venv/lib/python3.14/site-packages/openai/lib/streaming/responses/_responses.py`：

| 事实 | 证据 | 强度 |
|---|---|---|
| **`response.created` 必须是第一个事件**，否则 `RuntimeError` | `_responses.py:368-370`：`if event.type != "response.created": raise RuntimeError(f"Expected to have received \`response.created\` before \`{event.type}\`")` | 硬要求 |
| `response.output_text.delta` 要求 `snapshot.output[output_index].type == "message"` 且 `output.content[content_index].type == "output_text"`，否则 `AssertionError` | `_responses.py:252-257` | 硬要求 |
| 而 `output.content` 只由 `response.content_part.added` 追加 | `_responses.py:343-348` | 硬要求 |
| `snapshot.output` 只由 `response.output_item.added` **append** | `_responses.py:330-342` | 硬要求：`output_index` 必须等于当时的 `len(output)`，**不能跳号** |
| `response.output_text.done` 同样 assert `message` + `output_text` | `_responses.py:272-277` | 硬要求 |
| `response.function_call_arguments.delta` assert `output.type == "function_call"`，并做 `output.arguments += delta` | `_responses.py:292-296`、`355-358` | 硬要求：`added` 的 item 必须带 `arguments`（可为 `""`） |
| `response.completed` 时 `assert self._completed_response is not None`，最终响应完全取自该事件的 `response` 对象 | `_responses.py:308-317`、`359-364` | 硬要求 |
| 流结束时没收到 `response.completed` → `RuntimeError("Didn't receive a \`response.completed\` event.")` | `_responses.py:85`、`:187`（同步与异步两处 `get_final_response()`） | 硬要求 |
| 其余一切事件走 `else: events.append(event)` 原样透出 | `_responses.py:320-321` | 即：`in_progress`、`content_part.done`、`output_item.done`、`reasoning_*`、`web_search_call.*` 对 SDK **不是必需的** |
| SSE 解码用 `construct_type`（宽松构造，不校验） | `_models.py:588-592` 注释「Loose coercion … If the given value does not match the expected type then it is returned as-is」 | 缺字段不会在解码时报错，只会在上面那些 assert 或后续属性访问时炸 |

`sequence_number` 在所有事件模型上都是**无默认值的必填字段**（`response_created_event.py:17`、`response_output_item_added_event.py:26`、…）。虽然宽松构造不会因缺失报错，**[建议]** 仍应逐事件递增地发出。

`Response` 对象的无默认必填字段（`openai/types/responses/response.py`）：`id`、`created_at`、`object`、`output`、`parallel_tool_calls`、`tool_choice`、`tools`、`model`。其余（`status`、`usage`、`error`、`incomplete_details`、…）都是 `Optional[...] = None`。

### 2.2 块级约束下的最小合法出站序列 [建议]

块级交付意味着：一个块从「开始」到「结束」是同一瞬间的事，中间没有可播报的中途状态。因此每个 `*.delta` 要么不发，要么一次性发完整内容。

我建议的**每块闭合帧组**（与 `anthropic_sse.block_frames` 的哲学一致——`anthropic_sse.py:6-7` 已经写明「delta 存在是因为线格式有它，不是因为内容分片到达」）：

```
# 开场（每个响应一次）
response.created            status=in_progress, output=[], usage=null
response.in_progress        （可省，见下）

# 每个 text 块
response.output_item.added      output_index=k  item={type:message, id:<自铸>, role:assistant, status:in_progress, content:[]}
response.content_part.added     output_index=k  content_index=0  part={type:output_text,text:"",annotations:[],logprobs:[]}
response.output_text.delta      output_index=k  content_index=0  delta=<整块文本>
response.output_text.done       output_index=k  content_index=0  text=<整块文本>
response.content_part.done      output_index=k  content_index=0  part={type:output_text,text:<整块文本>,annotations:[],logprobs:[]}
response.output_item.done       output_index=k  item={…, status:completed, content:[{type:output_text,text:<整块文本>,…}]}

# 每个 tool_use 块
response.output_item.added              output_index=k  item={type:function_call, id:<自铸>, call_id:<上游的>, name, arguments:"", status:in_progress}
response.function_call_arguments.delta  output_index=k  item_id  delta=<整段 JSON 字符串>
response.function_call_arguments.done   output_index=k  item_id  arguments=<整段 JSON 字符串>
response.output_item.done               output_index=k  item={…, arguments:<整段>, status:completed}

# 每个 thinking 块
response.output_item.added   output_index=k  item={type:reasoning, id:<自铸>, summary:[…], content:[], encrypted_content:<解码出的原文>}
response.output_item.done    output_index=k  item=<同上>

# 收尾（二选一，各一次）
response.completed   response={…, status:"completed", output:[全部 item], usage:{…}}
response.incomplete  response={…, status:"incomplete", incomplete_details:{reason:"max_output_tokens"}, output:[…], usage:{…}}
```

**逐项说明「为什么可省 / 为什么不可省」：**

| 事件 | 判定 | 理由 |
|---|---|---|
| `response.created` | **不可省** | SDK `_responses.py:368-370` 硬性 `RuntimeError`。这是整份契约里唯一一个「不发就一定炸」的事件。 |
| `response.completed` | **不可省** | `_responses.py:85`/`:187` 在 `get_final_response()` 里对没收到它的流直接 `RuntimeError`。（截断时改发 `response.incomplete`；两者互斥。） |
| `response.in_progress` | 可省 | 走 SDK 的 `else` 分支原样透出，不参与快照累积。**[建议]仍然发**：3/3 录制里它都在、位置固定、代价一帧，且客户端 UI 常拿它做「已受理」提示。 |
| `response.output_item.added` | **不可省** | 快照 `output` 列表只由它追加（`_responses.py:330-342`）。没有它，后续任何带 `output_index` 的事件都会 IndexError。 |
| `response.content_part.added` | **文本块不可省** | `output_text.delta/done` 的 assert 依赖 `output.content[content_index]` 存在（`_responses.py:254-257`、`275-277`）。 |
| `response.output_text.delta` | 理论可省，**[建议]不省** | 若把全文塞进 `content_part.added.part.text`，SDK 快照也是对的。但只按 delta 渲染的客户端会一个字都看不到。发一条「整块 delta」既满足块级语义、又不损失可渲染性。这正是 Anthropic 侧 `_delta_for`（`anthropic_sse.py:48-60`）的做法。 |
| `response.output_text.done` | 可省，**[建议]不省** | SDK 用它触发 structured-output 的 `parse_text`。忽略 delta、只等 done 的客户端靠它拿全文。 |
| `response.content_part.done` | 可省 | SDK 走 `else`。**[建议]发**，因为它是「这个 part 到此为止」的唯一显式信号，且录制里 3/3 都有。 |
| `response.output_item.done` | 可省 | SDK 走 `else`。**[建议]必发**：按 item 完成渲染的客户端（Codex 一类）靠它，而且这是我们唯一能给出 `status: completed` 的地方。 |
| `response.function_call_arguments.delta` | 不可省（若走该形状） | SDK `output.arguments += delta`（`_responses.py:355-358`）是 `function_call` 快照拿到参数的唯一途径。若省掉，就必须在 `added` 的 item 上直接给全量 `arguments`——但那样 `delta` 的累积基线就变成「全量 + 全量」，所以两者只能选一，**[建议]** 选 `added.arguments=""` + 一条整段 delta。 |
| `response.function_call_arguments.done` | 可省，**[建议]不省** | 同 `output_text.done` 的理由。 |
| `response.reasoning_summary_part.added` / `reasoning_summary_text.delta` / `.done` / `part.done` | **[建议]省** | 上游 3/3 录制里 reasoning item **一个 delta 都没有**（第 1.1 节）。我们照抄这个形状即可：把摘要文本直接放进 item 的 `summary: [{"type":"summary_text","text": …}]`。**这一条是设计选择，需要裁决**——见第 7 节。 |
| `response.web_search_call.*` | **发不了** | 见 3.3：assembler 已经把 `web_search_call` 改写成 TEXT 块，原 item 不复存在。 |
| `response.queued` / `response.audio.*` / `response.refusal.*` / `response.output_text.annotation.added` | 省 | 我们没有对应的块类型。 |

**块级交付真正丢掉的东西，说清楚**：客户端拿不到「一个字一个字长出来」的观感。它拿到的是 N 个瞬间闭合的完整块。这是项目已裁定的产品边界（CLAUDE.md「Block-level buffering is required」），不是本设计的缺陷。

---

## 3. `ResponsesAssembler` / `Terminal` 保留了什么、丢了什么

读的是 `git show HEAD:src/app/pipeline/delivery/assembler.py`（HEAD = `2769a64`）。行号均指该 blob。

### 3.1 逐字段判定表

| 反向成帧需要的字段 | 还在 / 丢了 | 证据 |
|---|---|---|
| **item type** | **部分丢**。上游 `message`/`function_call`/`reasoning` 被映射成 `TEXT`/`TOOL_USE`/`THINKING`（`assembler.py:260-264`），这三者可逆。但 `web_search_call` 被**改写成 `TEXT`**（`assembler.py:320-325`：`payload = {"type": TEXT, TEXT: web_search_call_text(...)}` 且 `kind = TEXT`），不可逆。未识别的 item type 走 `.get(item_type, item_type)` 保留原字符串（`:264`），但 `_close` 的 `else` 分支把它渲染成 `{"type":"text","text":draft.text}`（`:326-327`），同样不可逆。 |
| **item id** | **丢了，且这是对的**。`_close` 构造的 payload 里没有上游 item id：文本走 `:327`，thinking 走 `:314-318`，tool_use 走 `:307-312`。唯一保留的是 tool_use 的 `call_id`（见下）。第 4 节论证为什么丢掉它是正确的。 |
| **`function_call.call_id`** | **还在**。`assembler.py:309`：`"id": str(draft.payload.get("call_id") or draft.payload.get("id",""))`。这是唯一必须原样转发的上游 id——客户端要用它回填 `function_call_output`。 |
| **`function_call.name`** | **还在**。`assembler.py:310`。 |
| **`function_call.arguments`** | **还在，但已被解析成对象**。`assembler.py:311`：`"input": _decode_json(draft.partial_json or "{}")`。出站要发 `arguments` 字符串，须重新序列化——**原始字节串丢了**，格式化差异（空格、键序）不保真。畸形 JSON 被包成 `{"__raw": raw}`（`:414-416`），反向成帧要专门处理，否则会把 `{"__raw":"…"}` 当成真参数发给客户端。 |
| **`reasoning.encrypted_content`** | **还在，但被包了一层**。`assembler.py:316` 存的是 `_reasoning_signature(draft, data)` 的结果，即 `encode_reasoning_carrier(encrypted or None)`（`:367-383`）——本项目自制的 `ghc-api-proxy:synthetic-reasoning:v1:…` 载体。反向成帧必须调 `decode_reasoning_carrier`（`src/app/pipeline/translation_driver/reasoning_carrier.py:77`）取回原文。**空载体（上游没给 `encrypted_content`）也会编成一个非空 marker**，出站时必须还原成「不写 `encrypted_content` 键」而不是写一个 marker 字符串。 |
| **reasoning 摘要文本** | **还在**。`assembler.py:315`（`THINKING: draft.text`），由 `response.reasoning_summary_text.delta` 累积（`:225-227`）。 |
| **content part index** | **丢了**。`_accumulate`（`:269-272`）完全不看 `content_index`，所有 delta 都并进同一个 `draft.text`。**[建议]** 不用补：录制里 `content_index` 恒为 0（3/3），出站自铸 0 即可。真出现多 part 时我们本来就已经合并了。 |
| **`output_index`** | **半在**。`CompletedBlock.index` 来自 `draft.index = self._order`（`:266`），是「assembler 见过的第 k 个 item」，不是上游的 `output_index`（后者只被 `_item_key` 用作字典键，`:250-252`，从不入块）。**且它可能有空洞**：`_open` 无条件 `self._order += 1`（`:267`），而 `_close` 在丢弃被上游截断的 item 时 `return ()`（`:296-306`），那个序号就永久缺席。⚠️ 空洞会让 SDK 的 `snapshot.output[output_index]` 抛 IndexError（第 2.1 节）。**出站成帧器必须用自己的计数器重新编号，不能直接用 `block.index`。** |
| **`usage`** | **丢了原始形状**。`assembler.py:338` 存的是 `_anthropic_usage(...)` 的结果，即 Anthropic 键（`_anthropic_usage` 在 `:386-395`，转换在 `src/app/protocols/responses_anthropic.py:214-224`）。该转换把 `input_tokens` 减去了 cache 部分、并**丢弃 `output_tokens_details.reasoning_tokens`**。仓库里**没有**反向转换函数（grep `src/` 只有 `anthropic_usage_from_responses` 一处）。 |
| **`status` / `stop_reason`** | **半在**。`Terminal.stop_reason`（`assembler.py:48`）在 Responses 腿上由 `_read_terminal` 写：`max_output_tokens` → `"max_tokens"`（`:349-352`），无理由的 incomplete → `"incomplete"`，其余上游原词直通，正常结束 → `"tool_use"` 或 `"end_turn"`（`:353`）。据此**可以**反推出站的 `status` 与 `incomplete_details.reason`，但 `"tool_use"` / `"end_turn"` 是我们合成的词、Responses 协议里没有对应物，反推时要当成 `status:"completed"` 处理。 |
| **`response.id`** | **丢了，且这是对的**。`Terminal` 的全部字段是 `stop_reason` / `usage` / `seen` / `dialect` / `blocks` / `tools` / `thinking`（`assembler.py:44-59`），没有 response id。第 4 节论证为什么应当自铸。 |
| **`model`** | **丢了上游的精确值**。`response.model` 是带日期的 `gpt-5.5-2026-04-23`（第 1.2 节），assembler 不读它。`stream_delivery` 拿到的 `model` 是 `context.resolved_model`（`git show HEAD:src/app/server/pipeline_app.py:653`），即路由解析出的 id，通常是 `gpt-5.5`。**这是一处真实但轻微的信息损失**：客户端将看不到上游的精确模型快照。 |
| **`created_at`** | **丢了**。出站自己取 `time.time()` 即可。 |
| **`phase` / `tool_usage` / `copilot_usage` / `obfuscation` / `logprobs`** | 全丢 | 都是上游私有或噪声字段，assembler 不读。**[建议]** 不补。 |

### 3.2 必须新增携带的东西（最小集）[建议]

1. **Responses 原始 `usage`**。给 `Terminal` 加一个字段（如 `upstream_usage: dict[str, Any]`），在 `ResponsesAssembler._read_terminal`（`assembler.py:332-353`）里把 `response["usage"]` 原样存一份。理由：现存的 `Terminal.usage` 是有损转换的结果，反向再转一次会把 `reasoning_tokens` 变成 0、把 `input_tokens` 变成「不含 cache 的净值」，等于向客户端报了个错数。写反向转换函数是更差的选择——两次有损转换的复合。
   ⚠️ 该字段一旦加上，`terminal_from_anthropic`（`assembler.py:73-91`，非流式路径）与 `AnthropicAssembler` 都不会填它，出站成帧器读到空要有明确行为（**[建议]** 空则 `usage: null`，不要造零）。
2. **上游 `response.status` / `incomplete_details`**：可以不加。用 `stop_reason` 反推足够（第 3.1 表最后几行），代价是把 `"tool_use"`/`"end_turn"` 归一到 `completed`——这是无损的，因为 Responses 协议本来就只有 `completed`/`incomplete`/`failed` 三档。
3. **上游 `response.model`**：**[建议]** 不加。`context.resolved_model` 已经是客户端请求的那个 id，客户端拿回自己请求的 id 比拿回一个它没见过的日期快照更不容易困惑。这条我信心中等，交回主会话。

### 3.3 一处必须承认的语义损失

`web_search_call` 在入站解析时就被**降级成散文**了（`assembler.py:319-325`，注释写明「Text from here on. The item type is upstream's, and it has no Anthropic spelling to keep.」）。那个决定是为 Anthropic 客户端腿做的，在 Responses 客户端腿上就变成了纯损失：一个本来看得懂 `web_search_call` item 的 Responses 客户端，会收到一段描述搜索的文本。

**[建议]** 本轮不修。修它要动 `CompletedBlock` 的「内部一律 Anthropic 块形状」这条不变式（`blocks.py:41-46` docstring），那是另一件事。但要写进 `deferred.md`，并且**在第一版 `responses_sse.py` 落地时就在代码注释里说明**——否则下一个人会以为这是成帧器的 bug。

---

## 4. id 稳定性陷阱

### 4.1 实测：比 CLAUDE.md 记的还严重 [录制]

CLAUDE.md 记的是「Copilot 会在 `output_item.added` 与 `output_item.done` 之间改变一个 item 的 id」。实测结果是：**每一个事件里的每一个 id 字段都不一样。**

统计（脚本输出见 `/home/xp/.claude/jobs/104f3935/tmp/payloads.txt` 末尾）：

| cassette | id 出现次数 | 去重后 |
|---|---|---|
| `anthropic_to_responses_stream` | 12 | **12** |
| `responses_web_search_stream` | 16 | **16** |
| `history_responses_stream` | 125 | **125** |

包括：

- `response.created`、`response.in_progress`、`response.completed` 三处的 **`response.id` 互不相同**——同一个响应，id 换了三次。
- 同一个 message item 的 `added` / `content_part.added` / 每条 `output_text.delta` / `output_text.done` / `content_part.done` / `done`，`item_id` 全部互不相同。
- `response.completed` 的 `response.output[]` 里那两个 item 的 id，与它们各自 `added`/`done` 事件上的 id 也都不同。
- 附带：reasoning item 的 `encrypted_content` 在 `added` 上是 4892 字符、在 `done` 上是 4984 字符，**内容也不同**——这就是 `_reasoning_signature` 必须读 `done` 而不是 draft 的原因（`assembler.py:367-383` 已写明）。

**这个结论的取证强度是「足够作为判断依据」**，理由有三：

1. `tests/int/recorded/cassettes.py:60-68` 的脱敏名单是 `{token, tracking_id, enterprise_list, organization_list, safety_identifier}`——**`id` 与 `item_id` 不在其中**，所以两份 live-recording 里的 id 是上游原始字节。
2. `history_responses_stream` 走的是另一条脱敏路径（`from_history.py:107-126`），该路径**一致映射**（同一原值恒得同一替身），其 docstring 明写这样做正是「so a capture where upstream changed an item's id between `added` and `done` still shows two different ids」。125/125 全异，说明原始值也是 125 个不同的串。
3. 两份 live-recording（2026-08-16 与 2026-08-20 前后）与一份 history（2026-08-09 库）三个独立来源结论一致。

现有代码已经吃过这个亏：`_item_key`（`assembler.py:238-255`）的 docstring 记录了「keying on the id meant `_close` never found what `_open` had created and the whole response assembled into nothing」，因此改用 `output_index`。

### 4.2 对出站成帧意味着什么 [建议]

**规则：出站的每一个 id 都由我们自铸，且在一个 item 的生命周期内保持恒定。一个上游 id 都不转发。**

具体：

| 出站字段 | 取值 |
|---|---|
| `response.id` | 每个响应铸一次，全程复用。**[建议]** 直接用 `stream_delivery` 已有的 `message_id`（即 `context.id`，`pipeline_app.py:652`），或加 `resp_` 前缀。复用它的好处是日志里的 request id 与客户端看到的 response id 对得上。 |
| `item.id`（message / reasoning / function_call） | 每个块铸一次，`added` 与 `done` 用同一个；`item_id` 字段（content_part.*、output_text.*、function_call_arguments.*）用所属 item 的这一个。**[建议]** 形如 `msg_<hex>` / `rs_<hex>` / `fc_<hex>`，与 OpenAI 的前缀习惯一致。 |
| `function_call.call_id` | **唯一的例外：必须原样转发上游的**。它已经在 `CompletedBlock.payload["id"]` 里（`assembler.py:309`）。客户端下一轮要用它构造 `function_call_output`，我们改掉它就等于让工具结果对不上号。 |
| `output_index` | 出站成帧器自己的计数器，从 0 连续递增。**不能用 `block.index`**——理由见 3.1 表（可能有空洞）。 |
| `sequence_number` | 出站成帧器自己的计数器，从 0 连续递增，跨所有事件类型共享一个。 |

「不转嫁上游不稳定性」这件事在这里几乎是免费的：我们本来就没保留上游的 item id（3.1 表），所以自铸不是额外工作，而是**唯一可行的做法**。真正的风险是反过来——有人为了「保真」去给 `Terminal`/`CompletedBlock` 补上上游 id 字段，那才会把混乱引进来。

---

## 5. `handled.synthesized` 的语义，以及它在 Responses 腿上的组合

### 5.1 是谁写的、什么形状 [码读]

- `synthesized=True` 只在一处置位：`handler.py:170-181`，条件是 `isinstance(outcome.error, WebSearchNotExecutable)`。
- 回复由 `_answered_failed_search`（`handler.py:184-…`）构造，内容是**本代理自己写的 Anthropic 报文**：流式走 `failed_search_sse`（`src/app/pipeline/delivery/synthetic.py:105-149`），发的是 `message_start` / N×(`content_block_start` + `content_block_stop`) / `message_delta` / `message_stop`，块是 `server_tool_use` + 失败的 `web_search_tool_result`。
- 它被刻意做成「上游回复」的形状，好让它走完全相同的 assembler → buffer → delivery 链路（`handler.py:187` docstring：「so it goes through the same assembler, buffer and delivery path as everything else」）。
- 三处 `synthesized` 分支的作用一致：`response_payload`（`handler.py:464`）不翻译它；`dialect_for`（`handler.py:517-529`，`synthesized` 分支在 `:524`）判它为 ANTHROPIC，于是 `assembler_for`（`handler.py:560-566`）给它 `AnthropicAssembler`；`delivers_blocks`（`handler.py:546-557`，`synthesized` 分支在 `:555`）判它可块级交付。

### 5.2 「Responses 客户端腿 + synthesized」可达吗？**可达。** [码读]

链条：

1. `gate_hosted_web_search`（`src/app/pipeline/subscribers/hosted_web_search.py:79-129`）第一道闸是 `if context.target_format is not WireFormat.OPENAI_RESPONSES: return`——直连 `/responses` 的路由 `target_format` **正是** `OPENAI_RESPONSES`，闸门不拦。
2. 它检查 `context.payload["tools"]` 里有没有 `{"type": "web_search"}`（`_is_hosted_web_search`，`:65-68`；`_HOSTED_WEB_SEARCH = "web_search"`，`:30`）。**`{"type":"web_search"}` 恰好就是 OpenAI Responses 协议里 hosted web search 的原生写法**——一个直连 Responses 的客户端要用联网搜索，写的就是这个。
3. 若 `hosted_web_search` 未开启、或 `models_support_web_search` 没有匹配该模型，就 `raise WebSearchNotExecutable`（`:115` 或 `:125`）。
4. `handler.handle` 捕获它，返回 `synthesized=True`（`handler.py:170-181`）。

所以：**一个直连 `/responses`、`stream: true`、声明了 `web_search` 工具、而代理未开启该能力的客户端，会拿到一份 Anthropic SSE**——这与本任务要修的主缺陷是同一个病灶的第二个入口。

（`server_tools.py:227` 那处 `WebSearchNotExecutable` 走的是 Anthropic 入站的 `server_tool_use` 声明，与 Responses 客户端腿无关。）

### 5.3 应该怎么成帧 [建议]

**按客户端腿成帧，`synthesized` 不改变这个判断。** 具体说：`synthesized` 决定的是「用哪个 assembler 读」（Anthropic，因为是我们自己写的 Anthropic 报文），**不是**「用哪个 framer 写」。写哪种取决于客户端在哪种协议里问的。

于是 Responses 腿上的 synthesized 回复应该被成帧为：`response.created` → 一个 message item（其 `output_text` 是那两个 Anthropic 块被展平后的文本）→ `response.completed`。

⚠️ 但这里有个直接后果：`failed_search_blocks` 产出的是 `server_tool_use` 和 `web_search_tool_result` 两个 Anthropic 专有块，`AnthropicAssembler._close`（`assembler.py:174-188`）会把它们原样放进 `CompletedBlock.payload`，`kind` 分别是 `"server_tool_use"` 和 `"web_search_tool_result"`。**Responses 出站成帧器必须对这两个 kind 有明确处理**，否则会 fall through 到某个默认分支、发出一个空 `output_text`——就是 `assembler.py:322` 注释里记过的那类「every search produced an empty text block」的老病。

**[建议]** 复用 `src/app/pipeline/server_tool_text.py` 里已有的展平（`translation_driver/openai_responses.py:498-517` 的 `_server_tool_block_as_text` 已经在非流式路径上这么做了，理由在其 docstring 里写得很完整）。这样流式与非流式对同一个块给出同一段文字，不会出现两种措辞。

---

## 6. 落点建议

### 6.1 ⚠️ 我不同意任务书里「让成帧侧与解析侧用同一个判断」这一句

任务书写的是：「把 dialect 从判断处传进 `stream_delivery`，让成帧侧与解析侧用同一个判断。」

**这条如果照做，会打断本项目的主产品路径。** 理由：

`dialect_for`（`handler.py:517-529`）回答的是「**上游**用哪种词汇答的」，它的 docstring 也是这么写的（「which upstream's vocabulary this route's reply came back in … The route is the only thing that still knows which upstream was actually spoken to」）。而本项目的首要路径是 **Anthropic Messages 入站 → OpenAI Responses 上游**（CLAUDE.md「The primary product path is Anthropic Messages input served through an OpenAI Responses upstream」）。这条路径上：

- `route.target_format is OPENAI_RESPONSES` → `dialect_for` 返回 **RESPONSES**；
- 但客户端是 Claude Code，必须收到 **Anthropic** 事件名。

若把 `dialect_for` 的结果拿去选 framer，主路径的客户端就会开始收到 `response.*`——把今天的缺陷从一条支路搬到了主路上。第 5.2 节的 synthesized 组合是第二个反例（`dialect_for` 说 ANTHROPIC，而客户端是 Responses）。

**正确的选择器是客户端腿：`handled.route.inbound_format`**（`src/app/pipeline/routing.py:43`）。仓库里已有两处按这个判断的先例，都是「关于客户端腿的问题」：

- `delivers_blocks`（`handler.py:546-557`，判据在 `:557`）：`return handled.route.inbound_format is not WireFormat.OPENAI_CHAT_COMPLETIONS`——它的 docstring 已经把这层区分写清楚了：「a route can have an assembler and still have nowhere to write what it produces」，「`assembler_for` above answers the first. This answers the second, and the two are separate questions」。
- `reply_summary`（`handler.py:532-544`，判据在 `:541`）：`if handled.route.inbound_format is not WireFormat.ANTHROPIC_MESSAGES: return None`，其 docstring 明写「which *words* to use is about the upstream leg while which *reader* to use is about the client leg」。

**换句话说：`delivers_blocks` 已经在回答「客户端腿有没有 framer」这个问题了，本任务要做的正是把它的返回类型从 bool 升级成「哪一个 framer」。** 这是最小侵入的形状，也让这个判断继续留在一个地方。

这一条我信心高（有两处同向先例 + 一条会被打断的主路径 + 一个可达的反例），但它推翻了任务书的一句原话，**交回主会话裁决**。

### 6.2 建议的形状：一个出站成帧器协议 [建议]

为什么必须是**对象**而不是 `dialect` 枚举 + if/else：Responses 出站成帧是**有状态**的——要维护 `sequence_number`、`output_index`、`response.id`、以及每个 item 自铸的 id。`anthropic_sse.block_frames` 是纯函数，Responses 侧做不到。用一个每请求构造一次的成帧器对象，恰好与入站侧的 `BlockAssembler`（`assembler.py:112-119`）对称。

```python
# src/app/pipeline/delivery/framing.py（新文件，或放在 blocks.py 旁）

class OutboundFramer(Protocol):
    """把已经完整的块写成客户端协议的 SSE。`BlockAssembler` 的镜像。

    每个请求构造一个：Responses 侧要跨帧维护 sequence_number / output_index / 自铸 id。
    """

    def preamble(self) -> tuple[bytes, ...]:
        """开场帧。Anthropic 是 message_start；Responses 是 response.created (+ in_progress)。"""
        ...

    def block(self, block: CompletedBlock) -> tuple[bytes, ...]:
        """一个完整块的闭合帧组。调用者拿不到半组。"""
        ...

    def terminal(self, terminal: Terminal) -> tuple[bytes, ...]:
        """正常收尾。Anthropic 是 message_delta + message_stop；Responses 是 response.completed / .incomplete。"""
        ...

    def error(self, *, error_type: str, message: str, code: str | None = None) -> bytes:
        """已开场的流不会成功收尾时的那一帧。与 terminal 互斥。"""
        ...

    def keepalive(self) -> bytes:
        """块之间的保活。"""
        ...
```

对应的两个实现：

```python
# anthropic_sse.py（既有函数的薄包装，行为一字不改）
class AnthropicFramer:
    def __init__(self, *, message_id: str, model: str, signature_compat: ContentBlockStartCompat) -> None: ...

# responses_sse.py（新）
class ResponsesFramer:
    def __init__(self, *, response_id: str, model: str, created_at: float) -> None: ...
```

选择器：

```python
# handler.py，取代现有的 delivers_blocks
def framer_for(handled: HandledRequest, chain: Chain, *, message_id: str, model: str) -> OutboundFramer | None:
    """客户端腿的出站成帧器，`None` 表示这条腿没有 framer（走 one_shot_delivery）。

    按 `route.inbound_format` 分派，不是按 `dialect_for`：那个回答的是上游用哪种词汇答的，
    这个回答的是客户端在哪种协议里问的。翻译路由上这是两个不同的格式。
    """
```

`stream_delivery` 的签名（相对**工作树态** `stream.py:207-217`，同伴正在改，以下按其当前形状给出）：

```python
async def stream_delivery(
    chunks: AsyncIterator[bytes],
    assembler: BlockAssembler,
    *,
    framer: OutboundFramer,          # 新增；取代 message_id / model / settings.signature_compat 的直接使用
    buffer: BlockBuffer,
    settings: StreamSettings,
    replay: ReplaySupport | None = None,
    continuation: ContinuationSupport | None = None,
) -> AsyncGenerator[bytes]: ...
```

`message_id` 与 `model` 随之从 `stream_delivery` / `_deliver` / `_commit` / `_hand_over` 的参数表里消失，改由 framer 在构造时持有。这实际上**减少**了穿透四层的参数。

### 6.3 三处（其实是六处）调用点怎么改 [建议]

按**工作树态** `stream.py` 的行号（同伴正在改，落地前需复核）：

| 位置 | 现状 | 改法 |
|---|---|---|
| `_commit`，`stream.py:447`+`:449` | `message_start(...)` + `block_frames(...)` | `framer.preamble()` + `framer.block(ready)` |
| `_deliver` 缓冲区收尾，`stream.py:347`+`:350` | `message_start(...)` + `block_frames(...)` | 同上 |
| `_deliver` 正常收尾，`stream.py:377-380` | `terminal_frames(stop_reason=…, usage=…)` | `framer.terminal(assembler.terminal)`——把 `stop_reason or "end_turn"` 这类合成挪进 framer，各自按本协议的词汇合成 |
| `_deliver` 客户端超时，`stream.py:311-315` | `error_frame(...)` | `framer.error(...)` |
| `_deliver` 截断报错，`stream.py:361-365` | `error_frame(...)` | `framer.error(...)` |
| `_deliver` 保活，`stream.py:299`（`PING_FRAME` 定义在 `:33`） | `yield PING_FRAME` | `yield framer.keepalive()` |
| `_hand_over`，`stream.py:416`/`:418`/`:422`/`:424`/`:426` | `message_start` / `block_frames` / `terminal_frames` | 同上三种替换 |

`_hand_over` 有个已经就位的保护：`ContinuationSupport.synthesize` 的实现 `_hand_back`（**工作树态** `pipeline_app.py`）第一句就是 `if route.wire_format is not WireFormat.ANTHROPIC_MESSAGES: return None`，其 docstring 写明「Only for a client that asked in Anthropic Messages」。所以续接机制在 Responses 腿上本来就返回 `None`，`_hand_over` 走不到成帧。**不需要为它做 Responses 版本**，但替换成 framer 调用后要确认这个短路仍然成立。

### 6.4 错误帧与保活在 Responses 腿上分别发什么 [建议]

**保活。** Anthropic 侧是 `PING_FRAME = b": ping\n\n"`（**工作树态** `stream.py:33`，HEAD 上是 `:32`）——一条 SSE 注释。**SSE 注释与协议无关，Responses 腿可以原样复用。** 它不携带事件名，任何 SSE 解析器都会忽略它，不会进入 OpenAI SDK 的事件流。我建议 `ResponsesFramer.keepalive()` 直接返回同一串字节。

不建议改用 `response.in_progress` 做保活：SDK 会把它透出给应用层，重复几十次会让「响应已受理」这个事件变成噪声，而且它带 `sequence_number`，重复发会让序号语义变形。

**错误帧。** Responses 协议里有两个候选：

1. `type: "error"` 事件（注意**没有** `response.` 前缀，见 `openai/types/responses/response_error_event.py:26`），字段 `{type:"error", sequence_number, code: str|null, message: str, param: str|null}`。
2. `response.failed` 事件，字段 `{type, sequence_number, response: {..., status:"failed", error:{code, message}}}`。

**[建议] 用 `error` 事件**，理由：
- 与 Anthropic 侧 `error_frame` 的语义一一对应（「已开场的流不会成功收尾」，`anthropic_sse.py:141-151`），映射直接：`error_type` → 无对应位置可丢或并入 `message`，`message` → `message`，`code` → `code`。
- `response.failed` 要求携带一个完整 `Response` 对象，而我们在流中途出错时那个对象是残缺的（没有 usage、output 半截），造一个出来是发明事实。
- OpenAI SDK 对 `error` 走 `else` 分支原样透出（`_responses.py:318-319`），不做断言，安全。

⚠️ 一处不对称需要裁决：Anthropic 侧的 `error_frame` 有 `error.type`（`WIRE_TYPES[ErrorCategory.*]`，如 `api_error` / `overloaded_error`），Responses 的 `error` 事件**没有对应字段**（只有 `code`/`message`/`param`）。**[建议]** 把类别塞进 `code`（因为 `code` 本来就是「稳定的机器可读标识」），把现有的 `code`（如 `incomplete_responses_stream`）保持在 `code`，类别并入 `message` 前缀。或者反过来。这一处我信心中等，列为待裁。

⚠️ 还有一个**必须回答但本设计不能自己决定**的问题：**工作树态** `stream.py:354-356` 那条「什么都没提交过就直接 `return`」的分支，在 Responses 腿上意味着客户端收到一个 200、空 body、**连 `response.created` 都没有**。OpenAI SDK 在这种情况下会走到 `get_final_response()` 报 `_completed_response is None`，或者干脆什么都没有。Anthropic 腿上这是既有行为（注释写明「pre-existing behaviour on a path this slice does not touch」），但 Responses 腿是新写的，我们有机会一开始就做对——**[建议]** 至少发 `response.created` + `error`。列为待裁，因为它改变了「首块之前不发任何东西」这条项目不变式在新腿上的表述（`blocks.py:1-8`）。

---

## 7. 待裁决与阻塞点

按重要性排序，全部交回主会话：

1. **【高】选择器用 `route.inbound_format` 而非 `dialect_for`。** 见 6.1。这一条推翻了任务书的一句原话，且如果照任务书做会打断主产品路径。**建议在写 `responses_sse.py` 之前先裁决**。
2. **【高】`Terminal` 需要新增 `upstream_usage` 字段。** 见 3.2.1。不加就只能向 Responses 客户端报一份被 Anthropic 化过、`reasoning_tokens` 归零的 usage。这是改 `assembler.py`，而该文件同伴正在改动范围之外（HEAD 与工作树一致），但仍需协调。
3. **【中】reasoning 摘要要不要发 `response.reasoning_summary_*` 事件族。** 见 2.2 表。我建议只放进 item 的 `summary`（照抄上游 3/3 录制的形状），但没有录制能证明「客户端只看 summary 字段也够」。
4. **【中】`error` 事件里 `error_type` 往哪塞。** 见 6.4。
5. **【中】「一块都没有」时 Responses 腿发不发 `response.created` + `error`。** 见 6.4 末尾。
6. **【中】`model` 报 `context.resolved_model` 还是补上游的日期快照。** 见 3.2.3。
7. **【低】`web_search_call` 在 Responses 客户端腿上被降级成散文。** 见 3.3。建议记入 `deferred.md`，本轮不修。
8. **【取证缺口】本仓库没有任何带 `function_call` 的 Responses 流式录制。** 三份 cassette（12/16/125 事件）全是 reasoning + message，外加一次 web_search_call。因此第 2.2 节里 `function_call` 那组帧的形状**是从 SDK 类型定义与解析器代码推出来的，不是从上游录制读出来的**，权重低于本文其余部分。建议在实现前按 CLAUDE.md 的办法补录一次带工具调用的 cassette（`PYTHONPATH=src:tests/int uv run python tests/int/recorded/record_cassette.py <scenario>`，需凭据、发真实请求）——这需要用户授权。
9. **【附带】HEAD 当前不可导入。** 见第 0 节。不影响本设计，但影响任何想在 HEAD 上跑验证的人。
