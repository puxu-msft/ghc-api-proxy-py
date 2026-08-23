# `aac348e` / `79428bb` / `e2cb70b` / `9645293` hand-over `message` 评审处置

- 日期：2026-08-23
- 两轮评审原件：[`260823-review-handover-message.md`](260823-review-handover-message.md)（第一轮，**needs-fix**，blocker 0 / major 1 / minor 4）、[`260823-review-handover-message-delta.md`](260823-review-handover-message-delta.md)（复评，**needs-fix**，blocker 0 / major 2 / minor 2）
- 处置结果：**九条全部采纳**，落地为 `79428bb`、`e2cb70b`、`9645293`
- 支撑调查：[`260823-handover-error-shapes.md`](260823-handover-error-shapes.md)

## 第一轮

| # | 严重度 | 结论 | 落点 |
|---|---|---|---|
| F1 | major | 采纳 | `tests/int/test_pipeline_app.py` 那条真实入口测试 |
| F2 | minor | 采纳（两半都改） | `hand_over.py` `_chain` / `describe_error` |
| F3 | minor | 采纳 | `hand_over.py` `_chain` |
| F4 | minor | 采纳（评审开始前已改，它读到的是旧状态） | 插件 `server.py`、插件 `README.md`、本主题 `README.md` |
| F5 | minor | 采纳（五处全部收窄） | `hand_over.py` 注释、测试 docstring |

## 复评

| # | 严重度 | 结论 | 落点 |
|---|---|---|---|
| M1 | major | 采纳 | `e2cb70b`：夹具换成真实 h2 链，断言改为钉解码出的错误码 + 与日志交叉核对的 request id |
| M2 | major | 采纳 | `e2cb70b` 后重写本主题 `README.md` 那一节，并加了同步锚点 |
| m1 | minor | 采纳 | `e2cb70b`：无文本的环只在此前没有任何一环带过文本时才出现 |
| m2 | minor | 采纳（五小条） | `9645293` + 插件 `server.py` 补上 attempt |

**没有不采纳项。** 本节按 `record-what-not-adopted` 保留，若后续有驳回再补。

## F1 与 M1 —— 同一个缺口被抓了两次，第二次更狠

两轮的 major 是同一件事的两层，值得连起来看。

**第一轮 F1** 的论证不是「测试写得不够多」，而是**做了变异**：从 `aac348e` 用 `git archive` 建副本，只把 `hand_back_block` 的接线改回 `detail = stop_reason if error is None else str(error)`，跑出 `16 passed`，并用 `inspect.getsource` + `__file__` 证明 pytest 装载的确实是被改过的那份。我复现并补上了对照：

| | 接线完好 | 接线切断 |
|---|---|---|
| `tests/unit/pipeline/test_hand_over_message.py` | 19 passed | **19 passed** |
| `…::test_an_interrupted_turn_is_handed_back_to_the_client_as_a_tool_call` | passed | **failed** |

**复评 M1 指出我的修法只挡住了那一种变异。** 它换了个更强的：不是退回 `str(error)`，而是**手搓一个形状相似的字符串**——

```python
detail = f"{type(error).__module__}.{type(error).__qualname__}: {error} [attempt {context.attempt_count}]"
```

不走 cause 链、不生成 HTTP/2 括注、完全丢掉 `request_id`。我加的三条断言（类型名、cause 原文、`attempt 1`）**全部满足**，20 条测试照样绿。根因是**夹具太弱**：它抛的是一个无 cause 的 `httpx2.RemoteProtocolError("peer closed the connection")`，所以「外层类型 + 外层文本 + attempt」这三样手工拼得出来。

它还查出我那条注释自称钉住了 request id，而 `:3179-3181` 根本没有 request id 断言——**注释描述的守卫比实际存在的守卫强**，这本身就是一种假绿。

最终修法两条：夹具改成按 httpcore→httpx 真实映射组装的 GOAWAY 链；断言改为钉 `NO_ERROR`（只有真链走 + 枚举解码能产出）与一个正则抓出的 `[request <uuid>, attempt N]`，**且把那个 uuid 与 `auto_retry_tool_not_declared` 日志里独立产生的同一个值交叉核对**——字面量满足不了它。复现复评的变异，集成测试在 `assert "NO_ERROR" in message` 上变红，单测 21 条仍全绿。

