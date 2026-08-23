# 未闭合、待查、与明确不做

本文件只列**需要用户裁决**或**已知未闭合**的项。已经定下来的在 `status.md`。

## 已知未闭合

### 1. 上下文超限的 400：两条腿的分类判据不同（原标题「主路径抽不出数字」已撤销）

**2026-08-22 更正**：本条原来的落点是「`parse_prompt_limit_error` 在主路径上返回 `None`，抽不出上下文上限的数字」。**用户质疑该理由是否成立，质疑成立，本项目撤回。**

- 那个数**上游模型目录里就公布着**，逐模型：`limits.max_prompt_tokens: 936000`、`max_context_window_tokens: 1000000`（一手样本 `exp/260820-websearch-probe/raw/models-live.json`）。从一个 400 里反解它，只是对上游已公布事实做交叉验证，不是唯一来源。
- 它的消费端也站不住：`parse_prompt_limit_error` 只有两个调用点——`app/hooks/builtin/token_calibration.py:87` 与 `app/tokenization/service.py:64`，而后者服务的 `/api/tokenization/limits` 在 `docs/.human-controlled/api.md:21` 里已标为**暂不支持**。前者在 **legacy 链路**上：它的两个 hook 只由 `hooks/builtin/__init__.py:17` 的 `register_builtin_hooks` 注册，而那只有一个调用点 `server/app_factory.py:110`，服务进程从 `cli.py:128`/`:154` 起**只构建 `create_pipeline_app(chain)`，从不走 `app_factory`**。措辞刻意不写成「这段代码没接线」——`ObserverEvent.ERROR` 带 `response_body` 的分发确实存在（`pipeline/executor.py:477-487`），准确的说法是**这条链路不被服务进程构建**（异源评审 F16 收紧）。

**这次错在哪**：「抽不出数字」这个说法是从一份调研报告里继承来的，本项目**没问过这个数字是给谁用的**就把它登记成了未闭合项。同一形状值得记住——*继承一个缺口的描述时，先找它的消费端*。

下面是仍然成立的部分：**正面形态是 HTTP 400，48 例一手录制**（`reports/260821-context-limit-400-examples.md`），**两条腿的表达结构性不同**，这关系到重试分类（上下文超限不可重试），与上限数字无关：

| | Anthropic 腿（27 例，2026-07-18～08-08） | Responses 腿（21 例，2026-08-06～08-08） |
|---|---|---|
| `Content-Type` | `application/json` | **`text/plain; charset=utf-8`**，body 末尾带 `\n` |
| `error.code` | `model_max_prompt_tokens_exceeded` | `invalid_request_body` |
| `error.type` | `invalid_request_error` | **没有** |
| `request_id` | 顶层有，另有顶层 `type:"error"` | **没有** |
| message | `prompt is too long: 1051542 tokens > 1000000 maximum`（`>` 在线上是 `>`） | `Your input exceeds the context window of this model. Please adjust your input and try again.` |
| 靠 `error.code` 能否区分 | **能**——其余 400 连 `code` 字段都不带 | **不能**——`Invalid 'input[1].id'`、`Invalid 'max_output_tokens'` 用的是同一个 `invalid_request_body`。只能匹配 message 文本，建议匹配 `exceeds the context window` |

**这条留作已查清的事实，不再是待办。** 人写文档原本写的是 `SSE stop_reason = model_context_window_exceeded`，**该判据已被实测证伪**：Responses 腿的值空间里没有这个东西（`incomplete_details.reason` 20/20 全是 `max_output_tokens`），Anthropic 腿 13 万次请求零观测（Anthropic 枚举里有该值，故属「未观测」而非「不可能」，见第 3 条）。

**顺带证伪一条旧结论**：归档里同伴写过「没有任何一条当前两条正则漏掉的真实 token-limit body」——现在不成立。原因是那份的语料**全部早于 2026-07-18**，而当时没有把这个时间窗写下来。

**仍未查清**（低优先，无消费端）：账户类型维度（history 库无此字段）；`/chat/completions` 腿只有 `vscode-copilot-chat` 2025-12 的第三方录制（第三种形态：OpenAI 措辞 + `model_max_prompt_tokens_exceeded`、无 `type`）。本项目自己不落盘上游 body，`~/.local/share/ghc-api-proxy/rejected/` 不存在，所以这两项只能等新的录制。

### 2. reasoning item 被截断时没有任何信号

`message` 与 `function_call` 的 `output_item.done` 带 `status`，被截断的是 `"incomplete"`。**reasoning item 没有这个字段**——已用正样本对照确认：正常收尾的 reasoning item 与被截断的，键集逐字相同（`content, encrypted_content, id, summary, type`），`summary: []` 在两侧都出现，也不是信号。

response 层有信号（`response.incomplete`），但它晚于 item 关闭到达，要用就得把块扣住——那是延迟提交，会往交付路径塞状态。

**用户 2026-08-21 裁决：历史里没有信号就保持悬念，暂不特殊处理。** 于是 20 例样本里有 6 例（只有 reasoning 中途撞顶）的半截 thinking 块会照常交付。哪天它造成可观测的麻烦，再考虑延迟提交。

### 3. `model_context_window_exceeded` 在 Anthropic 腿仍是可能的

两条腿的权重不同，别混为一谈：

- **Responses 腿**：结构性不存在，值空间里没有。权重强，可据此行动。
- **Anthropic 腿**：Anthropic 枚举里**有**这个值，只是 13 万次请求零观测。这是「未观测」，不是「不可能」。

所以分类表里不要把它写成已排除。

### 4. 上游 SSE 中途的 `error` 帧：零观测

134336 个 operation、约 3000 万根帧里，`response.failed`、`response.cancelled`、上游 `error` 帧**各 0 次**。参考实现枚举过的完整词表（含 Copilot 专有的嵌套 `{"type":"error","error":{code,message}}`）只有旁证。

现状的处置是坏的：这些帧被 `push` 静默丢弃，`terminal.seen` 保持 False，最终发出一条**与「连接被掐断」完全同形**的 `incomplete_responses_stream`。G1（分支 `fix/upstream-error-events`）正是在补这个。

### 5. ~~已交付之后的两条失败路径行为不一致~~ —— 已裁决并落地（2026-08-22）

