# 核心数据模型

> 本文档是**目标设计**（design spec），标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。未特别标注者默认 `[上游稳定][采纳]`。

## 概述

所有外部数据（请求、响应、配置）通过 Pydantic v2 模型验证。内部数据结构使用轻量 `dataclass`（不用 Pydantic——内部结构不需要外部输入验证，`dataclass` 更省创建开销，见下文「内部数据模型：性能取舍」）。

**Python 优化**：JS 版本使用 TypeScript 接口进行编译时类型检查，运行时无验证。Python 版本使用 Pydantic v2 的 Rust 核心提供运行时高速验证和自动序列化。

## 模型分类

- **OpenAI 模型**（`models/openai.py`）— Chat Completions API + Responses API
- **Anthropic 模型**（`models/anthropic.py`）— Messages API
- **Gemini 模型**（`models/gemini.py`）— `generateContent` / `streamGenerateContent` / `countTokens`
- **通用模型**（`models/common.py`）— 跨格式共享（Usage、ErrorResponse）
- **模型能力元数据**（`models/capabilities.py`）— `ModelInfo` / `ModelCapabilities` / `ModelSupports`
- **内部模型**（散布在各模块中）— 管道上下文、历史记录、审批等，均为轻量 `dataclass`

---

## OpenAI 模型 (`models/openai.py`)

### Chat Completions

```python
class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    n: int = 1
    stop: str | list[str] | None = None
    tools: list[Tool] | None = None
    tool_choice: str | dict | None = None
    response_format: dict | None = None
    seed: int | None = None

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart] | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

class ContentPart(BaseModel):
    type: Literal["text", "image_url"]
    text: str | None = None
    image_url: ImageUrl | None = None

class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall

class FunctionCall(BaseModel):
    name: str
    arguments: str                 # JSON string

class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDef

class FunctionDef(BaseModel):
    name: str
    description: str | None = None
    parameters: dict | None = None

class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage | None = None

class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None

class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChunkChoice]
    usage: Usage | None = None

class ChunkChoice(BaseModel):
    index: int
    delta: ChatMessageDelta
    finish_reason: str | None = None

class ChatMessageDelta(BaseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: list[ToolCallDelta] | None = None
```

### Responses API

```python
class ResponsesRequest(BaseModel):
    model: str
    input: list[InputItem]
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    tools: list[dict] | None = None
    instructions: str | None = None
    previous_response_id: str | None = None

class InputItem(BaseModel):
    """Responses API 输入项（多态）。"""
    type: str                          # "message", "function_call", "function_call_output", ...
    role: str | None = None
    content: str | list[dict] | None = None
    call_id: str | None = None
    name: str | None = None
    arguments: str | None = None
    output: str | None = None
    # ... 其他字段根据 type 而定

class ResponsesResponse(BaseModel):
    id: str
    object: Literal["response"] = "response"
    created_at: int
    model: str
    output: list[OutputItem]
    usage: ResponsesUsage | None = None
    status: str = "completed"

class OutputItem(BaseModel):
    type: str
    id: str | None = None
    role: str | None = None
    content: list[dict] | None = None
    # ... 其他字段

class ResponsesUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    output_tokens_details: OutputTokensDetails | None = None

class OutputTokensDetails(BaseModel):
    reasoning_tokens: int = 0
```

---

## Anthropic 模型 (`models/anthropic.py`)

### 请求/响应

```python
class MessagesRequest(BaseModel):
    model: str
    messages: list[AnthropicMessage]
    system: str | list[SystemBlock] | None = None
    max_tokens: int = 4096
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None
    tools: list[AnthropicTool] | None = None
    tool_choice: dict | None = None
    thinking: ThinkingConfig | None = None
    context_management: dict | None = None     # 服务端上下文编辑
    metadata: dict | None = None

class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]

class ContentBlock(BaseModel):
    """多态 content block，通过 type 字段区分。"""
    type: str
    # text
    text: str | None = None
    # tool_use
    id: str | None = None
    name: str | None = None
    input: dict | None = None
    # tool_result
    tool_use_id: str | None = None
    content: str | list[ContentBlock] | None = None
    is_error: bool | None = None
    # thinking
    thinking: str | None = None
    # image
    source: dict | None = None
    # cache_control
    cache_control: dict | None = None

class SystemBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str
    cache_control: dict | None = None

class ThinkingConfig(BaseModel):
    type: Literal["enabled", "disabled", "adaptive"] = "enabled"
    budget_tokens: int | None = None

class AnthropicTool(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict | None = None
    type: str | None = None          # server tools 的类型（如 "web_search_20250305"）
    cache_control: dict | None = None
    defer_loading: bool | None = None

class MessagesResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock]
    model: str
    stop_reason: str | None = None
    usage: AnthropicUsage | None = None

class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
```

