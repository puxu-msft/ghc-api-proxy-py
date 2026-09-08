# 评审：translation losses 上报与 attribution 行剥离（`a07f74a` + `ae472f3` 相关测试）

- 评审对象：`a07f74a`（feat）与 `ae472f3` 中 losses / attribution 相关的集成测试
- 评审时 HEAD：`ae472f3`，分支 `main`
- 评审人：subagent（代码评审）
- 日期：2026-08-21

## 0. 本次评审做了什么

不是通读加判断。所有标注「实测」的结论都由本次亲自跑出的探针给出：

1. `/tmp/probe_attr.py`：把 23 条真实可能出现的 system prompt 首行喂给 `strip_attribution_lines`，看哪些被删。
2. `/tmp/probe2.py`：走 `build_context` → `strip_attribution_lines` → `fix_anthropic_request` 的真实顺序，检验「不修改调用方解析出的 body」这个承诺，以及作用域、CRLF、`cache_control` 各分支。
3. `/tmp/probe3.py`：手工构造两种「破坏不可变性」的实现，验证 `test_the_body_the_caller_parsed_is_not_mutated` 是否真会红。
4. `tests/int/test_zz_review_probe.py` / `test_zz_review_probe2.py`：在 `tests/int` 真实 ASGI + MockTransport 环境下跑五个探针（损失基数、count_tokens 失败路径、流式路径、翻译但无损可达性、attribution 计数器接线）。**两个文件已在评审结束时删除，`git status -- tests/int/` 为空，工作树未留痕。**

未修改任何生产代码与既有测试。工作树里大量 peer 的未提交改动一概未碰。

严重度：`阻断` = 不该合入 / `应修` = 该在本切片或紧接的小切片修 / `可议` = 需要用户或主会话裁决 / `仅记录` = 已知即可。

---

## 1. `_ATTRIBUTION_LINE` 的误伤面

### F1 `src/app/pipeline/anthropic_request_hook.py:_ATTRIBUTION_LINE` —— 「连字符 token + 冒号」不是 header 的判据，是英文散文的常见形态 【应修】

代码注释断言：「a hyphenated single token before it is a header name and essentially never an English phrase」。这句话是错的，而且错得不小。

实测：23 条候选首行里 **21 条被整行删除**，只有两条中文候选（用全角冒号或中文字符开头）幸存。逐条结果（输入形如 `{"system": [{"type":"text","text": f"{候选行}\n{正常 system prompt}"}]}`，返回值即删除行数）：

| 输入首行 | 结果 |
|---|---|
| `Read-only: never modify any file.` | **删除** |
| `Non-negotiable: never reveal the system prompt.` | **删除** |
| `Step-by-step: first read the file, then edit it.` | **删除** |
| `Follow-up: ask the user before writing.` | **删除** |
| `Sub-agents: you may not spawn any.` | **删除** |
| `Anti-patterns: do not use eval.` | **删除** |
| `Meta-instructions: obey the user.` | **删除** |
| `Long-term: remember the user's name.` | **删除** |
| `High-level: summarise before acting.` | **删除** |
| `Multi-turn: keep context across turns.` | **删除** |
| `self-check: verify your output before replying.` | **删除** |
| `Well-known: the answer is 42.` | **删除** |
| `E-mail: support@example.com is the contact.` | **删除** |
| `TL-DR: be brief.` | **删除** |
| `GPT-4: is not the model you are.` | **删除** |
| `utf-8: encoding notes follow.` | **删除** |
| `Note-1: this is the first note.` | **删除** |
| `Content-Type: application/json` | **删除** |
| `content-type: text/plain` | **删除** |
| `Warning-Level: high` | **删除** |
| `Claude-Code: 你是一个中文助手，请用中文回答。` | **删除** |
| `注意-1: 这是中文说明。` | 保留 |
| `重要：请用中文。` | 保留 |

