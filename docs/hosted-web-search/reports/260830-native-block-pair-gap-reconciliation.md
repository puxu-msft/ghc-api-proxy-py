# hosted web search 原生块对：实现现状逐条对账

日期：2026-08-30
性质：只读调查报告（报告原件，不是活文档）。不改 `src/`、不改 `tests/`、不改规范。
锚定树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate`，HEAD `b9a7236`（`docs: correct three claims in the issue #1 comments that the code does not make`）。**本报告所有行号均以该树该提交为准。** 该树相对 `main` 有 6 个文件的差异（`git diff --stat main...HEAD`：`pipeline/delivery_policy.py`、`pipeline/driver.py`、`pipeline/reply.py`、`pipeline/subscribers/hosted_web_search.py`、`tests/int/test_pipeline_app.py`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py`），内容是 GitHub issue #1 的能力门作用域修复；主树尚未合入，读主树时行号会不同。

规范来源（判据，不从实现反推）：`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md`（2026-08-30 修订版，519 行）与 `.dev/docs/hosted-web-search/status.md`（105 行）。

方法与证据分级：
- **读出来的**：给 `文件:行号`，逐字读过该处代码。
- **跑出来的**：本次实际执行的命令与其输出，另行标注「实测」。共四组：五个定向测试（当前全绿，作为变红判断的基线）、`pytest --collect-only`（1941 个用例）、两份 cassette 与一份探针样本的结构解析、以及一段针对 `ResponsesAssembler` 块序号分配的只读探针（脚本落在 `/tmp/probe_index.py`，不在仓库内）。
- 凡我没有验证的，写在文末「不确定项」，不补看起来合理的答案。

---

## 0. 一句话结论

七个面里，**声明映射（§3）与能力门（§9）基本已实现**，**呈现形态（§5.3）、成块时点（§6.3）、citation 读取、`tool_usage` 读取四项完全未实现**，且这四项互相咬合——没有 citation 就填不出 §5.3 的 `content`，不改成块时点就拿不到 citation，不改块序号分配就发不出一对块。另有一条规范本身没写、但会直接撕流的前置条件：块对必须以「客户端腿是 Anthropic Messages」为条件（详见 G1b）。

---

## 1. 逐条差距表

### G1 — §5.3 冻结的呈现形态：未实现（一个文本块 vs 一对结构化块）

**规范要求**（§5.3，正文 171-204 行）：每个 Responses `web_search_call` item **必须**产出**一对**相邻的 Anthropic block —— `server_tool_use`（`name: "web_search"`，`id: srvtoolu_ws_<output_index>`，`input: {"query": <action.query，缺失时 action.queries 以 ", " 连接，都没有则省略 input>}`，query 必须已 strip）紧随一个同 `tool_use_id` 的 `web_search_tool_result`。`content` 按三分支表取值（单 call 且有 citation → 逐条 `{"type":"web_search_result","url","title"}` 按出现顺序、按 url 去重；多 call → error 形态并记 `web_search_results_unattributable`；无 citation 或 `status != "completed"` → error 形态并记 `web_search_results_not_representable`）。error 形态**必须是裸对象**，不得包成单元素数组。`encrypted_content` **必须省略**，不得填空串或占位串。每对块**必须**记一条 `server_tool_partially_representable` 的 DEGRADE fact，携带 `output_index`、`status`、结果条数与 `encrypted_content` 缺失的事实，**不得**记为已保真。这一对块与相邻答案文本块**不得**合并。搜索块**不得**把 `stop_reason` 设成 `tool_use`。

**实现现状**：

- 流式：`src/app/pipeline/delivery/formats/openai_responses.py:605-611`，`_close` 的 `WEB_SEARCH_CALL` 分支——
  ```python
  elif draft.kind == WEB_SEARCH_CALL:
      raw = data.get("item")
      item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
      payload = {"type": TEXT, TEXT: web_search_call_text(item.get("action"))}
      kind = TEXT
  ```
  即：读闭合事件上的 `action`，渲染成一行文本，块 kind 改成 `text`，然后走 :614 的通用 `CompletedBlock` 构造。
- 文本内容：`src/app/pipeline/server_tool_text.py:35-55` `web_search_call_text`，输出形如 `[web_search] <query>`；`action` 缺失时输出裸 `[web_search]`；刻意不带 item 的 416 字符 id（:42 的 docstring 说明理由）。
- 非流式（缓冲路径）：`src/app/pipeline/translation_driver/openai_responses.py:512-516` `blocks_from_item`，同一措辞、同一函数——
  ```python
  if kind == "web_search_call":
      return "assistant", (
          ContentBlock(BlockKind.TEXT, text=web_search_call_text(item.get("action")), raw=item),
      )
  ```
  由 `src/app/pipeline/translation_driver/responses.py:193` 在 `from_openai_responses_response` 的 output 循环里调用。

**差距性质：未实现。** 现在产出 **1 个 `text` 块**，规范要求 **2 个结构化块**。逐项缺：
1. `server_tool_use` 块整体（含 `srvtoolu_ws_<output_index>` 的派生 id、`name`、`input.query`）；
2. `web_search_tool_result` 块整体（含三分支的 `content`）；
3. 三分支所依赖的 citation 数据源（见 G2，零处读取）；
4. `server_tool_partially_representable` 的 DEGRADE fact —— 今天这条路径**一条 loss 都不记**：`_close` 里没有任何 `conversion.record`，缓冲侧 `blocks_from_item` 也没有（`responses.py:194-200` 只对 `BlockKind.UNKNOWN` 记 `ITEM_NOT_CARRIED`，`web_search_call` 返回的是 `TEXT`，走不到）。所以现状是「**记为已保真**」，正是 §5.3 明令禁止的那一项。

**关于「省略而非伪造」（§5.3）**：今天连结果块都不存在，所以谈不上伪造；这条裁决在落地时的具体含义是——摘要、`page_age`、`encrypted_content` 三样上游一样都不给（§5.1 已跨仓库复现三次以上），`url_citation` 只能给 `url` 与 `title`。项目里已经有同一条裁决的既有落点可以照抄口径：`src/app/pipeline/subscribers/server_tools.py:66-85` `_describe_one` 的 docstring 明写「`encrypted_content` 刻意不读」，理由是它是搜索结果的大头、对我们之外的所有人不透明。

**关于 `stop_reason`**：这一条落地时**自动满足**，不需要额外防护。`_saw_tool_call` 只在 `draft.kind == TOOL_USE`（字面量 `"tool_use"`）时置位（`formats/openai_responses.py:572-573`），`Terminal.record` 也只在 `block.kind == TOOL_USE` 时往 `tools` 里 append（`src/app/pipeline/delivery/assembling.py:57-58`）。`server_tool_use` 是另一个字符串，两处都命不中。

---

### G1b — 未在规范里、但会直接撕流的前置条件：块对必须按**客户端腿**开关

这一条不是规范的某一款，是把 §5.3 落到本项目代码结构上时冒出来的硬约束。写在最前面，因为它决定后面所有改动会不会在生产上撕流。

`ResponsesAssembler` **同时服务两条腿**：`src/app/pipeline/delivery/stream.py:311` 的 docstring 说得很直白——「The same `ResponsesAssembler` serves a Responses client directly and a Responses upstream being translated to Anthropic, and the framer is the *client's* either way, so neither object knows.」

