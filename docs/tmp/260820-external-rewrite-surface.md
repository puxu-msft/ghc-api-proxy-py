# 请求/响应改写接入点盘点 —— 「外置改写能力」可以落在哪

**日期**：2026-08-20
**任务**：为「把请求/响应改写能力外置」这一方向盘清事实基础。纯只读调查，未修改任何代码。
**基线**：HEAD `f5c2e9f`，工作树有大量未提交改动（`src/app/server/handler.py`、`src/app/pipeline/delivery/assembler.py`、`src/app/model_provider/github_copilot.py` 等正被并行会话编辑）。**本文的行号取自本次阅读时刻的工作树内容**；`handler.py` 在本次调查过程中就漂移了 5 行，引用时请以符号名为准、行号为辅。
**前置**：根因链路见 [`260820-websearch-400-synthesis.md`](260820-websearch-400-synthesis.md) 与 [`260820-websearch-400-our-side.md`](260820-websearch-400-our-side.md)，本文不重复。

---

## 0. 结论先行

1. **本项目已经有一整套「外置改写」机制，而且是完整实现的**：`src/app/hooks/`（四类 typed 契约 ＋ 启动期不可变 registry ＋ `importlib` 加载用户模块 ＋ 超时 ＋ 记账 ＋ 5 个测试文件）。它**只接在生产不跑的 legacy app 上**（`server/app_factory.py`），新 pipeline 链路完全不引用。
2. **新链路上也已经有一套订阅机制**：`pipeline/events.py` 的 `SubscriberRegistry`（唯一 id ＋ before/after 拓扑排序 ＋ freeze 时定序），驱动在 5 个事件点投递，`attempt.prepare` 的订阅者**可以直接改写 `context.payload` 并被下一步读走**（`direct_driver/base.py:130-133`）。它**默认零订阅者**，且**除测试外没有任何生产代码注册过订阅者**。
3. **用户已经裁决过方向**：`docs/.human-controlled/MAIN.md:62` 要求驱动提供事件订阅点；`docs/.human-controlled-candidates/pipeline-subscriptions.md:5` 记「方向已由用户裁决：**订阅机制吸收 hooks**」。所以「外置」不是新方向，而是一件**已裁决但未执行的迁移**。
4. **响应侧（出站方向）在新链路上没有任何改写接入点**。流式路径上更是明确「首版没有通用逐事件 transform hook」（`docs/2604-rewrite/hooks-system.md:64-66`）。legacy 侧有 `ResponseHook`，但只处理**完整非流式响应 bytes**。
5. 配置面上，`ProxyConfig.hooks` 的六个运维订阅点（`on_client_request_parsed` 等）**只有定义、零消费者**，且**列表项的语义至今未定义**（`docs/.human-controlled-candidates/config-migration-gaps.md:45-49`）。

证据权重：以上五条全部为**强，可据以动手**——都是静态可达性事实，用 `rg` 零命中/唯一命中判定，无分支歧义。

---

## 1. 请求改写接入点全集（新 pipeline 链路，即生产链路）

生产链路 = `cli.py` → `create_pipeline_app` → `pipeline_app._serve` → `server/handler.handle` → `DRIVERS[endpoint]`。按请求经过的时间顺序列出。

### 1.1 入站头过滤（allowlist，硬编码，无配置）

| 项 | 位置 |
|---|---|
| 接入点 | `src/app/server/inbound.py:85` `client_headers=forwarded_client_headers(headers or {})` |
| 实现 | `src/app/pipeline/request_headers.py:17-33`，`FORWARDED_REQUEST_HEADERS = {"anthropic-beta", "anthropic-version"}` |
| 时机 | 建 `RequestContext` 时，早于路由 |
| 能看到 | 客户端原始 headers |
| 配置粒度 | **无**。`allowed` 是函数默认参数，没有任何配置读入它 |

**注意**：`ProxyConfig.hook_strip_anthropic_request_headers`（`config/schema.py:217-221,312`，含 `strip_attribution_header`、`beta_strip_headers`）**零消费者**——`rg` 对这两个字段名在 `src/` 下只命中 schema 定义本身与 legacy `config/settings.py:83`。而 `config.example.yaml:455-490` 里这一节是用户亲笔写的、带实测注释的完整配置（列了 `claude-sonnet-4.6` 的四个会引发 400 的 beta flag）。**这是一个「配置已冻结、实现缺席」的缺口**。

### 1.2 `fix_anthropic_request` —— 目前唯一实际生效的请求体改写钩子

| 项 | 位置 |
|---|---|
| 调用点 | `src/app/server/handler.py:76-77`，条件 `context.inbound_format is WireFormat.ANTHROPIC_MESSAGES` |
| 实现 | `src/app/pipeline/anthropic_request_hook.py:55-91` `fix_anthropic_request(payload, config)` |
| 时机 | **路由之后、翻译之前**。模块 docstring（`:1-10`）写明这是刻意的：`attempt.prepare` 时 payload 已是目标格式、没有 `messages` 可修；这一点对应 spec 的 `on_client_request_parsed` |
| 能看到 | 整个客户端 Anthropic body（含 `tools`、`tool_choice`、`system`、`messages`），**已知路由结果**（`apply_route` 在 `handler.py:70` 之前已执行，`context.resolved_model` / `endpoint` / `target_format` 都可读，但函数签名没把 context 传进来，只传了 `payload` 和 `config`） |
| 就地修改 | 是（`in place`，docstring `:57-60` 说明理由） |

