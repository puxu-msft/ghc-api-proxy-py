# 干净 EOF 但没有合法终止事件：这个形态在历史里出现过多少次，落在哪里

调查日期：2026-08-22。调查者：subagent（只读调查）。
**未向上游发出任何真实网络请求**；未修改任何源码、测试或人写文档；未 `git add` / `git commit`；未运行 `ruff format`。
调查开始时本仓 HEAD 是 `c01191f`，**结束时是 `a59800d`**——并行会话在调查进行中提交了 4 个提交，其中一个正是本报告要评估的那条细化（见 §5.1）。**本文引用的全部源码行号一律对 `git show a59800d:` 复核过，不是工作树版本。**

探针脚本与原始输出：`.dev/docs/upstream/retry-and-continuation/evidence/clean-eof-no-terminal/`。

---

## 0. 三个数字

| # | 问题 | 数字 | 证据等级 | 权重 |
|---|---|---|---|---|
| 1 | 「上游干净 EOF 且无合法终止事件」出现过多少次 | copilot-api-js 语料 **109 次 / 133 929 条上游 SSE 流 = 0.081%**（Anthropic 腿 32、Responses 腿 77）。本项目自己的请求日志 **3 次 / 13 700 次真实流式轮次 = 0.022%** | 一手实测 | 够据此行动 |
| 2 | 其中 EOF 落在块边界 vs 块中途 | **块中途 100 条（91.7%）；块边界 4 条（3.7%，全在 Responses 腿）；一个块都没开过 5 条（4.6%）** | 一手实测 | 够据此行动，但**只覆盖 copilot-api-js 语料**——本项目自己那 3 次没有帧级留存，块完整性未知 |
| 3 | 块边界那些，上游还留了什么线索 | **几乎没有。** 唯一存活的线索是最后那条 `response.output_item.done` 上的 `item.status == "completed"`（4/4），而它与正常流上的取值**逐字相同，不具鉴别力**。usage **0/109**（usage 只搭 `response.completed` 走）、`[DONE]` 哨兵 **0/109**（**Copilot 两条腿从不发它**，这个判据恒假）、Anthropic 腿的 `message_delta` **0/32** | 一手实测 | 够据此行动 |

**一句话结论：这条细化值得留着，但它不是止血——它在 133 929 条流上只会改变 4 条的结局（0.003%），并且改变之后下游拿到的是一个没有 usage、`stop_reason` 由我们合成的收尾。** 它真正的价值在于把「上游其实说完了」和「上游被切断了」分成两件事，而不在于命中率。

> **必须先说的一件事**：这条细化**已经实现并提交了**——`78be0d4 feat: close a clean EOF at a block boundary instead of calling it truncated`（`src/app/pipeline/delivery/stream.py:424`，`if not assembler.cut_mid_block and settings.unterminated_stop_reason:`，配置项 `client_delivery.unterminated_stream_stop_reason` 默认 `incomplete`，注释自陈「Ruled 2026-08-22」）。它由并行会话在本次调查进行中写下并提交：18:36 我读到它还是工作树里的未提交改动，19:06 再看已经在 HEAD 里了。所以「值不值得做」这个问题的现实形态是「已经做了，本报告的数字说明它会不会触发、触发时拿得到什么」。详见 §5.1。

---

## 1. 方法：怎么在别人的库里认出「上游发的帧」和「干净 EOF」

### 1.1 数据源与分母

`~/.local/share/copilot-api/history-v3*.db` —— **现有服务 copilot-api-js 的抓取，不是本项目的**。八个 v3 库里只有四个还带 frame 对象（该服务 2026-08-15 之后不再存帧）：

| 库 | operation 数 | 有 `upstream-capture` 帧的 op | 时间窗 |
|---|---|---|---|
| `history-v3-260807.db` | 71 788 | 69 186 | 2026-07-17 09:37 → 08-06 20:25 |
| `history-v3-260809.db` | 39 927 | 36 316 | 2026-08-06 20:26 → 08-09 00:21 |
| `history-v3-260811.db` | 6 084 | 5 592 | 2026-08-10 06:46 → 08-11 07:47 |
| `history-v3.db` | 24 544 | 22 835 | 2026-08-11 08:11 → 08-15 17:48 |
| **合计** | **142 343** | **133 929** | **2026-07-17 → 08-15** |

