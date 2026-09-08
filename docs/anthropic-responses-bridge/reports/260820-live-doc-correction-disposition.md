# Live 文档修正处置记录（260820）

**任务**：按 [`docs/tmp/260820-memory-budget-doc-references.md`](260820-memory-budget-doc-references.md) 的 B／D／E／F／G 四节，把五份 live 文档从「全局内存预算」机制对齐到当前代码事实。spec.md 与 acceptance.md 由主会话自行处理，本次未打开写入。

**对齐的代码事实**（未重新推导，仅按派发给定并抽样核对）：

- `src/app/delivery/reservation.py` 已删除（`546852a`），连同 `openai_responses.global_resident_bytes`／`request_resident_bytes` 两个配置键。工作树核对：文件 ABSENT。
- 替代物是 `src/app/server/admission.py` 的 `InFlightLimit`（`f5589ec`），配置 `proactive_rate_limiter.max_inflight`，默认 50（`src/app/config/schema.py:150`）。**超限请求在 `asyncio.Semaphore` 上按到达顺序等待**，不拒绝、不 429、不断连。
- `/health`、`/health/liveness`、`/health/readiness`、`/metrics` 豁免该上限（`7e9b62d`）。
- `client_delivery.buffer_cap_bytes` 保留。核对 `src/app/pipeline/delivery/blocks.py`：cap 由 `BlockBuffer._enforce_cap()` 在 block 被接纳**之前**按预计字节数检查，越限抛 `BufferCapExceeded` 并**放弃该 response**——它不是背压，本记录中所有相关改写都按此措辞，未写成「背压」。
- 三个 commit 均已核对为当前 HEAD 的祖先。**注意**：本次执行期间 HEAD 由 `7e9b62d` 前进到 `3e75654`（并行会话在写 `docs/.human-controlled/config.example.yaml` 的提案）。因此所有改写**只绑定 commit 短哈希，不写「current HEAD 是 X」**——那种写法当场就会再次过期。

---

## 一、`docs/agents/anthropic-responses-bridge/architecture.md`

报告 B 节列 13 行；实际改 24 处（13 行按报告，11 行为报告漏列，见第六节）。

### 按报告执行（13）

