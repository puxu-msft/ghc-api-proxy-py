from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnthropicWireModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContentBlock(AnthropicWireModel):
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    content: str | list[ContentBlock] | None = None
    is_error: bool | None = None
    thinking: str | None = None
    signature: str | None = None
    source: dict[str, Any] | None = None
    cache_control: dict[str, Any] | None = None


class AnthropicMessage(AnthropicWireModel):
    role: str
    content: str | list[ContentBlock]


class SystemBlock(AnthropicWireModel):
    type: str = "text"
    text: str
    cache_control: dict[str, Any] | None = None


class AnthropicTool(AnthropicWireModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    type: str | None = None
    cache_control: dict[str, Any] | None = None
    defer_loading: bool | None = None


class MessagesRequest(AnthropicWireModel):
    model: str
    messages: list[AnthropicMessage]
    max_tokens: int = Field(ge=1)
    system: str | list[SystemBlock] | None = None
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    tools: list[AnthropicTool] | None = None
    tool_choice: dict[str, Any] | None = None
    thinking: dict[str, Any] | None = None
    context_management: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AnthropicUsage(AnthropicWireModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class MessagesResponse(AnthropicWireModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    content: list[ContentBlock]
    model: str
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: AnthropicUsage | None = None


class MessageStreamEvent(AnthropicWireModel):
    type: str
    message: MessagesResponse | None = None
    index: int | None = None
    content_block: ContentBlock | None = None
    delta: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
