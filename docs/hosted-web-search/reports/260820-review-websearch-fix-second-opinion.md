# 对照评审：Responses 腿 web_search 声明 400 止血修复

日期：2026-08-20
评审对象：`git diff src/app/pipeline/translation_driver/openai_responses.py src/app/pipeline/translation_driver/semantic.py tests/unit/test_translation_driver.py` 加 `tests/http/test_pipeline_app.py` 中新增的 `test_an_anthropic_server_tool_declaration_never_reaches_the_responses_endpoint` 一项。该文件其余未提交改动（stream 截断报告一批）属并行会话，不在本次评审范围。
自述文档：`docs/tmp/260820-websearch-responses-leg-400-fix.md`（作为待检验主张处理）
评审重心：范围裁决是否正确、三个已知缺口的取舍、对 `hosted-web-search-spec.md` 两处更正是否成立
结论：**needs-fix** —— 代码本身作为止血是可以留的，但自述文档中支撑范围裁决的**首要理由在在产链路上不成立**，且一条缺口的免责依据**误引了 spec**。这两条在交给用户裁决前必须更正，否则用户是在错误前提上做决定。

---

## 0. 一句话总结

**裁决（先止血、不实现 spec）是对的，但作者给出的最强理由是错的。** 实测证明：在产链路的响应侧遇到 `web_search_call` 不会失败，它会静默降级（流式多出一个空 text 块，非流式直接丢弃并记 `item-not-carried`）。所以「请求侧映射会把 400 换成一个更糟的失败」不成立。真正站得住的理由是另一条，作者没写：**没有能力门，映射会把 400 从 Claude 模型搬到 grok／mai-code 这些广告了 `/responses` 却从未探针过的模型上。**

---

## 1. 逐条发现

### [major-1] §4 理由 1「响应侧接不住 `web_search_call`」在在产链路上被证伪

**原声称**（文档 §4，列为「按可证的代价排列」的第一条，也是代码 docstring 里写进 `_tools_for_upstream` 的那条）：

> 只做请求侧映射会把 400 换成一个更糟的失败。映射之后上游会真的执行搜索，回复里带 `web_search_call` item，而响应侧今天没有承接它的地方（现有 parser 会落进 `UnsupportedResponsesEvent` 的默认分支）。

**质疑触发器**：承重（这条决定了用户是否接受「不实现 spec」）+ 跨条件外推（`UnsupportedResponsesEvent` 属哪条链路未加限定）。

**证据**：`UnsupportedResponsesEvent` 定义在 `src/app/openai/responses_stream_parser.py:54`，唯一消费者是 `src/app/delivery/anthropic_sse.py:655`。这两个文件属 legacy 链路——与作者自己在 §6.1 里指出的 `protocols/anthropic_responses.py` 是同一套。**在产的 pipeline 链路根本没有这个类型。**

我用真实录制的上游流（`exp/260820-websearch-probe/raw/C2-responses-search-stream-response.txt`，含 1 个 `web_search_call` item 与 `response.web_search_call.{in_progress,searching,completed}` 三个专有事件）直接驱动在产的 `ResponsesAssembler` 与 `pipeline/delivery/anthropic_sse.block_frames`，探针 `/tmp/probe_websearch_response_side.py`，输出逐字如下：

```
=== STREAMING PATH ===
blocks produced: 2
  index=0 kind='web_search_call' payload={'type': 'text', 'text': ''}
  index=1 kind='text' payload={'type': 'text', 'text': 'Today's date is **Thursday, August 20, 2026** in the United States. '}
terminal: seen=True stop_reason='end_turn'
frames the client would receive:
  content_block_start: {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}
  content_block_stop: {'type': 'content_block_stop', 'index': 0}
  content_block_start: {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}}
  content_block_delta: {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'text_delta', 'text': 'Today's date is ...'}}
  content_block_stop: {'type': 'content_block_stop', 'index': 1}

=== NON-STREAMING PATH ===
blocks: [(BlockKind.TEXT, 'Today's date is **Thursday, August 20, 2')]
losses: ["item-not-carried: output item 'web_search_call'"]
stop_reason: end_turn
```

