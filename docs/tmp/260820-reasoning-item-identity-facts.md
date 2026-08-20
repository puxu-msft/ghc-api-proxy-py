# Reasoning item identity — facts from recorded production history

调查日期 2026-08-20。数据源：`~/.local/share/copilot-api/` 下 6 个 history-v3 数据库，全部以 `file:<path>?immutable=1` 只读打开，未做任何写操作。本文只陈述数据显示的事实，不提设计建议。

## 摘要（Q1–Q5 各一句）

1. **Q1 方向**：在主产品路径（`endpoint=anthropic-messages`）上，`reasoning` item **只出现在请求侧**——`effective-request`（proxy）与 `wire-request`（upstream）两个 payload 的 `input` 数组里；响应侧从未出现过 `reasoning` sequence-item（响应被投影成 Anthropic 形状，`content`/`tool_calls`），响应侧的 reasoning 只在原始 SSE 帧里可见。**已验证**。
2. **Q2 上游是否发 `id`**：**是，每一个都发**——4 个近期库的 `response.output_item.added`/`.done` 帧中 894/894 个 reasoning item 都带 `id`，且 `id` 是 **420 字符的 base64 大块**，**不是 `rs_...`**（全样本 4004 个 id 中 `rs_` 前缀 = 0）；更要命的是同一个 `output_index` 上 `.added` 与 `.done` 的 `id` **446/446 全部不同**，`encrypted_content` 也不同（done 更长、是最终值）。**已验证**。
3. **Q3 请求侧是否带回 `id`**：**在 anthropic-messages 路径上一个都没有**——6 个库、4752 个去重 reasoning item 对象、174,597 次 `wire-request.input` 出现，键集恒为 `{encrypted_content, summary, type}`，`id` 出现 0 次，而这些请求上游全部正常接受。**唯一例外**是 history-v3.db 里 11 个 `endpoint=openai-responses` 的透传操作（非本产品路径），其外部客户端确实把带 `id` 的 reasoning 原样送回，10/10 带 `id`。**已验证**。
4. **Q4 顺序/位置**：reasoning 在 `input` 数组里**紧贴其所属的 assistant 动作**——后继 100% 是 `function_call`(5765)、另一个 `reasoning`(1485) 或 `message:assistant`(21)，前驱是 `message:system`(5307)/`reasoning`(1485)/`function_call_output`(408)/`message:user`(71)；**数组下标是唯一表达这种归属的东西**，item 内部没有任何指向兄弟项的字段。**已验证**。
5. **Q5 一轮多个 reasoning**：**极常见**——单个 `input` 数组里 reasoning 数量的观测分布从 1 一直到 **135**（08-17 库），315 个含 reasoning 的数组中 **0 个**含有字节相同的重复 reasoning item，也就是说它们彼此只靠 `encrypted_content` 的内容差异 + 数组位置区分，没有任何显式标识。**已验证**。

## 方法与工具

- 打开方式：`sqlite3.connect(f"file:{path}?immutable=1", uri=True)`。全程只读，未触碰 4141 服务。
- 解压：`canonical_gz` / `manifest_gz` / `payload_gz` / `track_gz` 是 **zstd**；`v3_operation_arenas.arena_gz` 是 **zstd 前加了 3 字节前缀 `00 01 02`**（zstd magic `28 b5 2f fd` 在 offset 3），直接 `decompress` 会报 `error determining content size from frame header`；脚本统一用 `blob.find(bytes.fromhex("28b52ffd"))` 定位后 `decompressobj().decompress(...)`。
- 序列还原：`v3_sequence_nodes` 是**反向链表**，`payloadSequences[handle][i].rootHash` 是**末端**节点，沿 `parent_hash` 上溯再 reverse 得到数组顺序；`item_hash` 指向 `v3_objects(kind='sequence-item')`。

## Q1 — 方向是怎么判定的

方向**不在 item 里**，在 manifest 的 arena 里。`manifest_gz` 解开后 `record.arena.payloads[]` 每个条目形如：

```json
{"handle":"payload:2","sequence":7,"origin":{"stage":"wire-request","track":"upstream","dispatch":"dispatch:0"},"provenance":"derived","derivedFrom":"payload:1","transformId":"request:prepare-wire"}
```

