from fastapi import FastAPI
from starlette.requests import Request

from app.config.settings import AppSettings
from app.deps import get_runtime_state, get_settings
from app.runtime import RuntimeState


def _request_for(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app, "headers": []})


def test_runtime_state_is_the_single_app_state_container() -> None:
    settings = AppSettings()
    runtime = RuntimeState(settings=settings)
    app = FastAPI()
    app.state.runtime = runtime
    request = _request_for(app)

    assert get_runtime_state(request) is runtime
    assert get_settings(request) is settings


def test_readiness_snapshot_uses_typed_runtime_fields() -> None:
    runtime = RuntimeState(settings=AppSettings())

    assert runtime.readiness_checks() == {
        "github_token": False,
        "copilot_token": False,
        "models": False,
    }

    runtime.github_token_ready = True
    runtime.copilot_token_ready = True
    runtime.models_ready = True

    assert runtime.is_ready is True
