# `79428bb` hand-over message delta 复核

- 评审对象：`79428bbd7b8a2994b88701b7588ac996e12c74a8`，父提交 `aac348e`
- 评审范围：F1～F5 的处置，以及当前插件描述和本主题跨仓契约
- 日期：2026-08-23
- Verdict：**needs-fix**
- 计数：blocker 0，major 2，minor 2，nit 0

## 结论

F3 已正确闭合；F4 的 `verbatim` 冲突也已闭合，当前有效描述里没有残留把代理合成句误称为上游原文。F2 的截断标记本身边界正确，但新的“新文本或新 `__qualname__`”筛选规则给两个已观测 deadline 形状加入了误导性较强的内部 `CancelledError` 噪声，同时仍会丢掉 module 才能区分的同名异常。F1 只挡住了原评审采用的那一个旧实现变异，仍能把 formatter 及其 cause/gloss/request-id 行为从生产接线拿掉而保持新增 19 条单测和加强后的集成测试全部通过。更直接的问题是，名为跨仓现行权威的 `.dev/docs/upstream/retry-and-continuation/README.md` 仍逐字描述旧筛选规则，并给出三条已经不再是实际输出的示例。

证据权重：M1 由隔离提交副本上的正控变异直接证明，强到足以据此修复；M2 是当前代码与当前权威文档逐字冲突，强到足以据此同步；m1 的 deadline 噪声以调查报告记录的真实链形状输入当前函数复现，足以据此重新裁定展示策略，而 same-qualname 丢失仅是构造反例，不支持声称线上已经误报；m2 是源码文本与现有测试／记录直接对账，足以修正文案。

## Findings

### M1 — [major] F1 尚未闭合：集成断言能挡住原始 `str(error)`，但仍不能证明 cause/gloss/request-id formatter 接上了生产块

**当前改进有效的一面。** `tests/int/test_pipeline_app.py:3178-3181` 确实让原来的 `detail = str(error)` 变异变红，因为旧值没有 `httpx2.RemoteProtocolError` 和 `attempt 1`。因此不能说这次补测毫无作用。

**仍可绕过的接线。** 我从 `79428bb` 用 `git archive` 建立 `/tmp/handover-delta-review-DR2rGU`。未变异时，新增单测加目标集成测试共 `20 passed in 3.86s`。随后只把 `hand_back_block` 中对 `interruption_message(...)` 的调用改成：

```python
detail = (
    f"{type(error).__module__}.{type(error).__qualname__}: {error} [attempt {context.attempt_count}]"
    if error is not None
    else stop_reason
)
```

这条接线不调用 `interruption_message`／`describe_error`，不走 cause chain，不会生成 HTTP/2 gloss，也完全丢掉 `request_id`。运行前用 `app.pipeline.hand_over.__file__` 和 `inspect.getsource(hand_back_block)` 确认加载的是该变异文件及上述表达式；随后同一组 19 条单测与目标集成测试仍为：

```text
20 passed in 2.73s
```

**为什么现有三条断言会漏。** 集成 fixture 只抛一个无 cause 的 `httpx2.RemoteProtocolError("peer closed the connection")`，所以手工拼 outer type、outer text 和 attempt 就能满足全部断言。单测仍直接调用真正的 helper，当然保持全绿。`tests/int/test_pipeline_app.py:3177` 的注释还说测试钉住了 “the type name and the request id”，但 `:3179-3181` 实际钉的是 type、text、attempt，根本没有 request id 断言。

**影响。** 新 formatter 最有价值的三项——深层 cause、HTTP/2 enum gloss、可回连代理日志的 request id——仍可以整体滞留在未被生产入口调用的 helper 中，而相关测试全绿。这不是要求测试必须锁死函数名；问题是生产可见契约的大半仍可丢失。

**建议。** 让真实入口 fixture 带一个已记录过的 cause/event 形状，并从客户端实收块断言内层原因或 `NO_ERROR` gloss；同时用 `request_log` fixture 已落下的记录取实际 request id，断言该值出现在 message。这样钉的是生产行为而不是 helper 身份，也能使上述变异变红。若不想在这条集成测试复造整个四层 reset，至少要加入实际 request id 对照，再选择一个带 cause 的最小已记录形状。

### M2 — [major] 名为跨仓现行权威的 README 仍描述旧算法，并给出三条已经错误的实测输出

