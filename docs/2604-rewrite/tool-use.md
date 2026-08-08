# Tool Use 机制

## 支持边界

本项目支持客户端执行工具：

- 请求 `tools` 中声明普通工具。
- assistant 产生 `tool_use`。
- 客户端执行后在下一条 user 消息回传 `tool_result`。
- Mandatory sanitizer 修复配对、重复 ID、result-first 顺序和 name casing。

本项目不支持 Anthropic 原生 server-tool 编排：不执行 web search/fetch/code execution，不合成服务端签名结果，不过滤服务端 blocks，也不在拒绝后剥离并降级重试。普通模型使用 `extra="allow"` 保持 wire 兼容性，但未知字段透传不代表代理提供对应能力。

## Client tool 配对

完整规则见 [sanitize-pipeline.md](sanitize-pipeline.md)：

1. `tool_result` 只能匹配紧随其前的 assistant 消息中的 `tool_use`。
2. ID 通过 `tool_use.id == tool_result.tool_use_id` 匹配。
3. 并行调用允许多个 pair。
4. 缺失或重复项按 block 粒度清除，不删除同消息中的普通内容。
5. User content 中所有保留的 `tool_result` 排在 text/image/document 之前。

## Tool preprocessing

普通 client tool preprocessing 是 direct Messages wire preparation，不是跨协议 `post_sanitize` payload hook。Route 确定为 Messages 后、`PRE_SEND` 前执行以下 adaptation：

- 普通 tool definitions 可按配置标记 `defer_loading: true`。
- `anthropic.tool_search_non_deferred` 中的工具保持 eager。
- `anthropic.tool_search=true` 时注入 Copilot 专用 `tool_search_tool_regex_20251119` 声明。
- 未知字段深拷贝保留。
- 带非空 `type` 的 API-defined typed tools 不被改写为 deferred；代理只透传其声明。

`tool_search` 是 Copilot 的工具发现 wire extension，并不意味着代理实现 Anthropic 原生 server-tool 执行或响应过滤。

Responses leg 的内建 preparation 保持普通 function tool 的 Anthropic canonical shape，随后由 Responses converter 同时转换 declaration、forced choice、历史 call 与 result；不得先注入 `defer_loading` 或 Anthropic tool-search server declaration。可信用户 hook若自行加入这些不受支持字段，converter会显式拒绝。兼容配置名 `builtin:tool_preprocessor` 仍可列入 `hooks.disabled`，其效果是关闭 Messages-only defer-loading 与 tool-search preparation；该名称不再产生 payload-hook 执行记录。

## Read tool 结果标签

`builtin:strip_read_tool_result_tags` 清理标记为 Read 结果的 `<system-reminder>` 内容。它是可禁用 built-in payload hook，不是协议合法性修复。

## 内容去重

`hooks.deduplicate_tool_calls=false` 为默认。启用后注册 `builtin:deduplicate_tool_calls`，按 `(name, input, result)` 内容签名保留首次完整 pair，并按 block 粒度删除后续重复 pair。该 hook 不替代 mandatory ID 配对修复。

## 配置

```yaml
anthropic:
  tool_search: true
  tool_search_non_deferred: []

hooks:
  deduplicate_tool_calls: false
  disabled: []
```

## 相关文档

- [消息清洗](sanitize-pipeline.md)
- [Hooks 机制](hooks-system.md)
- [Anthropic 兼容](anthropic-compat.md)
