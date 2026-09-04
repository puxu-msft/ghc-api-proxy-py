# 未闭合、待查、已查清未修、与明确不做

本文件收三类，**每一条必须属于其中之一**：

1. **需用户裁决** —— 有岔路，本项目不自行选。
2. **已知未闭合** —— 还没查清，或查清了但修法本身是开放问题。
3. **已查清未修（无岔路）** —— 事实清楚、修法唯一，只是没排期。**每条必须写明为什么没做。**

**查清并落地的内容不留在这里**，按它回答的问题移出：裁决进 `decisions.md`，支撑性实测证据进 `README.md` 的证据表，当下实现状态进 `status.md`。用户 2026-08-22 裁决：「已经查清的内容应该移出，归入常规文档的适当位置」。

> **编号是公共接口，永不回收，也不重新编号。** 清点实测：**6 个生产源文件 + 1 个集成测试 + 3 处活文档**按号引用本文件（`stream.py` 引 §12／§19／§20／8d，`openai_responses.py` 与 `responses.py` 引 §2，`inference.py` 与 `test_pipeline_app.py` 引 §5，`base.py` 引 8a）。重新编号**不会报错，只会静默指错人**。所以条目移出后原位留墓碑，空号（13、14）不补——用户 2026-08-22 第 2 条裁决：不必强求序号连续。清点全文见 `../../tmp/260822-deferred-md-inventory.md`。

## 已知未闭合

### 1. 上下文超限的 400 —— 已查清的部分已移出，只剩一条等录制

**已查清、已移出**（2026-08-22）：

- **两条腿的 400 形态结构性不同**，以及 `error.code` 在 Anthropic 腿可作判据、在 Responses 腿不可（与其他参数错误共用 `invalid_request_body`，只能匹配 message 文本）→ `README.md` 证据表已有该行，细节 48 例在 `reports/260821-context-limit-400-examples.md`。
- **`model_context_window_exceeded` 的两腿权重差异** → 同表另一行（并入了「未观测 ≠ 不可能」那句解读）。
- **本条原标题「主路径抽不出数字」已被用户质疑并撤回**，理由（那个数上游模型目录就公布着；其消费端在不被服务进程构建的 legacy 链路上）与教训（*继承一个缺口的描述时，先找它的消费端*）→ 记在 `../../tmp/260822-deferred-md-inventory.md` 与本条的历史版本里，不再占本文件篇幅。

**仍未查清**（低优先，**无消费端**）：账户类型维度（history 库无此字段）；`/chat/completions` 腿只有 `vscode-copilot-chat` 2025-12 的第三方录制（第三种形态：OpenAI 措辞 + `model_max_prompt_tokens_exceeded`、无 `type`）。本项目自己不落盘上游 body，`~/.local/share/ghc-api-proxy/rejected/` 不存在，所以这两项**只能等新的录制**——不是没排期，是没有可查的东西。

### 2. ~~reasoning item 被截断时没有任何信号~~ —— 已闭合，已移出（2026-08-22）

**裁决**「历史里没有信号就保持悬念，暂不特殊处理」→ `decisions.md` 第二节第 3 条（本条是它的重复副本，已删）。
**支撑事实**（reasoning item 的 `output_item.done` 没有 `status` 字段，与正常收尾的键集逐字相同，已做正样本对照）→ `README.md` 证据表。
**代价**（20 例样本里 6 例的半截 thinking 块会照常交付）随该裁决一并记在 `decisions.md`。

编号保留：`openai_responses.py` 与 `translation_driver/responses.py` 两处生产代码按「§2」引用本条。

### 3. ~~`model_context_window_exceeded` 在 Anthropic 腿仍是可能的~~ —— 已闭合，已移出（2026-08-22）

→ `README.md` 证据表的 `stop_reason` 那一行，「未观测 ≠ 不可能」这句解读已并入该行。本条是它的重复副本，已删。

### 4. ~~上游 SSE 中途的 `error` 帧：零观测~~ —— 已闭合，已移出（2026-08-27）

