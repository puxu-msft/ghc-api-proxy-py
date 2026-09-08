# Direct buffered Chat Completions 技术可实施性复评

日期：2026-09-06

结论：**未形成 0 blocker／0 major 共识。当前 candidate 为 0 blocker、1 major、2 minor。** 初审的 B-01、M-01～M-08、m-01～m-04均已在设计层闭合；其中 M-07以纠正当前 direct scope并显式登记 deferred D-2闭合，不代表 translated multi-choice代码缺陷已经修复。修订后的主架构可实施，新增裁决的 standard multi-choice、首个 `[DONE]` 后 semantic freeze／raw tail以及 post-`[DONE]` client deadline提交完整body，在现有调用链上均有可执行落点。尚存 major是新 mode矩阵误用了现有 `CapabilityMissing`类型。

## 1. 复评快照与方法

- 当前 decisions SHA-256：`517138203ed557a417197665d416f23b598815b488500d08883af98a4753da30`。
- 当前 design SHA-256：`bc847e2527db1291ed65ba6cde10f9f0bc23b0ff9cfe3092fa8949fff900704d`。
- 对照源码快照仍为 `f97d243f9431d836861ce5e9938605df56b37478`；本轮只评书面 candidate，没有源码实现可运行。
- 重新核对 `direct-passthrough/spec.md` §5.4／§9.3／§10、`error-envelope/spec.md` §8／§10.2、`tui/spec.md`“Chat provider observation schema”、`xingchen/spec.md` §4／§5、当前 `deferred.md`，以及原报告列出的现有源码接缝。
- OpenAI SDK探针确认当前环境存在 `openai.lib.streaming.chat.ChatCompletionStreamState`，公开方法含 `handle_chunk`、`current_completion_snapshot`与 `get_final_completion`。设计把它定位为可选实现基础而非行为 authority，技术上成立。

## 2. 原 finding逐项处置复核

| 原 finding | 状态 | 复评依据 |
|---|---|---|
| B-01 runner与 `DirectDriver` 双重 retry owner | **closed** | `design.md` §6.1把 collector限定为 single-attempt且禁止消费ledger；§6.2明确pre-success由 `DirectDriver`唯一拥有、post-header由delivery runner唯一拥有，并增加body-phase prepared retry seam与“一次failure只由一个owner消费”不变量。`direct-passthrough/spec.md` §5.4同步成为行为authority。 |
| M-01 client／upstream stream混槽 | **closed** | `design.md` §4.1／§7.1与 `direct-passthrough/spec.md` §9.3明确 `RequestContext.stream`只表示client contract，`ChatSendPlan.upstream_stream`独立决定provider mode，四种mode组合已闭合。 |
| M-02 synthetic response冒充raw exchange | **closed** | `design.md` §6.1／§7.1／§9与 `direct-passthrough/spec.md` §9.3.2明确raw request／status／headers／HTTP version／connection／SSE byte count和client JSON分槽，raw response由collector关闭。 |
| M-03 event rate-limit没有limiter seam且headers先记success | **closed** | `design.md` §8与 `direct-passthrough/spec.md` §5.4明确新增event-rate-limit入口、HTTP 200不先推进recovery success、最终body verdict后记success，下一attempt仍经 `RateLimiter.acquire()`。 |
| M-04 observation reset／promotion | **closed** | `design.md` §10与 `direct-passthrough/spec.md` §5.4／§10拆开attempt draft、candidate、request projection；replacement headers前失败时旧candidate snapshot随fallback发布，不再以 `context.current_attempt`偶然决定。 |
| M-05 unknown error、unassemblable与raw frame边界 | **closed** | `design.md` §5／§8先识别三类carrier，再按所有非空code／type的一致分类决定retry；unknown／malformed／冲突不retry；adaptation增加 `unassemblable`；reader保留raw frame起止offset。`error-envelope/spec.md` §8给出nested／flat／malformed的最终HTTP／JSON carrier。 |
| M-06 post-`[DONE]`状态不完整 | **closed** | 用户D-10／D-11已写入 decisions；`direct-passthrough/spec.md` §5.4按 `done_seen` 分成两张ending表，覆盖clean EOF、tear、idle、attempt／client deadline、cap、tail semantic event、本地tail failure与cancellation。 |
| M-07 translated assembler混合multi-choice | **closed for current scope** | `design.md` §5.2撤回“assembler共享同一choice state”的过宽主张，只复用纯reader；direct standard aggregation另有完整字段表。现有translated缺陷明确进入 `direct-buffered-chat-completions/deferred.md` D-2，未被TUI最小choice规则暗中裁决。 |
| M-08测试计划无鉴别力 | **closed** | `design.md` §12新增exact calls／ledger spent／payload／admission、mode分槽、timeout层次、cleanup、raw accounting、limiter、unknown error与完整post-terminal矩阵；§12.4／§12.5明确production black box不冒充“只解析一次”证明。 |
| m-01 capability语义混写 | **closed** | `response_modes`成为非空闭集，request extension改为 absent-default，显式client值优先，unsupported方向有明确动作。 |
| m-02 durable schema容器缺失 | **closed** | `tui/spec.md`新增独立 `chat` payload，逐层定义 `done_seen`、`tail_ending`、choices、stream error、unknown、tool fields、absent／null／unreadable、排序与console精确拼法。 |
| m-03 CodeBuddy `extra_headers`未传 | **closed at design level** | `design.md` §4.3、§11、§13明确将现有断路纳入provider boundary slice并要求component test，没有再把当前状态误称为已满足。 |
| m-04 人控归因写宽 | **closed** | `decisions.md` §“既有用户合同”只转述人控文档明示内容，随后单列living Spec推导，不再把comment commit frontier或Chat terminal-only单位冒充用户原句。 |

