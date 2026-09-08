# Direct buffered Chat Completions 实施计划架构评审

report_id: `dbc-plan-architecture-review`
attempt_id: `agent-abb6a835f10e0caff-260906`
status: `in-review`
reviewed_at_rev: plan SHA-256 `353e67ec8e4466414160de427612686cb5dcd60cd27a8065ca1033e995a5f3e3`；源码基线 `f97d243f9431d836861ce5e9938605df56b37478`，源码证据取自主树绝对路径的当前内容
reviewed_at: `2026-09-06`

## 评审范围

评审对象是主树 `.dev/docs/direct-buffered-chat-completions/plan.md` 的上述冻结字节，以及它声明为行为 authority 的 `design.md`、`decisions.md`、`direct-passthrough/spec.md`、`error-envelope/spec.md` 与 `tui/spec.md`。源码核对覆盖当前 `ModelDescriptor`／provider send、`RequestContext`／`Attempt`、`DirectDriver`、`replay_prepared()`、SSE source、delivery／ASGI handoff、retry／rate limiter、error classifier／writer和 response observation 调用链。未评 minor／nit，未执行尚不存在的实现或真实 provider／P6／canary，也未改源码、tests 或 living docs。

## 总体 verdict

`needs-fix`。Blocker 0，major 6；当前不可定稿。计划的范围护栏、双 retry owner 大方向、provider 边界、证据分层与版本控制安全约束基本正确，但六个承重接口仍无法同时兑现当前 Specs 与当前源码调用顺序。

## C1–C8 核验

| Claim | 判定 | 证据与限定 |
|---|---|---|
| C1 | 已推翻 | 范围禁令本身成立：`plan.md:21-23,894`保留 P6／translated multi-choice并禁止 cutover；但核心行为仍漏掉 model-protocol `stream` 写入、完整 memory-cap 计量和 §8 error carrier，见 finding 01／03／04。 |
| C2 | 已推翻 | owner 表写出了目标，但 handoff 的模块方向形成循环，最终 candidate／adapted state 又没有已定义的跨任务载体，见 finding 02／05。 |
| C3 | 已推翻 | Task 5 把 provider 迁移与 adapter 放在同一语义切片，避免了单独提交的不可用窗口；但按现有步骤仍会发送错误的 payload，Task 4 的 handoff import 与异常 cleanup 也不能按所列接口直接闭合，见 finding 01／05／06。 |
| C4 | 已推翻 | Collector 不消费 ledger、runner 在 draining 前不花预算这两点明确；但 direct streaming 缺 body-verdict finalization channel，仍会过早记 limiter／attempt success，且 hook failure 的 response cleanup 无 owner，见 finding 02／06。 |
| C5 | 已推翻 | 禁止 provider-name branch、CodeBuddy `extra_headers`和 Xingchen final-byte signing均有明确步骤；但 pipeline 未明确把 upstream mode写入最终 model-protocol payload，见 finding 01。 |
| C6 | 已推翻 | `[DONE]`同 chunk cap、typed `ResponseModeNotSupported`与 raw／synthetic成功分槽已有接口；最终 candidate promotion和 non-stream §8 failure carrier仍无可执行接口，见 finding 02／04。 |
| C7 | 已确认（blocker／major 阈值） | `plan.md:26-27,890-898`按语义提交、精确 path、禁止 broad staging／push／history reshape，并保留 worktree／report；未发现要求破坏性版本控制操作的 blocker／major。 |
| C8 | 已推翻 | 字面扫描未发现 `TBD`／`TODO`／“类似 Task N”，但“produces finalcandidate result”没有类型或出口，typed error carrier也没有字段／writer契约，且 `ResponseHandoff`放置与调用方向冲突，仍是会迫使实施者临场发明的语义占位，见 finding 02／04／05。 |

## Findings

### dbc-plan-architecture-review-01 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:580-598`
- `related_locations`: `.dev/docs/direct-passthrough/spec.md:773-782`；`src/app/model_provider/codebuddy_client/client.py:50-72`；`src/app/model_provider/ghc_client/client.py:68-82`
- `evidence`: Task 5只把`ChatSendPlan.upstream_stream`设为true并迁移defaults，随后删除provider内唯一的`body["stream"] = True`；当前client代码证明JSON body与HTTP SDK的`stream=`是两个独立输入。
- `impact`: client `stream:false`＋streaming-only capability会继续把`"stream": false`或缺席值发给upstream，同时本地按SSE读取；核心CodeBuddy adaptation可能收到JSON／拒绝而不可用，现有“upstreamstreamtrue”断言也可能只检查transport flag而假绿。
- `required_correction`: 明写在private `Attempt.payload`中把model-protocol `stream`设为`ChatSendPlan.upstream_stream`，并以实际发出的JSON bytes断言四格矩阵及两次retry payload逐字一致。

