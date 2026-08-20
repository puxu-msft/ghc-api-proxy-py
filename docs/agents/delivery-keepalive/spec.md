# 保活契约：client ↔ proxy 与 proxy ↔ upstream 是两侧，不是一件事

- 状态：规范。适用范围是 `src/app/pipeline/delivery/stream.py` 的下游交付，随该外部契约有效而有效。
- 用户裁决：**「要清晰区分 client ↔ proxy ↔ upstream 这两侧的保活，它们是不同的，不可混为一谈。」**（2026-08-20）
- 缺陷背景与实测证据：`docs/tmp/260820-downstream-keepalive-defect.md`（含独立证伪评审 `docs/tmp/260820-review-downstream-keepalive-defect.md`）与 `docs/tmp/260820-review-synthetic-start-fix.md`。**这三份连同 `docs/.human-controlled/` 目前都还不在 `main` 上**，由并行会话的 `53fec22` 一并提交；在它落到 `main` 之前，从 `main` 的干净 checkout 出发读不到本文引用的实测数字。
- 本文所在主题共 19 份独立评审报告：`docs/agents/delivery-keepalive/` 下 17 份（asyncio 正确性 8 轮、契约 3 轮、传输层 3 轮、调和 1 份、合入后传输层复评 1 份、合入后 cap 去重复评 1 份），`docs/tmp/` 下 2 份文档与裁决核对（`260820-review-keepalive-rulings.md`、`260820-review-keepalive-doc-fixes.md`）。本文正文经契约评审 3 轮修订（F1–F11 出自第一轮）。**§3 是上游 slice 落地后重写的，未经代码评审以外的任何评审；§2.2 与 §4 在 2026-08-20 又整段重写过一次，那一次由文档核对的第二轮覆盖。**
- 未决事项集中在 `deferred.md`；**§2.2 尚有一条需要用户裁决，未裁之前不得当作已定**

---

## 1. 为什么必须分开

代理中间隔着**块级交付**。上游按 delta 说话，我们按完整块交付。因此「上游这一侧有动静」与「下游那一侧有字节」在时间上是脱钩的：上游可以每 200ms 发一个 delta，而同一时间窗内下游一个字节都没有——那些 delta 正在装配一个尚未闭合的块。

把两侧的保活混成一套，结果就是保活被装反：上游安静时发 ping（此时下游本来就没有超时压力，因为我们也确实没什么可发），上游活跃时不发 ping（此时下游正被饿着）。这不是理论推演，是 `_events_with_ping` 在 2026-08-20 之前的实际行为，实测见背景文档第 1 节。

## 2. client ↔ proxy 一侧（下游保活）

**被保护的对象**：客户端到代理的那条 HTTP 连接，以及客户端自己的空闲计时器。

**判据**：一旦交付已经开始（定义见 §2.1），代理**不得**让客户端连续 `client_delivery.sse_ping_interval` 秒收不到任何字节。`sse_ping_interval = 0` 关闭该判据——此时本节不作任何承诺，下游静默无上界。

**唯一的计时基准是「我们上一次向客户端交出字节的时刻」。** 具体地：

- 任何写往客户端的字节都重置它——内容帧、`message_start`、终止帧，以及保活帧自身。
- **上游事件不得重置它。** 上游收到什么、收到多少、多频繁，与这个计时器无关。
- 保活帧是 SSE 注释（`: ping\n\n`）。它不携带内容，因此不可能被误读成一个块。已实测：客户端的空闲计时器接受注释帧作为活动信号（背景文档 §4）。

**为什么是注释帧而不是 `ping` 事件。** Anthropic 官方 API 发的是带类型的 `ping` 事件。本项目发注释帧，理由是它对下游的承诺更少，且实测足以重置客户端的空闲计时器。**若将来发现某个客户端只认事件不认注释，这条要重新裁决**，而不是两个都发。

**上一条全称断言由一个结构不变量支撑，改动时必须一并维持**：`stream_delivery` 是内层 `_deliver` 的薄包装，`_deliver` 产出字节的所有位置都经由它唯一的 `yield` 离开，时间戳在那一处打。**若将来有人在 `stream_delivery` 之外新增一条向客户端写字节的路径，这条断言就不再成立，而且不会有任何测试变红。**

