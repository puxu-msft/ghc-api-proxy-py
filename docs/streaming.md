# 流式处理

## 概述

流式处理系统（`streaming/`）负责 SSE（Server-Sent Events）响应的接收、转发、累积和跨格式翻译。设计核心原则：**流式直通，不缓冲**。

系统包含三个子模块：
- `sse.py`：SSE StreamingResponse 构建工具
- `accumulator.py`：流式块累积器（用于历史记录）
- `translator.py`：跨格式流式实时翻译（Chat ↔ Anthropic ↔ Responses）

## SSE 响应构建 (sse.py)

### FastAPI StreamingResponse

```python
from starlette.responses import StreamingResponse

def create_sse_response(
    stream: AsyncIterator[str],
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """创建 SSE 流式响应。"""
    response_headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
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

### SSE 事件格式化

```python
def format_sse_event(
    data: str,
    *,
    event: str | None = None,
) -> str:
    """格式化单个 SSE 事件。"""
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {data}")
    lines.append("")  # 空行结束事件
    return "\n".join(lines) + "\n"

# OpenAI Chat Completions 格式：无 event 字段
# data: {"id":"chatcmpl-xxx","choices":[...]}
#
# Anthropic 格式：有 event 字段
# event: content_block_delta
# data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}
#
# OpenAI Responses 格式：有 event 字段
# event: response.output_text.delta
# data: {"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"Hello"}
```

## 流式直通模式

当请求和上游使用相同格式时，直接透传 SSE 块：

```python
async def passthrough_stream(
    upstream_response: httpx.Response,
    accumulator: StreamAccumulator | None = None,
) -> AsyncIterator[str]:
    """直接透传上游 SSE 流。"""
    async for line in upstream_response.aiter_lines():
        yield line + "\n"

        # 可选：同时喂给累积器（用于历史记录）
        if accumulator and line.startswith("data: "):
            data = line[6:]
            if data != "[DONE]":
                accumulator.feed(data)
```

## 流式累积器 (accumulator.py)

### 设计：Tee 模式

累积器使用 tee（分流）模式工作：流式块同时发送给客户端和累积器，互不阻塞。

```
上游 SSE 流
    │
    ├──→ 客户端（立即 yield，零延迟）
    │
    └──→ 累积器（后台解析、拼接）
              │
              └──→ 完成后写入历史存储
```

### OpenAI 流式累积

```python
class OpenAIStreamAccumulator:
    """累积 OpenAI streaming chunks 为完整响应。"""

    def __init__(self):
        self.model: str = ""
        self.finish_reason: str | None = None
        self.content_parts: list[str] = []
        self.tool_calls: dict[int, ToolCallAccumulator] = {}
        self.usage: Usage | None = None

    def feed(self, chunk_json: str) -> None:
        """喂入一个 SSE data 行的 JSON。"""
        chunk = json.loads(chunk_json)

        if "model" in chunk:
            self.model = chunk["model"]

        for choice in chunk.get("choices", []):
            delta = choice.get("delta", {})

            # 累积文本
            if "content" in delta and delta["content"]:
                self.content_parts.append(delta["content"])

            # 累积 tool calls
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc["index"]
                    if idx not in self.tool_calls:
                        self.tool_calls[idx] = ToolCallAccumulator(
                            id=tc.get("id", ""),
                            name=tc.get("function", {}).get("name", ""),
                        )
                    if "function" in tc and "arguments" in tc["function"]:
                        self.tool_calls[idx].arguments_parts.append(
                            tc["function"]["arguments"]
                        )

            # finish_reason
            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]

        # usage（通常在最后一个 chunk）
        if "usage" in chunk:
            self.usage = Usage(**chunk["usage"])

    def to_response(self) -> dict:
        """组装为完整的 ChatCompletion 响应。"""
        content = "".join(self.content_parts) or None
        tool_calls = [tc.to_dict() for tc in self.tool_calls.values()] or None

        return {
            "model": self.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                },
                "finish_reason": self.finish_reason,
            }],
            "usage": self.usage.to_dict() if self.usage else None,
        }

@dataclass
class ToolCallAccumulator:
    id: str
    name: str
    arguments_parts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": "".join(self.arguments_parts),
            },
        }
