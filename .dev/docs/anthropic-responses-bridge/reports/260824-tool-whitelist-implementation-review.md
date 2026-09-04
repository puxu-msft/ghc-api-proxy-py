# Tool 白名单重建的独立评审（未提交工作树）

- 日期：2026-08-24
- 评审者：独立 subagent，按 `my-skills:as-reviewer` 工作，判据在读实现之前先取（openai SDK 3.3.1 的 `FunctionToolParam` / `ToolParam`、`spec.md` 的 HEAD 版本、`LossCode` 的 HEAD 版本、`docs/.human-controlled/`）
- 被评对象：主仓工作树未提交改动，限于 `src/app/pipeline/translation_driver/openai_responses.py`、`src/app/config/settings.py`、`tests/unit/pipeline/translation_driver/test_translation_driver.py`，以及 `.dev` 里 `docs/anthropic-responses-bridge/spec.md` 与新增的 `reports/260824-responses-leg-tool-field-measurements.md`
- 明确不在范围：`docs/.human-controlled/` 的改动、`src/app/pipeline/subscribers/`、`request_headers.py`、`driver.py`、`semantic.py` 里 `CACHE_CONTROL_FIELD_NOT_CARRIED` 那一格（同批另一组，另有评审）

## 总体 verdict

**needs-fix。blocker 0，major 4，minor 7，nit 1。**

核心修复本身是对的：白名单取自 wire 自己的类型而非我方推断、逐字段与 SDK 核对无遗漏、`defer_loading` 的处置有实测支撑、正反两向变异都能打红。四条 major 没有一条说「这个 400 没修好」——它们说的是「这次改动新造了一条更安的失效面」「一条断言是假的」「一条裁决无法被核验且被扩宽了」「一条与模块既有明文政策相反的决定被写进了规范却没并列代价」。

## 我跑过什么

```
git -C /home/xp/src/ghc-api-proxy-py diff -- <各路径>            # 被评对象
git -C /home/xp/src/ghc-api-proxy-py/.dev diff -- docs/anthropic-responses-bridge/spec.md
git show HEAD:src/app/pipeline/translation_driver/openai_responses.py   # 判据基线
git show HEAD:src/app/pipeline/translation_driver/semantic.py          # LossCode 既有语义
cat .venv/lib/python3*/site-packages/openai/types/responses/function_tool_param.py
cat .venv/lib/python3*/site-packages/openai/types/responses/tool_param.py
rg -n "tool_search" src tests docs                                     # 字段删除的残留核查
uv run ruff check <三个文件>                                            # All checks passed
uv run pyright src tests                                               # 0 errors
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80 -q  # 1779 passed, 2 skipped, 90.49%
```

另外跑了两组只读探针（直接 import 生产模块，未改任何文件）与四次**内存内**变异（pytest 插件在 `pytest_configure` 里改模块属性 / 包一层 `_function_tool`，全程不落盘；跑完复核 `git diff --stat` 与开工时逐字一致）。

> 全量数字与作者自报的 1773 passed / 90.51% 有差额。这不是矛盾：主树是共享的，同批另一组的 `subscribers/anthropic_cache_control.py` 及其测试在我这一轮里已经在树上了。

> **快照边界**：评审期间主树与 `.dev` 都在被同伴推进。`tests/unit/pipeline/test_client_request_headers.py` 从 +143 长到 +158，`.dev` 的 `docs/anthropic-responses-bridge/implementation.md` 从「HEAD 干净」变成「+8 行未提交」。本报告引用的所有行号在收尾时逐条复核过仍然成立，但范围内五个文件之外的任何数字都可能已经变了。

## 发现

### R1 · major · 白名单只覆盖 `FunctionToolParam`，而 `_function_tool` 收的是整个 `ToolParam` 联合；docstring 用来替代早返回的那条不变量是假的

- primary：`src/app/pipeline/translation_driver/openai_responses.py:160`
- related：`:143`（白名单定义）、`:190`（重建点）、`src/app/pipeline/translation_driver/openai_responses.py` 的 `_tools_for_upstream`（server tool 分流之后，一切非 dated `web_search_` 的 tool 都落到 `_function_tool`）