机制在 `src/app/pipeline/delivery/assembler.py:254-258`：`_open` 的 kind 映射表 `.get(item_type, item_type)` 对未知 item 类型**回落成它自己的名字**而不是报错；`_close`（`:292-293`）走 `else` 分支产出 `{"type":"text","text":""}`；`anthropic_sse._delta_for`（`:48-60`）对未知 kind 返回 `None`，于是只发 start + stop。非流式在 `translation_driver/responses.py:142-146` 走 `BlockKind.UNKNOWN` → 记 `ITEM_NOT_CARRIED` → `continue`，item 被丢掉，正文照常交付。

**结论（已推翻，强，一手实测 + 真实上游录制）**：请求侧映射今天**不会**在响应侧失败。它会交付一个可用的、降级的回答——搜索真的执行了，结果在模型正文里，客户端只是多收到一个空 text 块（流式）或什么都不多收到（非流式）。空 text 块在下一轮回传给 `/responses` 也是安全的：`exp/260820-empty-text-probe/FINDINGS.md` E2／E4 实测 200，且带阳性对照 E5（Anthropic 腿同一形状 400）。

**为什么这条重要，而不只是「理由写错了」**：作者据此建议用户接受「不实现 spec」。这条理由一倒，spec §5／§6（response presentation、stream lifecycle）从「不做就会坏」降级成「不做只是不好看」——下一片的成本与紧迫性完全变了。用户应当在正确的成本表上做裁决。

**讽刺之处，值得作者本人注意**：这正是他在 §6.1 里给 spec 挑出的那个错误——把 legacy 链路的行为当成在产行为——他在 §4 自己又犯了一次。同一份文档里一条纠正、一条复犯。

### [major-2] §5.1 用 spec §13「维持现状」免责其他 typed tool，是误引

**原声称**（文档 §5.1）：

> 按 spec §13「客户端执行型 typed tool 在 Responses 腿的处置：本规格不动，维持现状」，本次没有动它们。这与 `server_tools.py` 的既有纪律一致——只剥离**实测拒绝**的两族，不在猜测上剥离。

**两处都不成立。**

**其一，spec 说的「现状」不是生产上的现状。** spec §3.6 逐字要求「**其余任何非空 `tool.type` 继续 `server_tool_not_supported`**」，§11 的覆盖清单也把「请求侧历史 server-tool block 的 `REJECT`（`src/app/protocols/anthropic_responses.py:409` 实现）」当作起点。也就是说，spec 心目中的「现状」是**本地具名 REJECT**（legacy 链路的 `anthropic_responses.py:539`），而生产上的现状是**原样透传给上游、拿一个措辞不透明的 400、整轮死掉**。作者自己在 §6.1 证明了 spec 点名的那些行不在产——那么建立在同一误判之上的 §13「维持现状」，同样不能拿来免责。**spec 授权的是「保持本地 REJECT」，不是「保持静默透传」。**

**其二，这不是「猜测」。** 生产 400 的 body 自带上游枚举（文档 §1 逐字引用）：

```
Supported values are: 'code_interpreter', 'programmatic_tool_calling', 'function', 'namespace',
'tool_search', 'file_search', 'web_search_preview', 'web_search_preview_2025_03_11',
'image_generation', 'mcp', 'custom', 'computer', 'computer_use_preview', 'shell', 'apply_patch'
```

`bash_20250124`、`text_editor_20250728`、`computer_20250124`、`memory_*`、带日期的 `tool_search_*` **一个都不在里面**（`computer` 与 `tool_search` 只有裸拼法在）。这是上游自己列出的、该字段接受的全部取值。把它称作「从未探针」在字面上对，但把它归入「不在猜测上剥离」的纪律，是把一条上游自述的枚举证据降格成了推测。

我已实测确认这些声明今天确实原样透传（探针 `/tmp/probe_tool_choice_dangling.py`）：

```
=== anthropic -> responses, other typed tools (the unfixed gap) ===
payload: {'model': 'claude', 'input': [...], 'tools': [{'type': 'bash_20250124', 'name': 'bash'},
         {'type': 'text_editor_20250728', 'name': 'str_replace_based_edit_tool'}]}
```

