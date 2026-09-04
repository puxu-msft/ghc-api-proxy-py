# 结构化日志实施设计（分叉 E：渲染与承载分开）

**日期**：2026-08-21
**性质**：只读调查 + 设计。未修改任何源码。
**基线**：`git HEAD = be63418`。除 `src/app/observability/tracing.py` 外，本文涉及的 `observability/*`、`server/pipeline_app.py`、`tests/tui/*`、`tests/unit/observability/*` 在写作时均与 HEAD 一致（`git status --short` 实测）。**行号按此快照给出；并行会话若改动这些文件，以符号名为准。**
**上游文档**：`.dev/docs/history/proposal.md` §4.4 与 §6.1 分片 1、2。用户 2026-08-20 裁决：标准日志应当结构化，TUI 从结构化日志中解析。
**前序调研**：`.dev/docs/upstream/h2-goaway/archive-260820/260820-structured-log-survey.md`（2026-08-20）。它的两条结论**已被此后的实现推翻**，见 §1.5。

## 0. 证据分级

| 标记 | 含义 |
|---|---|
| **【实测】** | 本机跑过脚本，粘的是真实输出。一次性脚本在 `/tmp/structlog_probe/`，可重跑 |
| **【读码】** | 读源码（本仓或 `.venv` 内依赖）得出，未执行验证 |
| **【推定】** | 推断，不足以单独支撑决策，已逐条标注 |

环境：Python 3.14.2，structlog 26.1.0【实测】。

---

## 1. 现状测绘

### 1.1 structlog 处理器链

`src/app/observability/logging.py::setup_logging`（当前 121-179 行）。**一条链，一个 renderer，一个 handler。**

`shared_processors` 顺序（131-143 行）：

| # | 处理器 | 作用 |
|---|---|---|
| 1 | `structlog.contextvars.merge_contextvars` | 并入 contextvars 绑定 |
| 2 | `structlog.stdlib.add_log_level` | 写入 `level` |
| 3 | `structlog.stdlib.add_logger_name` | 写入 `logger` |
| 4 | `structlog.processors.TimeStamper` | **按 `log_format` 分叉**：json 用 `fmt="iso", utc=True`；text 用 `fmt="%H:%M:%S", utc=False` |
| 5 | `structlog.processors.format_exc_info` | 把 `exc_info` 解析成 `exception` 字符串。注释明说必须在**记录时**跑，因为 `exc_info=True` 要靠 `sys.exc_info()` 在 `except` 块内解析 |
| 6 | `_add_status_prefix`（34 行） | 由 `status` 或 `level` 推出 `prefix`（`[ OK ]` / `[FAIL]` / `[....]` …） |
| 7 | `_drop_status_prefix`（51 行） | **仅 json 模式追加**，把刚加的 `prefix` 再删掉 |

这一份 `shared_processors` 同时充当三个角色：`ProcessorFormatter` 的 `foreign_pre_chain`（147-153 行）、`structlog.configure` 的主链（171-179 行），以及（隐含地）唯一的字段生产者。

`ProcessorFormatter.processors` 只有两项：`remove_processors_meta` + `renderer`。`renderer` 由 `_build_renderer`（110 行）产出，json 分支是 `JSONRenderer()`，text 分支是闭包，塞入 `_colors` 后调 `_render_text`（76 行）。

**第 4、7 两处是关键**：格式选择被编进了共享链，所以这条链**结构上只能服务一个 renderer**。两个 sink 需要不同的时间格式、不同的 `prefix` 去留，而它们现在都在共享链里做决定。

### 1.2 谁调 `setup_logging`，传什么

| 调用点 | 参数 | 是否生产路径 |
|---|---|---|
| `src/app/cli.py:251`（`start` 命令） | `log_format="text"` **写死**，`log_level="DEBUG" if verbose else "INFO"` | **是**。唯一生产入口 |
| `src/app/server/app_factory.py:55`（`_lifespan`） | `settings.observability.log_format` / `.log_level` | 否。旧链路，生产从不调用（proposal §1.1） |
| `tests/int/test_pipeline_app.py:1255` | `log_format="text", colors=False` | 测试 |
| `tests/unit/lifecycle/test_shutdown_reporting.py:28` | 同上 | 测试 |
| `tests/unit/observability/test_logging.py`（6 处） | text 与 json 各半 | 测试 |

**`ProxyConfig`（新链路 `src/app/config/schema.py`）里没有任何日志格式或级别的键**——`rg 'log_format|log_level|LoggingConfig'` 在该文件零命中【实测】。所以 `log_format="json"` 这条分支在生产路径上不可达，只有旧链路 `config/settings.py` 的 `settings.observability` 能到。这与前序调研的结论一致。

### 1.3 text 与 json 两个分支各产出什么

**text**（`_render_text`，76-107 行）：`{prefix} {timestamp} {event}{extras}{traceback}`。它 `pop` 掉 `prefix` / `timestamp` / `event` / `logger` / `level` / `status` / `exception`，剩下的按键排序拼成 `k=v` 尾巴并整体 DIM，颜色在这里施加。

**json**（`JSONRenderer`）：全字典直接序列化。实测形态（前序调研粘的真实输出，本次未重跑）：

```json
{"status": "fail", "event": "H1/H2 200 anthropic-messages/claude-opus-5 5.8s ↑1.7MB ↓2.1KB", "level": "info", "logger": "app.request", "timestamp": "2026-08-20T16:20:39.869444Z"}
```

**这就是本次工作的核心事实：`event` 是一整条已经渲染完、可能还带 ANSI 的字符串。** 请求行的字段在进入 structlog 之前就被 `format_completion_line` 压扁了——见 `src/app/server/pipeline_app.py::_log_completion`（205-245 行）：

```python
write_request_record(line, status=status)
get_logger(REQUEST_LOGGER).info(
    format_completion_line(line, status=status, unicode=chain.capabilities.unicode, color=chain.capabilities.color),
    status=status,
)
```