### SSE 事件

```python
class MessageStreamEvent(BaseModel):
    """Anthropic SSE 事件（多态，通过 type 区分）。"""
    type: str
    # message_start
    message: MessagesResponse | None = None
    # content_block_start
    index: int | None = None
    content_block: ContentBlock | None = None
    # content_block_delta
    delta: dict | None = None
    # message_delta
    usage: dict | None = None
```

---

## Gemini 模型 (`models/gemini.py`)

Gemini 端点（详见 [multi-protocol.md](multi-protocol.md) 的路径解析与转换规则）以 `generateContent`/`streamGenerateContent`/`countTokens` 三个方法为核心。本项目不依赖官方 `google-genai` SDK 的类型（该 SDK 面向调用 Gemini，非承接 Gemini 请求），而是按 Gemini 公开 API 文档自行定义精简的 Pydantic 模型，只覆盖本项目实际转换用得到的字段——**不追求覆盖 Gemini API 全部参数面**，多余字段按 Pydantic 默认行为忽略（不设 `extra="forbid"`，因为客户端可能携带本项目暂不识别、但也不需要报错拒绝的扩展字段）。

```python
class GenerateContentRequest(BaseModel):
    """`:generateContent` / `:streamGenerateContent` 入站请求体。"""
    contents: list[Content] = Field(default_factory=list)
    tools: list[GeminiTool] | None = None
    tool_config: ToolConfig | None = None
    safety_settings: list[dict] | None = None      # 透传但本项目上游为 Copilot，不使用（见 multi-protocol.md）
    system_instruction: Content | None = None
    generation_config: GenerationConfig | None = None
    cached_content: str | None = None

class Content(BaseModel):
    role: Literal["user", "model"] | None = None   # None 见于 systemInstruction（无 role 语义）
    parts: list[Part] = Field(default_factory=list)

class Part(BaseModel):
    """多态 content part，按互斥字段出现与否区分变体（Gemini 官方 oneof 语义）。"""
    text: str | None = None
    inline_data: Blob | None = None                # {mime_type, data(base64)}
    function_call: FunctionCall | None = None
    function_response: FunctionResponse | None = None
    thought: bool | None = None                    # 标记该 part 为思维链片段
    thought_signature: str | None = None            # 思维签名（跨轮次校验，透传/剥离见 tool-use.md）

class Blob(BaseModel):
    mime_type: str
    data: str                                       # base64

class FunctionCall(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)

class FunctionResponse(BaseModel):
    name: str
    response: dict = Field(default_factory=dict)

class GeminiTool(BaseModel):
    function_declarations: list[FunctionDeclaration] | None = None

class FunctionDeclaration(BaseModel):
    name: str
    description: str | None = None
    parameters: dict | None = None                  # JSON Schema

class ToolConfig(BaseModel):
    function_calling_config: dict | None = None

class GenerationConfig(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    stop_sequences: list[str] | None = None
    candidate_count: int | None = None
    response_mime_type: str | None = None
    thinking_config: ThinkingConfigGemini | None = None

class ThinkingConfigGemini(BaseModel):
    include_thoughts: bool | None = None
    thinking_budget: int | None = None


class GenerateContentResponse(BaseModel):
    """`:generateContent` / `:streamGenerateContent` 出站响应体。"""
    candidates: list[Candidate] = Field(default_factory=list)
    prompt_feedback: dict | None = None
    usage_metadata: UsageMetadata | None = None
    model_version: str | None = None
    response_id: str | None = None

class Candidate(BaseModel):
    content: Content | None = None
    finish_reason: str | None = None
    index: int = 0
    safety_ratings: list[dict] | None = None

class UsageMetadata(BaseModel):
    prompt_token_count: int = 0
    candidates_token_count: int = 0
    total_token_count: int = 0
    thoughts_token_count: int = 0                   # 对应内部 Usage.reasoning_tokens，见下节转换


class CountTokensRequest(BaseModel):
    """`:countTokens` 入站请求体，两种互斥形态之一。"""
    contents: list[Content] | None = None
    generate_content_request: GenerateContentRequest | None = None
    cached_content: str | None = None

class CountTokensResponse(BaseModel):
    total_tokens: int
    cached_content_token_count: int | None = None


class GeminiErrorResponse(BaseModel):
    """Gemini 风格错误信封（gRPC 形态的 status 字段），见 multi-protocol.md 的 wire format 检测。"""
    error: GeminiErrorDetail

class GeminiErrorDetail(BaseModel):
    code: int
    message: str
    status: str
```

