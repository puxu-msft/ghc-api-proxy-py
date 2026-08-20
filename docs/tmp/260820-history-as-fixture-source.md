# 从 history 派生 cassette 固件——能力依赖与本项目差距（2026-08-20）

调查范围：只读。未修改任何代码或数据库。`~/.local/share/copilot-api/*.db` 全程以 `mode=ro` 或 `?immutable=1` 打开。

## 1. cassette 的完整数据结构

权威定义在 `/home/xp/src/ghc-api-proxy-py/tests/integration/recorded/cassettes.py`。

顶层 `Cassette`（166-317行区间，`cassettes.py:295-317`）：

```
{"version": 1, "interactions": [Interaction.as_json(), ...]}
```

`Interaction`（`cassettes.py:236-292`）每条记录一次上游请求/响应：

- `request.method` `request.path`：匹配用，不匹配 body（`ReplayTransport._handle`, `cassettes.py:358-385`，按 method+path 顺序匹配，不比对 body——body 里带一次性 id，永远不可能再次发出）。
- `request.authenticated`：布尔，只记录“是否带了 Authorization”这一事实，密钥本身绝不落盘（`cassettes.py:239-241`）。回放时若录制时认证过、这次请求没带 Authorization，抛 `UnauthenticatedRequest`（`cassettes.py:369-373`）。
- `request.shape`：由 `_request_shape()`（`cassettes.py:209-228`）产生——`model`、`stream` 明文保留，外加对整个请求体排序后取 sha256 的 `digest`。用整个 body 而非挑几个字段，是因为挑字段导致 `input` 整体清空还能匹配上录制（`cassettes.py:213-217` 注释里记录的真实故障）。
- `response.status` / `response.headers` / `response.extensions` / `response.source` / `response.chunks`。

**chunk 边界**：`chunks: list[bytes]`，即“一条录制就是一串按到达顺序排列的字节块”，逐块存储而非拼成一整段（`cassettes.py:82-94` 的 `_encode_chunk`/`_decode_chunk`：文本按 UTF-8 存 `text`，非 UTF-8 按 `base64`）。回放通过 `_ReplayStream`（`cassettes.py:319-330`）把这些块原样、逐个吐回给 httpx——这是整个设计要保的核心不变量：**下游是块级交付（见 `stream.py` 的 `stream_delivery`），chunk 怎么落在字节流上直接决定测试测的是什么**，vcrpy 因为合并 chunk 被拒绝（`docs/tmp/260818-vcrpy-poc.md`，`cassettes.py:1-6`）。

**响应头 allowlist**：`KEPT_RESPONSE_HEADERS = {"content-type", "transfer-encoding", "cache-control"}`（`cassettes.py:48-54`）。用 allowlist 而非 denylist 是吃过三次亏后的结论：`x-oauth-client-id`、`x-request-id`、`copilot-edits-session` 三个身份头是三轮人工审查各自漏掉一个才发现的，denylist 天然是“过去发现过的都删”，allowlist 是“只留下明确需要的”。

**请求头脱敏**：`VOLATILE_REQUEST_HEADERS = {authorization, cookie, x-request-id, x-agent-task-id, x-interaction-id}`（`cassettes.py:33-41`），录制前丢弃——`authorization` 是密钥，其余是每次请求都变、留着也匹配不上的噪音。

**响应体脱敏**：`REDACTED_RESPONSE_FIELDS = {token, tracking_id, enterprise_list, organization_list, safety_identifier}`（`cassettes.py:60-69`），按字段名任意深度递归替换（`_scrub_value`, `cassettes.py:97-118`）——`safety_identifier` 藏在 SSE 帧的 `response` 对象内部，只查顶层曾经漏掉过。`token` 之类会被替换成整数占位（`PINNED_RESPONSE_FIELDS = {"expires_at": FAR_FUTURE_EPOCH}`，`cassettes.py:73-79`：录制时是真实过期时间，固定成 2100 年，否则半小时后 cassette 就因为 token 判定过期而报「exhausted」）。

流式响应体的脱敏在 `_scrub_sse`（`cassettes.py:132-158`）：先把所有 chunk 拼接、再按帧扫描 `data:` 行、脱敏后按**原始长度占比**重新切回相同数量的 chunk（`_resplit`, `cassettes.py:161-175`）——因为脱敏会改变长度，若按原始字节偏移切会导致边界失真；之所以要先拼接再切，是因为真实抓包里 26 个 chunk 只有 9 个恰好落在帧结束处，逐 chunk 脱敏会解析出截断 JSON、静默失败、字段没脱干净（`cassettes.py:135-138` 注释记录的实测）。