operation 总数与 `reports/260821-max-tokens-block-completeness.md` 逐库相符（71788 / 39927 / 6084 / 24544），可作「打开的是同一批库」的对照。全部以 `file:<path>?immutable=1` 只读打开。

**分母是 133 929 条上游 SSE 流，不是 142 343 个 operation。** 差额 8 414 个 op 一条 `upstream-capture` 帧都没有：绝大多数是非流式请求（`summary.stream` 为空、`n_frames` 为 0），另有 407 个只带代理自造帧或早期恢复投影帧。把它们算进分母，等于把「压根没有流」冒充成「流正常结束」。

按腿拆分：**Anthropic 腿 68 774 条，Responses 腿 65 155 条**（腿由流里出现的事件名判定，不由 endpoint 判定——旧服务把两条腿都记在 `endpoint: anthropic-messages` 下）。

### 1.2 判据换了一个：不用「变换图的根」，用存储层自己的标签

`tests/int/recorded/from_history.py:107 _upstream_frames` 用「不是任何 `transform` 的输出」认上游帧。已知盲区（`reports/260821-upstream-termination-reasons.md` 的方法学警告框）：2026-07-17 19:41 之前的 366 个 operation 完全没有 transform 记录，该判据在它们身上**恒真**，代理自造帧与上游帧无法区分。

本次改用 manifest 的 `record.arena.frames[].origin.stage`——每帧都带存储层自己写下的来源标签。实测到的全部取值：

| `origin.stage` | `track` | `provenance` | 含义 |
|---|---|---|---|
| `upstream-capture` | `upstream` | `source` | **上游发来的原始帧** |
| `rewrite-out` / `render` | `client` | `derived` | 客户端侧改写／渲染出的副本（含 `rewrite-out:responses-fix-stream-ids`） |
| `client-sink` / `synthetic-root` | `client` / `internal` | `source` | **代理自己合成注入下游的帧** |
| `transform-root` | `internal` | `source` | 变换图内部根节点 |
| `recovery-projection` | — | — | 早期格式的恢复投影 |

这个判据严格更好，而且**把已知盲区从「静默污染」变成了「显式排除」**：那 366 个 op 的帧全部标 `recovery-projection`，一条 `upstream-capture` 都没有，于是整体落在分母之外，而不是被当成上游帧读进来。另有 41 个 op 只有 `client-sink` / `synthetic-root` 帧（就是那两条被前一份报告判为「根」的代理自造 `error` 帧所在的形态），同样被排除。

> **样本边界（承重）**：2026-07-17 09:37 → 19:23 之间那 366 个 operation **不可测**。本报告的任何数字都不覆盖它们。这不是「查过没问题」，是「看不见」。

### 1.3 「有没有终止事件」与「怎么结束的」：两条互不依赖的判据

**判据 A（一手，读上游字节）**：取每条流最后 12 个 `upstream-capture` 帧，解压读 SSE 事件名，看有没有 `response.completed` / `response.incomplete` / `message_stop`。

**判据 B（二手，读 copilot-api-js 自己的结论）**：读 `record.dispatches[].diagnostics` 里 `kind == "response.settled"` 那条。成功时带 `stop_reason`；失败时带 `error` 字符串，而 copilot-api-js **自己就区分了本次要找的形态**：

| `error` 字符串 | 含义 | 是不是我们要的形态 |
|---|---|---|
| `upstream stream truncated: closed without message_stop` | Anthropic 直连腿，干净排空但没收到 `message_stop` | **是** |
| `upstream stream truncated: closed without finish_reason` | translate 腿（Anthropic 入 → Responses 出，与本项目主产品路径同形），干净排空但没收到终止事件 | **是** |
| `Stream closed with error code NGHTTP2_CANCEL` | 流级 RST_STREAM，传输被重置 | 否——本项目走撕断路径，见 §3.3 |
| `client disconnected` / `Client disconnected` | 客户端走了 | 否 |
| `The operation was aborted.` | 代理自己 abort | 否 |

