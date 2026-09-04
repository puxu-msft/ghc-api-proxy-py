# 直连路径原生透传：实施计划

日期：2026-09-04（v13）
状态：**Responses 直连腿已接线并合入 `main`**（`1fb37cd`，1998 passed、ruff clean、pyright 0），issue #2 和 #3 已修；源提交存于 `archive/260901-passthrough-wiring`，经一次代码评审与两轮 Spec 评审。§0 的三项前置全部已合入 `main`（P1、P2 在 `7e96adc`，P3 在 `109dc44`）；骨架已合入 `main`（`01c33f1`）。**Responses 流式直连的 terminal status 与 client-action 可观测切片已实现并合入 `main`（`bb5783f`）**（Spec §7.1、§10；TUI Spec「着色规则」与「验收」；设计与规格提交 `.dev@831b7dc`；实施计划 §10 经两轮独立评审达到 0 blocker、0 major）。**Anthropic 直连腿的词汇已实现并单测，未接线**——挡在 [`spec.md`](spec.md) §2.8 的 hand-over 问题上（[`deferred.md`](deferred.md) D-5）
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

完整迁移仍包括 item 计数、需要客户端行动的 tool 名称与类型、reasoning 是否出现、权威 terminal status 与 usage、failure、截断和 replay 来源。本轮只完成 Responses 流式直连的 terminal status 与 client-action 这一组相互依赖的事实：三态 `client_action_requirement`、buffering bool 投影、terminal `response.output` authority、typed `client_actions`、`client_action_classification_complete`、结构化记录与完成行上下文着色。非流式 `/responses` reader、reasoning 与其它尚未迁移的旁路事实继续保持原状态，不能把本切片写成 §10 整体完成。

本轮 Goal：当 Responses terminal status 为 `completed` 时，完成行同时保留 terminal status 与 terminal output 中的 client actions；只有 terminal snapshot 分类完备且没有 required 或 unknown action 时，`completed` 才绿。

本轮 Architecture：`assembling.py` 持有方言无关的 typed records；Responses 方言从 terminal `response.output` 一次形成最终 action snapshot，同时保留现有 done-side bool 给 buffering 与下游 stop reason 合成；`RequestTrace` 与 `RequestLine` 只搬运事实；`request_log.py` 是唯一决定文本和颜色的 presentation 层。两条消费路径不得互相反推。

本轮 Tech Stack：Python 3.14 dataclasses、`StrEnum`、现有 SSE assembler、structlog 请求完成行、pytest、Ruff check、Pyright。

本轮 Spec：[`spec.md`](spec.md) §7.1 与 §10，以及 [`../tui/spec.md`](../tui/spec.md)「着色规则」「描述回复的用词跟随上游」「验收」；定稿基线为 `.dev@831b7dc` 加评审处置 [`reports/260903-completed-client-actions-spec-review-disposition.md`](reports/260903-completed-client-actions-spec-review-disposition.md)。

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
10. 可观测迁移按独立事实组落地。本轮 10a 是 Responses 流式直连的 terminal status 与 client actions，具体任务见 §10；它不改变非流式 `/responses` 的空摘要测试。后续 whole-body reader 真正落地时才修改那条刻意钉住缺席的断言，不能由 10a 提前改掉

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

## 10. Responses 流式直连的 terminal status 与 client actions

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐任务执行并在任务间复核。步骤使用 checkbox 追踪。

### 全局约束

- 实现只覆盖原生 Responses **流式直连**；非流式 `/responses` whole-body reader 与翻译型 Responses terminal status 均保持 deferred。
- Wire 仍逐字携带上游事件；新增 facts 不得反向改写 wire，也不得替代 `Terminal.stop_reason`、`_saw_client_action`、framing、continuation 或 buffering policy 的既有消费者。
- 最终 action facts 与 completed 颜色只读 terminal `response.output`；done-side facts 只服务既有 policy 与 stop-reason 合成，两个来源不得混用。
- 不运行 `ruff format`。实现后运行针对性 pytest、`uv run ruff check`、`uv run pyright`；最终候选再按项目规则跑一次完整回归。
- 提交边界按语义切片，不按红绿状态；共享主树提交只用精确 pathspec，不碰其它会话的索引与 WIP。

