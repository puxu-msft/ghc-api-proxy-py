from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.lifecycle.rolling.generation.phases import GenerationLifecycle, GenerationPhase
from app.routes.health import readiness
from app.runtime import RuntimeState
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


async def test_rolling_readiness_requires_dependencies_and_accepting_phase() -> None:
    lifecycle = GenerationLifecycle()
    runtime = RuntimeState(settings=AppSettings(), generation_lifecycle=lifecycle)

    starting = await readiness(runtime)
    assert starting.status_code == 503
    assert b'"phase":"starting"' in starting.body

    runtime.github_token_ready = True
    runtime.copilot_token_ready = True
    runtime.models_ready = True
    assert runtime.dependencies_ready is True
    assert runtime.is_ready is False

    await lifecycle.mark_ready()
    accepting = await readiness(runtime)
    assert accepting.status_code == 200
    assert b'"phase":"ready_accepting"' in accepting.body

    await lifecycle.quiesce()
    quiescing = await readiness(runtime)
    assert quiescing.status_code == 503
    assert lifecycle.phase is GenerationPhase.QUIESCING
    assert b'"accepting":false' in quiescing.body