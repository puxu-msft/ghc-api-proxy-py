# Anthropic Messages → Responses request converter 复评 R2

## 结论

- **评审范围**：只读复评 `/home/xp/src/ghc-api-proxy-py-request` 分支 `feat/anthropic-responses-request`，HEAD `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f`，base `ed77c9d191df81c451c25161420515cca52ce6a4`。范围限定为 R1 的四项 major、修复提交自身引入的问题，以及已裁决的 server-tool no-revive 边界；没有重做全仓评审。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **blocker 数**：0。该计数以本报告“事实性发现”中的 blocker 条目和最终汇总交叉核对。
- **major 数**：1。该计数以本报告“事实性发现”中的 major 条目和 R1 处置表的未关闭项交叉核对。
- **squash 判定**：当前**不可明确放行 squash**。R1 的 tool mapper、Node carrier、静态字段合同已经关闭，但 thinking capability API 仍有一项 major；修复并复评为零 major 后可 squash。

## 双视角覆盖证据

### 机械核对

- 同一 shell 调用内反复 gate 了物理 cwd、Git top-level、分支、完整 HEAD、base merge-base；所有 load-bearing 命令均确认运行于指定 request worktree。评审前后目标 worktree 均干净。
- 对账了 R1 报告 `docs/tmp/260806-review-code-request-converter.md` 的四项 major、server-tool 裁决 `docs/tmp/260806-arbitrate-server-tool-contract.md`、正式 `spec.md` 与 `acceptance.md` 的 REQ-04／REQ-05 条款，以及修复提交相对父提交 `cb286059b656d960225c2afff84f204b9123810d` 的最终 diff。
- 逐项读取了最终 `src/app/protocols/anthropic_responses.py`、共享 `src/app/anthropic/thinking/responses_reasoning.py`、模型 capability／Anthropic Pydantic 定义和新增测试。符号搜索确认 `ReasoningCapabilityFacts` 与 `ToolNameMappingFact` 当前是本 converter 切片新提供的 API／事实载体，尚未接入未来 response converter 或 model-catalog adapter；本轮因此只判断该 API 是否足以安全接线，不把尚未实施的完整 bridge 接线误报为本提交回归。
- 定点测试 `tests/unit/test_anthropic_responses_request.py` 与 `tests/unit/test_responses_reasoning.py` 通过；相关源文件与测试的 ruff 通过；定点 pyright 无诊断。测试均禁用了 Python bytecode 与 pytest cache，随后复核目标 worktree 无写入。
- carrier 不是用 Python 自己的 encode／decode 自洽证明。独立调用 Node v24 的 `Buffer.from(payload, "base64url").toString("utf8")` 生成 expected，对固定边界与确定性生成 corpus 做 differential；结果无 mismatch、无 Python 裸异常。另直接读取固定 upstream commit `8d5c861c2e079b92401dd8ccd49695a363d078fe` 的 `synthetic-reasoning.ts` 对账 prefix、宽松 base64url 与 UTF-8 replacement 语义。

### 第一人称执行模拟

- 作为 request caller，分别提交 enabled／adaptive／disabled thinking、缺 capability、超出显式 min／max、未知 thinking type，以及 capability limits 缺失时的负数／零 budget。前述正常和显式边界按预期处理，但后一个缺失事实分支错误产生合法-looking Responses reasoning wire，形成下述 major。
- 作为 response converter 实现者，不持有可变 `ToolNameMapper`，只拿 `ConvertedRequest.tool_name_mapping` 重建逆表；对 identity、链式映射与 cycle 映射逐一恢复，均可无歧义取回原名称。声明、历史 `function_call` 与 forced choice 共享同一次 bind，active collision 在请求发送前拒绝。
- 作为跨轮客户端，向真实 request converter echo 正常、单字符、padding 后垃圾、非 alphabet、非 ASCII 和非法 UTF-8 carrier；输出与固定 Node consumer 一致，并为 non-canonical payload产生 `malformed_reasoning_carrier` fact，不泄漏标准库异常。
- 作为共享模型维护者，模拟顶层 request、message、system 与 tool 增加正式 Pydantic 字段。converter 使用静态 consumed-field 集合与 `model_fields_set ∪ model_extra` 对账，新字段仍稳定 `unsupported_field`，不会因从 `model_extra` 移入正式字段而静默消失。
- 作为既有合同执行者，重放 typed tool declaration 与历史 server-tool block；实现继续返回 `server_tool_not_supported`，没有恢复 web search 白名单或形成 request／response 半支持。

## 事实性发现

