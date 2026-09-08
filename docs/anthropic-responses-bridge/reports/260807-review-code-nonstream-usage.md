# Non-stream usage details 独立代码评审

- **评审范围**：只读评审 `/home/xp/src/ghc-api-proxy-py-nonstream-usage` 的 `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857`，相对 happy integration base `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 的单提交 `fix: preserve nonstream usage details`。范围仅含 `ResponseUsageFacts`、non-stream usage 转换及对应 unit／smoke 测试；不重新评审完整 bridge、stream parity、History consumer 或后续集成接线。
- **总体 verdict**：**可进入下一阶段；该切片可 squash。**
- **blocker 数**：0。机械代码／契约对账与第一人称运行时反例两种独立路径均未发现核心目标失败。
- **major 数**：0。按本轮明确口径，仅统计会阻止该小边界切片 squash 的 major；静态全引用扫描、Spec 公式对账、运行时反例、全量质量门与错误算式变异控制交叉核验后均未发现此级别问题。

## 双视角覆盖证据

### 机械核对视角

- 每次目标 shell gate 均核对 physical root、branch、HEAD、base ancestry 和 clean worktree；目标树在所有只读检查与测试前后保持 clean。提交范围仅修改 `src/app/protocols/responses_anthropic.py`、`tests/unit/test_responses_anthropic_nonstream.py` 与 `tests/smoke/test_anthropic_responses_happy_path.py`，`git diff --check` 通过。
- 对照 current Spec `docs/agents/anthropic-responses-bridge/spec.md:361-379`：实现于 `src/app/protocols/responses_anthropic.py:224-284` 使用 `I=max(0,T-R-W)`，normalized total 为 `I+R+W+O`，`Q` 仅保留为 detail／diagnostic fact，未二次计入 output 或 total；cache、reasoning 与 upstream total 的不一致分别在 `src/app/protocols/responses_anthropic.py:237-258` 形成 typed `usage_inconsistent` fact。
- `ResponseUsageFacts` 在 `src/app/protocols/responses_anthropic.py:28-52` 使用 frozen／slotted dataclass，并在构造时复制详情映射后包装 `MappingProxyType`，因此既不受调用方原字典后续突变影响，也不允许经公开 mapping 引用改写。
- 全目标树引用扫描确认 `usage_facts` 只存在于 converter 返回对象与测试；wire 仍由 `src/app/protocols/responses_anthropic.py:125-140` 的 `converted_usage.wire` 提供，`AnthropicUsage` 未新增 reasoning 或 details 字段。独立 `MessagesResponse.model_dump(mode="json")` 探针确认 wire 只有既有 Anthropic usage 字段，不含 `usage_facts`、`reasoning_tokens`、`input_tokens_details` 或 `output_tokens_details`。
- 缺失 usage 在 `src/app/protocols/responses_anthropic.py:214-220` 返回 wire 零值、`usage_facts=None` 与 `usage_estimated` fact；details 中任意未来字段均经过非负整数验证并 value-exact 保存在 typed facts，malformed bool、负数与非整数走 `invalid_usage` typed error。
- 声明范围测试通过；全量 `pytest -p no:cacheprovider -q tests` 通过，`ruff check src tests` 通过，`pyright --pythonpath <project-python> src tests` 返回 `0 errors, 0 warnings, 0 informations`。执行时设置 `PYTHONDONTWRITEBYTECODE=1`，并在结束后复核目标树 clean。

### 第一人称执行视角

- 模拟一致向量 `T=100,R=20,W=10,O=30,Q=12`：得到 Anthropic wire `input=70`、cache read／write `20／10`、output `30`，typed total 为 `130`，future modality／prediction details 保留，`Q` 不重复相加。
- 模拟不一致向量 `T=5,R=4,W=3,O=5,Q=7,upstream_total=999`：得到非负 wire input `0`、normalized total `12`，同时 value-exact 保留 upstream input／total／reasoning，并产生 cache、reasoning、upstream total 三类 inconsistency facts；未静默修正 upstream 值。
- 模拟 facts 构造后的源字典突变、通过 mapping 写入、通过 dataclass 字段赋值：源字典突变不影响快照，后两者分别以 `TypeError`／`FrozenInstanceError` 被拒绝。
- 模拟 usage 完全缺失、未来 detail、malformed detail 与最终 message JSON 序列化：缺失值不会伪装成 upstream exact facts，未来 details 留在内部 typed facts，malformed 值显式失败，内部 details 不进入 Anthropic wire。
- 在内存中将正确结果变异为 `total_tokens += reasoning_tokens`，直接执行现有基础 usage 公式测试；测试按目标机制变红，证明其能拦截 reasoning 二次计数，而非仅对当前实现同源放行。

## 事实性发现

未发现会阻止该切片 squash 的 major。

## 结构与边界复核

- **扫描范围与判据**：`src/app/protocols/responses_anthropic.py:28-284` 及其全目标树引用；检查重复 usage 算式、typed facts／wire 职责错位、可变别名、公共 `AnthropicUsage` 扩张、future details 静默丢失与同源测试假绿。
- **处置**：本轮未发现需要作为 squash blocker 处理的结构怪味。`ResponseUsageFacts` 承载精确／诊断事实，`AnthropicUsage` 继续只承载下游 wire，两者职责边界清楚；测试同时覆盖 wire 与 typed facts，并由独立运行时探针和错误算式变异补强判别力。

## 结论边界

本 verdict 只放行 `aca3ced6e38efabf13ffe43d5935697801c74857` 相对 `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 的声明范围 squash，不表示完整 Anthropic Responses bridge、stream／non-stream usage parity、History 持久化或最终产品验收已经完成。
