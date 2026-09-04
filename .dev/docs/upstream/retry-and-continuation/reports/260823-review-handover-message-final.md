# hand-over `message` 最终确认复核

- 评审对象：`e2cb70b87d5028d15839061dfa9bdc5ab2d68838`、`96452937cc4b9125e53075a0f951f6802f2ba80d`
- 当前实现锚点：`9645293`；已确认 `9645293..HEAD` 未改动 `src/app/pipeline/hand_over.py`、`tests/unit/pipeline/test_hand_over_message.py`、`tests/int/test_pipeline_app.py`
- 日期：2026-08-23
- Verdict：**needs-fix**
- 计数：blocker 0，major 0，minor 2，nit 0

## 结论

前两轮的两个 major 均已闭合：error 分支的真实入口测试现在能击穿手搓 type/text formatter，并把 message 中的随机 request id 与独立日志值交叉核对；跨仓权威 README 已按 `e2cb70b` 重写、给出同步锚点，当前九条输出与代码相符。F3、F4、F5、M2、m2 均完整闭合；截断 marker 的 5/6/7 层与循环边界也仍正确。

本轮没有 blocker 或 major，但不能给 `pass`：一是同一生产接线的非错误分支仍可恢复成旧的裸 `stop_reason` 而所有直接相关测试保持全绿；二是 m1 为消除 deadline 的 `CancelledError` 噪声而采用的全局规则，会在“outer 已有文本、inner 只有独特类型”时重新吞掉真正唯一的 cause 线索。这两项都属于当前任务已经宣称覆盖的 message 契约，不宜留作无记录的取舍。

证据权重：两条 finding 都由精确提交副本或当前实现上的构造反例直接复现，足以据此修复；第二条未在支撑调查中观测到生产实例，因此定 minor 而非 major。

## Findings

### m1 — [minor] error 接线已被有效守住，但非错误 `stop_reason` 分支仍可退回旧值而全部相关测试保持全绿

**已闭合的部分。** `tests/int/test_pipeline_app.py:3200-3209` 现在构造当前 httpcore2→httpx2 的 GOAWAY cause 链；`:3229-3236` 断言 outer type、从内层 event 解出的 `NO_ERROR`，并将 message 内 request id 与 `auto_retry_tool_not_declared` 日志中的随机值交叉核对。我在 `9645293` 的隔离副本中把接线换回复评使用的手搓 formatter，目标集成测试按预期在 `assert "NO_ERROR" in message` 变红。M1 针对 error 路径的判据已具备鉴别力。

**仍未覆盖的同一接线分支。** `interruption_message` 的 `error is None` 分支把原来的裸 `max_tokens` 改成完整代理诊断；单测 `test_a_turn_cut_short_says_more_than_its_category` 直接测试 helper，但真实入口 `test_a_turn_that_ran_out_of_room_is_handed_back_the_same_way` 只断言 `category == "max_tokens"`，完全不看 `input.message`。

我从 `9645293` 建立 `/tmp/handover-final-review-8dy8E9`，基线运行 21 条 unit、error 入口 integration、max-tokens 入口 integration，共 `23 passed in 3.64s`。随后只把生产接线改成：

```python
detail = (
    stop_reason
    if error is None
    else interruption_message(
        error=error,
        stop_reason=stop_reason,
        request_id=request_id,
        attempt_count=context.attempt_count,
    )
)
```

运行前以 `__file__` 与 `inspect.getsource` 确认加载的是变异文件；同一组测试仍为 `23 passed in 3.22s`。这会让 max-tokens 客户端重新收到裸 `max_tokens`，丢掉完整解释、request id 与 attempt，而 error 分支的新强断言当然全部满足。

**严重度依据。** 主诉中的 error 路径已经闭合，遗漏只影响本次顺带增强的 non-error 分支，因此降为 minor；但它与前两轮 F1/M1 是同一种真实入口接线盲区，不是要求任意测试抵御恶意特判。

**建议。** 直接加强现有 `test_a_turn_that_ran_out_of_room_is_handed_back_the_same_way`：从 `_handed_back(delivered)` 取 `input.message`，至少断言它不等于 `max_tokens`、包含 `stop_reason=max_tokens` 与 `attempt 1`；若该路径也有独立 request-id 观测点，再与之交叉核对。无需新增夹具或证明基础设施。

### m2 — [minor] “已有任意文本就丢掉所有后续空文本类型”会再次吞掉真正唯一的 cause 线索