| 报告行号 | before（截断） | after（截断） |
|---|---|---|
| 66 | 「由普通全局 reservation…；全局 reservation 暂不可得时停止继续读取 upstream；若实际全局内存耗尽，当前最小止血是拒绝新的 bridge admission」 | 「由 per-request `client_delivery.buffer_cap_bytes`、有限队列与背压控制…越过 `buffer_cap_bytes` 时放弃该 response（`BufferCapExceeded`）…进程级只有在途请求数一道闸：超过 `max_inflight` 的请求按到达顺序等待，不被拒绝、不返回 429、连接不关闭」。保留「不得退化为 live forwarding」「不落盘」「扩张容量政策须先提交用户裁决」三条规则 |
| 395 | 「通过 request reservation、全局 memory reservation、有限 completed-block queue…约束 resident memory」 | 「通过 per-request `client_delivery.buffer_cap_bytes`、有限 completed-block queue 与上下游背压约束内存」 |
| 407（标题，报告未列，随段落一并改） | 「### 容量 reservation 与背压」 | 「### 容量约束与背压」 |
| 409 | 「接收 frame／扩展 draft 前增量申请全局 reservation…Reservation 必须按实际 resident bytes 记账并具备原子 acquire／release」 | 改述为 `buffer_cap_bytes` 的 admit-before 检查（点名 `src/app/pipeline/delivery/blocks.py`）＋有限 queue 背压；末句改为「不存在需要显式记账的字节配额」 |
| 411 | 「Global budget 是所有 bridge requests 共用的 resident-memory admission 水位…可观测性保留全局 resident／reserved bytes、reservation wait…admission rejection」 | 整段替换为 `InFlightLimit` 描述：ASGI 中间件、计请求数而非连接数、`0` 禁用、按到达顺序等待、健康与 metrics 路由豁免；可观测项改为在途请求数、admission 等待时长、queue depth |
| 413 | 「若实际全局内存已经耗尽…拒绝新的 bridge admission…admission rejection 必须发生在可控的 allocator failure 之前」 | **未整段删除**（报告建议删）。保留「不预先设计 spill／debt／阈值／victim selection」「不足时须先带压力证据征询用户」「不提交 partial block／不退化 live／不回退 frontier」三条规则，只换掉机制：改为在途上限＋buffer cap，真实内存耗尽由 cgroup 兜底；删掉与代码冲突的末句 |
| 454（报告未列，同表相邻行） | client abort 行「释放 memory reservation」 | 「释放 buffer 内存」 |
| 455 | 表行「全局 memory reservation 持续不可得 \| … \| 实际全局内存耗尽时拒绝新的 bridge admission」 | **未删行**（报告建议删）。改为「在途请求数已达 `max_inflight`」触发条件；「禁止」列**新增**「拒绝新请求、返回 429 或关闭其连接」，原有 spill／flush partial／切 live／扩张政策的禁止全部保留 |
| 490 | 「projection 连同覆盖其 resident bytes 的 reservation token 一起移交；History queue 必须同时按 job 数与 reserved bytes 有界…恰好一次释放 token」 | 删 token 移交语义，改「History queue 必须按 job 数有界」；ownership 的「恰好一次释放」全部保留，主语由 token 换成 projection |
| 515 | 「**普通全局内存门：** …共用 resident-byte reservation…实际全局内存耗尽时新 admission 被拒绝」 | **未删条**（报告建议删）。标题改「普通容量门」，机制换成 `buffer_cap_bytes`＋`max_inflight` 等待；原有「故意启用 spill／per-block threshold／overflow flush 应变红」保留，**新增**「对超限请求返回 429 或关闭连接同样应变红」 |
| 546／547（ADR-BRIDGE-03，报告只列 547） | 「已决边界：…普通 global reservation…」「最小止血：实际全局内存耗尽时拒绝新的 bridge admission」 | 按 (b) 处理：**不原地改写**，两条各加「（…已于 2026-08-19 被覆盖，见下）」标注，末尾追加一条 2026-08-19 裁决记录（列出 `546852a`／`f5589ec`／`7e9b62d` 与保留项）。547 的「用户门控」条只把「最小止血不足」改为「当前容量约束不足」，规则本身保留 |
| 655（ADR 表 U1 行） | 「只保留普通 global reservation／backpressure，实际全局内存耗尽时最小止血为拒绝新 admission」 | 按 (b) 处理：U1 行正文一字未动，处置列追加「本行的容量机制部分已于 2026-08-19 再次被覆盖，见 U3 行」；表尾**新增 U3 行**记录新裁决与复审证据要求 |
| 668／670 | 「admission 与 draft 增长按实际 resident bytes 申请 global reservation」「实际全局内存耗尽时…最小止血仅是拒绝新的 bridge admission」 | 改写为 per-request cap（admit-before 检查、越限放弃 response）＋进程级在途上限一道闸；「若这道闸不足，主会话必须先把压力形态与候选政策提交用户裁决」保留 |
| 678 | 「…普通全局内存 admission／backpressure…；若低概率全局容量事件需要超出「拒绝新 admission」的全面设计，必须先征询用户」 | 机制改为「等待式在途请求上限与 per-request buffer cap 带来的背压」；末句**未删**（报告建议删），改为「若在途上限与 per-request buffer cap 不足以覆盖真实容量压力，必须先征询用户」——删掉它等于删规则 |

### 与报告的分歧（已执行，理由如下）

报告对 413／455／515／547 都写「整段删除／删除该行」。这四处正文里各自挂着**仍然成立的禁令**（不 spill、不 flush partial block、不切 live、不回退 frontier、不自行扩张容量政策、不建 16 MiB 专属 fixture）。派发约束写明「Do not delete a rule and call it neutrality」，故一律改为「换机制、留规则」，并在 455／515 额外把新的错误做法（拒绝／429／断连）写成显式禁止，使这两处对新行为具备分辨力。

