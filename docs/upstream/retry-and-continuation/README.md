# 上游请求的重试与续写

**读这个目录从 [`status.md`](status.md) 开始**——那里是当前实现状态与分阶段路线。未闭合与待查项在 [`deferred.md`](deferred.md)。

## 权威在哪

**唯一权威是用户亲笔的 [`docs/.human-controlled/upstream-retry-and-continuation.md`](../../../../docs/.human-controlled/upstream-retry-and-continuation.md)。** 本目录的一切都是它的实现记录、证据与推论；任何一句与它相违背的，以它为准，并且要来改本目录而不是改它。

本目录**不复述**该文档的裁决，只在需要上下文时引用并指回。

## 这个主题回答什么

一次发往上游的模型请求失败了，接下来做什么。答案分两层：

1. **先判这次结束是不是上游造成的。** 客户端断开、进程优雅关闭、代理自己的保护机制触发，都不是上游失败，不进重试。
2. **再判客户端已经看到了什么。**
   - **还没交付过完整块** → 代理端**无痕重试**。客户端一无所见，第二次尝试可以无痕替代第一次。全协议生效。
   - **已经交付过至少一个完整块** → **MCP-driven 续写**。把错误合成为一个 `tool_use` 块，调用 MCP 工具 `turn_interrupted(num_messages, category, message)` 交回客户端；客户端执行它、拿到「继续」的指令、自然地发起下一轮。仅在 **anthropic-messages 客户端请求**上生效。

第 2 层的关键取舍是：**承载续写的是客户端自己的对话历史，不是代理构造的请求。** 这一条决定了它和被放弃的代理内续写之间的全部差别——见 [`archive-proxy-side-continuation/README.md`](archive-proxy-side-continuation/README.md)。

## 目录

| 路径 | 是什么 |
|---|---|
| `status.md` | **活文档**。当前实现状态、分阶段路线、每阶段的验证方式 |
| `decisions.md` | 裁决记录：哪条写进了人写文档、哪条只存在于讨论中、哪条其实是本项目的推论、哪条还没裁 |
| `deferred.md` | 未闭合、待查、以及明确不做的 |
| `archive-proxy-side-continuation/` | 被裁决放弃的代理内续写方案，及其三轮评审。原件逐字保留 |
| `reports/` | 本主题的调查报告原件 |

## 支撑本主题的实测证据

下面每条都来自真实录制或代码直读，不是推断。完整报告在 `reports/`。

| 事实 | 证据等级 | 出处 |
|---|---|---|
| 撞 `max_output_tokens` 时，上游为被截断的 item 发出 `output_item.done`——**观测到的 20/20 例皆如此** | 录制，n=20，逐例。**样本边界**：2026-08-04～08，模型 `gpt-5.6-sol`／`gpt-5.6-terra`，`incomplete_details.reason` 仅 `max_output_tokens` 一种。随时间或模型变化未排除 | `reports/260821-max-tokens-block-completeness.md` |
| 因此被截断的那个 item 自己会被交付成一个完整块 | **代码事实**（`assembler.py:231-232` → `_close`：`output_item.done` 是块完成的唯一判据），在上一行成立的前提下 | 同上 |
| 被截断的 item 在 `output_item.done` 上带 `status:"incomplete"`，完整的带 `"completed"`；**reasoning item 没有这个字段**（与正常收尾的 reasoning item 键集逐字相同，已做正样本对照） | 录制，`status:"incomplete"` 实测 15 次（4 次在 `function_call` 上） | 同上 + `evidence/probe-reasoning-item-control.py` |
| Responses 腿的终止只有 `response.completed`(64351) 与 `response.incomplete`(20)；`response.failed`／`cancelled`／上游 `error` 帧**各 0 次** | 录制，134336 个 operation | `reports/260821-upstream-termination-reasons.md` |
| `incomplete_details.reason` 20/20 全是 `max_output_tokens`，**没有第二个取值** | 录制 | 同上 |
| Anthropic 腿实测到的 `stop_reason`：`tool_use`(124927)、`end_turn`(8290)、`max_tokens`(24)、`refusal`(1)。`model_context_window_exceeded` **零观测** | 录制 | 同上 |
| 上下文超限走 HTTP 400，**两条腿形态不同**：Anthropic 腿 `error.code=model_max_prompt_tokens_exceeded` 且 message 带数字；Responses 腿 `error.code=invalid_request_body`（与其他参数错误共用，不可据以区分）且 message **无数字** | 录制，48 例一手 | `reports/260821-context-limit-400-examples.md` |
| Claude Code 的 `stop_reason` schema 是 `string().nullable()` **无枚举**，未知值不报错、直接跳过 | 代码事实，CC 2.1.226 | 同上 |
| Claude Code 对不认识的工具名发回 `No such tool available` 的 tool_result，**不崩溃**，对话继续 | 代码事实 | `~/.claude/skills/debugging-claude-agent-tools/reference/source-symbols.md:21` |
| 前身 `copilot-api-js` 的 `max_tokens` 处理**只接在 Anthropic 直连腿**，Responses 腿的谓词零调用点；官方 `vscode-copilot-chat` 对被截断的 tool call 是静默丢弃 | 代码事实（八个参考仓） | `reports/260821-reference-projects-max-tokens.md` |
| live 链路的重试**只存在于上游响应头到达之前**，无退避无 jitter；**读流中断零重试** | 代码事实 | `reports/260821-upstream-error-handling-survey.md` |

