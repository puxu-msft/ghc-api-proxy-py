# 直连 Responses 原生透传产品规格独立复评（round 4）

- report_id：`direct-responses-passthrough-spec-review-round4`
- attempt_id：`260830-review-spec-4`
- reviewed_at：2026-08-30
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v4）与同目录 `plan.md`（v3）
- 对照基线：`/tmp/260830-review-spec-round3.md`
- 评审性质：只读规格／计划复评；未修改 `src/` 或 `tests/`；未派 agent

## 评审范围

本轮沿用前三轮已建立的独立判据，重点重新遍历最终状态而非只勾 round3 清单。覆盖：§3 fidelity／unfinished suffix、§4 safe frontier、§5 pre/post-commit replay、§5.2 native failure code、§7 三种 policy 与所有 ending、§8 proxy error、§9.1 headers、§11 空清单、Plan v3 的步骤与验收，以及当前 `stream.py`／`retry.py`／`inference.py` 接口。

新增一项一手协议核对：本地 `openai==3.3.1` generated model `ResponseError.code` 的 Literal 集，用来检验“本项目没有 native failure code 语义表”的前提。另读取当前 integration tests，核 Plan 第 78／85 行所说的 issue #1／#2 测试是否真能按该顺序转绿。

明确不在范围内：实施主体、修改被评文档、修改生产代码或测试、真实 Copilot 调用、验收已经合入的 P1／P2、重新裁定用户亲笔的 retry／buffering 原则、生产 4141 服务的任何操作。

## 总体 verdict

**needs-fix。当前不可据此开始主体实现。blocker 数：1。**

v4 已把 round3 的四个修订方向写进正文，整体明显收敛；唯一新 blocker 是 §7.2 把“任何 ending”一律收口写得过宽，使首个 native event 提交前、仍获 budget 的 replayable tear／EOF 既要按 §5 丢弃旧 attempt 并 replay，又要按 §7.2 先提交 complete groups而关闭 replay。另有两条 major：§5.2 以“没有 code 语义表”为由把 `server_error`／`rate_limit_exceeded` 也判不重试，但 SDK 已给出这两个明确成员，且 `full` 下 pre-commit window并不窄；replacement 的 HTTP failure／refusal／draining 仍被统称为 exception 与 replacement attribution，后者没有 replacement。Header 与 Plan 各剩一条 minor 级残留。

## Round 3 四条处置状态

| finding_id | round3 级别 | 状态 | 判据与结论 |
|---|---:|---|---|
| `direct-responses-passthrough-spec-review-round3-01` | blocker | partially-closed | policy-held complete groups 已裁为 final ending 时原序提交；但“任何 ending”未排除仍将透明 replay 的 attempt，且 `full` 主表仍写只等 upstream terminal，见 round4-01 |
| `direct-responses-passthrough-spec-review-round3-02` | blocker | partially-closed | native event adapter 已有表，clean EOF 与 replacement source方向已写；但表的“无 code 语义”前提被 SDK证伪，draining／outcome error 也未形成三态 result，见 round4-02／03 |
| `direct-responses-passthrough-spec-review-round3-03` | major | partially-closed | dynamic `Connection` tokens 与主要 validator/digest 已加入；仍漏既有 `Proxy-Connection` 与 legacy `Content-MD5`，且 `Content-Encoding` 的动作仍写成含糊的“重建”，见 round4-04 |
| `direct-responses-passthrough-spec-review-round3-04` | major | closed | signature、正例、§9 旧句、§11、文首与 Plan 主体均已同步；只剩 Plan 自己早已有的步骤／测试时点冲突，作为独立 minor 见 round4-05 |

状态计数：`closed=1`、`partially_closed=3`、`not_closed=0`。

## 当前系统状态：新发现与残留发现

### direct-responses-passthrough-spec-review-round4-01

- finding_id：`direct-responses-passthrough-spec-review-round4-01`
- severity：`blocker`
- primary_location：`spec.md:106-122,177-183,203-221`
- related_locations：`spec.md:61-69,223-229`；`plan.md:45-57`；`src/app/pipeline/delivery/stream.py:456-473`
- 标题：“任何 ending 一律收口”把仍可透明 replay 的 attempt 先提交了，和 §5 的 commit gate 互斥

