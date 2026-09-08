# 直连 Responses 原生透传产品规格独立复评（round 8）

> **落盘位置说明（非正文）**：调用方指定路径是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260831-review-spec-round8.md`，`Write` 被 harness 的 bg-isolation 守卫拒绝（原文见本报告「限制」一节）。按调用方预案落 `/tmp`，请搬运：
>
> `cp /tmp/ghc-review-r8/260831-review-spec-round8.md /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/`

- report_id：`direct-responses-passthrough-spec-review-round8`
- attempt_id：`260831-review-spec-8`
- reviewed_at：2026-08-31
- 被评对象：`.dev/docs/direct-responses-passthrough/spec.md`（DRAFT v8）与同目录 `plan.md`（v7）
- 被评快照：`.dev` HEAD `fbd694b`、主仓 HEAD `7e96adc`、骨架 worktree HEAD `8bd5653`、P3 worktree HEAD `2c93ac6`——**四者本轮全部用 `git` 独立核验过**（`git log --oneline`、`git worktree list`、`git diff --stat`、`git show`），与调用方给出的一致。注意骨架已从 round7 的 `45f538d` 前进到 `8bd5653`
- 评审性质：只读。未修改 `src/`、`tests/`、`spec.md`、`plan.md`；未派 agent；未调用真实上游；未触碰 4141 服务；未 `git worktree add`；未 `EnterWorktree`

## 评审范围

按 `as-reviewer` 的两问分开走：第一问核 round7 十四条的逐条完成度；第二问**抛开那份清单**，重新判 Spec 与 Plan 的当前状态，并按调用方指令**把搜索面主动扩到 `docs/.human-controlled/` 的全部文件**。

**在范围内**：`spec.md` 全文 392 行、`plan.md` 全文 126 行；判据来源为 `docs/.human-controlled/` 的**全部 14 个文件**（含 605 行的 `config.example.yaml`，见第五节）、`.dev/docs/error-envelope/spec.md` §2–§3.5；代码面读了主仓 `sse_source.py` 全文、`stream.py:455-485`、`retry.py:130-150`、`inference.py:395-440`、`direct_driver/base.py:70-196`、`formats/openai_responses.py` 的 id 自铸面，骨架 worktree 的 `openai_responses_passthrough.py` 全文（222 行）与 `8bd5653` 的完整 diff，P3 worktree 对 `sse_source.py` 的完整 diff；跑了主仓的 `tests/unit/pipeline/delivery/test_sse_assembly.py` 与两个直连腿集成测试（52 passed）；对骨架 assembler 与主仓 `parse_frame` 各做了一次 Python 探针；对 WHATWG SSE 规范做了一次原文核对。

**明确不在范围内**：`anthropic-responses-bridge/spec.md` 与 `hosted-web-search-spec.md` 本体（只按引用核一致性）；`ResponsesAssembler` 翻译腿的正确性；P3 那一刀本身的正确性（只核它的存在与形状）；骨架的代码质量（round7 已评，本轮只在它与 Spec 冲突处触碰）；真实上游行为的发生率。

## 总体 verdict

**needs-fix。blocker 1、major 3、minor 5、nit 4（finding_total 13）。**

**round7 十四条：closed 14、partially-closed 0、not-closed 0。** 逐条判据见第一节。v8／plan v7 的自述在这一点上可信，我逐条回到原文核过。

**但「新问题主要由上一轮修复自己带进来」这条规律本轮继续成立，而且这次是最重的那一条。** 调用方点名要审的两处新产品决定里，§7.2 收口第 3 步（「无法归属」事件按 ending 来源二分）的**论据句在字面上说反了**，而它需要的那个推理——「上游终局到达 ⇒ 这些事件不再可能属于某个未闭合 item」——**被同一份 Spec 的 §3 逐字否掉**。我用骨架 assembler 实跑构造出了后果（round8-01）。

**本轮扩大搜索面的收获落在 `config.example.yaml`。** 它 605 行，前七轮里只有 round6 读过其中三行。第 602-605 行有一段用户亲笔注释指出 `@ai-sdk/openai` 校验 item ID 连续性，而 Spec §6.2 在裁定 id 逐字透传时写的是「其他客户端未穷尽」（round8-02）。

---

## 一 · round7 十四条逐条完成度

| finding_id | round7 级别 | 状态 | 判据 |
|---|---:|---|---|
| `round7-01` | blocker | **closed** | `spec.md:323` 已改为事实陈述「用户已经写过一份名单，而本规格此前写着「用户未裁决」——这是错标，v8 更正」，`:325-332` 逐字引用了用户名单，`:334` 写明定义域待裁并登记进 `:370` 的 §11 O-1，`:336`／`:348` 都补上了「除用户黑名单已点名者外」。我逐字回核了 `docs/.human-controlled/message-format-reshape.md:51-57`（用户名单）与 `.dev/docs/error-envelope/spec.md:58`／`:73`（跨腿套用），三处引文与 Spec 的转述一致。**「取交集」这个过渡方案本身有两处过强断言，见 round8-05／round8-12** |
| `round7-02` | major | **closed** | `spec.md:113` 已改写为一句正面规则：「可以构成一个交付单位，但**不得单独交付给客户端**——它随第一批可交付 item 事件一起落地」，`:115` 补了整段说明并点名「发了不算数」这种状态在 §5 里不存在。骨架侧那条错误注释也已在 `8bd5653` 改掉（`test_responses_passthrough.py:122` 现在写的是「The assembler releases it to its caller here; whether it reaches the client is the delivery step's decision」）——`git show 8bd5653` 逐行核过 |
| `round7-03` | major | **closed** | 三处全改：`spec.md:290` ending 表第一行谓词改为「**partition 第一格命中**（仍可 funded replay，**且重开已经成功**）」；`spec.md:137` 的丢弃句补上「**丢弃发生在新流到手之后**（§5.2 的 `OpenedAttempt`），在此之前旧 attempt 的队列**必须保持可提交**」；`spec.md:305` 的 cap 口径补上「replay reset 的时点是「重开成功」而非「判定可 replay」」。引用的实现顺序我实跑核过：`stream.py:468` 是 `replacement = await replay.reopen(torn)`，`:469` 是 `if replacement is not None:`，`:470-472` 才丢——v8 写的 `stream.py:468-472` 准确 |
| `round7-04` | major | **closed** | `spec.md:277` 新增收口第 3 步，`:280-286` 三段说明，`:372` 在 §11 记了闭合与重开条件；§3 侧 `:69` 新增了排除句；骨架侧 `8bd5653` 把 `unfinished` 拆成 `unfinished_items` 与 `unattributed` 并重写了两处 docstring，测试也跟着改。**空白被填上了——但填进去的裁定不成立，见 round8-01；且 §3:69 的交叉引用指错了步号，见 round8-08** |
| `round7-05` | minor | **closed** | `spec.md:187` 已改为「**保留为分类槽位**，但要如实说明它今天是空的……本规格没有点名其余实例，主仓 `_reopen` 也只有 draining 这一条本地前置拒绝（它另一条 `return None` 发生在 `handle` 之后，按定义属 `AttemptFailed`）」。我复核了 `inference.py:395-440`：`return None` 确实只有 `:415`（draining，在 `handle` 之前）与 `:433`（在 `:420` 的 `await handle(...)` 之后）两条，分类正确 |
| `round7-06` | minor | **closed** | `spec.md:175` 的论据已换成不依赖 draining 的那条：「replacement 自己失败与本代理拒绝重开的 **origin 不同**，压成一个 exception 会把前者的上游归因套到后者身上」；`:177` 另起一段说明旧论据为何落空 |
| `round7-07` | minor | **closed** | 取值已搬进权威侧：`spec.md:182` 的 `AttemptFailed` 行现在写着「**origin 为 upstream**——replacement 是一次真实的上游往返，即使失败发生在 transport 层。现有 `FailureOrigin` 只有 `UPSTREAM_EVENT` 与 `PROXY_REFUSAL` 两个值，哪一个承载它属实现问题，归 `plan.md`」；`:270` 的 final source 行仍是纯引用 |
| `round7-08` | minor | **closed** | `spec.md:309` 段首已补整段定义域：「**本节只覆盖成功（2xx）非流式响应。** 上游的非流式**错误**响应按 `error-envelope/spec.md` §3.1 **原始字节透传**，包括其 `Content-Type`（上游答 `text/html` 也照传）」。我回核 `error-envelope/spec.md:71`／`:76`／`:82`，转述准确 |
| `round7-09` | minor | **closed** | `plan.md:119` 已补第六条，写法与 round7 建议一致（正向断言 + 「销毁发生在新流到手之后」） |
| `round7-10` | minor | **closed** | `plan.md:94` 记了接线在后的代价（「三刀无调用者，要到 step 7 才第一次被真实入口执行」）并给出缓解办法；`plan.md:96` 记了第三个选项与它的否决理由 |
| `round7-11` | nit | **closed** | `spec.md:123` 已改为「三份 **Responses 流** cassette」，`spec.md:171` 已改为「**全部五份** cassette」。**同一文档第三处同形句 `spec.md:75` 不在 round7 的点名范围内，仍未加限定，见 round8-11** |
| `round7-12` | nit | **closed** | `spec.md:63` 的基准已改钉到「按 **SSE 规范的 field parsing 算法**得到的 logical `data` 字符串」，`:65` 整段说明为什么钉外部规范才有分辨力；`:92` 的引导句也改成了「第三条不是 writer 而是 **reader**（`parse_frame`）的缺陷」。**但「明确不承诺」那几项没有随新基准重推，见 round8-07** |
| `round7-13` | nit | **closed** | `spec.md:96` 已改为「后半段无论如何都不再构成一个 `data` 字段：没有冒号就被跳过，有冒号则落进一个既非 `event` 也非 `data` 的字段名」，两条路都写了 |
| `round7-14` | nit | **closed** | `plan.md:60` 已改为「映射见 Spec §5.2 的表，**本文件不复制**——与 §5.1 对 header 名单的纪律一致」，转抄消失 |

状态计数：`closed=14`、`partially_closed=0`、`not_closed=0`。

## 二 · 语义槽扫描

在 round7 那张表的基础上做，并补上 v8 新增的事实。判定列只答「这个事实是不是只剩一处当前指令」。

| 事实 | 权威处 | 复述处 | 判定 |
|---|---|---|---|
| 什么算「已提交」 | §5 提交表（`spec.md:129-135`） | §4:113（v8 已改为正面规则）、§7 `block` 行（`:225`）、§7.2 三格（`:257-259`）、§5.1（`:153-155`）、骨架测试注释（`8bd5653` 已改） | 一致 |
| funded replay 时旧 attempt 的去向 | §7.2 partition 第一格（`:257`） | §5:137（已补时点）、§7.2 ending 表第一行（`:290`）、§8:305（已补 reset 时点） | 一致 |
| 未闭合 item 尾巴的丢弃 | §3（`:67`） | §7.2 收口第 1 步（`:274`）、骨架 `unfinished_items` docstring | 一致 |
| **「无法归属」事件的处置** | §7.2 收口第 3 步（`:277`） | §3:69（**指向「第 4 步」，实际是第 3 步**）、§4:119（只说到「持有到 terminal」）、§11:372、骨架 `unattributed` docstring（**把整条规则逐字转抄进代码**）、`plan.md:117`（**仍是 v8 之前的旧规则**）、`plan.md:121` | **有问题**：一处错位引用（round8-08）、一处相反的旧指令（round8-04）、一处代码级转抄 |
| **§7.2 的收口顺序** | §7.2（`:273-278`，四步） | `plan.md:54`（**仍是三步**）、`plan.md:121` | **有问题**：实施者面向的那份指令少一步（round8-03） |
| draining 不得 replay | §5:145（用户亲笔） | §5.1 第三行、§5.2:185、§7.2:261 | 一致 |
| final source 决定末步 carrier | §7.2 final source 表（`:265-271`） | §7.2 收口第 4 步、`plan.md:54` | 一致（plan 只引不抄） |
| native failure code → RetryReason | §5.2 表（`:164-169`） | `plan.md:60`（已改为只引不抄） | 一致 |
| **哪些响应头转发** | §9.1（`:317-354`） | §11 O-1（`:370`，**重复了同一句过强断言**）、`plan.md:66`（只引不抄）、`plan.md:121`（**把裁决前的交集写死成判据**） | **有问题**：round8-05、round8-09 |
| `ReopenRefused`／`AttemptFailed` 的 origin | §5.2 表（`:182-183`） | §7.2:270 | 一致 |
| **§3.1 三处缺陷的实现状态** | `plan.md:15-17` | `spec.md:4`（「已在 worktree 实现，未进 `main`」）、`spec.md:96`（**「未实现」，无限定**） | **有问题**：三处口径不再一致（round8-10） |
| cassette 计数 | 无单一权威 | §3:75（**「三份」，无限定**）、§4:123（已加限定）、§5.2:171（已加限定） | **有问题**：第三处漏改（round8-11） |
| **id 是否逐字透传** | §6.2（`:199-207`） | `plan.md:3` §3（framer 不自铸）、骨架 framer docstring | **有问题**：权威处声称「其他客户端未穷尽」，而用户亲笔文件里已具名一个（round8-02） |
| **cap 的口径（持有 vs 累计）** | §8（`:305`） | `plan.md:40`、`plan.md:109` | **有问题**：权威处只引了用户双语注释的英文半句，中文半句读法相反（round8-06） |

---

## 三 · 本轮发现

### blocker

#### `direct-responses-passthrough-spec-review-round8-01`

- finding_id：`direct-responses-passthrough-spec-review-round8-01`
- severity：`blocker`
- primary_location：`spec.md:277`（§7.2 收口第 3 步）
- related_locations：`spec.md:282`（二分的论据段）、`spec.md:73`（§3「terminal 不能证明一个未知 lifecycle 已经完成」）、`spec.md:69`（§3 的排除句）、`spec.md:119-121`（§4 把两类不同来源的事件并进同一个桶）、`spec.md:284`（触发面）、`spec.md:372`（§11 的闭合声明）；骨架 `openai_responses_passthrough.py:184-194`（`unattributed` 的 docstring 与实现）、`:197-208`（`_item_of`）；`plan.md:121`
- 标题：「上游终局到达 ⇒ 这些事件不再可能属于某个未闭合 item」这个前提被同一份 Spec 的 §3 否掉，据它交付会把一个未闭合 item 的碎片作为孤儿帧发给客户端

**先说论据句本身：它在字面上说的是反话。** `spec.md:282` 逐字：

> 上游给出终局，说明它把整个 response 说完了，此时这些事件**不再有「属于某个还没说完的 item」之外的解释**，交付它们比丢掉它们更接近 §2.1

「不再有 X 之外的解释」＝「唯一的解释就是 X」。代进去读，这句话说的是「唯一的解释就是它属于某个还没说完的 item」——那恰恰是**丢弃**的理由，不是交付的理由。骨架的英文 docstring（`openai_responses_passthrough.py:190`）写对了作者真正想说的那一半：「upstream finished the response, so *"it might be part of something still in flight"* is no longer available as a reason」。所以中文这句是把否定层数写错了一层，两份文档目前对同一条裁定给出方向相反的论据。

**但改正措辞救不了它，因为作者真正想说的那个推理也不成立，而否掉它的正是这份 Spec 自己。** `spec.md:73` 逐字：

> **terminal 不能证明一个未知 lifecycle 已经完成。** `response.failed` 恰是反例：它只说明 response 结束了，不说明某个没收到 `done` 的 item 变完整了。

一个 item 收到了 `added` 却没收到 `done`，上游终局到达之后它**仍然**是未闭合的——§3 就是这么裁的，而且据此要求丢掉它的尾巴。既然如此，「它可能属于某个还没说完的 item」这个解释在终局之后**依然可用**，第 3 步赖以成立的那半句谓词是假的。

**根因在 §4 把两类语义完全不同的事件并进了同一个桶。** `spec.md:119-121` 定义「无法归属」时列了两类来源：

1. **本来就不属于任何 item** 的事件——`openai==3.3.1` 的四个 audio 事件，「既无 `output_index` 也无 `item_id`」；
2. **属于某个 item、但本代理没读出归属**的事件——同段末尾一句「payload 解不开时也落在这里」。

对第 1 类，终局到达时交付它们完全正确，也不会产生坏帧。对第 2 类，它按构造就属于某个 item，而那个 item 可能正好是未闭合的那个。**ending 的来源这根轴不区分这两类**，于是第 2 类继承了为第 1 类写的理由。

**实跑证据。** 我用骨架 worktree 的 assembler 加主仓的 `parse_frame` 跑了一条完整的 wire（`PYTHONDONTWRITEBYTECODE=1`，未在任何 worktree 留下文件），事件依次是 `response.created` → `output_item.added(index 0)` → `output_text.delta(index 0)` → `output_item.done(index 0，item 文本里含一个裸 U+2028)` → `response.completed`。输出：

```
== unfinished_items（第 1 步：每一种 ending 都丢） ==
   response.output_item.added | {"output_index":0,"item":{"id":"i1","type":"message"}}
   response.output_text.delta | {"output_index":0,"delta":"hel"}
