# G1 方案：让活跃 pipeline 链路认出上游发来的错误事件

**日期**：2026-08-21。**性质**：单一缺口的边界与设计裁决，供直接执行。
**上级文档**：`.dev/docs/tmp/260821-truncated-anthropic-stream-diagnosis.md`（G1 的事实基础，本文不重新论证）。
**执行约束**：本次调查全程只读，未改动任何生产代码，未触碰 git 索引（该工作树有并行会话在提交）。

## 0. 结论摘要

1. **spec 已经裁决过了，不需要另起炉灶。** 上游的 `error` / `response.failed` 是**合法终止事件**（与 clean EOF 必须区分），但它**不是成功**，因此绝不能走 `terminal_frames`。这正好是问题里的形态 (c)：一个独立于 `seen` 的「已知失败终止」。形态 (a) 不足（丢掉了「区分」这一半），形态 (b) 直接违反两条冻结条款。
2. **我们没有见过 Anthropic 腿的 error 事件的真实录制。** 5 份 cassette 全部不含，history 派生也未验证过。它的形状目前只来自协议文档 + 参考实现 `copilot-api-js` 的代码与注释——后者是**二手但高可信**的证据（它自己踩过这个坑并写下了修复），不是我们的一手录制。
3. **最小自足补丁约 5 处、40 行以内**，预期不打红任何现存测试（现存测试从不喂 error 事件）。`Terminal` 需要加一个字段，且必须**同时**改 `_ending()` 的文案分支，否则会出现「发了带上游原话的 error 帧、日志行却说没有终止事件」的自相矛盾。
4. **G4：`code` 别动，`message` 可以改。** `code="incomplete_responses_stream"` 被 2 处测试断言、被 `docs/agents/delivery-keepalive/spec.md:50` 逐字复述；message 字面**零断言、零消费**。

---

## 1. 语义裁决：spec 已裁决，照 spec 走

### 1.1 spec 原文（读到的，确凿）

`docs/agents/anthropic-responses-bridge/spec.md` 三处直接命中：

| 位置 | 原文 | 裁决内容 |
|---|---|---|
| 「Upstream Responses HTTP SSE」节 | 「`response.completed`、`response.incomplete`、`response.failed`、terminal `error` 与 clean EOF 的语义**必须区分**。没有合法 terminal event 的 EOF 是 truncation，不是成功。」 | `failed` / `error` 与 clean EOF **不同形**；且二者都不是成功 |
| 「Content 与 terminal status」节 | 「Responses `failed` 与 terminal `error` 不是成功 message，**必须进入统一 error mapping**。」 | 它们的去向是 error mapping，不是 terminal frames |
| 「Error 契约」节 | 「commit 后发生错误时，HTTP status 已不可更改；**发送一个 Anthropic SSE error terminal，关闭 stream**，History 标记 failed／aborted，且**不发送成功 terminal**。」 | 已 commit 之后的线形固定为一个 error 帧，禁止 `message_stop` |

另有「SSE／WS envelope 契约」第 5 条：「terminal error 在尚未提交 HTTP success 时使用 Anthropic HTTP error；已提交后使用 Anthropic SSE error event，且**不得再发 `message_stop` 冒充成功**。」

### 1.2 三种形态的后果

**(a) 只记录不当终止**——`seen` 仍 false，客户端仍收到当前那句合成的截断文案，只是 `detail` 带上上游原话。
后果：可观测性拿到了，但 spec 的「必须区分」只兑现了一半。对客户端而言，「上游明确说了 overloaded_error」与「上游一声不吭」仍然发出同一个 `incomplete_responses_stream` 帧——而这恰恰是 spec 点名要区分的两件事。**不采纳**，但注意它是 (c) 的严格子集，(c) 顺带完成了 (a) 的全部收益。

**(b) 当作终止事件（`seen=true` → 走 `terminal_frames`）**——**违反两条冻结条款**，不是「是否违反」的问题：
- 违反「Responses `failed` 与 terminal `error` 不是成功 message」；
- 违反「不得再发 `message_stop` 冒充成功」。

