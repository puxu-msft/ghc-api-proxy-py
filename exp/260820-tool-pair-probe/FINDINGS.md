# `tool_use` / `tool_result` 配对：上游实测

**日期**：2026-08-20
**问题**：legacy 的 `process_tool_blocks` 做四件事（删孤儿调用、删孤儿结果、删重复 id、删空消息）。要把它补到新链路上，得先知道**这个上游实际拒绝哪几件**——照搬一份没人验证过的规则，等于用别人的假设改写用户的请求。
**脚本**：`pairing_probe.py`（手动运行，需凭据，发真实请求）。原始请求与响应在 `raw/`。

## 结果

| 探针 | 形态 | HTTP | 上游原话 |
|---|---|---|---|
| G0 | **阳性对照**：配对完好 | **200** | — |
| G1 | assistant 发起调用，下一轮不作答 | **400** | ``messages.2: `tool_use` ids were found without `tool_result` blocks immediately after: toolu_1`` |
| G2 | user 给出结果，前一轮没有对应调用 | **400** | ``messages.2.content.0: unexpected `tool_use_id` found in `tool_result` blocks: toolu_1`` |
| G3 | 同一个 `tool_use` id 用两次 | **200** | — |
| G4 | 连续两轮 assistant | **200** | — |
| G5 | Responses 腿：`function_call` 无 `function_call_output` | **400** | `No tool output found for function call call_1.` |

## 结论

**[强，一手实测，足以行动]**

1. **孤儿配对两条腿都拒，且各有各的措辞。** G1/G2 是 Anthropic 腿，G5 是 Responses 腿翻译后的等价形态。所以这条不变量**不是某个端点的属性**——修复必须放在**翻译之前**，只修 Anthropic 出站腿会让主产品路径以完全相同的方式坏掉。这与空文本块那条正好相反（那条只有 Anthropic 腿拒，所以门控在出站点），两次都由实测定夺，不靠推断。
2. **id 重复不拒。** legacy 会删掉重复 id 的 `tool_use`。这个上游返回 200，所以照搬会**删掉上游接受的东西**——等于凭一条它并不执行的规则，把模型发起的一次工具调用拿走。已明确不实现。
3. **连续同角色轮次不拒。** 这让「清空后的轮次整条删掉」从猜测变成已测选项。它同时回溯影响了另一处判断：`subscribers/blank_text.py` 里全空的 user 轮原先原样发出、必然吃 400，理由正是「删轮次的后果没测过」；G4 之后该理由不再成立，已改为删除该轮次。
4. **`immediately after` 是上游自己的措辞**（G1 原话），所以配对只看紧邻的下一轮。晚一轮到达的结果，按同一条规则既让调用成为孤儿、也让自己成为孤儿。

## 这对本项目意味着什么

`src/app/pipeline/anthropic_request_hook.py::repair_tool_pairs` 按上表实现：删 G1、删 G2、**不**删 G3、清空后按 G4 删轮次（除非会把 `messages` 删空）。只有本次修复清空的轮次才会被删——客户端自己发来的 `content: []` 原样travel，上游指名它才是客户端要的答案。

## 边界

- 只测了非流式、`claude-sonnet-5`（Anthropic 腿）与 `gpt-5.5`（Responses 腿）。
- G3 只测了「两组完好配对复用同一个 id」这一种重复形态；没测「同一轮内两个 `tool_use` 共用一个 id」或「一个调用配两个结果」。
- G4 只测了连续两轮 **assistant**；连续两轮 user 未测。当前两处修复删掉的都是 user 轮（其邻居是 assistant），所以走的正是 G4 测过的那条。
- 未测：孤儿 `server_tool_use` / `*_tool_result`（那是另一个命名空间，由 `subscribers/server_tools.py` 处理）。
- 每个探针只发一次，失败即记录、不重试。
