# `one-ending-decision` 独立评审报告

> **落盘说明**：本文正文由独立评审者（异源模型）撰写，共四轮。评审者所在执行环境受上级约束无法直接写文件，故由实现者按其原文落盘，未作删改。第七节「第四轮」为实现者补记的处置状态，与前文分开标注。

## 一、评审对象与范围

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/one-ending`
- 分支：`fix/one-ending-decision`
- 基线：`4d96af8`
- 初始候选：`1e85449`
- 第三轮复核候选：`28b3e64`
- 已复核的连续修订：`53325be`、`791b4f6`、`91c56c6`、`28b3e64`
- 权威需求：`docs/.human-controlled/upstream-retry-and-continuation.md`
- 辅助裁决记录：`.dev/docs/upstream/retry-and-continuation/decisions.md`、`deferred.md`、`status.md`

本次评审只读，没有修改被评审工作树、文件或 Git 索引。

## 二、总评（截至 `28b3e64`）

**结论：needs-fix。**

候选已经正确完成主体目标：clean EOF、transport tear 与显式 terminal failure 现在进入统一裁决区域；Anthropic 分半终结与 Responses 同事件终结得到一致的语义判定；已交付内容的 clean EOF 不会获得无痕重放；不可继续的本地错误不再错误交接；显式上游失败不再一律伪装成 network；error frame、MCP hand-over 与成功 terminal 之间没有发现双重收尾。

前三轮发现的 6 个 major 与 4 个 minor 均已得到实质修正，相关受控复现也已转为期望结果。不过，`28b3e64` 为记录 client deadline 新增的 `_noting_client_deadline()` 破坏了异步迭代器的 close 传播，并且没有覆盖 replay 后替换进去的新 iterator。前者会让客户端断开时上游响应不能立即释放，属于当时候选的 major；后者使上一轮修复的日志归因在 replay attempt 上仍失效，属于 minor。

| 级别 | 数量（截至 `28b3e64`） |
|---|---:|
| blocker | 0 |
| major | 1 |
| minor | 1 |

## 三、第三轮之后仍需修复的发现

### major-1：`_noting_client_deadline()` 截断了 upstream iterator 的 close 传播

位置：`src/app/server/pipeline_app.py:191-203`

`_noting_client_deadline()` 使用裸 `async for chunk in chunks`，但没有在自身被关闭时调用内层 iterator 的 `aclose()`。本项目现有交付链明确把「每一层都向下传播 close」作为资源所有权契约；`read_events()`、deadline wrapper、`stream_delivery()` 与 `_tracked_delivery()` 都为此显式实现了清理。

当前调用链是：

```text
read_events
  -> _noting_client_deadline
    -> with_client_deadline_at
      -> _counted_upstream
        -> with_deadline_at
          -> with_idle_timeout
            -> response.aiter_bytes()
