# Direct buffered Chat Completions 书面设计一致性独立评审

日期：2026-09-06。

评审对象：`/home/xp/src/ghc-api-proxy-py` 当前 active `.dev/docs/` 与用户指定的 `docs/.human-controlled/` 文档。本文是时点评审报告，不是行为权威；所有规范修正仍应回到对应 living Spec。

## 结论

**当前书面设计不应直接进入实施计划。** 本轮发现 **2 项 blocker、6 项 major、2 项 minor**。阻断点不是方案方向错误，而是两个核心行为仍不能只凭 living Spec 得到唯一实现：其一，streaming-upstream→non-stream Chat JSON 的聚合合同把字段保真留给“现有实现／测试”决定；其二，`[DONE]` 后继续读尾部时，各种终止与保护事件相对“已成功”的优先级没有闭合。

方向性结论同时明确：现有设计**没有**意外重开 Chat block-level incremental delivery、Chat continuation 或 Chat streaming proxy error frame；最终不可恢复时继续使用 final-candidate partial bytes + naked close，符合现行用户裁决。Provider 只声明 per-model endpoint capability、pipeline 解释并执行、P6 暂不实测且 CodeBuddy streaming-only 只标为保守 compatibility，这些边界也都与用户裁决一致。问题集中在合同精度和 living docs 之间的同步，不需要推翻架构。

## 评审方法与权威顺序

先读根 `CLAUDE.md` 与 `.claude/rules/00-development-workflow.md`，再逐字读取用户指定的全部 18 份主题／人控文档。对照顺序为：用户亲笔 `docs/.human-controlled/` > 本主题记录的用户直接裁决 > 各 living Spec > 设计派生判断 > status／deferred／报告。检查了五组交叉不变量：裁决来源；`[DONE]` 与流内 error 的 terminal precedence；replacement 与 final carrier；TUI／durable observation 的 attempt isolation；provider capability 与 pipeline 内容 ownership。

行号均为 2026-09-06 主树 active 文件快照。

## Blocker

### B-1　Mode-adapted Chat JSON 没有规范性聚合合同，反而把行为交给现有实现与测试

**位置**：`direct-passthrough/spec.md` §9.3，尤其第 746～750 行；`direct-buffered-chat-completions/design.md` §5.1、§5.2、§7.1、§12.3；根开发规则第 8～13 行。

**事实**：Spec 只规定“生成标准 `chat.completion` JSON”，随后写道“现有实现对 id／created 及未知 choice 字段的保真限制须在 adapter 测试中显式记录，上移 owner 本身不授权扩大或缩小这些字段”。这没有规定现有行为究竟是什么，也把一个可观察的成功响应合同停在测试里。Design 的 `ChatEventReader` 又规定 malformed／unknown event 只成为 observation issue并保留 raw，但没有说明同一 event 对 direct raw streaming 与必须合成 JSON 的 adaptation 是否分别为可成功、可降级或必须失败。

**为什么是 blocker**：删除 provider 内 aggregation 并迁移到 pipeline 时，实现者必须自行选择 top-level `id`／`object`／`created`／`model`／`system_fingerprint`、choice 的 `role`／content／reasoning／tool-call arguments／finish reason、usage、多次更新、unknown fields 与 malformed event 的合并和保真规则。不同选择都会改变客户端可见 body，而 living Spec 无法判定哪一个正确。让测试“记录现有行为”违反本项目“Spec 级事实只能落在 Spec；测试只是转录”的硬规则。

**精确修订建议**：

1. 在 `direct-passthrough/spec.md` §9.3 增加规范性的 SSE→Chat JSON 字段表和合并规则，至少逐项定义 top-level identity／timestamp／model、按 choice index 的 content／reasoning／tool calls／finish reason、usage、unknown fields、重复或冲突字段及空输入。
2. 在同节明确 raw direct streaming 与 mode adaptation 的差异：unknown 但可原样携带的 event 可以在 direct streaming 中只记 issue；凡无法投影而会使 synthesized JSON 丢失已知内容的 event，在 adaptation 中必须得到具名 failure 或明确的、已获授权的有损规则。
3. 在 `design.md` §5.1／§7.1 只引用上述行为合同，不再用“标准 JSON”代替字段语义；§12.3 的测试逐项注明它转录 `direct-passthrough/spec.md` 哪一行。
4. 若测量当前 provider aggregation 后发现有两个都合理但客户端可见结果不同的选择，交用户裁决；若只是把当前已知行为写实，则可按 Spec 自身授权由评审共识修正。

