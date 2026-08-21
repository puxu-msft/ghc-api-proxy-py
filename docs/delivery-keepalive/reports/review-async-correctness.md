# `a374f39` asyncio 控制流与清理语义评审

## 结论

**可以合入。** 在 commit `a374f39`、Python 3.14.2、当前隔离 worktree 下，我没有构造出会漏发保活、无限快速 `yield None`、吞掉业务异常或 `CancelledError`、产生 `coroutine ignored GeneratorExit`／asyncio stderr 噪音、或只接在旧链路上的 blocker／major 缺陷。

发现 2 项 non-blocking minor：其一，`last_write.at` 实际记录的是把 chunk 交给 `StreamingResponse` 之前的时刻，而不是 `await send(...)` 完成的时刻；慢下游下会让下一枚 ping 提前，不会让它迟到。其二，现有噪音回归测试只覆盖正常耗尽，没有覆盖本提交新加外层生成器的提前 `aclose()`、取消和内层异常路径；本次独立探针覆盖后均通过，但建议后续把这些路径固化为测试。

证据强度：上述合入判断“强到足以据此行动”。依据是源码控制流穷举、候选与父提交的同构对照探针、生产接线运行探针，以及目标测试；它不声称证明任意 event-loop starvation、任意第三方 ASGI server 或非法并发消费 async generator 的行为。

## 评审锚点

- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`
- 候选：`a374f3950bdd61552bbbb953d42dbecfb78f32a2`
- 对照：`a374f39^`，其中已包含 `7a51902c58551bc7e81a72ac4ee183047728c908`
- 源码加载确认：

```text
$ uv run python -c "import app.pipeline.delivery.stream as m; print(m.__file__)"
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/pipeline/delivery/stream.py
```

## Findings

### F-1：打戳早于实际 ASGI send；慢下游时 ping 会提前

- 严重度：**minor，non-blocking**
- 把握程度：**高；强到足以作为后续修正依据**
- 位置：`src/app/pipeline/delivery/stream.py:122-127`，尤其是 `last_write.at = loop.time()` 位于 `yield chunk` 之前。
- 生产侧事实：当前 Starlette `StreamingResponse.stream_response` 先从 body iterator 取得 chunk，再执行 `await send({"type": "http.response.body", ...})`。因此这个打戳点严格早于向 ASGI server 交付 body，不能精确称为“客户端最后收到字节的时刻”。

可复核命令：

```text
$ uv run python -c 'import inspect; from starlette.responses import StreamingResponse; print(inspect.getsource(StreamingResponse.stream_response))'
```

关键顺序为：

```python
async for chunk in self.body_iterator:
    await send({"type": "http.response.body", "body": chunk, "more_body": True})
