# 核心数据模型

## 概述

本文档定义系统中所有 Pydantic 模型，分为三类：

- **OpenAI 模型**（`models/openai.py`）：OpenAI Chat Completions API 和 Responses API 请求/响应
- **Anthropic 模型**（`models/anthropic.py`）：Anthropic Messages API 请求/响应
- **通用模型**（`models/common.py`）：跨格式共享的数据结构

以及 **内部模型**（散布在各模块中）：管道上下文、历史记录、审批等。

---

## OpenAI 模型 (models/openai.py)

### 请求

```python
class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions 请求。"""
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    n: int = 1
    stop: str | list[str] | None = None
    tools: list[Tool] | None = None
    tool_choice: str | dict | None = None    # "auto" | "none" | "required" | {type, function}
    response_format: dict | None = None
    seed: int | None = None

class ChatMessage(BaseModel):
    """聊天消息。"""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart] | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None      # role=assistant 时
    tool_call_id: str | None = None                # role=tool 时

class ContentPart(BaseModel):
    """多模态内容部分。"""
    type: Literal["text", "image_url"]
    text: str | None = None
    image_url: ImageUrl | None = None

class ImageUrl(BaseModel):
    url: str
    detail: Literal["auto", "low", "high"] = "auto"

class ToolCall(BaseModel):
    """工具调用。"""
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall

class FunctionCall(BaseModel):
    name: str
    arguments: str                                  # JSON 字符串

class Tool(BaseModel):
    """工具定义。"""
    type: Literal["function"] = "function"
    function: FunctionDefinition

class FunctionDefinition(BaseModel):
    name: str
    description: str = ""
    parameters: dict | None = None                  # JSON Schema
    strict: bool | None = None
```

### 响应

```python
class ChatCompletionResponse(BaseModel):
    """非流式响应。"""
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: OpenAIUsage | None = None

class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None

class OpenAIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

### 流式块

```python
class ChatCompletionChunk(BaseModel):
    """流式响应块。"""
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChunkChoice]
    usage: OpenAIUsage | None = None           # 最后一个 chunk 可能包含

class ChunkChoice(BaseModel):
    index: int = 0
    delta: ChunkDelta
    finish_reason: str | None = None

class ChunkDelta(BaseModel):
    """流式增量内容。"""
    role: str | None = None
    content: str | None = None
    tool_calls: list[ChunkToolCall] | None = None

class ChunkToolCall(BaseModel):
    """流式工具调用增量。"""
    index: int
    id: str | None = None
    type: str | None = None
    function: ChunkFunction | None = None

class ChunkFunction(BaseModel):
    name: str | None = None
    arguments: str | None = None               # 增量 JSON 片段
```

### Responses API

OpenAI 新一代有状态 API，使用 `input` 替代 `messages`，`output` 替代 `choices`。

#### 请求

```python
class ResponsesRequest(BaseModel):
    """OpenAI Responses API 请求。"""
    model: str
    input: list[InputItem]                          # 输入条目数组
    instructions: str | None = None                 # 系统指令（替代 system message）
    stream: bool = False
    max_output_tokens: int | None = None            # 注意：非 max_tokens
    temperature: float | None = None
    top_p: float | None = None
    tools: list[ResponsesTool] | None = None
    tool_choice: str | dict | None = None
    previous_response_id: str | None = None         # 链接之前的响应（对话延续）
    store: bool = True                              # 是否在服务端存储
    truncation: str | None = None                   # "auto" | "disabled"
    reasoning: ReasoningConfig | None = None

class ReasoningConfig(BaseModel):
    """推理配置。"""
    effort: Literal["low", "medium", "high"] = "medium"
```

#### 输入条目

`input` 数组中的元素采用判别联合（discriminated union）模式：

```python
# 消息条目（无显式 type 字段，通过 role 判别）
class InputMessage(BaseModel):
    """输入消息。"""
    role: Literal["user", "assistant", "system", "developer"]
    content: str | list[InputContentPart]

class InputContentPart(BaseModel):
    """输入内容部分（多模态）。"""
    type: Literal["input_text", "input_image", "input_file"]
    text: str | None = None                         # input_text
    image_url: str | None = None                    # input_image
    file_id: str | None = None                      # input_file

# 函数调用输出（等价于 Chat Completions 的 role: "tool"）
class FunctionCallOutputItem(BaseModel):
    """函数调用结果。"""
    type: Literal["function_call_output"] = "function_call_output"
    call_id: str
    output: str

# 条目引用（引用之前响应中的条目）
class ItemReference(BaseModel):
    """条目引用。"""
    type: Literal["item_reference"] = "item_reference"
    id: str

