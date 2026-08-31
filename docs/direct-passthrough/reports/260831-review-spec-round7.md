# 直连 Responses 原生透传产品规格独立复评（round 7）

> **落盘位置说明（非正文）**：调用方指定路径是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260831-review-spec-round7.md`。按调用方预案先落 `/tmp`，请搬运：
>
> `cp /tmp/ghc-review-r7/260831-review-spec-round7.md /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/`

- report_id：`direct-responses-passthrough-spec-review-round7`
- attempt_id：`260831-review-spec-7`
- reviewed_at：2026-08-31
- 被评对象：`.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v7）与同目录 `plan.md`（v6）
- 被评快照：`.dev` HEAD `b8364a2`、主仓 HEAD `7e96adc`、骨架 worktree HEAD `45f538d`——**三者均为调用方给出，本轮无法用 git 独立核验**（见「限制」）
- 对照基线：[`reports/260831-review-spec-round6.md`](260831-review-spec-round6.md)（blocker 1、major 2、minor 6、nit 1）与 [`reports/260831-review-skeleton.md`](260831-review-skeleton.md)（major 4、minor 6、nit 1）
- 评审性质：只读。未修改 `src/`、`tests/`、`spec.md`、`plan.md`；未派 agent；未调用真实上游；未触碰 4141 服务

## 评审范围

按 `as-reviewer` 的两问分开走：第一问核 round6 十条与 skeleton 十一条的逐条完成度；第二问**抛开两份清单**，重新对 Spec 的承重条款、Plan 的可执行性、以及 Spec 与跨腿合同、用户亲笔文档之间的一致性做一遍。

**在范围内**：`spec.md` 全文 345 行、`plan.md` 全文 118 行；判据来源取自 `docs/.human-controlled/` 的 `upstream-retry-and-continuation.md`、`client-side-block-delivery.md`、`message-format-reshape.md`（三份逐字读全文）、`.dev/docs/error-envelope/spec.md` 的 §1–§3.5；代码面读了 `src/app/pipeline/delivery/sse_source.py` 全文、`src/app/pipeline/retry.py` 全文、`src/app/pipeline/delivery/stream.py:420-539`、`src/app/pipeline/direct_driver/base.py:40-159`、`src/app/server/routes/inference.py:370-499`、骨架 worktree 的 `openai_responses_passthrough.py`（208 行）与 `test_responses_passthrough.py`（303 行）全文、`tests/int/test_pipeline_app.py:2540-2689`、以及并行 worktree `260831-sse-line-endings` 的 `sse_source.py:1-70`。

**明确不在范围内**：`anthropic-responses-bridge/spec.md` 与 `hosted-web-search-spec.md` 本体（只按引用核一致性）；`ResponsesAssembler` 翻译腿；`delivery_policy` 的构造细节；真实上游行为的发生率；`260831-sse-line-endings` 那一刀本身的正确性（只用来判断 P3 的当前状态）。

## 总体 verdict

**needs-fix。blocker 1、major 3、minor 6、nit 4（finding_total 14）。**

**round6 十条：closed 10、partially-closed 0、not-closed 0。skeleton 十一条：closed 11、partially-closed 0、not-closed 0。** 逐条判据见第一节。这是六轮以来第一次两份清单全关，v7／plan v6 的自述在这一点上可信。

**但「连着两轮，新 blocker 都是上一轮修复自己带进来的」这条规律，本轮以另一种形态继续成立。** 调用方要我优先重审的那一片（§7.2 partition ＋ final source）本身修对了：第一格补上「且重开已经成功」之后，三格在任一时刻都可判定，我逐个场景走过，没有找到新的重叠或缺口。**没修干净的是同一节里的第二张表**——`spec.md:271` 的 policy × ending 表第一行仍写着收紧前的谓词「仍可 funded replay 的 tear／EOF」，配的仍是那个破坏性动作「整次 attempt 无提交丢弃」，而 `spec.md:131` 的丢弃句同样没有时点。一个从「每个 ending 该怎么办」这一侧读起的实施者，读到的正是修复前的那份指令（round7-03）。

**本轮的 blocker 不在那一片，而在 §9.1，且它是前六轮都没查的一个面。** §9.1 逐字写着「哪些头转发，用户未裁决，以下是本规格的推导」——而 `docs/.human-controlled/message-format-reshape.md:51-57` 有一份**用户亲笔的直连路径响应头黑名单**，`error-envelope/spec.md:73` 已经把那份名单套用到直连腿，本规格 §2.4 又声明 error envelope 这类跨腿合同「仍然适用」。三者合起来，§9.1 的「其余一律转发」与用户名单在 `Date`／`Cache-Control`／`Set-Cookie` 三个头上给出**相反**的当前指令，而 Spec 用一句「用户未裁决」把这个检查关掉了（round7-01）。

另有一处 v1→v7 一路留下、七轮都没点到的产品缺口：**「无法判定属于哪个 item」的事件在 ending 处没有归宿**。§4 说保守持有到 terminal，§7.2 的收口三步只有「未闭合 item 的 suffix」与「control ＋ 已完成 group」两类，它两类都不是；骨架已经替 Spec 裁定为丢弃（`unfinished` 的 docstring 逐字写着 "The tail that no ending may deliver"），而丢弃恰好是与 §2.1 用户裁决张力最大的那个答案（round7-04）。

---

## 一 · round6 十条逐条完成度

| finding_id | round6 级别 | 状态 | 判据 |
|---|---:|---|---|
| `round6-01` | blocker | **closed** | `spec.md:247` 第一格已补「且重开已经成功（§5.2 的 `OpenedAttempt`）」；`spec.md:260` final source 表已补第四行「上游终局存在，但其 attempt 已被 replay 判定作废」。三格在「重开结果已知」这个时点上重新互斥，我按 `AttemptFailed` 递归、`ReopenRefused`、预算耗尽三条路径各走了一遍，未再找到同时命中两格的场景。`spec.md:251` 引的三处代码实证我逐行核过并全部成立：`retry.py:140` 确是 `ledger.take(reason)`、`stream.py:467-468` 确是拿到 `REPLAY` 之后才 `await replay.reopen(torn)`、`inference.py:410-415` 的 draining 检查确在 `_reopen` 内部。**但同一节第二张表未同步，见 round7-03** |
| `round6-02` | major | **closed** | `spec.md:139` 已把 draining 写进 §5 的不得 replay 清单并标注出处为用户亲笔；`spec.md:149` §5.1 第三行、`spec.md:177` §5.2 表后一段都改成「不进本表／根本到不了这里」。用户原话我逐字比对过（`upstream-retry-and-continuation.md:22`）。**「资格判定、发生在重开之前」这个读法成立**：用户写的是「不再**考虑**无痕重试」，而「试了被拒」在语义上属于已经考虑过；主仓 `direct_driver/base.py:74-82` 也是先查 draining 再动 ledger，`:75` 的注释逐字记着两扇门的差异。归属上有一处措辞可再精确，见 round7 否决清单第 3 条 |
| `round6-03` | major | **closed** | `spec.md:109` 已补「只含 control 事件的安全前缀不构成「提交」」，`spec.md:215` §7 的 `block` 行已补「首批仍受 §5 的 control-event 提交时点约束」。round6 点名的那两条当前指令不再并存。**但补的这句自身给出两种读法，且已有读者取了另一读，见 round7-02** |
| `round6-04` | minor | **closed** | `plan.md:96-101` 已逐条点名：`tests/int/test_pipeline_app.py:2549` 一条；两条翻译腿测试列为「一律不动」；`:2585`／`:2617`／`:2652` 列为「会改变字节但不应改变断言」。**行号我逐个 Read 核过**：`:2549` 是 `test_an_output_item_this_assembler_does_not_know_is_refused_not_rendered`、`:2585` 是 `test_a_direct_responses_stream_is_answered_in_responses_events`、`:2617` 是 `test_a_direct_responses_client_declares_hosted_web_search_for_itself`、`:2652` 是 `test_a_direct_responses_client_survives_an_upstream_that_really_searched`，四处全部对得上 |
| `round6-05` | minor | **closed** | 采纳了 round6 建议的（甲）：接线从第 3 位移到第 7 位，理由记在 `plan.md:94`，并显式声明「这不是把接线拆开——它仍然是一刀，只是这一刀落在 policy 之后」。**决定成立，但记录只权衡了一侧，见 round7-10** |
| `round6-06` | minor | **closed** | `spec.md:163` 已改为「除上表明列的可重试 code 外一律保守不重试」，`failed_to_download_image` 单列为「是否瞬时未核……取得证据后可单独放宽」。全称消失，映射未变 |
| `round6-07` | minor | **closed** | `spec.md:88` 已改为过去式并注明「两者都已在主仓 `7e96adc` 修复。条款保留」，两条各带「**已实现（`7e96adc`）**」；第三条标「**未实现**」。与文首 `spec.md:4` 和 `plan.md:13-18` 三处口径一致 |
| `round6-08` | minor | **closed** | `spec.md:300` 新增整段限定，明确「该裁决的定义域是流式块级交付；把同一规则延伸到非流式是本规格的推导（§2.3）」，并保留了行为当前无差异的论证与「将来非流式接入 replay 时须重估」的出口 |
| `round6-09` | minor | **closed** | `plan.md:107` 引导句已从「v5 新增」改为「历次修订新增」，v6 四项与 v7 五项都补齐，weak `ETag`／`Last-Modified` 写成了正向断言。**v7 那一组仍缺一条，见 round7-09** |
| `round6-10` | nit | **closed** | `spec.md:135` 已改为「上面那句是概括，不是原文」，并写明后半句在人写文档里没有对应句子、本腿结论仍等价的理由 |

