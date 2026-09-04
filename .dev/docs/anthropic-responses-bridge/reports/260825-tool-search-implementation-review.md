# Tool search 翻译实现评审（`5eaef9d` + `b60797c` + spec `c80ec16`）

- 日期：2026-08-25
- 评审者：独立评审 subagent（未修改被评对象；一次受控变异已还原并核对，见 §5）
- 被评基线：主仓 `b60797c`（主体 `5eaef9d`）、`.dev` 仓 `c80ec16`（spec.md 与 implementation.md 的本次修订，在我开始阅读期间由主会话提交）

## 评审范围

**在范围内**：`src/app/pipeline/translation_driver/tool_search.py`（新增）、`openai_responses.py` 请求与响应两侧改动、`responses.py` / `registry.py` / `semantic.py` / `../driver.py` / `../reply.py` / `../delivery_policy.py` / `../delivery/formats/openai_responses.py` 的名字传递链、三个测试文件的新增部分、`exp/260824-beta-and-cache-control-probe/verify_tool_search_translation.py` 及其 raw 输出；以及 spec.md「Tools 与 tool choice」本次修订条款与实现的对账。

**明确不在范围内**：`docs/.human-controlled/` 下的未提交改动（按派活要求）；`.dev` 仓其余未提交文件；hosted web search 既有实现（只在它与本次改动交叉处检查，见 F-1）；TUI 与其它无关模块。

**判据来源**（按权重，全部在读实现之前读完）：`docs/.human-controlled/message-translation.md`；spec.md「Tools 与 tool choice」本次修订条款（既是判据也是被评对象，已用 `git show c80ec16` 分清哪些是本轮新写的）；实测报告 `reports/260825-tool-search-translation-measurements.md` 与 `reports/260825-tool-search-translation-shapes.md`；`CLAUDE.md` 与 `.claude/rules/00-development-workflow.md`。

## 总体 verdict

`needs-fix`。**blocker 0**，major 8，minor 5，nit 1。

没有发现「提升了却没移除」或「移除了却没提升」的常规路径缺陷——那两个不变量在单客户端搜索工具这条主路上是守住的，实测确认。问题集中在**三类交叉场景**：托管与自定义同时出现、托管被提升后上游回来的 item、以及**从请求侧到响应侧那条名字传递链完全没有任何检查在守它**（F-6，一次变异证明删掉它 1809 个测试仍全绿）。另有两处代码注释仍把已被推翻的 8-24 裁决写成现行裁决（F-8），这是投调查报告已经点名要求同步、但本次没做的一项。

---

## 发现

### F-1 · major · 托管 tool search 的名字进了 `mapped_names`，于是一个指向它的 forced choice 被改写成 `{"type": "web_search"}`

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:374-376`
- 相关位置：`src/app/pipeline/translation_driver/openai_responses.py:759-765`（`_carry_forced_search`）、`:783-789`（`_repoint_tool_choice`）

`mapped_names` 的既有语义是「变成了 web search builtin 的那些 Anthropic 声明名」——两个消费者都无条件把命中它的 `tool_choice` 改写成 `{"type": _WEB_SEARCH_TYPE}`。本次在托管 tool search 分支里也往这个集合塞了名字（注释写的理由是「让 `tool_choice` 能跟着走」），但没有区分它跟去的是哪一个 builtin。

**失败场景（已实测）**：客户端声明 `{"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"}` + 一个 deferred 工具 + `tool_choice: {"type": "tool", "name": "tool_search_tool_regex"}`（VS Code Copilot Chat 正是用这个名字发托管声明）。出站 body 实测为：

```
tools:       [{"type":"tool_search","execution":"server"}, {…get_weather, defer_loading:true}]
tool_choice: {"type":"web_search"}
```

`tools` 里根本没有 `web_search`，`tool_choice` 却强制它。要么整请求 400（forced choice 指向未声明的工具），要么上游宽容地跑一次客户端从未要求过的 web search。记录的 loss 只有 `EXTENSIONS_NOT_CARRIED: tool_choice`，而它此刻是错的——`tool_choice` 恰恰被 carried 了，只是 carried 到了另一个 builtin 上。

这是**本次改动引入**的：在此之前托管 tool search 的名字从不进 `mapped_names`。建议把「映射到哪个 builtin」跟着名字一起带，而不是让两个消费者假设集合里只可能有 web search。

**权重：可据以行动**（探针 `/tmp/ts_probe2.py`，走 `default_registry().translate` 全链，输出如上逐字引用）。**可达性我拿不准**：没有证据表明任何一线客户端会用 `tool_choice` 点名托管搜索声明；不确定的是概率，不是这条路径的正确性。

### F-2 · major · 历史认出的搜索工具若不在本请求 `tools[]` 里，`defer_loading` 会被留下而没有任何 `tool_search`，命中已实测的 400

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:360`（`will_search` 只看「名字非空」，不看这个名字是否真的在 `tools` 里）
- 相关位置：`src/app/pipeline/translation_driver/tool_search.py:86-88`（历史反查不校验该名字仍被声明）