### Task 10.1：把 action 语义建模为三态事实与 policy 投影

**Files**

- Modify: `src/app/pipeline/delivery/assembling.py:19-60`
- Modify: `src/app/pipeline/delivery/passthrough.py:38-66,79-110,145-200`
- Create: `src/app/pipeline/delivery/formats/openai_responses_actions.py`
- Modify: `src/app/pipeline/delivery/formats/openai_responses_passthrough.py:49-123`
- Modify: `src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py:40-68`
- Test: `tests/unit/pipeline/delivery/test_responses_passthrough.py:334-383`
- Test: `tests/unit/pipeline/delivery/test_anthropic_passthrough.py:96-119`

**Interfaces**

- Produces `ClientActionRequirement(StrEnum)` with `REQUIRED = "required"`, `NOT_REQUIRED = "not_required"`, `UNKNOWN = "unknown"`.
- Produces frozen `ClientAction` with fields `requirement: ClientActionRequirement`, `type: str`, `name: str = ""`, `output_index: int = -1`.
- Produces `client_action_requirement(item: dict[str, Any]) -> ClientActionRequirement` in dependency-leaf module `openai_responses_actions.py`, so both `openai_responses.py` and `openai_responses_passthrough.py` can import it without a cycle.
- Changes `Dialect` to consume `client_action_requirement: Callable[[dict[str, Any]], ClientActionRequirement]`; `RawEventBatch.requires_client_action` and `PassthroughAssembler._saw_client_action` use `requirement is not NOT_REQUIRED` as the sole bool projection.
- Keeps public per-dialect `requires_client_action(item) -> bool` wrappers for current callers and tests; each wrapper projects its classifier rather than maintaining a second classification table.

- [x] **Step 1：先实现 production 三态分类，不从 tests 反推合同。** 在 `assembling.py` 定义 enum 与 frozen record；在新依赖叶 `openai_responses_actions.py` 定义 `client_action_requirement(item)`，避免 `openai_responses.py ↔ openai_responses_passthrough.py` 循环 import：已知正例 → `REQUIRED`，已知 server-executed 反例 → `NOT_REQUIRED`，未知 type、缺 type、条件 type 缺或错 discriminator → `UNKNOWN`。`tool_search_call.execution` 只接受 `client` 或 `server`；`shell_call.environment.type` 只接受 `local` 或 `container_reference`。Anthropic 方言将 `tool_use` 分类为 `REQUIRED`，其余为 `NOT_REQUIRED`，保持现有未知 content block 的 false 语义。

```python
class ClientActionRequirement(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ClientAction:
    requirement: ClientActionRequirement
    type: str
    name: str = ""
    output_index: int = -1
```

- [x] **Step 2：把 generic engine 改读 classifier，再显式投影 bool。** `RawEventBatch` 先按 `dialect.item_index_field` 合并同一 item 在 opening 与 closing event 上的字典，再对每个 merged item 分类一次；否则 opening 上缺 `execution` 的 `tool_search_call` 会先得 `UNKNOWN`，把 closing 已明确的 `server` 错投影成 true。合并后只要任一 classification 不是 `NOT_REQUIRED`，batch property 就返回 true；没有整数 index 但带 item object 的事件单独分类。`PassthroughAssembler` 在 done 上更新 `_saw_client_action` 时同样使用投影。保留该 bool，因为 shared terminal reader 仍用它为下游合成 `tool_use` 或 `end_turn`；不要让本轮最终 action list 读取它。

- [x] **Step 3：补三态 unit tests。** 参数化覆盖 Responses 的 required、not-required 与 unknown 集，至少包括 `function_call`、`custom_tool_call`、server 与 client `tool_search_call`、local 与 container `shell_call`、缺 discriminator、未来 type 与缺 type；继续断言 wrapper 的 bool 对 `UNKNOWN` 为 true。Batch 测试必须保留 opening 缺 `execution`、closing 分别为 server/client 的成对样本，前者 false、后者 true；再加 opening/closing 都缺 discriminator 的 unknown→true 控制，证明 merge 而非常量。Anthropic 测试继续断言 `tool_use=True`、text/thinking=False，并新增 classifier 精确枚举断言，防 wrapper 与 classifier 漂移。

