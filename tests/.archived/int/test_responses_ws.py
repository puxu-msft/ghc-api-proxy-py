from collections.abc import AsyncIterator
from typing import Any

import httpx2
from fastapi.testclient import TestClient
from httpx2.websockets import WebSocketNetworkError, WebSocketUpgradeError
from starlette.websockets import WebSocketDisconnect

from app.config.settings import AppSettings
from app.deps import get_approval_gate, get_responses_ws_client
from app.pipeline.approval import ApprovalResult
from app.pipeline.context import RequestContext
from app.server.app_factory import create_app


class StubClient:
    async def create_response(
        self,
        frame: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        assert frame["response"]["stream"] is True
        yield {"type": "response.created"}
        yield {"type": "response.completed"}


class FailingClient:
    async def create_response(
        self,
        frame: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del frame
        yield {
            "type": "error",
            "error": {"message": "bad request", "status_code": 400},
        }


class RejectingGate:
    enabled = True

    async def wait_for_approval(self, context: RequestContext) -> ApprovalResult:
        del context
        return ApprovalResult("rejected", "denied")


class UpgradeFailingClient:
    async def create_response(
        self,
        frame: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del frame
        response = httpx2.Response(
            403,
            request=httpx2.Request("GET", "wss://upstream.test/responses"),
        )
        raise WebSocketUpgradeError(response)
        yield {}


class NetworkFailingClient:
    async def create_response(
        self,
        frame: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del frame
        raise WebSocketNetworkError("connection lost")
        yield {}


def test_responses_websocket_bridges_response_create_to_json_frames() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_responses_ws_client] = lambda: StubClient()

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
    app.dependency_overrides[get_responses_ws_client] = lambda: StubClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json({"type": "invalid"})
        error = websocket.receive_json()

    assert error["type"] == "error"


def test_responses_websocket_forwards_upstream_error_frame() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_responses_ws_client] = lambda: FailingClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {"type": "response.create", "response": {"model": "gpt-test", "input": "hi"}}
        )
        error = websocket.receive_json()

    assert error == {
        "type": "error",
        "error": {"message": "bad request", "status_code": 400},
    }


def test_responses_websocket_reports_approval_rejection() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_responses_ws_client] = lambda: StubClient()
    app.dependency_overrides[get_approval_gate] = lambda: RejectingGate()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {"type": "response.create", "response": {"model": "gpt-test", "input": "hi"}}
        )
        assert websocket.receive_json() == {
            "type": "error",
            "error": {"message": "Rejected: denied"},
        }
        try:
            websocket.receive_json()
        except WebSocketDisconnect as error:
            assert error.code == 4003


def test_responses_websocket_reports_upgrade_rejection() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_responses_ws_client] = lambda: UpgradeFailingClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {"type": "response.create", "response": {"model": "gpt-test", "input": "hi"}}
        )
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["error"]["status_code"] == 403


def test_responses_websocket_reports_network_failure() -> None:
    app = create_app(AppSettings())
    app.dependency_overrides[get_responses_ws_client] = lambda: NetworkFailingClient()

    with TestClient(app) as client, client.websocket_connect("/v1/responses") as websocket:
        websocket.send_json(
            {"type": "response.create", "response": {"model": "gpt-test", "input": "hi"}}
        )
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert "connection lost" in error["error"]["message"]
