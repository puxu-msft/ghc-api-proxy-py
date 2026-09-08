---
report_id: retry-continuation-review-round-seven
attempt_id: round-seven-0f2e7f1-gpt
status: in-review
reviewed_at_rev:
  main: 0f2e7f1066511ffcec5a0069d3661997e2063565
  parent: da0c4b57f59727e74715fc21e7d0693ff069fd65
  criteria_docs: 0f2e7f1066511ffcec5a0069d3661997e2063565
  dot_dev: d201cf79c71ff27751eadeae94bb43aa0dc370cb
reviewed_at: 2026-08-24
---

# 第七轮独立评审：cleanup 完成顺序与 replay 记账

## 评审范围

本轮评审主仓提交 `0f2e7f1066511ffcec5a0069d3661997e2063565` 及其父提交 `da0c4b57f59727e74715fc21e7d0693ff069fd65`，重点覆盖 `_counted_upstream` 的 cleanup 委托、`raise_with_cleanup_under` 的异常链语义、`_reopen` 的 replay 记账判据、新增测试的分辨力、pyright 修法，以及本轮新增或改写的事实性注释。产品判据来自提交态的 `docs/.human-controlled/upstream-retry-and-continuation.md`、`client-side-block-delivery.md`、`lifecycle.md`、`request-pipeline.md`；实现记录与历史依据来自 `.dev@d201cf7` 的本主题 living docs 与既有评审原件。

所有实现读取与验证都针对用户解包的 `/home/xp/.claude/jobs/06dcd6c1/tmp/tree-0f2e7f1/`。逐 blob 与 mode 对账结果为 `expected_files=528`、`missing=0`、`mismatched=0`；目录另有 14,437 个 `.venv`、`.ruff_cache` 等 ignored 运行产物，不参与提交身份。探针运行前另以 `inspect.getsourcefile` 确认 `_counted_upstream` 与 `raise_with_cleanup_under` 均从该提交树的 `src/` 加载。

明确不在本轮范围内：未提交的 `docs/.human-controlled/` 两处修改、主工作树其他 untracked 文件、未挂载 legacy 链路的产品行为，以及用户明确未要求的真实上游调用。本轮没有修改被评代码。

## 总体裁决

**verdict：`pass-with-fixes`。**

**blocker：0。major：0。minor：5。nit：2。**

核心修复成立：活动链上的三个调用点现在保留显式 `__cause__`；`_counted_upstream` 会等 cleanup 完成，第二次取消不会打断 release；`GeneratorExit` 归一让无其他 primary 时的 close failure 可见；`context.attempt_count > opened_before` 精确表示该次 `handle` 已执行 `begin_attempt`；多次 replay 原因与整体行长边界也已落地。提交态 Ruff 与 Pyright 通过，第二次全量提交态运行得到 `1643 passed, 2 skipped, 90.18%`。

需要修的都不是当前 happy path 的回退，而是 cleanup 组合矩阵与承重注释里的局部缺口：同一语义仍有两个旧调用点没有迁移；helper 会覆盖已有 `__context__`，同对象时还能造自引用；四处用异常真值代替 `is None`；`shield` 在“取消与 cleanup failure 同时发生”时留下未消费 diagnostic；一条已被既有评审指出的过期归因注释仍在。以上影响局部、都有明确修法，因此不升为 `needs-work`。

## Major

未发现 major。

## Minor

### R7-01：cleanup 链统一并不完整，两个同语义调用点仍会覆盖 primary 的显式 cause

- finding_id: `retry-continuation-review-round-seven-01`
- severity: `minor`
- primary_location: `src/app/streaming/keepalive.py:50-62`
- related_locations: `src/app/streaming/sse.py:218-230`、`src/app/streaming/keepalive.py:68-80`、`tests/unit/streaming/test_streaming_resilience.py:306-395`

**证据。** 提交态搜索：

```text
$ rg --line-number 'raise primary from cleanup_error|raise_with_cleanup_under\(' src tests
src/app/streaming/keepalive.py:62:                raise primary from cleanup_error
src/app/pipeline/delivery/stream.py:212:                raise_with_cleanup_under(primary, cleanup_error)
src/app/streaming/sse.py:228:                    raise primary from cleanup_error
src/app/server/routes/inference.py:647:                raise_with_cleanup_under(primary, close_error)
src/app/server/routes/inference.py:694:                raise_with_cleanup_under(primary, cleanup_error)
```

