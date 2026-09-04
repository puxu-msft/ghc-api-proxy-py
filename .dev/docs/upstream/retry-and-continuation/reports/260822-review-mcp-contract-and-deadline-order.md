# 评审：MCP 工具调用契约一节 + 提交 `027698f`（客户端时限次序）

- **日期**：2026-08-22
- **评审对象**：
  1. `.dev/docs/upstream/retry-and-continuation/README.md` 第 50–76 行「## 本仓实际发出的 MCP 工具调用（给改 MCP server 那一侧看）」（**未提交**，工作树状态）
  2. 提交 `027698f1adac0d24e91e2aeeeb466c0b09239c9d`「fix: say which clock a finished turn loses to, and pin it」
- **仓库状态**：`HEAD = 027698f`；`src/app/pipeline/delivery/stream.py` 与 `tests/unit/pipeline/delivery/test_stream_delivery.py` 在评审全程相对 HEAD 干净（评审结束时 sha256 逐字复核通过）
- **结论**：`needs-fix`（blocker 0，major 2，minor 5，确认无误 8）
- **派发时要求载入的 `my-skills:as-reviewer` 技能在本环境不存在**（`Skill` 返回 `Unknown skill`，`~/.claude/skills/` 下无该目录）。改用 `verifying-authoritative-claims` 与 `trusting-a-green-result` 执行。这一条影响的是方法来源，不影响下面任何一条结论的证据。

## 证据等级约定

- **一手实测**：本次评审自己跑出来的、带正样本对照的结果
- **代码事实**：直读当前 checkout 的源码与调用点穷举
- **推断**：由上述两者推出，但没有独立 oracle 复核

## 摘要表

| # | 位置 | 判定 | 分级 | 证据等级 |
|---|---|---|---|---|
| F1 | 发出的 JSON 形状（四个键） | 正确 | ok | 代码事实 + 一手实测 |
| F2 | `num_messages` 来源与非 list 取值 | 正确 | ok | 代码事实 |
| F3 | `category` 非错误分支取值 | 正确，条件写全了 | ok | 一手实测 |
| F4 | `category` 错误分支「四者之一」 | **应收窄为三者**，`internal` 当前不可达 | minor | 代码事实（调用点穷举） |
| F5 | `message` 取值 | 正确 | ok | 代码事实 |
| F6 | 「不会出现 `max_output_tokens`」 | 成立，且比文档说的更强 | ok | **一手实测**（含证伪对照） |
| F7 | 引用的行号与路径 | 一处指向语句首行、路径省略前缀 | minor | 代码事实 |
| F8 | 「只告警不拦截」+ 事件名 | 正确，且与人写文档一致 | ok | 代码事实 + 既有测试 |
| F9 | 缺 `num_messages` 的**判读规则**（`decisions.md` 四.3 仍是待对齐项） | 遗漏 | **major** | 代码事实 |
| F10 | 未给出工具全名的默认值 | 遗漏 | minor | 代码事实 |
| F11 | 工作树里 `config.example.yaml` 把 `max_output_tokens` 写进 `hand_over_stop_reasons`——该值结构上永不匹配 | 冲突 | **major** | **一手实测** |
| F12 | 改夹具是否削弱了那两条测试 | **没有削弱**其名义属性；次序鉴别力被有意移走并由新测试接手 | ok | **一手实测**（两轮受控变异） |
| F13 | 新测试是否单独承担次序 | 是 | ok | **一手实测** |
| F14 | 注释里「The attempt deadline just below」的方位描述 | 会误导 | minor | 代码事实 |
| F15 | `deferred.md` 第 11 条第 117 行仍写「唯一还要动手的部分」 | 已过期 | minor | 代码事实 |
| F16 | `parse_prompt_limit_error` 只有两个调用点、且一条在未挂载链路 | 成立 | ok | 代码事实 |
| F17 | `/api/tokenization/limits` 标为「暂不支持」 | 成立 | ok | 代码事实 |

---

## 第一件：README「本仓实际发出的 MCP 工具调用」一节

### F1 发出的 JSON 形状 —— 正确（ok，代码事实 + 一手实测）

`src/app/server/pipeline_app.py:580-590` 返回的字典恰好四个键，与文档的 JSON 块逐字对得上，**没有遗漏字段，也没有多写字段**：

