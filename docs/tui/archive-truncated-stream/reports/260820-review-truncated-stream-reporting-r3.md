# 定向复核 R3：B1 与 S1 的修法

- 复核对象：R2 报告 `docs/tmp/260820-review-truncated-stream-reporting-r2.md` 中 B1（门太宽）与 S1（`_tracked_delivery` 不关闭内层生成器）两条的处置
- 复核时间：2026-08-20 13:55～14:10 UTC
- 复核者：独立评审 subagent（只读；未修改仓库任何文件）
- 结论：**pass**（0 blocker，0 should，2 nit——均为注释／理由层面，不要求改行为）

只复核这两处 delta，其余未重看。快照：`src/app/server/pipeline_app.py` = `ee45811a501bbec818cc88a718a51f242443ebb7bba3d03643e58c25a9eb1280`。

## 1. B1：修好了，且你的版本比我建议的正确

端到端实测（`/tmp/probe7_tear_after_delta.py`，上游发完含 `message_delta{stop_reason,usage}` 的全部内容后抛 `httpx.ReadError`）：

```
[FAIL] 13:59:38 200 POST /v1/messages 4ms ↓0B ↑11 ↓22 end_turn: stream failed before a terminal event: connection reset by peer
downstream saw message_delta: False
downstream saw message_stop: False
```

R2 里那条绿行（`[ OK ] ... end_turn`，无 detail）已经消失。这一行同时出现 `end_turn` 与撕断，**不构成 R2-S3 说的自相矛盾**：那时的矛盾在于「有 reason」与「什么都没结束」互斥，而这里 detail 说的是「流失败了」，与「上游曾经给过 reason」完全相容，读者拿到的是两个都为真的事实。

### 关于多出来的 `self.failure is None`：应当保留，理由需要改一句

**结论先说：不引入任何问题，且比我建议的 `not (self.drained and terminal.stop_reason)` 更正确。** `_ending()` 本来就先查 `failure`，门与它保持同一顺序是对的；两者若不一致，就会出现「门放行了、但 `_ending()` 本来会报 failure」的缝。

但你给的触发场景**目前不可达**，实测：

```
raised during the loop: RuntimeError cleanup blew up | drained = False
aclose() on the exhausted generator: no exception
with an early break -> drained = True | aclose raised: RuntimeError cleanup blew up
```

即：正常排空之后 `chunks` 已经耗尽，`aclosing.__aexit__` 里的 `aclose()` 是空操作、抛不出任何东西；生成器 `finally` 里的异常会在**循环内**就浮出来，那时 `drained` 还没被置上，走的是 `failure` 那一支。所以「排空后清理失败」这个状态在当前形状下产生不出来。

它什么时候会变成活的？**循环一旦长出提前 `break`**（第三行实测）：那时 `drained = True` 照样执行，而 `chunks` 仍然活着，它的 `aclose()` 就能抛。

所以我的建议是：条件留着，把注释里的理由换成这两句——一是与 `_ending()` 的判定顺序保持一致（这是它今天真正在做的事），二是循环一旦有提前退出它就立刻生效。照现在的写法，下一个人会去为这个分支写测试，然后发现造不出这个状态，进而怀疑代码写错了。

顺带说明为什么我不建议为它补测试：造这个状态需要一个 `aclose` 会抛的假生成器 + 一个不存在的 `break`，属于为不可达分支预铺状态空间。真到循环长出 `break` 的那天，那次改动自己会带上它的测试。

### 新测试

`test_a_tear_after_the_stop_reason_is_still_a_tear` 有鉴别力，且鉴别的正是这个门：先断言 `assembler.terminal.stop_reason == "end_turn"`（证明确实走到了被豁免的那条路径，而不是碰巧从别处红的），再要求 `status == "fail"` 与异常原文上线。docstring 也点明了为什么另一条撕断测试抓不到它（那条在第一个块后就断，reason 从未被记下，门根本到不了）。你的变异验证与我实测到的绿行字样一致。

## 2. S1：修好了

实测（`/tmp/probe8_tracked_delivery_close.py`，上游发完第一个块后挂起，记录其 `finally`）：

```
after aclose() returned: ['upstream released']
```

