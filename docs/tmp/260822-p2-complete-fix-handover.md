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

## 8. 评审状态（两轮都已闭环）

- **GPT 异源评审**：`260822-review-complete-fix-gpt.md`，判 `needs-fix`（生产代码正确、夹具纠正正确，测试分辨力不足）。**已按 §5 闭环并复测。**
- **Opus 评审**：`260822-review-complete-fix-opus.md`，判 `needs-fix`，6 条发现（3 major / 3 minor），8 个受控变异，1 条必做。处置如下：

| 发现 | 处置 |
|---|---|
| 「把守卫改软」—— **证伪** | 无需动作。它做了新旧夹具四格对照：在「修复前 + 破坏『客户端已持有内容不得 replay』规则」那一格里旧夹具**绿**、新夹具**红**，即旧测试**从来没守住过它 docstring 声称的规则**（靠 `COMPLETE is not REPLAY` 抛异常才绿）。改夹具是改硬不是改软 |
| 位置载重性 | 已实测确认：合并进 `if torn is None` 会让三条 client-deadline 测试全红 |
| **A（major）**：完成行对上游 reset 完全沉默 | **登记为待裁项**，`../upstream/retry-and-continuation/deferred.md` 第 12 条。归交付侧重写切片——留痕需要一条 `_deliver` → `_StreamAccounting` 的新通道 |
| **B（major）**：`COMPLETE` 成孤儿件 | `1479025` 加回指注释，并补进 `deferred.md` 第 7 条。**不删**，**不**移进 verdict switch |
| **C（major，必做）**：deadline 与 `terminal.seen` 次序未裁 | **已写进 `deferred.md` 第 11 条**，含三条 deadline 测试夹具已无法区分两种情形这一事实 |
| **D（minor）**：注释「true by construction」说满了 | `1479025` 已收回到能证明的范围 |
| **E（minor）**：`break` 吃掉所有 `Exception` | 仅存档，评审自判可达性低 |
| **F（minor）**：`until-tool-use` 未参数化 | 不做。评审用探针实测三档逐帧一致，自己也不建议补 |

**一条我要认的流程问题**：评审进行中我在同一棵树上改了测试文件并提交（11:42 改、11:47 提交 `c86712d`），导致该评审前半程的两条发现失效，还把我的变异检验误判成测试 flake、为此花掉约 5 分钟和 12 次重跑。**下次在同一棵树上边改边评，派发时应给固定的 commit 或 stash 引用，而不是「未提交的 `git diff`」。**

---

## 9. 集成结局（2026-08-22 收尾，本节是本文最终状态）

**这份分支的代码修复没有被合并，因为同伴先做完了同一件事。** 时间线，全部经 `git log` / `git show` 核实：

| 时刻 | 提交 | 内容 |
|---|---|---|
| 11:20 | `bce8b0d` | 同伴独立发现并修复：在 verdict switch 里 `if verdict.ending is StreamEnding.COMPLETE: break`。同时修正了 `test_a_stream_the_client_already_saw_is_not_replaced` 的夹具（用 `[:3]`） |
| 11:47 | `c86712d`（分支） | 本会话的修复：判断前移到 `replay.eligible` 之前 |
| 13:03 | `1743a0b` | 同伴采纳本会话经评审提出的意见（提交信息原文：「A peer's review of the previous fix found it one door short」），把判断前移，并补了 `h2.ProtocolError` 那一档的测试与另一条夹具修正 |
| — | `f0527e5` | **本会话最终并入 main 的部分**：只有测试加固 + `retry.py` 一行注释 |

**所以「合并」的实际结果是**：语义早已在 main（经同伴之手），本会话最终贡献的是把守卫加硬。

### `f0527e5` 加硬了什么，以及各自的依据

同伴的 `test_a_finished_turn_survives_a_failure_nothing_recognises` 有三处可以「守卫失效而测试仍绿」：

| 弱点 | 加固 | 依据档位 |
|---|---|---|
| 用自造的 `_UnrecognisedTear` + 桩 taxonomy，断言的是前提而非发现；若 `normalize_upstream_error` 将来学会命名它，测试照绿而被守护的情形已不存在 | 换成生产分类器 + 真实 `h2.ProtocolError`，并**显式断言前提** `eligible(torn) is None` | 前提卫生，非变异所证 |
| 只跑 `block` | 加 `full`。`full` 下撕裂到达时一个字节都没交付，整条回复在险，且恢复它要走**循环之后的 flush**，`block` 因为没有扣留块根本不经过 | **实测**：把 held-back preamble 那支置假，`full` 打红、`block` 仍绿 |
| 包含式断言（`in body` / `[-1] == "message_stop"`），重复交付或多一个生命周期都能过；`reopen` 未被计数 | 精确事件序列 + `assert reopened == 0` | 构造性；重复交付这一形态由精确序列覆盖 |

对照变异（证明测试仍咬得住原 bug）：把 `if assembler.terminal.seen:` 置假，两档均打红（`h2.exceptions.ProtocolError`）。

### 归档

- `archive/260822-complete-not-abandon` → `1479025`（第一版，基线 `4c7129a`，两轮评审的对象；**未合并，语义已由 `bce8b0d`+`1743a0b` 覆盖**）
- `archive/260822-finished-turn-unnamed-failure` → `2230852`（第二版，基线 `f191e4d`；**未合并，同上**）
- `archive/260822-finished-turn-guard` → `22c7e8d`（第三版，即 `f0527e5` 的已评审源）

工作树 `.claude/worktrees/260822-complete-not-abandon` 保留。

### 集成时 main 的状态（如实记录，不是本会话造成的）

`1743a0b` 起 main 在 HEAD 上带 3 个失败：`tests/int/test_pipeline_app.py` 的三条引用了 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`，而该键在 schema 里尚不存在——同伴正在主树里加（`schema.py` 未提交）。按项目规矩，提交边界由语义定而非绿灯定，这是允许的状态。**本会话的 `f0527e5` 与之无关**：改动只有 `retry.py` 一行注释和测试文件，且落盘前已核实两文件在主树干净、在 `1743a0b..64bff1e` 之间无变化。落盘用 `git checkout <branch> -- <2 files>` + pathspec 提交，主树索引里同伴暂存的 15 个文件全程未被卷入（提交后复核为恰好 2 个文件）。

门禁（`f0527e5` 之后，主树）：`ruff check` 两文件通过；`pyright` 两文件 0 错误；`tests/unit/pipeline` 468 passed；`tests/unit/pipeline/delivery` 115 passed。