已实现的三条 fixup：

1. `normalize_context_management`（`:36-53`）——`context_management.edits: null` → `[]`。注释记录了 2026-08-18 对真实上游三种拼写的实测。**这是「Claude Code 发上游拒收的东西，我们出站前改写」的既有先例**，与本次 web_search 剥离形状完全相同。
2. 空 thinking 块清理（`:82-85`，`sanitize_empty_thinking`），受 `config.thinking.strip_both_empty_thinking_blocks` 控制。
3. assistant 消息 destack（`:88-89`，`destack_content`），受 `config.thinking.assistant_message_layout` 控制，三档映射在 `:19-33`。

**配置粒度**：`FixAnthropicRequestHook`（`config/schema.py:251-256`）共 5 个字段，**只有 `thinking` 下的两个被消费**。`cache_control`、`extended_cache_ttl`、`context_editing`、`strip_system_reminder_from_Read` 全部零消费者（`rg` 对每个字段名在 `src/` 下只命中 schema 与 legacy `anthropic/features.py`）。`thinking.strip_all_thinking_blocks_on_reject` 也无新链路消费者。

`fix_anthropic_request` 的形态限制：**它是一个写死在 handler 里的函数调用**，没有注册表、没有名字、不能被禁用、不能被排序、不能被第三方追加。要加一条 fixup 就是往这个函数里再写一段。

### 1.3 翻译器 —— 结构性改写，registry 可注册但未开放

| 项 | 位置 |
|---|---|
| 调用点 | `src/app/server/handler.py:79-86`，仅当 `route.translation_required` |
| Registry | `src/app/pipeline/translation_driver/registry.py:52-70`，`register_inbound` / `register_outbound` / `register_response_reader` / `register_response_writer` |
| 构造 | `server/composition.py:220` `translators=default_registry(config.model_translation)` |
| 注入 | `build_chain` **没有 `translators` 参数**，只能用 `default_registry` 的四个内置对。相比之下 `providers` 与 `subscribers` 都是可注入的（`composition.py:183-185`） |

翻译器本身就是改写：`translation_driver/openai_responses.py:406` `payload["tools"] = [_function_tool(tool) for tool in request.tools]`、`translation_driver/anthropic_messages.py:228` `payload["tools"] = request.tools`。两条都是**逐字/半逐字透传**，是 synthesis 文档记录的「已装填未击发」的同类敞口。

### 1.4 `attempt.prepare` 事件 —— **新链路上唯一真正的「可外置」请求改写点**

这就是简报里问的「`composition.py:216` 附近那个默认零 subscriber 的机制」。它不是 `context/consumers.py` 那个 `ContextEventBus`（那是 legacy 的错误持久化总线，新链路不引用），而是驱动自己的事件总线。

**接口**（`src/app/pipeline/events.py`，116 行）：

```python
registry.subscribe(event, subscriber_id, handler, *, before=(), after=())
# handler: Callable[[RequestContext], Awaitable[None]]
registry.freeze() -> FrozenSubscribers[RequestContext]
```

- 唯一 id；重复 id、引用不存在的 id、成环，**都在 `freeze()` 时抛 `SubscriptionError`**（`events.py:47-56,73-93`），即启动期失败，不会到达请求。
- `before` / `after` 拓扑排序，同序并列按注册顺序打破（`events.py:65-99`），结果确定而不只是合法。
- `FrozenSubscribers` 不可变，dispatch 不能重排或追加（`events.py:102-116`）。

**事件点**（`src/app/pipeline/direct_driver/base.py:29-41`）：`attempt.prepare`、`attempt.succeeded`、`attempt.failed`、`request.succeeded`、`request.failed`。

**`attempt.prepare` 是什么阶段、订阅者能否修改 payload —— 能，而且是明写的设计**：

```python
# base.py:130-133
await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)
# Subscribers edit the context payload.
# Re-read it rather than trusting the copy taken when the attempt opened.
attempt.payload = dict(context.payload)
```

即：发布 → 订阅者就地改 `context.payload` → 驱动**重新读取**并作为本次 attempt 的实际出站体。之后 `self._send(context, attempt.payload)` 直达 provider。

`_publish`（`base.py:114-123`）的 docstring 另写明：**订阅者抛异常就是它转向流程的方式**，异常不被吞，交给 `classify()`（`pipeline/exceptions.py`）判 RETRY / ABORT。这对应 `MAIN.md:62,64` 的裁决。

**订阅者在 `attempt.prepare` 能看到什么**：整个 `RequestContext`（`pipeline/request.py:50-97`）——`payload`（**已是目标 wire 格式**）、`resolved_model`、`provider_name`、`endpoint`、`target_format`、`translation_required`、`route_reason`、`client_headers`、`attempts` 历史（含上一次的 `status_code` 与 `error` 字符串）、以及 `extras`（订阅者之间传状态用的自由字典，`request.py:79-80`）。模块 docstring `request.py:1-6` 明写「每个字段都可写是设计意图，用户裁决了不适用所有权或权限规则」。

