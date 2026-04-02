# API 端点规格

本文档定义所有对外暴露的 HTTP 端点，分为**代理端点**（转发到上游）和**管理端点**（本地功能）。

## 代理端点

### POST /v1/chat/completions

OpenAI Chat Completions 兼容端点。接收 OpenAI 格式请求，转发到上游的 OpenAI-compatible 端点。

**请求体：**

```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"}
  ],
  "stream": true,
  "max_tokens": 4096,
  "temperature": 0.7,
  "top_p": 1.0,
  "tools": [...],
  "tool_choice": "auto"
}
```

**响应（非流式）：** `200 OK`，`Content-Type: application/json`

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

**响应（流式）：** `200 OK`，`Content-Type: text/event-stream`

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**错误响应：**

| 状态码 | 场景 |
|--------|------|
| 400 | 请求格式错误、模型不存在 |
| 401 | 认证失败（token 无效/过期） |
| 403 | 请求被审批拒绝 |
| 413 | 请求体过大（token 超限） |
| 429 | 上游限流 |
| 500 | 上游服务器错误 |
| 504 | 上游超时 |

---

### POST /v1/messages

Anthropic Messages API 兼容端点。接收 Anthropic 格式请求。

**路由逻辑：**
- 模型支持 Anthropic 端点（如 Claude 系列）→ 直接转发到上游 `/v1/messages`
- 模型不支持 Anthropic 端点 → 翻译为 OpenAI 格式，转发到 `/chat/completions`，响应翻译回 Anthropic 格式

**请求体：**

```json
{
  "model": "claude-sonnet-4-5-20250514",
  "max_tokens": 8096,
  "system": "You are a helpful assistant.",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Hello"}
      ]
    }
  ],
  "stream": true,
  "tools": [...],
  "tool_choice": {"type": "auto"},
  "thinking": {"type": "enabled", "budget_tokens": 10000}
}
```

**响应（非流式）：** `200 OK`，`Content-Type: application/json`

```json
{
  "id": "msg_xxx",
  "type": "message",
  "role": "assistant",
  "model": "claude-sonnet-4-5-20250514",
  "content": [
    {"type": "text", "text": "Hello! How can I help?"}
  ],
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 8,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0
  }
}
```

**响应（流式）：** `200 OK`，`Content-Type: text/event-stream`

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_xxx","type":"message","role":"assistant","model":"claude-sonnet-4-5-20250514","content":[],"usage":{"input_tokens":10,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":8}}