`will_search` 在循环前算，值为 `bool(search_tool) or any(hosted)`；`seen_tool_search` 在循环中变。两者不一致的方向只有一个，但那一个是致命的：`search_tool` 非空而循环里没有任何一个 tool 的 `name` 等于它 → 循环结束时 `seen_tool_search` 仍为 False（出站数组里没有 `tool_search`），而 `keep_defer_loading=will_search=True` 已经把 `defer_loading` 留在了每一个 function tool 上。

**失败场景（已实测）**：历史里有 `tool_use{id: toolu_1, name: FindTools}` + `tool_result{tool_use_id: toolu_1, content: [tool_reference…]}`，本请求 `tools` 只有 `get_weather{defer_loading: true}`（不再声明 `FindTools`）。出站实测：

```
tools:       [{"name":"get_weather","defer_loading":true,"type":"function",…}]   ← 没有任何 tool_search
input items: ['message', 'tool_search_call', 'tool_search_output']
```

这正是 `req=fcc0bebc` 那次 400 的逐字形状：`Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.`（spec.md:157 记载的实测）。而且 `input` 里还多了两个指向不存在的 `tool_search` 的 item。**整请求失败，客户端丢掉一整轮。**

修法一行：要么 `will_search` 改为「识别出的名字确实出现在 `tools` 里」，要么先建数组再据 `seen_tool_search` 决定 `keep_defer_loading`。

**权重：失败后果可据以行动（实测）；触发条件我拿不准。** 我没能从 Claude Code 或 VS Code Copilot Chat 的行为构造出「历史有 `tool_reference` 而当前 `tools` 不声明该工具、同时仍有 deferred 工具」的路径——两者都是每轮重发完整 tools 数组。但这里没有任何保护，代价是整请求 400，而防护成本是一个条件。