docstring 写：「A tool that already looks like a Responses tool still comes out unchanged — everything such a tool carries is in the whitelist by construction」。这句是**假的**。`FunctionToolParam` 只是 `ToolParam` 联合的一支；同一个联合里还有 `WebSearchToolParam`、`Mcp`、`CustomToolParam`、`FileSearchToolParam`、`ToolSearchToolParam` 等，它们携带的字段没有一个在白名单里。

已实测（经公共 API `default_registry().translate(source=OPENAI_RESPONSES, target=OPENAI_RESPONSES)`）：

| 输入 tool | 出站 | 记录 |
|---|---|---|
| `{"type":"web_search","user_location":{"type":"approximate","city":"Beijing"}}` | `{"type":"web_search"}` | 一条 `extensions-not-carried` |
| `{"type":"mcp","server_label":"docs","server_url":"https://example/mcp","require_approval":"never"}` | `{"type":"mcp"}` | 三条，全部写成 `a tool: …` |
| `{"type":"custom","name":"grammar_tool","format":{"type":"grammar",…}}` | `{"type":"custom","name":"grammar_tool"}` | 一条 |

第三行最阴：Responses 的 custom tool 丢掉 `format` 之后**仍然合法**，语义从 grammar 约束变成自由文本——这是 200 而不是 400 的静默降级。

**生产今天不可达，这一点我核过**：`src/app/pipeline/routing.py:124` 是 `translation_required=target_format is not inbound_format`，所以 Responses→Responses 在生产里根本不翻译。但这个 crossing 是 registry 支持、且**测试套件自己在用**的操作——`tests/unit/pipeline/translation_driver/test_translation_driver.py:715-730` 就是 `source=WireFormat.OPENAI_RESPONSES, target=WireFormat.OPENAI_RESPONSES`，`:165-174` 也有同格式 Anthropic→Anthropic 的往返测试。

所以：**删掉早返回今天没有生产回归**（这一点作者的判断是对的），但**拿来替代它的那条不变量是假的**，下一个据此推理的人会以为白名单已经保护了这条路。

建议（取舍交回调用方）：把 docstring 的断言收窄成「只对 function tool 成立」，并在函数入口对 `type` 既不是 `function` 也不是缺省的 tool 明确绕过白名单或显式拒绝。

### R2 · major · 400 修好之后，客户端会走进一条同一次调查已定位、却没有进任何活文档的静默失效

- primary：`src/app/pipeline/translation_driver/openai_responses.py:170-190`
- related：`.dev/docs/anthropic-responses-bridge/spec.md:145-147`（新条款）、`.dev/docs/anthropic-responses-bridge/implementation.md:206-212`（只列了已落地的三件事）、`.dev/docs/tmp/260824-defer-loading-responses-leg-investigation.md` DL-07

实测（经公共 API 走完整 Anthropic→Responses 翻译）：

```
输入   tool_result.content[] = [{"type":"tool_reference","tool_name":"Bash","description":"run a command"}]
输出   {"type":"function_call_output","call_id":"toolu_1","output":""}
记录   tool-result-content-flattened: non-text tool result content for toolu_1
```

场景：Claude Code 2.1.241 开 tool search。**改动前**——请求 400，用户立刻看到一句明确的错误。**改动后**——请求 200，模型调用客户端的 `ToolSearch`，客户端把 `tool_reference` 回传，代理把它压成空串，模型看到「搜了，什么都没有」，大概率再搜一次。用户侧表现是烧 token 不出活，且没有任何面向用户的错误。**这次改动把一个响亮的失败换成了一个安静的失败**，而这正是本项目反复写规则防的那一类。

同族第二项：`{"type":"tool_search_tool_regex_20251119","name":"tool_search_tool_regex"}` 仍然原样出站（`_ANTHROPIC_SERVER_TOOL_FAMILIES` 只有 `web_search_`），必然吃 `Invalid value:` 400。这是 VS Code Copilot Chat 的形态。而 Spec 矩阵那一行写的是 `REJECT | 执行本规格 server-tool no-revive，不进入 upstream`——**实现与 Spec 的这条偏离本就存在**，本次在同一张矩阵上新增三行时没有升级它。

