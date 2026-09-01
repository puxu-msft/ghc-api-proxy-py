# 直连路径原生透传：实施计划

日期：2026-09-01（v12）
状态：**Responses 直连腿已接线并合入 `main`**（`1fb37cd`，1998 passed／ruff clean／pyright 0），issue #2／#3 已修；源提交存于 `archive/260901-passthrough-wiring`，经一次代码评审与两轮 Spec 评审。§0 的三项前置全部已合入 `main`（P1／P2 在 `7e96adc`，P3 在 `109dc44`）；骨架已合入 `main`（`01c33f1`）。**Anthropic 直连腿的词汇已实现并单测，未接线**——挡在 [`spec.md`](spec.md) §2.8 的 hand-over 问题上（[`deferred.md`](deferred.md) D-5）
权威：[`spec.md`](spec.md)。**本文不定义任何用户可观察行为**——凡本文与 Spec 冲突，以 Spec 为准；凡本文出现 Spec 没有的行为承诺，那是缺陷，应移入 Spec 或删除。

> **v1 已作废并重写。** 它规定「只保存 `done.item` 的最终快照、重发 `added` + `done`、继续 mint id、沿用 framer 的 output index」，而 Spec v2 要求保存全部 item 专有事件、不得 mint id、terminal 整个对象逐字。照 v1 实施会直接违反 Spec。作废理由见 [`reports/260830-review-spec.md`](reports/260830-review-spec.md) major-08 与 [`reports/260830-review-plan.md`](reports/260830-review-plan.md)；两份报告作为时点记录不改。

## 0. 先修的既有缺陷（Spec §3.1）

它们是整条路的前置，且**两条腿共用**，所以先单独落地、单独验证。

| # | 缺陷 | 状态 |
|---|---|---|
| P1 | `_report_failure` 对含换行的 payload 写成一行 `data:` 加一行裸文本，客户端只剩第一行 | **已完成**（`7e96adc`）：新增 `encode_frame(event, data)`，每行一条 `data:` |
| P2 | `read_events` 的 frame separator 固定 `b"\n\n"`，两个合法 CRLF 帧被合并成一个事件 | **已完成**（`7e96adc`）：分隔符改为两个连续行尾，用 atomic group 防回溯把单个 `\r\n` 拆成两个 |
| P3 | `parse_frame` 用 `str.splitlines()` 拆行，其断行集是 SSE 的超集，data 里裸的 U+2028／U+2029／U+0085 会让该行从此处截断 | **已完成**（`109dc44`，源提交 `archive/260831-sse-line-endings`）：新增 `_LINE_ENDING = re.compile(r"\r\n\|\r\|\n")`，`parse_frame` 改用 `re.split`；5 个参数化用例，变异（改回 `splitlines()`）全红。独立评审 pass、0 blocker（[`reports/260831-review-sse-line-endings.md`](reports/260831-review-sse-line-endings.md)） |

P1／P2 都已变异验证：把分隔符改回 LF-only，CRLF 与 CR 两个参数变红；把 encoder 改回单行 `data:`，多行用例变红。

> P3 是骨架评审在核对 §3 承诺时发现的，机制已实跑证实、触发未证实（详见 Spec §3.1）。它与本腿的接线无关，两条腿共用，所以留在 §0 并单独落地。

## 1. 分流点

在 `delivery_policy` 计算出两种 mode，**实例化两个不同的 assembler**，而不是在 `_close` 深处散落客户端腿条件：

- **透传** —— `translation_required is False`，按 inbound 方言取对应的 `Dialect`（Spec §2.5 的表）。这里此前写的是「且两端同为 `openai-responses`」，那是 v10 放宽定义域**之前**的判据；实现里的 `carries_upstream_natively` 今天仍只放行 Responses，但那是 §2.8 的临时限制而不是分流点的定义
- `RESPONSES_TO_ANTHROPIC` —— 现有 `ResponsesAssembler`，独占块对归因队列、Anthropic 块号、`UNKNOWN → REJECT`、reasoning carrier

理由（评审 plan-review-06）：两个 feature 语义正交但**实施共享承重点**。issue #1 的块对工作与本工作都要改 `ResponsesAssembler` 的构造参数、`push`/`_open`/`_close`、块号分配与 terminal flush；不物理隔离就会出现「direct `web_search_call` 进了待归因队列」这类跨腿泄漏，而两边各自测试通过也证明不了合并态。