### F-3 · major · 托管与自定义同时出现时，行为随 `tools` 数组顺序而变；托管在前时客户端的搜索工具被静默删除且不记 loss

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:378-383`（客户端分支在 `seen_tool_search` 已置位时是一个裸 `continue`）
- 相关位置：`:363-377`（托管分支在同样情形下记了 `SERVER_TOOL_CONSTRAINT_DROPPED`）、`:829`（`request.client_search_tool` 无条件写成识别结果）

两个分支对「已经有一个 tool_search 了」的处置不对称：托管分支记 loss，客户端分支什么都不记。

**失败场景（已实测，两种顺序各跑一次）**：

| `tools` 顺序 | 出站 `tools` | 记录的 loss | `client_search_tool` |
|---|---|---|---|
| 托管在前，`ToolSearch` 在后 | `[{tool_search, execution: server}, get_weather]` | **空** | `'ToolSearch'` |
| `ToolSearch` 在前，托管在后 | `[{tool_search, execution: client, …}, get_weather]` | `SERVER_TOOL_CONSTRAINT_DROPPED` | `'ToolSearch'` |

第一行有三处问题叠加：(a) 客户端声明的 `ToolSearch` 从 `tools` 里消失了，**没有任何记录**——这正是模块 docstring 说「误判代价是静默删除一件能力」要防的那件事，只是这次不是误判造成的，是合并策略造成的；(b) `client_search_tool` 仍被设为 `'ToolSearch'`，于是响应侧会把上游**服务端执行**的 `tool_search_call` 当成一次要客户端回答的 `tool_use:ToolSearch` 交给客户端，而服务端已经自己搜完并继续了（实测 S1 的 output 序列即 `tool_search_call → tool_search_output → function_call`）；(c) 历史里对该工具的调用仍被写成 `execution: "client"` 的 item，与声明的 `execution: "server"` 不一致，这个组合从未实测过。

spec.md:161 只说了「托管与自定义两条路互斥」，没说互斥时谁赢、输的那个怎么记。实现选了「先到先得」，这是一个 spec 没有的行为决策。

**权重：可据以行动（实测）。可达性低**：两个一线客户端都是二选一（VS Code Copilot Chat 在 `!customToolSearchEnabled` 时才发托管）。

### F-4 · major · 托管提升让上游开始回 `tool_search_output`，流式路径把它变成空 text 块——那正是上游会拒绝回放的形状

- 主位置：`src/app/pipeline/delivery/formats/openai_responses.py:509-510`、`:584-585`
- 相关位置：`src/app/pipeline/translation_driver/openai_responses.py:426`（缓冲侧只认 `tool_search_call`，不认 `tool_search_output`）、`src/app/pipeline/translation_driver/responses.py:180-183`、spec.md:153-159（映射表没有 `tool_search_output` 的入站行）

调查报告 `260825-…-shapes.md` §4.2 已经把「流式对未知 output item 发一个空 text 块」标为「做 tool search 翻译那一刻会立刻从潜伏变成活缺陷」的潜伏面。本次把它变活了，而修的只有一半：`tool_search_call` 在**有名字**时被接住，`tool_search_output` 在**任何**情况下都没被接住。

**失败场景（已实测）**，喂 `tool_search_call` + `tool_search_output` 两个 item：

```
流式，client_search_tool='':          tool_search_call   {"type":"text","text":""}
                                      tool_search_output {"type":"text","text":""}
流式，client_search_tool='ToolSearch': tool_use           {…正确…}
                                      tool_search_output {"type":"text","text":""}
缓冲，client_search_tool='':          content=[]  losses=[ITEM_NOT_CARRIED ×2]
缓冲，client_search_tool='ToolSearch': content=[tool_use]  losses=[ITEM_NOT_CARRIED(tool_search_output)]
```

触发路径是本次新增的托管提升：客户端发 `tool_search_tool_regex_*` → 现在被翻成 `{type: tool_search, execution: server}` → 上游 200 并**自己**产出 `tool_search_call` 与 `tool_search_output`（实测 S1）→ 流式客户端收到一到两个空 text 块。按 `responses.py:88` 的注释，携带空 text 块的 assistant 轮被上游拒绝（`text content blocks must be non-empty`），所以客户端把这一轮存进历史再回放就会 400。在本次改动之前，托管声明会被上游直接 400 掉，这些 item 从来到不了这里。

`_open()` 那句注释「否则它falls through 并按任何其它未识别 item 处理，which is the honest outcome」在事实层面是对的，但「未识别 item 的处置」本身是一个**已知缺陷**而不是一个诚实兜底——同一份调查报告在同一天记下了这一点。`implementation.md` 新增段第 2 条写「流式此前会把它变成一个空 text 块」，读起来像已经全部修好，实际只修了有名字的 `tool_search_call` 那一格。

同时这是一处 **spec 缺口**：映射表有 `tool_search_call` 的入站行，没有 `tool_search_output` 的；而托管那一行既然是 `TRANSFORM`，上游必然回这个 item。

**权重：本代理行为可据以行动（实测，两条路径各跑）；上游流式是否与非流式一样发这两个 item 是推断**——实测报告 §7 明说没测过流式。

### F-5 · major · 回答搜索调用的 `tool_result` 若带的是文本或错误，会变成 `status: "completed"` 且 `tools: []`，错误被静默吞掉

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:577-584`（`tool_search_output` 分支硬编码 `status: "completed"`）
- 相关位置：`src/app/pipeline/translation_driver/tool_search.py:143-160`（`loaded_tools` 对非 `tool_reference` 的 part 直接跳过，对不认识的名字也直接跳过，两者都不记录）

