# 上游流级 RST_STREAM(CANCEL) 打掉在飞请求 —— 是否应修的诊断

**日期**：2026-08-22
**触发**：用户在另一台机器上观察到一条 `[FAIL]` + 一份 `Exception in ASGI application` traceback，要求分析并判定是否应修。
**性质**：一次性诊断报告（点时记录）。结论待用户裁决后再落进相应主题的活文档。
**本机 HEAD**：`8f654b4 feat: wire the replay, and give one client request one retry budget`

**评审**：本文经两轮异源独立评审，**均判 needs-fix**，本文是按其结论重写后的第三稿。
- GPT：`260822-review-streamreset-diagnosis-gpt.md`（4 处分歧 + 1 处遗漏）
- Opus：`260822-review-streamreset-diagnosis-opus.md`（4 major + 5 minor + 6 项查证无误；**用实测证伪了初稿的一条核心论断**）
- 两份评审彼此也有一处实质冲突，见 §3.1——那正是唯一真正需要用户裁决的问题。

> **工作树状态提醒**：评审期间有并行会话改动了 `src/app/pipeline/delivery/stream.py`、`assembler.py`、`server/handler.py`。本文所有行号与引文均对 `git show HEAD:` 复核过，**不是工作树版本**。同伴那处改动落在 `ClientDeadlineError` 分支（去掉了 `client_has_bytes` 门），与本次撕断路径无交集。

---

## 0. 结论速览

| # | 观察到的行为 | 判定 | 动作 |
|---|---|---|---|
| 1 | `[FAIL]` 行 + 异常原文 | **符合冻结规格，不是缺陷** | 不修 |
| 2 | 完全没有尝试重放 | 部署版本上是真缺陷；**HEAD 已修，但救不了这一次** | P0：那台机器升级 |
| 3 | 撕断后直接抛异常，客户端只拿到半截流 | **有两份权威文档各自裁决过，且互相冲突；两种实现都不存在** | P1：需用户裁一次，然后一次做完 |
| 4 | `StreamEnding.COMPLETE` 被当成失败抛掉 | **真 bug**，窄而确定，与本次事故无关 | P2：独立小修 |
| 5 | ASGI traceback | 是 3 的副产品，**不单列**（改 `break` 即同时消失） | 随 P1 |

**不要把这次概括成「代码处置基本正确」。** `ABANDON` 只是「代理端不能无痕重放」这一个内部裁决，它不等于对客户端的交付行为已经完备。

---

## 1. 可判定的事实

### 1.1 上游做了什么

```
httpcore2.RemoteProtocolError: <StreamReset stream_id:3, error_code:8, remote_reset:True>
```

- **流级** RST_STREAM，`error_code=8` 即 h2 的 `CANCEL`，`remote_reset=True` 表示帧由对端发出。
- **不要与 2026-08-20 那次混为一谈。** 那次是**连接级** `<ConnectionTerminated error_code:0, last_stream_id:2147483647>`（GOAWAY，一帧打掉四条在飞流）。本次只死了 stream 3。异常类名相同，机制不同。
- **归一化链有一步承重，必须写出来**：literal `httpcore2.RemoteProtocolError` **不在** `_CONNECTION_ERRORS`，直接归一化得 `None`，结论会翻转。生产路径成立是因为 `httpx2` 的 `map_httpcore_exceptions` 先把它映射成以原异常为 cause 的 `httpx2.RemoteProtocolError`——用户贴的 traceback 最后一行正是后者。
- **谁发的、为什么发，不分析。** 用户 2026-08-20 已裁决这类问题在我方原理上不可判定（`.dev/docs/upstream/h2-goaway/findings.md`「不可知项」段）。

### 1.2 我方当时的位置

