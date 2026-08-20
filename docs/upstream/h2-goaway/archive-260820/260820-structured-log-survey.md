# 结构化日志落点调研：现有可观测面 + 上游连接标识可行性

**日期**：2026-08-20
**任务**：为「四条流式请求是否共用同一条上游 H2 连接」这类事后问题找出最小可行的结构化日志落点。事故诊断见 `docs/agents/upstream-h2-goaway/findings.md`。
**性质**：只读调研，未修改任何既有文件。
**工作树**：`/home/xp/src/ghc-api-proxy-py`，HEAD 未变动。

---

## 0. 证据分级

本文每条结论都标了来源。三档：

| 标记 | 含义 |
|---|---|
| **【实测】** | 我在本机跑了脚本 / 命令，粘的是真实输出 |
| **【读码】** | 读源码得出，未执行验证 |
| **【未验】** | 推断或转述，不足以支撑决策 |

一次性 PoC 脚本在 `/tmp/h2connid_poc.py` 与 `/tmp/h2connid_poc2.py`，可重跑。

---

## 1. 结论速览

- **上游连接标识拿得到，而且不碰任何私有 API。**【实测】httpcore 1.0.9 把连接自己的 `network_stream` 对象放进 `Response.extensions`，H2 还额外放 `stream_id`；httpx 的连接池原样透传；openai SDK 的 `post(cast_to=httpx.Response)` 也原样透传。从 `network_stream.get_extra_info("client_addr")` 能读到本端 `(ip, port)`——那就是这条 TCP 连接在本机上的唯一名字。
- **本项目当前没有任何结构化日志落盘。** 明确的「否」。唯一落盘的结构化产物是 `rejection_capture` 写的 4xx 拒绝体（只在 `UpstreamRejected` 时触发，GOAWAY 这类传输层失败一条都不写）。
- **`log_format: "json"` 存在，但它解决不了这个问题，而且活链路根本到不了它。**【实测】JSON 模式只是给同一条**已渲染成字符串**的请求行套了个 5 键信封；没有 `request_id`，没有字段。且 `cli.py:249` 把 `log_format` 写死成 `"text"`。
- **推荐落点**：`_log_completion`（`src/app/server/pipeline_app.py:108`）。它已经是全部退出路径唯一汇合的那一点，已经构造了 `RequestLine` 这个聚合记录。把这条记录序列化成一行 JSON 追加到文件，就是全部工作——不需要第二套数据抽取。
- **一个已验证的坑**：TUI 的 `activate()` 会做 `root.handlers = [handler]`，把 root 上所有 handler 全换掉。【读码】所以「加一个 `FileHandler`」在有 footer 的那次运行里会被静默丢弃。这正是 `docs/agents/history-forensics/proposal.md` 4.4 节说的「另加一个 handler 并祈祷没人替换它」。

---

## 2. 现有可观测面盘点

### 2.1 控制台请求行——谁产生、数据从哪来

一条完整的链路，从入口到输出：

| 环节 | 位置 | 干什么 |
|---|---|---|
| 请求登记 | `pipeline_app.py:139` `_serve` | 建 `_Trace`（可变累积器），生成 `trace.request_id = uuid4()`，读 ASGI scope 拿 `client_protocol` |
| 路由 / 模型 | `pipeline_app.py:175` `_dispatch` | 填 `inbound_format`、`requested_model`、`model`、`attempts`、`detail` |
| 上游事实 | `pipeline_app.py:265-266` | `trace.bytes_in = len(response.request.content)`（实际发出的字节）、`trace.upstream_protocol = http_label(response.http_version)` |
| 下行计数 | `pipeline_app.py:410` `_counted_upstream` | 每个 chunk `trace.received += len(chunk)`，同时喂 footer |
| 回复摘要 | `assembler.terminal` → `_Trace.absorb` | `usage` / `stop_reason` / `tools` / `thinking` / `dialect` |
| 终结 | `_StreamAccounting.finish`（流式）或 `_serve`（缓冲） | 判 `status_override` 与 `detail`，调 `_log_completion` |
| 聚合记录 | `_log_completion` 构造 `RequestLine` | **同一事实只在这里推导一次**，两条交付路径共用 |
| 渲染 | `observability/request_log.py:269` `format_completion_line` | 纯函数，产出带 ANSI 的字符串 |
| 发射 | `get_logger("app.request").info(<字符串>, status=…)` | structlog → stdlib logging |
| 前缀与时钟 | `observability/logging.py` `_add_status_prefix` + `_render_text` | `[FAIL] 15:01:59 <消息> <extras>` |
| 终端 | `StreamHandler` → stderr；有 footer 时改走 `LiveConsoleHandler` | |