还有第二层危害，与 spec 无关而与本仓现状有关（读到的，确凿）：`seen` 今天是三个消费者的门——
- `stream.py:279` 决定发 error 帧还是 terminal frames；
- `pipeline_app.py:513` 决定 `context.reply` 写不写（即 hooks／History 的「这次回复完成了」契约）；
- `retry.py:158` `decide_stream_ending` 的第一分支：`terminal_seen → COMPLETE`。

把 `seen` 置真会让一次上游失败在这三处**同时**被记成成功，包括让未来接线的 G2 直接判 COMPLETE 而放弃重试。参考实现 `copilot-api-js` 正是踩过这一脚：它的 `sawMessageStop()` 对任何终止（含 failed）都为真，于是不得不再加一个 `sawUpstreamError()` 去**否决**（原文用词 VETOES）成功判定（`~/src/copilot-api-js/src/lib/pipeline/types.ts:405-420`）。我们不必复制这个补丁——只要一开始就别把 `seen` 置真。

**(c) 独立于 `seen` 的「已知失败终止」**——**采纳**。`seen` 保持它文档里那个含义不变（「上游自己的**成功**终止事件到没到」，即 `message_stop` / `response.completed` / `response.incomplete`），新增字段承载「上游明确说了它失败」。`stream.py` 的分支顺序变成三格：失败终止 → 截断 → 成功终止。三格与 spec 的「必须区分」一一对应。

### 1.3 与 legacy 的一致性（读到的，确凿）

legacy 链路的实际行为**就是 (c)**，只是没有把这个概念显式命名：

- `src/app/openai/responses_stream_parser.py:215-223` 把 `response.completed` / `incomplete` / `failed` / `error` 四者统一识别为终止事件，`_on_terminal`（:472-533）给出 `TerminalKind`，并从 `event["code"] / response.error.code` 与 `event["message"] / response.error.message` 取出上游原话。
- `src/app/delivery/anthropic_sse.py:729-745` `_finish_from_terminal`：`kind != "completed"` 且不是「`incomplete` + `max_output_tokens`」时，**抛 `ResponsesDeliveryError(terminal)`**，绝不进 `_write_terminal`。
- 该异常经 `responses_anthropic_stream.py:294-310` 的 `_normalize_stream_error` → `_upstream_error(str(error), code=error.code or error.kind)` → `session.render_error(...)`，最终是一个携带**上游原话**的 SSE error 帧。`ResponsesDeliveryError.__init__`（`anthropic_sse.py:57-60`）的 `super().__init__(detail or self.code or self.kind)` 就是「原话优先」的取词顺序。

结论（推出来的，强，足以行动）：新链路照 (c) 做是**移植而非重新设计**，与 `implementation.md:267` 记录的 STR-04 移植原则同向——同一条冻结规则，两条链路一个实现。

---

## 2. Anthropic 腿的 error 事件长什么样、我们见过吗

### 2.1 直接回答：**没见过**

`tests/int/cassettes/` 共 5 份：`anthropic_to_responses_stream.json`、`history_anthropic_stream.json`、`history_responses_stream.json`、`responses_web_search_nonstream.json`、`responses_web_search_stream.json`。

全文检索 `event: error` / `"type":"error"` / `response.failed`：**零命中**。逐条核对 `error` 字符串的实际出现位置，全部是 Responses 响应对象里的 `"error":null` 字段（3 份各 3 次），不是事件。`history_anthropic_stream.json` 的帧序列为 `message_start` → `content_block_*` → …，无 error。

（证据强度：确凿。这是穷举了目录下全部文件的检索结果。）

**因此按本项目纪律，「上游行为是录下来的，不是想象的」这一条在这里没有被满足。** 下面第 2.2、2.3 两节给的是**协议文档级 + 参考实现级**的形状，须按此标注权重使用。

### 2.2 形状（来自参考实现的类型与代码，二手但高可信）

`~/src/copilot-api-js/src/types/api/anthropic.ts:188-191`：

```ts
export interface StreamErrorEvent {
  type: "error"
  error: { type: string; message: string }
}
```

