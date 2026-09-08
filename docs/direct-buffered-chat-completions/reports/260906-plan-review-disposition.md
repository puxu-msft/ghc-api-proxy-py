# Direct buffered Chat Completions 实施计划评审处置

日期：2026-09-06。

最终评审对象：[`../plan.md`](../plan.md)，SHA-256 `7ed5221af6938d861690532ee0554d2809ebe572b82a063e05947c12de31a484`；同步direct Spec SHA-256 `6f0e7b4d83b8c0dc575c7b1b7bf3df1a7b065103f5e81eab59b6d127ef1a42e2`。该plan相对已通过的`4de58262…`只增加三处finalizer文义同步，验证与架构两位原评审均在各自final报告末尾对`7ed5221a…`做了定向复核并维持0 blocker／0 major。

评审原件：验证线的 [`260906-plan-verification-review.md`](260906-plan-verification-review.md)、[`260906-plan-verification-rereview.md`](260906-plan-verification-rereview.md)、[`260906-plan-verification-rereview-pass-before-architecture.md`](260906-plan-verification-rereview-pass-before-architecture.md)、[`260906-plan-verification-rereview-rr03.md`](260906-plan-verification-rereview-rr03.md)、[`260906-plan-verification-final-rereview.md`](260906-plan-verification-final-rereview.md)，以及架构线的 [`260906-plan-architecture-review-initial.md`](260906-plan-architecture-review-initial.md) 与 [`260906-plan-architecture-review.md`](260906-plan-architecture-review.md)。本文件记录处置，不替代plan或Spec。

## 最终结论

- 验证判据评审：0 blocker、0 major，可定稿。
- 架构／依赖评审：0 blocker、0 major，可定稿。
- 两条评审都只证明计划可执行、覆盖关键失败面；不证明尚不存在的代码会编译、测试会通过或真实provider能力已验证。

## 验证判据评审处置

| Finding | 处置 | Plan落点 |
|---|---|---|
| F-01 raw SSE compatibility oracle同源 | 采纳。先在改production前冻结literal input→event expected，重构后decoder与`read_events()`都对同一literal oracle；LF-only／drop-EOF各有单变量控制 | Task 2 Steps 1–3 |
| F-02 同chunk `[DONE]`＋越界tail未覆盖 | 采纳。Decoder改为bounded frame feed，不先复制整chunk；collector加入同chunk正确样本、whole-chunk pre-reject与append-first controls | Task 2 Step 2；Task 3 Steps 2／5 |
| F-03 缺少同一state／只解析一次component入口 | 采纳。State注入counting reader；同一实例生成decision／aggregation／observation；synthetic-body reparse seam用sentinel禁止 | Shared Contracts；Task 3 Step 5 |
| F-04 event limiter与跨retry client deadline不可判别 | 采纳。Generic、pre-success production与post-header runner分别断言mode／wait／ledger／raw status及固定absolute client deadline，并以漏signal／重置deadline控制判红 | Task 4 Step 6；Task 5 Steps 6–7；Task 6 Steps 7–8 |
| F-05 Tasks 4–7缺精确命令、虚构GitHub test路径 | 采纳。删除不存在路径；每个Task列可复制pytest／Ruff／Pyright命令，并注明zero collection不是pass | Tasks 1、4–7 |
| F-06 cassette层缺席却宣称证据边界齐全 | 采纳。明确本次无Chat cassette、现有Responses cassette不证明Chat、P6/live未执行；Task 8状态表逐层记录actual与不可冒充项 | Global Constraints；Task 8 Step 5 |
| RR-01 cap未计state／projection／observation | 采纳。新增统一mutable `BufferedMemoryAccount`、state prospective delta与materialization reservation；raw低于cap但raw＋state超cap有正例和zero-state-size control | Shared Contracts；Task 2 Step 5；Task 3 Steps 1–5 |
| RR-02 critical controls未逐项具名 | 采纳。补choice丢失、provider重写mode/payload、error field丢失／fallback多出、synthetic长度覆盖raw accounting的单变量控制与目标断言 | Task 2 Step 7；Task 5 Step 6 |
| RR-03 reopen压缩failure/refusal且request terminal双owner | 采纳。Reopen改为Opened／AttemptFailed／ReopenRefused三态；initial-only request finalizer、replacement defer request terminal；同一runner/production入口断言error identity/origin/index、旧fallback和exactly-one request terminal | Shared Contracts；Task 4 Steps 2–6；Task 6 Steps 1–8 |

