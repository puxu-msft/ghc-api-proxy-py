# `delivery/` 重排评审报告(HEAD `8312133`)

**评审对象**：`8312133 refactor: name the generic parts generically and the format-specific parts by format`，只读评审，未修改任何文件。

**方法**：`git show HEAD --stat` / `git show HEAD` 通读全部 hunk；对 `src/app/pipeline/delivery/` 现状逐文件 `Read`；`rg` 扫全仓(含 `.dev/`)找旧模块名/旧符号名残留；用一段 AST 脚本把旧 `assembler.py`/`anthropic_sse.py`/`responses_sse.py` 与新 `assembling.py`/`formats/anthropic_messages.py`/`formats/openai_responses.py` 按顶层函数/类(含方法)逐个配对做文本级 diff，规避重排导致的行序错位；额外对 `sse_frame.py` 单独核对。跑了 `uv run ruff check`(delivery 相关路径)与 delivery 相关 pytest 子集(228 个用例，未跑全量 1705)。

## 逐模块判定

| 模块 | 定位声称 | 判定 | 说明 |
|---|---|---|---|
| `delivery/__init__.py` | 包级说明 + 重导出 | **成立，有一处文档瑕疵** | 两条轴线的划分描述准确；但 docstring 说"formats 下每种格式一个模块"，实际 `formats/` 有 3 个文件(见下)。`__all__` 对比旧版无遗漏，新增 6 个符号(见「未丢失」一节)。 |
| `delivery/assembling.py` | 通用：装配契约 + `Terminal`/`Draft`/`decode_json` | **成立** | `ReplyDialect`、`Terminal`、`BlockAssembler`、`Draft`、`decode_json` 均不引用任何格式细节，只导入 `blocks`(THINKING/TOOL_USE 常量)与 `sse_source.SseEvent`。逐符号 diff 与旧 `assembler.py` 对应部分一致(见下)。 |
| `delivery/blocks.py` | 通用：块与缓冲策略 | **成立，一处值得记录的设计取舍(非本次引入)** | `CompletedBlock` 的 docstring 自己承认"kind 是 Anthropic 的词汇"；这是预先存在的规范化决定(任何上游都被装配成 Anthropic 形状的块)，非本次改动新增的错配，也在 `formats/openai_responses.py` 顶部说明("`CompletedBlock` 被定义为……Anthropic content block")。 |
| `delivery/framing.py` | 通用：`OutboundFramer` 契约 | **成立** | 只依赖 `assembling.Terminal` 与 `blocks.CompletedBlock`，不引用任何格式实现。 |
| `delivery/sse_frame.py` | 通用：线层帧结构 | **成立** | 与旧 `anthropic_sse.py::SseFrame` 逐字节比对完全一致，只是搬了家。docstring 准确描述了它以前寄居在 Anthropic 模块里的历史。 |
| `delivery/sse_source.py` | 通用：线层解析(本次未改) | **成立** | 未改动，纯生成/解析 SSE 帧，无格式知识。 |
| `delivery/stream.py` | 通用：投递循环 | **成立，但有一处遗留的不对等，非本次引入** | 第 22 行 `from app.pipeline.delivery.formats.anthropic_messages import AnthropicFramer`，第 262 行把它当默认 `framer`。这意味着"通用"的投递循环在没有显式传入 framer 时，默认值硬编码为某一个具体格式类——这是重构前就有的行为(旧代码同样 `from app.pipeline.delivery.anthropic_sse import AnthropicFramer`)，本次只是原样换了 import 路径，不是新缺陷，但和提交信息里"两个平等格式"的整体叙事有一点出入，值得注记(详见发现 F2)。 |
| `delivery/formats/__init__.py` | "one module per wire format" | **有问题(文档瑕疵)** | 同 `__init__.py`，与实际 3 个文件不完全吻合(详见 F3)。 |
| `delivery/formats/anthropic_messages.py` | Anthropic Messages：装配器+成帧器 | **成立** | 只依赖通用层(`assembling`/`blocks`/`sse_frame`/`sse_source`)与 `app.config.schema`，不 import `openai_responses`。逐符号 diff 与旧 `anthropic_sse.py`+旧 `assembler.py` 对应部分完全一致(仅 `Draft`/`decode_json` 多了两段新增 docstring，无逻辑改动)。 |
| `delivery/formats/openai_responses.py` | OpenAI Responses：装配器+成帧器 | **有问题(文档遗留引用)** | 结构上同样只依赖通用层，不 import `anthropic_messages`，符合"平等"。但模块 docstring 里两处仍写着旧模块名 `anthropic_sse`(应为 `anthropic_messages`)，见发现 F1。 |
| `delivery/formats/anthropic_messages_synthetic.py` | Anthropic Messages 专属：搜索失败合成回复 | **成立，命名可以再考虑** | 内容确实只写 Anthropic Messages 形状；新增的一句"该文件在此之前的名字说不出是哪种格式"准确对应用户原话。命名本身满足了用户"要说明格式"的诉求，但仓库里"synthetic/synthesize"这个词还有另外两个不相关的含义(见 F4)，本次改动没有加剧也没有解决这层歧义。 |

