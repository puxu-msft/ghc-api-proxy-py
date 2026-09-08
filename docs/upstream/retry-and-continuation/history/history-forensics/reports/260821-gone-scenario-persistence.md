# `gone` 场景下的落盘缺口取证报告

日期：2026-08-21。调查者：取证子智能体。性质：**只读调查**，未修改任何代码、配置或数据。

## 0. 这份报告在回答什么

生产请求元数据 `~/.local/share/ghc-api-proxy/requests/requests-YYYYMMDD.jsonl` 里出现了一条异常记录：客户端中途断开（`status=gone`），但我们已经从上游收到并计数了 4.3MB。用户问：**这条异常数据是否说明该场景下部分信息没落盘？**

拆成四问：A 丢了什么、B 哪些是「上游没给」哪些是「我们收到了却没存」、C history 落盘链路在生产中到底跑没跑、D 这是不是一个需要修的缺陷。

## 1. 结论摘要

1. **是的，丢了东西，但丢的不是记录里那些空字段。** 记录里 `usage={}`、`stop_reason=""` 属于「上游没给」——`terminal_seen=false` 意味着 `response.completed` 事件从未到达，而这两个字段只在该事件的处理函数里被写入。真正丢掉的是**我们确实收到的那 4.3MB 原始上游字节，以及从中装配出的 8 个完整 block 的内容**。它们全程只在内存里流过，没有任何一条路径把它们写到磁盘。
2. **history 落盘链路在生产中一次都没跑过，这不是 `gone` 场景专属的跳过，也不是配置未开启。** 整个 `app.history` 子系统挂在旧链路 `app.server.app_factory` 上，而生产入口 `cli.py` 只构造 `create_pipeline_app`。新链路的组合根 `composition.py` 对 history 零引用。`history.enabled` 默认 `True` 且生产配置未覆盖它——**该配置键在新链路上是死开关**。
3. **本项目已经知道这件事，并且已经裁决过。** `docs/agents/history-forensics/proposal.md`（r4，状态「主要分叉已裁决（2026-08-20），可进入 Spec 与实施」）的 §1.1 就是这个结论，且经过两轮双路独立评审。本次调查独立复现了它。**但该方案至今零实施**——目录下只有 `proposal.md`，无 spec/status，分片 0 未动。
4. **值得修，理由不是「信息可能有用」这种臆想，而是有已点名的消费者和已量化的损失。** 两天窗口内 3 条大额 `gone` 记录合计 10,120,001 字节上游内容蒸发，占同期全部上游字节的 **4.83%**；对应向上游发出的请求体另有 2,711,869 字节同样无留存。这些是已计费的 token。但**优先级判断不是「补一个 dump」**，见 §5。

**证据强度**：§2、§3、§4 的结论**强到足以据此行动**——依据是完整读通的调用链、三次证伪性检索、生产配置原文、以及仓库内两处独立的自陈式佐证。§5 的影响面估算**强到足以据此排优先级**，但样本窗口只有约 19 小时（2026-08-20T17:12 → 2026-08-21T12:28），长期比例需更多样本。

## 2. 先纠正三处交接信息中的偏差

调查起点的三条描述有偏差，后续判断依赖精确形态，故先列出。

### 2.1 jsonl 不是「有才打印」，它总是写全部字段

`src/app/observability/request_log_file.py:41`：

```python
record = {"at": utc_timestamp(now), "status": status, **asdict(line)}
```

`asdict(line)` 展开 `RequestLine` 的**每一个**字段，无论是否为默认值。所以 jsonl 里 `usage: {}`、`tools: []`、`stop_reason: ""` 都是**字段存在且取默认值**，不是字段缺席。

「有才打印」描述的是**控制台那一行**，是另一个函数：`src/app/observability/request_log.py:319` 的 `format_completion_line`，其 docstring 明写「Every field after the subject is omitted when it has nothing to say」；`format_tokens`（同文件 240 行起）在 `if not usage:` 时返回空串。

