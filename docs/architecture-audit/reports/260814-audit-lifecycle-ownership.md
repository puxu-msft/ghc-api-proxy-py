# 请求生命周期与所有权接缝独立体检

## 1. 结论摘要

已完成子轴 1 与子轴 2。Anthropic Responses 流的 parser→assembler→buffer→renderer→sink→frontier→ASGI 链在生产入口中未发现直接旁路；但 transport、终态和 History 发布仍是流式／非流式的分支化所有权，维持 `minor`。

## 2. 所有权矩阵

| 关注点 | 当前 owner（file:line） | 是否唯一 | 第二入口（若有） | 严重度 | 建议处置 |
|---|---|---|---|---|---|
| request id 的生成与持有 | `src/app/pipeline/context.py:74` 的 `RequestContext.id` 默认工厂生成；`src/app/pipeline/executor.py:205` 构造 Anthropic context | 已证实唯一 | 无；`pipeline/protocol_guard.py:16` 属其他协议 | 无 | 保持 executor 创建、context 持有。 |
| attempt 序列的推进 | `src/app/pipeline/executor.py:270` 的 `context.attempts.append(attempt)` | 已证实唯一 | 无；`src/app` 仅此 `attempts.append` | 无 | 保持 executor 同时拥有编号、创建与记录。 |
| approval 等待点 | `src/app/pipeline/executor.py:220` 调用 gate；`pipeline/approval.py:83` 持有 pending | 已证实唯一 | 无；`protocol_guard.py:21` 属其他协议 | 无 | executor 保持唯一等待者。 |
| retry 预算的扣减 | `src/app/pipeline/strategies/__init__.py:52` 的 `self._remaining -= 1` | 已证实唯一 | 无；`src/app` 仅此扣减 | 无 | 所有 retry 经过 coordinator。 |
| transport 的打开与关闭 | 打开：`anthropic/client.py:197`／`:262`；关闭按分支在 `client.py:308`、`routes/anthropic.py:203`、`:255`、`:289` 及 `executor.py:371`、`:397`、`:407`、`:440`、`:500` | 非单一 owner | 上述互斥分支 | minor | 显式资源移交 contract 或 response lease。 |
| finalize（请求终态） | 非流式：`executor.py:99`、`:455`、`:502`；流式：`routes/anthropic.py:72`、`:90` | 非单一 owner | stream handoff 两侧 | minor | 收拢 finalizer，或在 result 上显式移交。 |
| History 投影发布 | 非流式：`executor.py:123`、`:468`、`:511`；流式：`routes/anthropic.py:118` | 非单一 owner | stream handoff 两侧 | minor | 以统一 finalizer 或明确 stream-only 发布约束收拢。 |

## 3. 交付链与 `committed_response` 重判

| 链环 | 实际 owner（file:line） | 旁路核验 |
|---|---|---|
| parser | `delivery/responses_anthropic_stream.py:212` 解析 SSE，`:250` 调 `ResponsesStreamParser.process` | 不产生 ASGI 字节。 |
| assembler | `delivery/anthropic_sse.py:644` 的 `DeliverySession.consume`，`:686` 仅释放 closed prefix | 唯一写入下一环是 `:723` 的 writer。 |
| buffer／sink | `_BufferedWriter.write`（`responses_anthropic_stream.py:40`）只 append；`_BufferedSink.open_writer`（`:52`）拒绝第二 writer；`:376` 才 drain | buffer 之外未找到 Responses 字节 emitter。 |
| renderer／frontier | `anthropic_sse.py:713` render block，`:854`－`:883` 由 acknowledgement 独占推进 frontier | `accept_block`／terminal／error 仅在 `:874`－`:883` 调用。 |
| ASGI | `streaming/sse.py:117` 先取得 first batch，`:142`、`:162` 才写 start／body；Responses 路由只在 `routes/anthropic.py:259` 选择 delayed response | 未找到该 route 的第二个 `http.response.*` writer；generic `create_sse_response` 是非 Responses leg。 |

确认：`routes/anthropic.py:108`－`:117` 原地补写的是 `ResponsesAnthropicStreamState.committed_response` 的 History payload，不是 `DeliveryFrontier` 或已排队 SSE bytes。该 dict 在渲染器 finally 的 `responses_anthropic_stream.py:181` 冻结；其唯一生产消费链是 `_project_committed_response`（`:100`－`:138`）→ route `:104`－`:117` → `HistoryConsumer.finalized`，而前端 bytes 已在 `_history_stream` 的 `yield`（`routes/anthropic.py:48`－`:50`）交给 delayed ASGI writer。故**不构成交付链旁路，也不是第二个 History 发布者**；它是 route 对 delivery projection 的后提交元数据补全。

该对象为可变 cached dict，且“committed”易被误解为不可变快照；建议把 route 的 usage／error 补全改为复制后交给 History 或由 state 提供显式 History projection。当前唯一消费点扫描为 `routes/anthropic.py:104`，故这是 `minor` 可维护性建议，非已证实的行为缺陷。

纳入该证据后，finalize 的 `minor` 评级维持：它没有新增 `context.transition`／`context.fail`／`history.finalized` 入口，不能使流式与非流式终态分裂升级为重复 finalize。

## 4. 看起来可疑但实际正确

- `pipeline/protocol_guard.py:16` 与 `:21` 属 Azure、Gemini、OpenAI、Responses WebSocket 请求，不是 `/v1/messages` 的第二 owner。
- 多处 transport `aclose` 分属成功流式、成功非流式、retry／转换失败和最终错误的互斥分支；未发现同一成功 response 被双重关闭。
- `committed_response` 的 mutation 发生在 History 投影前，而非 SSE 发送前；其字段 `usage`、`usage_facts`、`error` 与 state 的 `content`、`delivery` 投影不重叠。

## 5. 扫描范围与判据

- 扫描 `src/app/{pipeline,anthropic,routes,delivery,history,context,streaming}/**/*.py` 的 `RequestContext`、终态、History、writer、`yield`、`send`、frontier、sink、`committed_response` 调用点；以 Responses `/v1/messages` 的可达生产调用链为范围，并同时查“直写 ASGI／frontier 早推／sink 外 bytes”与正常延迟链。

## 6. 未覆盖面

子轴 3～5（cleanup／cancellation、错误吞噬 AST 等）留待后续单独审计。
