from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from app.anthropic.request_preparation import prepare_anthropic_request
from app.anthropic.sanitize import SanitizationResult, sanitize_messages
from app.anthropic.thinking.quarantine import ThinkingQuarantineStore
from app.config.settings import AppSettings
from app.hooks.executor import HooksExecutor
from app.models.anthropic import MessagesRequest
from app.transform.model_resolver import ModelResolver

if TYPE_CHECKING:
    from app.history.consumer import HistoryConsumer
    from app.pipeline.approval import ApprovalGate
    from app.pipeline.context import RequestContext
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
        approval_gate: ApprovalGate | None = None,
        hooks: HooksExecutor | None = None,
    ) -> None:
        self._target = target
        self._resolver = resolver
        self._settings = settings or AppSettings()
        self.quarantine = quarantine
        self.history = history
        self.approval_gate = approval_gate
        self.hooks = hooks

    def resolve_model(self, model: str) -> str:
        return self._resolver.resolve(model)

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def prepare_payload(
        self,
        request: MessagesRequest,
        *,
        resolved_model: str,
        sanitization: SanitizationResult,
        payload: dict[str, Any],
        apply_payload_rewrites: bool,
    ) -> PreparedAnthropicRequest:
        deeply_prepared = prepare_anthropic_request(
            payload,
            tool_search=self._settings.anthropic.tool_search,
            non_deferred_tools=tuple(
                self._settings.anthropic.tool_search_non_deferred
            ),
            apply_payload_rewrites=apply_payload_rewrites,
        )
        return PreparedAnthropicRequest(
            original_model=request.model,
            resolved_model=resolved_model,
            sanitization=sanitization,
            wire=deeply_prepared.wire,
            headers=deeply_prepared.headers,
        )

    def prepare(self, request: MessagesRequest) -> PreparedAnthropicRequest:
        resolved_model = self.resolve_model(request.model)
        sanitization = sanitize_messages(request.messages, request.tools or [])
        wire = request.model_dump(mode="json", exclude_unset=True)
        wire["model"] = resolved_model
        wire["messages"] = [
            message.model_dump(mode="json", exclude_unset=True)
            for message in sanitization.messages
        ]
        return self.prepare_payload(
            request,
            resolved_model=resolved_model,
            sanitization=sanitization,
            payload=wire,
            apply_payload_rewrites=True,
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

    async def observe_stream_finalized(
        self,
        request: MessagesRequest,
        context: RequestContext,
        *,
        usage: Mapping[str, int],
        completed: bool,
    ) -> None:
        if self.hooks is None:
            return
        from app.hooks.context import HookContext
        from app.hooks.types import ObserverEvent

        hook_context = HookContext(
            request_id=context.id,
            endpoint=context.endpoint,
            protocol="anthropic",
            original_model=context.original_model,
            resolved_model=context.resolved_model,
            session_id=context.session_id,
            agent_id=context.agent_id,
            attempt_number=max(len(context.attempts) - 1, 0),
            settings=self._settings,
        )
        if completed:
            await self.hooks.observe(
                ObserverEvent.RESPONSE,
                hook_context,
                {"request": request, "usage": dict(usage), "status_code": 200},
                records=context.hook_records,
            )
        await self.hooks.observe(
            ObserverEvent.FINALIZE,
            hook_context,
            {"request": request, "state": "completed" if completed else "failed"},
            records=context.hook_records,
        )