R 片 `f12f76d` 已让 Responses 与 Anthropic 两条腿承接上游流内失败事件；当前源码中的 failure-event reader 已复核。完整的点时记录与「形状来自二手证据」这一限制迁入 [`status.md`](status.md)「2026-08-27 从台账迁入的闭合记录」。编号保留：当前生产源码仍按第 4 条回指这段历史。

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

   **排空主动拒绝重开的格子已裁决并移出（2026-08-27）**：维持现状，`committed_count == 0` 时整批丢弃，不为交接开口。客户端一个字节都没收到时，这一轮在它看来从未开始，没有「已收到一半」的部分状态可协调；由客户端重发语义更干净。用户同时接受已计费 token 会丢失、`buffering_policy: full` 时可能重付整份回复费用的代价。完整理由与被否决选项见 [`decisions.md`](decisions.md) 第六节。
3. **有意裁决为不可继续的失败**——人写文档的前提是「如果业务可能可以继续」。上游拒绝、转换错误、prompt-limit 不在内；多数发生在 commit 前（还能用 HTTP 错误），但已交付一块之后的转换／assembler 错误落在这里。
4. **种类上本可继续、只是分类器叫不出名字的失败**——**这一格与第 3 格形似而神不同，初稿把两者混写成一格，是错的**。机制是：`_replay_reason` 返回 `None` 时 `_deliver` 直接 `raise torn`，`_hand_over` **根本不被咨询**。于是一个本该续写的网络类失败，只因 `normalize_upstream_error` 没有它的名字（裸 `h2.ProtocolError` 就是），走的却是「不可继续」那条路。**这不是裁决，是漏网。** 详见第 20 条。

**证据等级：够据此写实现范围**（依据是人写文档原文与 `_hand_over`／`_replay_reason` 的现有分支）；**是否现在就接这条兜底，需裁决**。

### 6. ~~流式与非流式对同一事实给出不同答案~~ —— 已闭合，已移出（2026-08-22）

**闭合方式与本条原来设想的不同，所以值得写一句**：不是给 `Terminal` 加一个承载 `incomplete_details.reason` 的字段，而是裁决**不加**——`stop_reason` 现在已原样携带该事实（C 组停止了把非 `max_output_tokens` 的 incomplete 改写成 `end_turn`），桥 spec 要的「保留原因事实」由它满足，再加一个无人读取的字段就是孤儿件。

→ 决定与理由在 `status.md` C 组第 3 项；代码里那个刻意的往返写在 `formats/openai_responses.py` 的 `_INCOMPLETE_REASONS` 注释旁。

### 7. 孤儿件与死配置项的处置

2026-08-27 当前源码仍保留 `RetryBudget`、`streaming/buffered_retry.py`、`streaming/delayed_commit.py` 与 `client_delivery.hedge`。用户 2026-08-21 裁决「只删代理内续写机制，其他未接线的功能不要动」，所以这些件不因生产调用面窄而删除；`hedge` 的排期另见 `delivery-keepalive/deferred.md` D-4。

`decide_stream_ending()` 已接线，但它的 `COMPLETE` 分支仍从唯一生产调用点不可达。待裁的是形状：要么让这个纯函数只裁「未完成流」（去掉 `terminal_seen` 参数与 `COMPLETE`），要么重塑参数使调用者能在异常分类之前问出完整 verdict。**不要**改成在 verdict switch 里处理 `COMPLETE`——那条路对裸 `h2.ProtocolError` 根本到不了。

原条目里已经删除的 `continuation.*`、`streamReplay.max_retries` 与 `max_tokens_as_retryable`，以及它们被局部推翻的时间线，已于 2026-08-27 迁入 [`decisions.md`](decisions.md) 第六节，不再冒充当前成员。清点报告曾称 `streamReplay.max_retries` 仍在；当前 `src/`、`tests/` 与人写文档的检索不支持该说法，因此本条按当前源码收窄。

### 8. 生命周期所有权：一处缺口与三条未接线的通道

