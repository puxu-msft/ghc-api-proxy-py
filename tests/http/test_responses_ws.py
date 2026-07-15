from collections.abc import AsyncIterator

import httpx
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_openai_client
from app.models.openai import ResponsesRequest
from app.server import create_app


class EventStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"type":"response.created"}\n\n'
        yield b'data: {"type":"response.completed"}\n\n'


class StubClient:
    async def responses(self, request: ResponsesRequest) -> httpx.Response:
        assert request.stream is True
        return httpx.Response(200, stream=EventStream())


def test_responses_websocket_bridges_response_create_to_json_frames() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: StubClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {
                "type": "response.create",
                "response": {"model": "gpt-test", "input": "hi"},
            }
        )
        assert websocket.receive_json() == {"type": "response.created"}
        assert websocket.receive_json() == {"type": "response.completed"}


def test_responses_websocket_rejects_invalid_initial_frame() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: StubClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json({"type": "invalid"})
        error = websocket.receive_json()

    assert error["type"] == "error"