```python
return {
    "type": "tool_use",
    "id": f"toolu_{uuid4().hex[:24]}",
    "name": name,
    "input": {
        "num_messages": _client_message_count(inbound_payload),
        "category": category,
        "message": detail,
    },
}
```

`uuid4().hex` 是 32 个 hex 字符，`[:24]` 取前 24 个——文档写的「`toolu_<uuid4 前 24 个 hex 字符>`」精确。

这个形状还有 wire 侧的独立佐证：`tests/int/test_pipeline_app.py:3077-3091` 的 `_handed_back` 是**从交付出去的字节反解**的（`content_block_start` 的 `content_block` 取 `name`/`id`，`input_json_delta` 的 `partial_json` 拼出 `input`），`:3116-3120` 逐字段断言。也就是说文档呈现的是「客户端重组后看到的逻辑块」，而 MCP server 拿到的是 Claude Code 转成 `tools/call` 后的 `arguments`——**文档这样呈现是对的**，不必描述 Anthropic 的分帧细节。

### F2 `num_messages` 的来源与非 list 取值 —— 正确（ok，代码事实）

`_client_message_count`（`pipeline_app.py:379-385`）：

```python
messages = payload.get("messages")
return len(cast(list[Any], messages)) if isinstance(messages, list) else 0
```

「非 list 时为 `0`」精确（缺键也走这一支，因为 `.get` 返回 `None`）。

「客户端入站 body」这个限定也**站得住**，而且这是需要核的关键点：`inbound_payload = deepcopy(context.payload)` 在 `pipeline_app.py:488`，位于 `handle_bounded`（`:490`）**之前**，而翻译是 `handle` 里就地做的（`handler.py:161` `context.payload = translated`）。此前只经过 `build_context`（`inbound.py:83` 仅 `dict(payload)` 浅拷贝，不动 `messages`）与 `strip_attribution_lines`（只动 `system[0]`）。所以这个数确实是客户端自己数的那个数，不是上游请求的长度。文档特意加的「**不是**上游请求的长度」是必要的，保留。

### F3 `category` 在「error is None」分支的取值 —— 正确（ok，一手实测）

代码：`category = stop_reason`（`pipeline_app.py:571`）。而 `stop_reason` 在两条路径上都被 `hand_over_stop_reasons` 门住：

- 流式：`stream.py:366` `terminal.stop_reason in continuation.stop_reasons`，且 `stream.py:412` 再守一次
- 缓冲：`pipeline_app.py:779` `str(payload.get("stop_reason","")) in _hand_over_reasons`

默认值是 `["max_tokens"]`（`src/app/config/schema.py:187`）。所以文档「**默认配置下唯一可能的值是 `max_tokens`**」这个条件化写法是准确的，而且比「一定是 max_tokens」更诚实——一手实测（探针 C）显示，若运维把别的词加进 `hand_over_stop_reasons`，`category` 就会是那个上游原词（实测 `content_filter` 原样透出）。

### F4 `category` 在「error 非 None」分支：应收窄为三者（minor，代码事实）

文档写「`network` / `upstream` / `auth` / `internal` 四者之一（`_CATEGORY_FOR_REASON` 映射 `RetryReason`，映射不中落 `internal`）」。

**上界正确**——`RetryReason` 恰好三个成员（`retry.py:23-26`），三个全在 `_CATEGORY_FOR_REASON` 里（`pipeline_app.py:372-376`），`.get` 默认与 `if reason else` 兜底都指向 `internal`。所以**不可能有第五个值**。

**但 `internal` 这一支当前不可达**，理由是调用点穷举（`rg` 全仓，非推断）：

- `continuation.synthesize` 只在 `stream.py:415` 被调用，即 `_hand_over` 内部
- `_hand_over` 只有两个调用点：`stream.py:346`（带 `error=torn`）与 `stream.py:370`（带 `stop_reason=`，`error` 为 `None`）
- `stream.py:346` 位于 `stream.py:325-327` 之后：`reason = replay.eligible(torn)`；`if replay is None or reason is None: raise torn`
- `replay.eligible` 就是 `_replay_reason` 本身（`pipeline_app.py:724` `eligible=_replay_reason`），而 `_hand_back` 内部再调一次同一个纯函数（`pipeline_app.py:574`），必然给出同一个非 `None` 的答案

