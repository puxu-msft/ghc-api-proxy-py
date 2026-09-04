# 上游终止形态调查：GitHub Copilot Responses 一次响应可能怎么结束

调查日期：2026-08-21。调查者：subagent（只读调查，未修改任何生产代码）。
触发背景：用户裁决「下游 `stop_reason` 不得被改写成 `end_turn`，要原样透出」。本文回答该裁决落地前必须先知道的四个问题。

**与同伴报告的关系**：本文的调查与结论是**独立得出**的，写完主体后才发现 `.dev/docs/tmp/` 下已有几份同日的相邻工作。核对结果：
- `260821-probe-history-error-frames.md` —— 同样从 history 找上游 `error` 帧。**核心结论完全一致**（0 条上游 `error` 帧、0 条 `response.failed`、20 条真实 `response.incomplete`），数字互相独立复现。唯一分歧见 §1.1 的方法学警告框（那 2 条 `ROOT=True` 的 `error` 帧），根因已定位并量化。
- `260821-max-tokens-block-completeness.md` —— 同一批 20 条样本，回答的是「截断的 item 有没有 `output_item.done`」（有）。与本文互补，不冲突。
- `260821-plan-g1-upstream-error-events.md` / `260821-upstream-error-handling-survey.md` —— 本文未读，**可能与 §3.1、§6 有重叠或冲突，交主会话对账**。

## 证据等级约定

- `录制/实测` —— 来自 `tests/int/cassettes/`、现网 history 库、或本项目自己的请求日志，是真实发生过的 wire 事实。
- `代码事实` —— 本仓库或参考实现里读得到的代码，带 `文件:行号`。**参考实现的代码只说明它们相信上游会怎么做，不等于上游事实**，所以参考实现的代码事实一律降级标注为 `旁证`。
- `旁证` —— 参考实现的分类/处理逻辑，提示该去搜什么字面量。
- `推测` —— 显式标注，不作为结论。

---

## 0. 结论速览

| 问题 | 答案 | 最强证据等级 |
|---|---|---|
| 1. 上游终止形态全貌 | Responses 腿实测到**两种**：`response.completed`/`status:"completed"`（64 351 次）与 `response.incomplete`/`status:"incomplete"`（**20 次，全部 `incomplete_details.reason == "max_output_tokens"`，无第二个取值**）。`response.failed`、`response.cancelled`、上游 `error` 帧：**0 次**。Anthropic 腿实测到 `tool_use`/`end_turn`/`max_tokens`/`refusal` 四个 stop_reason | `录制/实测` |
| 2. 上下文超限的上游形态 | **Responses 腿没有对应物**——4 个库、3400 万帧里没有任何一条 `incomplete_details.reason` 是上下文相关的值，也没有 `model_context_window_exceeded`。它在 Responses 腿上是 **HTTP 400**（形态见 §2.2，`旁证`：body 的 `error.message` 匹配 `prompt token count of N exceeds the limit of M`；`error.code`/`error.type` 的字面量**未查清**）。Anthropic 腿有 `model_context_window_exceeded` 这个 stop_reason（官方客户端为它写了分支），但本地也**没录到过** | `录制/实测`（否证）+ `旁证`（正面形态） |
| 3. 本项目现状 | 流式链路把除 `max_output_tokens` 外的一切 incomplete 拍成 `end_turn`，**reason 不落在任何地方**；`response.failed` / `error` / `cancelled` 事件被 assembler 静默丢弃，最终以一条不含上游原因的 `incomplete_responses_stream` 错误帧收场。非流式链路会把 reason 记进 `conversion.losses`（只进日志）。两条路径对同一事实给出不同答案 | `代码事实` |
| 4. Claude Code 能否容忍未知 `stop_reason` | 能。CC 对 `stop_reason` 是一串 `if (x === "...")` 比较 + 一个 `string().nullable()` 的 schema，没有枚举校验；未知值走不到任何分支，不报错，只是没有专门 UI | `代码事实`（CC 2.1.226 打包源码） |

**对本次裁决最要紧的一条**：把 Responses 腿的 `incomplete_details.reason` 原样透出，**在已知的现网语料上等价于「把 `max_output_tokens` 透出去」**，因为那是唯一录到过的取值。真正会因为「原样透出」而改变行为的，是 `response.failed` / `error` 这两条**目前被完全吞掉**的路径——而它们恰恰一次都没录到，所以任何实现都必须按 `旁证` 写并标注证据等级。

---

## 1. 上游终止形态全貌

### 1.1 实测（`录制/实测`）

扫描现网 copilot-api-js 的 history 库中**变换图的根**（剔除客户端侧 rewrite 产生的副本，方法照搬 `tests/int/recorded/from_history.py:129 _upstream_frames`）。四个还带帧对象的库，合计 **69 586 + 36 322 + 22 836 + 5592 = 134 336 个 operation、约 3000 万根帧**：

