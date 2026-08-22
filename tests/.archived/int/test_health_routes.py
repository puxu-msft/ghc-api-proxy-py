from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.server.app_factory import create_app


@pytest.fixture(autouse=True)
def no_ambient_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's own credentials out of these assertions.

    Both tests here assert that dependencies are *uninitialised*, and the app looks for a GitHub token in the real data directory and the environment. So they passed only while the machine running them happened to have no credentials — putting a token on it turned them red without anything in the app changing. Local to this file rather than a shared entry: the other test groups have no business inheriting this environment.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("GHC_API_PROXY_GITHUB_TOKEN", raising=False)


def test_health_liveness_is_always_available() -> None:
    with TestClient(create_app(AppSettings())) as client:
        response = client.get("/health/liveness")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_readiness_reports_uninitialized_dependencies() -> None:
    with TestClient(create_app(AppSettings())) as client:
        response = client.get("/health/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "checks": {
            "github_token": False,
            "copilot_token": False,
            "models": False,
        },
    }


def test_health_alias_matches_readiness() -> None:
    with TestClient(create_app(AppSettings())) as client:
        health = client.get("/health")
        readiness = client.get("/health/readiness")

    assert health.status_code == readiness.status_code
    assert health.json() == readiness.json()

