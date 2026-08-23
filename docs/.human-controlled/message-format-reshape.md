# 模型请求与响应的消息格式的整形

GHC API 虽然声称支持 anthropic `/messages` `/messages/count_tokens` 和 openai `/responses` 等，但有其怪癖，我们需要按需消毒。

## 客户端输入 Anthropic Messages

这部分仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效。

### 剥离请求头

一般地，**直连路径上**，客户端请求头值得原样转发给上游，仅部分请求头是需要剥离的，即采用黑名单机制。翻译路径不遵循这一点，翻译路径采用白名单机制。

直连路径的黑名单有：（大小写不敏感）
- `Forwarded` chain
- `Authorization` `Cookie` `X-Api-Key`
- `Host`
- `Content-Length` `Content-Encoding` `Accept-Encoding`
（TODO：这些条目来自 `copilot-api-js` 项目，需要了解原因）

翻译路径的白名单有：
- （暂无）

### 总是剥离 attribution header

问题：Claude Code 把 attribution header `x-anthropic-billing-header: cc_version=…; cc_entrypoint=…;` 放在请求体 `system[0]`，GHC API 不认，需要剥离。

处置：在路由前剥离整个属性行（不仅是 `x-anthropic-billing-header`，全部剥离），如果剥离后该 `system[0]` 为空或纯空白字符，删除该项。

TODO：用户想知道 GHC API 不认 `x-anthropic-billing-header:` 还是 GHC API 不认 `system[0]` 中的任何 attribution？

用 `hook_strip_anthropic_request_headers.strip_attribution_header` 配置控制生效，默认禁用。额外提醒，保存历史记录时的原始客户端请求不应受此处理影响。

用户也可以给 Claude Code 配置环境变量 `CLAUDE_CODE_ATTRIBUTION_HEADER=0`，同样剥离所有 attribution headers。但这属于客户端行为，我们作为代理层做好剥离防护即可。

早期，旧版 Claude Code 通过 HTTP 头 `x-anthropic-billing-header` 发送 attribution billing line，现已不再使用，故我们也不为此特殊处理。

### 按需剥离 `anthropic-beta` 请求头的部分 flag

`anthropic-beta` 请求头表示希望访问的功能特性，是与模型能力相关的，不满足则报错 `400 invalid beta flag`。例如 `config.example.yaml` 中配置了

```yaml
strip_anthropic_beta_flags:
  claude-sonnet-4.6:
    # 400 invalid beta flag
    - interleaved-thinking-2025-05-14
    - context-management-2025-06-27
    - prompt-caching-scope-2026-01-05
    - mid-conversation-system-2026-04-07
```

## 客户端返回 Anthropic Messages

直连路径的黑名单有：
- `Connection` `Keep-Alive` `Proxy-Connection` `Hop-By-Hop`
- `Date` `Cache-Control` `Set-Cookie`
- `Content-Length` `Content-Encoding` `Transfer-Encoding`
（TODO：这些条目来自 `copilot-api-js` 项目，需要了解原因）

翻译路径的白名单有：
- `Request-Id` `X-Request-Id`
- `Anthropic-Organization-Id`
- `Anthropic-RateLimit-*` `Retry-After`
（TODO：这些条目来自 `copilot-api-js` 项目，需要了解原因；根据我的认知，翻译路径理应“翻译”而做不到“透传”部分字段，非 Anthropic 上游可能产生含义相同形式不同的请求头；在认清之前翻译路径的处置先不做）

## 向上游输出 Anthropic Messages

### assistant 消息的 thinking / redacted_thinking 块不允许相邻（400 "thinking blocks cannot be modified"）

部分客户端请求中却意外出现该情况，需要整形。

用 `hook_fix_anthropic_request.thinking.assistant_message_layout` 配置选项控制：
- `false`: 啥也不做、透传。
- `move_and_synthetic`: 与同意 assistant 消息内的其他非 thinking 块保序交错，其他块不足时，在 thinking 块之间插入合成标记（空格文本块；不是空文本块是因为它不被允许）。（默认）
- `synthetic_only`: 不动其他非 thinking 块，仅在相邻出现的 thinking 块之间插入合成标记。

### 剥离 signature text 都为空的 thinking/redacted_thinking 块

曾经用 `hook_fix_anthropic_request.thinking.strip_both_empty_thinking_blocks` 配置控制生效，现在我认为这是应该常驻的。

## 改写上游 Anthropic Messages 输出

### 部分上游模型在 SSE 传 thinking block 的 signature 嵌在 `content_block_start`

TODO：确认 Claude 新版是否接受这种情况，如果不接受，整形：将嵌入的 signature 抽成单独的 `signature_delta`。

曾经用 `hook_fix_anthropic_sse.thinking.content_block_start_compat` 配置控制生效，现在我认为（如果客户端真的不支持）这是应该常驻的。

TODO：该灵感抄自 copilot-api-js 项目，用户想了解原项目对该情形的处理。