**用户当日就这两条各下了一条裁决，都已实现（主仓见 `status.md` F 组）。原文保留在下面，因为本条剩下的部分仍然打开。**

- ~~上游干净 EOF 但无终止事件 → 发 SSE `error`。~~ **裁决：细化。** 判断装配器有没有未完成的草稿——**落在块边界（无草稿）就不报错，正常收尾**；**切穿了某个块才算截断**，保持 error 帧。收尾用的 `stop_reason` 是一次合成，因此**做成了配置项** `client_delivery.unterminated_stream_stop_reason`，默认 `incomplete`（上游自己的词），可填 `end_turn`，**留空则整个细化关掉**、退回原行为。守住的不变量没变：**绝不把上游没说完的回合打扮成它说完了**——`end_turn` 不会被默默用上。
- ~~上游撕流 / idle / deadline / 缓冲超限 → 不发任何错误帧，异常上抛截断连接。~~ **裁决：不行，要统一接入重试与续写。** 补了三处：
  1. **交接不再排在异常分类之后**。原先 `eligible` 返回 `None` 就直接裸抛，于是一个分类器叫不出名字的失败（裸 `h2.ProtocolError`）**根本不问交接**。能不能**命名**决定的是要不要再花一次尝试的预算，与客户端能不能把回合接着写下去无关，只有后者属于这道门。**注意范围**：叫不出名字的失败**仍然不重放**——那是第 20 条的产品裁决，本次没有替它作答。
  2. **每一条结局都发帧，然后再抛。** 两半都是必须的：只发帧不抛，调用方就读不到失败，完成行会记 `ok`、失败不留痕（那正是第 12 条的缺陷，等于亲手造一遍）；只抛不发帧，客户端拿到的就是一个 200 加半截 body，与 idle、deadline、代理放弃逐字节相同（第 8d 条）。**先 yield 后 raise**：生成器的 chunk 在 yield 时就写出去了。
  3. **代理自我保护（`DeliveryError`）不重试也不交接**，按人写文档它属于「无法继续」；但同样发帧，不再裸断。

  **归属分三格，各有自己的 code**：`proxy_delivery_aborted`（自我保护）、`proxy_delivery_failed`（装配抛出的，即我方 bug）、`upstream_stream_failed`（其余）。**「我方 bug」是正向识别的**（按身份标记 `assembler.push` 抛出的那一个），其余**默认归上游**——这个默认是载重的：初版反过来写（只有调用方命名过才算上游），而没配 `replay` 时调用方什么都不命名，于是一个普通的 `ConnectionError` 被报成 `internal_error`，代理替上游背锅。**在客户端唯一能读到的那个词上写错责任方，比写一个模糊但正确的更糟。**

  **已知限制**：成帧器抛出的 bug 仍会被归到上游。扩大标记区要把 `yield` 包进 `try`，那会连消费者 throw 进来的异常一起吃掉，代价大于收益。

下面是本条仍然打开的部分。

**一手证据（2026-08-22，`reports/260822-clean-eof-without-terminal.md`）——它对这条细化不客气，如实记下**：

| 问题 | 数字 |
|---|---|
| 干净 EOF 且无合法终止事件 | **109 / 133 929 条上游 SSE 流 = 0.081%**（Anthropic 腿 32、Responses 腿 77）。本项目自己的生产日志 3 / 13 700 = 0.022%。**不是零观测** |
| 其中落在**块边界** | **仅 4 条（3.7%），全在 Responses 腿**。块中途 100 条（91.7%），Anthropic 腿 **32/32 全在块中途** |
| 边界那几条有没有别的线索能判「说完了 vs 被切断」 | **没有**。usage 0/109（它只搭 `response.completed` 走）、`[DONE]` 哨兵 0/109（Copilot 两条腿从不发，该判据恒假）、Anthropic 腿 `message_delta` 0/32。唯一存活的 `item.status == "completed"` 与正常流逐字相同，无鉴别力 |

**所以这条细化改变的是 133 929 条里的 4 条（0.003%）。** 它不是止血；价值在于把「说完了」与「被切断了」分成两件事，不在命中率。**这个代价／收益比值得复核**——一个协议成员 + 一个配置项 + 一个新的合成 `stop_reason`，换 0.003%。已交独立评审评估。

**方法学副产品，比上面的数字更耐用**：该调查用 `origin.stage == "upstream-capture"` 取代了 `from_history.py:107` 的「取变换图的根」判据，从而**把 2026-07-17 那个已知盲区从静默污染变成显式排除**（那 366 个 operation 的帧全标 `recovery-projection`，整体落在分母外），并用这个独立判据逐库复现了 `260821-upstream-termination-reasons.md` 的数字（28904/4、30322/16、1222/0、3903/0，逐值相等）。**同样的改进适用于 `tests/int/recorded/from_history.py:107`，未动，待裁。**

### 5之二. ~~新造的一条：干净 EOF 收尾把「没测过」写成了零~~ —— 登记过头，已收窄（2026-08-22）

**由上面这条细化引入（主仓 `78be0d4`），实现者自查发现，一手实测确凿。**

新的收尾帧发出 `"usage":{"output_tokens":0}`——**一个从未做过的测量被呈现成零**，而这个回合确实产出过块。来源是 `formats/anthropic_messages.py` 的 `terminal_frames` 里 `usage or {"output_tokens": 0}`；**那一行本身是既有的，但改动之前它只在真见过终止事件时才可达**（那时 usage 是真的）。改动让它在完全没有 usage 的情况下可达。

**为什么这不是小事**：本仓已经在同一形状上打过三次——`Terminal.stop_reason` 的空默认（「upstream 说 end_turn」与「upstream 什么都没说」曾是同一个值）、`Terminal.upstream_usage` 坚持用 `None` 而非 `{}`（「零是一次测量，没测过不是」，原话在该字段注释里）、`_snapshot_upstream_connection` 宁可缺键也不写 `""`。这条是同一个错误在第四处出现，而且是本项目自己新造的。

**独立评审复核后收窄了这条，理由比原登记强，采纳**（`reports/260822-review-clean-eof-refinement.md` §1）：