`_item_from_block` 按 `call_id` 判定「这是一次搜索的结果」，然后无条件渲染成 `tool_search_output{status: "completed", tools: loaded_tools(output)}`。`loaded_tools` 只挑 `tool_reference`，其余一律丢弃。

**失败场景（已实测）**：客户端的 `ToolSearch` 这一轮失败或被用户打断，回的是 `tool_result{is_error: true, content: [{"type":"text","text":"tool search failed: index unavailable"}]}`。出站实测：

```
{"type":"tool_search_output","call_id":"toolu_2","execution":"client","status":"completed","tools":[]}
losses: []
```

模型被告知「搜索顺利完成、什么也没找到」，而客户端说的是「搜索失败了」。`is_error` 和错误文本一起消失，**且不记任何 loss**。这是本次改动引入的**回退**：在此之前这条 `tool_result` 会走 `function_call_output`，文本原样到达模型。

第二个触发点同源：`tool_reference` 指向一个本请求 `tools[]` 里没有的名字时，`loaded_tools` 静默跳过；全部跳过就得到同一个「completed + 空数组」。docstring 说「跳过好过编造」——**跳过确实好过编造，但两者都不是「不留痕迹地跳过」**。`SemanticRequest.conversion` 就是为这件事存在的，`LossCode` 里也有现成的 `TOOL_RESULT_CONTENT_FLATTENED`。

另外 `status` 有 `"incomplete"` 一档（SDK `ResponseToolSearchOutputItemParamParam`），错误结果按 `incomplete` 渲染至少不会撒谎；这条我列为建议而非事实缺陷，因为上游对 `incomplete` 的反应未实测。

**权重：可据以行动（实测）。可达性高**——工具调用被用户拒绝／中断在 Claude Code 是常规事件。

### F-6 · major · 从请求侧到响应侧那条名字传递链，没有任何测试在守；删掉它 1809 个测试全绿

- 主位置：`src/app/pipeline/driver.py:163-165`（`context.extras[CLIENT_SEARCH_TOOL] = …`）
- 相关位置：`src/app/pipeline/reply.py:36`、`src/app/pipeline/delivery_policy.py:92`、`exp/260824-beta-and-cache-control-probe/verify_tool_search_translation.py:49,55`

**变异实验（我跑的）**：把 `driver.py` 里那三行写入删成一句注释，跑 `uv run pytest tests -q -p no:randomly` → **1809 passed, 2 skipped**。变异已还原，`git diff --stat -- src/app/pipeline/driver.py` 与 `git status --short -- src/` 均为空。

全仓对 `client_search_tool` 的测试引用只出现在两处，且**都是在下一层手工注入**：`translate_response(..., client_search_tool="ToolSearch")` 和 `ResponsesAssembler(client_search_tool="ToolSearch")`。没有任何测试走 `handle()`／`response_payload()`／`assembler_for()`。

更要紧的是：**真实端点验证脚本也绕过了这条链**。`verify_tool_search_translation.py` 直接取 `semantic.client_search_tool` 再手工传给 `translate_response`，`body["stream"] = False`。所以提交信息里那句「Verified against the real endpoint in both directions」覆盖的是两个翻译函数，不是被服务出去的那条路；而流式那半在真实端点上**一次都没跑过**。

三个接缝我逐个读过，逻辑本身是自洽的（写入条件 → 读出默认 `""` → 两个消费者读同一个键），所以我没有把它定成 blocker：今天大概率是通的。但「大概率是通的」和「有东西在守它」是两回事，本仓的项目记忆里已经有一条 `guards-stranded-on-the-legacy-chain` 是为同一形状写的。补一个走 `handle()` + `assembler_for()` 的集成测试即可闭合。

**权重：可据以行动（变异实测，带还原核对）。**

### F-7 · major · `tool_search_call` 若没有 `output_item.added` 就直接 `done`，整个 item 被静默丢弃——而紧邻的 `web_search_call` 恰恰为这件事写了补救