**证据。** 取 `full` policy：upstream 已产生 complete group A，但尚无 terminal，随后发生 transport tear；客户端尚未看到任何 native event，ledger 仍有 budget。§5 明定此时旧 attempt 的 control／item queue／ids／usage 全丢并透明 replay；§3 也只承诺“最终被提交的那一次 attempt”，所以丢 A 合法。§7.2 却称“任何 ending 到达时”一律提交 control + 所有 complete groups + error，并在表里把 tear列入收口。只要先发 A，首个 native event就已提交，§5 紧接着禁止 whole-attempt replay；先 replay则不能执行 §7.2。clean EOF 有 budget 时同形。

**正确交互。** 首个 native event已经提交后，逻辑闭合：§5 禁止 replay，§7.2 收口剩余 complete groups并写 final error。首个 commit 前也只有在 replay不可用、被拒或 budget耗尽后，§7.2 才是 final ending。冲突仅来自“ending”把 **replay candidate** 与 **最终 client-visible ending** 混成一个词。

另有两个同类 restatement需同步：§7 主表仍写 `full`“上游终局后”才发，与 §7.2 的“任意最终 ending”不同；§8 把“下游交付失败”列为必须写 SSE error，但 §7.2 已正确承认下游无可写通道。这两处不另计 finding，随本条一起修。

**影响。** 照 §7.2 实现会关闭用户亲笔允许的 pre-commit无痕重试；照 §5 实现又会违反“任何 ending 一律收口”。这不是执行顺序细节，而是客户端收到旧 attempt partial answer还是全新 attempt的产品行为。

**建议。** 把 §7.2 的入口改为“replay 判定完成后的最终 ending”：先按 §5 判断；若 funded replay，则整次旧 attempt无提交丢弃，§7.2 不运行；若不可 replay／budget耗尽／post-commit，才按 §7.2 收口。policy表新增 funded replay一行或在表前写唯一 precedence。`full` 主表改为“所有可提交事件在任意最终 ending时一次发出”；§8 对 client cancellation／downstream write failure显式引用无写通道例外。

**证据强度。** 有 budget的 pre-commit tear 是现有状态机直接支持的状态，两个规范给出相反动作，强到 blocker；不依赖 upstream failure event样本。

**承重前提检查。** 前提是“每个 tear／EOF 都已经是最终 ending”；它支撑“任何 ending一律收口”。存在 funded transparent replay时该前提为假。

### direct-responses-passthrough-spec-review-round4-02

- finding_id：`direct-responses-passthrough-spec-review-round4-02`
- severity：`major`
- primary_location：`spec.md:132-147`
- related_locations：`.venv/lib/python3.14/site-packages/openai/types/responses/response.py:198-208`；`.venv/lib/python3.14/site-packages/openai/types/responses/response_error.py:10-35`；`.venv/lib/python3.14/site-packages/openai/types/responses/response_error_event.py:11-27`；`docs/.human-controlled/upstream-retry-and-continuation.md:3-24`；`plan.md:53-57`
- 标题：`response.failed` 已有可判的 retryable codes，“当前一律不重试”的事实前提不成立

**证据。** OpenAI SDK 3.3.1 的 `Response.error` 直接声明为 `ResponseError`；其 `code` 是 Literal 集，前两个成员就是 `server_error` 与 `rate_limit_exceeded`，其余包括 `invalid_prompt`、policy／image 等明确非瞬时失败。`response.failed` 正是携带这个 `Response`。因此“唯一判据是上游 code，而本项目没有该 code集的语义表”不成立：SDK generated type已经给出 code集，至少这两个值能无猜测地映射到用户亲笔 taxonomy 的 5xx／429“通常可继续”。五份 cassette零出现只证明当前样本没有命中过 failure event，不能抹去 protocol type 的分辨力。

flat `error` event 的 `code` 是开放 `str | None`，但同样可以只认这两个已知 spelling、其余保守 `None`；这不需要把未知猜成 retryable。`response.cancelled → None` 也合理，取消是终局决定，没有证据支持 replay。本 finding反对的是把**已知瞬时 code**与 unknown一起压成 `None`，不是要求默认重试所有 failure。