## 3. 新增 findings

### Major

#### NEW-M-01：Mode不支持分支误用现有 `CapabilityMissing`，现有类型的语义与签名均不能表达该失败

**位置**：

- `.dev/docs/direct-passthrough/spec.md` §9.3 mode矩阵的第四行，当前要求“以Chat／OpenAI `CapabilityMissing` 400拒绝”。
- `src/app/model_provider/types.py::CapabilityMissing`。
- `src/app/pipeline/routing.py::decide_route()`。
- `src/app/pipeline/error_classify.py::_PROVIDER_ROWS`。
- `.dev/docs/error-envelope/spec.md` §5.1的 `CapabilityMissing`行。

**现有合同**：`CapabilityMissing(provider, model_id)`只表示“descriptor的endpoint集合为空”，错误消息是 provider对该model“不advertise endpoints”。Routing也只在 `descriptor.endpoints`与 `unknown_endpoints`都为空时抛它；error-envelope §5.1逐字把它定义为“目录对该模型的端点集为空”。

**新分支事实**：model明确有 `/chat/completions` endpoint，缺的是client要求的 `streaming` response mode。复用现有类型会向client与operator谎称endpoint capability为空；现有构造签名也没有mode参数。给现有类硬加第三参数会把两种不同失败压进一个名字，并使既有routing caller、测试与error table语义漂移。

**必须修正**：新增具名 `ChatResponseModeNotSupported`／`ResponseModeNotSupported` `ProviderError`，携带provider、model、requested mode和available modes；在error-envelope §5.1明确映射为 `CLIENT`／400并给出OpenAI error code，mode矩阵改引该类型。也可以定义等价的新 typed pipeline refusal，但不能继续引用当前 `CapabilityMissing`。修正只涉及一个前置拒绝分支，不推翻整体架构，因此定级major而非blocker。

### Minor

#### NEW-m-01：`ChatSendPlan`与 `Attempt.payload`同时被写成final payload owner，prepared retry的单一权威尚需收紧

**位置**：`design.md` §4.1称 `ChatSendPlan`保存final payload；`direct-passthrough/spec.md` §9.3称 `Attempt.payload`保存真正发送的final payload。

Python frozen dataclass不会深度冻结其中的dict；若 plan与attempt各持一份copy，provider send、request byte accounting与body-phase prepared retry可能读取不同对象。应指定唯一owner：要么 `ChatSendPlan`只携带mode与capability引用，final payload唯一归 `Attempt.payload`；要么 plan持有不可变payload snapshot，`Attempt.payload`只引用／从它生成每次私有发送copy。不要让两个普通mapping都被称为最终事实源。

#### NEW-m-02：Capability provenance字段名在跨Spec转写中仍不一致

**位置**：`design.md` §4.1命名 `ChatEndpointCapabilities.provenance`；`xingchen/spec.md` §4 pseudo descriptor命名 `chat.capability_provenance`。

两者可以表达同一事实，但当前文字看起来都是字段名。实施前应统一名称，或明确后者只是diagnostic label而不是Python field，避免code／test分别抄一份。该问题不改变行为，定级minor。

## 4. 新增裁决与重点接口的可实施性结论

### 4.1 Single-attempt collector与两个 retry owners

可实施。Collector只返回raw bytes／facts／ending并关闭一个source；pre-success typed failure回到 `DirectDriver`，post-header runner调用现有 `replay_prepared()`。该结构保留shared `RetryLedger`而不共享ledger消费点，已闭合原B-01。

