# Anthropic Responses bridge-next merged-state 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-next` 的 `integrate/260807-bridge-next@a23081c5d5f48143bf3015182d8f00e1f6297755`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。提交链固定为 `1e3233cf23c07088469e3aa336c2e6031ce1315b`（route-happy）后接 `a23081c5d5f48143bf3015182d8f00e1f6297755`（block-delivery）。本轮评审最终合并态、两提交接缝与提交内容，不把 source R2 verdict 直接外推为 merged-state verdict。
- **总体 verdict**：**修复 major 后可进入。** route non-stream、header 过滤、single owner／History、Messages 回归、delivery parser API 与“delivery 尚未接入生产路径”边界均成立，但 selected Responses＋`stream=true` 的 typed 拒绝漏发冻结 hooks contract 要求的 `ERROR` 与 `FINALIZE`。当前不是 `0 major`，因此这两个提交**不可按现状逐片回放 `main`**。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **逐片回放结论**：当前不授权。修复 stream 拒绝的 hook 生命周期、补回归并取得 current HEAD 定向复评 `0 blocker／0 major` 后，才可按 `1e3233c…` route-happy → `a23081c…` block-delivery 的顺序逐片回放；block-delivery 本身未引入新的生产接线或合并态缺陷。

## 双视角覆盖证据

### 机械核对

- 每个 load-bearing shell 调用均在同一次调用内打印并校验目标物理 root、branch、完整 HEAD、父链与 clean worktree；失去本轮 nonce、被并发终端抢占或未闭合的调用全部作废，未用于 verdict。
- 完整读取最终态 `src/app/routes/anthropic.py`、`src/app/anthropic/client.py`、`src/app/pipeline/executor.py`、`src/app/anthropic/header_policy/__init__.py`、`src/app/openai/responses_stream_parser.py`、`src/app/delivery/anthropic_sse.py` 及两份新增 smoke，而非只看 diff。
- 两个集成提交分别与 source 最终 diff 做 stable patch-id 比较：route source `44808b7d…` 与 `1e3233c…` 相等；block-delivery source `e506bf87…` 与 `a23081c…` 相等。提交父链、subject 与 changed paths 均符合“route-happy 后接 block-delivery”的声明。
- 对照 source 证据：route R2 为 `0 blocker／0 major／0 minor`，独立 verification 为 `PASS`；block-delivery R2 为 `0 blocker／0 major／0 minor`。本轮把这些报告作为线索，并重新检查最终代码与真实路径。
- 生产引用扫描只在 `src/app/delivery/anthropic_sse.py` 与其 package export 中命中 `DeliverySession`／`AnthropicSseRenderer`；route、client、pipeline 和 transport 均无引用，因此 delivery 仍是纯 API 骨架，没有意外接线。
- Responses 成功与错误 adapter 都先用 Responses 专用 allowlist 归一化 header，再由 route 层应用现有 blacklist／whitelist／strict policy；Messages 路径不使用该 allowlist。
- 定向 merged-state pytest 通过；目标 import probe 指向该 worktree。全仓 pytest 通过，Ruff 通过，Pyright 无 diagnostics。全仓 pytest 与 Ruff 所在调用在 Pyright 阶段被其他会话抢占，故只采纳其已经完整打印的各自结果；Pyright 后续在独立闭合 nonce 中重跑通过。

### 第一人称执行

- 以真实 FastAPI／ASGI `/v1/messages` 路径执行 Responses-only non-stream：只发生一个 Responses exchange，Messages 零调用；同一 `RequestContext` 贯穿 approval、History 与 hooks，History started／finalized 各一次，attempt 连续且 response hooks 看到转换后的 Anthropic body。
- 以双能力 auto 执行：仍选择 Messages leg，既有 Messages body 与 header 保持，Responses allowlist 没有误伤原路径。
- 以 selected Responses＋`stream=true` 执行：在 upstream 调用和 delivery 接线前返回 typed `400 responses_stream_not_supported`，History 恰好 finalize 一次且 attempt 为空；但实际 observer 序列只有 `REQUEST_RECEIVED`。
- 用同一完整 observer 订阅做 A/B：stream typed 拒绝得到 `REQUEST_RECEIVED`；Responses upstream `429` 得到 `REQUEST_RECEIVED → ERROR → FINALIZE`。这排除了 observer 配置或 harness 不订阅 `ERROR` 的解释，确认新预执行拒绝旁路了 hooks error／finalize 生命周期。
- 以真实 `ResponsesStreamParser` 逐事件驱动 `DeliverySession.consume()`：多 part、较晚 item 先完成、零 block source、incomplete／failed／error terminal 与并发 writer 均保持 parser→delivery 合同；typed 与 manual API 不能混用。
- 从 route 进入生产路径时无法到达 delivery 模块，故当前 stream 行为是“明确拒绝并零 upstream／零 delivery”，不是半接线或 raw passthrough。

## 事实性发现

