# 全局内存预算删除后的文档残留审计（260820）

审计对象：`/home/xp/src/ghc-api-proxy-py/docs/` 全树。代码事实基线：`src/app/delivery/reservation.py` 已删除；`src/app/server/admission.py` 定义 `InFlightLimit`（等待，不拒绝、不 429、不断连）；`src/app/config/schema.py:150` `max_inflight: int = Field(default=50, ge=0)`，`schema.py:301` 挂载 `proactive_rate_limiter`；`schema.py:192` `buffer_cap_bytes` 仍在（用户明确保留，不在本审计范围）。

**LIVE-STALE 命中总数：56 行，分布在 7 个 live 文档。**其中 spec.md 与 acceptance.md 是冻结的对外合同（`FINALIZED@4c9beed…` / `FINALIZED_ACCEPTANCE_ORACLE@f99492a…`），改动它们等于改冻结合同，需要主会话向用户确认「本次裁决同时解冻并修订这两份」——我把替换文本写出来，但不建议在没有那句确认的情况下落笔。

## 一、LIVE-STALE 清单（按可执行性排序）

### A. `docs/agents/anthropic-responses-bridge/spec.md`（17 行，冻结合同，规范性最强）

| line | 现文（节选） | 建议替换 |
|---|---|---|
| 8 | 「buffer 与 carrier 是普通内存对象，统一服从**全局内存预算**、准入与背压，不 spill」 | 「buffer 与 carrier 是普通内存对象，服从 per-request `client_delivery.buffer_cap_bytes` 与在途请求数上限（`proactive_rate_limiter.max_inflight`）带来的背压，不 spill」 |
| 23 | 「**内存**、队列、并发、时间与 upstream frame 均有边界」 | 「单请求缓冲、队列、并发、时间与 upstream frame 均有边界」——删「内存」，进程级内存边界已不存在 |
| 249 | 「所有 carrier bytes 仍作为普通对象进入既有 request／**global memory budget**」 | 「所有 carrier bytes 仍作为普通对象计入该请求的 `buffer_cap_bytes`」 |
| 453 | 「HTTP SSE reader在队列／**budget**耗尽时暂停读取」 | 「HTTP SSE reader 在队列耗尽时暂停读取」 |
| 454 | 「总**resident bytes**／block count受请求级观测与**全局budget**约束」 | 「block count 受有界 queue 约束，累计缓冲字节受 `buffer_cap_bytes` 约束」 |
| 460 | 整条「所有 bridge resident bytes 与队列项统一进入现有的请求级观测和进程级**全局内存预算**。达到全局压力线后，普通 admission control 与有界队列**必须停止新准入**…」 | 整条删除，换为：「进程级并发由 `proactive_rate_limiter.max_inflight` 约束：超过上限的请求在 ASGI 层等待信号量，不被拒绝、不返回 429、连接不关闭。单请求累计缓冲字节由 `buffer_cap_bytes` 约束。」 |
| 461 | 「若**全局内存压力**在 request deadline 前解除，则继续组装原 block；若…**普通全局容量政策**使请求无法继续，则产生对应的 capacity／timeout／abort 终态」 | 删掉全局内存压力分支，保留 deadline／cancel／shutdown 分支：「若 deadline、cancel 或 shutdown 使请求无法继续，则产生对应的 timeout／abort 终态。」 |
| 462 | 「不得通过**超卖全局预算**、无限等待、磁盘 spill 或 live forwarding 绕过压力。**并发准入**…可以各有普通 hard limit」 | 「不得通过磁盘 spill 或 live forwarding 绕过压力。并发准入是等待式的，等待本身即为设计（见 `src/app/server/admission.py`）；queue depth 与 upstream frame limit 各有 hard limit。」注意原句「无限等待」被禁止，而新机制正是无超时等待——这一句必须改，否则与实现直接冲突 |
| 463 | 「每次**内存 charge／release** 必须绑定 request、attempt 和 buffer owner并恰好一次…记账必须回到实际 **resident 值**」 | 整条删除（charge/release 记账层已随 `reservation.py` 消失）；若要保留「配额等待必须响应 client cancel 与 shutdown」的意图，改写为对 `max_inflight` 信号量等待的要求 |
| 467 | limit 类别清单含「**per-request buffered bytes、global buffered bytes**…**并发bridge数**」 | 删「global buffered bytes」；「并发bridge数」必须移出 limit 清单（见 Q3，它现在不是 limit violation 而是等待），保留「per-request buffered bytes」 |
| 496 | 「steady-state memory由**已声明budget**限定，不随response总长度无界增长」 | 「steady-state memory 由 `buffer_cap_bytes` 与在途请求数上限共同限定」 |
| 499 | 「所有未提交block、carrier与completed queue均作为普通内存对象受**全局resident budget**记账」 | 「…作为普通内存对象受该请求的 `buffer_cap_bytes` 约束；不存在进程级字节记账」 |
| 504 | 可观测项含「**request resident bytes、global resident bytes、quota wait**／capacity failure」 | 删这三项，若需要替代可观测项则为「in-flight request count、admission wait time」 |
| 516 | 「性能优化不得放宽 buffering、**global quota**、no-dup或no-loss不变量」 | 删「global quota」 |
| 537 | 冻结轴清单含「buffer 与 carrier 作为普通内存对象统一服从**全局 budget** 和背压」 | 改为「…服从 per-request buffer cap 和背压」 |
| 548 | 「与一般 **memory-only／全局背压合同**冲突，排除；**普通 global budget**、deadline 或 cancel 仍可产生对应明确终态」 | 保留「排除 spill／live forwarding」的结论，删掉 global budget 作为终态来源：「…deadline 或 cancel 仍可产生对应明确终态」 |
| 567 | 「bridge必须把in-flight attempt／memory buffer与**global quota charge**纳入同一lifecycle」 | 「bridge 必须把 in-flight attempt 与 memory buffer 纳入同一 lifecycle」 |

