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


class CRLFEventStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"type":"response.completed"}\r\n\r\n'


class StubClient:
    async def responses(self, request: ResponsesRequest) -> httpx.Response:
        assert request.stream is True
        return httpx.Response(200, stream=EventStream())


class FailingClient:
    async def responses(self, request: ResponsesRequest) -> httpx.Response:
        return httpx.Response(
            400,
            request=httpx.Request("POST", "https://upstream.test/responses"),
            json={"error": {"message": "bad request"}},
        )


class CRLFClient:
    async def responses(self, request: ResponsesRequest) -> httpx.Response:
        return httpx.Response(200, stream=CRLFEventStream())


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


def test_responses_websocket_forwards_upstream_error() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: FailingClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {"type": "response.create", "response": {"model": "gpt-test", "input": "hi"}}
        )
        error = websocket.receive_json()

    assert error == {
        "type": "error",
        "error": {"message": "bad request", "status_code": 400},
    }


def test_responses_websocket_accepts_crlf_sse() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_openai_client] = lambda: CRLFClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {"type": "response.create", "response": {"model": "gpt-test", "input": "hi"}}
        )
        assert websocket.receive_json() == {"type": "response.completed"}