**已闭合的部分。** 新三分支规则正确消除了两个已观测 deadline 形状中的 `builtins.TimeoutError`／`asyncio.exceptions.CancelledError`，同时保留真实 reset 在首个有文本 OSError 之前的 `httpx2.ReadError` 与 `anyio.BrokenResourceError`。新增参数化测试使用全限定名，避免 `StreamIdleTimeoutError` 子串造成假绿；这部分判据准确。

**新反例。** `src/app/pipeline/hand_over.py:155-161` 在 `carried_text=True` 后无条件丢弃所有空文本 link，即使其 class 是此前从未出现、也是该 link 唯一能贡献的线索。当前代码对以下合法 cause 链：

```python
outer = RuntimeError("wrapper failed")
outer.__cause__ = PermissionError()
```

输出只有：

```text
builtins.RuntimeError: wrapper failed
```

`PermissionError` 完全消失。使用测试文件已经称为“sharpest defensive case”的固定消息 wrapper 也同样复现：`openai.APIConnectionError("Connection error.") from h2.exceptions.ProtocolError()` 输出只有：

```text
openai.APIConnectionError: Connection error.
```

唯一能说明底层是 HTTP/2 protocol failure 的 `h2.exceptions.ProtocolError` 被吃掉。这不是 same-`__qualname__` 的已接受取舍；两个类型名不同，丢失只由“前面曾有文本”触发。

**为什么这与 deadline 不是同一判断。** `TimeoutError() -> CancelledError()` 是否是噪声，依据是已实测的 `asyncio.timeout` 机制和已点名的 outer guard；“所有有文本 outer 后的空文本 cause 都是噪声”没有对应证据。当前全局启发式把一个对两种已知 guard 成立的判断扩成了对任意 exception chain 的规则。

**严重度依据。** 反例由真实异常类型组成，且 framing 区间结构上能把任意 `Exception` 送来；不过支撑调查没有观测到这种 exact shape 进入 hand-over，所以足以否定一般规则，尚不足以声称线上已误报，定 minor。

**建议。** 不要用全局 `carried_text` 代替“这个空 cause 是否只是已知包装机制”的判断。最窄的修法是仅对已测量的 `StreamDeadlineError`／`StreamIdleTimeoutError -> TimeoutError -> CancelledError` 机制抑制这两个内部 link，其他 fresh class 继续 type-only 保留；若坚持当前全局规则，则需把“会牺牲 text-bearing outer 后的所有空 cause 类型”作为明确产品取舍交给用户裁定，不能把它描述成没有新信息。

## 三个重点问题的确认结果

### 1. m1 三分支是否引入新丢失

**是，见 m2。** 新文本和重复文本／新类名两支正确；无文本分支把 deadline 的局部机制判断泛化后，会吞掉 `RuntimeError("wrapper failed") from PermissionError()` 这类唯一 inner type。`__qualname__` 去重的 module-only 损失已在 docstring 与 README 明确标为有意取舍，本轮不重复列 finding。

### 2. M1 新断言能否绕过

**error 路径的合理回归已挡住。** 手搓 outer type/text/attempt formatter 会因缺 `NO_ERROR` 失败；只补一个固定 `NO_ERROR` 仍过不了随机 request id 与日志的交叉核对。直接调用 `describe_error` 并正确拼接实际 request id/attempt 与 `interruption_message` 的 error 分支在外部行为上等价，不应为了锁函数名而判失败。

**non-error 路径仍有 m1 的独立绕过。** 它不是对 error 断言的反例，而是同一生产接线的另一个 observable branch 尚未在真实入口断言。

### 3. 前两轮九条是否闭合

| 原 finding | 最终判断 |
|---|---|
| F1 生产接线测试 | **error 分支闭合；non-error 分支仍有 m1** |
| F2 链上限与唯一类型 | 截断 marker 闭合；重复文本类型闭合；空文本类型的一般性保证被新规则重新打开，见 m2 |
| F3 falsy cause | 闭合 |
| F4 receiver `verbatim` | 闭合；schema 已含 request id 与 attempt，plugin README 明说不是异常原文且不解析 |
| F5 过度断言 | 闭合；journal 快照、GOAWAY 数字、remote-reset 方向、频率、构造案例均已收窄 |
| M1 error 接线鉴别力 | 闭合 |
| M2 权威 README 漂移 | 闭合；当前锚点为 `e2cb70b`，三分支、九条输出、截断 marker 均与代码一致 |
| m1 deadline cancellation 噪声 | 具体两种已观测形状闭合；通用修法产生 m2 |
| m2 五处措辞／schema | 闭合 |

## 其他确认

