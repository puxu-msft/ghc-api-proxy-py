# Direct buffered Chat Completions：决策来源

本文件只记录决策的来源与强度；行为正文分别归 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md)、[`../error-envelope/spec.md`](../error-envelope/spec.md) 与 [`../tui/spec.md`](../tui/spec.md) 所有。

## 用户直接裁决

| ID | 日期 | 裁决 | 来源强度 |
|---|---|---|---|
| D-1 | 2026-09-05 | 本次同时修复 direct `stream:true` whole-stream one-shot 的提交前 replay，以及上游以 Chat SSE 回答、客户端要求 `stream:false` 时的 attempt 内 buffered retry；不得只修其中一面 | 用户在设计问答中选择“两个故障面都修” |
| D-2 | 2026-09-05 | Chat SSE 流内 error 只有已知瞬时类型进入 retry；`server_error` 走 server-error 策略，明确 rate-limit 类型走现有限流处置，其余流内 error 不重试 | 用户在设计问答中选择“仅已知瞬时错误重试” |
| D-3 | 2026-09-05 | 每个把 Chat SSE 缓冲成一个完整交付单位的 transaction 必须见 `[DONE]` 才算成功；非空 `finish_reason` 单独不足 | 用户在设计问答中选择“必须见 `[DONE]`” |
| D-4 | 2026-09-05 | 采用通用 transactional buffered-delivery 引擎，而不是两处局部修补或只共享 observer | 用户在设计问答中选择“采用通用引擎” |
| D-5 | 2026-09-05 | 本次同时接通 direct buffered Chat 的 TUI／durable provider response observation，不继续把它留在 deferred | 用户在架构确认时选择“把 TUI 一并接通” |
| D-6 | 2026-09-05 | Model provider 不执行 stream/non-stream 内容处理，不修改 model-protocol payload，不解析 Chat SSE，不聚合 Chat JSON；provider 可以向上层声明自己对每个 model endpoint 的能力，pipeline解释并执行这些能力 | 用户先选择“provider 只管 headers”，随后明确补充“model provider 自身不处理 stream non-stream，但可以告知上层它是否支持，辅助上层设计”，并最终确认 per-model endpoint capability 形态 |
| D-7 | 2026-09-06 | 暂不对真实 CodeBuddy upstream 运行 P6；在 pipeline 上层保守维持 streaming-only compatibility，但必须把它标为未实测假设 | 用户在 P6 授权问答中选择“暂不实测，保守上移” |
| D-8 | 2026-09-06 | 最终架构为 provider 声明 per-model endpoint capability、pipeline解释并执行；route/replay持有同一不可变 capability快照 | 用户在最终设计问答中选择“确认设计” |
| D-9 | 2026-09-06 | Streaming Chat SSE→non-stream JSON采用标准多choice聚合：保留upstream identity与全部choices，按index累计content／reasoning／tools／logprobs，最终usage取终局值；OpenAI SDK accumulator可作实现基础，但本项目Spec自己的字段表才是合同 | 用户在评审后选择“标准多 choice 聚合” |
| D-10 | 2026-09-06 | 第一个合法 `[DONE]` 后冻结语义state但继续收raw尾巴；post-terminal transport tear／idle timeout／attempt deadline不retry并提交已收body，cap在越界前截尾后提交，后续semantic event不再改变verdict | 用户在评审后选择“冻结语义、继续收raw尾巴” |
| D-11 | 2026-09-06 | 已见 `[DONE]` 后收尾阶段触发client deadline时，立即提交已含 `[DONE]` 的完整body并记录tail-drain被截，不把完整回复降成失败；client cancellation仍因没有读者而不写 | 用户在评审后选择“提交完整body并记tail截断” |

## 既有用户合同，本次沿用而未重裁

- `docs/.human-controlled/upstream-retry-and-continuation.md`明示：尚未交付完整单位时无痕重试；draining不重试；429进入反应式限流；所有再发上游请求共享同一预算。
- `docs/.human-controlled/client-side-block-delivery.md`明示：第一次HTTP 200 response headers先提交；随后按 `sse_ping_interval` 发送SSE ping；client deadline与取消有既定处置；non-stream request天然是whole-body一次性交付。
- `docs/.human-controlled/message-translation.md`明示：直连尽可能保留上游原生内容，只在确需理解的边界读取对应事实。
- `docs/.human-controlled/config.example.yaml`明示：`client_delivery.buffer_cap_bytes`约束缓冲路径；`upstream_request_retry`是统一预算来源。