**这个区分是有后果的**：读 jsonl 时不存在「缺席 vs 空值」的歧义，但存在「默认值 vs 观测结果」的歧义——`tools: []` 是真实观测（装配出的 8 个 block 里确实没有 tool_use），而 `usage: {}` 是从未被写入过的初值。二者在 JSON 里同形，只能靠代码路径区分。§4 逐字段做了这件事。

### 2.2 `usage` 是完全空的 `{}`，不是「缺 output_tokens」

原始记录（`requests-20260820.jsonl`）：

```json
"usage": {},
"terminal_seen": false,
"stop_reason": "",
```

不存在「`output_tokens` 缺失而其他字段在」的形态。交接描述里的「缺 output_tokens、cache_read 为 None」是控制台渲染器对空 dict 的呈现方式所致。

### 2.3 这不是唯一一条，而且现象在复发

截至 2026-08-21T12:28 快照，全量 4,662 条记录中 `status=gone` 共 **8 条**，其中 `bytes_out > 100KB` 的有 **3 条**：

| at (UTC) | bytes_out | bytes_in | blocks | thinking | duration | model |
|---|---:|---:|---:|---:|---:|---|
| 2026-08-20T18:57:19 | 4,304,579 | 773,979 | 8 | 7×enc | 124.1s | gpt-5.6-sol |
| 2026-08-21T12:13:58 | 1,686,013 | 939,157 | 3 | 3×enc | 73.2s | gpt-5.6-sol |
| 2026-08-21T12:26:21 | 4,129,409 | 998,733 | 5 | 4×enc | 108.5s | gpt-5.6-sol |

后两条是**交接之后新产生的**（就在今天中午）。另外 5 条 `gone` 的 `bytes_out` 分别为 3,129 / 3,113 / 454 / 429 / 0，`blocks=0`——那些是还没装配出任何块就断开的，没有内容损失可言。

三条大额记录**全部**是 `dialect=responses` + `model=gpt-5.6-sol`，即 Anthropic Messages 入站经 OpenAI Responses 上游这条主产品路径。这是一个形态一致的复发现象，不是孤立异常。

## 3. A —— 这 4.3MB 走到哪一层就被丢弃了

### 3.1 完整的字节生命周期

顺真实入口读通的链路（全部在 `src/app/server/pipeline_app.py` 及其下游）：

1. `_dispatch`（`pipeline_app.py:401`）判定 `context.stream` 为真，进入流式交付分支。
2. `response.aiter_bytes()` 产出上游原始字节，依次被 `with_idle_timeout` → `with_deadline_at` → **`_counted_upstream`** 包裹（`pipeline_app.py:422-435`）。
3. `_counted_upstream`（`pipeline_app.py:549-559`）是**唯一**看得见完整原始字节的地方。它做三件事：记录首字节时刻、累加 `trace.received`、给 footer 加计数，然后 `yield chunk` **原样转发**。它不保留任何字节，也不旁路到任何地方。

   ```python
   async for chunk in chunks:
       if chunk and trace.first_upstream_byte_s is None:
           trace.first_upstream_byte_s = time.monotonic() - trace.started
       trace.received += len(chunk)
       chain.active_requests.add_bytes(request_id, len(chunk))
       yield chunk
   ```

   `trace.received` 就是记录里的 `bytes_out=4304579`。**4.3MB 在这里被折叠成一个整数，原始字节此后不可复得。**

4. `stream_delivery` → `_deliver` → `_events_with_ping` → `read_events` 把字节解析成 `SseEvent`。这一层已经有损：`proposal.md` §1.6 记载 `parse_frame` 用 `errors="replace"` 解码、丢弃注释行（含保活帧）、丢弃不认识的字段名、剥掉前导空格、用 `"\n"` 重接 data 行。**从 `SseEvent` 无法还原原始字节，也没有输入 chunk 边界。**
5. `ResponsesAssembler.push`（`assembler.py:218`）把事件累积进 `_Draft`，在 `response.output_item.done` 时由 `_close`（`assembler.py:279`）产出 `CompletedBlock`，并调用 `Terminal.record(block)`。
6. `_commit`（`stream.py:297`）把块交给 `DeliverySession.offer` → `BlockBuffer.add`。生产的 `buffering_policy` 是 schema 默认值 **`"block"`**（`config/schema.py:262`，生产 `config.yaml` 无 `client_delivery` 节），所以 `BlockBuffer.add` 立即 `_drain()` 放行（`blocks.py:100-101`）。块被 `block_frames` 渲染成 Anthropic SSE 帧写给客户端。
7. 客户端断开 → `_tracked_delivery` 的生成器收到 `GeneratorExit` → `finally` 调用 `accounting.finish()` → `_log_completion` 写出那一行 jsonl。