| 库 | 有根帧的 op | 根帧数 | `response.completed` | `response.incomplete` | `response.failed` | `response.cancelled` | 根 `error` 帧 |
|---|---|---|---|---|---|---|---|
| `history-v3-260807.db` | 69 586 | 15 259 454 | 28 904 | **4** | 0 | 0 | 2（见下方警告，实为代理自造） |
| `history-v3-260809.db` | 36 322 | 10 370 254 | 30 322 | **16** | 0 | 0 | 0 |
| `history-v3.db` | 22 836 | 3 368 903 | 3 903 | 0 | 0 | 0 | 0 |
| `history-v3-260811.db` | 5 592 | 975 710 | 1 222 | 0 | 0 | 0 | 0 |
| **合计** | **134 336** | **29 974 321** | **64 351** | **20** | **0** | **0** | **0（真上游）** |

`response.completed` 的 `status` 恒为 `"completed"`；`response.incomplete` 的 `status` 恒为 `"incomplete"`。

**非空 `incomplete_details` 全部 20 条，reason 一律 `max_output_tokens`，没有第二个取值。** 一条完整样本（`history-v3-260809.db`，operation `req_1786048072650_19`，`gpt-5.6-sol`）：

```json
{"error": null, "id": "<opaque>", "status": "incomplete",
 "incomplete_details": {"reason": "max_output_tokens"},
 "usage": {"input_tokens": 917011, "input_tokens_details": {"cache_write_tokens": 6264, "cached_tokens": 910400},
           "output_tokens": 4555, "output_tokens_details": {"reasoning_tokens": 1203}, "total_tokens": 921566}}
```

注意 `response.error` 在 incomplete 上是 `null`——**`incomplete` 不带错误对象**。

**新发现：output item 自己也带 `status: "incomplete"`。** `response.output_item.done` 的 item `(type, status)` 统计里出现了 `("message","incomplete") × 11`、`("function_call","incomplete") × 4`。本项目的 assembler 完全不看 item 的 status（`src/app/pipeline/delivery/assembler.py:279-320 _close`），一个 `incomplete` 的 `function_call` 会被当作正常 tool_use 交付，其 `partial_json` 很可能是截断的 JSON。这条与本次裁决相邻但不同题，**记录在此，未展开**。

同一批库里还出现了一个本项目没见过的 item 类型：`tool_search_call`（`in_progress`/`completed` 各 2 次，在 `history-v3-260809.db`）。

**Anthropic 形上游**（Copilot 的 `/v1/messages` 直连腿）根帧 `message_delta.delta.stop_reason` 的全部取值与次数：

| 值 | 260807 | 260809 | v3 | 260811 | 合计 |
|---|---|---|---|---|---|
| `tool_use` | 65 833 | 32 847 | 21 056 | 5 191 | 124 927 |
| `end_turn` | 3 673 | 2 516 | 1 719 | 382 | 8 290 |
| `max_tokens` | 9 | 15 | 0 | 0 | **24** |
| `refusal` | 1 | 0 | 0 | 0 | **1** |

没有 `stop_sequence`、没有 `pause_turn`、**没有 `model_context_window_exceeded`**。

> ⚠️ **方法学警告，会影响别人复用这批结论，也影响 `from_history.py`**：`history-v3-260807.db` 有 2 个 `error` 帧被判为「根」，内容却是 `{"type":"error","error":{"type":"api_error","message":"Upstream timed out before sending response headers"}}`——copilot-api-js **自己合成注入**下游流的错误帧。追查原因后确定：**这两条所在的 operation 整条时间线里一个 `transform` 事件都没有**。也就是说，早期格式根本不记 transform 图，于是「不是任何 transform 的输出」这个判据在那段时间**恒真**，代理自造帧与上游帧完全无法区分。
>
> 已量化这个盲区：`history-v3-260807.db` 里有帧的 69 586 个 operation 中，**366 个没有任何 transform 记录，全部早于 2026-07-17 19:41**；该时刻之后（含其余三个库的全部 op）transform 图完整。所以：
> - **「是根」是「上游发的」的必要条件，不是充分条件**，尤其在 2026-07-17 19:41 之前的 operation 上完全失效。
> - `tests/int/recorded/from_history.py` 用的是同一个判据，从那段窗口派生 cassette 会静默带上代理自造帧。
> - 判别办法：看 `synthetic` 字段、看措辞是不是代理自己的口吻、以及**先确认该 operation 的时间线里存在 transform 事件**。
>
> 与同伴报告 `.dev/docs/tmp/260821-probe-history-error-frames.md` 的分歧就出在这里：那份说「25 个唯一 `error` 对象逐条反查确认 `ROOT=False`」，我这边有 2 条判为 `ROOT=True`。**两边对『没有上游 error 帧』这个结论完全一致**，分歧只在这 2 条的 root 标签，根因是上述早期无 transform 窗口。这条应当补进那份报告，或在两份之间留一条互指。