---

## 二、`docs/agents/anthropic-responses-bridge/research.md`

报告 D 节列 4 行，全部执行，无分歧。

| 报告行号 | before（截断） | after（截断） |
|---|---|---|
| 16 | 「统一服从普通 per-request aggregate、全局 reservation、准入与背压…对实际全局内存耗尽…只做拒绝新 bridge admission 的最小止血」 | 「服从 per-request `client_delivery.buffer_cap_bytes`、有界队列与背压…进程级只有等待式在途请求上限 `proactive_rate_limiter.max_inflight`，超限请求排队等待而不被拒绝」；「须先询问用户并取得裁决」保留 |
| 123 | 「buffer 只走普通 per-request aggregate、全局 reservation、准入与背压；实际全局内存耗尽时仅拒绝新 bridge admission」 | 同上措辞 |
| 193 | 「只服从普通 per-request aggregate、全局 reservation、准入、backpressure 与取消清理。实际全局内存耗尽…只做拒绝新 bridge admission 的最小止血」 | 同上措辞；「16 MiB 不是阈值」与「先询问用户」保留 |
| 208 | R2 处置行「改为普通内存预算／准入／背压、实际全局耗尽时拒绝新 admission 的最小止血」 | 按 (b) 处理：原行正文未动，处置列追加「其中的内存预算部分已于 2026-08-19 被覆盖，见下一行」；表尾新增一行 2026-08-19 处置记录 |

---

## 三、`docs/agents/anthropic-responses-bridge/implementation.md`

报告 E 节列 13 行（其中 archive ref 五处明确不动）。已改 13 行按报告 ＋ 11 行报告漏列（见第六节）。

### E1 当前状态锚点（报告行 10／14／17／86／113／250）

| 报告行号 | before（截断） | after（截断） |
|---|---|---|
| 10 | 「**当前…主树状态**：…retry、resident wiring、Copilot identity…均已线性进入 current `main@c1de6bf…`」 | 标题改「（2026-08-08 快照）」；保留切片进入 `c1de6bf` 的历史事实，追加「此后 `main` 已继续前进，`c1de6bf…` 不再是 current HEAD：resident wiring 已于 2026-08-19 删除（`546852a`），改由 `max_inflight` 承接（`f5589ec`），健康与 metrics 路由豁免（`7e9b62d`）」 |
| 14 | 「**当前完整产品边界**：…network retry、resident wiring、Copilot identity…；完整产品仍为 `UNVERIFIED`：…quota／backpressure…」 | 删 resident wiring 并注明已删除；open 清单里「quota／backpressure」改「buffer cap 与在途上限下的真实背压行为」 |
| 17 | 「…resident-byte 最小 primitive `29c0ce3…`、production stream resident wiring `941299f…`…均已依次进入 main…完整 quota／backpressure…仍未闭合」 | 两片 commit 事实保留（archive ref 保留其历史身份），追加「其中两片 resident 切片的机制已于 2026-08-19 删除（`546852a`）」；未闭合项同上改写 |
| 86 | 「…retry、resident wiring、identity fixes…进入 current `main@c1de6bf…`」 | 删 resident wiring 并括注已删除与替代物；未闭合项同上改写 |
| 113 | 「…network retry、resident wiring、Copilot identity…进入 current main」 | 同 86 |
| 250 | 「Current main 上的…network retry、resident wiring…；Current 锚点为 `main@c1de6bf…`」 | 删 resident wiring；锚点句改「2026-08-08 快照锚点为 `main@c1de6bf…`，`main` 其后已继续前进，两片 resident 切片的机制已由 `546852a` 删除」。revert 顺序规则、archive ref 不移动、不复用旧 candidate identity 全部保留 |

