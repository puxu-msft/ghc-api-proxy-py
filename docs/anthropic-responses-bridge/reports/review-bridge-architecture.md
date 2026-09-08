# Anthropic Responses Bridge Architecture 独立评审

## 评审摘要

- **评审范围**：`docs/agents/anthropic-responses-bridge/architecture.md` 工作树快照，SHA-256 `5685ebc96672ea0354a75497270ad99f7bd2986f6b314b85e11a912694fcd661`；代码与既有决策基线为仓库 `HEAD 47d9ef101c4b81ac70d805b1da157b34d021d33d`。目标文档位于未跟踪的 `docs/agents/`，因此该 SHA-256 只标识本次读取的工作树内容，不能表述为 HEAD blob。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **计数**：blocker 0，major 5。本文按要求不报告 minor 或 nit。
- **机械核对覆盖证据**：逐项对账 C1～C8；核对架构内的 owner、事实真值时点、attempt/reset、block/order、sink/frontier、overflow、FINALIZE、History projection、候选方案与待裁决项；对照当前 `executor.py`、strategy contract、HTTP/WS client、SSE response、History consumer/store，以及 `docs/2604-rewrite/tool-use.md`、`history-system.md`、成熟库选型。检查 false-green 与 false-red：既检查错误状态能否通过，也检查合法 multi-part／交错 block、合法大 block、pre-commit retry 是否会被错误拒绝。
- **第一人称执行覆盖证据**：模拟了 Responses HTTP SSE 与 WS 两条 exchange 的打开、读流、fallback、取消和关闭；模拟同一 Responses message item 含多个 content parts、跨 item 交错完成、首 block 前断流、首 block 后断流、sink write 不确定、spool 后 History 持久化、observer／History 失败、client abort 与 shutdown 竞态；按现有 FastAPI／Starlette `StreamingResponse` 接线追踪了 HTTP success headers 与首个 body batch 的先后关系。

## C1～C8 结论

| 命题 | 结论 | 依据摘要 |
|---|---|---|
| C1 typed semantic kernel 与 driver/strategy 边界可落到当前代码 | **通过，需随下列 major 修边界** | 当前 `execute_anthropic_pipeline()` 已是集中 owner，现有 `RetryDecision` 可迁移为 typed outcome；架构也正确区分 observation、proposed effect 与 accepted effect。未发现需要第二条 pipeline 的结构障碍。 |
| C2 Responses HTTP/WS 能共享转换与 assembler | **方向通过，资源端口 major** | 两者可在 framing 后归一为 typed events，共享 converter／normalizer／assembler；但统一 port 没有表达 close/cancel contract，见 M1。 |
| C3 per-item block draft/commit frontier 可保证顺序、no dup/no loss | **未通过** | per-item identity 不能唯一表示一个 item 内多个 content parts／Anthropic blocks，见 M2；sink ack 仅能建立进程内“不可重放”边界，文档已正确否认客户端 durable exactly-once，但验收措辞仍应限定为应用层。 |
| C4 overflow 不会退化 live | **通过** | 容量路径只允许背压、spill 或 typed failure，并明确排除 retreat-to-live；未发现旁路 writer。实现时仍需原子 global quota reservation，但这不推翻当前架构方向。 |
| C5 pre/post commit retry 所有权清楚 | **未通过** | driver／policy／transport 的 owner 方向清楚，body block 前后边界也清楚；HTTP headers／`message_start` 的提交状态未纳入 frontier，见 M3。 |
| C6 History/observer 不重推导 | **部分通过，生命周期 major** | fact journal 与投影方向正确，明确禁止 observer 从 raw events 猜事实；但 spool cleanup 与 History projection 次序冲突，见 M4。 |
| C7 至少两方案权衡且推荐最佳 | **通过** | 比较 A、B、C 三方案，保留 A 为迁移兼容形态，拒绝双 lifecycle 的 C，并基于长期边界推荐 B。成熟库方面没有发现可直接替代 semantic converter、assembler、commit sequencer 或领域 retry policy 的通用库；既定 `httpx-ws`、HTTP SDK transport、AnyIO／`sse-starlette` 原语仍应复用。 |
| C8 不违背用户裁决 | **未通过** | block buffering／no-live 裁决得到遵守，server-tool 既有边界未被明确推翻；但默认持久化连续 attempt records 与既定 History 精简裁决冲突，见 M5。 |