- `_chain` 的 cause 优先、context suppression、循环保护与 6-link 截断行为没有回归。
- README 中 GOAWAY、RST_STREAM、真实 reset、deadline、idle timeout、裸 h2、StreamClosed、max_tokens 九条示例与当前代码一致；同步锚点和更新义务已写明。
- 当前 plugin schema 已写 “request id and which attempt this was”；有效文档没有把 message 再称作 upstream verbatim。
- 精确 `9645293` 副本的 21 条 unit + 两条相关 integration 为 `23 passed`；没有重跑协调者已报告通过的 1496 条全量测试。
- 本复核没有修改主工作树源码或测试。

## 第四轮：`8de0d3c` 收口确认

> 本节是这份报告的最新 verdict，覆盖文件开头针对 `9645293` 的历史 verdict；前文保留为每一轮实际发现的原始记录。

- 评审对象：`8de0d3c0decdbc951f6d49073a440b66fa90e4f8`
- Verdict：**needs-fix**
- 本轮计数：blocker 0，major 1，minor 1，nit 0

### 第四轮结论

第三轮的两个具体反例都已修复：真实 max-tokens 入口现在会让裸 `stop_reason` 变异变红；固定文本 wrapper 下的静默 `PermissionError`／`h2.ProtocolError` 与非 timeout 来源的 `CancelledError` 都重新保留类型。M1 的 error 入口强断言也没有回归。

尚不能给 `pass`。`8de0d3c` 再次修改了 `describe_error` 的筛选契约，但名为跨仓现行权威的 README 仍锚在 `e2cb70b`、逐字描述上一版规则；这正是 M2 要防的同一失效，严重度仍为 major。新的 `_asyncio_timeout_plumbing` 另有一个可构造的 minor：它把“任意较早出现过一个带文本的 `TimeoutError`”当成“当前静默 `TimeoutError`／`CancelledError` 是相邻的 asyncio.timeout plumbing”，会吞掉真正的 cancellation，也会在复制 guard 文本的 wrapper 下漏掉本来要压掉的 plumbing。该 minor 尚无生产观测，可以登记 deferred；M2 的权威契约漂移不应 deferred。

### M3 — [major] M2 立即复发：`describe_error` 已在 `8de0d3c` 改规则，跨仓权威仍锚定并描述 `e2cb70b`

`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/README.md:73-75` 仍把同步点写成 `e2cb70b`，并明确规定“改 `describe_error` 的人必须同时改本节，并把这行锚点换成新提交”。`8de0d3c` 正是一次 `describe_error` 语义改动，但当前锚点未更新。

更实质地，README `:87` 仍写上一版规则：

> 没有文本 → 只有 `module.QualName`，且仅当此前还没有任何一环带过文本。

当前代码 `src/app/pipeline/hand_over.py:129-136,162-177` 已改为：除了判定为 asyncio.timeout plumbing 的静默 `TimeoutError`／`CancelledError`，其他静默 fresh class 一律保留。第三轮的两个反例正是利用这个差异修复的，所以权威文档现在会把已经修好的行为描述成仍会丢失。

九条示例的字节恰好没有变化，因为本轮只把两类既有示例之外的静默 cause 恢复出来；这不能让算法契约的冲突降级。插件 README 仍指向这一节作为发出方格式权威，处置文档又把 M2 记成已闭合，因此维护者没有其他可靠位置判断当前规则。

**建议。** 把同步锚点更新到 `8de0d3c`，将第三分支改成当前 timeout-plumbing 判据，并记录该判据是否按本轮 m3 继续收窄；同步更新处置文档的提交列表与状态。M2 原本就是 major，本次是它规定的同步动作在下一次 `describe_error` 改动时立即未执行，严重度没有降级依据。

### m3 — [minor，可 deferred] `_asyncio_timeout_plumbing` 记住的是“任意先前 timeout”，不是实测 plumbing 的相邻结构

当前 helper：

```python
return named_a_timeout and isinstance(link, TimeoutError | CancelledError)
```

`named_a_timeout` 一旦任何先前以 fresh text 渲染的 link 是 `TimeoutError` 就永久为真。它不要求当前静默 link 与那个 timeout 相邻，也不要求出现实测的 `text-bearing TimeoutError guard -> builtins.TimeoutError() -> asyncio.CancelledError()` 三环结构。

我在当前代码上得到以下输出：