# 联合类型
InputItem = InputMessage | FunctionCallOutputItem | ItemReference
```

#### 工具定义

```python
class ResponsesTool(BaseModel):
    """Responses API 工具定义，支持内置工具。"""
    type: Literal["function", "web_search", "file_search", "code_interpreter", "computer_use"]

    # type = "function"
    function: FunctionDefinition | None = None       # 复用 Chat Completions 的定义

    # type = "file_search"
    vector_store_ids: list[str] | None = None

    # type = "computer_use"
    display_width: int | None = None
    display_height: int | None = None
    environment: str | None = None
```

#### 响应

```python
class ResponsesResponse(BaseModel):
    """Responses API 非流式响应。"""
    id: str                                          # "resp_xxx"
    object: Literal["response"] = "response"
    created_at: int
    model: str
    status: Literal["completed", "failed", "incomplete", "in_progress"]
    output: list[OutputItem]
    usage: OpenAIUsage | None = None

class OutputMessage(BaseModel):
    """输出消息条目。"""
    type: Literal["message"] = "message"
    id: str
    role: Literal["assistant"] = "assistant"
    status: Literal["completed", "in_progress"] = "completed"
    content: list[OutputContentPart]

class OutputContentPart(BaseModel):
    """输出内容部分。"""
    type: Literal["output_text", "refusal"]
    text: str | None = None                          # output_text
    refusal: str | None = None                       # refusal

class OutputFunctionCall(BaseModel):
    """函数调用输出条目。"""
    type: Literal["function_call"] = "function_call"
    id: str
    call_id: str
    name: str
    arguments: str                                   # JSON 字符串
    status: Literal["completed", "in_progress"] = "completed"

class OutputReasoning(BaseModel):
    """推理输出条目。"""
    type: Literal["reasoning"] = "reasoning"
    id: str
    summary: list[ReasoningSummary]

class ReasoningSummary(BaseModel):
    type: Literal["summary_text"] = "summary_text"
    text: str

# 联合类型
OutputItem = OutputMessage | OutputFunctionCall | OutputReasoning
```

#### 流式事件

```python
class ResponseStreamEvent(BaseModel):
    """Responses API 流式事件基类。"""
    type: str

# ── 响应生命周期事件 ──

class ResponseCreatedEvent(ResponseStreamEvent):
    type: Literal["response.created"] = "response.created"
    response: ResponsesResponse

class ResponseInProgressEvent(ResponseStreamEvent):
    type: Literal["response.in_progress"] = "response.in_progress"
    response: ResponsesResponse

class ResponseCompletedEvent(ResponseStreamEvent):
    type: Literal["response.completed"] = "response.completed"
    response: ResponsesResponse                      # 含完整 output 和 usage

class ResponseFailedEvent(ResponseStreamEvent):
    type: Literal["response.failed"] = "response.failed"
    response: ResponsesResponse

class ResponseIncompleteEvent(ResponseStreamEvent):
    type: Literal["response.incomplete"] = "response.incomplete"
    response: ResponsesResponse

# ── 输出条目事件 ──

class OutputItemAddedEvent(ResponseStreamEvent):
    type: Literal["response.output_item.added"] = "response.output_item.added"
    output_index: int
    item: OutputItem

class OutputItemDoneEvent(ResponseStreamEvent):
    type: Literal["response.output_item.done"] = "response.output_item.done"
    output_index: int
    item: OutputItem

# ── 内容部分事件 ──

class ContentPartAddedEvent(ResponseStreamEvent):
    type: Literal["response.content_part.added"] = "response.content_part.added"
    output_index: int
    content_index: int
    part: OutputContentPart

class ContentPartDoneEvent(ResponseStreamEvent):
    type: Literal["response.content_part.done"] = "response.content_part.done"
    output_index: int
    content_index: int
    part: OutputContentPart

# ── 增量事件 ──

class OutputTextDeltaEvent(ResponseStreamEvent):
    type: Literal["response.output_text.delta"] = "response.output_text.delta"
    output_index: int
    content_index: int
    delta: str

class OutputTextDoneEvent(ResponseStreamEvent):
    type: Literal["response.output_text.done"] = "response.output_text.done"
    output_index: int
    content_index: int
    text: str

class FunctionCallArgsDeltaEvent(ResponseStreamEvent):
    type: Literal["response.function_call_arguments.delta"] = "response.function_call_arguments.delta"
    output_index: int
    delta: str

class FunctionCallArgsDoneEvent(ResponseStreamEvent):
    type: Literal["response.function_call_arguments.done"] = "response.function_call_arguments.done"
    output_index: int
    arguments: str

