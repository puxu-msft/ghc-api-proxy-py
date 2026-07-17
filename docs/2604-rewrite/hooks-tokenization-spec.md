# Hooks、Tokenization 与协议修复规格

> 状态：已实施并通过测试
> 日期：2026-07-17
> 关联：`DESIGN.md`、`request-pipeline.md`、`sanitize-pipeline.md`、`tool-use.md`

## 1. 背景与决策

本项目删除代理侧 `auto_truncate` 与 Anthropic server-tool support。代理不得通过删除旧消息、压缩历史 `tool_result`、注入截断摘要或其他历史改写来处理 prompt 超限；这些行为破坏请求前缀稳定性与上游 KV/prompt cache，并且会在代理层隐式改变对话语义。

从原 auto-truncate 主题中保留四类正交能力：

1. 协议级 token-count endpoints 与本地估算。
2. 不改写请求的本地计数校准。
3. 从上游错误中观察模型真实 prompt limit。
4. Anthropic client-tool 的 `tool_use`/`tool_result` 配对修复。

同时增加强类型 hooks 机制，把可选改写、重试策略、响应变换和旁路观察从核心管道中解耦，供内建实现与可信用户模块复用。

## 2. Token count 的协议边界

`count_tokens` 不是全项目只有一个端点，但其 wire contract 属于具体协议：

- Anthropic：`POST /v1/messages/count_tokens`，优先转发上游精确计数，失败时本地估算。
- Gemini：`POST /v1beta/models/{model}:countTokens`，当前使用本地估算。
- OpenAI Chat/Responses 与 Azure：没有独立 count-tokens endpoint，只在完成响应中报告 usage。

因此不能把 Anthropic endpoint service 伪装成协议无关 API。模块化后采用以下边界：

```text
src/app/tokenization/
├── __init__.py
├── estimators.py       # 各协议的纯本地估算器与共享 tokenizer
├── calibration.py      # 按 protocol + model + size bucket 的校准模型
├── limits.py           # prompt-limit 错误解析与观测存储
└── service.py          # Anthropic 上游优先/本地 fallback 编排
```

- `tokenization.estimators` 可以有协议专用入口，例如 `estimate_anthropic_input()` 与 `estimate_gemini_input()`；共享的是 tokenizer 生命周期、offload 策略与结果契约，不强造统一 canonical payload。
- `tokenization.service.AnthropicTokenCountingService` 负责 Anthropic wire endpoint 的上游转发和 fallback。上游 transport 的 `send_anthropic_count_tokens()` 继续留在 `upstream/`。
- Gemini route 复用 `estimate_gemini_input()`，但不消费 Anthropic calibration。不同 wire protocol 的序列化开销与真实计数口径不同，校准 key 必须包含 protocol。
- 原 `anthropic/token_counting.py` 删除；其实现迁入上述模块。

## 3. 本地计数校准

### 3.1 目标与硬约束

校准只修正“本地估算值”，不得：

- 改写 payload。
- 触发截断或重试。
- 覆盖模型 catalog 的能力声明。
- 把一种协议的样本用于另一种协议。

### 3.2 数据模型

校准 key 为 `(protocol, normalized_model)`，其中模型规范化统一复用 `transform.model_resolver.normalize_for_matching()`，不得另写第二套规则。每个 key 保存固定边界的 size buckets：

```text
[0, 15k), [15k, 30k), [30k, 60k), [60k, 120k), [120k, 240k), [240k, +∞)
```

每个 bucket 保存 `sum_real`、`sum_estimated`、`sample_count`、`mean_estimated`。factor 为 `sum_real / sum_estimated`，由 `FACTOR_CLAMP_MIN = 0.5` 与 `FACTOR_CLAMP_MAX = 3.0` 限制；bucket 间按 `mean_estimated` 做 log-linear interpolation。无样本时 factor 为 `1.0`。

单 bucket 使用 `WEIGHT_CAP = 2000` 的有界滑动权重，防止历史数据永久冻结模型。状态使用版本化 JSON，经 off-event-loop、serialized、atomic replace 写入用户数据目录。损坏文件告警后从空状态启动；数据可重新学习。

