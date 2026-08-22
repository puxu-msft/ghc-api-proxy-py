"""What to do about a stream that stopped short, decided from what we received.

The rule these pin is the one `app/pipeline/retry.py` has stated since before anything called it: a replay is only legal while the client has seen nothing. What is left once the client has seen something used to be a proxy-side continuation; since 2026-08-21 it is the client's own next request, so from here every one of those endings is simply an ending.
"""

import pytest

from app.config.schema import UpstreamRequestRetryConfig
from app.pipeline.retry import (
    EndingVerdict,
    RetryLedger,
    RetryReason,
    StreamEnding,
    decide_stream_ending,
)


def ledger(**overrides: object) -> RetryLedger:
    return RetryLedger(UpstreamRequestRetryConfig.model_validate(overrides))


def decide(
    *,
    terminal_seen: bool = False,
    downstream_opened: bool = False,
    committed_blocks: int = 0,
    book: RetryLedger | None = None,
) -> EndingVerdict:
    return decide_stream_ending(
        terminal_seen=terminal_seen,
        downstream_opened=downstream_opened,
        committed_blocks=committed_blocks,
        ledger=book if book is not None else ledger(),
        reason=RetryReason.NETWORK,
    )


def test_a_stream_upstream_finished_is_simply_complete() -> None:
    """The terminal event is the only thing that makes an ending a success, whatever else happened."""
    assert decide(terminal_seen=True).ending is StreamEnding.COMPLETE
    # Still complete with content already delivered: a finished turn is finished.
    assert decide(terminal_seen=True, downstream_opened=True, committed_blocks=3).ending is StreamEnding.COMPLETE


def test_nothing_delivered_yet_may_be_replayed_transparently() -> None:
    """The one place a replay is legal: there is no client-visible trace for a second attempt to contradict."""
    verdict = decide()
    assert verdict.ending is StreamEnding.REPLAY
    assert verdict.reason is RetryReason.NETWORK


def test_delivered_content_is_never_replayed() -> None:
    """Replay would send the client a second copy of what it already has, so this side stops rather than trying again."""
    verdict = decide(downstream_opened=True, committed_blocks=2)
    assert verdict.ending is StreamEnding.ABANDON
    assert verdict.reason is None
    assert "already delivered" in verdict.detail


def test_an_opened_but_empty_response_says_so_in_its_own_words() -> None:
    """Opened with nothing in it: the client holds a `message_start` and no content, so a replay would send it a second one.

    **No caller can reach this today.** The one thing that put a `message_start` on the wire before a block existed was the synthesised preamble, and that is gone — the preamble now travels with the first block, which makes "opened" and "a block was delivered" the same instant. Kept because this function is pure and a caller is free to ask, and because the two abandoned routes leave the client holding different things: `detail` is what a reader gets, and flattening them would cost that.
    """
    verdict = decide(downstream_opened=True, committed_blocks=0)
    assert verdict.ending is StreamEnding.ABANDON
    assert "without a content block" in verdict.detail


def test_an_exhausted_budget_ends_the_stream_rather_than_looping() -> None:
    book = ledger(max_total=1, strategies={"network": {"max_retries": 1}})
    assert decide(book=book).ending is StreamEnding.REPLAY
    second = decide(book=book)
    assert second.ending is StreamEnding.ABANDON
    assert second.detail


def test_deciding_spends_the_budget_it_grants() -> None:
    """Otherwise a caller that asks twice for one stream is funded twice, and a torn stream can loop for as long as upstream keeps tearing."""
    book = ledger(strategies={"network": {"max_retries": 5}})
    decide(book=book)
    assert book.spent(RetryReason.NETWORK) == 1


def test_an_ending_that_starts_no_attempt_spends_nothing() -> None:
    """The abandoned routes must not draw on the budget: nothing is being retried, so nothing is owed."""
    book = ledger()
    decide(downstream_opened=True, committed_blocks=2, book=book)
    decide(downstream_opened=True, committed_blocks=0, book=book)
    assert book.total_spent == 0


@pytest.mark.parametrize("blocks", [1, 7])
def test_how_much_was_delivered_does_not_change_the_route(blocks: int) -> None:
    """One block or many, the client has seen something — that is the whole of the question."""
    assert decide(downstream_opened=True, committed_blocks=blocks).ending is StreamEnding.ABANDON
