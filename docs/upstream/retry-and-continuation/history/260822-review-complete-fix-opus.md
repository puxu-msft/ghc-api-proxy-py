# 评审：`_deliver` 在上游已发完终结事件后不再丢弃回复（`c86712d`）

评审人：Opus 5（subagent）。日期：2026-08-22。

隔离工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon`，分支 `worktree-260822-complete-not-abandon`，基线 `4c7129a`。

## 0. 先说评审对象的移动（必读，会影响你怎么读下面每一条）

派发时给我的对象是**未提交的 `git diff`**。评审进行中，该工作树被作者继续修改并提交：

- `src/app/pipeline/delivery/stream.py`：**始终未变**。blob `d5d8b24 → 0b88d62`，从我第一次 `git diff` 到 `c86712d` 落定，sha256 恒为 `1c0b8392…`。**所有源码层面的结论都是对最终态的结论。**
- `tests/unit/pipeline/delivery/test_stream_delivery.py`：**变了两次**。我拿到的草稿版 sha256 `3d1d3095…`（mtime 10:50），最终提交版 sha256 `92ff0580…`（mtime 11:42）。测试 diff 从 45 行长到 89 行。
- 提交 `c86712d`，作者 Pu Xu，时间 `2026-08-22 11:47:52 +0000`。我的评审窗口横跨这次提交。

两条由此产生的事实，都是我第一手观测到的：

1. **我 11:2x 的第一次跑测，撞上了作者当时正在进行的变异检验**。那一跑的结果是 `2 failed, 42 passed`，两条全是新测试的两档参数，报错 `ConnectionError: upstream tore`（`keepalive.py:126`）。我随后在 `/tmp` 副本上撤掉源码修复，得到**逐字相同**的输出（见 §5 的 M1）。也就是说：那一刻磁盘上的 `stream.py` 没有 `break`。我没有改过主树或本工作树的任何源码文件——`git status` 全程只显示那两个文件，现在为空。
2. **我针对草稿版测试写的两条发现已经被最终版消解**（见 §5）。我把它们保留在报告里并标注「已在 `c86712d` 中修复」，因为作者可能想知道那个草稿到底漏在哪。

**因此：如果你在读这份报告时又改了测试文件，§5 的两条要重跑；§1–§4、§6 只依赖 `stream.py`，不受影响。**

## 1. 结论摘要

修复本身**正确、必要、位置站得住**，我用受控变异逐条验证过，不是读代码读出来的判断。

裁决：`needs-fix`——三条 major 都不推翻这次修复，但都需要一个动作（记一笔、或补一处观测、或裁决一个孤儿分支）。

| # | 等级 | 一句话 | 权重档位 |
|---|---|---|---|
| A | major | 被 `break` 吞掉的异常**在任何地方都不留痕**：上游 reset 之后完成行只剩 `[ OK ]`，修复前那条（错误的）`[FAIL] … connection reset by peer` 是这类事件唯一的记录，现在没了 | 够据此行动（有正反两次实测日志行） |
| B | major | `decide_stream_ending` 的 `COMPLETE` 分支从唯一生产调用者视角**已不可达**——破坏它，unit+int 1589 条里只有它自己的单测变红 | 够据此行动（变异实测） |
| C | major | client deadline 与「上游已完成」的相对次序**现在是有真实后果的未决问题**，且三条既有 deadline 测试的夹具全部携带终结事件，已无法区分这两种情形；作者注释里说「不归本次裁决」是对的，但没有落到 `deferred.md` | 够据此行动（变异实测 + 读夹具） |
| D | minor | 注释里「`_ending()` true by construction」说得过满：`break` 之后的 flush 段仍可抛异常，此时 `terminal.seen` 为真 | 倾向（构造得出，未在生产观测到） |
| E | minor | `break` 对**所有** `Exception` 生效，包含 `BufferCapExceeded` 这类交付侧故障，不止传输撕裂 | 仅存档（当前不可达，见 §6） |
| F | minor | 新测试只参数化 `block` / `full`，`until-tool-use` 未覆盖 | 仅存档（我用探针实测三档行为一致，不建议补测试） |

主树侧的门（在提交态 `c86712d` 上跑的）：

```
uv run ruff check src tests            -> All checks passed!
uv run pytest tests --cov=app ...      -> 1686 passed, 3 skipped, TOTAL 91%（--cov-fail-under=80 通过）
uv run pyright src tests               -> 21 errors, 0 warnings
```

pyright 那 21 条**全部**落在 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`（`reportPrivateUsage` / `reportUnknown*`），这两个文件本次未改动、在基线 `4c7129a` 上即已如此。两个被改文件**零 pyright 报错**：

