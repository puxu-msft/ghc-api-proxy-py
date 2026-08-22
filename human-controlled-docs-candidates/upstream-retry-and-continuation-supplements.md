# 候选片段：`upstream-retry-and-continuation.md` 的补充

**日期**：2026-08-21。**性质**：候选材料，供用户摘取，**不是裁决**。
**目标文档**：`docs/.human-controlled/upstream-retry-and-continuation.md`（2026-08-21 21:xx 版，工具名已改为 `turn_interrupted`、`refusal` 已入「无法继续」、429 已入「一般可以继续」）。
**证据出处**：`.dev/docs/upstream/retry-and-continuation/`（README 有证据表，reports/ 有四份完整报告）。

本文只写目标文档**尚未涵盖**的部分。已经写进去的不复述。

---

## 一、回答文档第 23 行的 TODO

> 特殊地，`max_tokens` 不应无痕重试。TODO：参考项目对 `max_tokens` 的处理方案是什么？一般是否已经交付过完整块，只是最后一个块被截断了？

### 1a. 参考项目怎么做（八个仓库全查过）

| 项目 | 识别判据 | 处理 | 截断的 tool call | 重试 |
|---|---|---|---|---|
| `copilot-api-js`（前身） | `stopReason === "max_tokens"`，**只接在 Anthropic 直连腿**；Responses 腿的谓词零调用点 | 透传 + 记诊断，明确 observation-only | 无专门处理，走通用 `jsonrepair` | 否。`max_tokens_continuation` 默认 false 且无消费者 |
| `vscode-copilot-chat`（官方） | Chat Completions 的 `Length`；**Responses 路径 `incomplete_details` 全仓 0 命中** | 多数消费者转成错误；codeMapper 做续写 | **静默丢弃**（emit 条件是 `ToolCalls \|\| Stop`，不含 `Length`） | codeMapper `while(true)`，按累计长度封顶，无轮数上限、无退避 |
| `caozhiyuan/copilot-api` | `status === "incomplete" && reason === "max_output_tokens"` | 纯透传 → `max_tokens` | 原样发，仅补 `content_block_stop` | 否 |
| `hooyao/copilot-bridge` | `response.incomplete` 或 `status == "incomplete"`，**不读 reason** | 透传；关未闭合块时拒绝伪造完成态 | 校验 JSON+schema，**默认 observe-only 原样转发** | 否 |
| `sxwxs/ghc-api-py` | `status=="incomplete"` + `reason=="max_output_tokens"`，未知 reason 抛异常 | 透传 | 整条转换失败（fail-closed） | 否 |
| `CLIProxyAPIPlus` / `awsl-maxx` | 只有 `"length"` ⇄ `max_tokens` | 映射透传；输出 Responses 时硬编码 `completed`/`null`，**信号丢失** | 未处理 | 否 |
| `agent-maestro` | 无（`incomplete_details` 恒 `null`） | 不适用 | — | 否 |

**三条值得注意的**：

1. **没有任何一个参考项目做我们要做的事。** 七个是纯透传，唯一做续写的 `vscode-copilot-chat` 的 codeMapper 是代码映射的特化场景，且无轮数上限。
2. **前身仓的数据盖不到我们的主路径。** 它的 `max_tokens` 处理只接在 Anthropic 直连腿，而我们是 Anthropic 输入 → Responses 上游——恰是它 `isResponsesMaxTokensTerminal` 零调用点的那条腿。它那 5 例样本（约 0.4%）的分布结论不能搬。
3. **`status === "incomplete"` 是别人已在用的判据**（`caozhiyuan`、`hooyao`、`ghc-api-py` 三家），不是我们发明的。

### 1b. 是否已经交付过完整块（**成立，且比问句更强**）

**录制证据，n=20，逐例核对**（现网 history 的原始根帧）：

- 撞 `max_output_tokens` 时，上游**一定**为被截断的那个 item 发出 `response.output_item.done`——20/20 例中它就是 `response.incomplete` 的紧前一帧，`added` 与 `done` 计数逐例相等。
- 本项目 block 完成的唯一判据正是 `output_item.done`（`assembler.py:231-232` → `_close`），`response.incomplete` 完全不碰未完成的草稿。
- **所以被截断的那个块自己就会被完整交付。** 语料里**没有任何一例是零块交付**，包括最坏形态（只有 reasoning 中途撞顶，6 例）。

