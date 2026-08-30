# 合成回复在非 Anthropic 入站腿上的调查（GitHub issue #1）

日期：2026-08-30
性质：只读调查报告原件，点时间记录。
**预期落盘位置：`/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/reports/260830-synthesized-reply-non-anthropic-leg-survey.md`。** 该路径在本次调查后半程被 worktree 隔离守卫拦下（见第 9 节），本文件是它的临时落点，请主会话 `cp` 到上述位置后删除临时副本。

调查范围：`HandledRequest(synthesized=True)` 的全部生产者、它们在 `inbound_format != ANTHROPIC_MESSAGES` 时的可达性、缓冲路径的同族缺陷、gate 的可达性、既有测试覆盖、以及 `web_search_call` 在直连 Responses 腿上的往返形态。

**锚定提交未记录。** 调查后半程 Bash 被守卫拦死，没能补取 HEAD 哈希。本报告引用的行号是 2026-08-30 当日主工作树 `/home/xp/src/ghc-api-proxy-py` 的状态。

## 0. 结论摘要

| # | 问题 | 结论 | 证据等级 |
|---|---|---|---|
| 1 | 合成回复生产者 | 全仓恰好两处：`driver.py:150-155`（auto-mode）与 `driver.py:193-198`（failed search）。**auto-mode 有 inbound 格式守卫，failed search 没有** | 读码 + 实测 |
| 2 | `ContinuationSupport.synthesize` | 产出 `TOOL_USE` 块，`ResponsesFramer` 认得；且它在 inbound=OPENAI_RESPONSES 时**不可达**（`hand_back_block` 第一行就按 inbound 格式返回 `None`）。此处无缺陷 | 读码 |
| 3 | 缓冲（非流式）同族缺陷 | **会。** 一个原生 `/responses` 非流式请求拿到 200 + 一份 Anthropic message body（`{"type":"message","content":[{"type":"server_tool_use"},…]}`），Responses 客户端无法解析 | **实测复现** |
| 4 | gate 可达性 | 确实在原生 Responses 请求上击发，且 `context.payload` 就是客户端原样的请求体（无翻译） | **实测复现**（upstream 调用数 = 0） |
| 5 | 既有测试覆盖 | **零覆盖。** `test_pipeline_app.py` 里 7 条 web search 测试全部 POST `/v1/messages`；全仓没有任何一条测试把 `tools` 发到 `/responses` | 读码 + 全仓 grep |
| 6 | `web_search_call` 往返 | 客户端收到的是一个 **assistant `message` item**，正文是散文 `[web_search] <query>`，原始 `web_search_call` item 不复存在。与模块顶部注释第 7 行一致 | 读码（实测被守卫打断，见第 9 节） |

**issue #1 的机制已实测复现，且它有一个同族的孪生缺陷（第 3 条）在非流式路径上，症状不是撕流而是静默返回错协议的 body。** 第 3 条比 issue #1 更隐蔽：HTTP 200、日志行 `status=ok`、没有任何异常。

## 1. 合成回复的全部生产者

`rg -n "synthesized" src/ tests/` 全仓命中 `synthesized=True` 恰好两处，都在 `src/app/pipeline/driver.py`：

### 1.1 `_answered_auto_mode` — `driver.py:143-155`

**有 inbound 格式守卫，而且是显式的。** `driver.py:138`：

```python
if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
    verdict = classify(...)
```

`driver.py:137` 的注释把这条守卫的来历写死了：曾经没有它，一个 Chat Completions 请求因为 content parts 碰巧命中标记而被回了一份 Anthropic body。所以这条腿**已经修过一次同一形状的 bug**，而 failed-search 那条腿没有跟着改。

即便拿掉守卫，`classify` 的判据也读不到 Responses body 的任何东西：

- `auto_mode_classifier.py:131-137` `_has_classifier_shape` 要求 `payload["messages"]` 是 list；Responses 请求体没有 `messages`（它用 `input`），`isinstance(messages, list)` 为 False → 直接 `return False`。
- `auto_mode_classifier.py:174` 是 `classify` 的第二道门（`if not _has_classifier_shape(payload): return None`），排在两个文本标记之前，注释 `:170` 说明这是有意的结构下限。
- 两个标记本身也都读 Anthropic-only 字段：`_matches_system_prompt` 读 `payload["system"]` 的 block 列表（`:58-60`），Responses 用的是 `instructions`（字符串）；`_matches_transcript_wrapper` 读 `payload["messages"][-1]`（`:88-91`）。

