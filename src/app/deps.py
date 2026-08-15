from collections.abc import Set
from typing import Annotated, Protocol

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.anthropic.client import AnthropicClient
from app.config.settings import AppSettings
from app.history.store import HistoryStore
from app.history.ws import WebSocketManager
from app.models.common import ModelInfo
from app.openai.client import OpenAIClient
from app.pipeline.approval import ApprovalGate
from app.runtime import RuntimeState
from app.tokenization.service import AnthropicTokenCountingService


class ModelCatalogView(Protocol):
    @property
    def models(self) -> tuple[ModelInfo, ...]: ...

    @property
    def available_ids(self) -> Set[str]: ...

    def get(self, model_id: str) -> ModelInfo | None: ...


def get_runtime_state(connection: HTTPConnection) -> RuntimeState:
    runtime: RuntimeState = connection.app.state.runtime
    return runtime


def get_settings(connection: HTTPConnection) -> AppSettings:
    return get_runtime_state(connection).settings


def get_anthropic_client(connection: HTTPConnection) -> AnthropicClient:
    client = get_runtime_state(connection).anthropic_client
    if client is None:
        raise RuntimeError("Anthropic client is not initialized")
    return client


def get_token_counter(connection: HTTPConnection) -> AnthropicTokenCountingService:
    counter = get_runtime_state(connection).token_counter
    if counter is None:
        raise RuntimeError("Token counter is not initialized")
    return counter


def get_openai_client(connection: HTTPConnection) -> OpenAIClient:
    client = get_runtime_state(connection).openai_client
    if client is None:
        raise RuntimeError("OpenAI client is not initialized")
    return client


def get_model_catalog(connection: HTTPConnection) -> ModelCatalogView:
    services = get_runtime_state(connection).upstream_services
    if services is None:
        raise RuntimeError("Upstream services are not initialized")
    return services.model_catalog


def get_history_store(connection: HTTPConnection) -> HistoryStore:
    store = get_runtime_state(connection).history_store
    if store is None:
        raise RuntimeError("History store is not initialized")
    return store


def get_approval_gate(connection: HTTPConnection) -> ApprovalGate:
    gate = get_runtime_state(connection).approval_gate
    if gate is None:
        raise RuntimeError("Approval gate is not initialized")
    return gate


def get_websocket_manager(connection: HTTPConnection) -> WebSocketManager:
    manager = get_runtime_state(connection).websocket_manager
    if manager is None:
        raise RuntimeError("WebSocket manager is not initialized")
    return manager


RuntimeDependency = Annotated[RuntimeState, Depends(get_runtime_state)]
SettingsDependency = Annotated[AppSettings, Depends(get_settings)]
AnthropicClientDependency = Annotated[AnthropicClient, Depends(get_anthropic_client)]
TokenCounterDependency = Annotated[
    AnthropicTokenCountingService,
    Depends(get_token_counter),
]
OpenAIClientDependency = Annotated[OpenAIClient, Depends(get_openai_client)]
ModelCatalogDependency = Annotated[ModelCatalogView, Depends(get_model_catalog)]
HistoryStoreDependency = Annotated[HistoryStore, Depends(get_history_store)]
ApprovalGateDependency = Annotated[ApprovalGate, Depends(get_approval_gate)]
WebSocketManagerDependency = Annotated[
    WebSocketManager,
    Depends(get_websocket_manager),
]