补充实测（本项目自己的 `~/.local/share/ghc-api-proxy/requests/requests-2026082{0,1}.jsonl`，快照于 2026-08-21 21:55，共 7201 条；**该文件正在被运行中的服务持续追加，数字会继续涨**）：下游实际发出的 `stop_reason` 只有 `end_turn`（1745）、`tool_use`（5260）与空串（196，对应 `terminal_seen:false` 195 条）。**`max_tokens` 出现 0 次**，即这两天的生产流量里连 `max_output_tokens` 这一条已实现的分支都没被击中过。同期 36 条 4xx **全部是本代理自己的入参拒绝**（`request body must carry a non-empty string model` × 26 等），没有一条来自上游。

> **陷阱记录**：先用「解压后 bytes 子串搜索」扫全部 frame 对象时，`incomplete_details` / `refusal` / `content_filter` / `response.incomplete` 都有几万次命中——**绝大多数是会话正文**（那几天正好在讨论这个话题，模型输出的文本里含这些词；`history-v3-260809.db` 里 `refusal` 子串命中 39 307 次，结构化后真正的 refusal 是 0）。必须按结构解析 JSON、读帧信封的 `type`/`event` 与 `response.incomplete_details` 字段。另一个坑：帧信封是 `{"data":"...","event":"...","type":"..."}`，`type` 在**末尾**，只搜前 400 字节会漏掉全部 `response.incomplete`。

### 1.2 参考实现枚举的形态（`旁证`）

官方 VS Code 客户端把 Copilot Responses 的**流终止事件**列成一张表：

`/home/xp/src/refs/vscode-copilot-chat/src/platform/networking/node/chatWebSocketManager.ts:146-152`

```
'response.completed': 'completed',
'response.failed':    'response_failed',
'response.incomplete':'response_incomplete',
'response.cancelled': 'response_cancelled',
'error':              'upstream_error',
```

同文件 `:126-142` 记了一条 Copilot 专有的形态差异，值得单独拿出来：

> CAPI WebSocket error shape. Unlike the OpenAI SDK's flat `ResponseErrorEvent` (`{ type: "error", code, message }`), CAPI wraps the error details in a nested `error` object: `{ type: "error", error: { code, message } }`.

即 **Copilot 的 `error` 帧是 `{"type":"error","error":{"code":...,"message":...}}`，比 OpenAI 公开文档的扁平形多一层**；且非可恢复错误还会附带 `copilot_quota_snapshots`。该文件描述的是 WebSocket 传输，SSE 是否同形**未查清**；但事件词表是同一套 CAPI 词表。这是目前关于「上游 `error` 帧长什么样」唯一的形状证据——本地一条录制都没有。

copilot-api-js 的两处终止事件集合与之一致（少 `response.cancelled`）：
- `/home/xp/src/copilot-api-js/src/routes/responses/candidate-response-session.ts:222`
- `/home/xp/src/copilot-api-js/src/lib/openai/upstream-ws-connection.ts:25`
  两处均为 `new Set(["response.completed", "response.failed", "response.incomplete", "error"])`。

ghc-api-py 甚至为「HTTP 200 之后立刻 `response.failed`、一个 token 都没产出」专门做了一个默认开启的重试开关（`/home/xp/src/refs/ghc-api-py/README.md:155-162`，`enable_responses_early_failure_retry`）。这是**别人见过 `response.failed` 的最强间接迹象**——虽然我们自己一条都没录到。

### 1.3 `incomplete_details.reason` 的取值

**实测部分（`录制/实测`）**：唯一录到过的值是 `max_output_tokens`（20/20）。

**参考实现另外认得、但本地零样本的值（`旁证`）**：

| 字面量 | 出处 | 映射到 Anthropic |
|---|---|---|
| `max_output_tokens` | `copilot-api-js/src/lib/translation/legacy-direct/responses-to-cc-request.ts:511`；`ghc-api-py/ghc_api/anthropic_responses.py:1923-1924` | `max_tokens` / CC `length` |
| `content_filter` | `copilot-api-js/src/lib/translation/legacy-direct/responses-to-cc.ts:106`、`responses-to-anthropic-stream.ts:164`；`ghc-api-py:1925-1926` | copilot-api-js → CC `content_filter`，到 Anthropic 降级成 `end_turn` 并打 N3 标记；ghc-api-py → `refusal` |
| `safety`、`policy` | `ghc-api-py/ghc_api/anthropic_responses.py:1925` | `refusal` |