- 48.0s；上行 593.2KB；自上游收到 13.1KB（`↓` 按本项目约定是「自上游收到的字节」）。
- **这次走的是 Anthropic 上游腿，不是 Responses 腿。** 判据：`REASONING_WORD = {ANTHROPIC: "think", RESPONSES: "reason"}`（`request_log.py:33`），行上是 `think`；`dialect_for`（`handler.py:517-529`）只在 `route.target_format is WireFormat.OPENAI_RESPONSES` 时返回 `RESPONSES`，`assembler_for`（:546-553）据此分派。所以闭合那个块的是 `AnthropicAssembler`（`assembler.py:187`），**不是** `ResponsesAssembler`（:320）。
  > 初稿引了 `:320`，读反了。这一点承重——§3.1 的 spec 适用性问题就建立在它上面。
- `think(enc:1)`：assembler 闭合并记录了 1 个加密 reasoning 块。
- 行上无 stop_reason 词，而 `trace.absorb(terminal)` 无条件跑（`think(enc:1)` 能打印即证明它跑了），所以**未见 terminal event** 成立。

### 1.3 部署的是哪个版本 —— 只能定到区间

部署树的 `stream.py` / `keepalive.py` 与下面**五个**提交内容完全相同：

```
a68672c  b64003e  fa628e1  767d0f2  9aa31f9
```

**能确定的只是：早于 `8f654b4`（replay 接线）。定不到某一个提交，也不能说「落后 6 个提交」。** 另外 traceback 里的 `keepalive.py:126` **鉴别力为零**——该行在候选区间与 HEAD 上逐行相同。真正有鉴别力的是 `stream.py` 的 240/270（HEAD 为 241/283）与 `stream_delivery` 帧的 206（HEAD 为 207）。

> **初稿的错误，记在这里而不是删掉**：初稿断言「精确对应 `9aa31f9`」并称「不是推测」。错因是扫描用了 `git log -- src/app/pipeline/delivery/stream.py`，它**只列改动过该文件的提交**，于是四个「继承同一份文件、自己没碰它」的提交在扫描里根本不可见。正确口径是遍历 `git rev-list` 逐 revision 取行内容。这与记忆中「归因写下前先核 `--stat`」是同一形状的错：**归因错比事实错更难被发现**。

---

## 2. 逐条判定

### 2.1 `[FAIL]` 行 —— 符合规格，不修

`.dev/docs/tui/spec.md:74` 明写「上游撕断（reset、读错误、转换异常）→ `[FAIL]` + `stream failed before a terminal event: <异常原文>`」。原文照抄也是刻意的（`pipeline_app.py:_ending()`：「It is the only account of what went wrong that exists anywhere」）。**按预期工作。**

### 2.2 没有尝试重放 —— 部署版本上是真缺陷，HEAD 已修，但救不了这一次

**部署版本上**：候选区间的五个提交，`pipeline_app.py` 都没有把 `ReplaySupport` 传给 `stream_delivery`。于是 `replay is None` 恒真，第一处 `raise torn`（正是 270 行）无条件击发——**重放机制在那台机器上从未被咨询过**。这正是 `.dev/docs/upstream/h2-goaway/deferred.md` 第 3 条登记的「REPLAY / ABANDON 仍然要接」。

**HEAD 上**：`8f654b4` 接线了，实测该异常归类为 `RetryReason.NETWORK`（可重放），于是进 `decide_stream_ending`。两种位置的实测裁决：

| 位置 | 裁决 |
|---|---|
| `downstream_opened=False, committed_blocks=0` | **`replay`** |
| `downstream_opened=True, committed_blocks=1` | `abandon`（`response opened with content already delivered`） |

**这次属于第二行。** 依据：默认 `client_delivery.buffering_policy = "block"`（`schema.py:269`），块一闭合即释放。两位评审各自端到端复现了两种策略的差别：

```
policy=block  reopened=0  raised=RemoteProtocolError  message_stop=False
policy=full   reopened=1  raised=none                 message_stop=True
```

