import time
from typing import Any

from app.history.store import HistoryStore
from app.history.types import HistoryEntry, ModelRef
from app.pipeline.context import RequestContext, RequestState


class HistoryConsumer:
    def __init__(self, store: HistoryStore) -> None:
        self._store = store

    async def started(self, context: RequestContext) -> None:
        entry = self._entry(context, "pending")
        self._store.in_flight.add(entry)
        await self._store.websockets.broadcast(
            {"type": "entry_added", "entry": {"id": entry.id, "status": entry.status}}
        )

    async def finalized(
        self,
        context: RequestContext,
        *,
        response: dict[str, Any] | None = None,
    ) -> None:
        status = "completed" if context.state is RequestState.COMPLETED else "failed"
        entry = self._entry(context, status)
        entry.response = response
        await self._store.finalize(entry)
        await self._store.flush()
        self._store.in_flight.remove(entry.id)
        await self._store.websockets.broadcast(
            {"type": "entry_updated", "entry": {"id": entry.id, "status": entry.status}}
        )

    @staticmethod
    def _entry(context: RequestContext, status: str) -> HistoryEntry:
        return HistoryEntry(
            id=context.id,
            session_id=context.session_id,
            agent_id=context.agent_id or "main",
            started_at=context.created_at,
            ended_at=time.time() if status not in ("pending", "executing", "streaming") else None,
            endpoint=context.endpoint,
            status=status,
            model=ModelRef(
                context.original_model,
                context.resolved_model or context.original_model,
            ),
            request_payload=context.original_payload,
            error_message=context.error.message if context.error else None,
        )