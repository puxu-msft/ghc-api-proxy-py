# Spec 切片：被截断的流式 turn 的续写与放弃

**状态**：草案第 4 版，**未冻结**。第 1 版经独立评审判「不能冻结」（4 blocker、7 major）；第 2 版复核又出 5 major、2 minor。**两轮共 18 条发现全部采纳**，本版是第二次修订。待用户裁决第 8 节的八项后冻结。
**日期**：2026-08-21。
**评审**：`../../tmp/260821-review-g2-spec-draft.md`。

> ## ⚠️ 一个新增代价，先看这个
>
> 用户 2026-08-21 裁决「续写这个能力要做」，**该裁决仍然有效**。评审随后查明：实现它必须**附带修改一条桥 spec 的冻结条款**——四个启用前提里的「重复前缀 suppression」**对自由文本没有可靠解**，任何 best-effort 方案都讨不清它。
>
> 所以要裁的是**是否接受这个新增代价**：接受，则维持原裁决并修改冻结条款；不接受，则**显式推翻**「续写要做」并保持禁用。见 8.1。
>
> 本文作者主观推荐先不启用。**该推荐不改变现行裁决**——在你改判之前，「要做」仍是权威。

## 0. 这份文档与既有 spec 的关系

**它不是一份新框架。** `../../anthropic-responses-bridge/spec.md`（下称「桥 spec」，冻结中）在「推荐 retry 边界」一节已经裁决了这件事的形态：

> post-commit continuation 不是透明 retry。只有存在可证明的 resume contract、已提交 block ledger、重复前缀 suppression 与 tool/reasoning 安全条件时，才能作为独立能力启用。

本切片的全部工作是**逐条讨清那四个前提**。桥 spec 的任何条款在此均为**权威**；本文的复述都指回它，不得改写其含义。**凡本文需要放宽桥 spec 的地方，一律显式标为「需修改冻结条款」并进入第 8 节，不得以「可观测」「degradation」等措辞自行授权。**

**上游背景**（不重述）：`.dev/docs/upstream/h2-goaway/findings.md`、`../../tmp/260821-truncated-anthropic-stream-diagnosis.md`（触发本切片的事故 req=d3b7f5ba）、`260821-plan-g2-wire-stream-ending.md`、`260821-poc-continuation-reasoning-echo.md`。

**已生效的用户裁决（2026-08-21）**：`continuation.max_retries=10` 与 `streamReplay.max_retries=100` 的现有默认值保持不变。

## 1. 适用范围与恢复资格

仅适用于**流式**请求，且上游响应头已返回（driver 已出栈、body 正在交付）。

**恢复资格先于恢复裁决。** 桥 spec 把 client cancel、server shutdown、approval rejection、capability error、deterministic conversion error 与 hard limit violation 判为默认不可重试，并禁止 shutdown／client cancel 启动新 attempt。这些终态的**位置事实**（是否已开、提交了几块）与 upstream truncation 完全可能相同，因此位置事实**不足以**决定资格。

裁决前必须先由唯一 retry owner 把收尾归一化为一个 `ending_cause`：

| `ending_cause` | 含义 | 处置 |
|---|---|---|
| `UPSTREAM_ENDING` | 上游 clean EOF、上游传输撕裂，**或上游明确的 terminal failure** | 进入第 3 节裁决 |
| `LOCAL_ABORT` | 本侧停止：客户端断开／取消（`CLIENT_GONE`），或本进程正在退出（`SHUTDOWN`） | 直接 ABANDON，**不调用裁决、不扣预算** |
| `DELIVERY_FAILURE` | sink 写失败、conversion error、limit violation、capability error | 同上 |

`UPSTREAM_ENDING` **包含**上游明确失败，而不是排除它。第 1 版把这个 cause 叫 `UPSTREAM_TRUNCATION`，同时又在第 3 节强调「明确失败不是截断」——两者合起来要么让 R1 永远不可达，要么把明确失败重命名成本文刚否认过的截断。现在的分工是：**cause 只回答「这次收尾是上游那一侧结束的吗」，是不是截断由 R1 之后才判**——无 failure 且无成功 terminal 的剩余状态才叫 truncation。

