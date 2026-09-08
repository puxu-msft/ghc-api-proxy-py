# 独立评审：六条未被独立看过的提交

**评审对象**：`40d9c76`、`696a786`、`1018e3a`、`bce8b0d`、`fef7d96`、`af84097`（区间内其余提交不在范围）。
**评审基线**：`HEAD = 44fa576`，工作树 `src`／`tests` 在 2026-08-22 12:07 时与 HEAD 逐字节相同（`git status --short -- src tests` 空）。
**评审时间**：2026-08-22 12:00–12:30 UTC。
**结论**：`needs-fix`。两条既有 blocker 的修复**都成立**，且我构造的反例证明它们没有同型的第二个出口；新发现 0 blocker、4 major、11 minor。

> ⚠️ **本报告是时点记录，且时点很短。** 12:15 起有同伴在同一棵工作树上重构 `src/app/pipeline/delivery/` 包（`assembler.py → assembling.py`、`anthropic_sse.py → formats/anthropic_messages.py`、新增 `formats/`、`sse_frame.py`，已 staged 但未提交）。本报告所有行号与文件名以 `44fa576` 为准，重构落地后需要重指。
>
> **工作树安全性核对**：我的五次变异各自在 12:11–12:13 之间用 `/tmp` 字节备份还原，最后一次 `sha256sum -c` 在 12:13:35 通过；同伴文件的 mtime 最早为 12:15。12:07 的 `git status` 为空，说明当时没有同伴的未提交改动可被我的 `cp` 覆盖。**未发生覆盖。**

---

## 0. 摘要

| 级别 | 数量 |
|---|---|
| blocker | 0 |
| major | 4 |
| minor | 11 |
| 查过并确认无问题 | 6 组（见第 5 节，逐项给判据） |

两条 blocker 的复核结论（详见第 1 节）：

- `1018e3a`（重开复用 `RequestContext` 导致二次翻译）——**修对了，且经受住三次重开**。我实测连撕两次、第三次成功，三次上游 body 逐字节相同。
- `bce8b0d`（`decide_stream_ending` 的 COMPLETE 与 ABANDON 被折叠）——**修对了，且在主产品路径上同样成立**。我在 responses 腿上重放「上游发完 `response.completed` 后连接被 reset」，未合成 `tool_use`，`stop_reason` 为 `end_turn`，请求行 `[ OK ]`。

---

## 1. 两条 blocker 的复核（重点 1）

### 1.1 `1018e3a`：重开时的 payload 快照

**判据不是读代码，是构造反例。** 探针让上游连撕两次、第三次成功，断言三次发往上游的 body 相同：

```
B1 attempts: 3
  attempt 0: {"model":"gpt-model","input":[{...user "one"...},{...assistant "two"...}],"stream":true}
  attempt 1: 同上，逐字节相同
  attempt 2: 同上，逐字节相同
```

`context.payload = deepcopy(inbound_payload)`（`pipeline_app.py:659`）在**每一次**重开前执行，不是只在第一次，所以 N 次重开都成立。

**同型第二出口的排查**（逐项，均为否）：

| 候选 | 结论 | 判据 |
|---|---|---|
| `strip_attribution_lines` 二次剥离 | 否 | 它在 `pipeline_app.py:425-428` 执行，`inbound_payload` 在 `:490` 才快照，所以快照里已经是剥离后的版本，重开不会再剥一次 |
| `context.extras["conversion_losses"]` 跨 attempt 累积 | 只有观测面影响 | `handle` 每次翻译都整体覆盖该键；若第 1 次有损、第 2 次无损，第 1 次的记录会残留。这是「报告了没发生在最终 attempt 上的损失」，不影响发出的 body。列为 minor-10 之外的观察，不单独计数 |
| `context.attempts` 累积 | 期望行为 | `attempt_count` 正是 `1018e3a` 要刷新的观测面 |
| 非流式路径同样复用 context | 不适用 | 非流式没有重开入口 |
| `count_tokens` 路径 | 不适用 | 同上 |
| 重开后 framer 不重建 | 见 minor-12 | 分离问题，不是二次翻译 |

**变异检验 M2**：删掉 `context.payload = deepcopy(inbound_payload)` 那一行 → `test_a_replay_on_the_translation_leg_sends_the_conversation_again` 转红，报 `{'model': 'gpt-model', 'input': [], 'stream': True}`（正是 blocker 的原始症状）。还原后 sha256 与变异前一致。

