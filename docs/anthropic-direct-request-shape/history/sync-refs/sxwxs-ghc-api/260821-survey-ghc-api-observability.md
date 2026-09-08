# sxwxs/ghc-api 的可观测性、请求历史、统计与基准调研

调研对象为只读工作树 `/home/xp/.claude/jobs/89874ec2/tmp/ghc-api`，Git HEAD 为 `0cb1087c389d9948af580e90019cfde069444ed1`。以下所有“代码事实”均指该精确版本；“我方”指 `/home/xp/src/ghc-api-proxy-py`。本报告的判断权重含义是：`强到可直接采纳` 表示有明确代码路径且与我方既定立场兼容；`是个倾向、需更多样本` 表示设计值得作为候选，但收益取决于尚未观测的规模或我方现状；`仅存档、不据以决策` 表示仅说明该项目做了什么，不能支持迁移结论。

## 结论先行

`request_file_stats.py` 的 README 自述大体属实，但有两个重要限定：它用 `size + mtime_ns` 做快速命中，不看 inode；追加模式仍须哈希旧文件全部既有字节并复制整份 sidecar，因此不是 O(追加量) 的纯增量；并且它只验证 sidecar 的存在、字节长度和 metadata 形状，不能在“sidecar 内容被等长篡改或写坏”时自动重建。对于已拥有 SQLite 请求历史的我方，这套 JSONL sidecar 索引没有足够收益，除非主会话确认 SQLite 不保存统计必需字段、而历史 JSONL 才是不可替代的权威源。

`RequestCache` 名称容易误导：它不是响应复用缓存，而是进程内最近 1000 条请求尝试的 FIFO 观测缓冲，同时承载重启即失的累计计数器。它以一个全局 `threading.Lock` 包住写入、聚合、搜索和列表复制；读取还直接返回内部可变对象。不能把这个结构照搬到我方已有 SQLite 历史与聚合记录模型中。

真正值得借鉴的不是 dashboard 的图形本身，而是“分布桶 → 精确贡献请求 → 原始记录详情”的诊断闭环，以及把 cache write、cache read、未缓存输入、输出分开显示的字段语义。前者在 SQLite 中应直接通过历史记录主键或稳定 locator 实现，不需要另起 sidecar。

token reporter 不做本地 tokenizer 估算，而是把各 handler 已从上游 `usage` 取出的累计数按 5 分钟差分写 JSONL；上游漏报会被静默记录为 0，真 0 与未知不可区分。其 Responses 映射还疑似把 `input_tokens_details.cached_tokens` 放进 `cache_creation_input_tokens`，并遗漏 `cache_read_input_tokens`，不应复用其字段映射。

E2E benchmark 的工程卫生优于普通孤立微基准：真实 CLI 进程、同一 fake backend、direct baseline、预热、并发、p50/p95/TTFB/RPS、CPU/RSS、多 trial 和轮换实现顺序均在代码中。但 fake backend 是手写且不校验上游输入，load generator 也不校验语义输出；所以它有能力发现本机该构建下的明显性能回归，却不能证明真实 Copilot 行为、正确性、跨实现公平性，亦不能证明哪个项目“更快”是语言或架构的因果结论。

## 1. 请求落盘与 `request_file_stats.py`

### 1.1 daily `.jl` 的格式、轮转和写入时机

**发现 1：请求落盘是每次 `complete_request` 后，将已完成的 cache 条目整体 JSON 编码为一行，按本机当地日期分文件；没有按文件大小、条数或 UTC 轮转。** 权重：`强到可直接采纳`。

证据：`ghc_api/cache.py:283–286` 在释放锁后调用 `_append_request_to_daily_file(entry_snapshot)`；`ghc_api/cache.py:342–353` 的关键代码如下。

```python
requests_dir = os.path.join(get_config_dir(), "requests")
os.makedirs(requests_dir, exist_ok=True)
daily_file = os.path.join(requests_dir, f"{datetime.now().strftime('%Y-%m-%d')}.jl")
with open(daily_file, "a", encoding="utf-8") as f:
    f.write(self.format_request_jsonl_line(request_entry))
```

`ghc_api/cache.py:358–360` 规定格式为 `json.dumps(request_entry, ensure_ascii=False) + "\n"`。这意味着记录包含 cache entry 的 `request_headers`、`original_request_body`、`request_body`、`response_body` 或 `raw_events` 等字段，字段集可随未识别 sidecar 字段扩展，见 `ghc_api/cache.py:186–198`。因此它不是一个仅含观测标量的日志格式，而是完整（但可能截断）的请求诊断记录。

**发现 2：落盘承袭的是内存 cache 的正文上限，而非独立的落盘保留策略；写入失败被 `print` 后吞掉，且没有 `flush`/`fsync`。** 权重：`强到可直接采纳`，但结论是“不应照抄”。

