# Codex CLI 按什么把 Responses SSE 事件归组成 output item

调查日期：2026-09-02
性质：纯只读取证调查，读 Codex 官方 Rust 源码 + 对用户实际安装的二进制做定向字符串验证。未发起任何网络请求，未运行 Codex 的任何实际会话。

> **落盘位置偏差，读者请注意。** 本报告本应写入主工作树的 `.dev/docs/direct-passthrough/reports/`，但产出它的会话被隔离在 worktree `260902-fix-stream-ids` 中，写主树路径被护栏拒绝（详见 §9）。因此它暂时落在该 worktree 的同名相对路径下。**`.dev/` 的正典位置是主工作树根**，请把本文件移过去，并删除 worktree 内的这份副本。

## 0. 一页摘要

**待证假设**（来自 `.dev/docs/direct-passthrough/spec.md` §6.6.1 记录的现象）：Codex 按 `item_id` 把 SSE 事件归组成 output item，所以上游 id 漂移会让它把一个 item 拆成多个，导致同一段文本重复渲染。

**裁定：证伪。** Codex 0.144.1 既不按 `item_id` 归组，也不按 `output_index` 归组——它按**到达顺序**，用一个单槽变量 `active_item` 把 `output_item.added` 与 `output_item.done` 配对，中间的 `output_text.delta` 一律挂到那个单槽上。事件自身携带的 `item_id` 在 assistant 文本这条路径上**被显式丢弃**，`output_index` 则根本没有被反序列化进 Codex 的事件结构体。

**最硬的一条证据**：`ResponsesStreamEvent` 结构体（`codex-api/src/sse/responses.rs:159-174`）逐字列出了 Codex 会从 SSE JSON 里取的全部字段，其中**没有 `output_index`**；而 `response.output_text.delta` 的处理分支（同文件 `:338-342`）只取 `delta` 一个字段，连已解析出来的 `item_id` 都不用。

**`copilot-api-js` 做过 id 稳定化：是。** 名为 `responses-fix-stream-ids`，**默认开启**，且它的 tracker 正是**按 `output_index`** 建立 canonical id 映射。但它当年的注释点名的受害客户端是 `@ai-sdk/openai`，**不是 Codex**。

**对本项目的直接后果**：spec §6.6.3 已裁定的「统一到闭合事件（`output_item.done`）的那个 id」，从 Codex 侧看是安全的（见 §7）。但要注意 §7.3 给出的一条可证伪预测——如果修法只统一 `output_text.delta` 的 `item_id` 而不动 `added`/`done`，**对 Codex 不会产生任何可观察变化**。

---

## 1. 调查范围与版本适用性

### 1.1 读的是哪份源码

| 项 | 值 |
|---|---|
| 源码副本 | `/home/xp/src/copilot-api-js/refs/codex/` |
| git HEAD | `8cf9a1b1f8ea35c724831a739fea2d725d72c582` |
| HEAD 日期 | 2026-07-09 |
| HEAD 提交标题 | `code-mode: fall back to using in process v8 if we fail to resolve external process (#31899)` |

这是 Codex 的官方 monorepo（Rust 为主，`codex-rs/`）。**它不是二进制反推，是完整的可读源码。**

`codex-cli/package.json` 里 `"version": "0.0.0-dev"`，`codex-rs/Cargo.toml` 里 `version = "0.0.0"`——版本号由 CI 注入，所以**无法从这份副本直接读出它对应哪个发行版本号**。`git describe --tags` 给出的是 `codex-zsh-v0.1.0-221-g8cf9a1b1f8`，标签与 CLI 版本无关，不可用。

### 1.2 用户实际在跑的是哪个版本

| 项 | 值 |
|---|---|
| `codex --version` | `codex-cli 0.144.1` |
| 入口 | `/home/xp/.local/volta/bin/codex`（volta-shim） |
| 实际 native 二进制 | `/home/xp/.local/volta/tools/image/packages/@openai/codex/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex` |
| 二进制属性 | ELF 64-bit, x86-64, static-pie, **stripped**, 298,520,624 字节, mtime 2026-07-10 05:38 |
| 平台包声明版本 | `"version": "0.144.1-linux-x64"` |

源码副本（07-09）与二进制（07-10 落盘、0.144.1）时间相邻，但**相邻不等于同源**。

### 1.3 把「相邻」升级成证据：定向字符串探针

从我实际引用的那几段源码里取独特的字符串字面量，在用户的 0.144.1 二进制上做存在性检查。**每一轮都配了负控制**，以证明探针本身有分辨力（否则「全部命中」与「搜索根本没工作」同形）。

正探针（源码里存在，若二进制同源则应命中）：

