# Anthropic Messages → Responses request converter 复评 R3

## 结论

- **评审范围**：严格只读复评 `/home/xp/src/ghc-api-proxy-py-request` 分支 `feat/anthropic-responses-request`，HEAD `fdd2f75fcec11e592b04f2686c4664262052a964`，base `ed77c9d191df81c451c25161420515cca52ce6a4`。只逐条复核 R2 唯一 major，即 `budget limits unknown／unbounded` 混淆与 enabled thinking 非正 budget，并检查 `fdd2f75` 修复自身引入的问题；没有重做 R2 已关闭项。
- **总体 verdict**：**可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：0。
- **squash 判定**：**可以 squash**。R2 唯一 major 已关闭，未发现修复引入的新 blocker、major 或 minor 正确性问题。

## 双视角覆盖证据

### 机械核对

- 每条可信 shell 证据都在同一调用内绑定并验证绝对 cwd、Git top-level、分支、完整 HEAD、base ancestor 与工作树状态；评审前后目标 request worktree 均干净。对不含本轮唯一 nonce 的共享终端串扰输出一律作废，未纳入结论。
- 对账了 R2 报告 `docs/tmp/260806-review-code-request-r2.md` 的唯一 major、`fdd2f75` 相对父提交的完整聚焦 diff、最终 `src/app/protocols/anthropic_responses.py` 与 `tests/unit/test_anthropic_responses_request.py`。
- 仓库级构造点扫描确认 `ReasoningCapabilityFacts` 只在该实现和聚焦测试中出现；新增 `budget_limits_known` 没有默认值，现有构造点均已显式传值，因此不会把“未知”静默解释成“明确无界”。
- `tests/unit/test_anthropic_responses_request.py` 聚焦测试通过：pytest 原生输出为 `collected 51 items`、`51 passed in 1.35s`。运行时禁用了 Python bytecode 与 pytest cache，测试后工作树仍干净。
- 修复涉及的实现与测试通过 ruff；定点 pyright 输出 `0 errors, 0 warnings, 0 informations`；静态检查后工作树仍干净。

### 第一人称执行模拟

- 作为 capability adapter 调用者，故意省略新增字段构造 `ReasoningCapabilityFacts`；构造立即以缺少 `budget_limits_known` 的 `TypeError` 失败，证明该状态不会因默认值而悄然落入旧语义。
- 作为 enabled thinking caller，独立黑盒负边界覆盖缺失 budget、`False`、`True`、`0`、`-1`、浮点数和字符串；7 项均稳定返回 `invalid_thinking`／`thinking.budget_tokens`，不会被 capability 缺失或 unknown 状态掩盖。
- 作为 catalog adapter，分别提供 `budget_limits_known=False` 且 limits 为双缺失、仅 min、仅 max、双侧都有值；4 项均稳定返回 `reasoning_not_supported`／`thinking`，证明 unknown flag 优先于 optional limit 数值并 fail closed。
- 从相反方向模拟正确调用：`budget_limits_known=True` 且 min／max 双侧显式无界的 enabled 请求成功映射；`budget_limits_known=False` 的 adaptive 请求仍按 `adaptive_effort` 成功映射。新 gate 没有把明确无界误判成未知，也没有误伤不依赖 enabled budget limits 的 adaptive 路径。
- 现有测试另覆盖单侧显式无界、精确 min／max 边界和界外值，正反样本共同验证新判据既不会 false-green，也不会 false-red。

## 事实性发现

未发现问题。

R2 唯一 major 已关闭：

- `src/app/protocols/anthropic_responses.py:67-73` 将 `budget_limits_known` 建模为无默认值的必填事实，`None` 因而只在该 flag 明确为 `True` 时表示该侧显式无界。
- `src/app/protocols/anthropic_responses.py:272-287` 在 capability lookup 前无条件要求 enabled `budget_tokens` 为非布尔的正整数，关闭了零、负数及 Python `bool` 作为 `int` 子类的旁路。
- `src/app/protocols/anthropic_responses.py:317-322` 在 enabled 映射前检查 `budget_limits_known`，unknown 状态无论 optional limits 当前装载了哪些值都 fail closed。
- `tests/unit/test_anthropic_responses_request.py:310-449` 增加非正 budget、unknown limits、显式 unbounded 与精确边界回归样本，覆盖 R2 指定的缺 min、缺 max、双缺失、零、负数和边界行为。

未发现 blocker；未发现修复引入的新 major 或 minor。

## 结构怪味扫描

- `src/app/protocols/anthropic_responses.py:67-73` — **多个字段共同表达一个状态空间**：`budget_limits_known` 与两个 optional limits 需要调用者保持语义一致。**处置：本轮保留。** 必填 flag 已消除 R2 的 silent default，converter 又以 flag 为 enabled fail-closed 的唯一判据；当前不存在可复现的错误状态穿透。后续若 capability API 扩展，可考虑用 tagged union／专用 limits value object 让 unknown 与 known-unbounded 在类型层彻底互斥，但这不是本轮 squash 阻断项。
- `src/app/protocols/anthropic_responses.py:272-342` — **输入合法性与 capability 策略在同一方法内串行处理**。**处置：本轮保留。** 当前顺序是有意合同：先拒绝调用者无效输入，再检查模型能力，错误分类已由边界探针验证；此时拆 helper 只改变结构，不改善本轮正确性。

## 方法反思

- **更好的内部替代方案**：长期最强类型方案是把 unknown、known-bounded、known-left-unbounded、known-right-unbounded、known-unbounded 表达为互斥 tagged states，而不是布尔值加 optional 字段。不过当前必填 flag 已满足 R2 明确修复目标，且 fail-closed 行为有独立黑盒证据；不应把未来类型重构误报为当前 major。
- **判据判别力**：负向验证不仅覆盖 `None`，还覆盖“flag 为 unknown 但 limits 看似齐全”的矛盾输入；正向验证覆盖 explicit unbounded 和 adaptive，能够同时区分错误状态应拒绝与正确状态应通过。共享终端中缺少唯一 nonce 的输出被主动丢弃，避免“命令看似运行”造成假证据。
- **成熟第三方方案**：该修复是小型 immutable capability value object 与顺序校验，不存在引入第三方依赖能提升正确性的明确收益；Python dataclass 与现有类型检查足够表达当前合同。

## 最终结论

`fdd2f75fcec11e592b04f2686c4664262052a964` 已将 unknown 与 explicit unbounded 分离为调用者必须明确提供的事实，并在 capability lookup 前拒绝 enabled thinking 的非正及非整数 budget。聚焦测试、独立正负边界探针、ruff 和 pyright 均通过，目标 request worktree 评审后保持干净。

**最终为 blocker 0、major 0；明确可以 squash。**
