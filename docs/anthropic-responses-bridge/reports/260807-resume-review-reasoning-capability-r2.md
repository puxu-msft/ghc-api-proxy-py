# Responses reasoning capability R2 独立代码评审

- **评审范围**：严格只读评审 `/home/xp/src/ghc-api-proxy-py-reasoning-capability` 分支 `fix/responses-reasoning-capability`，候选 `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，base `b91e58a29324b11840002efc53ed6f869b800c39`。候选增量只修改 `src/app/anthropic/client.py` 与 `tests/smoke/test_anthropic_responses_route.py`。唯一主树写入为本报告。
- **总体 verdict**：**可进入 squash。** 上一轮从 `reasoning_effort` 列表顺序推断 enabled／adaptive 策略的 major 已关闭；本轮未发现 blocker 或 major。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 每个纳入结论的 shell 证据都在同一调用内固定候选物理路径、Git top-level、分支与完整 HEAD；最终候选保持 clean，`git diff --check base..HEAD` 无输出。两次出现外部终端输出串线且缺少本轮 nonce 的结果已作废，未进入结论。
- `src/app/anthropic/client.py:281-319` 只在 `reasoning_effort` 恰为唯一、非空、无重复 effort 时发布 `selected_effort`。多 effort、空 effort 或重复 effort 不再选取列表位置；enabled 不获得 budget band，adaptive 不获得 preferred effort，随后由 converter typed fail closed。
- `src/app/anthropic/client.py:294-317` 把 enabled 与 adaptive 的事实门分开：enabled 还要求 min／max budget 字段都由 catalog 显式提供；adaptive 还要求 `adaptive_thinking` 字段显式存在且值为 true。缺 catalog、catalog miss、字段缺失或 ambiguous effort 均不会按模型名或默认字段值猜测支持。
- `src/app/pipeline/executor.py:225-252` 的最终执行顺序是每轮 attempt 先运行 `PRE_SEND`，再以当轮 `attempt_payload` 构造 `PreparedAnthropicRequest`，随后调用 `send_prepared()`；`AnthropicClient._send_responses()` 才读取 resolved model facts 并转换。因此转换位于每个 attempt 的 `PRE_SEND` 之后，而不是 request loop 外的一次性转换。
- `tests/smoke/test_anthropic_responses_route.py:410-566` 通过真实 `TestClient → FastAPI route → pipeline → AnthropicClient → Responses target` 覆盖 singleton enabled／adaptive、unknown facts、同一多 effort 集合的正反排列、精确 budget 边界和 `PRE_SEND` 改写后的重转换，并断言拒绝路径零 upstream。
- 本轮在固定候选模块路径上独立运行 reasoning 相关 ASGI smoke，全部选中用例通过，pytest 退出码为 0；候选工作树状态指纹执行前后相同。用户上下文中同一 HEAD 的 post-commit gate 还记录了定向 pytest、Ruff 与 Pyright 均成功；对应日志分别为 `/tmp/260807-rcap-postcommit-targeted.log`、`/tmp/260807-rcap-postcommit-ruff.log` 与 `/tmp/260807-rcap-postcommit-pyright.log`。

### 第一人称执行模拟

- **enabled**：singleton effort 加显式 min／max budget 时，边界内 budget 转为该唯一 effort；低于 min 或高于 max 时在网络前返回 `reasoning_budget_not_supported`。
- **adaptive**：singleton effort 且 catalog 显式声明 `adaptive_thinking=true` 时转为该唯一 effort；缺少显式 adaptive 支持时不借用 enabled 的 budget facts，稳定 fail closed。
- **ambiguous 排列**：`[low, medium, high]` 与 `[high, medium, low]` 都产生同一类拒绝且零 upstream；排列不再改变 outbound effort。重复或空 effort 同样不会退化成“取第一项／最后一项”。
- **unknown**：无 capability facts、model catalog miss、空／多 effort、budget 字段不完整或 adaptive 未显式声明时，不按模型名称猜测，也不因 Pydantic 默认值误判为已声明能力。
- **每 attempt**：attempt 0 与 retry attempt 1 均从当轮 `PRE_SEND` 的输出构造发送对象；retry strategy 对 payload 的修改会成为下一轮输入，下一轮 hook 后再次转换，不会复用前一轮已转换的 Responses wire。
- **回归路径**：不带 thinking 的 Responses-only 请求保持既有真实 ASGI 成功流；双 endpoint auto 仍走 Messages；capability／stream／upstream typed failure、History、approval 与 observer 的既有 route smoke 继续通过。

## 事实性发现

未发现 blocker 或 major。

## 主观建议

无。
