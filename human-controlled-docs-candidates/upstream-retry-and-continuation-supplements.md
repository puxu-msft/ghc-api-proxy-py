# 候选片段：`upstream-retry-and-continuation.md` 的补充

**目标文档**：`docs/.human-controlled/upstream-retry-and-continuation.md`
**性质**：候选材料，供用户摘取，**不是裁决**。
**证据出处**：`.dev/docs/upstream/retry-and-continuation/`（README 有证据表，reports/ 有完整报告）。

**2026-08-22 全面刷新。** 用户当日多次更新目标文档，本文按逐条对账（`.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md`，81 条判定）重写：已采纳的撤下留记录，已否决的撤下留理由，走法不同的收紧适用域，仍然打开的保留。

**一条关于行号的说明**：本文引用人写文档时只写小节标题与原文引句，**不写行号**。上一版写了行号，而那些行号取自同一天不同时刻的工作树快照、互不自洽，读者按图索骥会以为自己找错了地方。引用代码时写行号，因为那些当场核过。

---

## 已采纳，撤下留记录

按 `record-what-not-adopted` 的同一条理由留记录：下一个读者要能看出这里曾经有过什么、结局如何，而不是发现一段凭空消失的历史。

| 原节 | 内容 | 落点 |
|---|---|---|
| §三（核心） | 400 这一格点明涵盖上下文超限 | 「这些情况下无法继续」表里已改为「400，包括请求非法和输入超长」 |
| §五 | 无痕重试不设间隔 | 已并入「如果业务可能可以继续」那段句末：「无痕重试不设冷却间隔」。429 的例外另有独立段落承载 |
| §八（前半） | 删 `config.example.yaml` 里 `continuation` 的五行 | 已删 |
| §八（追加） | 删 `config.example.yaml` 里 `streamReplay` 两行 | 已删 |
| §十一 | `client-side-block-delivery.md` 的配置节名从 `upstream_request_retry` 改为 `upstream_request_timeouts` | 已逐字采纳 |

**§八d／§八e 两条已过期**，撤下不留待办：`max_tokens_as_retryable` 在 `config.example.yaml` 与 `src/app/config/schema.py` 里都已不存在（被 `hand_over_stop_reasons` 取代并接线）；`hook_strip_anthropic_request_headers` 现在有了 schema 对应物，当时报的那条红已经不存在。

---

## 已否决，撤下留理由

### 原 §九：半开 `message_start` 的「给实现者的提醒」

原建议是往权威文档里补一句：该性质由构造保证、live 链路一条守卫都没有、将来谁再引入单发 `message_start` 的路径不会有任何东西报错。

**用户在同一段落里正面回答了**（那段现在是引用块）：

> ……也不再出现半开 `message_start` 需要考虑。**事实上目前不应该有半开 `message_start`，但这不属于本节讨论范围，是一条推论，不应由我们写死。**

被否的不是事实判断——用户承认「目前不应该有」——而是**把一条由代码构造保证的性质固化成需求文档条款**这个动作，理由是两条：不属于本节范围，且推论不应由我们写死进权威文档。

**因此这条不得以任何形式再送第二遍**（补 ADR、补 spec、补「守卫需求」都算再送一遍）。如果确实认为缺守卫是风险，那是实现侧的事，走代码与测试。

---

## 走法不同：我们建议的与用户采纳的不是同一个形状

这一类最要紧——候选材料若照原样留着，下一次会把同一个偏差再送一遍。

### 一、`max_tokens` 的处理：我们要「一律」，用户要「二分」，**用户是对的**

用户新起了一节「## 输出超长」：

> 对于 SSE stop_reason = `max_tokens` (anthropic-messages) / `max_output_tokens` (openai-responses) 的情形，不应无痕重试。要么在能续写的情况下，丢弃未完成的块，走下文合成续写机制；要么在不能续写的情况下，直接返回给客户端。

**采纳的**：「不应无痕重试」「走合成续写」。

**走法不同的**：我们原来的措辞是无条件的——「`max_tokens` **一律**走合成续写」「**总是**落在已交付过完整块那一格」。用户写的是有条件的二分，而**这个形状更准确**：目标文档自己就规定了该机制「只给 anthropic-messages 客户端请求」，于是「不能续写」这一格真实存在。

**我们那条全称是怎么错的**：n=20 的录制只覆盖「流式 + Responses 上游 + 撞 `max_output_tokens`」这一格，结论却写成了全称。**证据的适用域必须跟着写下来，否则它会被拿去推翻一个它根本没测到的分支。**

n=20 的结论本身仍然成立，收紧后是：**在流式、Responses 上游、撞 `max_output_tokens` 这一格里，不存在零块交付的形态**——上游一定为被截断的 item 发出 `output_item.done`（20/20，`added` 与 `done` 计数逐例相等），而本项目块完成的唯一判据正是它。样本边界：2026-08-04～08，模型 `gpt-5.6-sol` / `gpt-5.6-terra`，该语料里 `incomplete_details.reason` 只有 `max_output_tokens` 一种。

