# Anthropic Responses bridge acceptance 独立复评 R3

- **评审范围**：current `docs/agents/anthropic-responses-bridge/acceptance.md`，仅逐项复核 R2 的 `R2-M1` 与 `R2-M2`，并检查修订引入的新矛盾。行为 expected 以内容哈希绑定的 `spec.md` 为 oracle；官方 Anthropic 文档仅用于校准公开协议语义，不能覆盖项目已冻结的更严格 producer 合同。
- **总体 verdict**：**修复 major 后可进入下一阶段**。`REL-06` 的普通 per-request aggregate gate 已闭合；`CAL-04` 的来源与 fixture 声明已闭合，但内嵌 grammar 仍接受冻结 Spec 禁止的多个 `message_delta` 与过早 `ping`，因此 acceptance 暂不能定稿为最终 oracle。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：2。
- **基线证据**：每次 shell 调用均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。复评时 current `acceptance.md` SHA-256 为 `6eaf6007edf1213a9c7c59f203f3f42d644e1c9e70ba985083a0885973324c26`；其声明的 Spec、Architecture、首轮报告与 R2 报告 SHA-256 均与实际文件一致。
- **实现状态边界**：候选 bridge 实现仍为 **`UNVERIFIED`**。本报告只裁定 acceptance oracle 文档，未运行实现 gate，绝不把文档修订或 current main 上的局部 helper 误写成产品通过。

## 双视角覆盖证据

- **机械核对**：核验 current 文档与 R2 两项发现逐条对应；计算并对账五份输入文件哈希；用精确路径、同义文件名扫描、Git 索引和工作树状态共同确认规划 fixture 不存在；将 `CAL-04-GRAMMAR-v1` 与 Anthropic 官方 Streaming Messages、Thinking、Versioning 和 fine-grained tool streaming 文档对账；扫描 acceptance 中全部 `16 MiB`／single-block／per-block 语义；逐项清点 request/global current bytes、high-water mark、charge、release、owner、History 移交、retry reset、failure、cancel、shutdown与跨请求隔离判据。
- **第一人称执行模拟**：模拟测试作者从内嵌表生成五类最小正向 feed及其 ping 变体，再逐项生成负向 fixture与 oracle 放宽 mutation；实际构造“两次 `message_delta` 后一次 `message_stop`”“`message_start` 前发送 `ping`”和“open block 中发送 `ping`”三条反例，确认 CAL-04 会接受而冻结 Spec 会拒绝。另模拟两个并发请求在 `0 < request_budget < global_budget` 下增长多个普通 block／owner、等待、downstream drain、History ownership transfer、capacity failure、cancel与shutdown，检查计账是否超卖、双计费、提前释放或错误阻塞另一请求。

## R2 两项逐条结论

| R2 ID | R3 结论 | 复核依据 |
|---|---|---|
| `R2-M1` CAL-04 缺冻结来源／资产 | **部分关闭，仍有 1 major** | `acceptance.md:316-333` 已内嵌版本化 grammar、绑定官方来源与协议版本、列出五类最小正样本、单缺陷负样本及 oracle 放宽 mutation。规划 fixture 精确路径 `tests/fixtures/anthropic_responses_bridge/anthropic-sse-grammar-v1.json` 在文件系统、Git 索引及同义命名扫描中均不存在，故“尚不存在”声明诚实。但 grammar 的 `message_delta` 基数和 `ping` 可见时点均与冻结 Spec 冲突，详见事实性发现 1。 |
| `R2-M2` 缺普通 per-request aggregate gate | **已关闭** | `acceptance.md:223-228` 以配置化 `request_budget < global_budget`、多个均明显小于 request budget 的普通 blocks 和多个 resident owners 验证 request aggregate；同时验证 request/global current 与 high-water、charge-before-read、wait/resume、History 移交、无双计费／提前 release、所有终止路径释放以及另一请求隔离。两种相反变异分别捕获 global-only 与 single-block／16 MiB 特例。全文没有把 16 MiB 设为正向 fixture 类别、metric 阈值或产品状态分支。 |

## 事实性发现

### 1. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:320,325-331` — CAL-04 允许多个 `message_delta` 及过早 `ping`，与冻结 Spec 的 producer／commit 合同冲突

**问题**：`CAL-04-GRAMMAR-v1` 将 message 尾部定义为“一个或多个 `message_delta`”，而行为 oracle `spec.md:266` 明确规定 bridge 在所有 blocks 后“至多一个 `message_delta`”。同一表还允许 `message_start` 前及任一未终止状态出现 `ping`，并要求每类正向 fixture 都有插入多个 `ping` 的变体；但 `spec.md:263,433,505` 冻结首个完整 block 前零 body event，且 heartbeat／keepalive 不得穿过尚未完成的 block。官方 Streaming Messages 文档允许多个 `message_delta` 和在流中分散 `ping`，但 CAL-04 自称 bridge 的 strict producer oracle，项目冻结 Spec 比公开协议 consumer 合同更严格时必须服从 Spec，不能把“官方 consumer 可接受”放宽成“bridge producer 可生成”。

