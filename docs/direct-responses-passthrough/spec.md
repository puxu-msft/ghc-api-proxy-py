# 直连 Responses 路径：原生透传产品规格

日期：2026-08-30
状态：**DRAFT v6 — 待复评**。主体未开始；§3.1 的两处前置缺陷已实现并合入 `main`（`7e96adc`）。
定义域：**inbound 与 target 同为 `openai-responses`**（`route.translation_required is False`）。本规格不覆盖任何其他路由。

> **本文是活文档，不冻结。** 新裁决、实测或发现与本文冲突时当场修订，每次修订记入 §12。
>
> v2 按 [`reports/260830-review-spec.md`](reports/260830-review-spec.md) 重写（blocker 3、major 5，全部采纳）。v1 的自相矛盾与超范围归属见 §12。

## 1. 为什么需要这份规格

同格式直连请求上，客户端说 Responses，上游说 Responses，中间却走了一次往返翻译：

```
上游 Responses events → Anthropic CompletedBlock → 客户端 Responses events
```

`CompletedBlock` 的定义原文是「one fully materialised **Anthropic** content block」。这条路径上每一次往返都在损耗点上出过故障：

| | 损耗 | 故障 |
|---|---|---|
| GitHub issue #1 | `web_search_call` 无 Anthropic 块对实现，降级成散文 | 实现块对时 framer 不认，撕流 |
| GitHub issue #2 | `custom_tool_call` 连降级都没有，kind 与 payload 矛盾且 payload 为空 | `ValueError`，200 已发出后撕流 |

`ResponseOutputItem` union 共 **28** 个顶层成员；翻译层认识 6 个，**22 个**落进兜底。

**但「翻译是纯损耗」这个说法过头了，v1 写错了。** `CompletedBlock` 的消费者不止 framer：`BlockBuffer` 读整个 payload 的 `size_bytes` 做内存上限、读 `kind` 决定 `until-tool-use` 何时释放；`Terminal.record` 读 `kind`／tool name／thinking，流入完成行与 TUI。所以透传不是「拆掉中间层」，而是**把 wire 与可观测这两件事分开**——wire 走原生，可观测另立旁路事实（§10）。

## 2. 原则与其出处

**三条不同来源的依据，分开记，不要合并成一句。**

### 2.1 用户 2026-08-30 裁决（逐字锚）

原话：**「协议允许，凭什么拒绝？」**

支持的命题，仅此一条：**不得以「本代理不认识」为由，拒绝一个协议允许的直连 item。**

它**不**单独支持「不得丢弃」「不得改写任何字段」「id 必须逐字」——那些另有出处，见 §2.2 与 §2.3。v1 把整套保真政策归给这一句，是超范围归属。

### 2.2 用户既有裁决与亲笔文档

- `docs/.human-controlled/message-translation.md`：直连**尽可能原样转发**。
- `.dev/docs/error-envelope/spec.md` 保存的用户 2026-08-23 原话：**「直连路径一定用原生的，即使我们未知，也能传递」**。

这两条共同支撑「本腿走 native」这个方向。

### 2.3 本规格在上述授权范围内的推导

事件级 logical fidelity 的**精确层级**（§3）、逐事件 id 的处置（§6）、全局顺序与 commit frontier（§4）、`requires_client_action` 判据（§7）、可观测旁路（§10）——**这些是本规格的推导，不是用户裁决**，可由评审共识修正。

### 2.4 定义域边界

`anthropic-responses-bridge/spec.md` 的 response 矩阵规定「未知 output item → `REJECT`」。**该矩阵不适用于本腿**：那份规格逐字把定义域钉在 Anthropic `/v1/messages` inbound 选择 Responses upstream，其 downstream 始终是 Anthropic JSON／SSE；它排除 raw Responses passthrough 的理由正是「下游不是 Responses 客户端」，而本腿的下游就是。

`ca777df` 把该矩阵套用到了直连腿，是定义域误用，本规格落地时**必须撤销直连腿的那一半**。翻译腿的 `REJECT` 不变。

跨腿合同（error envelope、keepalive）仍然适用。

## 3. 保真层级：合法 UTF-8 SSE 的 logical event 与 data

**承诺**：在**最终被提交的那一次 attempt** 中，凡属于一个**已完成的 item group**、或属于 control 与 terminal／failure 的 SSE 事件，其 `event` 名与**经 SSE field parsing 得到的 logical `data` 字符串**逐字重放，包括本代理不认识的事件类型与字段。