在 exact tree 上让 `session_liveness_stream` 的 pull 抛 `PrimaryError from RootError`、`aclose` 再抛 `CleanupError`：

```text
session_liveness raised=PrimaryError cause=CleanupError root_reachable=False
```

这正是新 helper 要消除的故障。`tests/unit/streaming/test_streaming_resilience.py:376-395` 现有测试反而把 cleanup error 应成为 cause 固定成断言，没有携带已有 root 的反例。

**判断。** `raise_with_cleanup_under` docstring 的窄事实“production 现在有三个 helper 调用点”成立，但“一个实现，因为三个调用点是同一件事”并没有覆盖仓库内同一机制的全部拼法。`session_liveness_stream` 与 `DelayedStartStreamingResponse` 当前没有 production caller，故本项不升为 major；它们仍是保留并受测试的实现，不能继续把已知会丢 root cause 的行为写成正确 oracle。

**建议处置。** 把这两处也改用 helper，并把 `test_session_liveness_keeps_upstream_error_primary_when_close_fails` 改成带 `RootError` 的链断言。若项目明确只想统一活动链，应收窄 helper docstring，不要写成机制只有三个调用点；但保留 legacy 功能时更稳妥的方向仍是统一语义。

### R7-02：`raise_with_cleanup_under` 覆盖已有 context，重复使用时丢前一次 cleanup，同对象时会造自引用

- finding_id: `retry-continuation-review-round-seven-02`
- severity: `minor`
- primary_location: `src/app/streaming/keepalive.py:68-80`
- related_locations: `src/app/pipeline/delivery/stream.py:202-215`、`src/app/server/routes/inference.py:640-647`、`src/app/server/routes/inference.py:680-698`、`tests/unit/streaming/test_streaming_resilience.py:515-544`

**证据。** helper 在已有显式 cause 时直接执行 `primary.__context__ = cleanup_error`。exact tree 探针连续把两个 cleanup failure 放到同一个 `PrimaryError from RootError` 下：

```text
repeated_helper first_recorded_initially=True context_now=CleanupError:second cleanup first_still_reachable=False cause_is_root=True
```

把 `cleanup_error` 设为 `primary` 本身时，Python 接受直接赋值或 `raise primary from primary`，探针得到：

```text
raised=RuntimeError:same object
is_primary=True
context_is_self=True
```

无既有 cause 的分支同样得到 `cause_is_self=True`。所以 docstring 的“nothing already there lost”是全称过头；当前两个新增测试只覆盖“一次调用，显式 cause 有或无”，没有覆盖已有 implicit context、重复 cleanup 或 identity 相同。

**判断。** 当前三个活动调用点最常见的一次 cleanup failure 语义正确，显式 root cause 保住了；本项只在 primary 已有 context、同一 primary 经多层 cleanup 再次配对，或 cleanup 返回同一异常对象时出现，因此定为 minor。它不是纯注释问题：第一条 cleanup 真的从可达链中消失，自引用还会让没有 cycle guard 的链遍历者打转。

**建议处置。** 先把 helper 契约写精确：要保的是 explicit cause、已有 context、还是所有并发 secondary failure。实现至少应拒绝 `cleanup_error is primary`，并在替换 context 前保留旧链；如果线性 cause/context 无法如实表达多个 sibling cleanup failure，应考虑 `add_note` 或专门的 secondary-error 容器，而不是静默覆盖。补三条最小测试：已有非空 `__context__`、连续两次 helper、同对象输入。

### R7-03：四处 cleanup 分支用异常真值挑 primary，falsey exception 会被 cleanup error 或 cancellation 改写

- finding_id: `retry-continuation-review-round-seven-03`
- severity: `minor`
- primary_location: `src/app/server/routes/inference.py:685-698`
- related_locations: `src/app/pipeline/delivery/stream.py:202-215`、`src/app/streaming/keepalive.py:52-65`、`src/app/streaming/sse.py:219-232`

