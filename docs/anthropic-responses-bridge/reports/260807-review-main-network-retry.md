# Current main headers-before network retry 定向复核

- **评审范围**：`/home/xp/src/ghc-api-proxy-py` 的 current `main@fb5c027b38cc72910dd4495979a26a57fbbaa99b`，父提交 `910e4bcbe22f9477aa8d36e828f2d6a325498cd4`。只核对本轮 Responses headers-before retry：Responses 限定、`ConnectError`／`ConnectTimeout`／`PoolTimeout` 窄 allowlist、bare SDK `APIConnectionError`／`ReadError`／`RuntimeError` 不重试、attempt／History／hooks，以及 Messages 不回归。
- **明确排除**：未扩展 retry quota、stream response 已建立后的 retry、quota／resident backpressure、真实 socket partial-write／RST 或完整 Acceptance；本报告不得外推为完整 retry 或完整产品 `PASS`。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 当前不是 0 major，不能按“0 major 可继续”放行。
- **Blocker 数**：**0**。
- **Major 数**：**1**。

## 双视角覆盖证据

### 机械核对

- 核实 `HEAD`、`refs/heads/main` 与提交元数据，确认本轮为单父提交 `fix: retry Responses connection failures before headers`；逐个通读最终 `client`、`executor`、retry strategy、Generic／Copilot upstream 与相关 tests，并对账 `HEAD^..HEAD`，不是只沿既有评审报告复述。
- `src/app/upstream/base.py:7-31` 的 allowlist 仅含 `httpx.ConnectError`、`httpx.ConnectTimeout`、`httpx.PoolTimeout`；bare `OpenAIAPIConnectionError` 在无 cause 时 fail closed，cause 链首次遇到 `httpx.TransportError` 时只接受这三个类型。当前 `openai 2.21.0`／`httpx 0.28.1` 独立矩阵探针确认：三种 allowlist 类型 direct／SDK-wrapped 均接受，`ReadError`／`ReadTimeout`／`WriteError`／`WriteTimeout`、bare SDK error 与 wrapped `RuntimeError` 均拒绝。
- `src/app/upstream/generic.py:76-95` 与 `src/app/upstream/copilot.py:141-164` 只在 `send_responses_headers()` 包装上述 typed error；`src/app/anthropic/client.py:255` 只由 Responses route 调用该入口；`src/app/pipeline/executor.py:252-255,300-342` 只给 Responses leg 组合 network strategy，并继续由既有 `RetryCoordinator(max_retries=1)` 消耗预算。
- 对账 reviewed source `584e63ba3724a7b6999d2163266d3daf8e731221`、integration tip `97b1a5c792a919022176f7a32179b2c51c632337` 与 current main，确认 source 中的 `test_responses_sdk_connection_failures_exhaust_single_retry_budget` 和 `test_copilot_responses_headers_returns_unconsumed_response` 在 integration／main 中消失。
- 最小现有测试选择器以 `--collect-only` 与实际执行两种原理交叉核对，共覆盖 16 个 node，执行结果为 `16 passed in 1.97s`；另跑 `tests/unit/test_retry_strategies.py` 通过。选择器覆盖 upstream target、network retry 成功、三类不重试反例、Messages 单 attempt、stream final-attempt History facts、Responses non-stream／stream 与 dual-capability Messages route。

### 第一人称执行模拟

- 模拟 Responses 首次 `ConnectError`、第二次成功：同一 `RequestContext` 形成 attempts `[0, 1]`，`PRE_SEND` 每 attempt 一次；attempt 0 记录 network error 与 `responses_network_transport` owner，成功 facts 只来自 attempt 1，History 单次 finalized，hooks 为一个失败 attempt `ERROR` 加最终 `RESPONSE`／`FINALIZE`。
- 模拟连续两次 allowlisted 连接失败：本轮不落盘探针得到真实调用数 2、attempt 数 2、owner 为 `['responses_network_transport', None]`、两个 attempt 均留错、`PRE_SEND` 为 `[0, 1]`、History 单次 finalized、事件序列为 `REQUEST_RECEIVED → ERROR(0) → ERROR(1) → FINALIZE`，成功 response／usage／payload／conversion facts 全空。运行行为正确，但该路径当前没有仓库回归测试。
- 模拟 bare SDK `APIConnectionError`、SDK error whose cause is `RuntimeError`、direct `ReadError`：均只调用一次，strategy owner 为空，只有失败 lifecycle；对应现有 component tests通过。
- 模拟 Messages `ConnectError` 与 dual-capability auto route：Messages 不注册 Responses network strategy，仍只进行一次 transport 调用；现有 component 与 ASGI smoke 均通过。
- 模拟 Copilot Responses 真实 SDK 包装入口：`httpx.ConnectError` 被 SDK 包装为 `APIConnectionError(cause=ConnectError)`，最终形成 `ResponsesHeadersPendingTransportError`；但该入口的 source 回归测试未保留到 main。