### 3.2 所以，具体丢了这些

| 丢失物 | 在哪一层蒸发 | 有无磁盘副本 |
|---|---|---|
| 4,304,579 字节原始上游 SSE | `_counted_upstream` 折叠为整数后 | **无** |
| 8 个 `CompletedBlock` 的 payload（含 7 份 `encrypted_content` 推理载荷、1 份文本） | 渲染成 SSE 帧写给客户端后，随生成器一起被回收 | **无** |
| 断开瞬间 `ResponsesAssembler._drafts` 里未闭合的半成品块 | 随 assembler 对象被回收 | **无** |
| 发往上游的 773,979 字节请求体 | `trace.bytes_in = len(response.request.content)`（`pipeline_app.py:396`）只取长度 | **无** |
| `DeliverySession.delivered` 累积的已交付块列表（`blocks.py:138`） | 只被 `committed_count` 读，请求结束即回收 | **无** |

### 3.3 证伪性检索：确认没有别的写盘路径

**检索 1 —— 枚举 `src/` 下全部文件写入点：**

```
rg -n "\.write_text\(|\.write_bytes\(|open\([^)]*[\"']w|open\([^)]*[\"']a|aiofiles|sqlite3\.connect|\.execute\(" src/
```

命中 22 处，逐一归类后与本请求相关的只有三类：

- `observability/request_log_file.py:42` —— 就是那一行 jsonl 本身，只写 `RequestLine` 的标量字段。
- `observability/rejection_capture.py:77` —— **只在 `UpstreamRejected`（非限流的 4xx）时触发**（`capture_rejection` 首行即 `if not isinstance(error, UpstreamRejected): return None`）。本请求 `status_code=200`，从未进入。且它保存的是**请求体**，不是响应内容。
- `history/sqlite/writer.py` —— 见 §4，生产链路不可达。

其余（`auth/providers.py`、`cli.py`、`server/tls.py`、`lifecycle/pidfile.py`、`tokenization/*`、`context/error_persistence.py`）与请求内容无关，其中 `context/error_persistence.py` 属旧链路。

**检索 2 —— delivery 层有无任何持久化：**

```
rg -n -i "history|persist|dump|\.db|write_text|open\(" src/app/pipeline/delivery/ src/app/server/handler.py
```

零持久化命中。全部命中都是 `orjson.dumps`（序列化到 wire，不是落盘）。

**结论**：`gone` 场景下，没有任何一条路径把已收到的上游内容写到磁盘。唯一的磁盘产物是那一行 jsonl，它只含标量摘要。**证据强度：强到足以据此行动。**

### 3.4 一个必须说清的限定：客户端其实收到了那些块

因为生产用 `buffering_policy="block"`（每块闭合即放行），那 8 个块在断开**之前**已经逐块写给客户端了。所以准确的说法不是「客户端什么都没拿到」，而是：

- **客户端侧**：拿到了 8 个块，但作为一次被取消的 turn，Claude Code 这类客户端通常会丢弃半截 turn。这是客户端行为，不是我们的落盘缺陷。
- **服务端侧**：我们对这 8 个块的内容**零留存**，只剩计数。

这个限定重要，因为它把损失定位在正确的地方：**丢的是我们自己的取证能力，不是客户端的可用性。**

顺带记一笔（非本次场景，但同一段代码）：若 `buffering_policy` 被配成 `full` 或 `until-tool-use`，块会被 `BlockBuffer` 一直扣住，而释放它们的 `session.finish()` 在 `stream.py:266`——位于 `async for pull in events` 循环**之后**。客户端断开抛出的 `GeneratorExit` 会直接从 `yield` 处向上解栈，**跳过第 266 行**。届时被扣住的块连客户端都到不了。当前生产配置不触发这条，仅作已识别的相邻风险登记。

