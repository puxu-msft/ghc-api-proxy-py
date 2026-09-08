# Tool Use 机制

## 支持边界

本项目支持客户端执行工具：

- 请求 `tools` 中声明普通工具。
- assistant 产生 `tool_use`。
- 客户端执行后在下一条 user 消息回传 `tool_result`。
- Mandatory sanitizer 修复配对、重复 ID、result-first 顺序和 name casing。

本项目不支持 Anthropic 原生 server-tool 编排：不执行 web search/fetch/code execution，不合成服务端签名结果。普通模型使用 `extra="allow"` 保持 wire 兼容性，但未知字段透传不代表代理提供对应能力。

**2026-08-20 起，「不过滤服务端 blocks」不再成立**（用户裁决，见 [hooks-tokenization-spec.md](hooks-tokenization-spec.md) §5.2 的增补段）。路由到 Copilot 的 Anthropic Messages 端点时，`builtin:server-tool-capability` 订阅者（`src/app/pipeline/subscribers/server_tools.py`）在出站前做两件事：

1. 剥掉 `tools[]` 中上游已实测拒绝的 server-tool 声明，并清理因此悬空的 `tool_choice`；
2. 把历史里残留的 `server_tool_use` 与 `*_tool_result` blocks **摊平成纯文本**。

理由：该端点对这类声明整条拒绝请求（`The use of the web search tool is not supported.` / `unsupported_value`），一条声明就让整轮对话失败，而客户端下一轮会原样重放。第一方的 VS Code Copilot Chat 做法相同——出站前过滤掉 `web_search*`，并对其 Claude Code 集成直接 `disallowedTools: ['WebSearch']`。

摊平而非降级成 `tool_use`／`tool_result` 对：降级只在工具仍被声明时成立，而声明刚被剥掉，残留引用仍会被上游拒绝（参考项目为这种情形匹配 `Tool 'X' not found in provided tools`，本项目未自行实测该措辞）。也无法就地修复——上游要求每条搜索结果带真实非空 `encrypted_content`，空串与占位串都被拒绝。

**仍然不成立的是反应式路径**：本项目不在收到 400 后剥离并降级重试。判据读的是**我们自己发出的声明类型**，不是上游的错误措辞——同一条规则上游有两套 body（`unsupported_value` 与 `invalid_request_body`），按单一文本写 matcher 会漏。

剥离清单只含已实测被拒的族（`web_search*`、`web_fetch*`）。`memory_*`、`tool_search_*`、`text_editor_*`、`bash_*`、`computer_*` **刻意不剥**：它们由客户端执行，Claude Code 确实会发，没有任何证据表明上游拒绝它们。

Responses leg 的 hosted web search 支持是**另一件事**，尚未实现，见 [anthropic-compat.md](anthropic-compat.md) 与开发文档 `docs/tmp/260820-websearch-fix-v2-design.md`。

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