**关键时机差异**：`attempt.prepare` 在**翻译之后**发布（翻译在 `handler.py:79-86`，驱动在 `:98-101`）。所以：
- Anthropic 直通腿：payload 仍是 Anthropic 形状，`tools[]` 可见；
- Anthropic→Responses 腿：payload 已是 Responses 形状，`tools[]` 也可见（只是形状不同）。

**这意味着：一个挂在 `attempt.prepare` 上的「出站前剥 server tool」订阅者，能同时覆盖两条腿**，而且天然处在重试循环内（每次 attempt 都重跑）。这是本项目现有代码里**最贴合本次需求的接缝**。

**现状**：`server/composition.py:184,221`

```python
subscribers: SubscriberRegistry[RequestContext] | None = None,
...
subscribers=(subscribers or SubscriberRegistry[RequestContext]()).freeze(),
```

参数是**可注入的**，但 `build_chain` 的 5 个生产/工具调用点（`cli.py:139`、`cli.py:161`、`debug/models.py:156`、`tests/integration/recorded/record_cassette.py:58`、`tests/integration/recorded/recorded_provider.py:103`）**没有一个传 `subscribers`**。生产链路上 `attempt.prepare` 永远是空列表。

`rg "\.subscribe\("` 在 `src/` 下对这个 registry **零命中**；唯一使用者是 `tests/unit/test_pipeline_events.py`。

### 1.5 `src/app/hooks/` —— 完整的外置 hook 框架，接在 legacy app 上

这是本次盘点最重要的发现：**「外置」所需要的东西，本项目已经写完了一套，只是接错了地方。**

| 契约 | 定义 | 能改什么 |
|---|---|---|
| `PayloadHook` | `hooks/types.py:47-64` | 出站请求体（`dict -> PayloadHookResult`），分 `pre_sanitize` / `post_sanitize` / `pre_send` 三个 phase（`types.py:12-16`） |
| `RetryStrategyFactory` | `hooks/types.py:67-74` | 每请求造一个有状态 retry strategy（`pipeline/strategies/__init__.py:18-27` 的 `RetryStrategy` Protocol：`can_handle(error)` ＋ `handle(error, payload) -> RetryDecision`，**决策里带改写后的 payload**） |
| `ResponseHook` | `hooks/types.py:77-92` | **完整非流式响应 bytes**（`bytes -> ResponseHookResult`） |
| `ObserverHook` | `hooks/types.py:95-110` | 只读，7 个生命周期事件（`types.py:23-30`） |

配套设施全部就位：

- **Registry**：`hooks/registry.py:26-94`。`builtin:*` 命名空间 ＋ order `0..999`；用户 hook 禁用 `builtin:*` 且 order ≥ 1000（`registry.py:38-49`）；`build()` 后再注册报错；按 `(order, name)` 稳定排序。
- **外置加载器**：`hooks/loader.py:12-24`。`importlib.import_module(module_name)`，要求模块导出 `register(builder, settings)`，否则 `TypeError`。模块名来自 `settings.hooks.modules`（`config/settings.py:144-148`）。**这就是「Python entry-point 式插件」的现成实现**（不走 entry_points，走显式模块名列表）。
- **禁用**：`settings.hooks.disabled` 按全名排除（`registry.py:49`）。
- **超时**：`hooks/executor.py:26-27`，用户 hook 有超时（`settings.hooks.timeout_ms`，默认 5000），内建 hook 不套超时。
- **错误语义**：`HookErrorMode.FAIL_REQUEST` / `CONTINUE`（`types.py:18-20`），执行器在 `executor.py:68-80` 分流，`CONTINUE` 只 log warning。
- **记账**：每次调用记 name / type / phase / duration_ms / modified / error（`executor.py:29-51`），写进 `pipeline/context.py:84` 的 `hook_records`。
- **隔离**：payload hook 拿到的是 `copy.deepcopy(current)`（`executor.py:67`），改坏了不污染上游对象。
- **内建实现**：`hooks/builtin/payload.py`（`strip_read_tool_result_tags`、`thinking_destack`、可选的 `deduplicate_tool_calls`）、`builtin/retry.py`（`poisoned_thinking`）、`builtin/token_calibration.py`（两个 observer）。注册在 `builtin/__init__.py:17-42`。
- **测试**：`tests/unit/test_hooks_registry.py`、`test_hooks_loader.py`、`test_hooks_executor.py`、`test_builtin_hooks.py`、`tests/integration/test_hooks_pipeline.py`。

**接线点**：`src/app/server/app_factory.py:111-127` —— 构建 builder、注册内建、加载用户模块、`build()`、塞进 `runtime.anthropic_client.hooks`。**`server/pipeline_app.py` 与 `server/composition.py` 全文不引用 `app.hooks`**（`rg "app\.hooks" src/app/server/pipeline_app.py src/app/server/composition.py` 零命中）。

**消费点**：`src/app/pipeline/executor.py`（513 行，legacy 执行器）——`:272-275` 跑 `PRE_SEND` payload hooks、`:380-395` 跑 response hooks、`:245-250` 造 retry strategies、多处 `observe`。这个 executor 只被 legacy `anthropic/client.py` 驱动。

