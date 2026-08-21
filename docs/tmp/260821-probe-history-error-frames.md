# 取证：从 copilot-api history 里找真实的上游 SSE `error` 帧

- 日期：2026-08-21
- 授权：用户明确授权的**只读探测**。所有数据库连接一律 `file:...?mode=ro`（首轮结构与计数盘点用了 `immutable=1`，同样不写）。未执行任何写入、`VACUUM`、建索引或权限变更；未对 4141 端口的 Bun 服务做任何信号、停止、重启或接管。未改动任何生产代码，未触碰 git 索引。
- 探针脚本（均在 `/tmp`，未进入仓库）：
    - `/tmp/probe_history_errors.py` —— 按 operation 走 timeline，用 `from_history.py` 的 `_upstream_frames` 口径区分 root 与 derived。
    - `/tmp/sweep_frames.py` —— 绕开 operation，顺序全量扫描每个库的全部 frame 对象。
    - `/tmp/reverse_lookup.py` —— 把命中的对象 hash 反查回 operation，并用 transform 图判定 root/derived。
- 运行环境：`/home/xp/src/ghc-api-proxy-py/.venv/bin/python`（系统 python3 没有 `zstandard`）。

## 结论先行

**没有拿到任何一条上游发来的 SSE `error` 帧，也没有 `response.failed`。**

- 库里确实存在 `event: error` 的帧（共 25 个唯一对象，按 operation 实例算数十条），**全部是既有服务自己合成的下行帧**，逐条经 transform 图反查确认 `ROOT=False`，产出者是 `client-sink:synthetic` / `rewrite-out:recover-refusal` 一类。内容也自证：`[http2] upstream stream closed before any response (rstCode=0)`、`Server is shutting down`、一句中文的 refusal 提示——都是 copilot-api-js 自己的文案。
- `response.failed` 在 33,807,025 个已存 frame 对象里**一次都没有出现过**。

**但拿到了一个此前没有第一手样本的东西：20 条真实的上游 `response.incomplete` 帧，全部 `ROOT=True`。** 这是 Responses 腿的非正常终止事件（`incomplete_details.reason = max_output_tokens`），走的正是本项目主路径（客户端 `anthropic-messages` → 上游 Responses，模型 `gpt-5.6-sol` / `gpt-5.6-terra`）。完整帧见第四节。

这个「没有 error 帧」有两层，必须分开说，两者结论完全不同：

1. **在 frame 覆盖到的时间窗内（2026-07-17 09:37 → 2026-08-15 17:48，四个库共 3380 万个帧对象），库里确实没有。** 这是有分辨力的零命中，见第二节正样本对照。
2. **2026-08-15 之后的流量根本不存 frame**，那之后是否发生过，这些库无从回答。这一段是覆盖不到，不是没有。

## 一、库清单

| 文件 | 大小 | mtime | frame 对象数 | operations | 失败 op | operation 时间窗 |
|---|---|---|---|---|---|---|
| `history-v3-260807.db` | 19,641,716,736 | 2026-08-06 20:26 | 16,075,093 | 71,788 | 532 | 2026-07-17 09:37 → 2026-08-06 20:25 |
| `history-v3-260809.db` | 13,930,143,744 | 2026-08-09 00:28 | 10,846,890 | 39,927 | 680 | 2026-08-06 20:26 → 2026-08-09 00:21 |
| `history-v3-260811.db` | 1,268,183,040 | 2026-08-11 07:49 | 1,621,841 | 6,084 | 25 | 2026-08-10 06:46 → 2026-08-11 07:47 |
| `history-v3.db` | 4,222,758,912 | 2026-08-15 17:50 | 5,263,201 | 24,544 | 108 | 2026-08-11 08:11 → 2026-08-15 17:48 |
| `history-v3-20260815-183721.db` | 93,896,704 | 2026-08-16 16:02 | **0** | 797 | 4 | 2026-08-15 18:41 → 2026-08-16 16:01 |
| `history-v3-20260816-160151.db` | 95,563,776 | 2026-08-20 15:02 | **0** | 906 | 5 | 2026-08-16 16:02 → 2026-08-16 20:13 |
| `history-v3-20260817-050754.db` | 83,525,632 | 2026-08-17 13:17 | **0** | 571 | 2 | 2026-08-17 05:08 → 2026-08-17 13:13 |
| `history-v3-20260818-044224.db` | 157,941,760 | 2026-08-20 03:30 | **0** | 1,164 | 8 | 2026-08-18 04:42 → 2026-08-19 19:39 |