## 事实性发现

[major] `tests/component/test_pipeline_executor.py:1185-1335`、`docs/tmp/260807-next-small-slice.md:45-48`——current main 缺失本切片明确要求的 network retry exhaustion 回归路径——现有 tests 覆盖“第一次连接失败、第二次成功”和多个单次拒绝反例，却没有“两次 allowlisted 连接失败后预算耗尽”的 pipeline／History／hooks 断言；`tests/unit/test_retry_strategies.py:30-38` 只证明 coordinator 第二次决策返回 `None`，无法证明 executor 不进行第三次 exchange、两个 attempts 都留错、失败 attempt 不泄漏 success facts、History 只 finalized 一次以及 hooks 没有 `RESPONSE`。这不是尚未实现的建议项：reviewed source `584e63b…:tests/component/test_pipeline_executor.py:1243-1282` 原本已有该测试，integration／main 将其删除。临时探针证明当前实现今天正确，但不能替代仓库回归门；后续若在 executor 的 `continue`／finalize 顺序或 coordinator 接线中引入回归，现有 suite 可保持全绿。修复建议：恢复同等判别力的 test，但不要原样使用旧 source 的 bare `APIConnectionError`，因为 current fail-closed 合同正确地拒绝 bare SDK error；改用两次 direct `httpx.ConnectError`，或两次 cause 明确为 allowlisted connect error 的 SDK wrapper，并保留 source 中 calls／attempts／owner／success facts／History／hooks 的全部断言。

[minor] `tests/unit/test_upstream_targets.py:34-207`、`src/app/upstream/copilot.py:141-164`——Copilot 的新增 Responses headers 入口没有持久化单元测试——reviewed source 曾有 `test_copilot_responses_headers_returns_unconsumed_response`，integration／main 删除后，当前文件只测试 Copilot 的 Anthropic Messages 入口和 Generic 的 Responses 入口。本轮真实 SDK 探针确认 Copilot connect failure 包装正确，但没有仓库测试固定其 `stream=True`、Copilot headers 与未消费 response 合同。修复建议：恢复 Copilot Responses success 测试；可就近加入 connect failure typed wrapper 断言，避免 Generic 同构实现掩盖 Copilot 专属 headers／token 路径回归。

[minor] `src/app/upstream/base.py:7-31`、`tests/unit/test_upstream_targets.py:149-174`——正向 allowlist 的持久化测试只命中 `ConnectError`，没有固定 `ConnectTimeout` 与 `PoolTimeout`——本轮真实 runtime 矩阵证明当前分类正确，负向 `ReadError`／bare SDK／`RuntimeError` 也有 component 回归；但删除任一 timeout 成员会造成合法 pre-header 连接失败不再重试，而现有 suite 仍可全绿。这是 false-red 方向的测试判别力缺口。修复建议：给 helper 增加 direct 与 SDK-wrapped 参数化正反表，至少固定三种允许类型和一个近邻 `ReadError`；不要扩张到 quota 或 partial-write。

## 已核对且未发现回归

- Responses 限定没有泄漏到 Messages：network strategy 只在 route fact 为 `responses` 时组合，Messages transport 自身未被包装。
- bare SDK error、direct／SDK-wrapped `ReadError` 与 wrapped `RuntimeError` 均不重试；分类不是依据宽泛 `TransportError`、错误文本或归一化后的 `NETWORK` category。
- 第一次 allowlisted failure 后成功的 attempt／History／hooks 与 final-attempt conversion facts 保持一致；stream handoff仍使用未消费 response，没有把 body-read／post-header 失败纳入本片。
- Generic／Copilot 对 SDK HTTP status error仍返回 response 走既有 HTTP retry／错误路径，没有把 HTTP status 伪装成 headers-before transport exception。

## 主观建议

未提出额外主观建议。上述 major／minor 都是可由 current bytes、source→main 差分、现有测试清单与运行探针复现的事实性覆盖缺口。

## 结论

`main@fb5c027b38cc72910dd4495979a26a57fbbaa99b` 的 headers-before retry **实现行为在本轮定向探针中正确**，此前 bare SDK error 与宽 `TransportError` 两项 major 也已关闭；但 squash 丢失了明确要求且 source 已具备的 exhaustion 回归门，因此当前结论为 **0 blocker／1 major，修复 major 后可继续**。quota／resident backpressure、post-header retry与真实 socket partial-write继续保持本轮范围外，未被扩测或提前判定。