```

`read_events()` 会关闭 `_noting_client_deadline()`，但 `_noting_client_deadline()` 不会继续关闭 `with_client_deadline_at()`。因此客户端断开、生成器被提前关闭等本侧终止路径会在这一新层停住，内层 `_bounded()` 的 `finally` 无法立即运行，上游 HTTP response 也不能按既有合同及时释放。

受控探针直接驱动当前 helper：

```text
closed_immediately=False
closed_after_explicit_inner_close=True
```

这证明 wrapper 自身关闭后，内层 generator 仍保持打开；只有显式关闭内层后，其 `finally` 才执行。证据强度足以行动，且对应真实生产清理链，不是测试专用形态。

建议沿用本文件和 `sse_source.py` 的既有做法：在 `_noting_client_deadline()` 中显式取得并在 `finally` 调用内层 `aclose()`，或用与其类型合同相容的 `aclosing` 结构。应增加一条直接断言「关闭 noting wrapper 会立即关闭 source」的回归测试。

### minor-1：client deadline 的记录 wrapper 没有包住 replay 后的新 iterator

位置：`src/app/server/pipeline_app.py:545-557`

首个 attempt 的 body 经过 `_noting_client_deadline(with_client_deadline_at(...), accounting)`，但 `_reopen()` 返回的新 attempt 仍只有 `with_client_deadline_at(...)`。`_deliver()` replay 时会直接把 `chunks` 重绑定为 `_reopen()` 返回的新 iterator；首个 attempt 外面的 `_noting_client_deadline()` 不会跟随过去。因此 client deadline 如果在 replay attempt 上触发，wire 仍会正确收到 `client_deadline_exceeded`，但 `accounting.client_deadline_fired` 保持 `False`，日志继续落回 upstream failure 或 generic drain 的归因。

受控复现结果：

```text
reopened=1
wire_client_deadline=True
client_deadline_noted=False
```

这与本 delta 要修复的「wire 说什么，日志就说什么」仍不一致。证据强度足以行动。

建议把「构造受 client deadline 约束且会记录归因的 body」抽成同一个局部 helper，首个 attempt 与 `_reopen()` 都调用它，避免两处 wrapper 顺序继续漂移。相应测试应至少驱动一次 replay，再让 replacement iterator 抛 `ClientDeadlineError`，断言 `accounting.client_deadline_fired is True`。

## 四、前三轮发现及处置复核

### 第一轮：4 major、2 minor

#### major：`failure` 只在 clean drain 判据中优先，tear 后仍可按成功退出

初始代码只在 `torn is None` 时检查 `Terminal.failure`。若 upstream 先发送成功 terminal、再发送 error、随后 transport tear，`if terminal.seen` 会把 turn 当成成功。

原始受控复现：

```text
seen=True
failure=UpstreamFailure(type='overloaded_error', ...)
raised=None
clean_terminal=True
error_terminal=False
```

`91c56c6` 最终将「分类依据」与「实际抛出的异常」分开：`stopped` 优先取 `_truncation(terminal)`，而无交接时仍 `raise torn`。`28b3e64` 上复核结果：

```text
raised=ReadError
handed_over=False
error_terminal=True
```

该 finding 已修复。

#### major：`_hand_over` 被移到 retry eligibility 之外

初始改动使 `reason is None` 的错误也进入 `_hand_over`。这让 `BufferCapExceeded` 等权威文档明确归为「无法继续」的本地保护错误被合成为 MCP continuation。

原始受控复现：

```text
raised=None
first_block=True
handed_over=True
error_terminal=False
```

`791b4f6` 将 `_hand_over` 放回 `replay is not None and reason is not None` 内部。复核结果：

```text
raised=BufferCapExceeded
handed_over=False
error_terminal=True
```

该 finding 已修复。「可读」与「可恢复」已重新分开。

#### major：terminal failure 全部被包装成 `UpstreamTruncated(network)`

初始实现把 `response.failed` 与 terminal `error` 都转为无 status 的 `UpstreamTruncated`，而 `_replay_reason()` 又把该类型无条件映射到 `network`。结果是 `invalid_request_error`、authentication failure 等不可继续错误也获得 replay 或 hand-over 资格。

`791b4f6` 增加 type/code allowlist；`91c56c6` 又增加独立的 `reported` 事实，使「silent EOF」与「upstream 明确失败但没给 taxonomy」不再同形。

最终分类规则：

- `reported=False`：silent stop，判 `network`
- `reported=True` 且 type/code 位于 allowlist：可继续，判 `network`
- `reported=True` 且 taxonomy 为空或未知：保守判 `None`

受控复核：

```text
silent_reported=False silent_reason=RetryReason.NETWORK
failure_reported=True failure_reason=None
```

该 finding 已修复。

对 allowlist 的判断：未知 taxonomy 默认不可继续的方向正确，证据强度足以行动。它与项目既有 closed-set error normalization 一致，也避免把 400、401、refusal 或未来未知的永久错误默认为可恢复。当前六个成员均有合理的 transient 语义，没有发现应删除的成员：`overloaded_error`、`api_error`、`rate_limit_error`、`timeout_error`、`server_error`、`rate_limit_exceeded`。其中 `invalid_request_error`、`authentication_error`、`permission_error` 等正确地不在集合中。

#### major：具名 failure 在零交付或日志门上消失

初始 `_unfinished_ending()` 在没有已交付块、也没有 buffered block 时返回空列表，即使 upstream 已明确发送 terminal failure；与此同时，accounting 的 `delivered_whole` 没有检查 `terminal.failure`，使 stop reason 后发生的 failure 仍可保留 `[ OK ]`。

`791b4f6` 将 wire 行为收窄为：只有 `terminal.failure is not None` 时，零交付也发送 error frame；普通空 upstream stream 仍保持零字节合同。`91c56c6` 让 `_ending(terminal)` 优先渲染 upstream failure 原话。

该 finding 的主体已修复。

#### minor：空 exception message 使 `handed_over_cause` 仍为空

`791b4f6` 新增 `_cause_of()`，`str(error)` 为空时回退到 `type(error).__name__`。该 finding 已修复。

#### minor：新增测试插入位置使邻近 assertion 漂移

断言已经归还 `test_a_stream_cut_after_its_stop_reason_is_not_called_truncated`。该 finding 已修复。

### 第二轮：2 major、2 minor

#### major：显式 failure 后再 tear 时仍按 tear 分类

`91c56c6` 新增 `stopped`，分类与 hand-over 使用 `stopped`，实际记录仍使用 `raise torn`。当前受控复现已符合预期，该 finding 已修复。

#### major：message-only failure 仍被视为 silent EOF

`91c56c6` 给 `UpstreamTruncated` 增加 `reported`，不再从 type/code 是否为空推导「upstream 是否报告过 failure」。当前纯函数探针和新增回归测试均通过，该 finding 已修复。

#### minor：无 hand-over 的 terminal failure 日志只写 generic truncation

`91c56c6` 新增 `_failure_words()`，并令 `_ending(terminal)` 在 ordinary tear/drain 之前读取 `terminal.failure`。该 finding 已修复，但 client deadline 是更高优先级的特殊 ending，进入了第三轮 finding。

#### minor：yield 后 raise 的传输代价未登记

注释已明确登记 Uvicorn/h11 实测结果：客户端先收到完整 error SSE frame，随后因缺少 chunked final chunk 而以协议错误结束；「可读的帧不等于干净的 HTTP 收尾」，这是为保留 accounting tear attribution 接受的代价。该 finding 已修复。

### 第三轮：2 minor

#### minor：client deadline 与 terminal failure 同时存在时，wire 和日志归因冲突

`28b3e64` 新增 `_noting_client_deadline()` 与 `accounting.client_deadline_fired`，并把该标志放在 `_ending()` 的 terminal failure 之前。首个 attempt 上的基本归因已修正。但该修法引入第三节的 major-1，并漏掉 replay iterator，形成 minor-1。

#### minor：两个 major 修复没有回归测试

`28b3e64` 新增 `test_a_refusal_is_not_reclassified_by_the_tear_that_followed_it` 与 `test_a_reported_failure_without_a_kind_is_not_retried_as_a_silent_stop`，分别针对「分类不能退回读取 torn」和「reported 不能退回从 type/code 推导」，并已由实现者执行受控 mutation，能对目标回归变红。测试内容与生产 seam 对齐，没有发现同源 oracle 或恒真断言。该 finding 已修复。

## 五、七个重点问题的最终判断

### 1. `truncated`／unfinished 判据

当前核心判据：

```python
unfinished = terminal.failure is not None or (
    not terminal.seen and not terminal.stop_reason
)
```

语义正确。Anthropic upstream 的 `message_delta` 与 `message_stop` 分离：前者携带 stop reason 和 usage，后者只闭合。因此 clean EOF 位于二者之间时，`seen=False`、`stop_reason` 非空，不应叫 truncated。Responses upstream 的 stop reason 与 `seen` 在同一个 terminal event 中到达，不存在该中间态。两条腿状态形状不同，但语义一致。

当前又正确地区分：

```python
finished = torn is None and not unfinished
finished_then_tore = torn is not None and terminal.seen and terminal.failure is None
```

clean drain 在 Anthropic split ending 后可以完成；transport tear 则必须真正看到 terminal event。显式 failure 在两格中都优先。

### 2. 先 yield error frame 再 raise

已在当前项目 venv 的 Uvicorn/h11 上通过真实本地 TCP 实测，而非仅凭 ASGI 推理。

```text
frame_present=True
has_final_chunk=False
```

客户端确实先收到完整 error SSE frame，随后连接因没有 chunked final chunk 而异常结束。帧不会在 server exception 传播前被吞掉，但完整缓冲式 HTTP 客户端仍可能把最终结果报告为 protocol error；SSE consumer 则可以先处理 error event，再观察连接异常。当前注释已准确登记这项代价。

### 3. `_unfinished_ending` 的 flush 语义

与 `ClientDeadlineError` 的「不 flush」差异有正当理由。`ClientDeadlineError` 是本轮总时限的裁决，用户明确接受它到点时丢弃未交付 buffer；ordinary tear、clean truncation 或 terminal failure 下，buffer 中的块已经完整组装，客户端应获得这些完整块，buffering policy 不应改变最终能读到多少完整内容。

### 4. 是否存在双重收尾

没有发现 `_hand_over`、`_unfinished_ending` 与 `framer.terminal()` 之间的双重收尾路径。`_hand_over` 成功后 caller 立即 `return`；`_unfinished_ending` 后 clean drain `return`，tear 则 `raise`；正常 terminal tail 只在前述路径均未动作时到达；`session.finish()` 重复调用时 buffer 已被 drain。

### 5. `UpstreamTruncated` 分类与已交付路径

silent EOF 且未交付任何块时，`reported=False`，得到 `RetryReason.NETWORK`，符合用户新增裁决。silent EOF 且已交付完整块时，`decide_stream_ending()` 看到 `downstream_opened=True`／`committed_blocks>0`，返回 ABANDON，不会 replay；之后仅在 failure 可继续且 continuation 可用时 hand over，否则发 error ending。该路径已确认。具名 terminal failure 现在通过 allowlist 判定，不再自动获得 network replay。

### 6. 观测面

`handed_over_cause` 对非空错误保留 `str(error)`，对空错误回退 exception type；terminal failure 无 hand-over 时由 `_failure_words()` 输出 type/code/message。没有发现新增的信息泄漏合同问题。

### 7. 删除旧 `if not terminal.seen` tail 是否成立

成立。正常跳出 loop 的状态现在由 `finished` 或 `finished_then_tore` 明确约束。`stop_reason` 非空而 `seen=False` 的 clean Anthropic split ending 会进入成功 tail 并调用 `framer.terminal()`，这是既有裁决要求的行为；相同状态若由 tear 结束，则不会进入成功 tail。

## 六、验证与证据

### 候选身份与工作树

每轮开始均用 `git -C <worktree> log --oneline -1` 自证候选 HEAD。

### config test 失败归因

「在同 HEAD 的 detached clean worktree 复现」本身只能排除工作树污染，不能证明失败早于候选。补充核对显示 base `4d96af8` 与候选在以下直接输入上的 Git object 完全一致：

- `docs/.human-controlled/config.example.yaml`
- `src/app/config/`
- `tests/unit/config/test_config_schema.py`
- `pyproject.toml`
- `uv.lock`

候选 diff 也不触及这些文件或其 import 路径。因此该失败归因于既有状态的结论成立。

### 第三轮新增探针

`_noting_client_deadline` close 传播：

```text
closed_immediately=False
closed_after_explicit_inner_close=True
```

replay attempt 的 deadline 记录：

```text
reopened=1
wire_client_deadline=True
client_deadline_noted=False
```

## 七、第四轮：实现者对 major-1／minor-1 的处置（实现者补记）

> 本节的处置记录由实现者撰写；末尾的复核结论由评审者给出。

候选 HEAD：`28b3e64` → `f84e821`。

- **major-1（close 传播）**：`_noting_client_deadline()` 改用本链路既有写法——`close = getattr(chunks, "aclose", None)`，在 `finally` 中调用。新增 `test_noting_the_client_clock_still_closes_what_it_wraps`，断言打在 source 自己的 `finally` 上（唯一能证明 close 走完全程的位置）。**变异对照**：移除 close 传播后该测试变红，已精确反向还原，`rg MUTATION` 无残留。
- **minor-1（replay 未被包住）**：抽出局部 helper `_under_client_clock(inner)`，首个 attempt 与 `_reopen()` 都经由它构造，两处 wrapper 顺序不再各自组装。
- **测试覆盖的实际边界**：另加 `test_noting_the_client_clock_records_the_deadline_it_sees`，钉住记录器本身。**评审建议的「驱动一次真实 replay 再让 replacement iterator 抛 `ClientDeadlineError`」这条没有实现**——`_under_client_clock` 是 `_serve` 内的闭包，从测试不可达，要覆盖需搭建一套贯穿 app 的 replay harness。当前 replay 侧的正确性由「两处共用同一个 helper」这一结构性约束保证，**不是由测试保证**，此处如实登记。

第四轮门（`f84e821`）：`pytest tests/unit tests/int` → 1703 passed、1 failed（既有 config 那条）；`ruff check src tests` 全过；`pyright src tests` 21 errors，全部位于 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`，本分支未触碰。

