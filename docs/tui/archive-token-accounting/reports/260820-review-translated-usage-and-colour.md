# `70122b3`、`a6c0f20`、`eb93215` 代码评审

## 结论

**Verdict：needs-fix。** 三个提交中的颜色行为和流式 Responses usage 换算本身基本正确，但最终状态仍有 1 个 major 与 4 个 minor。最重要的问题不是 `eb93215` 的减法有误，而是提交所依赖的“缓冲路径已经做同一换算”只适用于旧的 `app.anthropic.client` 路径；当前 `pipeline_app` 的缓冲翻译路径仍把 Responses usage 原样写进 Anthropic 响应，因此同一翻译路由在 stream 与 non-stream 下给出不同且后者错误的 token 语义。

计数：major=1，minor=4，nit=0。

请求指定的 `my-skills:as-reviewer` 在本运行时未注册；本次按等效的只读、提交对象优先、发现先行流程执行。评审对象均通过 `git show <sha>` 和 `git grep ... <sha>` 读取，没有用工作树当前内容替代提交对象。

## Findings

### F1 — major — 当前缓冲翻译路径仍原样透传 Responses usage，stream 与 non-stream 的最终语义不一致

位置：`src/app/pipeline/translation_driver/responses.py:71-90`、`src/app/pipeline/translation_driver/responses.py:113-120`，并与 `src/app/protocols/responses_anthropic.py:214` 和 `src/app/pipeline/delivery/assembler.py:335` 对照。

`eb93215` 让 `ResponsesAssembler` 调用 `anthropic_usage_from_responses()`，所以 stream 路径现在会把 `input_tokens=138500,cached_tokens=135000` 正确换成 Anthropic 语义的 `input_tokens=3500,cache_read_input_tokens=135000`。然而当前主 server 的 non-stream 路径走 `handler.response_payload()` → translator registry → `from_openai_responses_response()` → `to_anthropic_response()`；前者在第 118—120 行把 Responses usage 原样放入 `SemanticResponse.usage`，后者在第 90 行又原样写入 Anthropic body。提交说明和 helper docstring 所说的“buffered path already converts”只对旧的 `app.anthropic.client` → `convert_responses_response_to_anthropic()` 路径成立，不对当前 `pipeline_app` 的缓冲路径成立。

我用与 `eb93215` 完全一致的 `responses.py` 和 `handler.py` 做了直接探针，138500／135000 的输入仍输出：

```python
{'input_tokens': 138500, 'input_tokens_details': {'cached_tokens': 135000}, 'output_tokens': 2700, 'total_tokens': 141200}
```

这不只是日志差异：non-stream Anthropic 客户端收到的是 Responses 键和 Responses 的总输入含义，既缺 `cache_read_input_tokens`，又把缓存命中部分算成 fresh input。相同模型、相同翻译方向仅因 `stream` 开关不同就改变 usage 契约，因此最终状态不自洽。

建议：让当前 `OPENAI_RESPONSES → ANTHROPIC_MESSAGES` 的缓冲响应翻译也复用 `anthropic_usage_from_responses()`，不要另写减法；同时加一条当前 `pipeline_app` non-stream HTTP 回归，断言 downstream body 与日志都得到 `3500 + 135000`，而不是 `138500`。

判断依据与权重：**足以据此修复。** 这是提交对象上的静态调用链，加上对与提交一致文件的可执行探针，不依赖工作树中并行修改。

### F2 — minor — stream wrapper 丢弃 `usage_inconsistent` 与 exact usage，诊断信号在该路径不可达

位置：`src/app/protocols/responses_anthropic.py:214-222`、`src/app/protocols/responses_anthropic.py:227-294`、`src/app/pipeline/delivery/assembler.py:335-346`。

`_convert_usage()` 不只产出 Anthropic wire 数字，还会产出 `ResponseConversionFact(code="usage_inconsistent", ...)` 与 `ResponseUsageFacts`，后者保留 `reasoning_tokens`、上游 totals 和完整 details。公开 wrapper 只返回 `.wire.model_dump()`，assembler 又只保存这个 dict，因此以下信号都会消失：cache 明细之和大于 `input_tokens`、`reasoning_tokens > output_tokens`、`total_tokens != input_tokens + output_tokens`。

代价不是当前日志少显示 reasoning tokens——日志本来不展示它，丢弃这一项没有直接 UI 损失。真正的代价是 `_convert_usage()` 用 `max(0, ...)` 继续产出可交付数字时，stream 路径再无任何地方说明这些数字来自自相矛盾的上游 usage。旧的 buffered executor 会把 `converted.facts` 与 `converted.usage_facts` 放进 context／history；当前主 `pipeline_app` 的 buffered translator 则也没有这条保存链，且还受 F1 影响。因此“缓冲路径仍保留 facts”只能限定为旧路径，不能作为当前 stream 丢弃它们的补偿。

