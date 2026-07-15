from collections.abc import Set
from typing import Annotated, Protocol

from fastapi import Depends, Request

from app.anthropic.client import AnthropicClient
from app.anthropic.token_counting import TokenCounter
from app.config.settings import AppSettings
from app.models.common import ModelInfo
from app.openai.client import OpenAIClient
from app.openai.responses_ws import ResponsesWebSocketClient
from app.runtime import RuntimeState


class ModelCatalogView(Protocol):
    @property
    def models(self) -> tuple[ModelInfo, ...]: ...

    @property
    def available_ids(self) -> Set[str]: ...

    def get(self, model_id: str) -> ModelInfo | None: ...


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


def get_openai_client(request: Request) -> OpenAIClient:
    client = get_runtime_state(request).openai_client
    if client is None:
        raise RuntimeError("OpenAI client is not initialized")
    return client


def get_model_catalog(request: Request) -> ModelCatalogView:
    services = get_runtime_state(request).upstream_services
    if services is None:
        raise RuntimeError("Upstream services are not initialized")
    return services.model_catalog


def get_responses_ws_client(request: Request) -> ResponsesWebSocketClient:
    client = get_runtime_state(request).responses_ws_client
    if client is None:
        raise RuntimeError("Responses WebSocket client is not initialized")
    return client


RuntimeDependency = Annotated[RuntimeState, Depends(get_runtime_state)]
SettingsDependency = Annotated[AppSettings, Depends(get_settings)]
AnthropicClientDependency = Annotated[AnthropicClient, Depends(get_anthropic_client)]
TokenCounterDependency = Annotated[TokenCounter, Depends(get_token_counter)]
OpenAIClientDependency = Annotated[OpenAIClient, Depends(get_openai_client)]
ModelCatalogDependency = Annotated[ModelCatalogView, Depends(get_model_catalog)]
ResponsesWSClientDependency = Annotated[
    ResponsesWebSocketClient,
    Depends(get_responses_ws_client),
]