所以「本项目已经在用 structlog，是结构化日志」这句话要说准：**有一个结构化的信封，没有结构化的请求记录**。信封里只有 5 个键，其中 4 个是元数据。

### 1.4 全项目的 handler 清单

`rg 'addHandler|handlers\s*=|logging.Handler|StreamHandler|FileHandler|basicConfig'` 在 `src/` 下**只有两处**【实测】：

| # | 位置 | 什么 | 装在哪 |
|---|---|---|---|
| 1 | `logging.py:154-159`（`setup_logging`） | `logging.StreamHandler()`（无参数即 stderr），带 `ProcessorFormatter` | root，**先 `handlers.clear()` 再 `addHandler`** |
| 2 | `tui.py:131-140`（`FooterTui.activate`） | `LiveConsoleHandler`，复用 root 上已有的 formatter | root，**`root.handlers = [handler]` 整体替换**，退出时 `root.handlers = previous` 还原 |

另外 `setup_logging` 把 `uvicorn` / `uvicorn.error` / `uvicorn.access` 三个 logger 的 handler 清空并设 `propagate=True`（162-165 行），把 `uvicorn.*` / `httpx` / `httpcore` 抬到 WARNING（168-169 行）。

**结论**：整个进程在任一时刻只有一个 root handler。TUI 激活期间那一个是 `LiveConsoleHandler`。`tui.py:150 footer_tui_or_none` 只在 `detect_terminal().live` 为真时返回非 `None`（`terminal.py:121-140`：tty 且非 `TERM=dumb` 且无 `CI`），所以交互式终端下 TUI **默认激活**——而交互式终端正是取证现场。

### 1.5 已经存在的 JSONL 落盘（前序调研已被推翻的部分）

`src/app/observability/request_log_file.py`（提交 `10e4811`，2026-08-20 `feat: keep a durable record of every completed request`）已经在生产路径上写结构化记录：

- 调用点唯一：`pipeline_app.py:241` `write_request_record(line, status=status)`，在 `_log_completion` 内。
- 落点 `user_data_path()/requests/requests-YYYYMMDD.jsonl`，一行一个 JSON 对象，内容是 `{"at":…, "status":…, **asdict(RequestLine)}`。
- 保留策略 `KEEP_DAYS = 14`，按文件名字典序（=时序）剪枝。
- 永不抛错：`except Exception` → `logger.warning` + 返回 `None`。

**实测当前落盘状况**（2026-08-21 13:28，服务正在运行）：`requests-20260820.jsonl` 3,305 行 / 3.0 MB，`requests-20260821.jsonl` 1,859 行 / 1.7 MB。约 **0.9 KB/请求**。`dialect` 正确序列化成 `"anthropic"`，因为 `ReplyDialect` 是 `StrEnum`（`assembler.py:33`）。

所以前序调研的两句话现在是错的，别再引用：

- ~~「本项目当前没有任何结构化日志落盘」~~ → 有，但只覆盖**已完成的请求行**这一类记录。
- ~~「`RequestLine` 缺 `request_id`」~~ → 已有（`request_log.py:113`），且新增了 `message_id`、`upstream_conn`。

### 1.6 于是真正的缺口是什么

`requests-*.jsonl` 补上了最贵的那一类记录，但**它是一条旁路，不是日志的落点**。剩下的缺口：

1. **除请求行外的一切都没有文件记录**：启动/监听行、`model catalog unavailable`、shutdown 阶梯的每一级、`[RETRY]` 行、`[....]` 到达行，以及所有第三方库的 WARNING/ERROR（asyncio 的 `StopAsyncIteration exception in shielded future` 就是这一类）。交互式终端下这些**只存在于 scrollback**，滚掉即消失。
2. **同一份事实两条投递路径**：`RequestLine` 在 `_log_completion` 里被喂给两个消费者，一个走 `write_request_record`，一个走 `format_completion_line` + logger。目前二者由同一个 `line` 对象派生，尚未违反「同一事实不得推导两遍」；但它已经是**两套 sink 关切**（建目录、剪枝、失败处理、序列化 fallback），再加一个通用日志文件就会是第三套。
3. **落盘代价压在事件循环上**。`write_request_record` 每条记录都 `open`→`write`→`close`，外加一次 `glob` 剪枝。【实测】/tmp 同形基准，2000 次采样：开闭+glob 中位 **94.9 µs**、p99 163.7 µs；持久句柄 `write+flush` 中位 **1.8 µs**、p99 5.2 µs——约 50×。当前流量（~4.5k/天）下不构成事故，但它与用户点名的硬约束（proposal §4.1「查询不得拖慢请求处理」）同向，且换成 `logging.FileHandler` 就自然消失（`FileHandler` 持有句柄）。

---

## 2. 「渲染与承载分开」具体怎么落

### 2.1 机制：一条链 + 多个各自带 `ProcessorFormatter` 的 handler

**不需要换掉 `ProcessorFormatter`，也不需要第二条 structlog 链。** 正确形态是：一条共享的**事实生产链**（只加字段，不做任何格式决定），每个 sink 一个 handler，每个 handler 挂自己的 `ProcessorFormatter`，格式决定全部下沉到各自的 `processors` 列表。

【读码】依据在 `structlog/stdlib.py:1136-1211` `ProcessorFormatter.format`：

- 1145 行 `record = logging.makeLogRecord(record.__dict__)` —— 每个 formatter 先浅拷贝 `LogRecord`。
- 1160 行 `ed = cast(dict[str, Any], record.msg).copy()` —— 事件字典也是**浅拷贝**，注释写明理由正是「同一条记录可能被多个 formatter 处理」。

【实测】`/tmp/structlog_probe/probe1_dual_renderer.py`：一条 structlog 链 + 两个 handler（text renderer / JSON renderer），同一批记录：