证据：`ghc_api/cache.py:58–74` 在 `request_size` 或 `response_size` 超过 `max_request_size` 时，把正文替换为 `{"_truncated": True, ...}`；`ghc_api/cache.py:126` 和 `198` 在 entry 入 cache、完成时调用它。`ghc_api/cache.py:342–355` 的外围为：

```python
try:
    ...
    with open(daily_file, "a", encoding="utf-8") as f:
        f.write(self.format_request_jsonl_line(request_entry))
except Exception as e:
    print(f"[Request File Logging] Failed to append request: {e}")
```

这不是基于威胁模型的脱敏，而是内存/文件容量截断；但它把“查看请求正文”的完整性与 cache 上限耦合，并在持久化失败后继续提供看似正常的内存观测。对于我方，既有 SQLite 历史应保持其自身的明确持久化语义，不能因为要加一个 dashboard 而复制此双重语义。

### 1.2 README 的 sidecar 自述核验

README 的原始自述在 `README.md:363–367`：称每个 request file 有轻量 JSONL sidecar 与 metadata；sidecar 存标量指标及 source offset/length/hash，不存 body/header；未变文件不重开；追加增量；截断、替换、损坏或不兼容时安全重建；详情以 SHA-256 验证且单行展示上限 4 MiB。

**发现 3：sidecar 确实不复制请求/响应 body 或 header，且持久化行含稳定 locator、请求身份与统计维度；README 所谓“scalar metrics”属实但不完整。** 权重：`强到可直接采纳`。

证据：`ghc_api/request_file_stats.py:284–341` 的 `_extract_index_row` 写入的核心字段为：

```python
"source_file": source_file,
"offset": offset,
"length": length,
"line_sha256": hashlib.sha256(raw_line).hexdigest(),
"id": str(entry.get("id") or ""),
"timestamp": _normalize_timestamp(entry.get("timestamp")),
"effective_model": _effective_model(entry),
"endpoint": str(entry.get("endpoint") or ""),
"status_code": _effective_status_code(entry),
"duration_ms": duration_ms,
"request_size": request_size,
"response_size": response_size,
"user_id": str(entry.get("user_id") or "anonymous"),
"client_ip": str(entry.get("client_ip") or "unknown"),
```

并带各 token 指标及 bucket。这里没有 `request_body`、`response_body`、`raw_events`、`request_headers`，所以 README 的“不复制正文/headers”与代码相符；但它也存了 `id`、model、endpoint、user、client IP 等定位/分组字段，不能严格描述成“只存标量指标”。

**发现 4：未变文件的快速命中判据严格是 source `st_size` 与 `st_mtime_ns` 同时相等；不比较 inode，也不在该快速路径重新哈希或打开 source 内容。** 权重：`强到可直接采纳`。

证据：`ghc_api/request_file_stats.py:540–562`：

```python
stat = request_path.stat()
snapshot_size = stat.st_size
...
if meta is not None and meta["size_bytes"] == snapshot_size and meta.get("mtime_ns") == stat.st_mtime_ns:
    if progress is not None:
        progress("cached", snapshot_size, snapshot_size)
    return meta, "cached", warnings
```

metadata 保存 `mtime_ns`、`size_bytes`、`content_sha256`，见 `ghc_api/request_file_stats.py:517–537`，但 fast path 不读 hash，也没有 `st_ino`。测试把 source 的 `Path.open` 改为失败后仍获得 `cached`，直接印证“不重开 source”：`tests/test_request_file_stats.py:108–122`。

正常编辑/替换会改变 mtime 或 size，随后进入内容 hash 分支；但若某外部写入刻意或异常地保持相同 size 与纳秒级 mtime，或发生 inode 替换而这两值巧合相同，代码会误判缓存有效。这是准确的实现边界，不是推定攻击模型。

**发现 5：追加判定不是 mtime 或 inode，而是“新 size 大于旧 size，且新文件前 `old_size` 字节的 SHA-256 与 metadata 的完整旧内容 hash 相同”；尾部才会被 JSONL 扫描。** 权重：`强到可直接采纳`。

证据：`ghc_api/request_file_stats.py:564–577`：

```python
if meta is not None and snapshot_size > meta["size_bytes"]:
    old_content_matches = _content_signature(request_path, meta["size_bytes"]) == meta["content_sha256"]
    if old_content_matches:
        mode = "incremental"
```

`_content_signature` 从 offset 0 起分块读完指定长度并做 SHA-256，见 `ghc_api/request_file_stats.py:373–383`。增量时它先完整复制旧 sidecar，再从 `meta["processed_bytes"]` 扫描 source 到当前 `snapshot_size`，见 `ghc_api/request_file_stats.py:606–630`。测试验证追加后不重复、旧行 offset 保持：`tests/test_request_file_stats.py:124–137`；未换行的 partial tail 则不入索引，等换行后才被增量读入：`tests/test_request_file_stats.py:139–149`。