### 4.2 Body-phase prepared retry seam

可实施，但必须是 `DirectDriver`内部的新phase-aware seam，而不是在driver外递归再跑一套runner。它可沿用delivery prepared replay已有的不变量：新 `RequestContext.begin_attempt()`、新attempt deadline、rate limiter acquire、复用admission，跳过mutable `attempt.prepare`。修订测试已能判红重跑prepare、重新admit与双花budget。

### 4.3 `ChatSendPlan`

client／upstream mode分槽正确，provider现有 `send(..., stream=bool)`签名足够，不需改 `ModelProvider`协议。只需按 NEW-m-01确定final payload单一owner。

### 4.4 Raw／synthetic分槽

可实施。Raw response在headers到达时先快照status／headers／HTTP version／connection，collector累计实际SSE bytes并关闭response；synthetic JSON单独进入server response。现有 `RequestTrace`／`RequestCompletionCoordinator`需要新增字段入口，但没有导入方向或生命周期阻断。

### 4.5 Event limiter

可实施。为 `RateLimiter`新增typed event signal入口，下一attempt仍由现有 `acquire()`等待；Chat streaming driver抑制headers阶段的premature success，final runner按body verdict回报success／event rate limit。无需伪造HTTP 429或500。

### 4.6 Candidate promotion

可实施。旧 `Attempt`对象本来就保留observer；需要停止让request projection自动跟随 `current_attempt`，并由runner在replacement response建立／final action两个明确时点切candidate与publish。

### 4.7 Raw frame offsets

可实施，但不能直接沿用只产出 `SseEvent`的当前 `read_events()`接口。Collector需在现有frame splitter层保留原buffer offset／separator边界，再把完整frame交给 `ChatEventReader`。这属于预期新增内部类型，不是不可实施接口。

### 4.8 Standard multi-choice aggregation

字段表已经闭合到足以编码：identity不再新造，choice与tool按原生index分槽，content／reasoning／arguments／logprobs有明确merge，finish reason与usage有final规则，unknown冲突与无法投影统一 `unassemblable`。当前OpenAI SDK accumulator存在，可复用但不能替代Spec或把内部辅助字段泄漏到wire。

### 4.9 Post-`[DONE]`矩阵

可实施。现有 `with_client_deadline_at()`在pull超时时抛 `ClientDeadlineError`并退出timeout scope；runner捕获后仍可yield已含 `[DONE]` 的buffer。Idle／attempt deadline同理。Semantic state在首个 `[DONE]` 冻结，tail只影响raw buffer与 `tail_ending`。Cap需要frame-aware prefix处理，但Spec已区分 `[DONE]` frame自身越界与同chunk尾巴越界。

### 4.10 TUI schema与provider boundary

可实施。TUI schema不复用Responses `status`／`output_items`，candidate lifecycle与display排序一致。Provider边界与现有签名兼容；Xingchen仍对pipeline最终bytes序列化一次并签名，CodeBuddy删除内容处理并补通既有 `extra_headers` seam。

## 5. 复评后否决的建议

1. **否决继续复用 `CapabilityMissing`表示response mode不支持。** 它已有更窄且可达的endpoint-empty语义；复用会制造错误诊断。应新增typed refusal。
2. **否决让 `ChatSendPlan.payload`与 `Attempt.payload`成为两份可独立变化的mapping。** Prepared retry必须只有一个final payload authority。
3. **否决因OpenAI SDK accumulator当前存在就删除本项目aggregation字段表。** SDK升级、unknown字段与内部辅助字段都可能改变wire；Spec表必须继续是authority。
4. **否决把 deferred D-2重新塞回本次direct slice。** 当前candidate已撤回对translated projection的错误承诺，并诚实记录仍存在的代码缺陷；没有新的用户裁决授权选择translated multi-choice语义。
5. **继续否决单一ledger-owning runner跨越HTTP commit frontier、provider内容特例、按provider名称分支、修改 `RequestContext.stream`、synthetic response冒充raw exchange及新proof framework。** 修订稿已经排除这些路线，没有理由重开。

## 6. 最终判定

- 原报告 findings：全部在设计层得到可核对的处置；M-07为scope-corrected／deferred，不是实现完成。
- 新增裁决：三项均形成可实施且与现有deadline／delivery生命周期兼容的合同。
- 当前 candidate：**0 blocker、1 major、2 minor**。
- 0 blocker／0 major共识：**否**。只需先把mode不支持分支从现有 `CapabilityMissing`改为语义正确的新typed refusal并同步error-envelope；该修订完成后，本轮未发现其它major阻碍。