**窗口宽度复核。** “首个 native event前的窗口本来很窄”只对迅速完成首个 safe group 的 `block` 倾向成立，不能支撑全局决策。`full` 在整个 upstream turn终局前都不 commit；未触发 action 的 `until-tool-use` 也可持有整个 turn；`block` 遇长 reasoning或较早 unfinished item同样可长时间不 commit。故 `response.failed` 到达时，`full` 下透明 replay窗口实际上覆盖整次 attempt，而不是尾端小窗。

**影响。** 一个明确 `server_error`／`rate_limit_exceeded` 的 attempt在客户端尚未看到任何 native event时会直接失败，而不是按既有 contract透明恢复；`full` 恰是损失最大的一种 policy。rate-limit code若要复用既有 reactive limiter，还需把该事实送入同一 limiter路径，不能只当普通 immediate server retry。

**建议。** 保留 conservative unknown fallback，但把 `response.failed.response.error.code == "server_error"` 映为 `SERVER_ERROR`；`rate_limit_exceeded` 进入既有 rate-limit处置并最终使用现有 reason/budget；其余 SDK Literal与 unknown均 `None`，除非后续实测支持放宽。flat／nested `error` 对已识别 spelling同样处理。Spec 记录语义 outcome，具体 adapter函数留给 Plan。

**证据强度。** SDK generated Literal与用户亲笔 5xx／429 taxonomy交叉支持，强到可直接修表；CAPI真实 failure事件发生率仍未验证，只限制频率判断，不限制 exact code出现时的语义。

**承重前提检查。** 前提是“code集完全未知，所以任何映射都是猜”；SDK给出 closed Literal并命名两个瞬时类别，前提为假。

### direct-responses-passthrough-spec-review-round4-03

- finding_id：`direct-responses-passthrough-spec-review-round4-03`
- severity：`major`
- primary_location：`spec.md:124-130,145-147`
- related_locations：`plan.md:53-57`；`src/app/server/routes/inference.py:395-461`；`src/app/pipeline/driver.py:190-207`；`src/app/pipeline/delivery/stream.py:78-90,467-473`
- 标题：replacement HTTP failure、local refusal 与 draining 仍被误写成同一种 exception／replacement attribution

**证据。** §5.2 写“建流前 HTTP失败、拒绝、draining返回 `None`……它是一个 exception，直接进 `replay_reason`”，Plan复述。当前 `_reopen` 却在 draining 时**尚未调用 `handle`**便返回 `None`，没有 replacement attempt、没有 exception；`handle` 对常规 upstream拒绝返回 `HandledRequest.outcome.error`，随后 `_reopen` 因 `response is None` 也返回 `None`。一个是本代理拒绝开新 attempt，一个是已经尝试后的 upstream outcome，当前接口把两者压成同形，不能靠一句“它是 exception”恢复来源。

即使实施时把 `outcome.error` 从 result取出交给 `replay_reason`，仍必须把 local shaping／translation refusal与 upstream HTTP failure分开；只有真正由 replacement upstream产生的 failure才能归因 replacement。draining应是 proxy-origin refusal，并按 §8 的客户端方言 SSE error表达；它不能满足“客户端看见 replacement 的失败”，因为 replacement根本不存在。

**影响。** draining或本地拒绝可能被记录为 upstream replacement failure；真实 replacement HTTP error又可能继续被 `None`吞掉、回退旧 attempt failure，重开 round3已经裁掉的行为。

**建议。** 在 Spec把 replacement结果写成三类 observable fact，而不是绑定 Python raise形态：`OpenedAttempt`；`AttemptFailed`，携带 actual attempt的 error／origin；`ReopenRefused`，例如 draining或本地前置拒绝，origin=proxy。Plan再据此把 `Attempt | None` 改为 typed result；actual upstream error可复用 `replay_reason`，proxy refusal不得进入 upstream retry。

**证据强度。** draining分支位置与 `outcome.error → None` 控制流是强静态证据；无需运行 upstream probe。

**承重前提检查。** 前提是“所有 reopen失败都已经打开 replacement并以 exception抛出”；draining与 `HandledRequest.outcome.error` 分别从两面证伪。

### direct-responses-passthrough-spec-review-round4-04

