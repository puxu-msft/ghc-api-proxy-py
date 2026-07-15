# 流式韧性

## 概述

上游参考项目（`copilot-api-js`）在长期与 Claude Code 等客户端联调中，摸索出一整套应对**上游长静默**与**上游 mid-stream 中断**的流式健壮性机制。本项目**采纳其解决的真实问题**，但对每一项都重新核算性能代价，严格区分默认路径与 opt-in 路径。

核心立场（呼应 [DESIGN.md](DESIGN.md) 的性能设计原则 P6）：**默认路径永远是零缓冲直通流**。本文档描述的三类机制——延迟提交窗口、keepalive 心跳、缓冲重试——分别解决不同的问题，取舍程度也不同，务必分开理解，不要混为一谈。

| 机制 | 解决的问题 | 本项目取舍 |
|------|-----------|-----------|
| 延迟提交窗口（delayed-commit） | 客户端需要真实 HTTP 状态码来做原生重试，但上游可能长时间静默才决定成败 | `[上游稳定][采纳]` |
| Keepalive 心跳 | 客户端有多层 idle watchdog，纯字节保活压不住"真实内容"型 watchdog | `[采纳]`（仅 `empty_text` + `ping`，拒绝 `enveloped_ping`） |
| 缓冲重试（buffered retry） | 上游 mid-stream RST 导致半截响应，客户端无法自然重试一个已经 200 的流 | `[上游实验][采纳，默认关，见 P6]` |

## 背景：为什么需要这些机制

Claude Code（及类似客户端）对一次 SSE 请求有**双层空闲 watchdog**，理解这一点是本篇几乎所有设计的前提：

1. **byte-idle watchdog（约 60 秒）**——只要连接上有任意字节流过（包括裸 `event: ping`），计时器就重置。
2. **no-real-content watchdog（约 300 秒）**——只有真正的 `content_block_delta` 之类的内容事件才重置；`event: ping` 之类的保活帧**不计入**，因为客户端在字节层面把它识别为「非内容 chunk」。

因此：短暂静默（几秒到几十秒）用裸 ping 就够；但当上游进入长时间「有推理无输出」的状态（如 Opus 系模型响应前的 thinking 静默，实测可达数十秒甚至更久）时，纯 ping 撑不过 300 秒的 no-real-content 上限，客户端会主动断开重连，打断一次本可能成功的生成。

同时，客户端有自己的原生重试/退避逻辑，但**只在收到真实 HTTP 状态码时才生效**——一旦代理提前 commit 了 200 状态码并开始推流，客户端就只能依赖 SSE 内部的 `error` 事件类协议来处理失败，丧失了"整个请求从未开始"语义下的原生重试能力。这催生了延迟提交窗口的设计。

## 1. 延迟提交窗口（Delayed-Commit）`[上游稳定][采纳]`

### 解决的问题

多数请求的上游要么很快返回（几十毫秒到几秒），要么很快报错（限流、鉴权、模型不存在等）。但 Opus 系模型存在响应前长时间静默的情况——上游既没有报错，也还没有开始吐字符。如果代理一收到客户端请求就立刻 commit HTTP 200 并打开 SSE 流，那么：

- 若上游随后返回错误，代理只能把错误"降级"成一个 SSE `error` 事件塞进已经开始的流里，客户端拿不到原始 HTTP 状态码，无法触发其原生的、经过精心调校的 retry/backoff 策略。
- 反之，如果代理能在打开流之前多等一会儿，让上游有机会先 settle（无论是成功开始输出还是报错），就能把真实状态码转发给客户端。

延迟提交窗口就是这"多等一会儿"的机制。

### 机制