我**不主张**这次必须实现这两项。主张的是：本 topic 没有 `deferred.md`，这两项目前只活在一份 `docs/tmp/` 的调查报告里，按项目自己的规则（「不让报告成为唯一真相来源」「中途发现的、与当前任务相关甚至构成闸门的，立即纳入考量，否则记下来」）必须进 Spec 或建台账。第二项还是「实现偏离了 Spec 正确记录的裁决」，按规则应当上报而不是沉默。

### R3 · major · 「用户 2026-08-24 裁定」无一手锚点可核，且 `spec.md:147` 把裁决从一个族扩到五个族

- primary：`.dev/docs/anthropic-responses-bridge/spec.md:147`
- related：`spec.md:16`、`spec.md:145`、`spec.md:146`、`src/app/pipeline/translation_driver/openai_responses.py:151`、`.dev/docs/anthropic-responses-bridge/implementation.md:206`、`:210`

**(i) 一手来源不可核。** 五处写「用户 2026-08-24 裁定 tool search 不是本代理提供的能力」，但都没有逐字原话，也没有可回指的锚。`rg -n "tool_search" docs` 在 `docs/.human-controlled/` 零命中——用户亲笔文档里没有这条。

我**不主张用户没说过**：历史对话我无法访问，那是我判定不了的事实。我主张的是——这条已经被用来关闭一个方向、删两个配置字段、写进规范文档三处，而任何后续会话都无法核验它。按 `as-reviewer` 的权威归属条款，举证责任在标注者：请补一句逐字原话，或在 `docs/.human-controlled/` 留一格，或把标注改成真实来源并留回填出口。

**(ii) 范围被扩宽。** `:147` 的原文：

> 顺带更正一条既有注释：……「`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_` 没有 hosted 对应物」的说法，被上面那份枚举证伪了至少 `tool_search_` 与 `computer_` 两族。**「endpoint 认识这个 type」不等于「我们应该去用它」**，所以证伪的是那句理由，不是那条不映射的结论——而现在那条结论有了比理由更硬的依据，即用户裁决。

「那条不映射的结论」在上下文里指向的注释覆盖**五个族**，而裁决按其自身表述只覆盖 tool search 一族。按字面读，这句把用户裁决扩成了另外四族（`memory_`／`text_editor_`／`bash_`／`computer_`）不映射的依据。

我承认这句**有歧义**：也可以只读成指前一段讨论的 tool search 映射结论。但正因为它在规范文档里、且歧义方向是「扩」，应当收窄。**这是调用方问我「是不是在护短」的第 8 点里我唯一认为确实越界的一处**；其余几处（`:16`、`:145`、`:146`）的范围我核过，都落在裁决字面之内。

至于「该裁决同时删除了 legacy `AppSettings` 里两个开关」：删字段这个动作本身是 agent 从裁决推出来的合理动作，但句式读起来像用户下令删的。建议改成「据此裁决，本次一并删除了……」。

### R4 · major · 同一个模块里两条相反的未知字段政策，且 Spec 把 `tools[]` 面的默认从严格翻成了宽松

- primary：`src/app/pipeline/translation_driver/openai_responses.py:170-190`
- related：`:250`（`_web_search_tool` 的相反政策，HEAD 起就在）、`.dev/docs/anthropic-responses-bridge/spec.md:169`（新矩阵行）、`spec.md:153`（DEGRADE 的规范定义）

`:250` 的既有注释写得非常明确：

> A field outside the allowed set refuses too, rather than being stripped. An unknown field today is a field with meaning tomorrow, and silently removing one turns whatever it asked for into a no-op — the same failure as the domain lists, arriving later and with nobody watching for it.

`_web_search_tool` 对白名单外字段 **raise `TranslationRefused`**。新的 `_function_tool` 对**完全相同的情形**静默剥离并记一条 `EXTENSIONS_NOT_CARRIED`。两个函数相隔六十行，同一个问题，相反的答案。

这不是纯理论。实测：

```
{"type":"web_fetch_20250910","name":"web_fetch","max_uses":3,"allowed_domains":["a.com"]}
→ {"type":"web_fetch_20250910","name":"web_fetch"}
  losses: extensions-not-carried × 2（allowed_domains、max_uses）
```

`allowed_domains` 是**收窄**，被静默丢掉就变成 no-op，而这正是 `:250` 那段话点名的那种「事后无法检测」的失效。今天它被 type 级 400 掩盖着，但把 `web_fetch_` 加进 `_ANTHROPIC_SERVER_TOOL_FAMILIES` 是模块注释自己点名的「the obvious edit … it is one word and it looks like a completion」。