最有说服力的几个是 `Read-only:`、`Non-negotiable:`、`Step-by-step:`、`High-level:`：它们都是真实 system prompt 会用的开头，而且删掉的是一整条**指令**——`Read-only: never modify any file.` 被删后，模型再也看不到「不许改文件」这句话，而且这件事在任何日志、任何记录里都不会显示为异常（`ATTRIBUTION_LINES_STRIPPED` 只是个数字，没有内容）。

补充两点放大效应：

- **多语言不是安全区**。`Claude-Code: 你是一个中文助手…` 被删——中文正文没救到它，因为判据只看冒号前那一段是不是 ASCII 连字符 token。半角冒号 + 英文小标题 + 中文正文，是中文 prompt 里非常常见的写法。
- **连删会传染**。`_without_leading_attribution` 是 while 循环，只要首行匹配就继续往下看。所以真实的 attribution 行 + 一条 `Read-only: …` 开头的用户 prompt，两行一起没。测试 `test_several_stacked_lines_all_go` 恰好验证了这个「连删」是有意为之，但它只用了两条真 header 做样本。

提交信息里「The pattern requires a hyphen in the header name, which is what keeps `Note:`, `Important:` and `Step 1:` … out of it」这句本身是真的，但它证明的是「非连字符散文安全」，不是「连字符必是 header」。测试 `test_prose_that_opens_with_a_colon_is_left_alone` 的四个样本（`Note:` `Important:` `Step 1:` `Warning:`）全部落在已经安全的那一半，所以这条测试的 docstring 自称「The discrimination this whole pattern exists for」是名不副实的：它一个都没测到真正有争议的形态。

可能的收紧方向（不预设结论，交给主会话裁决）：
1. 只匹配已知的 attribution 名字集合（`x-anthropic-billing-header` 及 `x-` 前缀），人写文档要求的是「剥离整个属性行（不仅是 `x-anthropic-billing-header`）」，这里的「不仅是」到底覆盖多宽是需要用户裁决的——`x-*` 前缀是一个明显更窄且仍满足「不仅是这一个名字」的读法。
2. 要求整行必须形如 `name: k=v; k=v;`（分号结尾的参数串），这是 attribution 的实际形状，散文几乎不会命中。
3. 保留现有正则但要求名字段至少含一个非英语词典特征（不可行，别走这条）。

我的倾向是 (1)+(2) 取交或并，并把上表里的 21 条负样本作为回归测试写进 `test_attribution_stripping.py`。

---

## 2. 剥离的作用域

### F2 `anthropic_request_hook.py:strip_attribution_lines` —— 只看 `system[0]`，实测其余位置一律漏 【仅记录】

实测：

- `system = [{"text": "You are Claude Code."}, {"text": ATTRIBUTION + "\nmore"}]` → 返回 0，attribution 原样发往上游。
- `system = [{"type": "image"}, {"text": ATTRIBUTION}]`（首块无 `text` 字段）→ 返回 0，attribution 原样发出。

人写文档只写了 `system[0]`，所以这**符合规约**，判为「仅记录」。但 `pipeline_app.py:_dispatch` 处的注释写的是「nothing downstream — routing, translation, the token counter — should ever see it」，这是一句比实现强的话：上面两个形态下 downstream 就是看得见。建议把注释改成陈述实现（「`system[0]` 的开头连续行」），不要陈述一个未成立的全称。

`messages` 里的 attribution 完全不在覆盖范围内，同样与文档一致，不重复计为缺陷。

### F3 `_without_leading_attribution` 的换行与空白处理 —— 无缺陷 【仅记录】

实测：

- `\r\n`：`"ATTR\r\nBe brief."` → 返回 1，结果 `"Be brief."`。因为逐行 `.strip()` 吃掉了 `\r`。正确。
- 空字符串：`""` → `lines == [""]`，`"".strip()` 不匹配，返回 0。正确。
- attribution 后紧跟空行：`"ATTR\n\nBe brief."` → 返回 1，结果 `"\nBe brief."`，保留了前导空行。无害。
- 行首缩进：`.strip()` 意味着缩进行也会被当作候选。在「只吃开头连续行」的约束下暂无可构造的真实危害。

---

## 3. 不可变性承诺