`CLIENT_GONE` 与 `SHUTDOWN` 在**恢复资格上合并**为 `LOCAL_ABORT`（处置完全相同），但二者的 origin 仍须为 History／observability 保留。**origin 必须由 disconnect watcher／shutdown coordinator 在起因处显式传入**，禁止由 `_StreamAccounting` 从 `drained`／`failure`／GeneratorExit 三态事后猜测——现有实现的注释已自陈那三态分不出这两者。

`ending_cause` 是**归一化归属**，不是具体异常类型。「异常类型不是裁决输入」这条原有裁决继续成立且不冲突：归属由捕获现场记录，裁决只读归属。

两条上游腿都适用，但 4.1 对它们提出不同的构造要求。

## 2. 裁决输入

`ending_cause == UPSTREAM_ENDING` 时，输入为五项：

| 输入 | 来源 | 含义 |
|---|---|---|
| `ending_cause` | 见第 1 节 | 是否有资格恢复 |
| `terminal.seen` | `Terminal.seen` | 上游自己的**成功**终止事件是否到达 |
| `terminal.failure` | `Terminal.failure`（G1 引入，分支 `fix/upstream-error-events`） | 上游是否**明确说了**它失败 |
| `downstream_opened` | `DeliverySession.started` / `client_has_bytes` | 客户端是否已见到任何语义事件（`message_start` 起算；keep-alive 注释不算） |
| `committed_ledger` | 见 4.2 | 已越过 commit frontier 的块及其身份 |

## 3. 五条路

**按此顺序求值，先命中者胜。**

| # | 条件 | 结果 | 依据 |
|---|---|---|---|
| R1 | `terminal.failure is not None` | **ABANDON** | 明确失败**优先于任何成功标记**。两者同时观察到时记录 `terminal_conflict`——assembler 的状态机在收到成功 terminal 后并不关闭，`seen` 与 `failure` 同真是可达状态，若让 R2 先命中，一次上游明确失败会被伪装成 COMPLETE |
| R2 | `terminal.seen` | **COMPLETE** | 上游正常收尾 |
| R3 | 未开 | **REPLAY**（预算允许）否则 ABANDON | 客户端一无所见，第二次 attempt 可无痕替代第一次 |
| R4 | 已开、ledger 为空 | **待裁决，见 8.2** | 此状态只由兼容性 synthesized preamble 产生 |
| R5 | 已开、ledger 非空 | **CONTINUE**（预算允许且 4.3／4.4 的门通过）否则 ABANDON | 本切片主体 |

R3–R5 均以 `not terminal.seen and terminal.failure is None` 为前提。

**failure precedence 是本切片对 `decide_stream_ending` 的唯一新增语义**；编号不承诺与现有实现一致。预算**当场扣减**而非仅查询（现有实现已满足）。

## 4. 四个启用前提

> **本节四条只约束 CONTINUE（R5）。** REPLAY（R3／R4）走不到这里：那两格的前提就是 ledger 为空，因此没有 resume turn 要构造、没有 ledger 要补齐、没有重复前缀要抑制，4.4 的 tool 门也恒真。REPLAY 需要遵守的是 5.1。

### 4.1 可证明的 resume contract

续写请求 = 原始请求 + 一个由**已提交块**构成的 assistant turn + 一句 continuation user 消息。

**Anthropic 腿**：`assistant.content` 由 ledger 中的 payload 依 index 顺序构成，随后追加 `{"role":"user","content":<continuation.message>}`。加密 thinking 原样保留 `{"type":"thinking","thinking":"","signature":"<原签名>"}`——空 `thinking` 合法，**前提是签名非空且逐字节原样**。

