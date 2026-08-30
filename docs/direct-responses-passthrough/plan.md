# 直连 Responses 透传：实施计划

日期：2026-08-30（v2）
状态：**待实施**，等 Spec v2 复评通过
权威：[`spec.md`](spec.md)。**本文不定义任何用户可观察行为**——凡本文与 Spec 冲突，以 Spec 为准；凡本文出现 Spec 没有的行为承诺，那是缺陷，应移入 Spec 或删除。

> **v1 已作废并重写。** 它规定「只保存 `done.item` 的最终快照、重发 `added` + `done`、继续 mint id、沿用 framer 的 output index」，而 Spec v2 要求保存全部 item 专有事件、不得 mint id、terminal 整个对象逐字。照 v1 实施会直接违反 Spec。作废理由见 [`reports/260830-review-spec.md`](reports/260830-review-spec.md) major-08 与 [`reports/260830-review-plan.md`](reports/260830-review-plan.md)；两份报告作为时点记录不改。

## 0. 先修的两处既有缺陷（Spec §3.1）

它们是整条路的前置，且**两条腿共用**，所以先单独落地、单独验证。

| # | 缺陷 | 判据 |
|---|---|---|
| P1 | `_report_failure` 对含换行的 payload 写成一行 `data:` 加一行裸文本，客户端只剩第一行 | 新增接受 `(event, data)` 的 raw-text SSE encoder，按 `data.split("\n")` 每段一条 `data:`；测试用多行 payload 走一个完整往返 |
| P2 | `read_events` 的 frame separator 固定 `b"\n\n"`，两个合法 CRLF 帧被合并成一个事件 | 修正边界判定；测试喂两个 CRLF 帧，断言得到**两个** `SseEvent` |

P1、P2 各自是完整语义单元，可先于主体合并。

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

按 Spec §7.1 实现，判据取自**原始请求的 tool declaration 与 execution mode** 加上响应 item type。所以需要一条从请求侧到交付侧的数据通路（Spec §11 第 3 项，通路本身待定）。

实现可以维护一张由 SDK 版本导出的表，但**表是判据的当前编码，不是判据本身**；未知类型按 Spec 保守视为需要释放并记 `predicate unknown`。

## 5. Replay 与 commit

按 Spec §5 实现 commit frontier 与 attempt 状态重置。这一块**没有现成代码可改**——现有 replay 判据读的是「客户端是否已看到 semantic bytes 与 committed block」，本腿要换成「首个原生事件是否已提交」。

## 6. 可观测

按 Spec §10：wire 走原生，可观测另立旁路 typed facts。`Terminal` 在本腿只作内部摘要，不得反推 wire。

需要迁移的既有事实：item 计数、需要客户端行动的 tool 名、reasoning 是否出现、权威 terminal status 与 usage、failure/截断/replay 来源。

## 7. 撤销 `ca777df` 在直连腿的那一半

`main` 上 `ca777df` 把翻译腿的「未知 item → REJECT」套用到了直连腿，是定义域误用（Spec §2.4）。透传落地后，直连腿不再有「未知」这个状态——所有 item 一律携带。**翻译腿的 REJECT 保留。**

## 8. 顺序

1. P1、P2（各自可独立合并）
2. 分流点 + 透传 assembler/framer 骨架，只跑通「无交错、无 replay」的正常流
3. commit frontier 与交错
4. replay 合同
5. `requires_client_action` 与三种 policy
6. 可观测迁移
7. 撤销 `ca777df` 的直连腿一半

第 2 步之后就应该能让 issue #1 与 issue #2 的直连腿复现用例转绿，**但在第 7 步之前不要动那两条测试的断言**——它们当前钉的是拒绝行为，改断言要与撤销同一刀。

## 9. 验收

Spec 每一条规范性要求各自需要一条可失败的判据，尤其：多行 data、空 data、未知事件类型、未知字段、id 逐字（含上游不一致）、terminal 整对象、交错 item 不重排、首个原生事件提交前后的 replay 差异、三种 policy 的释放时点、cap 按持有计量。

**判据必须在实现之前独立推导**，与 issue #1 块对那次同样的理由：判据一旦被实现假设污染就不可恢复。
