# 取证记录能力方案（history 增强）

状态：**主要分叉已裁决（2026-08-20），可进入 Spec 与实施**。版本：r4。

---

## 阅读指引

任务原话是「接上 history 功能，用户希望增强调研能力」。调查后发现这句话下面压着一个更大的事实：**现有 history 在生产链路上从未被调用过**，所以这不是给 history 加字段，而是决定新链路要不要有取证记录、记什么、记在哪、怎么查。

**第四节是裁决记录**（含用户点名的硬约束与仍需示下的三个小项），**第六节是分片计划**。前三节是支撑事实，第五节是不采纳项。

### 版本沿革

- **r1** → 两路独立评审（事实向 6 blocker / 范围向 2 blocker，共 32 条），全部采纳，全文重写为 r2。
- **r2** → 同两位评审者复评（事实向新增 5 major、范围向新增 1 blocker，共 19 条），全部采纳，**定点修改**为 r3。
- **r3** → 聚焦抽查（五处指定项 + 一致性扫描），发现 §6.2 一处硬矛盾与 §1.3 一处措辞过绝，均已修正。
- **r3 → r4** → **用户裁决**（见第四节），三项推翻我的推荐，据此改写第四、六节与 3.4、3.6。

r1 错得最实的六处：把 `_log_completion` docstring 的愿景当成既成保证；把有损的 `SseEvent` 当成可保真的记录点；把「复用 `app.history` 存储层」说成几乎免费；**引用我自己推导的 `history-system.md` 去论证掉 REST/WS，而用户亲笔的 `MAIN.md` 恰恰把它列为产品端点**；帧表漏了时间戳列，使 L3 只剩固件价值；整份文档没提日志文件 sink。

r2 在重写中新引入的四处：把 L2 说成「数据已在手」（实际前序 attempt 看不到）；取证表上套了 cassette 的 headers allowlist，与自己 3.5 节的立场冲突；把容量上限排到最后一片，留下「默认写盘但无上限」的中间态；**把日志 sink 说成「加个 handler 即可、可以单独批」，而 TUI 激活时会整体替换 root handler，交互式终端下文件是空的**。

> r1 → r2 用全文重写，代价是 15 条新问题。此后各版改用定点修改，就是吃这个教训。

完整评审报告：`reports/260820-review-history-forensics-proposal.md`、`reports/260820-review-history-forensics-scope.md`（r1 轮）、`reports/260820-review-history-forensics-proposal-r2.md`、`reports/260820-review-history-forensics-scope-r2.md`（r2 轮）、`reports/260820-review-history-forensics-r3-spotcheck.md`（r3 抽查）。逐条处置见第七节。

### 证据基线与一个警告

三份只读调查：`reports/260820-history-wiring-audit.md`、`reports/260820-forensic-demand-audit.md`、`reports/260820-history-as-fixture-source.md`。

> ⚠️ **有并行会话正在改本方案要动的文件。** 本会话开始时工作树中已修改的源文件只有 `bundled-config.yaml`、`sse_source.py`、`stream.py`；进行期间又出现了 `src/app/server/pipeline_app.py`、`src/app/observability/request_log.py`、`src/app/pipeline/delivery/assembler.py`。`_Trace.failed` 字段就是在这期间出现的。
>
> 因此本文档**一律按符号名指路，不写行号**。实施方式也受此约束，见第六节。

---

## 一、事实：现状

### 1.1 history 没有接在生产链路上

生产入口 `cli.py` → `create_pipeline_app`（`src/app/server/pipeline_app.py` + `composition.py`）。实测 import 闭包：`app.server.pipeline_app` 达 111 个 `app.*` 模块，`app.cli` 达 125 个，**两者都不含 `app.history*`、不含 `app.routes*`**。

接了 history 的是 `app.server.app_factory.create_app()`（旧链路），生产从不调用。调用它的是测试套件，**例如** `tests/http/*`、`tests/integration/test_server_startup.py`、`tests/smoke/test_anthropic_responses_route.py`、`tests/smoke/test_anthropic_responses_stream_route.py`、`tests/unit/test_observability_phase6.py`（r1 曾把这写成「只有」前两类，是错的全称断言）。

旧链路内部自带一处分裂：`/v1/messages` 走 `HistoryConsumer`，而 `openai.py` / `azure.py` / `gemini.py` / `responses_ws.py` 绕开它，用 `routes/protocol_history.py` 手写等价逻辑操作同一个 store。

`ProxyConfig.history`（`src/app/config/schema.py` 的 `HistoryConfig`，只有 `enabled: bool`）**没有任何消费者**——对 `src/**/*.py` 做 AST 搜索，`config.history` / `proxy_config.history` / `chain.config.history` 的运行时读取为 0。`--history/--no-history` 因此是死开关。

> 注意别与旧链路 `src/app/config/settings.py` 里的另一个同名 `HistoryConfig` 混淆，后者确实被 `app_factory` 消费。

**实测数据库快照（截至 2026-08-20 09:13:36）**：`~/.local/share/ghc-api-proxy/history.db` 8,630 行（09:00 时为 8,534 行，说明它此刻仍在增长），`endpoint` 分布无一条 `anthropic-messages`，`request_payload` 平均 46.66 字节。这是测试套件写进真实用户数据目录的痕迹。

### 1.2 边界测试不禁止复用 history 存储层

`tests/unit/test_module_boundaries.py` 的新链路禁区恰为三项：`app.server.app_factory`、`app.pipeline.executor`、所有 `app.routes.*`。`app.history` 不在其中。实测闭包：`history.types`=6、`sqlite.writer`=6、`store`=9、`consumer`=34，**三类违规均为 0**。

所以边界测试不是障碍。真正的障碍是接口不匹配，见 1.5。