### 1.2 `bce8b0d`：COMPLETE 与 ABANDON 的分离

**代码**：`stream.py:332-336`，`if verdict.ending is StreamEnding.COMPLETE: break`，排在 REPLAY 判定之前。

**主路径反例**（`bce8b0d` 自己的回归测试只跑 anthropic 直连腿，见 minor-1）：我在 responses 腿上重放同一形态——

```
B2: upstream 发完 output_item.done + response.completed，然后 RemoteProtocolError
    → delivered 不含 turn_interrupted
    → message_delta 的 stop_reason = end_turn
    → 请求记录 status = ok
```

**同型第二出口的排查**：

| 候选折叠点 | 结论 |
|---|---|
| `terminal.seen` 在 anthropic 腿只由 `message_stop` 置位，`message_delta{stop_reason}` 之后撕流仍走 ABANDON，category 报 `network` 而非 `max_tokens` | **是一处语义模糊，但不是折叠**：那一刻上游确实没说完（`message_stop` 未到），两种解读都讲得通，且 `deferred.md` §11 已登记相邻问题。不计为发现 |
| responses 腿 `response.incomplete` 也置 `seen=True`，于是 max_tokens + 撕流 → COMPLETE → 落到 `stream.py:365` 的 max_tokens 交接分支 | **正确**，B3 实测：交接发生，`category=max_tokens` |
| `_hand_over` 在一次 `_deliver` 里被调用两次 | 结构上不可能：两个调用点各自 `return`。但守卫被删了，见 minor-3 |
| `decide_stream_ending` 的 `committed_blocks == 0` 分支 | live 链路不可达，见 minor-7 |

**变异检验 M1**：把该分支改成 `if False and ...` → `test_a_turn_upstream_finished_is_not_handed_back_when_the_connection_goes_after` 转红。**只有这一条转红**，见 minor-1。还原后 sha256 一致。

**bce8b0d 的另外两处修复也复核了**：

- `_hand_over` 的 `started = session.started` 提到 `session.finish()` 之前（`stream.py:423`）——B5 实测：anthropic 腿 max_tokens 且零内容块时，`message_start` 正常发出，客户端拿到 preamble + `tool_use` + terminal，不是空 200。
- `session.started` 与 `committed_count > 0` 在 `blocks.py:151-156` 是同一事实（`_commit` 同时置两者），所以旧写法 `if remaining and not session.started` 的确会在「flush 之后再问」时永远为真。修复的推理成立。

---

## 2. major

### major-1：同一条上游回复，流式与非流式给出两套观测事实（`af84097`）

**位置**：`src/app/server/pipeline_app.py:759-780`（非流式追加块之后才调 `reply_summary`）对 `src/app/pipeline/delivery/stream.py:432`（流式用 `replace(assembler.terminal, ...)` 造副本，不改 `assembler.terminal`）。

**实测**。同一个上游回复（Responses，`incomplete_details.reason = max_output_tokens`，output = [完整 message, `status:"incomplete"` message]）：

| | 客户端拿到的 wire | 请求记录 `stop_reason` | `blocks` | `tools` | 控制台行 |
|---|---|---|---|---|---|
| 流式 (B3/probe) | `stop_reason: tool_use` + `turn_interrupted` 块 | `max_tokens` | 1 | `[]` | `… max_tokens: turn handed back to the client to continue` |
| 非流式 (B4/probe) | 同上 | **`tool_use`** | **2** | **`['mcp__plugin_…turn_interrupted']`** | `… function_call(mcp__plugin_…turn_interrupted): turn handed back…` |

**为什么错**。三点，任一独立成立：

1. **这正是 `fef7d96` 自己要消灭的形态。** 该提交的信息写着「the same upstream reply was described two different ways depending on which route read it… it makes the fact unreadable from the outside」。`af84097` 在同一主题上把它按回到了观测面。
2. **非流式的请求行报了一个模型从未请求过的工具。** `tools` 字段的契约是「这一轮模型要了哪些工具」（`assembler.py:56` 的注释自述），把代理自己合成的块记进去，使这个字段在非流式路径上不可信——读者无法区分「模型真调了 turn_interrupted」和「代理替它调的」。
3. **上游给出的 `max_tokens` 在非流式的请求行上彻底消失。** `decisions.md` §2 #8「`stop_reason` 不得被改写……原样透出」的意图是让这个事实可读；wire 上改成 `tool_use` 是裁决要的（这一轮确实变成了工具调用），但**观测行**应当仍报上游那一段（项目记忆：可观测性描述的是上游那一段）。流式那条做对了，非流式没有。