```text
MEASURED_TIMEOUT_PLUMBING
app.streaming.deadline.StreamDeadlineError: attempt exceeded its deadline

DIRECT_GENUINE_CANCELLATION_UNDER_A_TIMEOUT
builtins.TimeoutError: outer timeout

SEPARATED_GENUINE_CANCELLATION
builtins.TimeoutError: outer timeout; caused by builtins.RuntimeError: middle failure

SILENT_DISTINCT_TIMEOUT_SUBCLASS
builtins.TimeoutError: outer timeout
```

后三个输入分别是：`TimeoutError("outer timeout") -> CancelledError()`、`TimeoutError("outer timeout") -> RuntimeError("middle failure") -> CancelledError()`、`TimeoutError("outer timeout") -> DatabaseTimeout()`。三条 inner class 都是新且无文本，可能就是唯一失败线索，却只因链上较早出现过一个 timeout 就被压掉；第二条尤其证明该判据不是“under”或相邻关系。

反方向也会漏压。若未来新增一个复制 guard 文本的 wrapper：

```text
RuntimeError("attempt exceeded its deadline")
  -> StreamDeadlineError("attempt exceeded its deadline")
  -> TimeoutError()
  -> CancelledError()
```

当前输出是：

```text
builtins.RuntimeError: attempt exceeded its deadline; caused by app.streaming.deadline.StreamDeadlineError; caused by builtins.TimeoutError; caused by asyncio.exceptions.CancelledError
```

因为 guard 自己的文本与 outer 重复，它走 type-only 分支，`named_a_timeout` 没有被设为真；已经实测的 plumbing 反而全部漏出来。也就是说，这个 bool 同时比实测机制更宽、又在 wrapper 出现时更窄。

**严重度与处置建议。** 这是给人读的诊断丢失／噪声，不影响 retry 决策；上述均为构造反例，当前调查没有生产样本，故定 minor，可以登记 deferred 而不阻塞本轮功能。若现在修，仍可不列 guard 类名：在原始 `links` 上按相邻结构识别“一个自身有文本的 `TimeoutError` link，紧接 exact `builtins.TimeoutError()`，再紧接空的 `asyncio.CancelledError()`”，只压后两环。判据应读 link 自己的文本而不是 `fresh_text`，这样复制文本的 wrapper 不会使 guard 失去资格；中间插入其他 link、直接 cancellation、不同 TimeoutError 子类也不会误伤。

### 三项确认

#### 1. `_asyncio_timeout_plumbing` 是否误伤

**会，见 m3；无 blocker/major。** 两个已测 guard 输出正确，第三轮的两个 silent-cause 反例也已恢复；剩余问题是当前 bool 没有表达实测的相邻三环结构。它属于可 deferred 的 minor。

#### 2. m1 新断言是否仍可合理绕过

**旧分支回归已被可靠挡住，没发现需要阻断的新绕过。** 我从 `8de0d3c` 建立 `/tmp/handover-fourth-review-aeQKrh`，基线运行 23 条 unit 加 error/max-tokens 两条 integration，共 `25 passed in 2.89s`。随后只把 `error is None` 分支恢复成裸 `stop_reason`，并以 `__file__`／`inspect.getsource` 确认加载变异；max-tokens 测试按预期在 `assert 'max_tokens' != 'max_tokens'` 变红。

正则没有把 request id 与独立日志值交叉核对，因此一个刻意手拼完整文案并塞入无关 UUID 的实现可以满足它；但 helper 单测已钉传入的 `REQUEST_ID`，error 入口又独立证明同一无条件 call site 会把真实 request id 送到 wire。要绕过必须新造一个只对 non-error 分支伪造 UUID 的实现，已经超出这条测试要防的实际旧回归，不据此列 finding。

#### 3. 前三轮十一条是否全部闭合

- 两个第三轮 finding 的**具体反例均已闭合**：m1 的裸 stop_reason 变异会红；m2 的两种静默 cause 与非-timeout cancellation 均有回归测试。
- F1/F2/F3/F4/F5、M1、第一版 m1/m2 的代码与测试行为均无回归。
- **M2 没有保持闭合**：其同步规则在下一次 `describe_error` 改动时立即失效，见 M3。
- 新 timeout helper 的已测正路径成立，但存在 m3 的可 deferred 构造边界。

### 第四轮验证摘要

- 精确 `8de0d3c` 副本：23 条 unit + 两条相关 integration，`25 passed in 2.89s`。
- non-error 旧分支正控：运行时确认变异已加载，目标 integration 按预期在 `message != "max_tokens"` 失败。
- 当前实现探针：第三轮两个 silent-cause 反例、非-timeout cancellation、deadline/idle/reset 均得到协调者列出的预期输出；另得到 m3 的 false-positive/false-negative 输出。
- 协调者报告 Ruff、targeted Pyright 已通过；本轮未重复全量测试。
- 本轮没有修改主工作树源码或测试，只按要求追加本报告。