时间戳打在 `yield` **恢复之后**而不是之前：`StreamingResponse` 先取 chunk 再 `await send`，所以恢复点意味着该 chunk 已经交给服务器。打在之前会把计时起点提前到「我们造出字节」而非「字节离开」，慢下游会因此提前收到 ping。

**到期的保活必须在继续交付任意数量的「立即就绪」上游事件之前先结算。** 上游若有一串已缓冲的事件，每次拉取都在同一个调度轮内完成，于是「交付事件」这条分支每轮都命中，而它下面那个「deadline 到期了吗」的判断一次都到不了。这些事件在块未闭合时不产生任何下游字节，客户端就被饿死整段连发期。实测：10.46s 内出现 173125 次已到期却被跳过的机会，ping 数为 0。因此判据不是「等待超时时发一个 ping」，而是「到期就发」，无论这一轮有没有等待发生。

**但结算必须排在「已经就绪的结束」之后。** 一次拉取的结果只有三种：一个正常事件、流结束、或一个失败。结算要在读出结果、确认拿到的是正常事件之后才做——**已经在等着的 EOF 或异常必须先于保活传播**。反过来（在创建下一次拉取之前就结算）等于在不知道下一次拉取会返回什么的情况下先发一枚注释：流已经结束时它会插在终止帧前面，失败时它会把一次下游写入插在调用方与那个上游异常之间，而下游写入一旦失败或被取消，那个异常在这条消费链上就再也观察不到了。

**「到期就结算」适用于本节涉及的每一个 deadline，不只是保活。** §2.2 的合成计时是同一条连发路径下的另一个受害者：只结算保活而漏掉合成，在 `sse_ping_interval = 0` 且合成开启这个合法组合下，被扣住的回答的首字节会被推到流末——同一个饥饿，换一个 deadline。

**而「到期了」不等于「现在就可以写」。** 一次拉取成功返回一个事件，只证明**拉取**成功，不证明这个事件**能被交付**：一个畸形事件会让 assembler 在下一层同步抛异常。因此到期提示不能由调度层单独先写出去，它必须和事件一起交给交付层，由交付层在**成功装配完该事件之后**再决定：若装配已经产生了真实的下游字节，义务已被解除，不必再发；若没有产生字节，才发合成或保活；若装配抛了异常，那个异常先于任何提示传播。

**而且「到期了没有」这件事必须在**能够回答它的那一刻**去问，不能提前采样。** 装配是同步的、时长无上界，deadline 可以在装配期间才到期。把答案在拉取时算好、装配后再消费，等于在问题还不能被回答的时候就问了：实测两次各 1.05s 的装配下，本该 1.05s 发出的保活被推迟到 2.10s。所以调度层交给交付层的是**一个可以调用的提问**，而不是一个布尔答案；交付层在装配完、且确认没写出字节之后调用它，此时才读时钟、并在确实到期时前推排期。

**一个明示接受的取舍：到期的提示仍会发出，即使下一次拉取会立刻结束或失败。** 下一次拉取会返回事件、EOF 还是异常，不拉是不可能知道的。两种排法各有代价：提前采样会漏发（违反 §2 的判据），延后求值会在这种情况下多发一次提示（不违反任何判据）。**按 §2 裁定选后者——漏掉一次该发的保活是违约，多发一次不是。**

**这一次多发的具体形态必须原样写清，不能用「一枚无内容的注释」概括全体**：

- 客户端**已有**字节时，多发的是一枚 `: ping\n\n` 注释，落在流的尾部之前。
- 客户端**尚无**字节且合成已到期时，多发的是 `message_start`。它会置位「客户端已有字节」，于是这条流不再是零字节，而要走完 STR-04 的尾部判定。**若下一次拉取就是 EOF 且上游从未发出合法终止事件，实测线形是 `message_start` → `error`（`incomplete_responses_stream`），并且按已冻结的 Spec 不得再补 `message_stop`。** 也就是说，被接受的代价不是「一个已正常封口的空 message」，而是**把一次原本零字节的请求变成一次客户端可见的截断报错**。不接受这个取舍时，同一请求是零字节、客户端什么也读不到。

  （初版这里写的是 `message_start` → `message_delta` → `message_stop`「已正常封口」。那是主线落地 STR-04 截断语义**之前**的形态，现已作废——见 `review-reconciliation.md` F1。这一处两次写错同一件事：第一次把代价说成注释，第二次把截断说成正常结束。）

