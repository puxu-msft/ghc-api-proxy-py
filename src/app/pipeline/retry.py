"""Named retry strategies, per `upstream_request_retry.strategies`.

Each reason draws on its own counter and on the shared `max_total`.
One flapping cause therefore cannot consume the whole budget and starve the others.

`continuation` is not a replay.
It appends the committed blocks as an assistant turn plus a user message asking to continue.
That is why it is allowed after commit, where a transparent replay of the generation is not.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.config.schema import UpstreamRequestRetryConfig
from app.pipeline.exceptions import (
    Disposition,
    PipelineRetry,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamTimeout,
    classify,
)


class RetryReason(StrEnum):
    GITHUB_TOKEN_EXPIRED = "githubTokenExpired"
    NETWORK = "network"
    SERVER_ERROR = "serverError"
    STREAM_REPLAY = "streamReplay"
    CONTINUATION = "continuation"


@dataclass(frozen=True, slots=True)
class RetryVerdict:
    allowed: bool
    reason: RetryReason | None = None
    detail: str = ""


def reason_for(error: BaseException, *, status_code: int | None = None) -> RetryReason | None:
    """Name the reason a failure would be retried under, or None if it would not."""
    if classify(error) is not Disposition.RETRY:
        return None
    if isinstance(error, PipelineRetry):
        return RetryReason.STREAM_REPLAY
    if isinstance(error, UpstreamTimeout):
        return RetryReason.NETWORK
    if isinstance(error, UpstreamRateLimit):
        return RetryReason.SERVER_ERROR

    code = status_code
    if code is None and isinstance(error, UpstreamError):
        code = error.status_code
    if code == 401:
        return RetryReason.GITHUB_TOKEN_EXPIRED
    if code is not None and code >= 500:
        return RetryReason.SERVER_ERROR
    if code is None:
        # No status means the failure happened before a response existed.
        return RetryReason.NETWORK
    return RetryReason.SERVER_ERROR


@dataclass(slots=True)
class RetryLedger:
    """Spends the shared budget and the per-reason ones together."""

    config: UpstreamRequestRetryConfig
    total_spent: int = 0
    per_reason: dict[RetryReason, int] = field(
        default_factory=lambda: dict[RetryReason, int]()
    )

    def limit_for(self, reason: RetryReason) -> int:
        strategies = self.config.strategies
        if reason is RetryReason.GITHUB_TOKEN_EXPIRED:
            return strategies.githubTokenExpired.max_retries
        if reason is RetryReason.NETWORK:
            return strategies.network.max_retries
        if reason is RetryReason.SERVER_ERROR:
            return strategies.serverError.max_retries
        if reason is RetryReason.STREAM_REPLAY:
            return strategies.streamReplay.max_retries
        if not strategies.continuation.enabled:
            return 0
        return strategies.continuation.max_retries

    def spent(self, reason: RetryReason) -> int:
        return self.per_reason.get(reason, 0)

    def consider(self, reason: RetryReason) -> RetryVerdict:
        """Ask whether one more attempt is funded, without spending anything."""
        if self.total_spent >= self.config.max_total:
            return RetryVerdict(False, reason, "total retry budget exhausted")
        limit = self.limit_for(reason)
        if self.spent(reason) >= limit:
            return RetryVerdict(False, reason, f"{reason.value} budget exhausted")
        return RetryVerdict(True, reason)

    def take(self, reason: RetryReason) -> RetryVerdict:
        verdict = self.consider(reason)
        if verdict.allowed:
            self.total_spent += 1
            self.per_reason[reason] = self.spent(reason) + 1
        return verdict


def continuation_messages(
    committed: list[dict[str, object]],
    config: UpstreamRequestRetryConfig,
) -> list[dict[str, object]]:
    """Build the turns that ask the model to carry on from what the client already saw.

    The committed blocks become the assistant turn.
    The model continues rather than repeating what the client already has.
    """
    return [
        {"role": "assistant", "content": committed},
        {"role": "user", "content": config.strategies.continuation.message},
    ]