`history-v3-current.txt` 指向 `history-v3-20260818-044224.db`。

后四个库的 `v3_objects.kind` 只有 `payload` / `payload-skeleton` / `sequence-item`，**没有 `frame`**。这条实测直接印证了 `tests/int/recorded/from_history.py` 文档里那句「服务在 2026-08-15 停止写 frame 对象」，也确定了本次取证的时间上界。

`.db-wal` 存在且不小（最大 101 MB）。`mode=ro` 会读 WAL，`immutable=1` 不会；两种模式下 operation 计数一致，未见因此漏读。

### 表结构（`history-v3-20260818-044224.db`，与同代库一致）

```sql
CREATE TABLE v3_objects (
  hash TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  canonical_gz BLOB NOT NULL,
  canonical_bytes INTEGER NOT NULL
);
CREATE TABLE v3_operations (
  operation_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, digest TEXT NOT NULL,
  kind TEXT NOT NULL, created_at INTEGER NOT NULL, terminal_sequence INTEGER NOT NULL,
  ended_at INTEGER, timing_source TEXT NOT NULL DEFAULT 'storage-commit-upper-bound',
  manifest_gz BLOB NOT NULL, summary_json TEXT, pinned INTEGER NOT NULL DEFAULT 0,
  committed_at INTEGER NOT NULL
);
CREATE TABLE v3_timeline_chunks (
  operation_id TEXT NOT NULL REFERENCES v3_operations(operation_id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL, first_sequence INTEGER NOT NULL, last_sequence INTEGER NOT NULL,
  payload_gz BLOB NOT NULL, PRIMARY KEY(operation_id, chunk_index)
);
```

早期库（`history-v3-260807.db`、`history-v3-260809.db`）没有 `v3_transport_evidence` / `v3_operation_evidence_refs`，最新一代多了 `v3_operation_arenas`；核心三表在所有库中一致。

三处与探测方式直接相关：

- `*_gz` 后缀是历史包袱，**实际压缩算法是 zstd**（`from_history.py` 用 `zstandard.ZstdDecompressor`，本次实测确认）。所以对 blob 做 `LIKE '%error%'` 必然返回 0。这个坑本次绕开了；顺带一提，这里用 gzip 解 zstd 会直接抛异常而不会静默给出假数字，因为 zstd 魔数与 gzip 头不兼容。
- `summary_json` 是**明文** TEXT，可直接 `json_extract` 筛选，无需解压。
- `v3_objects` 是**内容寻址**表：内容完全相同的帧只存一份。所以「对象数」小于「帧实例数」，但对「这种形状的帧有没有出现过」这个问题去重不损失覆盖——每种唯一内容至少留下一份。下文凡说「N 条」，除非注明，都指唯一对象数。

## 二、正样本对照（证明管道有分辨力）

在断言任何「没有」之前，先用同一条解压 + 匹配管道去看确知存在的东西。这里有三层对照，逐层加强。

### 对照 1：管道读得到帧内容，且分得开 root 与 derived

取 `history-v3.db` 最近两个成功的 operation，按 `_upstream_frames` 口径（transform 图的根）分类：