**所以 auto-mode 这条腿是双保险：格式守卫 + 判据天然读不到。** 结论：inbound=OPENAI_RESPONSES 时不可达。

`context.inbound_format` 的来源确认：`src/app/server/inbound.py:61` `inbound_format=route.wire_format`，而 `src/app/server/routes/table.py:37` 把 `/responses` 登记为 `WireFormat.OPENAI_RESPONSES`。

### 1.2 `_answered_failed_search` — `driver.py:191-198`

```python
outcome = await driver.run(context)
if isinstance(outcome.error, WebSearchNotExecutable):
    return HandledRequest(
        context=context,
        route=route,
        outcome=_answered_failed_search(context, route),
        synthesized=True,
    )
```

**没有任何条件把它限制在 Anthropic 客户端腿上。** 唯一的判据是 `outcome.error` 的类型。而抛出它的 `gate_hosted_web_search` 的判据是 `context.target_format is WireFormat.OPENAI_RESPONSES`（`hosted_web_search.py:94`）——那是**上游腿**的格式，与客户端腿正交。两者相交出的那一格恰恰是 issue #1：inbound=OPENAI_RESPONSES 且 target=OPENAI_RESPONSES（直连，无翻译）。

`_answered_failed_search`（`driver.py:201-226`）产出的内容：

- 流式：`failed_search_sse(...)`，`content-type: text/event-stream`；
- 非流式：`dumps(failed_search_body(...))`，`content-type: application/json`。

两者都是 Anthropic Messages 形态。`driver.py:204` 的 docstring 明说「`synthesized` is what tells the delivery side to read it as Anthropic」——即它把「我们写的」等同于「Anthropic」，这个等式在客户端也说 Anthropic 时才成立，而没有任何地方检查过这一点。

顺带一个值得记的细节：`query_from_request`（`anthropic_messages_synthetic_reply.py:34-50`）**已经会读 Responses 形态的 body**（`messages` 读不到就退回 `input`，见 `:46-49`），docstring `:39` 说这是为了应付「翻译之后」的 body。实测里它从 `/responses` 的 `input` 里正确取到了 query。也就是说，合成回复这条链路的下半截已经知道自己可能站在 Responses body 上，只有「用什么协议把它写出去」这一步没跟上。

### 1.3 两处的对照

| | auto-mode | failed search |
|---|---|---|
| inbound 格式守卫 | `driver.py:138` 显式 | **无** |
| 判据是否天然限定 Anthropic | 是（`messages`/`system`） | 否（判据是上游腿的 `target_format`） |
| 触发点 | 翻译**之前**（`driver.py:135` 注释说明） | `driver.run` **之后** |
| 历史 | 已因同一形状的 bug 修过一次 | 未修 |

## 2. `ContinuationSupport.synthesize`

**结论：块 kind 是 `ResponsesFramer` 认得的，且这条路径在 inbound=OPENAI_RESPONSES 时不可达。此处无缺陷。**

- 块 kind：`stream.py:609` `CompletedBlock(index=..., kind=TOOL_USE, payload=payload)`。`ResponsesFramer.block` 的 `if block.kind == TOOL_USE`（`openai_responses.py:180`）认得它，走 `_function_call`。
- payload 形态兼容：`hand_back_block` 返回 `{"type": "tool_use", "id": ..., "name": ..., "input": {...}}`（`hand_over.py:275-285`），而 `_function_call` 读的正是 `payload["id"]`（当 `call_id`）、`payload["name"]`、`payload["input"]`（`openai_responses.py:261-267`）。就算走到也不会炸。
- 可达性：`hand_over.py:238-239`

```python
if wire_format is not WireFormat.ANTHROPIC_MESSAGES:
    return None
```

`wire_format` 由 `inference.py:317` 传入 `wire_format=route.wire_format`，即 InboundRoute 的入站格式。所以 `/responses` 上 `synthesize` 返回 `None`，`_hand_over`（`stream.py:598-600`）随即 `return None`，结尾落回原来的结尾。

- 一处**已经写在代码里的确认**：`stream.py:611` 的注释「`synthesize` refuses any client that did not ask in Anthropic Messages, so only that framer is ever reached here」。这条注释成立，靠的正是 `hand_over.py:238` 那道门。**它是 failed-search 那条腿缺的那道门的现成范本。**

