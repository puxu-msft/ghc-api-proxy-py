# 直连 Responses 原生透传产品规格独立复评（round 5）

- report_id：`direct-responses-passthrough-spec-review-round5`
- attempt_id：`260831-review-spec-5`
- reviewed_at：2026-08-31
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v5）与同目录 `plan.md`（v4）
- 对照基线：`/tmp/260830-review-spec-round4.md`
- 评审性质：只读规格／计划复评；未修改 `src/` 或 `tests/`；未派 agent

## 评审范围

本轮先沿用既有判据，再读取 v5／v4 最终状态。覆盖 round4 五条处置、§5 commit／replay partition、§5.1／§5.2 native 与 replacement failure、§7.2 final-ending gate、§9.1 semantic header predicate、§11 空清单、Plan 的全部当前步骤与验收，并专项判断 Plan step 2 的未接线 skeleton 是否能并行开工。

独立代码／协议核对包括本地 OpenAI SDK 3.3.1 `ResponseError.code` 20成员 Literal、现有 `RateLimiter`／`DirectDriver`／`RetryLedger` 的 429 路径、`_reopen` 的多种 return path，以及 RFC validator语义沿用上一轮已取得的依据。

明确不在范围内：评审正在并行编写的 skeleton bytes、修改 production／tests、真实 Copilot调用、重新验收 P1／P2、生产 4141服务的任何操作。

## 总体 verdict

**needs-fix。主体实现仍不可开始。blocker 数：1。**

**但 Plan step 2 的未接线 assembler／framer skeleton 可以并行开工。** 条件是它只实现 raw logical event/data round-trip、complete-group tracking、safe-prefix ordering与原生字段载体；不得接 production route，不得决定 final ending、replay、policy release、headers或 replacement result，也不得把当前 `push`／`finish` interface当成无需再改的产品合同。该 slice依赖的是五轮未变的核心条款，当前残留不推翻它。

v5 的 §7.2 replay入口已基本闭合，三种 commit partition穷尽且互斥；唯一 blocker在第二格的**输出**：pre-commit但不 replay不仅包括 proxy tear预算耗尽，也包括成功 upstream terminal与不可重试／预算耗尽的 native failure，表却一律写“末步 proxy error”，与 §5.1、§6.3及同节 final-ending表的原生 terminal／failure逐字交付相反。另有三条 major：`vector_store_timeout`并非非瞬时；Spec／Plan仍留有多处 v4旧话；header semantic predicate与例子对 `Last-Modified`／weak `ETag`给出不同答案，且“其余一律转发”会把 non-stream upstream `Content-Type`带到已重新序列化的JSON上。

## Round 4 五条处置状态

| finding_id | round4级别 | 状态 | 判据与结论 |
|---|---:|---|---|
| `direct-responses-passthrough-spec-review-round4-01` | blocker | partially-closed | funded replay已明确不收口，post-commit也明确收口；但 pre-commit final格把 upstream terminal／failure误写成 proxy error，见 round5-01 |
| `direct-responses-passthrough-spec-review-round4-02` | major | partially-closed | `server_error`与`rate_limit_exceeded`已纠正；20成员中仍把明确的 `vector_store_timeout`称为非瞬时并判 `None`，见 round5-02 |
| `direct-responses-passthrough-spec-review-round4-03` | major | partially-closed | 三类可观察结果已定；§5.1旧行与 Plan仍把 draining／local refusal写成 replacement failure／exception，见 round5-03 |
| `direct-responses-passthrough-spec-review-round4-04` | minor | partially-closed | dynamic hop、`Proxy-Connection`、semantic exact-byte predicate与 strip-or-recompute均加入；例子仍把不描述 exact bytes的 `Last-Modified`及未区分强弱的 `ETag`列为必剥，见 round5-04 |
| `direct-responses-passthrough-spec-review-round4-05` | minor | closed | skeleton未接线与observable activation已拆开，接线／撤销 direct reject／更新断言已合为同一刀，验收清单也扩充 |

状态计数：`closed=1`、`partially_closed=4`、`not_closed=0`。

## 当前系统状态：新发现与残留发现

### direct-responses-passthrough-spec-review-round5-01

- finding_id：`direct-responses-passthrough-spec-review-round5-01`
- severity：`blocker`
- primary_location：`spec.md:124-130,215-240`
- related_locations：`spec.md:106-122,177-181,246-252`；`plan.md:45-57`
- 标题：三种 commit partition穷尽且互斥，但 pre-commit final格丢失了 upstream ending source

