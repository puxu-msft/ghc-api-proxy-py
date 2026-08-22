# 评审：`78be0d4` 干净 EOF 落在块边界的收尾细化

评审日期：2026-08-22。评审者：subagent（只读评审）。

**技能声明**：派发要求的 `my-skills:as-reviewer` **确认不存在**——`~/.claude/skills/` 下 35 个条目里没有它（已列目录核对）。按派发指示改用 `my-skills:verifying-authoritative-claims` 与 `my-skills:trusting-a-green-result`，两份均已加载并按其协议执行（质疑触发器、命题条件化、变异前的在位探针、变异后的还原校验）。

## 0. 结论与纪律声明

**结论：`needs-fix`。** blocker 0 条，major 3 条，minor 5 条，另记 6 条「实现者做对了」的正面确认。

最要紧的一条：**Responses 腿上，上游明说 `status:"incomplete"` 的那个块被 `_cut_short` 摘走后 `_drafts` 就空了，于是 `cut_mid_block` 返回 `False`，这条流走进「干净收尾」分支——客户端拿到 `stop_reason:"incomplete"` + `message_stop`，而那半个块被静默丢弃；改动前它是一条响亮的 error 帧。**而证据报告实测到的 4 条块边界命中**全部**在 Responses 腿，这条腿的 `cut_mid_block` 在 unit+int 全量套件下又**没有任何鉴别力**（双向常量变异 1701 passed 不变）。细化唯一有实测价值的那条腿，判据有洞且无测试。

纪律：

- 全程只读。**未修改主工作树任何文件**，未 `git add`、未 `git commit`、未跑 `ruff format`、未向上游发任何真实网络请求、未建门禁或清单系统。未触碰 `docs/.human-controlled/`。
- 同伴分支 `fix/one-ending-decision`（`f84e821`，`.claude/worktrees/one-ending`）**只用 `git show f84e821:<path>` 读取**，未进入那棵工作树、未修改那个分支。
- 所有变异与探针在只读副本 `/tmp/rev-78be0d4`（`git archive 78be0d4 | tar -x`）上进行。读任何数字之前先证明解析：`app.pipeline.delivery.stream.__file__ == /tmp/rev-78be0d4/src/app/pipeline/delivery/stream.py`（实测输出）。**每一轮变异后都跑 `sha256sum --check /tmp/rev-78be0d4-baseline.sha256`，8 轮全部 4/4 `OK`**，最后一轮复核同样通过。

**时效**：主树 HEAD 已从 `a59800d` 走到 `17e7177`。`78be0d4` 仍是 HEAD 的祖先；`78be0d4..HEAD` 对 `src/app/pipeline/delivery/formats/` 的改动**只新增了上游 error 事件的日志**（`_FAILURE_EVENTS` / `_failure_words` / `logger.warning`），**未触碰 `cut_mid_block`、`_cut_short`、`_drafts` 生命周期，也未触碰 `stream.py` 的收尾**。本报告全部结论在当前 HEAD 上仍然成立。

---

## 1. 你点名要复核的那一条：usage 写成零

### 1.1 ① 描述属实吗 —— 属实

`证据等级：一手实测。分级：minor（理由见 1.4）。`

两条腿的新分支都在 wire 上发出未经测量的零，实测输出：

- Anthropic 腿（`anthropic_stream("one")[:-2]`，即丢掉 `message_delta` 与 `message_stop`）：
  `data: {"type":"message_delta","delta":{"stop_reason":"incomplete","stop_sequence":null},"usage":{"output_tokens":0}}`
- Responses 上游腿（只有一个完整 item，然后 EOF）：同样 `"usage":{"output_tokens":0}`。

链路与你的描述逐段吻合（代码事实）：`AnthropicFramer.terminal` 传 `usage=terminal.usage or None` → `terminal_frames(usage=None)` → `usage or {"output_tokens": 0}`。`Terminal.usage` 的默认是 `{}`，新分支上 `_read_terminal` 从未运行过（Responses 腿）或从未收到过 `message_delta`（Anthropic 腿），所以这里恒为空。

「本改动之前它只在真见过终止事件时才可达」——这半句**需要收窄一格**。改动前它同样在 `terminal.seen == True` 但上游终止事件不带 `usage` 字段时可达（Anthropic 腿的 `message_delta` 没有 `usage` 键，或 Responses 腿 `_anthropic_usage` 捕获 `ResponseConversionError` 返回 `{}`）。改动带来的新东西是：**在这条新分支上零是 100% 必然的**，因为按证据报告实测 usage 在 109 条干净 EOF 上 **0/109**——Responses 腿的 usage 只搭 `response.completed` 走。

### 1.2 ② 改法对正常路径 wire shape 的影响 —— 有，而且正是你担心的那处

`证据等级：代码事实。`