**要记住的判据**：一组测试对被测函数的鉴别力，不构成对调用它的那条链路的鉴别力；而接线测试的鉴别力，又受限于夹具的丰富度——**夹具越贫瘠，越多的假实现能通过**。两轮变异分别打掉了这两层。

## F2 与 m1 —— 同一条规则被调了两次

原规则：文本重复的丢，内层无文本的丢，最外层永远留。第一轮反例证明它会丢掉唯一有信息的类名：

- `RuntimeError('permission denied') from PermissionError('permission denied')` → 只剩 `builtins.RuntimeError: permission denied`。
- `RuntimeError() from PermissionError()` → 只剩 `builtins.RuntimeError`。

我改成「**新文本或新类名，二者有其一即入选**」。复评指出这个修法**过头了**：两个 deadline 守卫真实的 cause 链是 `TimeoutError('') -> CancelledError('')`（调查报告 §2.2(a)/(b) 实测），新规则于是产出

```
app.streaming.deadline.StreamDeadlineError: attempt exceeded its deadline; caused by builtins.TimeoutError; caused by asyncio.exceptions.CancelledError
```

而那个 `CancelledError` 只是 `asyncio.timeout` 的实现机制，不是这一轮发生的事。**给人和模型读的一句话里出现它，会把一个已经点名的超时读成取消**——那是另一种失败、另一个责任方。这比噪声更糟。

最终规则是三分支（见本主题 `README.md` 的表）：新文本 → 类型 + 文本；文本重复但类名新 → 只给类型；**无文本 → 只给类型，且仅当此前还没有任何一环带过文本**。最后那个条件同时保住了两头：deadline 的外层已经把话说完，内层不再出现；真实 reset 的外两环是静默的，内层类名与最底下的 `OSError` 都还在。

复评另指出 `__qualname__` 去重会合并两个无关模块里的同名异常（构造反例 `outer_library.CollisionError from inner_library.CollisionError`）。它自己判定这是本轮明确接受的去噪取舍、不足以单列 major，只要求在 docstring 里说明。已照做——**写清楚一个取舍，和消除它，是两件事，这里选前者**。

## F3 —— 真值判断选 cause，是正确性缺陷不是风格问题

`current.__cause__ or (...)`。Python 判定显式 cause 的判据是 `__cause__ is not None`，而异常子类可以定义 `__bool__`。于是 `raise X from falsy_cause` 会跳过作者点名的 cause，转而跟随无关的 context，或在 context 被 suppress 时直接停住。

评审的反例给 `RuntimeError("outer")` 同时挂上 falsy 的 `__cause__` 与一个 `__context__`，原实现输出的是 context。现在输出 `builtins.RuntimeError: outer; caused by __main__.FalsyCause: the actual cause`。

它同时驳回了「自定义异常在这里结构上不可达」这个可能的辩护：交付层那个 `try` 会接住 framer 抛出的任意 `Exception`（`stream.py:279` 的注释自陈这是已知边界）。**判据成立，所以不能按「实际到不了」降级处理。**

## M2 —— 权威文档在我自己手里过期了一次

第一轮之后我重写了本主题 `README.md` 的「本仓实际发出的 MCP 工具调用」一节，写的是 `aac348e` 时点的算法。**然后 `79428bb` 改了算法，而我没回头改那一节**，于是那份自称跨仓权威的文档逐字描述着旧规则，还挂着三条不再成立的实测输出。复评逐条对出了差异。

更值得记的是它的第二句：**我在处置文档里写下「三处已同步」，这句话本身掩盖了后续的再次过期**。「已同步」是一个有保质期的状态断言，写下时为真，`79428bb` 之后为假，而读者会把它当成持续为真。

修法两条：README 那一节现在带**同步锚点**（「本节与代码的同步点是提交 `e2cb70b`」），并明写「改 `describe_error` 的人必须同时改本节并更新锚点」；示例表由当前代码直接生成而不是手抄。本文件标题也改成列出四个提交，而不是笼统说「已同步」。

## F4 与 m2 —— 接收端契约

第一轮读到的 `server.py` 仍写着 "verbatim"，因为那是我派出评审之后才改的（时间差，不是分歧）。复评确认当前有效文件里已无 `verbatim` 残留，但指出 schema 描述只提了 request id、漏了同样固定存在的 attempt count，而插件 README 两项都写了——已补齐。

