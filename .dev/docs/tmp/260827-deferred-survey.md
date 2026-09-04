# 八份待办台账的清点：接下来做哪一件

调查时间：2026-08-27。基线：`main` 的 `efeab76`（工作树对照 `src/` 现状）。范围：任务点名的 8 份 `deferred.md`，不含 `multi-provider-routing/deferred.md`。

**读法**：每条给「出处 / 它是什么 / 不做的后果 / 规模 / 判断」。所有标注「已核实」的条目都在 `src/` 里读过对应代码，引文与行号是本次实测，不是转述台账。

**一句话结论**：这 8 份台账里真正未闭合的大约 40 条，但**已完成却没移出的至少 15 条**，其中 `delivery-keepalive/deferred.md` 整份 220 行只有 2 条是开着的。清理这份台账比做掉任何一条待办都更省下游读者的时间。

## 关于「多 provider 路由是否顺带解决了旧条目」

逐条对照 `20e3397` 与 `efeab76` 的改动面（`src/app/config/schema.py`、`core/chain.py`、`server/composition.py`、`pipeline/count_tokens.py`、`pipeline/driver.py`、`observability/request_log.py`、`model_provider/base.py`）：**没有一条旧条目被它关闭或作废。** 三处受影响但未闭合：

- **h2-goaway 第 1 条（每连接流数上限取什么值）的射程变了**。`src/app/core/chain.py:39` 与 `server/composition.py:484` 现在都写明：每 provider 一个 httpx client，因为共用连接池会让一个账号挣来的 GOAWAY 掐掉另一个账号的在途流，而 `max_streams_per_connection` **管不了这一格**（它约束一条连接上有几个请求，不约束是谁的）。也就是说这个键要解决的问题被切小了一块，但它自己那个「取什么值」的问题原封不动。
- **retry 第 17 条（重开不重建 framer）的风险面变大但仍不可达**。已核实 `inference.py:391` 的 `_reopen` 只刷新 assembler（`fresh_assembler`），`framer` 仍是循环外用第一次 `context.id` / `resolved_model` 建的。多 provider 引入了 `fallback_model_provider` 与两趟解析，路由机器变复杂了，但同一请求的路由结果今天仍是确定的，所以这条路依然走不到。
- `efeab76` 自己新登记了一条 `multi-provider-routing` 的 D-4（`[A, local]` 却问了 B），**归主会话**，本报告不重复。

---

## 一、值得优先做的

排序依据，从高到低三档：① **有人正在读到一句假话**（日志行、代码注释、客户端可见字段上写着与事实不符的东西，且已有人被它误导过）；② **无岔路的行为缺陷**（正确做法唯一，只是没排期）；③ **需要独立切片或调研的**（价值明确但不便宜）。同一档内，改动面小的排前面。**纯裁决项一律不进本节**，见第三节。

### 1. retry §9 — 一次性交付路径的结局判定不接线

- **出处**：`upstream/retry-and-continuation/deferred.md`「已查清未修」栏 §9
- **它是什么**：`/chat/completions` 这条腿走的是「读整条流、一次写出」的路径，它的记账对象构造时没带 assembler，而结局判定整段被包在 `if self.assembler is not None:` 里。
- **不做的后果**：这条腿上的流被上游撕断、或客户端中途走掉，**完成日志行一律打 `[ OK ] 200`**。不是「日志不够细」，是日志说了一件没发生的事。已核实：`src/app/server/routes/inference.py:333` 构造 `one_shot_accounting` 时确实不传 `assembler`，`:602` 的 `if self.assembler is not None:` 仍在。
- **规模**：改一个函数。判定所需的东西（`drained` / `failure` / `_ending()`）都在同一个类里。
- **判断**：**值得做，排第一**。台账写的「归同伴切片、他们当时仍在改该文件」是 2026-08-22 的状态，那次切片早已结束，现在无人认领。这是本次清点里最便宜的一条假事实。

### 2. error-envelope E-11 + E-6 — 完成日志行与线路对同一次失败给出两种说法

- **出处**：`error-envelope/deferred.md` E-11、E-6
- **它是什么**：失败时客户端收到的 `message` 是本项目自己构造的句子，而完成日志行尾巴取的是上游 SDK 的 `__str__`（形如 `Error code: 400 - {'error': {...}}`，Python dict 的 repr，单引号不可解析）。另一格是客户端截止时间到期：线路上写 `client_deadline_exceeded`，日志行却记成「上游流没有终止事件就结束了」。
- **不做的后果**：**用户 2026-08-24 已经亲自撞上过一次**——看到的是 SDK repr，客户端拿到的是另一句话，两者都为真却读不出对方。已核实两处都还在：`inference.py:291` 的 `trace.detail = str(error)`（`error` 来自 `model_provider/ghc_client/errors.py:163` 的 `f"upstream rejected the request: {error}"`）；`pipeline/delivery/stream.py:426` 写完 `client_deadline_exceeded` 帧之后是 `return` 而不是 `raise`，所以记账把它算成 `drained`。
- **规模**：改一个模块。E-11 自己给了判据：「完成行的失败说明取自 `ErrorInfo.message`」，而不是逐格打补丁。E-6 是同一条判据的第二格。
- **判断**：**值得做，排第二**。杠杆最高的一条——一次改动关掉两条台账，而且判据已经写好了，不需要重新设计。

### 3. auto-mode D1 — 合成回复被记账成一次真实上游交换

