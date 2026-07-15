# 流式处理与传输

## 概述

流式处理系统负责 SSE（Server-Sent Events）响应的接收、逐事件转发、累积和跨格式翻译。设计核心：**流式直通，不缓冲完整响应**（默认零缓冲）。

本文档覆盖基础流式机制（直通、累积、WebSocket、idle timeout、重复检测、跨格式翻译）。应对上游长静默/中断的**流式韧性**机制（延迟提交窗口、keepalive 心跳、缓冲重试）单列一篇，见 [streaming-resilience.md](streaming-resilience.md)。

## SSE 流式处理

所有 API 端点（Anthropic Messages、Chat Completions、Responses）支持 SSE 流式传输。代理收到上游的 SSE 事件后逐事件转发给客户端。

### SSE 响应构建

```python
def create_sse_response(
    stream: AsyncIterator[str],
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    response_headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",      # 禁用 nginx 缓冲
    }
    if headers:
        response_headers.update(headers)

    return StreamingResponse(
        stream,
        status_code=status_code,
        headers=response_headers,
        media_type="text/event-stream",
    )
```

### SSE 事件格式

```python
def format_sse_event(data: str, *, event: str | None = None) -> str:
    lines = []
    if event:
        lines.append(f"event: {event}")
    for line in data.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)
```

## Stream Accumulator

每个 API 格式有对应的 stream accumulator，在流式转发的同时累积完整响应用于 History 记录：

| Accumulator | 格式 | 模块 |
|-------------|------|------|
| `AnthropicStreamAccumulator` | Anthropic Messages | `anthropic/stream_accumulator.py` |
| `OpenAIStreamAccumulator` | Chat Completions | `openai/stream_accumulator.py` |
| `ResponsesStreamAccumulator` | Responses API | `openai/responses_stream_accumulator.py` |

### Accumulator 职责

- 累积 SSE 事件为完整的 response 对象
- 跟踪 token 使用量（input/output/cache）
- 记录 content blocks 和 tool calls
- 为 History 系统提供完整记录
- 检测 stop_reason

### Anthropic Stream Accumulator

```python
class AnthropicStreamAccumulator:
    def __init__(self):
        self.content_blocks: list[dict] = []
        self.usage: Usage | None = None
        self.stop_reason: str | None = None
        self.model: str | None = None
        self._current_block_index: int = -1

    def process_event(self, event_type: str, data: dict) -> None:
        match event_type:
            case "message_start":
                msg = data.get("message", {})
                self.model = msg.get("model")
                self.usage = Usage.from_anthropic(msg.get("usage", {}))

            case "content_block_start":
                block = data.get("content_block", {})
                self.content_blocks.append(block)
                self._current_block_index = data.get("index", len(self.content_blocks) - 1)

            case "content_block_delta":
                delta = data.get("delta", {})
                self._apply_delta(delta)

            case "message_delta":
                delta = data.get("delta", {})
                self.stop_reason = delta.get("stop_reason")
                if "usage" in data:
                    self._update_usage(data["usage"])

    def to_response_data(self) -> ResponseData:
        return ResponseData(
            content=self.content_blocks,
            stop_reason=self.stop_reason,
            usage=self.usage,
            tool_calls=self._extract_tool_calls(),
        )
```

## WebSocket Transport

Responses API 支持 WebSocket 传输，与 HTTP SSE 并行提供。

### 端点

- **HTTP POST** `POST /v1/responses` — 标准 HTTP SSE 流
- **WebSocket** `GET /v1/responses` — WebSocket JSON 帧流（同一路径，通过 HTTP Upgrade 区分）

### 协议

```
客户端 WebSocket 连接
    │
    ▼
客户端发送:
    {
        "type": "response.create",
        "response": {
            "model": "claude-opus-4.6",
            "input": [...],
            "stream": true,
            ...
        }
    }
    │
    ▼
服务端流式返回 JSON 帧:
    {"type": "response.output_item.added", ...}
    {"type": "response.content_part.delta", ...}
    {"type": "response.content_part.done", ...}
    ...
    │
    ▼
终结事件（之一）:
    {"type": "response.completed", ...}
    {"type": "response.failed", ...}
    {"type": "response.incomplete", ...}
    {"type": "error", ...}
    │
    ▼
服务端关闭 WebSocket
```

### 实现架构

WebSocket 处理器（`routes/responses.py`）复用现有 HTTP pipeline 的全部逻辑：

1. 解析 `response.create` 消息 → 提取 `ResponsesPayload`
2. Model 解析、endpoint 检查 → 与 HTTP 路径完全相同
3. Pipeline 执行（token 刷新、网络重试、rate limiting）→ 相同策略
4. SSE 事件 → WebSocket JSON 帧桥接 → 逐事件转发
5. 历史记录、日志 → 与 HTTP 路径相同