| 命中数 | 字符串 | 源码出处 |
|---|---|---|
| 4 | `OutputTextDelta without active item` | `core/src/session/turn.rs:2336` |
| 1 | `failed to parse ResponseItem from output_item.added` | `codex-api/src/sse/responses.rs:456` |
| 1 | `failed to parse ResponseItem from output_item.done` | `codex-api/src/sse/responses.rs:335` |
| 15 | `stream closed before response.completed` | `codex-api/src/sse/responses.rs:517` |
| 1 | `unhandled responses event` | `codex-api/src/sse/responses.rs:467` |
| 4 | `ConsolidateAgentMessage` | `tui/src/chatwidget/streaming.rs:44` |
| 1 | `StopCommitAnimation` | `tui/src/chatwidget/streaming.rs:54` |
| 1 | `StartCommitAnimation` | `tui/src/chatwidget/streaming.rs:140` |

负控制（应当全部落空）：

| 命中数 | 字符串 |
|---|---|
| 0 | `OutputTextDelta without a banana item` |
| 0 | `zzz_this_string_should_not_exist_zzz` |

**8/8 正探针命中，2/2 负控制落空。** 这覆盖了本报告承重的全部三层：SSE 解析层（`sse/responses.rs`）、turn 状态机层（`session/turn.rs`）、TUI 渲染层（`chatwidget/streaming.rs`）。

**这条证据支持什么**：我引用的这几段代码，其字符串字面量逐字存在于用户实际运行的 0.144.1 二进制中。**这条证据不支持什么**：它不能证明这几段代码的**逻辑**在 0.144.1 里与源码副本完全一致——字符串在，不等于它周围的分支没被改过。它把「同源」的置信度从「时间相邻」提到「同一批字面量」，**够强到可以据此行动，但不等于逐行比对**。

### 1.4 一个如实记录的异常观察

同一轮探针里，SSE 事件类型字面量的命中情况不整齐：

| 命中数 | 字符串 |
|---|---|
| 0 | `response.output_item.added` |
| 0 | `response.output_text.delta` |
| 0 | `response.content_part.added` |
| 1 | `output_item.added` |
| 3 | `output_item.done` |
| 1 | `reasoning_summary_text.delta` |
| 21 | `response.completed` |
| 1 | `response.created` |
| 0 | `output_text.delta` |

带 `response.` 前缀的长串多数落空，去掉前缀后部分命中。**我不为这个现象提供确定解释。** 一个合理但未经验证的猜测是 Rust 对 `match &str` 会做长度分桶与逐段比较的优化，使字面量在 `.rodata` 里不以连续形式存在；但我没有验证它，所以它只是猜测，不进结论。

**它不影响结论**：承重的探针是 panic/trace 消息与事件枚举名，那些是真正的字符串常量，全部命中。

---

## 2. 主结论：Codex 到底按什么归组

### 2.1 `output_index`：Codex 根本不读它

**判据一（结构体层面）**。Codex 把每一条 SSE `data:` 反序列化成 `ResponsesStreamEvent`。这个结构体逐字列出了它会取的全部字段（`codex-api/src/sse/responses.rs:159-174`）：

```rust
#[derive(Deserialize, Debug)]
pub struct ResponsesStreamEvent {
    #[serde(rename = "type")]
    pub(crate) kind: String,
    pub(crate) headers: Option<Value>,
    metadata: Option<Value>,
    response: Option<Value>,
    item: Option<Value>,
    item_id: Option<String>,
    call_id: Option<String>,
    delta: Option<String>,
    text: Option<String>,
    summary_index: Option<i64>,
    content_index: Option<i64>,
    safety_buffering: Option<Value>,
}
```

**没有 `output_index`。** serde 默认忽略未知字段（此处未加 `deny_unknown_fields`），所以 `output_index` 在进入 Codex 的第一步就被丢掉了。

**判据二（全库层面）**。在 `codex-rs/` 全树搜 `output_index`（不带任何排除、不限类型、提升隐藏与忽略文件），只有 2 个文件命中，且都是**测试里的局部变量名**，与 SSE 字段无关：

- `core/tests/suite/client.rs:968` — `let legacy_output_index = input...`
- `core/tests/suite/tool_parallelism.rs:279` — `for (output_index, _) in &function_call_outputs`

同一轮的正控制：`item_id` 命中 132 个文件。**搜索有分辨力，`output_index` 的缺席是真的。**

### 2.2 `item_id`：读，但只在三类事件上，且都不是 assistant 文本

`process_responses_event`（`codex-api/src/sse/responses.rs:326-472`）是全部事件的分发点。会用到 `item_id` 的只有两处：

