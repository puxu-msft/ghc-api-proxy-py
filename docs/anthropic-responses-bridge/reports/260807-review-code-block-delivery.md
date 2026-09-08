# Anthropic block delivery 骨架独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-block-delivery` 的 `feat/anthropic-block-delivery@e3fceb1cd14c44527bf2625acee0873421386caf`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。覆盖新增 renderer、continuous-prefix sequencer、首批 `message_start` 绑定、single-writer sink、delivery frontier、terminal 与 smoke；重点核对现有 `ResponsesStreamParser` API 是否可直接接入、`source_order` 缺口、重复／重排、terminal 是否可越过未提交 source，以及 smoke 判别力。按本轮明确范围，网络 partial write／delivery uncertainty、retry／post-commit replay 与 resident quota／backpressure 只登记为后续集成门，不报本轮 major。
- **总体 verdict**：**修复 major 后可进入；当前不可 squash。** Renderer 的 text／tool／thinking 完整 batch、首批绑定和理想化两 block continuous-prefix 正样本成立，但 delivery 的顺序坐标与 parser 当前事实模型不兼容，且 terminal API 无法消费 parser 的 open-source／terminal 事实，合法多 content-part 与 incomplete terminal 均可能失败或被误报成功。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：1。

## 双视角覆盖证据

### 机械核对视角

- 固定目标 HEAD 与 base，清点单提交新增的 3 个文件并完整读取实现和 smoke；`git diff --check` 通过，目标 worktree 在开始与结束核对时均为 clean。
- 对账 renderer 的三类 block：text 生成 start／可选 text delta／stop；tool 在渲染前要求完整 arguments 可解析为 JSON object，再生成 start／完整 `input_json_delta`／stop；thinking 生成可选 summary、项目主 v1 signature 与 stop。首个 block 的 `message_start` 与完整 block envelope 由同一个 `RenderedBatch.data` 承载；零 content terminal 也由单一 terminal batch 承载。
- 逐字段对账 `ResponsesStreamParser`：`SourceOpened.source_order` 在 output item added 时分配；同一 message item 的所有 text content parts 都复用 `item.source_order`；parser terminal 另带 `kind`、`error_code` 与 `open_blocks`。再对账 delivery：sequencer 把 `CompletedBlock.first_observed_order` 当成每 block 唯一且无洞的整数，`DeliverySession` 只接收 `CompletedBlock`，`finish()` 只检查 sequencer 中已完成但等待的 order。
- 扫描目标提交的调用面：新增 delivery 类型当前只由自身 smoke 使用，尚无 production parser／route／ASGI sink 接线。因此本轮判断是 checkpoint API 是否具备可组合性，不把“模块存在”外推为真实下游可观察行为已通过。
- 声明范围 smoke 实跑为 `6 passed`，口径仅为 `tests/smoke/test_anthropic_block_delivery.py` at `e3fceb1…`。该结果不构成全仓、真实 parser、ASGI、socket 或 Acceptance gate 通过证据；共享终端被其他并行会话复用，后续全仓／Ruff／Pyright输出无法可靠绑定本轮 nonce，故本报告不虚报其结果。

### 第一人称执行视角

- 以调用者身份走过 text、tool、thinking 三类完整 block：在当前手工构造的唯一连续 order 下，可得到闭合 batch；首 block 同 batch带 `message_start`，后续 block不重复起始事件，terminal 位于已提交 blocks 后。
- 模拟 `A` 先出现、`B` 先完成：只要调用者预先提供每 block唯一的 `0,1` order，`B` 等待、`A` 到达后按 `A,B` 释放；这是现有 smoke覆盖的理想化路径。
- 改用真实 parser 合同执行同一 message item 的两个 content parts：两个 `CompletedBlock` 都继承同一个 item-level `first_observed_order`。第一个 block 前移 sequencer 后，第二个会被判为“already delivered”；若后一个 part 先完成，也会与同 order 的前一个 part冲突。当前 API 因此不能按规格的“一 Responses item 多 content parts → 多 Anthropic blocks”直接组合。
- 模拟 `response.output_item.added` 后尚无完成 block便收到 `response.completed`：parser 正确产生 `kind="incomplete"`、`error_code="incomplete_lifecycle"` 和非空 `open_blocks`，但 `DeliverySession` 没有入口登记 `SourceOpened` 或消费该 terminal fact；其 pending order仍为空，调用 `finish()` 会生成成功 `message_delta`＋`message_stop`。同样，text part已完成但 message item尚未 done时，已提交 block之后仍可错误成功终止。
- 模拟并发调用时还发现 single writer 仅表示“只取得一个 writer 对象”，不自动保证 `deliver()`／`finish()` 的临界区串行。当前预期 driver可顺序调用，但 API 未声明或强制该前提；在接真实异步 sink前应补契约与定向并发控制。

