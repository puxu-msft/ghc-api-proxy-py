# Anthropic Responses route happy-path 定向代码复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-route-happy` 分支 `feat/anthropic-responses-route-happy`，固定 `HEAD=44808b7d0be84a0c1eb5c58294726c620d4280cd`、base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮只复核 `docs/tmp/260807-verify-route-happy.md` 的唯一 FAIL——Responses-specific header 泄漏——以及上一轮 reviewed HEAD `f3a5a768491c542224103a87b75e5bb39803ac4a` 到 current HEAD 的三文件增量是否引入新问题；不重新展开 route happy-path 既有全量代码评审，也不把结论扩大到完整 Responses stream 或 bridge 全规格。
- **总体 verdict**：**可进入下一阶段，0 major，明确可 squash。** 上一验收的 header 泄漏 FAIL 已关闭；本轮未发现新 major。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对

- 每个 load-bearing 检查均固定目标物理 root、branch、完整 HEAD 与 clean worktree。current HEAD 相对上一 reviewed HEAD 只修改 `src/app/anthropic/client.py`、`src/app/anthropic/header_policy/__init__.py` 与 `tests/smoke/test_anthropic_responses_route.py`。
- 对账上一验收根因：旧实现把 Responses upstream headers 原样带入转换后的 `httpx.Response`，随后默认宽松的通用 response policy 允许 `x-internal-openai` 穿透。current `src/app/anthropic/client.py:253-260` 与 `src/app/anthropic/client.py:350-360` 分别在成功和错误 adapter 边界调用 `normalize_responses_response_headers()`；两条路径均不再把原 header 集直接交给 route 层。
- `src/app/anthropic/header_policy/__init__.py:54-61,112-120` 采用 Responses 专用 allowlist：仅允许大小写不敏感的 `request-id`、`x-request-id`、`retry-after` 与 `x-ratelimit-*`；内部、认证、framing、cookie、Responses content-type及其他未列 header均在 adapter 边界丢弃。
- 通用 `forward_response_headers()` 未改，且仍在 route 层对归一化后的集合应用 strict／blacklist／whitelist，因此用户现有 response header 配置仍可继续收紧。新 helper 仅由 Responses 成功／错误路径调用，Messages 路径未调用它。
- 增量 smoke 同时断言 Responses 200 的 `x-internal-openai` 不下发、request id／rate-limit 保留且 upstream `content-length=99999` 不沿用；Responses 429 的内部 header 不下发且 `retry-after` 保留；双能力 auto 的 Messages 路径仍保留既有 `x-messages-existing`。
- 定向三文件 ruff 通过；定向三文件 pyright 为 `0 errors, 0 warnings, 0 informations`。直接 helper 向量验证 mixed-case allowlist，并确认 internal、auth、framing 与伪 Anthropic quota header均不进入归一化集合。

### 第一人称执行模拟

- 模拟 Responses-only HTTP 200：upstream 同时返回 `request-id`、`x-ratelimit-remaining-requests`、伪造 `content-length=99999` 与 `x-internal-openai`；真实 FastAPI／ASGI `/v1/messages` 客户端只观察到允许的 request id／rate-limit，内部 header消失，响应 framing由下游重算。
- 模拟 Responses-only HTTP 429：错误 envelope仍为 Anthropic-facing 429，`retry-after=3` 保留，`x-internal-openai` 消失；错误旁路没有绕开专用归一化。
- 模拟双能力 auto Messages：仍走 existing Messages leg，`x-messages-existing=preserved` 可见；Responses allowlist未错误施加到 Messages。
- 运行完整 `tests/smoke/test_anthropic_responses_route.py` ASGI matrix，pytest结果为 `5 passed`。源码对应 2 个参数化 Responses non-stream route case，加 Messages 保持、Responses stream零调用错误、Responses 429三个独立 case。
- 对 header判据做无文件写入的运行时正控：临时把 `app.anthropic.client` 已绑定的归一化函数替换为旧式 `dict(headers)`，同一真实 ASGI success oracle按目标原因观测到 `x-internal-openai` 泄漏并变红；恢复 production helper后重新为绿。这证明绿色确实依赖新增 adapter边界，而不是 TestClient或通用 route policy偶然隐藏 header。

## 事实性发现

未发现问题。

## 主观建议

无。

## 验证摘要

- ASGI matrix：`tests/smoke/test_anthropic_responses_route.py` 通过，pytest报告 `5 passed`。
- 独立 ASGI header probe：Responses 200内部 header消失、request id／rate-limit保留；Responses 429内部 header消失、`retry-after`保留；Messages既有 header保持。
- 正控：绕过 Responses normalization后按 `x-internal-openai` 泄漏原因变红；恢复后重新为绿。
- 静态检查：三文件 ruff通过；三文件 pyright零 diagnostics。
- helper边界探针：大小写不敏感；internal／auth／framing／伪 Anthropic quota header均拒绝。
- 收尾：目标树仍为 `feat/anthropic-responses-route-happy@44808b7d0be84a0c1eb5c58294726c620d4280cd` 且 clean；本报告不表示完整 Responses stream、bridge全规格或产品发布已通过。