它还逐行核实了一件我原先说得更松的事：接收端 `server.py:65-68` 只用 `category` 与 `num_messages` 驱动 loop 与 reply，`message` 仅在 `:69-75` 传给 `build_record`、`:103` 写进 JSONL。**所以这次改动不可能改变 retry 行为**——这个结论比我原先「插件只记不解析」的说法硬，因为它是逐行核过的。

## F5 与 m2 —— 九处把未观测写成已确认

两轮加起来九条，形态高度一致，合并记在这里：

| 原句 | 问题 | 改成 |
|---|---|---|
| 测试模块 "had no test at all until now" | 已有一条真值断言 | 「此前只有一条真值断言，没有对内容有鉴别力的测试」；行号改成测试名（那个行号后来确实移动了） |
| "Every case here is a shape that was measured" | 至少五类是构造的 | 「有些是实测有些是构造，各自在原地自陈；某个形状会不会到生产，去看报告而不是本文件」 |
| "`error_code:0` is the whole of what the old field said" | 旧字段是完整 repr | 「旧字段把错误码显示成数字 `0`，从不显示名字 `NO_ERROR`」 |
| 两个 repr "differ only by a number" | 还差类名与字段集 | 「靠一个读不出的 `error_code` 区分」 |
| "the most common tear there is" | 只有一次实测，无频率样本 | 「频率不是本文件知道的事」 |
| journal「迄今所有记录都是这两类」 | 是一份文件的快照 | 「2026-08-23 读到时那四条如此，是快照不是频率」 |
| `remote_reset` 注释：「上游的决定 vs 我们自己的决定」 | h2 也会在对端引发的本地流控错误上给 `remote_reset=False` | 只声称帧由哪一侧发出，并点名这个反例 |
| "every transport tear prints the same event repr twice" | 只对 h2 那条路成立 | 点明 HTTP/1.1 重复的是 h11 文本，真实 reset 什么都不重复 |
| `remote_reset=False` 测试无 docstring | 构造用例未自陈 | 补上，并写明只声称帧方向 |

第七条最值得记：gloss 输出的 `"sent by this proxy"` **本身是准确的**（它说的是帧方向），错的是注释把它进一步推成了决定归属。**一个准确的输出配一句过头的注释，比两者都错更难发现**，因为测试不会红。

## 评审明确查过、没发现问题的（覆盖面记录）

按 `no-silently-cut-but-defer` 记下，免得日后重复投入：

- `_chain` 的循环引用防护（`A -> B -> A` 只返回前两环）。复评另测了 5/6/7 层与 6 层回环，确认截断标记不漏打也不误打：回环在进入上限分支前就由 `id` 去重停住，不会误报「还有第 7 环」。
- `_h2_gloss` 对 httpcore2 的耦合：**两轮都实测了降级路径**——把 event 在进入 httpcore2 异常前转成字符串，gloss 消失而原始 repr 完整保留。确认静默降级，不会连原文一起丢。两轮均认为该耦合可接受。
- `_link_text` 的 h2 特判无误伤：h2 4.4.1 里带 `stream_id` 的异常只有三个，前两个正是遗留裸参数文本的、被正确改写，`StreamIDTooLowError` 有自己的合法消息、不满足 `text == str(stream_id)` 因而不动。
- 四层 reset 夹具忠实于报告 §2.2(d)：类型、文本、cause 方向逐项一致，没有用被测 formatter 去算 expected，也没有靠夹具 helper 预先消掉中间层。
- 无恒真断言。`test_the_same_text_is_not_repeated_down_the_chain` 经单独变异（只删去重分支）确认会以 `assert 2 == 1` 变红。
- 选择器的状态更新顺序正确，没有 seen set 提前更新导致后续环被无故吞掉的分支。
- 测试不钉整句，只钉语义 token，措辞仍有改良空间。
- 用户亲笔 `docs/.human-controlled/upstream-retry-and-continuation.md:27-39` 只规定工具签名与机制，未规定 `message` 内容，本改动不违背它。

## 范围外、已登记

`category` 的归类问题（裸 `h2.ProtocolError` 落 `internal`）明确排除在两轮评审之外，登记在 [`../deferred.md`](../deferred.md) 第 22 条；代理发 `max_tokens` 而插件按 `truncated` 配回复，登记在第 23 条。