## 2. 交付单元与队列

透传 assembler **不产出 `CompletedBlock`**——那个类型的 docstring 明定它是 Anthropic content block。需要一个并列的交付单元类型承载「一组原始事件」。

- 维护 attempt 内全局事件队列 + 单调 commit frontier（Spec §4）
- 释放条件：从 frontier 到某位置之间所有已打开 item 均已 `done`
- 事件按原位置排队，**不重排**；未知 item 专有事件无须被认识，只需停在原位

`BlockBuffer` 今天用 `kind == TOOL_USE` 做 `until-tool-use`、用 `repr(payload)` 计量。本腿需要各自的等价物：释放判据见 §4，计量按实际持有字节（Spec §8）。

## 3. Framer

透传 framer 只做一件事：把队列里的 `(event, data)` 用 P1 的 raw-text encoder 成帧。**不解析 data，不改写任何字段。**

`ResponsesFramer` 的 `preamble()` / `terminal()` / `_output_index` / id 自铸在本腿**全部不用**——control 与 terminal 事件按 Spec §6.3 原样重放。

## 4. `requires_client_action`

按 Spec §7.1 实现，签名是 `requires_client_action(item)`——**判据全部读 item 自身**（`item.execution`、`item.environment`），**不需要任何请求侧通路**。v2 写的那条数据通路是对评审意见的误读，已删。

实现可以维护一张由 SDK 版本导出的表，但**表是判据的当前编码，不是判据本身**；未知类型按 Spec 保守视为需要释放并记 `predicate unknown`。

还要实现 Spec §7.2 的收口顺序。**先过 §5 的 replay 门**——funded replay 时 §7.2 根本不运行，旧 attempt 一个字节都不提交。真正进入收口时**照 Spec §7.2 的四步执行，本文件不复制**——与本文件对 header 名单、code 映射表已经采纳的「不复制」纪律一致。v8 之前这里复述的是三步，漏掉的正是当时新增的那一步（无法归属事件的处置），而**漏写不构成冲突**，`plan.md` 文首那句「与 Spec 冲突以 Spec 为准」救不了它：少一步与本来就没有这一步在文本上完全同形，没有任何东西会红。客户端取消与下游写失败例外。**不得**沿用现有 `stream.py` 各 ending 是否 flush 的现状。

## 5. Replay 与 commit

按 Spec §5 实现 commit frontier 与 attempt 状态重置。现有 replay 判据读的是「客户端是否已看到 semantic bytes 与 committed block」，本腿换成「首个原生事件是否已提交」。

**还要实现 Spec §5.2 的 adapter**：把 `StreamFailure` 归一化成既有 `RetryReason | None` 再交给现有 taxonomy，**不新增枚举值**。映射见 Spec §5.2 的表，**本文件不复制**——与 §5.1 对 header 名单的纪律一致。Spec 是活文档，`vector_store_timeout` 那一格 v6 才刚改过一次，一份转抄在下一次改动时不会红。重开 attempt 的结果按 Spec §5.2 分成 `OpenedAttempt`／`AttemptFailed`／`ReopenRefused` 三类；**`ReopenRefused`（draining、本地前置拒绝）不得进上游 taxonomy**。承载类型由本文件决定，语义由 Spec 决定。

## 5.1 Headers

按 Spec §9.1 实现，流式与非流式同一合同。当前两处都不转发任何上游语义头，所以这是**新增行为**，各自要测试。

算法顺序要注意：**先读 `Connection` 的值把它点名的字段一并剥掉**，再剥固定的逐跳名单（含 `Proxy-Connection`），再按 **Spec §9.1 的语义判据**剥掉「验证或描述上游确切字节、而本代理未重新计算」的字段——**判据在 Spec，本文件不复制名单**，因为名单必漏。非流式的 `Content-Type` 按实际输出重建。流式只取第一次 HTTP 200 attempt 的头，replacement 不得覆盖。

## 6. 可观测

按 Spec §10：wire 走原生，可观测另立旁路 typed facts。`Terminal` 在本腿只作内部摘要，不得反推 wire。