```
# history-v3.db mode=sample ops=2
timeline entry types: {'payload': 10, 'ingress': 2, 'routing': 2, 'candidate': 2, 'dispatch': 2,
                       'diagnostic': 41, 'frame': 112, 'transform': 91, 'dispatch-settled': 2,
                       'egress': 2, 'candidate-settled': 2, 'terminal': 2}
ROOT frame events:    {'message_start': 1, 'content_block_start': 1, 'content_block_delta': 27,
                       'content_block_stop': 1, 'message_delta': 1, 'message_stop': 1, '<noname>': 1}
DERIVED frame events: {'message_start': 3, 'content_block_start': 3, 'content_block_delta': 61,
                       'content_block_stop': 3, 'message_delta': 3, 'message_stop': 3, '<noname>': 3}
HITS: 0
```

管道确实读到了帧内容，且 derived 恰为 root 的约 3 倍——与 `from_history.py` 文档里「同一事件被存三四份」的描述一致。这一条同时证明 root/derived 的划分在起作用。

### 对照 2：同一个匹配器能打到 `error` 帧

对 `history-v3.db` 全部 108 个失败 operation 跑同一管道：

```
# history-v3.db mode=failed ops=108
ROOT frame events:    {'response.created': 31, 'response.in_progress': 30,
                       'response.output_item.added': 183, 'response.reasoning_summary_part.added': 80,
                       'response.reasoning_summary_text.delta': 7789,
                       'response.reasoning_summary_text.done': 79, 'response.reasoning_summary_part.done': 79,
                       'response.output_item.done': 159, 'response.content_part.added': 14,
                       'response.output_text.delta': 14341, 'response.output_text.done': 11,
                       'response.content_part.done': 11, 'response.function_call_arguments.delta': 48163,
                       'response.function_call_arguments.done': 4, 'response.completed': 1,
                       'message_start': 33, 'content_block_start': 57, 'content_block_delta': 16024,
                       'content_block_stop': 34, 'message_delta': 4, 'message_stop': 4, '<noname>': 92}
DERIVED frame events: {'message_start': 130, 'content_block_start': 237, 'content_block_delta': 134179,
                       'content_block_stop': 124, 'ping': 144, 'message_delta': 12,
                       'message_stop': 12, 'error': 58, '<noname>': 15}
HITS: 58
```

**匹配器打到了 58 条 `error` 帧**，所以「找不到」不是因为匹配器瞎。这 58 条**全部落在 DERIVED 一侧，ROOT 侧一条都没有**。同一批 operation 的 root 侧出现了 15 种 `response.*` 事件名，`response.failed` 与 `response.incomplete` 不在其中。

### 对照 3：全库扫描的判据分支本身打红过

第三节的全量扫描用「帧的 `event` 名或 payload 顶层 `type` 落在 `{error, response.failed, response.incomplete, response.error}` 内」作为判据。这个判据的**同一个分支**在两个库里打出了 20 条 `response.incomplete`（第四节），且它们全部通过反查确认为 `ROOT=True`。也就是说：判定「上游发来的终止类事件」这条路径确实能亮，`response.failed` 的零命中不是判据没接上。

（`response.failed` 的 data 必然含 `"type":"response.failed"`，落在预筛子串 `failed` 内，随后被事件名判据接住——路径与 `response.incomplete` 完全相同。）

### 一个反面样本：为什么判据不能只用子串

第一版 sweep 只做子串匹配，在 `history-v3.db` 上报出 53 个「非 synthetic 命中」，逐条看下去**全是误报**：命中的是对话正文——我们自己在讨论 `response.failed` 的命令行与代码，被上游原样回显进了 `response.function_call_arguments.delta`。这就是为什么最终判据落在结构上而不是子串上。这条记下来，因为下次谁重跑这类扫描一定会再撞一次。

## 三、命中结果：全量对象扫描

绕开 operation 与 timeline，直接顺序扫每个库 `kind='frame'` 的全部对象。两段判定：先做便宜的子串预筛（`"error"` / `failed` / `incomplete`）保证速度，命中后解析帧、按帧自己的 `event` 名与 payload 顶层 `type` 判定。