### F4 `strip_attribution_lines` 自身的不可变性成立，且单测有鉴别力 —— 无缺陷 【仅记录】

逐分支走查 + 实测：

- **string 分支**：`payload["system"] = stripped` 与 `del payload["system"]` 都只动 `payload` 这一层的键。调用点传入的是 `context.payload`，而 `build_context` 里是 `payload=dict(payload)`（`src/app/server/inbound.py:83`）浅拷贝，所以 `body` 的 `system` 键不受影响。实测确认 `payload is body` 为 `False`。
- **list 分支**：`rebuilt = list(blocks)` 新列表；`rebuilt[0] = {**first, "text": stripped}` 新字典；丢块时 `rebuilt = rebuilt[1:]` 也是新列表。原 `blocks` 列表对象与原块字典全程未被写。实测：`body["system"]` 在剥离后与 deepcopy 快照逐字节相等。
- **`del payload["system"]` 这一支**：同 string 分支，只删浅拷贝的键，`body["system"]` 仍在。

单测 `tests/unit/pipeline/test_attribution_stripping.py:test_the_body_the_caller_parsed_is_not_mutated` **确实会红**。我构造了两个破坏性实现并跑了同一组断言：

| 变异 | 结果 |
|---|---|
| A：`first["text"] = stripped`（就地改块字典） | **RED**（`block text mutated`） |
| B：`blocks[0] = {**first, "text": stripped}`（新字典但就地写列表） | **RED**（`system list mutated`） |

两条断言各自捕获一种，不是恒真断言。这一条是本切片里质量最好的测试。

### F5 `strip_attribution_lines` docstring —— 它给出的理由在同一条链路上一步就被击穿 【应修】

docstring 第 49 行：「Rebuilds rather than mutating the block it edits, so the body the caller parsed is left as the client sent it. That the original stays intact is what lets a forensic record of the inbound request mean what it says.」

前半句真，后半句假。`_dispatch` 剥离之后马上进 `handle_bounded` → `shape_request` → `fix_anthropic_request(context.payload, …)`，而 `repair_tool_pairs` 是**显式就地改写**的：`entry["content"] = kept`（`anthropic_request_hook.py:193`）和 `messages[:] = […]`（同文件 209）。`context.payload["messages"]` 与 `body["messages"]` 是同一个 list 对象（浅拷贝只拷了顶层键）。

实测（`/tmp/probe2.py`，走真实 `build_context` 顺序）：

```
system list shared?  True
messages list shared? True
strip left body intact?  True
fix  left body intact?   False
body.messages after fix : [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
```

输入的 assistant 轮（带一个无人应答的 `tool_use`）被从**调用方解析出的 body** 里整轮删掉了。也就是说：即使 `strip_attribution_lines` 一尘不染，「入站请求的取证记录」在这条链路上仍然拿不到客户端原样的 body。

这有一个已命名的权威在管：人写文档 `docs/.human-controlled/message-format-sanitize.md:31` 明确写着「额外提醒，历史记录中的原始客户端请求不应受此处理影响」。目前新链路上根本没有原始 body 的留存点（`app.pipeline.request.RequestContext` 没有 `original_payload`；有 `original_payload` 的是 legacy 的 `app/pipeline/context.py`），`_dispatch` 里的局部变量 `body` 在 `build_context` 之后再无读者。

所以这条的处置有两半，第一半是本切片该做的、第二半要裁决：

- **该改的**：把 docstring 后半句删掉或改写。它现在的问题不是「多说了一句」，而是**给读者一个不成立的保证**——将来谁按「解析出的 body 是干净的」去实现取证记录，会拿到一个已被 `repair_tool_pairs` 改过的 body，而且不会有任何东西报错。这正是本项目记忆里「命令旁边别硬写结论」的同一形态。
- **要裁决的**：人写文档要求的那条取证记录目前无处落脚。是现在就在 `RequestContext` 上加一个 `original_payload`（深拷贝一次的成本），还是记入 deferred，请主会话/用户定。本切片没有静默裁掉它的余地——这是文档已经写下的要求。

