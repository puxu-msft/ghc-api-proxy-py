"""What to do about a stream that stopped short, decided from what we received.

The rule these pin is the one `app/pipeline/retry.py` has stated since before anything called it: a replay is only legal while the client has seen nothing, and continuation is what is left once it has. What is new is that something now decides between them.
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
    assert verdict.reason is RetryReason.STREAM_REPLAY


def test_delivered_content_is_continued_rather_than_replayed() -> None:
    """Replay would send the client a second copy of what it already has, so the blocks become the assistant turn instead."""
    verdict = decide(downstream_opened=True, committed_blocks=2)
    assert verdict.ending is StreamEnding.CONTINUE
    assert verdict.reason is RetryReason.CONTINUATION


def test_an_opened_but_empty_response_can_do_neither() -> None:
    """The synthesized-start case, and the reason four outcomes are needed rather than three.

    A long silence puts `message_start` on the wire before any block exists. Replaying would then send a second `message_start`; continuing would ask upstream to carry on from an assistant turn with no content, which this upstream refuses outright. Both doors are shut, so the stream has to end as truncated.
    """
    verdict = decide(downstream_opened=True, committed_blocks=0)
    assert verdict.ending is StreamEnding.ABANDON
    assert "content block" in verdict.detail


def test_an_exhausted_budget_ends_the_stream_rather_than_looping() -> None:
    book = ledger(max_total=1, strategies={"streamReplay": {"max_retries": 1}})
    assert decide(book=book).ending is StreamEnding.REPLAY
    second = decide(book=book)
    assert second.ending is StreamEnding.ABANDON
    assert second.detail


def test_continuation_switched_off_ends_the_stream() -> None:
    """`enabled: false` is an operator saying not to ask upstream to carry on; it must not fall through to a replay the client would see twice."""
    book = ledger(strategies={"continuation": {"enabled": False}})
    verdict = decide(downstream_opened=True, committed_blocks=1, book=book)
    assert verdict.ending is StreamEnding.ABANDON
    assert verdict.reason is RetryReason.CONTINUATION


def test_deciding_spends_the_budget_it_grants() -> None:
    """Otherwise a caller that asks twice for one stream is funded twice, and a torn stream can loop for as long as upstream keeps tearing."""
    book = ledger(strategies={"continuation": {"max_retries": 5}})
    decide(downstream_opened=True, committed_blocks=1, book=book)
    assert book.spent(RetryReason.CONTINUATION) == 1


@pytest.mark.parametrize("blocks", [1, 7])
def test_how_much_was_delivered_does_not_change_the_route(blocks: int) -> None:
    """One block or many, the client has seen something — that is the whole of the question."""
    assert decide(downstream_opened=True, committed_blocks=blocks).ending is StreamEnding.CONTINUE
