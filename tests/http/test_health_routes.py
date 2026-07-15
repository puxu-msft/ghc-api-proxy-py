from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.server import create_app


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