### 1.6 审批门 —— 另一条能改 payload 的既有腿（legacy）

`src/app/pipeline/protocol_guard.py:7-25` `apply_approval_guard` 返回 `result.modified_payload or payload`。即**人在环路里可以改请求体**。调用者是 `routes/azure.py:64,94,124` 与 `routes/responses_ws.py:43`，都属 legacy app。新链路无此门。

### 1.7 穷举确认：新链路上没有别的接入点

对新链路做了三组判据性检索：

1. `rg "payload\[|payload\.pop|payload\.setdefault|context\.payload"` 在 `src/app/server/`、`src/app/pipeline/`、`src/app/model_provider/`、`src/app/ghc_client/` 下的全部命中，请求方向只有：`handler.py:77`（fix hook）、`:79-86`（翻译）、`:90` 与 `:132`（覆写 model）、`base.py:133`（读回订阅者的改动）、翻译器内部的构造。
2. **无 ASGI 中间件**：`pipeline_app.py` 只有 `router.add_api_route`。
3. **无 provider 侧改写**：`model_provider/github_copilot.py` 的 `send`（`:132` 起）只做 descriptor 校验与端点分发，不碰 payload。

---

## 2. 响应改写接入点

### 2.1 新链路（生产）：**没有**

- **非流式**：`handler.py:257-273` `response_payload` —— 只在 `translation_required` 时调翻译器，否则 `return body` 原样。没有 hook 点。
- **流式（块级交付链）**：`pipeline_app.py:269-280` → `pipeline/delivery/stream.py:78-164` `stream_delivery`。链路是

  `upstream bytes` → `read_events`（`sse_source.py`） → `assembler.push(event)`（`stream.py:133`，产出 `list[CompletedBlock]`） → `session.offer(block)`（`stream.py:196`，`BlockBuffer` 按 `buffering_policy` 决定何时放行） → `block_frames(...)`（`stream.py:205`，编成 Anthropic SSE） → `yield`

  **全链路没有任何订阅点或注册表**。要插入改写，只能改这三个函数的源码。

  顺带：这里有两个天然接缝，与用户亲笔配置里的两个订阅点一一对应——
  - `stream.py:133` `blocks = assembler.push(event)` 之后 ＝ 「上游 SSE 完整块已准备好」＝ `on_upstream_sse_block_ready`
  - `stream.py:204` `for ready in released:` 之处 ＝ 「发往客户端的完整块已准备好但还没发」＝ `on_client_sse_block_ready`

- **响应头**：`pipeline_app.py` 只对错误路径做 allowlist（`handler.py:236-244` `error_headers`，只放 `retry-after`）。`config.example.yaml:494-511` 里有一整节被注释掉的 `hook_strip_anthropic_response_headers`（blacklist/whitelist 双模式），**schema 里连字段都没有**。

### 2.2 legacy：`ResponseHook`，仅完整非流式 bytes

`hooks/types.py:77-92` ＋ `hooks/executor.py`（`run_response`）＋ `pipeline/executor.py:380-395`。

`docs/2604-rewrite/hooks-system.md:64-66` 明确划界：

> ## Streaming 边界
> 首版没有通用逐事件 transform hook。Anthropic usage 由专用 byte-preserving tap 旁路采样，原 chunks 不重编码、不合并。Keepalive、idle timeout、delayed commit 与 buffered retry 仍属于 transport 基础设施。

**这条是已冻结的 spec 边界，不是遗漏。** 要在流式路径上做外置改写，等于修改这条已裁决的边界——需要用户重新裁决。

**但要注意本项目的交付语义已经变了**：新链路是**块级交付**（一个完整 Anthropic content block 是交付单位），而不是逐事件流式。所以「逐事件 transform hook」这条限制的原始理由（不重编码、不合并 chunks）在新链路上已经不成立——新链路本来就在 `assembler` 里把事件重组成块、再重新编码成 SSE 帧。**「块级 transform hook」与那条冻结边界并不冲突**，这是一个值得向用户提出的区分。证据权重：**倾向性，需用户确认**——我确信新链路确实重编码（`anthropic_sse.py:106-110` 构造 `start_payload`、`assembler.py:156-169` 构造 block payload），但「原 spec 的限制是否因此失效」是解读，不是事实。

---

## 3. 配置面盘点

### 3.1 `ProxyConfig.hooks`（`schema.py:202-214,310`）—— 六个运维订阅点，**零消费者**

```python
class HooksConfig(Section):
    on_client_request_parsed: list[str] = []
    on_upstream_request_ready: list[str] = []
    on_upstream_sse_block_ready: list[str] = []
    on_client_sse_block_ready: list[str] = []
    on_upstream_request_closed: list[str] = []
    on_client_request_closed: list[str] = []
```

判据：`rg "config\.hooks|on_client_request_parsed|..." src/ tests/` 的全部命中只有 schema 定义、两处**注释里的引用**（`handler.py:75`、`anthropic_request_hook.py:6`，都写「这是 spec 的 `on_client_request_parsed` 时刻」）、以及一条断言默认值为空的单测。

