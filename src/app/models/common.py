from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.capabilities import ModelCapabilities

if TYPE_CHECKING:
    from app.errors import ApiError


class WireModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Usage(WireModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @model_validator(mode="after")
    def populate_total_tokens(self) -> Usage:
        if self.total_tokens == 0:
            object.__setattr__(self, "total_tokens", self.input_tokens + self.output_tokens)
        return self


class ModelInfo(WireModel):
    id: str
    name: str | None = None
    object: str = "model"
    vendor: str | None = None
    version: str | None = None
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)


class ErrorDetail(WireModel):
    type: str
    message: str
    code: str | None = None
    request_id: str | None = None


class ErrorResponse(WireModel):
    error: ErrorDetail

    @classmethod
    def from_api_error(cls, error: ApiError) -> ErrorResponse:
        return cls(
            error=ErrorDetail(
                type=error.wire_type,
                message=error.message,
                code=error.code,
                request_id=error.request_id,
            )
        )


JsonObject = dict[str, Any]