**证据。** 四处均写作 `primary = primary or cleanup_cancellation`。`BaseException` 子类可以定义 falsey `__bool__`；本项目自己的异常链文档在别处也明确用 `is not None` 避开这一点。exact tree 探针让 `_counted_upstream` 的 pull 抛 falsey `FalseyPrimary`，随后 close 抛 `CleanupError`：

```text
falsey_counted raised=CleanupError same_primary=False chain=['CleanupError', 'FalseyPrimary']
```

原 primary 被降到 context，实际抛出的普通异常变成 cleanup error。若 cleanup 期间再收到 cancellation，同一写法会选中 cancellation，普通 primary 变成 `CancelledError`。

**判断。** 用户特别询问的 `primary is None + cleanup_cancellation is not None` 分支本身是对的；错误来自用 `or` 同时表达“是否存在”和“选择优先级”。内建与当前已知上游异常通常 truthy，所以影响面局部，定为 minor；但它直接违反本 helper 声称的 exit priority，且会发生“普通异常变成 cancellation／cleanup error”这种用户点名要求排查的类型转换。

**建议处置。** 四处都改成显式 identity 判定，例如 `if primary is None: primary = cleanup_cancellation`。补一个 falsey `BaseException` 回归，并同时断言 success、cleanup failure、cleanup cancellation 三种组合的最终 identity。

### R7-04：cleanup 被取消后若 cleanup task 自己失败，`asyncio.shield` 留下一条“exception in shielded future” diagnostic

- finding_id: `retry-continuation-review-round-seven-04`
- severity: `minor`
- primary_location: `src/app/streaming/keepalive.py:106-129`
- related_locations: `src/app/pipeline/delivery/stream.py:185-187`、`src/app/server/routes/inference.py:688-698`、`tests/unit/pipeline/delivery/test_stream_delivery.py:1377-1424`

**证据。** exact tree 探针从 `GeneratorExit -> None` 的 close 路径进入 cleanup，在 source `aclose` 等待期间取消外层 `aclose` task，再让 source close 分别成功／失败。行为结果本身正确：

```text
close_fails=False raised=CancelledError cause=None task_cancelled=True close_finished=True
close_fails=True raised=CancelledError cause=RuntimeError task_cancelled=True close_finished=True
```

但失败组合在上述两行之前向 stderr 写出：

```text
RuntimeError exception in shielded future
future: <Task finished ... finish_stream_cleanup.<locals>.cleanup() ... exception=RuntimeError('close failed')>
```

traceback 指向 `keepalive.py:99 -> _close_iterator -> source.aclose`。`finish_stream_cleanup` 最后确实调用了 `cleanup_task.result()`，但 cancellation 已取消本轮 `asyncio.shield(cleanup_task)` 产生的外层 future；inner 后来失败时，那个 shield waiter 仍报告未消费异常。相邻 `_events_with_ping` 在 `stream.py:185-187` 已准确解释了同一失效，并为 pull 使用 `asyncio.wait` 避开它。

**判断。** cleanup 完成、最终 cancellation 身份与 cleanup cause 都没有丢，本项不升为 major；但 operator 会同时得到已链上的异常和一条“未处理 future”噪声，恰好破坏本轮在修的诊断清晰度，而且现有 second-cancel 测试只让 close 成功，看不到这个组合。

**建议处置。** 用不会传播 cancellation 到 child、也不会创建 orphan shield waiter 的 `await asyncio.wait({cleanup_task})` 驱动等待，或显式持有并消费 shield waiter 的结果。新增测试安装 loop exception handler，要求“cancel during cleanup + close fails”最终抛 `CancelledError from RuntimeError`、cleanup 完成，并且 handler 没收到未消费异常。

### R7-05：`stream.py` 仍宣称 `_counted_upstream` 会被标成 upstream，与当前代码和已闭合文档直接冲突

- finding_id: `retry-continuation-review-round-seven-05`
- severity: `minor`
- primary_location: `src/app/pipeline/delivery/stream.py:378-387`
- related_locations: `src/app/pipeline/delivery/stream.py:35-43`、`src/app/server/routes/inference.py:491-503`、`.dev/docs/upstream/retry-and-continuation/deferred.md:327-339`、`.dev/docs/upstream/retry-and-continuation/reports/260823-review-h2-classification.md:467`

