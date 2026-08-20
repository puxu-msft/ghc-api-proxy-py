"""Anthropic token counting through a provider chain.

`inbound.anthropic_count_tokens.providers` names the order to try.
`ghc` asks upstream; `local` uses the calibrated estimate.
A provider that fails hands over to the next, so a transient problem degrades to an estimate.

`max_retries` applies per provider, not to the chain.
One flaky provider therefore cannot consume the attempts the next one would have had.

A refusal is not a failure. A provider that will not serve this model at all is not going to serve
it on the next attempt either, and answering with an estimate instead would report a count for a
model the caller can never reach — so `ProviderError` travels out rather than being handed on.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.config.schema import CountTokensProvider
from app.model_provider import ProviderError

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
    upstream_absent_reason: str = "unconfigured",
) -> CountTokensResult:
    """Try each provider in order, retrying within one before moving on.

    `upstream_absent_reason` names *why* there is no upstream counter, for the attempts trail. It defaults to the historical answer — nobody supplied one — but a caller that withheld it deliberately should say so, because `ghc:unconfigured` read against a config file that plainly configures `ghc` sends the next reader looking for a settings bug that is not there.
    """
    attempts: list[str] = []
    for provider in providers:
        for attempt in range(max_retries + 1):
            try:
                if provider == "ghc":
                    if upstream is None:
                        attempts.append(f"ghc:{upstream_absent_reason}")
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
            except ProviderError:
                # Unserviceable, not unlucky: retrying or degrading would both answer the wrong
                # question. The caller turns this into a 400.
                raise
            except Exception as error:
                attempts.append(f"{provider}:{attempt}:{type(error).__name__}")
    raise CountTokensUnavailable(attempts)