- 主位置：`src/app/pipeline/delivery/formats/openai_responses.py:529-536`

`_close()` 里 draft 缺失时只对 `WEB_SEARCH_CALL` 做迟到注册，其余一律 `return ()`。而 `tool_search_call` 与 `web_search_call` 在这两个性质上完全同构：**在 `done` 上才完整、没有任何 delta 事件**——这两点正是紧挨着的 `:548-550` 与 `:578` 两段注释各自写下的。

**失败场景（已实测消费端行为）**：只发 `response.output_item.done`（不发 `added`）→ 返回 `[]`。若这是该轮唯一的 item，客户端拿到一个没有内容的 assistant 轮，`_saw_tool_call` 也没置位，`stop_reason` 落到 `end_turn`——模型在等一次搜索，客户端被告知这一轮结束了。

**权重：后果可据以行动（实测）；触发条件是推断。** 上游是否会对 `tool_search_call` 省略 `added`，没有实测（流式整体未测）。我把它列为 major 而不是 minor，理由是同一个上游对同族 item 已经被观测到干过这件事，而且代码里两段注释都承认这两个 item 同构。

### F-8 · major · 两处代码注释仍把已被推翻的 8-24 裁决写成现行裁决，其中一处就在它所解释的常量正上方

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:154-158`
- 相关位置：`src/app/pipeline/translation_driver/openai_responses.py:217`

`:156-158` 逐字仍写着：「**用户 2026-08-24 裁定 tool search 不是本代理提供的能力**，所以那个映射不在桌面上，这个字段就直接去掉」——而它注解的 `_DEFERRED_LOADING` 现在恰恰会被保留，映射也恰恰做了。`:217` 写「`memory_`、`tool_search_`、… 今天原样通过」，`tool_search_` 一族现在被 `is_hosted_search_tool` 截走了。

调查报告 `260825-…-shapes.md` 的「交回主会话」第 1 条**逐字点名要求**同步这段注释，本次没有做。按 `one-authority-allows-contextual-restatement`，restatement 必须随权威一起更新；这里的偏差方向最坏——一个未来的读者会拿这段注释当作用户裁决的一手复述，据以把刚做好的翻译再撤回去。

同一条还开着的第三处：`.dev/docs/anthropic-responses-bridge/review-disposition-tool-whitelist.md` 也被那份报告点名要求同步，我核了 `c80ec16` 的 stat，该文件不在本次修订里。（我没读它的内容，只核了它是否被改。）

**权重：可据以行动**（`git show`／`rg` 逐字核对）。列为 major 而非 minor，是因为被复述错的是**一条用户裁决**，不是一个实现细节。

### F-9 · minor · `arguments` 不是 dict 时，缓冲与流式给出两个不同的答案

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:428,434`
- 相关位置：`src/app/pipeline/delivery/formats/openai_responses.py:562`

缓冲侧只判 `is not None`，流式侧判 `isinstance(dict)`。实测同一份 `arguments: '{"query": "w"}'`（JSON 字符串）：

```
缓冲: {"type":"tool_use","id":"call_a","name":"ToolSearch","input":"{\"query\": \"w\"}"}   ← input 是字符串
流式: {"type":"tool_use","id":"call_a","name":"ToolSearch","input":{}}
```

SDK 类型说 `arguments` 是 object，所以这只是防御路径；但两条交付路径对同一个畸形输入给出不同结果，正是本仓反复付过代价的那一类。缓冲那一侧更差：Anthropic 的 `tool_use.input` 是字符串，客户端解析器基本不接。

**权重：可据以行动（实测）。**

### F-10 · minor · 代理凭空补的 `description` / `parameters` 没有记 `SYNTHETIC_TURN_ADDED`，Spec 的映射表也没写它

- 主位置：`src/app/pipeline/translation_driver/tool_search.py:106-117`
- 相关位置：spec.md:153-159 映射表「客户端的搜索工具」行只写了 `description, parameters`（搬）