**证据。** `stream.py:382` 仍写：

```text
The converse does not hold yet ... a bug in `_counted_upstream` still reads as upstream's. `deferred.md` §22之六.
```

实际接线在 `inference.py:491-503` 把 `UpstreamSource` 放在 `_counted_upstream` 下面；同文件 `UpstreamSource` docstring 与测试均写 counter bug 现在是 `ours`。`.dev deferred.md` §22之六已标“已修”，既有第四轮评审 `260823-review-h2-classification.md:467` 也已经逐字指出这条 residue，本次提交仍未删除。

**判断。** 不影响运行行为，但这是归因边界旁的承重注释，会明确指示后续维护者去修一个已经修好的 seam，或据此错误判断 local bug 会被 hand-over。鉴于本项目明确把注释当判据，本项定为 minor，而不是普通文字 nit。

**建议处置。** 把这段改成当前事实：marker 下方两道 guard 代表 upstream condition，counter 与 client deadline 在 marker 上方，counter bug 因而是 ours；引用 `deferred.md` 时明确该项已闭合。同步复扫同段绝对化陈述，避免一边说“still”一边链接已划线关闭的台账。

## Nit

### R7-06：`attempt_count` 精确表示 logical attempt 已打开，不等价于“replay reached upstream／sent a byte”

- finding_id: `retry-continuation-review-round-seven-06`
- severity: `nit`
- primary_location: `tests/int/test_pipeline_app.py:3161-3204`
- related_locations: `src/app/server/routes/inference.py:414-426`、`src/app/pipeline/direct_driver/base.py:136-152`、`src/app/pipeline/request.py:94-109`、`src/app/pipeline/driver.py:116-171`、`src/app/observability/request_trace.py:153-157`

**证据。** 全仓对 request attempts 的唯一追加是 `RequestContext.begin_attempt -> self.attempts.append`（`request.py:94-101`）。`DirectDriver.run` 在 `base.py:139` 先调用它，随后才执行 `EVENT_ATTEMPT_PREPARE` subscribers（`:145`）、rate limiter（`:149-150`）与 `_send`（`:151`）。所以 `context.attempt_count > opened_before` 与“本次 `handle` 进入了 driver 并打开 logical attempt”等价；它不与“provider send 已调用”或“wire 上发出了字节”等价。subscriber 或 limiter 在 begin 后失败，仍会推进 count，但没有 upstream I/O。

反方向没有洞：本轮搜索只找到这一处 append，当前 `handle` 的 provider send 都在 begin 之后；不存在 replay 真正调用 `_send` 而 attempt count 不动的路径。

**判断。** 生产注释 `inference.py:418` 说的是“whether begin_attempt ran／attempt was opened”，准确；新增测试标题与 docstring 多次说“never reached upstream／never sent a byte”，范围更宽。当前 test 注入点在 `shape_request`，确实同时满足两者，所以测试会绿，却不能证明 after-begin-before-send 也不记录。实现无需因本项改变，问题是 test 与 commit 叙述把 logical attempt 写成 wire attempt。

**建议处置。** 把测试改名并收窄为“failed before opening an attempt is not recorded”，注释同样写 `begin_attempt`。如果真正需要“发到 upstream 才算 replay”，就不能继续拿 `attempt_count` 当 oracle，应在 provider send 边界增加明确事实；那是另一项产品语义，不应由测试措辞暗中决定。

### R7-07：一处“四个 wrappers，marker 在其中”的表述仍漏算最外层 client deadline

- finding_id: `retry-continuation-review-round-seven-07`
- severity: `nit`
- primary_location: `tests/unit/pipeline/delivery/test_stream_delivery.py:1473-1479`
- related_locations: `tests/unit/pipeline/delivery/test_stream_delivery.py:1330-1359`、`tests/unit/pipeline/delivery/test_stream_delivery.py:1717-1730`、`src/app/pipeline/delivery/stream.py:35-43`、`src/app/server/routes/inference.py:372-380`、`src/app/server/routes/inference.py:491-500`