### dbc-plan-architecture-review-02 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:654-685,746-761`
- `related_locations`: `.dev/docs/direct-passthrough/spec.md:350,354,829`；`src/app/pipeline/direct_driver/base.py:364-419`
- `evidence`: `BufferedCandidate`只有chunks／source／state／index，`BufferedReplaySupport`只有ledger／reopen／draining；未定义final-result或callback，却要求Task 7从async-generator runner发布winner／fallback。对不需adaptation的streaming handoff又在body前返回，当前driver会随即`observe_success()`并发布两个success events。
- `impact`: fallback可被`context.current_attempt`覆盖，Task 7只能重解析或临时改Task 6接口；同时HTTP 200会在`[DONE]` verdict前推进limiter recovery，post-header流内rate-limit没有一个对称的attempt finalization owner。
- `required_correction`: 在Task 6先定义typed final-candidate／replacement-failure结果与显式finalization sink，携带selected state并让runner在body verdict后恰好一次结算limiter／attempt lifecycle；Task 7只投影该结果。

### dbc-plan-architecture-review-03 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:277-297,371-414`
- `related_locations`: `.dev/docs/direct-passthrough/spec.md:694-696`
- `evidence`: 新bounded decoder只约束decoder＋candidate raw，collector接口也只接`state`与返回`None`的`observe` callback，没有读取`ChatAttemptState`、frozen JSON、projection／observation副本持有字节数的契约。
- `impact`: raw body达到cap时，逐choice content／reasoning／arguments、unknown JSON和同时存在的projection仍可再持有同量数据；计划的`peak_held_bytes <= cap`可以全绿而违反Spec明确要求的“raw buffer＋protocol state＋副本”总持有量上限。
- `required_correction`: 给generic state／projection定义可增量计量的held-bytes协议或明确转移所有权以避免并存，并让cap检查与peak断言覆盖raw、decoder staging、state及所有同时存活副本。

### dbc-plan-architecture-review-04 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:526-528,586-602`
- `related_locations`: `.dev/docs/error-envelope/spec.md:373-385,419-428`；`src/app/pipeline/error_classify.py:83-134,221-268`；`src/app/pipeline/delivery/formats/errors.py:77-88`
- `evidence`: 计划只写“typed … error used by error-envelope”，没有定义异常携带的原始JSON值／HTTP 200语义头／目标status，也没有指定renderer分支。当前generic classifier只理解HTTP error body，OpenAI writer会重造`{error:{message,type,param,code}}`，无法实现flat／`event:error`把整个object直接放入`error`值且不覆盖字段。
- `impact`: mode-adapted failure会丢字段或改变envelope；rate-limit预算耗尽未必为429，nested／flat／malformed三类也无法按Spec分别保真，Task 5列出的unknown/malformed测试不足以约束精确carrier与headers。
- `required_correction`: 先定义具名failure／failure-projection record及其完整字段和owner，再把明确的classifier／writer或edge branch文件纳入Task 4／5；为nested、flat、malformed、429／502、无合成`Retry-After`及filtered原200 headers逐字断言。

### dbc-plan-architecture-review-05 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:447-510`
- `related_locations`: `src/app/pipeline/driver.py:30-36`；`src/app/pipeline/direct_driver/__init__.py:9-27`；`src/app/pipeline/direct_driver/base.py:214-266`
- `evidence`: 计划把`ResponseHandoff`定义在`pipeline/driver.py`，却要求`direct_driver/base.py::_complete_response()`在运行时构造它；当前`pipeline/driver.py`顶层反向导入`app.pipeline.direct_driver`，后者再导入`base.py`。
- `impact`: 按所列模块直接import会在Task 4形成初始化循环；改用local import／`Any`虽可能暂时启动，却仍直接否定C2的“文件依赖无循环”并削弱Pyright能检查的接口。
- `required_correction`: 把handoff records移到双方都只向下依赖的独立types模块，或放到现有依赖方向的`direct_driver`侧；同步精确import与`DriverOutcome`／`HandledRequest`访问签名。