关键细节，来自 `~/src/copilot-api-js/src/lib/anthropic/wire-frame-type.ts:1-24` 的注释（该文件整篇就是为修这个 bug 而写）：

> An Anthropic SSE frame carries its type twice — on the `event:` line and as the payload's top-level `type` — and upstream does not always send both. **A raw upstream error frame in particular arrives as `event: error` with a body of just `{ error: { ... } }`**，canonical `type` 是后续 rewrite 才补上的。

**对我们的影响（推出来的，强）**：我们**已经**是安全的那一侧。`AnthropicAssembler.push:129` 写的是 `kind = event.event or str(data.get("type", ""))`——**事件行优先**，`parse_frame`（`sse_source.py:34-52`）也确实解析 `event:` 行。参考实现踩坑的五处读取器全是「只读 payload」，我们不在那个形态里。这条不需要额外改动，但值得在新增分支旁写一句，防止后来者把取词顺序改成 payload 优先。

Responses 腿的两种形状（来自 legacy parser 的实际取词，读到的）：
- `response.failed`：`event.response.error.{code,message}`，且 `response.id` 存在；
- `error`：顶层 `event.{code,message}`，`response.id` 可缺失（`responses_stream_parser.py:475-479` 专门为 `event_type == "error"` 放宽了 id 必填）。

### 2.3 参考实现怎么处理（读到的，确凿）

`~/src/copilot-api-js/src/lib/anthropic/stream-accumulator.ts:193-200`：

```ts
case "error": {
  const err = (event as { error?: { type?: string; message?: string } }).error
  acc.streamError = {
    type: err?.type ?? "unknown_error",
    message: err?.message ?? "Unknown stream error",
  }
  break
}
```

`~/src/copilot-api-js/src/routes/messages/handler-v4.ts:2036-2054`：`if (acc.streamError)` 分支——把上游原话写进日志与 `ctx.fail`，**并保留 error 帧之前已累积的部分内容**（注释 C1：`preserve the partial content accumulated before the terminal error frame`），且该分支**自己不写任何帧**，因为帧已经在转发路径上原样／规范化地给了客户端。

`~/src/copilot-api-js/src/lib/pipeline/types.ts:411-423` 给出的语义判断，与我们的裁决完全一致：

> H2 is a terminal upstream decision (**NOT a transport cut**) → the buffered sink COMMITS it … instead of wastefully retrying it as a truncation.
> live: it **VETOES** the post-terminal drain-as-complete gate.

它并且明确点名 `overloaded_error` 是这类帧的典型 type——这也是我们仓里 `src/app/lifecycle/adapter.py:15` 已经在用的 Anthropic 官方错误类型（我们自己发给客户端时用的就是它）。

**一个结构差异必须记住**：参考实现是**转发**上游帧，我们的新链路是**重组**（assembler 不透传字节）。所以我们不能「让帧自己走过去」，必须自己合成一个 `error_frame`，取词来自 `Terminal` 上的新字段。

### 2.4 怎么把「见过」补上（建议，未执行）

两条路，成本递增：

1. **从 history 派生**（`tests/int/recorded/from_history.py`）。前提是 `~/.local/share/copilot-api/history-v3-20260815-183721.db` 的 `v3_timeline_chunks` 里存在含 `event: error` 的上游原始帧。**我没有执行这个探测**：该 db 属于仍在运行的 `4141` Bun 服务，项目规则要求不去动它，我不替用户授权（哪怕只读打开）。若用户同意，只读探测命令是：

   ```bash
   sqlite3 'file:/home/xp/.local/share/copilot-api/history-v3-20260815-183721.db?mode=ro' \
     "select count(*) from v3_timeline_chunks where cast(payload_gz as blob) is not null;"
   ```

   注意 `payload_gz` 是压缩列，真正的判断要在 Python 里解压后按 `_upstream_frames` 取变换图的根再匹配 `"type":"error"`——直接对 blob 做 LIKE 会**静默返回 0**，读起来像「没有」。（这正是记忆里「先证明探针真的跑了」那条踩过的形状。）另外项目规则记载该服务 2026-08-15 后已停止存帧，而这个 db 恰好是 `20260815` 那一天建的，**命中概率不高**，需要先验证再当作路线。

