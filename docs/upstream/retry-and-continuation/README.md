# 上游请求的重试与续写

**读这个目录从 [`status.md`](status.md) 开始**——那里是当前实现状态与分阶段路线。未闭合与待查项在 [`deferred.md`](deferred.md)。

## 权威在哪

**唯一权威是用户亲笔的 [`docs/.human-controlled/upstream-retry-and-continuation.md`](../../../../docs/.human-controlled/upstream-retry-and-continuation.md)。** 本目录的一切都是它的实现记录、证据与推论；任何一句与它相违背的，以它为准，并且要来改本目录而不是改它。

本目录**不复述**该文档的裁决，只在需要上下文时引用并指回。

## 这个主题回答什么

一次发往上游的模型请求失败了，接下来做什么。答案分两层：

1. **先判这次结束是不是上游造成的。** 客户端断开、进程优雅关闭、代理自己的保护机制触发，都不是上游失败，不进重试。
2. **再判客户端已经看到了什么。**
   - **还没交付过完整块** → 代理端**无痕重试**。客户端一无所见，第二次尝试可以无痕替代第一次。全协议生效。
   - **已经交付过至少一个完整块** → **MCP-driven 续写**。把错误合成为一个 `tool_use` 块，调用 MCP 工具 `turn_interrupted(num_messages, category, message)` 交回客户端；客户端执行它、拿到「继续」的指令、自然地发起下一轮。仅在 **anthropic-messages 客户端请求**上生效。

第 2 层的关键取舍是：**承载续写的是客户端自己的对话历史，不是代理构造的请求。** 这一条决定了它和被放弃的代理内续写之间的全部差别——见 [`archive-proxy-side-continuation/README.md`](archive-proxy-side-continuation/README.md)。

## 目录

| 路径 | 是什么 |
|---|---|
| `status.md` | **活文档**。当前实现状态、分阶段路线、每阶段的验证方式 |
| `decisions.md` | 裁决记录：哪条写进了人写文档、哪条只存在于讨论中、哪条其实是本项目的推论、哪条还没裁 |
| `deferred.md` | 未闭合、待查、以及明确不做的 |
| `archive-proxy-side-continuation/` | 被裁决放弃的代理内续写方案，及其三轮评审。原件逐字保留 |
| `reports/` | 本主题的调查报告原件 |

## 支撑本主题的实测证据

下面每条都来自真实录制或代码直读，不是推断。完整报告在 `reports/`。

| 事实 | 证据等级 | 出处 |
|---|---|---|
| 撞 `max_output_tokens` 时，上游为被截断的 item 发出 `output_item.done`——**观测到的 20/20 例皆如此** | 录制，n=20，逐例。**样本边界**：2026-08-04～08，模型 `gpt-5.6-sol`／`gpt-5.6-terra`，`incomplete_details.reason` 仅 `max_output_tokens` 一种。随时间或模型变化未排除 | `reports/260821-max-tokens-block-completeness.md` |
| 因此被截断的那个 item 自己会被交付成一个完整块 | **代码事实**（`assembler.py:231-232` → `_close`：`output_item.done` 是块完成的唯一判据），在上一行成立的前提下 | 同上 |
| 被截断的 item 在 `output_item.done` 上带 `status:"incomplete"`，完整的带 `"completed"`；**reasoning item 没有这个字段**（与正常收尾的 reasoning item 键集逐字相同，已做正样本对照） | 录制，`status:"incomplete"` 实测 15 次（4 次在 `function_call` 上） | 同上 + `evidence/probe-reasoning-item-control.py` |
| Responses 腿的终止只有 `response.completed`(64351) 与 `response.incomplete`(20)；`response.failed`／`cancelled`／上游 `error` 帧**各 0 次** | 录制，134336 个 operation | `reports/260821-upstream-termination-reasons.md` |
| `incomplete_details.reason` 20/20 全是 `max_output_tokens`，**没有第二个取值** | 录制 | 同上 |
| Anthropic 腿实测到的 `stop_reason`：`tool_use`(124927)、`end_turn`(8290)、`max_tokens`(24)、`refusal`(1)。`model_context_window_exceeded` **零观测** | 录制 | 同上 |
| 上下文超限走 HTTP 400，**两条腿形态不同**：Anthropic 腿 `error.code=model_max_prompt_tokens_exceeded` 且 message 带数字；Responses 腿 `error.code=invalid_request_body`（与其他参数错误共用，不可据以区分）且 message **无数字** | 录制，48 例一手 | `reports/260821-context-limit-400-examples.md` |
| Claude Code 的 `stop_reason` schema 是 `string().nullable()` **无枚举**，未知值不报错、直接跳过 | 代码事实，CC 2.1.226 | 同上 |
| Claude Code 对不认识的工具名发回 `No such tool available` 的 tool_result，**不崩溃**，对话继续 | 代码事实 | `~/.claude/skills/debugging-claude-agent-tools/reference/source-symbols.md:21` |
| 前身 `copilot-api-js` 的 `max_tokens` 处理**只接在 Anthropic 直连腿**，Responses 腿的谓词零调用点；官方 `vscode-copilot-chat` 对被截断的 tool call 是静默丢弃 | 代码事实（八个参考仓） | `reports/260821-reference-projects-max-tokens.md` |
| live 链路的重试**只存在于上游响应头到达之前**，无退避无 jitter；**读流中断零重试** | 代码事实 | `reports/260821-upstream-error-handling-survey.md` |

## 相邻主题

- [`../h2-goaway/`](../h2-goaway/) —— GOAWAY 打掉在飞流的机理诊断，已收口。它的「三条路的裁决」欠账由本主题接手。
- [`../../anthropic-responses-bridge/`](../../anthropic-responses-bridge/) —— 桥 spec，冻结中。本主题的 wire 不变量指回它。
- G1「让活跃链路认出上游发来的错误事件」（分支 `fix/upstream-error-events`，同伴在飞）—— 本主题依赖它：`stop_reason` 原样透出与上游 `error` 帧不再静默丢弃，都要它先落地。
