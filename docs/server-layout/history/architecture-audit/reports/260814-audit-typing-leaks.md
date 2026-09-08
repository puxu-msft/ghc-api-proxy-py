# 类型化程度与抽象泄漏体检

> 最终报告：截至 HEAD `44471c6ceedd8a06a7e0cca480314f8fc205e7c0` 的已核验证据。扫描期间未修改 `src/`、`tests/` 或其他既有文件。

## 1. 结论摘要

- 结论：严格 Pyright 通过并不代表内部协议载体被类型化。`uv run pyright src tests` 在该 HEAD 输出 `0 errors, 0 warnings, 0 informations`，但同一主路径仍把 Anthropic request wire 作为 `dict[str, Any]` 在 hook、approval、retry、prepare、protocol conversion 与 history 之间传递。
- `src/app/` 的 AST 基线为 159 个 Python 文件、17,840 个逻辑行；其 `Any` 注解名出现 263 次、`cast(...)` 调用 162 次、忽略注释 1 次。每项均已按本报告“量化基线表”所列第二种语法方法复核。
- 当前最明确的内部所有权泄漏是 `RequestContext.original_payload`：它由 pipeline 创建，交给 approval 和 hooks，随后又作为可写 wire payload 进入 retry／上游；类型不表达“哪一阶段可改、重试是否 fork、approval 何时冻结”。
- `ApprovalResult`、`RetryDecision`、`RenderedBatch`、`ResponsesAnthropicStreamState`、`GenerationRecord` 都把互斥状态编码成 bool／Optional 字段组合；构造者可以制造非法组合，正确性主要依赖运行时 if／验证器。
- 合理边界逃逸已确认存在：JSON 解码后的未知上游／插件输入应先以 `object`／`Mapping[str, JsonValue]` 表示并经字段验证；`wire_json.dumps` 的单点 `cast(Any, value)` 位于先验递归验证之后，不能与内部 DTO 泄漏等同。

## 2. 量化基线表

| 指标 | 值 | 取值命令 | 交叉验证方法与结果 |
|---|---:|---|---|
| 审计 HEAD | `44471c6ceedd8a06a7e0cca480314f8fc205e7c0` | `git rev-parse HEAD` | 用户提供的固定 HEAD 与命令结果一致。 |
| `src/app/` Python 文件 | 159 | 内联 Python `Path(.../src/app).rglob('*.py')` | `rg --files src/app -g '*.py' \| wc -l` 为 159。 |
| `src/app/` 逻辑行 | 17,840 | 内联 Python `sum(len(read_text().splitlines()))` | `wc -l` 为 17,723 个换行字节；差值 117 恰为无末尾换行的文件数，故不是文件集合差异。 |
| `Any` 在注解 AST 中的 Name 出现数 | 263 | 内联 Python AST：遍历 `AnnAssign`、函数参数与返回注解，再数 `ast.Name(id='Any')` | AST 注解坐标范围内的 Python `tokenize` NAME `Any` 数也是 263。 |
| `cast(...)` 调用 | 162 | 内联 Python AST：`Call` 的 callee 为 `cast` 或 `.cast` | Python `tokenize` 中 NAME `cast` 紧邻 `(` 的调用形态数也是 162。 |
| `# type: ignore`／`# pyright: ignore` | 1 | `ast.Module.type_ignores` | Python `tokenize` COMMENT 搜索相同两种指令为 1；位置为 `src/app/server_adapter.py:174`。 |
| 参数化 `dict[...]` 注解槽位 | 230 | 内联 Python AST：参数、返回、变量注解的外层为 `dict`／`Dict` Subscript | 待最终逐位置分类时以 AST source span 复核；不将 `rg` 文本命中作为计数依据。 |
| Pyright | 0 errors／0 warnings／0 informations | `uv run pyright src tests` | 该结论仅覆盖配置包含的 `src`、`tests` 与该 HEAD，不证明协议状态建模无泄漏。 |

## 3. 发现表