建议：把这项明确记录为当前 pipeline 的诊断缺口，并在不改变块级交付的前提下保留 conversion result 中的 facts／exact usage，供 request context、history 或至少 operator warning 消费。无需为了这件事建立新门禁或证明基础设施。

判断依据与权重：**足以据此记录并修复，但不阻断本次正确 token 展示。** 正常上游 usage 的主功能正确；缺失的是矛盾输入的可观测性和取证信息。

### F3 — minor — malformed usage 被折叠成 `{}` 后没有运行时信号，无法与“上游未提供 usage”区分

位置：`src/app/pipeline/delivery/assembler.py:335-346`、`tests/unit/test_sse_assembly.py:321-330`。

捕获 `ResponseConversionError`、保住已经块级交付的响应是正确优先级；不能为日志字段中断已交付响应。代码也有充分注释说明为什么返回 `{}`，因此它满足项目 `never-swallow-errors` 的最低书面要求，我不把它判成规则层面的静默吞错。

但运行时仍然完全无信号：缺失 usage 时 `_read_terminal()` 不赋值，malformed usage 时 `_anthropic_usage()` 返回 `{}`，两者最终都让 token 字段消失。若上游字段结构变化或某个 detail 变成非法类型，生产日志只会像“这个 endpoint 不报 usage”，无法看出上游实际报了坏数据。`ResponseConversionError` 已带 `code` 与 `field_path`，丢掉这两项使问题很难定位。

建议：继续返回 `{}` 并继续交付响应，但同步记录一条 warning，或把错误 fact 挂到 `Terminal` 后由有 request context 的 accounting 层记录；至少保留 `code` 与 `field_path`。这不会违反“不为日志字段中断响应”。

判断依据与权重：**足以据此改进，但严重度为 minor。** 它影响异常上游 usage 的可诊断性，不影响正常 terminal usage 的换算与交付。

### F4 — minor — 新回归测试能抓代码退化，但 usage 字段结构仍来自手写 fixture，与本次上游依赖判据同源

位置：`tests/http/test_pipeline_app.py:1099-1117`、`tests/http/test_pipeline_app.py:1178-1208`、`tests/unit/test_sse_assembly.py:298-319`，并对照 `tests/integration/test_recorded_upstream.py`。

两条主要断言本身有鉴别力：unit test 直接要求 fresh input 为 3500，删掉减法会失败；HTTP test 还验证 route → assembler → request line 的接线，并明确排除旧的 `↑138.5k`。它们不是算术层面的恒真或与实现调用同一个 oracle。

不足在输入侧：两条测试都手写 `input_tokens_details.cached_tokens`，而这次修复是否成立恰恰取决于 Responses terminal usage 的真实字段结构和 `input_tokens` 是否包含 cached tokens。若我们对上游结构的认识错了，这两条测试会一起把错误认识证明为绿色。现有 recorded test 会重放真实 SSE，却只断言 block／event，不断言 terminal usage；因此 recorded evidence 与这次行为之间还没有测试接线。

仓库现有 cassette 已经给出足够事实，不需要再打真实上游：`tests/cassettes/anthropic_to_responses_stream.json` 与 `tests/cassettes/responses_web_search_stream.json` 的 `response.completed` 都带真实 Responses usage，后者有非零 `cached_tokens`。建议复用现有 cassette 增加一条 terminal usage 断言，保留现有手写 tests 负责快速定位算术和 HTTP 接线。不要用新的 proof framework，也不需要覆盖率指标。

判断依据与权重：**足以据此补一条 recorded regression。** 当前实现已由 cassette 内容静态印证，故这不是实现 correctness 的 major；它是项目明确测试约定下的证据来源缺口。

### F5 — minor — SPEC 在接受的整数阈值说明里仍把中档称为“白”，与最终不发 ANSI 的规则矛盾

位置：`docs/agents/tui-request-log/SPEC.md:73-74` 与 `docs/agents/tui-request-log/SPEC.md:91`。

表格和第 87 行已经正确写成中档“不着色”，但第 91 行仍说 10239 与 10240 “分处灰、白两侧”。`a6c0f20` 后第二侧不是显式白，而是不发任何 ANSI、沿用终端默认前景。这是 `70122b3` 旧措辞未随下一提交同步，正是用户要求检查的残留旧说法。

建议：只把“灰、白两侧”改为“灰、不着色两侧”或“灰、终端默认前景两侧”。不要改整数阈值，也不要重新提议显示值阈值。

判断依据与权重：**足以据此修正文档。** 同一 SPEC 的规则表与理由段直接互相矛盾。

## 专项核对结论

### 1．换算正确性与 `cache_write_tokens`

