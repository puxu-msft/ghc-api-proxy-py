from collections.abc import AsyncIterator

import httpx
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_openai_client
from app.models.openai import ChatCompletionRequest
from app.server import create_app


class Stream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"


class StubClient:
    async def chat(self, request: ChatCompletionRequest) -> httpx.Response:
        if request.stream:
            return httpx.Response(200, stream=Stream())
        return httpx.Response(
            200,
            json={
                "model": request.model,
                "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )


def _app():
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: StubClient()
    return app


def test_gemini_generate_content_nonstream() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/v1beta/models/gemini-test:generateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
        )
    assert response.status_code == 200
    assert response.json()["candidates"][0]["content"]["parts"][0]["text"] == "hello"


def test_gemini_stream_generate_content_is_sse_without_done() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/v1beta/models/gemini-test:streamGenerateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
        )
    assert response.status_code == 200
    assert b"hi" in response.content
    assert b"[DONE]" not in response.content


def test_gemini_unknown_method_uses_gemini_error_shape() -> None:
    with TestClient(_app()) as client:
        response = client.post("/v1beta/models/gemini-test:unknown", json={})
    assert response.status_code == 404
    assert response.json()["error"]["status"] == "NOT_FOUND"


def test_gemini_count_tokens_uses_local_counting() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/v1beta/models/gemini-test:countTokens",
            json={"contents": [{"role": "user", "parts": [{"text": "hello"}]}]},
        )
    assert response.status_code == 200
    assert response.json()["totalTokens"] > 0