| 事件 | 怎么用 `item_id` | 行号 |
|---|---|---|
| `response.custom_tool_call_input.delta` | 作为 `ToolCallInputDelta.item_id` 传下去（缺失时回退到 `call_id`） | `:343-353` |
| `response.reasoning_summary_text.done` | 作为 `ReasoningSummaryDone.item_id` 传下去 | `:362-372` |

而 **`response.output_text.delta` 完全不碰 `item_id`**（`:338-342`）：

```rust
"response.output_text.delta" => {
    if let Some(delta) = event.delta {
        return Ok(Some(ResponseEvent::OutputTextDelta(delta)));
    }
}
```

产出的 `ResponseEvent::OutputTextDelta(String)`（`codex-api/src/common.rs:97`）是一个**只裹着字符串的 tuple variant，不带任何标识**。

> **这一条单独就足以回答提问的后半段**：五条 `output_text.delta` 的 `item_id` 五个都不一样，对 Codex 而言**不可观察**——那个字段被解析出来之后原地丢弃了。

### 2.3 那些根本没有分支的事件

`process_responses_event` 的 match 有一个兜底分支（`:466-468`）：

```rust
_ => {
    trace!("unhandled responses event: {}", event.kind);
}
```

落进这里、**被完全忽略**的事件包括：

- `response.content_part.added`
- `response.content_part.done`
- `response.output_text.done`
- `response.in_progress`

对前两者的补充判据：在 `codex-rs/` 全树搜 `content_part`，只命中 `tui/src/history_cell/messages.rs` 与 `rollout-trace/.../normalize.rs` 里名为 `content_parts` 的**局部变量**，与 SSE 事件名无关。**Codex 从不处理 `response.content_part.*`。**

对 `response.output_text.done` 的补充判据：全树只在 realtime websocket 那条完全独立的协议路径上有处理（`codex-api/src/endpoint/realtime_websocket/protocol_v2.rs:42`），**在 Responses SSE 路径上没有**。

> 顺带更正一份既有记录的机制归因。`/home/xp/src/copilot-api-js/exp/responses-buffered-merge-codex-oracle/FINDINGS.md:73-75` 写道 Codex「reads the finalized text from the terminal `output_text.done` / `response.completed.output`」。**该实验的结论（drop-delta 对 Codex 透明）是对的，但这句机制归因是错的**：`output_text.done` 是 unhandled 的；而 `response.completed` 只被反序列化成 `ResponseCompleted { id, usage, end_turn }`（`sse/responses.rs:112-120`），**结构体里没有 `output` 字段**，所以 `response.completed.output` 也从未被读取。真正携带终态全文的是 `response.output_item.done` 的 `item`。

### 2.4 真正的归组机制：单槽 `active_item` ＋ 到达顺序

归组发生在 turn 状态机（`core/src/session/turn.rs`），载体是一个**单槽局部变量** `active_item: Option<TurnItem>`——不是 map，没有键。

**`response.output_item.added`**（`turn.rs:2144-2223`）：解析出 `TurnItem` 后，末尾直接覆盖单槽（`:2220-2221`）：

```rust
active_item = Some(turn_item);
active_item_is_streaming_to_client = stream_item_to_client;
```

**`response.output_text.delta`**（`turn.rs:2307-2338`）：item id **从单槽上取**，而不是从事件上取（`:2314`）：

```rust
if let Some(active) = active_item.as_ref() {
    if !active_item_is_streaming_to_client {
        continue;
    }
    let item_id = active.id();          // ← 来自 output_item.added，不是来自本条 delta
    if matches!(active, TurnItem::AgentMessage(_)) {
        let parsed = assistant_message_stream_parsers.parse_delta(&item_id, &delta);
        emit_streamed_assistant_text_delta(&sess, &turn_context, plan_mode_state.as_mut(), &item_id, parsed).await;
    }
    ...
} else {
    error_or_panic("OutputTextDelta without active item".to_string());
}
```

**`response.output_item.done`**（`turn.rs:2047-2062`）：从单槽**取走**，同样不做 id 比对（`:2056`）：

```rust
let previously_active_item = active_item.take();
```

**这里确实有一个按 id 索引的 map**，但它不构成反例：`AssistantMessageStreamParsers` 内部是 `parsers_by_item: HashMap<String, AssistantTextStreamParser>`（`turn.rs:1394-1397`）。**它的 key 全部来自 `active_item.id()`**——`seed_item_text`、`parse_delta`、`finish_item` 三个入口在本文件里的每一个调用点，传的都是 `active_item` / `previously_streamed_item` 的 id，**从来不是 SSE 事件自带的 `item_id`**。所以只要 `output_item.added` 出现过一次，该 item 全部 delta 与最终 flush 共用同一个 key，与上游 id 漂不漂移无关。

