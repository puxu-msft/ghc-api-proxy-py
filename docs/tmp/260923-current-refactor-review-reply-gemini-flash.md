# 审查报告：请求生命周期、观察记录与回复路径审查

- report_id: `260923-review-reply-gemini-flash-1`
- attempt_id: `260923-reply-gemini-flash-1`
- reviewed_at_rev: `061aff32520dd54dceda8ebce7ef6678dee3e02d`
- reviewer: `只读正确性审查员 (gemini-flash)`

## 审查范围与方法

### 审查范围
本次审查聚焦于当前请求生命周期中上游回复解析、下游装配交付以及可观测性记录的关键链路：
1. `src/app/pipeline/reply.py`：缓冲模式下的回复解析与 `reply_summary` 终态提取。
2. `src/app/pipeline/delivery_policy.py`：分块交付决策、协议方言判断 (`dialect_for`)、装配器 (`assembler_for`) 与成帧器 (`framer_for`) 派发机制。
3. `src/app/pipeline/hand_over.py`：未完成轮次的中断原因判定、分类映射 (`CATEGORY_FOR_REASON`) 与 Claude Code 接续块 (`hand_back_block`) 构造。
4. `src/app/pipeline/driver.py`：驱动请求流、重试记账、本地合成回复 (`_answered_failed_search` / `_answered_auto_mode`) 及交付计划绑定。
5. `src/app/observability/request_trace.py` 与 `src/app/observability/request_completion.py`：`RequestTrace` 与 `RequestCompletionCoordinator` 对回复终态事实、Token 使用量与双向事实的吸收和协调机制。
6. `src/app/server/routes/inference.py`：流式（分块）与非流式（整体缓冲）的分发、执行、终态吸收与下行写入。

### 审查方法
1. 原则对齐：严格基于项目原则 `one-reply-fact-one-answer-across-both-reply-modes`（单回复事实两模式同解）、`display-reads-an-aggregate-not-raw-objects`（展示层读聚合记录，不读原始对象）、`absence-is-not-readable-on-a-log-line`（日志行上的缺席读不出来）以及 `block-level-delivery-not-streaming`（块级交付非流式）。
2. 静态分析与链路比对：对流式路径（`_StreamAccounting.settle` -> `assembler.terminal` -> `trace.absorb(terminal)`）与整体缓冲路径（`response_payload` -> `reply_summary` -> `trace.absorb(context.reply)`）进行逐字段比对，重点审查 `usage`、`stop_reason`、`blocks`、`tools`、`thinking` 的推导是否存在重复实现或分支分歧。
3. 伪造默认值与脱节核查：核实是否存在将未观测事实伪造默认值、下游下行内容与记录跟踪不一致的情况。

---

## 审查发现（Findings）

### finding_id: `REP-01`
- severity: `major`
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/reply.py:102-108`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:1330-1348`
  - `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py:276-321`
- 证据与分析场景：
  在非流式整体缓冲（buffered）路径中，`src/app/server/routes/inference.py` 执行 `context.reply = reply_summary(handled, payload)`。然而，`reply_summary`（`src/app/pipeline/reply.py:102`）硬编码了入站协议门禁：
  ```python
  def reply_summary(handled: HandledRequest, payload: dict[str, Any]) -> Terminal | None:
      if handled.route.inbound_format is not WireFormat.ANTHROPIC_MESSAGES:
          return None
      return terminal_from_anthropic(payload, blocks_from_anthropic(payload), dialect=dialect_for(handled))
  ```
  当入站客户端为 OpenAI Responses 原生客户端（`/v1/responses`）或 Chat Completions 客户端（`/v1/chat/completions`）时，`reply_summary` 直接返回 `None`。这导致：
  1. `context.reply` 为 `None`，`trace.absorb(context.reply)` 被跳过。
  2. 尽管随后执行了 `_absorb_response_observation(context, trace)`，但这仅适用于上游为 `openai-responses` 且携带 `response_observation` 的场景。若目标上游非 Responses（如直接透传或 Chat Completions），`context.reply` 依然为空，`trace.usage`、`trace.stop_reason`、`trace.blocks`、`trace.tools`、`trace.thinking` 等终态事实完全未从非流式响应中提取。
  3. 与流式路径对比，流式路径下无论入站协议为何，装配器（`ResponsesPassthroughAssembler`、`ChatCompletionsAssembler` 等）均会生成 `assembler.terminal` 并被 `trace.absorb(terminal)` 吸收。这违反了 `one-reply-fact-one-answer-across-both-reply-modes`：同一非 Anthropic 入站格式的回复事实，流式能观测并沉淀为终态事实，整体缓冲模式却因格式白名单被直接丢弃。