**证据或失败场景**：按当前表生成 `message_start → message_delta(stop_reason) → message_delta(usage) → message_stop`，CAL-04 状态机合法通过；按 `spec.md:266`，同一输出违反至多一次 terminal delta。类似地，`ping → message_start → …` 与 `content_block_start → ping → content_block_delta → …` 也会被表判绿，却分别泄漏首 block 前 body event、让 heartbeat 穿过未完成 block，并可能使实现者误判透明 retry frontier。内存控制探针还确认 CAL-04 的负向清单有 `duplicate terminal`，却没有 duplicate `message_delta`、pre-start `ping` 或 open-block `ping`；因此现有 oracle 放宽 mutation 不会证明这些分支能区分正确与错误。执行者可据 CAL-04 写出全绿 strict tests，同时让产品输出冻结合同禁止的 wire。

**修复建议**：把 v1 尾部收紧为“恰好一个 `message_delta`，随后恰好一个 `message_stop`”；若 error 路径另行终止则不产生二者。把 `ping` 的合法位置收紧为冻结 commit 合同允许的边界：不得出现在首个完整 block batch之前，也不得穿过 open／尚未完成 block；正向 ping 变体必须写明插入点。增加 duplicate `message_delta`、pre-start `ping` 与 open-block `ping` 三类单缺陷负向 fixture，并分别放宽 oracle 对应约束，确认原负向 fixture转绿、外层 mutation gate因非法 feed 被接受而红。修订后重新核对五类正样本及合法 ping 变体仍绿，避免修成 false-red。

### 2. [minor] `docs/agents/anthropic-responses-bridge/acceptance.md:6` — “仓库 HEAD”当前状态声明已经陈旧

**问题**：文档声称仓库 HEAD 为 `47d9ef101c4b81ac70d805b1da157b34d021d33d`，并称该值由同一次 shell gate 取得；本轮每次独立 gate 均得到 current `main` HEAD `ed77c9d191df81c451c25161420515cca52ce6a4`。`implementation.md:6` 也记录后者为当前事实。

**证据或失败场景**：执行者按 acceptance 的旧 HEAD 重建“当前实现映射”会落到 reasoning squash 之前的树，与文档后部声称读取“当前实现”的语义不一致。行为 expected 已由 Spec 内容哈希绑定，故该问题不改变 gate 结果，定为 minor 而非 major。

**修复建议**：把该字段明确拆成“oracle 编写基线”与“本次 current-state 复核 HEAD”，或更新为 current main HEAD并记录 acceptance 内容哈希；不要继续把历史基线写成当前 shell gate 结果。

### 3. [minor] `docs/agents/anthropic-responses-bridge/acceptance.md:7` — 状态摘要仍写成容量“只走 global reservation”，与已补的 request aggregate gate 措辞相冲

**问题**：开头摘要称容量“只走普通 global reservation／backpressure”，而 `REL-06` 和 `spec.md` 的 Limits 已明确同时要求普通 per-request buffered bytes 与 global buffered bytes。后文详细 gate和处置表足够清楚，R2-M2 因而可关闭，但第一屏摘要仍会让执行者误以为 per-request aggregate 是超出用户裁决的新政策。

**证据或失败场景**：按摘要实现 global-only 会被 `REL-06` 的第一种缺陷注入正确打红；这说明详细 gate 判别力足够，但文档自身给出了互相竞争的执行指令。

**修复建议**：将摘要改为“容量只走普通 per-request aggregate＋global reservation／backpressure，不设 16 MiB 专门阈值”，与 `REL-06` 及处置表统一。

## 主观建议

无。本轮未引入新产品范围；发现均为可由冻结 Spec、文件系统或确定性反例裁定的事实问题。

## 最终结论

`R2-M2` 已完整关闭：普通 aggregate bytes gate 覆盖两级计账、owner transfer、释放、等待恢复和跨请求隔离，并且没有 16 MiB 特例。`R2-M1` 的外部来源绑定、内嵌表、fixture 不存在声明和大部分正反控制已经补齐，但 `message_delta` 基数与 `ping` 可见时点仍让冻结合同禁止的状态通过，因此本轮不能给出 0 major，也不能宣布 acceptance oracle 定稿。

**修复事实性发现 1 并复评为 blocker 0、major 0 后，oracle 文档可定稿；无论届时文档是否定稿，bridge 候选实现仍必须保持 `UNVERIFIED`，直到所有 required implementation gates 取得可复现实证。**
