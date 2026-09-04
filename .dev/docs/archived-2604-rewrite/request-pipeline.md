# Anthropic 请求执行管道

## 请求流程

```text
parse typed request
  → request_received observers
  → pre_sanitize payload hooks
  → mandatory message sanitizer
  → post_sanitize payload hooks
  → wire/header preparation
  → optional approval
  → rate limiter
  → pre_send payload hooks (per attempt)
  → upstream
  → success response hooks/observers or error observers/retry decision
  → finalize observers + history
```

Pipeline 的单一状态载体是 `RequestContext`。每次上游尝试记录一个 `Attempt`，包括状态码、错误、strategy owner、payload modifications 与 hook telemetry。

## Retry ownership

`RetryCoordinator` 逐序询问每请求创建的 strategies。一个 attempt 最多由一个 strategy owner 修改 payload；决定重试后，修改后的当前 wire payload 会再次经过 `pre_send` hooks。

当前生产策略为 `PoisonedThinkingStrategy`：匹配 thinking block 被修改的 400，剥离 thinking 后重试一次；成功后将 `(session, agent)` 记录到内存 quarantine，后续请求可主动剥离。

Prompt-limit 错误不会触发代理侧历史截断、压缩或摘要。失败 observer 只记录：

- 本地估算与上游报告真实 input token 的校准样本。
- 上游报告的 prompt limit observation。

随后原错误按原状态返回客户端。

原生 server-tool rejection 没有专用 retry、降级或过滤路径。

## Hook 错误语义

- Payload/Response hook 默认为 fail-request；注册实现可显式选择 `continue`。
- Observer 的异常或 timeout 记录 warning 与 telemetry 后隔离，不改变请求结果。
- 用户 hook 调用受 `hooks.timeout_ms` 限制。
- Registry 在 lifespan 启动期构建不可变快照，请求期间不热替换。

每次调用记录 `name/type/phase/duration_ms/modified/error`。

## Streaming

流式 wire chunks 仍按 bytes 直通。`AnthropicSSEUsageTap` 只在旁路增量解析 usage：

- 输出 chunk 与输入 chunk 对象内容逐字节一致。
- 不重编码、不合并、不吞掉 frame。
- 流结束后才调用 usage observers。

Streaming event transform 不属于首版通用 Hook API；idle timeout、keepalive、delayed commit 与 buffered retry 保持 transport 基础设施。

## 状态机

```text
pending → sanitizing → executing → streaming → completed
                             └──────────────→ failed
```

非法状态转换抛出 `RuntimeError`。非流式响应在 response hooks 成功后才进入 completed；流式响应由流包装器在正常耗尽后完成，提前中断记为 499 network failure。

## 相关文档

- [Hooks 机制](hooks-system.md)
- [消息清洗](sanitize-pipeline.md)
- [Tokenization](tokenization.md)
- [Thinking 管道](thinking-pipeline.md)
