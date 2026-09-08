# `0115c58` asyncio 控制流与清理语义复评

## 结论

**needs-fix，`0115c58` 暂不能合入。** 生产控制流本身通过：B-3、M-2、B-1、B-2 均已修；M-1 在新裁决的窄口径下成立；没有找到 claim 闭包的第八种生产状态缺陷或 busy loop。

阻塞点在这次**行为裁决的规范与回归证据**，不是 claim 实现：spec 把被接受的额外 cue 写成“多发一枚注释”，但 client 尚无字节时实际 cue 是 `message_start`，随后 EOF 会再产生 `message_delta`／`message_stop`。父提交同一构造输出空，当前输出一个完整的无内容 Anthropic message。这个差异比额外 SSE comment 强，必须在 normative spec 中明示后才能称裁决完整。

替换旧 M-1 测试本身不是“为了绿而改测试”：旧断言对应的强性质已被一个技术上站得住的契约取舍明确拒绝，删除它是正当的。但替代测试的名称／注释声称 scheduler “从不制造自己的 turn、每个 turn 都带 event”，与实现的 deadline timeout 路径 `_Pull(event=None, ...)` 直接矛盾；而且该测试从不调用 `claim()`，没有固定新裁决接受的“due cue 可先于下一 pull 的 EOF／异常”。它不能作为新行为的权威回归。

严重度：**major**。代码算法可保留，但项目要求 observable behavior 的 spec 先准确冻结；当前 spec 低估 wire 影响，替换测试又没有钉住所选行为，故不放行。

证据强度：**高，强到足以要求修正文档与测试后再合入**。潜在 EOF 构造走公共 `stream_delivery`，动态加载父提交对照，输出差异可直接观察。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`0115c58d7a284b60db81ecdb938fe504a8ff27e2`
- 对照：`0115c58^ = c897aec4b464f00b8eb7a46447f17b3e8e3b0ccd`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### M-3：spec 将 latent-EOF 前的额外 cue 错写成注释，替换测试未固定新裁决

- 严重度：**major**
- 把握程度：**高；公共 wire 修复前后对照 + 测试源码直接矛盾**
- 位置：`docs/agents/delivery-keepalive/spec.md` 的 §2 新增取舍段；`tests/unit/test_stream_delivery.py::test_the_schedule_never_manufactures_a_turn_of_its_own`。

#### 规范低估实际输出

spec 写：

> 延后求值会偶尔多发一枚落在流末或失败之前的注释……漏掉一次该发的保活是违约，多发一枚不是。

`claim()` 同时结算 keep-alive 与 preamble。client 已有字节时，extra cue 确实是 `PING_FRAME` comment；client 尚无字节且 synthesis due 时，extra cue 是 `message_start`，而 EOF 后 `_deliver` 因 `client_has_bytes` 已置位还会发送 terminal frames。

构造 `/tmp/compare_latent_eof_preamble_0115c58.py`：ping disabled、synthesis=1；一个正常 event 成功但无 block，装配 1.05s 后 claim due，下一 pull 立即 EOF。

```text
$ uv run python /tmp/compare_latent_eof_preamble_0115c58.py
{
  '0115c58^': [],
  '0115c58': ['message_start', 'message_delta', 'message_stop']
}
```

因此被接受的取舍不是“偶尔多一枚无内容注释”而已，而是“deadline 已到时，即使下一 pull 会立即 EOF／失败，也先履行当前 owed cue；若 client 尚无字节，这会把原本空 body 变成一个已开始并正常封口的无内容 Anthropic message”。这不必推翻选择，但必须原样写进 spec，不能用 comment 的低影响形态替代全体。

同理，下一 pull 若立即失败，preamble／ping 的 downstream send 仍可能先失败并使那个未来异常不被当前消费链观察；spec 已称这是接受项，但应写“cue”而非只写“注释／保活”。

#### 测试替换的正当与不足

旧测试断言“due 之后下一 pull EOF 时不得先有 cue”。新裁决明确拒绝这个强性质，因此删除旧断言**是正当的政策更新，不是单纯把失败测试改绿**。

但替代测试的全称描述为假：