## 4. B —— 「上游没给」vs「我们收到了却没存」

逐字段归类。判据是：该字段的**唯一**写入点是否在一条从未执行到的代码路径上。

### 4.1 上游没给（不算落盘缺陷）

| 字段 | 记录值 | 唯一写入点 | 依据 |
|---|---|---|---|
| `usage` | `{}` | `ResponsesAssembler._read_terminal`，`assembler.py:329` | `_read_terminal` 只被 `push` 在 `kind in {"response.completed", "response.incomplete"}` 时调用（`assembler.py:233-235`）。同一函数第一行 `self._terminal.seen = True`（`assembler.py:324`）。**`terminal_seen=false` 因此是「该函数从未执行」的直接证明**，`usage` 保持 `Terminal` 的初值 `{}`（`assembler.py:49`）。 |
| `stop_reason` | `""` | 同上，`assembler.py:336` / `340` | 同一函数、同一证明。`Terminal.stop_reason` 初值为 `""`，且该字段的注释明确说明为何不默认 `end_turn`：「it used to default to `end_turn`, which made 'upstream said the turn ended cleanly' and 'upstream never said anything' the same value」（`assembler.py:47`）。**这是项目已经处理过的同类问题**。 |

Responses 腿的 token 计数只在 `response.completed` / `response.incomplete` 的 `response.usage` 里出现一次。流在此之前被切断，**这些字节从未到达我们的网卡**。归入「上游没给」，与落盘无关。

### 4.2 真实观测结果（既非缺失也非缺陷）

| 字段 | 记录值 | 依据 |
|---|---|---|
| `tools` | `[]` | `Terminal.record` 在每个 `kind == "tool_use"` 的完成块上 append（`assembler.py:67-68`）。8 个块都闭合并走过 `record`，没有一个是 tool_use。**这是「确实没有工具调用」的真实观测**，不是默认值伪装。 |
| `blocks` | `8` | `record` 无条件 `+= 1`（`assembler.py:66`）。 |
| `thinking` | `["enc"×7]` | `record` 在 `kind == "thinking"` 时 append `"txt" if block.payload.get("thinking") else "enc"`（`assembler.py:70`）。7 个推理块，全部只带不透明签名、无可读文本。 |
| `terminal_seen` | `false` | 真实观测，且是本次归类的支点。 |
| `bytes_out` / `bytes_in` / `first_upstream_byte_s` / `upstream_conn` | 均有值 | `_counted_upstream` 与 `_snapshot_upstream_connection` 的实测读数。 |
| `detail` | `"delivery stopped before upstream finished"` | `_StreamAccounting._ending()` 的第三分支（`pipeline_app.py:514`）。其 docstring 诚实声明该分支无法区分「客户端离开」与「我方 shutdown 取消了自己的在途流」。 |

### 4.3 由端点性质决定的空缺（不属于任一类）

`count_provider` / `count_provider_reason` 为 `""`：本请求走 `/v1/messages` 而非计数端点，`route.count_tokens=false`，这两个字段只在计数分支写入（`pipeline_app.py:345-351`）。属于「这个端点本来就不报这一项」。

> 附带发现：`requests-20260820.jsonl` 里这两个字段名为 `counter` / `counter_reason`，`requests-20260821.jsonl` 里已改名为 `count_provider` / `count_provider_reason`。字段在两天之间被重命名，跨日期解析 jsonl 的工具需要同时认这两组名字。仅作记录，无需处理。

### 4.4 「我们收到了却没存」的完整清单

即 §3.2 那张表：**4.3MB 原始字节、8 个完整块的 payload（含 7 份 `encrypted_content`）、断开瞬间的半成品块、773,979 字节的上行请求体**。这四样全部满足「字节确实到过我们进程」且「磁盘上没有任何副本」。

**这才是这条记录暴露的落盘缺口。记录里那些空字段不是。**

## 5. C —— history 落盘链路在生产中到底有没有在跑

**答案：整个 history 子系统在生产链路上从未被调用过。既不是配置未开启，也不是 `gone` 场景专属跳过，而是根本没接线。**