> **证据等级：默认配置下强到可以据此行动；脱离生产配置只是条件结论。** 若那台机器设了 `full` / `until-tool-use`，块被扣住，HEAD 上这次反而会 replay 成功。**但改配置不是修复**——`full` 延迟所有块、抬高内存驻留，且并行会话此刻正在修「非 `block` 策略下客户端拿到零字节」的另一个形态。

**重试预算未被错误消耗**（已查证）：`ledger.take()` 只在 `not downstream_opened` 分支调用，本次走的 abandon 分支不碰账本。

**所以升级的价值不在这一次**，而在于让「撕断发生在首块交付之前」这一整类不再白白掉线——那一类目前在那台机器上 100% 直接失败。

### 2.3 撕断后客户端拿到什么 —— 现状与两个候选

**现状**：`raise torn` 直接跳出函数，末尾那段 `if not terminal.seen: yield error_frame(...)` **永远到不了**。于是形成分界：干净 EOF 无 terminal → 有带内 `error` 帧；被撕断 → 什么都没有。客户端侧是 HTTP 200 + 半截 SSE + `httpx.RemoteProtocolError`，**读不出发生了什么，也分不清是上游 RST 还是自己按了 Esc**。

> **初稿在这里犯了本次最实质的一个错，必须记下。** 初稿称「单纯吞掉异常会造成回归：改成 `return` 会给客户端一个干净的流结束，截断与成功完全同形」，并据此断言 P1/P2 存在顺序依赖。**Opus 评审用实测证伪了它，我复核后确认证伪成立**：
> - **它排除的是错的候选。** 正确的改法是 `break` 而不是 `return`。`break` 退出 `while True` 后落到 `stream.py:299` 往下，那里已经有现成的处理：`session.finish()` 释放扣留的块 → `if not terminal.seen:` → 发出现成的 `incomplete_responses_stream` 帧。评审在 HEAD 副本上实测 `block` 与 `full` **两档都产出该帧**，且 `full` 档顺带把扣留的块也交付了（6 chunk vs 现状 0 chunk）。
> - **连 `return` 也不与成功同形**：成功以 `message_delta` + `message_stop` 结尾，`return` 一个都不发。而初稿援引 STR-04 的「不得再发 `message_stop` 冒充成功」来支持自己，**方向是反的**——那条禁的是「发出」`message_stop`。
> - ⇒ **P1 与 P2 不存在顺序依赖；一个关键字同时做完两件事。**

**但真实代价存在，且初稿与该评审的 6.2 都没算到**（评审 6.3 补上）：`break` 之后 `_tracked_delivery` 的 `except Exception` 不再击发，`accounting.failure` 丢失、`drained` 置真，`[FAIL]` 的 detail 从异常原文退化成泛化文案：

```
HEAD(raise): 'stream failed before a terminal event: <StreamReset stream_id:3, error_code:8, remote_reset:True>'
break 档   : 'upstream stream ended without a terminal event'
```

这正撞上 §2.1 引的那句 docstring。**所以 `break` 必须配一个「把 tear 的原文另行送进 accounting」的小改动**，否则是拿运维可观测性换客户端可观测性。

### 2.4 `StreamEnding.COMPLETE` 被当成失败抛掉 —— 真 bug，与本次无关

`decide_stream_ending()` 有三格（`COMPLETE` / `REPLAY` / `ABANDON`），但 `_deliver()` 写的是：

```python
if verdict.ending is not StreamEnding.REPLAY:
    raise torn
```

**`COMPLETE` 与 `ABANDON` 被折叠成同一条路。** 实测 `decide_stream_ending(terminal_seen=True, downstream_opened=True, committed_blocks=1, reason=NETWORK)` → `complete`，而 caller 仍 `raise torn`。评审端到端复现：上游依次发完整 text block、`message_delta(end_turn)`、`message_stop`，然后抛 reset，结果 `terminal_seen=True stop_reason=end_turn raised=RemoteProtocolError message_stop_delivered=False`——**代理手里已经攒齐了完整回复，却把它当成传输失败丢了。**

