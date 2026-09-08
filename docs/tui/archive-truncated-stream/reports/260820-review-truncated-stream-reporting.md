# 定向评审：上游流截断（truncation）上报

- 评审对象：工作树未提交改动中与「上游流截断上报」相关的部分
- 评审时间：2026-08-20 09:15～09:40 UTC
- 评审者：独立评审 subagent（只读；未修改仓库任何文件）
- 结论：**needs-fix**（0 blocker，5 should，6 nit）

## 0. 快照与漂移声明

**工作树在本次评审期间被并行会话改动了至少三次**，其中一次正是针对我准备提出的第 3 点（客户端断开误报）。以下结论对齐的是这一组内容身份：

| 文件 | sha256（评审对齐版本） |
|---|---|
| `src/app/pipeline/delivery/assembler.py` | `2bd6fa68cb54c8c5b5f5b12acd4aebcfdb3e520ddb476dc5c9714189517b1f49` |
| `src/app/pipeline/delivery/stream.py` | `ab94ab9a05f2a4141d13f6a3bb57820a1dc6bc5bc3adbbe8f2568ea8e2bb4d07` |
| `src/app/server/pipeline_app.py` | `6501bf9a392e6c9485046471ec82a6dd8873271fc65a7d2ed621567d8f5c6408` |
| `src/app/observability/request_log.py` | `90581f8aaa45be116c80b882ded50f89c42446f1fb366cc9c20d65794bce86dc` |
| `tests/http/test_pipeline_app.py` | `2dce7036540d5cff5e2aebf962d28219b0fb85fba418180f4d57b4161ac20ce7` |
| `tests/unit/test_stream_delivery.py` | `7d2b85cfe9ed13cf19a4b7e5599bf01dd2a70a5daa6de10e369f4381e451adab` |
| `tests/unit/test_request_log.py` | `44ca4310ffe3271ea129ed6f5edb4c8e39b475f6b0fa16a219eacdae441d5d23` |
| `tests/unit/test_sse_assembly.py` | `a0493afef7e2cc262ab2f75bbe6a0e51a91d9106292e42279fafd9a390c0bb02` |

已包含并已核对主会话中途通报的 `drained` 补丁（`_StreamAccounting.drained`、`_tracked_delivery` 的 `drained = True`、`finish()` 的两套措辞、`test_a_client_that_walked_away_is_not_blamed_on_upstream`）。

`src/app/pipeline/delivery/stream.py` 与 `src/app/pipeline/delivery/sse_source.py` 里的 `aclosing` / `finish_stream_cleanup` 改动属于并行会话的在途工作，**不在本次范围**；只有它与截断上报存在交互时才被检查（见 §4「已核查未成问题」第 5 条）。

基线验证：`uv run pytest tests/http/test_pipeline_app.py tests/unit/test_stream_delivery.py tests/unit/test_request_log.py tests/unit/test_sse_assembly.py` → 140 passed；`ruff check` 与 `pyright` 对这 8 个文件均为 0 问题。

## 1. 发现清单

判据强度分三档：**实测**（我跑出了证据）、**代码推演**（读代码可确定，未跑）、**判断**（设计取舍，可争议）。

### S1（should，实测）上游异常撕断被措辞成交付侧停止，且异常本身不上线

`drained` 区分的是「`async for` 正常跑完」与「其他一切」，不是「上游」与「客户端」。第三条走到 `finish()` 且 `seen` 为假的路径是：**`stream_delivery` 抛异常**——上游 RST（`httpx.ReadError`）、`RemoteProtocolError`、或交付层自身的 bug。此时 `drained` 为假，行上写的是 `delivery stopped before upstream finished`，把上游故障说成我们这侧停止了；而真正的原因（`connection reset by peer`）**完全不出现在行上**。

实测（`/tmp/probe6_upstream_reset.py`，直接驱动 `_tracked_delivery`，上游发完第一个块后抛 `httpx.ReadError`）：

```
[FAIL] 09:30:54 200 POST /v1/messages 0ms ↓0B: delivery stopped before upstream finished
propagated: ReadError connection reset by peer
```