event: message_stop
data: {"type":"message_stop"}
```

---

### POST /v1/responses

OpenAI Responses API 兼容端点。这是 OpenAI 新一代有状态 API，与 `/v1/chat/completions` 相比提供更丰富的结构化输入/输出、内置工具、对话链式引用和推理能力。

**路由逻辑：**
- 模型支持 `/responses` 端点 → 直接转发到上游 `/responses`
- 模型不支持 `/responses` 端点 → 翻译为 Chat Completions 格式转发，响应翻译回 Responses 格式

**请求体：**

```json
{
  "model": "gpt-4o",
  "input": [
    {"role": "user", "content": "Hello"}
  ],
  "instructions": "You are a helpful assistant.",
  "stream": true,
  "max_output_tokens": 4096,
  "temperature": 0.7,
  "top_p": 1.0,
  "tools": [
    {"type": "function", "function": {"name": "search", "description": "...", "parameters": {...}}},
    {"type": "web_search"},
    {"type": "file_search", "vector_store_ids": ["vs_xxx"]}
  ],
  "tool_choice": "auto",
  "previous_response_id": "resp_xxx",
  "store": false,
  "truncation": "auto",
  "reasoning": {"effort": "medium"}
}
```

**`input` 字段格式：**

`input` 是一个数组，支持以下条目类型：

| 类型 | 说明 |
|------|------|
| 消息条目 | `{"role": "user/assistant/system/developer", "content": "..."}` |
| 多模态内容 | `{"role": "user", "content": [{"type": "input_text", "text": "..."}, {"type": "input_image", "image_url": "..."}]}` |
| 函数调用输出 | `{"type": "function_call_output", "call_id": "call_xxx", "output": "..."}` |
| 条目引用 | `{"type": "item_reference", "id": "msg_xxx"}` |

与 Chat Completions 的 `messages` 区别：
- 使用 `input_text` / `input_image` / `input_file` 替代 `text` / `image_url`
- 支持 `developer` 角色（等价于 `system`）
- 通过 `previous_response_id` 实现对话链式引用（服务端状态）
- 函数调用结果是独立条目类型而非 `role: "tool"` 消息

**关键字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型 ID |
| `input` | array | 输入条目数组 |
| `instructions` | string | 系统指令（替代 system message） |
| `stream` | bool | 是否流式 |
| `max_output_tokens` | int | 最大输出 token 数 |
| `temperature` | float | 采样温度 |
| `tools` | array | 工具列表（function / web_search / file_search / code_interpreter / computer_use） |
| `tool_choice` | string/object | 工具选择策略 |
| `previous_response_id` | string | 链接之前的响应（对话延续） |
| `store` | bool | 是否在服务端存储响应（默认 true） |
| `truncation` | string | 截断策略（`auto` / `disabled`） |
| `reasoning` | object | 推理配置 `{"effort": "low"/"medium"/"high"}` |

**响应（非流式）：** `200 OK`，`Content-Type: application/json`

```json
{
  "id": "resp_xxx",
  "object": "response",
  "created_at": 1234567890,
  "model": "gpt-4o",
  "status": "completed",
  "output": [
    {
      "type": "message",
      "id": "msg_xxx",
      "role": "assistant",
      "status": "completed",
      "content": [
        {"type": "output_text", "text": "Hello! How can I help?"}
      ]
    }
  ],
  "usage": {
    "input_tokens": 10,
    "output_tokens": 8,
    "total_tokens": 18
  }
}
```

**`output` 条目类型：**

| 类型 | 说明 |
|------|------|
| `message` | 助手消息，含 `content` 数组（`output_text` / `refusal`） |
| `function_call` | 函数调用，含 `call_id`, `name`, `arguments` |
| `reasoning` | 推理过程（当启用 reasoning 时），含 `summary` 数组 |

**响应（流式）：** `200 OK`，`Content-Type: text/event-stream`

Responses API 的流式事件比 Chat Completions 更细粒度：

```
event: response.created
data: {"type":"response.created","response":{"id":"resp_xxx","object":"response","status":"in_progress","output":[],...}}

event: response.in_progress
data: {"type":"response.in_progress","response":{...}}

event: response.output_item.added
data: {"type":"response.output_item.added","output_index":0,"item":{"type":"message","id":"msg_xxx","role":"assistant","content":[]}}

event: response.content_part.added
data: {"type":"response.content_part.added","output_index":0,"content_index":0,"part":{"type":"output_text","text":""}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"Hello"}

