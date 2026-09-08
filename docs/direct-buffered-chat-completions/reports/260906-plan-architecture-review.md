# Direct buffered Chat Completions 实施计划架构复评

report_id: `dbc-plan-architecture-review`
attempt_id: `agent-abb6a835f10e0caff-260906-final-rereview-2`
status: `in-review`
reviewed_at_rev: plan SHA-256 `4de5826286c5661a91de89966762f035ea3cf2fe0cc435db4fc288189570766a`；direct Spec SHA-256 `6f0e7b4d83b8c0dc575c7b1b7bf3df1a7b065103f5e81eab59b6d127ef1a42e2`；源码基线 `f97d243f9431d836861ce5e9938605df56b37478`
reviewed_at: `2026-09-06`

## 评审范围

本轮仅复评上一版报告的六项major及修订直接触及的接口，并按reviewer规则独立检查这些修订形成的系统状态。判据是同步后的`direct-passthrough/spec.md`、同主题design／decisions、error-envelope与TUI Specs及相关人控合同；源码对照聚焦当前`DirectDriver.run()`／`_handle_failure()`、`replay_prepared()`、server `_reopen()`和`_tracked_delivery()`。未评minor／nit，未运行尚不存在的实现或真实provider调用。

## 总体 verdict

`pass`。Blocker 0，major 0；可定稿。原六项在本冻结版本均已达到major阈值下的闭合，且相邻修订未引入新的blocker／major。

## 原六项逐条完成度

| finding_id | 状态 | 核验依据 |
|---|---|---|
| `dbc-plan-architecture-review-01` | closed | `plan.md:692-710,726-728`把`Attempt.payload["stream"]`与provider `stream=`显式同源，并以实际序列化bytes覆盖四格矩阵及retry一致性。 |
| `dbc-plan-architecture-review-02` | closed | `plan.md:138-140,583-597,702-714,773-834,918`定义adapted snapshot、selected candidate与显式callback，不再靠synthetic body／`context.current_attempt`重推。 |
| `dbc-plan-architecture-review-03` | closed | `plan.md:571-580,630-636,819-860`拆开attempt／request finalizer，initial pre-header仍由driver结算，replacement复用唯一outer request finalizer，typed reopen不压成`None`，success只在final body send-return后发布。 |
| `dbc-plan-architecture-review-04` | closed（major阈值） | `plan.md:123,260-261,409-501`给出typed state protocol、单次read、pre-mutation reserve、mutable memory account及projection／observation reservation；原collector无法取得facts／state计量的缺口已闭合。 |
| `dbc-plan-architecture-review-05` | closed（major阈值） | `plan.md:523,538,593-597`把lease／handoff移到双方单向依赖的`response_handoff.py`并明确`DriverOutcome.handoff`兼容语义；原反向import消失。 |
| `dbc-plan-architecture-review-06` | closed | `plan.md:595,630,650`定义lease的transfer／close状态、hook failure／cancellation cleanup及close-order与primary＋cleanup controls。 |

## C1–C8 核验

| Claim | 判定 | 证据与限定 |
|---|---|---|
| C1 | 已确认 | Tasks 1–8逐项覆盖design §§3–13及三份行为Spec；`plan.md:21-23,1050-1056`保留P6／translated multi-choice并禁止cutover，未重开block delivery／continuation。 |
| C2 | 已确认（blocker／major阈值） | `plan.md:123-141,260-261,409-487,536-597,773-826`给出类型先后、owner、生命周期、raw／projection与candidate handoff；依赖叶拆除了当前`pipeline.driver → direct_driver`的反向环。 |
| C3 | 已确认 | Tasks 1–7按capability→facts→collector→driver seam→provider migration／adapter→runner→observation排序；各任务有可运行的targeted pytest、Ruff与Pyright命令，Task 5在同一语义切片内先有pipeline adapter再删除provider内容处理。 |
| C4 | 已确认 | `plan.md:630-636,819-860`明确single ledger owner、attempt/request两级finalizer、initial与replacement terminal ownership、typed reopen三态、固定deadlines、event limiter、cancellation与lease cleanup。 |
| C5 | 已确认 | `plan.md:692-710,726-728`要求payload／transport mode同源、provider content-transparent、CodeBuddy headers贯通、Xingchen对pipeline最终bytes签名，且禁止provider-name branch。 |
| C6 | 已确认 | `plan.md:138-140,359-367,583-597,702-714,773-842,918`给出raw／synthetic handoff、candidate promotion、pre／post-`[DONE]` precedence与`ResponseModeNotSupported`实施接口。 |
| C7 | 已确认 | 计划按语义而非绿灯划分提交，使用精确path并禁止broad staging、push、history reshape及生产`4141`操作；未要求破坏性版本控制动作。 |
| C8 | 已确认（blocker／major阈值） | 字面扫描未见`TBD`／`TODO`／“类似Task N”；六项承重接口均已具名并给出producer／consumer／targeted verification，未发现阻断实施的占位描述。 |