另外，若下一次拉取是失败而非 EOF，这次提示的下游写入仍可能先失败，从而使那个尚未取到的异常不被当前消费链观察到。这同样属于接受项。

需要注意的是，**装配自身的异常仍然先于提示传播**（上一段），被接受的只有「下一次拉取才暴露的结束」这一种。

### 2.1 「交付已经开始」的定义

指 `_deliver` 里的 `client_has_bytes`：**客户端已经收到过至少一个字节**。本节判据涉及的三件事共用它——`_commit` 是否发过 `message_start`、保活是否可发、合成计时是否解除。（`DeliverySession.started` 是另一回事，它描述的是缓冲区有没有开始释放，不参与本节判据。）

早先版本有两道门——保活看「有没有写过」，合成计时看「assembler 有没有组装出块」——在 `buffering_policy` 取 `full` 或 `until-tool-use` 时二者会分叉：块被扣住到流末才交付，于是合成计时被解除、而写出从未发生，**两道守卫同时熄灭，静默没有任何上界**。实测（`sse_ping_interval=1`、首块 0.2s 闭合、第二块 3s 不闭合）：`block` 策略 3 个 ping、首字节 0.20s；`full` 与 `until-tool-use` 各 0 个 ping、首字节 3.22s，即流结束的时刻。该缺陷由 `docs/tmp/260820-review-synthetic-start-fix.md` §7 首次指出，现已合并为一道门修掉，回归测试 `test_a_held_back_block_does_not_disarm_both_guards`。

### 2.2 交付开始之前

首个字节交付之前不发保活帧。这一段的静默由另一个机制兜底：`client_delivery.synthesized_response_headers_after_sec` 到期时合成一个 `message_start`，它本身就是「第一个字节」，此后保活按 §2 正常工作。**该上界（默认 240s）现在对三种 `buffering_policy` 一致成立**（见 §2.1）。

**选择 `message_start` 而不是注释帧，是评审比较三个方案后的现行选择**（`docs/tmp/260820-review-synthetic-start-fix.md` §7 逐条比较了「填非空文本的内容块」「只发一个 SSE 注释」「改发 `event: error`」），**不是用户裁决**——该报告原文是「我的偏好」，且其 §9 已把与人写文档的冲突原样交回，至今未裁。

#### 【需用户裁决】实现与人写文档的窗口定义冲突

`docs/.human-controlled/config.example.yaml` 的 `synthesized_response_headers_after_sec` 一节（用户亲笔，按项目约定压过一切我方推导的 ADR 与 spec）。**不引行号**：该文件正被用户持续修订，行号引用已经失效过一次。

初版在此列了两条冲突，**其中一条已经不存在了**：

1. **窗口定义反了——仍在。** 用户描述的窗口是「若很久上游都没有响应头」，而实现的计时**从上游响应头到达之后**才起算——`_deliver` 的函数体要等 uvicorn 第一次拉取 `StreamingResponse` 才执行，那必然在拿到带响应头的 httpx response 之后。
2. ~~合成物不同（用户写「半块」，实现只发 `message_start`）~~ —— **已消解，无需裁决**。用户已于 2026-08-20 把中文原文改成「合成 HTTP 200 以及一个 `message_start`」，与实现一致。（该文件的**英文半句仍写着 `synthesize a half-block`**，中英不一致；那份文件归用户，我方不改，只在 `deferred.md` 记一笔提醒。）

用户在同一次修订里还新写了一条合成代价，我方文档此前没有记过：**「一旦合成，就无法再转发真正的上游 HTTP 状态码了，无法使用原生的客户端重试/退避机制。」** 这与本节下面讨论的代价是不同的一条——下面说的是「多发一次 `message_start` 会把零字节请求变成客户端可见的截断报错」，用户说的是「合成即锁死 HTTP 200，客户端自身的 retry/backoff 从此不可用」。两条都直接影响这个键该不该开、开多大。

**用户描述的那个窗口（请求受理 → 上游首字节）目前确实没有任何保活**，但它落在一个更大的上界之内：`upstream_request_timeouts.upstream_request_deadline`（默认 **1200**，由 `src/app/server/handler.py` 的 `attempt_deadline` 读出，`src/app/pipeline/direct_driver/base.py` 在开始一次尝试时把它固定成一个时刻）。1200s 远高于背景文档 §4 实测的客户端 300s 天花板，**所以指望它替客户端兜底是没有意义的**。

