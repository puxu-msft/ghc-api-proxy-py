# 直连 Responses 原生透传产品规格独立复评（round 3）

- report_id：`direct-responses-passthrough-spec-review-round3`
- attempt_id：`260830-review-spec-3`
- reviewed_at：2026-08-30
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v3）
- 关联 living plan：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/plan.md`（当前仍标 v2）
- 对照基线：`/tmp/260830-review-spec-round2.md`
- 评审性质：只读规格复评；未修改 `src/` 或 `tests/`；未派 agent

## 评审范围

本轮先沿用 round 2 已建立的独立判据：用户亲笔 `client-side-block-delivery.md` 的完整交付单位、首个 HTTP 200 attempt headers 与后续 HTTP failure→SSE error；`upstream-retry-and-continuation.md` 的 retry 分类；`message-translation.md` 的 direct-native 原则；`error-envelope/spec.md` 的 error source／carrier；以及现有 `stream.py`、`retry.py`、`hand_over.py` 的实际状态机。随后读取 Spec v3 全文并复核关联 Plan，分别回答 round2 四条处置与当前系统状态。

覆盖面包括：unfinished suffix 与 complete policy-held groups 的区别、`block`／`full`／`until-tool-use` 在所有 ending 下的释放、native failure／clean EOF／replacement failure 的 replay adapter、response header 的 hop-by-hop 与 representation metadata、`requires_client_action` 的同类 restatement、§11 归属以及 P1／P2 前置实现状态。

明确不在范围内：实施 direct passthrough、修改被评文档、修改生产代码或测试、真实 Copilot 调用、穷尽所有未来 HTTP response fields、重新裁定用户亲笔的 buffering policies、生产 4141 服务的任何操作。

## 总体 verdict

**needs-fix。不可据此开始主体实现。blocker 数：2。**

v3 对 round2-01 与 round2-02 的原问题作出了产品选择，方向成立；但完整的 ending 状态仍少一格：`full`／未触发的 `until-tool-use` 已持有 complete groups，而 cap／deadline／budget-exhausted EOF 等 proxy ending 先于 upstream terminal 到达时，Spec 同时要求保留这些 complete groups、等 terminal 才发、立即写 proxy error，三者无法同时执行。§5.1 仍以“复用既有 retry taxonomy”代替 native failure event→taxonomy input 的映射，且 replacement HTTP failure／draining 的 SSE carrier 与 attribution 未定。另有两条 major：header denylist 没有处理 `Connection` 动态命名的 hop-by-hop fields，也会转发因 body 变换失效的 validator／digest；v3 修订没有同步到 predicate signature、正例、§9 旧句、§11 与 living Plan。

## Round 2 四条处置状态

| finding_id | round2 级别 | 状态 | 判据与结论 |
|---|---:|---|---|
| `direct-responses-passthrough-spec-review-round2-01` | blocker | closed | §3 已明确只承诺 complete item groups，并把 unfinished suffix 在 tear／terminal／failure／cap／deadline／cancel 时丢弃；`response.failed` 反例与“terminal 不证明未知 lifecycle 完成”均入正文。新发现的 complete but policy-held groups 是另一状态，见 round3-01 |
| `direct-responses-passthrough-spec-review-round2-02` | blocker | closed | §9.1 已给 streaming／non-stream 同一 header 合同、首个 200 attempt 来源与 replacement 不覆盖，原先“表不存在”的 blocker 已消失；新表本身的协议错误另列 round3-03 |
| `direct-responses-passthrough-spec-review-round2-03` | blocker | partially-closed | clean EOF 与“replacement 失败应取 replacement”已定；native failure 到现有 taxonomy 的输入映射仍不存在，replacement 建流前 failure 的 carrier／attribution 仍不唯一，见 round3-02 |
| `direct-responses-passthrough-spec-review-round2-04` | major | partially-closed | §7.1 的解释段已改为读 response item；但函数签名、正例、§11 与 Plan 仍写 `original_request`／请求声明／数据通路，见 round3-04 |

状态计数：`closed=2`、`partially_closed=2`、`not_closed=0`。

## 当前系统状态：新发现与残留发现

### direct-responses-passthrough-spec-review-round3-01

- finding_id：`direct-responses-passthrough-spec-review-round3-01`
- severity：`blocker`
- primary_location：`spec.md:61-69,162-168,188-194`
- related_locations：`docs/.human-controlled/client-side-block-delivery.md:3-5,15-21`；`src/app/pipeline/delivery/stream.py:414-431,478-504,506-574`
- 标题：Spec 只裁了 unfinished suffix，没有裁 complete but policy-held groups 遇 proxy ending 时发还是丢

**证据。** 构造 `full` 下的有限序列：`response.created → item A added/delta/done → item B added/delta → cap exceeded`。A 是 §3 明确承诺逐字重放的 complete item group，B 按 v3 新条款属于 unfinished suffix 并丢弃；但 §7 又说 `full` 只有“上游终局后”才发全部事件，而 cap 没有 upstream terminal；§8 要立即写 proxy error。于是 A 只有三个互斥出口：在 error 前发，违反“等 upstream terminal”；随 B 丢，违反 §3 对 complete group 的承诺；继续等，违反 cap 的 abandoning ending。把 cap 换成 client deadline、post-replay budget-exhausted clean EOF 或 transport tear，矛盾不变。未触发 action 的 `until-tool-use` 也有同一格；`block` 没有，因为 A 已经 commit。

当前 `stream.py` 不能替 Spec 选答案，而且其不同 ending 本来就不一致：exception／client deadline 分支明确不 flush buffered blocks，clean EOF 则先 `session.finish()` 再处理 terminal-less ending。把其中任一条抄作 direct 行为都会让输出依赖 failure 以 exception 还是 EOF 到达，而不是依赖 policy。

**`full` 与 v3 unfinished 丢弃的专项结论。** 正常 upstream terminal／failure 到达时可以自洽：先剔除 unfinished suffix，再把 remaining complete groups + control + terminal／failure 当“全部可提交事件”一次发出。真正未定的是**没有 upstream terminal 的 proxy ending**。所以 round2-01 那个“terminal 让 unfinished item 怎么办”的原问题已 closed，本条是 v3 限定后暴露出的相邻状态，不把两条重复计数。

**影响。** 实现者必须替产品决定 `full` 是“response 任意 ending 前不发、ending 时发安全内容”，还是“只有 upstream terminal 才发，其他 ending 全丢”。这会改变客户端是否拿到已经完整生成的工具调用／文本，也改变三种 policy 的 failure semantics。

**建议。** 在 §7／§8 加一张 policy × ending 表。我的偏好是把 `full` 的“response ends”解释为任意最终 ending：先丢 unfinished suffix，随后按原序提交 control + 所有 complete safe groups，最后提交 upstream terminal／failure 或 proxy error；client cancellation 与 downstream delivery failure 因无可写通道显式例外。这样不丢完整语义，且“直到 response ends 才交付”仍成立。若产品要 all-or-nothing，则必须把 §3 承诺再收窄为“最终实际 committed 的 complete groups”，并明确 cap／deadline／EOF 会丢 policy-held complete groups，不能靠现有异常路径偶然决定。

**证据强度。** 有限 event sequence 即可同时命中三条规范，静态证据强到阻断；不依赖真实 upstream 出现率。现有各 ending 是否 flush 的源码差异只证明不能借现状消解，不被当作产品权威。

**承重前提检查。** 前提是“unfinished suffix 是 policy-held buffer 中唯一可能尚未交付的内容”；v3 据此只规定它的丢弃。`full` 在第一个完整 item 后立即给出反例：complete A 同样还在 buffer。

### direct-responses-passthrough-spec-review-round3-02

- finding_id：`direct-responses-passthrough-spec-review-round3-02`
- severity：`blocker`
- primary_location：`spec.md:106-132`
- related_locations：`src/app/pipeline/delivery/stream.py:70-90,394-401,409-473`；`src/app/pipeline/retry.py:23-58,99-158`；`src/app/pipeline/hand_over.py:24-53`；`src/app/pipeline/delivery/formats/openai_responses.py:472-501`；`src/app/server/routes/inference.py:395-461`；`.dev/docs/error-envelope/spec.md:196-203`；`docs/.human-controlled/client-side-block-delivery.md:7-10`
- 标题：“复用既有 retry taxonomy”没有定义 native failure 如何进入 taxonomy，replacement HTTP failure 的 SSE attribution 也未闭合

**证据。** 现有可复用入口是 `replay_reason(error: Exception)`；它把 exception 交给 `normalize_upstream_error()`／`reason_for()`。`reason_for()`可读 exception 或 HTTP status。原生 `response.failed`／`response.cancelled`／`error` 却是 `StreamFailure`，不是 exception，也没有一个统一 HTTP status；当前 assembler 还把三者全部先记成 `ErrorCategory.UPSTREAM`。`error-envelope/spec.md` 只说由 `response.error.code` 判 category，未知走 fallback；它没有 category→`RetryReason` 的映射。`CATEGORY_FOR_REASON` 是反方向的 reason→category，不能倒用。因此“taxonomy 判为可重试”仍没有可执行输入，尤其 unknown code、cancelled、refusal-like failure 到底 retry 与否仍由实现者猜。

“不为本腿另造闭集”这个目标成立，但它不能代替 adapter contract。复用应当是同一个判定机制接受另一种已归一化输入，而不是把“哪类 event 等价于哪个现有失败”留空。

replacement 行也只闭了一半。用户亲笔合同已经规定第一次 200 headers 之后，replacement 的建流前 HTTP failure 只能转换成 SSE error；v3 却写“客户端看见 replacement 的失败，若不能成帧则写 proxy error”，没有说明这是**upstream-origin failure 经 Responses error carrier 写出**，还是 **proxy-origin error**。两者在 §10 的 failure origin、wire code 与日志上相反。`draining 返回 None` 更不是“replacement attempt 自己失败”：它发生在新 attempt 打开之前，只能是 proxy refusal。当前 `Attempt | None` 把这些不同结局压成同一个 `None`，Spec 若不分，接口也无从分。

**与现有 `stream.py` 能否接上的裁定。** 能接，但仍需 round2 所列的中央改造：failure event 与 clean EOF 都必须先成为 typed replay candidate，不能在 `StreamFailure` 分支立即写出；`ReplaySupport.eligible` 要能接归一化 ending；`reopen` 要返回 `opened attempt | upstream failure | proxy refusal`，而非 `Attempt | None`。clean EOF 在 v3 已明确为 retryable truncation，这一格 closed；缺的是 native event adapter 与 replacement failure carrier。

**影响。** 同一个 `response.cancelled` 或未知 `response.failed`，实现 A 可以按 `UPSTREAM` 全部重试，实施 B 可以因无 HTTP status 全部不重试；二者都能声称“复用了 taxonomy”。replacement 失败时也可能把上游 refusal 误报成 proxy bug，或在 old attempt 已作废后仍回放 old failure。

**建议。** Spec 不必复制 retry closed set，但必须命名唯一 adapter 与 fallback。例如：先用 `error-envelope/spec.md` 的 source reader 得到 `ErrorInfo`／condition，再明确哪些既有 `Disposition`／`RetryReason` 接受这些 category，unknown event 的 fallback 是 retry 还是 terminal；该 adapter与 driver 共用同一表。replacement 结果应分三态：新 stream 成功打开；upstream HTTP/refusal 失败——在已提交 200 下用 Responses `event:error` 表达，origin 仍为 upstream；draining／本代理拒绝——proxy-origin error。旧 attempt 一旦实际 replacement 开始即永久作废，这一条 v3 已定，可保留。

**证据强度。** callable 类型、现有映射方向与 `None` 的三种来源都是强静态证据；哪个 unknown failure 应 retry 没有现成唯一答案，正是 blocker 而不是 reviewer 可代填的实现细节。

**承重前提检查。** 前提是“既有 taxonomy 已有 native stream event 入口”；v3 用它支撑“完全复用便已闭合”。现有唯一入口接受 `Exception`，故前提为假。

### direct-responses-passthrough-spec-review-round3-03

- finding_id：`direct-responses-passthrough-spec-review-round3-03`
- severity：`major`
- primary_location：`spec.md:204-216`
- related_locations：`docs/.human-controlled/client-side-block-delivery.md:7-10`；`docs/.human-controlled/message-format-reshape.md:51-63`；`httpx2/_models.py:871-900,970-1001`；RFC 9110 §7.6.1、§8.8.3.3；RFC 9530
- 标题：“其余一律转发”的 header 算法漏了 Connection-nominated fields 与 body-transform-invalid metadata

**证据一：hop-by-hop 不是一张固定名单。** RFC 9110 §7.6.1 要求 intermediary 在转发前 parse `Connection`，对其中列出的每个 connection option 删除同名 header／trailer，再删除或替换 `Connection` 本身。反例：upstream 返回 `Connection: X-Hop` 与 `X-Hop: value`；v3 固定名单会删 `Connection`，随后按“其余一律转发”把 `X-Hop` 错发到下一跳。现有用户亲笔的 Anthropic blacklist 还明确列了 `Proxy-Connection`，v3 新名单漏掉它。

**证据二：本腿改变 representation bytes，不只有三个 framing headers 失效。** streaming 把 logical events 重新成帧，non-stream 把 parsed JSON object 重新序列化；两者的 octets 都可能不同。因而 upstream strong `ETag`、`Content-Digest`、`Digest`／`Content-MD5`、`Repr-Digest` 等 validator／integrity metadata 不能原样转发。RFC 9110 明定 representation data 改变时必须改变 entity tag，RFC 9530 把 `Content-Digest` 定义为 HTTP message content integrity。当前 `httpx2.Response.aiter_bytes()` 与 `read()` 又明确返回 decoded content，所以 upstream 存在 `Content-Encoding` 时，除非代理重新压缩，否则应删除而不是含糊地“重建”。

**cassette allowlist 区分的专项裁定。** 作者的场景区分站得住：cassette 的具体 hazard 是把账号识别性 headers 持久化进版本库；本路径的 sink 是当前请求的客户端，没有相同的持久化与发布动作。不存在具体受保护资产／失败模式时，不应把录制 allowlist 扩成 wire allowlist，未知 end-to-end semantic headers 默认转发仍是对的方向。需要修的是 HTTP connection scope 与 representation correctness，不是借安全理由收窄功能。句子“客户端对上游的可见性本就不低于我们”比证据更宽——代理凭据下的账号标识未必是客户端原先知道的——但本任务没有已命名的保密要求，故不据此制造 security finding；删掉这句也不改变正确理由。

**影响。** 动态 hop-by-hop field 会泄漏到错误连接；stale digest／strong validator 会让客户端校验失败或把已变换 bytes 标成 upstream 原表示。它们是可构造的协议错误，不是安全推测。

**建议。** 把固定 denylist 改成分层算法：(1) parse `Connection` tokens 并删除同名 fields，再剥固定 hop-by-hop 与 `Proxy-Connection`；(2) 对 body octets／content coding 被本代理改变的响应删除或重新计算所有 representation-octet-dependent fields，至少明确 strong `ETag` 与 digest family，`Content-Encoding` 只在代理实际重新编码时设置；(3) 重建 `Content-Length` 与 streaming `Content-Type`；(4) 其余 end-to-end fields 一律转发，保留重复 field values。这样保住 unknown-richness，而不把无效 metadata 冒充原生。

**证据强度。** `Connection: X-Hop` 是 RFC MUST 直接覆盖的有限反例；decoded body 与 reserialization 是当前代码静态事实；strong ETag／digest 的失效由标准语义直接推出，强到 major。没有穷尽全部 representation metadata，建议用 predicate 而不是再手写一份自称完整的闭集。

**承重前提检查。** 前提是“除 Content-Length／Encoding／Type 外，其余 headers 都不依赖传输连接或 representation bytes”；动态 Connection option 与 strong ETag 各从一侧证伪。

### direct-responses-passthrough-spec-review-round3-04

- finding_id：`direct-responses-passthrough-spec-review-round3-04`
- severity：`major`
- primary_location：`spec.md:170-182,196-216,226-230`
- related_locations：`spec.md:3-9,234-240`；`plan.md:3-7,29-53,65-81`；`.claude/rules/00-development-workflow.md`
- 标题：v3 只改了解释段，没有同步同一事实的 signature、正例、旧状态句、§11 与 living Plan

**证据。** §7.1 第 180～182 行说 predicate 只读 response item、无需 request；但第 172 行的规范 signature 仍是 `requires_client_action(item, original_request)`，第 176 行正例仍写“请求声明 `execution:"client"` 的 `tool_search_call`”。§11 随即宣称数据来源问题已关闭。照 signature／正例实现与照解释段实现会得到不同 API 与数据来源，这正是 round2-04 指出的同类残留。

同一传播缺口还出现三次：§9 第 200 行仍说 header 表“本规格未列，是 §11 未闭合项”，四行后 §9.1 已列且 §11 宣称关闭；文首说“实现未开始”，§11 却说 P1／P2 已在 `8986bbf` 实现待合并；§11 把已实现待合并的代码状态列在“归本规格所有的未闭合项”，反而没有列 round3-01／02 这两条真实产品分叉。

living Plan 仍标 v2、等待 Spec v2 复评，且第 47 行继续要求“原始请求的 tool declaration 与 execution mode”及 request→delivery 通路；Replay 仍只有一句“没有现成代码可改”，没有 v3 的三态 ending；也没有 header、unfinished suffix 或 policy-held complete groups 的步骤／判据。项目规则明确 implementation plans 与 Spec 同为 living 文档，并要求 Spec transcription 同步更新；因此不能以“Spec 为准”让一份已知相反的计划继续当执行入口。

**影响。** 实现者顺 Plan 会重新造出 v3 已否决的数据通路，并漏掉 header 与新 ending；读 Spec 本身也会在 signature 与解释段之间自行选边。§11 则给出“只剩已实现待合并一项”的虚假 readiness 状态。

**建议。** 同一修订完成以下同步：(1) signature 改为 `requires_client_action(item)`，正例改读 `item.execution`；(2) 删除 §9 的旧“表未列”句；(3) §11 只留尚未闭合的产品问题，P1／P2 commit 移到 Plan／status，且在 blockers 清空时 §11 应为空；(4) 文首准确写“主体未开始，P1／P2 已在 worktree 实现待集成”；(5) Plan 升为 v3，加入 policy×ending、typed replay outcome、header algorithm，删除 request data path 与“无现成代码可改”。修订记录中的 v2 历史描述是点时记录，不要回改。

**证据强度。** 同一文件相距数行的逐字矛盾与 Plan 原文是强静态证据；这正是调用方要求检查的“只改被点名处而没扫同类”，不是风格意见。

**承重前提检查。** 前提是“解释段改正后，旧 signature／Plan 因 Spec 优先级而无害”；它会直接决定函数输入与实施步骤，故前提不成立。

## §3／§4／§7／§8 交叉复核

| 情形 | v3 是否闭合 | 结论 |
|---|---|---|
| `block`，item 正常 `done` | yes | safe prefix 就绪即提交；全局原序与 data fidelity兼容 |
| item A／B 交错且最终均 `done` | yes | 较早 unfinished item只造成 head-of-line blocking；最后一个 blocker关闭后连续 prefix 一次释放，不重排 |
| unfinished item 后出现 upstream terminal／failure | yes | unfinished events 丢弃；其余 complete groups + control + terminal／failure可按原相对序提交；terminal 不把 unknown lifecycle 变完整 |
| `status:"incomplete"` 但已有 `output_item.done` | yes | group 在 transport 层已闭合，§8 明定照常交付；不要与“没有 done 的 unfinished suffix”混同 |
| `full`，所有 groups 完成且 upstream terminal／failure 到达 | yes，但应把“全部事件”写成“全部可提交事件” | 丢弃任何 unfinished suffix后，一次释放 complete groups + control + terminal／failure；§3 的具体限定可消解 §7 的泛称 |
| `full`／未触发的 `until-tool-use`，已有 complete groups，随后 cap／deadline／budget-exhausted tear／EOF | **no** | 没有 upstream terminal，complete policy-held groups 发或丢未定；round3-01 |
| cap 只命中 unfinished suffix，此前无 complete group |基本闭合 | 丢 suffix，control 是否随 proxy error一并提交可从 §3 与 §5“无 item failure”合读得出，但建议在 policy×ending 表显式写，避免把 proxy failure 是否属于表中 failure留给术语解释 |
| client cancellation／downstream delivery failure |需要能力例外 | 下游不可写时任何 wire promise都无法兑现；应写为 delivery obligation 的自然例外，不要声称还能发 proxy error |

所以 v3 的 unfinished-item 裁定本身正确；缺口不是它“又会死锁”，而是它没有覆盖 buffer 中同时存在的 complete policy-held groups。

## §5.1 与现有 `stream.py` 接线复核

**结论：结构上可接，行为合同仍未闭合。** 可复用部分是 request-global `RetryLedger`、replacement fresh assembler/buffer reset、首个 downstream native event gate、attempt deadline 与 client deadline；必须改变的是 exception-only replay boundary。

建议的最小状态接口不是新 proof system，而是现有接口的 typed extension：

- `ReplayCandidate = TransportException | UnterminatedEof | NativeFailureEvent`；
- `ReplayDecision` 继续使用现有 `RetryReason`／budget，不另建 counters；
- `ReopenResult = OpenedAttempt | UpstreamFailure | ProxyRefusal`，消除 `None` 多义；
- direct attempt state 同时携带 global queue、frontier、held-byte charge 与 observability summary，replacement 时 wire state全清、operational replay fact保留。

是否采用这组类型名是实现选择；Spec 必须先给每个 variant 的 observable ending。当前 native failure adapter 与 replacement carrier 缺失，故“复用 taxonomy”确实把应由 Spec 定的那一半推给了别处。

## §9.1 header 推导专项结论

- **首个 200 attempt 是唯一 header 来源**：准确复述用户裁决；replacement 不覆盖已提交 headers成立。
- **cassette allowlist 不应扩成 wire allowlist**：场景差异真实且足够；前者有持久化／发布 hazard，后者没有已命名的同一 hazard。此处排除安全剧场。
- **unknown end-to-end headers 默认转发**：方向成立，符合 direct-native 与 richest-context 原则。
- **当前过滤算法不成立**：必须补 dynamic `Connection` tokens，并剥离／重算因 reframe／reserialize失效的 representation metadata；见 round3-03。
- **`Content-Encoding` 当前不是假设。** 本地 `httpx2.Response.aiter_bytes()` 与 `read()` 都经 decoder 返回 decoded content；生产路径继续使用它们时，upstream `Content-Encoding` 必须删除，只有本代理重新编码才可设置新的值。

## §11 复核

§11 当前唯一一项“P1／P2 已实现，待合并”**不阻断 Spec**，也不属于“归本规格所有的未闭合项”。它是实施状态，应进 Plan／status。静态读取 worktree 看到 `encode_frame()` 对每个 logical data line 写独立 `data:`，`iter_frames()` 用不回退的 CRLF／LF／CR 双 line-ending pattern；`git show 8986bbf` 也确认提交改了 `sse_source.py`、`stream.py` 与 `test_sse_assembly.py`。我在该 worktree 跑 `uv run --directory ... pytest tests/unit/pipeline/delivery/test_sse_assembly.py`，结果 `50 passed in 2.11s`。这次绿跑没有控制变异，只支持“当前 targeted suite 通过”，不冒充 P1／P2 已被完整验收；但其 pending merge 不需要留在产品 Spec。

真正漏出 §11 的有 round3-01 与 round3-02；round3-03／04 也必须在 readiness 前修。若这些正文闭合，§11 应为空，而不是用已完成待集成的代码项占位。

## 显式排除掉的可能性

1. **“v3 仍会把 unfinished item 当完整组发出”——排除。** §3 第 65～69 行已明确丢弃且 terminal 不证明完成。
2. **“`status:"incomplete"` item 也应按 unfinished suffix丢弃”——排除。** 它已有 `output_item.done`，transport group 完整；`status` 描述内容结果，不描述 lifecycle 缺 end。
3. **“`full` 在正常 upstream terminal 上必然冲突”——排除。** 把第 167 行的 all 读作 §3 已限定的 committable events即可自洽；建议改词是为阻止误读，不是另立 blocker。
4. **“只丢 unfinished suffix 已覆盖所有 buffered state”——排除。** `full` 的 complete group是有限反例。
5. **“policy-held complete groups应当然随 proxy error flush”——未作此全称。** 这是我的偏好；`full` 也可被产品裁成 failure all-or-nothing，但必须同步收窄 §3。
6. **“head-of-line blocking 等于 lock deadlock”——排除。** 正常 close有单向解锁；真正问题是 final ending 没有 complete-held 处置。
7. **“复用 retry taxonomy 必须复制一份新 closed set”——排除。** 共用一张表／一个 adapter更好；缺的是 input mapping 与 unknown fallback，不是要求重复。
8. **“`ErrorCategory.UPSTREAM` 自动等于 `RetryReason.SERVER_ERROR`”——排除。** 当前只有 reason→category 反向表，倒推会把未知、cancelled与明确 5xx混在一起。
9. **“draining 返回 `None` 是 replacement upstream failure”——排除。** 新 attempt 尚未打开，origin 是本代理的 refusal。
10. **“replacement 建流前 HTTP error可以原样当 SSE event发出”——排除。** 两种 carrier 不同；用户亲笔合同已裁为转成 SSE error。
11. **“wire 也应使用 cassette header allowlist”——排除。** 没有同一个 persistence hazard，且会无依据丢失 end-to-end semantics。
12. **“header denylist只要补 `Proxy-Connection` 就完整”——排除。** `Connection` 可以动态命名任意 field，representation validator又是另一维。
13. **“所有 ETag 都必须无条件剥离”——未作此全称。** 本 finding 直接覆盖 strong ETag；weak validator是否仍代表语义等价可另按 HTTP语义处理，不用为修强 validator制造过宽规则。
14. **“改了 §7.1 解释段就等于 major closed”——排除。** signature、正例、§11 与 Plan仍在说相反的话。
15. **“修订记录里的 v2 旧描述也该改”——排除。** 它是点时历史，回改会伪造记录；只改 living normative text与当前 Plan。
16. **“P1／P2 pending merge阻断产品 Spec定稿”——排除。** 行为判据已定且实现存在；它是集成顺序，不是产品分叉。
17. **“targeted 50 tests绿证明 P1／P2全对”——排除。** 未做控制变异，也未作本轮代码验收；只记录实际跑况。
18. **“没有新线上样本就不能报状态机缺口”——排除。** round3-01／02 都由有限输入与公开接口构成，发生率不决定合同是否必须有出口。

空清单声明：以上是本轮实际考虑并排除或限定的可能性；没有把猜测的 upstream 发生率、未知敏感 header 或未来 SDK 行为写成 severity finding。

## 搜索面、执行证据与限制

### 判据来源

- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/client-side-block-delivery.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-translation.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-format-reshape.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md`
- `/tmp/260830-review-spec-round2.md`
- RFC 9110 §7.6.1、§8.8.3.3 与 RFC 9530，来自 `https://www.rfc-editor.org/`