工具没有 description 时补一句 `"Search for tools that are available but not yet loaded."`，`input_schema` 空时补 `{query: string}`。避免 400 的理由成立（S3 实测），但这两样都是**代理写进 body、客户端没写过的东西**，而 `LossCode.SYNTHETIC_TURN_ADDED` 的 docstring 逐字就是为这件事定义的：「The only member that records an *addition* … a body that no longer says what the client said has to say so somewhere a reader will see it.」现在没人记，运维看不出模型读到的那句描述是谁写的。

同时这是一个 Spec 面外的可观察行为：映射表写的是「搬」，实现是「搬，没有就编一句」。按 `.claude/rules/00-development-workflow.md`「Spec 级事实不得停在别处」，这句兜底该进 Spec。

### F-11 · minor · Spec 第 4 步要求「记录未能识别这一事实」，实现没有记

- 主位置：spec.md:170
- 相关位置：`src/app/pipeline/translation_driver/tool_search.py`（全文无 logger、无 conversion 记录）、`openai_responses.py:199-205`

认不出时唯一的痕迹是 `_function_tool` 记的那条 `SERVER_TOOL_CONSTRAINT_DROPPED`，detail 是「deferred tool loading not carried … the full definition is in context」——它说的是「defer_loading 掉了」，不是「我没认出你的搜索工具」。两者对运维不是同一件事：前者读起来像既定行为，后者才是「你这个客户端的名字不在我的清单里，来提一下」。

### F-12 · minor · 三处没有分辨力的绿

- 主位置：`tests/unit/pipeline/delivery/test_sse_assembly.py:620-641`
- 相关位置：`tests/unit/pipeline/translation_driver/test_tool_search.py:39-45`、`tests/unit/pipeline/translation_driver/test_translation_driver.py`（新增段整体）

1. `test_without_a_name_a_search_call_is_not_delivered_as_some_other_tool` 只断言「没有块的 name 是 ToolSearch」。丢弃、空 text 块、抛异常……全都能过。它当前实际锁住的是 F-4 那个空 text 块，而 docstring 把它写成「worse but not *wrong*」。要么断言真实产物，要么把 F-4 修掉再断言。
2. `has_deferred_tool` 的 `is True` 是整个闸门的语义所在（`defer_loading: false` 必须**不**开闸，而 Claude Code 按百计地发 false），但没有任何测试覆盖「有 `defer_loading: false` + 有一个叫 `ToolSearch` 的工具」这一格。把 `is True` 改成 `is not None` 不会打红任何测试。
3. 新增的驱动测试没有断言 `tool_search_call` / `tool_search_output` 上的 `execution` 与 `status` 两个键（只断言了 `type`／`call_id`／`arguments`／`tools`）。把 `execution` 写成 `"server"` 不会打红——而实测 E1 说明这两种执行方是互斥的两条路。

（作者自报的三次变异——识别恒空、去闸门、流式不认 `tool_search_call`——我没有复跑；上面三条是我另找的、当前**没有**分辨力的分支。）

### F-13 · nit · `_tools_for_upstream(search=None)` 的默认值是死路，且恰好复活了同一文件警告过的那件事

- 主位置：`src/app/pipeline/translation_driver/openai_responses.py:342,358`

唯一调用者总是传 `search`。而 `:828` 的注释写着「Passed to both rather than computed twice — two independent answers to 'is there a search here' is how the tools array and the history come to disagree」——`:358` 的 `else resolve_client_search_tool(...)` 正是那第二个独立答案，只是今天没人走它。改成必填参数即可让这句注释自己成立。

---

## 我排除了什么（硬性清单）

**查了，认为不是问题：**