1. **协议把 `output_tokens` 定成必填**（anthropic SDK 1.0.0，`MessageDeltaUsage.output_tokens` 无默认），零是唯一合法占位。「诚实」在这条线上**没有合法拼写**——省略该键是把一个记录问题换成一个协议违规。
2. 「零是一次测量，没测过不是」这条判据保护的资产是**我们自己的记录**，而这条链路上本方记录是干净的：`Terminal.usage` 保持 `{}` 不是零，`request_log` 用 `if "output_tokens" in usage` 判断。**这正是它与另外三例的实质差别**——那三例污染的都是本方记录。
3. 想「不说谎」的操作员已有出口：`unterminated_stream_stop_reason` 留空 → 回到 error 帧，根本不发 `message_delta`。

**所以改的是可见性不是 wire**（主仓 `de5a1ac`）：把 `or {"output_tokens": 0}` 从 `terminal_frames` 的默认参数提到两个调用点，与 `or "end_turn"` 一样显式；`usage` 参数改成必填，好让下一个调用方**必须说出它放的是什么**。

**顺带一条不要将来被顺手「修齐」的**：两条腿对同一个「没测过」口径不同——`ResponsesFramer` 落 wire 上的 `null`（其 schema 允许），`AnthropicFramer` 落零（其 schema 不允许缺席）。**这个不对称是有原因的**，已写进代码注释。

### 5之三. 741 条 `NGHTTP2_CANCEL` 的腿间不对称（不属本题，登记以免丢）

同一份调查顺带量到：741 条 `NGHTTP2_CANCEL` 里有 **237 条落在块边界，全部在 Responses 腿、全部恰好停在 `output_item.done` 之后，Anthropic 腿一条没有**。这种不对称不像随机的连接死亡。**归属未查清。** 它不属于本条（撕断走异常路径，到不了那个分支），但谁要拿这批数据做别的统计，得先解决归属。


人写文档要求这两种都走同一个裁决点。**2026-08-22 已做到**，但下面第 2 格的「要不要为某些情形开口」仍待裁。

**2026-08-22 补一条触发条件的更正（此前只活在会话里，是本条唯一的持久载体）**：曾把 `anthropic-responses-bridge/spec.md` 那条「commit 后发生错误 → 发一个 Anthropic SSE error terminal」理解为「MCP 合成续写**失败**时的兜底」。**这个提法是错的，而且会误导实现**——按它去写会实现一个几乎永不触发的分支。

合成本身**不会失败**：它是纯本地构造（读客户端请求 `messages` 的长度、拼一个 `tool_use` 块、走已有的 block/terminal framing），不发任何上游请求；而人写文档已把最像失败的那一格堵死——「检查客户端请求是否包含该工具调用的定义，如果没有，打印警告日志，但**仍然依样返回给客户端**」。唯一能让它抛的是我方 bug，那种情况按项目规矩就该抛、留 traceback，不该被 error 帧盖住。

**正确的提法是「续写没接手时的 ending」**。**作用域限于流式交付路径**（`_deliver`）；非流式另有其路，见第 6 条。至少三格，今天全部落在「撕断／空 200」上：

1. **非 anthropic-messages 客户端请求**——用户已限定「其他上游请求暂不使用该机制」。判据在**客户端轴**（`route.wire_format` / `inbound_format`），不是上游轴。
2. **一个完整块都没交付过**——门是「已交付过至少一个完整块」。没交付走无痕重试；但重试预算耗尽或 `reopen()` 自己也失败时，既无内容也无续写。`_hand_over` 里已显式写了这一格返回 `None`（`committed_count == 0`），唯一的例外是 `ContinuationSupport.stop_reasons` 里的停止原因——**那是配置项，默认值是 `{"max_tokens"}`，不是硬编码条件**。

   **2026-08-22 补第三个触发条件，且它比另外两个常见得多：排空主动拒绝重开**（主仓 `db49581`）。每一次带在途流式请求的优雅重启都可能撞上，而不是「预算恰好耗尽」这种偶发。

   **同时更正一条本项目自己写错的机制陈述。** 落地 `db49581` 时，提交信息与两处 docstring 都称「交接需要已交付的内容，所以这一格结构上不可能交接」——**这句话是假的**，异源评审实测证伪（`reports/260822-review-drain-suppression.md` major-2）：`_hand_over` 在 `if not started:` 时会自己补 `framer.preamble()`，只把 `committed_count == 0` 那道门短路掉，排空被拒的那条流立刻产出一次干净的交接（日志 `upstream_replay_refused_while_draining` → `turn handed back to the client to continue`，`status=retry`）。挡住它的是**一道可配置的闸**，不是机制的固有属性。已改正代码注释与 `status.md`；此处登记的是那个假理由掩盖掉的真问题。

   **真问题：排空这一格要不要为交接开口？** 人写文档「特别地，优雅关闭时报错不再考虑无痕重试，**可以**走下文合成续写机制」这句，承接的正是它上一句「如果还没交付过完整块」——**说的就是这扇门**。措辞是许可式（「可以走」）而非命令式，所以现状（不开口）并不违反文档；但也谈不上被文档裁定过。

   **不开口的代价已量化，是真的丢东西**（评审 major-3，代码事实，推理链每环已核）：`client_delivery.buffering_policy` 取 `full` 或 `until-tool-use` 时，缓冲策略把整轮的完整块全压在 `BlockBuffer` 里不释放（`stream.py` 自己的注释写明这两种策略下「首块前的窗口就是整个回合」），于是 `committed_count` 恒为 0、`client_has_bytes` 未 set。此时关机 + 撕流 → `decide_stream_ending` 返回 REPLAY → 排空闸拒绝 → `_hand_over` 因 `committed_count == 0` 返回 `None` → 裸抛，**缓冲区里那一整份已经算完的回答被整批丢弃**。`db49581` **之前**这一格会重放并大概率成功（排空本来就在等这个请求）。即：本项目的改动让一条既有的丢失式结局在非默认配置下变得常态可达。

   开口的做法是现成的：`_hand_over` 一旦被允许在 `committed_count == 0` 时动作，它做的第一件事就是 `session.finish()` 把缓冲块冲出去再附上 `tool_use`，这一格自动补上。**证据等级：机制与代价均为确凿（一手实测 + 代码事实）；开不开口是产品裁决，需用户定。**