### B. `docs/agents/anthropic-responses-bridge/architecture.md`（13 行）

| line | 现文（节选） | 建议替换 |
|---|---|---|
| 66 | 「由普通**全局 reservation**、有限队列与 backpressure 控制…**全局 reservation 暂不可得时停止继续读取 upstream**；若实际全局内存耗尽，当前最小止血是**拒绝新的 bridge admission**」 | 删除全局 reservation 与「拒绝新 admission」两句，保留「不得退化为 live forwarding、不落盘」，并改述为：「并发由 `max_inflight` 信号量约束，超限请求等待而非被拒绝。」 |
| 395 | 「通过 request reservation、**全局 memory reservation**、有限 completed-block queue 与上下游背压约束 **resident memory**」 | 「通过 `buffer_cap_bytes`、有限 completed-block queue 与上下游背压约束内存」 |
| 409 | 「接收 frame／扩展 draft 前增量申请**全局 reservation**；申请暂不可用时停止继续读取 upstream…**Reservation 必须按实际 resident bytes 记账并具备原子 acquire／release**」 | 整段重写：删掉 reservation 申请／记账，保留「有限 queue 的背压沿 await 链传播」 |
| 411 | 整段「**Global budget** 是所有 bridge requests 共用的 **resident-memory admission 水位**…可观测性保留**全局 resident／reserved bytes、reservation wait**、queue depth 和 admission rejection」 | 整段删除。替换段落应描述 `InFlightLimit`：ASGI 层信号量、按请求而非连接计数、0 表示禁用、超限等待 |
| 413 | 整段「若实际**全局内存已经耗尽**，当前推荐只做最小止血：**拒绝新的 bridge admission**…**admission rejection 必须发生在可控的 allocator failure 之前**」 | 整段删除 |
| 455 | 表格行「**全局 memory reservation 持续不可得** \| 保持现有 frontier \| …**实际全局内存耗尽时拒绝新的 bridge admission**」 | 删除该表行 |
| 490 | 「为避免大 response 在异步 writer queue 中逃逸**全局内存记账**，projection 连同覆盖其 **resident bytes 的 reservation token** 一起移交；History queue 必须同时按 job 数与 **reserved bytes** 有界」 | 删掉 reservation token 移交语义（`ResidentLease` 已不存在），改为「History queue 按 job 数有界」，其余 ownership／receipt 语义保留 |
| 515 | 「所有 request admission 与 draft 增长共用 **resident-byte reservation**…**实际全局内存耗尽时新 admission 被拒绝**」 | 删除该条测试意图 |
| 547 | 「**最小止血：** 实际全局内存耗尽时**拒绝新的 bridge admission**」 | 删除该条 |
| 655 | ADR 表 U1 行「只保留普通 **global reservation／backpressure**，**实际全局内存耗尽时最小止血为拒绝新 admission**」 | 这是一条 ADR 处置记录。**不要原地改写**，追加一行新 ADR 记录 2026-08-19 的裁决覆盖它（内存预算删除、改为 `max_inflight` 等待式并发上限），并在 U1 行标注「已被后续裁决覆盖」 |
| 668 | 「普通路径只有一套机制：admission 与 draft 增长按实际 **resident bytes** 申请 **global reservation**…取消、既有 deadline、完成或失败负责**释放 reservation**」 | 整段删除 |
| 670 | 「**实际全局内存耗尽时，当前推荐的最小止血仅是拒绝新的 bridge admission**…」 | 整段删除 |
| 678 | 「这一路径与用户关于…**普通全局内存 admission／backpressure**、block buffering／no live downstream 的裁决一致…**若低概率全局容量事件需要超出「拒绝新 admission」的全面设计，必须先征询用户**」 | 删掉「普通全局内存 admission／backpressure」与末句 |