**承诺不覆盖未闭合 item 的尾巴。** 一个 item 收到了 `added` 与若干 delta 却始终没有 `done`，其已缓存的事件在下列时点**丢弃**，且**不计作重排**：上游 tear、terminal 到达、failure 到达、cap 超限、deadline、客户端取消。

> 这条限定是被一个反例逼出来的：`response.created → output_item.added(A) → delta(A) → response.failed`，其中 A 永不 `done`。此时「完整交付单位」「逐事件保真」「不重排」三项**不可兼得**——交付 A 就泄漏了不完整 item，让 failure 越过 A 就是重排，丢掉 A 又违反「每一个事件」的全称，不结束则 terminal 已到却仍在等。用户亲笔的块级合同把「`_start` 到 `_end` 之间的全部内容」定义为交付单位，所以放弃的必须是全称，而不是块级完整性。
>
> **terminal 不能证明一个未知 lifecycle 已经完成。** `response.failed` 恰是反例：它只说明 response 结束了，不说明某个没收到 `done` 的 item 变完整了。因此边界不明的 suffix 一律按不完整丢弃，而不是「既然 terminal 来了就当它完了」。

**不改写 `data` 内部的任何字段**——包括 `sequence_number`、`output_index`、任何 `id`，以及任何未知字段。v1 同时承诺「data 逐字」和「重编 sequence_number／output_index」，而**那两个字段就在 data 这个 JSON 文本里**，两者不可能同时成立。v1 给的理由（「时点改变后原序号不再连续」）也是错的：只推迟不重排时，原序号仍保持次序与连续性；三份 cassette 的 sequence 均为 `0..N-1`。**只有重排才会破坏它，而本规格不重排（§4）。**

**可承诺范围**（实跑核验，见评审 finding 04）：

- 多行 `data:` → SSE 规则 join 为一个含 `\n` 的 logical string，**内容不丢**（丢的是原分行拼法）
- 空 `data:` → 保留为空字符串

**明确不承诺**：

- **不是 byte-level。** 
- 注释行、`id:`、`retry:` 与任何其他／未来 SSE field：`parse_frame` 丢弃，不重放
- 只有 `event:` 而无任何 `data:` 的帧：`parse_frame` 返回 `None`，不重放
- 非法 UTF-8：`errors='replace'` 已替换为 `�`，不可恢复
- field 前后空白与行尾（CRLF／LF）的规范化

### 3.1 两处必须先修的既有缺陷

本承诺**不能**靠现有 writer 兑现，实跑给出两个反例：

1. `_report_failure` 把含换行的 payload 写成一行 `data:` 加一行裸文本，客户端再解析只剩第一行。**必须**新增一个接受 `(event: str, data: str)` 的 raw-text SSE encoder，对 `data.split("\n")` 的每一段各写一条 `data:`；**不得**复用只接受 dict 并 `orjson.dumps` 的 `SseFrame`。
2. `read_events` 的 frame separator 固定为 `b"\n\n"`，两个合法 CRLF 帧会被合并成一个事件。**必须**修正，这是两条腿共用的前置。

## 4. 交付单位与全局顺序

**交付单位是「安全前缀」，不是「单个 item」。**

维护一个 attempt 内的**全局事件队列**与一个**单调 commit frontier**：只有从 frontier 到某位置之间、所有已打开的 item 都已 `done` 时，才释放这段连续前缀。

- item lifecycle 交错时，**允许**一个已完成的 item 被更早的未完成 item 拖住；
- **不得**为了早发而重排事件——重排正是唯一会让 `sequence_number` 倒退、让 `output_index` 与 SDK snapshot 索引失配的原因。

未知 item-specific 事件**无须被任何类型表认识**，只需停在它原本的全局位置。无法判定某事件属于哪个 item 时，保守持有到 terminal。

> 三份 cassette 的 `output_index` run 都是 `[0,1]`，**只说明已观测样本没有交错**，是趋势样本而非协议保证；本规格按可能交错设计。

## 5. Commit frontier 与 attempt replay

**「已提交」指客户端已经看到本次 attempt 的原生事件。** 它决定 replay 是否还合法，因此必须在本规格裁定，而不是由发送顺序偶然决定。

| 动作 | 是否提交本次 attempt |
|---|---|
| HTTP 200 headers | 否 |
| SSE comment keepalive | 否 |
| `response.created` / `response.in_progress` | **保持 attempt-local**，随第一批可交付 item 事件一起提交 |
| 第一批 item 事件 | 是 |
| 无 item 的 terminal／failure | 在最终决定不 replay 后，与本 attempt 的 control events 一起提交 |