所以 error 分支实际只能是 `network` / `upstream` / `auth`。`internal` 是防御性默认，代码注释自己也说明了理由（`pipeline_app.py:575-577`：「a `RetryReason` someone adds later without touching the table would kill the client's turn rather than mislabel one field」）。

**怎么失败**：这不是会让另一个仓实现错的错误——多列一个值是 fail-safe 的（接收端会为它写一个分支，只是永远不进）。但这一节自称「从代码直读」「发出方的实际字节即权威」，而 `decisions.md` 第四节第 1 条也说「`category`、`num_messages`、`message` 的**全部取值**都在那里」。一个从未发出过的值被登记成「实际发出」，会让下一个读者以为线上见过 `internal`，从而在排障时去找一条不存在的历史。

**建议改法**：把括号里的说明改成「三者之一：`network` / `upstream` / `auth`。表里另有一个 `internal` 兜底（`_CATEGORY_FOR_REASON.get` 默认 + `reason` 为 `None` 时），但 `stream.py:325-327` 保证带 error 进入合成前 `reason` 必非 `None`，所以 `internal` 今天不可达；接收端仍建议兜住它，因为它会在有人给 `RetryReason` 加成员而忘了改表时出现」。

### F5 `message` 取值 —— 正确（ok，代码事实）

`detail = stop_reason if error is None else str(error)`（`pipeline_app.py:579`）。文档「非错误时是那个 `stop_reason`（与 `category` 同值）；错误时是 `str(error)`」逐字对上。

### F6 「不会出现 `max_output_tokens`」 —— 成立，而且比文档说的更强（ok，一手实测）

按要求写了探针实跑 `ResponsesAssembler` + 真实的 `stream_delivery` 循环，`ContinuationSupport.synthesize` 换成记录用的替身（`synthesize` 正是 `_hand_back` 在 `pipeline_app.py:718` 被传进去的那个位置）。**探针连同 provenance 一起打印，并带两组对照**：

```
### provenance
ResponsesAssembler from: /home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py
stream_delivery from:    /home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py
mapping line present in _read_terminal source: True

A. upstream reason=max_output_tokens, hand_over={max_tokens}
   terminal.stop_reason = 'max_tokens'
   synthesize called with = [(None, 'max_tokens')]
B. FALSIFIER: same stream, hand_over={max_output_tokens}
   terminal.stop_reason = 'max_tokens'
   synthesize called with = []          # 原始拼法根本活不到这里
C. POSITIVE CONTROL: reason=content_filter (no Anthropic spelling)
   terminal.stop_reason = 'content_filter'
   synthesize called with = [(None, 'content_filter')]   # 证明探针真的能走到 synthesize

### buffered leg (translation_driver.responses._responses_stop_reason)
   reason='max_output_tokens'  -> ('max_tokens', None)
   reason='content_filter'     -> ('content_filter', None)
   reason=''                   -> ('incomplete', None)
```

- **A** 是正向结论：`_hand_back` 拿到的 `stop_reason` 就是 `max_tokens`，于是 `category` 与 `message` 都是 `max_tokens`。
- **C 是防「探针静默不跑」的正样本对照**：换一个上游原词，`synthesize` 照样被调用且原词原样透出——说明 A 里那条路径确实执行过，`[]` 不是探针没跑出来的假象。
- **B 是证伪对照**：把 `hand_over_stop_reasons` 配成 `{"max_output_tokens"}`，`synthesize` 一次都没被调用。这说明「不会出现 `max_output_tokens`」**不只是因为默认配置只列了 `max_tokens`，而是因为归一化在更上游**——原始拼法在到达门之前就已经被换掉了。文档只说了前一半的理由，实测支持一个更强的结论。

**探针只覆盖了什么**：它跑的是 Responses 上游 → Anthropic 客户端这条主产品路径的流式与缓冲两条腿。它**没有**覆盖 Anthropic 直连腿（那条腿的 `stop_reason` 由上游直接给出、本来就是 Anthropic 拼法），也没有覆盖任何真实网络调用（按用户明令未发任何上游请求）。

**顺带的建议**：这一条可以在文档里升级为「不仅默认配置下不会，而且**配置成 `max_output_tokens` 也不会生效**」——见 F11，这句话马上就要有人用到。

### F7 引用的行号与路径（minor，代码事实）