== unattributed（第 3 步：上游终局时逐字交付） ==
   response.output_item.done | '{"output_index":0,"item":{"id":"i2","type":"message","content":[{"type":"output_text","text":"he'
== 客户端会看到的序列 ==
   response.created       -> parses
   response.output_item.done -> NOT JSON (JSONDecodeError)
   response.completed     -> parses
```

链条每一环都在 Spec 自己的文本里：`parse_frame` 用 `splitlines()` 在 U+2028 处截断（§3.1 第三条）→ 截断后的 payload 不是合法 JSON → `SseEvent.json()` 返回 `{}`（`sse_source.py:30-38`，我逐行读过）→ 没有 `output_index`，落进「无法归属」→ 与此同时 index 0 **永远不会被关闭**，因为关闭它的正是这个读不出 `output_index` 的 `done` 事件 → 收口时第 1 步丢掉 item 0 的 `added` 与 `delta`，第 3 步把这个 `done` 逐字发出去。

**客户端拿到的是两种坏帧叠在一起**：一个没有 `output_item.added` 与之配对的 `response.output_item.done`（协议层面的孤儿），且它的 `data` 不是合法 JSON（任何按 `ResponseOutputItemDoneEvent` 解析的客户端会直接抛）。

**§11 的重开条件已经被满足了。** `spec.md:372` 写「若将来出现上游样本表明交付它们会产生坏帧，须重开」——上面这个坏帧**不需要任何上游样本**，构造即可，而且骨架自己的测试 `test_an_unattributable_event_is_reported_apart_from_an_unclosed_tail` 就是在「有一个 item 开着」的状态下断言两个集合非空的，即它已经把这个共存状态钉成了正例。

**触发面分四层，请分开读**：

| 路径 | 权重 |
|---|---|
| U+2028／U+2029／U+0085 截断 payload | **今天在 `main` 上是活的**（`parse_frame` 仍是 `splitlines()`，我实跑确认）。P3 落地后这条关上——但 P3 正是这份 Spec §3.1 强制要求的修复，而 `spec.md:284` 恰恰把这条路径当作「不依赖任何未观测的上游行为」的主论据。**论据与它自己要求的修复互相抵消** |
| 上游发出非 JSON object 的 payload | 机制确定（`SseEvent.json()` 对非 object 也返回 `{}`），触发未测 |
| 四个 audio 事件 | 机制确定，触发未证实。**这一类交付是对的，不产生坏帧** |
| 将来新增的、携带 `item_id` 而不携带 `output_index` 的 item 专有事件 | 机制确定，是否出现取决于上游演进。**这一类正是本腿存在的理由**（§6.1「以及任何未来新增的」），而它一旦出现就会被 `_item_of` 判为无法归属，然后按第 3 步孤儿交付 |

**影响。** 三层：

1. **行为**。上游终局 + 存在未闭合 item 时，客户端收到孤儿帧（可能还是非法 JSON）。这与 §4「一个 item 的事件不得跨越释放边界」在同一件事上给相反答案——v7 花了一整条 major 才把「半个 group 出门」堵住，v8 的第 3 步在 ending 处重新开了一个口。
2. **权威**。§11 已据此关闭了一项，`plan.md:121` 已把它写成 v8 的验收正向断言。不重开的话，这条裁定往后每一轮都会被当作已决事项跳过。
3. **实现**。骨架 `8bd5653` 已把这条规则逐字写进 `unattributed` 的 docstring（「On an **upstream terminal** they are submitted verbatim in order」），这是一份代码里的 Spec 转抄；改 Spec 就必须同刀改它。

**建议。** 换掉那根轴：**判据不是 ending 的来源，而是这个事件有没有可能属于一个已知未闭合的 item。** 一个可执行的写法（属 §2.3 推导，但触到 §2.1 的边，是否要顺带升级给用户由调用方定）：

> 3. **无法归属的事件**（§4）：若收口时刻**没有任何已打开而未闭合的 item**，则与上一步一并按原序逐字提交——此时不存在「它属于某个还没说完的 item」这个解释，丢弃它就成了以本代理判不出归属为由拒绝一个协议合法的事件（§2.1）。若**存在**未闭合 item，则与未闭合尾巴同样丢弃——此时该解释仍然可用，而 §3 已裁定这类碎片一律不交付。**代理侧 ending（tear、EOF、cap、deadline、拒绝）一律丢弃**，理由不变。

这个谓词有分辨力：四个 audio 事件在一条正常结束的响应里会被交付（没有未闭合 item），而截断的 `done` 与它拖住的那个 item 一起被丢掉。它也不与 §2.1 相反——拒绝的理由从「判不出它属于谁」换成了「不能排除它属于一个我们已知没说完的 item」，而后一个理由 §3 已经用过一次并被接受。

同刀要改的：`spec.md:69`（§3 的排除句，顺带修 round8-08 的步号）、`spec.md:282`（那句说反的论据）、`spec.md:284`（把「不依赖任何未观测的上游行为」限定到 P3 落地之前）、`spec.md:372`（§11 的闭合声明改为重开）、`plan.md:121`（验收判据）、骨架 `openai_responses_passthrough.py:184-194` 的 docstring 与对应测试。

**证据强度：机制强到可以据此行动**——Spec 三处逐字自相矛盾（`:73` 对 `:282`）、一次一手实跑（骨架 assembler + 主仓 `parse_frame`，输出逐字贴在上面）、骨架自己的测试构造了同一共存状态。**四条触发路径的权重各不相同，已在上表逐条标注**，其中最强的一条会随 P3 落地而关闭，这一点我明确写下来，不拿它冒充长期风险；支撑本条的是「谓词本身为假」加上「未来未知事件类型这条路径不会关闭」。

---

### major

#### `direct-responses-passthrough-spec-review-round8-02`

- finding_id：`direct-responses-passthrough-spec-review-round8-02`
- severity：`major`
- primary_location：`spec.md:205`（§6.2「其他客户端未穷尽，不外推为全生态安全」）
- related_locations：`spec.md:207`（`fix_stream_ids` 的将来出口）、`spec.md:201-203`；`docs/.human-controlled/config.example.yaml:602-605`；`src/app/pipeline/delivery/formats/openai_responses.py:126-127`（`_item_id`）；`.dev/docs/direct-responses-passthrough/reports/260830-review-spec.md:195`（同一句话的最早出处）
- 标题：Spec 说「其他客户端未穷尽」，而用户在自己的配置样例里已经具名写下一个校验 ID 连续性的客户端；本腿改 native 等于撤掉今天 framer 提供的稳定 id，而没有任何文档登记这项回归

**用户亲笔的原文。** `docs/.human-controlled/config.example.yaml:602-605`：

```yaml
# hook_fix_responses_sse:
#   # 修复上游流在 `output_item.added` / `output_item.done` 间不一致的 item ID。`@ai-sdk/openai` 校验 ID 连续性需要。
#   # Fix inconsistent item IDs across `output_item.added` / `output_item.done` events from Copilot's upstream stream. Required by `@ai-sdk/openai` which validates ID continuity.
#   fix_stream_ids: true
```

**Spec 的当前陈述。** `spec.md:205`：

> 复核：`openai==3.3.1` 的 accumulator 按 `output_index` 累积、不校验 id 相等，所以「SDK 需要稳定 id」在该版本上被排除；**其他客户端未穷尽，不外推为全生态安全。**

这句话本身不假——它没有说「用户未裁决」，措辞也是诚实的对冲。**问题在于被对冲掉的那件事已经有一个具名实例，而实例就写在用户自己的文件里。** 「未穷尽」读起来像「我们不知道有没有」，实际状态是「已知有一个，名字是 `@ai-sdk/openai`，理由是它校验 ID 连续性」。这两句给读者的行动指引完全不同。

**回归是具体的，不是假想的。** 今天的直连 Responses 腿由 `ResponsesFramer` 成帧，`openai_responses.py:126-127`：

```python
def _item_id(self, prefix: str) -> str:
    return f"{prefix}_{self._response_id}_{self._output_index}"
