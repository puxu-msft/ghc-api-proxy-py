# 独立评审：采纳提交 `3193880` 与上游探针 `exp/260820-empty-text-probe/`

**评审对象**：两件互相独立的产物，分别给判定。
**评审基线**：以 `3193880` 的 Git object 为被评审源码（工作树里同伴的未提交改动不计入）。探针只读脚本与 `raw/` 里已落盘的响应，**没有重跑探针，没有发出任何上游请求**。
**证据强度**：足以据此处理。第一部分的关键事实（`_render_results` 无空串分支、lookahead 变异只被新增用例逮到）是我自己读源码 + 在 `/tmp` 隔离副本上做受控变异实测得到的一手结论；第二部分的关键事实（E1–E5 共用同一次 token 交换与同一套 header、四个 200 都带 usage 与真实输出、翻译产物与探针形态逐字一致）是读脚本、读 `raw/` 与顺翻译链核对得到的一手结论。

---

## 判定汇总

| 部分 | blocker | 应改 | 建议 | 不同意但可接受 |
|---|---|---|---|---|
| 一、提交 `3193880` | **0** | 3 | 3 | 0 |
| 二、探针方法论 | **0** | 2 | 4 | 0 |

两部分都**没有 blocker**。第一部分的采纳在它动到的三个文件里是忠实的、新写下的理由经核实**属实**；两条「应改」都是同一个问题的两处遗留：被撤回的旧理由还活在**另外两处复述**里。第二部分的探针方法**站得住**，阳性对照是真对照，四个 200 是真处理；「应改」在文档层面——`FINDINGS.md` 的「意味着」一节比裁决晚了十分钟就过时了，「边界」一节有一条与自己的证据自相矛盾。

---

# 第一部分：提交 `3193880`

## 1. 采纳是否忠实

上一轮报告（`docs/tmp/260820-review-blank-text-subscriber.md`）三条发现，逐条对照：

| 上一轮发现 | 采纳情况 | 判定 |
|---|---|---|
| 应改：顺序理由不实（`__init__.py:14` 称 server-tool pass 会产生空白 text） | 已撤回该因果，改写为「无数据依赖 + 末位是约定」。上一轮给了两个候选写法（面向未来的约定 / 如实写无依赖），提交把两者都写了，没有超出建议范围 | **忠实**，无过度采纳 |
| 建议：补 lookahead 边界测试 | 新增 4 个参数化用例；我实测确认它们真的守住了 lookahead（见 §4） | **忠实** |
| 不同意但可接受：全空 message 理由过强 | 行为未改（上一轮明确说「无需因此改行为」）；注释与 warning 均已收窄；模块开头也按建议补了「一个例外」的说明（`blank_text.py:5`） | **忠实**，无过度采纳 |

**没有过度采纳**：整个 diff 只动了注释、模块文档与测试，`src/` 里没有一行可执行语句变化（`git show 3193880 --stat` 与逐行 diff 核对）。上一轮明确要求不改行为的地方，行为确实没改。

### 应改 1：被撤回的旧理由还活在测试文档字符串里

- 位置：`tests/unit/test_blank_text_blocks.py:89`。
- 事实：该行逐字保留了被本次提交撤回的因果——「A turn is not a field that can be dropped for saying nothing: the rest of the history is paired against it by position, and a `tool_result` names a `tool_use` in the turn before.」而 `src/app/pipeline/subscribers/blank_text.py:109` 已经把同一件事改写成「Dropping the turn is not obviously safe rather than known to be unsafe … neither consequence has been measured against this upstream」。
- 为什么算漏采纳而不是我在扩大范围：上一轮那条发现的位置栏写的就是「`blank_text.py:109-112`；**对应测试 `tests/unit/test_blank_text_blocks.py:81-90`**」，测试文档字符串在被点名的范围内。
- 影响：同一事实在两处给出强弱不同的两种说法，且**更强的那个说法留在了测试里**——测试文档字符串恰恰是后来者用来理解「为什么这里必须是这个行为」的地方。按 `one-authority-allows-contextual-restatement`，复述必须随权威源一起改。
- 建议处理：把 `:89` 的第一句换成与 `blank_text.py:109` 同强度的表述（「没有一种改写被测得既合法又等义」），`content: []` 那半句可以保留（见下面「建议 1」对它的出处修正）。

