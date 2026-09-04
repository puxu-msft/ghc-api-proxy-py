# 直连腿「结果重复输出」：交付链路重复投递排查

调查日期：2026-09-02
性质：`/home/xp/src/ghc-api-proxy-py` 主工作树上的**只读**定向排查。未修改仓库内任何源码或测试，未发起任何真实上游请求。全部复现脚本写在 `/tmp/duphunt/`（清单见 §8）。
对应台账：`.dev/docs/direct-passthrough/deferred.md` **D-9**；上游前置调查：`260902-codex-item-grouping-key.md`。

> **落盘位置偏差，与前一份报告同因。** 本文本应写入主工作树的 `.dev/docs/direct-passthrough/reports/`，但产出它的会话被隔离在 worktree `260902-fix-stream-ids` 中，写主树路径被护栏拒绝（原文：`This session is isolated in the worktree ... Edit the worktree copy of this file instead of the shared-checkout path.`）。因此它落在该 worktree 的同名相对路径下。**`.dev/` 的正典位置是主工作树根**，请把本文件移过去。同目录下的 `260902-codex-item-grouping-key.md` 是上一次同样偏差留下的副本（主树已有正本），可一并删除。

## 0. 一页摘要

**(a) 交付链路本身没有找到重复投递。** 我用逐事件**计数**（不是成员断言）覆盖了成功路径、三种缓冲策略、`assembler.close()` 收口、replay／commit frontier、上游四类失败事件、CRLF 行尾、逐字节分块、保活介入——**每一个上游事件都恰好交付一次**。`1fb37cd` 评审记下的那个前科（失败事件被两条路径各发一次）在今天的 HEAD 上仍然是修好的，这一条也是用计数验的。

**(b) 但找到了唯一一个能产生该症状的形状，而且它确实是 `1fb37cd` 引入的行为变化。** 在 207 个上游事件序列变异的穷举里，**所有**能让 Codex 把同一段答案渲染两遍的变异，都是同一件事：**上游对同一个 message item 发出了第二个 `response.output_item.done`**。

| | 旧构建（翻译腿） | 现在（直连透传） |
|---|---|---|
| 第二个 `output_item.done` 的去向 | **被吞掉**，`openai_responses.py:577-588` 打一条 warning 后 `return ()` | **逐字转发**，透传引擎里没有幂等门 |
| Codex 0.144.1 的渲染次数 | 1 | **2**（同一段文字两遍） |

这是「一个事件同属两类、被两条路径各发一次」的**近亲而非同类**：不是代理把一个事件发了两遍，而是**代理不再吞掉上游发了两遍的那一个**。方向相反，症状相同。

**(c) 证据缺口，必须说清楚：我没能证明上游真的会重复发 `output_item.done`。** 三条取证路径全部走不通（§5.2）。所以本报告给出的是**机制**（强度：可据以行动，已由可执行复现钉死），**不是成因认定**（强度：仅为最强候选，未取证）。

**最强的下一步**（§5.3）：`PassthroughAssembler` 已经维护着 `_closed` 集合，「对一个已关闭的 `output_index` 再次收到 `item_done_event`」是一行就能判定的事，现在它**静默通过**。加一条 warning ＋ 计数，零行为改动、零成本，一次真实 Codex 会话就能把 (c) 的缺口填上或排除掉。

---

## 1. 方法与纪律

### 1.1 判据

**计数，不是成员断言。** `"x" in names` 对「发一遍 vs 发两遍」零鉴别力，本仓已经为此付过一次代价（`260831-review-spec-round9.md`）。本报告所有结论都建立在 `names.count(...)` 或渲染次数上。

### 1.2 A／B 对照怎么做的

同一份上游字节，跑两遍，唯一变量是 `1fb37cd` 翻的那个开关：

```python
dp.carries_upstream_natively = lambda handled: False   # 恢复翻译腿
```