**这一片要不要一起修？我的意见：不必剥离，但应当补一条本地 REJECT，作为紧随其后的独立小片。** 理由：剥离一个客户端执行型工具，是替客户端决定它的 harness 少一个工具，属于行为猜测；而本地具名失败既不猜测行为，又把一个不可诊断的上游 400 换成一个可诊断的本地错误，还恰好就是 spec §3.6 要的语义。代码量与本次相当。不列为本片 blocker，是因为它与本次事故不是同一个触发条件（暴露面取决于客户端是否发这些声明，未测），但**文档里那句「按 spec §13 维持现状」必须改掉**，否则它给了一个并不存在的授权。

### [minor-1] §5.2「没有东西可悬空」在同格式路径上被证伪，且缺了 Anthropic 腿已有的 `tool_choice` 清理

**原声称**（文档 §5.2）：跨协议翻译时 `tool_choice` 根本没到达上游，「本次修复因此不需要清理悬空 `tool_choice`（没有东西可悬空）」。

**跨格式那半，已确认**（探针输出）：

```
=== anthropic -> responses, tool_choice ===
payload: {'model': 'claude', 'input': [...], 'tools': [{'name': 'get_time', 'type': 'function', ...}]}
losses: ['extensions-not-carried: from anthropic-messages into openai-responses: tool_choice']
```

机制：`tool_choice` 不在 `anthropic_messages._PASSTHROUGH_KEYS`（`:31-33`）→ 落进 `extensions` → `semantic.extensions_for()`（`:101-113`）在 `source_format != wire_format` 时返回 `{}` 并记 `EXTENSIONS_NOT_CARRIED`。

**但同格式那半是假的。** Responses→Responses 时 `source_format == WIRE_FORMAT`，`extensions_for` 原样回放，而新判据仍然会剥掉带日期的声明：

```
=== responses -> responses, dated server tool + tool_choice ===
payload: {'model': 'gpt-5.6-sol', 'input': [], 'tool_choice': {'type': 'web_search_20250305'}}
losses: ['server-tool-not-carried: web_search_20250305 into openai-responses: this endpoint has no such value']
```

`tools` 没了，`tool_choice` 还在，指着一个不存在的工具。这条路径窄（要求入站就是 Responses 格式且用 Anthropic 拼法），而且修复前它本来也会 400，所以**不是回归**；但「没有东西可悬空」这句话是错的，应改为「跨格式路径上没有东西可悬空」。

更值得说的是纪律差异：Anthropic 腿在同一决策点有 `_drop_dangling_choice(payload)`（`src/app/pipeline/subscribers/server_tools.py:267`），spec §3.4 的 `drop_web_search` 分支与 §8.3 也都**必须**要求同步删除指向被剥声明的 `tool_choice`。新代码没有对应物。这也让 §4.3「剥离是完整实现的真子集」这个说法不完全准确：它是真子集**减去 tool_choice 清理**。

### [minor-2] 判据对「未来非日期拼法」的失败方向不安全

`_is_anthropic_server_tool` 认的是 `<family>_<8 位 ASCII 数字>`。它比 spec §3.1 的裸前缀窄得多——窄在正确的方向上（不误伤 `web_search_preview`），但也窄出了一个新的失效模式：**Anthropic 若换一种版本拼法（例如 `web_search_v2`），判据不命中，声明原样透传，复现本次事故**，而且是静默地复现（没有任何 loss、没有任何日志，直到上游 400）。

作者在 docstring 里论证了「读日期能扛住下一个日期版本」，这是对的，但只覆盖了「日期变了」，没覆盖「格式变了」。

**建议的替代判据（不是必须改，供裁决）**：剥离 `web_search_`／`web_fetch_` 前缀下的**一切**，除了端点自己的拼法允许清单 `{"web_search", "web_search_preview", "web_search_preview_2025_03_11"}`。这个清单来自上游 400 自己打印的枚举，加上 §4 记录的「上游回显把 `{"type":"web_search"}` 归一化成 `web_search_preview`」——即上游自己会产出这个值。两个方向的失效代价对比：允许清单过期 → 一个合法的 Responses→Responses 请求被误剥（这条路径在本项目里极少）；日期判据漏配 → 主产品路径整轮 400（就是本次事故）。**允许清单的失败方向更安全。**