**结论**：归组键既不是 `item_id` 也不是 `output_index`，而是**「当前活跃的那一个」**——一个由 `added` 置位、由 `done` 取走的单槽，靠事件到达顺序维持配对。

### 2.5 Codex 自己的 id 修复机制，对本场景不生效

`turn.rs:1918-1931` 有一个看起来相关的函数：

```rust
fn assign_missing_streamed_response_item_id(item: &mut ResponseItem, active_item: Option<&TurnItem>) {
    if item.id().is_some() {
        return;                                  // ← 我们的场景在这里就返回了
    }
    let active_item_id = active_item.map(TurnItem::id).filter(|item_id| !item_id.is_empty());
    item.set_id(active_item_id);
    Session::assign_missing_response_item_id(item);
}
```

它只在 **id 缺失**时才从 `active_item` 借用，或用 `{prefix}_{Uuid::now_v7()}` 自铸（`core/src/session/mod.rs:2797-2819`）。**Copilot 的 id 是「漂移」而非「缺失」，所以第一行直接 return，这套机制完全不介入。** 它还受 `turn_context.item_ids_enabled()` 门控（`core/src/session/turn_context.rs:154-157`）。

---

## 3. 逐事件对照：id 漂移各自的实际后果

按 spec §6.6.1 实测的漂移面，逐条对 Codex 0.144.1 求值：

| 漂移的字段 | Codex 是否读取 | 实际后果 |
|---|---|---|
| `response.created` / `in_progress` / `completed` 三处 `response.id` 互不相同 | `created` 只判 `response` 存在即产出 `Created{}`（`:381-385`）；`completed` 取 `id` 存入 `ResponseEvent::Completed.response_id`（`:433-449`）——但 turn 层用 `..` 把它**丢弃**了（`turn.rs:2279-2283`） | **无后果**（就 turn 主路径而言） |
| `output_item.added` 与 `.done` 的 `item.id` 不同 | 都读（各自解析成 `ResponseItem`） | added 的 id 成为 core 内部全部 delta 的 key；done 的 id 进入 `ItemCompleted` 载荷与会话历史。**配对不受影响**（单槽顺序配对） |
| 5 条 `output_text.delta` 的 `item_id` 各不相同 | **解析后丢弃**（`:338-342`） | **无后果，完全不可观察** |
| `response.completed` 里 `output[0].id` 又是一个值 | **整个 `output` 数组不被读取**（`ResponseCompleted` 无该字段） | **无后果** |
| `content_part.added` / `content_part.done` / `output_text.done` 上的 id | 这三类事件整体 unhandled | **无后果** |

**没有一条通向「同一段文本被渲染多次」。**

---

## 4. TUI 渲染路径：去重靠的是什么

这一节回答「即便 core 层配对正确，TUI 会不会因为 id 不同而把 completed 当成新 cell」。答案是不会，且原因很具体。

**第一步，delta 进 TUI 时 id 就没了**（`tui/src/chatwidget/protocol.rs:77`）：

```rust
self.on_agent_message_delta(notification.delta);
```

`AgentMessageContentDelta` 通知本身带 `item_id`，但**只有 `delta` 被传进去**。`on_agent_message_delta(&mut self, delta: String)`（`tui/src/chatwidget/streaming.rs:111-113`）的签名里没有 id。

**第二步，`ItemStarted` 对 assistant 消息什么也不做**（`protocol.rs:282-326`）。`handle_item_started_notification` 的 match 逐个列出 `CommandExecution`、`FileChange`、`McpToolCall`、`WebSearch`、`ImageGeneration`、`CollabAgentToolCall`、`SubAgentActivity`、`EnteredReviewMode`，**`AgentMessage` 落进末尾的 `_ => {}`**。所以 added 的 id 从不参与 TUI 建 cell。

**第三步，也是决定性的一步——去重判据是一个 `Option` 是否为空，不是 id 比对**（`tui/src/chatwidget/streaming.rs:97-109`）：

```rust
pub(super) fn finalize_completed_assistant_message(&mut self, message: Option<&str>) {
    // If we have a stream_controller, the finalized message payload is redundant because the
    // visible content has already been accumulated through deltas.
    if self.stream_controller.is_none()
        && let Some(message) = message
        && !message.is_empty()
    {
        self.handle_streaming_delta(message.to_string());
    }
    self.flush_answer_stream_with_separator();
    self.handle_stream_finished();
    self.request_redraw();
}
```

代码自带的注释把机制说明白了：**只要有活跃的 `stream_controller`（即 delta 流过），终态载荷就被判定为冗余而丢弃。**

**第四步，`item.id` 在整个 completed 处理里一次都没被用过**。`on_agent_message_item_completed(item: AgentMessageItem, from_replay: bool)`（`streaming.rs:268-309`）通读全文，只用了 `item.content`（拼文本）与 `item.phase`（决定状态行恢复），**`item.id` 未出现**。

