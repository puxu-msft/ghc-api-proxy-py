# 评审：`server-layout/README.md` 的目标布局设计

**日期**：2026-08-22。**评审对象**：`.dev/docs/server-layout/README.md`，`.dev` 提交 `58663b5`。**主仓工作树**：`main` = `1459320`（工作树脏，见 F14）。
**评审范围**：**只评设计**——第 5 节目标布局的每处落点、第 7 节对比、第 8 节顺序、与 `architecture.md` 及 `docs/.human-controlled/` 的抵触、共享树落地风险。
**不评**：数字是否属实、引用是否可达、行数统计是否准确——那是另一位事实核查评审者的范围，本文一律**假定原文事实为真**，除非我自己重新测过并在文中标注。

**结论（判断权重：可据以行动）**：方案 1 的**方向正确**，第 4 节五处怪味的诊断我全部认可，S3、S4 尤其站得住。但第 5 节的**六个落点里有两个是错的、三个切得过细、一个漏了 8 个符号**，而且这些错误有**同一个根因**：目标布局在搬文件，却没有动那些函数的**参数**——`Chain` 仍然作为参数穿过每一条新划的包边界，于是每一次搬迁都把组装根拖进了一个叶子。第 8 节的顺序另有一处实质缺陷：最贵的那件事被挂在唯一一道用户裁决后面。

---

## 严重度计数

| 级别 | 数量 | 编号 |
|---|---|---|
| blocker | 2 | F1、F2 |
| major | 6 | F3–F8 |
| minor | 8 | F9–F16 |
| nit | 2 | F17、F18 |

---

## 我自己测过的部分（这些结论不依赖原文）

用 AST 建了 `src/` 的模块级 import 图，并**补上了隐式的祖先包边**（`import a.b.c` 会先执行 `a/b/__init__.py`，这一条是本次两个 blocker 的关键，原提案没有考虑）。做了正样本对照：`app.server.pipeline_app` 可达 `app.pipeline.delivery` 为真，`app.config.schema` 可达为假——探针能区分。

得到的三条事实：

1. `app.pipeline.request` → `app.pipeline.delivery.assembling`（`RequestContext.reply: Terminal`）。因此 **`app/pipeline/delivery/` 在图上位于 `RequestContext` 与 `Route` 之下**，是一个叶子包。
2. `app.server.composition`（即目标里的 `app.composition`）可达 `app.pipeline.delivery` 包初始化，路径为 `app.composition → app.pipeline.translation_driver.registry → app.pipeline.request → app.pipeline.delivery.assembling → app.pipeline.delivery`。
3. `app.server.composition` 同样可达 `app.observability` 包初始化，路径为 `app.composition → app.observability.terminal → app.observability`。

另外用 `git log --since=2026-08-20` 测了同伴改动密度，见 F14。

---

## F1（blocker）`pipeline/delivery/selection.py` 把一条已存在且承重的分层倒过来了

**这条缝不是真缝。**

`framer_for`、`assembler_for`、`dialect_for`、`delivers_blocks`、`stream_settings`、`delivery_buffer`、`stream_idle_seconds` 这七个函数的输入是 `HandledRequest`（内含 `Route`）与 `Chain`。而上面测到：`app/pipeline/delivery/` 在图上位于 `RequestContext`／`Route` **之下**。把这七个函数放进 `delivery/`，等于让一个叶子包去 import 它上面两层的 `Route` 和最上面的组装根 `Chain`。

这不是抽象的洁癖问题，它会**具体地炸**。一旦 `app/pipeline/delivery/__init__.py` 像它对 `assembling`、`blocks`、`framing`、`sse_frame`、`sse_source`、`formats.*` 那样再导出一次 `selection`，就得到：

```
app.composition
  → app.pipeline.translation_driver.registry
  → app.pipeline.request
  → app.pipeline.delivery.assembling
  → app.pipeline.delivery            （包初始化）
  → app.pipeline.delivery.selection
  → app.composition                  （此时 app.composition 尚在执行第 25 行，Chain 未定义）
```

即 `ImportError: cannot import name 'Chain'`。换成 `from app.pipeline.routing import Route` 也一样成立——`app.pipeline.routing` 同样可达 `app.pipeline.delivery`。

也就是说，这个落点要求 `delivery/__init__.py` 从此**必须记得不要再导出 selection**，而这条规则没有任何地方写下来。这个仓库里恰好有两份 `__init__.py`（`app/pipeline/__init__.py`、`app/server/__init__.py`）的存在理由就是同一类事故，两份都用长篇 docstring 说明「这里为什么必须空着」。再制造第三个同形陷阱，与本提案第 4 节 S3 的论证自相矛盾。

**替代方案（可直接采纳）**：不要搬进 `delivery/`，先**收窄参数**再决定落点。