状态计数：`closed=10`、`partially_closed=0`、`not_closed=0`。

## 二 · skeleton 十一条逐条完成度

被检对象是骨架 worktree 当前状态（调用方给出 HEAD `45f538d`；我无法用 git 核验该哈希，判据是文件当前内容）。

| finding_id | 级别 | 状态 | 判据 |
|---|---:|---|---|
| `skeleton-01` | major | **closed** | `openai_responses_passthrough.py:150-162` 新增回退循环：算出尾部所有 int item，找到前缀里最早属于其一的事件位置，`cut` 退到那里，循环到稳定。与 `spec.md:105` 的定案逐字对应。两条新测试钉住它（`:114` 的基本形与 `:132` 的「一次回退不够」），后者正是回退必须迭代的那个反例。**逻辑我按 Spec 走过四个序列**（含 v7 举的 `created → added(0) → added(1) → delta(1) → done(0)`），未找到反例；终止性成立（`cut` 严格递减） |
| `skeleton-02` | major | **closed** | 新增 `Attribution` StrEnum（`:19-28`），`_item_of` 返回 `int | Attribution` 三态，`_is_barrier`（`:127-134`）把 `UNATTRIBUTED` 判为屏障，`unfinished`（`:175-180`）把它一并暴露。三条测试分别钉「持有而非释放」「阻塞其后前缀」「进入 ending 要丢的尾巴」。**但这第三条正是 Spec 未裁定的那件事，见 round7-04** |
| `skeleton-03` | major | **closed** | 类 docstring（`:100`）改为「**One per attempt, not one per request.**」并写明「There is deliberately no `reset`」；`test_a_second_attempt_needs_a_second_assembler`（`:251`）把这个生命周期钉成断言而不是注释 |
| `skeleton-04` | major | **closed** | `:119` 的注释已改为「Defensive……Whether upstream actually sends that shape is an open question — `hosted-web-search-spec.md` §12 P7」，并把「on record」还给了参考项目自己的实现缺陷；测试 docstring（`:180-186`）同样改写，且把 P7 的原文与三份 cassette 的核对一并写下 |
| `skeleton-05` | minor | **closed** | `response.queued` 已进 `CONTROL_EVENTS`（`:39`）；`:31-35` 的注释重写，逐条说明这张名单只区分「信封 vs 其他」、以及 `response.cancelled` 留下的理由（SDK 无该类型≠上游不发）。`test_queued_is_envelope_and_travels_with_its_prefix`（`:240`）钉住 |
| `skeleton-06` | minor | **closed** | `_closed` 的注释（`:107`）已改成它真实的作用（「一个已关闭的 index 不被后来的事件重开」），并写明单 attempt 内不发生、跨 attempt 才发生，因此类是 per-attempt 的；孤立 `done` 的防御理由移到了它真正所在的分支（`:119`） |
| `skeleton-07` | minor | **closed** | docstring（`:199`）改为「Holds no **renumbering** state」，`written` 字段已整个删除，并写明理由（「a bare tally with no consumer would be this slice deciding §10's carrier for it」）——比原建议更彻底，且与 Spec §10 的分工一致 |
| `skeleton-08` | minor | **closed** | 新增单一定义 `_event_bytes`（`:52-59`），`RawEventBatch.size_bytes` 与 `held_bytes` 都调用它，1.04x 的实测口径写进了 docstring。`size_bytes` 仍无调用者，但已不再是第二份实现，原发现的实质（同一事实两处各写一遍）消失 |
| `skeleton-09` | minor | **closed** | `:115-116` 已改为算一次存局部变量 |
| `skeleton-10` | minor | **closed**（Spec 侧） | `spec.md:92-94` 新增 §3.1 第三条，把它写成规范性要求（比原建议的「补进不承诺清单」更强），并逐字保留了「机制已实跑证实、触发未证实」的权重界定。代码侧 P3 在 `main` 上仍未实现——**但并行 worktree `260831-sse-line-endings` 已经实现**（`_LINE_ENDING = re.compile(r"\r\n|\r|\n")`，`parse_frame` 改用 `re.split`，模块 docstring 里那句被证伪的「`splitlines()` 一直handled」也改了）。见「交接事项」 |
| `skeleton-11` | nit | **closed**（测试侧） | `test_responses_passthrough.py:95` 已改为「The three Responses-stream cassettes in this repository」。**Spec 侧的同形残留仍在，见 round7-11** |

状态计数：`closed=11`、`partially_closed=0`、`not_closed=0`。

## 三 · 语义槽扫描（每个事实是否只剩一处当前指令）

调用方点名要做的一次扫描。我把 Spec 里会被实施者当作指令读的事实逐个列出来，查它的权威处与全部复述处。

| 事实 | 权威处 | 复述处 | 判定 |
|---|---|---|---|
| 什么算「已提交」 | §5 提交表（`spec.md:123-129`） | §4:109 的说明段、§7 `block` 行（`:215`）、§7.2 三格（`:247-249`）、§5.1（`:147-149`） | **有问题**：§4:109 的第三句给出与 §5 表不同的读法 → round7-02 |
| funded replay 时旧 attempt 的去向 | §7.2 partition 第一格（`:247`，v7 已收紧） | §5:131 的丢弃句、§7.2 ending 表第一行（`:271`） | **有问题**：两处复述都是收紧前的谓词／无时点 → round7-03 |
| 未闭合 item 尾巴的丢弃 | §3（`:65`） | §7.2 收口第 1 步（`:266`）、骨架 `unfinished` docstring | 一致 |
| 无法归属事件的处置 | §4（`:113`，只说到 terminal 为止） | §7.2 收口三步（**未出现**）、骨架 `unfinished` docstring（已裁定为丢弃） | **有问题**：Spec 无终局指令，代码已代裁 → round7-04 |
| draining 不得 replay | §5:139（用户亲笔） | §5.1 第三行、§5.2:177、§7.2:251 | 三处一致；§5.2:169 的历史论据陈旧 → round7-06 |
| final source 决定末步 carrier | §7.2 final source 表（`:255-261`） | §7.2 收口第 3 步、`plan.md:54` | 一致（plan 只引不抄） |
| native failure code → RetryReason | §5.2 表（`:158-163`） | `plan.md:60` **逐字转抄** | 今天准确，但与同文件 §5.1「本文件不复制名单」的纪律不一致 → round7-14 |
| 哪些响应头转发 | §9.1（`:302-312`，自称本规格推导） | `plan.md:66`（只引不抄） | **有问题**：用户亲笔名单与 error-envelope 已各有一份当前指令 → round7-01 |
| `ReopenRefused`／`AttemptFailed` 的 origin | §5.2 表（`:174-175`，只说「携带它自己的 origin」） | §7.2 新行（`:260`）声称「origin 依 §5.2」 | **有问题**：被引处并未给出取值 → round7-07 |
| §3.1 三处缺陷的实现状态 | `plan.md:13-18` | `spec.md:4`、`spec.md:88-94` | 三处一致（对 `main` 而言） |
| cassette 计数 | 无单一权威 | §4:117「三份」、§5.2:165「五份」 | **有问题**：同一文档两个数、未加限定 → round7-11 |

---

## 四 · 本轮发现

### blocker

#### `direct-responses-passthrough-spec-review-round7-01`

- finding_id：`direct-responses-passthrough-spec-review-round7-01`
- severity：`blocker`
- primary_location：`spec.md:302`（「哪些头转发，用户未裁决，以下是本规格的推导」）
- related_locations：`spec.md:312`（「其余一律转发」）、`spec.md:314`（cassette allowlist 那条注）、`spec.md:59`（§2.4「跨腿合同（error envelope、keepalive）仍然适用」）；`docs/.human-controlled/message-format-reshape.md:51-57`；`.dev/docs/error-envelope/spec.md:73`
- 标题：§9.1 把一片用户已经写过名单、且已被跨腿合同套用到本腿的区域标成「用户未裁决」，推导出的规则与那份名单在三个头上相反