2. **手写 fixture**——本项目明确把它当作反模式（「hand-written stand-in encodes what we believe upstream does」）。但对**本次这个补丁**它是可接受的，理由要写清楚：这个分支的判据是「我们的代码在收到形如 X 的帧时是否走对了分支」，**换个上游仍然成立**，属于项目记忆里「用 mock upstream，别反复实测上游」那一类。真正依赖上游真实行为的是「上游到底发不发这种帧、发的时候字段齐不齐」——那一问 mock 回答不了，也**不该**被这个补丁的绿灯冒充回答。

**建议**：补丁用手写 fixture 的单测落地，并在测试 docstring 里写明「形状来自协议文档与 `copilot-api-js` 的类型定义，尚无我方录制」。同时把「取得一份真实 error 帧录制」记为独立待办，不阻塞补丁。

---

## 3. 改动面清单与最小自足补丁

### 3.1 记录层：`Terminal` 要加字段

**要加。** 理由不是「顺手」，而是三条硬约束：

- 展示层（TUI／日志行／JSONL）按项目记忆只读 `Terminal` 这类聚合记录，不读原始事件对象。不加字段，上游原话就没有合法通道到达日志行。
- `_ending()` 必须能分辨「干净 EOF」与「上游说了原因」，而它手上只有 `self.assembler.terminal`。
- 不加字段的唯一替代是把原话塞进 `stream.py` 的局部变量，但发帧的地方（`stream.py`）与写日志的地方（`pipeline_app.py`）是两条不相交的调用路径，局部变量到不了后者。

形状（建议）：

```python
@dataclass(frozen=True, slots=True)
class UpstreamFailure:
    """上游明确说了这次不成功时，它自己给的那几个字。"""
    type: str = ""      # Anthropic 腿：上游自己的 error.type（已是 Anthropic taxonomy）；Responses 腿留空
    code: str = ""      # Responses 腿：event.code / response.error.code
    message: str = ""
```

`Terminal` 上加 `failure: UpstreamFailure | None = None`。用 `None` 而非空实例，因为「上游没说」与「上游说了但字段是空串」是两件事——正是项目记忆「日志行上的缺席读不出来」防的那一类。

**构造安全性（读到的，确凿）**：全仓 `Terminal(...)` 的构造点只有 4 处（`assembler.py:86,121,211`、`tests/.../test_stream_delivery.py:651`）外加 `test_request_log_file.py:57`，**全部使用关键字参数**，追加字段不会打破位置参数。

### 3.2 文件与函数清单

| 文件 | 位置 | 改什么 | 必要性 |
|---|---|---|---|
| `src/app/pipeline/delivery/assembler.py` | 新增 `UpstreamFailure`；`Terminal` 加 `failure` 字段 | 载体 | 必需 |
| 同上 | `AnthropicAssembler.push:127-145` | 加 `if kind == "error": self._read_failure(data); return ()` 分支 | 必需 |
| 同上 | `ResponsesAssembler.push:218-236` | 加 `if kind in {"response.failed", "error"}: ...` 分支 | 必需（spec 同款条款，两条腿一起闭合，成本几乎为零） |
| `src/app/pipeline/delivery/stream.py` | `_deliver` 尾部 :275-293 | 在 `if not terminal.seen` **之前**插入 `if terminal.failure is not None` 分支，发携带原话的 `error_frame` 后 `return` | 必需 |
| 同上 | :285 | 截断文案按 `terminal.dialect` 取词（见 §4） | 建议同一切片做掉，一行 |
| `src/app/server/pipeline_app.py` | `_ending():532-537` | 在 `if self.drained` **之前**加一格：`terminal.failure` 存在时返回 `("fail", f"upstream ended the stream: {…}")` | **必需**，见下 |
| 同上 | `_StreamAccounting.finish():506-522` | `_ending()` 需要读到 terminal，当前 `_ending` 不带参；最省的改法是把 `terminal` 作为参数传进去 | 必需（`_ending` 目前只读 `self.failure/self.drained`） |
| 同上 | `_Trace.absorb():193-205` | `self.upstream_error = …` | 建议做（见 §3.3） |
| `src/app/observability/request_log.py` | `RequestLine` :115-141 | 加 `upstream_error: dict[str, Any]`，默认 `{}` | 建议做 |