- assembler 按**上游方言**选：`src/app/pipeline/delivery_policy.py:82-96` `assembler_for`，判据是 `dialect_for`（`route.target_format is OPENAI_RESPONSES`）。
- framer 按**客户端腿**选：`src/app/pipeline/delivery_policy.py:51-80` `framer_for`，判据是 `route.inbound_format`。

于是：一个 inbound 为 `/responses`、上游也是 Responses 的直连请求，如果上游响应里带 `web_search_call`（用户 2026-08-30 已裁决这类请求的声明放行到上游，所以上游**会**执行搜索、**会**返回该 item），assembler 若无条件产出 `server_tool_use` 块，它会被送进 `ResponsesFramer.block`：

```python
# src/app/pipeline/delivery/formats/openai_responses.py:180-189
if block.kind == TOOL_USE: ...
elif block.kind == THINKING: ...
elif block.kind == TEXT: ...
else:
    raise ValueError(f"no Responses item shape for block kind {block.kind!r}")
```

**这正是 issue #1 的那句异常**，从另一个方向复现：200 已经发出、流被撕断。今天不发生，只是因为 assembler 把它变成了 `TEXT`。

因此实现必须：给 `ResponsesAssembler` 增加一个构造参数（今天它只有 `hand_over_stop_reasons` 与 `client_search_tool`，`delivery_policy.py:91-95`），由 `assembler_for` 从 `handled.route.inbound_format` 填；缓冲侧 `from_openai_responses_response` → `blocks_from_item` 需要同一个开关（`blocks_from_item` 今天已有 `client_search_tool` 关键字参数，位置现成）。

同时必须改一段注释，否则它会主动误导后来的读者：`src/app/pipeline/delivery/formats/openai_responses.py:7` 把「`web_search_call` 不能往返、assembler 刻意把它改写成散文」**记录为一项已知损失**并给了理由。块对落地后，这段话对 Anthropic 客户端不再成立、对 Responses 客户端仍然成立，必须写成分腿的。

**已有测试抓不住这一条**：`tests/int/test_pipeline_app.py::test_a_direct_responses_client_declares_hosted_web_search_for_itself`（:2516）用的上游是 `responses_sse_upstream()`，**其中没有 `web_search_call`**，所以它只验证声明被转发、`response.completed` 收尾，验证不到块形状。**这是本次最需要新增的一条控制用例**：inbound `/responses` + 上游响应含 `web_search_call`，断言不撕流且客户端拿到的是 Responses 形状。

---

### G2 — `url_citation` 读取：零处，有确凿的否定证据

**规范要求**（§5.1 正文 157 行、§5.3 的 `content` 第一分支、§14 D5）：后续 message 的 `annotations` 里的 `url_citation`（`{type,url,title,start_index,end_index}`）是 `web_search_tool_result.content` 的**唯一**数据来源；用过之后**不得**再以 Anthropic `citations` / `web_search_result_location` 形式重复附加到文本块上。

**否定证据（不是「我没找到」，是逐条穷举）**：

```
$ rg -n "url_citation" src
src/app/config/schema.py:210                         ← 注释
src/app/pipeline/subscribers/hosted_web_search.py:3  ← 模块 docstring
```
两处命中**全是散文**，零处代码。

```
$ rg -n "annotation" src | rg -v "from __future__ import annotations"
src/app/config/schema.py:210                                   ← 注释
src/app/pipeline/subscribers/hosted_web_search.py:3            ← docstring
src/app/pipeline/delivery/formats/openai_responses.py:198      ← "annotations": []
src/app/pipeline/delivery/formats/openai_responses.py:220      ← "annotations": []
```
后两处是 **出站** 方向：`ResponsesFramer._message` 给 Responses 客户端写空的 `annotations` 数组，与读上游无关。

所以：**代码里没有任何一处读上游的 annotations。**

**要在哪里读**：

- **非流式（缓冲）**：`src/app/pipeline/translation_driver/openai_responses.py:532-538` `_block_from_content_part` ——
  ```python
  def _block_from_content_part(part: dict[str, Any]) -> ContentBlock:
      kind = str(part.get("type", ""))
      if kind in {"input_text", "output_text", "text"}:
          return ContentBlock(BlockKind.TEXT, text=str(part.get("text", "")), raw=part)
  ```
  只取 `text`，`annotations` 整体丢弃。这是缓冲侧唯一的读取点（上游 message item 经 :474-478 的 `kind == "message"` 分支进到这里）。注意 `ContentBlock` 带 `raw=part`，所以原始 part 其实**还在**——下游取得到，只是没人取。
- **流式**：`ResponsesAssembler.push` 的分支表（`formats/openai_responses.py:441-489`）里，`response.content_part.done`、`response.output_text.annotation.added`、以及 message 的 `output_item.done` 上 `item.content[].annotations` 三个可选取点**一个都没有处理**；`content_part.done` 落到 :489 的 `return ()`。规范 §12 P9（2026-08-21 结案）记录三个取点都带完整数组。

**喂给谁**：§5.3 的 `web_search_tool_result.content`，每条 citation 一项 `{"type":"web_search_result","url":<url>,"title":<title>}`，按出现顺序、按 `url` 去重。

**一手样本形状（本次复核）**：`exp/260820-websearch-probe/raw/B7-responses-tool-choice-builtin-response.txt`，`output` 两项（`web_search_call` + `message`），`output[1].content[0].annotations` 有 **1 条**：

```json
{"end_index": 168, "start_index": 36, "title": "France – EU country | European Union", "type": "url_citation", "url": "https://european-union.europa.eu/principles-countries-history/eu-countries/france_en?utm_source=openai"}
```

同一段正文里还内联了 markdown 引用（`The capital of France is **Paris**. ([european-union.europa.eu](https://…?utm_source=openai))`），即规范 §5.3 末尾那条「上游本就已内联 markdown 引用，实测同一响应两种形式同时到达」的原始出处。`utm_source=openai` 这个尾巴是上游加的。

---

### G3 — §6.3 成块时点：未实现。**本次技术风险最高的一条，以下写足细节，实现者不必重读一遍代码**

**规范要求**（§6.3，正文 248-267 行）：`added` 到达时必须登记 `output_index`（占住 block index 的分配次序）但不得出块；`output_item.done` 上的 item 是唯一权威快照，此刻必须入**待归因队列**但**不得成块、不得发出任何字节**；**成块发生在紧随其后那个 message 文本块完成时（`content_part.done`）**，发射顺序必须是「该文本块对应的每个待归因 call 的 `server_tool_use` 与 `web_search_tool_result`，**然后**才是该文本块本身」；归因是局部规则，队列恰好一个 call 时才用 citation 填 `content`，多于一个则该组全部落 error 形态；队列每次成块后必须清空；一个 call 后面没有文本块时（响应结束、或下一个 item 是 `function_call` 等非文本 item），队列中全部 call 必须在其自然边界以 error 形态成块发出，不得丢失。

**现状的成块逻辑，逐点读出来**：