```python
@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"type": "function_call"}, ClientActionRequirement.REQUIRED),
        ({"type": "custom_tool_call"}, ClientActionRequirement.REQUIRED),
        ({"type": "message"}, ClientActionRequirement.NOT_REQUIRED),
        ({"type": "tool_search_call", "execution": "server"}, ClientActionRequirement.NOT_REQUIRED),
        ({"type": "tool_search_call", "execution": "client"}, ClientActionRequirement.REQUIRED),
        ({"type": "tool_search_call"}, ClientActionRequirement.UNKNOWN),
        ({"type": "future_tool_call"}, ClientActionRequirement.UNKNOWN),
        ({}, ClientActionRequirement.UNKNOWN),
    ],
)
def test_responses_client_action_requirement(item, expected):
    assert client_action_requirement(item) is expected
```

- [x] **Step 4：运行本任务验证。** Run: `uv run pytest tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_anthropic_passthrough.py -q`；expected: PASS。Run: `uv run ruff check src/app/pipeline/delivery/assembling.py src/app/pipeline/delivery/passthrough.py src/app/pipeline/delivery/formats/openai_responses_actions.py src/app/pipeline/delivery/formats/openai_responses_passthrough.py src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_anthropic_passthrough.py`；expected: clean。Run: `uv run pyright src/app/pipeline/delivery/assembling.py src/app/pipeline/delivery/passthrough.py src/app/pipeline/delivery/formats/openai_responses_actions.py src/app/pipeline/delivery/formats/openai_responses_passthrough.py src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_anthropic_passthrough.py`；expected: 0 errors。

- [x] **Step 5：记录实现 checkpoint，不提交。** 这一任务的接口会被 10.2～10.5 同一语义功能继续修改；把针对性命令与结果记在本计划，保留工作树供最终 merged-state review。

Checkpoint（2026-09-04）：`pytest` 59 passed；targeted Ruff clean；targeted Pyright 0 errors。首次运行只报新模块 I001 与 wrapper import unused，按生产接口归位 wrapper，并仅用一次 `ruff check --fix` 修新文件 import 排序后复跑通过；没有行为测试失败。绿色不是提交边界，且非平凡产物不得在独立评审前提交。

### Task 10.2：从 terminal output 建立权威 action snapshot

**Files**

- Modify: `src/app/pipeline/delivery/assembling.py:29-60`
- Modify: `src/app/pipeline/delivery/formats/openai_responses_actions.py`
- Modify: `src/app/pipeline/delivery/formats/openai_responses_passthrough.py:98-123`
- Test: `tests/unit/pipeline/delivery/test_responses_passthrough.py:401-443`
- Test: `tests/unit/pipeline/delivery/test_sse_assembly.py:520-620`

**Interfaces**

- Extends `Terminal` with `terminal_status: str = ""`, `client_actions: list[ClientAction]`, `client_action_classification_complete: bool = False`.
- Produces `read_responses_client_actions(response: dict[str, Any]) -> tuple[list[ClientAction], bool]`; list order is terminal `output` array order and `output_index` is `enumerate()` position.
- Only `openai_responses_passthrough._read_terminal()` fills these fields, and only for `response.completed`, after delegating existing stop-reason/usage work to `read_responses_terminal()`; `response.incomplete` keeps `terminal_status=""` and therefore retains the existing yellow `max_tokens` renderer path. The shared reader and translating `ResponsesAssembler` remain unchanged, so the feature cannot leak into translated routes.

- [x] **Step 1：实现 terminal snapshot reader。** If `response["output"]` is not a list, return `([], False)`; an explicit empty list returns `([], True)`. For every array element, coerce non-dict entries to `{}` so they classify `UNKNOWN`; retain an unknown native type verbatim, and use `"unknown"` only when type is absent. Use `name` only when it is a non-empty string. Never inspect assembler drafts or done snapshots in this function.