`app.pipeline.delivery_policy.carries_upstream_natively` 是 `framer_for` 与 `assembler_for` 共同的分派点，把它按住就得到 `ResponsesAssembler` ＋ `ResponsesFramer`，也就是 `1fb37cd` 之前 `/responses` 直连请求走的那条腿。**路由、缓冲策略、交付循环、观测记录全部是生产代码**，没有替身。

这不等于「逐字节还原 8/29 的构建」——那之后 `stream.py` 与 `inference.py` 都还有其它改动。它还原的是**这一个分派点**，而分派点正是症状出现的时间点上翻的那一个。强度：**足以定位分歧面，不足以断言 8/29 的构建在别的方面也一样**。

### 1.3 Codex 渲染次数的判据

`/tmp/duphunt/codexmodel.py` 把 Codex `0.144.1` 里决定这两件事的部分重写了一遍：**这一轮会渲染几条 assistant 消息**，以及**流是不是以错误收场**。

已建模：单槽 `active_item`（`added` 置位、`done` 取走）；`output_text.delta` 挂单槽、其自带 `item_id` 被丢弃；**空槽时到达的 `output_item.done` 仍然会完成一个 item**（`stream_events_utils.rs:370-379`），这条正是第二次渲染的机制；有 delta 时渲染累积文本、否则渲染 item 自带文本（`tui/src/chatwidget/streaming.rs:97-109`）；`response.failed` / `response.incomplete` → `ApiError::Stream`；`response.completed` 需要 `response.id: String`，且 `usage` 存在时必须带整数 `input_tokens` / `output_tokens` / `total_tokens`；流结束而没有 Completed → `ApiError::Stream`；其余事件名一律 unhandled 被忽略（**包括 `event: error`**）。

未建模：reasoning summary／text 的 delta、工具调用的渲染、app-server IPC 那一跳、TUI 的 cell 合并、Codex 的重试预算、以及重试那一轮的文字是否与第一轮逐字相同。

模型的每一条都对着 `/home/xp/src/copilot-api-js/refs/codex/codex-rs/` 的源码写，而那份源码与用户实际二进制的同源性由 `260902-codex-item-grouping-key.md` §1.3 的定向探针支持（8/8 正探针命中、2/2 负控制落空）。

**顺带确认了一件 D-9 需要的前提**：`CodexErr::Stream(..)` 在 `protocol/src/error.rs:176-205` 的 `is_retryable()` 里判为**可重试**，而 `core/src/session/turn.rs:1139-1204` 的重试循环在重试时用 `sess.clone_history()` 重建 prompt——**已渲染的内容不会被撤回**。所以「流以错误收场」对用户而言就等于「这一轮的答案会再来一次」。

### 1.4 两处测量方法上的更正，写下来因为它们差点污染结论

**第一处。** 第一版用 `TestClient.post()` 读客户端字节。**在流中途 app 抛异常的场景下它会把已经写出去的 body 整个丢掉**——撕裂类场景一律测出 `events=0`，而实际上代理已经写了 12 个事件。改成在 app 外面套一层录 `http.response.body` 的 ASGI 中间件（仍由 TestClient 驱动协议）之后才拿到真实字节。中间还试过完全手写 ASGI scope 直接驱动 app，**会挂起**，原因未查（不影响结论，已弃用）。

**第二处，夹具自伤。** 我第一版合成流里的 `response.completed.usage` 只写了 `input_tokens` / `output_tokens`，**没有 `total_tokens`**，于是每一轮都报「Codex 解析 `ResponseCompleted` 失败」——那是我的夹具造的假阳性。对照三份真实录音（§5.2 表）后补齐。**它被发现是因为两条腿同时报同一个错；如果它只污染一边，我很可能会把它当成发现写下来。**

---

## 2. 排除了什么，用什么证据排除的

以下每一条都有**执行过的**复现，不是纯读代码。

