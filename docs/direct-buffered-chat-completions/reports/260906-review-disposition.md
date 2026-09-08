# Direct buffered Chat Completions 设计评审处置

日期：2026-09-06。

评审原件：[`260906-spec-consistency-review.md`](260906-spec-consistency-review.md) 与 [`260906-technical-feasibility-review.md`](260906-technical-feasibility-review.md)。本文件记录处置，不替代living Spec。

## 用户在评审后补充的裁决

1. SSE→non-stream JSON采用标准multi-choice聚合，不保留旧CodeBuddy把choices混成一个、重造identity与静默丢字段的行为；成熟OpenAI SDK accumulator可作实现基础，但本项目Spec字段表是authority。
2. 第一个合法 `[DONE]` 后冻结semantic state、继续收raw tail；upstream-side tail ending与cap不反转成功。
3. Post-`[DONE]` tail收集遇client deadline时提交已完整body并记录tail截断，不降成失败；client cancellation仍不写。

以上已写入 [`../decisions.md`](../decisions.md) D-9～D-11。

## 规范一致性评审处置

| Finding | 处置 | 落点 |
|---|---|---|
| B-1 mode-adapted JSON合同缺失 | 采纳。新增closed capability matrix与SSE→`chat.completion`逐字段聚合表；unknown冲突与无法投影统一为具名 `unassemblable`，不让测试代替Spec | `direct-passthrough/spec.md` §9.3 |
| B-2 post-`[DONE]` precedence未闭合 | 采纳并由用户补裁。按 `done_seen` 两层列出clean EOF、tear、idle、attempt/client deadline、cap、tail semantic event、本地tail failure与cancellation | `direct-passthrough/spec.md` §5.4；`error-envelope/spec.md` §8／§10.2 |
| M-1 observation清空时点矛盾 | 采纳。拆分attempt draft、candidate与request projection；replacement建立后才切candidate，final action时promotion | `direct-passthrough/spec.md` §5.4／§10；`design.md` §10 |
| M-2 capability代数不完整 | 采纳。`response_modes`为非空闭集；四种client／endpoint mode组合闭合；streaming extension改名为absent-default，显式值优先 | `direct-passthrough/spec.md` §9.3；`xingchen/spec.md` §4／§5；`design.md` §4 |
| M-3 error识别／冲突／non-stream carrier不唯一 | 采纳。先识别三种carrier，再以所有非空code/type一致命中为retry条件；冲突／unknown不retry；定义429／502与nested／flat／malformed JSON carrier | `direct-passthrough/spec.md` §5.4；`error-envelope/spec.md` §8 |
| M-4 Chat observation schema不完整 | 采纳。新增独立 `chat` payload、choice／tool结构、absent/null/unreadable、unknown、issue与console精确拼法 | `tui/spec.md`“Chat provider observation schema” |
| M-5 client-leg README仍把所有Responses写成旧framer | 采纳。按direct／translated分行，`ResponsesFramer`与自铸id明确只属于translated projection | `client-leg-formats/README.md` §二／§三 |
| M-6 retry status的499陈述过期 | 采纳。核对当前人控文档、`RETRYABLE_STATUSES`与可达提交 `39274d7` 后改写current摘要 | `upstream/retry-and-continuation/status.md`开头 |
| m-1 人控文字与Spec推导混写 | 采纳。拆开人控明示与comment／Chat commit frontier推导 | `direct-buffered-chat-completions/decisions.md` |
| m-2 把额外用户复核写成项目门禁 | 采纳。Status改为当前会话brainstorming步骤与独立复评，不冒充产品／项目审批规则 | `direct-buffered-chat-completions/status.md` |

## 技术可实施性评审处置