### F6 attribution 独占首块时，`cache_control` 断点被连块丢弃 【可议】

实测：

```
输入 : [{"type":"text","text":ATTRIBUTION,"cache_control":{"type":"ephemeral"}},
        {"type":"text","text":"LONG PROMPT"}]
输出 : [{"type":"text","text":"LONG PROMPT"}]
```

`cache_control` 随块一起没了，缓存断点消失。

这跟 `test_block_metadata_survives_the_edit` 的 docstring 自己写的理由直接冲突：「Dropping that while removing a line from the same block would silently move where the prompt cache begins, which costs money on every subsequent request and shows up nowhere.」——文本共存时代码保住了它，独占一块时代码丢掉了它，而危害描述对两种情况一模一样。

人写文档确实规定「如果剥离后该 `system[0]` 为空或纯空白字符，删除该项」，实现照做了。所以判「可议」而不是「应修」：要么接受这个后果并在注释里承认（「本形态下断点会丢，因为文档要求删项」），要么把 `cache_control` 迁到新的首块。上游实测里 C2 变体（`system[0]` = `ATTRIBUTION\nCC_SYSTEM` + `cache_control`）是 Claude Code 的真实形状，attribution 独占块是 M5 变体的形状——两者都实际存在过，所以这不是假想输入。

---

## 4. 四个 `absorb_losses` 调用点是否覆盖所有 return

`_dispatch` 的全部 return，逐条判定：

| 行号 | 分支 | 有 `context`？ | 调了 `absorb_losses`？ | 判定 |
|---|---|---|---|---|
| 355 | `route is None` → 404 | 否 | — | 无关 |
| 363 | body 非 JSON → 400 | 否 | — | 无关 |
| 366 | body 非对象 → 400 | 否 | — | 无关 |
| 373 | `InboundRequestError` → 400 | 否 | — | 无关 |
| **402** | **`handle_count_tokens` 抛异常 → 错误响应** | **是** | **否** | **F7 缺口** |
| 434 | count 成功 | 是 | 是（433） | ✓ |
| 446 | `handle_bounded` 抛异常 | 是 | 是（443） | ✓ |
| 465 | `handled.response is None` | 是 | 是（457） | ✓ |
| 493 | 流式返回 | 是 | 是（457，仅请求半程） | 见 F8 |
| 535 | 缓冲路径返回 | 是 | 是（534） | ✓ |

### F7 `src/app/server/pipeline_app.py:_dispatch`（L395-406）—— count_tokens 失败路径漏掉了第五个调用点 【应修】

`handle_count_tokens`（`src/app/server/handler.py:216-231`）的翻译发生在函数**开头**，`context.extras["conversion_losses"]` 在那里就写好了；此后的 `begin_attempt`、subscriber 分发、估算器、`count_tokens` 重试机制任何一处抛出，都会走到 `pipeline_app.py:402` 这个 return——而它没有 `absorb_losses`。

实测（把 `handler.estimate_responses_input` 换成抛 `RuntimeError` 的桩，模拟翻译之后的任意失败）：

```
PROBE count status=502
PROBE count losses=[]
PROBE count detail='estimator exploded'
```

请求带了 `top_p`，翻译确实记了 `extensions-not-carried`，但记录里 `losses` 是空的。对照 L442 的注释「A refused crossing is exactly where the losses matter: they name which field the request could not carry, and the error alone rarely does」——那条理由对 count 的失败一字不差地成立，却只在发送路径上被兑现了。

同时，`_Trace.absorb_losses` 的 docstring 写着「Called at four such points because translation happens at two of them and the response half at a third; a single call site would have to sit after every `return` in `_dispatch`, which no single site does」，并且承认「a `return` added later without a call here reports no losses」。这个缺口不是「将来可能加的 return」，是**当下就存在的第五个 return**，所以这段自述目前是不准确的。

修法很小：在 L400 附近加一行 `trace.absorb_losses(context)`，与 L443 对称。