```
$ uv run pyright src tests 2>&1 | rg "delivery/stream.py|test_stream_delivery.py"
（无输出）
```

## 2. 逐题回答

### 问题 1：`break` 的落点是否正确，三种 policy 下线上帧序列对不对，会不会重复交付

**证实。** 不是读出来的，是把三种 policy × 三种回复形状全跑了一遍。

探针：`/tmp/mut2/probe_wire.py`，跑在 `/tmp/mut2/pkg`（副本）上，脚本开头有 `assert stream_mod.__file__.startswith("/tmp/mut2/pkg")` 自证。

```
$ PYTHONPATH=/tmp/mut2/pkg ./.venv/bin/python /tmp/mut2/probe_wire.py
--- one text block | policy=block
    events : ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop', 'message_delta', 'message_stop']
    starts : 1   stops: 1
    usage  : True   stop_reason: True   incomplete: False
--- one text block | policy=full            （同上）
--- one text block | policy=until-tool-use  （同上）
--- two text blocks | policy=block / full / until-tool-use
    events : [message_start, (start,delta,stop)×2, message_delta, message_stop]
    starts : 1   stops: 1   usage: True   stop_reason: True   incomplete: False
--- text then tool_use | policy=block / full / until-tool-use
    events : [message_start, (start,delta,stop)×3, message_delta, message_stop]
    starts : 1   stops: 1   usage: True   stop_reason: True   incomplete: False
```

九个组合全部：**恰好一个 `message_start`、每个块恰好一份且保持顺序、`message_delta` 带 `stop_reason` 与 `usage`、恰好一个 `message_stop`、没有 `incomplete_responses_stream`。**

「不会重复交付」在结构上是有保证的，不只是碰巧：`break` 之后走的 `session.finish()` → `buffer.finish()` → `_drain()`，而 `block` 策略下每个块在 `add` 时已 `_drain` 过，`_held` 是空的；`full` / `until-tool-use` 下未释放的块**只在这里**释放一次。`break` 路径与正常 `torn is None` 路径汇合到**完全相同的代码**，没有任何路径专属分支，所以「只有 break 路径重复交付」这种缺陷不添代码是构造不出来的。我用一个非路径专属的变异（M5）验证过这条汇合路径确实被守着，见 §5。

### 问题 2：位置放在 `ClientDeadlineError` 之后是否漏掉真实场景？合并进 `if torn is None` 那支是否更好？

**放在之后是对的，合并进去会破坏一条已裁决的契约——这一条是实测，不是意见。**

变异 M6：把判断合并成 `if torn is None or assembler.terminal.seen: break`（等价于把它提到 deadline 分支之上），原位置置死。

```
$ PYTHONPATH=/tmp/mut2/pkg ./.venv/bin/python -m pytest tests/unit/pipeline/delivery/test_stream_delivery.py -q -p no:cacheprovider
FAILED test_the_client_deadline_is_the_one_ending_that_says_so - AssertionError: assert 'message_stop' == 'error'
FAILED test_a_held_back_policy_still_hears_the_client_deadline[full] - assert b'client_deadline_exceeded' in b'event: message_start...'
FAILED test_a_held_back_policy_still_hears_the_client_deadline[until-tool-use] - assert b'client_deadline_exceeded' in ...
3 failed, 41 passed
```

**三条 deadline 测试全红。** 原因值得单独写下来，因为它同时是发现 C：

