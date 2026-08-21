# `c897aec` asyncio 控制流与清理语义复评

## 结论

**needs-fix，`c897aec` 当前不能合入。** M-2 已修，B-1、B-2、M-1、取消与 task-level 异常优先级均仍成立；`wrote` 对真实 chunk 与 held block 的区分也正确。

但“最后一个替身已拆掉”的声称可被第七种形态证伪：`cue_due` 是 scheduler 在 assembler 处理**之前**采的时间快照，delivery 却在 assembler 处理**之后**使用它。若第一个正常 event 的同步装配跨过 deadline，而 `cue_due` 采样时仍为 false，delivery 成功装配且未写字节后不会重新结算；它马上拉第二个 ready event。第二个 pull 才得到 `cue_due=True`，但 delivery 又先同步装配第二个 event、之后才发 cue。于是一个本可在第一次装配结束时发送的 ping，被推迟到第二次装配结束。

公共路径对照中，`sse_ping_interval=1`、两次各 1.05s 的成功但无输出装配，使父提交在约 1.05s 发首 ping，`c897aec` 在约 2.10s 才发。第一次装配结束时 event loop 已重新获得控制权，延迟第二个 1.05s 不是“同步代码运行时无法调度”的不可避免部分，而是 stale `cue_due` + “下一 event 先处理”的新抢占。

严重度：**blocker**。它重新违反 client 已有字节后不得静默超过 interval 的核心判据，并且直接命中本轮要求攻击的“scheduler 是否仍用看不见的东西做决定”。

证据强度：**高，强到足以阻止当前候选合入**。构造走公共 `stream_delivery`、合法 `BlockAssembler` protocol、真实 inner `AnthropicAssembler` 与真实 block buffer；修复前后唯一变量是提交。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`c897aec4b464f00b8eb7a46447f17b3e8e3b0ccd`
- 对照：`c897aec^ = b1eb2ee3e80fe82726053738f93f6e4f836b58f6`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### B-3：`cue_due` 在装配前采样、装配后消费，ready event 可再次延迟 cue

- 严重度：**blocker**
- 把握程度：**高；公共路径修复前后对照**
- 位置：`src/app/pipeline/delivery/stream.py:114-117` 与 `:207-225`。

scheduler 现在产出：

```python
item = task.result()
yield _Pull(event=item, cue_due=settle())
```

而 delivery 先做：

```python
wrote = False
if pull.event is not None:
    for block in assembler.push(pull.event):
        ...
if not pull.cue_due or wrote:
    continue
```

`cue_due=False` 只说明**装配开始前**尚未到期，不能说明**装配成功结束后**仍未到期。`wrote=False` 又只说明本 event 没产生字节，恰好是应该在成功装配后重新问 deadline 的路径；当前却因 `not pull.cue_due` 直接 continue。

构造 `/tmp/compare_slow_assembly_cue_delay_c897aec.py`：先完整交付 block 0，使 client 已有字节；随后两个属于未闭合 block 1 的 ready event 均成功装配但不释放 block，每次同步装配占 1.05s。interval 为合法整数 1s。

```text
$ uv run python /tmp/compare_slow_assembly_cue_delay_c897aec.py
{
  'c897aec^': {'first_ping_seconds': 1.0507370170089416},
  'c897aec': {'first_ping_seconds': 2.100833128031809}
}
```

父提交的 M-2 缺陷是 cue 在第二个 event 之前发；它虽然错误地没先验证第二个 event，但 timing 上在第一次成功装配结束后立即回答 due ping。`c897aec` 为优先验证第二个 event，把 cue 带在第二个 `_Pull` 上，并在其装配后才回答，于是多延迟整整一次 event processing。

这不是构造里 event loop 阻塞本身造成的全部迟延：第一次 1.05s 装配结束时，代码已经回到可执行 Python 控制流，deadline 已过、上一个 event 也已成功且没写字节；此刻可以安全发 cue。当前选择继续拉并处理第二个 ready event，才产生可避免的第二段 1.05s 静默。