**用户亲笔名单存在，且逐字可回指。** `message-format-reshape.md` 的「客户端返回 Anthropic Messages」一节（`:51-57`）写着：

> 直连路径的黑名单有：
> - `Connection` `Keep-Alive` `Proxy-Connection` `Hop-By-Hop`
> - `Date` `Cache-Control` `Set-Cookie`
> - `Content-Length` `Content-Encoding` `Transfer-Encoding`

这是用户自己写的文件（`docs/.human-controlled/`），三问全过：一手来源有、言语行为是规定而非倾向、**范围**是「直连路径的响应头」。唯一的范围疑点是节标题「客户端返回 Anthropic Messages」——本腿的客户端收到的是 Responses，不是 Anthropic Messages。

**但这个疑点已经被另一份 Spec 处理过，而且是朝相反方向处理的。** `error-envelope/spec.md:73` 逐字写着：「**响应头**：沿用 `message-format-reshape.md`「客户端返回 Anthropic Messages」一节的**直连黑名单**。该节原文不区分成功与错误，本 Spec 因此不区分。」而 error-envelope 的路径判据（其 §2 的表，`:58`）键在 `Route.translation_required is False`——**恰好就是本规格 §5 定义的定义域**，不是键在 inbound 是不是 Anthropic。也就是说：error-envelope 已经把用户那份名单套用到本腿，而本规格 `spec.md:59` 又声明「跨腿合同（error envelope、keepalive）仍然适用」。

**于是同一条腿的响应头上有三份当前指令，两两不同：**

| 头 | 用户名单（经 error-envelope 套用） | 本规格 §9.1 |
|---|---|---|
| `Date` | 剥离 | 「其余一律转发」→ 转发 |
| `Cache-Control` | 剥离 | 转发 |
| `Set-Cookie` | 剥离 | 转发 |
| `Connection` 一族、`Content-Length`／`Content-Encoding`／`Transfer-Encoding` | 剥离 | 剥离（一致） |

**影响。** 三层，逐层都实在：

1. **行为**。§9.1 是 plan step 8 要照着实施的那份文本，实施出来的直连腿会把 `Set-Cookie`／`Date`／`Cache-Control` 转给客户端，而同一条腿上的**错误**响应按 error-envelope 会剥掉它们——同一个客户端在同一条腿上，成功与失败拿到的头集合不同，且没有任何一份文档说过这是有意的。
2. **权威**。「用户未裁决」这句话的效果，是**永久关闭一个用户已经表过态的问题**。这正是 `as-reviewer` 三条必查面里点名的那类错标，本仓已有三例，全部靠异源复核发现。round6 的否决清单第 9 条考虑过 `Set-Cookie` 并以 threat model 为由否决——那个论证本身没错，错的是它没有先问「用户有没有已经写过一份名单」。
3. **可读性**。§9.1 的语义判据（「验证或描述上游确切字节而本代理未重新计算的字段一律剥离」）是本规格四轮打磨出来的好东西，比一份名单更抗漏。**本条不要求废掉它**——要求的是它必须在用户名单之上运行，而不是在「用户未裁决」的前提上运行。

**建议。** 这一条是本轮**唯一必须上交用户**的：名单的定义域（「客户端返回 Anthropic Messages」这个节标题是否覆盖 Responses 客户端）只有用户能裁。在拿到裁决之前，Spec 该做的三件事都不需要用户点头：

1. `spec.md:302` 那句「用户未裁决」改为事实陈述：用户在 `message-format-reshape.md:51-57` 写过一份直连响应头黑名单，节标题的定义域是 Anthropic 客户端，`error-envelope/spec.md:73` 已按 `translation_required` 把它套用到本腿；本规格与它在 `Date`／`Cache-Control`／`Set-Cookie` 上不一致，**待用户裁定定义域**。
2. 在裁定之前，§9.1 的「其余一律转发」明确写上「**除用户黑名单已点名者外**」，即取两者的交集——这是保守方向，且与 error-envelope 现状一致，落地后不会与任一份权威相反。
3. `spec.md:314` 那条注（论证转发 `Set-Cookie` 无害）保留，但要标明它论证的是**加不加额外防护**这个问题，不能用来越过一份已经存在的用户名单。

**证据强度：强到可以据此行动。** 三处原文我逐字读过全文（不是检索命中的一行）：用户名单在 `message-format-reshape.md:51-57`、error-envelope 的套用在 `:73`、本规格的自称在 `spec.md:302`。冲突的三个头是名单与「其余一律转发」的直接对撞，不依赖任何未观测行为。

**承重前提检查。** 前提是「§9.1 所在的这片区域没有用户已表态的一手来源」。`message-format-reshape.md:51-57` 直接证伪。次级前提「error-envelope 的直连定义域与本规格不同」也被证伪：两者都键在 `translation_required is False`。

---

### major

#### `direct-responses-passthrough-spec-review-round7-02`

- finding_id：`direct-responses-passthrough-spec-review-round7-02`
- severity：`major`
- primary_location：`spec.md:109`
- related_locations：`spec.md:111`（那条脚注）、`spec.md:121`（§5 对「已提交」的定义）、`spec.md:127`（提交表第三行）、`spec.md:215`（§7 `block` 行）；骨架 `tests/unit/pipeline/delivery/test_responses_passthrough.py:122`
- 标题：v7 为修 round6-03 补的那句话给出两种读法——「不发出去」与「发出去但不算数」——而 §5 只支持前者

**那句话有三个分句，第二句与第三句给的是不同的规则。** `spec.md:109` 逐字：

> **只含 control 事件的安全前缀不构成「提交」**，它何时落到客户端由 §5 规定。§4 讲的是「哪一段字节可以成为一个交付单位」，§5 讲的是「交付它算不算堵死了 replay」，两者不是同一个判定。

- 第二句「**它何时落到客户端由 §5 规定**」＝ §5 决定**发不发**，即扣住不发。
- 第三句「§5 讲的是「**交付它算不算堵死了 replay**」」＝ 已经发了，§5 只回答这次交付要不要关掉 replay 窗口。

**§5 只支持第二句。** `spec.md:127` 的提交表第三行写的是「`response.created` / `response.in_progress` → **保持 attempt-local**，随第一批可交付 item 事件一起提交」；第四行「无 item 的 terminal／failure → 在最终决定不 replay 后，与本 attempt 的 control events 一起提交」也只在「扣住」的读法下成立。而 `spec.md:121` 给「已提交」下的定义是「**客户端已经看到本次 attempt 的原生事件**」——按这个定义，一旦真把 `response.created` 写出去，它**就是**提交，第三句所描述的那种「发了但不算数」的状态在 §5 里不存在。

**第一句「不构成提交」在正确读法下是空的，而在错误读法下是一条许可。** 若按第二句扣住不发，那就没有什么需要声明「不构成提交」；这句话之所以读起来有内容，恰恰是因为它暗示「你可以发」。`spec.md:111` 的脚注反而把话说清楚了——「若按前者，`response.created` **一写出去** attempt 即为已提交」——脚注承认写出去就是提交，正文却在说写出去不算提交。

**已经有读者取了另一读，不是我构造的。** 骨架测试 `test_an_items_events_do_not_straddle_a_release_boundary` 第 122 行的注释逐字写着：

> `# The envelope frame is a control-only prefix: released here, but §5 says releasing it is not a commit.`

「§5 says releasing it is not a commit」——§5 没有说这句话，§5 说的是扣住不发。**这条注释是 Spec 这句话被误读之后的产物**（骨架本身的行为没有错：assembler 的 release 只是把批次交给调用方，写不写到客户端是 delivery 那一刀的事；错的是注释对 §5 的复述，而下一刀的实施者读的就是它）。

**影响。** 若 delivery 那一刀按错误读法实现，round6-03 指出的缺陷原样回来：`response.created` 一落地，§5 的整套 replay 合同在默认 policy 下永不成立，四轮评审的主要产出全部走不到。再加一层更直接的客户端可观察后果：真做了 replay，客户端会收到**两个** `response.created`（新旧 attempt 的 `response.id` 还不同），这是协议层面的坏帧，而不只是「窗口关早了」。

**为什么是 major 而不是 blocker。** §5 是无歧义的，且 §4 自己的第二句就把裁断权交给了 §5，所以存在明确的裁断方向——与 round6-01 不同，那一条的两个答案都在同一张表里、没有裁断句。

**建议。** `spec.md:109` 第一句与第三句一起改写为一句正面规则，例如：「只含 control 事件的安全前缀**可以成为一个交付单位，但不得单独交付给客户端**——它随第一批可交付 item 事件一起落地（§5 提交表）。§4 决定哪一段字节构成交付单位，§5 决定它何时落到客户端。」同时请骨架那一刀顺手修 `test_responses_passthrough.py:122` 的注释，它现在复述的是一条 §5 没有的规则。两处都属 §2.3 的本规格推导，评审共识即可改。