**请求侧记了什么**：只有 `_request_shape()` 产出的 `{model, stream, digest}` 摘要，**不存原始 body**（`cassettes.py:209-228`）。`from_history.py` 更进一步——它连这个摘要都拿不到，`request_shape={}`（`from_history.py:236-237`），因为 history 库根本不记录请求体，回放时该字段形同虚设，只校验 method+path 顺序。

`source` 字段区分录制来源：`"live-recording"`（`cassettes.py:417`）还是 `"history:<db文件名>:<operation_id>"`（`from_history.py:242`），因为二者可信度不同——只有真录制能证明 chunk 真实落在字节流上的方式。

## 2. copilot-api-js 的 history-v3 库：结构与「帧级派生」何以可能

`~/.local/share/copilot-api/` 下目前只有一个库真正带 `kind='frame'` 的对象：`history-v3.db`（4.2GB，`mtime=2026-08-15 17:50`）。2026-08-15 之后创建的四个库（`history-v3-20260815-183721.db` 直到当前 `history-v3-20260818-044224.db`，由 `history-v3-current.txt` 指向）里 `v3_objects` 只有 `payload` / `payload-skeleton` / `sequence-item` 三种 kind，**没有 `frame`**——这与 `from_history.py:14-19`、`from_history.py:90-91`（"the service stopped writing frame objects on 2026-08-15"）的说法数值吻合：直接验证成立，权重：**实测确认，非猜测**。

`history-v3.db` 的 schema（`.schema` 输出，只读）里与帧级派生直接相关的表：

- `v3_objects(hash PK, kind, canonical_gz, canonical_bytes)`：内容寻址对象仓库，`kind='frame'` 的行就是一条 SSE 帧的解压后 JSON（`{"event": ..., "data": "<json字符串>"}`），按内容哈希去重存储。实测：5,263,201 行，合计原始 `canonical_bytes` 约 2.05GB，合计压缩后 `canonical_gz` 约 1.40GB（平均单帧 390 字节原始 / 267 字节压缩，压缩算法版本未验证，大概率是 Node zstd 绑定，具体 level 未知——**未验证**）。
- `v3_operations(operation_id PK, ..., manifest_gz, summary_json, ...)`：一次请求（`operation_id` 形如 `req_<epoch>_<seq>`）的清单，`manifest_gz` 解压后是 `{"objectHashes": {handle: hash, ...}}`，把时间线里的“帧句柄”映射到 `v3_objects.hash`。`summary_json` 里有 `endpoint`、`stream`、`responseSuccess`、`responseModel` 等字段，是 `from_history.py:find_operation()`（199-213行）用 `json_extract` 查询定位一次操作的依据。
- `v3_timeline_chunks(operation_id, chunk_index, payload_gz, ...)`：一次操作的事件时间线，按 `chunk_index` 顺序分段存储，`payload_gz` 解压后是事件数组，每个事件带 `sequence`（全局递增序号，决定顺序）、`type`（`"frame"` 或 `"transform"`）、`handle`（指向 `objectHashes`）。**这是「一帧一个对象」得以重建到达顺序的关键**：`sequence` 才是权威顺序，帧对象本身不带顺序信息。
- `type='transform'` 的事件在 `value.outputs[]` 里列出它产生的新帧句柄（`kind='frame'`），这让 `_upstream_frames()`（`from_history.py:129-151`）能反向排除“被某个 transform 生产出来的帧”，只留下“没有被任何 transform 生产过”的帧——即真正来自上游的原始帧。

综上，帧级派生之所以可能，是因为该库**把每一条 SSE 事件当一等对象持久化，并且记录了「谁改写了谁」的转换图**（`transform` 事件），而不仅仅是最终结果。这正是本项目当前完全没有的能力（见第3节）。

## 3. 本项目要具备同等能力，最小需要补什么

现状（`src/app/history/sqlite/schema.py:1-20`，`src/app/history/types.py:1-26`）：`entries` 表只有 `request_payload`、`response`、`usage` 三个 BLOB 列，`response` 是**最终装配结果**（`src/app/history/consumer.py:45-46`：`entry.response = context.final_response_payload`），从未记录过任何一条原始上游 SSE 帧。`HistoryWriter`（`src/app/history/sqlite/writer.py`）也没有引入 zstd——`zstandard` 目前只是 dev 依赖，仅 `from_history.py` 用来读别人的库（`pyproject.toml:46-47`）。

最小 schema 增量建议（未落地，仅设计建议）：