这一条比 clean EOF 更值得处理：生产中「上游 43KB 之后断了」多半以 transport 异常出现，clean EOF 只是其中一种形态。而这次改动的全部动机就是「让操作者看到上游那一侧发生了什么」。

建议（小改）：`_tracked_delivery` 把退出原因交给 `finish()`，而不是只交一个布尔。例如在 `finally` 里读 `sys.exception()`（`stream.py` 已经用了这个手法），把 `GeneratorExit`／`CancelledError` 与其它异常分开，并把 `str(error)` 带进 `trace.detail`。三态足够：`drained` → 上游 clean EOF 无终止事件；取消／关闭 → 交付被放弃；异常 → 具名上游／交付错误。

### S2（should，判断 + 实测机制）客户端主动取消现在一律是红色 `[FAIL]`

按 Esc 取消一次 turn 会走 `_tracked_delivery` 的 GeneratorExit 分支，`failed = True`，前缀渲染为红色 `[FAIL]`。这在 Claude Code 客户端上是**高频正常操作**，改动前是 `[ OK ] 200`，改动后是红色失败行。

这不是「修好了一个误报」，而是把误报换了个方向：一个用户自己取消的请求既不是上游故障，也不是「请求出错」。`_Trace.failed` 的注释写的是「the request went wrong in a way its HTTP status cannot show」，取消并不满足这个描述。

更重要的是：**这条判据没有裁决可依**。本仓自己的调查 `docs/tmp/260820-truncated-stream-ruling-survey.md` 第 2 节明确记录「未检索到专门针对截断这一情形的 OK/FAIL 判据」。所以 `[FAIL]` 是这次改动新做的产品决定，按项目与用户规则应交用户裁决，而不是顺手定下。

候选之一是 `[WARN]`：`PREFIX_COLOURS` 已经有 `[WARN]` → `YELLOW`，但 `STATUS_PREFIXES`（`status=` 走的那张表）里**没有** `warn` 键，只有 `LEVEL_PREFIXES` 有，所以要用得补一个键——不是零成本，但也就一行。

建议：把「取消 → `[WARN]`／截断 → `[FAIL]`」作为一个明确的选项交给用户裁决，先不要默认把取消染红。

### S3（should，实测）`message_delta` 之后被切断时，行自相矛盾

Anthropic 先发 `message_delta`（携带 `stop_reason` 与 usage），再发内容为空的 `message_stop`。流在两者之间被切断时，`seen` 为假但 `stop_reason` 与 usage 都是**真实观测到的**，而且下游收到的字节与一次完全正常的应答**逐字节相同**（合成出来的 `message_delta` + `message_stop` 和上游本来要发的一模一样，什么都没丢）。

实测（`/tmp/probe4_delta_then_cut.py`）：

```
[FAIL] 09:28:27 H1/H1 200 anthropic-messages/claude-model 7ms ↑52B ↓541B ↑11 ↓22 end_turn: upstream stream ended without a terminal event
```

同一行既说 `end_turn` 和真实 token 数，又说「没有终止事件」。读者的第一反应会是「日志坏了」。

需要说清的是：**当前行为与冻结 Spec 一致**——STR-04 写的是「成功只在合法 terminal 且全部 block drain 后产生 `message_delta`＋`message_stop`」，缺 `message_stop` 按 Spec 就是 truncation。所以这不是合规缺陷，是**可读性缺陷**。

建议：`finish()` 在 `terminal.stop_reason` 非空时换一套措辞，例如 `upstream stream ended after its final delta, without message_stop`。不建议为此把 `seen` 的含义改掉——`seen` 之后要给 STR-04 用，不该在这里被稀释。

### S4（should，实测查证）「已知违反 Spec」这件事没有进入任何 living doc，而且它其实是新链路的回归

派单里说「`implementation.md`／`readiness.md` 已把它标为已知缺口」。**这一条不准确**，我逐文件核对过：

- `docs/agents/anthropic-responses-bridge/implementation.md`：全文没有 `STR-04`，也没有 truncation／terminal event 相关条目；只有反复出现的「完整产品 `UNVERIFIED`」。
- `docs/agents/service-cutover/readiness.md:59`：把 clean EOF 列在「Acceptance 要求……尚未执行」的清单里，状态是 `UNVERIFIED`。