```python
# app/pipeline/delivery_selection.py  —— pipeline 包根，不是 delivery/ 子包
def framer_for(route: Route, *, synthesized: bool, message_id: str, model: str, signature_compat: ContentBlockStartCompat) -> OutboundFramer | None: ...
def assembler_for(route: Route, *, synthesized: bool, hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"})) -> BlockAssembler: ...
def dialect_for(route: Route, *, synthesized: bool) -> ReplyDialect: ...
def delivers_blocks(route: Route, *, synthesized: bool) -> bool: ...
def stream_settings(delivery: ClientDeliveryConfig) -> StreamSettings: ...
def delivery_buffer(delivery: ClientDeliveryConfig) -> BlockBuffer: ...
def stream_idle_seconds(timeouts: UpstreamRequestTimeouts) -> int: ...
```

收窄之后这七个函数只依赖 `app.config.schema`（实测闭包 9 个模块，不可达 delivery）与 `app.pipeline.routing`，`Chain` 与 `HandledRequest` 都不再出现在签名里，落在 `app/pipeline/` 根下不产生任何环，也不需要任何「别导出我」的口头约定。

在第 5 节的树里，把

```
      delivery/selection.py       ← 自 server/handler.py：framer_for、assembler_for、...
```

替换为

```
      delivery_selection.py       ← 自 server/handler.py：framer_for、assembler_for、dialect_for、delivers_blocks、stream_settings、delivery_buffer、stream_idle_seconds
                                     参数由 Chain/HandledRequest 收窄为 Route + 对应 config 段；`delivery/` 是 RequestContext 之下的叶子包，选型在它之上，不能放进去
```

---

## F2（blocker）可观测性三块里，有一块搬进 `app/observability/` 会违反一条已被用户接受的架构边界

第 5 节把 `_StreamAccounting`、`_AccountedStreamingResponse`、`_counted_upstream`、`_tracked_delivery` 整体判给 `observability/wire_accounting.py`。前两个不是可观测性代码。

`_AccountedStreamingResponse.__call__` 做的事是：在框架之外套一层 `finally`，`await self._content.aclose()` 关闭交付生成器，把 close failure 与 primary exception 按机械优先级排序，再调用 `finish()`。它自己的注释写得很清楚：「Closing the body is this response's job and nobody else's」。

`architecture.md` 的两句：

- 「每个 exchange 有唯一 close owner。Driver 在 success、retry、parse error、buffer failure、client cancel 与 shutdown 路径都退出 async context；**converter 和 observer 不关闭 transport**。」
- 「**Downstream sink 是唯一 body writer**，串行接收完整 bytes batch。」

把 close owner 搬进 `app/observability/`，就是把 transport 的关闭责任放进 observer 包。这直接撞上第二句的后半。**这条比 S4 更严重**：S4 是「生命周期今天在错误的层」，而这一步是主动把它挪到一个被文档点名不能持有它的层。

`_StreamAccounting.finish()` 里还有一行 `self.context.reply = terminal`——写领域状态。按 `architecture.md` 的所有权表，`TerminalFacts` 由 driver finalize，不由 observer 写。

顺带一个次生代价：`app/observability/` 今天不 import 任何 web 框架（实测其外部依赖只有 `app.config.schema`、`app.pipeline.delivery.assembling`、`app.pipeline.delivery.blocks`、`app.pipeline.delivery.sse_source`）。`_AccountedStreamingResponse` 继承 `starlette.responses.StreamingResponse`，搬过去会让 observability 包依赖 ASGI 响应类型。这正是任务里问的「观测代码要反向 import 请求内部结构」的最坏形态——反向 import 的不是 request 结构（那个先例已存在，见 F3），而是**框架的响应对象**。

**替代方案（可直接采纳）**：把这块按「谁拥有」而不是「谁在记账」切开。

```
app/observability/
    request_trace.py        ← _Trace、_log_completion、_translation_losses、连接快照五件套、_counted_upstream
                               全是「读事实、填字段、写一行」，没有任何一处拥有生命周期
app/server/
    accounting.py           ← _StreamAccounting、_AccountedStreamingResponse、_tracked_delivery
                               这三个拥有的是 response body 的关闭顺序与 finish 的幂等，属于表面的交付所有权，
                               不属于 observer。它们只调用 request_trace 里的发射函数。
```

`_counted_upstream` 判给 observability 是对的：它是 `AsyncIterator[bytes]` 的透传计数器，不拥有关闭，也不写领域状态，只写 `_Trace` 与 `active_requests`。

---

## F3（major）`_Trace` 与 `RequestLine` 分成两个文件，会把一份 33 字段的机械抄写钉在模块边界上

`_log_completion` 的主体是把 `_Trace` 的字段一个一个抄进 `RequestLine`，我数了 33 个。`RequestLine` 在 `app/observability/request_log.py`。提案把 `_Trace` 放进**新建的** `observability/request_trace.py`。