```python
def read_responses_client_actions(response: dict[str, Any]) -> tuple[list[ClientAction], bool]:
    raw_output = response.get("output")
    if not isinstance(raw_output, list):
        return [], False
    actions: list[ClientAction] = []
    for output_index, raw_item in enumerate(cast(list[object], raw_output)):
        item = cast(dict[str, Any], raw_item) if isinstance(raw_item, dict) else {}
        requirement = client_action_requirement(item)
        if requirement is ClientActionRequirement.NOT_REQUIRED:
            continue
        raw_type = item.get("type")
        raw_name = item.get("name")
        actions.append(
            ClientAction(
                requirement=requirement,
                type=raw_type if isinstance(raw_type, str) and raw_type else "unknown",
                name=raw_name if isinstance(raw_name, str) else "",
                output_index=output_index,
            )
        )
    return actions, True
```

- [x] **Step 2：只接到 passthrough adapter 的 completed 分支，不改 shared reader、wire、incomplete 或 stop reason。** `openai_responses_passthrough._read_terminal()` 先照旧调用 `read_responses_terminal()`；仅当 event 是 `response.completed` 时，再从同一 response 对象填 direct-only facts。Status 为非空字符串时逐字保存，否则由 event name 得到 `completed`。`response.incomplete` 不填新字段，继续经 `stop_reason="max_tokens"` 与既有黄色 renderer 展示。不要修改 `openai_responses.read_responses_terminal()`、`ResponsesAssembler`、`Terminal.seen`、usage conversion、incomplete-reason mapping，或 `TOOL_USE if saw_tool_call else "end_turn"` 分支。

- [x] **Step 3：写 authority、completeness 与 scope 单测。** Extend the direct completed-terminal test with explicit `output=[] → complete true, actions=[]`; parameterize missing/malformed output → false; complete `message` → true and no action; unknown type → `UNKNOWN` fact; non-object item → `UNKNOWN(type="unknown")`. Add the source-control case: done snapshots are all server `tool_search_call`, terminal output contains required function/custom calls with different names; assert stop_reason still follows done-side bool (`end_turn`) while terminal action facts all follow terminal output. This apparent disagreement is intentional: two consumers, two authorities. Add `response.incomplete` with `incomplete_details.reason="max_output_tokens"` and terminal output present; assert `stop_reason == "max_tokens"`, `terminal_status == ""`, `client_actions == []` and completeness false, pinning F01’s excluded branch.

- [x] **Step 4：保住 translating assembler。** Add a focused assertion that a Responses-to-Anthropic stream with done-side `function_call` still synthesises `tool_use`, while `terminal_status == ""`, `client_actions == []` and `client_action_classification_complete is False` even when its raw terminal response contains `output`. This proves direct-only facts are filled by the passthrough adapter rather than the shared reader, and translated delivery semantics remain unchanged.

- [x] **Step 5：运行本任务验证。** Run: `uv run pytest tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_sse_assembly.py -q`；expected: PASS。Run: `uv run ruff check src/app/pipeline/delivery/assembling.py src/app/pipeline/delivery/formats/openai_responses_actions.py src/app/pipeline/delivery/formats/openai_responses_passthrough.py tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_sse_assembly.py`；expected: clean。Run: `uv run pyright src/app/pipeline/delivery/assembling.py src/app/pipeline/delivery/formats/openai_responses_actions.py src/app/pipeline/delivery/formats/openai_responses_passthrough.py tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_sse_assembly.py`；expected: 0 errors。

- [x] **Step 6：记录实现 checkpoint，不提交。** 把 terminal snapshot 单测与 targeted static-check 结果记入本计划；保留与 10.1 相同的未提交候选，供后续传播与最终一次 merged-state review。

Checkpoint（2026-09-04）：`pytest` 112 passed；targeted Ruff clean；targeted Pyright 0 errors。Direct completed terminal 的显式空、缺席或坏类型、unknown、terminal-vs-done authority 均有断言；incomplete 与 translating assembler 的新字段保持默认。

### Task 10.3：把新 facts 无损传播到结构化记录与完成行