这三条测试的夹具都是 `_hits_the_client_deadline_after(anthropic_stream(...))` / 等价物，用的是**完整**的 `anthropic_stream(...)`——里面含 `message_delta` + `message_stop`。所以在 `ClientDeadlineError` 到达的那一刻，`assembler.terminal.seen` **已经是 `True`**。

于是：

- **合并的代价是明确的**：`client_deadline_exceeded` 错误帧对这三条既有测试覆盖的全部场景都不再发出。这不是风格差异，是行为改变，而 deadline 帧是当天（2026-08-22）刚裁决的契约。**不要合并。**
- **不合并的代价是隐性的，而且是真实的**：生产上存在一个窗口——上游发完 `message_stop` 之后、EOF 之前，`with_client_deadline_at` 若在此刻到期，客户端拿到的是 `client_deadline_exceeded` 错误帧，而**手上已有一份完整回复**。这正是本次修复所治的病，在一个更窄的窗口里原样存在。
- 更麻烦的是：**这三条 deadline 测试现在无法区分「超时且回合未完成」与「超时但上游已完成」**——它们的夹具全部落在后者。也就是说这个窗口目前既没有被修，也没有被任何测试标定。

作者注释写「reordering is not this fix's to decide」，这个判断我**认同**（把两个当天刚裁决的分支放在一次 7 行修复里重排，风险大于收益）。但按 `no-silently-cut-but-defer`，它必须**落到文档**，不能只活在一条代码注释里。

**建议动作**（三选一，我倾向第一个）：

1. 在 `.dev/docs/delivery-keepalive/deferred.md`（或 deadline 主题对应的 `deferred.md`）记一条：「`ClientDeadlineError` 在 `terminal.seen` 为真时是否应让位于完整交付；现有 deadline 测试夹具均含终结事件，无法区分两种情形」。这是本次评审唯一一条我认为**必须**做的记录。
2. 若想顺手让守卫更锋利：把 `test_the_client_deadline_is_the_one_ending_that_says_so` 的夹具改成 `anthropic_stream("one")[:-2]`——与本次对另外两条测试做的修正**完全同构**，而且能让 §5 里那个「夹具混进 terminal event」的问题在 deadline 一侧也被清掉。改完 M6 就不再是 3 红而是 1 红（`test_a_held_back_policy_still_hears_the_client_deadline` 的夹具我没查，可能也要同样处理）。**这条属于建议，不属于本次修复范围**，交给你裁决。
3. 什么都不做，但至少把第 1 条记下来。

**合并写法的代价还有一条独立的**：`if torn is None or assembler.terminal.seen:` 会把「正常结束」与「撕裂后已完成」两个语义压到同一个条件里，而两者在可观测性上应该分开（见发现 A）。合并之后连「这里发生过一次 break-with-exception」这个事实都没有落点了。

### 问题 3：`COMPLETE` 是否成了孤儿件？注释里的理由站不站得住？

**证实：`COMPLETE` 分支从唯一生产调用者视角已不可达。** 这是实测，不是推理。

变异 M7：把 `decide_stream_ending` 的 `if terminal_seen: return EndingVerdict(StreamEnding.COMPLETE)` 改成返回 `ABANDON`，然后跑 unit + int 全量：

```
$ PYTHONPATH=/tmp/mut2/pkg ./.venv/bin/python -m pytest tests/unit tests/int -q -p no:cacheprovider
FAILED tests/unit/pipeline/test_stream_ending.py::test_a_stream_upstream_finished_is_simply_complete
1 failed, 1588 passed, 1 skipped in 94.49s
```

**1588 条无一受影响，唯一变红的是这个纯函数自己的单测。** 结构上也对得上：`_deliver` 在第 307 行传的是 `terminal_seen=assembler.terminal.seen`，而第 297 行的 `break` 保证走到这里时它必为 `False`。

**注释里的理由站得住，而且是有据的，不是修辞。** 它的核心论证是「一个分类法不认识的异常，不该成为丢弃完整回复的决定者」，并点名 `h2.ProtocolError`。我核过这条事实：