因此 README 的“append-only growth is indexed incrementally”在“避免重新 JSON 解析旧记录”意义上成立；但它仍为验证前缀而读取并哈希全部旧 source，且复制完整旧 sidecar。它不是仅随追加大小增长的 I/O 算法。对大日文件反复刷新统计时，这一限定决定了真实收益。

**发现 6：截断、普通替换、同 size 内容变化和 metadata 不兼容会触发 rebuild；建立过程使用临时文件、`fsync`、`os.replace`，取消时不会替换旧 sidecar。** 权重：`强到可直接采纳`。

证据：source 变小会记录 `source_shrank` 并 rebuild，见 `ghc_api/request_file_stats.py:578–583`；size 相等且 hash 不同会记录 `source_changed` 并 rebuild，见 `585–599`；schema/source/meta 字段、hash 格式、quality 计数、sidecar 缺失或 size 不匹配会在 `_load_meta` 抛 `RequestIndexValidationError`，见 `415–445`，调用者在 `552–557` 把它转成重建 warning。重建写入 `mkstemp` 临时文件、`flush`、`os.fsync`，之后原子替换 index、再原子写 meta，见 `601–671`；取消测试证明旧 sidecar 字节未变，见 `tests/test_request_file_stats.py:164–173`。

**发现 7：README 的“损坏则安全重建”表述过强。metadata 或 sidecar 长度异常会重建，但 sidecar 内容若仍等长，fast path 不解析 sidecar；之后 dataset load 才可能因坏行失败，且不会回到 rebuild。** 权重：`强到可直接采纳`。

证据：`_load_meta` 只验证 metadata JSON、版本、字段、hash 格式以及 `index_path.stat().st_size == meta["index_size_bytes"]`，`ghc_api/request_file_stats.py:415–445`；fast path 随即返回 cached，`559–562`。sidecar 每行 JSON/schema 的实际检查发生在后续 `_load_dataset`，`ghc_api/request_file_stats.py:968–987`：

```python
row = json.loads(line)
if not isinstance(row, dict) or row.get("schema_version") != INDEX_SCHEMA_VERSION:
    raise RequestIndexValidationError(...)
```

这里没有让 `build_or_load_file_index` 重建的回路。等长 bit corruption 亦不改变 sidecar size。因此 README 对“corrupt”的承诺只在 metadata parse、sidecar 缺失、长度不符等已覆盖类别成立；不能概括为任何损坏都自动修复。`tests/test_request_file_stats.py:108–173` 覆盖未变、追加、partial tail、source replacement、cancel，但这段范围内没有 sidecar 内容损坏自动重建测试。

**发现 8：详情链接的 SHA-256 与 4 MiB 上限确实实现；它先在 sidecar 找精确 locator，再 seek 原文件并复核行长度和 hash。** 权重：`强到可直接采纳`。

证据：`ghc_api/request_file_stats.py:31–32` 定义 `MAX_DETAIL_LINE_BYTES = 4 * 1024 * 1024`；`1257–1279`：

```python
if length > MAX_DETAIL_LINE_BYTES:
    raise RequestStatsValidationError(...)
if not _sidecar_contains_locator(filename, offset, length, sha256):
    raise RequestStatsValidationError(...)
with request_path.open("rb") as file:
    file.seek(offset)
    raw = file.read(length)
if len(raw) != length or hashlib.sha256(raw).hexdigest() != sha256:
    raise RequestFileChangedError("The request file changed; rebuild its statistics index")
```

`_sidecar_contains_locator` 本身逐行读 sidecar 查 offset/length/hash，见 `1238–1254`，并不是索引内的二分查找。测试覆盖 locator 不存在及原文件改动后报告 `RequestFileChangedError`：`tests/test_request_file_stats.py:221–233`。

### 1.3 相对 SQLite 的真实收益与我方判断

**发现 9：sidecar 的真实优势是把一个既有、可顺序追加的 JSONL archive 转为“轻量行级统计投影 + 可回跳原记录”，避免把完整 body 再装入统计 dataset；它不是通用数据库替代品。** 权重：`是个倾向、需更多样本`。

证据：`ghc_api/request_file_stats.py:801–930` 的 `RequestStatsDataset` 仅保留 sidecar rows，按 model、status code、metric bucket 建 position 列表，bucket drill-down 返回 summary 和 `detail_url`；`968–989` 还明确限制 `MAX_DATASET_ROWS = 1_000_000`、估算内存 `256 MiB`，常驻只缓存最多 3 个 dataset、TTL 900 秒，见 `39–42`、`933–965`。这说明设计目标是离线文件统计的按需投影，而不是提供自由查询。