## 3. 缓冲（非流式）那一侧的同族缺陷

**结论：会。一份 Anthropic message body 会原样返回给 Responses 客户端。已实测复现。**

代码路径：

1. `inference.py:322` `if context.stream:` 为假 → 落到 `:524` 之后的缓冲分支。
2. `inference.py:527` `parsed_reply = response.json()` —— 合成响应的 `content-type` 是 `application/json`，body 是 `dumps(failed_search_body(...))`，解析成功。
3. `inference.py:545` `payload = response_payload(chain, handled, body)`。
4. `reply.py:25-28`：

```python
if handled.synthesized:
    # Already in the client's format: this proxy wrote it, in the shape the client asked in.
    return body
```

这句注释是错的——它把「this proxy wrote it」直接读成「in the shape the client asked in」，而这两件事只有在客户端说 Anthropic 时才是同一件事。注释后半句「Translating it would carry an Anthropic body through the Responses reader」描述的是**翻译腿**（inbound=Anthropic，target=Responses）的正确考虑，但那个 `if` 的条件里没有任何东西把它限定在那条腿上。

5. `inference.py:549` `context.reply = reply_summary(handled, payload)` → `reply.py:66-67` 因 `inbound_format is not ANTHROPIC_MESSAGES` 返回 `None`，日志行不报回复内容（这一步本身是对的，但它顺带让这个缺陷在日志上更不可见）。
6. `inference.py:573` `return JSONResponse(payload, status_code=response.status_code)` → 200 + Anthropic body。

**实测输出**（详见第 7 节）：

```
NONSTREAM status: 200
NONSTREAM upstream calls: 0
NONSTREAM body: {"id":"msg_e48760436db847aba8b66735","type":"message","role":"assistant","model":"gpt-model","content":[{"type":"server_tool_use",…},{"type":"web_search_tool_result",…}],"stop_reason":"end_turn",…}
```

日志行：`H1/H1 200 openai-responses/gpt-model 0ms ↑0B ↓480B status=ok`。

**这比 issue #1 更危险的地方**：流式那条会抛 `ValueError` 并在完成行上留下 `status=fail` 加原因；非流式这条**没有任何异常、没有任何告警、状态是 `ok`**。客户端拿到一个它的 SDK 解析不了（或者更糟——静默解析成一个没有 `output` 的空响应）的 200。判定这条是 major，与 issue #1 同源、同一处修复点。

## 4. `gate_hosted_web_search` 的可达性

**结论：确实在原生 Responses 请求上击发；`context.payload` 就是客户端原样的请求体。已实测复现（upstream 调用数 = 0，即 gate 在发出前就拦下了）。**

完整代码路径：

1. `inference.py:147-148` 路由匹配 → `table.py:37` `InboundRoute("/responses", WireFormat.OPENAI_RESPONSES, openai_prefixed=True)`，`implemented` 默认 True。
2. `inference.py:188` `build_context(route, body, ...)` → `inbound.py:60-68`，`inbound_format=OPENAI_RESPONSES`，`payload=deepcopy(body)`（**客户端原样的 body**，只有 Azure 那几条路由会改写 `model`）。
3. `inference.py:267` `handle_bounded` → `driver.handle` → `driver.shape_request`（`driver.py:133`）。
4. `driver.py:94-101` `decide_route`：`gpt-5.6-sol` 的 catalog 支持 `/responses` → `routing.py:320-323` `inbound_endpoint` 被支持 → `endpoint = /responses`，`target_format = OPENAI_RESPONSES`，**`translation_required = False`**（`routing.py:335`：`target_format is not inbound_format` 为假）。`apply_route`（`routing.py:361-368`）把 `context.target_format` 写成 `OPENAI_RESPONSES`，`context.provider_name` 写成 provider 名。
5. `driver.py:111` 的 Anthropic-only 修补块被跳过（inbound 不是 Anthropic），`fix_anthropic_request` 不跑。
6. `driver.py:138` auto-mode 守卫跳过。
7. `driver.py:157` `if route.translation_required:` 为**假** → **不翻译，`context.payload` 保持客户端原样**。
8. `driver.py:172` 只改 `context.payload["model"] = route.model_id`。
9. `driver.py:177-190` 建 driver → `driver.run`（`direct_driver/base.py:136`）。
10. `direct_driver/base.py:145` `await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)` → `subscribers/__init__.py:73-76` 注册的 `gate_hosted_web_search`。
11. `hosted_web_search.py:94` `context.target_format is not WireFormat.OPENAI_RESPONSES` → 为假，**不返回**。`:96` `COUNTING_ONLY` 未设。`:99-101` `enabled` 默认 False（或模型不在列表）→ 不返回。`:102-106` `context.payload.get("tools")` 是客户端原样的 `[{"type":"web_search"}]`，`_is_hosted_web_search` 命中 `type == "web_search"`。
12. `:109-120` 抛 `WebSearchNotExecutable`。
13. `direct_driver/base.py:155-158` 捕获 → `_handle_failure`（`:212`）→ `exceptions.classify`（`exceptions.py:127-137`）：`WebSearchNotExecutable` 不是 `PipelineAbort`，也不在 `_RETRYABLE = (UpstreamError, PipelineRetry)`（`exceptions.py:124`）里 → `Disposition.ABORT` → `outcome.error = error`（`:232`），返回 False → `run` 返回 outcome。
14. 回到 `driver.py:191` `isinstance(outcome.error, WebSearchNotExecutable)` 命中 → 合成。