| Finding | 处置 | 落点 |
|---|---|---|
| B-01 runner与DirectDriver双重retry owner | 采纳。`BufferedAttemptCollector`只处理单attempt；pre-success由DirectDriver唯一消费ledger，post-header由delivery runner唯一消费；新增body-phase prepared retry seam | `direct-passthrough/spec.md` §5.4；`design.md` §6／§7 |
| M-01 client/upstream stream混槽 | 采纳。`RequestContext.stream`只存client contract；attempt-local `ChatSendPlan`另存 `upstream_stream`与final payload | `direct-passthrough/spec.md` §9.3；`design.md` §4／§7 |
| M-02 synthetic response冒充raw exchange | 采纳。Raw request/status/headers/version/connection/SSE bytes与client JSON projection分槽，raw response由collector明确关闭 | `direct-passthrough/spec.md` §9.3.2；`design.md` §6／§7／§9 |
| M-03 event rate-limit没有limiter seam且headers先记success | 采纳。增加明确event-rate-limit callback；buffered transaction的limiter success延后到body verdict，下一attempt沿用 `acquire()` | `direct-passthrough/spec.md` §5.4；`design.md` §8 |
| M-04 observation reset/promotion | 与规范评审M-1合并采纳 | 同上 |
| M-05 unknown error误归network、aggregation静默丢内容、frame边界缺失 | 采纳。先识别carrier；unknown/malformed error不retry；adaptation有 `unassemblable`；collector保留raw frame offsets | `direct-passthrough/spec.md` §5.4／§9.3；`design.md` §5／§8 |
| M-06 post-`[DONE]`状态不完整 | 与规范评审B-2合并采纳并由用户补裁 | 同上 |
| M-07 translated assembler混合multi-choice | 发现成立，但不在direct任务中改变translated client行为；显式登记独立未闭合项，reader可共享而projection不暗改 | `direct-buffered-chat-completions/deferred.md` D-2；`design.md` §5／§10 |
| M-08测试不足以判别double retry等 | 采纳。增加调用次数／ledger／payload/admission、mode分槽、timeout层次、cleanup、raw accounting、limiter、unknown error与post-terminal矩阵断言；不让black-box test冒充“只解析一次”证明 | `design.md` §12 |
| m-01 capability语义 | 与规范评审M-2合并采纳 | 同上 |
| m-02 durable schema容器 | 与规范评审M-4合并采纳 | 同上 |
| m-03 CodeBuddy `extra_headers`未传 | 采纳为provider boundary slice内的既有缺口，要求component test；不把当前状态说成已满足 | `design.md` §4.3／§11／§13 |
| m-04 人控归因写宽 | 与规范评审m-1合并采纳 | 同上 |

## 规范复评追加处置

复评报告：[`260906-spec-consistency-rereview.md`](260906-spec-consistency-rereview.md)。初审blocker已清零，复评剩余2 major／1 minor均采纳：

1. R-1：§9.3.1删除“其它已知top-level snapshot字段”，last-wins集合封闭为 `service_tier`／`system_fingerprint`／`moderation`；所有未枚举字段按原JSON层级进入unknown规则，SDK类型升级不得扩大集合。
2. R-2：error-envelope §8补齐 `event:error` 已确认但payload不含top-level `error`／`type:"error"` 的parsed object；整个object作为标准envelope的 `error` 值，429／502规则不变。
3. n-1：Design把capability default类型收窄为 `Literal[True] | None`，不允许未定义的false descriptor值。

这些修订不需要新的用户产品裁决；它们只闭合已确认合同中的集合与carrier缺格。

## 技术复评追加处置

复评报告：[`260906-technical-feasibility-rereview.md`](260906-technical-feasibility-rereview.md)。初审finding全部在设计层闭合，复评新增1 major／2 minor均采纳：

1. NEW-M-01：mode矩阵不再复用endpoint-empty语义的 `CapabilityMissing`；新增typed `ResponseModeNotSupported`，携带provider、model、requested mode与available modes，映射 `CLIENT`／400／`unsupported_response_mode`。
2. NEW-m-01：final payload唯一authority确定为 `Attempt.payload`；`ChatSendPlan`只保存client/upstream mode与capability snapshot，prepared retry从attempt payload建立private copy。
3. NEW-m-02：统一capability字段名为 `ChatEndpointCapabilities.provenance`；Xingchen pseudo descriptor同步写 `chat.provenance`。

## 最终复评结果

- [`260906-spec-consistency-final-rereview.md`](260906-spec-consistency-final-rereview.md)：0 blocker、0 major；R-1、R-2、n-1全部closed。
- [`260906-technical-feasibility-final-rereview.md`](260906-technical-feasibility-final-rereview.md)：0 blocker、0 major、0 minor；`ResponseModeNotSupported`、final payload authority与provenance字段三项全部closed。

当前书面design／living Specs已形成独立评审共识。报告是时点证据；行为authority仍是各living Spec。

## 未采纳／不在本次实施的建议

没有拒绝任何经验证成立的finding。以下路线仍不采纳，理由未因评审改变：

1. Chat block-level incremental delivery、Chat continuation与新的Chat streaming proxy error frame仍按既有用户裁决推迟；terminal-only replay不依赖它们。
2. 不让provider继续做内容aggregation，不在pipeline按provider名称分支，不把所有Chat target强制成streaming。
3. 不运行真实CodeBuddy P6或Xingchen canary；用户已选择本次暂不实测，capability保留明确provenance。
4. 不建立proof gate、schema registry或新的验证治理层；现有typed records、targeted tests与独立评审足够。
5. Translated Chat→Anthropic multi-choice projection不在本次direct范围；成立的问题进入deferred D-2，不以TUI presentation规则替它作产品决定。