```sql
CREATE TABLE IF NOT EXISTS upstream_frames (
    entry_id     TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    sequence     INTEGER NOT NULL,      -- 到达顺序；服务 cassette 的 chunk 顺序
    event        TEXT NOT NULL,         -- SSE 的 event: 行；服务 cassette 帧内 event 名
    data_zstd    BLOB NOT NULL,         -- 单帧 data: 载荷，zstd 压缩；服务 cassette 的 chunks[]
    data_bytes   INTEGER NOT NULL,      -- 压缩前字节数，体积估算/reaper 用
    PRIMARY KEY (entry_id, sequence)
);
```

对应 cassette 的哪一部分，逐列说明：

- `sequence`：cassette 的 `chunks` 列表顺序本身就是到达顺序；没有独立的顺序号列是因为现在只有“最终结果”这一份数据，没有帧序列。这一列是重建 `Interaction.chunks` 顺序的唯一依据。
- `event` + `data_zstd`：拼成 `f"event: {event}\ndata: {data}\n\n"` 就是 `from_history.py:224`（`build()`）里现成的组装方式，直接对应 `Interaction.chunks` 的一个元素。
- `data_bytes`：不是 cassette 直接需要的字段，是第4节体积估算/reaper 决策需要的元数据，避免每次要估算容量都要解压全部 BLOB。

此外，`entries` 表本身建议新增：

```sql
ALTER TABLE entries ADD COLUMN request_body_digest TEXT;   -- 对应 Interaction.request_shape.digest
ALTER TABLE entries ADD COLUMN authenticated INTEGER;      -- 对应 Interaction.authenticated
```

`request_body_digest`：本项目已经有 `request_payload` 整体，理论上可以现算 sha256，不必新增列——但如果 reaper 会先删 `request_payload`（比如出于合规只留 usage 摘要）而单独保留帧，这一列就是「日后仍能重建 `request_shape` 摘要」的唯一途径；**这是否需要取决于 reaper 策略是否会拆开这两者的生命周期，本报告不替用户裁决，只标出这个分叉**。

`authenticated`：现状 `HistoryEntry`/`entries` 表完全没有这个字段，而这恰恰是 cassette 用来发现「代码停止认证」这类回归的手段（`cassettes.py:239-241`）。补一个布尔列成本很低。

不需要补的：`v3_operations.manifest_gz`（对象句柄映射）和 `v3_timeline_chunks`（分块时间线）这两层间接结构，在 copilot-api-js 里存在是因为它的对象仓库是**跨操作共享、按内容寻址去重**的通用存储，一个 operation 只是「引用了一批 handle」。本项目没有理由复制这层去重设计——一个 `entry_id` 只属于一次请求，`upstream_frames` 直接以 `entry_id` 为外键即可，用不上单独的 manifest/handle 间接层。这是"最小"增量故意省略的部分。

## 4. 体积估算

**基准 1（checked-in cassette 的真实字节，任务要求的基准）**：`tests/cassettes/` 现有 5 个文件，对每个文件把 `chunks` 还原成原始 SSE 字节、用 zstd level 3 重新压缩：

| 文件 | 文件字节 | 还原后原始 SSE 字节 | zstd level3 压缩后 | 压缩比 |
|---|---|---|---|---|
| anthropic_to_responses_stream.json（真实录制，PONG） | 83,628 | 73,143 | 20,516 | 3.57 |
| history_anthropic_stream.json（history 派生，已脱敏） | 7,579 | 4,872 | 557 | 8.75 |
| history_responses_stream.json（history 派生，已脱敏） | 67,770 | 53,710 | 2,611 | 20.57 |
| responses_web_search_nonstream.json（真实录制） | 5,653 | 4,124 | 2,287 | 1.80 |
| responses_web_search_stream.json（真实录制） | 19,317 | 16,171 | 7,722 | 2.09 |

**history 派生的两个文件因为脱敏把所有自由文本换成字面量 `"placeholder"`，压缩比虚高（8.75×、20.57×），不能代表真实内容的压缩表现**——这是脱敏的副作用，不是真实上游文本的密度，权重：**方法论警告，非估算依据**。

**基准 2（真实生产流量交叉验证，未脱敏）**：直接从 `history-v3.db` 里随机取 25 条真实的 `anthropic-messages` 流式请求，重放 `from_history.py` 的帧提取逻辑但跳过 `_scrub()`，得到未脱敏的真实原始帧，逐条 zstd level 3 压缩：

- N=25，平均每请求原始 SSE 字节 = 27,154 字节，平均压缩后 = 3,592 字节，平均压缩比 7.56×（单条压缩比从 2.3× 到 18.2× 不等，长尾很宽——工具调用/长回复的请求原始体积可达 6-9 万字节）。
- 换算：**1000 条请求 ≈ 27.2 MB 原始 / 3.6 MB（zstd level 3 压缩后）**。