- `translation_driver/responses.py:125` —— **精确命中**，第 125 行就是 `if reason == "max_output_tokens":`。
- `formats/openai_responses.py:513` —— 第 513 行是 `self._terminal.stop_reason = (`，映射表达式在第 514 行。指向语句首行可以接受，但既然是给另一个仓的人看的，写 `513-515` 或直接写 514 更省事。
- 两处都省略了目录前缀。真实路径是 `src/app/pipeline/delivery/formats/openai_responses.py` 与 `src/app/pipeline/translation_driver/responses.py`。仓内有**三个** `openai_responses.py`（`pipeline/delivery/formats/`、`pipeline/direct_driver/`、`pipeline/translation_driver/`），靠 `formats/` 这一段仍然唯一，所以不歧义；但**这一节的读者可能手上没有这个仓**，给全路径成本为零。

**怎么失败**：另一个仓的人拿这两个引用去核对时，多花一次 `fd` 的功夫。纯成本问题，不改变任何结论。

### F8 「工具未声明时只告警不拦截」与事件名 —— 正确（ok，代码事实 + 既有测试）

`pipeline_app.py:557-566`：取 `context.payload["tools"]`，逐项比对 `name`，不匹配就 `get_logger().warning("auto_retry_tool_not_declared", request_id=..., tool=name)`，**之后没有 return，函数继续走到构块并返回**。事件名逐字为 `auto_retry_tool_not_declared`。

既有测试 `tests/int/test_pipeline_app.py:3127` 断言这条警告出现，同一个测试的 `:3116-3120` 又断言块照发——即「告警」与「不拦截」同时被钉住，不是只钉了一半。

这一条还有**人写权威文档背书**：`docs/.human-controlled/upstream-retry-and-continuation.md:37`「检查客户端请求是否包含该工具调用的定义，如果没有，在本代理日志中打印警告日志，但仍然依样返回给客户端。」README 写的「用户 2026-08-21 裁决」与它一致。

### F9 缺 `num_messages` 的判读规则 —— major（遗漏，代码事实）

这一节的自述是：「MCP server 在另一个仓……**本节是本仓发出方的一手契约**，从代码直读，**是两侧对齐的依据**」，并声明它把 `decisions.md` 第四节第 1 条的「待对齐」给答了。

但 `decisions.md` 第四节**第 3 条**是一个仍然打开的待对齐项，而且是同一批读者要解决的：

> 3. **`num_messages` 的判法**：本项目建议按「同一数值重复出现」而非「数值有没有增长」（并行子智能体与主会话共享同一个 MCP server 进程，调用会交错）。**待与 MCP 端对齐，两边不一致该参数即失效。**

本仓代码里也把这条写死在注释上（`pipeline_app.py:585`）：

> The client's own count, not the upstream request's: it advances by exactly two per hand-over — one assistant turn, one tool result — which is what makes "the same number twice" an exact answer rather than a heuristic. Ruled 2026-08-21.

README 这一节只给了「这个数是怎么来的」，没给「这个数该怎么读」。

**怎么失败**（具体场景，不是「建议完善」）：另一个仓的实现者拿到「客户端入站 `messages` 的长度」，最自然的写法是「记住上次的值，这次没增长就中止」。在并行子智能体与主会话共用同一个 MCP server 进程时，两条独立会话的调用会交错，于是 A 会话的 12 后面跟着 B 会话的 6——按「有没有增长」判，B 的正常调用会被误判成「无进展」而中止；反过来，A 的重复 12 夹在中间也可能被 B 的数值掩盖而漏判。`decisions.md` 四.3 已经预见了这一点并给了本仓的建议判法，而这份「两侧对齐的依据」偏偏没有把它带过去。

**建议改法**：在 `num_messages` 那一行下面加一句——「**判法（本仓建议，待对齐）**：按『同一数值重复出现』判无进展，不要按『数值有没有增长』判；每次交接后客户端会 +2（一条 assistant 轮次 + 一条 tool result），但并行子智能体与主会话共享同一个 MCP server 进程、调用会交错，所以跨调用的单调性不成立。见 `decisions.md` 第四节第 3 条。」

### F10 未给出工具全名的默认值（minor，代码事实）

`name` 那一行写的是「<配置项 `upstream_request_retry.auto_retry_tool_call_full_name` 的值>」，没给默认值。默认值是（`src/app/config/schema.py:189-191`）：