**状态空间结论。** §7.2 第 223～227 行按 `native_committed` 先二分；false再按“funded replay是否实际选择”二分。三格穷尽且互斥：`precommit+replay`、`precommit+final`、`postcommit+final`。没有第四种 commit状态；ongoing不是 ending，client cancel／downstream write failure是“无写通道”这一正交能力轴，不是第四种 commit值。

**冲突在动作，不在 partition。** 第二格写“首个原生事件尚未提交，但 replay不可用／被拒／预算耗尽 → 运行，末步写 proxy error”。这个集合至少包含三种不同来源：

1. upstream正常 `response.completed`／`response.incomplete` 到达，根本没有 replay必要；
2. `response.cancelled`或不可重试 code，§5.1要求原生 failure逐字交付；
3. retryable `response.failed`到达但 budget耗尽，upstream failure仍真实存在。

后两类及成功 terminal都已经有 upstream terminal／failure。§7.2 的三步正文与 final-ending表要求第三步提交它，§6.3又要求逐字；只有“没有 upstream terminal／failure的 tear／EOF／proxy refusal”才应写 proxy error。第二格的一句把它们全覆盖成 proxy error，与同一节下面的详细合同相反。

**影响。** 实现者无法判断 pre-commit `response.cancelled`、非retryable `invalid_prompt`、budget-exhausted `server_error`以及成功 no-item response究竟发上游原生 ending还是代理 error。direct-native最承重的失败合同因此仍有两个答案。

**建议。** 保留三格 partition，只把第二格改为“运行；第三步按 final source：有 upstream terminal／failure就逐字提交，否则写 proxy error”。最好把 final source列作为正交列显式写出，而不是让 commit状态决定 carrier。§5.1旧行也同步改为引用§5.2三类 reopen结果，见 round5-03。

**证据强度。** 同一 Spec 的两张表对有限事件给出相反 wire，强到 blocker；无需新增第四状态，也无需扩大状态机。

**承重前提检查。** 前提是“precommit且不 replay意味着没有 upstream ending可交付”；成功 terminal与nonretryable native failure直接证伪。

### direct-responses-passthrough-spec-review-round5-02

- finding_id：`direct-responses-passthrough-spec-review-round5-02`
- severity：`major`
- primary_location：`spec.md:132-147`
- related_locations：`.venv/lib/python3.14/site-packages/openai/types/responses/response_error.py:10-35`；`docs/.human-controlled/upstream-retry-and-continuation.md:3-20`；`plan.md:53-57`
- 标题：20成员中 `vector_store_timeout` 也是明确瞬时失败，不能落入“其余全非瞬时”

**证据。** v5正确认出 `server_error`与`rate_limit_exceeded`，但第143／145行又称其余18个 Literal“全是明确的非瞬时失败”。本地 SDK列表第19行包含 `vector_store_timeout`；它的名字明确陈述 timeout，而用户亲笔 retry合同把“请求超时”列为一般可继续。它至少不能与 `invalid_prompt`／policy rejection一起无条件映为 `None`。

`failed_to_download_image`等是否瞬时仍缺上下文，本报告不猜；继续保守 `None`合理。唯一直接可判的第三项是 `vector_store_timeout`。它应进 `SERVER_ERROR`还是 `NETWORK`会消耗不同 per-reason budget，须由Spec明确；我的偏好是 `SERVER_ERROR`，因为失败发生在 upstream的 vector-store服务而不是 proxy↔upstream transport。

**影响。** precommit、尤其 `full`整轮窗口内，一个明确 timeout会直接交给客户端，不尝试既有透明恢复。

**建议。** 把 `vector_store_timeout`单列为retryable并选定既有 reason；把表中“其余18个全非瞬时”收窄为逐项名单或“除明列retryable code外保守None”，不要再对剩余集合做未经逐项核验的全称。

**证据强度。** SDK exact Literal与用户timeout合同是强到可直接修表的静态证据；该code实际发生率未测，不影响分类。

**承重前提检查。** 前提是“除了前两个code，其余名称都表达永久失败”；`vector_store_timeout`逐字证伪。

### direct-responses-passthrough-spec-review-round5-03

