# Hooks 机制

## 类型

Hooks 不使用万能 callback，分成四类：

1. `PayloadHook`：按 phase 链式修改请求 payload。
2. `RetryStrategyFactory`：每请求创建有状态 retry strategy。
3. `ResponseHook`：修改完整非流式响应 bytes。
4. `ObserverHook`：只读生命周期事件，不能修改请求/响应。

## Payload phases

- `pre_sanitize`：typed request 解析后、mandatory sanitizer 前。
- `post_sanitize`：mandatory sanitizer 后、wire/header finalization 前。
- `pre_send`：每个 attempt 即将发送前；retry 修改后的当前 payload 会先经过该阶段。

`HookContext` 是 frozen snapshot，包含 request/endpoint/protocol/model/session/agent/attempt/settings，不提供可变 `extra` 暗通信道。

## Registry 生命周期

`HookRegistryBuilder` 仅在 lifespan 启动期可变。注册完成后 `build()` 产生不可变 registry：

- Hook name 全局唯一。
- Built-ins 使用 `builtin:*` 与 order `0..999`。
- 用户 hooks 禁止 `builtin:*`，order 必须 `>=1000`。
- 同类 hooks 按 `(order, name)` 稳定排序。
- Build 后继续注册会报错。

用户 module 通过 `hooks.modules` 显式声明，并导出：

```python
def register(builder, settings):
    builder.register_payload(MyHook())
```

Import 失败、缺少 `register()` 或 name 冲突都会阻止启动。Modules 是可信本地代码，与代理同进程、同权限运行；没有 sandbox。

## 错误语义

- Payload/Response 默认 fail-request；实现可显式选择 `HookErrorMode.CONTINUE`。
- Retry factory/strategy 异常不是“不匹配”，应终止对应决策。
- Observer 异常和 timeout 被隔离，只记录 warning 与 telemetry。
- 用户 hook 受 `hooks.timeout_ms` 限制。

Telemetry 记录：`name`、`type`、`phase`、`duration_ms`、`modified`、`error`。

## Built-ins

默认注册：

- `builtin:strip_read_tool_result_tags`
- `builtin:thinking_destack`
- `builtin:poisoned_thinking`
- `builtin:token_calibration_success`
- `builtin:token_calibration_failure`

`builtin:deduplicate_tool_calls` 仅在 `hooks.deduplicate_tool_calls=true` 时注册。

`builtin:tool_preprocessor` 不再注册为跨协议 payload hook。该名称仅作为兼容禁用键保留：默认情况下，普通 client tools 的 defer-loading 与 tool-search wire adaptation 在 route 已确定为 direct Messages 后、`PRE_SEND` 前执行；将完整名称列入 `hooks.disabled` 会关闭这项 Messages-only preparation。内建 tool preparation 不会向 Responses leg 注入 direct-Messages 专属字段或 server-tool declaration；可信用户 hook若自行加入不受支持的字段，Responses converter会显式拒绝。

Mandatory tool pair/orphan repair、模型解析、认证、header security floor、审批、限流、RequestContext 状态机、History lifecycle 与 transport 正确性不可 hook 化或禁用。

## Streaming 边界

首版没有通用逐事件 transform hook。Anthropic usage 由专用 byte-preserving tap 旁路采样，原 chunks 不重编码、不合并。Keepalive、idle timeout、delayed commit 与 buffered retry 仍属于 transport 基础设施。

## 示例配置

```yaml
hooks:
  modules:
    - my_proxy_hooks
  disabled:
    - builtin:strip_read_tool_result_tags
  timeout_ms: 3000
  deduplicate_tool_calls: false
```

## 相关文档

- [请求管道](request-pipeline.md)
- [消息清洗](sanitize-pipeline.md)
- [Tokenization](tokenization.md)