字段命名说明：Gemini 官方 wire format 用 `camelCase`（如 `systemInstruction`、`generationConfig`、`thinkingConfig`），本项目 Pydantic 模型字段名遵循 Python 惯例用 `snake_case`，通过 `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` 在序列化/反序列化边界自动转换，内部代码不接触 `camelCase` 拼写。

---

## 模型能力元数据 (`models/capabilities.py`)

Copilot `/models` 目录返回的每个模型条目携带一份能力描述，供 [model-resolution.md](model-resolution.md) 的端点决策、[anthropic-compat.md](anthropic-compat.md) 的 feature 检测（adaptive thinking、tool_search、context editing 等）、以及请求准备阶段的 header/参数适配共同消费。

```python
class ModelSupports(BaseModel):
    """`capabilities.supports` 的已知字段集合；Copilot 目录会随时间新增未列出的字段，
    未知字段通过 model_config extra="allow" 保留在 model_extra 里，不因未识别而丢失（见 richest-data-flow）。
    """
    model_config = ConfigDict(extra="allow")

    streaming: bool = True
    vision: bool = False
    tool_calls: bool = False
    parallel_tool_calls: bool = False
    tool_use: bool = True                      # Anthropic 语境下与 tool_calls 同义，两套协议字段名不同故都保留
    structured_outputs: bool = False

    # Thinking / reasoning 相关
    adaptive_thinking: bool = False
    min_thinking_budget: int | None = None
    max_thinking_budget: int | None = None
    reasoning_effort: list[str] | None = None  # 支持的 effort 档位，如 ["low", "medium", "high"]

    # 高级工具能力
    tool_search: bool | None = None            # None = 元数据未声明，回退 anthropic-compat.md 的 default-allow 判定
    context_editing: bool | None = None        # 同上，当前 Copilot 目录恒为 None

class ModelLimits(BaseModel):
    max_context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    max_prompt_tokens: int | None = None
    max_non_streaming_output_tokens: int | None = None
    max_inputs: int | None = None
    vision: VisionLimits | None = None

class VisionLimits(BaseModel):
    max_prompt_image_size: int | None = None
    max_prompt_images: int | None = None
    supported_media_types: list[str] | None = None

class ModelCapabilities(BaseModel):
    family: str = ""                   # "opus" | "sonnet" | "haiku" | "gpt-4o" | "gemini" | ...
    type: str = "chat"                 # "chat" | "embedding"
    tokenizer: str | None = None
    limits: ModelLimits | None = None
    supports: ModelSupports | None = None

class ModelBilling(BaseModel):
    is_premium: bool = False
    multiplier: float = 1.0
    restricted_to: list[str] | None = None

class ModelInfo(BaseModel):
    """模型信息（从上游 `/models` 目录获取，缓存并索引，见 model-resolution.md）。"""
    id: str
    name: str = ""
    vendor: str = ""                   # "Anthropic" | "OpenAI" | "Google" | ...
    version: str = ""
    object: str = "model"
    preview: bool = False
    model_picker_enabled: bool = True
    is_chat_default: bool = False
    is_chat_fallback: bool = False
    supported_endpoints: list[str] = Field(default_factory=list)   # 如 ["/chat/completions", "/v1/messages"]
    capabilities: ModelCapabilities | None = None
    billing: ModelBilling | None = None
    request_headers: dict[str, str] | None = None   # 模型级请求头，转发规则见 authentication.md
    policy: dict | None = None
```

---

## 通用模型 (`models/common.py`)