3. **有意裁决为不可继续的失败**——人写文档的前提是「如果业务可能可以继续」。上游拒绝、转换错误、prompt-limit 不在内；多数发生在 commit 前（还能用 HTTP 错误），但已交付一块之后的转换／assembler 错误落在这里。
4. **种类上本可继续、只是分类器叫不出名字的失败**——**这一格与第 3 格形似而神不同，初稿把两者混写成一格，是错的**。机制是：`_replay_reason` 返回 `None` 时 `_deliver` 直接 `raise torn`，`_hand_over` **根本不被咨询**。于是一个本该续写的网络类失败，只因 `normalize_upstream_error` 没有它的名字（裸 `h2.ProtocolError` 就是），走的却是「不可继续」那条路。**这不是裁决，是漏网。** 详见第 20 条。

**证据等级：够据此写实现范围**（依据是人写文档原文与 `_hand_over`／`_replay_reason` 的现有分支）；**是否现在就接这条兜底，需裁决**。

### 6. 流式与非流式对同一事实给出不同答案

非 `max_output_tokens` 的 `incomplete_details.reason`：流式路径读进局部变量后**不写任何地方**；非流式路径（`translation_driver/responses.py:114-130`）会记进 `conversion.losses` → `handler.py:425-426`。流式那条还违反 `../../anthropic-responses-bridge/spec.md:264-265`。归 C 组。

### 7. 孤儿件与死配置项的处置

`decide_stream_ending()` 之外，还有 5 组零生产调用点的件与 4 个无人读取的配置项：`RetryBudget`、`buffered_retry.py`、`delayed_commit.py`、`continuation.*`、`streamReplay.max_retries`、`max_tokens_as_retryable`、`hedge`。

**用户 2026-08-21 裁决：只删代理内续写机制，其他未接线的功能不要动。** 所以除 `continuation.*` 外一律保留。其中 `delayed_commit.py` 的形状恰好对得上第 2 条将来可能需要的延迟提交，`streamReplay.max_retries`（默认 100）在 D 组接线后会生效。

**2026-08-22 补一条同族的新情况**：`decide_stream_ending()` 本身已接线（`8f654b4`），但 `c86712d` 之后它的 **`COMPLETE` 那一格从唯一生产调用点不可达**——`_deliver` 必须在问它之前先答完「上游说完了没有」，否则一个 `normalize_upstream_error` 不认识的异常（裸 `h2.ProtocolError`）会让完整回复照样被丢。异源评审实测：把该分支改坏，unit+int 1589 条里只有它自己的单测变红。

按上述裁决**不删**，`1479025` 已在该分支加了回指注释。待裁的是形状：要么让这个纯函数只裁「未完成流」（去掉 `terminal_seen` 参数与 `COMPLETE`），要么重塑参数使调用者能在异常分类之前问出完整 verdict。**不要**改成在 verdict switch 里处理 `COMPLETE`——那条路对上述异常根本到不了。

### 8. 生命周期所有权：一处缺口与三条未接线的通道

来源：`reports/260822-lifecycle-ownership-audit.md`（异源审计，11 条发现，10 个实测探针）。裁断是**不需要全面重写**——上游侧的模型自洽且实测有效，客户端侧只有一个原语且被安在最早结束的所有者上，修法是加法。

**这几条登记在这里，而不是留在报告里，是有代价换来的**：其中两条（O5、流式作用域）2026-08-20 的评审报告就已写清，grep 确认**从未进入任何活文档**，因此两天后仍未被修。报告不能是唯一的真相来源。

| # | 事实 | 证据等级 | 处置 |
|---|---|---|---|
| 8a | **`client_request_deadline` 触发时，客户端拿到 502 `{"type":"CancelledError","message":""}` 而非 504。** driver 的 `except BaseException` 吞掉了 `asyncio.timeout` 的取消，那句 `raise UpstreamTimeout` 是死代码 | 实测 | **跨层所有权错误，要修。** 上层用取消表达「时间到了」，下层把取消当普通异常吃掉 |
| 8b | 该时限只覆盖「进入 `handle_bounded` → 上游响应头」，**流式 body 完全在外**；也不是「从受理开始计」——body 读取、JSON 解析、准入排队都在外 | 实测（1 秒时限下 3 秒 body 完整交付） | 要修：把 `with_deadline_at` 的模式复用到客户端时限 |
| 8c | 流式 body 的兜底者只有 `upstream_request_deadline`（1200）是真的；`stream_idle` 与 `response_header` 默认 0（关）；另有一个**没人选过、没文档的 httpx `read=600`**。把 1200 设 0 就只剩那 600 | 实测（`read=600` 随每个请求到达 transport） | 登记。那个 600 秒是隐式契约，值得写进配置文档 |
| 8d | **上游撕裂 / idle 触发 / deadline 触发，三者对客户端逐字节相同**——同样的事件序列、无 error 帧、chunked body 不完整。只有代理日志能分辨。另一对：「EOF 什么都没有」与「成功但零内容块」都是 200 + 空 body + clean EOF，日志一个 `fail` 一个 `ok` | 实测 | `error_frame` 通道**存在但没接到终止路径上**。用户 2026-08-22 已裁决：客户端时限在 body 阶段触发时发 SSE error 帧 |
| 8e | 关机有**两条路径**：systemd 部署走裸 uvicorn（等 300 秒再 `task.cancel()`，级联有效），`ShutdownLadder` 完全不参与；独立路径的 drain **无上限**，其注释前提「请求自带时限」只在 `upstream_request_deadline > 0` 时成立 | 实测 + 代码事实 | 登记，归 `deployment-systemd` / `graceful-shutdown` 主题 |
| 8f | `schema.py:250` 称 `client_request_deadline` 是 systemd 停机超时的基准，实为 300+30，**全仓无此推导** | 代码事实 | 注释失实，顺手改 |
| 8g | 两处潜伏泄漏：`http.response.start` 自身抛异常时生成器从未迭代、上游泄漏（**本部署不可达**，uvicorn 三个实现的 send 断连后静默返回）；`base.py:150-175` 丢弃已拿到的响应从不 `aclose`（今天无订阅者注册 `attempt.succeeded`，潜伏） | 实测 + 代码事实 | 登记，不改——两条今天都不可达，改动面大于收益 |

**明确不做全面重写**，理由见报告第 6 题：上游侧「一个时刻两处施加 + 六层一致的关闭契约」已由实测支持（客户端断连时上游 `is_closed=True`，断连中途与首 chunk 前两种情形都验证过）。