**关键的一点**：原生 Responses 客户端送的 `{"type": "web_search"}` 与翻译器为 Anthropic 客户端生成的 `{"type": "web_search"}` 逐字节相同，gate 分不出来——而 `hosted_web_search.py:29` 的注释恰恰声称能分：

> The spelling the translator emits, and the only one this reads. A client that sent a Responses request naming a builtin directly is left alone: it asked this endpoint for its own feature in its own words, and second-guessing that is not what a capability gate is for.

**这条注释描述的行为与代码不符。** 代码没有任何机制把「翻译器写的」与「客户端自己写的」分开——两者都落在同一个 `context.payload["tools"]` 里，同一个字符串。要真正实现注释承诺的「left alone」，需要一个新的判据（例如翻译器在 `context.extras` 里留标记，或读 `route.translation_required`）。这是一处独立于崩溃本身的**文档-代码失配**，判定 major：它会让下一个读代码的人以为这一格已经被处理过。

## 5. 现有测试覆盖

**结论：零覆盖。**

`tests/int/test_pipeline_app.py` 中的 7 条 web search 测试，**全部 POST `/v1/messages`**，即 inbound=ANTHROPIC_MESSAGES：

| 行号 | 测试名 | inbound 路径 | inbound 格式 |
|---|---|---|---|
| 400 | `test_an_anthropic_web_search_declaration_reaches_upstream_in_its_own_spelling` | `/v1/messages`（:422） | ANTHROPIC_MESSAGES |
| 444 | `test_a_streamed_search_is_delivered_as_a_line_rather_than_an_empty_block` | `/v1/messages`（:474） | ANTHROPIC_MESSAGES |
| 496 | `test_hosted_web_search_is_off_until_the_config_says_otherwise` | `/v1/messages`（:518） | ANTHROPIC_MESSAGES |
| 539 | `test_a_search_that_cannot_run_is_answered_as_a_failed_tool_not_an_error` | `/v1/messages`（:561） | ANTHROPIC_MESSAGES |
| 589 | `test_a_streamed_search_that_cannot_run_is_answered_the_same_way` | `/v1/messages`（:606） | ANTHROPIC_MESSAGES |
| 632 | `test_the_shape_claude_code_really_sends_reaches_upstream_as_a_search` | `/v1/messages`（:654） | ANTHROPIC_MESSAGES |
| 681 | `test_a_domain_restriction_refuses_before_upstream_is_called` | `/v1/messages`（:705） | ANTHROPIC_MESSAGES |

其中 496 与 589 正是与 issue #1 同形的两条（gate 拒 → 合成回复），只是入站腿是 Anthropic，所以 `AnthropicFramer` 认得 `server_tool_use`，全绿。

`tests/unit/pipeline/subscribers/test_builtin_subscribers.py` 里的 gate 测试（`:354`、`:378`、`:398`、`:419`、`:441`、`:466`、`:492`、`:518`、`:548`）全部**直接调用** `gate_hosted_web_search(context, ...)`，手工构造 `RequestContext` 并只设 `target_format`——它们完全不经过入站路由，**结构上无法覆盖 inbound 格式这一维**。

全仓 grep 确认：没有任何测试把 `tools` 发到 `/responses`。所有 POST `/responses` 的测试（`test_pipeline_app.py:2499`、`:2591`、`:3839`，`test_error_envelope.py:152`、`:252`、`:497`）body 都是 `{"model": …, "input": []}`，不带 `tools`。