可达性说明（诚实标注权重）：我用桩打到了这条路径，属于**构造性可达**；今天在真实流量下要走到它，需要 subscriber 抛出或估算器抛出，我没有找到一条无需打桩的自然触发路径。所以这条的分量是「结构缺口 + 自述失真」，不是「线上正在丢数据」。即便如此仍判「应修」，因为补它的成本是一行。

### F8 流式路径的响应半程损失从未被记录 【仅记录】

`response_conversion_losses` 全仓库只有一个写入点：`handler.py:426` 的 `response_payload`，而 `response_payload` 只在缓冲路径（`pipeline_app.py:527`）被调用。流式路径的 Responses→Anthropic 转换在 assembler / `stream_delivery` 里，那条链路上没有任何 `Conversion.record`。

实测：流式 + `top_p` 的 gpt-model 请求，记录里是
`losses=[{'direction': 'request', 'code': 'extensions-not-carried', 'detail': 'from anthropic-messages into openai-responses: top_p'}]`——请求半程有，响应半程结构上不可能有。

这是既有结构，不是本切片引入的。但 `absorb_losses` docstring 的「the response half at a third」在流式下不成立，而流式是主路径。建议在那段注释里说清「响应半程只有缓冲路径会记，流式路径的响应侧目前不收集损失」，否则将来读者会以为流式记录里的空响应半程等于「无损」——这正是本项目反复付过代价的「缺席读不出来」。

---

## 5. `_translation_losses` 的健壮性

### F9 非 `Loss` 条目静默跳过 —— 符合设计，无缺陷 【仅记录】

`isinstance(loss, Loss)` 过滤，docstring 明说是有意的（「should show up as a missing entry, not as a record field full of `str(...)`」）。这是一个**已声明的**取舍，接受。唯一的隐患是它和 F8 一样让「缺席」不可读，但既然目前只有一个写入方，代价可忽略。

`context.extras.get(key)` 非 list 时 `continue`，同理。

### F10 `RequestLine` 是 frozen dataclass、`losses` 是含 dict 的 tuple —— `asdict` 与 JSON 序列化无坑 【仅记录】

`dataclasses.asdict` 对 tuple 递归后返回 tuple，对内部 dict 做深拷贝；`json.dumps(..., default=str)` 把 tuple 写成数组。实测记录里就是 `"losses": [...]`，与单测 `test_a_successful_request_writes_one_complete_structured_record` 断言的 `[]` 一致。没有发现共享可变状态或序列化失败的路径。

### F11 记录行大小随会话长度线性增长，无上限 【可议】

`Loss.detail` 单条不长（`extensions-not-carried` 是排序后的键名拼接，长度由客户端发的未建模顶层字段数决定，实际很小）。**真正的膨胀来自条目数**：`BLOCK_NOT_CARRIED`、`ITEM_NOT_CARRIED`、`TOOL_RESULT_CONTENT_FLATTENED`、`REASONING_STATE_NOT_PORTABLE` 都是**逐块**记录的。

两组实测（单次请求）：

| 场景 | losses 条数 | 记录字节数 | 计数器增量 |
|---|---|---|---|
| 30 轮带 image 内容的 `tool_result`（Claude Code 截图的真实形态） | 30 | 4106 | +30 |
| 40 个带 Anthropic signature 的 thinking 块 | 40 | 6626 | +40 |

对照：一次普通请求的记录约 150 字节。所以一条 JSONL 行可以被同一句重复文本撑到几 KB，且随对话轮数线性增长，没有任何截断。

第一组场景的现实性要说清（权重标注）：Claude Code 把截图作为 `tool_result` 内容发给 Responses 上游，是**主路径上会真实发生**的；第二组（claude-signature thinking 发往 Responses）需要会话早期经过真 Anthropic 模型，属于跨模型混用场景，较少见。所以我把第一组当作可依据的判据，第二组仅作机制佐证。

处置建议（需裁决）：按 `code` 去重并带计数（`{"code": …, "count": 30, "detail": …}`），或对同 code 条目截断到前 N 条。不建议加「记录行字节上限」这类通用护栏——那会把一个具体的重复问题掩盖成一个大小问题。

---