class RefusalDeltaEvent(ResponseStreamEvent):
    type: Literal["response.refusal.delta"] = "response.refusal.delta"
    output_index: int
    content_index: int
    delta: str

class ReasoningSummaryDeltaEvent(ResponseStreamEvent):
    type: Literal["response.reasoning_summary_text.delta"] = "response.reasoning_summary_text.delta"
    output_index: int
    summary_index: int
    delta: str

# ── 元信息事件 ──

class RateLimitUpdatedEvent(ResponseStreamEvent):
    type: Literal["rate_limit_updated"] = "rate_limit_updated"
    rate_limits: list[dict]                          # name, limit, remaining, reset_seconds

class ResponseErrorEvent(ResponseStreamEvent):
    type: Literal["error"] = "error"
    code: str
    message: str
```

---

## Anthropic 模型 (models/anthropic.py)

### 请求

```python
class MessagesRequest(BaseModel):
    """Anthropic Messages 请求。"""
    model: str
    max_tokens: int
    system: str | list[SystemContent] | None = None
    messages: list[AnthropicMessage]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    tools: list[AnthropicTool] | None = None
    tool_choice: AnthropicToolChoice | None = None
    thinking: ThinkingConfig | None = None
    metadata: dict | None = None

class SystemContent(BaseModel):
    """系统提示词内容块（支持缓存标记）。"""
    type: Literal["text"] = "text"
    text: str
    cache_control: CacheControl | None = None

class CacheControl(BaseModel):
    type: Literal["ephemeral"] = "ephemeral"

class AnthropicMessage(BaseModel):
    """Anthropic 消息。"""
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]

class AnthropicTool(BaseModel):
    """工具定义。"""
    name: str
    description: str = ""
    input_schema: dict                          # JSON Schema

class AnthropicToolChoice(BaseModel):
    type: Literal["auto", "any", "tool", "none"]
    name: str | None = None                     # type=tool 时必需
    disable_parallel_tool_use: bool | None = None

class ThinkingConfig(BaseModel):
    type: Literal["enabled", "disabled", "adaptive"] = "enabled"
    budget_tokens: int | None = None           # type="enabled" 时必需，"adaptive" 时不需要
```

### 内容块

```python
class ContentBlock(BaseModel):
    """消息内容块，支持多种类型。"""
    type: Literal["text", "tool_use", "tool_result", "thinking", "image"]

    # type = "text"
    text: str | None = None
    cache_control: CacheControl | None = None

    # type = "tool_use"
    id: str | None = None
    name: str | None = None
    input: dict | None = None

    # type = "tool_result"
    tool_use_id: str | None = None
    content: str | list[ContentBlock] | None = None
    is_error: bool | None = None

    # type = "thinking"
    thinking: str | None = None

    # type = "image"
    source: ImageSource | None = None

class ImageSource(BaseModel):
    type: Literal["base64", "url"]
    media_type: str | None = None               # "image/jpeg", "image/png", etc.
    data: str | None = None                     # base64 编码
    url: str | None = None
```

### 响应

```python
class MessagesResponse(BaseModel):
    """非流式响应。"""
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str
    content: list[ContentBlock]
    stop_reason: Literal["end_turn", "max_tokens", "tool_use", "stop_sequence"] | None
    usage: AnthropicUsage

class AnthropicUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
```

### 流式事件

```python
class MessageStreamEvent(BaseModel):
    """SSE 流式事件基类。"""
    type: str

class MessageStartEvent(MessageStreamEvent):
    type: Literal["message_start"] = "message_start"
    message: MessagesResponse

class ContentBlockStartEvent(MessageStreamEvent):
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ContentBlock

class ContentBlockDeltaEvent(MessageStreamEvent):
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: Delta

class Delta(BaseModel):
    type: Literal["text_delta", "input_json_delta", "thinking_delta"]
    text: str | None = None                     # text_delta
    partial_json: str | None = None             # input_json_delta
    thinking: str | None = None                 # thinking_delta

class ContentBlockStopEvent(MessageStreamEvent):
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int

class MessageDeltaEvent(MessageStreamEvent):
    type: Literal["message_delta"] = "message_delta"
    delta: MessageDelta
    usage: MessageDeltaUsage

class MessageDelta(BaseModel):
    stop_reason: str | None = None

class MessageDeltaUsage(BaseModel):
    output_tokens: int

class MessageStopEvent(MessageStreamEvent):
    type: Literal["message_stop"] = "message_stop"

class PingEvent(MessageStreamEvent):
    type: Literal["ping"] = "ping"

class ErrorEvent(MessageStreamEvent):
    type: Literal["error"] = "error"
    error: ErrorInfo