```
$ ./.venv/bin/python -c "..."
h2.exceptions.ProtocolError      normalize=None                     reason=None
builtins.ConnectionError         normalize=None                     reason=None
httpx2.ReadError                 normalize=UpstreamError('upstream connection failed: reset')  reason=RetryReason.NETWORK
```

`h2.ProtocolError` → `normalize_upstream_error` 返回 `None` → `_replay_reason` 返回 `None` → 修复前在第 306 行 `raise torn`，**`decide_stream_ending` 根本没被调用过**。而「裸 `h2.ProtocolError` 不被包装、绕开我方全部捕获边界」这一条，在 `.dev/docs/upstream/h2-goaway/findings.md` 的表里是列在**「确凿」**栏的（该文件第 49 行）。所以论证的前提有项目自己的白盒+端到端证据支撑。

一个精确度上的补注：同一张表把「裸 `h2.ProtocolError` 在生产中出现的概率」列在**「未决」**栏。所以准确的说法是**机制确凿、频率未知**。这不削弱修复（修复在任何频率下都对），仅供你写文档时措辞用。

**所以「改成在 verdict switch 里处理 `COMPLETE`」是错的**，理由就是上面这条：那个 switch 在 `replay.eligible` 之后，而 `eligible` 会把 `h2.ProtocolError` 过滤掉，判断永远到不了。放在 `_deliver` 里是唯一能覆盖「分类法不认识的异常」的位置。

**但孤儿件的问题是真的，需要一个裁决。** 现在的状态是：一条规则写在两个地方，其中一处（纯函数里的）已经没有生产读者，只有一条单测在守着它。按项目记忆里的「不得擅自删除已实现的功能」，我**不建议**你删它。我建议二选一：

- **（倾向这个）** 在 `decide_stream_ending` 的 `terminal_seen` 分支上加一句注释，说明它已由 `_deliver` 在更早的位置抢答，此处保留是为了让这个纯函数对「位置」的描述保持完整、以及给未来别的调用者用；并在 `stream.py` 那条注释里回指。这样两处互相知道对方存在，不会有人下次读到时以为是重复实现。
- 或者在 `.dev/docs/` 的对应 `status.md` / 结构怪味登记里记一条，等这块再动时一起收。项目里已有「结构怪味登记」这个惯例（`pipeline_app.py:706` 的注释引用了它），沿用即可。

无论选哪个，**这属于「记一笔」而不是「改代码」**，不阻塞。

### 问题 4：改那两条既有测试，是不是「把守卫改软」？

**证伪——不是改软，是改硬。** 这一条我做了决定性的对照实验，结论是：其中一条测试**原本根本没有守住它 docstring 声称的规则**，改夹具之后才守住了。

先把两条测试原本守的东西说清楚：

- `test_an_upstream_tear_is_still_raised_rather_than_framed` 守的是：上游撕裂**抛出**而不是被包装成 SSE 错误帧。
- `test_a_stream_the_client_already_saw_is_not_replaced` 守的是：客户端已经收到内容之后，撕裂**不得触发 replay**（否则会收到第二份）。

实验用的是 `/tmp/mut2/test_variants.py`：把两条测试的**新旧夹具并排**成四条 test，再对源码施变异，看谁红谁绿。四个格子的结果：

**实验 4-1（对照，未变异，修复在位）**

```
FAILED test_A_old_fixture_raises - Failed: DID NOT RAISE ConnectionError
FAILED test_B_old_fixture_raises - Failed: DID NOT RAISE ConnectionError
2 failed, 3 passed
```

两条旧夹具在修复之后都不再抛了。也就是说**夹具非改不可**，不是可改可不改。这一步只证明「被迫」，不证明「没变软」。

**实验 4-2（决定性）：破坏 test B 声称守护的那条规则，看新旧夹具谁能发现**

变异 M3：把 `decide_stream_ending` 最后那支 `return EndingVerdict(ABANDON, detail="response opened with content already delivered")` 改成 `return EndingVerdict(REPLAY, reason)`——这正是 test B 的 docstring 所说的规则。