**注意这个上界的射程在 2026-08-20 当天变过，本文初版的描述已作废。** 初版写的是它「恰好且仅仅覆盖首字节前那一段」，理由是 `asyncio.timeout` 只包住 `await send`、body 在上下文之外消费——那正是 `deferred.md` D-6 记的缺陷。`783f023 fix: make each of the three upstream timeouts guard the phase it names` 已经修掉它：header 等待与 `pipeline_app.py` 的 body 流现在读同一个 `attempt.deadline_at`（后者经 `with_deadline_at`），**一个上界，两处执行**。

**它管到哪里，要说三点精度边界**：`with_deadline_at` 只在每次拉取的边界上判定，不打断正在进行的下游消费；上游流结束之后的下游交付（块级缓冲的释放、终止帧）不在界内；而且它是**每次尝试**的界——重试与续写各自 `begin_attempt()` 一次、各得一份新的 1200s，整个请求的墙钟不受它约束。所以它现在是整次尝试的总时长上界，包括流式正文。

**这使得「不要把调低它当成本节的解法」这条理由更强，而不是更弱。** 它是终止器，不是保活——按 §4 的分类，它决定何时放弃上游，而不是让客户端连接活着。把它调到 300 以下换来的不再只是「代理主动掐断等待」，而是**砍断一次已经在输出的长回答**（准确地说，是砍断当前这次尝试；重试会另起一份新的界）。而且人写文档在 `response_header` 名下写明**用户冻结的不变量是绝不误杀合法长思考**，「运维可显式配置非零值以选择有界等待，但那是对该不变量的主动覆盖」。**本规范不提议这种覆盖。**

剩下的那一条冲突（窗口定义）怎么处置由用户裁决：改实现向人写文档靠拢，还是修订人写文档。**未裁之前，实现维持现状。**

### 2.3 本节治下但尚未实现的缓解手段

`client_delivery.hedge`（阈值默认 300s）**只有配置项、没有任何消费方**（`rg 'hedge' src -g '*.py'` 只命中 `config/schema.py` 的定义）。它的触发条件字面上就是本节治理的下游静默——「若客户端请求在此秒数内没有任何块被交付」——因此它属于本节，不是相邻问题。人写配置文档称其用于兜住「Claude Code 的 no-real-content watchdog 尾部」，**这条兜底目前不存在**。

## 3. proxy ↔ upstream 一侧（上游保活）

**被保护的对象**：代理到上游的那条连接，以及中间任何会掐掉长时间空闲连接的设备。

**这一侧与 §2 没有任何共享的计时器、配置项或代码路径。** 它的正确做法是 socket 层的 `SO_KEEPALIVE` 或 HTTP/2 PING 帧，而不是往下游写字节；下游的保活也永远不能替它工作。

**本节初版写的是「两个配置项都没有实现名字所承诺的东西」。2026-08-20 用户裁决 A1 之后，`tcp_keepalive_interval` 已经实现，以下是当前状态。**

### `tcp_keepalive_interval`：已实现，但要说清它探的是哪一跳

`SO_KEEPALIVE` 开启，`TCP_KEEPIDLE` 与 `TCP_KEEPINTVL` 取配置值，探测四次；0 关闭。

**射程取决于有没有代理。** TCP keep-alive 是逐连接的，而代理会终结 TCP 连接。实测 `getpeername()`：直连时 socket 对端是上游本身，走 CONNECT 隧道时对端是**代理**而不是 origin。所以：

| 形态 | 这条 keep-alive 说明什么 |
|---|---|
| 直连 | 上游还活着 |
| HTTP forward 代理 / HTTPS CONNECT 隧道 | 到代理这一跳还活着；代理到上游那一段是代理自己的 socket，我们既看不见也设不了选项 |
| SOCKS | 什么也没探（见下） |

**本项目的部署形态是直连**，所以这个键在实际部署里确实探的是上游本身。但不要把「代理路径也修好了」读成「代理路径也能探到上游」。

### `http2_ping_interval`：不是接线遗漏，是能力缺口

