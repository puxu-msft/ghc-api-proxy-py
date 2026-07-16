from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class GeminiWireModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class Part(GeminiWireModel):
    text: str | None = None
    inline_data: dict[str, Any] | None = None
    function_call: dict[str, Any] | None = None
    function_response: dict[str, Any] | None = None
    thought: bool | None = None
    thought_signature: str | None = None


class Content(GeminiWireModel):
    role: str | None = None
    parts: list[Part] = Field(default_factory=lambda: list[Part]())


class GenerationConfig(GeminiWireModel):
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    stop_sequences: list[str] | None = None


class GenerateContentRequest(GeminiWireModel):
    contents: list[Content] = Field(default_factory=lambda: list[Content]())
    tools: list[dict[str, Any]] | None = None
    tool_config: dict[str, Any] | None = None
    system_instruction: Content | None = None
    generation_config: GenerationConfig | None = None
    cached_content: str | None = None