### 应改 2：被撤回的旧理由还活在 live 文档里

- 位置：`docs/2604-rewrite/hooks-system.md:100`。
- 事实：该表格行写着「排在后面是因为上一条会把 server-tool 轮次摊平成文本，**可能产出这一条要删的东西**」——这正是 `3193880` 判定为不实并从 `__init__.py:14` 删掉的那句话，中文版原封不动地活着。
- 为什么它比测试那处更要紧：`docs/2604-rewrite/hooks-system.md` 是 live 文档（最后一次更新是同一串工作的 `be87f59`），而且它自己在 `:102` 明确写着「顺序表与『为什么它排在那里』写在 `src/app/pipeline/subscribers/__init__.py` 的模块文档里」——它自认是复述，权威源改了，复述没跟。一个只读中文文档的维护者会得到与代码相反的结论。
- 建议处理：把该单元格改成与 `__init__.py:14` 一致的说法（「两者无数据依赖；末位是约定：只做删除的 pass 放在改写者之后」）。

### 建议 1：「`content: []` is certainly refused」是本仓唯一没标出处的实测口吻断言

- 位置：`src/app/pipeline/subscribers/blank_text.py:109`；同一断言的另一处在 `tests/unit/test_blank_text_blocks.py:89`、`:143`。
- 事实：这句话用了 `certainly`，而同一句话的后半段特意声明「dropping the turn … neither consequence **has been measured** against this upstream」。两个半句用了两套证据标准。本仓对 `content: []` 的实际证据链是：`docs/tmp/260820-empty-text-block-copilot-api-js.md:472` 明写「我没有验证 Copilot 的 `/v1/messages` 上游对 `content: []` 的实际拒绝行为——那需要真实调用。参考实现有两条注释断言它会 400，**我采信但标为二手**」。而 `exp/260820-empty-text-probe/` 的五个探针里**没有一个测 `content: []`**。
- 判定强度：这条断言应从「实测」降级为「二手，来自参考实现的两处注释 + Anthropic 公开契约的一般行为」。它**足以支撑当前的保守选择**（不去造一个没测过的 body），但不足以写成 `certainly`。补充一条我的记忆而非本仓证据、请勿据此改代码：Anthropic 官方 API 对空 content 的报错措辞里带「except for the optional final assistant message」这一例外，若属实则 `certainly` 连字面都不成立。
- 建议处理：把 `certainly refused` 改成带出处的写法（「参考实现两处注释断言会被拒，本项目未自测」）。**不建议**为此补一次探针：它要真实配额，而结论方向不会变。

### 建议 2：「Neither reads what the other writes」这一句字面不成立

- 位置：`src/app/pipeline/subscribers/__init__.py:14`。
- 事实：blank-text pass 读的正是 server-tool pass 写过的对象——`server_tools.py:234` 执行 `entry["content"] = rebuilt` 改写 message 的 content 列表，`blank_text.py:98-102` 随后读的就是 `entry.get("content")`。所以「谁也不读对方写的东西」是假的；真正成立的是紧随其后的那半句——**它写出来的东西没有一个能触发这一条的规则**。
- 为什么值得改：这次提交的全部目的就是「说出实际为真的东西」，而新写的第一句本身又是一个字面为假的全称。它不影响顺序结论，但复现了被修正的那个毛病的形状。
- 建议处理：改成「它确实会读到那个 pass 改写过的 content，但那个 pass 写出的每个 text block 都带 `[family]` 前缀，永远不空，所以触发不了这一条」。

