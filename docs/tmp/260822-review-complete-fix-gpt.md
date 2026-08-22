# `COMPLETE` 修复独立评审

评审对象：隔离工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon`，基线 `4c7129a`，候选为工作树中尚未提交的两文件改动。

## 结论

**Verdict：needs-fix。** 候选生产代码的修法正确，两个既有测试的夹具修改也都是纠正夹具，不是把守卫改软；但新增回归测试没有配置生产路径必有的 `ReplaySupport`，因此本次修改涉及的全部四个测试实例允许一个“仅在 `replay is None` 时修复”的缺陷实现保持全绿。这个缺口足够据此在整合前补测试，生产代码本身无需因本轮评审改动。

与提交者核心说法的实质分歧为 **1 项**：我同意根因、后果、插入位置和夹具纠正；我不同意当前新增测试已经充分锁住生产路径。另有 1 项非阻断的设计余味：当前生产调用点再也到不了 `decide_stream_ending()` 的 `COMPLETE` 分支。

## 一、先于 diff 形成的独立判断

【权重：足够据此行动】在基线控制流中，`decide_stream_ending()` 返回 `StreamEnding.COMPLETE` 后，调用者执行的是 `if verdict.ending is not StreamEnding.REPLAY: raise torn`，所以把 `COMPLETE` 和 `ABANDON` 都重新抛成传输失败。这与 `decide_stream_ending()` 自己把“已见合法 terminal event”定义为完成相冲突，也会使已经收齐 `message_delta` 和 `message_stop` 的回复丢失后续下游 terminal frames；该行为错误。

我在看 diff 前的首选修法是：调用者必须把 `COMPLETE` 解释为正常离开重试循环，而不是抛出 `torn`。若只在现有 verdict 后增加显式 `COMPLETE -> break`，仍受制于前面的 `replay is None or reason is None -> raise`，所以不能覆盖“不配置 replay”或异常分类器不认识异常的情况。因而更好的最小修法是在异常被捕获后、任何 replay 配置和异常分类之前，根据位置事实 `assembler.terminal.seen` 正常 `break`；但必须保留既有 `ClientDeadlineError` 的优先级。

查看候选 diff 后，生产代码正是采用了这个位置和动作，与独立判断一致。

## 二、逐点对照

### 1. 插入位置和 `ClientDeadlineError`

【权重：足够据此行动】候选把 terminal 短路放在 `ClientDeadlineError` 分支之后、`replay.eligible` 之前，是当前合同下最合适的位置。

原因有两层。第一，放在 `replay.eligible` 前面是必要的：完成与否是 assembler 已观察到的位置事实，不应由异常 taxonomy、是否配置 replay 或预算决定。第二，放在 `ClientDeadlineError` 后面保留了刚刚单独裁定并已有测试固定的行为：即使测试源先送完 terminal events 再抛 `ClientDeadlineError`，下游仍收到 `client_deadline_exceeded`，而不是把 held content 和成功 ending 刷出。

把它“合并进 `if torn is None:`”有两种解释，结果不同：若嵌套在该分支内，目标场景的 `torn` 非空，修复根本不会触发；若改成 `if torn is None or assembler.terminal.seen: break`，则 terminal 会压过 `ClientDeadlineError`，现有 `test_the_client_deadline_is_the_one_ending_that_says_so` 会改变语义并失败。这不是等价整理，而是新的 deadline policy 裁决。要在一个条件中维持现状只能写出排除 `ClientDeadlineError` 的复合表达式，反而不如当前顺序清楚。

与提交者说法：**无分歧。**

### 2. `decide_stream_ending()` 的 `COMPLETE` 是否仍可达

【权重：足够据此记录，但不足以阻断本次生产修复】从当前唯一生产调用点看，`COMPLETE` 已不可达。候选的 terminal 短路保证继续走到 `decide_stream_ending()` 时 `assembler.terminal.seen` 恒为 false，调用仍把该值传给 `terminal_seen`，所以函数第一个分支只剩纯函数单测能触达。

这不构成当前 correctness defect：调用者已在拥有完整位置事实且无需 `reason`／`ledger` 的地方完成同一裁决，随后统一执行 `session.finish()` 和 terminal framing。它是 API／职责形状上的余味：`decide_stream_ending()` 文档仍宣称三种 outcome，而生产只向它询问 `REPLAY` 与 `ABANDON`，同一条 complete rule 同时写在 caller 和 policy 中。不要为了本次小修扩大重构；后续若整理，应明确选择“policy 只裁未完成流”或重塑参数使 caller 能在分类前真正询问完整 verdict，而不是保留一个看似接线、实则恒不可达的 `COMPLETE`。

与提交者说法：**事实判断无分歧；我不把不可达本身升级为本次 blocker。**

### 3. 两个既有测试的夹具修改

【权重：足够据此行动】两处都是纠正与测试意图不符的夹具，不是迁就新行为而削弱守卫。

`test_a_stream_the_client_already_saw_is_not_replaced` 的命题是“已向 client 交付 block 的未完成 attempt 不可无痕 replay”。旧夹具先喂完整 `anthropic_stream("first")`，其中已含 `message_delta` 和 `message_stop`，随后才开始第二段；它测成了“已经完整结束后又出现另一段并 tear”，不是命名和 docstring 所说的未完成 attempt。改成第一段 `[:-2]` 后，第一 block 已交付而 terminal 未见，随后第二 block 只开到 delta 就 tear，正好命中 `ABANDON` 守卫。

`test_an_upstream_tear_is_still_raised_rather_than_framed` 的命题是“未完成的普通 upstream tear 仍然 raise，不伪装成 wire error frame”。旧夹具同样已送完 terminal；切掉最后两帧后才是该命题所需的未完成流。

`git blame -L 943,1058 4c7129a -- tests/unit/pipeline/delivery/test_stream_delivery.py` 还显示，第一条测试最初与 replay slice 一起引入，docstring 从一开始就只说 client 已持有 block 后不能 replay；第二条与 client deadline slice 一起引入，docstring 从一开始只说普通 upstream tear。两者旧夹具都额外携带了与命题冲突的完整 terminal。

但纠正夹具后必须由正向测试接住完整 terminal 场景。候选新增了正向测试，所以不是“删掉旧守卫后不补”；问题只是正向测试没有接住生产必有的 replay 配置，见下一节。

与提交者说法：**对“夹具应改”无分歧；对改后测试组合是否足够有 1 项分歧。**

### 4. 新增参数化测试的分辨力

#### 4.1 删除修复分支的正控

【权重：足够确认该测试能咬住被删除的短路机制】我先运行候选，四个相关实例均绿；随后用预先冻结的 exact patch 删除整个 `if assembler.terminal.seen: break` 分支，并通过运行时 `inspect.getsource()` 证明 pytest 导入的是这个隔离工作树中的变异模块。输出为：

```text
resolved_module=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon/src/app/pipeline/delivery/stream.py
terminal_short_circuit_present=False
```

运行新增测试后，两种 policy 都按预期因 `ConnectionError: upstream tore` 失败：

```text
collected 2 items
... [block] FAILED
... [full] FAILED
2 failed in 2.17s
```

反向应用同一冻结 patch 恢复后，运行时确认 `terminal_short_circuit_present=True`，新增测试恢复为：

```text
2 passed in 2.06s
```

所以“把源码这一支完整去掉”确实会打红，不是假变异。

#### 4.2 一个更贴近生产接线、但全部改动测试仍全绿的反例

【权重：足够据此要求整合前修正测试】生产 `_serve()` 对 block delivery 始终构造并传入 `ReplaySupport`。新增测试却故意不传 `replay`。我把候选正确条件受控变异为：

```python
if assembler.terminal.seen and replay is None:
```

该实现只修测试路径，生产路径仍会在完整 terminal 后落回原缺陷：若 `eligible` 不认识异常就提前 raise；若认识，则 `decide_stream_ending()` 返回 `COMPLETE`，又被 `is not REPLAY` 折叠为 raise。运行时探针确认加载了该变异：

```text
resolved_module=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon/src/app/pipeline/delivery/stream.py
replay_specific_counterexample_present=True
```

然而新增测试的两个 policy，加上本次修改过的两条既有测试，全部保持绿色：

```text
collected 4 items
...terminal_event...[block] PASSED
...terminal_event...[full] PASSED
...client_already_saw... PASSED
...upstream_tear... PASSED
4 passed in 2.05s
```

这正好说明：夹具修改本身正确，但测试组合丢掉了旧夹具曾经偶然覆盖的“terminal + replay configured”条件，新增测试没有补回。候选源代码没有这个 defect，缺的是回归测试的生产接线分辨力。

我还做了第二个反例，把条件变为只接受 `ConnectionError`：

```python
if assembler.terminal.seen and isinstance(torn, ConnectionError):
```

新增测试两种 policy 仍为 `2 passed`。`h2.exceptions.ProtocolError` 的实际 MRO 是 `ProtocolError -> H2Error -> Exception -> BaseException`，不是 `ConnectionError`；这说明当前测试也不能锁住注释强调的“完成事实不依赖异常类型”性质。

最小修正不是添加矩阵或 gate，而是让现有正向测试走更承重的一条路径：传入非空 `ReplaySupport`，使用一个不是 `ConnectionError` 的异常，并让 `eligible` 返回 `RetryReason.NETWORK`；`reopen` 应是若被调用就失败的 spy。这样去掉短路分支会真正抵达旧的 `COMPLETE -> raise`，把条件错误收窄到 `replay is None` 或 `ConnectionError` 也会打红，同时无需再加一组参数化维度。

#### 4.3 输出断言本身

【权重：只是改进倾向，不足以单独阻断】现有断言能证明 text、stop reason、`message_stop` 存在且没有 truncation error，但都是包含性断言；重复 terminal frames、错误顺序或多一个 message lifecycle 仍可能通过。若本次测试继续声称“delivered whole”，用现有 `events_of(chunks)` 对短小的完整 event 序列做精确断言会更匹配命题。usage 未写进夹具，因此这条新测试本身也不证明 torn-after-terminal 路径保留 usage；不过当前实现走的是与 clean EOF 相同的统一 `terminal_frames(..., usage=terminal.usage or None)`，且已有 assembler／普通 terminal 测试覆盖 usage，故我不要求为这个分支另造 usage 矩阵。

### 5. 其他失效面

【权重：足够排除当前候选中的这些具体问题；依据是当前控制流静态核对与相关测试套件，不外推为所有未来重构的保证】没有发现提交者未提到的 production correctness defect。

- 记账：terminal 后的 reset 被 delivery 解释为正常完成后，`_tracked_delivery()` 正常耗尽并设置 `accounting.drained=True`，不会设置 `failure`。`_StreamAccounting.finish()` 看到 terminal、drained 且无 failure，保留成功状态；这与“reply 已完整，socket 后续事实不应把它记为失败”一致。
- `context.reply`：`finish()` 仍在 `terminal.seen` 为真时写入 `context.reply = terminal`，没有被短路绕过。
- usage：assembler 已在 `message_delta` 读取 usage；`break` 后仍走统一的 `terminal_frames(stop_reason=..., usage=...)`，没有丢字段。
- `session.finish()`：短路只跳出外层 retry `while`，随后仅调用一次 `session.finish()`。`block` policy 此时通常无 held blocks，`full` policy 在这里恰好 flush 一次；未见双调用。
- retry ledger 和 reopen：terminal 短路位于 `eligible`、`decide_stream_ending()` 和 `reopen()` 前，不花 budget，也不打开第二 attempt。
- 清理：发生异常时 `_events_with_ping()` 的 `finally` 已结算 pull／events；离开 `async with aclosing(...)` 后再 `break`，不会把 upstream iterator 悬挂。

现有 integration test `test_a_tear_after_the_stop_reason_is_still_a_tear` 不与本修复冲突：它只送 `message_delta` 而不送 `message_stop`，所以 `terminal.stop_reason` 有值但 `terminal.seen` 仍为 false，仍应按 tear 记账和 raise。

## 三、验证记录

以下命令均在隔离工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon` 运行，未运行 `ruff format`。

