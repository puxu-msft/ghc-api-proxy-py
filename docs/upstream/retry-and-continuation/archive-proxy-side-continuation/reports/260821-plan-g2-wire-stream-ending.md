# G2 修复方案：把截断恢复的裁决接到线上

**日期**：2026-08-21。**性质**：实现方案草案。三个产品分叉**用户已于 2026-08-21 全部裁决**（见下），加密 reasoning 回传的 PoC 已完成。**代码未开工**——待 Spec 切片。
**上游诊断**：`.dev/docs/tmp/260821-truncated-anthropic-stream-diagnosis.md`（req d3b7f5ba）。**上级文档**：`.dev/docs/upstream/h2-goaway/findings.md` 的「在建」表。

> **G1 已落地，本方案的一处前提因此变了。** 上游明确失败现在会被记录为 `Terminal.failure`（分支 `fix/upstream-error-events`，`eb6cdd6`）。接线 G2 时，**`terminal.failure is not None` 必须映射到 ABANDON，不是 CONTINUE**——上游明确拒绝不是截断，续写它是浪费，参考实现正是为此加了一道否决。`decide_stream_ending` 目前只读 `terminal_seen`，需要同时读 `failure`。

## 先纠正一件事：悬空的不止一个函数

`findings.md` 把这笔欠账记成「`decide_stream_ending` 函数已就绪、无调用者」。实测范围更大——**整套截断恢复机器在 `src/` 下都没有生产调用者**：

| 零件 | 位置 | 生产调用者 |
|---|---|---|
| `decide_stream_ending` | `src/app/pipeline/retry.py:138` | **无**（仅 `tests/unit/pipeline/test_stream_ending.py`） |
| `continuation_messages` | `src/app/pipeline/retry.py:108` | **无**（仅 `tests/unit/pipeline/test_retry_strategies.py`） |
| `PipelineRetry` | `src/app/pipeline/exceptions.py:86` | **从未被 raise** |
| `RetryReason.STREAM_REPLAY` | `retry.py:29` | 只在 `retry.py` 内部与 `reason_for` 里出现，而 `reason_for` 认它的唯一入口是 `PipelineRetry`，那个异常没人抛 |
| `RetryReason.CONTINUATION` | `retry.py:30` | 同上 |

**直接后果**：配置键 `upstream_request_retry.strategies.streamReplay.max_retries=100` 与 `continuation.max_retries=10` **当前控制不了任何东西**。接线的那一刻它们会同时生效——见下面的裁决 B/C。

## 结构上的真正障碍

`DirectDriver._send()` 的 await **止于响应头到达**（`src/app/pipeline/direct_driver/base.py:228` 的 docstring 明写这是刻意设计，2026-08-20 实测过），随后 `run()` 返回、`handle()` 返回、`_serve()` 构造 `_AccountedStreamingResponse` 返回——**流式 body 是在 driver 完全出栈之后才被消费的**（`src/app/server/pipeline_app.py:401-447`）。

所以「重开一次 attempt」在今天的结构里**不可达**：交付层手里只有一个字节迭代器，没有任何东西能让它再要一个上游响应。这不是加一个 `if` 的事。

## 接线需要的六件事

### 已经现成的（不用做）

判据的两个输入都已存在于交付层：

- `downstream_opened` → `DeliverySession.started`（`src/app/pipeline/delivery/blocks.py:137`），或 `stream.py` 里的 `client_has_bytes`；
- `committed_blocks` → `DeliverySession.committed_count`（`blocks.py:141-142`）；
- `continuation_messages` 要的 `committed` → `[b.payload for b in session.delivered]`，`CompletedBlock.payload` 正是 Anthropic 内容块的形状。

### 要做的

**1. 把「重开一次 attempt」的把手交到交付层。** 今天 `stream_delivery(chunks, assembler, ...)` 只收字节迭代器。两种形态：
- **(a) 可续源**：在字节层之上包一个 source，它持有 `driver` / `context` / `ledger`，在干净 EOF 或撕裂且无终止事件时调 `decide_stream_ending`，判 CONTINUE 就用续写 payload 重开一次 attempt，把新流的事件继续喂给交付层。交付层与下游 SSE 会话不重建。
- **(b) 把 body 消费搬回 driver 循环内**。改动面大得多，且要推翻「`_send` 止于 headers」这个刻意设计。**不推荐。**