### C. `docs/agents/anthropic-responses-bridge/acceptance.md`（6 行，冻结 oracle）

| line | 问题 | 建议 |
|---|---|---|
| 41 | 一致性表 `limits` 行：「`REL-06`固定普通per-request aggregate＋**global resident reservation**、有限queue、**charge-before-read**、**两级可观测计账**、capacity／deadline／cancel终态与**拒绝新admission最小止血**」 | 整行重写：只保留 per-request `buffer_cap_bytes`、有限 queue、deadline／cancel 终态；删掉 global reservation、charge-before-read、两级计账、拒绝新 admission |
| 241 | 小节标题「### REL-06 backpressure、有限队列与**全局 resident quota**」 | 「### REL-06 backpressure 与有限队列」 |
| 243 | 整条正确样本：「…同时进入普通per-request aggregate reservation和**global reservation／resident计账**，charge／release绑定request、attempt与owner且恰好一次。测试配置满足 `0 < request_budget < global_budget`…**实际全局内存压力达到已决拒绝条件时只拒绝新的bridge admission**」 | 整条重写。`request_budget`／`global_budget` 两个配置键都已不存在；`0 < request_budget < global_budget` 这个前置条件在当前代码里不可满足，该验收样本现在**不可执行**。保留的部分只有：慢 downstream + 有限 queue 导致生产者被背压、不提交 partial block、已提交前缀不重复 |
| 246 | 通过判据「per-request current bytes等于该request所有 **resident owner** 之和，**global current bytes** 等于所有request及共享bridge resident owner之和…**两级计账回到实际resident值**」 | 删掉两级计账判据 |
| 418 | R2-M2 处置行「REL-06新增配置化**request/global两级预算**…」 | 同 architecture.md:655 处理：不原地改写，追加覆盖记录 |
| 438 | 「REL-06同时验证Spec已冻结的普通 **per-request aggregate buffered-bytes 预算**；该预算跨多个 **resident owner** 聚合」 | 改为只针对 `buffer_cap_bytes` 的单一 per-request cap，删掉「跨多个 resident owner 聚合」 |

### D. `docs/agents/anthropic-responses-bridge/research.md`（4 行）

- `research.md:16`：「buffer 与 carrier…统一服从普通 per-request aggregate、**全局 reservation**、准入与背压…对**实际全局内存耗尽**这一夸张小概率事件，当前只做**拒绝新 bridge admission** 的最小止血」→ 删掉全局 reservation 与整个「全局内存耗尽 → 拒绝新 admission」的止血论述。
- `research.md:123`：同上措辞，「buffer 只走普通 per-request aggregate、**全局 reservation**、准入与背压；**实际全局内存耗尽时仅拒绝新 bridge admission**」→ 同上处理。
- `research.md:193`：「buffer 与 carrier 只服从普通 per-request aggregate、**全局 reservation**、准入、backpressure 与取消清理。**实际全局内存耗尽这一夸张小概率事件只做拒绝新 bridge admission 的最小止血**」→ 同上处理。
- `research.md:208`：R2 处置行「改为普通**内存预算**／准入／背压、**实际全局耗尽时拒绝新 admission** 的最小止血」→ 处置记录，追加覆盖标注而非原地改写。