**所以**：`ItemStarted(id=A)` ＋ N 条无 id 的 delta ＋ `ItemCompleted(id=B)`，A≠B 时 TUI 的行为与 A==B **逐字节相同**。

---

## 5. 假设裁定

> 假设：Codex 按 `item_id` 归组，id 漂移使它把一个 item 拆成多个，于是同一段文本被渲染多次。

**裁定：证伪。** 强度：**足以据此行动**——它不是「找不到证据」，而是找到了三层相互独立的反证（事件结构体里没有该字段用于文本、turn 层用单槽而非 id 配对、TUI 用 `Option` 空判而非 id 比对），且每一层都在用户实际运行的二进制上通过了字面量探针。

**必须同时说明这条裁定不覆盖什么。** 「Codex 不按 id 归组」**不等于**「代理这一侧没问题」，也不等于用户看到的重复是幻觉。spec §6.6.1 记录的相关性——同一客户端、同一 provider、同一模型，接线前正常、接线后重复——是一条真实的观测，本报告没有推翻它，只推翻了对它的**机制归因**。

spec §6.6.1 自己写了一句话，现在看是写对了的：

> 这条单变量论证不依赖于知道 Codex 内部怎么解析：那个客户端在 id 稳定时能用、在 id 漂移时重复，恢复稳定即恢复它工作过的条件。

这句话在本报告之后**依然成立**（它只主张相关性与可回退性，不主张机制）。但任何把它读成「因为 Codex 按 item_id 归组」的转述，现在都是**已被证伪的**，不得写进 spec 或代码注释。

**我没能给出重复输出的替代机制。** 这是本次调查的实际边界，不做填补。我读遍了 assistant 文本从 SSE 字节到 TUI 屏幕的完整链路，没有找到任何一处 id 漂移能致其重复。可能性因此落在我**未覆盖**的面上（见 §8），其中我认为最值得先查的两条：

1. **同一条 `ItemCompleted(AgentMessage)` 被投递了两次。** 由 §4 第三步可知，`flush_answer_stream_with_separator` 会 `take()` 掉 `stream_controller`；若 `finalize_completed_assistant_message` 在同一轮里被调用第二次，此时 `stream_controller.is_none()` 为真，**终态全文会被当作正常内容再渲染一遍**。这是我在整条链路上找到的**唯一一个真实存在的文本重复机制**，但它的触发条件是「终态事件来了两遍」，**与 id 无关**。本仓已有一条同形状的记录可以对上：`.dev/docs/direct-passthrough/reports/260831-review-spec-round9.md:300` 记载「直连 Responses 腿收到上游终局失败事件时，`block` 下会把该事件**发两遍**」，并指出覆盖它的测试用成员断言（`in`）因而对「发一遍 vs 发两遍」没有分辨力。**建议优先验证代理侧是否重复投递了 `output_item.done` 或终局事件**，判据用计数而非成员判定。
2. **代理侧是否重试了整个上游请求**，使同一段生成被产出两次。

这两条都是**推断出的调查方向，不是结论**，我没有为它们收集证据。

---

## 6. `copilot-api-js` 的 id 稳定化：做过，且默认开启

### 6.1 它在哪、叫什么、默认值

| 项 | 值 |
|---|---|
| 变换名 | `responses-fix-stream-ids` |
| 注册处 | `src/lib/codec/openai-responses/response-rewrites.ts:60-69` |
| 核心实现 | `src/lib/openai/stream-id-sync.ts`（143 行） |
| 配置键 | `openai_responses.fix_stream_ids` |
| 内部状态字段 | `state.fixResponsesStreamIds` |
| **默认值** | **`true`（默认开启）** — `packages/foundation/src/state-defaults.ts:299` |

`packages/foundation/src/state.ts:884-890` 的字段注释：

> Fix inconsistent item IDs between output_item.added and output_item.done events from GitHub Copilot's Responses API. Without this fix, @ai-sdk/openai breaks because it expects consistent IDs across the stream lifecycle. Enabled by default; disable with config `openai_responses.fix_stream_ids: false`.

作用域由 `appliesTo` 限定（`response-rewrites.ts:63`）：仅 `clientFormat === "openai-responses"` **且** `targetEndpoint === ENDPOINT.RESPONSES` **且** 开关为真。同文件 `:56-58` 解释了为什么只在直连腿上跑：fallback 腿（`/chat/completions`）自铸 id，**构造上就是一致的**，没有可修的东西。

### 6.2 它为什么这么做——受害者是 `@ai-sdk/openai`，不是 Codex

`src/lib/openai/stream-id-sync.ts:1-18` 的模块头注释：