| 假设 | 结论 | 证据 |
|---|---|---|
| `BlockBuffer` 在策略释放与终局 `finish()` 各释放一次 | **排除** | `_drain()` 释放即清空；三种策略（`block` / `until-tool-use` / `full`）× 四种流形态实测，每个上游事件恰好一次（sweep1、sweep4 D10） |
| `until-tool-use` 下一个批次既被策略释放、又在终局再释放 | **排除** | 带 `function_call` 的流（正是 `until-tool-use` 等的那个东西）在三种策略下逐名计数一致（sweep1 S2、sweep4 D3） |
| `assembler.close()` 收口与 `push` 的释放重叠 | **排除** | `_take_safe_prefix` 释放前 `del self._queue[:cut]`，`close()` 只读剩余队列；带未闭合 item 的流实测（sweep1 S4）：未闭合项被丢弃（符合 §3），其余各一次 |
| replay 把已交付的事件再发一遍 | **排除** | 上游发完整段答案后撕裂 → `decide_stream_ending` 因 `downstream_opened` 判 ABANDON，不 replay；上游在首次释放前撕裂 → replay 合法，客户端只看到第二次尝试的 12 个事件、渲染 1 次（sweep4 D9 / D11，`full` 与 `until-tool-use` 下同样只有一次） |
| 上游失败事件被两条路径各发一次（`1fb37cd` 的前科复发） | **排除** | `response.failed` / `response.incomplete` / `response.cancelled` / 裸 `error` 四种，逐名计数：**每一个上游事件恰好一次**（sweep8） |
| SSE 帧切分导致重复 | **排除** | CRLF 全流、逐字节分块两种，逐名计数一致（sweep5 F6 / F7） |
| 保活介入导致重复 | **排除** | 慢上游 ＋ `sse_ping_interval: 1`，逐名计数一致（sweep5 F8） |
| 上游重复 `output_item.added` | **排除**（不产生重复渲染） | 第二个 `added` 覆盖单槽，`done` 取走 → 仍然只渲染一次（sweep5 F5、sweep7 全部 `dup#<added>`） |

补充一条只读代码得出、**未执行验证**的排除：`app/streaming/buffered_retry.py` 与 `delayed_commit.py` 名字上像会重放字节，实际在 `src/` 里没有任何引用，不在生产链路上。

---

## 3. 找到的东西：唯一的重复形状

### 3.1 穷举

对三条参考流做单事件与连续段的穷举变异，每个变异跑两条腿，比较 Codex 的渲染次数：

| 参考流 | 变异数 | 直连腿把同一段文字渲染 >1 次的变异 |
|---|---|---|
| R1 纯回答（reasoning item ＋ message item） | 67 | 5 |
| R2 回答后接 `function_call`（Codex 最常见的轮次形态） | 92 | 11 |
| R3 只有 message item | 48 | 5 |

变异族：单事件复制 / 删除 / 与邻居交换；长度 2、3、4 的连续段复制；整个 item 组（`added`…`done`）复制。

**21 个命中变异，无一例外**，全部包含同一件事：**message item 的 `response.output_item.done` 被投递了两次**——或者是它本身被复制（`dup#`），或者是包含它的连续段被复制（`duprun#`），或者是整个 item 组被复制（`dupgroup`）。

其中 `dup#` 与 `duprun#` 各例，**翻译腿都只渲染一次**；只有 `dupgroup`（整组 `added`…`done` 重放）两条腿都渲染两次——因为那种情形下第二个 `added` 在旧腿上也会开出一份新草稿。

同一轮枚举里，两条腿其它的分歧只有两类，都**不是**重复：`drop#<message 的 added>`（直连腿凭裸 `done` 仍渲染一次，翻译腿丢弃、渲染零次——**直连腿在这里严格更好**，正是 §2.1 要拆的天花板）；`swap#<done ↔ completed>`（直连腿零次，因为 Codex 在 `completed` 处就收了；翻译腿一次）。

### 3.2 两条路径各做了什么

**直连腿（今天的行为）**，`src/app/pipeline/delivery/passthrough.py:170-179`：