**证据权重**：强到足以阻断实施计划。这里不是猜测潜在边界，而是 Spec 自己明写“由测试记录”、且没有正文定义。

### B-2　`[DONE]` 后继续读取尾部，但 post-terminal ending 的优先级没有闭合

**位置**：`direct-passthrough/spec.md` §5.4 第 315、319～329 行；`direct-buffered-chat-completions/design.md` §7.2 第 90～93 行、§9 第 104～108 行；`error-envelope/spec.md` §8、§10.2。

**事实**：两份文档都规定 `[DONE]` 是 SSE transaction 成功的必要条件，并要求看到它后继续读到 EOF以保留尾随原始 bytes；它们只明确了一种 post-terminal 情形——`[DONE]` 后 transport tear 时提交已有 body、不 retry。与此同时，`direct-passthrough/spec.md` 的 ending 表把 upstream idle timeout、attempt deadline和 transport tear列入 `NETWORK` retry 行，语法上只有 clean EOF 被“无 `[DONE]`”限定；client deadline、cancellation、cap、local reader／collector failure则在另一行不 retry。于是下列可达情形没有唯一答案：`[DONE]` 后 idle timeout、attempt deadline、client deadline、cap 在尾随 chunk 上触发、reader fault、又出现 error event或第二个 `[DONE]`。

**为什么是 blocker**：这些分支直接决定是否向上游重复请求、客户端拿到完整成功 body还是 partial+naked-close，以及 accounting／TUI 记成功还是失败。尤其 cap 与 deadline 可能在“为了保留尾随 bytes而继续读”期间触发；若 `[DONE]` 已经建立成功，却按表重试或按 fallback 报失败，就与 D-3 的 terminal 语义冲突。反过来，若一律忽略，又会绕过 cap／client cancellation 的既有保护。

**精确修订建议**：

1. 在 `direct-passthrough/spec.md` §5.4 把 ending 表改成 `done_seen == false` 与 `done_seen == true` 两层，逐项覆盖 clean EOF、transport tear、idle timeout、attempt deadline、client deadline、cancellation、cap、reader／collector failure与后续 stream error。
2. 高置信建议是把首个合法 `[DONE]` 定为 semantic verdict 的封口点：其后不再 replay；上游侧 tear／idle／attempt deadline只影响 tail observation，cap 则停止接收会越界的 chunk并提交已持有、已含 `[DONE]` 的 body。client cancellation仍因无读者而不写。至于 `[DONE]` 后的非注释 data／error是否应随 raw tail交付，必须在正文选定，不能让 reader 实现偶然决定。
3. `design.md` §7.2 与 `error-envelope/spec.md` §8／§10.2 同步引用同一张 precedence 表；验证设计增加每一种 post-terminal control，而不只测 tear。

**证据权重**：强到足以阻断实施计划。当前两段文字对至少 idle timeout／attempt deadline给出可冲突读法，且其结果是可观察行为。

## Major

### M-1　Replacement observation 的清空时点与 final-candidate fallback 自相矛盾

**位置**：`direct-buffered-chat-completions/design.md` §6.2 第 76 行与 §10 第 112 行；`direct-passthrough/spec.md` §5.4 第 317 行与 §10 第 769 行。

**事实**：transaction 合同规定 replacement response 成功建立前旧 attempt仍是最终 fallback候选，成功建立后才丢弃旧 bytes与side facts；但 Design §10 写“Replacement开始时当前request observation清空”。若 replacement 在建立 response 前失败，客户端最终收到旧 candidate，而 request observation 已被提前清空或切到失败的新 attempt，违背“只有最终 attempt进入 observation”的合同。