### 1.3 采集点：两处已有，一处需要扩展观测合同

| 层 | 采集点（符号名） | 现状 |
|---|---|---|
| L1 完成记录 | 非流式在 `_serve` 的返回前；流式在 `_StreamAccounting.finish` | `_Trace` 已攒满字段，只写 stdout。**采集点已有，但不是 exactly-once，见 1.4** |
| L2 上行快照 | 最终 attempt 在 `_dispatch` 设置 `trace.bytes_in` 处；**前序 attempt 无采集点** | 见下方限定 |
| L3 上游帧 | `_counted_upstream` | 已逐 chunk 遍历并计数，原始字节在手，只需旁路 |

> ⚠️ **L2 的限定（r2 曾把这条说过头，r3 又说得太绝对）**：`RequestContext.attempts` 里的 `Attempt` **已经**记了 `index` / `endpoint` / `payload`（字典）/ `status_code` / `error`（字符串）。所以不是「前序 attempt 毫无采集」。
>
> 但离 L2 要的还差六样，且每一样都有具体理由：
>
> | 缺的 | 为什么不能用现有的替代 |
> |---|---|
> | 实际序列化发出的字节 | `Attempt.payload` 是发送**前**的字典。既有裁决明确 `↑` 要从 `response.request.content` 取，因为翻译会重写 payload，被计费和 tokenize 的是发出去的那一份 |
> | 上游 method / path | cassette 必需；`trace.path` 是客户端入站路径，不是上游路径 |
> | 请求头与「是否认证过」 | cassette 必需 |
> | 响应头与 `extensions` | cassette 必需（含 `http_version`）；L1 只有压缩过的 H1/H2 显示标签 |
> | 上游错误响应体**原文** | `Attempt.error` 只是一个字符串，不是上游回的 body。而排障要的恰恰是上游原话 |
> | 每次 attempt 的起止时刻 | 判断是哪一次 attempt 慢、慢在哪 |
>
> 而 `_dispatch` 那个位置只看得到**最终**那次交换的 `response`，所以这六样要在 attempt 边界上采，需要扩展 driver / transport 的观测合同。这是 L2 的真实成本。

L1 与 L3 确实只需要在已有的手上留下东西；L2 不是。

### 1.4 但 L1 的采集点当前不是 exactly-once

**这条推翻了 r1 的核心假设。** `_log_completion` 只有两个调用点：`_serve` 中 `_dispatch` 正常返回后，以及 `_StreamAccounting.finish`。

- **流式路径是真 exactly-once**：`_StreamAccounting.finish` 自带幂等标记，generator 与 response 的 `__call__` 两个收尾者谁先到谁记录。这一层设计是好的，可以直接依赖。
- **非流式路径有洞**：`_serve` 捕获 `_dispatch` 抛出的 `BaseException` 后只从 active registry 删除再 `raise`，**不记录**。`await request.body()`（客户端中途断连）、`response.json()`、翻译层的非预期异常都走这条路。

评审用临时探针令 `Request.body()` 抛错，确认请求异常退出且完成记录为 0。函数 docstring 写的「每一条退出路径都必须产出且仅产出一条」是愿景，不是事实。

> 未注册 URL 的 404 不记录，那是代码里明确声明的边界（「a 404 for a path this proxy does not serve is not a proxied request」），不算洞。

### 1.5 `HistoryEntry` 承不住 L1

| 差异 | 具体 |
|---|---|
| 字段 | `HistoryEntry` 要 session_id / agent_id / endpoint / ModelRef / `request_payload`；`_Trace` 有 method / path / 两侧协议 / duration / 双向 bytes / stop_reason / tools / thinking / dialect / attempts / detail。交集很小 |
| 时间 | `_Trace.started` 是 `time.monotonic()`，**不能当 SQLite 的墙钟 `started_at`** |
| 写法 | `writer` 以无列名的 14 个位置参数写整行，又按固定下标反序列化。加列要同步改写所有 positional SQL、reader 和已有库迁移 |
| 同步性 | `_log_completion` 是同步函数，`HistoryStore.finalize` 是 async；唯一的同步入口 `submit_nowait` 在 `discardable=False` 时**直接抛 ValueError** |

结论：**可以共用同一个数据库文件与「单 writer + 有界队列 + 线程池下沉」的实现模式，但不该复用 `HistoryEntry` / `entries` 合同。** 新 DTO、新表。

### 1.6 记帧的位置：raw chunks，不是 `SseEvent`

`parse_frame` 用 `errors="replace"` 解码（有损）、丢弃注释行（**包括保活帧**）、丢弃不认识的字段名、剥掉一个前导空格、再用 `"\n"` 重接 data 行。从 `SseEvent(event: str, data: str)` **无法**还原原始字节，更没有输入 chunk 边界。

`copilot-api-js` 的 `from_history.py` 踩的两个坑（同一事件存 3-4 份、存的是被 id 修复改写过的版本）说的是「解析后／被改写过」的事件。**在 `_counted_upstream` 记原始字节，位于所有解析之前，既更保真又更彻底地躲开这两个坑，实现还更简单。**

第三份调查建议记在 `read_events`，本版**不采纳**该建议，理由如上。

> 补充限定：`read_events` 是**当前生产闭包内**的唯一帧解析点。全仓另有 `src/app/streaming/openai_sse.py`、`src/app/streaming/anthropic_usage.py` 两个独立解析器，都在旧链路。

**硬纪律保留**：不要在 `assembler` 之后再记第二份。那样记下来的东西恰好丧失了记录它的理由。

> 一个容易误配的对应关系：raw chunk 采集点**不等于**人写配置里的 `on_upstream_sse_block_ready`。后者的语义是「完整的块」，而 raw chunk 是任意边界的传输分片，二者不是一回事。见第五节末对钩子点的定位。