## 本仓实际发出的 MCP 工具调用（给改 MCP server 那一侧看）

MCP server 在另一个仓（插件 `ghc-api-proxy-helper`），本会话够不到那位同伴。**本节是本仓发出方的一手契约，从代码直读，是两侧对齐的依据**——发出方的实际字节即权威，`decisions.md` 第四节第 1 条的「待对齐」在这里给出取值。

合成点 `src/app/pipeline/hand_over.py` 的 `hand_back_block`（2026-08-22 由 `b973ed0` 从 `src/app/server/pipeline_app.py` 移出），发出的块：

```json
{
  "type": "tool_use",
  "id": "toolu_<uuid4 前 24 个 hex 字符>",
  "name": "<配置项 upstream_request_retry.auto_retry_tool_call_full_name 的值>",
  "input": {"num_messages": 0, "category": "…", "message": "…"}
}
```

`name` 的默认值是 `mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted`（`src/app/config/schema.py:157-159`）。**这个字符串对接收端是载重的**：Claude Code 对插件提供的 MCP server 命名成 `mcp__plugin_<插件名>_<server 名>__<工具名>`，所以那一侧必须把插件叫 `ghc-api-proxy-helper`、server 叫 `auto-retry`、工具叫 `turn_interrupted`，三段全对才匹配得上。三段里任一段不同，线上表现是**每次交接都走「工具未声明」那条路**——不报错、不拦截、块照发，客户端回一个 `No such tool available`，对话继续但续写机制静默失效。

| 字段 | 取值 |
|---|---|
| `num_messages` | 客户端入站 body 的 `messages` 长度（`client_message_count(inbound_payload)`）。**不是**上游请求的长度——Responses 腿上一条 Anthropic 消息会变成若干 item。非 list 时（含缺键）为 `0` |
| `category` | 上游把这一轮截短、并非错误时：**就是那个 `stop_reason`**，默认配置下唯一可能的值是 **`max_tokens`**。是错误时：`network` / `upstream` / `auth` **三者之一**，外加结构上今天不可达的 `internal` |
| `message` | **一句代理合成的诊断，不是异常原文**（2026-08-23 起，提交 `aac348e`）。格式与取值见下 |

### `message` 的格式（2026-08-23 起，本节对应 `e2cb70b`）

> **本节与代码的同步点是提交 `e2cb70b`。** 前一版本节写于 `aac348e` 时点，`79428bb` 改了筛选规则之后就过期了，独立复评（`260823-review-handover-message-delta.md` M2）指出「命名为跨仓权威的文档逐字描述旧算法、并给出三条已不成立的示例」。**改 `describe_error` 的人必须同时改本节，并把这行锚点换成新提交。**

改之前它是 `str(error)`（非错误时是 `stop_reason`，与 `category` 逐字同值）。**那个值在真实流量里读不出东西**：MCP server 日志当时积累的 4 条记录全部是 h2 事件的裸 `repr`，其中 3 条 `error_code:0`、1 条 `error_code:8`，而区分二者的那个词是一个 `IntEnum`，`str()` 打出来是数字。同一轮调查还测出另外三种更糟的形态（`.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md`）：真实连接重置的 `httpx2.ReadError` 的 `str()` **是空串**，裸 `h2.ProtocolError()` 也是空串，而 `h2.StreamClosedError(3)` 的 `str()` 是裸数字 `'3'`——看着像一条真消息。