**为什么 `_ending()` 那一格是必需而不是可选**：新分支保持 `seen=false`，于是 `finish()` 里 `delivered_whole and terminal.stop_reason` 仍为假，`_ending()` 照旧返回「upstream stream ended without a terminal event」。结果是客户端收到「上游说 overloaded_error」的帧，而操作者的日志行说「上游什么都没说就结束了」——**两条交付路径对同一事实给出互相矛盾的描述**。这正是项目记忆「同一事实不得在两条交付路径各推导一遍」要防的形态。所以 `stream.py` 与 `_ending()` 必须在同一个补丁里改，不能拆。

### 3.3 日志行文案怎么变

- **控制台行不加新列。** 上游原话进 `detail`，`detail` 已经是行尾那段带颜色的解释（`request_log.py:380-382`），也已经进 JSONL。文案建议：`upstream ended the stream: overloaded_error: Overloaded`（先 type／code 后 message，与 legacy `ResponsesDeliveryError` 的取词顺序同向）。
- **JSONL 建议加结构化字段** `upstream_error: {"type": ..., "code": ..., "message": ...}`，`{}` 表示没有。`write_request_record` 用的是 `asdict(line)`（`request_log_file.py:41`），加字段自动进盘，零额外代码。理由：上一次诊断（req=d3b7f5ba）就是靠 JSONL 第 1675 行的结构化字段做的，散文 `detail` 可 grep 但会随文案漂移；`RequestLine.upstream_conn` 已经是嵌套 dict 的既有先例，形状不新。
- **History**：`schema.py` 无 frame 字段，且被截断的回复因 `context.reply` 仍 gate 在 `seen` 而根本不写 `reply`。**本切片不动 History**——那是 G3，`implementation.md:268` 已登记为需与 `context.reply` 放宽一并裁决。

### 3.4 哪些测试会红

**预期：零。** 依据（读到的，确凿）：现存测试没有任何一条向 assembler 喂 `error` / `response.failed` 事件——`_truncated_delivery`（`test_stream_delivery.py:322-338`）喂的是 `anthropic_stream("one")[:-2]`（砍掉 `message_delta` 与 `message_stop`），`test_a_synthesized_start_that_never_gets_a_block_ends_in_an_error` 喂的是空列表。`tests/unit/pipeline/delivery/test_sse_assembly.py` 的 26 条测试也无 error 事件。因此新分支在现存测试里**永不进入**。

改截断文案（§4）同样不打红：全仓无任何测试断言 `"Responses stream ended before a successful terminal event"` 这个字面。

**要新增的测试（3 条，够了）**：

1. `AnthropicAssembler` 收到 `event: error`（body 只有 `{"error": {...}}`，无顶层 `type`）后，`terminal.failure` 带上原话且 `terminal.seen` 仍为 `False`——第二个断言是这条测试的要害，它钉住「不得伪装成功」。
2. 端到端：一段发了一个块然后发 error 帧的流，客户端收到的字节里有上游 type／message，且 `"message_stop" not in body`、`'"stop_reason"' not in body`。
3. `ResponsesAssembler` 收到 `response.failed`，同上。

不要为「上游 error 帧后又发 message_stop」之类的畸形序列预建状态空间——项目规则明确禁止预建完备证明矩阵，等真出现再补。

### 3.5 明确不做（本切片边界）

