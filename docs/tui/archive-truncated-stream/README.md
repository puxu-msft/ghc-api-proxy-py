# 档案：一行什么都没说的时候，它在说什么

用户贴来一行日志，问「没有任何其他信息，这说明什么」：

```
[ OK ] 09:00:11 H1/H2 200 anthropic-messages/claude-opus-5 385.0s ↑583.5KB ↓43.2KB
```

385 秒、上游回了 43.2KB，然后整行只有协议、状态、模型、耗时、字节。没有词元、没有结束原因、没有推理块。2026-08-20 完成。

行为契约见 `../spec.md`；本文件记录**怎么定下来的**和**踩过什么**。评审原件逐字保留在 `reports/`——它们是快照，其中的路径、行号与提交哈希记录的是当时，可能已经不成立。

## 零、最该记住的一条：缺席读不出来

请求行的每个字段都是「无话可说就整个省略」——这是对的设计，它让一行随实际发生的事生长。代价是**缺席本身不携带任何信息**：

- 「上游没给这项」
- 「这个端点不报这项」
- 「代码把它丢了」

三者渲染出的是同一个东西：什么都没有。上面那一行的真相是第一种，而它看起来和一次安静的成功请求完全一样。

推论有三条，都不是打字错误，而是「让常见情况安静」这个正确设计的背面：

1. **全有或全无的门会连观测到的事实一起丢掉。** 当时 `_StreamAccounting.finish()` 把整个 reply 摘要 gate 在 `terminal.seen` 上。但 `Terminal.tools` 与 `Terminal.thinking` 是每个 block 关闭时 `record()` 进去的，与终止事件无关——它们被一起扔了。门只该挡住它真正不确定的那部分。
2. **默认值会伪装成观测结果。** `Terminal.stop_reason` 默认 `"end_turn"`，于是「上游说了 end_turn」与「上游什么都没说」是同一个值。同一份代码里的 `terminal_from_anthropic` 早就发现了这个坑并显式传 `stop_reason=""`（见其 docstring），但流式路径没跟上。
3. **查表的兜底会让新档位静默消失。** `_add_status_prefix` 对不认识的 status 回落到 `[....]`。所以断言 `status == "gone"` 证明不了读者看到的是 `[GONE]`——必须断言**渲染出来的那个前缀**。这一条是加 `[GONE]` 时才发现的，靠一次变异（删掉字典键）暴露出来。

这条教训已沉淀为记忆条目 `absence-is-not-readable-on-a-log-line`。

## 一、这一行为什么会是绿的

`status_for(status_code, failed=False)` 里的 `failed` **在生产代码里从来没被传过 True**——只有单测调用过那条分支。流式请求的状态码在上游响应头到达时就定死，此后无论流怎么结束都是 200。

所以前缀不是「判断错了」，而是**根本没有渠道**表达响应头之后发生的事。修法是给 trace 一个 `status_override`，让看着交付结束的那段代码有话可说。

## 二、方向相反的第二件事

`stream_delivery` 收尾处不看 `seen`，直接用 `terminal.stop_reason`（默认 `end_turn`）发 `message_delta` + `message_stop`。`synthesized_response_headers_after_sec` 默认 240 秒，385 > 240，`started` 必为真。

**客户端收到的是一个伪造的干净结束**，并把被截断的回答当作完整回答存进会话历史。

于是同一个事实上，两条交付路径撒了两种谎：对操作者是沉默（真话，但写成了没人读得出的缺席），对客户端是编造（假话，但说得斩钉截铁）。

这一条**本次没修**：`docs/agents/anthropic-responses-bridge/spec.md`（FINALIZED）第 298 行明文「没有合法 terminal event 的 EOF 是 truncation，不是成功」，`acceptance.md` STR-04 要求这类路径产生确定的 Anthropic error 与 failed History，并把「在 clean EOF 上调用正常 flush」列为必须变红的缺陷注入点。那是客户端可见的契约变更，需要独立切片。