- finding_id：`direct-responses-passthrough-spec-review-round5-03`
- severity：`major`
- primary_location：`spec.md:124-130,149-157`
- related_locations：`plan.md:45-63,75-94`；`src/app/server/routes/inference.py:395-461`；`src/app/pipeline/direct_driver/base.py:136-234`
- 标题：§5.1与Plan仍保留v4旧行为，反向覆盖v5的replay、reopen与header合同

**Spec内部残留。** §5.1第130行仍把“建流前HTTP失败／被拒／draining返回None”全称为“replacement attempt自己失败”，要求客户端看见replacement失败。§5.2随后才裁定 `ReopenRefused`没有replacement、origin=proxy。两行对draining给出相反attribution，说明同类扫描仍漏了一处normative表。

**Plan残留不是元文本。** 当前Plan v4第51、57、63行分别仍写：

- “任何 ending到达时一律收口”，漏掉funded replay不运行§7.2；
- native failure“当前一律不重试”且replacement failure“是exception”，正是v5推翻的两句话；
- header继续列固定validator名单，漏掉semantic predicate、`Content-MD5`、`Proxy-Connection`与strip-or-recompute。

第81／92行虽又写v5新合同，却没有作废上面三条，所以Plan内部也一事两答。按第51／57／63行实施会重开round4的blocker／major／minor。

**影响。** 执行者可能在正确验收清单下实施错误步骤；draining会被归因不存在的replacement，funded replay会先flush，known failure codes仍不retry，headers继续按漏项名单。

**建议。** §5.1第三行改为引用§5.2的三类结果，不再枚举draining为replacement failure。Plan第51行加入§5-before-§7.2 gate；第57行改为三code mapping + typed reopen result；第63行改semantic header predicate。然后做一次语义槽扫描，而不只grep旧token：每个事实只保留一处当前指令，其余改引用。

**证据强度。** 被评两个living文档逐字保留旧行为，强静态证据；这是本主题反复出现的同形问题，不是历史修订记录应保留的旧话。

**承重前提检查。** 前提是“Plan v4已同步v5，旧话只剩主动说明”；第51／57／63行都是当前实施命令，直接证伪。

### direct-responses-passthrough-spec-review-round5-04

- finding_id：`direct-responses-passthrough-spec-review-round5-04`
- severity：`major`
- primary_location：`spec.md:254-277`
- related_locations：`plan.md:59-63`；`src/app/server/routes/inference.py:524-573`；RFC 9110 §8.8
- 标题：Header predicate与例子不一致，non-stream `Content-Type`又落入“其余一律转发”

**证据一：predicate与例子。** v5的规范predicate是“验证或描述上游确切字节、且代理未重新计算”，这条不会过度剥离：`Content-Digest`／`Repr-Digest`／`Content-MD5`／`Content-Range`以及strong ETag在body reserialize／reframe后失效，必须strip或重算。但同一句的例子还列 `Last-Modified`与不分强弱的`ETag`：`Last-Modified`描述origin resource修改时间，不验证响应octets；weak ETag的目的就是标识语义等价而非byte-identical representation。它们不满足前面的predicate，却会因例子被实现成固定strip。

**证据二：non-stream Content-Type。** §9明定成功body先parse为JSON object再由`JSONResponse`序列化，并准确陈述“原Content-Type不保留”。§9.1只重建**流式**`Content-Type`，随后规定“其余一律转发”，于是non-stream upstream `Content-Type`会被转发。反例：upstream以`text/html`或vendor type承载一个可解析JSON object；proxy输出自己的JSON bytes却仍告诉client是原media type。若headers传给`JSONResponse`，显式Content-Type还会压过它本应生成的`application/json`。这与§9当前行为陈述及客户端按media type解析的需要相冲突。

**客户端需要面的判断。** `Last-Modified`／weak ETag可参与cache validation，剥掉会损失能力；本Responses POST路径上实际消费者与发生率未验证。strong ETag若不重算仍必须剥。产品可以保守全剥weak validators，但须明确这是“stream可能后来截断／semantic equivalence不保证”等取舍，而不是exact-byte predicate的必然推论。

**建议。** 明定non-stream成功body的`Content-Type`由proxy按实际输出重建为JSON media type，只有兼容的upstream JSON media type才可选择保留；从exact-byte例子删`Last-Modified`，把`ETag`拆成strong strip/recompute与weak preserve-or-explicitly-drop。Plan只引用predicate并列真正exact-byte正例，不复制易漂的完整名单。

**证据强度。** non-stream可构造错误会改变客户端解析，支持major；validator部分由标准语义直接证明predicate与例子不一致，实际cache使用未验证。