### [minor-3] §6.2 的更正成立，但它成立的前提是 §6.1，文档没写出这层依赖

作者主张 spec §3.1 的「`type` 以 `web_search_` 开头」判据「会误伤上游合法值 `web_search_preview` 与 `web_search_preview_2025_03_11`」。

**在作者选定的落点上，这条完全成立**：`to_openai_responses` 是 Anthropic→Responses 与 Responses→Responses **共用**的写出器，裸前缀判据会命中一个合法的 Responses 入站声明。我已用变异复现（见 §2 的分辨力核验）。

**但 spec 在它自己的作用域里并不会遇到这个值**：spec §2 把「声明」定义为「**Anthropic 请求** `tools[]` 中 `type` 以 `web_search_` 开头的条目」，§1 的范围也是「Anthropic Messages 客户端声明」，而 §3.6 把判据放在 `protocols/anthropic_responses.py`——那个文件只接 Anthropic 入站。所以严格讲，**§3.1 不是一条独立的事实错误，它是在 §6.1 的更正（判据必须搬进共享 translator）落地之后才变成错误的**。

这不影响「建议 spec 收紧 §3.1」这个结论，但影响用户读到的因果。建议改述为：「§3.1 的判据在 spec 自己假定的落点上无害；一旦按 §6.1 搬到共享 translator，它就会误伤上游合法值，因此两条更正必须一起提交。」

另附一条限定：`web_search_preview` 「是 `/responses` 接受的合法值」这条，证据是上游 400 的枚举 + §4 记录的上游回显归一化，**没有 200 直发探针**——spec 自己在 §12 P11 把它标成「别名推断未验证」。权重：强，足以据此设计判据；但文档写成「都是 `/responses` 接受的合法值」比证据略绝对，建议标注来源。

### [minor-4] 落点在纯 translator，承载不了能力门，「就是能力门为假的那一支」偏乐观

文档 §4.3：

> 剥离不是白工，它是完整实现的真子集：对应 spec §8.3「路由到 Responses 腿但能力门未通过」的保守分支……完整实现落地时，这段代码是能力门为假的那一支。

行为上确实对应 §8.3（剥离、记 DEGRADE、INFO 日志、不 REJECT）。但**结构上不是**：spec §9.3 的能力门要读「当前 attempt 的路由已确定为 Responses 腿」「resolved model 的 `supported_endpoints`」「配置维护的允许清单」，这些都在 `RequestContext` 上，而 `to_openai_responses(request)` 只拿到一个 `SemanticRequest`（`model` 字段还是入站模型名，`payload` 里那条 `'model': 'claude'` 就是证据）。Anthropic 腿的对应物 `adapt_server_tools(context)` 之所以是订阅者，正是因为它要读 `context.target_format`。

也就是说，完整实现落地时这段代码**大概率要搬到一个 Responses 腿的订阅者里**，而不是原地长出一个能力门。这不是缺陷，是对「真子集」这个措辞的精度修正——用户不应据此以为下一片是纯增量。

### [minor-5] INFO 日志是假阴性唯一的对外出口，却没有任何测试断言它

文档 §3 花了整段论证「为什么日志不能省」（`conversion_losses` 无消费者，日志是运维查明「搜索为什么从不执行」的唯一途径）。我确认了它确实会输出——`logging.py:160` 只设 root level，默认 `INFO`（`settings.py:122`），`:168` 的降噪清单只含 `uvicorn.*`／`httpx`／`httpcore`，没有对本项目 logger 的白名单过滤。

但四个单元测试 + 一个端到端测试**没有一个碰这条日志**。既然它被论证为假阴性的唯一可观测出口，一条 `caplog` 断言（消息里必须出现被剥的 type）成本极低，而且能挡住「日志被顺手降成 DEBUG／措辞被改得搜不到」这类回归。建议补，不阻塞。

### [info] §3 的「唯一的失败」已过期