代价同样明确：每次追加检查要哈希旧 source 全长，增量要复制整份 sidecar，见发现 5；统计 dataset 仍把所选所有 sidecar rows 读入内存并排序，见 `968–989`；筛选维度固定为 overall/model/status/bucket，不能像 SQLite 索引那样按新字段直接查询。

对我方的判断：**不值得移植 sidecar 索引。** 我方已明确有 SQLite 请求历史，且既定原则是展示层读聚合记录、同一事实不在两条交付路径各推导一次。SQLite 可以让请求历史主记录、统计聚合和 drill-down 以同一持久化事实工作，避免 JSONL source、sidecar metadata、内存 dataset 三层一致性问题。只有在主会话核对后发现“SQLite 并不保存某项统计需要的 proxy↔upstream 标量，且已有不可替代的 append-only JSONL 作为权威 archive”时，才值得采用“轻量投影 + 记录 locator”这一思想；即使如此，应优先补 SQLite schema/index，而不是复制该 O(旧文件长度) 校验路径。

## 2. `cache.py`：它不是响应复用 cache

**发现 10：`RequestCache` 是按插入顺序 FIFO 淘汰的进程内观测历史，不是 LRU，也没有任何“命中后重用上游响应”的读取路径。默认最多 1000 entry。** 权重：`强到可直接采纳`。

证据：`ghc_api/cache.py:36–40` 定义 `max_entries=1000`、`OrderedDict` 和一个 lock；`97–126` 与 `199–230` 都在容量到达上限时执行：

```python
if len(self.cache) >= self.max_entries:
    self.cache.popitem(last=False)
self.cache[request_id] = {...}
```

代码从不在 `get_request` 后向客户端返回先前响应；`ghc_api/cache.py:375–378` 仅是普通字典取值，调用它的 dashboard detail endpoint 是 `ghc_api/routes/dashboard.py:608–640`。反之，流 handler 每个请求仍明确走 `start_request → SENDING → RECEIVING → complete_request`，见 `ghc_api/sse/base.py:12–14`、`194–244`。所以“cache”准确含义是最近请求/响应对的 ring-like history buffer，而非 memoization。

**发现 11：锁粒度是单一全局 `threading.Lock`；写入、全局/用户聚合、搜索时的 JSON 序列化、列表复制都在锁内，落盘刻意在锁外。** 权重：`强到可直接采纳`。

证据：`ghc_api/cache.py:39–40` 的 `self.lock = threading.Lock()`；`146–283` 将 entry 更新、`request_count`、bytes、model/endpoint/per-user stats 以及 `entry_snapshot = dict(...)` 一并包在 `with self.lock` 内；`285–286` 才落盘。`472–506` 的 `search_requests` 和 `fulltext_search` 也在锁内遍历全部最多 1000 条，并对 request/response body `json.dumps`：

```python
with self.lock:
    for item in reversed(list(self.cache.values())):
        ...
        request_body_str = json.dumps(item.get("request_body", {})).lower()
```

这能保证 Python 线程下内部状态修改一致，但大 body/full-text search 会占用同一 lock，阻塞所有请求状态更新。对于上限 1000 的单进程 Flask 应用是简单取舍；不是可扩到我方生产路径的锁模型。

**发现 12：对外读取不是不可变 snapshot，`get_request` 和列表中的 entry 都把内部对象直接交给调用者；cache 同时保存正文、raw SSE payload、headers、状态、token、字节和 duration。** 权重：`强到可直接采纳`。

证据：`ghc_api/cache.py:375–386` 返回 `self.cache.get(request_id)` 和 `items[...]`，没有 `dict`/deep copy；entry 字段可见 `103–125` 与 `151–198`。streaming entry 将所有上游 `data:` payload 原样累计为 `raw_events`，`ghc_api/sse/base.py:5–12`、`101–119`；完成时传给 cache，`217–244`。这解释 dashboard 能展示完整请求/响应，但也说明它让展示读原始可变对象，与我方“展示层读聚合记录”的既定边界相反。

## 3. dashboard：有用视图与应避免的部分

**发现 13：基础 dashboard 的有用信息是按 model 与 endpoint 的请求数、token 分层、发往上游的 bytes、以及最近请求的状态/HTTP status/duration/request-response size；它把累计总量与最近缓存量并列。** 权重：`是个倾向、需更多样本`。

证据：路由 `ghc_api/routes/dashboard.py:447–452` 直接组合 `cache.get_stats()` 与 `counters.snapshot()`。model 和 endpoint 聚合结构由 `ghc_api/cache.py:238–280` 更新；HTML 表列明确是 `Model, Requests, Input Tokens, Cache Create, Cache Read, Output Tokens, Data Sent, Data Received`，`ghc_api/templates/dashboard.html:520–558`。最近请求列为 `Timestamp, Model, Endpoint, State, Status, Duration, Request Size, Response Size`，`581–602`；前端从 API 填入 total requests、bytes sent/received、cached requests，`719–766`。

