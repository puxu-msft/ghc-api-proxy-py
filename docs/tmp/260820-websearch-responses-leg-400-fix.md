# Responses 腿 web_search 声明 400 的止血修复

日期：2026-08-20
性质：故障分析 + 已落地的止血修复 + 对 `hosted-web-search-spec.md` 的两处事实更正

## 1. 现象

```
[FAIL] 13:30:57 H1 400 POST /v1/messages gpt-5.6-sol 226ms: upstream rejected the request: Error code: 400 - {'error': {'message': "Invalid value: 'web_search_20250305'. Supported values are: 'code_interpreter', 'programmatic_tool_calling', 'function', 'namespace', 'tool_search', 'file_search', 'web_search_preview', 'web_search_preview_2025_03_11', 'image_generation', 'mcp', 'custom', 'computer', 'computer_use_preview', 'shell', and 'apply_patch'.", 'code': 'invalid_request_body'}}
```

Anthropic 客户端声明了 web search server tool，模型 `gpt-5.6-sol` 路由到 Responses 腿，声明被**原样**发给 `/responses`，上游拒绝整轮。客户端下一轮重放同一份声明，于是同样失败——每一轮都失败。

## 2. 根因

在产链路是 `pipeline_app`（`ghc_client` + `src/app/pipeline/translation_driver/`）。请求侧工具转换落在 `src/app/pipeline/translation_driver/openai_responses.py` 的 `_function_tool()`，它开头一句是：

```python
if "input_schema" not in tool:
    return tool
```

这条捷径的本意写在它自己的 docstring 里——「一个看起来已经是 Responses 工具的声明就别改它，好让 Responses→Responses 直通不被重写」。判据取的是「有没有 `input_schema`」。

而 Anthropic 的 server tool 声明恰好没有 `input_schema`：

```json
{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
```

于是它命中了「已经是 Responses 工具」这一分支，原样透传。判据问的是「这是不是 Anthropic function tool」，答案是「不是」；它被当成了「那就是 Responses 工具」，而第三种可能——Anthropic 的 server tool——不在这个二分里。

### 两道本应拦住它的守卫都不在这条链路上

- `src/app/protocols/anthropic_responses.py:539` 的 `server_tool_not_supported`：只被 `src/app/anthropic/client.py` 调用，属 legacy 链路。
- `src/app/pipeline/subscribers/server_tools.py` 的 `builtin:server-tool-capability`：门控是 `context.target_format is WireFormat.ANTHROPIC_MESSAGES`，按设计只作用于 Anthropic 腿，Responses 腿不在它的范围内（它的 docstring 明说「Responses 腿需要自己的答案」）。

复现（`_function_tool` 的直接输入输出，修复前）：

| 输入 | 输出 |
|---|---|
| `{"type":"web_search_20250305","name":"web_search","max_uses":5}` | 原样返回 |
| `{"name":"Bash","input_schema":{...}}` | `{"name":"Bash","type":"function","parameters":{...}}` |

## 3. 已落地的修复

改动四个文件：

- `src/app/pipeline/translation_driver/semantic.py`：新增 `LossCode.SERVER_TOOL_NOT_CARRIED`。
- `src/app/pipeline/translation_driver/openai_responses.py`：新增 `_is_anthropic_server_tool()` 与 `_tools_for_upstream()`，`to_openai_responses()` 改走后者。
- `tests/unit/test_translation_driver.py`：7 个回归测试（含 `web_fetch` 边界与 `tool_choice` 的一正一反）。
- `tests/http/test_pipeline_app.py`：1 个端到端测试，断言在**上游实际收到的字节**上。

### 判据：读日期后缀，不读家族前缀

```python
_ANTHROPIC_SERVER_TOOL_FAMILIES = ("web_search_",)
# 命中条件：type 以其中之一开头，且剩余部分恰好是 8 位 ASCII 数字
```