文档称全量跑有 1 个失败：`tests/unit/test_lifecycle_pidfile.py::test_writing_leaves_no_temporary_behind`，归因于并行会话新增的 `tests/unit/conftest.py`。我复跑该测试：**1 passed**。并行会话已经修了——`tests/unit/conftest.py:16` 的 docstring 现在逐字写着「the pidfile test asserts precisely that, and an earlier version of this fixture broke it」，改用 `tmp_path_factory` 而非 `tmp_path`。归因是对的，状态已过期。交给用户前删掉或标注即可，免得有人去追一个已经不存在的失败。

---

## 2. 我独立复核通过的部分

以下各项**沿用／已确认**，用户可以放心。

### 2.1 §6.1「spec 点名的文件不在产」——已确认，强证据

三条独立事实：

1. `convert_messages_request_to_responses` 在 `src/` 下的唯一调用者是 `src/app/anthropic/client.py:250`（`rg` 全仓 58 处命中，其余全是 `tests/` 与 `docs/`）。
2. `AnthropicClient` 只由 `src/app/upstream/bootstrap.py:145` 构造，而 `bootstrap` 只被 `src/app/server/app_factory.py:38` 引用，`app_factory.create_app` 在 `src/` 下**零调用者**。`routes/anthropic.py` 同理，只挂在 `app_factory.py:24`。
3. `src/app/cli.py:23,144,169` 只构造 `create_pipeline_app(chain)`。

另有一条旁证支持「生产跑的就是这个 Python 项目」：事故日志的行格式 `[FAIL] 13:30:57 H1 400 POST /v1/messages gpt-5.6-sol 226ms` 与我跑测试时看到的本项目请求行格式 `H1/H1 200 anthropic-messages/gpt-model 6ms ↑276B ↓15B` 同源。

**这条更正成立，作者据此建议用户改 spec 是正确的。** 它不是 blocker。

### 2.2 「剥离而不是本地快速失败」——正确，且 spec 自己已经这么裁过

评审提问：「剥离让搜索静默不执行，比本地快速失败更好吗？」

**我的答案是：剥离更好，理由三条，都不依赖作者的论证。**

1. **spec 已经裁决过同一个问题。** §8.3 逐字写着：「路由到 **Responses 腿但能力门未通过**时：**必须**剥离 web search 声明……**不得** `REJECT` 整个请求。理由：与 Anthropic 腿保持同一取舍——剥掉一个能力，好过整轮失败。」本次止血就是「能力门恒为假」的那个形态，行为与 §8.3 逐条对得上。
2. **§9.3 的「假阴性最坏」不是在回答这个问题。** 那段讲的是**能力门清单宁窄勿宽**——在「映射存在」的世界里，选错模型的两类代价不对称。它不是在主张「不能搜就该让整轮失败」。把它读成后者是断章。
3. **本地 400 不恢复任何功能。** 客户端每轮重放同一份声明，本地 400 与上游 400 对用户来说是同一件事：一轮都跑不通。差别只在错误措辞好不好看。剥离至少让每一轮都能得到回答。

### 2.3 这不构成 `ask-if-scope-shrink` 意义上的擅自缩小范围

三条依据：

1. **spec 自己锁着自己的实现门。** §15（文档状态第 15 行）逐字：「**实现前必须先关闭这些项**」，列了 MJ-1／MJ-2／MJ-4／MJ-5／MJ-7／MJ-8 与全部 minor；§14 还有 D2／D3／D5／D7 四个未裁决点。实现 spec 不在授权范围内。
2. **止血落在 spec 自己规定的保守分支上**（§8.3），不是自创的第三种行为。
3. **缺口被记账并上报了**，没有静默切掉——§5 三条、§4 的代价陈述都在。这正是 `no-silently-cut-but-defer` 要的形态。

**但有一条需要补：** 由于 major-1，作者呈给用户的选项集是不完整的。真实的选项至少有三个，用户应该看到第三个：