`terminal.usage` 的类型是 `dict[str, Any]`，默认 `{}`；`AnthropicFramer.terminal` 里的 `terminal.usage or None` **把空 dict 也变成 `None`**，于是 `terminal_frames` 的 `or {"output_tokens": 0}` 接手。正常路径有两条合法途径到达空 dict：

1. `_anthropic_usage` 捕获 `ResponseConversionError` 后 `return {}`（`openai_responses.py:542-545`，注释写明「A malformed usage yields no counts instead of propagating」）；
2. 上游终止事件根本没带 `usage` 字段（`_read_terminal` 的 `if isinstance(usage, dict)` 不成立）。

这两种今天也发 `{"output_tokens": 0}`。所以「无 usage 时省略该键」会**同时改变这两条正常路径的 wire shape**，不是零波及。

### 1.3 ③ `message_delta.usage` 是不是必填

`证据等级：一手实测（读已安装 SDK 的类型定义）。`

anthropic Python SDK **1.0.0**（本仓 `.venv` 里的版本）：

- `RawMessageDeltaEvent.usage: MessageDeltaUsage` —— **无默认值，必填**；
- `MessageDeltaUsage.output_tokens: int` —— **无默认值，必填**（同类里 `input_tokens`、`cache_*`、`output_tokens_details`、`server_tool_use` 全是 `Optional[...] = None`，唯独它不是）。

也就是说协议层面**没有「未知」的合法拼写**。省略该键会让任何用 Python SDK 解析这条 SSE 的下游直接 `ValidationError`。

关于 Claude Code：`证据等级：推断，未实测`。它走 TS SDK，而 TS SDK 不做运行时 schema 校验（只做类型断言），所以大概率不会崩，但读到的是 `undefined`，token 计数会失真。**我没有对 Claude Code 做任何实测，这一条不足以据此行动。**

一个calibration 用的旁证（代码事实）：`anthropic_messages.py:26-41` 的 `message_start` 在**每一个回合**都无条件发 `"usage": {"input_tokens": 0, "output_tokens": 0}`——一个纯发明的零，早已在 wire 上、从未被当作缺陷。所以「不写未测量的零」这条判据在**这个 wire 字段**上本来就没有被执行过。

### 1.4 我的修法建议

**不要省略该键，也不必改 wire。** 理由按权重排：

1. 协议把 `output_tokens` 定成必填，零是唯一合法的占位；「诚实」在这里没有合法拼写，省略是把一个记录问题换成一个协议违规。
2. 「零是一次测量，没测过不是」这条判据保护的资产是**我们自己的记录**，而这条链路上我们的记录是干净的：`Terminal.usage` 保持 `{}`（不是零），`request_log.py:291` 用 `if "output_tokens" in usage` 判断，缺席就是缺席。**本方记录没有被污染**，这是它与 `Terminal.stop_reason` 空默认、`upstream_usage` 用 `None`、`_snapshot_upstream_connection` 宁可缺键那三例的实质差别——那三例污染的都是本方记录。
3. 想要「不说谎」的操作员已经有出口：`unterminated_stream_stop_reason` 留空 → 回到 error 帧，根本不发 `message_delta`，也就没有那个零。这条开关已经实现并有测试。

**真正值得改的是可见性，一行位置的事**：把 `or {"output_tokens": 0}` 从 `terminal_frames` 的默认参数里提到调用点，和它上面那行 `stop_reason=terminal.stop_reason or "end_turn"` 一样显式写在 `AnthropicFramer.terminal` 里，并把「这是合成，因为协议不接受缺席」写进注释。合成留在原地，但它变成**看得见**的合成——这正是本仓对 `or "end_turn"` 的处理方式（`anthropic_messages.py:220-232` 的 docstring 明写「a synthesis and stays visible rather than being written into the record」）。

顺带记一条（minor，见 §3.5）：同一次收尾上两条腿的诚实度不一致——`ResponsesFramer.terminal` 传 `usage=terminal.upstream_usage`，`None` 直接落成 wire 上的 `null`（docstring 自陈「absent rather than zeroed when it was never seen」），而 Anthropic 腿伪造零。同一个事件，两种口径。

---

## 2. Major 发现

### 2.1 [major] Responses 腿：`_cut_short` 摘走草稿，使 `cut_mid_block` 在「上游明说被切断」时返回 `False`

`证据等级：一手实测（probe P3 / P3b）。分级：major。`

**怎么失败**，具体场景：

1. Responses 上游发完 item 0（`output_item.done`，`status: "completed"`），一个完整块交付给客户端；
2. 再发 item 1 的 `output_item.done`，**`status: "incomplete"`**——上游明说这个 item 没写完；
3. 然后 EOF，没有 `response.completed` / `response.incomplete`。

