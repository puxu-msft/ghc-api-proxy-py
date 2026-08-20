# 定向复核 R2：上游流截断上报（11 条处置后的 delta）

- 复核对象：R1 报告 `docs/tmp/260820-review-truncated-stream-reporting.md` 全部 11 条的处置结果
- 复核时间：2026-08-20 13:36～13:55 UTC
- 复核者：独立评审 subagent（只读；未修改仓库任何文件）
- 结论：**needs-fix**（1 blocker，2 should，3 nit）

只复核 delta，R1 已确认无误的部分未重看。

## 0. 快照

| 文件 | sha256 |
|---|---|
| `src/app/server/pipeline_app.py` | `c3160f3a6f5acb0735c610473ed2dbaad3765d1f3849360c11589b70ea44036d` |
| `src/app/observability/request_log.py` | `ae5e54d91129b48e4f68178c43149be7a5323c3bf583d8b52d0fe018fc65c564` |
| `src/app/observability/logging.py` | `aa939cebccad9ebdb6230b71e4bf1da779b48dc355376a7b7bff317879e420d6` |
| `src/app/pipeline/delivery/stream.py` | `84754efe6c6720693fbdc7ff78adbe9ac9335f4b00d0bce27b17442e35ef63be` |
| `src/app/pipeline/delivery/assembler.py` | `2bd6fa68cb54c8c5b5f5b12acd4aebcfdb3e520ddb476dc5c9714189517b1f49` |
| `tests/http/test_pipeline_app.py` | `451bb59a28445f6dd92dfa6a42d7cc6e94d7fad6a27d9e1d2ea6b221e6bd283d` |
| `tests/unit/test_stream_delivery.py` | `8ff991958fd3c826b8dfce5e937c4f7510162d0b584838e9ff42a17c39f4c0f5` |
| `tests/unit/test_request_log.py` | `35fd403f7b073aa42e7e372d8de6c59ca36072f3a93324abbd0420db32141e2b` |

独立跑通的基线：全量 **1399 passed / 2 skipped**（你报的是 1396，期间工作树又前进过，方向一致）；`pyright` 全仓 **0 errors**；`ruff check` 对 delta 涉及的 9 个文件 **All checks passed**。仓库全量 `ruff check .` 有 331 条，全部落在 `exp/`、`verification/final_acceptance/probes/` 与 `.claude/worktrees/` 三处，与本次改动无关，属既有状态。

## 1. 发现清单

### B1（blocker，实测）新门 `not terminal.stop_reason` 把「上游在最后一个 delta 之后撕断」放回了静默成功

这正是你 Q3 问的假阴性，而且它存在。

S3 的豁免逻辑对 **drained** 那一支成立：上游字节流自己跑完 → `stream_delivery` 的 `async for` 正常结束 → 尾部 `if started:` 跑到 → 用上游自己的 `stop_reason` 与 usage 发出 `message_delta` + `message_stop` → 下游拿到逐字节正确的流，确实一无所失。

但它对另外两支**不成立**：撕断与客户端离开都是从 `yield` 处展开的，`stream_delivery` 的尾部**根本不会执行**，终止帧从来没有发出去。此时「上游说过 `stop_reason`」只描述我们知道了什么，完全不描述客户端收到了什么。而当前的门只看 `terminal.stop_reason`，于是这一支被整体豁免。

实测（`/tmp/probe7_tear_after_delta.py`：上游发完全部块 + `message_delta{stop_reason:end_turn, usage}` 后抛 `httpx.ReadError`）：

```
[ OK ] 13:38:56 200 POST /v1/messages 0ms ↓0B ↑11 ↓22 end_turn
propagated: ReadError connection reset by peer
downstream saw message_delta: False
downstream saw message_stop: False
```

三件事同时发生：客户端**既没拿到 `message_delta` 也没拿到 `message_stop`**、异常穿透到框架、日志行报绿色 `[ OK ]` 且没有任何 detail。`accounting.failure` 明明被记下了，却因为门在前面就被跳过，`_ending()` 从未被调用。

严重性判定为 blocker 的依据：这不是「旧代码本来就这样」——R1 那一版（门是 `not terminal.seen`）会把这个场景报成 `fail` + 具名原因；是 S3 的修法把它退回去的。它复现的正是这次改动存在的理由（一个 43KB 之后断掉的流报成安静的成功），修法只有一行，且不牵动任何已裁决的语义。