### 建议 3：表格「goes before/after」列声明了一个代码里没有表达的约束

- 位置：`src/app/pipeline/subscribers/__init__.py:14`（列值 `after builtin:server-tool-capability`）对 `:35-44`（注册处）。
- 事实：`SubscriberRegistry.subscribe` 支持 `before=` / `after=` 参数（`src/app/pipeline/events.py:41-42`），而两个内置订阅者都没有传；实际顺序来自注册先后，锁它的是 `tests/unit/test_builtin_subscribers.py:26` 的元组。
- 判定：**不建议**去补 `after=`——那会与新写的「Nothing forces it」自相矛盾。建议反过来改列值：写成「registered last, by convention」，让这一列不再声称一个机器约束。元组锁已经能让第三个订阅者插进来时红掉，这个约定有执行面，不必再加。

## 2. 新理由本身是否属实（我自己读了 `server_tools.py`）

**属实。逐点核实如下。**

- `_as_text` 只有两个调用点：`server_tools.py:196` 与 `:204`。
- `:196` 传入 `f"[{family}]{_call_subject(entry.get('input'))}"`。`family` 来自 `_family()`（`:83-88`），只可能是 `"web_search"` 或 `"web_fetch"`，不可能为空串——`_flatten_history_block` 在 `:193-195` 与 `:201-203` 对 `family is None` 都直接 `return None`。所以**即使 `_call_subject` 返回空串**（`:154` 非 dict、`:160` 无 query/url 或全为空白，两条 return `""` 的路径我都读了），文本也至少是 `"[web_search]"`——非空，且含非空白字符。
- `:204` 传入 `_render_results(...)`（`:129-143`），它的每一条 return 我都读了：`:136` `f"[{family} failed: {failure}]"` 或 `f"[{family} failed]"`；`:142` `f"[{family} results omitted]"`；`:143` `"\n".join([f"[{family} results]", *lines])`。函数体没有第四条出口，**没有任何分支返回空串或纯空白串**。
- `_as_text` 自身（`:163-172`）只是把这个 text 装进 `{"type": "text", "text": text}` 并可选带上 `cache_control`，不会把 text 变空。
- 因此 `__init__.py:14` 的「every text block it produces is generated with a `[family]` prefix and so is never blank」为真，提交信息里那句「`_render_results` has no branch returning an empty string」也为真。
- 「that pass edits `tools`, `tool_choice` and server-tool history blocks」也为真（`_strip_declarations`、`_drop_dangling_choice`、`_flatten_history`，无其它写入面）。
- 唯一不实的是「Neither reads what the other writes」的字面，见上面「建议 2」。

## 3. 收窄后的全空 message 理由是否仍有过强之处

`blank_text.py:109-112` 与 `:5` 现在的分寸**基本正确**：`Dropping the turn is not obviously safe rather than known to be unsafe`、`neither consequence has been measured against this upstream`、`With nothing measured to replace it` 三处都把「未测」写在了明面上，warning 文案（`:111`）也从断言后果改成了断言「不知道有等义改写」，这正是上一轮要求的收窄。

仍然过强的只有一处，就是「建议 1」的 `certainly refused`。另有两处措辞值得注意，但我判定**可接受、不必改**：

- `it moves every later turn's position` —— 若全空轮次是最后一轮，删它并不移动任何后续轮次。这个全称字面不严谨，但它服务的结论是「有未测后果」，方向正确，且随后立刻用「neither consequence has been measured」限定了。
- `which is at least the client's own error rather than one this chain invented` —— 这是价值判断而非事实断言，写成这样没有问题。

## 4. 新增参数化测试的分辨力（受控变异实测）

方法：把 `3193880` 用 `git archive` 解到 `/tmp/rev3193880`（**没有动仓库**），用仓库 venv 的 Python 跑 pytest；每次只改 `_without_blank_text` 的那一行判据，跑完恢复并与 `3193880` 的 blob 逐字比对确认已还原（`diff` 报 IDENTICAL）。基线：该文件 17 passed。

