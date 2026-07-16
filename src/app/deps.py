from collections.abc import Set
from typing import Annotated, Protocol

from fastapi import Depends, Request

from app.anthropic.client import AnthropicClient
from app.anthropic.token_counting import TokenCounter
from app.config.settings import AppSettings
from app.history.store import HistoryStore
from app.history.ws import WebSocketManager
from app.models.common import ModelInfo
from app.openai.client import OpenAIClient
from app.openai.responses_ws import ResponsesWebSocketClient
from app.pipeline.approval import ApprovalGate
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


def get_history_store(request: Request) -> HistoryStore:
    store = get_runtime_state(request).history_store
    if store is None:
        raise RuntimeError("History store is not initialized")
    return store


def get_approval_gate(request: Request) -> ApprovalGate:
    gate = get_runtime_state(request).approval_gate
    if gate is None:
        raise RuntimeError("Approval gate is not initialized")
    return gate


def get_websocket_manager(request: Request) -> WebSocketManager:
    manager = get_runtime_state(request).websocket_manager
    if manager is None:
        raise RuntimeError("WebSocket manager is not initialized")
    return manager


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
HistoryStoreDependency = Annotated[HistoryStore, Depends(get_history_store)]
ApprovalGateDependency = Annotated[ApprovalGate, Depends(get_approval_gate)]
WebSocketManagerDependency = Annotated[
    WebSocketManager,
    Depends(get_websocket_manager),
]