```

同一个 item 的 `added` 与 `done` 走同一个 `_output_index`，因此**今天客户端拿到的 id 是连续的**。本腿改 native 之后，客户端拿到的是上游那份实测 12/12、16/16、125/125 全不相同的 id。也就是说：一个用 `@ai-sdk/openai` 的 Responses 客户端，今天在这条腿上能跑，透传落地后会被它自己的 ID 连续性校验拒掉。

**这不是「用户已裁决要修 id」。** 那段配置是注释掉的，和它上面的 `hook_fix_responses_request` 一样属于用户写下的候选项，不是已启用的裁决。我不主张 Spec 必须改成 mint id——`spec.md:207` 给的出路（「另立显式、可选的 reshape 合同，不得叫它 native 或逐字」）在方向上与用户那段注释是一致的，因为那段注释本身就是一个 opt-in 开关的形状。

**要改的是三件事，都不需要用户点头：**

1. `spec.md:205` 把「其他客户端未穷尽」换成事实陈述：用户在 `config.example.yaml:602-605` 具名记录了 `@ai-sdk/openai` 校验 ID 连续性，因此已知**至少有一类客户端**会因 native id 而失败；`openai==3.3.1` 仍然不受影响。
2. `spec.md:207` 补上：这项 reshape 在本腿**不是纯粹的将来事项**，因为本腿落地即撤掉今天 framer 提供的稳定 id，**对已知的那一类客户端是回归**。
3. 登记进 §11 或 `deferred.md`：本腿是否需要在启用透传的同一刀里提供 `fix_stream_ids` 这个 opt-in，属产品分叉，按 `no-silently-cut-but-defer` 不应被静默略过。

**为什么是 major 而不是 blocker。** Spec 的方向（native 为默认、reshape 另立 opt-in）与用户那段注释不冲突，落地也不会立刻产生坏帧——受影响的是一类今天能跑、之后跑不了的客户端。它需要在 §11 立项、在 §6.2 更正陈述，但不需要推翻任何已有裁定。

**证据强度：强到可以据此行动。** 用户原文逐字读过全文（不是检索命中的一行）；`_item_id` 的实现我逐行读过；「本项目内零引用」是实跑 `rg -n 'fix_stream_ids|ai-sdk' src/ tests/` 得到空集、`rg` 整个 topic 目录只命中 `spec.md:207` 一处（那一处不含 `@ai-sdk/openai`）。**未核的一项**：`@ai-sdk/openai` 具体在哪个版本、以何种方式校验连续性，我没有它的源码，采纳的是用户的陈述。

---

#### `direct-responses-passthrough-spec-review-round8-03`

- finding_id：`direct-responses-passthrough-spec-review-round8-03`
- severity：`major`
- primary_location：`plan.md:54`
- related_locations：`spec.md:273-278`（§7.2 的四步收口）、`plan.md:87`（顺序表第 6 步）、`plan.md:121`
- 标题：§7.2 的收口顺序在 v8 变成四步，而 plan 里那条面向实施者的复述仍然是三步，漏掉的正是 v8 新增的那一步

`plan.md:54` 逐字：

> 真正进入收口时：丢未闭合 suffix → 按原序提交已完成 group → 末步的 carrier **按 §7.2 的 final source 表**（有上游终局就逐字提交它，没有才写 proxy error）。

`spec.md:273-278` 现在是四步：丢未闭合 suffix → 按原序提交 control 与已完成 group → **无法归属的事件按 ending 来源处置** → 提交 terminal 或 proxy error。

`plan.md:54` 属于 plan §4，也就是**顺序表第 6 步（`plan.md:87`）的实施说明**——一个实施 §7.2 的人读的就是这一段。它现在给出的是 v8 之前的那份三步指令，而按三步实施的结果恰好是 round7-04 点名的那个缺陷：无法归属的事件在收口处没有归宿，被静默丢掉。

**这是「缺席读不出来」的标准形状**：少一步与「本来就没有这一步」在文本上完全同形，没有任何东西会红。`plan.md:121` 的 v8 验收清单里确实有一条对应判据，但那是**验收**，不是**指令**；而 `plan.md:5` 声明「凡本文与 Spec 冲突，以 Spec 为准」也救不了它，因为漏写不构成冲突。

**建议。** `plan.md:54` 的复述补上第三步，或者更彻底一点：既然 §7.2 已经把顺序写成编号清单，plan 这里改成纯引用（「收口顺序照 Spec §7.2 的四步执行，本文件不复制」），与同文件 §5、§5.1 已经采纳的「不复制」纪律一致——那条纪律正是 round7-14 的产物。**注意本条的最终文字取决于 round8-01 的处置**：若第 3 步的谓词按 round8-01 修改，这里要同刀跟上。

**证据强度：强**（两处逐字对读，plan 的自我定位由 `plan.md:87` 与 `plan.md:5` 逐字确定）。

---

#### `direct-responses-passthrough-spec-review-round8-04`

- finding_id：`direct-responses-passthrough-spec-review-round8-04`
- severity：`major`
- primary_location：`plan.md:117`（v7 验收清单第三条）
- related_locations：`plan.md:121`（v8 验收清单第一条）、`spec.md:277`；骨架 `test_responses_passthrough.py:222-238`
- 标题：plan 的 v7 验收清单说无法归属的事件「进入未闭合尾巴」，v8 清单说它在上游终局时「仍在交付里」，两条判据在同一份清单里对同一个构造给相反答案

`plan.md:117`（v7 组）逐字：

> **「无法归属」与「envelope」处置相反**（拿一个不带 `output_index` 的 audio 事件构造，断言它被持有且**进入未闭合尾巴**）

`plan.md:121`（v8 组）逐字：

> **无法归属的事件按 ending 来源二分**（上游终局到达时，一个不带 `output_index` 的事件**仍在**交付里——正向断言；代理侧 ending 时不在）

同一个构造（不带 `output_index` 的 audio 事件），一条要求断言它在未闭合尾巴里（也就是会被丢），另一条要求断言它在交付里。**v8 的 §7.2 第 3 步把这两件事拆开了，v7 那条却没跟着改。**

**代码侧已经站在 v8 那边，v7 那条判据现在是可证伪的假命题。** 骨架 `8bd5653` 把 `unfinished` 拆成两个属性，对应测试现在断言的是：

```python
assert [e.event for e in assembler.unattributed] == ["response.audio.delta"]
assert assembler.unfinished_items == ()
```

也就是说，照 `plan.md:117` 的字面写出来的那条断言，在当前骨架上必然为假。

**这不是纯粹的红／绿问题。** 一个实施者遇到两条相反的判据，同样可能选择去改实现来满足先读到的那一条——而 v7 那条排在前面。

**建议。** `plan.md:117` 的括号内容改成只保留仍然成立的那一半：「断言它被**持有**而不是随 envelope 释放，且它与未闭合尾巴**分列两个集合**」；把 ending 处的去向整个交给 v8 那条。属 plan 自己的记录，评审共识即可改。

**证据强度：强**（同一文件两条判据逐字对读，加骨架 `git show 8bd5653` 的实际断言）。

---

### minor

#### `direct-responses-passthrough-spec-review-round8-05`

- finding_id：`direct-responses-passthrough-spec-review-round8-05`
- severity：`minor`
- primary_location：`spec.md:336`（「落地后不与任一份权威相反。差异只在 `Date`／`Cache-Control`／`Set-Cookie` 三项」）
- related_locations：`spec.md:370`（§11 O-1 重复同一断言）、`spec.md:340-347`（语义判据）、`docs/.human-controlled/message-format-reshape.md:11`（黑名单机制的定义）、`:53-57`
- 标题：「剥离集取并集」在剥离方向确实保守，但「不与任一权威相反」与「差异只在三项」是两句过强的断言——并集会剥掉用户名单没点名的头，而黑名单的语义蕴含「未点名者转发」

**用户把它明确称为黑名单，而黑名单是有语义的。** `message-format-reshape.md:11` 在同一份文件里给请求头写下机制：「一般地，**直连路径上**，客户端请求头值得原样转发给上游，**仅部分请求头是需要剥离的，即采用黑名单机制**」。响应头那一节（`:53-57`）用的是同一个词。黑名单的含义是**只剥这些，其余转发**——所以它不只规定了剥离集，也蕴含了转发集。

**并集因此会在另一个方向上偏离那份名单。** §9.1 的语义判据要求剥离的头里，用户名单**没有点名**的至少有：strong `ETag`、`Content-Digest`、`Digest`、`Repr-Digest`、`Content-Range`、`Content-MD5`（`spec.md:343` 自己列的例子，且明说「这是例子不是穷举」）。按黑名单读法，这些头应当转发；按 §9.1 读法，它们必须剥离。所以：

- 「**落地后不与任一份权威相反**」不成立——它在剥离方向不与用户名单相反，在转发方向相反。
- 「**差异只在 `Date`／`Cache-Control`／`Set-Cookie` 三项**」也不成立，那只是「用户名单要剥而 §9.1 会转发」这一侧的差异；反向那一侧的差异至少还有上面六个，而且按 §9.1 自己的说法这一侧**必然漏**，数不完。

**逐跳那一族不在差异里，因为用户名单里有一个类别标记。** 名单第一行是「`Connection` `Keep-Alive` `Proxy-Connection` `Hop-By-Hop`」——`Hop-By-Hop` 不是一个真实的头名，它是用户在写「以及逐跳的那些」。所以 `TE`／`Trailer`／`Upgrade`／`Proxy-Authenticate`／`Proxy-Authorization` 被这个类别覆盖，§9.1 剥它们不构成偏离。这一点也值得在 §9.1 引用名单时点破（见 round8-12）。

**影响主要落在 §11 那条待裁项的质量上。** 用户读 O-1 时被告知「差异仅三项」，于是无论他裁「适用」还是「不适用」，那六个 validator／digest 头的去留都不在他视野里；而若他裁「适用」，Spec 会继续剥离用户名单没点名的头，且 §9.1 已经声明这不与任何权威相反，没有人会回头再看。这属于 `as-pending-decisions-checker` 关心的那一类：**上桌的问题没有把真实的分叉面描述完整。**

**建议。** 两处一起改：

1. `spec.md:336` 改为：「取并集在**剥离方向**保守，落地后不会转发用户名单点名要剥的任何头。但黑名单蕴含「未点名者转发」，因此并集在**转发方向**确实偏离该名单——`spec.md:343` 的语义判据会剥掉名单没有点名的 strong `ETag`／`Content-Digest`／`Content-Range`／`Content-MD5` 一族。这一侧的偏离是有理由的（本代理已经重新成帧或重新序列化，那些字段不再为真），但它是**本规格的推导**，不是名单授权的。」
2. `spec.md:370` 的 O-1 现状列同步，把差异写成两侧而不是一侧。

**证据强度：强**（用户原文逐字读过全文，「黑名单机制」是用户自己在同一份文件里下的定义；差异清单来自 §9.1 自己列的例子）。**这一条不主张改行为**——语义判据我认为是对的，要改的是对它的描述与上交给用户的那份分叉面。

---

#### `direct-responses-passthrough-spec-review-round8-06`

- finding_id：`direct-responses-passthrough-spec-review-round8-06`
- severity：`minor`
- primary_location：`spec.md:305`（§8 memory cap）
- related_locations：`docs/.human-controlled/config.example.yaml:391-393`；`spec.md:391`（v2 的修订记录称「cap 口径已有确证」）
- 标题：§8 说 cap 的「用户亲笔定义」是那句英文，而用户那条注释是双语的，中文半句写的是「累计缓冲」——被引用的只是支持结论的那一半

`spec.md:305` 逐字：

> `buffer_cap_bytes` 的用户亲笔定义是「max bytes to buffer before abandoning this response」，故**限制的是本代理当前持有的字节，不是累计交付量**。

用户的注释是两行，`config.example.yaml:391-392`：

```yaml
  # 缓冲路径内存守卫：累计缓冲超此字节即放弃该响应。0 = 无限制。默认 16MiB。
  # Buffered-path memory guard: max bytes to buffer before ABANDONING this response. 0 = unlimited. Default 16MiB.