### 9. 一次性交付路径的结局判定不接线（同伴切片）

`one_shot_accounting`（`pipeline_app.py:541`）构造时**不带 `assembler`**，而 `_StreamAccounting.finish()` 把整段结局判定包在 `if self.assembler is not None:` 里。于是走一次性交付的 chat-completions 流，**撕流与客户端断开一律记 `[ OK ] 200`**。

来源：`reports/260822-review-e-group.md` M3。**归同伴的切片**（`2769a64`，2026-08-22 10:38），且他们仍在改该文件（`630f7f3`，11:09），故本主题登记不动手。

### 10. 缺一个 schema → example 的反向检查

`tests/unit/config/test_config_schema.py` 只查「`config.example.yaml` 里的键 schema 认不认」，**不查反向**——schema 新增的键有没有写进 example。`client_delivery.auto_retry_tool_call_full_name` 正是这次从这个方向漏掉的。

补不补由用户裁决：它是一道守卫，而本项目对「把守卫接成阻断」有明确态度。

### 11. ~~客户端时限与「上游已完成」谁先答~~ —— 已裁决（2026-08-22），当前次序正确

**裁决**：`client_request_deadline` 保护的是「这一轮总耗时」，所以**客户端时限先答、`terminal.seen` 后答**。见 `decisions.md` 第二之二节第 18 条。`stream.py` 当前次序已经是这个，无需改码。

保留下面的原始分析，因为它记录了这个次序**是载重的**（不是风格选择），以及一条仍然成立的测试缺陷：

来源：`../../tmp/260822-review-complete-fix-opus.md` 问题 2（异源评审，8 个受控变异）。由 `bce8b0d` 引入的 `if assembler.terminal.seen: break` 带出。

- **真实后果**：上游已发完 `message_delta` + `message_stop`，随后客户端时限到期 —— 当前发 `client_deadline_exceeded` error 帧，**丢掉一条已经攒齐的完整回复**。按上述裁决，这是对的。
- **实测（评审）**：把该支合并进 `if torn is None:` 那一支（即让 terminal 压过 deadline），三条 client-deadline 测试全部转红。
- **仍未闭合的那一条**：`test_the_client_deadline_is_the_one_ending_that_says_so` 与 `test_a_held_back_policy_still_hears_the_client_deadline` 的夹具都携带完整终结事件（`anthropic_stream(...)` 末尾自带 `message_delta` + `message_stop`），因此**它们已经无法区分「时限先到」与「上游已完成后时限才到」**。裁决落定后这两条测试实际钉的是后者，而名字说的是前者。按 `[:-2]` 模式改夹具（与 `c86712d` 对另外两条测试所做的相同）可让名字与内容对上，另加一条专测「上游已完成后时限才到 → 仍报时限」的正样本，才算把新裁决钉住。**这是本条唯一还要动手的部分。**

  **2026-08-22 已完成，见主仓 `08f3c29`**（上面那段是完成前的原始分析，保留原样）。三件都做了：两条夹具改成 `[:-2]`、新增 `test_the_client_deadline_outranks_an_upstream_that_just_finished`、把裁决写在两处分支注释旁。异源评审用两轮受控变异复核（`reports/260822-review-mcp-contract-and-deadline-order.md` F12/F13），结论是**改夹具没有削弱那两条测试名义上的属性**：把整支禁掉时它们照样全红，说明「时限收尾必须是 error 帧」「不得冒充 `message_stop`」「held-back 策略下缓冲块被丢弃」三条仍被咬住，且最后一条在新夹具下**非平凡**（不触发时限时那个块确实被组装出来了）。被移走的只有「次序」那一层鉴别力，由新测试独家接手——次序变异之下，全套件里只有它转红。净增的是「时限落在回合中途」这个旧夹具**根本测不到**的位置。

### 12. 上游在终结事件之后 reset：完成行不再留痕

**这条的归属被改错过一次，改正记在这里而不是抹掉**：标题一度写着「原始来源 `c86712d` 是一个不被任何 ref 引用的对象」。**该断言不成立**——2026-08-22 收尾时逐 ref 复核，`c86712d` 可达自 `archive/260822-complete-not-abandon`（命令：对 `git for-each-ref` 的每个 ref 跑 `git merge-base --is-ancestor c86712d <ref>`）。准确的时间线是三步，全部在 `main` 上或归档 ref 上可查：`bce8b0d`（同伴，在 verdict switch 里判 `COMPLETE`）→ `1743a0b`（同伴，采纳评审意见把判断前移到异常分类之前）→ `f0527e5`（守卫加硬）。本条描述的观测面缺口由这三步共同引入，不归任何单一提交。

来源：同上，发现 A（正反两次实测，用项目自己的 `_StreamAccounting` + `_tracked_delivery`）。

`c86712d` 之前，「上游发完终结事件后连接被 reset」打出的是一行**自相矛盾**的日志：

```
[FAIL] 200 POST /v1/messages … end_turn: stream failed before a terminal event: connection reset by peer
```

（`end_turn` 与「before a terminal event」并列。）修复后是一行**真话**：

```
[ OK ] 200 POST /v1/messages … end_turn
```

**但 `connection reset by peer` 这个事实现在不出现在任何地方**：`_tracked_delivery` 正常跑完所以 `accounting.failure` 是 `None`，局部变量 `torn` 在 `break` 之后被丢弃，没有日志、计数或 trace 字段承接它。而 `_ending()` 自己的 docstring 写着 failure「is the only account of what went wrong that exists anywhere」。

**为什么这值得登记而不是忽略**：`../h2-goaway/findings.md` 的「未决」栏里有两项正需要这类样本——「上游响应被提前关闭的频率」与「本项目自身的传输失败频率（此前零生产数据，日志刚上线）」。一次修复静默削掉了刚建起来的观测面的一角。

**反方向的先例也要一起权衡**：项目已有裁决 `test_a_stream_cut_after_its_stop_reason_is_not_called_truncated`（`tests/int/test_pipeline_app.py:1833`）说「`message_delta` 之后被切断的流已经把客户端应得的都说了，不算 truncated」。按同一逻辑，`message_stop` 之后被 reset 报 `[ OK ]` 是自洽的。所以这不是「显然要修」。

