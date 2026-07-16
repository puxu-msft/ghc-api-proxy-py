from app.history.types import HistoryEntry


class InFlightHistory:
    def __init__(self) -> None:
        self._entries: dict[str, HistoryEntry] = {}

    def add(self, entry: HistoryEntry) -> None:
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> HistoryEntry | None:
        return self._entries.get(entry_id)

    def remove(self, entry_id: str) -> HistoryEntry | None:
        return self._entries.pop(entry_id, None)

    def list(self) -> list[HistoryEntry]:
        return sorted(self._entries.values(), key=lambda entry: entry.started_at, reverse=True)