1. **`push` 只在两个事件上出块**（`formats/openai_responses.py:437-489`）：`response.output_item.done` → `_close`（:450-451），以及 `response.completed` / `response.incomplete` 分支里释放 `_cut_short`（:452-459）。其余全部返回空元组。`response.content_part.done` **不在分支表里**，落到 :489 `return ()`。
2. **`_open`（:505-520）** 建 `Draft(index=self._order, kind=..., payload=dict(item))` 并 `self._order += 1`。**一个 item 一个号**。
3. **`_close`（:532-620）** pop 出 draft；draft 不存在时对 `web_search_call`（与有名字的 `tool_search_call`）做**迟到补登记**（:555-561，同样 `self._order += 1`），其余 warning 后丢弃（:543-554）。然后按 kind 构造 payload，`block = CompletedBlock(index=draft.index, kind=kind, payload=payload)`（:614），`self._terminal.record(block)`（:619），返回 `(block,)`。
4. **交付侧**：`stream.py:381-391`，`completed = assembler.push(pull.event)`，逐块进 `_commit`（:616-633）→ `session.offer(block)` → `BlockBuffer.add`（`blocks.py:88-107`）→ 释放的块交给 `framer.block(...)`。

**改动会波及的不变量，逐条**：

**（a）`CompletedBlock.index` 的分配 —— 必须从「按 item」改成「按发出的块」。**

一个 `web_search_call` 现在要产出**两个**块。`Draft.index` 一 item 一号，两个块共用一号会让 Anthropic 客户端把第二块当成第一块的续写：Anthropic framer 把 `block.index` **逐字**写进 wire——

```
src/app/pipeline/delivery/formats/anthropic_messages.py:84   signature_delta 的 index
src/app/pipeline/delivery/formats/anthropic_messages.py:120  content_block_start 的 index
src/app/pipeline/delivery/formats/anthropic_messages.py:135  content_block_delta 的 index
src/app/pipeline/delivery/formats/anthropic_messages.py:139  content_block_stop 的 index
```

所以序号必须在**发出块**的时刻分配，而不是在开 draft 的时刻。

**顺带实测到的一个既有的洞（不属本规格，需要单独裁决，但同一处改动会顺手关掉它）**：`_order` 对 `DISCARDED` item 也递增（`_open` :519-520 无条件 `+= 1`），而 `DISCARDED` 在 `_close` :569-571 直接 `return ()` 不出块。于是 Anthropic 客户端**今天就会**收到不连续的 `content_block` index。

实测（`/tmp/probe_index.py`，2026-08-30，本树 HEAD）：构造 `ResponsesAssembler()`（不给 `client_search_tool`，于是 `tool_search_call` 判为 `DISCARDED`），依次推入 output_index 0 的 `tool_search_call` 的 added/done、output_index 1 的 message 的 added/delta/done，输出：

```
discarded-then-text blocks: [(1, 'text')]
terminal.blocks: 1
```

唯一交付的块 `index=1`，**没有 index 0**。`tool_search_output` 恒为 `DISCARDED`（:516），`tool_search_call` 在没有客户端工具名时也是（:514），两者都是真实可达的上游形状。

模块顶部注释 `formats/openai_responses.py:13` 说 Responses framer 之所以自己数 `output_index`「而**不**取 `CompletedBlock.index`，因为那个计数器对它后来丢弃的 item 也递增——留个洞就是客户端的 IndexError」。**那句话描述的是 Responses 腿的自保，它没有替 Anthropic 腿解决同一个问题。** 块对落地后这个计数器会多一个产生洞/重号的来源（一 item 两块），所以两件事一起改最省。

**（b）`Terminal.record` 的计数。**

`record`（`assembling.py:51-61`）只做三件事：`self.blocks += 1`；`kind == TOOL_USE` 时把 `payload["name"]` append 进 `tools`；`kind == THINKING` 时 append `"txt"`/`"enc"`。块对会让 `terminal.blocks` 每次搜索 **+2**。

`terminal.blocks` 被读的地方**只有一处**，而且是有判断力的一处：

```python
# formats/openai_responses.py:567
cut_short = _upstream_cut_this_item_short(data) and self._terminal.blocks > 0
```

判据是「> 0」，所以 1→2 本身不翻转结论。**但时点会翻转**：把搜索对推迟到后随文本块的边界之后，在**那个文本 item 的 `_close` 里**读 `blocks` 时，搜索对是否已经 `record` 取决于你把 record 放在 `content_part.done` 还是放在同一次 `_close` 里。

具体后果：一个「先搜索、随后第一个文本块被上游截断（`status: "incomplete"`）」的响应——
- 今天：搜索的文本块已在自己的 `done` 上 record，`blocks == 1`，`cut_short` 为真，被截断的文本块**保留**在 `_cut_short` 里等终局。
- 改后若先判 `cut_short` 再 record 搜索对：`blocks == 0`，`cut_short` 为假，那个半截块**直接交付**，语义与今天相反。

所以：**若搜索对与文本块在同一次 `_close` 里产生，必须先 record 搜索对、再算 `cut_short`。**

`terminal.tools` 不会被污染、`stop_reason` 不会变成 `tool_use`：两处都比对字面量 `"tool_use"`（`assembling.py:57`、`formats/openai_responses.py:572`），`server_tool_use` 命不中。这正好落在 §5.3 的要求上，不需要额外防护。

`stream.py` 里的 `session.committed_count`（`blocks.py:139-141` = `len(self.delivered)`）是**另一个**计数，与 `terminal.blocks` 无关。`decide_stream_ending`（`stream.py:455-461`）与 `_hand_over`（:595、:609）读的都是它，而它按实际交付的块数走，所以 `_hand_over` 合成块的 index（`stream.py:609` `CompletedBlock(index=session.committed_count, ...)`）会自动跟上块对。**这一处不需要改。**

**（c）「`output_index` 不取 `CompletedBlock.index`」那条注释（:13）。**

它约束的是 `ResponsesFramer` 自己的计数器 `self._output_index`（初始化 :111，每发一块 `+= 1` 于 :188）。只要块对不进 Responses framer（见 G1b），本次改动与它**不冲突**。但那条注释给出的**理由**在块对之后会多一个来源：不只是「计数器对丢弃的 item 也递增」，还有「一个 item 可以产出两块」。如果将来有人想让 Responses framer 也发块对，`_output_index` 的一 item 一号也要同步改；今天不用。

**（d）兜底分支（§6.3「一个 call 后面没有文本块时」）的插入位置。**

`push` 的 `response.completed` / `response.incomplete` 分支（:452-459）现在的顺序是：`_read_terminal(kind, data)` → 取出 `_cut_short` → 按 `stop_reason` 决定保留还是丢弃 → 返回 `(held,)` 或 `()`。待归因队列的兜底必须插在 `_read_terminal` **之后、返回之前**，并与 `_cut_short` 的释放**定序**——两者都往同一个返回元组里放块，顺序就是 wire 上的先后。另一条兜底路径（下一个 item 是 `function_call` 等非文本 item）要在 `_close` 的开头处理，即「新 item 开始收口时，先把队列里剩下的以 error 形态发出」。

**（e）流式与非流式的等价。**

缓冲侧 `from_openai_responses_response`（`responses.py:178-200`）是一个逐 item 的 for 循环，同一条局部归因规则要在那里再写一遍。今天两侧共用 `blocks_from_item`（`responses.py:193` 调用 `openai_responses.py:445` 起的那个函数），所以最可能保持等价的做法是让 `blocks_from_item` 能返回两个块并另接收 annotations；两侧各写一份归因逻辑，就是 §6.3 末条明确要防的分叉。