| 库 | 扫描帧对象 | 预筛命中 | 判定为终止/错误形状 | 耗时 |
|---|---|---|---|---|
| `history-v3.db` | 5,263,201 | 13,340 | 5 | 29 s |
| `history-v3-260811.db` | 1,621,841 | 4,352 | 3 | 14 s |
| `history-v3-260809.db` | 10,846,890 | 102,802 | 20 | 139 s |
| `history-v3-260807.db` | 16,075,093 | 95,314 | 17 | 167 s |
| **合计** | **33,807,025** | 215,808 | **45** | |

45 条按事件名与来源展开：

| 事件 | 数量 | `synthetic` 标记 | 反查结论 |
|---|---|---|---|
| `error` | 15 | `error-shaping-canonical` | derived（服务合成） |
| `error` | 1 | `refusal-recovery` | derived（服务合成） |
| `error` | 9 | 无标记 | **仍是 derived**，见下 |
| `response.incomplete` | 20 | 无标记 | **ROOT=True，上游发来的** |
| `response.failed` | **0** | — | — |

### `synthetic` 字段不是可靠判据

9 条 `error` 帧没有 `synthetic` 标记，看上去像上游帧。逐条走 transform 图反查，**全部 `ROOT=False`**，产出者是 `client-sink:synthetic`（8 条）与 `rewrite-out:recover-refusal` → `render:anthropic` → `candidate:on-rendered-frame` → `client:on-rendered-frame` 这条改写链（1 条，同一 operation 里链上四个 handle 各存一份）。

内容本身也自证是服务自造：

```
{"type":"error","error":{"type":"api_error","message":"Upstream timed out before sending response headers"}}
{"type":"error","error":{"type":"api_error","message":"Failed to create messages"}}
{"type":"error","error":{"type":"invalid_request_error","message":"[http2] upstream stream closed before any response (rstCode=0)"}}
{"type":"error","error":{"type":"api_error","message":"[http2] upstream stream closed before any response (rstCode=0)"}}
{"type":"error","error":{"type":"api_error","message":"The operation was aborted."}}
{"type":"error","error":{"type":"api_error","message":"Server is shutting down"}}
{"type":"error","error":{"type":"timeout_error","message":"Upstream timed out before sending response headers"}}
{"type":"error","error":{"type":"api_error","message":"上游模型本轮以「拒绝（refusal）」结束、未产出可用回复（仅思考块）。已按 error 策略中断本次请求。可换表述/拆分步骤后重试，或改用其他模型。"}}
```

`[http2]`、`Server is shutting down`、那句中文提示，都是 copilot-api-js 自己的文案。这一段的操作性结论：**判断一条帧是不是上游发的，只能走 transform 图，不能看 `synthetic` 字段**——`error-shaping-canonical` 的打标本来就是 copilot-api-js 后期补上的（其 `docs/plan/2026-07-13-upstream-error-client-shaping/task-observability-fix-report.md` 记录了这个补丁），早期帧没有。

## 四、真正的命中：上游 `response.incomplete`

20 条，`history-v3-260809.db` 16 条 + `history-v3-260807.db` 4 条，**每一条反查都是 `ROOT=True`**，各自属于一个独立 operation。典型行：

```
== cb15e1a37ededa2d  owned by 1 operation(s)
   op=req_1786092809504_33 handle=frame:3783 ROOT=True endpoint=anthropic-messages
      model=gpt-5.6-sol success=True state=completed stream=True attempts=1 err='None'
```

几个值得注意的属性：