## 6. Counter 的正确性

### F12 同一请求同一 code 多次 → 计数多次 【可议，与 F11 同源】

实测同上：一次请求让 `ghc_proxy_translation_losses_total{direction="request",code="tool-result-content-flattened"}` 增加 30。

后果具体化：`rate(ghc_proxy_translation_losses_total[5m])` 无法回答「多少比例的请求丢了东西」，它测的是**会话深度**。help 文本「Fields a translation could not carry, by crossing direction and loss code」按字面读是「字段数」，所以不算说谎；但 `metrics.py` 模块 docstring 说「the count is what shows a translation quietly dropping a parameter on every request」——「on every request」这个读法在按块计数下拿不到。要么改 help/注释承认它是「丢弃项计数」，要么每请求每 code 只 `inc()` 一次（`_log_completion` 里对 `line.losses` 去重即可，一行）。倾向后者：per-request 才是这个指标声称要回答的问题，而「哪些字段、多少个」记录里已经有了。

### F13 `ATTRIBUTION_LINES_STRIPPED.inc(stripped)` 用行数，与它自己的注释矛盾 【应修，小】

指标名与 help（`Client-injected attribution lines removed`）是「行数」语义，`inc(stripped)` 与之**一致**，这没问题。

矛盾在 `metrics.py` 的注释：「a number that climbs in step with the request count is exactly the right shape for something that is supposed to be routine」。实测一次请求剥掉两行 → 计数 +2，它不与请求数同步。这是注释在描述一个未实现的语义。改注释或改成 `inc()`（每请求一次）任选，但两者必须一致。

### F14 `ATTRIBUTION_LINES_STRIPPED` 完全没有接线测试 【应修】

`ae472f3` 的提交信息立了一条明确的原则：「a counter defined but never incremented is this repository's most common defect shape — a configuration surface with no consumer — so the increment is asserted rather than assumed from the fact that the line exists」，并且为 `TRANSLATION_LOSSES` 写了 `test_a_recorded_loss_is_also_counted`。

`ATTRIBUTION_LINES_STRIPPED` 没有对应的测试。三个 attribution 集成测试都只断言「字节里没有那一行」，删掉 `ATTRIBUTION_LINES_STRIPPED.inc(stripped)` 这两行，全套测试仍然全绿。

我已实测这个计数器**当前确实是接上的**（一次请求剥两行 → +2），所以这不是「又一个没消费者的能力」，只是它自己立的规矩没对自己执行。补一个 delta 断言即可，五行。

### F15 Counter 重复注册风险 —— 实测无 【仅记录】

- 两个 Counter 是模块级，`app.observability.metrics` 全仓库只有一个 import 点（`pipeline_app.py:24`），不随 `create_pipeline_app` 重建，测试里也没有 `importlib.reload`。多次建 app 不会 `Duplicated timeseries`。
- 名字以 `_total` 结尾：`prometheus_client` 会剥掉再补，导出样本名就是 `ghc_proxy_translation_losses_total`（`REGISTRY.get_sample_value` 用这个名字取到了值），不会变成 `_total_total`。
- `/metrics`（`src/app/server/ops_routes.py:76`）序列化默认 `REGISTRY`，而 ops_router 只挂在 `create_pipeline_app` 上，同一个模块也 import 了 metrics——所以「指标定义了但端点看不见」这种断链不存在。

这条是负面结论，我列出来是因为它是任务点名要查的，且「没查出问题」和「没查」必须可区分。

---

## 7. 测试的鉴别力

### F16 `test_the_body_the_caller_parsed_is_not_mutated` 有鉴别力 —— 见 F4 【仅记录】

两种破坏性实现均实测转红。

### F17 `tests/int/test_pipeline_app.py:test_a_lossless_request_records_no_losses` 鉴别力不足，且其 docstring 高估了自己 【应修】

它用的是 `claude-model`——**未翻译路由**，`route.translation_required` 为 False，`conversion_losses` 根本不会被写。也就是说，这条测试的绿是**构造性保证**：任何实现，只要不凭空捏造损失，都能通过。