- **M3 + 修复在位**：`test_B_new_fixture_raises` **红**。
- **M3 + 修复撤掉（M1，即修复前的世界）**：

```
FAILED test_B_new_fixture_raises - Failed: DID NOT RAISE ConnectionError
1 failed, 4 passed          <- test_B_old_fixture_raises 绿
```

**旧夹具对这个缺陷完全瞎。** 原因也清楚：旧夹具用了完整的 `anthropic_stream("first")`，`terminal.seen` 为 `True`，于是 `decide_stream_ending` 在**第一支**就返回 `COMPLETE`，压根走不到「客户端已持有内容」那支——它当年抛异常靠的是 `COMPLETE is not REPLAY`，跟它 docstring 里写的规则毫无关系。作者在新 docstring 里写的「It raised for the right reason by accident」，我实测确认属实。

**实验 4-3：test A 的守卫是否还在**

变异 M4：把第 306 行 `raise torn` 换成 `break`（即「被包装成帧而不是抛出」）。

```
FAILED test_A_new_fixture_raises - Failed: DID NOT RAISE ConnectionError
FAILED test_A_old_fixture_raises - Failed: DID NOT RAISE ConnectionError
```

新旧夹具**都能打红**。所以 test A 的鉴别力一点没丢，只是把「撕裂点在终结事件之前」这个前提摆正了。

**有没有失效面丢掉？** 有一个，但它被搬走了而不是被丢掉：旧 test A 覆盖的「终结事件之后撕裂」这个位置，现在由新测试 `test_a_stream_torn_after_its_terminal_event_is_still_delivered_whole` 覆盖，只是期望反了过来——这正是本次修复的全部内容。**我找不到任何一个失效面是两条测试改完之后无人覆盖的。**

一条与此相邻、值得你顺手处理的：问题 2 里已经说了，`test_the_client_deadline_is_the_one_ending_that_says_so` 的夹具**也**有同一个毛病（用完整 `anthropic_stream` 当「凑几个已交付的块」的懒办法，混进了 terminal event）。作者这次清了两条，还剩这一条（可能还有 `test_a_held_back_policy_still_hears_the_client_deadline`）没清。**同一个模式，值得一并收掉**，但因为它同时牵涉问题 2 那个未决的次序问题，我把它标为建议而非要求。

### 问题 5：新增测试的分辨力

**证实，且最终提交版比派发给我的草稿版强不少。**

**（a）变异检验复跑——对最终提交态**

M1（撤掉 `if assembler.terminal.seen: break`）：

```
FAILED test_a_stream_torn_after_its_terminal_event_is_still_delivered_whole[block] - httpx2.RemoteProtocolError: <StreamReset stream_id:3, error_code:8, remote_...
FAILED test_a_stream_torn_after_its_terminal_event_is_still_delivered_whole[full]  - httpx2.RemoteProtocolError: ...
2 failed, 42 passed
```

**两档都打红，确认。**（对草稿版跑同一变异也是 2 红，报错是 `ConnectionError: upstream tore`——那正是我 §0 里撞上的那次输出。）

**（b）断言集是否够——「改坏了但测试仍绿」的搜寻**

我对**草稿版**找到过一个真的洞，对**最终版**则没找到：

变异 M5：`remaining = session.finish()` → `remaining = session.finish() or tuple(session.delivered)`，即把已交付的块再发一遍。

- **草稿版**：新测试 **2 passed** ← 洞。当时的断言是 `'"text":"one"' in body` 等「包含」型断言，重复交付一份照样包含。
- **最终版**：`FAILED …[block] - AssertionError: assert ['message_sta...k_delta', ...] == [...]` ← **补上了**。

最终版加的三样东西正好各堵一类：

1. `assert events_of(chunks) == [...]`（**精确相等**）堵重复交付、堵缺帧、堵多出 `error` 帧；
2. `assert reopened == 0` 堵「给一份已完整的回复又开了一次尝试」；
3. 把夹具换成 `httpx2.RemoteProtocolError` + 配好 `eligible` 的 `replay`，堵住 docstring 里点名的两个假修复（`terminal.seen and replay is None`、`terminal.seen and isinstance(torn, ConnectionError)`）。