## 事实性发现

### [major] M1 `architecture.md:261-275` — 统一 transport port 没有表达 driver 所声称的唯一 close/cancel 所有权

**问题**：`ResponsesTransport.exchange()` 只返回 `JsonExchange | EventExchange`，接口片段没有要求 `aclose()`、async context manager、取消传播或“terminal 后仍须关闭”的契约；但紧接着又要求 driver 在 success、retry、parse error、buffer failure、client cancel 与 shutdown 路径关闭 exchange。

**证据或失败场景**：当前 WS 实现 `src/app/openai/responses_ws.py:31-45` 是 async generator，连接关闭依赖 generator 被关闭后退出 `async with`；HTTP 则由 `httpx.Response.aclose()` 关闭。若统一层只把两者擦成普通 `AsyncIterator`，driver 无法由类型强制关闭；在 parser error、policy fallback 或 consumer 提前停止时，正确的 converter／assembler 仍可能留下 WS connection 或 HTTP response。机械 false-green 是“事件 parity 测试全绿但连接未关闭”；第一人称执行时，WS iterator 在 terminal 前异常或下游 cancel 即命中该分支。

**修复建议**：把 port 改为明确的 request-owned async context manager，例如 `async with transport.exchange(...) as exchange`；`UpstreamExchange` 必须提供 typed `events/body`、`aclose` 幂等语义、cancel provenance 和 close outcome。验收同时断言 success、fallback、parse failure、quota failure、client abort、shutdown 后资源归零；正确路径重复 close 不应 false-red。

### [major] M2 `architecture.md:307-330` — `per-item draft` 与“item 首次出现顺序”不足以定义 Anthropic semantic block identity

**问题**：架构按 Responses item identity／`output_index` 建一个 per-item draft，并写成“对应 item”产出 `CompletedBlock`；sequencer 也按 item 首次出现冻结顺序。Responses message item 可以含多个有独立 `content_index` 的 content parts，一个 item 因此可能映射为多个 Anthropic blocks；item identity 既不能唯一标识 block，也不能单独表达 item 内顺序。

**证据或失败场景**：同一 message item 依次包含 output text、refusal 或多个 content parts 时，单 per-item `CompletedBlock` 只能合并、覆盖或另造未定义的子 identity。现有判据 `architecture.md:416-417` 只测两个 item 的交错完成，错误实现即使丢失同一 item 的第二个 part 仍可全绿；相反，若实现为了避免冲突拒绝合法 multi-part item，则形成 false-red。配套 `spec.md:386-396` 仍把“按 Anthropic 可闭合语义”与“按 Responses output item”列为待裁决分叉，说明该身份模型尚未冻结。

**修复建议**：先接受并写清 semantic block 定义。推荐以稳定复合 key 表达 block，例如 `(attempt_id, output_index/item_id, content_index, semantic_kind)`，把 item metadata 与 block drafts 分层；顺序来自协议定义的 output／content 序位，而不是仅靠本地首次 arrival。新增同一 item 多 part、跨 item 交错、done-only、重复 done、delta-after-done 的正反控制，并以最终 block marker 有序精确相等检验 no-dup/no-loss/order。

### [major] M3 `architecture.md:313-319, 353-361` — commit frontier 漏掉 HTTP headers 与 `message_start` 的外部提交状态

**问题**：frontier 只在 `sink.write(batch)` 后记录 block／terminal；failure matrix 却区分“response headers 前”，但没有 `headers_committed` 或 `message_started` 状态，也没有规定谁延迟 ASGI `http.response.start`。因此“首 block 前 frontier 为空即可透明 retry”在真实 HTTP route 上并不充分。

**证据或失败场景**：当前 `src/app/streaming/sse.py:31-48` 直接构造 Starlette `StreamingResponse(status_code=200)`；标准 ASGI streaming response 会提交 response start 后再迭代 body。若 bridge 沿此接缝实现，首 block 尚未完成时 upstream 截断，block frontier 虽为空，客户端却已观察到 HTTP 200。重试耗尽后已不能返回真实 HTTP error，只能发流内 error；现有 `frontier 真值` 测试只观察 fake sink 写入数，会 false-green。反方向上，若实现无条件禁止此时 retry，又会把可通过 delayed-header sink 正确处理的路径误判为 false-red。

