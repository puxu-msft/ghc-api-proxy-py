# 上游请求的重试

建立在“客户端块级交付”的基础上，当上游问题造成请求失败时，先区分业务是否因此无法继续。如果无法继续，直接返回给客户端。

这些情况下无法继续：

- 客户端已断开，取消上游请求
- 代理的保护机制触发（如块的内存缓存超限）
- 400
- 401，如凭据过期
- SSE stop_reason = refusal

这些情况下一般可以继续：

- 网络中断
- 请求超时
- 429 Too Many Requests
- 5xx
- SSE stop_reason = max_tokens / max_output_tokens

如果业务可能可以继续，区分是否已经向客户端交付过完整块。如果还没交付过完整块，直接在代理端无痕重试。

特殊地，`max_tokens` 不应无痕重试。TODO：参考项目对 `max_tokens` 的处理方案是什么？一般是否已经交付过完整块，只是最后一个块被截断了？

特殊地，优雅关闭时不应无痕重试，走下文“MCP-driven 合成续写”机制。

其中，HTTP 429 会启用“反应式限流器”，而不是立即重试，如果预算耗尽，最后一次尝试是限流重试，返回给客户端的应该是 429 + Retry-After。（用户已裁决删除 `client_delivery.synthesized_response_headers_after_sec`，因为这种情况下没有交付过完整块，也不再出现半开 `message_start` 需要考虑。）

## MCP-driven 合成续写

如果已经交付过至少一个完整块，则将报错合成为自制的 `tool_use` / `function_call` 块，调用 MCP 工具 `mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted(num_messages, category, message)` 返回给客户端。这里 `num_messages` 是客户端请求中 `messages` / `input` 的长度，用于检测和避免无进展的重试循环。

客户端会正常调用该 MCP，待 MCP 返回结果后继续会话，形成续写。

该工具调用全名可通过配置项 `upstream_request_retry.auto_retry_tool_call_full_name` 覆盖。

检查客户端请求是否包含该工具调用的定义，如果没有，在本代理日志中打印警告日志，但仍然依样返回给客户端。

MCP-driven 续写是否需要次数上限？不需要，因为出现这种情况说明事情有进展，是好事，即使多次触发此种重试，事情也是不断进展的。

限制：目前我只使用 Claude Code，所以这里续写协议的格式描述都是 CC-style，但该机制本应是通用的，其他客户端也可以实现类似的续写协议。我接受目前只给 anthropic-messages 客户端请求时使用该机制，其他上游请求暂不使用该机制。未来我有需要后再补全。

## 代理内续写（已放弃）

如果业务可能可以继续，检查已提交给客户端的块是否包含工具调用。如果包含工具调用，因为工具调用可能有副作用，将报错作为 SSE error 返回给客户端，交给下一次携带工具调用的请求来续写。

如果已提交的块不包含工具调用，则在客户端无感知的情况下，代理端带上已提交的块、续写一条 `role: user` 的消息，内容为 "network error occurrend, please retry"。向上游发起该请求，作为重试。

```yaml
upstream_request_retry:
    # 续写：已经有块提交给客户端（非工具调用）后请求中断，代理合成续写轮直接重投（已提交块作 assistant + 续写 user）。
    # Continuation: some block was committed to the client, a mid-stream RST occurs -- the proxy appends messages (the already-committed blocks as an assistant turn + this user message) so the model continues.
    continuation:
      enabled: true
      max_retries: 10
      message: "Please continue where you left off."
```