**Responses 腿**：**不能**套用上述形状。必须构造顶层 `input` 序列：`{"type":"reasoning","summary":[],"encrypted_content":"<output_item.done 的最终值>"}`，其后是 assistant 的 `output_text` message item 与 user 的 `input_text` message item。

> `continuation_messages()` 目前只产出 Anthropic 形状。在 Responses 腿的构造函数落地前，**Responses 腿必须显式判 ABANDON**，且必须是代码里写明的一格加注释，不是默认落空。

**reasoning 不可逐字节同腿回传时（缺失、空、损坏、跨腿不兼容）：ABANDON**，记录 `continuation_reasoning_unusable`。第 1 版写的是「丢弃 reasoning 后继续」——那是桥 spec 未授权的新 degradation，可观测并不能把未经授权的语义丢失变成合法。若要允许，须先在桥 spec 的字段处置矩阵新增具名 DEGRADE 政策，见 8.4。

PoC 只证明了**有效签名可原样回传**（`claude-opus-4.8`，非 `claude-opus-5`，属外推），**未**证明删除已提交 reasoning 后 resume 仍安全。

### 4.2 已提交 block ledger —— **当前不满足，是前置条件**

第 1 版称「已存在，无需新建」，**该陈述失实**。`CompletedBlock` 只有 `index`、`kind`、`payload`；`DeliverySession.delivered` 只是它的列表，`committed_count` 只是列表长度。桥 spec 要求的 stable semantic identity、normalized content digest、tool call id、reasoning semantic identity、carrier digest 与独立 commit state **都不存在**。

**启用 CONTINUE 前必须先补齐该 ledger**，`committed_count` 由其连续 committed frontier 导出。ledger 的 identity 用于审计与 suppression，**不得用 payload 列表冒充**。这是前置条件，不是运行时 degradation。

### 4.3 重复前缀 suppression —— **无可靠通解；这决定了整个能力能否启用**

续写把已生成内容交回并要求模型接着写。**模型仍可能重复它说过的内容**：换个说法重述、重开一个它以为没写完的工具调用、或从头再答一遍。

不借助上游提供的 resume cursor 或幂等 generation identity，**无法可靠区分「模型在重复前缀」与「模型有意重复同一句话」**。这不是回避一个有解的问题——缺口是真实的。

| 方案 | 做法 | 能否讨清桥 spec 的前提 |
|---|---|---|
| A. 不抑制 | 信任提示词 | **否** |
| B. 块级摘要去重 | 新块内容摘要与 ledger 比对，命中即整块丢弃 | **否**（只抓逐字节整块重复；工具块可靠，文本块改写即漏） |
| C. 文本前缀重叠裁剪 | 新首块与已交付尾部做最长重叠匹配并裁剪 | **否**（会误删合法的重复用词；裁剪后的块不再是上游发的那个块，与「预构造完整 envelope」的不变量另有冲突） |
| D. 对 eligible continuation 不做任何内容删除，自由文本重复记为具名 degradation | 不删内容，只上报 | **否** |

**D 里原本写的「工具块强制去重」已删除，因为它不可达。** 4.4 规定 ledger 中存在任意未配对 `tool_use` 就在发请求前 ABANDON，于是：ledger 有旧工具块 → 整个 continuation 被挡住，suppression 根本看不到新 attempt；ledger 没有旧工具块 → 新 attempt 的工具块也没有旧的可匹配。**在任何 eligible 的 continuation 上，D 实际就等于 A**：没有文本抑制，也没有工具前缀可抑制。第 1 版把 D 描述得比 A 强，是靠一条走不到的分支。

**结论：现有冻结前提下不能启用 post-commit continuation。** 8.1 要裁的是**是否允许这种没有可靠 suppression 的 continuation**，而不是「A–D 选哪个即可启用」。若允许，**不得再声称 continuation 对客户端不可见，也不得再声称满足 no-duplication 保证**。将来若引入 tool-result rendezvous contract，再单独重开工具 suppression 的设计。