**影响**：完成行／durable record可能描述一个客户端没有收到的 attempt，或对 final fallback显示为空。这正是本设计要消除的 discarded-attempt 污染的反向形态。

**精确修订建议**：把 `design.md` §10 改成 attempt-local state始终彼此隔离；replacement开始时不修改 request-level observation；replacement成功建立时原子替换 candidate；最终 action选定时才把被提交／作为 fallback交付的 candidate snapshot发布到 `RequestContext.response_observation` 与 `RequestTrace`。若 request-level槽在尝试期间必须可见，则定义 generation id与原子 compare-and-swap语义，但当前没有这种需求，不应增加机制。

### M-2　Capability 不是一个封闭代数，且 Xingchen 的“要求”与“显式值优先”互相冲突

**位置**：`direct-buffered-chat-completions/design.md` §4.1～§4.3；`direct-passthrough/spec.md` §9.3；`client-leg-formats/README.md` §二·五；`xingchen/spec.md` §4 第 98～108 行与 §5 第 116～131 行。

**事实**：Design 说 capability 至少表达 streaming／non-streaming support，以及 `stream_options.include_usage`／`tool_stream` 是“要求或支持”；Xingchen Spec 又写“streaming请求要求缺省 … =true，但显式client值优先”。真正“要求 true”与“显式 false优先”不能同时成立；这里实际描述的是 absent 时 defaulting，而不是 required。Capability 也没有规定全部组合的行为：client `stream:true` 但 endpoint只支持non-stream、两种 mode都不支持、descriptor声明矛盾、extension不支持却client显式携带时分别如何失败或透传。Xingchen §4 列出的 `ModelDescriptor` 投影仍没有 Chat capability字段，与§5“随resolved endpoint声明”不完整同步。

**影响**：实现可以把同一 capability理解成 bool、三态或四态，并在 unsupported mode上选择静默改 mode、送上游碰运气或本地拒绝；这些选择改变 payload、failure status与provider边界。

**精确修订建议**：

1. 定义可枚举的 mode matrix：preserve native mode、`non-stream client → streaming upstream + aggregate`、unsupported client mode的本地失败，以及非法 descriptor组合。
2. 把 extension规则命名为字段级操作，例如 `absent_default=true`、`explicit_value_wins=true`、`unsupported/pass_through`，不要用“要求或支持”压成一个布尔。当前 Xingchen合同应写成“仅在 upstream streaming mode且字段缺席时 default true；任何显式值原样保留”。
3. 明确 `stream` mode是 pipeline按mode matrix决定，不受“extension显式值优先”一句影响。
4. 在 `xingchen/spec.md` §4 的 descriptor投影中加入实际 capability值；在 direct Spec 写 client `stream:true` + non-stream-only endpoint的错误 carrier与status，或明确该组合被 descriptor validation禁止。

### M-3　流内 error 的识别、冲突优先级与 non-stream HTTP carrier 仍不唯一

**位置**：`direct-buffered-chat-completions/design.md` §5.1 第 60 行、§8 第 94～100 行；`direct-passthrough/spec.md` §5.4 第 319～329 行；`error-envelope/spec.md` §8 第 373～383 行与 §10.2 第 417～427 行。

**事实**：文档说 `error.code` 与 `error.type` 都进入闭集，但没有定义它们同时存在且冲突时谁优先，也没有钉住支持的 wire shape是顶层 `{error:{…}}`、扁平对象、具名 SSE event还是三者。它还没有规定 error与先前 `finish_reason`、后续 `[DONE]` 的优先级。Direct streaming的不可重试结局已经明确为截至error event的原始 SSE；但 mode-adapted non-stream只写“OpenAI-compatible JSON，保留 error对象，使用现有proxy upstream-failure status映射”，没有给出具体 HTTP status、`ErrorInfo` category／code、headers，也没有说明未知／malformed error对象落哪一格。

