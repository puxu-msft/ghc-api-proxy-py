import httpx2
import pytest

from app.ghc_client import fetch_models

CATALOG = {"object": "list", "data": [{"id": "model-a"}, {"id": "model-b"}]}


@pytest.mark.asyncio
async def test_fetch_returns_raw_payload_and_etag() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/models"
        assert request.headers["authorization"] == "Bearer copilot"
        assert "if-none-match" not in request.headers
        return httpx2.Response(200, json=CATALOG, headers={"etag": 'W/"v1"'})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        page = await fetch_models(
            http_client,
            "https://copilot.example",
            {"Authorization": "Bearer copilot"},
        )

    assert page is not None
    assert page.raw == CATALOG
    assert page.etag == 'W/"v1"'


@pytest.mark.asyncio
async def test_known_etag_is_negotiated_and_304_reports_no_change() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["if-none-match"])
        return httpx2.Response(304)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        page = await fetch_models(
            http_client,
            "https://copilot.example",
            {},
            etag='W/"v1"',
        )

    assert page is None
    assert seen == ['W/"v1"']


@pytest.mark.asyncio
async def test_base_url_trailing_slash_does_not_double_up() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return httpx2.Response(200, json=CATALOG)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        await fetch_models(http_client, "https://copilot.example/", {})

    assert seen == ["https://copilot.example/models"]


@pytest.mark.asyncio
async def test_error_status_propagates() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"error": "boom"})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        with pytest.raises(httpx2.HTTPStatusError):
            await fetch_models(http_client, "https://copilot.example", {})
