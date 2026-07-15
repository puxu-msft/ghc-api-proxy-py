import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QuarantineKey:
    session_id: str
    agent_id: str = ""


class ThinkingQuarantineStore:
    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[QuarantineKey, float] = {}

    def record(self, key: QuarantineKey) -> None:
        now = self._clock()
        self._entries[key] = now
        expired = [item for item, seen in self._entries.items() if now - seen > self._ttl]
        for item in expired:
            self._entries.pop(item, None)
        while len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=self._entries.__getitem__)
            self._entries.pop(oldest)

    def is_poisoned(self, key: QuarantineKey) -> bool:
        seen = self._entries.get(key)
        now = self._clock()
        if seen is None or now - seen > self._ttl:
            self._entries.pop(key, None)
            return False
        self._entries[key] = now
        return True