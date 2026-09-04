# Anthropic 直连腿的请求体构造

**这个 topic 管什么**：**出站目标格式是 Anthropic Messages** 的请求，在 translation 之后的最终形状——`thinking` 与 `output_config` 该长什么样。客户端原样送来的（`translation_required == False`）与从别的协议翻译过来的都算，因为「这个模型收不收 `thinking.type: enabled`」是**回答请求的那个模型**的属性，与请求体从哪儿来无关。

**它不管什么**：

- **Anthropic → Responses 方向**的 reasoning 映射——那是 `anthropic-responses-bridge/spec.md` 的管辖，其 `:30` 把范围写死在「选择 Responses upstream 后」，`:205` 是它对 thinking→reasoning capability gate 的条款。两个 topic 按**目标格式**切分，互不覆盖。
- **响应方向**的整形（SSE 里 thinking block 的 signature 位置等）——`docs/.human-controlled/message-format-reshape.md`「改写上游 Anthropic Messages 输出」一节。
- **错误信封**怎么渲染给客户端——`error-envelope/`。它管一个 400 到达客户端后长什么样，本 topic 管为什么那个 400 不该发生。

## 文档

| 文件 | 是什么 |
|---|---|
| [spec.md](spec.md) | 规范。活文档，随裁定与实测持续修订。 |
| [status.md](status.md) | 现在实现成了什么样，以及判据做过哪些变异验证。 |
| [review-disposition.md](review-disposition.md) | 实施评审 7 条发现的逐条处置，含只采纳一半的那条的理由。 |
| [reports/](reports/) | 时点报告原件，不改写。 |

## 这个 topic 为什么现在才存在

`sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62` 在 2026-08-22 就写下了成因并建议立项：

> **`claude-sonnet-5` 不支持 Responses API**（实测 `unsupported_api_for_model`）。这意味着翻译路径承载不了 Claude 系模型，它们只能走直连。超出本轮范围，建议单独立项。

这条预告正确，但两天里没有被提炼进任何活文档，于是「Claude 系模型只能走直连、而直连腿的 thinking 构造没有任何 owner」这个事实只活在一份报告里。2026-08-24 的线上 400（`req=530e0e10-c724-45a0-964a-129c3351646a`）正是它的第一次兑现。立此 topic 同时清掉那处「报告成了唯一真相来源」。