| 变异 | 判据改成 | 逮到它的用例 |
|---|---|---|
| M1 去掉 lookahead | `if kept and _is_thinking(kept[-1]):` | `trailing`、`leading-middle-trailing`（**全量 1335 个测试里只有这两个红**，其余 1333 passed / 3 skipped，耗时 118s） |
| M2 去掉前项判据 | `if _is_thinking(following):` | `run-of-two`、`leading`、`leading-middle-trailing` |
| M3 对称回看、不靠 `kept[-1]` 阻断 | 用 `reversed(content[:index])` 找前一个非空白块 | **仅** `run-of-two` |
| M4 去掉 `kept and` 空表守卫 | `if _is_thinking(kept[-1]) …` | 8 个测试（含 4 个既有测试）—— 这条本来就有覆盖 |
| M5 把「kept 为空」当成边界 | `if (not kept or _is_thinking(kept[-1])) and …` | `leading`、`leading-middle-trailing` |

结论：

- **提交信息里「Removing the lookahead leaves every other test green」经实测为真**，且是精确的——M1 只红这两个新用例，其余 1333 个全绿。
- `run-of-two`、`trailing` 各自守住了别人守不住的失效面（M3 只被前者逮到；M1 在新用例之外无人逮到）。`leading` 守住 M5 与 M4。**没有恒真用例**：四个用例都能被某个变异打红。
- **`leading-middle-trailing` 是复合用例**：在我构造的全部五个变异里，它从来不是唯一的报红者（M1 与 `trailing` 同时红，M5 与 `leading` 同时红）。它不是恒真、也不是无效，但它没有带来 `leading` + `trailing` 之外的新失效面。

### 建议 4：`expected is None` 这个写法应当直接写成字面量

- 位置：`tests/unit/test_blank_text_blocks.py:217`（参数表里的 `None`）与 `:230-235`（函数体里的替换）。
- **它没有把断言变弱**：实测中它照样报红（M1、M5 都逮到它），最终断言仍是精确的整表相等。
- 但它有两个可读性代价：其一，参数表里三行是字面量、第四行是哨兵 `None`，读者必须跳进函数体才知道第四个用例期望什么；其二——这才是要紧的——它**恰好掩盖了「第四个用例的期望输出与第一个逐字相同」这个事实**，而这正是读者判断它有没有增量所需要的信息（见上面的复合用例结论）。
- 建议处理：把第四行的期望直接写成与第一行相同的字面量列表，删掉函数体里的 `if expected is None` 分支；如果决定保留这个用例，在 docstring 里说明它是首尾中三种形态同处一条 content 的整合形态，而不是一个新的失效面。

---

# 第二部分：探针方法论

## 1. 阳性对照 E5 是否真的构成对照 —— **是，真对照**

顺 `probe.py` 的执行路径核实：

- **同一次 token 交换**：`probe.py:127` 在 `for` 循环**之前**取一次 token，五个 case 共用同一个 `token` 变量。
- **同一个 client / 同一个 base URL**：`probe.py:126` 一个 `httpx.AsyncClient`（timeout 60s）贯穿全程；`probe.py:132-134` 五个 case 都发往 `f"{BASE_URL}{case['path']}"`，`BASE_URL` 是唯一常量 `https://api.githubcopilot.com`（`:30`）。
- **同一套 header 构造**：`probe.py:129` 每个 case 都调 `build_request_headers(token, config, interaction_id=...)`，参数完全相同；E5 唯一的增量是 `:131` 追加 `anthropic-version`，这是该端点必需的协议头，不是另一套鉴权。`build_request_headers`（`src/app/ghc_client/headers.py:19-58`）里 `Authorization: Bearer {token}` 与全部身份头对两条腿一视同仁。
- E5 排在列表最后（`:109-119`），因此它的 400 还顺带证明了凭据到运行结束仍然有效——四个 200 不是「token 过期后的某种降级」。
- E5 的响应体（`raw/E5-positive-control-anthropic-leg.json:25-32`）是 `invalid_request_error` + `messages: text content blocks must be non-empty`，与生产日志逐字一致，**并且带 `request_id`**，说明它是端点的 body 校验器给出的判决，不是网关层的通用 400。