来源：`reports/260822-lifecycle-ownership-audit.md`（异源审计，11 条发现，10 个实测探针）。裁断是**不需要全面重写**——上游侧的模型自洽且实测有效，客户端侧只有一个原语且被安在最早结束的所有者上，修法是加法。

**这几条登记在这里，而不是留在报告里，是有代价换来的**：其中两条（O5、流式作用域）2026-08-20 的评审报告就已写清，grep 确认**从未进入任何活文档**，因此两天后仍未被修。报告不能是唯一的真相来源。

| # | 事实 | 证据等级 | 处置 |
|---|---|---|---|
| 8a | **已闭合，已移出（2026-08-27）** | 当前 `direct_driver/base.py` 对 `asyncio.CancelledError` 直接 `raise`，完成记录迁入 `status.md` | 编号保留：生产源码仍按 8a 回指本台账 |
| 8b | 该时限只覆盖「进入 `handle_bounded` → 上游响应头」，**流式 body 完全在外**；也不是「从受理开始计」——body 读取、JSON 解析、准入排队都在外 | 实测（1 秒时限下 3 秒 body 完整交付） | 要修：把 `with_deadline_at` 的模式复用到客户端时限 |
| 8c | 流式 body 的兜底者只有 `upstream_request_deadline`（1200）是真的；`stream_idle` 与 `response_header` 默认 0（关）；另有一个**没人选过、没文档的 httpx `read=600`**。把 1200 设 0 就只剩那 600 | 实测（`read=600` 随每个请求到达 transport） | 登记。那个 600 秒是隐式契约，值得写进配置文档 |
| 8d | **上游撕裂 / idle 触发 / deadline 触发，三者对客户端逐字节相同**——同样的事件序列、无 error 帧、chunked body 不完整。只有代理日志能分辨。另一对：「EOF 什么都没有」与「成功但零内容块」都是 200 + 空 body + clean EOF，日志一个 `fail` 一个 `ok` | 实测 | `error_frame` 通道**存在但没接到终止路径上**。用户 2026-08-22 已裁决：客户端时限在 body 阶段触发时发 SSE error 帧 |
| 8e | 关机有**两条路径**：systemd 部署走裸 uvicorn（等 300 秒再 `task.cancel()`，级联有效），`ShutdownLadder` 完全不参与；独立路径的 drain **无上限**，其注释前提「请求自带时限」只在 `upstream_request_deadline > 0` 时成立 | 实测 + 代码事实 | 登记，归 `deployment-systemd` / `graceful-shutdown` 主题 |
| 8f | `schema.py:250` 称 `client_request_deadline` 是 systemd 停机超时的基准，实为 300+30，**全仓无此推导** | 代码事实 | 注释失实，顺手改 |
| 8g | 两处潜伏泄漏：`http.response.start` 自身抛异常时生成器从未迭代、上游泄漏（**本部署不可达**，uvicorn 三个实现的 send 断连后静默返回）；`base.py:150-175` 丢弃已拿到的响应从不 `aclose`（今天无订阅者注册 `attempt.succeeded`，潜伏） | 实测 + 代码事实 | 登记，不改——两条今天都不可达，改动面大于收益 |

**明确不做全面重写**，理由见报告第 6 题：上游侧「一个时刻两处施加 + 六层一致的关闭契约」已由实测支持（客户端断连时上游 `is_closed=True`，断连中途与首 chunk 前两种情形都验证过）。

### 9. ~~一次性交付路径的结局判定不接线~~ —— 已闭合，已移出（2026-08-27）

`_StreamAccounting.finish()` 已为无 assembler 的 one-shot 路径补上结局判断；完成记录、三格测试与变异证据迁入 [`status.md`](status.md)。编号保留。

### 10. 缺一个 schema → example 的反向检查

`tests/unit/config/test_config_schema.py` 只查「`config.example.yaml` 里的键 schema 认不认」，**不查反向**——schema 新增的键有没有写进 example。`client_delivery.auto_retry_tool_call_full_name` 正是这次从这个方向漏掉的。

补不补由用户裁决：它是一道守卫，而本项目对「把守卫接成阻断」有明确态度。

