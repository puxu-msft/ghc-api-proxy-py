from unittest.mock import AsyncMock, Mock

import pytest
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


def test_server_lifespan_initializes_and_closes_phase1_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize = AsyncMock()
    close = AsyncMock()
    available = AsyncMock(return_value=True)
    services = Mock()
    services.copilot_tokens = None
    initialize.return_value = services
    monkeypatch.setattr("app.server.initialize_upstream_services", initialize)
    monkeypatch.setattr("app.server.close_upstream_services", close)
    monkeypatch.setattr("app.server.noninteractive_token_available", available)
    app = create_app(AppSettings.model_validate({"auth": {"github_token": "ghu"}}))

    with TestClient(app):
        initialize.assert_awaited_once_with(app.state.runtime)

    close.assert_awaited_once_with(app.state.runtime)