| 位置(file:line) | 泄漏类型 | 证据 | 严重度 | 建议的目标类型／处置 |
|---|---|---|---|---|
| `src/app/pipeline/context.py:70-91` | 内部事实载体是可变 `dict[str, Any]` | `original_payload`、`hook_records`、`final_response_payload` 与 `RequestState`、`error` 混放在一个公共可变 context。创建者为 `execute_anthropic_pipeline`（`src/app/pipeline/executor.py:204-210`）；approval 读取同一对象（`pipeline/approval.py:62-75`），hooks 获得并返回其字典版本（`pipeline/executor.py:154-193`、`hooks/executor.py:53-91`），retry 在每次 attempt 改写 payload（`pipeline/executor.py:259-325`）。没有类型表示 original／approved／prepared-attempt 的 fork 边界。 | major | 将 request 生命周期事实拆成不可变 `OriginalMessagesRequest`／`PreparedAnthropicWire`／`AttemptPayload` 值对象；将 hook history 改为具名 `HookRecord`。明确 hook 得到 deep-copy 的可变 plugin boundary，retry 只能以新 `AttemptPayload` 产生下一 attempt。 |
| `src/app/pipeline/approval.py:13-30, 133-146` | discriminant 与 Optional 不对应 | `ApprovalResult.status` 可为 `approved_with_modifications` 而 `modified_payload=None`，也可为 `approved`／`rejected` 但携带 payload；`reason=""` 混淆“无理由”和空理由。`modify_and_approve` 用顶层 `{**approval.payload, **modifications}` 合并未类型化 wire。 | major | 改为 `Approved`、`Rejected(reason: str)`、`ApprovedWithModifications(payload: ApprovedMessagesRequest)` 的 discriminated union；管理 API 输入先验证为显式 patch model，随后重新验证完整 `MessagesRequest`。 |
| `src/app/pipeline/strategies/__init__.py:10-15, 40-60, 104-120` | retry 决策的非法 bool 组合与 wire 泄漏 | `RetryDecision(should_retry=False, payload=..., modifications=..., owner=...)` 可构造却无语义；`PoisonedThinkingStrategy` 从宽 `dict[str, object]` 再 `cast(list[dict[str, Any]], ...)` 后改写 messages。coordinator 是 retry 预算 owner，strategy 是 payload transform owner；成功后仅通知，不存在显式 immutable input／fork contract。 | major | `Retry = dataclass(payload: AttemptPayload, modifications: tuple[str, ...], owner: StrategyName)` 与 `DoNotRetry` union；策略输入／输出使用 `AttemptPayload`，将 thinking messages 建成 typed block union 或在单一 parser boundary 证实并封装。 |
| `src/app/delivery/responses_anthropic_stream.py:64-99, 100-156` | streaming state 由 Optional＋bool 拼装且投影回无类型 wire | `usage_estimated=True` 与 `usage=None`、`stop_reason` 未终态、`message_id`／`frontier` 不一致等均可构造。stream renderer 写 state，route 在 `routes/anthropic.py:51-127` 再用多个空值判断完成、usage 与 history；`_committed_response: dict[str, Any]` 允许投影后被 history route 二次改写。 | major | 用 `StreamPending`／`StreamDeliveredSuccess(terminal: ...)`／`StreamFailed(error, frontier_projection)` union，完成投影返回 immutable typed `AnthropicHistoryResponse` 或 `MappingProxyType`，由唯一 owner 负责转为 wire。 |
| `src/app/rolling_state.py:16-29, 146-215` | generation 生命周期的 role／phase／ready／accepting／pid 是可任意组合的标量 | 例如 `GenerationRecord(role="committed", phase="reserved", ready=False, accepting=True, pid=0)` 可在类型层构造，只有 store 读写时 `_validate_generation_record` 拒绝。owner 为 `RollingStateStore` 的持久状态；`RollingController` 直接替换记录（`rolling_controller.py:90-101, 139-143, 199-207, 223-252`），不存在类型级 transition API。 | major | `CandidateGeneration`／`CommittedGeneration`／`DrainingGeneration`／`TerminalGeneration` discriminated union，phase 用 role-specific Literal；仅暴露 `advance_*`／`mark_failed` 工厂，持久化在 `TypeAdapter` 单点解码。 |