其中最有诊断价值的字段是：终态/HTTP status 与 duration 的组合、请求和响应字节、model/endpoint 维度、以及四段 token（未缓存输入、cache write、cache read、输出）。这些都能回答“代理到上游的哪段变慢、哪个模型/endpoint 有失败或异常体积、缓存计费组成是否变化”。我方已决定日志/footer 的观察范围为 proxy↔upstream，采用这些字段时应明确用实际发往上游的 bytes、上游终态与相应耗时，而不混入客户端显示或 cache 内存占用。

**发现 14：最值得借鉴的交互闭环是持久历史统计页的“总体/按 model/按精确 status code → 请求大小、duration、token 分布 → 点选 bucket → 贡献请求 → 原始详情”。** 权重：`强到可直接采纳`，但应使用 SQLite 实现。

证据：`ghc_api/templates/request_stats.html:180–250` 定义三个 view 与三类分布、model 对比、精确 response code 对比和 matching requests；特别写明精确 code 保留 rate limit、取消与 upstream failure 的区别：

```html
<h3>Response code comparison</h3><p>Exact codes preserve the distinction between rate limits, cancellations, and upstream failures.</p>
```

后端的 bucket 查询 endpoint 在 `ghc_api/routes/dashboard.py:498–523`，`RequestStatsDataset.query_bucket` 由 bucket position 和 model/status position 做交集，`ghc_api/request_file_stats.py:840–901`，再通过 `detail_url` 回原记录。它是一条可操作的异常定位链，而不是只展示好看的平均值。

我方值得借鉴的是这条交互语义，而不是 sidecar：若 SQLite 历史已经有稳定 request id/row id 与聚合记录，应让 histogram bucket 返回这些 ID，详情页读取同一历史记录；“同一事实只推导一次”的规则要求 metrics 在 `RequestLine` 或等价聚合记录生产时确定，而不是 dashboard 再从 raw payload 重算。

**发现 15：`Proxy Activity` modification counters 对排查“代理到底改了什么”有一定价值，但只有启动以来的绝对计数、会随重启归零，且不带请求分母或时间窗，不能单独判断异常率。** 权重：`是个倾向、需更多样本`。

证据：`ghc_api/templates/dashboard.html:560–579` 明说“Counts are global and reset on restart”；`772–804` 列举 `ping_sent`、`ping_received`、system prompt 修改、tool recovery、model mapping、Web IQ 成功/失败等 counter 标签。`ghc_api/routes/dashboard.py:447–452` 每次返回当前 `counters.snapshot()`，没有时间序列/窗口。可采纳的部分是把明确的兼容性变换作为可观测事件；不应把无分母的 lifetime 数字当作健康指标。是否需要把我方已有日志行中的事件另做聚合，需主会话核对，不能从本报告推定。

## 4. `token_usage_reporter.py`：token 来源与缺失语义

**发现 16：reporter 不导入 tokenizer、不从 prompt/body 重新估算 token；它完全消费 cache 内由 upstream `usage` 填入的累计计数，并每 300 秒按 `(user_id, model)` 做正差分写 JSONL。** 权重：`强到可直接采纳`。

证据：`ghc_api/token_usage_reporter.py:18` 只导入 `.cache`，全文件没有 tokenizer 库；`25–39` 以初始 `cache.get_user_model_token_snapshot()` 建快照并启动间隔线程；`60–113` 计算 current−previous：

```python
current = cache.get_user_model_token_snapshot()
delta_input = max(0, int(now.get("input_tokens", 0)) - int(prev.get("input_tokens", 0)))
...
delta_total = delta_input + delta_cache_create + delta_cache_read + delta_output
...
payload = {"timestamp": ts, "user_id": user_id, "models": models}
```

流式基类把 handler 的四个累计字段原样交给 `cache.complete_request`，`ghc_api/sse/base.py:115–119`、`217–244`。例如 Anthropic direct handler 从上游 `message_start.message.usage` 和 `message_delta.usage` 取字段，`ghc_api/sse/anthropic_direct.py:49–59`；Responses handler 从 terminal `response.usage` 取字段，`ghc_api/sse/openai_responses.py:178–185`。这满足“不用本地 tokenizer 制造伪精确值”的工程取向。

**发现 17：上游不报 usage 时，该项目把缺失当 0，既不估算也不保存“unknown/missing usage”标志；因此 0 与未观测在统计上不可区分。** 权重：`强到可直接采纳`。

证据：四个 stream accumulator 初始化为 0，`ghc_api/sse/base.py:115–119`；Responses handler 用 `response.get("usage", {}) or {}` 和 `.get(..., 0)`，`ghc_api/sse/openai_responses.py:178–185`；cache 完成时又以 `data.get(..., 0)` 计入聚合，`ghc_api/cache.py:173–180`、`250–256`。reporter 遇到 zero delta 不写该 model line，`ghc_api/token_usage_reporter.py:73–86`。README 也只提示 failed attempts“commonly record zero usage tokens”，`README.md:367`，没有缺失标记。

