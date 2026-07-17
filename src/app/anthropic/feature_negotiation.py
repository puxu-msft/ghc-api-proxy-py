import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

NEGOTIATION_CATEGORIES = (
    "features",
    "betas",
    "efforts",
    "effortUnsupported",
    "deferredTools",
    "partnerFeatures",
    "systemRejectModels",
    "toolFields",
    "cacheControlSubfields",
)


@dataclass(slots=True)
class LearnedEntry:
    first_learned_at: float
    last_confirmed_at: float
    pinned: bool = False
    manually_expired: bool = False


class FeatureNegotiationStore:
    def __init__(
        self,
        *,
        default_ttl_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl = default_ttl_seconds
        self._clock = clock
        self._entries: dict[tuple[str, str, str], LearnedEntry] = {}

    def _validate(self, category: str) -> None:
        if category not in NEGOTIATION_CATEGORIES:
            raise ValueError(f"unknown negotiation category: {category}")

    def learn(self, category: str, key: str, value: str) -> None:
        self._validate(category)
        now = self._clock()
        entry = self._entries.get((category, key, value))
        if entry is None:
            self._entries[(category, key, value)] = LearnedEntry(now, now)
        else:
            entry.last_confirmed_at = now
            entry.manually_expired = False

    def is_active(self, category: str, key: str, value: str) -> bool:
        self._validate(category)
        entry = self._entries.get((category, key, value))
        if entry is None:
            return False
        if entry.pinned:
            return True
        if entry.manually_expired:
            return False
        return self._clock() <= entry.last_confirmed_at + self._ttl

    def pin(self, category: str, key: str, value: str, pinned: bool) -> None:
        self._entries[(category, key, value)].pinned = pinned

    def expire(self, category: str, key: str, value: str) -> None:
        self._entries[(category, key, value)].manually_expired = True

    def active_values(
        self,
        category: str,
        key: str,
        *,
        configured: Iterable[str] = (),
    ) -> set[str]:
        learned = {
            value
            for candidate_category, candidate_key, value in self._entries
            if candidate_category == category
            and candidate_key == key
            and self.is_active(category, key, value)
        }
        return set(configured) | learned