### E. `docs/agents/anthropic-responses-bridge/implementation.md`（13 行）

这份是 `LIVING` 文档，问题分两类：

**E1 — 当前状态锚点已过期（必须改）**：`implementation.md:10`、`:14`、`:17`、`:86`、`:113`、`:250` 都把 `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62` 描述为 current main，且把「retry、**resident wiring**、Copilot identity」列为 current main 的内容。current HEAD 已推进过 `f5589ec`，且 resident wiring 的语义已被删除。建议：把锚点更新到当前 HEAD，并把「resident wiring」从 current main 内容清单中移除，改列「in-flight 并发上限（`InFlightLimit`）」。

**E2 — 已收敛切片行与「下一步」（必须改）**：
- `:40`、`:41`、`:81`、`:82`、`:105`、`:106`：四行分别记录「Resident-byte最小primitive」与「Production stream resident wiring」两片已进入 main 并归档，遗留项写「完整quota其他owner、parser drafts、有限queue、admission、metrics／History映射仍未完成」。建议：保留切片行作为历史 provenance（archive ref 与 main commit 都是真实存在的不可变事实），但在每行**遗留项**一栏改写为「**已于 2026-08-19 按用户裁决整体删除，由 `proactive_rate_limiter.max_inflight` 的等待式在途上限取代（`src/app/server/admission.py`，`f5589ec`）**」，并删掉「完整 quota 仍未完成」这类把删掉的东西写成待办的措辞。
- `:260`：「**下一核心边界继续分片闭合**：优先补完整quota／backpressure，覆盖 **resident owner、有限queue、admission、metrics／History映射**」——这是把已删机制写成下一步计划，最容易误导接手者。建议整条删除 resident/quota 部分，只保留「真实 loopback sink 闭合 kernel partial-write」那半句。

（`implementation.md` 的 `:12`、`:80`、`:232`、`:235`、`:242` 只出现 `archive/260807-resident-byte-budget@8fb6a97…` / `archive/260807-resident-budget-wiring@aa5f1d3…` 这类 archive ref 名字。分支名是不可变历史标识，**不属于 LIVE-STALE，不要改**。）

### F. `docs/agents/service-cutover/readiness.md`（2 行）

- `:53`：「current `main@fb4272b…`已包含network retry、**resident wiring**及token／response／item identity fixes」→ 删掉「resident wiring」，或改写为「该 commit 曾包含 resident wiring，该机制已于 2026-08-19 删除」。
- `:56`：整行是最严重的一条。行标题「Block-level buffering／**delivery frontier／resident budgets**与backpressure」，状态 `UNVERIFIED`，正文「由 `REL-06` 冻结普通 per-request aggregate＋**global resident reservation**…配置默认 `0／0` 保持既有行为」，组件列写着 `runtime/memory-quota`＋`pipeline/admission`，下一步写「先闭合完整quota／backpressure的其他owner…」。建议：行标题去掉 resident budgets；正文删掉 reservation 与 `0／0` 默认；组件列删 `runtime/memory-quota`；下一步只保留真实 loopback sink 那部分。

### G. `docs/agents/service-cutover/plan.md`（1 行）

- `:9`：「Current main已线性包含 foundations、systemd runtime、bridge主路径、retry／**resident wiring**、Copilot identity…」→ 删掉「／resident wiring」。

## 二、Q1—Q4

### Q1. `spec.md` 中要求全局内存预算的规范性条款

**有，10 条带 `必须`／`不得`／`不得…绕过` 的强制条款。**逐条（引文见上表同行）：