`TokenizationStateStore` 是应用生命周期单例。Observer 和 count service 只更新其内存状态并标记 dirty；lifespan 启动一个固定间隔的单 writer flush loop，关闭时在取消 task group 前执行最终 flush。写失败告警但不改变请求结果，dirty 状态保留以供下一轮重试。所有 flush 通过同一 async lock 串行化，避免周期写与 shutdown 写竞态。

### 3.3 学习来源

首个完整版本支持：

1. Anthropic `/count_tokens` 上游精确响应：同一请求先计算本地 estimate，再用精确 `input_tokens` 学习。这是最直接且口径一致的样本。该值与 completion usage 的 `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` 都表示完整 prompt 的真实输入量；若真实上游探针推翻这一等价关系，必须分离 caliber，不能混训。
2. Anthropic completion 成功 usage：当 hook 生命周期能够取得完整 usage 时，由 built-in observer 学习；`real = input_tokens + cache_read_input_tokens + cache_creation_input_tokens`。
3. Token-limit 400：由 built-in observer 从原始上游错误体提取 `current`，补充最高尺寸 buckets。

所有 Anthropic 学习腿必须复用同一个 `estimate_anthropic_input()`，并排除历史 assistant thinking，避免训练与消费 caliber 不一致。

Completion usage 通过 byte-preserving 旁路 tap 提取：非流式响应从将要返回的原始 JSON bytes 解析 usage；流式响应只旁路观察 SSE `message_delta.usage` 与终态。Tap 不得重编码、合并、吞掉或延迟原始 chunks，因此它是只读 observer 数据采集器，不是首版排除的 stream transform hook。

### 3.4 消费与可观测性

- 上游 `/count_tokens` 成功时直接返回精确结果。
- 上游被禁用或失败时，返回 `calibrate(protocol="anthropic", model, estimate)`。
- Gemini 目前只返回 raw local estimate，直到存在 Gemini 真实计数样本后再启用独立 calibration。
- 管理 API 暴露只读 tokenization 状态，包括 factor buckets、样本数与 prompt-limit observations，确保保留能力有实际消费者和诊断入口。

## 4. Prompt limit observations

### 4.1 来源优先级

模型 catalog 的 `capabilities.limits.max_prompt_tokens` 是声明值。错误观测是独立事实，不静默覆盖 catalog：

- `advertised_limit`：catalog 声明。
- `observed_limit`：上游错误体报告。
- `observed_input_tokens`：触发错误的真实输入量。
- `source`：`anthropic_count_tokens_error`、`anthropic_messages_error`、`openai_chat_error` 或其他明确的协议/端点枚举值。
- `observed_at`、`observation_count`。

管理面同时展示两者及差异。未来客户端 setup 可以使用明确策略选择有效窗口，但本阶段不让代理据此修改历史。

### 4.2 解析

至少支持已验证的两种消息：

- `prompt token count of N exceeds the limit of M`
- `prompt is too long: N tokens > M maximum`

解析器同时接受裸文本和 `{ "error": { "message": ... } }`。只处理正整数且 `current > limit` 的样本；无法识别的 400 原样失败，不猜测。

## 5. Anthropic tool pair/orphan 修复

### 5.1 当前版本的问题

当前 Python 算法全局收集所有 IDs，再做集合差：

- 会让后续轮次的同名 ID 错误匹配更早的 result。
- 不验证官方要求的“tool result message 必须紧跟对应 assistant tool use message”。
- 不确保 user content 中所有 `tool_result` 位于文本之前。Anthropic 官方明确要求包含工具结果的 user message 中，所有 `tool_result` blocks 必须位于其他 text blocks 之前。
- 重复 ID 会被 set 折叠，可能留下多个 `tool_use` 对一个 result。

它会同时删除全局未配对的 `tool_use` 与 `tool_result`，并在删除所有 blocks 后移除空消息。

### 5.2 最佳合并算法