规范一侧同理：`spec.md:153` 写着「只有矩阵明确写为 `DEGRADE` 的项目才允许 permissive 处理；**unknown 不自动继承 permissive**」，而新增的矩阵行类目字面就是「`tools[]` 上 Responses 不承认的键 → `DEGRADE`」。用一条覆盖「所有未知键」的 DEGRADE 行去满足「unknown 不自动继承 permissive」，等于对整个 `tools[]` 面把默认翻了过来。

**这是个真实取舍**，不是我判它错：黑名单复制换来「每来一个新字段就整请求 400」，白名单换来「每来一个新字段就静默变 no-op」，两者都有代价。我定 major，理由不是今天坏，而是一条与模块既有明文政策相反的决定被写成了规范条款，却没有把另一半代价并列写出来。取舍与是否给「收窄类字段」开一个拒绝的口子，交调用方裁决。

### R5 · minor · Spec 宣告的注释更正没有落到代码，且该注释被本次改动新证伪的那一半无人记录

- primary：`src/app/pipeline/translation_driver/openai_responses.py:197`
- related：`.dev/docs/anthropic-responses-bridge/spec.md:147`、`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:482`

`spec.md:147` 说「顺带更正一条既有注释」，但 `git diff` 显示 `openai_responses.py:197` 一字未改，仍然逐字写着：

> …so there is no hosted equivalent to name — **they travel unchanged today** and are recorded in …

两半都有问题：前半句被 P5 的枚举证伪（Spec 已记录），后半句被**本次改动本身**证伪，且没有记在任何地方。实测：

```
{"type":"text_editor_20250728","name":"str_replace_based_edit_tool","max_characters":10000}
→ {"type":"text_editor_20250728","name":"str_replace_based_edit_tool"}   # max_characters 被白名单吃掉
```

`hosted-web-search-spec.md:482` 同样还写着「客户端执行型 typed tool（`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_`）在 Responses 腿的处置：本规格不动，维持现状」——本次改动改了这个处置。

定 minor 而非 major：这些 type 全部在上游枚举之外，无论字段剥不剥都是 400，**今天没有可观察的行为差**。但一个排查「`max_characters` 为什么不见了」的人会读到这条注释并得出反向结论。

### R6 · minor · `defer_loading` 的 `is not True` 对一切非 `True` 值静默无声

- `src/app/pipeline/translation_driver/openai_responses.py:176`

实测（直接调 `_function_tool`）：

| `defer_loading` 的值 | 出站 | 记录 |
|---|---|---|
| `None` | 移除 | **无** |
| `"true"`（字符串） | 移除 | **无** |
| `1`（整数） | 移除 | **无** |
| `0` | 移除 | **无** |

`1 is True` 在 Python 里是 `False`（`bool` 与 `int` 不是同一个对象），所以 JSON 里的 `1` 也走静默分支。

今天不触发：JSON 的 `true` 只会解码成 `True`，客户端也没有理由发 `"true"`。但注释写的是「An explicit `false` says the tool was never deferred」，而代码覆盖的是「凡不是 `True` 的一切」——两者不是一回事，且**这个差别在日志上读不出来**：没观测到与不报这项同形。

建议：改成 `is False` 或 `if tool[key] is not True: record-or-skip 按 bool 判定`，把非 bool 值当作「客户端说了点什么但我不认识」记一条。

### R7 · minor · 两处没有鉴别力的绿

- `tests/unit/pipeline/translation_driver/test_translation_driver.py:922`、`:571-584`

**先说有鉴别力的部分**（我复现了作者做过的那次变异，并补了两次）：

| 变异（内存内） | 结果 |
|---|---|
| 把 `defer_loading` / `cache_control` / `eager_input_streaming` 加进白名单 | **3 红**（新增的前三条） |
| 只把 `defer_loading` 加进白名单 | **2 红** |
| 从白名单**移除** `output_schema` | **1 红**（负控制 `test_the_fields_this_wire_does_take_survive_the_whitelist`） |

两个方向都能打红，这三条是实的。

**没有鉴别力的两处**：