**处置：归交付侧重写切片（同伴），本主题登记不动手。** 理由是留痕需要一条从 `_deliver` 到 `_StreamAccounting` 的新通道——`stream_delivery` 今天完全看不到 accounting——而同伴正在做的重写已经在加 `ContinuationSupport` 这类回调通道，也已认领第 8d 条。硬塞进 `c86712d` 会是与该提交语义无关的管道铺设。

候选做法（评审倾向第一个，本会话同意）：① 给 `_StreamAccounting` 加一个与 `failure` 分开的字段（如 `tore_after_terminal`），完成行仍判 `ok` 但 detail 里附一句 —— `format_completion_line` 的 `if line.detail:` 对任何状态都渲染，**无需改日志格式**；② 只记一条 debug 日志；③ 明确裁决「这个事实不需要留痕」并写下理由（按 `record-what-not-adopted`，不采纳也要写）。

**不要**为此加门禁或指标体系。

### 15. `hand_over_stop_reasons` 在非流式的丢弃上不生效

配置项 `upstream_request_retry.hand_over_stop_reasons` 接到了三处中的两处：流式 assembler、以及两条路的**交接**判断。**没接到非流式的丢弃**——`from_openai_responses_response` 是通过翻译器注册表按格式调用的（`registry.py:120` 的 `reader(payload)`），穿一个配置进去要改所有格式的 reader 协议，而同伴正在那片工作。

**危害有界**：默认值两边一致；而且「不交接就不丢」这条不变量**在任何配置下都成立**——把 `content_filter` 加进配置时，非流式会**保留**半截块**并且**交接（内容不丢，客户端也能续），只是比流式多留一块。反过来的「交接就一定丢」不是不变量，本项目不需要它。

补法：改 reader 协议让它接受一个上下文，或把丢弃从翻译器挪到调用方。两条都比现在这个不一致贵，等它真的碍事再做。

### 16. 反方向（`/responses` 客户端 + Anthropic 上游）仍在抹平

`fef7d96` 只修了一个方向。实测 `to_openai_responses_response`：

```
anthropic stop_reason='max_tokens'     -> responses status='incomplete'  incomplete_details=None
anthropic stop_reason='refusal'        -> responses status='completed'   incomplete_details=None
anthropic stop_reason='stop_sequence'  -> responses status='completed'   incomplete_details=None
```

`refusal` 被报成 `completed`——与 `fef7d96` 消灭的形态同构；`max_tokens` 虽报 `incomplete`，但 `incomplete_details` 从不生成，客户端读不到原因。**该路由是 served 的**（`/responses` + `claude-model`），只是不在主产品路径上。

来源：`reports/260822-review-unreviewed-span.md` minor-8。

### 17. 重开不重建 framer

`_reopen` 刷新了 assembler、buffer、attempt 计数，但 `framer` 是循环外用**第一次**的 `context.id` / `context.resolved_model` 建的。若重开时路由解析到不同的模型，客户端收到的 `message_start.model` 仍是第一次那个。

今天路由对同一请求是确定的，所以不可达。**登记以免将来加入模型回退时无声出错。** 来源：同上 minor-12。

### 18. 一条提交信息缺字

`696a786` 的正文里 `A response that says it is incomplete without saying why gets , which is…` 缺了 `incomplete` 一词（`cat -A` 确认，非渲染问题）。历史已发布，不重写；`fef7d96` 的同一句是完整的，可作对照。登记以免后来者读到一句没有主语的话。

### 19. 截断 error 帧的 message 在 Anthropic 上游腿上字面是错的

`_deliver` 末尾那条帧写死了 `message="Responses stream ended before a successful terminal event"`（`src/app/pipeline/delivery/stream.py:386`，`code="incomplete_responses_stream"` 那处）。而 `_deliver` **对两条上游腿共用**——它收的是 `assembler`（`AnthropicAssembler` 或 `ResponsesAssembler`，即上游轴），而这条 message 是常量。所以一次走 Anthropic 上游腿的截断，客户端收到的是一句声称上游是 Responses 的话。

> **本条初稿的论证是错的，记在这里而不是抹掉**：初稿写「`framing` 由调用方给，两条腿共用同一段代码」。**用错了轴**——`framing.py` 的模块 docstring 开宗明义警告：framer 选的是**客户端**协议（`route.inbound_format`），`dialect_for` 才回答「哪个上游说了话」，「把这两者搞反正是这个类型存在的理由」。主产品路径恰恰是 Anthropic 客户端 + Responses 上游，两轴不同向。结论不变，但成立的理由是 `assembler` 那条轴，不是 framer。

2026-08-22 那次生产事故正是 Anthropic **上游**腿（判据：日志行上是 `think` 而非 `reason`，`REASONING_WORD` + `dialect_for` + `assembler_for` 三处共同决定；见 `../../tmp/260822-h2-streamreset-cancel-diagnosis.md` §1.2）。

**代价比初稿估的高，这一段也已更正**：

- `code` 不能动——被 2 处测试断言，并被 `../../delivery-keepalive/spec.md` 逐字复述（`../../tmp/260821-plan-g1-upstream-error-events.md` 的 G4 已查清）。
- `message` **不是「零消费」**。初稿这么写，错了。它有**两个产出点**：`src/app/delivery/responses_anthropic_stream.py:349`（legacy 链路）与 `stream.py:386`（活链路）。而且 `stream.py:382` 的注释把这件事写成**有意契约**：「Same code, same wire shape, **same message**, same gate on the message having started — a client that already learned to read one of these does not have to learn a second.」所以改 message 要么两处一起改、要么明确裁决让两条链路发散，不是顺手改一个字符串。

**为什么登记而不是顺手改**：它与第 5 条（已交付之后两条失败路径不一致）、G1 那份方案是同一片区域，且牵动一条跨链路的措辞契约，应当一并裁决。**证据等级：代码事实，确凿；是否值得改属措辞与契约取舍，需裁决。**

### 20. `_hand_over` 仍排在异常分类之后 —— `f0527e5` 修好的那扇门只修了一半

来源：`../../tmp/260822-review-session-closeout.md` 整改复核 N1（异源评审，配负样本对照）。

**形态**：客户端已收到 ≥1 个完整块、`terminal.seen` 为假、而失败是一个 `normalize_upstream_error` **叫不出名字**的异常时——

