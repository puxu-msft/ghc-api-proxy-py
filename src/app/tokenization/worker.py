from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import anyio
from anyio.to_process import run_sync
from pydantic import ValidationError

from app.models.anthropic import MessagesRequest
from app.observability.metrics import RESPONSIVENESS
from app.pipeline.count_tokens import CountTokensRequestError
from app.tokenization.estimators import EstimatorTiming, estimate_anthropic_input
from app.tokenization.features import analyze_responses_input
from app.tokenization.types import EstimateFeatures, TokenizationCapabilities


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    tokens: int | None
    timings: tuple[EstimatorTiming, ...]
    error: Exception | None = None
    features: EstimateFeatures | None = None


def _countable(payload: Mapping[str, Any]) -> MessagesRequest:
    # The count endpoint does not require max_tokens. This private copy is for validation/estimation only and never becomes an upstream request.
    countable = dict(payload)
    countable.setdefault("max_tokens", 1)
    try:
        return MessagesRequest.model_validate(countable)
    except ValidationError as error:
        raise CountTokensRequestError(f"not a countable Messages body: {error}") from error


def _estimate_input(
    protocol: str,
    payload: Mapping[str, Any],
    capabilities: TokenizationCapabilities | None = None,
) -> TokenEstimate:
    timings: list[EstimatorTiming] = []
    try:
        if protocol == "anthropic":
            count = estimate_anthropic_input(_countable(payload), timings=timings)
            features = None
        elif protocol == "openai-responses":
            features = analyze_responses_input(
                payload,
                capabilities=capabilities,
                timings=timings,
            )
            count = max(features.known_tokens, 1)
        else:
            raise CountTokensRequestError(f"no token estimator for {protocol}; add one before routing counts there")
    except Exception as error:
        # Return completed stage observations even on an ordinary failure. The parent records them and raises this error; a worker killed by cancellation or a process failure cannot return a final timing sample.
        return TokenEstimate(None, tuple(timings), error)
    return TokenEstimate(count, tuple(timings), features=features)


class LocalTokenWorker:
    def __init__(self, *, limiter: anyio.CapacityLimiter | None = None) -> None:
        self.limiter = limiter if limiter is not None else anyio.CapacityLimiter(1)

    async def _run(
        self,
        protocol: str,
        payload: Mapping[str, Any],
        capabilities: TokenizationCapabilities | None = None,
    ) -> TokenEstimate:
        if capabilities is None:
            result = await run_sync(
                _estimate_input,
                protocol,
                payload,
                cancellable=True,
                limiter=self.limiter,
            )
        else:
            result = await run_sync(
                _estimate_input,
                protocol,
                payload,
                capabilities,
                cancellable=True,
                limiter=self.limiter,
            )
        for sample in result.timings:
            RESPONSIVENESS.tokenizer[(sample.format, sample.phase)].observe(sample.seconds, failed=sample.failed)
        if result.error is not None:
            raise result.error
        return result

    async def estimate(self, protocol: str, payload: Mapping[str, Any]) -> int:
        result = await self._run(protocol, payload)
        if result.tokens is None:
            raise RuntimeError("token worker returned neither a count nor an error")
        return result.tokens

    async def analyze_responses(
        self,
        payload: Mapping[str, Any],
        *,
        capabilities: TokenizationCapabilities | None = None,
    ) -> EstimateFeatures:
        result = await self._run("openai-responses", payload, capabilities)
        if result.features is None:
            raise RuntimeError("Responses token worker returned no structured features")
        return result.features