「尚未验证」与「已知违反」是两个不同的断言。今天我们已经知道它违反了，而这个事实目前只活在一段代码注释和一个单测里——两处都不是做 Spec 合规审计的人会去翻的地方。

更值得注意的是：**legacy 链路已经实现了这条规则**。`src/app/delivery/responses_anthropic_stream.py:347`：

```python
    if not session.frontier.terminal_accepted:
        api_error = _upstream_error(
            "Responses stream ended before a successful terminal event",
            code="incomplete_responses_stream",
        )
```

也就是说 STR-04 在新 pipeline 链路上是**回归**，不是尚未开工的功能，而且旧实现现成可参照。这会改变这个缺口的优先级和实现成本估计（与项目记忆里「守卫被留在了 legacy 链路上」是同一个形态，这是第三次击发）。

建议：在 `implementation.md`（或该 topic 的 living 文档）加一行具名记录——当前新链路已知不符合 STR-04、现状被 `tests/unit/test_stream_delivery.py::test_a_stream_that_stopped_before_its_ending_is_recorded_as_truncated` 钉住、legacy 已有实现可参照。这比代码注释更接近「审计者会去看的地方」。

### S5（should，代码推演）`context.reply` 仍然 gate 在 `seen` 上，与 `trace.absorb` 不再一致

```python
self.trace.absorb(terminal)
if terminal.seen:
    if self.context is not None:
        self.context.reply = terminal
```

改动的核心论点是「观测到的事实不该被没观测到的事实拖着一起丢掉」，但这个论点只应用到了 `trace`，没有应用到 `context.reply`。而 `Terminal` 现在自带 `seen`，读者完全可以自己判断，gate 已无必要。`RequestContext.reply` 的注释说「`None` 表示没有到达任何 reply」，截断时其实到达了部分 reply。

今天无实际影响：全仓 `context.reply` **没有任何读者**（只有 `pipeline_app.py:296/329` 两处写）。但等 History／订阅者接上去时，两条交付路径对同一记录的取舍会不一致，而那时问题会以「截断请求在 History 里什么都没有」的形式重新出现。

建议：要么一并无条件写入，要么把「这里为什么保留 gate」写进注释（当前注释没解释）。

### N1（nit，代码推演）`finish()` else 分支的注释在断开这一支里是错的

那段注释仍是纯截断叙事：「Meanwhile the client was handed a `stop_reason` this proxy invented, so the operator is the only party who can be told what actually happened」。客户端断开时没有客户端可交付，这句话不成立。`drained` 补丁加了新的一行注释，但旧的那段没跟着调整。

### N2（nit，判断）`tools(...)` 与请求侧的 `tools` 声明同名

选词的理由在 docstring 里讲得很清楚，也确实不该借用 `tool_use`／`function_call`。唯一的风险是：Anthropic 请求体里本来就有一个 `tools` 数组，本仓也确实在处理工具声明（`subscribers/server_tools.py`）。一行日志上孤零零的 `tools(Bash,Read)` 可能被读成「这次请求声明了这些工具」。

多数情况下同一行末尾的 detail 会兜住语境，但 `elif line.tools` 只看 `stop_reason` 为空，buffered 回复缺 `stop_reason` 字段时也会命中，那种行没有 detail。若要更保险，`called(...)` 之类的动词形态更难被读成声明。判断，不强求。

### N3（nit，代码推演）「下游字节与改动前完全一致」有一个例外

上游发出 `message_delta` 且 `stop_reason` 为空字符串时：旧代码把 `""` 直接下发，新代码经 `or "end_turn"` 下发 `end_turn`。只有畸形上游触发，且新行为更好——只是这句断言本身需要收窄，别让它以后被当成一条被验证过的不变量。

### N4（nit，代码推演）注释引用的 Spec 句子出自 Responses 一节