`ResponsesAssembler._close` 在第 2 步 `self._drafts.pop(key)` 之后把块存进 `self._cut_short` 并 `return ()`（`openai_responses.py:433-480`）。`_cut_short` 只在 `response.completed` / `response.incomplete` 到达时才被释放（`push` 的 `if kind in {...}` 分支）。所以 EOF 时：

```
P3 cut_mid_block: False
P3 terminal.seen: False
P3 quiet close: True          ← stop_reason:"incomplete" + message_stop
P3 error frame: False
P3 'half' delivered: False    ← 上游那半个块被丢掉
P3 'whole' delivered: True
```

对照 P3b（同一条流，但第 2 步的 `output_item.done` 干脆不发，草稿真的开着）：`cut_mid_block: True`，`error frame: True`——判据在这一腿上只对「草稿开着」这一种切断有效。

**为什么这是实质缺陷而不是措辞问题**：`BlockAssembler.cut_mid_block` 的 docstring 说「Whether a block was still being accumulated when the events stopped」，并被 `stream.py:424` 反用为「没有草稿 ⇒ 没有块被切断」。而 `_cut_short` 恰好是第三态：**块被切断了，而且还没交付**。改动前这条流得到 error 帧（客户端知道出事了）；改动后得到一个看起来干净的收尾，内容静默消失。**从「响亮的截断」退化成「安静的丢内容」，这是所有失败模式里最难被发现的那一种。**

**两条腿的 `_drafts` 生命周期确实不同**（你问的第 1 点，答案是「是」）：

| | Anthropic 腿 | Responses 腿 |
|---|---|---|
| 草稿开 | `content_block_start` | `output_item.added`（对每种 item 类型都开） |
| 草稿关 | `content_block_stop` → 立即 `record()` + 交付 | `output_item.done` → **可能** `record()` + 交付，**也可能**进 `_cut_short` 扣住 |
| 「块关了但没交付」的中间态 | 不存在 | **存在**（`_cut_short`），且 `cut_mid_block` 看不见 |

所以判据在两条腿上系统性偏向不同方向：Anthropic 腿上 `bool(self._drafts)` 与「有没有块被切断」同义；Responses 腿上它只是「有没有块**正在**被切断」，漏掉「已经被切断、正扣着」。

**建议**：`ResponsesAssembler.cut_mid_block` 改为 `bool(self._drafts) or self._cut_short is not None`。不建议改 `_cut_short` 的持有语义——那是另一条已裁决的规则（`Ruled 2026-08-21, narrowed 2026-08-22`），动它超出本改动范围。

### 2.2 [major] 上游给出的 `stop_reason` 被合成值无条件覆盖，且与同一提交里的调用方自相矛盾

`证据等级：一手实测（probe P2）+ 代码事实。分级：major。`

`stream.py:430` 写的是 `replace(terminal, stop_reason=settings.unterminated_stop_reason)`——**无条件覆盖**，不看 `terminal.stop_reason` 有没有值。

**怎么失败**：Anthropic 上游发 `message_delta{"stop_reason":"max_tokens"}`，然后 EOF，`message_stop` 没来。`terminal.seen` 仍是 `False`（只有 `message_stop` 置位），`_drafts` 已空。实测输出：

```
P2 has max_tokens: False
P2 has incomplete: True
```

上游明确说了 `max_tokens`，客户端被告知 `incomplete`。**一个观测被一个合成覆盖掉了**，方向和这一整族缺陷（`Terminal.stop_reason` 的空默认那一族）完全一致，只是这次是「有观测却不用」而不是「没观测却编一个」。

**而同一棵树的调用方给出相反的裁决**（代码事实，`inference.py:534-539`）：

```python
delivered_whole = self.drained and self.failure is None
if self.handed_over or not (delivered_whole and terminal.stop_reason):
    self.trace.status_override, self.trace.detail = self._ending()
```

配套注释明写：「an Anthropic leg splits its ending, `message_delta` carrying the reason and usage and `message_stop` merely closing, and **a stream that drained after the first has told us everything the client was owed**. Reporting that as truncated produced a line arguing with itself」。

于是在这个形态上：`drained=True`、`failure=None`、`terminal.stop_reason="max_tokens"` 为真 → **不做 `_ending()` 覆写，完成行按 200 记 `ok` 并带 `stop_reason=max_tokens`**（覆写不发生是代码事实；最终标签为 `ok` 是由 `status_code=200` + `status_override is None` 推断）。**同一次回合，日志说「ok / max_tokens」，客户端收到「incomplete」。** 同一个提交的两半对同一个事实给出两个答案。

**一行修法**：`stop_reason=terminal.stop_reason or settings.unterminated_stop_reason`。这既保住了「不得静默变成 `end_turn`」的不变量（`terminal.stop_reason` 为空时仍走配置值），又让上游真说过的话优先。同伴分支正是这么裁的（见 §5）。