| 不做 | 理由 |
|---|---|
| 动 `seen` 的语义或它的三个读者 | §1.2 |
| 接线 `decide_stream_ending`（G2） | 独立切片。**但要在 `retry.py` 留一条注释**：接线时 `failure is not None` 必须映射到 ABANDON 而非 CONTINUE——上游明确失败不是截断，重试是浪费。这是参考实现 VETO 的同一条理由，属于「不得静默裁掉的潜在需求」，登记而不实现 |
| 放宽 `context.reply` 的 `seen` 门（G3） | `implementation.md:268` 已裁定与 STR-04 的 failed History 同批 |
| 处理「零字节流上收到 error 帧」 | 当前 `stream.py:277` 的 `not client_has_bytes.is_set()` 早退让客户端拿到 200 空 body。spec 说 commit 前应给 Anthropic **HTTP** error，这是既有缺口（代码里已有注释自陈），比本补丁大一号，单独裁决 |
| 改 `AnthropicAssembler` 的 `kind` 取词顺序 | 已经是事件行优先，恰好是对的（§2.2）。只加注释说明为什么不能改成 payload 优先 |

---

## 4. G4：截断帧的文案与 code

### 4.1 现状（读到的，确凿）

`stream.py:281-287` 无条件发 `message="Responses stream ended before a successful terminal event"`、`code="incomplete_responses_stream"`。两条腿共用：assembler 在 `handler.py:481-488` 按 dialect 分流，随后共用同一个 `stream_delivery`；`error_frame`（`pipeline/delivery/anthropic_sse.py:141-151`）不按 dialect 改写。本次事故走的是 anthropic 腿，于是客户端读到的是另一条腿的协议名。

### 4.2 `code` 被谁消费

- **测试**：2 处断言——`tests/unit/pipeline/delivery/test_stream_delivery.py:177` 与 `:367`。
- **文档**：3 处复述——`docs/agents/delivery-keepalive/spec.md:50`（**逐字写出该 code 并称其为实测线形**）、`docs/agents/delivery-keepalive/status.md:69`、`docs/agents/delivery-keepalive/review-reconciliation.md:30`。另 `docs/agents/anthropic-responses-bridge/implementation.md:267` 与 `docs/tmp/260807-resume-verify-stream-route.md:44` 也提到。
- **代码**：`src/` 下**无任何读者**。它只被产出，从不被回读。
- **客户端**：作为 Anthropic SSE error 帧的 `error.code` 字段发出。检索 `copilot-api-js` 全仓亦无消费者。**判断（推出来的，中等偏强）**：对客户端而言这是一个不透明标签，改名不会破坏任何已知消费者，但也拿不到任何已知收益。

### 4.3 legacy 的移植来源

`src/app/delivery/responses_anthropic_stream.py:347-351`：

```python
if not session.frontier.terminal_accepted:
    api_error = _upstream_error(
        "Responses stream ended before a successful terminal event",
        code="incomplete_responses_stream",
    )
```

字面完全一致——新链路是逐字移植的（`stream.py:281` 的注释自陈如此）。但 legacy 那条链路**只服务 Responses 上游**，所以在那里 `Responses` 这个词是准确的；移植到两条腿共用的位置之后它才变成缺陷。这一点是本条 finding 的核心，也解释了为什么它不是既定裁决：**spec 冻结的是错误语义与 envelope，没有冻结这句 message 与 code 的字面**（诊断文档已核，我复核成立）。

### 4.4 建议改法

**改 message，不改 code。**

```python
UPSTREAM_WORD = {ReplyDialect.ANTHROPIC: "Anthropic", ReplyDialect.RESPONSES: "Responses"}
...
message=f"{UPSTREAM_WORD[terminal.dialect]} stream ended before a successful terminal event",
```

`terminal.dialect` 就在手边（`stream.py:277` 上一行已取 `terminal = assembler.terminal`），零plumbing。`request_log.py` 里已有 `REASONING_WORD[dialect]` 这个「按 dialect 取词」的既有形状，新常量与它同构，不是新机制。

**不改 code 的理由**：它是一个 code 不是散文，误导发生在人读的那半边；改名要连带改 2 处断言 + 至少 1 处 spec 复述（`delivery-keepalive/spec.md:50` 在其外部契约仍活跃期间是规范性的），换来的是没有已知消费者的收益。ROI 为负。