```

### Anthropic 流式累积

```python
class AnthropicStreamAccumulator:
    """累积 Anthropic streaming events 为完整响应。"""

    def __init__(self):
        self.model: str = ""
        self.stop_reason: str | None = None
        self.content_blocks: list[dict] = []
        self.current_block_index: int = -1
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.cache_creation_tokens: int = 0

    def feed(self, event_type: str, data: dict) -> None:
        """喂入一个 SSE 事件。"""
        match event_type:
            case "message_start":
                msg = data.get("message", {})
                self.model = msg.get("model", "")
                usage = msg.get("usage", {})
                self.input_tokens = usage.get("input_tokens", 0)

            case "content_block_start":
                block = data.get("content_block", {})
                self.content_blocks.append(block)
                self.current_block_index = data.get("index", 0)

            case "content_block_delta":
                idx = data.get("index", self.current_block_index)
                delta = data.get("delta", {})
                if idx < len(self.content_blocks):
                    block = self.content_blocks[idx]
                    if delta.get("type") == "text_delta":
                        block["text"] = block.get("text", "") + delta.get("text", "")
                    elif delta.get("type") == "input_json_delta":
                        # tool_use 的 input 是流式传来的 JSON 片段
                        block.setdefault("_input_parts", [])
                        block["_input_parts"].append(delta.get("partial_json", ""))

            case "content_block_stop":
                idx = data.get("index", self.current_block_index)
                if idx < len(self.content_blocks):
                    block = self.content_blocks[idx]
                    # 组装 tool_use input
                    if "_input_parts" in block:
                        block["input"] = json.loads("".join(block.pop("_input_parts")))

            case "message_delta":
                delta = data.get("delta", {})
                self.stop_reason = delta.get("stop_reason")
                usage = data.get("usage", {})
                self.output_tokens = usage.get("output_tokens", 0)

    def to_response(self) -> dict:
        """组装为完整的 Messages 响应。"""
        return {
            "type": "message",
            "role": "assistant",
            "model": self.model,
            "content": self.content_blocks,
            "stop_reason": self.stop_reason,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_read_input_tokens": self.cache_read_tokens,
                "cache_creation_input_tokens": self.cache_creation_tokens,
            },
        }
```

## 跨格式流式翻译 (translator.py)

当客户端使用 Anthropic 格式但上游返回 OpenAI 格式时（翻译路径），需要实时翻译流式块。

### OpenAI Chunk → Anthropic Events

```python
class StreamTranslator:
    """将 OpenAI streaming chunks 实时翻译为 Anthropic SSE events。"""

    def __init__(self, model: str, translation_ctx: TranslationContext):
        self._model = model
        self._ctx = translation_ctx
        self._content_block_index = 0
        self._started = False
        self._tool_call_indices: dict[int, int] = {}  # openai idx → anthropic block idx

    async def translate_stream(
        self,
        openai_stream: AsyncIterator[str],
    ) -> AsyncIterator[str]:
        """翻译 OpenAI SSE 流为 Anthropic SSE 流。"""

        async for line in openai_stream:
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                # 发送 message_stop
                yield format_sse_event(
                    json.dumps({"type": "message_stop"}),
                    event="message_stop",
                )
                break

            chunk = json.loads(data)
            async for event in self._translate_chunk(chunk):
                yield event

    async def _translate_chunk(self, chunk: dict) -> AsyncIterator[str]:
        """翻译单个 OpenAI chunk 为一个或多个 Anthropic events。"""

        # 首个 chunk → message_start
        if not self._started:
            self._started = True
            yield format_sse_event(
                json.dumps({
                    "type": "message_start",
                    "message": {
                        "id": f"msg_{chunk.get('id', '')}",
                        "type": "message",
                        "role": "assistant",
                        "model": self._model,
                        "content": [],
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                }),
                event="message_start",
            )

        for choice in chunk.get("choices", []):
            delta = choice.get("delta", {})

            # 文本内容
            if "content" in delta and delta["content"]:
                # 首次文本 → content_block_start
                if self._content_block_index == 0 and not self._tool_call_indices:
                    yield format_sse_event(
                        json.dumps({
                            "type": "content_block_start",
                            "index": self._content_block_index,
                            "content_block": {"type": "text", "text": ""},
                        }),
                        event="content_block_start",
                    )

                yield format_sse_event(
                    json.dumps({
                        "type": "content_block_delta",
                        "index": self._content_block_index,
                        "delta": {
                            "type": "text_delta",
                            "text": delta["content"],
                        },
                    }),
                    event="content_block_delta",
                )

            # Tool calls
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    openai_idx = tc["index"]

                    if openai_idx not in self._tool_call_indices:
                        # 关闭之前的文本块
                        if self._content_block_index == 0:
                            yield format_sse_event(
                                json.dumps({
                                    "type": "content_block_stop",
                                    "index": 0,
                                }),
                                event="content_block_stop",
                            )

                        self._content_block_index += 1
                        self._tool_call_indices[openai_idx] = self._content_block_index

                        # 恢复原始工具名称
                        name = tc.get("function", {}).get("name", "")
                        original_name = self._ctx.tool_name_mapping.get(name, name)

                        yield format_sse_event(
                            json.dumps({
                                "type": "content_block_start",
                                "index": self._content_block_index,
                                "content_block": {
                                    "type": "tool_use",
                                    "id": tc.get("id", ""),
                                    "name": original_name,
                                    "input": {},
                                },
                            }),
                            event="content_block_start",
                        )

                    # 流式 tool arguments
                    if "function" in tc and "arguments" in tc["function"]:
                        block_idx = self._tool_call_indices[openai_idx]
                        yield format_sse_event(
                            json.dumps({
                                "type": "content_block_delta",
                                "index": block_idx,
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": tc["function"]["arguments"],
                                },
                            }),
                            event="content_block_delta",
                        )

            # finish_reason
            finish = choice.get("finish_reason")
            if finish:
                # 关闭所有打开的 content blocks
                # ...

                # message_delta
                stop_reason_map = {
                    "stop": "end_turn",
                    "length": "max_tokens",
                    "tool_calls": "tool_use",
                }
                yield format_sse_event(
                    json.dumps({
                        "type": "message_delta",
                        "delta": {
                            "stop_reason": stop_reason_map.get(finish, "end_turn"),
                        },
                        "usage": {"output_tokens": 0},
                    }),
                    event="message_delta",
                )