- **出处**：`auto-mode-classifier/deferred.md` D1
- **它是什么**：分类器命中时本代理自己造一个 `httpx2.Response` 直接回答，没有任何网络参与；但下游记账无条件按真实上游响应处理它，把 `HTTP/1.1`（`httpx2.Response` 的默认值）记成上游协议，把本地 body 长度记成上游返回字节。
- **不做的后果**：完成行声称「代理从一个 HTTP/1.1 上游收到了这份回复」。这与项目既有约定直接冲突：日志与 footer 的这组字段描述的是 proxy↔upstream 那一段。已核实 `inference.py:300-303` 的三行（`bytes_in` / `upstream_protocol` / `upstream_conn`）**无任何 `synthesized` 分支**，而 `HandledRequest.synthesized` 已经存在并被交付层读了三处（`pipeline/reply.py:25`、`delivery_policy.py:29,45`）。同形的第二条路径 `_answered_failed_search`（`driver.py:196`）早于此存在。
- **规模**：改一个模块。记账点缺的就是交付层已有的那个 carve-out；两条 synthetic 路径要一起改，否则行为分叉。
- **判断**：**值得做**。它与第 2 条是同一类（可观测面上的假事实），只是伤害面窄一些——今天只有两条合成路径会触发。

### 4. retry §16 — 反方向（`/responses` 客户端 + Anthropic 上游）仍在抹平

- **出处**：`upstream/retry-and-continuation/deferred.md`「已查清未修」栏 §16
- **它是什么**：把 Anthropic 响应翻回 Responses 形状时，`stop_reason` 只认 `max_tokens`，其余一律写成 `completed`，且从不生成 `incomplete_details`。
- **不做的后果**：一次 `refusal`（模型拒答）被报成 `completed`——与 `fef7d96` 已经消灭过的形态同构；`max_tokens` 虽报 `incomplete`，但客户端读不到原因。已核实 `src/app/pipeline/translation_driver/responses.py:212`：`"status": "incomplete" if response.stop_reason == MAX_TOKENS else "completed"`，返回的 dict 里没有 `incomplete_details` 这个键。
- **规模**：改一个函数。修法与 `fef7d96` 同构，无岔路。
- **判断**：**值得做**。唯一压低它的因素是这条路不在主产品路径上（主路径是 Anthropic 客户端 + Responses 上游），但它是 served 的。

### 5. tui §0.5 — 上游 usage 自相矛盾时没有落点，**且它「不做的理由」已经过期**

- **出处**：`tui/deferred.md` §0.5
- **它是什么**：`_convert_usage` 会产出 `usage_inconsistent` 这类事实（缓存明细之和大于 `input_tokens`、`reasoning_tokens > output_tokens` 等），但公开包装 `anthropic_usage_from_responses()` 只返回 `.wire`，把 facts 与 exact usage 全丢掉；usage 非法时两处都返回 `{}` 继续交付，运行时零信号。
- **不做的后果**：上游报了自相矛盾的 usage，管线照常给出看起来正常的数字，没有任何地方说明它来自矛盾输入；「上游没报 usage」与「上游报了坏数据」在日志上完全一样。已核实 `protocols/responses_anthropic.py:214` 的包装签名返回 `dict[str, int]`，`translation_driver/responses.py:86` 就是这样用的。
- **⚠️ 台账写的理由现在是假的**：它说「为一个 minor 引入这个依赖方向不划算，**当前 `src/app/pipeline/` 下没有任何模块 import `app.observability.logging`**」。已核实 `src/app/pipeline/hand_over.py:18` 现在就 `from app.observability.logging import get_logger`（`b973ed0` 引入）。那个依赖方向已经有人开了，成本论证不再成立。
- **规模**：改一个模块。
- **判断**：**值得做**，且**这条台账的正文必须先更正**——否则下一个读它的人还会按一条已经不存在的约束把它放回去。

### 6. 两条一行注释级的假事实（合成一件做）

**6a. retry 8f —— `schema.py` 声称 `client_request_deadline` 是 systemd 停机超时的基准**
- 已核实 `src/app/config/schema.py:238` 的注释「Also the base for the systemd stop timeout.」仍在，而 `client_request_deadline` 默认 3600；实际 `contrib/systemd/ghc-api-proxy.service:28` 是 `TimeoutStopSec=330s`，来自 `install-user.py` 的 `SYSTEMD_STOP_TIMEOUT_SECONDS`（300+30，即 `DEFAULT_GRACEFUL_TIMEOUT_SECONDS`）。**全仓没有任何一处从 `client_request_deadline` 推出这个数。**
- 不做的后果：调这个键的运维会以为自己在动停机超时。规模：改注释。台账自己写的处置就是「顺手改」。

**6b. error-envelope E-1 的「顺带要修的」半条 —— `inference.py` 说守卫触发时客户端拿到空 body**
- 已核实 `inference.py:331` 现在写的是「the guard's exception simply ends the response — 200, `text/event-stream`, and whatever had been buffered, **which is nothing**」，而 E-1 的实测是**客户端拿到了已到达的上游字节（实测 69 字节）**——这条腿一边读一边写，不存在「缓冲了什么」这回事。
- **这半条的闭合载体已经开走了**：台账说它「随计划的 J 片或 F 片修正」，而 `error-envelope/plan.md` 显示 J 片（`c4216f7`）与 F 片（`633b404`）**都已完成**，两次都没带上它。
- 规模：改注释。**判断**：值得做，且要在 E-1 里换一个新的闭合载体，否则它会永远挂在两个已经走掉的车上。

### 7. auto-mode D3 前半 —— `from_history.py` 的注释说历史库没存入站 body

- **出处**：`auto-mode-classifier/deferred.md` D3
- **它是什么**：已核实 `tests/int/recorded/from_history.py:211` 逐字仍是 `# Left empty: history records no request body, so there is nothing to project.`，而 D3 的取证证明历史库完整保存了入站 body（`payload-skeleton` + `payloadSequences` + `v3_sequence_nodes` 三段可拼回）。
- **不做的后果**：将来要给上行方向造夹具的人，会照这句话去发真实上游请求或手写 fixture，而实际上可以从历史库导出真实骨架——那正是项目「Upstream behaviour is recorded, not imagined」要的东西。这不是注释洁癖，是一条会把人引去走远路的假路标。
- **规模**：改注释（一行）。**把 `from_history.py` 扩展成支持请求侧投影是另一件事**，见第三节。
- **判断**：注释这半**值得做**，便宜且止损明确。