(a) `test_a_deferred_tool_does_not_reach_the_responses_wire` 只用 `conversion.has(...)`，不排他。变异：让 `defer_loading` 在记 `SERVER_TOOL_CONSTRAINT_DROPPED` 之外**额外**再记一条 `EXTENSIONS_NOT_CARRIED` → **50 个测试全绿**。也就是说「这次特意做的 code 选择」这件事本身没有被钉住。补一行 `assert not conversion.has(LossCode.EXTENSIONS_NOT_CARRIED)` 即可。

(b) 变异：把非 bool 的 `defer_loading` 路由到记录分支（等价于把 `is not True` 换成 `is False` 语义）→ **50 个测试全绿**。R6 那一支两个方向都无覆盖。

(c) 没有任何测试让一个**没有 `input_schema`** 的 tool 带着非 `type`/`name` 的字段走新白名单。最接近的 `:571-584` 只放了三个裸 `{"type":"web_search…"}`，恰好全在白名单内，所以它对 R1 恒绿。给那三个里的任意一个加上 `user_location`，它立刻会红——那就是 R1。

### R8 · minor · DEGRADE 记录的「字段路径」不成路径，无名 tool 的多条 loss 互相无法区分

- `src/app/pipeline/translation_driver/openai_responses.py:183`、`:187`

新矩阵行要求「记录字段路径」。实现记的是 `f"{name}: {key} not carried into openai-responses"`——没有索引，而且 **`defer_loading` 那条完全没有字段名**（`"{name}: deferred tool loading not carried into …"`），后续没人能按字段名把它检索出来。

无 `name` 的 tool 一律落到 `"a tool"`：实测一个 mcp tool 产生三条逐字相同前缀的 loss，读者分不出它们来自同一个 tool 还是三个。既有的 `_web_search_tool` 用的是 `f"{declared}.{key} into {WIRE_FORMAT}"`，有 type 作前缀，比这个可读。

### R9 · minor · `SERVER_TOOL_CONSTRAINT_DROPPED` 的既有语义被扩宽了

- `src/app/pipeline/translation_driver/openai_responses.py:181`

HEAD 版本里这个 code 的**全部** 5 处用法（`:264`／`:276`／`:287`／`:313`／`:346`）都在 `_web_search_tool` 与 `_user_location` 内部，无一例外是「一个 **server tool 声明** 上的字段无法表达」。现在它被用在一个普通 client function tool 的字段上。

**行为无后果，这一点我核过**：全仓只有 `src/app/pipeline/delivery/formats/errors.py:48` 对 `LossCode` 分支，且只看 `UPSTREAM_ERROR_NOT_INTERPRETED`。所以这纯粹是可读性问题。

具体代价：想在 History 里按这个 code 审计「web search 的约束丢了多少」的人，现在会收到大量普通 function tool 的命中；反过来，在 Responses 腿上看到这个 code 曾经等价于「有一个 web search 声明被翻译过」，现在不再等价。

判断：`EXTENSIONS_NOT_CARRIED` 也不合身（`defer_loading` 确实不是「未识别的扩展」，上游认识它）。两个都不理想。**这是判断题，我倾向于新开一个成员**（同批另一组给 `cache_control` 就是这么做的，理由结构完全一样：丢的东西具体且有后果），但不主张必须改。

### R10 · minor · 报告的推荐选项 A 与落地行为不一致，而 Spec 把该报告链接为依据

- `.dev/docs/anthropic-responses-bridge/reports/260824-responses-leg-tool-field-measurements.md:41`、`:50`

报告 §2 结论 1 写「保留它也不会有人受损」，§3 选项 A 写「翻译时删掉 `defer_loading: true`（**保留 `false`**）」，而实现两者都删。Spec 矩阵 `:171` 写的是「`false` 静默移除」，与实现一致——所以不一致的是 Spec 与它自己引用的依据。

报告是点时记录，不该回填改写。建议在 `spec.md` 引用它的那一句后面补半句：「落地时把 A 收紧为一并移除，因为 `false` 与缺省对上游同义」。

### R11 · minor · 探针原始输出没有归档，且同目录里有一条形似矛盾的旧记录

- `exp/260824-beta-and-cache-control-probe/probe_responses_tools.py:104-118`