协议修复是不可禁用的 mandatory sanitizer，不属于用户 hook。只处理 client tools；`server_tool_use` 与 `*_tool_result` 不进入配对修复，也不获得任何 server-tool 降级、过滤或重试支持。从曾支持 server tools 的版本升级时，客户端历史中的残留 server-tool blocks 可能被上游拒绝；这是有意的 breaking removal。项目只提供清晰错误与 release note，不保留隐式 downgrade sanitizer，否则实质上仍在维护 server-tool support。

按消息局部相邻关系处理：

1. 顺序扫描历史并维护已见 client `tool_use.id`。同一 assistant 消息或跨轮再次出现相同 ID 时，保留全局首次出现的 call pair；后续重复 `tool_use` 及其局部 result 删除并计数。该选择优先保持最旧请求前缀稳定。
2. 只有紧随其后的 user 消息可提供对应 `tool_result`。其他位置的 result 均为 orphan。
3. 在紧随 user 消息中，每个 ID 最多保留一个 result；重复 result 只保留首次出现。
4. 做局部交集：
   - assistant 中没有匹配 result 的 `tool_use` 删除。
   - user 中没有匹配 use 的 `tool_result` 删除。
   - 并行工具调用允许多个 pair，但缺失的 pair 独立删除，不牵连完整 pair。
5. 将保留下来的 `tool_result` 稳定移动到该 user content 数组最前面；其他 text/image/document blocks 保持相对顺序。
6. tool name casing 只修正保留下来的 `tool_use`，依据当前请求的 tool definitions。
7. 若 `tools` 为空或未提供，跳过 name casing 修正。
8. 删除 blocks 后为空的消息移除；混合消息保留其非工具内容。若结果为空或产生其他消息合法性问题，不在本算法中合并角色或合成内容，交给统一 mandatory message-legality pass 显式处理。
9. 算法幂等；第二次运行必须得到完全相同的消息和零新增修复。

这样既满足官方 immediate-follow 与 result-first 约束，又不会让跨轮 IDs 假配对。删除 unmatched `tool_use` 是必要的对称修复：历史请求里的 assistant tool call 若没有紧随的 user result，上游会以 `tool_use ids were found without tool_result blocks immediately after` 拒绝。

### 5.3 去重边界

“相同 name/input/result 但 ID 不同”的完整工具轮次在协议上合法，不由 mandatory pair repair 删除。现有 signature-based `deduplicate_tool_calls()` 不是配对修复，且会删除整条含工具消息；它不得默认启用。若保留，则重写为 block-preserving 的可选 built-in payload hook，默认关闭。

## 6. Hooks 类型系统

不得使用万能 callback。首版定义四类：

1. `PayloadHook`：某一 payload phase 的链式改写。
2. `RetryStrategyFactory`：每请求创建有状态 retry strategy。
3. `ResponseHook`：完整非流式响应变换。
4. `ObserverHook`：只读生命周期观察，不修改请求或响应。

流式逐事件变换不进入首版；keepalive、idle timeout、delayed commit 与 buffered retry 保持 transport 基础设施。

### 6.1 Payload phases

- `pre_sanitize`：typed request 已解析、mandatory sanitizer 之前。
- `post_sanitize`：mandatory sanitizer 之后、wire preparation 之前。
- `pre_send`：resolved wire payload 即将发送前；每个 attempt 运行。重试时输入是 retry strategy 已修改的当前 wire payload，而不是原始 payload；`attempt_number` 从 0 开始递增。

Hook context 是 frozen snapshot，包含 request ID、endpoint、protocol、original/resolved model、session/agent、attempt number 与只读 settings。Hook 间不通过可变 `extra` 暗通状态；需要状态时由明确返回 metadata 或 per-request strategy 承载。

### 6.2 注册与顺序