## 架构／依赖评审处置

| Finding | 处置 | Plan落点 |
|---|---|---|
| 01 JSON `stream`与provider mode未同源 | 采纳。每个Chat attempt把`Attempt.payload["stream"]`写成`ChatSendPlan.upstream_stream`，provider参数读取同一值；actual serialized bytes覆盖四格矩阵与retry一致性 | Task 5 Steps 1／6 |
| 02 adapted／streaming final state没有显式跨层载体 | 采纳。Adapted `ResponseHandoff.chat_snapshot`携带immutable facts；streaming runner通过`on_selected(SelectedBufferedCandidate)`发布winner／fallback | Shared Contracts；Tasks 4、5、6、7 |
| 03 post-header limiter／attempt lifecycle无owner | 采纳。Attempt与request finalizer分槽；initial handoff唯一创建request finalizer，replacement仅有attempt finalizer；body send-return后才success，send failure走cancelled | Task 4 Steps 1–6；Task 6 Steps 1–8 |
| 04 collector callback拿不到facts做pre-mutation cap | 采纳。定义typed `BufferedProtocolState[FactsT]`，collector严格执行read once→measure delta→reserve→apply；memory account可在projection时继续reserve／transfer | Shared Contracts；Task 3 Steps 1–5 |
| 05 Handoff放`pipeline.driver`形成反向import | 采纳。新建dependency-leaf `pipeline/response_handoff.py`，driver与direct_driver只向下import | File Map；Task 4 |
| 06 hook异常时raw response可能漏关 | 采纳。`ResponseLease`从headers到transfer／close唯一持有raw response；hook failure/cancel由`_run_attempt()`cleanup，collector stream close与outer cleanup共享idempotence guard；tests断言close order与primary＋cleanup identity | Task 4 Steps 1–2／6 |
| Finalizer复评：initial pre-header无outer、replacement多outer、send-return顺序 | 采纳。Initial pre-header仍由原driver终结；只有initial successful streaming handoff创建outer request finalizer；replacement设defer terminal且不新建outer；selected snapshot在yield前确定，attempt/request success在ASGI send-return后发布 | Task 4 Steps 2–6；Task 6 Steps 1–8 |

## Task 2／3接口定向评审处置

Task 2实现评审把下层事实接口精化后，plan由`7ed5221a…`修订为当前`b2577401444304f0b0d66c3ad197a486230ee6fd6d552e3c322989339ffae73d`。验证与架构原评审者仅复核受影响接口：

| Finding | 处置 | Plan落点 |
|---|---|---|
| T23-01 collector仍调用batch feed | 采纳。Task 3新增`RawFrameProposal`／`propose_one_bounded()`，collector在同chunk每产出一frame就read→measure→reserve→apply并重算capacity；明确禁止batch API，增加frame A state增长后frame B不fit的控制 | Task 3 Files／Interfaces／Steps 1、3、6 |
| T23-02 same-state test调用已删除materializer | 采纳。测试改走projection/observation reservation→shared memory reserve→materialize，reader计数与reparse sentinel落在目标断言 | Task 3 Step 6 |
| Architecture F07 batch proposal无法兑现state-aware cap | 与T23-01合并采纳；把`sse_source.py`和decoder regressions纳入Task 3 exact paths／commands | Task 3全节 |

验证判据定向复核已确认0 blocker／0 major、Task 3 ready；架构线对当前hash的最终回执附在`260906-plan-architecture-review.md`。

## 未采纳项

没有驳回任何经核验成立的finding。评审提出并否决的扩大路线继续不采纳：不运行P6／真实provider／新Chat cassette作为门槛；不建立proof framework；不重开Chat block delivery／continuation／proxy error frame；不让provider继续聚合；不按provider名称分支；不顺带修改translated multi-choice projection。这些理由分别保留在评审原件和[`../decisions.md`](../decisions.md)／[`../deferred.md`](../deferred.md)。