### 8. retry §21 的 S3 那一格 —— 唯一已经真的伤过人的静默丢弃

- **出处**：`upstream/retry-and-continuation/deferred.md` §21（10 处静默丢弃点的表）
- **它是什么**：`openai_responses.py` 的 `_close` 在找不到对应 draft 时直接 `return ()`，整个 output item 消失且零痕迹。
- **不做的后果**：这一格制造过生产事故——Copilot 在 `output_item.added` 与 `output_item.done` 上发不同的 `item.id`，于是 `_close` 永远找不到 draft，**整条回复装配成零字节，而 1243 条测试全绿**。已核实判据已改成 `output_index` 优先（`:491-496` 的 `_item_key`，注释记录了这次事故），并且新增了 `web_search_call` / `tool_search_call` 的补救分支（`:536-548`），**但兜底的 `if not rescuable: return ()` 仍然无痕**。对照之下，`f21d7f4` 已经修掉的那三个事件在 3000 万根帧里出现 0 次。
- **规模**：改一个函数（加一条日志）。
- **判断**：**值得做**。台账把 S3 与 S7（任意未识别事件，需要一份「明知故忽略」词表）捆在一起推迟了，但 S3 不需要词表——它是「本该有 draft 却没有」，任何时候都值得出声。**S7 与整体日志级别另裁**，见第三节。

### 9. auto-mode D4 —— 把内嵌的网关契约文档单独立项

- **出处**：`auto-mode-classifier/deferred.md` D4
- **它是什么**：Claude Code bundle 里内嵌了一份写给网关/代理实现方的契约文档，含一张有序的 `error.message` → 错误类别映射表（`prompt_too_long`、`max_tokens_context_overflow`、`beta_header:<value>`、`effort_unsupported`、`image_block` 等）、阻断请求的标准格式（`400` + `x-should-retry: false` + `policy_blocked`）、以及端点形状约定。
- **不做的后果**：`error-envelope` 主题刚刚落地了 I / J / K / N / R 五个切片，把上游错误映射成客户端能正确恢复的形状——而**校准这套映射的权威表就在客户端自己的 bundle 里，没人对过**。那份文档自己写着「分类要保守，一个错的 token 会触发错误的客户端恢复动作」。不对表的代价不是漏一个 case，是我们的映射可能触发客户端做错误的自愈动作。
- **规模**：需新设计（一个调研切片 + 可能的 spec 修订）。不改代码就能先产出对照表。
- **判断**：**值得做**，但排在上面几条之后，因为它是投入型而非止损型。**时机上它现在最划算**——`error-envelope` 的映射刚定型，趁热对表比半年后回头对便宜得多。

### 10. tui §0 —— `/responses` 与 `/chat/completions` 入站的回复汇总为空

- **出处**：`tui/deferred.md` §0（台账自评「优先级最高，因为是功能缺失而非用词问题」）
- **它是什么**：日志行里描述回复内容的字段（推理块、工具调用、stop reason、token 用量）只在入站格式是 Anthropic Messages 时才有；已核实 `src/app/pipeline/reply.py:66-68`，`reply_summary` 对其它入站格式直接 `return None`。
- **不做的后果**：那些行完全不报告回复内容。**返回 `None` 是刻意的诚实**（比伪造一个 `end_turn` 好，那个回归 2026-08-20 出现过并已被测试钉住），所以这不是缺陷，是缺口。
- **规模**：需新设计。要一个 Responses 形状的读取器，外加 Responses 自己的 usage 与 stop reason 读法——而 usage 的键不同（`input_tokens_details.cached_tokens` vs `cache_read_input_tokens`），改法会波及**主产品路径**的 token 列。
- **判断**：**值得做，但先测流量占比再排期**。台账自己也说 ROI 取决于 `/responses` 入站实际有多少流量，而这个数**至今没测**。测它比做它便宜得多。放在本节最后正是因为这个前置条件没做。

---

## 二、应该关掉的

以下条目**已经做完或已经不成立**，但仍然躺在台账里。每条附本次核实的证据。

### A. 已实现，代码里有指名回指

| 出处 | 条目 | 证据 |
|---|---|---|
| retry | **8a** 客户端时限触发返回 502 `CancelledError` 而非 504 | 已修。`src/app/pipeline/direct_driver/base.py:153` 现在是 `except asyncio.CancelledError: raise`，其注释逐字写明「The client was told 502 `CancelledError` … Measured 2026-08-22; see `deferred.md` 8a」。台账里 8a 那行的处置栏「要修」已过期 |
| retry | **§12** 上游在终结事件之后 reset：完成行不再留痕 | 已修，且用的正是台账候选做法①。`inference.py:590` 有 `tore_after_terminal` 字段、`:509` 接了 `on_tear_after_terminal=accounting.note_tear_after_terminal`、`:623` 写进 trace，`observability/request_trace.py:159` 与 `request_log.py:152` 都有该字段。**同一件事已在 22 之七的表里记为已修，§12 正文却仍写着「归交付侧重写切片，本主题登记不动手」——一件事在同一份台账里同时记着开与闭** |
| retry | **§19** 截断 error 帧的 message 在 Anthropic 上游腿上字面是错的 | 已修。`stream.py:569` 现在是 `"upstream stream ended before a terminal event"`，上一行注释写明「Names no upstream dialect. … `deferred.md` §19」。`code` 按台账要求未动 |
| retry | **§4** 上游 SSE 中途的 `error` 帧 | 处置已不再是「坏的」。R 片 `f12f76d` 已落地：`openai_responses.py:51` 的 `_FAILURE_EVENTS = frozenset({"error", "response.failed", "response.cancelled"})`，`:67-76` 读两种 error 形状（含 Copilot 的嵌套 `{"type":"error","error":{...}}`），`anthropic_messages.py:318-330` 读 `event: error`。**`error-envelope` 的 E-8 早就说了这条要按新事实改写，两天没人动。** 剩下的「零观测、形状是二手」这条事实属证据表，不属待办栏 |
| retry | **§7 的两个成员已不存在** | `max_tokens_as_retryable`：全仓（含 `.dev`、测试）零命中。`continuation.*`：按用户裁决删除完毕，`continuation_messages` 在 `src/` 零命中。**仍在的只有** `RetryBudget`（`direct_driver/`）、`streaming/buffered_retry.py`、`streaming/delayed_commit.py`、`streamReplay.max_retries`、`hedge`——按「不要动」的裁决保留 |

