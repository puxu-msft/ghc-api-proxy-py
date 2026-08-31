# 直连 Responses 透传：实施计划

日期：2026-08-31（v6）
状态：**主体待实施**；§0 的 P1／P2 已合入 `main`（`7e96adc`），P3 未实施。骨架（顺序表第 2 步）已在 `worktree-260831-passthrough-skeleton` 落地并经独立评审修正
权威：[`spec.md`](spec.md)。**本文不定义任何用户可观察行为**——凡本文与 Spec 冲突，以 Spec 为准；凡本文出现 Spec 没有的行为承诺，那是缺陷，应移入 Spec 或删除。

> **v1 已作废并重写。** 它规定「只保存 `done.item` 的最终快照、重发 `added` + `done`、继续 mint id、沿用 framer 的 output index」，而 Spec v2 要求保存全部 item 专有事件、不得 mint id、terminal 整个对象逐字。照 v1 实施会直接违反 Spec。作废理由见 [`reports/260830-review-spec.md`](reports/260830-review-spec.md) major-08 与 [`reports/260830-review-plan.md`](reports/260830-review-plan.md)；两份报告作为时点记录不改。

## 0. 先修的既有缺陷（Spec §3.1）

它们是整条路的前置，且**两条腿共用**，所以先单独落地、单独验证。

| # | 缺陷 | 状态 |
|---|---|---|
| P1 | `_report_failure` 对含换行的 payload 写成一行 `data:` 加一行裸文本，客户端只剩第一行 | **已完成**（`7e96adc`）：新增 `encode_frame(event, data)`，每行一条 `data:` |
| P2 | `read_events` 的 frame separator 固定 `b"\n\n"`，两个合法 CRLF 帧被合并成一个事件 | **已完成**（`7e96adc`）：分隔符改为两个连续行尾，用 atomic group 防回溯把单个 `\r\n` 拆成两个 |
| P3 | `parse_frame` 用 `str.splitlines()` 拆行，其断行集是 SSE 的超集，data 里裸的 U+2028／U+2029／U+0085 会让该行从此处截断 | **未实施**：改为只认 CR／LF／CRLF。判据用一个 data 里含裸 U+2028 的帧，断言回读得到完整 payload |

P1／P2 都已变异验证：把分隔符改回 LF-only，CRLF 与 CR 两个参数变红；把 encoder 改回单行 `data:`，多行用例变红。

> P3 是骨架评审在核对 §3 承诺时发现的，机制已实跑证实、触发未证实（详见 Spec §3.1）。它与本腿的接线无关，两条腿共用，所以留在 §0 并单独落地。

## 1. 分流点

在 `delivery_policy` 计算出两种 mode，**实例化两个不同的 assembler**，而不是在 `_close` 深处散落客户端腿条件：

- `DIRECT_RESPONSES_PASSTHROUGH` —— `translation_required is False` 且两端同为 `openai-responses`
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

还要实现 Spec §7.2 的收口顺序。**先过 §5 的 replay 门**——funded replay 时 §7.2 根本不运行，旧 attempt 一个字节都不提交。真正进入收口时：丢未闭合 suffix → 按原序提交已完成 group → 末步的 carrier **按 §7.2 的 final source 表**（有上游终局就逐字提交它，没有才写 proxy error）。客户端取消与下游写失败例外。**不得**沿用现有 `stream.py` 各 ending 是否 flush 的现状。

## 5. Replay 与 commit

按 Spec §5 实现 commit frontier 与 attempt 状态重置。现有 replay 判据读的是「客户端是否已看到 semantic bytes 与 committed block」，本腿换成「首个原生事件是否已提交」。

**还要实现 Spec §5.2 的 adapter**：把 `StreamFailure` 归一化成既有 `RetryReason | None` 再交给现有 taxonomy，**不新增枚举值**。映射见 Spec 的表——`server_error` 与 `vector_store_timeout` 可重试、`rate_limit_exceeded` 走既有 rate-limit 通道、其余与未知不重试。重开 attempt 的结果按 Spec §5.2 分成 `OpenedAttempt`／`AttemptFailed`／`ReopenRefused` 三类；**`ReopenRefused`（draining、本地前置拒绝）不得进上游 taxonomy**。承载类型由本文件决定，语义由 Spec 决定。

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
4. 交错场景与 §5 的提交语义接线（**什么算「已提交」**）。纯分组与 safe-prefix 归第 2 步，本步只拥有提交语义
5. replay 合同（含 §5.2 的三类重开结果与 failure 归一化）
6. `requires_client_action` 与三种 policy（含 §7.2 的 policy × 最终 ending）
7. **分流点接线 + 撤销 `ca777df` 的直连腿一半 + 更新下述测试的断言，同一刀**
8. Headers（§9.1）
9. 可观测迁移

> **接线为什么必须合成一刀。** v3 把「接线」与「撤销 direct 的 `REJECT`」分成两步，同时又说接线之后 issue 测试应转绿、且撤销之前不要改它们的断言——三句话不能同时成立。`test_an_output_item_this_assembler_does_not_know_is_refused_not_rendered`（`tests/int/test_pipeline_app.py:2549`）当前**明确断言** direct `custom_tool_call` 以 `error` 收尾、不出现任何 `response.output_item*`；接线一旦生效，正确行为恰好相反，该测试必红。启用 direct 透传与撤销 direct 的拒绝**是同一个 observable switch**，不是两个步骤。

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

v7：**control-only 前缀不构成提交**（首帧 `response.created` 之后 replay 仍然合法——这一条直接决定四轮评审产出的 replay 合同走不走得到）；**一个 item 的事件不跨越释放边界**（反例序列 `created → added(0) → added(1) → delta(1) → done(0)`，断言 `added(0)` 不与 `done(0)` 分离）；**「无法归属」与「envelope」处置相反**（拿一个不带 `output_index` 的 audio 事件构造，断言它被持有且进入未闭合尾巴）；**draining 不花 replay 预算**（判定发生在重开之前，断言预算计数器未变）；**上游终局存在但 attempt 已作废时不得逐字重放它**。

来源：[`reports/260831-review-spec-round6.md`](reports/260831-review-spec-round6.md) round6-09、[`reports/260831-review-skeleton.md`](reports/260831-review-skeleton.md) finding 01／02。

**判据必须在实现之前独立推导**，与 issue #1 块对那次同样的理由：判据一旦被实现假设污染就不可恢复。