### 1.7 排障真正缺的是什么

按被点名次数排序：

| 缺口 | 次数 | 现状 |
|---|---|---|
| 实际发往上游的字节级 body | 4 | 数据在手，未保存 |
| 该次请求的服务端完成记录 | 3 | 有雏形，只写 stdout |
| 上游 SSE 帧**时序** | 3 | 完全无 |
| 上游错误响应体原文 | 2 | 只在日志 `detail` 留只言片语 |

**反向核对**——以下五类记了也没用，不要浪费字段：客户端到我方的重试次数与时序、Bun 运行时自身的空闲超时天花板、pts/tmux 回滚缓冲、上游内部决策逻辑、Claude Code 二进制内部的错误分类正则。这些只能靠客户端黑盒测试或反编译获得。

### 1.8 体积：r1 的数字口径是错的

来源报告的 3.6KB/请求是把**整个请求的帧字节串整体做一次 zstd-3**。r1 却提议逐帧独立压缩，二者不能划等号。实测对照：

| 样本 | 整请求 zstd-3 | 逐帧 zstd-3 | 倍数 |
|---|---:|---:|---:|
| `anthropic_to_responses_stream` 模型响应 | 17,085 B | 19,764 B | 1.16× |
| `responses_web_search_stream` 模型响应 | 7,373 B | 10,985 B | 1.49× |

结论：**按请求（或按 attempt）把原始 chunks 合成一个压缩 blob，另存每个 chunk 的长度与到达时刻**，既省空间又保边界与时序。容量应按实际压缩后字节统计，不是原始字节。

### 1.9 cassette 的完整合同

`Interaction` 必需字段：method、path、authenticated、extensions、source、request_shape、status、headers、chunks。`request_shape` 只保留 model、stream 与规范化 body 的 sha256（**但对非 JSON/非对象 body 返回空字典**，所以「只存 sha256」不是每个 Interaction 的强制不变量）。响应头 allowlist 恰为 `content-type`、`transfer-encoding`、`cache-control` 三项。

r1 的 L2+L3 **不足以**无推断地导出完整 cassette，缺四样：上游 request 的 method 与 path（`trace.path` 是客户端入站路径，不是上游路径）、`response.extensions`（特别是 `http_version`，L1 只有压缩过的 H1/H2 显示标签）、真实 chunks、**attempt 身份**（一次客户端请求可有多次上游交换，`(entry_id, sequence)` 没有 attempt 维度）。

`from_history.py` 之所以能产出可读 cassette，是因为它人为填入 POST、调用者提供的 path、200、`content-type`、HTTP/1.1。**那是对旧历史固件的公开证据降级，不应成为新取证系统凭空补事实的模式。**

另需注意：完整 `recorded_chain` cassette 往往还含 token exchange / models interaction（当前 `anthropic_to_responses_stream.json` 有 3 个 interactions）。`export-cassette` 不能同时承诺「单交互 delivery fixture」和「完整 provider cassette」两种语义而不说明范围。

### 1.10 用户亲笔文档说了什么

`docs/.human-controlled/MAIN.md` 的「运维与调试端点」一节把 **`/history/api/*`、`/history/ws` 列为产品端点**，且**没有**像同文件对 Responses WebSocket 那样标注「已裁决 暂不支持」。

`config.example.yaml` 里 `history: enabled: true`，并预留了六个钩子点：`on_client_request_parsed`、`on_upstream_request_ready`、`on_upstream_sse_block_ready`、`on_client_sse_block_ready`、`on_upstream_request_closed`、`on_client_request_closed`。

**这两样都不是我能替你论证掉的。** r1 引用我自己推导的 `history-system.md` 去否定 REST/WS，属于拿二手材料压人写权威，已改正。

### 1.11 消费面：既有形态与裁决后的去向

`ghc-api-proxy debug <子命令>` 已立，`debug models` 刚实现且带 `--json`，`debug info` / `debug usage` 仍是 `_not_implemented` 占位。

`src/app/debug/__init__.py` 定了这个包的性质：回答「an operator asks while something is wrong」，且「built to run against the same wiring the server uses rather than against a server that may not be up」。

**但用户已裁决查询面走 HTTP、不做 CLI（见 4.3）**，所以本节记录的是既有形态，不是本方案的交付面。有一条取向仍然成立并转移到 HTTP 面上：**本项目的调研主要是派 subagent 做的**，所以查询响应必须是机器可读的结构化 JSON，这一点不因载体从 CLI 换成 HTTP 而改变。

同样的取向也支撑了分叉 E 的方向——日志本身结构化，subagent 才读得动。

---

## 二、前置条件（不解决就白做）

### 2.1 测试正在往用户真实数据目录写库

`~/.local/share/ghc-api-proxy/history.db` 的 8,630 行全是测试流量，且**此刻仍在增长**。

r1 把它判为「不在本方案范围内」，**这是错的**：新 recorder 若共用同一个数据库文件，测试噪音会把真实取证记录挤出成功桶（按 r1 提的 N=50，几轮测试就能冲干净）。这是前置条件，不是顺手清理。

两种解法：测试库改落 `tmp_path`；或取证库另用独立文件名。**建议两者都做**——前者是缺陷修复，后者是隔离。

### 2.2 L1 采集点需要先补成 exactly-once

见 1.4。非流式路径的异常退出必须进入同一个幂等终结器，否则「客户端中途断连」这类事故恰好不留记录——而那正是最需要记录的一类。

流式侧的 `_StreamAccounting.finish` 已经是正确范本，照它做即可。

---

## 三、设计

### 3.1 数据模型：request → attempt → chunks 三层

