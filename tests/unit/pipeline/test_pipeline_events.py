import pytest

from app.pipeline.events import SubscriberRegistry, SubscriptionError
from app.pipeline.exceptions import (
    Disposition,
    PipelineAbort,
    PipelineRetry,
    UpstreamError,
    UpstreamRateLimit,
    UpstreamTimeout,
    classify,
    is_known,
)


async def noop(_: object) -> None:
    return None


def registry_with(*ids: str) -> SubscriberRegistry[object]:
    registry = SubscriberRegistry[object]()
    for name in ids:
        registry.subscribe("pre_send", name, noop)
    return registry


def test_registration_order_is_kept_when_nothing_constrains_it() -> None:
    # Ids are deliberately in reverse alphabetical order.
    # Sorting instead of keeping registration order would be invisible with alphabetical ids.
    frozen = registry_with("zeta", "mid", "alpha").freeze()
    assert frozen.ids("pre_send") == ("zeta", "mid", "alpha")


def test_ties_break_on_registration_order_not_on_the_name() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "root", noop)
    registry.subscribe("pre_send", "zulu", noop, after=["root"])
    registry.subscribe("pre_send", "alpha", noop, after=["root"])
    assert registry.freeze().ids("pre_send") == ("root", "zulu", "alpha")


def test_after_moves_a_subscriber_later() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop, after=["b"])
    registry.subscribe("pre_send", "b", noop)
    assert registry.freeze().ids("pre_send") == ("b", "a")


def test_before_moves_a_subscriber_earlier() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop)
    registry.subscribe("pre_send", "b", noop, before=["a"])
    assert registry.freeze().ids("pre_send") == ("b", "a")


def test_order_is_deterministic_not_merely_valid() -> None:
    # Two subscribers constrained after a third could legally come out in either order.
    # Ties break on registration order, so repeated freezes agree.
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "root", noop)
    registry.subscribe("pre_send", "zulu", noop, after=["root"])
    registry.subscribe("pre_send", "alpha", noop, after=["root"])
    first = registry.freeze().ids("pre_send")
    second = registry.freeze().ids("pre_send")
    assert first == second == ("root", "zulu", "alpha")


def test_constraints_from_both_directions_agree() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "middle", noop)
    registry.subscribe("pre_send", "last", noop, after=["middle"])
    registry.subscribe("pre_send", "first", noop, before=["middle"])
    assert registry.freeze().ids("pre_send") == ("first", "middle", "last")


def test_events_are_ordered_independently() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop)
    registry.subscribe("post_send", "b", noop)
    frozen = registry.freeze()
    assert frozen.ids("pre_send") == ("a",)
    assert frozen.ids("post_send") == ("b",)
    assert frozen.events == {"pre_send", "post_send"}


def test_unknown_event_yields_no_subscribers() -> None:
    assert registry_with("a").freeze().for_event("never_published") == ()


def test_duplicate_id_on_one_event_is_rejected() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop)
    with pytest.raises(SubscriptionError, match="duplicate"):
        registry.subscribe("pre_send", "a", noop)


def test_same_id_on_different_events_is_allowed() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop)
    registry.subscribe("post_send", "a", noop)
    assert registry.freeze().ids("post_send") == ("a",)


def test_empty_id_is_rejected() -> None:
    with pytest.raises(SubscriptionError, match="must not be empty"):
        SubscriberRegistry[object]().subscribe("pre_send", "", noop)


def test_reference_to_an_unregistered_id_fails_at_freeze() -> None:
    # Freeze happens at startup, so a typo in a constraint cannot wait for a request to surface.
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop, after=["typo"])
    with pytest.raises(SubscriptionError, match="unknown subscriber"):
        registry.freeze()


def test_cycle_fails_at_freeze() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop, after=["b"])
    registry.subscribe("pre_send", "b", noop, after=["a"])
    with pytest.raises(SubscriptionError, match="cyclic"):
        registry.freeze()


def test_cycle_formed_by_mixed_directions_fails_at_freeze() -> None:
    registry = SubscriberRegistry[object]()
    registry.subscribe("pre_send", "a", noop, before=["b"])
    registry.subscribe("pre_send", "b", noop, before=["a"])
    with pytest.raises(SubscriptionError, match="cyclic"):
        registry.freeze()


def test_frozen_view_cannot_be_extended_through_the_registry() -> None:
    registry = registry_with("a")
    frozen = registry.freeze()
    registry.subscribe("pre_send", "late", noop)
    # The already-frozen order is the one a request runs; a later subscribe does not reach it.
    assert frozen.ids("pre_send") == ("a",)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PipelineAbort("stop"), Disposition.ABORT),
        (PipelineRetry("again"), Disposition.RETRY),
        (UpstreamError("boom"), Disposition.RETRY),
        (UpstreamTimeout("slow"), Disposition.RETRY),
        (UpstreamRateLimit("429"), Disposition.RETRY),
    ],
)
def test_known_exceptions_map_to_their_disposition(
    error: Exception, expected: Disposition
) -> None:
    assert classify(error) is expected
    assert is_known(error) is True


@pytest.mark.parametrize(
    "error",
    [KeyError("k"), AttributeError("a"), ValueError("v"), RuntimeError("r")],
)
def test_unknown_exceptions_always_abort(error: Exception) -> None:
    # A subscriber bug must not read as a retry instruction.
    # One defect would otherwise become an upstream storm bounded only by the retry budget.
    assert classify(error) is Disposition.ABORT
    assert is_known(error) is False


def test_rate_limit_carries_retry_after_and_the_status() -> None:
    error = UpstreamRateLimit("slow down", retry_after=12.5)
    assert error.retry_after == 12.5
    assert error.status_code == 429


def test_upstream_error_carries_its_status() -> None:
    assert UpstreamError("bad gateway", status_code=502).status_code == 502
