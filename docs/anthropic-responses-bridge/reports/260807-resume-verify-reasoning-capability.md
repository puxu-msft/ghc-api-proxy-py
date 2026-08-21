# Reasoning capability 独立验收报告

## 判定

**PASS**。

候选 `/home/xp/src/ghc-api-proxy-py-reasoning-capability` 的精确 `HEAD=8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，相对精确 `base=b91e58a29324b11840002efc53ed6f869b800c39`，满足本次从冻结 Spec 独立推导的 reasoning capability 合同：singleton effort 下 `enabled`／`adaptive` 成功；multi-effort 的所有三元素排列均 typed reject；未知或不完整 capability facts fail closed；budget 上下界为闭区间；两次 attempt 均在各自 `PRE_SEND` 后重新转换；双能力模型无 override 时继续选择 Messages。

本判定严格限于上述能力合同，不外推完整 Anthropic Responses bridge，不代表 stream、carrier、response conversion、usage、History 或其他 bridge 合同已整体验收。

## Oracle 与执行边界

- 唯一行为 oracle：候选树 `docs/agents/anthropic-responses-bridge/spec.md`，本次文件 SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。该值分别用系统 `sha256sum` 与 Python `hashlib.sha256` 计算，结果一致。
- Spec 锚点：双能力默认 Messages 位于 `spec.md:78`；每 attempt 的 `PRE_SEND` 后转换位于 `spec.md:110`；reasoning effort 与 budget facts gate 位于 `spec.md:203`；retry 后重跑 `PRE_SEND` 并重新转换位于 `spec.md:340`；外部验收行为位于 `spec.md:522-523`。
- 候选 provenance：独立 Python probe 在进程内记录 `cwd=/home/xp/src/ghc-api-proxy-py-reasoning-capability`、`git_top=/home/xp/src/ghc-api-proxy-py-reasoning-capability`、`git_head=8bff1c3fbd721060a87f18b0ef9d90d7d998a997`、实际加载模块 `/home/xp/src/ghc-api-proxy-py-reasoning-capability/src/app/anthropic/client.py`，且 `git_status_porcelain` 为空。
- Probe 使用真实 FastAPI／ASGI 应用入口 `/v1/messages`、真实 pipeline、hook executor、retry coordinator、request converter 与 route policy；upstream transport 使用内存 recording target，不发外部网络请求。
- 独立 probe 放在 `/tmp/verify_reasoning_capability_8bff1c3.py`，结果放在 `/tmp/verify_reasoning_capability_8bff1c3-r3.json`，未写候选树。结果 JSON SHA-256 为 `ffc515eb8dd1548a458628db711f238af487346d6bad7859b43de5e5e19b7b96`，分别用系统 `sha256sum` 与 Python `hashlib.sha256` 计算，结果一致。

## 从 Spec 推导的验收矩阵与实证

| 验收项 | 独立判据 | 实际结果 |
|---|---|---|
| Singleton `enabled` 成功 | 模型明确提供唯一 `reasoning_effort=["medium"]`、明确 budget limits；`enabled` 请求应只走 Responses，并产生明确 wire effort | ASGI 返回 `200`；零 Messages 调用、一次 Responses 调用；wire `reasoning={"effort":"medium","summary":"auto"}` |
| Singleton `adaptive` 成功 | 模型还明确提供 `adaptive_thinking=true`；`adaptive` 应映射到唯一明确 effort | ASGI 返回 `200`；wire reasoning 与上项相同 |
| Multi-effort 排列无关 typed reject | 对 `low／medium／high` 的全部六种排列，分别发送 `enabled` 与 `adaptive`；不得因首元素或排列改变而猜测 effort | 共十二个 ASGI case 全部在零 upstream 调用前返回 `400`；`enabled` 固定 `reasoning_budget_not_supported`，`adaptive` 固定 `reasoning_not_supported` |
| Unknown facts fail closed | capability 缺失、budget limits 缺失、adaptive fact 缺失、重复 effort、空 effort 均不得靠模型名或 heuristic 猜测 | 五种 ASGI case 均返回 `400 reasoning_not_supported`，且 Messages／Responses 调用数均为零 |
| Budget 上下界 | 对明确 `[1024,32768]` 闭区间测试下界外、下界、上界、上界外 | `1023→400`、`1024→200`、`32768→200`、`32769→400`；两个越界 case 均为 `reasoning_budget_not_supported`，两个边界 case 均映射 `medium` |
| 组件 typed contract | 绕过 ASGI，直接调用 request converter，确认 success wire 与歧义 error code | Singleton `enabled`／`adaptive` 均得到 `medium`；multi-effort 的 `enabled`／`adaptive` 分别抛出 `reasoning_budget_not_supported`／`reasoning_not_supported` |
| 两 attempt 的 `PRE_SEND` 后重转换 | 真实 ASGI 流程令 attempt 0 的 `PRE_SEND` 把 disabled 改成 enabled budget `1024` 与 `max_tokens=200`；首个 Responses exchange 返回 `429`，retry strategy 再把 canonical payload 改回 disabled；attempt 1 的 `PRE_SEND` 设置 `max_tokens=201` | 实际产生两个 Responses exchange，attempt status 为 `[429,200]`；第一份 wire 有 `reasoning=medium` 且 `max_output_tokens=200`，第二份 wire 无 reasoning 且 `max_output_tokens=201`；两个 hook context 的 attempt number 分别为 `0`、`1`，证明没有复用 loop 外陈旧 Responses payload |
| 双能力 route 不回归 | 模型同时明确支持 `/v1/messages` 与 `/responses`，无 override | ASGI 返回 `200`；一次 Messages 调用、零 Responses 调用；context 为 `protocol_leg=messages`、`route_reason=dual_capability_default` |
| 目标正控 | 临时 monkeypatch `AnthropicClient._reasoning_capabilities()` 返回未知 facts，必须让 singleton enabled 成功 probe 转红；退出 patch 后必须复绿 | baseline `200` → mutation `400 reasoning_not_supported` → restore `200`；正控命中目标 capability extraction／gate 机制，且没有修改生产文件 |

## 实际运行记录

1. 独立 ASGI／组件／retry／正控 probe：在 `.venv` Python、`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-reasoning-capability/src`、`PYTHONDONTWRITEBYTECODE=1` 下运行 `/tmp/verify_reasoning_capability_8bff1c3.py`。最终 `r3` JSON 自证精确 cwd、加载模块、Git top、Git HEAD 与空工作树，verdict 为 `PASS`，上述全部八组结果均为 `PASS`。
2. 候选自带定向回归：运行 `tests/smoke/test_anthropic_responses_route.py` 与 `tests/unit/test_anthropic_responses_request.py` 的 reasoning／effort／dual-capability selector，并禁用 pytest cache。结果为 `30 passed, 46 deselected in 2.63s`，退出码 `0`。该数字的口径仅为这两个文件在指定 selector 下的本次运行，不代表全仓测试数。
3. 候选只读校验：probe 前后 `git status --porcelain=v1 -z` 的 SHA-256 均为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，即空输出的哈希；候选树保持干净。
4. 终端证据处置：两次并行终端回显出现与本任务不相干的其他工作树输出，均因缺少本任务 provenance 标记而废弃，未用于判定。最终只采用带进程内 provenance 的 `r3` JSON、绝对路径读取结果及随后精确 HEAD 的定向 pytest 结果。

## 实现接缝核对

行为实证通过后再核对实现接缝：`src/app/anthropic/client.py:281-318` 从 resolved model 的结构化 capability facts 构造 reasoning facts，仅在 effort 集合恰好有一个明确值时选择 effort；`src/app/pipeline/executor.py:225-252` 在 attempt loop 内运行 `PRE_SEND`，构造当前 attempt 的 prepared request，再调用 `send_prepared()`；request conversion 位于 `src/app/anthropic/client.py:232`。这些位置与 probe 观察到的两份不同 wire payload一致。

## 缺陷与未验证项

- 本次范围内没有发现违反 Spec 的缺陷，因此没有失败复现或修复路由建议。
- 未验证完整 bridge；尤其未覆盖 streaming、carrier roundtrip、response assembler、block commit、usage、History projection、cancel／shutdown、完整 headers／errors 及全仓回归。它们既不计为通过，也不计为本次缺陷。
- 未连接真实外部 upstream；本次“真实 ASGI”指真实应用路由与内部组件链，transport counterpart 为确定性的 recording target。

## 最终结论

候选 `8bff1c3fbd721060a87f18b0ef9d90d7d998a997` 对 base `b91e58a29324b11840002efc53ed6f869b800c39` 的 reasoning capability 定向验收为 **PASS**。结论只覆盖本报告验收矩阵，不得转述为完整 Anthropic Responses bridge 已通过。