- `HookRegistryBuilder` 只在 lifespan 启动期可变；`build()` 产出不可变 `HookRegistry` 快照。
- 不可变快照由 `RuntimeState.hook_registry` 持有，并在构造协议 clients 时注入；请求开始后不读取可变 builder。
- 内建 hooks 使用保留命名空间 `builtin:*` 与 `0..999` 固定 order；用户 hooks 不得使用 `builtin:*`，order 必须大于等于 1000。
- 用户在 `hooks.modules` 中声明可信 Python module；module 必须导出 `register(builder, settings)`。
- `hooks.disabled` 可在 builder 阶段按完整 name 排除可选 built-in 或用户 hook；mandatory sanitizer、security floor 与核心基础设施不在此列表中，也不可禁用。
- 显式配置的 module 导入失败、缺少 register 或注册冲突必须阻止启动，不能静默跳过。
- 用户代码与代理进程同权限执行，不提供虚假 sandbox；文档明确只加载可信模块。
- module 列表和注册顺序变更需要重启。当前项目没有完整可靠的 config hot reload，因此不声称支持 hook 热替换。

### 6.3 错误语义

- Payload/Response hook 默认 fail-request。显式注册时可选择 `continue`，但不得隐式吞错。
- Retry strategy 异常终止 retry decision，并把 hook 错误作为内部错误记录，不能伪装成“不匹配”。
- Observer 异常与超时记录 warning 后隔离，不改变请求结果。
- 用户 hook 有独立 timeout；内建同步纯变换不套不必要的超时。
- 所有调用记录 name、type、phase、duration、modified、error。

## 7. Built-in hooks 与核心边界

首版提取的 built-in payload hooks：

- `builtin:strip_read_tool_result_tags`
- `builtin:thinking_destack`
- `builtin:tool_preprocessor`
- 可选、默认关闭的 `builtin:deduplicate_tool_calls`

`builtin:tool_preprocessor` 只处理普通 client tool definitions：按配置注入 `tool_search_tool_regex`、为非白名单工具设置 `defer_loading`，并保持未知字段。它不识别、注入、降级或过滤 Anthropic server tools。

首版 retry factory：

- `builtin:poisoned_thinking`

首版 observers：

- `builtin:token_calibration_success`
- `builtin:token_calibration_failure`
- 后续可迁移 telemetry 与 error persistence，但 HistoryConsumer 保持 guaranteed-delivery 的一等公民。

以下不可 hook 化或不可禁用：

- tool pair/orphan repair、空 block/message legality 等协议 sanitizer。
- 模型解析、认证、header security floor、审批、限流、请求状态机。
- history lifecycle 与 transport/streaming 正确性。

Warmup 保持 route interceptor；它会短路请求并返回合成响应，不伪装成 payload rewrite。

## 8. 删除范围

代码删除：

- `src/app/auto_truncate/`
- `tests/unit/test_auto_truncate.py`
- `src/app/anthropic/token_counting.py`，其有效实现迁移到 `src/app/tokenization/`
- `src/app/anthropic/server_tool_filter.py`
- 对应 server-tool filter tests
- feature negotiation 的原生 server-tool 类别；运行时 API 对未知类别显式报错，避免拼写错误污染缓存

保留：

- client `tool_use`/`tool_result`
- tool search 与 `defer_loading`
- Anthropic/Gemini count-token endpoints
- token estimation、calibration 与 prompt-limit observation

## 9. 验收标准

1. 生产代码和 live docs 不再声明或引用代理侧 auto-truncate 与 server-tool support。
2. 任意 built-in 路径都不会因 prompt 超限删除、压缩或摘要历史。
3. Anthropic 精确 count 成功会训练 calibration；fallback 消费对应 protocol/model factor。
4. Prompt-limit 400 被记录但 payload 不变，错误仍按原状态透传。
5. Tool pair repair 通过 adjacent、parallel、partial、duplicate、reversed、cross-round、result-first、mixed-content 与 idempotence 测试，并保持现有合法 pair/casing 测试行为等价。
6. 用户 hooks 可按确定顺序加载；冲突和启动错误显式失败；Observer 故障被隔离。
7. Ruff、Pyright strict、全量 pytest 与覆盖率门禁通过。
8. 管理 API 按 protocol/model 返回 calibration buckets、样本数、advertised/observed prompt limits 及差异。