分形态：纯文本单 message item（1 例）→ 1 个 text 块；reasoning+message（8 例）→ thinking 块 + 1 个 text 块；只有 reasoning（6 例）→ 若干 thinking 块；带工具调用（5 例）→ 前序块 + 1 个 `tool_use` 块。

**样本边界（建议一并写进文档）**：该语料里 `incomplete_details.reason` **只有** `max_output_tokens` 一种，`content_filter` 等未观测到；时间窗 2026-08-04～08，模型 `gpt-5.6-sol` / `gpt-5.6-terra`；现有 cassette 一份都没覆盖这个场景。

**建议措辞**（替换第 23 行的 TODO）：

> 特殊地，`max_tokens` 不应无痕重试，一律走 MCP-driven 合成续写。
>
> 实测（n=20，2026-08-04～08 的现网录制）：撞顶时上游**一定**为被截断的 item 发出 `output_item.done`，因此被截断的那个块自己就会被交付成一个完整块，**不存在零块交付的形态**。所以 `max_tokens` 总是落在「已交付过完整块」那一格。「不无痕重试」这条因此是冗余保险而非必需分支，保留它是为了挡上游哪天改行为。
>
> 参考项目无一做代理端续写：七个纯透传，唯一做续写的官方 `vscode-copilot-chat` 是代码映射的特化场景。

---

## 二、被截断的那个块要不要交付（文档目前完全没有这一格）

**上游把答案标在 wire 上了**：`output_item.done` 的 item 带 `status` 字段——被截断的是 `"incomplete"`，完整的是 `"completed"`。实测 15 次（其中 4 次在 `function_call` 上）。而 `assembler.py` **一个字都没读**（该文件 `.status` / `"status"` 零命中）。

**reasoning item 没有这个字段**——已做正样本对照：正常收尾的 reasoning item 与被截断的，键集逐字相同（`content, encrypted_content, id, summary, type`）；`summary: []` 在两侧都出现，也不是信号。

**建议措辞**：

> 上游在 `output_item.done` 上标出该 item 是否被截断（`status: "incomplete"` / `"completed"`）。据此：
>
> - **已经有任何完整块时，丢弃被截断的那个块**——不把半截语义交给客户端。
> - **只有未完成块时，保留它**——给客户端半截内容优于给一个空回答。
> - **reasoning item 上游不带这个字段**，无信号，暂不特殊处理。
>
> 这条判断是零成本的：被截断的 item 永远是最后一个，处理它时前面发过几块是本地已知的，不需要缓冲或前瞻。

**顺带解决的一件事**：撞顶落在工具调用上时，`arguments` 是残缺 JSON（4/4 例），现在会回退成 `input={"__raw": …}` 交给客户端。按上面的规则它正是 `status="incomplete"` 的那个，直接被丢掉。（另有旁证表明 Claude Code 自己有 `safeParseJSON` → `{}` → zod → `is_error` 的恢复链，所以这本来也不是必须修的危害，只是顺手更干净。）

---

## 三、400 这一格建议点明它涵盖上下文超限

文档第 9 行现在只写「400」。上下文超限**没有独立的一格**，而它是 400 里最需要被认出来的一种。

**实测已否证** stop_reason 路径：Responses 腿的值空间里根本没有 `model_context_window_exceeded`（`incomplete_details.reason` 20/20 全是 `max_output_tokens`）；Anthropic 腿 13 万次请求零观测——但那条腿上它是**可定义**的，所以是「未观测」不是「不可能」。

正面形态是 **HTTP 400**，已找到 **48 例一手录制**，而且**两条腿的表达是结构性不同的**：

- **Anthropic 腿**（27 例）：`application/json`，`error.code = model_max_prompt_tokens_exceeded`，`error.type = invalid_request_error`，message 带数字（`prompt is too long: 1051542 tokens > 1000000 maximum`）。**靠 `error.code` 可靠区分**——其余 400 连 `code` 字段都不带。
- **Responses 腿**（21 例，**这是主产品路径**）：`text/plain; charset=utf-8`，`error.code = invalid_request_body`，**没有 `error.type`、没有 `request_id`、message 里没有任何数字**（`Your input exceeds the context window of this model.`）。`error.code` **毫无区分力**——`Invalid 'input[1].id'` 用的是同一个值，只能匹配 message 文本。

