from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from app.hooks.context import HookContext
from app.hooks.types import ObserverEvent
from app.models.anthropic import MessagesRequest
from app.tokenization.estimators import estimate_anthropic_input
from app.tokenization.limits import parse_prompt_limit_error
from app.tokenization.state_store import TokenizationStateStore
from app.wire_json import loads


def _usage_from_data(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    usage = data.get("usage")
    if isinstance(usage, Mapping):
        return cast(Mapping[str, Any], usage)
    body = data.get("response_body")
    if not isinstance(body, bytes):
        return None
    try:
        value = loads(body)
    except ValueError:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("usage"), dict):
        return None
    return cast(dict[str, Any], value["usage"])


def _request_from_data(data: Mapping[str, Any]) -> MessagesRequest | None:
    request = data.get("request")
    return request if isinstance(request, MessagesRequest) else None


@dataclass(frozen=True, slots=True)
class TokenCalibrationSuccessObserver:
    state: TokenizationStateStore
    name: str = "builtin:token_calibration_success"
    order: int = 100
    events: frozenset[ObserverEvent] = frozenset({ObserverEvent.RESPONSE})

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        del event, context
        request = _request_from_data(data)
        usage = _usage_from_data(data)
        if request is None or usage is None:
            return
        real = sum(
            value
            for field in (
                "input_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
            if isinstance((value := usage.get(field)), int)
        )
        if real <= 0:
            return
        estimate = estimate_anthropic_input(request)
        self.state.calibration.learn("anthropic", request.model, estimate, real)


@dataclass(frozen=True, slots=True)
class TokenCalibrationFailureObserver:
    state: TokenizationStateStore
    name: str = "builtin:token_calibration_failure"
    order: int = 200
    events: frozenset[ObserverEvent] = frozenset({ObserverEvent.ERROR})

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        del event
        request = _request_from_data(data)
        body = data.get("response_body")
        status_code = data.get("status_code")
        if request is None or not isinstance(body, bytes) or status_code != 400:
            return
        parsed = parse_prompt_limit_error(body.decode(errors="replace"))
        if parsed is None:
            return
        current, limit = parsed
        self.state.prompt_limits.record(
            "anthropic",
            request.model,
            current=current,
            limit=limit,
            source="anthropic_messages_error",
        )
        estimate = estimate_anthropic_input(request)
        self.state.calibration.learn("anthropic", request.model, estimate, current)