```
=== TEXT sink ===
[ OK ] 13:24:53 POST /v1/messages bytes_in=1234 model=claude-opus-4-8 prechain_seq=1
[....] 13:24:53 foreign record from a library prechain_seq=2
[....] 13:24:53 exploded exception=Traceback (most recent call last): … ValueError: boom prechain_seq=4

=== JSON sink ===
{"status": "ok", "model": "claude-opus-4-8", "bytes_in": 1234, "event": "POST /v1/messages", "level": "info", "logger": "app.request", "prechain_seq": 1, "timestamp": "…"}
{"event": "foreign record from a library", "level": "warning", "logger": "httpx", "prechain_seq": 3, "timestamp": "…"}
{"status": "fail", "event": "exploded", "level": "error", "logger": "app", "exception": "Traceback…", "prechain_seq": 4, "timestamp": "…"}
```

text renderer `pop` 掉了 `prefix` / `timestamp` / `event` / `level` / `status`，JSON sink **仍然全都有**。**互不干扰成立。**

### 2.2 三个实测出来的坑

#### 坑 1：`foreign_pre_chain` 每个 formatter 各跑一次

看上面 `prechain_seq`：那条 httpx 记录在 text sink 是 2、在 JSON sink 是 3——**同一条记录，pre_chain 被跑了两次**。structlog 原生记录只跑一次（在 `structlog.configure` 的链里，记录时就跑完了）。总计数 4 = 1（原生）+ 2（foreign 两遍）+ 1（原生）。

后果：**共享链里的处理器必须是幂等且无副作用的**。当前 7 个处理器都满足（`format_exc_info` 对已解析过的字典是幂等的，`_add_status_prefix` 重算同一个值）。但这条约束要写进注释，否则下一个往共享链里加计数器、加 ID 分配器的人会静默踩上。

#### 坑 2：`TimeStamper` 放进 per-renderer 链会给出多个时刻

【实测】`/tmp/structlog_probe/probe2_timestamp_and_consumer.py`，共享链已放过一次 `TimeStamper`，两个 sink 各自再放一个：

```
--- structlog-native record（共享链已经放过一次 TimeStamper）
  [sinkA] ts='2026-08-21T13:25:26.618240Z' event='POST /v1/messages'
  [sinkB] ts='2026-08-21T13:25:26.618273Z' event='POST /v1/messages'
```

而共享链写进去的是 `.618147Z`。**`TimeStamper` 覆盖已有的 `timestamp` 键**，同一个事件在两个 sink 里差了几十微秒，而且都不是它真正发生的时刻。

对策，也是唯一正确的形状：**共享链里放且仅放一个 `TimeStamper(fmt=None, utc=True)`，产出 UNIX float；每个 renderer 各自把这个数格式化成自己要的样子。** 这同时解决了 §1.1 第 4 项那个「格式被编进共享链」的结构问题。

【实测】`/tmp/structlog_probe/probe3_carrier_vs_render.py` 验证了这个形状：

```
=== TEXT ===
'[ OK ] 13:27:25 \x1b[32m200\x1b[0m claude-opus-4-8 POST /v1/messages\n'
=== JSON ===
{"status": "ok", "event": "request", "level": "info", "logger": "app.request", "timestamp": "2026-08-21T13:27:25.949Z", "request": {…}}
```

text 拿到本地墙钟 `HH:MM:SS`，JSON 拿到 UTC ISO，**同一次读钟**。注意这里有一个必须人眼确认的点：现行 text 时钟是 `utc=False`（本地时），从 UTC float 派生时若忘了 `time.localtime`，终端时钟会整体偏移一个时区。见 §7。

#### 坑 3：`JSONRenderer` 对 dataclass 与非 str 枚举回落到 `repr`

【实测】：

```
StrEnum    -> {"v": "anthropic"}
plain Enum -> {"v": "<E.A: 'anthropic'>"}
dataclass  -> {"v": "L(m='POST')"}
json.dumps(default=str) 对 dataclass -> {"v": "L(m='POST')"}
```

所以把 `RequestLine` 整个塞进事件字典时，**JSON sink 必须有一个显式的摊平处理器**（`asdict`）；`ReplyDialect` 因为是 `StrEnum` 不受影响。这不是理论洁癖：现行 `write_request_record` 用的 `json.dumps(..., default=str)` 有同样的回落行为，只是它先做了 `asdict` 所以没被咬到。

### 2.3 落地形状（建议）

```
共享事实链 shared_processors（只加字段，不做格式决定）
  merge_contextvars → add_log_level → add_logger_name
  → TimeStamper(fmt=None, utc=True)        # 唯一一次读钟，产出 float
  → format_exc_info                        # 必须在记录时跑
  → _add_status_prefix                     # 语义字段，不是渲染
        │
        ├── console handler ── ProcessorFormatter(processors=[
        │       _format_local_clock,        # float → "%H:%M:%S" 本地时
        │       _render_request_line,       # RequestLine → format_completion_line(unicode=, color=)
        │       remove_processors_meta, _render_text])
        │
        └── file handler ───── ProcessorFormatter(processors=[
                _format_iso_clock,          # float → ISO UTC
                _drop_status_prefix,        # prefix 是终端呈现物，JSON 不要
                _flatten_records,           # asdict(RequestLine) 等
                remove_processors_meta, JSONRenderer()])
```

三处随之而来的改动，都是「把渲染从承载里拿出来」的必然：