**建议**：非流式在追加 `handed` **之前**取一次 `reply_summary`，用它填 `trace`；或者显式记录两套（`trace.stop_reason` 取上游的、`trace.detail` 已经说了交接）。倾向前者——它让两条路径读的是同一件事实，且不需要新字段。

### major-2：截断块的丢弃超出了裁决范围，且在超出的那一段里没有交接兜底（`af84097`）

**位置**：`src/app/pipeline/translation_driver/responses.py:148`。

```python
if str(item.get("status", "")) == "incomplete" and response.blocks:
```

**裁决原文**（`decisions.md` §2 #1）：「**`max_tokens` 时**，只有未完成块就保留它；有任何完整块就丢弃未完成块。」丢弃规则是**挂在 `max_tokens` 上的**。实现挂在 `item.status` 上，于是覆盖了所有 `incomplete_details.reason`。

**实测**（`content_filter`，同样两个 item）：

```
CF NONSTREAM content: [{"type":"text","text":"whole"}]      ← "half" 被丢掉了
CF NONSTREAM stop_reason: content_filter
CF NONSTREAM 请求行 status: ok
```

交接不会发生，因为 `_HANDED_OVER_STOP_REASONS == {"max_tokens"}`（`stream.py:395`）。于是：**客户端少了一段内容，没有任何拿回来的途径，请求行还报 `[ OK ]`。**

`af84097` 的提交信息把这个防线写成绝对的：「dropping content is only defensible when the client is handed a way to get it back」。它自己的代码在 `reason != max_output_tokens` 时违反了这句话。

**范围划分要说清楚**：流式那一侧的同型缺陷是 `66b63c9`（不在本次范围）留下的，`af84097` 做的是把它**复制到非流式**。所以「两条路径一致」这个目标达到了，代价是把缺陷也对齐了。这一条记在 `af84097` 账上是因为它新造了一个实例，并给出了一句站不住的辩护。

**建议**（择一，倾向第一个）：

1. 把丢弃条件收窄到裁决说的范围——`response.status == "incomplete"` 且 `reason == "max_output_tokens"` 时才丢；其余原样带过去。流式侧同步收窄（属 `66b63c9` 的账，可另开切片）。
2. 或者把 `_HANDED_OVER_STOP_REASONS` 扩到「所有 incomplete 结局」，让丢弃处处有兜底。但这需要用户裁决——`content_filter` 是否可续写，人写文档没说，而 `refusal` 明确归「无法继续」。

**不要**自行选 2 而不问：那等于替用户裁决 `content_filter` 的可续性。

### major-3：`max_tokens_as_retryable` 的删除与已记录的裁决直接冲突，且没有任何裁决记录（`fef7d96`）

**位置**：`fef7d96` 删掉 `src/app/config/schema.py` 的 `max_tokens_as_retryable: bool = True`。提交信息写「both as the user directed」。

**冲突的记录有两处，都还在生效**：

- `decisions.md` §2 #12：「**删码范围**：只删代理内续写机制本身，**其他未接线的功能不要动**。」
- `status.md:62`：「**明确不动**：……`streamReplay`、`hedge`、`max_tokens_as_retryable`。用户 2026-08-21 裁决：『现有代理内续写机制从代码中删除，其他未接线的功能不要动』。」
- `deferred.md:71`：「**用户 2026-08-21 裁决：只删代理内续写机制，其他未接线的功能不要动。** 所以除 `continuation.*` 外一律保留。」

`streamReplay` 的删除**有**记录（`decisions.md` §2之二 #15，2026-08-22 用户裁决），`max_tokens_as_retryable` 的删除**没有**。

**为什么这不是吹毛求疵**。`decisions.md` 开篇自己写明它为什么存在：2026-08-21 的独立评审因为 `.dev` 里查不到口头裁决，把已裁决的内容误判成「照未经裁决的建议施工」。这份文件是为了防止同一件事再发生而建的，而 `fef7d96` 恰好绕过了它。下一位评审面对的证据状态与那次完全相同。