该探针只 `print`，不写 `raw/`；同目录的 `probe.py` 会写 `raw/results.json` 与 `raw/run-main.txt`。所以报告的 P0–P7 全表在仓库里**没有任何原始证据**，只剩报告正文这一层转述。

更值得说的是混读风险：`raw/results.json` 里有一格 `C7-scope-on-a-tool -> 400`，与报告 P4「tool 上带 `scope` 的 `cache_control` → 200」表面相反。**我核过，不矛盾**——`probe.py:246` 打的是 `/v1/messages`（Anthropic 直连腿），`probe_responses_tools.py:108` 打的是 `{base}/responses`。但 `spec.md:16` 的修订记录里恰好并排提了这两条腿的 `cache_control`，一个只读文档的人极易读混。建议把 `probe_responses_tools.py` 的输出补存一份 `raw/run-responses-tools.txt`，并在报告 §2 抬头一句「本表全部打 `/responses`，与 `raw/results.json` 的 `C*` 行不是同一条腿」。

### R12 · nit · `spec.md` 的 `## 问题与意图` 后空行被删

- `.dev/docs/anthropic-responses-bridge/spec.md:18-19`

diff 里删掉了标题与正文之间的空行，标题直接贴正文。与本次改动无关，看起来是误改。

## 调用方点名的问题，逐条回答

**1 · 白名单本身正确吗** —— 正确，**在 function tool 的范围内**。`FunctionToolParam` 八个字段（`name`／`parameters`／`strict`／`type`／`allowed_callers`／`defer_loading`／`description`／`output_schema`）里七个在白名单，只差刻意排除的 `defer_loading`，无遗漏。Anthropic client tool 真实携带的键集合（`name`／`description`／`input_schema`／`type`／`cache_control`／`defer_loading`／`eager_input_streaming`）也无遗漏。范围外的问题是 R1。

顺带排除一条：`FunctionToolParam` 把 `parameters`／`strict`／`type` 标成 `Required`，但那是 SDK 构造侧的 TypedDict 约束，不是端点要求；缺 `strict` 的请求现网 200，这一点探针和现有测试都证过。不需要补齐。

**2 · `defer_loading` 的 `false` 静默 / `true` 记 loss 这个分支** —— 分支方向对（P1 vs P2 支持它），但判定式写错了覆盖面。见 R6，`None`／`"true"`／`1`／`0` 全部静默且无记录，其中 `1` 是因为 `1 is True` 为 `False`。

**3 · `_coerced_description` 与白名单的相互作用** —— **无问题，已实测**。`{"name":"t","input_schema":{…},"description":42,"zzz":1}` → 出 `{"name":"t","description":"42","type":"function","parameters":{…}}`，`TOOL_DESCRIPTION_COERCED` 与 `EXTENSIONS_NOT_CARRIED` 各一条。`_coerced_description` 返回的新 dict 被 `tool = ` 接住，`description` 在白名单内，没有丢失路径。

**4 · 删掉早返回的后果** —— 见 R1。分流之后走到 `_function_tool` 的有三类：Anthropic 普通 client function tool（唯一的生产路径，行为正确）、Anthropic 的其余 dated typed tool（`text_editor_`／`bash_`／`memory_`／`tool_search_`／`web_fetch_`，行为变了但被 type 级 400 掩盖，见 R5）、以及 Responses 原生非 function tool（R1，生产不可达但 registry 与测试都在走）。

**5 · loss code 选得对不对** —— `EXTENSIONS_NOT_CARRIED` 用在一般未知字段上，与 `semantic.py:146` 的既有用法（「本格式没人认领的键」）一致，成立。`SERVER_TOOL_CONSTRAINT_DROPPED` 是扩宽，见 R9，无行为后果。

**6 · 测试的分辨力，以及那次负控制收窄** —— 收窄是**必要的，不是掩盖**，我**不认为这是护短**，理由如下（实测，不是推断）：把共享夹具 `ANTHROPIC_REQUEST` 加上一个全合法 tool 跑一遍，`conversion.lossless` 恒为 `False`，且损失清单**恰好只有一条** `system-metadata-not-carried: into openai-responses instructions: cache_control`。而白名单这条路径能产生的 code**只有** `EXTENSIONS_NOT_CARRIED` 与 `SERVER_TOOL_CONSTRAINT_DROPPED` 两个（代码里就这两处 `record`）。所以收窄到这两个 code，没有放过任何本函数造得出的损失。

