# 提交 `e12411b` 代码评审：request log 着色

## 结论

**Verdict：needs-fix。** 本次发现 2 条 major、2 条 minor。两条 major 分别是字节量级的显示值与颜色边界不一致，以及实现者未经用户裁决便把部分终结状态改为黄色并将该选择写成“已裁决”。其余核心机制，包括纯文本兼容、ANSI span、工具列表分段和词元边界，未发现实现缺陷。

本报告只评审提交 `e12411b` 在以下四个文件中的内容：`src/app/observability/request_log.py`、`src/app/observability/terminal.py`、`tests/unit/test_request_log.py`、`docs/agents/tui-request-log/SPEC.md`。工作树中的并行改动不在范围内，也未把已知的 footer 测试失败或 `server_tools.py` 类型错误计入结论。

## Findings

### F1（major）：字节颜色在两个临界点附近与打印出来的量级不一致

**位置：** `src/app/observability/request_log.py` 第 37～39、278～284 行；`src/app/observability/terminal.py` 第 47～58 行；`docs/agents/tui-request-log/SPEC.md` 第 73 行；`tests/unit/test_request_log.py` 第 356～364 行。

实现按原始字节数采用半开区间：`<10 * 1024` 为灰，`[10 * 1024, 100 * 1024)` 为白，`>=100 * 1024` 为黄。因此，`10 * 1024` 恰好应为白，`100 * 1024` 恰好应为黄；这个边界解释本身与 Spec 表格一致，也符合“以临界点进入下一档”的通常理解。

问题在于 `format_bytes` 只打印一位小数并采用四舍五入。实测 `10_189`～`10_239` 字节已经显示为 `10.0KB`，却仍是灰色；`102_349`～`102_399` 字节已经显示为 `100.0KB`，却仍是白色。具体正样本为：`10_239 -> 10.0KB + DIM`、`10_240 -> 10.0KB + WHITE`、`102_399 -> 100.0KB + WHITE`、`102_400 -> 100.0KB + YELLOW`。因此，同一个可见数字会因被隐藏的原始字节差异呈现两种颜色。

这直接推翻了源码注释“颜色与打印数字在同一行跨过 `10.0KB`”以及 Spec“与 `format_bytes` 打印的数字同时变色”的事实主张，也不满足本次明确要求核对的“阈值与打印出来的数字一致”。判断强度为**足以据此阻止通过**，依据是对提交代码的直接边界探针，而不是对文案的主观解释。

修复前需要把三个同时存在的约束对清楚：原始阈值确实是 `10 * 1024`／`100 * 1024`、彩色显示的数字不能跨档后仍保留上一档颜色、`color=False` 又必须逐字节保持旧输出。我的偏好是保留精确的 1024 进制原始阈值，并只在彩色呈现的临界舍入带内增加足够精度，使临界点下方仍可见为 `<10KB`／`<100KB`；纯文本路径继续使用旧 formatter。另一可选方案是按已经四舍五入的显示值着色，但那会把实际阈值提前约 51 字节，不再严格是 `10 * 1024`／`100 * 1024`，不应由实现者静默选择。

### F2（major）：两档终结状态是合理提案，但属于未经裁决的可观察行为偏离

**位置：** `src/app/observability/request_log.py` 第 41～44、132～143 行；`docs/agents/tui-request-log/SPEC.md` 第 66、78、86 行；`tests/unit/test_request_log.py` 第 388～398 行。

用户原要求是“`end_turn` 等终结状态显示为绿色”。当前实现却把 `end_turn`／`stop_sequence` 设为绿色，把同样终结本轮回复的 `max_tokens`／`refusal` 设为黄色。代码和测试明确固化了这个偏离，而同一个提交还把 Spec 写成“裁决于 2026-08-20”，但现有用户要求没有裁决这项扩展。

实现者给出的产品理由有实质价值：`max_tokens` 表示输出被截断，黄色比绿色更能提醒读者；`refusal` 虽不等同于截断，也通常值得注意。**我的产品偏好是赞成保留“正常收尾绿、受限或拒绝黄、工具调用原因本身不着色”这套两档语义。** 但是，这个偏好不能把显式需求自动改写成授权，尤其不能由实现者把自己的选择记成“已裁决”。判断强度为**足以据此阻止通过，直到用户明确裁决**；依据是可观察颜色契约与用户原话直接不一致，而不是代码质量问题。