**证据强度：强到可以据此行动。** 纯文本自证（三处逐字引用），加一处已经发生的误读实例。不依赖实现或上游。

---

#### `direct-responses-passthrough-spec-review-round7-03`

- finding_id：`direct-responses-passthrough-spec-review-round7-03`
- severity：`major`
- primary_location：`spec.md:271`（policy × ending 表第一行）
- related_locations：`spec.md:131`（§5 的丢弃句）、`spec.md:247`（partition 第一格，v7 已收紧）、`spec.md:251`（v7 那条说明）；`src/app/pipeline/delivery/stream.py:467-472`
- 标题：v7 只给 partition 第一格补了「且重开已经成功」，同一节第二张表与 §5 的丢弃句仍是收紧前的谓词

**修复没有传播到全部复述处，而漏掉的那处正是实施者最可能读的一张表。** v7 把 `spec.md:247` 收紧成「replay 有预算、该失败可重试，**且重开已经成功**（§5.2 的 `OpenedAttempt`）」。但同一节 `spec.md:271` 的 policy × ending 表第一行仍然是：

> | **仍可 funded replay 的 tear／EOF** | **不收口**，整次 attempt 无提交丢弃 | 同左 | 同左 |

「仍可 funded replay」正是 round6-01 攻击的那个谓词：它在**尝试重开之前**就可求值，而它配的动作是这份 Spec 里最具破坏性的一个（「整次 attempt 无提交丢弃」，`full` 下等于整轮内容）。同理 `spec.md:131` §5 的丢弃句——「旧 attempt 的 control events、item 队列、terminal、ids、usage 与内存计量**全部丢弃**」——通篇没有时点。

**两张表可以调和，但要靠读者自己接线。** §7.2 的入口段（`spec.md:243`）说本节只在 §5 的 replay 判定之后运行，partition 表是入口门；照这个顺序读，第二张表的第一行只在 partition 判了第一格之后才可能命中，于是「仍可 funded replay」隐含了「重开已经成功」。**问题在于这条接线要求读者先读 partition 表再读 ending 表**，而一个从「每种 ending 该怎么办」这一侧读起来的实施者——这恰恰是 plan step 6 的视角，`plan.md:87` 就叫「三种 policy（含 §7.2 的 policy × 最终 ending）」——读到的第一份指令就是收紧前的那份。

**代价与 round6-01 完全相同，不是它的弱化版。** 优雅关闭已经被 round6-02 的修复挪走，但 `AttemptFailed` 与本地前置拒绝仍然落在同一个间隔里（v7 自己在 `spec.md:251` 写下了这一点）。命中时两个答案是「整轮已完成内容 ＋ 一条 error」与「只有一条 error」。

**现有实现的顺序是对的，Spec 反而落后于它。** `stream.py:468-472`：`replacement = await replay.reopen(torn)`，`if replacement is not None:` 之后才「Everything the failed attempt built is dropped, not carried」。也就是说主仓已经是「重开成功之后才丢」，Spec 的两处复述比代码还宽。

**建议。** 三处一起改，都属 §2.3 推导：

1. `spec.md:271` 第一行谓词补齐为「仍可 funded replay **且重开已经成功**的 tear／EOF」，或直接改写为「partition 第一格命中时」，把两张表的接线写在字面上而不是留给读者。
2. `spec.md:131` 的丢弃句补一个时点：「丢弃发生在新流到手之后；在此之前旧 attempt 的队列必须保持可提交」。
3. 顺带把 §8 的 memory cap 口径对齐：既然队列要保留到重开成功，那段时间内它按 `spec.md:286` 就仍属「本代理当前持有的字节」，`spec.md:286` 的「replay reset 后按实际持有退还计量」也应说明 reset 的时点是重开成功而非判定 replay。**这一项本身不产生错误行为**（保留期内新 attempt 还没开始产字节，峰值不会超过旧 attempt 已有的持有量），但计数器会在两种读法下差一个窗口，属于「缺席读不出来」的同族。

**证据强度：强到可以据此行动。** 依据是被评文档两处的逐字谓词，加上主仓 `stream.py:468-472` 的执行顺序实证。不依赖任何未观测的上游行为。

---

#### `direct-responses-passthrough-spec-review-round7-04`

- finding_id：`direct-responses-passthrough-spec-review-round7-04`
- severity：`major`
- primary_location：`spec.md:263-267`（§7.2 收口三步）
- related_locations：`spec.md:113-115`（§4 的「保守持有到 terminal」与四个 audio 反例）、`spec.md:63-65`（§3 承诺的覆盖面与未闭合尾巴的丢弃）、`spec.md:38`（§2.1 用户裁决）；骨架 `openai_responses_passthrough.py:175-180`（`unfinished` 的 docstring 与实现）
- 标题：「无法归属」的事件被持有到 terminal 之后没有归宿，收口三步不含它，骨架已代 Spec 裁定为丢弃

**Spec 只写到「持有」为止。** `spec.md:113`：「无法判定某事件属于哪个 item 时，保守持有到 terminal——它与「这是 envelope 事件」是**两个相反的处置**。」v7 把「持有 vs 释放」这一半定死了，**没有定「持有到 terminal 之后呢」**。

**收口三步（`spec.md:265-267`）把可能的去向穷举成了两类，而它两类都不是：**

1. 丢弃**未闭合 item 的 suffix**（§3）——它不属于任何 item，按定义不是某个未闭合 item 的 suffix；
2. 按原序提交 control 与**所有已完成的安全 group**——它既不是 control（§4 刚把它和 envelope 分开），也不属于任何已完成 group；
3. 提交上游 terminal／failure 或 proxy error——与它无关。

§3 的承诺面（`spec.md:63`）同样把它排除在外：承诺只覆盖「属于一个已完成的 item group、或属于 control 与 terminal／failure 的 SSE 事件」。所以 Spec 既没承诺交付它，也没规定丢弃它。

**骨架已经把这个空白填上了，填的是丢弃。** `openai_responses_passthrough.py:175-180` 的 `unfinished` docstring 第一句逐字：「The tail that **no ending may deliver**: events of items that never closed, and events that could not be attributed at all.」——"no ending may deliver" 是一条规范性陈述，而 Spec 里没有这条。调用方按 §7.2 第 1 步丢弃 `unfinished`，这些事件就没了。

**丢弃恰好是与 §2.1 用户裁决张力最大的那个答案。** 用户原话「协议允许，凭什么拒绝？」支持的命题是「不得以本代理不认识为由拒绝一个协议允许的直连 item」。而这里发生的正是：**因为本代理判不出它属于谁，一个协议合法、承载模型输出的事件被静默丢掉**。Spec 自己在 `spec.md:115` 列出了这类事件的实例——`openai==3.3.1` 的四个 audio 事件（`response.audio.delta`／`.done`／`.transcript.delta`／`.transcript.done`）「**它们承载模型输出**，却既无 `output_index` 也无 `item_id`」。一个用音频的 Responses 客户端在本腿上会拿到零个音频事件，而这不是任何人裁决过的。

**触发面要分开说。** 两条路径的权重不同：

- **audio 系列**：机制确定（SDK 类型逐字可核），**触发未证实**——GitHub Copilot 的 Responses 端点是否发音频事件，本轮无从测。这一条只是倾向。
- **payload 解不开**：`spec.md:115` 自己写了「payload 解不开时也落在这里」，而 `SseEvent.json()`（`sse_source.py:30-38`）对任何非 object 或解析失败的 payload 返回 `{}`。**P3 修复落地之前，一个含裸 U+2028 的普通 `output_text.delta` 被截断后就不再是合法 JSON**，于是它落进「无法归属」，被持有，再在收口时丢掉——**一个正常的文本增量事件因为一个编码问题而静默消失**。这条路径的机制与触发链条都在 Spec 自己的文本里，比 audio 那条实在得多。

**影响。** 用户可观察行为二选一（交付 or 丢弃），Spec 没选，代码选了，且选的那一支与 §2.1 冲突。plan step 6（§7.2 收口）没有这条的判据，plan step 2（骨架）已经把答案写进 docstring——**这是实现先于 Spec 确立了一条对外行为**，项目规则里点名不许的那一形。

**建议。** 在 §7.2 收口顺序里给它第四类处置，并在 §3 的承诺面上同步。我的推荐（属 §2.3 推导，评审共识即可改，但请注意它触到 §2.1 的边）：

> 4. 无法归属的事件：若最终 ending 是**上游终局**（`completed`／`incomplete`／`cancelled`／`failed`／`error`），**按原序逐字提交**它们——上游把整个 response 结束了，它们不再有「属于一个未闭合 item」的可能性之外的解释，而丢弃它们就是以本代理判不出归属为由拒绝一个协议合法的事件；若最终 ending 是**代理侧的**（tear、EOF、cap、deadline、拒绝），与未闭合尾巴同样丢弃——此时上游确实没把话说完。