```python
if isinstance(item, int):
    if event.event == self._dialect.item_done_event:
        self._open.discard(item)      # 已经不在 _open 里，空操作
        self._closed.add(item)        # 已经在 _closed 里，空操作
        self._terminal.blocks += 1    # 计数照加
        ...
    elif item not in self._closed:
        self._open.add(item)
```

第二个 `done` 三行全是空操作，事件进队列，随下一个安全前缀**原样发给客户端**。这里**没有幂等门**，而且这不是疏忽：§2.1 裁定过这条腿不得建立类型表、不得让「本代理认识的形状」成为客户端能收到的天花板。**但「同一个位置不能关闭两次」是边界事实，不是分类学事实**——它落在 `Dialect` 已经描述的那一类里（`item_index_field` ＋ `item_done_event`），与 §2.1 的禁令并不冲突。这一点是我的判断，不是既有裁决。

顺带一个副作用：`self._terminal.blocks += 1` 对重复的 `done` 照加，所以请求行上的 `blocks` 数**已经在计 `output_item.done` 的次数**——只是没有独立的 item 数可比对，单看它读不出重复。

**翻译腿（`1fb37cd` 之前的行为）**，`src/app/pipeline/delivery/formats/openai_responses.py:577-588`：

```python
if not rescuable:
    logger.warning(
        "dropping an output item that closed without ever opening: type=%r item_id=%r key=%r open_drafts=%r",
        ...
    )
    return ()
```

第二个 `done` 找不到还开着的草稿，于是被丢弃并打一条 warning。**旧腿并不是「对」，它只是恰好盖住了这件事**——那条丢弃的本意是给「关闭了一个从未打开的 item」用的，它自己的注释也说这是「已经花掉过一整个响应」的那处丢弃。它顺手把重复的 `done` 一起吞了。

**Codex 侧（为什么这会变成两遍文字）**：第二个 `done` 到达时 `active_item` 已经被第一个 `done` 取走，于是走 `stream_events_utils.rs:370-379` 的 `previously_active_item.is_none()` 分支，**补发一次 `ItemStarted` 再发 `ItemCompleted`**；TUI 的 `finalize_completed_assistant_message` 此时 `stream_controller` 已被第一次 flush 用 `take()` 拿走，`is_none()` 为真，于是**把 `done` 载荷里的全文当作普通内容再渲染一遍**（`tui/src/chatwidget/streaming.rs:97-109`）。这正是 `260902-codex-item-grouping-key.md` §5 第 1 条预告的那个机制。

> **这两处是本次会话直接读源码核实的，不是转述。** `stream_events_utils.rs` 里 `emit_turn_item_started` 在 `if previously_active_item.is_none()` 之内、`emit_turn_item_completed` 在其外无条件执行；`streaming.rs` 里 `finalize_completed_assistant_message` 的丢弃条件是 `self.stream_controller.is_none()`，而 `flush_answer_stream_with_separator` 的第一行就是 `self.stream_controller.take()`。**第二次调用必然走进渲染分支。**

---

## 4. 最小复现

上游发一条普通的 Responses 流，**只把最后那个 `response.output_item.done` 帧原样再发一遍**：

```
event: response.created            data: {"response":{"id":"resp_001", ...}}
event: response.in_progress        data: {"response":{"id":"resp_002", ...}}
event: response.output_item.added  data: {"output_index":0,"item":{"id":"rs_003","type":"reasoning", ...}}
event: response.output_item.done   data: {"output_index":0,"item":{"id":"rs_004","type":"reasoning", ...}}
event: response.output_item.added  data: {"output_index":1,"item":{"id":"msg_005","type":"message","content":[]}}
event: response.content_part.added data: {"output_index":1, ...}
event: response.output_text.delta  data: {"output_index":1,"delta":"Hello"}
event: response.output_text.delta  data: {"output_index":1,"delta":" world"}
event: response.output_text.done   data: {"output_index":1,"text":"Hello world"}
event: response.content_part.done  data: {"output_index":1, ...}
event: response.output_item.done   data: {"output_index":1,"item":{"id":"msg_011","type":"message","content":[{"type":"output_text","text":"Hello world"}]}}
event: response.output_item.done   data: {"output_index":1,"item":{"id":"msg_011","type":"message","content":[{"type":"output_text","text":"Hello world"}]}}   ← 唯一的改动
event: response.completed          data: {"response":{"id":"resp_012","usage":{"input_tokens":8,"output_tokens":5,"total_tokens":13}, ...}}
```