```python
async def test_the_schedule_never_manufactures_a_turn_of_its_own()
# ... every turn it produces carries an event
```

pending task 因 deadline timeout 时，scheduler 明确产生 `_Pull(event=None, claim=claim)`。所以 scheduler 会制造一个没有 event 的 deadline turn；只是该测试的单 event → consumer sleep → next EOF 构造没有走 pending-timeout 路径。

测试还只收集 `_Pull`，从不调用 `pull.claim()`。它证明“scheduler 不再在下一 pull 前额外 yield 一个 record”，却不证明所选政策“成功装配后 claim due 时，cue 可以先于尚未拉取的 EOF／异常”。建议保留窄形状测试并准确命名，再新增／改写一个 public-path case，钉住上面的两种 accepted wire shape，至少明确 preamble case不是 comment。

## 1. B-3 与 M-2 复评

### B-3

按要求重跑 `/tmp/compare_slow_assembly_cue_delay_c897aec.py`。脚本动态加载 `c897aec^ = b1eb2ee` 作约 1.05s 正对照，当前 import 指向 `0115c58`；标签沿用旧提交名：

```text
$ uv run python /tmp/compare_slow_assembly_cue_delay_c897aec.py
{
  'c897aec^': {'first_ping_seconds': 1.050755621981807},
  'c897aec': {'first_ping_seconds': 1.050526525999885}
}
```

当前在第一次成功无输出装配结束后立即调用 claim，约 1.05s 发 ping，不再等第二次装配到 2.10s。B-3 真正修掉。

新增 `test_a_deadline_that_falls_due_during_assembly_is_not_missed` 在父提交实测约 2.1006s、当前小于2s，测试有分辨力。

### M-2

```text
$ uv run python /tmp/compare_preamble_before_assembler_error_b1eb2ee.py
parent: message_start_count=0, ValueError
current: message_start_count=0, ValueError
```

`assembler.push()` 在 claim 前执行；畸形 event 仍无任何 chunk、直接传播 `ValueError`。M-2 仍成立。

## 2. B-1、B-2 与新口径 M-1

### B-1

```text
$ uv run python /tmp/probe_ready_upstream_ping_starvation.py
{'deltas': 200000, 'elapsed_seconds': 6.814968150982168, 'ping_count': 6, 'chunks_out': 12, 'zero_timeouts': 0, 'zero_timeouts_with_done_task': 0}
```

ready event 不再饿死 keep-alive。

### B-2

```text
ping=0, synthesis=1:
  parent first=1.3008s, running=false
  current first=1.0001s, running=true

ping=2, synthesis=1:
  parent first=1.3006s, running=false
  current first=1.0001s, running=true
```

两个 deadline 仍在 processing 后当前时刻被 claim；preamble 不再依赖 ping 偶然唤醒。

### 新口径 M-1

- 已经 ready 的 EOF／task exception：`task.result()` 在 `_Pull` 产生前离开，仍先行。
- 当前 event 的 assembler exception：`assembler.push()` 在 claim 前执行，仍先行。
- 下一 pull 才会暴露的 EOF／异常：成功 processing 且 claim due 后允许 cue 先行，这是本轮明确选择，不再称缺陷。

这三个范围在代码与 spec 的结构上可区分；唯一问题是 spec 把第三类 cue 缩写成 comment。

## 3. 裁决本身

技术上，这个取舍站得住：在成功处理当前 event、确认没有真实字节、且 deadline 此刻已经到期时，等待一次尚未发起的 lookahead 才决定是否履约，会重新引入 B-3／B-1 类型的漏发或延迟。§2 的明确判据是 client silence 的上界，extra cue 不破坏内容语义；因此选择“当前 owed cue 优先于未知的下一 pull”有一致依据。

限定条件必须写足：

1. extra comment 仅是 client 已有字节时的形态。
2. client 尚无字节时是 synthetic `message_start`，随后可能有 terminal frames。
3. 当前 event processing failure 仍优先；未来 pull failure 不优先。
4. 这是无 lookahead 设计下的明确产品取舍，不是“EOF 后绝不会发 cue”的技术事实。

按这些条件收窄后，我支持该裁决。

## 4. claim 闭包与第八种形态攻击

### 调用次数

