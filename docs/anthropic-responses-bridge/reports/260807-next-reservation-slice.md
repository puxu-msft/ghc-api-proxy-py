# 下一最小代码切片：DeliverySession resident reservation primitive

## 调查锚点与结论

- **代码锚点**：`/home/xp/src/ghc-api-proxy-py` 的 current `main@fb5c027b38cc72910dd4495979a26a57fbbaa99b`。
- **行为 oracle**：`docs/agents/anthropic-responses-bridge/spec.md`，尤其是“Block-level buffering 与 commit 契约”和“Shutdown、cancel、backpressure 与 limits 契约”。Architecture 与 Acceptance 只用于理解承载接缝，不改写 Spec。
- **当前结论**：main 已有完整 block withholding、连续前缀 sequencer、typed sink outcome 与 ASGI ACK／uncertain 接缝，但没有 request／global resident byte reservation；现有 list、dict 与 `_BufferedSink` 都可以无界持有 payload。
- **推荐最小 primitive**：新增一个基于 `asyncio.Condition` 的共享 weighted byte budget、一个带构造期capacity的request-local account和显式lease；先以opt-in方式供 `DeliverySession` 对“等待连续前缀的completed semantic payload”和“等待sink ACK的rendered batch”记账及背压。此片不接生产配置、不宣称所有route生效，也不宣称关闭完整 `REL-06`。
- **改进用户示例的唯一校正**：current main 的 incomplete drafts 实际由 `ResponsesStreamParser` 持有，不归 `DeliverySession`。首片不能把“DeliverySession 已记账”写成“draft 已覆盖”；parser delta 的 charge-before-append 是明确后继边界。

## Spec quota 条款的最小不可破坏集合

本片不是重新设计 quota，只保留实现 primitive 时不能违背的冻结条款：

1. `spec.md:308-315`：完整 Anthropic content block 是最小提交单元；quota 压力不得切换到 live write-through，也不得提交 partial block。
2. `spec.md:450-464`：慢 downstream 必须通过有限容量和 budget 等待向 upstream 反压；completed blocks 可以排队，但 resident bytes／block count 必须受 request 观测与 global budget 约束；等待必须响应 cancel／shutdown；每次 charge／release 绑定 request、attempt、owner并恰好一次。
3. `spec.md:467-476`：完整产品最终必须具有 per-request buffered bytes、global buffered bytes、completed-block queue depth、deadline 等限制，并在失败后清理 quota charge。
4. `spec.md:498-500`：steady-state memory 最终必须由声明的 budget 限定，不 spill，并能把 downstream backpressure 传回 upstream。
5. `spec.md:530-548`：任意单 block 大小只是普通维度；不得引入 `16 MiB` 或其他 per-block 特殊阈值、oversized debt、spill、overflow-to-live、victim policy或全面物理 OOM 状态机。

因此本片只能声称提供可复用的两级reservation primitive与一个真实await接缝。request／global capacity尚未接生产配置，route admission、全部resident owner、queue item cap、deadline到Anthropic error／History／metrics的产品映射仍未完成。

## current main 的 resident 与 delivery 现状

### 已有的正确接缝

- `ResponsesStreamParser` 在 `_text`、`_function_calls`、`_reasoning` 中持有 attempt-local draft；完成后产出 immutable `CompletedBlock`，见 `src/app/openai/responses_stream_parser.py:80-145,366-404,573-606`。
- `ContinuousPrefixSequencer` 在较早 source 尚未闭合时，把后完成的 `CompletedBlock` 留在 `_SourceState.blocks`；只有连续前缀闭合后才返回 ready blocks，见 `src/app/delivery/anthropic_sse.py:185-263`。
- `DeliverySession` 串行执行 consume／render／write，`_pending` 在 sink 返回 `pending` 后保留 `RenderedBatch` 与 semantic block，直到 accepted／uncertain ACK，见 `src/app/delivery/anthropic_sse.py:585-600,606-703,788-837`。
- production `_BufferedSink` 在 `_pending: list[bytes]` 中保留 batch；`_drain_accepted()` 在 generator resume 后才 ACK accepted，在 yield 异常时 ACK uncertain，因此这里已经存在真实 downstream backpressure 接缝，见 `src/app/delivery/responses_anthropic_stream.py:29-59,332-345`。

