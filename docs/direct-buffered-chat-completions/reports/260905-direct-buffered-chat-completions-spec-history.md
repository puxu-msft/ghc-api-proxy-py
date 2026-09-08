# Direct buffered `/chat/completions` retry：规范与历史调查

日期：2026-09-05

调查性质：只读设计前置调查，不修改源码、测试、Spec 或 living docs。

源码快照：`f97d243f9431d836861ce5e9938605df56b37478`（隔离工作树 HEAD）。

dotdev 快照：本地 `dotdev` 为 `6bdcaba271ccf6fb31ad8be33e48a3cda43fb1df`，`origin/dotdev` 为 `862b13748cefe3e27f8a95c7885cb3a4405345bc`；本地分支比远端多两项合并收尾记录。主工作树 `.dev/docs/` 当前只展开了少数主题，本报告因此同时读取主工作树现有 living docs 与仓库规则指定的耐久源 `dotdev`。

CodeGraph 状态：当前 Python 仓库根虽然存在 `.codegraph/` 目录，但 `codegraph explore` 在主树与隔离工作树都明确报告“no .codegraph index exists”，未自行重建索引，后续按工具指示退回 `rg`、`fd`、`Read` 与 Git object 读取。前身 `/home/xp/src/copilot-api-js` 的 CodeGraph 可用，已优先用它追踪 `chatCompletionsBufferedRetry`、`runResponseBufferedSink` 与 Chat handler 调用链。

## 1. 结论摘要

### 1.1 这里的“direct buffered `/chat/completions`”应指什么

本问题应主要解释为：客户端向 direct `/chat/completions` 发出 `stream: true` 请求，当前 Python 代理因没有 Chat Completions 客户端 framer 而走 `one_shot_delivery`，把上游 SSE 整轮缓冲，结束后一次性交付。

它不等同于普通 `stream: false` JSON。后者也会被口语称作 buffered，但当前 GHC、Xingchen 与 CodeBuddy provider 都在 `DirectDriver.run()` 返回前取得完整 body；本次本地探针已证明 GHC/OpenAI SDK 的 non-stream body 中途截断会在 provider 调用内抛出并被共享 direct driver 重试，第一次截断、第二次成功得到 `attempts=2`。因此普通 non-stream Chat 的 transport/body retry 机制已经存在，主要缺口在 `stream: true` 的 whole-stream one-shot 路径。

### 1.2 核心判断