**未采纳报告的一处建议**：报告 E1 说「把锚点更新到当前 HEAD」。未照做——本次执行中 HEAD 就前进了一次（`7e9b62d` → `3e75654`），写死一个「current HEAD」会立刻再次成为同类缺陷。改为保留历史锚点＋声明其已非 current＋绑定三个不动的 commit 短哈希。同理，文档顶部第 6 行的「事实快照：2026-08-08 / HEAD c1de6bf」是一条自带日期的过程记录（含「本轮每次 shell 调用都在同一调用内验证…」），改写它等于伪造过程记录，故未动。

### E2 已收敛切片行与「下一步」（报告行 40／41／81／82／105／106／260）

| 报告行号 | before（遗留项列，截断） | after（截断） |
|---|---|---|
| 40 | 「完整 quota 其他 owner、parser drafts、有限 queue、admission、metrics／History 映射与真实 partial-write 仍未验证」 | 「该 resident-byte 记账已于 2026-08-19 按用户裁决整体删除（`reservation.py` 随 `546852a` 移除），由 `max_inflight` 的等待式在途上限取代（`f5589ec`）；quota 其他 owner、parser drafts、admission 与 metrics／History 映射不再是待办。有限 queue 与真实 partial-write 仍未验证」 |
| 41 | 「完整 quota 的其他 owner、parser drafts、有限 queue、admission 与 metrics／History 映射仍未完成」 | 同上句式，追加「该 wiring 与其两个配置键…随全局内存预算一并删除」；「有限 queue 仍未闭合」保留 |
| 81 | 「Production stream 接线已由下一片完成；不得把两片绿灯外推为完整 quota／backpressure…」 | 改为删除声明＋替代物；「真实 partial-write 与完整 Acceptance 继续独立取证」保留 |
| 82 | 「Token identity 后继已进入 current main；完整 quota 的其他 owner…仍未完成」 | 改为删除声明＋替代物 |
| 105 | 「Production stream wiring 后继已作为 `941299f…` 进入 main；完整 quota 其他 owner、parser drafts 与 metrics 继续保持未完成」 | 改为删除声明＋替代物；标题列加「（已收敛，机制其后被删除）」；「archive 保持 immutable」保留 |
| 106 | 「Token identity 后继已进入 current main；完整 quota 其他 owner、parser drafts 与 metrics 仍未完成」 | 同 105 |
| 260 | 「**下一核心边界继续分片闭合**：优先补完整 quota／backpressure，覆盖 resident owner、有限 queue、admission、metrics／History 映射；随后用真实 loopback sink 闭合 kernel partial-write…」 | 只保留 loopback sink／kernel partial-write 那半句作为下一步，并显式写明「原列的完整 quota／backpressure 已随 2026-08-19 的用户裁决删除，不再是下一步」。S5、P2／P3、`UNVERIFIED`／`NO_CUTOVER` 三条保留 |

**切片行第二列（处置列）未改**：它记录的是那一片当时落地了什么（含「配置默认 `0／0` 保持既有行为」），是历史事实。删除声明写在第三列与标题列，读者不会把它当现状。

### 未改（报告明示不动）

`:12`、`:80`、`:232`、`:235`、`:242` 的 `archive/260807-resident-byte-budget@8fb6a97…`、`archive/260807-resident-budget-wiring@aa5f1d3…` 等 archive 分支名，一律未动。

---

## 四、`docs/agents/service-cutover/readiness.md`

报告 F 节列 2 行，全部执行。