**承重前提检查。** 前提有二：“例子中每个字段都描述exact upstream bytes”与“non-stream Content-Type仍描述proxy输出”；`Last-Modified`／weak ETag及任意非JSON upstream media type分别证伪。

## §7.2入口门与§5 commit状态专项结论

**三种commit状态穷尽且互斥，没有第四种。** 可写成：

1. `not committed ∧ replay selected`：旧attempt零提交丢弃；
2. `not committed ∧ no replay selected`：进入final ending；
3. `committed`：whole-attempt replay非法，进入final ending。

`client cancel／downstream write failure`是write-channel availability，不是commit state；`ongoing`尚未到ending，不进表；keepalive／HTTP headers按§5不构成native commit。这个partition可以直接实施。

当前唯一缺陷是第2格不能自行决定final carrier。它还要读取ending source：有upstream terminal／failure就原样提交；无则proxy error；无write channel则不写。修round5-01后，§3丢suffix、§4保持remaining相对序、§5不重复replay、§7 flush complete groups可同时成立。

## `rate_limit_exceeded` → 既有rate-limit处置专项结论

**这次不是把Spec决定推给别处。** v5已经定了产品语义：该native code与HTTP 429同类；必须进入reactive limiter；不得普通即时retry；最终仍受request-global budget。既有`RateLimiter`是这组节流／恢复行为的authority，重复抄它的`retry_interval`、limited mode与recovery会制造第二份Spec。

实现接线仍须在Plan说清：native event adapter向既有limiter提供429 signal；stream event没有`Retry-After`响应头时按limiter既有default interval；budget reason继续走现有server-error槽。函数名、synthetic exception还是typed signal属于Plan。当前Plan第57行仍写“一律不重试”，所以**Spec合同够了，Plan没同步**，归round5-03而非新产品finding。

## §11空清单复核

**当前不名副实。** round5-01的precommit final carrier与round5-02的`vector_store_timeout` mapping仍是Spec级行为未闭合；round5-03中的`ReopenRefused`在§5.2已定、只是§5.1冲突，修同步即可，不是新fork；round5-04是header规则表述冲突。

修完这些后，本轮未发现第四种commit状态或另一个未裁产品fork。§11可以真正为空，不必为了保守留占位项。

## Plan step 2并行开工判断

**yes，可以并行开工；这不是“主体实现已获通过”。** 允许范围：

- 新建direct assembler／raw framer类型；
- 保存`SseEvent.event`与`data`原文；
- 跟踪item open／done，形成complete group与safe prefix；
- 保持原序，保留每event ids／sequence／unknown fields；
- unit smoke只证明这些纯转换／分组事实。

明确不能借step 2先定：

- `stream_delivery`接线、route switch或改issue integration assertions；
- policy buffer／`until-tool-use` release；
- final ending／flush／discard orchestration；
- replay eligibility、budget spending、replacement outcome；
- response headers与observability record终态；
- 把骨架当前API当stable跨层接口。

理由是这些边界都在orchestrator而非raw group/framer核心，round5残留不会改变“完整group按原event/data原序携带”这一不变量。若骨架把`finish()`设计成自动flush或把failure event直接变proxy error，就已越出允许范围，应停。

## 文档分层复核

元判断只部分落地。Plan确实接收了typed reopen carrier、adapter、测试与实施顺序；但Spec仍保留`encode_frame(event,data)`、`data.split()`、atomic parser缺陷、`driver.py`／`replay_reason`／`StreamFailure`／`hand_back_block`／`JSONResponse`等实现证据与Python符号，§4也仍规定“维护全局事件队列”。这不造成新的行为finding，却继续扩大同步面。

建议在本轮行为收口后做一次**不改变normative semantics**的瘦身：Spec保留predicate、observable outcome与provenance；Plan接走具体载体、函数、现状差距与测试。不要在尚有blocker时大搬文字，以免混入语义改动。

## 显式排除掉的可能性