**而 legacy 链路早就正确实现了它**——`src/app/delivery/responses_anthropic_stream.py` 在 `not frontier.terminal_accepted` 时抛 `incomplete_responses_stream` 并 render SSE error。所以落地 STR-04 是一次**移植**，不是重新设计。这是「守卫被留在了 legacy 链路上」在本仓的第三次击发，而且形态与前两次不同：前两次生产表现是上游 400（吵闹、必然被发现），这次是静默的假成功。

现状标注在三处：`stream.py` 就地的 KNOWN SPEC VIOLATION 注释、`tests/unit/test_stream_delivery.py::test_a_truncated_stream_is_still_flushed_as_a_clean_ending_downstream`（docstring 明写「本测试的目的是被反转、不是被保留」）、以及 `docs/agents/anthropic-responses-bridge/implementation.md` 的结构怪味登记。

## 三、三种结局，不是一种

`finish()` 从 `finally` 里跑，所以**三种完全不同的结局走到同一处，`seen` 都是假**。区分方式必须写在它们各自发生的地方，不能在 `finish()` 里猜：

| 结局 | 怎么识别 | 前缀 | detail |
|---|---|---|---|
| 上游流自己跑完但没发终止事件 | `_tracked_delivery` 的 `async for` 正常结束 → `drained = True` | `[FAIL]` | `upstream stream ended without a terminal event` |
| 上游撕断（`ReadError`、reset、converter 抛异常） | `except Exception` 捕获 → `failure = error` | `[FAIL]` | `stream failed before a terminal event: <原文>` |
| 客户端走人（Esc、网络断） | GeneratorExit／CancelledError 从 `yield` 处展开，两个标记都没置上 | `[GONE]` | `delivery stopped before upstream finished` |

`except Exception` 而非 `BaseException` 是刻意的：GeneratorExit 与 CancelledError 正是「这一侧停止交付」，捕获它们会把三种结局重新揉成一种。评审在 py3.14.2 / anyio 4.14.2 上实测确认两者均非 `Exception`，且 anyio 的 cancelled exc class 就是 `asyncio.CancelledError`。

撕断那一支把**异常原文**放进 detail，因为这条路径上没有别的地方记下它：异常从交付生成器展开、穿过框架出去，请求自己那一行是唯一幸存的记录。

## 四、报告截断的门需要两个条件

```python
delivered_whole = self.drained and self.failure is None
if not (delivered_whole and terminal.stop_reason):
```

两个条件缺一不可，这是评审第二轮抓到的 blocker，也是本次最值得记的一处**过度修正**。

起因是一个真实的问题：Anthropic 上游把结局拆成两半，`message_delta` 带 stop reason 与 usage，`message_stop` 只负责关闭。切在两者之间时，客户端该拿的都拿到了，而按 `seen` 判会渲染出自相矛盾的一行：

```
end_turn: upstream stream ended without a terminal event
```

于是门改成只看 `terminal.stop_reason`。**但「上游给了 reason」不等于「客户端拿到了 terminal frames」**：`stream_delivery` 的收尾 flush 写在它的事件循环**之后**，撕断与断开都从 `yield` 展开、尾部根本不跑。所以「上游在 `message_delta` 之后撕断」这一种又变回了绿色 `[ OK ] ... end_turn` 且无 detail——`failure` 明明记着却从没被读。要消除的静默，被恢复在了一条更窄的路径上。

`delivered_whole` 里的 `failure is None` 是评审建议之外多加的，用意是让这道门与 `_ending()` 的判定顺序一致。评审实测确认该组合**当前不可达**（生成器 `finally` 的异常在循环内就浮出来，那时 `drained` 还没置上），并要求把理由写成「保持同序」而不是「覆盖某个场景」，否则下一个人会去为它造状态、造不出来、进而怀疑代码错了。注释已按此改写。

## 五、已否定的方案与否定的理由