```python
reason = replay.eligible(torn) if replay is not None else None
if replay is None or reason is None:
    raise torn          # ← 裸抛。既不发 error 帧，也不咨询 _hand_over
```

客户端拿到的是 HTTP 200 + 半截 SSE + 连接撕断，**什么都读不出来**；而按人写文档，这一格本该合成 `turn_interrupted` 交给客户端续写。

**这正是 `1743a0b` / `f0527e5` 刚处理过的那扇门的另一半**：那次把「上游是否已完成」（`terminal.seen`）前移到了分类之前，理由是「完成与否是位置事实，不该由异常 taxonomy 决定」。**同一条理由原样适用于「客户端手里有没有内容」**——`committed_count` 也是位置事实。但 `_hand_over` 至今仍排在 `replay.eligible` 之后。

**这个异常不是假想的**：裸 `h2.ProtocolError` 会从 httpcore 的守卫缝隙里抛出，绕开所有包装边界（`../h2-goaway/archive-260820/260820-h2-goaway-poc.md` 端到端实测）。`tests/unit/pipeline/delivery/test_stream_delivery.py::test_a_finished_turn_survives_a_failure_nothing_recognises` 里那句 `assert eligible(torn) is None` 正是这条前提的显式断言，评审实跑 2 passed 并配了负样本对照。

**与第 5 条的关系**：第 5 条第 4 格描述的是同一件事在「续写没接手」这个分类下的位置；本条是它的代码落点。两条一并裁决。

**处置：登记，不动手。** 修法看似只是把 `_hand_over` 也前移，但它牵动「哪些失败算可继续」这条判据本身——分类器叫不出名字时默认可继续还是默认不可继续，是产品裁决而非实现选择。**证据等级：代码事实与实测前提均确凿；默认方向需用户裁决。**

### 21. 交付链路上还有 10 处「已知不处理却零痕迹」的丢弃点

来源：`../../tmp/260822-review-never-silent-failure-events.md` §2（异源评审，探针带正样本对照）。探针原件与边界说明在 `../../../exp/260822-silent-drop-probes/`。

用户 2026-08-22 裁决「已知不处理的路径绝不能静默，应该打日志」。主仓 `f21d7f4` 只兑现了其中三个上游失败事件那一格。**同一条链路上还有 10 处，全部经实测确认在任何日志级别都不产出记录**：

| # | 位置 | 触发条件 | 后果 |
|---|---|---|---|
| S1／S2 | `sse_source.py` `SseEvent.json()` | `data:` 不是合法 JSON，或是合法 JSON 但不是对象 | 整帧变成 `{}`，后续按事件名照常处理 |
| **S3** | `openai_responses.py` `_close` | `output_item.done` 找不到对应 draft，且 item 不是 `web_search_call` | **整个 output item 消失** |
| S4 | `openai_responses.py` `_accumulate` / `_accumulate_arguments` | delta 的 `output_index` 没有对应 draft | 该段文本／arguments 丢失 |
| S5 | `anthropic_messages.py` `_close` | `content_block_stop` 的 index 没有 draft | 整个 content block 消失 |
| S6 | `anthropic_messages.py` `_accumulate` | delta 的 index 没有 draft | 该段文本丢失 |
| S7 | 两个 `push` 结尾的裸 `return ()` | 任何不认识的事件名 | 事件整个丢弃 |
| S8 | `openai_responses.py` `_anthropic_usage` | usage 转换抛 `ResponseConversionError` | `Terminal.usage` 变 `{}`，与「从没设过」同值 |
| S9 | `assembling.py` `decode_json` | tool call arguments 不是合法 JSON | 保留为 `{"__raw": …}`；**内容没丢**，只是无痕 |
| S10 | `translation_driver/reasoning_carrier.py` | carrier 解不开（4 个 `except → return None`） | 推理载体降级 |