**首个原生事件提交前**：retry taxonomy 判为可重试的 transport tear、无终局 EOF、可重试的 upstream failure，可在统一预算内**透明 replay**；旧 attempt 的 control events、item 队列、terminal、ids、usage 与内存计量**全部丢弃**。

**首个原生事件提交后**：**禁止**整次 attempt replay，已交付前缀保留。这与用户亲笔的重试合同一致——「尚未交付完整块可无痕重试；已交付块则不得从头重放」。

cap 超限、客户端取消、客户端 deadline 等人写文档列为不可继续的原因，**不得** replay。

### 5.1 三个必须闭合的状态转换

| 情形 | 裁定 |
|---|---|
| 上游**原生 failure 事件**（`response.failed` / `response.cancelled` / `error`）在首个原生事件提交前到达 | 是否可 replay **完全复用既有 retry taxonomy**，不为本腿另造闭集。taxonomy 判为不可重试时，该 failure 事件**逐字**交付并结束 |
| **clean EOF 且无终局** 在首个原生事件提交前 | 按既有 taxonomy 视作可重试的截断。用尽预算后仍无终局时，写 proxy error（§8），**不得**合成成功 terminal |
| **重开 attempt 没能给出新流** | 按 §5.2 的三类结果分别处置——**不要在这里把 draining 也算成「replacement 失败」**，那种情形根本没有 replacement。客户端看见 `AttemptFailed` 时才是 replacement 的失败，不是旧 attempt 的。§5 已规定 replay 时丢弃旧 attempt 的 terminal／ids／usage，所以回头重放旧 failure 会交付一份已被本代理判定作废的记录。若 replacement 的失败本身不可成帧，则写 proxy error |

### 5.2 native failure 进入 taxonomy 的 adapter

「复用既有 taxonomy」**不能代替一个可执行的输入**，而 v3 就停在了那里。既有入口是 `replay_reason(error: Exception)`，最终落到 `reason_for(error, status_code=...)`，它只认 exception 与 HTTP status；原生 failure 是一个 `StreamFailure`，两者都不是。所以本规格必须给出归一化，否则「taxonomy 判为可重试」没有可求值的东西。

**归一化结果只能是既有三个 `RetryReason` 之一或 `None`，不新增枚举值。**

| 输入 | 归一化 | 理由 |
|---|---|---|
| `response.cancelled` | `None`（不重试） | 取消是一个**决定**而非故障；再试一次的输入完全相同 |
| `code == "server_error"` | `SERVER_ERROR` | 与用户亲笔 taxonomy 里的 5xx 同类 |
| `code == "rate_limit_exceeded"` | 进**既有 rate-limit 处置**，由它给出 reason 与预算 | 与 429 同类。**不得**当作普通即时重试——限流有它自己的退避通道 |
| `code == "vector_store_timeout"` | `SERVER_ERROR` | 超时就是瞬时失败，与它同处一个 Literal 集不改变这一点 |
| 其余 `code`，含未知 | `None` | 余下 17 个是明确的非瞬时失败（`invalid_prompt`、各类 image 错误、policy）；未知 code 保守不重试 |

> **v4 写的「没有该 code 集的语义表」是错的**，我没有核就写了。`openai==3.3.1` 的 `ResponseError.code` 是一个 20 成员的 `Literal`，头两个正是 `server_error` 与 `rate_limit_exceeded`，语义一目了然。「五份 cassette 里零出现」只说明当前样本没命中过 failure event，抹不掉协议类型自带的分辨力。
>
> **v4 判断「replay 窗口本就很窄，所以代价小」也不成立。** 那只对迅速完成首个安全前缀的 `block` 成立。`full` 在上游终局前根本不 commit，未触发的 `until-tool-use` 可以持有整轮，`block` 遇到长 reasoning 或较早的未闭合 item 同样长时间不 commit。所以 `response.failed` 到达时，`full` 下的透明 replay 窗口覆盖的是**整次 attempt**——损失最大的恰恰是它。

**重开一次 attempt 的结果有三类，必须分开**，v4 把它们压成了「一个 exception」，而那不成立——draining 时**根本没有调用过 `handle`**，既没有 replacement attempt 也没有 exception：

