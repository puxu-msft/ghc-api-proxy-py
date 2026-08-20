# 延后项：TUI 请求日志

本文件记录**已经想到、但本次未做**的事，以及为什么没做。用于避免下一次把同一个问题再想一遍，也避免有人误以为这些是遗漏。

权威来源：`spec.md`（行为契约）。本文件只登记尚未进入契约的候选。

## 0. `/responses` 与 `/chat/completions` 入站的回复汇总为空

**优先级最高的一条**，因为它是**功能缺失**而非用词问题。

**现状**：日志行里描述回复内容的那几个字段（推理块、工具调用、stop reason、token 用量）目前只在**入站格式是 Anthropic Messages** 时才有。`handler.reply_summary` 对其它入站格式返回 `None`，那些行就完全不报告回复内容。

**为什么**：缓冲回复被读回时，payload 已经是**客户端**要的形状（`response_payload` 的产物），而现有读取器 `blocks_from_anthropic` 只认 Anthropic 的 `content` 块。`/responses` 入站的 body 带的是 `output`，读不到任何东西——而且是**静默**读不到，因为「没有 content」与「回复本来就是空的」无法区分。

**这不是本次引入的**：改动前同样读不到，只是当时表现为「什么都不显示」。2026-08-20 的 `f8f5854` 一度让它变成显示一个伪造的 `end_turn`（`Terminal` 类默认值经聚合记录进入日志行），该回归当日已修，并由 `tests/http/test_pipeline_app.py::test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it` 钉住。

**要做需要什么**：一个 Responses 形状的读取器（`blocks_from_responses`，镜像 `ResponsesAssembler._close` 的块构造），外加 Responses 自己的 usage 与 stop reason 读法。

**为什么没顺手做**：usage 的键不同。现在的数字取自翻译后的 Anthropic 形状（`cache_read_input_tokens` 等），`format_tokens` 依赖这套键；改从 Responses 原始 body 读会变成 `input_tokens_details.cached_tokens`，波及**主产品路径**（`/v1/messages` → Responses 上游）的 token 列。这是一个独立切片，不该塞进用词改动里。

**判断**：值得做，但 ROI 取决于 `/responses` 入站实际有多少流量——本项目的主产品路径是 Anthropic Messages 入站，这条是次要面。**证据强度：现象已由 mock 上游复现，可据此行动；流量占比未测，属于待确认。**

## 0.5 上游 usage 自相矛盾时，这条信号在当前管线里没有落点

**现状**：`protocols/responses_anthropic.py` 的 `_convert_usage` 除了产出数字，还会产出 `ResponseConversionFact`（`usage_inconsistent`：缓存明细之和大于 `input_tokens`、`reasoning_tokens > output_tokens`、`total_tokens` 对不上）与 `ResponseUsageFacts`（保留 `reasoning_tokens` 与上游原始 totals）。

2026-08-20 新增的公开包装 `anthropic_usage_from_responses()` **只返回 `.wire`**，把 facts 与 exact usage 都丢掉了。流式路径（assembler）与缓冲路径（translation_driver）都用这个包装，所以当前主管线两条路都不保留这些信号。旧的 `app.anthropic.client` 路径会把它们放进 context / history，但那条路不是现在的主路。

**后果**：`_convert_usage` 用 `max(0, ...)` 仍会产出可交付的数字，于是**上游报了自相矛盾的 usage 时，管线照常给出看起来正常的数字，而没有任何地方说明它来自矛盾输入**。

**同类的第二个缺口**：usage 格式非法时（`ResponseConversionError`），两处都返回 `{}` 并继续交付。这在优先级上是对的——不能为一个没人在等的计数中断已交付的响应——但运行时**没有任何信号**，「上游没报 usage」与「上游报了坏数据」在日志上完全一样。异常本身带着 `code` 与 `field_path`，现在被丢弃。

**为什么本次没做**：修法需要把 facts 挂到某处并让有 request context 的层去消费，或者在 pipeline 层直接打日志。后者是新的依赖方向——**当前 `src/app/pipeline/` 下没有任何模块 import `app.observability.logging`**，为一个 minor 引入这个方向不划算。前者是独立切片。评审同样评为 minor，且明确不建议为此中断响应。

**倾向**：值得做，优先级低于第 0 条。做的时候应当一并处理，别只补一半。

## 1. Responses 上游的 stop reason 仍是合成词

**现状**：2026-08-20 起，日志行对推理块与工具调用已按上游用词区分（`think` / `reason`，`tool_use` / `function_call`，见 `spec.md` 的「描述回复的用词跟随上游」）。但同一行上的 `end_turn` 与 `max_tokens` **在 Responses 上游同样是合成的**：

| 行上显示 | Responses 实际发的 |
|---|---|
| `end_turn` | `response.completed`（没有 stop reason 这个概念） |
| `max_tokens` | `response.incomplete` + `incomplete_details.reason = "max_output_tokens"` |

**为什么没做**：用户本次只指定了推理块与工具调用两处。扩大到 stop reason 会改变更多行的可观察输出，属于用户未裁决的范围。

**留下的不一致**：一条 Responses 行现在可能读作 `function_call(Bash)`（上游真名）紧邻 `end_turn`（合成词），词汇是一半一半的。这是已知的、有意接受的状态，不是疏漏。

**决定时需要的信息**：`end_turn` 出现在几乎每一行上，改词的影响面远大于 `tool_use`；而 `tool_use` 只在工具轮出现。两者 ROI 不同，值得分开裁决。

## 2. `enc` / `txt` 两个计数标签未按上游改名

**现状**：`think(enc:1,txt:2)` 里的 `enc` / `txt` 在两种上游下用同一组词。真实名称在 Anthropic 侧是 thinking 块有无正文，在 Responses 侧是 `encrypted_content` 与 reasoning summary。

**为什么没做**：同上，用户未指定；且这两个标签是**分类**而非上游的字段名，`enc` / `txt` 在两侧表达的语义是同一个（有没有可读的推理正文），改名的收益不明显，而宽度成本是每行都付。

**倾向**：不建议改。若要改，更值得先确认的是这个分类本身是否还有人在用。

## 3. `[GONE]` 分不出「客户端走了」与「我们自己关停了」

**现状**：三种结局里最后一档由「两个标记都没置上」判定——`_tracked_delivery` 的 `async for` 既没正常跑完（`drained`），也没抛出异常（`failure`），也就是 GeneratorExit 或 CancelledError 从 `yield` 处展开。这同时覆盖两件事：客户端按 Esc 或断线走人，以及**关停时本进程取消自己的在途流**。后者里客户端还在，走掉的是我们。

**为什么措辞仍然成立**：detail 写的是 `delivery stopped before upstream finished`——没人收到答案、交付先于上游结束，两种情形都为真。`[GONE]` 同理：都不是本代理或上游的过错。所以这不是错误，是**分辨率不足**。

**要做需要什么**：让关停路径在取消在途流之前给 `_StreamAccounting` 留一个标记（关停是本进程自己发起的，它知道自己在做什么），再在 `_ending()` 里多一档。技术上不难，难在判断值不值：关停时终端通常正在被 SIGTERM 收走，那批行有没有人读是个问题。

**判断**：**证据强度仅为「已想到」，未观测到任何人因此误判过**。不建议在没有真实困扰之前做——多一档就多一个要维护的词，而这条区分只在关停这一个窗口内有意义。若将来关停诊断成为议题，这是现成的接入点。