- **腿别：Responses 腿。** 事件名是 `response.incomplete`，payload 顶层带 `copilot_usage` + `response` + `sequence_number`——这是 Copilot 的 OpenAI Responses SSE，不是 Anthropic Messages SSE。客户端侧端点是 `anthropic-messages`，也就是说这走的正是本项目的主产品路径：Anthropic Messages 输入 / Responses 上游。
- 模型是 `gpt-5.6-sol`（17 条）与 `gpt-5.6-terra`（3 条，`req_1786048*` 那批）。
- **这些 operation 最终 `responseSuccess=True`**：既有服务把 `incomplete` 当正常终止处理，`diagnostic` 里记 `"stop_reason": "incomplete"`，`terminal` 记 `"outcome": "completed"`。所以按 `responseSuccess=0` 去筛 operation 是找不到它们的——这也是为什么第三节要绕开 operation 层做全量对象扫描。
- **它是上游流的最后一帧。** 以 `req_1786092809504_33` 为例，root 帧尾部：

```
  seq 7463 'response.output_text.done'
  seq 7465 'response.content_part.done'
  seq 7466 'response.output_item.done'
  seq 7468 'response.incomplete'      <- 上游最后一帧
  seq 7469 'content_block_stop'
  seq 7470 'message_delta'
  seq 7471 'message_stop'
```

上游在 `response.incomplete` 之后没有再发 `error`，流正常结束。

### 顺带发现的一个口径缺陷（影响 `from_history.py`）

上面 seq 7469–7471 的 `content_block_stop` / `message_delta` / `message_stop` 也被判成了 root。它们显然不是 Responses 上游发的（上游那一腿根本不说 Anthropic 事件名），而是既有服务**直接构造**的 Anthropic 下行尾帧——因为不是任何 transform 的 output，`_upstream_frames` 的「root = 没有 transform 产出它」口径就把它们算作了上游帧。

这不影响本次结论（本次判 root 的是 `response.*` 帧，腿别自证），但它意味着 **`tests/int/recorded/from_history.py` 派生出来的 cassette 里可能混入服务自造的尾帧**。这条留给主会话决定要不要跟进；本次探测不做修改。

### 代表性帧全文（脱敏后）

来源：`history-v3-260809.db`，operation `req_1786092809504_33`，object `cb15e1a37ededa2d06768dd4b0ba9a37ec9684d769afefa4241d05ba40346ee8`，root frame `frame:3783`（timeline sequence 7468）。

帧对象在库里的结构是 `{"data": <SSE data 原文字符串>, "event": "response.incomplete", "type": "response.incomplete"}`，所以线上的字节是：

```
event: response.incomplete
data: <下面这个 JSON 的紧凑形式>

```

脱敏口径：**凭据与账号标识**（`id` / `item_id` / `encrypted_content` / `safety_identifier` / `user`）替换为 `<scrubbed:字段名>`；超过 60 字符的自由文本（system prompt、推理摘要、输出正文）替换为长度标注；`tools` 数组 28 个工具定义整体折叠。**其余一律原样**，包括所有枚举值、数值、布尔与 null——协议形状完整保留。