r1 的两层模型表达不了重试。实际形状：

```
ForensicRequest          一次客户端请求
  └─ UpstreamExchange    一次上游 attempt（可多次）
       └─ UpstreamChunk  该 attempt 收到的原始 chunk
```

| 表 | 关键列 | 服务于 |
|---|---|---|
| `ForensicRequest` | id、session_id、agent_id、**wall-clock started_at / ended_at**、method、path、inbound_format、两侧协议、requested_model、resolved_model、status_code、failed、detail、bytes_in、bytes_out、usage、stop_reason、tools、thinking、dialect、attempts、pinned | L1 |
| `UpstreamExchange` | request_id、**attempt_index**、上游 method、上游 path、authenticated、request_body、request_body_digest、status、**headers（完整，不裁剪）**、extensions、error_body、**started_at / ended_at** | L2 + cassette |
| `UpstreamChunk` | request_id、attempt_index、sequence、**arrived_at**、byte_length，chunk 字节合并存于 exchange 级的单个 zstd blob + offset 表 | L3 |

**时间戳是 L3 的取证依据，不是可选项。** 没有 `arrived_at`，「上游沉默 242 秒」这类问题记了也答不了——`sequence` 推不出时刻。这是 r1 最实的一处漏。

`session_id` / `agent_id` 必须进 L1，否则第四节的 `--session` 过滤器没有数据源（r1 承诺了过滤器却没给字段，是文档内部矛盾）。取自 `history/sessions.py` 已有的 `identify_session`。

> **响应头存完整的，不在取证表上套 allowlist。** 三项 allowlist 是 cassette 的产物合同，属于 3.6 的导出阶段。取证表若提前裁剪，会丢掉上游 request id 这类只在响应头里出现的取证事实——而那正是向上游报障时唯一能引用的凭据。这与 3.5 的立场一致：本地库不裁剪，导出才裁剪。（r2 在这两处自相矛盾，本版改正。）

### 3.2 采集点分工

| 采什么 | 在哪采 | 说明 |
|---|---|---|
| L1 最终完成记录 | 外层幂等 finalizer（非流式补洞后的 `_serve`，流式的 `_StreamAccounting.finish`） | 不能用 `app.pipeline.events` 的 `request.succeeded` 代替——它在拿到 response headers 后就发布，此时 stream 尚未被消费，terminal / usage / stop_reason / received bytes 都还不存在 |
| L2 每 attempt 的上行快照 | attempt 事件 / transport tap | `app.pipeline.events` 的 `attempt.*` 适合这一层 |
| L3 原始 chunk | `_counted_upstream`，不改字节地旁路 | 见 1.6 |

### 3.3 先写后分类

r1 的「失败全留 + 成功滚动窗口」有个致命缺陷：**失败何时可知**。stream 是否完整要到 `_StreamAccounting.finish` 才知道；进程 crash、请求永久挂起、磁盘写失败时，「完成后按结果决定留不留」会恰好丢掉最需要的记录。

改为：

1. 请求开始先写 provisional L1；
2. 每个 attempt 开始时写 request snapshot；
3. chunk 到达时写入**有界 spool（未压缩、带到达时刻）**；
4. attempt 结束时把 spool 收敛成 1.8 说的单个 zstd blob + offset/时刻表，删除 spool；
5. 请求结束后标终态；
6. 归档器只搬迁**已知成功且已过热区**的记录；失败与未终结按单独策略长留热区（见 3.4）。

**第 3、4 步是 1.8 与本节的接缝，必须一起看**：1.8 要的「按 attempt 合并压缩」只有在 attempt 结束时才做得到，而 crash 恰恰发生在结束之前。所以在途的 chunk 只能以未压缩形式落 spool——代价是在途请求占用未压缩体积，收益是进程被 kill 时那些字节还在。二者不可兼得，本方案选保住证据。

> 未终结记录本身是一条线索，**但因果要说准**：它只说明「这条请求没有走到终结点」。可能是进程死了，也可能是请求永久挂起，还可能是终结写入本身失败了。三者的排查方向不同，记录不能替读者做这个判断。（r2 写成「说明进程在那一刻死了」，因果过强。）

### 3.4 容量、归档与会话聚合

用户裁决是**全量记录 + 按会话聚合 + 定期归档化**，不是淘汰式 reaper。这改变了本节的整个形状：

- **不删，归档。** 记录到期后转入归档批次而非 `DELETE`。这与旧服务「产品面不提供删除端点」的既有决策同向，但更进一步——连内部淘汰也改为搬迁。`history-system.md` 曾把分层归档整体列入 BACKLOG，此裁决把它提回主线。
- **会话是一等实体。** 归档按会话成批，而不是按行数截断。理由是取证的自然单位是一次会话：翻一个事故时要看的是那段对话的前后文，按行数切会把一次会话劈成两半。`SessionSummary` 在 `history-system.md` 已有设计，`history/sessions.py` 的 `identify_session` 已有实现。
- **热区仍需要一个上限**，否则「全量」在长期运行下会让热库无限膨胀、拖慢查询——而查询性能是用户点名的硬约束（4.1）。上限触发的动作是归档，不是删除。按**实际压缩后字节数**统计，不是原始字节。
- **归档的物理形态待定**：同库的冷表、独立的按日期分片库文件、还是压缩包。倾向独立文件——它让热库始终小、查询始终快，且归档批次可以整体移走或离线分析。这一项列入 4.6 待你示下。
- **回收/搬迁必须显式**：现有 reaper 只 `DELETE FROM entries`，且 `writer._open` **没有设 `PRAGMA foreign_keys=ON`**，外键 cascade 当前不工作。子表要在同一 writer 事务里按 request/attempt 显式处理。
- `pin` 的语义从「免于淘汰」变为**「免于归档」**——钉住一条正在排查的记录，让它留在热区可查。旧 `set_pinned` 只操作旧 `entries`，用不上；新表的 `pinned` 需要自己的写入途径，即 `POST /history/api/entries/pin`（原方案给的是 CLI 动词，按裁决改为 HTTP）。