- `spec.md:8` —— 「已裁决且不可重开」段：「buffer 与 carrier 是普通内存对象，统一服从**全局内存预算**、准入与背压」。这是被标为「不可重开」的裁决项，现已被 2026-08-19 裁决推翻。
- `spec.md:23` —— 「**内存**、队列、并发、时间与 upstream frame 均有边界」。
- `spec.md:249` —— 「所有 carrier bytes **仍作为普通对象进入**既有 request／global memory budget。Malformed／unknown **不得**绕过 size、cancel、deadline 或 cleanup 合同」。
- `spec.md:453` —— 「HTTP SSE reader在队列／budget耗尽时暂停读取；upstream WS receive queue**必须**有界」。
- `spec.md:454` —— 「总resident bytes／block count**受**请求级观测与全局budget**约束**」。
- `spec.md:460` —— 「达到全局压力线后，普通 admission control 与有界队列**必须**停止新准入或暂停可暂停的 HTTP／WS upstream读取」。
- `spec.md:462` —— 「**不得**通过超卖全局预算、**无限等待**、磁盘 spill 或 live forwarding 绕过压力」。
- `spec.md:463` —— 「每次内存 charge／release **必须**绑定 request、attempt 和 buffer owner并**恰好一次**；…记账**必须**回到实际 resident 值」。
- `spec.md:467` —— 「**必须存在并可观测**的限制类别包括：…global buffered bytes…并发bridge数」。
- `spec.md:516` —— 「性能优化**不得**放宽 buffering、**global quota**、no-dup或no-loss不变量」。
- `spec.md:537` —— 冻结轴：「buffer 与 carrier 作为普通内存对象统一服从**全局 budget** 和背压」，明文「**不得在实施计划中重新开放**」。
- `spec.md:567` —— 「bridge**必须**把in-flight attempt／memory buffer与**global quota charge**纳入同一lifecycle」。

### Q2. 是否有 live 文档宣称存在「全局内存预算」概念

**有，四份**：`spec.md`（8、460、537 明文写「全局内存预算」「global budget」）、`architecture.md`（411「Global budget 是所有 bridge requests 共用的 resident-memory admission 水位」、395「全局 memory reservation」、515「普通全局内存门」）、`acceptance.md`（241 标题「全局 resident quota」、243「global reservation／resident计账」）、`research.md`（16／123／193「全局 reservation」）。此外 `readiness.md:56` 以行标题「resident budgets」把它登记为一条待验证的产品能力。

### Q3. 是否有 live 文档与「等待而非拒绝」矛盾——**有，而且这是本次审计里最需要先处理的一类**

新行为（`src/app/server/admission.py` 头部注释与实现）：超过 `max_inflight` 的请求在 ASGI 层 `asyncio.Semaphore` 上按到达顺序**等待**，不拒绝、不 429、不断连。下列 live 文档明文要求相反行为：

1. **`spec.md:460`**：「达到全局压力线后，普通 admission control 与有界队列**必须停止新准入**」——要求拒绝新准入。
2. **`spec.md:462`**：「**不得**通过超卖全局预算、**无限等待**、磁盘 spill 或 live forwarding 绕过压力」——明文禁止无限等待，而当前实现正是无超时等待。这是与代码最直接的字面冲突。
3. **`spec.md:467` + `:468-473`**：`并发bridge数` 被列为「必须存在并可观测的限制类别」，而 468-473 规定「所有 limit violation 都**必须**：在可能时于 upstream 调用前**拒绝**…**产生稳定的 Anthropic error、History 原因与 metrics label**」。按这份 spec，超过并发上限应当在调用上游前被拒绝并返回稳定 Anthropic error；实现改成了排队。必须把「并发bridge数」从 limit 清单移出，否则 spec 直接要求实现返回错误。
4. **`spec.md:461`**：容量压力产生「capacity 终态」。
5. **`architecture.md:413`／`:455`／`:547`／`:670`／`:678`**：反复写「实际全局内存耗尽时**拒绝新的 bridge admission**」，`:413` 还加了「**admission rejection 必须发生在可控的 allocator failure 之前**」。
6. **`acceptance.md:41`／`:243`**：验收 oracle 要求「拒绝新admission最小止血」并「产生稳定Anthropic **capacity／limit终态**」。这是一条会把正确实现判红的验收判据。
7. **`research.md:16`／`:123`／`:193`**：同样的「拒绝新 bridge admission」表述。

反向核对：没有任何 live 文档把下游客户端的 429 与并发上限挂钩。`docs/.human-controlled/config.example.yaml:354-355` 的 429 只指**上游**返回的 429 触发 reactive rate limiter，与本议题无关，不算矛盾。