现在的形状是 `<对失败的描述> [request <request_id>, attempt <N>]`。

错误分支的描述由 `describe_error` 生成，沿 `__cause__` 自外向内走（`__cause__` 为 `None` 且未被 suppress 时才退到 `__context__`；判据是 `is not None` 而非真值，因为异常子类可以定义 `__bool__`）。**一环是否出现，按它有没有说出新东西决定**，三种情形：

| 这一环 | 输出 | 为什么 |
|---|---|---|
| 文本是新的 | `module.QualName: 文本` | 常规情形 |
| 文本已出现过，但类名是新的 | 只有 `module.QualName` | 否则 `RuntimeError('denied') from PermissionError('denied')` 只剩外层，丢掉唯一说明「哪一类失败」的词。h2 事件经 httpcore→httpx 映射时文本也重复，但类名一并重复，那一环整个丢弃 |
| 没有文本 | 只有 `module.QualName`，且**仅当此前还没有任何一环带过文本** | 两个 deadline 守卫外面裹着 `TimeoutError() -> CancelledError()`，那是 `asyncio.timeout` 的构造方式而不是这一轮发生的事；外层已经点名是哪道守卫了，再附上 `CancelledError` 会把一个已明确的超时读成取消。而真实连接重置的外两环是静默的，那时内层类名就是仅有的线索 |

类名的「新鲜」按 `__qualname__` 判，不按完整点分路径——`httpx2.ReadError` 套 `httpcore2.ReadError` 是同一个失败被两个库各描述一遍，正是该合并的情形。两个真正无关模块里的同名异常也会被合并，这是有意取舍，且迄今只在构造反例里出现过。

链上出现 `h2.events.ConnectionTerminated` / `StreamReset` 对象时（httpcore 是 `RemoteProtocolError(event)`，对象比文本多活一环），额外附一段括注，`error_code` 读事件自己的枚举而不是本仓维护的表。**这条依赖是静默降级的**：复评实测把 event 在进入 httpcore2 异常前转成字符串（模拟未来依赖不再把对象放进 `args`），结果括注消失而原始 repr 完整保留。

实测输出（每一种都对应报告里判定为可达的形态，由当前代码直接生成）：

| 触发 | `message` |
|---|---|
| h2 GOAWAY（日志里 3 条） | `httpx2.RemoteProtocolError: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None> (HTTP/2 GOAWAY from upstream, error_code=NO_ERROR) [request a1b2c3d4, attempt 1]` |
| h2 RST_STREAM（日志里 1 条） | `httpx2.RemoteProtocolError: <StreamReset stream_id:1011, error_code:8, remote_reset:True> (HTTP/2 RST_STREAM from upstream on stream 1011, error_code=CANCEL) [request a1b2c3d4, attempt 1]` |
| 真实连接重置 | `httpx2.ReadError; caused by anyio.BrokenResourceError; caused by builtins.ConnectionResetError: [Errno 104] Connection reset by peer [request a1b2c3d4, attempt 1]` |
| HTTP/1.1 提前关闭 | `httpx2.RemoteProtocolError: peer closed connection without sending complete message body (received 19 bytes, expected 1000) [request a1b2c3d4, attempt 1]` |
| attempt 时限 | `app.streaming.deadline.StreamDeadlineError: attempt exceeded its deadline [request a1b2c3d4, attempt 1]` |
| 空闲超时 | `app.streaming.idle_timeout.StreamIdleTimeoutError: No stream item received for 300s [request a1b2c3d4, attempt 1]` |
| 裸 `h2.ProtocolError` | `h2.exceptions.ProtocolError [request a1b2c3d4, attempt 1]` |
| `h2.StreamClosedError(3)` | `h2.exceptions.StreamClosedError: stream 3 [request a1b2c3d4, attempt 1]` |
| `max_tokens` 交接（非错误） | `upstream ended the turn before it was finished: stop_reason=max_tokens [request a1b2c3d4, attempt 1]` |

**给接收端的四点**：