> 附带发现（非本方案范围，记一笔）：`writer._open` 设的是 `busy_timeout=0`，而 `docs/2604-rewrite/history-system.md` 的设计明写 `busy_timeout = 5000`。实现与设计文档对不上。

### 3.5 脱敏立场

**取证库本身不脱敏。** 它落在本机用户自己的数据目录，完整记录含临时 token 不构成本项目认定的敏感面。只有 `export-cassette` 那一步才走脱敏（按字段名递归 + 响应头 allowlist），因为 cassette 要进版本库。

这是我按既有立场**推定**的，不是你裁决过的，列在这里供你否决。

### 3.6 cassette codec 要提升为共享模块

导出端点若直接用 `tests/integration/recorded/cassettes.py`，会让生产代码 `import tests.*`。正解是把 codec 与 scrubber 提升为可安装的共享模块，测试与 `POST /history/api/entries/export-cassette` 同时依赖它。导出只做 scrub / encode 已记录的真实字段，**不补猜测值**。

---

## 四、已裁决（2026-08-20）

用户于 2026-08-20 就第四节原八个分叉作出裁决。**其中三项推翻了我的推荐，且都推翻得有道理。** 原分叉表已被下表取代；原文档的分叉版本见 git 历史。

| 分叉 | 裁决 | 与我的推荐 |
|---|---|---|
| A 取证深度 | **A1：L1 + L2 + L3 全做** | 一致 |
| B L3 形态 | **B1：raw parser-input chunks + 到达时刻** | 一致（未单独裁决，按推荐执行；见 4.5） |
| C 持久化保证 | **C1：L1 durable，L2/L3 bounded best-effort** | 一致（未单独裁决，按推荐执行；见 4.5） |
| D 查询面 | **完整 HTTP 支持；不要 CLI；非 RESTful，用 `POST /path/to/resource/action`** | **推翻**。我倾向只做 CLI |
| E 日志 | **做，且方向改为：标准日志结构化，TUI 从结构化日志解析** | **推翻分层**。我原方案是给 TUI 的 `activate()` 打补丁 |
| F cassette 派生 | **做** | 一致 |
| G 保留档位 | **全量 + 按会话聚合 + 定期归档化** | **推翻**。我推荐的是滚动窗口淘汰式 reaper |
| H replay | **做** | 一致 |

### 4.1 用户点名的硬约束：查询不得拖慢请求处理

> 「在 copilot-api-js 上，曾经因为设计问题导致 history 查询拖慢请求处理，我们能在避免这个的基础上实现完整的 HTTP 支持吗」

这是本次唯一一条用户亲自点名的危害，因此它是设计约束而不是一般性能考量。旧服务的成因在 `history-system.md` 已有分析：同步 `bun:sqlite` 落在请求路径上。但**查询侧**还有几条独立的失效路径，必须逐条堵住：

| 失效路径 | 对策 |
|---|---|
| 查询与写入争同一个连接 | 读写连接分离。查询用独立的 `mode=ro` 只读连接，写入仍是单 writer 独占。WAL 下读不阻塞写、写不阻塞读 |
| 查询在事件循环上跑 | 查询一律 `asyncio.to_thread`，慢查询只占线程池 worker，不停住事件循环 |
| 查询与请求处理抢同一个线程池 | 历史读用**独立的小线程池**，容量单独设定。否则一次大查询会饿死请求路径的线程 |
| 列表查询顺手解压大字段 | 列表只走索引列，**绝不触碰 blob**。解压只发生在单条详情与导出 |
| 查询卡住 writer 队列 | 现有 `reap()` 用的是 `await self._queue.join()`——那是写路径的同步模式。**读路径一条都不许进 writer 队列** |
| 无界查询 | 强制 limit，按索引列过滤，无全表扫描 |

这几条落地后应有一个能证伪的检验：在持续请求负载下反复打列表与详情查询，请求侧的 p99 不出现可归因于查询的抬升。**这是一个检验，不是一道门**——它用来发现问题，不用来阻断交付。

### 4.2 HTTP 面的形态

`MAIN.md` 已列 `/history/api/*` 与 `/history/ws`。按用户裁决用动作式而非 RESTful 写法：

```
POST /history/api/entries/list        列表（过滤、分页）
POST /history/api/entries/get         单条完整详情
POST /history/api/entries/pin         钉住，免于归档
POST /history/api/entries/unpin
POST /history/api/entries/replay      用记录的真实 outbound body 重放上游（分叉 H）
POST /history/api/entries/export-cassette   导出固件（分叉 F）
POST /history/api/sessions/list       会话聚合列表
POST /history/api/sessions/get        单会话详情
POST /history/api/archives/list       已归档批次
GET  /history/ws                      实时推送
```

一个需要注意的连带影响：这些端点当前只存在于旧链路，而旧链路的 `app.routes.*` **在新链路的边界禁区里**（`test_module_boundaries.py`）。所以要么在新链路下另建路由模块（不叫 `app.routes`），要么调整边界断言。**建议前者**——边界断言是有意为之的产品决策，为了少写一个模块名去动它不划算。

### 4.3 「不要 CLI」的影响

原方案的分片 1、2、3、5、7 都以 `debug history *` 作为交付面，现在全部改为 HTTP 端点。相应地：