**代码现状。** `src/app/pipeline/hand_over.py:137-157` 已改为“新文本或新 `__qualname__` 即保留”，并在截断时追加 marker。

**文档现状。** `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/README.md:77` 仍写：

> 文本与前面某一环重复的丢弃，内层无文本的丢弃，最外层无论有没有文本都保留。

这正是 `79428bb` 删除的旧规则。该文档 `:85` 仍把真实 reset 输出写成不含 `anyio.BrokenResourceError` 的旧值，`:87-88` 仍把 attempt deadline／idle timeout 写成只有 outer link 的旧值。当前代码对调查报告已记录的三种链实际输出分别是：

```text
httpx2.ReadError; caused by anyio.BrokenResourceError; caused by builtins.ConnectionResetError: [Errno 104] Connection reset by peer [request a1b2c3d4, attempt 1]
app.streaming.deadline.StreamDeadlineError: attempt exceeded its deadline; caused by builtins.TimeoutError; caused by asyncio.exceptions.CancelledError
app.streaming.idle_timeout.StreamIdleTimeoutError: No stream item received for 300s; caused by builtins.TimeoutError; caused by asyncio.exceptions.CancelledError
```

`README.md:97` 还只说“链最多走 6 环”，没有写达到上限时的新 marker。插件 README 在 `/home/xp/.claude/my/ghc-api-proxy-helper/README.md:26` 明确指向本节为发出方格式权威，因此这不是普通旧笔记，而是接收端主动依赖的契约。

**影响。** 接收端维护者按权威表理解或写测试会得到错误规则和错误字节；本轮处置文档 `260823-review-handover-message-disposition.md:58` 又宣称三处已同步，进一步掩盖了 `79428bb` 后 README 再次过期的事实。

**建议。** 按 `79428bb` 当前输出同步规则、三条示例与截断 marker，并在处置文档中把“已同步”的版本锚到同步后的 commit／快照，避免把 F4 时点的同步误当作 F2 后仍然同步。

### m1 — [minor] “每个新类名都保留”在两个已观测 timeout 链上引入内部取消噪声，同时 `__qualname__` 去重仍会丢 module-only 区分

**已观测形状上的新噪声。** 一手调查 `260823-handover-error-shapes.md:108-130` 记录了 `StreamIdleTimeoutError`／`StreamDeadlineError` 的真实 cause 均为 `TimeoutError('') -> CancelledError('')`。把这两个已记录形状交给当前 `describe_error`，输出为：

```text
app.streaming.deadline.StreamDeadlineError: attempt exceeded its deadline; caused by builtins.TimeoutError; caused by asyncio.exceptions.CancelledError
app.streaming.idle_timeout.StreamIdleTimeoutError: No stream item received for 300s; caused by builtins.TimeoutError; caused by asyncio.exceptions.CancelledError
```

外层已经准确说明 attempt deadline／idle timeout；内层 `CancelledError` 是 `asyncio.timeout` 实现超时的机制，不是客户端取消或另一个中断原因。把它放进给人和模型读的一句话，容易把已明确的 timeout 重新读成 cancellation。当前新增测试只覆盖了 reset 链多出 `anyio.BrokenResourceError`，没有覆盖这两个报告中同样明确的链形状。

**仍存在的丢失。** 代码展示完整 `module.qualname`，却只用 `__qualname__` 判断 class 是否新鲜（`hand_over.py:145-150`）。两个不同 module 的同名异常、同文本异常会被当成同一类。我构造 `outer_library.CollisionError("same text") from inner_library.CollisionError("same text")`，当前输出只有：

```text
outer_library.CollisionError: same text
```

当前已观测的同名组合主要是 httpx2/httpcore2 的包装层，丢 inner module 是本轮明确接受的去噪取舍，所以这个构造反例不足以单独定 major；它只是说明“新类名”并不是一般性的完整 class identity 判据。

**建议。** 先裁定“唯一”是否等于“值得展示”。一个较窄方向是：文本重复但类型不同的 link 保留 type-only，满足 `PermissionError` 反例；纯空文本的内部实现链则不要仅因类名不同全部打印，尤其当 outer 已有完整说明时。若继续按 `__qualname__` 去重，应在 docstring 明说 module 差异被有意视为同一包装类，而不是笼统宣称“新类名”。

### m2 — [minor] F5 收窄仍有残留；插件已无 `verbatim` 残留，但 schema 描述漏写 attempt