`stream.py` 注释引用的「没有合法 terminal event 的 EOF 是 truncation」在 `spec.md:298`，属于「Upstream Responses HTTP SSE」一节；而 `stream_delivery` 同时服务 Anthropic 上游。WS 一节（`spec.md:304`）有同义表述，原则通用，我不认为这削弱了结论，但引用值得加半句限定。本仓自己的调查 `docs/tmp/260820-truncated-stream-ruling-survey.md` 也把「是否把这条字面扩大到 Anthropic 直连上游」列为待确认点。

### N5（nit，判断）STR-04 钉子把「长期不变」和「必须反转」的断言混在一个函数里

`test_a_stream_that_stopped_before_its_ending_is_recorded_as_truncated` 的四条断言分两类：

- 长期不变：`terminal.seen is False`、`terminal.stop_reason == ""`——STR-04 落地后依然成立；
- 必须反转：`'"stop_reason":"end_turn"' in body`、`"message_stop" in body`——STR-04 落地后必须变红。

而测试名字听起来完全像前一类。真正的风险不是「变红被误读成回归」（docstring 已经把这点讲死了，且 `rg STR-04` 能找到 acceptance.md、`stream.py`、这个测试三处，线索是通的），而是**落地时的拆分事故**：实现者看到红，最省事的动作是删掉整个测试，于是那两条长期不变的断言被顺手带走。建议拆成两个函数，或把名字改成一眼可见是待反转的钉子（例如 `..._is_still_given_a_synthesised_clean_ending_pending_str04`）。

### N6（nit，判断）测试导入私有名 + `# pyright: ignore[reportPrivateUsage]`：可接受

- 先例成立但不完全同型：`tests/unit/test_model_provider.py:270,273` 是**属性访问**上的同一条 ignore；模块级私有名 import 是首例（全仓 `rg reportPrivateUsage` 只有这两处 + 本次三处）。
- 我认为可以放行：替代方案是为一个测试把 `_StreamAccounting`／`_tracked_delivery` 提升为公开 API，那是更差的交换。
- 唯一的违和是分组：这条测试完全绕过 HTTP 层，而 `tests/http/test_pipeline_app.py` 的文件头写的是「upstream protocol behaviour is therefore the real thing rather than a friendlier stand-in」。它留在这里是因为要复用 `make_client`／`_chain_of`／`request_log`，docstring 也解释了为什么必须绕过 `TestClient`。够了，不必搬。

## 2. 逐条回答派单中的重点问题

### 2.1 `Terminal.stop_reason` 默认值改动的波及面

**独立复核结论：你的清点是对的，没有遗漏。** 证据：

- 消费点只有两处：`stream.py:177`（已用 `or "end_turn"` 承接）、`pipeline_app.py:97`（`_Trace.absorb` → `RequestLine.stop_reason` → `format_completion_line` 的 `if line.stop_reason:` 守卫，空值天然掉出）。
- 第三个写入点 `context.reply`（`request.py:77`）**全仓没有读者**，只有两处写（见 S5）。
- `terminal_from_anthropic`（`assembler.py:80`）本来就显式传 `stop_reason=""`，且其 docstring 早就写明「The stop reason starts empty rather than at the class default」——改动前后一致。
- `ResponsesAssembler._read_terminal`（`assembler.py:298-315`）在 `response.completed` 与 `response.incomplete` 两条分支上都显式赋值，从不依赖默认值。
- `AnthropicAssembler._read_terminal`（`assembler.py:184-192`）只在 `message_delta` 到达时赋值——正是默认值该生效的场景。
- `src/app/delivery/` 的 legacy 链路用的是另一个类型 `ResponsesTerminal`（`openai/responses_stream_parser.py:65`），与本次改动无关。
- 测试侧：`rg "Terminal\("` 在 `tests/` 只命中 `ResponsesTerminal`；`rg "terminal\.stop_reason"` 的 6 处命中全部断言具体值或空值，没有任何一处依赖旧默认 `end_turn`。

### 2.2 Anthropic 的 `message_delta` / `message_stop` 之间被切断

见 S3。组合本身不算「不合理」——它与冻结 Spec 一致，而且 `failed=True` 在 Spec 语义下站得住；问题纯粹在这一行读起来自相矛盾，且这是**唯一一种什么都没丢的截断**。

### 2.3 客户端断开的误报风险

