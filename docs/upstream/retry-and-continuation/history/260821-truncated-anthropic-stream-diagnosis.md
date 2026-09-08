# 一条 Anthropic 腿的流被上游干净截断（req d3b7f5ba）

**日期**：2026-08-21。**性质**：单次生产事件的诊断，四条主张经异源评审（gpt-opus）逐条证伪未果，判定全部成立。
**上级文档**：`.dev/docs/upstream/h2-goaway/findings.md`。本次形态与那份记录的 GOAWAY 事故**不同**（见下），但撞上的是它「在建」表里那笔待接线欠账。

## 事件

```
[FAIL] 12:55:46 H1/H2 200 POST /v1/messages claude-opus-5 33.2s ↑951.0KB ↓6.5KB think(enc:1): upstream stream ended without a terminal event req=d3b7f5ba-330c-4183-b442-cf7c1c749b14
```

结构化记录：`~/.local/share/ghc-api-proxy/requests/requests-20260821.jsonl` 第 1675 行。要点：`dialect: "anthropic"`、`terminal_seen: false`、`stop_reason: ""`、`usage: {}`、`blocks: 2`、`thinking: ["enc"]`、`tools: []`、`attempts: 1`、`first_upstream_byte_s: 2.53`、`duration_s: 33.2`、`upstream_conn: {peer: 140.82.114.22:443, alpn: h2, stream_id: 7}`。

控制台那一行没印 `dialect`，而它是本次最关键的一个字段：**走的是 Anthropic 方言腿，不是 Responses**，因此应到的终止事件是 `message_delta` + `message_stop`。

## 判据落在哪一格

`_StreamAccounting._ending()`（`src/app/server/pipeline_app.py:501-514`）分三格，本次落 `drained`：上游 SSE body **正常耗尽、无异常**。`drained` 只在 `_tracked_delivery` 的 `async for` 自然结束后置位（`pipeline_app.py:571-583`），任何异常都会写进 `failure` 并改用另一句文案。

## 已排除

| 被排除项 | 依据 | 强度 |
|---|---|---|
| 我方 idle / deadline 守卫 | `with_idle_timeout` 抛 `StreamIdleTimeoutError`、`with_deadline_at` 抛 `StreamDeadlineError`（`src/app/streaming/idle_timeout.py:34-47`、`deadline.py:32-44`），均为 `Exception`，只能进 `failure` 格 | 确凿（构造性） |
| 任何 30s 级配置上限 | 有效配置 `stream_idle=0`（守卫**未启用**）、`upstream_request_deadline=1200`（`src/app/config/schema.py:145-152`），用户配置未覆盖 | 确凿 |
| 时长本身异常 | 同文件前 1675 行内 112 条 >30s，其中 108 条 `ok`；同模型 87 条 >30s 成功，最长 313.9s | 确凿 |
| 上行体量 / 模型 | 同一条 h2 连接上紧邻的 sid 1/3/5 为 941/946KB 同规模同形请求，全部 ~11.5s 以 `stop_reason=tool_use` 正常完成 | 强，足以行动 |

## 上游侧：能说的只有这么窄

上游发出 2 个完整块（1 个加密 thinking + 1 个块）、累计 6.7KB 之后**干净地结束了这条 h2 流**，`message_delta` 与 `message_stop` 都没到。

**与 2026-08-20 那次 GOAWAY 事故形态不同**：那次是 `httpcore.RemoteProtocolError: <ConnectionTerminated …>`（异常格），本次是干净 EOF。**不得据此把本次归入 GOAWAY**。

「谁关的、为什么关」按用户 2026-08-20 裁决属**我方原理上不可判定**，不再作为待查项。

弱证据一条，**不足以支撑任何结论**：这条连接此后未再出现，13:10 换用 `140.82.113.21`——但中间 15 分钟无流量，连接池自然过期给出同样表象。

## 三处我方缺口

### G1 上游即使说了原因，活跃链路也听不见