**次生危害（两份评审均未提，本文补）**：这种情况下 `_StreamAccounting._ending()` 的第一支只看 `self.failure is not None`、不看 `terminal.seen`，会无条件打出 `stream failed before a terminal event`——而 terminal event **明明已经收到**。日志行会说一句假话。这与 G1 计划 §0.3 提醒的「发了带上游原话的 error 帧、日志行却说没有终止事件」是同一类自相矛盾。

**不修这次事故**（本次确未见 terminal），但方向相反且更值：它把本来能成功的请求救回来。

### 2.5 ASGI traceback —— 不单列

`lifecycle/adapter.py:403` 有同型先例（「对一个计划内的普通事件打出 traceback」），那次修法是「答复而不是抛」；这里做不到（响应头已发，200 已定死）。但按 §2.3，**改 `break` 之后 traceback 自然消失**，无需单独立项。

**边界必须守住**：只有「被代码明确识别、且已转成协议 ending」的分支才 `break`。未被识别的异常（assembler/conversion bug、`BufferCapExceeded` 等本地失败）**继续 raise，traceback 是它们唯一的完整诊断**。不要把「消 traceback」泛化到所有 `raise torn`。

---

## 3. 需要你裁决的那一件事

### 3.1 两份权威文档对同一格给出了不同的线上结果

两位评审在这里实质冲突，而冲突的根源是**两份文档都裁决过这一格，答案不同**：

| 来源 | 权威性 | 对「已交付完整块之后中断」的裁决 |
|---|---|---|
| `docs/.human-controlled/upstream-retry-and-continuation.md`「MCP-driven 合成续写」 | **用户亲笔**，2026-08-21 | 合成 `tool_use` 块调用 `mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted(num_messages, category, message)` 返回给客户端，由客户端续写 |
| `.dev/docs/anthropic-responses-bridge/spec.md`「Error 契约」:385、「SSE envelope 契约」:289 | 智能体撰写，标 **`FINALIZED`**，自述「行为 oracle」，基线 commit `ed77c9d`（2026-08-07） | commit 后发生错误 → 发一个 Anthropic SSE error terminal，关闭 stream，不发成功 terminal |

两者对本次这一格给出的客户端观感截然不同：前者让这一轮**看起来正常结束**（客户端调 MCP 工具后续写），后者让这一轮**明确失败**。

**我的读法（倾向，不是替你裁）**：人写文档赢，理由有二——它是用户亲笔且更晚（2026-08-21 vs 2026-08-07 基线）；`.dev/docs/upstream/retry-and-continuation/decisions.md` 已把它逐条落成裁决台账。spec 的 SSE error terminal 则退为**兜底**：适用于 MCP 机制覆盖不到的位置（非 anthropic-messages 客户端请求、不可继续的失败类别、以及合成本身失败时）。

**但有两点我不能替你决定：**

1. **`anthropic-responses-bridge/spec.md` 的 Error 契约是否约束 Anthropic 腿？** 那份 spec 管的是 Messages → Responses 桥，而本次事故按 §1.2 发生在 **Anthropic 腿**上。倾向「约束」——`stream.py:316` 的注释就在这段**两腿共用**的代码里援引该条款（「The frozen Spec rules these two mutually exclusive」），说明实现方已按「管这段共用代码」在办事。但这一步是推断，不是 spec 原文。
2. **兜底要不要现在就接。** `break` 是一个关键字的事，而且**即使最终答案是 MCP 合成，它作为过渡也严格优于现状**（现状是客户端零信息）。代价是线上行为会改两次。

### 3.2 MCP-driven 合成续写：已裁决、已冻结、代码里不存在

`rg -i 'turn_interrupted|auto_retry_tool_call' src tests` **零命中**。而细节早已在 `.dev/docs/upstream/retry-and-continuation/status.md:112-121` 与 `decisions.md` 冻结完毕：`num_messages` 取客户端请求的 `messages` 长度、工具定义缺失打 warning 照发、不设次数上限、观测面记 `[RETY]` + 黄色、`usage` 报失败 attempt 实报值、`client_delivery.auto_retry_tool_call_full_name` 可覆盖全名。