**Files**

- Modify: `src/app/observability/request_trace.py:147-270`
- Modify: `src/app/observability/request_log.py:103-159`
- Test: `tests/unit/observability/test_request_log_file.py:57-178`

**Interfaces**

- `RequestTrace` adds `terminal_status: str`, `client_actions: tuple[ClientAction, ...]`, `client_action_classification_complete: bool`; `absorb()` copies all three.
- `RequestLine` adds the same three frozen-record fields; `log_completion()` forwards them one-for-one.
- JSONL serialization uses existing `dataclasses.asdict`, yielding action objects as `{requirement,type,name,output_index}` and retaining the completeness bool even when false.

- [x] **Step 1：扩展 aggregate 与 immutable line。** Defaults must represent “nothing observed”: empty status, empty tuple, false completeness. Keep `tools` untouched for translated/Anthropic wording. `absorb()` converts terminal list to tuple; `log_completion()` forwards every field explicitly.

- [x] **Step 2：更新完整结构化记录 oracle。** In `test_a_successful_request_writes_one_complete_structured_record`, construct terminal facts explicitly and add the three keys to both exact key set and exact value object. Use two actions, including an unnamed one, so `asdict` shape and absence-vs-empty semantics are visible.

```python
terminal.terminal_status = "completed"
terminal.client_actions = [
    ClientAction(ClientActionRequirement.REQUIRED, "function_call", "Bash", 0),
    ClientAction(ClientActionRequirement.REQUIRED, "custom_tool_call", "", 1),
]
terminal.client_action_classification_complete = True
```

- [x] **Step 3：加一个 isolation assertion。** A terminal with legacy `tools=["Bash"]` and no new facts must keep the new fields at `""`, `[]`, `False`; this prevents generic `Terminal.record()` from accidentally fabricating direct facts and widening the feature into translated/Anthropic paths.

- [x] **Step 4：运行本任务验证。** Run: `uv run pytest tests/unit/observability/test_request_log_file.py -q`；expected: PASS。Run: `uv run ruff check src/app/observability/request_trace.py src/app/observability/request_log.py tests/unit/observability/test_request_log_file.py`；expected: clean。Run: `uv run pyright src/app/observability/request_trace.py src/app/observability/request_log.py tests/unit/observability/test_request_log_file.py`；expected: 0 errors。

- [x] **Step 5：记录实现 checkpoint，不提交。** 把结构化记录 exact-object 测试与 targeted static-check 结果记入本计划；保留候选给完成行与端到端接线继续使用。

Checkpoint（2026-09-04）：`pytest` 8 passed；targeted Ruff clean；targeted Pyright 0 errors。Exact JSONL object 现含 `terminal_status`、有序 typed actions 与 completeness；legacy `Terminal.record()` 控制确认默认仍为 `""`、`[]`、false。

### Task 10.4：按 terminal snapshot 上下文渲染 completed

**Files**

- Modify: `src/app/observability/request_log.py:31-57,162-247,338-412`
- Test: `tests/unit/observability/test_request_log.py:341-389,525-562`

**Interfaces**

- Produces `format_client_actions(actions: tuple[ClientAction, ...], *, color: bool = False) -> str`.
- Extends `format_stop_reason()` only by leaving it untouched for existing stop reasons; direct terminal status is a separate formatter path.
- Adds `format_terminal_status(status: str, actions: tuple[ClientAction, ...], classification_complete: bool, *, color: bool = False) -> str`; conditional green applies only to `status == "completed"`, completeness true, and empty actions.

- [x] **Step 1：先实现纯 presentation helpers。** Required actions render as `<type>` or `<type>(<dim/cyan names>)`; unknown actions render `client_action?(<native type>)`, or `client_action?(unknown)` when no type. An incomplete snapshot with no action appends `client_action?(unclassified)`. `completed` is painted GREEN only when complete and action-free; other known terminal statuses remain uncoloured unless the closed whitelist later names them. Reuse `_painted_tools` for action names so `AskUserQuestion` stays cyan and ordinary names stay dim.