这对我方的借鉴结论是：只借“上游 reported usage 是唯一 token 事实源”，不要照抄“缺失即 0”。我方若要展示 token 字段，应在聚合记录中表达 `reported` 与 `not reported` 的区别，或者干脆不显示该项；具体字段模型需主会话核对既有 SQLite schema 后裁定。

**发现 18：Responses usage 的 cache 字段映射看起来错误或至少未被命名所证实：它把 `input_tokens_details.cached_tokens` 计为 `cache_creation_input_tokens`，并不设置 `cache_read_input_tokens`。** 权重：`强到可直接采纳`，结论是“不应照抄”。

证据：`ghc_api/sse/openai_responses.py:178–185`：

```python
usage = resp.get("usage", {}) or {}
self.input_tokens = usage.get("input_tokens", 0)
self.output_tokens = usage.get("output_tokens", 0)
details = usage.get("input_tokens_details", {}) or {}
self.cache_creation_input_tokens = details.get("cached_tokens", 0)
```

相同逻辑存在于 `ghc_api/sse/proxy_responses.py:28–35`。反而 OpenAI Chat 的转换把同名 `cached_tokens` 显式放在 `cache_read_input_tokens`，`ghc_api/streaming.py:33–50`、`138–151`。这至少造成同一语义在不同路径中分到不同统计列；若 `cached_tokens` 的通常含义是读取命中缓存，Responses 路径更可能是错列。报告不据此推断真实 Copilot 字段含义，但代码自相矛盾已经足以否决直接复用该映射。

**发现 19：跨机器 token overview 是读取各机器 `token_usage.jl` 后按 machine/model/user 聚合，并对旧行重新计算 total；坏 JSONL 行和整文件读错会被静默跳过。** 权重：`仅存档、不据以决策`。

证据：`ghc_api/token_usage_reporter.py:192–209` 从 OneDrive agents 或本地 fallback 找文件；`291–377` 对每行 `json.loads` 失败 `continue`、外层文件异常也 `continue`，再以 `input + cache_creation + cache_read + output` 重算 total，`349–375`。这是一套跨机器人工汇总需要的 append-only delta 格式；我方项目背景未说明有该需求，不能把它当作应实现功能。

## 5. `benchmarks/e2e/`：比较对象、负载与分辨力

### 5.1 它实际测量什么

**发现 20：单项目 runner 测 ghc-api 的真实 CLI 进程相对直连 fake backend 的增量开销，并分别打开 baseline、request-file logging、tool-call recovery 三个变体。** 权重：`强到可直接采纳`。

证据：`benchmarks/e2e/runner.py:275–335` 启动 fake backend，再为每一变体起 `python -m ghc_api.cli`，对 direct fake URL 和 proxy URL 各跑同一 scenario；变体定义在 `279–283`：

```python
variants = [
    {"name": "baseline"},
    {"name": "request-file-logging", "save_request_to_file": True},
    {"name": "tool-call-recovery", "enable_tool_call_recovery": True},
]
```

请求发生器从请求开始到读到 `[DONE]`、`message_stop` 或 `response.completed` 计 latency，首个 `iter_lines()` 行计 TTFB，`runner.py:63–95`；输出 mean/p50/p95/p99/max、RPS、bytes，`110–132`。可选 `psutil` 还统计 proxy process CPU seconds、RSS delta 和 thread 数，`189–211`。

**发现 21：比较脚本同时测 ghc-api 与 `puxu-msft/copilot-api-js` 的 production bundle，保留 commit/version、使用相同 nominal payload、history retention=1000，并做预热、多 trial、实现顺序交替与每 trial 内 direct baseline。** 权重：`强到可直接采纳`。

证据：`benchmarks/e2e/compare_copilot_api_js.py:291–333` 配置 Python 与 JS 进程；Python 的 `cache_max_entries = 1000` 在 `291–296`，JS `history.success_limit/failure_limit = 1000` 在 `308–316`。测量循环的关键实现为 `341–363`：

```python
for trial in range(trials):
    direct = _run_load(fake_url, scenario["payload"], ...)
    ordered = implementations if trial % 2 == 0 else list(reversed(implementations))
    for implementation, process, port in ordered:
        proxy, metrics = _run_measured_load(process, proxy_url, scenario["payload"], ...)
```

默认 60 requests、5 warmup、3 trials、并发 `[1, 8]`，`255–266`；汇总对每 trial 的 `proxy − direct` overhead 取中位数，而不是把 raw latency 直接相减，`178–210`。输出还记录 JS repo commit、commit date、version 与启动 URL override，`369–391`。这些是可复现实验记录的实质内容。

