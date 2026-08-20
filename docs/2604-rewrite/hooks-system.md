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

## 事件订阅（新链路）

本节描述的是**新处理链**上的机制，与上面四类 hooks 并存但方向已定：`MAIN.md` 要求驱动提供事件订阅点，订阅者传入唯一 id 与可选的「插入到谁之前/后」，能修改公共对象、也能靠抛不同异常触发中止/重试。已裁决的方向是**订阅机制吸收 hooks**，「要不要吸收」不再重开；细节与剩余待裁决点见 [pipeline-subscriptions.md](../.human-controlled-candidates/pipeline-subscriptions.md)。

### 已建成

| 件 | 位置 |
|---|---|
| 注册表与定序 | `src/app/pipeline/events.py`。唯一 id、`before`/`after` 拓扑排序，顺序在 `freeze()` 时解析一次并固化；重复 id、引用不存在的 id、成环都在 freeze 时失败，同序并列按注册顺序决定 |
| 驱动事件 | `src/app/pipeline/direct_driver/base.py`：`attempt.prepare`、`attempt.succeeded`、`attempt.failed`、`request.succeeded`、`request.failed`。事件名由发布它的驱动拥有 |
| 异常闭集 | `src/app/pipeline/exceptions.py`。闭集外的一切由 `classify()` 判为 ABORT |
| 内置订阅者与注册 | `src/app/pipeline/subscribers/`，由 `build_chain`（`src/app/server/composition.py`）注册，调用点无需改动 |

`attempt.prepare` 在**重试循环内**发布，订阅者修改 `context.payload` 后驱动重新读取；它同时覆盖直通腿与翻译腿，但翻译发生在驱动之前，所以订阅者在翻译腿上看到的是**已翻译成目标格式**的载荷。需要在翻译前动手的改写不属于这个事件。

### 内置订阅者

| id | 事件 | 作用 |
|---|---|---|
| `builtin:server-tool-capability` | `attempt.prepare` | 路由到 Anthropic Messages 端点时，剥掉上游已实测拒绝的 server-tool 声明、清理因此悬空的 `tool_choice`，并把历史里残留的 server-tool blocks 摊平成文本。见 [tool-use.md](tool-use.md) |
| `builtin:blank-text-blocks` | `attempt.prepare`（注册在上一条之后） | 路由到 Anthropic Messages 端点时，剥掉上游拒收的空／纯空白文本块。两者之间没有数据依赖：上一条写出的每个文本块都带 `[family]` 前缀，永远不空，触发不了这一条。末位是约定——只做删除的 pass 放在改写者之后，看到的才是真正会发出的形态 |

顺序表与「为什么它排在那里」写在 `src/app/pipeline/subscribers/__init__.py` 的模块文档里，锁定它的测试是 `tests/unit/test_builtin_subscribers.py`。

### 尚未建成

- **配置面**。内置订阅者目前没有开关：协议兼容性修复属于不可禁用的 mandatory sanitizer，与 `normalize_context_management` 一样本就无开关。`config.example.yaml` 的 `hooks:` 一节另给了六个**面向运维**的订阅点（`on_client_request_parsed` 等），与驱动内部的 `attempt.*` / `request.*` 不是同一层，其**列表项语义尚未定义**——是模块路径还是订阅者 id，见 [config-migration-gaps.md](../.human-controlled-candidates/config-migration-gaps.md)。配置面等这道裁决落地后再补。
- **响应侧接入点**。新链路上非流式只有翻译，流式链全程无订阅点；`config.example.yaml` 已定名的两个 SSE 块级点尚未发布。
- **吸收本身**。`src/app/hooks/` 的四类 typed 契约、loader、executor 仍只接在 legacy app 上，没有一个内置 hook 迁过来。

## 相关文档

- [请求管道](request-pipeline.md)
- [消息清洗](sanitize-pipeline.md)
- [工具使用](tool-use.md)
- [Tokenization](tokenization.md)
- [订阅机制如何吸收 hooks（候选）](../.human-controlled-candidates/pipeline-subscriptions.md)