**判定：E5 成立**。它证明了「这套凭据 + 这套 header + 这个主机」的路径能够抵达会判断 body 的那一层并被拒绝，因此四个 200 不能被解释成「请求没到判断层」。

### 建议 5：E5 同时改变了两个变量，`FINDINGS.md` 的结论句把拒绝归因给了「API」

- 位置：`FINDINGS.md:25`（「Anthropic Messages API 不接受」）、`:27`。
- 事实：E5 相对 E1–E4 同时换了端点（`/v1/messages`）与模型（`claude-sonnet-5` vs `gpt-5.5`）。这对「探针能否检出拒绝」这个目的是充分的（`FINDINGS.md:27` 的措辞本身也只声称这一点，没有超出）；但结论句把拒绝归因给端点，探针无法把端点与模型两个因素分开。
- 对本次修复无影响：Anthropic 腿在本代理上永远只承载 Claude 模型（`server_tools.py:11` 记录「no Claude model in the catalog advertises `/responses`」），所以「腿」与「模型族」在生产中是同一件事。
- 建议处理：在「边界」里补一句「E5 同时改变端点与模型，只证明探针能检出拒绝，不单独归因」。

## 2. E2/E3/E4 的 200 能支撑多强的结论 —— **能支撑「上游真的处理了」，不只是「接受了 body」**

我读了 `raw/` 里四份响应体的实际内容：

| 探针 | `status` | `usage` | 输出 |
|---|---|---|---|
| E1 | `completed` | input 9 / output 16（reasoning 9）| `reasoning` + `message`，`output_text: "OK"` |
| E2 | `completed` | input **9** / output 16 | 同上，`output_text: "OK"` |
| E3 | `completed` | input **10** / output 16 | 同上，`output_text: "OK"` |
| E4 | `completed` | input 21 / output 5 | `message`，`output_text: "OK"` |

四份都带 `model: gpt-5.5-2026-04-23`、`incomplete_details: null`、完整 usage 与真实生成文本。所以「上游看过并接受了」（`FINDINGS.md:27`）**没有超出证据**。

附带一条 FINDINGS 没用上、但对本次裁决有正面价值的观察（强度：一手，两个样本，够用来说明方向）：E1 与 E2 的 `input_tokens` 都是 9，即那个空 `input_text` part **一个 token 都没有产生**；E3 的空白 part 产生了 1 个。也就是说 Responses 腿不仅不拒，还基本把空 part 当成不存在——这反过来说明「在 Responses 腿上不剥」确实是无损的。可以补进 FINDINGS，不补也不影响结论。

### 应改 3：`FINDINGS.md` 的「这对本项目意味着什么」一节已经过时，且与最终落地的代码相反

- 位置：`exp/260820-empty-text-probe/FINDINGS.md:31-33`。
- 事实：该节第 2、3 条是围绕「无条件剥离」那条裁决写的——「剥离后该 item 整个不再产出」「裁决取消门控没有引入风险」。但探针写于 07:19，而 `4f2d786`（07:29:38）把剥离**重新装上了门控**，只不过换了轴：现在按 `target_format` 判，Responses 腿完全不动（`src/app/pipeline/subscribers/blank_text.py:74-75`）。所以第 2 条描述的两项「修的是别的东西」在当前代码里**根本不会发生**，第 3 条「取消门控」也已不是现状。
- 为什么要紧：`blank_text.py:7` 与 `tests/unit/test_blank_text_blocks.py:5` 都把这个目录当作实测出处指过来。读者顺着指针过来，会读到一份说「门控被取消了」的文档，而代码里门控就在第 74 行。
- 建议处理：**不要改结论与边界两节**（它们仍然正确）。在「意味着」一节顶上加一行日期标注：「本节写于 07:19，反映的是当时那条『无条件剥离』裁决；07:29 的 `4f2d786` 依据本探针把剥离改为按 `target_format` 门控，Responses 腿不再被改写。」