更好的处理方式有两种。若先按当前明确需求交付，应把所有已认定的终结状态显示为绿色，并把两档方案作为待裁决提案记录；若用户认可这里的语义改进，则可以保留当前映射，但必须把 Spec 的“裁决”建立在用户明确决定上，并把理由写准确：`max_tokens` 是截断，`refusal` 是需要注意的非正常答复，两者不应统称为“回复被截断”。此外，Spec 应明确“等”是封闭枚举还是类别规则，否则未知终结原因会因当前白名单实现而静默不着色。

### F3（minor）：字节阈值测试无法识别灰色到白色这一档完全失效

**位置：** `tests/unit/test_request_log.py` 第 349～364 行。

`_received()` 总是设置 `duration_s=1.0`，而耗时字段本身必定带有 `WHITE`。所以第 362、363 行的 `assert WHITE in _received(...)` 即使下行字节仍被错误地染成 `DIM` 也会通过。内存内受控变异已证实：把所有 `<100KB` 的下行字节都强制设成灰色、完全删除 10KB 的灰→白转换后，`test_what_came_back_escalates_with_its_size` 仍然保持绿色。

该测试仍能识别 100KB 的白→黄边界，因为该样本里没有其它黄色 span；词元测试也有区分力，因为其样本没有无关的白色 span。问题只在字节的第一道边界。判断强度为**足以要求补强当前切片测试，但不是独立的运行时 major**，依据是已执行的变异正样本。

建议直接断言完整目标 span，例如 `f"{WHITE}↓10.0KB{RESET}"`，或让样本省略会产生白色 span 的耗时字段。断言应同时绑定方向符号、打印数字和 ANSI code，这也会抓住 F1 的显示／颜色不一致。

### F4（minor）：新增说明混淆“回复结束”与“工作流继续”，并对其它工具作了无依据的绝对断言

**位置：** `src/app/observability/request_log.py` 第 41～47、126～132、148～152 行；`docs/agents/tui-request-log/SPEC.md` 第 86～87 行；`tests/unit/test_request_log.py` 第 401～402 行。

同一个 docstring 先说 `tool_use` 表示“turn ended in tool calls”，随后又说它是“a turn that has not ended”；Spec 则写成“这一轮还在继续”。这两句话只有在分别指“当前模型回复已经结束”和“工具驱动的 agent 工作流仍会继续”时才能同时成立，当前文本没有区分层级。

另外，“列表里其它每一项都会自行了结”“Every other entry resolves on its own”不是由任何类型或契约保证的事实。工具名是任意字符串，其它工具同样可能等待审批、外部事件或人工输入。可靠且足以支撑当前颜色规则的事实只是：名为 `AskUserQuestion` 的工具明确表达了需要用户回答，因此值得从默认灰色列表中挑出。

判断强度为**应修正文档和注释，但不影响现有运行行为**。建议改写为：“`tool_use` 终止当前模型回复，但通常表示 agent 工作流会在工具结果后继续；`AskUserQuestion` 明确请求人的输入，因此单独显示为青色。”不要对所有其它任意工具的完成方式作绝对承诺。

## 已核对且不构成发现的事项