### 2.3 [major] `ResponsesAssembler.cut_mid_block` 在全量套件下没有任何鉴别力

`证据等级：一手实测（变异 M7，双向）。分级：major。`

只把 **Responses 腿**的 `cut_mid_block` 改成常量（Anthropic 腿保持原样），跑 `tests/unit tests/int` 全量：

| 变异 | 在位探针 | 结果 |
|---|---|---|
| `ResponsesAssembler.cut_mid_block → True` | `[probe] responses: return True  # MUTATED-M7` / `[probe] anthropic : return bool(self._drafts)` | `1 failed, 1701 passed` |
| `ResponsesAssembler.cut_mid_block → False` | 同上（`return False`） | `1 failed, 1701 passed` |
| 基线（未变异） | — | `1 failed, 1701 passed` |

**两个方向都一条不红。** 那唯一的 `1 failed` 是 `tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses`，与本改动无关，见 §4.1。

这条本身只是覆盖缺口，但它和 §2.1 叠在一起才是要紧的：证据报告实测的 4 条块边界命中**全部在 Responses 腿**（`260822-clean-eof-without-terminal.md` §3.2，Anthropic 腿 32/32 全在块中途）。也就是说，**这条细化唯一会真正触发的那条腿，判据有洞（§2.1）而且一个测试都没有。** 已有的 5 个新测试全部只跑 Anthropic 腿。

**建议**：把 `test_an_eof_between_blocks_...` 与 `test_an_eof_through_a_block_...` 各补一个 `ResponsesAssembler` 版本，其中至少一个覆盖 `_cut_short` 那条路径。这是补测试，不是建门禁。

---

## 3. Minor 发现

### 3.1 [minor] 归属默认归上游时，两个可命名的输入会指错责任方

`证据等级：一手实测（probe Q1 / Q2）。`

三格是**穷尽且互斥**的（代码事实，`if/elif/else` 结构 + `else` 兜底），这一点写对了。默认归上游而不是归自己也是对的判断（见 §6）。两个具体反例：