**证据。** production 从 raw response 往外依次是 idle timeout、attempt deadline、`UpstreamSource` marker、`_counted_upstream`、client deadline，共五个对象。新改的 `:1333` “Production stacks five”与 `:1357` “All five”正确；`:1729` 与 `stream.py:40` 用“四个 ordinary wrappers + marker = five objects”的口径也能解码。唯独 `:1477` 写“four wrappers over the raw response with the marker among them”，把 marker 算进四个后，client deadline 没了，而且与同文件“stacks five”冲突。

**判断。** 该测试只关心 marker、counter 与 source 的归因边界，漏 client deadline 不改变判据，因此定为 nit。此前“four layers”改成“four wrappers”没有真正消除这一个位置的数量歧义。

**建议处置。** 直接写“五个对象，marker 是其中之一”；若只想描述归因相关的 inner four，应明确限定为“the four objects at the attribution boundary, excluding the outer client deadline”，不要再用无范围的 production composition 全称。

## 未计级建议

### 用 Event 代替 second-cancellation test 的固定 sleep

`test_a_second_cancellation_does_not_interrupt_the_release_it_arrives_during` 使用 `0.05 / 0.05 / 0.3`。本轮把 exact test 连续运行 25 次，结果为 `25 passed`，未观察到 flake；同一 event loop 内 ready queue 与 timer deadline 的先后也让它比跨线程 sleep 稳定。因此我没有把“它会 flake”写成事实发现。

仍建议改成结构化同步：source 在 close 开始时 `close_entered.set()`，等 `allow_close.wait()`；测试第一次 cancel 后 `await close_entered.wait()`，第二次 cancel，再 `allow_close.set()`。这样直接把“第二次取消落在 release 内”变成前提，不用 300ms 墙钟窗口，也能显著缩短测试。前提若为假，测试会停在带 timeout 的 event wait 或前提断言，而不是把调度速度混进产品结论。

### pyright helper 可去掉 `Any`，但当前修法没有造成运行期盲区

当前 `_connection_the_pool_creates` 的 `transport: Any` 确实让 type checker 看不见 `_pool` 拼错或消失；不过四个调用点都真实执行 `transport._pool.create_connection` 并断言 created 类型，缺属性会在 runtime 立即红，production 又访问同一 private path。因此“pyright gate 为了第三方 private boundary 显式收口 Any，运行测试守住行为”基本成立，不列缺陷。

更清晰的写法已经在 exact 环境 PoC 通过 Pyright 与 runtime：

```python
transport = client._transport  # pyright: ignore[reportPrivateUsage]
pool = getattr(transport, "_pool", None)
assert isinstance(pool, httpcore2.AsyncConnectionPool)
return pool.create_connection(httpcore2.Origin(b"https", b"example.invalid", 443))
```

最小 PoC 输出 `0 errors, 0 warnings, 0 informations`，direct 与 proxy client 的 pool 均通过 `isinstance`，都建立 `AsyncHTTPConnection`。这比 `Any` 多一条运行时形状断言，建议采用，但不是当前提交的放行条件。

## 明确排除的怀疑

