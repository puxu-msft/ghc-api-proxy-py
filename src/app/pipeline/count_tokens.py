"""Anthropic token counting through a provider chain.

`inbound.anthropic_count_tokens.providers` names the order to try.
`ghc` asks upstream; `local` uses the calibrated estimate.
A provider that fails hands over to the next, so a transient problem degrades to an estimate.

`max_retries` applies per provider, not to the chain.
One flaky provider therefore cannot consume the attempts the next one would have had.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.config.schema import CountTokensProvider

type UpstreamCounter = Callable[[Mapping[str, Any]], Awaitable[int]]
type LocalCounter = Callable[[Mapping[str, Any]], int]


class CountTokensUnavailable(RuntimeError):
    """Every configured provider failed."""

    def __init__(self, attempts: Sequence[str]) -> None:
        super().__init__(f"no token counter succeeded: {', '.join(attempts)}")
        self.attempts = tuple(attempts)


@dataclass(frozen=True, slots=True)
class CountTokensResult:
    tokens: int
    provider: CountTokensProvider
    attempts: tuple[str, ...] = ()


async def count_tokens(
    payload: Mapping[str, Any],
    *,
    providers: Sequence[CountTokensProvider],
    max_retries: int,
    upstream: UpstreamCounter | None = None,
    local: LocalCounter | None = None,
) -> CountTokensResult:
    """Try each provider in order, retrying within one before moving on."""
    attempts: list[str] = []
    for provider in providers:
        for attempt in range(max_retries + 1):
            try:
                if provider == "ghc":
                    if upstream is None:
                        attempts.append("ghc:unconfigured")
                        break
                    return CountTokensResult(
                        tokens=await upstream(payload),
                        provider=provider,
                        attempts=tuple(attempts),
                    )
                if local is None:
                    attempts.append("local:unconfigured")
                    break
                return CountTokensResult(
                    tokens=local(payload),
                    provider=provider,
                    attempts=tuple(attempts),
                )
            except Exception as error:
                attempts.append(f"{provider}:{attempt}:{type(error).__name__}")
    raise CountTokensUnavailable(attempts)