**修复建议**：把 delivery frontier 扩成明确的 envelope state，至少包含 `headers_committed`、`message_start_committed`、连续 block frontier、terminal state 与 sink generation；指定 route 使用 delayed-start ASGI response／等价 response owner，在首个完整 block或确定 terminal 前不发送 headers。failure matrix 应分别定义“headers 未提交”“headers 已提交但零 block”“block prefix 已提交”“write uncertain”，并为每个状态规定 retry 与错误 wire。

### [major] M4 `architecture.md:321-325, 383-396` — spool cleanup、FINALIZE 与 History projection 的顺序无法同时成立

**问题**：spool 在成功、失败、取消时清理；`FINALIZE` 又规定发生在 spool cleanup 完成之后；但流式 History 可以从 committed block ledger／spool 形成持久化 projection。文档没有定义在清理前由谁 materialize／移交 projection，也没有所有权转移或引用计数。

**证据或失败场景**：大响应已 spill、terminal batch 已提交，driver 先按规则 cleanup，再触发 FINALIZE／History consumer；History 此时无法读取 spool，导致 response 缺失。若先把完整 response materialize 到内存再 cleanup，则破坏 tiered buffer 的资源目标；若 History 异步持有已删除路径，则持久化竞态丢数据。当前 `src/app/history/consumer.py:20-33` 会 await finalize 与 flush，更说明持久化时点必须被明确，而不能靠 observer 自行从 raw events 重推导。

**修复建议**：冻结一条明确流水线：committed records 形成 protocol-neutral History projection／可转移 spool handle → History consumer 接受所有权并返回 accepted/durable outcome → request owner 依据政策释放或转移资源 → 发布 FINALIZE。若 History 不得阻塞 delivery，使用独立有界 writer queue 与引用计数／原子 rename 的 immutable spool artifact；若持久化失败，保留 `history.persistence_failed`，但不得重新解析 raw Responses events。为 success、persistence failure、cancel、shutdown 与 writer backpressure 做竞态测试。

### [major] M5 `architecture.md:394-396` — 默认 History 投影“连续 attempt records”越过既有精简持久化裁决

**问题**：架构把连续 attempt records、route／conversion diagnostics 和 commit frontier列为 History request truth，措辞指向默认持久化；现行长期文档则明确不持久化逐 attempt 对象图，只保存 `attempt_count`、`retry_strategies_applied` 等终态标量，详细模式留在 BACKLOG。

**证据或失败场景**：`docs/2604-rewrite/history-system.md:19-20,154-154` 明确采用轻量终态一次写入，并拒绝 client/upstream 双腿＋逐 attempt 重对象图；`architecture.md:394` 未区分 request-local fact journal 与持久化 History schema。实现者照架构落全量 attempt records 会改变存储、性能与对外查询合同，属于未获授权的重裁；实现者照既有 History 只落摘要，又会被架构文字误判为不完整。

**修复建议**：明确分三层：request-local journal 保留完整 typed attempt facts；默认 History 只投影既定标量与必要的新终态字段，例如 route、transport、commit count／terminal、final error；逐 attempt diagnostics 仅进入已裁决的可选详细模式／受限诊断附件。若确需改变默认持久化面，先由用户重裁并同步 `history-system.md`／BACKLOG，而不是在 bridge ADR 中隐式接受。

## 综合裁决

方案 B 的核心方向成立：typed shared facts、单一 driver、protocol／transport 正交、HTTP／WS 共享语义层、assembler 与 sink 分离、overflow 永不退 live、observer 只消费已发布事实，均比方案 A 的长期 wire-shaped state 更稳健；也没有发现成熟库能整体替代这些领域机制。当前不能直接接受为可实施架构，原因不是需要更多实现细节，而是上述 5 个缺口会让实现者在合法输入、真实 HTTP 提交、取消／关闭、spool 持久化和既有用户裁决上得到相互冲突的行为。

**复审门**：修订 M1～M5 后，逐条重跑 C1～C8 对账；重点要求 multi-part item 正负控制、真实 ASGI delayed-header 路径、HTTP／WS close/cancel 资源归零、spool→History ownership race，以及默认 History schema 与现行裁决一致。