### 4.4 tool/reasoning 安全条件

- **reasoning**：见 4.1。
- **tool_use**：**ledger 中存在任何尚无对应 `tool_result` 的 `tool_use` 时，判 ABANDON。**

  依据是**代理拿不到 tool_result，因而无法构造协议完整的 resume turn，也无法证明重新生成不会让客户端重复执行**。第 1 版给的理由是「客户端已经拿到工具调用并会去执行」——**那是对未定义客户端行为的假定，已撤回**：截断时发出的是 SSE `error` 而非 `message_stop`，没有任何合同保证客户端会在一条失败消息上执行工具，它也可能等成功 terminal 才执行。

  判据必须覆盖 **ledger 中任意**未配对 tool call，不能只看最后一块——`tool_use` 之后还有 text／thinking 的前缀会绕过「最后一块」门，却仍构造出缺 `tool_result` 的非法请求。

  **影响规模**：事故当日 `/v1/messages` 的 2355 条成功 terminal 中 1805 条为 `stop_reason=tool_use`（约 76.6%，两条腿都约四分之三）。**这是潜在影响的上界倾向，不是截断命中率**——截断落点未必与正常收尾落点同分布，事故请求本身 `tools=[]` 并不命中这条门。

  只有将来存在可验证的 tool-result rendezvous contract 时，才可为此状态另立恢复路径。

## 5. 多-attempt 流的 wire 不变量

一次请求跨了不止一个 upstream attempt 时，下游看到的仍必须是**一条** Anthropic message。REPLAY 与 CONTINUE 都会造成多 attempt，所以下面分两组：5.1 两者都适用，5.2 只对 CONTINUE 适用。

### 5.1 所有多-attempt 流共用（REPLAY 与 CONTINUE 均适用，现在就生效）

- **中间 attempt 绝不向下游发任何终止性帧。** attempt 的 EOF／撕裂先进入裁决；只要判 REPLAY 或 CONTINUE，就**不得**发 `error`、`message_delta` 或 `message_stop`。最终 COMPLETE 产生一次成功 terminal；最终因 upstream ending、conversion／limit failure 或预算耗尽而 ABANDON 时，**仅在 downstream 仍可写、且 message wire 已进入可发送状态时**产生一次 SSE `error`。`LOCAL_ABORT` 中的 `CLIENT_GONE` **不写** synthetic error（没有人在读）；sink write failure **不再写一次**；shutdown 按剩余可写窗口处理。所有路径在 History／diagnostics 中仍必须有明确终态。
  > 这条最容易在接线时踩：若把每个 attempt 分别交给现有 `stream_delivery`，它在第一次 EOF 就会发出 `error` 并返回，wire 从此不可恢复。**REPLAY 同样会踩**——所以这一条不能等到 CONTINUE 启用才生效。
- **一次请求只有一个 `message_start`。** 已经发出 preamble 之后重开 attempt，不得再发第二个。
- **后续 attempt 的身份不得泄漏到 wire。** downstream `message_id`、model、HTTP status 与已提交 response headers 在首个可见 batch 后冻结；后续 attempt 的 response id、model、status、request id、rate-limit headers 只进入 attempt diagnostics。否则一条 Anthropic message 会呈现为两条上游 response 的拼接。
- **每个 attempt 必须新建 assembler、`Terminal` 与 attempt-local buffer**；旧 attempt 的 drafts、已完成但未提交的块、usage 与 terminal metadata 整体丢弃。这是桥 spec「attempt reset 必须丢弃全部未提交状态；已提交 frontier 不得回退」的直接应用。REPLAY 时 frontier 本来就是空的，该规则退化为「全部丢弃」。
- **每个 attempt 有自己的 `deadline_at`**（`context.begin_attempt()`），不得沿用前一 attempt 已过期的 deadline。

### 5.2 CONTINUE 专属（**仅在 8.1 选择修改桥 spec、且 4.1–4.4 的其余前置条件满足后生效**）