- **`message` 现在恒为非空**。改之前它可以是空串，那是接收端最难处理的取值。
- **方括号里那两项是代理侧的身份，不是上游说的话。** `request_id` 是本仓请求追踪的主键——本仓的日志按它记着模型、字节数与上游连接标识（`upstream_conn`），而 MCP 日志此前没有任何字段能连回来。**刻意只带这把钥匙、不复制它指向的事实**，免得两处各存一份漂移。`attempt` 是例外，因为它单独改变这条线的读法，而客户端那侧根本看不见它（那边的打转判据只有 `num_messages`）。
- **单行、有长度上限。** 每一环文本超过 240 字符时截断并写明还剩多少（`… (+N more chars)`）；链最多走 6 环，**走满即截断并追加 `; caused by … (chain continues past 6 links)`**——不静默，因为「链到此为止」和「链被砍断」否则同形。
- **`message` 不供解析。** 措辞会随可读性改良而变；接收端的行为只应依赖 `category` 与 `num_messages`。复评逐行核过接收端确实如此（`server.py:65-68` 只用这两项驱动 loop 与 reply，`message` 仅在 `:69-75` 传给 `build_record`、`:103` 写进 JSONL），所以本次改动不可能改变 retry 行为。

对应的插件侧工具描述（`~/.claude/my/ghc-api-proxy-helper/src/auto_retry/server.py`）原先写的是「上游错误消息原文，verbatim」，与上面这个形状已经不符，2026-08-23 一并改掉。

**`num_messages` 该怎么读（本仓建议，仍待对齐）**：按「**同一数值重复出现**」判无进展，**不要**按「数值有没有增长」判。每次交接后客户端会 +2（一条 assistant 轮次 + 一条 tool result），但**并行子智能体与主会话共享同一个 MCP server 进程，调用会交错**——A 会话的 12 后面可能跟着 B 会话的 6，按「有没有增长」判会把 B 的正常调用误判成无进展而中止，反过来 A 的重复 12 也可能被 B 的数值掩盖而漏判。见 `decisions.md` 第四节第 3 条，那是本节写下时仍打开的待对齐项。

三条会绊到人的：

- **`category` 的错误取值经过重试分类器，不是对异常原地分类。** 一次传输撕裂原地分类是 `internal`（它不是 `OSError`），而重试路径叫它 `network`——走同一个映射是为了让两边对同一个事件说同一个词。
- **`internal` 今天发不出来，但接收端仍应兜住它。** `CATEGORY_FOR_REASON`（`hand_over.py:21-25`）确实有一个落 `internal` 的默认分支，但 `RetryReason` 只有三个成员且三个全在表里，而 `stream.py` 保证「带 error 走到合成」之前 `reason` 必非 `None`——所以那一格结构上不可达，**不要因为它出现在这张表里就以为线上见过**。它是防御性的：将来谁给 `RetryReason` 加了成员却忘了改表，才会真的发出 `internal`。（**2026-08-23 存疑**：`260823-handover-error-shapes.md` §2.2(g) 认为裸 `h2.exceptions.ProtocolError` 与 framing 层 bug 都能带着 `reason is None` 走到合成，那样 `internal` 就是可达的。两说未对账，以报告的代码直读为准去复核，本条留作待查。）
- **`max_tokens` 是 Anthropic 的拼法，不会出现 `max_output_tokens`；而且把配置改成 `max_output_tokens` 也不会生效。** 上游 Responses 说的是后者，两条路径都在**门之前**就归一了（`src/app/pipeline/delivery/formats/openai_responses.py`、`src/app/pipeline/translation_driver/responses.py`），所以那个原始拼法压根活不到比较的那一步。异源评审的一手实测（含证伪对照：把 `hand_over_stop_reasons` 配成 `{"max_output_tokens"}`，合成一次都没触发）见 `reports/260822-review-mcp-contract-and-deadline-order.md` F6/F11。

**工具未声明时只告警不拦截**：客户端没在 `tools` 里声明这个名字，本仓打一条 `auto_retry_tool_not_declared` 警告日志，**照发不误**。用户 2026-08-21 裁决，人写权威原文在 `docs/.human-controlled/upstream-retry-and-continuation.md:37`。

## 相邻主题

- [`../h2-goaway/`](../h2-goaway/) —— GOAWAY 打掉在飞流的机理诊断，已收口。它的「三条路的裁决」欠账由本主题接手。
- [`../../anthropic-responses-bridge/`](../../anthropic-responses-bridge/) —— 桥 spec，冻结中。本主题的 wire 不变量指回它。
- G1「让活跃链路认出上游发来的错误事件」（分支 `fix/upstream-error-events`，同伴在飞）—— 本主题依赖它：`stop_reason` 原样透出与上游 `error` 帧不再静默丢弃，都要它先落地。