ghc-api-py 对**未知** reason 的处理是 `raise AnthropicResponsesConversionError("Responses incomplete reason is not safely representable")`（`anthropic_responses.py:1927-1941`）——它选择整体失败而不是猜。

`safety` / `policy` 这两个值只在 ghc-api-py 里出现，OpenAI 公开文档没有，其他参考实现也没有；`推测`：可能是该项目作者的防御性扩写而非实测所得，**不要当作上游事实**。

### 1.4 refusal / 内容过滤

- **Responses 侧：一次都没录到。** `response.output[].content[].type == "refusal"` 这个 content part、以及 output item 上的 `refusal` 字段，在四个库全部约 3000 万根帧里出现 **0** 次；`incomplete_details.reason == "content_filter"` 同样 **0** 次。ghc-api-py 认 refusal part 这个形态（`anthropic_responses.py:1829-1831`，把它转成 text block）——`旁证`。
- **Anthropic 侧：录到 1 次。** `history-v3-260807.db` 的根帧里有一条 `message_delta.delta.stop_reason == "refusal"`。也就是说 Copilot 的 Anthropic 腿确实会发 `refusal`，只是极罕见（1 / 133 218 次 message_delta）。copilot-api-js 为它专门做了 `refusal-recovery` 合成错误帧（在同一个库里能看到那条自造帧：「上游模型本轮以「拒绝（refusal）」结束、未产出可用回复（仅思考块）」）——那是**它的**处置，不是上游形态。
- Chat Completions 侧：`finish_reason: "content_filter"` 是官方客户端认的（`vscode-copilot-chat/src/platform/networking/common/openai.ts:223`，`ContentFilter = 'content_filter'`）。本项目主产品路径不走 Chat Completions，列在这里只为说明「过滤」在另一个 dialect 有独立表达。
- HTTP 422 + `content_filter`：copilot-api-js 有专门的 422 分支（`src/lib/error/forward.ts:206-227`），说明它相信 Copilot 会用 **HTTP 422** 表达内容过滤（而不只是 `incomplete_details`）。`旁证`，无本地样本。

---

## 2. 上下文超限专项

### 2.1 结论

**Responses 腿：已否证 stop_reason 路径，正面形态仍未查清。**

- **否证部分（`录制/实测`，权重：足以据此行动）**：四个库、约 3000 万根帧、64 371 次 Responses 终止事件里，`incomplete_details.reason` 只有 `max_output_tokens` 一个取值，没有任何上下文相关的值；`response.failed` 与上游 `error` 帧 0 次。所以**「上下文超限会以某个 `incomplete_details.reason` 或某个 stop_reason 出现在 Responses 腿上」这个假设，在现有语料上不成立**。
- **正面部分（`旁证`，仍未查清）**：它走的是 HTTP 400，形态见 §2.2；`error.code` / `error.type` 的确切字面量**没有任何一份材料给出**。

**Anthropic 腿**：`model_context_window_exceeded` 作为 stop_reason 存在（官方客户端为它写了分支，见 §2.3），但本地 133 218 次 `message_delta` 里 **0 次**。

### 2.2 候选路径 A：HTTP 400 + 消息文本（最强旁证）

本项目自己就带着这两个正则（`代码事实`）：

`/home/xp/src/ghc-api-proxy-py/src/app/tokenization/limits.py:10-13`

```python
_LIMIT_PATTERNS = (
    re.compile(r"prompt token count of\s+(\d+)\s+exceeds the limit of\s+(\d+)", re.I),
    re.compile(r"prompt is too long:\s*(\d+)\s+tokens\s*>\s*(\d+)\s+maximum", re.I),
)
```

取的是 body 的 `error.message`（`limits.py:16-27`）。同一对正则在 copilot-api-js 里逐字对应（`/home/xp/src/copilot-api-js/packages/foundation/src/error/parsing.ts:6,14`），且只在 `error.status === 400` 时才尝试（`src/lib/error/forward.ts:379`）。

因此**关于上游形态，能说的只有**：上游用 HTTP **400**，body 是 `{"error":{"message": "<上面两条之一>"}}`。
**`error.code` / `error.type` 的字面量未查清** —— 两份实现都只匹配 `message` 文本，没有任何一处读上游的 `error.code`。copilot-api-js 里的 `code: "context_length_exceeded"` / `type: "invalid_request_error"`（`forward.ts:159-161`）是**它自己合成给下游**的 OpenAI 形封装，不是它从上游读到的。这一点很容易读反，务必注意。

第一条正则（`prompt token count of N exceeds the limit of M`）按措辞更像 Copilot 的 OpenAI 形（Responses / Chat Completions）腿，第二条更像 Anthropic 形腿——但这是**`推测`**，两份实现都没标注哪条对应哪个端点。

### 2.3 候选路径 B：Anthropic 形上游的 `stop_reason: "model_context_window_exceeded"`