```python
class DelayedCommitResult(NamedTuple):
    committed_early: bool          # True = 窗口内已 settle，可用真实状态码
    upstream_response: httpx.Response | None
    upstream_error: ApiError | None


async def run_with_delayed_commit(
    upstream_call: Awaitable[httpx.Response],
    *,
    commit_after_sec: float,
) -> DelayedCommitResult:
    """在提交 200 SSE 响应之前，最多等待 commit_after_sec 秒让上游 settle。"""
    if commit_after_sec <= 0:
        # 立即提交：不做延迟判断，等价于旧的"收到请求即开流"行为
        response = await upstream_call
        return DelayedCommitResult(True, response, None)

    task = asyncio.ensure_future(upstream_call)
    try:
        response = await asyncio.wait_for(asyncio.shield(task), timeout=commit_after_sec)
        return DelayedCommitResult(True, response, None)
    except asyncio.TimeoutError:
        # 窗口耗尽仍未 settle（如 opus 长 pre-response thinking）——
        # 不取消 task，而是把它交给后续的流式管道继续等待，
        # 此后代理必须先 commit 200，再把 upstream_call 的最终结果
        # 桥接进 SSE 流（含错误降级为 error 帧）。
        return DelayedCommitResult(False, None, None)
```

窗口内两种结局：

- **上游在窗口内返回或报错** → `committed_early=True`，代理转发**真实 HTTP 状态码**（2xx 或错误码），客户端保留其原生 retry/backoff 能力。这是绝大多数请求的路径。
- **窗口耗尽上游仍然静默**（典型：Opus pre-response thinking）→ 代理不再等待，**立即 commit 200** 并开始 keepalive，请求转入"流已提交"状态。此后若上游最终报错，只能通过 SSE `error` 事件降级通知客户端，无法再改口 HTTP 状态码。

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.stream_commit_after_sec` | `20` | 延迟提交窗口秒数，`0`=立即提交（禁用窗口）。Clamp 到小于客户端 byte-idle watchdog（60 秒），避免代理自己的等待反而触发客户端断连 |

### 性能取向

延迟提交窗口本身**不引入额外内存开销**——它只是把"何时打开 HTTP 响应流"这个决策推迟了最多 N 秒，期间上游请求正常进行中（`asyncio.shield` 保护其不被误取消），不缓冲任何响应内容。相比缓冲重试（见下）动辄兆字节级的内存占用，延迟提交窗口的代价仅是**几秒到几十秒的额外首字节延迟**，且只发生在窗口耗尽的少数请求上。

## 2. Keepalive 心跳 `[采纳]`

### 解决的问题

一旦流式响应 200 已提交（无论是立即提交还是延迟提交窗口耗尽后的提交），代理必须持续产出让客户端认为"连接仍然存活"的信号，覆盖两类场景：

- 上游仍在传输中途出现短暂停顿（如 adaptive thinking 阶段性静默）。
- 延迟提交窗口耗尽后开了 200，上游仍在长时间静默中未产出任何真实内容。

如背景一节所述，客户端的两层 watchdog 对"什么算保活"要求不同：byte-idle 层认任意字节，no-real-content 层只认真实内容事件。因此保活帧的形态直接决定了它能撑住哪一层。

### 三种模式

| 模式 | 行为 | 能否压住 300s no-real-content watchdog | 状态 |
|------|------|----------------------------------------|------|
| `empty_text`（默认） | 有已打开的 content block 时，发一个**匹配该 block 类型**的空 delta（`text_delta`/`thinking_delta`/`input_json_delta`，内容为空字符串）；无已打开 block 时，**懒注入**一个合成的 `message_start` + 空 text 锚点块（`content_block_start`）+ 空 `text_delta`，作为可被客户端识别为"内容 chunk"的重置点 | 是 | `[采纳]` |
| `ping` | 发送裸 `event: ping` 帧（Anthropic 协议原生保活事件） | 否（仅能压住 byte-idle 60s 层，是短静默场景的逃生舱） | `[采纳]`（作为轻量备选） |
| `enveloped_ping` | 先合成一个 `message_start` 信封，再发裸 ping | 否（上游自身注释明确"预期会超时"） | `[上游实验][拒绝]`，见 [ROADMAP.md](ROADMAP.md) |

`empty_text` 模式是默认值，也是唯一被证明能压住 300 秒 no-real-content watchdog 的方案——原因是空 delta 在客户端解析层面与真实内容 delta 走的是同一条"重置计时器"代码路径，区别仅在于 payload 内容为空字符串。

```python
def make_keepalive_frame(open_block: OpenBlock | None, mode: KeepaliveMode) -> SseFrame:
    """构造一帧 keepalive；block-aware（empty_text）或固定 ping。"""
    if mode in ("ping", "enveloped_ping"):
        return PING_FRAME

    match open_block:
        case OpenBlock(type="thinking", index=idx):
            return content_block_delta_frame(idx, {"type": "thinking_delta", "thinking": ""})
        case OpenBlock(type="text", index=idx):
            return content_block_delta_frame(idx, {"type": "text_delta", "text": ""})
        case OpenBlock(type="tool_use" | "server_tool_use", index=idx):
            return content_block_delta_frame(idx, {"type": "input_json_delta", "partial_json": ""})
        case _:
            # 尚无已打开的 block（如延迟提交窗口耗尽、上游还未吐出第一个 block）
            # 且尚未注入过锚点：懒注入合成 message_start + 空 text 锚点块
            return synthetic_anchor_sequence()