```

构造 `/tmp/probe_stamp_order.py` 模拟 `StreamingResponse` 在取得最后一个内容 frame 后于 `await send(...)` 停留 110ms，而 interval 为 50ms，再请求下一 chunk：

```text
$ uv run python /tmp/probe_stamp_order.py
{'next_is_ping': True, 'anext_elapsed_seconds': 9.720103116706014e-05}
```

这证明下一枚 ping 几乎立即返回，而不是从模拟 send 完成后再等一个 interval。影响方向只是**提前发送**：它不会产生超过 interval 的静默窗口，也不会形成忙等，因为这枚 ping 击发时仍会把 `ping_deadline` 前推。若要让命名与实现完全一致，可在后续 slice 中把打戳放到 `yield chunk` 恢复之后、下一次拉取 inner 之前；在当前生产 `StreamingResponse` 中，这一恢复点位于上一轮 `await send(...)` 之后。另一种诚实做法是把该字段与文档改称“last handoff”，但那会偏离已冻结 spec 的“last write”措辞。

### F-2：现有 asyncio 噪音测试不足以覆盖新增外层生成器

- 严重度：**minor，测试缺口，non-blocking**
- 把握程度：**高；代码位置与测试路径可直接核对**
- 位置：`tests/unit/test_stream_delivery.py:280-293`。

`test_a_keep_alive_wait_leaves_no_asyncio_noise` 只通过 `collect(...)` 正常耗尽流，再检查 loop exception handler。它确实能回归 `7a51902` 修掉的“正常超时等待后，`StopAsyncIteration` 被 stale shield observer 报到 stderr”路径；但它没有对候选新增的 `stream_delivery → _deliver` 外层执行以下三条路径：

1. 外层停在 outward `yield` 时由调用方 `aclose()`。
2. 外层正在等待 inner 时，消费任务被取消。
3. inner 抛出非 `StopAsyncIteration` 异常。

本次 `/tmp/review_delivery_keepalive_probe.py` 独立构造得到：

```text
$ PYTHONASYNCIODEBUG=1 uv run python /tmp/review_delivery_keepalive_probe.py
cancel_exception = CancelledError
inner_exception = ["Boom", "sentinel"]
noise = []
```

候选没有吞异常或取消，也没有出现 `coroutine ignored GeneratorExit`／loop exception handler 噪音。动态加载 `a374f39^:src/app/pipeline/delivery/stream.py` 的对照构造得到相同的 `CancelledError` 传播结果，因此外层包装没有改变该语义。建议后续把这三条构造收进 `tests/unit/test_stream_delivery.py`；本次有独立运行证据且实现没有失败，所以测试缺口不阻塞合入。

## 1. 忙等风险穷举

相关位置为 `src/app/pipeline/delivery/stream.py:58-88` 与 `:157-171`。决定 timeout 的只有两个 deadline：有效 ping deadline 与 response headers deadline。对配置和状态的穷举如下。

| `interval` | synthesis deadline | `started` | 到期后的状态变化 | 是否能连续得到不变的过期 deadline |
|---|---|---|---|---|
| `<= 0` | disabled | 任意 | `pending_deadlines` 为空，等待 upstream task | 否 |
| `<= 0` | enabled | false | 首次到期产生 `None`；`_deliver` 同步执行 `response_started.set()` 并 yield `message_start` | 否，下一次循环移除 synthesis deadline |
| `> 0` | disabled | false | ping 到期先执行 `ping_deadline = now + interval`，随后 `None` 被 `_deliver` 吞掉 | 否，调用方不写字节也不影响 raw ping deadline 已前推 |
| `> 0` | enabled，ping 先到 | false | 每次 ping 到期均先前推 ping deadline；到 synthesis 时设置 `response_started` | 否 |
| `> 0` | enabled，synthesis 先到或同时到 | false | synthesis 同步置位；若 ping 同时到，ping deadline 也先前推 | 否 |
| `> 0` | 任意 | true | ping 到期先前推 deadline，`_deliver` yield `PING_FRAME`，外层打戳 | 否 |

`timeout == 0` 可以短暂发生，但没有“状态不变后再次 timeout 仍为 0”的生产路径：若 raw ping 到期，`src/app/pipeline/delivery/stream.py:86-87` 先把它前推；若 synthesis deadline 到期，`src/app/pipeline/delivery/stream.py:158-168` 在下一次回到 `_events_with_ping` 前置位 `response_started`；若 upstream task 同时完成，`:83-85` 优先交付真实事件，下一 pull 至多再以 0 timeout 击发一次已到期 ping，然后同样前推 deadline。

短 interval 探针的代表结果：

```text
direct_ping_only: 115ms 内 5 次 None，时间约为 21.7、42.6、63.2、90.2、111.9ms
ping_before_synthesis: message_start 约 56.9ms；ping 约 77.6、98.3、118.9ms
synthesis_before_ping: message_start 约 21.2ms；ping 约 72.2、123.2ms
ping_disabled: 只有约 21.0ms 的 message_start
both_disabled: 0 个输出
```

证据强度：**高；强到足以排除本实现由 deadline 状态机导致的无限 `yield None`**。它不排除 event loop 被其他任务长期阻塞造成的迟发，也不把一个自身无限同步地产生 upstream 事件的非法／退化源归为 ping busy loop。

## 2. 多包一层生成器后的清理与异常语义

控制流位于 `src/app/pipeline/delivery/stream.py:111-127`。外层只在一个地方 await inner，并在 `finally` 调用 `inner.aclose()`。

- **正常 inner 异常**：`async for` 不捕获；outer `finally` 中对已经关闭的 inner 调用 `aclose()` 为 no-op；原异常原样传播。探针中的 `Boom("sentinel")` 原样到达调用方。
- **取消**：消费 task 在 outer 等待 inner 时被 `cancel()`，`CancelledError` 进入 inner 等待链；outer `finally` 随后关闭 inner，最终 `CancelledError` 原样传播。
- **调用方提前 `aclose()`**：outer 停在 outward `yield` 时收到 `GeneratorExit`，进入 `finally` 并关闭停在对应 inner `yield` 的 `_deliver`；没有代码在 `GeneratorExit` 后继续 yield，因此没有 `async generator ignored GeneratorExit` 的路径。
- **并发消费者**：没有新增合法的并发消费假设。Python async generator 本身拒绝重叠 `anext()`／`aclose()`；生产 `StreamingResponse` 是串行消费，见上面的 Starlette 源码。外层共享 `_LastWrite` 不引入另一个 task，也没有跨 task 读写。

旁注：提前关闭或取消时，本次探针观察到 upstream async generator 的 `finally` **不会立即执行**，因为 `_events_with_ping` 对 pending `anext(events)` task 没有显式 cancel。对 `a374f39^` 运行同一构造结果也为 false，因此这是既存行为，不是本提交新增的清理语义变化；本次带普通结束和迟发 `RuntimeError` 的构造均未产生 loop handler 噪音。证据强度：**高到足以判定“不是本提交回归”**；是否另开修复 pending pull 的 slice，应独立评审，不应让它反向阻塞这个 keep-alive 计时修复。

## 3. 打戳可见性与竞态

`src/app/pipeline/delivery/stream.py:123-125` 在单一消费 task 中执行：inner 的一次 `__anext__()` 返回 chunk，outer 同步赋值 `last_write.at`，随后 outward yield。outer 未被再次拉取时，inner 也不会继续执行；调用方下一次 `anext(outer)` 时，inner 才会继续，因此 inner 下一次在 `src/app/pipeline/delivery/stream.py:63-80` 计算 deadline 前必然已经看见新值。

没有 off-by-one：每个 outward chunk 恰好打一次戳，包含 `message_start`、内容 frame、terminal frame 和 `PING_FRAME`。没有数据竞争：生产路径没有并发拉取 body iterator；即使有人非法重叠调用，async generator 自身会先报 already running，而不是让 `_LastWrite` 并发写入。

唯一偏差就是 F-1：这个值对应“outer handoff 开始”，而非 `await send` 完成；偏差方向使 ping 早，不使其晚。

## 4. `max(ping_deadline, last_write.at + interval)` 边界

- `interval == 0`：`ping_deadline` 为 `None`，`:67-69` 根本不计算 `last_write.at + interval`。synthesis deadline 仍能独立工作；synthesis 置位后若没有 upstream event，等待会变成无 deadline 的阻塞。探针确认禁用 ping 时只出现 synthesis `message_start`，两者都禁用时无输出。
- `interval > 0`：`last_write.at` 初始化为 outer generator 首次运行时的 `loop.time()`，与 `_events_with_ping` 使用同一个 running loop 的 monotonic clock，时钟域正确。它不会受 wall clock 调整影响。
- 下一枚 ping 不会因 `max` 被算法性推迟到“最后一次 outward handoff之后超过一个 interval”。raw `ping_deadline` 只有在 ping 到期时前推为 `now + interval`；同一枚 ping 的 outward handoff 随后立即打戳，因此两者基本同刻。任何其他 outward handoff 都令 `last_write.at + interval` 成为更晚的候选，恰好把截止点推到该 handoff 后一个 interval。F-1 所述慢 send 只会令实际 client write 晚于这个 handoff，因此产生早 ping而非迟 ping。
- event loop 自身调度迟延当然可以让实际执行晚于 deadline；这不是 `max` 的状态机错误，也不是 asyncio timer 能给出的 hard real-time 保证。

## 5. 生产接线

静态调用链已逐段核对：

1. `src/app/cli.py:130-165` 的 systemd inherited listener 与 standalone 两条启动路径都调用 `create_pipeline_app(chain)`。
2. `src/app/server/pipeline_app.py:256-285` 的 `context.stream` 分支调用本模块的 `stream_delivery(...)`。
3. 同一调用点把 `settings=stream_settings(chain)` 传入。
4. `src/app/server/handler.py:361-369` 将 `chain.config.client_delivery.sse_ping_interval` 逐值写入 `StreamSettings.sse_ping_interval`。
5. `src/app/config/schema.py:187-195` 定义该配置为 `int`、默认 15、下界 0。

运行探针：

```text
$ uv run python -c 'from types import SimpleNamespace; from app.config.schema import ProxyConfig; from app.pipeline.delivery.stream import stream_delivery; from app.server import pipeline_app; from app.server.handler import stream_settings; config = ProxyConfig.model_validate({"client_delivery": {"sse_ping_interval": 7}}); settings = stream_settings(SimpleNamespace(config=config)); print({"pipeline_imports_target_stream_delivery": pipeline_app.stream_delivery is stream_delivery, "configured_interval": config.client_delivery.sse_ping_interval, "stream_settings_interval": settings.sse_ping_interval})'
{'pipeline_imports_target_stream_delivery': True, 'configured_interval': 7, 'stream_settings_interval': 7}
```

证据强度：**高；强到足以确认当前 CLI 生产入口不是旧链路孤儿，且配置值 7 无变换流到 `StreamSettings`**。

## 回归与正控证据

```text
$ uv run pytest tests/unit/test_stream_delivery.py -q
21 passed in 12.39s

$ uv run pytest tests/unit/test_config_loading.py -q
19 passed in 0.26s
```

为了确认新 talkative-upstream 回归不是“只会绿”，动态加载 `a374f39^` 与候选运行同一 10×200ms delta 构造：

```text
$ uv run python /tmp/compare_talkative_keepalive.py
{'before_ping_count': 0, 'candidate_ping_count': 2}
```

这个正控证明该构造确实能区分“每次 upstream pull 重建 deadline”的旧机制与候选机制。测试绿支持当前 selector 覆盖的行为，不证明未枚举的 ASGI server；生产接线另由上一节的源码链与运行探针独立确认。

## 最终裁决

- blocker：0
- major：0
- minor：2
- informational／既存非回归观察：1
- verdict：**pass，可以合入 `a374f39`**