当前默认禁用不等于删除设计——这是将来启用 CONTINUE 时必需的 wire contract。

- continuation 的 **attempt boundary 在 Anthropic wire framing 上不可见**：仍只有一条 message、一个 preamble、一个 terminal。但按 8.1 接受的自由文本重复 degradation **可能在语义内容上可见**，所以不得称为「对客户端完全不可见」。
- **index 在 suppression 之后再分配。** 每个 attempt 保留自己的 source index／identity；suppression 完成后，**按被接受的新块顺序**分配下一个连续 downstream index。**不得**用 `committed_count + raw_attempt_index`——suppression 丢掉 attempt 的第 0 块会留下 index 洞。也不得修改 ledger 中既有 block 的 index。
- **attempt 边界只带过两样东西**：committed ledger 与 downstream session。

## 6. 记账与可观测性

- `attempts`：真实 attempt 数（既有语义）。
- `bytes_in`：定义为本请求**所有真实 upstream exchange 的发送字节总和**（每次发送都可直接观察，所以累加是事实而非估计），并在 `upstream_attempts[]` 保留各 attempt 值。
- `↓` 收字节：`_counted_upstream` 已累加，跨 attempt 自然正确。
- **`usage` 不累加，且 calibration 还有一个额外条件。** downstream 成功 `usage` 仍**只取最终成功 attempt**，保持桥 spec 算式不变。
  **token calibration 只在 observer 同时拿到该最终 attempt 实际发送前的 canonical Anthropic request 时才允许学习**，并用它估算后与该 attempt 的 usage 配对。**不得**拿 original inbound request 去配最终 continuation 的 usage——续写请求比原始请求多了一个 assistant turn 和一句 user 消息，两者不是同一个请求。若现有 hook contract 只能提供 original request，则被续写的请求**跳过** success calibration，记录 `calibration_skipped=continuation_request_unavailable`，直到 hook contract 补齐。
  > 「只取最终 attempt」本身并不足以保护校准，它只是比「两次 usage 相加」少错一层。正确性条件是**估算与实测必须来自同一个实际请求**。
  > 第 1 版倾向累加，已撤回。桥 spec 冻结的是「仅最终成功 attempt 能更新成功 usage 与 token calibration」，它并没有禁止单独记录失败 attempt 的成本——两件事本就可以并存，不需要改冻结条款。而累加会把失败尝试、重复输入与被续写请求放大的 payload 混进一条 model message 的 usage，并**污染 token 校准**：`TokenCalibrationSuccessObserver`（`src/app/hooks/builtin/token_calibration.py`）用一次请求的估算去配上游实报 usage 反解校准因子，喂给它两次 attempt 的输入总和会学出错误的因子。已核实。
- 另设 `attempt_usage[]` / `retry_cost` 诊断事实，逐 attempt 记录上游实报 usage、`estimated`、缺失原因与累计**可知**成本；**不得**把缺失 attempt 估成零后宣称精确累计。
- **`upstream_conn` 保持现有对象形状，继续记录首个可见／发生截断的 attempt。** 第 1 版倾向改记最后一个，已撤回：最后一条是恢复成功的连接，不是出故障的那条，而 `findings.md` 有一个具名读者跨失败行比较 `upstream_conn.local` 来判断是否同一条连接——改记最后一条会直接抹掉故障连接身份，detail 里的次数无法还原地址。另增 `upstream_attempts[]` 结构化数组（`attempt`、`reason`、`bytes_in`、`bytes_out`、`upstream_conn`），最后成功的连接从数组末项读。
- **续写必须出现在请求行上**，否则操作者无法把「一次干净的回答」与「一次补出来的回答」分开。具体措辞不冻结。
- 4.1 的 reasoning 不可用、4.3 的 suppression 命中、4.4 的 tool 门命中，都必须可观测。

## 7. 明确不做