**发现 22：负载覆盖两个全功能流式场景：Anthropic `/v1/messages` 与 OpenAI `/v1/responses`，各带工具定义、1 KiB 文本、16 text chunks、tool argument chunks；fake backend 可以受 metadata 控制文本/参数大小和每块 delay。** 权重：`强到可直接采纳`。

证据：scenario payload 在 `benchmarks/e2e/runner.py:214–238`；fake 参数解析与上限在 `fake_backend/app.py:39–52`，SSE 每个 event 的 `ttft_ms`/`chunk_delay_ms` 实现于 `82–100`。Responses fake stream 覆盖 reasoning、function call、web search、output text、annotations、completed event，`246–313`；Anthropic fake stream 覆盖 thinking、text、tool use、usage 与 message stop，`339–388`。这比只回一个短 JSON 的 endpoint microbenchmark 更接近代理的编码、SSE 解析与转译热路径。

### 5.2 可比性做得怎样

**发现 23：同一 fake server、同一 client payload、同一预热/并发参数和 direct baseline，确实控制了若干本机噪声；脚本还可在测前/启动后等待低系统与 security CPU。** 权重：`是个倾向、需更多样本`。

证据：fake 仅启动一次并被所有实现使用，`compare_copilot_api_js.py:282–289`；两个实现复用 `_scenario_payloads()`，`341–354`；负载器先 warmup，再用固定 `ThreadPoolExecutor(max_workers=concurrency)`，`runner.py:135–142`。可选 idle 检查要求连续时间内 system CPU ≤35%、security CPU ≤10%，`compare_copilot_api_js.py:71–104`。脚本的自述也明确 fake backend 是共享瓶颈、应主要看配对 overhead，`235–251`。

这些措施足以让它作为“同一机器、该构建、该 fake profile 下的相对性能回归探针”。但没有提交的 `benchmarks/results/` 产物可供复核，本次只能评价 harness，不能背书任何未提供的数值结论。

**发现 24：该 benchmark 没有语义 oracle，因而不能证明两个 proxy 对同一负载正确，也不能证明 fake 所称的“同一个负载”在上游转换后真等价。** 权重：`强到可直接采纳`。

证据：`runner.py:63–95` 只在 HTTP status ≥400 时失败，并在读到一个终止 sentinel/event 后停止；它不比较下游内容、block/event 序列、tool arguments、usage、ID 关联或请求/响应 schema。fake route 也只取 `metadata`、`model`、`stream`：`fake_backend/app.py:487–508`，没有验证 proxy 送到 upstream 的 body 是否与协议契约等价。其文件头更明确承认响应 shape 为手写 inventory：`fake_backend/app.py:1–5`。

所以一个代理若在 converter 中漏掉 content、错误拼接 tool arguments、错标 usage，甚至向 fake 发出真实上游不会接受的形状，只要 fake 仍返回 completion，bench 仍会“绿”。这正是同源 fake/孤立性能结果的固有盲区：它能量到处理成本，不能成为正确性的 oracle。

**发现 25：跨项目“公平性”是有意保留各自实际 pipeline 的产品比较，而不是控制变量后的语言或 runtime 比较；因此任何“Python 比 JS 快/慢”的结论没有分辨力。** 权重：`强到可直接采纳`。

证据：compare report 自己写明 ghc-api 用 Flask threaded development server，copilot-api-js 用 `node dist/main.mjs`，并承认 JS 仍有 SQLite history 与更复杂 codec/observability、Python 是内存 cache，`compare_copilot_api_js.py:239–250`。实际配置也印证这一点，见发现 21。二者虽同为 1000 retention，但 retention 数量相同不等于写放大、索引、序列化、GC、服务器模型、功能复杂度相同。

这不是 benchmark 的“错误”——若问题是“用户部署这两个完整产品时的本机端到端开销”，保留完整 pipeline 合理；错误在于把结果归因为语言、SQLite、某个 codec 或单个实现选择。报告输出若没有限定为“此构建的产品栈比较”，就超出了该 harness 能支持的结论。

## 6. 明显不该照抄或过于笨重的部分