**不能用裸前缀**，这是本次最容易写错的一处：上游 400 消息自己列出的合法值里就有 `web_search_preview` 与 `web_search_preview_2025_03_11`，两者都以 `web_search_` 开头。一条 `startswith("web_search_")` 的判据会把它们从 Responses→Responses 直通里剥掉——那是完全合法的请求。

反过来，**也不能逐字匹配 `web_search_20250305`**：Anthropic 给 server tool 打日期版本，逐字匹配会在下一个日期版本上静默失效。读 `<family>_<YYYYMMDD>` 这个形状同时避开两边。

（`isdigit()` 之外还要 `isascii()`：前者单独用会接受其他文字系统的数字字符。）

**`web_fetch_` 曾在这个清单里，评审后移除**（处置见 §7 的 A 条）。它与 `web_search` 该得到的处置不同：spec §8.3 要求 web search 被剥离而对话继续，§13 要求 `web_fetch` 被**本地明确拒绝**，让客户端知道这个工具不可用，而不是被静默地少给一个能力。在这里剥掉它两样都给不了，而且它不是本次故障的内容。移除后它回到原样透传、上游 400，与 `bash_20250124` 等同类缺口处境一致（§5.1）。已加一条测试固化这个边界——把 `web_fetch_` 加回清单是一个看起来像「补全」的单词级改动，没有别的东西会反对。

### 行为

| 输入 | 发往上游的 `tools` |
|---|---|
| 只有 `web_search_20250305` | 整个 `tools` 键不出现（不是 `[]`） |
| `web_search_20250305` + 一个 function tool | 只剩那个 function tool |
| `web_search` / `web_search_preview` / `web_search_preview_2025_03_11` | 原样保留 |
| `web_fetch_20250910` | **原样透传，未改**（评审后移除，见 §7 的 A 条） |
| `web_search_20991231`（未来版本） | 剥离 |
| `bash_20250124` 等客户端执行型 typed tool | **原样透传，未改**（见 §5） |

剥离时记一条 `SERVER_TOOL_NOT_CARRIED` loss，并打一条 INFO 日志。

**为什么日志不能省**：`Conversion` 的 loss 经 `src/app/server/handler.py:94` 写进 `context.extras["conversion_losses"]`，而这个键**今天没有任何消费者**——写进去就没了。只记 loss，运维在日志里看不到搜索为什么从不执行，正是 spec §9.3 说的「假阴性：用户以为搜了、其实没搜」。INFO 级别与 Anthropic 腿订阅者的同一决策一致：一个开了 web search 的客户端每轮都会触发，所以它是设置而不是警告；但它确实移除了客户端以为自己有的能力，运维不该为了查明这一点去开 debug。

### 验证

- `tests/unit/test_translation_driver.py`：34 passed。
- `tests/http/test_pipeline_app.py` 的端到端测试断言在**上游实际收到的字节**上（`b"web_search" not in seen[-1].read()`），不是翻译函数的返回值。这一点是刻意的：这个缺陷恰恰是从一条捷径穿过去的，而工具转换的每一个单元测试都从它旁边走过——`_function_tool` 放行任何没有 `input_schema` 的声明，而 Anthropic server tool 也没有 `input_schema`。只测翻译函数的人看不见这条路。
- 变异验证（证明新测试有鉴别力，已还原）：
  - 屏蔽 `_is_anthropic_server_tool` 谓词 → 3 个单元测试红，端到端测试也红。
  - 去掉 8 位日期检查、退回裸前缀 → 「上游合法拼法不被误伤」那条红。
  - 关掉悬空 `tool_choice` 清理 → 该条红；改成无条件清理 → 它的对照条红。
- 全量：`uv run pytest -q --ignore=tests/tui` → **1402 passed, 2 skipped, 1 failed**（该次全量跑在端到端测试加入之前；加入后 `tests/http/test_pipeline_app.py` 与 `tests/unit/test_translation_driver.py` 合跑 90 passed）。
- Ruff `check`、Pyright 于改动文件均干净。