| 结果 | 含义 | 处置 |
|---|---|---|
| `OpenedAttempt` | 新 attempt 已建立 | 继续 |
| `AttemptFailed` | replacement **确实开了**并失败，携带它自己的 error 与 origin | 该 error 走既有 `replay_reason`；最终不可重试时客户端看见 **replacement 的**失败 |
| `ReopenRefused` | 本代理**拒绝重开**（draining、本地前置拒绝），origin 是 proxy | **不得**进上游 retry taxonomy，**不得**归因给一个不存在的 replacement；按 §8 写客户端方言的 SSE error |

这是**可观察事实的分类**，不是 Python 抛不抛异常的形态；具体用什么类型承载留给 [`plan.md`](plan.md)。

**这四条都是本规格的推导**（§2.3），不是用户裁决。

## 6. 各事件与各字段的处置

### 6.1 item 专有事件

**必须**原样重放，包括但不限于 `response.custom_tool_call_input.delta` / `.done`、`response.function_call_arguments.*`、`response.output_text.*`、`response.reasoning_summary_text.*`、`response.web_search_call.*`、`response.content_part.*`、`response.output_text.annotation.added`，以及**任何未来新增的**。**不得**因「本代理不消费该事件」而丢弃。issue #2 的根因正是 `custom_tool_call_input.delta` 无人消费。

### 6.2 id：逐事件原样，包括不一致

每个事件携带的 id（item id、`response.id`、`item_id` 等）**必须**原样重放。**不得**重新 mint。

现有 framer 自铸 id 的依据是实测「上游 id 在事件之间不同」（12/12、16/16、125/125）。**那个观测只证明 id 不能作为内部 draft 关联键**——内部改用 `output_index` 与 attempt-local 序号即可（§4 的队列本就按位置组织）。它不证明发给客户端的 id 应当被改写。

**上游 id 不一致是上游 wire 的事实，在 native 合同下属于应当保留的事实，不是代理该默默修复的缺陷。** 复核：`openai==3.3.1` 的 accumulator 按 `output_index` 累积、不校验 id 相等，所以「SDK 需要稳定 id」在该版本上被排除；其他客户端未穷尽，不外推为全生态安全。

若将来要提供 `fix_stream_ids` 之类的兼容变换，**必须**另立显式、可选的 reshape 合同，**不得**叫它 native 或逐字。

### 6.3 control 与 terminal 事件

`response.created` / `response.in_progress` / `response.completed` / `response.incomplete` / `response.failed` / `response.cancelled`：**必须**原样重放上游的，**整个 `response` 对象逐字**——含 `status`、`incomplete_details`、`usage`、`tool_usage`、`metadata` 及任何本代理不认识的根级字段。**不得**由本代理合成，**不得**由 `Terminal.stop_reason` 反推（那是面向 Anthropic 的派生摘要，本腿只作可观测用途，见 §10）。

提交时点见 §5。

### 6.4 reasoning

`encrypted_content` **必须**原样交还，**不得**经本项目的 reasoning carrier 编解码。

**下一轮回传不会进入 carrier decoder**，这一条已有确证而非待定：`driver.py` 只在 `route.translation_required` 为真时调用 request translator，而 carrier decoder 只存在于该 translator 内；本规格的定义域恰为 false。**需要一条回归测试钉住这个门。**

## 7. Buffering policy

| policy | 本腿含义 |
|---|---|
| `block` | 每个安全前缀（§4）一就绪即发出。默认。 |
| `full` | 全部可提交事件在**任意最终 ending**（§7.2）时一次发出，不限于上游终局。 |
| `until-tool-use` | 见下。 |

### 7.1 `until-tool-use` 的释放判据

**判据是 `requires_client_action(item)`：该 output item 是否要求客户端提交与之对应的 tool output 或 approval，模型回合才能继续。**

**不是** Anthropic `BlockKind.TOOL_USE`（本腿没有 Anthropic kind），**也不是**「类型名以 `_call` 结尾」。

当前正例：`function_call`、`custom_tool_call`、`computer_call`、`local_shell_call`、`apply_patch_call`、`item.environment` 为 local 的 `shell_call`、`item.execution == "client"` 的 `tool_search_call`、等待客户端回答的 `mcp_approval_request`。

当前反例（上游自行执行并在同一响应内给出结果）：`web_search_call`、`file_search_call`、`code_interpreter_call`、`image_generation_call`、server-executed `tool_search_call` 与 MCP call。

**判据读 item 自身携带的执行语义**，不是 item 的 `type`，也**不需要回查原始请求**。核对 SDK 类型（2026-08-30）：`ResponseToolSearchCall` 自带 `execution: Literal["server", "client"]`，`ResponseFunctionShellToolCall` 自带 `environment`。同一个 `tool_search_call` 因此会给出相反答案——这正是「按 type 判」不成立、而本规格必须定案的原因。