1. **`_log_completion` 不再自己渲染。** 由 `get_logger(REQUEST_LOGGER).info(format_completion_line(...), status=...)` 改为把 `RequestLine` 作为字段传出去（例如 `.info("request", status=status, request=line)`）。`format_completion_line` 从「调用点的一步」变成「console renderer 的一步」。随之 `setup_logging` 的 `colors: bool | None` 要扩成完整的 `TerminalCapabilities`——renderer 需要 `unicode` 才能决定 `↑`/`↓` 字形，而 `unicode` 目前**根本没有进入日志层的通路**（见 §9 风险 1）。
2. **`_add_status_prefix` 的定位要重述。** 它现在被当成渲染准备（json 模式还要 `_drop_status_prefix` 撤销）。改成：`prefix` 是**语义字段**（这条记录属于哪个结果档位），共享链算一次，console renderer 直接用，file renderer 丢掉。行为不变，理由变了，且省掉了「加了再删」这个自相矛盾的往返。
3. **`log_format` 参数的含义变了。** 它现在选的是「唯一那个 renderer 是哪种」，之后应当选的是「console sink 用哪种」——file sink 恒为 JSON。旧链路 `app_factory` 仍在传它，签名可以保留兼容，但语义要在 docstring 里说清。

### 2.4 明确不采纳的两条

- **换掉 `ProcessorFormatter`、改用两条独立 structlog 链。** 没有必要：`ProcessorFormatter` 的浅拷贝已经把多 renderer 支撑起来了（§2.1 实测），而两条链会让 stdlib 的 foreign 记录（asyncio / uvicorn / httpx）失去统一入口——那正是当前设计花力气统一的东西（`logging.py:139-140` 的长注释）。
- **`QueueHandler` + `QueueListener` 把文件 IO 挪出事件循环线程。** 【实测】`QueueHandler.prepare` 会把 `record.msg` 换成 `self.format(record)` 的字符串：

  ```
  prepare 后 msg 类型: str  "{'event': 'e', 'status': 'ok'}"
  ```

  【读码】`logging/handlers.py` 源码注释写明它「overwrites the record's msg and message attributes with the merged message」。**结构化字典在入队时就被销毁了**，之后的 `ProcessorFormatter` 只会看到那个字符串的 `repr`。要用队列就必须自己覆写 `prepare`。鉴于 §1.6 测出持久句柄写一条只要 1.8 µs，本次不引入队列；若日后确实需要，记住这个坑。

---

## 3. TUI 怎么从结构化流里消费

### 3.1 先把「为什么要抢占」说准

`FooterTui` 现在身兼两职，但抢占 root handler 的理由**只来自其中一职**：

- **渲染器**：`activate()` 132-137 行从 root 上已有的 handler 抄走 formatter。这一职在渲染与承载分开后自然消失。
- **终端所有者**：`LiveConsoleHandler` 的 docstring（`tui.py:70-80`）记录了三条已付过代价的事实——`rich.Live` 按行数擦除并重绘自己的区域，任何绕过它写同一个终端的写者都会被擦掉或把区域顶走；`markup=False` 是因为 `[ OK ]` 会被 rich 当成样式标签吞掉；`soft_wrap=True` 是因为 rich 会自己折行导致请求行断成两截。**这一职不会因为日志结构化而消失。**

所以要说准：**结构化承载并不会让「TUI 需要接管终端输出」这件事消失，它只让「TUI 需要替换整个 handler 列表」这件事消失。** 只要 file sink 不写终端，它和 Live 区域就没有冲突，可以整段活着。

> 这一条是本设计里最容易被误读的地方。proposal §4.4 写「把它改成结构化流的消费者，抢占这件事根本不会发生」——如果「抢占」指的是替换整个列表，成立；如果指的是「不再需要接管终端写者」，不成立，理由是上面那条 rich.Live 的物理事实（该事实为项目已记录的一手结论，本次未重新用 pty 复验，取信档位：足以据此设计，若要动 Live 的用法则需重测）。

### 3.2 `activate()` 还要不要动 root.handlers

**要动，但改成只换一个 handler，不换整个列表。** 具体：

- `setup_logging` 给 console handler 一个稳定身份（`handler.set_name("console")`），并在模块内暴露一个取回它的函数。
- `activate()` 取出 console handler，**只把它替换成** `LiveConsoleHandler`（沿用同一个 `ProcessorFormatter`），退出时换回。file handler 与任何第三方 handler 全程不受影响。
- 更彻底的替代：console handler 不被替换，而是**换掉它的写出目标**——把 `StreamHandler.setStream` 指到一个把 `Text.from_ansi(...)` 交给 `live.console.print` 的适配器。这样连 handler 身份都不变。**倾向后者**，因为它让「谁负责渲染」在整个进程生命周期里只有一个答案。但它要求那个适配器逐行地把字节交出去（`StreamHandler.emit` 会写 `msg + terminator` 再 `flush`），需要一次小 PoC 确认换行不会在 Live 区域里多吃一行——**本次未验证**，列为分片 2 的第一件事。

### 3.3 TUI 拿到的是什么

【实测】`/tmp/structlog_probe/probe2_timestamp_and_consumer.py` 里一个什么都不做的 `logging.Handler`：

```
logger=app.request  is_dict=True   msg={'status': 'ok', 'model': 'opus', 'event': 'POST /v1/messages', 'level': 'info', 'timestamp': '…'}
logger=httpx        is_dict=False  msg='library line'
```

即：**structlog 原生记录的 `record.msg` 就是走完共享链之后的事件字典；foreign 记录的 `record.msg` 是一个普通字符串。** 任何消费者都必须处理后者。

本仓已经在用这个形态了——`tests/int/test_pipeline_app.py:1298-1306` 的 `_request_prefixes` 直接读 `cast(dict[str, Any], record.msg)["prefix"]`。所以这不是新机制，是把已经在测试里用的东西提到生产。

于是三个问题的答案：

| 问题 | 答案 |
|---|---|
| TUI 拿到的是已渲染的行还是事件字典？ | **两者都要，但走两条不同的路**。终端上那一行必须是 console renderer 渲染出来的字符串（否则 TUI 就又成了渲染器）；TUI 自己的状态更新应当读**事件字典**（`record.msg`），或者更好——读字典里的 `RequestLine` 对象本身 |
| 谁负责送过去？ | 送**行**的是 console handler（TUI 只是接管了它的写出目标）；送**字典**的是一个独立的、不写终端的 handler（消费者 handler），由 `activate()` 挂上、退出时摘掉 |
| `activate()` 还需不需要动 root.handlers？ | 需要，但从「替换整个列表」降级为「替换/改写一个 handler，并追加一个消费者 handler」。**不再有任何 handler 因为 TUI 激活而收不到记录** |