httpcore 1.0.9 不提供发送 PING 的接口，h2 库有 `ping()` 但 httpcore 从不调用、也没有后台读循环，实现它等于分叉传输层。键保留并标注 NOT IMPLEMENTED。它原先兼职决定协议（`http2 = interval > 0`），并行会话已用独立的 `upstream_transport.http2` 取代那个用法。

### SOCKS 路径：用户裁决接受限制并告警

`httpcore.AsyncSOCKSProxy` **根本没有 `socket_options` 参数**——与 HTTP 代理那条不同（那是收了参数却在 `create_connection` 丢掉，已覆写修好）。实测 SOCKS5 连接读回 `SO_KEEPALIVE=0`。2026-08-20 用户裁决：**接受这个限制，构造期告警**（覆盖配置与环境变量两种来源，只记 origin 不记凭据）。

### 不再由本项目决定的事

连接池的保留时长与连接数上限**不再由新链路配置**。初版曾把 `tcp_keepalive_interval` 错映射产生的 15 秒当成需要保住的行为、并为此新造了一个键——用户指出那从来没有被裁决过，是缺陷的副产物。现已撤销：`composition.py` 不向 transport 传 `limits`，httpx 自己的默认即生效值。

（射程限定在**新链路**是有必要的：旧链路 `src/app/config/settings.py` 的 `UpstreamConfig` 仍带 `max_connections` / `max_keepalive_connections` / `keepalive_expiry`，并由 `src/app/upstream/client.py` 的 `create_http_client()` 传给 `httpx.Limits`。那条链路没有被删，按项目约定孤儿模块可以留着。写成「不是本项目的配置」是把射程放大了。）

`src/app/config/settings.py` 的 `upstream_keepalive` / `upstream_h2_ping` 是这两项的 legacy 拼写，均已被上述键取代并删除。

## 4. 相邻但不属于本规范的

**上游空闲检测**（「上游多久不说话就判定它死了」）是终止条件，不是保活：一个是让连接活着，一个是决定放弃它。

**这一段在 2026-08-20 当天被并行会话改过两次，本规范此前的两版描述都已作废。** 初版写的是「`upstream_request_timeouts.stream_idle` 无任何消费方，实际生效的是旧链路 `routes/anthropic.py` 那个同名配置」；`a7ca9ea feat: honour the upstream idle timeout on the pipeline streaming path` 之后不再成立。第二版写的是它读 `stream_idle` **与 `stream_idle_overrides`**；`064ba63` 之后这半句也不成立了——那次提交把 `stream_idle_seconds` 的 overrides 解析删掉，随后 `783f023` 又删掉了 `schema.py` 里对应的两个字段。

当前事实：`src/app/server/handler.py` 的 `stream_idle_seconds` 函数体只有一行，直接返回 `chain.config.upstream_request_timeouts.stream_idle`，没有 overrides；`UpstreamRequestTimeoutsConfig` 只剩 `response_header` / `stream_idle` / `upstream_request_deadline` 三个字段。接线点在 `src/app/server/pipeline_app.py`，经 `with_idle_timeout` 套在上游字节流上，并由 `with_deadline_at` 包在外层。**新链路现在有上游空闲检测，默认值 0（禁用）。**

（`src/app/config/settings.py` 的 legacy `TimeoutConfig` 里还留着 `stream_idle_overrides` / `response_header_overrides` 同名字段，读它们的是旧链路的 `app/streaming/idle_timeout.py` 的 `resolve_stream_idle`，只有 `routes/anthropic.py` 导入。与本节讨论的 `upstream_request_timeouts.*` 不是同一组配置。注意 `with_idle_timeout` 本身是两条链路共用的函数——分离的是字段，不是那个函数。）

记这一笔不是为了记录一次配置变更，而是因为它示范了本规范的一个使用限制：**本文里每一条关于「某处有没有接线」的断言都有保质期**，主线在动，读到时请重新核实，不要把它当成当前事实引用。这条警告目前已击发五次：本节两次、§2.2 一次、§3 关于 `http2_ping_interval` 兼职协议开关一次，以及用户改写人写文档使 §2.2 的引文作废一次。

`upstream_request_deadline` **被 `response_header_overrides` 解析**（`deferred.md` D-5）由 `064ba63` 修掉，body 未被 deadline 约束（D-6）由 `783f023` 修掉。**注意 D-5 的主语是 deadline 不是 `response_header`**；`response_header` 无消费方是另一件事，一道从未实现的守卫。