[major] `src/app/pipeline/executor.py:170-178` — selected Responses＋`stream=true` 的 typed 拒绝漏发 `ERROR` 与 `FINALIZE` hooks，违反冻结 hooks 生命周期合同 — Spec `docs/agents/anthropic-responses-bridge/spec.md:410-416` 要求 `REQUEST_RECEIVED`、每-attempt事件、`ERROR` 与 `FINALIZE` 的既有顺序和 Anthropic protocol contract 保持，且 hook failure／错误不得造成重复 finalize。当前拒绝分支只调用 `_fail_internal()`；该 helper只标记 context 失败并 finalize History，不调用 `client.hooks.observe()`。真实 ASGI A/B 探针确认 stream 拒绝的 observer 序列仅为 `REQUEST_RECEIVED`，而同一 harness 的 upstream `429` 正确产生 `REQUEST_RECEIVED → ERROR → FINALIZE`；两者 History 均 finalize 一次，且 stream 路径 upstream调用数为零。现有 `tests/smoke/test_anthropic_responses_route.py:399-425` 只断言 typed error、零 upstream、History 与 context，没有断言 hook序列，因此全绿未捕获该缺陷 — **修复建议**：把预执行 Responses stream拒绝纳入 pipeline 的统一失败终结路径，由 single owner按既有 contract发出一次 `ERROR` 和一次 `FINALIZE`，同时保持 History恰好一次、attempt为空、upstream零调用；在现有 ASGI smoke中让 observer订阅 `ERROR` 并精确断言 `REQUEST_RECEIVED → ERROR → FINALIZE`，再对 current successor HEAD定向复评。

## 已核实通过的组合接缝

- **route 当前明确拒绝 Responses stream**：`src/app/pipeline/executor.py:170-178` 在 attempt与网络前拒绝，`src/app/anthropic/client.py:215-225` 还有 adapter防御；typed error、零 upstream与零 delivery成立。缺陷仅是 hooks终结序列，不是拒绝失效。
- **delivery 未意外接线**：生产调用者为空；新增包只提供 parser facts→Anthropic SSE batch的纯 API与内存 sink。
- **single owner／History／non-stream**：Responses non-stream仍由原 Anthropic pipeline拥有 approval、hooks、attempt、History与终态；真实 ASGI路径只有一个 context与一个 upstream exchange。双能力 auto仍保持 Messages。
- **header 过滤**：Responses成功／错误两条 adapter路径使用同一专用 allowlist；internal、auth、framing、cookie与Responses-specific headers不会下发，request id、`retry-after`与明确 rate-limit headers可保留；现有 route policy还能继续收紧。
- **delivery parser API兼容**：`ResponsesSemanticEvent` 的 `SourceOpened`、`CompletedBlock`、`UnsupportedResponsesEvent` 与 `ResponsesTerminal` 均由 typed `consume()`处理；真实 parser驱动 smoke覆盖 item内多 part、跨 item连续前缀、零 block source和失败 terminal。
- **提交内容**：`1e3233c…`只承载 route、pipeline、header、配置、bootstrap及对应 smoke；`a23081c…`只新增 delivery package与 smoke。提交 subject与内容相符，没有把 delivery接线混入骨架提交。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/pipeline/executor.py:28-51,141-178` | 失败终结逻辑分散；`_fail_internal()`名称与职责不匹配，既处理 hook内部错误，也处理 typed client拒绝，但不统一发送 hooks `ERROR／FINALIZE` | **本轮必须修**。将失败状态、observer终结与History终结收敛到 single-owner helper，避免每个早退分支各自遗漏生命周期事件；保持现有不重复 finalize约束 |
| `src/app/anthropic/client.py:215-225` 与 `src/app/pipeline/executor.py:170-178` | stream unsupported判断重复 | **后续可重构，不单独阻塞**。pipeline前置判断负责零 attempt／完整生命周期，adapter判断作为防御边界可保留，但错误构造应共享常量／helper，避免 message与code漂移 |
| `src/app/delivery/anthropic_sse.py:516-624` | manual compatibility API与 typed parser API并存 | **当前保留**。mode机械禁止混用且生产尚未接线；未来接 driver时只暴露 typed path，避免调用者绕过 item lifecycle facts |

## 主观建议

无。当前 major 是冻结 contract 的可复现实质缺陷，不是风格偏好；其余通过项没有发现需要扩大本轮修复范围的主观问题。

## 验证摘要

- 两个 source→integration stable patch-id 均相等。
- merged-state 定向 pytest通过，覆盖 route、delivery、route policy、Anthropic preparation、HTTP route与Responses parser。
- 全仓 pytest通过；Ruff通过；独立重跑 Pyright无 diagnostics。
- 独立真实 ASGI A/B探针稳定复现 stream拒绝漏发 hooks `ERROR／FINALIZE`，并确认普通 upstream错误路径的完整 hook contract仍工作。
- 目标树检查前后保持 `integrate/260807-bridge-next@a23081c5d5f48143bf3015182d8f00e1f6297755` 且 clean。

## 结论

Merged-state 不是 `0 major`。`a23081c5d5f48143bf3015182d8f00e1f6297755` 当前为 **0 blocker／1 major／0 minor**；route 与 delivery 的主要组合边界均成立，但 route-happy 的 stream typed拒绝漏掉冻结 hooks终结合同。**当前两个提交不可按现状逐片回放 `main`。** 修复该 major、补 ASGI hook序列回归并对 successor HEAD取得 `0 blocker／0 major` 后，可重新裁定按 route-happy→block-delivery顺序逐片回放；本结论不外推为完整 Responses stream、transport、retry、quota、部署或产品 `PASS`。