判据 B 的语义已在 copilot-api-js 源码里核实，不是从字符串猜的（`代码事实`）：

- `/home/xp/src/copilot-api-js/src/routes/messages/handler-v4.ts:2132-2152`，`} else if (!acc.sawMessageStop) {` 分支，注释写明「a clean EOF WITHOUT the mandatory `message_stop` terminator (GHC mid-stream cutoff). The driver sees a clean drain → `complete`, but the message never finished.」
- 同文件 `:2351-2362`，`outcome.kind === "complete"`（干净排空）且 `meta?.stopReason === undefined` 时抛 `upstream stream truncated: closed without finish_reason`。

也就是说这两条字符串的成立前提是「上游迭代器干净结束、没抛异常」——**恰好就是本项目 `if not terminal.seen:` 那一支的触发条件**。

### 1.4 正样本对照（先证明探针真的在读东西）

四个对照，每个在探针坏掉时都会变红：

**对照一 —— 终止事件距流尾多远。** 若 12 帧尾窗不够，这里会出现一批距离 1～11 的样本：

| 库 | 距离 0（终止事件即最后一帧） | 距离 1～11 | 不在尾窗内 |
|---|---|---|---|
| `history-v3-260807.db` | 68 820 | **0** | 366 |
| `history-v3-260809.db` | 35 825 | **0** | 491 |
| `history-v3-260811.db` | 5 573 | **0** | 19 |
| `history-v3.db` | 22 776 | **0** | 59 |

尾窗绰绰有余；「不在尾窗内」的那些不是被窗口截掉的，是真的没有。

**对照二 —— 两条判据交叉制表，133 929 条流上零分歧。** 「copilot-api-js 说成功」的全部找得到终止事件；「copilot-api-js 说截断」的全部找不到。两个方向都没有反例（`totals.py` 输出 `disagreements: 0`）。

**对照三 —— 开闭配平代码必须在已知正常的流上报「全闭合」。** 对 4 个库各取 12 条已知正常结束的流（两条腿各 6 条，共 48 条）跑同一段配平代码：48/48 报 `at_block_boundary=True`、`legal_terminal` 非空、usage 存在，Anthropic 腿 24/24 在 `message_stop` 前都有 `message_delta`。若配平那段根本没被执行到（例如事件名对不上），会全报 `opened=0 closed=0`——那是一个形状正确的假数字。对照跑出非零并配平，才有资格去读候选样本上的 `UNCLOSED`。

**对照四 —— 用一个完全不同的判据复现前一份报告的数字。** `reports/260821-upstream-termination-reasons.md` 用「变换图的根」数出的 `response.completed` 与 `response.incomplete`，本次用 `origin.stage` 重数：

| 库 | 前报告 `response.completed` | 本次 | 前报告 `response.incomplete` | 本次 |
|---|---|---|---|---|
| `history-v3-260807.db` | 28 904 | **28 904** | 4 | **4** |
| `history-v3-260809.db` | 30 322 | **30 322** | 16 | **16** |
| `history-v3-260811.db` | 1 222 | **1 222** | 0 | **0** |
| `history-v3.db` | 3 903 | **3 903** | 0 | **0** |

逐库逐值相等。同时本次在 133 929 条流的尾窗里数到 `response.failed` **0**、`response.cancelled` **0**、上游 `error` 帧 **0**——与前报告一致，且**这一次那两条被前报告判为「根」的代理自造 `error` 帧不再需要人工甄别**：它们的 `origin.stage` 是 `client-sink` / `synthetic-root`，判据本身就把它们排除了。**建议把这条方法学改进回填到那份报告的警告框里**（本报告不代改别人的原件）。

**另一条陷阱记录**：Copilot 的两条腿在本语料里**都不发 `[DONE]` 哨兵**（48 条对照流 0 次，133 929 条流的尾帧直方图里也 0 次）。所以「有没有 `[DONE]`」在这里是恒假判据，区分不了任何东西——问题三里它是一条死路，不是一条没走的路。

---

## 2. 问题一：这个形态出现过多少次

### 2.1 copilot-api-js 语料（2026-07-17 → 08-15）

`证据等级：一手实测。权重：够据此行动。`