- 修复建议：
  扩展 `reply_summary`，或者使 `reply_summary` 根据 `handled.route.inbound_format` 分发到对应的终态提取器（例如针对 Responses 格式调用提取 Responses 终态的 helper，针对 Chat Completions 提取 `choices[0].finish_reason` 与 usage），确保缓冲路径上的所有协议均产出自洽的 `Terminal`。

---

### finding_id: `REP-02`
- severity: `major`
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:1334-1358`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:1515-1540`
  - `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py:276-321`
- 证据与分析场景：
  在 `src/app/server/routes/inference.py` 中，无论是非流式路径（第 1347 行）还是流式结算路径（第 1528 行），均存在“先吸收 `Terminal`，后无条件调用 `_absorb_response_observation(context, trace)` 覆盖”的双重推导与字段覆盖冲突：
  ```python
  # 第 1347 行：
  if context.reply is not None:
      trace.absorb(context.reply)
  _absorb_response_observation(context, trace)

  # 第 1528 行：
  self.trace.absorb(terminal)
  ...
  _absorb_response_observation(self.context, self.trace)
  ```
  而在 `_absorb_response_observation` 内部：
  ```python
  observation = getattr(context, "response_observation", None)
  if observation is not None:
      trace.absorb_response(observation)
  ```
  在 `request_trace.py:288-320` 的 `absorb_response()` 中，会直接无条件覆盖由 `Terminal` 填入的核心字段：
  ```python
  self.usage = dict(observation.usage)
  self.stop_reason = observation.stop_reason
  self.blocks = observation.blocks
  self.tools = list(observation.tools)
  self.thinking = observation.thinking
  ```
  这一覆盖机制导致：
  1. `Terminal` 中由装配器或 `reply_summary` 计算的字段（例如针对特定客户端方言规范化的 `stop_reason`、经过 `hand_back_block` 注入或裁剪后的工具调用与块计数）被上游原生 `response_observation` 的原始事实强行重置覆盖。
  2. 流式装配器在处理 `max_tokens` 截断时，如果发生了 hand-over（改写了 stop_reason 为 `tool_use`，注入了接续 tool call），`terminal.stop_reason` 已变为修改后的状态；但在 `settle()` 中随后执行 `_absorb_response_observation`，`trace.stop_reason` 又被 `observation.stop_reason`（例如原生的 `max_tokens` 或 `length`）覆盖回滚。
  3. 这使得 `trace.stop_reason` 与实际向客户端发送的结束事件脱节（记录显示原生截断，下行网络却发送了带有接续 tool call 的 `end_turn` / `tool_use`）。
- 修复建议：
  统一单回复事实的吸收源。若已有经过装配器或交付方言统一决议的 `Terminal`，应以 `Terminal` 作为最终事实；若需保留上游原生 observation，应将其作为独立原生属性记录（例如保留在 `trace.upstream_response_observation`），而不是直接在 legacy projection 层双重覆盖。

---