而 `manifest.payloadSequences` 把同一个 `handle` 映射到若干 `{path, rootHash, length}`。于是 `(origin.stage, origin.track, path)` 就是方向坐标。观测到的 stage 取值：`ingress/client`、`effective-request/proxy`、`wire-request/upstream`、`upstream-response-projection/upstream`、`upstream-response-envelope/upstream`、`egress/client`。

对 4 个近期库做全量遍历（walk 每个 op 每个 payload 每条 sequence），reasoning 出现位置的计数：

| DB | ops | `effective-request/proxy` `input` | `wire-request/upstream` `input` | 任何响应侧 payload |
|---|---|---|---|---|
| history-v3-20260815-183721.db | 797 | 2150 | 2150 | 0 |
| history-v3-20260816-160151.db | 906 | 4192 | 4192 | 0 |
| history-v3-20260817-050754.db | 571 | 16351 | 16384 | 0 |
| history-v3-20260818-044224.db | 1164 | 7223 | 7271 | 0 |

history-v3.db（24544 ops）全量遍历结果：

```
('anthropic-messages','effective-request','input','no-id')      144179
('anthropic-messages','wire-request','input','no-id')           144600
('openai-responses','ingress','input','id')                         10
('openai-responses','effective-request','input','id')               10
('openai-responses','wire-request','input','id')                    10
('openai-responses','upstream-response-envelope','output','id')      6
('openai-responses','egress','output','id')                          6
```

**已验证的结论**：anthropic-messages 路径上 reasoning 是纯请求侧对象。响应侧之所以看不到，是因为该路径的响应投影 payload 走的是 Anthropic 形状（sequence path 为 `content` / `tool_calls`），而不是 Responses 的 `output`。只有 `openai-responses` 透传路径才有 `output` 序列，那 11 个 op 里响应侧 reasoning 是可见的。

## Q2 — 上游确实在 reasoning item 上发 `id`，而且它在 added→done 之间会变

SSE 帧体的存放位置在 08-15 前后**换了地方**，但**从未停止存储**：

| DB | 帧存放方式 | 有帧体的 op 数 |
|---|---|---|
| history-v3.db、history-v3-260811.db | `v3_objects(kind='frame')`（5,263,201 / 1,621,841 行） | — |
| 4 个 2026-08-15 之后的库 | `v3_operation_arenas.arena_gz`（JSON: `{"frame:N":{event,data,...}}`） | 758 / 879 / 570 / 1141 |

**「2026-08-15 之后不再存 frame」这个说法是错的**：新库里 `v3_objects` 确实没有 `kind='frame'` 了，但完整帧体搬进了 `v3_operation_arenas`，且 08-18 库里 1141 个 op 都有帧体、335 个 op 含 `output_item` 事件。**已验证**。

history-v3-20260818-044224.db 中所有 `response.output_item.*` 且 `item.type=="reasoning"` 的事件：

```
event types: {'response.output_item.added': 448, 'response.output_item.done': 446}
keysets:  ('added', ('content','encrypted_content','id','summary','type'))  448
          ('done',  ('content','encrypted_content','id','summary','type'))  446
id length histogram: {420: 894}     ids starting with 'rs_': 0
```

样例（来自 `req_1787056882119_91`，帧的 origin 是 `('upstream-capture','upstream', transformId=None)`，即**未经任何 rewrite 的原始上游字节**）：

```
frame:3  response.output_item.added  oi=0  id=wrl6Owoe+k2dmQhDC/BddAGb…(420 chars)  enc_len=4964
frame:5  response.output_item.done   oi=0  id=dhSy4sfeCJD5QWnk+qpqsSJb…(420 chars)  enc_len=7152
```

完整 added item（`encrypted_content`/`id` 截断至 80 字符）：