```

### 完整翻译流程

```
上游 OpenAI SSE 流
    │
    ▼ data: {"choices":[{"delta":{"role":"assistant"}}]}
    │
    ├─→ [StreamTranslator]
    │       │
    │       ├─→ event: message_start
    │       │   data: {"type":"message_start","message":{...}}
    │       │
    │       ├─→ event: content_block_start
    │       │   data: {"type":"content_block_start","index":0,...}
    │       │
    │       ├─→ event: content_block_delta (多个)
    │       │   data: {"type":"content_block_delta","delta":{"type":"text_delta",...}}
    │       │
    │       ├─→ event: content_block_stop
    │       │   data: {"type":"content_block_stop","index":0}
    │       │
    │       ├─→ event: message_delta
    │       │   data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}
    │       │
    │       └─→ event: message_stop
    │           data: {"type":"message_stop"}
    │
    └─→ 客户端收到标准 Anthropic SSE 流
```

## Responses API 流式处理

### 事件模型

Responses API 的流式事件比 Chat Completions 更加结构化，分为三层：

```
响应生命周期层
    response.created → response.in_progress → response.completed/failed/incomplete

输出条目层
    response.output_item.added → ... → response.output_item.done

内容层（增量）
    response.content_part.added
    response.output_text.delta (多个) → response.output_text.done
    response.function_call_arguments.delta (多个) → response.function_call_arguments.done
    response.refusal.delta (多个) → response.refusal.done
    response.reasoning_summary_text.delta (多个) → response.reasoning_summary_text.done
    response.content_part.done