唯一代价是控制项现在看不见 `TOOL_DESCRIPTION_COERCED` 被误记——但那不是本次改动的面。真正的鉴别力缺口在别处，是 R7 的三条。

**7 · 删两个 `settings.py` 字段是否安全** —— **安全，两点我都独立复核了**：

- `rg -n "tool_search" src` 只命中 `src/app/models/capabilities.py:19` 的 `ModelDescriptor.tool_search`（模型能力描述符，与 `AppSettings` 无关）和四条注释，**没有任何 `settings.anthropic.tool_search` 的读点**；`rg -n "tool_search" tests -g '*.py'` 只命中新测试的 docstring；`rg -n "tool_search" docs` 零命中（工作树版本的 `config.example.yaml` 也不含）；`src/app/config/bundled-config.yaml` 零命中。
- `AnthropicConfig` 只被 `settings.py:174` 自己引用；新链的 `app/config/schema.py` 完全不用它；`app/config/loader.py` 首段明写 `load_settings` 自 2026-08-22 起在 `src/` 里除 re-export 外无调用者，只有 `tests/unit/config/test_config_loader.py` 在跑。`compat.py` 里没有涉及这两个键的迁移。

唯一残留风险：如果用户本机私有 config 曾写过这两个键，`extra="forbid"` 会让 `load_settings` 抛错。但该函数已无生产调用点，所以影响面为零。值得在 Spec 或 implementation.md 里留半句，以免将来有人以为它是配置删除的先例。

**8 · Spec 修订是否越权或过宽** —— 见 R3。一处确实扩宽（`:147`），一处标注归属需要一手锚点（五处）。其余的范围限定段（`:16` 的「本条只移除字段并记 DEGRADE，不引入任何 tool_search 能力」、`:145` 的 `defer_loading` 条款、`:171` 的矩阵行）我逐条对过裁决字面，都在覆盖之内，写得也克制。另外 `:146` 明确写下「可行不是要做的理由」并保留了未采纳方向 B 的记录，符合项目 `record-what-not-adopted` 的要求。

**9 · 项目纪律** —— 硬折行：逐行看过 diff，代码注释、Spec 新段、报告正文全部整行，无 80/120 折行。注释密度：新增注释都在解释「为什么是白名单」「为什么 `defer_loading` 不在里面」这类不看代码就想不出来的事，密度合适，没有复述代码。`ruff check` 三个文件全过，`pyright src tests` 0 errors，全量 1779 passed / 2 skipped / 覆盖 90.49%。

## 我排除了什么

按硬性要求逐条列出考虑过但认为不构成发现的：