> GitHub Copilot's Responses API returns different IDs for the same output item in `response.output_item.added` vs `response.output_item.done` events. This breaks clients like @ai-sdk/openai that expect consistent IDs across the stream lifecycle (**errors: "activeReasoningPart.summaryParts" undefined, "text part not found"**).

`src/lib/codec/openai-responses/response-rewrites.ts:5-7` 同样点名 `@ai-sdk/openai`。

**两处注释都没有提到 Codex。** 记下的具体故障是 `@ai-sdk/openai` 抛的两条异常，形态是**报错**，而不是「重复渲染」。**前身项目撞的墙与本次用户报告的症状不是同一个症状。**

### 6.3 它按什么建映射——**按 `output_index`**

这是本节对本项目最有价值的一点。tracker 的类型定义（`stream-id-sync.ts:22-29`）：

```ts
export interface StreamIdTracker {
  /** output_index → canonical item ID from the "added" event */
  readonly outputItems: Map<number, string>
}
```

三条规则：

| 事件 | 行为 | 行号 |
|---|---|---|
| `response.output_item.added` | 以本事件的 `item.id` 为 **canonical**，存进 `tracker[output_index]`；若 `item.id` 缺失则自铸 `oi_{output_index}_{16位随机}` 后再存 | `:62-79` |
| `response.output_item.done` | 按 `output_index` 查 canonical，**覆盖** `item.id` | `:86-97` |
| `function_call_arguments.delta` / `.done` | 按 `output_index` 查 canonical，**覆盖** `item_id` | `:106-122` |

**覆盖面必须看清楚**（`stream-id-sync.ts:106`）：

```ts
const ITEM_ID_EVENT_TYPES = new Set(["response.function_call_arguments.delta", "response.function_call_arguments.done"])
```

**只有这两类。** 它**不修** `response.output_text.delta` 的 `item_id`，也不修 `content_part.*`、`output_text.done`、以及 `response.completed` 里 `output[]` 各元素的 id、envelope 事件的 `response.id`。

它还有一条明确的健壮性契约（`stream-id-sync.ts:13-17`）：任何解析失败一律原样返回输入字符串，「ID correction is an optimization for downstream clients — a single malformed frame must never abort the stream consumer that called us」。

### 6.4 与本项目 §6.6 的实质分歧

| 维度 | `copilot-api-js` `fix-stream-ids` | 本项目 spec §6.6 草案 |
|---|---|---|
| 稳定到哪个 id | **首见的**（`added` 的 id 为 canonical） | **闭合的**（`done` 的 id），§6.6.3 明确裁定 |
| `output_text.delta` 的 `item_id` | 不改 | 拟统一 |
| envelope `response.id` | 不改 | 拟统一（§6.6.4，取 `created` 的） |
| `encrypted_content` 与 id 的绑定 | **未处理** | §6.6.3 要求删除被改写 id 的非闭合事件所携带的密文 |
| 默认值 | **默认开** | 待用户裁定 |

**「稳定到首见的 id」正是 spec §6.6.3 已经识别并否决的那条路**——它会把 `done` 的密文挂到 `added` 的 id 上，逐字复现 issue #4 的错配。所以**不要把前身项目的做法当作可直接搬运的先例**：它跑在没有 `encrypted_content` 绑定校验的年代/路径上，而本项目 §6.6.3 记录的实测（`reasoning` item，added 4,888 字节 vs done 5,032 字节，两段密文各绑各的 id）证明这条路在当前上游行不通。

其它可能相关的既有开关：`normalizeResponsesCallIds`（`state-defaults.ts:291`，默认 `true`），本次未展开调查。

---

## 7. 对本项目 spec §6.6 的三条可用结论

### 7.1 §6.6.3「统一到闭合事件的 id」从 Codex 侧看是安全的

Codex 内部所有 delta 的 key 取自 `active_item.id()`，即 **`added` 的 id**；`done` 的 id 只流向 `ItemCompleted` 的载荷与会话历史。把 `added` 改写成 `done` 的 id，对 Codex 的效果是「内部 key 换了个值」，而该 key 只在一次 turn 内部使用、且全程自洽。

**这是一条支持性证据，不是 §6.6.3 的理由。** §6.6.3 的理由是密文绑定（issue #4），本报告不动摇它，只是补上「这么做不会踩到 Codex」。

### 7.2 §6.6.4 统一 `response.id`：对 Codex 无影响

turn 层用 `..` 丢弃了 `response_id`（`turn.rs:2279-2283`）。取 `created` 的那个（§6.6.4 的裁定）对 Codex 既不改善也不损害。该裁定的依据应当落在其它客户端与日志关联上，**不要以 Codex 为由**。

### 7.3 一条可证伪的预测，可用作鉴别实验