**参考项目综述（八个仓全查过）属于证据材料而非规格文本**，不再往人写文档送，留在 `.dev/docs/upstream/retry-and-continuation/reports/260821-reference-projects-max-tokens.md`。一句话结论：**没有任何一个参考项目做我们要做的事**，七个纯透传，唯一做续写的官方 `vscode-copilot-chat` 是代码映射的特化场景且无轮数上限。

### 二、「丢弃被截断的块」：条件换了一套，且实现判据不必进文档

原建议给了三条规则，绑的是「已经交付过几个完整块」。用户写的是「能不能续写」。

**代码实际绑的是第三样东西**：`stop_reason ∈ hand_over_stop_reasons`（`src/app/pipeline/delivery/formats/openai_responses.py:393`）。三者在主路径上恰好重合，分叉的地方见下面「待裁决」第 1 条。

两点澄清，都不是待办：

- **`status: "incomplete"` 这个 wire 判据没进人写文档，也不该进**——用户文档写需求不写实现。它已经是实现事实（`formats/openai_responses.py` 的 `_upstream_cut_this_item_short`），候选材料不该继续把它当成「待用户采纳的措辞」。
- **reasoning item 不带 `status` 字段**（正样本对照确认：正常收尾与被截断的键集逐字相同，`summary: []` 两侧都出现）。用户 2026-08-21 已裁决「历史里没有信号就保持悬念」，登记在 `deferred.md` §2。

### 三、非流式：**这一条是我的过失，单独写**

原 §四 的建议措辞是：

> 非流式请求没有「块」的概念，整条响应是原子的，因此**只可能无痕重试，不可能续写**。

**这是我 2026-08-22 被用户更正之前的旧立场。** 当天用户明确推翻了它（「非流式不可续写？用户肯定说错了，非流式应该找到最后一个 incomplete 块边界」），我据此实现了非流式的丢块 + 交接（主仓 `af84097`）——**但没有回头改这份候选材料**。

随后用户写文档时，从这份过期材料里取了一句几乎同义的话写进权威文档（「非流式请求只接入适合无痕重试的情形，不支持合成续写」），于是权威文档与已落地的代码相反。经确认后用户已自行改正，现在那一节是：

> ## 非流式请求
>
> 非流式请求也支持无痕重试、合成续写机制。

**这一格现在文档与代码一致，无待办。** 记录在这里是因为教训是可复用的：**一份过期的候选材料是一个把已被推翻的立场重新送进权威文档的通道**——它看起来像是我们的建议，而用户没有义务记得哪一条已经作废。所以「用户采纳了某条」与「用户推翻了某条」都必须当场回写候选材料，不能只改代码。

---

## 仍然打开

### 四、一处措辞残留：「其他**上游请求**暂不使用该机制」

「限制」那段结尾仍写着「其他上游请求暂不使用该机制」，而同句前半已改为**客户端请求**。

按已确立的判据（决定能不能合成 `tool_use` 块的是发给客户端的格式，决定客户端会不会执行它的是客户端是什么），这里应统一为客户端请求，否则会被读成「只在 Anthropic 直连上游腿上做」——**那恰好排除掉主产品路径**（Anthropic 输入 → Responses 上游）。

**建议**：句尾改为「其他客户端请求格式暂不使用该机制」。

### 五、观测面（文档仍无对应文字）

> 合成续写之后，**客户端请求算成功**（我们有独特的 MCP 工具调用，不难判断），**但这次上游尝试算失败**。请求日志用 `[RETY]` 前缀 + 黄色。
>
> `usage` 报本次失败 attempt 上游实报的值——被交付的块确实进了客户端的 transcript，下一轮会带着它们发出去；这里报零会让客户端对上下文占用的估计持续偏低，压缩时机跟着错。

（`[RETY]` 而非 `[RETRY]`：现有前缀实测全是 6 字符宽，只有 `[RETRY]` 是 7，把固定宽度那一列顶歪了。改成 `[RETY]` 顺带修掉这个既有 bug。已实现。）

### 六、400 两条腿形态差异的详细措辞（核心已采纳，这是余项）

用户已把 400 那一格改成「400，包括请求非法和输入超长」，核心诉求达成。**下面这段更细的措辞放不放由你**，它的价值在于说明为什么不能只看 `error.code`：

> 两条腿的形态不同：Anthropic 腿给 `error.code = model_max_prompt_tokens_exceeded` 且 message 带数字，Responses 腿给 `error.code = invalid_request_body`（与其他参数错误共用，**不可据以区分**）且 message 无数字，只能匹配 `exceeds the context window`。
>
> （Anthropic 腿的 `model_context_window_exceeded` 在 13 万次请求中零观测，但该腿上它可定义，不排除将来出现。）

一手证据 48 例，见 `reports/260821-context-limit-400-examples.md`。