**建议**：在 `decisions.md` §2之二 补一条（时间、场合、原话转述、理由），并同步改 `status.md:62` 与 `deferred.md:71`。如果那次裁决其实不存在，则应回退该删除。**这一条我不能替你判定**——我只能看到 `.dev` 里没有它。

### major-4：`status.md` 与 `decisions.md` 有四处已被本区间作废的陈述（`sync-live-docs-timely` 是 `[hard]`）

`status.md` 的 mtime 是 10:55，早于 `bce8b0d`(11:20)、`fef7d96`(11:35)、`af84097`(11:56)。逐条：

| 位置 | 现在说的 | 事实 | 作废它的提交 |
|---|---|---|---|
| `status.md:62`、`:27`、`deferred.md:71` | `max_tokens_as_retryable` 明确不动 / 仍是死配置项 | 已删除 | `fef7d96` |
| `status.md` E 组表 | 只有 `66b63c9`、`e81f07f` 两行 | 还有 `bce8b0d`、`fef7d96`、`af84097` | 三者 |
| `status.md` E 组原计划条目 | 「配置项 `client_delivery.auto_retry_tool_call_full_name` 可覆盖工具全名」 | 已迁到 `upstream_request_retry.` | `fef7d96` |
| `decisions.md` §一 索引表「工具全名可由 `client_delivery.auto_retry_tool_call_full_name` 覆盖 \| 第 35 行」 | 同上 | 人写文档第 35 行写的就是 `upstream_request_retry.`——**索引行从一开始就抄错了权威**，`fef7d96` 让代码对齐了权威，索引行反而更显眼 | — |

另外 `deferred.md` §6「流式与非流式对同一事实给出不同答案」描述的正是 `fef7d96` 修掉的那件事，条目未销账。

**建议**：把 E 组表补齐（含每条的变异检验结论），改掉上面四处，把 `deferred.md` §6 移到「已闭合」或直接删除并在 `status.md` 记一笔。

---

## 3. minor

**minor-1｜`bce8b0d` 的 blocker 回归测试仍长在非主路径样本上。**
`tests/int/test_pipeline_app.py::test_a_turn_upstream_finished_is_not_handed_back_when_the_connection_goes_after` 经 `_delivered()`（`:2321`）发请求，而 `_delivered` 写死 `{"model": "claude-model", "messages": [], "stream": True}`——anthropic 直连腿，且空对话。变异 M1 只被这一条捕获。主路径（anthropic 进／responses 出）上这条判据无覆盖。我实测（B2）行为是对的，所以这是**覆盖缺口而非缺陷**，但它与该提交自己批评的「the test that should have caught it was itself built on the wrong sample」是同一形状。建议：把 B2 的形态补成一条 responses 腿的测试。

**minor-2｜非流式 `num_messages` 没有非空样本。**
`af84097` 改写的 `test_max_output_tokens_becomes_the_anthropic_stop_reason`（`:800`）post 的是 `"messages": []`，`num_messages` 恒为 0——正是 `bce8b0d` 提交信息点名的那种「零在两种读法下都相等」的空断言。变异 M5（把非流式的 `_client_message_count(inbound_payload)` 改成读 `context.payload`）只被流式那条 `test_a_hand_back_on_the_translation_leg_counts_the_client_s_own_messages` 捕获；今天两条路径共用 `_hand_back`，所以还有覆盖，一旦分家就没有了。建议：给那条测试三条消息。

**minor-3｜`accounting.handed_over` 的「一轮一次」守卫被删了，不变式改由控制流隐式保证。**
`af84097` 把 `_hand_back` 提到外层时，删掉了 `if accounting.handed_over: return None`（原 `pipeline_app.py:656-658`），只在 `_hand_back_streaming`（`:696-707`）里保留了置位。我核对过 `_deliver` 的两个 `_hand_over` 调用点各自 `return`，所以今天调用不到第二次；但守卫原来的价值就是「即使控制流变了也不会合成第二个结局」。这个项目已经在「守卫被留在别处」上翻过车。建议：把该判定放回 `_hand_back_streaming` 的开头。

