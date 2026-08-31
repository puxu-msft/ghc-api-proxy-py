# 直连透传接线评审（`worktree-260831-passthrough-wiring` @ `b9195f4`）

日期：2026-08-31
评审者：独立评审 agent（叶子执行者）
被评对象：worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260831-passthrough-wiring`，分支 `worktree-260831-passthrough-wiring`，HEAD `b9195f4`，基线 `main` 的 `01c33f1`，共六笔提交
判据来源：`.dev/docs/direct-passthrough/spec.md`（**磁盘上的实际版本是 DRAFT v10**，见 F-05）、`plan.md`（v10）、`deferred.md`（D-1～D-5）、`.claude/rules/00-development-workflow.md`、`docs/.human-controlled/`；`.dev` HEAD `68a95b3`

> 本文原定落在 `.dev/docs/direct-passthrough/reports/260831-review-wiring.md`，被主树写入守卫拒绝，按派发约定落在 `/tmp/ghc-review-wiring/`。搬运命令见文末。

## 总体结论

**verdict：needs-fix。不建议以当前状态合入 `main`。**

- blocker：**1**
- major：**4**
- minor：**4**
- nit：**2**
- 主观建议：2

功能主线是对的：`custom_tool_call` 确实能完整到达客户端，issue #2／#3 的根因（按上游方言选 assembler）确实被切掉了，翻译腿的 `REJECT` 确实保留着。**但透传腿的所有非正常收尾路径都坏了，而且是静默坏的**——上游撕流、无终局 EOF、item 未闭合三种情形下，客户端拿到的是一个 200、若干（或零）字节、没有任何 error 帧，异常被吞掉，完成行记 `ok`。1993 个测试全绿看不见这一整族，因为没有任何测试在透传腿上走过这三条路。

## 评审范围

**看了**：`git log --oneline 01c33f1..b9195f4` 六笔的完整 diff 与合并后的最终状态；`delivery_policy.py`、`delivery/passthrough.py`、`delivery/blocks.py`、`delivery/framing.py`、`delivery/stream.py`、`delivery/assembling.py`、`formats/openai_responses.py`、`formats/openai_responses_passthrough.py`、`formats/anthropic_messages.py`、`formats/anthropic_messages_passthrough.py`；接线的调用侧 `server/routes/inference.py`（streaming 分支全段）、`pipeline/routing.py` 的 `decide_route`、`pipeline/driver.py` 的 `shape_request`／`handle`、`pipeline/reply.py`、`pipeline/hand_over.py` 的门；`tests/unit/pipeline/delivery/test_responses_passthrough.py`、`test_anthropic_passthrough.py`、`tests/int/test_pipeline_app.py` 的直连腿段落；`tests/int/cassettes/` 五份全部。

**跑了**：完整套件基线一次（1993 passed／2 skipped／117s）、`ruff check src tests`（clean）、`uv run pyright src tests`（0 errors）；7 次变异各跑一次完整套件；6 个自写探针（`/tmp/ghc-review-wiring/probe1..6.py`，均以 `PYTHONPATH=src uv run python` 在该 worktree 内运行，不写入 worktree）。

**没看的面**（明确声明）：Spec §9.1 的响应头合同（plan 第 9 步，本轮未做，不在本次改动范围）；§10 的可观测迁移（plan 第 10 步，同上，但 F-06 是本轮改动引入的、不属于该步）；非流式路径只核到「未被本轮改动触及」为止；Anthropic 直连腿只读代码与单测，未接线故未跑端到端；`docs/.human-controlled/` 只读了与本腿相关的 `message-format-reshape.md`、`config.example.yaml`、`upstream-retry-and-continuation.md` 三处引文；TUI、cassette 重录、性能均未涉及。

---

## blocker

### F-01　透传腿上 `response.created` 就把 `terminal.seen` 置真，于是所有终局缺失的收尾全部静默成功

- **严重级别**：blocker
- **primary_location**：`src/app/pipeline/delivery/formats/openai_responses_passthrough.py:96-107`（`_read_terminal` 无条件转调）
- **related_locations**：`src/app/pipeline/delivery/formats/openai_responses.py:689`（`read_responses_terminal` 第一行 `terminal.seen = True`）；`src/app/pipeline/delivery/passthrough.py:170-174`（对**每个** envelope 事件调用 `read_terminal`）；`src/app/pipeline/delivery/stream.py:434`、`:519`、`:533-538`（三处消费 `terminal.seen`）；`src/app/observability/request_trace.py:191`（`terminal_seen` 上完成行）

**判据**：Spec §5「首个原生事件提交前……可在统一预算内**透明 replay**」；§5.1「**clean EOF 且无终局**……按既有 taxonomy 视作可重试的截断。用尽预算后仍无终局时，写 proxy error（§8），**不得**合成成功 terminal」；§8「**无终局 EOF**：本腿不得伪造成功终局」；§10「无法分类时**必须**明确记为 unknown，**不得**伪装成 absent」。另有本仓自己的设计意图：`passthrough.py:171` 的注释写着「Each dialect's reader ignores the envelope events it has nothing to say about」，`d3b4cc2` 的提交信息也逐字这么承诺。

**事实**：`read_anthropic_terminal` 确实按事件名做了守卫（`message_stop` 置 `seen`、`message_delta` 读 stop reason、其余直接 `return`）；`read_responses_terminal` **没有**任何守卫，第一行就是 `terminal.seen = True`，随后落到 `terminal.stop_reason = TOOL_USE if saw_tool_call else "end_turn"`。翻译腿的调用点在 `ResponsesAssembler.push` 里被 `kind in {"response.completed","response.incomplete"}` 挡住，所以翻译腿不受影响；透传腿把它接到了 `CONTROL_EVENTS` 的全集（含 `response.created`／`queued`／`in_progress`／`failed`／`cancelled`／`error`）上。

实测（`probe1.py`）：

```
initial seen: False stop: ''
after response.created -> released: ()
  terminal.seen: True stop_reason: 'end_turn'