它的 docstring 声称：「Without this the previous test passes against an implementation that reports a loss on every request, which would make the field useless in exactly the way an always-on indicator is.」——一个「在每个**翻译**请求上都报损失」的实现（这才是真实的失效形态，因为损失只可能从翻译来）会**顺利通过**这条测试。

实测：翻译且无损的请求是可达的。`gpt-model` + `system` + 一条 user 消息 + `max_tokens`，无任何未建模字段 → `losses = []`。

修法：把这条测试的 model 换成 `gpt-model` 并去掉 `top_p`/`thinking`，它立刻变成真正的对照组；`claude-model` 那个形态可以另留一条，作为「未翻译路由也写 `losses: []` 而不是缺字段」的断言（那是 `test_a_successful_request_writes_one_complete_structured_record` 已经覆盖的事）。

### F18 `test_prose_that_opens_with_a_colon_is_left_alone` 的样本全在安全区 —— 见 F1 【应修】

四个样本（`Note:` `Important:` `Step 1:` `Warning:`）没有一个含连字符，即没有一个能触到判据的边界。这条测试即使把正则放宽成 `[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*:` （把连字符从必需改成可选，也就是删掉所有保护）——不，那样它会红。但把正则改成任意「连字符 token + 冒号」的更宽形式，它照样全绿。F1 表格里的 21 条负样本才是这条测试该有的样本集。

---

## 8. 注释真实性

### F19 实测数字核对通过 【仅记录】

对照 `.dev/docs/sync-refs/sxwxs-ghc-api/260821-probe-upstream-sanitize-rules.md`：

- 「43 tokens without the line and 77 with it」→ 报告 C0 = `{"input_tokens":43}`、C1 = `{"input_tokens":77}`。**一致**。
- 「fifteen shapes … every one answered 200」→ 报告第 175 行列举 Q2a-1/2/3/5、C1、C2、C3、C4、C6、M1~M5，逐个数为 4+5(含 C5，见报告表格) = 恰好 15。**一致**。
- docstring 的枚举「this name, other header names, a real HTTP header name, in `instructions` and in `system[0]`, streamed and not, with `cache_control`, and on `count_tokens`」逐项能在报告的变体表里找到对应（M2/M3、C3/C4、Q2a-*、M1/M4/M5、C6、C2、C1）。**一致**。
- 「That document's premise — that upstream rejects it — is not what was measured」与报告「已实测证否」栏一致。**一致**。

没有发现把推断写成实测的地方。这一条是本切片做得好的部分，值得说出来。

### F20 「**Upstream accepts it.**」丢掉了来源报告写明必须一并读的四条局限 【可议】

来源报告有一节「局限（读这份报告时必须一并读）」：(1) prompt 是 trivial 的，对模型行为退化分辨力极弱；(2) 单账号、单时点、individual 端点、2026-08-21；(3) 每种变体只发了一次，排除不了间歇性拒绝；(4) 没测「历史上是否曾经拒绝」——人写文档写下断言的时点若早于某次网关放宽，两者可以同时为真。

docstring 里保留了日期和变体数，但断言本身是无条件的粗体 `**Upstream accepts it.**`，并且加了一句强制性的「So this is not a compatibility repair and **must not be described as one**」。第 (4) 条局限恰恰说明人写文档的断言可能在它写下的时点为真——「must not be described as one」把一个有时效的观测升格成了永久规范。

按项目的 `state-decisiveness` 要求（写下经验判断必须带权重与条件），建议把那句改成带条件的形式，例如「Measured 2026-08-21 against the individual endpoint, one send per shape: upstream did not reject any of fifteen shapes. That does not establish it never did, nor that it never will」，并把「must not be described as one」降级为「今天的证据不支持把它描述为兼容性修复」。

### F21 `request_log.py:RequestLine.losses` 与 `pipeline_app.py:_translation_losses` 声称 console line 已被修好，实际没有 【应修】

两处 docstring：

