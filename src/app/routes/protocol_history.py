import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any
from uuid import uuid4

from app.history.types import HistoryEntry, ModelRef
from app.runtime import RuntimeState


def start_protocol_history(
    runtime: RuntimeState,
    *,
    endpoint: str,
    model: str,
    payload: dict[str, Any],
) -> HistoryEntry | None:
    if runtime.history_store is None:
        return None
    entry = HistoryEntry(
        id=str(uuid4()),
        session_id=None,
        agent_id="main",
        started_at=time.time(),
        ended_at=None,
        endpoint=endpoint,
        status="pending",
        model=ModelRef(model, model),
        request_payload=payload,
    )
    runtime.history_store.in_flight.add(entry)
    return entry


async def finalize_protocol_history(
    runtime: RuntimeState,
    entry: HistoryEntry | None,
    *,
    status: str,
) -> None:
    if entry is None or runtime.history_store is None:
        return
    entry.status = status
    entry.ended_at = time.time()
    await runtime.history_store.finalize(entry)
    runtime.history_store.in_flight.remove(entry.id)
    await runtime.history_store.websockets.broadcast(
        {"type": "entry_updated", "entry": {"id": entry.id, "status": status}}
    )


async def history_stream(
    stream: AsyncIterator[bytes],
    *,
    runtime: RuntimeState,
    entry: HistoryEntry | None,
) -> AsyncGenerator[bytes]:
    completed = False
    try:
        async for chunk in stream:
            yield chunk
        completed = True
    finally:
        await finalize_protocol_history(
            runtime,
            entry,
            status="completed" if completed else "aborted",
        )