- finding_id：`direct-responses-passthrough-spec-review-round4-04`
- severity：`minor`
- primary_location：`spec.md:239-253`
- related_locations：`plan.md:59-63`；`docs/.human-controlled/message-format-reshape.md:51-63`；`.venv/lib/python3.14/site-packages/httpx2/_models.py:871-900,979-1001`
- 标题：Header 主算法已修，但固定逐跳与 exact-octet metadata仍各漏一例

**证据。** v4 已正确加入 dynamic `Connection` tokens与 validator／digest层，round3最承重的两个反例关闭。剩余固定名单仍漏用户亲笔旧表已列的非标准 `Proxy-Connection`；representation list仍漏 round3明确举出的 legacy `Content-MD5`，于是两者会落入“其余一律转发”。此外 `httpx2.read()`／`aiter_bytes()`都经 content decoder，生产路径继续使用它们时 upstream `Content-Encoding` 的正确动作是“删除；只有代理重新编码才设置新值”，而“必须重建（若已解压）”仍可能被读成复用原值。

**影响。** legacy client/proxy header可能跨 hop，legacy digest会校验代理已经改写后的不同 bytes而失败。主流 current headers已覆盖，故从 round3 major降为 minor；这不是说协议错误变成无害，而是剩余面已窄。

**建议。** 固定表补 `Proxy-Connection`；把 representation条款写成语义 predicate——任何验证／描述 exact upstream octets且代理未重算的 field都剥离，`Content-MD5`作为例子，而非继续扩一个自称穷尽的名字表；`Content-Encoding`明确为 strip-or-reencode。`Last-Modified`与 weak ETag不是 exact-byte digest，当前一律剥离是保守的功能取舍，不构成 correctness blocker，但若追求“尽可能原样”可另行收窄。

**证据强度。** 两个具体 header可直接构造；影响范围是 legacy／非主路径，支持 minor而非更高等级。

**承重前提检查。** 前提是“新增名单已经覆盖之前 finding 的全部具体反例”；`Proxy-Connection`与`Content-MD5`仍不在名单，前提为假。

### direct-responses-passthrough-spec-review-round4-05

- finding_id：`direct-responses-passthrough-spec-review-round4-05`
- severity：`minor`
- primary_location：`plan.md:75-91`
- related_locations：`plan.md:20-27`；`tests/int/test_pipeline_app.py:2528-2582`
- 标题：Plan 同时说 step 2 让 issue #2 测试转绿，又禁止在 step 7 前改它当前的 rejection 断言

**证据。** 当前 `test_an_output_item_this_assembler_does_not_know_is_refused_not_rendered` 明确断言 direct `custom_tool_call` 最后是 `error`、包含 `unknown_output_item`、没有任何 `response.output_item*`。Step 2 建 direct passthrough assembler并接分流后，正确行为恰好相反：原生 item events与 terminal必须出现，该测试必红，除非同时改断言。Plan 第 85 行却说 step 2 后 issue #1／#2复现应转绿，同时要求 step 7 前不要改这两条断言。三句不能同时成立。

项目允许语义中间提交暂时红，所以这不构成产品 blocker；缺陷是 Plan把“可以暂时红”写成“已经绿”，让执行者无法判断 step 2终态。Step 7 的“撤销 `ca777df` direct一半”实际上与启用 direct assembler是同一个 observable switch，不能在代码已绕开旧 assembler后再撤一次。

**建议。** 把 direct route activation、撤销 direct `REJECT` 与两条测试断言更新放在同一个语义步骤；若 step 2 只建未接线 skeleton，就明确它只跑 unit smoke、不宣称 issue tests绿。Plan §9 的“尤其”清单也补 funded replay不收口、policy×final-ending、known native failure code与 dynamic headers，避免最新承重点只在正文出现。

**证据强度。** 测试当前断言与 Plan步骤逐字相反，强静态证据；只影响执行顺序与完成信号，定为 minor。

**承重前提检查。** 前提是“step 2启用 passthrough但不改变现有 rejection test”；测试正是在 production direct route上断言 rejection，前提为假。

## §7.2 与 §3／§4／§5 的交叉结论

### 已自洽的部分