**关键点：`RequestLine` 已经是那份聚合记录。**【读码】它是 `frozen dataclass`，18 个字段，构造点唯一（`_log_completion`），两条交付路径（缓冲 / 流式）都经它。这就是本项目「展示层读聚合记录」取向的落地形态，新的结构化日志复用它即可。

**已经在线上但记录里没有的字段**（`_Trace` 有、`RequestLine` 没有）：`request_id`。这是本次事故答不出问题的第二个原因——就算把四条日志行摆在一起，也没有任何 id 能把它们和别的记录对上。

### 2.2 `log_format: "json"` 是什么，不是什么

【实测】真实输出（`setup_logging(log_format="json")` + 一条 `app.request` 记录）：

```json
{"status": "fail", "event": "H1/H2 200 anthropic-messages/claude-opus-5 5.8s ↑1.7MB ↓2.1KB", "level": "info", "logger": "app.request", "timestamp": "2026-08-20T16:20:39.869444Z"}
```

- 只有 5 个键。`event` 是**已经渲染完的整行字符串**，字段全糊在里面。
- 没有 `request_id`、没有 `model`、没有 `bytes_*`、没有 `duration`，更没有连接信息。
- 【读码】`_build_renderer` 的 json 分支忽略 `colors`，但消息本身是用 `chain.capabilities.color` 构造的——所以在能上色的终端下开 JSON 模式，`event` 里会带 ANSI 转义。
- 【读码】**活链路到不了它**：`cli.py:249` 写死 `setup_logging(log_format="text", …)`。`settings.observability.log_format` 只被 `app_factory.py:56`（legacy 链路）读，而 `cli start` 走的是 `create_pipeline_app`（`cli.py:144/169`）。

所以「本项目已经有结构化日志」这个说法是错的，得说清楚：**有一个结构化的日志信封，没有结构化的请求记录，且该信封在生产路径上不可达。**

### 2.3 落盘的结构化产物——明确的是 / 否

**否。没有任何 JSONL / NDJSON 请求日志落盘。**

【实测】全仓扫描 `jsonl|ndjson|FileHandler|RotatingFile|WatchedFile|open(…, "a")`，`src/` 下零命中。`docs/tmp/260820-server-timeout-forensics.md:212` 记录了另一位调研员做过同样的事——在仓库、`~/.local/share/ghc-api-proxy`、`/tmp` 三处按 mtime 搜 `*.log` / `*.jsonl`，命中的全是 agent 产物，与本服务无关。两次独立核查结论一致。

**唯一落盘的结构化产物**是 `src/app/observability/rejection_capture.py`：

- 触发条件极窄：`isinstance(error, UpstreamRejected)`，即「上游读了这个 body 并且不收」的 4xx（不含 429）。GOAWAY / 超时 / 连接失败**一条都不写**。
- 落点 `user_data_path() / "rejected" / <UTC时间戳>-<状态码>-<request_id>.json`，按名字保留最新 50 个。
- **它是本项目关于「派生路径而不是发明配置键」的先例**，值得直接沿用：`config.example.yaml` 里没有对应的键，模块文档里明说「一个在这里发明出来的键是操作者没要求做的决定」。

### 2.4 History（SQLite）——记什么、不记什么

**它在活链路上根本没接。**【读码】证据三条，互相独立：