同一形态也适用于 preamble：若 `cue_due` 在装配前 false，而装配跨过 `response_headers_deadline` 且没有真实输出，下一 ready event 会先被处理，再发合成；首字节上界被多推迟一个 event-processing 时长。

修复判据而非指定实现：normal event 的 assembler processing 成功后，delivery 必须依据**此刻**的 deadline 与“这次是否真的写了”共同决定 cue，不能只消费装配前的 bool 快照。M-2 又要求 processing 异常先行，所以正确决策点只能在成功处理 event 之后；scheduler 若仍独占可变 ping schedule，需要把可重检／可确认的 deadline 状态交给 delivery，而不是只交一个 precomputed boolean。若真实 chunk 已产生，它继续解除义务；若无 chunk，则用处理后的时刻重新判定。

这就是第七种形态：**“装配前已到期”仍是“装配后是否欠 cue”的替身量。**

## 1. M-2 复评

按要求重跑 `/tmp/compare_preamble_before_assembler_error_b1eb2ee.py`。脚本动态加载 `b1eb2ee^ = 87b8899` 作为正确异常优先级对照，当前 import 指向 `c897aec`；输出标签沿用旧提交名：

```text
$ uv run python /tmp/compare_preamble_before_assembler_error_b1eb2ee.py
{
  'b1eb2ee^': {
    'message_start_count': 0,
    'error': "ValueError: invalid literal for int() with base 10: 'not-an-int'"
  },
  'b1eb2ee': {
    'message_start_count': 0,
    'error': "ValueError: invalid literal for int() with base 10: 'not-an-int'"
  }
}
```

当前实现不再先发 `message_start`；`assembler.push(pull.event)` 的 `ValueError` 在任何 cue 判断前传播。M-2 真正修掉。

新增 `test_an_unassemblable_event_fails_before_the_preamble` 使用同一真实 assembler failure，断言 `ValueError` 且 `chunks == []`。它在父提交会先收一个 chunk，当前通过；测试有分辨力。

## 2. `wrote` 短路复评

### 明明写了字节却仍发 cue

没有这条路径。`_commit` 返回的每个 `chunk` 都在同一循环中执行：

```python
client_has_bytes.set()
wrote = True
yield chunk
```

只要至少一个真实 chunk outward yield，`wrote=True`，后面的 cue 分支被短路。`message_start`、block frames 都经这条路径；chunk 均为非空 SSE frame。outer 恢复后给 `last_write` 打戳，下一 due 从实际 handoff 重新计时。

### 明明欠着却被 `wrote` 吞掉

在 buffer policy 扣住 block 时，`_commit(...)` 返回空列表，循环体不执行，`wrote` 保持 false；若 `pull.cue_due=True`，preamble／ping 仍发送。`full` 与 `until-tool-use` 的参数化测试继续覆盖这点。

若 `_commit` 释放一个或多个 held block，真实 bytes 确实已解除同一义务，短路 cue 正确。多个 chunk 中第一个 yield 前已置 `wrote=True`；如果 downstream 在该写上失败，流随即关闭，不存在随后还应发送 cue 的活路径。

### 新发现

`wrote` 自身正确；B-3 出在 `pull.cue_due=False` 的另一半短路。成功装配、未写字节、但处理期间 deadline 刚到期时，`not pull.cue_due` 使用了 stale snapshot。

## 3. B-1、B-2、M-1 与 busy loop

### B-1

```text
$ uv run python /tmp/probe_ready_upstream_ping_starvation.py
{'deltas': 200000, 'elapsed_seconds': 7.182832906022668, 'ping_count': 7, 'chunks_out': 13, 'zero_timeouts': 2, 'zero_timeouts_with_done_task': 2}
```

普通快速 ready event 仍不会饿死 keep-alive。B-3 是 event processing 本身跨 deadline 时的下一层形态。

### B-2

两组合法配置仍在约 1s、source 运行期间得到首字节：

```text
ping=0, synthesis=1:
  parent first=1.3005s, running=false
  current first=1.0001s, running=true

ping=2, synthesis=1:
  parent first=1.3003s, running=false
  current first=1.0001s, running=true
```