**建议措辞**：

> - 400，**含输入超出模型上下文窗口**。上游用 400 表达它，不是用 `stop_reason`；两条腿的形态不同：Anthropic 腿给 `error.code = model_max_prompt_tokens_exceeded` 且 message 带数字，Responses 腿给 `error.code = invalid_request_body`（与其他参数错误共用，不可据以区分）且 message 无数字，只能匹配 `exceeds the context window`。
>
>   （Anthropic 腿的 `model_context_window_exceeded` 在 13 万次请求中零观测，但该腿上它可定义，不排除将来出现。）

**一件与本文档相邻、但属于另一个主题的事**（记在这里免得丢，处置由你）：把三条真实 body 喂给生产模块 `parse_prompt_limit_error` 实测——Anthropic 腿解出 `(1051542, 1000000)`，**Responses 腿返回 `None`**。主产品路径正是没覆盖的那条，而且**补正则也救不回来**，因为那条 message 里没有数字，`PromptLimitRegistry` 结构上喂不进去。要让 prompt-limit 观测在主路径上工作，需要的是另一个数据来源，不是一条正则。

---

## 四、非流式路径（文档没写；裁决已在 2026-08-21 的讨论中做出）

出处：`.dev/docs/upstream/retry-and-continuation/decisions.md` 第二节第 4 条——该裁决此前只存在于对话中，`.dev` 里没有落点，独立评审因此查无此记录。现已补记。

**建议措辞**：

> 非流式请求没有「块」的概念，整条响应是原子的，因此**只可能无痕重试，不可能续写**。其中 `max_tokens` 两条都不适用（不能无痕重试，也没有可合成的位置），原样返回给客户端。

---

## 五、无痕重试的间隔（文档没写）

现状是 network / serverError 各 9 次、`max_total` 20，**无退避、无 jitter、无间隔**——连打。

**建议措辞**：

> 无痕重试不设间隔。唯一的例外是 HTTP 429 触发的反应式限流器，它自己给的间隔照旧生效。

---

## 六、观测面（文档没写）

**建议措辞**：

> 合成续写之后，**客户端请求算成功**（我们有独特的 MCP 工具调用，不难判断），**但这次上游尝试算失败**。请求日志用 `[RETY]` 前缀 + 黄色。
>
> `usage` 报本次失败 attempt 上游实报的值——被交付的块确实进了客户端的 transcript，下一轮会带着它们发出去；这里报零会让客户端对上下文占用的估计持续偏低，压缩时机跟着错。

（`[RETY]` 而非 `[RETRY]`：现有前缀实测全是 6 字符宽，只有 `[RETRY]` 是 7，把固定宽度那一列顶歪了。改成 `[RETY]` 顺带修掉这个既有 bug。）

---

## 七、一处措辞残留

文档第 41 行结尾仍写着「其他**上游请求**暂不使用该机制」，而同句前半和第 31 行都已改为**客户端请求**。按已确立的判据（决定能不能合成 `tool_use` 块的是发给客户端的格式，决定客户端会不会执行它的是客户端是什么），这里应统一为客户端请求，否则会被读成「只在 Anthropic 直连上游腿上做」——那恰好排除掉主产品路径。

**建议**：把该句尾改为「其他客户端请求格式暂不使用该机制」。

---

## 八、`config.example.yaml` 里有五行需要你删（B 组落地后唯一的红）

代码里的 `continuation` 策略已随 B 组删除（提交 `40d9c76`）。但 `docs/.human-controlled/config.example.yaml` 仍在第 341–346 行声明它，而 schema 是 `extra="forbid"`，于是 `tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses` **持续为红**，直到这几行从你的文件里去掉。

我不动你的文件，所以把要删的原文贴在这里：

```yaml
    # 续写：已经有块提交给客户端（非工具调用）后请求中断，代理合成续写轮直接重投（已提交块作 assistant + 续写 user）。
    # Continuation: some block was committed to the client, a mid-stream RST occurs -- the proxy appends messages (the already-committed blocks as an assistant turn + this user message) so the model continues.
    continuation:
      enabled: true
      max_retries: 10
      message: "Please continue where you left off."
```