需要迁移的既有事实：item 计数、需要客户端行动的 tool 名、reasoning 是否出现、权威 terminal status 与 usage、failure/截断/replay 来源。

## 7. 撤销 `ca777df` 在直连腿的那一半

> 顺序表里这一步现在是第 7 位，与本节编号无关；见 §8 的两条说明。

`main` 上 `ca777df` 把翻译腿的「未知 item → REJECT」套用到了直连腿，是定义域误用（Spec §2.4）。透传落地后，直连腿不再有「未知」这个状态——所有 item 一律携带。**翻译腿的 REJECT 保留。**

## 8. 顺序

1. ~~P1、P2~~ **已完成**（`7e96adc`）
2. 透传 assembler／framer **骨架**，不接线。只跑单元 smoke，**不宣称任何 issue 测试转绿**
3. `parse_frame` 只认 CR／LF／CRLF（Spec §3.1 第三条）。两腿共用的前置，与本腿的接线无关，可独立落地
4. ~~交错场景与 §5 的提交语义接线~~ **已完成**（`092bd43`）：control-only 前缀持有到第一批 item 事件，终局解除持有
5. replay 合同 —— **部分完成，此前标「已完成」是过头的**。已完成的是：`terminal`／`failure`／`cut_mid_block` 由与翻译型 assembler 共用的读取函数填充，交付循环既有的 replay 机制因此原样适用于本腿。**未完成的是 Spec §5.2 那一半**：原生 failure → `RetryReason` 的归一化 adapter 与 `OpenedAttempt`／`AttemptFailed`／`ReopenRefused` 三类重开结果都还不存在，`assembler.failure` 今天直接写给客户端然后 `return`，从不进 retry taxonomy。也就是说**一个可重试的原生 `response.failed` 今天不会被重试**
6. ~~`requires_client_action` 与三种 policy~~ **已完成**（`82cfa29`、`092bd43`）：三种 policy 由泛型化后的 `BlockBuffer` 直接提供，判据按 §7.1 读 item 自身
7. ~~抽方言词汇 ＋ `anthropic-messages` 一份~~ **已完成**（`d76ac1c`、`d3b4cc2`）。**写第二份词汇是引擎两条不通用规则的暴露方式**：终局事实此前只在终局事件上读（Anthropic 把 stop reason 放在 `message_delta`，会漏一半），批次判据此前只读闭合事件（Anthropic 的 `content_block_stop` 只带 index，会让每个 tool call 答 `False`）
8. **接线**：Responses 直连腿**已完成并合入 `main`**（`1fb37cd`），issue #2／#3 关闭。**Anthropic 腿未接线**，挡在 Spec §2.8 上（`deferred.md` D-5、D-6）
9. Headers（§9.1）
10. 可观测迁移（本步会改变 `tests/int/test_pipeline_app.py:2788` 的断言——该测试自己的注释写着这样断言就是为了让「给它一个 reader」成为一次**有意**的改动而不是静默的）

> **第 7 步是 v9 新增的，来自用户 2026-08-31 的「根因修复所有直连路径」裁决。** 它排在接线之前而不是之后，理由与 v6 把接线挪到 policy 之后是同一条：一次「只接 Responses、Anthropic 直连继续走往返翻译」的接线不是自足切片——它会让同一个缺陷在两条腿上一条修好一条留着，而两条腿的客户端都看不出区别在哪。**Chat Completions 直连不在本步射程内**：它今天就把上游字节原样前送，天花板不存在（Spec §2.6），它缺的块级交付是 2026-08-22 已裁决的推迟项，不因本规格重开。