class ErrorInfo(BaseModel):
    type: str
    message: str
```

---

## 通用模型 (models/common.py)

```python
class Usage(BaseModel):
    """统一 token 用量。"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @classmethod
    def from_openai(cls, usage: dict) -> "Usage":
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        return cls(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_read_input_tokens=cached,
        )

    @classmethod
    def from_anthropic(cls, usage: dict) -> "Usage":
        return cls(**usage)

class ModelInfo(BaseModel):
    """模型信息（对应上游 API 返回的模型对象）。"""
    id: str                                          # 模型标识（如 "claude-opus-4.6"）
    name: str = ""                                   # 显示名称（如 "Claude Opus 4.6"）
    version: str = ""                                # 版本标识（可能与 id 不同）
    vendor: str = ""                                 # 供应商："Anthropic" | "OpenAI" | "Azure OpenAI" | "Google"
    object: Literal["model"] = "model"
    preview: bool = False                            # 预览版标记
    model_type: Literal["chat", "embeddings", "completion"] = "chat"

    # 端点支持
    supported_endpoints: list[str] = []              # 如 ["/chat/completions", "/v1/messages"]
                                                     # 空列表表示旧模型，隐式仅支持 /chat/completions

    # UI 相关
    model_picker_enabled: bool = False               # 是否在模型选择器中显示
    model_picker_category: Literal["powerful", "versatile", "lightweight"] | None = None
    is_chat_default: bool = False                    # 是否为默认 chat 模型
    is_chat_fallback: bool = False                   # 是否为回退 chat 模型

    # 计费
    billing: ModelBilling | None = None

    # 策略
    policy: ModelPolicy | None = None

    # 能力（仅 chat 类型模型有完整能力）
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)

class ModelBilling(BaseModel):
    """模型计费信息。"""
    is_premium: bool = False                         # 是否为高级模型（消耗额外配额）
    multiplier: float = 0                            # 配额消耗倍率（0=免费，1=标准，3=3倍）
    restricted_to: list[str] | None = None           # 订阅等级限制
                                                     # 如 ["pro", "pro_plus", "business", "enterprise"]

class ModelPolicy(BaseModel):
    """模型策略信息。"""
    state: str = "enabled"                           # "enabled" | "disabled"
    terms: str = ""                                  # 使用条款说明

class ModelCapabilities(BaseModel):
    """模型能力描述。"""
    family: str = ""                                 # 模型家族（如 "claude-opus-4.6"）
    tokenizer: str = ""                              # 分词器："o200k_base" | "cl100k_base"

    # 功能支持
    supports_tool_calls: bool = True
    supports_parallel_tool_calls: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_structured_outputs: bool = False

    # Thinking 支持（三种模式）
    supports_thinking: bool = False                  # 是否支持 thinking
    supports_adaptive_thinking: bool = False          # 是否支持自适应 thinking（模型自行决策）
    max_thinking_budget: int | None = None           # 最大 thinking token 预算
    min_thinking_budget: int | None = None           # 最小 thinking token 预算

    # Token 限制
    max_context_window_tokens: int | None = None     # 总上下文窗口（input + output）
    max_prompt_tokens: int | None = None             # 最大输入 token
    max_output_tokens: int | None = None             # 最大输出 token（流式）
    max_non_streaming_output_tokens: int | None = None  # 最大输出 token（非流式，可能更小）

    # 视觉能力详情
    vision_limits: VisionLimits | None = None

class VisionLimits(BaseModel):
    """视觉能力限制。"""
    max_prompt_image_size: int | None = None         # 最大图片大小（字节）
    max_prompt_images: int | None = None             # 最大图片数量
    supported_media_types: list[str] = []            # 如 ["image/jpeg", "image/png", "image/webp"]

class EmbeddingCapabilities(BaseModel):
    """嵌入模型能力（type=embeddings 时使用）。"""
    family: str = ""
    tokenizer: str = ""
    max_inputs: int | None = None                    # 最大批量输入数
    supports_dimensions: bool = False

class ErrorResponse(BaseModel):
    """通用错误响应（管理 API 使用）。"""
    error: str
    code: str
```

---

## 内部模型

### 管道相关（pipeline/）

```python
# pipeline/context.py

class RequestState(str, Enum):
    PENDING = "pending"
    SANITIZING = "sanitizing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class RequestContext:
    id: str                              # uuid4
    endpoint: Literal["openai-chat-completions", "openai-responses", "anthropic-messages"]
    state: RequestState
    created_at: float
    completed_at: float | None

    original_model: str
    resolved_model: str
    original_payload: dict

    sanitization: SanitizationResult | None
    approval_status: str | None
    rate_limiter_wait_ms: float

    attempts: list[Attempt]
    current_attempt: int

    response: ResponseData | None
    error: ApiError | None

@dataclass
class Attempt:
    number: int
    started_at: float
    completed_at: float | None
    status_code: int | None
    error: ApiError | None
    strategy_applied: str | None
    payload_modifications: list[str]

# pipeline/executor.py

@dataclass
class PipelineResult:
    context: RequestContext
    response: httpx.Response | None
    stream: AsyncIterator[bytes] | None
    is_streaming: bool

# pipeline/strategies/base.py

@dataclass
class RetryAction:
    should_retry: bool
    modified_payload: dict
    modifications: list[str]
```

### 转换相关（transform/）

```python
# transform/translator.py

@dataclass
class TranslationContext:
    tool_name_mapping: dict[str, str]    # 截断名 → 原始名
    original_model: str
    had_thinking: bool

# transform/sanitizer.py

@dataclass
class SanitizationResult:
    orphaned_blocks_removed: int
    empty_blocks_removed: int
    system_tags_stripped: int
    tool_names_fixed: int
    double_serialized_fixed: int
```

### 审批相关（pipeline/）

```python
# pipeline/approval.py

@dataclass
class PendingApproval:
    id: str
    request_id: str
    payload: dict
    endpoint: str
    model: str
    created_at: float
    timeout_at: float
    event: asyncio.Event
    result: ApprovalResult | None

@dataclass
class ApprovalResult:
    status: Literal["approved", "rejected", "approved_with_modifications"]
    reason: str = ""
    modified_payload: dict | None = None
    modifications: list[str] | None = None
```

### 历史相关（history/）

```python
# history/store.py

@dataclass
class HistoryEntry:
    id: str
    timestamp: float
    completed_at: float | None
    endpoint: Literal["openai-chat-completions", "openai-responses", "anthropic-messages"]
    status: Literal["pending", "streaming", "success", "error"]
    model: str
    original_model: str
    request_payload: dict
    response: ResponseData | None
    pipeline: PipelineDetails

@dataclass
class ResponseData:
    content: list[dict] | str | None
    stop_reason: str | None
    usage: Usage | None
    tool_calls: list[dict] | None

@dataclass
class PipelineDetails:
    attempts: int
    total_duration_ms: float
    sanitization: SanitizationResult | None
    model_resolved_from: str
    model_resolved_to: str
    format_translated: bool
    approval_status: str | None
    rate_limiter_wait_ms: float
    retry_strategies_applied: list[str]

@dataclass
class HistoryStats:
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_input_tokens: int
    total_output_tokens: int
    by_model: dict[str, ModelStats]
    by_endpoint: dict[str, int]
    durations: list[float]

@dataclass
class ModelStats:
    count: int
    input_tokens: int
    output_tokens: int
```

### 错误相关

```python
# errors.py

class ErrorType(str, Enum):
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    INVALID_REQUEST = "invalid_request"
    AUTH_ERROR = "auth_error"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    MAX_RETRIES = "max_retries"

@dataclass
class ApiError:
    type: ErrorType
    message: str
    status_code: int = 0
    retry_after: float | None = None
```

---

## 模型关系图

```
                    ┌──────────────────┐
                    │   AppSettings    │
                    │   (config/)      │
                    └────────┬─────────┘
                             │ 配置
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐   ┌──────────────┐    ┌──────────────────┐
│ ModelResolver │   │  Sanitizer   │    │ SystemPrompt     │
│              │   │              │    │ Processor        │
└──────┬───────┘   └──────┬───────┘    └──────┬───────────┘
       │                  │                   │
       │                  ▼                   │
       │         ┌──────────────┐             │
       │         │  Translator  │             │
       │         └──────┬───────┘             │
       │                │                     │
       ▼                ▼                     ▼
┌────────────────────────────────────────────────────┐
│                RequestContext                       │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Attempt │  │ ApiError │  │SanitizationResult│  │
│  └─────────┘  └──────────┘  └──────────────────┘  │
└───────────────────────┬────────────────────────────┘
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
     ┌──────────┐ ┌──────────┐ ┌──────────────┐
     │ Pipeline │ │ Approval │ │ HistoryEntry │
     │ Result   │ │ Result   │ │              │
     └──────────┘ └──────────┘ └──────────────┘
```

## 相关文档

- [整体架构概览](architecture.md)
- [转换系统](transform-system.md)（翻译和清洗逻辑）
- [流式处理](streaming.md)（流式块模型）
- [请求执行管道](request-pipeline.md)（管道数据结构）
- [历史与审计](history-system.md)（历史数据结构）