### 11. ~~客户端时限与「上游已完成」谁先答~~ —— 已闭合，已移出（2026-08-22）

两半都完成了，本条不再是待办：

- **裁决**（`client_request_deadline` 保护的是「这一轮总耗时」，故时限先答、`terminal.seen` 后答）→ `decisions.md` 第二之二节第 18 条。
- **实现与验证**（夹具改 `[:-2]`、新增 `test_the_client_deadline_outranks_an_upstream_that_just_finished`、裁决写进两处分支注释）→ 主仓 `08f3c29`，状态见 `status.md`。
- **为什么这个次序是载重的**，以及两轮受控变异的证据 → `reports/260822-review-complete-fix-opus.md` 问题 2 与 `reports/260822-review-mcp-contract-and-deadline-order.md` F12／F13。

编号保留：`decisions.md:64`、`status.md:29`、`../h2-goaway/deferred.md:30` 三处活文档按「第 11 条」引用本条。

### 12. ~~上游在终结事件之后 reset：完成行不再留痕~~ —— 已闭合，已移出（2026-08-27）

当前实现已有 `on_tear_after_terminal`、`_StreamAccounting.tore_after_terminal` 与 `RequestLine.tore_after_terminal` 的完整通路；完成行保留该事实。完整的归属更正、候选做法与当时的取舍迁入 [`status.md`](status.md)。编号保留：生产源码仍按 §12 回指。

### 15. `hand_over_stop_reasons` 在非流式的丢弃上不生效

配置项 `upstream_request_retry.hand_over_stop_reasons` 接到了三处中的两处：流式 assembler、以及两条路的**交接**判断。**没接到非流式的丢弃**——`from_openai_responses_response` 是通过翻译器注册表按格式调用的（`registry.py:120` 的 `reader(payload)`），穿一个配置进去要改所有格式的 reader 协议，而同伴正在那片工作。

**危害有界**：默认值两边一致；而且「不交接就不丢」这条不变量**在任何配置下都成立**——把 `content_filter` 加进配置时，非流式会**保留**半截块**并且**交接（内容不丢，客户端也能续），只是比流式多留一块。反过来的「交接就一定丢」不是不变量，本项目不需要它。

补法：改 reader 协议让它接受一个上下文，或把丢弃从翻译器挪到调用方。两条都比现在这个不一致贵，等它真的碍事再做。

### 16. 反方向（`/responses` 客户端 + Anthropic 上游）仍在抹平

→ **已移入「已查清未修（无岔路）」栏**（2026-08-22）。编号保留，正文见下方该栏。

### 17. 重开不重建 framer

→ **已移入「已查清未修（无岔路）」栏**（2026-08-22）。编号保留，正文见下方该栏。

### 18. 一条提交信息缺字 —— 已移入读史提示（2026-08-27）

这件事按定义不会执行，完整记录迁入 [`README.md`](README.md)「读史提示：不会执行的旧记录」。编号保留，不再把它列作未修工作。

### 19. ~~截断 error 帧的 message 在 Anthropic 上游腿上字面是错的~~ —— 已闭合，已移出（2026-08-27）

当前 `stream.py` 使用不点名上游方言的 `upstream stream ended before a terminal event`，并保留原 `code`。完整的轴线更正与消费面辨析迁入 [`status.md`](status.md)。编号保留：生产源码仍按 §19 回指。

### 20. `_hand_over` 排在异常分类之后 —— **交接那一半已闭合；「叫不出名字的失败该不该可重放」仍开着**

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

~~**处置：登记，不动手。**~~ 修法看似只是把 `_hand_over` 也前移，但它牵动「哪些失败算可继续」这条判据本身——分类器叫不出名字时默认可继续还是默认不可继续，是产品裁决而非实现选择。**证据等级：代码事实与实测前提均确凿；默认方向需用户裁决。**

**2026-08-24：本条一分为二。交接那一半闭合，重放那一半仍开着。以上原文全部保留为点时记录。**

**已闭合的一半——交接不再由异常 taxonomy 决定，分两次做完：**