```

**影响**（`probe2.py`／`probe4.py`，把真实的 `stream_delivery` 跑起来，逐条对照翻译腿）：

| 场景 | 透传腿（现状） | 翻译腿（同输入） |
|---|---|---|
| `created`+`added(0)`+`delta` 后传输撕流，尚无任何提交 | 客户端 0 字节、**无 error 帧**、异常被吞（`raised=None`）、**replay 一次都没问**（`replay_asked=0`） | `event: error` + 异常上抛，`replay_asked=1` |
| 已提交一个完整 group 后撕流 | 只有前面那些事件，**无 error 帧**，异常被吞 | 同样的事件 + `event: error` + 异常上抛 |
| 已提交一个完整 group 后 clean EOF（无终局） | 只有前面那些事件，**无 error 帧** | 同样的事件 + `event: error` |
| 已提交一个完整 group、在 item 边界 clean EOF | 只有前面那些事件，什么都不补 | 补 `response.incomplete` |

机制是 `stream.py:434` 的 `if assembler.terminal.seen: break`——它的语义是「上游把这一轮说完了，之后连接才断」，于是撕流被当成正常收尾：不 replay、不发 error、不上抛，`on_tear_after_terminal` 记一笔就走。随后 `stream.py:533` 的 `if not terminal.seen:` 永假，`framer.synthesises_terminal` 那一支**在这条腿上不可达**。

**正控**（`probe5.py`，在进程内 `dataclasses.replace` 出一份把 `read_terminal` 守卫到 `response.completed`／`incomplete` 的 `Dialect`，worktree 一个字节都没改）：

```
--- tear before any commit ---
  as shipped                 events=[] raised=None replay_asked=0
  with guarded read_terminal events=['error'] raised=Tear replay_asked=1
--- tear after one commit ---
  as shipped                 events=[... 4 个事件] raised=None replay_asked=0
  with guarded read_terminal events=[... 4 个事件, 'error'] raised=Tear replay_asked=0
--- clean EOF at boundary ---
  as shipped                 events=[... 4 个事件] raised=None replay_asked=0
  with guarded read_terminal events=[... 4 个事件, 'error'] raised=None replay_asked=0