## 事实性发现

### [major] `src/app/delivery/anthropic_sse.py:113-130`、`src/app/openai/responses_stream_parser.py:421-438` — sequencer 把 item-level `source_order` 误当成 block-level唯一连续序号

**问题**：`ContinuousPrefixSequencer.push()` 以单个整数作为 pending key，并要求每个整数恰好对应一个 block；但 parser 的 `source_order` 在 output item added 时分配，单个 item实际可产生零个、一个或多个 Anthropic blocks。`_text_draft()` 会给同一 message item的所有 `content_index` 复用 `item.source_order`；空 message或空 summary＋无 payload reasoning又可能不产出任何 `CompletedBlock`。现有 parser 测试只证明不同 output items的 source order为 `0,1`，没有冻结 item order到 block order的一一映射。

**证据或失败场景**：合法 message item含 `content_index=0` 的 text `A` 与 `content_index=1` 的 text `B` 时，两块的 `first_observed_order`相同。先提交任一块后，另一块必触发 `DeliveryOrderError("source order 0 was already delivered")`；如果两块在前块提交前都进入 pending，则后者直接撞相同 dict key。反方向上，若 order 0 的 item合法形成零 block，后续 order 1 的 block会永久停在 pending，因为 sequencer永远等待不存在的 block 0。结果既可能是合法 block丢失／失败，也可能是 source-order缺口导致 terminal无法完成。Smoke 的 `_block(order, ...)` 人工令 `BlockIdentity`、item id与 `first_observed_order` 一一对应，恰好绕开这两种真实 cardinality，因此 6 项全绿无法区分正确实现与此缺陷。

**修复建议**：不要在 delivery层自行假设 `first_observed_order` 已是 block-level稠密序号。让 parser／共享 semantic normalizer发布可排序的 block identity与 source lifecycle，例如按 item source order＋content part order建模，并让 sequencer消费 source-open／part-open／source-close事实；或者由上游明确产出真正的 block-level连续 order。无论选哪种，必须覆盖同一 item多 content parts、跨 item交错、后 part先完成、重复 done与 content-index gap，并证明 marker恰好一次且语义顺序精确相等。

### [major] `src/app/delivery/anthropic_sse.py:376-420`、`src/app/openai/responses_stream_parser.py:159-190,382-418` — session 无法登记 open source或消费 parser terminal，`finish()` 可越过未闭合／未提交 source发成功 terminal

**问题**：parser 的连续前缀安全性不只由“已完成但等待的 blocks”决定，还依赖 `SourceOpened`、item done与 `ResponsesTerminal.open_blocks`。`DeliverySession` 只暴露 `deliver(CompletedBlock)` 与自由形状的 `finish(stop_reason, usage)`；`finish()` 仅检查 `pending_source_orders`。一个已打开但尚未产生 `CompletedBlock` 的更早 source完全不在 sequencer中，parser报告 incomplete／failed／error也无法通过 API约束 terminal类型。

**证据或失败场景**：`response.output_item.added(message)` 后直接收到 `response.completed` 时，既有 parser 单测冻结 expected为 `ResponsesTerminal(kind="incomplete", error_code="incomplete_lifecycle", open_blocks=(identity,))`。若调用者按当前 delivery API调用 `finish()`，pending为空，renderer会合法生成 `message_start → message_delta → message_stop` 的零 content成功 batch；这把 malformed／truncated lifecycle伪装为成功。另一个场景是 text content-part done已形成并提交 block，但 output item尚未 done，parser仍把 source列为 open，当前 session却可立即发成功 terminal。该缺陷直接违反 terminal只能在所有应提交／应闭合 blocks之后产生的 checkpoint目标。

**修复建议**：建立 parser facts到 delivery的显式、穷尽式 adapter，最好让 session／driver消费完整 `ResponsesSemanticEvent` union：`SourceOpened`登记排序阻塞，`CompletedBlock`关闭对应 block并进入连续前缀，`UnsupportedResponsesEvent`走 typed failure，`ResponsesTerminal`只有在 kind允许成功、`open_blocks`为空、所有已知 source已闭合、ready batches已被 sink接受后才能生成成功 terminal。不要让调用者从 parser terminal旁路调用无类型 `finish()`。补 `added-only → completed`、part done但item未done、failed／error terminal、terminal重复与 terminal后content的正反测试。

### [minor] `src/app/delivery/anthropic_sse.py:85-107,376-420` — “single writer”只限制 writer领取次数，未定义或强制异步写入串行性