派你之前的版本**确实会**误报（我在 `drained` 补丁落地前读到的 `finish()` 只看 `seen`，没有任何其他输入，因此断开必然落入截断分支）。你已自行实测确认并修复。

对修复本身的评估：

- `drained` 的机制是可靠的。`async for` 正常结束才置位；`aclose()` 的 GeneratorExit 与任务取消的 CancelledError 都在 `yield` 处展开，必然跳过那一行。这是 Python 生成器的语言语义，不依赖 Starlette 的实现细节。
- 我完整枚举了到达 `finish()` 且 `seen` 为假的路径，**第三条你漏了**：`stream_delivery` 抛异常（S1）。它同样跳过 `drained = True`，于是上游 RST 被写成 `delivery stopped before upstream finished`。
- 第四条 `_AccountedStreamingResponse.__call__` 的 `finally`（body 一次都没被迭代，例如首次 `send` 失败）也会 `drained` 为假 → 归为「交付停止」，这条归类是对的。
- 措辞：`upstream stream ended without a terminal event` 准确；`delivery stopped before upstream finished` 对断开准确、对异常不准确（S1）。

关于 ASGI 边界的 `send` 抛 OSError 那条路：**我认为不值得追**。理由有二：一是判别逻辑完全在 `_tracked_delivery` 内部，Starlette 交付的是 GeneratorExit 还是 CancelledError 都同样跳过 `drained = True`，那条测试要证明的东西已经被现在这条覆盖；二是那里能额外证明的只有「Starlette 真的会关闭 body 生成器」，那是第三方契约，`tests/smoke/test_anthropic_responses_stream_route.py` 已有同型覆盖。挂死的原因大概率是 Starlette 的 `StreamingResponse` 用 anyio task group，其 `__aexit__` 的清理对外层 `asyncio.timeout` 的取消不敏感——这也说明那条路的调试成本远高于收益。

### 2.4 `tools(...)` 的用词

见 N2。在本仓用词体系里站得住：`format_thinking` 已有 `think`／`reason` 这种「非上游原词的房内词」，所以造一个词不违和；风险只在与请求侧 `tools` 声明重名。

### 2.5 测试鉴别力

你已变异验证过的那条之外，逐条评估：

| 测试 | 能抓住什么 | 判定 |
|---|---|---|
| `test_a_stream_that_did_terminate_is_still_reported_as_one` | 「无差别把所有流报成截断」这一类过度修复；断言 `status == "ok"` + `end_turn` in line + detail 不出现 | 有鉴别力，是 S1 那条的必要对照 |
| `test_a_client_that_walked_away_is_not_blamed_on_upstream` | 措辞判断被写成恒真；你已变异验证 | 有鉴别力。补充一点：它断言 `status == "fail"`，因此若采纳 S2（取消改 `[WARN]`），这条断言需要一起改 |
| `test_tools_without_a_stop_reason_are_still_named` | 删掉 `elif line.tools` 分支 → 红；改词（`tool_use(...)`）→ 红 | 有鉴别力。`assert "tool_use" not in line and "function_call" not in line` 在无 stop_reason 时近乎恒真，是措辞守卫而非行为守卫，留着无害 |
| `test_a_stream_cut_off_before_its_ending_still_says_what_it_did_produce` | 恢复 `stop_reason: str = "end_turn"` 默认值 → 红（这是它的核心断言）；tools/thinking 两条是既有行为的回归守卫 | 有鉴别力 |
| `test_a_stream_that_stopped_before_its_ending_is_recorded_as_truncated` | 删掉 `or "end_turn"` → body 里出现 `"stop_reason":""` → 红 | 有鉴别力，正是它声称要防的事 |

另外两点：

- `_request_outcomes` 的 `(line, status), = ...` 单元素解包是有效守卫：「一行都没打」和「打了两行」都会以 `ValueError` 失败，不会静默通过。
- 没有发现恒真断言（近似恒真的只有上表标注的那一条措辞守卫）。
- 缺口：S1 那条路径（上游异常撕断）目前没有任何测试。建议在修好措辞之后补一条——这是一个**已被实测证实的真实失败面**，不是为覆盖率补的矩阵。