```

三条路径全部恢复正确，且 replay 只在合法的那一格发生。**因果被隔离到这一处**，不是多因叠加。

顺带两项：完成行的 `trace.terminal_seen` 在透传腿上恒为真（`request_trace.py:191` 从同一个 `Terminal` 取），这正是 §10 禁止的「把未知伪装成已观测」；`stop_reason` 在 `response.created` 之后就是 `end_turn`，虽然正常流最后会被 `response.completed` 覆盖回正确值，但撕流时留在完成行上的就是这个凭空的 `end_turn`。

**建议**：给 `openai_responses_passthrough._read_terminal` 加上与 Anthropic 侧同形的事件名守卫（只对 `response.completed`／`response.incomplete` 转调），或把守卫下沉进 `read_responses_terminal` 自身（后者更好——它是共享函数，守卫在里面就不会被第三个调用者再踩一次）。修完必须配一条会红的测试：`assembler.push(response.created)` 之后断言 `terminal.seen is False`。现有 `test_the_terminal_facts_are_recorded_without_touching_the_wire` 在第 404 行断言了 `seen is False`，但那是在 push 任何事件**之前**，而且该用例全程不发 `response.created`，所以它对这个缺陷天然没有分辨力。

**证据强度**：强，足以据此行动。机制与触发均已实跑证实，且有隔离到单一原因的正控。

---

## major

### F-02　上游失败事件被发给客户端两次

- **严重级别**：major
- **primary_location**：`src/app/pipeline/delivery/formats/openai_responses_passthrough.py:21-43`（`response.failed`／`cancelled`／`error` 同时列在 `CONTROL_EVENTS` 与 `TERMINAL_EVENTS`）
- **related_locations**：`src/app/pipeline/delivery/passthrough.py:170-177`（同一次 `push` 里既记 failure 又释放含该事件的前缀）；`src/app/pipeline/delivery/stream.py:385-403`（先 yield 批次、再 yield `_report_failure`）；`src/app/pipeline/delivery/stream.py:295-297`（`_report_failure` 在 passthrough 且 origin 为 `UPSTREAM_EVENT` 时逐字重发）

**判据**：Spec §8「上游终局失败事件（`response.failed` / `response.cancelled` / `error`）：若最终可见则**逐字**重放」——重放一次；§7.2 收口第 4 步「提交上游 terminal／failure（若有）」也是一次；§3 的保真承诺是「逐字重放」而不是「重放两遍」。

**事实**：这三个事件既是 envelope（于是随安全前缀作为普通事件出门），又是 `_FAILURE_EVENTS`（于是 `_report_failure` 再写一遍原始帧）。两条机制互不知情。

实测（`probe6.py`，`created → added(0) → done(0) → response.failed`，`passthrough=True`）：

```
events to client: ['response.created', 'response.output_item.added', 'response.output_item.done', 'response.failed', 'response.failed']
```

两帧的 `data` 逐字节相同。`error` 与 `response.cancelled` 结构同形，同样重复。

**影响**：客户端收到两次终局失败。对 OpenAI SDK 的 `ResponseStreamManager` 一类累积式解析器，第二帧落在一个已经结束的流上；对自写客户端，最轻也是失败被记两次。这条路径今天在 `main` 上不存在（翻译腿只从 `_report_failure` 出一帧），所以是本次接线引入的新行为。

**建议**：两个方向都可行，选一个并写进 Spec：(a) 在 `_take_safe_prefix` 释放前把 failure 事件从批次里排除，由 `_report_failure` 独家承载；(b) 在透传腿上不走 `_report_failure`（`stream.py:401` 加一个「该失败是否已随批次出门」的判据）。倾向 (a)，因为 §7.2 第 4 步把 terminal／failure 明确写成收口的最后一步、与前三步的 group 提交分开，(a) 与那个结构一致。注意 `TERMINAL_EVENTS` 里保留这些名字仍然必要——它们要负责解除 control-only 前缀的持有（§5 第四行）。

**证据强度**：强。机制与触发均实跑证实，输入是协议内的普通失败流。

### F-03　§7.2 的收口顺序完全没有实现：一个不闭合的 item 会让整条响应归零

- **严重级别**：major
- **primary_location**：`src/app/pipeline/delivery/passthrough.py:258-276`（`unfinished_items`／`unattributed` 两个属性**没有任何生产调用者**）
- **related_locations**：`src/app/pipeline/delivery/stream.py:508-583`（收尾段只 `session.finish()` 冲 buffer，从不询问 assembler 队列）；`plan.md:54`、`plan.md:87`（第 6 步标「已完成」，而 plan §4 把「实现 Spec §7.2 的收口顺序」归在该步）

**判据**：Spec §7.2「最终 ending 到达时，一律按同一顺序收口：1 丢弃未闭合 item 的 suffix（§3）；2 按**原序**提交 control 与所有已完成的安全 group；3 无法归属的事件……；4 提交上游 terminal／failure（若有），否则提交 proxy error（§8）」。

**事实**：`PassthroughAssembler._queue` 里被 head-of-line 挡住的事件，任何 ending 都不会被冲出来。`session.finish()` 冲的是 `BlockBuffer`，而卡在 assembler 队列里的事件根本没进过 buffer。`rg -n "unfinished_items|unattributed" src` 的结果只有定义处与 docstring，没有读者。

实测（`probe2.py` 场景 D，`created → added(0) → delta(0) → response.completed`，item 0 永不闭合）：

```
--- D: item never closes, then response.completed ---
  events to client: []
