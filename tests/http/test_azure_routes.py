import httpx
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_openai_client
from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.server import create_app


class StubClient:
    async def chat(self, request: ChatCompletionRequest) -> httpx.Response:
        return httpx.Response(200, json={"model": request.model})

    async def responses(self, request: ResponsesRequest) -> httpx.Response:
        return httpx.Response(200, json={"model": request.model})

    async def embeddings(self, request: EmbeddingsRequest) -> httpx.Response:
        return httpx.Response(200, json={"model": request.model})


def test_azure_classic_chat_uses_deployment_model() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: StubClient()
    with TestClient(app) as client:
        response = client.post(
            "/openai/deployments/deployment/chat/completions?api-version=2025-01-01",
            json={"model": "ignored", "messages": []},
        )
    assert response.status_code == 200
    assert response.json()["model"] == "deployment"


def test_azure_responses_and_embeddings_use_deployment_model() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: StubClient()
    with TestClient(app) as client:
        responses = client.post(
            "/openai/deployments/deployment/responses",
            json={"model": "ignored", "input": "hi"},
        )
        embeddings = client.post(
            "/openai/deployments/deployment/embeddings",
            json={"model": "ignored", "input": "hi"},
        )
    assert responses.json()["model"] == "deployment"
    assert embeddings.json()["model"] == "deployment"