**唯一的失败与本次改动无关**：`tests/unit/test_lifecycle_pidfile.py::test_writing_leaves_no_temporary_behind`。原因是并行会话新增的未跟踪文件 `tests/unit/conftest.py`，其 autouse fixture 在 `tmp_path` 下建了 `xdg-data` 目录，而该测试断言 `tmp_path` 里只有 `standalone.pid`。归属并行会话，本次不动。

## 4. 范围裁决：为什么是剥离，而不是按 spec 做映射

`docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md`（DRAFT，用户已裁决 D1／D4／D6）要求的是**映射**：把声明译成 `{"type":"web_search"}`，让上游真正执行搜索，并在响应侧合成 `server_tool_use` + `web_search_tool_result` 块。本次**没有**实现它。

理由，按可证的代价排列：

1. ~~**只做请求侧映射会把 400 换成一个更糟的失败。**~~ **这条理由是错的，经独立评审证伪，保留在此并注明。** 我当时写的是「映射之后上游会真的执行搜索，回复里带 `web_search_call` item，而响应侧今天没有承接它的地方（现有 parser 会落进 `UnsupportedResponsesEvent` 的默认分支）」。

   `UnsupportedResponsesEvent` 在 `src/app/openai/responses_stream_parser.py` 与 `src/app/delivery/anthropic_sse.py`——**都属 legacy 链路**，`src/app/pipeline/` 下没有它。在产链路的实际行为是**静默降级**：`src/app/pipeline/translation_driver/responses.py:141-145`，未知 item 走 `BlockKind.UNKNOWN`，记一条 `ITEM_NOT_CARRIED` 然后**丢弃**，正文照常交付。流式路径按评审实测是多出一个空 text 块。**没有任何路径会整轮失败。**

   这个错误值得点名，因为它与我在 §6.1 给 spec 指出的错误是**同一个**——把 legacy 链路的行为当成在产行为。我在同一份文档里先纠正了别人，又自己犯了一次。

2. **完整实现是七个面的大工程**，且 spec §15 明确写着「实现前必须先关闭 MJ-1／MJ-2／MJ-4／MJ-5／MJ-7／MJ-8 与全部 minor」。这条成立。
3. **剥离不是白工，但它也不是完整实现的真子集**（这处措辞经评审纠正）。它照搬的是 spec §8.3「路由到 Responses 腿但能力门未通过」那一支的**行为**——剥离声明、记 `DEGRADE`、输出 INFO 日志、不 `REJECT` 整个请求。但 spec 的能力门对 `gpt-5.6-sol` 这类模型会**判定通过**并要求映射，所以本次是**无条件**应用了那一支的行为。准确的说法是：**临时止血降级**，落地完整实现时这段代码是能力门为假的那一支，而判据本身要换。

### 4.1 理由 1 被证伪后浮现的第三条路（待用户裁决）

既然响应侧不会失败，就存在一个我原先没有呈上的选项：

**选项 C：请求侧映射 `{"type":"web_search"}` + 模型允许清单，响应侧不动。**

搜索会**真的执行**，答案带着搜索结果回到客户端——结果本来就在正文里而不在 `web_search_call` item 里（spec §5.1 已证实该 item 通篇只有一个 query）。客户端拿不到的是 spec D6 要求的 `server_tool_use` + `web_search_tool_result` 块形态，以及流式下可能多收一个空 text 块。

它比本次的剥离更接近用户 2026-08-20 的裁决方向（「该路径要正确支持 server tool web_search」）。**但它不是一个纯增量的小片**，至少要一并带上两件事，否则会踩到用户已经裁决过的东西：