1. **撕裂侧由 `78be0d4` 修掉，本条上方引用的那段代码在 HEAD 上已不成立。** 现在是 `if not ours: handed_over = _hand_over(...)`，无条件咨询。**此前本条的处置栏与代码脱节了两天**，是我在 2026-08-24 诊断 req=`75ccdf6f` 时才发现的。
2. **干净 EOF 侧是同一扇门从未被记过的第三半**（主仓 `a7a0e05`）。`78be0d4` 在给撕裂路径装上无条件咨询的**同一个提交**里新建了干净 EOF 收尾路径，而没有给它装——于是「被本侧 idle 守卫掐死」的客户端结局反而**优于**「上游干净关闭」，因为前者抛异常、后者不抛。req=`75ccdf6f` 撞上了它：客户端交付过一个完整块之后只拿到一句 `API Error`。已修：报 SSE error 之前先咨询 `_hand_over`；块边界那一格不受影响（它不报错），代理自我保护等「无法继续」各格也不咨询。权威是人写文档第 30 行，**不是新裁决**；`anthropic-responses-bridge/spec.md` 第 7 条已同步修订。诊断见 `reports/260824-silent-eof-after-thinking-diagnosis.md`。

**仍然开着的一半——「`normalize_upstream_error` 叫不出名字的失败该不该可重放」，这仍是产品裁决，没有人替它作答。** `78be0d4` 明确只解开了交接那道门，它自己的注释就写着「An unnamed failure is still not replayed……it stays in `deferred.md` §20」。本文件另有三处按此引用本条（第 49 行、第 115 行、第 299 行），生产代码 `stream.py` 也引。**证据：`httpx2.DecodingError` 探针实测 `normalize_upstream_error(...) is None` 且 `replay_reason(...) is None`。**

> **本条 2026-08-24 曾被我整体标成「已闭合」，是错的**，异源评审当日判为 major 并推翻。错误的形状是**把一条含两个独立问题的条目按其中一个的进展整体结案**——而另一个问题正被三处活引用当作未决在用。这与我同日在诊断报告里犯的错互为镜像：那次是把已裁定的报成待裁，这次是把未裁定的报成已决。

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

### 22. ~~`internal` 同时盖着「上游协议故障」与「本仓 bug」两件相反的事~~ —— 已闭合，已移出（2026-08-27）

用户裁决与 `0ca87b9` 的落地记录已迁入 [`decisions.md`](decisions.md) 第六节；未随它解决的「叫不出名字的失败是否可重放」仍由第 20 条单独跟踪。编号保留，不把含两个问题的条目按其中一半整体结案。

### 22 之二. ~~同一个失败，两条出口给两个相反的答案~~ —— 已闭合，已移出（2026-08-27）

完成记录迁入 [`status.md`](status.md)「2026-08-27 从台账迁入的闭合记录」。编号保留。

### 22 之三. ~~`transport.py` 的 h2 识别挂在没有活调用者的链上~~ —— 已闭合，已移出（2026-08-27）

归档经过与「守卫留在无调用者链上」的教训迁入 [`status.md`](status.md)「2026-08-27 从台账迁入的闭合记录」。编号保留。

### 22 之五. `copilot.py` 剩下的两个 header wrapper 是 production-zero

归档 `CopilotUpstream` 之后独立评审顺手核了同一文件的其余符号，结果与我归档时写下的不符（我写的是「两个 header builder 由活链路使用」，那是**未观测写成事实**，已更正）：

| 符号 | 实际 |
|---|---|
| `GitHubTokenSourceAdapter` | **活的**，`src/app/server/composition.py:57,312-329` 构造它 |
| `build_copilot_identity_headers` | `src/` 与 `tests/` 里**零调用者** |
| `build_copilot_headers` | `src/` 里零调用者，唯一调用者是 `tests/unit/upstream/test_upstream_client.py` |

活链路直接调下一层：`client.py` 用 `build_request_headers`，`composition.py` 用 `build_identity_headers`。**有测试在保它，不等于产品在用它**——这正是本项目已经付过一次代价的形状（第 1 条那个 `parse_prompt_limit_error`）。