本次事故的四项要素**逐条命中那个门**：路由 `/v1/messages`（anthropic-messages）、失败类别是网络中断（文档列在「一般可以继续」集合里）、已交付过至少一个完整块、非 `count_tokens`。

**跨仓依赖**：`num_messages` 的判法需与改 MCP 的同伴对齐（`status.md:121` 建议按「同一数值重复出现」而非「数值有没有增长」，因为并行子智能体与主会话共享同一个 MCP server 进程，调用会交错）。

### 3.3 与在办计划 G1 的重叠 —— 请你确认

`.dev/docs/tmp/260821-plan-g1-upstream-error-events.md`（2026-08-21，自述「供直接执行」）处理的是**上游明确发来 `error` / `response.failed` 事件**时的识别与交付。触发条件与本文不同（我这里是根本没有终止事件的传输撕断），但**落点高度重叠**：同一段 `stream.py` 的 ending 分支、同一个 `_ending()` 文案、同一批 spec 条文。G1 已给出「(c) 独立于 `seen` 的已知失败终止」三格设计，并明确提醒必须同时改 `_ending()` 否则会自相矛盾——那正是本文 §2.4 补的那条次生危害。

**建议合成一条线做，不要开两条。** 请你确认 P1 是否就是 G1 的一部分。

---

## 4. 建议（含优先级与我的偏好）

1. **P0 · 升级那台机器到 HEAD。** 零代码改动，把「首块前撕断」从必死变成可无痕重放。**我强烈建议做**，这是本次调查中唯一确凿的纯收益动作。部署记录写「旧版本早于 replay 接线（`8f654b4`），文件态匹配 `9aa31f9..a68672c` 区间」，**不要写成某个精确提交**。
2. **P1 · 裁完 §3.1 再一次做完。** 我的建议顺序是：先答 §3.1 的两问 → 若采纳我的读法，则主路径实现 MCP 合成续写（§3.2），兜底路径把 `raise torn` 改 `break` 并补 accounting 原文（§2.3），两者与 G1 合并成一条线（§3.3）。**不要把「补帧」和「消 traceback」当成两个切片**——它们是同一个关键字。
3. **P2 · 修 `StreamEnding.COMPLETE` 被折叠成 `ABANDON`**，连带修 `_ending()` 在 terminal 已见时仍说「before a terminal event」。窄、确定、纯收益，配一个「terminal 之后才 reset」的判别性回归测试即可（不追覆盖率）。
4. **不做**：追查上游为何发 CANCEL（2026-08-20 已裁定为原理不可判定项）。
5. **不做**：把 `buffering_policy` 改成 `full` 来「修」这个问题——伪装成修复的配置权衡。

---

## 5. 查证后判定「没问题」的项（列出以免重复劳动）

Opus 评审逐项查过，结论均为**否定**（不是缺陷）：

1. **上游响应未释放？没有。** `httpx2` 的 `aiter_raw` 带 `finally: await self.aclose()`，撕断路径必经；`_events_with_ping` 的 `finally → finish_stream_cleanup → _close_iterator` 是第二道关闭。
2. **重试预算被错误消耗？没有。** 见 §2.2。
3. **`_cancel_and_observe` 出现在栈上暗示清理路径有问题？不暗示。** 机制是：pull task 已带异常完成 → `finally` 调 `finish_stream_cleanup` → `_cancel_and_observe` 的 `await pending` **重抛同一异常对象**，Python 往其 `__traceback__` 追加这一帧 → 立刻被 `except Exception: return error` 接住 → `if pending_error is primary: pending_error = None` 认出它就是主异常并丢弃。**异常不是从 cleanup 里冒出来的，只是路过留了个帧。** 评审在 7 次运行中每次都观察到。
4. **清理路径会不会用第二个异常盖掉主异常？不会。** 主异常始终赢，清理失败挂 `__cause__`。
5. **`accounting` 会不会记两遍？不会。** `finish()` 首行 `if self.done: return`，双保险是有意的。
6. **HEAD 新增的 `ClientDeadlineError` 分支会不会改判这次？不会。** `client_request_deadline` 默认 3600s，本次 48s 够不着。