**问题**：`InMemoryDeliverySink` 确保其生命周期内只返回一个 writer，但 `DeliverySession.deliver()` 与 `finish()` 都会跨 `await writer.write()` 保留可变状态，且没有 lock／mailbox／single-consumer task或非重入断言。一个 writer对象可被多个 coroutine并发调用；“writer唯一”不自动推出“writes串行”。

**证据或失败场景**：若首 block写入在 await中暂停，另一个 task可看到 frontier尚未接受 `message_start`且 pending已清空，从而进入 `finish()`并写 terminal；随后首 block写返回，frontier因 terminal已接受而报错，但 wire可能已经成为 terminal在前、block在后。当前 memory writer不让出调度，smoke也没有并发调用，因此无法抓到这一时序。由于当前 checkpoint尚未接生产 driver，且调用者可以通过单一顺序消费 task满足合同，本项记 minor而非 major。

**修复建议**：在 API层明确且机械保证单一消费语义。优先让一个 driver／mailbox task独占 session并串行消费 semantic events；若保留可并发调用的 public async方法，则用同一锁包住 sequencer→render→write→frontier整个状态转移，并明确取消语义。增加可控暂停 writer测试，覆盖 deliver／deliver、deliver／finish与重复 finish，不要用同步 append writer证明异步 sink安全。

## 已确认成立的 checkpoint 行为

- Renderer 对完整 `TextBlock`、`FunctionCallBlock`、`ReasoningBlock` 预构造闭合 Anthropic SSE batch；tool arguments在渲染前要求 JSON object，thinking signature使用项目主 v1 carrier。
- 理想化 block-level稠密 order输入下，continuous-prefix会等待缺口并按顺序释放，不按 completion order重排。
- 首 block的 `message_start` 与该完整 block envelope处于同一个 `RenderedBatch`；零 content成功的 `message_start`、`message_delta`、`message_stop`处于同一个 terminal batch。
- Frontier只在 `writer.write()` 正常返回后记录 accepted block／terminal；render本身不推进 frontier。网络 partial-write／uncertain outcome尚未建模，按本轮约束留给后续，不据此追加 major。
- `InMemoryDeliverySink` 会拒绝第二次 `open_writer()`；这证明 ownership guard存在，但不证明异步 writes已串行化。

## Smoke 判别力结论

当前 smoke 对 renderer字段、首批事件顺序、理想化 `B done → A done`、terminal usage与 writer领取次数有基础判别力，但对本 checkpoint最关键的生产接缝判别力不足：它不运行 `ResponsesStreamParser`，不消费 `SourceOpened`／`ResponsesTerminal`，不覆盖同 item多 content parts，不覆盖 part done但item未done，也不使用会在 `write()` 中暂停的异步 sink。因此它会在上述两个 major都存在时保持全绿。修复后应至少增加 parser→semantic adapter→delivery的组件 smoke；真实 ASGI delayed-start、partial write／uncertain、retry、quota与backpressure仍按既定后续阶段执行，不把它们塞回本轮 major。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/openai/responses_stream_parser.py:421-438` ↔ `src/app/delivery/anthropic_sse.py:113-130` | 相邻模块用同名 `source_order` 表达不同粒度，属于跨边界语义泄漏 | **本轮修**：冻结 block-level排序合同并让 parser facts显式适配；不能靠调用者重编号掩盖 |
| `src/app/delivery/anthropic_sse.py:376-420` | Session只接 happy-path value objects，丢掉 open／unsupported／terminal控制事实，职责边界形成“信息都在上游但 API不可达” | **本轮修**：引入穷尽式 semantic-event adapter或等价 typed driver合同 |
| `tests/smoke/test_anthropic_block_delivery.py:20-34` | 测试 fixture自行制造实现所需的不真实不变量，形成同源 false-green | **本轮修**：保留 renderer unit fixture，同时新增真实 parser事实链 smoke与缺陷注入 |
| 网络 partial write／retry／quota | 后续完整产品能力尚未进入本 checkpoint | **记后续 gate**：按用户明确范围不报本轮 major；组合阶段执行真实 ASGI／socket、retry frontier与resident budget验收 |

## 主观建议

未提出额外主观范围扩张建议。当前最优修复路线是先把 parser→delivery 的 typed事实合同补齐，再接 delayed response start／真实 sink；成熟第三方库可帮助 SSE framing或队列实现，但无法替代本项目特有的 semantic order、open-source与commit frontier合同，不建议为这部分引入新的通用流处理框架。

## 结论

本提交是有价值的 renderer／frontier骨架，但还没有达到“0 major可 squash”的 checkpoint门。先关闭上述 2 个 major，并把 smoke改为能穿过真实 parser facts的组件级判据；minor可同时修复或在进入真实异步 sink前明确封口。网络 partial write／retry／quota继续作为后续必做 gate，不影响本轮严重级别判断。
