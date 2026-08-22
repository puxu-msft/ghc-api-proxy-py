import time
from collections.abc import Callable

from app.pipeline.context import RequestContext


class RequestContextManager:
    def __init__(
        self,
        *,
        stale_max_age: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._stale_max_age = stale_max_age
        self._clock = clock
        self._active: dict[str, RequestContext] = {}

    @property
    def active_count(self) -> int:
        return len(self._active)

    def register(self, context: RequestContext) -> None:
        self._active[context.id] = context

    def complete(self, context_id: str) -> None:
        self._active.pop(context_id, None)

    def reap_stale(self) -> list[RequestContext]:
        cutoff = self._clock() - self._stale_max_age
        stale = [context for context in self._active.values() if context.created_at < cutoff]
        for context in stale:
            self._active.pop(context.id, None)
        return stale