```
mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted
```

这个字符串对接收端是**载重的**：Claude Code 对插件提供的 MCP server 的命名是 `mcp__plugin_<plugin>_<server>__<tool>`，所以另一个仓必须把插件命名为 `ghc-api-proxy-helper`、把 MCP server 命名为 `auto-retry`、把工具命名为 `turn_interrupted`，三段全对才匹配得上。

**为什么只判 minor**：同一 README 第 18 行已经点了 `turn_interrupted`，第 52 行点了插件名 `ghc-api-proxy-helper`；而且人写权威文档 `docs/.human-controlled/upstream-retry-and-continuation.md:31` 就写着完整默认名，README 第 7 行也把读者指过去了。缺的只是 `auto-retry` 这一段和「一处可读」。

**怎么失败**：如果只把这一节剪贴给另一个仓（这正是它被写出来的用途），对方把 server 命名成别的（比如 `retry`），线上表现是**每次交接都走 `auto_retry_tool_not_declared` 那条路**——不报错、不拦截、块照发，客户端回一个 `No such tool available`，对话继续但续写机制静默失效。这正是本项目「告警不拦截」这个裁决的代价面，所以名字写全的收益不低。

### F11 工作树里的 `config.example.yaml` 把一个永不匹配的值写进了 `hand_over_stop_reasons` —— major（一手实测）

评审期间发现 `docs/.human-controlled/config.example.yaml` 有**未提交**改动（`git diff`）：

```diff
-    streamReplay:
-      max_retries: 100
 
   auto_retry_tool_call_full_name: mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted
 
+  hand_over_stop_reasons: ["max_tokens", "max_output_tokens"]
```

删 `streamReplay` 与 `decisions.md` 第二之二节第 15 条一致，没问题。**问题在新增的 `max_output_tokens`。**

F6 的对照 B 是一手实测：把 `hand_over_stop_reasons` 配成 `{"max_output_tokens"}`，`synthesize` **一次都没被调用**——因为归一化发生在门之前，`terminal.stop_reason` 永远是 `max_tokens`，`max_output_tokens` 这个值在门上**结构上永不匹配**。

- **今天无害**：列表里 `max_tokens` 还在，所以行为不变，多出来的那个值是个静默的空操作。
- **明天怎么失败**：这是一份**用户亲笔的权威配置样例**，它现在在暗示 `max_output_tokens` 是一个有意义的取值。下一个读者（包括另一个仓的人）合理地推断「上游说的是 `max_output_tokens`，`max_tokens` 大概是写错了/是别名」，把 `max_tokens` 删掉或替换掉——此后**所有撞上限的回合都不再交接**：`ResponsesAssembler` 的 `_hand_over_stop_reasons` 同时决定「被截断的块丢不丢」（`openai_responses.py:393`），门不中就走「保留被截断的块、正常收尾」，客户端拿到一个半截块 + `stop_reason: max_tokens`，没有任何 tool call，也没有任何告警。这是静默失效，不是可见故障。
- **保质期声明**：这份改动**未提交**，我无法判定作者是用户本人还是并行会话；`docs/.human-controlled/` 按项目约定归用户。所以这条不是「请去改」，而是**请主会话把它端给用户裁决**：要么删掉 `max_output_tokens`，要么在 README 这一节和该 yaml 的注释里写明「它是给未来上游改口径留的门，今天永不命中」。
- 顺带：这也让 F6 里的建议更值钱——README 那句「不会出现 `max_output_tokens`」如果补上「**配置成它也不会生效**」，正好挡住这次误解。

---

## 第二件：提交 `027698f`

### F12 改夹具**没有削弱**那两条测试原本钉住的东西（ok，一手实测，两轮受控变异）

先说方法，因为「打红了」本身不够——要分清打红的是哪一层。

**基线冻结与还原（全程未用 `git checkout --`）**：`cp` 一份 `stream.py` 到 `$CLAUDE_JOB_DIR/tmp/stream.py.baseline` 并存 `sha256`；确认基线里**确实含有被变异的那两支**（`grep` 到第 304、318 行）且相对 HEAD 干净；变异一律先**在副本上生成，再 `diff -u` 导出冻结补丁**，用 `git apply` 打入、`git apply --reverse` 还原；还原写在 `trap ... EXIT INT TERM` 里；每轮结束 `sha256sum --check` + `git status` 复核。两轮变异后工作树只剩评审开始前就存在的那两个 `docs/.human-controlled/` 未提交改动，`stream.py` 与基线**字节一致**。