**minor-4｜`_CATEGORY_FOR_REASON` 从 `.get(…, default)` 改成下标，新增 `RetryReason` 会在交付路径抛 `KeyError`。**
`pipeline_app.py:575-577`。今天 `RetryReason` 只有三个成员且都在表里，所以不可达；但它位于交付生成器内部，抛出会直接杀掉客户端这一轮。建议：改回带默认值的读法，或在表旁写一条断言把它变成启动期错误。

**minor-5｜`_hand_back` 的工具声明检查读的是已翻译的 `context.payload`，与同函数内 `num_messages` 的判据不一致。**
`pipeline_app.py:557`。`_client_message_count(inbound_payload)` 明确读快照并在注释里解释了为什么（`:584`），而三行之上的 `declared = context.payload.get("tools")` 读的是被 `handle` 就地翻译过的 body。我实测两条腿都碰巧成立：Responses function tool 保留顶层 `name`（探针实证 `{"name":"mcp__plugin_…","description":"d","type":"function","parameters":{…}}`，未告警），anthropic 腿本来就是 `name`。**没有当前缺陷**，但两个相邻判据用两个不同的数据源，是下一个人踩的坑。建议统一读 `inbound_payload`。

**minor-6｜非流式路径在 `content` 不是 list 时静默丢弃已构造好的 `handed`。**
`pipeline_app.py:773-780`：`_hand_back` 已经执行（包括打出 `auto_retry_tool_not_declared` 警告、消耗一个 uuid），随后 `if isinstance(content, list)` 不成立就什么都不做，回复照原样发出，`status_override` 也不设。这是 `never-swallow-errors` 的形态。建议：把 `content` 的形状检查提到 `_hand_back` 之前，或在 else 分支记一条日志。

**minor-7｜`decide_stream_ending` 的 `committed_blocks == 0` 分支在 live 链路已不可达。**
`retry.py:144-149`。`downstream_opened` 由 `client_has_bytes.is_set()` 供给，而它只在 `_commit` 产出块时置位（`stream.py:295`），所以 `downstream_opened and committed_blocks == 0` 结构上不可达——`decisions.md` §三.2 那条推论说的正是这个状态不再可达。`40d9c76` 明确选择保留（「The two ending routes are held apart」）。这与 `696a786` 自己在提交信息里立的原则（「a branch with no producer is what this project keeps finding written and unwired」）相左。**不建议现在删**（它是纯函数、有单测、REPLAY/ABANDON 的接线还可能变），但建议在 `retry.py` 的 docstring 里写明「今天没有生产调用方会走到这一格，前提是 `message_start` 不再单独发出」，让下一个读者不必重新推一遍。

**minor-8｜反方向（`/responses` 客户端 + Anthropic 上游）仍在抹平，`fef7d96` 只修了一个方向。**
实测（probe C，`translation_driver/responses.py:180-190` 的 `to_openai_responses_response`）：

```
anthropic stop_reason='max_tokens'     -> responses status='incomplete'  incomplete_details=None
anthropic stop_reason='refusal'        -> responses status='completed'   incomplete_details=None
anthropic stop_reason='stop_sequence'  -> responses status='completed'   incomplete_details=None
```

`refusal` 被报成 `completed`——与 `fef7d96` 消灭的那个形态同构；`max_tokens` 虽然报 `incomplete`，但 `incomplete_details` 从不生成，客户端读不到原因。这条路由是 served 的（`/responses` + `claude-model`）。不是主产品路径，故为 minor。建议登记进 `deferred.md`，或在 `to_openai_responses_response` 里补 `incomplete_details`。

**minor-9｜`696a786` 的提交信息丢字。**
原文：`A response that says it is incomplete without saying why gets , which is still upstream's word for it`——`incomplete` 一词缺失（`git show 696a786 --format=%B --no-patch | cat -A` 确认，不是渲染问题）。历史已发布，不建议重写；`fef7d96` 的信息里同一句话是完整的，可视为已有对照。登记以免后来者读到一句无主语的话。