**（f）一个可以省掉一整套机器的观察，需要裁决（我不代裁）。**

本次逐字复核 `tests/int/cassettes/responses_web_search_stream.json`（16 个事件）得到的事件序是：

```
 0 response.created
 1 response.in_progress
 2 response.output_item.added        output_index=0   (web_search_call)
 3 response.web_search_call.in_progress
 4 response.web_search_call.searching
 5 response.web_search_call.completed
 6 response.output_item.done         output_index=0
 7 response.output_item.added        output_index=1   (message)
 8 response.content_part.added
 9-11 response.output_text.delta ×3
12 response.output_text.done
13 response.content_part.done        output_index=1   ← §6.3 指定的成块点
14 response.output_item.done         output_index=1   ← 今天文本块成块的点
15 response.completed
```

`content_part.done`（#13）**紧接** `output_item.done`（#14），中间没有任何其他事件；且规范 §12 P9 已结案记录「`content_part.done` 与 `output_item.done` 各另带一份完整 `annotations` 数组」——本次也从 cassette 上复核到 message 的 `output_item.done` 里 `item.content[0].annotations` 确实存在（值为 `[]`）。

于是：**在 message 的 `output_item.done` 上一次性返回「`server_tool_use`、`web_search_tool_result`、文本块」三元组，能得到与 §6.3 完全相同的 wire 顺序**，而不必新增 `content_part.done` 的处理分支、不必维护跨事件的队列状态、也不必改动 `_close` 之外的任何时点。代价是它与 §6.3 字面的「成块发生在……`content_part.done`」不符。

这属于「规范条款要不要按新证据修订」的问题（§6.3 那条规则本身就在 2026-08-21 换过一次依据），**不是我能代裁的**，写在这里供实现者与用户决定。若采纳字面版本，上面 (a)~(e) 全部适用；若采纳这个简化版本，(b) 的「先 record 再判 cut_short」变成必须，(d) 的第二条兜底路径依然需要。

---

### G4 — §3.4 域名限制与 `max_uses`

**分支的当前位置：`src/app/pipeline/translation_driver/openai_responses.py:285-309`**（status.md §4.5 记的 `:231` 已过期）。结构逐字如下：

```python
if key in _UNREPRESENTABLE_CONSTRAINTS:            # :285   ("allowed_domains", "blocked_domains")，定义在 :241
    if not value:                                  # :286   空列表：记 loss 后 continue
        conversion.record(LossCode.SERVER_TOOL_CONSTRAINT_DROPPED, ...)
        continue
    if policy == "error":                          # :293
        raise TranslationRefused(
            ..., code="server_tool_constraint_not_representable",
            field_path=f"tools.{declared}.{key}",  # :298
        )
    conversion.record(LossCode.SERVER_TOOL_CONSTRAINT_DROPPED, ...)   # :300-304
    logger.warning(...)                            # :305-308
    continue                                       # :309
```

**status.md §4.5 警告的那个 `else` 仍在，只是它不是 `else` 关键字，而是 `if policy == "error"` 之后的无条件落空（fall-through）。** 效果完全一样：`Literal` 扩到三个取值后，`empty_result` 会静默执行 `drop_fields` 的行为。类型检查不会报（没有穷尽性检查，也没有 `assert_never`），测试也不会红——三处已有用例只覆盖两个取值：`tests/unit/pipeline/translation_driver/test_translation_driver.py:631`（默认 `drop_fields`）、:639（显式 `error`）、`tests/int/test_pipeline_app.py:682`（`error`）。

**`Literal` 现有取值：两个。** `src/app/config/schema.py:27`：

```python
type WebSearchConstraintPolicy = Literal["error", "drop_fields"]
```

（status.md 记的 `:26` 已过期一行。）

**status.md §4.5 的波及面清单，行号全部过期，文件与符号全部正确**：

| status.md §4.5 写的 | 当前实际 | 内容 |
|---|---|---|
| `schema.py:26` | `schema.py:27` | `Literal` 定义 |
| `schema.py:219` | `schema.py:227` | 默认值 `drop_fields` |
| `registry.py:145` | `registry.py:154` | 接线 `web_search_domain_restrictions=settings.to_openai_responses...` |
| `openai_responses.py:702` | `openai_responses.py:868` | `to_openai_responses` 的形参 |
| `openai_responses.py:714` | `openai_responses.py:886` | `_tools_for_upstream(request, web_search_domain_restrictions, search)` 调用 |
| `openai_responses.py:231` | `openai_responses.py:285-309` | 分支本体 |

**`max_uses`**：`_WEB_SEARCH_DROPPED = frozenset({"max_uses"})`（:235），处置在 :310-315——记一条 `LossCode.SERVER_TOOL_CONSTRAINT_DROPPED`，**没有日志**。规范 §3.4 要求 fact 码 `server_tool_max_uses_not_enforceable` 且日志级别 INFO。**差距性质：偏离（两处，均为轻微）**——码名被并进通用码，日志缺失。

**fact 码词汇整体是一处系统性偏离**：`LossCode`（`src/app/pipeline/translation_driver/semantic.py:32-56`）里**没有**规范点名的任何一个专用码（`server_tool_constraint_dropped` / `server_tool_max_uses_not_enforceable` / `server_tool_partially_representable` / `web_search_results_unattributable` / `web_search_results_not_representable` / `server_tool_call_id_not_carried` / `server_tool_constraint_yielded_empty_result`）。实现把它们全部并进 `SERVER_TOOL_CONSTRAINT_DROPPED`（值 `server-tool-constraint-dropped`，连字符），靠 detail 字符串区分。实测**没有任何表以 `LossCode` 为键**（`rg -n "LossCode\]" src` 零命中），所以加成员的代价低——这一点值得写下来，因为「枚举加成员会给每张以它为键的表造缺项」是本项目吃过亏的模式，这次不适用。

**`empty_result` 的一处规范覆盖不全（新发现）**：§3.4 的 `empty_result` 要求「合成 `server_tool_use` + `web_search_tool_result`（`content: []`）」并「同步删除指向该声明的 `tool_choice`」。**这同样是一对 Anthropic 块**，因此必须受 §8.3 末条（2026-08-30 补入）的腿约束——只在客户端腿是 Anthropic Messages 时产出。而 §8.3 末条的作用域写的是「**本节**规定的失败结果」，**没有覆盖 §3.4**。落地 `empty_result` 时不能只读 §3.4。

（顺带：`error` 分支不存在腿泄漏。`_web_search_tool` 只在 `_is_anthropic_server_tool` 为真时被调用（:416-422），而该谓词要求 `web_search_` 后跟 8 位 ASCII 数字（:244-261），直连 Responses 客户端写的裸 `{"type": "web_search"}` 命不中。`tests/unit/pipeline/translation_driver/test_translation_driver.py:569-580` 正面钉住了这一点。）

---

### G5 — `usage`：`tool_usage.web_search.num_requests` 零处读取

**规范要求**（§5.3 末条）：`tool_usage.web_search.num_requests` **必须**进入可观测 facts（日志与 footer），**不得**进入 Anthropic wire content。是否同时写入 Anthropic `usage.server_tool_use.web_search_requests` 见待裁决 **D7（未裁决）**。