**这就是测试全绿而生产撕流的原因**：合成回复的每一条测试都站在同一条入站腿上，而缺陷恰在另一条腿上。补测的最小形状是「`/responses` + `tools=[{"type":"web_search"}]`」两条（流式、非流式各一），第 7 节的复现脚本可以直接改成它们。

## 6. `ResponsesAssembler` 对 `web_search_call` 的处理

**结论：模块顶部注释第 7 行与代码一致。客户端拿到的是一个 assistant `message` item，正文是散文 `[web_search] <query>`；原始 `web_search_call` item 不复存在。**

`openai_responses.py:5-7` 的注释：

> A `web_search_call` item does not survive the round trip. The assembler rewrites it into a text block with prose describing the search, deliberately, because Anthropic has no spelling for it. A Responses client that could have read the real item gets that prose instead.

逐步核对代码：

1. `_open`（`:505-520`）：item 类型映射表 `:509-517` 里**没有** `web_search_call` 这一项，`.get(item_type, item_type)` 于是让 `kind` 落成字符串 `"web_search_call"`，恰好等于模块常量 `WEB_SEARCH_CALL`（`:387`）。`:386` 的注释明说这是有意的：「Carried as its own draft kind so `_close` can tell it from a message and render it」。
2. `_close`（`:605-611`）：

```python
elif draft.kind == WEB_SEARCH_CALL:
    raw = data.get("item")
    item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    payload = {"type": TEXT, TEXT: web_search_call_text(item.get("action"))}
    kind = TEXT
```

`kind` 就地改写成 `TEXT`，payload 变成一个纯文本块。
3. 文本内容：`web_search_call_text`（`server_tool_text.py:35-55`）→ `call_text("web_search", {"query": …})` → `server_tool_text.py:30-32` 返回 `f"[{family}]{call_subject(raw_input)}"`，即 `[web_search] <query>`；`action` 缺失时是裸 `[web_search]`。
4. 交付侧：`delivery_policy.framer_for`（`delivery_policy.py:70-71`）按 `route.inbound_format is OPENAI_RESPONSES` 选 `ResponsesFramer`；`ResponsesFramer.block` 的 `elif block.kind == TEXT` → `_message`（`:191-251`），发出 `response.output_item.added`（item 类型 `"message"`，role `assistant`）、`content_part.added`、`output_text.delta`、`output_text.done`、`content_part.done`、`output_item.done`，正文即那句散文。
5. 直连腿不会绕过这一层：`inference.py:515` 传的 `passthrough=not context.translation_required` 在直连时为 True，但 `passthrough` **只影响一件事**——`stream.py:282-293` `_report_failure` 在上游报错时是否原样回抛上游的失败事件。正常内容仍然走 assembler + framer。`stream.py:311` 的 docstring 明说「It changes exactly one thing」。
6. 相邻的两个 item 类型：`tool_search_output` 一律 `DISCARDED`（`:516`），`tool_search_call` 在没有 `client_search_tool` 名字时也 `DISCARDED`（`:514`）——而直连 Responses 腿上 `client_search_tool` 恒为空（它由请求翻译写入 `context.extras`，见 `driver.py:165-167`，直连不翻译）。所以直连腿上这两类 item 都会被静默丢弃。

**副作用（值得单列）**：`output_index` 由 framer 自己数（`:188` `self._output_index += 1`，`:13` 注释解释为什么不用 `CompletedBlock.index`）、item id 全部重铸（`:10`）。所以直连 Responses 客户端拿回来的 item id 与 `response.id` 都不是上游的。这是已记录的有意行为，不是缺陷，但它意味着「直连 = 透传」这个直觉在本项目里不成立，判断第 6 条时不要用它。

**证据等级**：本条**只有读码**。为它准备的实测脚本（`/tmp/repro_issue1/test_q6.py`，用 `tests/int/cassettes/responses_web_search_stream.json` 驱动）在提交运行前被 worktree 守卫拦下（第 9 节）。间接支撑：仓库既有测试 `test_pipeline_app.py:444` 用同一份 cassette 证明了 assembler 侧确实产出 `[web_search] ` 开头的文本块（`:490` 断言），只是它经 `AnthropicFramer` 出口。也就是说链路上**只有最后一步（`ResponsesFramer._message`）没有被实际跑过**，而那一步是无分支的直读。判定：足以据此行动，但补一条 `/responses` 的 cassette 测试仍值得。