- **能力门是必须的，不是可选的。** 广告 `/responses` 的模型里有 `grok-4.5`、`grok-4.6`、`mai-code-*` 等**全部未探针**的非 OpenAI 模型（spec §9.2）。没有清单就直接映射，等于把 400 从 web search 客户端转嫁到这些模型上。
- **`allowed_domains` / `blocked_domains` 不能静默丢。** 用户裁决 D1 要求默认 `error` 大声报错。这两个字段写入上游一律 400（spec §3.4 三条独立实测），而静默丢弃会把用户明确要求的**收紧**变成 no-op，且**事后无法补救**——搜索结果不在我们手里。选项 C 若不带 D1 的 error 分支，就是在违反一条已裁决条款。

所以选项 C 的最小完整形态是「映射 + 允许清单 + D1 的 error 分支 + `max_uses` 剥离」。这是一片可控的工作，但它**改变产品行为**，且落在多个已裁决点上，因此**不由我径自实施，列为裁决点交用户**。

代价要说清楚：本次交付的剥离让**搜索不会执行**，客户端以为自己有这个能力而实际没有。这个取舍与 Anthropic 腿已在产的 `builtin:server-tool-capability` 完全一致——剥掉一个能力，好过整轮失败——但它不等于 spec 想要的产品形态，也不等于选项 C 能给的东西。

## 5. 已知缺口（本次未修，记账）

### 5.1 其他 Anthropic typed tool 仍会撞同一条捷径

`bash_20250124`、`text_editor_20250728`、`computer_20250124`、`memory_*`、`tool_search_*` 同样没有 `input_schema`，同样会被 `_function_tool` 原样透传给 `/responses`。

我起初写的免责理由是「按 spec §13『客户端执行型 typed tool 在 Responses 腿的处置：本规格不动，维持现状』」，**这是误引，经评审纠正**，两处都站不住：

- **spec 心目中的「现状」不是生产上的现状。** spec §3.6 描述的现状是 `protocols/anthropic_responses.py` 的**本地具名 REJECT**，客户端会收到一条说明问题的 400。而在产链路上根本没有那道守卫（这正是本文 §6.1 的内容），实际现状是静默透传后被上游拒绝。spec 说「维持现状」时，指的不是今天生产在做的事。
- **它们被上游拒绝也不是「猜测」。** 上游那条 400 自带的枚举点名了它接受的全部 `type`：`code_interpreter`、`programmatic_tool_calling`、`function`、`namespace`、`tool_search`、`file_search`、`web_search_preview`、`web_search_preview_2025_03_11`、`image_generation`、`mcp`、`custom`、`computer`、`computer_use_preview`、`shell`、`apply_patch`。`bash_20250124`、`text_editor_20250728`、`computer_20250124` 这些带日期的 Anthropic 拼法**一个都不在里面**。所以「没有实测所以不能动」的说法过强——枚举本身就是证据。

修正后的取舍理由只剩一条，但它足够：**它们该得到的是本地具名 REJECT，不是和 web search 一样的剥离**。剥离会让客户端以为自己有 `bash` 工具而模型从未被告知，而这些是**客户端执行型**工具——静默拿掉它们改变的是对话能做什么，不只是少一次搜索。做对需要一条本地拒绝路径，那是独立的一片。

**要点名的是**：在那一片落地之前，如果 Claude Code 在 Responses 腿上声明 `bash_20250124`，它会以与本次故障完全相同的方式打挂整轮，且没有任何东西会提示原因。这是同一根因的未修部分，不是已解决问题。`web_fetch_20250910` 现在也在这个清单里（§3 与 §7 的 A 条）。

### 5.2 `tool_choice` 跨协议时被整体丢弃（同格式路径的悬空已在本片修掉）

`SemanticRequest` 没有 `tool_choice` 字段。Anthropic 的 `tool_choice` 不在 `_ANTHROPIC_KEYS` 里，因此落进 `extensions`，而 `extensions_for()` 在 `source_format != wire_format` 时返回空并记一条 `EXTENSIONS_NOT_CARRIED`。

所以跨协议翻译时**客户端的 forced tool choice 根本没有到达上游**。这是一个独立缺口，与 spec §4 要求的 `tool_choice` 映射表直接冲突。**未修，未在别处记账，此处登记。**