### B. 正文自己已标闭合，但没有移出

- **retry §22、22 之二、22 之三、22 之六**：分别标着「已裁决并落地（`0ca87b9`）」「已修（`0ca87b9`）」「已归档（2026-08-23）」「已修（`1a34042`）」。四条的正文都是完整的事后记录，属于 `decisions.md` 或 `status.md`。留在待办栏里，每个读者都要重读一遍才知道不用管。
- **retry §2、§3、§5、§6、§11**：已经是墓碑（正文只剩一句「已闭合，已移出」+ 编号保留说明）。**这些墓碑是对的，不要删**——`stream.py`、`openai_responses.py`、`responses.py`、`inference.py`、`base.py` 等 6 个生产源文件按号引用本文件。墓碑与「已闭合但正文完整」是两回事，前者留，后者移。
- **error-envelope E-8**：正文首行就是「**已闭合**，闭合于 2026-08-24，R 片落地（主仓 `f12f76d`）」。可移出，只需把「retry 第 4 条仍需改写」这句转成一条对那份台账的交办。
- **h2-goaway §3**：正文写「这笔欠账 2026-08-21 移交给 `../retry-and-continuation/`，本主题不再跟踪它」。既然不跟踪，就该只剩一行指针，而不是 10 行含一个「2026-08-22 更正」的历史层。

### C. **`delivery-keepalive/deferred.md` 整份需要重构**

这是本次清点里最大的一处收益。该文件 228 行，逐节核对后：

- **已实现/已裁决/已删的**：D-1、D-2、D-3a、D-3b、D-3c、D-3d、D-3e、D-3f、D-5、D-6、D-7、D-8、D-9、D-10，以及「初版的三条缺陷」「用户裁决一/二」「合入后复评查出的三条」「未采纳的建议」——**十几个小节，全部是完成记录**。
- **真正开着的只有两条**：D-4（`client_delivery.hedge` 只有配置项没有实现，已核实 `schema.py:255` 是唯一命中，用户已裁「未来做，暂缓」）与文末的「错误帧的交付时机要不要做成守卫」（未裁决）。
- **另有一条交还用户的文档问题**（`http2_ping_interval` 在人写配置文档里读起来像是生效的保活），既不是待办也不是完成项，是一条待用户处理的交还。

**判断**：把完成记录移进 `delivery-keepalive/status.md` 或 `decisions.md`，本文件缩到两条待办 + 一条交还。理由不是整洁——是这份文件里有大量「我先前搞错了 / 初版写反了 / 本条初版的论证是错的」这类**极有价值的教训记录**，它们埋在待办栏里没人会去读，放进 decisions 才会被下一个人读到。

### D. 已不成立或已被别处接管

- **h2-goaway §5 的第一项**（`HistoryConsumer` 没接活链路，「尤其值得单独确认是否有意为之」）：**这个问句已经被回答了**。已核实 `HistoryConsumer` 在全仓（`src/`、`tests/`）零命中，整个 history 链已归档进 `src/.archived/app/history/`（`2248a69 refactor: move the chain no entry point reaches out of the source tree`），并且 `.dev/docs/history/` 是一个有 `spec.md` / `decisions.md` / `proposal.md` 的活主题，专门在建取证记录能力。答案是「有意为之，且已另立主题接管」。**第三项仍然成立**——本机 `systemctl --user` 无本项目单元，journald 仍空。
- **tui §2**（`enc` / `txt` 标签未按上游改名）：正文的结论是「**不建议改**」，并给了理由（两侧语义相同、宽度成本每行都付）。这是一条裁决，属 `decisions.md`，不属待办台账。留在这里，每个读者都要重新判断一次「要不要改」。
- **retry §18**（一条提交信息缺字）：正文自己写「历史已发布，不重写。**这一条永远停在这里，不会有人去做它**」。一条按定义永不执行的条目不是待办，是一条给后来者的注解，属代码注释或 `README` 的读史提示。
- **client-leg-formats 的「已在本轮修掉的（不要重复处理）」整节**：28 行、三批共 20 条完成记录，占该文件的一半以上。该文件真正开着的只有 U-1 与 n-1 两条。

---

## 三、需要用户裁决的

每条写清**要裁的是什么**与**有哪几个选项**。按「不裁的代价」排序。

### 1. retry §5 第 2 格 —— 排空主动拒绝重开时，要不要为交接开口

- **要裁什么**：优雅关闭排空期间拒绝重开的那条流，`_hand_over` 因 `committed_count == 0` 返回 `None` 而裸抛。要不要在这一格允许交接。
- **选项**：(a) 开口——`_hand_over` 被允许在 `committed_count == 0` 时动作，它第一件事就是 `session.finish()` 把缓冲块冲出去再附上 `tool_use`；(b) 维持现状。
- **不裁的代价（已量化，一手实测）**：`client_delivery.buffering_policy` 取 `full` 或 `until-tool-use` 时，整轮的完整块全压在 `BlockBuffer` 里不释放，`committed_count` 恒为 0。此时关机 + 撕流 → **缓冲区里那一整份已经算完的回答被整批丢弃**。而 `db49581` 之前这一格会重放并大概率成功。**即：本项目自己的改动让一条既有的丢失式结局在非默认配置下变得常态可达**，而每一次带在途流式请求的优雅重启都可能撞上。
- **人写文档的措辞是许可式**（「优雅关闭时报错……**可以**走下文合成续写机制」），所以现状不违反文档，但也没被文档裁定过。
- **判断**：**这是本次清点里最该先裁的一条**——代价已量化、机制已现成、开口的实现是加法。