| `src/app/models/anthropic.py:12-24, 27-61, 82-88`；同形态见 `models/openai.py:10-80`、`models/gemini.py:15-70` | protocol sum types 被“`type: str`＋一组 Optional／`dict[str, Any]`”替代 | `ContentBlock(type="text", input={...})`、`ContentBlock(type="tool_use", text="x")` 等在模型层可构造；`MessagesRequest.thinking`、`tool_choice`、`metadata` 及三个协议模型的多态 payload 均只在下游 converter 的 if 分支中重新解释。模型 owner 是 FastAPI/Pydantic 入站解析，但同一模型随后是 sanitizer、hook、converter 的内部 carrier。 | major | 保留 `extra="allow"` 的外层 ingress model，但在 sanitize 后投影为封闭的 canonical discriminated union，例如 `TextBlock`／`ToolUseBlock`／`ToolResultBlock`／`ThinkingBlock`；将 JSON schema、metadata 等真正开放字段标为 `JsonObject`（递归 `JsonValue`），不使用 `Any`。 |
| `src/app/history/types.py:12-25`、`history/consumer.py:26-48, 55-173`、`routes/anthropic.py:102-117` | 持久化 projection 是可变 `dict[str, Any]`，写者不唯一 | `HistoryEntry.request_payload`／`response`／`usage` 由 `HistoryConsumer` owner 建立；stream route 在取到 `responses_state.committed_response` 后原地写入 `usage`、`usage_facts`、`error`，然后交给 history。reset 为新的 `HistoryEntry`，但没有 immutable snapshot 或 projection schema。 | major | 用 frozen `HistoryRequestSnapshot`、`HistoryResponseSnapshot`、`UsageSummary` 和 `StreamFailureProjection`；在 route 完成最后投影后一次性构造 history entry，history consumer 只接收不可变对象。 |
| `src/app/pipeline/context.py:74-89` | 同一“尚未产生”概念混用 `None`、`""`、空 tuple 与 state enum | `resolved_model`、`protocol_leg`、`route_reason` 以 `""` 表示 pending，`sanitization`／`response_usage` 用 `None`，`conversion_facts` 用 `()`；history 又以 `resolved_model or original_model` 掩盖漏设（`history/consumer.py:65-70`）。构造默认值使不完整 context 可被传递。 | major | 按 phase 分离 `ReceivedContext`、`PreparedContext`、`CompletedContext`、`FailedContext`，或至少改为 `None` 加显式 `require_prepared()`；移除空字符串默认值，使遗漏在构造或 transition 时失败。 |
| `src/app/delivery/anthropic_sse.py:122-129, 335-395` | batch kind 与 Optional 字段的非法组合 | `RenderedBatch(kind="terminal", block_index=0, order_key=...)`、`RenderedBatch(kind="block", block_index=None)` 均能构造；`DeliveryFrontier` 只在接收时以 `if batch.kind...` 拒绝。renderer 是 batch owner，`DeliverySession` 是 commit／reset owner，batch 跨此二者传递。 | major | 定义 `BlockBatch(kind: Literal["block"], block_index: int, order_key: BlockOrderKey, ...)`、`TerminalBatch`、`ErrorBatch` union；`DeliveryFrontier` 接受相应窄类型，消除运行时“kind 再检查字段”模式。 |
| `src/app/pipeline/context.py:22-33`；`errors.py:13`；`observability/logging.py:10`；`protocols/anthropic_responses.py:43-50`；`transform/model_resolver.py:4` | 模块级可变容器作为常量 | AST 找到 5 个非 `__all__` 模块级 list/dict/set，未发现 class-level mutable literal default。静态消费者搜索只读这些对象，未找到项目内 mutation；但 `ALLOWED_TRANSITIONS` 的 value 是可变 `set`，其余 dict 也可被任意 importer 改写。 | minor | 对真正常量改为 `MappingProxyType`／`Mapping[..., frozenset[...]]`／tuple；不需要增加锁，因为当前证据没有并发写者。 |