## 第五轮：`2d6b878` / `.dev@2d4c38c` 收口确认

> 本节是这份报告的最终 verdict，覆盖前文各轮的历史 verdict。

- 评审对象：主仓 `2d6b8780b844e09f91ceeac09ba9f155abb56192`；开发文档仓 `2d4c38c63b2a66028ef998825fb6032f63ef7d26`
- Verdict：**pass**
- 本轮计数：blocker 0，major 0，minor 0，nit 1

### 第五轮结论

M3 与 m3 均已闭合。timeout suppression 现在只匹配调查实际记录的相邻三环，并在原始 link 自身文本上判定，不再用跨链状态推测位置；第四轮的三个误伤反例与一个漏压反例全部有直接回归测试。跨仓 README 已锚到 `2d6b878`，规则表逐项对应当前 helper，违反锚点两次的历史也留在规则旁；处置文档不再复制可变规则。M1 的 error 与 max-tokens 两个真实入口断言均保持有效。

没有发现 blocker、major 或应在本轮继续修复／登记 deferred 的 minor。唯一 nit 是发现数量的台账口径：前三轮明确计为 11 条，第四轮新增 M3/m3 两条，按报告标签应为 **13 条**而非处置文档和本轮提示中的“14 条”；这不影响任何实现或 finding 处置结论。

### 1. 相邻三环判据

当前 `_asyncio_timeout_plumbing` 只在原始 `links` 中匹配：

```text
TimeoutError 子类且自身文本非空
  -> type(x) is builtins.TimeoutError 且自身文本为空
  -> type(x) is asyncio.CancelledError 且自身文本为空
```

只压后两环。四个第四轮反例逐项核对：直接挂在 timeout 下的 `CancelledError` 保留；隔着 `RuntimeError` 的 `CancelledError` 保留；静默 `TimeoutError` 子类保留；复制 guard 文本的 outer wrapper 不再妨碍识别真实 plumbing。两个实测 guard 仍只输出已点名的 outer；reset、fixed-text wrapper、silent cause 等前几轮反例不变。

还能手工构造一条语义上声称“不是 asyncio.timeout”、字节与类型却完全等于上述三环的链，但 formatter 没有可观察事实可以区分它；要求它猜隐藏 provenance 不是可实施判据，不据此列 finding。判据对 exact builtins `TimeoutError` 与 exact `asyncio.CancelledError` 的要求是保守的：未来 runtime 若改用子类只会多显示类型，不会再静默吞掉原因。

### 2. m1 真实入口断言

`test_a_turn_that_ran_out_of_room_is_handed_back_the_same_way` 现在读取客户端实收的 `input.message`，同时钉住“不是裸 `max_tokens`”、`stop_reason=max_tokens` 与 request/attempt 结构。第四轮已验证的裸 `stop_reason` 变异现在会在 `message != "max_tokens"` 处变红；`2d6b878` 未改动该入口或调用接线，本轮基线再次通过。

error 入口继续钉 `NO_ERROR` 与同日志交叉核对的 request id。两个入口配合 helper 单测后，没有发现仍能丢掉本次 message 契约而属于合理回归的绕过。

### 3. 前四轮 finding 闭合状态

按报告中实际编号，前四轮共有 13 条：第一轮 F1～F5 五条，第二轮 M1/M2/m1/m2 四条，第三轮 m1/m2 两条，第四轮 M3/m3 两条。它们的具体反例、生产接线、跨仓描述和同步锚点均已闭合；`__qualname__` 合并不同 module 同名异常是已明确接受并写入权威文档的产品取舍，不是未处置 finding。

### 第五轮验证摘要

- 精确 `2d6b878` 副本：26 条 unit + error/max-tokens 两条 integration，共 `28 passed in 2.81s`。
- 主仓 `2d6b878` 后的 `tests/int/test_pipeline_app.py` 有同伴新增改动，但提交副本验证隔离了它们；`hand_over.py` 与本次 unit 文件在当前 HEAD 与 `2d6b878` 一致。
- 开发文档仓 `2d4c38c`：README 锚点为 `2d6b878`，规则表与代码相符；处置文档只指向该锚点，不再充当第二份可变规则。
- 协调者报告 Ruff、targeted Pyright 与全量 `1506 passed / 2 skipped` 均通过；本轮未重复全量。
- 本轮没有修改主工作树源码或测试，只按要求追加本报告。