**影响**：相同 wire可因实现读取顺序而重试或不重试；non-stream客户端可能分别收到200 error body、400、429或502。`code`／`type`冲突还可能错误激活 limiter。

**精确修订建议**：在 `direct-passthrough/spec.md` §5.4 增加 error normalization 表，明确支持的 event/envelope shape、字段读取顺序、冲突时保守规则、error相对 `[DONE]` 的 terminal precedence、malformed与unknown的 typed outcome。随后在 `error-envelope/spec.md` §8或§10.2逐字规定 mode-adapted JSON 的 HTTP status、headers和body：哪些字段原样保留，哪些由proxy补充，unknown fields放在何处。若“保留原始 error对象”意味着直接以该对象为 `error` 值，应明确禁止 IR writer覆盖其 `type`／`code`。

### M-4　Chat observation 与 TUI 只列概念字段，没有形成可实现的 schema／render contract

**位置**：`direct-buffered-chat-completions/design.md` §10 第 110～118 行；`direct-passthrough/spec.md` §10 第 769 行；`tui/spec.md` 第 162～164、196 行。

**事实**：三份文档一致要求全部choices、native finish reason、reasoning、ordered tool calls、三槽usage、`[DONE]`、stream error和issues，但没有给出 canonical durable字段名与形状，也没有定义 duplicate／missing／non-integer choice index或tool index、一个choice多次非空finish reason、tool-call name始终缺席、reasoning究竟读取哪些Chat native字段、raw unknown fields附着在event／choice／tool哪一层。Console要求测试包含无名调用，却没有规定无名Chat tool call的可见文本；“按index排序”在index缺失或重复时没有稳定次序。

**影响**：两个都符合当前散文的实现可以产生不兼容的 schema v2 JSON和不同完成行；验收中的“目标字段变红”也没有唯一字段可断言。

**精确修订建议**：在 `tui/spec.md`“描述回复的用词”之后新增 Chat observation schema表，逐层定义 top-level、choice、tool call、reasoning、usage、error与issue字段及 absent／null／empty语义；规定 malformed／duplicate index的稳定排序 tie-breaker和raw保存位置；给无名调用、unknown finish reason、多choice、只有called无finish reason的精确纯文本例。`direct-passthrough/spec.md` §10只引用该schema authority，不再平行概述一套容易漂移的字段；Design仅说明生产者与生命周期。

### M-5　`client-leg-formats/README.md` 自称当前状态权威，却仍把所有 Responses 客户端腿写成旧 `ResponsesFramer`／自铸 id

**位置**：`client-leg-formats/README.md` 第 4、19～29、37～44 行；对照 `direct-passthrough/spec.md` §2.6、§6.2、§6.6。

**事实**：README 的“每种客户端腿现在怎么答”表写 OpenAI Responses使用 `ResponsesFramer`，下一节又写 id“一律自铸，不转发上游”。当前 direct Responses路径已按 direct-passthrough Spec走native passthrough，逐事件 id默认原样，只有显式 `fix_stream_ids` opt-in才reshape。`ResponsesFramer`与自铸 id仍可能准确描述 translated→Responses客户端腿，但 README没有这个定义域限定，并明确自称“当前状态的权威”。

**影响**：living docs对同一 direct Responses腿给出相反 wire合同，也会诱导本次共享 Chat engine的实现者把“client format决定framer”错误推广到 direct native路径。

**精确修订建议**：把第二节按 `translation_required` 再分 direct native与translated projection；把第三节标题和每条规则限定为“translated path 的 `ResponsesFramer`”。Direct Responses一行只引用 `direct-passthrough/spec.md` §3／§6，显式区分默认native与opt-in reshape。更新完成记录中任何把旧framer行为当全客户端腿现状的句子。

### M-6　Retry status 对当前人控 499 合同作了已知错误的“当前”陈述

**位置**：`upstream/retry-and-continuation/status.md` 第 2～10 行；对照 `docs/.human-controlled/upstream-retry-and-continuation.md` 第 12～20 行。