1. `HistoryConsumer` / `HistoryStore` 的唯一构造点是 `src/app/server/app_factory.py:79/101`——legacy 链路。`pipeline_app.py` 里没有任何 history import。
2. `HistoryConsumer` 吃的是 `app.pipeline.context.RequestContext`（legacy），不是新链路的 `app.pipeline.request.RequestContext`。两个同名不同物的类。
3. `/history/api/*` 路由在 `app/routes/history.py`，只挂在 `app_factory`；而 `app.routes.*` 在新链路的模块边界禁区里（`test_module_boundaries.py`）。

`HistoryConfig` 只有一个 `enabled: bool = True`，是个**死开关**——`docs/agents/history-forensics/proposal.md` 4.6 节已经把它登记为待裁决项。

真接上时它记什么（`src/app/history/types.py::HistoryEntry`，14 列）：`id / session_id / agent_id / started_at / ended_at / endpoint / status / model.{requested,resolved} / request_payload / response / usage / error_message / pinned`。

**它不记什么**（对本次事故而言）：连接标识、协议版本、上行 / 下行字节、attempt 次数、终止原因的机制层描述、失败时已收到多少内容。且 `entry.response` 与 `usage` 只在完成时写；`context.reply` 还 gate 在 `terminal.seen` 上（`pipeline_app.py:351`），失败流连 reply 都没有。

### 2.5 TUI / footer 消费什么

【读码】`ActiveRequestRegistry`（`observability/active_requests.py`）→ `snapshot()` → `ActiveRequest` 记录 → `build_footer`。字段只有 `request_id / model / started_at / bytes_out / attempts`，加上进程级的 `draining` 与 `connections()`。

**只有在途请求，没有历史**：`finish()` 一调用就 `remove`。所以 footer 对事后诊断零贡献。

`FooterTui.activate()` 里这两行是本次调研最重要的副产物：

```python
previous = list(root.handlers)
root.handlers = [handler]
```

**任何挂在 root 上的 handler，在 footer 活着的那段时间里都收不到记录。** 【读码】`footer_tui_or_none` 只在 `capabilities.live`（即终端可承载）时返回非 None，所以 systemd 下没有这个问题，人在终端里盯着跑的时候才有——而这正是本次事故被看到的那种运行方式。

### 2.6 telemetry / tracing

- `observability/telemetry.py`：OTel counter/histogram（`ghc_proxy_requests` / `_tokens` / `_duration_ms`），属性只有 `model / endpoint / status`。Prometheus reader，进程内暴露，**不落盘**，且【读码】`RequestTelemetry` 在新链路上没有构造点。
- `observability/tracing.py`：FastAPI + httpx 的 OTel instrumentation，`setup_tracing(enabled=…)`。有 exporter 才有数据，本机没配 collector。`trace_context()` 能给 `trace_id` / `span_id`，但没有任何调用点把它写进日志。

---

## 3. 连接标识：能不能拿到（核心可行性）

### 3.1 源码层的事实

【读码】`.venv/…/httpcore/_async/http2.py:159-163`——H2 每条响应带三个 extension：

```python
extensions={
    "http_version": b"HTTP/2",
    "network_stream": self._network_stream,   # 连接自己的，同连接上所有流共享同一个对象
    "stream_id": stream_id,
}
```

`http11.py:126-131` 是 `http_version` / `reason_phrase` / `network_stream`（H1 下每连接一个对象，无 `stream_id`）。
`connection_pool.py:267` 原样 `extensions=response.extensions` 透传，不重建。
`_backends/anyio.py:82-94` `get_extra_info` 支持 `ssl_object` / `client_addr` / `server_addr` / `socket` / `is_readable`。

### 3.2 实测：并发请求能不能区分连接

【实测】`/tmp/h2connid_poc.py`，6 条并发请求打 `https://api.github.com/zen`，httpx 0.28.1 / httpcore 1.0.9 / h2 4.3.0。

**H2 + 流式**（截取，6 条全部同形）：