建议改法：

```python
# 只有「上游自己的流跑完，且跑完之前已经说过怎么结束」才是不需要上报的结局。已知的 reason 只豁免这一支：撕断与客户端离开都跳过了那次 flush，上游说了什么不代表客户端收到了什么。
if not (self.drained and terminal.stop_reason):
    self.trace.status_override, self.trace.detail = self._ending()
```

改完之后三个结局分别是：drained + 有 reason → 不上报（S3 想要的）；drained + 无 reason → `fail` 截断；撕断 → `fail` + 异常原文（无论有没有 reason）；客户端离开 → `gone`（无论有没有 reason）。

配套测试建议加一条：现有的 `test_an_upstream_that_tore_says_so_and_says_what_broke` 在**第一个块之后**就撕断，`stop_reason` 为空，因此恰好绕开了这个门，抓不到本条。把撕断点挪到 `message_delta` 之后再断一次，才是对这个门有鉴别力的样本。

### S1（should，实测）`_tracked_delivery` 仍然没有 `aclose` 它包住的交付生成器

`_tracked_delivery` 用的是裸 `async for chunk in chunks`。关闭它时 GeneratorExit 从 `yield` 处展开、直接掠过循环，`stream_delivery` 没有被关闭——正是同一批工作在下一层刚刚用 `aclosing` 修掉的形状，而且那一层自己的注释把标准写成了「closed by the time `aclose()` returns, not a few ticks later once the collector reaches it」。

实测（`/tmp/probe8_tracked_delivery_close.py`，上游发完第一个块后挂起，记录其 `finally`）：

```
after aclose() returned: UPSTREAM STILL OPEN
after 20 event-loop turns: ['upstream released']
after a 50ms sleep: ['upstream released']
```

即：上游响应最终会被 async-generator finalizer 收掉，但**不是在 `aclose()` 返回时**，而是若干个事件循环回合之后。

对本次改动的分类逻辑**没有影响**（`finish()` 在 `_tracked_delivery` 自己的 `finally` 里同步跑完，早于内层关闭），所以 `gone` 的判定与新测试都不受影响。但它是同一条链路上同一个缺陷的最后一段。

一行修法：`async with aclosing(chunks) as stream: async for chunk in stream: ...`（注意 `drained = True` 要留在 `async with` 内层循环之后、`aclosing` 退出之前或之后皆可，语义不变）。

归属提示：这属于并行会话的 `aclosing` 切片，不必塞进本切片；但既然它落在本次 delta 的文件里、又被新测试覆盖到，建议在那个切片里点名收掉，别让它掉在两个切片中间。

### S2（should，判断）S5 的「无读者故不改」这个理由本身站不住，但结论可以留

你要我直说，我直说：**结论我接受，理由是反的。**

理由写的是「`reply` 的语义要由第一个真实读者来定，盲改无从验证」。问题在于：`context.reply` 不写，第一个读者就**没有东西可读**——`Terminal` 只能从 `_StreamAccounting` 拿到，而它在 `finish()` 之后就消失了，信息是被销毁而不是被推迟。反过来，无条件写入才是保留选择权的那一侧：`Terminal.seen` 就在记录上，第一个读者想只认完整回复，加一个 `if reply.seen` 即可；想认截断，也现成。

也就是说，这两个选项并不对称：一个保留全部选项，一个替未来的读者做掉了决定。而这次改动对**日志**那一侧的核心论证恰恰是「观测到的事实不该被没观测到的事实拖着一起丢掉」——同一段代码里，两个字段用了相反的原则。

那么为什么我仍然接受「先不改」？因为真正成立的理由是另一个：**保守，维持既有契约**。`RequestContext.reply` 现在的注释写着「`None` 表示没有到达任何 reply」，无条件写入会在没有任何读者、也没有任何测试的情况下改掉这句话的含义。在 STR-04 与 History 接线一起裁决时改，成本同样是一行。这个理由成立，而且诚实。

建议：把就地注释与 `implementation.md` 那条登记的措辞换成这个理由，并写明「代价是第一个读者必须自己补上这次写入，因为现在这条路径不保留记录」。照现在的写法，接手的人会以为选择权还在他手上。

