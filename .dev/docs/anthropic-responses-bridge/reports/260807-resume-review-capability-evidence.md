# Reasoning capability 证据交叉复核

- **评审范围**：只读交叉复核 `docs/tmp/260807-resume-review-reasoning-capability-r2.md` 与 `docs/tmp/260807-resume-verify-reasoning-capability.md`，并独立回落到候选 `/home/xp/src/ghc-api-proxy-py-reasoning-capability` 的最终代码、测试、冻结 Spec 与留存 probe 证据。主树固定为 `main@b91e58a29324b11840002efc53ed6f869b800c39`，feature 固定为 `fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。
- **总体 verdict**：**可进入 squash。** 两份报告锁定同一候选 HEAD；R2 code review 的 `0 blocker／0 major` 与独立 verification 的 `PASS` 在 reasoning capability 定向范围内相互一致，且核心断言可由最终代码、测试与独立 probe 证据支持。该 `0 major` 可作为候选 `8bff1c3…` 相对 base `b91e58a…` 进入 squash 的证据。
- **blocker 数**：0。
- **major 数**：0。
- **范围警戒**：本 verdict 只覆盖本报告列出的 reasoning capability、每-attempt 转换与 route 回归合同；**不得外推为完整 Anthropic Responses bridge 已通过、已完成或可整体 squash。**

## 双视角覆盖证据

### 机械核对

- 每次 shell 调用均在同一调用内校验主树 top-level／HEAD 为 `/home/xp/src/ghc-api-proxy-py@b91e58a…`，并校验 feature top-level／HEAD 为 `/home/xp/src/ghc-api-proxy-py-reasoning-capability@8bff1c3…`。候选工作树为 clean；候选差异仅含 `src/app/anthropic/client.py` 与 `tests/smoke/test_anthropic_responses_route.py`，`git diff --check` 无输出。
- 两份被复核报告都写明完整候选 `HEAD=8bff1c3fbd721060a87f18b0ef9d90d7d998a997` 与完整 base `b91e58a29324b11840002efc53ed6f869b800c39`。R2 报告给出 `0 blocker／0 major` 与“可进入 squash”；verify 报告给出 `PASS`，并在结尾再次把结论限定为同一 base→candidate 的 reasoning capability 定向验收。
- 最终实现中，`src/app/anthropic/client.py:281-319` 只在 `reasoning_effort` 唯一、非空且无重复时产生 `selected_effort`；budget limits 必须由 `model_fields_set` 显式同时包含 min／max 字段；adaptive 还必须显式提供且取值为 true。catalog 缺失、model miss、空／重复／multi effort、budget facts 不完整或 adaptive 未显式声明均不会按模型名或 Pydantic 默认值猜测支持。
- Converter 在 `src/app/protocols/anthropic_responses.py:286-349` 对未知 capability、adaptive 无明确 effort、enabled 无明确 budget facts或无 effort band 分别发出稳定 typed error；候选的 extractor 与既有 converter fail-closed 合同闭合。
- `src/app/pipeline/executor.py:225-252` 在每个 attempt 内依次执行 `PRE_SEND`、以当轮 payload 构造 `PreparedAnthropicRequest`、再调用 `send_prepared()`；`src/app/anthropic/client.py:228-245` 随后读取 resolved-model capability facts并执行 Responses request conversion。转换没有被移到 attempt loop 外复用。
- 候选新增 ASGI smoke 覆盖 singleton `enabled／adaptive`、unknown facts、multi-effort 正反排列、闭区间 budget 边界、attempt 0 的 `PRE_SEND` thinking 改写以及双能力默认 Messages，见 `tests/smoke/test_anthropic_responses_route.py:410-582`。
- 独立 probe `/tmp/verify_reasoning_capability_8bff1c3.py` 自证 cwd、loaded module、Git top、Git HEAD 与空工作树；留存结果 `/tmp/verify_reasoning_capability_8bff1c3-r3.json` 的 SHA-256 为 `ffc515eb8dd1548a458628db711f238af487346d6bad7859b43de5e5e19b7b96`，verdict 为 `PASS`，八组结果均为 `PASS`。其中正控实际观察 `200 → 400 reasoning_not_supported → 200`，证明 probe 能命中 capability extraction／gate，而不只是自洽绿灯。
- verify 报告记录的定向 pytest 口径为两个指定测试文件上的 selector：`30 passed, 46 deselected in 2.63s`；R2 报告另引用同 HEAD 的 post-commit 定向 pytest、Ruff 与 Pyright 成功日志。本轮没有把这些数字扩张成全仓测试结果。
- 本轮尝试重新执行独立 probe 与两个相关测试文件时，环境 WIP 审计门因另一个并行 worktree `/home/xp/src/ghc-api-proxy-py-stream-route` 对 `src/app/anthropic/client.py` 存在未提交 overlap 而在执行前拒绝，`AUDIT_RC=1`。该调用没有被记作通过或失败，也没有绕过保护门；本报告采用的是已核对 provenance 的既有 probe／日志、最终代码与精确 diff 证据。

### 第一人称执行模拟

- **Singleton enabled**：resolved model 显式给出唯一 `medium` effort 与 min／max budget facts；边界内请求转换为 `reasoning={"effort":"medium","summary":"auto"}`，并只调用 Responses transport。
- **Singleton adaptive**：除唯一 effort 外还要求 catalog 显式声明 `adaptive_thinking=true`；满足时转换为 `medium`，缺字段或仅依赖默认 false 时 typed fail closed。
- **Unknown／ambiguous**：无 capability、catalog miss、budget facts 缺失、adaptive fact 缺失、空 effort、重复 effort及 multi-effort 都不选择首项或末项。独立 probe 对三元素全部六种排列分别运行 enabled／adaptive，共十二个 case 均在零 upstream 前 typed reject；候选 smoke 另覆盖正反排列，防止顺序回归。
- **Budget 边界**：显式 `[1024,32768]` 按闭区间处理，独立 probe 观察 `1023→400`、`1024→200`、`32768→200`、`32769→400`；越界为 `reasoning_budget_not_supported`。
- **Attempt 转换**：独立 probe 令 attempt 0 的 `PRE_SEND` 把 disabled 改成 enabled、首个 Responses exchange 返回 `429`、retry strategy 再把 canonical payload改回 disabled、attempt 1 的 hook 修改 `max_tokens`。实际两份 wire 分别为“有 `medium` reasoning／`max_output_tokens=200`”与“无 reasoning／`max_output_tokens=201`”，attempt 状态为 `[429,200]`，证明每轮在各自 `PRE_SEND` 后重转换。
- **Route 回归**：双 endpoint、无 override 时仍只调用 Messages，context 为 `protocol_leg=messages`、`route_reason=dual_capability_default`；本 capability 增量没有把双能力模型静默切到 Responses。
- **非 reasoning 请求**：不带 thinking 的 Responses-only 既有 ASGI success flow仍由同一 route／pipeline owner处理；候选增量只向 converter补充 resolved-model capability facts，没有创建第二套 approval、retry、History 或 finalize owner。
- **范围终点**：执行者只能据此接受 reasoning capability 子合同与相关 route／attempt seam。streaming、carrier roundtrip、response assembler、block commit、usage、History projection、cancel／shutdown、完整 headers／errors、真实外部 upstream与全仓回归均未由这两份报告整体验收，不能随本 verdict一并宣告通过。

## 事实性发现

未发现 blocker 或 major。

两份报告的结论并不冲突：R2 的 `0 major` 表示在候选增量代码评审范围内未发现 major；verify 的 `PASS` 表示冻结 Spec 推导的八项 reasoning capability 验收矩阵通过。两者共同支持 `8bff1c3…` 进入 squash，但都没有覆盖完整 bridge。

## Squash 证据裁决

**可以作为 squash 证据。** 精确对象是 `b91e58a29324b11840002efc53ed6f869b800c39..8bff1c3fbd721060a87f18b0ef9d90d7d998a997` 的 reasoning capability 增量：singleton enabled／adaptive、unknown／ambiguous fail closed、budget 闭区间、每-attempt `PRE_SEND` 后重转换及双能力默认 Messages route。证据组合为独立 code review `0 blocker／0 major`、独立 verification `PASS`、最终代码／测试接缝复核、独立 ASGI probe及命中目标机制的正控。

该裁决不授权把“reasoning capability 可 squash”改写为“完整 Anthropic Responses bridge 可 squash／已验收”。完整 bridge 的未验证范围必须继续保持开放。

## 主观建议

无。
