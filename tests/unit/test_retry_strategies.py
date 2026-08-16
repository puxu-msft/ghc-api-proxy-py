import pytest

from app.config.schema import UpstreamRequestRetryConfig
from app.pipeline.exceptions import (
    PipelineAbort,
    PipelineRetry,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamTimeout,
)
from app.pipeline.retry import (
    RetryLedger,
    RetryReason,
    continuation_messages,
    reason_for,
)


def config(**overrides: object) -> UpstreamRequestRetryConfig:
    return UpstreamRequestRetryConfig.model_validate(overrides)


def test_defaults_match_the_spec() -> None:
    ledger = RetryLedger(config())
    assert ledger.limit_for(RetryReason.GITHUB_TOKEN_EXPIRED) == 0
    assert ledger.limit_for(RetryReason.NETWORK) == 9
    assert ledger.limit_for(RetryReason.SERVER_ERROR) == 9
    assert ledger.limit_for(RetryReason.STREAM_REPLAY) == 100
    assert ledger.limit_for(RetryReason.CONTINUATION) == 10


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UpstreamTimeout("slow"), RetryReason.NETWORK),
        (UpstreamRateLimit("429"), RetryReason.SERVER_ERROR),
        (PipelineRetry("again"), RetryReason.STREAM_REPLAY),
        (UpstreamError("gone", status_code=401), RetryReason.GITHUB_TOKEN_EXPIRED),
        (UpstreamError("boom", status_code=503), RetryReason.SERVER_ERROR),
        (UpstreamError("no status"), RetryReason.NETWORK),
    ],
)
def test_failures_are_named_by_reason(error: Exception, expected: RetryReason) -> None:
    assert reason_for(error) is expected


@pytest.mark.parametrize("error", [PipelineAbort("stop"), KeyError("bug"), ValueError("v")])
def test_non_retryable_failures_have_no_reason(error: Exception) -> None:
    # An abort and an unknown exception are both terminal, so neither names a retry strategy.
    assert reason_for(error) is None


def test_one_reason_cannot_starve_another() -> None:
    # githubTokenExpired is capped at 0, which must not stop network retries from running.
    ledger = RetryLedger(config())
    assert ledger.take(RetryReason.GITHUB_TOKEN_EXPIRED).allowed is False
    assert ledger.take(RetryReason.NETWORK).allowed is True


def test_per_reason_limit_is_enforced() -> None:
    ledger = RetryLedger(config(strategies={"network": {"max_retries": 2}}))
    assert ledger.take(RetryReason.NETWORK).allowed is True
    assert ledger.take(RetryReason.NETWORK).allowed is True
    verdict = ledger.take(RetryReason.NETWORK)
    assert verdict.allowed is False
    assert "network" in verdict.detail


def test_shared_total_bounds_every_reason_together() -> None:
    ledger = RetryLedger(config(max_total=3))
    for _ in range(3):
        assert ledger.take(RetryReason.NETWORK).allowed is True
    verdict = ledger.take(RetryReason.SERVER_ERROR)
    assert verdict.allowed is False
    assert "total" in verdict.detail


def test_refused_attempt_spends_nothing() -> None:
    ledger = RetryLedger(config(max_total=1))
    ledger.take(RetryReason.NETWORK)
    before = ledger.total_spent
    ledger.take(RetryReason.SERVER_ERROR)
    assert ledger.total_spent == before
    assert ledger.spent(RetryReason.SERVER_ERROR) == 0


def test_consider_does_not_spend() -> None:
    ledger = RetryLedger(config())
    assert ledger.consider(RetryReason.NETWORK).allowed is True
    assert ledger.total_spent == 0


def test_disabled_continuation_has_no_budget() -> None:
    ledger = RetryLedger(config(strategies={"continuation": {"enabled": False}}))
    assert ledger.limit_for(RetryReason.CONTINUATION) == 0
    assert ledger.take(RetryReason.CONTINUATION).allowed is False


def test_continuation_sends_the_committed_blocks_as_an_assistant_turn() -> None:
    # Continuation is not a replay: the client keeps what it saw, and the model carries on.
    committed: list[dict[str, object]] = [{"type": "text", "text": "first half"}]
    messages = continuation_messages(committed, config())
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"] == committed
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Please continue where you left off."


def test_continuation_message_is_configurable() -> None:
    messages = continuation_messages([], config(strategies={"continuation": {"message": "go on"}}))
    assert messages[1]["content"] == "go on"