**2. 块索引连续性——这是最容易被漏掉的正确性问题。** 下游 `content_block_start` 的 `index` 直接取 `block.index`（`src/app/pipeline/delivery/anthropic_sse.py:117`），而 assembler 每个 attempt 从 0 开始编号。续写 attempt 的第一个块会**再发一次 `index: 0`**，客户端按 index 归位内容块，结果是覆盖或报错。需要以 `session.committed_count` 为基准做索引偏移。

**3. 守卫与记账跟着新 attempt 走。** `with_deadline_at` 读 `attempt.deadline_at`（`pipeline_app.py:425-431`），续写 attempt 要走 `context.begin_attempt()` 拿新 deadline。`trace.bytes_in` / `upstream_conn` / `attempts` 现在都在 `pipeline_app.py:396-399` 从**第一个** response 上一次性读取——续写后是累加、还是只记最后一次，这是个展示裁决（影响请求行与 JSONL 记录的口径）。

**4. 两条腿的续写请求形状不同。** `continuation_messages`（`retry.py:108-120`）产出的是 `[{"role":"assistant","content":…},{"role":"user","content":…}]`——**Anthropic 的形状**。Responses 腿的上游 payload 用的是 `input` 数组而非 `messages`，直接套用会发出上游读不懂的请求。本次事故是 Anthropic 腿，所以可以先只接 Anthropic 腿并**显式**在 Responses 腿上判 ABANDON，但那必须写下来，不能默认它能用。

**5. 加密 reasoning 的回传合法性（已验证，2026-08-21）。** ~~这一条我没有验证过，是接线前必须做 PoC 的一点。~~ **PoC 已完成，结论是可以回传**：真实 Copilot `/v1/messages` 接受 `{"type":"thinking","thinking":"","signature":"<原签名>"}` 的 assistant 续轮并返回 200，签名改动一个字符即 400。空 `thinking` **不会**像空 `text` 那样被拒——前提是签名非空且**原样保留**。限制：该探针用的是 `claude-opus-4.8`，不是本次事故的 `claude-opus-5`，属外推。全文与两条腿的构造形状见 `260821-poc-continuation-reasoning-echo.md`。

**6. 行为变化需要 Spec。** 项目规则要求「改变可观测行为前先有冻结的 Spec」。截断后自动续写是显著的可观测行为变化（客户端会看到一条被补完的消息，而不是一次失败），需要一个 Spec 切片，不能当作纯接线做掉。

## 三个产品分叉——**用户已于 2026-08-21 全部裁决**

**A. 续写这个行为本身要不要。** → **要，做。**
它让代理替上游把一次截断补成完整回答，代价是**把整个上下文再发一遍**——本次是 951KB。`findings.md` 记的 2026-08-20 裁决「成本不构成理由」针对的是 **headers 之前**撕裂的重试（那次 attempt 已经花掉了，不重试也退不回来）；续写是**新增**一次完整上下文的开销，不在那条裁决的覆盖范围内，所以单独裁了这一次。

**B. 接线后立刻生效的默认值。** → **保持现值，不下调。**
`continuation.max_retries=10`（`src/app/config/schema.py:158-184`）。最坏情况是 10 次续写 × ~1MB 上下文，用户接受。

**C. REPLAY 那条路同样立刻生效。** → **保持 `streamReplay.max_retries=100`。**
它只在客户端一无所见时合法，代价比续写低（没有额外的 assistant turn）。

## 在哪里做

**不要在当前共享工作树里就地做。** 2026-08-21 观测：并行会话正在提交（HEAD 从 `fce9311` 前进到 `9222ea7`，httpx2 迁移 + stream cap），索引中有它暂存的改动（`composition.py`、`subscribers/`、`upstream/stream_cap.py`、`config/schema.py` 均为 `MM`）。本方案要动的 `pipeline_app.py` / `stream.py` / `blocks.py` 目前不在它手里，但重叠随时可能发生。

建议隔离工作树 + squash 集成，按项目 Git 约定办。
