from typing import Annotated

from fastapi import Depends, Request

from app.config.settings import AppSettings
from app.runtime import RuntimeState


def get_runtime_state(request: Request) -> RuntimeState:
    runtime: RuntimeState = request.app.state.runtime
    return runtime


def get_settings(request: Request) -> AppSettings:
    return get_runtime_state(request).settings


RuntimeDependency = Annotated[RuntimeState, Depends(get_runtime_state)]
SettingsDependency = Annotated[AppSettings, Depends(get_settings)]