### 2. retry §20 剩的一半 —— 「叫不出名字的失败」该不该可重放

- **要裁什么**：`normalize_upstream_error` 认不出的异常（裸 `h2.ProtocolError`、`httpx2.DecodingError` 已实测），默认可继续还是默认不可继续。
- **不裁的代价**：交接那一半已经闭合（`78be0d4` + `a7a0e05`），所以客户端至少能收到东西；剩下的是「本可继续的网络类失败白白丢一次重放预算」。**本文件另有三处按此条引用**（§5 第 4 格、§22 的 DecodingError 残留、§49 行），生产代码 `stream.py` 也引——它是好几条的共同上游。
- **规模**：裁完之后是改一个函数。
- **判断**：**值得裁，因为它挡着好几条**。这条 2026-08-24 曾被整体标成「已闭合」并被异源评审推翻，注意别再犯——**开着的是重放那一半，不是交接那一半**。

### 3. h2-goaway §2 / STR-04 —— `context.reply` 是否放宽到未完成的回复

- **要裁什么**：`context.reply` 现在 gate 在 `terminal.seen`，被截断的回复不进 `reply`。放宽是 **hooks 与 History 的契约变更**（现有契约是 `reply is not None ⇒ 回复已完成`）。
- **已核实**：`inference.py:607-608` 的 `if terminal.seen and self.context is not None:`，其上方注释写明「widening it is a contract change that belongs with the STR-04 slice which needs a failed History anyway」。
- **不裁的代价**：失败的回合在 hooks 与 History 里完全没有记录，取证少一半。
- **选项**：(a) 放宽 `reply` 并同步改契约文档与所有消费方；(b) 另加一个字段承载「未完成的回复」，`reply` 语义不动。
- **判断**：与 `history` 主题正在做的取证记录能力**强相关，应当同一切片裁**。

### 4. delivery-keepalive —— 错误帧的交付时机要不要做成守卫

- **要裁三问**：① 要不要加一道守卫强制错误帧早于首个非 thinking 内容块；② 若要，落在交付链哪一层（framer 管不了时机，候选是 `stream.py` 的交付点或块提交处）；③ 与「保活提前发 `message_start`」的既有取舍怎么排序，因为两者争的是同一个窗口。
- **背景已就位**：`error-envelope/spec.md` §6.3 的两条硬约束里，「形状」那条已由 F 片（`633b404`）落地，「时机」那条明确移交本主题。
- **判断**：形状那半已经做完，时机这半再拖就会变成一条无人认领的孤儿移交。

### 5. error-envelope E-9 —— 上游报告失败时是否也该先给 hand-over

- **要裁什么**：干净 EOF 时失败会先交给 hand-over（客户端拿到 `turn_interrupted`，能继续这一轮）；上游**明确报告**失败时走错误帧／原样重放，不经 hand-over。要不要统一。
- **两难点**：直连腿上 Spec §3.4 要求「原样重放上游的事件名与完整 payload」，hand-over 会取而代之，二者不能同时满足；**翻译腿没有这条约束，可以两者兼得**。
- **不裁的代价**：两种失败对客户端的价值不同（一个能继续，一个只能重来），而现在区分它们的是「上游有没有说话」而不是「客户端能不能继续」。
- **若裁「是」，需同时裁**直连腿上它与 §3.4 的优先级。

### 6. error-envelope E-5 —— `ApiError` / `classify_error` 的去留

- **已核实**：`ApiError` 与 `classify_error` 在 `src/` 里的引用只有 `app/models/common.py:54`（`from_api_error`）与 `app/streaming/sse.py:149`；而这两个模块的出口（`create_sse_response`、`format_sse_event`、`ErrorResponse`）**在 `src/` 里除自身包的 `__init__` 再导出之外零消费方**。`errors.py:315` 自己的 docstring 写着「The legacy carrier, kept because `app.models.common` and `app.streaming.sse` still reference it」——三者互相引用，整块没有活链路入口。
- **选项**：(a) 整块移进 `src/.archived/`（该机制已成熟，`_ARCHIVED` 守卫已实测有鉴别力）；(b) 保留并写出它们的外部契约。
- **为什么归裁决**：`never-delete-implemented-functionality-unsolicited`。且台账已注明 I 片会改 `ErrorCategory` 与 `WIRE_TYPES`，若 `ApiError.wire_type` 因表结构变化而失效，**要立刻重评而不是顺手删**。
- **判断**：现在裁最划算——`src/.archived/` 已经有先例、有守卫、有 README 记录理由。

### 7. retry §22 之五 —— `copilot.py` 剩的两个 header wrapper

- **已核实**：`build_copilot_identity_headers`（`src/app/upstream/copilot.py:38`）在 `src/` 与 `tests/` **零调用者**；`build_copilot_headers`（`:42`）在 `src/` 零调用者，唯一调用者是 `tests/unit/upstream/test_upstream_client.py`。活链路直接调下一层。
- **选项**：(a) 归档／删除；(b) 写出保留它们的外部契约。
- **判断**：**「有测试在保它，不等于产品在用它」**——这正是本项目已经付过一次代价的形状（`parse_prompt_limit_error`）。与第 6 条同批裁最省事。

### 8. retry §22 之七剩的一条 —— 要不要为消除误归因放弃族级映射

