# Responses reasoning capability WIP 独立评审

- **评审范围**：严格只读评审 `/home/xp/src/ghc-api-proxy-py-reasoning-capability` 分支 `fix/responses-reasoning-capability` 的未提交 WIP。评审时 `HEAD == main == b91e58a29324b11840002efc53ed6f869b800c39`，候选仅修改 `src/app/anthropic/client.py` 与 `tests/smoke/test_anthropic_responses_route.py`；完整 WIP patch SHA-256 为 `ea970cbcec3239b651efebe0b817a2831ceaf1e3ff192ee727999019b8aa4cb7`。本轮定向复核 current main merged-state 报告 `docs/tmp/260807-review-main-successor-resume.md` 的第一项 major：`ModelInfo` reasoning facts 接线、unknown fail closed、enabled／adaptive／budget、每个 attempt 的 `PRE_SEND` 后转换与测试覆盖。候选文件未被修改。
- **总体 verdict**：**修复 major 后可 commit／squash。** WIP 已把 resolved-model facts 接入 production converter，并且转换确实发生在每个 attempt 的 `PRE_SEND` 后；但 facts adapter 仍从目录未声明的列表顺序臆造 enabled／adaptive effort 选择和 budget band，当前不可提交。
- **blocker 数**：0。
- **major 数**：1。

## 双视角覆盖证据

### 机械核对

- 每个承载结论的 shell 调用均在同一调用内绑定候选绝对路径、Git top-level 与完整 base HEAD；最终确认候选仍无分支提交，只有上述两文件 WIP，`git diff --check` 无输出。评审前后候选状态指纹均为 `4136d2fb22baa99f59f7bdb5f34488a9fc4cb05a6915028019d5cae4b2d8676a`。
- 对账 `ModelInfo → ModelCapabilities.supports → AnthropicClient._reasoning_capabilities() → convert_messages_request_to_responses()`：adapter 使用 resolved model 查目录；缺 catalog、缺 model、缺／空／重复 effort、缺 budget 字段与未显式 adaptive 均不会靠模型名猜测支持。`budget_limits_known` 使用 `model_fields_set` 区分字段缺失与显式无界，方向正确。
- 对账 pipeline 最终代码：每个 attempt 先执行 `PayloadPhase.PRE_SEND`，再用当次 `attempt_payload` 构造 `PreparedAnthropicRequest` 并进入 `_send_responses()`；因此 converter 不是 request-loop 外的一次性预转换。
- 以绝对 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-reasoning-capability/src` 证明 `app` 与 `app.anthropic.client` 均来自候选树后，定向运行 `tests/smoke/test_anthropic_responses_route.py` 与 `tests/unit/test_anthropic_responses_request.py`，pytest 全绿；同范围 ruff 与 pyright 也全绿。执行项数量只取 pytest 原生输出，未用第二原理交叉计数，故不在本报告写具体数量。
- 首次未绑定 `PYTHONPATH` 的测试实际把 `app` 导入到 `ghc-api-proxy-py-stream-route`，其红灯已作废；后续两次外部 `Ctrl-C` 中断也因缺少结束 nonce 作废。只有候选模块路径与 begin／end nonce 完整的专用日志结果进入本结论。

### 第一人称执行模拟

- **已知支持的 enabled／adaptive**：resolved model 同时声明 `reasoning_effort`、min／max budget 与 `adaptive_thinking` 时，真实 `/v1/messages` Responses-only route 可发送 reasoning wire；精确 budget 边界外返回 typed capability error，目录 facts 缺失时在 upstream 前 fail closed。
- **每 attempt 重转换**：内存 target 让 attempt 0 返回 429，retry strategy 触发 attempt 1；`PRE_SEND` hook 在 attempt 0 写入 enabled、在 attempt 1 写入 adaptive。捕获到的两个 Responses outbound payload 均反映各自当次修改，attempt journal 也分别记录当次 hook／retry modifications，证明转换位于每次 `PRE_SEND` 之后。
- **列表顺序反例**：同一个支持集合分别以 `['low', 'medium', 'high']` 与 `['high', 'medium', 'low']` 提供，adapter 分别把所有 enabled budget 和 adaptive 映射为 `high` 与 `low`。仅改变集合排列就改变 outbound wire；目录模型、Spec 与 adapter API 都没有声明该列表按强度排序或最后一项是默认 effort。
## 事实性发现

[major] `src/app/anthropic/client.py:291-317`、`src/app/models/capabilities.py:15-18`、`docs/agents/anthropic-responses-bridge/spec.md:203` — capability adapter 把 `reasoning_effort` 列表最后一项擅自解释为 enabled／adaptive 的目标 effort，并构造覆盖全部合法 budget 的开放 band，语义没有目录 facts 或冻结 Spec 支撑 — `ModelSupports` 只声明 `reasoning_effort: list[str] | None` 为支持集合以及 min／max budget，没有 budget→effort thresholds、默认 effort、adaptive preferred effort或顺序合同；Spec 还明确禁止把 budget heuristic 当作模型明确支持。运行时反例显示，同一集合只换排列，enabled 与 adaptive wire 就从 `high` 变成 `low`。这会让目录返回顺序变化成为用户可观察行为，也会把低 budget 无条件抬到最高 effort，或者在反向排列时把所有请求降到最低 effort；新增 smoke tests把当前“最后一项”策略写成 expected，因此测试全绿只是固化了无依据的策略 — adapter 只能发布目录明确提供的 facts。若当前目录无法表达 enabled budget bands／adaptive preferred effort，则这两个分支应 fail closed，或先由用户在产品合同中明确选择并记录一个独立配置／policy facts 来源；不要从支持集合的排列推导。补正反控制：同一 effort 集合不同排列必须产生相同结果或同样拒绝；单 effort 可作为明确无歧义正样本；多 effort 且无 band／preferred facts 必须按已裁决策略处理。修复并复评到 0 blocker／0 major 后即可 commit／squash。

## 主观建议

无。完整 History facts 是 current main 的另一项独立 major，不属于本 WIP 评审范围；stream route 的完整产品状态也不在本轮重开。