搬完之后，「同一件事的两个记录」仍然是两份，只是从「同一个包的两个文件」变成「同一个包的两个文件」——收益为零，而抄写现在跨了一次 import。项目记忆里有一条「展示层读聚合记录，不读原始对象」，`RequestLine` 就是那个聚合记录；`_Trace` 是它的可变构造期形态。这两个应该**贴在一起**，让新增一个字段时漏抄的概率降到最低。

**替代方案**：`_Trace` 与 `_log_completion` 落在 `app/observability/request_log.py`（`RequestLine` 已在那里），不新建 `request_trace.py`。若嫌 `request_log.py` 已 36 KB，则新建的文件里放 `RequestLine` **和** `_Trace` 两个，把 `format_*` 留在 `request_log.py`——按「记录 vs 渲染」切，而不是按「谁写的」切。

顺便：`_Trace` 与 `RequestLine` 高度重合这件事本身值得在第 10 节登记为一处怪味（**能不能直接让 `_Trace` 消失、由调用方逐步填一个可变的 `RequestLine`**），但不必在本次做。

---

## F4（major）`model_provider/transport.py` 这个名字三重撞车，而且归属判错了

三重撞车：

1. `src/app/model_provider/ghc_client/transport.py` **已经存在**（43 行，上游 pre-header 传输错误分类）。同一个包树下两个 `transport.py`。
2. `architecture.md` 里 `transport` 是一个**被定义过的词**：「`/v1/messages`、`/responses` 是 protocol legs；HTTP SSE、HTTP JSON 与 WebSocket 是 physical transports」，并有 `ResponsesTransport` port。httpx client 工厂不是那个东西。
3. 还有第三个 HTTP client 工厂：`src/app/upstream/client.py:create_http_client`（旧链，吃 `AppSettings`）。

这恰好是本提案第 4 节 S5 自己立的规矩——「同一个词在一个代码库里只能指一件事」——而这一步在制造第三个 `transport`。

归属也判错了。`TransportOptions`、`transport_options`、`build_http_client`、`_keepalive_socket_options`、`_effective_proxies` 这一组的输入是 `ProxyConfig`，输出是 `httpx2.AsyncClient`，**完全与模型提供方无关**：代理、SOCKS、keepalive socket options、http2、stream cap。它的消费者是 `cli.py`、`debug/models.py`、`build_chain`——三个都是组装侧，没有一个在 `model_provider` 里。把它放进 `model_provider/` 是在宣称「httpx 客户端是模型提供方抽象的一部分」，而代码不这么说。

**替代方案**：跟着组装根走，不要跨包。见 F5 的目录形状。

---

## F5（major）`composition.py` 的正确切法是「记录 vs 建造者」，不是「对象图 vs 传输」

提案把 576 行切成 `app/composition.py`（对象图）+ `model_provider/transport.py`（HTTP 客户端）。这一刀切在了错误的维度上。

真正让后面每一步变难的，是 `Chain` 这个**记录类型**和 `build_chain` 这个**建造者**住在同一个模块里。`Chain` 被 `handler.py`、`ops_routes.py`、`pipeline_app.py` 当类型用；`build_chain` 只被 `cli.py`、`debug/models.py` 和测试用。而 `build_chain` 所在的模块 import 了 24 个 `app.pipeline.*` 模块（实测）。于是任何 `app.pipeline` 下的模块想拿到 `Chain` 类型，都得反向 import 一个装满 pipeline 依赖的模块——F1 那条环就是这么来的。

**替代方案（可直接采纳）**，把第 5 节的两行替换为：

```
app/
  chain.py                        ← 自 composition.py：Chain 记录本身（仅类型：ProxyConfig、ProviderRegistry、
                                     TranslatorRegistry、FrozenSubscribers、AsyncClient、RateLimiter、
                                     ActiveRequestRegistry、TerminalCapabilities、TokenizationStateStore）
  composition/                    ← 建造者，只有组装侧 import 它
      __init__.py                 ← build_chain、refresh_catalogs
      http_client.py              ← TransportOptions、transport_options、build_http_client、keepalive、代理与 SOCKS
      providers.py                ← resolve_provider_base_urls、build_copilot_provider
      tokens.py                   ← github_token_path、build_github_token_source
```

好处有三：`app.chain` 是一个薄记录模块，任何层 import 它都不会拖进 24 个 pipeline 模块；`http_client.py` 不再需要一个撞车的名字；`composition/` 是包，以后加第二个 provider 的组装不必再切一次。

关于 `Chain` 是否应该继续作为参数出现在 driver 签名里——那是一个更大的问题（`Chain` 是组装根的产物，driver 按 `architecture.md` 应该读 typed facts），**不必在本次解决**，但应在第 10 节登记，否则第 4 步做完之后没人会再回头看它。

---

## F6（major）`handler.py` 的三条缝漏了 8 个符号、约 110 行，而且应该是四条缝

