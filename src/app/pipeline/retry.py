"""Named retry strategies, per `upstream_request_retry.strategies`.

Each reason draws on its own counter and on the shared `max_total`.
One flapping cause therefore cannot consume the whole budget and starve the others.

A retry here is only ever a replay. Once the client holds a complete block there is nothing left for this module to fund: carrying on from what was already delivered is the client's own next request, and it arrives as one. Ruled 2026-08-21 — see `docs/.human-controlled/upstream-retry-and-continuation.md`, and `.dev/docs/upstream/retry-and-continuation/archive-proxy-side-continuation/` for the design that was replaced and which of its findings survived.
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
        # A subscriber asking for another attempt is not an upstream failure, and it used to draw on a counter of its own. It does not need one: the reasons here exist so that one flapping cause cannot starve the others, and a mechanism with no production caller cannot flap. `network` is where anything transient and statusless already goes.
        return RetryReason.NETWORK
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
        return strategies.serverError.max_retries

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


class StreamEnding(StrEnum):
    """What to do about a stream that stopped, decided from what we received."""

    COMPLETE = "complete"
    REPLAY = "replay"
    ABANDON = "abandon"


@dataclass(frozen=True, slots=True)
class EndingVerdict:
    ending: StreamEnding
    reason: RetryReason | None = None
    detail: str = ""


def decide_stream_ending(
    *,
    terminal_seen: bool,
    downstream_opened: bool,
    committed_blocks: int,
    ledger: RetryLedger,
    reason: RetryReason,
) -> EndingVerdict:
    """Choose between finishing, replaying and giving up.

    Decided from what this side received and delivered, and from nothing else. Who sent the GOAWAY, and why, is not observable from here — our stack stops reading the moment the frame arrives — so a rule written in terms of the peer's intent would be a rule written about something we cannot see. Ruled 2026-08-20; see `.dev/docs/upstream/h2-goaway/findings.md`.

    The exception type is deliberately not an input. A clean EOF with no terminal event and a torn connection leave the client in the same place, and it is that place — not the manner of arrival — that decides what may legally happen next.

    Three outcomes, and only one of them starts another attempt: a stream that may not be replayed still has to end, and telling the client it was truncated is that ending. This function used to name a fourth, carrying on from the committed blocks, which was ruled out on 2026-08-21 — what happens after the client already holds content is now the client's own next request, and nothing this function decides.

    `downstream_opened` means a semantic event has already gone out — a `message_start`, whether it came with the first block or was synthesised during a long silence. Keep-alive comments do not count; they carry nothing a client stores.

    Budget is spent here, not merely consulted: choosing to replay is what consumes an attempt. A caller that decides twice for one stream would otherwise be funded twice. It is spent under the reason the failure itself draws on, passed in by the caller — a torn body is a network failure at a later instant than a torn connection, not a different kind of thing, and it used to have a counter of its own for no better reason than that the design it came from paired it with a proxy-side continuation. That pairing is gone.
    """
    if terminal_seen:
        return EndingVerdict(StreamEnding.COMPLETE)

    if not downstream_opened:
        # Nothing the client can see, so the second attempt can stand in for the first with no trace. This is the only place a transparent replay is legal.
        verdict = ledger.take(reason)
        if verdict.allowed:
            return EndingVerdict(StreamEnding.REPLAY, reason)
        return EndingVerdict(StreamEnding.ABANDON, reason, verdict.detail)

    if committed_blocks == 0:
        # Opened but empty: the client holds a `message_start` and no content. A replay would send it a second one, so the only ending left is to say the stream was truncated. Kept apart from the case below because the two leave the client holding different things, and the detail is what a reader sees.
        return EndingVerdict(
            StreamEnding.ABANDON,
            detail="response opened without a content block",
        )

    # The client holds content. Nothing here can replace it, and asking upstream to carry on is no longer this side's job.
    return EndingVerdict(
        StreamEnding.ABANDON,
        detail="response opened with content already delivered",
    )