[major] `src/app/protocols/anthropic_responses.py:67-100,301-333` — `ReasoningCapabilityFacts` 无法区分“模型目录未提供 budget limit”与“模型明确支持无界 budget”，并允许非正 budget 映射为合法 effort — `min_budget_tokens`／`max_budget_tokens` 都是可选值，`__post_init__` 只检查两者同时存在时是否反转；enabled 路径也只在 bound 非 `None` 时比较。仓库事实源 `src/app/models/capabilities.py:14-18` 同样以 `None` 表示目录字段缺失，因此未来 catalog adapter 最自然的逐字段投影会把“未知”传成 `None`。黑盒探针构造 `supported_efforts=("low",)`、open-ended low band、两侧 limit 均缺失后，`budget_tokens=-1` 与 `budget_tokens=0` 都成功产生 `{"effort":"low","summary":"auto"}`。这违反正式规格“enabled thinking 必须受模型 budget limits 约束”和 capability unknown fail closed，也说明 API 自身没有把无效 Anthropic budget 挡在 Responses wire 前。现有测试只覆盖已知 `min=1024`／`max=32768` 两侧越界，未覆盖缺失 limit 与非正值 — 将“未知”与“明确无界”建模为不同状态；enabled 映射在缺少所需目录事实时返回稳定 capability error，并无条件拒绝非正 budget。建议由 `ReasoningCapabilityFacts.__post_init__` 固化事实一致性，由 `_convert_reasoning()` 固化用户输入约束；补缺 min、缺 max、两侧缺失、零、负数和精确边界测试。若产品确实允许某一侧无界，应使用显式 sentinel／flag 表达，而不是复用 catalog 的 `None=unknown`。

未发现 blocker。除上述 thinking capability API 问题外，未发现新的 major／minor 正确性缺陷。

## R1 四项逐条处置

| R1 项 | R2 判定 | 证据与剩余动作 |
|---|---|---|
| M1 thinking facts／capability API | **未关闭** | enabled／adaptive／disabled 的基本转换和显式 effort／limit gate 已实现，但 optional limit 的 unknown／unbounded 混同与非正 budget fail-open 构成本轮 major。按上述修法补齐后复评。 |
| M2 tool mapper／response 逆映射 facts | **关闭** | `ToolNameMapper.bind()` 收集声明、历史 call 与 forced choice 的 active 名称，拒绝 active 非双射；`ConvertedRequest.tool_name_mapping` 发布 frozen changed-pair facts。response 侧以这些 pairs 建逆表、对未变化名称做 identity fallback，已对 identity、chain、cycle 做独立 fact-only probe。未来接线必须传递该 tuple 或等价 typed fact，不得只保留 request wire。 |
| M3 Node carrier malformed 合同 | **关闭** | `_decode_encrypted_content()` 与固定 Node consumer 的 differential 无 mismatch／裸异常；request converter 保留 Node decode 结果并额外记录 malformed degradation。固定 R1 vectors 与更广 deterministic corpus 均通过。 |
| M4 静态字段合同／模型演进 fail closed | **关闭** | request、message、system、tool 与 content variant 使用独立静态 consumed sets，并按 `model_fields_set ∪ model_extra` 检查显式输入；正式字段演进 probe 稳定拒绝。静态集合与实现重复是本合同有意要求，不应重构回动态 `model_fields` allowlist。 |

## 结构怪味扫描

- `src/app/protocols/anthropic_responses.py:67-100` — **状态表示混同**：optional limits 同时承载 unknown 与 unbounded。**处置：本轮 major，必须修复。**
- `src/app/protocols/anthropic_responses.py:108-146` — **可变 builder 与跨阶段共享的边界风险**：mapper 在 bind 后有内部状态。**处置：保留当前 request-scoped one-shot builder，但跨 request／response 只传 frozen `ToolNameMappingFact` tuple；现有复用拒绝测试守住该边界。**
- `src/app/protocols/anthropic_responses.py:20-50,612-640` — **协议字段集合与 Pydantic schema 重复**。**处置：有意保留。这里的重复正是 fail-closed consumed contract；改回动态 schema 派生会复发 R1 M4。**
- `src/app/anthropic/thinking/responses_reasoning.py:35-62` — **自定义兼容 codec**。**处置：保留标准库实现。其行为目标是 Node 宽松解码而非 RFC 严格解码，已由独立 Node differential 校准；未发现更合适的项目内 helper 或成熟依赖可直接替代该特定语义。**

## 方法反思

- **更好的内部替代方案**：converter 接收预解析 typed facts 而不是自行查 model name 的方向正确；但 capability fact 必须先消除 unknown／unbounded 二义性。tool response 阶段消费 immutable pairs 比共享可变 mapper 更稳，当前 API 已提供所需载体。
- **判据判别力**：tool 使用仅 facts 的独立 response 模拟；carrier 使用 Node 外部 oracle；字段演进使用正式字段子类；thinking 则由缺失 limit 加非正 budget 的反例打破现有绿灯。现有判据因此确实区分出了三项已修与一项未修，而不是统一“测试通过”。
- **成熟第三方方案**：tool bijection 与静态字段对账边界很小，无需新增依赖；carrier 必须复制固定 Node 宽松语义，Python 标准库加 differential fixture 比引入通用 base64 package更符合冻结合同。

## 最终结论

`028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 已关闭 R1 的 tool mapper、Node carrier 与静态字段合同，server-tool no-revive 也保持正确；thinking 的基本 mapping 已加入，但 capability API 仍会在 limit facts 未知时接受非正 budget。**当前为 blocker 0、major 1，不能给出“零 major，可 squash”的结论。修复该 major 并通过同范围复评后，可 squash。**
