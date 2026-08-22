# 未闭合、待查、与明确不做

本文件只列**需要用户裁决**或**已知未闭合**的项。已经定下来的在 `status.md`。

## 已知未闭合

### 1. 上下文超限的 400：形态已查清，但两条腿不一样，且主路径抽不出数字

人写文档原本写的是 `SSE stop_reason = model_context_window_exceeded`。**该判据已被实测证伪**：Responses 腿的值空间里根本没有这个东西（`incomplete_details.reason` 20/20 全是 `max_output_tokens`），Anthropic 腿 13 万次请求零观测。

正面形态是 **HTTP 400**，**48 例一手录制**（`reports/260821-context-limit-400-examples.md`），**两条腿的表达是结构性不同的**：

| | Anthropic 腿（27 例，2026-07-18～08-08） | Responses 腿（21 例，2026-08-06～08-08） |
|---|---|---|
| `Content-Type` | `application/json` | **`text/plain; charset=utf-8`**，body 末尾带 `\n` |
| `error.code` | `model_max_prompt_tokens_exceeded` | `invalid_request_body` |
| `error.type` | `invalid_request_error` | **没有** |
| `request_id` | 顶层有，另有顶层 `type:"error"` | **没有** |
| message | `prompt is too long: 1051542 tokens > 1000000 maximum`（`>` 在线上是 `>`） | `Your input exceeds the context window of this model. Please adjust your input and try again.` |
| 靠 `error.code` 能否区分 | **能**——其余 400 连 `code` 字段都不带 | **不能**——`Invalid 'input[1].id'`、`Invalid 'max_output_tokens'` 用的是同一个 `invalid_request_body`。只能匹配 message 文本，建议匹配 `exceeds the context window` |

**两条新的未闭合，都在主产品路径上**：

1. **`parse_prompt_limit_error` 对主路径返回 `None`。** 把三条真实 body 喂给生产模块实测：Anthropic 腿 → `(1051542, 1000000)`，Responses 腿 → `None`。而主产品路径正是 Responses 腿。
2. **而且补正则也救不回来**——Responses 腿的 message **里没有任何数字**，所以 `PromptLimitRegistry` 结构上就喂不进去。要让 prompt-limit 观测在主路径上工作，需要的不是一条正则，是另一个数据来源。参考实现 `copilot-api-js` 自己把这种响应分类成 `bad_request` 而非 `token_limit`，等于它的解析器也自认没认出来。

**顺带证伪一条旧结论**：归档里同伴写过「没有任何一条当前两条正则漏掉的真实 token-limit body」——现在不成立。原因是那份的语料**全部早于 2026-07-18**，而当时没有把这个时间窗写下来。

**仍未查清**：账户类型维度（history 库无此字段）；`/chat/completions` 腿只有 `vscode-copilot-chat` 2025-12 的第三方录制（第三种形态：OpenAI 措辞 + `model_max_prompt_tokens_exceeded`、无 `type`）。本项目自己不落盘上游 body，`~/.local/share/ghc-api-proxy/rejected/` 不存在，所以这两项只能等新的录制。

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

### 5. 已交付之后的两条失败路径行为不一致

- 上游干净 EOF 但无终止事件 → 发 SSE `error`（`stream.py:279-288`）。
- 上游撕流 / idle / deadline / 缓冲超限 → **不发任何错误帧**，异常上抛截断连接，只进服务端日志（`pipeline_app.py:590-591`）。

人写文档要求这两种都走同一个裁决点，所以后者现在连「有机会合成工具调用」都做不到。归 D 组。

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

### 11. 客户端时限与「上游已完成」谁先答，尚未裁决；且三条 deadline 测试的夹具已分辨不出这两种情形

来源：`../../tmp/260822-review-complete-fix-opus.md` 问题 2（异源评审，8 个受控变异）。由 `c86712d` 引入的 `if assembler.terminal.seen: break` 带出。

该支被**刻意**放在 `ClientDeadlineError` 分支之后，理由写在代码注释里：「跑超时了」与「上游已完成」是两个问题，重排属于新的 deadline policy 裁决。**这个理由只说明本次不裁，不说明该问题不存在。**

- **有真实后果**：上游已发完 `message_delta` + `message_stop`，随后客户端时限到期 —— 当前发 `client_deadline_exceeded` error 帧，**丢掉一条已经攒齐的完整回复**。若次序对调，则交付该回复。哪个对，取决于「时限」保护的是「客户端还愿不愿意等」还是「这一轮总耗时」，人写文档 `client-side-block-delivery.md` 未区分。
- **实测（评审）**：把该支合并进 `if torn is None:` 那一支（即让 terminal 压过 deadline），三条 client-deadline 测试全部转红——所以当前次序是**载重的**，不是风格选择。
- **同时登记一条测试事实**：`test_the_client_deadline_is_the_one_ending_that_says_so` 与 `test_a_held_back_policy_still_hears_the_client_deadline` 的夹具都携带完整终结事件（`anthropic_stream(...)` 末尾自带 `message_delta` + `message_stop`），因此**它们已经无法区分「时限先到」与「上游已完成后时限才到」**。裁决次序时应一并把夹具按 `[:-2]` 模式改掉——与 `c86712d` 对另外两条测试所做的相同，理由见该提交。

**证据等级：足以据此登记，不足以据此选一边。** 需要用户裁决时限的语义。

### 12. 上游在终结事件之后 reset：完成行不再留痕（`c86712d` 引入）

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

### 11. `hand_over_stop_reasons` 在非流式的丢弃上不生效

配置项 `upstream_request_retry.hand_over_stop_reasons` 接到了三处中的两处：流式 assembler、以及两条路的**交接**判断。**没接到非流式的丢弃**——`from_openai_responses_response` 是通过翻译器注册表按格式调用的（`registry.py:120` 的 `reader(payload)`），穿一个配置进去要改所有格式的 reader 协议，而同伴正在那片工作。

**危害有界**：默认值两边一致；而且「不交接就不丢」这条不变量**在任何配置下都成立**——把 `content_filter` 加进配置时，非流式会**保留**半截块**并且**交接（内容不丢，客户端也能续），只是比流式多留一块。反过来的「交接就一定丢」不是不变量，本项目不需要它。

补法：改 reader 协议让它接受一个上下文，或把丢弃从翻译器挪到调用方。两条都比现在这个不一致贵，等它真的碍事再做。

## 明确不做

- **发真实请求向上游补证。** 用户 2026-08-21 明确禁止：只查历史，历史没有就保持悬念。调查报告里那条「最低成本补证是发个超长 prompt 触发 400」的建议**不采纳**。
- **代理内续写。** 已裁决放弃，见 `archive-proxy-side-continuation/`。
- **MCP-driven 续写的次数上限。** 已裁决不设，理由在 `status.md`。
- **为非 anthropic-messages 客户端合成工具调用。** 用户接受当前只支持这一种；将来用上别的 harness 再补。这是范围边界，不是遗漏。

## 方法学警告（给后来查 history 的人）

`from_history.py` 的「只取变换图的根」判据，在 **2026-07-17 19:41 之前的 366 个 operation 上恒真失效**——那批完全没有 transform 记录，代理自造帧与上游帧无法区分。涉及那段时间窗的样本必须标注这个限制，否则会把代理改写过的帧当成上游事实。
