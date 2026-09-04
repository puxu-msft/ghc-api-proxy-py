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

**为什么本次没做（2026-08-27 更正）**：修法仍有两路——把 facts 挂到某处并让有 request context 的层去消费，或者在 pipeline 层直接打日志。初版用「`src/app/pipeline/` 下没有任何模块 import `app.observability.logging`」论证后一条路会新建不划算的依赖方向；这个前提已被 `b973ed0` 之后的源码证伪，`src/app/pipeline/hand_over.py` 现在就从 `app.observability.logging` import `get_logger`。因此「要新开依赖方向」不再是推迟理由，但这不自动回答两种做法该选哪一种，也不自动改变优先级。

**倾向**：值得做，优先级低于第 0 条。做的时候应当一并处理，别只补一半。**本条仍未闭合；旧成本论证失效后，是否做与怎么做需要按当前接线重新评估，本文不替用户作出重估。**

## 1. 翻译型 Responses 路径的 stop reason 仍是合成词

**已从本条移出的定案**：原生 Responses 流式直连路径必须同时记录权威 `terminal_status` 与 typed `client_actions`；`completed` 只有在集合分类完备且不存在 required 或 unknown client-action fact 时才绿。该合同及用户 2026-09-03 的裁决已进入 [`spec.md`](spec.md)「着色规则」和 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §10，本条不再承载它。

**仍未闭合的现状**：翻译型 Responses 路径的日志行对推理块与工具调用已按上游用词区分（`reason`、`function_call`），但终局仍来自为 Anthropic 下游合成的 `end_turn` / `max_tokens`：

| 行上显示 | Responses 实际发的 |
|---|---|
| `end_turn` | `response.completed` |
| `max_tokens` | `response.incomplete` + `incomplete_details.reason = "max_output_tokens"` |

原生直连路径本轮新增的旁路 facts 不能自动解决这里：缓冲翻译路径在读回客户端形状时已经丢掉原生 response status，流式翻译路径则仍把 status 映成下游 stop reason。要让它们也显示权威 status，需要在翻译前保存同一份旁路事实，而不是从合成词反推。

**为什么仍留在本条**：用户本轮明确选择把端到端接线落在 direct `openai-responses`；翻译型路径是否同步改变每条 Responses 完成行的词汇与字段数，仍未裁决。`end_turn` 出现在几乎每条翻译型完成行上，影响面远大于工具轮，不能借直连路径的实现范围静默扩大。

**证据强度**：路径与数据丢失点已由源码和既有集成测试确认，足以据此设计后续切片；是否值得改变主产品路径的所有完成行，仍需用户决定。

## 3. `[GONE]` 分不出「客户端走了」与「我们自己关停了」

**现状**：三种结局里最后一档由「两个标记都没置上」判定——`_tracked_delivery` 的 `async for` 既没正常跑完（`drained`），也没抛出异常（`failure`），也就是 GeneratorExit 或 CancelledError 从 `yield` 处展开。这同时覆盖两件事：客户端按 Esc 或断线走人，以及**关停时本进程取消自己的在途流**。后者里客户端还在，走掉的是我们。

**为什么措辞仍然成立**：detail 写的是 `delivery stopped before upstream finished`——没人收到答案、交付先于上游结束，两种情形都为真。`[GONE]` 同理：都不是本代理或上游的过错。所以这不是错误，是**分辨率不足**。

**要做需要什么**：让关停路径在取消在途流之前给 `_StreamAccounting` 留一个标记（关停是本进程自己发起的，它知道自己在做什么），再在 `_ending()` 里多一档。技术上不难，难在判断值不值：关停时终端通常正在被 SIGTERM 收走，那批行有没有人读是个问题。

**判断**：**证据强度仅为「已想到」，未观测到任何人因此误判过**。不建议在没有真实困扰之前做——多一档就多一个要维护的词，而这条区分只在关停这一个窗口内有意义。若将来关停诊断成为议题，这是现成的接入点。

## 4. 计数行说不出上游是怎么失败的

**已解决的那半**：`provider(local)` 原本合并了「没有上游计数器」「上游被问了却答不出」「运维配成只估算」三种情形。2026-08-20 由用户裁决，改为 `provider(no-counter,local)` / `provider(ghc-failed,local)` / `provider(local)`，判定在 `handle_count_tokens` 里做（依据是它自己传出的 `upstream_absent_reason` 与尝试轨迹里有没有 `ghc:` 条目）。见 `spec.md`「一次计数请求怎么读」。

**仍然没有读者的那半**：`ghc-failed` 说不出是超时、429 还是 500，也说不出重试了几次。这些都躺在 `context.extras["count_tokens_attempts"]` 里（形如 `ghc:0:APIStatusError`），**至今没有任何消费者**。

**做法**：把 `count_tokens_attempts` 带进 `_Trace` → `RequestLine` → JSONL 结构化记录，**不上控制台行**——`request_id=` 这个 join key 就能回答「那次到底怎么失败的」，而行宽不变。上控制台会把最长的那个字段放进最常见的端点，不建议。

**为什么没做**：`ghc-failed` 已经把「要不要看一眼」这个判断交付给读者了，剩下的是排障时才需要的细节，而排障时结构化记录本来就在手边。**证据强度：已想到，未观测到有人因此卡住过。**

**来源**：`archive-count-tokens-line/reports/260820-review-count-tokens-log-line.md` F6，以及更早的 `../count-tokens/reports/260820-review-count-tokens-shared-pipeline.md:72`（后者属另一切片）。
