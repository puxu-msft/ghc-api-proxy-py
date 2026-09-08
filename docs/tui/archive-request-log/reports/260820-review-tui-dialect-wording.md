# 评审报告：请求日志的上游用词区分（2026-08-20）

评审对象：工作树中「日志用词跟随上游」这一改动（`ReplyDialect` / `dialect_for` / `reply_summary` / `format_thinking` / `format_stop_reason` 及相应测试）。

评审者：异源模型 agent（gpt-opus），角色为代码评审者。**该 agent 的 harness 禁止其创建文件**，因此本报告由派发方（本会话）按其返回内容转写，并逐条附上**我的复核结论与处置**——转写不等于采纳。

判定基线：全量 1307 passed / 2 skipped，`ruff check src/ tests/` 与 pyright 干净。

---

## 结论

评审给出 needs-fix：1 major、2 minor、1 nit。我逐条复核后：**major 部分成立但归因需要拆开**，两条 minor 与 nit 采纳（其中一条以文档修正而非代码改动处置）。

---

## Major：缓冲路径把客户端形状的 payload 一律当 Anthropic 读

**评审原述**：`pipeline_app` 在 `response_payload()` 把响应翻译回**客户端**格式之后，无条件用 `terminal_from_anthropic` 汇总。该 payload 只有 Anthropic 客户端路径才是 Anthropic 形状。受影响的是 `/responses` 入站的两条路由，实测得到 `openai-responses/gpt-model ... end_turn`，而本应含 `reason(enc:1)` 与 `function_call(Bash)`。

**我的复核**：现象复现成立（mock 上游，`/responses` 入站，upstream 返回 reasoning + function_call）。但归因必须拆成两件事，因为处置不同：

| 现象 | 归属 | 处置 |
|---|---|---|
| 行上出现 `end_turn` | **本次引进的回归**（`f8f5854`） | 已修 |
| 汇总为空（无 `reason` / `function_call`） | **既存缺陷**，非本次引入 | 记入 `deferred.md`，未在本切片修 |

回归的证据：`git show f5a7a8b:src/app/server/pipeline_app.py` 中 `trace.stop_reason` 默认 `""`，且仅当 payload 带 `stop_reason` 键时才赋值——Responses 形状的 body 没有该键，那行**不显示**结束原因。`f8f5854` 引入 `Terminal` 后，其类默认值 `stop_reason="end_turn"` 经 `absorb` 进入日志行，于是这行开始**声称一个上游从未说过的结束原因**。这比「少显示信息」严重：它是无证据的断言。

汇总为空是既存的：`blocks_from_anthropic` 读 `body["content"]`，Responses 形状的 body 只有 `output`，改动前后都读不到。

**处置**（两处保护，各自成立，互相冗余）：

1. `terminal_from_anthropic` 的 stop reason 从空串起步，只在 body 确实说了时才赋值。理由写在 docstring 里：流没发终端事件时合成 `end_turn` 是有依据的，而 body 根本没带这个字段意味着**没人说过**。
2. 新增 `handler.reply_summary`，由它持有「这个形状能不能读」这一判断；读不了返回 `None`，而不是返回一条「这个回复什么都没有」的空记录。`context.reply` 是本次刚建立的公共聚合点，`None`（没读）与空记录（读了、是空的）是两个不同的事实。

**关于评审建议「根据 `target_format` 从 upstream body 汇总」——未采纳**。理由：usage 数字目前取自**翻译后**的 payload，键是 Anthropic 的（`cache_read_input_tokens` 等），`format_tokens` 依赖这套键；改从 Responses 原始 body 读，usage 键变成 `input_tokens_details.cached_tokens`，会让所有已通过的翻译路由的 token 列失真。正确的做法是给 `/responses` 入站补一个**同形状的读取器**（`blocks_from_responses` + Responses 的 usage/stop reason 读法），那是一个独立切片，已记入 `deferred.md`。在本切片里按 `target_format` 换读取器会同时改动主产品路径的数字，得不偿失。

**测试**：`test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it`（mock 上游）。需要说明其鉴别力的性质：由于上述两处保护**互相冗余**，单独移除任一处该测试都不变红；**同时移除两处**（即回到缺陷状态）才变红，已实测确认。这不是测试无力，而是「充分条件有两个，各自都不是必要条件」的正常后果。

## Minor 1：`dialect_for` 把所有非 Responses 目标静默归为 Anthropic

**评审原述**：catch-all 同时覆盖 `OPENAI_CHAT_COMPLETIONS` 与 `OPENAI_EMBEDDINGS`，`Terminal.dialect` 与 `ReplyDialect` docstring 声称的来源事实已不真。

**我的复核与处置**：现象属实，但**不改代码，改文档**。因为 `assembler_for` 本来就把一切非 Responses 的上游交给 `AnthropicAssembler`（既存行为，非本次引入），而 `dialect_for` 现在正是 `assembler_for` 的分派依据——两者一致，方言标签如实描述了 assembler 实际做了什么。为 Chat 造一套第三方言，需要先有 Chat 自己的 assembler，否则那套词汇没有对应的事实。已在 `dialect_for` 的 docstring 中写明这一点。

**不采纳「显式区分受支持的两种 dialect 与其它格式」**：那会引入一个当前没有任何行为差异、也无法被测试区分的第三状态，属于为假想扩展预留结构。

## Minor 2：`responses_sse_upstream()` 的 docstring 描述不成立

**评审原述**：docstring 称用词「由 route 决定而非 wire 上的任何东西」，但流式测试实际依赖 Responses frames 被 `ResponsesAssembler` 识别并关闭，`Terminal.dialect` 来自 assembler。

**采纳**。已改写为：它验证的是**已知事件契约下**的 route → assembler → 日志接线，不对 Copilot 真实 wire 行为作主张；真实上游的怪癖（item id 不稳定、chunk 边界）仍归 cassette。评审同时确认手写 mock 在此恰当、不建议换成真实上游或 cassette——与用户 2026-08-20 的裁定一致。

## Nit：「upstream's own word」并非字面事实

**采纳**。真实对象名是 `thinking` 与 `reasoning`，`think` / `reason` 是为控制行宽所做的缩写。相关注释与 docstring 已改为「abbreviated from each upstream's vocabulary」一类表述。

## 评审明确不建议采纳的事项（我同意，一并记录）

- 不因 `"tool_use"` 字符串识别而重构：当前两种方言下无误伤实例，两侧行为均已被单测固定。
- 不为 count_tokens、路由失败、retry、非 200 单独增加方言测试：这些路径没有可渲染的回复内容汇总，不会暴露错误用词。
- 不改用真实上游测试。

---

## 过程中发现的一件事（与评审无关，但必须记录）

做变异对照时我采用了「快照源文件 → 改 → 还原」的手法，而**同伴会话正在同一个 `handler.py` 里工作**（其 `fix_anthropic_request` 增加 `upstream_is_anthropic` 参数的改动）。还原后的字节比对为 False，说明窗口期内该文件被他人写过。事后核对确认**没有造成损失**：`anthropic_request_hook.py` 中该函数的必填关键字参数与 `handler.py` 的调用点匹配，若被覆盖则每个请求都会抛 `TypeError`；全量测试亦通过。

但这是侥幸。**结论：在共享检出里，不要对可能被并行编辑的源文件做快照—改—还原式变异测试**；应当在临时副本或独立 worktree 中进行。
