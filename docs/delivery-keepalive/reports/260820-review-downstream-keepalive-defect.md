# 《下游保活缺陷》独立证伪评审

## 评审结论

**中心机制主张成立，把握高。** `src/app/pipeline/delivery/stream.py::_events_with_ping` 确实在每次开始拉取下一个上游 SSE event 时重建 `ping_deadline`。只要上游 event 的到达间隔持续短于 ping interval，当前拉取任务就会先完成，控制流直接把 event 交给 assembler 并回到外层重建 deadline；若这些 event 只是尚未闭合 block 的 delta，`stream_delivery` 不会产生下游字节。因此，首块已经交付之后，单个未闭合 block 可以造成不受 `sse_ping_interval` 约束的下游静默。

**整份事故诊断只能判为部分成立，把握高。** 机制和可复现实验成立，但第 3、5 节把「该机制能产生这种现象」写成了「事故中上游确实持续发 delta，而且 253.81s 静默确由我方制造」。现有取证明确没有该请求的服务端记录，客户端 transcript 也看不见 block 内 delta、字节时序或隐式重试，因而尚不足以完成事故因果归因。

评审对象取自工作树快照 `HEAD 319388052068bd3d6c1cc133f0fc4ac24b000ffb`。所读核心源码与单测相对 `HEAD` 无已跟踪 diff；目标报告本身为未跟踪文件。指定的 `my-skills:as-reviewer` 在当前 harness 中未注册，调用返回 `Unknown skill`，本报告按用户给出的证伪标准直接执行。

## 发现

### F1．事故因果归因越过了现有证据

- 严重度：Major
- 把握程度：高，足以要求修正文档

目标报告 `docs/tmp/260820-downstream-keepalive-defect.md:64` 写道「之后进入一个长块，上游持续在发 delta，我们持续不发任何字节」，`docs/tmp/260820-downstream-keepalive-defect.md:88` 又把「253.81s 的下游静默都是我方制造的」和「任何一个候选都会被不再静默消掉」当成确定事实。

这两句没有被现有取证支撑。`docs/tmp/260820-client-timeout-forensics.md:102` 明确说明 transcript 只在完整 content block 落盘，253.81s 只是从最后一个已落盘 block 算出的静默上界，无法看到其后的真实字节；同文件 `:104` 明确说明无法判断 256.97s 是否包含不落盘的自动重试。`docs/tmp/260820-server-timeout-forensics.md:102` 更直接写明没有该请求的任何服务端记录，不能断言同一次请求的因果链。

尤其是目标报告第 5 节自己列出的第二个候选「链路上还有一个没测到的计时器」并不必然由 body 字节重置；若它是总时限，「任何一个候选都会被不再静默消掉」在逻辑上就是假的。第一个候选「发生了未落盘重试」也意味着 253.81s 不能直接解释成同一条代理下游连接的连续静默。

可复核命令如下。

```bash
rg --line-number '上游持续在发 delta|253\.81s 的下游静默|真实的最后一个字节|自动重试|不能断言这就是同一次请求' docs/tmp/260820-downstream-keepalive-defect.md docs/tmp/260820-client-timeout-forensics.md docs/tmp/260820-server-timeout-forensics.md
```

建议把第 3 节改为「事故现象与机制相容，但没有证据证明事故窗口内上游持续发 delta」，把第 5 节改为「该缺陷值得独立修复，但能否解释或消除本次 256.97s 失败尚未证实」。

### F2．探针说明把「观察窗口内无新增内容」写成了「下游产出为 0 字节」

- 严重度：Minor
- 把握程度：高，属于可直接修正的表述错误

目标报告 `:26` 和探针模块注释说两组在 3 秒里都交付 0 下游字节，但真实输出均为 `other_chunks=6`。这些是为了令 `started=True` 而在计时开始后立即交付的首个完整 block。正确判据应是「首块交付后的 3 秒观察窗口内没有新增内容字节」，而不是整次运行 0 字节。

这不推翻 ping 表格。独立重跑得到 chatty 为 0 ping，silent 为 2 ping，时间分别为 1.0s、2.0s，与表格完全一致。

可复核命令如下。

```bash
PYTHONPATH=src /home/xp/src/ghc-api-proxy-py/.venv/bin/python /home/xp/.claude/jobs/d18048c0/tmp/ping_probe.py
```

本次输出如下。

```text
[upstream-chatty] over 3.0s: pings=0 other_chunks=6
  [upstream-silent] ping at 1.0s
  [upstream-silent] ping at 2.0s
[upstream-silent] over 3.0s: pings=2 other_chunks=6
```

### F3．既有测试没有覆盖「上游持续活跃但 block 未闭合」；其中一条测试对 ping 是否存在没有分辨力