`anthropic_usage_from_responses()` 复用 `_convert_usage()` 是恰当方向，正常 usage 下的公式 `max(0, total_input - cache_read - cache_creation)` 同样适用于 stream terminal event。stream 与 non-stream 的 `usage` 都位于完整 response object，仓库真实 cassette 证明 terminal `response.completed` 使用同一结构。

`cache_write_tokens` 并非只存在于 non-stream。真实 `tests/cassettes/anthropic_to_responses_stream.json` 和 `tests/cassettes/responses_web_search_stream.json` 的 stream `response.completed` 都含 `input_tokens_details.cache_write_tokens: 0`；由 history 派生的 `tests/cassettes/history_responses_stream.json` 则只含 `cached_tokens`，证明该键也可能省略。当前 converter 对省略键取 0 正确。

现有真实样本中的 cache write 为 0，因此 `↻hit%+new%` 的 `+new%` 不出现符合上游实际报告，不是 stream 路径缺陷。若上游以后在 stream terminal 报非零 `cache_write_tokens`，当前换算与 `format_tokens()` 都会显示它。无需为了追求 `+new%` 而伪造 cache creation。

### 2．副产物丢弃

见 F2。`reasoning_tokens` 当前没有日志展示消费者，所以单独丢它没有可见代价；`usage_inconsistent` 和 exact upstream totals 则是实质诊断缺口。旧 buffered executor 保留，当前主 pipeline 的 stream 与 buffered 都未保留。

### 3．异常处理

见 F3。保住响应、返回 `{}` 的产品取舍正确；注释满足最低规则，但“缺失”和“格式坏”不应在所有运行时信号上完全合并。建议 warning／structured fact，不建议重新抛错中断响应。

### 4．依赖方向

没有发现循环依赖或分层倒置。`pipeline/delivery/assembler.py` 依赖 `protocols/responses_anthropic.py`，而后者只依赖 model、Anthropic／Responses protocol converter 与 reasoning helper，不反向 import pipeline。运行时导入探针成功。pipeline 复用协议换算，而不是 protocol 层调用 delivery，方向合理。

### 5．`paint()` 空颜色语义

枚举 `eb93215` 的全部 `paint()` 与 `volume_colour()` 调用点后，没有发现调用方依赖旧的“空 code 仍追加 RESET”行为。旧行为只会产生裸 reset，不承载合法颜色语义。`volume_colour()` 返回空字符串作为 SGR code 的 identity，与 `paint(text, code: str, ...)` 的现有 string 契约自然一致；改成 `str | None` 会把分支和类型扩散到所有调用方，却没有消除实际歧义，因此我**不建议**为此改成 `None`。当前 docstring 与精确 equality test 已把哨兵语义说清。

### 6．整数阈值一致性

实现与 tests 正确固定在 `10 * 1024`／`100 * 1024` 和 1000／10000；10239 与 10240 同显 `10.0KB` 而一侧灰、一侧不着色，是用户明确接受的行为，本报告不建议改变。仅发现 F5 的“白”字残留。源码阈值注释已说明 rounding band trade-off，没有残留“按显示数字分档”的实现主张。

### 7．测试鉴别力

颜色 tests 使用完整 span equality，能抓住阈值偏移、显式白、裸 RESET 和空 code 误处理。`test_the_thresholds_are_the_round_numbers` 精确跨过 10239／10240，能抓住恢复“按显示值分档”的退化。

usage unit test 能抓住减法被删除或 cached 键未映射；HTTP test 能抓 assembler 没接 helper、日志 reader 仍拿 raw Responses usage 等接线退化。malformed test 能固定“丢 token 数字但不让 terminal 处理失败”的现行为。唯一证据缺口是 F4 所述的真实字段结构没有由 cassette test 承担。

## 不建议采纳的做法

- 不建议重回按显示数字设阈值；这是用户已裁决接受的 rounding-band 行为。
- 不建议把 `volume_colour()` 的空字符串机械改成 `None`；现有 string identity 更简单，且没有误用证据。
- 不建议让 malformed usage 抛出并中断已块级交付的响应；应增加旁路诊断，而不是牺牲交付。
- 不建议为了这次修复重新实测真实上游；现有真实 cassette 已回答字段结构问题，应复用它。
- 不建议增加覆盖率指标、门禁、验收状态机或新的证明基础设施；一条现有 cassette 上的定向断言足够。
- 不建议为了保留 `reasoning_tokens` 强行把它塞进当前日志行；当前具体缺口是诊断事实丢失，不是 UI 必须新增字段。

## 并行工作树交互