```json
{"content": [], "encrypted_content": "JsNdwKaIUI4ivCnyCZcsBzHO+GFcN4w9gxXPJxShLEvByujBrqVdu5JyC6AfvXb3T+643gEGbIZ/Wstg…(4964 chars)", "id": "wrl6Owoe+k2dmQhDC/BddAGb7Q5xJDYEeO6SNGy4YtKPCxdkPgsaDiO5pyG8x7daPBQNH5vTOYxP//Cq…(420 chars)", "summary": [], "type": "reasoning"}
```

按 `(event, output_index)` 归并（arena 里同一事件有多份 transform 副本，归并后 `added` 侧 446/446 是**单值**，说明副本之间 id 一致，差异不是 transform 造成的）：

```
{'id_CHANGED': 446, 'added_id_single': 446, 'added_only': 2}
```

**446 对里 446 对的 `id` 都变了，没有一对相同。** `encrypted_content` 同理：448 个 added 哈希与 446 个 done 哈希**交集为 0**。

history-v3-260811.db 独立复核（扫完全部 1,621,841 个 frame 对象，9.5 秒）：3110 个 reasoning `output_item` 帧，1555 added + 1555 done，**3110 个 id 全部互不相同，无一重复**，长度 424(2078)/420(994)/436(38)，`rs_` 前缀 0 个。其中 38 个 item 的键集是 `('content','id','summary','type')`——**没有 `encrypted_content`**。

**已验证的结论**：上游 100% 发 `id`；`id` 不是 `rs_` 形式而是 420–436 字符的 base64 不透明块；同一个 item 在 `.added` 与 `.done` 上拿到的是两个不同的 `id`，因此这个 `id` 无法在流内用作稳定标识。

## Q3 — 请求侧是否带回 `id`

**anthropic-messages 路径：一个都没有。** 样本规模：

| DB | 去重 reasoning item 对象 | 键集 | 带 `id` |
|---|---|---|---|
| history-v3-20260815-183721.db | 157 | `{encrypted_content, summary, type}` | 0 |
| history-v3-20260816-160151.db | 226 | 同上 | 0 |
| history-v3-20260817-050754.db | 327 | 同上 | 0 |
| history-v3-20260818-044224.db | 313 | 同上 | 0 |
| history-v3-260811.db | 389 | 同上 | 0 |
| history-v3.db | 3350 中的 3340 | 同上 | 0 |

按出现次数算：`wire-request.input` 上 anthropic-messages 路径共 **174,597** 次 reasoning 出现（2150+4192+16384+7271+144600），**带 `id` 的 0 次**。这些请求上游全部正常处理（08-18 库 1164 个 op 中 314 个含 reasoning 且完成）。

配套的一个决定性事实（08-18 库，按 SHA-256 比对 `encrypted_content`）：

```
added-enc: 448   done-enc: 446   added∩done: 0
request-enc: 313   req∩added: 0   req∩done: 313
```

**请求侧回送的 `encrypted_content` 逐字节等于 `.done` 那一份，313/313 全中，而 `id` 被整个丢掉。** 已验证。

**唯一例外，且不在本产品路径上**：history-v3.db 里 11 个 `endpoint=openai-responses` 的透传操作（`requestModel=gpt-5.6-terra`，客户端不是本 proxy 的转换层）。这里客户端把带 `id` 的 reasoning 原样送回，10/10 带 `id`，且 id 与上游此前发出的完全一致——`req_1786596997110_300` 的响应 `output` 里的 id `Ere2nsyA2RfZs94h6m+Ip4qqymq57KOSwG590KSu…` **逐字节**出现在后续 `req_1786597003191_303` 的 `ingress.input` 里，两个 op 的 `responseSuccess` 均为 `true`、`state=completed`。

请求侧带 id 的 item 与响应侧同一 item 的形状还不一样：

```
响应 output:  {"content": [], "encrypted_content": "…", "id": "…", "summary": [],                              "type": "reasoning"}
请求 input:   {              "encrypted_content": "…", "id": "…", "summary": [{"text":"","type":"summary_text"}], "type": "reasoning"}
```

即客户端丢掉了 `content`，并把空 `summary` 换成了一个空 `summary_text`。