**如果修法只统一 `output_text.delta` 的 `item_id`，而不动 `output_item.added` / `.done`，Codex 的行为不会有任何可观察变化。** 依据是 §2.2：那个字段被解析后原地丢弃。

反过来，这给了一个**便宜的鉴别实验**：先只开「统一 `added`/`done` 的 id」，观察重复是否消失。

- **消失** → 说明起作用的是 `added`/`done` 这一对，而按本报告 §3，那一对在 Codex 内部**并不影响配对**——那就说明重复的成因在我未覆盖的面上（§8），或在代理侧的投递次数上（§5 第 1 条）。
- **不消失** → 直接支持 §5 的方向：去查代理是否重复投递了终态事件。

**两种结果都有信息量**，这正是它值得先做的原因。

---

## 8. 范围限制：本报告没有覆盖的面

诚实列出，避免读者把本报告当成比它更强的东西：

1. **app-server IPC 层未逐行核查。** Codex 的 TUI 通过 app-server 协议（`ServerNotification::ItemStarted` / `ItemCompleted`）接收事件。我读完了两端（core 的产出、TUI 的消费），**中间的 `app-server/src/bespoke_event_handling.rs` 等转发层没有逐行读**。我没有证据表明它按 id 做聚合或配对（它的形态是 1:1 通知转发），但这是**未验证的推断**。此项因工具受限而中止（见 §9）。
2. **只覆盖了 assistant 文本这一条路径。** reasoning（`ReasoningSummaryDelta` 用 `summary_index`、`ReasoningContentDelta` 用 `content_index`）与 tool call（`ToolCallInputDelta` 用 `item_id` ＋ `call_id`）的归组语义不同，本报告未展开。**若重复发生在 reasoning 或工具调用的展示上，本报告的结论不适用。**
3. **`codex exec`（非交互 JSONL 输出）路径只扫了一眼。** `exec/src/event_processor_with_jsonl_output.rs:464-482` 的形态是 1:1 映射，未深入。若用户的重复是在 `codex exec` 而非 TUI 中观察到的，需要单独核查。
4. **未运行 Codex 做任何实证。** 全部结论来自源码阅读 ＋ 二进制字面量探针。**没有任何一条结论来自实际观测到的 Codex 行为。**
5. **源码副本与运行二进制的同源性是概率性的**（§1.3），不是逐行比对。

---

## 9. 两处工具受限，如实记录