**minor-10｜`deferred.md` §12 的归因指向一个不可达的提交。**
条目写「`c86712d` 引入」。`c86712d` 是一个存在但**不被任何 ref 引用**的对象（`git log --oneline --all` 无命中），`main` 上承载同一语义的是 `bce8b0d`。项目记忆里「归因写下前先核 `--stat`」说的正是这一类。建议改指 `bce8b0d`，并保留 `c86712d` 作为原始来源的旁注。
顺带确认：§12 描述的「reset 事实不留痕」我复测仍然成立（B2 的记录 `detail` 为空，`torn` 在 `break` 后被丢弃），**已在册，不重复计为新发现**。

**minor-11｜非流式的丢弃规则注释没有复述 reasoning item 的盲区。**
`responses.py:149-158` 写「Same rule as the streaming assembler applies」，但流式那边（`assembler.py:306`）明确记了「A `reasoning` item carries no `status` at all……Left open deliberately; `deferred.md` 2」。非流式继承同一盲区却没说。建议补一句并指向 `deferred.md` §2。

**minor-12｜重开不重建 framer。**
`_reopen`（`pipeline_app.py:651-694`）刷新了 assembler、buffer、attempt 计数，但 `framer` 是在循环外用第一次的 `context.id` / `context.resolved_model` 建的（`:594-599`）。若重开时路由解析到不同的模型，客户端收到的 `message_start.model` 仍是第一次的。今天路由对同一请求是确定的，所以不可达；登记以免将来加入模型回退时无声出错。

---

## 4. 变异抽查（5 处，全部转红，全部 sha256 核对还原）

方法：`cp` 到 `/tmp/rev-probe/bak/` 留字节备份 → 改坏 → 跑 → `cp` 还原 → `sha256sum -c` 比对。

| # | 变异 | 目标行为 | 结果 | 捕获者 |
|---|---|---|---|---|
| M1 | `stream.py:332` 的 COMPLETE 分支改成 `if False and …` | `bce8b0d` blocker | 红（1 条） | `test_a_turn_upstream_finished_is_not_handed_back_when_the_connection_goes_after` |
| M2 | 删 `pipeline_app.py:659` 的 `context.payload = deepcopy(inbound_payload)` | `1018e3a` blocker | 红（1 条），报 `input: []` | `test_a_replay_on_the_translation_leg_sends_the_conversation_again` |
| M3 | `responses.py:148` 去掉 `and response.blocks`，无条件丢弃 | `af84097` 的「只有它时保留」 | 红（1 条） | `test_the_item_upstream_cut_short_is_kept_when_it_is_all_there_is` |
| M4 | `pipeline_app.py:761` 的交接门改成 `if False` | `af84097` 非流式交接 | 红（1 条），`'max_tokens' == 'tool_use'` | `test_max_output_tokens_becomes_the_anthropic_stop_reason` |
| M5 | 非流式 `num_messages` 改读 `context.payload` | `bce8b0d` 的主路径计数 | 红（1 条） | `test_a_hand_back_on_the_translation_leg_counts_the_client_s_own_messages`（流式那条，见 minor-2） |

还原核对：

```
$ sha256sum -c /tmp/rev-probe/bak/BEFORE.sha256
src/app/pipeline/delivery/stream.py: OK
src/app/server/pipeline_app.py: OK
src/app/pipeline/translation_driver/responses.py: OK
```

**变异结果证明了什么、没证明什么**：五条都只有**一条**测试转红，说明这些新行为各自恰好有一处判据、没有冗余；也说明**判据的样本选择就是全部防线**——M1 与 M5 的唯一捕获者分别落在非主路径样本和另一条路径上（minor-1、minor-2）。变异对**没有测试的地方一言不发**：major-1 与 major-2 都不是变异找到的，是构造上游回复直接读输出读出来的。

---

## 5. 查过并确认无问题的方面（判据逐项给出）

**5.1 `40d9c76` 的删除干净度（重点 4）——干净，既没删多也没留孤儿。**
全仓 `rg -n "continuation_messages|ContinuationStrategyConfig|StreamEnding.CONTINUE|RetryReason.CONTINUATION|strategies.continuation" src tests docs .dev/docs`：`src` 与 `tests` **零命中**；`.dev` 的 17 处命中全部落在 report 原件与 archive 目录（时点记录，按项目规则不改写），加 `status.md:60`（描述该删除任务本身）与 `h2-goaway/deferred.md:33`／`findings.md`（已带移交注记）。
删多的排查：`RetryReason.STREAM_REPLAY` 在 `40d9c76` 时被保留，后由区间外的 `9aa31f9` 删除，`limit_for` 与之同步；HEAD 上 `retry.py` 无悬挂引用，`uv run ruff check` 与 `pyright` 对该文件均无告警。