- 未完成 item events 在最终 ending 丢弃；complete groups 保留，二者不再混同。
- 删除某个 unfinished group 的 events 后，其余 complete groups／control／terminal保持原相对次序；这是删除，不是重排。原始 `sequence_number` 可能有 gap，但不倒退，也不需改写。
- `block` 已提交的 prefix不重复发；`until-tool-use` 触发后永久按 `block`；未触发与 `full`在最终 ending统一 flush。
- upstream terminal／failure 是最终 ending时，顺序“丢 unfinished → 提交 remaining complete groups → terminal／failure”闭合。
- 首个 native event已经提交后，whole-attempt replay被禁止，§7.2负责收剩余 queue并结束，二者一致。
- client cancellation／downstream write failure确实没有 wire通道；§7.2 的例外正确，只需同步删除 §8 的相反全称。

### 未自洽的唯一承重交互

首个 commit前的 tear／EOF只是 replay candidate，不一定是 final ending。必须先走 §5；只有 replay不允许或预算耗尽才进入 §7.2。v4没有写这层 precedence，见 round4-01。

## §5.2 “当前一律不重试”的判断

**结论：对 unknown code保守 `None` 合理；对 SDK已经命名的 `server_error`／`rate_limit_exceeded` 一律 `None`，过保守且有害。**

代价也不小。`full` 的 first-commit window覆盖整个 attempt；未触发的 `until-tool-use`同样可能覆盖整个 turn；`block`在首个长 item／交错 blocker下也可很长。故“窗口本来很窄”最多是普通 `block` happy path的倾向，不能支撑全 policy合同。

这项判断的证据等级是**强到可直接修表**：SDK generated type给出 exact code，用户亲笔 taxonomy给出 server error／rate limit可继续。真实 CAPI cassette零样本只让 occurrence rate保持 unknown，不让 exact spelling的语义也变 unknown。应继续保守的范围是所有未声明／未识别 code，以及 `response.cancelled`。

## §11 空清单复核

**当前不名副实。** round4-01 的 final-ending precedence与 round4-03 的 draining origin仍是真产品分叉，尚未被正文唯一决定；round4-02 是已作决定但与现有 authority／SDK冲突，必须纠正后才能称闭合。Header residual与 Plan sequencing不是产品分叉，可不进 §11。

在修完上述三项后，本轮没有再发现别的真实产品 fork需要挂 §11：unknown native failure fallback、unfinished suffix、complete policy-held groups、headers、client-action predicate、reasoning／ids、non-stream fidelity都已有明确 outcome。这个否定只覆盖本轮列出的 sources与当前 SDK 3.3.1，不外推未来协议成员。

## Plan v3 对齐复核

Plan 主体已与 Spec v4 同步：signature、item-side semantics、policy×ending、native adapter、headers、P1／P2 main状态均更新，未新增 Spec外的 wire promise。

残余有三类：

1. Spec 自身的 round4-01／02／03会被 Plan第 51～57 行照搬，修 Spec时必须同步。
2. Header第 63 行重复了 residual closed list，随 round4-04改为 semantic predicate。
3. 第 78／85 行的 issue #2 test时点互斥，见 round4-05；§9“尤其”清单也未加入最新四个承重点。

Plan 第 18 行声称 P1／P2已经变异验证。本轮没有修改 source做独立 mutation，因用户明确禁止；因此该句的 evidence status是 **author claim, unverified in this review**。我独立确认 `7e96adc` 当前指在 `main`，且此前 targeted suite绿；这不替代 mutation claim。该证据限制不影响本轮 Spec verdict。

## 四轮 blocker 走势与 Spec 粒度判断

**判断：行为层面是正常收敛，文档层面确实混入了可以下放的实现细节；新 blocker不是“Spec写太细”造成的，而是新增状态维度后没有重新计算已有维度的优先级。这个判断强到可以据此重构文档。**

`3 → 3 → 2 → 1` 已在单调下降。四轮 blocker分别决定客户端最终收到哪些 events、是否泄漏 partial item、是否 whole-attempt replay、哪个 attempt的失败可见、完整 groups发还是丢；这些都是外部行为，不能留给实现边做边定。round4-01尤其说明删掉行为细节只会把同一个 fork重新藏回代码，不会让它消失。