客户端在 `POST /responses` 上以 `{"model": "gpt-model", "input": [], "stream": true}` 发起，模型映射到 `/responses` 上游。

实测结果：

| | 客户端收到的事件数 | Codex 渲染 |
|---|---|---|
| 直连透传 | 13 | `['Hello world', 'Hello world']` |
| 翻译腿 | 11 | `['Hello world']` |

复跑：

```bash
/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/duphunt/sweep5.py     # F4 一行就是它
/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/duphunt/sweep7.py     # 207 个变异的全枚举
```

### 触发条件

1. 客户端与上游都是 `openai-responses`，`translation_required is False`（也就是本腿）；
2. 上游对**同一个 message item** 发出第二个 `response.output_item.done`；
3. 客户端按单槽模型配对——Codex `0.144.1` 满足。

条件 1 与 3 是已知成立的；**条件 2 是未取证的那一环**。

与缓冲策略无关：`block` / `until-tool-use` / `full` 三种下重复照样发生（重复的 `done` 属于同一个安全前缀，一起释放）。

---

## 5. 证据缺口

### 5.1 缺的是什么

「上游会重复发 `output_item.done`」这一条，我**没有任何一手证据**。既没有观测到，也没有观测到它不发生。§3 证明的是「**如果**上游这么发，直连腿就会产生用户报告的症状，而翻译腿不会」——这是一条条件命题，条件本身未验证。

### 5.2 试过的取证路径，以及各自为什么不行

| 路径 | 结果 |
|---|---|
| `~/.local/share/copilot-api/history-v3-archive.db`（旧 JS 服务的帧级录制） | **不可用**。`select count(*) from v3_objects where kind='frame'` = **0**；库里只剩 `sequence-item` 9693、`payload` 81、`payload-skeleton` 46。`openai-responses` 端点共 484 条操作（其中流式 472 条，分布在 2026-07-12 / 07-23 / 08-06 / 08-07 / 08-08 五天），全部取不到帧 |
| `~/.codex/sessions/` 的 rollout 记录 | **不可用**。最新的会话文件停在 2026-08-08，症状发生在 09-02 |
| `~/.local/share/ghc-api-proxy/requests/*.jsonl`（本代理自己的请求日志） | **不含 body**，只有元数据。09-02 当天 `inbound_format=openai-responses` 的记录数为 **0**；09-01 有 25 条，但从内容看（出现 `rs_deadbeefdeadbeefdeadbeef` 这样的 id）是 issue #4 调查时的手工探针，不是真实 Codex 会话 |
| 三份 cassette 里的真实录音 | **有帧，但都是单份**：`anthropic_to_responses_stream.json`（live-recording）、`responses_web_search_stream.json`（live-recording）、`history_responses_stream.json`（history 派生）三条流各自 `output_item.added` 2 次 / `output_item.done` 2 次，每个 `output_index` 一次，**没有重复**。样本量 3，只能说「不是每条流都这样」 |
| 发真实上游请求 | **本次任务禁止**，未做 |

### 5.3 建议的下一步（按我的推荐排序）

**第一优先——把缺席变成可读的，零行为改动。** `PassthroughAssembler` 已经维护着 `_closed`；「对一个已在 `_closed` 里的 `output_index` 再次收到 `item_done_event`」是一行判定，现在**静默通过**。加一条 warning（或一个计到 `Terminal` 上的计数）之后，用户跑一次真实 Codex 会话就能判定条件 2。