event: response.output_text.delta
data: {"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"! How can I help?"}

event: response.output_text.done
data: {"type":"response.output_text.done","output_index":0,"content_index":0,"text":"Hello! How can I help?"}

event: response.content_part.done
data: {"type":"response.content_part.done","output_index":0,"content_index":0,"part":{"type":"output_text","text":"Hello! How can I help?"}}

event: response.output_item.done
data: {"type":"response.output_item.done","output_index":0,"item":{...}}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_xxx","status":"completed","output":[...],"usage":{...}}}
```

**流式事件类型完整列表：**

| 事件类型 | 说明 |
|----------|------|
| `response.created` | 响应对象创建 |
| `response.in_progress` | 响应开始生成 |
| `response.completed` | 响应完成 |
| `response.failed` | 响应失败 |
| `response.incomplete` | 响应因截断不完整 |
| `response.output_item.added` | 新输出条目添加 |
| `response.output_item.done` | 输出条目完成 |
| `response.content_part.added` | 新内容部分添加 |
| `response.content_part.done` | 内容部分完成 |
| `response.output_text.delta` | 文本增量 |
| `response.output_text.done` | 文本完成 |
| `response.function_call_arguments.delta` | 函数参数增量 |
| `response.function_call_arguments.done` | 函数参数完成 |
| `response.refusal.delta` | 拒绝内容增量 |
| `response.refusal.done` | 拒绝内容完成 |
| `response.reasoning_summary_text.delta` | 推理摘要增量 |
| `response.reasoning_summary_text.done` | 推理摘要完成 |
| `rate_limit_updated` | 限流信息更新 |
| `error` | 错误事件 |

**错误响应：** 同 Chat Completions 端点（OpenAI 格式）。

---

### GET /v1/models

返回上游可用模型列表。

**响应：** `200 OK`

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4-5-20250514",
      "object": "model",
      "name": "Claude Sonnet 4.5",
      "created": 1234567890,
      "owned_by": "anthropic",
      "capabilities": {
        "supports_tool_calls": true,
        "supports_vision": true,
        "supports_thinking": true
      },
      "supported_endpoints": ["/chat/completions", "/v1/messages", "/responses"]
    }
  ]
}
```

**数据来源：**
- Copilot 上游：通过 GitHub Copilot Models API 获取（需要 GitHub token）
- Generic 上游：通过 `GET {base_url}/v1/models` 获取

---

## 管理端点

### GET /health

健康检查端点。

**响应：** `200 OK`

```json
{
  "status": "healthy",
  "upstream": {
    "type": "copilot",
    "authenticated": true,
    "models_loaded": true,
    "model_count": 12
  },
  "rate_limiter": {
    "mode": "normal"
  },
  "approval": {
    "enabled": true,
    "pending_count": 0
  },
  "history": {
    "entry_count": 42,
    "max_entries": 200
  },
  "uptime_seconds": 3600
}
```

---

### 历史 API

#### GET /api/history/entries

查询历史记录。

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 50 | 返回条数（max 500） |
| `offset` | int | 0 | 偏移量 |
| `model` | string | - | 按模型名过滤 |
| `endpoint` | string | - | 按端点类型过滤（`openai-chat-completions` / `openai-responses` / `anthropic-messages`） |
| `status` | string | - | 按状态过滤（`success` / `error`） |
| `since` | ISO datetime | - | 起始时间 |
| `until` | ISO datetime | - | 结束时间 |
| `search` | string | - | 全文搜索（匹配消息内容） |

**响应：** `200 OK`

```json
{
  "entries": [
    {
      "id": "req_abc123",
      "timestamp": "2025-02-15T10:30:00Z",
      "endpoint": "anthropic-messages",
      "model": "claude-sonnet-4-5-20250514",
      "status": "success",
      "duration_ms": 1234,
      "usage": {
        "input_tokens": 500,
        "output_tokens": 200
      },
      "request_summary": {
        "message_count": 5,
        "has_tools": true,
        "has_system": true,
        "stream": true
      },
      "response_summary": {
        "content_block_count": 1,
        "stop_reason": "end_turn"
      }
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

#### GET /api/history/entries/{id}

获取单条历史详情（包含完整请求和响应）。

**响应：** `200 OK`

```json
{
  "id": "req_abc123",
  "timestamp": "2025-02-15T10:30:00Z",
  "endpoint": "anthropic-messages",
  "model": "claude-sonnet-4-5-20250514",
  "status": "success",
  "duration_ms": 1234,
  "request": {
    "model": "claude-sonnet-4-5-20250514",
    "system": "...",
    "messages": [...],
    "tools": [...],
    "max_tokens": 8096,
    "stream": true
  },
  "response": {
    "content": [...],
    "stop_reason": "end_turn",
    "usage": {...}
  },
  "pipeline": {
    "attempts": 1,
    "sanitization": {
      "orphaned_blocks_removed": 0,
      "empty_blocks_removed": 1
    },
    "model_resolved_from": "sonnet",
    "model_resolved_to": "claude-sonnet-4-5-20250514",
    "format_translated": false,
    "approval_status": "approved",
    "rate_limiter_wait_ms": 0
  }
}
```

#### GET /api/history/stats

获取使用统计。

**响应：** `200 OK`

```json
{
  "total_requests": 1000,
  "successful_requests": 950,
  "failed_requests": 50,
  "total_input_tokens": 500000,
  "total_output_tokens": 200000,
  "by_model": {
    "claude-sonnet-4-5-20250514": {"count": 800, "input_tokens": 400000, "output_tokens": 160000},
    "gpt-4o": {"count": 200, "input_tokens": 100000, "output_tokens": 40000}
  },
  "by_endpoint": {
    "anthropic-messages": {"count": 700},
    "openai-chat-completions": {"count": 200},
    "openai-responses": {"count": 100}
  },
  "avg_duration_ms": 1500,
  "p95_duration_ms": 3200
}
```

#### GET /api/history/export

导出历史记录为 JSON。

**查询参数：** 同 `GET /api/history/entries`（支持相同的过滤条件）

**响应：** `200 OK`，`Content-Type: application/json`，流式输出 JSON 数组。

#### WS /api/history/ws

WebSocket 端点，实时推送历史更新。

**服务器推送消息格式：**

```json
{
  "type": "entry_added",
  "entry": { /* HistoryEntry 摘要 */ }
}
```

```json
{
  "type": "entry_updated",
  "entry": { /* HistoryEntry 摘要（含响应） */ }
}
```

```json
{
  "type": "stats_updated",
  "stats": { /* 同 GET /api/history/stats */ }
}
```

---

### 审批 API

#### GET /api/approval/pending

获取所有待审批请求。

**响应：** `200 OK`

```json
{
  "pending": [
    {
      "id": "approval_xyz789",
      "request_id": "req_abc123",
      "created_at": "2025-02-15T10:30:00Z",
      "timeout_at": "2025-02-15T10:35:00Z",
      "endpoint": "anthropic-messages",
      "model": "claude-opus-4.6",
      "summary": {
        "message_count": 10,
        "has_tools": true,
        "has_system": true,
        "estimated_input_tokens": 5000
      }
    }
  ]
}
```

#### GET /api/approval/{id}

查看待审批请求详情（完整 payload）。

**响应：** `200 OK`

```json
{
  "id": "approval_xyz789",
  "request_id": "req_abc123",
  "created_at": "2025-02-15T10:30:00Z",
  "timeout_at": "2025-02-15T10:35:00Z",
  "endpoint": "anthropic-messages",
  "model": "claude-opus-4.6",
  "payload": {
    "model": "claude-opus-4.6",
    "system": "...",
    "messages": [...],
    "tools": [...],
    "max_tokens": 8096,
    "stream": true
  }
}
```

#### POST /api/approval/{id}/approve

批准请求，允许继续执行。

**请求体：** 空或 `{}`

**响应：** `200 OK`

```json
{
  "id": "approval_xyz789",
  "status": "approved"
}
```

#### POST /api/approval/{id}/reject

拒绝请求，返回错误给客户端。

**请求体：**

```json
{
  "reason": "Suspicious content detected"
}
```

**响应：** `200 OK`

```json
{
  "id": "approval_xyz789",
  "status": "rejected",
  "reason": "Suspicious content detected"
}
```

客户端收到的错误响应（格式取决于请求来源）：

OpenAI 格式：
```json
{
  "error": {
    "message": "Request rejected: Suspicious content detected",
    "type": "request_rejected",
    "code": "rejected"
  }
}
```

Anthropic 格式：
```json
{
  "type": "error",
  "error": {
    "type": "request_rejected",
    "message": "Request rejected: Suspicious content detected"
  }
}
```

#### POST /api/approval/{id}/modify

修改请求后批准。审批者可以编辑 payload 的任何部分后放行。

**请求体：**

```json
{
  "payload": {
    "system": "Modified system prompt...",
    "messages": [...],
    "max_tokens": 4096
  }
}
```

仅需包含要修改的字段，未包含的字段保持原值。

**响应：** `200 OK`

```json
{
  "id": "approval_xyz789",
  "status": "approved_with_modifications",
  "modifications": ["system", "max_tokens"]
}
```

#### WS /api/approval/ws

WebSocket 端点，实时推送审批事件。

**服务器推送消息格式：**

```json
{
  "type": "approval_requested",
  "approval": {
    "id": "approval_xyz789",
    "request_id": "req_abc123",
    "endpoint": "anthropic-messages",
    "model": "claude-opus-4.6",
    "summary": { /* 摘要 */ }
  }
}
```

```json
{
  "type": "approval_resolved",
  "approval": {
    "id": "approval_xyz789",
    "status": "approved"
  }
}
```

```json
{
  "type": "approval_timeout",
  "approval": {
    "id": "approval_xyz789",
    "status": "rejected",
    "reason": "Approval timeout"
  }
}
```

---

## 通用错误格式

所有端点在错误时根据来源格式返回对应的错误结构。

**OpenAI 格式错误（/v1/chat/completions, /v1/responses, /v1/models）：**

```json
{
  "error": {
    "message": "Error description",
    "type": "error_type",
    "code": "error_code"
  }
}
```

**Anthropic 格式错误（/v1/messages）：**

```json
{
  "type": "error",
  "error": {
    "type": "error_type",
    "message": "Error description"
  }
}
```

**管理端点错误（/api/*, /health）：**

```json
{
  "error": "Error description",
  "code": "error_code"
}
```

## 相关文档

- [整体架构概览](architecture.md)
- [手动审批系统](approval-system.md)
- [历史与审计](history-system.md)
- [核心数据模型](data-models.md)