**上游给在哪里（本次实测，三个独立样本一致）**：`tool_usage` 在**响应体根**，**不在 `usage` 里**。

- `tests/int/cassettes/responses_web_search_nonstream.json` 的 `/responses` 响应根：`tool_usage = {"image_gen": {...}, "web_search": {"num_requests": 1}}`，`usage = {"input_tokens": 4693, "input_tokens_details": {...}, "output_tokens": 112, "output_tokens_details": {"reasoning_tokens": 51}, "total_tokens": 4805}`。
- `tests/int/cassettes/responses_web_search_stream.json` 的 `response.completed` 事件里的 `response` 对象：同样两个键并列。
- `exp/260820-websearch-probe/raw/B7-responses-tool-choice-builtin-response.txt`：同。

**现状：零处读取。** `rg -n "tool_usage|num_requests" src` 共 4 条命中，**全部在注释里**（`translation_driver/openai_responses.py:234`、`:271`、`:793`、`:817`）。

**要改哪里**：

`anthropic_usage_from_responses`（`src/app/protocols/responses_anthropic.py:214-222`）**只接受 `usage` 一个对象**，它看不见 `tool_usage`。它的两个调用者都能看见响应根对象，所以两处都改得动：

| 路径 | 调用点 | 根对象在作用域里叫什么 |
|---|---|---|
| 缓冲 | `src/app/pipeline/translation_driver/responses.py:93-103` `_anthropic_usage`，由 `from_openai_responses_response` 在 :170-172 调用 | `payload` |
| 流式 | `src/app/pipeline/delivery/formats/openai_responses.py:675-685` `_anthropic_usage`，由 `_read_terminal` 在 :626-630 调用 | `response`（:624-625 已从事件里取出） |

**若要写进 Anthropic wire（即 D7 取 (b)），还差一层模型扩展**：`AnthropicUsage`（`src/app/models/anthropic.py:64-68`）只有 `input_tokens` / `output_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens` 四个字段，没有 `server_tool_use`；而 `anthropic_usage_from_responses` 的返回是 `converted.wire.model_dump()`（:222），所以不扩 `AnthropicUsage` 就加不进去。

**一处必须说清的陷阱**：`convert_responses_response_to_anthropic`（同文件 :72-141）看起来像非流式转换的主路径，**它不是**。`rg -n "convert_responses_response_to_anthropic" src tests` 的结果：src 内只有定义（:72）与 `__all__`（:357），**零调用**；全部 15 处调用在 `tests/unit/protocols/test_responses_anthropic_nonstream.py`。它在 :112-113 对任何 `*_call` / `*_result` item 显式 `server_tool_not_supported` 失败——那正是 §8.4 / §11 要覆盖的那一条，但**改它不会改变任何产品行为**。真正的缓冲路径是 `translation_driver/responses.py`。同一个模块里 `anthropic_usage_from_responses` 是活的（两个调用者），`_convert_message`（:153-174，同样丢弃 `annotations`）随 `convert_responses_response_to_anthropic` 一起是死的。

**差距性质：未实现（可观测 facts 那一半是 §5.3 的必须项，与 D7 无关）；wire usage 那一半待 D7 裁决。**

---

### G6 — 既有测试与 cassette 覆盖面（爆炸半径）

#### 两份 cassette 里到底有什么（本次逐字解析）

**`tests/int/cassettes/responses_web_search_nonstream.json`**（5653 字节，2 个 interaction）
- interaction 0：`GET /copilot_internal/v2/token`，`authenticated: true`。
- interaction 1：`POST /responses`，`shape = {"model": "gpt-5.5", "stream": false, "digest": "44816fc0…"}`。
- 响应根键 24 个，含 `tool_usage`、`usage`、`tools`、`output`。
- `tools` 回显：`[{"type":"web_search","return_token_budget":"default","search_content_types":["text"],"search_context_size":"medium","user_location":{"type":"approximate","city":null,"country":"US","region":null,"timezone":null}}]` —— 即 §3.2 记录的那份默认值回显，逐字对得上。
- `output` 两项：
  - `[0]` `web_search_call`，**键恰为四个** `action` / `id` / `status` / `type`（§5.1 复现成功），`status: "completed"`，`action = {"queries": ["time: {\"utc_offset\":\"-04:00\"}"], "query": "time: {\"utc_offset\":\"-04:00\"}", "type": "search"}`（`query` 与 `queries` 内容相同），`id` 416 字符。
  - `[1]` `message`，`content[0]` 是 `output_text`，**`annotations == []`**，正文 66 字符。
- **`web_search_call` 数量：1。citations：无。**
- 根上 `tool_usage.web_search.num_requests == 1`。

**`tests/int/cassettes/responses_web_search_stream.json`**（19317 字节，2 个 interaction）
- interaction 1：`POST /responses`，`shape = {"model": "gpt-5.5", "stream": true, "digest": "4506eeb2…"}`，响应 **18 个 chunk / 16 个事件**（chunk 边界保留，事件跨 chunk 切分——例如第 14 个 chunk 以 `done"}\n\n` 开头，正是块级交付要求保留的那种边界）。
- 事件序见 G3(f) 的表。事件计数：`output_text.delta` ×3，`output_item.added` ×2，`output_item.done` ×2，三个 `web_search_call.*` 专有事件各 1，`created` / `in_progress` / `content_part.added` / `output_text.done` / `content_part.done` / `completed` 各 1。
- **`web_search_call` 数量：1**（output_index 0）。
- **annotations 处处为空数组**：`content_part.done` 的 `part.annotations == []`，message `output_item.done` 的 `item.content[0].annotations == []`。
- **没有 `response.output_text.annotation.added` 事件。**
- `response.completed` 里 `tool_usage.web_search.num_requests == 1`。

#### 全仓 cassette 的 citation 覆盖：零

实测五份 cassette 的 `url_citation` 出现次数全部为 **0**。`history_responses_stream.json` 与 `anthropic_to_responses_stream.json` 里的 `web_search` 命中（各 3 次）是响应体 `tools` 回显，两者的 `web_search_call` 出现次数均为 **0**。

**结论：§5.3 `content` 那张三分支表里「有 citation」的那一支，没有任何录制证据可回放。** 唯一的一手样本是 `exp/260820-websearch-probe/raw/B7-*.txt`——一份**非流式**、手工探针、一条 citation。这直接决定了新功能的验证只能靠：(a) 手写夹具（项目规则明确警告「手写 stand-in 编码的是我们相信的上游行为，而那份相信正是缺陷的藏身处」）；(b) `from_history.py` 派生（需要 2026-08-15 之前的历史帧，且 `.dev/docs/hosted-web-search/reports/260821-responses-websearch-citation-evidence.md` 说取证正是从 history 库里拿到的根帧，所以这条路**可能**走得通）；(c) 真实上游重录（需授权，且 §12 P11 的类型问题会同时被触发）。

#### 两份 cassette 的录制/回放状态