来源是用户亲笔的 `docs/.human-controlled/config.example.yaml:436-453`，每个点带一句中文说明。

**未决问题**（`docs/.human-controlled-candidates/config-migration-gaps.md:45-49`）：

> **新**：`hooks` 一节已有六个订阅点，但**列表项指什么没有说明**（模块路径？已注册订阅者的 id？），实现暂按 `list[str]` 建模、无消费者。**单 hook 超时**也没有承载。

**这个未决问题正是「外置形态」这次要回答的东西。** 列表项是模块路径 → entry-point/模块插件形态；是订阅者 id → 声明式启用/排序形态。

### 3.2 六个订阅点与驱动内部事件的对应关系（我的映射，证据权重：强）

| 配置订阅点 | 新链路上对应的真实接缝 | 现状 |
|---|---|---|
| `on_client_request_parsed` | `handler.py:76-77`（`fix_anthropic_request` 调用处，翻译之前） | 已有硬编码函数，无注册表 |
| `on_upstream_request_ready` | `direct_driver/base.py:130` `attempt.prepare` | **订阅机制齐备，零订阅者** |
| `on_upstream_sse_block_ready` | `delivery/stream.py:133` `assembler.push(event)` 之后 | 无接缝 |
| `on_client_sse_block_ready` | `delivery/stream.py:204` `for ready in released:` | 无接缝 |
| `on_upstream_request_closed` | `base.py:164` `request.succeeded` / `:210,213` `request.failed` | 事件已发布，零订阅者 |
| `on_client_request_closed` | `pipeline_app.py:353` `_tracked_delivery` 的 `finally` ／ `_StreamAccounting.finish` | 无接缝（但有既成的收口位置） |

### 3.3 各 `hook_*` 节的接线状态

| 配置节 | 字段 | 默认值 | 消费者 |
|---|---|---|---|
| `hook_strip_anthropic_request_headers` | `strip_attribution_header` | `True` | **无** |
| | `beta_strip_headers` | `{}`（example.yaml 里有实测内容） | **无** |
| `hook_fix_anthropic_request` | `cache_control` | `"passthrough"` | **无** |
| | `extended_cache_ttl` | `enabled=False` | **无** |
| | `context_editing` | `enabled=False` | **无** |
| | `thinking.assistant_message_layout` | `"move_and_synthetic"` | ✅ `anthropic_request_hook.py:70` |
| | `thinking.strip_both_empty_thinking_blocks` | `True` | ✅ `anthropic_request_hook.py:71` |
| | `thinking.strip_all_thinking_blocks_on_reject` | `enabled=True` | **无**（`anthropic/thinking/strip_all.py`＋`quarantine.py` 有既有件，新链未接） |
| | `strip_system_reminder_from_Read` | `False` | **无** |
| `hook_fix_anthropic_sse` | `thinking.content_block_start_compat` | `"signature_delta"` | ✅ `handler.py:335` → `StreamSettings` → `delivery/anthropic_sse.py` |
| | `fix_malformed_unicode_escape` | `True` | **无**（且无任何既有实现） |
| | `rewrite_refusal` | `action="as_end_turn"` | **无** |
| `history` | `enabled` | `True` | **无**（新链路不接 history） |

（本表与 `docs/.human-controlled-candidates/config-schema-gap.md:72-86` 的结论一致，我独立复核了每一项的 `rg` 命中。）

**legacy 侧的 `AppSettings.hooks`**（`config/settings.py:144-148`）是另一套：`modules: list[str]`、`disabled: list[str]`、`timeout_ms: int = 5000`、`deduplicate_tool_calls: bool = False`。**它才是「外置」的现役配置面**，但它属于生产不跑的那套。

---

## 4. 既有设计意图与已裁决事项

### 4.1 用户亲笔（`docs/.human-controlled/`，权威最高）

`docs/.human-controlled/MAIN.md:62`（原文）：

> 为了充分可扩展，每个请求都由一个 RequestContext 描述，驱动应该提供事件订阅点，允许功能模块订阅（传入唯一 id 和可选的“插入到谁之前/后”）。订阅者能够修改公共对象，也可以通过抛出不同的异常来触发中止/重试。

`docs/.human-controlled/MAIN.md:64`（原文）：

> 2026-08-16：这里“不同的异常”分两类，已知异常（如 `UpstreamError`、`UpstreamTimeout`、`UpstreamRateLimit`、`PipelineRetry`、`PipelineAbort`）会按内置逻辑处理；未知异常则总是中止。

`docs/.human-controlled/config.example.yaml:436-453`（原文，节标题为「模块化与钩子 / Modularization & Hooks」）：

> ```yaml
> hooks:
>   # 当客户端请求被解析、已知路由模型后触发。
>   on_client_request_parsed: []
>   # 当发往上游的请求已准备好（但还没发）时触发。
>   on_upstream_request_ready: []
>   # 当上游 SSE 流式响应的完整块已准备好时触发。
>   on_upstream_sse_block_ready: []
>   # 当发往客户端的 SSE 流式响应的完整块已准备好（但还没发）时触发。
>   on_client_sse_block_ready: []
>   # 当上游请求结束时触发。
>   on_upstream_request_closed: []
>   # 当客户端请求结束时触发。
>   on_client_request_closed: []
> ```