**上一版这里还挂着一条「`parse_prompt_limit_error` 在主路径返回 `None`」的相邻问题，已于 2026-08-22 撤销**——那个数字上游模型目录里就公布着（`limits.max_prompt_tokens`），而它唯一的消费端 `/api/tokenization/limits` 在 `api.md` 里已标为暂不支持。理由不成立，详见 `deferred.md` §1。

### 七、`config.example.yaml` 里两处描述已放弃方案的相邻注释

删不删由你，功能无影响：

- `# Includes both direct replay and continuation` —— 现在只剩 direct replay。
- `# This also allows us to implement a valuable "continuation" feature: blocks already seen by the client are not discarded, and can be sent to the model as context for continuation.` —— 「把已见块回送给模型作上下文」正是被放弃的那件事。块级交付本身的价值不受影响，只是这句举的例子换了。

### 八、两处文档自身的小不一致（对账时顺带发现）

- **`README.md` 的索引指向不存在的 `observability.md`**，同时漏列已存在的 `release-and-deployment.md`。
- **「## 输出超长」那句「走**下文**合成续写机制」方向写反了**——「## MCP-driven 合成续写」在它**上面**。改成「上文」或直接写小节名。

---

## 待裁决

### 1. `hand_over_stop_reasons` 里的 `max_output_tokens`：不是删不删的问题，是文档二分与代码三态不一致

**上一版这里的诉求是「建议删掉 `max_output_tokens`」。该诉求已被你以一次正面书写驳回**——你保留了它，并在「## 输出超长」里把两个拼法并列成同一情形的两种协议写法。所以那个诉求撤下，**但它暴露的两件事不是被驳回的东西**：

**（1）比较发生在归一化之后，所以 `max_output_tokens` 结构上永不匹配。**

两条路径都在**门之前**把它改写成 `max_tokens`：流式 `src/app/pipeline/delivery/formats/openai_responses.py:513-515`，非流式 `src/app/pipeline/translation_driver/responses.py:125-126`。实测（含证伪对照：把 `hand_over_stop_reasons` 配成 `{"max_output_tokens"}` 即删掉 `max_tokens` 只留它，合成**一次都没触发**）：

| 上游 `incomplete_details.reason` | 记下的 `stop_reason` |
|---|---|
| `max_output_tokens` | **`max_tokens`** |
| `content_filter` | `content_filter` |
| 无 | `incomplete` |
| （对照：`response.completed`） | `end_turn` |

**容易读错的原因**：那两处代码的注释都写着「上游自己的词，不翻译」，而 `max_output_tokens` 正是那句话的**唯一例外**，例外就写在紧挨着的一行。

**今天无害，明天的失效形态是静默的**：下一个读者（包括另一个仓改 MCP 的人）反向推断「上游明明说 `max_output_tokens`，`max_tokens` 大概写错了」，把 `max_tokens` 删掉——此后所有撞上限的回合既不交接，**同一个键还决定被截断的块丢不丢**（`formats/openai_responses.py:393`），于是保留半截块正常收尾，客户端拿到一个截断块 + `stop_reason: max_tokens`，没有 tool call、没有告警。

**（2）你的二分与代码的判据不是同一条，中间漏了一格。**

文档说「能续写 → 丢弃未完成的块；不能续写 → 直接返回给客户端」。而代码里：

- **丢弃**只由 `stop_reason ∈ hand_over_stop_reasons` 决定（`formats/openai_responses.py:393`）；
- **能不能续写**另有一道闸：`src/app/server/pipeline_app.py:552` 的 `if route.wire_format is not WireFormat.ANTHROPIC_MESSAGES: return None`；
- 而 assembler 的选择只看**上游方言**，不看客户端格式（`src/app/server/handler.py` 的 `assembler_for` 依 `dialect_for`）。

于是存在第三种形态：**一个非 anthropic-messages 的客户端走 Responses 上游撞上限时，被截断的块被丢掉，而交接的 `tool_use` 块不会生成**——两条分支都没走成，客户端既没拿到半截内容，也没拿到续写入口，日志上也没有告警。

**两条出路，请裁决**：

- **A. 让代码去迎合文档** —— 把「客户端格式」这道闸并进同一条判据，使「丢弃」与「交接」同生同死。这样第三种形态消失：非 anthropic-messages 客户端撞上限时保留半截块正常收尾。
- **B. 让文档补一格** —— 承认三态，写明「客户端格式不支持续写时，保留被截断的块并原样返回」。

**本项目倾向 A**：`deferred.md` §15 已经记过一条不变量——「不交接就不丢」在任何配置下都成立，而「交接就一定丢」不是不变量、本项目也不需要它。A 是把这条不变量落到代码上，B 是把违反它的那一格写进规格。

**证据等级：代码事实与一手实测，确凿**（异源评审 2026-08-22 F6/F11 + 本次对账独立复核）。**怎么选属你的取舍。**

### 2. 「不能续写时保留半截块」这一格，文档没明说

「## 输出超长」的「不能续写 → 直接返回给客户端」可以读成「连同半截块一起返回」，但没有明说。这一格与上面第 1 条的出路 B 是同一件事的两面，一并裁决即可。