**5.2 `[RETY]` 的宽度主张——成立，无残留。**
`rg -n "RETRY" src tests -g '!*.md'` 的 15 处命中全是 `RETRYABLE_STATUSES` / `Disposition.RETRY` / `PipelineRetry` 等无关标识符，没有一处是日志前缀。`logging.py` 里其余前缀 `[FAIL]`、`[GONE]`、`[WARN]`、`[<-->]`、`[DRIN]`、`[....]` 均为 6 字符含括号，`[RETRY]` 为 7，`[RETY]` 为 6——「所有前缀 6 字符宽，只有它 7 字符」这个主张我逐个数过，成立。

**5.3 第三条抹平路径（重点 3）——served app 内没有第三条。**
`rg -n '"end_turn"|END_TURN' src/app` 的全部生产者：
- 新链路：`assembler.py:355-359`（已按 `696a786` 修）、`translation_driver/responses.py:135`（已按 `fef7d96` 修）、`stream.py:389` 与 `anthropic_sse.py:237` 的 `or "end_turn"`（只在见过终结事件且上游给了空串时填补，注释自述且成立）、`synthetic.py`（代理自写的回复，本就是 end_turn）。
- 旧链路：`protocols/responses_anthropic.py:130`（**连 `max_output_tokens` 都抹平**）与 `delivery/responses_anthropic_stream.py:271-276`。二者的唯一调用方是 `app/anthropic/client.py` 与 legacy 交付层。
**是否 served**：`src/app/cli.py:23,139,165` 只挂 `create_pipeline_app`，`app_factory.create_app` 无 CLI 调用方。Gemini／Azure 路由（`src/app/routes/gemini.py`、`tests/int/test_azure_routes.py`）同属未挂载的旧链路。`/chat/completions` 与 `/responses` 的入站在新链路上是直通，不经 stop_reason 映射。
**唯一仍在 served 路径上抹平的是反方向**，即 minor-8。

**5.4 `af84097` 的边界规则在各形态下的表现——实测七种，均符合裁决或有正当理由。**

| 形态 | 结果 | 判定 |
|---|---|---|
| responses 腿，[完整, 截断]，max_tokens，非流式 | 丢截断，追加 `tool_use` | 符合裁决 §2 #1 |
| responses 腿，[截断] 独此一块，max_tokens，非流式 | **保留** `half` + 追加 `tool_use`（B4） | 符合「只有它时保留」 |
| responses 腿，同上但流式 | 保留 `half` + `tool_use`（B3） | 与非流式一致 |
| output 为空 + max_tokens | `content` 从 `[]` 变 `[tool_use]` | 交接是整轮唯一内容，符合 |
| anthropic 直连腿，非流式，max_tokens，两块 | **两块都保留** + 追加 `tool_use` | 该腿没有 item status，无法识别截断块；保留是安全方向。**但没有任何文档说明这条腿与 responses 腿的丢弃行为不同**，建议补一句（并入 major-4 的文档修正） |
| `web_search_call` | Responses 该 item 的 status 枚举无 `incomplete`；即便有，两条路径都会丢并渲染成 TEXT | 一致 |
| `reasoning` item | 无 `status`，两条路径都看不见截断 | 一致，`deferred.md` §2 已在册（见 minor-11） |

**追加块之后 `content` 的自洽性**：Anthropic 非流式 content 块**不带 `index` 字段**（B4 的 wire 输出实证），所以不存在编号错位；`tool_use` 追加在末位；`stop_reason` 改成 `tool_use`——与流式那条 wire 上完全一致。**唯一不自洽的是观测面**，即 major-1。

**5.5 静态检查——`ruff` 全绿；`pyright` 的 21 个错误全在本区间之外。**
`uv run ruff check src tests` → `All checks passed!`。
`uv run pyright src tests` → 21 errors，全部落在 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`（同伴的切片，对应未追踪的 `exp/260820-h2-stream-cap/`）。本区间改过的三个文件零告警——包括 `pipeline_app.py:43` 那个带 `# pyright: ignore[reportPrivateUsage]` 的 `_HANDED_OVER_STOP_REASONS` 导入。