- `debug history list/show/pin` 不做。
- `debug replay`、`export-cassette` 改为上表的 HTTP 动作端点。
- `debug info` / `debug usage` 那两个 `_not_implemented` 占位与本方案无关，保持原状。

我原先主张 CLI 的理由是「服务出事时可能已经不在，CLI 直读库更可靠」。**该理由已被用户裁决否决，记录在此，不再重提。** 若日后确实撞上「服务起不来但要查库」的场景，再单独提出。

### 4.4 结构化日志：E 的分层被改对了

我原方案是改造 `tui.py` 的 `activate()`，让它保留非控制台 handler。用户给的方向不同：**标准日志本身应当是结构化的，TUI 从结构化日志中解析。**

这个分层更好，理由不止一条：

- 我原来的做法是在错误的层面打补丁。TUI 之所以要抢占 root handler，是因为它既是渲染器又是 handler；把它改成结构化流的**消费者**，抢占这件事根本不会发生。
- 结构化日志天然可被机器读——而本项目的调研主要靠派 subagent 做，这一点比人读格式重要。
- 文件 sink 不再是「另加一个 handler 并祈祷没人替换它」，而是同一份结构化流的一个落点。

需要注意的是本项目已在用 structlog（处理器链渲染了固定宽度的状态前缀），所以这不是从零引入，而是**把渲染与承载分开**：结构化记录是权威，终端呈现与文件落盘都是它的下游。

这项改动比我原估的 1.5 片大，且触及可观测性的架构分层。它也**必须有人眼验收**——终端呈现改动的验收标准是人看着对不对，测试替代不了。

### 4.5 未单独裁决、按推荐执行的两项

分叉 B 与 C 未被单独问及，按 r3 的推荐执行。若与你的意图不符，请指出：

- **B1**：L3 记 raw parser-input chunks（而非解析后的 `SseEvent`）。理由是 `SseEvent` 有损——`errors="replace"` 解码、丢注释帧与保活帧、重接 data 行，无法还原原始字节与 chunk 边界。
- **C1**：L1 durable（背压、不丢），L2/L3 bounded best-effort（队列满即丢并计数）。L1 是「哪条请求出事了」的唯一答案来源，不该丢；L2/L3 丢一条可接受。

### 4.6 仍需你示下的三个小项

- **`ProxyConfig.history` 那个死开关**：接上（让 `history.enabled` 真正控制记录子系统）／保持现状但启动时明说无效／删除。接上意味着**默认就开始记录**（`config.example.yaml` 里是 `true`）。鉴于你已裁决全量记录，我倾向接上。
- **配置键放哪**：归档与会话聚合的配置进 `history.*`，还是另立一段？`history-system.md` 已 spec 了 `success_limit` / `failure_limit` / `reaper_interval` / `db_path` / `websocket` 五个键，而 `HistoryConfig` 只有 `enabled`。注意你裁的是归档不是淘汰，所以 `success_limit` / `failure_limit` 这两个键的语义需要重定。
- **旧链路 history 的去留**：我建议本次完全不动。`protocol_history.py` 的重复实现是在一条不服务生产的链路上做整洁性重构，ROI 低；判定它无用并移除则触及「不得擅自删除已实现的功能」，不是我该判的。

---

## 五、不采纳，及理由

- **记 L4 下行交付块**。取证盘点零次点名。但 r1 说的「对照 L3 就能推出来」**理由过强**，已收窄为：L3 到下行块之间还隔着 buffering、header synthesis、ping、terminal synthesis，且受当时代码版本与配置影响；客户端提前断开时更不能由上游帧推出。正确说法是「可在固定代码/配置下重放预期转换，不能冒充实际交付证据」。
- **复制 `copilot-api-js` 的内容寻址 manifest/handle 结构**。为跨请求去重设计，与单请求直接关联、无去重目标的前提不匹配。
- **记 1.7 反向核对里那五类事实**。只能靠客户端黑盒测试或反编译获得，服务端补记录覆盖不到。

### 六个钩子点：从「不采纳」降为「待办，非本次」

r1 把它们归入「不采纳」，理由是平面不存在。这个核查是对的（六个键只定义于 `config/schema.py`，全仓零消费者；当前真实注册表用的是 `direct_driver/base.py` 的 `attempt.*` / `request.*` 内部事件）。

但**它们在你亲笔的 `config.example.yaml` 里**，且本方案无论如何都要在 `on_upstream_request_ready` 与 `on_upstream_sse_block_ready` 这两个语义位置开接缝。所以正确定位是「本次不实现，但实现取证采集点时按它们的语义留好位置，日后接钩子分发不用重开刀」，而不是「不采纳」。

### 看到了但本次不做的另外两种解读

「增强调研能力」还有两种合理解读，评审点出后记在这里，免得它们变成静默裁掉的需求：

- **TUI 历史回看面板**。现在的 footer 只显示在途请求，翻不了历史。裁决把 TUI 改成结构化日志流的消费者（4.4）之后，这件事反而更顺——面板与 footer 都是同一份流的呈现。但它仍是独立的界面工作，验收方式不同，建议等分片 2 落定后单独立项。
- **按 `message.id` 关联客户端与服务端两侧记录**。项目记忆里已经写过「Claude Code 把一轮 assistant 按内容块拆成多条记录，靠 `message.id` 归组」。如果 L1 记下我方生成的 message id，取证时就能把客户端 transcript 与服务端记录直接对上，而不是靠时间戳猜。**这一条成本极低**（L1 加一列），但需要确认该 id 在我方是否稳定可得，本次未核实，故不写进分片表。

---

## 六、实施顺序与约束

### 6.1 分片

排序原则：**每片交付后必须有人能用它回答一个真实问题**。r2 曾声称每片自足又说「1+2 之后才是第一个有用的里程碑」，自相矛盾；本表按裁决后的形态重排。