官方 VS Code 客户端在处理 **Copilot 的 Anthropic Messages 腿**时，把它当 stop_reason 分支处理（`旁证`，但来自官方客户端，可信度较高）：

`/home/xp/src/refs/vscode-copilot-chat/src/platform/endpoint/node/messagesApi.ts:1006-1017`

```ts
switch (this.stopReason) {
    case 'refusal':                        finishReason = FinishedCompletionReason.ClientDone; break;
    case 'max_tokens':
    case 'model_context_window_exceeded':  finishReason = FinishedCompletionReason.Length;     break;
    default:                               finishReason = FinishedCompletionReason.Stop;       break;
}
```

copilot-api-js 的客户端行为审计文档对两路并存写得很直白（`旁证`）：

`/home/xp/src/copilot-api-js/docs/todo/cc-client-2.1.207-behavior-audit.md:297`
> `model_context_window_exceeded` 若 GHC 以 stop_reason 发则透传给 CC（298173 处理）；若 GHC 以 HTTP-400 发则本项目 reactive auto-truncate 接住——两路都覆盖。

同文档 `:292` 还记了一条对我们直接有用的观察：copilot-api-js **在直连 Anthropic 路径上对 stop_reason 是透传的**，全仓 grep `model_context_window_exceeded` 零命中——也就是说它从没在自己的代码里合成或改写过这个值。这与用户当前的裁决方向一致。

### 2.4 Responses 侧有没有对应物？

**没有。** 三条独立的证据指向同一结论：

- `录制/实测`：四个库、约 3000 万根帧里，非空 `incomplete_details` 共 20 条，reason **全部**是 `max_output_tokens`；没有 `model_context_window_exceeded`、`context_length_exceeded`、`context_window` 或任何近义值。
- `旁证`：任何一份参考实现的 Responses 侧代码里都没有出现过这些字面量；它们认的 reason 只有 `max_output_tokens` 与 `content_filter`（外加 ghc-api-py 自扩的 `safety`/`policy`）。
- `旁证`：`model_context_window_exceeded` 在参考实现里**只**出现在 Anthropic 形的 stop_reason 语境（`vscode-copilot-chat/src/platform/endpoint/node/messagesApi.ts:1011`）与 CC 客户端的消费端。

所以对第 2 题的直接回答：**Anthropic 侧的 `model_context_window_exceeded` 在 Responses 上游没有对应物**。Responses 腿上的上下文超限是 HTTP 400（§2.2）——一次 4xx，根本走不到 `stop_reason` 这条路上。

**这条结论的推论对「原样透出」很要紧**：把 `stop_reason` 改成原样透出，**不会**让 `model_context_window_exceeded` 出现在 Responses 上游腿的下游输出里，因为上游从不在这条腿上发它。它只可能出现在 Anthropic 形上游腿（若我们保留那条腿）。上下文超限在 Responses 腿上是一个 **4xx 问题，归错误映射管，不归 stop_reason 管**。

---

## 3. 本项目 live 链路现在拿这些做了什么

进程实际服务的是 `create_pipeline_app`（`src/app/cli.py:151,176` → `src/app/server/pipeline_app.py:682`）。以下均为 `代码事实`。

### 3.1 流式（主产品路径）

`src/app/pipeline/delivery/assembler.py`：

| 上游形态 | 代码位置 | 结果 | 丢失了什么 |
|---|---|---|---|
| `response.completed`（有 tool call） | `:340` | `stop_reason = "tool_use"` | — |
| `response.completed`（无 tool call） | `:340` | `stop_reason = "end_turn"` | — |
| `response.incomplete` + `reason == "max_output_tokens"` | `:330-338` | `stop_reason = "max_tokens"` | — |
| `response.incomplete` + **任何其他 reason** | `:330-338` | `stop_reason = "end_turn"` | **reason 字面量。** 它在 `:333` 被读进局部变量 `reason`，只参与一次 `== "max_output_tokens"` 比较，之后**不写入任何字段、不记 loss、不进日志、不进 `Terminal`**。`Terminal`（`:43-62`）根本没有承载它的字段 |
| `response.failed` | `assembler.py:218-236` | **静默丢弃**（`push` 落到 `:236 return ()`）；`_terminal.seen` 保持 `False` | 上游 `response.error.{code,message}` 全部丢失 |
| `error` 帧（含 CAPI 的 `{"type":"error","error":{...}}`） | 同上 | **静默丢弃** | 上游 `error.code` / `error.message` 全部丢失 |
| `response.cancelled` | 同上 | **静默丢弃** | 同上 |

`response.failed` / `error` / `cancelled` 之后的收场在 `src/app/pipeline/delivery/stream.py:279-288`：因为 `terminal.seen` 是 `False`，走的是「EOF 前没见到合法终止事件」那条 STR-04 分支，向下游发一条

