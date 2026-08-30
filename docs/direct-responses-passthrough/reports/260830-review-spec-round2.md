# 直连 Responses 原生透传产品规格独立复评（round 2）

- report_id：`direct-responses-passthrough-spec-review-round2`
- attempt_id：`260830-review-spec-2`
- reviewed_at：2026-08-30
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v2）与同目录 `plan.md`（v2）
- 对照基线：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260830-review-spec.md`
- 评审性质：只读规格与计划复评；未修改 `src/` 或 `tests/`；未派 agent

## 评审范围

本轮先以第一轮八条 finding、用户亲笔的 `message-translation.md`、`client-side-block-delivery.md`、`upstream-retry-and-continuation.md`、`config.example.yaml`，以及 `error-envelope/spec.md`、`delivery-keepalive/spec.md` 建立判据，再读取 Spec v2 与 Plan v2。复核范围包括八条发现的逐条处置、v2 新增的全局 queue／commit frontier、control-event commit、attempt replay、`requires_client_action`、未闭合项、non-stream fidelity、observability、provenance 与现有 `stream.py` 状态机的接线面。

静态代码搜索面覆盖 `delivery/stream.py`、`delivery/assembling.py`、`delivery/blocks.py`、`delivery/sse_source.py`、`delivery/sse_frame.py`、`delivery/formats/openai_responses.py`、`delivery_policy.py`、`retry.py`、`hand_over.py`、`request.py`、`driver.py`、`reply.py`、`server/routes/inference.py`，并核对本地 `openai==3.3.1` 的 `ResponseOutputItem`、`ResponseToolSearchCall`、`ToolSearchToolParam`、`ResponseFunctionShellToolCall` 等声明。

明确不在范围内：修改被评文档、实施生产代码、修改或运行测试、真实 Copilot 调用、穷尽所有 OpenAI 客户端行为、重新评审 Anthropic bridge 自身的 response matrix、生产 4141 服务的任何操作。

## 总体 verdict

**needs-fix。不可据此开始实现。blocker 数：3。**

v2 确实关闭了大部分第一轮问题，但不是“blocker 3 + major 5 全部闭合”：八条中 5 条 closed、3 条 partially-closed。当前仍有三处行为合同要求实现者自行裁定：未完成 item 位于 terminal／failure 之前时无法同时满足完整单位、逐事件保真与原序；直连 response-header 过滤表仍未定义且 streaming 面也未纳入；replay 对 native failure／clean EOF 的分类以及 replacement attempt 自己失败时谁的错误可见仍无闭合状态转换。另有一条 major：§7.1 把 action 判据绑定到 `original_request`，而当前 SDK 的 response item 自己已经携带 `execution`／`environment`，该绑定既无依据又可能读取错误版本的请求。

## 第一轮八条发现处置总表

| finding_id | 上轮级别 | 状态 | 复核判据 | 结论摘要 |
|---|---:|---|---|---|
| `direct-responses-passthrough-spec-review-01` | blocker | partially-closed | `data` 保真与字段改写不能冲突；全局顺序必须有对所有 ending 闭合的 frontier | 已取消全部字段改写并新增 frontier；但未完成 item 遇 terminal／failure 的状态没有合法出口，见 round2-01 |
| `direct-responses-passthrough-spec-review-02` | blocker | partially-closed | control event 的 commit、首个 commit 前后 replay、replacement reset 与 post-commit ending 均须唯一 | commit 时点与 reset 已写；native failure／clean EOF／replacement failure 的状态转换仍缺，见 round2-03 |
| `direct-responses-passthrough-spec-review-03` | blocker | closed | `until-tool-use` 的语义 predicate、正反例、unknown fallback 与触发时点必须由 Spec 定 | §7.1 已给出 predicate、正反例、unknown→release 与一次性转态；数据来源错误作为新 major 单列，不推翻 predicate 本身已定 |
| `direct-responses-passthrough-spec-review-04` | major | closed | fidelity 必须限定为合法 UTF-8 SSE parsing 后的 logical event/data，并正视 multi-line writer 与 CRLF parser 缺陷 | §3／§3.1 已准确收窄承诺并把两个反例列为前置；Plan P1/P2 同步 |
| `direct-responses-passthrough-spec-review-05` | major | partially-closed | non-stream fidelity level、status 与 headers 都必须成为合同 | JSON value fidelity 与 status 已定，现状陈述已纠正；header 表仍空缺且 streaming 面未定义，见 round2-02 |
| `direct-responses-passthrough-spec-review-06` | major | closed | 原第 3、4 项应正文定案，第 5 项应移出 direct 定义域，真正行为决定不得藏在待办 | cap 口径与 carrier gate 已进正文，`function_call_output` 已移出；本轮新发现的待办误分类另见 §11 复核 |
| `direct-responses-passthrough-spec-review-07` | major | closed | 8 月 30 日原话只归属 rejection 命题；native 方向与精确 fidelity 必须拆 provenance | §2.1～§2.3 拆分准确，原文复核通过，见 provenance 专节 |
| `direct-responses-passthrough-spec-review-08` | major | closed | Spec 要定义 wire／observability 分离，Plan 不得继续 final-snapshot、mint-id、重成帧旧方案 | §10 已成最小合同；Plan v2 已撤销 v1 的 final-snapshot／mint／合成 terminal 路线，未再出现相反行为承诺 |

状态计数：`closed=5`、`partially_closed=3`、`not_closed=0`。

## 当前系统状态：新发现与残留发现

### direct-responses-passthrough-spec-review-round2-01

- finding_id：`direct-responses-passthrough-spec-review-round2-01`
- severity：`blocker`
- primary_location：`spec.md:61-65,87-98,100-116,134-138,170-176`
- related_locations：`docs/.human-controlled/client-side-block-delivery.md:3-5,15-21`；`docs/.human-controlled/config.example.yaml:374-393`；`plan.md:29-37,51-54`
- 标题：未完成 item 位于 terminal／failure 之前时，完整单位、逐事件保真与原序三项无法同时成立

**证据。** §3 对“属于本响应的每一个 SSE 事件”承诺 logical `event`／`data` 逐字重放；§4 又规定只有涉及的全部已打开 item 都已 `done` 才能推进连续 prefix；§6.3／§8 要求 terminal 或 upstream failure 若最终可见则在原位置逐字。构造合法于当前文字但未被状态机定义的序列：`response.created → output_item.added(A) → delta(A) → response.failed`，其中 A 永不 `done`。A 的 events 不能交付，因为用户亲笔的块级合同把 `_start` 到 `_end` 之间的完整区间定义为交付单位；`response.failed` 又不能越过 A 提前交付，否则发生重排；若连 A 一起发则交付了不完整 item；若丢掉 A 再发 failure，则违反 §3 的“每一个事件”承诺。普通 `response.completed` 落在同一矛盾中，§7 的 `full`“终局后全部发出”也没有说明它是否能越过 §4 的未完成 item 门。

**关于死锁与上界的专项结论。** 这不是 lock 层面的 deadlock：没有循环等待，只有更早未完成 item 对后续 prefix 的 head-of-line blocking，解锁条件完全取决于上游发 `done`。在默认 `buffer_cap_bytes=16MiB`、`client_request_deadline=3600` 下，resident bytes 与等待时间分别有外部终止器，不会无限增长或永久等待；但两个配置都允许取 0，分别明确表示 unlimited／disabled。该合法配置下，上游若持续给 A 发数据而永不 `done`，queue 可无界增长；若静默而所有 deadline／idle guard 也关闭，则可永久持有。这个“配置选择可取消上界”本身已有用户亲笔依据，不冒充新缺陷；真正的 blocker 是 terminal／failure 已到达时仍没有一个满足三项合同的合法 ending。

**影响。** 实现者只能擅自选一项牺牲：泄漏不完整 item、重排 terminal／failure、丢弃已收 events，或 terminal 已到后仍不结束。cap、deadline、client cancel 也要求丢弃未完成 suffix 后发 proxy error，当前 §3 的全称同样没有给这个例外。

**建议。** 在 Spec 明确“保真承诺只覆盖被选中 attempt 中最终可提交的完整 item groups、control 与 terminal／failure；未闭合 item 的 raw suffix 在 tear、terminal、failure、cap、deadline、cancel 时丢弃且不算重排”，并定义 failure／terminal 如何截断 queue。若产品反而要求连未完成 item events 都保留，就必须明示放弃块级完整单位；不能继续同时承诺两者。另应明确 terminal 是否能证明未知 lifecycle 已完成；我的偏好是不能，未知边界只能按不完整 suffix 丢弃，因为 failure terminal 明确可能在 item 未完成时到达。

**证据强度。** 同一 Spec 的三条规范与用户亲笔块级合同可静态构成反例，强到足以阻断；“默认配置有界、0 配置无界”由配置原文直接支持。真实上游发生率未测量，不影响状态必须有定义。

**承重前提检查。** 前提是“terminal 到达自动让此前所有 events 成为安全 prefix”；它若为真才能同时执行 §4 与 §6.3。规格没有写这条，而 `response.failed` 本身就是反例：它只能证明 response 结束，不能把一个未收到 `done` 的 item 变完整。

### direct-responses-passthrough-spec-review-round2-02

- finding_id：`direct-responses-passthrough-spec-review-round2-02`
- severity：`blocker`
- primary_location：`spec.md:178-184,194-200`
- related_locations：`spec.md:100-116`；`docs/.human-controlled/client-side-block-delivery.md:7-10`；`docs/.human-controlled/message-format-reshape.md:51-63`；`src/app/server/routes/inference.py:491-522,524-573`；`plan.md:65-81`
- 标题：response-header 过滤仍是未决的用户可观察行为，而且 streaming 面没有定义

**证据。** §9 已明确承诺“response headers 按一张明确的直连腿过滤表保留语义头”，紧接着承认该表未列并把它留在 §11。这个选择决定 `request-id`、rate-limit、`retry-after` 等客户端实际收到什么，不是 raw-text encoder 一类实现细节。用户亲笔的 `client-side-block-delivery.md` 又规定 streaming 只转发第一次 HTTP 200 attempt 的响应头，后续 attempt 的 HTTP 错误只能转成 SSE error；因此表至少还必须回答“第一次 200 的哪些头”。现有 `message-format-reshape.md` 第 51～63 行标题和内容明确写的是“客户端返回 Anthropic Messages”，不能不经裁定直接扩成 Responses 成功响应的表。

当前代码也没有偶然替规格作答：non-stream 只构造 `JSONResponse(payload, status_code=...)`，stream 只构造 `_AccountedStreamingResponse(..., status_code=..., media_type="text/event-stream")`，两处都没有转发 upstream semantic headers。§9 只放在“非流式”章节，§5 对 streaming header 只说“不提交 native attempt”，所以即使补完 §11 第 1 项的字面位置，streaming 仍可能继续丢全部 semantic headers而不违反正文。

**影响。** 实现者必须自行决定是否复用 Anthropic 黑名单、采用新 allowlist、两种响应模式是否同表、第一次 200 attempt 的 `request-id` 是否保留。不同答案会改变 SDK 的限流、退避与请求关联行为。项目规则要求完整行为 Spec 先于实现，故这不是可边做边定的非阻断项。

**建议。** 在正文定义同格式 Responses direct leg 的成功响应头合同，并同时覆盖 streaming 与 non-stream：明确第一 HTTP 200 attempt 是 streaming headers 的唯一来源，replacement attempt 不覆盖已提交 headers；列出 hop-by-hop／reframing 头的剥离规则与 semantic headers 的保留规则。若决定复用既有直连黑名单，需由新条款显式扩展其适用方言，不能靠 `error-envelope/spec.md` 对错误面的引用或 `message-format-reshape.md` 的 Anthropic 标题暗推。

**证据强度。** Spec 自己明确标注表缺失，且人写文档证明 streaming 的 attempt 选择会影响 header 来源，强到足以阻断完整范围实现。

**承重前提检查。** 前提是“headers 只属于局部 writer 细节”；它支撑把 §11 第 1 项称为不阻断。`Retry-After` 与 rate-limit 会改变客户端动作，`request-id` 决定关联对象，故前提不成立。

### direct-responses-passthrough-spec-review-round2-03

- finding_id：`direct-responses-passthrough-spec-review-round2-03`
- severity：`blocker`
- primary_location：`spec.md:100-116,170-176`
- related_locations：`plan.md:51-54`；`src/app/pipeline/delivery/stream.py:70-90,367-504,506-574`；`src/app/pipeline/retry.py:99-158`；`src/app/pipeline/hand_over.py:41-53`；`src/app/server/routes/inference.py:395-461`
- 标题：Replay 写了 commit 边界，却没有闭合 native failure／clean EOF／replacement failure 的状态转换

**证据。** §5 允许首个 native event 提交前对“transport tear、无终局 EOF、可重试 upstream failure”做透明 replay，却没有定义 native failure event 如何映射到现有 `RetryReason`，也没有定义 replacement attempt 自己在建流前以 HTTP failure／refusal 结束、或因 draining 返回 `None` 时，客户端最终看见旧 attempt 的 failure、replacement failure，还是 proxy error。这个选择直接决定哪个 attempt 的原文可见；尤其 §5 同时说一旦 replay 就把旧 attempt 的 terminal／ids／usage 全部丢弃，不能在 replacement 失败后不加说明地回头重放旧 failure。

现有状态机证明这不是把新 assembler 塞进去即可接上：`ReplaySupport.eligible` 只接 `Exception`；`replay_reason()` 同样只分类 exception。`ResponsesAssembler` 把 `response.failed`／`response.cancelled`／`error` 记成 `StreamFailure`，而 `_deliver` 在读到它时立即 `_report_failure()` 后 `return`，完全绕过 replay。clean EOF 令 `_events_with_ping` 正常结束，`torn is None` 后直接 `break`，到尾部只走 terminal-less ending，也完全绕过 `decide_stream_ending()`。replacement 的 `Attempt | None` 又只携带 fresh bytes／assembler／buffer，`None` 同时覆盖 draining、不再是 stream、没有 response 等不同结局，无法把 replacement failure 交给 wire policy。

**与现有 `stream.py` 能否接上的裁定。** 能接，但必须重构中央状态机，而不是 Plan §5 所说“没有现成代码可改”。至少要把 replay candidate 从 exception 扩为 typed ending（transport exception、unterminated EOF、native failure event），让 eligibility 对三类各有明确映射；让 replacement 结果携带其失败而不是压成 `None`；并把 direct attempt 的 queue／frontier／observability record 连同 fresh source 一起 reset。当前 `Attempt = tuple[bytes, UpstreamSource, BlockAssembler, BlockBuffer]` 与 `BlockAssembler → CompletedBlock`／`BlockBuffer` 接口都绑定 Anthropic block 路径，Plan 新设的 raw-event delivery unit 也必须进入这些接口或走一条并列的 direct delivery loop。

**影响。** 按当前文字，两个实现都能自称合规：一个把所有 native failure events 当不可 replay 并原样发旧 attempt；另一个按 `ErrorInfo.category` 或字符串猜 retryability、丢旧 attempt 后在 replacement 失败时发新 proxy error。它们在 attempt 数、最终错误原文、id／usage 与可观测来源上相反。clean EOF 也可能继续沿用今天“不 replay”的行为，直接违反 §5 的表面承诺。

**建议。** Spec 应补一张 ending transition：每种 pre-commit ending 的 retry reason 来源、budget exhausted 的 visible ending、replacement 在 headers 前失败／返回非-stream／draining refusal 的 visible ending，以及旧 attempt 在何一刻不可恢复。我的偏好是：clean unterminated EOF 明定为 network replay candidate；native failure 先按 `error-envelope/spec.md` 的 response error reader 得到 typed condition/category，再由一张显式映射决定 retry reason；replacement 一旦实际开出新 attempt，旧 native events 永久丢弃，最终暴露 replacement 的失败。偏好不是既有裁决，需由 Spec 作者按现有重试 authority 定案。

**证据强度。** 现有 callable 类型与控制流是静态强证据；“最终该暴露哪个 failure”没有现成权威给唯一答案，正因而是必须先闭合的产品分叉。没有运行探针，不能声称某一 replacement failure 已在生产发生。

**承重前提检查。** 前提是“现有 replay taxonomy 已能直接分类所有三类 ending，`reopen(None)` 也只有一种含义”；源码分别证明 taxonomy 只接 exception、`None` 有多条来源，前提为假。

### direct-responses-passthrough-spec-review-round2-04

- finding_id：`direct-responses-passthrough-spec-review-round2-04`
- severity：`major`
- primary_location：`spec.md:154-168,194-200`
- related_locations：`plan.md:45-50`；`.venv/lib/python3.14/site-packages/openai/types/responses/response_tool_search_call.py:11-28`；`.venv/lib/python3.14/site-packages/openai/types/responses/tool_search_tool_param.py:11-24`；`.venv/lib/python3.14/site-packages/openai/types/responses/response_function_shell_tool_call.py:45-73`；`src/app/pipeline/request.py:58-94`；`src/app/pipeline/driver.py:82-190`
- 标题：`requires_client_action` 被不必要地绑定到原始 request，而且没有规定 request 与 response 冲突时谁权威

**证据。** §7.1 断言判定“需要原始请求的 tool declaration 与 execution mode，不能只看 response item”，§11／Plan 因此新增一条 request→delivery 数据通路待办。当前 `openai==3.3.1` 的 `ResponseToolSearchCall.execution` 却是 required `Literal["server", "client"]`；`ResponseFunctionShellToolCall` 也直接携带实际 `environment`。其余当前正例由 response type 自身已经决定（`function_call`、`custom_tool_call`、`computer_call`、`local_shell_call`、`apply_patch_call`、`mcp_approval_request`），当前反例同理。也就是说，本轮给出的唯一“同 type 得相反答案”反例不需要回查 request，closing item 自己就有答案。

更重要的是，`RequestContext.original_payload` 按合同是客户端送达、任何整形之前的对象；实际 upstream payload 会经过 route shaping、model rewrite、subscriber 等步骤。若 response item 与 client-original declaration 不同，当前 Spec 既要求看两者又没定 precedence。实现者读取 `original_request` 可能否定 upstream response 自己明确写出的 `execution:"client"`，把 action item 扣到 terminal；反向也可能把 server-executed item误作 client action而提前释放。

**影响。** 这不会推翻第一轮 finding 03 的核心 predicate、正反例与 unknown fallback已经闭合，但会使其编码在真正出现 request／response 差异时产生相反 release 行为，也凭空增加一条跨层数据依赖。因此定为 major，而不是把上一轮 blocker 重新计一次。

**建议。** 把判据改为先读 closing response item 的规范字段：`tool_search_call.execution`、`shell_call.environment` 与 item type；字段缺失、无效或未来类型则走已经定好的 unknown→release。只有能给出一个 response item 无法承载、而 request 确实决定 client action 的具体类型时，才把“实际送往 upstream 的 attempt payload”作为补充输入，并明确 response／request precedence；不要用 `original_payload`。§11 第 3 项据此可以关闭或移到 Plan 的纯接线事项。

**证据强度。** SDK 3.3.1 的 generated models 对 `tool_search_call.execution` 是直接静态证据，强到足以否定“当前必须回查原始 request”的全称；未来协议是否新增 request-only 判据未验证，故不外推为“永远不需要 request”。

**承重前提检查。** 前提是“response item 只告诉 type，不告诉执行位置”；它支撑新增跨层数据通路。当前 SDK 的 required `execution` 与 response `environment` 直接证伪该前提。

## §4 commit frontier 与 §5 replay 专项结论

### §4 的内部一致性与 liveness

- **正常交错可以保持顺序。** 当所有 item 最终都有 `done` 时，单调 prefix 能让后来完成的 item 等较早未完成 item，最终一次释放连续区间；不需要改写 `sequence_number` 或 `output_index`。这一结论强到可据此实现正常路径。
- **“拖住而不重排”不是内部 deadlock，但确实是 head-of-line blocking。** progress 依赖 upstream closure event，不依赖本地另一个锁。默认 cap／client deadline 给出终止器；显式把它们都设为 0 就主动选择无 memory／time 上界。此处不把“管理员选择 unlimited”误报成实现 bug。
- **terminal／failure 到达而 item 未 `done` 时合同不闭合。** 这不是发生率问题，而是一条有限输入就能到达的状态；详见 round2-01。未闭合 suffix 的丢弃规则必须进入 Spec。
- **未知 event 的“持有到 terminal”不是 release rule。** §4 第 96 行只给持有时点，没有说明 terminal 到达后它属于完整 group、丢弃 suffix，还是连同 terminal 释放。不能让实现者从“持有到”自行推导“terminal 证明完成”。

### §5 与现有状态机的接线

当前 `stream.py` 的 replay 骨架可以复用 shared ledger、fresh attempt reset、`client_has_bytes` 持久状态与 `last_write` 计时，但 direct contract 不能靠换一个 assembler/framer 落地。必须改造的承重点至少有：

1. `BlockAssembler.push() → CompletedBlock` 与 `DeliverySession/BlockBuffer` 只表达 Anthropic block，不能携带 control events、raw event groups 与 direct commit frontier。
2. `StreamFailure` 当前先写 wire 后立即结束，native failure event 没有进入 replay 决策。
3. clean EOF 不构造 exception，因此今天不会进入 `decide_stream_ending()`。
4. replacement `Attempt | None` 不携带 replacement failure，无法兑现“旧 attempt 全丢弃后最终谁可见”。
5. `_StreamAccounting` 通过替换当前 assembler 丢弃旧 summary，只另存 exception 型 `replaced_failures`；native failure event replay 还需要一条独立 operational record，才能满足 §10。

因此答案是：**技术上能接，但 Plan v2 描述的改造面不足，且 Spec 的 ending transition 必须先闭合。**

## §11 未闭合项复核

| §11 项 | 是否阻断 | 判定 |
|---|---|---|
| 1. direct response-header 过滤表 | **阻断** | 用户可观察行为，且目前只挂在 non-stream 章节，streaming 第一次 200 attempt 的 header contract也未覆盖；见 round2-02 |
| 2. raw-text encoder 形态、CRLF 影响面 | 不阻断 | §3／§3.1 已把 logical fidelity 与两个失败反例定清；函数放哪、parser 如何切边界是实现设计。事实上正文与 Plan 已给出 `(event,data)` 和逐 `data:` 行编码的足够判据，宜从 Spec“未闭合项”移到 Plan |
| 3. `requires_client_action` 的 request 数据通路 | 不阻断，但当前依据不成立 | 这是接线而非未决行为；且 SDK closing item 已携带 `execution`／`environment`。应按 round2-04 修正文档后关闭，而不是继续让 Spec 显得未定 |

§11 漏回去的阻断项有两组：round2-01 的未完成 item ending，以及 round2-03 的 replay ending transition。header 项本身也漏掉了 streaming 半面。故“只剩三项且都不阻断”不成立。

## Plan v2 与 Spec v2 对齐复核

### 已对齐

- v1 的 final `done.item` snapshot、重生 `added`／`done`、mint ids、自编 `output_index` 与 synthetic terminal 已全部撤销。
- P1／P2、raw `(event,data)` framing、全局 queue／frontier、三种 policy、observability 旁路、翻译腿继续 `UNKNOWN→REJECT` 均指回 Spec，没有新增用户可观察承诺。
- Plan 没有把翻译腿的 `function_call_output` 能力重新塞进 direct 定义域。

### 未对齐或不足

1. Plan §5 说“这一块没有现成代码可改”，与源码相反：现有 `_deliver`、`ReplaySupport`、`decide_stream_ending`、`_reopen` 正是必须改的中央状态机。它不是空白实现，而是需要把 block／exception-only 合同泛化或并列化。
2. Plan 没有一个步骤关闭 response headers／non-stream 路径，也没有覆盖 streaming 第一次 200 attempt 的 headers；照其七步走完仍违反 Spec §9。
3. Plan 没有安排未完成 item suffix 遇 failure／terminal／cap／deadline 的 ending；照“所有 raw events排队”实现会在 round2-01 的有限序列上停住或违约。
4. Plan 的 replay 步骤没有列 native failure、clean EOF 与 replacement failure 三条不同入口，且验收清单只写“首个 event 前后 replay 差异”，不足以防止只有 transport exception 接上线的假完成。
5. Plan §4 继承了 `original_request` 数据通路，但当前 SDK 证据支持优先读 response item；这条不应在实现计划中固化为跨层依赖。

Plan v2 **没有出现 Spec 之外的新 wire 行为承诺**；问题是中央状态机与 headers／ending 的实施面遗漏，而不是再一次与 Spec 正面相反。因此它的 verdict 是 needs-fix，不单独新增 severity finding。

Plan 第 68 行称骨架会让 issue #1／#2 的 direct 复现转绿，第 75 行又要求第 7 步前不改当前 rejection assertions。两句只有在“复现用例”与“当前两条测试”不是同一组时才能同时成立；文档没有给 test path，静态材料不足以判定，故记为**待澄清但不计 finding**，没有把猜测制造成配额。

## Provenance 逐字复核

### `message-translation.md`

原文第 7 行是：**「对于直连路径，采用尽可能原样转发的原则。当我们需要理解和处理时，才分析和处理对应部分。」** Spec §2.2 只把它概括为“直连尽可能原样转发”，并与另一条依据共同支持 native 方向；没有把“尽可能”偷换为 byte-exact，也没有隐去“需要理解和处理时”的例外。归属与范围准确。

### `error-envelope/spec.md` 保存的 2026-08-23 原话

原文第 35～38 行是：**「1. 直连路径一定用原生的，即使我们未知，也能传递；2. 翻译路径，按需建立 IR 机制……」** Spec §2.2 引用的第 1 条逐字一致。该原话位于错误信封的裁决上下文，单独最多直接管 error surface；与用户亲笔 `message-translation.md` 合用，可以支撑全 direct leg 的 native 方向，但不能推出 event-level exact fidelity。Spec §2.3 正好把 fidelity、id、ordering、predicate、observability 标为本规格推导，未再次超范围。

### 2026-08-30 原话

本轮可用的一手上下文与第一轮报告都把原话限定为**「协议允许，凭什么拒绝？」**，只支持“不认识不是 rejection reason”。Spec §2.1 明说不支持丢弃、字段改写与 id fidelity，并把后者移到 §2.2／§2.3，处置准确。当前文件称其为“逐字锚”但没有给 transcript／message id；这降低跨会话可追溯性，不改变本轮由用户任务直接确认的 scope，故不计 severity finding。若有可持久解析的会话锚，建议补上。

**Provenance verdict：pass。** 证据强度足以支持 native 方向与 attribution 拆分，不足以把精确 fidelity 倒签为用户裁决；v2 没有这样做。

## 显式排除掉的可能性

1. **“取消 sequence／output-index 改写后，第一轮 finding 01 就全部关闭”——排除。** 字段矛盾已关，但 unfinished suffix 与 terminal 的状态冲突仍在。
2. **“拖住必然是 deadlock”——排除。** 本地没有循环等待；它是 upstream-controlled head-of-line blocking。
3. **“默认 cap 与 deadline 仍可能让 resident queue 永久无界”——排除。** 默认值分别提供 memory／time 终止；无界只在管理员显式把相应上界设为 0 时成立。
4. **“terminal 天然证明所有 earlier items 完整”——排除。** `response.failed` 可以结束 response 而不提供缺失的 item `done`，不能据此满足块完整定义。
5. **“HTTP 200 headers 不 commit native attempt，所以客户端什么都没看到”——排除。** 人写合同明确第一次 200 headers 已转发；它只是不使 SSE attempt body 失去 replay 资格。
6. **“Anthropic response-header 黑名单可自动套给 Responses”——排除。** 权威文件的小节定义域明确写 Anthropic Messages，没有跨方言扩张授权。
7. **“现有 replay 只差一个 mode flag”——排除。** failure event、clean EOF 与 replacement failure 分别绕过或超出 exception-only 接口。
8. **“`reopen(None)` 只有 draining 一种含义”——排除。** 现有 `_reopen` 还对 no response 与 non-stream replacement 返回 `None`。
9. **“`tool_search_call` 必须回查 request 才知道 execution”——排除。** SDK 3.3.1 response type 自带 required `execution`。
10. **“未来永远不需要 request context”——未作此全称。** 本轮只证明当前列出的唯一动态反例可由 response item回答；未来新增 request-only 语义仍可在取得具体类型后扩展 predicate。
11. **“Plan v2 又引入了 Spec 外的新 wire promise”——排除。** 未发现新增 promise；Plan 的缺陷是遗漏和错误估计接线面。
12. **“三项 §11 都阻断”——排除。** 只有 headers 是未定行为；encoder layout 与数据通路属于实现设计，其中后者当前还建立在错误事实之上。
13. **“第一轮八条必须全 closed 才能发现新 blocker”——排除。** 逐条处置与当前系统状态分开检查；round2-01／03 正是 v2 新状态机引入或暴露的问题。
14. **“旧 full regression 绿可证明新 frontier/replay 正确”——排除。** 尚无实现，且现有状态机根本没有这些入口；本轮未拿旧测试替代合同评审。

空清单声明：以上是本轮实际考虑并排除或限定的可能性；没有把未取得静态依据的 upstream 发生率猜测写成 severity finding。

## 搜索面、证据限制与工具摩擦

- 判据来源：第一轮报告、`docs/.human-controlled/{message-translation.md,message-format-reshape.md,client-side-block-delivery.md,upstream-retry-and-continuation.md,config.example.yaml}`、`.dev/docs/{error-envelope/spec.md,delivery-keepalive/spec.md}`。
- 被评对象：Spec v2 与 Plan v2 全文。
- 代码面：本报告“评审范围”列出的文件与本地 OpenAI SDK generated types。
- 未运行 tests／probe：这是规格复评，核心反例可由有限 event sequence 与现有类型／控制流静态闭合；没有把未执行结果写成“测试验证通过”。
- Bash 在首次只读 revision/hash 探测时被 isolation guard 拒绝；遵照任务提示没有绕过，之后只用 `Read`。因此主仓 `ca777df`、`.dev` 仓 `029eb64` 采用调用方给定值，**未独立验证**；报告中的代码结论是读取共享路径当前内容所得的静态 snapshot。
- 指定 report path 的 `Write` 同样被 isolation guard 拒绝；按调用任务预案写到 `/tmp/260830-review-spec-round2.md`。
- 没有真实 upstream call，故未断言 unfinished／interleaved item 的线上发生率；finding 只依赖状态空间必须有定义。

## 严重度汇总

- blocker：3
- major：1
- minor：0
- nit：0
- finding_total：4

## 可否据此开始实现

**no。** 至少先修 round2-01、round2-02、round2-03，并同步 Plan；round2-04 应在实现 `until-tool-use` 前修正，否则会把错误的数据来源固化进接口。

## 收尾判断

本轮不触发开发 closeout：可观察事实是本次只产出一份只读评审报告，既没有实现／提交／worktree 需要集成或清理，也没有临时 probe 资产；三个 blocker 明确交回规格作者继续修订，当前边界是“评审完成、产品工作未完成”，不是可归档并宣称整个功能完成的边界。