| # | 内容 | 交付后能回答 | 触及并行编辑区 |
|---|---|---|---|
| 0 | 前置：测试库改落 `tmp_path`；取证库独立文件名；`_serve` 异常退出补进幂等终结器 | —（不解决则记录不完整且被噪音污染） | **是**（`pipeline_app.py`） |
| 1 | 结构化日志：把渲染与承载分开，文件落点接上（分叉 E 的第一半） | 「昨天那条 400 的完整上下文」——终端滚掉也还在 | 是（`observability/*`） |
| 2 | TUI 改为结构化流的消费者（分叉 E 的第二半），人眼验收 | 同上，且 TUI 不再抢占 handler | 是（`observability/tui.py`） |
| 3 | L1 落盘 + **热区上限同片交付** + 新链路路由模块 + `POST /history/api/entries/list`、`/get` | 「哪条请求出事、哪个模型、几次 attempt、是不是客户端断的」 | 是（`pipeline_app.py`） |
| 4 | L2：扩展 driver/transport 观测合同，每 attempt 上行快照 | 「我们到底发了什么给上游、上游错误原话是什么」——盘点第一大缺口 | 是 |
| 5 | `POST /history/api/entries/replay`（分叉 H） | 「上游对这个 body 现在还怎么反应」——替代手写 curl 探针 | 否 |
| 6 | L3：raw chunks + 到达时刻 + spool 收敛 | 「上游什么时候回的、中间停了多久」 | 是（`pipeline_app.py`） |
| 7 | 会话聚合 + 归档机制 + `/sessions/*`、`/archives/*` 端点 | 「那次会话整体发生了什么」；长期运行容量可控 | 否 |
| 8 | `export-cassette` + codec 提升为共享模块（分叉 F） | 从生产流量派生测试固件 | 否 |
| 9 | `/history/ws` 实时推送、`pin`/`unpin`、配置键 | 实时观察；钉住正在排查的记录 | 否 |

**热区上限与首次持久化同片（分片 3）。** r2 把容量排在最后，意味着中间存在「默认写盘、无任何上限」的集成态，不可接受。注意上限触发的动作是归档（3.4），完整归档机制在分片 7，所以分片 3 的上限可以先用最简形态（超限即停写并告警，或先落一个简单冷表），分片 7 再换成正式归档。**这个临时形态必须在分片 3 的说明里写明是临时的**，否则它会活下来。

> 分片 0 本身不产出可用能力，它是让后续记录**可信**的前提：不补 exactly-once，记录会在最该有的时候缺失；不隔离数据库，真记录会被测试噪音挤掉。分片 1 之后才第一次有人能查到东西。

### 6.2 并行会话约束

**本节 r3 版本有两处错误，本版改正**：它写着「分片 1（日志 sink）几乎不碰这些文件」，一是沿用了 r2 的旧分片编号，二是这个判断本身就错——按任何编号，改 `_serve` 与 `_StreamAccounting` 的那些分片碰的正是并行会话在编辑的核心函数。

当前工作树中，并行会话正在编辑 `src/app/server/pipeline_app.py`、`src/app/observability/request_log.py`、`src/app/pipeline/delivery/assembler.py`、`sse_source.py`、`stream.py`。本方案要动的 `_serve`、`_StreamAccounting`、`_counted_upstream` 全部在第一个文件里。

上表的「触及并行编辑区」一列给出了真实情况：**十片里有六片碰**，包括最早的分片 0。所以「先做不冲突的分片」这条路基本不存在。

这不构成缩小范围的理由，但决定了动手方式：

1. **进独立 worktree 实施**，合入时对齐。这是本方案的默认做法，不是例外。
2. 分片 5、7、8、9 不碰共享文件，可以随时并行推进。
3. 若并行会话在短期内落定，直接在主工作树做会更省事——这一点动手前先看 `git status`，不要按本文档写作时的快照假定。

### 6.3 需要 Spec 吗

项目纪律要求「改变可观察行为前需要完整行为 Spec」。本方案改变可观察行为的部分：新增磁盘写入（结构化日志文件、取证数据库、归档批次三处）、新增 HTTP 端点、默认开启记录、改动终端呈现的分层。

界线：

- **分片 0 不需要 Spec**。测试库改落 `tmp_path` 是缺陷修复；补 exactly-once 是让既有 docstring 承诺的行为真正成立，不是新行为。
- **分片 1 起需要 Spec**，把第三节扩写为行为 Spec 并冻结。分片 1 是第一个新增磁盘写入的，界线划在这里。
- **分片 2 的 TUI 改造需要人眼验收**，不是 Spec 能替代的——终端呈现的验收标准是人看着对不对。
- **4.1 那条查询性能约束需要一个可证伪的检验**，但它是发现问题用的，不是阻断交付的门。

## 七、评审处置

五次评审共 55 条发现（r1 轮 32 条、r2 轮 19 条、r3 抽查 4 条），**全部采纳，无驳回**。r4 的变更来源是用户裁决而非评审。

### r3 → r4（用户裁决驱动）

| 裁决 | 落地 |
|---|---|
| 查询面走完整 HTTP、不要 CLI、动作式路径 | 4.2 端点表、4.3 影响说明、1.11 改写、3.6 去 CLI、第六节分片表全部改为 HTTP 交付面 |
| 查询不得拖慢请求处理（用户点名的唯一危害） | 新增 4.1，逐条列出六条失效路径与对策，并给一个可证伪的检验（明确它是检验不是门） |
| 全量 + 会话聚合 + 定期归档 | 3.4 整节重写：淘汰改归档、会话成为一等实体、`pin` 语义从「免于淘汰」改为「免于归档」；3.3 第 6 步同步改写；分片 7 承接 |
| 标准日志结构化，TUI 从中解析 | 4.4 记录该分层比我原方案好在哪；分叉 E 从「给 `activate()` 打补丁」改为「渲染与承载分离」，拆成分片 1、2 |
| A1 / F / H | 分片 3–6、8 承接 |