```
error_type = "upstream_error"
message    = "Responses stream ended before a successful terminal event"
code       = "incomplete_responses_stream"
```

——即上游明明说了话（`response.failed` 带 `error.message`），下游收到的却是一句「流提前结束了」，**且这句话把「上游主动报错」和「连接被掐断」写成了同一种东西**。

`stream.py:289-292` 的 `terminal.stop_reason or "end_turn"` 是第二处合成，但它只在 `terminal.seen` 为真时才跑，注释里已经承认它是合成。

### 3.2 非流式

`src/app/pipeline/translation_driver/responses.py:114-130 _responses_stop_reason`：

```python
if status == "incomplete":
    ...
    if reason == "max_output_tokens":
        return MAX_TOKENS, None
    return END_TURN, f"incomplete response with reason {reason!r}"
```

与流式同样拍成 `end_turn`，**但**第二个返回值是一条 problem 说明，在 `:155-156` 被记进 `response.conversion`（`LossCode.ITEM_NOT_CARRIED`），最终经 `src/app/server/handler.py:425-426` 落到 `context.extras["response_conversion_losses"]`，进日志/请求行。

也就是说：**同一个事实，非流式留了一条侧信道，流式一条都没有。** 这本身就是两条交付路径对同一产品行为给出不同答案，属于本仓 CLAUDE.md 明确点过的那类问题。

`to_openai_responses_response`（`responses.py:177`）反向也有对称的信息损失：`"status": "incomplete" if stop_reason == MAX_TOKENS else "completed"`，任何非 `max_tokens` 的终止在往 Responses 形写回时都变成 `completed`。

### 3.3 HTTP 4xx（上下文超限真正会走的路）

- SDK 异常 → `src/app/model_provider/ghc_client/errors.py:80-110 normalize_upstream_error`：4xx 非 429 非可重试 → `UpstreamRejected(status_code, headers, body)`，**body 原文被带着走**。
- 渲染：`src/app/server/handler.py:367-370` 用上游自己的状态码回下游；`error_body()`（`:385` 起）把上游原文放在一个单独命名的字段里，不与我们的措辞混在一起。
- **没有任何按语义分类的动作**：`parse_prompt_limit_error`（`src/app/tokenization/limits.py:30`）只在 count_tokens 路径（`src/app/tokenization/service.py:64`）和**未挂载的** `src/app/hooks/builtin/token_calibration.py:9` 被调用。**generation 路径上没有人调它**——所以上下文超限的 400 在主链路上不会被识别为「上下文超限」，只会作为一个透传的 400 出去（对「原样透出」而言这未必是坏事，但它意味着 `prompt_limits` 注册表在主链路上永远学不到东西）。
- `src/app/observability/rejection_capture.py` 会把 4xx 的请求体落盘到 `~/.local/share/ghc-api-proxy/rejected/`。**当前该目录不存在**，即这台机器上从没发生过一次上游 4xx 拒绝——与 §1.1 的请求日志（36 条 400 全是本代理自己的入参拒绝）一致。

### 3.4 与已冻结 Spec 的偏差

`.dev/docs/anthropic-responses-bridge/spec.md:264-265` 写着：

> content filter、cancelled 与未知 incomplete reason 必须保留原因事实，不能仅映射成看似正常的 `end_turn` 后丢失 side-channel。
> Responses `failed` 与 terminal `error` 不是成功 message，必须进入统一 error mapping。

按 §3.1，**流式链路两条都没做到**：未知 incomplete reason 既拍成了 `end_turn` 又没留 side-channel；`response.failed` / `error` 没有进统一 error mapping，而是被丢弃后由 STR-04 兜底成一句通用的截断报错。这不是本次裁决新引入的问题，是本次裁决**顺带暴露**的既有偏差。

---

## 4. 下游取值域：Claude Code 能否容忍未知 `stop_reason`

**能，不会报错。** 证据来自 CC 打包源码 `/home/xp/.claude/refs/claude-code-2.1.226/app.pretty.js`（`代码事实`）。

1. **没有枚举校验。** CC 自己的结果 schema 里 `stop_reason` 是 `$().nullable()`（纯字符串、可空），不是 enum。两处出现，均在 SDK result 的 schema 定义中。
2. **消费方式是一串独立的相等比较，不是穷举 switch。** 全文 `stop_reason ===/==/!== "字面量"` 共 44 处，涉及的字面量只有：`refusal`(23)、`pause_turn`(6)、`end_turn`(6)、`max_tokens`(4)、`tool_use`(2)、`model_context_window_exceeded`(2)、`stop_sequence`(1)。
3. **`message_delta` 的处理段（`:324620-324645`）逐条 `if` 判断**：`refusal` 触发 fallback 逻辑、`max_tokens` 发 `tengu_max_tokens_reached` 提示、`model_context_window_exceeded` 发 `tengu_context_window_exceeded` 提示。一个不认识的字符串**一条 `if` 都不进**，直接 `break`，`stream_event` 照常向下游发。没有 `default:` 抛错，没有 assert。
4. 注意 `model_context_window_exceeded` **本来就不是标准 Anthropic stop_reason**，CC 却专门为它写了分支——这本身说明 CC 的设计前提就是「stop_reason 可能出现枚举外的值」。