- **要裁什么**：httpcore 在 body 路径上 `acknowledge_received_data` 抛出的裸 `H2Error` 是**依赖自己的记账不变量**被破坏，位置在 marker 之下，因而被归为上游。消除这个误归因要放弃族级映射。
- **不裁的代价**：一小类本方/依赖方的故障被报成上游。**但放弃族级映射会把已经付过代价的那个真实故障（GOAWAY 从守卫缝隙裸奔）重新打回 `internal` 且不可重放**。
- **判断**：现状（明账 + 四格都留痕）已经不难受了。**倾向维持现状**，但要用户点头才算结案。

### 9. retry §21 的日志级别与措辞（S1、S2、S4—S10）

- **要裁什么**：十处静默丢弃里，S3 之外那九处的日志级别与措辞。特别是 S7（任意未识别事件），不吵就得有一份「明知故忽略」的词表，而本项目规矩是**上游行为靠录制不靠想象**。
- **不裁的代价**：用户 2026-08-22 已裁「已知不处理的路径绝不能静默，应该打日志」，而 `f21d7f4` 只兑现了三个上游失败事件那一格——**一条已下的裁决执行了三成**。
- **判断**：先做 S3（第一节第 8 条），其余成批裁。

### 10. server-layout D-B —— 未实现端点的错误信封是否按 inbound 方言分化

- **要裁什么**：Gemini 路径的 501 现在用本代理通用信封 `{"error": {"message": ...}}`；旧链与参考实现（`copilot-api-js`）答的都是 Gemini 信封 `{"error": {"code", "message", "status"}}`，Gemini 客户端 SDK 解析的是 `error.code` / `error.status`。
- **不裁的代价**：Gemini 客户端读不懂我们的 501。**但一旦分化，Gemini 路径上所有错误都要跟着分化**，波及面远大于「留空」。
- **相关**：与 `error-envelope` E-2（框架自身 404/405 用另一种信封）是同一族问题——**该 app 里现在有三种信封**（Starlette 的 `{"detail":...}`、本项目的 `{"error":{...}}`、未来可能的 Gemini 形状）。建议一并裁。

### 11. h2-goaway §1 —— `max_streams_per_connection` 取什么值

- **要裁什么**：默认 0（关闭）要不要改。已核实 `schema.py:132` 仍是 `default=0`。
- **给选值人的事实**：上游通告 `MAX_CONCURRENT_STREAMS = 100`，所以只有我方的 cap 起作用；姊妹项目 `copilot-api-js` 发的是 **1**，测到成批失败占比从 57.6% 降到 5.9%（**但本项目的规矩是不把它的默认值当契约**）；代价 PoC 实测每条连接边际 ~87 KiB RSS、1 个 fd，TLS 握手 ~155ms 是最大项。
- **新信息（本次核实）**：多 provider 改造之后每 provider 一个 client，跨账号的爆炸半径已经被切开了，这个 cap 现在只管同一 provider 内部。
- **判断**：默认关闭是刻意的（「本项目没有任何测量支持某个具体数字」），**这个理由今天仍然成立**。要裁得先有测量，见第五节。

### 12. tui §1 —— Responses 上游的 stop reason 要不要跟随上游用词

- **要裁什么**：日志行上的 `end_turn` / `max_tokens` 在 Responses 上游是合成词（上游实际发 `response.completed` / `response.incomplete` + `incomplete_details.reason`）。要不要跟随。
- **不裁的代价**：一条 Responses 行现在可能读作 `function_call(Bash)`（上游真名）紧邻 `end_turn`（合成词），词汇一半一半。**这是已知且有意接受的状态。**
- **决定需要的信息**：`end_turn` 出现在几乎每一行上，改词影响面远大于 `tool_use`。台账建议**两者分开裁**。

### 13. retry §10 —— 缺一个 schema → example 的反向检查

- **已核实**：`tests/unit/config/test_config_schema.py` 有 `test_authoritative_example_config_parses`（正向：example 的键 schema 认不认），**没有反向**（schema 新增的键有没有写进 example）。`client_delivery.auto_retry_tool_call_full_name` 正是从这个方向漏掉的。
- **为什么归裁决**：它是一道守卫，而本项目对「把守卫接成阻断」有明确态度——**可以写检查脚本，但把它接成阻断门是用户的决定**。
- **选项**：(a) 只加测试不接门；(b) 不加；(c) 加进现有测试文件（那本身已经是 pytest 的一部分，等于接了门）。**注意 (c) 与 (a) 在本项目的实际效果相同**，这一点要在提问时说清楚。

### 14. retry §7 剩的一格 —— `decide_stream_ending()` 的 `COMPLETE` 形状

- **要裁什么**：该纯函数的 `COMPLETE` 那一格从唯一生产调用点不可达（调用者必须先答完「上游说完了没有」）。两个选项台账已写好：(a) 让它只裁「未完成流」（去掉 `terminal_seen` 参数与 `COMPLETE`）；(b) 重塑参数使调用者能在异常分类之前问出完整 verdict。
- **台账明确写了不要做的第三种**：不要改成在 verdict switch 里处理 `COMPLETE`——那条路对裸 `h2.ProtocolError` 根本到不了。
- **判断**：低紧迫。按「不删未接线功能」的裁决它不会被删，只是形状怪。

### 15. client-leg-formats U-1 —— 补录带 `function_call` 的 Responses 流式 cassette

- **要的授权**：补录要用凭据、发真实上游请求（`tests/int/recorded/record_cassette.py`）。已核实仓库五份 cassette（`anthropic_to_responses_stream`、`history_anthropic_stream`、`history_responses_stream`、`responses_web_search_nonstream`、`responses_web_search_stream`）**`function_call` 零命中**。
- **不做的后果**：`_function_call` 那组帧与 reasoning item 的 `summary_text` 形状只由 openai SDK 3.3.1 的类型担保，而 SDK 的 `construct_type` 是宽松构造不校验。已加了一条「逐事件对账 SDK 必填字段」的测试兜住缺字段那一层，但**管不了「字段齐全而语义错」**。
- **判断**：需要用户授权发真实请求，属第 15 项而非「可以直接做」。

