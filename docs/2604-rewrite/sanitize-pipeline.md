# Anthropic 消息清洗

## 边界

协议必需的消息合法性修复由 `anthropic/sanitize/` 承担，不能被用户 hook 禁用。可选改写位于 mandatory sanitizer 前后的 payload hooks，详见 [hooks-system.md](hooks-system.md)。

代理不会为解决 prompt 超限而删除旧消息、压缩历史工具结果或注入摘要。Prompt limit 只被观察和报告，详见 [tokenization.md](tokenization.md)。

## 当前顺序

1. `process_tool_blocks()` 修复 client `tool_use` / `tool_result` 配对与工具名大小写。
2. `filter_empty_text_blocks()` 删除空 text blocks。
3. 删除清洗后 content 数组为空的消息。
4. `post_sanitize` built-in hooks 执行可选改写：Read 结果标签清理、thinking destack、tool preprocessing；内容去重默认关闭。

## Tool pair/orphan repair

Anthropic 要求 assistant `tool_use` 与**紧随其后的** user `tool_result` 配对。修复算法按局部相邻关系处理，而不是全局 ID 集合：

- 只允许紧随 assistant 的 user 消息提供结果。
- 并行 calls 独立取局部交集，完整 pair 保留，缺失一侧的 block 删除。
- 同一 assistant 或跨轮重复 ID 只保留全局首次出现的完整 pair；后续重复项删除。
- 同一 user 消息里重复 result 只保留第一次。
- 保留下来的 `tool_result` 稳定移动到 user content 最前；其他 text/image/document blocks 保持相对顺序。
- 只有保留下来的 `tool_use` 才按当前 tool definitions 修正 name casing。
- 删除工具 block 后仍有普通内容的消息保留；完全空的消息删除。
- 算法幂等，第二次执行不会产生新修改。

原生服务端执行工具不属于这套 client-tool 配对逻辑。本项目不注入、降级、过滤或重试原生 server-tool 能力；未知历史块由协议保真模型透传，上游拒绝则原样返回错误。

## 统计

`SanitizationResult` 记录：

- `orphaned_tool_uses_removed`
- `orphaned_tool_results_removed`
- `empty_text_blocks_removed`
- `tool_names_fixed`

统计附在 `RequestContext`，用于历史与诊断。

## 与 Hooks 的关系

- `pre_sanitize`：mandatory sanitizer 前，可信扩展可调整 typed payload。
- mandatory sanitizer：不可禁用的协议修复。
- `post_sanitize`：合法消息形成后执行 built-in/user payload hooks。
- `pre_send`：每次 attempt 发送前执行；retry strategy 修改后的 payload 会先经过该阶段再发送。

可选 `builtin:deduplicate_tool_calls` 按 name/input/result 内容签名删除重复 pair，默认关闭。它与 ID 配对修复正交：ID 不同但内容相同的完整工具轮次在协议上合法，不应默认删除。

## 相关文档

- [Hooks 机制](hooks-system.md)
- [Tool Use](tool-use.md)
- [Tokenization](tokenization.md)
- [请求管道](request-pipeline.md)