顺带一提，`docs/agents/anthropic-responses-bridge/acceptance.md` 的 STR-04 明文要求 truncation 路径产生 **failed History**——所以「第一个真实读者」不是假想的，它已经被冻结判据点名了，而 History 要写的正是这条被丢掉的记录。

### N1（nit）源码注释与 living doc 都指向 `docs/tmp/` 里的报告

`pipeline_app.py` 的 `reply` 注释写「see `docs/tmp/260820-truncated-stream-reporting.md`」，`implementation.md` 那条登记里也有同一个指针。项目规则要求「及时把结论蒸馏进 live docs，不要让 `docs/tmp/` 成为唯一真相源」。`implementation.md` 本身已经承载了实质内容，所以这只是指针方向问题：源码注释更应该指向 `implementation.md` 的结构怪味登记（那是会被维护的），而不是一个 tmp 报告。

### N2（nit）进程关停时被取消的在途流会被记成 `[GONE]`

优雅关停会取消在途请求 → CancelledError → `gone`。但 `[GONE]` 在 `logging.py` 里的定义是「A request nobody was left to receive」——关停时客户端还在，走掉的是我们。detail 那句 `delivery stopped before upstream finished` 中性、仍然成立，只有 `[GONE]` 的语义略偏。不值得为它加第四档；若在意，可在 `logging.py` 那条注释里补半句「也包括本进程主动停止交付」。

### N3（nit）`context.reply` 的门现在多出第三种分叉

改成按 `stop_reason` 判定之后，出现了这样一种请求：报告完全干净（`ok`、有真实 reason 与 usage、无 detail），但因为 `seen` 为假，`context.reply` 仍然是 `None`。这不是新缺陷，是 S2 那条不一致在新门下的新表现形态，建议一并写进那条登记，免得将来被当成两个独立问题各查一遍。

## 2. 逐条回答你的四个复核点

### 2.1 `except Exception` 的边界

**边界是干净的，我在本环境上实测了它依赖的每一条前提。**

```
python 3.14.2  anyio 4.14.2  starlette 0.52.1
CancelledError <: Exception?      False
GeneratorExit  <: Exception?      False
ExceptionGroup <: Exception?      True    | BaseExceptionGroup <: Exception? False
anyio cancelled exc class:        <class 'asyncio.exceptions.CancelledError'>
```

所以你担心的那点不成立：anyio 在 asyncio backend 上的 cancellation 就是 `asyncio.CancelledError`，是 BaseException，`except Exception` 抓不到，落进 `gone` —— 这正是设计意图。anyio 4 的 `BaseExceptionGroup` 只在 task group 的 `__aexit__` 处构造，那在生成器**之外**，不会以 group 的形态穿过 `_tracked_delivery`；即便穿过，全 Exception 成员的 `ExceptionGroup` 会被抓成 `fail`、含 CancelledError 的 `BaseExceptionGroup` 落进 `gone`，两种归类都说得通。

到达 `finish()` 的路径我重新完整枚举，**共四条，没有第五条**：

| 路径 | `drained` | `failure` | 结局 | 归类是否正确 |
|---|---|---|---|---|
| `async for` 正常耗尽 | True | None | `fail` 截断 | ✓ |
| 生成器被 `aclose()`（GeneratorExit） | False | None | `gone` | ✓ |
| 任务被取消（CancelledError，含 Starlette 断连处理） | False | None | `gone` | ✓（关停场景见 N2） |
| `stream_delivery` 抛异常 | False | 已记录 | `fail` + 异常原文 | ✓，但被 B1 的门挡住时不生效 |
| `_AccountedStreamingResponse.__call__` 的 `finally`（body 一次都没被迭代） | False | None | `gone` | ✓，这是第四条，归类正确 |

顺序保证也成立：异常先被 `except Exception` 记进 `failure` 再 `raise`，生成器自己的 `finally` 随即调用 `finish()`，都发生在 Starlette 看到这个异常之前；`_AccountedStreamingResponse` 那次 `finish()` 被 `done` 挡住，不会覆盖。

另外确认 `stream.py` 新 `finally` 不会把上游错误转写成取消：`primary = sys.exception()` 保留上游异常并原样 `raise`，只有 primary 为空时才把 deferred cancellation 抛出去。所以撕断不会被误记成 `gone`。

**结论：这一条你做对了，`Exception` 而非 `BaseException` 是正确选择，注释里的理由也准确。** 唯一的问题不在边界，在门（B1）。