```

### 合成帧的可观测性约定

延迟提交耗尽后注入的合成 `message_start` 与 keepalive 锚点块是**代理自造的、上游从未发出过**的帧。为避免这些合成物污染对上游行为的观测，必须：

- 在**转发轨**（即客户端实际收到的事件记录，如 `forwarded_sse_events`）中，为合成帧打上 `synthetic` 标记（如 `synthetic="synthetic-message-start"` / `synthetic="keepalive-anchor"`）。
- **上游轨**（即代理从上游收到的原始事件记录）**绝不**包含任何合成物——上游轨必须精确反映上游实际发送了什么，这是诊断"上游到底发生了什么"的唯一可信来源。

这一约定也解释了为什么合成锚点块要占用一个专属的、可预测的块索引（如索引 0），真实内容块统一在其后重新编号（index remap）——保证客户端看到的块索引序列自洽，同时诊断日志能清楚区分"这块是不是我们编的"。

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.stream_keepalive_ping_sec` | `20` | 心跳间隔秒数，`0`=禁用。Clamp 到小于客户端 byte-idle watchdog（60 秒）。心跳与上游解耦——只要客户端方向这么久没写出任何字节就补一帧，覆盖 mid-stream 停顿与延迟提交窗口耗尽后的静默 |
| `anthropic.stream_keepalive_mode` | `empty_text` | `empty_text`（默认，推荐） / `ping`（逃生舱，仅压 60s 层）/ `enveloped_ping`（`[拒绝]`，见下） |

心跳间隔在**流开始时读取一次**（与流空闲超时的 per-model 解析约定一致），进行中的流不受热重载影响；新流按热重载后的值生效。

### 为什么拒绝 `enveloped_ping`

`enveloped_ping` 是上游的实验性分支，其自身代码注释直接写明"预期会超时"（expected to time out）——它只是在裸 ping 前多合成了一个 `message_start` 信封，但保活帧本体仍是不计入 no-real-content watchdog 的裸 ping，因此**无法解决它本该解决的问题**。本项目不实现这个分支，见 [ROADMAP.md](ROADMAP.md) 借鉴但暂缓能力表。

## 3. 缓冲重试（Buffered Retry）`[上游实验][采纳，默认关，见 P6]`

### 解决的问题

上游在处理超大上下文的请求（典型场景：Opus 系模型执行大型 Write/Edit 类工具调用）时，偶发 mid-stream 连接级中止（观测到的具体形态是 HTTP/2 `NGHTTP2_CANCEL`）。这类中止发生在流已经开始向客户端转发部分内容之后——此时客户端已经收到了半截 assistant 消息，既无法安全地当作"整个请求失败"重试（可能已执行了部分 tool_use 副作用的语义前提），也不能假装成功。

缓冲重试的目标：把"上游 mid-stream RST"这类瞬时故障，转换成对客户端**透明**的重试——客户端要么拿到一个完整、正确的响应，要么拿到一个明确的失败，绝不会看到一个断在中间的半截流。