**5.6 测试基线。**
- 12:08，clean tree，目标子集 `tests/int/test_pipeline_app.py tests/unit/pipeline tests/unit/observability/test_logging.py`：**571 passed**。
- 12:15 全量 `uv run pytest tests`：1713 passed / 3 failed / 2 skipped。三条红都不在本区间账上：
  1. `tests/systemd/test_systemd_pipeline_unit.py` 超时——既有，任务简报已声明。
  2. `tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses`——**失败原因与任务简报所述不符**：现在报的是 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags: Extra inputs are not permitted`，不是 `streamReplay:`。`docs/.human-controlled/config.example.yaml` 里 `continuation`／`streamReplay`／`max_tokens_as_retryable` 三个键**都已不在**（`rg` 确认只剩两条散文提及和 `auto_retry_tool_call_full_name:337`）。也就是说 `40d9c76` 故意留下的那道红**已经被用户清掉了**，现在这条红是另一件事（用户文件里的新键还没建模）。
  3. `tests/unit/test_module_boundaries.py::test_the_new_chain_does_not_drag_in_the_existing_one`——同伴正在飞的 delivery 包重构：`src/app/pipeline/delivery/__init__.py:3` 仍 import `anthropic_sse`，而该文件已被 staged-rename 成 `formats/anthropic_messages.py`。中间态，不是本区间的问题。

---

## 6. 「把未观测说成已确认」的排查（重点 5）

逐条读了六个提交的注释与提交信息，找绝对化措辞、丢失的样本边界、把推论写成裁决：

| 陈述 | 判定 |
|---|---|
| `696a786`：「Claude Code's own schema for this field is a nullable string with no enumeration and its readers compare against known values and skip the rest」 | **未标注证据来源与权重档**。这是关于第三方客户端行为的断言，`.dev` 里我没找到支撑它的实测或读码记录。它承担的是「透出未知词不会伤到客户端」这个安全性论证的全部重量。建议补出处或降级措辞。不单独计为 minor，因为它是注释而非行为 |
| `assembler.py:306`：「A `reasoning` item carries no `status` at all — verified against a completed one, whose key set is identical」 | **写法正确**：说了验证方式、样本（一个 completed item），没有推广成「不可能有」。`deferred.md` §2 也在册 |
| `assembler.py:300`：「Measured 15 times, four of them on a `function_call`」 | **写法正确**：给了样本量 |
| `af84097`：「dropping content is only defensible when the client is handed a way to get it back」 | **这一条是把一个只在 max_tokens 下成立的辩护写成了无条件的**。见 major-2 |
| `pipeline_app.py:826`（区间外，但被 bce8b0d 的修复依赖）：「a review measured that `drained` and `failure` cannot both be set today……Do not go looking for the state」 | **写法正确**：说了它今天为什么不可达、以及什么改动会让它可达 |
| `retry.py:124`：「Ruled 2026-08-20; see `.dev/docs/upstream/h2-goaway/findings.md`」 | 对得上，`findings.md:80` 有 |
| `fef7d96`：「both as the user directed」 | **无出处**，见 major-3 |
| `1018e3a`：「Measured 2026-08-22 on the primary path: the second attempt went out as `{...}`」 | **写法正确**：给了具体观测值，我用 M2 复现了同一个值 |
| `1018e3a`：「a two-second deadline let a replayed body run six」 | 未复测（代价高，且 `test_a_replayed_body_is_still_held_to_the_client_deadline` 在跑）。**登记为未复核项，不是发现** |
| `decisions.md` §三 的三条推论 | 都在「本项目推论，**不是裁决**（前提变了即失效）」标题下，并各自写了前提。**写法正确** |

---

## 7. 交回给主会话的判断项

1. **major-2 的两个修法二选一需要用户裁决**（`content_filter` 是否可续写）。我不替选。
2. **major-3 需要用户确认**「删 `max_tokens_as_retryable`」这条裁决是否真的存在。若存在，补记录；若不存在，回退删除。
3. major-1、major-4 与全部 minor 属于可直接施工的范围，不需要新裁决。
4. 同伴的 delivery 包重构落地后，本报告第 1–3 节的所有行号需要重指；**报告原件不改**，请在 `status.md` 里做重指。