```

**中文那半句写的是「累计缓冲超此字节即放弃该响应」。** 「累计缓冲」有两种读法：一是「累计起来的缓冲量」（即当前持有），二是「累计缓冲过的字节」（即随时间累加）。第二种读法与 §8 的裁定相反：在 `block` 下一路交付、从不同时持有超过几百 KB 的一次长响应，按第一种读法永远不触 cap，按第二种读法可能触。

**Spec 只引了英文那半句，并称它是「用户亲笔定义」。** 英文半句确实支持「当前持有」这一读；但它不是用户写的全部，而被略掉的那半句恰好是可能给出相反答案的那半句。这是「转述会丢掉原文的限定成分」的标准形状。

**round6 读过这几行**（`260831-review-spec-round6.md:312` 逐字写着「`config.example.yaml:391-393`（`buffer_cap_bytes` 定义）——**四处均逐字比对过**」），中文那半句仍然没有进 Spec；round1 的报告（`260830-review-spec.md:131`）也只引了英文。所以这不是某一轮的疏忽，是这条引文从一开始就只取了一半，而 §11 在 v2 就以「cap 口径已有确证」把它关闭了。

**我不主张改结论。** 「当前持有」这个读法与 `BufferCapExceeded` 的「guard bounds memory」自述、与「abandoning this response」的语气都更一致，而且它是两种读法里唯一能让 `full` policy 有意义的那个（按累计读法，`full` 与 `block` 的 cap 行为就没有区别了）。要改的是**如实陈述它是本规格在用户双语注释两读之间做的选择**，而不是把它写成用户的定义本身。

**建议。** `spec.md:305` 改为：「`buffer_cap_bytes` 的用户注释是双语的，英文半句是「max bytes to buffer before abandoning this response」，中文半句是「累计缓冲超此字节即放弃该响应」；后者可读成随时间累加。**本规格取「当前持有」这一读**（§2.3 推导），理由是……若用户裁定取累计读法，本节与 §7.2 的 `full` 行为都要重估。」是否顺带升级给用户由调用方定；我倾向不必，因为累计读法会让 `full` policy 失去意义，这本身是很强的反证。

**证据强度：强**（用户原文逐字，两轮历史报告的引用面逐字核过）。**影响**：文档权威归属；行为差异只在「累计读法为真」的前提下才发生，而我判断那个前提大概率不成立。

---

#### `direct-responses-passthrough-spec-review-round8-07`

- finding_id：`direct-responses-passthrough-spec-review-round8-07`
- severity：`minor`
- primary_location：`spec.md:65`（「下面「明确不承诺」的四项里有三项描述的是本项目 parser 的现有行为而非规范要求」）
- related_locations：`spec.md:84-88`（那份清单，实际是五条）、`spec.md:63`（新基准）
- 标题：§3 的基准改钉到 SSE 规范之后，「明确不承诺」那份清单没有随之重推——计数是四但有五条，其中两条在新基准下其实是**规范一致**而非偏离

**计数对不上。** `spec.md:84-88` 是五个 bullet：不是 byte-level／注释行与 `id:`／`retry:`／只有 `event:` 无 `data:` 的帧／非法 UTF-8／field 前后空白与行尾的规范化。`:65` 说「四项」。

**更实质的是分类。** 我按 WHATWG SSE 规范原文核过两条（`https://html.spec.whatwg.org/multipage/server-sent-events.html`，本轮实取）：