1. **「提升可能既留原工具又加 builtin」**（派活问题 2 的前半）——不成立。两个提升分支都以 `continue` 结尾，测试 `test_promotion_removes_the_original_rather_than_adding_beside_it` 断言了缺席，我另跑的 P1/P2 两种顺序也都确认原工具不在出站数组里。反方向（移除却没生成）成立，即 F-2。
2. **`context.extras` 的生命周期与重试**（派活问题 4）——查了没找到问题。翻译在 `driver.handle()` 里只做一次，在驱动的重试循环**之外**；`RequestContext` 是每请求一个。`inference.py:416` 的 replay 会拿同一个 `context` 重入 `handle()`，但它先把 `context.payload` 恢复成入站原体，于是识别结果逐位相同。唯一的理论残留是「写入是条件的、从不清空」：若某次重入不再需要翻译，旧名字会留在 extras 里——但那种重入意味着入站本来就不是 Anthropic，也就从来没识别出过名字。没有构造出有害路径，故不列为发现。
3. **`_search_context` 用一次性 `Conversion`**（派活问题 6 的前半）——做法正确。每个工具在主循环里都会再走一次 `_function_tool` 并把真实丢弃记进真 conversion；scratch 那遍唯一多丢的是 `defer_loading`，记进去反而会报一次本请求没发生的降级。P1–P4 四次实测的 losses 列表里没有任何重复条目，与这个判断一致。
4. **定义里剥掉 `defer_loading`**（派活问题 6 的后半）——**结论对，但给的理由不是证据**。真正的依据是 `probe_tool_search_roundtrip.py:28-33,75`：R2 实测回传的 `WEATHER_FULL` 就是**不带** `defer_loading` 的那份，200 通过；带着 `defer_loading` 回传从未测过。代码注释给的是语义美学理由（「正在被加载的定义不该还说自己是 deferred」），我认为该理由本身也成立，但它不是这条能安全落地的原因。建议把实测那一句写进注释。此外，注释里那句反问「一个 `tool_reference` 指向请求里不存在的工具时会怎样」的答案是「静默跳过」，已并入 F-5。
5. **历史反查的 `call_id` 跨轮次串味**（派活问题 1）——查了，不成立。`referenced` 收集所有带 `tool_reference` 的 `tool_result` 的 `call_id`，再按同一个 id 反查 `tool_use`；id 在 Anthropic 侧是全会话唯一的。真正的取值风险不在串味，而在 F-2 的「反查到的名字可能已不在 tools 里」。
6. **「恰好一个」那条的意外命中**（派活问题 1）——查了，我认为可接受。同名重复声明会让它退让（`len(named) == 2`），这是保守方向；托管声明若恰好也叫 `tool_search` 会同时进 `named` 和托管分支，后果并入 F-3。剩下的真实假阳性是「第三方客户端有一个普通工具叫 `tool_search`／`ToolSearch`，同一请求里还有 deferred 工具」——MCP 工具带 `mcp__` 前缀撞不上，闸门也确实把普通请求挡在外面（P 系列实测：无 deferred 工具时 `search_tool` 恒为 `""`）。风险已被压到 spec.md:172 自己描述的那一格，我同意那个取舍。
7. **`DeferredToolPlaceholder` 让闸门形同虚设**——查了，不改变结论。Claude Code 会塞一个 `defer_loading: true` 的占位工具（shapes 报告 §1.3），所以对 CC 而言闸门几乎恒开。但闸门的作用本来就只是「把没有搜索机制的请求排除」，CC 塞占位工具本身就说明搜索机制开着，闸门判断正确。模块 docstring 说「a tool called `ToolSearch` in a request with no deferred tools is never examined」在字面上仍然成立。
8. **入站方向（Responses → 内部）读到 `tool_search_call`**——`blocks_from_item` 在请求侧 input reader 上用默认 `client_search_tool=""`，于是这类 item 变 UNKNOWN。这是 Responses→Anthropic 入站方向的既有限制，不是本次引入，也不在主产品路径上（`routing.py` 不做 Responses→Responses）。不列为发现。
9. **spec 修订是否越界**（派活问题 8）——**查了，没有越界。** 修订把 8-24 的两半明确拆开，禁止主动注入那半保留（spec.md:14、:148 各写了一次），两个 legacy 开关不恢复。Server-tool no-revive 里同时移出的 web search 一族我单独核了：`hosted-web-search-spec.md:20` 记有用户 2026-08-20 的逐字裁决（「anthropic 上游不支持，但 gpt 上游支持 websearch」「该路径要正确支持 server tool web_search」），所以「两族已经由用户裁决移出本条」这句归属成立。`memory_`／`text_editor_`／`bash_`／`computer_` 四族仍留在 no-revive 内，与 8-24 评审收窄的结论一致。
10. **Spec 修订记录格式**——第 14 行按既有体例写了触发、依据、被证伪的旧理由与报告链接，符合本项目「修订须可审计」的要求。未发现问题。
11. **纪律面**（派活问题 9）——`uv run ruff check src tests` 全绿、`uv run pyright src tests` 0 errors，与作者自报一致（我复跑了）。新增代码无硬折行，注释密度符合本仓风格（长单行注释、解释「为什么」而非「是什么」）。`b60797c` 修的是 `pyright src tests` 与 `pyright src` 的差别，属实。
12. **`_search_context` 把非 deferred 工具也放进 `definitions`**——想过，未列为发现。后果是「`tool_reference` 指向一个本来就在 `tools` 里的非 deferred 工具时，它的定义会被重复送一份」，上游反应未实测，且两个一线客户端的 `matches` 都来自 deferred 集合。记在这里以免被静默丢掉。
13. **`tool_search_call` 置位 `_saw_tool_call`**——查了，正确且必要：客户端必须回答这次搜索，`stop_reason` 必须是 `tool_use`。缓冲侧有断言，流式侧没有（并入 F-12 的性质，但我没单列，因为该行为本身对）。
14. **截断的 `tool_search_call`**（派活问题 5 提到的「被截断的 item」）——两条路径处置一致：流式走 `_upstream_cut_this_item_short` + `_cut_short` 暂存，缓冲走 `status == "incomplete"` + `ITEM_NOT_CARRIED`，与 `function_call` 同规则。未发现新问题。