| 选项 | 用户可见结果 | 成本 | 风险 |
|---|---|---|---|
| A. 本次的剥离（已落地） | 每轮成功，搜索不执行，客户端不知情 | 已付 | 假阴性长期存在 |
| B. 本地 REJECT | 每轮失败，措辞清楚 | 小 | 与事故等价的不可用 |
| **C. 请求侧映射 + 模型允许清单 + 响应侧不动** | **搜索真的执行**，客户端多收一个空 text 块 | 映射约十行（`{"type":"web_search"}` + `user_location`，其余字段必须剥掉否则 400）；允许清单可先硬编码两个实测模型 `gpt-5.5`／`gpt-5.6-sol` | 允许清单之外的 `/responses` 模型（`grok-4.5`／`grok-4.6`／`mai-code-*`）从未探针，无门就映射会把 400 搬到它们身上 |

**C 的那个风险，才是本次不做映射的正确理由，作者没写。** 我的偏好：**本片按 A 合入（今天就止血），紧接着做 C 作为独立小片**——它把假阴性真正消掉，而不是只写在日志里，而且不需要等 spec §5／§6 的 presentation 定稿（那部分现在只影响好看程度，不影响能不能用）。是否要做 C、允许清单硬编码还是走配置键（spec §9.3 说键名须与人写 `config.example.yaml` 对齐，尚未定），请用户裁决。

### 2.4 测试的分辨力——独立复现，两条变异都变红

我没有改仓库任何文件，用两个只活在进程内的 pytest 插件做受控变异（`/tmp/mutate_predicate.py`、`/tmp/mutate_bare_prefix.py`，均通过 `pytest_configure` 替换模块属性）：

- **变异一：谓词恒假**（`_is_anthropic_server_tool = lambda tool: False`）→ `4 failed, 1 passed`。红的是三个单元测试加那个端到端测试；端到端的失败逐字是 `assert b'web_search' not in b'{"model":"gpt-model","input":[{"type":"messag...`，即它确实钉在上游收到的字节上。
- **变异二：退回裸前缀**（`startswith(family)`）→ `1 failed, 3 passed`，红的正是 `test_the_endpoints_own_web_search_spellings_are_left_alone`，失败信息 `Right contains 2 more items, first extra item: {'type': 'web_search_preview'}`。

作者声称的分辨力属实。基线：`tests/unit/test_translation_driver.py` 31 passed；新端到端测试 1 passed。`ruff check` 与 `pyright` 在两个改动源文件上均干净（我复跑确认）。

### 2.5 §5.3「`conversion_losses` 没有消费者」——已确认

全仓 `rg conversion_losses` 只有两个写入点（`src/app/server/handler.py:94` 与 `:285`，后者是 `response_conversion_losses`）与三处文档提及，零读取点。因此「只记 loss 等于没记」的论证成立，补 INFO 日志是必要的绕过。这是缺口而非本片的错。

---

## 3. 给主会话的处置建议

**必须改（交给用户裁决之前）**：

1. 文档 §4 理由 1 与 `_tools_for_upstream` docstring 里对应的那句，按 major-1 的实测结果改写；同时把「真正的理由」——没有能力门，映射会伤及未探针的 `/responses` 模型——补上。
2. 文档 §5.1 删掉「按 spec §13 维持现状」这个免责依据，改成 major-2 的表述：spec 的「现状」指本地 REJECT，生产上的静默透传不在其授权内；并把上游枚举作为证据升格。
3. 文档 §5.2 把「没有东西可悬空」限定到跨格式路径。
4. 文档 §6.2 补上它对 §6.1 的依赖（minor-3）。
5. 文档 §3 删掉已过期的「唯一的失败」段（info）。

**建议改（可与用户一并裁决）**：判据换成「family 前缀 + 端点自有拼法允许清单」（minor-2）；补一条 `caplog` 断言（minor-5）；`§4.3「真子集」` 改述为「行为对应 §8.3 的保守分支，结构上将来需搬到 Responses 腿订阅者」（minor-4）。

**不必改**：代码本身。作为止血它是对的，测试有分辨力，静态检查干净。

**建议作为紧接的独立小片**：其他 typed tool 的本地具名 REJECT（major-2 的后半），以及选项 C 的映射（2.3）。两者互不依赖，可并行。