但每轮“新 blocker落在上一轮新增章节”也不是纯正常噪声。它揭示的过程问题是局部补 paragraph，而不是把 `commit state × policy state × buffered state × ending cause × write-channel availability` 放回同一个权威 transition表重算。机械 grep只能找到同词残留，找不到“任何 ending”与“replay candidate”的语义冲突；v4就是新证据。正确收敛手法不是再加一套 proof gate，而是让 §5／§7.2共用一张 final-ending precedence表，其他段只引用它。

### 可以移到 Plan／status、边实现边定的内容

- §3.1 的 `encode_frame(event,data)` signature、`data.split("\n")`、atomic regex与旧缺陷实跑叙事；Spec只留 logical round-trip与 CRLF／LF／CR均合法。
- §4 的具体“全局 queue”数据结构；Spec保留 safe prefix、完整 group与不重排，Plan决定容器／索引。
- §5.2 的 `replay_reason`、`reason_for`、`StreamFailure` 等 Python符号与 adapter形态；Spec必须保留 event code→retry outcome、unknown fallback和precedence。
- §6.4 的 `driver.py` 调用门、decoder所在函数与“需要一条测试”；Spec只留 direct leg不解 carrier，Plan负责接线／测试。
- §8 的 `hand_back_block()`当前返回值等实现证据；Spec只留 direct leg不走 Anthropic hand-over。
- §9／§9.1 的当前 `JSONResponse`／`_AccountedStreamingResponse`源码观察与“各自要测试”；Spec保留 value fidelity与 header algorithm，Plan记录现状差距。
- §10 的 `Terminal.stop_reason` default、`BlockBuffer.kind`耦合等代码怪味；Spec保留必须记录的 facts与 unknown≠absent，Plan选 record shape。
- `requires_client_action(item)` 的 Python式 signature可放 Plan；Spec保留语义 predicate、正反例与 item-side字段来源。

### 不能下放的内容

§3 的哪些 events会丢、§5 的 commit/replay边界与 failure mapping、§6 的 wire fidelity、§7 的 policy release与 final ending、§8 的 error carrier、§9 的 JSON／headers、§10 的对外可观测事实都必须先定。它们不是实现术语多就变成实现细节。

所以我的建议不是缩减行为 scope，而是**瘦身证据与机制描述，集中状态转换 authority**。第三次漏同步的根因也会随重复 restatement减少；但不要用“留给实现”替代仍会改变 wire的决定。

## 显式排除掉的可能性

1. **“v4 的 policy-held complete groups仍无去向”——排除。** final ending时原序提交已经定案；剩余 blocker只是 replay candidate不应过早进入 final收口。
2. **“任何 upstream tear天然就是 final ending”——排除。** pre-commit且有 budget时，§5明确把它变成 replacement触发器。
3. **“先提交 complete groups再 whole-attempt replay仍可无痕”——排除。** 第一 native event一旦可见，§5自己禁止 replay。
4. **“replay丢掉旧 attempt的 complete groups违反 §3”——排除。** §3承诺只覆盖最终 committed attempt，旧 attempt在 replay时整体作废。
5. **“删除 unfinished item events等于重排 remaining events”——排除。** remaining events相对序未变；sequence可能跳号但不倒退。
6. **“`full` 必须等 success terminal，failure flush complete groups一定违约”——排除。** 用户文字是等 response结束；v4把 final failure也裁作结束，这个产品选择自洽。
7. **“native failure event一律不重试几乎没有代价，因为窗口很窄”——排除。** `full`与未触发的 `until-tool-use`给出整轮 pre-commit窗口。
8. **“零 cassette样本证明 code没有协议语义”——排除。** 它只证明样本未出现；SDK generated Literal仍定义 exact code。
9. **“所有未知 native failure都应 retry”——排除。** unknown继续 `None`合理；finding只认 `server_error`／`rate_limit_exceeded`。
10. **“`response.cancelled`也应按 server error replay”——排除。** 没有依据；保持不重试。
11. **“`rate_limit_exceeded`只映成 ordinary immediate `SERVER_ERROR`就够”——排除。** 用户合同还有 reactive limiter语义，adapter必须复用那一层。
12. **“draining是 replacement的失败”——排除。** replacement未打开；它是 proxy拒绝 reopen。
13. **“`outcome.error`一定以 exception从 `handle`抛出”——排除。** 当前 driver把常规拒绝放在 result，`_reopen`再压成 `None`。
14. **“dynamic Connection tokens加入后 header finding全关”——排除。** 固定 `Proxy-Connection`与 exact-byte `Content-MD5`仍落入 default forward。
15. **“wire response headers应改用 cassette allowlist”——排除。** 没有同一 persistence hazard，unknown end-to-end headers默认保留仍成立。
16. **“Last-Modified／weak ETag必须保留，否则是 correctness defect”——未作此全称。** v4选择剥离是保守功能损失；可优化但不占 severity。
17. **“§11写空就说明没有产品分叉”——排除。** final-ending precedence与 draining origin仍未唯一。
18. **“Plan v3仍整体落后 Spec”——排除。** 主体已同步；剩余是两条 Spec residual的转录与一个原有步骤矛盾。
19. **“全仓 grep能证明同类语义都同步”——排除。** grep可找旧 token，找不到 final ending／replay candidate这类同义冲突。
20. **“四轮新 blocker说明所有状态机细节都该下放实现”——排除。** 每条 blocker都改变 wire或 replay；可下放的是数据结构、函数名、测试位置与历史证据。
21. **“Spec完全没有过细”——排除。** 多处 Python符号、算法与现状证据可移 Plan；结论不是非黑即白。
22. **“P1／P2 mutation claim已由本轮独立复现”——排除。** 本轮未获修改授权，未做 mutation；只确认 main commit存在。

