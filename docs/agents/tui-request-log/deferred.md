# 延后项：TUI 请求日志

本文件记录**已经想到、但本次未做**的事，以及为什么没做。用于避免下一次把同一个问题再想一遍，也避免有人误以为这些是遗漏。

权威来源：`SPEC.md`（行为契约）。本文件只登记尚未进入契约的候选。

## 0. `/responses` 与 `/chat/completions` 入站的回复汇总为空

**优先级最高的一条**，因为它是**功能缺失**而非用词问题。

**现状**：日志行里描述回复内容的那几个字段（推理块、工具调用、stop reason、token 用量）目前只在**入站格式是 Anthropic Messages** 时才有。`handler.reply_summary` 对其它入站格式返回 `None`，那些行就完全不报告回复内容。

**为什么**：缓冲回复被读回时，payload 已经是**客户端**要的形状（`response_payload` 的产物），而现有读取器 `blocks_from_anthropic` 只认 Anthropic 的 `content` 块。`/responses` 入站的 body 带的是 `output`，读不到任何东西——而且是**静默**读不到，因为「没有 content」与「回复本来就是空的」无法区分。

**这不是本次引入的**：改动前同样读不到，只是当时表现为「什么都不显示」。2026-08-20 的 `f8f5854` 一度让它变成显示一个伪造的 `end_turn`（`Terminal` 类默认值经聚合记录进入日志行），该回归当日已修，并由 `tests/http/test_pipeline_app.py::test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it` 钉住。

**要做需要什么**：一个 Responses 形状的读取器（`blocks_from_responses`，镜像 `ResponsesAssembler._close` 的块构造），外加 Responses 自己的 usage 与 stop reason 读法。

**为什么没顺手做**：usage 的键不同。现在的数字取自翻译后的 Anthropic 形状（`cache_read_input_tokens` 等），`format_tokens` 依赖这套键；改从 Responses 原始 body 读会变成 `input_tokens_details.cached_tokens`，波及**主产品路径**（`/v1/messages` → Responses 上游）的 token 列。这是一个独立切片，不该塞进用词改动里。

**判断**：值得做，但 ROI 取决于 `/responses` 入站实际有多少流量——本项目的主产品路径是 Anthropic Messages 入站，这条是次要面。**证据强度：现象已由 mock 上游复现，可据此行动；流量占比未测，属于待确认。**

## 1. Responses 上游的 stop reason 仍是合成词

**现状**：2026-08-20 起，日志行对推理块与工具调用已按上游用词区分（`think` / `reason`，`tool_use` / `function_call`，见 `SPEC.md` 的「描述回复的用词跟随上游」）。但同一行上的 `end_turn` 与 `max_tokens` **在 Responses 上游同样是合成的**：

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