```python
def format_terminal_status(status, actions, classification_complete, *, color=False):
    clean_completed = status == "completed" and classification_complete and not actions
    head = paint(status, GREEN, color=color) if clean_completed else status
    detail = format_client_actions(actions, color=color)
    if not classification_complete and not detail:
        detail = "client_action?(unclassified)"
    return " ".join(part for part in (head, detail) if part)
```

- [x] **Step 2：把 terminal-status branch 放在 count provider 之后、legacy stop reason 之前。** `count_provider` remains mutually exclusive. When `line.terminal_status` exists, render status/actions/completeness and do not also render synthesised `line.stop_reason` or `line.tools`; translated routes have empty terminal status and keep their exact old output. Thinking remains after the ending segment.

- [x] **Step 3：补 exact color/text tests。** Cover clean completed exact green span; completed plus required function/custom actions with dim names and uncoloured status/types; unknown native type; missing snapshot → unclassified; `AskUserQuestion` remains cyan; action order and duplicates preserved. Add regressions that `terminal_status=""` keeps existing `function_call(Bash)` output byte-for-byte, and direct `response.incomplete` still reaches the legacy `max_tokens` formatter with its yellow span rather than the new terminal-status branch.

- [x] **Step 4：运行本任务验证。** Run: `uv run pytest tests/unit/observability/test_request_log.py -q`；expected: PASS。Run: `uv run ruff check src/app/observability/request_log.py tests/unit/observability/test_request_log.py`；expected: clean。Run: `uv run pyright src/app/observability/request_log.py tests/unit/observability/test_request_log.py`；expected: 0 errors。

- [x] **Step 5：记录实现 checkpoint，不提交。** 把 presentation exact-span 测试与 targeted static-check 结果记入本计划；保留候选给真实 streaming route 验收。

Checkpoint（2026-09-04）：`pytest` 54 passed；targeted Ruff clean；targeted Pyright 0 errors。Clean completed、required actions、unknown、unclassified 与 AskUserQuestion 均有 exact span；`terminal_status` 分支显式忽略 legacy `stop_reason`，incomplete 继续黄色 `max_tokens`。

### Task 10.5：用真实 streaming `/responses` 内部路由锁住两个 source consumers

**Files**

- Modify: `tests/int/test_pipeline_app.py:15-80,1955-1975,2800-2895,3289-3343`
- Reuse production code from Tasks 10.1～10.4; no new test-only parser or proof framework.

**Interfaces**

- Adds one helper that builds raw Responses SSE from explicit opening/done/terminal item arrays; it must use `orjson` only for framing fixture bytes, never production serializers for expected log text.
- The test reads the actual request completion line through `_request_lines(caplog.records)`. Route (e) replaces the app-state chain with `replace(_chain_of(client), capabilities=TerminalCapabilities(live=False, color=True, unicode=True))`, so the same production route exposes action-name DIM spans and whether `completed` itself received GREEN; `setup_logging(colors=False)` remains responsible only for outer logger decoration.

- [x] **Step 1：扩展 fixture helper，使 done 与 terminal snapshots 可故意不同。** Define module sentinel `_OUTPUT_MISSING = object()` and signature `responses_observability_sse(*, stream_items: dict[int, tuple[dict[str, Any], dict[str, Any]]], done_order: tuple[int, ...], terminal_output: object = _OUTPUT_MISSING, unattributed: tuple[str, dict[str, Any]] | None = None) -> bytes`. Emit ordinary created/in_progress, every added snapshot in mapping insertion order, optional unattributed frame, every done snapshot in explicit `done_order`, then a `response.completed` whose response includes `output` only when `terminal_output is not _OUTPUT_MISSING`. Import `TerminalCapabilities` for the color-enabled source-control request. This helper describes bytes; it must not compute expected actions or colors.

- [x] **Step 2：实现 Spec 的五组 route 对照。** Parameterize explicit empty output plus unattributed event, complete message, missing/malformed output, and unknown future type. Add the source-control request whose terminal output is three required actions while all done snapshots are server `tool_search_call` and close 2/1/0. Assert the whole ending suffix exactly, including `client_action?(unclassified)` and `client_action?(future_tool_call)`.