空清单声明：以上是本轮实际考虑并排除或限定的可能性；没有把 future code、未知 CAPI occurrence rate或未执行 mutation写成 severity finding。

## 搜索面、执行证据与限制

### 判据来源

- 前三轮报告及其中已核过的用户亲笔 `client-side-block-delivery.md`、`upstream-retry-and-continuation.md`、`message-translation.md`、`message-format-reshape.md`。
- `.dev/docs/error-envelope/spec.md` 与项目 living-Spec／Plan规则。
- 本地 OpenAI SDK 3.3.1 generated types：`response.py`、`response_error.py`、`response_error_event.py`、`response_failed_event.py`。

### 被评与代码面

- Spec v4、Plan v3全文。
- `stream.py`、`retry.py`、`hand_over.py`、`inference.py`、`driver.py`、`openai_responses.py` 的既有 ending／reopen接口。
- `tests/int/test_pipeline_app.py:2528-2582` 的 direct unknown-item regression。
- `httpx2/_models.py` decoded-body合同与 RFC 9110／9530 header规则沿用 round3核验结果。

### 执行证据与限度

- 只读 `git show`／ancestor核对确认 `7e96adc` 当前在 `main`，提交内容是 P1／P2三文件改动。
- 使用 `rg -u`定位 issue #1／#2 tests并读取具体 assertion；没有用目录遍历零命中作结论。
- 未运行 tests：本轮核心发现是 Spec／Plan内部状态与 SDK type静态反例，旧 suite不能回答；P1／P2不是本轮验收对象。
- 未做 mutation，Plan第18行的变异声称本轮标为 unverified author claim。
- 未作真实 upstream call；native failure发生率未知，但 exact SDK code出现时的分类可判。
- `.dev` HEAD `9a718f2`采用调用方给定值，未跨 background isolation guard独立验证；被评 bytes来自绝对路径 `Read` 的当前 snapshot。
- 指定 report path的 `Write`被 background isolation guard拒绝，按预案写到 `/tmp/260830-review-spec-round4.md`，未绕过守卫。

## 严重度汇总

- blocker：1
- major：2
- minor：2
- nit：0
- finding_total：5

## 可否据此开始实现

**no。** 先把 replay candidate排除在 §7.2 final收口之外；同时修正已知 retryable native codes与 reopen三态，再同步 Plan。Header／Plan两个 minor可以与同次文档修订一并关闭。P1／P2已在 main，不是阻塞来源。

## 收尾判断

本轮不触发开发 closeout：只读复评仍有 1 blocker、2 major、2 minor，主体尚未到实施边界；本轮没有创建 source/test改动、commit或 worktree需要集成／删除。报告交回 Spec作者继续修订即是当前边界的完整处置。

