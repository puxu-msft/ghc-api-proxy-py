from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from app.anthropic.sanitize import SanitizationResult, sanitize_messages
from app.models.anthropic import MessagesRequest
from app.transform.model_resolver import ModelResolver

if TYPE_CHECKING:
    from app.pipeline.executor import PipelineResult


class AnthropicTarget(Protocol):
    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class PreparedAnthropicRequest:
    original_model: str
    resolved_model: str
    sanitization: SanitizationResult
    wire: dict[str, Any]


class AnthropicClient:
    def __init__(self, target: AnthropicTarget, resolver: ModelResolver) -> None:
        self._target = target
        self._resolver = resolver

    def prepare(self, request: MessagesRequest) -> PreparedAnthropicRequest:
        resolved_model = self._resolver.resolve(request.model)
        sanitization = sanitize_messages(request.messages, request.tools or [])
        wire = request.model_dump(mode="json", exclude_none=True)
        wire["model"] = resolved_model
        wire["messages"] = [
            message.model_dump(mode="json", exclude_none=True)
            for message in sanitization.messages
        ]
        return PreparedAnthropicRequest(
            original_model=request.model,
            resolved_model=resolved_model,
            sanitization=sanitization,
            wire=wire,
        )

    async def send_messages(
        self,
        request: MessagesRequest,
    ) -> tuple[httpx.Response, PreparedAnthropicRequest]:
        prepared = self.prepare(request)
        response = await self.send_prepared(prepared, stream=request.stream)
        return response, prepared

    async def send_prepared(
        self,
        prepared: PreparedAnthropicRequest,
        *,
        stream: bool,
    ) -> httpx.Response:
        response = await self._target.send_anthropic(
            prepared.wire,
            stream=stream,
        )
        return response

    async def execute(self, request: MessagesRequest) -> PipelineResult:
        from app.pipeline.executor import execute_anthropic_pipeline

        return await execute_anthropic_pipeline(self, request)