1. `_painted_tools` 的分段算法在空列表、单元素、全部同色、交替颜色、重复 `AskUserQuestion`、空名字过滤和名字内含逗号的样本上均保持正确边界。名字内的逗号留在该名字自己的 span 中；不同颜色 run 之间的分隔逗号使用默认颜色，但它不是工具名，不违反“普通工具名灰、`AskUserQuestion` 青”的契约。
2. 新增 ANSI span 没有嵌套。结束原因的 reset 在括号之前完成，工具 run 各自 reset，括号始终在 span 外；这与 `paint()` 的 self-contained span docstring 一致。
3. `color=False` 的行为与父提交逐字节一致。通过动态加载 `e12411b^` 的旧 formatter，并对 stop reason、工具列表、dialect、字节边界、usage、Unicode／ASCII、重试和 detail 的组合样本逐项比较，全部相同。名字内含逗号的旧有无转义表示也被保留；本次不建议顺手改变它，因为那会破坏明确的纯文本兼容契约。
4. 词元边界使用 1000 进制并采用正确半开区间：`999` 灰、`1_000` 白、`9_999` 白、`10_000` 黄。对应测试没有无关颜色造成的假绿。
5. 结束原因绿／黄互换会被精确字符串断言抓住；`AskUserQuestion` 精确匹配失效也会因缺少完整 cyan span 而被抓住。这两类测试不是与实现同源的自证。
6. Spec 着色表除 F1 的“同时变色”和 F2 的未经裁决映射外，与代码逐项相符。新增中文段落未发现半角中文标点或句中硬折行问题。
7. 本次不建议把上行量级也升级颜色。它不在用户要求内，且会削弱下行大小这个信号；当前恒灰实现与 Spec 一致。
8. 本次不建议因“名字含逗号”新增转义协议。逗号歧义是提交前已有的纯文本格式特性，新着色逻辑没有放大或误解析它，改变它反而会违反 `color=False` 的逐字节兼容要求。
9. 本次不建议否定两档终结状态的产品思路。问题是未经裁决便改变需求和写成“已裁决”，不是黄色方案本身缺乏价值。

## 验证记录

- `git diff e12411b -- <四个目标文件>`：退出码 0，确认当前工作树中的四个目标文件与提交对象一致。
- `git diff e12411b^ e12411b --check -- <四个目标文件>`：通过。
- `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/unit/test_request_log.py`：37 passed。
- `uv run ruff check --no-cache src/app/observability/request_log.py src/app/observability/terminal.py tests/unit/test_request_log.py`：All checks passed。
- `PYTHONDONTWRITEBYTECODE=1 uv run pyright src/app/observability/request_log.py src/app/observability/terminal.py tests/unit/test_request_log.py`：0 errors、0 warnings、0 informations。
- 边界／ANSI 探针：确认上述四个舍入带样本，确认所有工具列表样本均为非嵌套 span。
- 父提交纯文本对比探针：通过。
- 字节灰→白转换受控变异探针：目标测试错误地保持绿色，形成 F3 的直接证据。

未运行全量测试和项目级 Pyright；用户已明确指出并行工作树中存在与本提交无关的已知失败，本次采用仅覆盖评审对象的定向验证，避免把同伴在飞改动误计入结论。

## 技能可用性说明

用户指定的 `my-skills:as-reviewer` 在本运行时未注册，调用返回 `Unknown skill: my-skills:as-reviewer`。本评审因此按同等的只读、提交对象优先、发现先行流程执行；该工具缺失不影响以上源码、测试和动态探针证据。


---

## 后续裁决（2026-08-20，派发方补记）

**F1 的修复已被用户推翻，回退。**

我最初按「按显示出来的数字着色」处理，使阈值实际前移约 51 字节（10.0KB 从 10240 变 10189），理由是「屏幕上不可能自相矛盾」。用户裁定：

> 你过于纠结「换来屏幕上不可能自相矛盾」了，按实际情况处理即可，不必移动阈值，用户接受按他要求的着色。

因此阈值恢复为 `10 * 1024` / `100 * 1024` 与 1000 / 10000 这几个整数；`shown_magnitude` helper 与 `test_the_same_number_is_never_shown_in_two_colours` 一并删除。**F1 描述的现象仍然存在且现在是已接受行为**：10239 与 10240 字节都显示 `10.0KB`，一灰一白。`SPEC.md` 已把它写成明示的接受项，而不是继续声称「颜色与打印数字同时变化」——评审指出的**文案与事实不符**这一点是成立的，只是正确的修法是改文案，不是改阈值。

F1 附带的两项改进**保留**：断言完整 span（marker + 数字 + ANSI code），以及从样本中去掉会产生无关白色 span 的耗时字段。这两项与阈值取值无关，且已用变异证明能抓住评审演示的那类退化。

F3、F4 采纳，无变化。F2 由用户于同日裁决（`max_tokens` 黄、`refusal` 红）而消解。