**追加（2026-08-22）**：同一段里的 `streamReplay` 也要删——你已裁决删除它，代码侧已随之移除。要删的是第 339–340 行：

```yaml
    streamReplay:
      max_retries: 100
```

理由记在 `.dev/docs/upstream/retry-and-continuation/decisions.md` 第四节：它是代理内续写方案的遗留，配对的另一半已经删了；断流重开现在走 `network` 的普通预算，`max_total` 成为整条客户端请求的总闸。

顺带两处**同一段落里的相邻文字**，删不删由你，它们描述的都是已放弃的方案：

- 第 322 行 `# Includes both direct replay and continuation` —— 现在只剩 direct replay。
- 第 383 行 `# This also allows us to implement a valuable "continuation" feature: blocks already seen by the client are not discarded, and can be sent to the model as context for continuation.` —— 「把已见块回送给模型作上下文」正是被放弃的那件事。块级交付本身的价值不受影响，只是这句举的例子换了。

**`max_tokens_as_retryable: true`（第 350 行附近）保留**——用户裁决「其他未接线的功能不要动」，它不属于代理内续写机制。

### 顺带发现：一处与本次无关的既有红

同一条测试还报第二个 `extra_forbidden`：`config.example.yaml:450` 的 `hook_strip_anthropic_request_headers` 整段在 schema 里没有对应物。这在本次改动之前就存在（`app/hooks/` 是未挂载的 legacy 链路），**不是 B 组造成的**，也不在本次范围内。列在这里只为免得将来把两条红算成一条。

---

## 九、一条推论（不是裁决，前提变了它就失效）

删掉 `client_delivery.synthesized_response_headers_after_sec` 之后，`stream.py:253-262` 那个唯一会单独发 `message_start` 的出口消失，于是 **`message_start` 只能与第一个完整块同批发出，半开状态不再可达**。

文档第 27 行已经写了「也不再出现半开 `message_start` 需要考虑」，措辞已经正确。这里只补一条**给实现者的提醒**，可放可不放：

> 该性质由构造保证，不由任何断言保证——live 链路一条相关守卫都没有（9 条 `DeliveryOrderError` 全在未挂载的 legacy 侧）。将来谁再引入单独发 `message_start` 的路径，不会有任何东西报错。

---

## 十、`config.example.yaml` 里 `hand_over_stop_reasons` 的 `max_output_tokens` 是死条目

**2026-08-22 追加。** 你在 `docs/.human-controlled/config.example.yaml:339` 写的是：

```yaml
  hand_over_stop_reasons: ["max_tokens", "max_output_tokens"]
```

`max_output_tokens` **永远不会匹配**。这个键的两个消费点比较的都是**翻译之后**的 Anthropic 拼法，而 `max_output_tokens` 恰好是唯一一个被翻译的值：

- 流式：`src/app/pipeline/delivery/formats/openai_responses.py:513-514`，`"max_tokens" if reason == "max_output_tokens" else reason or "incomplete"`；
- 非流式：`src/app/pipeline/translation_driver/responses.py:125-126`，`if reason == "max_output_tokens": return MAX_TOKENS, None`。

实测（`ResponsesAssembler.push` 喂 `response.incomplete`，含正样本对照确认 push 确实执行）：

| 上游 `incomplete_details.reason` | 记下的 `stop_reason` |
|---|---|
| `max_output_tokens` | **`max_tokens`** |
| `content_filter` | `content_filter` |
| 无 | `incomplete` |
| （对照：`response.completed`） | `end_turn` |

**为什么容易读错**：那两处代码的注释都写着「上游自己的词，不翻译」，而 `max_output_tokens` 正是那句话的**唯一例外**，例外写在紧挨着的一行。Anthropic 腿本来就用 `max_tokens`，所以两条腿在这个键上看到的都是 `max_tokens`。

**没有危害**，多一个永不匹配的值不改变任何行为。**建议**：删掉 `max_output_tokens`，与 schema 默认 `["max_tokens"]` 一致；若想保留作提示，改成注释更准确，例如 `# 上游 Responses 的 max_output_tokens 已在翻译时归一为 max_tokens，此处不必列`。

**证据等级：确凿**（一手实测 + 两处代码事实）。**是否要改属你的取舍。**