我另外试了 M8（把 held-back 路径的 `message_start` 前导去掉）：最终版新测试的 `[full]` 档**打红**，另有三条既有测试同时打红。

**结论：最终版断言集我找不到「改坏了仍绿」的改法。** 需要说清这个结论的边界——它是「我这一轮试过 M1/M4/M5/M8 四种改法都被抓住」，不是「不存在这种改法」。够据此行动，不够当成完备性证明。

**（c）不建议做的事**：不要为此再加参数化矩阵或变异框架。`until-tool-use` 那一档我已用探针实测（问题 1），行为与另两档逐帧一致，加进参数化只会让同一条汇合路径被跑第三遍。

### 问题 6：漏掉的失效面

逐条查了你点名的五项，外加两项我自己找的。

| 项 | 结论 | 依据 |
|---|---|---|
| `session.finish()` 在 break 路径上被调用两次 | **证伪，不会。** `break` 跳出 `while True` 只发生一次，`session.finish()` 在循环外只有一处 | 读代码 + 问题 1 的探针（每块恰好一份） |
| `assembler.terminal.usage` 的传递 | **证实，正常传递。** 探针里 `usage: True` 九个组合全中；`terminal_frames(usage=terminal.usage or None)` 在 break 路径与正常路径是同一段代码 | `probe_wire.py` 输出 |
| replay 预算 | **证实，无变化。** `decide_stream_ending` 的 `if terminal_seen: return COMPLETE` 排在 `ledger.take(reason)` **之前**，所以修复前这条路也从未花过预算；修复后更早短路，同样不花 | 读 `retry.py:134-142` |
| `context.reply` 的写入门 | **证实，无变化。** `_StreamAccounting.finish` 里是 `if terminal.seen and self.context is not None`，`terminal.seen` 修复前后都是 `True`，所以 History / hooks 侧看到的东西没变 | 读 `pipeline_app.py:707` |
| `_StreamAccounting` 的记账 | **变了，而且是发现 A。** 见下 | 正反两次实测日志行 |
| （自查）跳过 `replay.eligible` 是否有副作用 | **证伪，无副作用。** 生产的 `eligible` 是 `_replay_reason`，纯函数，只做 isinstance 与 `normalize_upstream_error` | 读 `pipeline_app.py:563-575` |
| （自查）`break` 对非传输类异常也生效 | **发现 E，当前不可达** | 见下 |

#### 发现 A（major）：完成行现在对上游 reset 完全沉默

这条我做了正反两次实测，用的是项目自己的 `_StreamAccounting` + `_tracked_delivery`（把 `tests/int/test_pipeline_app.py` 复制到 `/tmp/mut2/intprobe/` 后追加一条探针 test，夹具是完整 `sse_upstream("first","second")` 后抛 `httpx2.ReadError("connection reset by peer")`）。

**修复后（提交态）**：

```
INFO app.request {'status': 'ok', 'event': '200 POST /v1/messages 0ms ↓0B end_turn', 'prefix': '[ OK ]'}
```

**修复前（M1）**：

```
[FAIL] 200 POST /v1/messages 0ms ↓0B end_turn: stream failed before a terminal event: connection reset by peer req=req_1
```

修复前那行是**自相矛盾**的（`end_turn` 与「before a terminal event」并列），作者说它错，我确认它错。但修复把它换成了一行**真话 + 全部沉默**：`connection reset by peer` 这个事实，现在**不出现在任何地方**——`accounting.failure` 是 `None`（因为 `_tracked_delivery` 正常跑完，走的是 `drained = True`），`torn` 这个局部变量在 `break` 之后就被丢弃，没有任何日志、计数或 trace 字段承接它。

`_ending()` 自己的 docstring 写着：failure「is the only account of what went wrong that exists anywhere」。对这一类撕裂，现在 anywhere 里没有了。