- 「**只有 `event:` 而无任何 `data:` 的帧：`parse_frame` 返回 `None`，不重放**」——规范的 dispatch 步骤逐字是「If the data buffer is an empty string, set the data buffer and the event type buffer to the empty string and **return**」，即**这种帧本来就不派发任何事件**。所以 `parse_frame` 返回 `None` 是**符合**新钉的基准，不是相对它的欠缺。我实跑确认了这个行为（`parse_frame(b"event: x")` → `None`）。
- 「**非法 UTF-8：`errors='replace'` 已替换为 `�`**」——规范逐字是「Streams must be decoded using the **UTF-8 decode** algorithm」，而 UTF-8 decode 的错误模式就是 replacement。所以这一条同样是**符合**基准。

于是新基准下，这五条的真实身份是：一条是承诺范围的声明（不是 byte-level），一条是落在承诺面之外的真实取舍（注释行与 `id:`／`retry:` 不重放——`id:` 影响客户端的 `Last-Event-ID`，是真的损失，只是本承诺只覆盖 event 名与 data），两条是**基准一致**，一条（前后空白与行尾规范化）描述的正是基准算法自己做的事。

**为什么值得写下来。** `:65` 把它们统称为「本项目 parser 的现有行为**而非规范要求**」，一个读者据此去「让 parser 更贴近规范」，最可能动的就是那两条已经符合规范的——比如把 `errors='replace'` 改成 `errors='strict'` 并抛错，那才是真的偏离。这与 round7-05 是同一形状：**一个正确的清单配一句把它归错类的说明**。

**建议。** `spec.md:65` 改为按新基准逐条重述，例如：「下面五项里，第 1 项是承诺范围的声明；第 2 项落在本承诺覆盖面之外（`id:` 不重放会影响客户端的 `Last-Event-ID`，这是真实取舍）；第 3、4 项在新基准下**是规范一致**（规范规定空 data buffer 不派发事件、规定用 UTF-8 decode），列在这里只为读者不必自己去查；第 5 项描述的是基准算法自身的规范化。」

**证据强度：强**（规范原文本轮实取并逐字引用；`parse_frame` 的两个行为实跑确认；bullet 计数直接可数）。**影响**：判据的可读性与后续改动的方向，无当前行为后果。

---

#### `direct-responses-passthrough-spec-review-round8-08`

- finding_id：`direct-responses-passthrough-spec-review-round8-08`
- severity：`minor`
- primary_location：`spec.md:69`
- related_locations：`spec.md:63`（§3 承诺的覆盖面）、`spec.md:277`（实际是第 3 步）、`spec.md:280`、`spec.md:372`
- 标题：§3 的排除句把读者指向「§7.2 收口第 4 步」，而那一步是提交 terminal／error；真正的裁定在第 3 步。同时 §3 的承诺面没有随之扩展

**两处，同一次编辑造成。**

**其一，步号错位。** `spec.md:69` 逐字：「**「无法归属」的事件不属于上面这条，它有自己的裁定，见 §7.2 收口第 4 步。**」而 `spec.md:277` 是第 3 步，`spec.md:280` 与 `spec.md:372` 都自称「第 3 步」。按 `:69` 跳过去的读者落在「提交上游 terminal／failure（若有），否则提交 proxy error」上，那里一个字都没提无法归属的事件——最可能的反应是「Spec 说有裁定，但那里没有」。成因看得出来：round7 的建议文本是接在原三步之后编号为 4 的，v8 采纳时把它插成了第 3 步，`:69` 的引用抄的是建议稿的编号。

**其二，承诺面没跟上。** `spec.md:63` 的承诺仍然只覆盖「凡属于一个**已完成的 item group**、或属于 control 与 terminal／failure 的 SSE 事件」。无法归属的事件三类都不是，而 §7.2 第 3 步现在要求在上游终局时**逐字提交**它们。于是 Spec 出现了一处「在 §7.2 承诺逐字、在 §3 不承诺」的缝——round7-04 的建议里「并在 §3 的承诺面上同步」这半句没有落实。`:69` 那句排除只是说明它「另有裁定」，没有把它纳入保真承诺。

**建议。** 一次编辑改两处：`:69` 的步号改为「第 3 步」；`:63` 的承诺面补上「以及按 §7.2 第 3 步被提交的无法归属事件」。**注意本条的最终文字取决于 round8-01 的处置。**

**证据强度：强**（三处逐字对读，编号可数）。

---

#### `direct-responses-passthrough-spec-review-round8-09`

- finding_id：`direct-responses-passthrough-spec-review-round8-09`
- severity：`minor`
- primary_location：`plan.md:121`（v8 验收清单第三条，「响应头取交集」）
- related_locations：`plan.md:66`（同文件的「本文件不复制名单」纪律）、`spec.md:336`、`spec.md:370`（§11 O-1）
- 标题：v8 验收把裁决前的交集写成三个具名头的固定判据，没有标注它会随 §11 O-1 的裁决翻转

`plan.md:121` 逐字：

> **响应头取交集**（`Date`／`Cache-Control`／`Set-Cookie` 不在输出里，而 weak `ETag`／`Last-Modified` 在——两个方向同一条判据里各测一次）

前半句是**过渡状态**的判据。§11 O-1 一旦裁「该名单不覆盖 Responses 客户端的直连腿」，正确行为就变成转发这三个头，这条判据要整个反过来。而 plan 里没有任何字标注这一点。

**失效方式是静默的。** 判据先落地 → 实现照它写 → 用户裁「不适用」→ 实现没改，测试仍绿，Spec §9.1 的「其余一律转发」被一条过时判据钉住。这正是项目规则里「a stale transcription keeps its tests **green** while it does」点名的形状。后半句（weak `ETag`／`Last-Modified` 仍在）不受裁决影响，是稳定的。

**顺带一处纪律不一致。** 同文件 `plan.md:66` 对 header 写的是「**判据在 Spec，本文件不复制名单**，因为名单必漏」，而 `:121` 复制了三个头名。这一处我不主张删——验收判据必须具名才可执行，与 §5.1 拒绝转抄**映射表**不是同一回事。要补的只是它的条件性。

**建议。** `plan.md:121` 那半句改为：「**响应头取交集**——`Date`／`Cache-Control`／`Set-Cookie` 不在输出里。**这条判据的方向取决于 Spec §11 O-1，用户裁「名单不覆盖本腿」时须整条反转**；weak `ETag`／`Last-Modified` 在输出里，这一半与裁决无关。」

**证据强度：强**（plan 两处与 spec §11 逐字对读）。

---

### nit

#### `direct-responses-passthrough-spec-review-round8-10`

- finding_id：`direct-responses-passthrough-spec-review-round8-10`
- severity：`nit`
- primary_location：`spec.md:96`（§3.1 第三条「**未实现。**」）
- related_locations：`spec.md:4`（文首）、`plan.md:17`
- 标题：P3 的状态在三处不再同口径——文首与 plan 说「已在 worktree 实现，未进 `main`」，§3.1 第三条仍是无限定的「未实现」

`spec.md:4`：「第三处（`parse_frame` 的行拆分）**已在 worktree `260831-sse-line-endings` 实现，未进 `main`**」。`plan.md:17`：「**已实现，未进 `main`**（`worktree-260831-sse-line-endings`，`2c93ac6`）」。`spec.md:96`：「3. **未实现。**」

对 `main` 而言「未实现」为真，但它没有限定语，而前两处都限定了。round6-07 关闭时的判据正是「与文首和 `plan.md:13-18` 三处口径一致」，这次同步只做了两处。我核过 P3 worktree 的 `git diff 7e96adc..2c93ac6`：`_LINE_ENDING = re.compile(r"\r\n|\r|\n")` 与 `parse_frame` 改用 `re.split` 都在，`plan.md:17` 的转述准确。

**建议。** `spec.md:96` 改为「**未进 `main`**（已在 worktree `260831-sse-line-endings` 实现，`2c93ac6`）」。`plan.md:17` 已经写了「合入 `main` 后须同步 `spec.md` 文首与 §3.1 第三条」，这一条正是那份同步清单里的一项，只是它在 worktree 落地时就该走一次。

**证据强度：强**（三处逐字，`git diff` 实跑核过）。

---

#### `direct-responses-passthrough-spec-review-round8-11`

- finding_id：`direct-responses-passthrough-spec-review-round8-11`
- severity：`nit`
- primary_location：`spec.md:75`
- related_locations：`spec.md:123`、`spec.md:171`
- 标题：round7-11 修了两处 cassette 计数，同一文档第三处同形句仍未加限定

`spec.md:75`：「**三份 cassette** 的 sequence 均为 `0..N-1`」。round7-11 点名的是当时的 `:117` 与 `:165`（今 `:123`、`:171`），两处都改了；`:75` 不在点名范围内，所以没被扫到。`tests/int/cassettes/` 下共 5 个文件，带 Responses 事件流的是 3 个，因此「三份」在这里指的也是 Responses 流那三份。

**建议。** 改为「三份 Responses 流 cassette」，与 `:123` 同措辞。

**证据强度：强**（三处逐字对读；集合大小沿用 skeleton 评审的全量核对，本轮未重新清点文件）。

---

