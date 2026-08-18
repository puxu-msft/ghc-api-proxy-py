from pydantic import BaseModel, ConfigDict, Field


class CapabilityModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ModelSupports(CapabilityModel):
    streaming: bool = True
    vision: bool = False
    tool_calls: bool = False
    parallel_tool_calls: bool = False
    tool_use: bool = True
    structured_outputs: bool = False
    adaptive_thinking: bool = False
    min_thinking_budget: int | None = None
    max_thinking_budget: int | None = None
    reasoning_effort: list[str] | None = None
    tool_search: bool | None = None
    context_editing: bool | None = None


class VisionLimits(CapabilityModel):
    max_prompt_image_size: int | None = None
    max_prompt_images: int | None = None


class ModelLimits(CapabilityModel):
    max_context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    max_prompt_tokens: int | None = None
    max_non_streaming_output_tokens: int | None = None
    max_inputs: int | None = None
    vision: VisionLimits | None = None


class ModelCapabilities(CapabilityModel):
    supports: ModelSupports = Field(default_factory=ModelSupports)
    limits: ModelLimits = Field(default_factory=ModelLimits)