这两个结论对用户意义完全不同，所以逐级证明。

### 5.1 生产入口只构造新链路

`src/app/cli.py` 是唯一入口（`pyproject.toml:51` → `ghc-api-proxy = "app.cli:main"`；`src/app/__main__.py` 转发到 `app.cli:main`）。它只 import 并调用 `create_pipeline_app`：

- `cli.py:23` `from app.server.pipeline_app import create_pipeline_app`
- `cli.py:144`（`serve_inherited`，socket activation 路径）与 `cli.py:169`（`_serve_pipeline`，standalone 路径）各调用一次。

**`app.server.app_factory.create_app`（挂着 history 的那个）在 `src/` 全域没有任何调用者**，只在 `src/app/server/__init__.py:12` 的一句 docstring 里被提到名字。

### 5.2 新链路的组合根对 history 零引用

```
rg -n -i "history" src/app/server/composition.py
```

**零命中。** `Chain` 这个数据结构里根本没有 history 字段可供任何请求路径去调用。

### 5.3 两条链路用的是两个不同的 `RequestContext`

这是「接线断在哪里」的结构性证据：

- `HistoryConsumer` 的类型签名吃 `from app.pipeline.context import RequestContext`（`consumer.py:7-12`）。
- 新链路全程用 `from app.pipeline.request import RequestContext`（`pipeline_app.py:35`、`composition.py`、`handler.py`、`inbound.py`、全部 `direct_driver/*` 与 `subscribers/*`）。

两个同名不同源的类。import 两侧的文件集合互不相交：消费 `pipeline.context` 的是 `app/routes/*`、`app/pipeline/executor.py`、`app/context/*`、`app/anthropic/client.py`——全是旧链路。

### 5.4 三次证伪性检索

**检索 1 —— 谁调用 `HistoryConsumer.started` / `.finalized`：**

```
rg -n "\.finalized\(|\.started\(" src/
```

4 处，全部在旧链路：`app/routes/anthropic.py:117`、`app/pipeline/executor.py:123 / 213 / 468 / 511`。新链路一处没有。

**检索 2 —— 谁构造 `HistoryStore` / `HistoryWriter`：**

```
rg -n "HistoryWriter\(|HistoryStore\(" src/
```

生产代码只有 `app/server/app_factory.py:79`（不可达）与 `app/history/store.py:22`（被前者调用）。其余全在 `tests/`。

**检索 3 —— 谁读 `context.reply`（新链路上最接近 history 的那个字段）：**

```
rg -n "\.reply\b" src/
```

只有 3 处，全在 `pipeline_app.py`：455-457 写入并立刻 `absorb` 到日志行，491 在流式路径写入。**没有任何读者。** 这印证了 `implementation.md` 的自陈：「今天 `context.reply` 无读者所以无可观测影响」。

### 5.5 配置是一个死开关

`HistoryConfig`（`config/schema.py:269-270`）只有 `enabled: bool = True`。生产 `~/.local/share/ghc-api-proxy/config.yaml` **没有 `history` 节**，所以默认值 `True` 生效。

也就是说：**配置说 history 是开的，但新链路没有任何代码去读这个键。** `cli.py:100` 的 `--history/--no-history` 会把 `{"enabled": ...}` 写进 `ProxyConfig`，然后无人消费。

> 注意不要与旧链路 `src/app/config/settings.py:173` 里另一个同名的 `HistoryConfig` 混淆——那一个确实被 `app_factory` 消费，但 `app_factory` 本身不可达。

### 5.6 8,966 行 `gpt-test` 数据的来源

那些行是**测试套件写进用户真实数据目录**的痕迹。`app_factory.py:75-77` 在 `settings.history.db_path` 为空时回落到 `user_data_path() / "history.db"`，而调用 `create_app()` 的正是测试套件。`proposal.md` §2.1 已把这条列为实施前置条件（当时快照 8,630 行且仍在增长）。

### 5.7 仓库内两处独立的自陈佐证

不是我一个人的推断，代码注释里已经写着同样的结论：