1. **用户已经裁定该路径在尚未向客户端交付完整单位时应无痕重试，证据强度足够直接行动。** 人控 `docs/.human-controlled/upstream-retry-and-continuation.md` 明写“如果还没交付过完整块，直接在代理端无痕重试。无痕重试不设冷却间隔”，并在“非流式请求”中说明非流式同样支持无痕重试。`docs/.human-controlled/client-side-block-delivery.md` 又说明非流式天然是一次性交付；Chat `stream:true` 的 whole-stream buffer 在提交前与此具有同一位置事实：客户端尚未见到任何完整语义单位。
2. **当前 streaming direct Chat 实现违反该合同。** `src/app/pipeline/delivery/stream.py:295-320` 的 `one_shot_delivery()` 明写“No replay and no keep-alive”，异常时会把当前 attempt 已缓冲的部分字节先 `yield` 给客户端再重抛。`src/app/server/routes/inference.py:745-806` 在 `framer is None` 分支直接调用它，且在 `_reopen`／`ReplaySupport` 建立之前提前返回；所以 transport tear、attempt deadline 或 idle timeout 不会无痕替换 attempt，而会把失败 attempt 的部分 SSE 暴露给客户端。
3. **排除 replay 的历史理由已经失效，而且原本就不是用户裁决。** 2026-08-22 的 `2769a641` 只把“先整轮缓冲、以后再做块边界”记为用户裁决；“No replay and no keep-alive: both answer questions only block delivery raises”是代理在同一提交中的推导。2026-09-04 的 `fcb6982` 已加入并生产接线 `ChatCompletionsAssembler`，能从 `choices[].delta` 推断 text/tool 单位，识别 `finish_reason`、`[DONE]` 和 in-band `error`。所以 living docs 里“本项目没有任何东西读它”“在能识别完整单位之前”的事实前提现在为假。
4. **必须先改权威 Spec，再实现。** 第一份应改的是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md`：它自称覆盖所有 `translation_required is False` 路由，§5 是透明 replay 合同，§2.6／修订记录 v14、v22 又把 Chat 排除建立在已经过期的“没有边界 reader”事实上。应先明确 Chat 的 terminal-only whole-stream commit frontier、透明 replay 资格与 continuation 仍然分离。随后同步 `dotdev:.dev/docs/error-envelope/spec.md` §8／§10.2，限定“最后一轮已到达字节 + 裸断”的例外只发生在 retry 不可用或耗尽之后；若要改变最终失败 carrier，则仍需用户重新裁决。`dotdev:.dev/docs/client-leg-formats/README.md` 与 `dotdev:.dev/docs/upstream/retry-and-continuation/status.md` 是现状文档，也应同一变更同步，但不能代替先改 Spec。
5. **推荐实现不是移植前身整套框架，而是把现有 `ReplaySupport` 接到 one-shot，并增加只观察、不改写原始 bytes 的 Chat terminal observer。** 复用现有 `_reopen`、共享 `RetryLedger`、原 payload/admission 快照、draining 门、统一 deadline 与 attempt 记录；最终成功 attempt 的 SSE 仍逐字节一次交付。前身的 terminal-only `runResponseBufferedSink` 是行为和测试素材，不是本项目合同。

## 2. 权威层级与已有裁决

### 2.1 用户直接控制的文档

| 来源 | 用户已经决定的内容 | 对本问题的含义 | 证据权重 |
|---|---|---|---|
| `docs/.human-controlled/README.md:3-5` | 与人控文档冲突的既有内容需重新裁决；代理不能自行修改人控文档 | 代码、Spec 与代理历史推导不得覆盖下列条款 | **最高，直接权威** |
| `docs/.human-controlled/upstream-retry-and-continuation.md:13-25` | 网络中断、请求超时、429、499、5xx 一般可以继续；未交付完整块时代理无痕重试；无痕重试无冷却；draining 不无痕重试；429 走反应式限流 | direct Chat whole-stream buffer 在最终提交前没有交付完整单位，因此 retry 资格不依赖 Chat block framer | **最高，足以行动** |
| 同文件 `:29-41` | 已交付完整块后才进入 MCP-driven continuation；当前 carrier 只支持 Anthropic Messages 客户端 | transparent retry 与 continuation 必须分开；Chat 没有 continuation 不能推出 Chat 没有 replay | **最高，足以行动** |
| 同文件 `:63-65` | 非流式请求也支持无痕重试与合成续写 | 用户没有把“缓冲后一次提交”排除在 retry 之外 | **最高，足以行动** |
| `docs/.human-controlled/client-side-block-delivery.md:3-9` | 非流式天然一次性交付；流式按完整块交付；第一次 HTTP 200 的响应头先转发，后续 attempt 不能覆盖 | one-shot 可把整轮视为退化的单一交付单位；response headers 与 semantic commit 必须分槽 | **最高，足以行动** |
| 同文件 `:11-21` | 响应头提交后按 `sse_ping_interval` 发 ping；client deadline 到达后若已发 200 则以流内错误结束；客户端请求结束应取消上游 | 当前 one-shot“No keep-alive”不是用户裁决；不过 Chat error carrier 的既有推迟限制了 deadline 最终载体 | **最高，足以行动，但 carrier 受后述裁决约束** |
| `docs/.human-controlled/config.example.yaml:317-341` | `upstream_request_retry` 覆盖所有“再发一次上游请求”，包含 replay 与 continuation；所有策略共享 `max_total` | 不应另造 `streamReplay` 或 Chat 专属 retry budget | **最高，足以行动** |
| 同文件 `:370-395` | 强制块级／缓冲交付；`buffer_cap_bytes` 是缓冲路径的内存守卫 | one-shot 当前无 cap 是相邻实现缺口；加入 retry 时不能忽略常驻内存边界 | **最高，足以行动；cap 超限后的 Chat carrier 仍有开放边界** |
| `docs/.human-controlled/message-translation.md:7` | 直连路径尽可能原样转发，只在确需理解时解析对应部分 | terminal observer 可以读 Chat SSE 决定是否完整，但不得因此重写成功 attempt 的原始 bytes | **最高，足以行动** |

### 2.2 用户裁决的历史记录，但不是新的权威

`dotdev:.dev/docs/client-leg-formats/README.md:26-28` 记录用户 2026-08-22 裁定 Chat Completions 客户端腿“整段缓冲后原样一次性交付”，原因是当时没有 Chat reader，先缓冲、边界解析留待未来。

提交 `2769a6412a7d0fb70ab513813e4ef2720e1e267d` 是该裁决的源码落点：它修复此前 streaming direct Chat 返回 `200 + 0 bytes` 的缺陷，并新增 whole-stream one-shot。

该提交同时写入“No replay and no keep-alive”，但没有对应用户原话或人控文档锚点。它是当时的代理推导，而且其“两者只对 block delivery 有意义”论据不成立：透明 replay 只要求客户端未见语义内容，whole-stream buffer 比 block buffer 更容易满足这个条件；keepalive comment 也不需要 Chat block framer。

证据权重：关于“整轮缓冲、原样一次交付”是**用户裁决的可靠二手记录，足以行动**；关于“No replay/no keep-alive”是**代理推导，且已被上位人控合同反驳，不可作为约束**。

### 2.3 当前 living Spec 与状态文档

#### `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md`

- 文首定义域是任何 `route.translation_required is False` 的路由（§2.1 用户 2026-08-31“根因修复所有直连路径”）。
- §5.0 `:205-225` 定义透明 replay：首个原生事件提交前，retry taxonomy 认可的 tear／无终局 EOF／native failure 可在统一预算中 replay；提交后禁止 whole-attempt replay。
- §2.6 `:90-99` 把 direct Chat 描述为 `one_shot_delivery` 字节直送，称其缺少块级交付，并仅明确排除 §5.3 continuation。
- 修订记录 v14（`:779`）承认：定义域放宽后 §5／§8／§10 按字面也落在 Chat，而 `one_shot_delivery` docstring 逐字否掉三者；当时的处置意图是把哪些条款不适用写明，而不是留白。
- 修订记录 v22（`:770`）正确地把 **continuation** 限定为当前 Anthropic Messages 与 OpenAI Responses 两种可表达 synthetic call 的 block-aware 方言；但它把 Chat 的排除继续建立在“块级解析仍推迟”上，没有单独回答 transparent replay。

判断：**这份 Spec 当前已知不完整且部分事实过期，必须先改。** 错误不是“Chat 现在已经有原生 block delivery”——它仍没有 Chat 客户端 framer，成功路径仍应 raw one-shot；错误是用“没有 framer／continuation”推导“不适用 replay/cap/observation”，并继续声称没有任何 Chat 边界 reader。

#### `dotdev:.dev/docs/error-envelope/spec.md`

- §8 `:371-378` 与 §10.2 `:412-418` 明确记录用户 2026-08-23 裁决：Chat 流式腿的合法 error carrier 推迟；守卫或 tear 后客户端得到已到达上游字节 + 裸断，以缺少 `[DONE]` 判断截断。
- 这份裁决没有禁止在任何字节提交前透明 replay；它规定的是最终需要把失败交给客户端时用什么 carrier。
- 因此最小兼容实现应在 retry 可用时先隐藏失败 attempts；预算耗尽、draining、错误不可重试或 replacement 未建立时，最终 attempt 仍保留现有 partial+naked-close 行为。若改成“丢掉全部 partial 并合成 OpenAI error”，必须先由用户重新裁决 §10.2，不能借 retry 顺手改变。

判断：**这份 Spec 也要同步澄清，但不应先于 direct-passthrough Spec。** 前者管最终 error carrier，后者管 direct delivery 的 commit/replay 语义。若实现保持最终 carrier 不变，只需把 §8／§10.2 的触发范围收窄到“透明 replay 不发生或最终耗尽”。

#### 其它 living docs

- `dotdev:.dev/docs/client-leg-formats/README.md:26-28` 的成功交付合同仍正确，但“本项目没有任何东西读 Chat 边界”已在 `fcb6982` 后过期，应改为“direct client leg 没有 Chat framer，故 wire 仍 one-shot；已有 upstream assembler 可提供 observer 素材”。
- `dotdev:.dev/docs/upstream/retry-and-continuation/README.md` 把“未交付完整块 → 全协议透明 retry”记为现状目标，方向正确。
- `dotdev:.dev/docs/upstream/retry-and-continuation/status.md:291-299` 的 one-shot 结局日志缺口已于 2026-08-27 闭合：当前 `_StreamAccounting` 能把 tear 记为 fail、客户端中断记为 gone、正常排空记为 ok；这解决可观测结局，不等于解决 retry。
- `dotdev:.dev/docs/tui/deferred.md:7-15` 另有 direct buffered Chat reply summary 为空的缺口。它与 retry 不同，但 terminal observer 可以成为共同事实源；不能让 retry parser 与 observability reader各自推导一次。
- 顶层 `README.md` 只声明 `/chat/completions` 端点和直连／翻译能力，没有 retry 语义或相反约束。

## 3. 现状代码调用链

### 3.1 Streaming direct Chat

1. `src/app/server/routes/table.py:28-40` 注册 `/chat/completions` 及 OpenAI 前缀。
2. `src/app/pipeline/routing.py:295-345` 在模型支持 inbound endpoint 时得到 `translation_required=False`。
3. `src/app/pipeline/direct_driver/base.py:344-460` 的共享 `DirectDriver.run()` 负责 headers 前的异常／状态 retry；`_send()` `:462-489` 只等到 provider 返回 response。
4. `src/app/server/routes/inference.py:745-765` 进入 streaming 分支并调用 `framer_for()`。
5. `src/app/pipeline/delivery_policy.py:51-64,84-105` 对 Chat 客户端返回 `None`，因此 `inference.py:765-806` 提前走 `one_shot_delivery()` 并直接返回。`_reopen`、`ReplaySupport` 与 `stream_delivery` 都定义在其后 `:837-994`，该路径永远接不到它们。
6. `src/app/pipeline/delivery/stream.py:295-320` 把全部 chunks 放进无上限 `bytearray`；正常 EOF 时一次 `yield`；异常时若已有 bytes，同样先 `yield` 全部 partial，再重抛。
7. `tests/unit/pipeline/delivery/test_one_shot_delivery.py:77-107` 将该 partial-on-error 行为固定为测试；`tests/int/test_pipeline_app.py:1449-1471` 只覆盖完整流 byte-for-byte，没有 retry 用例。

结论：headers 前 retry 已有；headers 后 streaming body 的 tear 不 replay。因为异常前所有真实 SSE 都被扣住，当前正处于最强的无痕替换窗口，却主动把失败 attempt 变成客户端可见 partial。

### 3.2 普通 non-stream direct Chat

- GHC：`src/app/model_provider/ghc_client/client.py:68-128` 调 OpenAI SDK `.post(..., stream=False)`；生产构造在 `src/app/server/composition.py:463-474` 显式 `max_retries=0`，避免 SDK 自己另开一套预算。
- Xingchen：`src/app/model_provider/xingchen/client.py:77-139` 使用 `httpx2.AsyncClient.send(request, stream=stream)`，`stream=False` 时完整读取 body 后返回，并统一经过 `normalize_upstream_error()`。
- CodeBuddy：`src/app/model_provider/codebuddy_client/client.py:50-87` 即便 upstream 只支持 SSE，也在 provider 内 `aggregate_stream()` 后才返回 non-stream response；聚合异常发生在 `DirectDriver.run()` 调用栈内。
- `src/app/model_provider/upstream_errors.py:31-58,144-189` 将 SDK connection／timeout、`httpx2.TransportError` 和 H2 body-path 异常归入封闭 pipeline error；`src/app/pipeline/retry.py:36-58` 将无 status 的 `UpstreamError` 归为 `NETWORK`。

本次只读探针一：本地 H1 server 返回 `200 Content-Length: 100`，实际只发 11 bytes 后关闭；OpenAI SDK 3.8.0 在 `client.post(..., stream=False)` 返回前抛 `openai.APIConnectionError`，cause 为 `httpx2.RemoteProtocolError: peer closed connection without sending complete message body`，`normalize_upstream_error()` 得到 `UpstreamError`。

本次只读探针二：同一 server 首次截断、第二次返回完整 Chat JSON，经真实 `GhcApiClient.send_chat_completions()` 与真实 `OpenAIChatCompletionsDriver`，结果 `succeeded=True`、`attempts=2`、server requests=2、最终 body 为第二次完整响应。

证据权重：**强到足以把 ordinary non-stream 排除出当前缺口**。但仓库没有 direct `/chat/completions` 生产入口的同等回归测试；探针位于 `/tmp/probe_direct_buffered_chat_retry.py` 与 `/tmp/probe_direct_buffered_chat_driver_retry.py`，不是持久产品证据，不应替代后续正式测试。

## 4. 历史动机与时间线

| 日期／提交 | 发生了什么 | 现在如何解释 |
|---|---|---|
| 2026-08-18，历史报告 `dotdev:.dev/docs/pipeline-rewrite-parity/reports/260818-retry-gap.md` | 当时 Python 新链错误归一化未闭合，前身 history 已出现一次 `retry:buffered-retry` 成功与一次 `network-retry` 成功 | **历史动机，不能当现状。** 后续 `c4216f7` 等提交建立统一 SDK/httpx 错误归一化，当前 headers 前与 non-stream body retry 已可达 |
| 2026-08-22，`96eb2fa` | 给 block-aware `stream_delivery` 加 `ReplaySupport`，拆分“delivery 判断位置合法性”与“调用方判断错误 taxonomy” | **当前可复用核心** |
| 2026-08-22，`8f654b4` | 把 replay 接入真实入口，共享同一 request 的 `RetryLedger`，重开复用最终 payload/admission 与同一 client deadline | **当前可复用 wiring** |
| 2026-08-22，`2769a641` | 修复 direct Chat streaming 的 200 空 body；按用户裁决整轮缓冲、原样一次交付 | **成功路径合同仍有效**；该提交附带“No replay/no keep-alive”是未获用户锚定的推导 |
| 2026-08-23，error-envelope Spec §10.2 | 用户裁决推迟 Chat streaming error carrier | **最终失败兼容边界仍有效**；不阻止提交前 replay |
| 2026-08-31，direct-passthrough Spec v10／v14 | 用户把 native 直连原则扩到所有 direct legs；v14 发现 Chat 被 `one_shot_delivery` 排除于 §5／§8／§10，但仍接受“没有 reader”的旧前提 | **当前 Spec 修订的直接前史** |
| 2026-09-04，`fcb6982` | 加入 `ChatCompletionsAssembler` 并在 Chat upstream 的 translated streaming 路径接线；识别 `finish_reason`、`[DONE]`、in-band `error` 与 text/tool/reasoning 单位 | **使“没有任何东西读 Chat 边界”成为已知错误** |
| 2026-09-04，direct-passthrough Spec v22 | 正确区分 continuation applicability，只覆盖 Anthropic／Responses 两种已有 synthetic-call writer 的方言 | **不应反向拿来排除 Chat transparent replay** |
| 2026-09-05，`f97d243`／`3b48e54`／`6bdcaba` | 合并并对账 source 与 dotdev；TUI deferred 恢复 direct buffered Chat observation 缺口 | 没有出现新的用户裁决来撤销 transparent replay 或 whole-stream buffer |

## 5. 规范上应先补出的语义

以下是基于现有用户裁决与现有跨协议 retry 机制的规格化推导，不冒充用户原话；可由评审修正。

### 5.1 定义域

目标是 `translation_required is False`、inbound/target 均为 `openai-chat-completions`、客户端请求 `stream:true`、客户端腿仍采用 whole-stream one-shot 的路径。

普通 `stream:false` Chat 已由 provider eager-buffer + direct driver retry 覆盖；translated Chat upstream 已由 `ChatCompletionsAssembler` + 客户端 framer 走 block-aware `stream_delivery`，不属于这个 one-shot 缺口。

### 5.2 Commit frontier

- 第一次 HTTP 200 headers 已发送，但不构成 semantic commit，沿用人控 `client-side-block-delivery.md` 与现有 `decide_stream_ending()` 的区分。
- SSE ping/comment 不构成 semantic commit；否则一次保活就永久关闭 replay 窗口，与现有 block-aware 行为相反。
- whole-stream one-shot 的唯一 semantic commit 是最终选定 attempt 的完整原始 body 被 ASGI send 接受。终局识别只决定该 attempt 是否完整，不把帧提前送出。
- replacement 成功建立前必须保留旧 attempt buffer；replacement 建立后旧 attempt 的 bytes、terminal facts、usage、response observation 与内存计量全部丢弃，不能污染最终记录。

### 5.3 哪些 ending 可透明 replay

- retry taxonomy 已认定的上游 transport tear、idle timeout、attempt deadline。
- clean EOF 但没有 Chat terminal 事实。最低兼容判据应复用 Chat parser 的事实：出现非空 `choices[].finish_reason` 或 `[DONE]` 可证明上游有意结束；不能只做 `body.endswith(b"data: [DONE]\n\n")`，因为合法 SSE line ending、multi-line data、comments 与扩展字段会产生假阴／假阳。
- 仅当当前 request 的共享 `RetryLedger` 批准，且进程不在 draining，且 client deadline 尚未结束。

不得 replay：客户端取消、下游写失败、client deadline、`buffer_cap_bytes` 等 proxy protection、代理自己的 parser／accounting bug。异常归因应像 block-aware 路径一样用 `UpstreamSource` 正向标记，不能把 one-shot 外层任意异常都当成 upstream。

### 5.4 终局已见后的 transport tear

若 terminal 已见而随后 transport 报错，模型回合已完整；应提交已缓冲的原始 body，不再 replay，并把 post-terminal tear 作为旁路可观测事实。现有 block-aware `stream_delivery` 与前身 `isPostTerminalTeardown()` 都采取这一顺序。

需要 Spec 明确 terminal 的最小判据。当前 `ChatCompletionsAssembler` 把非空 `finish_reason` 与 `[DONE]` 任一视为 `terminal.seen`；前身以 `finish_reason` 为 `sawMessageStop`，随后自行补一个 `[DONE]`。本项目承诺原始 bytes，因此不能照抄“丢上游 `[DONE]` 再合成”的做法。建议 observer 只读，不改变 body；`finish_reason` 已见但 trailing usage／`[DONE]` 尚未到达时仍继续收集，只有后续 transport tear 才用“terminal 已见”决定是否接受已有 body。

### 5.5 Retry 耗尽与错误 carrier

最小兼容方案：所有被 replacement 成功取代的 attempt 完全不可见；当 retry 不可用、被 draining 拒绝、预算耗尽或 replacement 未建立时，只交付**最终 attempt** 已到达的 partial bytes，然后裸断，保持 error-envelope Spec §10.2 的现有用户裁决。绝不能把第一轮 partial 与最后一轮 partial 拼在一起。

若期望真正 all-or-nothing，即耗尽后也不交付 partial、改发 OpenAI-compatible error event，需要重新打开 `dotdev:.dev/docs/error-envelope/spec.md` §10.2 的用户裁决；本调查没有该授权。

### 5.6 In-band `{"error":...}`

这是未闭合的产品／规范问题。当前 `ChatCompletionsAssembler.chat_failure_from()` 能识别该形状；前身将它视作上游的 terminal decision，原样提交一次且不按“无 terminal”重试。direct-passthrough Spec 对 Responses native failure 有 code→taxonomy 表，但没有 Chat 对应表。

建议：Spec 必须先明确 Chat in-band error 是“保持原 carrier，不作为 truncation retry”，还是将已知瞬时 code 映射进现有 `RetryReason`。在没有用户／真实上游证据前，保守兼容方案是沿前身做法：识别为 terminal failure、原样交付、不误标为 clean EOF truncation；未知 code 不自行重试。此建议的证据权重是**可实施的保守倾向，不足以冒充用户裁决**。

### 5.7 预算、等待、headers 与资源

- 复用 `context.retry_ledger`，受 `upstream_request_retry.max_total` 与现有 per-reason 上限共同约束；不恢复已删除的 `streamReplay`，不新增 Chat 专属 retry 次数。
- 无痕 network retry 不额外 sleep；429 仍走反应式限流器。这是人控条款，不复制前身的 per-vendor retry cap。
- 继续保留第一次 HTTP 200 attempt 的客户端响应头；replacement headers 不覆盖。后续 attempt 的 `Retry-After` 无载体是用户已接受的限制。
- 每次失败 attempt 在重开前完成 response/source cleanup；client deadline 使用同一个绝对时点，不在 retry 时重置。
- attempts、replaced failures、最终 attempt observation 必须按现有 `_reopen` 语义更新；丢弃 attempt 的 side facts 不得进入最终 reply summary。

### 5.8 Keepalive 与 buffer cap

这两项是 retry 旁边已经存在的合同，不应因本次聚焦 retry 而继续隐身：

- 人控 `client-side-block-delivery.md` 要求 headers 提交后按 `sse_ping_interval` 发 ping；当前 one-shot“No keep-alive”与之冲突。retry 会延长等待，更不能忽略。可复用通用 SSE comment `PING_FRAME`；comment 不算 semantic commit。前身选择 Chat-shaped keepalive chunk，但那是其客户端兼容设计，本项目没有证据要求照抄。
- 人控配置把 `buffer_cap_bytes` 定义为“缓冲路径内存守卫”；当前 one-shot 的 `bytearray` 无上限。应在 direct-passthrough Spec 的 Chat 条款明确 cap 按当前持有 bytes 计。cap 超限本身不可 retry；其最终 Chat carrier 与 error-envelope §10.2 的关系需要写准，不能由实现猜。

## 6. 三类可行方案素材

### 方案 A：给 `one_shot_delivery` 接现有 `ReplaySupport`，增加只读 Chat terminal observer（推荐）

形状：保留 raw bytes byte-for-byte；one-shot 循环内按 attempt 建新 buffer 和 Chat observer，消费时同时累积原始 chunks 与观察完整 SSE events；异常／无 terminal EOF 时先按 `UpstreamSource` 归因与 `replay_reason` 分类，再用共享 ledger 和现有 `_reopen` 重开；replacement 成功后丢弃旧 attempt；成功或最终失败才执行一次现有输出语义。

可复用：`ReplaySupport`、`ledger_for()`、`replay_prepared()`、`_reopen` 中的 payload/admission snapshot、draining 门、attempt deadline/client deadline、attempt 可观测更新；`ChatCompletionsAssembler` 的 terminal/error 识别可以抽成 observer 或作为临时 side reader，但不能让它产出的 Anthropic `CompletedBlock` 改写 direct wire。

优点：最小改动，保持 2026-08-22 的 raw one-shot 用户裁决，直接兑现全协议 transparent retry；无需 Chat framer，也不触碰 continuation。

风险：若直接把完整 `ChatCompletionsAssembler` 当 observer，要确保 parser／tool-argument decode 的错误不会把合法未知直连事件变成代理错误；更稳妥的是抽出一个只负责 terminal/failure/usage 的 no-throw typed observer，并让 TUI deferred 的 whole-body／stream summary后续复用同一事实源。

证据权重：**推荐，置信高**。它直接复用本仓已经过端到端验证的 replay 接缝，新增的只有 one-shot attempt owner 与 Chat terminal observation。

### 方案 B：抽出通用 transactional buffered delivery，统一 one-shot 与 `stream_delivery` 的 pre-commit retry

形状：把“attempt-local buffer → terminal/failure observation → shared ledger → reopen/reset → final commit”提炼为协议中立驱动；block-aware 路径提供 block commit frontier，Chat one-shot 提供 terminal-only frontier。前身 `/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:1541+` 的 `runResponseBufferedSink` 是成熟样本，Chat handler 在 `src/routes/chat-completions/handler-v4.ts:577-596` 以 `retryCap`、`bufferCapBytes`、terminal/error predicates 接入；`tests/chat-completions/cc-buffered.it.test.ts:134-268` 覆盖一次截断后恢复、首轮成功、耗尽、in-band error 不误判 truncation。

优点：从模型上最干净，能让 Chat、Responses full policy 和未来 whole-response 模式共用同一个 attempt transaction；天然容纳 cap、keepalive 与 per-attempt facts。

风险：本仓已有 `stream_delivery` 的成熟状态机和 `_reopen` wiring，另起一套通用 driver 容易复制 finalization／cleanup／attribution；前身还带 hedge、candidate、anchor、continuation 等本项目不需要或合同不同的机制。应只借状态划分，不复制框架。

证据权重：**可行但改动较大，适合作为后续重构，不是本次首选**。

### 方案 C：为 direct Chat 建 raw passthrough adapter，让它进入现有 block-aware `stream_delivery`

形状：使用已有 Chat parser识别 text/tool/terminal，但 delivery unit 保留原始 SSE event groups；新增 Chat native passthrough framer只原样编码这些 groups，并按 terminal-only 或未来 block boundaries 提交。这样 replay、cap、keepalive、observer 与 finalization 直接沿用通用 `stream_delivery`。

优点：长期上最接近“一个引擎，每种方言一份词汇”，为未来 Chat block delivery 与 continuation 留入口。

风险：目前 Chat 只有推断边界，没有协议显式 `_start/_end`；多 choice、交错 tool calls、usage trailing frame、`[DONE]` 与未知扩展都扩大规则面。若 framer重建而不是原样携带，立即破坏 byte fidelity；若现在顺便启用按块交付，又越过了 2026-08-22“先整轮缓冲”的用户裁决。只有在 adapter 仍采取 terminal-only commit、raw events 不重写时才可作为 retry 实现；否则需新裁决。

证据权重：**技术可行、长期价值中等，当前不推荐作为最小修复**。

## 7. 前身与参考项目给出的模式

### 7.1 `/home/xp/src/copilot-api-js`

这是唯一找到与目标语义直接同构、且有完整 tests 的参考。

- `src/routes/chat-completions/buffered-config.ts:5-29`：Chat buffered retry 选择 shared buffered sink；buffered 模式强制 keepalive。
- `src/routes/chat-completions/handler-v4.ts:574-596`：Chat 是 shared `runResponseBufferedSink` 的第三个 consumer，传入 terminal-only／error、retry cap 与 buffer cap。
- `src/lib/pipeline/driver.ts:1541+`：attempt-local buffer；在整个 response 提交前允许 retry；replacement 用新 candidate state；终局才 commit。
- `tests/chat-completions/cc-buffered.it.test.ts:134-181`：第一次 clean EOF 无 `finish_reason`，第二次完整；客户端只见第二次；attempt 计数为 2。
- 同文件 `:199-230`：预算耗尽；前身选择丢掉全部 content、发 synthetic error。
- 同文件 `:241-268`：in-band error 原样一次交付、不按 truncation retry。

可复用的是状态机与测试场景，不是默认值或最终 carrier。前身当前把 `chat_completions.client_delivery` 默认打开、用 per-vendor cap、在耗尽后合成 error，并可能丢上游 `[DONE]` 后自己补一个；这些都与本项目的人控配置、raw-byte 合同或 error-envelope 推迟裁决不同，不能照搬。

### 7.2 其它列出的参考项目

对 `agent-maestro`、`CLIProxyAPIPlus` 做了只读关键词扫描，能找到 `/chat/completions` handler 与普通 retry-after／executor retry，但没有找到与“direct Chat SSE terminal-only whole-buffer + pre-commit replay”同等清晰的实现。`/home/xp/src/refs/sxwxs/ghc-api-py` 路径当前不存在。没有必要为了凑数把普通 HTTP retry 冒充本问题的可复用模式。

证据权重：**仅用于排除，不用于设计决定**。

## 8. 被排除的路线与原因

1. **维持现状，在 tear 时把第一轮 partial bytes 发给客户端。** 排除：与人控“未交付完整块 → 无痕重试”冲突；whole-stream buffer 本来给出了最强的 replay 窗口，先 `yield` 才人为关闭它。
2. **只依赖 provider／SDK retry。** 排除：它能覆盖 headers 前和 `stream:false` body read；`stream:true` 在 headers 后由 delivery 消费，`DirectDriver.run()` 已返回，异常回不到 provider retry loop。
3. **复制前身的 Chat 专属 enable flag、per-vendor retry cap 或恢复已删除的 `streamReplay`。** 排除：本项目人控配置明确所有 retry 共享 `max_total` 和 named strategy budgets；用户已裁掉独立 stream replay budget。前身默认不是本项目合同。
4. **把已有 `src/app/streaming/buffered_retry.py::collect_with_limit()` 直接接上就算完成。** 排除：该 helper 只有 byte cap，没有 terminal detection、retry taxonomy、shared ledger、reopen、attempt isolation、draining、deadline、response cleanup 或 observability；它是可复用小件，不是恢复机制。
5. **为了 retry 立即实现 Chat 原生逐块 framer／continuation。** 排除：retry 不需要向客户端表达 synthetic call；这会把已推迟的 block delivery 产品行为偷偷带入当前切片。可保留为方案 C 的未来方向。
6. **只检查 byte suffix `data: [DONE]`。** 排除：合法 SSE line ending、multi-line data、comments 与 trailing frames会让字符串后缀法产生假阴／假阳；仓库已为 SSE parser 的 CRLF、多行与 Unicode separator 问题付过成本。
7. **将 observer exception 一律当 upstream retry。** 排除：用户要求未知直连内容尽可能原样转发；本侧 parser bug 不应花 upstream retry 预算或被归因给 upstream。必须保留 `UpstreamSource` 的正向身份边界。
8. **在 retry 耗尽后直接改成 synthetic OpenAI error。** 当前排除：error-envelope Spec §10.2 保存了用户“推迟”裁决；若要改变，需先请用户重裁，不能以实现便利越过。

## 9. 开放问题

### 9.1 不阻塞 transparent retry 的问题

- Chat terminal 的规范最小判据是“任一非空 `finish_reason`”还是还要求 `[DONE]`？建议延续当前 `ChatCompletionsAssembler` 的“任一即可证明有意结束”，但必须在 direct-passthrough Spec 明文，不可只由实现决定。
- in-band `{"error":...}` 是否对已知 `server_error`／rate-limit code 进入现有 retry taxonomy？建议先保持原 carrier、不当 truncation；要放宽需补 Chat code 表与真实 upstream 证据。
- observer 是复用 `ChatCompletionsAssembler` 的 terminal 子集，还是抽 `ChatCompletionsObserver`？推荐抽共享 reader，使 translated assembler、direct one-shot retry 与 TUI reply summary共用一份 terminal/failure/usage 事实，但实现切片可以先只抽最小 terminal observation，不顺手完成整个 TUI deferred。

### 9.2 需要用户裁决才可改变的问题

- retry 耗尽／cap 超限后是否继续“最后一轮 partial + 裸断”，还是升级为 all-or-nothing + Chat error carrier。当前权威答案是前者；后者要重开 error-envelope Spec §10.2。
- 是否把 direct Chat 从 whole-stream one-shot 改成真正按推断 block 交付。2026-08-22 的用户裁决是推迟，现有 assembler 只消除了技术前提，不自动撤销产品决定。
- 是否把 continuation 扩展到 Chat 客户端。当前 human-controlled 文档仍接受只给 Anthropic Messages，后续 2026-09-01 扩展被 Spec 限定到 Anthropic／Responses 两种已有 writer 的方言；retry 不应偷偷回答这个问题。

## 10. 建议的实施与验证切片

### 10.1 先改文档

1. 先改 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md`：在 §2.5／§2.6 明确 Chat 已有 upstream reader、但 direct client 仍 terminal-only raw one-shot；在 §5 写明它在 whole-body commit 前使用同一 replay ledger；在 §7／§8／§10 写清 pings、cap 与 side facts；修订记录注明触发是 `fcb6982` 加 reader后旧前提失效，加上本次现状对账。
2. 同一语义变更同步 `dotdev:.dev/docs/error-envelope/spec.md` §8／§10.2：partial+naked-close 是 final fallback，不是跳过 transparent retry 的依据。若不改变 final carrier，不需要新用户裁决。
3. 同步 `dotdev:.dev/docs/client-leg-formats/README.md` 与 `dotdev:.dev/docs/upstream/retry-and-continuation/status.md`；前者纠正“无人读边界”，后者把 one-shot retry 的当前缺口和计划落点写准。