1. **「这次修复没修好用户报的那个 400」** —— 排除。我一度认为生产 body 里可能同时带着 `tool_search_tool_regex_20251119` server tool，那样剥掉 `defer_loading` 之后还会撞第二个 400。查 `.dev/docs/tmp/260824-tool-search-beta-400-investigation.md` TS-02 与 §209：Claude Code 2.1.241 的运行时代码只构造普通 client-executed `ToolSearch`，不构造那个 typed server tool（有 `app.pretty.js` 的逐行行号依据），发那个的是 VS Code Copilot Chat。所以生产 body 里只有 `defer_loading`，剥掉即通。**这条我采信的是他人报告而非一手复核**（生产 body 未落盘，无法取证），分量：足以据以行动，但不是我亲测。
2. **`raw/results.json` 的 `C7-scope-on-a-tool -> 400` 与报告 P4 的 200 相矛盾** —— 排除，两条腿。`probe.py:246` 打 `/v1/messages`，`probe_responses_tools.py:108` 打 `/responses`。已核 URL。混读风险另记为 R11。
3. **本次剥 `cache_control` 与同批另一组新增的 `CACHE_CONTROL_FIELD_NOT_CARRIED` 冲突** —— 排除。`subscribers/anthropic_cache_control.py` 的 docstring 明写它面向 Anthropic Messages upstream（直连腿），而且它只剥 `cache_control` **内部**上游不认的键（`scope`），保留 `ttl`；本次是在翻译腿上整个丢掉 `cache_control`。两条腿、两个问题、两种正确处置，不冲突。两边用了不同 code 也说得通。
4. **loss code 选择会改变下游行为** —— 排除。全仓只有 `delivery/formats/errors.py:48` 对 `LossCode` 分支，且只看 `UPSTREAM_ERROR_NOT_INTERPRETED`。其余消费者（`driver.py:157` 塞进 `context.extras["conversion_losses"]`、`observability/request_trace.py` 的 `Loss`）都是泛化处理。所以 R9 只影响可读性。
5. **新增枚举成员会给以 `LossCode` 为键的表造缺项** —— 排除。本次没有新增成员（新增的 `CACHE_CONTROL_FIELD_NOT_CARRIED` 属另一组），且全仓没有以 `LossCode` 为键的查表。
6. **`FunctionToolParam` 里 `Required` 的字段没补齐会 400** —— 排除，见回答 1。
7. **`name` 取 `tool.get("name") or "a tool"` 在 `name` 为非字符串时会炸** —— 排除。它只进 f-string，任何对象都能渲染。可读性问题已并入 R8。
8. **`_translated_tools` 辅助函数直接取 `payload["tools"]` 可能 KeyError** —— 排除。白名单最少会留下 `type`，`tools` 键永远存在。
9. **早返回删除会破坏 Anthropic→Anthropic 同格式往返** —— 排除。那条路走 `to_anthropic_messages`，根本不经过 `_function_tool`；`test_unmodelled_fields_survive_a_same_format_round_trip` 现在也是绿的。
10. **`type: "custom"` 的 Anthropic client tool 会被翻错** —— 查了，**是既有行为且本次未改**：`{"type":"custom","name":"t","input_schema":{…}}` 出站为 `{"type":"custom","name":"t","parameters":{…}}`，`type` 原样带过去。Responses 的 `custom` 是另一种工具（要 `format`，不要 `parameters`），所以这大概率是个既有缺陷。**但它不属于本次改动**，且我没有实测上游对这个组合的反应，所以不列为发现，只在此记下供后续判断。
11. **`docs/.human-controlled/` 的两处改动、`subscribers/`、`request_headers.py`、`driver.py`、`semantic.py` 的 `CACHE_CONTROL_FIELD_NOT_CARRIED`** —— 按指派不评，未读实现细节（只读了与本次判据相关的 docstring）。
12. **「低概率扩展删除第 5 项」** —— 派发说明里列为本次改动之一，但**工作树里不存在这个改动**。`git -C .dev diff` 的 spec.md 只有三个 hunk（修订记录、Tools 一节、矩阵三行）加一个误删的空行；`git show HEAD:…spec.md` 的「仍需用户选择的低概率扩展」本来就只有 4 项。所以要么是记错，要么是一处打算做而没做的编辑。**请确认这是不是一个漏掉的修改。**

## 搜索面

**读了**：`openai_responses.py`（全文，HEAD 版与工作树版对读）、`semantic.py`（HEAD 版 + 工作树 diff）、`registry.py`、`routing.py`、`request.py` 相关段、`driver.py:130-275`、`config/settings.py`、`config/loader.py`、`config/compat.py`、`test_translation_driver.py`（新增 4 条 + `:125-200`／`:540-760`／`:880-987`）、`.venv` 里的 `function_tool_param.py` 与 `tool_param.py`、`spec.md`（HEAD 版与工作树版）、新增报告全文、`implementation.md:195-215`、`hosted-web-search-spec.md` 相关行、`docs/tmp/260824-defer-loading-responses-leg-investigation.md` 与 `260824-tool-search-beta-400-investigation.md` 的相关段、`probe_responses_tools.py`、`probe.py` 的目标 URL 与 `raw/results.json` 汇总。

**没看**：`delivery/` 全部（本次不涉及）、`subscribers/` 除两条 docstring 外、Anthropic 直连腿的实现、`archive-260808/`、cassette 与 int 测试。

**没能核的**：用户 2026-08-24 那条裁决的一手原话（历史对话不可访问，见 R3）；`req=fcc0bebc` 的实际出站 body（本代理不落盘 body，见排除项 1）；上游对 `{"type":"custom","name":…,"parameters":…}` 的反应（排除项 10，需要一次真实调用）。
