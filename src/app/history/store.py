from pathlib import Path

from app.history.in_flight import InFlightHistory
from app.history.sqlite.writer import HistoryWriter
from app.history.types import HistoryEntry
from app.history.ws import WebSocketManager


class HistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.writer = HistoryWriter(db_path)
        self.in_flight = InFlightHistory()
        self.websockets = WebSocketManager()

    async def start(self) -> None:
        await self.writer.start()

    async def finalize(self, entry: HistoryEntry) -> None:
        await self.writer.submit(entry)

    async def flush(self) -> None:
        await self.writer.flush()

    async def list_entries(self, *, limit: int = 100) -> list[HistoryEntry]:
        persisted = await self.writer.list_entries(limit=limit) if self.writer.started else []
        merged = {entry.id: entry for entry in persisted}
        merged.update({entry.id: entry for entry in self.in_flight.list()})
        return sorted(merged.values(), key=lambda entry: entry.started_at, reverse=True)[:limit]

    async def get(self, entry_id: str) -> HistoryEntry | None:
        live = self.in_flight.get(entry_id)
        if live is not None:
            return live
        entries = await self.list_entries(limit=1000)
        return next((entry for entry in entries if entry.id == entry_id), None)

    async def close(self) -> None:
        await self.writer.close()