**S3 该排在最前，理由不是严重度排序而是它已经真的伤过人**：Copilot 在 `output_item.added` 与 `output_item.done` 上发**不同的 `item.id``，早先按 id 找 draft 于是 `_close` 永远找不到，**整条回复装配成零字节**——这就是 `openai_responses.py` 里 `_item_key` 那段注释记录的事故。当时它是静默的，所以 1243 条测试全绿而生产上零字节。改判据（`output_index` 优先）之后这条路不再被那个原因走到，但**丢弃分支本身还在，仍然无痕**。

对比之下，`f21d7f4` 修的那三个事件在 3000 万根帧里出现 **0 次**。**先修哪个是明摆着的。**

**不在本次范围，登记而非动手**，理由与第 4 条同源：S7 那一格（任意未识别事件）要不吵就得有一份「明知故忽略」的词表，而本项目规矩是上游行为靠录制不靠想象；其余各格的日志级别与措辞该一并定，而不是各修各的。**证据等级：位置与「零痕迹」均为一手实测（21 组反例 + 正样本对照），确凿；排期与级别需裁决。**

### 22. `internal` 同时盖着「上游协议故障」与「本仓 bug」两件相反的事 —— 待裁决要不要修

**「可不可达」这一半已经查实，不再是开放项。** 2026-08-23 端到端实测（`reports/260823-h2-protocolerror-category.md`，探针接生产的 `replay_reason` 与 `hand_back_block`，附 `httpx2.RemoteProtocolError → network` 的阴性对照）：

```
h2.exceptions.ProtocolError   -> {'category': 'internal', ...}
httpx2.DecodingError          -> {'category': 'internal', ...}
framing-bug TypeError         -> {'category': 'internal', ...}
httpx2.RemoteProtocolError    -> {'category': 'network',  ...}   ← 阴性对照
```

`README.md` 那句「结构上不可达」**是错的，且写下时就已经错了**：它的前提「带 error 走到合成前 `reason` 必非 `None`」被 `78be0d4`（2026-08-22 18:57）解耦掉，而那句话是次日 `a8862e6`（06:26）才写的。README 已更正。

### 仍待裁决的是：要不要修，以及怎么修

`internal` 今天盖着方向相反的两件事：

| 来源 | 是什么 | 报 `internal` 对不对 |
|---|---|---|
| 裸 `h2.exceptions.H2Error` 全族、`httpx2.DecodingError` | 上游/传输的真实故障 | **错** |
| framing 层 bug（`framer.block()` 抛的异常） | 本仓自己的 bug | 对 |

**错报那一半的代价不止是个标签。** 同一个缺口让它在 body 阶段**既不可重放、也被归错类**；而**同一个 GOAWAY 事件**若 httpcore 恰好包住了它（GOAWAY 与后续帧分开到达），就是 `network` 且可重放。决定命运的是操作系统那一次 `read()` 的分包——见 `../h2-goaway/archive-260820/260820-h2-goaway-poc.md` 第 34 条（源码确定 + 4/4 实测）。

**候选修法（报告 §4 有完整影响面）**：

- **(a) 把 `h2.exceptions.H2Error` 加进 `errors.py` 的 `_CONNECTION_ERRORS`。** 一行。body 阶段的 h2 与 headers 阶段的 h2 拉齐（headers 阶段今天由 openai SDK 的 `except Exception → APIConnectionError` 兜住，早就是 `network`）。**唯一不新增分类表的改法。** 实测只红 2 个测试点，且红的是 `test_a_finished_turn_survives_a_failure_nothing_recognises` 的**前提断言**——那条测试的 docstring 自己写明了「若 `normalize_upstream_error` 学会命名这一个，本用例守的洞就不存在了」。所以要连带给它换一个「生产叫不出名字」的载具，或把断言反过来写。**报告推荐这一条，本会话同意。**
- **(b) 只在 `replay_reason` 里特判。** 「影响面更小」是**错觉**：因为 `replay_reason` 同时喂着 `ReplaySupport.eligible` 与交接分类，它改的行为与 (a) 一样多，只是测试打不到（那条测试用的是自建的 stand-in `eligible`，不是生产接线）。而且会让 `replay_reason` 的文档串「`normalize_upstream_error` is the same mapping the driver's own retries are decided by」变成假话。**不推荐。**
- **(c) 只改 `hand_back_block` 的分类，不动可重放性。** 等于把分裂搬进同一个函数——那里第 250 行的注释正是在说「所以它读的是同一张表」。**不推荐。**

**为什么要用户裁决**：(a) 会让上游协议层故障开始花网络重试预算。本会话判断这**符合**用户亲笔的 `docs/.human-controlled/upstream-retry-and-continuation.md`（「这些情况下一般可以继续：网络中断」），是把代码拉回既有裁决而非新立规矩；但它确实改动重试行为，且要改写别人的一条回归守卫，所以不擅自动手。

**连带**：修法一旦定下，`README.md` 那一格与「给接收端的四点」要跟着改口径——若采纳 (a)，`internal` 就只剩本仓 bug 一种来源，接收端的含义随之收紧。

### 22 之二. 同一个失败，两条出口给两个相反的答案

同一个裸 h2 异常：

- `committed_count >= 1` → 走交接块 → `category: "internal"`（甩锅自己）
- `committed_count == 0` → 走 SSE 错误帧（`stream.py:385`，`ours=False` 那一侧）→ `type: "upstream_error"`（甩锅上游）

**方向正好相反，而分岔点只是缓冲策略放行了几个块。** framing bug 上同样成立且同样错：错误帧会把本仓的 bug 标成 `upstream_error`。

这正是 `hand_over.py` 开头那条注释想消灭的东西（「Two taxonomies for one failure is two answers」），只是它当时消灭的是「`classify_error` vs 重试路径」那一对，没看见这一对。证据等级：本次实测（两个变体各跑一次）。**与第 22 条一起裁决为宜**——单修一边只会把不一致换个方向。

### 22 之三. `transport.py` 的 h2 识别挂在没有活调用者的链上

`is_responses_headers_pending_transport_error`（`transport.py:32`，专门点名 `H2ProtocolError` 并附了机理注释）唯一被 `client.py:192` 调用；`client.py:177` 的 `send_responses_headers` 唯一被 `src/app/upstream/copilot.py:131` 调用；而 **`CopilotUpstream` 在 `src/` 与 `tests/` 里没有任何实例化点**。现役 provider 走的是 `github_copilot.py:167-172` 的 `send_responses`。

**没有造成行为缺口**——headers 阶段由 openai SDK 兜住了。但它是一份**读起来像在保护现役路径、实际不在现役路径上**的守卫，而且它是全仓唯一一处写着「h2 异常不被包装」这个知识的地方。第 22 条那个缺口能存在这么久，一部分原因就是这份守卫让知识看起来已经在场。

处置需裁决：随 legacy 链一起移进 `src/.archived/`，还是在现役链上重新接线。**不建议顺手删**——按 `never-delete-implemented-functionality-unsolicited`，孤儿模块可以留着。证据等级：代码直读。

### 23. ~~代理发 `max_tokens`，插件按 `truncated` 配回复~~ —— 已修复（2026-08-23）

插件侧已把 `DEFAULT_REPLIES_BY_CATEGORY` 的键从 `truncated` 改成 `max_tokens`，并加了一段说明「词表由发出方决定，不是这边命名的」；同时新增 `reply_source` 字段（`by_category` / `default` / `loop`）写进 JSONL，**下次再对不上，记录里一眼看得见**——那正是这次三个月没被发现的原因：落回 `reply.default` 是静默的。

改动在 `~/.claude/my/ghc-api-proxy-helper/`，本会话核对时尚未提交。本条留作记录：**一个「有才生效」的查表，对不上时与「没配这一项」同形**，与第 16 条「日志行上的缺席读不出来」是同一族。

## 明确不做

- **发真实请求向上游补证。** 用户 2026-08-21 明确禁止：只查历史，历史没有就保持悬念。调查报告里那条「最低成本补证是发个超长 prompt 触发 400」的建议**不采纳**。
- **代理内续写。** 已裁决放弃，见 `archive-proxy-side-continuation/`。
- **MCP-driven 续写的次数上限。** 已裁决不设，理由在 `status.md`。
- **为非 anthropic-messages 客户端合成工具调用。** 用户接受当前只支持这一种；将来用上别的 harness 再补。这是范围边界，不是遗漏。

## 方法学警告（给后来查 history 的人）

`from_history.py` 的「只取变换图的根」判据，在 **2026-07-17 19:41 之前的 366 个 operation 上恒真失效**——那批完全没有 transform 记录，代理自造帧与上游帧无法区分。涉及那段时间窗的样本必须标注这个限制，否则会把代理改写过的帧当成上游事实。