1. `tests/unit/pipeline/test_hand_over_message.py:5` 说只有两个非实测 case 且“各自在 docstring 里自陈”。当前至少有 `APIConnectionError`、falsy cause、同文本不同类型、七层截断、`remote_reset=False + CANCEL` 五类构造 case；其中七层截断只说性质，`remote_reset=False` 测试甚至没有 docstring。这个新全称在新增三条反例测试后已经不成立。
2. `tests/unit/pipeline/test_hand_over_message.py:64` 的 “The old field ended at `error_code:0`” 仍容易被读成旧字符串到此结束；实际旧值在该字段后还有 `last_stream_id` 和 `additional_data`。应直接说“旧字段把错误码显示为数字 0，而没有显示枚举名 NO_ERROR”。
3. `src/app/pipeline/hand_over.py:137` 新写 “every transport tear prints the same event repr twice”，但调查报告已经记录真实 reset 的两个 outer 文本都为空、HTTP/1.1 提前关闭重复的是 h11 错误文本而非 event repr。这里只能说当前 h2 event 经 httpcore2→httpx2 映射时会重复 event repr。
4. `tests/int/test_pipeline_app.py:3177` 声称 request id 被钉住，而实际没有断言，见 M1。
5. `/home/xp/.claude/my/ghc-api-proxy-helper/src/auto_retry/server.py:54-58` 已正确删除 `verbatim`，`/home/xp/.claude/my/ghc-api-proxy-helper/README.md:20-26` 也明确“不是异常原文”且 receiver 只原样记账；在当前有效文件中没有发现旧 `verbatim` 语义残留。不过 schema description 只列 “plus the proxy's own request id”，漏了同样固定存在的 attempt count；插件 README 已写全两项，建议让 schema 与之对齐。

## 重点复核逐项结论

### 1. 新的“新文本或新类名”规则

**有一个已观测噪声问题和一个构造性信息丢失，见 m1。** 对原 F2 两个反例的修复本身正确：同文本 `PermissionError` 会 type-only 保留，全空 `RuntimeError -> PermissionError` 也会保留两类。真实 reset 现在多保留 `anyio.BrokenResourceError`，与修订测试一致。

除此之外，选择器的状态更新顺序正确：新 class／重复 text 会输出 type-only；重复 class／新 text 会输出 type + text；两者都重复才跳过。没有发现 seen set 更新导致后续 link 被无故吞掉的分支。

### 2. 截断 marker

**查过，没发现漏打或误打。** 探针覆盖 5、6、7 层与 6 层回环：

```text
links  5 -> walked 5, truncated False, marker False
links  6 -> walked 6, truncated False, marker False
links  7 -> walked 6, truncated True,  marker True
6-link cycle -> walked 6, truncated False, marker False
```

循环在进入上限分支前由 `id(current) not in seen` 停止，不会误报“还有第 7 个独立 link”；第 7 个未见对象存在时才返回 `True`。falsy 显式 cause 现在也会成为真实的下一环，不再造成 marker 漏判。新增正向测试没有钉“恰好 6 层不标记”的负边界，但当前实现足够直接，未据此另列 finding。

### 3. 集成测试接线鉴别力

**原始 `str(error)` 变异已被挡住，但仍有 M1 的更强绕过。** 当前三项断言不能证明 route 使用了 chain-aware formatter，也没有钉住注释自称已钉的 request id。

### 4. F5 与 `verbatim`

**部分收窄正确，仍有 m2；另有 M2 的权威文档漂移。** journal 快照、remote_reset 方向与 reset 频率三处已准确收窄；APIConnectionError 局部说明仍明确说结构上不可达。当前有效 receiver 描述没有把 message 再称作 upstream verbatim；搜索命中的 `verbatim` 只剩“旧描述曾这样写”的历史说明，以及与 message 无关的 `category verbatim`。

## 已通过的验证

- 精确提交副本：`19` 条 unit + 目标 integration，共 `20 passed in 3.86s`。
- M1 变异副本：运行时确认加载变异后，同一选择器仍 `20 passed in 2.73s`，证明剩余接线盲区。
- Ruff：对 `79428bb` 副本的三个变更文件执行 `ruff check`，通过。
- Pyright：在项目环境对三个变更文件执行 targeted Pyright，`0 errors, 0 warnings, 0 informations`。
- 没有运行全量测试；没有修改主工作树源码或测试。