若采纳，`unfinished` 的语义要拆成两个（「未闭合 item 的尾巴」与「无法归属」），骨架那句 "no ending may deliver" 必须同时改；plan 的 v7 验收清单要加一条正向断言（「上游终局到达时，一个不带 `output_index` 的事件**仍在**交付里」）。若不采纳而选择丢弃，那也请写进 §7.2 并在 §3 的「明确不承诺」里点名，理由不能是「判不出归属」，得是别的——因为那个理由用户已经否过一次。

**证据强度：机制强到可以据此行动**（Spec 三处逐字 ＋ SDK 枚举 ＋ 骨架 docstring 逐字）；**audio 那条触发路径只是倾向，需要上游样本**；**payload 解不开那条路径的链条完整**，因为 §3.1 第三条自己就描述了截断，`SseEvent.json()` 的兜底我逐行读过。

---

### minor

#### `direct-responses-passthrough-spec-review-round7-05`

- finding_id：`direct-responses-passthrough-spec-review-round7-05`
- severity：`minor`
- primary_location：`spec.md:177`
- related_locations：`spec.md:175`（`ReopenRefused` 行）、`spec.md:251`、`spec.md:260`（final source 新行）；`src/app/server/routes/inference.py:410-433`
- 标题：draining 移走之后 `ReopenRefused` 没有任何具名实例，「其余形态还在它下面」是一句无据的非空断言

`spec.md:177` 写：「`ReopenRefused` 这个分类本身仍然有用——**本地前置拒绝的其余形态还在它下面**——**不要因为把 draining 提前就把整个 `ReopenRefused` 删掉**。」这句话断言集合非空，但 Spec 全文没有点名任何一个其余形态。

**代码侧我逐行读过 `_reopen`（`inference.py:395-461`），它只有两种返回 `None` 的路径**：`:410-415` 的 draining 检查（这一个正在被移走），以及 `:432-433` 的 `if reopened is None or not again.context.stream`——后者发生在 `await handle(...)` **之后**，即 replacement 已经开过，按 §5.2 的定义属于 `AttemptFailed` 一侧而不是「本地前置拒绝」。所以今天 `ReopenRefused` 的具名实例数是 **1**，移走 draining 之后是 **0**。

**为什么仍然只是 minor。** 保留这个分类本身是对的：三分法的价值在于「本地拒绝」与「上游失败」的 origin 不同，一个今天为空的槽位好过将来把本地拒绝挤进 `AttemptFailed`。错的只是理由——一句「其余形态还在它下面」会让下一个读者以为有过核对。这与 round6-06 是同一形状：**一个正确的结论配一个假的理由，核到理由为假的人会连结论一起推翻**。

**连带影响一处。** `spec.md:260` 的 final source 新行按 `ReopenRefused`／`AttemptFailed` 分派 origin；若前者今天为空，那一行实际只有一半会执行，而 plan 的 v7 验收清单里「上游终局存在但 attempt 已作废时不得逐字重放它」这条判据大概率只能用 `AttemptFailed` 构造。写清楚可以省下实施者一次困惑。

**建议。** `spec.md:177` 改为：「`ReopenRefused` 保留为分类槽位。**移走 draining 之后本规格没有点名其余实例，主仓 `_reopen` 今天也只有 draining 这一条本地前置拒绝**；保留它是为了将来新增的本地拒绝有处可去，不是因为已知还有别的。」

**证据强度：强**（`_reopen` 全文逐行读过，两条 `return None` 路径逐一分类）。「将来会不会有别的本地拒绝」不可证伪，本条不要求预测，只要求 Spec 别断言。

---

#### `direct-responses-passthrough-spec-review-round7-06`

- finding_id：`direct-responses-passthrough-spec-review-round7-06`
- severity：`minor`
- primary_location：`spec.md:169`
- related_locations：`spec.md:177`
- 标题：§5.2 的三分法仍以 draining 为论据，而同节下方已把 draining 移出该表

`spec.md:169` 逐字：「重开一次 attempt 的结果有三类，必须分开，v4 把它们压成了「一个 exception」，而那不成立——**draining 时根本没有调用过 `handle`**，既没有 replacement attempt 也没有 exception」。八行之后的 `spec.md:177` 说「**draining 不进这张表**」。

于是这张表的存在理由，落在一个这张表已经声明不管的例子上。三分法本身仍然成立（`OpenedAttempt` 与 `AttemptFailed` 的差别与 draining 无关），只是论据要换：`AttemptFailed` 携带 replacement 自己的 error 与 origin，而 v4 的「一个 exception」把它与「本代理拒绝」混为一谈，这才是三分法今天的理由。

**建议。** 把 `spec.md:169` 的破折号后半句换成不依赖 draining 的论据，例如「replacement 自己失败与本代理拒绝重开的 origin 不同，压成一个 exception 会把前者的上游归因套到后者身上」。属 §2.3 推导。与 round7-05 同一次编辑即可。

**证据强度：强**（同节两句逐字对读）。**影响：文档可信度，无行为后果。**

---

#### `direct-responses-passthrough-spec-review-round7-07`

- finding_id：`direct-responses-passthrough-spec-review-round7-07`
- severity：`minor`
- primary_location：`spec.md:260`
- related_locations：`spec.md:174-175`（§5.2 表的两行）
- 标题：final source 新行说 origin「依 §5.2」，而 §5.2 并没有给出 origin 的取值

`spec.md:260` 逐字：「origin 依 §5.2（`ReopenRefused` 为 proxy，`AttemptFailed` 为 upstream）」。回去看 §5.2：`ReopenRefused` 行写「origin 是 proxy」——这一半对得上；`AttemptFailed` 行只写「**携带它自己的 error 与 origin**」，**没有给出取值**。所以「`AttemptFailed` 为 upstream」这个决定实际是在 §7.2 作出的，却被写成了对 §5.2 的引用。

这正是 round6-01 留下的那半个问题：它当时指出「replacement 的 HTTP 500 在 `FailureOrigin` 的两个值（`UPSTREAM_EVENT` 与 `PROXY_REFUSAL`）里都不是」。v7 给了答案（算 upstream），答得也合理——replacement 是一次真实的上游往返——但答案落在了引用侧而不是权威侧，于是「同一事实只有一处当前指令」被破坏，且被破坏的方式最难发现：读者跳到 §5.2 去核，会发现那里没有这句话，然后不知道该信谁。

**建议。** 把取值搬进 §5.2 的表（`AttemptFailed` 行补「origin 为 upstream——replacement 是一次真实的上游往返，即使失败在 transport 层」），`spec.md:260` 保留纯引用。若 `FailureOrigin` 现有两值都不合身，那属实现层的承载问题，归 plan，不必进 Spec。

**证据强度：强**（两处逐字对读）。

---

#### `direct-responses-passthrough-spec-review-round7-08`

- finding_id：`direct-responses-passthrough-spec-review-round7-08`
- severity：`minor`
- primary_location：`spec.md:290-292`（§9 的裁定）
- related_locations：`spec.md:59`（§2.4 跨腿合同）；`.dev/docs/error-envelope/spec.md:71`、`:76`、`:80-84`（§3.1／§3.2）
- 标题：§9 没有把定义域限在成功 body，而上游的非流式**错误** body 归 error-envelope，两者的保真级别不同

`spec.md:292` 的裁定逐字：「合法 Responses JSON object 按 **JSON value 保真**，所有未知字段保留，允许序列化拼法变化；HTTP status 原样」。这句话没有说「成功」二字。

`error-envelope/spec.md:71` 对同一条腿的**错误** body 的要求严格得多：「上游的错误 body **原样交给客户端**。不解析、不重排、不改写、不包一层」，并且 `:80-84` 把「在 `_response_parts` 处同时保留原始 `bytes` 与其 content-type」列为 §3 其余部分的**前置**，理由是评审实测过非 UTF-8 body 已不可恢复。`:76` 还规定错误响应的 `Content-Type` **随上游**（`text/html` 也照传）——与本规格 `spec.md:310` 对成功响应的「由本代理按实际输出重建」正好相反。

**两条规则各自都对，冲突只在定义域没写。** §9.1 的标题带了「成功响应头」四个字，§9 没有；一个照 §9 字面实施的人会把上游的 4xx／5xx JSON body 也 parse 一遍再重新序列化，那正是 error-envelope 用一整节前置工作在防的事。

**建议。** `spec.md:290` 段首补一句定义域：「本节只覆盖**成功**（2xx）非流式响应。上游的非流式错误响应按 `error-envelope/spec.md` §3.1 原始字节透传，包括其 `Content-Type`——那是跨腿合同（§2.4），不因本腿走 native 而改变。」属 §2.3 推导。

