from collections.abc import Awaitable, Callable

import httpx2
import pytest

from app.model_provider.ghc_client.device_flow import DeviceFlowClient, DeviceFlowError


def _client(
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    sleep: Callable[[float], Awaitable[None]],
    web_base_url: str | None = None,
) -> tuple[DeviceFlowClient, httpx2.AsyncClient]:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    # Left unpassed rather than defaulted to the constant, so the tests below that assert github.com are still testing the *default* and not a value they supplied themselves.
    if web_base_url is None:
        return DeviceFlowClient(http_client, sleep=sleep), http_client
    return DeviceFlowClient(http_client, sleep=sleep, web_base_url=web_base_url), http_client


@pytest.mark.asyncio
async def test_request_device_code_uses_github_oauth_contract() -> None:
    async def no_sleep(delay: float) -> None:
        del delay

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url == "https://github.com/login/device/code"
        assert request.method == "POST"
        assert request.headers["accept"] == "application/json"
        assert request.headers["content-type"] == "application/json"
        assert request.read() == b'{"client_id":"Iv1.b507a08c87ecfe98","scope":"read:user"}'
        return httpx2.Response(
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

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url == "https://github.com/login/oauth/access_token"
        return httpx2.Response(200, json=next(responses))

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

    def handler(request: httpx2.Request) -> httpx2.Response:
        del request
        return httpx2.Response(200, json={"error": "access_denied"})

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


@pytest.mark.asyncio
async def test_both_endpoints_follow_a_tenant_web_origin() -> None:
    """A data-residency tenant issues its own device codes, and both calls must reach it.

    Both, not one: the device code and the token exchange are a pair, and posting the second to dotcom would fail against a code dotcom never issued. The paths must stay put while only the origin moves.
    """
    posted: list[str] = []

    async def no_sleep(delay: float) -> None:
        del delay

    def handler(request: httpx2.Request) -> httpx2.Response:
        posted.append(str(request.url))
        if request.url.path.endswith("/device/code"):
            return httpx2.Response(
                200,
                json={
                    "device_code": "device",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://octocorp.ghe.com/login/device",
                    "expires_in": 900,
                    "interval": 5,
                },
            )
        return httpx2.Response(200, json={"access_token": "ghu_tenant"})

    # A trailing slash is what an operator's config file tends to carry; it must not double up in the path.
    client, http_client = _client(handler, sleep=no_sleep, web_base_url="https://octocorp.ghe.com/")
    try:
        device = await client.request_device_code()
        token = await client.poll_access_token(device)
    finally:
        await http_client.aclose()

    assert token == "ghu_tenant"
    assert posted == [
        "https://octocorp.ghe.com/login/device/code",
        "https://octocorp.ghe.com/login/oauth/access_token",
    ]