## 4. 合理的逃逸口

- `src/app/wire_json.py:9-11, 51-60`：递归 `JsonValue` 是 wire JSON 的正确边界类型；`dumps` 在 `_validate_wire_value` 已检查 JSON 值、字符串 key、非有限数和整数范围之后才对 `orjson.dumps` 使用单点 `cast(Any, value)`（第 54 行）。这是第三方无泛型 encoder 签名的受控逃逸，保留并用注释说明前置不变量即可。
- `src/app/openai/responses_stream_parser.py:173-223, 973-1027`：SSE JSON event 的未知字段与不同 event kind 在入站时确实不能预先假定 schema；以 `dict[str, Any]` 接收、逐字段 `isinstance` 验证，并输出 `ResponsesSemanticEvent` discriminated union 是合理边界设计。后续审计将检查它是否有未经验证的逃逸回内部。
- `src/app/protocols/responses_anthropic.py:72-140`：完整 Responses JSON 在 converter ingress 使用 `Mapping[str, Any]`，但逐字段检查并输出 `ConvertedResponse`、Pydantic `MessagesResponse` 和 fact records；该函数的入参宽度本身是适当的协议边界，不建议将 upstream 未知扩展字段伪装为封闭 dataclass。
- `src/app/pipeline/route_policy.py:40-50`：`TransportAvailability` 的三个 bool 是独立物理 transport capabilities，不是互斥 action；例如 Responses HTTP 与 WebSocket 可同时可用、两个协议 leg 也可同时可用。因此不应为消除 bool 数量而错误改成 union。
- `src/app/openai/responses_stream_parser.py:86-140, 149-171`：私有 draft 的 Optional／bool 由单一 parser instance 持有、不会跨模块公开，且终态输出是 `ResponsesSemanticEvent` union。这是封装内部的有界状态机，不列为抽象泄漏；重构时应避免将这些 draft 暴露给 delivery。
- `src/app/server_adapter.py:174-190`：唯一 `# type: ignore[no-untyped-def]` 包住 uvicorn 的私有 protocol factory。相邻代码以 `_UvicornProtocolFactory` cast 收窄返回值；在上游没有公开 typed hook 前，这是受限的第三方适配逃逸，保留并标注依赖版本／私有 API 风险。
- `src/app/config/loader.py:36-57, 81-101`：YAML／环境／CLI layer 合并必然接收开放配置；最终 `AppSettings.model_validate` 是适当的收敛点。不要把该 ingress 改为虚假的封闭 dict。

## 5. 扫描范围与判据

- 已扫描路径：`/home/xp/src/ghc-api-proxy-py/src/app/**/*.py`。明确未读取禁止的 `docs/agents/anthropic-responses-bridge/architecture.md` 与 `implementation.md`。
- 语法计数以 Python 3.14 `ast` 为主；`# ... ignore` 因不在 AST 语义树中，使用 `ast.Module.type_ignores` 与 `tokenize` comment token 的独立复核。`rg` 仅用于定位调用接缝，不用于任何报告计数。
- 判为问题须同时满足：值越过一个内部模块／生命周期边界；其结构、owner、可写性或 reset／fork 语义会影响后续行为；现有类型无法排除已知不合法状态。纯 ingress／egress JSON、第三方 SDK 和有验证的 decode boundary 单列为合理逃逸。

## 6. 未覆盖面