### 3.4 一个必须说清的范围界线

**当前的 footer 其实不需要读日志流。** 它的数据源是 `ActiveRequestRegistry`（`observability/active_requests.py`），字段只有在途请求的 `request_id / model / started_at / bytes_out / attempts`，`finish()` 一调用就 `remove`。日志流对它零贡献。

真正需要读结构化流的是 proposal §5 记的那两件「看到了但本次不做」：**TUI 历史回看面板**（需要已完成记录，而那正是 registry 丢掉的）和按 `message.id` 关联两侧记录。

因此「TUI 从结构化日志解析」这个裁决的落地有两种读法，**我不替你选**（§8 分叉 1）：

- **读法 A（最小）**：本次只做到「TUI 不再抢占、消费者接缝留好」，footer 数据源不变。分片 2 小而稳，人眼验收只需确认终端看起来没变化。
- **读法 B（完整）**：本次就把 footer 改成读结构化流，让它能显示最近完成的若干条。这直接把历史面板的地基打好，但它改变了终端上人眼看到的东西，验收成本高一档，且与 `.dev/docs/tui/spec.md` 已有的视图模型有交互。

---

## 4. 文件 sink 的完整合同

### 4.1 与既有 `requests-*.jsonl` 的关系（先决问题）

在谈路径和轮转之前必须先答：新的通用日志文件与 `request_log_file.py` 写的 `requests-*.jsonl` 是什么关系？三条路：

| 选项 | 形态 | 代价 |
|---|---|---|
| **并存** | `requests/requests-*.jsonl` 不动；新增 `logs/app-*.jsonl` 承载全部日志（含请求行的结构化副本） | 请求记录落两份盘（当前 ~0.9 KB/条 × 2）。取证时要知道查哪个。**但两份格式不同、受众不同**，未必是坏事 |
| **合并** | `write_request_record` 撤掉，请求记录只作为一条结构化日志进 `logs/app-*.jsonl` | 一份权威。但 `requests-*.jsonl` 的字段是**平铺**的（`asdict` 直接展开到顶层），合并后会变成 `request.{…}` 嵌套，**破坏现有文件的 schema**，且触及「不得擅自删除已实现的功能」 |
| **分层** | 通用日志走 `logs/`；`requests-*.jsonl` 保留，但改由一个订阅结构化流的 sink 写，而不是由 `_log_completion` 直接调 | 消除第二条投递路径，保住文件合同。改动面最小、语义最干净 |

**我倾向「分层」**，理由是它同时满足三条既有取向：单一权威（事件流）、不删已实现的功能（文件合同不变）、消除 §1.6 第 2 条的双路径。但这是**推定**，不是裁决过的，列入 §8 分叉 2。

### 4.2 路径

沿用本项目已经立过两次的先例：**派生而不是发明配置键**。

- `rejection_capture.py` → `user_data_path()/rejected/`，`config.example.yaml` 无对应键，模块 docstring 明写「一个在这里发明出来的键是操作者没要求做的决定」。
- `request_log_file.py` → `user_data_path()/requests/`，同样无键。

所以：**`user_data_path()/logs/app-YYYYMMDD.jsonl`，默认开启，无配置键。** 不做可配置路径，直到用户要求。

> 反向核对：`config.example.yaml` 是否已经有日志相关的键？`ProxyConfig` 里没有 `log_format` / `log_level`（§1.2 实测）。所以这里不存在「有键不接」的问题，与 `history.enabled` 那个死开关不同类。

### 4.3 格式

**JSON Lines，一条记录一行，UTF-8，`ensure_ascii=False`。** 与 `requests-*.jsonl` 同形。

必备键（由共享链保证）：`timestamp`（ISO UTC，毫秒精度）、`level`、`logger`、`event`。加上按记录携带的 `status`、`request`（摊平的 `RequestLine`）、`exception`。

**不写 `prefix`**：它是终端呈现物，由 file renderer 的 `_drop_status_prefix` 丢掉。**不写 ANSI**：渲染下沉之后，`event` 不再是渲染产物，颜色只在 console renderer 里施加——这顺带修掉了前序调研记的那个坑（「在能上色的终端下开 JSON 模式，`event` 里会带 ANSI 转义」）。

### 4.4 轮转与保留

**按 UTC 日切文件 + 按文件名保留最新 N 天**，与 `request_log_file._prune` 完全同形（文件名末尾是 `YYYYMMDD`，字典序即时序，复制或恢复过的文件不会因为 mtime 变了就插队）。

不用 `RotatingFileHandler` / `TimedRotatingFileHandler`，两条理由：

1. 项目已有的两个 sink 都用「日期文件名 + 按名剪枝」，第三种轮转形态没有收益。
2. `TimedRotatingFileHandler` 的滚动发生在**下一条记录到达时**，且它按进程启动时刻计算窗口；对一个可能几小时没有流量、又要被 systemd 重启的服务，文件边界会和日期对不上。日期文件名不受这两件事影响。

`KEEP_DAYS` 取什么值：`requests-*.jsonl` 是 14 天。通用日志比请求记录**每条更小但每天更多条**（库的 WARNING、shutdown 阶梯、启动行）。当前无实测量级——请求行 0.9 KB/条 × ~3.3k/天 ≈ 3 MB/天，通用日志的额外部分**没有数据**。**建议先取 14 天与既有对齐，并在分片 1 落地一周后实测一次真实日增，再决定是否调整**（这是一个观测，不是门）。

### 4.5 写失败时的行为