#### `direct-responses-passthrough-spec-review-round8-12`

- finding_id：`direct-responses-passthrough-spec-review-round8-12`
- severity：`nit`
- primary_location：`spec.md:334`（「与本规格 §2.4 的定义域完全相同」）
- related_locations：`spec.md:5`（本规格定义域）、`spec.md:328`（引用用户名单的第一行）；`.dev/docs/error-envelope/spec.md:58`
- 标题：两处引用不精确——error-envelope 的直连定义域是本规格的**超集**而非「完全相同」；用户名单里的 `Hop-By-Hop` 是类别标记不是头名

**其一。** `spec.md:5` 把本规格定义域钉为「**inbound 与 target 同为 `openai-responses`**（`route.translation_required is False`）」——两个条件。`error-envelope/spec.md:58` 的键只有一个：「**直连路径**（`Route.translation_required` 为 False）」，它同样覆盖 Anthropic 直连、chat-completions 直连、embeddings 直连。所以是**超集**关系，不是相同。

**结论不受影响，反而更稳**：超集当然包含本腿，所以「error-envelope 已经把用户名单套用到本腿」照样成立。写下来只因为这是「一个正确的结论配一个不准确的理由」，而下一个核到理由为假的人可能连结论一起推翻。round7 的报告里也有同一句（「恰好就是本规格 §5 定义的定义域」），所以这是继承来的，不是 v8 新引入的。

**其二。** `spec.md:328` 逐字引用用户名单第一行「`Connection` `Keep-Alive` `Proxy-Connection` `Hop-By-Hop`」而未加说明。`Hop-By-Hop` 不是一个 HTTP 头的名字，它是用户在写「以及逐跳的那一族」。不点破的话，一个照字面实施的人会去匹配一个名叫 `Hop-By-Hop` 的头（无害但无用），并以为 `TE`／`Trailer`／`Upgrade`／`Proxy-Authenticate`／`Proxy-Authorization` 不在用户名单里——而它们其实被这个类别覆盖，这直接影响 round8-05 里「差异有多大」的算法。

**建议。** `spec.md:334` 改「完全相同」为「其直连定义域是本规格定义域的**超集**（它只键在 `translation_required`，不要求两端同为 `openai-responses`），因此本腿被它覆盖」。`spec.md:328` 引文后加一句括注：「名单第一行的 `Hop-By-Hop` 是类别标记而非头名，逐跳那一族因此已被用户名单覆盖。」

**证据强度：强**（三份文档逐字对读；`error-envelope/spec.md:58` 本轮实取）。

---

#### `direct-responses-passthrough-spec-review-round8-13`

- finding_id：`direct-responses-passthrough-spec-review-round8-13`
- severity：`nit`
- primary_location：`spec.md:84-88`（「明确不承诺」清单）
- related_locations：`spec.md:63`（新基准）；`src/app/pipeline/delivery/sse_source.py:48-50`
- 标题：基准改钉到 SSE 规范之后新出现一处未登记的偏差——不含冒号的 `data` 行，规范要求当成空值的 `data` 字段，`parse_frame` 直接跳过

规范逐字：「Otherwise, the string is not empty but does not contain a U+003A COLON character: Process the field using the whole line as the field name, and the empty string as the field value.」也就是一行裸的 `data`（无冒号）应当往 data buffer 里追加一个空行。`sse_source.py:48-50` 的 `if not separator: continue` 把它跳过了。

实跑（主仓 `parse_frame`）：

```
b"event: x\ndata: a\ndata\ndata: b"   -> data='a\nb'     （规范：'a\n\nb'）
b"event: x\ndata: a\ndata:\ndata: b"  -> data='a\n\nb'   （与规范一致）
```

**后果很小，但它属于新基准下应当登记的那一类。** 一个 payload 里的空行，若上游把它拼成裸 `data` 而不是 `data:`，会丢。本项目自己的 `encode_frame` 写的是 `data:` + 行内容，所以往客户端那一侧不会产生这种拼法；上游会不会这么写未测。§3 现在承诺的是「按 SSE 规范的 field parsing 算法得到的 logical `data` 字符串」，而这是一处相对该算法的实际偏差，清单里没有它。

**建议。** 两条路都行，选一条即可：把它加进「明确不承诺」（成本最低），或者在 §3.1 之外单列为一条可选修复（`if not separator:` 改成把整行当字段名、值为空串——两行代码）。**不建议**把它升格成 P4 那样的前置：它与 P1／P2／P3 不同，没有已知的 payload 截断后果。

**证据强度：机制强**（规范原文本轮实取、`parse_frame` 实跑两个对照用例）。**触发未测**——上游是否会写裸 `data` 行，本轮无从测；权重仅够登记，不够要求修复。

---

## 四 · 门禁：plan §8 顺序表逐步 yes/no

复核并更新 round7 那份。**变化的是第 2、4、5、6、8、9 行**，理由各自写在条件列。

| 步 | 内容 | 门禁 | 条件与本轮变化 |
|---|---|---|---|
| 1 | P1／P2 | — | 已完成（`7e96adc`）。本轮用 `git show`／实跑 `test_sse_assembly.py` 复核，`encode_frame` 与 `_FRAME_SEPARATOR` 都在，52 passed |
| 2 | 透传 assembler／framer 骨架 | **conditional yes（可 squash，有一处必改）** | round7 点名的两处已在 `8bd5653` 改掉（`unfinished` 拆成两个属性、测试注释对 §5 的错误复述）。**必改**：`openai_responses_passthrough.py:190` 的 `unattributed` docstring 把 §7.2 第 3 步的处置规则**逐字复述进了代码**（「On an **upstream terminal** they are submitted verbatim in order…」），而那条裁定正被 round8-01 挑战。把这两句改成纯引用（「处置见 `spec.md` §7.2 收口步骤；本属性只负责把两类分开报出来」）即可与 round8-01 的处置解耦，**代码行为一个字节都不用动**。属性拆分本身是对的，与 round8-01 的结论无关——无论第 3 步的谓词怎么改，这两类都必须分开报 |
| 3 | `parse_frame` 只认 CR／LF／CRLF（P3） | **yes，无条件** | 已在 `260831-sse-line-endings`（`2c93ac6`）实现，我核过完整 diff：`_LINE_ENDING = re.compile(r"\r\n\|\r\|\n")` ＋ `re.split`，模块 docstring 里那句被证伪的断言也改了。合入时须同步 round8-10 点名的 `spec.md:96` |
| 4 | 交错场景与 §5 的提交语义接线 | **yes（round7 是 no）** | 唯一的阻塞项 round7-02 已 closed：`spec.md:113` 现在是一句无歧义的正面规则，骨架那条错误注释也改了。§5 提交表与全部四处复述本轮扫描一致 |
| 5 | replay 合同（§5.2 三类结果与 failure 归一化） | **yes（round7 是 conditional yes）** | round7-03 的三处全部改到位，且 `spec.md:137` 现在与主仓 `stream.py:468-472` 的实际顺序一致（我实跑核过）。round7-05／06／07 也都关了，§5.2 的映射表可执行 |
| 6 | `requires_client_action` 与三种 policy（含 §7.2） | **no** | 挡在 **round8-01**（收口第 3 步的谓词不成立，且它的论据句字面说反）。另有两条同刀要改：round8-03（`plan.md:54` 仍是三步收口，而这一步的实施说明就是它）与 round8-04（`plan.md:117` 的判据与 v8 相反）。**§7.1 那一半没有问题，可以先做**——判据全部读 item 自身，SDK 类型我复核无误 |
| 7 | 分流点接线 ＋ 撤销 `ca777df` ＋ 更新断言 | **no** | 依赖 4 与 6。这一步自身的执行指令本轮**实跑核过**：`tests/int/test_pipeline_app.py` 的 `:2549`／`:2585`／`:2617`／`:2652` 四个函数名与 plan 点名的完全一致，`test_openai_responses_format.py:331` 与 `test_responses_anthropic_nonstream.py:259` 两条「一律不动」的翻译腿测试也对得上。`plan.md:94` 已按 round7-10 把「新链路确实被真实入口调用」写进本步验收 |
| 8 | Headers（§9.1） | **conditional yes（round7 是 no）** | 「取交集」这个过渡方案在**剥离方向**是安全的，落地后不会转发用户名单点名要剥的任何头，因此技术上可以先实施而不必等裁决。**三个条件**：(a) §11 O-1 要真的送到用户面前，而不是停在 §11 里——round7 判它「唯一必须上交用户」，v8 只做了登记；(b) `plan.md:121` 的判据要标注它随裁决翻转（round8-09）；(c) §9.1／§11 那两句过强断言先改（round8-05），否则用户拿到的分叉面不完整。**我把它从 no 改成 conditional yes，理由是** v8 已经把 round7 要求的三件事做了两件，剩下的是描述精度问题而不是行为未定 |
| 9 | 可观测迁移（§10） | **yes**，排在 4–6 之后不变 | round7 沿用 round6 的那条建议（在本步点名 `tests/int/test_pipeline_app.py:2788`）已被 v7 采纳，`plan.md:90` 逐字写着；我核过 `:2788` 确是 `test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it`。**一处小瑕疵**：`plan.md:90` 说「见 §9 末」，而 plan §9 末尾（`:125`）讲的是「判据必须在实现之前独立推导」，没有关于 `:2788` 的任何内容——指针悬空，改成「见 §6」或直接删掉那三个字即可，不单独立条 |

**总结成一句**：step 3、4、5 现在就能走，step 2 改一段 docstring 即可 squash，step 8 在三个描述性条件下可以开工；step 6 挡在唯一的 blocker 上，step 7 依赖 4 与 6。

## 五 · `docs/.human-controlled/` 通读结果

**已通读全部 14 个文件**（`ls` 清点：`README.md`、`api.md`、`cli.md`、`client-side-block-delivery.md`、`config.example.yaml`、`ghc-api.md`、`lifecycle.md`、`message-format-reshape.md`、`message-translation.md`、`module-org.md`、`release-and-deployment.md`、`request-pipeline.md`、`test-org.md`、`upstream-retry-and-continuation.md`；其中 `cli.md` 是 0 字节空文件）。前七轮的判据来源里最多出现过其中四份。

