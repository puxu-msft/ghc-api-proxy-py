# Responses network retry WIP 只读预审

评审范围：current `main` 与 `feat/responses-network-retry` worktree，二者基线均为 `910e4bcbe22f9477aa8d36e828f2d6a325498cd4`。WIP 快照限定为 `src/app/anthropic/client.py` blob `27b2b74b…`、`src/app/pipeline/executor.py` blob `173f2da…`、`src/app/pipeline/strategies/__init__.py` blob `729ca6a…`、`tests/component/test_pipeline_executor.py` blob `1141dfd…`。未检查或扩展 quota、partial-write 设计。

总体 verdict：**PENDING——修复 major 后可进入下一阶段**。

Blocker 数：**0**。

Major 数：**1**。

## 双视角覆盖证据

### 机械核对

- 用 `git diff-index`／`git diff-files` 以及 HEAD、index、worktree blob 三方比较识别真实 WIP；普通 `git status` 曾因 stat cache 未刷新显示假干净，因此未将其单独作为变更集证据。
- 对账 Responses leg 限定、原始 exception allowlist、既有 `RetryCoordinator(max_retries=1)` budget owner、attempt ledger、Messages transport、失败态 success facts 隔离及新增测试断言。
- 核对异常继承关系：`httpx.TransportError` 同时覆盖 `ConnectError`、`ConnectTimeout`、`ReadError`、`ReadTimeout`、`WriteError`、`WriteTimeout` 与 `PoolTimeout`；`openai.APITimeoutError` 是 `openai.APIConnectionError` 子类。
- 在上述最终四 blob 快照上单次运行 `tests/component/test_pipeline_executor.py`，结果为 26 passed；`ruff` 与 `pyright` 对四个 WIP 文件均通过。该测试数量是本次单次运行口径，未作第二原理计数交叉验证。

### 第一人称执行模拟

- 模拟 Responses 连接失败后成功：第二次 exchange 复用唯一 pipeline driver，attempt 为 `[0, 1]`，成功 facts 只来自 attempt 1。
- 模拟连续两次 SDK connection failure：共享 coordinator 只允许一次 retry，第二次失败后仅一次 FINALIZE，且没有 normalized response、usage、final payload 或 conversion facts。
- 模拟 `RuntimeError`、已返回 Responses response 后读取 body 时的 `ReadError`，以及 Messages leg 的 `ConnectError`：现有测试均保持单次 exchange。
- 额外模拟 Responses target 在返回 `httpx.Response` 前直接抛 `httpx.ReadError`：当前实现错误地将其标为 `responses_network_transport`，执行第二次 exchange 并最终成功，复现 allowlist 过宽缺陷。

## 事实性发现

[major] `src/app/anthropic/client.py:265-275`、`tests/component/test_pipeline_executor.py:1287-1337`——原始 exception allowlist 仍过宽，现有反例测试未命中同一捕获入口——`_send_responses()` 把整个 `httpx.TransportError` 家族包装成 `ResponsesHeadersPendingTransportError`，executor 随后在 `src/app/pipeline/executor.py:299-341` 消耗既有 retry budget。直接让 Responses target 在返回 response 前抛 `httpx.ReadError` 的只读探针得到 `success calls=2 attempts=2 owner=responses_network_transport`。现有 body-read 反例是在 target 已返回 `Response` 后由 `upstream.aread()` 抛错，位于 wrapper 之外，只能证明另一条路径不重试，不能约束 allowlist。修复建议：将 raw httpx 集合收窄为本次已裁定的连接类原始异常，例如显式 `httpx.ConnectError` 与按合同决定是否包含的 `httpx.ConnectTimeout`，保留 SDK `APIConnectionError` 类型；新增一个从 `send_responses()` 直接抛近邻非 allowlist `httpx.ReadError` 的反例，断言 calls 与 attempts 均为 1、strategy owner 为空。不要借此扩展 quota 或 partial-write 行为。

## 已通过的限定项

- Responses leg 限定：wrapper 仅位于 `AnthropicClient._send_responses()`，executor 还要求 route 为 `responses`。
- budget／attempt owner：network strategy 插入现有 `RetryCoordinator(max_retries=1)`，没有第二套 retry loop 或 transport retry owner。
- Messages 不回归：定向测试证明 Messages `ConnectError` 仍只有一次 transport call。
- 失败 attempt facts 隔离：成功 facts 只投影最终成功 attempt；budget 耗尽时 success facts 保持为空，ERROR 按 attempt 记录，FINALIZE 一次。
- 测试已具备主要路径的最小判别力；尚缺的唯一关键反例即上述同入口近邻异常。