- **framer 抛错 → `upstream_error` / `upstream_stream_failed`。** 实测：一个 `framer.block()` 抛 `ValueError("no Responses item shape for block kind 'weird'")`（这是 `openai_responses.py:143` 真实存在的抛点），客户端拿到 `{"type":"upstream_error", ..., "code":"upstream_stream_failed"}`。**提交注释已自认这是 known limit**（"A bug in framing would still be attributed to upstream"），所以这条是「已知并记录」而非漏判。但注释没提到的是它还覆盖**操作员配置错误**：`block_frames` 对 `signature_compat == "redacted_thinking"` 抛 `ValueError`，同样落成 `upstream_stream_failed`——配置错误被记在上游账上。
- **本方 attempt deadline → `upstream_error` / `upstream_stream_failed`。** 实测：`StreamDeadlineError("upstream_request_deadline of 600s exceeded")` 落成 `upstream_stream_failed`。这个时钟是本方配置的，`stream.py:331` 的注释也把它明确称作「The attempt deadline (`upstream_request_deadline`, raised by `pipeline_app`'s `with_deadline_at`)」。可辩护的方向是「上游确实太慢」，但那和 `ClientDeadlineError` 被专门分出去归 `INTERNAL` 的处理不一致——两个都是本方的时钟，一个归自己一个归上游。

另有一处次序细节（代码事实，无实测反例）：`DeliveryError` 与 `from_assembly` 同时成立时，`isinstance` 分支先赢，报 `proxy_delivery_aborted`（「本方保护触发」）而不是 `proxy_delivery_failed`（「本方 bug」）。今天两个装配器都不抛 `DeliveryError`，所以不可达；记录以免将来悄悄反转。

### 3.2 [minor] 一条新加的断言在前一条通过的前提下恒真

`证据等级：一手实测（变异 M6）+ 构造性推理。`

`test_an_eof_between_blocks_closes_the_message_without_claiming_success` 里：

```python
assert '"stop_reason":"incomplete"' in body
...
# The whole point of not reverting: a reason upstream never gave must not be the one that means "finished".
assert '"stop_reason":"end_turn"' not in body
```

`framer.terminal` 只发出**一条** `message_delta`，其中只有**一个** `stop_reason`（`message_start` 里那个是 `"stop_reason":null`，字面不匹配）。所以只要前一条断言通过，后一条就**严格蕴含为真**。

M6（把 `replace(terminal, stop_reason=...)` 换成 `framer.terminal(terminal)`，此时 `stop_reason=""` → framer 的 `or "end_turn"` 生效，body 里确实出现 `end_turn`）实测：**红点落在 `'"stop_reason":"incomplete"' in body` 这一条上**，`end_turn` 那条根本没被求值到。

提交信息说这条不变量「is asserted rather than described」，而**它在实践中从未独立击发过**。修法：把 `end_turn` 那条挪到 `incomplete` 那条之前，或改成解析 `message_delta` 载荷后对 `delta.stop_reason` 做等值断言（一条断言同时钉死两个方向）。这是本次唯一一条恒真断言；其余 4 个新测试都有独立鉴别力（见 §4.2）。

### 3.3 [minor] `SlowAssembler.cut_mid_block` 是一个不会失效的桩

`证据等级：代码事实。`

测试桩 `SlowAssembler` 硬返回 `False` 并注明「Never mid-block: this stand-in exists for the timing」。桩本身没问题；值得记的是：**协议加成员时，所有测试桩都要跟着加**，而一个硬编码 `False` 的桩在将来某个 keepalive 测试恰好走到收尾分支时，会给出一个形状正确的假结果。今天不触发。

### 3.4 [minor] 新配置项没有出现在操作员看的配置样例里

`证据等级：一手实测（全仓 grep）。`

`unterminated_stream_stop_reason` 在 `docs/.human-controlled/config.example.yaml` 中**不存在**；该文件里 `client_delivery` 段逐项中英双语注释了 `client_request_deadline`、`buffering_policy` 等。**这个文件是用户亲笔、由用户控制，不归我改也不该由我催**——纯粹作为事实记录：本仓其他 `client_delivery` 设置都在那里有条目，这个新的没有。

### 3.5 [minor] 同一次收尾上两条腿对 usage 的诚实度不一致

见 §1.4 末段。`ResponsesFramer.terminal` 走 `usage = terminal.upstream_usage`，`None` 直接落成 wire 上的 `null`；`AnthropicFramer.terminal` 落成 `{"output_tokens": 0}`。两条腿对同一个「没测过」给出不同答案。Anthropic 腿是被协议逼的（§1.3），所以这条不是要求统一，只是记录这个不对称是有原因的、不要将来被当成 bug 顺手「修齐」。

---

## 4. 测试鉴别力：我自己重跑的变异

按 `trusting-a-green-result` 的协议执行：变异前先跑在位探针（读 `inspect.getsource` 与 `_deliver` 源码文本，独立于被测判据），确认变异在**测试将要读取的那一层**生效；每轮结束还原并 `sha256sum --check`。

### 4.1 基线

`/tmp/rev-78be0d4` 上 `tests/unit/pipeline/delivery/test_stream_delivery.py`：**48 passed in 22.27s**。

全量 `tests/unit tests/int`：**1 failed, 1701 passed**。那条 failed 是 `test_authoritative_example_config_parses`，报 `upstream_request_retry.strategies.streamReplay: Extra inputs are not permitted`——**与本改动无关，在父提交 `ef4defb` 上同样红**（已实测复现）。它是用户亲笔的 `config.example.yaml` 要了一个 schema 没有建模的重试策略。归属清楚，记在这里只为免得下一个人把它算到 `78be0d4` 头上。

**且这条可能已经在工作树里被解掉了**（一手实测，2026-08-22 19:31）：主树的 `docs/.human-controlled/` 有 5 个文件处于未提交修改状态（不是本次评审造成的，本次评审只写了这一份报告），而**工作树版本的 `config.example.yaml` 里已经没有 `streamReplay`**。上面那个红是**提交态**（`78be0d4` 与 `ef4defb` 的 archive 副本）上的事实，工作树上是否仍红需要重测。这一条不影响本报告任何其他结论。

### 4.2 六轮变异（全部在位探针确认后才跑）

| # | 变异 | 探针确认 | 红了几条 | 红在哪 |
|---|---|---|---|---|
| M1 | 两腿 `cut_mid_block → False` | `return False  # MUTATED-M1`（两腿都印出） | 1 | `test_an_eof_through_a_block_is_still_a_truncation` |
| M2 | 删掉 `raise torn` 前的 `yield framer.error(...)` | `_deliver tear-frame code triple present: False` | **2** | `test_an_unassemblable_event_fails_before_the_preamble`、`test_an_upstream_tear_is_framed_and_then_raised` |
| M3 | `ours = isinstance(torn, DeliveryError)`（去掉装配 bug 识别） | `..._or torn is from_assembly: False` | 1 | `test_an_unassemblable_event_fails_before_the_preamble` |
| M4 | 去掉 `and settings.unterminated_stop_reason`（开关失效） | `cut_mid_block gate present: False` | 1 | `test_an_empty_stop_reason_puts_the_clean_eof_back_to_an_error` |
| M5 | 两腿 `cut_mid_block → True` | `return True  # MUTATED-M5` | 1 | `test_an_eof_between_blocks_closes_the_message_without_claiming_success` |
| M6 | 不套用合成 reason（`framer.terminal(terminal)`） | `replace-override present: False` | 1 | 同上（红在 `incomplete` 断言，见 §3.2） |
| M7 | **只**动 Responses 腿，双向常量 | 两腿分别印出、可区分 | **0（两个方向）** | —— 见 §2.3 |

**与实现者自报的对账**：他报「五次受控变异，各只红一条」。我重跑的结果与之**基本相符但有两处修正**：

1. **M2 红的是 2 条不是 1 条**（`test_an_unassemblable_event_fails_before_the_preamble` 也断言 `proxy_delivery_failed` 在 body 里，去掉帧后它同样红）。这是好消息——帧那一半比自报的覆盖更宽。
2. **M7 是他没做的那格**，而它正好是 0。

一处方法学记录：M6 我第一次写的替换吃掉了行尾的 `:`，探针阶段直接 `SyntaxError` 打了回来——**这就是「先证明变异在位、再跑测试」那一步存在的理由**，如果先跑测试，我拿到的会是一个 collection error，形状上很像一次成功的正控。

### 4.3 恒真断言排查

逐条过了 5 个新测试的全部新增断言。**只有一条恒真**（§3.2）。其余：`'"type":"error"' not in body`（M5 击中）、`"incomplete_responses_stream" in/not in body`（M1/M4/M5 击中）、`"message_stop" in/not in body`（M1 击中）、`"upstream_stream_failed" in body`（M2 击中）、`"proxy_delivery_failed" in body`（M2/M3 击中）、`len(synthesised) == 1`（结构上只能由 hand-over 真被调用满足）、`'"text":"one"' in body`（钉住「已交付的块不被收回」，非平凡）。

`assert "message_start" not in body`（装配 bug 测试）鉴别力弱但不恒真——它钉的是既有不变量「失败在有内容之前就不开消息」，M1–M7 都不触及它。不算缺陷。

---

## 5. 「先 yield 再 raise」：实测确认，两半都成立

`证据等级：一手实测（probe P4a / P4b）。结论：实现正确。`

这是本次设计的核心，我按你要求做了独立实测——并且**我的第一次探针给出了假阴性，必须记下来**：

- **第一次用 `starlette.testclient.TestClient`**，客户端侧收到 **0 字节**，`ConnectionError` 从 `client.stream(...)` 抛出。如果我停在这里，就会报一条不存在的 blocker。TestClient 在进程内跑 ASGI 应用，异常在任何字节被收集之前就传播出来了——**它测的是 TestClient 的缓冲行为，不是 wire。**
- **改到真正决定这件事的那一层**（starlette 的 `StreamingResponse` 每 yield 一个 chunk 就 `await send(...)`，所以 `send` 调用序列就是 wire）：

  ```
  P4a raised out of the app: ConnectionError upstream socket went away
  P4a send message types: ['http.response.start', 'http.response.body', ... ]
  P4a has error frame: True
  P4a has upstream_stream_failed: True
  P4a has text one: True
  ```

- **再用真 uvicorn + 真 socket 复核**（`uvicorn.Server` 绑在 127.0.0.1 随机端口，raw socket 发 `GET`，读到 EOF）：

  ```
  HTTP/1.1 200 OK
  ...
  Transfer-Encoding: chunked
  ...
  8d
  event: error
  data: {"type":"error","error":{"type":"upstream_error","message":"upstream socket went away","code":"upstream_stream_failed"}}
  ```
  `P4b has error frame: True` / `P4b has upstream_stream_failed: True` / `P4b has text one: True`。

**两半都成立**：客户端确实拿到了完整的 error 帧（逐字节在 wire 上），调用方确实拿到了异常（`raised out of the app: ConnectionError`），且 `inference.py:636-640` 的 `except Exception` 会把它记进 `accounting.failure`，`_ending()` 返回 `("fail", f"stream failed before a terminal event: {...}")`（代码事实）。

**一个应当写进文档的代价**（实测观察，非缺陷）：raw wire 上**没有 chunked 的终止块 `0\r\n\r\n`**——异常传播出去后连接直接断。所以客户端读到的是「完整的 error 帧 + 一个协议层面不干净的 HTTP 结尾」。同伴分支 f84e821 的注释已经把这一点明确写下来了（"a readable frame is not a clean HTTP ending, and this is the accepted cost rather than an oversight"），**本提交的注释里没有这句**。建议补上——它是一个会被下一个人当成 bug 报上来的现象。

## 5b. `from_assembly` 的身份标记：实测确认，无泄漏

`证据等级：一手实测（probe Q3）+ 代码事实。结论：实现正确。`

- `from_assembly: Exception | None = None` 声明在 `while True:` **内部**，`continue`（重放）回到循环顶端时必然重新初始化（代码事实）。
- 实测：第一次尝试撕断（`ConnectionError`，`eligible` 返回 `NETWORK`）→ `reopen()` 给出第二条流 → 第二条流第一个事件就让装配器抛 `ValueError`。结果：

  ```
  Q3 second attempt ran: True
  Q3 raised: ValueError
  Q3 says proxy_delivery_failed: True
  Q3 says upstream_stream_failed: False
  ```
  第二次尝试的装配 bug 被正确归到本方，**没有继承第一次的上游归属**。
- 反方向（第一次是装配 bug、泄漏到第二次）在结构上不可达：装配 bug ⇒ `ours` ⇒ `reason = None` ⇒ 不进 `REPLAY` 分支 ⇒ 没有第二次。

---

## 6. 实现者做对了的地方（不是凑数，是逐条核过的）

1. **「先 yield 再 raise」在真 wire 上确实两半都成立**（§5）。我的第一版探针给出的假阴性已排除。
2. **`from_assembly` 按 attempt 重置、重放后不泄漏**（§5b），且按身份而非按类型比较的理由（同一个 `ValueError` 在两个抛点意义相反）成立。
3. **`cut_mid_block` 而不是「客户端拿到的都是整块」**——后者在块级交付下恒真、区分不了任何东西。这个判断是对的，而且它正是本仓「恒真判据不是判据」那条经验的正确应用。
4. **三格穷尽且互斥**（代码事实）。
5. **默认归上游而不是归自己是对的裁决**，而且它防的那个反例是真的：Q2 实测里一个纯粹的本方超时如果按「只有调用方命名过才算上游」的旧逻辑，会带着 `internal_error` 到客户端；提交信息里那段 `ConnectionError → internal_error` 的复盘不是事后编的。
6. **error 帧文案去掉 `Responses` 方言名是对的**——这个函数同时服务两条腿，`framer` 是调用方给的，旧文案会在 Anthropic 直连回合上声称回复来自 Responses。

---

## 7. 与同伴分支 `f84e821`（`fix/one-ending-decision`）的实质分歧

`证据等级：代码事实（全部经 git show f84e821:<path> 读取，未进入该工作树）。`

merge-base 是 `4d96af8`；同伴分支自 base 起 6 个提交，main 侧 6 个提交。两份改的是同一段收尾逻辑，**分歧是实质的，不是措辞**：

| # | 主题 | `78be0d4`（main） | `f84e821`（peer） | 合并时必须裁的 |
|---|---|---|---|---|
| a | **「上游算不算说完了」的判据** | `assembler.terminal.seen`（只有 `message_stop` 置位） | `unfinished = failure is not None or (not seen and not stop_reason)`——`message_delta` 给了 reason、只差 `message_stop` 就**算说完了**，走 `framer.terminal(terminal)` 发上游真实 reason | **这正是 §2.2。peer 的裁决与 main 自己的 `inference.py` 一致，与 main 的 `stream.py` 冲突。** |
| b | **干净 EOF 能不能进重放/交接** | 不能。`torn is None` → `break` → 由 `if not terminal.seen:` 尾段独立处理，永不触及 replay/`_hand_over` | 能。命名为 `UpstreamTruncated` 并送进与撕断同一条路径，可被重放、可被交接 | 干净 EOF 是不是一个「待裁决的结局」。这是两份最大的结构分歧 |
| c | **`cut_mid_block` / `unterminated_stream_stop_reason`** | 新增协议成员 + 新增配置项 | **两者都不存在**。所有未完成结局统一走 `_unfinished_ending` / `_unfinished_frame`，总是发一条带上游原话的帧 | squash 合并会按树取一边，**这两个符号会静默消失或静默复活** |
| d | **责任归属的词汇表** | `ours` 判据 + 三个 code（`proxy_delivery_aborted` / `proxy_delivery_failed` / `upstream_stream_failed`） | **这三个符号一个都没有**。改用 `Terminal.failure`（记录上游自己报的 error/`response.failed`）+ `_unfinished_frame` 把上游原话透出去 | 客户端读到的是哪套词汇 |
| e | **无法命名的失败要不要交接** | 要。`if not ours:` 在 `eligible` 之外，注释明写「Naming a failure decides whether another *attempt* is worth funding; it says nothing about whether the client can carry the turn on」 | **不要。** `_hand_over` 写在 `if replay is not None and reason is not None:` **内部**，注释明写「a proxy protection firing, a 400, a 401 and a refusal are all on the side that cannot [go on]」 | **两份对同一扇门给出相反裁决，且各自都写了论证。** 这一条必须由人裁 |
| f | **`Terminal.failure`** | 不存在 | 新字段，且**优先级高于 `seen`**（上游说自己失败了，压过它自己的终止事件） | main 后续提交（`17e7177` 之前）已经在两个装配器里加了上游 error 事件的**日志**但不作用于状态机——peer 的 `failure` 正是「作用于状态机」的那一步 |

**给后续合并的一句话**：a、e 两条是**语义对立**，必须由人裁；c、d 两条是**词汇表二选一**，squash 会静默取一边，合完必须 grep 确认 `cut_mid_block` / `unterminated_stream_stop_reason` / 三个 code 是不是还在（或者是不是不该还在）。b 条 peer 的做法更完整，但它会让 §2.1 那个 `_cut_short` 的洞暴露在更多路径上，**先修 §2.1 再合 b 条**。

---

## 8. 代价与收益是否相称

`依据：260822-clean-eof-without-terminal.md（一手实测，133 929 条上游流）+ 本次实测。`

**代价**：1 个协议成员（两个实现 + 至少 1 个测试桩）、1 个配置项、1 个合成 `stop_reason`、1 个伪造的 usage 零、约 20 行 `stream.py`。

**收益**：4 / 104 可达样本（3.8%），4 / 133 929 全部上游流（0.003%），**全部在 Responses 腿**。

**我的判断（够据此行动）**：

「为 0.003% 引入一个协议成员 + 一个配置项」这笔账**本身是划得来的**——代码代价确实很小，而且它买到的东西不是命中率，是把「上游说完了」和「上游被切断了」变成两个可以分别回答的问题，这个语义分离有独立于频率的价值（同伴分支从完全不同的方向也需要同一个区分，见 §7a）。**所以我不同意「为 0.003% 不值得」这个方向的批评。**

**但在当前形态下这笔账是负的**，理由不是频率而是分布：

- 4/4 的实测命中在 Responses 腿；
- 那条腿的判据有洞（§2.1，`_cut_short` 让「上游明说被切断」读成「没被切断」）；
- 那条腿的判据在全量套件下零鉴别力（§2.3）。

**也就是说，这条细化在它唯一会触发的那条腿上，把「响亮的截断」换成了「可能安静地丢内容」，而没有任何测试会告诉你它做了这件事。** 修掉 §2.1 与 §2.3 之后，这笔账重新变成正的，而且成本只是一行判据 + 两个测试。

一个必须说清的边界：证据报告自己标注了 §5.2 的限制——**本项目自己那 3 次干净 EOF 的块完整性无从得知**（不做帧级留存）。所以「4 条在块边界」这个数字来自 copilot-api-js 的语料，不能直接外推到本项目。这不影响上面的结论（结论依赖的是「命中集中在 Responses 腿」这个**分布**事实，而不是绝对数），但它意味着**真实命中率可能更高也可能更低**。

---

## 9. 复现

只读副本与探针（`/tmp` 可随时删）：

```bash
# 副本
rm -rf /tmp/rev-78be0d4 && mkdir -p /tmp/rev-78be0d4
git -C /home/xp/src/ghc-api-proxy-py archive 78be0d4 | tar -x -C /tmp/rev-78be0d4

# 证明解析（必须先跑这一步）
cd /tmp/rev-78be0d4 && PYTHONPATH=/tmp/rev-78be0d4/src \
  /home/xp/src/ghc-api-proxy-py/.venv/bin/python -c \
  "import app.pipeline.delivery.stream as s; print(s.__file__)"

# 基线
cd /tmp/rev-78be0d4 && PYTHONPATH=/tmp/rev-78be0d4/src \
  /home/xp/src/ghc-api-proxy-py/.venv/bin/python -m pytest \
  tests/unit/pipeline/delivery/test_stream_delivery.py -q -p no:cacheprovider
```

本次写下的探针文件（在副本里，不在主树）：

- `/tmp/rev-78be0d4/tests/unit/pipeline/delivery/test_zz_review_probes.py` —— P1（两腿 usage 零）、P2（stop_reason 被覆盖）、P3/P3b（`_cut_short` 洞）
- `/tmp/rev-78be0d4/tests/unit/pipeline/delivery/test_zz_review_probes_wire.py` —— P4a（ASGI `send` 序列）、P4b（真 uvicorn + raw socket）
- `/tmp/rev-78be0d4/tests/unit/pipeline/delivery/test_zz_review_probes2.py` —— Q1（framer bug 归属）、Q2（attempt deadline 归属）、Q3(`from_assembly` 跨重放)

变异脚本：`/tmp/mutate.sh`（M1–M4）、`/tmp/mutate3.sh`（M5–M6）、`/tmp/mutate4.sh`（M7 双向 + 全量套件）。三个脚本都用 `trap restore INT TERM EXIT` + 冻结副本还原 + `sha256sum --check`，基线校验和在 `/tmp/rev-78be0d4-baseline.sha256`。

**注意**：`tests/unit/pipeline/delivery/test_stream_delivery.py` 单文件跑一次约 22 秒；`tests/unit tests/int` 全量约 103 秒。M7 需要跑两次全量。