`AnthropicAssembler.push`（`src/app/pipeline/delivery/assembler.py:127-145`）对 Anthropic SSE `error` 事件无分支，静默 `return ()`；`ResponsesAssembler.push`（同文件 :218-236）只认 `response.completed` / `response.incomplete`，**不认 `response.failed`，也不认 `error`**。legacy 的 `src/app/openai/responses_stream_parser.py:215-223` 两者都当终止事件。

链路上没有第二个 observer：`sse_source.py:34-83` 只做机械解析，`stream.py:223-249` 把事件交给 assembler 后不再看，`_counted_upstream`（`pipeline_app.py:549-559`）只累计字节，请求日志只吸收 assembler 的 `Terminal` 摘要（`:484-499`），history schema 无 frame 字段（`src/app/history/sqlite/schema.py:1-16`）。

**后果**：「上游报了 overloaded_error 后关闭」与「上游一声不吭地关闭」在我方观测里**完全同形**。本次究竟是哪一种，**不可知**——目标 `request_id` / `message_id` 在 `history.db` 中无匹配，全仓没有 raw-frame recorder。

### G2 三条路的裁决仍未接线，而本次预算是够的

`decide_stream_ending`（`src/app/pipeline/retry.py:138-177`）在 `src/` 下**零调用者**，仅 `tests/unit/pipeline/test_stream_ending.py:14,29` 引用。`findings.md:89-94` 的「在建」表登记为「函数已就绪、无调用者」。

本次落在它的 CONTINUE 格：`terminal_seen=false`、`downstream_opened=true`、`committed_blocks=2`。有效 buffering policy 为 `block`，每个已闭合块立即 commit（`src/app/pipeline/delivery/blocks.py:87-107`），且本次走到 `drained`，排除客户端中途停拉，故这两个推断成立。

**预算不是 0**：`max_total=20`、`continuation.enabled=true`、`continuation.max_retries=10`（`src/app/config/schema.py:158-184`），bundled 与用户配置均未覆盖；本次 `attempts=1` 未消耗预算。**所以接线会改变本次结果，而不是「接了也照样 ABANDON」。**

### G3 失败的 turn 没有账

`usage: {}`——951KB 上行的 token 花销一个数都没留下，因为 `context.reply` 仍 gate 在 `terminal.seen`（`pipeline_app.py:490`）。已登记在 `docs/agents/anthropic-responses-bridge/implementation.md` 的结构怪味表，待与 hooks／History 契约一并裁决。

### G4（小）错误帧报了另一条腿的协议名

`stream.py:275-288` 在 `terminal.seen=false` 时无条件发 `message="Responses stream ended before a successful terminal event"`、`code="incomplete_responses_stream"`，两条腿共用（assembler 在 `src/app/server/handler.py:481-488` 按 dialect 分流，但随后共用同一个 `stream_delivery`），`error_frame` 不按 dialect 改写（`anthropic_sse.py:140-150`）。

spec（`docs/agents/anthropic-responses-bridge/spec.md:264-265`、`:278-305`、`:380-388`）冻结的是**错误语义与 envelope**，没有冻结这句 message 与 code 的字面。**因此这是缺陷，不是既定裁决。**

## 代理这次做对了的部分

它没有伪造 `message_delta{stop_reason:"end_turn"}` + `message_stop` 把截断包装成干净结束存进客户端历史，而是发了 Anthropic SSE `error` 并把请求行标红——STR-04（`16dd68c`）落地的那一半正在起作用。客户端看到的是一次明确失败。

## 候选工作项（未裁决，供排期）

1. **G2 接线**——收益最大且函数已就绪。`findings.md` 记的阻塞原因是 `pipeline_app.py`／`handler.py` 正被并行会话大改，需先确认该阻塞是否已解除。
2. **G1 记下上游的错误事件**——不需要改变终止语义即可先取得可观测性：认出 `error` / `response.failed` 并把其文字带进 `detail`。是否同时把它们**当作**终止事件（legacy 的做法）是另一个裁决。
3. **G4 文案按 dialect 取词**——一行的事，但涉及客户端可见文本。
4. **G3** 依赖 `context.reply` gate 的裁决，不宜单独动。