```
[stream 1] http=HTTP/2 ext_keys=['http_version','network_stream','stream_id'] network_stream_id=0x7bc2afe7f9d0 fileno=7 local=('172.19.141.235', 56822) server_addr=('140.82.116.5', 443) ssl_alpn='h2' h2_stream_id=3
[stream 3] … network_stream_id=0x7bc2afe7f9d0 … local=('172.19.141.235', 56822) … h2_stream_id=7
[stream 5] … network_stream_id=0x7bc2afe7f9d0 … local=('172.19.141.235', 56822) … h2_stream_id=11
[stream 0] … network_stream_id=0x7bc2afe7f9d0 … local=('172.19.141.235', 56822) … h2_stream_id=1
[stream 2] … local=('172.19.141.235', 56822) … h2_stream_id=5
[stream 4] … local=('172.19.141.235', 56822) … h2_stream_id=9
```

6 条共用一个 `network_stream` 对象、一个本端端口 56822，`stream_id` 各不相同（1,3,5,7,9,11）。**这正是本次事故要回答的那个问题的形状。**

**H2 + 缓冲**：同样带全部三个 extension（本端端口 56826，`stream_id` 1..11）。所以缓冲请求和流式请求一样能标。

**H1 + 流式**：6 条拿到 6 个不同的 `network_stream` 对象、6 个不同本端端口（56832/56834/56846/56852/56858/56874），`ext_keys` 里没有 `stream_id`，`ssl_alpn='http/1.1'`。**降级到 H1 之后这套标识依然成立**，正好覆盖待裁决项 C（`http2_ping_interval: 0`）落地后的形态。

### 3.3 实测：openai SDK 会不会把 extensions 吃掉

本项目发往 Copilot 走 `AsyncOpenAI` / `AsyncAnthropic` 的 `post(cast_to=httpx.Response)`（`src/app/ghc_client/client.py:74-93`），所以这一步必须验。

【实测】用 `httpx.MockTransport` 塞一个哨兵对象进 extensions，再经 `AsyncOpenAI.post(cast_to=httpx.Response)` 取回：

```
type       : <class 'httpx.Response'>
keys       : ['http_version', 'network_stream', 'stream_id']
same object: True
stream_id  : 9 http_version: HTTP/2
```

**同一个对象原样返回。** SDK 不重建、不剥离。

### 3.4 实测：一个会咬人的时序坑

【实测】`/tmp/h2connid_poc2.py`：

```
at headers      : {'client_addr': ('172.19.141.235', 34378), 'fileno': 7}
after body      : {'client_addr': ('172.19.141.235', 34378), 'fileno': 7}
after ctx exit  : {'client_addr': ('172.19.141.235', 34378), 'fileno': 7}
after client close: OSError: [Errno 9] Bad file descriptor
```

**连接关掉之后 `get_extra_info("client_addr")` 会抛 `OSError`**，因为它底下是 `raw_socket.getsockname()`。

结论：**必须在响应头到手时立刻把地址读成字符串存下来，不能把 `network_stream` 对象留到写日志时再读。** 这一点对本项目尤其要紧——`_log_completion` 是在上游 response 已经释放之后才跑的（`_tracked_delivery` 的注释明说了这个顺序是有意的）。

### 3.5 代价

**零私有 API。** `Response.extensions` 是 httpx 的公开属性，`get_extra_info` 是 httpcore 传输层的公开方法，两者都在 httpx 的 transport 文档里。不需要自定义 transport，不需要 monkey-patch，不需要 event hook。

需要写的代码，就是在 `pipeline_app.py:265-266` 那两行旁边再加一次读取——那里已经在读 `response.http_version` 了，是同一个对象、同一个时刻。

**自定义 transport 打 id 的替代方案：不需要。** 记在这里是为了说明为什么不采纳：包一层 `AsyncHTTPTransport` 给每条连接发号，得自己复刻连接池的 handle_async_request 语义，或者去拿 `_pool._connections`（私有）。而 `client_addr` 已经是操作系统给的、天然唯一的连接名字，还能直接和 `ss -tnp` / tcpdump 对上——这是自造序号做不到的。