`handler.py` 有 26 个顶层符号。第 5 节点名了 18 个，剩下 8 个没有落点：

| 符号 | 行数 | 现状 |
|---|---|---|
| `HandledRequest`（dataclass） | 13 | driver 与 selection 与 errors 都要它 |
| `_ledger_for` | 8 | 被 `pipeline_app` 以 `# pyright: ignore[reportPrivateUsage]` 跨模块 import |
| `_answered_failed_search` | 26 | 只被 handler 自己用 |
| `CountTokensRequestError` | 2 | 被 `error_status` 判 400，跨了提案划的两条缝 |
| `_countable` | 13 | 只被 handler 自己用 |
| `response_payload` | 22 | 正文第 163 行说「归 pipeline」，但树里没有它的文件 |
| `blocks_from_anthropic` | 14 | 无落点 |
| `reply_summary` | 12 | 无落点，被 `pipeline_app` 用 |

`response_payload` 判给 pipeline 而不是 `errors.py`——**这个判断我认可，理由也对**：它调用 `chain.translators.translate_response`，是翻译，不是 HTTP 渲染。但「归 pipeline」不是一个落点，树里必须有那个文件名。

**替代方案**：加第四条缝。这四个符号是同一件事——「把一份已经完成的回复，按客户端的语汇读回来」：

```
  pipeline/
      reply.py                    ← 自 server/handler.py：response_payload（翻译回客户端格式）、
                                     blocks_from_anthropic、reply_summary、dialect_for
```

再把剩下四个明确落位：`HandledRequest` 与 `CountTokensRequestError` 随 `driver.py`（`server/errors.py` 反向 import `app.pipeline.driver` 取异常类型是允许方向）；`_ledger_for`、`_answered_failed_search`、`_countable` 随 `driver.py`，其中 `_ledger_for` 被 `pipeline_app` 跨模块用了私有名，搬迁时顺手改成公开 `ledger_for` 并删掉那条 pyright ignore——这是这次搬迁能免费拿到的一处清理。

注意 `dialect_for` 同时被 F1 的 `delivery_selection.py`（`assembler_for` 要它）与 `reply.py`（`reply_summary` 要它）需要。放 `delivery_selection.py`，`reply.py` import 它；反向会让 selection 依赖 reply。

---

## F7（major）第 8 节的顺序有实质缺陷：最贵的一件事被挂在唯一一道裁决后面，而且 `_dispatch` 要被改写三遍

`_dispatch` 是 428 行、六个变化理由，第 4 节 S4 说它违反 `D-ARCH=B` 边界 2——按提案自己的论证，这是**本次唯一一处架构边界违反**。第 8 节把它放在第 5 步「瘦身后的派发」，而第 5 步的前置是第 9.1 条用户裁决（`server/routes` 这个名字）。

于是：**改不改 `_dispatch`，取决于用户怎么答一个关于目录名字的问题。** 这两件事之间没有真实依赖。`_dispatch` 可以就地拆薄，留在 `pipeline_app.py` 里；等 9.1 有了答案再决定它落在 `routes/inference.py` 还是别处。

第二个顺序问题：按提案的排法，`_dispatch` 的函数体要被改写三遍——第 3 步抽可观测性（`_StreamAccounting` 在 `_dispatch` 里构造、`_counted_upstream` 与 `_tracked_delivery` 在 `_dispatch` 里接线）、第 4 步换 handler 的 import 与调用、第 5 步再整体搬走。在一个两天内被提交 31 次的文件里，同一个 428 行函数改三遍。

**替代方案（可直接采纳）**，把第 8 节替换为：

1. **`tls.py` → `lifecycle/`**。零包内消费者，`git log --since=2026-08-20` 显示它 0 次提交。最安全，也用来验证搬迁流程。（与原第 1 步相同。）
2. **收窄参数，不搬文件**。把 F1 列的七个 selection 函数、`_log_completion`、`deliver_blocks` 的 `Chain` 参数换成它们实际读的那一段 config 或 `Route`。约 20 处调用点，全是小 hunk。**这一步是原提案没有的，但它让第 3、4、5 步各自独立、且都不再产生 import 环。**
3. **`composition.py` 按 F5 切**：`app/chain.py` + `app/composition/`。完成后 `server/__init__.py` 不再需要为隔离而空着。
4. **`_dispatch` 就地拆薄**，不搬家。把六个变化理由拆成命名函数，留在 `pipeline_app.py`。这一步兑现 S4，且不依赖任何裁决。
5. **`handler.py` 按 F6 的四条缝拆开** → `pipeline/driver.py`、`pipeline/reply.py`、`pipeline/delivery_selection.py`、`server/errors.py`。
6. **可观测性按 F2 切开**：发射侧进 `app/observability/`，所有权侧留 `server/accounting.py`。
7. **建立 `server/routes/`**（前置 9.1）。此时 `_dispatch` 已经薄了，这一步退化成纯搬迁。
8. **旧链收尾**（前置 9.2）。