**变异 M1（把 `terminal.seen` 提到 client deadline 之前）**：实现为等价改写，只改一行——

```
-        if isinstance(torn, ClientDeadlineError):
+        if isinstance(torn, ClientDeadlineError) and not assembler.terminal.seen:
```

它与「把 `if assembler.terminal.seen: break` 整支提到 `if isinstance(torn, ClientDeadlineError):` 之前」逐分支等价：`terminal.seen` 为真时跳过时限支、落到下面的 `terminal.seen` 支 `break`；为假时两者行为相同。选它是因为它能表达成一行的精确补丁，还原风险最低。

**变异确已装载**（在测试会读到的那一层读，不是看 diff）：

```
module file: /home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py
branch as loaded: ['if isinstance(torn, ClientDeadlineError) and not assembler.terminal.seen:']
MUTATION CONFIRMED PRESENT AT RUNTIME
```

**M1 在仓内套件上的结果**（`uv run pytest tests/unit/pipeline/delivery/test_stream_delivery.py -q -k client_deadline`）：

```
1 failed, 3 passed, 41 deselected
FAILED ...::test_the_client_deadline_outranks_an_upstream_that_just_finished
    AssertionError: assert 'message_stop' == 'error'
```

**只有新测试转红。** 提交信息说的「Swapping the branches now reddens exactly it」——一手复核吻合。

**M1 在「改夹具前」的版本上会怎样**：为了不碰共享树里的测试文件，把两条测试的 **pre-commit 版本**（夹具为完整 `anthropic_stream("one")`）与 **post-commit 版本**（`[:-2]`）各复刻一份到 `/tmp` 的独立文件里，用 `PYTHONPATH=src` 跑。未变异时六个用例全绿（说明复刻是忠实的）；M1 之下：

```
3 failed, 3 passed
FAILED test_PRECOMMIT_the_client_deadline_is_the_one_ending_that_says_so
FAILED test_PRECOMMIT_a_held_back_policy_still_hears_the_client_deadline[full]
FAILED test_PRECOMMIT_a_held_back_policy_still_hears_the_client_deadline[until-tool-use]
```

即：**改夹具确实把「次序」这一层的鉴别力从这两条测试上拿走了**（这与 `deferred.md` 第 11 条第 116 行记录的「三条 client-deadline 测试全部转红」是同一个观测）。这是本次提交**有意**做的取舍，且立刻由新测试接手——净鉴别力没有下降，只是从「三条各带一点、名字都不提它」变成「一条独家承担、名字直说」。

**变异 M2（把整支禁掉：`if False and isinstance(torn, ClientDeadlineError):`）**，同样先证已装载，然后：

- `/tmp` 复刻文件：**6 个用例全红**（pre-commit 与 post-commit 夹具都红）
- 仓内套件 `-k client_deadline`：**4 个全红**

即两条测试**各自名义上的属性**（「客户端时限是唯一会明说的收尾」「held-back 策略下这个 error 帧照样欠着」）在改夹具后**仍然被咬住**。

**再补一个非平凡性对照**，因为 held-back 那条测试还断言 `b'"text":"one"' not in ...`（「缓冲块被丢弃而不是先 flush」）——如果新夹具下那个块根本没被组装出来，这条断言就成了恒真。实测同一截断夹具、**不触发时限**时：

```
policy=full            truncated fixture, NO deadline -> block text present: True
policy=until-tool-use  truncated fixture, NO deadline -> block text present: True
policy=block           truncated fixture, NO deadline -> block text present: True
```

块确实存在，断言非平凡。

**逐条回答「改之前它能打红什么、改之后还能吗」**：

| 属性 | 改之前 | 改之后 |
|---|---|---|
| 客户端时限收尾必须是 `error` 帧且带 `client_deadline_exceeded` | 能（M2 红） | 能（M2 红） |
| 不得冒充 `message_stop` | 能（M2 红） | 能（M2 红） |
| held-back 策略下缓冲块被丢弃而非 flush | 能（且非平凡） | 能（且非平凡，见上表） |
| **客户端时限压过「上游刚好完成」** | 能（M1 红 ×3） | **不能**（M1 全绿）——**由新测试接手，M1 下它是全套件里唯一转红的** |
| 「时限落在回合中途」这一位置 | **测不到**（旧夹具永远带完整终结事件） | 能（这是新夹具带来的**净增**覆盖） |