```python
class Usage(BaseModel):
    """统一 token 使用量（跨格式：OpenAI Chat/Responses、Anthropic Messages、Gemini）。"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_anthropic(cls, data: dict) -> "Usage":
        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=data.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=data.get("cache_read_input_tokens", 0),
            # Anthropic Messages API 目前不区分 reasoning tokens——thinking 内容计入 output_tokens
            reasoning_tokens=0,
            total_tokens=input_tokens + output_tokens,
        )

    @classmethod
    def from_openai(cls, data: dict) -> "Usage":
        """兼容 Chat Completions（`prompt_tokens`/`completion_tokens`）与
        Responses API（`input_tokens`/`output_tokens`），并提取
        `completion_tokens_details.reasoning_tokens` / `output_tokens_details.reasoning_tokens`。
        """
        input_tokens = data.get("prompt_tokens", data.get("input_tokens", 0))
        output_tokens = data.get("completion_tokens", data.get("output_tokens", 0))
        details = data.get("completion_tokens_details") or data.get("output_tokens_details") or {}
        reasoning_tokens = details.get("reasoning_tokens", 0)
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=data.get("total_tokens", input_tokens + output_tokens),
        )

    @classmethod
    def from_gemini(cls, data: dict) -> "Usage":
        """从 Gemini `usageMetadata`（`UsageMetadata`，见上文 Gemini 模型）转换。
        Gemini 用 `thoughtsTokenCount` 对应 reasoning tokens，`promptTokenCount`/
        `candidatesTokenCount` 对应 input/output。
        """
        prompt_tokens = data.get("prompt_token_count", 0)
        candidates_tokens = data.get("candidates_token_count", 0)
        reasoning_tokens = data.get("thoughts_token_count", 0)
        return cls(
            input_tokens=prompt_tokens,
            output_tokens=candidates_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=data.get("total_token_count", prompt_tokens + candidates_tokens + reasoning_tokens),
        )

class ErrorResponse(BaseModel):
    """统一错误响应（内部规范形状；对外根据 wire format 转译为 OpenAI/Anthropic/Gemini 各自的错误信封，
    见 multi-protocol.md 的 `detect_error_wire_format`）。"""
    error: ErrorDetail

class ErrorDetail(BaseModel):
    type: str
    message: str
    code: str | None = None
```

`reasoning_tokens` 的统一提取使可观测性层（见 [telemetry-observability.md](telemetry-observability.md)）与历史记录层（见下文 `HistoryEntry.usage`）在跨协议场景下用同一份字段名做统计与展示，不必对每种上游格式各写一套 reasoning token 提取逻辑。

---

## 内部数据模型