关键改动是把「拆薄 `_dispatch`」从第 5 步提到第 4 步、并与目录裁决解耦，以及在最前面插入「收窄参数」。

---

## F8（major）第 7 节对方案 3 的反对，理由被本文档自己的触发来源证伪了

原文：「它把……违反，从『待修的债』改写成『记录在案的现状』，而**记录下来的现状是不会有人再回头看的**。」

后半句是一条没有依据的经验断言，而且这份文档的**触发来源恰好是它的反例**：第 4 行写着「修复代码文档引用时发现 `src/app/server/__init__.py` 引用了……」——`server/__init__.py` 那段记录现状的 docstring 被读了，而且正是它启动了这次分析。同一份文档不能一边靠「记录被读到了」立论，一边断言「记录不会被读」。

另外提交 `1f29d0a` 刚刚做了方案 3 的一部分（9.2 节的选项 c），所以这句反对同时也在否定几小时前刚落地的一次改动。

**结论本身我认可**，方案 1 优于方案 3——但理由要换。**替代文本（可直接采纳）**，替换第 209 行「方案 3 我明确反对」那一句：

> 方案 3 我明确反对，但不是因为「写下来就没人看」——`server/__init__.py` 的那段记录恰好被读到了，这份分析就是那么开始的。反对的理由是**这次要修的不是一处描述不准**：`_dispatch` 持有客户端时限与交付编排，违反的是 `D-ARCH = B` 边界 2 这条已被用户接受的架构边界。一处架构边界违反被准确地记录下来，仍然是一处架构边界违反；文档改对了不会让边界重新成立。方案 3 适用于「代码是对的、文档说岔了」，而 S4 是反过来的。

---

## F9（minor）`routes/table.py` 把 `InboundRoute` 与它唯一的消费者 `build_context` 拆开了

第 5 节让 `table.py` 收走 `InboundRoute`、`ROUTES`、`route_for_path`，`inbound.py` 只剩 `build_context`。但 `build_context(route: InboundRoute, ...)` 的第一个参数就是 `InboundRoute`。拆开之后 `server.inbound` → `server.routes.table`，而 `server.routes.inference` → `server.inbound.build_context`，两个包互相依赖。

这 89 行是一件事：「哪些端点、各自什么格式、body 怎么解」。`route_for_path` 与 `build_context` 在 `pipeline_app._dispatch` 里连着调用（第 399 行和第 417 行）。拆它没有收益。

**替代方案**：`server/routes/table.py` 收走整个今天的 `inbound.py`（含 `build_context`、`InboundRequestError`），`server/` 根下不再有 `inbound.py`。`build_router` 与 `ROUTES` 也在同一个文件——路由表和遍历它的注册函数是一件事，14 行的 `build_router` 单独占 `__init__.py` 是过度切分。

---

## F10（minor）`server/errors.py` 与已存在的 `app/errors.py` 撞名

`src/app/errors.py` 已存在（`ErrorCategory`、`WIRE_TYPES`、`ApiError`、`classify_error`），且被 `app/pipeline/delivery/stream.py` 使用。再建一个 `server/errors.py` 装 `error_status`／`error_headers`／`error_body`，就得到两个 `errors`。同 F4，是 S5 自己立的规矩。

**替代方案**：`server/error_response.py`，或 `server/http_errors.py`。这三个函数做的事是「领域异常 → HTTP 状态、头、body」，名字应该说出 HTTP 那一半。我倾向 `server/error_response.py`。

---

## F11（minor）`observability/upstream_connection.py` 单开一个模块，收益撑不起

那 68 行是 `_extra_info`、`_readable`、`_socket_address`、`_alpn`、`_snapshot_upstream_connection`，其中前四个是第五个的私有助手，而第五个的唯一消费者是 `_Trace.upstream_conn`。一条链，一个消费者，单开一个顶层模块。

**替代方案**：并入 F3 决定的那个文件（`request_log.py` 或新的记录文件），跟 `_Trace` 放一起。第 5 节里删掉 `upstream_connection.py` 这一行。

这是第 3 问「哪一步收益撑不起改动面」的答案之一：第 3 步里，三个新模块可以是一个半。

---

## F12（minor）`app/composition.py` 是一个新增的、不在追认清单里的顶层落点，而第 3.4 节把这件事当作缺陷来数

第 3.4 节列了「存在却从未在追认清单里出现」的 10 个顶层包，作为「追认的树与代码分叉」的证据。然后第 5 节新增 `app/composition.py`（按 F5 则是 `app/chain.py` + `app/composition/`），同样不在清单里，第 9 节也没把它列为需要追认的第三项。

