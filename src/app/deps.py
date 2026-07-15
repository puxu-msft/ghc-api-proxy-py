from typing import Annotated

from fastapi import Depends, Request

from app.anthropic.client import AnthropicClient
from app.anthropic.token_counting import TokenCounter
from app.config.settings import AppSettings
from app.runtime import RuntimeState


def get_runtime_state(request: Request) -> RuntimeState:
    runtime: RuntimeState = request.app.state.runtime
    return runtime


def get_settings(request: Request) -> AppSettings:
    return get_runtime_state(request).settings


def get_anthropic_client(request: Request) -> AnthropicClient:
    client = get_runtime_state(request).anthropic_client
    if client is None:
        raise RuntimeError("Anthropic client is not initialized")
    return client


def get_token_counter(request: Request) -> TokenCounter:
    counter = get_runtime_state(request).token_counter
    if counter is None:
        raise RuntimeError("Token counter is not initialized")
    return counter


RuntimeDependency = Annotated[RuntimeState, Depends(get_runtime_state)]
SettingsDependency = Annotated[AppSettings, Depends(get_settings)]
AnthropicClientDependency = Annotated[AnthropicClient, Depends(get_anthropic_client)]
TokenCounterDependency = Annotated[TokenCounter, Depends(get_token_counter)]