### 第四轮复核结论（评审者）

**PASS，可提交用户。** `f84e821` 正确恢复 close 传播，受控探针由 `closed_immediately=False` 转为 `True`；首个 attempt 与 replay attempt 也已机械核对为共同调用 `_under_client_clock()`。

未实现 replay 端到端测试**不构成 pass 阻碍**：共享 helper 已消除两处独立组装造成的漂移，现有测试分别钉住 helper 的 deadline 记录与 close 传播，新增完整 harness 的收益不足以匹配成本。

第四轮计数：`blocker=0 major=0 minor=0`。证据强度足以行动。

## 八、四轮总计

| 轮次 | 候选 | blocker | major | minor |
|---|---|---:|---:|---:|
| 一 | `1e85449` | 0 | 4 | 2 |
| 二 | `791b4f6` | 0 | 2 | 2 |
| 三 | `91c56c6` | 0 | 0 | 2 |
| 四 | `f84e821` | 0 | 0 | 0 |
| **合计** | | **0** | **6** | **6** |

12 条发现全部采纳。实现者另在四轮之间自行发现并修复 5 条（重新引入旧分支已修的 major、修复过宽打红四条既有测试、合并「完成」判据打红既有裁决测试、变异还原丢失未提交修复、以及本轮的测试覆盖边界如实登记）。

**一条值得记下的模式**：第二、三、四轮的发现全部是实现者在修上一轮问题时新引入的，形状一致——为让某个入口行为正确而改动共用结构，未检查它服务的其他调用者或其他状态组合。