我不认为这构成阻断——第 2 节引的授权说明确实覆盖「`app/` 内部的模块合并与拆分」。但**标准要一致**：要么在第 9 节加一条「顺带请用户追认 `composition`（或 `chain`）这个顶层名」，要么在第 5 节写明「本文认为它落在授权覆盖范围内，不需要追认，与第 3.4 节列举的 10 个不同，因为那 10 个是既成事实而这一个是本次主动选择的名字」。我倾向前者：一行字的成本，换掉一处将来会被翻出来的不一致。

---

## F13（minor）第 5 节「与 `D-ARCH = B` 五项核心的对应」表里，边界 4 那一行的说法不成立

原文：「4 assembler／sequencer／sink／frontier 是一条完整交付链 → 交付选型迁入 `pipeline/delivery/`，表面不再持有成帧决定」。

边界 4 讲的是 assembler、commit sequencer、block memory buffer、renderer、sink、delivery ledger 这**六个组件的职责分离与顺序**。把「选哪个 framer」这个决定换个目录，既没有引入 sequencer，也没有改变 frontier，跟边界 4 无关。而按 F1，这一步还会损害 `delivery/` 作为叶子的地位。

**替代文本**：把这一行改成

> | 4 assembler／sequencer／sink／frontier 是一条完整交付链 | **本次不触及**。交付选型（选哪个 assembler／framer）与交付链本身是两件事，前者是路由的推论、后者是 `pipeline/delivery/` 的内部结构；本次只把选型从 HTTP 表面挪到 pipeline，链本身的组件划分不动 |

---

## F14（minor）落地风险：按同伴改动密度，第 3、4、5 步是撞车区，第 1、2 步几乎无风险

我测了 `git log --since=2026-08-20 --oneline -- <file> | wc -l`：

| 文件 | 两天内提交次数 | 当前工作树 |
|---|---|---|
| `src/app/server/pipeline_app.py` | **31** | 脏 |
| `src/app/server/handler.py` | **20** | 脏 |
| `src/app/server/composition.py` | 17 | 干净 |
| `src/app/cli.py` | 14 | 脏 |
| `src/app/server/inbound.py` | 1 | 干净 |
| `src/app/server/tls.py` | **0** | 干净 |
| `src/app/server/ops_routes.py` | **0** | 干净 |

`docs/.human-controlled/` 下有 5 个文件当前是脏的（含 `module-org.md`），说明用户本人也在改。

判断（判断权重：可据以行动）：

- **第 1 步（tls）零风险**，`tls.py` 与 `ops_routes.py` 都是两天零提交。
- **第 2 步（收窄参数，见 F7）风险低于搬迁**：它改的是签名和 20 处调用点，都是小 hunk。同伴在 `_dispatch` **函数体**里的改动与 `framer_for` **签名**的改动通常落在不同 hunk，Git 能自动合。而「把 645 行搬出 `handler.py`」与同伴对 `handler.py` **任何位置**的改动都会冲突。这是把收窄提到最前面的第二个理由。
- **最容易撞车的是第 6 步（可观测性）与第 5 步（handler 拆分）**，两者都在 `pipeline_app.py`／`handler.py` 上。这两步应该**当天开工当天落地**，不要跨会话挂着。
- 提案第 8 节说「每一步单独提交」，这是对的，但还不够。建议补一句：**每一步都用 `git mv` 起头**，让 Git 记录 rename，这样同伴在旧路径上的并行改动在 rebase 时还能被跟到新路径；先复制再删除会让 rename 检测失效。

原提案第 11 节已经承认了同伴并行改动，但第 8 节没有把这个事实变成顺序决策。上面这几条应该进第 8 节正文，而不是留在能力边界里。

---

## F15（minor）目标布局没有为 `http.response.start` 的所有者留位置

`architecture.md`：「**Delayed response-start owner** 是 route 与 sink 之间唯一有权发送 ASGI `http.response.start` 的组件。流式 success headers 在首个完整 block 已 materialize、或无 block 的 terminal／pre-body error 已确定前保持未提交。」

第 5 节的树里没有任何一个名字对应它。仓库里 `src/app/streaming/delayed_commit.py` 存在，`app_factory.py` 那条链上还有 `DelayedStartStreamingResponse`（`_AccountedStreamingResponse` 的 docstring 提到它）。新链上这个角色今天由谁承担、目标布局里它落在哪，提案没有回答。

不构成阻断（本次不触及边界 4/5 是明说的），但应在第 10 节登记一条，否则第 5 步建 `server/routes/` 时会临时给它找个地方放。

---

## F16（minor）第 3.4 节只数了顶层「包」，漏了 7 个顶层「模块」，其中一个与第 6 步直接相关

`src/app/` 下还有 `deps.py`、`errors.py`、`graceful_timeout.py`、`repetition_detector.py`、`runtime.py`、`shutdown.py`、`wire_json.py`，都不在 `module-org.md` 的追认清单里，第 3.4 节没有数它们。