**解读**：用户亲笔的这份配置**已经把「外置改写」的接入点位置定死了**——包括**出站方向的两个 SSE 块级订阅点**。这一点很关键：`hooks-system.md:64` 那条「首版没有逐事件 transform hook」的限制，与用户亲笔的 `on_upstream_sse_block_ready` / `on_client_sse_block_ready` 是**同方向的**（块级而非事件级），并不冲突。

### 4.2 已裁决：订阅机制吸收 hooks

`docs/.human-controlled-candidates/pipeline-subscriptions.md:5`：

> 方向已由用户裁决：**订阅机制吸收 hooks**。本文只处理「怎么吸收」，不重开「要不要吸收」。

同文 `:33`：

> 差距原本集中在两点：**有序插入**与**以异常表达控制流**。**两者现在都已建成**……尚未发生的是**吸收**——旧 `src/app/hooks/` 仍与新机制并存，没有一个内置 hook 迁过去。

同文 `:63-67` 列出剩余待用户决定的三点：

1. 「修改公共对象」的写入规则取哪一种（唯一写者 / 后写覆盖 / 其它）；
2. 现有 `HookErrorMode` 的语义是保留还是并入异常体系；
3. `config.example.yaml` 的 `hooks` 六个订阅点，列表项指什么，以及是否需要单 hook 超时。

`docs/.human-controlled-candidates/uncovered-modules.md:18`：

> `hooks/` | 四类 typed 扩展契约、启动期不可变 registry、可信 loader、三个内置实现 | 用户已裁决由事件订阅吸收，见 `pipeline-subscriptions.md`

### 4.3 已冻结的 spec（`docs/2604-rewrite/hooks-tokenization-spec.md`，状态「已实施并通过测试」，2026-07-17）

对本次话题有约束力的条款：

- `:151-157`（§6）**「不得使用万能 callback」**，首版定义四类 typed 契约。这是一条明确的形态裁决：**外置不能是一个通用 `Callable`**。
- `:160-166`（§6.1）三个 payload phase 的定义与 `HookContext` 是 **frozen snapshot**、**hook 间不通过可变 `extra` 暗通状态**。
  ⚠️ **与新链路存在冲突**：`pipeline/request.py:79-80` 的 `extras` 正是「订阅者之间传状态用的可变字典」，而 `request.py:1-6` 说这是用户裁决的。两条规则方向相反，属于 `pipeline-subscriptions.md:63` 那个「写入规则」未决点的一部分。
- `:168-177`（§6.2）注册与顺序：`builtin:*` 保留命名空间、用户 hook order ≥ 1000、**用户模块在 `hooks.modules` 声明并导出 `register(builder, settings)`**、导入失败必须阻止启动、**「用户代码与代理进程同权限执行，不提供虚假 sandbox；文档明确只加载可信模块」**、**「当前项目没有完整可靠的 config hot reload，因此不声称支持 hook 热替换」**。
- `:179-186`（§6.3）错误语义：payload/response hook 默认 fail-request，可显式选 `continue`，**不得隐式吞错**；用户 hook 有独立 timeout；所有调用记 name/type/phase/duration/modified/error。
- `:206-213`（§7）**不可 hook 化或不可禁用的清单**：tool pair/orphan repair 与消息合法性等协议 sanitizer、模型解析、认证、header security floor、审批、限流、请求状态机、history lifecycle、transport/streaming 正确性。
- `:126`（§5.2）**与本次 400 直接相关的冻结条款**：

  > 协议修复是不可禁用的 mandatory sanitizer，不属于用户 hook。只处理 client tools；`server_tool_use` 与 `*_tool_result` 不进入配对修复，也不获得任何 server-tool 降级、过滤或重试支持。……这是有意的 breaking removal。项目只提供清晰错误与 release note，不保留隐式 downgrade sanitizer，否则实质上仍在维护 server-tool support。

- `:224`（§8 删除范围）**「feature negotiation 的原生 server-tool 类别；运行时 API 对未知类别显式报错，避免拼写错误污染缓存」**。

**这最后两条合起来回答了简报里关于 `feature_negotiation.py` 的问题**（见 §4.4）。

### 4.4 `feature_negotiation.py` 是什么，为什么被称为孤儿，缺的两类是刻意删除的

- **是什么**：`src/app/anthropic/feature_negotiation.py`（83 行）——进程内 TTL 缓存，记「上游拒绝过哪些能力值」。API：`learn(category, key, value)` / `is_active(...)` / `pin(...)` / `expire(...)` / `active_values(category, key, configured=...)`。条目带 `first_learned_at` / `last_confirmed_at` / `pinned` / `manually_expired`（`:18-23`）。`_validate`（`:37-39`）对未知类别抛 `ValueError`。
- **被谁用**：**没有人**。`rg "feature_negotiation" --type py src/` 只命中文件自身；唯一引用者是 `tests/unit/test_feature_negotiation.py`。这就是「孤儿模块」的含义。`docs/.human-controlled-candidates/uncovered-modules.md:42` 把它列在「未被 `MAIN.md` 覆盖」的清单里。
- **缺的两类**：`NEGOTIATION_CATEGORIES`（`:5-15`）共 9 类，对比现网 JS 服务少了 `serverTools` 与 `serverToolDowngrade`——**正是处理本次 400 的那两类**。
- **为什么缺**：**这不是遗漏，是冻结 spec 明写的删除项**（`hooks-tokenization-spec.md:224`）。JS 侧的对应实现见 synthesis 文档 §2；本项目在 2026-07-17 主动删掉了这两个类别，并要求运行时对未知类别显式报错。
- **附带事实**：JS 侧的 learned state 是**落盘**的（`<APP_DIR>/negotiation-states.json`，TTL 30 天）；本项目这个 store 是**纯内存**，没有任何持久化代码。