1. `src/app/observability/rejection_capture.py` 的模块 docstring：

   > 「the investigation had to reconstruct the outbound request from the *client's* own transcripts, **because the pipeline records no history** and the request that caused the refusal is gone the moment the response is written.」

   `rejection_capture` 这个机制本身就是**因为 history 没接线**才被造出来的补丁——而且它只补了「4xx 被拒的请求体」这一个洞。

2. `src/app/pipeline/subscribers/server_tools.py:13`：

   > 「This project's own `history.db` holds 8,966 requests and **not one of them reached this module**」

### 5.8 小结

| 候选解释 | 判定 |
|---|---|
| 配置未开启 | **否**。`history.enabled` 默认 `True` 且生产未覆盖。 |
| 写入路径有 bug | **否**。`HistoryWriter` 本身有测试覆盖（`tests/component/history/test_history_store.py`）且确实在写——8,966 行就是它写的。 |
| `gone` 场景专属跳过 | **否**。不存在任何场景下新链路会调用 history。 |
| **整个子系统未接在生产链路上** | **是。证据强度：强到足以据此行动。** |

## 6. D —— 这是不是一个需要修的缺陷

### 6.1 先说不值得做的那部分

按项目规则「先证明你要建在其上的平面存在」和「拒绝臆想式加固」，以下**不应该**做，我不建议：

- **不要「加个日志」或「加个 dump」。** 单点补丁正是 `rejection_capture` 已经走过的路——它补了 4xx 请求体这一个洞，然后 `gone` 场景这个洞还在。再补一个只会得到第三个互不相干的落点。
- **不要为「信息可能有用」而留存。** 若真要留存，必须指得出消费者。下面指得出。

### 6.2 但这确实值得修，因为消费者是具体的、已被点名的

`proposal.md` §1.7 有一张**按被点名次数排序**的排障缺口表（来自三份只读需求调查）：

| 缺口 | 被点名次数 | 现状 |
|---|---:|---|
| 实际发往上游的字节级 body | 4 | 数据在手，未保存 |
| 该次请求的服务端完成记录 | 3 | 有雏形，只写 stdout |
| 上游 SSE 帧**时序** | 3 | 完全无 |
| 上游错误响应体原文 | 2 | 只在日志 `detail` 留只言片语 |

本次 `gone` 记录同时命中第 1、第 3 两项。而且项目自己的开发纪律里写着「Upstream behaviour is recorded, not imagined」——cassette 固件是硬需求，而 `from_history.py` 这条派生路径**已于 2026-08-15 失效**（旧 Bun 服务不再存帧）。也就是说：**现在每一次生产流量都是不可复得的固件素材，而我们一份都没留。**

同一份 `proposal.md` §1.10 还记载：用户亲笔的 `docs/.human-controlled/MAIN.md` 把 `/history/api/*`、`/history/ws` 列为**产品端点**，且未标注「暂不支持」。按项目记忆「人写文档是最终权威」，这是一个已经存在的产品承诺。

### 6.3 影响面量化

快照时间 2026-08-21T12:28，窗口 2026-08-20T17:12 → 2026-08-21T12:28（约 19 小时）。

| 指标 | 数值 |
|---|---|
| 全部请求记录 | 4,662 |
| `status=gone` | 8（占 0.17%） |
| 其中 `bytes_out > 100KB` | **3** |
| 这 3 条蒸发的上游内容 | **10,120,001 字节** |
| 占同期全部上游字节（209,344,035）的比例 | **4.83%** |
| 这 3 条对应的上行请求体（同样无留存） | 2,711,869 字节 |
| 这 3 条装配出的完整块 | 16 个，其中 14 个加密推理块 |

**近 5% 的已计费上游产出在服务端不留任何痕迹。** 三条全部落在 `dialect=responses` / `gpt-5.6-sol` 主产品路径上，且形态一致（长思考、大量 `encrypted_content`、100 秒量级、客户端在完成前离开）——这类请求恰好是**最贵**且**最难复现**的那一类。

需要如实标注的限定：窗口只有 19 小时，且其中包含开发调试流量。4.83% 这个比例**足以支撑排优先级**，但不足以外推为稳态生产比例。「现象在复发」这一点则是确定的——3 条里有 2 条产生于交接之后的几小时内。