生产 `_deliver` 只有一个调用点：

```python
if wrote or not pull.claim():
    continue
```

- `wrote=True` 时 Python short-circuit，claim 调用 0 次；真实 bytes 与 outer post-yield timestamp 解除义务，schedule 无需前推。
- `wrote=False` 时调用恰好 1 次；若 due，keep-alive schedule 当场前推，或 preamble 由随后 `client_has_bytes.set()` one-shot 退出。

同一个 `_Pull` 不会在生产循环中复用。`_events_with_ping` yield 一个 Pull 后保持 suspended，直到 `_deliver` 完成 processing／claim 并请求下一项；不存在多个 outstanding Pull 并发调用同一个 closure。

### 重复调用与完全不调用

closure 不是公开幂等 API：外部若手工保存 Pull 并重复调用，preamble 在 Event 尚未置位前可连续返回 true；若在生成器关闭后调用，它仍可因闭包引用存活。可是 `_Pull`、`_events_with_ping` 均为 private，生产 caller 的单次／短路结构排除了这些路径。没有具体生产 actor 能触发，因此不构成当前缺陷。

完全不调用只发生于：

1. `wrote=True`——真实写解除义务，正确。
2. assembler 抛异常——流终止，schedule 无后续消费者，正确。
3. `_deliver` 被取消／关闭——同样没有后续 cue 义务；D-1 的 pending pull cleanup 是既存独立缺陷。

### 可变量读取

claim 在 delivery processing 成功后读取 `ping_deadline`、`last_write`、`client_has_bytes`，不是 stale snapshot。三者在同一消费 task 中串行访问；inner generator suspended，outer 没有并发写。若 claim due 后发送真实 cue，schedule／Event 各自更新；若 claim 前已有真实 write，短路并由 last_write 提供新基准。

结论：**没有构造出第八种生产形态。** closure 的滥用面存在于 private API 的非生产调用，但当前唯一 caller 约束充分、可机械核对。

## busy loop、取消与异常

- pending timeout Pull 的 claim 在 delivery 立刻调用；keep-alive due 时前推 schedule，preamble due 时随后置位 Event。
- ready normal Pull 的 claim 在成功 processing 后调用；未到期返回 false，不生成 cue。
- client 无字节且 synthesis disabled 时，due keep-alive claim 前推 schedule，caller吞掉 cue；不会每 event 都 due。
- claim 若因早醒返回 false，scheduler 恢复后按同一 deadline 再 wait；无状态不变的无限 outward cue。

取消测试与 upstream／assembler 异常测试全部通过。closure 同步执行，不捕获 `CancelledError` 或其它异常。

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
30 passed in 24.81s

$ uv run pytest tests/unit/test_stream_delivery.py::test_a_deadline_that_falls_due_during_assembly_is_not_missed tests/unit/test_stream_delivery.py::test_an_unassemblable_event_fails_before_the_preamble tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_preamble tests/unit/test_stream_delivery.py::test_an_always_ready_upstream_does_not_starve_the_keep_alive tests/unit/test_stream_delivery.py::test_the_schedule_never_manufactures_a_turn_of_its_own tests/unit/test_stream_delivery.py::test_a_cancelled_consumer_gets_its_cancellation_back tests/unit/test_stream_delivery.py::test_an_upstream_failure_reaches_the_caller tests/unit/test_stream_delivery.py::test_a_held_back_block_does_not_disarm_both_guards -q
9 passed in 12.58s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
0 errors, 0 warnings, 0 informations
```

这些绿确认 B-3、M-2、B-1、B-2、新口径 M-1、取消及已覆盖异常；M-3 来自裁决文本与替代测试能力边界，不是测试套件执行失败。

## 最终裁决

- blocker：0
- major：1
- minor：0
- B-3／M-2／B-1／B-2：已修
- M-1：按“已 ready 的结束先行、未来 pull 未知”口径成立
- 第八种生产形态：未发现
- verdict：**needs-fix**
- 合入判断：**`0115c58` 的 claim 实现可保留，但须先把 spec 的“额外注释”修正为完整 cue 行为，并用有分辨力的测试固定所选 latent-EOF／failure 取舍；当前不能合入。**