### dbc-plan-architecture-review-06 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:504-542,586-594`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:327-419`；`.dev/docs/direct-buffered-chat-completions/design.md:74-81,118`
- `evidence`: 新hook在`_run_attempt()`取得headers后执行；当前`run()`只有在`response = await _run_attempt(...)`赋值成功后才进入持有response的cleanup `finally`。hook若抛出，外层只拿到exception；计划仅要求Task 5 collector close，Task 4自己的“hook fails after headers”测试不检查close或cleanup chain。
- `impact`: body-phase retry／本地hook failure可在开下一attempt前泄漏raw response，且close failure无法与primary同时保留；这破坏每个raw response恰好关闭一次及既有cleanup排序。
- `required_correction`: 在`_run_attempt()`内明确定义“headers取得→handoff成功”的所有权转移，handoff失败／取消时由该层调用既有cleanup helper；给Task 4正反例增加close次数、先关旧response再重试及primary＋cleanup identity断言。

## 被否决建议及原因

1. **让CodeBuddy provider继续补`stream:true`。** 否决；这会违反D-6与`direct-passthrough/spec.md:313`的content-transparent provider边界，正确修复点是pipeline的`Attempt.payload`。
2. **从synthetic JSON或`context.current_attempt`重建最终Chat observation。** 否决；`direct-passthrough/spec.md:829`与`tui/spec.md:222`要求实际winner／fallback的同一attempt facts。
3. **只在现有post-header测试里断言最终limiter状态。** 否决；NORMAL→提前success→LIMITED与没有提前success同形，必须从RECOVERING状态或调用序列观察headers阶段没有success。
4. **让collector自行再解析frame以取得`facts`。** 否决；会建立第二个reader调用并违反同一state只解析一次的计划与Spec。
5. **用local import或`Any`隐藏handoff循环。** 否决；这不消除文件依赖环，也让签名一致性失去静态检查。

## 搜索面与证据能力

- 完整读取：冻结plan；同主题design／decisions；direct-passthrough、error-envelope、TUI三份living Spec；相关人控block delivery、retry／continuation、message translation与release／deployment合同。
- 源码读取：`model_provider/types.py`、provider protocol与GitHub／CodeBuddy／Xingchen clients，`pipeline/request.py`、`driver.py`、`direct_driver/base.py`／Chat driver、`retry.py`、`rate_limiting.py`、`sse_source.py`、`delivery/stream.py`、`server/routes/inference.py`、error classifier／writer、response observation及trace／completion接缝。
- 机械检查：冻结hash精确匹配；符号搜索核对调用点与provider payload／transport双输入；AST枚举当前`ModelDescriptor(...)`构造点；字面placeholder扫描为0命中。仓库无CodeGraph索引，故使用绝对路径`Read`／`rg`，未自行索引。
- 证据上限：这是未实施计划的静态架构评审，能判接口是否闭合及是否与当前源码可接；不能声称未来实现可运行、测试会通过或真实provider具备某能力。本轮不运行P6／live／canary，符合范围而非阻塞。

## 我最没把握的三个判断

1. finding 03中“attempt success event也必须延后”的语义不如limiter条款直白；但`direct-passthrough/spec.md:350`对limiter success延后无歧义，而当前接口连这一最低要求也承载不了，因此finding与major定级不依赖更宽的event解释。
2. finding 02的缺口可由一个尚未写明的callback轻易修复，但“容易补”不等于接口已经存在；C2／C6／C8评的是冻结计划能否按步骤执行，故仍定major。
3. finding 05可用local import绕过Python初始化失败；但用户的C2明确要求文件依赖无循环，且该绕法把核心handoff降成运行时约定，因此不改变结论。

## 执行本契约时遇到的摩擦

评审期间plan多次变化；协调者最终明确冻结上述SHA-256，本报告只采用该版本并废弃此前读数。隔离worktree策略阻止`Write`直接命中主树绝对路径；报告经该worktree已存在且唯一指向主树`.dev`的符号链接写入指定路径。仓库无CodeGraph索引，故使用绝对路径`Read`／`rg`与当前源码调用链。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-06`
- `finding_total: 6`
- `blocker: 0`
- `major: 6`
- `minor: 0`
- `nit: 0`
- `verdict: needs-fix`
- `finalizable: false`