- 严重度：Moderate
- 把握程度：高，足以据此补一条针对性回归测试

`tests/unit/test_stream_delivery.py:227-231` 只证明完整 block 之后上游静默 1.2s 会发 ping。`:236-240` 证明首块前静默不发 ping。没有测试让上游以小于 interval 的间隔持续发送 delta 并保持 block 未闭合。

`tests/unit/test_stream_delivery.py:197-199` 的 `test_a_keep_alive_carries_no_content` 也不能弥补缺口。它使用 `gap=0.0`，通常不会产生任何 ping；断言 `all(chunk != PING_FRAME or chunk.startswith(b":"))` 在零 ping 时仍然为真，而且对常量 `PING_FRAME = b": ping\n\n"` 本身也恒真。它只检查「如果遇到该常量，它以冒号开头」，不检查活跃上游期间是否实际产生 ping。

可复核命令如下。当前 20 条测试全绿，但该绿灯没有推翻缺陷。

```bash
rg --line-number 'test_a_keep_alive_carries_no_content|test_silence_after_a_block_produces_a_keep_alive|test_silence_before_the_first_block_produces_no_keep_alive|PING_FRAME in chunks|all\(chunk != PING_FRAME' tests/unit/test_stream_delivery.py
PYTHONPATH=src /home/xp/src/ghc-api-proxy-py/.venv/bin/python -m pytest tests/unit/test_stream_delivery.py --quiet
```

本次结果为 `20 passed in 10.36s`。

### F4．第 6 节对 `streaming/keepalive.py` 的接线描述不够准确

- 严重度：Minor
- 把握程度：高，属于旁支结论的措辞修正

`timeouts.stream_idle` 只在旧链路生效这一条成立：`resolve_stream_idle` 的生产调用点是 `src/app/routes/anthropic.py:217`，新链路 `src/app/server/pipeline_app.py` 不调用它。

但「`streaming/keepalive.py` 只接在旧链路」容易让读者误以为其中的 heartbeat 行为至少在旧链路运行。实际是 `session_liveness_stream` 与 `keepalive_stream` 没有任何模块外生产调用者；旧链路的 `app.streaming.sse` 只导入了同文件中的通用清理函数 `finish_stream_cleanup`。更准确的结论是「liveness／keepalive 两个生成器目前根本没有生产接线；该文件的 cleanup helper 仅被旧 SSE 包装层间接使用」。

可复核命令如下。

```bash
rg --line-number --glob '*.py' 'from app\.streaming\.keepalive|import app\.streaming\.keepalive|keepalive_stream\(|session_liveness_stream\(' src/app
rg --line-number --glob '*.py' 'stream_idle|resolve_stream_idle' src/app
```

第一条只会得到 `src/app/streaming/sse.py` 对 `finish_stream_cleanup` 的 import，以及两个生成器自身的定义／内部调用；不会得到生产端对两个生成器的调用。

### F5．第 7 节声称这是 `_events_with_ping` 内「一行位置的改动」，不能实现它自己提出的计时基准

- 严重度：Moderate
- 把握程度：高，足以否定该实现规模判断

目标报告 `:97` 要求按「上次向下游写出字节」重置 deadline，却又说只需在 `_events_with_ping` 中移动一行。该函数的输入是上游 bytes，输出是 `SseEvent | None`；它看不到 assembler 是否闭合 block，也看不到 `stream_delivery` 在 `:128-133`、`:138-150` 实际向下游 yield 了哪些字节。把 `ping_deadline` 从外层循环体移到循环外，最多得到一个不再随上游 event 重置的周期 timer，并不会在真实下游内容写出时重置。

可复核位置如下。

```bash
rg --line-number 'task = asyncio|ping_deadline =|yield None|blocks = assembler\.push|yield chunk|terminal_frames' src/app/pipeline/delivery/stream.py
```

这不否定修复方向，但否定「一行位置改动即可精确实现按下游字节计时」这一工程判断。若只要求静默不超过 interval，独立周期 ping 可能已足够；若合同确实要求以最后一次下游写出为基准，就需要让计时器位于能观察下游 yield 的层级，或加入明确反馈。

## 中心机制逐步复核

`src/app/pipeline/delivery/stream.py:44-45` 每次进入外层循环都创建新的 `anext(events)` task，并设 `ping_deadline = loop.time() + interval`。内层 `asyncio.wait` 有两种与本问题相关的返回路径。

1. task 先完成时，`:65-67` 执行 `yield task.result()` 后立刻 `break`。这条路径不会执行 `:70` 的 `yield None`，随后回到外层并重建 deadline。
2. deadline 先到而 task 未完成时，`:68-70` 才会更新已到期的 ping deadline 并执行 `yield None`。

