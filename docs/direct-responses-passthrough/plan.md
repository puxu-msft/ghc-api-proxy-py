# 直连 Responses 透传：实施计划

日期：2026-08-31（v5）
状态：**主体待实施**；§0 的两项前置已合入 `main`（`7e96adc`）
权威：[`spec.md`](spec.md)。**本文不定义任何用户可观察行为**——凡本文与 Spec 冲突，以 Spec 为准；凡本文出现 Spec 没有的行为承诺，那是缺陷，应移入 Spec 或删除。

> **v1 已作废并重写。** 它规定「只保存 `done.item` 的最终快照、重发 `added` + `done`、继续 mint id、沿用 framer 的 output index」，而 Spec v2 要求保存全部 item 专有事件、不得 mint id、terminal 整个对象逐字。照 v1 实施会直接违反 Spec。作废理由见 [`reports/260830-review-spec.md`](reports/260830-review-spec.md) major-08 与 [`reports/260830-review-plan.md`](reports/260830-review-plan.md)；两份报告作为时点记录不改。

## 0. 先修的两处既有缺陷（Spec §3.1）

它们是整条路的前置，且**两条腿共用**，所以先单独落地、单独验证。

| # | 缺陷 | 状态 |
|---|---|---|
| P1 | `_report_failure` 对含换行的 payload 写成一行 `data:` 加一行裸文本，客户端只剩第一行 | **已完成**（`7e96adc`）：新增 `encode_frame(event, data)`，每行一条 `data:` |
| P2 | `read_events` 的 frame separator 固定 `b"\n\n"`，两个合法 CRLF 帧被合并成一个事件 | **已完成**（`7e96adc`）：分隔符改为两个连续行尾，用 atomic group 防回溯把单个 `\r\n` 拆成两个 |

两项都已变异验证：把分隔符改回 LF-only，CRLF 与 CR 两个参数变红；把 encoder 改回单行 `data:`，多行用例变红。

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

`main` 上 `ca777df` 把翻译腿的「未知 item → REJECT」套用到了直连腿，是定义域误用（Spec §2.4）。透传落地后，直连腿不再有「未知」这个状态——所有 item 一律携带。**翻译腿的 REJECT 保留。**

## 8. 顺序

1. ~~P1、P2~~ **已完成**（`7e96adc`）
2. 透传 assembler／framer **骨架**，不接线。只跑单元 smoke，**不宣称任何 issue 测试转绿**
3. **分流点接线 + 撤销 `ca777df` 的直连腿一半 + 更新那两条测试的断言，同一刀**
4. commit frontier 与交错
5. replay 合同（含 §5.2 的三类重开结果与 failure 归一化）
6. `requires_client_action` 与三种 policy（含 §7.2 的 policy × 最终 ending）
7. Headers（§9.1）
8. 可观测迁移

> **第 3 步为什么必须合成一刀。** v3 把「接线」与「撤销 direct 的 `REJECT`」分成 step 2 与 step 7，同时又说 step 2 之后 issue 测试应转绿、且 step 7 之前不要改它们的断言——三句话不能同时成立。`test_an_output_item_this_assembler_does_not_know_is_refused_not_rendered` 当前**明确断言** direct `custom_tool_call` 以 `error` 收尾、不出现任何 `response.output_item*`；接线一旦生效，正确行为恰好相反，该测试必红。启用 direct 透传与撤销 direct 的拒绝**是同一个 observable switch**，不是两个步骤。

## 9. 验收

Spec 每一条规范性要求各自需要一条可失败的判据，尤其：多行 data、空 data、未知事件类型、未知字段、id 逐字（含上游不一致）、terminal 整对象、交错 item 不重排、首个原生事件提交前后的 replay 差异、三种 policy 的释放时点、cap 按持有计量。

v5 新增的承重点同样各要一条，它们只在正文出现过：**funded replay 时不收口**（已完成 group 一个字节都不提交）、**policy × 最终 ending** 的三行差异、**已知 native failure code** 的归一化（`server_error` 与 `rate_limit_exceeded` 分别走哪条路）、**`ReopenRefused` 不进上游 taxonomy**、**`Connection` 动态点名的字段被剥离**、**表征元数据按语义判据剥离**（含 `Content-MD5` 这种不在名单里的）。

**判据必须在实现之前独立推导**，与 issue #1 块对那次同样的理由：判据一旦被实现假设污染就不可恢复。