> v2 曾写「判定需要原始请求的 tool declaration」，那是把上一轮评审的「同一 type 会有相反答案」误读成「要回请求里查」。响应 item 自己就带着答案；回查原始请求既无依据，还可能读到 attempt 之间被改写过的版本。

**未知类型**：**不得**默认 `false`。默认 false 会把客户端所需的行动扣押到 terminal，并再次让「代理认识的集合」成为客户端能力的上界。保守视为**需要释放**，并记一条 `predicate unknown` 的可观测事实（§10）；wire 事件本身仍逐字。

触发**只发生在**该 action item 完成且已到达安全 commit frontier 时；触发后永久转为逐前缀释放，保持今天 `until-tool-use` 的一次性状态变化语义。

### 7.2 policy × ending

`block` 之外的两种 policy 会持有**已完成**的 item group，而 proxy ending（cap、deadline、预算耗尽的 EOF、transport tear）可能先于上游 terminal 到达。v3 只裁了未闭合 suffix 的去向，没裁这些**完整**group 的去向，于是同一段文字同时要求「保留它们」「等 terminal 才发」「立刻写 error」——三者互斥。

**入口条件先于顺序，两者不能混为一谈。** 「ending」在 v4 里同时指了两件事——*一个可能被 replay 掉的 attempt 结束*，和*客户端最终看到的结束*。只有后者才触发收口。

**§7.2 只在 §5 的 replay 判定完成之后运行**：

| §5 判出 | §7.2 |
|---|---|
| 首个原生事件**尚未**提交，且 replay 有预算、该失败可重试 | **不运行。** 旧 attempt 的 control、queue、ids、usage 全部丢弃且**一个字节都不提交**——包括已完成的 group |
| 首个原生事件尚未提交，但 replay 不可用／被拒／预算耗尽 | 运行；末步的 carrier 由**下表的 final source** 决定，不由 commit 状态决定 |
| 首个原生事件**已**提交 | 运行（§5 此时已禁止 whole-attempt replay） |

**末步发什么，由 final source 决定——这是一根与 commit 状态正交的轴。** v5 把第二格一律写成 proxy error，而那一格至少装着三种来源，其中两种手里有上游自己的终局：

| final source | 末步 |
|---|---|
| 上游 `response.completed`／`response.incomplete` 到达 | **逐字提交它**（§6.3）。这一格里根本没有 replay 的必要 |
| 上游 `response.cancelled`，或不可重试 code 的 `failed`／`error` | **逐字提交它**（§5.1）。它是真实存在的上游终局 |
| 可重试的 `response.failed` 但预算耗尽 | **逐字提交它**。预算耗尽改变的是「能不能再试」，不改变「上游说了什么」 |
| 没有任何上游终局（tear、EOF、proxy refusal、cap、deadline） | 写 proxy error（§8） |

**裁定：`full` 的「response 结束」指任意**最终**ending，不限于上游 terminal。** 最终 ending 到达时，一律按同一顺序收口：

1. 丢弃未闭合 item 的 suffix（§3）
2. 按**原序**提交 control 与所有已完成的安全 group
3. 提交上游 terminal／failure（若有），否则提交 proxy error（§8）

| 最终 ending | `block` | `until-tool-use`（未触发） | `full` |
|---|---|---|---|
| **仍可 funded replay 的 tear／EOF** | **不收口**，整次 attempt 无提交丢弃 | 同左 | 同左 |
| 上游 terminal／failure | 已逐前缀提交 | 按上表收口 | 按上表收口 |
| cap／deadline／预算耗尽 EOF／不可重试 tear | 已提交部分保留，写 error | 按上表收口，末步写 error | 按上表收口，末步写 error |
| 客户端取消／下游写失败 | — | **例外：无可写通道，不收口** | **例外：无可写通道，不收口** |

**取「先提交已完成内容再写 error」而不是「全丢」**，因为那些 group 在语义上已经完整——它们是模型已经生成完的工具调用或文本，丢掉它们并不比交付它们更诚实，而「直到 response 结束才交付」这条承诺仍然成立。

**不得**沿用现有 `stream.py` 各 ending 的现状作为答案：那里的 exception／client-deadline 分支不 flush 缓冲块，clean EOF 分支却先 `session.finish()`，抄任何一条都会让输出取决于失败**以何种形式**到达，而不是取决于 policy。

## 8. 失败、截断与容量

