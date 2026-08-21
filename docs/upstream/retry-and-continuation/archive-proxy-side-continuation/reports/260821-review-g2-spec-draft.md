# G2 continuation 行为 Spec 草案评审

**评审对象**：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/h2-goaway/spec-stream-continuation.md`。

**评审基线**：草案当前文本；冻结中的桥 spec；`fix/upstream-error-events` 工作树 `fd6b59187ad0f1262e9c25a4b796b8ba58952253`；用户指定的实现文件、背景文档与 `requests-20260821.jsonl`。本次只读源码、文档和日志，未修改被评对象，未触碰 git 索引。

**总评**：**不能冻结。** 草案诚实地识别了自由文本重复抑制没有可靠解，但随即把一个明确不满足冻结前提的方案 D 当成可启用方案；同时把并不存在的 ledger 能力写成“已存在”，并用四个位置事实替代了 retry eligibility，导致 client cancel、shutdown、delivery failure 等真实终态会被误判为 CONTINUE。`tool_use` 的 ABANDON 方向可以保留，但当前判据和理由都不成立。草案所称“只逐条讨清四个前提、没有改写桥 spec”目前不成立。

**发现计数**：4 blocker，7 major。

## 发现

### F1 — blocker — 四个输入不足以决定恢复资格，R5 会把本侧停止和不可重试失败续写

**读到的**：第 2 节明确说无论“干净 EOF、传输撕裂，还是本侧提前停止”都用 `terminal.seen`、`terminal.failure`、`downstream_opened`、`committed_blocks` 四项裁决，并禁止异常类型作为输入。桥 spec `Retry ownership 与 delivery semantics` 明确把 client cancel、server shutdown、approval rejection、capability error、deterministic conversion error 与 hard limit violation判为默认不可重试；`Shutdown、cancel、backpressure 与 limits 契约` 又明确禁止 shutdown／client cancel 启动新 attempt。现有 `_tracked_delivery` 也明确区分 upstream drain、异常和本侧关闭，只是 `Terminal` 本身不承载这些原因。

**推出来的**：一个已提交块后发生的 client disconnect、shutdown cancellation、sink write failure 或 conversion／limit failure，四项位置事实都可以与 upstream truncation 相同，于是会落入 R5 并消耗 continuation 预算。具体异常类不应决定恢复，这一点正确；但“归一化终止归属／类别”与“具体异常类”不是一回事。**证据强度：构造性冲突，足以阻断冻结。**

**替代措辞**：把第 1、2 节改成：

> 本切片只裁决由 upstream EOF、upstream transport tear 或 upstream 无成功 terminal 的等价 truncation 所触发的收尾。client cancel、server shutdown、approval／capability／conversion／limit failure、downstream sink failure 与本侧主动停止先由唯一 owner 归一化为不可恢复原因，直接 ABANDON，且不得调用 `decide_stream_ending` 消耗预算。裁决输入由五项组成：`ending_cause`、`terminal.seen`、`terminal.failure`、`downstream_opened`、`committed_blocks`。`ending_cause` 是归一化归属，不是具体异常类型；只有 `ending_cause == UPSTREAM_TRUNCATION` 才进入 R1–R5。

### F2 — blocker — 第 4.2 节声称 ledger 已存在，与 `fd6b591` 源码直接矛盾

**读到的**：桥 spec 要求 committed block ledger 至少记录 stable semantic identity、Anthropic index、normalized content digest、tool call id、reasoning semantic identity、carrier digest 与 commit 状态。草案称这些“由既有实现承担”。但 `CompletedBlock` 在 `blocks.py:40-46` 只有 `index`、`kind`、`payload`；`DeliverySession.delivered` 只是 `list[CompletedBlock]`，`committed_count` 只是列表长度。没有 semantic identity、normalized digest、reasoning identity、carrier digest，也没有独立 commit state。

**推出来的**：当前对象足够重放 Anthropic payload，却不满足冻结 spec 所称 ledger，更不足以跨 attempt 判断 duplicate semantic item。草案把第二个启用前提误记成已满足。**证据强度：源码逐字段对账，足以阻断冻结。**

**替代措辞**：把第 4.2 节改成：

> 当前 `DeliverySession.delivered` 只保存 `CompletedBlock(index, kind, payload)`，可作为已交付 payload 前缀，但**不满足**桥 spec 的 committed block ledger。启用 CONTINUE 前必须为每个已提交 block 保存：attempt-local source identity、全局 Anthropic index、normalized content digest、tool call id、reasoning semantic identity、carrier digest 与 committed 状态；`committed_count` 由该 ledger 的连续 committed frontier 导出。ledger 的 identity 用于审计与 suppression，不得用 payload 列表冒充。

### F3 — blocker — 第 4.3 节的“诚实缺口”判断正确，但方案 D 与方案 A 一样不满足启用前提

**读到的**：桥 spec 明定只有具备“重复前缀 suppression”才能启用 post-commit continuation。草案方案 D 明说文本重复不抑制，只记录和上报，却只把 A 标成“违反冻结条款”。B 只能去掉字节级整块相同内容；C 只能裁剪可证明的字面重叠并有误删歧义；D 对文本完全不抑制。

**推出来的**：对随机模型自由文本，不借助 provider resume cursor／幂等 generation identity，无法可靠区分“模型重复前缀”和“模型有意重复同一句”。作者不是在回避一个显然可解的问题；缺口是真实的。但真实缺口的结论应是“现有冻结前提下不能启用”，而不是把不满足前提的 D 改名为 degradation。B、C、D 都不能证明桥 spec 当前要求，D 与 A 在该前提上没有本质差别。**证据强度：合同对账加不可区分性推理，足以阻断冻结。**

**替代措辞**：把第 4.3 节结论和第 8.1 项改成：

> 现有上游没有可证明的 resume cursor／generation identity，因此目前没有方案能同时保证自由文本重复前缀被抑制且合法重复不被删除。B、C 可作为 best-effort 机制，但均不能满足桥 spec 当前的启用前提；D 与 A 一样需要修改冻结条款。待用户裁决的不是“A–D 选哪个即可启用”，而是二选一：① 保持桥 spec，不启用 post-commit continuation；② 明确修改桥 spec，允许文本重复作为已知 degradation，并冻结可接受的 best-effort suppression、可观测字段和失败边界。若选择②，建议采用 D 作为最少误删的政策，但不得再声称 continuation 对客户端不可见或满足 no-duplication 保证。

### F4 — blocker — `tool_use` 判据只看最后一块会漏掉非法 assistant turn，理由也假定了未定义的客户端行为

**读到的**：第 4.4 节只在“最后一个已提交块是 `tool_use`”时 ABANDON。第 4.1 节则把**全部**已提交块放进一个 assistant turn，随后直接追加普通 continuation user 消息。只要任何已提交块是 `tool_use`，该 assistant turn 就含尚无对应 `tool_result` 的调用。日志中的 `tools` 记录所有工具块，不只最后一个。草案给出的理由是客户端“已经拿到该工具调用并会去执行”；现有 wire 在 truncation 时发 SSE `error` 而没有 `message_stop`，没有合同保证客户端会在失败消息上执行工具。

**推出来的**：一条 `tool_use` 后再有 text／thinking 的已提交前缀会绕过“最后一块”门，却仍可能构造出缺少 `tool_result` 的非法或语义错乱请求。相反，客户端可能等待成功 terminal 才执行，也可能在 `content_block_stop` 后立即执行；代理无法从当前输入知道是哪种，不能把任一种客户端策略写成理由。ABANDON 的保守方向成立，但正确依据是“代理没有 tool_result，无法证明 resume request 合法且不会造成重复执行”，判据应覆盖 committed ledger 中任意未配对 tool call。**证据强度：请求形状的构造性反例，足以阻断冻结。**

**影响估计**：读取日志时，`/v1/messages` 的 2355 条成功 terminal 中有 1805 条 `stop_reason=tool_use`，约 **76.6%**；Anthropic 与 Responses 两腿都约为四分之三。因此，若 truncation 位置近似正常 terminal 位置，这条门可能覆盖很大比例，但这只是**上界倾向，不足以外推真实 truncation 比例**。事故请求本身是唯一明确的 upstream clean truncation，`tools=[]`，并未命中。相邻成功请求“多数为 tool_use”不能证明截断也会按同一比例落点。

**替代措辞**：把第 4.4 节改成：

> 若 committed ledger 中存在任何尚无对应 `tool_result` 的 `tool_use`，判 ABANDON。代理在当前请求内拿不到客户端执行结果，既不能构造协议完整的 resume turn，也不能证明重新生成不会让客户端重复执行；不得假定客户端会或不会在失败 terminal 前执行工具。只有未来存在可验证的 tool-result rendezvous contract 时，才可为该状态另立恢复路径。

### F5 — major — R1 与 R2 不互斥，当前顺序允许 failure 被 COMPLETE 覆盖

**读到的**：R1 条件只有 `terminal.seen`，R2 条件只有 `terminal.failure` 非空；表中没有互斥条件，R1 排在 R2 前。`fd6b591` 的 assembler 没有关闭 terminal state 的 guard：收到 `message_stop`／`response.completed` 后仍可读取后续 `error`／`response.failed`，所以 `seen=True` 且 `failure!=None` 在状态机上可达。`pipeline_app.py` 已经刻意让 `terminal.failure` 否决 otherwise-successful ending。

**推出来的**：R2 排在 R3/R4/R5 前是必要但不充分；它还必须否决 R1。否则明确失败会被伪装成 COMPLETE，直接违反 error mapping。**证据强度：源码可达状态，足以要求修改。**

**替代措辞**：把顺序改为：

> R1：`terminal.failure is not None` → ABANDON。明确失败优先于任何 success marker；若同时观察到 success terminal 与 failure，记录 `terminal_conflict`。
>
> R2：`terminal.failure is None and terminal.seen` → COMPLETE。
>
> 后续各格均显式以 `not terminal.seen and terminal.failure is None` 为前提。

并把“R2 是唯一新增分支”改成“failure precedence 是唯一新增语义；编号不承诺与旧实现一致”。

### F6 — major — R4 的 ABANDON 不是穷尽性要求，而是一个尚未说明的产品裁决

**读到的**：R4 说 replay 必然发送第二个 `message_start`，所以只能 ABANDON；第 5 节却已经要求 continuation source 维持单个 downstream session、不得发送第二个 `message_start`。当前真实可达状态来自 synthesized preamble：客户端已见 `message_start`，但没有 block 越过 commit frontier。桥 spec 的透明 retry 边界按“是否提交 semantic block”划分，而不是按“是否发过 preamble”划分；桥 spec 本身还要求 preamble 与首块同 batch，因此 R4 是 active direct leg 的兼容状态，不是桥 spec 正常状态。

**推出来的**：重开原请求并复用同一个 downstream session，可以保留已有 preamble、抑制第二个 preamble，再从新 attempt 提交第一个块；此前没有 block 可重复。它是否仍叫 REPLAY、以及已提交 HTTP 200 后是否愿意承担第二次失败只能发 SSE error，是产品裁决，但“必然第二个 message_start”不是成立的技术理由。**证据强度：现有 wire 控制流与冻结 frontier 定义共同支持，足以要求把该项交给用户。**

**替代措辞**：把 R4 改成待裁决项：

> R4：未 `seen`、未 `failure`、已开、`committed_blocks == 0`。此状态只由兼容性 synthesized preamble 产生。候选政策为 REPLAY：复用既有 downstream message，禁止第二个 `message_start`，新 attempt 的首块从 index 0 提交；若预算耗尽则 ABANDON。若用户选择保守 ABANDON，理由应冻结为“preamble 已使 HTTP success 不可撤回，项目不在此状态继续上游工作”，不得写成 replay 技术上必然重复 preamble。

### F7 — major — “签名不可用时丢弃 reasoning 后继续”新增了桥 spec 没有授权的 reasoning degradation

**读到的**：第 4.1 节允许签名缺失、为空或跨腿不兼容时丢弃 reasoning 块并继续，只要求可观测。桥 spec 的兼容性条款明确说 tools、reasoning、carrier、ordering 与 unknown 项不得由 permissive 政策额外放宽；推荐边界要求存在 reasoning 安全条件。PoC 只证明有效签名可原样回传，未证明删除已提交 reasoning 后的 resume 仍安全。

**推出来的**：可观测并不会自动把未经授权的语义丢失变成合法 degradation。这是草案实际放宽冻结条款的第二处。**证据强度：冻结条款直接冲突，足以要求修改。**

**替代措辞**：把该段改成：

> committed ledger 中存在 reasoning 时，只有能按当前 leg 的合法形状逐字节回传 opaque payload／signature 才允许 CONTINUE；缺失、空、损坏或跨腿不兼容均 ABANDON，并记录 `continuation_reasoning_unusable`。若用户希望允许删除 reasoning 后继续，必须先在桥 spec 的字段处置矩阵中新增一条具名 DEGRADE 政策；本切片不得自行授权。

### F8 — major — 第 5 节的 wire 不变量不完整，按当前分层接线会在第一次截断时提前泄漏 error

**读到的**：当前 `stream_delivery` 在单个 event stream EOF 后立即检查 terminal；未见 terminal 就发 SSE `error` 并返回。草案要在同一个 downstream message 内跨 attempt，却只列 index、第二个 `message_start` 和最终 terminal 次数。`CompletedBlock.index` 是 immutable attempt-local 值；重复 suppression 可能丢掉 continuation attempt 的前几个块。

**推出来的**：若 source 仍把每个 attempt 分别交给现有 `stream_delivery`，第一次 EOF 的 `error` 会先到客户端，随后再续块，wire 已不可恢复。仅做 `new_index = committed_count + attempt_index` 也会在 suppression 丢掉 attempt index 0 后让首个新块从 `committed_count + 1` 开始，留下 index hole。后续 attempt 的 message id、model、response headers 和 terminal metadata若泄漏，也会让一条 Anthropic message呈现为两条上游 response 的拼接。**证据强度：现有调用路径的直接结果，足以要求扩充合同。**

**替代措辞**：在第 5 节追加：

> attempt EOF／tear 先进入 ending decision；只要裁决为 REPLAY／CONTINUE，就不得向 downstream 发中间 `error`、`message_delta` 或 `message_stop`。只有最终 COMPLETE 产生成功 terminal，最终 ABANDON 产生且只产生一个 SSE `error`，两者互斥。
>
> downstream `message_id`、model、HTTP status 与已提交 response headers在首个可见 batch 后冻结；后续 attempt 的 response id、model、status、request id、rate-limit headers只进入 attempt diagnostics，不得覆盖 downstream wire。
>
> 每个 attempt 保留自己的 source index／identity；suppression 完成后，**按被接受的新块顺序**分配下一连续 downstream index。不得用 `committed_count + raw_attempt_index`，也不得修改 ledger 中既有 block 的 index。
>
> 新 attempt 必须创建新的 assembler、Terminal 与 attempt-local buffer；旧 attempt 的 drafts、held-but-uncommitted completed blocks、usage 和 terminal metadata整体丢弃，只把 committed ledger 与 downstream session带过边界。

### F9 — major — 把 `upstream_conn` 改记最后一条会破坏已经具名的事故读者

**读到的**：`pipeline_app.py` 与结构化日志文档明确命名读者：跨失败行比较 `upstream_conn.local`，相同即同一条 TCP/H2 连接。草案建议续写后只记最后一条连接，并以 detail 说明续写。最后一条是恢复成功的连接，不一定是发生截断的连接。

**推出来的**：只记最后一条会抹掉故障连接身份，让该读者无法判断多条截断是否来自同一连接；detail 只有次数，不能恢复地址。直接把字段改为列表又会破坏按对象读取的现有消费者。**证据强度：具名 reader contract 的直接回归，足以要求修改。**

**替代措辞**：把第 6 节该项改成：

> `upstream_conn` 保持现有对象形状并继续记录**首个可见／发生截断的 attempt**，维持具名 forensic reader。另增 `upstream_attempts` 结构化数组，每项含 `attempt`、`reason`、`bytes_in`、`bytes_out` 与 `upstream_conn`；最后成功连接从数组最后一项读取。不得用最后连接覆盖故障连接。

### F10 — major — usage 并不与“只由最终成功 attempt 更新成功 usage”冲突，累加后塞回成功 usage 会混淆两种事实

**读到的**：桥 spec 冻结的是“仅最终成功 attempt 能更新成功 usage 与 token calibration”；它没有说失败 attempt 的成本不得单独记录，反而允许失败 attempt进入 error／prompt-limit observation。事故的截断 attempt 根本没有 terminal usage，日志为 `{}`。草案把“成功 message usage”和“多次 upstream exchange 的累计成本”视为同一个字段，并倾向累加全部 attempt 后修改冻结条款。

**推出来的**：两者可同时保留，不需要修改成功 usage 语义。把所有 attempt 相加后写入 Anthropic terminal usage 会把失败尝试、重复输入和 continuation 的扩大 payload混进一条模型 message 的 usage，并可能把缺失值伪装成精确总数；还会污染 token calibration。`bytes_in` 可以定义为真实累计发送字节，因为每次发送都可直接观察，但最好保留 per-attempt breakdown。**证据强度：合同字段语义对账，足以否决当前倾向 (a)。**

**替代措辞**：把第 6、8 节 usage 项改成：

> downstream terminal `usage`、成功 usage 与 token calibration仍只取最终成功 attempt，并保持桥 spec 算式。另设 `attempt_usage[]`／`retry_cost` 诊断事实，逐 attempt记录 upstream 实报 usage、`estimated`、缺失原因与累计可知成本；不得把缺失 attempt估成零后宣称精确累计。`bytes_in` 定义为本请求所有真实 upstream exchanges 的发送字节总和，并在 `upstream_attempts[]` 保留各 attempt 值。

### F11 — major — 第 8 节问少了决定能否启用和能否保持既有合同的关键问题

**读到的**：当前三问只有 suppression 方案、usage 累加方式和末块 `tool_use`。上面的合同对账还暴露了 cancellation eligibility、R4 synthesized-preamble policy、reasoning 丢弃、任意未配对 tool call、后续 attempt headers、ledger 是否先补齐等未决项。桥 spec 又规定 retry 期间只保留最终可见 attempt headers，但 post-commit 时第一 attempt 的 HTTP headers已经不可撤回；草案没有指出这处潜在冲突。

**推出来的**：即使用户回答当前三问，Spec 仍不能冻结为可执行且不改写上位合同的行为。**证据强度：待裁决项与规范缺口逐项对账，足以要求补问。**

**替代措辞**：用以下裁决清单替换第 8 节，并在每项后写明推荐值：

> 1. 是否修改桥 spec，允许自由文本重复作为已知 degradation；若不修改，post-commit continuation保持禁用。推荐：先不启用，除非用户明确接受 D 的可见重复风险。
>
> 2. synthesized `message_start` 且零 committed block时选择复用 session 后 REPLAY，还是保守 ABANDON。推荐：REPLAY，但必须抑制第二个 preamble。
>
> 3. committed ledger 中任意未配对 `tool_use` 是否一律 ABANDON。推荐：是。
>
> 4. reasoning 无法逐字节、同腿合法回传时是否一律 ABANDON，还是修改桥 spec授权具名 degradation。推荐：ABANDON。
>
> 5. post-commit continuation 如何处理已经冻结的第一 attempt HTTP headers与后续 attempt headers。推荐：downstream headers保持第一 attempt；后续 headers仅入 attempt diagnostics，并在桥 spec Header 契约中写明 post-commit continuation 例外。
>
> 6. usage 是否维持最终成功 attempt语义并另记 attempt cost。推荐：维持，不修改成功 usage。
>
> 7. 是否先补齐满足桥 spec 字段要求的 committed ledger，再允许 CONTINUE。推荐：是，这是前置条件而非运行时 degradation。
>
> 8. ending eligibility 是否显式排除 client cancel、shutdown、sink／conversion／limit failure。推荐：是。

## 对重点问题的直接结论

1. **与冻结条款一致性**：不一致。第 4.2 对 ledger 的既有能力陈述失实；D 与 reasoning-drop 都放宽了冻结前提；四输入又违反不可重试类别。块 frontier 的文字复述本身正确，但 index offset 算法不完整，suppression 后可能制造洞。
2. **R1–R5 穷尽且互斥**：对四个布尔／计数输入的理想子空间近似穷尽，但对真实 ending state 不穷尽，对 `seen + failure` 不互斥。R2 必须在 R1 前，而不只是排在 R3/R4/R5 前。R4 是可达状态，但 ABANDON 不是唯一技术结果。
3. **重复前缀 suppression**：缺口诚实且没有通用可靠解；D 是修改冻结合同后的合理最小伤害政策，不是现合同下可启用的实现。我不同意按当前写法选择 D 后冻结。
4. **`tool_use` 结尾 ABANDON**：保守方向同意，当前理由不同意，判据必须从“最后一块”扩大为“任意未配对 tool call”。事故日 76.6% 的正常 terminal 为 `tool_use`，只说明潜在影响上界很大，不是 truncation 命中率。
5. **wire 不变量**：不完整；最关键遗漏是中间 attempt 绝不能先发 error／terminal，suppression 后再分配连续全局 index，以及后续 attempt 的 id／model／headers不得泄漏。
6. **记账**：`bytes_in` 累加可成立，但应有 per-attempt breakdown；成功 `usage` 不应累加失败 attempt；`upstream_conn` 只记最后一条会直接破坏具名 forensic reader。
7. **待裁决项**：没问全；至少应补 ending eligibility、R4、reasoning degradation、任意 tool call、headers 与 ledger 前置条件。

---

## 第 2 版复核（2026-08-21）

**复核范围**：只检查第 1 版发现的采纳是否到位，以及采纳过程中是否引入新矛盾；不重复论证第 1 版已经成立的结论。复核基线仍为 `fix/upstream-error-events` 的 `fd6b591` 与冻结中的桥 spec。

**结论**：第 1 版 11 条发现的实质均已采纳，但第 2 版仍**不能冻结**。新发现 5 major、2 minor；其中三条来自采纳项之间的新交互：F1 的 cause taxonomy 与 failure precedence 没接平、F4 使方案 D 的工具 suppression 变成不可达、F3 的“语义可见”与 F8 的“客户端不可见”形成正文自相矛盾。

### V2-F1 — major — `UPSTREAM_TRUNCATION` 既要排除明确失败，又必须承载 R1，cause taxonomy 自相矛盾

**读到的**：第 1 节只允许 `ending_cause == UPSTREAM_TRUNCATION` 进入 R1–R5；R1 又专门处理 `terminal.failure is not None`。第 1 版及本版第 3 节都强调“上游明确失败不是截断”。当前 `Terminal.failure` 由 upstream `error`／`response.failed` 产生，而 stream 随后仍可能自然 EOF。

**推出来的**：若 capture site忠实把明确失败归成非 truncation，R1 永远不可达；若为了让 R1 可达而把它标成 `UPSTREAM_TRUNCATION`，taxonomy 又把明确失败重命名为先前明确否认的截断。**证据强度：表格控制流直接冲突，足以要求修改。**

**替代措辞**：二选一，推荐第一种：

> 将可进入裁决的 cause 改名为 `UPSTREAM_ENDING`，含 upstream clean EOF、transport tear 与 upstream terminal failure；R1 先用 `terminal.failure` 否决，只有无 failure 且无 success terminal 时才把余下状态称为 truncation。

或：

> 新增 `UPSTREAM_TERMINAL_FAILURE`，直接 ABANDON且不扣预算；`UPSTREAM_TRUNCATION` 才进入 R2–R5。R1 只保留为 defensive conflict guard，并注明正常分类下不可达。

### V2-F2 — major — “最终 ABANDON 必发一个 SSE error”覆盖了 client gone 与 sink write failure，违反既有 cancel／sink 契约

**读到的**：第 1 节把 `CLIENT_GONE`、`SHUTDOWN`、sink 写失败都归为直接 ABANDON；第 5 节第一个不变量却无条件规定“最终 ABANDON 产生且只产生一个 SSE `error`”。桥 spec 明定 client cancel 后不尝试 synthetic error；sink 写失败时 downstream 本身不可证明可写。当前 `stream_delivery` 也只在已有可写 stream 上产生 error。

**推出来的**：新 cause 表把原本只针对 upstream truncation 的 wire 结论扩到了无法／不得写 wire 的终态。shutdown 也可能已失去发送窗口，不能无条件承诺一个 frame。**证据强度：冻结 cancel 条款的直接冲突，足以要求修改。**

**替代措辞**：把第 5 节首项改成：

> 中间 attempt 绝不发终止性帧。最终 COMPLETE 产生一次成功 terminal；最终因 upstream ending、conversion／limit failure或预算耗尽而 ABANDON时，**仅在 downstream 仍可写且 message wire 已进入可发送状态时**产生一次 SSE `error`。`CLIENT_GONE` 不写 synthetic error；sink write failure 不再次写；shutdown按剩余可写窗口处理。所有路径在 History／diagnostics 中仍必须有明确终态。

### V2-F3 — major — F4 的任意 tool 门使方案 D 的“工具块强制去重”不可达，D 在可恢复状态上已经退化为 A

**读到的**：4.4 现在规定 ledger 中存在任意未配对 `tool_use` 就在发 continuation 请求前 ABANDON。4.3／8.1 的方案 D 却仍把“对 tool_use 做 ledger 去重”写成修改冻结条款后的推荐机制。

**推出来的**：若 ledger 有旧 tool block，4.4 已经挡住整个 continuation，suppression 看不到新 attempt；若 ledger 没有旧 tool block，新 attempt 的 tool block也没有 ledger 中的旧 tool block可匹配。因此 D 的工具去重分支在当前安全政策下不可达， eligible continuation 上的 D 实际就是 A：文本不抑制，也没有工具前缀可抑制。**证据强度：两个顺序门的构造性对账，足以要求修改选项。**

**替代措辞**：删除“工具块强制去重”的 D，改成：

> D. 对 eligible continuation 不做内容删除；自由文本重复作为具名 degradation 记录。任意旧 `tool_use` 已由 4.4 在请求前 ABANDON，因此本政策没有 tool suppression 分支。

第 8.1 应让用户裁决的是“是否允许这种**无可靠 suppression** 的 continuation”，不得再用不可达的工具去重把它描述得比 A 更强。若未来引入 tool-result rendezvous，再单独重开工具 suppression 设计。

### V2-F4 — major — 第 5 节仍称“续写对客户端必须不可见”，与 4.3 接受可见重复直接矛盾；index 规则应标为条件生效

**读到的**：4.3 明说若修改冻结条款采用 D，“不得再声称 continuation 对客户端不可见”；第 5 节开头紧接着又写“续写对客户端必须不可见”。同节 index suppression 规则无条件出现，而 8.1 选择不修改时 CONTINUE 没有触发路径。

**推出来的**：这里混淆了两种可见性：attempt boundary 的 wire framing可以不可见，重复文本的语义效果可能可见。index 规则作为 dormant contract 可以保留，但必须明确只在 8.1 允许 CONTINUE 且所有前置条件满足后生效，否则正文一面禁用能力、一面无条件冻结其算法。**证据强度：正文逐字矛盾，足以要求修改。**

**替代措辞**：把第 5 节开头改成：

> **本节仅在 8.1 选择修改桥 spec、且 4.1–4.4 的其余前置条件满足后生效。** continuation 的 attempt boundary 在 Anthropic wire framing上不可见：一次请求仍只有一条 message、一个 preamble和一个 terminal；但按 8.1 接受的自由文本重复 degradation 可能在语义内容上可见，不得称为“对客户端完全不可见”。以下 index 规则是该条件路径的规范，不因当前默认禁用而删除。

### V2-F5 — major — “只用最终成功 attempt 做 calibration”仍不足够，必须配对该 attempt 的实际 augmented request

**读到的**：`TokenCalibrationSuccessObserver` 在 `token_calibration.py:48-65` 取 `data["request"]` 做 `estimate_anthropic_input(request)`，再与同一 observation 的 usage输入 token相配。continuation 的最终 attempt 请求不是原始入站 request，而是原始请求加已提交 assistant turn与 continuation user消息。第 6 节只禁止 usage跨 attempt累加，却没有要求 observer收到最终 attempt 的实际 canonical request。

**推出来的**：把最终 attempt usage单独喂给 observer，若仍与原始 request estimate配对，一样会学出错误因子；它只是比“两次 usage 相加”少错一层。正确性条件不是“只取最终 usage”，而是“estimate 与 real必须来自同一个实际 request”。**证据强度：observer 源码的数据配对关系，足以要求修改。**

**替代措辞**：把第 6 节 calibration 句改成：

> downstream成功 `usage` 仍取最终成功 attempt。token calibration 只有在 observer 同时拿到**该最终 attempt 实际发送前的 canonical Anthropic request**时才允许学习，并用它估算后与该 attempt usage配对；不得拿 original inbound request 或前一 attempt request配最终 continuation usage。若现有 hook contract只能提供 original request，则 continued request跳过 success calibration，并记录 `calibration_skipped=continuation_request_unavailable`，直到 hook contract补齐。

### V2-F6 — minor — 重新询问 8.1 是恰当风险披露，不是越权推翻，但“原裁决需要重新确认”应改成依赖裁决而非失效裁决

**读到的**：顶部明确披露新发现，第 8.1 把是否修改冻结条款交回用户，没有直接执行“先不启用”。因此当前文本**没有越权改掉**用户的“续写要做”。但“那次裁决……需要你重新确认”容易读成旧裁决已经自动失效，8.1 的推荐值又与它相反。

**推出来的**：新事实足以要求用户裁决 degradation，但在用户改判前，“续写要做”仍是有效权威；其实现现在多了一个必须由用户批准的桥 spec 修改。若用户不接受修改，才需要他显式推翻先前决定。**证据强度：决策权与文档措辞对账，属于可在冻结前修正的权威表达问题。**

**替代措辞**：把顶部告示和 8.1 收束为：

> “续写要做”的裁决仍有效；新发现表明，实现该裁决必须附带修改桥 spec、接受自由文本重复 degradation。请裁决是否接受这个新增代价：接受则维持原裁决并修改冻结条款；不接受则显式推翻“续写要做”并保持禁用。本文作者主观推荐先不启用，该推荐不改变现行裁决。

### V2-F7 — minor — `CLIENT_GONE` 与 `SHUTDOWN` 可以保留区分，但不能要求 `_StreamAccounting` 从同一个隐含退出形状事后猜出来

**读到的**：两者在 retry eligibility 上处置相同；当前 `_StreamAccounting` 的注释明确说隐含的本侧停止无法区分 client gone 与 shutdown。桥 spec 同时要求 History／observability保留 cancel 与 shutdown 原因，因此区分并非无价值，也不是原则上做不到。

**推出来的**：分两行不是新错误；正确实现方式是由 client-disconnect watcher／shutdown coordinator 在起因处显式传递 origin，而不是由 `drained`／`failure`／GeneratorExit 三态反推。若本切片只想定义恢复资格，可用一个 `LOCAL_ABORT` eligibility 值并另存 `abort_origin`，减少 retry policy 对实现细节的要求。**证据强度：现有实现能力与冻结 observability要求共同支持，足以澄清但不阻断整体设计。**

**替代措辞**：在第 1 节补一句：

> `CLIENT_GONE` 与 `SHUTDOWN` 对恢复裁决可合并为 `LOCAL_ABORT`；二者的 origin仍须为 History／observability保留。origin必须由 disconnect／shutdown 发起处显式传入，禁止从 `_StreamAccounting` 的隐含 GeneratorExit 事后猜测。

## 三个重点问题的直接答复

1. **`ending_cause` 接缝**：`CLIENT_GONE` 与 `SHUTDOWN` 分开不是不必要要求，因为上位 spec 已要求区分两种终止原因；但 retry eligibility 可以合并，origin另存。当前实现确实不能靠 `_StreamAccounting` 三态区分，必须从发起处显式传播。真正的 major 是 taxonomy遗漏了 explicit upstream failure，并把所有 ABANDON误写成必发 error。
2. **与既有“续写要做”裁决的关系**：重新询问 degradation 是恰当的风险披露，不构成越权；但旧裁决在用户改判前仍有效。应把 8.1 写成“接受新增代价以维持原裁决／不接受并显式推翻原裁决”，而不是暗示旧裁决因新发现自动失效。
3. **index 规则是否保留**：应保留，但明确为条件生效。它是未来启用 CONTINUE 时必需的 wire contract；当前不启用不等于删除设计。与此同时必须把“对客户端不可见”收窄成“attempt boundary在 wire framing上不可见”，否则与可见文本重复自相矛盾。

---

## 第 3 版最后确认（2026-08-21）

**限定范围**：只检查采纳第 2 版七条意见所产生的新交互，不重开前两轮结论，不扩展主题。

**结论：仍不可冻结。** 第 3 版正确采纳了七条复核意见，但“把第 5 节整体标为仅在 8.1 接受 CONTINUE 后生效”新引入 1 条 major：R3／R4 的 REPLAY 同样依赖该节多项不变量，8.1 拒绝 CONTINUE 后这些不变量反而全部 dormant。除此之外，本轮未发现新的矛盾或不可达分支。第 8 节提交用户裁决的八项**是完整的**；下面这条是正文适用范围的修订，不是第九项产品裁决。

### V3-F1 — major — 第 5 节被整体条件化后，仍启用的 R3／R4 REPLAY 失去了共同 wire contract

**读到的**：第 5 节开头规定整节“仅在 8.1 选择修改桥 spec”后生效；8.1 的“不接受”分支却明确仍落地 R3，8.2 又可独立选择 R4=REPLAY，并引用第 5 节的单 session／不发第二个 `message_start` 规则。第 5 节的“中间 attempt 不发 terminal”“不得发第二个 `message_start`”“新建 assembler／Terminal／attempt-local buffer”“每 attempt 新 deadline”等并非 CONTINUE 专属，也约束 REPLAY。

**推出来的**：若用户在 8.1 禁用 CONTINUE、同时按 8.2 选择 R4=REPLAY，第 5 节按首句整体不生效，8.2 赖以成立的禁止第二个 preamble规则就没有规范效力；R3 的中间 attempt terminal suppression、reset 与 deadline同样失去约束。这正是本轮要求检查的“采纳时产生的新交互”。**证据强度：8.1、8.2 与第 5 节适用门的直接控制流冲突，足以阻断冻结。**

**替代措辞**：把第 5 节拆成两个适用域：

> ### 5.1 所有多 attempt stream 的共同不变量
>
> 本节对 R3／R4 的 REPLAY 与 R5 的 CONTINUE 均生效：中间 attempt 不发终止性帧；已发 preamble 时不得发第二个 `message_start`；后续 attempt 的 identity／headers不得覆盖已经冻结的 downstream wire；每个 attempt 新建 assembler、`Terminal`、attempt-local buffer并取得新 deadline；最终 terminal／error按 downstream可写性只产生一次。
>
> ### 5.2 CONTINUE 专属不变量
>
> 本节仅在 8.1 接受修改桥 spec且 4.1–4.4 前置条件满足后生效：自由文本重复可能语义可见；committed ledger跨 attempt保留；suppression后分配连续 downstream index；已提交 frontier不得回退。

## 两个自查问题的结论

1. **R1 的双重角色**：当前措辞准确，不构成新问题。`terminal.failure is not None` 是正常 upstream failure 的主路径；“两者同时观察到时记录 `terminal_conflict`”语法上明确只约束 `seen && failure` 这个子集，没有把普通 failure误记成 conflict。若求更清楚，可把依据拆成“普通情形：明确失败直接 ABANDON；冲突子情形：若 `seen` 同真，另记 `terminal_conflict`”，但不是冻结阻碍。
2. **4.2／4.4 是否也要条件化**：二者已经由“启用 CONTINUE 前必须”和“四个启用前提”限定，并由 R5 显式引用；无需再挂 8.1 的整节门。REPLAY 时 ledger为空，不构造已提交 assistant turn，也不需要 tool门。可以各补一句“仅约束 R5 CONTINUE，不约束 R3／R4 REPLAY”以防误读，但不是缺失行为。真正需要修的是把第 5 节的共同 REPLAY／CONTINUE规则与 CONTINUE专属规则拆开。

## 冻结／裁决完备性

- 当前第 3 版因 V3-F1 **仍不可冻结**。
- 修正第 5 节适用域后，本文即可提交用户裁决；没有需要新增的第九项。
- 第 8 节八项覆盖了本切片所有尚需用户决定的产品／上位合同分叉。用户完成八项裁决并将相应选择同步进正文与桥 spec 后，可以冻结。