**事实**：status写当前 checkout的人控 requirement“不含 HTTP 499”，而当前指定的人控文档第 17 行已经把 `499 Client Closed Request`列入“一般可以继续”。该status后面又有2026-09-06 Chat更新，第2行却仍标“最近同步：2026-09-04”，因此不能把开头自然读成仅供存档的旧快照而不影响current摘要。

**影响**：本设计反复引用“现有 taxonomy／shared ledger”；读status会得到比最终权威更窄的retry集合。即使post-header Chat body本身不产生HTTP 499，replacement／pre-header driver仍共享同一请求预算和taxonomy，陈旧状态会误导实施与验证范围。

**精确修订建议**：把第4～10行明确移入带commit/date锚的历史段，新增当前摘要，先核对source history再分别陈述“人控合同已有499”和“当前实现是否已有499”；不得因本次仅做文档复核就猜实现已同步。把“最近同步”更新到实际当前对账日期。该修订不需要重裁用户合同，人控原文已经是authority。

## Minor

### m-1　`decisions.md` 把用户亲笔文字与设计推论合写成一条“既有用户合同”

**位置**：`direct-buffered-chat-completions/decisions.md` 第 17～22 行；对照 `client-side-block-delivery.md` 全文与 `client-leg-formats/README.md` 第 25～29 行。

`client-side-block-delivery.md`明确写了HTTP 200响应头先提交、SSE ping、流式按完整block交付、非流式whole-body交付；它没有逐字写“comment不构成semantic commit”，也没有把流式buffering概括为“一次性交付”。Chat terminal-only whole-attempt buffering来自2026-08-22的单独用户裁决，由client-leg living doc记录。当前推导本身合理，但来源层级被压成了用户亲笔合同。

**建议**：把该条拆成“人控文档明示”与“由明示合同＋2026-08-22 Chat裁决推导”两段；`comment不提交attempt`标为本规格对semantic commit的定义。D-1～D-8在本轮指定材料中没有发现相反的用户原文，保持不动。

### m-2　`status.md` 把额外用户复核写成 brainstorming workflow 的强制门，与项目工作流不一致

**位置**：`direct-buffered-chat-completions/status.md` 第 16～25 行；对照 `.claude/rules/00-development-workflow.md` 第 8～14 行。

Status一面写“设计已由用户确认”，一面写实施计划“须等用户复核书面设计后开始”，理由是 brainstorming workflow；项目规则则规定 living plan经独立评审共识后无需额外批准即可执行。用户当然可以显式设置复核门，但当前 decisions没有把这件事列为用户裁决，不能由技能流程冒充用户授权来源。

**建议**：若用户曾明确要求二次复核，补入decisions并引用；否则把下一步写成“先闭合本报告 blocker／major并完成独立复评，再写实施计划”，不要声称外部workflow建立了产品门禁。

## 请求的六个重点结论

| 审查面 | 结论 | 依据 |
|---|---|---|
| 用户裁决归因 | **基本一致，但有一处来源层级混写** | D-1～D-8与指定人控文档无直接冲突；m-1需把亲笔条款与推导拆开 |
| living Spec相互一致／已知错误 | **不通过** | B-1、B-2、M-1、M-5、M-6；尤其不能让测试或旧status承载当前合同 |
| `[DONE]` | **核心裁决正确，post-terminal闭包缺失** | D-3与三份Spec一致；B-2列出未定义ending |
| 流内error与final carrier | **direct streaming最终carrier保持正确；error normalization与mode-adapted HTTP carrier未闭合** | 不可恢复时仍为final candidate partial+naked-close，没有新error frame；M-3仍需精确定义 |
| TUI字段 | **方向完整，schema与边界值不够明确** | 最终attempt、choices、finish reason、reasoning、tools、usage均已列出；M-1与M-4阻止唯一实现 |
| Provider capability边界 | **ownership正确，capability algebra不完整** | Provider不处理内容、pipeline执行、snapshot冻结均一致；M-2需闭合状态空间与Xingchen descriptor |