因此，内层的 `yield None` 虽然在 `if ping_deadline ...` 之后是无条件语句，却不是每轮等待、也不是每个上游 event 都会执行；它只位于「task 尚未完成，某个 pending deadline 已令 wait 超时」的路径。若超时来自更早的 `response_headers_deadline`，即使 ping deadline 未到也会产出 `None`，但 `stream_delivery:108-121` 会先处理 header synthesis；首个真实 block 到达后 `response_started` 已置位，header deadline 不再参与等待，此后 `None` 才对应 ping deadline。

`stream_delivery:108-121` 对 `event is None` 的处理也没有反转结论。deadline 未到且上游 event 已完成时，调用方根本收不到 `None`。收到 `None` 后，首块前要么在 synthesis deadline 到时发 `message_start`，要么继续；只有 `started=True` 才发 `PING_FRAME`。所以「无条件 `yield None` 会不会导致 deadline 未到也持续发 ping」的答案是不会。

可复核命令如下。

```bash
rg --line-number 'task = asyncio|ping_deadline =|if task\.done\(\)|yield task\.result|yield None|if event is None|elif started|yield PING_FRAME|blocks = assembler\.push' src/app/pipeline/delivery/stream.py
```

## Responses 生产路径交叉验证

探针采用 `AnthropicAssembler` 不会偷换中心条件，因为 ping 调度发生在 `assembler.push(event)` 之前，而且生产路径 `src/app/server/pipeline_app.py:262-280` 会按实际 upstream dialect 选择 assembler 后调用同一个 `stream_delivery`。`ResponsesAssembler` 在 `src/app/pipeline/delivery/assembler.py:210-220` 对 `response.output_text.delta`／`response.reasoning_summary_text.delta` 只累积数据，到 `response.output_item.done` 才闭合 block。

我另用合法的 Responses 事件形状独立复跑：先闭合一个 message item 令 `started=True`，再打开 reasoning item；chatty 组每 0.2s 发送 `response.reasoning_summary_text.delta` 而不发送 `response.output_item.done`，silent 组不再发送 event。结果与 Anthropic 探针相同。

```bash
PYTHONPATH=src /home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/260820-responses-ping-probe.py
```

```text
[responses-chatty] over 3.0s: pings=0 other_chunks=6
[responses-silent] ping at 1.0s
[responses-silent] ping at 2.0s
[responses-silent] over 3.0s: pings=2 other_chunks=6
```

该结果强到足以支持「缺陷与 assembler dialect 无关」，但只能支持机制，不支持本次事故中实际上游 delta 的存在。

## 第 6 节其余两条复核

### 上游两个 keepalive 旋钮名不副实

结论成立，把握高。`src/app/server/composition.py:67-80` 把 `tcp_keepalive_interval` 映射为 `httpx.Limits.keepalive_expiry`，其含义是连接池内 idle connection 的保留期限；全仓没有 `SO_KEEPALIVE`。同处只用 `http2_ping_interval > 0` 决定是否启用 HTTP／2，没有按该间隔发送 PING 的实现。现有测试 `tests/unit/test_http_client_build.py:15-35` 也直接把这两个映射分别固定为 expiry 和布尔值。

```bash
rg --line-number --glob '*.py' 'tcp_keepalive_interval|http2_ping_interval|keepalive_expiry|SO_KEEPALIVE' src tests
```

### `client_delivery.hedge` 未实现

结论成立，把握高。生产源码对 `hedge` 的唯一命中是 `src/app/config/schema.py:195` 的字段定义，没有消费者。现有候选权威文档 `.dev/human-controlled-docs-candidates/config-schema-gap.md:80` 也明确记录为未实现能力。

```bash
rg --line-number --glob '*.py' 'hedge' src tests
```

## 最终裁决

- 中心机制：**成立**。
- Anthropic 探针数字：**成立**，表格的 ping 数与时间准确；「整次 3 秒下游 0 字节」措辞不准确。
- Responses 生产形状：**同样复现**，没有因 assembler 差异而失效。
- 既有测试：**未覆盖并未推翻**，且有一条存在性上无分辨力的断言。
- 本次 256.97s 事故的因果归因：**未成立**，目前只能说现象相容，不能说上游持续 delta 或 253.81s 静默确定由代理制造。
- 第 6 节：transport 与 hedge 两条成立；`stream_idle` 旧链路结论成立；`keepalive.py` 应改写为「两个 liveness 生成器完全未接线，cleanup helper 仅在旧 SSE 层使用」。
- 整份报告：**部分成立，需要修正后再作为事故根因报告使用**。