### 2.2 `status_for` 由布尔改单值

**没有漏改。** 全仓 `status_for` 生产调用点只有 `pipeline_app.py:132` 一处；`rg "failed="` 在 `src/` 与 `tests/` 零命中；`tests/unit/test_request_log.py` 已同步（含新增的三档断言）。`_Trace.failed` 也已完全替换为 `status_override`，无残留。

改成单值这个决定我赞成，理由与你写的一致（这三个是互斥的结局，不是三个可以同时为真的标志）。

关于 `override="ok"` 会不会被误用：**今天不会，也不建议为此收窄类型。** 唯一的生产者是 `_ending()`，它只返回 `fail`／`gone`。把类型收成 `Literal["fail", "gone"]` 会让下一个合法用法（比如某条路径确实知道 200 之外的成功）反而要先改类型，收益为负。`test_a_streaming_outcome_outranks_the_status_code_it_was_stuck_with` 里那条 `status_for(500, override="ok") == "ok"` 钉的是「override 优先」这条规则本身，不是在鼓励谁去覆盖成功——注释也这么写了，可以留。

### 2.3 `not terminal.stop_reason` 的假阴性

主结论是 B1。另外三种我逐一验过，**都不构成额外假阴性**：

- 上游发 `"stop_reason": null` → `_read_terminal` 的 `isinstance(reason, str)` 不成立，字段留空 → 按未知处理。✓
- 上游发 `"stop_reason": ""` → 赋值为空字符串 → 空串为假 → 按未知处理。✓
- 上游发一个不认识的值（比如 `"garbage"`）→ 按已知处理，并原样转发下游。这是对的：那确实是上游说的话，日志与下游都不该替它改写。✓
- Responses 腿：`_read_terminal` 在 `response.completed` / `response.incomplete` 两支里同时置 `seen` 并赋非空 `stop_reason`，所以在那条腿上新门与旧门**完全等价**，S3 的改动只作用于 Anthropic 腿。你的测试 docstring 已经说明了这一点，属实。✓

### 2.4 S5 的理由

见 S2。一句话：**结论留，理由换**。

## 3. 已核对无误、不再展开的处置

- **S1（异常记录 + `_ending()` 三分支）**：机制正确，`failure` 记录点与再抛顺序无误；异常原文进 detail 的做法我赞成（那确实是唯一留存的记录）。唯一的问题是它被 B1 的门挡在外面。
- **N1（删掉「client was handed a stop_reason」）**：已删，剩下的表述在三支下都成立。
- **N2（`tools(...)` → `called(...)`）**：改到位，docstring 记录了旧拼法与它撞车的那个含义，正是这个仓库注释风格该有的样子。
- **N3（唯一字节差异）**：注释准确。
- **N4（引用范围）**：改为分别引用下游 SSE envelope 合同与两条上游腿的条款，准确。
- **N5（拆测试）**：拆得干净。`_truncated_delivery` 共享 fixture、两个测试各自持有一半断言、待反转的那个在 docstring 里用粗体写明「meant to be reversed, not preserved」，并补上了 legacy 参考实现的指针。这条处置比我建议的更完整。
- **S4（`implementation.md` 结构怪味登记）**：内容属实，我逐句核对过——legacy 分支确在 `responses_anthropic_stream.py:347`，「回归而非未开工」的定性成立。
- **N6（测试留在 `tests/http/`）**：docstring 已写明为何不搬（需要 `make_client` 与 `_chain_of`，复制一份更差），我接受。
- **你新发现的第 4 次变异（`[....]` 静默回落）**：这条抓得好，`_request_prefixes` 是必要的补充。`_add_status_prefix` 对未知 status 回落 `[....]` 而不报错，只断言 status 字符串确实抓不到「新档位没接进渲染表」。这是我在 R1 提 S2 时没有想到的落地陷阱。

## 4. 建议的处理顺序

1. **B1** —— 一行，必须在这批落地前改，并把撕断测试的断点挪到 `message_delta` 之后。
2. **S2** —— 改注释与登记的措辞，不改行为。
3. **S1** —— 交给 `aclosing` 切片收口，别掉在两个切片中间。
4. N1～N3 随手。

---

附：本轮一次性探针 `/tmp/probe7_tear_after_delta.py`、`/tmp/probe8_tracked_delivery_close.py`（均在仓库之外）。
