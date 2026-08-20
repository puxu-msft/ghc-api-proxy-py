# 空 text content part：GHC 上游实测

**日期**：2026-08-20
**问题**：GHC 的 Responses API 接不接受不携带文本的 text content part？Anthropic Messages 腿已知会拒（那是本次事故的 400），Responses 腿从未测过。
**脚本**：`probe.py`（手动运行，需凭据，发真实请求）。原始请求与响应在 `raw/`，账号标识落盘时脱敏、上行不脱敏。

## 结果

| 探针 | 形态 | HTTP |
|---|---|---|
| E1 | 基线：正常 `input_text` | **200** |
| E2 | `input_text: ""` 与一个真实 `input_text` 并列 | **200** |
| E3 | 纯空白 `input_text: "   \n"` 与一个真实的并列 | **200** |
| E4 | assistant 轮 `message` item 携带 `output_text: ""` | **200** |
| E5 | **阳性对照**：Anthropic 腿 `messages` 里的空 text 块 | **400** |

E5 的响应体逐字为：

```json
{"type":"error","error":{"type":"invalid_request_error","message":"messages: text content blocks must be non-empty"},"request_id":"req_011CeDbPwSjTZEc1W2JASgju"}
```

## 结论

**[强，一手实测，足以行动] 在 `gpt-5.5`、非流式下，GHC 的 Responses API 接受不携带文本的 text content part；Anthropic Messages API 不接受。** 空串与纯空白在 Responses 腿上都是 200，在 user 侧的 `input_text` 与 assistant 侧的 `output_text` 上都是 200。

**限定不是客套话，请连同结论一起引用。** E5 恰恰证明了同一台主机上两个端点对同一个 body 的判据可以不同，所以「同端点必同判据」不是白拿的前提——把这条结论外推到 Responses 腿上的**其它模型**时，强度应降为「合理外推」。实际暴露面很小：本上游没有任何 Claude 模型广告 `/responses`。

**归因也要说准**：E5 与 E1–E4 之间同时变了两个量（端点 **和** 请求形态的协议拼写）。严格说，本探针证明的是「Anthropic Messages 端点 + Anthropic 空 text 块 → 400」与「Responses 端点 + Responses 空 text part → 200」这一对事实，而不是把拒绝单独归因给「API 本身」。对落点决策而言这已经够用——生产里这两者本来就是绑定出现的。

阳性对照是这个结论成立的前提：同一次运行、同一套凭据、同一个上游主机，E5 拿到了 400 且措辞与生产日志逐字一致。所以那四个 200 是「上游看过并接受了」，而不是「请求根本没到达会判断 body 的那一层」。

## 这对本项目意味着什么

> **本节写于 07:19，反映的是当时那条「无条件剥离、两条腿都过」的裁决。** 随后 `4f2d786`（07:29:38）正是依据本探针把剥离改成按 `target_format` 门控：Responses 腿现在完全不被改写（`src/app/pipeline/subscribers/blank_text.py`）。下面第 2、3 条描述的行为在当前代码里不会发生，保留原文以记录当时的推理。结论与边界两节不受影响。

- 空 text 块此前在 Responses 腿上是**噪声而非故障**。这解释了为什么这个缺陷只在 Anthropic 直通腿上现形，尽管产生空块的合成占位块对两条腿一视同仁。**这一条至今成立，并且正是把剥离限定在 Anthropic 腿的依据。**
- ~~因此 2026-08-20 那条「无条件剥离」的裁决在 Responses 腿上**不修复任何 400**，它修的是别的东西：翻译后 `instructions` 尾部的空白填充、以及一个只含空块的 assistant 轮会退化成 `message` item 带 `output_text: ""`（剥离后该 item 整个不再产出，只剩 `function_call`）。~~ 已不适用：现在 Responses 腿不剥离，这两项都保持原样。
- ~~首轮评审当初主张给剥离加门控……裁决取消门控没有引入风险。~~ 已被后续裁决取代：门控回来了，但换了轴——不再问「客户端发的是什么」，而是问「谁会读它」。

## 第二轮：容器为空，而不是块为空

