# Copilot Responses 会话绑定候选

> **候选材料，不是人控合同。** 本文只供用户自行摘取到 `docs/.human-controlled/message-format-reshape.md`；在用户采纳前，它不能被实现、评审或运维说明当成已经批准的公开协议。

Anthropic Messages 翻译到 Copilot Responses 时，客户端的逻辑会话标识需要参与上游会话绑定。按优先级识别以下请求头：`x-claude-code-session-id`、`x-session-id`、`x-conversation-id`、`x-chat-session-id`、`x-thread-id`、`x-interaction-id`。

这些请求头不应作为客户端自有请求头原样转发；代理应将第一个非空值写入上游自有的 `X-Interaction-Id`。没有客户端会话标识时，Copilot provider 使用启动期生成、跨请求稳定的 UUID。其它客户端协议协商请求头仍不因这一规则进入翻译后的上游请求。