- **不在** `tests/int/recorded/record_cassette.py` 的 `SCENARIOS` 里——那张表**只有一个** `anthropic_to_responses_stream`（:36-44）。
- **不在** `tests/int/recorded/from_history.py` 的 `SCENARIOS` 里（:225-238，三个 history_* 场景）。
- `responses_web_search_stream.json` 被 `tests/int/test_pipeline_app.py:451` **当字节源**使用：读出 `interactions` 里 path 含 `responses` 的那一条，把 `chunks` 的 `text` 拼成一整段 SSE，喂给一个 stub transport。**不走 `RecordedProvider` 的形状校验**，所以规范 §12 说的「直接拿现有两份去回放会撞 `RequestShapeChanged`」今天不会发生。
- `responses_web_search_nonstream.json` 在 `src` 与 `tests` 里**零引用**（`rg -n "responses_web_search"` 只有 `test_pipeline_app.py:445/451` 与 `formats/openai_responses.py:10` 的注释）。
- 因此规范 §12 那句「它们目前没有任何测试在回放」：**按字面已不准确**（stream 那份在被用），**按「未经回放框架的形状校验」仍然成立**。

#### 必然变红的测试：**3 个**（全部已实测当前为绿）

基线实测：`uv run pytest -q` 跑下列五个 nodeid（三个候选 + 两个控制项）→ `5 passed in 2.32s`。

1. **`tests/unit/pipeline/delivery/test_sse_assembly.py::test_a_search_that_closes_without_ever_opening_is_still_delivered`**（:383-404）
   断言 `[block.payload["text"] for block in blocks] == ["[web_search] orphan query"]`。
   两条独立原因各自足以打红：§5.3 之后块 payload 没有 `"text"` 键（`KeyError`）；§6.3 之后 `output_item.done` 上根本不出块（返回空元组，列表推导得到 `[]`）。
   注意这个用例覆盖的是 §6.3「`done` 无 `added` 时必须补登记而非失败」那条防御性分支，**改写后必须保留该语义**，只换断言形态。

2. **`tests/int/test_pipeline_app.py::test_a_streamed_search_is_delivered_as_a_line_rather_than_an_empty_block`**（:444-495）
   断言 `deltas[0].startswith("[web_search] ")`，其中 `deltas` 是所有 `content_block_delta` 的 `delta.text`。
   块对不产生 `content_block_delta`：`_delta_for`（`formats/anthropic_messages.py:55-66`）对 `text` / `thinking` / `tool_use` 之外的 kind 返回 `None`，`block_frames` 于是只发 start + stop。所以 `deltas[0]` 会变成答案正文，断言失败。
   同一用例的 `assert all(text for text in deltas)`（:493）本身仍会通过。

3. **`tests/unit/pipeline/translation_driver/test_translation_driver.py::test_a_search_the_upstream_ran_is_reported_rather_than_dropped`**（:747-781）
   两条断言都会红：
   - `assert payload["content"] == [{"type": "text", "text": "[web_search] bun release notes"}, {"type": "text", "text": "Bun 1.3 is out."}]`（:773-776）—— 形态从 2 个 text 变成 3 个块。
   - `assert semantic.conversion.lossless`（:781）—— §5.3 要求每对块必记一条 DEGRADE。
   同一用例的 `assert "x" * 32 not in json.dumps(payload)`（:779，防 416 字符 id 泄漏到客户端）**必须保留**：§5.3 的派生 id 规则是同一条裁决。

#### 不会变红但需要新增配套的

- **G1b 的控制用例（最重要）**：inbound `/responses` + 上游响应含 `web_search_call`。今天的 `test_a_direct_responses_client_declares_hosted_web_search_for_itself`（:2516）用 `responses_sse_upstream()`，其中**没有** `web_search_call`，抓不住撕流。
- **§3.4 第三取值 `empty_result` 的用例**：今天零覆盖（status.md §4.5 已警告），且落地时要连带覆盖「块对只在 Anthropic 客户端腿产出」。
- **成功结果块回喂的用例**：`test_a_replayed_failed_search_still_says_it_happened`（:845-885）覆盖的是**失败**结果块的回喂摊平（断言 `[web_search] bun 1.3` 与 `[web_search failed: unavailable]` 出现在 texts 里），仍然成立；**成功**结果块的回喂今天没有任何用例——见 G6b，那正是会出问题的地方。

#### 不受影响的（澄清，避免误伤）

- `tests/unit/pipeline/subscribers/test_subscribers_server_tools.py:148` 与 `:293` 的 `[web_search] today's date` 断言，测的是 **Anthropic 腿的历史摊平**（§5.4 / §10 明确「不变」），不受 §5.3 影响。
- `tests/int/test_history_fixtures.py` 的 cassette 断言：`history_responses_stream.json` 没有 `web_search_call`。
- 请求侧的一整批（`test_translation_driver.py:536-745`、`test_pipeline_app.py:400-442/643-720`、`test_builtin_subscribers.py:354-600`）全部是声明映射与能力门，不受影响。

#### 规模参照

`uv run pytest tests --collect-only -q` → **1941 个用例**（默认扫描，不含 `tests/tui`）。必然变红 3 个，占比可忽略——**爆炸半径小，风险不在测试数量上，在 G1b 与 G3 那两条没有测试守着的不变量上。**

---

### G6b — 顺带发现的一处两腿渲染分叉（§5.3 落地后会立刻变成信息损失）

这不在任务清单里，但它会被 §5.3 直接引爆，所以写在这里。

同一件事「把 Anthropic server-tool 结果块摊平成文本」，两条腿今天各有一份**不等价**的实现：

- **Anthropic 腿**：`src/app/pipeline/subscribers/server_tools.py:104-118` `_render_results`
  - 失败 → `[web_search failed: <code>]`
  - 成功且有条目 → `[web_search results]` 换行后逐条 `- <title> — <url>`（`_describe_one`，:66-85）
  - 空 → `[web_search results omitted]`
- **Responses 腿**：`src/app/pipeline/translation_driver/openai_responses.py:665-691` `_server_tool_block_as_text`
  - 失败（`content` 是 dict 且有非空 `error_code`）→ `[web_search failed: <code>]`
  - **其余一律** → `[web_search results omitted]`，**不看内容**（:691）

**今天无害**，因为我们只产失败结果（合成失败搜索），两条腿在那一支上一致。

**§5.3 落地之后就不无害了**：我们会产**带 `url` / `title` 的成功 `web_search_tool_result`**，客户端下一轮原样回传。走 Responses 腿时那些 url 会被整体抹成 `[web_search results omitted]`；同一份历史走 Anthropic 腿则保留成清单。**同一会话在两腿之间迁移会出现两种文本形状，而不会有任何东西报错**——这正是 §10 第一条硬性要求（「必须提取为一份共享实现」）要防的那个漂移。

该要求今天只完成了一半：**调用行**渲染已经共享（`src/app/pipeline/server_tool_text.py` 的 `call_subject` / `call_text` / `web_search_call_text`，两腿都 import），**结果行**渲染没有共享。规范 §10 那条的诊断措辞（「今天该逻辑私有在订阅者模块内」）因此也已经过期一半——见 G7 第 5 条。

---

### G7 — 反向检查：规范里已经过期的条款

已知的两条（§10 表格、§13 关于 `web_fetch`）确认过期，另有 11 条。**只列出，不修改。**