`probe_empty_containers.py`，2026-08-20。第一轮留下的两条未测项都是承重的：`subscribers/blank_text.py` 拒绝清空一条轮次，依据是「`content: []` 会被拒」——而那是参考实现两处注释的说法，本项目从未自测。

**F0 是这一轮的阳性对照，方向与 E5 相反**：E5 防的是「一排 200 其实什么都没证明」，F0 防的是「一排 400 其实只是凭据或这条腿坏了」。F0 是同一次运行里一个普通的合法 Anthropic 请求。

| 探针 | 形态 | HTTP | 上游原话 |
|---|---|---|---|
| F0 | **阳性对照**：合法 Anthropic 请求 | **200** | — |
| F1 | user 轮 `content: []` | **400** | `messages.0: user messages must have non-empty content` |
| F2 | user 轮 content 只有一个空文本块 | **400** | `messages: text content blocks must be non-empty` |
| F3 | assistant 轮（会话中间）content 只有一个空文本块 | **400** | 同上 |
| F4 | **末轮** assistant `content: []` | **200** | — |
| F6 | **会话中间** assistant `content: []` | **200** | — |
| F5 | Responses 腿 assistant message `content: []` | **200** | — |

### 结论

**[强，一手实测，足以行动]**

1. **`content: []` 不是一律被拒的。** 它对 **user 轮**被拒，且上游用的是**另一套措辞**（`user messages must have non-empty content`，与空文本块那条不同）；对 **assistant 轮被接受**，无论是末轮还是会话中间。参考实现「`content: []` 会被拒」那条二手断言**只对了一半**，照抄它会得出过度保守的结论——本项目此前正是这样。
2. 「Anthropic 允许可选的末轮 assistant 为空」这个契约细节**被本上游honour**（F4），而且**不止末轮**（F6）。所以位置不是判据，**角色才是**。
3. Responses 腿继续接受一切空容器（F5），与第一轮一致。

### 这直接改了代码

`subscribers/blank_text.py` 原先对「一条轮次全是空白块」一律原样发出。按上表改为按角色分：

- **assistant 轮 → 清空成 `content: []`**。两种拼法语义相同，而只有这一种能过（F6/F4 是 200，F3 是 400）。这把一个**必然失败**的请求变成了可以成功的请求。
- **user 轮 → 仍原样发出**。两种拼法都被拒（F1、F2 都是 400），既然怎么改都失败，那就让客户端自己的输入原样travel，上游报的错才指向客户端真正发了什么。

### 边界

- 未测：user 轮 `content: []` 出现在**非首位**时是否仍是同一条错误（F1 的错误带 `messages.0` 前缀，说明它按位置报，但只测了位置 0）。
- 未测：`system: []`。`blank_text.py` 对全空 `system` 的处置是删键而非清空，所以这条不承重，但它仍是一条没问过的形态。
- 未测：一条轮次里既有空白块又有非文本块（如 `tool_use`）时被清空的情形——不会发生，因为非文本块会存活，走不到清空分支。

## 第一轮的边界

- 只测了非流式 `/responses` 与 `gpt-5.5`。没有测流式，没有测其它模型。
- **「content 全是空 part」的形态：assistant 轮已测**——E4 发的就是 `content: [{"type":"output_text","text":""}]`，200。**未测**的是 user 轮（尤其是末轮）的同一形态，以及 `content: []` 这种空数组。后者正是 `subscribers/blank_text.py` 里那条「参考实现断言会被拒、本项目未自测」的二手断言所在之处，两处互相指认。
- E4 的空 assistant 轮后面跟的是一个 user message，而生产形态里它后面跟的是 `function_call` / `function_call_output`；另外五个探针**都没有携带 `tools`**，而生产请求几乎总是带。两者都不太可能改变 body 校验对空 part 的判断（校验通常是 part 级的），但没测就是没测。
- 只测了「上游是否接受」，没有测「上游是否因此产生不同的输出」。E2/E3/E4 都正常返回了内容，但本探针不对生成质量做任何判断。
- 每个探针只发一次，失败即记录、不重试。