### r3 抽查

| 发现 | 处置 |
|---|---|
| **§6.2 硬矛盾**：沿用 r2 旧分片编号，且「几乎不碰共享文件」的判断本身就错 | 6.2 重写，并在分片表新增「触及并行编辑区」一列，如实标出十片里有六片碰 |
| §1.3 说得太绝对：`RequestContext.attempts` 已记每 attempt 的 payload/状态码/错误串 | 1.3 改写为一张「还差哪六样、每样为什么不能用现有的替代」的表 |
| §3.1/§3.5 headers 分层、§6.1 容量边界、§4 TUI 合同、§6.3 Spec 顺序 | 四项经源码核实准确一致，无需修改 |

### r2 轮

| 发现 | 处置 |
|---|---|
| **范围 blocker N1** TUI 整体替换 root handler，日志 sink 在交互终端下失效 | 分叉 E 重写、粗估上调、撤销「若只批一件事批这个」。r4 又被用户裁决进一步改对了分层 |
| 事实 major 1 「L2 数据已在接缝中」失真 | 1.3 改写（r4 再次细化） |
| 事实 major 2 取证表套 allowlist 与 3.5 矛盾 | 3.1 改为「headers（完整，不裁剪）」并说明理由 |
| 事实 major 3 容量上限排在最后 | 6.1 移入首次持久化同片（r4 分片 3） |
| 事实 major 4 Spec 顺序自相矛盾 | 6.3 重写 |
| 事实 major 5 E1 粗估偏低 | 列出六项未计入内容（r4 后该项进一步扩大为两片） |
| 事实 M1 残留：spool 与单 blob 未闭合 | 3.3 补第 3、4 步与取舍说明 |
| 事实 M1 残留：「未终结＝进程死了」因果过强 | 3.3 改为三种可能 |
| 事实 minor raw chunk ≠ `on_upstream_sse_block_ready` | 1.6 末补注 |
| 事实 minor / 范围 N2 `pinned` 无写入途径 | 3.4 补写入途径（r4 改为 HTTP 端点） |
| 范围 major N3 分叉 D 缺中间选项、D3 负担高估 | 补 D2 与候选稿说明（r4 已被裁决取代） |
| 范围 「默认记多少」失去裁决位置 | 还原为分叉 G（r4 已裁决为全量+归档） |
| 范围 新解读 `debug replay` | 新增分叉 H（r4 裁决为做，改为 HTTP 端点） |
| 范围 漏 TUI 历史面板、`message.id` join key | 第五节新增「看到了但本次不做的另外两种解读」 |
| 范围 分片 0/1 价值表述过强 | 6.1 末补注 |

### r1 轮

| 发现 | 处置 |
|---|---|
| 事实 B1 「只有两类测试调用旧链路」是错的全称断言 | 1.1 改为「例如」并补全五处 |
| 事实 B2 `_log_completion` 非 exactly-once | 新增 1.4 与前置条件 2.2；L1 采集点改为幂等 finalizer |
| 事实 B3 `SseEvent` 不能保真 | 1.6 改为记 raw chunks；新增分叉 B |
| 事实 B4 复用 `HistoryEntry` 不便宜 | 新增 1.5；3.1 改为新 DTO 新表 |
| 事实 B5 L2+L3 不足以导出 cassette | 1.9 列出缺失四项；3.1 补 attempt 维度与上游 method/path/extensions |
| 事实 B6 压缩口径错 | 1.8 改为按 attempt 合并压缩 + offset 表 |
| 事实 M1 失败何时可知 | 3.3 改为「先写后分类」 |
| 事实 M2 reaper 孤儿 | 3.4 显式处理 + 指出 FK 未启用 |
| 事实 M3 内部事件不能代替完成点 | 3.2 采集点分工表 |
| 事实 M4 缺两个真分叉 | 新增分叉 B、C |
| 事实 M5 「L3 可推出 L4」理由过强 | 第五节收窄表述 |
| 事实 m1 数据库计数是可变快照 | 1.1 加时间锚点 |
| **范围 blocker 1** 未引用人写权威 | 新增 1.10；分叉 D 交还用户裁决——**该交还直接导致了 r4 的裁决把我的推荐推翻，这是本轮评审价值最高的一条** |
| **范围 blocker 2** 帧表无时间戳 | 3.1 加 `arrived_at` |
| 范围 M 分叉 A 捆绑 cassette | 拆出分叉 F |
| 范围 M L1 缺 session/agent/墙钟 | 3.1 补齐 |
| 范围 M 日志 sink 缺席 | 新增分叉 E |
| 范围 M 测试写真实数据目录 | 改为前置条件 2.1 |
| 范围 M 钩子点定位错误 | 第五节降为「待办，非本次」 |
| 范围 M 无工作量量级 | 第四节各分叉给粗估 |
| 范围 M 分片不自足 | 6.1 按「交付后能回答什么」重排 |

### 评审明确肯定、历经四版保留的

1.7 的反向核对（防住「补记录就能覆盖所有缺口」）；1.6 的硬纪律（防住未来重构在 assembler 之后再记一份）；3.3 的「先写后分类」（范围评审称这是它和 r1 都没看见的时序问题）；3.5 主动声明脱敏立场是推定而非裁决、且未给取证库加任何多余保护；拒绝钩子点前先核查平面是否存在；全程未搭建不成比例的证明基础设施。