## 3. 形态覆盖是否与生产实际形态对应 —— **一致，我顺翻译链核实过**

生产里出问题的 Anthropic 形态是 `{"type":"text","text":""}`。它到 Responses 腿的完整路径：

1. `src/app/pipeline/translation_driver/anthropic_messages.py:70` 把它读成 `ContentBlock(BlockKind.TEXT, text="")`——**没有在解析期被丢弃或报错**，空串原样保留。
2. `src/app/pipeline/translation_driver/openai_responses.py:274-278`：`BlockKind.TEXT` 按 role 决定 part 类型，`part_type = "output_text" if role == "assistant" else "input_text"`，返回 `{"type": part_type, "text": ""}`。
3. `openai_responses.py:231-256`：这些 part 被收进 `{"type": "message", "role": ..., "content": [...]}`。

于是：

- user 轮的空 text → `{"type":"input_text","text":""}`，与 **E2** 发的（`raw/E2-...json` 的 request 段逐字可见）完全一致。
- assistant 轮 `[text(""), tool_use]` → `message(assistant, [output_text ""])` ＋ 一个独立的 `function_call` item（tool_use 走 `openai_responses.py:281` 那条分支，不进 message content）。所以那个 assistant message item 的 content **只剩一个空 `output_text`**，与 **E4** 发的 `{"type":"message","role":"assistant","content":[{"type":"output_text","text":""}]}` 逐字一致。

**探针发的不是手写近似，就是翻译产物本身。** 这一条我判定为通过。

顺带核实：Anthropic 的 `system` 里的空块**不会**变成空 part，它被 `openai_responses.py:105-123` join 成 `instructions` 字符串，所以探针没有为它设形态是对的（FINDINGS 提到的「instructions 尾部空白填充」是字符串层面的问题，不是 part 层面的）。

### 建议 6：与生产形态相比，两个未覆盖的差异值得写进边界

- E4 的空 assistant 轮后面跟的是一个 user message，而生产形态里它后面跟的是 `function_call` / `function_call_output`。
- 五个探针**都没有携带 `tools`**，而生产请求几乎总是带。
- 两者都不太可能改变 body 校验对空 part 的判断（校验通常是 part 级的），所以我不建议为此再发请求；建议只在「边界」里列出来，让下一个读者知道这两项没测。

## 4. 「边界」一节是否诚实完整 —— **诚实，但有一条与自己的证据矛盾**

已列且属实：只测非流式、只测 `gpt-5.5`、只测「是否接受」不测输出差异、每个探针只发一次不重试。

### 应改 4：「没有测『一条 message 的 content 全是空 part』」与 E4 自相矛盾

- 位置：`FINDINGS.md:37`。
- 事实：E4 发的 assistant message 的 content 就是 `[{"type":"output_text","text":""}]`——**这正是一条 content 全为空 part 的 message**，而且它拿到了 200。所以这句边界声明把一个已经测过的形态列成了未测。
- 方向是保守的（少声称），但它是一份被当作「实测记录」引用的文档里的事实性错误，而且恰好会让读者以为最关键的退化形态没有证据。
- 建议处理：改成准确的版本——「已测：assistant 轮 content 全为空 part（E4，200）。未测：**user 轮**（尤其是末轮）content 全为空 part，以及 `content: []` 这种空数组形态。」后者正是第一部分「建议 1」里那条二手断言所在的位置，两处可以互相指认。