本仓已经吃过「absence is not readable」的亏：字段有才打印，于是「没观测到」和「不报这项」同形。这里同样——今天的日志里，一条重复 `done` 与一条正常 `done` 逐字节一样。

代价评估：一次 `set` 查询，每个 item 一次；不改任何交付行为；不需要新的验证设施。

**第二优先——如果条件 2 被证实，修法的形状。** 直连腿对「同一 `output_index` 的第二个 `item_done_event`」应当丢弃而非转发。**这要先改 Spec 再改实现**（项目规则：绝不绕过 Spec）；而且它是一条**新的对外行为**——「本代理会吞掉上游的某个事件」与 §3「上游的事件原样带过去」在字面上冲突，需要在 §4／§5 里显式立起这条例外并说明它是边界事实而非类型表。**这一条我不认为可以由评审共识直接落地**，它改的是这条腿的对外承诺，应当交用户裁定。

**第三优先——用 §7.3 已有的鉴别实验反过来用。** `260902-codex-item-grouping-key.md` §7.3 给了一个可证伪预测。既然本报告把成因指向 `output_item.done` 的**次数**而非 id，那么 §6.6 的整套 id 稳定化**预期对本症状无效**——如果用户开了它之后重复消失，说明本报告的机制归因错了，值得回来重查。

> **这条现在是活的。** 本次调查进行期间（2026-09-02 23:0x），worktree `260902-fix-stream-ids` 上落了一个提交 `b8fe245 feat: an opt-in reshape that settles upstream's drifting stream ids`，看提交标题正是 §6.6。**我没有评审也没有测试它**——我全部实测跑的是主工作树的源码，而主树的 `src/app/pipeline/delivery/` 各文件在我整个会话期间 mtime 未变（`2026-09-01 16:38`），所以本报告的结论不受它影响。但它一旦合并，上面那个双向都有信息量的实验就可以直接做。

### 5.4 一件应当同步的事

`deferred.md` D-9 目前写着「当前最强线索：给定 Codex 的单槽模型，能让它产出两遍的形状只有一个——同一个 item 的 `added`／`done` 对被投递了不止一次」。本报告把它**收窄并具体化**了：不需要 `added`，**单独一个多余的 `done` 就够**；而且投递方不是代理，是代理不再过滤的上游。是否更新 D-9 由主会话裁定。

---

## 6. 被证伪的假设，记下来省得重走

**每一条都是我实际走过并自己推翻的**，不是纸面排除。

**「`synthesises_terminal` 的腿间分歧就是成因」——证伪。** 我一度认为找到了：上游干净地在块边界结束、没发 `response.completed` 时，翻译腿（`ResponsesFramer.synthesises_terminal == True`）合成一个终局事件，直连腿（`PassthroughFramer.synthesises_terminal == False`，§8 明令禁止）改发 `error`，于是 Codex 报错重试、渲染两遍。**推翻它的是 Codex 自己的源码**：`response.incomplete` 分支同样返回 `Err(ApiError::Stream)`（`sse/responses.rs:422-431`），也就是说翻译腿合成的那个终局事件**在 Codex 眼里同样是错误**。两条腿在这个结局上都会触发重试，分歧只在错误消息的措辞。实测确认（sweep4 D4：passthrough 得 `stream closed before response.completed`，translating 得 `ApiError::Stream(response.incomplete)`，两者都是错误）。

**「Codex 解析 `response.completed` 失败」——证伪。** `ResponseCompleted.usage` 里 `input_tokens` / `output_tokens` / `total_tokens` 三项都是必需的非 Option 字段，我一度怀疑上游的 usage 形状过不去。三份真实录音全部带齐三项（12/19/31、4693/112/4805、56919/637/57556），能解析。

**「replay 会把已交付的事件再发一遍」——证伪。** 两个方向都验了：已交付内容后撕裂时 `decide_stream_ending` 因 `downstream_opened` 判 ABANDON，根本不 replay；`full` / `until-tool-use` 下 `committed_count` 为 0、replay 合法时，`_deliver` 换上全新的 assembler ＋ buffer ＋ `DeliverySession`，客户端只收到第二次尝试的事件（sweep4 D9/D11）。

