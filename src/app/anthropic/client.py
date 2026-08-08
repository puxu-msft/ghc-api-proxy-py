from __future__ import annotations

import copy
from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

import httpx
import orjson

from app.anthropic.header_policy import normalize_responses_response_headers
from app.anthropic.request_preparation import prepare_anthropic_request
from app.anthropic.sanitize import SanitizationResult, sanitize_messages
from app.anthropic.thinking.quarantine import ThinkingQuarantineStore
from app.config.settings import AppSettings
from app.errors import ApiError, ErrorCategory
from app.hooks.executor import HooksExecutor
from app.models.anthropic import MessagesRequest
from app.models.common import ModelInfo
from app.protocols.anthropic_responses import (
    ConversionFact,
    ReasoningCapabilityFacts,
    ReasoningEffortBand,
    RequestConversionError,
    convert_messages_request_to_responses,
)
from app.protocols.responses_anthropic import (
    ConvertedResponse,
    ResponseConversionError,
    convert_responses_response_to_anthropic,
)
from app.transform.model_resolver import ModelResolver
from app.wire_json import dumps

if TYPE_CHECKING:
    from app.history.consumer import HistoryConsumer
    from app.pipeline.approval import ApprovalGate
    from app.pipeline.context import RequestContext
    from app.pipeline.executor import PipelineResult
    from app.pipeline.route_policy import RouteDecision


class AnthropicTarget(Protocol):
    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response: ...


class ResponsesTarget(Protocol):
    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response: ...


class ModelCatalogView(Protocol):
    @property
    def available_ids(self) -> Set[str]: ...

    def get(self, model_id: str) -> ModelInfo | None: ...


@dataclass(frozen=True, slots=True)
class PreparedAnthropicRequest:
    original_model: str
    resolved_model: str
    sanitization: SanitizationResult
    wire: dict[str, Any]
    headers: dict[str, str]
    route: RouteDecision | None = None