```json
{
 "copilot_usage": {
  "token_details": [
   {"batch_size": 1000000, "cost_per_batch": 1000000000000, "token_count": 3, "token_type": "input"},
   {"batch_size": 1000000, "cost_per_batch": 100000000000, "token_count": 918200, "token_type": "cache_read"},
   {"batch_size": 1000000, "cost_per_batch": 1250000000000, "token_count": 819, "token_type": "cache_write"},
   {"batch_size": 1000000, "cost_per_batch": 4500000000000, "token_count": 2544, "token_type": "output"}
  ],
  "total_nano_aiu": 104294750000
 },
 "response": {
  "background": false,
  "completed_at": null,
  "created_at": 1786092813,
  "error": null,
  "frequency_penalty": 0,
  "id": "<scrubbed:id>",
  "incomplete_details": {"reason": "max_output_tokens"},
  "instructions": "<text elided: 13452 chars>",
  "max_output_tokens": 64000,
  "max_tool_calls": null,
  "metadata": {},
  "model": "gpt-5.6-sol",
  "moderation": null,
  "object": "response",
  "output": [
   {
    "content": [],
    "encrypted_content": "<scrubbed:encrypted_content>",
    "id": "<scrubbed:id>",
    "summary": [{"text": "<text elided: 591 chars>", "type": "summary_text"}],
    "type": "reasoning"
   },
   {
    "content": [],
    "encrypted_content": "<scrubbed:encrypted_content>",
    "id": "<scrubbed:id>",
    "summary": [],
    "type": "reasoning"
   },
   {
    "content": [{"annotations": [], "logprobs": [], "text": "<text elided: 6077 chars>", "type": "output_text"}],
    "id": "<scrubbed:id>",
    "phase": "final_answer",
    "role": "assistant",
    "status": "incomplete",
    "type": "message"
   }
  ],
  "parallel_tool_calls": true,
  "presence_penalty": 0,
  "previous_response_id": null,
  "prompt_cache_retention": "24h",
  "reasoning": {"context": "all_turns", "effort": "high", "mode": "standard", "summary": "detailed"},
  "safety_identifier": "<scrubbed:safety_identifier>",
  "service_tier": "default",
  "status": "incomplete",
  "store": false,
  "temperature": 1,
  "text": {"format": {"type": "text"}, "verbosity": "medium"},
  "tool_choice": "auto",
  "tool_usage": {
   "image_gen": {
    "input_tokens": 0,
    "input_tokens_details": {"image_tokens": 0, "text_tokens": 0},
    "output_tokens": 0,
    "output_tokens_details": {"image_tokens": 0, "text_tokens": 0},
    "total_tokens": 0
   },
   "web_search": {"num_requests": 0}
  },
  "tools": ["<28 tool definitions elided>"],
  "top_logprobs": 0,
  "top_p": 0.98,
  "truncation": "disabled",
  "usage": {
   "input_tokens": 919022,
   "input_tokens_details": {"cache_write_tokens": 819, "cached_tokens": 918200},
   "output_tokens": 2544,
   "output_tokens_details": {"reasoning_tokens": 748},
   "total_tokens": 921566
  },
  "user": "<scrubbed:user>"
 },
 "sequence_number": 1896,
 "type": "response.incomplete"
}
```

对本项目直接有用的几点：

- 终止事件携带**完整的 response 快照**，包括整份 `instructions`、整个 `tools` 数组、以及全部 `output` 项（含 `encrypted_content`）。这一帧的 data 长 114,864 字节——一个 `response.incomplete` 帧比整段增量流还大。
- `response.status = "incomplete"`，`incomplete_details.reason = "max_output_tokens"`，而 `response.error = null`。**失败原因不在 `error` 字段里**。
- 被截断的那个 message 项自身也带 `"status": "incomplete"`。
- `output` 里的 reasoning 项 `content` 为空、只有 `summary` 与 `encrypted_content`。

## 五、意外收获：上游非流式错误响应体的真实形状

不是 SSE 帧，但同属「我们没有第一手样本」的东西。它们存在 `kind='payload'` / `payload-skeleton` 的对象里，外层是既有服务自己的信封 `{"error":{"message":<上游原文>,"type":"error"}}`，`message` 里嵌的是**上游原样返回的响应体字符串**：

Anthropic 腿（注意有 `request_id`）：

```json
{"type":"error","error":{"type":"invalid_request_error","message":"messages: at least one message is required"},"request_id":"req_011Cdw25RhAemPc7DsQLyGuT"}
```

```json
{"type":"error","error":{"type":"invalid_request_error","message":"Tool 'finish_silently' cannot have both defer_loading=true and cache_control set. Tools with defer_loading cannot use prompt caching."},"request_id":"req_011Cdw8NQcMRSXVPARMkfPco"}
```

Responses 腿（形状完全不同：`error.code`，没有 `error.type`，末尾带一个换行）：