**证据强度：强**（两份文档逐字对读，定义域缺失是文本事实）。**当前是否已产生错误行为未核**——`inference.py` 的错误路径本轮没读全，本条只要求 Spec 划清定义域。

---

#### `direct-responses-passthrough-spec-review-round7-09`

- finding_id：`direct-responses-passthrough-spec-review-round7-09`
- severity：`minor`
- primary_location：`plan.md:113`（v7 验收清单）
- related_locations：`spec.md:247`、`spec.md:271`
- 标题：v7 验收清单收了五条，唯独漏了 round6 那个 blocker 的修复本身

`plan.md:113` 的 v7 组列了五条：control-only 前缀不构成提交、item 事件不跨越释放边界、「无法归属」与「envelope」处置相反、draining 不花 replay 预算、上游终局存在但 attempt 已作废时不得逐字重放。

**漏掉的是第六条：重开被拒／失败时，已完成 group 仍须按原序提交。** 这正是 v7 那次修复（partition 第一格补「且重开已经成功」）的可观察产物，也是 round6-01 那个 blocker 的正解。按 `plan.md:107` 自己给的入选理由（「只在正文出现过」）它完全够格，而且它是**反向断言**——错误实现（判定 replay 就立刻销毁队列）在只测「funded replay 时一个字节都不提交」的判据下照样绿，因为那条判据测的是另一个方向。这与 round6-09 点名的 weak `ETag` 是同一形状，也是本项目付过代价的形状。

**建议。** `plan.md:113` 补一条，写成正向断言：「构造『判定可 replay → 重开被拒』，断言此前已完成的 group **仍在**最终输出里且保持原序（错误实现会只剩一条 error）」；顺带把 round7-03 要补的时点也纳入同一条判据。

**证据强度：强到可以据此行动**（依据是 Plan 自身条款与 v7 的改动面）。

---

#### `direct-responses-passthrough-spec-review-round7-10`

- finding_id：`direct-responses-passthrough-spec-review-round7-10`
- severity：`minor`
- primary_location：`plan.md:94`（接线从第 3 位挪到第 7 位的说明）
- related_locations：`plan.md:82-90`（顺序表）、`plan.md:92`（接线必须是一刀的论证）
- 标题：顺序调整成立，但记录只权衡了一侧的风险，也没记下第三个选项

**先说结论：这次调整我判为成立**，理由与 plan 自己给的一致且我复核过——「一个把两种 policy 留作未定义的接线」不是自足切片，「小切片即刻集成」要求的是切片自足，不是要求它排在前面；接线仍然是一刀，只是落在 policy 之后，round6-04 论证的「同一个 observable switch」不受影响。

**但记录只写了一半。** `plan.md:94` 只权衡了「接线在前」的代价（非默认 policy 静默退化成 `block`，本项目在「缺席读不出来」上付过代价）。**没有记「接线在后」的代价**：step 3（P3）、step 4（提交语义）、step 5（replay）、step 6（policy）四刀落进 `main` 之后，其中 4、5、6 的产物**没有任何调用者**，要到 step 7 才第一次被真实入口执行。本项目对这个形状同样有成本记录——「守卫被留在了 legacy 链路上：先问『新链路真调用它了吗』；三次击发，第三次是静默假成功而非 400」。两侧都是真实风险，只记一侧会让下一个读者以为这个决定没有代价。

**也没有记第三个选项**：接线早落，但**按 policy 条件路由**——`delivery_policy` 只在 `block` 下选透传 assembler，`full`／`until-tool-use` 仍走 `ResponsesAssembler`，直到 step 6 把等价物补齐。它同时避开了静默退化（`full` 仍是真的 `full`）与死码窗口（新链路一落地就有真实流量）。**它的代价也很具体**：直连腿的可观察行为在过渡期取决于 policy，`ca777df` 的撤销只在 `block` 下生效，于是 issue #2 那个 item 在 `full` 下仍被拒——「行为取决于配置项」本身就是个坏形状。我**不推荐**它，但它应该被记下来并写明否决理由，否则下一个人还会重新想到它一次。

**建议。** `plan.md:94` 补两句：接线在后的代价（三刀无调用者，直到 step 7 才第一次被真实入口执行；缓解办法是 step 7 明确把「新链路确实被调用」列为验收的一部分，而不是只看单测绿）；以及第三个选项与它被否决的理由。属 plan 自己的记录，不涉及 Spec。

**证据强度：强到可以据此行动**（依据是 plan 自身的顺序表与说明段）。**「哪种顺序更好」是主观判断**，我给的是「调整成立」，不是「另一种不可行」。

---

### nit

#### `direct-responses-passthrough-spec-review-round7-11`

- finding_id：`direct-responses-passthrough-spec-review-round7-11`
- severity：`nit`
- primary_location：`spec.md:117`
- related_locations：`spec.md:165`
- 标题：同一份 Spec 里「三份 cassette」与「五份 cassette」指的不是同一个集合，都没加限定

`spec.md:117`：「**三份** cassette 的 `output_index` run 都是 `[0,1]`」；`spec.md:165`：「「**五份** cassette 里零出现」只说明当前样本没命中过 failure event」。skeleton-11 已经在测试侧改成了「the three **Responses-stream** cassettes」，Spec 侧两处都还没加限定词。`tests/int/cassettes/` 下共 5 个文件，带 Responses 事件流的是 3 个。

**建议。** `spec.md:117` 改「三份 Responses 流 cassette」，`spec.md:165` 改「全部五份 cassette」。

**证据强度：强**（skeleton 评审已全量核对过两个集合，本轮沿用）。

---

#### `direct-responses-passthrough-spec-review-round7-12`

- finding_id：`direct-responses-passthrough-spec-review-round7-12`
- severity：`nit`
- primary_location：`spec.md:63`
- related_locations：`spec.md:88`、`spec.md:92`
- 标题：§3 的保真承诺以本项目 parser 的输出为基准，因此对 P3 这一类 parser 缺陷天然没有分辨力

§3 承诺的是「经 SSE field parsing 得到的 logical `data` 字符串」逐字重放。**注意这个基准是相对的**：`parse_frame` 把 payload 截断之后，我们仍然「逐字重放了它解析出来的东西」，§3 的承诺照样成立。也就是说，**§3 这句话本身检测不出 P3**，P3 只能靠 §3.1 第三条自己的规范性语句站住。同理，§3 的「明确不承诺」四项里有三项是按 `parse_frame` 的现有行为写的（注释行、只有 `event:` 的帧、`errors='replace'`），混着规范与实现两个基准。

**顺带一处归属**：`spec.md:88` 的引导句把三条都归进「本承诺不能靠 v2 当时的 **writer** 兑现」，而第三条是 **reader**（`parse_frame`）的缺陷，与 writer 无关。

**建议。** `spec.md:63` 把基准钉到外部规范：「按 **SSE 规范的 field parsing 算法**得到的 logical `data` 字符串」，并在 §3.1 第三条旁注明「本项目当前的 `parse_frame` 与该算法有偏差，见下」；`spec.md:88` 的引导句改为「两处 writer 缺陷与一处 reader 缺陷」。

**证据强度：强**（`sse_source.py:41-59` 全文读过，承诺文本逐字）。**影响：判据的分辨力，无当前行为后果**（第三条已被单独写成规范性要求）。

---

#### `direct-responses-passthrough-spec-review-round7-13`

- finding_id：`direct-responses-passthrough-spec-review-round7-13`
- severity：`nit`
- primary_location：`spec.md:92`
- 标题：P3 的机制陈述「后半段没有冒号，`parse_frame` 直接跳过它」只对举例的那个 payload 成立

`spec.md:92` 写：「于是 data 里一个裸的 U+2028、U+2029 或 U+0085 会让该行**从此处截断**：后半段没有冒号，`parse_frame` 直接跳过它」。

**对示例 `data: {"delta":"a<CH>b"}` 成立**（后半段是 `b"}`，确实无冒号）。但真实 payload 的截断点之后通常**还有冒号**——例如 `{"delta":"a<U+2028>b","output_index":0}` 的后半段是 `b","output_index":0}`，`partition(":")` 会得到 name=`b","output_index"`，因为它既不是 `event` 也不是 `data` 而被忽略。**结论（后半段丢失）不变，机制多了一条路**。

写下来的理由是：「后半段没有冒号」读起来像一条普遍机制，会让人以为「有冒号的后半段是安全的」。

**建议。** 改为「后半段不构成一个 `data` 字段（无冒号则被跳过，有冒号则落进一个既非 `event` 也非 `data` 的字段名），两条路都丢内容」。

**证据强度：强**（`parse_frame` 逐行读过，两条分支各自走过一遍）。

---

#### `direct-responses-passthrough-spec-review-round7-14`