### Q4. 是否已有 live 文档记录 `proactive_rate_limiter` / `max_inflight`

**只有一处，且在 human-controlled 目录**：`docs/.human-controlled/config.example.yaml:350-352`

```yaml
# # 主动式速率限制 / Proactive rate limiting
# proactive_rate_limiter:
#   max_inflight: 5
```

准确性评估：键名与层级与 `src/app/config/schema.py:301`／`:150` 一致，**结构正确**。三点值得报告，均不建议我去动这个文件：
- 整段被注释掉（`# #` 双井号），读起来像「尚未实现的规划项」，而它现在是已接线的生效配置。
- 示例值 `5` 与代码默认 `50`（`schema.py:150`）不同。示例值本可自选，但此处没有任何文字说明默认值，读者会把 5 当默认。
- 没有一个字说明**超限行为是等待**。这恰恰是最容易被误解的一点（同一文件 354 行紧接着谈 429），也是 `admission.py` 注释里花最大篇幅强调的设计意图。

除此之外，`docs/` 全树没有任何 live 文档描述 `max_inflight` 或 `InFlightLimit`。也就是说：**旧机制在四份 live 文档里被当作现存能力反复规范，新机制在 live 文档里一行都没有。**

## 三、FROZEN（不动）

- `docs/agents/anthropic-responses-bridge/archive-260808/README.md`、`archive-260808/evidence/current-main-real-copilot-path-review.md`（10 处 resident），`docs/agents/service-cutover/archive-260808/README.md`。冻结历史记录，保持原样。
- `docs/tmp/` 下 40 余份带 `resident`／`内存预算` 的报告，命中最密的是 `260807-next-reservation-slice.md`(28)、`260807-review-main-resident-budget.md`(15)、`260807-review-retry-living-checkpoint.md`(12)、`260807-review-resident-living-checkpoint.md`(12)、`260807-final-worktree-cleanup-plan.md`(12)、`260807-audit-resident-byte-budget-squash.md`(12)、`260807-review-resident-byte-budget{,-r2,-r3}.md`(各 10)、`260807-review-reservation-wiring-living.md`(8)、`260807-verify-resident-byte-budget.md`(6)。按项目约定「临时报告永不覆写」，全部视为历史记录，不动。

## 四、HUMAN-CONTROLLED

`docs/.human-controlled/` 对 `resident`／`ResidentByteBudget`／`global_resident_bytes`／`内存预算`／`全局内存`／`驻留`／`memory budget`／`byte budget` **零命中**——用户亲笔文档从未写入过这个机制。唯一相关的是 Q4 那三点关于 `max_inflight` 表述的建议，候选修订会是：解注释该段、标注默认值 50、并加一句「超过上限的请求排队等待，不会被拒绝或返回 429」。**我没有改动该目录任何文件，也不建议未经用户点头就改。**

## 五、OUT-OF-SCOPE

- `docs/2604-rewrite/streaming-resilience.md:220`（「单个请求可能在内存中**驻留**完整的响应缓冲区——按 `buffer_cap_bytes` 默认上限计算…16MB」）与 `:226`（「缓冲重试是本文档中唯一需要用户在开启前评估**内存预算**的机制」）：讲的是 `buffer_cap_bytes` 与缓冲重试的内存代价，两者都仍然成立。派发时已判定出范围，未复议。
- `docs/2604-rewrite/lib-survey/domain2-reliability.md:93`：「库本身贡献的价值（键淘汰／**内存管理**）在这里占比很小」——讲的是通用缓存库的选型，与本机制无关。
- `docs/2604-rewrite/history-system.md` 全部 `in-flight` 命中（43、373、482 等）：指 History 的「进行中请求内存映射」，与 `InFlightLimit` 只是同名，语义无关，不要顺手改。
- `docs/agents/deployment-systemd/README.md:93`（`MemoryHigh`／`MemoryMax` cgroup 限制）：cgroup 层内存限制，与应用内字节记账是两回事，仍然有效——顺带一提，用户裁决里「主动式限流器可以满足类似需求」与 `docs/.human-controlled/lifecycle.md:63`「要求使用单独的 cgroup 以限制 CPU 和内存用量」是一致的，进程内存的兜底本来就归 cgroup。