### 机制：all-or-nothing

```python
class BufferedRetryCaps(NamedTuple):
    max_retries: int = 3
    buffer_cap_bytes: int = 16 * 1024 * 1024   # 16MB
    heartbeat_sec: int = 15


async def run_buffered_retry(
    open_stream: Callable[[], AsyncIterator[SseEvent]],
    *,
    caps: BufferedRetryCaps,
) -> AsyncIterator[SseEvent]:
    """
    缓冲整个流式响应，直到确认终止（message_stop / 上游 error 帧）才一次性 flush 给客户端。
    任何 transport-close 或截断都会丢弃已缓冲内容、重新取一次新流，而不是转发半截响应。
    """
    for attempt in range(caps.max_retries + 1):
        buffer: list[SseEvent] = []
        buffered_bytes = 0
        try:
            async for event in open_stream():
                buffer.append(event)
                buffered_bytes += len(event.data)

                if buffered_bytes > caps.buffer_cap_bytes:
                    # 超过内存上限：放弃缓冲策略，退回 live 直写，防止 OOM。
                    # 已缓冲内容 + 后续内容都直接透传，不再等待终止再 flush。
                    async for buffered_event in buffer:
                        yield buffered_event
                    async for live_event in event_source_remainder():
                        yield live_event
                    return

                if event.is_terminal:  # message_stop 或上游 error 帧
                    for buffered_event in buffer:
                        yield buffered_event
                    return

        except (TransportClosed, StreamTruncated):
            # 丢弃本次缓冲，若还有重试预算则取新流重来；
            # 绝不转发半截 buffer。
            if attempt >= caps.max_retries:
                raise BufferedRetryExhausted(attempts=attempt + 1)
            continue
```

关键约束：

- **all-or-nothing**：客户端要么在流终止后一次性收到完整的事件序列，要么完全收不到任何本次尝试的内容（转到下一次重试或最终失败）。绝不转发半截响应。
- **超 cap 退回 live 直写**：`buffer_cap_bytes`（默认 16MB）是防 OOM 的硬上限，一旦触达就放弃 all-or-nothing 语义、退化为普通直通转发——防止一个异常庞大的响应把内存占用无限拉高。
- **`heartbeat_sec`**（默认 15 秒）：缓冲窗口期间仍需要向客户端产出保活信号（否则客户端会认为连接挂起），复用上一节的 keepalive 心跳机制。
- **`max_retries`**（默认 3）：重试预算上限，超过后向客户端报告最终失败（不再无限重试掩盖真实故障）。

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.protect_streaming_generation` | `false` | `false`（默认关）/ `"on"`（对所有流式请求启用）/ `"tool_use_only"`（仅当请求携带 `tools` 时启用） |
| `anthropic.buffered_retry.max_retries` | `3` | 重试次数上限（transport-close/truncation 触发） |
| `anthropic.buffered_retry.buffer_cap_bytes` | `16777216`（16MB） | 内存上限，超过则退回 live 直写 |
| `anthropic.buffered_retry.heartbeat_sec` | `15` | 缓冲窗口期间的保活间隔 |

### 性能声明（对应 DESIGN.md P6）

**这是本篇性能取舍最重的一项，必须显式声明代价：** 缓冲整个流式响应意味着单个请求可能在内存中驻留完整的响应缓冲区——按 `buffer_cap_bytes` 默认上限计算，单请求最坏情况可达 **16MB**。在并发请求较多、且都命中大 Write/Edit 场景的情况下，这个开销会成倍放大，与"默认路径零缓冲直通"的整体设计原则直接冲突。

因此本项目的取舍是：

- **默认关闭**（`protect_streaming_generation = false`）。默认路径始终是本文档第 2 节之前描述的零缓冲直通流，缓冲重试是**严格 opt-in** 的能力，只有明确评估过内存代价、且确实需要应对大上下文 mid-stream RST 问题的部署才应该开启。
- 上游把这个特性标注为 `[上游实验]`（默认关闭，四类端点非对称支持，块级粒度的缓冲重试仍在上游自己的 PoC 阶段未启用）——本项目采纳的是**整响应级**的缓冲重试（上游已相对稳定的粒度），不采纳块级缓冲重试；块级方案复杂度更高且上游自身尚未定论，列入 [ROADMAP.md](ROADMAP.md) `[缓存/延后]`。
- 与延迟提交窗口、keepalive 心跳这类"零额外内存代价"的机制不同，缓冲重试是本文档中唯一需要用户在开启前评估内存预算的机制。

## 4. 上游保活（补充：非应用层 idle）

前三节讨论的都是"代理 → 客户端"方向的保活/韧性；本节补充"代理 → 上游"方向的连接保活，二者互补但解决不同层面的问题。

### TCP keepalive

上游连接（httpx 经 httpcore 建立）应配置 TCP 层 keepalive，防止 NAT/防火墙/负载均衡器的空闲连接回收器在长时间静默期间（如上游 adaptive thinking 静默数十秒）切断底层 TCP 连接：

```python
import socket