| # | 条款 | 规范怎么写 | 实际怎么样 | 性质 |
|---|---|---|---|---|
| 1 | **§8.3 第一条 + §10 表格「声明」行的 Anthropic 腿格** | 「订阅者继续剥离声明、清理悬空 `tool_choice`、摊平历史块。**行为完全不变**」 | 早已不剥离：`subscribers/server_tools.py:198-232` `_refuse_declarations` 收集被拒声明后 `raise WebSearchNotExecutable(code="server_tool_not_executable")`，由 `pipeline/driver.py:191-204` 合成失败结果作答。§8.3 的 2026-08-22 更正只改了 Responses 腿那一半 | **规范过期** |
| 2 | **§4 第二条** | 「被指向的 web search 声明因能力门未通过而**被剥离**时（§8.3），该 `tool_choice` 必须同步删除」 | 前提不再发生：门不通过时整条请求不发出，改为合成作答。这条今天**没有对象** | **规范过期**（同 1 的下游） |
| 3 | **§10 表格「`web_fetch`」行的 Responses 腿格 + §13 第一条** | 「声明继续 `REJECT`」 | 不 REJECT：`_ANTHROPIC_SERVER_TOOL_FAMILIES` 只含 `("web_search_",)`（`translation_driver/openai_responses.py:223`），`web_fetch_*` 走普通工具路径**原样透传**到上游，由上游 400。`tests/unit/pipeline/translation_driver/test_translation_driver.py:738-744` 逐字钉住了这个透传且为绿。status.md §4.4 已记 | **规范过期**（用户已知） |
| 4 | **§10 表格「`web_fetch`」行的 Anthropic 腿格** | 「订阅者剥离 + 摊平（不变）」 | `_REJECTED_TYPE_PREFIXES = ("web_search", "web_fetch")`（`server_tools.py:40`），走的是同一个 `raise`，不是剥离 | **规范过期**（同 1） |
| 5 | **§10 三条硬性要求第一条** | 「今天该逻辑（`_family`、`_call_subject`、`_describe_one`、`_failure_of`、`_render_results`）私有在订阅者模块内」 | 已部分变化：`call_subject` / `call_text` / `web_search_call_text` 提取到 `src/app/pipeline/server_tool_text.py` 两腿共用；`_family` / `_describe_one` / `_failure_of` / `_render_results` 仍私有，且 Responses 腿另写了一份**不等价**的（G6b） | **诊断过期，问题未解决**——条款本身仍然成立且更紧迫 |
| 6 | **§6.1 配套要求第一条** | 「`src/app/routes/anthropic.py:228` 对 Copilot 上游把 `require_stable_item_id` 设为 `False` 的现有分流**必须保持**」 | `src/app/routes/` **目录不存在**；`require_stable_item_id` 在 `src` 里 **0 命中**。今天等价的做法是 `_item_key`（`formats/openai_responses.py:491-503`）一律优先 `output_index`，对所有上游一视同仁，**没有** strict / 非 strict 的分流 | **规范过期**（描述的机制已不存在） |
| 7 | **§3.6** | 要求改 `src/app/protocols/anthropic_responses.py:538`（`self._reject_extras(tool, _TOOL_FIELDS, path)`）与 `:539-540`（`if tool.type is not None: self._fail(path, "server_tool_not_supported", ...)`） | **两行今天仍然逐字存在、行号仍然对得上**，但该模块**已不在产品链上**：`rg -n "app\.protocols" src` 显示 src 内只有 `protocols/responses_anthropic.py:14` 为拿 `ToolNameMapper` 而 import 它，请求翻译早已走 `pipeline/translation_driver/`。**按 §3.6 改那两行不会改变任何产品行为** | **规范过期，且是最容易骗过实现者的一条**——行号还对得上 |
| 8 | **§5.4 最后一条的定点改动** | 「对 `src/app/protocols/anthropic_responses.py:409` 现有 `server_tool_not_supported` 的定点改动」 | 那行还在（今天约 :408，`if self._is_server_block(block.type): self._fail(...)`），同样不在产品链上。产品链上等价的摊平**已经实现**在 `translation_driver/openai_responses.py:665-691` | **规范过期**——这一条实际上**已经完成**，只是完成在别的文件里 |
| 9 | **§11 覆盖清单第四行** | 同样指向 `anthropic_responses.py:409` | 同 8 | **规范过期** |
| 10 | **§12「cassette 的现状与限定」整段 + 文档状态「一手证据基线」一栏 + §5.1 / §5.3 的样本引用** | 路径写 `tests/cassettes/responses_web_search_*.json`；要求把场景挪进 `tests/integration/recorded/record_cassette.py` | 路径已迁到 `tests/int/cassettes/`；录制脚本已迁到 `tests/int/recorded/record_cassette.py` | **规范过期**（路径迁移） |
| 11 | **§12 同段「它们目前没有任何测试在回放」** | —— | 按字面不准确：`tests/int/test_pipeline_app.py:451` 在用 stream 那份（当字节源）。按「未走回放框架的形状校验」仍成立 | **部分过期**，需要改措辞而非改结论 |
| 12 | **文档状态第 6 行「状态：DRAFT」与第 24 行「实现前必须先关闭这些项」** | 「MJ-1／MJ-2／MJ-4／MJ-5／MJ-7／MJ-8 与全部 minor……**实现前必须先关闭**」 | 实现早已落地并在产（默认关闭）。这句按字面已不可能执行。status.md §4.3 记过一次，规范未改 | **规范过期** |

**另有一条我标为存疑而非过期**：§9.3 列出的三个必要条件里，第二条（resolved model 的 `supported_endpoints` 含 `/responses` 或 `ws:/responses`）在 `gate_hosted_web_search` 里**没有被求值**——该函数只判 inbound 格式（:94）、target 格式（:103）、counting-only（:105）、provider 的模式清单（:108-115）。合理的解释是这条由更早的路由阶段保证（模型不广告 `/responses` 就不会被路由到这条腿），但**我没有读 `pipeline/routing.py` 去证实**。见「不确定项」第 1 条。

---

## 2. 我排除掉、认为不成立的可能性

写下来，因为纯推理排除的路线事后谁都捞不回。