- [x] **Step 3：在同一个 source-control request 上分开观察两个 consumers。** Before sending route (e), replace the app-state chain capabilities with `TerminalCapabilities(live=False, color=True, unicode=True)`. Assert the exact ANSI suffix: terminal actions and order prove action-list authority；absence of `GREEN` around `completed` while every done-side classification is `NOT_REQUIRED` proves color authority。Keep a Task 10.4 unit record with `terminal_status="completed"`, terminal required actions, completeness true and legacy `stop_reason="end_turn"`; the direct branch must ignore that stop reason for color。

- [x] **Step 4：运行集成与相邻回归。** Run: `uv run pytest tests/int/test_pipeline_app.py -q -k 'responses and (terminal or client_action or logged_in_its_own_words or output_item_this_proxy)'`；expected: selected tests PASS. Then run `uv run pytest tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/observability/test_request_log_file.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py -q`；expected: PASS。

- [x] **Step 5：执行已写入 Spec 的缺陷控制。** 先把 clean candidate 的 `openai_responses_actions.py`、`openai_responses_passthrough.py`、`request_log.py` 与 `test_pipeline_app.py` 逐文件复制到 `$CLAUDE_JOB_DIR/tmp/completed-actions-controls/`，并用 `cmp` 验证快照。逐次只改一个变量并跑同一目标测试：`clean_completed` 恒按 status 为 true、恒为 false、忽略 completeness；classifier 恒为 UNKNOWN；reader 丢掉 UNKNOWN；reader 反转 terminal output；route (e) 的 terminal output 临时换成 done snapshots；action 列仍读 terminal 但 completed 颜色改读 `line.stop_reason`。每次确认失败断言正是目标 span、suffix 或 field，立即从 candidate 快照复制回去并逐文件 `cmp`；不得后台运行 mutation，不得用 `git checkout` 或 `git restore` 恢复。最后再跑 Task 10.5 combined suite，证明没有 mutation 留在树上。

- [x] **Step 6：形成一个待评审候选，不提交。** 核对 source/test diff 只包含 10.1～10.5，记录 targeted suite 与每个缺陷控制的结果；进入 10.6 的 merged-state 独立评审。

Checkpoint（2026-09-04）：新增 route tests 6 passed；相关 merged-state suite 367 passed，mutation restore 后复跑仍为 367 passed；changed-path Ruff clean；changed-path Pyright 0 errors。实现评审前 8 个控制依次判红：status-only green、all-uncoloured、empty-actions-as-complete、missing-output-as-complete、all-unknown、drop-unknown、reverse-terminal-order、terminal-snapshot-replaced-by-done；runner 末尾逐文件核对快照并跑回核心 60 passed。实现评审修复 present-empty item 后新增第 9 个 skip-empty-item 控制，9 个 controls 全红，恢复后核心 61 passed。

### Task 10.6：合并态验证、独立评审与文档同步

**Files**

- Modify: `.dev/docs/direct-passthrough/plan.md`（本节 task 状态与证据）
- Modify: `.dev/docs/direct-passthrough/spec.md` 顶部状态与 §12 修订记录，仅在实现证据成立后从“待实现”改为“已实现”
- Modify: `.dev/docs/tui/spec.md` 顶部状态与修订记录，仅同步本切片
- Create: `.dev/docs/direct-passthrough/reports/260904-completed-client-actions-implementation-review-disposition.md`
- Modify: `.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md` only if implementation review finds a spec-level correction
- Reviewer original: write inside the reviewer’s isolated worktree because that harness cannot write the main tree’s `.dev`; distil every finding and disposition into the main-tree disposition file above

**Interfaces**

- No product interface; closes the implementation slice against the approved living Specs.

- [x] **Step 1：运行 targeted merged-state suite。** Run the Task 10.5 combined pytest command；expected: all selected tests pass。确认 Task 10.5 的 mutation 全部已经从 candidate 快照恢复，四个 snapshot files 逐个 `cmp` 相等。

