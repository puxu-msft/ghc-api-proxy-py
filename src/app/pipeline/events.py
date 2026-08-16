"""Ordered event subscription for the request driver.

MAIN.md: the driver provides subscription points.
A subscriber gives a unique id and may say which ids it goes before or after.
Order is resolved once, at freeze time, and never at dispatch.
The same request sequence must not order differently under different concurrency.

Event names belong to the driver that publishes them, so this module does not enumerate them.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

type Handler[T] = Callable[[T], Awaitable[None]]


class SubscriptionError(RuntimeError):
    """Raised at freeze time, so a malformed wiring cannot reach a request."""


@dataclass(frozen=True, slots=True)
class Subscription[T]:
    id: str
    handler: Handler[T]
    before: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    after: frozenset[str] = field(default_factory=lambda: frozenset[str]())


class SubscriberRegistry[T]:
    """Collects subscriptions during startup and freezes them into a fixed order."""

    def __init__(self) -> None:
        self._events: dict[str, dict[str, Subscription[T]]] = {}

    def subscribe(
        self,
        event: str,
        subscriber_id: str,
        handler: Handler[T],
        *,
        before: Iterable[str] = (),
        after: Iterable[str] = (),
    ) -> None:
        if not subscriber_id:
            raise SubscriptionError("subscriber id must not be empty")
        bucket = self._events.setdefault(event, {})
        if subscriber_id in bucket:
            raise SubscriptionError(
                f"duplicate subscriber id {subscriber_id!r} on event {event!r}"
            )
        bucket[subscriber_id] = Subscription(
            id=subscriber_id,
            handler=handler,
            before=frozenset(before),
            after=frozenset(after),
        )

    def freeze(self) -> FrozenSubscribers[T]:
        ordered: dict[str, tuple[Subscription[T], ...]] = {}
        for event, bucket in self._events.items():
            ordered[event] = _order(event, bucket)
        return FrozenSubscribers(ordered)


def _order[T](event: str, bucket: Mapping[str, Subscription[T]]) -> tuple[Subscription[T], ...]:
    """Topologically sort one event's subscribers.

    Ties break on registration order so the result is deterministic rather than merely valid.
    """
    edges: dict[str, set[str]] = {name: set() for name in bucket}
    for name, subscription in bucket.items():
        for other in subscription.after:
            if other not in bucket:
                raise SubscriptionError(
                    f"{name!r} wants to run after unknown subscriber {other!r} on event {event!r}"
                )
            edges[name].add(other)
        for other in subscription.before:
            if other not in bucket:
                raise SubscriptionError(
                    f"{name!r} wants to run before unknown subscriber {other!r} on event {event!r}"
                )
            edges[other].add(name)

    registration = list(bucket)
    resolved: list[str] = []
    remaining = dict(edges)
    while remaining:
        ready = [name for name in registration if name in remaining and not remaining[name]]
        if not ready:
            raise SubscriptionError(
                f"subscription order on event {event!r} is cyclic: {sorted(remaining)}"
            )
        for name in ready:
            resolved.append(name)
            del remaining[name]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return tuple(bucket[name] for name in resolved)


class FrozenSubscribers[T]:
    """The resolved order. Immutable, so dispatch cannot reorder or add."""

    def __init__(self, events: Mapping[str, Sequence[Subscription[T]]]) -> None:
        self._events = {event: tuple(items) for event, items in events.items()}

    @property
    def events(self) -> frozenset[str]:
        return frozenset(self._events)

    def for_event(self, event: str) -> tuple[Subscription[T], ...]:
        return self._events.get(event, ())

    def ids(self, event: str) -> tuple[str, ...]:
        return tuple(subscription.id for subscription in self.for_event(event))