### finding_id: `REP-03`
- severity: `minor`
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/responses.py:328-348`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:168-185`
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/reply.py:102-108`
- 证据与分析场景：
  关于“丢弃因 `max_tokens` 截断的不完整输出项（truncated item）”这一业务逻辑，在流式装配器与非流式响应转换器中存在两套独立的判定与修剪实现：
  1. 流式装配器：在 `ResponsesAssembler`（`src/app/pipeline/delivery/formats/openai_responses.py:175`）中，根据 `self._will_hand_over` 判断是否在收到 `response.output_item.done` 且 `item.status == "incomplete"` 时丢弃该 item。
  2. 非流式响应转换：在 `src/app/pipeline/translation_driver/responses.py:330-345` 的 `from_openai_responses_response` 中，另行实现了一套遍历 `output`、检查 `item.status == "incomplete"`、并根据 `retry_config.hand_over_stop_reasons` 过滤 `incomplete_details.reason` 的裁剪逻辑。
  虽然两处逻辑意图一致，但两套独立的过滤代码不仅增加了维护成本，而且在判断依据的细节上存在隐蔽差异（例如流式路径基于装配器初始化时传入的 `hand_over_stop_reasons` 与 `stop_reason` 累积状态，非流式路径则直接检查 item 级别的 `incomplete_details.reason`）。当未来扩展新的 incomplete 状态或原因时，极易发生流式与缓冲模式行为分叉。
- 修复建议：
  将 truncated item 的判定与修剪规则收拢为公共域函数（例如 `should_discard_incomplete_item(...)`），由 `ResponsesAssembler` 与 `from_openai_responses_response` 共享调用，确保两模式判据完全一致。

---

### finding_id: `REP-04`
- severity: `minor`
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/hand_over.py:348-351`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/hand_over.py:27-31`
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:20-50`
- 证据与分析场景：
  在 `src/app/pipeline/hand_over.py` 中构造接续块时，针对未映射或未知原因的异常，退避分类直接降级赋值为 `ErrorCategory.UPSTREAM.value`：
  ```python
  category = (
      CATEGORY_FOR_REASON.get(reason, ErrorCategory.UPSTREAM).value
      if reason
      else ErrorCategory.UPSTREAM.value
  )
  ```
  代码注释明确承认了这一点（“UPSTREAM when the retry taxonomy has no word for the failure, not INTERNAL”）。虽然注释解释了避免向客户端汇报代理自身损坏（internal）的考量，但当发生的实际异常属于代理本地配置、ASGI 下行故障或未预期的本地系统异常时，直接将 category 标记为 `upstream`，向客户端伪造了“这是上游故障”的结论。这可能导致客户端 MCP 或 Claude Code 在诊断日志中误判故障归属方，将网关本地缺陷排查引向服务端上游。
- 修复建议：
  在 `hand_over.py` 中细化异常原因分类，对于未明确由上游网络或服务端返回的错误，提供明确的本地异常分类或中立的 `unknown` / `unclassified` 状态，避免将未确认归属的故障无差别伪造为上游责任。

---

## 排除的可疑项（Dismissed Suspect Items）

1. **可疑项：`delivers_blocks` 对 Chat Completions 的一刀切全量交付判定**
   - 怀疑点：`delivers_blocks` 在 `handled.route.inbound_format is WireFormat.OPENAI_CHAT_COMPLETIONS and not handled.route.translation_required` 时返回 `False`，导致 Chat Completions 流式不走逐块交付，怀疑是逻辑缺失。
   - 排除依据：核查 `src/app/pipeline/delivery_policy.py:62` 及对应历史裁决，Chat Completions 的流式边界位于 `choices[].delta` 内部，下游协议没有独立的块结构成帧器，因此设计上明确由 `one_shot_delivery` 原样透传上游字节，避免了无成帧器时向客户端发送空 200 的缺陷。这属于明确的协议边界设计，而非缺陷。

2. **可疑项：`hand_back_block` 中 `client_message_count` 直接读取入站请求而非翻译后请求**
   - 怀疑点：`client_message_count` 使用未翻译的原始 `payload["messages"]` 长度，怀疑在 Responses 展开多项时导致计数不准。
   - 排除依据：核查 `src/app/pipeline/hand_over.py:59` 注释及客户端行为。Claude Code 的循环检测器（loop detector）仅感知自身视角发送的消息数，而 Anthropic 消息在 Responses 链路会被拆为多个 item。若使用翻译后 item 计数，会导致客户端每轮步进数字混乱，破坏客户端死循环熔断。因此基于客户端视角计数是正确的设计。

