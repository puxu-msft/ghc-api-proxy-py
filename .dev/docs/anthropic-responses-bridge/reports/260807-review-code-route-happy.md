# Anthropic Responses route happy-path 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-route-happy`，分支 `feat/anthropic-responses-route-happy`，固定 `HEAD=f3a5a768491c542224103a87b75e5bb39803ac4a`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。仅评审 happy-path 纵向切片：单一 `RequestContext`／approval／hooks／History owner、每 attempt `PRE_SEND` 后转换、Responses-only／显式 override／双能力默认 Messages 路由、HTTP `send_responses`、non-stream 转换／错误 envelope／headers、Responses stream 零调用显式错误、existing Messages 回归及 smoke 假绿风险。按派活边界，不要求也不评审 stream converter、block buffering 或 block sink。
- **总体 verdict**：**可进入下一阶段，可 squash。** 未发现阻止 squash 的 major。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 固定并逐次复核目标物理 root、branch、HEAD 与 clean worktree；候选相对 base 为单提交，变更面为 `src/app/anthropic/client.py`、`src/app/config/settings.py`、`src/app/pipeline/context.py`、`src/app/pipeline/executor.py`、`src/app/routes/anthropic.py`、`src/app/upstream/bootstrap.py`、`tests/smoke/test_anthropic_responses_route.py` 与 `tests/smoke/test_systemd_units.py`。
- 对账最终态而非只看 diff：route policy、`AnthropicClient`、pipeline executor、FastAPI route、runtime lifespan owner 接线、`GenericUpstream`／`CopilotUpstream`、OpenAI SDK `max_retries=0`、request／non-stream response converters、header policy及既有 Messages tests。
- `src/app/anthropic/client.py:163-176,178-219,221-283` 将 route decision 保留在 prepared request 上；Responses leg 调用 `send_responses()`，成功 body 转成 Anthropic message，失败 status 先转 Anthropic error envelope，并在所有路径关闭原 upstream response。
- `src/app/pipeline/executor.py:120-179,202-337` 保持单一 context、approval、attempts、hooks 与 History owner；route metadata 写回同一 context，Responses stream 在 attempt 创建和 upstream 调用前显式失败；每 attempt 的 `PRE_SEND` 完成后才构造当前 prepared request并发送。
- `src/app/routes/anthropic.py:45-144` 继续只调用 `client.execute()`；`ApiError`、`UpstreamResponseError` 与成功 non-stream 均输出 Anthropic-facing envelope／body，并经既有 response header policy 过滤。
- `src/app/upstream/bootstrap.py:137-149,223-235` 把同一 model catalog 注入生产 `AnthropicClient`；`src/app/server.py:98-126` 随后把 production History、approval gate 与 hooks 接回同一个 client，没有创建第二 lifecycle owner。
- `src/app/upstream/generic.py:43-54` 与 `src/app/upstream/copilot.py:104-116` 都通过 production OpenAI SDK `POST /responses`；`src/app/upstream/client.py:34-83` 的 SDK 自动 retry 保持关闭。
- 定向 pytest、完整 `tests` pytest、ruff 与 pyright 均通过；每次执行前后均复核指定 HEAD 和 clean worktree。报告不把测试计数当作覆盖面证明。

### 第一人称执行模拟

- 模拟 Responses-only 请求：resolved model catalog 只广告 `/responses`，同一 ASGI `/v1/messages` 请求只调用一次 Responses transport，request hook／approval／History／response hook／finalize 共用同一 context，用户得到转换后的 Anthropic `MessagesResponse` 与允许的 request-id header。
- 模拟双能力 auto 与显式 override：auto 走 existing Messages；override `responses` 走 Responses；两条路径都由同一 route decision 接缝决定，未在 route handler、converter 或 retry 中二次猜测。
- 模拟两次 attempt：第一次 Responses exchange 返回 429，自定义 retry strategy 修改 canonical Anthropic metadata；第二次 attempt 再跑 `PRE_SEND`。独立探针观察到两个 outbound Responses payload 的 `max_output_tokens` 分别反映各自 attempt 值，且 retry 修改只出现在第二次 wire，证明不是 loop 外陈旧转换。
- 模拟 Responses 429：upstream OpenAI error body被转换为 Anthropic error envelope，HTTP status 与 `retry-after` 保留，History 在同一 context 上失败终止，原 upstream response关闭。
- 模拟 Responses `stream=true`：在 attempt 和网络调用前返回带稳定 code 的 Anthropic 400 error；Messages 与 Responses transport 调用数均为零，History／approval仍属于同一请求。
- 模拟 production HTTP last mile：用真实 `GenericUpstream`＋OpenAI SDK＋本地 `MockTransport` 执行，观测到单次 `POST https://upstream.test/v1/responses` 与 exact JSON body；因此新增 ASGI smoke 虽以 `RecordingTarget` 隔离 upstream，本评审没有把 fake method 本身冒充物理 HTTP 接线证据。
- 模拟 existing Messages 回归：双能力 auto 请求仍调用 `send_anthropic()`，完整回归测试通过；systemd real-process smoke 的 model fixture补充明确 `/v1/messages` capability，符合 current fail-closed route contract。

## 事实性发现

未发现阻止 squash 的 major。

## 主观建议

按本次授权只报告阻止 squash 的 major；未列非阻断建议。

## 验证摘要

- 定向 route／policy／pipeline／request converter／non-stream response converter 测试：通过。
- 全量 `tests`：通过。
- ruff：通过。
- pyright：通过，零 diagnostics。
- 独立两-attempt probe：通过；真实 exchange 与 attempt 一一对应，每 attempt `PRE_SEND` 后重新转换。
- production SDK HTTP probe：通过；单次 `POST /v1/responses`，body exact，未走 Messages transport。
- 目标树收尾状态：仍为 `feat/anthropic-responses-route-happy@f3a5a768491c542224103a87b75e5bb39803ac4a`，clean。
