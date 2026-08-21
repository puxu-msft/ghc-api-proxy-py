# Anthropic Responses route-happy 独立验收 R3

- **候选**：`/home/xp/src/ghc-api-proxy-py-route-happy`，`feat/anthropic-responses-route-happy@dd376d6f1e9dc2997bc2f95d03a352fed4df1412`。
- **base／主树证据基线**：`main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- **冻结行为 oracle**：主树 `docs/agents/anthropic-responses-bridge/spec.md`，状态 `FINALIZED`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。该哈希由 `sha256sum` 与 Python `hashlib.sha256` 两种方法交叉复核一致。
- **总体判定**：**`PASS`。** 用户点名的三类 pre-attempt 拒绝、Responses non-stream success／header／error、Messages 回归及 observer 抛错正控均在固定候选 HEAD 上通过。
- **范围边界**：本 verdict 只覆盖本报告矩阵。Responses `stream=true` 的通过含义仅为“当前切片按冻结行为在 attempt 与 upstream exchange 前显式拒绝”；完整 Responses stream converter、SSE block commit、post-commit failure、cancel、backpressure及 HTTP／WS parity仍为 **`UNVERIFIED`**。不得把本报告外推为完整 bridge `PASS`。
- **写入边界**：候选树未写入；本文件是本轮唯一写入主树的产物。独立 harness 通过 stdin 执行，没有创建临时脚本、fixture或测试文件。

## 从冻结 Spec 独立推导的验收矩阵

| 验收项 | Spec 推导的 expected | 实际结果 | 判定 |
|---|---|---|---|
| unknown capability | Anthropic-compatible HTTP error；`REQUEST_RECEIVED → ERROR → FINALIZE`；attempt 与 upstream exchange 均为零；一个 History identity只 started／finalized 各一次 | HTTP `400`，code `capability_missing`；事件为 `request_received → error → finalize`；attempt `0`；Messages／Responses upstream均 `0`；History `1 started／1 finalized`且为同一 context | PASS |
| Responses override mismatch | 显式 Responses override 不得 fall through 到 Messages；同一 pre-attempt failure lifecycle与零网络合同 | HTTP `400`，code `override_unsupported`；事件为 `request_received → error → finalize`；attempt `0`；两种 upstream均 `0`；History同一 context各一次 | PASS |
| selected Responses＋`stream=true` | 当前切片未实现 stream时必须显式 typed reject，不得创建 attempt或调用任一 upstream | HTTP `400`，code `responses_stream_not_supported`；事件为 `request_received → error → finalize`；attempt `0`；两种 upstream均 `0`；History同一 context各一次 | PASS；完整 stream仍 `UNVERIFIED` |
| Responses non-stream happy | 只调用 Responses；转换为 Anthropic message；usage按 `I=max(0,T-R-W)`；single context／attempt／History；关闭 upstream response | Responses `1`、Messages `0`；HTTP `200`；text为 `RESPONSES-HAPPY`；`T=100,R=20,W=10,O=30,Q=12`得到 `input=70,cache_read=20,cache_creation=10,output=30`；attempt `1`；History同一 context各一次；upstream已关闭 | PASS |
| Responses success header | 仅保留明确允许的 request id、`retry-after`与 rate-limit facts；Responses-specific、未知 framing及 hop-by-hop header不下发；不得沿用 upstream `content-length` | 保留 `request-id`、`x-request-id`、`retry-after`、`x-ratelimit-remaining-requests`；未出现 `x-internal-openai`、`openai-processing-ms`、`x-upstream-frame-mode`、`transfer-encoding`；客户端 `content-length`不等于 upstream伪造值 `424242` | PASS |
| Responses non-stream upstream error | 保留可表达的 HTTP status、message、code与允许 header；形成 Anthropic error；同一 context失败终止且关闭 upstream | HTTP `429`；Anthropic `rate_limit_error`，message `UPSTREAM-RATE-LIMIT`，code `rate_limit_exceeded`，`retry-after=17`；Responses `1`、Messages `0`；事件为 `request_received → error → finalize`；History同一 context各一次；upstream已关闭 | PASS |
| Messages 回归 | 双能力且无 override时固定走 Messages；Responses header allowlist不得改变既有 Messages header行为 | Messages `1`、Responses `0`；HTTP `200`；content为 `MESSAGES-REGRESSION`；route reason为 `dual_capability_default`；`request-id`与既有 `x-messages-existing`保留；History同一 context各一次 | PASS |
| observer 抛错正控 | 真实 `ERROR`／`FINALIZE` observer接缝必须被触达；observer异常应被记录并隔离，不得吞掉原 typed rejection或造成重复 finalize | 注入 observer在 `ERROR`与`FINALIZE`分别抛出 `POSITIVE-CONTROL-error`与`POSITIVE-CONTROL-finalize`；两次调用与两条 hook error record均可见；原 `capability_missing`、零 attempt／upstream、单 History终态保持不变 | PASS |

## 独立运行方法与证据

### 真实 ASGI＋fake upstream matrix

本轮从冻结 Spec先确定 expected，再读取候选实现与既有测试。验收通过 stdin-only Python harness运行，不复用旧 `/tmp/verify_route_happy_260807.py`，也不调用候选 converter或 codec生成 expected。

执行路径包含 production `create_app()`、真实 FastAPI `POST /v1/messages` route、`httpx.ASGITransport`、production dependency injection、`AnthropicClient`、single pipeline owner、route policy、request／response converter、header policy、hooks与 History consumer接缝；只以可计数 fake替代外部 upstream。fake返回独立静态 Responses／Messages wire fixture，并记录两种 transport的实际调用。

执行绑定与加载 oracle：物理 root `/home/xp/src/ghc-api-proxy-py-route-happy`，branch `feat/anthropic-responses-route-happy`，HEAD `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`，解释器 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python`，`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-route-happy/src`。进程内 `app.__file__` 为 `/home/xp/src/ghc-api-proxy-py-route-happy/src/app/__init__.py`，证明运行时加载的是候选实现而非主树副本。