- finding_id：`direct-responses-passthrough-spec-review-round7-14`
- severity：`nit`
- primary_location：`plan.md:60`
- related_locations：`plan.md:66`（同一文件的相反纪律）、`spec.md:158-163`
- 标题：plan §5 逐字转抄了 Spec 的 code 映射表，而同一文件 §5.1 明确拒绝转抄名单

`plan.md:60`：「映射见 Spec 的表——`server_error` 与 `vector_store_timeout` 可重试、`rate_limit_exceeded` 走既有 rate-limit 通道、其余与未知不重试。」这是一份转抄，今天与 `spec.md:158-163` 一致。而同一文件 `plan.md:66` 对 header 名单写的是「**判据在 Spec，本文件不复制名单**，因为名单必漏」——同一份文件里两种纪律。

Spec 是活文档，`vector_store_timeout` 这一格在 v6 才刚改过一次；再改一次时这份转抄不会红。项目规则对转抄的要求是「同一次改动更新全部已知复述」，而一份口头承诺不如不抄。

**建议。** `plan.md:60` 改为「映射见 Spec §5.2 的表，本文件不复制」，与 §5.1 的纪律对齐。

**证据强度：强**（同一文件两处逐字对读）。

---

## 五 · 门禁：可否开始主体实现（plan.md §8 逐步）

调用方要求每一步单独给 yes/no 与条件。

| 步 | 内容 | 门禁 | 条件 |
|---|---|---|---|
| 1 | P1／P2 | — | 已完成（`7e96adc`） |
| 2 | 透传 assembler／framer 骨架 | **yes（已落地），但 squash 前有一处必改** | skeleton 十一条全关，逻辑我按 Spec 走过四组序列。**必改**：`unfinished` 的 docstring 那句 "The tail that no ending may deliver" 是一条 Spec 没有的规范性陈述（round7-04）；`test_responses_passthrough.py:122` 对 §5 的复述是错的（round7-02）。两处都是注释级，不改代码行为 |
| 3 | `parse_frame` 只认 CR／LF／CRLF（P3） | **yes，无条件** | Spec §3.1 第三条无歧义，plan §0 已给可失败判据，两腿共用、与本腿接线无关。**注意**：并行 worktree `260831-sse-line-endings` 已经实现了它（`_LINE_ENDING` ＋ `re.split`），落地后 `spec.md:4`／`spec.md:92`／`plan.md:17` 三处状态要同步 |
| 4 | 交错场景与 §5 的提交语义接线 | **no** | 挡在 round7-02：这一步**拥有的就是**「什么算已提交」，而 §4:109 对 control-only 前缀给出两种读法，其中一读会让 replay 合同永不成立、并让客户端在 replay 后收到两个 `response.created`。改一句话即可解除 |
| 5 | replay 合同（§5.2 三类结果与 failure 归一化） | **conditional yes** | round7-03 必须先改——这一步要决定「队列何时销毁」，而 Spec 的两处复述比代码还宽。round7-05／06／07 落在同一片，可与实施同刀改 Spec，不必先行。§5.2 的映射表本身可执行，我复核无缺口 |
| 6 | `requires_client_action` 与三种 policy（含 §7.2） | **no** | 挡在 round7-04（收口三步不穷尽，第四类处置未裁）与 round7-03（ending 表第一行仍是旧谓词）。§7.1 那一半没有问题，可以先做 |
| 7 | 分流点接线 ＋ 撤销 `ca777df` ＋ 更新断言 | **no** | 依赖 4 与 6 落地。这一步自身的执行指令（点名的测试、翻译腿不动）已核准确，`:2549`／`:2585`／`:2617`／`:2652` 四处行号逐个对得上。建议按 round7-10 在本步验收里加一条「新链路确实被真实入口调用」 |
| 8 | Headers（§9.1） | **no** | 挡在 round7-01，**且这是唯一必须上交用户的一条**：用户亲笔黑名单的定义域只有用户能裁。在裁决到达之前，Spec 可以先按「取交集」写，落地后不与任一份权威相反；round7-08 同刀处理 |
| 9 | 可观测迁移（§10） | **yes**，但排在 4–6 之后不变 | §10 的下界与「无法分类必须记 unknown」是清楚的；它消费的事实由 4–6 产出，提前做没有输入。`plan.md` 未提但会在本步触发的测试变更（`tests/int/test_pipeline_app.py:2788`）round6 已点名，v6 未收进 plan——**这一条我沿用 round6 的建议，仍然建议在本步点名它** |

**总结成一句**：step 2 收尾与 step 3 现在就能走；step 5 改一处 Spec 即可开工；step 4、6 各挡在一条 major 上，都是文本级修正；step 7 依赖 4／6；step 8 挡在唯一需要用户裁决的那条上。

## 六 · plan v6 顺序调整是否成立

单独回答调用方的第四问。

**成立。** 三条理由，逐条复核过：

1. **「一刀」的完整性不受位置影响。** round6-04 论证接线必须是一刀，依据是「启用透传」与「撤销 direct 的 `REJECT`」是同一个 observable switch——这个依据与它排第几位无关。v6 在 `plan.md:94` 自己也点明了这一点。
2. **与「小切片即刻集成」不冲突。** 这条规则要求的是**切片自足**。一个「把 `full` 与 `until-tool-use` 留作未定义」的接线不自足：它的可观察行为在两种合法配置下没有定义，最可能的实现结果是静默退化。把它推迟到自足为止，是让规则生效而不是绕过它。
3. **备选方案确实更差。** 保持顺序 ＋ 写降级代码 ＋ 声明一条退化事实，那段代码在 step 6 之后即成死码；而「静默退化成 `block`」正是本项目在「缺席读不出来」上付过代价的形状。

**但记录不完整**，见 round7-10：另一侧的代价（三刀无调用者）与第三个选项（按 policy 条件路由）都没写下来。**这不改变结论，只影响下一个读者能不能复用这个判断。**

## 七 · §11「当前为空」的复核

**当前不名副实。** round7-01（用户名单冲突，需用户裁定定义域）与 round7-04（无法归属事件在 ending 处的处置）都是 Spec 级、影响用户可观察行为的未闭合项，按 §11 自己的定义应当登记。round7-02／03 是措辞与传播问题，改完即消，不必进 §11。

修完这两条之后，本轮**没有**发现第三个需要用户裁决的产品分叉。届时 §11 可以真正为空。

## 八 · 考虑过但否决的候选发现

逐条写下，因为纯推理排除掉的路线事后捞不回来。

