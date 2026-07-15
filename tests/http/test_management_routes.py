from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.server import create_app


def test_status_and_config_management_routes() -> None:
    with TestClient(create_app(AppSettings())) as client:
        status = client.get("/api/status")
        config = client.get("/api/config")

    assert status.status_code == 200
    assert status.json()["ready"] is False
    assert config.status_code == 200
    assert config.json()["port"] == 4141


def test_event_logging_batch_is_silently_consumed() -> None:
    with TestClient(create_app(AppSettings())) as client:
        response = client.post("/api/event_logging/batch", json={"events": [{"type": "noise"}]})

    assert response.status_code == 204
    assert response.content == b""


def test_browser_probe_is_silently_consumed() -> None:
    with TestClient(create_app(AppSettings())) as client:
        assert client.get("/favicon.ico").status_code == 204