**未处置，需裁决**：归档／删除，还是写出保留它们的外部契约。本次不擅自动手（`never-delete-implemented-functionality-unsolicited`），也不因为「顺手」就扩大上一次裁决的范围。

### 22 之六. ~~本侧的 `_counted_upstream` bug 仍被标成上游~~ —— 已闭合，已移出（2026-08-27）

`UpstreamSource` 的边界与生产接线已复核，完成记录迁入 [`status.md`](status.md)「2026-08-27 从台账迁入的闭合记录」。编号保留：生产源码仍按 §22之六 回指。

### 22 之七. h2 残留：归因仍在，**但不再是静默的**（2026-08-24 处置，主仓 `1a34042` + 后续；只剩一条产品裁决）

**已闭合的一半**：交接此前是唯一会把异常吞掉、且不留任何记录的结局——它不 re-raise，于是 `_StreamAccounting.failure` 永远是 `None`，完成行只说「turn handed back」而不说从什么手里接过来的。现在被吞掉的异常记在 `handed_over_error` 上，完成行照这条路径上其他每一种结局的做法把它引出来。变异验证：不记录它，集成测试在 `assert 'RemoteProtocolError' in ...` 变红，印出的正是旧那行。

**仍然存在的一半**：httpcore 在 body 路径上除了 `receive_data` 还调 `acknowledge_received_data`，那里抛出的裸 `H2Error` 是**依赖自己的记账不变量**被破坏，而它在 marker **之下**，所以仍被归为上游。这一格从外部看不进去——除非放弃族级映射，而那会把本项目已经付过代价的那个真实故障（GOAWAY 从缺口裸奔）重新打回 `internal` 且不可重放。

**取舍现在是明账，但覆盖面要说准**（评审 R4-M2 指出我上一版把只覆盖交接的改动写成了整类失败）：

| 这类失败落在哪个位置 | 此前 | 现在 |
|---|---|---|
| 已交付过块 → 交接 | 只说「turn handed back」 | 带异常的类型与消息 |
| 未交付过块 → 透明重放**成功** | 只有 `retries=N` | `retries=N after <异常>` |
| 未交付过块 → 重放耗尽/不合法 | 异常上抛，本来就有 | 不变 |
| **上游终止事件已见之后再撕裂** | `stream.py` 直接 `break`，无痕 | **已修**（2026-08-24）：交付层新增 `on_tear_after_terminal` 回调，`_StreamAccounting.tore_after_terminal` 承载，完成行加一条说明 |

最后一格是评审补上的反例，它证伪了我写过的「交接是唯一会吞掉异常的结局」。**2026-08-24 已连带修掉**，但第一版修错了一半，值得记下来：

我写的是「那条路径上回合是完整的、客户端什么也不欠，所以状态仍是 `ok`」，并把说明塞进 `trace.detail` 的一个 `elif` 分支。**「终结事件已见」不等于「客户端什么也不欠」**——`max_tokens` 恰恰就是终结事件已见而回合未完成，于是交接与撕裂同时成立，而 `if/elif` 让交接的 detail 把撕裂整个吃掉。复评走真实 app 入口实测：`status=retry`、`detail='turn handed back to the client to continue'`、`tear_persisted=False`——撕裂哪里都没留下。

现在它有自己的字段 `trace.tore_after_terminal`（→ `RequestLine.tore_after_terminal`，完成行上自成一段），**不决定状态**：`end_turn` 后撕裂仍是 `ok`，`max_tokens` 后撕裂仍是 `retry`。截断界限与另外两处上异常的地方共用。变异验证：去掉那次回调，集成测试变红；`max_tokens` + 撕裂的真实入口测试单独钉住共存。

**教训的形状**：把两个可以同时为真的事实写进一个互斥分支。判据是「这两件事有没有一条路径上同时成立」，不是「读起来像不像两选一」。

之所以是回调而不是本生成器上的一个字段：拿这个事实**做什么**属于持有请求账目的调用方，而交付层并不知道有这么一本账——`ReplaySupport` 与 `ContinuationSupport` 是同样的理由。