- **取消一律染红。** 三种未完成结局统一 `[FAIL]`，靠行尾 detail 区分。改动最小，但这是一个面向交互式客户端的代理——按 Esc 是日常动作，日志会变成一片红，「红色」这个信号随之贬值，真正的上游故障被淹掉。用户 2026-08-20 裁决否定。
- **取消回到 `[ OK ]`，只留 detail。** 只有上游截断与上游撕断报 FAIL。否定理由是它正是本次要消除的那种误导：一个没拿到完整回答的请求标成 OK，与真的答完了无从区分。而且 detail 目前红色渲染，OK 行带红字读着别扭。
- **采用第三档 `[GONE]`（黄）。** 用户裁决采纳。`STATUS_PREFIXES` 里已有 `[RETRY]` 这个额外档位的先例，所以是既有机制而不是新机制；宽度 6 与主档位一致。
- **`tools(...)` 作为无结束原因时的工具字段名。** 第一版拼写，被评审否定：`tools` 也是请求侧**工具声明**的名字，读日志的人无从分辨「这次请求声明了 Bash 和 Read」与「这一轮调用了它们」，两者是交换的两端。改为 `called(...)`。也不能借用 `tool_use` / `function_call`，那两个词都断言「回复以工具调用**收尾**」，而这条行上根本没人说过回复结束了。
- **无条件把截断的 `Terminal` 写进 `context.reply`。** 保持 gate 在 `seen` 上。第一版给的理由是「今天没有读者，语义留给第一个真实读者定」——评审指出这个理由是**反的**：`Terminal.seen` 就在记录上，无条件写入才是保留选择权的那一侧，不写是销毁信息。真正成立的理由是保守：`reply is not None ⇒ 回复已完成` 是 hooks 与 History 的现有契约，放宽它是契约变更；而 STR-04 已点名需要 failed History，第一个读者并不假想。故与 STR-04 同一切片一并裁决，已登记在 bridge 的结构怪味表。
- **在 ASGI 边界用「`send` 抛 OSError」模拟客户端断开。** 仓库里 `tests/smoke/test_anthropic_responses_stream_route.py` 有这个模式，但直接 `await app(scope, receive, send)` 会挂死，连 `asyncio.timeout` 都不生效（怀疑与没跑 lifespan 有关）。放弃，改为直接驱动 `_tracked_delivery`。

## 六、两次假绿

两次都被守卫断言挡住，都值得复述，因为它们的形态会复发：

1. **`TestClient` 抓不到中途断开。** 断开测试的第一版流式读一个 chunk 后退出 `with` 块——`TestClient` 会把响应体读完，所以上游其实跑完了、日志是 `end_turn`，根本没触发断开。测试全绿而证明不了任何东西。是靠一条 `assert "end_turn" not in line` 的守卫才发现的。
2. **`git diff --cached` 看不出被拼坏的文件。** 收尾提交时按 hunk 过滤补丁，`-U0` 没有上下文可锚定、丢弃前面的 hunk 后偏移全错，把一个函数插进了另一个函数的 docstring 里。是**把 index 物化成独立的树跑测试**才发现的。

变异验证共五次，每次都逐字节还原并比对：`finish()` 的分支置死、`failure` 不记录、门改回 `seen`、删掉 `STATUS_PREFIXES` 的 `gone` 键、门改回只看 `stop_reason`。每一次都变红，且捕获的输出与评审描述的失效形态逐字同形。

## 七、相关位置

- 实现在 `src/app/observability/request_log.py`（`status_for` / `format_pending_tools` / `LogStatus`）、`src/app/observability/logging.py`（`STATUS_PREFIXES` / `PREFIX_COLOURS`）、`src/app/server/pipeline_app.py`（`_Trace.status_override` / `_StreamAccounting` / `_tracked_delivery`）、`src/app/pipeline/delivery/assembler.py`（`Terminal` 默认值）、`src/app/pipeline/delivery/stream.py`（合成 `end_turn` 的那一处）。
- 主仓那次改动的提交标题是 `fix: say when a stream ended without upstream's terminal event`。**这里不记哈希**：写下时记的 `15abef4` 在一小时内就因并行会话重写历史而不再是 `main` 的祖先。在这棵被反复重写的树上，提交标题比哈希耐用。
- 遗留的 STR-04 缺口登记在 `docs/agents/anthropic-responses-bridge/implementation.md` 的结构怪味表。