**这是不是缺陷？我认为是，但不严重，而且有一个反方向的先例需要你一起权衡**：项目已有裁决（`test_a_stream_cut_after_its_stop_reason_is_not_called_truncated`，`tests/int/test_pipeline_app.py:1833`）说「`message_delta` 之后被切断的流已经把客户端应得的都说了，不算 truncated」。按同一逻辑，`message_stop` 之后被 reset 报 `[ OK ]` 是自洽的。

但 `.dev/docs/upstream/h2-goaway/findings.md` 的「未决」栏里明写着两项：「上游响应被提前关闭的频率」「本项目自身的传输失败频率——此前零生产数据，日志刚上线」。**这次修复恰好把其中一类样本从日志里抹掉了**。刚建起来的观测面，被一次修复静默削掉一角。

**建议动作**（倾向第一个，代价最小）：

1. 在 `break` 之前把 `torn` 记一笔——最轻的做法是给 `_StreamAccounting` 加一个与 `failure` 分开的字段（例如 `tore_after_terminal: BaseException | None`），完成行仍判 `ok`，但在 detail 里附一句。这样 `[ OK ]` 与「reset 发生过」不再互斥。
2. 或者退一步，只记一条 debug 级日志。
3. 或者明确裁决「这个事实不需要留痕」，并把裁决写进 `.dev/docs/` ——按 `record-what-not-adopted`，**不采纳也要写下为什么**。

我不主张为此加门禁或指标体系，一个字段或一行日志就够。

#### 发现 D（minor）：注释的「true by construction」说过了

注释第三段：

> every `raise torn` below now runs with `terminal.seen` false, so a completion line reading `stream failed before a terminal event` can no longer be printed for a stream that saw one.

前半句**成立**（三处 `raise torn` 都在 `break` 之下）。后半句**说满了**：`_StreamAccounting.failure` 并非只由 `raise torn` 喂养——`break` 之后的 flush 段（`session.finish()` / `block_frames` / `terminal_frames`，`stream.py:323-351`）若抛出任何 `Exception`，它会绕过 `except`（那时已出 `try`）直达 `_tracked_delivery` 的 `except Exception`，此时 `terminal.seen` 为 `True`，`_ending()` 照样会打印那句话。

这是构造性论证，我**没有**在生产或测试里观测到这条路径被触发（`block_frames` 的输入是已完成的块，序列化失败需要相当异常的 payload）。所以权重是**倾向**，不是行动依据。

建议把 that 后半句改成有条件的说法，例如「每一处 `raise torn` 都不再以 `terminal.seen` 为真的状态运行」——只保留能证明的那一半。按 `state-decisiveness`，绝对化的措辞比事实错误更难被后人发现。

#### 发现 E（minor，仅存档）：`break` 吃掉的是所有 `Exception`

`except Exception as error: torn = error` 捕的是整个 `Exception`，所以 `break` 一旦触发，被放行的不止传输撕裂，还包括 `BufferCapExceeded`（`DeliveryError`，交付侧故障）、assembler 对畸形事件的报错、`read_events` 的解析错误、`_events_with_ping` 的 cleanup 失败。

我查了可达性：

- `BufferCapExceeded` 只在 `buffer.add()` 抛出，而 `add` 只由块完成触发。`AnthropicAssembler` 的 `terminal.seen` 只由 `message_stop` 置位，`ResponsesAssembler` 只由 `response.completed` / `response.incomplete` 置位——两者在正常上游里都排在最后一个块之后。**要触发需要上游在终结事件之后再送出一个完整块**，我没有找到这样的上游行为记录。
- 其余几类在终结事件之后触发，语义上「回复已完整、之后的噪声不该毁掉它」也说得通。

所以**当前不可达，且即使可达行为也大致合理**，我不建议现在收窄捕获范围（收窄会引入一份异常白名单，那正是这次修复所反对的「让分类法决定一份完整回复的去留」）。仅记录，供日后有人给 `ResponsesAssembler` 加终结事件之后的块处理时回看。

#### 发现 F（minor，仅存档）：`until-tool-use` 未参数化