其中 `runtime.py` 值得单独提：它装的是 `RuntimeState`——旧链的「整个进程装配好的状态」，也就是新链 `Chain` 的对应物（`AnthropicClient`、`OpenAIClient`、`ApprovalGate`、`HistoryStore`……）。第 6 步删旧链时它一起走。这一条与 S5「两个 `DeliverySession`」是同一族，可以并进第 4 节 S5 的例子里，也让第 6 步的清单更完整。

---

## F17（nit）`deliver_blocks` 是死代码，提案给它安排了新家

`rg -w deliver_blocks src tests` 在全仓只有 1 处命中，就是它自己的定义（`handler.py:517`）。第 5 节把它列进 `delivery/selection.py` 的搬迁清单。

搬迁前先确认它是不是刚被同伴的某次改动孤立掉的（`handler.py` 两天内 20 次提交）。若确实无人调用，删掉比搬走便宜。`blocks_from_anthropic` 只有测试在用（`tests/unit/pipeline/delivery/test_sse_assembly.py`），但它是 `reply_summary` 的实现细节，随 F6 的 `reply.py` 走即可。

---

## F18（nit）第 5 节把 `apply_route`／`translation_target` 写成「并入 `pipeline/routing.py`」，但没说并进去之后名字冲不冲

`app/pipeline/routing.py` 已有 `Route`、`RoutingError`、`decide_route`；`app/pipeline/route_policy.py` 也已存在。`apply_route` 与 `decide_route` 两个名字挨在一起，读者要停一下才知道谁调用谁。搬进去时顺手在文件头写一句两者的分工，或者把 `apply_route` 改名（它做的是「把已决的 route 写回 context」）。

---

## 逐条回答任务里的六个问题

**Q1 第 5 节的目标布局是不是真的更好？** 部分是。

- `composition.py` 的切法**不对**（F4、F5）。切在「对象图 vs HTTP 客户端」上，漏掉了真正让后续变难的那一刀：记录 vs 建造者。
- `tls.py` → `lifecycle/` **对**。三个消费者全在 `lifecycle`／`cli`，包内零消费者，`module-org.md` 明写「不代表子模块也被追认」所以不需要裁决，S2 的依赖方向论证成立。这是六个落点里最干净的一个。
- `handler.py` 的三条缝：**两条是真缝，一条是错的，还缺第四条**。`server/errors.py`（改名，见 F10）真；`pipeline/driver.py` 真；`pipeline/delivery/selection.py` **错**（F1）；缺 `pipeline/reply.py`（F6）。`response_payload` 判给 pipeline 而不是 errors——**判对了**，理由（它调 `translate_response`，是翻译不是渲染）也成立，但树里必须给它一个文件名。
- 可观测性三块搬进 `app/observability/`：**会造成新耦合，但不是任务里担心的那一种**。反向 import 请求内部结构这个先例**已经存在且已被接受**——`app/observability/rejection_capture.py` 今天就 import `app.pipeline.request.RequestContext`，`request_log.py` 今天就 import `app.pipeline.delivery.assembling.ReplyDialect`。所以 `_Trace`／`_log_completion` 那一块**没有新增耦合类别**。真正的新耦合是 `_AccountedStreamingResponse` 会把 Starlette 拖进一个今天不认识任何 web 框架的包，而且它是 body close owner——那是 F2 的 blocker。
- `server/routes/` 再分三份：**过度切分**（F9）。`table.py` 与 `build_context` 拆开制造双向依赖；`__init__.py` 只放 14 行 `build_router` 没必要。`ops.py` 独立是对的（76 行、两天零提交、职责清楚）。

**Q2 有没有更好的分解？** 有，写在 F1、F5、F6、F7 里，都是可直接替换进原文的成品文本。一句话概括：**先收窄参数，再搬文件**。目标布局的每一处争议——delivery 的环、observability 的框架依赖、driver 拖进组装根——都是同一个原因：`Chain` 作为参数穿过了每一条新划的包边界。把七个 selection 函数和 `_log_completion` 的 `Chain` 换成它们实际读的 config 段（约 20 处调用点），三个问题同时消失，后面四步互相解耦。

**Q3 有没有过度设计？** 有三处，都在第 5 节而不在第 8 节：`observability/upstream_connection.py` 单开模块（F11）、`routes/table.py` 与 `inbound.py` 的拆分（F9）、`routes/__init__.py` 只装 14 行。第 8 节六步里，**没有哪一步应该不做**——每一步都对应第 4 节一处有独立判据的怪味。但**第 3 步与第 6 步应该合并**成一步（F2 的切法一旦定下来，可观测性发射侧与所有权侧是同一次改写），**第 5 步应该拆成两步**（拆薄 `_dispatch` 与建 `routes/` 目录，前者不该等裁决）。

