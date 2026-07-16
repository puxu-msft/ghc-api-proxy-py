import time
from collections.abc import Callable

from app.transform.model_resolver import normalize_for_matching


class TokenLimitCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 86400,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, tuple[int, float]] = {}

    def record(self, model: str, limit: int) -> None:
        self._entries[normalize_for_matching(model)] = (limit, self._clock())

    def get(self, model: str) -> int | None:
        key = normalize_for_matching(model)
        entry = self._entries.get(key)
        if entry is None:
            return None
        limit, learned_at = entry
        if self._clock() > learned_at + self._ttl:
            self._entries.pop(key, None)
            return None
        return limit