以下是living Spec基于上述合同作出的推导，不冒充用户亲笔原句：SSE comment不构成semantic commit；direct streaming Chat的整轮raw body是terminal-only交付单位；`[DONE]`前的attempt-local bytes可以被transparent replay隐藏。对应行为权威是 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §5.4。

## 代理派生判断

以下不是用户原话，而是为实现上述裁决作出的设计判断；发生冲突时，上述用户裁决与 living Spec 优先。

| ID | 判断 | 依据与强度 |
|---|---|---|
| A-1 | `ChatEventReader`／`ChatAttemptState` 应是 retry、SSE→JSON aggregation 与 response observation 的同一协议事实源；delivery owner各自决定何时 retry | 用户选择通用引擎，加上“同一事实不得由两条路径各自推导”的项目既有原则；高置信 |
| A-2 | non-stream mode adaptation 必须位于 `OpenAIChatCompletionsDriver` 的 shared attempt loop 内、response headers返回后且 attempt success事件前；否则 body tear回不到同一 `RetryLedger` | 当前调用时序与异常边界唯一确定；强到足以行动 |
| A-3 | direct `stream:true` 的 post-header replay仍由 delivery owner执行；provider和pre-header driver不能拥有这段已越过 headers 的生命周期 | 当前 server/delivery调用链与 HTTP commit frontier唯一确定；强到足以行动 |
| A-4 | provider capability随 resolved model endpoint 的 immutable descriptor或等价 route snapshot携带，不能只用 provider-wide布尔值，也不能在 pipeline按 provider名称分支 | 用户允许 provider告知能力；同一 provider不同模型/account可能不同；高置信 |
| A-5 | retry耗尽、draining或不可重试时，direct streaming Chat继续使用现行“最终候选 partial bytes + 裸断”carrier；本次不顺手发明 Chat streaming error frame | `error-envelope/spec.md` §10.2 的既有用户裁决未被重开；强到足以行动 |
| A-6 | Console只显示最小 choice index并附 `choices=<n>`，durable schema保存全部 choices；这是 presentation trim，不丢上游事实 | 既有 TUI“展示层读聚合记录”与 richest-context 原则；高置信设计判断 |

## 未采用的方案

1. **只修 direct `stream:true` 或只修原 CodeBuddy `stream:false` 聚合。** 用户要求两个故障面都修。
2. **共享 observer、两处各写一套 buffering/retry loop。** 用户选择通用 transactional engine；两套 loop会复制 terminal、cap、cleanup和attempt isolation。
3. **两处局部扫描 `[DONE]`。** 会产生重复 SSE parser和漂移的 error taxonomy，且无法成为 TUI observation 的事实源。
4. **把 force-stream／aggregation留在 CodeBuddy provider。** 与 D-6 冲突；只在外层补 catch修得了一个异常，修不了职责边界。
5. **在 pipeline按 provider名称分支。** 只是把耦合换了目录；新增 provider仍需改 Chat executor。
6. **所有 Chat target一律强制 upstream streaming。** 会无依据改变 GitHub Copilot／Xingchen 的 payload、latency、headers、失败时点与 native JSON fidelity。
7. **直接假定 CodeBuddy支持 `stream:false` 并删除 mode adaptation。** P6 尚未运行；用户选择保守维持兼容。
8. **本次运行真实 P6。** 用户明确选择暂不实测；后续可用 `exp/260904-codebuddy-provider/probe.py` 的 P6修正 capability数据，不需要改 pipeline控制流。
9. **让 provider response通过私有 metadata把 observer送回 pipeline。** D-6 后无需这条旁路：内容 adapter在 pipeline内，attempt state可直接拥有最终 observation。
10. **把整个 block-aware `stream_delivery` 与 buffered transaction合成一套大状态机。** 本次只抽共享的 attempt collector／verdict／transaction原语；block-aware commit frontier与 continuation保持现有 owner，避免无关重构。
11. **继续把 direct buffered Chat TUI observation留在 deferred。** 用户明确要求本次接通。
