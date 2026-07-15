from typing import Annotated

from fastapi import Depends, Request

from app.config.settings import AppSettings


def get_settings(request: Request) -> AppSettings:
    settings: AppSettings = request.app.state.settings
    return settings


SettingsDependency = Annotated[AppSettings, Depends(get_settings)]