3. **可疑项：`_answered_failed_search` 与 `_answered_auto_mode` 的伪造响应**
   - 怀疑点：网关本地合成回复（`synthesized=True`）伪造了 HTTP 200 响应，怀疑违背了“不伪造默认值”原则。
   - 排除依据：这两处属于显式授权的业务容错特性（分别针对客户端重复触发不可用搜索工具导致死循环、以及自动模式授权拦截），合成的响应严格经过装配器、成帧器与交付管线，并在 `HandledRequest` 上显式标记了 `synthesized=True`，展示层与审计均可知晓，不属于“无观测事实下的静默伪造”。

---

## 整体判定（Overall Verdict）

**VERDICT: `needs-fix`**

系统在主功能路径（Anthropic 客户端接入 Responses 上游）的设计与实现高度成熟，块级交付与成帧器抽象非常清晰。但存在两处 `major` 级别的设计缺陷：
1. `reply_summary` 对非 Anthropic 入站格式直接返回 `None`，导致非流式整体缓冲路径在处理非 Anthropic 请求时彻底丢失终态事实记录（`REP-01`）。
2. 在结算阶段，`_absorb_response_observation` 强行覆盖 `Terminal`，导致经过装配器改写或适配的终态事实（如接续工具调用与修正后的 stop_reason）被上游原始 observation 抹去，造成跟踪记录与下行实际数据脱节（`REP-02`）。

---

## 最没把握的三个判断（Least Confident Judgments）

1. **关于 `REP-01` 中 Chat Completions / Responses 客户端在非流式下是否确实需要结构化 `Terminal`：**
   目前 `Terminal` 的结构（`blocks`、`thinking`、`tools`）深度契合 Anthropic 格式。对于纯 OpenAI Responses 或 Chat Completions 的非流式客户端，它们自身并不消费 Anthropic block 概念。尽管可观测性日志（如终端输出）希望看到统一的终态摘要，但目前缺失的是针对 OpenAI 格式的 `Terminal` 构建器。
2. **关于 `REP-02` 中 `absorb_response` 覆盖的真实意图：**
   `_absorb_response_observation` 对 `trace` 的覆盖可能是为了确保原生 token usage（包含 cached tokens、reasoning tokens）不被简化版 `Terminal` 丢失。如果仅因保留 usage 而一并覆盖了 `stop_reason`，则属于伴生副作用。需确认系统设计上是否意图让 observation 享有高于 terminal 的优先级。
3. **关于 `REP-04` 中退避为 `UPSTREAM` 的危害程度：**
   代码注释明确指出该设计是为了防止向客户端透露“代理内部崩溃”，避免客户端误以为是网关自身 Bug 而放弃重试。这种为了驱动客户端继续重试而做出的降级分类，在工程权衡上可能有其实际收益，认定为 `minor` 缺陷依赖于对“日志归因纯粹性”与“客户端行为驱动”之间的权衡。

---

## 执行摩擦（Execution Frictions）

1. **规范与实现的术语重载：**
   代码库中频繁出现 `observation`、`terminal`、`reply`、`summary` 等近似术语。例如 `context.response_observation`、`context.reply`、`assembler.terminal` 以及 `trace.absorb`，在不同生命周期节点的流转关系较为复杂，需要反复交叉验证调用栈才能确认实际生效顺序。
2. **多协议交叉组合的静态跟踪成本高：**
   入站格式（`inbound_format`）与出站目标格式（`target_format`）的乘积空间庞大（Anthropic Messages、OpenAI Responses、Chat Completions、CommandCode），部分路径（如 Chat Completions 客户端流式）通过 `delivers_blocks` 的负条件直接跳过成帧器，逻辑分布在多个策略函数中，难以通过单一接口全景审视。

---

## 交付声明

```yaml
delivery_complete: true
completed_at: "2026-09-23T10:45:00Z"
findings_total: 4
counts:
  major: 2
  minor: 2
  info: 0
```