### 3.6 已知局限（诚实说明）

- **本端端口会被 OS 复用**。同一个文件里，时间上相隔很远的两条记录可能撞上同一个端口。判「是否同一条连接」时要连时间戳一起看。对本次事故（同一秒内的四条）不构成问题。
- 【未验】**代理场景**。`config.proxy` 非空时 `client_addr` 是到代理的本端地址，`server_addr` 是代理的地址。不影响「这几条是不是共用一条连接」，但会让 `server_addr` 不再是 Copilot 的地址。没测。
- **答不了的仍然答不了**：GOAWAY 是源站发的还是边缘发的、上游为什么此刻回收连接、我方停止读取之后对端做了什么。这些不是日志字段能解决的问题（`findings.md` 的「未决」列里那三条依旧未决）。

---

## 4. 最小可行方案

### 4.1 落点与形态

| | 决定 | 理由 |
|---|---|---|
| 写在哪 | `user_data_path() / "requests" / "requests-YYYYMMDD.jsonl"` | 沿用 `rejection_capture` 的先例：派生路径，不发明配置键（人写的 `config.example.yaml` 里没有 `observability:` 段） |
| 格式 | 每条完成的请求一行 JSON，追加 | grep 得动、`jq` 得动、subagent 读得动 |
| 容量 | 按天分文件，保留最新 N 天（建议 14），启动时剪一次 | 和 `rejection_capture._prune` 同一个套路。**不引入 logrotate、不引入日志框架** |
| 谁写 | `_log_completion` 内一次直写，走一个和 `rejection_capture` 同形的小模块 | 见 4.3 |
| 触发 | 每条请求恰好一次，成功失败都写 | `_log_completion` 本来就是「每条退出路径恰好一条」的那个点 |

### 4.2 字段——恰好回答那三个问题

```json
{
  "at": "2026-08-20T15:01:59.412Z",
  "request_id": "3f2a…",
  "message_id": "msg_01…",
  "status": "fail",
  "method": "POST", "path": "/v1/messages",
  "inbound_format": "anthropic-messages",
  "client_protocol": "H1", "upstream_protocol": "H2",
  "requested_model": "claude-opus-5", "model": "gpt-5.1-codex",
  "status_code": 200,
  "started_at": "2026-08-20T15:01:53.580Z",
  "duration_s": 5.83,
  "first_upstream_byte_s": 0.42,
  "bytes_in": 1783221,
  "bytes_out": 2153,
  "usage": {"input_tokens": 1, "…": 0},
  "terminal_seen": false,
  "stop_reason": "",
  "blocks": 3,
  "tools": ["Bash", "Read"],
  "thinking": ["enc"],
  "dialect": "responses",
  "attempts": 1,
  "detail": "stream failed before a terminal event: <ConnectionTerminated error_code:0, last_stream_id:2147483647>",
  "upstream_conn": {
    "local": "172.19.141.235:56822",
    "peer": "140.82.116.5:443",
    "alpn": "h2",
    "stream_id": 7
  }
}
```

逐条对上事故答不出的问题：

| 问题 | 字段 | 怎么读 |
|---|---|---|
| 四条是否共用同一条上游连接 | `upstream_conn.local` | 四行的 `local` 相同 ⇒ 同一条 TCP/H2 连接。不同 ⇒ 是节点级回收而不是单连接回收，直接把待裁决项 C 的「收益取决于回收的是单条还是整节点」变成可判的 |
| 每条流各自占哪个 H2 流 | `upstream_conn.stream_id` | 还能和 GOAWAY 的 `last_stream_id` 对照，验证 `2^31-1` 哨兵的判定 |
| 失败时已从上游收到多少 | `bytes_out` + `first_upstream_byte_s` + `duration_s` | 已收字节 + 首字节时刻 ⇒ 「响应已经开始了没有」「停在哪一段」 |
| 到哪个语义位置 | `terminal_seen` / `blocks` / `tools` / `thinking` / `stop_reason` | `terminal_seen=false` + `blocks=3` = 上游发完了 3 个完整块后断的，不是 headers 之后一片空白 |
| 上行 / 下行字节 | `bytes_in` / `bytes_out` | `bytes_in` 是实际发出的字节（`response.request.content`），不是客户端 body |
| 终止原因 | `status` + `detail` | `_ending()` 已经区分 fail(异常) / fail(无终止事件) / gone(下游先走)，`detail` 带异常原文 |
| 跨记录关联 | `request_id` / `message_id` | `message_id`（`context.id`）能把服务端记录和客户端 transcript 按 `message.id` 归组——proposal 五节里点名过、说「成本极低但没核实 id 是否稳定可得」的那条，这里顺带确认了：`RequestContext.id` 是 `uuid4()`，请求全程唯一稳定 |