### 6.4 我的主观判断

**值得修，但不是现在临时补一个 dump，而是把已经裁决过的方案推进到分片 0-3。**

理由三条：

1. **方案已经存在且已被用户裁决**（`proposal.md` r4，2026-08-20，八个分叉全部裁决，其中三项用户推翻了作者推荐）。它经过 r1→r4 四版、两路独立评审、一轮聚焦抽查。**现在缺的是实施，不是设计**。绕过它另做一个补丁，等于把一份已付过评审代价的裁决作废。
2. **本次 `gone` 记录不改变该方案的任何裁决，但给它增加了一个具体的、可引用的事故**。方案 §2.2 原本担心的是「非流式路径异常退出不留记录」；本次事故说明**流式路径的 L1 记录其实是健全的**（`_StreamAccounting.finish` 的幂等终结器正确工作，jsonl 那一行完整写出），缺的恰恰是方案里的 **L3（raw chunks + 到达时刻，分片 6）** 和 **L2（每 attempt 上行快照，分片 4）**。
3. **分片 0 是纯缺陷修复、不需要 Spec、且独立有价值**：把测试库改落 `tmp_path`（阻止测试噪音继续污染真实数据目录），以及取证库用独立文件名。这两件事今天就可以做，不依赖任何设计决策。

**需要提请用户注意的排期矛盾**：`proposal.md` §6.1 的分片顺序把 L3 排在第 6 片，前面压着结构化日志、TUI 改造、L1 落盘、L2、replay 五片。而本次事故暴露的**最贵**的损失恰好是 L3 覆盖的那部分。是否要为此调整分片顺序，是一个需要用户裁决的分叉——我不在这份报告里替他决定，但倾向是：**分片 0 立即做，L3 的优先级值得重新讨论**，因为它是唯一能把已计费上游产出变成可复用固件的一片，而固件的另一条来源（`from_history.py`）已经断了。

### 6.5 一个不需要修的相邻项

`_StreamAccounting.finish` 里 `context.reply` 仍 gate 在 `terminal.seen` 上（`pipeline_app.py:490`），而同一处的 `trace.absorb(terminal)` 是无条件的。这看起来像是「截断的回复丢了信息」，但**不是**：

- `trace.absorb` 无条件执行，所以日志行拿到了全部已观测事实（这正是我们能读到 `blocks=8`、`thinking=7×enc` 的原因）。
- `context.reply` **今天没有任何读者**（§5.4 检索 3 已证）。
- `implementation.md` 的「结构怪味登记」已就地记录此事并给出裁决：有意保持不一致，与 STR-04 同一切片一并裁决，理由是 `reply is not None ⇒ 回复已完成` 是 hooks 与 History 的现有契约，放宽它是契约变更。

**这一项已被正确处理，不要动它。** 在这里提出来，是为了防止读这份报告的人把它误判成一个新缺陷。

## 7. 与既有文档的关系

- **权威源**：`docs/agents/history-forensics/proposal.md`（r4，2026-08-20）。本报告 §5 的结论与其 §1.1 一致，是独立复现而非引用。
- **本报告新增的**：`gone` 场景的逐字段归类（§4）、字节生命周期的逐层追踪（§3）、复发现象与影响面量化（§2.3、§6.3）、以及 §2 对三处交接偏差的纠正。
- **未纳入的**：`proposal.md` §3 之后的设计细节（数据模型、查询面、脱敏立场、cassette 合同）本报告不复述也不修改，它们仍以该文档为准。

## 8. 纪律声明

- 未修改任何代码、配置或数据。`~/.local/share/ghc-api-proxy/config.yaml` 与 `history.db` 均只读访问。
- 未接触 4141 端口的 Bun 服务。
- 所有指路按符号名与文件路径，行号取自 2026-08-21 的工作树状态；`proposal.md` §6.2 警告过有并行会话在编辑 `pipeline_app.py`，引用行号前请复核。
- 数据快照时间 2026-08-21T12:28。服务在调查期间仍在运行，两次统计之间记录数从 4,618 增至 4,662，正文采用后者。