**Q4 第 8 节的顺序对吗？** 不对，有两处（F7）。一是 `_dispatch` 的拆薄被挂在 9.1 裁决后面，而两者无真实依赖；这是**本次最贵、也是唯一兑现架构边界的那一步**。二是 `_dispatch` 的函数体会被第 3、4、5 步各改一遍，在一个两天 31 次提交的文件里。替代顺序见 F7，共八步。

**Q5 对方案 3 的反对是否过强？** **理由过强，结论不过强**（F8）。「记录下来的现状不会有人再回头看」被本文档自己的触发来源证伪，也否定了几小时前的 `1f29d0a`。换成「S4 是架构边界违反，不是描述不准，改文档不会让边界重新成立」，结论照样立得住。

**Q6 共享树上现实吗？** 现实，但要按 F14 重排。第 1、2 步几乎无风险；第 5、6 步是撞车区，要当天落地；每步用 `git mv` 起头以保住 rename 检测。这几条应该写进第 8 节正文，不是留在第 11 节能力边界。

**Q7 漏掉的约束？** 一条 blocker（F2，`architecture.md`「converter 和 observer 不关闭 transport」＋「Downstream sink 是唯一 body writer」）、一处未安置的已定义角色（F15，Delayed response-start owner）、一处不成立的边界对应声明（F13，边界 4）。`docs/.human-controlled/` 方面：`module-org.md` 明写「不代表子模块也被追认」，所以 `lifecycle/tls.py`、`pipeline/driver.py`、`pipeline/reply.py`、`server/routes/*` 都不需要裁决；`request-pipeline.md` 的「`app.pipeline` 负责驱动模型请求的处理」正面支持 `handler.py → pipeline/driver.py`；`api.md` 与第 6 节的对账我认可，没有发现新的抵触。唯一要补的是 F12：新增顶层 `composition`／`chain` 这个名字，标准应与第 3.4 节一致。

---

## 我**没有**核查的部分

- **原文的一切数字与引用**：行数、模块数、可达性表格、`_dispatch` 418 行、`pipeline_app.py` 1037 行、第 2 节权威表里各文档的日期与授权原文、第 9.1 节的提交考古（`b4ae8b0`、2026-07-15 的兄弟提交）。这些归事实核查评审者。本文引用它们时一律当作真。我自己另测的数字（33 个字段、26 个顶层符号、七个 selection 函数、churn 表、import 图）在文中标注了，可复核。
- **没有跑任何测试、没有跑 ruff／pyright**，也没有实际执行任何搬迁或改动。本文全部结论来自静态阅读与 AST 分析。
- **import 环的三条结论是静态推导，不是运行时复现**。机制（`import a.b.c` 先执行 `a/b/__init__.py`）是 Python 语义，路径是从真实 import 语句建的图，正样本对照做过。判断权重：**可据以行动**。但如果要在动手前把它变成一手证据，最便宜的做法是在一次性解释器里造一个空的 `app/pipeline/delivery/selection.py`（内含 `from app.server.composition import Chain`）并在 `delivery/__init__.py` 里导出它，然后 `import app.server.composition`——一条命令就能看到 `ImportError`。**我没有做这件事，因为它需要写文件到主树。**
- **`architecture.md` 我只读了第 128–427 行**（推荐目标架构、单一 driver 职责、策略 outcome、共享事实模型、所有权与生命周期、隔离规则、protocol/transport 分离、Responses transport port、Converter 边界、Block assembler／buffer／sink、以及 Retry 与 frontier 的开头）。679 行的后半（Failure matrix、History 与 observer、非流式路径、可证伪判据、结构怪味登记、ADR-BRIDGE-0x、裁决矩阵、评审问题处置表）**未读**。若那半部分另有对内部分层的细约束，本文的 F2、F13、F15 可能需要修正。
- **`docs/.human-controlled/` 我读了 `README.md`、`module-org.md`、`request-pipeline.md`、`api.md`**。`lifecycle.md`、`client-side-block-delivery.md`、`message-format-reshape.md`、`message-translation.md`、`observability.md`、`test-org.md`、`upstream-retry-and-continuation.md`、`config.example.yaml` **未读**。特别是 `observability.md`（README 清单里有，但目录里我没看到这个文件——可能是清单与实际不符，这一条留给事实核查者）与 `lifecycle.md`，前者可能对 F2、F3 的落点有话说，后者可能对 `lifecycle/tls.py` 有话说。
- **两份支撑报告**（`260822-server-layout-chain-map.md`、`260822-server-layout-prior-art.md`）未读。
- **未评估旧链 12 个 `app/routes/` 模块的内部结构**，第 6 节的端点对账我按原文接受。
- **未评估测试文件的搬迁成本**。`tests/unit/server/` 下至少 `test_http_client_build.py`（约 540 行）、`test_tls_and_count_tokens.py`、`test_server_inbound.py` 会跟着移位置或改 import；`tests/int/` 有 4 个文件 import `app.server.handler` 或 `app.server.composition`。第 8 节没有提到这部分工作量。
