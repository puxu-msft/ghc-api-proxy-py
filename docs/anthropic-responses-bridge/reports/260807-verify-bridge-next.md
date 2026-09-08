# Anthropic Responses bridge-next 独立验收

## 判定

- **验收对象**：`/home/xp/src/ghc-api-proxy-py-integrate-next` 的 `integrate/260807-bridge-next@a23081c5d5f48143bf3015182d8f00e1f6297755`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`；冻结 Spec SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。候选由 `1e3233cf23c07088469e3aa336c2e6031ce1315b` 与 `a23081c5d5f48143bf3015182d8f00e1f6297755` 两个线性提交组成；所有验收运行前后均确认候选 worktree clean，运行时 `app` 解析到候选树 `src/app/__init__.py`。
- **总体判定**：**FAIL**。真实 ASGI non-stream route、Responses header 过滤、History 单 context／单 finalize、typed stream reject／零 upstream，以及纯 parser→delivery 的完整 block batch、source order、terminal gate 均通过；但三条 pre-attempt typed reject 路径没有产生冻结 Spec 要求的 `ERROR` 与 `FINALIZE` hook events，只观察到 `REQUEST_RECEIVED`。
- **完整 stream 状态**：**`UNVERIFIED`**。候选真实 `/v1/messages` 对 selected Responses＋`stream=true` 明确返回 typed `responses_stream_not_supported` 且零 upstream；这证明当前拒绝边界正确，不证明完整 stream 已接。Parser 与 delivery skeleton 的独立 smoke 也不能替代 route-level stream wiring、HTTP commit、retry、History、cancel、backpressure 或完整 Acceptance required gates。
- **生产代码改动**：无。候选与主树生产代码均只读。
- **唯一主树写入**：本报告 `docs/tmp/260807-verify-bridge-next.md`。独立 harness 与日志仅位于 `/tmp`，没有写入候选或主树。

## 从冻结 Spec 独立推导的验收矩阵

| 验收项 | 独立 oracle | 实际结果 | 判定 |
|---|---|---|---|
| Responses-only auto route | 真实 ASGI `/v1/messages` 只调用 Responses；返回 Anthropic JSON | Responses 1 次、Messages 0 次；Anthropic text／model／usage 正确 | PASS |
| 双支持默认 route | 无 override 时固定 Messages | Messages 1 次、Responses 0 次 | PASS |
| 双支持显式 Responses | override 选择 Responses，不能回落 Messages | Responses 1 次、Messages 0 次 | PASS |
| capability fail closed | unknown capability 与不支持 Responses 的显式 override 均为 typed 400、零 upstream | 分别得到 `capability_missing` 与 `override_unsupported`；两者均零 upstream | PASS |
| stream 当前边界 | selected Responses＋`stream=true` typed reject，零 upstream；不得误称 stream 已接 | 400 `responses_stream_not_supported`；Messages／Responses 均 0 次 | PASS，完整 stream 仍 `UNVERIFIED` |
| header 过滤 | 只保留 request id、`retry-after`、明确 rate-limit；过滤 auth、cookie、内部与 Responses-specific header | success 与 429 均只保留允许集合；重新生成 Anthropic `content-type`／`content-length` | PASS |
| single lifecycle／History | 每请求一个 context、一次 approval、一个连续 attempt 序列、History finalize 恰好一次 | success、typed reject 与 429 均为同一 started／finalized context；attempt 数分别符合是否真实调用 upstream | PASS，仅 History 轴 |
| hooks lifecycle | 冻结顺序必须保留 `REQUEST_RECEIVED`、`ERROR`、`FINALIZE` | 三条 pre-attempt typed reject 均只有 `REQUEST_RECEIVED` | **FAIL** |
| block full-batch | block 完成前零 batch；完成后一个连续闭合 envelope；首 block 同 batch 带 `message_start` | 第一 source 未闭合前，即使第二 source 已完成仍零 batch；闭合后每 block 各一完整 batch | PASS |
| source order | 按首次合法 source order，而非 `output_index` 或完成顺序 | `output_index=1` 先完成，仍在 `output_index=9` 对应的先见 source 之后提交 | PASS |
| terminal order | terminal 只能在全部 source 闭合并提交后出现；open source 时零 terminal／零 batch | 正常 terminal 为独立最后一批；open source 上 completed 被 `incomplete_lifecycle` 拒绝且零 batch | PASS |

## 实际运行与证据

### 真实 ASGI non-stream route matrix

独立 harness 自行构造 model catalog、upstream target、History、approval 与 observer，不导入候选自带测试 helper。固定候选 HEAD 后运行 `route` section，实际覆盖：Responses-only auto、双支持 auto、双支持显式 Responses、unknown capability、override capability mismatch、Responses stream typed reject、Responses upstream 429。

- 行为基线日志：`/tmp/bn-route-c4a7.log`，SHA-256 `363e078ab75a4c558317e1e4acbc8a6a244ca7301fc178807754c0f90142cda1`，退出码 0。
- 加入完整 hooks lifecycle oracle 后的日志：`/tmp/bn-route-hooks-full-f271.log`，SHA-256 `15fa9cb543fb831fb86d241237c9908b95f9eff083fe866f165df54177857e8f`，退出码 1。失败集合为 `unknown_capability`、`explicit_responses_without_capability`、`responses_stream_typed_reject`，三者实际 observer 序列均为 `['request_received']`。
- 对照路径：正常 upstream 429 的 observer 序列为 `REQUEST_RECEIVED → ERROR → FINALIZE`，因此 observer 与 harness 能观察到正确失败 lifecycle；缺失只发生在 attempt 前 reject 接缝，不是测试替身失真造成的假红。

### 纯 parser→delivery smoke

独立事件序列先打开 source A，再打开 source B；B 先完整结束，A 后结束。验收要求 B 完成时不越过仍打开的 A；A 结束后一次释放连续 source prefix；最后 terminal 独立提交。

- 日志：`/tmp/bn-delivery-c4a7.log`，SHA-256 `8183d09dede24c4cea31c50e6a12492ec6523b1d32d00e0b2694704b6a7b7816`，退出码 0。
- 结果：`DELIVERY_CASE=full_block_batches_source_order_terminal_after_blocks:PASS`；`DELIVERY_CASE=terminal_cannot_cross_open_source:PASS`。
- 第一 batch 事件顺序为 `message_start → content_block_start → content_block_delta → content_block_stop`；第二 batch 为独立闭合 block envelope；terminal batch 为 `message_delta → message_stop`，且位于两个 blocks 之后。

### 正控

1. **Header 正控**：仅在独立 Python 进程内把 `app.anthropic.client.normalize_responses_response_headers` 替换为直接返回全部 upstream headers。日志 `/tmp/bn-control-header-3d6a.log`，SHA-256 `764f0c93ba5bfc2c96cdd5895e1db7f806101d469003583fd874deb0b54af1c6`。验收按目标原因在 `x-internal-openai-secret` 泄漏处变红，变异进程退出码 1。
2. **Terminal 正控**：仅在独立 Python 进程内旁路 `DeliverySession._finish_from_terminal` 的 open-source gate。日志 `/tmp/bn-control-terminal-3d6a.log`，SHA-256 `e08391fac63d5708df8cdcbfaf4cd261ed4bdd5d5a56daac01999ef0eaa486db`。完整 block／order 正样本仍绿，open-source 样本随后按目标原因在 `terminal crossed an open source` 处变红，变异进程退出码 1。
3. 两个正控前后候选 HEAD 均保持 `a23081c5d5f48143bf3015182d8f00e1f6297755`，worktree tracked／untracked 状态均为空；没有把变异写入生产文件。

## 阻断缺陷

### BN-V1：pre-attempt typed reject 丢失 `ERROR` 与 `FINALIZE` hooks

- **违反的 Spec 条款**：`docs/agents/anthropic-responses-bridge/spec.md:412` 要求 `REQUEST_RECEIVED`、`PRE_SANITIZE`、`POST_SANITIZE`、每-attempt `PRE_SEND`、`RESPONSE`、`ERROR` 与 `FINALIZE` 的顺序和 `protocol="anthropic"` contract 保持；同文件 `:420-424` 要求一个 request id 对应一个 History entry并且 finalize 恰好一次。History 一次 finalize 不能替代 hook `FINALIZE` event。
- **失败测试位置**：独立 harness `/tmp/verify_bridge_next_8f31c2.py:478` 的 `assert lifecycle_failures == []`。
- **实证失败结果**：固定候选 HEAD 运行 route matrix 得到 `LIFECYCLE_FAILURES=[('unknown_capability', ['request_received']), ('explicit_responses_without_capability', ['request_received']), ('responses_stream_typed_reject', ['request_received'])]`，进程退出码 1。完整输出见 `/tmp/bn-route-hooks-full-f271.log`。
- **生产接缝证据**：`src/app/pipeline/executor.py:34-50` 的 `_fail_internal()` 只把 context 标为 failed并调用 History `finalized()`，没有发 observer `ERROR`／`FINALIZE`；route／capability preparation failure在 `:141-145` 调用该 helper，stream typed reject在 `:170-178` 调用同一 helper。相对地，进入 attempt 后的正常 upstream error路径会在 executor 后段显式发送 `ERROR` 与 `FINALIZE`，与独立 429 对照一致。
- **影响**：用户收到的 typed Anthropic error、零 upstream和History exactly-once仍正确，但 hooks／observability contract 不完整；不能宣称 single lifecycle 全轴符合 Spec。
- **修复路由建议**：根因接缝明确，建议主会话交回 implementer，在统一 pre-attempt failure finalizer 中按一次性语义发送 `ERROR` 与 `FINALIZE`，覆盖 preparation／route capability、approval reject／modified payload validation、stream unsupported及其他 attempt 前失败；补真实 ASGI observer regression，避免只修 stream 特例。修后应重新执行本报告 route matrix与现有完整 gate。

## 未验证范围

- 完整 Responses stream route wiring、首 block 前真实 HTTP success headers／body 零可见、post-commit SSE error、route-level parser→delivery 接线。
- Retry frontier、失败 attempt header／usage 隔离、post-commit partial failure与 no replay。
- HTTP SSE parser framing、upstream WS parity、真实 backpressure／quota、cancel／shutdown、sink write uncertainty。
- 完整 request／response semantic matrix、approval modification、tokenization、History 终态矩阵、live canary、capture corpus与 Acceptance 的其余 required gates。

上述范围均保持 **`UNVERIFIED`**，不得由本轮 non-stream route PASS、纯 parser→delivery smoke或候选自带全量测试外推为通过。