### 16. auto-mode D2 —— 判据在真实流量上从未命中过一次

- **要用户做什么**：把 Claude Code 切到 auto mode，打开 `decision: allow`，确认日志里出现命中行、且客户端没有因为回复不可解析而重试（重试会表现为同一动作前连续多条命中）。**几分钟的人工确认，不是自动化任务。**
- **已核实环境事实仍成立**：`~/.claude/settings.json` 的 `defaultMode` 仍是 `"bypassPermissions"`，该模式下客户端根本不调用分类器。
- **不做的后果**：`auto-mode-classifier/spec.md` 里所有「客户端会接受这个回复」的陈述**强度停在「从源码推出、足以据以实现」，不是「已观测」**。这个特性的全部证据是三个版本的客户端源码静态阅读 + 历史流量。
- **判断**：只有用户能做，且很便宜。**建议直接问用户愿不愿意花这几分钟。**

### 17. auto-mode D3 后半 —— 是否扩展 `from_history.py` 支持请求侧投影

- 与第一节第 7 条（改注释）分开：注释是止损，扩展是投入。要裁的是值不值得为上行方向建夹具能力。

### 18. client-leg-formats n-1 —— `response.id` 要不要加 `resp_` 前缀

- **已核实**：`openai_responses.py:142` 直接用 `self._response_id`，无前缀。上游真实值是 416 字符的 base64 串，我们本来就不模仿。
- **要裁什么**：是不是要迁就「按前缀识别 id」的客户端。**兼容性口味问题，不是缺陷。**

---

## 四、可以放着的

这些留着不亏，**每条附「为什么放着不亏」**。

| 出处 | 条目 | 为什么放着不亏 |
|---|---|---|
| auto-mode | **D6** M2（转录包裹判据）没有单独关闭的开关 | 触发条件极窄（某客户端把 `<transcript>\n` 用作末条 user 消息首块 + 同消息内有闭合块 + 满足结构门槛），今天零观测；真发生了短期一行改常量即可。已核实 `auto_mode_classifier.py:27` 的 `_TRANSCRIPT_OPEN` 与 `:177` 的配置项并存 |
| error-envelope | **E-2** 框架自身 404 / 405 用另一种信封 | Spec §11 已排除并写明重开条件（要单一信封先得决定无 route 时用哪种方言 fallback）。未注册路径推不出 `inbound_format`，「按方言渲染」在那里没有定义域 |
| error-envelope | **E-3** 响应头黑白名单的内容 | 名单由用户亲笔文档规定，Spec 引用不改写。**这是排除记录，不是待办** |
| error-envelope | **E-4** Gemini 成功请求的 wire 翻译 | Spec §11 排除；Gemini 的**错误**信封已在射程内（J 片已落地）。实现要点在 server-layout D-A |
| error-envelope | **E-7** `ResponsesAssembler` 不读 `output_item.done` 里的 content | 已核实仍然如此（`openai_responses.py:602` 的文本兜底只用 `draft.text`）。但真实上游的文本一律走 delta 累积，`done` 里的 content 是冗余；只有构造得出的 mock 才会命中 |
| error-envelope | **E-10 / E-12** 上下文超限的两个未映射条件 | 都在**等一份真实样本**。E-10 在本机 145,781 个 operation 里零命中；E-12 的 48 例上下文超限全部是建流前 400，无一以流内事件到达。**凭客户端能力反推一个上游从没发过的条件，等于替上游发明错误**——这条自我约束正确，不要为了清台账而破例 |
| server-layout | **D-A** Gemini 实现前必看的四件事 | **这是指路牌不是待办**。已核实四个归档件都在（`src/.archived/app/protocols/gemini.py`、`models/gemini.py`、`tokenization/gemini_estimator.py`、`tests/.archived/.../test_gemini_protocol.py`）。它存在的全部意义是「Gemini 那天真要做时，这些东西在哪」 |
| server-layout | **D-C** 升级 FastAPI 时要重跑的判据 | 同上，是条件触发的检查清单。已核实 fastapi 仍是 0.141.1 / starlette 1.6.0，未升级；`inference.py:146` 的 `request.scope.get("route")` 仍在。失效形态是「Azure 与 Gemini 全线 404、其余照常」的局部退化，不是错路由 |
| delivery-keepalive | **D-4** `client_delivery.hedge` 只有配置项没有实现 | 用户已裁「未来做，目前暂缓」。已核实 `schema.py:255` 是全仓唯一命中 |
| retry | **§1** 上下文超限 400 剩的一条 | 「不是没排期，是没有可查的东西」——账户类型维度 history 库无此字段，`/chat/completions` 腿只有第三方 2025-12 录制。**只能等新录制** |
| retry | **§5 之三** 741 条 `NGHTTP2_CANCEL` 的腿间不对称 | 归属未查清，不属该条。**登记的价值在于：谁要拿这批数据做别的统计，得先解决归属** |
| retry | **§17** 重开不重建 framer | 今天路由对同一请求是确定的，这条路不可达。登记只为「将来加入模型回退时它会无声出错」 |
| retry | **8b / 8c** 客户端时限的覆盖范围、隐式的 httpx `read=600` | 8c 那个 600 秒是隐式契约，值得写进配置文档，但不影响行为。8b 要复用 `with_deadline_at` 的模式，是个明确但不紧迫的加法 |
| retry | **8d** 三种失败对客户端逐字节相同 | 已部分兑现——客户端时限那一格现在发 SSE error 帧（已核实 `stream.py:426`）。**其余各格「维持不可区分」是刻意的**，`stream.py:419` 的注释写明「widening the frame to cover them is a separate question with its own answer to find」 |
| retry | **8e** 关机两条路径 | 归 `deployment-systemd` / `graceful-shutdown` 主题，本主题只是登记 |
| retry | **8g** 两处潜伏泄漏 | 两条今天都不可达（一条本部署不可达、一条今天无订阅者），改动面大于收益 |
| retry | **22 之四** 一条状态断言在写下时就已经过期 | **不是待办，是登记形态**——它记的是一族错误的形状（文档照着一份自己已经过期的心智模型写，读起来与刚核实过的结论毫无差别）。这类条目应当搬去教训文档而不是删掉 |
| tui | **§3** `[GONE]` 分不出「客户端走了」与「我们自己关停了」 | 台账自评「**证据强度仅为『已想到』，未观测到任何人因此误判过**」。多一档就多一个要维护的词，而这条区分只在关停这一个窗口内有意义 |
| tui | **§4** 计数行说不出上游是怎么失败的 | 已核实 `count_tokens_attempts` 仍是「`driver.py:342` 写、零消费者」。但 `provider(ghc-failed,local)` 已经把「要不要看一眼」交付给读者了，剩下的是排障时才需要的细节，而排障时结构化记录本来就在手边 |
| h2-goaway | **§4** 「上游响应被提前关闭」的频率没有数 | 结构化日志使它可估而非可精确计数（`status=gone` 包含客户端取消也包含 shutdown）。**要精确得先排除 shutdown**——那是第 12 条那类工作，不是这条 |