**「`until-tool-use` 会让同一批次被释放两次」——证伪。** `BlockBuffer._drain()` 释放即清空 `_held`；`finish()` 第二次拿到的是空的。三策略 × 四形态实测一致。

**「SSE 读取层重复产出帧」——证伪。** `iter_frames` 在 `yield` 之前就 `del buffer[:found.end()]`；CRLF 与逐字节分块实测计数一致。

---

## 7. 本报告没有覆盖的面

诚实列出，避免被当成比它更强的东西。

1. **没有发起真实上游请求**，所以「上游会不会重复发 `done`」始终是开着的。
2. **变异穷举是单事件与连续段级别的**，不是任意多点组合。两个互相独立位置同时被扰动的形状没有覆盖。
3. **只覆盖了 assistant 文本这一条渲染路径。** reasoning summary／content 的 delta（按 `summary_index` / `content_index` 归组）与工具调用的展示语义不同，未展开。若用户看到的重复发生在 reasoning 或工具调用的展示上，本报告的结论不适用。
4. **Codex 模型是重写而非运行。** `codexmodel.py` 对着源码写，未跑过任何真实 Codex 会话；app-server IPC 那一跳与 TUI 的 cell 合并均未建模。
5. **A／B 里的「翻译腿」是按住一个分派点还原的**，不是 8/29 那个构建的逐字节还原（§1.2）。
6. **`response.cancelled` 与裸 `error` 在 Codex 侧都落进 unhandled 兜底**，于是这两种上游结局在两条腿上都表现为「流没有 Completed 就结束了」，也就都会触发客户端重试。这一点已实测（sweep8），与本次症状无关，但它是一条独立成立的观察，未展开。
7. **交付层之外没查。** 请求方向（发往上游的 body）如何影响上游的分片行为，完全没碰。

---

## 8. 附录：脚本清单与复跑

全部在 `/tmp/duphunt/`，不进仓库。用主树的解释器跑：`/home/xp/src/ghc-api-proxy-py/.venv/bin/python <脚本>`。

| 文件 | 做什么 |
|---|---|
| `harness.py` | 载入主树的 `tests/int/test_pipeline_app.py::make_client`，合成按真实录音形状写的 Responses 流，解析客户端 SSE |
| `codexmodel.py` | Codex `0.144.1` 的渲染次数 ＋ 终局判定模型，含 modelled／not modelled 清单 |
| `sweep1.py` | 三种缓冲策略 × 四种流形态的逐名计数 |
| `sweep2.py` | 直连腿 vs 翻译腿的首次并排对照 |
| `sweep3.py` | 各种结局的 A／B（含被证伪的 `synthesises_terminal` 分歧） |
| `sweep4.py` | 引入 Codex 渲染次数判据的差分扫描（D1–D11） |
| `sweep5.py` | 上游异形：两个 message item、重复 `done`、重复 `added`、CRLF、逐字节、保活（F0–F8） |
| `sweep6.py` | 单事件变异穷举 ＋ 录制 body 的 ASGI 中间件 |
| `sweep7.py` | 三条参考流 × 三个变异族的全枚举（207 个变异） |
| `sweep8.py` | 失败路径的显式逐名计数（`1fb37cd` 前科的回归确认） |
| `history_survey.py` `probe_db.py` | 历史库取证尝试，结论见 §5.2 |

复跑顺序建议：`sweep8`（前科仍已修复）→ `sweep7`（唯一重复形状的全枚举）→ `sweep5`（F4 最小复现）。

**这些脚本是临时产物。** 若要把 §4 的最小复现留成回归测试，它属于 `tests/int/test_pipeline_app.py`，判据必须是 `names.count("response.output_item.done") == 2` 加上客户端文本里 `"Hello world"` 出现的次数，**不能用成员断言**。是否落地由主会话决定；本次任务是只读排查，我没有写入仓库。
