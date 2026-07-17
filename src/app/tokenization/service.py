from collections.abc import Mapping
from typing import Any, Protocol

import httpx
from anyio.to_thread import run_sync

from app.models.anthropic import MessagesRequest
from app.tokenization.estimators import estimate_anthropic_input
from app.tokenization.limits import parse_prompt_limit_error
from app.tokenization.state_store import TokenizationStateStore
from app.wire_json import dumps


class AnthropicCountTokensTarget(Protocol):
    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response: ...


class AnthropicTokenCountingService:
    def __init__(
        self,
        target: AnthropicCountTokensTarget,
        state: TokenizationStateStore,
        *,
        use_upstream: bool = True,
        offload_threshold_bytes: int = 100_000,
    ) -> None:
        self._target = target
        self._state = state
        self._use_upstream = use_upstream
        self._offload_threshold = offload_threshold_bytes

    async def _estimate(self, request: MessagesRequest) -> int:
        wire_size = len(dumps(request.model_dump(mode="json", exclude_none=True)))
        if wire_size >= self._offload_threshold:
            return await run_sync(estimate_anthropic_input, request)
        return estimate_anthropic_input(request)

    async def count(self, request: MessagesRequest) -> dict[str, Any]:
        estimate = await self._estimate(request)
        if self._use_upstream:
            payload = request.model_dump(mode="json", exclude_none=True)
            payload.pop("stream", None)
            response: httpx.Response | None = None
            try:
                response = await self._target.send_anthropic_count_tokens(payload)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                input_tokens = data.get("input_tokens")
                if not isinstance(input_tokens, int) or input_tokens <= 0:
                    raise ValueError("upstream count_tokens response has no positive input_tokens")
                self._state.calibration.learn(
                    "anthropic",
                    request.model,
                    estimate,
                    input_tokens,
                )
                return data
            except (httpx.HTTPError, OSError, ValueError):
                if response is not None and response.status_code >= 400:
                    raw = (await response.aread()).decode(errors="replace")
                    parsed = parse_prompt_limit_error(raw)
                    if parsed is not None:
                        current, limit = parsed
                        self._state.prompt_limits.record(
                            "anthropic",
                            request.model,
                            current=current,
                            limit=limit,
                            source="anthropic_count_tokens_error",
                        )
                        self._state.calibration.learn(
                            "anthropic",
                            request.model,
                            estimate,
                            current,
                        )
            finally:
                if response is not None:
                    await response.aclose()
        calibrated = self._state.calibration.calibrate(
            "anthropic",
            request.model,
            estimate,
        )
        return {"input_tokens": calibrated, "estimated": True}