**我起初据此写下「本次不需要清理悬空 `tool_choice`，因为没有东西可悬空」，这句话是错的，经评审证伪。** 同格式路径（Responses 入口 → Responses 上游）会**原样重放自己的 extensions**，`tool_choice` 因此存活。一个发了 Anthropic 拼法声明、又用 `tool_choice` 点名它的客户端，在剥离之后会留下一个指向不存在工具的 choice——把一个 400 换成另一个 400，等于修复在这条路径上无效。

实测（探针，修复前后各一次）：

| 路径 | 剥离前 `tool_choice` | 修复前结果 | 修复后结果 |
|---|---|---|---|
| Responses → Responses | `{"type":"function","name":"web_search"}` | **悬空保留** | 一并删除 |
| Anthropic → Responses | `{"type":"tool","name":"web_search"}` | 整体丢弃（extensions 不跨格式） | 同前，不受影响 |

已加 `_drop_dangling_tool_choice()`，判据与 Anthropic 腿 `server_tools.py` 的 `_drop_dangling_choice` 相同的两种情形：choice 点名的工具已不在，或 `tools` 整个没了。只在**确有声明被剥离**时才运行，并有一条对照测试保证「choice 仍指向存在的工具时不得删它」——两个方向都做过变异验证。

### 5.3 `conversion_losses` 没有消费者

`src/app/server/handler.py:94` 与 `:285` 把 loss 写进 `context.extras`，全仓库没有任何东西读它。所有翻译损失今天都不可观测。本次靠额外打 INFO 日志绕过，但这是逐点绕过，不是修复。

## 6. 对 `hosted-web-search-spec.md` 的两处事实更正

本文件不修改该 spec（它是 DRAFT 且由用户维护）。以下两点建议在其定稿前更正，否则照着它实现的人会改错地方：

### 6.1 §3.6 点名的文件不在产

spec §3.6 写着「对现有拒绝点的改动：`src/app/protocols/anthropic_responses.py` — `:538` `self._reject_extras(...)`、`:539-540` `if tool.type is not None: self._fail(...)`」，§5.4 与 §11 也把 `:409` 当作要改的位置。

**这些行属 legacy 链路**：`convert_messages_request_to_responses` 全仓库只有 `src/app/anthropic/client.py:250` 一个调用者。在产的 `pipeline_app` 走的是 `src/app/pipeline/translation_driver/openai_responses.py`。生产 400 恰好证明了这一点——如果请求经过了 §3.6 点名的那道守卫，得到的会是本地 400 `server_tool_not_supported`，而不是上游 400。

实现该 spec 时，请求侧的改动位置应是 `translation_driver/openai_responses.py`（或其上游的 pipeline 订阅者），不是 `protocols/anthropic_responses.py`。

### 6.2 §3.1 的识别判据会误伤上游合法值

**先说这条为什么依赖 §6.1**：只有在 spec 的目标文件被更正为在产的 `translation_driver/` 之后，「识别判据」才会被写进一个真的会执行的地方。在 legacy 文件里，§3.1 的判据无论宽窄都不影响生产。

spec §3.1 写着「识别判据**必须**是 `type` 以 `web_search_` 开头（含尾部下划线）」。

`web_search_preview` 与 `web_search_preview_2025_03_11` 都以 `web_search_` 开头，且都是 `/responses` 接受的合法值——它们就写在上游拒绝时打印的枚举里。按 §3.1 字面实现，会把这两个值从 Responses→Responses 直通里剥掉或错误映射。

本次采用的判据是 `<family>_<YYYYMMDD>`（8 位 ASCII 数字后缀），它同时满足 §3.1 想要的「不得逐字匹配日期版本」，又不误伤上游自己的拼法。建议 spec §3.1 按此收紧。