## 发现清单(按严重度)

- **F1(有问题)** `src/app/pipeline/delivery/formats/openai_responses.py:3` 与 `:59`：docstring 仍写"The mirror of `anthropic_sse`"和"where `anthropic_sse` is a set of functions"，这两处引用的旧模块名已经在本次改动里被重命名成 `anthropic_messages`，属于重命名后遗留、未同步的引用。改法：把这两处 `anthropic_sse` 替换成 `anthropic_messages`。

- **F2(存疑)** `src/app/pipeline/delivery/stream.py:22,262`：号称"通用"的投递循环把 `AnthropicFramer` 作为 `framer` 参数缺省值硬编码进来，这处调用点两个格式并不对等。这是重构前就有的行为(旧代码同样从 `anthropic_sse` 引入并默认这个类)，本次改动没有引入新问题，只是把 import 路径原样换掉；是否需要处理(比如要求调用方总是显式传入 framer，去掉这个默认值)超出本次"重命名"授权范围，留给用户判断是否值得作为独立事项跟进。

- **F3(有问题，小)** `src/app/pipeline/delivery/__init__.py:6` 与 `src/app/pipeline/delivery/formats/__init__.py:1`：都写"one module per wire format"，但 `formats/` 下实际是 3 个文件——`anthropic_messages.py`、`anthropic_messages_synthetic.py`、`openai_responses.py`，其中前两个都属于同一种格式(Anthropic Messages)。docstring 的"一个格式一个模块"是不准确的过度简化。改法：改成类似"一种格式至少一个模块"或直接点名 `anthropic_messages_synthetic` 是 Anthropic Messages 格式的第二个模块。

- **F4(信息/存疑，非本次改动引入)** `anthropic_messages_synthetic.py` 的"synthetic"与仓库另外两处用法重名但不同义：`app/server/handler.py` 的 `HandledRequest.synthesized`(整条回复是本代理自己写的)，以及 `app/pipeline/delivery/stream.py` 的 `ContinuationSupport.synthesize`(流中途把工具调用收尾)。三处叫同一个词却是三件不同机制，容易在跨文件搜索或交接时认错。本次改动只是给旧 `synthetic.py` 加了格式前缀，未触碰这层歧义，是否要进一步改名(如 `anthropic_messages_search_refusal.py`)不在用户裁定的整改范围内，仅记录供参考。

- **F5(信息，范围外)** `rg` 命中 `.dev/exp/260820-streaming-and-timeouts/rev-idle-impl/probe_close_chain.py:9` 与 `probe_close_chain2.py:8` 仍 `from app.pipeline.delivery.assembler import AnthropicAssembler`，现在会 ImportError。`.dev/` 是独立仓库且这两个是一次性实验脚本，不属于本次评审范围，仅记录。`.dev/docs/upstream/retry-and-continuation/status.md` 等文档里的旧路径引用都带着"本节描述的是主仓 `8a36fe3`"这类锚点，属于按项目约定允许的历史快照写法，不算失真。

## 未丢失的确认(逐符号级)