## 7. 实测记录

复现脚本写在仓库外（`/tmp/repro_issue1/test_repro.py`），复用 `tests/int/test_pipeline_app.py` 的 `make_client` 与 MockTransport，未改动仓库任何文件。

配置：`models_support_web_search: ["gpt-model"]`，`hosted_web_search` **不设**（用默认 off）——与 `test_hosted_web_search_is_off_until_the_config_says_otherwise` 的构造理由相同：让开关成为唯一说「不」的东西。

请求：`POST /responses`，body `{"model": "gpt-model", "input": [{"role":"user","content":"search for bun"}], "tools": [{"type":"web_search"}]}`。

命令：`uv run pytest /tmp/repro_issue1/test_repro.py -s -q -p no:cacheprovider` → `2 passed`。

原始输出：

```
[debug] POST /responses  status=pending
[info ] H1/H1 200 openai-responses/gpt-model 0ms ↑0B ↓480B  status=ok
NONSTREAM status: 200
NONSTREAM upstream calls: 0
NONSTREAM body: {"id":"msg_e48760436db847aba8b66735","type":"message","role":"assistant","model":"gpt-model","content":[{"type":"server_tool_use","id":"srvtoolu_58e485ee3fc64df6b8a29f23","name":"web_search","input":{"query":"search for bun"}},{"type":"web_search_tool_result","tool_use_id":"srvtoolu_58e485ee3fc64df6b8a29f23","content":{"type":"web_search_tool_result_error","error_code":"unavailable"}}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":0,"output_tokens":0}}

[debug] POST /responses  status=pending
[info ] H1/H1 200 POST /responses gpt-model 1ms ↑0B ↓1.0KB: stream failed before a terminal event: no Responses item shape for block kind 'server_tool_use' req=db0c48ee-…  status=fail
STREAM upstream calls: 0
STREAM bytes: b''
STREAM raised: ValueError("no Responses item shape for block kind 'server_tool_use'")
```

这一次运行同时钉死了四件事：

- 流式：issue #1 的 `ValueError` 逐字复现，**客户端收到零字节**（`STREAM bytes: b''`）——状态码 200 已经先发出去了，所以客户端看到的是一个空的 200 SSE 流。
- 非流式：第 3 节的孪生缺陷复现，200 + Anthropic body，日志 `status=ok`。
- gate 可达性：两次都是 `upstream calls: 0`，即 gate 在发出前拦下，证实第 4 节的路径。
- `query_from_request` 从 Responses 的 `input` 里正确取到了 `"search for bun"`——合成回复的内容组装是对的，错的只有「用哪个协议写出去」。

## 8. 排除掉、认为不成立的可能性

写下来是为了让后来者不必重走这几条：