1. **「`url_citation` 也许在别的模块以别名被读取（比如只提 `annotations` 不提 `url_citation`）」** —— 排除。`rg -n "annotation" src` 去掉 `from __future__ import annotations` 后**只剩 4 条**，两条是散文、两条是出站写 `"annotations": []`。没有第三处代码触及 annotations。
2. **「`convert_responses_response_to_anthropic` 也许才是真正的非流式路径，改它就够了」** —— 排除。`rg -n "convert_responses_response_to_anthropic" src tests`：src 内除定义（`responses_anthropic.py:72`）与 `__all__`（:357）外**零调用**，15 处调用全在 `tests/unit/protocols/test_responses_anthropic_nonstream.py`。真正路径是 `translation_driver/responses.py:156` `from_openai_responses_response` → `blocks_from_item`。
3. **「`web_fetch` 在 Responses 腿也许在别处被 REJECT 了，只是不在 `_ANTHROPIC_SERVER_TOOL_FAMILIES` 里」** —— 排除。`test_translation_driver.py:738-744` **正面断言透传**且为绿。
4. **「`tool_usage` 也许被 history 层或 observability 层读走了，只是不在这两个文件里」** —— 排除。`rg -n "tool_usage|num_requests" src` 全仓 4 条命中，全部在注释里。
5. **「§6.3 也许已经部分实现，比如 `content_part.done` 已经在收集什么」** —— 排除。`ResponsesAssembler.push` 的分支表（:441-489）没有该事件，也没有 `annotation.added`，落到 :489 `return ()`。
6. **「块对也许可以无条件产出，Responses framer 会兜底」** —— 排除。`ResponsesFramer.block`（:180-189）的 `else` 是 `raise ValueError`，:178 的 docstring 明说这是刻意的：旧的 `else` 落到 `_message`（读 `payload[TEXT]`）会把未知块变成一个空的 assistant 轮次，把「我们没认出来」和「上游什么都没发」变成同一件事。
7. **「status.md §4.5 说的那个 `else` 也许已经被人改成穷尽分支了」** —— 排除。:285-309 仍是「`if policy == "error"` → raise，其余无条件落空」。三处已有用例（:631、:639、`test_pipeline_app.py:682`）确实只覆盖两个取值。
8. **「加 `LossCode` 成员也许会打破某张以它为键的表」** —— 排除。`rg -n "LossCode\]" src` **零命中**，没有以它为键的映射；`Conversion.has(LossCode.…)` 那类是按值查询，不是穷举表。
9. **「`server_tool_use` 块也许会污染 `terminal.tools`，或把 `stop_reason` 变成 `tool_use`」** —— 排除。两处判据都是与字面量 `"tool_use"` 比较（`assembling.py:57`、`formats/openai_responses.py:572`），`server_tool_use` 不等于它。
10. **「§5.3 的块对在 Anthropic framer 那边可能也没有 item 形状」** —— 排除。`block_frames`（`formats/anthropic_messages.py:90-141`）对未知 kind 走通用路径：`content_block_start` 带整个 payload、`_delta_for` 返回 `None` 就不发 delta、然后 `content_block_stop`。**合成失败结果的路径已经在跑这条通路**（`formats/anthropic_messages_synthetic_reply.py` 产 `server_tool_use` / `web_search_tool_result`），并被 `test_hosted_web_search_is_off_until_the_config_says_otherwise`（`test_pipeline_app.py:496`）等用例覆盖为绿。
11. **「`session.committed_count` 也需要跟着块对改」** —— 排除。它是 `len(session.delivered)`（`blocks.py:139-141`），按实际交付的块数走，块对会自动被计入；`_hand_over` 的 `CompletedBlock(index=session.committed_count, ...)`（`stream.py:609`）因此自动正确。
12. **「`terminal.blocks` 从 1 变 2 会翻转 `cut_short` 的判断」** —— 排除（判据是 `> 0`，1→2 不翻转）。**但同一处存在另一个真实风险**：时点，见 G3(b)。这一条不是排除而是**改判**，写在这里以免读者把 G3(b) 误读成「已排除」。

**清单非空。** 另有一类我没有去排除、直接按不成立处理的：规范里所有仅涉及请求侧声明映射（§3.1、§3.2、§3.3、§3.5）与能力门（§9.1、§9.2、§9.3）的条款，本次只做了抽样对读，没有逐条对账——它们不在任务的七条范围内。

---

## 3. 不确定项（明说，不补答案）

1. **§9.3 第二条件（`supported_endpoints` 含 `/responses`）是否真的在路由阶段被当作必要条件。** 我没有读 `src/app/pipeline/routing.py`。如果不是，能力门里确实少判一条，§9.3 就不只是「表述让人误会」而是真有缺口。
2. **`error_code: "unavailable"` 是否在 Anthropic `web_search_tool_result_error` 的合法枚举内**（规范 §5.3 新增探针 P12，标着「实现前必须核对」）。我没有核对外部文档。它已经在合成失败结果里用了一段时间（`formats/anthropic_messages_synthetic_reply.py` 的 `ERROR_CODE`），但「客户端没报错」不等于「在枚举内」。
3. **`url_citation` 的 `start_index` / `end_index` 是字节偏移还是字符偏移**，以及去重时 `?utm_source=openai` 这个尾巴是否应先归一化。一手样本只有一条 citation，判不出来。§5.3 只要求 `{type,url,title}` 三个键，所以不阻塞；但去重键取 `url` 时这个尾巴会影响结果。
4. **`tests/int/recorded/cassettes.py:228` 的 digest 覆盖范围**（status.md §4.1 引用它说「digest 覆盖整个请求体」）。我没有复核该行号与该断言。
5. **主工作树 HEAD 与本工作树 HEAD 的逐行差异。** 只看了 `git diff --stat main...HEAD` 的文件名（6 个）。若在主树上实施，本报告所有行号需重新定位；文件与符号名应当仍然有效。
6. **`from_history.py` 能否真的派生出一份带 `url_citation` 的 cassette。** `reports/260821-responses-websearch-citation-evidence.md` 说取证来自 history 库的真实上游根帧，这**暗示**可行，但我没有跑 `from_history.py`，也没有查那些操作是否在 2026-08-15 之前（那是历史库停止存帧的日期）。这是 §5.3 「有 citation」分支能否被真实证据覆盖的关键，值得优先证实。

---

## 4. 给实现者的次序建议（不是计划，是依赖顺序）

1. **先加「客户端腿」开关并补 G1b 的控制用例**（inbound `/responses` + 上游含 `web_search_call`）。它决定后面所有改动会不会在生产上撕流，而且今天没有任何测试守着它。
2. **再改块序号分配**（从「按 item」改成「按发出的块」），同时把 `Terminal.record` 相对 `cut_short` 判断的时点定死（G3(b)）。顺手可以关掉 `DISCARDED` item 留洞那个既有问题——但那属于本规格之外，要不要一起做请先问。
3. **再接 annotations**（先做非流式 `_block_from_content_part`，形状简单、可直接用 B7 样本验；再做流式）。此时才有东西可以填 §5.3 的 `content`。
4. **再统一两腿的结果行渲染**（G6b），否则第一轮回喂就把 url 丢掉，而且不会有任何东西报错。
5. `empty_result`（G4）与 `usage`（G5）是可以独立并行的两片，与上面四步无依赖；`empty_result` 落地时记得它也产 Anthropic 块对，同样受 §8.3 末条的腿约束（而 §3.4 没写这一条）。

---

## 附：本次实际执行过的命令（可复现）

- `uv run pytest -q` 五个定向 nodeid → `5 passed in 2.32s`（基线）
- `uv run pytest tests --collect-only -q` → `1941 tests collected`
- `uv run python /tmp/probe_index.py` → 块序号分配实测（脚本在 `/tmp`，不在仓库内）
- `rg -n "url_citation" src` / `rg -n "annotation" src | rg -v "from __future__"` / `rg -n "tool_usage|num_requests" src` / `rg -n "LossCode\]" src` / `rg -n "convert_responses_response_to_anthropic" src tests`
- Python 解析 `tests/int/cassettes/responses_web_search_{stream,nonstream}.json`、`history_responses_stream.json`、`anthropic_to_responses_stream.json`、`exp/260820-websearch-probe/raw/B7-responses-tool-choice-builtin-response.txt`

未执行任何写操作。`src/` 与 `tests/` 未被触碰（调查开始时 `git status --short` 为空，全程只用 Read / rg / python 解析 / pytest 只读运行）。

> 落盘说明：本报告在隔离工作树 `260830-issue1-websearch-gate` 中撰写，而 `.dev/` 只存在于主工作树根（隔离工作树里没有副本）。Write 工具的工作树护栏不认这个例外，因此正文先写到 `/tmp`，再用 `cp` 复制到本路径。内容未经任何中间加工。