- 已完成：下方完整位置清单覆盖 263 个 `Any`、162 个 `cast` 与唯一 ignore；AST 已检查参数／属性默认值、模块级 mutable 和 class-level mutable literal default。
- 未覆盖：未对运行时生成的 `Any`、第三方库 stub 的精确性、`tests/` 自身的类型设计或动态插件的外部实现逐一审计。
- out-of-axis：发现 `RollingStateStore`／`RollingController` 同时承担状态验证与状态迁移，属于职责边界／模块划分问题；本报告未沿该轴展开。未对重复实现、生命周期功能正确性、测试完备性、第三方库选型或依赖环作结论。


### 完整 `Any`／`cast`／ignore 位置清单

下表逐位置覆盖 AST 统计中的 263 个 `Any` 注解 Name、162 个 `cast(...)` 调用和 1 个 ignore；“合理”只表示该位置位于未经信任的 JSON／第三方边界且有相邻验证，不表示其返回值可继续以 `Any` 穿越内部模块。`Any` 的同一行多次出现会按次数列出。

| 文件 | `Any` 注解行 | `cast` 调用行 | ignore 行 | 逐位置归类 |
|---|---|---|---|---|
| `src/app/anthropic/client.py` | 46, 56, 72, 118 | 261, 284, 435, 438 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/message_tools.py` | 7, 11 | — | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/request_preparation.py` | 13, 18 | 30, 34, 39, 69 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/response_validation.py` | — | 16, 26, 32 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/sanitize/deduplicate_tool_calls.py` | 8, 10, 12, 36 | 17, 20, 29, 32, 49, 50 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/sanitize/read_tool_result_tags.py` | 7, 7 | — | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/thinking/destack.py` | 11, 15, 23, 25, 29 | — | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/thinking/protection.py` | 21, 28, 35, 37, 40 | 18, 24 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/thinking/reasoning_carrier.py` | — | 113 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/thinking/responses_reasoning.py` | — | 57, 60, 65 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/thinking/signature_compat.py` | 4, 4 | 10 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/thinking/strip_all.py` | 10, 11, 18 | 19, 23 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/anthropic/warmup.py` | 6, 30, 32 | 10, 13, 20, 23 | — | F1：request preparation wire 在内部继续流动，需 stage type。 |
| `src/app/auth/copilot.py` | 21, 99, 117 | — | — | 配置／HTTP 边界：保留宽输入，Pydantic 验证前不得进入内部事实。 |
| `src/app/auth/device_flow.py` | 39, 75 | — | — | 配置／HTTP 边界：保留宽输入，Pydantic 验证前不得进入内部事实。 |
| `src/app/auth/github.py` | 34, 40, 43, 51 | — | — | 配置／HTTP 边界：保留宽输入，Pydantic 验证前不得进入内部事实。 |
| `src/app/config/compat.py` | 8, 28, 28 | 34, 42 | — | 配置／HTTP 边界：保留宽输入，Pydantic 验证前不得进入内部事实。 |
| `src/app/config/loader.py` | 37, 38, 40, 84, 89 | 51, 52 | — | 配置／HTTP 边界：保留宽输入，Pydantic 验证前不得进入内部事实。 |
| `src/app/context/consumers.py` | 11, 26 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/context/error_persistence.py` | 18 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/delivery/anthropic_sse.py` | 461, 1017 | 515 | — | F4：delivery state 或 wire projection，按 batch kind／terminal 分型。 |
| `src/app/delivery/responses_anthropic_stream.py` | 74, 92, 100, 108, 111, 141, 405, 426, 445, 448, 459, 472, 482 | 148, 218, 238, 285, 408, 422, 427, 455 | — | F4：delivery state 或 wire projection，按 batch kind／terminal 分型。 |
| `src/app/generation_control.py` | 120 | 123 | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/generation_control_client.py` | — | 102, 103, 109, 112, 129, 132, 165, 200, 203, 221, 222, 223, 226, 227 | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/history/consumer.py` | 30, 74, 126, 127, 156 | — | — | 持久化 projection：以 JsonObject/History DTO 替代 Any。 |
| `src/app/history/sqlite/writer.py` | 213 | — | — | 持久化 projection：以 JsonObject/History DTO 替代 Any。 |
| `src/app/history/types.py` | 21, 22, 23 | — | — | 持久化 projection：以 JsonObject/History DTO 替代 Any。 |
| `src/app/history/ws.py` | 25 | — | — | 持久化 projection：以 JsonObject/History DTO 替代 Any。 |
| `src/app/hooks/builtin/payload.py` | 21, 58, 90, 107 | 27, 32, 36, 64, 69, 95, 108, 111, 116, 120, 147, 150 | — | 插件边界：允许开放 JSON，仍应用 JsonValue alias 与 immutable stage wrapper。 |
| `src/app/hooks/builtin/token_calibration.py` | 14, 14, 30, 46, 79 | 17, 27 | — | 插件边界：允许开放 JSON，仍应用 JsonValue alias 与 immutable stage wrapper。 |
| `src/app/hooks/executor.py` | 31, 56, 59, 60, 99, 139, 141 | — | — | 插件边界：允许开放 JSON，仍应用 JsonValue alias 与 immutable stage wrapper。 |
| `src/app/hooks/loader.py` | — | 22 | — | 插件边界：允许开放 JSON，仍应用 JsonValue alias 与 immutable stage wrapper。 |
| `src/app/hooks/registry.py` | — | 81 | — | 插件边界：允许开放 JSON，仍应用 JsonValue alias 与 immutable stage wrapper。 |
| `src/app/hooks/types.py` | 35, 62, 109 | — | — | 插件边界：允许开放 JSON，仍应用 JsonValue alias 与 immutable stage wrapper。 |
| `src/app/models/anthropic.py` | 17, 23, 24, 35, 41, 43, 58, 59, 60, 61, 87, 88 | — | — | F6：稀疏 wire model，需 discriminated union。 |
| `src/app/models/gemini.py` | 17, 18, 19, 27, 58 | — | — | F6：稀疏 wire model，需 discriminated union。 |
| `src/app/models/openai.py` | 13, 45, 46, 47, 54, 70, 71 | — | — | F6：稀疏 wire model，需 discriminated union。 |
| `src/app/observability/logging.py` | 118, 119 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/openai/client.py` | 16, 23, 28, 39 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/openai/responses_conversion.py` | — | 12, 23 | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/openai/responses_stream_accumulator.py` | 8, 9, 11, 21 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/openai/responses_stream_parser.py` | 173, 226, 283, 332, 348, 380, 391, 413, 427, 441, 454, 472, 535, 557, 570, 619, 677, 767, 802, 814, 900, 916, 929, 950, 974, 975, 988, 1004 | 474, 484, 522, 700, 711, 826, 833, 904, 983 | — | 合理：上游 SSE decoder，验证后输出 typed facts。 |
| `src/app/openai/responses_ws.py` | 23, 33, 34, 42 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/openai/sanitize.py` | 6, 7, 22 | 11, 13, 30, 32 | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/openai/stream_accumulator.py` | 11, 13, 26 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/pipeline/approval.py` | 17, 24, 32, 136, 148, 152 | — | — | F1-F3：内部 request／approval／retry state，需封装。 |
| `src/app/pipeline/context.py` | 72, 84, 86 | — | — | F1-F3：内部 request／approval／retry state，需封装。 |
| `src/app/pipeline/executor.py` | 67 | 264, 271 | — | F1-F3：内部 request／approval／retry state，需封装。 |
| `src/app/pipeline/protocol_guard.py` | 8, 13 | — | — | F1-F3：内部 request／approval／retry state，需封装。 |
| `src/app/pipeline/strategies/__init__.py` | — | 114 | — | F1-F3：内部 request／approval／retry state，需封装。 |
| `src/app/protocols/anthropic_responses.py` | 635, 669 | 397, 532 | — | 边界：解码时可宽；内部输出改 JsonValue/具名 DTO。 |
| `src/app/protocols/azure.py` | 8, 9, 13 | — | — | 边界：解码时可宽；内部输出改 JsonValue/具名 DTO。 |
| `src/app/protocols/gemini.py` | 20, 29, 30, 50, 64, 91, 91, 126, 126 | 96, 97, 100, 127 | — | 边界：解码时可宽；内部输出改 JsonValue/具名 DTO。 |
| `src/app/protocols/responses_anthropic.py` | 73, 153, 178, 295, 307, 318, 325 | 93, 157, 203, 328 | — | 边界：解码时可宽；内部输出改 JsonValue/具名 DTO。 |
| `src/app/rolling_runtime.py` | — | 71 | — | F5：rolling persistent/control state，需 role／phase 分型。 |
| `src/app/rolling_state.py` | 218 | 83, 90, 97, 98, 99, 100, 101, 239, 243 | — | F5：rolling persistent/control state，需 role／phase 分型。 |
| `src/app/routes/anthropic.py` | 131, 296 | — | — | HTTP boundary；approval route 另见 F2，其他出站 wire 用 JsonObject。 |
| `src/app/routes/approval.py` | 11, 16, 32, 41 | — | — | HTTP boundary；approval route 另见 F2，其他出站 wire 用 JsonObject。 |
| `src/app/routes/azure.py` | 58, 88, 118 | — | — | HTTP boundary；approval route 另见 F2，其他出站 wire 用 JsonObject。 |
| `src/app/routes/gemini.py` | 46, 84, 104 | 36, 40, 44, 50, 57, 61 | — | HTTP boundary；approval route 另见 F2，其他出站 wire 用 JsonObject。 |
| `src/app/routes/management.py` | 12, 20 | — | — | HTTP boundary；approval route 另见 F2，其他出站 wire 用 JsonObject。 |
| `src/app/routes/protocol_history.py` | 15 | — | — | HTTP boundary；approval route 另见 F2，其他出站 wire 用 JsonObject。 |
| `src/app/server_adapter.py` | 35, 177 | 178, 276, 278 | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/streaming/anthropic_usage.py` | — | 31, 36, 39 | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/streaming/sse.py` | 121 | — | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/streaming/translator.py` | 5, 5 | 9 | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/tokenization/calibration.py` | 109, 122 | 130, 138, 146 | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/tokenization/estimators.py` | 99 | — | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/tokenization/limits.py` | 92, 101 | 23, 26, 109 | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/tokenization/service.py` | 17, 41, 50 | — | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/tokenization/snapshot_store.py` | 56, 139 | 126, 129, 142, 221, 247, 248, 250, 251, 259 | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/tokenization/state_store.py` | 39 | 63, 74, 78 | — | 持久化／control protocol boundary：解码后收窄为 DTO。 |
| `src/app/transform/translator.py` | 6, 6, 9, 19, 50, 50, 53 | 58, 70 | — | 局部 JSON／第三方边界；按调用方向收窄。 |
| `src/app/upstream/base.py` | 38, 45, 53, 58, 65, 70 | — | — | 外部 transport boundary：宽输入可接受，转换后必须收窄。 |
| `src/app/upstream/bootstrap.py` | — | 180 | — | 外部 transport boundary：宽输入可接受，转换后必须收窄。 |
| `src/app/upstream/copilot.py` | 96, 110, 125, 136, 150, 169 | 103, 118, 130, 143, 156, 174 | — | 外部 transport boundary：宽输入可接受，转换后必须收窄。 |
| `src/app/upstream/generic.py` | 27, 40, 55, 65, 78, 96 | 34, 48, 60, 72, 84, 101 | — | 外部 transport boundary：宽输入可接受，转换后必须收窄。 |
| `src/app/upstream/models_api.py` | 22, 27, 41, 62 | 45 | — | 外部 transport boundary：宽输入可接受，转换后必须收窄。 |
| `src/app/wire_json.py` | — | 34, 44, 54 | — | 合理：单点 JSON encoder escape，前置递归验证。 |