**判定：ok，不构成削弱。** 而且最后一行是个容易被忽略的收益——旧夹具下这两条测试的名字说「时限先到」，实际钉的是「上游完成后时限才到」，改夹具把名实对齐了。

### F13 新测试是否单独承担次序 —— 是（ok，一手实测）

见 F12 的 M1 结果：仓内 `-k client_deadline` 四条里只有 `test_the_client_deadline_outranks_an_upstream_that_just_finished` 转红，失败信息 `assert 'message_stop' == 'error'` 正是「上游已完成的回合被交付了出去、而不是被时限打断」这个语义。**这条测试确实独家承担了次序，并且它的名字直说了这件事。**

裁决来源核对无误：`decisions.md` 第二之二节第 18 条（用户 2026-08-22）与 `deferred.md` 第 11 条对得上；人写权威 `docs/.human-controlled/client-side-block-delivery.md:19`「当客户端请求超时，如果已发 HTTP 200 响应头，则**放弃当前缓冲块**，发 SSE error 再收尾」——无条件句，**不区分上游有没有刚好完成**，所以代码注释、测试与裁决三者与人写权威一致，没有冲突。

### F14 「The attempt deadline just below」这个方位描述会误导（minor，代码事实）

`stream.py:311` 新增的注释末句：

> The attempt deadline **just below** is ordered the other way for the opposite reason — it ends only *this attempt*, so a finished turn has to be recognised before anything asks what went wrong.

问题是：**`_deliver` 里根本没有 attempt deadline 的显式分支。** `rg "StreamDeadlineError" src/app/pipeline/delivery/stream.py` **零命中**——它由 `with_deadline_at`（`pipeline_app.py:736-742`）抛出，作为普通的 `torn` 走到 `stream.py:325` 的 `replay.eligible`，在 `pipeline_app.py:540-541` 才被 `_replay_reason` 认成 `RetryReason.NETWORK`。

于是「just below」往下看，第一个分支是 `if assembler.terminal.seen:`（`:318`），而那条**恰恰不是** attempt deadline。一个只读第一条注释的人会把「排在下面、次序相反的那个」认成 `terminal.seen` 支本身，得到一个自相矛盾的读法。

**为什么只判 minor 而不是 major**：第二条注释（`:323`）把它补上了——「Above the attempt deadline, though, **which reaches here as an ordinary tear**」，明说了它不是一个分支。两条合读可解，且这条提交的主要目的（把裁决写在代码旁边）达成了。

**怎么失败**：下一个改这段代码的人按第一条注释去找「下面那个 attempt deadline 分支」，找不到，于是要么去翻 `pipeline_app.py` 才明白，要么误以为注释已经过期而顺手删掉——本提交的全部价值就在这两条注释上。

**建议改法**：把 `:311` 的末句改成「上游时限（`upstream_request_deadline`，由 `pipeline_app` 的 `with_deadline_at` 抛出）**在这里没有自己的分支**，它作为普通 tear 落到下面的 `terminal.seen` 之后；次序相反且必须相反——它只结束*这次尝试*，所以『上游说完了没有』必须先答」。这样「相反的次序」就锚在 `terminal.seen` 这个真实存在的位置上，而不是锚在一个不存在的分支上。

### F15 `deferred.md` 第 11 条的收尾句已过期（minor，代码事实）

`deferred.md:117` 结尾仍写着：

> 按 `[:-2]` 模式改夹具……另加一条专测「上游已完成后时限才到 → 仍报时限」的正样本，才算把新裁决钉住。**这是本条唯一还要动手的部分。**

`027698f` 把这三件事全做了。时间线支持「写在前、没回来更新」：`deferred.md` mtime `Aug 22 13:37`，提交时间 `Aug 22 13:42:42`。

这一段被放在「保留下面的原始分析」之下，可以主张它是历史记录；但**加粗的那句是现在时的待办断言**，一个只读这一条的人会以为还没做。按 `sync-live-docs-timely`，建议在该行后追加一句「**2026-08-22 已完成，见 `027698f`**」——注意不要改写原句本身（那会篡改这份原始分析所记录的时间点）。