| 不做 | 理由 |
|---|---|
| 把 body 消费搬回 driver 循环 | 要推翻「`_send` 止于 headers」这个有实测依据的刻意设计，改动面远大于收益 |
| 非流式路径的续写 | 没有 commit frontier，失败即整体重试，既有判据已覆盖 |
| 放宽 `context.reply` 的 `seen` 门（G3） | 独立裁决项，与 failed History 同批 |
| 为「续写的 attempt 又被截断」预建多层状态空间 | 预算天然收敛，第二次截断走同一套判据 |

## 8. 待用户裁决（八项，均附推荐）

1. **是否接受「自由文本重复对客户端可见」这个新增代价，以维持「续写要做」的裁决？**（4.3）
   **接受** → 维持原裁决，同时修改桥 spec 的 post-commit continuation 条款，允许无可靠 suppression 的 continuation。客户端可能看到重复内容；不再满足 no-duplication 保证。
   **不接受** → 需要你**显式推翻**「续写要做」，post-commit continuation 保持禁用，本切片只落地 R1／R2／R3 与各 ABANDON 分支。
   **注意这不是「A–D 选哪个」**：D 在任何 eligible continuation 上等价于 A（见 4.3），所以选项里没有一个「更强的抑制方案」可选。
   **推荐：先不启用。** 但这只是主观推荐——在你改判之前，「续写要做」仍是有效裁决。
2. **R4（synthesized preamble 已发、零已提交块）取哪条路？**
   **推荐：REPLAY**——复用既有 downstream message、禁止第二个 `message_start`、新 attempt 首块从 index 0 提交。第 1 版说「replay 必然发第二个 `message_start`」是**错的**，第 5 节已经要求维持单个 session。若你选保守 ABANDON，理由应冻结为「preamble 已使 HTTP success 不可撤回」，不得写成技术必然。
3. **ledger 中任意未配对 `tool_use` 是否一律 ABANDON？** **推荐：是。**
4. **reasoning 无法逐字节同腿回传时一律 ABANDON，还是修改桥 spec 授权具名 degradation？** **推荐：ABANDON。**
5. **post-commit 时第一 attempt 已冻结的 HTTP headers 怎么处理？** 桥 spec 规定 retry 期间只保留最终可见 attempt 的 headers，但 post-commit 时第一 attempt 的 headers 已不可撤回，这是一处潜在冲突。**推荐：downstream headers 保持第一 attempt，后续 headers 仅入 attempt diagnostics，并在桥 spec 的 Header 契约中写明 post-commit continuation 例外。**
6. **usage 维持最终成功 attempt 语义并另记 attempt cost？** **推荐：是，不修改成功 usage。**
7. **是否先补齐符合桥 spec 字段要求的 committed ledger 再允许 CONTINUE？** **推荐：是，前置条件而非运行时 degradation。**
8. **ending eligibility 是否显式排除 client cancel、shutdown、sink／conversion／limit failure？** **推荐：是。**

---

## 9. 修订记录

| 版本 | 变化 |
|---|---|
| v1 | 初稿。评审判不能冻结：ledger 声称失实、四输入不足以决定资格、方案 D 未讨清前提、`tool_use` 判据与理由均不成立，另有 7 条 major |
| v2 | 全文重写，11 条全部采纳 |
| v4 | 第三轮仅 1 条 major：第 5 节按「REPLAY 也需要」拆成 5.1 共用不变量与 5.2 CONTINUE 专属；第 4 节补注仅约束 CONTINUE。评审确认八项待裁决完整，无需第九项 |
| v3 | 复核 7 条全部采纳：cause taxonomy 改名 `UPSTREAM_ENDING` 以容纳明确失败、ABANDON 不再无条件承诺 SSE error、D 的工具去重分支被证明不可达并删除、第 5 节可见性收窄为 wire framing 且标为条件生效、calibration 增加「配对同一实际请求」条件、恢复对用户既有裁决的正确表述、`LOCAL_ABORT` 的 origin 须由起因处传播 |