- **上游终局失败事件**（`response.failed` / `response.cancelled` / `error`）：若最终可见则**逐字**重放。
- **代理侧错误**（cap 超限、客户端 deadline、预算耗尽而无上游终局）：按 `error-envelope/spec.md` 写 Responses `event: error`，**不得**合成成功 terminal，**不得**咨询只适用于 Anthropic 客户端的 hand-over 机制。**客户端取消与下游写失败除外**——那两种情形没有可写通道，§7.2 已把它们列为不收口的例外，写 error 是写给一个已经不在的读者。
- **`status: "incomplete"` 的 item**：**必须**照常交付，**不得**套用翻译腿的 `cut_short` / hand-over 政策——`hand_back_block()` 对非 Anthropic inbound 返回 `None`，那套政策在本腿上只会让最后一个 item 消失。
- **无终局 EOF**：本腿不得伪造成功终局（§6.3 禁止推导）。按 §5 判断：首个原生事件提交前可 replay；提交后写 `event: error` 并保留已交付前缀。
- **memory cap**：`buffer_cap_bytes` 的用户亲笔定义是「max bytes to buffer before abandoning this response」，故**限制的是本代理当前持有的字节，不是累计交付量**。本腿计入：尚未 `done` 的原始事件队列、已完成但被 policy 扣住的事件组、control events、以及同时保留的预渲染副本。释放、replay reset、failure、cancel 后按实际持有退还计量。

## 9. 非流式

**当前行为的准确陈述**：`inference.py` 先 `response.json()`（并拒绝非 object 的 JSON），`response_payload` 在 `translation_required is False` 时返回同一个 dict，随后 `JSONResponse(payload)` 再序列化。因此**未知字段按 JSON value 保留，但 raw bytes、空白、key 顺序、数字字面形式、重复键与原 `Content-Type` 都不保留**。v1 写的「今天已是 body 原样返回」按 §3 的逐字读法是错误陈述。

**本规格裁定**：合法 Responses JSON object 按 **JSON value 保真**，所有未知字段保留，允许序列化拼法变化；HTTP status 原样；response headers 见 §9.1。

若将来要 byte-exact，必须在 JSON parse 之前直接交付 `response.content` 与原 content type，并另定非 object／malformed 成功 body 的行为。

## 9.1 成功响应头（流式与非流式同一合同）

**来源已由用户裁决**（`docs/.human-controlled/client-side-block-delivery.md`「客户端响应头」）：**只在第一次 HTTP 200 尝试时转发响应头**；后续重试若 HTTP 报错只能转成 SSE error，并**已明确接受**「找不到载体转发后续 attempt 的 `Retry-After`」这个限制。replacement attempt **不得**覆盖已提交的响应头。

**哪些头转发，用户未裁决，以下是本规格的推导**（§2.3）：

- **必须剥离**：hop-by-hop 头（`Connection`、`Keep-Alive`、`Transfer-Encoding`、`TE`、`Trailer`、`Upgrade`、`Proxy-Authenticate`、`Proxy-Authorization`、以及非标准但既有直连表已列的 `Proxy-Connection`）——HTTP 规范要求，不是产品选择。
- **必须由本代理重建**：`Content-Length`（流式重新成帧后不再成立）、`Content-Encoding`（若本代理已解压）、流式的 `Content-Type`（`text/event-stream`）。
- **必须剥离 `Connection` 逐跳清单里点名的头**。`Connection: X, Y` 把 `X` 与 `Y` 也声明为逐跳，所以固定名单不够——**必须先读 `Connection` 的值，把它列出的每个字段一并剥掉**，再剥 `Connection` 自己。
- **必须剥离因 body 变换而失效的表征元数据**。判据是**语义**而非名单：**任何验证或描述上游确切字节、而本代理未重新计算的字段，一律剥离**。非流式会重新序列化 JSON（§9），流式会重新成帧，两边都不再持有上游那份字节。当前已知的例子有 **strong** `ETag`、`Content-Digest`／`Digest`、`Repr-Digest`、`Content-Range`、以及 legacy 的 `Content-MD5`——**这是例子不是穷举**，写成名单必然漏，round4 就漏了 `Content-MD5`。

  > **v5 的例子里有两个不满足这条判据，是我把名单和判据混着写留下的。** `Last-Modified` 描述的是源资源的修改时间，不验证响应字节；**weak** `ETag` 的用途恰恰是标识语义等价而非逐字节相同。两者都不是 exact-byte 断言，因此**保留**。strong `ETag` 仍须剥离或重算。若将来要连 weak validator 也一并剥，那是「块级交付可能改变表征」的另一条取舍，须单独裁定，不能当成本判据的必然推论。
