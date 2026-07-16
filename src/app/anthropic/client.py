from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from app.anthropic.request_preparation import prepare_anthropic_request
from app.anthropic.sanitize import SanitizationResult, sanitize_messages
from app.anthropic.thinking.quarantine import ThinkingQuarantineStore
from app.config.settings import AppSettings
from app.models.anthropic import MessagesRequest
from app.transform.model_resolver import ModelResolver

if TYPE_CHECKING:
    from app.history.consumer import HistoryConsumer
    from app.pipeline.executor import PipelineResult


class AnthropicTarget(Protocol):
    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class PreparedAnthropicRequest:
    original_model: str
    resolved_model: str
    sanitization: SanitizationResult
    wire: dict[str, Any]
    headers: dict[str, str]


class AnthropicClient:
    def __init__(
        self,
        target: AnthropicTarget,
        resolver: ModelResolver,
        settings: AppSettings | None = None,
        quarantine: ThinkingQuarantineStore | None = None,
        history: HistoryConsumer | None = None,
    ) -> None:
        self._target = target
        self._resolver = resolver
        self._settings = settings or AppSettings()
        self.quarantine = quarantine
        self.history = history

    def prepare(self, request: MessagesRequest) -> PreparedAnthropicRequest:
        resolved_model = self._resolver.resolve(request.model)
        sanitization = sanitize_messages(request.messages, request.tools or [])
        wire = request.model_dump(mode="json", exclude_unset=True)
        wire["model"] = resolved_model
        wire["messages"] = [
            message.model_dump(mode="json", exclude_unset=True)
            for message in sanitization.messages
        ]
        deeply_prepared = prepare_anthropic_request(
            wire,
            tool_search=self._settings.anthropic.tool_search,
            non_deferred_tools=tuple(
                self._settings.anthropic.tool_search_non_deferred
            ),
        )
        return PreparedAnthropicRequest(
            original_model=request.model,
            resolved_model=resolved_model,
            sanitization=sanitization,
            wire=deeply_prepared.wire,
            headers=deeply_prepared.headers,
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
            extra_headers=prepared.headers,
        )
        return response

    async def execute(
        self,
        request: MessagesRequest,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> PipelineResult:
        from app.pipeline.executor import execute_anthropic_pipeline

        return await execute_anthropic_pipeline(
            self,
            request,
            session_id=session_id,
            agent_id=agent_id,
        )