`full`／`until-tool-use` 的独立探针也均约 1.0001s。B-2 在快速 normal processing 下成立；B-3 说明处理跨 deadline 时仍会多延迟一个 event。

### M-1

ready EOF／task-level `RuntimeError` 仍在 `_Pull` 产生前从 `task.result()` 离开。旧探针因返回类型改为 `_Pull` 而显示首项类型不同，但没有任何额外 pull／cue：

```text
'eof':   ['_Pull', 'StopAsyncIteration']
'error': ['_Pull', 'RuntimeError: next pull failed']
```

M-1 仍成立。

### 取消与异常

取消测试、upstream mid-stream error 测试与新 assembler error 测试均通过。`_Pull` 是 frozen record，没有捕获异常；delivery processing failure 发生在 cue 判断前。

### busy loop

- pending path 仍先 `settle()`，yield `_Pull(event=None, cue_due=True)`；keep-alive due 时 schedule 已前推，preamble due 时 caller 第一次处理后置位 Event。
- ready path `settle()` 为 true 时同样已前推 keep-alive；caller 不写且 synthesis disabled 时，raw deadline 在未来，不会每 event 产生 cue。
- `_Pull` 本身没有新增循环；每个 record 要么携带一个正常 event，要么对应一次 deadline wakeup。

未发现新的恒0／无限 cue busy loop。B-3 是有限但可任意长的 cue 延迟，不是空转。

## 4. “最后一个替身”声称评估

该声称被 B-3 推翻。scheduler 确实不再决定“现在写什么”，但仍决定并冻结“这个 pull 的 cue 是否 due”；delivery 在同步装配完成后把这个旧 bool 当作当前事实。

调度层看不见的量还有两个：

1. assembler processing 是否成功——M-2 已通过先 processing 修正。
2. assembler processing 花了多久、结束时 deadline 是否新近到期——B-3 尚未修。

因此正确边界不是简单的“scheduler 计算、delivery 执行”，而是：scheduler 可提供 pull 与 deadline 状态，delivery 必须在成功 processing 后用当前时刻完成最终决策。数据可以跨层流动，决定不能基于失效快照。

## 新测试评估

- `test_an_unassemblable_event_fails_before_the_preamble` 精确覆盖 M-2，正负路径有分辨力。
- 修改后的 EOF 测试断言后续 pull 不带 `cue_due`，与新 `_Pull` API 对齐。
- 现有 ready keep-alive／preamble 测试的 assembler processing 很快，因此看不见 B-3；需要一个“第一个 event processing 跨 deadline、成功且无输出，第二个 event ready”的构造才能固定第七种形态。

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
29 passed in 22.68s

$ uv run pytest tests/unit/test_stream_delivery.py::test_an_unassemblable_event_fails_before_the_preamble tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_preamble tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_keep_alive tests/unit/test_stream_delivery.py::test_an_end_of_stream_is_not_preceded_by_a_keep_alive tests/unit/test_stream_delivery.py::test_a_cancelled_consumer_gets_its_cancellation_back tests/unit/test_stream_delivery.py::test_an_upstream_failure_reaches_the_caller tests/unit/test_stream_delivery.py::test_a_held_back_block_does_not_disarm_both_guards -q
8 passed in 10.47s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

这些绿确认 M-2、快速处理下的 B-1／B-2、M-1、取消及异常；不覆盖 B-3 的跨-deadline processing latency。

## 最终裁决

- blocker：1
- major：0
- minor：0
- M-2：已修
- B-1／B-2／M-1：仍已修，但 B-3 揭示 slow-processing 子形态
- 第七种形态：B-3，装配前 `cue_due` 快照替代装配后当前 deadline
- verdict：**needs-fix**
- 合入判断：**`c897aec` 不能按当前形态合入。保留 event+cue record 与 assembler-error-first 方向，但必须在成功 processing 且没有真实 write 后按当前时间重新结算，不能仅依赖装配前的 `cue_due`。**