## Findings

可定稿。未发现blocker／major。

## 被否决建议及原因

无。本轮没有提出后又否决的blocker／major级建议。

## 搜索面与证据能力

- 逐段读取冻结plan中原六项修订对应的shared contracts、Tasks 2–7、targeted controls及相邻Task 8；读取同步后的direct Spec §5.4／§9.3／§10相关段落。
- 重读当前`DirectDriver.run()`／`_handle_failure()`、`replay_prepared()`、server `_reopen()`与`_tracked_delivery()`时序，核对新finalizer／typed reopen／send-return边界确有可接的现有位置。
- 机械核对plan与direct Spec两个SHA-256、相关新类型的定义／consumer位置，以及字面placeholder扫描。仓库无CodeGraph索引，故使用绝对路径`Read`／`rg`与当前源码调用链。
- 证据上限：这是未实施计划的静态架构复评；`pass`表示计划可进入实施，不表示代码已实现、测试已通过或真实provider能力已验证。

## 我最没把握的三个判断

不足三个真实的major级不确定判断，不为满足格式制造疑点。唯一需要保留的限定是：`BufferedProtocolState`的`.observe()`／`.apply()`、`ChatAttemptSnapshot`在Task 2定义而Task 4 handoff复用的措辞仍可在实施时统一命名；相邻正文已经明确单一reader、单一snapshot owner与依赖方向，因此它们不改变本轮pass。

## 执行本契约时遇到的摩擦