`logging` 的既有行为已经对：`Handler.emit` 里的异常走 `handleError`，默认打到 `sys.stderr` 且**不向调用者传播**。这与 `request_log_file.write_request_record` 的立场一致（「Durable observability is subordinate to serving the request」）。

需要额外决定的只有一件：**磁盘满或目录不可写时，要不要在 console 上说一句。** `logging.raiseExceptions` 默认 `True`，`handleError` 会往 stderr 打一次完整 traceback——**每条记录一次**。在一个满盘的机器上这会把终端刷爆。建议：给 file handler 覆写 `handleError`，第一次失败时通过 console logger 报一条 WARNING，之后静默计数，恢复时再报一条。**这不是吞掉错误**——错误被显式报告了一次并被计数，只是不重复。

### 4.6 shutdown 时的 flush

三层，从可靠到不可靠：

1. **每条记录已经落盘。**【实测】`logging.StreamHandler.emit` 源码含 `self.flush()`，`FileHandler` 是它的子类。写一条后另一个 reader 立刻读得到（实测 `size: 6`）。所以正常情况下**不存在需要在 shutdown 补 flush 的缓冲数据**。
2. **解释器正常退出**：`logging` 模块自己在 `logging/__init__.py` 末尾 `atexit.register(shutdown)`，会 flush + close 所有 handler。本仓 `src/` 下**没有任何 `atexit` 或 `logging.shutdown` 调用**【实测 rg】，靠的就是这个默认。
3. **`SIGKILL` / `os._exit`**：无法保证。但因为第 1 层，丢的最多是 OS page cache 里未落盘的部分，而不是进程缓冲区里整批记录。

结论：**不需要为 flush 做任何新东西。** 建议只做一件小事——在 shutdown 阶梯的最后一级（`lifecycle/standalone.py::_finalize` 附近）记一条「日志文件路径 + 本次写入条数」的行，让操作者知道去哪找。这是便利，不是正确性要求。

用 `delay=True` 建 `FileHandler`：【实测】文件在第一条记录写入前不存在。避免每次 `--help` 都在数据目录里留一个空文件。

---

## 5. 兼容面

### 5.1 会被影响的测试

| 文件 | 怎么被影响 | 严重度 |
|---|---|---|
| `tests/unit/observability/test_logging.py`（8 个测试，全部用 `capsys` 读 stderr） | `setup_logging` 装两个 handler 后，**stderr 上仍只有 console 那一份**，text 断言不受影响。但 `test_json_renderer_includes_context_and_event`（26 行）等 3 个 json 测试断的是 `json.loads(captured.err)`——json 若变成「console sink 的一种模式」则仍成立，若 json 只留给 file sink 则这些测试要改成读文件 | **中**。取决于 §2.3 第 3 条怎么定 |
| `tests/unit/observability/test_logging.py::test_a_logged_exception_carries_its_stack`（71 行） | 断 traceback 出现在 text 输出里。`format_exc_info` 仍在共享链，行为不变 | 低 |
| `tests/int/test_pipeline_app.py:1298 _request_prefixes` | 读 `record.msg["prefix"]`。**`prefix` 仍由共享链产出，仍在 `record.msg` 里** | 低（应当继续通过，是一个好的回归锚点） |
| `tests/int/test_pipeline_app.py:1481` 附近 | docstring 里写死了整行渲染结果 `[ OK ] 09:00:11 H1/H2 200 …`。渲染逻辑搬家但输出应逐字节不变——**这是分片 1 的主判据** | **高**。它是「渲染搬家没改变输出」的唯一现成证据 |
| `tests/unit/observability/test_request_log.py` | 只测 `format_*` 纯函数，不经 logger。**渲染下沉后这些函数的签名与行为不应变**，测试不受影响 | 低 |
| `tests/unit/observability/test_request_log_file.py`（含 `test_prune`、完整键集断言） | 只有在 §4.1 选「合并」时才被破坏；选「并存」或「分层」则不变 | 取决于分叉 2 |
| `tests/unit/lifecycle/test_shutdown_reporting.py:28-31` | fixture 先 `setup_logging` 再 `logging.getLogger().handlers.clear()`。**清的是全部 handler**，两个 handler 时同样清干净。但它随后用 `caplog`——若测试环境下 file handler 仍然装上并往真实 `user_data_path()` 写盘，会污染用户数据目录（proposal §2.1 已经点名过同类问题） | **高**，见 §5.3 |
| `tests/tui/_footer_driver.py:24` | `logging.basicConfig(...)` + `tui.activate()`。当前 `activate()` 替换整个列表，所以 basicConfig 那个 handler**被换掉**，只有 Live 一份输出。改成「只换 console handler」后，basicConfig 装的 handler 与 `LiveConsoleHandler` **同时存在**，每条日志出现两次，`tests/tui/test_footer_screen.py` 的 `LOG-\d{4}` 序数断言会看到重复 | **高**。driver 必须同步改成走 `setup_logging` |
| `tests/tui/test_footer_screen.py`（4 个 pyte 屏幕测试） | 间接受上一条影响。`test_the_scoring_catches_a_footer_that_scrolled_out_of_place` 是负样本对照，不受影响 | 中 |
| `tests/unit/observability/test_observability_footer.py` | 只测 `build_footer` 纯函数 | 无 |
| `tests/unit/test_imports.py` | 提到 structlog，需确认新增 import 不破坏闭包断言 | 低 |
| `tests/unit/test_module_boundaries.py` | 新链路禁区是 `app.server.app_factory` / `app.pipeline.executor` / `app.routes.*`。`app.observability.*` 不在其中 | 无 |

### 5.2 生产侧会被影响的东西

