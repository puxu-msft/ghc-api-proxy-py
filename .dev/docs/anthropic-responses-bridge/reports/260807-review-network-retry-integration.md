# Network retry integration 只读预审

## 评审结论

- **评审范围：** current main `910e4bcbe22f9477aa8d36e828f2d6a325498cd4`、network retry source `584e63ba3724a7b6999d2163266d3daf8e731221`，以及 `integrate/260807-network-retry` 在 main 同一 `HEAD` 上的当前 staged integration WIP。当前 integration index SHA-256 为 `6c7503bbfdedad360ac0bff0e0057fb7ff6731af9d6245f87d0ae1f90adc74f0`，unstaged diff 为空。
- **总体 verdict：修复 major 后可进入下一阶段。** 当前不是 0 major，不能按“0 major 可继续”放行。
- **Blocker：0。**
- **Major：1。**

### 双视角覆盖证据

- **机械核对：** 固定并核验三方 ref；对账 source delta 与 integration staged 路径；通读共享 `client`、`executor`、retry strategy、upstream target 与相关 tests；检查 capability 映射、`AnthropicAttemptResult`、conversion／usage／History facts、stream 状态与 Messages 分支；执行 staged／unstaged `diff --check`；用 OpenAI SDK `2.21.0` 的真实包装矩阵核验 `ConnectError`、`ConnectTimeout`、`PoolTimeout`、`ReadError`、`ReadTimeout`、`WriteError` 分类；当前定向测试集实跑与 `--collect-only` 均得到 44 项，实跑结果为 44 passed，范围是 retry 正反样本、Messages 防回归、final-attempt stream History facts、unconsumed Responses response、SDK error response 和两条 Responses smoke 路径。
- **第一人称执行：** 模拟 Responses 非流与流式请求从 capability route、每 attempt conversion、pre-header failure、单次 coordinator retry，到 final-attempt facts／History／stream handoff；模拟 retry budget 耗尽与不可重试异常终止；模拟 Messages connect failure，确认不注册 Responses retry strategy；再模拟“SDK 只给出 bare `APIConnectionError`、没有原始 cause”的分支，确认当前实现仍会透明重试未知失败。

## 事实性发现

[major] integration WIP `src/app/upstream/base.py:20-32` — bare `OpenAIAPIConnectionError` 在 `__cause__ is None` 时被直接判为可重试，不满足“原始异常窄 allowlist”，也无法证明请求尚未跨过可能产生上游副作用的 write／read 边界 — 当前 allowlist 明列的原始类型只有 `ConnectError`、`ConnectTimeout`、`PoolTimeout`，但第 26–27 行在缺少任何原始异常时返回 `True`；直接构造 OpenAI SDK `2.21.0` 的 `APIConnectionError(request=...)` 可复现 `cause=None` 且 helper 返回 `True`。真实 SDK 矩阵还证明 `ReadError`、`ReadTimeout`、`WriteError` 都同样包装为 `APIConnectionError`，只有 cause 链让 helper 能将它们排除；因此“没有 cause”不是“已证明为 connect failure”。source `584e63b` 更宽，会在 cause 链没有任何 `httpx.TransportError` 时也返回 `True`；integration 已正确修掉 `APIConnectionError → RuntimeError` 这一部分，但仍保留无 cause 的未知分支。生产 callers `src/app/upstream/generic.py:89-92` 与 `src/app/upstream/copilot.py:155-158` 会把该判定包装为 `ResponsesHeadersPendingTransportError`，随后 `src/app/pipeline/executor.py:300-334` 启动透明 retry。失败场景是自定义／替换 SDK client 抛出无 cause 的 `APIConnectionError`，实际失败可能发生在 write／read 阶段，当前实现仍重发请求，存在重复上游操作风险。建议 fail closed：只有直接异常或 cause 链明确命中三种 allowlisted `httpx` 类型时返回 `True`，`cause is None` 返回 `False`；增加 bare `APIConnectionError` 不重试的回归测试，并保留当前 wrapped `RuntimeError`、direct `ReadError`、Messages 单次尝试正反样本。

## 已核对且未发现回归

- `src/app/anthropic/client.py:232-337` 仍在每次 Responses attempt 中从 model catalog 构造 `ReasoningCapabilityFacts`／`ReasoningEffortBand`，并保留 request conversion facts、converted response 与 typed usage；network retry 没有旁路这些转换。
- `src/app/pipeline/executor.py:349-468` 仍只从成功 attempt 发布 request／response conversion facts、normalized response、final payload 与 usage，并在非流成功后走既有 FINALIZE／History；retry 后 facts 的 attempt 归属保持 final attempt。
- `src/app/pipeline/executor.py:456` 的 stream 成功状态仍为 `STREAMING`；upstream 的 `send_responses_headers()` 返回未消费 response，由既有 stream route 接管，没有在 network retry 层读取 body 或创建第二套 stream facts。
- Messages 分支不插入 `ResponsesNetworkTransportStrategy`；Messages connect failure 定向测试仍断言单次调用。
- HTTP status error 仍返回 response 进入既有 coordinator；任意 `RuntimeError`、direct `ReadError` 与 response body read failure不应被本次 pre-header allowlist 扩大。integration 已覆盖前两类；body read failure由成功取得 response 后的既有读取失败路径终结，不经过 `ResponsesHeadersPendingTransportError`。

## 主观建议

未提出额外建议。按本次范围，不扩展 retry quota，也不设计 partial-write／continuation 语义；这些内容未作为本次放行条件。

## 结构怪味扫描

- `src/app/upstream/base.py:20-32` — **抽象泄漏／未知状态被默认归入安全集合** — 本轮作为 major 修复，不能记为非阻断 backlog。
- 扫描范围还包括 `src/app/anthropic/client.py`、`src/app/pipeline/executor.py`、`src/app/pipeline/strategies/__init__.py`、两个 upstream 实现及四组相关测试；除上述 allowlist fallback 外，未发现本次 integration 新增且需要本轮处置的结构怪味。