### 直接回答第五问

**没有第二个 round7-01 那种形状的错标**——我没有再找到第二处 Spec 逐字写着「用户未裁决／未定」而用户其实已经表过态的地方。`spec.md` 全文现在只剩一处「未裁决」字样（`:323`），而那一处正是 v8 用来更正错标的那句事实陈述。

**但找到两处相邻形状，都已单独立条：**

1. **round8-02（major）**：Spec 说「其他客户端未穷尽」，而用户在 `config.example.yaml:602-605` 具名写下了 `@ai-sdk/openai`。它不是「说未裁决」，是「说不知道，而用户写下来了」。
2. **round8-06（minor）**：Spec 说 cap 的「用户亲笔定义」是那句英文，而用户那条注释是双语的，中文半句给出另一读。它不是「说未裁决」，是「只引了原文的一半」。

### 逐份核对结果

| 文件 | 与本规格相关的内容 | 判定 |
|---|---|---|
| `README.md` | 文档清单与「你不能亲自动手修改本系列文档」的约束 | 无冲突。（顺带：清单第 18 行列了 `observability.md`，目录里没有该文件——用户自己的文件，不归本报告处置，只记） |
| `api.md` | `POST /responses` 注册在 `/v1` 与 `/openai/v1`；Responses WebSocket「暂不支持」 | 与本规格定义域一致，无冲突 |
| `cli.md` | 空文件 | 无内容 |
| `client-side-block-delivery.md` | 响应头只在第一次 HTTP 200 转发；SSE ping；两个 deadline；客户端超时的两分支；「完整块 ＝ `_start` 到 `_end` 之间的全部内容」 | **§9.1 已逐字援引响应头那条并正确限定了定义域**（`spec.md:319-321`）；§3 的脚注也援引了块级合同。**「未发头则直接返回 HTTP 504」那一支不在本规格，但它归 `error-envelope/spec.md:174`（`ClientDeadlineError` → `TIMEOUT` → 504），而 §2.4 保留了该跨腿合同**——见第六节第 4 条 |
| `config.example.yaml` | `buffering_policy` 三值、`buffer_cap_bytes`、`sse_ping_interval`、`hedge`、`hook_fix_responses_sse.fix_stream_ids` | **两处问题**：round8-02、round8-06。`hedge` 见第六节第 5 条 |
| `ghc-api.md` | `POST /responses` → `direct_driver.openai_responses` | 一致，无冲突 |
| `lifecycle.md` | 关闭信号语义、优雅关闭三级 | 与 §5 的 draining 裁决同源、不冲突（Spec 引的是 `upstream-retry-and-continuation.md`，那是更贴题的一份） |
| `message-format-reshape.md` | 直连**请求头**黑名单（**明确限定「仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效」**）、直连**响应头**黑名单（**无同类限定句，只有节标题**）、attribution header、`anthropic-beta` flag | round7-01 的源头，v8 已更正。**但有一条对 §11 O-1 有用的证据没有进 Spec，见下** |
| `message-translation.md` | 「对于直连路径，采用尽可能原样转发的原则」 | §2.2 已逐字援引，无冲突 |
| `module-org.md` | 追认的模块层次（`pipeline` → `delivery`） | 骨架落在 `app/pipeline/delivery/formats/`，属未追认的子模块，文件自己写明「不代表子模块也被追认」——无冲突 |
| `release-and-deployment.md` | 依赖固定 | 与本规格无关 |
| `request-pipeline.md` | 已知异常五类、未知异常总是中止 | 与 §5.2「不新增枚举值」一致，无冲突 |
| `test-org.md` | `tests/unit/<类似 src 的包结构>/` | 骨架测试落在 `tests/unit/pipeline/delivery/`，一致 |
| `upstream-retry-and-continuation.md` | 可继续／不可继续两张清单、无痕重试、优雅关闭、429、MCP 续写「只给 anthropic-messages」、**输出超长（点名 `max_output_tokens`）** | §5 与 §8 已援引前四项。**「输出超长」那条点名了 `openai-responses` 而 Spec 从未引用它**——核过之后判为已被满足，见第六节第 3 条 |

### 一条对 §11 O-1 有用、但目前没有进 Spec 的证据

`message-format-reshape.md` 里，**请求头**那一节（「## 客户端输入 Anthropic Messages」）第 7 行有一句明确的定义域限定：

> 这部分仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效。

而**响应头**那一节（「## 客户端返回 Anthropic Messages」）**没有**任何同类句子，只有节标题。

这个**不对称**是用户自己写下的文本事实，而 O-1 要裁的恰恰是「节标题的定义域覆不覆盖 Responses 客户端」。它可以朝两个方向读——「用户会在需要限定时明确写出来，这里没写所以不限定」，或者「限定句写在文件开头一节，统辖全文」——**我不主张任何一读**，那正是 O-1 要交给用户的。但把它摆在 O-1 的现状列里，用户裁起来的信息量明显不同于现在只写着「节标题的定义域只有作者能裁」。

**建议**：`spec.md:370` 的 O-1 现状列补一句记下这个不对称，与 round8-05 的两侧差异同刀写。属事实登记，不需要用户点头。

## 六 · 考虑过但否决的候选发现

逐条写下，因为纯推理排除掉的路线事后捞不回来。

1. **「§7.2 第 3 步对四个 audio 事件也是错的，应当一并丢弃」——否决。** audio 事件按 SDK 类型「既无 `output_index` 也无 `item_id`」，它们按构造不属于任何 item，所以「可能属于某个未闭合 item」这个理由对它们不成立，交付是对的。round8-01 攻击的是**判据的轴选错了**，不是「交付这件事本身错了」；我给的替代谓词（收口时刻有没有未闭合 item）在正常结束的响应上仍然交付它们。
2. **「§4 把 audio 与解析失败并进一个桶，应当在 §4 就拆成两类」——考虑后并入 round8-01，不另立条目。** §4 的合并本身不产生行为（两类的**持有**处置相同，都必须挡住其后的前缀），问题只在收口时刻它们的**去向**应当不同。在 §4 拆桶是一种可选实现，但 Spec 层只要把第 3 步的谓词改对就够了，不必强制两个概念。
3. **「用户亲笔的『输出超长』一节点名了 `openai-responses` 的 `max_output_tokens`，而 Spec 从未引用它，属漏引用户裁决」——查证后否决。** 用户的要求是「不应无痕重试；能续写就走续写，不能续写就直接返回给客户端」。逐条对：`response.incomplete` 在本规格里是**终局**而不是 failure（`spec.md:211` 与 `:267`），§5 的 replay 资格只覆盖「transport tear、无终局 EOF、可重试的 upstream failure」，终局根本进不了 replay 判定，所以「不应无痕重试」自动成立；本腿没有续写通道（`spec.md:141` 已写明），所以「直接返回给客户端」＝ §7.2 final source 表第一行「逐字提交它」；`status: "incomplete"` 的 item 照常交付也已在 `spec.md:303` 单独裁过。**三项全部被满足，只是 Spec 没有引用这条出处。** 值不值得补一句引用是编辑口味，不构成发现。
4. **「§8 说代理侧错误一律写 SSE `event: error`，而用户裁决在响应头未发时要求 HTTP 504」——查证后否决。** `error-envelope/spec.md:174` 的 §5.1 表里 `ClientDeadlineError` → `TIMEOUT` → **504** 已经承载了那一支，而 `spec.md:59` 的 §2.4 明确保留了 error-envelope 这类跨腿合同。此外 §7.2 的 ending 表把 deadline 归进「按上表收口，末步写 error」，那本身就预设了通道已开。**不构成本规格的缺口。**
5. **「`config.example.yaml:399-407` 的 `hedge`（同一客户端请求并发两个上游 attempt）与 §5 的 attempt／replay 模型冲突」——查证后否决为发现，转交接。** 实跑 `rg -ln 'hedge' src/` 只命中 `src/app/config/schema.py`，即今天只有配置项没有行为。§5 的模型（一次一个 attempt、replay 是替换）在 hedge 落地时确实要扩展——两个并发 attempt 各有自己的 `response.id`，而「已提交」是 attempt-local 的——但那属于 hedge 那个功能自己的规格，不是本规格今天的缺口。记在第七节交接。
6. **「`hooks.on_client_sse_block_ready`（「发往客户端的 SSE 完整块已准备好」）在本腿上的载荷不再是 Anthropic 块，Spec 没规定它变成什么」——否决，不在定义域。** 钩子订阅面归 `hooks-subscription-migration` 主题，两处默认都是 `[]`。记下来只为免得下一轮重新想一次。
7. **「§9.1『其余一律转发』会把 `Set-Cookie` 转给客户端，构成安全问题」——仍然否决为安全发现，沿用 round6／round7 的处置。** 用户既有立场是没有具体危害就不加防护，转发对象是发起请求的客户端本人。v8 的取交集事实上已经剥掉它，但那是**权威冲突**的结果不是威胁模型的结果，`spec.md:350` 那条注已经把这一点写对了。
8. **「§3 承诺『按 SSE 规范的 field parsing 算法』，而 `parse_frame` 还有别的偏差没登记」——只找到一处，已立 round8-13。** 我逐条对着规范走了 `parse_frame` 的每个分支：注释行跳过（规范一致）、单个前导空格剥离（一致）、多 `data:` 用 `\n` join 且无尾随换行（与规范「移除尾随换行」等价）、空 data buffer 返回 `None`（一致）、UTF-8 replacement（一致）。**只有无冒号行那一条是真偏差。**
9. **「骨架 `_take_safe_prefix` 的回退循环是 O(n²)」——否决，沿用前两轮处置。** 量级实测可忽略，无 Spec 条款被违反。
10. **「`RawEventBatch.size_bytes` 仍无调用者」——否决，沿用 round7。** 在 cap 那一刀落地前不构成缺陷。
11. **「§5.2 的 `ReopenRefused` 今天为空，应当删掉」——否决。** `spec.md:187` 已如实陈述它为空并写明保留理由（将来的本地拒绝不被挤进 `AttemptFailed` 继承错误归因），这是正确处置。
12. **「`spec.md:26` 的『28 个顶层成员』与 §4 的『58 个 `ResponseStreamEvent` 成员』该复核一遍」——本轮未复核，不报。** skeleton 评审逐个数过，本地 SDK 版本未变（`openai==3.3.1`），没有新证据。**明确标为本轮未验的继承事实。**
13. **「Spec 里仍留着 `encode_frame`、`JSONResponse`、`hand_back_block()` 等实现符号，应搬进 plan」——本轮仍不报，状态不变。** 这是 round5 提出、round6／round7 沿用的一条**未采纳建议**，不是已闭合项。现在仍有 blocker，大搬文字会混入语义改动。
14. **「§2.1 的用户原话「协议允许，凭什么拒绝？」应当独立回指」——无法执行，按前几轮处置。** 我无法访问原始会话，按「与调用方复述及前七轮一致」采纳。**§2.2、§5、§9.1、round8-02、round8-06 的用户归属则逐字可核，本轮已核。**
15. **「应该给这些判据加一道 gate／覆盖率门／验收状态机」——否决。** 项目明令禁止为证明而搭证明设施。本报告只给判据与建议，不建议任何阻断装置，也不建议 `ruff format`。
16. **「P3 worktree 的 `re.split` 会多产生一个尾部空串」——沿用 round7 的处置，不报。** 空串既不以 `:` 开头也不含冒号，`partition` 后 `separator` 为空即 `continue`，行为无差异。本轮我读了完整 diff，确认结论仍成立。