### 2.6 注释与文档质量

整体符合本仓风格（解释为什么、记录踩过的坑，而不是复述代码），且我逐条核对过它引用的外部事实，**都属实**：`spec.md` 状态确为 `FINALIZED`、第 298 行文字属实、STR-04 的「在 clean EOF 上调用正常 flush」确实被列为必须变红的缺陷注入点。

问题只有三处：N1（`finish()` 注释在断开分支上已过时）、N4（引用范围）、以及 `Terminal.stop_reason` 那条注释偏长——但它记录的是一次真实的语义混淆，我不建议压缩。

## 3. 对「留而不修 + 钉住 + 标注」的评估

**赞成这个划分，且认为它讲得通。** 理由：

1. STR-04 是**客户端可见的协议变更**（改发 SSE `error` event、不再发 `message_stop`），它会改变客户端 history 里存的东西；而这次改动是**操作者可见的日志修复**，两者的受众、回滚成本、验收面都不同。把前者塞进后者，会让一个日志修复变成协议修复。
2. 它有独立的验收判据（STR-04 的正确样本 + 缺陷注入 + 通过判据），本来就该单独走一轮。
3. 钉住 + 注释让缺口可搜索（`rg STR-04` 三处相连），比「先删了 `or` 再说」安全得多——你担心的那个具体风险（顺手删掉 `or "end_turn"` 从而下发 `stop_reason: ""`）是真实的，钉子正对着它。

会不会在 STR-04 落地时变成阻碍？**会变红，但红得有解释**，这不构成阻碍。真正的风险不是误读，而是拆分事故——见 N5。

两条改进：

- N5：拆开长期不变量与待反转钉子，或给名字加上待反转的标记。
- S4：把「已知违反」写进 living doc，并把定性从「尚未验证」修正为「新链路回归，legacy 已有实现」。你给出的理由里「已标为已知缺口」这一条**事实上不成立**，而这恰恰是这个划分唯一薄弱的支撑点——补上它，划分就完整了。

不建议的做法（记录以免重复讨论）：`pytest.mark.xfail` 语义不对（测试今天是通过的）；专门的 `known_spec_gap` marker + `--strict-markers` 注册属于与 ROI 不相称的证明设施，不该为一处缺口建。

## 4. 已核查、未构成问题（记录以免重复排查）

1. **上游返回 4xx/5xx 的流式请求不会走到截断分支**。实测：上游 400 → `UpstreamRejected` → JSONResponse 400（不进 streaming 分支）；上游 500 → 重试预算耗尽 → 502。所以不存在「上游错误响应被写成 upstream stream ended without a terminal event」。
2. **`Terminal` 默认值改动没有第三个消费点**（详见 2.1）。
3. **测试没有依赖旧默认值**，改动不会静默改变任何既有断言的含义。
4. **`_StreamAccounting.finish` 的幂等性未被破坏**：`done` 守卫仍在最前，两个 `finally`（生成器与 `__call__`）竞争时仍只记一次。
5. **与并行会话的 `aclosing` 改动无冲突**：clean EOF 仍然从 `async for` 正常退出（`test_a_stream_that_never_terminated_...` 打出 `upstream stream ended without a terminal event` 就是活证据，它要求 `drained` 为真），`finish_stream_cleanup` 没有把正常 EOF 变成异常退出。
6. **`ruff check` 与 `pyright` 对全部 8 个文件干净**；四个测试文件 140 passed。

## 5. 建议的处理顺序

1. S1（补第三条路径的措辞与异常信息）——它是这次改动目标的直接延伸，且已有实测证据。
2. S2（把取消染红这件事交用户裁决）——在裁决前不要固化，因为它已经在改变每天都能看到的界面。
3. S4（living doc 记一行 + 修正定性）——成本一行，收益是缺口不再只活在代码里。
4. S3、S5、N1～N6 可并入下一个切片。

---

附：本次评审用到的一次性探针留在 `/tmp/probe2_error_status.py`、`/tmp/probe3_error_status.py`、`/tmp/probe4_delta_then_cut.py`、`/tmp/probe6_upstream_reset.py`（均在仓库之外，未落入工作树）。