- **`src/app/server/app_factory.py:55`**（旧链路）传 `settings.observability.log_format`。签名兼容即可，但要确认它不会因为多装一个 file handler 而在测试里写盘（同 §5.3）。
- **`src/app/cli.py:251`** 是唯一生产调用点，写死 `log_format="text"`。文件 sink 一旦默认开启，它就开始往 `user_data_path()/logs/` 写——这是**新增磁盘写入**，按项目纪律（proposal §6.3）**需要 Spec**。
- **systemd 部署形态**：`detect_terminal().live` 为假 → 无 TUI → console handler 直写 stderr → journald。文件 sink 与 journald **并存且内容重复**。这不是缺陷（journald 有轮转与查询、文件有结构化字段），但要在 Spec 里写明是有意的。

### 5.3 一个必须一起解决的前置问题

`request_log_file` 的测试用 `monkeypatch.setattr(request_log_file, "user_data_path", lambda: tmp_path)` 把落点挪走（`test_request_log_file.py:26`）。**但任何调用 `setup_logging` 的测试都没有这层保护**——`tests/unit/observability/test_logging.py` 有 8 处、`test_shutdown_reporting.py` 有 1 处、`test_pipeline_app.py` 有 1 处。文件 sink 一旦默认开启，这 10 处会开始往用户真实数据目录写 `logs/app-*.jsonl`。

这与 proposal §2.1 记的问题（测试往 `~/.local/share/ghc-api-proxy/history.db` 写了 8,630 行）**是同一个形状，且这次是我们主动引入的**。所以分片 1 必须自带对策，两条择一或并用：

1. `setup_logging` 增一个 `log_dir: Path | None` 参数，测试传 `tmp_path`；
2. 一个 session 级 autouse fixture 把 `user_data_path` 指到 `tmp_path`——**但按项目纪律（`.claude/rules/00-development-workflow.md`），这类 setup 不得放进共享 `conftest.py`**，因为它会把一个组的环境强加给所有组。

**倾向第 1 条**：它是显式参数，谁需要谁传，不改变任何其他测试组的环境。

---

## 6. 分片建议

### 6.1 能拆成两步，每步各自可交付

| 分片 | 内容 | 交付后谁能回答什么 |
|---|---|---|
| **1 结构化承载** | 共享链去掉格式决定（`TimeStamper(fmt=None)` + `prefix` 语义化）；`_log_completion` 改为传 `RequestLine` 字段；console/file 两个 handler 各带自己的 `ProcessorFormatter`；file sink 写 `logs/app-*.jsonl`；`setup_logging(log_dir=)` 让测试可隔离 | **在非交互场景（systemd、管道、CI）下**，任何人能回答「昨天 03:14 那条 400 前后发生了什么」——包括请求行之外的库 WARNING、shutdown 阶梯、catalog 失败。**但交互式终端下仍然拿不到**，因为 TUI 还在替换整个 handler 列表 |
| **2 TUI 改消费者** | `activate()` 从「替换整个列表」改为「接管 console 的写出目标」；挂上不写终端的消费者 handler；`tests/tui/_footer_driver.py` 改走 `setup_logging` | **在交互式终端下**同样能回答上面那个问题。这才是取证现场真正被覆盖的时刻 |

### 6.2 分片 1 单独交付有没有价值——诚实说

**有，但比它看起来的小，而且必须写明界线。** 生产的唯一入口 `cli.py start` 在交互式终端下**默认激活 TUI**（§1.4），而那正是 proposal §4.4 说的取证现场。所以分片 1 交付后：

- systemd / 管道 / CI 下：完全可用。
- 人在终端里盯着跑：**file sink 是空的**，因为 `root.handlers = [handler]` 把它换掉了。

因此分片 1 的交付说明里必须有一句「交互式终端下本片不生效，由分片 2 补齐」。**不写这句话，第一个去查文件却查到空的人会得出「这功能坏了」的结论。**

> 一个更省事的替代：分片 1 顺手在 `activate()` 里把 `root.handlers = [handler]` 改成保留非 console 的 handler（一行改动），分片 2 再做完整的消费者接缝。**这恰好是用户推翻掉的那个原方案的动作。** 我不采纳，记在这里说明为什么：那一行改动会让分片 1、2 之间存在一个「TUI 半改」的中间态，而 §5.1 已经测出 `tests/tui/_footer_driver.py` 会因此重复输出——即修一行会同时欠下一次 driver 改造。收益（提前一个分片覆盖交互式场景）小于代价（一个说不清的中间态 + 一次注定要重做的测试改造）。若用户认为交互式覆盖必须提前，这个取舍可以反过来，**请示下**。

### 6.3 顺序不可交换

分片 2 依赖分片 1：TUI 作为消费者要消费的东西（干净的事件字典、下沉后的 renderer）由分片 1 产出。反过来做的话，分片 2 只能消费一个 `event` 是渲染字符串的流——那正是现在的形态。

### 6.4 与 proposal §6.1 的对齐

proposal 的分片 1、2 与本文一致，编号可直接沿用。本文相对 proposal 新增两条约束：分片 1 必须自带测试落点隔离（§5.3），分片 2 必须自带 `_footer_driver.py` 改造（§5.1）。

---

## 7. 哪些部分必须人眼验收

项目既定：界面呈现的验收标准是人看着对不对，测试替代不了。具体到本工作：