1. **「v7 收紧后的 partition 仍不穷尽——`AttemptFailed` 落在三格之外」——查证后否决。** 逐路径走过：`AttemptFailed` 之后 §5.2 要求它的 error 走既有 `replay_reason`，于是要么再次命中第一格（重开成功），要么最终不可重试／预算耗尽而落进第二格。它是**过程态**而不是 ending 态，三格在「最终 ending 到达」这个时点仍然穷尽。唯一可挑的是第二格「replay 不可用」这个措辞略宽，需要读者把「replacement 的失败最终不可重试」读进去——但 §5.2 的 `AttemptFailed` 行写了「最终不可重试时」，接得上，不值得单报。
2. **「第一格与第二格之间有一个『判定 replay 之后、结果已知之前』的真空」——查证后否决为发现。** 确实两格都不覆盖那个瞬间，但 §7.2 的入口条件是「客户端最终看到的结束」，而重开进行中不是任何 ending，此刻不需要答案。收紧后隐含的要求（那段时间队列必须保持可提交）我并入 round7-03 的建议 2，不另立一条。
3. **「§5:139 把『判定发生在重开之前』一并标成用户裁决，属超范围归属」——考虑后降级为提醒，不占档位。** 三问走过：用户原话「不再**考虑**无痕重试」，而「试了被拒」在语义上属于已经考虑过，所以「资格判定」这个读法是**语义蕴含**而不是新增裁决；主仓 `base.py:74-82` 也早按这个读法实现并在注释里记着两扇门的差异。归属成立。**要提醒的只有一点**：那一段把用户原话与「因此判定发生在重开之前」写在同一句里，`spec.md:181` 又说「这四条都是本规格的推导」，读者不容易分清哪半是哪半。若做 round7-05／06 的编辑，顺手把「因此」后半句拆成独立一句并标 §2.3 即可。
4. **「§7.1 说未知类型『保守视为需要释放』，而 §4 说无法归属『保守持有』，同一个词指向相反动作」——否决。** 两处问的不是同一个问题：§7.1 是「要不要提前触发 `until-tool-use`」，扣住的代价是客户端拿不到该行动的工具调用；§4 是「要不要交付一个可能属于未闭合 item 的碎片」。两个「保守」各自朝着代价小的一侧，逻辑一致，不是措辞冲突。
5. **「§9.1『其余一律转发』会把 `Set-Cookie` 转给客户端，构成安全问题」——仍然否决为安全发现。** 用户既有立场是没有具体危害就不加防护，转发对象是发起请求的客户端本人。**本轮把它升级成 round7-01 的理由与安全无关**：它与一份用户亲笔名单相反，这是权威冲突，不是威胁模型问题。两者不要混为一谈——即使用户裁定「本腿不适用那份名单」，安全侧也不需要额外动作。
6. **「§9 的 JSON value 保真会丢重复键与数字字面形式，应改为 byte-exact」——否决。** `spec.md:290-294` 已经准确陈述了当前行为与代价，并给了将来 byte-exact 的出口。这是有依据的取舍，不是缺陷。
7. **「骨架的 `_take_safe_prefix` 回退循环是 O(n²) 的两层扫描，`full` 下 n 是整个响应」——否决为发现，沿用 skeleton 评审的处置。** 量级实测可忽略（该轮已在 125 事件的 cassette 上测过），且没有 Spec 条款被违反。记在这里以免 `full` 那一刀落地时重新发现一次。
8. **「`RawEventBatch.size_bytes` 仍然没有调用者」——否决。** skeleton-08 的实质（同一事实两处各写一遍）已由 `_event_bytes` 消除；一个没有调用者的 property 在 cap 那一刀落地前不构成缺陷，也不值得现在删。
9. **「并行 worktree `260831-sse-line-endings` 的 `re.split` 会比 `splitlines()` 多产生一个尾部空串」——查证属实但不报，且不在本次范围。** `"data: 1\n"` 经 `re.split` 得到 `["data: 1", ""]`，而空串既不以 `:` 开头也不含冒号，`partition` 后 `separator` 为空即 `continue`，行为无差异；何况 `iter_frames` 交给 `parse_frame` 的帧已经不含尾部分隔符。**记在这里以免那一刀的评审者重新走一遍。**
10. **「`sse_source.py` 主仓版本的模块 docstring 第 9 行『`parse_frame` has always handled that, because `splitlines()` does』已被 P3 证伪」——属实，但不在被检对象范围内，且并行 worktree 已经改了那句。** 记下来只为一件事：若 P3 从别的路径落地而不是走那个 worktree，这句话必须一起改。
11. **「§10 的可观测清单太薄」——否决，沿用 round6 的处置。** 下界与「无法分类必须记 unknown、不得伪装成 absent」已经是硬约束，载体归 plan。
12. **「Spec 里仍留着 `encode_frame`、`JSONResponse`、`hand_back_block()` 等实现符号，应搬进 plan」——本轮仍不报，但状态要说清楚。** 这是 round5 提出、round6 沿用的一条**未采纳建议**，不是已闭合项。现在仍有 blocker，大搬文字会混入语义改动；建议等 §9.1 与 §7.2 收口后一次性瘦身。
13. **「`plan.md:5` 说『本文不定义任何用户可观察行为』，但 §5 的三类重开结果承载类型是 plan 决定的」——否决。** `spec.md:179` 已经写明「这是可观察事实的分类……具体用什么类型承载留给 plan」，分层是清楚的：语义在 Spec，承载在 plan。
14. **「§2.4 说 `ca777df` 的直连腿一半必须撤销，但没说撤销之后未知 item 走哪条路」——否决。** §3／§4／§6.1 合起来已经回答：一律原样重放，不需要被任何类型表认识。§2.4 只负责废掉误用的矩阵。
15. **「`spec.md:26` 的『28 个顶层成员』过期了」——否决。** skeleton 评审逐个数过为 28，本轮无新证据，且本地 SDK 版本未变。
16. **「应该给这些判据加一道 gate／覆盖率门／验收状态机」——否决。** 项目明令禁止为证明而搭证明设施。本报告只给判据与建议，不建议任何阻断装置。

以上是本轮实际考虑并排除或限定的线索。没有把未观测的上游发生率、未知客户端的解析行为、或未来的 SDK 变更猜成 severity finding。

## 九 · 搜索面、执行证据与限制

### 判据来源（独立于被检对象）

- `docs/.human-controlled/upstream-retry-and-continuation.md`（全文 65 行，逐字）、`client-side-block-delivery.md`（全文 22 行，逐字）、`message-format-reshape.md`（全文 89 行，逐字）——**第三份是本轮新读的，round1–6 的搜索面里都没有它，round7-01 就出自这里**。
- `.dev/docs/error-envelope/spec.md` §1–§3.5（`:20-99`），含用户 2026-08-23 原话与直连响应头规则。
- 主仓源码：`sse_source.py` 全文、`retry.py` 全文、`stream.py:420-539`、`direct_driver/base.py:40-159`、`inference.py:370-499`。
- 骨架 worktree：`openai_responses_passthrough.py` 全文（208 行）、`test_responses_passthrough.py` 全文（303 行）。
- 并行 worktree `260831-sse-line-endings`：`sse_source.py:1-70`。
- `tests/int/test_pipeline_app.py:2540-2689`（plan 点名的四个函数）。
- 前六轮报告 ＋ skeleton 评审（作为已核事实的来源，不作为判据的替代）。

### 限制（本轮的限制比前几轮**重得多**，读结论时请连同这一节一起读）

- **Bash 完全不可用。** harness 的 worktree isolation guard 认定本会话属于 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260831-sse-line-endings`，而工具的 cwd 解析到 `260831-passthrough-skeleton`，于是**每一次** `Bash` 调用都被拒（含无 `cd`、无 git 的纯 `ls`）。`EnterWorktree` 也拒（「已经在该目录」）。**后果**：本轮**没有跑任何测试、没有做任何变异、没有跑 `rg`／`fd`、没有用 git 核验任何哈希或 diff**。
- 因此：**「1968 passed／2 skipped」「HEAD `45f538d`」「`.dev` HEAD `b8364a2`」三项自述我一项都没能独立核验**，全部按调用方转述采纳，不按已验证采纳。
- 因此：**骨架测试的分辨力本轮未验。** skeleton 评审做过 12 次变异，本轮无法复现或补做。我对 skeleton 十一条的「closed」判定，依据是**读代码与读测试断言的形状**，属强推断而非一手执行——具体说：我核的是「修复的代码路径存在且逻辑正确」与「有一条断言会在旧行为下为假」，没核「跑起来确实红／绿」。
- 所有行号引用来自 `Read` 的输出（`cat -n` 形式），可回指；但**没有 grep，因此所有「全文只有一处」「没有别的实例」类判断的搜索面是我读过的文件，不是全仓**。round7-05 的「`_reopen` 只有两条 `return None`」是逐行读全函数得出的，可靠；「全仓没有别的本地前置拒绝」我**没有**断言。
- §2.1 的用户 8/30 原话「协议允许，凭什么拒绝？」我无法访问原始会话独立回指，按「与调用方复述及前六轮一致」采纳。§2.2、§5、§9.1 的用户归属则逐字可核，已核。
- **指定的报告路径写不进去**（worktree isolation guard），已按预案落到 `/tmp/ghc-review-r7/`，需调用方搬运。

## 十 · 严重度汇总

- blocker：1（`round7-01`）
- major：3（`round7-02`、`round7-03`、`round7-04`）
- minor：6（`round7-05`、`round7-06`、`round7-07`、`round7-08`、`round7-09`、`round7-10`）
- nit：4（`round7-11`、`round7-12`、`round7-13`、`round7-14`）
- finding_total：14

基线处置状态：round6 `closed=10`、`partially_closed=0`、`not_closed=0`；skeleton `closed=11`、`partially_closed=0`、`not_closed=0`。

## 十一 · 交接事项

1. **P3 正在并行进行。** `260831-sse-line-endings` worktree 已实现 `_LINE_ENDING` ＋ `re.split`，并改掉了模块 docstring 里那句被证伪的断言。它落地后，`spec.md:4`、`spec.md:92`（「未实现」）、`plan.md:4`、`plan.md:17` 四处状态要同步。本报告对 plan step 3 的「yes」是对 `main` 而言的。
2. **round7-01 需要用户裁决**，且只需要裁一件事：`message-format-reshape.md` 那份直连响应头黑名单（节标题「客户端返回 Anthropic Messages」）是否覆盖 Responses 客户端的直连腿。其余十三条都是评审共识可改的推导。
3. **本轮的限制清单请连同结论一起转述**：没有跑测试、没有变异、没有 git 核验。若下一轮能解除 Bash 限制，最该补的一件事是**对骨架新增的回退循环做一次变异**（把 `while cut > 0` 的循环改成单次 `if`，看 `test_retreating_past_one_straddling_item_can_expose_another` 是否变红）——那是 v7 最重的一处新逻辑，而我只能读出它对，读不出它的测试打不打得到它。

## 十二 · 收尾判断

本轮不触发开发 closeout：评审完成，但 Spec 仍有 1 blocker ＋ 3 major，主体边界未到；本轮没有 source／test 改动、没有提交、没有 worktree 处置，唯一交付物是本报告。采纳与修改由调用方执行。