调查后段 Bash 工具被 worktree 隔离护栏锁死：本会话隔离在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260902-fix-stream-ids`，而我在一次调用中 `cd` 到了共享检出 `/home/xp/src/ghc-api-proxy-py`，此后 Bash 的持久 cwd 停留在共享检出，护栏在每次调用**开始时**判定，早于命令内的 `cd` 生效，因此后续所有 Bash 调用（包括只含 `cd <worktree> && pwd` 的那次）一律被拒。

**受影响的只有 §8 第 1 条**（app-server 层核查），该项已改用 `Read` 起了个头但未完成，如实标为未覆盖。**本报告的全部承重证据在锁死之前已经取得**，不受影响。

同一护栏也拒绝了向主工作树 `.dev/` 写入，因此本报告落在 worktree 内的同名相对路径下（见文首提示）。**这是落盘位置的偏差，不是内容上的保留**——需要主会话把它搬到主树 `.dev/docs/direct-passthrough/reports/` 并删除 worktree 内的副本。

---

## 附录 A：完整证据索引

Codex 源码（`/home/xp/src/copilot-api-js/refs/codex/codex-rs/`，HEAD `8cf9a1b1`）：

| 文件:行 | 内容 |
|---|---|
| `codex-api/src/sse/responses.rs:159-174` | `ResponsesStreamEvent` 字段表，无 `output_index` |
| `codex-api/src/sse/responses.rs:326-472` | `process_responses_event` 全部分发分支 |
| `codex-api/src/sse/responses.rs:330-337` | `output_item.done` → `OutputItemDone(item)` |
| `codex-api/src/sse/responses.rs:338-342` | `output_text.delta` → 只取 `delta` |
| `codex-api/src/sse/responses.rs:451-458` | `output_item.added` → `OutputItemAdded(item)` |
| `codex-api/src/sse/responses.rs:466-468` | `_ =>` unhandled 兜底 |
| `codex-api/src/sse/responses.rs:112-120` | `ResponseCompleted` 只有 `id`/`usage`/`end_turn` |
| `codex-api/src/sse/responses.rs:491-596` | `process_sse_with_treatment` 主循环 |
| `codex-api/src/common.rs:74-121` | `ResponseEvent` 枚举全貌 |
| `core/src/session/turn.rs:1394-1397` | `parsers_by_item` map（key 来自 `active_item`） |
| `core/src/session/turn.rs:1715-1724` | `flush_assistant_text_segments_for_item` |
| `core/src/session/turn.rs:1918-1931` | `assign_missing_streamed_response_item_id`（仅补缺失） |
| `core/src/session/turn.rs:2047-2062` | `OutputItemDone` → `active_item.take()` |
| `core/src/session/turn.rs:2144-2223` | `OutputItemAdded` → `active_item = Some(...)` |
| `core/src/session/turn.rs:2279-2283` | `Completed` 用 `..` 丢弃 `response_id` |
| `core/src/session/turn.rs:2307-2338` | `OutputTextDelta` → `active.id()` |
| `core/src/session/turn_context.rs:154-157` | `item_ids_enabled()` |
| `core/src/session/mod.rs:1986-2015` | `emit_turn_item_started` / `emit_turn_item_completed` |
| `core/src/session/mod.rs:2797-2819` | `assign_missing_response_item_id` 自铸规则 |
| `core/src/stream_events_utils.rs:90-104` | `raw_assistant_output_text_from_item` |
| `core/src/stream_events_utils.rs:318-420` | `handle_output_item_done` |
| `core/src/stream_events_utils.rs:370-379` | `if previously_active_item.is_none()` 才 emit started |
| `core/src/stream_events_utils.rs:422-465` | `handle_non_tool_response_item` |
| `core/src/event_mapping.rs:151-170` | `parse_turn_item` 从 item 取 id |
| `core/src/util.rs:92-98` | `error_or_panic`（debug 下 panic，release 下 error） |
| `protocol/src/items.rs:625-647` | `TurnItem::id()` |
| `tui/src/chatwidget/protocol.rs:77` | delta 进 TUI 时丢弃 `item_id` |
| `tui/src/chatwidget/protocol.rs:282-326` | `ItemStarted`：AgentMessage 落 `_ => {}` |
| `tui/src/chatwidget/protocol.rs:328-338` | `ItemCompleted` → `handle_thread_item` |
| `tui/src/chatwidget/replay.rs:67-110` | `handle_thread_item` 的 AgentMessage 分支 |
| `tui/src/chatwidget/streaming.rs:19-59` | `flush_answer_stream_with_separator`（`take()` 掉 controller） |
| `tui/src/chatwidget/streaming.rs:97-109` | **去重靠 `stream_controller.is_none()`** |
| `tui/src/chatwidget/streaming.rs:111-113` | `on_agent_message_delta(delta)` 无 id 参数 |
| `tui/src/chatwidget/streaming.rs:268-309` | `on_agent_message_item_completed`，`item.id` 未使用 |

`copilot-api-js`（`/home/xp/src/copilot-api-js/`）：

| 文件:行 | 内容 |
|---|---|
| `src/lib/openai/stream-id-sync.ts:1-18` | 模块头注释，点名 `@ai-sdk/openai` |
| `src/lib/openai/stream-id-sync.ts:22-29` | tracker 按 `output_index` |
| `src/lib/openai/stream-id-sync.ts:62-79` | `added` 设 canonical ＋ 缺失时自铸 |
| `src/lib/openai/stream-id-sync.ts:86-97` | `done` 按 `output_index` 覆盖 |
| `src/lib/openai/stream-id-sync.ts:106-122` | `ITEM_ID_EVENT_TYPES` 仅两类 |
| `src/lib/codec/openai-responses/response-rewrites.ts:53-69` | rewrite 注册与 `appliesTo` |
| `packages/foundation/src/state-defaults.ts:299` | **`fixResponsesStreamIds: true`** |
| `packages/foundation/src/state.ts:884-890` | 字段文档注释 |
| `exp/responses-buffered-merge-codex-oracle/FINDINGS.md:60-77` | 2026-07-20 drop-delta oracle 实测（结论对、机制归因错，见 §2.3） |
| 相关测试 | `tests/responses/stream-id-sync.unit.test.ts`、`tests/responses/responses-v4.http.test.ts`、`tests/responses/responses-ws.http.test.ts`、`tests/pipeline/two-axis-gating.it.test.ts`、`tests/infra/debug-dry-run-pipeline.http.test.ts` |

本项目既有记录：

| 文件:行 | 内容 |
|---|---|
| `.dev/docs/direct-passthrough/spec.md:422` | 2026-09-02 用户报告与逐字段实测对照表 |
| `.dev/docs/direct-passthrough/spec.md` §6.6.3 | 裁定统一到闭合事件的 id ＋ 密文实测 |
| `.dev/docs/direct-passthrough/reports/260831-review-spec-round9.md:300` | 终局失败事件「发两遍」＋ 成员断言无分辨力 |