---

## 五、我没能判断的

**不是空清单。** 以下条目我读懂了内容，但**判断不了它值不值得做**，因为缺一个我无法在只读范围内取得的量。

1. **tui §0 的 ROI —— `/responses` 入站到底有多少流量。** 台账自己写着「流量占比未测，属待确认」。这个数决定第一节第 10 条排在第 1 位还是第 20 位。取它需要读生产日志或结构化记录（`requests-*.jsonl`），我没有取。**建议：先测这一个数，它比做这条便宜两个数量级。**

2. **h2-goaway §1 的取值。** 「默认 0 是刻意的，因为本项目没有任何测量支持某个具体数字」——这个理由今天仍然成立，所以我也拿不出数字。姊妹项目那个 1 的证据（57.6% → 5.9%）是**它的**测量，本项目规矩是不把它的默认值当契约。**要闭合这条得先有本项目自己的测量，而那要生产流量**，与下一条互锁。

3. **h2-goaway §5 与 §4 的互锁。** 「本项目自身的中断频率仍无历史基线」，而基线要生产数据；而是否切到生产（替换现网 `copilot-api-js`）是一次需要显式指令的 cutover。我判断不了这个环该从哪里断开——是先切生产拿数据，还是先在 backup 端口跑金丝雀。**这属于 `service-cutover` 主题的范畴，不在这 8 份台账里。**

4. **retry §5 之三（741 条 `NGHTTP2_CANCEL` 的腿间不对称）值不值得查。** 237 条落在块边界、全部在 Responses 腿、全部恰好停在 `output_item.done` 之后、Anthropic 腿一条没有——「这种不对称不像随机的连接死亡」。我同意它不像随机，但**判断不了查清它能换来什么**：可能揭示上游的一个行为模式（有价值），也可能只是两条腿的帧结构差异导致的采样偏差（无价值）。要判断得先重跑历史库统计，那是一次真正的调查而不是清点。

5. **retry 8b / 8c 是否已被别处解决。** 这两条归 `deployment-systemd` / `graceful-shutdown` 主题的邻域，而那两个主题的台账不在本次范围内。我没有核对它们是否已经在别处闭合。**这正是 8e 那条自己写的处置（「登记，归 deployment-systemd / graceful-shutdown 主题」）留下的缝**——登记在这里、闭合在那里，两边都不知道对方的状态。

6. **error-envelope E-10 / E-12 什么时候能拿到样本。** 两条都卡在「等一份真实上游 body」。我判断不了这个等待有没有尽头——如果 Copilot 永远不这样报告，这两条就该从「等样本」改成「明确不做，重开条件是……」。**区分这两者需要一个我没有的判断：上游会不会变。**

7. **一个我读不懂动机的地方（非台账条目）**：仓库里还留着分支 `fix/upstream-error-events`（即 G1，retry §4 提到的那条）。R 片已经从 `main` 上落地了同一件事（`f12f76d`），我不知道这条分支是已被取代的残留、还是另有未合入的内容。**没有核对它的 diff**（超出「读台账」的范围，且核对本身要跑 git 命令对比两棵树）。如果是残留，它属于 `git-housekeeping` 主题。

---

## 附：本次核实用到的一手证据索引

所有路径为绝对路径下的仓库相对写法，行号为 2026-08-27 `efeab76` 工作树实测。

- 假事实类：`src/app/server/routes/inference.py:291,300-303,333,602`、`src/app/config/schema.py:238`、`tests/int/recorded/from_history.py:211`、`src/app/pipeline/delivery/formats/openai_responses.py:602`
- 已修类：`src/app/pipeline/direct_driver/base.py:153`、`src/app/server/routes/inference.py:509,590,623`、`src/app/pipeline/delivery/stream.py:569`、`src/app/pipeline/delivery/formats/openai_responses.py:51,67-76`
- 已不成立类：`max_tokens_as_retryable` / `continuation_messages` / `HistoryConsumer` 全仓零命中；`src/.archived/app/history/`（`2248a69`）
- 仍然开着类：`src/app/pipeline/reply.py:66-68`、`src/app/protocols/responses_anthropic.py:214`、`src/app/pipeline/translation_driver/responses.py:86,212`、`src/app/pipeline/translation_driver/registry.py:135`、`src/app/upstream/copilot.py:38,42`、`src/app/errors.py:315`、`src/app/config/schema.py:132,255`
- 环境事实：`~/.claude/settings.json` `defaultMode: "bypassPermissions"`；`systemctl --user` 无本项目单元；fastapi 0.141.1 / starlette 1.6.0 / httpx2 2.12.0；`contrib/systemd/ghc-api-proxy.service:28` `TimeoutStopSec=330s`
