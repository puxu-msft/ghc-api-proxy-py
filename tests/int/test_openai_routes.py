from collections.abc import AsyncIterator

import httpx2
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_model_catalog, get_openai_client
from app.models.common import ModelInfo
from app.models.openai import ChatCompletionRequest, EmbeddingsRequest, ResponsesRequest
from app.server.app_factory import create_app


class Stream(httpx2.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: chunk\n\n"


class StubOpenAIClient:
    async def chat(self, request: ChatCompletionRequest) -> httpx2.Response:
        if request.stream:
            return httpx2.Response(200, stream=Stream())
        return httpx2.Response(200, json={"id": "chat_1", "future": True})

    async def responses(self, request: ResponsesRequest) -> httpx2.Response:
        return httpx2.Response(200, json={"id": "resp_1", "future": True})

    async def embeddings(self, request: EmbeddingsRequest) -> httpx2.Response:
        return httpx2.Response(200, json={"object": "list", "data": []})


class FailingStreamClient(StubOpenAIClient):
    async def chat(self, request: ChatCompletionRequest) -> httpx2.Response:
        return httpx2.Response(
            429,
            request=httpx2.Request("POST", "https://upstream.test/chat/completions"),
            json={"error": {"type": "rate_limit_error"}},
        )


class StubCatalog:
    models = (ModelInfo(id="gpt-test", vendor="OpenAI"),)
    available_ids = frozenset({"gpt-test"})

    def get(self, model_id: str) -> ModelInfo | None:
        return self.models[0] if model_id == "gpt-test" else None


def _app():
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: StubOpenAIClient()
    app.dependency_overrides[get_model_catalog] = lambda: StubCatalog()
    return app


def test_openai_routes_are_registered_under_three_prefixes() -> None:
    with TestClient(_app()) as client:
        for prefix in ("", "/v1", "/openai/v1"):
            chat = client.post(
                f"{prefix}/chat/completions",
                json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
            )
            assert chat.status_code == 200
            assert chat.json()["future"] is True
            models = client.get(f"{prefix}/models")
            assert models.status_code == 200
            assert models.json()["data"][0]["id"] == "gpt-test"


def test_chat_stream_has_sse_headers_and_bytes() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "stream": True, "messages": []},
        )

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.content == b"data: chunk\n\n"


def test_responses_and_embeddings_routes() -> None:
    with TestClient(_app()) as client:
        responses = client.post("/v1/responses", json={"model": "gpt-test", "input": "hi"})
        embeddings = client.post(
            "/v1/embeddings", json={"model": "gpt-test", "input": "hi"}
        )

    assert responses.status_code == 200
    assert embeddings.status_code == 200


def test_streaming_error_preserves_upstream_status() -> None:
    app = _app()
    app.dependency_overrides[get_openai_client] = lambda: FailingStreamClient()
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "stream": True, "messages": []},
        )

    assert response.status_code == 429
    assert response.json() == {"error": {"type": "rate_limit_error"}}
