# 评审：`docs/agents/delivery-keepalive/spec.md` 能否作为规范固定

- 评审对象：commit `a374f39`（`fix: keep the client alive on our own writes, not on upstream's chatter`），重点是新增文件 `docs/agents/delivery-keepalive/spec.md`
- 评审工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`（隔离 worktree，全程只读；探针写在 `/tmp/probe_keepalive/`，未落进仓库）
- 角色：证伪者。下面每条都给可复核命令或 `文件:行`
- 结论：**needs-fix**。骨架成立，但 §2.2 的枚举漏了三者中唯一无上界的窗口，§2.2/§4 有三条可复核的事实错误，§2 的核心术语未定义

严重度：**阻断**（会让读者据此做错决策，或与人写文档冲突）／**重要**（事实不准，需改）／**次要**（措辞与完备性）
把握程度：**高**（本次亲手复现或 grep 全量复核）／**中**（读码推断，未直接复现）

---

## 0. 先说结论

站得住的三条骨架，我复核后确认无误：

1. **两侧必须分开**（§1）。理由陈述准确，且被 `docs/tmp/260820-downstream-keepalive-defect.md` §1 的正样本对照实测（chatty 0 ping / silent 2 ping）与评审方独立重跑双重支撑。
2. **下游保活的唯一基准是「我们上一次向客户端写出字节」**（§2）。逐条复核后成立，见 F9。
3. **上游侧那两个配置项名不副实**（§3）。逐条复核后成立，且比 spec 说的更彻底，见 F6。

不能就这样固定的原因集中在 F1–F5、F7。

---

## F1【阻断 / 高】§2.2 的「已知未覆盖的窗口」漏了第三个，而它是三者中唯一没有上界的

§2.2 用「**已知未覆盖的窗口（待用户裁决，本规范不擅自改动）：**」起头，随后编号列出两条——这是一份自称完整的枚举。它漏掉了第三条，且这一条比列出的两条都严重。

**机制**（`src/app/pipeline/delivery/stream.py`）：

- `:172-176` 首个完整块一经 **assembler 组装出来** 就 `response_started.set()`，代码注释自己写明「It ends even if the selected buffering policy holds that block for a later commit」——合成计时就此解除。
- 但 `_commit`（`:203-223` → `blocks.py:98-108`）在 `policy == "full"` 时恒返回 `()`，在 `until-tool-use` 且尚未出现 `tool_use` 块时也恒返回 `()`。于是 `started` 保持 `False`。
- `:169-170` 的 `elif started: yield PING_FRAME` 因此永不击发。

**净结果：`buffering_policy` 取 `full` 或 `until-tool-use` 时，首块一旦组装完成，客户端就进入零字节 + 零保活 + 合成计时已被解除的状态，直到上游整条流结束。上界不是 240s，是「上游想说多久」。**

**实测复现**（探针 `/tmp/probe_keepalive/probe_full_policy.py`，`sse_ping_interval=1`、`synthesized_response_headers_after_sec=2`，首块在 0.2s 闭合、第二块 3s 内不闭合）：

| policy | 总 chunk | ping 数 | 首字节时刻 | 最大间隔 |
|---|---|---|---|---|
| `block` | 9 | **3** | 0.20s | 1.00s |
| `until-tool-use` | 6 | **0** | **3.22s** | — |
| `full` | 6 | **0** | **3.22s** | — |

后两行的「首字节 3.22s」就是流结束的时刻：全部事件在末尾一次性涌出。复现命令（本 worktree 根）：

```bash
PYTHONPATH=src uv run python /tmp/probe_keepalive/probe_full_policy.py
```

**这不是新发现，spec 引用的那份报告里就写着。** `docs/tmp/260820-review-synthetic-start-fix.md` §7 的「【建议】重新审视「解除计时」的条件」整段讲的就是这个，原文「于是 `full` 策略下，第 5 秒就组装好的块被扣住时，合成计时被解除，客户端可以零字节一直等到上游结束（探针 B 复现）」，并给了修法「把「解除」的判据从「首个块被组装出来」改成「已经有字节发给客户端」（即 `started`）即可」，§9 第 4 条把它列为建议 deferred。spec §2.2 恰好引用了同一份报告的 §7，却没有把这一条搬进枚举。

**这条不会因为「交付还没开始所以不违反 §2 判据」而消解。** 就算按最宽松的读法把它归进「交付开始之前」，§2.2 第 2 条仍然明写「该窗口的静默上界是 `synthesized_response_headers_after_sec`（默认 240s）」——在非默认 buffering 策略下这句话**是假的**。而 240s 这个数值的全部意义在于卡住背景文档 §4 实测的客户端 300s 天花板；上界一旦消失，这个设计就整个落空。

`buffering_policy` 是三值合法配置（`src/app/config/schema.py:15,191`，默认 `block`），`full` 与 `until-tool-use` 都能经 `src/app/server/handler.py:313-314,374-375` 生效，不是死路径。

**建议改法**：把这条作为第 3 条加进枚举，明确写出「该窗口在 `full` / `until-tool-use` 下没有任何上界」，并把 §7 已给出的修法（解除判据改用 `started`）作为待裁决选项一并列出。

---

## F2【重要 / 高】§2.2 第 1 条「也没有上限」不属实

原文：「合成计时从**上游响应头到达之后**才起算，「请求受理 → 上游首字节」这一段完全没有保活，也没有上限。」

前半句正确（`_deliver` 的 body 要等 uvicorn 第一次拉取 StreamingResponse 才执行，那必然在 `handle_bounded` 拿到带响应头的 httpx response 之后）。后半句错。

这一段恰好且仅仅被 `upstream_request_timeouts.upstream_request_deadline` 限住：

- `src/app/server/handler.py:99-104` 读出它（`src/app/config/schema.py:104` 默认 **1200**），传给 driver；
- `src/app/pipeline/direct_driver/base.py:233-241` 用 `asyncio.timeout(self._attempt_deadline)` 包住 `await send`，超时抛 `UpstreamTimeout`；
- 对流式请求，`await send` 拿到响应头就退出该上下文，body 在上下文之外消费——所以这个 deadline 正好只覆盖 spec 说的这个窗口。

也就是说上限存在，是 1200s。spec 想说的结论（这段实际上没有有效保护）仍然成立，但正确理由是「1200s 远超背景文档 §4 实测的客户端 300s 天花板，所以这个上限对客户端毫无意义」。写成「没有上限」会让读者去补一个已经存在的东西，也会让读者错过「把 1200 调到 300 以下」这个现成选项。

**附带观察（非本 spec 引入，记录备查）**：`src/app/pipeline/direct_driver/base.py:223-224` 的 docstring 称该 deadline「bounds the whole attempt rather than a phase of it, which is what catches an upstream that trickles forever without ever finishing」——对流式请求为假，body 在 `asyncio.timeout` 之外。这条建议单独立案。

---

## F3【重要 / 高】§2.2 把「既有裁决」的权威等级说高了，而且它引用的那条正与人写文档冲突且尚未裁决

原文：「选择 `message_start` 而不是注释帧是既有裁决，理由见 `docs/tmp/260820-review-synthetic-start-fix.md` §7。」

复核该文件后：

1. **§7 的原话是「我的偏好」，不是裁决。** 原文首句：「**我的偏好：维持现方案（只发 `message_start`）**」——这是评审 agent 写在 `docs/tmp/` 临时报告里的偏好陈述。按项目约定，`docs/tmp/` 是工作记录，不是权威源。
2. **引用的内容本身准确。** §7 确实逐条比较了「保留内容块但填非空文本」「只发一个 SSE 注释（复用 `PING_FRAME`）」「改发 `event: error`」三个替代方案并给了理由。所以问题不在事实，在权威标签。
3. **同一份报告把这件事明确交回用户且未裁。** §4.3 标题直接是「【应改·需用户裁决】人写文档说的是「半块」」；§9「交回主会话的事项」第 1 条：「`docs/.human-controlled/config.example.yaml:404-408` 与本次实现冲突（「半块」；以及「无法再转发真正的上游状态码」与实现不符）。该文件属用户亲笔，只能由用户裁决与修改。」

**这直接改变 §2.2 第 1 条的定性。** 人写文档 `docs/.human-controlled/config.example.yaml:404-409` 原文：

> 客户端发起流式请求时，若很久**上游都没有响应头**，合成一个**半块**给客户端。

两处冲突：

- 用户定义的计时窗口是「上游都没有响应头」，实现却从响应头**到达之后**才起算——窗口定义整个反了；
- 用户写的是「半块」，实现只发 `message_start`。

所以 §2.2 第 1 条不是「待用户裁决的未覆盖窗口」，而是**实现与人写文档的直接冲突**。按项目约定 `docs/.human-controlled/` 压过一切我方推导的 ADR/spec，这个定性差别决定了下一步动作完全不同：前者是「等用户想清楚要不要加功能」，后者是「实现偏离了已有裁决，要么改实现要么请用户改文档」。

**建议改法**：§2.2 第 1 条改写为「与人写文档冲突」并直接引用 `docs/.human-controlled/config.example.yaml:404-409`；§2.2 里「既有裁决」四字改为「评审比较后的现行选择（见 …§7），该条与人写文档的「半块」表述冲突，尚未经用户裁决」。

---

## F4【重要 / 高】§4 把 `hedge` 归进「不属于本规范的相邻问题」，定性错误

事实陈述本身正确——`rg -n "HedgeConfig|hedge" src/ tests/ --type py` 只命中 `src/app/config/schema.py:165` 与 `:195`，无任何消费方。

但归类错。人写文档 `docs/.human-controlled/config.example.yaml:415-423`：

> 如果客户端请求在此秒数内**没有任何块被交付**，则开始"对冲"……保守默认 300 秒用于兜住 Claude Code 的 no-real-content watchdog 尾部

它的触发条件字面上就是 §2 治理的「下游交付静默」，默认阈值针对的就是 §2/背景文档 §4 关心的那个 300s 客户端 watchdog。把用户专门为这个窗口设计的兜底机制排除在保活契约之外，会让读者以为 §2.2 的未覆盖窗口没有任何设计方案——实际上用户已经写了一个，只是没实现。

**建议改法**：把 `hedge` 从 §4 挪进 §2.2，作为「用户已设计、尚未实现的兜底」列出，并注明它与 §2.2 各窗口的对应关系。

---

## F5【重要 / 高】§4 的 `stream_idle` 指错了配置项，并低估了缺口

原文：「上游**空闲检测**（`upstream_request_timeouts.stream_idle`……）……当前它只接在旧链路 `app/routes/*`，新链路 `server/pipeline_app.py` 未接线。」

三处不准：

1. **接在旧链路上的不是这个配置对象。** 旧链路读的是 `src/app/config/settings.py:69` 的 `TimeoutConfig.stream_idle`（默认 **300**），路径 `src/app/routes/anthropic.py:217` → `src/app/streaming/idle_timeout.py:12-16`。
2. **spec 点名的 `upstream_request_timeouts.stream_idle`（`src/app/config/schema.py:102`，默认 0）没有任何消费方。** `rg -n "upstream_request_timeouts" src/ --type py` 只有两处命中：定义 `schema.py:295` 与 `handler.py:99`，后者只取 `upstream_request_deadline` 和 `response_header_overrides`。同一对象里的 `response_header`（`schema.py:100`）同样无人读。
3. **旧链路在生产里根本没被服务。** `src/app/cli.py:19,140,165` 只构造 `create_pipeline_app`；`app.server.app_factory`（挂载 `routes/*` 的那个）经 `rg -n "app_factory" src/ tests/ --type py` 复核，只被 `tests/` 引用。所以准确表述是「上游空闲检测在生产链路上完全不存在」，而不是「只接在旧链路」——后者会让读者以为还有一条路在用它。

一个想据此调参的读者会去改一个没人读的键。

**附带观察（非本 spec 引入）**：`src/app/server/handler.py:100-104` 用 `upstream_request_deadline` 作标量、却配 `response_header_overrides` 作按模型覆盖表，与人写文档 `config.example.yaml:292-294`「按模型覆盖的 response_header」的语义不符。建议单独立案。

---

## F6【重要 / 中】§3 的清单不完整，且与既有 live 设计文档失联

§3 的两条事实陈述我逐条复核，**都成立，而且比 spec 说的更彻底**：

- `tcp_keepalive_interval` → `src/app/server/composition.py:66-71` 映射成 `TransportOptions.keepalive_expiry` → `:80` 的 `httpx.Limits(keepalive_expiry=...)`。`rg -n "SO_KEEPALIVE" src/` 零命中，全仓仅 `docs/2604-rewrite/streaming-resilience.md:250` 的设计示例代码里出现。
- `http2_ping_interval` → `composition.py:70` 只用作 `http2 = interval > 0`。我进一步查了传输层：`.venv/.../httpcore/_async/http2.py` 全文无任何 ping 发送逻辑（`h2 4.3.0` 已安装，所以 `http2=True` 本身是生效的，只是永远不发 PING）。**这不是接线遗漏，是 httpx/httpcore 根本没有这个公共能力**，spec 可以把这点补上，因为它决定了「实现」这条路的代价。
- `composition.py:60-81` 这个行号引用准确（`transport_options` 60-72，`build_http_client` 75-81）。

不完整之处：

1. **上游侧还有两个同类死旋钮 spec 没提**：`src/app/config/settings.py:73-74` 的 `upstream_keepalive: int = 15` 与 `upstream_h2_ping: int = 15`，`rg -n "upstream_keepalive|upstream_h2_ping" src/ tests/ --type py` 显示零消费方。加上 §3 点名的两个，上游保活一共 4 个旋钮全是死的。
2. **与既有 live 设计文档失联**。`docs/2604-rewrite/streaming-resilience.md`「上游连接保活」整节已经把这一侧设计完了：给了 `socket_options=[(SOL_SOCKET, SO_KEEPALIVE, 1), (IPPROTO_TCP, TCP_KEEPIDLE, 15), (IPPROTO_TCP, TCP_KEEPINTVL, 15)]` 的具体做法、h2 PING 的做法与「httpx 不暴露公共 API、需在 httpcore 连接对象层接入」的判断，还有配置表 `upstream.keepalive_expiry` / `timeouts.upstream_keepalive` / `timeouts.upstream_h2_ping`。新 spec §3 复述了同样的结论却未引用它，读者无从知道这一侧已有设计。按 `one-authority-allows-contextual-restatement`，这里应当回链。
3. **三套命名互不一致**，spec 未指出：人写文档与 schema 用 `upstream_transport.tcp_keepalive_interval` / `http2_ping_interval`；设计文档用 `timeouts.upstream_keepalive` / `timeouts.upstream_h2_ping` / `upstream.keepalive_expiry`；`settings.py` 里同时存在后两组的残留。

**措辞问题**：§3 末句「这两个名字目前在说谎，怎么处置（实现、**改名**、还是**撤掉**）留给用户裁决」——这两个名字是用户在 `docs/.human-controlled/config.example.yaml:269-277` 亲笔写的（「TCP 保活间隔」「HTTP/2 PING 保活间隔」）。把「改名/撤掉」摆成平等选项，等于提议推翻人写文档。应表述为「这是实现缺口：名字是用户裁定的语义，实现没跟上」。

---

## F7【重要 / 高】§2 的「交付已经开始」未定义，而这正是新读者判不出的那个点

代码里有**三个不同的门**，spec 把它们压成了一个词：

| 门 | 位置 | 语义 | 用途 |
|---|---|---|---|
| `response_started` | `stream.py:174-176` | 首块**被组装出来** | 解除合成计时 |
| `started` | `stream.py:167,181-182,189` | **已有字节写给客户端** | 决定 `elif started: yield PING_FRAME` |
| `DeliverySession.started` | `blocks.py:151-156` | 首批块被 buffer **释放** | 会话状态 |

§2 判据写「一旦交付已经开始（见 §2.2）」，§2.2 写「首个完整块**交付**之前不发保活帧」。一个新读者拿这两句去回答「块已经组装好但被 buffer 扣住，这时该不该发 ping」——查不出答案。而代码的答案是「不发，而且合成计时同时被解除」，也就是 F1。

同样地，「某处该不该打戳」这个问题 spec 给的规则是「任何写往客户端的字节都重置它」，可它没说清判据锚在哪个门上。

**建议改法**：§2 直接把判据锚在 `started`（已向客户端写出过字节）上，并显式写一句「块被 assembler 组装出来 ≠ 交付开始；buffering 策略可能把它扣住任意久」。这一句同时消化了 F1 和 F7。

---

## F8【次要 / 高】§2 判据在 `sse_ping_interval = 0` 时退化，spec 未说明

`stream.py:58` 只在 `interval > 0` 时建 deadline；为 0 时 `_events_with_ping` 的待决 deadline 集合可能整个为空，此后全程静默。人写文档 `config.example.yaml:411-413` 明写「0 = 禁用」。§2 的全称判据「代理**不得**让客户端连续 `client_delivery.sse_ping_interval` 秒收不到任何字节」在 0 处语义崩塌，应补一句「`0` 表示运维主动放弃本条义务」。

`docs/tmp/260820-review-synthetic-start-fix.md` §5 的附带记录里已提过同一点。

---

## F9【次要 / 高】§2 的全称断言在当前代码上成立，但它靠一个 spec 没写出来的结构不变量撑着

**逐条复核 §2「任何写往客户端的字节都重置它——内容帧、`message_start`、终止帧，以及保活帧自身」，结论：成立，没有旁路。**

`_deliver` 里全部 6 个产字节点位：

| 字节 | 位置 |
|---|---|
| 合成 `message_start` | `stream.py:168` |
| `PING_FRAME` | `stream.py:170` |
| `_commit` 产出的 `message_start` + block frames | `stream.py:219-222` → `:178-183` |
| held-back 路径的 `message_start` | `stream.py:188` |
| `finish()` 后的 block frames | `stream.py:191-192` |
| terminal frames | `stream.py:196-200` |

全部经 `stream_delivery` 的 `async for chunk in inner: last_write.at = loop.time(); yield chunk`（`stream.py:123-125`）打戳。外层同样干净：`_tracked_delivery`（`pipeline_app.py:358-367`）与 `_counted_upstream`（`:347-355`）都是纯转发不造字节，`_AccountedStreamingResponse.__call__`（`:340-344`）只加 `finally`。

节拍也实测正确：探针 `policy=block`、`interval=1`、3s 窗口 → 3 个 ping、最大间隔 1.00s，无漂移无双发。`uv run pytest tests/unit/test_stream_delivery.py tests/unit/test_block_delivery.py tests/unit/test_http_client_build.py -q` → 40 passed。

**但 spec 只写了结果，没写撑住这个结果的不变量。** 真正成立的原因是「下游字节的唯一出口是 `stream_delivery` 里那一个 `yield`」。将来任何在 `stream_delivery` **外层**注入字节的包装器（例如给 `_tracked_delivery` 加一个错误帧、或在 `_AccountedStreamingResponse` 里补一个终止帧）都会静默破坏计时基准，且不会有任何测试变红。`stream.py:109` 的 docstring 提到了「A seventh such place would otherwise have to remember to stamp it」，但那只覆盖 `_deliver` 内部新增点位，不覆盖外层注入。建议把这个不变量本身写进 §2。

**两条观察（当前部署下无影响，记录备查）**：打戳发生在 `yield chunk` **之前**，记的是「交给下一环的时刻」而非「落到 socket 的时刻」；且整条链是拉取式的，消费端不来拉就不会产生 ping。默认 uvicorn 部署下两者都不构成风险。

---

## F10【次要 / 高】文字规范：无问题

- **标点**：剥离行内代码后全文扫描（`/tmp/probe_keepalive/punct.py`），7 处命中全部是 Markdown 标题编号（`## 1.`）与有序列表标记（`1.`）以及分隔线 `---`，无一是真实违例。中文句内无半角 `,.:;?!()`，无全角字母数字，`——`／`「」`／`（）` 使用正确。
- **硬折行**：56 行中每个段落均为完整一行（最长 197 字符），符合 `no-hard-wrap`。
- **术语一致**：全文统一「保活帧 / 注释帧 / 块级交付 / 下游 / 上游 / 计时基准」，标题与 §2、§3 小节名对齐，与 `stream.py:7` 新增的模块 docstring 用词一致。
- 唯一小建议：§2.1 论证「发注释帧而不发 `ping` 事件」，§2.2 又说合成时发 `message_start`（而不是注释帧）——两个「不是注释帧」的取舍理由完全不同（一个嫌 `ping` 事件承诺多，一个嫌注释帧承诺少）。建议在 §2.2 首句点一句「这与 §2.1 是方向相反的两个取舍」，否则读者容易读成自相矛盾。

---

## F11【次要 / 中】文档位置与状态标签

项目约定：`docs/` 放 live conclusions，`docs/agents/<topic>/` 放 in-flight development documents。这份自称「状态：规范（normative）」的文件落在 in-flight 目录。若确实要作为规范固定，位置与约定不符；若留在 `docs/agents/`，状态标签宜降为「候选规范」。这条交主会话裁决，不构成技术缺陷。

---

## 汇总处置建议

必改（挡住「固定为规范」）：

1. **F1** — §2.2 补第 3 条未覆盖窗口（`full` / `until-tool-use` 下无上界），并修正第 2 条「上界是 240s」的说法。
2. **F3** — §2.2 第 1 条改定性为「与人写文档冲突」并回链 `config.example.yaml:404-409`；「既有裁决」降级为「评审偏好，未经用户裁决」。
3. **F7** — §2 判据把「交付已经开始」锚定到「已向客户端写出过字节」，并写明「块被组装 ≠ 交付开始」。

应改（事实错误）：

4. **F2** — §2.2 第 1 条删「也没有上限」，改为「上限是 `upstream_request_deadline`（默认 1200s），远超客户端 300s 天花板故无效」。
5. **F5** — §4 的 `stream_idle` 改指 `app/config/settings.py` 的 `TimeoutConfig.stream_idle`，并说明 schema 侧同名项无消费方、旧链路在生产未被服务。
6. **F4** — `hedge` 从 §4 挪进 §2.2。
7. **F6** — §3 补上 `settings.py` 的另两个死旋钮、回链 `docs/2604-rewrite/streaming-resilience.md`、指出三套命名不一致、把「改名/撤掉」措辞改为「实现缺口」。

宜改（完备性）：

8. **F8** — §2 补 `sse_ping_interval = 0` 的退化说明。
9. **F9** — §2 把「下游字节唯一出口」这个结构不变量写出来。
10. **F10** — §2.2 首句点明与 §2.1 是方向相反的两个取舍。

交主会话／用户：

11. **F11** — 文档位置与状态标签。
12. 三条与本 spec 无关、建议单独立案的观察：`direct_driver/base.py:223-224` docstring 对流式请求为假；`handler.py:100-104` 把 `upstream_request_deadline` 配 `response_header_overrides`；上游保活 4 个旋钮全死这件事本身要不要立 issue。

---

## 附：评审期间工作树被并行会话改动

评审开始时 `HEAD = a374f39` 且工作树干净；收尾时 `git status --short` 显示有并行会话的未提交改动，另有一份同伴报告 `docs/agents/delivery-keepalive/review-async-correctness.md`（untracked）。改动内容：

- `src/app/pipeline/delivery/stream.py:123-126` 把 `last_write.at = loop.time()` 从 `yield chunk` **之前**挪到**之后**，并加了解释性 docstring（理由：`StreamingResponse` 先拉 chunk 再 `await send`，生成器恢复时该 chunk 才真正交出去）。
- `tests/unit/test_stream_delivery.py` 新增两条测试：消费者被取消时 `CancelledError` 要透出、上游中途抛错要透给调用方。

对本报告的影响，逐条核过：

- **F1 不受影响，已在改动后的工作树上重跑复现**，三行数字与 HEAD 上完全一致（`block` 3 pings / `until-tool-use` 与 `full` 各 0 pings、首字节 3.22s）。该缺陷的成因在 `response_started` 与 `started` 两个门，那段代码未被触碰。
- **F9 里「打戳发生在 `yield chunk` 之前」这条观察，对评审对象 `a374f39` 成立（`git show a374f39 -- src/app/pipeline/delivery/stream.py` 可复核），但工作树里已经被同伴改掉了。** 记在这里以免读者对着当前文件找不到。F9 的主体结论（全称断言成立、靠「唯一出口」不变量撑着、spec 未写出该不变量）不受影响。
- 其余各条针对的是 `docs/agents/delivery-keepalive/spec.md` 与配置/接线现状，均未被这次改动触及。

---

## 是否可以固定为规范

**不能照现状固定。** 但缺陷集中在枚举完备性、事实精度与术语定义，不在设计判断上——§1 的两侧分离论证、§2 的「以下游写出为唯一计时基准」、§3 的「上游侧名不副实」这三条骨架经我复核全部成立，代码实现（`a374f39`）与 §2 的核心断言一致且实测节拍正确。修掉 F1–F5、补 F7，这份 spec 就可以作为规范固定下来。

需要特别提醒主会话的一点：**F3 牵涉人写文档的权威等级**。`docs/.human-controlled/config.example.yaml` 关于 `synthesized_response_headers_after_sec` 的窗口定义（「上游都没有响应头」）与实现（响应头到达之后才起算）是方向性冲突，`260820-review-synthetic-start-fix.md` §9 已经把它交回主会话且至今未裁。在用户裁决之前，spec 不宜用「既有裁决」把现实现的做法固化下来。