1. **“§7.2仍会在funded replay前flush”——排除。** 第225／237行已明确零字节提交。
2. **“三格commit partition漏了第四种状态”——排除。** write-channel availability与ending source是正交轴，不是第四commit值。
3. **“第二格永远应写proxy error”——排除。** successful upstream terminal与nonretryable native failure均在第二格且有原生carrier。
4. **“budget-exhausted native failure因为预算耗尽就不再是upstream failure”——排除。** budget改变是否retry，不抹掉已收到的terminal source。
5. **“删除unfinished suffix会重排remaining complete groups”——排除。** relative order保留；sequence gap不等于倒退。
6. **“`rate_limit_exceeded`引用既有limiter就是Spec bypass”——排除。** semantic mapping已定，复用另一authority优于复制其参数与状态机。
7. **“rate-limit event有`Retry-After`可直接复用”——未作此假设。** event code本身不携HTTP header；无signal时走limiter既有default。
8. **“其余18个Literal都明确non-transient”——排除。** `vector_store_timeout`是逐字反例。
9. **“`failed_to_download_image`也一定retryable”——未作此判断。** 名称不足以区分永久URL错误与瞬时transport；保持None。
10. **“draining属于replacement attempt failure”——排除。** 没有attempt；§5.2已正确归`ReopenRefused`。
11. **“§5.2更具体，所以§5.1旧行无害”——排除。** 两者都是normative table，且Plan仍选择旧版本。
12. **“Plan v4只剩主动说明v2错误的元文本”——排除。** 第51／57／63行是当前命令，不是历史。
13. **“header semantic predicate必然过度剥离”——排除。** predicate准确；过度来自与它不相符的例子。
14. **“所有ETag都精确描述bytes”——排除。** strong与weak validator语义不同。
15. **“Last-Modified应随body reserialization失效”——排除。** 它描述origin修改时间，不是body digest。
16. **“Skeleton必须等所有ending收口”——排除。** 未接线raw grouping不决定orchestration。
17. **“Skeleton接口可以现在冻结”——排除。** 后续delivery integration仍会决定跨层API。
18. **“§11空意味着本轮一定pass”——排除。** 正文仍存在冲突与漏分支；ledger文字不是oracle。
19. **“Spec实现细节已经全部移Plan”——排除。** 多个Python symbol与algorithm仍在正文；只是不构成行为阻断。
20. **“旧tests绿能证明v5状态机”——排除。** 主体未实现，本轮没有以旧suite替代Spec评审。

空清单声明：以上是本轮实际考虑并排除或限定的可能性；没有把未知upstream发生率、缓存消费者或未来code猜成severity finding。

## 搜索面、执行证据与限制

### 判据来源

- 前四轮报告及其已核用户亲笔合同。
- `docs/.human-controlled/upstream-retry-and-continuation.md`、`config.example.yaml`的retry／reactive limiter条款。
- 本地OpenAI SDK 3.3.1 `response_error.py`。
- RFC validator语义沿用round3／round4已取得的一手标准依据。

### 被评与代码面

- Spec v5、Plan v4全文。
- `pipeline/rate_limiting.py`、`pipeline/retry.py`、`pipeline/exceptions.py`、`pipeline/direct_driver/base.py`、`driver.py`、`inference.py`相关状态机。
- 没有读取并行skeleton WIP；本轮对“能否开工”的判断基于Plan step边界，避免把尚在变化的实现反推成判据。

### 执行证据与限制

- Bash因当前session被绑定到`260831-passthrough-skeleton`而拒绝从`.dev`cwd执行共享树搜索；遵照提示没有绕过，改用绝对路径`Read`静态核对。
- 未运行tests／probe：主体尚未实施；核心发现由规范表、SDK Literal与现有typed control flow静态闭合。
- 未真实调用upstream，native failure code发生率仍unknown。
- `.dev` HEAD `7bd8888`由调用方给定，并以`.dev/.git/logs/HEAD`末条独立对上；目标bytes来自绝对路径`Read`的当前snapshot。
- 指定report path的`Write`被worktree isolation guard拒绝，按预案写到`/tmp/260831-review-spec-round5.md`。

## 严重度汇总

- blocker：1
- major：3
- minor：0
- nit：0
- finding_total：4

## 两个开工结论

- **骨架可否并行开工：yes。** 仅限Plan step 2的未接线pure skeleton与unit smoke，边界如上。
- **可否据此开始主体实现：no。** 先修round5-01的final source、round5-02的timeout mapping，并清掉Spec／Plan当前旧话；随后这份Spec才有资格进入主体接线与状态机实现。

## 收尾判断

本轮不触发开发closeout：评审完成但Spec仍有1 blocker，主体边界未到；并行skeleton是另一执行单元且本轮未读写其产物。本轮只有报告需要交付，没有source/test／commit／worktree处置。