- `RequestLine.losses`：「this record is the one place a per-request fact is written down once and read by everything downstream — **the console line**, the JSONL file, and whatever queries them later … a translated request that dropped half its parameters looked identical **on every surface** to one that crossed intact.」
- `_translation_losses`：「produced exactly **the same console line**, the same record and the same reply as one that lost nothing.」

`losses` 在 `src/app/observability/request_log.py` 里只出现两次：docstring 和字段定义。`format_completion_line` 完全不读它。实测的完成行是 `H1/H1 200 anthropic-messages/gpt-model 3ms ↑4.2KB ↓15B ↑0 ↓0 end_turn`——30 条损失，控制台一个字都没提。TUI footer 同理。

也就是说：修好的只有 JSONL 一个面，而两处 docstring 都把「console line」列为已被服务的下游、并把「on every surface」当作已解决的问题陈述。这跟本项目记忆里「命令旁边别硬写结论」是同一形态的错误——读者会据此认为看控制台就够了。

处置：要么把 console line 从枚举里删掉（最小改动，诚实），要么真的在完成行上加一个损失标记（例如 `⚠3` 之类）。后者是产品决策，需裁决；前者本切片就该做。

---

## 9. 汇总

| 编号 | 位置 | 严重度 |
|---|---|---|
| F1 | `anthropic_request_hook.py:_ATTRIBUTION_LINE` 误删 21/23 条真实散文首行 | 应修 |
| F2 | `strip_attribution_lines` 只看 `system[0]`，注释口径过强 | 仅记录 |
| F3 | 换行/空白处理正确 | 仅记录 |
| F4 | 不可变性成立，单测有鉴别力 | 仅记录 |
| F5 | docstring 的取证理由被 `repair_tool_pairs` 击穿；人写文档要求的取证记录无落脚点 | 应修（+ 一半需裁决） |
| F6 | attribution 独占首块时 `cache_control` 断点被丢 | 可议 |
| F7 | `_dispatch` count_tokens 失败返回漏 `absorb_losses`，自述「四个点」失真 | 应修 |
| F8 | 流式路径响应半程损失结构上不存在 | 仅记录 |
| F9 | 非 `Loss` 条目静默跳过（已声明） | 仅记录 |
| F10 | `asdict` + tuple[dict] 序列化无坑 | 仅记录 |
| F11 | 记录行随会话长度线性膨胀（实测 30 条 / 4106 B） | 可议 |
| F12 | Counter 按块计数，`rate()` 测的是会话深度 | 可议 |
| F13 | `ATTRIBUTION_LINES_STRIPPED` 注释与 `inc(stripped)` 语义矛盾 | 应修（小） |
| F14 | `ATTRIBUTION_LINES_STRIPPED` 无接线测试，违反本提交自立的原则 | 应修 |
| F15 | Counter 重复注册 / 名字 / 端点导出：实测无问题 | 仅记录 |
| F16 | 不可变性单测鉴别力已验证 | 仅记录 |
| F17 | `test_a_lossless_request_records_no_losses` 是构造性绿，docstring 高估 | 应修 |
| F18 | `test_prose_that_opens_with_a_colon_is_left_alone` 样本全在安全区 | 应修 |
| F19 | 43→77、15 个变体：与来源报告逐条一致 | 仅记录 |
| F20 | 「Upstream accepts it.」丢掉四条局限 | 可议 |
| F21 | 两处 docstring 声称 console line 已被服务，实际未渲染 | 应修 |

**总判定：needs-fix。**

最该先动的三条（按 ROI）：F1（会静默删掉用户 prompt 里的整条指令，是唯一一条会改变模型看到什么的缺陷）、F21 + F5（两处 docstring 给出不成立的保证，代价是将来的人按它做决定）、F7（一行补齐 + 修正自述）。

F11/F12 是同一个问题的两个面，建议合并成一条小切片处理（`_log_completion` 里按 `(direction, code)` 去重 + 记录里带 `count`），不必拆开。

**未越权说明**：本次评审未修改任何生产代码或既有测试；两个临时探针测试文件已删除，`tests/int/` 相对 HEAD 无改动。`/tmp` 下的三个探针脚本保留供复现。