---

## 6. 一个主动提出的观察，以及它撑不起什么

`error_code=8 (CANCEL)` 在 h2 里是「这条流不再需要了」。历史取证（`.dev/docs/upstream/h2-goaway/findings.md`）说**时长是主导变量**：<5s 危险率 0.011%，160–320s 涨到 24.9%；本次 48s 在中间区。

**证据等级：单样本，只够作为提示，不足以下任何结论。** 既不能说明「CANCEL 是一类新形态」，也不能说明「只是偶发」。要回答得看那台机器结构化日志里 `detail` 含 `StreamReset` 的行的分布——本报告没做，日志不在本机。

---

## 7. 顺带记下的两件不属于本次范围的事

跑本项目验证套件时观察到，**均与本次诊断无关**：

- `uv run ruff check src tests` 全绿。
- `uv run pyright src tests` 21 个错误，全部集中在 `src/app/upstream/stream_cap.py`（4）与 `tests/unit/upstream/test_stream_cap.py`（19）——同伴在飞的 h2 stream cap 工作。
- `uv run pytest tests` 1 failed / 1666 passed，覆盖率 90.93%。失败的是 `test_authoritative_example_config_parses`：用户当前未提交的 `docs/.human-controlled/config.example.yaml` 里写了两个代码还没有的配置键——`upstream_request_retry.strategies.streamReplay` 与 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`。**这是用户在人写文档里写前瞻需求造成的，不是 HEAD 代码的缺陷。**（`streamReplay` 作为独立重试预算，与 §2.2 讨论的「replay 与 network 共用 budget」正好相关。）

---

## 8. 本文三稿之间改了什么

| 评审意见 | 采纳？ | 我的复核 |
|---|---|---|
| GPT 分歧 1 / Opus F4：版本不能精确归因 | **采纳** | 自跑逐 revision 行签名扫描，5 个提交全中；错因写进 §1.3 |
| GPT 分歧 2：漏掉用户已裁决的 MCP-driven 续写 | **采纳** | 自读人写文档与 `retry-and-continuation/{status,decisions}.md`，确认已冻结；`rg` 零命中 |
| GPT 分歧 3/4：优先级与切片边界 | **采纳** | 已重排 |
| Opus F1：`think` 说明走的是 Anthropic 腿，初稿引错 assembler | **采纳** | 自读 `REASONING_WORD` + `dialect_for` + `assembler_for` 复核成立 |
| Opus F2：P1 定性反了（是偏离 FINALIZED spec，不是待裁功能） | **部分采纳** | spec 原文自读复核成立。但**与 GPT 分歧 2 冲突**——人写文档对同一格另有裁决。§3.1 把冲突摊开交用户裁，不替他选 |
| **Opus F3：「吞掉异常会造成回归」被证伪** | **采纳** | 自读控制流复核：`break` 确实落到 299 行往下、命中现成的 error 帧。**初稿评估的是 `return` 这个没人会提议的候选，结论与顺序依赖都不成立** |
| Opus 6.3：`break` 的真实代价是 accounting 丢原文 | **采纳** | 写进 §2.3 |
| Opus f4：「已登记」措辞不成立 | **采纳** | 已删除该措辞；那条缺口目前只活在 `reports/` 与 `tmp/`，未进任何活文档 |
| Opus f5：`httpcore2` vs `httpx2` 的映射步骤承重 | **采纳** | 写进 §1.1 |
| Opus §7.2：与 G1 计划重叠 | **采纳** | 自读 G1 全文，确认落点重叠；§3.3 交回用户确认 |
| Opus §8：六项查证无误 | **采纳** | 转录进 §5，避免下一位评审重跑 |