- [x] **Step 2：先完成 independent implementation review 与处置。** Reviewer compares source, tests, Spec §7.1/§10 and TUI acceptance；claims list includes both action-list and color consumers reading terminal facts, done-side bool retained only for stop reason/policy, `response.incomplete`、buffered 与 translated paths unchanged, JSONL fields durable, and mutation controls failing for the intended reason。Reviewer writes its original in its isolated worktree；main session records every finding、C-level disposition and rejected route in `260904-completed-client-actions-implementation-review-disposition.md`。Use `my-skills:let-agent-review` and `my-skills:checking-review-report` until 0 blocker/major。If a finding changes relevant bytes, rerun only its affected targeted tests and mutation controls before resuming the same reviewer；do not run the full suite yet。

- [x] **Step 3：共识后的稳定候选只做一次最终验证。** Run: `uv run ruff check src tests`；expected: clean。Run: `uv run pyright src tests`；expected: 0 errors。Run: `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`；expected: PASS with coverage threshold met。These are the final candidate’s checks；do not re-run merely because unrelated HEAD moves，only when relevant bytes change。

- [x] **Step 4：最终验证后提交一个 source 语义单元。** Commit subject: `feat: report contextual Responses completion status`。用 Write 在 `$CLAUDE_JOB_DIR/tmp/source-commit-message.txt` 写入 subject。先看全局 `git diff --cached --name-status`，保留任何同伴 staged entries；再对下列同一份精确 pathspec 执行 `git add -- "${paths[@]}"`、scoped cached audit 与 `git commit -F ... -- "${paths[@]}"`。显式 add 是新文件进入 index 的必要条件；不得为清索引而 reset 或 restore，也不使用裸 commit。

```bash
paths=(
  src/app/pipeline/delivery/assembling.py
  src/app/pipeline/delivery/passthrough.py
  src/app/pipeline/delivery/formats/openai_responses_actions.py
  src/app/pipeline/delivery/formats/openai_responses_passthrough.py
  src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py
  src/app/observability/request_trace.py
  src/app/observability/request_log.py
  tests/unit/pipeline/delivery/test_responses_passthrough.py
  tests/unit/pipeline/delivery/test_anthropic_passthrough.py
  tests/unit/pipeline/delivery/test_sse_assembly.py
  tests/unit/observability/test_request_log_file.py
  tests/unit/observability/test_request_log.py
  tests/int/test_pipeline_app.py
)
git diff --cached --name-status
git add -- "${paths[@]}"
git diff --cached --name-status -- "${paths[@]}"
git commit -F "$CLAUDE_JOB_DIR/tmp/source-commit-message.txt" -- "${paths[@]}"
git show --format='%H %s' --name-status --no-renames HEAD -- "${paths[@]}"
```

Final candidate checkpoint（2026-09-04）：implementation review 首轮 1 major 已修，第二轮 0 blocker、0 major、0 minor，verdict pass；受影响回归 65 passed，修复控制目标变红，恢复后核心 61 passed；最终 `ruff check src tests` clean，`pyright src tests` 0 errors，full regression 2213 passed、2 skipped，coverage 91.29%。Source commit：`bb5783f17f8f21017010a14d00b762b49ee6cc13`。

- [x] **Step 5：同步 living docs。** Mark only Task 10a complete, record exact verification commands and reviewer verdict in this plan, and update both Specs’ status/revision records. Do not mark all §10 observability migration complete; reasoning、failure provenance and buffered reader remain outside this slice.

- [x] **Step 6：提交文档语义单元。** In `.dev`, use Write to create the commit-message file，then `git add --` the exact touched plan、Spec and disposition-report paths so the new report is known to Git；audit scoped cached paths and use a pathspec `git commit -F` with subject `docs: record contextual completed status implementation`。Do not include unrelated `.dev` WIP and do not push。

- [ ] **Step 7：判断并执行 closeout。** Load `my-skills:closing-out-work-at-a-boundary`; inspect plan/report dispositions, leave still-open direct-passthrough items in their authoritative carriers, and report code commit(s), `.dev` commit, targeted/full verification, review verdict, and any blocked item without claiming the broader direct-passthrough project complete。