| 发现 | 证据 | 判断 | 权重 |
|---|---|---|---|
| 将请求历史、统计累计器、最近请求正文缓存、导出/导入和每日落盘集中在 `RequestCache` | `ghc_api/cache.py:36–52, 97–360, 513–608` | 职责耦合且重启丢累计数；展示读的是原始可变 entry，违背我方聚合记录边界。 | 强到可直接采纳 |
| 一个 global lock 覆盖 full-text search 的全量 `json.dumps` | `ghc_api/cache.py:472–506` | 对 1000 条且 body 很小时可接受，但不应放到代理请求状态的共享临界区。 | 强到可直接采纳 |
| JSONL sidecar 追加模式需哈希整个旧 source 且复制旧 sidecar | `ghc_api/request_file_stats.py:373–383, 564–577, 606–630` | “incremental”只减少 JSON 解析，不是低 I/O 增量。已有 SQLite 时徒增第三套物化状态。 | 强到可直接采纳 |
| sidecar integrity 仅以 metadata 和总长度检查 | `ghc_api/request_file_stats.py:415–445, 559–562, 968–987` | README 对任意损坏自动 rebuild 的表述不成立；没有校验每行或 sidecar content hash。 | 强到可直接采纳 |
| token missing 被静默零值化 | `ghc_api/sse/base.py:115–119; ghc_api/sse/openai_responses.py:178–185; ghc_api/cache.py:173–180` | 混淆“上游报告 0”与“没有观测到 usage”，会污染 billing/usage 结论。 | 强到可直接采纳 |
| Responses `cached_tokens` 进入 `cache_creation_input_tokens`，但 Chat 路径放 `cache_read_input_tokens` | `ghc_api/sse/openai_responses.py:178–185; ghc_api/streaming.py:33–50` | 映射自相矛盾；不能照抄，先针对我方上游 cassette/真实字段定语义。 | 强到可直接采纳 |
| dashboard 的 lifetime modification counter 无分母、无窗口 | `ghc_api/templates/dashboard.html:560–579, 772–830` | 可做调试线索，不可单独用于健康/失败率判断。 | 是个倾向、需更多样本 |
| hand-authored fake backend 加性能测试 | `benchmarks/e2e/fake_backend/app.py:1–5; benchmarks/e2e/runner.py:63–95` | 值得保留为性能回归 probe，但须与真实上游 cassette 的行为测试分工，不能充当正确性证明。 | 强到可直接采纳 |
| OneDrive 多机器 usage JSONL 汇总 | `ghc_api/token_usage_reporter.py:192–209, 291–377` | 只有明确跨机器汇总需求才有价值；我方是否有该需求需主会话核对。 | 仅存档、不据以决策 |

## 7. 面向我方的借鉴决策表

| 发现 | 我方是否值得借鉴 | 理由 |
|---|---|---|
| 将 proxy↔upstream 的 model、endpoint、upstream status、duration、实际 request/response bytes、四段 token 作为同一聚合记录的字段 | 值得 | 与我方日志/footer 范围和“展示读聚合记录”立场一致。token 的 `reported/missing` 语义不可抄 ghc-api 的 0 值做法。 |
| 历史统计的“bucket → 精确贡献请求 → 原始详情”诊断闭环 | 值得 | 能把异常分布转为可行动的请求定位；应以 SQLite 主键/稳定记录引用实现，不能再从展示层推导原始对象。 |
| 用精确 upstream response code 分组，而非只看成功/失败 | 值得 | 能区分 429、取消、连接/协议失败等不同处置方向；我方是否已记录完整上游终态需主会话核对。 |
| 将 cache write/read/uncached input/output 分开呈现 | 存疑 | 语义有诊断价值，但我方 OpenAI Responses 上游对各 usage 字段的稳定映射需先以既有 cassette/代码核对；ghc-api 自身映射不可靠。 |
| `RequestCache` 的 1000-entry FIFO 原始请求/响应缓冲 | 不适用 | 我方已有 SQLite 历史，且既定展示边界禁止原始对象成为多条交付路径的共同输入。 |
| JSONL request archive + metadata + sidecar statistics index | 不适用 | SQLite 已是更合适的统一事实源；该实现还反复全文件 hash、复制 sidecar，并有损坏检测缺口。若 SQLite 缺字段，先补 schema/index；需主会话核对字段现状。 |
| 5 分钟从进程累计值差分写 token JSONL | 存疑 | 只适合明确需要跨机器、append-only usage 汇总的场景；而且进程崩溃前未 flush 的窗口会丢失，缺 usage 会伪装成 0。是否存在跨机器需求需主会话核对。 |
| dashboard 的 raw body/full-text search | 不适用 | 与我方“展示层读聚合记录”的边界不符，并会把大 body JSON 序列化放到共享 cache lock 内。 |
| 把明确的协议修复/降级事件做计数 | 值得 | 适合作为调试线索；需与请求总数或时间窗一起解释，不能只提供 restart-reset 的绝对数。是否我方已有等价日志事件需主会话核对。 |
| 真实 CLI + direct baseline + warmup + 多并发 + 多 trial + 记录 commit 的 E2E 性能 harness 方法 | 值得 | 这是低成本、可复现的性能回归方法，但只可用于测性能；不要扩建证明基础设施，也不可取代针对真实上游 cassette 的行为验证。 |
| hand-authored fake backend 作为正确性或跨实现公平性的 oracle | 不适用 | 它不验证上游请求或下游语义输出，不能证明转换正确或真实 Copilot 兼容。现有我方 cassette 机制更适合承担真实上游行为断言。 |