---

## 顺带核验：`deferred.md` 第 1 条的撤销依据

两条都成立，但其中一条的措辞值得收紧。

### F16 「`parse_prompt_limit_error` 只有两个调用点，其一在未挂载的 legacy hooks 链」—— 成立（ok，代码事实）

`rg` 全仓（含 `tests/`）后，生产代码里的**调用点**恰好两个，行号也对：

- `src/app/tokenization/service.py:64`
- `src/app/hooks/builtin/token_calibration.py:87`

其余命中全是 `import` / `__all__` / 测试（`tests/unit/tokenization/test_tokenization_limits.py`）。

「未挂载」也成立，链条是：`token_calibration` 的两个 hook 只由 `register_builtin_hooks` 注册（`src/app/hooks/builtin/__init__.py:17`），而它只有一个调用点 `src/app/server/app_factory.py:110`；服务进程从 `src/app/cli.py:128` 与 `:154` 起，**只构建 `create_pipeline_app(chain)`**，从不调 `app_factory`。另有一条架构测试 `tests/unit/test_module_boundaries.py:43` 钉住 `assert "app.pipeline.executor" not in new_chain`。

**但措辞的边界要写准**：`ObserverEvent.ERROR` 带 `response_body` + `status_code` 的分发**是存在的**，在 `src/app/pipeline/executor.py:477-487`（另外三处 `ObserverEvent.ERROR` 不带 `response_body`，所以对这个 observer 无效）。所以准确的说法不是「这段代码没接线」，而是「**这条链路不被服务进程构建**」。建议把 `deferred.md:12` 的「（**未挂载的 legacy hooks 链**）」改成「（**legacy 链路，服务进程只构建 `create_pipeline_app`，从不走 `app_factory`**）」——同一个结论，但下一个人核对时不会因为找到 `register_builtin_hooks` 的调用点而以为这句错了。

### F17 `/api/tokenization/limits` 标为「暂不支持」—— 成立（ok，代码事实）

`docs/.human-controlled/api.md:21`：

```
- ~~Tokenization：`/api/tokenization/calibration`、`/api/tokenization/limits`~~ 暂不支持
```

删除线 + 「暂不支持」，与 `deferred.md:12` 的引用一致。（路由本身仍存在于 `src/app/routes/management.py:79`，但那是 `app_factory` 那侧的路由，同样不被服务进程构建。）

---

## 范围外的一条观察（不计入分级，仅告知）

`docs/.human-controlled/client-side-block-delivery.md:16` 写「一次上游请求的最大时长（`upstream_request_retry.upstream_request_deadline`）」，而代码读的是 `chain.config.upstream_request_timeouts.upstream_request_deadline`（`src/app/server/handler.py:170`，字段定义 `src/app/config/schema.py:152`）——**配置节名不一致**。人写文档是权威，所以方向上应当是代码或人写文档二选一去对齐，但这既不在本次两件评审对象之内，`docs/.human-controlled/` 又正有未提交改动在飞，所以此处只记录不判定。

---

## 证据与探针的处置

- 变异冻结补丁与基线：`$CLAUDE_JOB_DIR/tmp/`（`stream.py.baseline`、`stream.sha256`、`mutation.patch`、`mutation2.patch`）
- 临时探针：`/tmp/probe_maxtok_260822.py`、`/tmp/probe_precommit_260822/test_precommit_fixtures.py` —— 评审结束时删除
- **仓库未被本次评审改动**：`sha256sum --check` 通过，`git status` 与评审开始时逐项相同（两个 `docs/.human-controlled/` 未提交改动是评审开始前就在的，非本次产生）
- 未向上游发出任何真实网络请求；未运行 `ruff format`（只跑了 `ruff check src/app/pipeline/delivery/stream.py`，通过）

## 建议的处置优先级

1. **F11**（major，且有保质期）——把工作树里 `config.example.yaml` 的 `max_output_tokens` 端给用户裁决，因为它是一份权威样例在暗示一个结构上永不命中的取值。
2. **F9**（major）——把 `num_messages` 的判读规则补进这一节，否则另一个仓最可能实现成「按增长判」，而那在并行子智能体场景下会误判。
3. F4 / F10 / F14 / F15 / F7（minor）——各自一两行的改法已写在对应条目里。
4. F16 的措辞收紧可选。