| 报告行号 | before（截断） | after（截断） |
|---|---|---|
| 53 | 「current `main@fb4272b…` 已包含 network retry、resident wiring 及 token／response／item identity fixes」 | 删 resident wiring，括注「同期的 resident wiring 已于 2026-08-19 按用户裁决删除，见下方 block buffering 行」 |
| 56 | 行标题「…／resident budgets 与 backpressure」；正文「由 `REL-06` 冻结普通 per-request aggregate＋global resident reservation、有限 queue、charge-before-read、两级可观测计账、capacity／deadline／cancel 终态与拒绝新 admission…配置默认 `0／0`…」；组件列 `runtime/memory-quota`＋`pipeline/admission`；下一步「先闭合完整 quota／backpressure 的其他 owner…」 | 标题改「…／per-request buffer cap 与 backpressure」；正文改为：REL-06 具体条款以 `spec.md` 为准（不代主会话陈述冻结合同内容）＋两片 resident 切片曾进入 main 但字节级预算已于 2026-08-19 整体删除＋`max_inflight` 等待式上限与豁免路由＋`buffer_cap_bytes` 保留且越限放弃 response；组件列改 `delivery/block-buffer`＋`pipeline/sink`＋`server/admission`；下一步只留真实 loopback sink 那半句。状态仍 `UNVERIFIED`，未改 |

**一处刻意未改**：53 行的「budget 边界」（出现在证据列与 Next smoke 列）。它与 unknown capability reject、retry 后重转换并列，指的是 **retry attempt budget**，不是内存预算；报告也未把它列进来。按「宁可留一条已知的旧句，也不做一次错误的修正」，未动。

---

## 五、`docs/agents/service-cutover/plan.md`

报告 G 节列 1 行，已执行。

| 报告行号 | before（截断） | after（截断） |
|---|---|---|
| 9 | 「Current main 已线性包含 foundations、systemd runtime、bridge 主路径、retry／resident wiring、Copilot identity…」 | 「…bridge 主路径、retry、Copilot identity…（同期的 resident wiring 已于 2026-08-19 按用户裁决删除，进程级改由 `proactive_rate_limiter.max_inflight` 等待式在途上限承接）」 |

---

## 六、不在原报告中（我另行发现并修正）

以下与派发给定的代码事实直接冲突，报告未列。全部为「悬空引用已删除符号／机制」或「把已删机制写成下一步」。

### `architecture.md`（11 处）

| 现行号 | before（截断） | after |
|---|---|---|
| 149 | mermaid 节点 `BB[Per-block memory buffer + global reservation]` | `BB[Per-block memory buffer + per-request buffer cap]` |
| 274 | `HistoryDurabilityReceipt` 字段 `reservation_released` | `projection_released`（保留「恰好一次释放」的所有权语义，只换掉已删机制名） |
| 292 | 「durable 或 failed 单次终结，reservation release 恰好一次」 | 「…projection ownership release 恰好一次」 |
| 454 | client abort 行「释放 memory reservation」 | 「释放 buffer 内存」 |
| 473 | request journal 事件清单含 `memory.reservation_waited` | 删该事件名。**未替换为新事件名**：admission 等待发生在 ASGI 中间件、request journal 之前，凭空造一个 `admission.waited` 会是新的错误断言 |
| 477 | 「只承载 `history.durable`、`history.persistence_failed` 与对应 reservation release」 | 「…与对应的 projection ownership release」 |
| 485 | 「request-owned buffer／reservation 已清理」 | 「request-owned buffer 已清理」 |
| 520 | 「且 reservation 恰好释放一次」（测试意图） | 「且 projection ownership 恰好释放一次」 |
| 531 | 「目标使用按 Anthropic block identity 分桶的 memory buffer 与 global reservation」 | 「…与 per-request buffer cap」 |
| 599 | 「History writer 独立拥有 durable／failed receipt 和移交后的 reservation」 | 「…与移交后的 projection」 |
| 639／640 | Gate 清单「request／global reservation」「reservation release」 | 「per-request buffer cap」「projection ownership release」 |

### `implementation.md`（10 处，均为「下一步／待补 = quota／backpressure」）

`:71`、`:75`、`:79`、`:93`、`:94`、`:104`、`:117`、`:222`、`:237`、`:276` 的**前瞻列**把已删机制写成待办。统一改为：「下一核心入口／序列」→ `kernel partial-write`；「待补 quota／backpressure」→「buffer cap 下的背压」。另 `:235` 的「quota／resident backpressure」直接点名已删符号，改为「buffer cap 下的背压」。