候选相关套件：

```text
uv run pytest tests/unit/pipeline/delivery/test_stream_delivery.py tests/unit/pipeline/test_stream_ending.py --verbose
collected 53 items
53 passed in 21.64s
```

变异恢复后的新增测试：

```text
uv run pytest 'tests/unit/pipeline/delivery/test_stream_delivery.py::test_a_stream_torn_after_its_terminal_event_is_still_delivered_whole' --verbose
2 passed in 2.06s
```

静态检查：

```text
uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/pipeline/delivery/test_stream_delivery.py
All checks passed!

uv run pyright src/app/pipeline/delivery/stream.py tests/unit/pipeline/delivery/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

最终 `git status --short` 只剩候选原有两项，说明三轮变异均已恢复：

```text
 M src/app/pipeline/delivery/stream.py
 M tests/unit/pipeline/delivery/test_stream_delivery.py
```

`git diff --check` 无输出。

## 四、建议处置

【权重：足够据此行动】保留当前生产代码和两处夹具纠正；在新增正向测试中加入非空 `ReplaySupport`，采用非 `ConnectionError` 异常，并让 eligibility 可抵达旧 `COMPLETE` verdict、让 reopen 被调用即失败。随后重跑该测试和上述 53 项相关套件即可，不需要新增 gate、证明框架或参数化矩阵。