权重：**N=25 的真实生产样本，量级可信（同一数量级不会错），具体系数（3.6MB/1000条）只是点估计，不同工作负载（重工具调用 vs 简单问答）会有数倍摆动**。

这决定 reaper 上限怎么定的含义：如果 `upstream_frames` 表按 3.6MB/1000 条的量级设计，即使 reaper 保留 10 万条「已完成」记录也只是约 360MB 压缩后数据，量级上完全可控；真正的容量风险来自**长尾**（单条 9 万字节原始的请求不罕见，×压缩比低谷 2.3× 约等于单条 4 万字节压缩后），如果 reaper 只按「条数」限制而不设「总字节数」上限，长尾请求可能让 100 条记录占的空间等于 1000 条中位数请求——**建议 reaper 至少同时看条数与压缩后总字节数两个维度**，这是本报告基于以上真实分布提出的建议，未经用户裁决。

## 5. 结构性规避 from_history.py 的两个坑

两个坑（均为已确认事实，来自 `from_history.py:14-19` 注释和 `cassettes.py:8-11` 注释）：

1. 同一事件被存了 3-4 份——一次原始到达，若干次每个 client-side transform 各存一份改写后的副本。
2. 存下来的副本已经过 `rewrite-out:responses-fix-stream-ids` 修复，正好抹掉了 cassette 想要捕捉的「上游 `output_item.added` 与 `output_item.done` 之间 id 不稳定」现象。

本项目管线里，从上游字节进入自己的代码，到帧被消费为止，只有**一条路径、一个消费者**：

- `response.aiter_bytes()` 在 `src/app/server/pipeline_app.py:274` 交给 `_counted_upstream()`（同文件 347-352 行）——纯粹的字节计数直通生成器，`async for chunk in chunks: ...; yield chunk`，不做任何解析或改写。这是上游字节进入本项目代码后的**第一个可介入点**。
- `_counted_upstream` 的输出交给 `stream_delivery()`（`src/app/pipeline/delivery/stream.py:102`），内部通过 `read_events(chunks)`（`src/app/pipeline/delivery/sse_source.py:65-87`）解析成 `SseEvent(event, data)`，**一次解析产生一份，不重复、不分叉**——`iter_frames`/`parse_frame`（`sse_source.py:35-63`）是唯一的帧切分逻辑。
- 解析出的 `SseEvent` 交给 `assembler.push(event)`（`ResponsesAssembler`/`AnthropicAssembler`，`src/app/pipeline/delivery/assembler.py`），这里对 `item_id`/`item.get("id")` 做的是**配对容忍**（`assembler.py:245-246`：`item.get("id") or data.get("item_id")` 兜底取值），而不是「先改写成一份新的稳定 id、再往下传」。也就是说，本项目结构上没有一个独立的「id 修复」transform 阶段——不稳定性在 assembler 里被就地兼容，从未产生过第二份「修复后的帧副本」。

**因此，只要把帧记录点放在 `read_events` 产出 `SseEvent` 的那一刻（`sse_source.py:78-80` 附近，或等价地包一层订阅者），就天然满足**：
- 只有一份记录，因为只有一个解析点、没有下游 transform 会再产出竞争性的副本（不存在 copilot-api-js 那种「记录每个 transform 输出」的历史设计）；
- 记录的是「上游实际发送的」帧，而不是经过 id 归一化之后的版本，因为 assembler 的归一化发生在记录点**之后**、且是运行时兼容而非落盘改写。

具体接入方式（设计建议，未实现）：在 `read_events`（或 `stream_delivery` 内部包一层）旁路订阅每个 yield 出的 `SseEvent`，异步喂给 `HistoryWriter`（类似现有 `submit_nowait`，discardable，不阻塞交付路径），写入第3节建议的 `upstream_frames` 表，`sequence` 用简单自增计数器（无需全局时间线序号，因为一个 `entry_id` 只对应一次请求内的严格到达顺序）。**不要**在 `assembler.push` 之后再记一份「装配后」的帧——那正是 copilot-api-js 掉进去的坑：一旦装配/翻译层也被当成一个记录点，就会诱使未来某次重构在两处都记，从而重新制造重复与「哪份是原始」的歧义。

## 未采纳/待裁决事项

- `request_body_digest` 是否需要独立列，取决于 reaper 是否会让 `request_payload` 和 `upstream_frames` 有不同的生命周期——未问用户，本报告只标出分叉，不擅自决定。
- reaper 按「总字节数」而非仅「条数」限流——本报告基于真实分布提出的建议，尚未经用户裁决，未采纳/未实现。
- zstd 压缩级别沿用「level 3」是任务给定的假设参数，本报告未测试其他 level（如 level 9/19）的体积/CPU 权衡——**未验证**，如需要可另行测量。