@dataclass(frozen=True, slots=True)
class AnthropicAttemptResult:
    response: httpx.Response
    converted_request_facts: tuple[ConversionFact, ...] = ()
    converted_response: ConvertedResponse | None = None


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
        model_catalog: ModelCatalogView | None = None,
    ) -> None:
        self._target = target
        self._resolver = resolver
        self._settings = settings or AppSettings()
        self.quarantine = quarantine
        self.history = history
        self.approval_gate = approval_gate
        self.hooks = hooks
        self._model_catalog = model_catalog

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
        route = self._decide_route(resolved_model)
        if route is not None and route.protocol_leg.value == "responses":
            return PreparedAnthropicRequest(
                original_model=request.model,
                resolved_model=resolved_model,
                sanitization=sanitization,
                wire=copy.deepcopy(payload),
                headers={},
                route=route,
            )
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
            route=route,
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
        result = await self.send_prepared_attempt(prepared, stream=stream)
        return result.response

    async def send_prepared_attempt(
        self,
        prepared: PreparedAnthropicRequest,
        *,
        stream: bool,
    ) -> AnthropicAttemptResult:
        if prepared.route is not None and prepared.route.protocol_leg.value == "responses":
            return await self._send_responses(prepared, stream=stream)
        response = await self._target.send_anthropic(
            prepared.wire,
            stream=stream,
            extra_headers=prepared.headers,
        )
        return AnthropicAttemptResult(response)

    def _decide_route(self, resolved_model: str) -> RouteDecision | None:
        from app.pipeline.route_policy import (
            ProtocolLeg,
            ResolvedModelFacts,
            RouteDecisionError,
            TransportAvailability,
            decide_protocol_leg,
        )

        if self._model_catalog is None:
            return None
        model = self._model_catalog.get(resolved_model)
        override_value = self._settings.anthropic.route_override
        override = None if override_value == "auto" else ProtocolLeg(override_value)
        try:
            return decide_protocol_leg(
                None
                if model is None
                else ResolvedModelFacts(
                    resolved_model=resolved_model,
                    supported_endpoints=model.supported_endpoints,
                ),
                override=override,
                transports=TransportAvailability(
                    messages_http=True,
                    responses_http=True,
                ),
            )
        except RouteDecisionError as error:
            raise ApiError(
                error.detail,
                category=ErrorCategory.CLIENT,
                status_code=400,
                code=error.code.value,
            ) from error

    async def _send_responses(
        self,
        prepared: PreparedAnthropicRequest,
        *,
        stream: bool,
    ) -> AnthropicAttemptResult:
        reasoning_capabilities = self._reasoning_capabilities(
            prepared.resolved_model
        )
        try:
            converted_request = convert_messages_request_to_responses(
                prepared.wire,
                reasoning_capabilities=reasoning_capabilities,
            )
        except RequestConversionError as error:
            raise ApiError(
                str(error),
                category=ErrorCategory.CLIENT,
                status_code=400,
                code=error.code,
            ) from error
        responses_target = cast(ResponsesTarget, self._target)
        upstream = await responses_target.send_responses_headers(
            converted_request.wire,
        )
        if not upstream.is_success:
            return AnthropicAttemptResult(
                await _responses_error_response(upstream),
                converted_request_facts=converted_request.facts,
            )
        if stream:
            return AnthropicAttemptResult(
                upstream,
                converted_request_facts=converted_request.facts,
            )
        try:
            parsed_body: object = orjson.loads(await upstream.aread())
            if not isinstance(parsed_body, dict):
                raise ApiError(
                    "Responses upstream returned a non-object JSON body",
                    category=ErrorCategory.UPSTREAM,
                    status_code=502,
                    code="invalid_responses_body",
                )
            body = cast(dict[str, Any], parsed_body)
            converted = convert_responses_response_to_anthropic(body)
            return AnthropicAttemptResult(
                response=httpx.Response(
                    upstream.status_code,
                    headers=normalize_responses_response_headers(upstream.headers),
                    content=dumps(
                        converted.message.model_dump(mode="json", exclude_none=True)
                    ),
                    request=getattr(upstream, "_request", None),
                    extensions=upstream.extensions,
                ),
                converted_request_facts=converted_request.facts,
                converted_response=converted,
            )
        except (orjson.JSONDecodeError, ResponseConversionError) as error:
            code = getattr(error, "code", "invalid_responses_body")
            raise ApiError(
                str(error) or "Responses response conversion failed",
                category=ErrorCategory.UPSTREAM,
                status_code=502,
                code=code,
            ) from error
        finally:
            await upstream.aclose()

    def _reasoning_capabilities(
        self,
        resolved_model: str,
    ) -> ReasoningCapabilityFacts | None:
        if self._model_catalog is None:
            return None
        model = self._model_catalog.get(resolved_model)
        if model is None:
            return None
        supports = model.capabilities.supports
        efforts = tuple(supports.reasoning_effort or ())
        if len(set(efforts)) != len(efforts) or any(not effort for effort in efforts):
            efforts = ()
        budget_limits_known = {
            "min_thinking_budget",
            "max_thinking_budget",
        }.issubset(supports.model_fields_set)
        selected_effort = efforts[0] if len(efforts) == 1 else None
        return ReasoningCapabilityFacts(
            supported_efforts=efforts,
            budget_limits_known=budget_limits_known,
            min_budget_tokens=supports.min_thinking_budget,
            max_budget_tokens=supports.max_thinking_budget,
            enabled_budget_bands=(
                (
                    ReasoningEffortBand(
                        max_budget_tokens=None,
                        effort=selected_effort,
                    ),
                )
                if selected_effort is not None
                else ()
            ),
            adaptive_effort=(
                selected_effort
                if supports.adaptive_thinking and "adaptive_thinking" in supports.model_fields_set
                else None
            ),
        )

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
        usage_estimated: bool = False,
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
                {
                    "request": request,
                    "usage": dict(usage),
                    "status_code": 200,
                    **({"usage_facts": {"estimated": True}} if usage_estimated else {}),
                },
                records=context.hook_records,
            )
        elif context.error is not None:
            await self.hooks.observe(
                ObserverEvent.ERROR,
                hook_context,
                {
                    "request": request,
                    "status_code": context.error.status_code,
                    "error": context.error,
                },
                records=context.hook_records,
            )
        await self.hooks.observe(
            ObserverEvent.FINALIZE,
            hook_context,
            {
                "request": request,
                "state": "completed" if completed else "failed",
                **({"error": context.error} if context.error is not None else {}),
            },
            records=context.hook_records,
        )


async def _responses_error_response(upstream: httpx.Response) -> httpx.Response:
    raw = await upstream.aread()
    message = raw.decode(errors="replace") or (
        f"Responses upstream returned HTTP {upstream.status_code}"
    )
    code: str | None = None
    try:
        parsed_value: object = orjson.loads(raw)
        if isinstance(parsed_value, dict):
            parsed = cast(dict[str, Any], parsed_value)
            error_value: object = parsed.get("error")
            if isinstance(error_value, dict):
                error = cast(dict[str, Any], error_value)
                error_message: object = error.get("message")
                error_code: object = error.get("code")
                if isinstance(error_message, str):
                    message = error_message
                if isinstance(error_code, str):
                    code = error_code
    except orjson.JSONDecodeError:
        pass
    api_error = ApiError(message, status_code=upstream.status_code, code=code)
    response = httpx.Response(
        upstream.status_code,
        headers=normalize_responses_response_headers(upstream.headers),
        content=dumps(
            {
                "type": "error",
                "error": {
                    "type": api_error.wire_type,
                    "message": api_error.message,
                    **({"code": code} if code is not None else {}),
                },
            }
        ),
        request=getattr(upstream, "_request", None),
        extensions=upstream.extensions,
    )
    await upstream.aclose()
    return response