### 当前无界或未记账之处

- parser 的 string delta lists、authoritative values 与 carrier bytes 没有 charge-before-append。
- sequencer-held completed blocks 没有 byte charge，也没有 request／global high-water。
- rendered bytes 同时被 `RenderedBatch`、`DeliverySession._pending` 与 `_BufferedSink._pending` 引用；虽是同一 `bytes` 对象，不应按引用数重复收费，但 current code 没有 owner token来表达这一点。
- `DeliverySession._scheduled_blocks` 与 `DeliveryFrontier._committed_blocks` 为 ACK／History 保留 semantic blocks；`ResponsesAnthropicStreamState.batches` 还会累计 accepted bytes，而 production source中没有读取该字段的消费者，见 `src/app/delivery/responses_anthropic_stream.py:61-71,340-345`。在这些引用仍存活时提前 release 会造成“计数为零、对象仍 resident”的假绿。
- delivery 模块没有显式 close／cleanup API。route 当前只通过 `passthrough_bytes(..., cleanup=upstream.aclose)` 关闭 upstream，见 `src/app/routes/anthropic.py:220-257`；它尚不能证明 delivery-owned lease 在 success、error、cancel和uncertain路径都释放。

## 选择的 primitive

### 为什么选 `asyncio.Condition`

优先复用标准异步原语，但不误用不匹配的抽象：

- `asyncio.Semaphore` 一次 acquire 只代表一个 token。循环 acquire `N` 次不是原子 weighted reservation，两个大 waiter可能各拿到部分 token后互相阻塞。
- 当前 AnyIO `CapacityLimiter.acquire()`／`acquire_on_behalf_of()` 同样一次只借一个 token，且 borrower不能同时借多个 token；`create_memory_object_stream()`限制 item 数，不限制每个 item 的 bytes。把 byte 数硬映射成逐 byte token既低效，也不能原子取得整个 reservation。
- 一个很小的 `asyncio.Condition` wrapper 可以在锁内以谓词 `current + amount <= capacity` 原子检查并 charge，在 release 后 `notify_all()`。它复用成熟 cancellation／task scheduling语义，只自定义项目真正缺少的 weighted accounting，不自建调度器、worker或治理层。

本片不承诺严格 FIFO 或按 request公平调度。若真实负载证明大 waiter starvation，后续以运行证据决定是否增加 waiter queue；当前不得提前扩张为公平性／victim policy系统。

### 最小接口与不变量

建议新增三个窄类型，命名可以在实现 review 时微调，但职责不能合并回 route或renderer：

- `ResidentByteBudget(capacity_bytes)`：进程内可共享的 weighted budget；暴露只读 `current_bytes`、`high_water_bytes`；`await reserve(account, owner, amount)` 在容量不足时等待，`await reserve_many(account, charges)` 对同一 delivery step 的多个owner执行全有或全无的原子charge。
- `RequestResidentAccount(request_id, attempt, capacity_bytes, budget)`：request-local current／high-water counter、owner registry与普通aggregate hard capacity；capacity只由构造参数提供，本片不增加settings或route默认值。
- `ResidentLease(owner, amount)`：唯一释放权；`await release()` 恰好减一次 request与global计数并唤醒 waiters。直接重复 release 应抛出 programming error；上层 `DeliverySession.aclose()` 本身应幂等，避免多条 cleanup路径造成 double release。

机械不变量：