1. **「`passthrough=True` 会让直连 Responses 腿绕过 framer，所以问题只出在翻译腿」** —— 不成立。`stream.py:311` 与 `:282-293` 证明 `passthrough` 只改变上游报错时的一帧的写法，正常内容仍然走 assembler + framer。实测的 `ValueError` 正是从 framer 里抛出来的，而那次请求 `translation_required` 为 False。
2. **「auto-mode 那条腿也有同样的洞」** —— 不成立，且是双保险。`driver.py:138` 有显式格式守卫，`auto_mode_classifier.py:131-137` 的结构下限又要求 `messages` 是 list。两道都过不去。（我一开始按「两处对称」的直觉预期它也有洞，判据推翻了这个预期。）
3. **「`ContinuationSupport.synthesize` 会造出 framer 不认的块」** —— 不成立。kind 是 `TOOL_USE`，`ResponsesFramer` 认得，payload 字段也对得上（`hand_over.py:275-285` vs `openai_responses.py:261-267`）。而且它压根到不了那儿（`hand_over.py:238`）。
4. **「gate 的注释说它放过原生 Responses 客户端，所以直连请求本来就不该被拦」** —— 注释（`hosted_web_search.py:29`）确实这么说，但**代码没有实现它**：翻译器写的 `{"type":"web_search"}` 与客户端自己写的逐字节相同，`_is_hosted_web_search` 分不出来。实测证明了拦截确实发生。所以这不是「可能性被排除」，而是「注释被证伪」——见第 4 节末，这本身是一条独立的 major。
5. **「非流式那条也许在 `response.json()` 那里就炸了，所以不会静默返回错 body」** —— 不成立。合成响应的 `content-type` 是 `application/json`，body 是合法 JSON 对象，`inference.py:527-543` 的两道检查都通过。实测拿到了 200 和完整 body。
6. **「`reply_summary` 返回 `None` 会让请求走上错误分支」** —— 不成立。`inference.py:569` 是 `if context.reply is not None:`，`None` 只是少写几个日志字段。它不影响 body。
7. **「Chat Completions 腿上也有同一个洞」** —— 未成立，但**理由与 Responses 腿不同，不要照搬**：`delivery_policy.delivers_blocks`（`:45-47`）对 `synthesized` 直接返回 True，绕过了 Chat Completions 的 `None`-framer 分支，于是 `framer_for`（`:70-72`）落到 `AnthropicFramer` —— 也就是说 Chat Completions 客户端会拿到一份 **Anthropic SSE**，不撕流、不报错，静默错协议。这一格我**没有实测**（Bash 被拦），也不在本次派活范围内，登记为待查项。**注意它与第 3 节非流式那条是同一类失效（静默错协议）而非同一条。** 另外 Chat Completions 腿上 `target_format` 通常不是 OPENAI_RESPONSES，gate 因此不击发；能到这一格需要一条 chat-completions 入站 + responses 上游的翻译路线，而 `delivery_policy.py:63-68` 显示这样的翻译器今天没注册。所以这条是**结构性预留的洞而非今天可达的路径**。
8. **「Azure 的 `/openai/deployments/{deployment}/responses` 是另一条独立路径，可能不受影响」** —— 不成立。`table.py:47-51` 把它登记为同一个 `WireFormat.OPENAI_RESPONSES`，`inbound.py:41-58` 只额外改写 `model`。同一个洞。

## 9. 阻塞与未完成项

**Bash 在调查后半程被 worktree 隔离守卫拦死。** 具体现象：完成第 7 节那次运行之后，任何 Bash 调用（包括 `echo probe`、`cd <worktree> && pwd`）都返回

> This session is isolated in the worktree /home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate, but this command's working directory resolved to the shared checkout (/home/xp/src/ghc-api-proxy-py). Refusing to run it there.

随后 `Write` 到主工作树 `.dev/` 也被同一守卫拒绝（「Edit the worktree copy of this file instead」）。而 `.dev/` 只存在于主工作树根，隔离 worktree 里没有副本，该提示无法执行。我的派活提示词明确说「工作目录 /home/xp/src/ghc-api-proxy-py，不要进 worktree」，与守卫要求直接冲突，所以我没有自行 `EnterWorktree`，也没有在 worktree 里新建一个 `.dev/` 影子目录。`Read` 不受影响，本报告的全部读码都在主工作树上完成。

因此未完成：

1. **本报告未能落到预期路径**，临时落在 `/tmp/repro_issue1/`。请主会话 `cp` 到文件头写明的位置。
2. **第 6 条缺实测**（脚本已写好在 `/tmp/repro_issue1/test_q6.py`，用 cassette 驱动，一条命令就能跑）。
3. **锚定提交哈希未取。**
4. **第 8 节第 7 条（Chat Completions 腿）未验证**，只有读码推断。

给主会话的建议：

- **修复点建议放在 `driver.py:191` 而不是 framer。** 让 `ResponsesFramer` 学会写 `server_tool_use` 是把一个 Anthropic 概念硬塞进 Responses 协议（Responses 那边对应的是 `web_search_call`，语义不对等，且 `web_search_tool_result_error` 在那边没有对应形态）。更合的形状是在合成之前按 `route.inbound_format` 分派——正如 `hand_over.py:238` 已经在做的。至于非 Anthropic 腿上该合成什么（Responses 形态的失败回复？还是干脆放行给上游？还是 400？），那是**产品行为裁决，归用户**，我不在这里替他定。
- **两条修复方向互斥，别同时做。** 一条是「按 inbound 格式分派合成」（保留拦截），另一条是采纳 `hosted_web_search.py:29` 注释所描述的「原生 Responses 客户端不拦」（放行给上游）。后者会让第 3 节与 issue #1 一起消失，但也放弃了对直连客户端的能力把关。
- **非流式那一半（第 3 节）必须与流式一起修**，否则 issue #1 关闭之后同一个 bug 仍然活着，而且更难发现。
- 补测的最小形状与脚本见第 5、7 节。