- **非流式的 `Content-Type` 由本代理按实际输出重建**。§9 已说明成功 body 会被 parse 成 JSON object 再由 `JSONResponse` 重新序列化，所以输出的就是 JSON——转发上游的 `text/html` 或 vendor media type 会告诉客户端一件不再为真的事，且显式 `Content-Type` 还会压过 `JSONResponse` 本该生成的 `application/json`。只有当上游的 media type 与实际输出兼容时才可保留。
- **`Content-Encoding` 是 strip-or-recompute**：生产路径经 `httpx2` 的 content decoder 读取，body 到这里已解压，所以上游那个值不再为真——**删除它**，只有本代理自己重新编码时才设新值。**不得**复用原值。
- **其余一律转发**，包括本代理不认识的头。理由与 §2.1 同源：客户端本来就是冲着这个上游去的，`request-id`、rate-limit 系列、`retry-after` 等决定它的关联、退避与限流行为，剥掉它们是把代理的无知强加给客户端。

> **这与 cassette 录制用 allowlist 的既有教训不冲突，两者场景相反。** 那条教训（denylist 让三个识别性 header 漏进磁盘）针对的是**把上游响应写进版本库**，防的是账号标识被提交；这里是**转发给发起请求的客户端本人**，它对上游的可见性本就不低于我们。没有具体危害就不加防护，是用户既有的安全立场。

**当前实现均未转发任何上游语义头**（非流式只构造 `JSONResponse(payload, status_code=...)`，流式只构造 `_AccountedStreamingResponse(..., media_type="text/event-stream")`），所以本条是新增行为，需要各自的测试。

## 10. 可观测合同

**wire 的 source of truth 永远是上游原生事件与原生 terminal；可观测事实从旁路派生，不得反向改写 wire。**

本腿**至少**要记录：原生 output item 计数、需要客户端行动的 tool 名称／类型（§7.1）、reasoning 是否出现、权威 terminal status 与 usage、failure／截断／replay 的来源。无法分类时**必须**明确记为 unknown，**不得**伪装成 absent——`Terminal` 的 `stop_reason` 空默认值就是为这个区分而设的。

`BlockBuffer` 今天靠 Anthropic `kind` 同时承担 payload 载体、释放判据与日志分类三件事；本腿**不得**沿用该耦合。

## 11. 未闭合项（归本规格所有）

**当前为空。** v4 把此前挂在这里的产品分叉全部移入正文定案：header 合同 → §9.1；`requires_client_action` 的数据来源 → §7.1（item 自带，无需请求侧通路）；policy × ending → §7.2；native failure 的 taxonomy 输入 → §5.2。

实施状态不属于本节，见 [`plan.md`](plan.md)。

> 以下**不在**本规格定义域，已从待办移出：`function_call_output` 在响应 output 中的出现与翻译，归 `anthropic-responses-bridge/spec.md`（见 [`reports/260830-known-set-divergence.md`](reports/260830-known-set-divergence.md)）；本腿无条件携带它。

## 12. 修订记录