内部模型（管道上下文、历史记录、审批状态）**不使用 Pydantic**，而是 `dataclass`。理由：这些结构只在进程内部流转（不接受外部输入、不需要运行时校验），Pydantic 模型的实例化开销（即便是 Rust 核心）仍高于纯 `dataclass`——每个请求都会创建若干个这类实例（`RequestContext`、多个 `Attempt`、`HistoryEntry`），在高 QPS 下这部分开销会累积。这一选择呼应 [DESIGN.md](DESIGN.md#性能设计原则第一优先级) 的通用取向"热路径避免不必要的模型重建"。

### 管道上下文（`pipeline/context.py`）

见 [请求执行管道](request-pipeline.md) 中的 `RequestContext`、`Attempt`、`SanitizationResult`、`PipelineResult`。

### 历史记录（`history/types.py`）

见 [历史与审计](history-system.md) 中的 `HistoryEntry`、`ModelRef`、`EntrySummary`、`SessionSummary`。

### 审批（`pipeline/approval.py`）

见 [手动审批系统](approval-system.md) 中的 `PendingApproval`、`ApprovalResult`。

### 错误（`errors.py`）

见 [请求执行管道](request-pipeline.md) 中的 `ApiError`、`classify_error`。

---

## 关于 client/upstream 双腿模型：本项目的简化 `[简化，见 BACKLOG#4]`

### 上游做法

上游参考项目（TS）的每条历史 entry 是一个重对象图：

- `clientRequest` / `clientResponse` — 面向调用方的入站/出站快照
- 每个 attempt 各自的 `upstreamRequest` / `upstreamResponse` — 重试过程中每次实际打到 Copilot 的请求/响应都独立留档
- `sseEvents` — 流式响应的逐事件原始记录
- `_index.derived` — 一组**每次读取时重算**的派生字段（如 preview 文本、耗时分解、tool 调用摘要）
- `_index.aux` — 辅助索引字段

持久化按**多 stage 增量写入**：eager head（请求刚到达即写一条骨架）→ 每次协议转换后追加 → 每个 attempt 完成后追加 → 终态 finalize 时再写一次。旧版本的 entry 结构（"legacy stage"）在读取时还需要做兼容适配。

### 性能问题（对应 [DESIGN.md](DESIGN.md) P7）

- **每请求重对象图**：即使是简单的一次成功请求（零重试），也要维护 client 腿 + upstream 腿两套并行结构。
- **多次投影重算**：`_index.derived` 类字段没有在写入时算好存住，而是每次读取（列表/详情/WebSocket 推送）都重新计算一遍——CPU 开销从"写一次"变成了"读 N 次都要付出"。
- **多 stage 增量写盘**：一次请求触发 3～5 次独立的 SQLite 写事务（eager head、转换后、每 attempt、finalize），比"终态一次写入"多出数倍 I/O。

### 本项目默认：轻量 dataclass + 惰性投影 + 终态一次写入

本项目**不复刻**双腿模型，用一组扁平、单一视角的 `dataclass` 记录请求生命周期中的关键字段，完整定义见 [history-system.md](history-system.md#数据模型)：

```python
from dataclasses import dataclass, field
from typing import Literal

EntryStatus = Literal["pending", "executing", "streaming", "completed", "failed", "aborted", "interrupted"]

@dataclass
class ModelRef:
    requested: str              # 客户端原始模型名（pre-alias）
    resolved: str                # 解析后的规范模型名

@dataclass
class AttemptSummary:
    """单次上游尝试的摘要标量，不保留完整 wire 报文。"""
    attempt_index: int
    strategy: str | None         # 触发该次重试的策略名（如 "auto_truncate"），首次尝试为 None
    status_code: int | None
    duration_ms: float
    error_message: str | None = None

@dataclass
class HistoryEntry:
    """请求/响应的**单一视角**记录——只有面向客户端的 payload，没有独立的 upstream 腿。
    重试过程的中间 upstream 请求/响应不逐条持久化，只落一份 attempts 摘要（标量列表）。
    """
    id: str                                  # 请求 ID（uuid4）
    session_id: str | None
    agent_id: str | None
    started_at: float
    ended_at: float | None

    endpoint: str                            # "openai-chat-completions" | "anthropic-messages" | ...
    status: EntryStatus

    model: ModelRef
    request_payload: dict                    # 客户端可见的入站 payload（压缩存储）
    response: dict | None                     # 客户端可见的累积响应（压缩存储）
    usage: Usage | None

    attempts: list[AttemptSummary] = field(default_factory=list)   # 摘要 list，非逐 attempt 全量对象图
    duration_ms: float | None = None
    request_bytes: int = 0
    response_bytes: int = 0
    transport: Literal["http", "websocket"] = "http"

    error_message: str | None = None
```

关键设计取舍：

1. **单一视角，非双腿**：`request_payload`/`response` 只是客户端可见的入站/出站数据，不额外维护一份"upstream 视角"的平行结构。多次重试中，每次实际打给 Copilot 的请求内容可能与 `request_payload` 不同（如 auto-truncate 改写过 payload），但这些中间态**不逐条持久化**——只在内存中的 `RequestContext.attempts`（见 [request-pipeline.md](request-pipeline.md)）里保留用于当次请求处理，终态时压缩为 `attempts: list[AttemptSummary]` 标量列表写入 entry。
2. **终态一次性写入，非多 stage**：整个请求生命周期只有一次异步落盘（见 [history-system.md](history-system.md) 的 off-loop writer 设计）——不做 eager head、不做逐 attempt 追加。进行中的状态完全留在内存 in-flight 映射中供 WebSocket 实时推送，不依赖数据库的中间态行来反映"请求正在处理"。
3. **惰性投影，非预算全部派生字段**：`EntrySummary.preview_text` 这类展示用字段在终态写入时**惰性生成一次**（截断固定长度），而非像上游那样每次读取都重新计算。列表/详情/WebSocket 消费的是同一份预算好的摘要，不重复付出计算成本。

### 可选实现路径

若未来确有需求做完整的逐 attempt 审计（如合规要求保留每次上游交互的完整报文），走一个显式的"详细模式"开关：在该模式下额外记录每个 attempt 的完整 upstream request/response（仍然只在终态一次性写入，不做多 stage 增量），而不是默认启用这种重量级记录。默认关闭，理由与 [BACKLOG#4](BACKLOG.md#4-clientupstream-双腿数据模型--多-stage-持久化-简化) 一致。

## 相关文档

- [设计文档总纲](DESIGN.md)（性能设计原则 P7，双腿模型简化的整体动机）
- [配置系统](config-system.md)（`AppSettings` 模型）
- [请求执行管道](request-pipeline.md)（管道上下文模型：`RequestContext`、`Attempt`）
- [历史与审计](history-system.md)（历史记录模型：`HistoryEntry`、`EntrySummary`、`SessionSummary`，含完整性能重设计说明）
- [模型解析](model-resolution.md)（`ModelInfo`/`ModelCapabilities` 在解析与端点决策中的用法）
- [多协议适配](multi-protocol.md)（Gemini 请求/响应转换如何使用 `models/gemini.py`）
- [BACKLOG](BACKLOG.md#4-clientupstream-双腿数据模型--多-stage-持久化-简化)（双腿模型简化的完整记录）