顺带记一条容易读错的证据：`app.pretty.js:58930` 有一个完整枚举 `{CONTENT_FILTERED, END_TURN, GUARDRAIL_INTERVENED, MAX_TOKENS, MODEL_CONTEXT_WINDOW_EXCEEDED, STOP_SEQUENCE, TOOL_USE}`，看起来像「CC 认的取值域」——**它不是**。它在一大段 AWS SDK 常量表中间，是打包进来的 Bedrock `StopReason` 枚举，与 CC 消费 Anthropic 响应的代码路径无关。不要拿它当 CC 的校验清单。

**未查清的部分**：CC 之外的其他 Anthropic 客户端（`anthropic` Python/TS SDK 的严格模式、LiteLLM 等）是否会对未知 `stop_reason` 报错，本次未查。若「原样透出」的下游只限 Claude Code，这一条不构成风险。

---

## 5. 复现方法与仍需补齐的证据

### 5.1 本次用到的脚本

脚本与四个库的完整扫描输出已存到 `.dev/docs/tmp/260821-upstream-termination-evidence/`（`roots-*.txt` 是 §1.1 全部数字的原始出处）：

- `scan_objects.py <db> <out>` —— 解压全部 frame 对象做 bytes 子串搜索。**在本语料上没有分辨力**（会话正文污染），但它顺带产出的「帧信封 `type` 直方图」是可靠的，本次就是靠它先发现 260807/260809 里存在 `response.incomplete`，再用结构化扫描坐实的。
- `scan_roots.py <db> <out>` —— 结构化扫描：逐 operation 读 `v3_operations.manifest_gz` 拿 `objectHashes`，读 `v3_timeline_chunks` 还原时间线，按 `transform.outputs` 求出被派生的 frame handle 并剔除，只解析剩下的**根帧**；统计事件类型、`response.status`、非空 `incomplete_details`、`response.error`、`error` 帧、`message_delta.stop_reason`、output item `(type,status)`、refusal。逻辑与 `tests/int/recorded/from_history.py:129-151` 同源。**本文 §1.1 的全部数字来自它**，四个库全部跑完（最大的 260807 约 15 分钟）。
- `dump2.py <db>...` —— 把信封 `type` 属于 `{response.incomplete, response.failed, response.cancelled, error}` 的帧按结构去重后打印，只保留 `status`/`incomplete_details`/`error` 等结构字段，避开会话正文。
- `rootcheck.py <db>` —— 验证某组 hash 对应的 handle 在各自 operation 里是不是根。用它确认了 260809 的 16 条 `response.incomplete` **全部是根、分属 16 个不同 operation、0 条派生**。
- `notransform.py <db>...` —— 统计有多少 operation 的时间线里一个 `transform` 事件都没有（root 判据在这些 op 上失效）。产出了 §1.1 那条方法学警告的量化：260807 里 366 个，全部早于 2026-07-17 19:41；其余库 0 个。
- `scan_diag.py <db>...` —— 扫时间线里的 `diagnostic` / `dispatch-settled` / `terminal` 事件找错误字面量。**注意**：朴素字符串匹配会把 `sequence: 413` 之类的数字误判成 HTTP 状态码，本次的「413/422 命中」全是这种假阳性。
- `scan_evidence.py` —— 扫 `v3_transport_evidence`。**该表在所有库里都是空的**（旧库根本没有这张表），此路不通。
- `reasons.py` —— 想对**全部**帧（含派生副本）再做一次 reason/refusal 普查作为冗余交叉验证。**本次主动中止、无输出**：它的作用域比 `scan_roots.py` 更差（会把派生副本和会话正文一起算进去），而 `scan_roots.py` 已经在正确的作用域上给出了答案，跑完它只会得到一个更脏的同结论。脚本保留供他人判断，**不要拿它的数字当结论**。

用 `uv --project /home/xp/src/ghc-api-proxy-py run python` 跑（需要 `orjson` + `zstandard`）。**一律以 `file:<path>?immutable=1` 只读打开**，本次调查全程未写入任何 history 库。

### 5.2 要拿到还缺的证据，需要做什么