**推论（证据权重：强）**：若外置形态里要做「被拒 → 学习 → 此后提前剥」（synthesis 的方案 C），需要**同时**推翻两条已冻结条款——§8 的类别删除，和 §5.2 的 no-downgrade-sanitizer。这是产品合同层面的变更，必须用户裁决，不能顺手做。

### 4.5 明确没有的东西

`rg -i -e "外置" -e "plugin" -e "可扩展" -e "rewriter"` 扫 `docs/`（排除 archive）——**没有任何文档规划过「把改写外置到进程外」**（子进程、HTTP 回调、sidecar 之类）。已有的全部规划都是**进程内、同权限、可信模块**形态，且 `hooks-tokenization-spec.md:176` 明写「不提供虚假 sandbox」。

---

## 5. 「外置」的候选形态（可行性盘点，不做设计）

以下五种形态互不排斥，可组合。每种给：挂在哪、要改哪些文件、现有代码支持程度。

### 形态 A：把 `src/app/hooks/` 整套接到新链路（「吸收」的最小执行）

- **挂点**：`attempt.prepare`（`base.py:130`）作为 `PRE_SEND`；`handler.py:76` 处新增一个 `pre_sanitize`/`post_sanitize` 等价点。
- **要改**：`server/composition.py`（`Chain` 加 hook registry 字段、`build_chain` 构建它）、`cli.py:139,161`（传进去）、`server/handler.py`（在 `fix_anthropic_request` 前后跑 payload hooks）、`direct_driver/base.py`（在 `attempt.prepare` 里跑 `PRE_SEND`）。`HookContext`（`hooks/context.py`）依赖 legacy `AppSettings`，需换成 `ProxyConfig` 或做适配。
- **已有多少**：契约、registry、loader、executor、超时、记账、错误模式、5 个测试文件——**全部现成**。
- **缺多少**：`HookContext` 的 settings 类型迁移；与 `SubscriberRegistry` 的关系（两套排序机制并存 vs 二选一）；`hooks-tokenization-spec.md:162` 的「frozen snapshot、不通过可变 extra 暗通」与 `request.py:79-80` 的 `extras` 冲突需裁决。
- **与已裁决方向的关系**：用户裁决的是「**订阅机制吸收 hooks**」，不是「把 hooks 原样搬过来」。所以 A 是**逆着裁决方向**的捷径。若采纳需重新裁决。

### 形态 B：`SubscriberRegistry` ＋ 内置订阅者（顺着已裁决方向）

- **挂点**：`attempt.prepare` 等 5 个既有事件；按需在 `handler.py`、`delivery/stream.py`、`pipeline_app.py` 的收口处**新增**事件发布点，对齐 `config.example.yaml` 的六个名字。
- **要改**：`server/composition.py:221`（改成构建一个非空 registry）、`cli.py`（或 composition 内部）注册内置订阅者、新建订阅者模块。若要覆盖 SSE 两个块级点，还要给 `stream_delivery` 传入 subscribers 并在 `stream.py:133,204` 发布——**注意 `stream_delivery` 是同步生成器风格的 async generator，订阅者 handler 是 `async`，可以 await，但会引入每块一次的调度开销**。
- **已有多少**：id/before/after/拓扑排序/freeze 期校验/不可变快照/异常转向控制流——**全部现成且有单测**；`attempt.prepare` 的 payload 改写语义已明写在 `base.py:131-133`。
- **缺多少**：SSE 两个块级事件点（要新写发布代码，且 `FrozenSubscribers[RequestContext]` 的泛型参数对块级事件不合适——块级订阅者要看的是 `CompletedBlock`，需要第二个 registry 或换载荷类型）；`on_client_request_closed` 的收口点；订阅者的错误模式（现在只有「抛异常 = 转向」，没有 `CONTINUE` 语义）；单订阅者超时；调用记账。
- **对本次 400 的适配度**：**最高**。一个订阅在 `attempt.prepare` 的 `strip_server_tools` 订阅者，两条腿都覆盖、在重试循环内、可被日志观察、可被 before/after 定序。

### 形态 C：配置声明式规则（无代码扩展）

即让 `hooks.on_upstream_request_ready: ["strip_server_tools"]` 这类列表项指**已注册的内置订阅者 id**，操作员只做启用/停用/排序。

