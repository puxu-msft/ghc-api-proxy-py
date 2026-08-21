# Anthropic Responses route happy-path 独立复验 R2

- **候选**：`/home/xp/src/ghc-api-proxy-py-route-happy`，`feat/anthropic-responses-route-happy@44808b7d0be84a0c1eb5c58294726c620d4280cd`。
- **上一验收候选**：`f3a5a768491c542224103a87b75e5bb39803ac4a`。本轮新增提交为 `44808b7d0be84a0c1eb5c58294726c620d4280cd`，提交说明为 `fix: filter Responses headers for Anthropic clients`。
- **冻结行为 oracle**：主树 `docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；本轮以 `sha256sum` 与 Python `hashlib.sha256` 两种原理交叉复核一致。
- **主树证据基线**：`main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- **总体判定**：**`PASS`。** 上一轮 route-happy matrix 的全部项目在固定候选 HEAD 上独立重跑通过；上一轮唯一失败项已关闭。Responses 成功和 429 错误路径均不再泄漏 `x-internal-openai`、`openai-processing-ms`、未知 `x-upstream-frame-mode` 或 hop-by-hop framing，且允许的 `request-id`、`x-request-id`、`retry-after` 与明确 rate-limit header 保留。Messages leg 的原有响应 header 与调用路径未被 Responses allowlist 误伤。route 反转与 Responses header normalizer 旁路两个单侧正控均按目标原因变红，恢复后保持绿。
- **完整 stream**：**`UNVERIFIED`。** 本轮只复验 selected Responses＋`stream=true` 在网络调用前返回 typed Anthropic error；没有实现或验收完整 Responses stream converter、SSE grammar、block commit、post-commit failure、cancel、backpressure或 HTTP／WS parity。不得把本切片 `PASS` 扩张为 stream 或完整 bridge `PASS`。
- **写入边界**：候选树未写入；执行前后均为上述固定 HEAD 且 `git status --porcelain` 为空。本文件是本轮唯一写入主树的产物。

## 从冻结 Spec 独立重建的本轮矩阵

| 验收项 | 独立 expected | 实际结果 | 判定 |
|---|---|---|---|
| Responses-only non-stream route | 只调用 Responses 一次，Messages 零调用 | Responses `1`，Messages `0`，HTTP `200` | PASS |
| non-stream text／reasoning／tool／usage | block 顺序为 `thinking → text → tool_use`；reasoning 使用 Spec 项目主 v1 exact carrier；tool identity 与 JSON input 保留；usage 使用 `I=max(0,T-R-W)` | 顺序一致；`opaque-😀` carrier exact；`call_acceptance_01`／`weather`／`{"city":"Paris"}` 保留；`T=100,R=20,W=10,O=30,Q=12` 得 `input=70,cache_read=20,cache_creation=10,output=30` | PASS |
| explicit Responses override＋双支持 | override 优先，Responses `1`，Messages `0` | 符合 | PASS |
| explicit Messages override＋双支持 | override 优先，Messages `1`，Responses `0` | 符合 | PASS |
| auto＋双支持 | 固定选择 Messages，Messages `1`，Responses `0` | 符合 | PASS |
| `PRE_SEND` 后转换 | 最终 Responses wire 只含 hook 修改后的 `PRE-SEND-MARKER`，不含入站 `ORIGINAL-MARKER` | 符合 | PASS |
| approval／History／context／attempt single owner | approval `1`、History started／finalized 各 `1`、同一 context／request id、attempt `[0]`、真实 exchange `1` | 全部符合；History original payload 保留原 marker | PASS |
| Responses upstream HTTP 429 | Anthropic HTTP `429` error envelope，保留稳定 message／code与允许 header | `rate_limit_error`、`RATE-LIMIT-MARKER`、`rate_limit_exceeded`；Responses `1`、Messages `0` | PASS |
| selected Responses＋stream | typed Anthropic HTTP `400` error，Responses／Messages 网络调用均为 `0` | `responses_stream_not_supported`，两类调用均 `0` | PASS；完整 stream 仍 `UNVERIFIED` |
| Responses success header 边界 | internal／Responses-specific／未知 framing／hop-by-hop header 不下发；request id、retry-after与明确 rate-limit header允许 | `x-internal-openai`、`openai-processing-ms`、`x-upstream-frame-mode`、`transfer-encoding` 均缺失；`request-id`、`x-request-id`、`retry-after`、`x-ratelimit-remaining-requests` 保留；upstream `content-length=424242` 未沿用 | PASS |
| Responses 429 header 边界 | 错误路径与成功路径使用同一归一化边界 | 同一组禁止 header 均缺失，同一组允许 header 均保留 | PASS |
| Messages leg 回归 | 双支持 auto 仍走 Messages；Responses allowlist 不改变 direct Messages 原 header policy | Messages `1`、Responses `0`；`request-id=messages-request-id` 与 `x-messages-existing=preserved` | PASS |

