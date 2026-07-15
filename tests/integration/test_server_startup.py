from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.server import create_app


def test_server_lifespan_starts_and_stops_cleanly() -> None:
    app = create_app(AppSettings())

    with TestClient(app):
        settings: AppSettings = app.state.runtime.settings
        assert settings.port == 4141
        assert app.state.runtime.background_task_group is not None


def test_create_app_does_not_enable_otel_by_default() -> None:
    app = create_app(AppSettings())

    assert app.state.runtime.otel_enabled is False