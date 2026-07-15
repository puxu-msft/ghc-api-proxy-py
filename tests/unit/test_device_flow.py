from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.auth.device_flow import DeviceFlowClient, DeviceFlowError


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    sleep: Callable[[float], Awaitable[None]],
) -> tuple[DeviceFlowClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DeviceFlowClient(http_client, sleep=sleep), http_client


@pytest.mark.asyncio
async def test_request_device_code_uses_github_oauth_contract() -> None:
    async def no_sleep(delay: float) -> None:
        del delay

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://github.com/login/device/code"
        assert request.method == "POST"
        assert request.headers["accept"] == "application/json"
        assert request.headers["content-type"] == "application/json"
        assert request.read() == b'{"client_id":"Iv1.b507a08c87ecfe98","scope":"read:user"}'
        return httpx.Response(
            200,
            json={
                "device_code": "device",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            },
        )

    client, http_client = _client(handler, sleep=no_sleep)
    try:
        device = await client.request_device_code()
    finally:
        await http_client.aclose()

    assert device.user_code == "ABCD-EFGH"


@pytest.mark.asyncio
async def test_poll_handles_pending_and_slow_down_before_success() -> None:
    sleeps: list[float] = []
    responses = iter(
        [
            {"error": "authorization_pending"},
            {"error": "slow_down"},
            {"access_token": "ghu_device"},
        ]
    )

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://github.com/login/oauth/access_token"
        return httpx.Response(200, json=next(responses))

    client, http_client = _client(handler, sleep=record_sleep)
    device = client.parse_device_code(
        {
            "device_code": "device",
            "user_code": "CODE",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
    )
    try:
        token = await client.poll_access_token(device)
    finally:
        await http_client.aclose()

    assert token == "ghu_device"
    assert sleeps == [5, 5, 10]


@pytest.mark.asyncio
async def test_poll_raises_for_access_denied() -> None:
    async def no_sleep(delay: float) -> None:
        del delay

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"error": "access_denied"})

    client, http_client = _client(handler, sleep=no_sleep)
    device = client.parse_device_code(
        {
            "device_code": "device",
            "user_code": "CODE",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
    )
    try:
        with pytest.raises(DeviceFlowError, match="access_denied"):
            await client.poll_access_token(device)
    finally:
        await http_client.aclose()