```json
{"error":{"message":"Invalid 'max_output_tokens': integer below minimum value. Expected a value >= 16, but got 8 instead.","code":"invalid_request_body"}}
```

`history-v3.db` 里含 `"error"` 的 payload 对象共 9 个；最新库 `history-v3-20260818-044224.db` 只有 1 个（`getaddrinfo ETIMEOUT`，服务自造）。

## 六、时间窗覆盖的补充证据

2026-08-15 之后的四个库虽然不存 frame，但仍有 operation summary。它们的失败原因分布（共 19 条）：

| 失败原因 | 20260815 | 20260816 | 20260817 | 20260818 |
|---|---|---|---|---|
| `The operation was aborted.` | 2 | 3 | — | 1 |
| `"Client disconnected"` / `"client disconnected"` | 2 | 2 | 1 | 3 |
| `"Stream closed with error code NGHTTP2_CANCEL"` | — | — | 1 | 2 |
| `getaddrinfo ETIMEOUT` | — | — | — | 1 |
| `[generation-budget] total candidate budget exhausted before recovery` | — | — | — | 1 |

全是传输层与客户端断开，没有一条读起来像「上游发来了一个 error 事件」。**这是弱证据**（`responseError` 是服务对失败的归因文本，不是上游原文；而且第四节已经证明 `response.incomplete` 会落在 `responseSuccess=True` 里，压根不进这张表），只能说明「这段时间没有出现明显由上游错误事件导致的失败」，不能反过来断言那段时间上游没发过 error 帧。判断这一段仍须以「覆盖不到」为准。

## 七、结论与建议（供主会话裁决，本次未执行任何改动）

1. **想要真实的上游 Anthropic SSE `error` 帧，这批 history 给不出来。** 库里所有 `error` 帧都是既有服务自己造的。要拿到真的，只能实际触发上游错误并录制（`tests/int/recorded/record_cassette.py`），或者接受「上游 Anthropic 腿在观测窗内从未发过 error 事件」这一事实并据此设计。
2. **`response.failed` 同样没有第一手样本。** 值得注意的是，`copilot-api-js` 源码里到处都有 `response.failed` 的处理分支（`candidate-response-session.ts:222`、`responses-stream-accumulator.ts:137`、`response-wire.ts:458`、`commit-boundaries.ts:21` 等），但按本次观测，**那些分支同样从未被真实上游流量走到过**——它们编码的是对协议的信念，不是对上游行为的记录。照抄它们等于照抄一个未经验证的假设。
3. **`response.incomplete` 可以直接派生成 cassette，且值得做。** 20 条 root 帧俱在，来源 operation 明确，走的是本项目主路径。它给出的是「Responses 腿非正常终止」这一类的真实形状，且暴露了一个不平凡的性质：终止帧携带完整 response 快照（此例 114 KB），`error` 为 null，失败信息在 `incomplete_details.reason` 里。
4. **`from_history.py` 的 root 口径有一个已确认的缺陷**（第四节末），会把服务直接构造、未经 transform 的下行尾帧算作上游帧。是否修、怎么修，交主会话裁决。
5. 若要为 `response.incomplete` 建 cassette，注意现有 `SCENARIOS` 用 `responseSuccess` 筛选，而这些 operation 的 `responseSuccess=True`，需要另加选择条件（例如直接指定 operation_id，或按 root 帧含 `response.incomplete` 来筛）。

## 附：本次跑过的命令要点

```bash
# 按 operation 走 timeline，正样本对照（mode=ro）
/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/probe_history_errors.py history-v3.db sample 2
/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/probe_history_errors.py history-v3.db failed

# 全量对象扫描（mode=ro）
for d in history-v3.db history-v3-260811.db history-v3-260809.db history-v3-260807.db; do
  /home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/sweep_frames.py "$d"
done

# 命中反查（mode=ro）
/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/reverse_lookup.py history-v3-260809.db <hash>...
/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/reverse_lookup.py history-v3-260807.db <hash>...
```