### `readiness.md`（4 处）／`plan.md`（1 处）

`readiness.md:55`、`:72`、`:124`、`:154`、`:160` 与 `plan.md:524` 的前瞻句同样写着「下一核心先 quota／backpressure」，统一改为 `partial-write`。

---

## 七、明确未改，及理由

1. **spec.md、acceptance.md** —— 派发禁止，未打开写入。它们仍带 8 处（spec）与 6 处（acceptance）与代码冲突的规范条款，其中 `spec.md:462`「不得…无限等待」与实现直接字面冲突，`spec.md:467+468-473` 把「并发 bridge 数」列为必须拒绝并产生稳定 Anthropic error 的 limit 类别——按现行 spec，正确实现会被判红。**这是本次剩下的最高优先级项，归主会话。**
2. **archive 分支名**（`archive/260807-resident-byte-budget@…` 等）—— 不可变历史标识，按派发不动。
3. **ADR／处置记录正文**（architecture.md:655 U1 行、ADR-BRIDGE-03 前两条、research.md:208 R2 行、implementation.md:654 M4 行）—— 按 (b) 只加标注与追加新记录，不原地改写。其中 **implementation.md 评审处置表的 M4 行提到「reservation token 移交」**，属同类历史处置记录，未动；机制删除已由 architecture.md 新增的 U3 行与本文件承载。
4. **「…仍未验证 / 未覆盖 quota／backpressure」这类范围声明**（`implementation.md:11`、`:15`、`:38`、`:39`、`:81`、`:84`、`:222`、`:234`、`:280`、`:291`；`readiness.md:6`、`:9`、`:42`、`:72`、`:124`、`:160`、`:181`）—— **未改**。它们陈述的是「某次 gate／canary 没有覆盖到那一块」，作为当时的取证边界记录仍然字面为真；改写它们等于重写历史取证范围。**但这是一个残留风险，我不认为它可以就此了结**：接手者读到「quota／backpressure 仍未验证」仍可能去找那块不存在的工作。建议主会话裁决是否统一改写为「buffer cap 与在途上限下的背压行为」。我没有自行决定，因为这会波及 17 行历史记录列。
5. **「current `main@c1de6bf…`」的其余出现**（implementation.md 7 处、readiness.md 9 处、plan.md 3 处）—— 未逐处改。文档顶部已声明 `c1de6bf` 不再是 current HEAD，且 HEAD 在并行会话下持续移动，逐处写死新哈希只会制造下一轮同类缺陷。同样建议主会话裁决处理方式（例如统一改为「2026-08-08 快照锚点」）。
6. **`docs/.human-controlled/config.example.yaml`** —— 未动（禁止范围）。报告 Q4 指出的三点（整段被注释、示例值 5 vs 默认 50、没写「超限是等待」）仍在；并行会话的 `3e75654`「docs: propose how the in-flight cap should read in the user's config example」看起来正是在处理它，主会话可核对是否已覆盖。

---

## 八、自查

```
git --no-optional-locks diff --stat -- docs/
 .../anthropic-responses-bridge/architecture.md     | 58 +++++++++++-----------
 .../anthropic-responses-bridge/implementation.md   | 48 +++++++++---------
 docs/agents/anthropic-responses-bridge/research.md |  9 ++--
 docs/agents/service-cutover/plan.md                |  4 +-
 docs/agents/service-cutover/readiness.md           | 14 +++---
 5 files changed, 68 insertions(+), 65 deletions(-)
```

只有五份被许可的文件被修改，加本文件（新建于 `docs/tmp/`）。未执行任何改变 git 状态的命令。

书写约定自查：改动行均为整行替换，未引入句内换行；新增中文句读全部为全角 `，。：；（）`，半角标点只出现在英文／代码片段与 markdown 语法中（已用正则对 diff 的新增行逐行核对，仅命中 mermaid 的 `-->` 与 markdown 链接括号两处误报）。