**一条已知的失败方向，记在这里而不是掩盖**：日期判据认的是「Anthropic 今天的拼法形状」。如果 Anthropic 将来发一个**不带 8 位日期**的 server tool 拼法，这条判据会**漏掉**它，表现为又一次上游 400。评审提出的替代方案是反过来做——维护一份**端点自有拼法的允许清单**，凡不在清单内的 `type` 一律剥离，那样的失败方向是「误剥一个上游新加的合法值」，比漏掉更容易被发现。这个方向更稳，但它要求我们持有一份上游 builtin 工具的完整清单，而那份清单目前只能从一条 400 的错误消息里读到，且**是按模型给的还是端点共用一份尚未区分**（spec §9.3 末尾已记此事）。因此本次不采用，登记为待办。

## 7. 评审处置

两位独立评审者（异源模型）各评审一轮，均绑定当时的 HEAD。合计 blocker 0、major 3、minor 5。

| # | 发现 | 严重度 | 处置 |
|---|---|---|---|
| A | `web_fetch_` 被一并剥离，违反 spec §13（该族应本地 REJECT 而非静默剥离） | major | **采纳。** 已从家族清单移除，并加测试固化这个边界。理由比评审给的更强一层：本次故障精确对应 `web_search`，`web_fetch` 是跟着 `server_tools.py` 的清单顺手加的，超出止血范围 |
| B | §4 首要理由「响应侧接不住 `web_search_call`」把 legacy 链路当成在产链路，实测证伪 | major | **采纳。** 已自行复核 `from_openai_responses_response`（`responses.py:141-145`）确认未知 item 记 `ITEM_NOT_CARRIED` 后丢弃、不失败。文档 §4 与代码 docstring 均已更正并注明这是我在同一份文档里犯的、与 §6.1 指出的同一个错误 |
| C | §5.1 误引 spec §13「维持现状」为其他 typed tool 免责 | major | **采纳。** 已重写：spec 说的「现状」是本地具名 REJECT 而非生产上的静默透传；且上游 400 的枚举已点名它接受的全部 `type`，那些带日期的拼法一个都不在，因此「未探针所以不能动」过强 |
| D | 「剥离是完整实现的真子集」措辞不严谨 | minor | **采纳。** 改述为「临时止血降级」：spec 的能力门对本次故障的模型会判定**通过**并要求映射，所以当前是无条件应用了能力门为假那一支的行为 |
| E | §5.2「没有东西可悬空」在同格式路径被证伪 | minor | **采纳并修代码。** 已自行探针复现，加 `_drop_dangling_tool_choice()` 及一正一反两条测试，两个方向都做过变异验证。见 §5.2 |
| F | 日期判据对「未来非日期拼法」失败方向不安全，建议改用端点允许清单 | minor | **记录，不采纳（附理由）。** 见 §6.2 末段：方向更稳，但要求一份我们目前只能从错误消息里读到、且尚不知是按模型还是按端点给的清单 |
| G | 存在第三条路：请求侧映射 + 模型允许清单，响应侧不动 | major（信息） | **采纳为裁决点，不径自实施。** 已写入 §4.1，连同它必须一并带上的能力门与 D1 域名限制处置 |
| H | INFO 日志是假阴性的唯一出口，却没有测试断言它 | minor | **未采纳。** 日志文案本身不是行为契约，为它加断言会把措辞钉死；`conversion_losses` 这条结构化出口才是该长出消费者的地方（§5.3），那是独立的一片 |

第一位评审者因 harness 限制未能落盘报告，其结论记录于本节。第二位的完整报告在 [`docs/tmp/260820-review-websearch-fix-second-opinion.md`](260820-review-websearch-fix-second-opinion.md)。

## 8. 相关文档

- 产品规格：[`docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md`](../agents/anthropic-responses-bridge/hosted-web-search-spec.md)
- 上游实测一手报告：[`docs/tmp/260820-websearch-upstream-probe.md`](260820-websearch-upstream-probe.md)
- Anthropic 腿的对应处置：`src/app/pipeline/subscribers/server_tools.py`