```python
@router.websocket("/v1/responses")
async def responses_ws(websocket: WebSocket, ...):
    await websocket.accept()
    try:
        # 接收 response.create 消息
        raw = await websocket.receive_json()
        if raw.get("type") != "response.create":
            await websocket.close(code=4000, reason="Expected response.create")
            return

        payload = raw["response"]

        # 复用 HTTP 处理逻辑
        result = await execute_pipeline(ctx, payload, ...)

        # SSE → WebSocket 桥接
        async for event in result.stream:
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
```

### 一个连接一个请求

每次 WebSocket 连接处理一个 `response.create` 请求。请求完成后服务端关闭连接。

## 流空闲超时

`streaming/idle_timeout.py` 检测流式传输中的停滞：

```python
class StreamIdleTimeoutError(Exception):
    """流式传输超时：连续事件间隔超过阈值。"""
    pass

async def with_idle_timeout(
    stream: AsyncIterator[T],
    timeout_seconds: int,
) -> AsyncIterator[T]:
    """包装流式迭代器，添加空闲超时检测。"""
    if timeout_seconds <= 0:
        async for item in stream:
            yield item
        return

    while True:
        try:
            item = await asyncio.wait_for(
                stream.__anext__(),
                timeout=timeout_seconds,
            )
            yield item
        except asyncio.TimeoutError:
            raise StreamIdleTimeoutError(
                f"No SSE event received for {timeout_seconds}s"
            )
        except StopAsyncIteration:
            return
```

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `timeouts.stream_idle` | `300` | 连续 SSE 事件间最大等待秒数（0=禁用） |
| `timeouts.stream_idle_overrides` | `{}` | 按模型名覆盖上表标量（键=模型名子串，值=秒数）`[采纳]` |

适用于所有流式路径（Anthropic、Chat Completions、Responses）。

### Per-model 覆盖

不同模型的思考停顿特征差异很大——例如 `gpt-5.5` 系列在长链路推理时可能有远超 300 秒的静默期，而多数模型不需要这么宽松的阈值。`stream_idle_overrides` 允许按模型名做键值覆盖，命中优先于标量默认值：

```yaml
timeouts:
  stream_idle: 300
  stream_idle_overrides:
    gpt-5.5: 600
```

```python
def resolve_stream_idle(model: str, settings: TimeoutConfig) -> int:
    """解析某个模型应使用的流空闲超时（覆盖优先，未命中回落标量默认值）。"""
    for key, value in settings.stream_idle_overrides.items():
        if key in model:
            return value
    return settings.stream_idle
```

解析结果在**流开始时**读取一次，注入 `with_idle_timeout()`；进行中的流保持其解析值不受热重载影响，新流按热重载后的配置重新解析。这与延迟提交窗口、keepalive 心跳的"流起点读取一次"约定一致，见 [streaming-resilience.md](streaming-resilience.md)。

## 重复性检测

`repetition_detector.py` 使用 KMP（Knuth-Morris-Pratt）前缀函数检测流式输出中的重复模式。

### 工作原理

```python
class RepetitionDetector:
    def __init__(
        self,
        min_pattern_length: int = 50,
        min_repetitions: int = 3,
        buffer_size: int = 10000,
    ):
        self._buffer: str = ""
        self._min_pattern_length = min_pattern_length
        self._min_repetitions = min_repetitions
        self._buffer_size = buffer_size

    def feed(self, text: str) -> RepetitionResult | None:
        """喂入新的文本 delta，检测是否出现重复。"""
        self._buffer += text
        if len(self._buffer) > self._buffer_size:
            self._buffer = self._buffer[-self._buffer_size:]

        # 使用 KMP 前缀函数检测重复模式
        pattern = self._detect_repetition()
        if pattern:
            return RepetitionResult(
                pattern=pattern,
                repetitions=self._count_repetitions(pattern),
            )
        return None
```

### 集成

集成在 Anthropic 流式处理中，对 `text_delta` 事件进行实时检测：

- 当模型陷入重复输出循环时，记录警告日志
- **不中断流式传输**（仅告警，不干预）
- 可配置参数：最小模式长度、最小重复次数、缓冲区大小

### 使用场景

模型在某些情况下可能陷入重复输出循环（如反复输出相同的代码块或文本段落），浪费 token。重复性检测可以及时发现并记录这些情况。

## 跨格式流式翻译

`streaming/translator.py` 在需要时进行实时的 SSE 事件格式转换：

| 源格式 | 目标格式 | 场景 |
|--------|----------|------|
| Anthropic events | Chat Completions chunks | 当 Anthropic 端点响应需要以 OpenAI 格式返回 |
| Chat Completions chunks | Anthropic events | 当 OpenAI 端点响应需要以 Anthropic 格式返回 |
| Anthropic/Chat events | Responses events | Responses API 格式输出 |

翻译在流式迭代器层面实现，逐事件转换，不缓冲完整响应。

## 相关文档

- [设计文档总纲](DESIGN.md)
- [请求执行管道](request-pipeline.md)
- [流式韧性](streaming-resilience.md)（延迟提交窗口、keepalive 心跳、缓冲重试）
- [历史与审计](history-system.md)（Accumulator 提供的完整响应）
- [配置系统](config-system.md)（超时配置）
