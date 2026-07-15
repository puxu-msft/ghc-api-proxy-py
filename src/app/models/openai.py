from typing import Any

from pydantic import BaseModel, ConfigDict


class OpenAIWireModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContentPart(OpenAIWireModel):
    type: str
    text: str | None = None
    image_url: dict[str, Any] | None = None


class FunctionCall(OpenAIWireModel):
    name: str
    arguments: str


class ToolCall(OpenAIWireModel):
    id: str
    type: str = "function"
    function: FunctionCall


class ChatMessage(OpenAIWireModel):
    role: str
    content: str | list[ContentPart] | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(OpenAIWireModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    n: int = 1
    stop: str | list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    seed: int | None = None


class ResponsesInputItem(OpenAIWireModel):
    type: str
    role: str | None = None
    content: str | list[dict[str, Any]] | None = None
    id: str | None = None
    call_id: str | None = None
    name: str | None = None
    arguments: str | None = None
    output: str | None = None


class ResponsesRequest(OpenAIWireModel):
    model: str
    input: str | list[ResponsesInputItem]
    instructions: str | None = None
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    previous_response_id: str | None = None


class EmbeddingsRequest(OpenAIWireModel):
    model: str
    input: str | list[str] | list[int] | list[list[int]]
    encoding_format: str | None = None
    dimensions: int | None = None
    user: str | None = None