全部 133 929 条上游 SSE 流的收尾分类：

| 收尾 | 条数 | 尾部有终止事件 | 占比 |
|---|---|---|---|
| 正常结束（`response.settled` 报成功） | 129 527 | 是 | 96.71% |
| 无 `response.settled` 诊断（早期格式），但帧里有终止事件 | 3 416 | 是 | 2.55% |
| **干净 EOF、无终止事件** | **109** | **否** | **0.081%** |
| 传输被重置（`NGHTTP2_CANCEL`） | 741 | 否 | 0.553% |
| 传输被重置，但上游已发完终止事件 | 13 | 是 | 0.010% |
| 客户端断开 | 71 + 38 | 否 / 是 | 0.081% |
| 其他错误（abort、502 等） | 13 + 1 | 否 | 0.010% |

逐库：

| 库 | 上游 SSE 流 | 干净 EOF 无终止 | 该库占比 |
|---|---|---|---|
| `history-v3-260807.db` | 69 186 | 38 | 0.055% |
| `history-v3-260809.db` | 36 316 | 46 | 0.127% |
| `history-v3-260811.db` | 5 592 | 2 | 0.036% |
| `history-v3.db` | 22 835 | 23 | 0.101% |
| **合计** | **133 929** | **109** | **0.081%** |

四个库同一数量级，没有一个库把总数带偏。按腿：**Anthropic 腿 32 / 68 774 = 0.047%，Responses 腿 77 / 65 155 = 0.118%。**

> 另有 **1 条**（`history-v3-260809.db`）copilot-api-js 判为 `closed without finish_reason`、但**一条 `upstream-capture` 帧都没有**——上游给了响应头然后一个 SSE 帧都没发就 EOF。它不在上面 109 条里（分母按 §1.1 只算有上游帧的流），也走不到本项目那条分支（同 §3.2 末段的理由）。记在这里是为了别人复算时对得上账：**110 = 109 + 1**。

**这个形态不是零观测，也不罕见到不值一提**：它比「上游发 `response.failed`」（0 次）常见得多，但比「传输被重置」（741 次）少一个数量级。

### 2.2 本项目自己的请求日志（2026-08-20 → 08-22 18:40）

`证据等级：一手实测（本项目自己的生产日志）。权重：存在性够据此行动；频率只是倾向，n=3。`

`~/.local/share/ghc-api-proxy/requests/requests-2026082{0,1,2}.jsonl`，14 848 行，快照于 2026-08-22 18:40（**服务在跑，还会继续追加**）。

筛出真实流式轮次：`path == "/v1/messages"`、`upstream_conn.peer` 存在（真连到了 `140.82.x.x:443`）、`first_upstream_byte_s` 非空 ——共 **13 700** 条（Anthropic 客户端腿 12 015、Responses 客户端腿 1 685；按天 08-20 2877 / 08-21 4562 / 08-22 6261）。

其中 `terminal_seen == false` 共 47 条，按 `detail` 分：

| `detail` | 条数 | 对应的代码分支 |
|---|---|---|
| `upstream stream ended without a terminal event` | **3** | `inference.py:558-559` 的 `self.drained` 支——**就是本次要查的形态** |
| `stream failed before a terminal event: <ConnectionTerminated …>` / `<StreamReset …>` | 14 | 撕断路径，`inference.py:556-557` |
| `delivery stopped before upstream finished` | 28 | 客户端走了，`inference.py:560` |
| `turn handed back to the client to continue` | 3 | `max_tokens` 续写交接 |

那 3 条（**全部在 Anthropic 上游腿**，`dialect: anthropic`、`claude-opus-5`、`alpn h2`）：

| 时间 | 已交付块数 | 时长 | 下发字节 |
|---|---|---|---|
| 2026-08-21T12:55:46Z | 2 | 33.2 s | 6 707 |
| 2026-08-21T21:13:11Z | 1 | 175.9 s | 3 251 |
| 2026-08-21T21:19:08Z | 0 | 565.2 s | 694 |

**0.022%（3 / 13 700），与 copilot-api-js 的 0.081% 同数量级。** n=3，两者的差值没有意义，不要拿来比较两套实现。

