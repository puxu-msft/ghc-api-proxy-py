# `7732a75` asyncio 正确性最终确认

## 结论

**pass，可以合入。** M-3 两项均已修：normative spec 现在完整写出 latent ending／failure 前 due cue 的两种 wire 形态与异常可观察性代价；两条测试分别固定窄 scheduler 形状和接受的公共 preamble 线形，名称、注释、断言与实际能力一致。

`7732a75` 未改生产源码；前七轮最终确认的 claim 实现、B-3、M-2、B-1、B-2、新口径 M-1、post-yield 打戳、单门、取消与异常传播均保持。没有发现第八种生产形态。

证据强度：**高，强到足以据此合入**。依据包括提交差异、公共路径父／子对照探针、关键路径与全量测试、相关 Ruff 及全仓 Pyright。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- HEAD：`7732a758cb127eda8755242ca35168c94b80a24f`
- 对照：`7732a75^ = 0115c58d7a284b60db81ecdb938fe504a8ff27e2`
- `src/app/pipeline/delivery/stream.py` 在本提交中无差异。
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## 1. Spec 准确性与完整性

修订后的取舍段准确区分：

1. client 已有字节、下一 pull EOF 时，due cue 是 `: ping\n\n` comment，位于 terminal frames 前。
2. client 尚无字节且 synthesis due、下一 pull EOF 时，due cue 是 `message_start`；它置位 `client_has_bytes`，EOF 后带出 `message_delta` 与 `message_stop`，把原本零字节的回复变成“已开始、无内容块、已在 wire 上正常封口”的 Anthropic message。
3. 下一 pull 若失败，先发生的 cue downstream write 可能自身失败／取消，使尚未拉取的异常不被当前消费链观察；这是明示接受项。
4. 当前 event 的 assembler exception 仍在 claim 前传播，不属于接受项。

公共父／子对照与 spec 完全一致：

```text
$ uv run python /tmp/compare_latent_eof_preamble_0115c58.py
{'0115c58^': [], '0115c58': ['message_start', 'message_delta', 'message_stop']}
```

当前模块实际为 `7732a75`，脚本输出标签沿用创建时的 `0115c58`。本提交未改生产源码，所以该线形与新增测试的 oracle 相同。

没有再发现夸大保证：spec 明确把保证收窄为“已 ready 的 task EOF／异常先行、当前 assembler exception 先行；下一 pull 尚未知时 due cue 先行”。它不再声称所有 extra cue 都只是 comment，也不再声称未来 pull failure 必然可观察。

结论：**准确且完整。**

## 2. 两条测试的名称、能力与分辨力

### `test_the_schedule_adds_no_turn_between_an_event_and_an_ending`

名称与注释已收窄到它真正覆盖的 ready-path 形状：scheduler yield 一个 event-bearing Pull；consumer 离开一段时间；下一 pull 立即 EOF；中间不新增 scheduler record。测试同时明确说明 pending task deadline timeout 的另一分支会合法产生 `event=None` Pull，本构造不覆盖它。

`len(pulls) == 1` 与 `pulls[0].event is not None` 正好断言该窄性质，不再作“每个 turn 都带 event”的全称声明。

### `test_a_due_preamble_goes_out_even_though_the_stream_is_already_over`

测试走公共 `stream_delivery`，使用 `ping=0`、`synthesis=1`、`SlowAssembler(1.05s)` 与 one-event-then-EOF，精确断言：

```python
events_of(chunks) == ["message_start", "message_delta", "message_stop"]
PING_FRAME not in chunks
```

它固定的正是 spec 新接受的高影响 preamble 形态，而不是较便宜的 comment 形态。父提交 `0115c58^` 产出 `[]`，当前产出三帧；因此测试有分辨力，不是同源恒真断言。

旧强性质被明确拒绝后删除对应测试是正当政策更新；现在的窄 scheduler test 与公共 trade-off test 合起来分别固定机制边界和产品可见结果，不是把失败测试改写成无关的绿色测试。

结论：**两条均名副其实且有分辨力。**

## 3. 前七轮修复保持情况

`7732a75` 只修改 spec 与 tests，生产 `stream.py` 与 `0115c58` 相同。关键探针复核：

- B-3：两次慢装配的首 ping 仍约 1.05s，而非 2.10s。
- M-2：malformed `index` 仍在 0 chunk 后直接抛 `ValueError`。
- B-1：200000 ready delta 在约 6.81s 内产生 6 枚 ping，0 次 zero timeout。
- B-2：`ping=0/synthesis=1` 与 `ping=2/synthesis=1` 均约在 1.00s、source 尚未结束时产生首字节。
- M-1：已 ready 的 task EOF／异常仍在 Pull 产生前离开；latent next-pull ending 按新 spec 接受 due cue 先行。
- claim 闭包仍由唯一生产 caller 串行调用：`wrote=True` 时 0 次，`wrote=False` 时恰好 1 次；未发现重复调用、漏调用或并发可变状态路径。
- post-yield 打戳、`client_has_bytes` 单门、取消传播、普通 upstream exception、assembler exception、held-back policy 均由现有回归继续覆盖。

结论：**前七轮最终确认的修复均保持。没有发现第八种生产形态。**

## 验证结果

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
31 passed in 25.85s

$ uv run pytest -q
1348 passed, 3 skipped in 123.72s

$ uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py
All checks passed!

$ uv run ruff check src tests
All checks passed!

$ uv run pyright
0 errors, 0 warnings, 0 informations
```

完整性说明：字面执行无路径参数的 `uv run ruff check` 仍会命中受追踪的既存 `exp/carrier-v2/*`、`exp/phase2-acceptance/*` 问题并退出 1；这些文件不在本候选差异中，相关 `src tests` 以及本次目标文件均干净。故 coordinator 所称“Ruff 干净”若指候选／产品与测试范围已确认；若指 repository root 的所有受追踪实验文件，则该全称不成立，但不归因于 `7732a75`，不阻塞本次 asyncio 候选。

## 最终裁决

- blocker：0
- major：0
- minor：0
- M-3 spec：已修
- M-3 tests：已修
- 前七轮修复：全部保持
- 第八种生产形态：未发现
- verdict：**pass**
- 合入判断：**`7732a75` 可以合入。**
