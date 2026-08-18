from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_settings
from app.server import create_app


@pytest.fixture(autouse=True)
def no_ambient_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's own credentials out of these assertions.

    Both tests here assert that dependencies are *uninitialised*, and the app looks for a GitHub
    token in the real data directory and the environment. So they passed only while the machine
    running them happened to have no credentials — putting a token on it turned them red without
    anything in the app changing. Local to this file rather than a shared entry: the other test
    groups have no business inheriting this environment.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for name in ("COPILOT_API_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_status_and_config_management_routes() -> None:
    settings = AppSettings.model_validate(
        {
            "auth": {"github_token": "ghu-secret"},
            "upstream": {"api_key": "sk-secret"},
        }
    )
    app = create_app(AppSettings())
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        status = client.get("/api/status")
        config = client.get("/api/config")

    assert status.status_code == 200
    assert status.json()["ready"] is False
    assert config.status_code == 200
    assert config.json()["port"] == 4141
    assert config.json()["auth"]["github_token"] == "***"
    assert config.json()["upstream"]["api_key"] == "***"
    assert "ghu-secret" not in config.text
    assert "sk-secret" not in config.text


def test_event_logging_batch_is_silently_consumed() -> None:
    with TestClient(create_app(AppSettings())) as client:
        response = client.post("/api/event_logging/batch", json={"events": [{"type": "noise"}]})

    assert response.status_code == 204
    assert response.content == b""


def test_browser_probe_is_silently_consumed() -> None:
    with TestClient(create_app(AppSettings())) as client:
        assert client.get("/favicon.ico").status_code == 204


def test_tokenization_management_routes_expose_and_filter_state() -> None:
    app = create_app(AppSettings())
    with TestClient(app) as client:
        state = app.state.runtime.tokenization_state
        assert state is not None
        state.calibration.learn("anthropic", "Claude-Test", 10_000, 12_000)
        state.calibration.learn("gemini", "Gemini-Test", 10_000, 11_000)
        state.prompt_limits.record(
            "anthropic",
            "Claude-Test",
            current=120_000,
            limit=100_000,
            source="anthropic_messages_error",
            observed_at=10,
        )

        calibration = client.get(
            "/api/tokenization/calibration",
            params={"protocol": "anthropic", "model": "claude.test"},
        )
        limits = client.get("/api/tokenization/limits")

    assert calibration.status_code == 200
    assert list(calibration.json()["calibration"]) == ["anthropic:claude-test"]
    assert limits.status_code == 200
    item = limits.json()["limits"]["anthropic:claude-test"]
    assert item["observed_limit"] == 100_000
    assert item["advertised_limit"] is None
    assert item["difference"] is None