> **陷阱记录**：同一批日志里还有 6 条同样 `detail` 的行是**开发自测**，不能算进来——判据是 `upstream_conn` 为 `{"unavailable":"no-transport-identity"}`、`upstream_protocol: "H1"`、model 为 `cc-model` / `claude-model`、`duration_s` 恰好 0.0028 或 2.002 s。另有若干 `model: ""`、`duration_s: 100658` 的行同属自测。按「有没有真实 peer」筛，不按 `detail` 字符串筛。

---

## 3. 问题二：EOF 落在块边界还是块中途

### 3.1 判据与本项目实现是同一个

`证据等级：代码事实。`

本项目的 `cut_mid_block` 就是「装配器里还有没有未完成的草稿」：

- `src/app/pipeline/delivery/formats/openai_responses.py:367-369`：`return bool(self._drafts)`；草稿在 `response.output_item.added` 开（`_open`，`:410`，**对每一种 item 类型都开**），在 `response.output_item.done` 关（`_close`，`:433`）。
- `src/app/pipeline/delivery/formats/anthropic_messages.py:253-255`：同样是 `bool(self._drafts)`；草稿在 `content_block_start` 开、`content_block_stop` 关。
- 草稿的键是 **`output_index`**，不是 `item.id`（`_item_key`，`openai_responses.py:396-408`，注释写明 Copilot 会在 `added` 与 `done` 上发不同的 `item.id`，所以键必须是 index）。

本次探针用的正是同一组事件、同一个键（`completeness.py`），所以「探针报的 `UNCLOSED`」与「本项目跑到那一刻 `cut_mid_block` 会返回什么」**是同一个量**，不是近似。

### 3.2 数字

`证据等级：一手实测。权重：够据此行动，但只覆盖 copilot-api-js 语料。`

109 条干净 EOF 无终止的落点：

| 落点 | 条数 | 占比 | 腿 |
|---|---|---|---|
| **块中途**（有未闭合的 item / content_block） | **100** | **91.7%** | Anthropic 32、Responses 68 |
| **块边界**（开过块，且全部闭合） | **4** | **3.7%** | **全部 Responses** |
| **一个块都没开过**（只有 `response.created`，共 1 帧） | **5** | **4.6%** | 全部 Responses |

按腿：Anthropic 腿 **32/32 全部落在块中途**，一条边界都没有。Responses 腿 77 条里 68 中途、4 边界、5 空。

未闭合的块是什么类型（100 条中途的分布）：Responses 腿以 `function_call`（写工具参数写到一半）与 `message`（正文写到一半）为主，另有 `reasoning`（刚 `output_item.added` 就断）；Anthropic 腿以 `tool_use` 为主，另有 `text` 与 `thinking`。

**那 5 条「一个块都没开过」在本项目上根本走不到这条分支**：`stream.py:420-422` 的 `if not client_has_bytes.is_set(): return` 排在 `if not terminal.seen:`（`:423`）前面，而 `client_has_bytes` 只在 `_commit` 真交付出块时才置位（keepalive 注释帧不置位）。一条只发了 `response.created` 就断的流交付不出任何块，于是在那一行就返回了，既不发 error 帧也不发终止帧。所以**本项目能走到那条分支的样本是 104 条，其中 4 条在块边界（3.8%）**。

### 3.3 不要把传输重置算进来

`证据等级：一手实测 + 代码事实。`

741 条 `NGHTTP2_CANCEL` 里也有 **237** 条落在块边界（**全在 Responses 腿**，Anthropic 腿 88 条全部落在块中途）。**它们不属于本题**：RST_STREAM 在本项目走的是撕断路径——`httpcore2.RemoteProtocolError` → `httpx2.RemoteProtocolError` → `stream.py` 的 `except Exception` → `torn`，去 replay / `_hand_over` / 裸抛，**永远到不了 `if not terminal.seen:`**（链路与归一化细节见 `.dev/docs/tmp/260822-h2-streamreset-cancel-diagnosis.md` §1.1）。

把它们算进「块边界」会把 4/104 抬到 241/845，是一个**看起来强烈支持这条细化、实际上不成立**的数字。写在这里就是为了别人复算时不会顺手算进去。

