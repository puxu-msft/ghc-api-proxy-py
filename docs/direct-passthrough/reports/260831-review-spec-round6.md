# 直连 Responses 原生透传产品规格独立复评（round 6）

> **落盘位置说明（非正文）**：调用方指定的路径是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260831-review-spec-round6.md`，`Write` 被 worktree isolation guard 拒绝（提示「This subagent's parent bg session hasn't isolated yet」）。我没有自行 `git worktree add`（那是对共享状态的持久操作，未获授权）。按 round5 的既有预案落到 `/tmp`。**请把本文件原样拷贝到指定路径**：`cp /tmp/ghc-review/260831-review-spec-round6.md /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/`。

- report_id：`direct-responses-passthrough-spec-review-round6`
- attempt_id：`260831-review-spec-6`
- reviewed_at：2026-08-31
- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v6）与同目录 `plan.md`（v5）
- 被评快照：`.dev` HEAD `bad7391`，主仓 HEAD `7e96adc`
- 对照基线：`reports/260831-review-spec-round5.md`（needs-fix，blocker 1、major 3）
- 评审性质：只读。未修改 `src/`、`tests/`、`spec.md`、`plan.md`；未派 agent；未调用真实上游；未触碰 4141 服务

## 评审范围

按「逐条完成度」与「系统状态」两问分开走。第一问核 round5 四条的当前状态；第二问抛开 round5 清单，重新对 Spec 的承重条款与 Plan 的可执行性做一遍。

覆盖面：Spec 全文 §1–§12；Plan 全文；判据来源取自 `docs/.human-controlled/`（`message-translation.md`、`client-side-block-delivery.md`、`upstream-retry-and-continuation.md`、`config.example.yaml`）、本地 `openai==3.3.1` 的 `ResponseError.code` 与 `ResponseOutputItem` union、以及主仓 `7e96adc` / `ca777df` 的实际 diff。代码面读了 `pipeline/retry.py` 全文、`pipeline/delivery/stream.py:430-530`、`pipeline/direct_driver/base.py:55-235`、`server/routes/inference.py:370-500`、`tests/int/test_pipeline_app.py` 的直连腿测试群。

执行证据：跑了 `uv run pytest tests/unit/pipeline/delivery/test_sse_assembly.py -q`（50 passed），用于核 Plan §0 关于 P1／P2 的自述。

明确不在范围内：并行编写中的 skeleton 产物、`anthropic-responses-bridge/spec.md` 本体、`error-envelope/spec.md` 本体（只按引用核一致性）、真实上游行为的发生率。

## 总体 verdict

**needs-fix。blocker 1、major 2、minor 6、nit 1。**

**round5 的四条：closed 3、partially-closed 1、not-closed 0。** v6 声称的四项修改（a）（c）（d）逐条核实为真且改到位；（b）只做到一半——`vector_store_timeout` 已归瞬时，但 round5 真正针对的那个「对剩余集合做未经逐项核验的全称」原封不动地留了下来，现在写成「余下 17 个是明确的非瞬时失败」，而 round5 明确拒绝对 `failed_to_download_image` 下这个判断。

**本轮 blocker 是 v6 这次修复自己带进来的。** 新的 final source 表把「末步发什么」从 commit 状态里解耦，方向是对的，但它与上方 partition 表第一格在**时间上不互斥**：第一格的谓词（「replay 有预算、该失败可重试」）在重开之前就能求值，并要求「一个字节都不提交、全部丢弃」；而第二格把「被拒」也算进自己，要求运行 §7.2 去提交那些已经被第一格销毁的完整 group。同一个可达场景（优雅关闭期间收到可重试的 `response.failed`）因此有两个相反的答案，在 `full` 下差别是「整轮内容」对「一条 error」。final source 表本身也不穷尽：它没有「上游终局存在、但它所属的 attempt 已被 replay 判定作废」这一格。

顺着这条线查到一件更要紧的事：**用户亲笔的重试合同里有一句「优雅关闭时报错不再考虑无痕重试」，Spec §5 从头到尾没有记它**，而 §5.2 把 draining 建模成「重开之后的拒绝」，时序恰好与该裁决相反；主仓 driver 侧的门（`direct_driver/base.py:74-82`）已经按该裁决实现成判定之前的拒绝，并在注释里逐字记下了两扇门的这个差异。

另有一处 v1→v5 一路留下来、前五轮都没点到的旧问题：§4／§7 的「安全前缀一就绪即发出」与 §5 的「control events 保持 attempt-local」对同一段字节给两个答案，按前者实施会让直连腿的透明 replay 事实上永不成立。

## 一 · round5 四条逐条完成度

| finding_id | round5 级别 | 状态 | 判据与结论 |
|---|---:|---|---|
| `...round5-01` | blocker | **closed** | `spec.md:227` 第二格已改为「末步的 carrier 由下表的 final source 决定，不由 commit 状态决定」；`spec.md:230-237` 新增 final source 表，四格分别给出逐字提交与 proxy error；`spec.md:243` 收口第三步、`spec.md:129` §5.1 第二行、`spec.md:259` §8 的「预算耗尽而无上游终局」三处口径一致。round5 点名的那个矛盾不再存在。**但这次修复引入了 round6-01，见第二节** |
| `...round5-02` | major | **partially-closed** | `spec.md:143` 已单列 `vector_store_timeout → SERVER_ERROR`，本地 SDK 第 19 行逐字核对为 20 成员 Literal，扣掉三个已列 code 恰余 17，算术无误。**但 round5 建议的另一半没做**：`spec.md:144` 仍是全称——「余下 17 个是明确的非瞬时失败」。round5 原文写的是「`failed_to_download_image` 等是否瞬时仍缺上下文，本报告不猜」，并要求「不要再对剩余集合做未经逐项核验的全称」。映射本身（`None`）保守且正确，错的是理由。见 round6-06 |
| `...round5-03` | major | **closed** | `spec.md:130` 已改为「按 §5.2 的三类结果分别处置」，不再把 draining 枚举成 replacement 失败。Plan 三行逐条核：`plan.md:51` 已含 §5-before-§7.2 gate 与 final source 表；`plan.md:57` 已改成三 code 映射 + `OpenedAttempt`／`AttemptFailed`／`ReopenRefused`；`plan.md:63` 已改成语义判据并显式声明「本文件不复制名单」。v4 旧话全部清除 |
| `...round5-04` | major | **closed** | `spec.md:283` 已把 `Last-Modified` 与 weak `ETag` 移出必剥例子并明确「保留」，`ETag` 拆强弱且 strong 仍须剥离或重算；`spec.md:284` 新增非流式 `Content-Type` 由本代理按实际输出重建，并写明显式 `Content-Type` 会压过 `JSONResponse` 本该生成的 `application/json`；`plan.md:63` 同步 |

状态计数：`closed=3`、`partially_closed=1`、`not_closed=0`。

**残留没修干净的扫描结果**：本轮专门查了前几轮反复出现的形状（正文改了、表格／例子／修订记录留旧说法）。v6 在这一点上是干净的——§12 的 v6 行如实记了四项，没有把旧结论留在正文；Plan 三行全部改写而非叠加。**唯一的同形残留是 §3.1**（见 round6-07）：两处前置已在 `7e96adc` 合入，文首状态行说了，§3.1 正文仍以「必须新增／必须修正」的将来时写着。

## 二 · 本轮发现

### direct-responses-passthrough-spec-review-round6-01

- finding_id：`direct-responses-passthrough-spec-review-round6-01`
- severity：`blocker`
- primary_location：`spec.md:224-237`
- related_locations：`spec.md:118-122`、`spec.md:130`、`spec.md:150-157`；`src/app/pipeline/retry.py:138-143`；`src/app/pipeline/delivery/stream.py:456-473`、`:487`；`src/app/server/routes/inference.py:406-415`
- 标题：partition 第一格的「全部丢弃」在「被拒」可知之前就已求值，且 final source 表没有「终局存在但其 attempt 已作废」这一格

**两张表分别是什么。** `spec.md:224-228` 按 commit 状态三分；`spec.md:232-237` 按 final source 四分，并声明后者与前者正交。方向正确，round5-01 因此关闭。问题在两张表各自的**谓词何时可求值**。

**第一格与第二格在时间上重叠。** 第一格的谓词是「首个原生事件尚未提交，且 replay 有预算、该失败可重试」——这三项在**尝试重开之前**就全部可求值。它的动作是「不运行 §7.2；旧 attempt 的 control、queue、ids、usage 全部丢弃且一个字节都不提交——包括已完成的 group」。第二格的谓词是「replay 不可用／**被拒**／预算耗尽」，其中「被拒」按 §5.2 就是 `ReopenRefused`，而那是**重开之后**才知道的事实。它的动作是「运行」，而运行的第二步（`spec.md:242`）是「按原序提交 control 与所有已完成的安全 group」。

于是优雅关闭期间收到一个可重试的 `response.failed` 时：第一格先命中并销毁全部已完成 group，随后第二格命中并要求提交它们。Spec 没有说这两格谁先求值，也没有说第一格的丢弃是否要等到拿到新流之后。

**这不是纸面推演，现有实现正是这个顺序。** `retry.py:140` 的 `ledger.take(reason)` 在返回 `REPLAY` 时就已经**花掉**了预算；`stream.py:467-468` 拿到 `REPLAY` 之后才 `await replay.reopen(torn)`；`inference.py:410-415` 的 draining 检查在 `_reopen` 内部，返回 `None`。也就是说「判定 replay」与「知道被拒」之间隔着一次完整的往返，Spec 描述的两格就落在这个间隔的两端。`stream.py:487` 的注释还逐字写着现状是「Nothing is flushed first」，而 Spec `spec.md:254` 明令不得沿用现状——这恰好说明 Spec 必须自己把顺序说清楚，没有可以退回去参照的默认值。

**final source 表另有一处不穷尽。** 四行分别是：上游 completed／incomplete；cancelled 或不可重试 code 的 failed／error；**可重试的 failed 但预算耗尽**；没有任何上游终局。`ReopenRefused` 场景既不满足第三行（不是预算耗尽），也不满足第四行（上游终局确实存在，只是所属 attempt 被判定作废）。`AttemptFailed` 同样落空：`spec.md:155` 说「客户端看见 replacement 的失败」，`spec.md:130` 说「若 replacement 的失败本身不可成帧，则写 proxy error」，但 replacement 的失败是一个 HTTP／transport exception，本来就没有原生事件可成帧，所以「可成帧」这一支永远为假还是另有所指，读不出来；它的 error origin 也未定——主仓 `FailureOrigin` 只有 `UPSTREAM_EVENT` 与 `PROXY_REFUSAL` 两个值，而 replacement 的 HTTP 500 两个都不是。

**影响。** `full` 与未触发的 `until-tool-use` 下，这一格的两个答案分别是「整轮已完成内容 + 一条 error」和「只有一条 error」。优雅关闭是本项目 systemd 部署的常规路径，不是边角场景。实现者按任一读法写出来的代码都能声称合规。

**建议。** 两处各补一句，都属 §2.3 的本规格推导，评审共识即可改：

1. 把第一格谓词收紧为「……且重开**已经成功**（§5.2 的 `OpenedAttempt`）」，或等价地在动作里写明「丢弃发生在新流到手之后，在此之前旧 attempt 的队列必须保持可提交」。二者选其一即可，选前者更清楚，因为它让三格重新变成可判定的 partition。
2. final source 表补一行：「上游终局存在，但其 attempt 已被 replay 判定作废（`ReopenRefused`／`AttemptFailed`）→ 按 §8 写 error，origin 按 §5.2（`ReopenRefused` 为 proxy，`AttemptFailed` 为 upstream）；**不得**回头逐字重放那份已作废的终局」——最后这半句 `spec.md:130` 已经有了，把它抬进表里，读者才不必跨节拼。

采纳 round6-02 会顺带消掉这一格里最尖锐的那个实例（draining），但**不能替代本条**：`AttemptFailed` 与「本地前置拒绝」的其余形态仍然落在同一个空格里。

**证据强度：强到可以据此行动。** 依据是被评文档自身两格谓词的可求值时点，加上现有实现三处代码的执行顺序实证。不依赖任何未观测的上游行为。

**承重前提检查。** 前提是「三格 partition 在任一时刻都可判定且互斥」。round5 已证明按 commit 状态分是穷尽互斥的，本条不推翻那一点——推翻的是「第二格的谓词与第一格的谓词在同一时刻都可求值」这个隐含假设。

### direct-responses-passthrough-spec-review-round6-02

- finding_id：`direct-responses-passthrough-spec-review-round6-02`
- severity：`major`
- primary_location：`spec.md:118-122`
- related_locations：`spec.md:150-157`；`docs/.human-controlled/upstream-retry-and-continuation.md`（「特别地，优雅关闭时报错不再考虑无痕重试，可以走下文合成续写机制。」）；`src/app/pipeline/direct_driver/base.py:67-82`；`src/app/server/routes/inference.py:410-415`
- 标题：用户亲笔的「优雅关闭不再考虑无痕重试」没有进入 §5 的 replay 合同，§5.2 采用的时序与之相反

**用户原话在人写文档里，是一手证据。** `upstream-retry-and-continuation.md` 在「无法继续／一般可以继续」两张清单之后单起一段：「特别地，优雅关闭时报错不再考虑无痕重试，可以走下文合成续写机制。」这是对 replay **资格**的裁决，不是对重开结果的裁决。

**Spec 没有记它。** `spec.md:122` 列不得 replay 的原因时写的是「cap 超限、客户端取消、客户端 deadline 等人写文档列为不可继续的原因」——优雅关闭不在其中，全文 grep `drain`／`优雅`／`关闭` 也只在 §5.1／§5.2 出现，且都只作为「重开被拒」的一个例子。于是 Spec 把一条用户裁决降格成了实现细节。

**时序被建反了，而主仓已经按用户裁决实现过一次。** `direct_driver/base.py:74-82` 的 `LedgerBudget.take_for` 先查 draining 再动 ledger，注释（`:75`）逐字写着理由：「Before the ledger, so a shutdown does not also show up as budget exhaustion in whatever reads the counters next……**and the delivery-side replay spends its own attempt before its drain check, so the two doors differ on this.** Refusing first is the honest report of why, not a resource decision.」也就是说：主仓自己知道两扇门时序不同，driver 侧那扇是按用户裁决写的，delivery 侧那扇不是。**Spec §5.2 抄的是后者。**

**这不是把裁决交回用户，而是把已有裁决补记进 Spec。** 按项目规则，「记录一条 Spec 尚不知道的事实」不需要用户再裁；「实现偏离用户裁决时改的是实现」也正好适用于 delivery 侧那扇门。要提醒的边界只有一条：`ReopenRefused` 这个分类本身仍然有用（「本地前置拒绝」的其余形态），**不要因为把 draining 提前就把整个 `ReopenRefused` 删掉**。

**影响。** 直接影响两件事：（一）优雅关闭期间会为一次根本不会发生的 replay 花掉一次预算，这个副作用在直连腿上不可观测但会污染完成行与计数器，正是 `base.py:75` 那条注释在防的东西；（二）它是 round6-01 那个空格最常发生的实例，不补记就等于让 Spec 在一个用户已经表过态的问题上继续保持沉默。

**建议。** §5 的不得 replay 清单加入「进程处于优雅关闭（draining）」并标注出处为用户亲笔；§5.2 的 `ReopenRefused` 行加一句「draining 属于 §5 的 replay 资格判定，**不进入本表**；本表只承载判定为可 replay 之后重开仍未给出新流的情形」。

**证据强度：强到可以据此行动。** 用户原话是一手且逐字可回指；两扇门的时序差异由主仓代码注释自证，不是我推的。

**承重前提检查。** 前提是「人写文档列出的不可继续原因已被 §5 完整吸收」。「优雅关闭」那一段直接证伪。

### direct-responses-passthrough-spec-review-round6-03

- finding_id：`direct-responses-passthrough-spec-review-round6-03`
- severity：`major`
- primary_location：`spec.md:96-102`、`spec.md:193-196`
- related_locations：`spec.md:112-116`、`spec.md:180-182`、`spec.md:239-243`
- 标题：「安全前缀一就绪即发出」与「control events 保持 attempt-local」是同一段字节的两条当前指令

**两条指令。** `spec.md:97` 定义释放条件：「只有从 frontier 到某位置之间、所有已打开的 item 都已 `done` 时，才释放这段连续前缀」。`spec.md:195` 的 `block` 行：「每个安全前缀（§4）一就绪即发出。默认。」而 `spec.md:114` 的 commit 表写的是：`response.created` / `response.in_progress` →「**保持 attempt-local**，随第一批可交付 item 事件一起提交」。

**冲突可达且是常态。** 上游的首帧就是 `response.created`，此时**一个 item 都还没打开**，§4 的释放条件因此**空真**——从 frontier 到该位置之间没有任何未完成的 item。按 §7 的 `block` 行，这个只含 control 的安全前缀「一就绪即发出」。按 §5，它必须被扣住。这不是罕见交错，是每一个请求的第一帧。

**代价是透明 replay 在直连腿上事实上消失。** 一旦 `response.created` 被写出去，按 `spec.md:108` 的定义「客户端已经看到本次 attempt 的原生事件」即为已提交，`spec.md:120` 随即禁止整次 attempt replay。于是 §5、§5.1、§5.2、§7.2 第一格这一整套 replay 合同——四轮评审的主要产出——在 `block`（默认 policy）下永远走不到。

**为什么不是 blocker。** `spec.md:182` 写了「提交时点见 §5」，§5 本身也是无歧义的，所以存在一个明确的裁断方向：§5 赢。这与 round6-01 不同，那一条的两个答案都在 §7.2 内部、没有裁断句。

**建议。** 两处各加一句限定：§4 在释放条件后补「control-only 的安全前缀不构成提交，其提交时点由 §5 规定」；§7 的 `block` 行改为「每个安全前缀（§4）一就绪即发出，**首批仍受 §5 的 control-event 提交时点约束**」。两处都属 §2.3 推导。

**证据强度：强到可以据此行动。** 纯文本自证，不依赖实现或上游。

**承重前提检查。** 前提是「§4／§7 描述的释放与 §5 描述的提交是同一件事的两种说法」。只含 control 的空真前缀直接证伪：两者给出相反动作。

### direct-responses-passthrough-spec-review-round6-04

- finding_id：`direct-responses-passthrough-spec-review-round6-04`
- severity：`minor`
- primary_location：`plan.md:79`
- related_locations：`plan.md:86`；`tests/int/test_pipeline_app.py:2549-2582`；`tests/unit/pipeline/delivery/test_openai_responses_format.py:331`；`tests/unit/protocols/test_responses_anthropic_nonstream.py:259`
- 标题：step 3 说要更新「那两条测试」的断言，实际只有一条直连腿测试断言了会被反转的行为

**核过的事实。** `git show ca777df -- tests/int/test_pipeline_app.py` 只新增了**一个**测试函数 `test_an_output_item_this_assembler_does_not_know_is_refused_not_rendered`（`tests/int/test_pipeline_app.py:2549`），加上一个 SSE 夹具辅助函数，共 57 行。全仓 grep `unknown_output_item` 只命中该文件。`plan.md:86` 的论证段本身也只点名了这一条。

另外两条形近的测试都**不**在直连腿上，接线后应当继续为绿：`test_a_block_kind_this_does_not_know_is_refused_rather_than_emptied` 测的是 `ResponsesFramer` 对未知 `BlockKind` 的拒绝，直连腿换掉 framer 后走不到它；`test_rejects_unknown_output_item_explicitly` 是 Responses 上游 → Anthropic 客户端的非流式翻译腿。

**风险是具体的。** 一个照着「那两条」去凑数的实施者，最可能改的就是上面这两条之一，而它们承载的正是 Spec `spec.md:57` 明令保留的翻译腿 `REJECT` 覆盖。改动不会有冲突也不会报错，只会让翻译腿的保护静默消失。

**建议。** `plan.md:79` 把「那两条测试」改成逐条点名（当前是 `tests/int/test_pipeline_app.py:2549` 一条），并加一句「翻译腿的 `REJECT` 测试**不动**」。顺带把 step 3 会改变字节但不会改变断言的直连腿测试列出来（`/responses` 在 `tests/int/test_pipeline_app.py` 上共 7 个调用点，其中 `:2585`、`:2617`、`:2652` 三条断言的是事件名与「没有 Anthropic 事件名」，透传后仍应成立），这样红了才知道是不是意外。

**证据强度：强到可以据此行动。** 依据是 `git show` 的 diff 与全仓 grep，不是记忆。

### direct-responses-passthrough-spec-review-round6-05

- finding_id：`direct-responses-passthrough-spec-review-round6-05`
- severity：`minor`
- primary_location：`plan.md:76-84`
- related_locations：`plan.md:37`、`plan.md:51`；`spec.md:193-196`；`src/app/pipeline/delivery/stream.py`（`delivery_buffer(chain)` 为两腿共用）
- 标题：step 3 让直连腿上线，但 `full`／`until-tool-use` 的等价物要到 step 6 才有，中间这段的行为没写

**事实。** `plan.md:37` 明写「`BlockBuffer` 今天用 `kind == TOOL_USE` 做 `until-tool-use`……本腿需要各自的等价物：释放判据见 §4」，而 Plan 的 §4（`plan.md:45-51`）对应顺序表的**第 6 步**。第 3 步是接线，第 6 步才有 policy。`delivery_buffer(chain)` 是两腿共用的构造，`client_delivery` 的 policy 是用户可配项。

**于是 step 3 到 step 6 之间，直连腿上配 `full` 或 `until-tool-use` 会发生什么，Plan 没有答案。** 最可能的实现结果是静默退化成 `block`——配置项还在、日志还照旧、行为悄悄换了一种。本项目已经在「缺席读不出来」这个形状上付过代价。

**这不是要求 step 3 必须绿。** 项目规则明确允许中间提交不完整。要求的只是**把这段真空写进 step 3 的定义**，让它是一个被记录的状态而不是一个被发现的状态。

**建议。** 二选一，都可接受：（甲）把 step 3 移到 step 6 之后——step 3 之所以必须是一刀，理由（`plan.md:86`）是「启用透传」与「撤销 direct 的 REJECT」是同一个 observable switch，这个理由与它排在第几位无关；（乙）保持顺序，在 step 3 写明「非默认 policy 在 step 6 之前退化为 `block`，并按 §10 记一条可观测事实说明退化发生了」。我倾向（甲），因为它不需要写一段用完就删的降级代码。

**证据强度：强到可以据此行动。** 依据是 Plan 自身的顺序表与共用构造，不依赖对实现者的猜测。

### direct-responses-passthrough-spec-review-round6-06

- finding_id：`direct-responses-passthrough-spec-review-round6-06`
- severity：`minor`
- primary_location：`spec.md:144`
- related_locations：`.venv/lib/python3.14/site-packages/openai/types/responses/response_error.py:12-32`；`plan.md:57`
- 标题：「余下 17 个是明确的非瞬时失败」仍是未逐项核验的全称，`failed_to_download_image` 是它已知的疑点

**round5 建议的另一半没做。** round5 的原话是「把表中『其余 18 个全非瞬时』收窄为逐项名单或『除明列 retryable code 外保守 None』，不要再对剩余集合做未经逐项核验的全称」，并且在同一条里明确表示对 `failed_to_download_image` 「名称不足以区分永久 URL 错误与瞬时 transport；保持 None」。v6 把 18 改成 17，全称的形式没动。

**逐项看。** 余下 17 个是 `invalid_prompt`、`data_residency_mismatch`、`bio_policy`，加 14 个 image 相关 code。前三个与其中 13 个 image code（格式、尺寸、编码、策略、找不到文件）都名副其实地永久。**`failed_to_download_image` 不是**——下载失败既可能是 404 也可能是一次瞬时网络故障，名字本身不区分。把它称为「明确的非瞬时失败」是一句没有依据的断言。

**映射本身不必改。** `None`（不重试）在缺乏证据时是正确的保守选择，round5 也是这么判的。要改的是理由：一个正确的结论配一个假的理由，下一个人核到理由为假时会连结论一起推翻。这条全称已经生产过一次缺陷（`vector_store_timeout`），它还会再生产。

**建议。** `spec.md:144` 改为「其余 `code`（含未知）→ `None`：**除上表明列的可重试 code 外一律保守不重试**。其中 `invalid_prompt`、`data_residency_mismatch`、`bio_policy` 与各类 image 格式／尺寸／策略错误由名称即可判定为永久；`failed_to_download_image` 是否瞬时**未核**，按保守规则同样落 `None`，取得证据后可单独放宽。」

**证据强度：强到可以据此行动**（SDK Literal 逐字可核、round5 已就该 code 表过态）；至于 `failed_to_download_image` 究竟是不是瞬时，**只是倾向，需要上游样本**——本条不要求现在裁定它，只要求 Spec 不要替它下断言。

### direct-responses-passthrough-spec-review-round6-07

- finding_id：`direct-responses-passthrough-spec-review-round6-07`
- severity：`minor`
- primary_location：`spec.md:86-91`
- related_locations：`spec.md:4`；`plan.md:13-18`；主仓 `7e96adc`
- 标题：§3.1 仍以将来时写着两处已经合入 `main` 的前置

**事实。** `spec.md:88` 写「本承诺**不能**靠现有 writer 兑现，实跑给出两个反例」，随后两条各写「**必须**新增……」「**必须**修正……」。两条都已在 `7e96adc` 落地（`encode_frame(event, data)` 与 frame separator 改为两个连续行尾）。只有文首 `spec.md:4` 的状态行说了这件事。

**为什么值得记。** 这正是前几轮反复出现的形状的同族：一处说了、另一处没改。单读 §3.1 的读者会以为这两件事还没做，而 §3.1 是 §3 全部保真承诺的地基。

**建议。** 两条各加尾注「**已实现（`7e96adc`）**」，要求文本保留——它仍然是规范性要求，只是已被满足。同时把 `spec.md:88` 的「不能靠现有 writer 兑现」改成过去式并注明修复前后的分界。

**证据强度：强。** `git show --stat 7e96adc` 与 `uv run pytest tests/unit/pipeline/delivery/test_sse_assembly.py -q`（50 passed）双向确认。

### direct-responses-passthrough-spec-review-round6-08

- finding_id：`direct-responses-passthrough-spec-review-round6-08`
- severity：`minor`
- primary_location：`spec.md:272-274`
- related_locations：`docs/.human-controlled/client-side-block-delivery.md`「客户端响应头」节；`src/app/pipeline/direct_driver/base.py:161-193`
- 标题：「流式与非流式同一合同」把一条只覆盖流式的用户裁决扩到了非流式，且标注为用户裁决

**归属核对（三问）。** 一手来源：有，`client-side-block-delivery.md` 的「客户端响应头」节逐字可回指。言语行为：是裁决，不是倾向。**范围：盖不住。** 原文是「不等到出现完整块才转发上游响应头给客户端，但也不可能每次上游尝试都能提交响应头给客户端，而是只在第一次 HTTP 200 尝试时转发响应头给客户端。后续重试若 HTTP 报错**只能转化为 SSE error**。」——文档名、所在节、以及「转化为 SSE error」这个补救方式，三重都把定义域钉在流式块级交付上。非流式没有「已经发出去收不回来」这个约束，也没有 SSE 这个补救通道。

`spec.md:276` 已经正确地把「哪些头转发」标为本规格推导；漏标的是**「只取第一次 200 尝试」这条规则向非流式的延伸**，它写在标题里（`spec.md:272`「流式与非流式同一合同」）并紧接着一句「来源已由用户裁决」。

**行为影响当前不可达，所以是 minor 而不是 major。** `direct_driver/base.py:136-193` 的 `run` 在拿到响应头后即返回，body 无论流式还是非流式都在 `inference.py` 里、在 driver 循环之外读取；非流式 body 读取失败不会重回该循环。因此「第一次 200 的头」与「产出 body 的那次 200 的头」在非流式上恒为同一个 attempt，不存在错配。这是一条归属范围问题，不是当前的行为缺陷。

**建议。** `spec.md:272` 的标题保留，但把该延伸移到 `spec.md:276` 那句「以下是本规格的推导」的管辖之下，或就地加一句「用户裁决的定义域是流式块级交付；非流式沿用同一规则是本规格的推导（§2.3）」。

**证据强度：归属部分强到可以据此行动**（一手原文逐字可核，范围三重钉死）；**行为不可达这一判断是强推断**（读了 driver 的 `run` 全部返回路径），但没有构造实验证伪，若将来非流式接入 replay 需要重估。

### direct-responses-passthrough-spec-review-round6-09

- finding_id：`direct-responses-passthrough-spec-review-round6-09`
- severity：`minor`
- primary_location：`plan.md:88-94`
- related_locations：`spec.md:143`、`spec.md:232-237`、`spec.md:283-284`
- 标题：验收清单补到 v5 为止，v6 新增的四处承重点没有各自的可失败判据

**事实。** `plan.md:92` 起头是「**v5 新增**的承重点同样各要一条，它们只在正文出现过」，随后列的六项全是 v5 的。Plan 自身日期已是 2026-08-31（v5）、正文已按 Spec v6 更新（`plan.md:51`、`:57`、`:63` 都引了 v6 的新条款），唯独验收清单没跟。

**v6 新增而清单未覆盖的四处**，每一处都满足 `plan.md:92` 自己给的入选理由（「只在正文出现过」）：

1. **末步 carrier 按 final source**——尤其是「不可重试 code 的 `failed` 逐字交付」与「可重试但预算耗尽的 `failed` 逐字交付」这两格。它们是 round5 那个 blocker 的正解，没有判据就没有任何东西能防止实现退回写 proxy error。
2. **`vector_store_timeout` 可重试**——一个 code 的分类，判据成本极低。
3. **非流式 `Content-Type` 由本代理重建**——反例是上游用 `text/html` 承载可解析 JSON。
4. **weak `ETag` 与 `Last-Modified` 必须保留**——**这一条是反向要求**，也是四条里最容易被静默违反的：语义判据的自然实现方式是「剥离一切像 validator 的头」，而正确行为是留下它们。一条只测「strong `ETag` 被剥」的判据在错误实现上照样绿。

**建议。** `plan.md:92` 的引导句从「v5 新增」改成「历次修订新增」，并把上面四条加进去；第 4 条写成「weak `ETag` 与 `Last-Modified` **仍在**响应头中」这样的正向断言。

**证据强度：强到可以据此行动。** 依据是 Plan 自身条款（`plan.md:90` 的通则 + `:92` 的入选理由）与 Spec v6 的 diff 面。

### direct-responses-passthrough-spec-review-round6-10

- finding_id：`direct-responses-passthrough-spec-review-round6-10`
- severity：`nit`
- primary_location：`spec.md:120`
- related_locations：`docs/.human-controlled/upstream-retry-and-continuation.md`
- 标题：以引号呈现的「用户亲笔的重试合同」是转述，不是原句

`spec.md:120` 写「这与用户亲笔的重试合同一致——「尚未交付完整块可无痕重试；已交付块则不得从头重放」」。前半句在人写文档里的对应原文是「如果还没交付过完整块，直接在代理端无痕重试」，语义相同；**后半句在人写文档里没有对应句子**——那里写的是已交付完整块之后走 MCP 合成续写，并且该机制明确「目前只给 anthropic-messages 客户端请求时使用」。

在本腿上结论是等价的（本腿没有续写通道，`spec.md:259` 已裁定走 SSE error），所以这不是行为缺陷。记它只为一件事：引号 + 「亲笔」会让下一个读者以为能逐字回指，而实际不能。建议去掉引号改为「概括为」，或替换成两句真正的原文。

**证据强度：强**（逐字比对过人写文档全文）；**影响：仅文档可信度，无行为后果。**

## 三 · §11「当前为空」的复核

**当前不名副实**，与 round5 同因不同项。round6-01（final source 表的空格与两格重叠）与 round6-03（control-event 提交时点）都是 Spec 级、影响用户可观察行为的未闭合项，属于 §11 的定义。round6-02 是一条已有用户裁决的补记，不构成新分叉，但在补记之前它同样是 Spec 未答的问题。

修完这三条之后，本轮**没有**发现第四种 commit 状态，也没有发现另一个需要用户裁决的产品分叉——round6 全部十条要么是评审共识可改的推导，要么是把已有用户裁决写进来。届时 §11 可以真正为空。

## 四 · 门禁问题：可否据此开始主体实现（Plan step 3）？

**no。**

**但与 round5 不同，挡住 step 3 的东西不含 blocker，全部是文本级修正，且不必等 round6-01／02。** 分开说清楚：

**step 3 自身边界内、必须先改的三处：**

1. `plan.md:79` 的「那两条测试」改成逐条点名，并写明翻译腿的 `REJECT` 测试不动（round6-04）。这是 step 3 的执行指令本身含有的事实错误，照做会损伤 Spec §2.4 明令保留的覆盖。
2. step 3 的定义补上 `full`／`until-tool-use` 在 step 6 之前的行为，或把 step 3 移到 step 6 之后（round6-05）。
3. `spec.md:195` 的 `block` 行与 `spec.md:97` 各加一句提交时点限定（round6-03）。这一条严格说属于 step 5 的领域，但接线一旦生效，「control 前缀何时落到客户端」就是 step 3 的产出，先写清比事后回改便宜。

**不挡 step 3、但挡 step 5／step 6 的：** round6-01 与 round6-02。它们全部落在 replay 与 ending 的语义上，step 3 的接线、撤销与断言更新不消费这两条。**在它们闭合之前，step 5（replay 合同）与 step 6（policy × ending）不得开工。**

**round5 对 step 2 骨架的并行开工授权在本轮继续成立**，边界不变；本轮没有新发现推翻「完整 group 按原 event／data 原序携带」这一不变量。

## 五 · Plan v5 自身的可执行性

**步骤边界。** 大体互不重叠，但有两处需要修：

- **step 2 与 step 4 都持有 commit frontier。** `plan.md:33` 把「attempt 内全局事件队列 + 单调 commit frontier」写在 §2「交付单元与队列」里，而 §2 属于 step 2 的骨架；顺序表的 step 4 又叫「commit frontier 与交错」。round5 授权 step 2 做「complete-group tracking、safe-prefix ordering」，那已经是 frontier 的全部纯计算部分。建议把 step 4 明确改名为「交错场景与 §5 的提交语义接线」，让 step 2 只拥有纯分组、step 4 拥有「什么算已提交」。这不是矛盾，是边界含混。
- **step 3 与 step 6 之间的 policy 真空**，见 round6-05。

**验收标准的可证伪性。** `plan.md:90` 的通则（「Spec 每一条规范性要求各自需要一条可失败的判据」）与 `plan.md:94`（「判据必须在实现之前独立推导」）都是对的，且后者正是本项目付过代价的那条。清单里已列的十余项都是可证伪的具体行为，不是「工作正常」这类不可失败的措辞。**缺口只有一个**：v6 新增的四处没进清单（round6-09），其中 weak validator 的「保留」是反向判据，最容易被静默违反。

**有没有哪一步在实施前就已被 Spec 推翻。** 没有。round5 点名的 v4 三条旧话（`plan.md:51`／`:57`／`:63`）已全部改写为 v6 口径，我逐行核过，不是叠加而是替换。Plan 与 Spec 之间目前没有第二个当前指令。

**一处 Plan 未提、但会在 step 8 触发的测试变更：** `tests/int/test_pipeline_app.py:2788` 的 `test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it` 断言直连腿的完成行**不**报告 `reason(` / `function_call(`，而 §10 要求直连腿记录原生 item 计数与需要客户端行动的 tool 名。该测试自己的注释写着「Asserted so that giving it a reader is a deliberate change to this test rather than a silent one」——正是为这一刻准备的。建议在 step 8 里点名它，别让实施者把一次预期变更读成回归。

**Plan §0 的自述已核。** `plan.md:18` 声称 P1／P2 都做过变异验证。我没有做变异（那要改 `src/`，超出只读边界），但读了 `7e96adc` 加的两个参数化测试：帧分隔测试断言的是**事件名的序对**而非条数，commit 信息记录了「第一次修复尝试产出两个名字都为空的帧，只数条数会放行」——这条判据有分辨力；编码器测试的多行用例在「退回单行 `data:`」的变异下必红，因为回读会丢掉首行之后的一切。跑了该文件，50 passed。**自述可信。**

## 六 · 考虑过但否决的候选发现

1. **「三格 commit partition 漏了第四种状态」——否决。** round5 已证穷尽互斥，本轮没有新证据推翻。round6-01 攻击的是谓词的**求值时点**，不是格数；补一行 final source 不等于加一个 commit 状态。
2. **「final source 表应该按 policy 再分一层」——否决。** carrier 与 policy 正交：policy 决定**何时**收口与**发多少**，final source 决定**末步是谁的字**。再分一层只会重造 v4 那种互斥表。
3. **「`response.completed` 到达那一格里仍可能需要 replay」——否决。** `spec.md:234` 的判断成立：成功终局在手时没有可重试的失败。
4. **「§7.2 收口三步的第 2 步在 `ReopenRefused` 时是空操作，所以两格重叠无害」——否决，且这正是问题所在。** 它是不是空操作，取决于第一格的丢弃有没有先执行——而那恰恰是 Spec 没说的那件事。用「反正没东西可提交」来消解冲突，等于把两个读法中的一个偷偷选定。
5. **「`rate_limit_exceeded` 引用既有 rate-limit 处置是把决定推给别处」——否决。** round5 已判定不是，本轮复核同意：语义映射（与 429 同类、不得普通即时重试、仍受 request-global budget）已在 Spec 定死，退避参数与限流状态机复用另一个 authority 优于复制。
6. **「用户裁决『最后一次尝试是限流重试，返回 429 + Retry-After』与本腿冲突」——否决。** 那条讲的是上游 HTTP 429，发生在 200 之前，走的是非流式／pre-200 路径；本腿 §5.2 处理的是流中的原生 `rate_limit_exceeded` **事件**，此时 200 已发出，用户自己在 `client-side-block-delivery.md` 里已明确接受「只能转化为 SSE error」。且 v6 的 final source 表对这一格给的答案（预算耗尽则逐字提交上游那条 `failed`）比写 proxy error 更贴近原生合同。
7. **「§6.2 不做 id 修复，与将要替换的 copilot-api-js（默认开 `rewrite-out:responses-fix-stream-ids`）行为不一致，应记为切换风险」——否决为发现，保留为提醒。** `spec.md:174-176` 已经把范围限定说清楚（SDK 3.3.1 按 `output_index` 累积、其他客户端不外推），并留了显式 reshape 合同的出口。这是一个有依据的产品选择，不是缺陷。**但它确实是与现役服务的可观察差异**，切换前值得单独实测一次 Claude Code 的解析行为——那属于 cutover 准备，不属于本 Spec。
8. **「P1 的验收是与本仓自身 parser 的往返，不是对 SSE 规范的字节断言」——考虑后不报。** 观察成立：`test_an_encoded_frame_reads_back_as_what_went_in` 的 oracle 是 `parse_frame`，编码器与解析器若共享同一个错误约定，往返仍会绿。但 `7e96adc` 的 commit 信息记录了对原始字节的实测，且「退回单行 `data:`」的变异会让往返失败（`parse_frame` 会跳过裸行），分辨力实际存在。残余风险低于报一条的成本。
9. **「§9.1 的『其余一律转发』会把 `Set-Cookie` 之类转给客户端」——否决。** 按用户既有安全立场（没有具体危害就不加防护，且转发对象是发起请求的客户端本人），`spec.md:288` 已经论证过场景与 cassette allowlist 相反。构造不出本项目语境下的受保护资产与危害，不报。
10. **「非流式 `Content-Length` 也会因重新序列化而失效，§9.1 只在流式语境下给了理由」——考虑后不报。** `spec.md:279` 的要求本身是无条件的（「必须由本代理重建：`Content-Length`」），只是括号里的理由写成了流式的。行为无歧义，属措辞。若采纳 round6-07 顺手改一下括号即可。
11. **「`inference.py:408` 的注释指向 `deferred.md` §5，而该条的仍开放部分讲的是 clean-EOF 细化的代价，不是 drain 门」——查证属实但不报。** 那是主仓代码注释里的一个陈旧指针，不在本次评审的被检对象（spec.md／plan.md）范围内，且不影响 Spec 的任何结论。**记在这里以免丢**：谁下次动 `_reopen` 那段注释，顺手把 §5 改成正确的条目号。
12. **「§7.1 说判据『不是 item 的 type』，但多数 item 事实上就是按 type 判的」——否决。** 上下文（`spec.md:208` 的 `tool_search_call` 相反答案）已经把这句限定成「type 单独不足」，不是「type 无关」。`plan.md:49` 的「表是判据的当前编码，不是判据本身」也接住了。核过 SDK：`ResponseToolSearchCall.execution` 是必填 `Literal["server","client"]`，`ResponseFunctionShellToolCall.environment` 是 `Optional[Union[ResponseLocalEnvironment, ResponseContainerReference, None]]`——后者可为 `None`，此时按 `spec.md:212` 的未知规则保守释放，链路闭合。
13. **「`ResponseOutputItem` 的 28 成员数字过期了」——否决。** 本地 SDK 逐个数为 28，与 `spec.md:26` 相符。
14. **「§12 的 v6 行『至少装着三种来源，其中三种手里有上游自己的终局』读起来自相矛盾」——降级为不报。** 第二格实际装着四类来源，其中三类有原生终局。措辞压缩得别扭但不假，且修订记录是时点叙述，不是当前指令。
15. **「§10 的可观测清单太薄，没规定字段与载体」——否决。** `spec.md:296` 已经给了「至少要记录」的下界与「无法分类必须记 unknown、不得伪装成 absent」的硬约束，具体载体按 Spec／Plan 分工归 `plan.md:65-69`。这是分层正确，不是缺口。
16. **「Spec 里仍留着 `encode_frame`、`JSONResponse`、`hand_back_block()` 等实现符号，应搬进 Plan」——本轮不报，沿用 round5 的处置。** round5 已建议在行为收口后做一次不改变 normative semantics 的瘦身；现在仍有 blocker，大搬文字会混入语义改动。**这条不是新发现，是 round5 的一条未采纳建议仍然挂着**，记在这里以免被读成已闭合。

以上是本轮实际考虑并排除或限定的线索。没有把未观测的上游发生率、未知客户端的解析行为、或未来的 SDK 变更猜成 severity finding。

## 七 · 搜索面、执行证据与限制

### 判据来源（独立于被检对象）

- `docs/.human-controlled/message-translation.md`（直连尽可能原样转发）、`client-side-block-delivery.md`（客户端响应头）、`upstream-retry-and-continuation.md`（可继续／不可继续清单、优雅关闭、429、MCP 续写的适用范围）、`config.example.yaml:391-393`（`buffer_cap_bytes` 定义）——**四处均逐字比对过，不是靠记忆**。
- `.dev/docs/error-envelope/spec.md:37`（用户 2026-08-23 原话「直连路径一定用原生的，即使我们未知，也能传递」）——逐字命中。
- 本地 `openai==3.3.1`：`response_error.py`（20 成员 `Literal`，逐个读过）、`response_output_item.py`（28 成员 union，逐个数过）、`response_tool_search_call.py`、`response_function_shell_tool_call.py`。
- 前五轮报告（作为已核事实的来源，不作为判据的替代）。

### 被评面与代码面

- `spec.md` v6 全文 318 行、`plan.md` v5 全文 95 行。
- `src/app/pipeline/retry.py` 全文；`src/app/pipeline/delivery/stream.py:430-530`；`src/app/pipeline/direct_driver/base.py:55-235`；`src/app/server/routes/inference.py:370-500`。
- `git show --stat` + 完整 diff：`7e96adc`、`ca777df`。
- `tests/int/test_pipeline_app.py` 的 `/responses` 调用点（7 处）与其中 `:2549`、`:2585`、`:2766`、`:2788`、`:4041` 五个函数的正文。

### 执行证据

- `uv run pytest tests/unit/pipeline/delivery/test_sse_assembly.py -q` → **50 passed**。用途仅限核 Plan §0 的自述，不作为 Spec 合规证据。
- 全仓 `rg` 若干次：`unknown_output_item`、`draining|_reopen|ReopenRefused`、`drain|优雅|关闭|shutdown|续写|429|限流`（对 spec.md／plan.md）、`"/responses"`（对 tests/）。

### 限制

- **未做变异实验。** 变异需要改 `src/`，超出本次只读边界。因此本报告对 P1／P2 那个绿的分辨力判断，依据是读测试断言的形状 + commit 信息里记录的实测，属**强推断而非我自己的一手执行**。
- **未调用真实上游。** 原生 failure code 的实际发生率、Copilot 是否真会发 `failed_to_download_image`，仍 unknown；round6-06 因此只要求 Spec 别下断言，不要求现在分类。
- **§2.1 的用户 8/30 原话「协议允许，凭什么拒绝？」我无法访问原始会话独立回指。** 它与派发说明中调用方的复述一致，本报告按「与调用方复述一致」采纳，不按「已独立验证」采纳。§2.2、§8、§9.1 的三处用户归属则是逐字可核的，已核。
- 本轮未读并行 skeleton 的 WIP 产物，对 step 2 的判断沿用 round5 的边界。
- **指定的报告路径写不进去**（worktree isolation guard），已按 round5 预案落到 `/tmp/ghc-review/260831-review-spec-round6.md`，需调用方搬运。

## 八 · 严重度汇总

- blocker：1（`round6-01`）
- major：2（`round6-02`、`round6-03`）
- minor：6（`round6-04`、`round6-05`、`round6-06`、`round6-07`、`round6-08`、`round6-09`）
- nit：1（`round6-10`）
- finding_total：10

round5 处置状态：`closed=3`、`partially_closed=1`、`not_closed=0`。

## 九 · 收尾判断

本轮不触发开发 closeout：评审完成，但 Spec 仍有 1 blocker，主体边界未到；本轮没有 source／test 改动、没有提交、没有 worktree 处置，唯一交付物是本报告。采纳与修改由调用方执行。
