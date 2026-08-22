# P2 修复交接：`StreamEnding.COMPLETE` 不再被当成传输失败丢弃

**日期**：2026-08-22
**分支**：`worktree-260822-complete-not-abandon`，提交 `c86712d`，基线 `4c7129a`
**工作树**：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-complete-not-abandon`（保留，未删）
**性质**：一次性交接记录（点时）。上游诊断见 `260822-h2-streamreset-cancel-diagnosis.md`。

---

## 1. 修了什么

`decide_stream_ending()` 有三格返回值，但 `_deliver()` 只问了「是不是 `REPLAY`」：

```python
if verdict.ending is not StreamEnding.REPLAY:
    raise torn
```

于是 `COMPLETE` 与 `ABANDON` 被折叠。后果：上游已经发完 `message_delta` + `message_stop`、紧接着连接被 reset 时，代理手里已有完整回复，却当成传输失败丢弃并向 ASGI 抛异常。`block` 策略下丢掉收尾帧，`full` 策略下**整条回复都丢**。

改动是 7 行：在 `_deliver` 的错误处理里、`ClientDeadlineError` 分支之后、`replay.eligible` 之前，加

```python
if assembler.terminal.seen:
    break
```

## 2. 为什么放在那个位置

- **必须在 `replay.eligible` 之前**：上游有没有说完是 assembler 已观察到的**位置事实**，不该由异常 taxonomy、有没有配 replay、或预算来决定。放在 verdict switch 里只能覆盖「replay 已接线且异常被识别」这一种；一个裸 `h2.ProtocolError` 会绕开所有包装边界，`normalize_upstream_error` 对它返回 `None`，完整回复照样被丢。
- **必须在 `ClientDeadlineError` 之后**：那条分支同日刚裁决过并有测试固定。「跑超时了」与「上游已完成」是两个问题，重排属于新的 deadline policy 裁决，不在本次范围。
- **合并进 `if torn is None:` 不可行**：写成 `if torn is None or assembler.terminal.seen:` 会让 terminal 压过 `ClientDeadlineError`，现有 `test_the_client_deadline_is_the_one_ending_that_says_so` 语义改变。

## 3. 一个已知的结构余味（不阻断，登记备查）

加了这一支之后，从**唯一生产调用点**看，`decide_stream_ending()` 的 `COMPLETE` 分支已不可达——调用者到达该函数时 `terminal_seen` 恒为 false。

这不是 correctness 缺陷（同一条规则在调用者处以更完整的位置事实答完了），但它是职责形状上的余味：函数文档仍宣称三格，生产只问其中两格。**不要为本次小修扩大重构。** 后续整理时应明确二选一：要么让 policy 只裁「未完成流」，要么重塑参数使调用者能在分类前真正问出完整 verdict——而不是留一个看似接线、实则恒不可达的 `COMPLETE`。

## 4. 我改了两条既有测试的夹具，理由与证据

`anthropic_stream(*texts)` 末尾自带 `message_delta` + `message_stop`。两条既有测试把「一条完整流」当成「凑几个已交付的块」的懒办法，于是夹具里混进了 terminal event，与它们 docstring 自述的命题不符：

| 测试 | 它自述守的是 | 旧夹具实际测的是 | 改法 |
|---|---|---|---|
| `test_a_stream_the_client_already_saw_is_not_replaced` | 已交付 block 的**未完成** attempt 不可无痕 replay | 已经完整结束后又出现另一段并 tear | 第一段 `[:-2]` |
| `test_an_upstream_tear_is_still_raised_rather_than_framed` | **未完成**的普通 upstream tear 仍然 raise | 完整 terminal 之后才 tear | `[:-2]` |

异源评审用 `git blame` 独立核过：两条测试的 docstring **从引入的第一天起**就只说未完成流，是夹具后来带错了。改后两条各自的守卫仍然成立（分别命中 `ABANDON` 守卫与 raise 路径）。

## 5. 变异检验（四个变异，全部被咬住）

新增 `test_a_stream_torn_after_its_terminal_event_is_still_delivered_whole`（参数化 `block` / `full`）。

**初稿的测试不合格，这一点必须写下来**：它用 `replay=None` + `ConnectionError`，异源评审构造的两个受控变异让**四条相关测试全绿**——

| 变异 | 初稿测试 | 加固后 |
|---|---|---|
| 整支删除 | 红 | 红 |
| `and replay is None` | **绿（漏网）** | 红 |
| `and isinstance(torn, ConnectionError)` | **绿（漏网）** | 红 |
| `break` → `return` | 未测 | 红（靠精确事件序列断言） |

加固的做法**不是加参数矩阵**，是让同一条测试走承重路径：传真实 `ReplaySupport`（`eligible` 恒返回 `NETWORK`、`reopen` 是「被调用即计数」的探针）、用生产真正会抛的 `httpx2.RemoteProtocolError`、断言 `reopened == 0`、并把包含性断言换成 `events_of(chunks)` 的精确序列。

第二个变异尤其要紧：它恰好推翻了源码注释里「完成事实不依赖异常类型」那句话——`h2.exceptions.ProtocolError` 的 MRO 是 `ProtocolError -> H2Error -> Exception`，不是 `ConnectionError`。

## 6. 验证

```
uv run ruff check src tests                          -> All checks passed
uv run pyright <改动的两个文件>                        -> 0 errors
uv run pytest tests --cov=app --cov-fail-under=80    -> 1686 passed, 3 skipped, 91.00%
```

（本工作树全量绿。主树同期的 21 个 pyright 错误在 `stream_cap` 一带，是同伴在飞工作；主树 pytest 的 1 个失败来自用户未提交的 `config.example.yaml`。两者都不在本分支。）

## 7. 集成注意事项 —— 给做交付侧重写的同伴

主树此刻有未提交的 `_hand_over` / `ContinuationSupport` 改动。**那份重构把本 bug 变成了更严重的形态**：

```python
if verdict.ending is StreamEnding.REPLAY: ... continue
handed_over = _hand_over(...)      # ← COMPLETE 落到这里
if handed_over is not None: ...; return
raise torn
```

`terminal.seen=True` → verdict 是 `COMPLETE` → 不是 `REPLAY` → 进 `_hand_over`。而 `synthesize(error, stop_reason)` 的签名看不到 `terminal.seen`，所以会照常合成。**结果是一条上游已经发完 `message_stop` 的完整回复，被合成成 `turn_interrupted` 工具调用交给客户端，`stop_reason=tool_use`，客户端会去续写一个已经写完的回合。**

本分支的这一支落在那份 diff 没有触碰的区域，可直接取走折进重写。**唯一的硬要求是：这一支必须在 `_hand_over` 之前。**

## 8. 评审状态

- GPT 异源评审：`260822-review-complete-fix-gpt.md`，判 `needs-fix`（生产代码正确、夹具纠正正确，测试分辨力不足）。**该意见已按 §5 闭环并复测。**
- Opus 评审：派出后约 40 分钟未落盘，本文写作时仍在进行。若其结论落地且与本文冲突，以复跑证据为准。