可信执行 marker为 `BEGIN_VRH3_ASGI_MATRIX_DD376D6_4A7C`、`HARNESS_VERDICT=PASS`、`END_VRH3_ASGI_MATRIX_DD376D6_4A7C`，命令退出码为 `0`。执行前后候选 HEAD不变且 tracked／untracked worktree均为空；主树指定报告在执行时尚不存在。

### observer 抛错正控的判别力

- **被测对象边界**：pre-attempt typed rejection发生后，production hooks executor对 `ERROR`与`FINALIZE` observer的真实调用接缝，以及 observer error isolation与 hook record。
- **缺陷注入**：仅增加一个 observer；它只订阅 `ERROR`和`FINALIZE`，每次先记录调用再抛出独立固定异常。route policy、ASGI request、fake upstream、History recorder与 expected不变。
- **正控结果**：stderr出现两条 production warning；observer调用序列精确为 `error,finalize`，context hook records精确保存 `POSITIVE-CONTROL-error`与`POSITIVE-CONTROL-finalize`。若任一 terminal接缝未被触达、异常未被隔离或 hook record未保存，同一断言会按目标机制变红。
- **恢复与基线**：正控使用独立 harness实例，没有修改生产文件；随后 Responses success／error与 Messages回归实例继续通过。候选工作树始终干净。

### 候选持久化回归资产

在同一固定 HEAD与同一 import oracle下运行：

- `tests/smoke/test_anthropic_responses_route.py`
- `tests/http/test_anthropic_routes.py`
- `tests/component/test_pipeline_executor.py`

pytest退出码为 `0`，三个文件的选中测试全部通过。可信 marker为 `BEGIN_VRH3_TARGETED_PYTEST_DD376D6_B81E`与`END_VRH3_TARGETED_PYTEST_DD376D6_B81E`；执行后候选 HEAD仍为 `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`且 worktree为空。该回归结果只作为持久化资产补证，最终 verdict主要依据上一节独立 ASGI运行。

## 未验证范围

- 完整 Responses stream，包括 Anthropic SSE grammar、首 block前零 success header／body、block envelope、terminal usage、post-commit failure、cancel、backpressure及 HTTP／WS parity。
- approval modified payload、retry后的第二 attempt、transport unavailable、Responses WebSocket、count_tokens、真实外部 upstream canary与 SQLite History durability。
- 本轮未运行全项目 pytest、ruff或pyright，因此不把定向回归扩大为全项目 gate通过。

## 结论

固定候选 `dd376d6f1e9dc2997bc2f95d03a352fed4df1412` 对用户点名的 route-happy R3 验收切片总体 verdict为 **`PASS`**。unknown capability、Responses override mismatch与 selected Responses stream reject均在真实 ASGI路径上满足 `request_received → error → finalize`、零 attempt、零 upstream与单一 History identity；Responses non-stream success／header／error及 Messages回归全部成立；observer抛错正控证明 terminal observer接缝真实可达且异常隔离不破坏原终态。完整 Responses stream与完整 bridge继续为 **`UNVERIFIED`**。

本报告是当前状态交付物；按叶子验收者职责标记为**需要主会话完成独立文档复核后再定稿**。