### 4.3 复用点（这是本节最要紧的部分）

项目取向是「展示层读聚合记录，同一事实不得在两条交付路径各推导一遍」。这个方案的每一个字段都落在既有聚合上，**不新增任何抽取路径**：

1. **`RequestLine` 就是记录本身。** `_log_completion` 已经构造它，两条交付路径共用。结构化行 = `dataclasses.asdict(line)` + 几个 `RequestLine` 目前缺的字段。不要另写一个 `_build_json_record(trace)`——那就是第二条抽取路径。
   - 需要给 `RequestLine` 补的字段：`request_id`、`message_id`、`started_at`、`first_upstream_byte_s`、`terminal_seen`、`blocks`、`upstream_conn`。这些 `_Trace` 上要么已有（`request_id`、`started`），要么是一次赋值就能有的。
   - 补上之后**控制台行也白赚**：`format_completion_line` 现在完全没有 `request_id`，一条 `[FAIL]` 行没法和任何别的东西对上。这是同一处修改的免费收益，不是范围蔓延。

2. **连接事实在 `pipeline_app.py:265-266` 捕获。** 那两行已经在读同一个 `response` 对象拿 `http_version` 和 `request.content`。加一次读取，立刻转成字符串（3.4 的坑）。这是唯一一个真正新增的读取点，而且它在既有的「上游事实」环节里。

3. **`blocks` 加在 `Terminal` 上。** `Terminal.record()`（`delivery/assembler.py:59`）是三个生产者（两个 assembler + `terminal_from_anthropic`）唯一共用的记录点，`self.blocks += 1` 一行。`_Trace.absorb` 已经是 `Terminal → _Trace` 的唯一搬运点，跟着走即可。这与该文件注释里写明的设计意图（「classification lives here, on the record itself」）一致。

4. **`first_upstream_byte_s` 加在 `_counted_upstream`。** 那个 generator 已经在逐 chunk 累加 `trace.received`，第一个 chunk 时记一次时刻。一行。

5. **状态词复用 `status_for(status_code, override=trace.status_override)`**，就是控制台前缀那个函数。JSON 里的 `status` 和 `[FAIL]` / `[GONE]` 必须同源，否则两条交付路径又开始各说各话。

### 4.4 写入机制：两条路，我推荐哪条

**路 A（推荐）：`_log_completion` 里直接追加，走一个和 `rejection_capture` 同形的小模块。**

- 好处：**免疫 TUI 的 handler 接管**（2.5 节那两行）。有 footer 的运行里 root handler 会被整体替换，任何挂上去的 `FileHandler` 都收不到记录——而人盯着终端跑，正是事故被看到的那种场景。
- 好处：不动 structlog 处理器链，不动渲染，不动 TUI。改动面 = 一个新模块 + `_log_completion` 里两行。
- 好处：和 `rejection_capture` 完全同形——「never raises」「派生路径」「按名字剪枝」三条现成纪律直接照抄。
- 代价：它不是 proposal 4.4 所说的「同一份结构化流的一个落点」。但 4.4 反对的具体做法是「另加一个 handler 并祈祷没人替换它」——路 A 压根不是 handler，不在那个栈里，那个危害对它不成立。日后做分片 1 时，把控制台渲染改成读同一份 `RequestLine` 记录即可，路 A 写的字段一个都不用改。

