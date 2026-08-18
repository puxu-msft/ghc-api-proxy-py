from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_history_store
from app.history.store import HistoryStore
from app.history.types import HistoryEntry, ModelRef
from app.server import create_app


def _entry() -> HistoryEntry:
    return HistoryEntry(
        id="entry-1",
        session_id="session",
        agent_id="main",
        started_at=1,
        ended_at=2,
        endpoint="anthropic-messages",
        status="completed",
        model=ModelRef("requested", "resolved"),
        request_payload={"message": "hi"},
    )


def test_history_entries_and_detail_routes(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")
    store.in_flight.add(_entry())
    app = create_app(AppSettings())
    app.dependency_overrides[get_history_store] = lambda: store
    with TestClient(app) as client:
        entries = client.get("/history/api/entries")
        detail = client.get("/history/api/entries/entry-1")

    assert entries.status_code == 200
    assert entries.json()["data"][0]["id"] == "entry-1"
    assert detail.json()["request_payload"] == {"message": "hi"}


def test_history_websocket_receives_broadcast(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")
    app = create_app(AppSettings())
    app.dependency_overrides[get_history_store] = lambda: store
    with (
        TestClient(app) as client,
        client.websocket_connect("/history/ws") as websocket,
    ):
        websocket.send_json({"type": "subscribe", "topic": "history"})
        assert websocket.receive_json() == {
            "type": "subscribed",
            "topic": "history",
        }