R2 时是 `UPSTREAM STILL OPEN`，要等若干事件循环回合才被 finalizer 收掉；现在在 `aclose()` 返回时就已释放，与下一层立的标准一致。分类不受影响，同一次运行照常打出 `[GONE] ... delivery stopped before upstream finished`。

`accounting.drained = True` 放在 `async with` 内部是对的：放到外面会让「排空后 aclose 抛错」变成排空成功，与 B1 的门自相矛盾。`except Exception` 在 `async with` 之外、`try` 之内，因此 `__aexit__` 抛出的异常也会被记进 `failure`——这一点结构上成立。

### N-1（nit）新的排序耦合，说明即可，不建议改

`chunks.aclose()` 现在跑在 `accounting.finish()` **之前**（`__aexit__` 先于外层 `finally`）。好处是上游先释放再记账；代价是记账与日志行的及时性现在挂在清理链的及时性上——若某天 `stream_delivery.aclose()` 挂住，这个请求就会既不下 footer 也不出日志行。今天不会：下一层的 `test_a_pull_in_flight_does_not_outlive_the_delivery` 正是钉这个的，我上面那次实测也走的是同一条路。不建议为此重排结构（把 `finish()` 提前会把 S1 的收益丢掉），只是把这条耦合记下来。

## 3. 其余四条的抽查

- **S2**：源码注释与 `implementation.md` 都已改写，且**明写了修正本身**（「理由**不是**『无读者故推迟决定』……不写是销毁信息」）。这比只换结论更有用：接手的人会看到那条被否掉的推理，不会再推一遍。真正的理由（保守、维持 `reply is not None ⇒ 回复已完成` 这个 hooks／History 现有契约；STR-04 已点名要 failed History）准确。
- **N1**：`rg -n "docs/tmp" src/` 在本切片内零命中，已核。（唯一剩下的一处是 `translation_driver/openai_responses.py:146`，属并行会话的另一切片，不在本次范围，仅告知。）
- **N2**：`_ending()` docstring 那段补得诚实——「nothing here can tell the two apart, and the line should not claim to」，比硬编一个分不出来的区别好。
- **N3**：已并入 `implementation.md` 同一条登记，两种分叉形态都写明了。

## 4. 关于你提到的 deselect 与我这边的全量结果

我这边的全量跑不出你那个数字，两边看到的不是同一棵树：

- 你报 1404 passed / 2 skipped / 1 deselected。
- 我这边（13:59 与 14:02 两次）：**17 failed / 1388 passed / 2 skipped，无 deselected**。`tests/unit/test_lifecycle_pidfile.py` 单独跑 **23 passed**，包括你说被 deselect 的那条。

17 条失败全部集中在 lifecycle／drain：`tests/unit/test_lifecycle_cleanup.py` 的 `'StubAdapter' object has no attribute 'begin_draining'`（8 条）、`tests/integration/test_standalone_lifecycle.py` 的 `TimeoutError`、`test_standalone_process.py` 的 drain 断言。对应的 `src/app/lifecycle/{adapter,listener,standalone}.py` 三个文件此刻是 dirty 的，`begin_draining` 是一个正在落地的新协议方法，测试替身还没跟上。

**与本切片无关，我认同你不要去动它**：那是同伴正在改的产品代码与它自己的替身之间的不同步，改法应由那个切片选。我只是把「我这边的全量不是绿的」如实记下来，免得这份复核被当成「全量绿」的证据。

本切片自己的证据是干净的：`tests/http/test_pipeline_app.py`、`tests/unit/test_stream_delivery.py`、`tests/unit/test_request_log.py`、`tests/unit/test_sse_assembly.py` 合计 **149 passed**；delta 涉及文件 `ruff check` 全通过、`pyright` 0 errors。

## 5. Verdict

**pass。** B1 已闭合并经端到端实测确认，S1 已闭合并经实测确认，S2／N1／N2／N3 的处置准确。剩下两条 nit 都在注释层面：`failure is None` 的理由需要换一句（当前场景不可达，真正作用是与 `_ending()` 同序 + 为将来的 `break` 预留），以及新的排序耦合值得记一笔。两条都不阻塞落地。

---

附：本轮探针复用 `/tmp/probe7_tear_after_delta.py`、`/tmp/probe8_tracked_delivery_close.py`，新增一次性内联脚本验证 exhausted-generator 的 `aclose` 语义（未落盘）。