1. **排除“`pending=None` 让 `_counted_upstream` 漏掉 in-flight pull”。** `_counted_upstream` 自己没有创建 pull task，迭代它的 task 由 `_events_with_ping` 所有并在那里先 settle；这里拥有的只有被消费 iterator 的 close，所以 `pending=None` 与所有权相符。结论强度：强到可据此不改参数。
2. **排除“primary 为 None、cleanup cancellation 非 None 的分支吞掉取消或把它普通化”。** exact probe 中 close 成功得到 `CancelledError`、`task_cancelled=True`、`close_finished=True`；close 同时失败得到 `CancelledError from RuntimeError`，仍然 `task_cancelled=True`。该分支顺序正确；额外 stderr diagnostic 单独记为 R7-04。结论强度：强到可据此确认用户点名分支的主语义。
3. **排除“普通 truthy primary 会被第二次取消替换”。** 代码优先保留已有 primary；cleanup error 作为 cause/context，第二次 cancellation 不改顶层。问题只在 falsey primary，已精确拆成 R7-03。结论强度：代码路径与 probe 足以行动。
4. **排除“`GeneratorExit -> None` 归一会吞 close failure”。** 新测试在无其他 ending 时让 source close 抛 `RuntimeError`，`counted_stream.aclose()` 收到该错误；去掉归一的用户变异证据也会让该测试转绿变假，当前实现方向正确。结论强度：强到可据此保留归一。
5. **排除“没有 `aclosing` 也能在同一个 cancelled consumer task 内看见 defect”。** exact probe中显式 `aclosing` 在 `after-consumer` 之前进入 raw finally；bare `async for` 则先记录 `after-consumer:True`，过三个 loop tick 才在另一 task 进入 raw finally。测试 docstring 所说“由 async-gen hook 稍后、任务之外 finalize，无法打中第二次取消窗口”成立。结论强度：强到可据此保留 `aclosing`。
6. **排除“`attempt_count` 还有别的生产推进路径”。** tracked source 中只有 `RequestContext.begin_attempt` append；`handle_count_tokens` 也调用 begin，但不是 `_reopen` 的请求路径。反向所有 replay provider send 都由 `DirectDriver.run` 在 begin 之后发起。R7-06 只收窄“到达 wire”的措辞，不否定 logical-attempt 判据。结论强度：全 tracked source 搜索，强到可行动。
7. **排除“多次 replay 仍只记录第一条”。** `replaced_failures.append` 在每次 `_reopen` logical attempt 打开后执行，RequestTrace 到 RequestLine 到 JSON 的 tuple/list 转换完整；request line 对 join 后整体调用 `one_line`。父提交新增的多 replay 与整体截断修复在最终树中自洽，用户提供的对应变异均能打红。结论强度：代码链、测试与提交态全量绿共同支持；本轮未重复改写源码做同一变异。
8. **排除“pyright 修法让 `_pool` 消失后测试仍绿”。** helper 的每个调用都会访问 `_pool.create_connection`；属性消失会直接 `AttributeError`，返回错误形状也会被 `isinstance(created, StreamCappedConnection)` 抓到。`Any` 是静态盲区，不是运行期缺席盲区；更好的 typed runtime guard 已在上节给出。结论强度：强到不列 finding。
9. **排除“本轮 five-object 主结论仍整体算错”。** production expression 确有 idle、attempt deadline、marker、counter、client deadline 五个对象位于 raw source 之上；`_counted_upstream` docstring 的“real five-object composition”和主 close regression 的“All five”成立。只剩 R7-07 那一处把 marker 算进 four 又没限定 client deadline。结论强度：直接代码计数，强到行动。
10. **排除“第一次全量红可以归因于本提交”。** 第一次提交态全量唯一失败是未改动的 `tests/int/test_standalone_process.py::test_a_run_on_another_port_leaves_the_incumbent_its_record`，当时 throwaway pidfile 在 child 退出后仍存在；该 test 立刻单独重跑 `1 passed in 1.88s`，随后同一 exact tree 全量 `1643 passed, 2 skipped`。这是一次跨进程时序不稳定的观测，不能支撑对被评 diff 的归因；也不能反过来宣称该测试没有 flake。结论强度：仅能排除本轮归因，不足以关闭 lifecycle test 自身问题。

## 验证记录与搜索面

### 提交身份

```text
commit=0f2e7f1066511ffcec5a0069d3661997e2063565
parent=da0c4b57f59727e74715fc21e7d0693ff069fd65
tree=76989a90eaf8c981a7093ea24d698cbbf7c60b65
expected_files=528
missing=0
mismatched=0
```

tracked bytes 与 mode 全部一致；extra 仅为 ignored runtime assets。

### 正式 gate

```text
$ cd /home/xp/.claude/jobs/06dcd6c1/tmp/tree-0f2e7f1 && uv run ruff check src tests
All checks passed!
ruff_rc=0

$ uv run pyright src tests
0 errors, 0 warnings, 0 informations
pyright_rc=0

$ uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80 -q
TOTAL 10375 1019 90%
Required test coverage of 80% reached. Total coverage: 90.18%
1643 passed, 2 skipped in 114.30s
```