已知的 `Terminal.stop_reason` 默认值从 `"end_turn"` 改为 `""` 的并行 hunk，不会改变 `eb93215` 正常 terminal usage 的结论。`ResponsesAssembler._read_terminal()` 在 `response.completed`／`response.incomplete` 上仍会显式设置 stop reason；`ResponseConversionError` 也已在 helper 内捕获，不会提前跳过该赋值。它与 F3 的共同风险只在“非 `ResponseConversionError` 的意外异常”上，此时整个 terminal 处理本来就会失败，不是默认值改动新造的 usage 问题。

## 执行证据与限制

- `git diff --check 70122b3^..70122b3`、`a6c0f20^..a6c0f20`、`eb93215^..eb93215` 均通过。
- runtime import 与正常 usage 换算探针通过，得到 `input_tokens=2,cache_read_input_tokens=8,output_tokens=2`。
- 定向运行 8 条相关 tests，结果为 `8 passed in 1.37s`：颜色空 code、失败行 route、字节分档、整数边界、token 分档、Responses stream usage、malformed usage、HTTP 日志接线。
- 定向 tests 在共享工作树当前状态运行，因此它们包含并行会话的额外未提交改动；本报告的代码结论以提交对象为准，且 F1 探针涉及的 `responses.py` 与 `handler.py` 已用 `git diff --exit-code eb93215 -- ...` 确认为与评审提交一致。测试绿灯仅作支持证据，不用于覆盖静态发现。

---

## 处置记录（2026-08-20，派发方补记）

评审 5 条发现，**全部采纳判断，其中 3 条落地为代码/文档改动，2 条记入延后项**。落地于 `1ac5ab2`。

### F1（major）— 已修，且我先独立复现过

不照单全收：先用 mock 上游探针查看**客户端实际收到的响应体**，得到

```
{'input_tokens': 138500, 'input_tokens_details': {...}, 'output_tokens': 2700, 'total_tokens': 141200}
```

确认这不只是日志差异，而是**下游契约被破坏**——Anthropic 客户端拿到自己没有 schema 的键，且 `input_tokens` 的含义与它的理解相反。

同时确认了评审的因果判断：`stream.py:180` 在 `eb93215` 之后发的是换算后的 usage，非流式仍逐字透传，**这个不对称是 `eb93215` 造成的**，而 `eb93215` 的提交信息里「缓冲路径已经换算过」这句话是错的（它只对旧的 `app.anthropic.client` 路径成立）。修复与更正一并写进 `1ac5ab2` 的提交信息。

修法采纳评审建议：在 `from_openai_responses_response` 复用 `anthropic_usage_from_responses`，不另写减法。格式非法时留空而非透传原形状，与流式路径同姿态。

### F4（minor）— 已修，并纠正我自己的一个错误认识

评审说仓库 cassette 里已有真实 usage。我最初用纯文本 grep 搜 `cached_tokens` **搜不到**，一度以为评审说错了；实际是 chunk 以 `{"text": ...}` 结构存储，我的检索方式不对。按结构解析后确认：

| cassette | input_tokens | cached_tokens | cache_write_tokens |
|---|---|---|---|
| `responses_web_search_stream` | 4693 | 3712 | 0 |
| `history_responses_stream` | 56919 | 55680 | **键不存在** |
| `anthropic_to_responses_stream` | 12 | 0 | 0 |

这组数据同时证明了两件手写 fixture 证明不了的事：`input_tokens` **含**缓存；`cache_write_tokens` **可能整个缺席**（所以 converter 默认取 0 是对的）。已在 `tests/integration/test_history_fixtures.py` 加一条基于录制的断言。

写测试时我把 `output_tokens` 凭印象写成 218，录制里是 637——输入侧三项一次命中，说明换算正确，而那个错数字正好说明**手写期望值的风险**，与本条发现同源。

### F5（minor）— 已修

SPEC 第 91 行残留的「灰、白两侧」改为「灰、不着色两侧」。

### F2、F3（minor）— 未落地，记入 `deferred.md` 第 0.5 条

丢弃 `ResponseConversionFact` / `ResponseUsageFacts`，以及 malformed 与 absent usage 在运行时不可区分。**不做的理由**：两者的修法要么把 facts 挂到某处再由有 request context 的层消费（独立切片），要么在 pipeline 层直接打日志——而**当前 `src/app/pipeline/` 下没有任何模块 import `app.observability.logging`**，为一个 minor 引入这个依赖方向不划算。评审自身也评为 minor 且不建议为此中断响应。

### 评审明确不建议采纳的事项，我同意并遵守

- 不重回「按显示数字设阈值」（用户已裁决）。
- 不把 `volume_colour` 的空字符串哨兵改成 `str | None`。
- 不让 malformed usage 抛错中断已交付的响应。
- 不为此实测真实上游——现有 cassette 已回答字段结构问题。
- 不新增覆盖率指标、门禁或证明基础设施。
