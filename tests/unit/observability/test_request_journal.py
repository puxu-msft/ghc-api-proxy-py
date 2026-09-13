from __future__ import annotations

from app.observability.request_journal import (
    RequestJournal,
    RequestJournalEventKind,
)


def test_request_journal_freezes_typed_order_and_rejects_late_observations() -> None:
    journal = RequestJournal("request-journal", max_events=2)

    assert journal.record(
        RequestJournalEventKind.RESPONSE_READY,
        0.1,
        {"status_code": 200},
    )
    assert journal.record(
        RequestJournalEventKind.DELIVERY_STARTED,
        0.2,
        {"status_code": 200},
    )
    assert not journal.record(
        RequestJournalEventKind.DELIVERY_FINISHED,
        0.3,
        {"body_bytes": 12},
    )
    events = journal.freeze()

    assert [event.sequence for event in events] == [0, 1]
    assert [event.kind for event in events] == [
        RequestJournalEventKind.RESPONSE_READY,
        RequestJournalEventKind.DELIVERY_STARTED,
    ]
    assert journal.dropped_events == 1
    assert journal.frozen is True
    assert not journal.record(RequestJournalEventKind.FINALIZED, 0.4)


def test_request_journal_observation_failure_does_not_escape() -> None:
    journal = RequestJournal("request-journal")

    assert not journal.record(
        RequestJournalEventKind.FAILURE,
        0.1,
        {"unserializable": object()},
    )
    assert journal.snapshot() == ()