**一处未查清、也不影响本报告结论的观察**：那 237 条**全部在 Responses 腿、Anthropic 腿一条没有**，而且全部恰好停在 `response.output_item.done` 之后。随机的连接死亡不该有这种腿间不对称，也不该这么集中在 item 边界上——这强烈暗示这批 CANCEL 中有相当一部分是**某一侧看到 item 收尾后主动发的**（谁发的、为什么发，从 `Stream closed with error code NGHTTP2_CANCEL` 这条字符串上判不出来）。若将来有人拿这 741 条做别的统计，**先解决归属问题再下结论**。

---

## 4. 问题三：块边界那 4 条，上游还留了什么线索

`证据等级：一手实测。「块边界那 4 条的形态」n=4；「usage、[DONE] 哨兵、message_delta 一律缺席」n=109（全部干净 EOF 样本）。权重：够据此行动——否证类结论强，且线索的缺席是逐条查过的，不是没找。`

四条全在 Responses 腿、全是 `gpt-5.6-sol`：

| operation | 库 | 上游帧数 | item 数 | 最后一个 item | 最后一帧 |
|---|---|---|---|---|---|
| `req_1785165288095_4608` | `history-v3-260807.db` | 399 | 1 开 1 关 | `function_call`，`status: "completed"`，394 条 arg delta | `response.output_item.done` |
| `req_1785274389752_3511` | `history-v3-260807.db` | 20 | 5 开 5 关 | `function_call`，`status: "completed"`（末 4 个 item 全 completed） | `response.output_item.done` |
| `req_1786086942777_687` | `history-v3-260809.db` | 8 036 | 13 开 13 关 | `message`，`status: "completed"`，7 519 条 text delta + `output_text.done` + `content_part.done` | `response.output_item.done` |
| `req_1786123332693_642` | `history-v3-260809.db` | 1 096 | 15 开 15 关 | `function_call`，`status: "completed"`（末 4 个 item 全 completed） | `response.output_item.done` |

逐项核对可能的线索：

| 候选线索 | 结果 | 说明 |
|---|---|---|
| `usage` | **0/4，一条都没有；把范围放大到全部 109 条干净 EOF 也是 0/109** | Responses 腿的 usage **只搭 `response.completed` 走**（48 条对照流 48/48 有，109 条干净 EOF 0/109 有）。没有终止事件就没有 usage |
| `[DONE]` 哨兵 | **0/4，全部 109 条也是 0/109** | 但这不是线索的缺席，是**判据本身不存在**：Copilot 两条腿在 133 929 条流上一次都没发过 `[DONE]` |
| `message_delta`（Anthropic 腿的「先报 stop_reason 与 usage、再 `message_stop`」拆分） | **不适用于 Responses 腿；Anthropic 腿 0/32** | Responses 腿没有这个事件。而 Anthropic 腿的 32 条干净 EOF **0/32 收到过 `message_delta`**——「上游报了 stop_reason 只差一个 `message_stop`」这个本来最有价值的形态，**在语料里一次都没出现过**。（对照：正常流上 `message_delta` 与 `message_stop` 的条数在四个库里逐库相等，39912/39912、5487/5487、4351/4351、18873/18873，没有任何一条流只有前者） |
| item 自己的 `status` | **4/4 是 `"completed"`** | **但它没有鉴别力**：正常结束的流上最后那个 item 的 status 也是 `"completed"`。它说的是「这个 item 写完了」，不是「这次回复结束了」。用它区分不了「说完了」和「刚好在 item 边界被切断」 |
| item 数量 | 无用 | 上游从不预告要发几个 item |
| 最后 item 的类型 | **弱线索，且指向两边** | 3/4 是 `function_call`（以工具调用收尾是一个完整回合的正常样子），1/4 是带完整正文的 `message`。**但 100 条块中途样本里，被截断的也大量是 `function_call`**——它常见只是因为这个语料里模型经常在写工具参数 |

**结论：在块边界的那一刻，上游没有留下任何能把「说完了」和「被截断了」区分开的线索。** 唯一存活的 `item.status == "completed"` 与正常流逐字相同。