## 独立 oracle 与执行证据

### 上一 matrix 原样重跑

本轮复用了上一验收的独立临时 harness `/tmp/verify_route_happy_260807.py`，先完整通读确认其 expected 为静态 Spec vector与独立 Responses fixture，不调用候选 codec／converter生成 expected。harness SHA-256 为 `7f3f5f2f9461f4709ed2bc2ae9369694dd37af64d91f1bbef4a68eac9446600a`。

执行绑定：物理 root `/home/xp/src/ghc-api-proxy-py-route-happy`、分支 `feat/anthropic-responses-route-happy`、HEAD `44808b7d0be84a0c1eb5c58294726c620d4280cd`、`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-route-happy/src`、解释器 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python`、`PYTHONDONTWRITEBYTECODE=1`。运行前导入探针确认 `app.__file__` 位于候选树 `src/app/`。

可信执行 marker 为 `BEGIN_INDEPENDENT_ROUTE_R2_MATRIX_44808B7_E19C`／`HARNESS_VERDICT=PASS`／`END_INDEPENDENT_ROUTE_R2_MATRIX_44808B7_E19C`，退出码 `0`。结构化结果确认上述 Responses-only、双 override、auto Messages、`PRE_SEND`、single owner、429、selected stream与 route 反转正控全部满足 expected；执行后候选 HEAD 不变且 clean。

### Header 扩展探针

本轮另用真实生产 `create_app()`、FastAPI `POST /v1/messages`、production dependency wiring、pipeline、route policy、Responses adapter、header policy和 `httpx` ASGI client执行短探针；仅外部 upstream 由 fake 替代。Success 与 HTTP 429 均注入：

- 允许候选：`request-id=req-allow`、`x-request-id=xreq-allow`、`retry-after=13`、`x-ratelimit-remaining-requests=5`。
- 禁止候选：`x-internal-openai=reject-internal`、`openai-processing-ms=reject-openai`、未知 `x-upstream-frame-mode=reject-unknown-framing`、`transfer-encoding=chunked`、伪造 upstream `content-length=424242`。

可信执行 marker 为 `BEGIN_ROUTE_R2_HEADER_SHORT_44808B7_71AF`／`HEADER_BASELINE_GREEN`／`MESSAGES_REGRESSION_GREEN`／`HEADER_POSITIVE_CONTROL_RED`／`END_ROUTE_R2_HEADER_SHORT_44808B7_71AF`，退出码 `0`。成功与 429 路径均仅保留允许项；禁止项均未下发，且 route 层重新生成的 `content-length` 不等于 upstream 伪造值。Messages leg 保留 `request-id` 与 `x-messages-existing`，调用计数为 Messages `1`／Responses `0`。

### 正控

#### Route 反转

- **被测对象边界**：双支持模型无 override 时，真实 ASGI 请求最终触发的 Messages／Responses transport 调用计数。
- **正确样本**：Messages `1`、Responses `0`。
- **单侧变异**：只把 route selector 的双支持 auto 结果反转为 Responses，不修改 expected、fixture或 transport counter。
- **结果**：同一 oracle 以 `route oracle rejected inversion: messages=0 responses=1` 按目标原因变红。
- **恢复**：patch context退出后生产 selector恢复，候选树无改动。

#### Responses header normalizer 旁路

- **被测对象边界**：Responses adapter 在成功和错误 response 转为 Anthropic-facing response之前的 header归一化边界。
- **正确样本**：未知 `x-upstream-frame-mode` 不可见，允许 header可见。
- **单侧变异**：只将 `app.anthropic.client.normalize_responses_response_headers` 暂时替换为 identity；route policy、fake headers与 assertion不变。
- **结果**：同一 oracle 以 `normalizer bypass leaked unknown framing=reject-unknown-framing` 按目标原因变红。
- **恢复**：patch context退出后重回生产 normalizer，候选树无改动。

该正控证明 gate 依赖真正的 Responses header归一化机制，而不是只因通用 route policy、fake未注入header或某个固定 blacklist拼写而绿。

## 候选回归与静态检查

在同一固定候选 HEAD 上执行以下相关范围：

- `tests/smoke/test_anthropic_responses_route.py`
- `tests/smoke/test_route_policy.py`
- `tests/unit/test_anthropic_preparation.py`
- `tests/http/test_anthropic_routes.py`

结果为 `30 passed in 3.75s`。另以 `pytest --collect-only` 按 node id独立计数得到 `30`，与运行数一致。targeted ruff输出 `All checks passed!`；targeted pyright输出 `0 errors, 0 warnings, 0 informations`。执行后候选 HEAD仍为 `44808b7d0be84a0c1eb5c58294726c620d4280cd`且 clean。

候选实现的最终承载位置经交付前复核：

- `src/app/anthropic/header_policy/__init__.py:54-61`：Responses允许 header集合与 rate-limit pattern。
- `src/app/anthropic/header_policy/__init__.py:112-120`：Responses header归一化函数。
- `src/app/anthropic/client.py:255`：成功 response在Anthropic转换后使用归一化headers。
- `src/app/anthropic/client.py:352`：Responses错误 envelope同样使用归一化headers。

这些位置只解释本轮观测到的承载接缝；最终判定来自上述真实 ASGI运行，不来自静态读码。

## 无效证据处置

共享终端期间有数次调用被其他并发会话输出抢占或被外部 `Ctrl-C` 中断。凡未出现本轮唯一 nonce首尾marker、输出属于其他仓库／HEAD、或最终退出码非零的调用均整体作废，未用于任何 PASS／FAIL结论。最终判定只使用本报告明确列出的完整 marker与退出码为 `0` 的执行。

## 未验证范围

- 完整 Responses stream：Anthropic SSE grammar、完整 block commit、首 block前零header／body、stream usage、post-commit failure、cancel、backpressure、HTTP／WS parity均未验证。
- approval modified payload与retry后的第二attempt：本轮原样matrix验证unchanged approval、单attempt和`PRE_SEND`修改后的wire，没有把未测路径折算为通过。
- capability unknown／unsupported／transport unavailable、Messages-only、WS physical transport、count_tokens、真实upstream canary、capture corpus与local socket fault不在本轮切片范围，保持`UNVERIFIED`。
- 本轮不把相关`30`个候选测试通过扩张为全项目回归通过，也不把route-happy切片`PASS`扩张为完整bridge符合Spec。

## 结论

候选`44808b7d0be84a0c1eb5c58294726c620d4280cd`对本轮route-happy切片的总体verdict为**`PASS`**。上一matrix全部项目通过；Responses成功和错误路径均建立了明确allowlist边界，`x-internal-openai`及未知framing不泄漏，`request-id`／`x-request-id`／`retry-after`与明确rate-limit header允许，Messages leg未回归；route反转与header normalizer旁路正控均有效。完整Responses stream仍为**`UNVERIFIED`**，不得随本切片一并放行。

本报告属于当前状态交付物，按叶子验收者职责标记为**需要主会话完成独立文档复核后再定稿**；该复核义务未因本轮是验证报告而消失。