- **挂点**：同 B。
- **要改**：`schema.py` 的 `HooksConfig` 保持不变（列表项语义定为「订阅者 id」）；`composition.build_chain` 按配置从一张内置订阅者表里挑选并注册。
- **已有多少**：配置字段已冻结（用户亲笔）；`SubscriberRegistry.subscribe` 的 id 参数天然对应。
- **缺多少**：内置订阅者表本身；「配置里写了不存在的 id」的启动期报错；顺序表达（配置列表顺序 vs `before`/`after`，两者语义如何合并）。
- **优点**：完全不引入外部代码执行，不触碰 `hooks-tokenization-spec.md:176` 的「同权限、无 sandbox」问题。**这是把 `config-migration-gaps.md:45-49` 那个未决问题往「订阅者 id」方向解的形态。**

### 形态 D：Python 模块插件（`hooks.modules` 式）

- **挂点**：同 B/C，只是订阅者来自 `importlib` 加载的第三方模块。
- **要改**：把 `hooks/loader.py:12-24` 移植/复用到新链路（改成 `register(registry, config)`）；`ProxyConfig` 加 `hooks.modules` 与 `hooks.disabled`（**目前新 schema 里没有这两个字段**，只有 legacy `settings.py:144-148` 有）。
- **已有多少**：loader 实现现成（12 行）；命名空间与 order 规则现成（`registry.py:38-49`）；「导入失败必须阻止启动」的裁决现成（spec §6.2）。
- **缺多少**：新 schema 的字段；与 `SubscriberRegistry` 的 order 规则对齐（现在是 before/after，不是数字 order）；单模块超时。
- **风险与既有裁决**：spec §6.2 已明写「同权限执行、不提供虚假 sandbox、只加载可信模块、不支持热替换」。**这些是已裁决的，不需要重新讨论，但需要在新链路的文档里重述**。

### 形态 E：进程外改写（子进程 / HTTP 回调 / sidecar）

- **挂点**：理论上同 B，订阅者内部去调外部进程。
- **要改**：全新。
- **已有多少**：**零**。`docs/` 全库对「外置到进程外」零规划。
- **缺多少**：几乎全部——序列化契约、超时与熔断、失败语义（fail-open 还是 fail-closed）、并发模型、以及最要命的**每请求一次跨进程往返的延迟**（本项目 `client_request_deadline` 默认 3600s，但块级交付链上每块一次的话开销不可忽略）。
- **判断**：**与项目现状距离最远，且与「不得使用万能 callback」的 typed 契约取向相悖**。除非用户的「外置」本意就是「不用改 Python 代码就能改写」，否则 C 或 D 已经能满足。

### 五种形态与「本次 web_search 400」的匹配度

| 形态 | 能否解决本次 400 | 需要新裁决 |
|---|---|---|
| A | 能 | 是（逆着已裁决方向） |
| **B** | **能，且改动最小** | 否（顺着 `MAIN.md:62` 与 pipeline-subscriptions 的裁决） |
| C | 能（B 的配置化外壳） | 需定义列表项语义（本就是未决点 3） |
| D | 能，且第三方可自行补 | 需给新 schema 加字段 |
| E | 能，但性价比最低 | 是（全新方向） |

**我的偏好**：**B 打底 + C 作为配置面**。理由：B 的全部基础设施已建成且有单测，C 正好把 `config-migration-gaps.md` 那个悬置的未决问题落地成一个具体答案，两者都不触碰任何已冻结条款。D 可以作为后续增量（加两个 schema 字段 + 复用现成 loader），E 不建议。证据权重：**强，可据以动手**——B 的可行性由 `base.py:130-133` 的既有语义与 `composition.py:184` 的既有注入参数直接支撑，不是推测。

---

## 6. 需要用户裁决的点（本次盘点新暴露的，不含 pipeline-subscriptions.md 已列的三条）

1. **本次 400 的剥离逻辑，是「先外置机制、再把它作为第一个订阅者」，还是「先硬修 `fix_anthropic_request`、外置另开一刀」？** 前者更整齐但会把一条生产故障的修复时间绑在一次架构迁移上；后者能立刻恢复可用，但会在 `anthropic_request_hook.py` 里留下一段将来要搬走的代码。
2. **`hooks-tokenization-spec.md:126` 的 no-downgrade-sanitizer 条款，是否适用于「剥离 `tools[]` 声明」？** 该条禁止的是「隐式 downgrade sanitizer」（把 server tool 块降级），剥离声明是否属于同一类，文本没有直接回答。这条已在 synthesis §4 提出，本文只是确认它同样约束「外置」形态——**外置本身不能绕过一条产品合同**。
3. **响应/流式方向要不要一并外置？** 用户亲笔配置里有两个 SSE 块级订阅点，而冻结 spec 说首版没有逐事件 transform hook。§2.2 论证了两者其实不冲突（块级 ≠ 事件级），但这是我的解读，需要用户确认。
4. **`hook_strip_anthropic_request_headers` 的实现缺席**：用户亲笔配置里有实测过的 `beta_strip_headers`（列了 `claude-sonnet-4.6` 的四个会引发 400 的 beta flag），schema 里有字段，**代码里没有消费者**。这是一个和本次 400 同族的「配置已定、行为缺席」缺口，且它同样是一个「上游拒收 → 出站前剥」的改写。若外置机制要建，它是一个天然的第二个订阅者。