**这对细化的实际含义**：细化触发时，合成的收尾只能给出一个我们自己选的 `stop_reason`（默认 `incomplete`），**usage 是空的**——下游拿不到 token 计数。这是这条细化的真实代价，n=4 上 4/4 成立。

---

## 5. 边界、限制与交回主会话的事

### 5.1 这条细化已经实现并提交了（要裁的不是「做不做」）

`证据等级：代码事实。行号对 git show a59800d: 复核过，不是工作树版本。`

**提交是 `78be0d4 feat: close a clean EOF at a block boundary instead of calling it truncated`**，位于 `c01191f`（本次调查开始时的 HEAD）之后第三个、当前 HEAD `a59800d` 之前一个。

- `src/app/pipeline/delivery/stream.py:421-443`：`if not terminal.seen:` 之下先问 `if not assembler.cut_mid_block and settings.unterminated_stop_reason:`（`:424`），成立就发 `framer.terminal(replace(terminal, stop_reason=settings.unterminated_stop_reason))` 并返回；否则落到原来的 `incomplete_responses_stream` error 帧。注释自陈「Ruled 2026-08-22」。
- `src/app/config/schema.py:230-239`：`unterminated_stream_stop_reason: str = "incomplete"`，注释写明**留空即整条细化关闭**、以及为什么不用 `end_turn`。
- `src/app/pipeline/delivery_policy.py` 接线；`stream.py` 的 `StreamSettings` 承载。
- `tests/unit/pipeline/delivery/test_stream_delivery.py` 里已有开关关闭时回到 error 帧的测试。

> **时间线（因为它解释了本报告为什么两处口径不同）**：18:36 我读到这些改动时它们还是工作树里的未提交状态；19:06 再查已经在 HEAD 里了。同一段调查里同一个事实翻了一次面，所以本报告任何关于「提交没提交」的表述都以 19:06 的复核为准。**并行会话还把 `assembler.py` 拆成了 `assembling.py` + `formats/`——前一份报告 `260821-upstream-termination-reasons.md` 里的 `assembler.py:NNN` 行号已全部失效。**

所以本报告的数字应当这样用：**不是「要不要做」，而是「已经做了，它会不会触发、触发时值多少」。** 我的答案是：会触发，但很稀有（133 929 条流里 4 条），而且触发时拿不到 usage。

### 5.2 每条结论的权重与它证明不了什么

| 结论 | 权重 | 它**不能**证明什么 |
|---|---|---|
| 「干净 EOF 无终止」= 109 / 133 929 = 0.081% | 够据此行动 | 不能外推到别的模型或别的时间。语料是一个人 2026-07-17 → 08-15 的编程会话，模型集中在 `gpt-5.6-sol` / `gpt-5.6-terra` / `claude-opus-5`；上游行为随时间变化未被排除 |
| 「块中途 100、块边界 4、空 5」 | 够据此行动，仅限该语料 | **不能**说本项目自己那 3 次也是这个分布——本项目不做帧级留存，那 3 次的块完整性**无从得知**。这是本报告最大的空白 |
| 「块边界时上游不留可用线索」 | 够据此行动（n=4 全无，且 usage 的缺席有机制解释：它只搭 `response.completed`） | 不能说未来上游不会加线索 |
| 「Anthropic 腿 32/32 全在块中途，且 0/32 有 `message_delta`」 | 够据此行动 | 不能说 `message_delta` 后干净 EOF 不可能发生——`stream.py` 的注释显示本项目已经为这个形态写了处理（`inference.py:535` 那段），只是语料里没出现过 |
| 「传输重置不走这条分支」 | 代码事实，确凿 | —— |
| 本项目自己 3 / 13 700 | 存在性够据此行动；频率只是倾向 | n=3，与 copilot-api-js 的比率不可比较 |
| 上面所有比率 | 是**下界**，不是精确值 | 每个 operation 只评估了最后一次 dispatch 的那条流，**最多 77 条重试流没被评估**（0.057%，量化见 §6 的注）。按基准率估计藏着不到 0.1 次本形态，但不是零 |

### 5.3 三件交回主会话的事

