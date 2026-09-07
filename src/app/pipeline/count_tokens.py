"""Anthropic token counting through the routed upstream and local fallback.

The current route decides which upstream may answer. That upstream is tried
first when it owns the native counter; a local calibrated estimate follows when
the protocol has no upstream counter or the upstream cannot answer.

`max_retries` applies per provider, not to the chain.
One flaky provider therefore cannot consume the attempts the next one would have had.

A refusal is not a failure. A provider that will not serve this model at all is not going to serve it on the next attempt either, and answering with an estimate instead would report a count for a model the caller can never reach — so `ProviderError` travels out rather than being handed on.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.config.schema import LOCAL_COUNTER
from app.model_provider import EndpointNotImplemented, ProviderError

type UpstreamCounter = Callable[[Mapping[str, Any]], Awaitable[int]]
type LocalCounter = Callable[[Mapping[str, Any]], int]


class CountTokensRequestError(ValueError):
    """The body cannot be read as an Anthropic Messages request, so there is nothing to count.

    Defined here rather than in `driver`, where it was until 2026-08-23, because it is about counting and because `app.pipeline.error_classify` has to name it. Classifying it from `driver` would pull the whole request pipeline into a module whose job is to answer "what kind of failure is this" — and that module is imported by the HTTP edge on every failure.
    """


class CountTokensUnavailable(RuntimeError):
    """The routed upstream and local estimator both failed.

    `cause` is the last counter's failure. It travels because without it this
    exception flattens every reason into one.

    `attempts` stays as the human-readable trail of everything that was tried.
    `cause` is what anything downstream classifies from.
    """

    def __init__(self, attempts: Sequence[str], *, cause: BaseException | None = None) -> None:
        super().__init__(f"no token counter succeeded: {', '.join(attempts)}")
        self.attempts = tuple(attempts)
        self.cause = cause


@dataclass(frozen=True, slots=True)
class CountTokensResult:
    tokens: int
    provider: str
    attempts: tuple[str, ...] = ()


async def count_tokens(
    payload: Mapping[str, Any],
    *,
    providers: Sequence[str],
    max_retries: int,
    upstream: UpstreamCounter | None = None,
    local: LocalCounter | None = None,
    upstream_absent_reason: str = "unconfigured",
) -> CountTokensResult:
    """Try the routed upstream and then the local estimator.

    `upstream_absent_reason` names *why* there is no upstream counter, for the attempts trail. It defaults to the historical answer — nobody supplied one — but a caller that withheld it deliberately should say so, because `ghc:unconfigured` read against a config file that plainly lists `ghc` sends the next reader looking for a settings bug that is not there.
    """
    attempts: list[str] = []
    # The failure the last counter raised, kept so `CountTokensUnavailable` can carry it. Only the last one: the trail in `attempts` records that the earlier ones happened, and a client is owed one verdict rather than a list it cannot act on.
    last_failure: BaseException | None = None
    for provider in providers:
        for attempt in range(max_retries + 1):
            try:
                if provider != LOCAL_COUNTER:
                    if upstream is None:
                        attempts.append(f"{provider}:{upstream_absent_reason}")
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
            except EndpointNotImplemented as error:
                last_failure = error
                attempts.append(f"{provider}:unavailable")
                break
            except ProviderError:
                # Unserviceable, not unlucky: retrying or degrading would both answer the wrong question. The caller turns this into a 400.
                raise
            except Exception as error:
                last_failure = error
                attempts.append(f"{provider}:{attempt}:{type(error).__name__}")
    raise CountTokensUnavailable(attempts, cause=last_failure)
