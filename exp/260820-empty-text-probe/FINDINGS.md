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

**[强，一手实测，足以行动] GHC 的 Responses API 接受不携带文本的 text content part；Anthropic Messages API 不接受。** 空串与纯空白在 Responses 腿上都是 200，在 user 侧的 `input_text` 与 assistant 侧的 `output_text` 上都是 200。

阳性对照是这个结论成立的前提：同一次运行、同一套凭据、同一个上游主机，E5 拿到了 400 且措辞与生产日志逐字一致。所以那四个 200 是「上游看过并接受了」，而不是「请求根本没到达会判断 body 的那一层」。

## 这对本项目意味着什么

- 空 text 块此前在 Responses 腿上是**噪声而非故障**。这解释了为什么这个缺陷只在 Anthropic 直通腿上现形，尽管产生空块的合成占位块对两条腿一视同仁。
- 因此 2026-08-20 那条「无条件剥离」的裁决在 Responses 腿上**不修复任何 400**，它修的是别的东西：翻译后 `instructions` 尾部的空白填充、以及一个只含空块的 assistant 轮会退化成 `message` item 带 `output_text: ""`（剥离后该 item 整个不再产出，只剩 `function_call`，这才是「助手调用了工具」的正确形态）。
- 首轮评审当初主张给剥离加门控，理由是「Responses 腿上会拒这件事未经测量」。现在测量出来了：**不拒**。所以那条门控当初防的不是一个真实故障，而是一个未知；裁决取消门控没有引入风险。

## 边界

- 只测了非流式 `/responses` 与 `gpt-5.5`。没有测流式、没有测其它模型、没有测「一条 message 的 content 全是空 part」这种退化形态。
- 只测了「上游是否接受」，没有测「上游是否因此产生不同的输出」。E2/E3/E4 都正常返回了内容，但本探针不对生成质量做任何判断。
- 每个探针只发一次，失败即记录、不重试。