### 被评与静态代码面

- Spec v3 与关联 Plan 全文。
- 主树当前共享路径的 `stream.py`、`retry.py`、`hand_over.py`、`openai_responses.py`、`request.py`、`inference.py`，以及本地 OpenAI SDK／httpx2 types。
- worktree `worktree-260830-sse-frame-fidelity` 的 `sse_source.py`、`stream.py`、`test_sse_assembly.py` 与提交 `8986bbf` stat。

### 执行证据与限度

- 在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-sse-frame-fidelity` 运行 targeted test：50 passed，2.11s。
- 未运行 full suite、Ruff、Pyright：本轮对象是尚未实施的 Spec v3；它们不能回答新增状态分叉。P1／P2 代码也不是本轮完整验收对象。
- 未做真实 upstream call；interleaving／unfinished／failure发生率不作结论。
- `.dev` HEAD `5e1ed49` 采用调用方给定值，未跨 isolation guard独立运行 git验证；被评 bytes 来自绝对路径 `Read` 的当前 snapshot。
- 指定 report path 的 `Write` 被 background isolation guard拒绝；按任务预案写到 `/tmp/260830-review-spec-round3.md`，没有绕过守卫。

## 严重度汇总

- blocker：2
- major：2
- minor：0
- nit：0
- finding_total：4

## 可否据此开始实现

**no。** 先闭合 round3-01 的 policy×ending 与 round3-02 的 replay adapter／replacement carrier，再修 header algorithm并同步全部 living transcriptions与 Plan。P1／P2 worktree可以作为独立前置继续走既有集成流程，但不能据此宣称 direct主体 Spec已可执行。

## 收尾判断

本轮不触发开发 closeout：可观察事实是只读评审产出了 2 条 blocker 与 2 条 major，主体实现明确未达开始条件；没有由本轮创建的 source/test改动、commit或 worktree要集成／删除。P1／P2 worktree属于另一实施单元且已有 archive ref，本报告只核其 §11 身份，不接管其收尾。