| 何时 | 看什么 | 为什么测试不够 |
|---|---|---|
| **分片 1 之后** | `ghc-api-proxy start --verbose`，打几条真实请求，**逐字节对照渲染搬家前后的终端输出**：状态前缀、时钟、颜色、`↑`/`↓` 字形、extras 尾巴、异常的多行 traceback | 渲染从调用点搬到 renderer，颜色与 unicode 能力的传递路径整个换了。`test_pipeline_app.py:1481` 的 docstring 断言只覆盖一条 `[ OK ]` 行 |
| **分片 1 之后** | **时钟是本地时还是 UTC**。§2.2 坑 2 的对策是从 UTC float 派生，忘了 `localtime` 就整体偏移一个时区 | 这类偏移在测试里往往被 freeze 掉或恰好在 UTC 环境下跑，看不出来 |
| **分片 1 之后** | 一条 `[FAIL]` 行同时出现在终端与 `logs/app-*.jsonl`，**两边说的是同一件事**（时刻一致、状态一致、字段没丢） | 两个 sink 的一致性是本设计的核心承诺 |
| **分片 2 之后** | footer 活着的时候：日志行不被 Live 区域吞掉、footer 始终钉在底部、退出后终端干净还原、scrollback 里没有 footer 残影 | `tests/tui/test_footer_screen.py` 用 pyte 覆盖了这四条，但它跑的是 `_footer_driver.py`；driver 本身被改过之后，**先要人眼确认真实 `start` 的观感**，再信那四条绿 |
| **分片 2 之后** | 终端能力降级路径：`NO_COLOR=1`、`TERM=dumb`、`ghc-api-proxy start 2>&1 \| cat` 三种，各看一次 | 能力探测的三个维度（live / color / unicode）在渲染下沉后由 renderer 读取，路径变了 |
| **分片 2 之后（仅当选读法 B）** | footer 显示最近完成记录时的观感 | 新的界面元素，无既有基线可比 |

**不建这些的验收门。** 上面是检查清单，不是阻断交付的装置。

---

## 8. 需要你示下的三个分叉

1. **TUI 消费的深度**（§3.4）。读法 A：只做到「不再抢占 + 留好消费者接缝」，footer 数据源不变，分片 2 小而稳。读法 B：footer 本次就改为读结构化流并显示最近完成记录，把历史面板的地基打好，但改变了人眼看到的东西。**我倾向 A**——裁决的原话是分层问题，读法 A 已经把分层改对了；显示什么是独立的界面决策，proposal §5 也把历史面板列为「等分片 2 落定后单独立项」。

2. **通用日志文件与既有 `requests-*.jsonl` 的关系**（§4.1）。并存 / 合并 / 分层。**我倾向分层**：通用日志走 `logs/`，`requests-*.jsonl` 文件合同不变但改由订阅结构化流的 sink 写。这消除了 `_log_completion` 里的双投递路径，又不删任何已实现的功能、不破坏现有文件 schema。

3. **`log_format` 参数今后的含义**（§2.3 第 3 条 / §5.1）。file sink 恒为 JSON 之后，`log_format="json"` 是（a）继续存在、表示 console 也输出 JSON，还是（b）废弃、由 file sink 取代？选 (b) 会让 `test_logging.py` 的 3 个 json 测试改成读文件；选 (a) 保持兼容但留下一个「两个地方都能产 JSON」的形态。**我倾向 (a) 保留**——旧链路 `app_factory` 还在传它，且「把 console 也切成 JSON」对着管道跑时仍有用；成本只是多一个 renderer 分支。

另有两项**已按既有取向推定、请你否决**：文件 sink 派生路径而不发明配置键（§4.2，沿用 `rejection_capture` / `request_log_file` 两次先例）；日切文件 + 按名保留 14 天（§4.4，与 `request_log_file.KEEP_DAYS` 对齐）。

---

## 9. 我认为最大的三个风险

1. **渲染搬家改变了终端输出而没人发现，`unicode` 尤其。** 这是分片 1 唯一真正危险的地方。`format_completion_line` 的 `unicode` / `color` 两个参数现在由 `_log_completion` 从 `chain.capabilities` 取（`pipeline_app.py:243`），搬进 renderer 后必须改由 `setup_logging` 一侧提供。【实测】两侧同源但**不是同一次探测**：`composition.py:273` 是 `capabilities: TerminalCapabilities = field(default_factory=detect_terminal)`，`logging.py:128` 是 `detect_terminal().color if colors is None else colors`——两次独立调用同一个探测函数，正常情况下答案一致。

   真正的缺口是：**`setup_logging` 当前只接 `colors`，`unicode` 根本没有进入日志层的通路。** 渲染下沉后 renderer 需要 `unicode` 才能决定 `↑`/`↓` 字形，所以 `setup_logging` 必须改成接一个完整的 `TerminalCapabilities`（并把它与 `Chain` 共享同一个实例，顺带消掉那处「两次探测」的潜在分家——`logging.py:127` 的注释「One detector for the whole process」现在其实并不成立）。

   若这一步做漏或做偏，请求行的字形/颜色会与 footer 的判断分家，而现有测试**全部用 `colors=False` 跑**，看不出来。对策是 §7 第一行的逐字节人眼对照。

2. **分片 1 单独上线时，交互式终端下文件是空的。** §6.2 已说明。风险不在技术上，在**交付说明写不写那句话**。

3. **测试开始往用户真实数据目录写日志。** §5.3。10 个调用 `setup_logging` 的测试位点没有任何落点隔离，而 proposal §2.1 已经记过同一形状的事故（8,630 行测试流量写进真实 history.db）。这件事必须与分片 1 同片解决，不能排到后面。

---

## 附：一次性验证脚本

| 脚本 | 验证了什么 |
|---|---|
| `/tmp/structlog_probe/probe1_dual_renderer.py` | 一条链 + 两个 `ProcessorFormatter` 互不干扰；`foreign_pre_chain` 每 formatter 各跑一次 |
| `/tmp/structlog_probe/probe2_timestamp_and_consumer.py` | per-renderer `TimeStamper` 会给出多个时刻；裸 `logging.Handler` 看到的 `record.msg` 是事件字典（foreign 时是字符串） |
| `/tmp/structlog_probe/probe3_carrier_vs_render.py` | 共享单次读钟 + 各自格式化；`RequestLine` 一侧渲染成行、另一侧摊平成字段；`JSONRenderer` 对 dataclass 回落到 `repr` |

内联跑过、未存盘的三次：`JSONRenderer` 对 `StrEnum` / `Enum` / dataclass 的回落对照；`StreamHandler.emit` 每条 flush 与 `QueueHandler.prepare` 销毁字典；落盘代价基准（开闭+glob 94.9 µs vs 持久句柄 1.8 µs）。