1. account构造时必须满足 `0 < request_capacity_bytes <= global_capacity_bytes`；否则立即拒绝。这个关系保证request gate放行的charge不会仅因本request自身已持有的lease而永久卡在global gate。
2. `amount` 必须为正整数。若本次charge使 `request.current + amount` 超过request capacity，或单次／整组charge本身超过global capacity，则立即抛带scope的typed `ResidentCapacityError`，不得等待一个不可能由其他request释放容量而满足的谓词；只有request gate通过后的global contention才进入 `Condition.wait_for()`。
3. 这道request gate不是大block特殊阈值：同一普通aggregate公式适用于所有owner。它同时阻止自死锁——已由本request持有且必须等delivery前进才能释放的semantic lease，不能让下一份rendered lease无限等待自己。
4. waiter取消时尚未charge，因此request／global current不变；取得lease后发生取消，则lease进入session-owned cleanup集合并由 `aclose()`释放。
5. global与request计数之间不得出现await；一次成功reserve在同一临界区／无切换区间内同时更新两者。
6. 同一次 `consume()` 若携带多个 `CompletedBlock`，先以 `reserve_many()` 对整组owner做全有或全无的charge，再修改sequencer。容量不足、取消或typed capacity failure时，一个block都不得被插入；禁止逐个reserve后留下半更新的source state。
7. 同一payload object只由一个owner lease收费。completed semantic payload与其新生成的rendered `bytes`是两个同时resident的不同对象，转换重叠期间应分别收费，不能为了通过小budget测试而提前释放semantic lease。
8. 本片的byte size是明确、可复现的 **payload-byte accounting**：字符串字段按UTF-8 bytes，rendered batch按 `len(batch.data)`；不声称等于CPython allocator／container overhead或RSS。完整 `actual resident bytes` 校准与container overhead政策留给后续Acceptance slice，当前文档不得把该近似写成完整Spec PASS。

## DeliverySession 的最小接线

本片只在调用者显式传入 `RequestResidentAccount` 时启用；未传入时保持 current behavior。这样 primitive 可以先合并和复用，而不会偷偷给 production选择硬编码容量或伪装成全局配置已经完成。

### completed semantic owner

- 在 `DeliverySession.consume()`／`deliver()` 把新 `CompletedBlock` 放入 sequencer前，计算其规范 payload bytes；`deliver()`用单owner `reserve()`，`consume()`把本次events中的全部新blocks交给 `reserve_many()`，全部lease取得后才依次修改sequencer。
- lease 随 block在 sequencer、`_scheduled_blocks`、frontier与History projection生命周期内移动，不因 `reconcile_open_identities()` 返回 ready、render完成或 sink ACK就提前 release。
- `DeliverySession.aclose()` 在调用者已形成自包含 History projection后清理 sequencer／scheduled／pending／frontier payload引用并释放这些 lease。首片测试必须显式调用；production cleanup接线列入后续边界，不在本片假定存在。

### rendered batch owner

- renderer生成 `RenderedBatch` 后、调用 writer前，先为 `len(batch.data)`取得 `("rendered", batch.digest)` lease；容量等待发生在继续读取下一 upstream event之前，因此 caller 的 `await session.consume()`自然形成背压。
- sink返回 `pending` 时 lease随 `_pending`保留；accepted或uncertain ACK从 `_pending`移除batch后释放。启用account时，sink合同必须是：`accepted`表示sink不再在进程内保留该bytes，`pending`表示lease仍由session持有直至ACK；若未来sink在accepted后仍排队，必须显式接管同一lease，不能无账复制。本片同时删除production adapter中无消费者的 `ResponsesAnthropicStreamState.batches`累计，否则计数释放早于真实引用。测试专用 `InMemoryDeliverySink`未传account，继续保留其观测用bytes。
- 若 writer在返回 outcome前抛异常，释放刚取得的 rendered lease；semantic lease仍归 session cleanup，不能因 render／write失败双重释放。