## 没有被意外重开的用户边界

1. **Chat block delivery没有被重开。** Direct Chat仍是terminal-only whole-attempt缓冲；`ChatCompletionsAssembler`复用reader不等于direct客户端获得按推断block边界增量交付。
2. **Chat continuation没有被重开。** 当前 continuation applicability仍限定为能识别完整生成单位且客户端方言能表达synthetic call的Anthropic Messages与OpenAI Responses；Chat只做whole-attempt replay。
3. **Chat streaming proxy error frame没有被重开。** 新设计只把transparent replay放到existing fallback之前，最终形状仍是final-candidate partial bytes + naked close。
4. **Direct成功wire没有被改写。** Reader与observer只旁路观察；最终成功streaming body来自单一final attempt，keepalive comment不混入semantic body。
5. **Provider内容处理没有被重新塞回provider。** URL、认证、headers、签名、transport与status normalization仍归provider；mode选择、extension defaulting、SSE解析与JSON aggregation归pipeline。
6. **CodeBuddy真实能力没有被伪称实测。** P6未运行与保守streaming-only compatibility在各living docs中一致标注。

## 建议的修订顺序

1. 先修 `direct-passthrough/spec.md`：闭合B-1的mode-adapted成功body合同、B-2的post-`[DONE]` precedence、M-3的error normalization／carrier。它是行为authority，不能先改Design。
2. 再修 `tui/spec.md` 与 `xingchen/spec.md`：分别闭合M-4 schema／render和M-2 capability algebra／descriptor；若其中任何选择会改变用户已裁的外部行为，先请用户裁决。
3. 同步 `direct-buffered-chat-completions/design.md`：删除M-1的clear-on-start，改为引用上述Spec；不要在Design重复建第二张行为表。
4. 修 `client-leg-formats/README.md` 与 `upstream/retry-and-continuation/status.md` 的current-state错误，再更新本主题 `status.md`，不得继续写“living Specs已同步”。
5. 对修订后的最终候选只做一次独立规范复评；没有必要为本工作建立新门禁、proof framework或真实upstream canary。

## 审查后否决的建议及原因

1. **否决“趁本次把Chat改成真正按block边界增量交付”。** 用户2026-08-22已明确先whole-attempt缓冲、block解析留待未来；本次transparent replay不依赖该能力，扩大范围会重开用户未授权行为。
2. **否决“为Chat streaming补一个proxy error SSE frame以简化最终失败”。** 用户2026-08-23裁决继续推迟；新裁决只改变fallback发生前必须先retry，不改变carrier形状。
3. **否决“在Chat失败后复用现有continuation”。** Chat当前没有该客户端腿的block／synthetic-call合同，现行continuation applicability明确不含Chat；接入会同时重开block delivery与continuation两个范围。
4. **否决“让provider继续聚合，以免补B-1”。** 这与D-6／D-8直接冲突，也会保留第二套parser、retry与observation事实源；正确动作是先把现有聚合行为写入Spec，再迁移owner。
5. **否决“pipeline按provider名称分支”。** Capability应跟resolved model endpoint；provider-name分支不能表达同一provider不同model／account能力，也违反已确认架构。
6. **否决“所有Chat target统一强制upstream streaming”。** 它会无授权改变GitHub Copilot与native non-stream路径的payload、latency、headers、失败时点与JSON fidelity。
7. **否决“把finish reason当作`[DONE]`替代品”。** D-3明确要求每个SSE-buffered transaction见`[DONE]`才成功；finish reason只描述模型停止原因。
8. **否决“本轮补跑真实CodeBuddy P6或Xingchen canary”。** 用户明确选择P6暂不实测；Xingchen canary另需凭据并消耗额度。文档复核应保持既有证据等级，不用真实调用替代合同修订。
9. **否决“为解决当前歧义新建proof gate／schema registry／状态机治理层”。** 现有living Spec、typed records与针对性测试足够；问题是正文缺少行为定义，不是缺少一套证明基础设施。

除上述九项外，本轮没有其他审查后否决的建议。