第一次全量的唯一瞬时失败及复跑结果已在排除项 10 如实保留，没有用第二次绿抹掉第一次红。

### 直接探针

- `/tmp/review_round7_exception_probe.py`：证实 session liveness 的未迁移 raw chain、falsey primary 错序、重复 helper 覆盖 context。
- `/tmp/review_round7_cleanup_cancellation_probe.py`：证实 `primary=None + cleanup cancellation` 的顶层语义正确，同时抓到 shielded-future diagnostic。
- `/tmp/review_round7_aclosing_probe.py`：证实有／无 `aclosing` 进入不同 finalize 时机与 task。
- `/tmp/review_round7_pyright_pool_minimal.py`：证实 `getattr + isinstance` 替代方案 Pyright 为 0 error。
- `/tmp/review_round7_repeat_timing_test.py`：exact second-cancel test 连续 25 次通过；只支持“本机未复现 flake”，不支持绝对稳定性。

### 阅读与搜索范围

逐行或承重区间读取：`src/app/server/routes/inference.py`、`src/app/streaming/keepalive.py`、`src/app/pipeline/delivery/stream.py`、`src/app/pipeline/direct_driver/base.py`、`src/app/pipeline/request.py`、`src/app/pipeline/driver.py`、`src/app/observability/request_trace.py`、`src/app/observability/request_log.py`、`src/app/upstream/stream_cap.py`、`src/app/streaming/sse.py`，以及五个本轮变更测试文件与父提交关联测试。全仓搜索了 `begin_attempt`／attempt list mutation、`raise primary from cleanup_error`／helper callsites、wrapper count 断言、`_transport._pool` 与 replay record 全链。读取了提交态四份 human-controlled 判据与 `.dev` 本主题 README、status、decisions、deferred 相关段落和既有第四／第五轮评审证据。

未穷举所有第三方异常类是否存在 falsey `__bool__`；R7-03 的结论是 generic `BaseException` 契约反例，不声称当前已观测到某个上游库这样实现。未执行真实 upstream call；本轮问题不依赖 upstream wire 行为。

## 我最没把握的三个判断

1. **R7-02 定为 minor，而不是 major。** 已确认 helper 能丢旧 context 与造 self-cycle；没确认当前 production 三个调用点能在同一次真实请求中让同一 primary 连续遭遇两个独立 cleanup failure。若有一条可达组合证明会发生，级别应上调。
2. **second-cancel test 不列 flake finding。** 25 次重复与同 loop timer ordering 支持“当前不是已证 flake”，但固定时长仍比 Event 脆弱；若 CI 有历史随机红，应把未计级建议升级为 minor。
3. **R7-01 定为 minor。** 两个残留 raw call 当前全仓无 production caller；如果 `DelayedStartStreamingResponse` 或 `keepalive_stream` 由动态入口、插件或未被静态搜索发现的调用者挂载，root-cause loss 会进入 live path，级别应上调。

## 执行本契约时遇到的摩擦

用户提供的解包目录已经含 `.venv` 与 `.ruff_cache`，所以“目录有 extra”不能作为提交树不一致；本轮改用 Git blob object id 与 mode 对 tracked 清单逐项核验。第一次全量又出现一个随后无法复现的跨进程 test failure，必须同时保留红样本、单测复跑与第二次全量结果，不能只挑最后一次绿。除此之外无阻塞。

## 整体判定

`0f2e7f1` 完成了活动链上本轮四项主修复，父提交的 multi-replay 与整体截断也保持成立；没有 blocker 或 major。修完五条 minor 与两条 nit 后可转 `pass`，其中优先级最高的是 R7-01、R7-03、R7-04：它们分别关闭仍存的 cause 覆盖、falsey exception 错序和 shield diagnostic。R7-02 需要先明确多 secondary failure 的表达契约，避免用另一种线性链改写替代当前改写。

## 交付声明

- delivery_complete: true
- completed_at: 2026-08-24
- finding_total: 7
- blocker: 0
- major: 0
- minor: 5
- nit: 2
- suggestions_unscored: 2
- exclusions_recorded: 10