**明确的负面结论**：现有生产服务在 anthropic-messages 路径上 **不携带 item 身份地往返 reasoning，上游照单全收**——样本 174,597 次出现、6 个数据库、跨 2026-08-06 至 2026-08-20，反例 0。同时数据也显示，**带 id 往返同样被上游接受**（openai-responses 路径 10/10 成功），只是那不是本 proxy 产生的流量。

## Q4 — 顺序与位置

history-v3-20260818-044224.db，全部 `wire-request` 的 `input` 数组中每个 reasoning item 的直接前驱/后继：

```
PRECEDED BY: {'message:system': 5307, 'reasoning': 1485, 'function_call_output': 408, 'message:user': 71}
FOLLOWED BY: {'function_call': 5765, 'reasoning': 1485, 'message:assistant': 21}
```

三个完整 `input` 数组的 type 序列：

```json
["message:user","message:system","reasoning","function_call","function_call_output","message:user","message:system","reasoning","function_call","function_call_output","message:user","message:system"]
```
（`req_1787104498464_858`，12 项）

```json
["message:user","message:system","reasoning","function_call","function_call_output","message:user","message:system"]
```
（`req_1787104496308_857`，7 项）

```json
["message:user","message:system","reasoning","function_call","function_call_output","message:user","message:system","reasoning","function_call","function_call_output","message:user","message:system"]
```
（`req_1787075720135_720`，12 项）

多工具并发时形态不变，reasoning 仍紧贴其后的 `function_call` 组，例如 `req_1787104664801_884`（160 项）中出现 `…,"message:system","reasoning","function_call","function_call","function_call","function_call_output","function_call_output","function_call_output",…`。

**已验证**：reasoning 的后继 100% 落在 `function_call` / 另一个 `reasoning` / `message:assistant` 三者之内，也就是它总是紧邻它所属的那次 assistant 输出。item 本身的三个键 `{encrypted_content, summary, type}` 中没有任何指向邻居的字段，因此**数组下标是唯一表达这种归属关系的载体**。注意 `message:system` 大量作为前驱出现（5307 次），是因为该 proxy 在把 Anthropic messages 转成 Responses `input` 时会在每个回合前插入 system 角色消息；这不改变「reasoning 紧挨着它的 function_call」这一点。

## Q5 — 一个请求里的多个 reasoning item

含 reasoning 的 `input` 数组中 reasoning 个数的分布（每个库独立统计，effective-request 与 wire-request 各计一次，故计数成对出现）：

| DB | 观测到的每数组 reasoning 个数范围 | 峰值 |
|---|---|---|
| history-v3-20260815-183721.db | 1–45 | 45 |
| history-v3-20260816-160151.db | 1–63 | 63 |
| history-v3-20260817-050754.db | 1–135 | 135 |
| history-v3-20260818-044224.db | 1–62 | 62 |

08-18 库中 315 个含 reasoning 的 `wire-request.input` 数组，**含字节相同重复 reasoning item 的数组数 = 0**。请求侧 reasoning 的 `summary` 长度分布：`{0: 4764, 1: 2507}`——即多数是空 summary，其余是单条 `summary_text`。

**已验证**：多 reasoning 是常态而非边缘情况，最多一次观测到 135 个；它们没有 `id`，彼此之间只靠 `encrypted_content` 的内容差异区分（全库无重复），而与各自 `function_call` 的绑定只靠数组位置。

## 未能回答 / 边界

- **响应侧完整（非流式）Responses body 里的 reasoning**：在 anthropic-messages 路径上不存在这样的 payload——响应投影是 Anthropic 形状。只有 11 个 `openai-responses` op 有 `upstream-response-envelope` 的 `output` 序列，样本 6 个 item，全部带 `id`。样本量太小，**只能作为存在性证据，不足以支撑分布性结论**。
- history-v3-260811.db 我只做了 `sequence-item` 全量键集扫描（389 个 reasoning 对象，全部无 `id`）与 frame 全量扫描，**没有**做逐 op 的 manifest walk，所以该库没有按 stage/path 拆分的计数。
- history-v3-260807.db（19.6 GB）与 history-v3-260809.db（14 GB）**未扫描**——前 6 个库已给出一致且样本量充足的结论，扫描它们的边际信息量低于其代价。这一点是**判断**，不是数据。