## 七 · 搜索面、执行证据与限制

### 判据来源（独立于被检对象）

- **`docs/.human-controlled/` 全部 14 个文件**，逐字读全文。第五节有逐份核对表。前七轮里 `config.example.yaml` 只被读过三行、`api.md`／`ghc-api.md`／`module-org.md`／`test-org.md`／`request-pipeline.md`／`lifecycle.md`／`README.md` 从未出现在任何一轮的判据来源里。
- `.dev/docs/error-envelope/spec.md` 的 §2（`:52-63`）、§3.1–§3.5（`:65-99`）、§5.1 表（`:174-175`）、§11（`:424`）。
- WHATWG SSE 规范原文（`https://html.spec.whatwg.org/multipage/server-sent-events.html`），本轮实取，用于核 §3 新钉的基准。
- 主仓源码：`sse_source.py` 全文、`stream.py:455-485`、`retry.py:130-150`、`inference.py:395-440`、`direct_driver/base.py:70-196`、`formats/openai_responses.py:112-250`。
- 骨架 worktree `260831-passthrough-skeleton`（HEAD `8bd5653`）：`openai_responses_passthrough.py` 全文 222 行、`git show 8bd5653` 完整 diff。
- P3 worktree `260831-sse-line-endings`（HEAD `2c93ac6`）：`git diff 7e96adc..HEAD -- sse_source.py` 完整 diff。
- 前七轮报告 ＋ skeleton 评审（作为已核事实的来源，不作为判据的替代）。

### 本轮的执行证据（round7 完全没有这一节，因为它的 `Bash` 全程被拒）

- `git log --oneline`／`git worktree list`／`git diff --stat`／`git show`：**四个 HEAD 全部独立核验**，与调用方给出的一致。
- `uv run pytest tests/unit/pipeline/delivery/test_sse_assembly.py` ＋ 两个直连腿集成测试（主仓）：**52 passed in 2.87s**。
- `awk` 定位：`tests/int/test_pipeline_app.py` 的 `:2549`／`:2585`／`:2617`／`:2652`／`:2788` 五处函数名，`test_openai_responses_format.py:331`、`test_responses_anthropic_nonstream.py:259` 两处——**七处行号逐个对得上**。
- **探针一（round8-01）**：骨架 assembler ＋ 主仓 `parse_frame`，构造含裸 U+2028 的 `output_item.done`，实跑得到孤儿帧与非法 JSON payload，输出逐字贴在 round8-01 里。
- **探针二（round8-13）**：主仓 `parse_frame` 对五个 SSE 边界用例，确认无冒号 `data` 行被跳过、只有 `event:` 的帧返回 `None`。
- 两次探针都用 `PYTHONDONTWRITEBYTECODE=1` 从 `/tmp` 运行，**没有在任何 worktree 里写入任何文件**（无 `__pycache__`、无 `.pytest_cache`）。
- `rg` 检索：`fix_stream_ids|ai-sdk` 在 `src/`、`tests/` 为空集，在整个 topic 目录只命中 `spec.md:207`；`hedge` 在 `src/` 只命中 `config/schema.py`；`未裁决|用户未|待裁|未定` 在 `spec.md`／`plan.md` 只命中 `:323` 与 `:385` 两处（都是 v8 的更正陈述）。

### 限制

- **报告写不进指定路径。** `Write` 到 `.dev/docs/direct-responses-passthrough/reports/` 被 harness 拒绝，原文：「This subagent's parent bg session hasn't isolated yet, so writes to the shared checkout are blocked.」已按调用方预案落 `/tmp/ghc-review-r8/`，搬运命令在文首。**这只影响落盘位置，不影响任何结论**——`Bash`、`git`、`rg`、`pytest`、`Read`、`WebFetch` 本轮全部可用。
- **没有做变异。** 调用方的白名单明确写着「不允许修改 `src/`、`tests/`」，而 round7 交接项第 3 条建议的那次变异（把骨架 `_take_safe_prefix` 的 `while cut > 0` 改成单次 `if`，看 `test_retreating_past_one_straddling_item_can_expose_another` 会不会红）需要改测试目录下的代码。**因此骨架回退循环的测试分辨力本轮仍未验**，我对它的判断依据是读逻辑与读断言形状，属强推断而非一手执行。这一条**交接给下一轮**，它仍然是骨架里最重的一处新逻辑。
- **没有在骨架 worktree 里跑 pytest。** 出于同一条边界（避免在别人的工作树里留下 `.pytest_cache`／`__pycache__`），我用无字节码写入的独立探针替代。**后果**：骨架那 300 余行测试今天是不是全绿，本轮**未验**；我只验了它们断言的形状与被断言的实现逻辑。
- **`@ai-sdk/openai` 的具体校验方式未核**（round8-02）。我没有它的源码，采纳的是用户在 `config.example.yaml:603-604` 的陈述。这不影响本条的核心——核心是 Spec 说「未穷尽」而用户已具名，那是文本事实。
- **上游行为的发生率全部未测**：audio 事件、非 object payload、未来事件类型是否携带 `item_id` 而不携带 `output_index`——三条都只有机制没有触发证据，round8-01 的表里逐条标了权重。
- **§2.1 的用户 8/30 原话无法独立回指**（无法访问原始会话），按与调用方复述及前七轮一致采纳。
- **`spec.md:26` 的「28 个顶层成员」与 §4 的「58 个 `ResponseStreamEvent` 成员」本轮未复核**，是继承自 skeleton 评审的事实。

## 八 · 严重度汇总

- blocker：1（`round8-01`）
- major：3（`round8-02`、`round8-03`、`round8-04`）
- minor：5（`round8-05`、`round8-06`、`round8-07`、`round8-08`、`round8-09`）
- nit：4（`round8-10`、`round8-11`、`round8-12`、`round8-13`）
- finding_total：13

基线处置状态：round7 `closed=14`、`partially_closed=0`、`not_closed=0`。

**按位置分**：`spec.md` 8 条（round8-01、05、06、07、08、11、12，加 round8-02 的主位置）、`plan.md` 4 条（round8-03、04、09，加 round8-10 的一半）、骨架 1 条连带（round8-01 的第 3 层影响，属注释级）。

## 九 · 交接事项

1. **round8-01 是本轮唯一必须在 step 6 之前解决的一条**，且它牵动六处：`spec.md:69`／`:282`／`:284`／`:372`、`plan.md:121`、骨架 `openai_responses_passthrough.py:184-194` 与对应测试。我给了一个可执行的替代谓词，但它属 §2.3 推导且触到 §2.1 的边——**是否顺带升级给用户，由调用方判断**；我的看法是不必，因为替代谓词拒绝的理由（「不能排除它属于一个已知没说完的 item」）是 §3 已经用过并被接受的那个，不是用户否掉的那个。
2. **round8-02 需要一次登记决定。** 本腿改 native 会撤掉今天 `ResponsesFramer` 提供的稳定 id，对用户具名的 `@ai-sdk/openai` 一类客户端是回归。是否在启用透传的同一刀里提供 opt-in 的 `fix_stream_ids`，属产品分叉，按 `no-silently-cut-but-defer` 应当登记而不是静默略过——**登记本身不需要用户点头，怎么裁需要**。
3. **§11 O-1 至今没有真的送到用户面前。** round7 判它「唯一必须上交用户」，v8 把它登记进了 §11，但登记不等于上交。第五节末尾给了一条对这次裁决有用、目前不在 O-1 里的证据（请求头一节有明确的定义域限定句，响应头一节没有）。
4. **P3（`2c93ac6`）随时可以合入 `main`**，合入时的同步清单 `plan.md:17` 已经写好，再加上 round8-10 点名的 `spec.md:96`。
5. **下一轮最该补的一件事仍然是骨架回退循环的变异**（round7 交接项 3），本轮因白名单不允许改 `tests/` 而未做。若下一轮的边界允许在隔离工作树里做受控变异，这是投入产出最高的一项。

## 十 · 收尾判断

本轮不触发开发 closeout：评审完成，但 Spec 仍有 1 blocker ＋ 3 major，主体边界未到；本轮没有 source／test 改动、没有提交、没有 worktree 处置，唯一交付物是本报告（落在 `/tmp`，待调用方搬运）。采纳与修改由调用方执行。