| 日期 | 条款 | 变化 | 触发 |
|---|---|---|---|
| 2026-08-30 | 全文 | 初稿 | GitHub issue #1／#2；用户裁决；方案评审的 blocker-01 |
| 2026-08-31 | §5.1、§5.2、§7.2、§9.1 | **v6。** (a) §7.2 第二格把「有上游终局」的情形也写成 proxy error——它至少装着三种来源，其中三种手里有上游自己的终局；新增 final source 表，明确 **carrier 由 final source 决定、与 commit 状态正交**；(b) `vector_store_timeout` 归入瞬时，v5 的「其余 18 个全非瞬时」把它一起压掉了；(c) §5.1 仍把 draining 枚举成「replacement 失败」，与 §5.2 的 `ReopenRefused` 相反——改为引用；(d) §9.1 的例子里 `Last-Modified` 与 weak `ETag` **不满足**同句的判据（它们不验证响应字节），已移出并明确保留，`ETag` 拆强弱；非流式 `Content-Type` 此前落进「其余一律转发」，会告诉客户端一个与实际输出不符的 media type | [`reports/260831-review-spec-round5.md`](reports/260831-review-spec-round5.md)：blocker 1、major 3 |
| 2026-08-30 | §5.2、§7、§7.2、§8、§9.1、文首 | **v5。** (a) §7.2 的「任何 ending 一律收口」与 §5 的透明 replay **互斥**——先提交已完成 group 就等于提交了首个原生事件，而 §5 随即禁止 whole-attempt replay；根因是「ending」一词同时指了「可能被 replay 掉的 attempt 结束」与「客户端最终看到的结束」。现在 §7.2 只在 replay 判定之后运行，表里加了 funded replay 一行，§7 主表与 §8 的两处同类表述一并同步；(b) §5.2 放宽——v4 写的「没有 code 语义表」是**未核就写的错误**，`ResponseError.code` 是 20 成员 `Literal`，`server_error` 与 `rate_limit_exceeded` 语义明确；v4「replay 窗口很窄」的判断也只对 `block` 成立，`full` 下窗口覆盖整次 attempt；(c) §5.2 把重开结果分成 `OpenedAttempt`／`AttemptFailed`／`ReopenRefused` 三类可观察事实——v4 的「它是一个 exception」不成立，draining 时根本没调用过 `handle`；(d) §9.1 补 `Proxy-Connection`，表征元数据改为**语义判据**而非名单（名单必漏，round4 漏了 `Content-MD5`），`Content-Encoding` 明确为 strip-or-recompute | [`reports/260830-review-spec-round4.md`](reports/260830-review-spec-round4.md)：blocker 1、major 2、minor 2 |
| 2026-08-30 | §5.2、§7.1、§7.2、§9、§9.1、§11、文首 | **v4。** (a) §7.2 新增 policy × ending 表——v3 只裁了未闭合 suffix，没裁 `full`／未触发 `until-tool-use` 持有的**已完成** group 遇 proxy ending 时的去向，那里三条规范互斥；裁定为「丢 suffix → 按原序提交已完成 group → 提交 terminal 或 error」，客户端取消与下游写失败显式例外；(b) §5.2 新增 native failure → taxonomy 的归一化表——v3 的「复用既有 taxonomy」不是复用而是留空，因为 `replay_reason` 只认 exception 与 HTTP status，而原生 failure 两者都不是；当前保守判为一律不重试并写明放宽条件；(c) §9.1 补 `Connection` 逐跳清单点名的字段与因 body 变换失效的 validator／digest；(d) 同步 v3 只改了解释段而漏掉的 signature、正例、§9 旧句、§11 与文首状态 | [`reports/260830-review-spec-round3.md`](reports/260830-review-spec-round3.md)：blocker 2、major 2 |
| 2026-08-30 | §3、§5.1、§7.1、§9.1、§11 | **v3。** (a) §3 的「每一个事件」是不可兑现的全称——未闭合 item 遇 terminal／failure 时，完整单位／逐事件保真／不重排三者不可兼得；改为限定在「可提交的完整 item group + control + terminal」，并写明未闭合尾巴的丢弃时点与「terminal 不证明未知 lifecycle 已完成」；(b) §5.1 补三个此前无定义的状态转换（原生 failure、无终局 EOF、replacement 自身失败）；(c) §7.1 更正判据来源——响应 item 自带 `execution`／`environment`，v2 写的「需回查原始请求」是对上一轮评审的误读；(d) §9.1 把 header 合同写进正文并覆盖流式，来源部分援引用户亲笔裁决、选择部分标为本规格推导 | [`reports/260830-review-spec-round2.md`](reports/260830-review-spec-round2.md)：blocker 3、major 1 |
| 2026-08-30 | §2、§3、§4、§5、§6、§7、§8、§9、§10、§11 | **v2 全面重写。** (a) §3 的「data 逐字」与「重编 sequence_number／output_index」自相矛盾——那两个字段就在 data 里；改为一律不改写，并新增 §4 的 commit frontier 保持全局顺序而非重排；(b) §2 拆开 provenance，用户 8/30 原话只覆盖「不得以不认识为由拒绝」，其余归本规格推导；(c) §5 新增 control event commit 时点与 attempt replay 合同（v1 完全缺失）；(d) §7.1 定案 `requires_client_action`，v1 留给实现是错的——同一 `tool_search_call` 会因请求的 `execution` 而相反；(e) §3 的可行性论证有两个实跑反例（多行 payload 重放丢行、CRLF 帧被合并），改为先修再依赖；(f) §9 更正「今天已是 body 原样」的不实陈述；(g) §10 新增可观测合同，v1 §1 的「唯一消费者是 framer」被源码反例推翻；(h) §11 关闭原第 3、4 项（cap 口径与 carrier 门已有确证），移出定义域外项 | [`reports/260830-review-spec.md`](reports/260830-review-spec.md)：blocker 3、major 5，全部采纳 |