- 用 AST 把旧 `assembler.py`+`anthropic_sse.py`+`responses_sse.py` 与新 `assembling.py`+`formats/anthropic_messages.py`+`formats/openai_responses.py` 的顶层函数/类/方法各自抽取(58 个符号)逐一配对比对文本(先做 `_Draft→Draft`、`_decode_json→decode_json`、`TOOL_USE_KIND→TOOL_USE` 的机械改名归一化)：**56 个逐字节相同，2 个(`Draft`、`decode_json`)只多了新增的 docstring，逻辑代码零改动**。
- `SseFrame`(含 `.encode`)单独核对：旧 `anthropic_sse.py` 与新 `sse_frame.py` 逐字节相同。
- 包级 `__all__`：旧版 18 个符号全部存在于新版(`TOOL_USE_KIND`→`TOOL_USE` 属提交内说明过的改名)，新版另外新增 `TEXT`、`THINKING`、`AnthropicFramer`、`OutboundFramer`、`ReplyDialect`、`ResponsesFramer` 六个符号(这些之前只能从子模块直接 import，现在包根也能拿到)——是扩大导出面，不是丢失。

## 两个格式模块"平等"性核查

`formats/anthropic_messages.py` 只 import 通用层(`assembling`/`blocks`/`sse_frame`/`sse_source`)与 `app.config.schema`；`formats/openai_responses.py` 只 import 通用层与 `app.pipeline.server_tool_text`/`app.pipeline.translation_driver.reasoning_carrier`/`app.protocols.responses_anthropic`。两者互不 import 对方，共享符号(`SseFrame`、`Draft`、`decode_json`、`TEXT`/`THINKING`/`TOOL_USE`)全部归属通用层，没有一个格式充当另一个的基准。**成立**——但见 F2，`stream.py` 这个通用调用点仍然对 Anthropic 有隐性偏向，"平等"只在 `formats/` 目录内部严格成立。

## 命名一致性核查

`formats/anthropic_messages.py`、`formats/openai_responses.py` 与 `direct_driver/anthropic_messages.py`、`direct_driver/openai_responses.py`、`translation_driver/anthropic_messages.py`、`translation_driver/openai_responses.py` 拼写完全一致，也和 `WireFormat.ANTHROPIC_MESSAGES`("anthropic-messages")/`WireFormat.OPENAI_RESPONSES`("openai-responses") 的取值同源(蛇形/短横线两种大小写是仓库既有惯例，不是新引入的不一致)。**成立**，没有新引入的拼写不一致。`anthropic_messages_synthetic.py` 见 F4。

## 漏网检查(全仓 rg)

`responses_sse`、`delivery.assembler`/`delivery import assembler`、`delivery.synthetic`/`delivery import synthetic`、`TOOL_USE_KIND`(作为被使用的符号，而非注释里的历史说明)、`_Draft`、`_decode_json`：**src/、tests/ 范围内零残留**。`anthropic_sse` 在 `src/app/delivery/`(legacy 包，题目已明确排除)、`config/schema.py` 的 `hook_fix_anthropic_sse` 配置字段名(与本次重命名无关，是独立的配置项名字)、以及 F1 提到的两处文档遗留引用之外，没有别的命中。

## 验证

- `uv run ruff check src/app/pipeline/delivery tests/unit/pipeline/delivery tests/int/test_history_fixtures.py tests/int/test_pipeline_app.py` → 全部通过。
- `uv run pytest tests/unit/pipeline/delivery tests/int/test_history_fixtures.py tests/int/test_pipeline_app.py -q` → 228 passed(未跑全仓 1705 条，仅对本次改动直接相关的子集做了抽查，与提交信息里"1705 tests pass"的说法不冲突，只是没有独立复核全量)。

## 总体裁决

「通用 vs 格式特定」这条线基本立住：`assembling`/`blocks`/`framing`/`sse_frame`/`sse_source`/`stream` 五个通用模块干净、`formats/anthropic_messages.py` 与 `formats/openai_responses.py` 互不依赖、真正平等，符号搬移经逐个比对确认零逻辑丢失(仅两处新增 docstring)。存在一处应改的遗留引用错误(F1，`openai_responses.py` 里两处仍写旧模块名 `anthropic_sse`)和一处文档表述过度简化(F3，"一个格式一个模块"与实际 3 个文件不符)，两处都是小改动量级；F2、F4 是设计/术语层面的存疑项，均非本次改动引入，是否处理留给用户裁定。