### 10.2 推荐代码切片

1. 抽出／前移 `_reopen` 所需的 request-stable wiring，让 block-aware 与 one-shot 共用同一个 `ReplaySupport` 和 `RetryLedger`。
2. 让 one-shot 的每个 attempt 拥有 raw byte buffer、正向 `UpstreamSource` marker 与 Chat terminal/failure observer；正常完整结束一次提交。
3. retryable pre-commit tear 或无 terminal EOF：replacement 成功后清空旧 buffer/facts并继续；不重置 client deadline，不重跑 mutable shaping。
4. retry 不可用／耗尽：仅 final attempt 按现有 partial+naked-close 行为交付；client cancel、client deadline、draining、cap、local bug按既有分类结束。
5. 接通 `sse_ping_interval`，并确保 ping 不设置 semantic commit；接 `buffer_cap_bytes` 前先在 Spec 写清 cap 超限的 Chat final carrier。
6. 保持最终成功 attempt bytes 原样，包括上游 `[DONE]`、event/id/retry 字段、换行与未知扩展；observer 不反写 wire。

### 10.3 最小高价值测试

- 真实 `/chat/completions` direct production 入口：attempt 1 发部分 SSE 后抛 `httpx2.RemoteProtocolError`，attempt 2 完整；断言 upstream 调用两次、客户端只见 attempt 2、attempt 1 的 marker 不出现、最终 bytes 与 attempt 2 逐字相同。
- clean EOF 无 terminal 与异常 tear 各一例，共用 `NETWORK` budget；反例是 terminal 已见后 tear，不 retry且仍交付完整 body。
- budget exhaustion：调用次数为 `1 + funded retries`，客户端只见 final attempt partial，保持当前 error-envelope 裁决；前面 attempts 不泄漏。
- local observer/accounting error、client cancellation、client deadline、draining 与 cap 各不 retry；至少挑一条 `UpstreamSource` 正／反归因控制。
- keepalive comment 在 retry 前后可出现但不关闭 replay；final semantic body仍只有一个 attempt。
- ordinary `stream:false` direct Chat 保留一条 production-entry H1 incomplete-body recovery 测试，防止 provider 以后改成 lazy body 后无声失去当前能力。