1. **本项目自己那 3 次的块完整性无从得知，而这正是决策要的量。** copilot-api-js 的语料只能告诉我们「在**它**那条链路上、**那**段时间、**那**批模型上，91.7% 落在块中途」。要在本项目上直接量到，需要帧级留存——**不建议为此单独建基建**，但如果将来因为别的原因加了帧留存，这是一个应该顺带回答的问题。**本次未做任何这方面的改动，也未提议做。**

2. **`reports/260821-upstream-termination-reasons.md` 的方法学警告框可以更新。** 那份说「『是根』是『上游发的』的必要条件、不是充分条件，在 2026-07-17 19:41 前完全失效」——现在有了更好的判据：`origin.stage == "upstream-capture"`。它把那 366 个 op 干净地排除（它们的帧全标 `recovery-projection`），也把那两条代理自造 `error` 帧自动挡掉（`client-sink` / `synthetic-root`）。**同样的改进适用于 `tests/int/recorded/from_history.py:107 _upstream_frames`**，那里今天仍用「取根」。**本次没有改任何一处**——改别人的报告原件违反本仓约定，改 `from_history.py` 超出只读调查范围。是否要改，交裁决。

3. **741 条 `NGHTTP2_CANCEL` 的归属没查清**（§3.3 末段）。落在块边界的 237 条**全部在 Responses 腿、全部恰好停在 `output_item.done` 之后**，Anthropic 腿一条都没有。这种腿间不对称不像随机的连接死亡。本报告的结论不依赖它，但它是一个悬着的问题，而且它牵动的是重放与撕断那一片（`deferred.md` 第 20 条附近），不是本题。

---

## 6. 复现

```bash
cd /home/xp/src/ghc-api-proxy-py
E=.dev/docs/upstream/retry-and-continuation/evidence/clean-eof-no-terminal
H=$HOME/.local/share/copilot-api
mkdir -p /tmp/ceof

# 1) manifest 扫描：每个 operation 一行，不解压任何 frame 对象（四个库合计约 6 分钟）
for db in history-v3-260807 history-v3-260809 history-v3-260811 history-v3; do
  uv run python $E/scan_manifests.py "$H/$db.db" "/tmp/ceof/$db.jsonl"
done

# 2) 尾部事件名：只解压每条流最后 12 个上游帧（最大的库约 6 分钟）
for db in history-v3-260807 history-v3-260809 history-v3-260811 history-v3; do
  uv run python $E/tail_events.py "$H/$db.db" "/tmp/ceof/$db.jsonl" "/tmp/ceof/$db.tails.jsonl"
done

# 3) 候选与正样本对照名单，然后逐条做块完整性（见 classify.py / summarize.py 的用法）
#    候选 = 尾窗里没有 response.completed / response.incomplete / message_stop 的流
uv run python $E/completeness.py "$H/history-v3-260809.db" /tmp/ceof/history-v3-260809.cand.txt

# 4) 汇总（§2 §3 §4 的全部数字）
uv run python $E/totals.py

# 5) 单条样本逐帧读（不打印任何正文）
uv run python $E/dump_op.py "$H/history-v3-260809.db" req_1786086942777_687
```

`totals.py` 里的库名与 `/tmp/ceof` 路径是写死的常量——中间产物换位置就得改那几行。

> **一处已知的漏算，量化如下。** `scan_manifests.py` 的 `tail_handles` 取的是**整个 operation 最后 12 个上游帧**，不按 dispatch 分组。四个库里有 279 个 operation 带 2～5 个 dispatch（216 个带上游帧），其中**非最后一次**的 dispatch 有 **77 次真的收到过上游 token**（判据：`dispatches[].timing` 里有 `upstreamFirstTokenAt`）。也就是说**最多 77 条上游 SSE 流没有被评估**（占 133 929 的 0.057%），而尾部落在最后一次 dispatch 上——这三个数字都是本次实测的。按 0.081% 的基准率，这 77 条里期望藏着不到 0.1 次本形态，不影响任何结论；但**这是一个漏算而不是零漏算**，要精确就得改成按 `origin.dispatch` 分组重扫。

> 探针全程以 `file:<path>?immutable=1` 只读打开，未写入任何 history 库。所有中间产物在 `/tmp/ceof/`（可随时删；`.dev` 下只留脚本）。