**没有查的面（交回调用方）：**

15. **真实客户端的 tool search 请求样本**——本仓仍没有一份带 `defer_loading` 的 Claude Code 出站请求副本（实测报告 §6 已记）。所以「`ENABLE_TOOL_SEARCH=true` 之后本代理实际收到什么」仍未观测，F-2／F-3 的可达性判断因此只能停在「我构造不出」。
16. **流式路径对真实上游的验证**——一次都没有。F-4 与 F-7 都落在这个盲区里。建议在下一次真实调用时把 `stream=True` 也跑一遍，并把 `output_item.added/done` 的原始帧存成 cassette。
17. `review-disposition-tool-whitelist.md` 的正文内容我没读（只核了它未被本次修订触及）。

## 我跑过的命令

```
git show 5eaef9d --stat / -- <各文件>；git show b60797c --stat
git -C .dev show c80ec16 -- docs/anthropic-responses-bridge/spec.md
git -C .dev log --oneline -- docs/anthropic-responses-bridge/spec.md
rg -n / rg -c 'client_search_tool|CLIENT_SEARCH_TOOL|_tools_for_upstream|mapped_names' src tests
PYTHONPATH=src uv run python /tmp/ts_probe.py      # P1–P8，见各条发现
PYTHONPATH=src uv run python /tmp/ts_probe2.py     # F-1
uv run ruff check src tests                        # All checks passed
uv run pyright src tests                           # 0 errors
uv run pytest tests -q -p no:randomly               # 变异态：1809 passed, 2 skipped（F-6）
cp /tmp/driver.py.good src/app/pipeline/driver.py && git diff --stat -- src/app/pipeline/driver.py   # 还原核对：空
```

两个探针留在 `/tmp/`（`ts_probe.py`、`ts_probe2.py`），未进仓库。变异快照 `/tmp/driver.py.good`。

## 建议的处置顺序（取舍归调用方）

1. F-2（一个条件，挡掉整请求 400）与 F-3（一个 loss 记录 + 决定谁赢并写进 Spec）——都在 `_tools_for_upstream` 同一段，一起改代价最低。
2. F-5（错误结果不再被静默吞掉）——面向真实用户触发率最高的一条。
3. F-4（`tool_search_output` 的入站处置 + Spec 补一行）与 F-1（`mapped_names` 区分它跟去哪个 builtin）。
4. F-6（一个走 `handle()` 的集成测试）与 F-12（三处补断言）。
5. F-8（两处注释 + 一份处置文档）——纯文档，但它复述错的是用户裁决。
6. F-7、F-9、F-10、F-11、F-13 视排期。