首片不修改 parser delta append，因此它实现的是 **charge-before-delivery-retain／write**，不是 Spec 最终要求的 charge-before-upstream-read。文档、commit message与测试名都必须保持这一限定。

## 最小改动 paths

建议恰好 4 个 path：

1. `src/app/delivery/reservation.py`：新增 `ResidentByteBudget`、带request capacity的 `RequestResidentAccount`、`ResidentLease`与带 `request|global` scope的 `ResidentCapacityError`；只依赖 `asyncio.Condition`和标准类型。
2. `src/app/delivery/anthropic_sse.py`：给 `DeliverySession`增加可选 account、completed／rendered owner lease、只读 request current／high-water代理以及幂等 `aclose()`；不改 renderer、frontier或sink outcome的产品语义。
3. `src/app/delivery/responses_anthropic_stream.py`：删除无生产消费者的 `ResponsesAnthropicStreamState.batches`与accepted后的append，使 `_BufferedSink.drain()`＋ACK后不再保留rendered bytes；仍不创建production budget或改route接线。
4. `tests/smoke/test_anthropic_block_delivery.py`：增加下面两个并发判别测试；复用现有 paused／pending sink，不新建 quota harness。

`src/app/delivery/__init__.py` 可以暂不 re-export新 primitive，测试直接从窄模块 import。route、settings、metrics、History和parser本片均不改。

## happy path

1. 测试创建一个共享 `ResidentByteBudget`、一个capacity足以容纳本次semantic＋rendered重叠的 `RequestResidentAccount`，以及使用discarding accepted sink的 `DeliverySession`。
2. 完整 `CompletedBlock`进入 session前取得 semantic lease；render前再取得 rendered lease；writer明确不保留bytes并返回accepted后，rendered lease释放，semantic lease继续准确反映 frontier／History仍持有payload。
3. 测试形成自包含投影后调用 `aclose()`，semantic lease释放；request与global current回到零，高水位保留。
4. 没有容量压力时，下游事件序列、commit frontier、single writer和terminal行为与 current main完全相同；reservation只增加await边界与观测计数，不改变semantic ordering。

## 一个 backpressure 失败机制

唯一纳入本片的失败机制是 **等待中的 delivery reservation 被 cancel**：

- request A通过同一shared budget的显式holder lease占满capacity后，request B在 `await reserve_many(...)`挂起；B不得修改sequencer、进入writer或推进frontier，调用者也不会读取下一事件。
- 取消B的task时，`asyncio.CancelledError`原样传播；由于谓词未成功，B的request current保持零、global current仍只包含A，不生成partial batch，也不把取消包装成capacity success。
- 随后显式释放A的holder lease，global current回零。该机制证明真实backpressure await可取消且不泄漏，但**不**在本片决定route应将deadline／cancel映射成哪一种Anthropic error、History reason或metric label。

request aggregate超过request capacity，或单次／整组charge超过shared global capacity时，由 `ResidentCapacityError`立即失败，作为防自死锁／永久等待的primitive guard；它不是新的per-block产品阈值，因为同一aggregate公式对所有owner和大小统一适用。

## 新测试

### 1. `test_shared_resident_budget_backpressures_second_delivery_until_release`

- request A先从shared budget取得一个普通holder lease，只留下不足以容纳B semantic charge的余量；capacity与payload按测试实际bytes计算，不使用 `16 MiB`或具名“大 block”fixture。
- B启动 `deliver()`后停在semantic reserve，断言B writer无batch、B sequencer／frontier未推进、global current不超过capacity。
- 释放A holder lease后，B继续完成；B形成投影并 `aclose()`，断言request与global current回零、high-water符合owner之和，事件顺序与现有happy path一致。
- 该测试防 false-red：capacity恢复后普通block必须继续，而不是永久poison budget或进入专门overflow状态。

### 2. `test_cancelled_reservation_wait_does_not_charge_or_leak`