```

客户端拿到 200、零字节、无 error 帧。连上游自己发出来的 `response.completed` 都没出去。翻译腿在同一输入下至少会发出终局帧。

**影响**：整条响应静默消失。触发条件是「上游打开了一个 item 却没有闭合它」，这正是 Spec §3 整节论证所基于的形态（§3 逐字写着「一个 item 收到了 `added` 与若干 delta 却始终没有 `done`」）；Spec §3.1 第三条描述的 payload 截断也会造出同形状态（`done` 变成无法归属 → 该 item 永远开着）。**机制确定；触发在本仓无实测样本**——五份 cassette 里没有未闭合 item。权重：足以在合并前修，不足以断言「生产上正在发生」。

与 F-01 叠加时更糟：F-01 让 `terminal.seen` 为真，于是 `stream.py:533` 的补救分支也不会跑，最终落到 `stream.py:530` 的 `return`，一个字节都不写。

**建议**：在 `_deliver` 的收尾处（`session.finish()` 之前）向 assembler 要一次收口批次，由 assembler 按 §7.2 的四步给出——它已经把两类事件分开报了，缺的只是消费者。这一项如果本轮不做，**必须进 `deferred.md` 并在 `plan.md` 第 6 步的「已完成」上打折**，因为现在的文档状态读起来是它已经做了。

**证据强度**：强（机制）／中（触发）。缺失是逐条 grep 确认的，后果是实跑的；触发依赖上游行为，未观测。

### F-04　§8 的 cap 管不到透传腿真正持有的那部分字节

- **严重级别**：major
- **primary_location**：`src/app/pipeline/delivery/passthrough.py:253-256`（`PassthroughAssembler.held_bytes` 无生产调用者）
- **related_locations**：`src/app/pipeline/delivery/blocks.py:117-153`（`BlockBuffer._enforce_cap` 只计已释放的批次）；`src/app/config/schema.py:242`（`buffer_cap_bytes` 默认 16MiB，**默认生效**）

**判据**：Spec §8「**限制的是本代理当前持有的字节**……本腿计入：尚未 `done` 的原始事件队列、已完成但被 policy 扣住的事件组、control events、以及同时保留的预渲染副本」。

**事实**：`_enforce_cap` 只在 `BlockBuffer.add` 里跑，而 `add` 只在批次被 `_take_safe_prefix` 释放之后才被调用。被 head-of-line 挡住的事件（含**已完成但排在未闭合 item 之后的 group**）全部停留在 `PassthroughAssembler._queue`，从不计入。`held_bytes` 这个属性存在，注释也明说它是为 §8 准备的，但没人调用它。

**影响**：`block` policy 下，一个早早打开且不闭合的 item 会让整条响应无上界地堆在内存里，`BufferCapExceeded` 永不触发。这与翻译腿的既有形态不同：翻译腿上一个 item 在 `done` 时就变成 `CompletedBlock` 进 buffer，因而落在 cap 之内；透传腿把「已完成但被前面的 item 挡住」这一整类也移出了 cap 的视野，而那正是 §8 点名要计入的第一项。

**建议**：在 `_deliver` 每次 `assembler.push` 之后（或在 buffer 的 cap 检查里）把 `assembler.held_bytes` 一并计入，超限时抛 `BufferCapExceeded`。这一项若推迟，同样要进 `deferred.md`。

**证据强度**：强。缺失由 grep 逐条确认，默认值由配置 schema 与用户亲笔 `config.example.yaml` 双向确认。

### F-05　Spec 与实现脱节：文首、§2.6 仍写「未接线」，§12 没有本次修订的记录

- **严重级别**：major
- **primary_location**：`.dev/docs/direct-passthrough/spec.md:4`（「状态：**DRAFT v10 — 待复评**……Responses 方言的透传骨架亦已合入（`01c33f1`，**未接线**）。**主体（接线）未开始**。」）
- **related_locations**：`spec.md:90`（§2.6 Responses 行的依据栏仍是「引擎已建（`01c33f1`），未接线」）；`spec.md:483-495`（§12 修订记录最新一行是 v10，没有为 §2.8 的新增写任何一行）；`spec.md:97-107`（§2.8 由 `68a95b3` 新增）

**判据**：项目规则 `.claude/rules/00-development-workflow.md`：「**The Spec is a living document and is never frozen** — 当新的裁决、测量或发现与它冲突或限定它时，**当场**修订；……**Every amendment is logged in the Spec's own revision record** — what changed, why, and what triggered it」，并且「never treat a Spec's age, its status line, or a pending question elsewhere as grounds for leaving a known-wrong sentence standing」。Spec 自己第 9 行也写着「新裁决、实测或发现与本文冲突时当场修订，每次修订记入 §12」。

**事实**：`.dev` HEAD `68a95b3` 的标题是「the Responses leg is wired and issues #2 and #3 are closed」，它给 spec.md 新增了 §2.8、改了 §2.6 的 Anthropic 行——但**没有**改文首状态行、**没有**改 §2.6 的 Responses 行、**没有**在 §12 补一行。`plan.md` 的状态行反倒是对的（「Responses 直连腿已接线」）。于是同一个主题里，plan 说已接线、spec 说主体未开始。

派发描述称 spec 为「DRAFT v12」，磁盘上是 v10——这条不作为发现，只作为「转述与权威不一致」的提示：**以文件当前内容为准**。

**影响**：Spec 是本主题的权威，它现在对「这条腿处于什么状态」给出的是一个已知为假的答案，且 §12 缺了那一次修订使得「写这段代码时我们承诺了什么」不再可审——而 §12 的可审性正是项目规则用来替代冻结的那个机制。

**建议**：合并前把文首状态、§2.6 的 Responses 行改成实际状态，并在 §12 补一行记 §2.8 的新增（触发：放宽定义域时发现 §8 的限定写宽了）。§2.8 与 §2.7 的编号顺序另见 N-01。

**证据强度**：强。文本事实，`git show 68a95b3 -- docs/direct-passthrough/spec.md` 可复核。

---

## minor

### F-06　透传腿的 `Terminal.dialect` 停在默认的 `ANTHROPIC`，完成行按错误方言判读

- **严重级别**：minor
- **primary_location**：`src/app/pipeline/delivery/passthrough.py:147`（`self._terminal = Terminal()`，未传 `dialect`）
- **related_locations**：`src/app/pipeline/delivery/formats/openai_responses.py:461`（翻译腿写的是 `Terminal(dialect=ReplyDialect.RESPONSES)`）；`src/app/observability/request_trace.py:194`（`self.dialect = reply.dialect`）；`src/app/observability/request_log.py:42-45`、`:366`、`:383`、`:399`
- **另一半**：`src/app/pipeline/delivery/passthrough.py:40-41`（`Dialect.name` 的注释自称「What the completion line and the observability record call this leg」，而 `rg` 全仓无读者）

**判据**：Spec §10「本腿**至少**要记录：原生 output item 计数、需要客户端行动的 tool 名称／类型、reasoning 是否出现、权威 terminal status 与 usage、failure／截断／replay 的来源」。方言不在那份最低清单里，但它决定了这些数字**怎么被判读**。

**事实**：`RECEIVED_BYTES_THRESHOLDS` 两条方言的阈值差一个数量级（Anthropic `10KiB/100KiB`，Responses `384KiB/4MiB`），`format_stop_reason`／`format_thinking` 也按方言取词。透传腿的 `Terminal` 用默认值，于是一条 Responses 直连回复会被按 Anthropic 的尺子染色——120KiB 就被判为 heavy，而同样字节数走翻译腿只是普通。`request_log.py:365` 的注释还特意写了「subscripted rather than looked up with a default, exactly as `REASONING_WORD` and `TOOL_WORD` are, so a dialect added later fails here instead of silently being judged by another path's sense of large」——这里发生的正是那句话要防的事，只是不通过新增方言，而是通过一个没传的构造参数。

**影响**：只影响完成行与 TUI 的判读，不影响 wire。

**建议**：`PassthroughAssembler.__init__` 里按 `Dialect` 给出对应的 `ReplyDialect`（`Dialect` 上已经有 `name` 字段，可以顺手让它变成有读者的字段，或直接加一个 `reply_dialect` 字段）。

**证据强度**：强。字段与读者链路逐处核过。

### F-07　`Attempt` 别名注释声称的不变量，在它指名的构造点上并不成立

- **严重级别**：minor
- **primary_location**：`src/app/pipeline/delivery/stream.py:73`（「That is guaranteed at construction — `inference.py` builds the replacement from the same `assembler_for`/`delivery_buffer` pair as the first attempt」）
- **related_locations**：`src/app/server/routes/inference.py:420`、`:435`（`again = await handle(...)` 之后 `assembler_for(again, ...)`）；`src/app/pipeline/driver.py:133`／`:88-99`（`shape_request` → `decide_route`，每次都对着**当前**的 `chain.providers` 重算）；`src/app/pipeline/delivery/stream.py:473`（`chunks, upstream, assembler, buffer = replacement`）

**判据**：注释自身的断言，以及类型层面被 `Any` 放弃后所依赖的那个不变量：「a replacement must carry the same unit as the attempt it replaces」。

**事实**（按派发要求去核了构造点，没有信注释）：`_reopen` 用的是**同一个函数** `assembler_for`，但喂给它的是一个**重新路由过的** `HandledRequest`。`decide_route` 不读任何被钉住的路由，它每次都从 `chain.providers` 与 `chain.config.model_mappings` 重算，而 `routing.py:282` 的注释自己说明 catalogue 是被 `refresh_catalog` 整体替换的。如果两次尝试之间该模型的 descriptor 不再支持 `/responses`，`target_format` 会落到回退端点，`translation_required` 随之翻转，`assembler_for` 就会返回另一种单位类型的 assembler。而 `framer` 是在循环之前构造一次、**不随 replacement 更新**的。

**影响**：这一形态在 `main` 上也存在，但后果不同：过去两侧都产 `CompletedBlock`，错配只会「安静地错」；现在 `PassthroughFramer.block(CompletedBlock)` 会走到 `block.encode()`、`ResponsesFramer.block(RawEventBatch)` 会走到 `block.kind`，都是 200 已发出之后的 `AttributeError` 撕流。**机制确定，触发未测**——需要一次尝试之间的 catalogue 变更，本轮没有构造。

**建议**：不必现在改行为，但那句注释要改成它实际成立的样子（「保证来自路由在两次尝试之间不变，而这一点没有任何东西断言」），或者在 `_reopen` 里断言 `carries_upstream_natively(again) == carries_upstream_natively(handled)`，不等则返回 `None`（拒绝重开好过撕流）。后者一行，且把一个隐式不变量变成显式的。

**证据强度**：中。链路是读代码确认的，触发条件未实测。

### F-08　`blocks.py` 的文档指针仍指向已改名的目录

- **严重级别**：minor
- **primary_location**：`src/app/pipeline/delivery/blocks.py:48`（`direct-responses-passthrough/spec.md` §10）

**判据**：`.claude/rules/00-development-workflow.md`「repoint living documents when files move」；`spec.md:7` 明说已重指的是「活文档与源码注释」，报告原文才保持原样。

**事实**：`d7b1534` 重指了三处（`openai_responses_passthrough.py`、`test_pipeline_app.py`、`test_responses_passthrough.py`），但 `blocks.py:48` 那处是 `82cfa29` 写的、排在 `d7b1534` **之前**，因而被漏掉。`rg -n "direct-responses-passthrough" src tests docs` 今天只剩这一处命中。

**建议**：改成 `direct-passthrough/spec.md`。

**证据强度**：强。单条 grep，全仓唯一命中。

### F-09　一条集成测试的守卫目标已经随接线消失，docstring 却仍在描述它

- **严重级别**：minor
- **primary_location**：`tests/int/test_pipeline_app.py:2673-2690`（`test_a_direct_responses_client_survives_an_upstream_that_really_searched` 的 docstring）

**判据**：本仓已付过代价的形态——「守卫被留在了 legacy 链路上」。测试仍然绿，但它自称守的东西已经不可能触发。

**事实**：该 docstring 逐字写着「`ResponsesAssembler` serves both legs — a Responses client directly, and a Responses upstream being translated to Anthropic」，并说它「is here to go red the moment that changes without a per-leg switch」。接线之后直连腿根本不经过 `ResponsesAssembler`，所以「`web_search_call` 被组装成 `server_tool_use` 交给 `ResponsesFramer`」这件事在这条腿上永远不会发生——这条守卫的击发条件被移除了。它还在测的是「真实 cassette 能原样透传并以 `response.completed` 收尾」，那是有价值的，但和 docstring 说的是两回事。

**建议**：改写 docstring 说明它现在守的是什么（cassette 驱动的透传端到端），并把 §5.3 那条块对守卫另找一个仍然可达的位置（翻译腿）。

**证据强度**：强。逐字比对 docstring 与 `assembler_for` 的当前分支。

---

## nit

### N-01　`spec.md` 里 §2.8 排在 §2.7 前面

- **primary_location**：`.dev/docs/direct-passthrough/spec.md:97`（§2.8）与 `:109`（§2.7）
- `68a95b3` 把新增的 §2.8 插在了 §2.7 之上。内容上 §2.8 引用 §2.7 的裁定，倒序阅读要跳一次。建议调换位置，或把 §2.8 改成 §2.7.1。

### N-02　`test_cut_mid_block_is_true_only_while_an_item_is_open` 的 docstring 现在是错的

- **primary_location**：`tests/unit/pipeline/delivery/test_responses_passthrough.py:459`（「Both leave `terminal.seen` false, so this is the only observable that separates them.」）
- 因为 F-01，透传腿上这两种收尾**都**留下 `terminal.seen` 为真。结论（`cut_mid_block` 是唯一区分器）碰巧仍成立，前提是假的。F-01 修好之后这句话会自动变回真，所以只作 nit 记录，提醒修 F-01 时顺手复核。

---

## 主观建议（不占 severity 档位）

- **S-01　把「终局读取器只应答自己认识的事件」这条规则钉在引擎侧而不是各方言侧。** `Dialect.read_terminal` 的契约今天是隐式的（「reader 会忽略它无话可说的事件」写在 `passthrough.py:171` 的注释里），Anthropic 那份遵守了，Responses 那份没有，而 F-01 就是这个隐式契约被违反的直接后果。预期影响：把守卫写进引擎（例如只对 `terminal_events ∪ {方言自报的 fact 事件}` 转调，或让 `read_terminal` 返回一个「我处理了吗」的答案），下一份方言词汇就不可能再踩同一处。
- **S-02　给三种 policy 在透传腿上各补一条端到端判据。** 目前 `until-tool-use` 与 `full` 在这条腿上只有「谓词单测」与「批次属性单测」，没有一条走过 `BlockBuffer`。这不是「某分支没测到」那类空诉求——F-01／F-03 都发生在「单元件各自对、合起来不对」的缝里，而这条腿的 policy 缝还没有任何东西照过。预期影响：一条 `full` 的端到端用例会顺带钉住 F-03 修复后的收口顺序。

---

## 变异验证结果

纪律：变异前 `git status --short` 确认树干净；**每次都跑完整套件**（不用 `-k`，避免派发里点名的那个陷阱）；每次跑完 `git checkout -- <file>` 还原并再次 `git status --short` 确认干净；全程不放后台。基线：1993 passed／2 skipped／117s。离开时该 worktree 已确认 clean（`ruff`／`pyright` 也在 clean 树上各跑过一次，分别 `All checks passed!` 与 `0 errors`）。

| # | 变异 | 位置 | 结果 | 归因 |
|---|---|---|---|---|
| M1 | `carries_upstream_natively` 恒 `False`（整条接线关掉） | `delivery_policy.py:68-72` | **红 1**：`tests/int/test_pipeline_app.py::test_an_output_item_this_proxy_does_not_know_reaches_the_client_intact` | 打红了，但**分辨力只有一条**。`test_a_direct_responses_stream_is_answered_in_responses_events` 等三条直连腿测试在关掉透传后照样绿，因为翻译腿也产 `response.created`／`response.completed`。**测试不足**（够证明接线生效，不够证明接线之后的收尾行为） |
| M2 | 删掉「control-only 前缀不单独交付」那一段判断 | `passthrough.py:246-249` | **红 6**：`test_a_terminal_lifts_the_hold_on_a_response_with_no_items`、`test_control_events_keep_their_place_in_the_queue`、`test_queued_is_envelope_and_travels_with_its_prefix`、`test_an_items_events_do_not_straddle_a_release_boundary`（Responses）＋ `test_events_are_grouped_by_index_not_by_the_responses_field`、`test_message_delta_carries_the_stop_reason_without_ending_the_response`（Anthropic） | 充分。两个方言各有独立见证 |
| M3 | 取消 barrier（整个队列一律释放），即「跳过而不是停在」的极端形态 | `passthrough.py:225-229` | **红 12**：含 `test_nothing_is_released_before_its_item_closes`、`test_a_finished_item_waits_behind_an_unfinished_earlier_one`、`test_an_unattributable_event_blocks_the_prefix_behind_it`、`test_held_bytes_measures_the_text_actually_held` 等 | 充分 |
| M4 | 删掉 straddle 回退循环 | `passthrough.py:230-242` | **红 2**：`test_an_items_events_do_not_straddle_a_release_boundary`、`test_retreating_past_one_straddling_item_can_expose_another` | 充分，且第二条专门覆盖「回退要迭代」这一层 |
| M5 | `Dialect.item_index_field` 由 `output_index` 改成 `index` | `openai_responses_passthrough.py:116` | **红 18**：4 条集成 + 14 条单元 | 充分。集成侧以 `IndexError: list index out of range` 现形（客户端零事件），说明这条判据被端到端钉住 |
| M6 | `PassthroughFramer.synthesises_terminal` 改 `True` | `passthrough.py:298` | **红 1**：`test_the_framer_refuses_to_synthesise_a_terminal`，而该用例的全部内容就是 `assert framer.synthesises_terminal is False` | **测试不足，且不是普通的不足**：唯一红的那条是同义反复，它断言的是属性本身而不是任何行为。没有任何交付层测试变红，因为读它的那个分支（`stream.py:533-538`）**在这条腿上不可达**——这正是 F-01 的独立佐证。若只看「变异打红了」就收工，会把一个不可达的能力位记成「有覆盖」 |
| M7 | Responses `requires_client_action` 未知类型改答 `False` | `openai_responses_passthrough.py:93` | **红 1**：`test_an_item_type_nothing_here_knows_is_assumed_to_need_the_client` | 谓词本身**有**覆盖。谓词 → `RawEventBatch.requires_client_action` → `BlockBuffer` 的 `until-tool-use` 这条链没有端到端见证，但那一段是**构造性保证**（`BlockBuffer` 已泛型化并对 `DeliveryUnit` 协议编程，其三种 policy 由 `test_block_delivery.py` 以 `CompletedBlock` 覆盖），所以不单列为缺陷，只作 S-02 |

**两条要单独说清的**：

- M1 与 M6 是本轮唯二「红了但红得不够」的。M1 的红只证明接线接上了，不证明接线之后的行为对；M6 的红完全不证明任何行为。F-01、F-02、F-03 三条发现没有任何一条能被现有测试的任何变异照出来——它们是靠自写探针（`probe2`／`probe4`／`probe6`）跑真实 `stream_delivery` 才现形的。
- **没有出现「打不红是因为构造性保证」的情形被误判为缺陷**：唯一归到构造性保证的是 M7 的下游那一段，理由是 `BlockBuffer` 的泛型化把「policy 怎么放行」这件事从单位类型上剥离了，而它自己那一份测试仍在跑。

## 考虑过但否决的候选发现

1. **`_hand_over` 在透传腿上会撕流。** `stream.py:617` 构造 `CompletedBlock` 再交给 `framer.block(handed)`，而 `PassthroughFramer.block` 会调 `block.encode()`——`CompletedBlock` 没有这个方法。**否决**：构造性不可达。`ContinuationSupport.synthesize` 是 `inference.py:311` 的 `_hand_back` → `hand_over.py:222` 的 `hand_back_block`，其第一行就是 `if wire_format is not WireFormat.ANTHROPIC_MESSAGES: return None`，而传进去的 `route.wire_format` 是**入站**格式（`inference.py:156` 用同一个字段填 `trace.inbound_format` 可证）。Responses 入站永远拿到 `None`，`_hand_over` 在碰 framer 之前就返回了。记为潜在风险而非缺陷；若将来 Anthropic 直连腿接线（D-5），这一处会立刻变成真缺陷，值得在那时先看。
2. **`carries_upstream_natively` 读 `inbound_format` 而不是 `target_format`，是不是有洞。** **否决**：`routing.py:335` 把 `translation_required` 定义成 `target_format is not inbound_format`，所以在 `not translation_required` 的前提下两者恒等，判据等价。同理，`synthesized` 那一支即使删掉也不会误判——`driver.py:138`／`:191` 两个合成点都以 `inbound_format is ANTHROPIC_MESSAGES` 为前提，Responses 入站根本产不出合成回复；留着它与 `delivers_blocks` 的写法一致，是好的。
3. **非流式直连 Responses 被这轮改坏了。** **否决**：`assembler_for`／`framer_for` 只在 `inference.py:322` 的 `if context.stream:` 之内被调用；缓冲路径走 `reply.py:31` 的 `if not route.translation_required: return body`，本轮六笔提交没有触及那一行。
4. **四个读取函数的提取改变了翻译腿的既有行为。** **否决**，逐行核 `d76ac1c` 与 `d3b4cc2` 的 diff：`responses_failure_from`、`read_responses_terminal`、`anthropic_failure_from`、`read_anthropic_terminal` 的函数体与被抽出来之前逐字相同，唯一变化是「先构造 `StreamFailure` 后 log」变成「先 log 后构造」，以及新函数各自重算了一次 `kind`——重算用的表达式与调用点原本那一行完全一致（`event.event or str(data.get("type", ""))`），且调用点仍有各自的 `kind` 守卫，所以新加的 `if kind not in ...: return None` 在翻译腿上恒不命中。**注意**：`read_anthropic_terminal` **有**事件名守卫，`read_responses_terminal` **没有**——这个不对称本身不是提取引入的（旧代码的守卫在调用点），但它是 F-01 的必要条件。
5. **两个 mock 补 `response.created`／`in_progress` 之后，别的测试变成绿在错误的原因上。** **否决**。判据自己核过：`tests/int/cassettes/` 共 5 份，带 Responses 事件流的是 3 份（`anthropic_to_responses_stream`、`history_responses_stream`、`responses_web_search_stream`），三份的前两个事件**一致**是 `response.created` 然后 `response.in_progress`，与提交信息的陈述相符。副作用面：`ResponsesAssembler.push` 对这两个事件名没有任何分支，直接落到函数末尾的 `return ()`，所以翻译腿的行为一字未变；受影响的只有直连腿携带的事件数，而那正是本次要改的东西。`test_a_direct_responses_stream_is_answered_in_responses_events` 的 `names[0] == "response.created"` 从「断言本代理的发明」变成「断言上游的事实」，是变好而不是变松。
6. **`RawEventBatch.size_bytes` 与实际成帧字节差 1.04x，cap 会算少。** **否决**：`passthrough.py:58-66` 已经把这个偏差实测量化（125 个真实事件上 51710 对 53710）并写明它省掉的是 `encode_frame` 加的字段名与分隔符。这是已声明的近似而非缺陷。真正的 cap 缺口是 F-04，与这条无关。
7. **`_item_of` 会把 `output_index: true` 当成 item 1**（Python 里 `bool` 是 `int` 的子类）。**否决**：无判据支持上游会发布尔 index，属臆测；且后果是分组错误而非静默丢失。不列为发现。
8. **`error` 同时进 `CONTROL_EVENTS` 与 `TERMINAL_EVENTS` 本身是错的。** **否决**：`TERMINAL_EVENTS` 的成员资格是 §5 第四行明确要求的（否则「envelope + 终局」这种最短合法响应会被永久扣住），删不得。F-02 的成因是 `TERMINAL_EVENTS` 与 `_FAILURE_EVENTS` 的**重叠**加上两条独立的出门通道，不是成员资格本身；建议已按这个成因写。

## 对派发七问的逐条回答

1. **接线的正确性**：判据本身**没有洞**。`translation_required is False ⟺ target == inbound`（`routing.py:335`），所以「不翻译 + 入站是 Responses」严格蕴含「上游也是 Responses」；`synthesized` 与 Chat Completions／Embeddings 的排除都成立（详见否决项 2、3）。**没有发现被错判进或判出的路由。** 问题不在选谁，在选中之后的收尾（F-01～F-04）。
2. **`_deliver` 泛型化是否引入行为变化**：循环本身没有分支变化，replay 分支（`stream.py:473`）与各 ending 分支对 `RawEventBatch` 都成立。hand-over 分支**构造性不可达**（否决项 1，已去核 `hand_back_block` 而非信注释）。`Attempt` 别名注释声称的不变量在它指名的构造点上**不成立**——`_reopen` 是拿重新路由过的 `HandledRequest` 再算一次 assembler，见 F-07。真正的行为变化不来自泛型化，而来自 `terminal.seen` 被提前置真（F-01）之后，同一套 ending 分支走到了完全不同的格子里。
3. **`synthesises_terminal`**：它落到的那个分支**根本不会被求值**。`stream.py:533` 的 `if not terminal.seen:` 在透传腿上恒假（F-01），所以 `not cut_mid_block and settings.unterminated_stop_reason and framer.synthesises_terminal` 这个组合一次都不会被算。它的取值 `False` 按 Spec §5.1／§8 是对的（「不得合成成功 terminal，须写 error」），设计意图正确，**但今天是死码**；M6 变异只打红一条同义反复的属性断言，是这个结论的独立佐证。F-01 修好之后它会立刻变成活的，并且是那条腿唯一正确的答案。
4. **共用的 terminal／failure 读取函数**：**没有改变翻译腿的既有行为**，已逐行核 diff（否决项 4）。但提取把一个原本靠调用点守卫的函数暴露给了第二个调用者，而第二个调用者没有加守卫——这是 F-01 的结构性来源，也是 S-01 的由来。
5. **测试的鉴别力**：见上一节。7 个变异里 5 个打红充分（M2／M3／M4／M5 与 M7 的谓词那一半），2 个红得不够（M1 只有一条见证、M6 的唯一见证是同义反复）。三条最重的发现现有测试**一条都照不出来**。
6. **两个 mock 补事件**：**正确**，与三份 cassette 逐字相符（我自己核的，见否决项 5），且没有让别的测试绿在错误原因上。
7. **有没有把翻译腿弄坏**：**没有**。`ca777df` 的未知 item 拒绝仍在 `ResponsesAssembler._close` 的 `UNKNOWN` 分支上，翻译腿仍然走得到它（`carries_upstream_natively` 为假 → `ResponsesAssembler`）。两条点名的测试基线全绿，且都不经过被改动的路径：`test_a_block_kind_this_does_not_know_is_refused_rather_than_emptied` 直接构造 `ResponsesFramer`，`test_rejects_unknown_output_item_explicitly` 在非流式翻译腿上。两者测的仍是它们原本测的东西。

---

## 复核用的探针

`/tmp/ghc-review-wiring/probe1.py`（`terminal.seen` 被 `response.created` 置真）、`probe2.py`（五种收尾在透传腿上的产出）、`probe3.py`／`probe4.py`（与翻译腿逐场景对照）、`probe5.py`（守卫 `read_terminal` 的正控，进程内构造，不改 worktree）、`probe6.py`（`response.failed` 双发）。全部以 `cd <worktree> && PYTHONPATH=src uv run python /tmp/ghc-review-wiring/probeN.py` 运行。

## 搬运到 `.dev`

主树写入被守卫拒绝，请调用方执行：

```bash
cp /tmp/ghc-review-wiring/260831-review-wiring.md \
   /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260831-review-wiring.md
```