评审对象此前多次变化；本轮先核验协调者给出的plan与direct Spec两个SHA-256，再只读取对应版本。隔离worktree阻止`Write`直接命中主树绝对路径，报告通过worktree中唯一指向主树`.dev`的既有符号链接写入指定路径。仓库无CodeGraph索引，未自行建立。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-06`
- `prior_findings_reviewed: 6`
- `closed: 6`
- `partially_closed: 0`
- `finding_total: 0`
- `blocker: 0`
- `major: 0`
- `minor: 0`
- `nit: 0`
- `verdict: pass`
- `finalizable: true`


## 定向复核记录：plan `7ed5221af6938d861690532ee0554d2809ebe572b82a063e05947c12de31a484`

- `scope`: 仅核对相对已通过版本`4de5826286c5661a91de89966762f035ea3cf2fe0cc435db4fc288189570766a`的三处finalizer修订；未重审其它内容。追加前本报告SHA-256为`772023869b2e589d2bd3755305dcfdf2658e6e1abef5ae2f15d4910757baac44`。
- `shared-state verdict`: pass。`plan.md:139-140`把per-attempt finalizer与唯一request-level finalizer分槽，owner、lifetime、终态与event职责不再混写。
- `initial/replacement verdict`: pass。`plan.md:631,637,697`明确initial pre-header failure仍由原driver终结；只有initial successful handoff创建request finalizer；replacement以`defer_request_terminal=True, create_request_finalizer=False`运行，只创建attempt finalizer。
- `runner consumption verdict`: pass。`plan.md:775,819-839,859-861`让runner显式持有initial request finalizer，typed reopen不压成`None`，final body只有在ASGI send-return后才发布success，send failure只走`cancelled`；正反例覆盖第二finalizer、inner request terminal与send frontier。
- `result`: 0 blocker／0 major；与原pass结论一致，可定稿。
- `rejected_suggestions`: 无。

## 交付声明：定向复核

- `delivery_complete: true`
- `completed_at: 2026-09-06`
- `reviewed_plan_sha256: 7ed5221af6938d861690532ee0554d2809ebe572b82a063e05947c12de31a484`
- `finding_total: 0`
- `blocker: 0`
- `major: 0`
- `verdict: pass`
- `finalizable: true`


## Task 2／3 接口定向复核：plan `2a4613cc127a46094df693b29e8c23944809b98bd17b9e3ef93a5fabdec619b2`

- `scope`: 仅核Task 2已集成API与Task 3计划consumer，并对照direct Spec `760fef1cca5944e5f94a19d2d84c3fce05995957cd0f43dc71ab34f644b6af0b`、TUI Spec `63bd30c090866e7931a4182901f27cc64001665a10b40106c3bf207a7278e6a9`；不重审其它任务。
- `closed_interfaces`: `RawSseFrame`单份raw＋`body_end` memoryview、`ChatEventFacts.value: JsonObservation`、error／unattributed／layered unknown／usage snapshot states、no-clone prospective sizing、`MaterializationReservation`及`ChatAttemptState.read→additional_held_bytes→apply`均与main已集成源码逐项一致。
- `dependency_result`: 未发现当前Task 2模块环；`sse_source → events → state`为单向依赖，Task 3可用structural `BufferedProtocolState`而无需让state反向import collector。相关计划类型均已有定义或明确由Task 3创建。
- `verdict`: needs-fix。Blocker 0，major 1；当前不应继续Task 3。

### dbc-plan-architecture-review-07 — `major`
- `primary_location`: `.dev/docs/direct-buffered-chat-completions/plan.md:305-312,519-535`
- `related_locations`: `src/app/pipeline/delivery/sse_source.py:90-137`；`.dev/docs/direct-passthrough/spec.md:696`
- `evidence`: 已集成`feed_bounded()`一次扫描并复制当前transport chunk中所有raw-fit frames后才返回tuple；Task 3只能在返回后逐frame执行read→measure→reserve→apply。前一frame新增的state bytes因此无法收窄同chunk后续frame的decoder capacity，而后续frame已被复制、消费并推进offset。
- `impact`: 对“多个完整frame同chunk，raw总量在cap内、raw＋首frame state增量越cap”的输入，collector只能暂时持有未计量raw、过早丢弃本可保留前缀，或重放／重解析后续bytes；三种都违背cap-before-retain、最大合法frame前缀或单次reader合同，现有single-frame large-state与`[DONE]+tail` controls不能判红该形状。
- `required_correction`: 让decoder支持每次至多产出一个frame并返回未消费cursor／remainder，或接受逐frameadmission callback，使collector可在同一transport chunk内每产出一frame就measure／reserve／apply并重算capacity；把`sse_source.py`加入Task 3修改范围，并新增two-semantic-frames-one-chunk＋state-growth control。

## 被否决建议及原因：Task 2／3定向复核

1. **在collector中忽略`RawFrameFeed`尚未处理的frame bytes。** 否决；这些bytes已经被decoder复制并持有，忽略计量会让cap假绿。
2. **把整个chunk预拒绝。** 否决；会丢掉本可在cap内保留的完整前缀，且`[DONE]`可能就在该前缀。
3. **把返回tuple中的后续frame重新喂给新decoder。** 否决；原decoder已推进offset／ordinal，重喂会复制解析并破坏raw坐标authority。

## 搜索面与证据能力：Task 2／3定向复核

完整读取本轮plan Task 2／3接口、同步direct／TUI clauses，以及main当前`sse_source.py`、`chat_completions/events.py`、`state.py`、package exports与相关public signatures。静态复核能判API与容量时序是否闭合；未运行尚不存在的Task 3 collector。

## 交付声明：Task 2／3定向复核

- `delivery_complete: true`
- `completed_at: 2026-09-06`
- `reviewed_plan_sha256: 2a4613cc127a46094df693b29e8c23944809b98bd17b9e3ef93a5fabdec619b2`
- `reviewed_direct_spec_sha256: 760fef1cca5944e5f94a19d2d84c3fce05995957cd0f43dc71ab34f644b6af0b`
- `reviewed_tui_spec_sha256: 63bd30c090866e7931a4182901f27cc64001665a10b40106c3bf207a7278e6a9`
- `finding_total: 1`
- `blocker: 0`
- `major: 1`
- `verdict: needs-fix`
- `task3_ready: false`


## Finding 07 定向复核：plan `d3f272eed18507a999f969fb926b1878c0e997b5258ae960aafd1b7b729852a0`

- `scope`: 只复核`dbc-plan-architecture-review-07`及Task 2／3相邻接口；direct／TUI Specs仍分别为`760fef1cca5944e5f94a19d2d84c3fce05995957cd0f43dc71ab34f644b6af0b`／`63bd30c090866e7931a4182901f27cc64001665a10b40106c3bf207a7278e6a9`。
- `status`: not-closed，severity仍为major。
- `evidence`: `plan.md:448,464`新增single-frame `propose_one_bounded()`并明令cap-aware collector不得用batch API，但实际collector步骤`plan.md:540`仍逐字调用`feed_bounded()`。测试清单`plan.md:552`也只有`[DONE]+tail`同chunk和单frame raw＋state越界，没有“frame1 state增长后同chunk frame2不再fit”的控制。
- `impact`: 执行Task 3正文仍会走原finding指出的batch路径；前一frame的state增量无法收窄同chunk后续frame capacity。新增API与接口声明本身正确，但consumer未接线且缺判红用例，不能据此放行Task 3。
- `required_correction`: 把`plan.md:540`改为按caller cursor循环调用`propose_one_bounded()`，每个proposal后执行read→measure→reserve→apply再重算capacity；在`plan.md:552`加入两个semantic frames同chunk、frame1 state增长使frame2不fit的exact-prefix／cursor／peak control。
- `dependency_result`: 除此接线缺口外，Task 2现有`RawSseFrame`／`JsonObservation`／snapshot／reservation APIs与Task 3类型依赖一致，未发现module cycle或其它未定义类型。
- `verdict`: needs-fix；0 blocker／1 major；`task3_ready=false`。
- `rejected_suggestions`: 不接受仅凭Step 1的“must not use batch”覆盖Step 3相反调用；实施者按步骤执行时，承重consumer步骤必须自身正确。

## 交付声明：Finding 07 定向复核

- `delivery_complete: true`
- `completed_at: 2026-09-06`
- `reviewed_plan_sha256: d3f272eed18507a999f969fb926b1878c0e997b5258ae960aafd1b7b729852a0`
- `finding_total: 1`
- `blocker: 0`
- `major: 1`
- `verdict: needs-fix`
- `task3_ready: false`


## Finding 07 关闭复核：plan `b2577401444304f0b0d66c3ad197a486230ee6fd6d552e3c322989339ffae73d`

- `scope`: 仅复核`dbc-plan-architecture-review-07`及Task 2／3相邻接口；不重审其它内容。
- `status`: closed。
- `evidence`: `plan.md:448,453-464,540`把`propose_one_bounded()`定义为at-most-one-frame proposal并让collector持有caller cursor，逐frame read→measure→reserve→apply后重算capacity，且明确禁止cap path调用batch `feed_bounded()`；`sse_source.py`已加入Task 3修改范围。
- `controls`: `plan.md:552`加入同chunk frame A的state增长使frame B不再fit、最大合法前缀、read-count及batch mutation control；`plan.md:554`改为现存reservation→memory reserve→`to_completion_bytes`／`observation_facts`链，不再依赖旧materializer路径。
- `adjacent_result`: 新API可在现有Task 2 decoder的buffer／offset／ordinal状态上实现，`RawFrameProposal`字段足以区分frame、overflow与needs-more；Task 3 consumer与已集成`ChatAttemptState` APIs一致，未发现module cycle或未定义承重类型。
- `verdict`: pass；0 blocker／0 major；`task3_ready=true`。
- `rejected_suggestions`: 无。

## 交付声明：Finding 07 关闭复核

- `delivery_complete: true`
- `completed_at: 2026-09-06`
- `reviewed_plan_sha256: b2577401444304f0b0d66c3ad197a486230ee6fd6d552e3c322989339ffae73d`
- `finding_total: 0`
- `blocker: 0`
- `major: 0`
- `verdict: pass`
- `task3_ready: true`