- A以显式holder lease占用capacity，B以一个包含两个completed blocks的 `consume()`等待同一 `reserve_many()`；确认B task尚未完成后取消它。
- 断言B收到 `CancelledError`、B current为零、global current未增加、B sink、sequencer与frontier均为空，证明整组charge和sequencer mutation没有留下半步状态。
- 释放A holder后global current为零；B重复 `aclose()`不改变计数。紧邻子例再让B的两个block总charge超过request capacity，断言立即得到scope为request的 `ResidentCapacityError`且sequencer仍为空；另对裸lease的重复 `release()`断言programming error，区分“session cleanup幂等”与“owner不得double release”。

现有 `tests/smoke/test_anthropic_block_delivery.py` 全部测试继续通过，确保无 account调用者不回归。此片不增加 route／ASGI E2E，因为 production budget与cleanup尚未接线；新增E2E会把未实现范围伪装成产品覆盖。

## 后续接线边界

以下全部保留，但不进入本片：

1. **parser drafts**：在每个 SSE payload进入 draft list／authoritative value前做增量 charge，retry reset／parse failure／cancel时释放；这是实现 charge-before-read的关键下一片。
2. **production request identity与cleanup**：由唯一 pipeline／route lifecycle owner创建 account；在 History自包含投影完成后调用 `DeliverySession.aclose()`，覆盖 success、conversion error、sink uncertain、client cancel与shutdown。
3. **真正共享的进程budget与配置**：从application lifespan创建单实例并注入Responses bridge；把global与per-request capacity接入显式settings／依赖注入，禁止module hidden singleton和硬编码阈值。
4. **有限 completed queue**：在 byte budget之外增加普通 block-count／queue-depth bound；不得把 byte budget冒充item count限制。
5. **其他 resident owner**：carrier、parser draft、预渲染envelope、History handoff job和必要的 transport queue逐项绑定owner；先确认对象何时不再被任何生产 owner持有，再 release。
6. **观测与产品错误映射**：request／global current与high-water、wait time、capacity failure进入既有 metrics／History facts；deadline、cancel、shutdown与admission rejection映射为稳定终态。
7. **admission**：只有global runtime配置与lifecycle owner存在后，才在新 bridge request进入upstream前拒绝新admission；本片不设计physical OOM恢复、victim selection、spill或全route quota。
8. **早释放优化**：若要在 request finalize前释放 committed semantic payload，必须先把 History所需字段压成自包含 immutable projection并清除 frontier／scheduled中的payload引用；不能只减counter而保留原对象。

## 不采纳的替代方案

- **逐 byte `Semaphore.acquire()`／AnyIO token循环**：非原子、可能部分占用后死锁，且开销随payload bytes增长。
- **只给 `_BufferedSink`计数**：漏掉parser／sequencer／frontier semantic payload，并在 semantic与rendered双份驻留期间系统性低估。
- **ACK即释放全部block charge**：current frontier与History仍保留semantic block，属于提前release。
- **本片直接加settings／global singleton／route admission**：在owner cleanup和parser draft尚未接好时只会产生配置名与假背压，扩大为半套quota系统；constructor capacity足以验证primitive，不等于production policy已经选择。
- **overflow flush、live forwarding或disk spill**：直接违反冻结Spec。

## 合并判据与退出声明

本片可以合并的条件只有：共享weighted reservation原子、不超卖；request-local计数与owner lease一致；正常delivery不变；容量等待真实阻塞第二session；取消waiter不charge、不写sink、不推进frontier；session cleanup后计数归零；现有block-delivery测试无回归。

通过后只能声明：**DeliverySession completed semantic payload与pending rendered batch已有opt-in两级resident reservation primitive、request capacity／可取消global backpressure单测，且production adapter不再无界累计已ACK batch副本。** 不得声明production-configured request／global quota、parser charge-before-read、有限queue、route admission、metrics／History终态、完整 `REL-06`或完整bridge quota已经完成。