| 缺的事实 | 拿到它的办法 |
|---|---|
| 一条真实的 `response.incomplete` + **非** `max_output_tokens` reason | 录 cassette：构造一个会被内容过滤的请求。`PYTHONPATH=src:tests/int uv run python tests/int/recorded/record_cassette.py <scenario>`，需凭据、会真实调用上游。**注意**：`max_output_tokens` 这一条不必再录，现网语料里有 20 条，可以直接用 `tests/int/recorded/from_history.py` 从 `history-v3-260809.db` 派生（它有 16 条，`req_1786048072650_19` 等 16 个 operation） |
| 一条真实的 `response.failed` / CAPI `error` 帧的确切形状（尤其 SSE 下是否也是嵌套 `error` 对象、是否带 `copilot_quota_snapshots`） | 无法从现有语料派生——四个库 3000 万根帧里一条都没有。只能实录，或在本项目侧打开帧级留存后等它自然发生。ghc-api-py 为「HTTP 200 然后 `response.failed`」做了默认开启的重试开关，说明它在别人的流量里并不罕见 |
| 上下文超限 400 的 body 里 `error.code` / `error.type` 的确切字面量 | 发一个超长 prompt（会被上游 400 拒），让 `src/app/observability/rejection_capture.py` 把 body 落到 `~/.local/share/ghc-api-proxy/rejected/`。**这条不需要额外基建，现有代码已经会捕获**，只需要那次请求真的发生。是几条里成本最低的 |
| Anthropic 腿的 `model_context_window_exceeded` 实样 | 同上一条实验的 Anthropic 腿版本；若它返 400 而不是 stop_reason，这条也就同时被否证 |

### 5.3 各条结论的权重

- **「Responses 腿的 `incomplete_details.reason` 只有 `max_output_tokens`」**：样本 64 371 次终止事件、20 条非空 `incomplete_details`，覆盖 2026-07 下旬至 08-15 的现网流量。**权重：足以据此行动**——把它当作「当前上游在我们这套模型/参数组合下的实际行为」。**它不能证明** Copilot 永远不发 `content_filter`；这类事件依赖于请求内容，而我们的语料是同一个人的编程会话，样本在这个维度上是有偏的。
- **「`response.failed` / `response.cancelled` / 上游 `error` 帧 0 次」**：同样的样本量，但**权重更低**——参考实现为它们各自写了分支甚至重试开关，说明它们在别处发生过。合理解读是「在我们这条链路上罕见到 3000 万帧未遇」，不是「不存在」。任何针对这三种形态的实现，都只能按 §1.2 的旁证写，并在代码里标明证据等级。
- **「Anthropic 腿录到 1 次 `refusal`、24 次 `max_tokens`」**：单个样本的存在性结论是可靠的（有就是有），但**频率结论没有意义**（1/133 218）。它证明的是「这两个值会出现」，仅此而已。
- **「上下文超限走 HTTP 400」**：`旁证`，两份独立实现用同一对正则匹配同一段文本，且本项目已经把它抄进了 `tokenization/limits.py`。**权重：足以据此设计，不足以据此断言字面量**——尤其 `error.code`/`error.type` 完全没有来源。

---

## 6. 这些事实对「原样透出」意味着什么

以下是**观察，不是决定**，交主会话裁断。

1. **「原样透出 `incomplete_details.reason`」在现网语料上是个空操作。** 唯一录到过的 reason 就是 `max_output_tokens`，而它已经被映射成 `max_tokens` 了。裁决真正改变的是「万一出现别的 reason」时的行为——那是一条 0 样本的路径。
2. **真正在丢东西的是 `response.failed` / `error` / `response.cancelled`。** 它们连 `terminal.seen` 都不会置位，最终下游收到的是一句与「连接被掐断」同形的 `incomplete_responses_stream`。上游明确说了「我失败了，原因是 X」，下游听到的却是「流断了」。这三条同样是 0 样本，但 Spec §「Responses `failed` 与 terminal `error` 不是成功 message，必须进入统一 error mapping」已经把它们定为必须处理。
3. **`stop_reason` 的取值域不是瓶颈，Claude Code 不校验。** 所以「透出什么字符串」这件事在下游侧没有约束，约束只来自我们自己想不想让下游认得。
4. **有一条相邻的、本次顺带发现的问题**：output item 自己带的 `status: "incomplete"`（实测 15 次）被 assembler 完全忽略，其中 4 次发生在 `function_call` 上——那意味着一个可能截断的 `partial_json` 被当作正常 tool_use 交付。这与 stop_reason 无关，但同属「上游说了话我们没听」这一类。按 `no-silently-cut-but-defer`，记录在此，不擅自扩大本次调查范围。
5. **流式与非流式对同一事实给出不同答案**（非流式记 `conversion.losses`，流式什么都不记）。无论裁决怎么落地，这两条路径都应当同时改，否则「原样透出」只在一半路径上成立。