> **接线的目标是覆盖所有直连腿，今天只落了 Responses 一条。** Spec §2.6 逐条核过四条直连对：Responses **已接线**；**Anthropic 直连是同形缺陷且今天可达**（`descriptor.supports(inbound_endpoint)` 为真时 target 即等于 inbound，集成测试里已有 `anthropic-messages` 上游），词汇已实现但**未接线**，挡在 §2.8 的 hand-over 问题上（`deferred.md` D-5、D-6）；Chat Completions 的天花板不存在但那是偶然（没有 framer 所以字节直传），而 §5／§8／§10 在它上面今天都不成立，见 §2.6；Embeddings 非流式。
>
> 此前这句写的是「接线覆盖所有直连腿」，与它上面第 8 步「Anthropic 腿未接线」直接矛盾——同一份文件里两处相反，而其中一处还在复述 v11 已经换掉的旧论据。
>
> **接线为什么必须合成一刀。** v3 把「接线」与「撤销 direct 的 `REJECT`」分成两步，同时又说接线之后 issue 测试应转绿、且撤销之前不要改它们的断言——三句话不能同时成立。`test_an_output_item_this_assembler_does_not_know_is_refused_not_rendered`（`tests/int/test_pipeline_app.py:2549`）当前**明确断言** direct `custom_tool_call` 以 `error` 收尾、不出现任何 `response.output_item*`；接线一旦生效，正确行为恰好相反，该测试必红。启用 direct 透传与撤销 direct 的拒绝**是同一个 observable switch**，不是两个步骤。

> **另一侧的代价，与一个被否决的第三选项（v7 补记）。** 只写「接线在前」的风险会让下一个读者以为这个决定没有代价。接线在后的代价是：step 4（提交语义）、step 5（replay）、step 6（policy）三刀落进 `main` 之后**没有任何调用者**，要到 step 7 才第一次被真实入口执行——本项目在这个形状上有成本记录（守卫被留在 legacy 链路上，三次击发，第三次是静默假成功而非报错）。缓解办法是 step 7 的验收必须包含「新链路确实被真实入口调用」，而不是只看单测绿。
>
> 第三个选项是**接线早落但按 policy 条件路由**：`delivery_policy` 只在 `block` 下选透传 assembler，`full`／`until-tool-use` 仍走 `ResponsesAssembler`，直到 step 6 补齐等价物。它同时避开静默退化与死码窗口。**否决理由**：直连腿的可观察行为在过渡期取决于 policy，`ca777df` 的撤销只在 `block` 下生效，于是 issue #2 那个 item 在 `full` 下**仍被拒**——而「不得以不认识为由拒绝」是用户裁决，让它取决于一个配置项是更坏的形状。
>
> **接线为什么从第 3 位挪到第 7 位（v6 改）。** 它原本排在 policy 之前，而 `delivery_buffer(chain)` 是两腿共用的构造、`client_delivery` 的 policy 是用户可配项——于是接线生效到 policy 落地之间，直连腿上配 `full` 或 `until-tool-use` 会发生什么，计划里没有答案，最可能的结果是**静默退化成 `block`**：配置项还在、日志照旧、行为悄悄换了一种。本项目已经在「缺席读不出来」这个形状上付过代价。备选方案是保持顺序、写一段降级代码外加一条声明退化的可观测事实，但那段代码在 policy 落地后即成死码；而「一个把两种 policy 留作未定义的接线」本就不是自足的切片，与「小切片即刻集成」的规则并不冲突。**这不是把接线拆开**——它仍然是一刀，只是这一刀落在 policy 之后。来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-05。

> **那一刀要动的测试，逐条点名。** `git show ca777df -- tests/` 核过：它只新增了**一个**测试函数，即上面那条（连同一个 SSE 夹具辅助函数，共 57 行）。**「那两条测试」是 v5 的事实错误**，照它去凑数最可能改到的是下面这两条形近但**不在直连腿上**的测试，而它们承载的正是 Spec §2.4 明令保留的翻译腿 `REJECT` 覆盖——改动不会冲突也不会报错，只会让翻译腿的保护静默消失：
>
> - `test_a_block_kind_this_does_not_know_is_refused_rather_than_emptied`（`tests/unit/pipeline/delivery/test_openai_responses_format.py:331`）测的是 `ResponsesFramer` 对未知 `BlockKind` 的拒绝，直连腿换掉 framer 后走不到它；
> - `test_rejects_unknown_output_item_explicitly`（`tests/unit/protocols/test_responses_anthropic_nonstream.py:259`）是 Responses 上游 → Anthropic 客户端的非流式翻译腿。
>
> **翻译腿的 `REJECT` 测试一律不动。**另有三条直连腿测试会改变字节但不应改变断言（`tests/int/test_pipeline_app.py` 的 `:2585`、`:2617`、`:2652`，断言的是事件名与「没有 Anthropic 事件名」），先列出来，红了才知道是不是意外。来源：round6-04。

## 9. 验收