这些是针对真实新增失败面的方法，不建议建立新的 proof framework。

## 11. 最终证据权重

| 结论 | 权重 | 理由 |
|---|---|---|
| direct streaming Chat 在 full-buffer commit 前应透明 retry | **强到足以行动** | 人控 retry 合同 + whole-stream 一次交付裁决 + 当前零提交位置事实 |
| 当前 one-shot 没有 retry且会泄漏失败 attempt partial | **强到足以行动** | 当前源码调用链 + 单元测试明确断言 |
| ordinary non-stream Chat body truncation当前会 retry | **强到足以行动** | SDK源码 + 真实 GHC wrapper/direct driver 本地双 attempt 探针 |
| direct-passthrough Spec 必须先修 | **强到足以行动** | Spec 自称覆盖全部 direct legs；v14 已意识到 §5/§8/§10 射程；`fcb6982` 使排除前提过期 |
| 推荐复用 `ReplaySupport` 而非移植前身框架 | **高置信设计判断** | 本仓已有同责任边界与真实入口测试；前身证明 terminal-only 模式可行，但其预算／carrier／默认值合同不同 |
| in-band Chat error 不 retry | **保守倾向，需更多证据或 Spec 定案** | 前身采用该行为；本仓 human taxonomy 未给 Chat in-band code 表 |
| 其它参考项目没有更合适模式 | **仅用于排除** | 关键词调查未找到同构 terminal-only buffered retry；不支持“它们绝对没有”的全称 |