要不要为消除**误归因**放弃族级映射，仍是产品裁决——这是本条**唯一**还开着的部分。四格现在都留痕；「都不再是看不见的问题」这句在 `max_tokens` 共存那条路径上曾经是假的，见上。

### 22 之四. 一条状态断言在写下时就已经过期 —— 已移入教训文档（2026-08-27）

这不是待办，而是一族错误的形状。正文已并入 [`README.md`](README.md)「三条会绊到人的」一节，那里区分「写下时已经是假的」与「写下后才过期」；本处只留编号墓碑。

### 23. ~~代理发 `max_tokens`，插件按 `truncated` 配回复~~ —— 已修复（2026-08-23）

插件侧已把 `DEFAULT_REPLIES_BY_CATEGORY` 的键从 `truncated` 改成 `max_tokens`，并加了一段说明「词表由发出方决定，不是这边命名的」；同时新增 `reply_source` 字段（`by_category` / `default` / `loop`）写进 JSONL，**下次再对不上，记录里一眼看得见**——那正是这次三个月没被发现的原因：落回 `reply.default` 是静默的。

改动在 `~/.claude/my/ghc-api-proxy-helper/`，本会话核对时尚未提交。本条留作记录：**一个「有才生效」的查表，对不上时与「没配这一项」同形**，与第 16 条「日志行上的缺席读不出来」是同一族。

## 已查清未修（无岔路）

事实清楚、修法唯一、只是没排期。**每条都写了为什么没做**——没有那一句，这一栏就会退化成一个谁也不敢删的许愿池。编号沿用原编号，不重新编。

### 16. 反方向（`/responses` 客户端 + Anthropic 上游）仍在抹平

`fef7d96` 只修了一个方向。实测 `to_openai_responses_response`：

```
anthropic stop_reason='max_tokens'     -> responses status='incomplete'  incomplete_details=None
anthropic stop_reason='refusal'        -> responses status='completed'   incomplete_details=None
anthropic stop_reason='stop_sequence'  -> responses status='completed'   incomplete_details=None
```

`refusal` 被报成 `completed`——与 `fef7d96` 消灭的形态同构；`max_tokens` 虽报 `incomplete`，但 `incomplete_details` 从不生成，客户端读不到原因。

**为什么没做**：该路由是 served 的（`/responses` + `claude-model`），但**不在主产品路径上**（主路径是 Anthropic 客户端 + Responses 上游）。修法与 `fef7d96` 同构，无岔路。

来源：`reports/260822-review-unreviewed-span.md` minor-8。**点时观测**：上表是 `fef7d96` 之后的实测。

### 17. 重开不重建 framer

`_reopen` 刷新了 assembler、buffer、attempt 计数，但 `framer` 是循环外用**第一次**的 `context.id` / `context.resolved_model` 建的。若重开时路由解析到不同的模型，客户端收到的 `message_start.model` 仍是第一次那个。

**为什么没做**：今天路由对同一请求是确定的，所以**这条路不可达**。登记只为一件事——将来加入模型回退时，它会无声出错。

来源：`reports/260822-review-unreviewed-span.md` minor-12。

## 明确不做

→ **已移入 `decisions.md` 第五节**（2026-08-22）。「不做」是裁决，属于那里；本文件按宪章只收未闭合与待裁项。四条分别是：不发真实请求向上游补证、不做代理内续写、MCP-driven 续写不设次数上限、不为非 anthropic-messages 客户端合成工具调用。

## 方法学警告（给后来查 history 的人）

→ **已移入 `tests/int/recorded/from_history.py` 的模块 docstring**（2026-08-22，主仓 `f0459f2`）。

那份 docstring 自己写着「两条限制，都是载重的，**都编码在下面而不是留给读者的记忆**」，而这第三条（「只取变换图的根」在 2026-07-17 19:41 之前的 366 个 operation 上恒真失效）正被留在本文件里——**造夹具的人不会来这儿看**。判据的限制归判据所在的地方。