### 建议 7：结论句应带上模型与模式限定，因为被引用出去的正是这一句

- 位置：`FINDINGS.md:25`；引用它的是 `src/app/pipeline/subscribers/blank_text.py:7` 与 `tests/unit/test_blank_text_blocks.py:5`。
- 事实：结论句写的是「GHC 的 Responses API 接受……」，限定（gpt-5.5、非流式）只在两节之外的「边界」里；而两处复述都没有带限定。
- 判定与降级建议：对 **gpt-5.5、非流式** 保持「强，一手实测，足以行动」；对 Responses 腿上的**其它模型**，这条结论应降级为「合理外推」——理由是 E5 本身就证明了同一台主机上不同端点/模型族的 body 校验判据可以不同，所以「同端点必同判据」不是白拿的前提。实际暴露面很小（Responses 腿不承载 Claude 模型），所以**不需要补测**，只需要把限定写进那一句。

## 5. 探针脚本自身的缺陷

先说结论：**没有会让结果失真的缺陷。** 逐条核对用户点名的几类：

- **重试**：没有任何重试逻辑，`probe.py:132` 一次 `post` 到底，与 `:11` 的自述一致。✅
- **把失败当成功**：五个 case 都直接记录 `response.status_code`（`:142`），探针请求上**没有** `raise_for_status`，所以非 2xx 会被如实落盘而不是抛掉；`raise_for_status` 只用在 token 交换（`:58`），那是正确的位置——凭据换不到就该整轮中止而不是产出一排 401。✅
- **脱敏误伤请求体**：`scrub()` 只作用于响应（`:137`），请求体按原样落盘（`:142` 的 `"request": case["body"]`）。请求体里没有任何凭据（token 只在 header 里，而 header 根本不落盘），所以这个选择既保真又无泄露。`REDACT_FIELDS` 是精确 key 匹配，`raw/` 里每份响应各有且仅有一处 `REDACTED`（`safety_identifier`），响应的其余结构完整可读。✅
- **超时**：统一 60s，非流式 + `max_output_tokens: 32`，不会把慢响应误判成失败。✅

以下两条是**建议**，不影响本次结论：

### 建议 8：传输层失败会中断全轮，而 docstring 说「a failure is recorded」

- 位置：`probe.py:11` 对 `:132-149`。
- 事实：只有 HTTP 层面的失败会被记录；`httpx` 的超时/连接异常会从 `main()` 里抛出，中断循环，已跑过的 case 留在盘上、未跑的（**包括排在最后的 E5**）没有文件。本次没有踩到（五份文件齐全），但如果踩到，盘上会留下一组没有阳性对照的 200——恰好是 `:9` 警告的那种不可读状态。
- 建议处理：要么把 `:11` 的措辞改成「HTTP 层的失败被记录」，要么把 `post` 包进 `try` 并把异常写成一条 `status: "transport-error"` 的记录。

### 建议 9：`raw/*.json` 其实不是合法 JSON

- 位置：`probe.py:140-148` 写的是「header 对象 + 空行 + 响应体」两个拼接的 JSON 文档。
- 人读没问题，机器复读要用 `raw_decode` 分两次解（我就是这么读的）。若以后想把它当 fixture 或做批量比对，建议改成一个对象 `{"why":…, "request":…, "status":…, "response":…}`。**不必为此重跑探针**，现有文件照旧可读。
- 另：响应 header 完全没落盘（E5 的 `request_id` 只是碰巧在 body 里），以后要拿 `x-request-id` 找上游侧日志就没有依据。同样只是建议。

---

## 附：本次评审用到的隔离副本

`/tmp/rev3193880` 是 `git archive 3193880` 的一次性解包，变异实验全部发生在那里，结束时已还原并与 `3193880` 的 blob 逐字比对确认一致。仓库工作树全程未被写入（本报告文件除外）。该目录可随时 `rm -rf` 删除。