新测试只跑 `block` / `full`。我用探针实测了 `until-tool-use`（含 `text → tool_use → text` 这种会触发 `_released_after_tool_use` 的形状），逐帧与另两档一致。**不建议加进参数化**——三档在 `break` 之后汇合到同一段代码，第三次跑的是同一条路径，符合项目「不预建完整状态空间」的取向。写在这里是为了让下一个人不必重新问一遍。

## 3. 我的实验环境（可复现，且不碰共享树）

所有变异都跑在 `/tmp/mut2/pkg`（`src/` 的副本），通过 `PYTHONPATH` 压过 venv 里的 editable `.pth`。**本工作树的源码全程零改动**：

```
$ cat .venv/lib/python3.14/site-packages/_editable_impl_app.pth
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon/src

$ PYTHONPATH=/tmp/mut2/pkg ./.venv/bin/python -c "import app.pipeline.delivery.stream as s; print(s.__file__)"
/tmp/mut2/pkg/app/pipeline/delivery/stream.py
```

pytest 侧也单独证过（`/tmp/mut2/prove_harness.sh`，一条断言 `s.__file__.startswith("/tmp/mut2/pkg")` 的 test，通过）。每轮变异后都 `cp -a` 回原文件并 `sha256sum` 比对；收尾时：

```
$ sha256sum /tmp/mut2/pkg/app/pipeline/delivery/stream.py src/app/pipeline/delivery/stream.py
1c0b8392…  /tmp/mut2/pkg/app/pipeline/delivery/stream.py
1c0b8392…  src/app/pipeline/delivery/stream.py
$ git status --short
（空）
```

留在 `/tmp` 的产物（可随时删）：`/tmp/mut2/pkg/`（源码副本）、`/tmp/mut2/test_variants.py`（问题 4 的四格实验）、`/tmp/mut2/probe_wire.py`（问题 1 的三档探针）、`/tmp/mut2/intprobe/`（问题 6 的记账探针）、`/tmp/mut2/prove_harness.sh`、`/tmp/rerun_stream.sh`、`/tmp/mutcheck/`（第一次拷贝时嵌套错的目录，无用）。**这些都是测试侧资产，没有一件进过仓库。**

## 4. 建议的处置顺序

1. **必做**：把问题 2 的未决点写进对应主题的 `deferred.md`（deadline 与 `terminal.seen` 的相对次序 + 三条 deadline 测试夹具已无法区分两种情形）。这是唯一一条我认为不做就算漏的。
2. **建议做**：发现 A ——给「上游在终结事件之后 reset」留一个落点，或明确裁决不留并写下理由。
3. **建议做**：发现 D ——把注释里那半句绝对化的措辞收回到能证明的范围。
4. **建议做**：发现 B ——给 `decide_stream_ending` 的 `terminal_seen` 分支加一句回指注释，或登记进结构怪味。**不要删。**
5. **可选**：把 `test_the_client_deadline_is_the_one_ending_that_says_so`（及 `test_a_held_back_policy_still_hears_the_client_deadline`）的夹具按同一模式改成 `[:-2]`，与 1 一并裁决。
6. **不要做**：不要合并进 `if torn is None`；不要把判断移进 verdict switch；不要给新测试加 `until-tool-use` 参数化；不要加门禁/变异框架。

## 5. 给主会话的两条流程观察（非缺陷）

1. **评审对象在评审期间被就地修改并提交。** 这次结果是好的（最终版测试明显更强），但它让我前半程的两条发现失效，也让我一度把作者的变异检验误判为测试 flake——我为此花了 ~5 分钟和 12 次重跑去追一个不存在的竞态。如果下次仍要在同一棵树上边改边评，**建议派发时给一个固定的 commit 或 stash 引用**，而不是「未提交的 `git diff`」。
2. **作者在 `c86712d` 的 docstring 里写了自己做过的负向验证**（「两个错误实现都被草稿版判绿，都是实测」）。这条信息对我极有价值——它直接告诉我草稿版的洞在哪，省掉我自己去构造那两个假修复。这是个值得推广的写法。