```

### Responses 流式累积

```python
class ResponsesStreamAccumulator:
    """累积 Responses API streaming events 为完整响应。"""

    def __init__(self):
        self.response_id: str = ""
        self.model: str = ""
        self.status: str = "in_progress"
        self.output_items: list[dict] = []
        self.usage: dict | None = None

        # 文本累积缓冲（按 output_index + content_index 索引）
        self._text_parts: dict[tuple[int, int], list[str]] = {}
        # 函数参数累积缓冲（按 output_index 索引）
        self._func_args_parts: dict[int, list[str]] = {}

    def feed(self, event_type: str, data: dict) -> None:
        """喂入一个 SSE 事件。"""
        match event_type:
            case "response.created" | "response.in_progress":
                resp = data.get("response", {})
                self.response_id = resp.get("id", "")
                self.model = resp.get("model", "")

            case "response.output_item.added":
                item = data.get("item", {})
                output_idx = data.get("output_index", 0)
                # 确保 output_items 列表足够长
                while len(self.output_items) <= output_idx:
                    self.output_items.append({})
                self.output_items[output_idx] = item

            case "response.output_text.delta":
                key = (data.get("output_index", 0), data.get("content_index", 0))
                self._text_parts.setdefault(key, []).append(data.get("delta", ""))

            case "response.output_text.done":
                output_idx = data.get("output_index", 0)
                content_idx = data.get("content_index", 0)
                text = data.get("text", "")
                if output_idx < len(self.output_items):
                    item = self.output_items[output_idx]
                    content = item.setdefault("content", [])
                    while len(content) <= content_idx:
                        content.append({})
                    content[content_idx] = {"type": "output_text", "text": text}

            case "response.function_call_arguments.delta":
                idx = data.get("output_index", 0)
                self._func_args_parts.setdefault(idx, []).append(data.get("delta", ""))

            case "response.function_call_arguments.done":
                idx = data.get("output_index", 0)
                if idx < len(self.output_items):
                    self.output_items[idx]["arguments"] = data.get("arguments", "")

            case "response.completed":
                resp = data.get("response", {})
                self.status = "completed"
                self.output_items = resp.get("output", self.output_items)
                self.usage = resp.get("usage")

            case "response.failed":
                self.status = "failed"

            case "response.incomplete":
                self.status = "incomplete"

    def to_response(self) -> dict:
        """组装为完整的 Responses API 响应。"""
        return {
            "id": self.response_id,
            "object": "response",
            "model": self.model,
            "status": self.status,
            "output": self.output_items,
            "usage": self.usage,
        }
```

### 跨格式流式翻译：Responses → Anthropic Events

当客户端使用 Anthropic 格式但上游返回 Responses 格式时，需要实时翻译：

```
Responses 事件                              Anthropic 事件
─────────────────────                      ─────────────────
response.created                        → message_start
response.output_item.added (message)    → (无需映射，等待内容)
response.content_part.added (text)      → content_block_start (type: "text")
response.output_text.delta              → content_block_delta (text_delta)
response.output_text.done               → content_block_stop
response.output_item.added (func_call)  → content_block_start (type: "tool_use")
response.function_call_arguments.delta  → content_block_delta (input_json_delta)
response.function_call_arguments.done   → content_block_stop
response.output_item.added (reasoning)  → content_block_start (type: "thinking")
response.reasoning_summary_text.delta   → content_block_delta (thinking_delta)
response.completed                      → message_delta (stop_reason) + message_stop
response.failed                         → error event
```

### 跨格式流式翻译：Responses → Chat Completions Chunks

当客户端使用 Chat Completions 格式但上游返回 Responses 格式时：

```
Responses 事件                              Chat Completions Chunk
─────────────────────                      ─────────────────────
response.created                        → chunk: delta={role: "assistant"}
response.output_text.delta              → chunk: delta={content: delta_text}
response.function_call_arguments.delta  → chunk: delta={tool_calls: [{index, function: {arguments}}]}
response.output_item.added (func_call)  → chunk: delta={tool_calls: [{index, id, function: {name}}]}
response.completed                      → chunk: finish_reason="stop"/"tool_calls"
                                          → data: [DONE]
```

### 跨格式流式翻译：Chat Completions Chunks → Responses Events

当客户端使用 Responses 格式但上游返回 Chat Completions 格式时：

```
Chat Completions Chunk                    Responses 事件
─────────────────────                    ─────────────────
首个 chunk (role)                       → response.created + response.in_progress
                                          + response.output_item.added
                                          + response.content_part.added
delta.content                           → response.output_text.delta
delta.tool_calls[i] (首次出现)          → response.output_item.added (function_call)
delta.tool_calls[i].function.arguments  → response.function_call_arguments.delta
finish_reason="stop"                    → response.output_text.done
                                          + response.content_part.done
                                          + response.output_item.done
                                          + response.completed
finish_reason="tool_calls"              → response.function_call_arguments.done
                                          + response.output_item.done (each)
                                          + response.completed
data: [DONE]                            → (已在 finish_reason 处理中发送 completed)
```

## 性能考量

- **零缓冲**：每个 SSE 块从上游到达后立即 yield 给客户端
- **Tee 模式**：累积器在同一个 async 循环中同步处理，不创建额外 task
- **内存效率**：累积器仅拼接字符串片段，完成后立即写入历史并释放
- **背压**：使用 `AsyncIterator` 自然背压，客户端消费慢时上游读取自动暂停

## 相关文档

- [整体架构概览](architecture.md)
- [请求执行管道](request-pipeline.md)
- [转换系统](transform-system.md)（非流式翻译）
- [历史与审计](history-system.md)（累积器数据去向）
