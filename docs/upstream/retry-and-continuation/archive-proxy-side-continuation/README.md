# 归档：代理内续写（已裁决放弃）

**裁决日期**：2026-08-21。**裁决人**：用户。**权威**：`docs/.human-controlled/upstream-retry-and-continuation.md` 的「代理内续写（已放弃）」一节。

这个方向做的事是：上游把一条流式回复截断之后，**由代理自己**带上已提交的块、补一条 `role: user` 的续写消息，向上游重新发起请求，让客户端察觉不到。它被放弃了，取而代之的是 MCP-driven 续写——代理把错误合成为一个工具调用块交回客户端，由**客户端自己的对话历史**去承载续写。

## 为什么放弃

不是因为它做不出来，是因为它要付的代价在换了方案之后**整片消失**了。

`reports/spec-stream-continuation.md` 经三轮独立评审（11 + 7 + 1 条发现全部采纳；原文 `:3` 的「18」已是前两轮之和）之后，把启用它的前提收敛成四条，其中第 4.3 条**没有解**：

> 不借助上游提供的 resume cursor 或幂等 generation identity，无法可靠区分「模型在重复前缀」与「模型有意重复同一句话」。

该文考察的四个方案（不抑制、块级摘要去重、文本前缀重叠裁剪、只上报不删除）没有一个能讨清这条前提，其中方案 D 还被证明在任何 eligible 的 continuation 上**退化成等于方案 A**——它显得更强，是靠一条走不到的分支。该文作者因此主观推荐先不启用，并把是否接受「自由文本重复对客户端可见」这个新增代价列为待用户裁决的第 1 项。

用户的裁决没有停在「接受还是不接受这个代价」上，而是**换掉了承载续写的那一侧**。MCP-driven 方案下：

- **4.1（可证明的 resume contract）作废**——续写请求由客户端构造，不需要代理证明自己能重建它。
- **4.2 的一半作废**：稳定语义身份、内容摘要、carrier digest 是为了把已提交的块回放给上游并做去重，而客户端的 transcript 本来就是权威，这部分不再需要。**但「有一个可读的 committed frontier」不作废**——MCP-driven 的那道门（已交付过至少一个完整块）正要靠它，而它今天还读不出来（见 `../status.md` 的现状表）。原文 `:97` 把它称作「独立 commit state」。
- **4.3（重复前缀 suppression）作废**——模型仍可能重述，但那是一次**正常对话里的正常重述**，发生在客户端可见的历史上，不是代理偷偷修补出来的产物。没有东西需要被抑制，也就没有那个无解的判据。
- **4.4（tool/reasoning 安全条件）作废**——`tool_result` 一直在客户端手里，代理拿不到它才是原方案必须 ABANDON 的理由。

## 哪些结论没有被推翻，仍然有效

归档的是**方案**，不是它查出来的事实。下面几条仍然成立，新方向直接继承：

- **恢复裁决必须读「我们已经收到了什么」，不能读异常类型**（`../../h2-goaway/findings.md` 的设计推论）。干净 EOF 与连接撕裂把客户端留在同一个位置，位置才是判据。
- **本侧结束不等于上游失败**（原文的 `LOCAL_ABORT`）。客户端断开、进程退出、我方主动放弃，与上游截断的**位置事实完全可能相同**，所以位置事实不足以决定恢复资格，起因必须在发生处记下。用户 2026-08-21 已把这一条写进人写文档的「无法继续」一格。
- **一次请求只有一个 `message_start`；中间 attempt 绝不向下游发终止性帧**（原文 5.1）。这条对无痕重试同样适用，与续写方案的取舍无关。
- **每个 attempt 必须新建 assembler、`Terminal` 与 attempt-local buffer；已提交 frontier 不得回退。**
- **后续 attempt 的身份不得泄漏到 wire**：downstream `message_id`、model、HTTP status 与已提交 response headers 在首个可见 batch 后冻结，后续 attempt 的 response id、model、status、request id、rate-limit headers 只进 attempt diagnostics。否则一条 Anthropic message 会呈现为两条上游 response 的拼接。
- **每个 attempt 有自己的 `deadline_at`**（`context.begin_attempt()`），不得沿用前一 attempt 已过期的 deadline。
- **一条接线陷阱，原文明写「最容易在接线时踩」**：若把每个 attempt 分别交给现有 `stream_delivery`，它在第一次 EOF 就会发出 `error` 并返回，wire 从此不可恢复。原文强调**无痕重试同样会踩**，所以这条不能等到续写启用才生效——它现在就约束 D 阶段。
- **`usage` 不累加**——这一半仍然成立。

**下面这条不再成立，列在这里免得被当成仍然有效**：原文的「`usage` 只取最终成功 attempt」预设一次下游 message 可以横跨多个上游 attempt，而 MCP-driven 下每条下游 message 只对应一个 attempt，且它是失败的那个。新方向报的是**那次失败 attempt 上游实报的值**（见 `../status.md` 与 `../decisions.md`）。前提被拆掉了，结论跟着走。

## 目录

| 文件 | 是什么 |
|---|---|
| `reports/spec-stream-continuation.md` | 行为 Spec 切片第 4 版，未冻结。四个启用前提的完整论证，以及八项待用户裁决 |
| `reports/260821-plan-g2-wire-stream-ending.md` | G2 实现方案草案：把截断恢复的裁决接到线上 |
| `reports/260821-poc-continuation-reasoning-echo.md` | PoC：续写请求能否原样回传加密 reasoning（结论：可以）。**该 PoC 的价值随方案一并作废**——MCP-driven 下 reasoning 由客户端回传，不经代理构造 |
| `reports/260821-review-g2-spec-draft.md` | 上述 Spec 草案的独立评审 |

**报告原件逐字保留，不因归档而改写**——包括其中指向旧路径的引用。那些是时间点记录，改写它们等于篡改引文。

## 与之相邻、但没有被归档的

- `../../h2-goaway/` —— GOAWAY 打掉在飞流的机理诊断。该主题已收口，本次裁决不影响它的任何结论。
- `../../../tmp/260821-truncated-anthropic-stream-diagnosis.md` —— 触发整个切片的生产事故（req d3b7f5ba）。事故本身没有被推翻，它是新方向的事实基础之一。
- G1（让活跃链路认出上游发来的错误事件，分支 `fix/upstream-error-events`）—— **没有被推翻，而且新方向更需要它**：`stop_reason` 要原样透出、上游 `error` 帧不能再被静默丢弃，都依赖它。该分支在同伴的独立 worktree 中在飞，其计划与评审文档保持原位未动。