Spec 每一条规范性要求各自需要一条可失败的判据，尤其：多行 data、空 data、未知事件类型、未知字段、id 逐字（含上游不一致）、terminal 整对象、交错 item 不重排、首个原生事件提交前后的 replay 差异、三种 policy 的释放时点、cap 按持有计量。

**历次修订新增的承重点同样各要一条**，它们只在正文出现过。

v5：**funded replay 时不收口**（已完成 group 一个字节都不提交）、**policy × 最终 ending** 的三行差异、**已知 native failure code** 的归一化（`server_error` 与 `rate_limit_exceeded` 分别走哪条路）、**`ReopenRefused` 不进上游 taxonomy**、**`Connection` 动态点名的字段被剥离**、**表征元数据按语义判据剥离**（含 `Content-MD5` 这种不在名单里的）。

v6：**末步 carrier 按 final source**——尤其「不可重试 code 的 `failed` 逐字交付」与「可重试但预算耗尽的 `failed` 逐字交付」这两格，它们是 round5 那个 blocker 的正解，没有判据就没有任何东西能防止实现退回写 proxy error；**`vector_store_timeout` 可重试**；**非流式 `Content-Type` 由本代理重建**（反例是上游用 `text/html` 承载可解析 JSON）；**weak `ETag` 与 `Last-Modified` 必须保留**——**这一条是反向要求，也是最容易被静默违反的**：语义判据的自然实现方式是「剥离一切像 validator 的头」，而正确行为是留下它们，一条只测「strong `ETag` 被剥」的判据在错误实现上照样绿，所以要写成「weak `ETag` 与 `Last-Modified` **仍在**响应头中」这样的正向断言。

v7：**control-only 前缀不构成提交**（首帧 `response.created` 之后 replay 仍然合法——这一条直接决定四轮评审产出的 replay 合同走不走得到）；**一个 item 的事件不跨越释放边界**（反例序列 `created → added(0) → added(1) → delta(1) → done(0)`，断言 `added(0)` 不与 `done(0)` 分离）；**「无法归属」与「envelope」处置相反**（拿一个不带 `output_index` 的 audio 事件构造，断言它被**持有**而不是随 envelope 释放，且它与未闭合尾巴**分列两个集合**——ending 处的去向不归这条判据，见下面 v9 那条）；**draining 不花 replay 预算**（判定发生在重开之前，断言预算计数器未变）；**上游终局存在但 attempt 已作废时不得逐字重放它**。

v7 还缺一条，v8 补上：**重开被拒或失败时，已完成的 group 仍须按原序提交**。这是 v7 那次修复（partition 第一格补「且重开已经成功」）的可观察产物，也是 round6 那个 blocker 的正解。它是**反向断言**——错误实现（判定可 replay 就立刻销毁队列）在只测「funded replay 时一个字节都不提交」的判据下照样绿，因为那条测的是另一个方向。写法：构造「判定可 replay → 重开被拒」，断言此前已完成的 group **仍在**最终输出里且保持原序（错误实现只剩一条 error），并一并断言销毁发生在新流到手之后。

v8：**非流式错误 body 原始字节透传**（上游 4xx 的 `text/html` body 不被 parse 也不被重新序列化）；**响应头取交集**——`Date`／`Cache-Control`／`Set-Cookie` 不在输出里，**这半条的方向取决于 Spec §11 O-1，用户裁「名单不覆盖本腿」时须整条反转**；weak `ETag`／`Last-Modified` 在输出里，这半条与裁决无关。

v9：**无法归属的事件按「收口时刻有没有未闭合 item」判**，两个方向各一条，同一个构造只差一个未闭合 item：没有未闭合 item 时一个不带 `output_index` 的事件**仍在**交付里（正向断言）；存在未闭合 item 时它与那条尾巴一同不在。**v8 曾把这条写成「按 ending 来源二分」，那个判据是错的**——照它写出来的实现会在上游终局 ＋ 存在未闭合 item 时发出孤儿帧。

来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-09、[`reports/260831-review-skeleton.md`](reports/260831-review-skeleton.md) finding 01／02、[`reports/260831-review-spec-round7.md`](reports/260831-review-spec-round7.md) round7-09。

**判据必须在实现之前独立推导**，与 issue #1 块对那次同样的理由：判据一旦被实现假设污染就不可恢复。