**路 B：把记录作为 structlog kwarg 传下去，加一个带 filter 的 `FileHandler`。**

- 更贴 4.4 的字面方向。
- 但必须同时改 `FooterTui.activate()` 让非控制台 handler 存活，还要改 `_render_text` 把 `record` 字段从 extras 里摘掉（否则整个 dict 会被 `key=value` 拍进控制台行尾）。改动面明显更大，而且触及 TUI——按项目纪律那是要人眼验收的。
- 【记录，未采纳】它更完整，但它是分片 1 + 分片 2 的形态，不是「回答这次事故」的最小形态。建议留给 proposal 的分片 1 去做，届时路 A 的模块降级成那份流的一个 sink。

### 4.5 顺带发现的一个缺口（不在本任务范围，但会影响记录完整性）

【读码】`_serve`（`pipeline_app.py:164-166`）的 `except BaseException: remove; raise` **不写完成行**。异常从 `_dispatch` 逃出去（不是被内部 try 抓住的那些）就没有任何记录。`proposal.md` 的分片 0 已经把它登记为「`_serve` 异常退出补进幂等终结器」。本次 GOAWAY 事故走的是 `_tracked_delivery` → `accounting.failure` → `finish()` 那条路，有记录；但如果结构化日志要被当成取证依据，这个洞得堵上，否则「文件里没有」和「没发生」同形——这正是项目记忆里那条 `absence-is-not-readable-on-a-log-line`。

### 4.6 明确不做的事

- 不引入日志框架、不引入 schema registry、不设门禁。
- 不做脱敏。本项目已裁决日志内容与 token 不敏感；`config.example.yaml` 里唯一被点名为敏感的是请求头黑名单（cookie / x-api-key / x-github-* 等），而这份记录**不写请求头**——和 `rejection_capture` 一样，理由是范围而不是脱敏：回答「这几条是不是同一条连接」用不到请求头。
- 不记请求 / 响应 body。那是 proposal 分片 3-6 的 L1/L2/L3 取证层的事，形态是 SQLite 不是 JSONL，别在这里预支。
- 不改 TUI。

---

## 5. 与既有裁决的关系

`docs/agents/history-forensics/proposal.md` 第四节记着 2026-08-20 用户对分叉 E 的裁决：**「做，且方向改为：标准日志结构化，TUI 从结构化日志解析」**，并在 6.1 分片表里排为：

> | 1 | 结构化日志：把渲染与承载分开，文件落点接上（分叉 E 的第一半） | 「昨天那条 400 的完整上下文」——终端滚掉也还在 |
> | 2 | TUI 改为结构化流的消费者（分叉 E 的第二半），人眼验收 |

**本文提的方案就是分片 1 的前半，而且比它窄**：只落文件、不动渲染分层。字段设计是本文新增的部分（proposal 没有展开过字段），连接标识的可行性也是本文第一次实证。

两处需要请示的地方：

1. **是否接受路 A（绕过 handler 栈直写）作为分片 1 的第一步。** 它偏离 4.4 的字面表述（「同一份结构化流的一个落点」），但避开了 2.5 实证的 handler 接管。我的倾向是接受，理由在 4.4 节。
2. **文件保留策略**：按天分文件保留 14 天，还是按字节轮转。我倾向前者——和 `rejection_capture` 的「按名字剪枝」同构，且天然对齐「昨天那条」这种查询方式。

---

## 6. 复现方式

```bash
cd /home/xp/src/ghc-api-proxy-py
uv run python /tmp/h2connid_poc.py    # 并发请求的连接归属（H2 流式 / H2 缓冲 / H1 流式）
uv run python /tmp/h2connid_poc2.py   # extension 的生命周期，末尾会抛 OSError（这是预期结果）
```

第二个脚本**故意**以 `OSError: Bad file descriptor` 结束——那就是 3.4 节要证明的那件事。