**留给用户的分叉**：若认为 `code` 里的 `responses` 同样不可接受，中性化为 `incomplete_upstream_stream` 的**精确代价**是：改 2 处测试断言、更新 `delivery-keepalive` 的 spec/status/review-reconciliation 三处复述、更新 `anthropic-responses-bridge/implementation.md:267`。我的倾向是**不改**，但这是可以推翻的偏好，不是判定。

---

## 5. 待用户裁决的分叉（我给了倾向，但不自行决定）

1. **error 帧的 `error_type` 取谁的？**
   我的倾向：**Anthropic 腿透传上游自己的 `error.type`**（`overloaded_error` 等本来就在 Anthropic taxonomy 里，spec「尽可能保留语义等价的 error type」同向），**Responses 腿保持 `upstream_error`** 并把上游 code 放进 `code` 字段（OpenAI 的 code 不是 Anthropic type，透传会造出客户端不认识的 type）。这是一处真实的两腿不对称，值得写进代码注释。
   替代方案：两腿一律 `upstream_error`，把上游 type 塞进 message。更保守，也更少信息。
2. **JSONL 是否加 `upstream_error` 结构化字段**（§3.3）。我倾向加；不加也能靠 `detail` 散文过日子。
3. **G4 的 `code` 是否中性化**（§4.4）。我倾向不改。
4. **是否授权只读探测 `~/.local/share/copilot-api/history-v3-*.db`** 以尝试取得一份真实 error 帧录制（§2.4）。命中概率不高，不阻塞补丁。

---

## 6. 证据强度总表

| 主张 | 来源 | 类别 | 强度 |
|---|---|---|---|
| spec 已把 `failed`／terminal `error` 裁为「须区分、非成功、进 error mapping」 | `spec.md` 三处原文 | 读到的 | 确凿 |
| spec 禁止在这种情况下发 `message_stop` | `spec.md` SSE envelope 第 5 条 + Error 契约 | 读到的 | 确凿 |
| `seen` 今天是三个消费者的门 | `stream.py:279`、`pipeline_app.py:513`、`retry.py:158` | 读到的 | 确凿 |
| legacy 实际行为等价于形态 (c) | `responses_stream_parser.py:215-223,472-533` + `anthropic_sse.py:729-745,57-60` + `responses_anthropic_stream.py:294-310` | 读到的 | 确凿 |
| cassettes 无任何 error 事件 | 穷举 5 份文件的检索 | 读到的 | 确凿 |
| Anthropic error 帧可能不带顶层 `type`，只有 `event: error` + `{error:{...}}` | `copilot-api-js/src/lib/anthropic/wire-frame-type.ts:1-24` | 二手（他人代码注释，且是其修复记录） | 强，足以据此不改我们的取词顺序 |
| 我方取词顺序已是事件行优先，不受该坑影响 | `assembler.py:129` + `sse_source.py:34-52` | 读到的 | 确凿 |
| 参考实现把上游 error 当终止决定、否决成功判定、不重试 | `types.ts:405-423`、`handler-v4.ts:2036-2054`、`stream-accumulator.ts:193-200` | 读到的（他人代码） | 强 |
| 现存测试不会因新分支变红 | `test_stream_delivery.py:322-338,166-180`、`test_sse_assembly.py` 全部用例 | 读到的 | 强（穷举了两个相关测试文件；未跑测试） |
| 截断 message 字面零断言 | 全仓检索该字符串 | 读到的 | 确凿 |
| `incomplete_responses_stream` 有 2 处测试 + 3 处文档复述、`src/` 内零读者 | 全仓检索 | 读到的 | 确凿 |
| 全部 `Terminal(...)` 构造点均用关键字参数 | 全仓检索 | 读到的 | 确凿 |
| `_ending()` 不改就会与 error 帧自相矛盾 | 由 `finish():506-522` 与 `_ending():532-537` 的控制流推出 | 推出来的 | 强，足以行动 |
| history db 里存在可派生的 error 帧 | 未探测 | **未验证** | 无——不得作为路线依据 |