transport = httpx.AsyncHTTPTransport(
    # httpx 本身不直接暴露 keepalive 参数，需通过自定义
    # socket_options 传给 httpcore 的连接池
)

# 或在创建连接池时传入 socket 选项
limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
client = httpx.AsyncClient(
    limits=limits,
    transport=httpx.AsyncHTTPTransport(
        socket_options=[
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15),   # 首次探测延迟（秒）
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 15),  # 探测间隔（秒）
        ],
    ),
)
```

上游参考项目默认值为 15 秒（其运行时 undici 默认是 60 秒，对约 30 秒的空闲回收窗口而言太长，第一次探测都来不及发出连接就已被回收）。本项目沿用同一数值经验，作为 Python httpx/httpcore 传输层的默认配置。

### HTTP/2 PING keepalive

TCP keepalive 只解决 L4 层"连接是否还在"，但部分中间层（GHC 边缘节点或中间代理）按**应用层静默时长**判断连接是否空闲，纯 TCP 层探测无法阻止这类连接级回收。因此还需要一个应用层的 h2 PING：

```python
class Http2KeepaliveClient:
    """基于 httpx 的 HTTP/2 客户端，附加周期性 PING 帧防止应用层空闲回收。"""

    def __init__(self, *, ping_interval_sec: float = 15.0):
        self._ping_interval_sec = ping_interval_sec
        self._client = httpx.AsyncClient(http2=True)

    async def _ping_loop(self, connection) -> None:
        if self._ping_interval_sec <= 0:
            return
        while True:
            await asyncio.sleep(self._ping_interval_sec)
            await connection.ping()  # httpx/httpcore 的 h2 连接对象需支持显式 ping
```

httpx 本身不直接暴露"周期性发送 h2 PING"的公共 API，需要在 httpcore 的连接对象层面接入（或依赖 h2 库的连接保活回调）。这是 Python 传输层相对上游 Node/Bun 实现需要额外适配的一处，具体实现细节留给传输层模块（`upstream/client.py`）文档化，此处仅记录设计意图与配置项。

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `upstream.keepalive_expiry` | `30` | httpx 连接池空闲连接过期秒数（已在 [config-system.md](config-system.md) 定义） |
| `timeouts.upstream_keepalive` | `15` | 上游 TCP keepalive 首次探测延迟秒数（0=使用传输层默认，不覆盖） |
| `timeouts.upstream_h2_ping` | `15` | 上游 HTTP/2 PING 心跳间隔秒数（0=禁用） |

## 相关文档

- [设计文档总纲](DESIGN.md)（性能设计原则 P6）
- [流式处理与传输](streaming.md)（基础直通、累积、idle timeout、重复检测）
- [请求执行管道](request-pipeline.md)（重试策略、错误分类）
- [配置系统](config-system.md)（完整配置清单）
- [ROADMAP.md](ROADMAP.md)（`enveloped_ping`、块级缓冲重试的暂缓决策）
